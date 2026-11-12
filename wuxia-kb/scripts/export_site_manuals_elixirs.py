# -*- coding: utf-8 -*-
"""EX-6b：manuals.json（秘籍谱 manuals-v1）/ elixirs.json（丹药谱 elixirs-v1）导出器
（名物页重构设计 §七 秘籍谱与丹药谱 · 决策 5/12/13，天山演示版任务 D11，2026-11-12）。

架构（复用 EX-6 模式）：人工校定底表（唯一真源）× registry/concordance（频次/覆盖书口径）
× KB 标注层 struct 扫描（出场定位符）——默认 dry-run 写 staging/logs，--apply 写 site/data（先备份）。

数据源（只读）：
  - kb/校订/秘籍谱.tsv（manual/aliases/arts/books/loc/note/status，人工校定稿）
  - kb/校订/丹药谱.tsv（elixir/kind/aliases/books/loc/note/status/negative_notes，人工校定稿；
    negative_notes=丹药级负证据注记列，D16 增——「注记——书名·NNN:NNN」段以「；」分隔）
  - kb/校订/毒解配对.tsv（poison/antidote/book/loc/note/status，D16 正式底表：14 组 18 证据行，
    由 D13 草案正式化——verbatim 摘样改写为原创注记；# 注释行跳过）
  - registry/concordance/<书>.json（ev_total 口径 + 覆盖书/回目，同 EX-6 weapons count 口径）
  - KB 标注层 struct 文件（tagged/<书>/NNN.struct.md，无标注纯文本、段号 [N] 与 tagged 同源）
    —— 出场定位符扫描口径（canonical+别名原文命中，含未入实体层的提及）
  - site/data/arts.json（related_arts 链接目标校验，advisory；缺失跳过）

入谱纪律（名物页重构设计 §七「入谱纪律同神兵：专名性归层、凡物不入谱、宁缺毋滥」）：
  - 通名不入谱：剑谱/拳经/剑诀/真经/秘籍/秘笈 等通名（及比喻用法，如 朱砂「掌心红似朱砂」）
    一律不入；拿不准的行标 draft——只有 status=校定 的行入站，draft 计入 meta 报告；
  - 校定行 books 列=人工核定的覆盖书（D11 逐条 grep concordance/struct 核证据后填写）；
    scope 口径下 concordance 覆盖书 ∪ 扫描覆盖书 ⊄ 校定书 → 导出报错（语料漂移须人工复核，
    不静默改写人工校定稿）；全量口径（--scope all / 不带 --scope）不设闸（TSV 只核 7 书），
    books=concordance ∪ 扫描 ∪ 底表 并集（方案 R6：两口径同源，全量口径不伪造 7 书外考订）。

口径（meta.field_gaps 固化）：
  - ev_total=concordance 该 canonical 全类型（{/•/☆/^…）出现合计；concordance 未收的行
    （未入标注实体层，如 曼陀罗花）→ ev_total=原文扫描计数并显式声明（ev_basis 字段）；
  - locs=KB 标注层 struct 原文扫描（canonical+别名，含「天山雪莲」中「雪莲」式子串命中），
    只作定位符清单，不作频次主张；count=扫描总数（含未标注提及），与 ev_total 两口径分列；
  - related_arts=秘籍↔武功人工配对（底表 arts 列）： arts.json 有页 → 前端互链；无页（如 惊涛剑法
    未收武功谱）→ 数据保留、前端纯文本呈现，meta.field_gaps 点名；配不上的行留空；
  - 毒↔解药配对（丹药，D16 落地）：毒解配对.tsv 14 组 18 证据行双向结构化——
    antidote_to=[{poison, note, locs}]（解药条「可解」清单）/ antidoted_by=[{antidote, note, locs}]
    （谱内毒物条「可被解」清单）/ negative_notes=[{desc, locs}]（丹药级负证据），三键恒在
    （无数据=[]）；poison/antidote null 占位键移除（契约演进：D16 重置 elixirs.json 契约基线）；
    解药名须为丹药谱校定名/别名（互链总有效，装载即校验）；解药别名（少阳小还丹式）归并正名；
    通名毒不立配对；新毒物实体已第二批入谱（F3，2026-11-12：kind=毒药 5 条孔雀粪/蛇焰箭/
    七煞白眉针/孔雀胆/赤毒珠）——毒物条「可被解」互链由本表 antidoted_by 驱动；
    掌毒/功毒类目（阴风毒砂掌(掌毒) 等）为武功毒伤类目，不入丹药谱。

用法：
  python scripts/export_site_manuals_elixirs.py                       # 全量口径 dry-run
  python scripts/export_site_manuals_elixirs.py --scope tianshan-demo # 天山 7 书裁剪口径
  python scripts/export_site_manuals_elixirs.py --scope tianshan-demo --apply   # 写 site/data
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import export_site_common as esc  # noqa: E402
from export_site_sects_weapons_arts import BOOKS  # noqa: E402  (书序与 EX-6 同源，勿重排)

KB = config.LEGACY_KB
ROOT = config.ROOT
EXPORTER = "EX-6b export_site_manuals_elixirs"

MANUAL_TSV = KB / "校订" / "秘籍谱.tsv"
MANUAL_HEADER = ["manual", "aliases", "arts", "books", "loc", "note", "status"]
ELIXIR_TSV = KB / "校订" / "丹药谱.tsv"
ELIXIR_HEADER = ["elixir", "kind", "aliases", "books", "loc", "note", "status", "negative_notes"]
PAIR_TSV = KB / "校订" / "毒解配对.tsv"
PAIR_HEADER = ["poison", "antidote", "book", "loc", "note", "status"]
ROW_STATUS = ("校定", "draft")                    # 只消费 校定 行（人工校定稿唯一真源）
# F3（2026-11-12 用户裁定）：类别词表扩「毒药」——毒物名物实体（孔雀粪/蛇焰箭/七煞白眉针/
# 孔雀胆/赤毒珠）第二批入谱，毒物条「可被解」互链由毒解配对表 antidoted_by 驱动
ELIXIR_KINDS = ("丹药", "药材", "毒药")
# loc 列=「书名·NNN:NNN」（·或空格分隔；与神兵表-补录/武功评语 loc 同口径，书名不得含空白）
LOC_RE = re.compile(r"^(?P<book>[^\s·]+)\s*[·\s]\s*(?P<loc>\d{1,3}:\d{1,4})$")
PARA_RE = re.compile(r"^\[(\d+)\]")
# 毒解配对 loc 列=纯 NNN:NNN（书名独立成列）；通名毒不入 poison 列（专名性纪律，D13/D16 口径）
PAIR_LOC_RE = re.compile(r"^\d{1,3}:\d{1,4}$")
GENERIC_POISONS = {"解药", "毒药", "丹药", "毒箭", "毒针", "蛇毒", "毒酒", "毒烟",
                   "毒水", "暗器", "毒药粉", "蒙汗药"}

# 秘籍类别词表（索引分组用；后缀规则，长词优先）
MANUAL_CATS = [("剑诀", "剑诀·剑谱"), ("剑谱", "剑诀·剑谱"),
               ("真经", "经"), ("拳经", "经"), ("经", "经"),
               ("要诀", "诀"), ("百炼诀", "诀"), ("诀", "诀"),
               ("秘笈", "秘笈")]


class ManualsElixirsError(ValueError):
    """秘籍/丹药谱 TSV 非法或语料-考订覆盖不一致（表头/状态词/类别/定位符/重复行/覆盖书缺口），
    消息中文，导出即报错（不静默改写人工校定稿）。"""


def manual_category(name: str) -> str:
    for suf, cat in MANUAL_CATS:
        if name.endswith(suf):
            return cat
    return "其他"


# ---------------------------------------------------------------- TSV 装载
def _parse_loc_cell(cell: str, i: int, p: Path) -> tuple[str, str]:
    m = LOC_RE.match(cell)
    if not m:
        raise ManualsElixirsError(f"第 {i} 行 loc={cell!r} 非「书名·NNN:NNN」式"
                                  f"（书名不得含空白）：{p}")
    return m.group("book"), m.group("loc")


def _split_names(cell: str) -> list[str]:
    return [x.strip() for x in re.split(r"[、,，]", cell) if x.strip()]


def _parse_negative_notes(cell: str, i: int, p: Path) -> list[dict]:
    """丹药谱 negative_notes 列（D16）：「注记——书名·NNN:NNN」段以「；」分隔；
    空单元格 → []；段内多定位符以「、」分隔（每段须全称「书名·NNN:NNN」）。"""
    if not cell.strip():
        return []
    items: list[dict] = []
    for seg in cell.split("；"):
        seg = seg.strip()
        if not seg:
            continue
        if "——" not in seg:
            raise ManualsElixirsError(f"丹药谱 TSV 第 {i} 行 negative_notes 段 {seg!r} "
                                      f"非「注记——书名·NNN:NNN」式：{p}")
        desc, locs_cell = seg.rsplit("——", 1)
        if not desc.strip():
            raise ManualsElixirsError(f"丹药谱 TSV 第 {i} 行 negative_notes 段注记为空：{p}")
        locs = []
        for part in locs_cell.split("、"):
            m = LOC_RE.match(part.strip())
            if not m:
                raise ManualsElixirsError(f"丹药谱 TSV 第 {i} 行 negative_notes 定位符 "
                                          f"{part!r} 非「书名·NNN:NNN」式：{p}")
            locs.append({"book": m.group("book"), "loc": m.group("loc")})
        items.append({"desc": desc.strip(), "locs": locs})
    return items


def _load_rows(path: Path, header: list[str], name_col: str, label: str,
               kinds: tuple | None = None) -> tuple[list[dict], dict]:
    """通用 TSV 装载：表头/空值/状态词/(丹药)类别词/定位符/重复行逐项校验；draft 行保留不入站。

    返回 (rows, stats)；row = {name, kind?, aliases, arts, books, book, loc, note, status,
    negative_notes?}。
    列序：秘籍谱 manual/aliases/arts/books/loc/note/status；
          丹药谱 elixir/kind/aliases/books/loc/note/status/negative_notes（无 arts 列；D16 增列）。
    """
    if not path.exists():
        return [], {"rows": 0, "consumed": 0, "draft": 0, "exists": False}
    with open(path, encoding="utf-8", newline="") as f:
        raw = list(csv.reader(f, delimiter="\t"))
    if not raw or [c.strip() for c in raw[0][:len(header)]] != header:
        raise ManualsElixirsError(f"{label} TSV 表头必须为 {'/'.join(header)}：{path}")
    known_books = set(config.book_names()) | \
        {p.stem for p in (config.DIR_REGISTRY / "concordance").glob("*.json")}
    out, seen = [], set()
    stats = {"rows": 0, "consumed": 0, "draft": 0, "exists": True}
    for i, row in enumerate(raw[1:], 2):
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if len(cells) < len(header):
            raise ManualsElixirsError(f"{label} TSV 第 {i} 行列不足（须 {'/'.join(header)}）：{path}")
        name, status, aliases_cell, books_cell, loc_cell, note = (
            cells[0], cells[6], cells[1] if not kinds else cells[2], cells[3], cells[4], cells[5])
        kind = cells[1] if kinds else None
        arts = [] if kinds else _split_names(cells[2])
        stats["rows"] += 1
        if not name or not books_cell or not loc_cell:
            raise ManualsElixirsError(f"{label} TSV 第 {i} 行 {name_col}/books/loc 存在空值"
                                      f"（loc 必填——无定位符的考订不入站）：{path}")
        if kinds and kind not in kinds:
            raise ManualsElixirsError(f"{label} TSV 第 {i} 行 kind={kind!r} 不在类别词表"
                                      f"（{'/'.join(kinds)}）：{path}")
        if status not in ROW_STATUS:
            raise ManualsElixirsError(f"{label} TSV 第 {i} 行 status={status!r} 不在校定档"
                                      f"（{'/'.join(ROW_STATUS)}）：{path}")
        book, loc = _parse_loc_cell(loc_cell, i, path)
        tsv_books = _split_names(books_cell)
        bad_books = [b for b in tsv_books if b not in known_books]
        if bad_books:
            raise ManualsElixirsError(f"{label} TSV 第 {i} 行 books 含未知书名 {bad_books}"
                                      f"（须为章回版/concordance 在册书名）：{path}")
        if book not in tsv_books:
            raise ManualsElixirsError(f"{label} TSV 第 {i} 行 loc 书名 {book!r} 不在 books 列"
                                      f"（{tsv_books}）——定位符与覆盖书不一致：{path}")
        if name in seen:
            raise ManualsElixirsError(f"{label} TSV 第 {i} 行：{name} 重复行（唯一真源）：{path}")
        seen.add(name)
        if status == "draft":
            stats["draft"] += 1
        else:
            stats["consumed"] += 1
        rec = {"name": name, "kind": kind, "aliases": _split_names(aliases_cell),
               "arts": arts, "books": tsv_books,
               "book": book, "loc": loc, "note": note, "status": status}
        if kinds:                                    # 丹药谱：负证据注记列（D16）
            rec["negative_notes"] = _parse_negative_notes(cells[7], i, path)
        out.append(rec)
    return out, stats


def load_manual_tsv(path: Path | None = None) -> tuple[list[dict], dict]:
    p = Path(path) if path is not None else MANUAL_TSV
    return _load_rows(p, MANUAL_HEADER, "manual", "秘籍谱")


def load_elixir_tsv(path: Path | None = None) -> tuple[list[dict], dict]:
    p = Path(path) if path is not None else ELIXIR_TSV
    return _load_rows(p, ELIXIR_HEADER, "elixir", "丹药谱", kinds=ELIXIR_KINDS)


def load_antidote_tsv(path: Path | None = None) -> tuple[list[dict], dict]:
    """毒解配对底表装载（D16）：poison/antidote/book/loc/note/status，# 注释行与空行跳过。

    校验：表头/状态词/定位符（纯 NNN:NNN，书名独立列）/已知书名/通名毒排除/
    重复证据行（poison+antidote+book+loc）/同组注记一致（同配对多证据行 note 必须相同）。
    """
    p = Path(path) if path is not None else PAIR_TSV
    if not p.exists():
        return [], {"rows": 0, "consumed": 0, "draft": 0, "exists": False}
    with open(p, encoding="utf-8", newline="") as f:
        raw = list(csv.reader(f, delimiter="\t"))
    data = [(i, r) for i, r in enumerate(raw, 1)
            if r and r[0].strip() and not r[0].startswith("#")]
    if not data or [c.strip() for c in data[0][1]] != PAIR_HEADER:
        raise ManualsElixirsError(f"毒解配对 TSV 表头必须为 {'/'.join(PAIR_HEADER)}：{p}")
    known_books = set(config.book_names()) | \
        {p2.stem for p2 in (config.DIR_REGISTRY / "concordance").glob("*.json")}
    out: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    pair_notes: dict[tuple[str, str], str] = {}
    stats = {"rows": 0, "consumed": 0, "draft": 0, "exists": True}
    for fi, row in data[1:]:
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if len(cells) < len(PAIR_HEADER):
            raise ManualsElixirsError(
                f"毒解配对 TSV 第 {fi} 行列不足（须 {'/'.join(PAIR_HEADER)}）：{p}")
        poison, antidote, book, loc, note, status = cells
        stats["rows"] += 1
        if not poison or not antidote or not book or not loc or not note:
            raise ManualsElixirsError(
                f"毒解配对 TSV 第 {fi} 行 poison/antidote/book/loc/note 存在空值"
                f"（注记必填——正式行须原创 L0 注记，不留 verbatim 摘样）：{p}")
        if status not in ROW_STATUS:
            raise ManualsElixirsError(
                f"毒解配对 TSV 第 {fi} 行 status={status!r} 不在校定档"
                f"（{'/'.join(ROW_STATUS)}）：{p}")
        if not PAIR_LOC_RE.match(loc):
            raise ManualsElixirsError(
                f"毒解配对 TSV 第 {fi} 行 loc={loc!r} 非「NNN:NNN」式（书名独立成列）：{p}")
        if book not in known_books:
            raise ManualsElixirsError(
                f"毒解配对 TSV 第 {fi} 行 book={book!r} 为未知书名"
                f"（须为章回版/concordance 在册书名）：{p}")
        if poison in GENERIC_POISONS:
            raise ManualsElixirsError(
                f"毒解配对 TSV 第 {fi} 行 poison={poison!r} 为通名毒"
                f"（专名性纪律：通名不入 poison 列）：{p}")
        key = (poison, antidote, book, loc)
        if key in seen:
            raise ManualsElixirsError(
                f"毒解配对 TSV 第 {fi} 行：{poison}↔{antidote} {book}·{loc} 重复证据行：{p}")
        seen.add(key)
        if status == "draft":
            stats["draft"] += 1
        else:
            stats["consumed"] += 1
        pk = (poison, antidote)
        if pk in pair_notes and pair_notes[pk] != note:
            raise ManualsElixirsError(
                f"毒解配对 TSV 第 {fi} 行：{poison}↔{antidote} 同组注记不一致"
                f"（同配对多证据行 note 必须相同）：{p}")
        pair_notes[pk] = note
        out.append({"poison": poison, "antidote": antidote, "book": book,
                    "loc": loc, "note": note, "status": status})
    return out, stats


def validate_antidotes_against_spectrum(pairs: list[dict], elixir_rows: list[dict]) -> None:
    """解药专名必须为丹药谱校定名/别名（互链总有效；别名如 少阳小还丹 由消费端归并正名）。"""
    spectrum: set[str] = set()
    for r in elixir_rows:
        if r.get("status") == "校定":
            spectrum.add(r["name"])
            spectrum.update(r.get("aliases") or [])
    bad = sorted({r["antidote"] for r in pairs if r["antidote"] not in spectrum})
    if bad:
        raise ManualsElixirsError(
            f"毒解配对解药 {bad} 不在丹药谱校定名/别名——解药页互链将断，请人工复核底表")


def group_antidote_pairs(pairs: list[dict], book_rank,
                         name2canon: dict[str, str] | None = None) -> tuple[dict, dict]:
    """证据行 → 双向组：({正名: [{poison, note, locs}]}, {正名: [{antidote, note, locs}]})。

    antidote_to 键=毒名（原样，含 (掌毒)/(功毒) 后缀；毒名未入谱实体层——文本呈现）；
    antidoted_by 键=解药名（原样；必为丹药谱校定名/别名，前端可互链）；别名解药归并正名
    （name2canon：名/别名 → 正名，由丹药谱校定行构建）。
    locs 按（书序, 回, 段）排序；组按键名排序（确定性）。
    """
    name2canon = name2canon or {}
    to_map: dict[str, dict[str, dict]] = {}
    by_map: dict[str, dict[str, dict]] = {}
    for r in pairs:
        loc = {"book": r["book"], "loc": r["loc"]}
        antidote_canon = name2canon.get(r["antidote"], r["antidote"])
        poison_canon = name2canon.get(r["poison"], r["poison"])
        g = to_map.setdefault(antidote_canon, {}).setdefault(
            r["poison"], {"poison": r["poison"], "note": r["note"], "locs": []})
        g["locs"].append(loc)
        h = by_map.setdefault(poison_canon, {}).setdefault(
            r["antidote"], {"antidote": r["antidote"], "note": r["note"], "locs": []})
        h["locs"].append(loc)

    def _sort_key(x: dict) -> tuple:
        b, l = x["book"], x["loc"]
        ch, para = l.split(":")
        return (book_rank(b), int(ch), int(para))

    def _finalize(groups: dict[str, dict[str, dict]]) -> list:
        return [dict(v, locs=sorted(v["locs"], key=_sort_key))
                for _, v in sorted(groups.items(), key=lambda kv: kv[0])]

    return ({name: _finalize(m) for name, m in to_map.items()},
            {name: _finalize(m) for name, m in by_map.items()})


# ---------------------------------------------------------------- concordance / struct 扫描
def load_concordance(books: list[str] | None = None) -> dict:
    """{(canonical): {count, books: {book: n}, chapters: {book: set}}}——口径同 EX-6 load_sources
    conc 段（canonical 聚合不分类型）；books 为 None 时读 registry/concordance 全部在册书。"""
    d = config.DIR_REGISTRY / "concordance"
    book_iter = books if books is not None else \
        (sorted(p.stem for p in d.glob("*.json")) if d.exists() else [])
    conc: dict[str, dict] = {}
    for b in book_iter:
        p = d / f"{b}.json"
        if not p.exists():
            continue
        for e in json.load(open(p, encoding="utf-8")).get("entities", []):
            rec = conc.setdefault(e["canonical"], {"count": 0, "books": {}, "chapters": {}})
            rec["count"] += e.get("total", 0)
            rec["books"][b] = rec["books"].get(b, 0) + e.get("total", 0)
            rec["chapters"].setdefault(b, set()).update(
                c.get("chapter", 0) for c in e.get("chapter_counts", []) or [])
    return conc


def scan_corpus(names: list[str], books: list[str]) -> tuple[dict[str, list], dict[str, set]]:
    """KB 标注层 struct 原文扫描（canonical+别名）→ ({name: [ {book,loc} …]}, {name: {book…}})。

    struct 文件（tagged/<书>/NNN.struct.md）与 tagged 同源同段号（[N] 前缀）；struct 缺失的回
    回目回退 tagged（标注括记可能截断字符串，两源并集、同段去重）。段号取该行 [N] 前缀，
    无前缀行并入前一段（续行）。
    """
    locs: dict[str, list] = {n: [] for n in names}
    hit_books: dict[str, set] = {n: set() for n in names}
    for b in books:
        d = config.DIR_TAGGED / b
        if not d.exists():
            continue
        chapter_sources: dict[int, list[Path]] = {}
        for p in sorted(d.glob("*.struct.md")):
            chapter_sources.setdefault(int(p.stem.split(".")[0]), []).append(p)
        for p in sorted(d.glob("*.tagged.md")):
            ch = int(p.stem.split(".")[0])
            if ch not in chapter_sources:
                chapter_sources[ch] = [p]
        for ch in sorted(chapter_sources):
            paras: dict[str, set] = {n: set() for n in names}
            for fp in chapter_sources[ch]:
                cur = 0
                for line in fp.read_text(encoding="utf-8").split("\n"):
                    m = PARA_RE.match(line)
                    if m:
                        cur = int(m.group(1))
                    for n in names:
                        if n in line:
                            paras[n].add(cur)
            for n, ps in paras.items():
                for para in sorted(ps):
                    locs[n].append({"book": b, "loc": f"{ch:03d}:{para}"})
                    hit_books[n].add(b)
    for n in names:
        locs[n].sort(key=lambda x: (x["book"], int(x["loc"].split(":")[0]),
                                    int(x["loc"].split(":")[1])))
    return locs, hit_books


# ---------------------------------------------------------------- 构建
def _resolve_row(row: dict, conc: dict, locs: dict, hit_books: dict,
                 scope, book_rank, to_map=None, by_map=None) -> tuple[dict, list[str]]:
    """单行 → 记录（books 并集/频次双口径/定位符），并返回该行的 gap 注记清单。

    覆盖闸（仅 scope 口径）：concordance 覆盖书 ∪ 扫描覆盖书（canonical+别名）⊆ 校定行 books。
    """
    name, aliases = row["name"], row["aliases"]
    tsv_books = set(row["books"])
    conc_books: set = set(conc.get(name, {}).get("books", {}))
    scan_books: set = set(hit_books.get(name) or set())
    alias_names = list(aliases)
    for a in alias_names:
        conc_books |= set(conc.get(a, {}).get("books", {}))
        scan_books |= set(hit_books.get(a) or set())
    gaps: list[str] = []
    if scope is not None:
        scope_books = set(scope["books"])
        conc_books &= scope_books
        scan_books &= scope_books
        unattested = (conc_books | scan_books) - tsv_books
        if unattested:
            raise ManualsElixirsError(
                f"「{name}」语料覆盖书 {sorted(unattested)} 未列入校定行 books（{sorted(tsv_books)}）"
                f"——concordance/扫描与人工校定不一致，请人工复核后更新底表")
        if not (conc_books or scan_books):
            raise ManualsElixirsError(
                f"「{name}」scope 内无任何语料出现（concordance/扫描皆空）——校定行与语料不一致")
    else:
        extra = sorted((conc_books | scan_books) - tsv_books)
        if extra:
            gaps.append(f"全量口径：concordance/扫描另见书外覆盖 {'、'.join(extra)}"
                        "（底表 books 列为天山 7 书人工核口径）")
    # books：并集（concordance 回目 ∪ 扫描定位符回目），按书序排
    books: dict[str, list] = {}
    for b in sorted(conc_books | scan_books, key=book_rank):
        chs = set(conc.get(name, {}).get("chapters", {}).get(b) or set())
        for x in (locs.get(name) or []) + [x for a in alias_names for x in (locs.get(a) or [])]:
            if x["book"] == b:
                chs.add(int(x["loc"].split(":")[0]))
        books[b] = sorted(chs)
    # 频次：ev_total=concordance 标注口径（canonical 全类型）；未收者回退扫描计数并声明
    #（F4：回退计 canonical+别名扫描——玉匣解药式考订定名行原著无连称、由别名（玉匣）携定位符，
    # ev_total 回退取 count 而非 canonical 单名扫描，避免「证据 0 处」与定位符表矛盾）
    count = len(locs.get(name) or []) + sum(len(locs.get(a) or []) for a in alias_names)
    ev_total = int(conc.get(name, {}).get("count") or 0)
    if ev_total:
        ev_basis = "concordance"
    else:
        ev_total = count
        ev_basis = "原文扫描计数（未入标注实体层）"
        gaps.append(f"「{name}」未入标注实体层（concordance 未收），ev_total=原文扫描计数"
                    + ("（含别名扫描）" if alias_names else ""))
    rec = {
        "name": name,
        "aliases": list(aliases),
        "books": books,
        "count": count,
        "ev_total": ev_total,
        "ev_basis": ev_basis,
        "anchor": {"book": row["book"], "loc": row["loc"]},
        "note": row["note"],
    }
    if row.get("kind"):
        rec["kind"] = row["kind"]
        # 毒↔解药配对（D16）：三键恒在（无数据=[]）；poison/antidote null 占位键移除
        rec["antidote_to"] = list((to_map or {}).get(name) or [])
        rec["antidoted_by"] = list((by_map or {}).get(name) or [])
        rec["negative_notes"] = list(row.get("negative_notes") or [])
    else:
        rec["category"] = manual_category(name)
        rec["related_arts"] = list(row["arts"])   # 配不上 → []（不伪造配对；契约统一键）
    return rec, gaps


def build_spectrum(rows: list[dict], stats: dict, scope, conc: dict,
                   scan_books: list[str], spectrum: str,
                   pairs: list[dict] | None = None) -> dict:
    """通用构建：秘籍谱（spectrum="manuals"）/ 丹药谱（spectrum="elixirs"）同构。

    只有 status=校定 的行入站（draft 行不计入 records，仅 stats["draft"] 上报）；
    丹药谱配对消费（D16）：pairs=毒解配对校定证据行 → antidote_to/antidoted_by/negative_notes
    三键恒在（无数据=[]），毒解配对组数入 meta.totals["毒解配对"]。
    """
    rows = [r for r in rows if r.get("status") != "draft"]
    is_scope = scope is not None
    scan_scope_books = list(scope["books"]) if is_scope else list(scan_books)
    book_order = list(scope["books"]) if is_scope else list(BOOKS)

    def book_rank(b: str) -> int:
        return book_order.index(b) if b in book_order else len(book_order)

    # 毒解配对分组（丹药谱专用；秘籍谱忽略）
    pair_to: dict = {}
    pair_by: dict = {}
    n_pairs = 0
    if spectrum == "elixirs" and pairs:
        pairs = [r for r in pairs if r.get("status") != "draft"]
        name2canon = {}
        for row in rows:
            name2canon[row["name"]] = row["name"]
            for a in row["aliases"]:
                name2canon[a] = row["name"]
        pair_to, pair_by = group_antidote_pairs(pairs, book_rank, name2canon)
        n_pairs = len({(r["poison"], r["antidote"]) for r in pairs})

    names: list[str] = []
    for row in rows:
        names.append(row["name"])
        names.extend(row["aliases"])
    locs, hit_books = scan_corpus(sorted(set(names)), scan_scope_books)

    records, all_gaps = [], []
    for row in rows:
        rec, gaps = _resolve_row(row, conc, locs, hit_books, scope, book_rank,
                                 to_map=pair_to, by_map=pair_by)
        all_gaps.extend(gaps)
        full_locs = (locs.get(row["name"]) or []) + \
            [x for a in row["aliases"] for x in (locs.get(a) or [])]
        rec["locs"] = full_locs
        rec["evidence"] = [dict(x, kind="原文扫描") for x in full_locs[:12]]
        records.append(rec)

    # related_arts 链接目标校验（advisory）：site/data/arts.json 有页→互链；无页→纯文本呈现
    arts_path = esc.SITE_DATA / "arts.json"
    art_names: set[str] = set()
    if arts_path.exists():
        try:
            art_names = {a["canonical"] for a in
                         json.load(open(arts_path, encoding="utf-8")).get("arts", [])}
        except (json.JSONDecodeError, OSError):
            art_names = set()
    no_art_page = sorted(f"{rec['name']}↔{art}" for rec in records
                         for art in (rec.get("related_arts") or [])
                         if art_names and art not in art_names)

    records.sort(key=lambda r: (-(r["ev_total"]), r["name"]))
    n_scope_books = sorted({b for r in records for b in r["books"]}, key=book_rank)
    n_kind = Counter(r.get("kind") for r in records)
    meta = {
        "generated": esc.today(),
        "schema": f"{spectrum}-v1",
        "books": n_scope_books,
        **({"scope": scope["profile"]} if is_scope else {}),
        "totals": {
            spectrum: len(records),
            "draft": stats.get("draft", 0),
            "locs": sum(len(r["locs"]) for r in records),
            **({"丹药": n_kind.get("丹药", 0), "药材": n_kind.get("药材", 0),
                "毒药": n_kind.get("毒药", 0),
                "毒解配对": n_pairs} if spectrum == "elixirs" else {}),
        },
        "source": "kb/校订 底表（人工校定稿）× registry/concordance × KB 标注层扫描（EX-6b）",
        "field_gaps": [
            "ev_total=concordance 标注口径（canonical 全类型出现合计，"
            + ("天山 7 书 scope 内" if is_scope else "全量书目")
            + "）；count/locs=KB 标注层原文扫描（canonical+别名，含复合名子串命中，"
              "如「天山雪莲」中的「雪莲」）——两口径分列，定位符清单不作频次主张。",
            "通名不入谱（专名性纪律）：剑谱/拳经/剑诀/真经/秘籍/秘笈 等通名与比喻用法不入；"
            "底表 draft 行不入首批（meta.totals.draft）。",
        ],
    }
    if spectrum == "elixirs":
        meta["field_gaps"].extend([
            "毒↔解药配对 D16 落地：毒解配对.tsv " + str(n_pairs) + " 组（校定）双向结构化——"
            "antidote_to=[{poison, note, locs}]（解药条「可解」）/ antidoted_by=[{antidote, note, "
            "locs}]（谱内毒物条「可被解」）/ negative_notes=[{desc, locs}]（丹药级负证据，"
            "如 碧灵丹 对皇帝毒酒无效）。三键恒在，无数据=[]。",
            "通名毒（皇帝毒酒/唐家暗器毒等）与无名解药不立配对（专名性纪律）；"
            "五毒散↔消魂蚀骨散同伤异名，底表两行分立、注记互见。",
        ])
        # F3：毒物实体入谱情况（配对表内毒名 → 谱内 kind=毒药 条互链；掌毒/功毒类目与未入谱
        # 毒名仍以文本呈现，不伪造实体）
        if pairs:
            paired_poisons = {r["poison"] for r in pairs if r.get("status") != "draft"}
            spectrum_names = {r["name"] for r in rows} | \
                {a for r in rows for a in (r.get("aliases") or [])}
            class_poisons = sorted(p for p in paired_poisons if p.endswith("）") or p.endswith(")"))
            out_pois = sorted(p for p in paired_poisons
                              if p not in spectrum_names
                              and not (p.endswith("）") or p.endswith(")")))
            if out_pois:
                meta["field_gaps"].append(
                    "毒名未入谱实体层（第二批候选），现以文本列于解药页：" + "、".join(out_pois) + "。")
            else:
                meta["field_gaps"].append(
                    "毒物名物已入谱（F3，kind=毒药 5 条：孔雀粪/蛇焰箭/七煞白眉针/孔雀胆/赤毒珠）"
                    "——解药页 antidote_to 毒名与毒物页 antidoted_by 解药名双向互链；"
                    + (f"掌毒/功毒类目（{'、'.join(class_poisons)}）为武功毒伤类目不入丹药谱，"
                       "仍以文本呈现。" if class_poisons else ""))
    if stats.get("draft"):
        meta["field_gaps"].append(f"底表 draft 行 {stats['draft']} 条未消费（待人工裁定后再入首批）。")
    if no_art_page:
        meta["field_gaps"].append(
            "related_arts 无武功专页（数据保留，前端纯文本呈现）：" + "、".join(no_art_page) + "。")
    if not is_scope:
        meta["field_gaps"].append(
            "全量口径不设「覆盖书 ⊆ 底表 books」闸（底表 books 列为天山 7 书人工核口径）；"
            "books=concordance ∪ 原文扫描 ∪ 底表 并集，不伪造 7 书外考订。")
    if all_gaps:
        meta["field_gaps"].extend(all_gaps)
    return {"meta": meta, spectrum: records}


def tagged_book_dirs() -> list[str]:
    """全量口径扫描范围：KB 标注层在册书目录名（有目录即扫）。"""
    d = config.DIR_TAGGED
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


def ensure_contract(name: str, payload) -> None:
    """首导契约基线：contracts/<name>.schema.json 缺失时，以本次 payload 签名落盘
    （口径同 esc.snapshot_contracts 阶段 0；此后每次导出与基线 diff）。"""
    cp = esc.contract_path(name)
    if not cp.exists():
        esc.atomic_write_json({"name": name, "generated": esc.now_iso(),
                               "schema": esc.signature(payload)}, cp)
        print(f"[EX-6b] 首导契约基线 → {cp.name}")


# ---------------------------------------------------------------- 主流程
def main() -> int:
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    conc = load_concordance(scope["books"] if scope else None)
    m_rows, m_stats = load_manual_tsv()
    e_rows, e_stats = load_elixir_tsv()
    p_rows, p_stats = load_antidote_tsv()
    validate_antidotes_against_spectrum([r for r in p_rows if r["status"] == "校定"], e_rows)
    all_books = tagged_book_dirs()
    payloads = {
        "manuals.json": build_spectrum(m_rows, m_stats, scope, conc, all_books, "manuals"),
        "elixirs.json": build_spectrum(e_rows, e_stats, scope, conc, all_books, "elixirs",
                                       pairs=p_rows),
    }
    notes = {
        "manuals.json": (f"秘籍谱：底表校定行 {m_stats.get('consumed', 0)} / draft "
                         f"{m_stats.get('draft', 0)}；产出 {len(payloads['manuals.json']['manuals'])} 件"
                         "（manuals-v1，按 (-ev_total, name) 排序）。"),
        "elixirs.json": (f"丹药谱：底表校定行 {e_stats.get('consumed', 0)} / draft "
                         f"{e_stats.get('draft', 0)}；产出 {len(payloads['elixirs.json']['elixirs'])} 件"
                         f"（elixirs-v1：丹药 {payloads['elixirs.json']['meta']['totals'].get('丹药', 0)}"
                         f" + 药材 {payloads['elixirs.json']['meta']['totals'].get('药材', 0)}"
                         f"；毒解配对 {payloads['elixirs.json']['meta']['totals'].get('毒解配对', 0)}"
                         f" 组 / 毒解配对底表校定行 {p_stats.get('consumed', 0)}（D16 双向结构化）。"),
    }
    diffs = {}
    for fname, payload in payloads.items():
        ensure_contract(fname, payload)
        diffs[fname] = esc.finish(fname, payload, exporter=EXPORTER, notes=notes[fname])
        print(f"[EX-6b] {fname}: {diffs[fname]['old_record_count']} → "
              f"{diffs[fname]['new_record_count']} | hard_gap={diffs[fname]['hard_gap_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
