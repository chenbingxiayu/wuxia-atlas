#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修辞层启用补标（SKILL_02j ※；wordlists/rhetoric.json 精确匹配 + LLM 逐处裁决）。

docs/35 §三.4 启用口径 / docs/37 执行记录：
  1. 候选索引：tagged 全回按 rhetoric.json surface 精确匹配——仅取正文段落
     （标题行与 ::: 围栏块除外：对联/回末对归结构层，02j 固化单元分流），
     且命中区间须完全落在既有 〖〗⟦⟧〘〙 标注区间之外的纯文本中；
     变体（敬酒不吃你要吃罚酒）按消歧管道形态 〘※原文形式|规范形式〙 落标。
  2. LLM 逐处裁决（deepseek-flash，temperature=0）：※=修辞固定表达 /
     ☆=技法专名（本轮不标仅报告，交 ☆ 词表流程）/ skip=非固化用法。
  3. 机械插入：仅按裁决包标记，不改任何原文字符；逐段剥新标回读断言 = 原段。
  4. 花费：聚合 API usage，按 DeepSeek 官方价（高峰/非高峰，USD/百万 token）
     计费，落 logs/token_usage/。

用法：
    python scripts/annotate_rhetoric_llm.py --dry-run     # 仅候选索引，不调 API
    python scripts/annotate_rhetoric_llm.py               # 全回执行
    python scripts/annotate_rhetoric_llm.py --chapters 5,15,17
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import api_config  # noqa: E402
import config  # noqa: E402

# ---- DeepSeek 官方价（USD / 百万 token；2026-11 取自 api-docs.deepseek.com 定价页）----
PRICE_OFFPEAK = {"input_miss": 0.15, "input_hit": 0.003, "output": 0.60}
PEAK_MULT = 2.0
# 高峰：UTC 周一至周五 01:00-04:00 与 06:00-10:00
PEAK_WINDOWS = ((1, 0, 4, 0), (6, 0, 10, 0))
PEAK_DAYS = (0, 1, 2, 3, 4)  # Mon=0

VARIANTS = {  # surface -> [(原文形式, 规范形式)]；原文形式＝待匹配串
    "敬酒不吃吃罚酒": [("敬酒不吃吃罚酒", None), ("敬酒不吃你要吃罚酒", "敬酒不吃吃罚酒")],
}

SYSTEM_PROMPT = (
    "你是武侠小说语料修辞层标注裁决员。只输出一个 JSON 对象，不要输出任何解释或代码围栏。"
    "任务：对候选列表逐条裁决该处出现是否作为修辞层固定表达标注 〘※…〙。裁决规则：\n"
    "1. category 为 成语/俗语/四字语/四字成语 → 默认 mark=※（固化表达即标，含对白内）。\n"
    "2. category 为 惯用语/武学惯用语/武学意象语/阵法意象语/江湖切口 → "
    "该处为比喻性/程式化固定用法 → mark=※；该处实为武功招式/阵法/身法的专名指称"
    "（如『一招苍鹰扑兔』式技法名）→ mark=☆（本轮不标，仅报告）。\n"
    "3. 该出现并非固化表达用法（偶然字面组合、被既有标注切开、明显不成立）→ mark=skip。\n"
    "4. 你不改动文本，只做裁决；候选的『原文形式』已由精确匹配定位，你只裁决语境。\n"
    '输出格式：{"marks":[{"id":1,"mark":"※","note":"可选简注"},…]}——id 必须覆盖候选列表全部编号，逐条给全。'
)


# ---------------------------------------------------------------- 语料解析 ----
def load_items():
    src = config.DIR_WORDLISTS / "rhetoric.json"
    data = json.loads(io.open(src, encoding="utf-8").read())
    return data["items"]


def parse_blocks(text: str):
    """按行切块：title / fence / paragraph。返回 [(kind, start_line, end_line, pn)]，行号半开区间。"""
    lines = text.split("\n")
    blocks, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        if i == 0 and line.startswith("# "):
            blocks.append(("title", i, i + 1, None))
            i += 1
            continue
        m = re.match(r"^::: ?(\S+)", line)
        if m:
            j = i + 1
            while j < n and not re.match(r"^:::\s*$", lines[j]):
                j += 1
            blocks.append(("fence", i, min(j + 1, n), None))
            i = min(j + 1, n)
            continue
        mp = re.match(r"^\[(\d+)\] ", line)
        if mp:
            blocks.append(("para", i, i + 1, int(mp.group(1))))
            i += 1
            continue
        blocks.append(("other", i, i + 1, None))
        i += 1
    return lines, blocks


def mark_spans(s: str):
    """既有 〖〗⟦⟧〘〙 令牌覆盖区间列表（防嵌套/跨层插入）。"""
    spans, stack = [], []
    pairs = {"〖": "〗", "⟦": "⟧", "〘": "〙"}
    for idx, ch in enumerate(s):
        if ch in pairs:
            stack.append((ch, idx))
        elif ch in pairs.values():
            for k in range(len(stack) - 1, -1, -1):
                if pairs[stack[k][0]] == ch:
                    _, st = stack.pop(k)
                    spans.append((st, idx + 1))
                    break
    return spans


def plain_hits(s: str, needle: str, claimed: list):
    """返回 needle 在纯文本区间的全部命中起点（与 claimed 及既有标注不重叠）。"""
    spans = mark_spans(s)
    out, start = [], 0
    while True:
        pos = s.find(needle, start)
        if pos < 0:
            break
        end = pos + len(needle)
        inside = any(not (end <= a or pos >= b) for a, b in spans)
        clash = any(not (end <= a or pos >= b) for a, b in claimed)
        if not inside and not clash:
            out.append(pos)
        start = pos + 1
    return out


# ---------------------------------------------------------------- LLM 调用 ----
def peak_utc(ts: float) -> bool:
    t = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    if t.weekday() not in PEAK_DAYS:
        return False
    hm = t.hour * 60 + t.minute
    return any(a * 60 <= hm < b * 60 for a, b, _, _ in
               [(w[0], w[1], 0, 0) for w in PEAK_WINDOWS])


def call_deepseek(messages, usage_log):
    url = api_config.get("deepseek", "url").rstrip("/") + "/chat/completions"
    model = api_config.load().get("deepseek", {}).get("model", "deepseek-flash")
    payload = {"model": model, "messages": messages,
               "temperature": 0, "max_tokens": 4000, "stream": False}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + api_config.get("deepseek", "key")})
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            u = data.get("usage", {})
            created = float(data.get("created") or time.time())
            rec = {"model": model, "created_utc": dt.datetime.fromtimestamp(
                       created, tz=dt.timezone.utc).isoformat(),
                   "peak": peak_utc(created),
                   "prompt_tokens": u.get("prompt_tokens", 0),
                   "completion_tokens": u.get("completion_tokens", 0),
                   "prompt_cache_hit_tokens": u.get("prompt_cache_hit_tokens", 0),
                   "prompt_cache_miss_tokens": u.get("prompt_cache_miss_tokens",
                                                     u.get("prompt_tokens", 0))}
            usage_log.append(rec)
            return data["choices"][0]["message"]["content"]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            wait = (2, 6, 15)[min(attempt, 2)]
            print(f"    [retry] 第 {attempt + 1} 次失败：{e}；{wait}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"DeepSeek 调用三次失败：{last_err}")


def parse_verdicts(content: str, ids: list):
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    got = {}
    for it in data.get("marks", []):
        try:
            got[int(it["id"])] = str(it.get("mark", "skip")).strip()
        except (KeyError, TypeError, ValueError):
            continue
    missing = [i for i in ids if i not in got]
    return got, missing


# ---------------------------------------------------------------- 主流程 ----
def build_candidates(chapters, items, book=config.PILOT_BOOK, base_dir=None):
    """返回 {ch: {"paras": {pn: text}, "cands": [cand]}}；cand 含 id 全局编号。

    book 参数（2026-11-05 多书修复）：原实现写死 白发魔女传，换书会把别书 tagged
    当成本书候选源、并在 apply_marks 后把别书正文写回本书产物。缺省仍取试点书，
    保持旧调用（`build_candidates([ch], items)`）行为不变。
    base_dir 参数（2026-11-05 修复）：显式指定候选源目录；annotate_chapter_llm 的
    `--out-dir` 沙盒模式下必须读刚写好的 out_path 而非默认 tagged 路径，否则会把
    默认路径旧稿回写进产物。缺省 = DIR_TAGGED/book，旧行为不变。
    """
    out, gid = {}, 0
    root = Path(base_dir) if base_dir else (config.DIR_TAGGED / book)
    for ch in chapters:
        path = root / f"{ch}.tagged.md"
        text = io.open(path, encoding="utf-8").read()
        lines, blocks = parse_blocks(text)
        paras = {pn: lines[a] for kind, a, b, pn in blocks if kind == "para"}
        claimed_by_para, cands = {}, []
        for kind, a, b, pn in blocks:
            if kind != "para":
                continue
            s = lines[a]
            claimed = claimed_by_para.setdefault(pn, [])
            occ_counter = {}
            for it in sorted(items, key=lambda x: -len(x["surface"])):
                for raw, canon in VARIANTS.get(it["surface"], [(it["surface"], None)]):
                    for pos in plain_hits(s, raw, claimed):
                        occ = occ_counter.get(raw, 0) + 1
                        occ_counter[raw] = occ
                        claimed.append((pos, pos + len(raw)))
                        gid += 1
                        cands.append({"id": gid, "pn": pn, "surface": it["surface"],
                                      "raw": raw, "canonical": canon or it["surface"],
                                      "category": it["category"], "occ": occ,
                                      "ctx": s[max(0, pos - 14):pos + len(raw) + 14]})
        out[ch] = {"paras": paras, "cands": cands, "lines": lines, "blocks": blocks}
    return out


def apply_marks(ch, info, verdicts):
    """按裁决插标；返回 (插入数, skipped_☆, skipped_other)。逐段剥新标回读断言。"""
    lines = list(info["lines"])
    by_pn = {}
    for c in info["cands"]:
        by_pn.setdefault(c["pn"], []).append(c)
    n_ins, n_star, n_skip, n_miss = 0, 0, 0, 0
    for pn, cands in by_pn.items():
        li = next(a for kind, a, b, p in info["blocks"] if kind == "para" and p == pn)
        orig = lines[li]
        verdict = verdicts.get(pn, {})
        edits = []
        claimed = []
        # 逐候选镜像候选阶段：cand.occ 是"claimed 过滤后该原文形式的第 occ 个命中"，
        # 因此每次只取 plain_hits 的第 occ-1 个作为目标，再把目标 span 计入 claimed。
        for c in cands:
            hits = plain_hits(orig, c["raw"], claimed)
            if c["occ"] > len(hits):
                n_miss += 1
                print(f"    [warn] {ch}[{pn}] id{c['id']} 「{c['raw']}」occ{c['occ']} 定位失败")
                continue
            pos = hits[c["occ"] - 1]
            end = pos + len(c["raw"])
            claimed.append((pos, end))
            vd = verdict.get(c["id"], "skip")
            if vd == "※":
                body = c["raw"] if c["raw"] == c["canonical"] else \
                    f"{c['raw']}|{c['canonical']}"
                edits.append((pos, end, f"〘※{body}〙"))
                n_ins += 1
            elif vd == "☆":
                n_star += 1
            else:
                n_skip += 1
        new = orig
        for pos_a, pos_b, rep in sorted(edits, key=lambda x: -x[0]):
            new = new[:pos_a] + rep + new[pos_b:]
        # 精确校验：只摘除本次插入的标记（全局剥标会误伤既有 〘※〙，见 run3 教训）。
        # 2026-11-04 修：同段多处插入时，倒序回退的坐标要扣掉"更小位置已完成插入"的长度差，
        # 否则第二处会报"插入位置偏移"（020[75] 指东打西/指南打北 首例）。
        check = new
        for pos_a, pos_b, rep in sorted(edits, key=lambda x: -x[0]):
            delta = sum((len(r) - (bb - aa)) for aa, bb, r in edits if aa < pos_a)
            ix = pos_a + delta
            assert check[ix:ix + len(rep)] == rep, f"{ch}[{pn}] 插入位置偏移！"
            check = check[:ix] + orig[pos_a:pos_b] + check[ix + len(rep):]
        assert check == orig, f"{ch}[{pn}] 剥新标回读不一致！"
        lines[li] = new
    info["lines"] = lines  # 写回：main 落盘读取 info["lines"]
    if n_miss:
        print(f"    [warn] {ch} 定位失败合计 {n_miss}（不落标）")
    return n_ins, n_star, n_skip


def main():
    ap = argparse.ArgumentParser(description="修辞层 ※ 启用补标（精确匹配 + LLM 裁决）")
    ap.add_argument("--book", default=config.PILOT_BOOK, help="书名（config.books() 键）")
    ap.add_argument("--chapters", default="all", help="回号逗号列表或 all")
    ap.add_argument("--dry-run", action="store_true", help="仅候选索引，不调 API 不落盘")
    args = ap.parse_args()

    items = load_items()
    chapters = ([f"{i:03d}" for i in range(1, 20)] if args.chapters == "all"
                else [f"{int(x):03d}" for x in args.chapters.split(",")])
    index = build_candidates(chapters, items, args.book)

    total_c = sum(len(v["cands"]) for v in index.values())
    print(f"候选索引完成：{len(chapters)} 回，候选 {total_c} 处")
    for ch in chapters:
        v = index[ch]
        detail = {}
        for c in v["cands"]:
            detail[c["category"]] = detail.get(c["category"], 0) + 1
        print(f"  {ch}: {len(v['cands'])} 处 {detail}")
    if args.dry_run:
        return

    usage_log, total_ins, total_star, total_skip = [], 0, 0, 0
    per_ch = {}
    for ch in chapters:
        v = index[ch]
        if not v["cands"]:
            print(f"  {ch}: 无候选，跳过 API")
            continue
        paras_needed = sorted({c["pn"] for c in v["cands"]})
        user = ["【待裁决段落】"]
        for pn in paras_needed:
            user.append(f"[PN {pn}] {v['paras'][pn]}")
        user.append("\n【候选列表】id | PN | 原文形式 | 规范形 | category | 该形第几次出现")
        for c in v["cands"]:
            user.append(f"{c['id']} | {c['pn']} | {c['raw']} | {c['canonical']} | "
                        f"{c['category']} | #{c['occ']} | …{c['ctx']}…")
        content = call_deepseek([{"role": "system", "content": SYSTEM_PROMPT},
                                 {"role": "user", "content": "\n".join(user)}], usage_log)
        parsed = parse_verdicts(content, [c["id"] for c in v["cands"]])
        if parsed is None:
            print(f"    [warn] {ch} 返回不可解析，重试一次")
            content = call_deepseek(
                [{"role": "system", "content": SYSTEM_PROMPT},
                 {"role": "user", "content": "\n".join(user) +
                  "\n\n上一次输出无法解析为 JSON。请严格只输出一个 JSON 对象。"}], usage_log)
            parsed = parse_verdicts(content, [c["id"] for c in v["cands"]])
        if parsed is None:
            raise RuntimeError(f"{ch} 裁决 JSON 两次不可解析")
        verdict_all, missing = parsed
        if missing:
            print(f"    [warn] {ch} 缺裁决 id {missing}，按 skip 处理（宁漏勿错）")
        verdict_by_pn = {}
        for c in v["cands"]:
            verdict_by_pn.setdefault(c["pn"], {})[c["id"]] = verdict_all.get(c["id"], "skip")
        n_ins, n_star, n_skip = apply_marks(ch, v, verdict_by_pn)
        path = config.DIR_TAGGED / args.book / f"{ch}.tagged.md"
        io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(v["lines"]))
        per_ch[ch] = (n_ins, n_star, n_skip)
        total_ins += n_ins; total_star += n_star; total_skip += n_skip
        print(f"  {ch}: 插标 {n_ins}，☆报告 {n_star}，skip {n_skip} → 已写盘")

    # ---- 花费聚合 ----
    def cost_of(rec):
        p = PRICE_OFFPEAK if not rec["peak"] else {k: v * PEAK_MULT for k, v in PRICE_OFFPEAK.items()}
        hit = rec["prompt_cache_hit_tokens"]
        miss = rec["prompt_cache_miss_tokens"]
        return (hit * p["input_hit"] + miss * p["input_miss"]
                + rec["completion_tokens"] * p["output"]) / 1e6

    usd = sum(cost_of(r) for r in usage_log)
    tk_in = sum(r["prompt_tokens"] for r in usage_log)
    tk_out = sum(r["completion_tokens"] for r in usage_log)
    tk_hit = sum(r["prompt_cache_hit_tokens"] for r in usage_log)
    n_calls = len(usage_log)
    print("\n===== 执行汇总 =====")
    print(f"插标合计 {total_ins}；☆报告 {total_star}；skip {total_skip}")
    print(f"API 调用 {n_calls} 次 | 输入 {tk_in} tok（缓存命中 {tk_hit}）| 输出 {tk_out} tok")
    print(f"花费（DeepSeek 官方价，含高峰×2）：${usd:.4f}")
    logp = config.DIR_LOGS / "token_usage"
    logp.mkdir(parents=True, exist_ok=True)
    lp = logp / f"rhetoric_deepseek_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
    io.open(lp, "w", encoding="utf-8", newline="\n").write(json.dumps(
        {"task": "修辞层启用补标 〘※〙", "model": "deepseek-flash",
         "chapters": chapters, "per_chapter": per_ch,
         "inserted": total_ins, "star_reported": total_star, "skipped": total_skip,
         "usage": usage_log,
         "price_usd_per_1m": PRICE_OFFPEAK, "peak_mult": PEAK_MULT,
         "cost_usd": round(usd, 6), "tokens": {"input": tk_in, "output": tk_out,
                                               "cache_hit": tk_hit, "calls": n_calls}},
        ensure_ascii=False, indent=1) + "\n")
    print(f"用量明细已落盘: {lp}")


if __name__ == "__main__":
    main()
