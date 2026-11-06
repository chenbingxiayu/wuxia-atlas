# -*- coding: utf-8 -*-
"""C20 · 实体边界体检（武侠版 8 模式，只报告/建议 TSV，不改 tagged）。

移植自 shiji-kb/scripts/detect_entity_boundary_errors.py（只读参考，2026-11-04），
8 类模式保留、触发词与白名单全部换武侠：

  P1 实体跨动词吞入     —— 令牌内吞入「说道/喝道/问道/笑道/叫道/骂道/…」或「姓X名Y」描述句
  P2 实体后粘语气/动词   —— @ 令牌尾字粘 道/说/喝/问/了/着（"…道"=说话动词被吞）
  P3 介词误入           —— 令牌尾字粘 于/在/向/从/往/到/自 或含「在…中/向…外」介词结构
  P4 官职/身份拆分错误   —— 同实体被拆成相邻两令牌（别名+正名分裂）
  P5 单字实体边界       —— 单字令牌后接裸文可补全登记名；未挂管道的单字令牌告警
  P6 括号内标点         —— 令牌显示串（管道前）含中文标点
  P7 实体覆盖人名+称谓   —— @ 令牌把「名号 + 称谓」整体吞入（未挂管道）
  P8 回末套语误标       —— 围栏政策禁止处（回末/回末对/词/诗…）出现令牌

关键改造：
  - 符号解析统一 `symbols.TOKEN_RE/parse_token`，禁本地实体字符类；
  - 触发词表换武侠（道/说/喝/问/了/着；于/在/向/从…）；
  - WN 白名单按武侠**职衔/门派/器物/固定表达**重建：registry 正名别名 + 静态
    门派/职衔/武功器物表 + `wordlists/rhetoric.json` 固定表达 + stopwords；
    经 masker 最长匹配判断"命中片段是否被白名单覆盖"；
  - 报告按 8 类分组：计数 + 严重度（error/warning/info）+ 样例 + 定位（回:行 / PN）；
  - `--tsv` 另出 `registry/patches/<回>_boundary_fix.tsv`（人工审查用，非 C7 插入契约）；
  - `--selftest` 用合成语料 + **内置 mock registry/WN** 逐类验证检测器（hermetic：
    不读真实 registry/词表，无 registry 环境也可 8/8 PASS）；

用法：
    python scripts/detect_entity_boundary_errors.py --book 白发魔女传 --all
    python scripts/detect_entity_boundary_errors.py --book 白发魔女传 --chapter 011
    python scripts/detect_entity_boundary_errors.py --book 白发魔女传 --all --tsv
    python scripts/detect_entity_boundary_errors.py --book 白发魔女传 --all --strict
    python scripts/detect_entity_boundary_errors.py --selftest

边界：只读 tagged，不修文、不调 LLM；建议 TSV 供人工/后续修复脚本消费。
"""
from __future__ import annotations

import argparse
import bisect
import io
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config      # noqa: E402
import symbols     # noqa: E402
import masker      # noqa: E402

REGISTRY_PATH = config.DIR_REGISTRY / "entities.json"
RHETORIC_PATH = config.DIR_WORDLISTS / "rhetoric.json"
STOPWORDS_PATH = config.DIR_WORDLISTS / "stopwords.json"
LOG_DIR = config.DIR_LOGS / "boundary"
PATCH_DIR = config.DIR_REGISTRY / "patches"

PATTERN_IDS = [
    ("P1", "实体跨动词吞入"),
    ("P2", "实体后粘语气/动词"),
    ("P3", "介词误入"),
    ("P4", "官职/身份拆分错误"),
    ("P5", "单字实体边界"),
    ("P6", "括号内标点"),
    ("P7", "实体覆盖人名+称谓"),
    ("P8", "回末套语误标"),
]
PATTERN_NAME = dict(PATTERN_IDS)

# ---- 武侠触发词 ----
VERB_SWALLOW = ("说道", "喝道", "问道", "答道", "笑道", "叫道", "骂道", "怒道",
                "吼道", "沉声道", "厉声道", "朗声道", "低声道", "冷冷的道",
                "走了", "来了", "去了", "出来", "进来", "起来", "过来", "回来",
                "出去", "进去", "下去", "上来", "下来", "飞起", "跃起", "奔来",
                "冲去", "追来", "逃去", "看到", "听见")
P2_TAIL = "道说喝问了着"
P3_TAIL = "于在向从往到自"
P3_LOCATIVE = ("于上", "于中", "于下", "于内", "于外", "于前", "于后",
               "在上", "在中", "在下", "在内", "在外", "在前", "在后",
               "向上", "向下", "向前", "向后", "从中", "从上", "从下",
               "往前", "往后", "到上", "到中", "自内", "自外")
CN_PUNCT = "，。、；：！？"

# WN 白名单（武侠职衔/门派/器物/固定表达）；registry 与词表数据另行并入
WUXIA_WN = {
    # 职衔/身份/称谓
    "掌门", "掌门人", "大弟子", "帮主", "寨主", "舵主", "总舵主", "镖头", "老镖头",
    "武师", "道人", "道长", "居士", "大师", "法师", "禅师", "喇嘛", "酋长",
    "前辈", "老前辈", "女侠", "大侠", "弟子", "门人", "师父", "师娘", "师兄",
    "师弟", "师姐", "师妹", "师叔", "师伯", "侍卫", "随从", "侍从", "从犯",
    "自家人", "自己人", "一向", "老儿", "小子", "老贼", "老怪",
    # 门派/组织
    "武当派", "少林派", "峨嵋派", "华山派", "雪山派", "嵩阳派", "龙门帮", "锦衣卫",
    "东厂", "西厂", "东西厂", "铁家庄", "天龙派", "武当山", "少林寺",
    # 江湖/道路/固定说法（含"道"字，避免 P2 误报）
    "绿林道", "驿道", "穴道", "贫道", "邪魔外道", "旁门左道", "同道中人", "江湖道",
    "大道", "小道", "官道", "山道", "地道",
    # 武功/器物（含数量/动词字样的冻结名）
    "铁沙掌", "大擒拿手", "绵掌", "点穴镢", "分筋错骨", "三环套月", "八方风雨",
    "五行剑", "三绝招", "连环剑", "金针度线", "抽撒连环", "旱地拔葱", "渔夫晒网",
    "三刀六洞", "三十六式", "七十二手连环剑", "七十二手连环剑法", "武当五老",
    "西川双煞", "麦氏三雄", "方氏兄弟", "照夜狮子",
}

# P7 称谓后缀 / 前缀（人名被整体吞入的判定）
# 佛道名号构词后缀（道人/道长/禅师/法师/喇嘛/上人）不算"称谓覆盖"，单独豁免
NAME_FORMING_SUFFIXES = ("道人", "道长", "禅师", "法师", "喇嘛", "上人", "居士")
TITLE_SUFFIXES = ("大人", "公子", "先生", "前辈", "姑娘", "小姐",
                  "女侠", "大侠", "老伯", "老爷子", "老弟", "贤弟", "大哥", "师兄",
                  "师弟", "师姐", "师妹", "师父", "师叔", "师伯", "掌门", "帮主",
                  "寨主", "舵主", "武师", "镖头", "老贼", "老怪", "贼道", "小子",
                  "老儿", "夫人", "相公", "酋长")
TITLE_PREFIXES = ("大师兄", "二师兄", "三师兄", "四师兄", "大师姐", "二师姐",
                  "师父", "师叔", "师伯", "师娘")
# P1/P2/P3 适用的实体类型（人物/地点/组织/家族/族群；不含时间/数量/武功等短语型类型）
TEXT_BOUNDARY_CODES = {"@", "=", "◆", "&", "~"}

_PAREN_NOTE_RE = None


def _clean(name: str) -> str:
    """剥名称尾部括号说明（registry 的「（旧称）」等不是字面词）。"""
    global _PAREN_NOTE_RE
    if _PAREN_NOTE_RE is None:
        import re
        _PAREN_NOTE_RE = re.compile(r"[（(][^（）()]*[）)]\s*$")
    return _PAREN_NOTE_RE.sub("", (name or "").strip()).strip()


def load_wn() -> tuple[set, dict]:
    """WN = registry 正名/别名 + 武侠静态白名单 + rhetoric 固定表达 + stopwords。"""
    wn: set[str] = set(WUXIA_WN)
    sources = Counter({"static": len(WUXIA_WN)})
    if REGISTRY_PATH.exists():
        data = json.loads(io.open(REGISTRY_PATH, encoding="utf-8").read())
        n = 0
        for ent in data.get("entities", []):
            for raw in [ent.get("canonical", "")] + list(ent.get("aliases") or []):
                word = _clean(raw)
                if word:
                    wn.add(word)
                    n += 1
        sources["registry"] = n
    if RHETORIC_PATH.exists():
        data = json.loads(io.open(RHETORIC_PATH, encoding="utf-8").read())
        n = 0
        items = data if isinstance(data, list) else data.get("items", [])
        for it in items:
            word = _clean(it.get("surface", "") if isinstance(it, dict) else str(it))
            if len(word) >= 2:
                wn.add(word)
                n += 1
        sources["rhetoric"] = n
    if STOPWORDS_PATH.exists():
        data = json.loads(io.open(STOPWORDS_PATH, encoding="utf-8").read())
        n = 0
        items = data if isinstance(data, list) else data.get("items", [])
        for it in items:
            word = _clean(it.get("surface", "") if isinstance(it, dict) else str(it))
            if word:
                wn.add(word)
                n += 1
        sources["stopwords"] = n
    return wn, dict(sources)


def load_registry() -> dict:
    """registry → 正名集合、alias→canonical 映射。"""
    canon, alias2canon = set(), {}
    if not REGISTRY_PATH.exists():
        return {"canon": canon, "alias2canon": alias2canon}
    data = json.loads(io.open(REGISTRY_PATH, encoding="utf-8").read())
    for ent in data.get("entities", []):
        canonical = _clean(ent.get("canonical", ""))
        if canonical:
            canon.add(canonical)
        for raw in ent.get("aliases") or []:
            alias = _clean(raw)
            if alias and canonical:
                alias2canon.setdefault(alias, canonical)
    return {"canon": canon, "alias2canon": alias2canon}


# ---------------------------------------------------------------- 结构工具 ----
def tokenize(text: str) -> list[dict]:
    """全书/单回令牌表（symbols.parse_token，禁本地实体字符类）。"""
    out = []
    for m in symbols.TOKEN_RE.finditer(text):
        layer, code, body, disp, note, err = symbols.parse_token(m.group(0))
        out.append({"start": m.start(), "end": m.end(), "layer": layer,
                    "code": code, "body": body, "display": disp or "",
                    "canonical": note, "token": m.group(0), "parse_error": err})
    return out


def line_index(text: str) -> dict:
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    lines = text.split("\n")
    pn_by_line = {}
    cur = None
    for idx, line in enumerate(lines):
        if line.startswith("[") and "]" in line[:8]:
            try:
                cur = int(line[1:line.index("]")])
            except ValueError:
                pass
        pn_by_line[idx] = cur
    return {"starts": starts, "lines": lines, "pn_by_line": pn_by_line}


def locate(li: dict, offset: int) -> tuple[int, int | None]:
    """字符偏移 → (行号 1-based, 段号 PN)。"""
    line_idx = max(0, bisect.bisect_right(li["starts"], offset) - 1)
    return line_idx + 1, li["pn_by_line"].get(line_idx)


def fence_regions(text: str) -> list[dict]:
    """围栏区间 [start, end) 与类型（判断 P8）。"""
    regions = []
    offset = 0
    cur = None
    for line in text.split("\n"):
        start, end = offset, offset + len(line)
        m = symbols.FENCE_OPEN_RE.match(line)
        if m:
            cur = {"start": start, "end": end, "type": m.group(1)}
        elif symbols.is_fence_close(line):
            if cur:
                cur["end"] = end
                regions.append(cur)
                cur = None
        offset = end + 1
    return regions


def _context(text: str, start: int, end: int, radius: int = 16) -> str:
    return text[max(0, start - radius):min(len(text), end + radius)].replace("\n", "↵")


def _finding(pattern_id: str, severity: str, chapter: str, li: dict,
             start: int, end: int, text: str, matched: str, suggestion: str,
             token: dict | None = None) -> dict:
    line, pn = locate(li, start)
    return {"pattern_id": pattern_id, "pattern": PATTERN_NAME[pattern_id],
            "severity": severity, "chapter": chapter, "line": line, "pn": pn,
            "start": start, "matched": matched,
            "context": _context(text, start, end), "suggestion": suggestion,
            "token": token["token"] if token else matched}


# ---------------------------------------------------------------- 8 类检测 ----
def detect_chapter(chapter: str, text: str, wn_matcher, registry: dict,
                   alias2canon: dict) -> list[dict]:
    tokens = tokenize(text)
    li = line_index(text)
    fences = fence_regions(text)
    fetch = []
    wn_hits_cache: dict[str, bool] = {}

    def whitelisted(fragment: str) -> bool:
        if fragment not in wn_hits_cache:
            wn_hits_cache[fragment] = bool(masker.find_candidates(fragment, wn_matcher))
        return wn_hits_cache[fragment]

    # P1 实体跨动词吞入
    for t in tokens:
        if t["layer"] != "entity" or t["code"] not in TEXT_BOUNDARY_CODES:
            continue
        disp = t["display"]
        hit = next((p for p in VERB_SWALLOW if p in disp), None)
        if hit and not whitelisted(disp):
            fetch.append(_finding("P1", "error", chapter, li, t["start"], t["end"], text,
                                  t["token"], "拆出动词成分，实体名单独成令牌", t))
        elif disp.startswith("姓") and "名" in disp[1:] and t["canonical"] is None:
            fetch.append(_finding("P1", "error", chapter, li, t["start"], t["end"], text,
                                  t["token"], "「姓X名Y」是叙述句，改为姓名令牌或只标姓名", t))

    # P2 实体后粘语气/动词（@ 尾字粘连道/说/喝/问/了/着）
    for t in tokens:
        if t["layer"] != "entity" or t["code"] != "@":
            continue
        disp = t["display"]
        if len(disp) >= 2 and disp[-1] in P2_TAIL and not whitelisted(disp) \
                and disp not in registry["canon"]:
            fetch.append(_finding("P2", "error", chapter, li, t["start"], t["end"], text,
                                  t["token"], "把句末动词/语气词/称谓移出令牌，只保留人名", t))

    # P3 介词误入
    for t in tokens:
        if t["layer"] != "entity" or t["code"] not in TEXT_BOUNDARY_CODES:
            continue
        disp = t["display"]
        if len(disp) < 2:
            continue
        if disp[-1] in P3_TAIL or any(p in disp for p in P3_LOCATIVE):
            if disp.startswith("于"):        # 「于」可为姓氏（于孔谦），不作介词误判
                continue
            if not whitelisted(disp):
                fetch.append(_finding("P3", "warning", chapter, li, t["start"], t["end"],
                                      text, t["token"], "介词移出令牌，只保留实体名", t))

    # P4 官职/身份拆分错误（同实体被拆成相邻令牌 / 相邻同码拼接成登记名）
    for a, b in zip(tokens, tokens[1:]):
        if b["start"] != a["end"] or a["layer"] != "entity" or b["layer"] != "entity":
            continue
        a_disp, b_disp = a["display"], b["display"]
        is_split = bool(alias2canon.get(a_disp) == b_disp or alias2canon.get(b_disp) == a_disp)
        concat = a_disp + b_disp
        is_split = is_split or concat in registry["canon"] or bool(alias2canon.get(concat))
        if is_split and a["code"] == b["code"]:
            fetch.append(_finding("P4", "error", chapter, li, a["start"], b["end"], text,
                                  a["token"] + b["token"],
                                  "合并为单令牌（显示串|规范名）或拆成不同实体", a))

    # P5 单字实体边界（人物单字：查姓氏/名字被切开的边界；其他类型的单字是常态）
    for t in tokens:
        if t["layer"] != "entity" or t["code"] != "@" or len(t["display"]) != 1:
            continue
        completion = None
        for span in (1, 2):
            nxt = text[t["end"]:t["end"] + span]
            if "\n" in nxt or not nxt:
                continue
            if t["display"] + nxt in registry["canon"]:
                completion = t["display"] + nxt
                break
        if completion:
            fetch.append(_finding("P5", "error", chapter, li, t["start"], t["end"], text,
                                  t["token"] + completion[len(t["display"]):],
                                  f"补全为登记名「{completion}」后标注", t))
        elif t["canonical"] is None:
            fetch.append(_finding("P5", "warning", chapter, li, t["start"], t["end"], text,
                                  t["token"],
                                  "单字令牌无管道/无全名证据：确认是否单字即规范名，否则挂管道", t))

    # P6 括号内标点（只看显示串，管道后的消歧说明不算）
    for t in tokens:
        disp = t["display"]
        if any(p in disp for p in CN_PUNCT):
            severity = "info" if t["layer"] == "rhetoric" else "error"
            fetch.append(_finding("P6", severity, chapter, li, t["start"], t["end"], text,
                                  t["token"], "标点外置/按标点切分令牌（固定表达除外）", t))

    # P7 实体覆盖人名+称谓（未挂管道）
    #   「道人/道长」是道号构词（紫阳道长/白石道人），按 01g 佛道名号规则不算称谓覆盖 → 豁免
    for t in tokens:
        if t["layer"] != "entity" or t["code"] != "@" or t["canonical"] is not None:
            continue
        disp = t["display"]
        if disp in registry["canon"] or len(disp) < 3:
            continue
        suffix = next((s for s in TITLE_SUFFIXES
                       if s not in NAME_FORMING_SUFFIXES and disp.endswith(s)
                       and len(disp) > len(s)), None)
        prefix = next((p for p in TITLE_PREFIXES if disp.startswith(p) and len(disp) > len(p)), None)
        if suffix or prefix:
            rest = disp[:-len(suffix)] if suffix else disp[len(prefix):]
            if len(rest) >= 2:
                fetch.append(_finding("P7", "warning", chapter, li, t["start"], t["end"],
                                      text, t["token"],
                                      "称谓移出令牌：『名〗+称谓」或名+称谓挂管道", t))

    # P8 回末套语/围栏政策误标
    def fence_of(offset: int):
        for region in fences:
            if region["start"] <= offset < region["end"]:
                return region
        return None

    set_phrase = ("欲知后事如何", "请听下回分解", "且听下回分解", "正是：")
    for t in tokens:
        region = fence_of(t["start"])
        if region:
            ftype = region["type"]
            if ftype == "回末":
                fetch.append(_finding("P8", "error", chapter, li, t["start"], t["end"], text,
                                      t["token"], "回末围栏全不标：删除令牌", t))
            elif symbols.FENCE_ENTITY_POLICY.get(ftype) == "real_only":
                severity = "warning" if t["layer"] == "verb" else "info"
                fetch.append(_finding("P8", severity, chapter, li, t["start"], t["end"], text,
                                      t["token"],
                                      f"{ftype}围栏仅实指可标；非实指删除/动词不标", t))
            elif symbols.FENCE_ENTITY_POLICY.get(ftype) == "tech_only":
                severity = "warning" if t["layer"] == "entity" and t["code"] != "☆" else "error"
                fetch.append(_finding("P8", severity, chapter, li, t["start"], t["end"], text,
                                      t["token"], f"{ftype}围栏仅技术名可标", t))
            elif t["layer"] == "verb":
                fetch.append(_finding("P8", "warning", chapter, li, t["start"], t["end"], text,
                                      t["token"], f"{ftype}围栏动词不标", t))
        else:
            line = li["lines"][locate(li, t["start"])[0] - 1]
            if any(p in line for p in set_phrase) and len(line) <= 30:
                fetch.append(_finding("P8", "warning", chapter, li, t["start"], t["end"], text,
                                      t["token"], "回末套语行不应标注（套语全不标）", t))
    fetch.sort(key=lambda f: (f["start"], f["pattern_id"]))
    return fetch


# ---------------------------------------------------------------- 报告/输出 ----
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def write_tsv(out_dir: Path, findings: list[dict]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_chapter: dict[str, list] = defaultdict(list)
    for f in findings:
        by_chapter[f["chapter"]].append(f)
    paths = []
    for chapter, items in sorted(by_chapter.items()):
        path = out_dir / f"{chapter}_boundary_fix.tsv"
        lines = ["章节\t行号\t段号\t模式\t严重度\t匹配文本\t上下文\t建议"]
        for f in items:
            lines.append("\t".join([
                f["chapter"], str(f["line"]), str(f["pn"] or ""), f["pattern"],
                f["severity"], f["matched"], f["context"], f["suggestion"],
            ]))
        io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
        paths.append(path)
    return paths


def write_report(book: str, chapters: list[int], params: dict, findings: list[dict],
                 wn_sources: dict, selftest_table: str = "") -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 子集扫描不覆盖全书报告（2026-11-04 Lead 修复）
    suffix = "" if params.get("chapter") in (None, "all") else \
        "_" + str(params["chapter"]).replace(",", "-").replace(" ", "")
    label = f"{book}{suffix}"
    by_pattern = defaultdict(list)
    for f in findings:
        by_pattern[f["pattern_id"]].append(f)
    total = len(findings)
    sev = Counter(f["severity"] for f in findings)
    lines = [
        f"# C20 实体边界体检报告 — {book}",
        "",
        f"- 生成时间：{stamp}",
        f"- 语料：`tagged/{book}/` 扫描 {len(chapters)} 回 / 全书 {params.get('total_chapters', len(chapters))} 回",
        f"- 参数：{json.dumps(params, ensure_ascii=False)}",
        f"- WN 白名单来源：{json.dumps(wn_sources, ensure_ascii=False)}（registry+武侠静态+固定表达+泛称）",
        "- 写入范围：本报告 + 同名 JSON"
        + (" + 建议 TSV" if params.get("tsv") else "")
        + "；tagged 未改动",
        "",
        "## 一、总览（8 类计数）",
        "",
        "| 模式 | 名称 | 计数 | error | warning | info |",
        "|---|---|---|---|---|---|",
    ]
    for pid, name in PATTERN_IDS:
        items = by_pattern.get(pid, [])
        counts = Counter(f["severity"] for f in items)
        lines.append(f"| {pid} | {name} | {len(items)} | {counts.get('error', 0)} | "
                     f"{counts.get('warning', 0)} | {counts.get('info', 0)} |")
    lines += [
        f"| **合计** | — | **{total}** | {sev.get('error', 0)} | "
        f"{sev.get('warning', 0)} | {sev.get('info', 0)} |",
        "",
        "## 二、逐类明细（每类样例最多 8 条）",
        "",
    ]
    for pid, name in PATTERN_IDS:
        items = sorted(by_pattern.get(pid, []),
                       key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["chapter"],
                                      f["line"]))
        lines.append(f"### {pid} {name} — {len(items)} 条")
        lines.append("")
        if not items:
            lines.append("本轮语料未命中（规则已实现，可由 `--selftest` 证明可触发）。")
            lines.append("")
            continue
        for f in items[:8]:
            loc = f"{f['chapter']}:{f['line']}" + (f"（PN [{f['pn']}]）" if f["pn"] else "")
            lines.append(f"- `{loc}` [{f['severity']}] `{f['matched']}` …{f['context']}…")
            lines.append(f"  - 建议：{f['suggestion']}")
        if len(items) > 8:
            lines.append(f"- …另有 {len(items) - 8} 条，见 TSV/JSON。")
        lines.append("")
    lines += [
        "## 三、检测规则说明（武侠版触发词）",
        "",
        "- P1：动词吞入触发词 = " + "、".join(VERB_SWALLOW[:16]) + " 等，及未挂管道的「姓X名Y」叙述句；",
        "- P2：@ 令牌尾字 ∈ `" + P2_TAIL + "`；",
        "- P3：令牌尾字 ∈ `" + P3_TAIL + "` 或含「在…中/向…外」等介词结构（「于」开头视为姓氏豁免）；",
        "- P4：相邻同码令牌中，一个显示串是另一者 canonical/alias，或拼接后命中 registry 名；",
        "- P5：人物单字令牌 + 后接裸文补全 registry 名 = error；单字无管道 = warning；",
        "- P6：令牌显示串（管道前）含 `" + CN_PUNCT + "`；修辞层固定表达计 info；",
        "- P7：@ 令牌未挂管道且 = 名号 + 称谓后缀（或称谓前缀 + 名）；"
        "佛道名号构词（道人/道长/禅师/法师/喇嘛/居士）豁免；",
        "- P8：按 symbols.FENCE_ENTITY_POLICY：回末=全不标；词/诗/歌/对联/回末对=仅实指；"
        "口诀=仅技术名；其他围栏动词不标；另查回末套语行。",
        "",
        "## 四、正例/边界说明（避免误报）",
        "",
        "- 已挂管道的描述性显示串（如 `〖@姓岳的小子|岳鸣珂〗`）按 01g 允许，不计 P1/P7；",
        "- 登记名本身含「道/人」等字样（紫阳道长/白石道人）不计 P2/P7；",
        "- 门派/职衔/道路/武功冻结名（武当派/驿道/穴道/铁沙掌）由 WN 白名单整体豁免；",
        "- 量词/时间/武功等短语型类型（$%☆•）不参与 P1/P2/P3，避免把合法短语标为边界错误。",
        "",
    ]
    if selftest_table:
        lines += ["## 五、检测器自检（--selftest，内置 mock registry/WN，hermetic）",
                  "", selftest_table, ""]
    path = LOG_DIR / f"{label}.md"
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    payload = {
        "book": book, "generated": stamp, "params": params, "wn_sources": wn_sources,
        "summary": {"total": total, "by_severity": dict(sev),
                    "by_pattern": {pid: len(by_pattern.get(pid, [])) for pid, _ in PATTERN_IDS}},
        "selftest": selftest_table,
        "findings": findings,
    }
    io.open(LOG_DIR / f"{label}.json", "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    return path


# ---------------------------------------------------------------- 自检 ----
# 2026-11-05 P2-B：selftest 改为 **hermetic** —— 内置 mock registry/WN，
# 不读真实 registry/entities.json、rhetoric.json、stopwords.json；
# 主流程（--chapter/--all）仍使用真实 load_wn()/load_registry()。
MOCK_REGISTRY = {
    "canon": {"卓仲廉", "练霓裳"},
    "alias2canon": {"玉罗刹": "练霓裳"},
}
MOCK_WN = set(WUXIA_WN) | set(MOCK_REGISTRY["canon"]) | set(MOCK_REGISTRY["alias2canon"])

SELFTEST_TEXT = """# [0] 测试回
[1] 〖@张三说道〗一句话。
[2] 〖@李四道〗又一句。
[3] 〖@王五在〗再一句。
[4] 〖@玉罗刹〗〖@练霓裳〗并肩而来。
[5] 却说〖@卓〗仲廉到了。
[6] 收入〖=京城，〗之中。
[7] 〖@青蓑师叔〗与〖@新城师兄〗。
::: 回末对
[8] 正是：〖=沙漠〗孤烟直。
:::
"""
# 说明：P4 依赖 MOCK_REGISTRY 中「玉罗刹=练霓裳」；P5 依赖 mock canon「卓仲廉」。


def selftest() -> tuple[bool, str]:
    """内置 mock registry/WN 逐类自检；不读真实 registry（hermetic，2026-11-05 P2-B）。"""
    registry = MOCK_REGISTRY
    wn_matcher = masker.build_matcher(MOCK_WN)
    findings = detect_chapter("000", SELFTEST_TEXT, wn_matcher, registry,
                              registry["alias2canon"])
    got = Counter(f["pattern_id"] for f in findings)
    lines = ["| 模式 | 合成语料命中 | 判定 |", "|---|---|---|"]
    ok = True
    for pid, name in PATTERN_IDS:
        hit = got.get(pid, 0) > 0
        ok = ok and hit
        lines.append(f"| {pid} | {got.get(pid, 0)} | {'PASS' if hit else '**FAIL**'} |")
    lines.append("")
    lines.append("（内置 mock registry：canon={卓仲廉,练霓裳}、"
                 "alias2canon={玉罗刹→练霓裳}；WN=WUXIA_WN+mock 名，不读真实 registry/词表）")
    return ok, "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="C20 实体边界体检（8 模式，只读 tagged）")
    ap.add_argument("--book", default=config.PILOT_BOOK)
    group = ap.add_mutually_exclusive_group(required=False)
    group.add_argument("--chapter", help="单回（如 011）")
    group.add_argument("--all", action="store_true", help="全书")
    ap.add_argument("--out", default=str(LOG_DIR), help=f"报告目录（默认 {LOG_DIR}）")
    ap.add_argument("--tsv", action="store_true", help="另出 registry/patches/<回>_boundary_fix.tsv")
    ap.add_argument("--strict", action="store_true", help="存在 error 级问题时 exit 1")
    ap.add_argument("--selftest", action="store_true", help="用合成语料验证 8 类检测器")
    args = ap.parse_args()

    if args.selftest:
        ok, table = selftest()            # hermetic：内置 mock registry/WN，不读真实文件
        print(table)
        print("SELFTEST", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    wn, wn_sources = load_wn()
    wn_matcher = masker.build_matcher(wn)
    registry = load_registry()

    if not args.chapter and not args.all:
        ap.error("需指定 --chapter 或 --all（或 --selftest）")
    all_chapters = [int(p.name.split(".")[0]) for p in
                    sorted(config.DIR_TAGGED.joinpath(args.book).glob("*.tagged.md"))
                    if p.name.split(".")[0].isdigit()]
    if not all_chapters:
        raise SystemExit(f"[ERROR] 未找到 {args.book} 的 tagged 回目")
    chapters = [int(args.chapter)] if args.chapter else all_chapters
    params = {"book": args.book, "chapter": args.chapter or "all", "tsv": args.tsv,
              "strict": args.strict, "total_chapters": len(all_chapters)}

    findings = []
    for ch in chapters:
        fpath = config.tagged_path(args.book, ch)
        if not fpath.exists():
            print(f"  [WARN] 缺 {ch:03d}.tagged.md")
            continue
        text = io.open(fpath, encoding="utf-8").read()
        items = detect_chapter(f"{ch:03d}", text, wn_matcher, registry,
                               registry["alias2canon"])
        findings.extend(items)
        if items:
            c = Counter(f["pattern_id"] for f in items)
            print(f"  {ch:03d}: {len(items):3d} 条 → " + " ".join(
                f"{k}×{v}" for k, v in sorted(c.items())))
        else:
            print(f"  {ch:03d}: 0")

    patch_dir = config.patches_dir(args.book)
    patch_dir.mkdir(parents=True, exist_ok=True)
    tsv_paths = write_tsv(patch_dir, findings) if args.tsv else []
    st_ok, st_table = selftest()          # hermetic：报告里的自检也不读真实 registry
    report_path = write_report(args.book, chapters, params, findings, wn_sources,
                               st_table + ("\n\nSELFTEST: PASS" if st_ok else "\n\nSELFTEST: FAIL"))
    sev = Counter(f["severity"] for f in findings)
    print(f"\n合计 {len(findings)} 条（error {sev.get('error', 0)} / "
          f"warning {sev.get('warning', 0)} / info {sev.get('info', 0)}）；报告：{report_path}")
    if tsv_paths:
        print(f"建议 TSV：{len(tsv_paths)} 个 → {PATCH_DIR}")
    if args.strict and sev.get("error", 0) > 0:
        print("[STRICT] 存在 error 级边界问题 → exit 1")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
