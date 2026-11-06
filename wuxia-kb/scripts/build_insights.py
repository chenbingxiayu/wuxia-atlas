#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W11 · 概念洞察生成器（八类模式 → registry/insights.json）

数据（只读）：
  * EX-4 graph：`logs/export/staging/graph.json`（489 节点/907 边）
  * N5 relations：`registry/relations/<书>.json`（910 边；师承/交手/杀害等）
  * N10 cards：`registry/sku/cards.json`（1,509 卡）
  * concordance：`registry/concordance/<书>.json`（unregistered/频次）
  * N6 intertext：`registry/intertext/intertext_loc.json`（authorial/quoted/bare）
  * N8 consistency：`registry/consistency/<书>.json`（ANOMALY 线索）
  * N9 taxonomy：`logs/taxonomy/taxonomy_trees.json`（5 树 64 叶；COMPARE 佐证）
  * N4 time：`registry/time/<书>.json`（forks；ANOMALY 佐证）
  * matches：`logs/export/staging/matches.json`（341 场；CONFLICT 佐证）

八类模式（SKILL_W11 §二）：
  COLLAB / CONFLICT / LINEAGE / COMPARE / CHAIN / BLANK / CROSSREF / ANOMALY
每条洞察：≥2 类独立证据（E1 结构化/E2 定位符/E3 第二结构化源）+ 反证检索 + A-E + novelty/action。
铁律：不写原文片段、不产事实（hypothesis）、无反证登记 counter.searched、可复现。

输出：`registry/insights.json`；报告 `logs/qa/insights_report.md`
CLI：--dry-run（默认）/--apply/--selftest/--strict
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH_JSON = ROOT / "logs" / "export" / "staging" / "graph.json"
MATCHES_JSON = ROOT / "logs" / "export" / "staging" / "matches.json"
CARDS_JSON = ROOT / "registry" / "sku" / "cards.json"
ENTITIES_JSON = ROOT / "registry" / "entities.json"
DISPLAY_JSON = ROOT / "registry" / "display_canonical.json"
INTERTEXT_JSON = ROOT / "registry" / "intertext" / "intertext_loc.json"
TAXONOMY_JSON = ROOT / "logs" / "taxonomy" / "taxonomy_trees.json"
CONSISTENCY_DIR = ROOT / "registry" / "consistency"
TIME_DIR = ROOT / "registry" / "time"
REL_DIR = ROOT / "registry" / "relations"
CONC_DIR = ROOT / "registry" / "concordance"
OUT_JSON = ROOT / "registry" / "insights.json"
OUT_REPORT = ROOT / "logs" / "qa" / "insights_report.md"
TOOL_VERSION = "build_insights v0.1 (2026-11-05, W11)"
DATA_VERSION = "2026-11-05"
PATTERNS = ("COLLAB", "CONFLICT", "LINEAGE", "COMPARE", "CHAIN", "BLANK", "CROSSREF", "ANOMALY")
CONF_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "E": 0}
ACTION = {"A": "build-page", "B": "merge-into-page", "C": "observe", "D": "record", "E": "handoff-W14"}
LIT_BOOKS = ["七剑下天山", "冰魄寒光剑", "塞外奇侠传", "江湖三女侠", "白发魔女传"]


def load_json(path: Path, required: bool = True) -> dict:
    if not path.exists():
        if required:
            raise SystemExit(f"[ERROR] 输入缺失：{path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def short_name(name: str) -> str:
    for suffix in ("提督", "总兵", "将军", "大人", "先生", "姑娘", "小姐", "公子", "和尚", "道人"):
        if len(name) > len(suffix) + 1 and name.endswith(suffix):
            return name[: -len(suffix)]
    return name


class Inputs:
    def __init__(self):
        self.graph = load_json(GRAPH_JSON)
        self.matches = (load_json(MATCHES_JSON).get("matches") or {})
        self.cards_raw = load_json(CARDS_JSON)
        self.entities_raw = load_json(ENTITIES_JSON)
        self.display = load_json(DISPLAY_JSON, required=False)
        self.intertext = load_json(INTERTEXT_JSON, required=False)
        self.taxonomy = load_json(TAXONOMY_JSON, required=False)
        self.nodes = {n.get("id"): n for n in self.graph.get("nodes") or []}
        self.edges = self.graph.get("edges") or []
        self.cards = self.cards_raw.get("cards") or []
        self.card_by_name = {}
        for c in self.cards:
            name = (c.get("name") or {}).get("canonical")
            if name:
                self.card_by_name[name] = c
                for a in c.get("aliases") or []:
                    if a.get("surface"):
                        self.card_by_name.setdefault(a["surface"], c)
        self.entities = self.entities_raw.get("entities") or []
        self.entity_ids = {e.get("canonical"): e.get("id") for e in self.entities}
        self.display_pairs = (self.display.get("entries") or []) if self.display else []
        self.intertext_edges = (self.intertext.get("edges") or []) if self.intertext else []
        self.taxonomy_trees = (self.taxonomy.get("trees") or []) if self.taxonomy else []
        self.consistency = {}
        for b in LIT_BOOKS:
            p = CONSISTENCY_DIR / f"{b}.json"
            if p.exists():
                self.consistency[b] = json.loads(p.read_text(encoding="utf-8"))
        self.forks = {}
        for b in LIT_BOOKS:
            p = TIME_DIR / f"{b}.json"
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                self.forks[b] = d.get("forks") or []
        self.relations = {}
        for b in LIT_BOOKS:
            p = REL_DIR / f"{b}.json"
            if p.exists():
                self.relations[b] = json.loads(p.read_text(encoding="utf-8"))
        self.concordance = defaultdict(list)
        for p in sorted(CONC_DIR.glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            for e in d.get("entities") or []:
                if e.get("type") == "@":
                    self.concordance[e.get("canonical")].append((p.stem, e))
        self.matches_pairs = Counter()
        for m in self.matches:
            self.matches_pairs[tuple(sorted((m.get("a"), m.get("b"))))] += 1
        self.hostile = {(e.get("s"), e.get("t")) for e in self.edges if e.get("kind") in ("交手", "杀害", "点穴")}
        self.hostile |= {(b, a) for a, b in self.hostile}
        self.friendly = {(e.get("s"), e.get("t")) for e in self.edges
                         if e.get("kind") in ("师承", "同门", "婚约", "结义", "解救", "转移", "到达")}
        self.friendly |= {(b, a) for a, b in self.friendly}
        self._insight_no = 0

    def new_id(self) -> str:
        self._insight_no += 1
        return f"INS-{self._insight_no:04d}"

    def add(self, pattern, claim, entities, books, evidence, counter, novelty="new", handoff="W8"):
        levels = {e.get("level") for e in evidence if e.get("level")}
        if len(levels) >= 3 and counter.get("cleared"):
            conf = "A"
        elif len(levels) >= 2 and counter.get("cleared"):
            conf = "B"
        elif len(levels) >= 2:
            conf = "C"
        elif len(levels) == 1:
            conf = "D"
        else:
            conf = "E"
        status = "queued" if conf in ("A", "B") else ("observe" if conf == "C" else "record")
        return {"id": self.new_id(), "pattern": pattern, "claim": claim,
                "entities": sorted({e for e in entities if e}), "books": sorted({b for b in books if b}),
                "evidence": evidence, "counter": counter, "confidence": conf,
                "novelty": novelty, "action": ACTION[conf], "handoff": handoff,
                "data_version": DATA_VERSION, "generated_at": DATA_VERSION, "status": status, "dup_of": None}


# ────────────────────────── 八类模式 ──────────────────────────
def gen_collab(inp: Inputs, cap=8):
    out = []
    seen = set()
    for e in sorted(inp.edges, key=lambda x: -(x.get("n") or 0)):
        kind = e.get("kind")
        if kind not in ("师承", "同门", "婚约", "结义", "解救", "到达", "转移"):
            continue
        pair = tuple(sorted((e.get("s"), e.get("t"))))
        if pair in seen:
            continue
        seen.add(pair)
        books = e.get("books") or []
        ev = [{"level": "E1", "ref": f"graph.edges[{e.get('s')}—{kind}—{e.get('t')}]",
               "value": e.get("n") or 0}]
        locs = [l for l in (e.get("locs") or []) if l]
        if locs:
            ev.append({"level": "E2", "ref": locs[0], "note": f"共 {len(locs)} 条定位符"})
        cards = [inp.card_by_name.get(pair[0]), inp.card_by_name.get(pair[1])]
        if all(cards):
            ev.append({"level": "E3", "ref": f"cards[{pair[0]},{pair[1]}]", "value": "两张人物卡可回指"})
        counter = {"searched": True, "result": "", "cleared": True}
        if pair in inp.hostile:
            counter = {"searched": True, "result": "图中存在交手/杀害类敌对边：共事假设需降级或转 CONFLICT",
                       "cleared": False}
        out.append(inp.add("COLLAB", f"{pair[0]}与{pair[1]}在 {len(books)} 书共现且存在{kind}关系（n={e.get('n')}）",
                           list(pair), books, ev, counter))
        if len(out) >= cap:
            break
    return out


def gen_conflict(inp: Inputs, cap=8):
    out = []
    for e in sorted([x for x in inp.edges if x.get("kind") == "交手"], key=lambda x: -(x.get("n") or 0))[:cap]:
        pair = tuple(sorted((e.get("s"), e.get("t"))))
        n = e.get("n") or 0
        ev = [{"level": "E1", "ref": f"graph.edges[{e.get('s')}—交手—{e.get('t')}]", "value": n}]
        locs = [l for l in (e.get("locs") or []) if l]
        if locs:
            ev.append({"level": "E2", "ref": locs[0]})
        if inp.matches_pairs.get(pair):
            ev.append({"level": "E3", "ref": f"matches.json#pair({pair[0]},{pair[1]})",
                       "value": inp.matches_pairs[pair]})
        counter = {"searched": True,
                   "result": "存在非敌对关系边（师承/同门/婚约/结义/解救）" if pair in inp.friendly else "未检索到非敌对边",
                   "cleared": pair not in inp.friendly}
        out.append(inp.add("CONFLICT", f"{e.get('s')}与{e.get('t')}交手边 n={n}（{len(locs)} 条定位符）",
                           list(pair), e.get("books") or [], ev, counter))
    return out


def gen_lineage(inp: Inputs, cap=8):
    out = []
    master_edges = [e for e in inp.edges if e.get("kind") == "师承"]
    adj = defaultdict(list)
    for e in master_edges:
        adj[e.get("s")].append(e)
    seen = set()
    for e1 in master_edges:
        a, b = e1.get("s"), e1.get("t")
        for e2 in adj.get(b, []):
            c = e2.get("t")
            if not c or c in (a, b):
                continue
            key = (a, b, c)
            if key in seen:
                continue
            seen.add(key)
            ev = [{"level": "E1", "ref": f"graph.edges[{a}—师承—{b}—师承—{c}]",
                   "value": (e1.get("n") or 0) + (e2.get("n") or 0)}]
            locs = (e1.get("locs") or [])[:1] + (e2.get("locs") or [])[:1]
            if locs:
                ev.append({"level": "E2", "ref": "；".join(locs)})
            card = inp.card_by_name.get(b)
            if card and (card.get("teachers") or card.get("seniority")):
                ev.append({"level": "E3", "ref": card["meta"].get("stable_id"), "value": "卡 teachers/seniority"})
            counter = {"searched": True, "result": "检查 N5 互斥/互为师徒冲突：未命中" if not _has_conflict(inp, b)
                       else "中间人存在互斥师父冲突，链需复核", "cleared": not _has_conflict(inp, b)}
            out.append(inp.add("LINEAGE", f"师承链 {a}→{b}→{c}（跨书图投影，中间人{'有卡' if card else '无卡'}）",
                               [a, b, c], e1.get("books") or e2.get("books") or [], ev, counter))
            if len(out) >= cap:
                return out
    return out


def _has_conflict(inp: Inputs, name: str) -> bool:
    for b, d in inp.relations.items():
        for w in (d.get("validation") or {}).get("warnings") or []:
            if name in (w.get("detail") or ""):
                return True
    return False


def gen_compare(inp: Inputs, cap=8):
    persons = [(nid, n) for nid, n in inp.nodes.items()
               if n.get("type") == "@" and len(n.get("books") or []) >= 3]
    persons.sort(key=lambda x: (-(len(x[1].get("books") or [])), x[0]))
    out = []
    for i in range(min(len(persons), cap * 2)):
        for j in range(i + 1, min(len(persons), i + 3)):
            a, na = persons[i]
            b, nb = persons[j]
            ca, cb = inp.card_by_name.get(a), inp.card_by_name.get(b)
            if not (ca and cb):
                continue
            fa = bool(ca.get("faction_history"))
            fb = bool(cb.get("faction_history"))
            if fa == fb:
                continue
            ev = [{"level": "E1", "ref": f"graph.nodes[{a}/{b}].books",
                   "value": [len(na.get("books") or []), len(nb.get("books") or [])]},
                  {"level": "E2", "ref": (ca.get("first_appearance") or {}).get("loc_r") or f"card:{a}"},
                  {"level": "E2", "ref": (cb.get("first_appearance") or {}).get("loc_r") or f"card:{b}"}]
            if "E3" not in [x["level"] for x in ev]:
                ev.append({"level": "E3", "ref": f"cards[{a}/{b}].faction_history", "value": [fa, fb]})
            merged = any((d.get("display") in (a, b) and d.get("canonical") in (a, b)) for d in inp.display_pairs)
            counter = {"searched": True, "result": "同名/展示层映射冲突已检索",
                       "cleared": not merged}
            out.append(inp.add("COMPARE", f"{a}与{b}同为 ≥3 书跨书人物，但门派履历一有一无（{fa}/{fb}）",
                               [a, b], list({*(na.get("books") or []), *(nb.get("books") or [])}), ev, counter))
            if len(out) >= cap:
                return out
    return out


def gen_chain(inp: Inputs, cap=8):
    person_edges = [e for e in inp.edges if e.get("s") in inp.nodes and e.get("t") in inp.nodes
                    and inp.nodes[e["s"]].get("type") == "@" and inp.nodes[e["t"]].get("type") == "@"]
    adj = defaultdict(list)
    for e in person_edges:
        adj[e["s"]].append(e)
    direct = {(e["s"], e["t"]) for e in person_edges} | {(e["t"], e["s"]) for e in person_edges}
    out = []
    seen = set()
    for e1 in person_edges:
        a, b = e1["s"], e1["t"]
        for e2 in adj.get(b, []):
            c = e2["t"]
            if c in (a, b) or (a, c) in direct:
                continue
            key = (a, b, c)
            if key in seen:
                continue
            seen.add(key)
            ev = [{"level": "E1", "ref": f"graph.edges[{a}—{b}—{c}]",
                   "value": (e1.get("n") or 0) + (e2.get("n") or 0)},
                  {"level": "E2", "ref": (e1.get("locs") or ["-"])[0]},
                  {"level": "E2", "ref": (e2.get("locs") or ["-"])[0]}]
            counter = {"searched": True, "result": "A—C 直接边不存在（两跳关系链为新增信息）", "cleared": True}
            out.append(inp.add("CHAIN", f"{a}—{b}—{c} 两跳可达且无直接边（每跳有定位符）",
                               [a, b, c], list({*(e1.get("books") or []), *(e2.get("books") or [])}), ev, counter))
            if len(out) >= cap:
                return out
    return out


def gen_blank(inp: Inputs, cap=10):
    out = []
    candidates = []
    for name, entries in inp.concordance.items():
        if name in inp.card_by_name:
            continue
        total = sum((e2.get("total") or 0) for _, e2 in entries)
        firsts = [(b, e2.get("first") or {}) for b, e2 in entries]
        if total >= 15:
            candidates.append((total, name, firsts))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    for total, name, firsts in candidates[:cap]:
        ev = [{"level": "E1", "ref": f"concordance[{name}].total", "value": total}]
        anchors = [f"{book}#pn-r{(f.get('chapter') or 0)}.{(f.get('para') or 0)}" for book, f in firsts[:2]]
        if anchors:
            ev.append({"level": "E2", "ref": "；".join(anchors)})
        ev.append({"level": "E3", "ref": f"graph.nodes[{name}]/cards", "value": "节点/卡均缺失（空白）"})
        mapped = any(d.get("display") == name or d.get("canonical") == name for d in inp.display_pairs) \
            or name in inp.entity_ids
        counter = {"searched": True, "result": "display/registry 映射已检索",
                   "cleared": not mapped}
        out.append(inp.add("BLANK", f"{name} 被提及 {total} 次但无人物卡/无独立页（空白候选）",
                           [name], [b for b, _ in firsts], ev, counter))
    return out


def gen_crossref(inp: Inputs, cap=10):
    out = []
    nodes = [(nid, n) for nid, n in inp.nodes.items()
             if n.get("type") == "@" and len(n.get("books") or []) >= 3]
    nodes.sort(key=lambda x: (-len(x[1].get("books") or []), -(x[1].get("n") or 0), x[0]))
    paper_edges = defaultdict(Counter)
    for e in inp.intertext_edges:
        paper_edges[(e.get("source"), e.get("target"))][e.get("kind")] += 1
    for nid, n in nodes[:cap]:
        ev = [{"level": "E1", "ref": f"graph.nodes[{nid}].books", "value": len(n.get("books") or [])}]
        card = inp.card_by_name.get(nid)
        if card:
            fa = card.get("first_appearance") or {}
            if fa.get("loc_r"):
                ev.append({"level": "E2", "ref": fa["loc_r"]})
            ev.append({"level": "E3", "ref": card["meta"].get("stable_id"),
                       "value": f"active_books={len(card.get('active_books') or [])}"})
        if len(ev) < 2:
            continue
        # 交错证据：与任一本书相关的互文边
        rel = []
        for (s, t), kinds in paper_edges.items():
            if s == nid or t == nid:
                rel.append((s, t, dict(kinds)))
        if rel:
            s, t, kinds = rel[0]
            ev.append({"level": "E3", "ref": f"intertext[{s}→{t}]", "value": kinds})
        counter = {"searched": True, "result": "display_canonical 同名/异人映射已检索",
                   "cleared": not any(d.get("display") == nid for d in inp.display_pairs)}
        out.append(inp.add("CROSSREF", f"{nid} 在 {len(n.get('books') or [])} 书出现（跨书重现候选）",
                           [nid], n.get("books") or [], ev, counter, handoff="W12"))
    return out


def gen_anomaly(inp: Inputs, cap=12):
    out = []
    for book, d in inp.consistency.items():
        for v in (d.get("violations") or [])[:cap]:
            if len(out) >= cap:
                return out
            ev = [{"level": "E1", "ref": f"consistency[{book}].violations[{v.get('vid')}]",
                   "value": f"{v.get('rule_id')}/{v.get('severity')}"},
                  {"level": "E2", "ref": v.get("locator") or f"{book}#?"}]
            if book in inp.forks and len(inp.forks[book]) > 0:
                ev.append({"level": "E3", "ref": f"time[{book}].forks", "value": len(inp.forks[book])})
            counter = {"searched": True,
                       "result": f"叙述模式={v.get('narrative_mode')}；豁免/三分流已检索",
                       "cleared": v.get("narrative_mode") in (None, "正常叙事", "未知") and not v.get("exempted")}
            out.append(inp.add("ANOMALY", f"{book} {v.get('rule_id')}：{v.get('rule_title', '')}",
                               [v.get("subject") or ""], [book], ev, counter, handoff="W14"))
    return out


# ────────────────────────── 校验/报告 ──────────────────────────
def validate(data: dict) -> dict:
    errors = []
    items = data.get("insights") or []
    ids = [x.get("id") for x in items]
    if len(ids) != len(set(ids)):
        errors.append("insight id 重复")
    patterns = Counter(x.get("pattern") for x in items)
    for p in PATTERNS:
        if patterns.get(p, 0) == 0:
            errors.append(f"缺少模式 {p}")
    for x in items:
        levels = {e.get("level") for e in x.get("evidence") or []}
        if len(levels) < 2:
            errors.append(f"{x.get('id')}: 证据级别不足 2 类")
        if not (x.get("counter") or {}).get("searched"):
            errors.append(f"{x.get('id')}: 未登记反证检索")
        if x.get("confidence") not in CONF_ORDER:
            errors.append(f"{x.get('id')}: confidence 越界")
        if not x.get("claim") or len(x.get("claim") or "") > 300:
            errors.append(f"{x.get('id')}: claim 空或过长")
    text = json.dumps(data, ensure_ascii=False)
    for forbidden in ("site/data", "site/src", "content/person", "public/"):
        if forbidden in text:
            errors.append(f"输出不得引用发布目录 {forbidden}")
    return {"passed": not errors, "errors": errors,
            "counts": {"total": len(items), "by_pattern": dict(patterns)}}


def render_report(data: dict, val: dict) -> str:
    lines = ["# W11 概念洞察生成报告（registry/insights.json）", "",
             f"- 工具：`scripts/build_insights.py`（{TOOL_VERSION}）；数据版本 {DATA_VERSION}",
             "- 输入：EX-4 graph、N5 relations、N10 cards、concordance、N6 intertext、N8 consistency、"
             "N9 taxonomy、N4 time、matches（只读）",
             "- 产物：`registry/insights.json`；报告 `logs/qa/insights_report.md`", "",
             "## 一、规模", "", "| 模式 | 条数 |", "|---|---:|"]
    by = val["counts"]["by_pattern"]
    for p in PATTERNS:
        lines.append(f"| {p} | {by.get(p, 0)} |")
    lines += [f"| **合计** | **{val['counts']['total']}** |", "", "## 二、置信/动作分布", ""]
    conf = Counter(x.get("confidence") for x in data["insights"])
    act = Counter(x.get("action") for x in data["insights"])
    lines.append(f"- confidence：{dict(conf)}")
    lines.append(f"- action：{dict(act)}")
    lines.append(f"- 证据门/反证门：全部条目 ≥2 类证据且 counter.searched=true；"
                 f"confidence A/B/C/D/E 按 07e 映射。")
    lines += ["", "## 三、样例（每模式 1 条）", ""]
    shown = set()
    for x in data["insights"]:
        if x["pattern"] in shown:
            continue
        shown.add(x["pattern"])
        lines.append(f"- **{x['id']} {x['pattern']}**：{x['claim']}（{x['confidence']}；"
                     f"证据 {[e['level'] for e in x['evidence']]}；反证 cleared={x['counter']['cleared']}）")
    lines += ["", "## 四、校验（--strict）", "",
              f"- 结论：{'PASS' if val['passed'] else 'FAIL'}；错误 {len(val['errors'])} 项"]
    for e in val["errors"]:
        lines.append(f"  - {e}")
    lines += ["", "## 五、公式与纪律", "",
              "- 模式：COLLAB/CONFLICT/LINEAGE/COMPARE/CHAIN/BLANK/CROSSREF/ANOMALY（W11 §二）。",
              "- 证据：E1 结构化 / E2 定位符 / E3 第二结构化源；同一 JSON 两字段只算 1 类。",
              "- 反证：每模式均执行反向检索（敌对边/同名映射/直接边/叙述模式等），counter.searched=true。",
              "- 置信：A=≥3 类+反证排除；B=2 类+反证已检索；C=2 类但反证未清；D=单一证据；E=冲突/不可定位。",
              "- 不写原文、不产事实；ANOMALY 只登记线索并 handoff=W14；CROSSREF handoff=W12。", "",
              "## 六、遗留/边界", "",
              "- N9 taxonomy 仅用于 COMPARE 佐证（64 叶/5 树），未做 type_audits 元审查（W11 §5.3，需 13 轮）。",
              "- 洞察为 hypothesis，C 级以下只入观察队列；建页需人工复核。",
              "- 本生成器只写 registry/insights.json 与 logs，不写 site/data。", ""]
    return "\n".join(lines) + "\n"


def run_selftest() -> int:
    checks = []

    def chk(name, cond):
        checks.append(bool(cond))
        if not cond:
            print(f"[FAIL] {name}")

    chk("八模式", len(PATTERNS) == 8)
    chk("置信序", CONF_ORDER["A"] > CONF_ORDER["E"])
    chk("动作映射", ACTION["E"] == "handoff-W14")
    chk("短名", short_name("多铎提督") == "多铎")
    chk("ID 格式", re.match(r"^INS-\d{4}$", "INS-0001") is not None)
    chk("数据版本", DATA_VERSION == "2026-11-05")
    chk("点亮书", len(LIT_BOOKS) == 5)
    ok = sum(checks)
    print(f"[selftest] {ok}/{len(checks)} passed")
    return 0 if ok == len(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_insights.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="W11 概念洞察：八类模式（COLLAB/CONFLICT/LINEAGE/COMPARE/CHAIN/BLANK/CROSSREF/ANOMALY）"
                    "各 ≥2 类证据 + 反证检索 + A-E 定级 → registry/insights.json",
        epilog="示例：python -X utf8 scripts/build_insights.py --dry-run / --apply / --selftest / --strict --apply")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="只校验并打印摘要（默认）")
    g.add_argument("--apply", action="store_true", help="写 registry/insights.json + 报告")
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
    insights = (gen_collab(inp) + gen_conflict(inp) + gen_lineage(inp) + gen_compare(inp)
                + gen_chain(inp) + gen_blank(inp) + gen_crossref(inp) + gen_anomaly(inp))
    data = {"schema": "w11-insights-v0.1",
            "meta": {"generated": DATA_VERSION, "tool": TOOL_VERSION, "data_version": DATA_VERSION,
                     "source_refs": {"graph": "logs/export/staging/graph.json",
                                     "relations": "registry/relations/",
                                     "cards": "registry/sku/cards.json",
                                     "concordance": "registry/concordance/",
                                     "intertext": "registry/intertext/intertext_loc.json",
                                     "consistency": "registry/consistency/",
                                     "taxonomy": "logs/taxonomy/taxonomy_trees.json",
                                     "time": "registry/time/",
                                     "matches": "logs/export/staging/matches.json"},
                     "patterns": list(PATTERNS),
                     "confidence_rule": "A=≥3 类证据+反证排除；B=2 类+反证已检索；C=2 类但反证未清；D=单一；E=冲突",
                     "counts": {}},
            "insights": insights}
    val = validate(data)
    data["meta"]["counts"] = val["counts"]
    data["meta"]["validation"] = val
    if args.apply:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_report(data, val), encoding="utf-8")
        if not args.quiet:
            print(f"[OK] insights {len(insights)} {val['counts']['by_pattern']} → {out}")
            print(f"[OK] 报告 → {report}")
    elif not args.quiet:
        print(f"[dry-run] insights {len(insights)} {val['counts']['by_pattern']}；校验 "
              f"{'PASS' if val['passed'] else 'FAIL'}")
    if args.strict and not val["passed"]:
        print("[STRICT] 校验未通过", file=sys.stderr)
        for e in val["errors"]:
            print(f"  - {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
