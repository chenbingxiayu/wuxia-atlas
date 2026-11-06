# -*- coding: utf-8 -*-
"""EX-1 · books.json + chapters.json 导出器（docs/51 §三 EX-1 / §五 契约 / §七 验收）。

桥接层定位：新管线（config + 章回版 + tagged + registry/concordance）为唯一真源；
旧站点消费层冻结，本脚本把新产物按 2026-11-02 `site/data/` 旧契约导出，
保证 Astro 38 页零改动。默认 dry-run（只写 logs/export/staging + reports）；
`--apply` 由 export_site_common.finish 自动备份后写 site/data（本阶段验收只用 dry-run）。

导出内容：
  - books.json     ：34 部作品索引（旧结构 meta + missing_works + books）
  - chapters.json  ：34 部逐回回目；tagged 存在的"已点亮"书（当前 5 部）附
                     逐章出场人物 / 动词密度 / 叙事事件流（A—动词—B 邻近对）+ kb 统计

数据源（全部只读）：
  - scripts/config.py                   路径与书目唯一来源（章回版 34 部）
  - ../章回版/<书>/*.txt                回目、回数、字数（旧站同口径）
  - ../kb/作品元数据表.json              year/era/series/leads/kb_status 等考订元数据
  - ../kb/互文引用表.json                authorial/quoted 互文边（旧逻辑照搬）
  - tagged/<书>/*.tagged.md             逐段 〖实体〗/⟦动词域⟧ 令牌
  - registry/concordance/<书>.json      逐章人物出现计数（tagged 的登记层聚合）
  - registry/entities.json              跨书规范名/别名（唯一别名映射，避免人物页断链）

字段口径（docs/51 §五 契约纪律）：
  - 旧站字段集合"不缺、类型不破"是硬条件；新数据暂缺项置 0/空数组并在
    meta.field_gaps 显式声明，不静默丢字段。
  - 已点亮口径：tagged/<书>/*.tagged.md 存在（当前 5 部，旧站为 3 部）。
  - 计数口径与旧站差异（字数/事件数等）写入 meta.notes，供差异报告追溯。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import config                     # scripts/config.py：路径唯一来源
import export_site_common as esc  # EX 导出层公共设施（contracts/staging/reports）
import symbols                    # scripts/symbols.py：标注令牌唯一解析入口

# ---------------------------------------------------------------- 路径 / 常量
CORPUS = config.CORPUS_ROOT                  # ../章回版（只读底本）
LEGACY_KB = config.LEGACY_KB                 # ../kb（只读旧资产）
TAGGED = config.DIR_TAGGED                   # wuxia-kb/tagged（新管线产物）
REGISTRY = config.DIR_REGISTRY               # wuxia-kb/registry（新管线产物）

SCHEMA_BOOKS = "site-books-v1"               # 沿用旧站 meta.schema
SCHEMA_CHAPTERS = "chapters-v1"
SOURCE = "wuxia-kb 新管线 + kb 只读资产（桥接层 EX-1）"
EXPORTER = "EX-1 export_site_books_chapters"

FULL_SPACE = "\u3000"
PARAGRAPH_RE = re.compile(r"^\[(\d+)\]\s*(.*)$")      # 结构层段号 [N]；标题行是 "# [0]"
WHITESPACE_RE = re.compile(r"\s")
SENTENCE_END = set("。！？；…")
QUOTE_OPEN = set("“‘「『")
QUOTE_CLOSE = set("”’」』")

# 旧站事件流把 5 类角色实体当作 A/B 两侧（人物/群组/组织/家族）
ACTOR_TYPES = {"@", "◎", "◆", "&"}

# 旧站动词密度五码（Sparkbars 消费）← 新管线六域映射；▲（擒控）新域无对应，恒 0
VERB_OLD_CODES = ("◈", "◉", "▲", "◇", "○")
VERB_OLD_TO_NEW = {"◈": "⊞", "◉": "⊠", "▲": None, "◇": "▣", "○": "⊡"}
VERB_DOMAINS = ("⊞", "⊠", "⊡", "⊟", "▣", "■")   # 新六域原值同 dict 附出

TOP_CHARS = 30          # 旧站逐章出场人物 Top 30
CONF_HIGH_GAP = 20      # 主语与动词的字符距离阈值 → 启发式置信（宾语侧另受邻近规则约束）
CONF_MED_GAP = 40
LOC_CHAPTER_WIDTH = 3   # 定位符 "001:27" 的章号宽度（旧站同格式）

# 事件流配对规则（A—动词—B 邻近对，见 analyze_paragraph）：
#   宾语须紧跟动词：间隔 ≤ OBJECT_GAP_MAX 且只能是虚词/趋向补语；
#   主宾不得为同一实体（避免"卓一航…⟦v⟧…卓一航"式自指假配对）。
OBJECT_GAP_MAX = 4
OBJECT_GAP_ALLOWED = set("了着在向给过出到和与至入往自被把对于得地成为一之其并再又便就都也还已将")


# ---------------------------------------------------------------- 基础 IO
def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def canon_name(name: str, canon_map: dict) -> str:
    """跨书同人异名 → registry 规范名（仅唯一别名映射，冲突项不动）。"""
    return canon_map.get(name, name)


def entity_name(body: str) -> str:
    """〖@显示|规范〗 → 规范名（管道右侧）；无管道取显示串。"""
    rest = body[1:]
    return (rest.split("|", 1)[1] if "|" in rest else rest).strip()


def trigger_word(body: str) -> str:
    """⟦⊞动词|消歧说明⟧ → 触发词（管道左侧）。"""
    return body[1:].split("|", 1)[0].strip()


# ---------------------------------------------------------------- 章回版底本
def discover_corpus() -> dict:
    """章回版 → {书名: [{no, title}]}（旧站 chapter_meta 同口径）。

    - 回目/回号取自文件名：`NNN　标题.txt`，no=前 3 位，title=全角空格后的余部；
    - 含 6 部书的楔子（000）；狂侠天骄魔女/鸣镝风云录的 `第一○○回` 式回号也照收；
    - config.CHAPTER_FILE_RE 会漏计这 28 回，故本导出器以文件枚举为准（见 meta.notes）。
    """
    corpus: dict = {}
    if not CORPUS.exists():
        return corpus
    for d in sorted(p for p in CORPUS.iterdir() if p.is_dir()):
        items = []
        for fp in sorted(d.glob("*.txt")):
            try:
                no = int(fp.name[:3])
            except ValueError:
                continue
            parts = fp.stem.split(FULL_SPACE)
            title = FULL_SPACE.join(parts[1:]) if len(parts) > 1 else fp.stem
            items.append({"no": no, "title": title})
        if items:
            corpus[d.name] = items
    return corpus


def corpus_char_count(book: str) -> int:
    """本书非空白字符数（旧站 books[].chars 同口径"字"）。"""
    total = 0
    for fp in sorted((CORPUS / book).glob("*.txt")):
        total += len(WHITESPACE_RE.sub("", fp.read_text(encoding="utf-8")))
    return total


def tagged_chapters(book: str) -> int:
    d = TAGGED / book
    if not d.is_dir():
        return 0
    return len(list(d.glob("*.tagged.md")))


def lit_books(corpus: dict) -> list:
    """已点亮书 = 新管线 tagged 存在者（当前 5 部；旧站 kb/ 时代为 3 部）。"""
    return sorted(b for b in corpus if tagged_chapters(b) > 0)


# ---------------------------------------------------------------- 旧 kb 只读资产
def load_legacy_metadata() -> dict:
    """作品元数据表 + 互文引用表（只读；旧站 build_site_data.build_books 同源）。"""
    wmeta = read_json(LEGACY_KB / "作品元数据表.json")
    inter = read_json(LEGACY_KB / "互文引用表.json")
    return {"wmeta": wmeta, "inter": inter}


def intertext_index(edges: list) -> tuple:
    """互文边按旧逻辑索引：只取 authorial/quoted，按 源→目标 / 目标→源 分组。

    旧站 build_site_data.build_books():
      out_edges[e['source']][e['target']].append(e)
      in_edges[e['target']][e['source']].append(e)
    """
    out_edges: dict = defaultdict(lambda: defaultdict(list))
    in_edges: dict = defaultdict(lambda: defaultdict(list))
    for e in edges:
        if e.get("kind") not in ("authorial", "quoted"):
            continue
        out_edges[e["source"]][e["target"]].append(e)
        in_edges[e["target"]][e["source"]].append(e)
    return out_edges, in_edges


def pack_refs(edges_by_book: dict, book: str) -> list:
    """互文明细打包（旧站 pack() 逐字段照搬，含排序/locs/sample 截断口径）。"""
    items = []
    for tgt, es in sorted(edges_by_book.get(book, {}).items(), key=lambda kv: -len(kv[1])):
        items.append({
            "book": tgt,
            "kind": es[0]["kind"],
            "count": len(es),
            "locs": [f"{es[0]['source']}·{e['loc']}" for e in es[:5]],
            "sample": es[0]["snippet"][:60],
        })
    return items


def load_registry_canon() -> dict:
    """registry/entities.json → {别名: 规范名}，仅收录唯一映射。

    - 同一别名指向多个规范名（如"平南王"→吴三桂/尚之信/尚可喜）时跳过，避免误归并；
    - 别名本身已是某实体规范名时不改（防链式误映射）。
    用于把 concordance 书内规范名归一为跨书 registry 规范名（旧站 BOOK_CANON 的升级版）。
    """
    path = REGISTRY / "entities.json"
    if not path.exists():
        return {}
    reg = read_json(path)
    canon_set = {e["canonical"] for e in reg.get("entities") or []}
    alias_to: dict = defaultdict(set)
    for e in reg.get("entities") or []:
        for a in e.get("aliases") or []:
            alias_to[a].add(e["canonical"])
    return {a: next(iter(v)) for a, v in alias_to.items()
            if len(v) == 1 and a not in canon_set}


_CONCORDANCE_CACHE: dict = {}


def load_concordance(book: str) -> dict | None:
    if book not in _CONCORDANCE_CACHE:
        p = REGISTRY / "concordance" / f"{book}.json"
        _CONCORDANCE_CACHE[book] = read_json(p) if p.exists() else None
    return _CONCORDANCE_CACHE[book]


def chapter_person_counts(book: str, canon_map: dict) -> dict:
    """concordance → {回号: Counter(规范名→出现次数)}（人物 @ 类，跨书别名归并后合并）。"""
    conc = load_concordance(book)
    per: dict = defaultdict(Counter)
    if not conc:
        return per
    for ent in conc.get("entities") or []:
        if ent.get("type") != "@":
            continue
        name = canon_name(ent.get("canonical") or "", canon_map)
        if not name:
            continue
        for cc in ent.get("chapter_counts") or []:
            try:
                no = int(cc.get("chapter") or 0)
                cnt = int(cc.get("count") or 0)
            except (TypeError, ValueError):
                continue
            per[no][name] += cnt
    return per


# ---------------------------------------------------------------- tagged 解析
def _quote_depth(text: str) -> list:
    """逐字符累计中文引号深度：用于剔除对话内事件（旧站 in_quote 口径）。"""
    depth = [0] * len(text)
    d = 0
    for i, ch in enumerate(text):
        depth[i] = d
        if ch in QUOTE_OPEN:
            d += 1
        elif ch in QUOTE_CLOSE:
            d = max(0, d - 1)
    return depth


def _sentence_bounds(text: str) -> tuple:
    bounds = [0]
    for i, ch in enumerate(text):
        if ch in SENTENCE_END:
            bounds.append(i + 1)
    bounds.append(len(text) + 1)
    return bounds


def analyze_paragraph(text: str, chapter_no: int, para_no: int, canon_map: dict):
    """单段 → (动词域计数 Counter, 叙事动词数, 事件流 list)。

    - 动词密度：全部 ⟦⟧ 令牌按六域计数（含对话内，旧站 verbs 口径）；
    - 叙事事件数：非对话内的 ⟦⟧ 令牌数（旧站 events_narrative 口径）；
    - 事件流：同句内 A—⟦动词⟧—B 邻近对。A=动词前最近角色实体；B=动词后、
      同句内紧邻动词的角色实体（间隔 ≤ OBJECT_GAP_MAX 且仅虚词/趋向补语）；
      主宾同一实体不配对。置信 c 按主语与动词距离启发式分档
      （新管线事件层 N4/D03 未产出，无人工校订置信，具体口径见 meta.field_gaps）。
    """
    verbs: Counter = Counter()
    stream: list = []
    actors: list = []     # (字符位置, 规范名)
    vtoks: list = []      # (起, 止, 域名, 触发词, 是否对话内)
    qdepth = _quote_depth(text)
    for m in symbols.TOKEN_RE.finditer(text):
        kind, code, body, _disp, _canon, err = symbols.parse_token(m.group(0))
        if err:
            continue
        if kind == "entity" and code in ACTOR_TYPES:
            name = canon_name(entity_name(body), canon_map)
            if name:
                actors.append((m.start(), name))
        elif kind == "verb" and code in symbols.VERB_CODES:
            vtoks.append((m.start(), m.end(), code, trigger_word(body),
                          qdepth[m.start()] > 0 if m.start() < len(qdepth) else False))
    narrative = 0
    bounds = _sentence_bounds(text)
    if actors and vtoks:
        for vs, ve, code, word, in_quote in vtoks:
            verbs[code] += 1
            if in_quote:
                continue
            narrative += 1
            # 所在句界
            a, b = bounds[0], bounds[-1]
            for s0, s1 in zip(bounds, bounds[1:]):
                if s0 <= vs < s1:
                    a, b = s0, s1
                    break
            subj = None
            for pos, name in actors:
                if a <= pos < vs:
                    subj = (pos, name)
            obj = None
            for pos, name in actors:
                if ve <= pos < b:
                    obj = (pos, name)
                    break
            if not (subj and obj) or subj[1] == obj[1]:
                continue
            gap_o = text[ve:obj[0]]
            if len(gap_o) > OBJECT_GAP_MAX or any(ch not in OBJECT_GAP_ALLOWED for ch in gap_o):
                continue
            gap_s = vs - subj[0]
            conf = ("high" if gap_s <= CONF_HIGH_GAP
                    else "medium" if gap_s <= CONF_MED_GAP else "low")
            item = {
                "s": subj[1], "v": word, "o": obj[1],
                "loc": f"{chapter_no:0{LOC_CHAPTER_WIDTH}d}:{para_no}",
                "c": conf,
            }
            if item not in stream:      # 同段同 A—V—B 去重
                stream.append(item)
    else:
        narrative = sum(1 for v in vtoks if not v[4])
        for _vs, _ve, code, _word, _q in vtoks:
            verbs[code] += 1
    return verbs, narrative, stream


def parse_tagged_chapter(path: Path, chapter_no: int, canon_map: dict):
    """整回 tagged 文件 → (动词域 Counter, 叙事动词数, 事件流 list)。围栏内不抽事件。"""
    verbs: Counter = Counter()
    narrative = 0
    stream: list = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if in_fence:
            if line.strip() == ":::":
                in_fence = False
            continue
        if line.startswith(":::"):
            in_fence = True
            continue
        m = PARAGRAPH_RE.match(line)
        if not m:
            continue
        no = int(m.group(1))
        if no == 0:          # [0] 回目标题不是正文段
            continue
        v, n, s = analyze_paragraph(m.group(2), chapter_no, no, canon_map)
        verbs.update(v)
        narrative += n
        stream.extend(s)
    return verbs, narrative, stream


# ---------------------------------------------------------------- books.json
def build_books(corpus: dict, char_counts: dict) -> tuple:
    """books.json payload + 口径统计（返回 payload, stats 供 reports/notes 用）。"""
    legacy = load_legacy_metadata()
    wmeta, inter = legacy["wmeta"], legacy["inter"]
    out_edges, in_edges = intertext_index(inter.get("edges") or [])
    lit = set(lit_books(corpus))

    books = []
    for w in wmeta.get("works") or []:
        book = w["book"]
        books.append({
            "no": w.get("no"),
            "book": book,
            "year": w.get("year"),
            "year_conf": w.get("year_conf") or "",
            "era": w.get("era") or "",
            "era_conf": w.get("era_conf") or "",
            "series": w.get("series") or "",
            "series_conf": w.get("series_conf") or "",
            "leads": list(w.get("leads") or []),
            "leads_conf": w.get("leads_conf") or "",
            "chapters": len(corpus.get(book) or []),
            "chars": char_counts.get(book, w.get("chars") or 0),
            # 新 tagged 存在 → 已点亮；否则沿用旧元数据表口径（待建/标注中 fallback）
            "kb_status": "已点亮" if book in lit else (w.get("kb_status") or "待建"),
            "intertext_out": sum(len(v) for v in out_edges.get(book, {}).values()),
            "intertext_in": sum(len(v) for v in in_edges.get(book, {}).values()),
            "out_refs": pack_refs(out_edges, book),
            "in_refs": pack_refs(in_edges, book),
        })

    # 兜底：底本新增但元数据表未收录的书（当前 0 部），仍按契约结构补位并记 field_gaps
    known = {w["book"] for w in wmeta.get("works") or []}
    extra_books = []
    for i, book in enumerate(sorted(set(corpus) - known), start=len(books) + 1):
        extra_books.append(book)
        books.append({
            "no": i, "book": book, "year": None, "year_conf": "missing",
            "era": "", "era_conf": "todo", "series": "", "series_conf": "todo",
            "leads": [], "leads_conf": "todo",
            "chapters": len(corpus.get(book) or []),
            "chars": char_counts.get(book, 0),
            "kb_status": "已点亮" if book in lit else "待建",
            "intertext_out": sum(len(v) for v in out_edges.get(book, {}).values()),
            "intertext_in": sum(len(v) for v in in_edges.get(book, {}).values()),
            "out_refs": pack_refs(out_edges, book),
            "in_refs": pack_refs(in_edges, book),
        })

    totals = {
        "books": len(books),
        "chapters": sum(int(b.get("chapters") or 0) for b in books),
        "chars": sum(int(b.get("chars") or 0) for b in books),
    }
    snapshot = _snapshot_block(corpus, sorted(lit), legacy)
    payload = {
        "meta": {
            "generated": esc.today(),
            "schema": SCHEMA_BOOKS,
            "totals": totals,
            "source": SOURCE,
            "field_gaps": _books_field_gaps(legacy, extra_books),
            "notes": _books_meta_notes(totals, sorted(lit), char_counts, legacy, extra_books),
            "snapshot": snapshot,
        },
        "missing_works": legacy["wmeta"].get("missing_works") or [],
        "books": books,
    }
    stats = {
        "legacy": legacy,
        "lit": sorted(lit),
        "extra_books": extra_books,
        "char_counts": char_counts,
        "old_chars": {w["book"]: w.get("chars") for w in wmeta.get("works") or []},
        "old_status": {w["book"]: w.get("kb_status") for w in wmeta.get("works") or []},
        "intertext_edges": {"authorial": sum(1 for e in inter.get("edges") or [] if e.get("kind") == "authorial"),
                            "quoted": sum(1 for e in inter.get("edges") or [] if e.get("kind") == "quoted"),
                            "bare": sum(1 for e in inter.get("edges") or [] if e.get("kind") == "bare")},
    }
    return payload, stats


def _books_meta_notes(totals, lit, char_counts, legacy, extra_books) -> list:
    wmeta = legacy["wmeta"]
    old_chars = {w["book"]: w.get("chars") for w in wmeta.get("works") or []}
    char_diffs = [(b, old_chars[b], char_counts.get(b)) for b in sorted(char_counts)
                  if old_chars.get(b) is not None and old_chars[b] != char_counts.get(b)]
    old_status = {w["book"]: w.get("kb_status") for w in wmeta.get("works") or []}
    status_changes = [(b, old_status.get(b), "已点亮") for b in lit if old_status.get(b) != "已点亮"]
    notes = [
        f"books={totals['books']}，chapters={totals['chapters']}，chars={totals['chars']}。",
        "kb_status 口径：tagged/<书>/*.tagged.md 存在即『已点亮』，其余沿用 kb/作品元数据表.json 旧值。"
        + (f" 本次状态变化：{status_changes}。" if status_changes else " 本次无状态变化。"),
        "chars 口径：当前章回版 *.txt 非空白字符实测（旧站语义『字』）；"
        + (f"与旧 wmeta 值有 {len(char_diffs)} 部书小幅差异（底本 2026-11-05 修复后重算）：{char_diffs}。"
           if char_diffs else "与旧 wmeta 值一致。"),
        "chapters 口径：章回版 *.txt 文件枚举（含楔子 000）；与旧站逐书回数一致。"
        " config.CHAPTER_FILE_RE 对 6 部书漏计 28 回（『楔子』及『第一○○回』式回号），故不以 config.books() 计数。",
        "intertext_* 口径：kb/互文引用表.json 现算，仅 authorial/quoted（旧站口径）；bare 级计入旧表但旧站不导出。",
    ]
    if extra_books:
        notes.append(f"底本新增但元数据表未收录：{extra_books}（已按契约补位，year 置 null 并记 field_gaps）。")
    return notes


def _books_field_gaps(legacy, extra_books) -> list:
    gaps = [
        "year/year_conf/era/era_conf/series/series_conf/leads/leads_conf：新管线暂无考订登记层，"
        "取 kb/作品元数据表.json（只读旧资产）",
        "kb_status：新管线无『标注中』细分状态，仅按 tagged 是否存在置『已点亮』，其余 fallback 旧值",
        "chars：新管线无字数统计产物，按章回版底本非空白字符实测（旧 wmeta 值因底本修复小幅失真）",
        "intertext_*：新管线无互文产出，按旧站口径从 kb/互文引用表.json 现算（authorial+quoted）",
    ]
    if extra_books:
        gaps.append(f"底本新增书 {extra_books} 缺作品元数据（year/era/series/leads 置空）")
    return gaps


# ---------------------------------------------------------------- chapters.json
def verb_density(counter: Counter) -> dict:
    """逐章动词密度 dict：旧站五码兼容列 + 新管线六域原值。

    Sparkbars 只读 ◈◉▲◇○；映射口径：◈←⊞、◉←⊠、◇←▣、○←⊡；▲（擒控）新域无对应=0。
    新六域键保留原值，供后续 W 组 schema 直接消费。
    """
    out = {}
    for old in VERB_OLD_CODES:
        new = VERB_OLD_TO_NEW[old]
        out[old] = int(counter.get(new, 0)) if new else 0
    for dom in VERB_DOMAINS:
        out[dom] = int(counter.get(dom, 0))
    return out


def build_chapters(corpus: dict) -> tuple:
    """chapters.json payload + 口径统计。"""
    lit = lit_books(corpus)
    canon_map = load_registry_canon()
    payload = {}
    book_stats = {}
    for book in sorted(corpus):
        chapter_meta = corpus[book]
        entry = {"chapters": [{"no": c["no"], "title": c["title"]} for c in chapter_meta],
                 "lit": False}
        if book not in lit:
            payload[book] = entry
            continue

        chars_by_chapter = chapter_person_counts(book, canon_map)
        chapters = []
        narrative_total = 0
        verbs_total = 0
        stream_total = 0
        for c in chapter_meta:
            no = c["no"]
            tp = TAGGED / book / f"{no:03d}.tagged.md"
            if tp.exists():
                verbs, narrative, stream = parse_tagged_chapter(tp, no, canon_map)
            else:
                verbs, narrative, stream = Counter(), 0, []
            narrative_total += narrative
            verbs_total += sum(verbs.values())
            stream_total += len(stream)
            top = chars_by_chapter.get(no) or Counter()
            chars = [{"name": name, "n": int(cnt)}
                     for name, cnt in sorted(top.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_CHARS]]
            chapters.append({
                "no": no,
                "title": c["title"],
                "events": len(stream),
                "verbs": verb_density(verbs),
                "chars": chars,
                "stream": stream,
            })

        conc = load_concordance(book)
        entity_count = int((conc or {}).get("summary", {}).get("entity_count") or 0)
        entry.update({
            "chapters": chapters,
            "lit": True,
            "kb": {
                "entities": entity_count,
                # 新管线无事件表（N4/D03 未产出）：全部/非对话 ⟦⟧ 令牌数
                "events_narrative": narrative_total,
                "events_total": verbs_total,
                "relations": 0,     # 新关系层（N5）未产出 → 0 + meta.field_gaps
            },
        })
        payload[book] = entry
        book_stats[book] = {
            "chapters": len(chapters),
            "tagged": tagged_chapters(book),
            "events": stream_total,
            "events_total": verbs_total,
            "entities": entity_count,
            "concordance_generated": (conc or {}).get("generated"),
        }

    snapshot = _snapshot_block(corpus, lit, load_legacy_metadata())
    out = {"meta": {
        "generated": esc.today(),
        "schema": SCHEMA_CHAPTERS,
        "lit_books": lit,
        "note": ("回目取自章回版文件名（短句元数据）；已点亮书逐章事件流为 tagged 图谱事实"
                 "（A—动词—B 邻近对），不含摘录"),
        "source": SOURCE,
        "field_gaps": _chapters_field_gaps(book_stats),
        "notes": _chapters_meta_notes(lit, book_stats),
        "snapshot": snapshot,
    }}
    for book in sorted(corpus):
        out[book] = payload[book]
    return out, {"lit": lit, "book_stats": book_stats, "snapshot": snapshot}


def _chapters_field_gaps(book_stats) -> list:
    gaps = [
        "kb.relations：新关系层（N5/EX-4 依赖）未产出，置 0（旧站为旧 kb 关系表条目数）",
        "events/verbs/stream：新管线无事件层（N4/D03 未产出），由 tagged ⟦六域⟧ 令牌现算；"
        "stream 为同句 A—⟦动词⟧—B 邻近对（宾语须紧邻动词、间隔≤4 字符且仅虚词/趋向补语，"
        "主宾同一实体不配对）；旧站为旧 kb 事件表（含 LLM 校订与 dropped）",
        "stream.c（置信度）：新管线无事件置信标注，按主语与动词字符距离启发式分 high/medium/low",
        "verbs：旧站五码 ◈◉▲◇○ 为六域兼容映射（◈←⊞、◉←⊠、◇←▣、○←⊡；▲ 无对应域=0），"
        "新六域 ⊞⊠⊡⊟▣■ 原值同 dict 附出",
        "kb.entities：取 concordance 去重规范实体数（15 类全含），与旧 kb 实体登记表口径不同",
    ]
    return gaps


def _chapters_meta_notes(lit, book_stats) -> list:
    notes = [
        f"lit_books={lit}（旧站 3 部：七剑下天山/塞外奇侠传/白发魔女传；"
        f"新增 {sorted(set(lit) - {'七剑下天山', '塞外奇侠传', '白发魔女传'})}）。",
        "回目/回数：34 部逐回取自章回版文件名，与旧站逐书逐回一致（含 6 部书楔子 000 回）。",
        "逐章 events=本回 A—动词—B 邻近对数；kb.events_total=全部 ⟦⟧ 令牌数，"
        "kb.events_narrative=非对话内 ⟦⟧ 令牌数。",
    ]
    for book in lit:
        s = book_stats[book]
        notes.append(f"{book}：tagged {s['tagged']} 回、事件流 {s['events']} 条、"
                     f"⟦⟧ 令牌 {s['events_total']}、concordance 实体 {s['entities']}"
                     f"（{s['concordance_generated']}）。")
    return notes


# ---------------------------------------------------------------- 快照块
def _snapshot_block(corpus: dict, lit: list, legacy: dict) -> dict:
    """并发会话说明用快照：记录导出时可见的底本/tagged/registry/concordance 规模与时间戳。"""
    reg_path = REGISTRY / "entities.json"
    reg = read_json(reg_path) if reg_path.exists() else {}
    conc_generated = {}
    for book in lit:
        conc = load_concordance(book)
        if conc:
            conc_generated[book] = conc.get("generated")
    return {
        "exported_at": esc.now_iso(),
        "corpus_books": len(corpus),
        "corpus_chapters": sum(len(v) for v in corpus.values()),
        "tagged_books": {b: tagged_chapters(b) for b in lit},
        "registry_entities": len(reg.get("entities") or []),
        "registry_generated": reg.get("generated"),
        "concordance_generated": conc_generated,
        "legacy_meta_generated": (legacy.get("wmeta") or {}).get("meta", {}).get("generated"),
    }


# ---------------------------------------------------------------- 与旧站记录级对比（写入 notes）
def compare_books(payload: dict) -> list:
    old = esc.load_baseline("books.json")
    if not old:
        return ["（无旧站 books.json 基线，跳过记录级对比）"]
    ob = {b["book"]: b for b in old.get("books") or []}
    nb = {b["book"]: b for b in payload.get("books") or []}
    lines = [f"- 记录数：旧 {len(ob)} → 新 {len(nb)}；"
             f"新增书名 {sorted(set(nb) - set(ob)) or '无'}；缺失书名 {sorted(set(ob) - set(nb)) or '无'}。"]
    fields = ("no", "year", "year_conf", "era", "era_conf", "series", "series_conf",
              "leads", "leads_conf", "chapters", "chars", "kb_status",
              "intertext_out", "intertext_in")
    diffs: dict = defaultdict(list)
    for book in sorted(set(ob) & set(nb), key=lambda b: nb[b].get("no") or 0):
        for k in fields:
            if ob[book].get(k) != nb[book].get(k):
                diffs[k].append((book, ob[book].get(k), nb[book].get(k)))
    identical = [k for k in fields if k not in diffs]
    lines.append(f"- 逐字段一致：{', '.join(identical) if identical else '无'}。")
    for k, items in diffs.items():
        shown = items[:6]
        more = f" …等 {len(items)} 部" if len(items) > 6 else ""
        lines.append(f"- 字段差异 `{k}`（{len(items)} 部）：{shown}{more}。")
    # 互文明细逐书对齐
    ref_diff = [b for b in sorted(set(ob) & set(nb))
                if ob[b].get("out_refs") != nb[b].get("out_refs")
                or ob[b].get("in_refs") != nb[b].get("in_refs")]
    lines.append("- 互文出入明细 out_refs/in_refs："
                 + ("与旧站逐条一致。" if not ref_diff else f"{len(ref_diff)} 部不一致：{ref_diff[:6]}"))
    return lines


def compare_chapters(payload: dict) -> list:
    old = esc.load_baseline("chapters.json")
    if not old:
        return ["（无旧站 chapters.json 基线，跳过记录级对比）"]
    ob = {k: v for k, v in old.items() if k != "meta"}
    nb = {k: v for k, v in payload.items() if k != "meta"}
    lines = [f"- 书名集合：旧 {len(ob)} → 新 {len(nb)}；"
             f"新增 {sorted(set(nb) - set(ob)) or '无'}；缺失 {sorted(set(ob) - set(nb)) or '无'}。"]
    old_total = sum(len(v.get("chapters") or []) for v in ob.values())
    new_total = sum(len(v.get("chapters") or []) for v in nb.values())
    lines.append(f"- 回数合计：旧 {old_total} → 新 {new_total}。")
    no_diffs, title_diffs, lit_changes = [], [], []
    for book in sorted(set(ob) & set(nb)):
        oc, nc = ob[book].get("chapters") or [], nb[book].get("chapters") or []
        if [c.get("no") for c in oc] != [c.get("no") for c in nc]:
            no_diffs.append(book)
        if [c.get("title") for c in oc] != [c.get("title") for c in nc]:
            title_diffs.append(book)
        if bool(ob[book].get("lit")) != bool(nb[book].get("lit")):
            lit_changes.append((book, ob[book].get("lit"), nb[book].get("lit")))
    lines.append("- 逐收回号：" + ("34/34 部与旧站一致。" if not no_diffs else f"{no_diffs} 不一致"))
    lines.append("- 逐回回目：" + ("34/34 部与旧站一致。" if not title_diffs else f"{title_diffs} 不一致"))
    lines.append("- lit 变化：" + (str(lit_changes) if lit_changes else "无"))
    for book in sorted(set(ob) | set(nb)):
        old_lit = bool((ob.get(book) or {}).get("lit"))
        new_lit = bool((nb.get(book) or {}).get("lit"))
        if not (old_lit or new_lit):
            continue
        old_events = sum(len(c.get("stream") or []) for c in (ob.get(book) or {}).get("chapters") or [])
        new_events = sum(int(c.get("events") or 0) for c in (nb.get(book) or {}).get("chapters") or [])
        if old_lit and new_lit:
            lines.append(f"- {book}：旧事件流 {old_events} 条 → 新 {new_events} 条"
                         f"（新为 tagged 严格邻近对，量级低于旧站事件表；旧表含人工/LLM 校订与补造）")
        elif new_lit:
            lines.append(f"- {book}：旧站未点亮（无 lit/kb/事件流）→ 新点亮，回目 "
                         f"{len((nb[book] or {}).get('chapters') or [])} 回，事件流 {new_events} 条")
    return lines


def render_notes(payload: dict, kind: str) -> str:
    """报告「说明」段：与旧站记录级对比 + 口径提示（finish 已做契约字段级 diff）。"""
    if kind == "books":
        sections = ["### 与旧站 site/data/books.json 记录级对比", *compare_books(payload)]
    else:
        sections = ["### 与旧站 site/data/chapters.json 记录级对比", *compare_chapters(payload)]
    sections += [
        "",
        "### 复现命令",
        "```",
        "python scripts/export_site_books_chapters.py        # dry-run（默认，只写 staging/reports）",
        "```",
        "### 与旧站的预期差异（不计入 hard_gap）",
        "- 新管线无事件层/关系层/考订层：对应字段按 `meta.field_gaps` 口径补齐；",
        "- kb_status 已点亮由 3 部 → 5 部（江湖三女侠、冰魄寒光剑新 tagged 存在）；",
        "- 字数按当前章回版实测，3 部书与旧 wmeta 有 ±27 字内差异（底本修复）；",
        "- 事件流只保留 tagged 中 A—动词—B 严格邻近对（宾语紧邻动词），"
        "未做旧站事件表的人工/LLM 校订与补造，量级低于旧站；kb.events_* 仍按 ⟦⟧ 全量计数。",
    ]
    return "\n".join(sections)


# ---------------------------------------------------------------- 收尾
def run() -> int:
    if not CORPUS.exists():
        print(f"[EX-1] 底本目录不存在：{CORPUS}")
        return 2
    corpus = discover_corpus()
    char_counts = {book: corpus_char_count(book) for book in corpus}
    books_payload, books_stats = build_books(corpus, char_counts)
    chapters_payload, chapters_stats = build_chapters(corpus)

    print(f"[EX-1] 底本 {len(corpus)} 部 / {sum(len(v) for v in corpus.values())} 回；"
          f"已点亮 {len(chapters_stats['lit'])} 部：{chapters_stats['lit']}")
    print(f"[EX-1] books：{books_stats['intertext_edges']}；"
          f"字数实测 {books_payload['meta']['totals']['chars']}（旧站 17004547）")

    d_books = esc.finish("books.json", books_payload, exporter=EXPORTER,
                         notes=render_notes(books_payload, "books"))
    d_chapters = esc.finish("chapters.json", chapters_payload, exporter=EXPORTER,
                            notes=render_notes(chapters_payload, "chapters"))
    hard = d_books["hard_gap_count"] + d_chapters["hard_gap_count"]
    print(f"[EX-1] hard_gap 合计 = {hard}"
          f"（books={d_books['hard_gap_count']}, chapters={d_chapters['hard_gap_count']}）")
    if hard:
        print("[EX-1] ✗ 契约硬缺口未清零，见 reports")
        return 1
    print("[EX-1] ✓ 契约字段不缺、类型不破；dry-run 完成（staging + reports）")
    return 0


def main() -> int:
    if "--apply" in sys.argv:
        print("[EX-1] 注意：--apply 将经 export_site_common 备份后写 site/data；"
              "docs/51 阶段 1 验收默认先 dry-run。")
    return run()


if __name__ == "__main__":
    sys.exit(main())
