#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""09c · 阅读路径生成器（S 组收尾⑥）

从已就绪数据生成四类阅读路径（main/theme/character/difficulty）：
  * books/chapters：`logs/export/staging/books.json`、`chapters.json`（EX-1 导出；只读）
  * graph：`logs/export/staging/graph.json`（EX-4；节点/边）
  * SKU 卡：`registry/sku/cards.json`（N10；人物卡 active_books/别名）
  * concordance：`registry/concordance/<书>.json`（人物活跃书/频次，卡数据不足时兜底）
  * 结构底本：`tagged/<书>/NNN.struct.md`（只读；章长/围栏块数；EX-1 field_gap：新管线无字数产物）

输出：
  * `registry/reading_paths.json`
  * `logs/qa/reading_paths_report.md`

规则（照 SKILL_09c）：
  * 四类路径：main（系列主线，按 year 升序）/ theme（专题，按事件/边密度）/
    character（角色线，按 active_books+出场回）/ difficulty（难度渐进，每档 3-5 回）
  * 难度 L1-L5（§四 五维公式）：
      raw = 0.20*z(L) + 0.25*z(P) + 0.25*z(E) + 0.15*z(V) + 0.15*z(X)
      D = quintile(raw)（按书内回目分位；<10 回用全点亮集 z）
      L=章长（去空白字符）、P=len(chars)、E=events/(L/1000)、
      V=sum(verbs)/(L/1000)、X=stream 实体在 graph.nodes[].books 的并集大小
  * spoiler_level 0-3：0 无剧透 / 1 轻度 / 2 中度 / 3 重度（结局/反转）
  * 未点亮 29 部：features="toc-only"，difficulty=null，reason="no_chapter_features"（§4.3 禁估难度）

CLI：
  python -X utf8 scripts/build_reading_paths.py                 # dry-run（默认，不写盘）
  python -X utf8 scripts/build_reading_paths.py --apply         # 落盘 registry/reading_paths.json + 报告
  python -X utf8 scripts/build_reading_paths.py --selftest      # 纯函数断言
  python -X utf8 scripts/build_reading_paths.py --strict --apply # 严格校验（失败 exit 2）
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS_JSON = ROOT / "logs" / "export" / "staging" / "books.json"
CHAPTERS_JSON = ROOT / "logs" / "export" / "staging" / "chapters.json"
GRAPH_JSON = ROOT / "logs" / "export" / "staging" / "graph.json"
MATCHES_JSON = ROOT / "logs" / "export" / "staging" / "matches.json"
CARDS_JSON = ROOT / "registry" / "sku" / "cards.json"
CONC_DIR = ROOT / "registry" / "concordance"
TAGGED = ROOT / "tagged"
OUT_JSON = ROOT / "registry" / "reading_paths.json"
OUT_REPORT = ROOT / "logs" / "qa" / "reading_paths_report.md"
TOOL_VERSION = "build_reading_paths v0.1 (2026-11-05, S/09c)"
DATA_VERSION = "2026-11-05"
BOOK_IDS = {"江湖三女侠": "jianghu", "七剑下天山": "qijian", "塞外奇侠传": "saiwai",
            "冰魄寒光剑": "bingpo", "白发魔女传": "bainv"}
LIT_BOOKS = ["七剑下天山", "冰魄寒光剑", "塞外奇侠传", "江湖三女侠", "白发魔女传"]
PATH_TYPES = ("main", "theme", "character", "difficulty")
SPOILER_CAP = 1
DIFF_WEIGHTS = {"L": 0.20, "P": 0.25, "E": 0.25, "V": 0.15, "X": 0.15}


# ────────────────────────── 加载 ──────────────────────────
def load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"[ERROR] 输入缺失：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def book_id(book: str) -> str:
    return BOOK_IDS.get(book, "b" + str(abs(hash(book)) % 100000))


def pn(book: str, no: int) -> str:
    return f"{book}#pn-r{no}"


def short_name(name: str) -> str:
    """人物显示名归一（去常见职衔后缀，用于 graph/章节 chars 匹配）。"""
    for suffix in ("提督", "总兵", "将军", "大人", "先生", "姑娘", "小姐", "公子", "和尚", "道人"):
        if len(name) > len(suffix) + 1 and name.endswith(suffix):
            return name[: -len(suffix)]
    return name


class Inputs:
    def __init__(self):
        self.books_raw = load_json(BOOKS_JSON)
        self.chapters_raw = load_json(CHAPTERS_JSON)
        self.graph = load_json(GRAPH_JSON)
        self.cards_raw = load_json(CARDS_JSON)
        self.matches_raw = load_json(MATCHES_JSON) if MATCHES_JSON.exists() else {"matches": []}
        self.books = {b["book"]: b for b in self.books_raw.get("books") or []}
        self.chapter_meta = self.chapters_raw.get("meta") or {}
        self.lit_books = [b for b in (self.chapter_meta.get("lit_books") or LIT_BOOKS) if b in self.books]
        self.book_chapters = {}
        for b in self.books:
            entry = self.chapters_raw.get(b) or {}
            self.book_chapters[b] = list(entry.get("chapters") or [])
        self.cards = self.cards_raw.get("cards") or []
        self.person_cards = [c for c in self.cards if c.get("meta", {}).get("card_type") == "person"]
        self.card_by_canon = {c.get("name", {}).get("canonical"): c for c in self.person_cards}
        self.spotlight = {n.get("id"): n for n in self.graph.get("nodes") or []}
        self.graph_nodes = self.graph.get("nodes") or []
        self.graph_edges = self.graph.get("edges") or []
        self.matches = self.matches_raw.get("matches") or []
        self.edge_kinds = {}
        for e in self.graph_edges:
            s, t = e.get("s"), e.get("t")
            if s and t:
                self.edge_kinds.setdefault(tuple(sorted((s, t))), set()).add(e.get("kind"))
        self.book_year = {b: (rec.get("year") or 9999, rec.get("book")) for b, rec in self.books.items()}

    def is_lit(self, book: str) -> bool:
        return book in self.lit_books

    def sorted_lit(self) -> list[str]:
        return sorted(self.lit_books, key=lambda b: self.book_year.get(b, (9999, b)))


def struct_stats(book: str, no: int) -> tuple[int, int]:
    """(章长=去空白字符数, 围栏块数)；struct 缺失时 0（报告计入 field_gap）。"""
    path = TAGGED / book / f"{no:03d}.struct.md"
    if not path.exists():
        return 0, 0
    chars, fences = 0, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# [0]"):
            continue
        if line.startswith(":::"):
            if line[3:].strip():
                fences += 1
            continue
        m = re.match(r"^\[\d+\] ", line)
        text = line[m.end():] if m else line
        chars += len(re.sub(r"\s", "", text))
    return chars, fences


# ────────────────────────── 难度（09c §四） ──────────────────────────
def zscore(xs: list[float], x: float) -> float:
    if not xs:
        return 0.0
    mu = statistics.fmean(xs)
    sd = statistics.pstdev(xs) if len(xs) > 1 else 0.0
    return 0.0 if sd == 0 else (x - mu) / sd


def quintile(values: list[float], x: float) -> int:
    """1..5 分位档（升序；同值同档，最大值归 5）。"""
    if not values:
        return 1
    vals = sorted(values)
    if len(vals) == 1:
        return 3
    le = sum(1 for v in vals if v <= x)
    rank = (le - 1) / (len(vals) - 1)
    return max(1, min(5, 1 + int(rank * 5)))


def spoiler_level(no: int, max_no: int) -> int:
    """结局锁定：末回 3；楔子 0；按进度 0→0/1/2。"""
    if no <= 0:
        return 0
    if max_no and no >= max_no:
        return 3
    frac = no / max_no if max_no else 0
    if frac <= 0.2:
        return 0
    if frac <= 0.6:
        return 1
    if frac <= 0.9:
        return 2
    return 3


# ────────────────────────── 章节事实与难度 ──────────────────────────
def build_chapter_facts(inp: Inputs) -> dict:
    facts: dict[str, dict] = {}
    graph_books = {}
    for n in inp.graph_nodes:
        names = set()
        nid = n.get("id")
        if nid:
            names.add(nid)
            names.add(short_name(nid))
        for nm in names:
            graph_books.setdefault(nm, set()).update(n.get("books") or [])
    for book in inp.lit_books:
        chs = [c for c in inp.book_chapters.get(book, [])]
        max_no = max((c.get("no") or 0) for c in chs) if chs else 0
        recs = []
        for c in chs:
            no = int(c.get("no") or 0)
            chars = len({ch.get("name") for ch in (c.get("chars") or []) if ch.get("name")})
            events = int(c.get("events") or 0)
            verbs = c.get("verbs") or {}
            verb_n = sum(int(v or 0) for v in verbs.values() if isinstance(v, (int, float)))
            length, fences = struct_stats(book, no)
            stream = c.get("stream") or []
            books_union = set()
            for item in stream:
                for key in ("s", "o"):
                    name = item.get(key)
                    if not name:
                        continue
                    books_union |= graph_books.get(name, set()) or graph_books.get(short_name(name), set())
            rec = {
                "chapter": no, "title": c.get("title") or "",
                "length": length, "events": events, "entities": chars,
                "verbs": verb_n, "fences": fences, "stream": stream,
                "stream_books": len(books_union),
            }
            rec["E"] = events / (length / 1000) if length else 0.0
            rec["V"] = verb_n / (length / 1000) if length else 0.0
            recs.append(rec)
        facts[book] = {"chapters": recs, "max_no": max_no}
    return facts


def assign_difficulty(inp: Inputs, facts: dict) -> dict:
    all_raw = []
    for book, info in facts.items():
        for rec in info["chapters"]:
            rec["_raw"] = None
    # 先算各书 z 所需的分书统计（n<10 用全局）
    per_book_stats = {}
    for book, info in facts.items():
        recs = info["chapters"]
        per_book_stats[book] = {
            k: [r[k] for r in recs if r.get(k) is not None] for k in ("length", "entities", "E", "V", "stream_books")
        }
    global_stats = {k: [r[k] for info in facts.values() for r in info["chapters"]]
                    for k in ("length", "entities", "E", "V", "stream_books")}
    for book, info in facts.items():
        recs = info["chapters"]
        n = len(recs)
        stats = per_book_stats[book] if n >= 10 else global_stats
        for rec in recs:
            raw = (DIFF_WEIGHTS["L"] * zscore(stats["length"], rec["length"])
                   + DIFF_WEIGHTS["P"] * zscore(stats["entities"], rec["entities"])
                   + DIFF_WEIGHTS["E"] * zscore(stats["E"], rec["E"])
                   + DIFF_WEIGHTS["V"] * zscore(stats["V"], rec["V"])
                   + DIFF_WEIGHTS["X"] * zscore(stats["stream_books"], rec["stream_books"]))
            rec["_raw"] = round(raw, 6)
            all_raw.append(raw)
        raws = [r["_raw"] for r in recs]
        for rec in recs:
            rec["difficulty"] = quintile(raws, rec["_raw"])
            rec["spoiler_level"] = spoiler_level(rec["chapter"], info["max_no"])
        info["boundaries"] = {
            "q20": round(_quantile(raws, 0.2), 6), "q40": round(_quantile(raws, 0.4), 6),
            "q60": round(_quantile(raws, 0.6), 6), "q80": round(_quantile(raws, 0.8), 6),
        }
    return facts


def _quantile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    vals = sorted(xs)
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(vals) - 1)
    frac = pos - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


# ────────────────────────── 路径构建 ──────────────────────────
def _step(book: str, no: int, features: str, difficulty, spoiler, codes: list[str],
          evidence: dict | None = None) -> dict:
    return {"book": book, "chapter": no, "pn": pn(book, no),
            "difficulty": difficulty, "spoiler_level": spoiler,
            "features": features,
            "reason": {"codes": codes, "evidence": evidence or {}}}


def build_paths(inp: Inputs, facts: dict) -> dict:
    index = {}
    for book, info in facts.items():
        for rec in info["chapters"]:
            index[(book, rec["chapter"])] = rec
    paths = []

    # ① main：含点亮书的系列，按 year 升序（未点亮书 toc-only）
    lit_series = sorted({inp.books[b].get("series") or "" for b in inp.lit_books if b in inp.books})
    for series in lit_series:
        if not series:
            continue
        members = [b for b, rec in inp.books.items() if (rec.get("series") or "") == series]
        members.sort(key=lambda b: (inp.books[b].get("year") or 9999, inp.books[b].get("book") or b))
        if not any(inp.is_lit(b) for b in members):
            continue
        steps = []
        for b in members:
            recs = [r for r in facts.get(b, {}).get("chapters", [])]
            if inp.is_lit(b) and recs:
                first = min(recs, key=lambda r: r["chapter"])
                steps.append(_step(b, first["chapter"], "full", first["difficulty"], 0,
                                   ["series_anchor"] if len(steps) == 0 else ["sequential", "series_bridge"],
                                   {"series": series, "year": inp.book_year.get(b, (None,))[0]}))
            else:
                steps.append(_step(b, 0, "toc-only", None, 0, ["series_bridge"],
                                   {"series": series, "note": "未点亮：仅目录级信息（09c §4.3）"}))
        paths.append({
            "id": "path-main-" + _slug(series), "type": "main",
            "title": f"{series}主线（按成书年升序；已点亮 {sum(1 for b in members if inp.is_lit(b))} 部）",
            "steps": steps,
            "constraints": {"max_books": len(members), "spoiler_cap": SPOILER_CAP},
            "enabled": True,
        })

    # ② theme：按 graph 边 kind/章节 stream 命中
    themes = [
        ("师承与门派", {"师承", "同门", "任职"}, {"拜", "收", "传", "授", "教", "学"}),
        ("情缘与结义", {"婚约", "结义", "收养", "解救"}, {"娶", "嫁", "婚", "许", "结拜"}),
        ("对决与仇怨", {"交手", "杀害", "点穴", "押送"}, {"斗", "战", "杀", "刺", "打", "胜", "败"}),
    ]
    for theme_name, kinds, verbs in themes:
        scored = []
        for book, info in facts.items():
            for rec in info["chapters"]:
                hits = 0
                for item in rec["stream"]:
                    pair = tuple(sorted((item.get("s"), item.get("o"))))
                    edge_kind = inp.edge_kinds.get(pair, set())
                    if edge_kind & kinds:
                        hits += 1
                    elif any(v in (item.get("v") or "") for v in verbs):
                        hits += 1
                if hits:
                    scored.append((hits, book, rec))
        if not scored:
            continue
        scored.sort(key=lambda x: (-x[0], inp.book_year.get(x[1], (9999,))[0], x[2]["chapter"]))
        picks, seen = [], set()
        for hits, book, rec in scored:
            if (book, rec["chapter"]) in seen:
                continue
            seen.add((book, rec["chapter"]))
            picks.append(_step(book, rec["chapter"], "full", rec["difficulty"], 1,
                               ["theme_match"], {"theme": theme_name, "matched_streams": hits}))
            if len(picks) >= 5:
                break
        paths.append({
            "id": "path-theme-" + _slug(theme_name), "type": "theme",
            "title": f"专题阅读：{theme_name}（事件/关系密度优先）",
            "steps": picks,
            "constraints": {"max_books": 3, "spoiler_cap": SPOILER_CAP},
            "enabled": True,
        })

    # ③ character：角色卡 × 章节 chars（按 active_books 排序）
    char_candidates = []
    for card in inp.person_cards:
        canon = card.get("name", {}).get("canonical") or ""
        active = [b for b in (card.get("active_books") or []) if b in inp.lit_books]
        node = inp.spotlight.get(canon) or {}
        n = int(node.get("n") or 0)
        names = {canon} | {a.get("surface") for a in (card.get("aliases") or []) if a.get("surface")}
        names |= {short_name(x) for x in names}
        hits_total = 0
        for book in active:
            for rec in facts.get(book, {}).get("chapters", []):
                chs = inp.book_chapters.get(book, [])
                raw = next((c for c in chs if int(c.get("no") or 0) == rec["chapter"]), {})
                char_names = {ch.get("name") for ch in (raw.get("chars") or [])}
                if char_names & names:
                    hits_total += 1
        if hits_total:
            char_candidates.append((n + 100 * len(active) + hits_total, canon, card, names, active))
    char_candidates.sort(key=lambda x: (-x[0], x[1]))
    for score, canon, card, names, active in char_candidates[:8]:
        steps = []
        for book in sorted(active, key=lambda b: inp.book_year.get(b, (9999,))[0]):
            raw_chs = sorted(inp.book_chapters.get(book, []), key=lambda c: int(c.get("no") or 0))
            for raw in raw_chs:
                no = int(raw.get("no") or 0)
                char_names = {ch.get("name") for ch in (raw.get("chars") or [])}
                if not (char_names & names):
                    continue
                rec = index.get((book, no))
                if not rec:
                    continue
                steps.append(_step(book, no, "full", rec["difficulty"], 1,
                                   ["character_arc"], {"card": card["meta"].get("stable_id")}))
                if len(steps) >= 8:
                    break
            if len(steps) >= 8:
                break
        if not steps:
            continue
        paths.append({
            "id": "path-character-" + _slug(canon), "type": "character",
            "title": f"角色线：{canon}（{len(steps)} 回，跨 {len(active)} 部）",
            "steps": steps,
            "constraints": {"max_books": max(1, len(active)), "spoiler_cap": SPOILER_CAP},
            "enabled": True,
        })

    # ④ difficulty：每部点亮书 L1→L5，每档 3-5 回（结局回不入）
    for book in inp.sorted_lit():
        info = facts.get(book)
        if not info:
            continue
        steps = []
        for d in (1, 2, 3, 4, 5):
            pick = [r for r in info["chapters"] if r["difficulty"] == d and r["spoiler_level"] <= SPOILER_CAP]
            pick.sort(key=lambda r: r["chapter"])
            for rec in pick[:4]:
                steps.append(_step(book, rec["chapter"], "full", d, rec["spoiler_level"],
                                   ["difficulty_step"], {"level": d}))
        if not steps:
            continue
        paths.append({
            "id": "path-difficulty-" + book_id(book), "type": "difficulty",
            "title": f"《{book}》难度渐进（L1→L5；每档 3-4 回）",
            "steps": steps,
            "constraints": {"max_books": 1, "spoiler_cap": SPOILER_CAP},
            "enabled": True,
        })

    # 章节索引（阅读器按需查难度/剧透）
    chapter_index = {}
    for book in inp.sorted_lit():
        recs = facts.get(book, {}).get("chapters", [])
        chapter_index[book] = [{
            "chapter": r["chapter"], "title": r["title"], "difficulty": r["difficulty"],
            "spoiler_level": r["spoiler_level"], "features": "full",
            "metrics": {"L": r["length"], "P": r["entities"], "E": round(r["E"], 4),
                        "V": round(r["V"], 4), "X": r["stream_books"], "fences": r["fences"],
                        "events": r["events"]},
        } for r in recs]

    # 下一章/跳读/预警（09c §3.3；每部点亮书一条）
    recommendations = []
    for book in inp.sorted_lit():
        recs = [r for r in facts.get(book, {}).get("chapters", []) if r["chapter"] > 0]
        if not recs:
            continue
        cur = recs[len(recs) // 2]
        nxt = next((r for r in recs if r["chapter"] == cur["chapter"] + 1), None)
        skips = [r for r in recs if r["events"] <= 1 and r["spoiler_level"] <= SPOILER_CAP][:3]
        warns = []
        for a, b in zip(recs, recs[1:]):
            if abs(b["difficulty"] - a["difficulty"]) >= 2:
                warns.append({"chapter": b["chapter"], "kind": "difficulty_spike",
                              "evidence": {"difficulty": b["difficulty"],
                                           "delta": b["difficulty"] - a["difficulty"]}})
            if len(warns) >= 3:
                break
        recommendations.append({
            "book": book,
            "current": {"chapter": cur["chapter"], "pn": pn(book, cur["chapter"])},
            "next": ({"chapter": nxt["chapter"], "difficulty": nxt["difficulty"],
                      "reason_codes": ["sequential", "difficulty_step"]} if nxt else None),
            "skip_candidates": [{"chapter": r["chapter"], "reason_codes": ["low_event_density"],
                                 "evidence": {"events": r["events"]}} for r in skips],
            "warnings": warns,
            "spoiler_level": 0,
        })

    # 未点亮 29 部：toc-only
    unlit = []
    for book, rec in sorted(inp.books.items(), key=lambda kv: (kv[1].get("series") or "", kv[1].get("year") or 9999)):
        if inp.is_lit(book):
            continue
        unlit.append({
            "book": book, "series": rec.get("series"), "year": rec.get("year"),
            "leads": rec.get("leads") or [], "features": "toc-only",
            "difficulty": None, "spoiler_level": 0,
            "reason_codes": ["no_chapter_features"],
            "reason": "未点亮：仅目录级信息，不估难度（09c §4.3）",
        })
    return {"paths": paths, "chapter_index": chapter_index,
            "recommendations": recommendations, "unlit_books": unlit,
            "facts": facts, "lit_series": lit_series}


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in text).strip("-").lower() or "x"


# ────────────────────────── 校验/报告 ──────────────────────────
def validate(data: dict, inp: Inputs) -> dict:
    errors = []
    paths = data.get("paths") or []
    ids = [p.get("id") for p in paths]
    if len(ids) != len(set(ids)):
        errors.append("path id 重复")
    for p in paths:
        if p.get("type") not in PATH_TYPES:
            errors.append(f"{p.get('id')}: 非法 type")
        steps = p.get("steps") or []
        if not steps:
            errors.append(f"{p.get('id')}: steps 为空")
        for s in steps:
            if s.get("book") not in inp.books:
                errors.append(f"{p.get('id')}: book 不存在 {s.get('book')}")
            if s.get("features") == "full":
                if not isinstance(s.get("difficulty"), int) or not 1 <= s["difficulty"] <= 5:
                    errors.append(f"{p.get('id')}: full step difficulty 越界")
            elif s.get("features") == "toc-only":
                if s.get("difficulty") is not None:
                    errors.append(f"{p.get('id')}: toc-only 不应有 difficulty")
            else:
                errors.append(f"{p.get('id')}: features 非法")
            if not isinstance(s.get("spoiler_level"), int) or not 0 <= s["spoiler_level"] <= 3:
                errors.append(f"{p.get('id')}: spoiler_level 越界")
        if p.get("type") == "difficulty":
            levels = {s.get("difficulty") for s in steps if s.get("features") == "full"}
            if len(levels) < 3:
                errors.append(f"{p.get('id')}: 难度渐进档位不足（{sorted(levels)}）")
    unlit = data.get("unlit_books") or []
    if len(unlit) != 29:
        errors.append(f"unlit_books 数量应为 29，实际 {len(unlit)}")
    if any(b.get("features") != "toc-only" or b.get("difficulty") is not None for b in unlit):
        errors.append("unlit_books 存在非 toc-only/带 difficulty 条目")
    if len(data.get("chapter_index") or {}) != len(inp.lit_books):
        errors.append("chapter_index 未覆盖全部点亮书")
    counts = {}
    for p in paths:
        counts[p["type"]] = counts.get(p["type"], 0) + 1
    for t in PATH_TYPES:
        if counts.get(t, 0) == 0:
            errors.append(f"缺少路径类型 {t}")
    text = json.dumps(data, ensure_ascii=False)
    if "site/" in text:
        errors.append("输出不得引用 site/ 发布目录")
    return {"passed": not errors, "errors": errors, "counts": counts}


def render_report(data: dict, inp: Inputs, val: dict, stats: dict) -> str:
    lines, add = [], None
    add = lines.append
    add("# 09c 阅读路径生成报告（registry/reading_paths.json）")
    add("")
    add(f"- 工具：`scripts/build_reading_paths.py`（{TOOL_VERSION}）；数据版本：{DATA_VERSION}")
    add(f"- 输入：books/chapters（EX-1 staging）、graph（EX-4）、SKU 卡、concordance、tagged/struct（只读）")
    add(f"- 产物：`registry/reading_paths.json`；本报告 `logs/qa/reading_paths_report.md`")
    add("")
    add("## 一、规模")
    add("")
    add("| 项 | 数量 |")
    add("|---|---:|")
    add(f"| 路径总数 | {len(data['paths'])} |")
    counts = {}
    for p in data["paths"]:
        counts[p["type"]] = counts.get(p["type"], 0) + 1
    for t in PATH_TYPES:
        add(f"| {t} | {counts.get(t, 0)} |")
    add(f"| steps 总数 | {sum(len(p['steps']) for p in data['paths'])} |")
    add(f"| 点亮书/章 | {len(inp.lit_books)} / {sum(len(v['chapters']) for v in data['facts'].values())} |")
    add(f"| 未点亮 toc-only | {len(data['unlit_books'])} |")
    add(f"| 章节索引 | {sum(len(v) for v in data['chapter_index'].values())} 章 |")
    add(f"| 推荐条目（下一章/跳读/预警） | {len(data['recommendations'])} |")
    add("")
    add("## 二、难度公式与边界（09c §四）")
    add("")
    add("```text")
    add("raw = 0.20*z(L) + 0.25*z(P) + 0.25*z(E) + 0.15*z(V) + 0.15*z(X)")
    add("D   = quintile(raw)  # 书内回目分位；<10 回用全点亮集 z-score")
    add("L=章长(去空白字符) P=len(chars) E=events/(L/1000) V=sum(verbs)/(L/1000)")
    add("X=stream 实体在 graph.nodes[].books 的并集大小")
    add("```")
    add("")
    add("| 书 | 章数 | D 分布 L1/L2/L3/L4/L5 | raw 分位边界 q20/q40/q60/q80 |")
    add("|---|---:|---|---|")
    for book in inp.sorted_lit():
        recs = data["facts"][book]["chapters"]
        dist = [sum(1 for r in recs if r["difficulty"] == d) for d in (1, 2, 3, 4, 5)]
        b = data["facts"][book].get("boundaries") or {}
        add(f"| {book} | {len(recs)} | {'/'.join(map(str, dist))} | "
            f"{b.get('q20')}/{b.get('q40')}/{b.get('q60')}/{b.get('q80')} |")
    add("")
    add("## 三、剧透分级（09c §5.1）")
    add("")
    add("| level | 含义 | 出现章节数 |")
    add("|---|---|---:|")
    sp = [0, 0, 0, 0]
    for info in data["facts"].values():
        for r in info["chapters"]:
            sp[r["spoiler_level"]] += 1
    labels = {0: "无剧透（结构/回目）", 1: "轻度（关系/归属）", 2: "中度（胜负/生死）", 3: "重度（结局/反转）"}
    for k in (0, 1, 2, 3):
        add(f"| {k} | {labels[k]} | {sp[k]} |")
    add("")
    add("> 规则：楔子 0；按回目进度 ≤20%→0、≤60%→1、≤90%→2；末回/结局→3。难度路径不入 spoiler>1 的回。")
    add("")
    add("## 四、路径清单")
    add("")
    add("| id | type | 标题 | steps | spoiler_max |")
    add("|---|---|---|---:|---:|")
    for p in data["paths"]:
        add(f"| {p['id']} | {p['type']} | {p['title']} | {len(p['steps'])} | "
            f"{max(s['spoiler_level'] for s in p['steps'])} |")
    add("")
    add("## 五、未点亮 29 部（toc-only）")
    add("")
    add("| 书 | 系列 | 年 | 处理 |")
    add("|---|---|---|---|")
    for b in data["unlit_books"]:
        add(f"| {b['book']} | {b.get('series')} | {b.get('year')} | toc-only / difficulty=null / no_chapter_features |")
    add("")
    add("## 六、校验（--strict）")
    add("")
    add(f"- 结论：{'PASS' if val['passed'] else 'FAIL'}；错误 {len(val['errors'])} 项；类型分布 {val['counts']}")
    for e in val["errors"]:
        add(f"  - {e}")
    add("")
    add("## 七、遗留/边界")
    add("")
    add("- 章长/围栏数取自 struct（EX-1 field_gap：新管线无章节字数产物）；struct 缺失章节按 0 计并在 metrics 可见。")
    add("- 角色线依赖 SKU 人物卡 active_books 与 chapters[].chars；未匹配到章节的角色不出路径（宁缺勿造）。")
    add("- 未点亮 29 部不估难度；toc-only 仅目录级。")
    add("- 本生成器只写 registry/reading_paths.json 与 logs，不写 site/data。")
    add("")
    return "\n".join(lines) + "\n"


# ────────────────────────── selftest / CLI ──────────────────────────
def run_selftest() -> int:
    checks = []

    def chk(name, cond):
        checks.append(bool(cond))
        if not cond:
            print(f"[FAIL] {name}")

    chk("权重和=1", abs(sum(DIFF_WEIGHTS.values()) - 1.0) < 1e-9)
    chk("quintile 最小", quintile([0, 1, 2, 3, 4], -1) == 1)
    chk("quintile 最大", quintile([0, 1, 2, 3, 4], 10) == 5)
    chk("quintile 中间", quintile([0, 1, 2, 3, 4], 2) == 3)
    chk("zscore 零方差", zscore([1, 1, 1], 1) == 0)
    chk("spoiler 楔子", spoiler_level(0, 40) == 0)
    chk("spoiler 末回", spoiler_level(40, 40) == 3)
    chk("spoiler 早期", spoiler_level(2, 40) == 0)
    chk("spoiler 中期", spoiler_level(20, 40) == 1)
    chk("pn 格式", pn("七剑下天山", 1) == "七剑下天山#pn-r1")
    chk("slug", _slug("师承与门派") != "")
    chk("类型集合", set(PATH_TYPES) == {"main", "theme", "character", "difficulty"})
    chk("剧透上限", SPOILER_CAP == 1)
    chk("书 ID", set(BOOK_IDS.values()) == {"jianghu", "qijian", "saiwai", "bingpo", "bainv"})
    ok = sum(checks)
    print(f"[selftest] {ok}/{len(checks)} passed")
    return 0 if ok == len(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_reading_paths.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="09c 阅读路径生成：从 books/chapters/graph/SKU 卡生成 main/theme/character/difficulty 四类路径，"
                    "L1-L5 难度五维公式派生，spoiler_level 0-3，未点亮 29 部 toc-only。",
        epilog="示例：python -X utf8 scripts/build_reading_paths.py --dry-run\n"
               "      python -X utf8 scripts/build_reading_paths.py --apply\n"
               "      python -X utf8 scripts/build_reading_paths.py --selftest",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="只校验并打印摘要（默认行为）")
    g.add_argument("--apply", action="store_true", help="写 registry/reading_paths.json + 报告")
    p.add_argument("--selftest", action="store_true", help="纯函数自检")
    p.add_argument("--strict", action="store_true", help="严格校验，失败 exit 2")
    p.add_argument("--out", default=str(OUT_JSON), help="JSON 输出路径（默认 registry/reading_paths.json）")
    p.add_argument("--report", default=str(OUT_REPORT), help="报告输出路径")
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
    facts = assign_difficulty(inp, build_chapter_facts(inp))
    built = build_paths(inp, facts)
    val = validate({"paths": built["paths"], "chapter_index": built["chapter_index"],
                    "unlit_books": built["unlit_books"], "recommendations": built["recommendations"]}, inp)
    meta = {
        "generated": DATA_VERSION,
        "tool": TOOL_VERSION,
        "data_version": DATA_VERSION,
        "source_refs": {
            "books": str(BOOKS_JSON.relative_to(ROOT)), "chapters": str(CHAPTERS_JSON.relative_to(ROOT)),
            "graph": str(GRAPH_JSON.relative_to(ROOT)), "cards": str(CARDS_JSON.relative_to(ROOT)),
            "concordance": "registry/concordance/", "struct": "tagged/<书>/NNN.struct.md",
        },
        "source_generated": {
            "books": inp.books_raw.get("meta", {}).get("generated"),
            "chapters": inp.chapter_meta.get("generated"),
            "graph": inp.graph.get("meta", {}).get("generated"),
            "cards": inp.cards_raw.get("meta", {}).get("generated_at"),
        },
        "difficulty_formula": ("raw=0.20*z(L)+0.25*z(P)+0.25*z(E)+0.15*z(V)+0.15*z(X); "
                               "D=quintile(raw) within book (n<10 fallback to all lit chapters); "
                               "L=non-space chars (struct), P=len(chars), E=events/(L/1000), "
                               "V=sum(verbs)/(L/1000), X=union books of stream entities in graph.nodes"),
        "spoiler_rule": "楔子 0；按回目进度 ≤20%→0、≤60%→1、≤90%→2；末回→3（09c §5.1）",
        "difficulty_boundaries": {b: data.get("boundaries") for b, data in facts.items()},
        "counts": {"paths": len(built["paths"]),
                   "by_type": {t: sum(1 for p in built["paths"] if p["type"] == t) for t in PATH_TYPES},
                   "steps": sum(len(p["steps"]) for p in built["paths"]),
                   "unlit_books": len(built["unlit_books"]),
                   "chapter_index": sum(len(v) for v in built["chapter_index"].values())},
        "validation": val,
    }
    data = {"schema": "reading-paths-v0.1", "meta": meta,
            "paths": built["paths"], "chapter_index": built["chapter_index"],
            "recommendations": built["recommendations"],
            "unlit_books": built["unlit_books"]}
    if args.apply:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_report({**data, "facts": facts}, inp, val, meta["counts"]),
                          encoding="utf-8")
        if not args.quiet:
            print(f"[OK] 路径 {len(data['paths'])}（main/theme/character/difficulty="
                  f"{meta['counts']['by_type']}）→ {out}")
            print(f"[OK] 报告 → {report}")
    else:
        if not args.quiet:
            print(f"[dry-run] 路径 {len(data['paths'])} {meta['counts']['by_type']}；"
                  f"toc-only {len(data['unlit_books'])}；校验 {'PASS' if val['passed'] else 'FAIL'}")
    if args.strict and not val["passed"]:
        print("[STRICT] 校验未通过", file=sys.stderr)
        for e in val["errors"]:
            print(f"  - {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
