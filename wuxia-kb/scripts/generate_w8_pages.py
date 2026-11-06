#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W8 · 精品页生成器 —— generate_w8_pages.py（W 组波 1：person 卡页型首发）

定位
----
按 `templates/忠义殉主者.md` 的 W8 五段式（适用判断→必有节→加分项→反面示例→参考页面）
与 `registry/sku/cards.json`（N10 五类卡）+ `w8_w9_interface` 槽位，把 SKU 卡投影为
`content/` 下的 W8 精品页草稿：

  - 本批实现 **person 卡页型**（367 张 person 卡 → 人物档案页；忠义殉主者页型分支按
    ending.type 判定，当前数据无殉主卡，分支作为接口保留）；
  - 其余四类卡（faction/art/artifact/manual）**留接口**：`build_page()` 统一分发，
    未实现类型返回 interface 记录，不写盘；
  - 每页 frontmatter 必带 `quotes: []`（W7 `verify_quotes.py` 消费入口）与 `demo: true`
    （本批全部为演示/草稿页，不进入发布库，R4/K3）；`publish_state: draft`；
  - 只读上游（tagged/registry/site 均不写）；产物只落 `content/`，备份/统计落 `logs/qa/`。

用法
----
  # 1) 自检（合成卡，不写盘）
  python scripts/generate_w8_pages.py --selftest

  # 2) dry-run（默认；打印统计 + 样例页，不写盘）
  python scripts/generate_w8_pages.py
  python scripts/generate_w8_pages.py --limit 5 --sample 2

  # 3) 落盘（自动备份已有页到 logs/qa/w8_content_backup/<run_id>/，含 sha256 断言）
  python scripts/generate_w8_pages.py --apply
  python scripts/generate_w8_pages.py --apply --select card.person.e0019

  # 4) 其它卡型接口（预留，本批不产出）
  python scripts/generate_w8_pages.py --type faction

安全
----
  - `--apply` 仅允许写到仓库 `content/` 下（`--out-dir` 越界会被拒绝，除非 `--unsafe-out`）；
  - 覆盖前备份 + sha256 断言：备份缺失/不一致即中止；
  - 写后回读比对：内容不一致即中止（原子写入 tmp→replace）；
  - 不输出/不写原文：卡面 brief 已按 R1/R2 脱敏；页面引文只用指针（quotes 由后续撰写填入）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

ROOT = Path(config.ROOT)
CARDS = Path(config.DIR_REGISTRY) / "sku" / "cards.json"
RELATIONS_DIR = Path(config.DIR_REGISTRY) / "relations"
DISPLAY_CANONICAL = Path(config.DIR_REGISTRY) / "display_canonical.json"
TEMPLATE = ROOT / "templates" / "忠义殉主者.md"
CONTENT_DIR = ROOT / "content"
BACKUP_ROOT = Path(config.DIR_LOGS) / "qa" / "w8_content_backup"
STATS_OUT = Path(config.DIR_LOGS) / "qa" / "w8_generate_stats.json"

SCHEMA = "w8-page-v0.1"
PAGE_SCHEMA = "w8-five-section-v0.1"
GENERATED_BY = "scripts/generate_w8_pages.py"
SUPPORTED_TYPES = ("person", "faction", "art", "artifact", "manual")
BATCH2_TYPES = ("faction", "art", "artifact", "manual")
TYPE_PAGE_TYPE = {
    "person": "人物档案页", "faction": "门派档案页", "art": "武功档案页",
    "artifact": "兵器档案页", "manual": "秘籍档案页",
}
ENTITY_REG = Path(config.DIR_REGISTRY) / "entities.json"
_SLOT_MAP = {}          # card_type → w8_w9_interface.slot_mapping 字段列表（main 从 cards.json 注入）
PERSON_CONF_OK = {"A", "B", "C"}          # w8_w9_interface：B/C 可作候选页；D/E 需复核不产出
MARTYR_MARKERS = ("殉", "代死", "殉义", "死节", "殉主")
# W8 五段式必有节（对齐 templates/忠义殉主者.md §二 2.1-2.5）
SECTIONS = ("一、档案", "二、关系与阵营", "三、核心事件与结局", "四、证据与来源", "五、未定与边界")
SECTION_KEYS = ("dangan", "guanxi", "shijian", "zhengju", "weiding")


# ==================== 通用工具 ====================
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def display_map() -> dict:
    """registry/display_canonical.json → canonical→display（展示层，B-1/B-2；URL 仍 canonical）。"""
    if not DISPLAY_CANONICAL.exists():
        return {}
    payload = load_json(DISPLAY_CANONICAL)
    out = {}
    for e in payload.get("entries") or []:
        c, d = e.get("canonical"), e.get("display")
        if c and d and c != d:
            out[c] = d
    return out


def load_entity_map() -> dict:
    """registry/entities.json → {EID: {canonical,type}}（只读；用于卡面引用解析）。"""
    if not ENTITY_REG.exists():
        return {}
    try:
        payload = load_json(ENTITY_REG)
    except Exception:
        return {}
    out = {}
    for e in payload.get("entities") or []:
        eid = e.get("id")
        if eid:
            out[eid] = {"canonical": e.get("canonical") or eid, "type": e.get("type") or ""}
    return out


def load_slot_mapping(payload) -> dict:
    """cards.json#w8_w9_interface.W9_页型模板.slot_mapping → {ctype: [fields]}。"""
    try:
        iface = payload.get("w8_w9_interface") or {}
        slot = (iface.get("W9_页型模板") or {}).get("slot_mapping") or {}
        return {k: list(v) for k, v in slot.items() if isinstance(v, list)}
    except Exception:
        return {}


def load_relations() -> dict:
    """registry/relations/*.json → {edge_id: edge}（只读；用于关系引用解析）。"""
    idx = {}
    if not RELATIONS_DIR.exists():
        return idx
    for f in sorted(RELATIONS_DIR.glob("*.json")):
        try:
            payload = load_json(f)
        except Exception:
            continue
        for edge in payload.get("edges") or []:
            eid = edge.get("id")
            if eid:
                idx[eid] = edge
    return idx


class CardIndex:
    """卡片索引：stable_id/entity_ref → 卡；关系边 ID → edge。"""

    def __init__(self, cards, relations, entities=None):
        self.cards = cards
        self.by_stable = {}
        self.by_entity = {}
        for c in cards:
            meta = c.get("meta") or {}
            if meta.get("stable_id"):
                self.by_stable[meta["stable_id"]] = c
            if meta.get("entity_ref"):
                self.by_entity[meta["entity_ref"]] = c
        self.relations = relations or {}
        self.entities = entities or {}

    def resolve_ref(self, ref: str, prefer="stable") -> str:
        """stable_id / entity_ref / 关系边 → 可读名（找不到回退原 ID）。"""
        if not ref:
            return ""
        if ref in self.by_stable:
            return ((self.by_stable[ref].get("name") or {}).get("canonical")) or ref
        if ref in self.by_entity:
            return ((self.by_entity[ref].get("name") or {}).get("canonical")) or ref
        return ref

    def resolve_relation(self, ref: str, self_canonical: str) -> dict:
        """关系边引用 → {counterpart, predicate, confidence, loc, id, resolved}。"""
        edge = self.relations.get(ref)
        if not edge:
            return {"id": ref, "counterpart": ref, "predicate": "", "confidence": "",
                    "loc": "", "resolved": False}
        sub, obj = edge.get("subject"), edge.get("object")
        rel = edge.get("predicate") or edge.get("subtype") or ""
        locs = edge.get("locs") or ([edge["loc"]] if edge.get("loc") else [])
        counterpart = ""
        if sub == self_canonical:
            counterpart = obj
        elif obj == self_canonical:
            counterpart = sub
        return {"id": ref, "counterpart": counterpart or f"{sub or '?'}—{obj or '?'}",
                "predicate": rel, "confidence": edge.get("confidence") or "",
                "loc": locs[0] if locs else "", "resolved": bool(counterpart)}

    def resolve_entity(self, ref: str) -> str:
        ent = self.entities.get(str(ref))
        return (ent or {}).get("canonical") or str(ref)

    def resolve_any(self, ref: str) -> str:
        """卡引用（stable/entity）→卡名；registry EID → canonical；未知回退原 ID。"""
        if not ref:
            return ""
        if ref in self.by_stable:
            return ((self.by_stable[ref].get("name") or {}).get("canonical")) or ref
        if ref in self.by_entity:
            return ((self.by_entity[ref].get("name") or {}).get("canonical")) or ref
        if ref in self.entities:
            return (self.entities[ref] or {}).get("canonical") or ref
        return str(ref)

    def person_names(self, refs) -> list:
        return [self.resolve_any(str(r)) for r in (refs or []) if r]


# ==================== 页面构建 ====================
def _aliases(card) -> list:
    return [a.get("surface") if isinstance(a, dict) else str(a) for a in (card.get("aliases") or []) if a]


def _alias_summary(card, limit=12) -> str:
    """别名摘要：优先正式别名/语境称谓，语料变体（concordance）压缩为"等 N 个"。"""
    aliases = [a for a in (card.get("aliases") or []) if isinstance(a, dict) and a.get("surface")]
    primary = [a["surface"] for a in aliases if a.get("type") != "语料变体（concordance）"]
    variants = [a["surface"] for a in aliases if a.get("type") == "语料变体（concordance）"]
    if not primary and not variants:
        return "未明示（aliases 空）"
    shown = primary[:limit]
    if len(primary) < limit:
        shown += variants[: max(0, limit - len(shown))]
    total = len(primary) + len(variants)
    return "、".join(shown) + (f" 等 {total} 个（含语料变体）" if total > len(shown) else "")


def is_martyr(card) -> bool:
    ending = card.get("ending") or {}
    text = f"{ending.get('type') or ''}{ending.get('summary') or ''}"
    return any(m in text for m in MARTYR_MARKERS)


def page_type(card) -> str:
    return "忠义殉主者" if is_martyr(card) else "人物档案页"


def build_person_page(card, index: CardIndex, disp_map: dict, template_sha: str,
                      generated_at: str, demo: bool = True) -> dict:
    """person 卡 → W8 五段式页面（frontmatter dict + body lines + evidence）。"""
    meta = card.get("meta") or {}
    name = card.get("name") or {}
    canonical = name.get("canonical") or ""
    display = disp_map.get(canonical, canonical)
    stable = meta.get("stable_id") or ""
    ending = card.get("ending") or {}
    ttype = page_type(card)

    # ---- evidence 汇总（只存指针/ID，不贴原文）----
    evidence = []
    for s in meta.get("sources") or []:
        evidence.append({"kind": "source", "ref": s})
    supported = meta.get("supported_by") or {}
    for e in supported.get("entities") or []:
        evidence.append({"kind": "entity", "ref": e})
    for r in supported.get("relations") or []:
        evidence.append({"kind": "relation", "ref": r})
    for ev in supported.get("events") or []:
        evidence.append({"kind": "event", "ref": ev})
    fa = card.get("first_appearance") or {}
    if fa.get("loc_r"):
        evidence.append({"kind": "pn", "ref": fa["loc_r"]})
    age = card.get("age_anchor") or {}
    if age.get("loc"):
        evidence.append({"kind": "pn", "ref": age["loc"]})
    for r in (card.get("life_events") or [])[:10]:
        if isinstance(r, str):
            evidence.append({"kind": "event", "ref": r})

    # ---- 关系与阵营 ----
    rel_rows = []
    for ref in card.get("teachers") or []:
        rr = index.resolve_relation(str(ref), canonical)
        rel_rows.append(("师承", rr["counterpart"], rr["id"] + (f" · {rr['loc']}" if rr["loc"] else ""),
                         rr["confidence"] or "—"))
    for ref in card.get("disciples") or []:
        rr = index.resolve_relation(str(ref), canonical)
        rel_rows.append(("传人", rr["counterpart"], rr["id"] + (f" · {rr['loc']}" if rr["loc"] else ""),
                         rr["confidence"] or "—"))
    for label, key in (("亲属", "kinship"), ("情缘", "romance")):
        for ref in card.get(key) or []:
            rr = index.resolve_relation(str(ref), canonical)
            rel_rows.append((label, rr["counterpart"], rr["id"] + (f" · {rr['loc']}" if rr["loc"] else ""),
                             rr["confidence"] or "—"))
    for fh in card.get("faction_history") or []:
        fname = index.resolve_ref(fh.get("faction_ref") or "")
        edge_ref = fh.get("edge_ref") or ""
        src = edge_ref or (fh.get("role") or "门派归属（推导）")
        rel_rows.append(("门派/阵营", fname, str(src), fh.get("conf") or "—"))
    seniority = card.get("seniority") or {}
    for lab in seniority.get("labels") or []:
        rel_rows.append(("辈分", f"相对 {lab.get('relative_to') or '?'}",
                         f"{lab.get('value') or '?'}（规则 {lab.get('rule') or '?'}）",
                         lab.get("confidence") or "—"))

    # 武功/招式（卡面投影；w8_w9_interface core_facts 的 type-specific 数组）
    arts_rows = []
    seen_art = set()
    for a in card.get("arts") or []:
        art_ref = a.get("art_ref") or ""
        art_name = index.resolve_ref(art_ref) if art_ref else (a.get("art_surface") or "")
        row = (art_name, a.get("verb") or "", a.get("conf") or "")
        if row[0] and row[0] not in seen_art:
            seen_art.add(row[0])
            arts_rows.append(row)

    # ---- 三、核心事件与结局（人物页；殉主页型换"殉主事件"）----
    event_lines = []
    if ttype == "忠义殉主者":
        event_lines += ["- **所殉对象**：未明示（卡面关系字段未给主仆/结义边；不虚构）",
                        "- **殉身事件**：未明示（life_events 空，D03 事件流未建）"]
    event_lines += [
        f"- **事件流**：未明示——`life_events` 为空（N10 unfillable：上游 #4a 事件流未建；本页不写事件叙事）",
        f"- **时点锚**：{age.get('display') or '时点未锚'}"
        + (f"（{age.get('age')} 岁，{age.get('loc')}，置信 {age.get('confidence') or '?'}，tp_id {age.get('tp_id') or '?'}）"
           if age.get("age") is not None else "（卡面无年龄锚）"),
        f"- **结局**：{ending.get('type') or '未明示'}"
        + (f"（{ending.get('summary')}）" if ending.get("summary") else "")
        + (f"；事件引用 {ending.get('event_ref')}" if ending.get("event_ref") else ""),
        f"- **首见**：{(fa.get('book') or '?')} · {fa.get('loc_r') or '未明示'}（PN 指针）",
    ]
    if "死亡" in (ending.get("type") or ""):
        event_lines.append("- ⚠ 死亡线索为 **N5 杀害边候选，未经事件层核实（D03）**；本页不写成已确证死亡。")

    # ---- 四、证据与来源 ----
    src_lines = ["| 类型 | 引用 |", "|---|---|"]
    seen = set()
    for ev in evidence:
        key = (ev["kind"], ev["ref"])
        if key in seen:
            continue
        seen.add(key)
        src_lines.append(f"| {ev['kind']} | {ev['ref']} |")
    src_lines += [
        "",
        f"- 可信度：**{meta.get('confidence') or '?'}**；发布状态：{meta.get('publish_state') or 'draft'}",
        f"- 版本：data_version `{meta.get('data_version') or '?'}` / rule_version `{meta.get('rule_version') or '?'}`",
        "- 纪律：**引文只存指针，页面不贴原文**（R1/R2）；`quotes[]` 为 W7 核验入口（本页为空，待撰写阶段填入）。",
    ]

    # ---- 五、未定与边界 ----
    unfillable = ["identity_tags（D08 身份树未建）", "life_events（#4a 事件流未建）",
                  "relational_sku_refs（Relational SKU 未生成）"]
    edge_lines = [
        f"- 字段缺省：{'、'.join(unfillable)}；缺省 = 「未明示」≠「无」。",
        "- 关系引用：只写 ID/定位符，不重算上游（K6）；weak 派生项标 derived，不混人工边。",
        f"- 结局：{ending.get('type') or '未明示'}（未明示不等于无）。",
        "- 已知冲突：暂无（N8 一致性 lint 未报）。",
    ]
    if demo:
        edge_lines.append("- **demo：本页 `demo: true`，不进入发布库**（R4/K3）；发布需人工签核后改 demo=false + publish_state=approved。")

    body = [
        f"# {display}",
        "",
        f"> {meta.get('proposition') or f'{display}（{canonical}）的人物档案页（卡面投影）。'}",
        "",
        f"**页型**：{ttype}（W8 五段式） · **证据等级**：{meta.get('confidence') or '?'} "
        f"· **卡**：`{stable}` · **状态**：{meta.get('publish_state') or 'draft'}"
        + ("（demo）" if demo else ""),
        "",
        "## 一、档案",
        "",
        f"- 规范名：**{canonical}**（canonical；URL/slug 保持 canonical）",
        f"- 展示名：**{display}**（display 层；B-1/B-2）",
        f"- 别名：{_alias_summary(card)}",
        f"- 身份标签：未明示（identity_tags 空；D08 身份树未建）",
        f"- 首见：{(fa.get('book') or '?')} · {fa.get('loc_r') or '未明示'}",
        f"- 行经：{'、'.join(card.get('active_books') or []) or '未明示'}",
        f"- 结局：{ending.get('type') or '未明示'}"
        + (f"（{ending.get('summary')}）" if ending.get("summary") else ""),
        "",
        f"- **卡面摘要（brief，R1/R2 脱敏；W8 summary 槽位）**：{card.get('brief') or '未明示'}",
        "",
        "## 二、关系与阵营",
        "",
    ]
    if rel_rows:
        body += ["| 关系 | 对象 | 证据（ID/定位符） | 置信 |", "|---|---|---|---|"]
        body += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rel_rows]
        body += ["", "> 关系为卡面投影（K6）；只写 ID/定位符，不贴原文；weak/derived 项逐行标置信。"]
    else:
        body.append("未明示（卡面关系字段为空；不虚构）。")
    if arts_rows:
        body += ["", f"**武功/招式（卡面投影，共 {len(arts_rows)} 项）**：", "",
                 "| 武功 | 招式/用法 | 置信 |", "|---|---|---|"]
        body += [f"| {a} | {b or '—'} | {c or '—'} |" for a, b, c in arts_rows[:20]]
        if len(arts_rows) > 20:
            body.append(f"| … | 其余 {len(arts_rows) - 20} 项见卡面 | — |")
    body += ["", "## 三、核心事件与结局", ""]
    body += event_lines
    body += ["", "## 四、证据与来源", ""] + src_lines
    body += ["", "## 五、未定与边界", ""] + edge_lines
    # 作者按语（有门槛；默认省略）
    if meta.get("confidence") in ("A", "B") and ending.get("type") not in (None, "未明示"):
        body += ["", "## 附：作者按语（有依据才写，≤120 字）", "",
                 "（本页按语待人工撰写：需 ≥1 条 E1 明文 + 无冲突；当前默认省略，不代写评价。）"]

    # ---- frontmatter ----
    slots = list(SECTIONS)
    fm = {
        "page_type": ttype,
        "page_schema": PAGE_SCHEMA,
        "template_ref": "templates/忠义殉主者.md",
        "template_page_type": "忠义殉主者",
        "template_sha256_12": template_sha[:12],
        "card_ref": stable,
        "entity_ref": meta.get("entity_ref") or "",
        "canonical": canonical,
        "display": display,
        "slug": canonical,
        "book_scope": list(card.get("active_books") or []),
        "confidence": meta.get("confidence") or "",
        "publish_state": meta.get("publish_state") or "draft",
        "demo": bool(demo),
        "demo_note": "demo 数据，不进入发布库（R4/K3）" if demo else "",
        "data_version": meta.get("data_version") or "",
        "rule_version": meta.get("rule_version") or "",
        "generated_by": GENERATED_BY,
        "generated_at": generated_at,
        "sections": slots,
        "evidence": evidence,
        "quotes": [],
        "quote_status": "pending",
        "quote_note": "卡面按 R1/R2 脱敏无原文片段；引文由撰写阶段填入 text+cited_pn 后交 W7 核验",
        "used_cards": sorted({stable} | {
            index.by_entity[fh.get("faction_ref")].get("meta", {}).get("stable_id")
            for fh in (card.get("faction_history") or [])
            if fh.get("faction_ref") in index.by_entity
        } | {
            index.by_stable[ref].get("meta", {}).get("stable_id")
            for ref in [a.get("art_ref") for a in (card.get("arts") or []) if a.get("art_ref")]
            if ref in index.by_stable
        }),
    }
    return {"frontmatter": fm, "body": body, "card_ref": stable,
            "entity_ref": meta.get("entity_ref") or "", "canonical": canonical,
            "display": display, "page_type": ttype, "confidence": meta.get("confidence") or "",
            "demo": bool(demo), "evidence_count": len(evidence),
            "relations_count": len(rel_rows)}



# ==================== batch2：faction/art/artifact/manual 页型 ====================
def _fmt(v, limit=120) -> str:
    if v is None or v == "" or v == [] or v == {}:
        return "未明示"
    if isinstance(v, list):
        return "、".join(str(x) for x in v[:12]) or "未明示"
    if isinstance(v, dict):
        return "；".join(f"{k}={_fmt(x, 40)}" for k, x in list(v.items())[:8])
    s = str(v)
    return s if len(s) <= limit else s[:limit] + "…"


def _table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return out


def _evidence_of(card, extra_locs=None) -> list:
    meta = card.get("meta") or {}
    out = []
    for s in meta.get("sources") or []:
        out.append({"kind": "source", "ref": s})
    sup = meta.get("supported_by") or {}
    for e in sup.get("entities") or []:
        out.append({"kind": "entity", "ref": e})
    for r in sup.get("relations") or []:
        out.append({"kind": "relation", "ref": r})
    for ev in sup.get("events") or []:
        out.append({"kind": "event", "ref": ev})
    fa = card.get("first_appearance") or {}
    if fa.get("loc_r"):
        out.append({"kind": "pn", "ref": fa["loc_r"]})
    for loc in extra_locs or []:
        if loc:
            out.append({"kind": "pn", "ref": loc})
    seen, uniq = set(), []
    for ev in out:
        key = (ev["kind"], ev["ref"])
        if key not in seen:
            seen.add(key)
            uniq.append(ev)
    return uniq


def _identity_lines(card, disp_map) -> list:
    name = card.get("name") or {}
    canonical = name.get("canonical") or ""
    meta = card.get("meta") or {}
    fa = card.get("first_appearance") or {}
    display = disp_map.get(canonical, canonical)
    return [
        f"- 规范名：**{canonical}**（canonical；URL/slug 保持 canonical）",
        f"- 展示名：**{display}**（display 层；B-1/B-2）",
        f"- 别名：{_alias_summary(card)}",
        f"- 首见：{(fa.get('book') or '?')} · {fa.get('loc_r') or '未明示'}（PN 指针）",
        f"- 行经：{'、'.join(card.get('active_books') or []) or '未明示'}",
        f"- 模块：{meta.get('proposition') or '未明示'}",
    ]


def _assemble_page(card, index, disp_map, template_sha, generated_at, demo,
                   ctype, sec, unfillable) -> dict:
    meta = card.get("meta") or {}
    name = card.get("name") or {}
    canonical = name.get("canonical") or ""
    display = disp_map.get(canonical, canonical)
    stable = meta.get("stable_id") or ""
    ptype = TYPE_PAGE_TYPE[ctype]
    evidence = _evidence_of(card, sec.pop("_extra_locs", []))
    used = set(sec.pop("_used_cards", []))
    used.add(stable)
    # 四、证据与来源
    src = ["| 类型 | 引用 |", "|---|---|"]
    src += [f"| {e['kind']} | {e['ref']} |" for e in evidence]
    src += ["", f"- 可信度：**{meta.get('confidence') or '?'}**；"
                f"发布状态：{meta.get('publish_state') or 'draft'}",
            f"- 版本：data_version `{meta.get('data_version') or '?'}` / "
            f"rule_version `{meta.get('rule_version') or '?'}`",
            "- 纪律：**引文只存指针，页面不贴原文**（R1/R2）；`quotes[]` 为 W7 核验入口。"]
    # 五、未定与边界
    edge = [
        f"- 字段缺省：{'、'.join(unfillable)}；缺省 = 「未明示」≠「无」。",
        "- 引用口径：只写卡/实体/边 ID 与 PN 指针，不重算上游（K6）；派生字段逐行标 derived/置信。",
        "- 类型槽位：见 frontmatter `slot_fields`（w8_w9_interface.W9_页型模板.slot_mapping）。",
    ]
    if demo:
        edge.append("- **demo：本页 `demo: true`，不进入发布库**（R4/K3）；发布需人工签核。")
    body = [
        f"# {display}", "",
        f"> {meta.get('proposition') or f'{display}（{canonical}）的{ptype}（卡面投影）。'}", "",
        f"**页型**：{ptype}（W8 五段式） · **证据等级**：{meta.get('confidence') or '?'} "
        f"· **卡**：`{stable}` · **状态**：{meta.get('publish_state') or 'draft'}"
        + ("（demo）" if demo else ""), "",
        "## 一、档案", "", *sec.get("一", []), "",
        "## 二、关系与阵营", "", *sec.get("二", []), "",
        "## 三、核心事件与结局", "", *sec.get("三", []), "",
        "## 四、证据与来源", "", *src, "",
        "## 五、未定与边界", "", *edge,
    ]
    fm = {
        "page_type": ptype, "page_schema": PAGE_SCHEMA,
        "template_ref": "templates/忠义殉主者.md", "template_page_type": "忠义殉主者",
        "template_sha256_12": template_sha[:12],
        "card_ref": stable, "entity_ref": meta.get("entity_ref") or "",
        "canonical": canonical, "display": display, "slug": canonical,
        "card_type": ctype,
        "book_scope": list(card.get("active_books") or []),
        "confidence": meta.get("confidence") or "",
        "publish_state": meta.get("publish_state") or "draft",
        "demo": bool(demo),
        "demo_note": "demo 数据，不进入发布库（R4/K3）" if demo else "",
        "data_version": meta.get("data_version") or "",
        "rule_version": meta.get("rule_version") or "",
        "generated_by": GENERATED_BY, "generated_at": generated_at,
        "sections": list(SECTIONS),
        "slot_fields": list(_SLOT_MAP.get(ctype, [])),
        "evidence": evidence, "quotes": [], "quote_status": "pending",
        "quote_note": "卡面按 R1/R2 脱敏无原文片段；引文由撰写阶段填入 text+cited_pn 后交 W7 核验",
        "used_cards": sorted(used),
    }
    return {"frontmatter": fm, "body": body, "card_ref": stable,
            "entity_ref": meta.get("entity_ref") or "", "canonical": canonical,
            "display": display, "page_type": ptype, "card_type": ctype,
            "confidence": meta.get("confidence") or "", "demo": bool(demo),
            "evidence_count": len(evidence), "slot_fields": list(_SLOT_MAP.get(ctype, []))}


def _build_faction(card, index, disp_map, tpl_sha, gen_at, demo):
    meta = card.get("meta") or {}
    sec = {"一": [], "二": [], "三": []}
    sec["一"] += _identity_lines(card, disp_map)
    sec["一"] += [f"- 类型：{_fmt(card.get('faction_type'))}（#8 门派树未建，启发式）",
                  f"- 存续状态：{_fmt((card.get('status') or {}).get('value'))}"]
    sec["一"] += ["", f"- **卡面摘要（brief，R1/R2 脱敏；W8 summary 槽位）**：{card.get('brief') or '未明示'}"]
    # 二：镇派武功 + 支派联盟 + 成员规模 + 据点
    rows = []
    for a in card.get("signature_arts") or []:
        rows.append((index.resolve_any(a.get("art_ref") or ""), a.get("conf") or "—"))
    if rows:
        sec["二"] += [f"**镇派武功（signature_arts，卡面投影，共 {len(rows)} 项）**：", ""]
        sec["二"] += _table(rows, ("武功", "置信"))
    else:
        sec["二"].append("- 镇派武功：未明示（signature_arts 空）")
    ba = [index.resolve_any(x if isinstance(x, str) else (x.get("faction_ref") or x.get("ref") or ""))
          for x in card.get("branch_alliance") or []]
    sec["二"].append(f"- 支派/联盟：{_fmt([x for x in ba if x])}")
    ms = card.get("member_stat") or {}
    sec["二"].append(f"- 成员规模（member_stat）：{_fmt(ms)}")
    sh = card.get("strongholds") or []
    if sh:
        rows = [(x.get("place_ref") or "?", x.get("conf") or "—", x.get("basis") or "")
                for x in sh[:20]]
        sec["二"] += ["", "**据点（strongholds；tagged 共现启发式，非组织驻地谓词）**：", ""]
        sec["二"] += _table(rows, ("地点", "置信", "依据"))
        if len(sh) > 20:
            sec["二"].append(f"- … 其余 {len(sh) - 20} 处见卡面 strongholds")
    else:
        sec["二"].append("- 据点：未明示（strongholds 空）")
    # 三：源流 / 存续 / 任职
    sec["三"] += ["- 源流（lineage）：未明示（卡面 lineage 为空；门派世系考订表 #8 未迁）",
                  f"- 存续（status）：{_fmt((card.get('status') or {}).get('value'))}",
                  "- 任职/掌门（继任链）：未明示（N5 任职边稀疏，D06 #30 覆盖不足）",
                  f"- 据点数量：{len(sh)} 处（tagged 共现启发式，非定版驻地）"]
    used = [a.get("art_ref") for a in card.get("signature_arts") or [] if a.get("art_ref")]
    used += [x if isinstance(x, str) else (x.get("faction_ref") or x.get("ref"))
             for x in card.get("branch_alliance") or []]
    sec["_used_cards"] = used
    extra_locs = []
    if meta.get("stable_id"):
        extra_locs.append("")  # 占位：据点无 loc，不虚构
    unfillable = ["lineage（门派世系考订表 #8 未迁）", "timeline（门派事件流未建）",
                  "branch_alliance（派系联盟边未建）", "任职链（N5 任职边稀疏）"]
    return _assemble_page(card, index, disp_map, tpl_sha, gen_at, demo, "faction", sec, unfillable)


def _build_art(card, index, disp_map, tpl_sha, gen_at, demo):
    sec = {"一": [], "二": [], "三": []}
    sec["一"] += _identity_lines(card, disp_map)
    sec["一"] += [f"- 品类：{_fmt(card.get('category'))}（名称后缀启发式；#8 武功树未建）",
                  f"- 品级：{_fmt(card.get('grade'))}（依据：{_fmt(card.get('grade_basis'))}）"]
    sec["一"] += ["", f"- **卡面摘要（brief，R1/R2 脱敏；W8 summary 槽位）**：{card.get('brief') or '未明示'}"]
    creator = card.get("creator") or {}
    proc = card.get("inheritance_chain") or []
    prac = card.get("practitioners") or []
    if creator:
        if creator.get("person_ref"):
            sec["二"].append(f"- 创派/传下：{index.resolve_any(creator['person_ref'])}"
                             f"（{creator.get('conf') or '—'}；{_fmt(creator.get('note'))}）")
        else:
            sec["二"].append(f"- 创派/传下：{_fmt(creator.get('type') or creator)}")
    else:
        sec["二"].append("- 创派/传下：未明示")
    if proc:
        rows = []
        for x in proc:
            if isinstance(x, dict):
                rows.append((index.resolve_any(x.get("person_ref") or x.get("ref") or ""),
                             x.get("conf") or "—", _fmt(x.get("basis"))))
            else:
                rows.append((index.resolve_any(str(x)), "—", ""))
        sec["二"] += ["", f"**传承层级（inheritance_chain，共 {len(rows)} 项）**：", ""]
        sec["二"] += _table(rows, ("传承者", "置信", "依据"))
    else:
        sec["二"].append("- 传承层级（inheritance_chain）：未明示（inheritance_chain 空）")
    if prac:
        sec["二"].append(f"- 修习者（practitioners）：{_fmt([index.resolve_any(p.get('person_ref') if isinstance(p, dict) else p) for p in prac[:12]])}")
    else:
        sec["二"].append("- 修习者（practitioners）：未明示（practitioners 空；修习事件层未建）")
    moves = card.get("moves") or []
    if moves:
        rows = []
        for m in moves[:20]:
            used_by = [index.resolve_any(x) for x in (m.get("used_by") or [])]
            rows.append((m.get("move_name") or m.get("move_ref") or "?", _fmt(used_by), m.get("conf") or "—"))
        sec["三"] += [f"**招式（moves，共 {len(moves)} 条）**：", ""]
        sec["三"] += _table(rows, ("招式", "使用者", "置信"))
    else:
        sec["三"].append("- 招式（moves）：未明示（moves 空；招式表未关联）")
    rec = card.get("recorded_in") or []
    if rec:
        sec["三"].append(f"- 秘籍/文书（recorded_in）：{_fmt([index.resolve_any(r) for r in rec])}")
    else:
        sec["三"].append("- 秘籍/文书（recorded_in）：未明示")
    sec["三"].append(f"- 层级（hierarchy）：{_fmt(card.get('hierarchy'))}")
    used = [a.get("art_ref") for a in []]  # noqa
    used += [r for r in rec]
    used += [x.get("person_ref") for x in proc if isinstance(x, dict) and x.get("person_ref")]
    sec["_used_cards"] = used
    unfillable = ["moves（招式表仅 40/852 卡有映射）", "practitioners（修习者，事件层/掌握边稀疏）",
                  "creator（852/852 卡为未明）", "grade（品级需战绩事件支撑）"]
    return _assemble_page(card, index, disp_map, tpl_sha, gen_at, demo, "art", sec, unfillable)


def _build_artifact(card, index, disp_map, tpl_sha, gen_at, demo):
    sec = {"一": [], "二": [], "三": []}
    sec["一"] += _identity_lines(card, disp_map)
    sec["一"] += [f"- 器类：{_fmt(card.get('kind'))}",
                  f"- 级品：{_fmt(card.get('grade'))}（依据：{_fmt(card.get('grade_basis'))}）"]
    sec["一"] += ["", f"- **卡面摘要（brief，R1/R2 脱敏；W8 summary 槽位）**：{card.get('brief') or '未明示'}"]
    forge = card.get("forge") or {}
    if forge:
        if forge.get("smith_ref"):
            sec["二"].append(f"- 铸造者：{index.resolve_any(forge['smith_ref'])}"
                             f"（置信 {forge.get('conf') or '—'}；"
                             f"地点 {_fmt(forge.get('place_ref'))}；事件 {_fmt(forge.get('event_ref'))}）")
        else:
            sec["二"].append(f"- 铸造：{_fmt(forge.get('type') or forge)}")
    else:
        sec["二"].append("- 铸造：未明示")
    chain = card.get("chain") or []
    if chain:
        rows = []
        for x in chain[:20]:
            rows.append((x.get("verb") or "?", _fmt(index.person_names(x.get("persons"))),
                         f"{x.get('book') or '?'}·{x.get('loc_r') or x.get('loc') or '—'}",
                         x.get("conf") or "—"))
        sec["二"] += ["", f"**流转/持有链（chain，共 {len(chain)} 段）**：", ""]
        sec["二"] += _table(rows, ("动作", "涉及人物", "定位", "置信"))
        if len(chain) > 20:
            sec["二"].append(f"- … 其余 {len(chain) - 20} 段见卡面 chain")
    else:
        sec["二"].append("- 流转/持有链（chain）：未明示（chain 空）")
    cw = card.get("current_whereabouts") or {}
    sec["三"] += [f"- 结局/下落（current_whereabouts）：{_fmt(cw.get('status'))}",
                  f"- 级品：{_fmt(card.get('grade'))}（{_fmt(card.get('grade_basis'))}）",
                  f"- 流转段数：{len(chain)}；铸造者："
                  f"{index.resolve_any(forge.get('smith_ref')) if forge.get('smith_ref') else '未明示'}"]
    used = []
    sec["_used_cards"] = used
    locs = [x.get("loc_r") for x in chain[:10] if x.get("loc_r")]
    sec["_extra_locs"] = locs
    unfillable = ["forge.place_ref/event_ref（null）", "forge（193/226 卡为锻造未明）",
                  "chain persons 覆盖率部分为空", "current_whereabouts.loc_ref（null）"]
    return _assemble_page(card, index, disp_map, tpl_sha, gen_at, demo, "artifact", sec, unfillable)


def _build_manual(card, index, disp_map, tpl_sha, gen_at, demo):
    sec = {"一": [], "二": [], "三": []}
    sec["一"] += _identity_lines(card, disp_map)
    sec["一"] += [f"- 状态：{_fmt((card.get('status') or {}).get('value'))}"]
    sec["一"] += ["", f"- **卡面摘要（brief，R1/R2 脱敏；W8 summary 槽位）**：{card.get('brief') or '未明示'}"]
    author = card.get("author") or {}
    if author:
        if author.get("person_ref"):
            sec["二"].append(f"- 作者：{index.resolve_any(author['person_ref'])}"
                             f"（置信 {author.get('conf') or '—'}；{_fmt(author.get('note'))}）")
        else:
            sec["二"].append(f"- 作者：{_fmt(author.get('type') or author)}")
    else:
        sec["二"].append("- 作者：未明示")
    holders = card.get("holders") or []
    prov = card.get("provenance") or []
    sec["二"].append(f"- 持有者（holders）：{_fmt([index.resolve_any(h.get('person_ref') if isinstance(h, dict) else h) for h in holders])}")
    sec["二"].append(f"- 来历/传承（provenance）：{_fmt([index.resolve_any(p.get('ref') if isinstance(p, dict) else p) for p in prov])}")
    ca = card.get("content_arts") or []
    if ca:
        rows = []
        for x in ca[:20]:
            rows.append((index.resolve_any(x.get("art_ref") or ""), x.get("conf") or "—",
                         _fmt(x.get("basis"))))
        sec["三"] += [f"**内容武功（content_arts，共 {len(ca)} 项）**：", ""]
        sec["三"] += _table(rows, ("武功", "置信", "依据"))
    else:
        sec["三"].append("- 内容武功（content_arts）：未明示（content_arts 空）")
    locs = card.get("locations") or []
    if locs:
        rows = [(x.get("place_ref") or "?", x.get("conf") or "—", _fmt(x.get("basis")))
                for x in locs[:20]]
        sec["三"] += ["", f"**藏处/相关地点（locations，共 {len(locs)} 处）**：", ""]
        sec["三"] += _table(rows, ("地点", "置信", "依据"))
    else:
        sec["三"].append("- 藏处/相关地点（locations）：未明示")
    sec["三"].append(f"- 状态：{_fmt((card.get('status') or {}).get('value'))}")
    used = [x.get("art_ref") for x in ca if x.get("art_ref")]
    sec["_used_cards"] = used
    unfillable = ["holders（21 卡中多数为空）", "provenance（来历链未建）",
                  "author（作者未明/托名常态）", "locations（tagged 共现启发式，非藏处谓词）"]
    return _assemble_page(card, index, disp_map, tpl_sha, gen_at, demo, "manual", sec, unfillable)


def build_page(card, index: CardIndex, disp_map: dict, template_sha: str,
               generated_at: str, demo: bool = True) -> dict:
    """统一分发：person/faction/art/artifact/manual 五类卡页型（batch2 完成四类）。"""
    ctype = (card.get("meta") or {}).get("card_type") or ""
    builders = {"person": build_person_page, "faction": _build_faction, "art": _build_art,
                "artifact": _build_artifact, "manual": _build_manual}
    fn = builders.get(ctype)
    if fn is None:
        return {"interface": True, "card_type": ctype,
                "card_ref": (card.get("meta") or {}).get("stable_id") or "",
                "reason": f"interface_not_implemented:{ctype}",
                "note": "五类卡页型；未知类型仅登记接口"}
    return fn(card, index, disp_map, template_sha, generated_at, demo)


# ==================== YAML 渲染（不依赖第三方库） ====================
_YAML_SPECIAL = re.compile(r"[:#\[\]{},&*!|>'\"%@`]|^\s|\s$|[\n\r\t]")


def _yaml_scalar(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s == "" or _YAML_SPECIAL.search(s) or s.lower() in {"true", "false", "null", "~", "yes", "no"}:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def render_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            if not v:
                lines.append(f"{k}: []")
            else:
                lines.append(f"{k}:")
                for item in v:
                    if isinstance(item, dict):
                        first = True
                        for ik, iv in item.items():
                            prefix = "  - " if first else "    "
                            lines.append(prefix + f"{ik}: {_yaml_scalar(iv)}")
                            first = False
                    else:
                        lines.append(f"  - {_yaml_scalar(item)}")
        elif isinstance(v, dict):
            lines.append(f"{k}:")
            for ik, iv in v.items():
                lines.append(f"  {ik}: {_yaml_scalar(iv)}")
        else:
            lines.append(f"{k}: {_yaml_scalar(v)}")
    lines.append("---")
    return "\n".join(lines)


def render_page(page: dict) -> str:
    return render_frontmatter(page["frontmatter"]) + "\n\n" + "\n".join(page["body"]).rstrip() + "\n"


def page_equivalent(old: str, new: str) -> bool:
    """幂等判定：忽略仅 `generated_at` 行差异（同一卡/模板/数据 → 视为未变，不重写不备份）。"""
    if old == new:
        return True

    def norm(s: str) -> str:
        return "\n".join(line for line in s.splitlines() if not line.startswith("generated_at:"))

    return norm(old) == norm(new)


# ==================== 选择/统计 ====================
def person_cards(cards, confidence_ok=PERSON_CONF_OK):
    """筛选可生成 person 卡；返回 (eligible, skipped[list])。"""
    eligible, skipped = [], []
    for c in cards:
        meta = c.get("meta") or {}
        if (meta.get("card_type") or "") != "person":
            continue
        cid = meta.get("stable_id") or ""
        canonical = (c.get("name") or {}).get("canonical") or ""
        if not cid:
            skipped.append({"card": canonical or "?", "reason": "missing_stable_id"})
            continue
        if not canonical:
            skipped.append({"card": cid, "reason": "missing_canonical"})
            continue
        conf = meta.get("confidence") or ""
        if conf not in confidence_ok:
            skipped.append({"card": cid, "reason": f"confidence_{conf or 'missing'}_not_eligible"})
            continue
        if (meta.get("publish_state") or "") == "blocked":
            skipped.append({"card": cid, "reason": "publish_blocked"})
            continue
        eligible.append(c)
    return eligible, skipped


def build_all(cards, index, disp_map, template_sha, generated_at, demo=True, limit=None, select=None):
    eligible, skipped = person_cards(cards)
    selected = []
    wanted = set(select or [])
    for c in eligible:
        meta = c.get("meta") or {}
        if wanted and (meta.get("stable_id") not in wanted
                       and (c.get("name") or {}).get("canonical") not in wanted):
            continue
        selected.append(c)
    if limit is not None:
        selected = selected[:limit]
    pages = [build_page(c, index, disp_map, template_sha, generated_at, demo=demo) for c in selected]
    return pages, skipped, len(eligible)


def eligible_cards(cards, ctype, confidence_ok=PERSON_CONF_OK):
    """按卡型筛选可生成卡（confidence A/B/C、publish_state≠blocked、有 stable_id/canonical）。"""
    eligible, skipped = [], []
    for c in cards:
        meta = c.get("meta") or {}
        if (meta.get("card_type") or "") != ctype:
            continue
        cid = meta.get("stable_id") or ""
        canonical = (c.get("name") or {}).get("canonical") or ""
        if not cid:
            skipped.append({"card": canonical or "?", "reason": "missing_stable_id"})
            continue
        if not canonical:
            skipped.append({"card": cid, "reason": "missing_canonical"})
            continue
        conf = meta.get("confidence") or ""
        if conf not in confidence_ok:
            skipped.append({"card": cid, "reason": f"confidence_{conf or 'missing'}_not_eligible"})
            continue
        if (meta.get("publish_state") or "") == "blocked":
            skipped.append({"card": cid, "reason": "publish_blocked"})
            continue
        eligible.append(c)
    return eligible, skipped


def build_pages_by_type(cards, index, disp_map, template_sha, generated_at, types,
                        demo=True, limit=None, select=None) -> dict:
    """按卡型构建：{ctype: {pages, skipped, eligible, total}}。"""
    wanted = set(select or [])
    out = {}
    for ctype in types:
        eligible, skipped = eligible_cards(cards, ctype)
        selected = []
        for c in eligible:
            meta = c.get("meta") or {}
            if wanted and (meta.get("stable_id") not in wanted
                           and (c.get("name") or {}).get("canonical") not in wanted):
                continue
            selected.append(c)
        if limit is not None:
            selected = selected[:limit]
        pages = [build_page(c, index, disp_map, template_sha, generated_at, demo=demo)
                 for c in selected]
        out[ctype] = {"pages": pages, "skipped": skipped, "eligible": len(eligible),
                      "total": sum(1 for c in cards if (c.get("meta") or {}).get("card_type") == ctype)}
    return out


def slot_fill_stats(cards, ctype) -> dict:
    """w8_w9_interface slot_mapping 的逐槽位填充率（供 batch2 报告）。"""
    slots = _SLOT_MAP.get(ctype) or []
    if not slots:
        return {"slots": [], "by_slot": {}, "card_avg_fill": 0.0, "cards": 0}
    pool = [c for c in cards if (c.get("meta") or {}).get("card_type") == ctype]
    by_slot = {s: 0 for s in slots}
    card_fill = 0

    def get_path(card, path):
        cur = card
        for part in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                return None
        return cur

    for c in pool:
        filled = 0
        for s in slots:
            v = get_path(c, s)
            if v not in (None, "", [], {}):
                by_slot[s] += 1
                filled += 1
        card_fill += filled / max(1, len(slots))
    return {"slots": slots, "by_slot": by_slot, "cards": len(pool),
            "card_avg_fill": round(card_fill / max(1, len(pool)), 3)}


# ==================== 落盘（--apply） ====================
def _assert_inside(path: Path, parent: Path, what: str):
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        raise SystemExit(f"[W8] 安全断言失败：{what} 不在 {parent} 内：{path}")


def apply_pages(pages, out_dir: Path, backup_base: Path, run_id: str, unsafe_out=False) -> dict:
    out_dir = Path(out_dir)
    if not unsafe_out:
        _assert_inside(out_dir, CONTENT_DIR, "输出目录")
    person_dir = out_dir / "person"
    person_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(backup_base) / run_id / "person"
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "w8-apply-manifest-v0.1", "run_id": run_id,
                "out_dir": str(out_dir), "backup_dir": str(backup_dir),
                "files": [], "unchanged": [], "written": 0, "backed_up": 0}
    written = unchanged = backed_up = 0
    for page in pages:
        if page.get("interface"):
            continue
        name = page["card_ref"] + ".md"
        target = person_dir / name
        text = render_page(page)
        old = target.read_text(encoding="utf-8") if target.exists() else None
        if old is not None and page_equivalent(old, text):
            unchanged += 1
            manifest["unchanged"].append(name)
            continue
        if old is not None:
            bk = backup_dir / name
            bk.write_text(old, encoding="utf-8")
            old_sha, bk_sha = sha256_text(old), sha256_text(bk.read_text(encoding="utf-8"))
            if old_sha != bk_sha:
                raise SystemExit(f"[W8] 备份断言失败：{name} sha 不一致")
            backed_up += 1
            manifest["files"].append({"file": name, "backup": str(bk), "old_sha256": old_sha,
                                      "new_sha256": sha256_text(text)})
        else:
            manifest["files"].append({"file": name, "backup": "", "old_sha256": "",
                                      "new_sha256": sha256_text(text)})
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
        if sha256_text(target.read_text(encoding="utf-8")) != sha256_text(text):
            raise SystemExit(f"[W8] 回读断言失败：{name}")
        written += 1
    # person/_index.json（后续 EX/W 组消费的索引）
    index_path = person_dir / "_index.json"
    index_payload = {
        "schema": "w8-content-index-v0.1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generated_by": GENERATED_BY,
        "demo": all(p.get("demo", True) for p in pages if not p.get("interface")),
        "pages": [{
            "card_ref": p["card_ref"], "entity_ref": p.get("entity_ref"),
            "slug": p.get("canonical"), "display": p.get("display"),
            "page_type": p.get("page_type"), "confidence": p.get("confidence"),
            "demo": p.get("demo"), "path": f"content/person/{p['card_ref']}.md",
        } for p in pages if not p.get("interface")],
    }
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest.update({"written": written, "backed_up": backed_up, "unchanged": unchanged,
                     "index": str(index_path)})
    (Path(backup_base) / run_id / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def apply_pages_by_type(pages_by_type, out_dir: Path, backup_base: Path, run_id: str,
                        unsafe_out=False) -> dict:
    """batch2 落盘：逐类型写 content/<type>/、备份 + sha 断言 + 回读 + _index.json。"""
    out_dir = Path(out_dir)
    if not unsafe_out:
        _assert_inside(out_dir, CONTENT_DIR, "输出目录")
    run_backup = Path(backup_base) / run_id
    manifest = {"schema": "w8-apply-manifest-v0.2", "run_id": run_id,
                "out_dir": str(out_dir), "backup_dir": str(run_backup), "types": {}, "files": []}
    for ctype, info in pages_by_type.items():
        pages = info.get("pages") or []
        tdir = out_dir / ctype
        tdir.mkdir(parents=True, exist_ok=True)
        bdir = run_backup / ctype
        bdir.mkdir(parents=True, exist_ok=True)
        written = unchanged = backed_up = 0
        type_files = []
        for page in pages:
            if page.get("interface"):
                continue
            name = page["card_ref"] + ".md"
            target = tdir / name
            text = render_page(page)
            old = target.read_text(encoding="utf-8") if target.exists() else None
            if old is not None and page_equivalent(old, text):
                unchanged += 1
                continue
            if old is not None:
                bk = bdir / name
                bk.write_text(old, encoding="utf-8")
                old_sha = sha256_text(old)
                if old_sha != sha256_text(bk.read_text(encoding="utf-8")):
                    raise SystemExit(f"[W8] 备份断言失败：{ctype}/{name}")
                backed_up += 1
                type_files.append({"file": f"{ctype}/{name}", "backup": str(bk),
                                   "old_sha256": old_sha, "new_sha256": sha256_text(text)})
            else:
                type_files.append({"file": f"{ctype}/{name}", "backup": "",
                                   "old_sha256": "", "new_sha256": sha256_text(text)})
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, target)
            if sha256_text(target.read_text(encoding="utf-8")) != sha256_text(text):
                raise SystemExit(f"[W8] 回读断言失败：{ctype}/{name}")
            written += 1
        index_payload = {
            "schema": "w8-content-index-v0.1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "generated_by": GENERATED_BY, "card_type": ctype,
            "demo": True,
            "pages": [{
                "card_ref": p["card_ref"], "entity_ref": p.get("entity_ref"),
                "slug": p.get("canonical"), "display": p.get("display"),
                "page_type": p.get("page_type"), "confidence": p.get("confidence"),
                "demo": p.get("demo"), "path": f"content/{ctype}/{p['card_ref']}.md",
            } for p in pages if not p.get("interface")],
        }
        index_path = tdir / "_index.json"
        index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        manifest["types"][ctype] = {"written": written, "backed_up": backed_up,
                                    "unchanged": unchanged, "pages": len(pages),
                                    "index": str(index_path)}
        manifest["files"].extend(type_files)
    (run_backup / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    return manifest


def write_batch2_report(stats, type_stats, slot_fills, samples, applied_manifest=None) -> Path:
    """logs/qa/w8_pages_batch2_report.md：四类页数/槽位填充/样例/遗留。"""
    lines = [
        "# W8 波2 · 四类卡页型生成报告（faction/art/artifact/manual）",
        "",
        f"- 生成：{datetime.now().isoformat(timespec='seconds')} · 生成器：`{GENERATED_BY}`",
        f"- 模板：`templates/忠义殉主者.md`（五段式） · sha256_12=`{stats.get('template_sha256_12')}`",
        f"- cards：`{stats.get('cards_source')}` · 模式：**{stats.get('mode')}**",
        f"- 类型页数：{[f'{t} {type_stats.get(t, {}).get("generated", 0)} 页' for t in BATCH2_TYPES]}",
        "",
        "## 1 · 四类页数",
        "",
        "| 类型 | 页型 | 卡总量 | 可生成 | 已生成 | 跳过 | 页目录 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for t in BATCH2_TYPES:
        ts = type_stats.get(t, {})
        lines.append(f"| {t} | {TYPE_PAGE_TYPE[t]} | {ts.get('total', 0)} | {ts.get('eligible', 0)} | "
                     f"{ts.get('generated', 0)} | {ts.get('skipped', 0)} | content/{t}/ |")
    lines += ["", "卡型合计（四类）：" +
              f"{sum(type_stats.get(t, {}).get('generated', 0) for t in BATCH2_TYPES)} 页；"
              f"cards.json 卡型计数：" +
              str({t: type_stats.get(t, {}).get('total', 0) for t in BATCH2_TYPES})]
    lines += ["", "## 2 · 槽位填充（w8_w9_interface.W9_页型模板.slot_mapping）", "",
              "| 类型 | 卡数 | 平均槽位填充率 | 主要空槽位（Top） |",
              "|---|---:|---:|---|"]
    for t in BATCH2_TYPES:
        sf = slot_fills.get(t) or {}
        empty = [f"{s}（{sf['by_slot'].get(s, 0)}/{sf.get('cards', 0)}）"
                 for s in sf.get("slots", []) if sf["by_slot"].get(s, 0) == 0][:6]
        lines.append(f"| {t} | {sf.get('cards', 0)} | {sf.get('card_avg_fill', 0):.0%} | "
                     f"{'、'.join(empty) or '—'} |")
    lines += ["", "逐槽位填充（四类）：", ""]
    for t in BATCH2_TYPES:
        sf = slot_fills.get(t) or {}
        if not sf.get("slots"):
            continue
        lines += [f"**{t}**：", "",
                  "| 槽位 | 填充 | 填充率 |", "|---|---:|---:|"]
        for s in sf["slots"]:
            n = sf["by_slot"].get(s, 0)
            lines.append(f"| {s} | {n}/{sf['cards']} | {n / max(1, sf['cards']):.0%} |")
        lines.append("")
    lines += ["## 3 · 样例页（每类 1 页，frontmatter 键 + 五段式节标题）", ""]
    for t in BATCH2_TYPES:
        smp = samples.get(t)
        if not smp:
            lines.append(f"- {t}：无样例（可生成 0）")
            continue
        lines += [f"### {t} · `{smp['card_ref']}`（{smp['page_type']}）", "",
                  f"- canonical/display：{smp['canonical']} / {smp['display']}；"
                  f"confidence={smp['confidence']}；demo={smp['demo']}",
                  f"- frontmatter：{smp['fm_keys']}",
                  f"- 节标题：{smp['sections_ok']}",
                  "", "```markdown", smp["excerpt"], "```", ""]
    lines += ["## 4 · 落盘与幂等", ""]
    if applied_manifest:
        lines += [f"- run_id：`{applied_manifest.get('run_id')}`；"
                  f"备份：`{applied_manifest.get('backup_dir')}`",
                  "- 逐类型：" + str({t: {k: v.get(k) for k in ('pages', 'written', 'backed_up', 'unchanged')}
                                     for t, v in (applied_manifest.get('types') or {}).items()})]
    else:
        lines.append("- 本次为 dry-run，未写盘；`--apply` 时会逐类型备份 + sha256 断言 + 回读校验。")
    lines += ["", "## 5 · 遗留与边界", "",
              "1. 四类卡共 1,159 张（faction 60 / art 852 / artifact 226 / manual 21；任务单写 1,169，"
              "以当前 `registry/sku/cards.json` 的 card_index 计数为准，差异 10 张为上游卡集版本变化）。",
              "2. 槽位大面积为空为**上游未建**，非生成器遗漏：门派 lineage/timeline/branch_alliance（#8 门派树/世系）、"
              "武功 moves 40/852、practitioners 34/852、creator 852/852 未明、兵器 forge.place/event 为 null、"
              "秘籍 holders/provenance 多数空。页面按 SKILL 未知原则以「未明示」缺省，不虚构。",
              "3. demo：按任务与 person 批一致，四类页全部 `demo: true`、`publish_state` 沿用卡面 draft/in-review，"
              "不进入发布库（R4/K3）；cards.json#w8_w9_interface 的 `demo_isolation` 描述指真实发布卡，"
              "本批为 W8 演示批，以任务指令为准。",
              "4. 引用解析：卡引用走 CardIndex（stable/entity）；EID 人物走 registry/entities.json canonical；"
              "未解析项保留原 ID（K4 指针口径，不贴原文）。",
              "5. 与 person 批差异：person 仍由 `--type person` 维护（本批不重生成，避免动 batch1 的 367 页）；"
              "`--type all` 才会五类全量。",
              "6. 复现：`python scripts/generate_w8_pages.py --type batch2`（dry-run）→ `--apply`；"
              "或 `--type faction` 单类。",
              ""]
    out = Path(config.DIR_LOGS) / "qa" / "w8_pages_batch2_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ==================== 自检 ====================
def selftest() -> int:
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        ok = ok and bool(cond)

    print("[W8 selftest]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # 模板占位（读取真实模板做 sha；若缺失用临时）
        template = TEMPLATE if TEMPLATE.exists() else (td / "tpl.md")
        if not template.exists():
            template.write_text("# 五段式\n## 必有节\n", encoding="utf-8")
        tpl_sha = sha256_text(template.read_text(encoding="utf-8"))
        relations = {"测试书#R1": {"id": "测试书#R1", "subject": "甲", "object": "乙",
                                  "predicate": "师承", "confidence": "ok", "loc": "1:2"}}
        rich = {
            "name": {"canonical": "甲"},
            "aliases": [{"surface": "甲某"}, {"surface": "老甲"}],
            "identity_tags": [], "faction_history": [], "seniority": {"generation": 0, "labels": []},
            "teachers": ["测试书#R1"], "disciples": [], "kinship": [], "romance": [],
            "arts": [], "life_events": [], "age_anchor": {"book": "测试书", "ch": 1, "pn": 3,
                                                          "age": 30, "display": "三十岁",
                                                          "confidence": "low", "tp_id": "t-1",
                                                          "loc": "1:3"},
            "ending": {"type": "殉义", "summary": "为护义而死"}, "relational_sku_refs": [],
            "brief": "测试卡摘要（不含原文片段）。",
            "active_books": ["测试书"], "first_appearance": {"book": "测试书", "loc_r": "测试书#pn-r1.2"},
            "meta": {"stable_id": "card.person.t001", "entity_ref": "E-T-1", "card_type": "person",
                     "proposition": "甲为测试人物", "confidence": "B", "publish_state": "draft",
                     "sources": ["01g:E-T-1"], "data_version": "test.1", "rule_version": "test-rule",
                     "supported_by": {"entities": ["E-T-1"], "relations": [], "events": []}},
        }
        low = json.loads(json.dumps(rich))
        low["meta"]["stable_id"] = "card.person.t002"
        low["meta"]["confidence"] = "D"
        faction = {"name": {"canonical": "某派"}, "meta": {"stable_id": "card.faction.t003",
                                                          "entity_ref": "E-F-1", "card_type": "faction",
                                                          "confidence": "C", "publish_state": "draft"}}
        index = CardIndex([rich, low, faction], relations)
        disp = {"甲": "甲展示"}
        pages, skipped, eligible = build_all([rich, low, faction], index, disp, tpl_sha,
                                             "2026-11-05T00:00:00", demo=True)
        check("person 卡筛选（D 置信跳过）", any(s["reason"].startswith("confidence_D") for s in skipped)
              and len(pages) == 1, str(skipped))
        page = pages[0]
        text = render_page(page)
        fm = page["frontmatter"]
        check("frontmatter 关键字段", all(k in fm for k in (
            "page_type", "card_ref", "entity_ref", "canonical", "display", "slug", "demo",
            "quotes", "quote_status", "evidence", "sections", "confidence", "publish_state")),
            str(list(fm.keys())))
        check("display 与 canonical 分离", fm["display"] == "甲展示" and fm["canonical"] == "甲"
              and fm["slug"] == "甲")
        check("五段式必有节齐全", all(f"## {s}" in text for s in SECTIONS), SECTIONS)
        check("demo=true 且 draft", fm["demo"] is True and fm["publish_state"] == "draft")
        check("quotes[] 为空待 W7", fm["quotes"] == [] and fm["quote_status"] == "pending")
        check("证据含 PN 指针", any(e["kind"] == "pn" and "pn-r" in e["ref"] for e in fm["evidence"]))
        check("殉主页型分支", fm["page_type"] == "忠义殉主者" and "所殉对象" in text)
        check("关系行解析（师承→乙）", "| 师承 | 乙 |" in text, "relation")
        check("结局/死亡线索不越界", "殉义" in text)
        # 其它类型接口
        iface = build_page(faction, index, disp, tpl_sha, "2026-11-05T00:00:00")
        check("faction 卡已实现页型（batch2）", not iface.get("interface")
              and iface.get("page_type") == "门派档案页" and "## 一、档案" in render_page(iface))
        # 生成器安全：dry-run 不写盘
        dry_dir = td / "content_dry"
        pages2, _, _ = build_all([rich], index, disp, tpl_sha, "2026-11-05T00:00:00")
        check("dry-run 不创建目录", not dry_dir.exists())
        # apply 到临时目录：备份/回读/幂等
        out = td / "content"
        backup = td / "backup"
        pd = out / "person"
        pd.mkdir(parents=True, exist_ok=True)
        target = pd / "card.person.t001.md"
        target.write_text("old-content\n", encoding="utf-8")
        m1 = apply_pages(pages2, out, backup, "run1", unsafe_out=True)
        check("apply 写入 1 页", m1["written"] == 1 and target.exists())
        check("apply 备份已有页", m1["backed_up"] == 1
              and (backup / "run1" / "person" / target.name).exists())
        check("备份 sha 可校验", sha256_text("old-content\n") == sha256_text(
            (backup / "run1" / "person" / target.name).read_text(encoding="utf-8")))
        check("写后内容含五段式", "## 一、档案" in target.read_text(encoding="utf-8"))
        m2 = apply_pages(pages2, out, backup, "run2", unsafe_out=True)
        check("幂等（二次 apply unchanged）", m2["written"] == 0 and m2["unchanged"] == 1, str(m2))
        check("时间戳差异不触发重写",
              page_equivalent(render_page(pages2[0]),
                              render_page(build_page(rich, index, disp, tpl_sha, "2026-11-06T00:00:00"))))
        # 索引
        check("content 索引写入", (out / "person" / "_index.json").exists())
        # 不输出原文（卡面 brief 原样进页面摘要会含"测试卡摘要"；R1 检查只针对原文连续片段，
        # 这里断言页面不含"原文"测试标记）
        check("页面无原文标记", "【原文】" not in text)
    ok = _selftest_batch2() and ok
    print(f"[W8 selftest] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def _selftest_batch2() -> bool:
    """batch2 四类页型自检（合成卡，不写真实 content/）。"""
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        ok = ok and bool(cond)

    print("[W8 selftest · batch2]")
    global _SLOT_MAP
    saved_slots = _SLOT_MAP
    _SLOT_MAP = {t: ["name.canonical", "brief"] for t in BATCH2_TYPES}
    try:
        tpl_sha = "a" * 64
        entities = {"E1": {"canonical": "甲", "type": "@"}, "E2": {"canonical": "乙", "type": "@"}}
        cards = [
            {"name": {"canonical": "某派"}, "aliases": [], "faction_type": "门派",
             "signature_arts": [{"art_ref": "card.art.t1", "conf": "ok"}],
             "strongholds": [{"place_ref": "某山", "conf": "weak", "basis": "共现"}],
             "status": {"value": "未明示"}, "member_stat": {"metric": "x", "value": 0},
             "branch_alliance": [], "lineage": [], "timeline": [], "brief": "门派卡摘要。",
             "active_books": ["测试书"], "first_appearance": {"book": "测试书", "loc_r": "t#pn-r1.1"},
             "meta": {"stable_id": "card.faction.t1", "card_type": "faction", "confidence": "C",
                      "publish_state": "draft", "sources": ["#8"]}},
            {"name": {"canonical": "某掌"}, "aliases": [], "category": "掌法",
             "moves": [], "creator": {"type": "创派者未明"}, "inheritance_chain": [],
             "practitioners": [], "recorded_in": ["card.manual.t1"], "grade": None,
             "grade_basis": "未评", "hierarchy": None, "brief": "武功卡摘要。",
             "active_books": ["测试书"], "first_appearance": {"book": "测试书", "loc_r": "t#pn-r1.2"},
             "meta": {"stable_id": "card.art.t1", "card_type": "art", "confidence": "C",
                      "publish_state": "draft", "sources": ["#7"]}},
            {"name": {"canonical": "某剑"}, "kind": "剑", "grade": "神兵", "grade_basis": "明文",
             "forge": {"smith_ref": "E1", "place_ref": None, "event_ref": None, "conf": "strong"},
             "chain": [{"verb": "夺", "persons": ["E1", "E2"], "book": "测试书", "loc": "1:5",
                        "loc_r": "t#pn-r1.5", "conf": "strong"}],
             "current_whereabouts": {"status": "下落不明"}, "brief": "兵器卡摘要。",
             "active_books": ["测试书"], "first_appearance": {"book": "测试书", "loc_r": "t#pn-r1.3"},
             "meta": {"stable_id": "card.artifact.t1", "card_type": "artifact", "confidence": "B",
                      "publish_state": "draft", "sources": ["#6"]}},
            {"name": {"canonical": "某诀"}, "content_arts": [{"art_ref": "card.art.t1", "conf": "weak",
                                                             "basis": "共现"}],
             "author": {"person_ref": "E1", "conf": "weak", "note": "启发式"},
             "provenance": [], "holders": [{"person_ref": "E2"}], "status": {"value": "未明示"},
             "locations": [{"place_ref": "某山", "conf": "weak", "basis": "共现"}], "brief": "秘籍卡摘要。",
             "active_books": ["测试书"], "first_appearance": {"book": "测试书", "loc_r": "t#pn-r1.4"},
             "meta": {"stable_id": "card.manual.t1", "card_type": "manual", "confidence": "C",
                      "publish_state": "draft", "sources": ["#7"]}},
        ]
        index = CardIndex(cards, {}, entities=entities)
        built = {}
        for t in BATCH2_TYPES:
            card = next(c for c in cards if c["meta"]["card_type"] == t)
            page = build_page(card, index, {}, tpl_sha, "2026-11-05T00:00:00", demo=True)
            built[t] = page
            text = render_page(page)
            fm = page["frontmatter"]
            check(f"{t} 五段式节齐全", all(f"## {s}" in text for s in SECTIONS))
            check(f"{t} frontmatter 同 person 关键键",
                  all(k in fm for k in ("page_type", "card_ref", "entity_ref", "canonical",
                                        "display", "slug", "demo", "quotes", "quote_status",
                                        "evidence", "sections", "confidence", "publish_state",
                                        "template_sha256_12", "slot_fields")), str(list(fm)))
            check(f"{t} demo=true / quotes 空 / 证据非空",
                  fm["demo"] is True and fm["quotes"] == [] and bool(fm["evidence"]))
            check(f"{t} 页型标签", fm["page_type"] == TYPE_PAGE_TYPE[t])
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            out = td / "content"
            backup = td / "backup"
            m1 = apply_pages_by_type({t: {"pages": [built[t]]} for t in BATCH2_TYPES},
                                     out, backup, "run1", unsafe_out=True)
            check("batch2 apply 四类目录", all((out / t).is_dir() for t in BATCH2_TYPES))
            check("batch2 apply 四类 _index.json",
                  all((out / t / "_index.json").exists() for t in BATCH2_TYPES))
            check("batch2 apply 写入 4 页", m1["types"].get("faction", {}).get("written") == 1)
            m2 = apply_pages_by_type({t: {"pages": [built[t]]} for t in BATCH2_TYPES},
                                     out, backup, "run2", unsafe_out=True)
            check("batch2 幂等（二次 unchanged=4）",
                  sum(v.get("unchanged", 0) for v in m2["types"].values()) == 4)
    finally:
        _SLOT_MAP = saved_slots
    return ok


# ==================== CLI ====================
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="W8 精品页生成器（person + batch2 四类卡页型：faction/art/artifact/manual）")
    ap.add_argument("--apply", action="store_true", help="落盘（缺省 dry-run）")
    ap.add_argument("--selftest", action="store_true", help="自检（合成卡，不写盘）")
    ap.add_argument("--type", default="person", choices=list(SUPPORTED_TYPES) + ["all", "batch2"],
                    help="卡型（缺省 person；batch2=faction/art/artifact/manual；all=五类）")
    ap.add_argument("--cards", default=str(CARDS), help="cards.json 路径")
    ap.add_argument("--template", default=str(TEMPLATE), help="页型模板路径")
    ap.add_argument("--out-dir", default=str(CONTENT_DIR), help="输出目录（缺省 content/）")
    ap.add_argument("--backup-dir", default=str(BACKUP_ROOT), help="备份根目录（缺省 logs/qa/w8_content_backup/）")
    ap.add_argument("--limit", type=int, default=None, help="每类最多生成多少页（调试）")
    ap.add_argument("--select", action="append", default=None, help="按 stable_id/canonical 选择（可重复）")
    ap.add_argument("--sample", type=int, default=1, help="dry-run 打印样例页数（batch2 每类 1 页）")
    ap.add_argument("--run-id", default=None, help="apply 运行 ID（缺省时间戳）")
    ap.add_argument("--unsafe-out", action="store_true", help="允许写 content/ 之外的目录（仅调试）")
    ap.add_argument("--json-summary", action="store_true", help="输出 JSON 统计（便于报告/流水线）")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    t0 = time.time()
    cards_path = Path(args.cards)
    if not cards_path.exists():
        raise SystemExit(f"[W8] cards.json 不存在：{cards_path}")
    payload = load_json(cards_path)
    cards = payload.get("cards") or []
    global _SLOT_MAP
    _SLOT_MAP = load_slot_mapping(payload)
    if args.type == "all":
        types = list(SUPPORTED_TYPES)
    elif args.type == "batch2":
        types = list(BATCH2_TYPES)
    else:
        types = [args.type]

    template_path = Path(args.template)
    if not template_path.exists():
        raise SystemExit(f"[W8] 页型模板不存在：{template_path}")
    tpl_text = template_path.read_text(encoding="utf-8")
    if "五段式" not in tpl_text or "必有节" not in tpl_text:
        raise SystemExit(f"[W8] 模板校验失败（缺「五段式/必有节」标记）：{template_path}")
    tpl_sha = sha256_text(tpl_text)

    relations = load_relations()
    index = CardIndex(cards, relations, entities=load_entity_map())
    generated_at = datetime.now().isoformat(timespec="seconds")
    by_type = build_pages_by_type(cards, index, display_map(), tpl_sha, generated_at,
                                  types, demo=True, limit=args.limit, select=args.select)
    stats = {
        "schema": SCHEMA, "generated_at": generated_at,
        "cards_source": str(cards_path), "template": str(template_path),
        "template_sha256_12": tpl_sha[:12],
        "relations_loaded": len(relations),
        "slot_mapping_types": {t: len(_SLOT_MAP.get(t) or []) for t in types},
        "demo": True, "mode": "apply" if args.apply else "dry-run",
        "types": {}, "elapsed_sec": 0,
    }
    samples = {}
    type_stats = {}
    for t, info in by_type.items():
        pages = info["pages"]
        ts = {"total": info["total"], "eligible": info["eligible"],
              "generated": len(pages), "skipped": len(info["skipped"]),
              "skipped_reasons": dict(Counter(s["reason"] for s in info["skipped"])),
              "page_type": TYPE_PAGE_TYPE.get(t, ""), "pages": len(pages)}
        if not args.apply:
            new = changed = unchanged = 0
            for page in pages:
                if page.get("interface"):
                    continue
                target = Path(args.out_dir) / t / (page["card_ref"] + ".md")
                if not target.exists():
                    new += 1
                elif page_equivalent(target.read_text(encoding="utf-8"), render_page(page)):
                    unchanged += 1
                else:
                    changed += 1
            ts.update({"would_write": new + changed, "new": new, "changed": changed,
                       "unchanged": unchanged})
        stats["types"][t] = ts
        type_stats[t] = ts
        first = next((p for p in pages if not p.get("interface")), None)
        if first:
            rendered = render_page(first)
            body = rendered.split("\n---\n", 1)[1] if "\n---\n" in rendered else rendered
            chunks = re.split(r"\n(?=## )", body)
            preview = chunks[0][:400] + "\n" + "\n".join(c[:220] for c in chunks[1:6])
            samples[t] = {
                "card_ref": first["card_ref"], "canonical": first["canonical"],
                "display": first["display"], "page_type": first["page_type"],
                "confidence": first["confidence"], "demo": first["demo"],
                "fm_keys": list(first["frontmatter"].keys())[:20],
                "sections_ok": [s for s in SECTIONS if f"## {s}" in rendered],
                "excerpt": preview,
            }
    slot_fills = {t: slot_fill_stats(cards, t) for t in types if t != "person"}
    applied = None
    if args.apply:
        run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        applied = apply_pages_by_type(by_type, Path(args.out_dir), Path(args.backup_dir), run_id,
                                      unsafe_out=args.unsafe_out)
        for t, m in applied["types"].items():
            stats["types"].setdefault(t, {}).update({k: m[k] for k in ("written", "backed_up", "unchanged")})
        stats.update({"run_id": run_id, "backup_dir": applied["backup_dir"]})
        Path(STATS_OUT).parent.mkdir(parents=True, exist_ok=True)
        (Path(config.DIR_LOGS) / "qa" / "w8_generate_stats_batch2.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[W8] apply：run_id={run_id}；" +
              "；".join(f"{t} 写{m['written']}/备{m['backed_up']}/不变{m['unchanged']}"
                       for t, m in applied["types"].items()))
    else:
        for t, ts in type_stats.items():
            print(f"[W8] dry-run · {t}（{ts['page_type']}）：卡 {ts['total']} / 可生成 {ts['eligible']} / "
                  f"渲染 {ts['generated']} / 拟写 {ts.get('would_write', 0)}"
                  f"（new {ts.get('new', 0)} / changed {ts.get('changed', 0)} / "
                  f"unchanged {ts.get('unchanged', 0)}）/ skipped {ts['skipped']}")
        for t in types:
            if samples.get(t) and args.sample:
                print("\n" + "=" * 70 + f"\n样例页 · {t}\n" + "=" * 70)
                print(samples[t]["excerpt"][:1800])
        print(f"[W8] 提示：确认后加 --apply 落盘（自动备份到 {args.backup_dir}/<run_id>/）")
    stats["elapsed_sec"] = round(time.time() - t0, 2)
    if any(t in BATCH2_TYPES for t in types):
        report = write_batch2_report(stats, type_stats, slot_fills, samples,
                                     applied_manifest=applied)
        print(f"[W8] batch2 报告 → {report}")
    if args.json_summary:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
