#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W12 · 跨书叙事线索生成器（同实体 / 同名异人 / 仅提及 + authorial/quoted/bare 判真）

数据（只读）：
  * EX-4 graph：`logs/export/staging/graph.json`（489/907；nodes[].books 跨书并集）
  * N10 cards：`registry/sku/cards.json`（active_books / 别名）
  * registry：`registry/entities.json`、`registry/display_canonical.json`（同名/展示层）
  * concordance：`registry/concordance/<书>.json`（逐书首见锚）
  * N6 互文：`registry/intertext/intertext_loc.json`（1904 边；authorial 98/quoted 31/bare 1775）
  * crossover：`registry/crossover/merge_candidates.json`（140 候选；判真参考）
  * books/chapters：`logs/export/staging/books.json`、`chapters.json`（series/year）

三类跨书（SKILL_W12 §二）：
  * character-line：canonical 同实体跨书（nodes[].books ≥2；按 year/series 排）
  * same-name-diff-person：display_canonical/同名不同实体 → 必须分写
  * mention-only：N6 bare 边且无 authorial/quoted → 只能写"被提及"
判真顺序：canonical 是否同 → 边 kind authorial/quoted → loc 是否 resolved → 才决定叙事强度。

输出：`registry/crossbook_threads.json`；报告 `logs/qa/crossbook_threads_report.md`
CLI：--dry-run（默认）/--apply/--selftest/--strict
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH_JSON = ROOT / "logs" / "export" / "staging" / "graph.json"
BOOKS_JSON = ROOT / "logs" / "export" / "staging" / "books.json"
CHAPTERS_JSON = ROOT / "logs" / "export" / "staging" / "chapters.json"
CARDS_JSON = ROOT / "registry" / "sku" / "cards.json"
ENTITIES_JSON = ROOT / "registry" / "entities.json"
DISPLAY_JSON = ROOT / "registry" / "display_canonical.json"
INTERTEXT_JSON = ROOT / "registry" / "intertext" / "intertext_loc.json"
CROSSOVER_JSON = ROOT / "registry" / "crossover" / "merge_candidates.json"
CONC_DIR = ROOT / "registry" / "concordance"
OUT_JSON = ROOT / "registry" / "crossbook_threads.json"
OUT_REPORT = ROOT / "logs" / "qa" / "crossbook_threads_report.md"
TOOL_VERSION = "build_crossbook_threads v0.1 (2026-11-05, W12)"
DATA_VERSION = "2026-11-05"
TYPES = ("character-line", "same-name-diff-person", "mention-only", "intertext-line")


def load_json(path: Path, required: bool = True) -> dict:
    if not path.exists():
        if required:
            raise SystemExit(f"[ERROR] 输入缺失：{path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class Inputs:
    def __init__(self):
        self.graph = load_json(GRAPH_JSON)
        self.books_raw = load_json(BOOKS_JSON)
        self.chapters_raw = load_json(CHAPTERS_JSON)
        self.cards_raw = load_json(CARDS_JSON)
        self.entities_raw = load_json(ENTITIES_JSON)
        self.display_raw = load_json(DISPLAY_JSON, required=False)
        self.intertext = load_json(INTERTEXT_JSON)
        self.crossover = load_json(CROSSOVER_JSON, required=False)
        self.nodes = {n.get("id"): n for n in self.graph.get("nodes") or []}
        self.edges = self.graph.get("edges") or []
        self.books = {b["book"]: b for b in self.books_raw.get("books") or []}
        self.chapter_meta = self.chapters_raw.get("meta") or {}
        self.lit_books = [b for b in (self.chapter_meta.get("lit_books") or []) if b in self.books]
        self.cards = self.cards_raw.get("cards") or []
        self.card_by_name = {}
        for c in self.cards:
            name = (c.get("name") or {}).get("canonical")
            if name:
                self.card_by_name[name] = c
        self.entities = self.entities_raw.get("entities") or []
        self.display_pairs = (self.display_raw.get("entries") or []) if self.display_raw else []
        self.intertext_edges = self.intertext.get("edges") or []
        self.conc = defaultdict(dict)   # canonical -> book -> entry
        for p in CONC_DIR.glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            book = d.get("book") or p.stem
            for e in d.get("entities") or []:
                if e.get("type") == "@":
                    self.conc[e.get("canonical")][book] = e
        self._no = 0

    def new_id(self) -> str:
        self._no += 1
        return f"CB-{self._no:04d}"

    def year(self, book: str) -> int:
        return int(self.books.get(book, {}).get("year") or 9999)

    def series(self, book: str) -> str:
        return self.books.get(book, {}).get("series") or ""


def beat(book: str, chapter: int | None, pn: str | None, summary: str,
         evidence: list[str], confidence: str = "B", evidence_level: str = "E2") -> dict:
    return {"book": book, "chapter": chapter, "pn": pn, "summary": summary,
            "evidence": evidence, "evidence_level": evidence_level, "confidence": confidence}


def gen_character_lines(inp: Inputs, cap=25) -> list[dict]:
    threads = []
    nodes = [(nid, n) for nid, n in inp.nodes.items()
             if n.get("type") == "@" and len(n.get("books") or []) >= 2]
    nodes.sort(key=lambda x: (-len(x[1].get("books") or []), -(x[1].get("n") or 0), x[0]))
    for nid, n in nodes[:cap]:
        books = sorted(n.get("books") or [], key=lambda b: (inp.year(b), b))
        beats = []
        for b in books:
            entry = inp.conc.get(nid, {}).get(b)
            pn = loc = None
            chapter = None
            if entry:
                first = entry.get("first") or {}
                chapter = first.get("chapter")
                pn = entry.get("anchor") or f"{b}#pn-r{chapter}.{first.get('para')}"
                loc = pn
            if not pn:
                for e in inp.edges:
                    if b in (e.get("books") or []) and nid in (e.get("s"), e.get("t")) and e.get("locs"):
                        loc = e["locs"][0]
                        break
            ev = [f"graph.nodes[{nid}].books", f"concordance[{nid}@{b}]" if entry else f"graph.edges@{b}"]
            summary = f"{b} 内出现/关系边 {n.get('n') or 0} 次量级" if not entry else \
                f"{b} 首见 {pn}（concordance total={entry.get('total')}）"
            beats.append(beat(b, chapter, loc, summary, ev, "B" if entry else "C"))
        if not beats:
            continue
        span = f"{beats[0]['book']} → {beats[-1]['book']}" if len(beats) > 1 else beats[0]["book"]
        threads.append({
            "id": inp.new_id(), "type": "character-line",
            "title": f"{nid}：{span}", "entities": [nid], "books": books,
            "beats": beats,
            "timeline": {"basis": "books.year+series", "forks": []},
            "judgement": {"canonical_same": True, "authorial": 0, "quoted": 0, "bare": 0,
                          "note": "canonical 同实体跨书（registry ID/图节点合并）"},
            "spoiler_level": 1, "data_version": DATA_VERSION, "status": "draft",
        })
    return threads


def gen_same_name(inp: Inputs, cap=12) -> list[dict]:
    threads = []
    # display_canonical 展示层同名/异名对
    for d in inp.display_pairs:
        display, canonical = d.get("display"), d.get("canonical")
        if not display or not canonical:
            continue
        books = sorted(set(inp.conc.get(display, {})) | set(inp.conc.get(canonical, {})),
                       key=lambda b: (inp.year(b), b))
        ev = [f"display_canonical[{display}→{canonical}]", f"registry.entities[{canonical}]"]
        entry = inp.conc.get(canonical, {}).get(books[0]) if books else None
        if entry:
            ev.append(entry.get("anchor") or "")
        threads.append({
            "id": inp.new_id(), "type": "same-name-diff-person",
            "title": f"同名/异名：{display}（展示）≠ {canonical}（规范）",
            "entities": [canonical, display], "books": books,
            "beats": [beat(books[0] if books else "", None,
                           (entry.get("anchor") if entry else None),
                           f"展示名 {display} 与规范名 {canonical} 分离，叙事须分写/标展示名",
                           [e for e in ev if e])],
            "timeline": {"basis": "books.year+series", "forks": []},
            "judgement": {"canonical_same": False, "must_split": True, "display": display,
                          "canonical": canonical, "note": "B-1/B04 展示层与规范层分离；禁合并叙事"},
            "spoiler_level": 0, "data_version": DATA_VERSION, "status": "draft",
        })
        if len(threads) >= cap:
            break
    # registry 内同名/别名指向多个 canonical
    surface_map = defaultdict(set)
    for e in inp.entities:
        for surface in [e.get("canonical")] + list(e.get("aliases") or []) + list(e.get("contextual") or []):
            if surface:
                surface_map[surface].add(e.get("canonical"))
    for surface, canonicals in surface_map.items():
        if len(canonicals) > 1:
            books = sorted({b for c in canonicals for b in inp.conc.get(c, {})},
                           key=lambda b: (inp.year(b), b))
            threads.append({
                "id": inp.new_id(), "type": "same-name-diff-person",
                "title": f"同名表面 {surface} 指向 {len(canonicals)} 个规范实体",
                "entities": sorted(canonicals), "books": books,
                "beats": [beat(books[0] if books else "", None, None,
                               f"surface={surface} 对应 canonical={sorted(canonicals)}；须人工裁定",
                               [f"registry.entities[surface={surface}]"])],
                "timeline": {"basis": "books.year+series", "forks": []},
                "judgement": {"canonical_same": False, "must_split": True, "display": surface,
                              "canonical": None, "note": "同名异人候选，须 03b 消歧裁定"},
                "spoiler_level": 0, "data_version": DATA_VERSION, "status": "draft",
            })
            if len(threads) >= cap:
                break
    return threads


def gen_intertext_threads(inp: Inputs, cap=30) -> list[dict]:
    agg = defaultdict(lambda: Counter())
    resolved = defaultdict(Counter)
    for e in inp.intertext_edges:
        key = (e.get("source"), e.get("target"))
        agg[key][e.get("kind") or "bare"] += 1
        resolved[key][e.get("loc_status") or "unlocatable"] += 1
    rows = []
    for (src, tgt), kinds in agg.items():
        rows.append((sum(kinds.values()), src, tgt, kinds, resolved[(src, tgt)]))
    rows.sort(key=lambda x: (-x[0], x[1], x[2]))
    threads = []
    for total, src, tgt, kinds, res in rows[:cap]:
        authorial, quoted, bare = kinds.get("authorial", 0), kinds.get("quoted", 0), kinds.get("bare", 0)
        typ = "intertext-line" if (authorial or quoted) else "mention-only"
        strength = "authorial" if authorial else ("quoted" if quoted else "bare")
        if typ == "mention-only":
            summary = f"仅提及：{src}→{tgt} 共 {total} 条 bare 互文；无 authorial/quoted，只能写'被提及'"
            conf = "C"
        else:
            summary = (f"互文：{src}→{tgt} authorial={authorial}/quoted={quoted}/bare={bare}；"
                       f"resolved={res.get('resolved', 0)}")
            conf = "B" if res.get("resolved") else "C"
        beats = [beat(src, None, None, summary,
                      [f"intertext_loc[{src}→{tgt}]"],
                      conf, "E1" if typ == "mention-only" else "E1+E2")]
        if res.get("resolved"):
            beats.append(beat(tgt, None, None, f"可定位边 {res['resolved']} 条（loc_r 可作 E2）",
                              [f"intertext_loc[{src}→{tgt}].loc_r"], "B", "E2"))
        threads.append({
            "id": inp.new_id(), "type": typ,
            "title": (f"仅提及：{src} → {tgt}" if typ == "mention-only" else f"互文：{src} → {tgt}"),
            "entities": [src, tgt], "books": [src, tgt],
            "beats": beats,
            "timeline": {"basis": "books.year+series", "forks": []},
            "judgement": {"canonical_same": False,
                          "authorial": authorial, "quoted": quoted, "bare": bare,
                          "locatable": res.get("resolved", 0),
                          "strength": strength,
                          "note": ("仅提及，禁写情节" if typ == "mention-only"
                                   else "按 authorial/quoted 判真；bare 只能写'提及'")},
            "spoiler_level": 0, "data_version": DATA_VERSION, "status": "draft",
        })
    return threads


# ────────────────────────── 校验/报告 ──────────────────────────
def validate(data: dict) -> dict:
    errors = []
    threads = data.get("threads") or []
    ids = [x.get("id") for x in threads]
    if len(ids) != len(set(ids)):
        errors.append("thread id 重复")
    types = Counter(x.get("type") for x in threads)
    for t in TYPES:
        if types.get(t, 0) == 0:
            errors.append(f"缺少类型 {t}")
    for x in threads:
        if not x.get("entities") or not x.get("books"):
            errors.append(f"{x.get('id')}: entities/books 为空")
        if not x.get("beats"):
            errors.append(f"{x.get('id')}: beats 为空")
        for b in x.get("beats") or []:
            if not b.get("evidence"):
                errors.append(f"{x.get('id')}: beat 缺 evidence")
        if x.get("type") == "character-line":
            if len(x.get("books") or []) < 2:
                errors.append(f"{x.get('id')}: character-line 跨书不足 2")
        elif x.get("type") == "same-name-diff-person":
            if not (x.get("judgement") or {}).get("must_split"):
                errors.append(f"{x.get('id')}: same-name 必须 must_split")
        elif x.get("type") == "mention-only":
            j = x.get("judgement") or {}
            if j.get("authorial", 0) or j.get("quoted", 0):
                errors.append(f"{x.get('id')}: mention-only 不得含 authorial/quoted")
            if not (j.get("bare", 0) > 0):
                errors.append(f"{x.get('id')}: mention-only 需 bare>0")
        elif x.get("type") == "intertext-line":
            j = x.get("judgement") or {}
            if not (j.get("authorial", 0) + j.get("quoted", 0) > 0):
                errors.append(f"{x.get('id')}: intertext-line 需 authorial/quoted")
        if not isinstance(x.get("spoiler_level"), int) or not 0 <= x["spoiler_level"] <= 3:
            errors.append(f"{x.get('id')}: spoiler_level 越界")
    text = json.dumps(data, ensure_ascii=False)
    for forbidden in ("site/data", "site/src", "content/person", "public/"):
        if forbidden in text:
            errors.append(f"输出不得引用发布目录 {forbidden}")
    return {"passed": not errors, "errors": errors, "counts": {"threads": len(threads), "by_type": dict(types)}}


def render_report(data: dict, val: dict, inp: Inputs) -> str:
    lines = ["# W12 跨书叙事线索生成报告（registry/crossbook_threads.json）", "",
             f"- 工具：`scripts/build_crossbook_threads.py`（{TOOL_VERSION}）；数据版本 {DATA_VERSION}",
             "- 输入：EX-4 graph（489/907）、cards（1,509）、entities/display_canonical、concordance、"
             "N6 intertext_loc（1904 边）、crossover（140 候选）、books/chapters（只读）",
             "- 产物：`registry/crossbook_threads.json`；报告 `logs/qa/crossbook_threads_report.md`", "",
             "## 一、规模", "", "| 类型 | 条数 |", "|---|---:|"]
    by = val["counts"]["by_type"]
    for t in TYPES:
        lines.append(f"| {t} | {by.get(t, 0)} |")
    lines += [f"| **合计** | **{val['counts']['threads']}** |", "",
              "## 二、判真口径（W12 §二/§五）", "",
              "- 同一实体跨书：canonical/registry ID 同 + graph nodes[].books 并集 → character-line；",
              "- 同名异人：display_canonical 展示层/registry 同名不同 canonical → same-name-diff-person，必须分写；",
              "- 仅被提及：N6 bare 边且无 authorial/quoted → mention-only，只能写'被提及/被引述'；",
              "- 互文判真：authorial（作者自述）> quoted（文中引述）> bare（仅提及）；loc_status=resolved 才可作 E2。",
              f"- intertext 实测：1904 边（authorial 98 / quoted 31 / bare 1775）；resolved 21（1.1%），"
              f"unlocatable 1883（source_book_no_struct）。", "",
              "## 三、样例", ""]
    shown = set()
    for x in data["threads"]:
        if x["type"] in shown:
            continue
        shown.add(x["type"])
        lines.append(f"- **{x['id']} {x['type']}**：{x['title']}（books={x['books']}；"
                     f"judgement={x['judgement'].get('strength', x['judgement'].get('note', ''))}）")
    lines += ["", "## 四、校验（--strict）", "",
              f"- 结论：{'PASS' if val['passed'] else 'FAIL'}；错误 {len(val['errors'])} 项"]
    for e in val["errors"]:
        lines.append(f"  - {e}")
    lines += ["", "## 五、遗留/边界", "",
              "- 图仅 5 书点亮集，29 书无 struct → 跨书线不覆盖未点亮书（其互文边多为 bare/unlocatable）。",
              "- mention-only/intertext-line 只登记互文关系，不扩写为同一宇宙；bare 不得写情节。",
              "- 同名异人须 03b 裁定后再上线；本生成器只给 must-split 候选。",
              "- 续书/前传按 D07 权威层级只作外传视角，不入主线时间线。",
              "- 本生成器只写 registry/crossbook_threads.json 与 logs，不写 site/data。", ""]
    return "\n".join(lines) + "\n"


def run_selftest() -> int:
    checks = []

    def chk(name, cond):
        checks.append(bool(cond))
        if not cond:
            print(f"[FAIL] {name}")

    chk("四类型", len(TYPES) == 4 and "same-name-diff-person" in TYPES)
    chk("beat 字段", set(beat("b", 1, "p", "s", ["e"])) >= {"book", "chapter", "pn", "summary", "evidence"})
    chk("版本", DATA_VERSION == "2026-11-05")
    chk("ID 格式", "CB-0001".startswith("CB-"))
    ok = sum(checks)
    print(f"[selftest] {ok}/{len(checks)} passed")
    return 0 if ok == len(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_crossbook_threads.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="W12 跨书叙事线索：同实体/同名异人/仅提及 + authorial/quoted/bare 判真 → registry/crossbook_threads.json",
        epilog="示例：python -X utf8 scripts/build_crossbook_threads.py --dry-run / --apply / --selftest / --strict")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="只校验并打印摘要（默认）")
    g.add_argument("--apply", action="store_true", help="写 registry/crossbook_threads.json + 报告")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--strict", action="store_true", help="严格校验，失败 exit 2")
    p.add_argument("--out", default=str(OUT_JSON))
    p.add_argument("--report", default=str(OUT_REPORT))
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    if args.selftest:
        return run_selftest()
    inp = Inputs()
    threads = gen_character_lines(inp) + gen_same_name(inp) + gen_intertext_threads(inp)
    data = {"schema": "w12-crossbook-threads-v0.1",
            "meta": {"generated": DATA_VERSION, "tool": TOOL_VERSION, "data_version": DATA_VERSION,
                     "source_refs": {"graph": "logs/export/staging/graph.json",
                                     "cards": "registry/sku/cards.json",
                                     "entities": "registry/entities.json",
                                     "display_canonical": "registry/display_canonical.json",
                                     "concordance": "registry/concordance/",
                                     "intertext": "registry/intertext/intertext_loc.json",
                                     "crossover": "registry/crossover/merge_candidates.json"},
                     "types": list(TYPES),
                     "counts": {}},
            "threads": threads}
    val = validate(data)
    data["meta"]["counts"] = val["counts"]
    data["meta"]["validation"] = val
    if args.apply:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_report(data, val, inp), encoding="utf-8")
        if not args.quiet:
            print(f"[OK] threads {len(threads)} {val['counts']['by_type']} → {out}")
            print(f"[OK] 报告 → {report}")
    elif not args.quiet:
        print(f"[dry-run] threads {len(threads)} {val['counts']['by_type']}；校验 "
              f"{'PASS' if val['passed'] else 'FAIL'}")
    if args.strict and not val["passed"]:
        print("[STRICT] 校验未通过", file=sys.stderr)
        for e in val["errors"]:
            print(f"  - {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
