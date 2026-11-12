# -*- coding: utf-8 -*-
"""武侠章回标注执行器（LLM 契约阶段 annotate 的 API 量产件，2026-11-04）。

定位：pipeline_wuxia.py 的 annotate 阶段（读 tagged/<书>/NNN.struct.md →
写 tagged/<书>/NNN.tagged.md）的 API 执行器。规则来源 = skills/SKILL_03a_实体标注.md
§二 SYSTEM_PROMPT（运行时从 SKILL 原文提取，禁止手抄；规则改动改 SKILL 不改本脚本）。
要点：
  1) 两遍标注：P1 首标 → P2 自检补标（漏标器物/地点/数量/时间/类型码复核）；
  2) 回锚保真：LLM 只出"标记 + 文本"，程序用 difflib 把令牌锚回原始 struct 文本，
     原文永不采用模型转写结果（DEF-02/DEF-09 类缺陷免疫）；
  3) 结构校验：类型码白名单 / 闭合 / 无嵌套 / 无重叠 / 管道非空 / 剥标逐字等于底本；
  4) 修辞层：复用 annotate_rhetoric_llm 的候选索引与裁决（※），落标后再复验；
  5) 费用：逐次 API usage 记录（prompt/cache hit/completion），按 DeepSeek 官方价
     （.token_cost_config.json 非高峰基准；高峰窗口 ×2，规则同 annotate_rhetoric_llm）
     逐回计费，落 logs/token_usage/annotate_<书>_<回>_<时间>.json。

用法：
    python scripts/annotate_chapter_llm.py --book 白发魔女传 --chapter 20
    python scripts/annotate_chapter_llm.py --book 白发魔女传 --chapter 20 --dry-run
    python scripts/annotate_chapter_llm.py --book 白发魔女传 --chapter 19 --out-dir logs/_calib
    python scripts/annotate_chapter_llm.py --book 白发魔女传 --chapters 20-32
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import io
import os
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

_STDOUT_PINS = []          # 防二次 TextIOWrapper 包装后原对象被 GC 连带关闭共享 buffer
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    _STDOUT_PINS.append(sys.stdout)
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    _STDOUT_PINS.append(sys.stdout)

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import api_config  # noqa: E402
import config      # noqa: E402
import symbols     # noqa: E402

# ---------------------------------------------------------------- 常量 ----
SKILL = config.DIR_SKILLS / "SKILL_03a_实体标注.md"
PRICE_OFFPEAK = {"input_miss": 0.15, "input_hit": 0.003, "output": 0.60}  # USD / 1M tok
PEAK_MULT = 2.0
PEAK_WINDOWS = ((1, 0, 4, 0), (6, 0, 10, 0))   # UTC 周一-周五（与 annotate_rhetoric_llm 同口径）
PEAK_DAYS = (0, 1, 2, 3, 4)
ENT_OK = set(symbols.ENTITIES)
VERB_OK = set(symbols.VERBS)
PIPE = "|"

PARA_RE = re.compile(r"^\[(\d+)\] (.*)$")
FENCE_OPEN_RE = re.compile(r"^::: ?(\S+)")


# ---------------------------------------------------------------- 提示词 ----
def load_system_prompt():
    """从 SKILL_03a §二 的 ````text 围栏提取唯一权威 SYSTEM_PROMPT。"""
    text = io.open(SKILL, encoding="utf-8").read()
    m = re.search(r"````text\n(.*?)\n````", text, re.S)
    if not m:
        raise SystemExit(f"SKILL_03a 未找到 SYSTEM_PROMPT 围栏: {SKILL}")
    ver = re.search(r"## 二、SYSTEM_PROMPT（(v[0-9.]+)", text)
    return m.group(1), (ver.group(1) if ver else "unknown")


def cn_chapter(n: int) -> str:
    """20 → 第二十回（仅用于上下文包）。0 → 楔子（000 底本文件，梁羽生部分书目有楔子）。"""
    if n == 0:
        return "楔子"
    digits = "零一二三四五六七八九"
    if n < 20:
        base = ["", "第一回", "第二回", "第三回", "第四回", "第五回", "第六回", "第七回",
                "第八回", "第九回", "第十回", "第十一回", "第十二回", "第十三回", "第十四回",
                "第十五回", "第十六回", "第十七回", "第十八回", "第十九回"]
        return base[n]
    tens, rest = divmod(n, 10)
    head = "" if tens == 1 else digits[tens]
    return f"第{head}十{digits[rest] if rest else ''}回"


def _get_add_scope_notes():
    """回级注记解析的单一来源 = accept_batch._add_scope_notes。

    accept_batch 在本模块导入期会反向 import 本模块，故此处必须延迟导入；独立运行
    （accept_batch 不可用）时返回 None，退化为无回级注记（与旧行为一致）。
    """
    try:
        from accept_batch import _add_scope_notes
        return _add_scope_notes
    except Exception:      # noqa: BLE001 - 任何导入失败都按“无回级注记”降级
        return None


def load_mapping_table_parts(book: str):
    """《已核准映射表》→ (全局 pairs 列表, {(回,显示串): 规范名} 回级注记)。

    全局段 = registry/entities.json 的 @ 类映射 + 已过审金标准 tagged 中实际使用过的
    管道（显示串→规范名）。回级注记只来自 registry 记录（context_notes 或
    aliases/contextual 中的 dict 条目，见 accept_batch `_add_scope_notes`）；
    **无回级注记的现有输入，输出与旧 `load_mapping_table` 完全一致**。
    """
    pairs = {}
    scoped = {}
    add_notes = _get_add_scope_notes()

    reg = config.DIR_REGISTRY / "entities.json"
    if reg.exists():
        data = json.loads(io.open(reg, encoding="utf-8").read())
        entities = data.get("entities", []) if isinstance(data, dict) else []
        for e in entities:
            if e.get("type") != "@" or e.get("status") == "pending":
                continue
            canon = (e.get("canonical") or "").strip()
            if not canon:
                continue
            for a in list(e.get("aliases") or []) + list(e.get("contextual") or []):
                if isinstance(a, dict):
                    continue      # 回级注记统一走 _add_scope_notes
                a = (a or "").strip()
                if not a or "（" in a or "(" in a or a == canon:
                    continue
                pairs.setdefault(a, canon)
            if add_notes is not None:
                # book 必传（2026-11-05 修复）：None 时 accept_batch 会丢弃所有带书级
                # 作用域的条目（宁缺勿错），本书注记永不生效；传 book 后只装载本书条目。
                add_notes(e, canon, scoped, book=book)
    # 已过审金标准里的管道即人工核准映射（001-019 tagged 产物；跨回全局，口径不变）
    d = config.DIR_TAGGED / book
    if d.is_dir():
        for p in sorted(d.glob("*.tagged.md")):
            t = io.open(p, encoding="utf-8").read()
            for m in re.finditer(r"〖@([^|〗]+)\|([^〗]+)〗", t):
                disp, canon = m.group(1).strip(), m.group(2).strip()
                if disp and canon and disp != canon:
                    pairs.setdefault(disp, canon)
    base = sorted(pairs.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    return base, scoped


def load_mapping_table(book: str, chapter=None) -> list:
    """《已核准映射表》→ [(显示串, 规范名), ...]（按显示串长度降序）。

    chapter=None（缺省）行为与旧版完全一致（回级注记不参与）；传 chapter 时按
    (书,回,显示串) 覆盖同显示串全局映射，其余回级条目不出现（不跨回污染）。
    """
    base, scoped = load_mapping_table_parts(book)
    return _apply_scoped_pairs(base, scoped, chapter)


def load_mapping_file_parts(path, book=None) -> tuple:
    """映射快照 JSON → (全局 pairs 列表, 回级注记 dict)（条目级 chapter/scope 字段）。

    book 非 None 时传给 `_pairs_from_items` 做书级过滤（2026-11-05 修复：原恒 None，
    多书共表快照会把别书的 (回,显示串) 注记装入，同键互相覆盖、跨书串味）。
    """
    from accept_batch import _mapping_items_from_obj, _pairs_from_items
    data = json.loads(io.open(path, encoding="utf-8").read())
    items = _mapping_items_from_obj(data)
    if items is None:
        raise SystemExit(f"[ERROR] 无法识别的映射快照 schema：{path}")
    pairs, canons, scoped = set(), set(), {}
    _pairs_from_items(items, pairs, canons, scoped=scoped, book=book)
    base = sorted(pairs, key=lambda kv: (-len(kv[0]), kv[0]))
    return base, scoped


def _apply_scoped_pairs(base, scoped, chapter):
    """回级视图：chapter 声明的条目覆盖同显示串全局映射；chapter=None 原样返回 base。"""
    if chapter is None or not scoped:
        return base
    disp_set = {d for d, _ in base}
    out = []
    for disp, canon in base:
        out.append((disp, scoped[(chapter, disp)]) if (chapter, disp) in scoped
                   else (disp, canon))
    for (c, disp), canon in scoped.items():
        if c == chapter and disp not in disp_set:
            out.append((disp, canon))
    return out


# ---------------------------------------------------------------- 计费 ----
def peak_utc(ts: float) -> bool:
    t = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    if t.weekday() not in PEAK_DAYS:
        return False
    hm = t.hour * 60 + t.minute
    return any(a * 60 + b <= hm < c * 60 + d for a, b, c, d in PEAK_WINDOWS)


def usage_cost(rec: dict) -> float:
    # opencode-go：DSH 订阅通道，不按 token 计费（token 数仍记录）；费用记 0
    if rec.get("provider") == "opencode-go":
        return 0.0
    p = PRICE_OFFPEAK if not rec["peak"] else {k: v * PEAK_MULT for k, v in PRICE_OFFPEAK.items()}
    return (rec["prompt_cache_hit_tokens"] * p["input_hit"]
            + rec["prompt_cache_miss_tokens"] * p["input_miss"]
            + rec["completion_tokens"] * p["output"]) / 1e6


class Usage:
    """单回 API usage 账本（含逐次记录与分阶段小计）。"""

    def __init__(self):
        self.records = []

    def add(self, stage: str, module: str, rec: dict):
        rec = dict(rec)
        rec["stage"] = stage
        rec["module"] = module
        rec["cost_usd"] = round(usage_cost(rec), 8)
        self.records.append(rec)

    def by_stage(self) -> dict:
        out = {}
        for r in self.records:
            s = out.setdefault(r["stage"], {"calls": 0, "input": 0, "cache_hit": 0,
                                            "output": 0, "cost_usd": 0.0})
            s["calls"] += 1
            s["input"] += r["prompt_tokens"]
            s["cache_hit"] += r["prompt_cache_hit_tokens"]
            s["output"] += r["completion_tokens"]
            s["cost_usd"] = round(s["cost_usd"] + r["cost_usd"], 8)
        return out

    def total(self) -> dict:
        s = {"calls": len(self.records), "input": 0, "cache_hit": 0, "output": 0, "cost_usd": 0.0}
        for r in self.records:
            s["input"] += r["prompt_tokens"]
            s["cache_hit"] += r["prompt_cache_hit_tokens"]
            s["output"] += r["completion_tokens"]
            s["cost_usd"] = round(s["cost_usd"] + r["cost_usd"], 8)
        return s


# ---------------------------------------------------------------- API ----
class LLM:
    """LLM 通道封装。provider:
       * deepseek   —— 官方 DeepSeek API（默认，原有行为）；
       * opencode-go —— 当前 DSH Session 使用的模型通道（deepseek-v4.1-flash，
                         OpenAI 兼容；需 x-opencode-session 头，凭据取 DSH 凭据库）。
    """

    OPENCODE_BASE = "https://opencode.ai/zen/go/v1"

    def __init__(self, model: str, usage: Usage, retries: int = 4, provider: str = "deepseek"):
        self.provider = provider
        if provider == "opencode-go":
            self.url = self.OPENCODE_BASE + "/chat/completions"
            self.key = (os.environ.get("OPENCODE_GO_API_KEY")
                        or api_config.dsh_credential("OPENCODE_GO_API_KEY"))
            self.extra_headers = {"x-opencode-session": str(uuid.uuid4())}
        else:
            self.url = api_config.get("deepseek", "url").rstrip("/") + "/chat/completions"
            self.key = api_config.get("deepseek", "key")
            self.extra_headers = {}
        self.model = model
        self.usage = usage
        self.retries = retries

    def call(self, system: str, user: str, max_tokens: int, stage: str) -> str:
        payload = {"model": self.model,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}],
                   "temperature": 0, "max_tokens": max_tokens, "stream": False,
                   "thinking": {"type": "disabled"}}
        body = json.dumps(payload).encode("utf-8")
        last = None
        for attempt in range(1, self.retries + 1):
            t0 = time.time()
            try:
                if self.provider == "opencode-go":
                    # opencode-go 网关对 urllib 默认头返回 403；requests + 精确头已验证 200
                    import requests  # 延迟导入，deepseek 通道零依赖变化
                    resp = requests.post(
                        self.url,
                        headers={"Content-Type": "application/json",
                                 "Authorization": "Bearer " + self.key,
                                 **self.extra_headers},
                        json=payload, timeout=(30, 180))
                    if resp.status_code != 200:
                        raise urllib.error.HTTPError(
                            self.url, resp.status_code, resp.text[:200], None, None)
                    data = json.loads(resp.text)
                else:
                    req = urllib.request.Request(
                        self.url, data=body,
                        headers={"Content-Type": "application/json",
                                 "Authorization": "Bearer " + self.key,
                                 **self.extra_headers})
                    with urllib.request.urlopen(req, timeout=600) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                u = data.get("usage", {}) or {}
                created = float(data.get("created") or time.time())
                rec = {"model": self.model, "provider": self.provider,
                       "created_utc": dt.datetime.fromtimestamp(created, tz=dt.timezone.utc).isoformat(),
                       "peak": peak_utc(created),
                       "prompt_tokens": u.get("prompt_tokens", 0),
                       "completion_tokens": u.get("completion_tokens", 0),
                       "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
                       "prompt_cache_hit_tokens": u.get("prompt_cache_hit_tokens", 0),
                       "prompt_cache_miss_tokens": u.get("prompt_cache_miss_tokens",
                                                         u.get("prompt_tokens", 0)),
                       "elapsed_s": round(time.time() - t0, 1)}
                self.usage.add(stage, "annotate", rec)
                content = data["choices"][0]["message"].get("content") or ""
                if not content.strip():
                    raise RuntimeError("空 content（可能触发 max_tokens/reasoning）")
                return content
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError,
                    RuntimeError, KeyError, json.JSONDecodeError) as e:
                last = e
                wait = (2, 6, 15, 30)[min(attempt - 1, 3)]
                print(f"      [retry {attempt}/{self.retries}] {type(e).__name__}: {str(e)[:120]}；{wait}s 后重试")
                time.sleep(wait)
        raise RuntimeError(f"API 调用失败（{self.retries} 次）：{last}")


# ---------------------------------------------------------------- 文本/令牌 ----
def strip_all(s: str) -> str:
    return symbols.strip_markup(s)


def split_blocks(out: str):
    """模型输出 → {pn: annotated_block_text}（不含 [N] 前缀）。"""
    res = {}
    cur, buf = None, []
    for line in out.split("\n"):
        m = PARA_RE.match(line)
        if m:
            if cur is not None:
                res[cur] = "\n".join(buf).strip("\n")
            cur, buf = int(m.group(1)), [m.group(2)]
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        res[cur] = "\n".join(buf).strip("\n")
    return res


def iter_tokens(s: str):
    """单遍扫描：产出 (open_idx, close_idx, kind, code, body)；容忍闭合符误写。"""
    i, n = 0, len(s)
    pairs = {"〖": "〗", "⟦": "⟧", "〘": "〙"}
    wrong = {"〖": "⟧", "⟦": "〗", "〘": "〙"}
    while i < n:
        ch = s[i]
        if ch in pairs:
            want = pairs[ch]
            j = s.find(want, i + 1)
            k = s.find(wrong[ch], i + 1)
            if j < 0 and k >= 0:
                yield (i, k, "fix", ch, s[i + 1:k])
                i = k + 1
                continue
            if j < 0:
                i += 1
                continue
            body = s[i + 1:j]
            code = body[0] if body else ""
            yield (i, j, "ok", code, body[1:] if body else "")
            i = j + 1
        else:
            i += 1


def normalize_pipes(s: str):
    """管道纪律机械归一（v1.8 §管道规则）：

      * 仅 @ / % / 动词允许挂管道；其他实体类型 〖=X|Y〗 → 〖=X〗（显示串不变）；
      * @ 管道后规范名与显示串相同 → 摘管道（〖@公孙大娘|公孙大娘〗 → 〖@公孙大娘〗）；
      * % 只允许 |时点 / |时长 / |年龄，其他标签摘除。
    返回 (新文本, 归一化条数)。剥标后正文不变。
    """
    out, last, n = [], 0, 0
    for (a, b, kind, code, body) in iter_tokens(s):
        if kind != "ok":
            continue
        out.append(s[last:a])
        disp, sep, note = body.partition(PIPE)
        new_body = body
        if code in ("@", "%") and sep:
            if code == "@" and note == disp:
                new_body = disp
                n += 1
            elif code == "%" and note not in ("时点", "时长", "年龄"):
                new_body = disp
                n += 1
        elif sep and code not in ("@", "%") and code not in VERB_OK:
            new_body = disp
            n += 1
        out.append(s[a] + code + new_body + s[b])
        last = b + 1
    out.append(s[last:])
    return "".join(out), n


def validate_and_repair(s: str, source: str):
    """令牌结构校验 + 确定性修复；返回 (fixed_text, problems, dropped)。"""
    problems, dropped = [], []
    # 0) 管道纪律归一（v1.8：仅 @/%/动词可挂管道；@ 同名管道摘除；% 受控标签）
    s, n_norm = normalize_pipes(s)
    if n_norm:
        problems.append(f"管道归一{n_norm}处")
    # 0b) 层-码一致性归一：〖⊠X〗 → ⟦⊠X⟧（实体括号内动词域码）、⟦@X⟧ → 〖@X〗
    n_layer = 0
    for (a, b, kind, code, body) in list(iter_tokens(s)):
        if kind != "ok":
            continue
        op = s[a]
        if op == "〖" and code in VERB_OK:
            s = s[:a] + "⟦" + code + body + "⟧" + s[b + 1:]
            n_layer += 1
        elif op == "⟦" and (code in ENT_OK or code == "※"):
            s = s[:a] + "〖" + code + body + "〗" + s[b + 1:]
            n_layer += 1
    if n_layer:
        problems.append(f"层码归一{n_layer}处")
    # 1) 归一化误写闭合符（逐处重扫，避免下标漂移）
    while True:
        fix = next(((a, b, ch, body) for (a, b, kind, ch, body) in iter_tokens(s)
                    if kind == "fix"), None)
        if fix is None:
            break
        a, b, ch, body = fix
        close = {"〖": "〗", "⟦": "⟧", "〘": "〙"}[ch]
        s = s[:a] + ch + body + close + s[b + 1:]
        problems.append(f"闭合符误写@{a}:{ch}{body[:12]}")
    # 2) 逐令牌校验；非法令牌摘除（保留显示串正文）
    edits = []
    for (a, b, kind, code, body) in iter_tokens(s):
        if kind != "ok":
            continue
        if any(c in body for c in "〖〗⟦⟧〘〙"):
            edits.append((a, b, "嵌套"))
            continue
        if code not in ENT_OK and code not in VERB_OK and code != "※":
            edits.append((a, b, f"非法类型码{code!r}"))
            continue
        disp = body.split(PIPE, 1)[0]
        if not disp:
            edits.append((a, b, "空显示串"))
            continue
    for a, b, why in sorted(edits, key=lambda x: -x[0]):
        dropped.append(f"{why}@{a}:{s[a:b + 1][:18]}")
        # 令牌区间 s[a..b]（a=开括号，b=闭括号）：摘掉开括号+类型码 与 闭括号，保留正文
        s = s[:a] + s[a + 2:b] + s[b + 1:]
    # 3) 孤立闭括号清理 + 未闭合开括号摘除
    out, stack = [], []
    for ch in s:
        if ch == "〖":
            stack.append(("〗", len(out)))
            out.append(ch)
        elif ch == "⟦":
            stack.append(("⟧", len(out)))
            out.append(ch)
        elif ch == "〘":
            stack.append(("〙", len(out)))
            out.append(ch)
        elif ch in "〗⟧〙":
            if stack and stack[-1][0] == ch:
                stack.pop()
                out.append(ch)
            else:
                problems.append("孤立闭括号")
        else:
            out.append(ch)
    s = "".join(out)
    if stack:
        for _close, pos in reversed(stack):
            problems.append(f"未闭合@{pos}")
        for _close, pos in sorted(stack, key=lambda x: -x[1]):
            if pos < len(s):
                s = s[:pos] + s[pos + 1:]
    return s, problems, dropped


def parse_annotated(s: str):
    """解析标注文本 → (tokens, plain)。

    tokens = [(plain_start, plain_end, token_str, display, code)]，位置坐标属于 plain
    （＝剥标后正文），这是回锚映射的正确坐标系；block_out 内的原始下标不能直接用于 plain。
    """
    pairs = {"〖": "〗", "⟦": "⟧", "〘": "〙"}
    tokens, parts = [], []
    plen, i, n = 0, 0, len(s)
    while i < n:
        ch = s[i]
        if ch in pairs:
            j = s.find(pairs[ch], i + 1)
            if j < 0:
                parts.append(ch)
                plen += 1
                i += 1
                continue
            body = s[i + 1:j]
            disp = body[1:].split(PIPE, 1)[0] if body else ""
            tokens.append((plen, plen + len(disp), s[i:j + 1], disp, body[0] if body else ""))
            parts.append(disp)
            plen += len(disp)
            i = j + 1
        else:
            parts.append(ch)
            plen += 1
            i += 1
    return tokens, "".join(parts)


def reanchor(block_out: str, original: str):
    """把模型输出中的令牌锚回原始段落文本。

    返回 (annotated_text, dropped)。锚定失败/重叠的令牌丢弃；
    annotated_text 剥标后必然逐字等于 original（构造保证）。
    """
    tokens, plain = parse_annotated(block_out)
    if plain == original:
        blocks = [difflib.Match(0, 0, len(original))] if original else []
    else:
        sm = difflib.SequenceMatcher(None, plain, original, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size > 0]

    def m2o(pos, prefer_end=False):
        for b in blocks:
            if b.a <= pos < b.a + b.size:
                return b.b + (pos - b.a)
            if prefer_end and pos == b.a + b.size and b.size > 0:
                return b.b + b.size
        return None

    marks, drops = [], []
    for (pa, pb, tok, disp, _code) in tokens:
        oa = m2o(pa)
        ob = m2o(pb, prefer_end=True)
        if oa is not None and ob is not None and oa <= ob and plain[pa:pb] == original[oa:ob] \
                and disp and original[oa:ob] == disp:
            marks.append((oa, ob, tok))
            continue
        if disp:
            hits = [m.start() for m in re.finditer(re.escape(disp), original)]
            if len(hits) == 1:
                marks.append((hits[0], hits[0] + len(disp), tok))
                continue
        drops.append(f"未锚定:{tok[:20]}")
    marks.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    kept, occupied = [], []
    for oa, ob, tok in marks:
        if any(not (ob <= c or oa >= d) for c, d in occupied):
            drops.append(f"重叠丢弃:{tok[:20]}")
            continue
        occupied.append((oa, ob))
        kept.append((oa, ob, tok))
    out = list(original)
    for oa, ob, tok in sorted(kept, key=lambda x: -x[0]):
        out[oa:ob] = [tok]
    result = "".join(out)
    if strip_all(result) != original:
        result, drops = original, [f"剥标不一致，整段令牌回退（{len(kept)} 个）"]
    return result, drops


# ---------------------------------------------------------------- 分块 ----
def read_struct(path: Path):
    text = io.open(path, encoding="utf-8").read()
    lines = text.split("\n")
    paras = {}
    for ln in lines:
        m = PARA_RE.match(ln)
        if m:
            paras[int(m.group(1))] = m.group(2)
    return lines, paras


def build_chunks(paras: dict, max_chars: int):
    """连续段落贪心打包（单段超限独立成块）。返回 [[pn,...], ...]。"""
    chunks, cur, size = [], [], 0
    for pn in paras:
        L = len(paras[pn])
        if cur and size + L > max_chars:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(pn)
        size += L
        if L > max_chars:
            chunks.append(cur)
            cur, size = [], 0
    if cur:
        chunks.append(cur)
    return chunks


# ---------------------------------------------------------------- 上下文包 ----
def mapping_text(pairs, limit=400) -> str:
    if not pairs:
        return "（无）"
    return "；".join(f"{a}→{b}" for a, b in pairs[:limit])


def context_pack(book: str, ch: int, idx: int, total: int, prompt_ver: str, mapping: str,
                 pns, paras) -> str:
    head = (f"【上下文包】\n书名：《{book}》；回号：{ch:03d}（{cn_chapter(ch)}）；"
            f"块号：{ch:03d}.{idx}/{total}；规则版本：SKILL_03a {prompt_ver}；"
            f"段号范围：[{min(pns)}]-[{max(pns)}]。\n"
            f"《已核准映射表》（人物管道只允许用下列映射或当前块内可确认的文内证据；"
            f"规范名与显示串相同的**不挂管道**）：\n{mapping}\n\n【待标注正文】\n")
    body = "\n\n".join(f"[{pn}] {paras[pn]}" for pn in pns)
    return head + body


P2_INSTRUCTION = """\n【上一稿·第一遍标注】\n{draft}\n【第二遍任务：自检补标与类型校正】请以第一遍为底稿，逐句复核后输出修订稿：
1. 补齐漏标的实体：具体器物（兵器/暗器/衣物/钱财/灯烛/岩石草木等）、动物坐骑、具名或情节性地点（谷口/山壁/峡谷/路口/房内/院中/山腰等）、数量（数词+量词、约量确数、承载情节信息的计数）、时间（时点/时长/年龄）、技艺（☆）、概念（^）、文书（{）、组织（◆）、职衔（;）、身份（#）。
2. 复核类型码：☆（武功技艺）vs •（器物）、#（身份）vs ;（职衔）、=（地点）vs ◆（组织）、% vs $。
3. 复核人物管道：显示串与规范名相同时不挂管道（写 〖@公孙大娘〗 而不是 〖@公孙大娘|公孙大娘〗）。
4. 复核动词边界：结果补语保留在内、方式修饰留外、不吞宾语、不标命令内容/意图/否定/比喻性描述。
5. 只输出修订后的完整标注正文（保留每个 [N] 段号），不得解释、不得增删原文任何字符；不确定的保持原样。"""


# ---------------------------------------------------------------- 标注主流程 ----
def annotate_blocks(llm: LLM, system: str, book: str, ch: int, paras: dict,
                    chunks, prompt_ver: str, mapping: str,
                    max_tokens: int, report: list):
    """两遍标注 → ({pn: annotated_text}, {pn: draft_text})。"""
    n_total = len(chunks)

    def run_pass(pass_no: int, seed: dict) -> dict:
        result = {}
        for idx, pns in enumerate(chunks, 1):
            user = context_pack(book, ch, idx, n_total, prompt_ver, mapping, pns, paras)
            if pass_no == 2:
                draft = "\n\n".join(f"[{pn}] {seed.get(pn, paras[pn])}" for pn in pns)
                user += P2_INSTRUCTION.replace("{draft}", draft)
            stage = f"P{pass_no}"
            out = llm.call(system, user, max_tokens, stage)
            blocks = split_blocks(out)
            missing = [pn for pn in pns if pn not in blocks]
            for pn in missing:
                single = context_pack(book, ch, idx, n_total, prompt_ver, mapping, [pn], paras)
                if pass_no == 2:
                    single += P2_INSTRUCTION.replace("{draft}",
                                                     f"[{pn}] {seed.get(pn, paras[pn])}")
                rep_mark = "" if pass_no == 1 else (
                    "\n【注意】上一稿整块输出遗漏了本段。请只标注本段，必须保留 [N] 段号。")
                try:
                    out2 = llm.call(system, single + rep_mark, max_tokens, stage)
                    b2 = split_blocks(out2)
                    blocks[pn] = b2.get(pn) or re.sub(r"^\s*\[\d+\]\s*", "", out2).strip()
                except RuntimeError:
                    blocks[pn] = paras[pn]
                report.append(f"  [P{pass_no}] 块{idx} 缺段[{pn}]已单段重标")
            extra = [p for p in blocks if p not in pns]
            if extra:
                report.append(f"  [P{pass_no}] 块{idx} 多余段号 {extra} 已忽略")
            for pn in pns:
                blk = blocks.get(pn, paras[pn])
                anchored, drops = reanchor(blk, paras[pn])
                fixed, probs, dropped = validate_and_repair(anchored, paras[pn])
                if drops or probs or dropped:
                    joined = "；".join((drops + probs + dropped)[:3])
                    report.append(f"  [P{pass_no}] [{pn}] 回锚丢弃{len(drops)} 修复{len(probs)} "
                                  f"摘除{len(dropped)}: {joined}")
                result[pn] = fixed
        return result

    draft = run_pass(1, {})
    final = run_pass(2, draft)
    return final, draft


# ---------------------------------------------------------------- 落盘/复验 ----
def compose_tagged(lines, annotated: dict) -> str:
    out = []
    for ln in lines:
        m = PARA_RE.match(ln)
        if m:
            pn = int(m.group(1))
            out.append(f"[{pn}] {annotated.get(pn, m.group(2))}")
        else:
            out.append(ln)
    return "\n".join(out)


def final_verify(tagged_text: str, struct_paras: dict) -> list:
    """复验：逐段剥标 == struct 原文；令牌合法；段序一致。"""
    errs = []
    got = {}
    for ln in tagged_text.split("\n"):
        m = PARA_RE.match(ln)
        if m:
            got[int(m.group(1))] = m.group(2)
    if list(got) != list(struct_paras):
        errs.append(f"段号序列不一致：{list(got)[:5]}… vs {list(struct_paras)[:5]}…")
    for pn, src in struct_paras.items():
        cur = got.get(pn, "")
        if strip_all(cur) != src:
            errs.append(f"[{pn}] 剥标 != 底本")
            continue
        _, probs, dropped = validate_and_repair(cur, src)
        if probs or dropped:
            errs.append(f"[{pn}] 令牌问题：{(probs + dropped)[:2]}")
    return errs


def summarize_tokens(text: str) -> dict:
    ce, cv, cr = {}, {}, {}
    for m in re.finditer(r"〖(.)", text):
        ce[m.group(1)] = ce.get(m.group(1), 0) + 1
    for m in re.finditer(r"⟦(.)", text):
        cv[m.group(1)] = cv.get(m.group(1), 0) + 1
    for m in re.finditer(r"〘(.)", text):
        cr[m.group(1)] = cr.get(m.group(1), 0) + 1
    return {"E": ce, "V": cv, "R": cr,
            "E_total": sum(ce.values()), "V_total": sum(cv.values()), "R_total": sum(cr.values())}


# ---------------------------------------------------------------- 修辞层 ----
def add_rhetoric(book: str, chapter: int, tagged_path: Path):
    """复用 annotate_rhetoric_llm 的候选索引/裁决/插标能力，逐回落 〘※〙。

    book 必须传入（2026-11-05 多书修复）：原签名只取回号，候选索引写死 白发魔女传，
    换书会把别书正文写回本书 tagged。
    """
    _STDOUT_PINS.append(sys.stdout)      # 该模块 import 时会再包一层 stdout，钉住原对象
    import annotate_rhetoric_llm as rl
    _STDOUT_PINS.append(sys.stdout)

    ch3 = f"{chapter:03d}"
    items = rl.load_items()
    # 候选源必须取 tagged_path 本身（2026-11-05 修复）：--out-dir 沙盒下默认 tagged
    # 路径可能是旧稿（回写覆盖新标注）或不存在（FileNotFoundError）。
    index = rl.build_candidates([ch3], items, book, base_dir=tagged_path.parent)
    info = index[ch3]
    if not info["cands"]:
        return {"candidates": 0, "inserted": 0, "star": 0, "skip": 0, "usage": [], "cost": 0.0}
    usage_log = []
    paras_needed = sorted({c["pn"] for c in info["cands"]})
    user = ["【待裁决段落】"]
    for pn in paras_needed:
        user.append(f"[PN {pn}] {info['paras'][pn]}")
    user.append("\n【候选列表】id | PN | 原文形式 | 规范形 | category | 该形第几次出现")
    for c in info["cands"]:
        user.append(f"{c['id']} | {c['pn']} | {c['raw']} | {c['canonical']} | "
                    f"{c['category']} | #{c['occ']} | …{c['ctx']}…")
    content = rl.call_deepseek([{"role": "system", "content": rl.SYSTEM_PROMPT},
                                {"role": "user", "content": "\n".join(user)}], usage_log)
    parsed = rl.parse_verdicts(content, [c["id"] for c in info["cands"]])
    if parsed is None:
        content = rl.call_deepseek(
            [{"role": "system", "content": rl.SYSTEM_PROMPT},
             {"role": "user", "content": "\n".join(user) +
              "\n\n上一次输出无法解析为 JSON。请严格只输出一个 JSON 对象。"}], usage_log)
        parsed = rl.parse_verdicts(content, [c["id"] for c in info["cands"]])
    if parsed is None:
        raise RuntimeError(f"{ch3} 修辞层裁决 JSON 不可解析")
    verdict_all, missing = parsed
    verdict_by_pn = {}
    for c in info["cands"]:
        verdict_by_pn.setdefault(c["pn"], {})[c["id"]] = verdict_all.get(c["id"], "skip")
    n_ins, n_star, n_skip = rl.apply_marks(ch3, info, verdict_by_pn)
    io.open(tagged_path, "w", encoding="utf-8", newline="\n").write("\n".join(info["lines"]))
    cost = 0.0
    for r in usage_log:
        p = dict(PRICE_OFFPEAK) if not r.get("peak") else {
            k: v * PEAK_MULT for k, v in PRICE_OFFPEAK.items()}
        cost += (r["prompt_cache_hit_tokens"] * p["input_hit"]
                 + r["prompt_cache_miss_tokens"] * p["input_miss"]
                 + r["completion_tokens"] * p["output"]) / 1e6
    return {"candidates": len(info["cands"]), "inserted": n_ins, "star": n_star,
            "skip": n_skip, "missing_verdict": missing, "usage": usage_log,
            "cost": round(cost, 8)}


# ---------------------------------------------------------------- 主流程 ----
def ensure_struct(book: str, chapter: int) -> Path:
    p = config.struct_path(book, chapter)
    if p.exists():
        return p
    print(f"  [structure] {book} 第 {chapter} 回 struct 缺失 → 生成")
    subprocess.run([sys.executable, str(SCRIPT_DIR / "generate_pn_wuxia.py"),
                    "--book", book, "--chapter", str(chapter), "--verify"],
                   cwd=str(config.ROOT), check=True)
    if not p.exists():
        raise SystemExit(f"struct 生成失败：{p}")
    return p


def annotate_one(book: str, chapter: int, args, system: str, prompt_ver: str,
                 mapping: str, usage: Usage, out_dir: Path) -> dict:
    print(f"\n=== 《{book}》第 {chapter:03d} 回标注开始 {dt.datetime.now():%H:%M:%S} ===")
    struct_p = ensure_struct(book, chapter)
    lines, paras = read_struct(struct_p)
    total_chars = sum(len(v) for v in paras.values())
    chunks = build_chunks(paras, args.max_chars)
    print(f"  struct：{len(paras)} 段 / {total_chars} 字 → {len(chunks)} 块（≤{args.max_chars} 字/块）")
    if args.dry_run:
        return {"chapter": chapter, "dry_run": True, "chunks": len(chunks),
                "paras": len(paras), "chars": total_chars}

    report = [f"# 第 {chapter:03d} 回标注执行报告",
              f"- 书：{book}；struct：{struct_p.name}；段数 {len(paras)}；字数 {total_chars}",
              f"- 分块：{len(chunks)} 块；规则：SKILL_03a {prompt_ver}；通道：{args.provider}；模型：{args.model}",
              f"- 开始：{dt.datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    llm = LLM(args.model, usage, provider=args.provider)
    t0 = time.time()
    final, draft = annotate_blocks(llm, system, book, chapter, paras, chunks, prompt_ver,
                                  mapping, args.max_tokens, report)
    elapsed = time.time() - t0
    tagged_text = compose_tagged(lines, final)
    errs = final_verify(tagged_text, paras)
    out_path = out_dir / f"{chapter:03d}.tagged.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(tagged_text)
    rhetoric = {"candidates": 0, "inserted": 0, "star": 0, "skip": 0, "usage": [], "cost": 0.0}
    if not args.no_rhetoric:
        rhetoric = add_rhetoric(book, chapter, out_path)
    final_text = io.open(out_path, encoding="utf-8").read()
    errs2 = final_verify(final_text, paras)
    stats = summarize_tokens(final_text)
    stage_cost = usage.by_stage()
    total = usage.total()
    print(f"  两遍标注 {elapsed:.0f}s；E={stats['E_total']} V={stats['V_total']} R={stats['R_total']}")
    print(f"  脚本内复验：{'PASS' if not errs2 else 'FAIL:' + '；'.join(errs2[:3])}")
    print(f"  本回费用：${total['cost_usd']:.6f}（{total['calls']} 次调用，入 {total['input']} tok / "
          f"缓存 {total['cache_hit']} / 出 {total['output']} tok）")
    report += ["", "## 结果",
               f"- 两遍耗时：{elapsed:.0f}s",
               f"- 令牌：E={stats['E_total']} V={stats['V_total']} R={stats['R_total']}",
               f"- 脚本内复验：{'PASS' if not errs2 else 'FAIL ' + '；'.join(errs2[:5])}",
               f"- 修辞层：候选 {rhetoric['candidates']}，落标 {rhetoric['inserted']}，"
               f"☆报告 {rhetoric['star']}，skip {rhetoric['skip']}",
               f"- 费用：${total['cost_usd']:.6f}", "", "## 分阶段用量", ""]
    for st, v in stage_cost.items():
        report.append(f"- {st}: {v['calls']} 次，入 {v['input']}（缓存 {v['cache_hit']}）"
                      f"出 {v['output']}，${v['cost_usd']:.6f}")
    if rhetoric.get("candidates"):
        report.append(f"- rhetoric: {len(rhetoric['usage'])} 次，${rhetoric['cost']:.6f}")
    report.append("")
    report.append(f"- 逐段问题日志 {len([r for r in report if '[P' in r])} 条")
    logs_dir = config.DIR_LOGS / "annotate" / book   # 书名一级目录（2026-11-05）：多书并行批次报告互不覆盖
    logs_dir.mkdir(parents=True, exist_ok=True)
    io.open(logs_dir / f"{chapter:03d}.report.txt", "w", encoding="utf-8", newline="\n").write(
        "\n".join(report) + "\n")
    usage_log = {
        "task": "章回标注（annotate 阶段）", "book": book, "chapter": chapter,
        "model": args.model, "provider": args.provider, "prompt": f"SKILL_03a {prompt_ver}",
        "started_at": dt.datetime.now().isoformat(),
        "paras": len(paras), "chars": total_chars, "chunks": len(chunks),
        "tokens": {"E": stats["E_total"], "V": stats["V_total"], "R": stats["R_total"]},
        "usage_by_stage": stage_cost, "usage": usage.records,
        "rhetoric": {k: v for k, v in rhetoric.items() if k != "usage"},
        "rhetoric_usage": rhetoric.get("usage") or [],
        "price_usd_per_1m": PRICE_OFFPEAK, "peak_mult": PEAK_MULT,
        "cost_usd": total["cost_usd"],
        "reverify_pass": not errs2,
    }
    td = config.DIR_LOGS / "token_usage"
    td.mkdir(parents=True, exist_ok=True)
    lp = td / f"annotate_{book}_{chapter:03d}_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
    io.open(lp, "w", encoding="utf-8", newline="\n").write(
        json.dumps(usage_log, ensure_ascii=False, indent=1) + "\n")
    print(f"  → {out_path}")
    print(f"  → {lp}")
    return {"chapter": chapter, "paras": len(paras), "chars": total_chars,
            "chunks": len(chunks), "tokens": stats, "cost_usd": total["cost_usd"],
            "usage": total, "by_stage": stage_cost, "reverify_pass": not errs2,
            "rhetoric": {k: v for k, v in rhetoric.items() if k != "usage"},
            "report": str(logs_dir / f"{chapter:03d}.report.txt")}


def parse_chapters(spec: str) -> list:
    out = []
    try:
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                out.extend(range(int(a), int(b) + 1))
            else:
                out.append(int(part))
    except ValueError:
        raise SystemExit(f"[ERROR] --chapters 格式非法：{spec!r}（示例：20-32 或 12,13）")
    return out


def main():
    ap = argparse.ArgumentParser(description="武侠章回标注执行器（两遍 LLM + 回锚 + 修辞层 + 计费）")
    ap.add_argument("--book", default=config.PILOT_BOOK)
    ap.add_argument("--chapter", type=int, default=None)
    ap.add_argument("--chapters", default=None, help="如 20-32 或 20,21,22")
    ap.add_argument("--provider", default="deepseek", choices=("deepseek", "opencode-go"),
                    help="LLM 通道：deepseek=官方 API（默认）；opencode-go=当前 DSH Session 模型通道")
    ap.add_argument("--model", default=None,
                    help="缺省：deepseek→deepseek-flash；opencode-go→deepseek-v4.1-flash")
    ap.add_argument("--max-chars", type=int, default=1100, help="每块原文上限（字）")
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--no-rhetoric", action="store_true", help="跳过修辞层补标")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-dir", default=None, help="产物目录（缺省 tagged/<书>）")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的 tagged 文件")
    ap.add_argument("--mapping-file", default=None,
                    help="冻结的《已核准映射表》快照（JSON: [[显示串,规范名],...]）；并行批次用")
    args = ap.parse_args()
    if not args.model:
        args.model = ("deepseek-v4.1-flash" if args.provider == "opencode-go"
                      else api_config.load().get("deepseek", {}).get("model", "deepseek-flash"))

    # 0 为合法回号（楔子），必须用 is not None 判空——原 `if args.chapter` 会把 0 当缺省回退到 [20]
    chapters = [args.chapter] if args.chapter is not None else (
        parse_chapters(args.chapters) if args.chapters else [20])
    system, prompt_ver = load_system_prompt()
    if args.mapping_file:
        base_pairs, scoped_pairs = load_mapping_file_parts(args.mapping_file,
                                                           book=args.book)
    else:
        base_pairs, scoped_pairs = load_mapping_table_parts(args.book)
    # 回级作用域（task-11）：有 scoped 注记时逐回取生效视图；无注记时 mapping 全程复用。
    pairs = _apply_scoped_pairs(base_pairs, scoped_pairs,
                                chapters[0] if chapters else None)
    mapping = mapping_text(pairs)
    out_dir = Path(args.out_dir) if args.out_dir else (config.DIR_TAGGED / args.book)
    # 防误覆盖：正式目录下已存在的回必须显式 --force（001-019 金标准不许被批量脚本重写）
    if not args.force and not args.dry_run:
        exists = [ch for ch in chapters if (out_dir / f"{ch:03d}.tagged.md").exists()]
        if exists:
            print(f"[abort] 目标已存在 tagged：{exists}（如确需重标请加 --force）")
            return
    print(f"规则：SKILL_03a {prompt_ver}；SYSTEM_PROMPT {len(system)} 字；"
          f"映射表 {len(pairs)} 条；模型 {args.model}")
    print(f"回目：{chapters}；输出目录：{out_dir}")

    results = []
    for ch in chapters:
        usage = Usage()
        mapping_ch = mapping if not scoped_pairs else mapping_text(
            _apply_scoped_pairs(base_pairs, scoped_pairs, ch))
        try:
            r = annotate_one(args.book, ch, args, system, prompt_ver, mapping_ch, usage, out_dir)
            results.append(r)
        except Exception as e:  # noqa: BLE001
            print(f"  [error] 第 {ch} 回失败：{type(e).__name__}: {e}")
            results.append({"chapter": ch, "error": f"{type(e).__name__}: {e}"})

    if len(results) > 1:
        print("\n===== 批次费用汇总 =====")
        tot = 0.0
        for r in results:
            if r.get("error"):
                print(f"  {r['chapter']:03d}: ERROR {r['error']}")
                continue
            tot += r["cost_usd"]
            t = r.get("tokens", {})
            print(f"  {r['chapter']:03d}: {r.get('chars', 0)} 字 E={t.get('E_total', 0)} "
                  f"V={t.get('V_total', 0)} R={t.get('R_total', 0)} "
                  f"${r['cost_usd']:.6f} 复验={'PASS' if r.get('reverify_pass') else 'FAIL'}")
        print(f"  合计 ${tot:.6f}")


if __name__ == "__main__":
    main()
