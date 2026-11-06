#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""09b · 游戏化关卡/成就/进度生成器（S 组收尾⑥）

输入（只读）：
  * `logs/export/staging/graph.json`（EX-4；489 节点 / 907 边）
  * `registry/sku/cards.json`（N10；1,509 卡）
  * `logs/export/staging/matches.json`（EX-5；341 场对局）+ `ratings.json`（Glicko-2）
  * `logs/export/staging/books.json` / `chapters.json`（EX-1；回目/事件/实体）
  * `tagged/<书>/NNN.struct.md`（只读；围栏块数/章长）

输出：
  * `registry/game/levels.json`（level / achievement / progress / sim schema）
  * `logs/qa/game_levels_report.md`

公式（SKILL_09b §五；禁手填）：
  章节难度 D ∈ [1,5]：
    raw = 0.4*events + 0.3*entities + 0.2*fences + 0.1*(chars/median_chars)
    D   = 1 + 4*pct_rank(raw)   # 全点亮集 151 章分位；分母写入 difficulty_basis
  成就阈值三档（k=0.1/0.3/0.6）：
    收集类 count = round(该类卡总量*k)；事件类 ≤ 该类事件总数；关系类 ≤ 图内该类 kind 边数
  推演 p_a（Glicko-2 expected score）：
    p_a = 1/(1+10^(-(r_a-r_b)/400))；basis 必须含 ratings 与 matches.json 的 h2h 实计数

铁律：只用已有 kind 的边、只回放已抽取 341 场对局、不补写未抽取场次；任何输入缺失 → p_a:null 降级，
不估数；`simulate:true`；progress 只本地；不写 site/data/content/public。

CLI：
  python -X utf8 scripts/build_game_levels.py                 # dry-run（默认，不写盘）
  python -X utf8 scripts/build_game_levels.py --apply         # 落盘 registry/game/levels.json + 报告
  python -X utf8 scripts/build_game_levels.py --selftest
  python -X utf8 scripts/build_game_levels.py --strict --apply # 严格校验（失败 exit 2）
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "logs" / "export" / "staging"
BOOKS_JSON = STAGING / "books.json"
CHAPTERS_JSON = STAGING / "chapters.json"
GRAPH_JSON = STAGING / "graph.json"
MATCHES_JSON = STAGING / "matches.json"
RATINGS_JSON = STAGING / "ratings.json"
CARDS_JSON = ROOT / "registry" / "sku" / "cards.json"
TAGGED = ROOT / "tagged"
OUT_JSON = ROOT / "registry" / "game" / "levels.json"
OUT_REPORT = ROOT / "logs" / "qa" / "game_levels_report.md"
TOOL_VERSION = "build_game_levels v0.1 (2026-11-05, S/09b)"
DATA_VERSION = "2026-11-05"
BOOK_IDS = {"江湖三女侠": "jianghu", "七剑下天山": "qijian", "塞外奇侠传": "saiwai",
            "冰魄寒光剑": "bingpo", "白发魔女传": "bainv"}
LIT_BOOKS = ["七剑下天山", "冰魄寒光剑", "塞外奇侠传", "江湖三女侠", "白发魔女传"]
LEVEL_TYPES = ("chapter", "relation", "person", "match")
OBJECTIVE_KINDS = {"identify", "connect", "collect", "resolve", "replay"}
TIER_K = (("bronze", 0.1), ("silver", 0.3), ("gold", 0.6))


def load_json(path: Path, required: bool = True) -> dict:
    if not path.exists():
        if required:
            raise SystemExit(f"[ERROR] 输入缺失：{path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def book_id(book: str) -> str:
    return BOOK_IDS.get(book, "b" + str(abs(hash(book)) % 100000))


def short_name(name: str) -> str:
    for suffix in ("提督", "总兵", "将军", "大人", "先生", "姑娘", "小姐", "公子", "和尚", "道人"):
        if len(name) > len(suffix) + 1 and name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def struct_stats(book: str, no: int) -> tuple[int, int]:
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


def pct_rank(values: list[float], x: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return 0.5
    le = sum(1 for v in values if v <= x)
    return (le - 1) / (len(values) - 1)


def difficulty_from_rank(values: list[float], x: float) -> int:
    return max(1, min(5, int(1 + 4 * pct_rank(values, x))))


# ────────────────────────── 加载 ──────────────────────────
class Inputs:
    def __init__(self):
        self.books_raw = load_json(BOOKS_JSON)
        self.chapters_raw = load_json(CHAPTERS_JSON)
        self.graph = load_json(GRAPH_JSON)
        self.matches_raw = load_json(MATCHES_JSON)
        self.ratings_raw = load_json(RATINGS_JSON, required=False)
        self.cards_raw = load_json(CARDS_JSON)
        self.books = {b["book"]: b for b in self.books_raw.get("books") or []}
        self.chapter_meta = self.chapters_raw.get("meta") or {}
        self.lit_books = [b for b in (self.chapter_meta.get("lit_books") or LIT_BOOKS) if b in self.books]
        self.book_chapters = {b: list((self.chapters_raw.get(b) or {}).get("chapters") or []) for b in self.books}
        self.graph_nodes = self.graph.get("nodes") or []
        self.graph_edges = self.graph.get("edges") or []
        self.matches = self.matches_raw.get("matches") or []
        self.fighters = self.matches_raw.get("fighters") or []
        self.cards = self.cards_raw.get("cards") or []
        self.card_index = self.cards_raw.get("card_index") or {}
        self.card_by_name = {}
        for c in self.cards:
            name = (c.get("name") or {}).get("canonical")
            if name:
                self.card_by_name[name] = c
                for a in c.get("aliases") or []:
                    if a.get("surface"):
                        self.card_by_name.setdefault(a["surface"], c)
        self.players = {p.get("name"): p for p in (self.ratings_raw.get("players") or [])}
        self.tiers = (self.ratings_raw.get("meta") or {}).get("tiers") or {}


# ────────────────────────── 章节难度（09b §5.1） ──────────────────────────
def build_chapter_facts(inp: Inputs) -> dict:
    facts = {}
    for book in inp.lit_books:
        recs = []
        for c in inp.book_chapters.get(book, []):
            no = int(c.get("no") or 0)
            length, fences = struct_stats(book, no)
            entities = len({ch.get("name") for ch in (c.get("chars") or []) if ch.get("name")})
            events = int(c.get("events") or 0)
            verb_n = sum(int(v or 0) for v in (c.get("verbs") or {}).values() if isinstance(v, (int, float)))
            recs.append({"book": book, "chapter": no, "title": c.get("title") or "",
                         "length": length, "events": events, "entities": entities,
                         "fences": fences, "verbs": verb_n,
                         "chars": c.get("chars") or []})
        facts[book] = recs
    return facts


def assign_difficulty(facts: dict) -> dict:
    all_recs = [r for recs in facts.values() for r in recs]
    lengths = [r["length"] for r in all_recs if r["length"] > 0]
    median_length = statistics.median(lengths) if lengths else 1
    raws = []
    for r in all_recs:
        r["_raw"] = (0.4 * r["events"] + 0.3 * r["entities"] + 0.2 * r["fences"]
                     + 0.1 * (r["length"] / median_length))
        raws.append(r["_raw"])
    for r in all_recs:
        r["difficulty"] = difficulty_from_rank(raws, r["_raw"])
    return {"median_length": round(median_length, 2), "raw_min": round(min(raws), 4) if raws else 0,
            "raw_max": round(max(raws), 4) if raws else 0, "denominator": f"{len(all_recs)} 章（5 书点亮集）"}


# ────────────────────────── 关卡 ──────────────────────────
def make_chapter_levels(inp: Inputs, facts: dict, diffs: dict) -> list[dict]:
    levels = []
    for book in inp.lit_books:
        recs = facts.get(book, [])
        by_no = {r["chapter"]: r for r in recs}
        for r in recs:
            no = r["chapter"]
            top_char = (r["chars"][0].get("name") if r["chars"] else None)
            objectives = []
            reward = {"kind": "none", "ref": None}
            if top_char:
                objectives.append({"kind": "identify", "target": f"@{top_char}",
                                   "evidence": f"chapters.json#{book}/chapters[{no}].chars[0]"})
                card = inp.card_by_name.get(top_char) or inp.card_by_name.get(short_name(top_char))
                if card:
                    reward = {"kind": "card", "ref": card["meta"].get("stable_id")}
            else:
                objectives.append({"kind": "resolve", "target": f"{book}#pn-r{no}",
                                   "evidence": "chapters.json#chapter_has_no_chars"})
            prev = no - 1
            gate = f"lv-{book_id(book)}-{prev:03d}" if prev in by_no else None
            levels.append({
                "id": f"lv-{book_id(book)}-{no:03d}",
                "type": "chapter",
                "name": f"{book}·{r['title'][:24] or ('第' + str(no) + '回')}",
                "source_refs": [f"{book}#pn-r{no}", f"chapters.json#{book}/chapters[{no}]"],
                "difficulty": r["difficulty"],
                "difficulty_basis": {"events": r["events"], "entities": r["entities"],
                                     "fences": r["fences"], "chars": r["length"],
                                     "chapter_median": diffs["median_length"],
                                     "denominator": diffs["denominator"]},
                "objectives": objectives,
                "gates": ([f"完成上一回（{book}第{prev}回）"] if gate else []),
                "reward": reward,
                "simulate": True,
                "publish_state": "local-only",
            })
    return levels


def make_relation_levels(inp: Inputs) -> list[dict]:
    edges = sorted(inp.graph_edges, key=lambda e: -(e.get("n") or 0))
    ns = [e.get("n") or 0 for e in edges]
    levels = []
    for i, e in enumerate(edges[:40]):
        s, t, kind = e.get("s"), e.get("t"), e.get("kind")
        levels.append({
            "id": f"lv-rel-{i + 1:03d}",
            "type": "relation",
            "name": f"{s}—{kind}—{t}",
            "source_refs": [f"graph.json#edges[{inp.graph_edges.index(e)}]"],
            "difficulty": difficulty_from_rank(ns, e.get("n") or 0),
            "difficulty_basis": {"edge_n": e.get("n") or 0, "kind_edges_total": sum(1 for x in edges if x.get("kind") == kind),
                                 "denominator": f"graph.edges {len(edges)} 条"},
            "objectives": [{"kind": "connect", "target": f"@{s}", "evidence": f"graph.nodes/{s}"},
                           {"kind": "connect", "target": f"@{t}", "evidence": f"graph.nodes/{t}"}],
            "gates": [],
            "reward": {"kind": "relation", "ref": f"graph.json#edges[{inp.graph_edges.index(e)}]"},
            "simulate": True,
            "publish_state": "local-only",
        })
    return levels


def make_person_levels(inp: Inputs) -> list[dict]:
    nodes = sorted([n for n in inp.graph_nodes if n.get("type") == "@"], key=lambda n: -(n.get("n") or 0))
    ns = [n.get("n") or 0 for n in nodes]
    levels = []
    for i, n in enumerate(nodes[:30]):
        name = n.get("id")
        card = inp.card_by_name.get(name) or inp.card_by_name.get(short_name(name))
        objectives = [{"kind": "identify", "target": f"@{name}", "evidence": f"graph.nodes/{name}"}]
        reward = {"kind": "none", "ref": None}
        if card:
            objectives.append({"kind": "collect", "target": card["meta"].get("stable_id"),
                               "evidence": "registry/sku/cards.json#card_index/person"})
            reward = {"kind": "card", "ref": card["meta"].get("stable_id")}
        levels.append({
            "id": f"lv-person-{i + 1:03d}",
            "type": "person",
            "name": f"人物：{name}",
            "source_refs": [f"graph.json#nodes[{name}]",
                            f"registry/sku/cards.json#cards[name={name}]" if card else "graph.json#nodes"],
            "difficulty": difficulty_from_rank(ns, n.get("n") or 0),
            "difficulty_basis": {"node_n": n.get("n") or 0, "books": len(n.get("books") or []),
                                 "denominator": f"graph.nodes @ {len(nodes)} 个"},
            "objectives": objectives,
            "gates": [],
            "reward": reward,
            "simulate": True,
            "publish_state": "local-only",
        })
    return levels


def make_match_levels(inp: Inputs, facts: dict) -> list[dict]:
    dmap = {(r["book"], r["chapter"]): r["difficulty"] for recs in facts.values() for r in recs}
    levels = []
    for m in inp.matches:
        book = m.get("book")
        loc = m.get("loc") or ""
        ch = None
        if ":" in loc:
            try:
                ch = int(str(loc).split(":", 1)[0])
            except ValueError:
                ch = None
        d = dmap.get((book, ch))
        basis = {"chapter_difficulty": d, "weight": m.get("weight"), "confidence": m.get("confidence"),
                 "kind": m.get("kind"), "denominator": "chapters 151 章全点亮集分位"}
        if d is None:
            d = 3
            basis["fallback"] = "无对应点亮章节：按默认 3 级占位（不参与难度统计）"
        levels.append({
            "id": f"lv-match-{m.get('id')}",
            "type": "match",
            "name": f"对局：{m.get('a')} vs {m.get('b')}",
            "source_refs": [f"matches.json#matches[{m.get('id')}]"],
            "difficulty": d,
            "difficulty_basis": basis,
            "objectives": [{"kind": "replay", "target": f"matches#{m.get('id')}",
                            "evidence": f"matches.json#matches[{m.get('id')}]"}],
            "gates": ([f"完成 {book} 第{ch}回"] if ch else []),
            "reward": {"kind": "match_record", "ref": f"matches.json#matches[{m.get('id')}]"},
            "simulate": True,
            "publish_state": "local-only",
        })
    return levels


# ────────────────────────── 成就 ──────────────────────────
def _thresholds(total: int) -> list[tuple[str, int]]:
    out = []
    for tier, k in TIER_K:
        out.append((tier, max(1, round(total * k))))
    return out


def build_achievements(inp: Inputs) -> list[dict]:
    ach = []
    # 收集类：五类卡
    for ctype, ids in (inp.card_index or {}).items():
        total = len(ids or [])
        if total <= 0:
            continue
        for tier, count in _thresholds(total):
            ach.append({
                "id": f"ach-collect-{ctype}-{tier}",
                "name": f"{ctype} 图鉴·{tier}",
                "tier": tier,
                "condition": {"kind": "collect", "where": {"card_type": ctype}, "count": count},
                "progress_source": f"registry/sku/cards.json#card_index/{ctype}",
                "evidence": [f"cards.json#card_index[{ctype}]（总量 {total}）"],
                "computable": True,
            })
    # 关系类：top 5 edge kinds
    kind_totals = {}
    for e in inp.graph_edges:
        kind_totals[e.get("kind")] = kind_totals.get(e.get("kind"), 0) + 1
    for kind, total in sorted(kind_totals.items(), key=lambda kv: -kv[1])[:5]:
        for tier, count in _thresholds(total):
            ach.append({
                "id": f"ach-rel-{_slug(kind)}-{tier}",
                "name": f"关系收集·{kind}·{tier}",
                "tier": tier,
                "condition": {"kind": "connect", "where": {"edge_kind": kind}, "count": count},
                "progress_source": "graph.json#edges（按 kind 统计）",
                "evidence": [f"graph.json meta.totals（{kind} 边 {total} 条）"],
                "computable": True,
            })
    # 对局完成类
    total_matches = len(inp.matches)
    for tier, count in _thresholds(total_matches):
        ach.append({
            "id": f"ach-match-complete-{tier}",
            "name": f"对局回顾·{tier}",
            "tier": tier,
            "condition": {"kind": "complete", "where": {"source": "matches"}, "count": count},
            "progress_source": "logs/export/staging/matches.json#matches",
            "evidence": [f"matches.json totals.matches={total_matches}"],
            "computable": True,
        })
    return ach


def build_sims(inp: Inputs) -> list[dict]:
    sims = []
    pair_count = {}
    for m in inp.matches:
        key = tuple(sorted((m.get("a"), m.get("b"))))
        pair_count[key] = pair_count.get(key, 0) + 1
    for m in inp.matches[:12]:
        a, b = m.get("a"), m.get("b")
        pa = inp.players.get(a) or inp.players.get(short_name(a or ""))
        pb = inp.players.get(b) or inp.players.get(short_name(b or ""))
        h2h = pair_count.get(tuple(sorted((a, b))), 0)
        if pa and pb:
            p_a = 1 / (1 + 10 ** (-((pa.get("rating") or 1500) - (pb.get("rating") or 1500)) / 400))
            result = {"p_a": round(p_a, 4), "method": "glicko2_expected_score",
                      "note": "按 Glicko-2 期望得分公式；非原著结局推断"}
            basis_ratings = {"a": {"r": pa.get("rating"), "rd": pa.get("rd")},
                             "b": {"r": pb.get("rating"), "rd": pb.get("rd")}}
        else:
            result = {"p_a": None, "method": "glicko2_expected_score",
                      "note": "不可推演：ratings 缺少一方（按铁律 p_a=null，不估数）"}
            basis_ratings = {"a": None, "b": None}
        sims.append({
            "simulate": True, "a": a, "b": b, "match_id": m.get("id"),
            "basis": {"ratings": basis_ratings, "h2h": {"matches": h2h, "note": "由 matches.json 统计填入（禁手填）"}},
            "result": result,
            "disclaimer": "推演基于 Glicko-2 评级与历史对局，非原著结局，非考订结论。",
        })
    return sims


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in str(text)).strip("-").lower() or "x"


# ────────────────────────── 校验/报告 ──────────────────────────
def validate(data: dict, inp: Inputs, facts: dict) -> dict:
    errors = []
    levels = data.get("levels") or []
    ids = [lv.get("id") for lv in levels]
    if len(ids) != len(set(ids)):
        errors.append("level id 重复")
    counts = {}
    for lv in levels:
        counts[lv.get("type")] = counts.get(lv.get("type"), 0) + 1
        if lv.get("type") not in LEVEL_TYPES:
            errors.append(f"{lv.get('id')}: 非法 type")
        if not isinstance(lv.get("difficulty"), int) or not 1 <= lv["difficulty"] <= 5:
            errors.append(f"{lv.get('id')}: difficulty 越界")
        if not lv.get("source_refs"):
            errors.append(f"{lv.get('id')}: 缺 source_refs")
        for obj in lv.get("objectives") or []:
            if obj.get("kind") not in OBJECTIVE_KINDS:
                errors.append(f"{lv.get('id')}: 非法 objective kind")
        if lv.get("simulate") is not True:
            errors.append(f"{lv.get('id')}: simulate 应为 true")
        if lv.get("publish_state") != "local-only":
            errors.append(f"{lv.get('id')}: publish_state 应为 local-only")
    ach = data.get("achievements") or []
    for a in ach:
        if a.get("computable") is not True:
            errors.append(f"{a.get('id')}: computable 必须 true")
        cnt = (a.get("condition") or {}).get("count")
        if not isinstance(cnt, int) or cnt <= 0:
            errors.append(f"{a.get('id')}: count 非法")
    progress = data.get("progress") or {}
    if progress.get("local_only") is not True:
        errors.append("progress.local_only 必须 true")
    text = json.dumps(data, ensure_ascii=False)
    for forbidden in ("site/data", "site/src", "content/person", "public/"):
        if forbidden in text:
            errors.append(f"输出不得引用发布目录 {forbidden}")
    expect = {"chapter": sum(len(v) for v in facts.values()), "relation": 40, "person": 30,
              "match": len(inp.matches)}
    for t, n in expect.items():
        if counts.get(t, 0) != n:
            errors.append(f"{t} 关卡数 {counts.get(t, 0)} != {n}")
    return {"passed": not errors, "errors": errors, "counts": counts,
            "achievements": len(ach), "sims": len(data.get("sims") or [])}


def render_report(data: dict, inp: Inputs, facts: dict, diffs: dict, val: dict) -> str:
    lines, add = [], None
    add = lines.append
    add("# 09b 游戏化关卡/成就/进度生成报告（registry/game/levels.json）")
    add("")
    add(f"- 工具：`scripts/build_game_levels.py`（{TOOL_VERSION}）；数据版本 {DATA_VERSION}")
    add("- 输入：graph.json（489 节点/907 边）、SKU cards（1,509）、matches（341）、ratings（194 players）、"
        "books/chapters、tagged/struct（只读）")
    add("- 产物：`registry/game/levels.json`；本报告 `logs/qa/game_levels_report.md`；`simulate:true`；不写 site/data")
    add("")
    add("## 一、规模")
    add("")
    add("| 类型 | 数量 |")
    add("|---|---:|")
    for t in LEVEL_TYPES:
        add(f"| {t} | {val['counts'].get(t, 0)} |")
    add(f"| **levels 合计** | **{sum(val['counts'].values())}** |")
    add(f"| achievements | {val['achievements']} |")
    add(f"| sims | {val['sims']} |")
    add(f"| progress | 1（本地 schema，local_only） |")
    add("")
    add("## 二、公式（禁手填；SKILL_09b §五）")
    add("")
    add("```text")
    add("章节难度：raw = 0.4*events + 0.3*entities + 0.2*fences + 0.1*(chars/median_chars)")
    add("           D   = 1 + 4*pct_rank(raw)   # 分母=5 书点亮集 151 章")
    add(f"           median_chars={diffs['median_length']}；raw ∈ [{diffs['raw_min']}, {diffs['raw_max']}]")
    add("关系/人物关卡：D = 1 + 4*pct_rank(edge_n / node_n)")
    add("对局关卡：D = 所属章节 D（book+loc 回号）；无对应章节 → 3 级占位并标 fallback")
    add("成就阈值：collect count = round(该类总量*k)，k ∈ {0.1,0.3,0.6}（bronze/silver/gold）")
    add("           connect count ≤ 该类 kind 边数；complete count ≤ 341 场")
    add("推演：p_a = 1/(1+10^(-(r_a-r_b)/400))，basis.ratings + basis.h2h.matches 来自实测")
    add("```")
    add("")
    add("## 三、关卡难度分布")
    add("")
    add("| 类型 | L1 | L2 | L3 | L4 | L5 |")
    add("|---|---:|---:|---:|---:|---:|")
    for t in LEVEL_TYPES:
        dist = [sum(1 for lv in data["levels"] if lv["type"] == t and lv["difficulty"] == d) for d in (1, 2, 3, 4, 5)]
        add(f"| {t} | {' | '.join(map(str, dist))} |")
    add("")
    add("## 四、成就与推演")
    add("")
    add(f"- 成就 {len(data['achievements'])} 条：收集类（五类卡）、关系类（top 5 kind）、对局完成类；全部 computable=true。")
    add(f"- 推演 {len(data['sims'])} 条：p_a 由 Glicko-2 期望得分计算；缺 ratings 的条目 p_a=null（不估数）。")
    add("")
    add("## 五、校验（--strict）")
    add("")
    add(f"- 结论：{'PASS' if val['passed'] else 'FAIL'}；错误 {len(val['errors'])} 项")
    for e in val["errors"]:
        add(f"  - {e}")
    add("")
    add("## 六、遗留/边界")
    add("")
    add("- event/sect 关卡未生成：任务输入未含事件层与 sect 数据（graph sects=0）；registry/events 22,978 条待后续批次接入。")
    add("- 对局关卡只回放 matches.json 已抽取 341 场，不补写未抽取场次；胜负证据仅作回放，不作考订结论。")
    add("- 章节难度使用点亮 5 书 151 章分位；未点亮 29 部不参与关卡（09c/09b 同纪律）。")
    add("- 本生成器只写 registry/game/levels.json 与 logs；不写 site/data/content/public。")
    add("")
    return "\n".join(lines) + "\n"


# ────────────────────────── selftest / CLI ──────────────────────────
def run_selftest() -> int:
    checks = []

    def chk(name, cond):
        checks.append(bool(cond))
        if not cond:
            print(f"[FAIL] {name}")

    chk("pct 最小", pct_rank([1, 2, 3], 1) == 0.0)
    chk("pct 最大", pct_rank([1, 2, 3], 3) == 1.0)
    chk("D 范围内", 1 <= difficulty_from_rank([1, 2, 3, 4, 5], 3) <= 5)
    chk("阈值三档", len(_thresholds(100)) == 3 and _thresholds(100)[0][1] == 10)
    chk("阈值最小 1", _thresholds(1)[0][1] == 1)
    chk("tier 名", [t for t, _ in TIER_K] == ["bronze", "silver", "gold"])
    chk("level 类型", set(LEVEL_TYPES) == {"chapter", "relation", "person", "match"})
    chk("objective 类型", OBJECTIVE_KINDS == {"identify", "connect", "collect", "resolve", "replay"})
    chk("书 ID", set(BOOK_IDS.values()) == {"jianghu", "qijian", "saiwai", "bingpo", "bainv"})
    chk("slug", _slug("交手") != "")
    chk("p_a 均衡", abs(1 / (1 + 10 ** (-(1500 - 1500) / 400)) - 0.5) < 1e-9)
    chk("p_a 高 r", 1 / (1 + 10 ** (-(1600 - 1500) / 400)) > 0.5)
    ok = sum(checks)
    print(f"[selftest] {ok}/{len(checks)} passed")
    return 0 if ok == len(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_game_levels.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="09b 游戏化生成：graph/cards/matches → levels/achievements/progress/sim（难度公式派生，simulate:true）。",
        epilog="示例：python -X utf8 scripts/build_game_levels.py --dry-run\n"
               "      python -X utf8 scripts/build_game_levels.py --apply\n"
               "      python -X utf8 scripts/build_game_levels.py --selftest",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="只校验并打印摘要（默认行为）")
    g.add_argument("--apply", action="store_true", help="写 registry/game/levels.json + 报告")
    p.add_argument("--selftest", action="store_true", help="纯函数自检")
    p.add_argument("--strict", action="store_true", help="严格校验，失败 exit 2")
    p.add_argument("--out", default=str(OUT_JSON), help="JSON 输出路径")
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
    facts = build_chapter_facts(inp)
    diffs = assign_difficulty(facts)
    levels = make_chapter_levels(inp, facts, diffs) + make_relation_levels(inp) \
        + make_person_levels(inp) + make_match_levels(inp, facts)
    achievements = build_achievements(inp)
    sims = build_sims(inp)
    progress = {"schema": "game-progress-v0.1", "local_only": True, "levels": {},
                "achievements": {}, "sim_runs": [], "updated_at": None}
    data = {
        "schema": "game-levels-v0.1",
        "meta": {
            "generated": DATA_VERSION, "tool": TOOL_VERSION, "data_version": DATA_VERSION,
            "simulate": True,
            "source_refs": {
                "graph": "logs/export/staging/graph.json",
                "cards": "registry/sku/cards.json",
                "matches": "logs/export/staging/matches.json",
                "ratings": "logs/export/staging/ratings.json",
                "chapters": "logs/export/staging/chapters.json",
                "struct": "tagged/<书>/NNN.struct.md",
            },
            "source_generated": {
                "graph": inp.graph.get("meta", {}).get("generated"),
                "cards": inp.cards_raw.get("meta", {}).get("generated_at"),
                "matches": inp.matches_raw.get("meta", {}).get("generated"),
                "ratings": inp.ratings_raw.get("meta", {}).get("generated"),
            },
            "formulas": {
                "chapter_difficulty": "raw=0.4*events+0.3*entities+0.2*fences+0.1*(chars/median_chars); D=1+4*pct_rank(raw)",
                "denominator": diffs["denominator"],
                "relation_person_difficulty": "D=1+4*pct_rank(edge_n or node_n)",
                "achievement_threshold": "collect=round(total*k), k∈{0.1,0.3,0.6}; connect<=kind_edges; complete<=341",
                "sim": "p_a=1/(1+10^(-(r_a-r_b)/400))（Glicko-2 expected score）",
            },
            "input_totals": {"graph_nodes": len(inp.graph_nodes), "graph_edges": len(inp.graph_edges),
                             "cards": len(inp.cards), "matches": len(inp.matches),
                             "ratings_players": len(inp.players), "lit_chapters": sum(len(v) for v in facts.values())},
            "counts": {},
            "validation": {},
        },
        "levels": levels,
        "achievements": achievements,
        "progress": progress,
        "sims": sims,
        "disclaimer": "本产物为本地/只读游戏化视图：推演非原著结局、非考订结论；不写入任何发布目录。",
    }
    val = validate(data, inp, facts)
    data["meta"]["validation"] = val
    data["meta"]["counts"] = {"levels": len(levels), "by_type": val["counts"],
                              "achievements": len(achievements), "sims": len(sims)}
    if args.apply:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_report(data, inp, facts, diffs, val), encoding="utf-8")
        if not args.quiet:
            print(f"[OK] levels {len(levels)} {val['counts']}；achievements {len(achievements)}；sims {len(sims)} → {out}")
            print(f"[OK] 报告 → {report}")
    elif not args.quiet:
        print(f"[dry-run] levels {len(levels)} {val['counts']}；achievements {len(achievements)}；"
              f"sims {len(sims)}；校验 {'PASS' if val['passed'] else 'FAIL'}")
    if args.strict and not val["passed"]:
        print("[STRICT] 校验未通过", file=sys.stderr)
        for e in val["errors"]:
            print(f"  - {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
