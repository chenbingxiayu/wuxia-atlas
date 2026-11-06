# -*- coding: utf-8 -*-
"""EX-4 · graph.json 导出器（桥接层，docs/51 §三 E 组阶段 2）。

数据源（新管线唯一真源，只读）：
  - registry/relations/<书>.json   N5 relation_validator 产出（当前 5 书，910 条候选/落库边；
                                  schema relations-v0.1：subject/subject_type/predicate/object/
                                  object_type/confidence/loc/evidence/rule/count/books …）
  - registry/entities.json         实体身份层（canonical/type/aliases；跨书规范名）
  - registry/concordance/<书>.json 逐书实体频次（node.n 的次数口径）与出现书目（node.books）

导出目标：按 site/data 现有 `graph.json` 契约（2026-11-02 基线）
  {meta, nodes:[{id,type,n,books}], edges:[{s,t,kind,n,lable,locs,books}]}
  映射（对齐 N5 报告 §8）：
    predicate→kind；count→n；evidence.loc→locs（"书·loc"，≤3 条去重）；
    subtype/params→label（如 夺; 物=宝剑）；subject_type/object_type→nodes.type；
    跨书同 canonical 合并 nodes（books 并集、n 合计）；books 同理并集。
  node.n ：concordance 该书 total 之和（alias-aware 反查）；books：concordance 出现书 ∪ 边涉及书。
  node.id ：规范名（与 characters/dossiers/entity-index 的 canonical 一致；display 仅展示层）。

口径与边界：
  - 只读 relations/entities/concordance，不写 registry 其它目录、不写 site/data（默认 dry-run，
    --apply 才由 export_site_common 统一备份后写）；
  - 旧图 626 边中 对局/拥有/独门/创制/镇山/救助/恩义 为旧 kb 考订边，D06 55 谓词无对应者
    不导出（写入 meta.field_gaps / 报告对照），本导出为 N5 候选层关系边的 graph 投影；
  - 节点保留 N5 端点全部符号类型（含 =/◎/&/;），站点 NetworkGraph 当前仅区分 @/☆/◆，
    其余按"人物"分类渲染（桥接期已知偏差，W 组落地后替换）。

CLI：
  python scripts/export_site_graph.py            # dry-run（staging + 差异报告）
  python scripts/export_site_graph.py --apply    # 写 site/data（common 自动备份；本阶段默认不用）
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

import config
import export_site_common as esc

REL_DIR = config.DIR_REGISTRY / "relations"
REGISTRY_PATH = config.DIR_REGISTRY / "entities.json"
CONCORDANCE_DIR = config.DIR_REGISTRY / "concordance"

SCHEMA = "graph-v1"          # 沿用旧站 meta.schema
SOURCE = "N5 registry/relations（5 书，relation_validator 产出）+ registry/entities.json + concordance"
EXPORTER = "EX-4 export_site_graph"
LOCS_MAX = 3                 # 旧站口径：每条边保留 ≤3 条定位符
NODE_TYPE_PRIORITY = {"@": 0, "◆": 1, "☆": 2, "•": 3, "&": 4, "◎": 5, ";": 6, "=": 7, "^": 8}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def relations_books() -> list:
    """发现 registry/relations 下 N5 产出书（按 config 书目顺序）。"""
    names = {p.stem for p in REL_DIR.glob("*.json")}
    order = {b: i for i, b in enumerate(config.book_names())}
    return sorted(names, key=lambda b: (order.get(b, 10 ** 6), b))


# ---------------------------------------------------------------- 实体身份/频次
def load_registry() -> dict:
    """registry/entities.json → {canonical 相关索引}。"""
    payload = load_json(REGISTRY_PATH)
    entities = payload.get("entities") or []
    by_canon_type = {}          # (type, canonical) -> entity
    canon_aliases = defaultdict(set)   # (type, canonical) -> {别名}
    alias_to_canon = defaultdict(set)  # (type, 别名) -> {canonical}
    for e in entities:
        typ, canon = e.get("type"), e.get("canonical")
        if not typ or not canon:
            continue
        by_canon_type[(typ, canon)] = e
        for a in e.get("aliases") or []:
            canon_aliases[(typ, canon)].add(a)
            alias_to_canon[(typ, a)].add(canon)
    return {"entities": entities, "count": len(entities),
            "generated": (payload.get("meta") or {}).get("generated") or payload.get("generated"),
            "by_canon_type": by_canon_type, "canon_aliases": canon_aliases,
            "alias_to_canon": alias_to_canon}


def load_concordance(books: list) -> dict:
    """逐书 concordance → total[(书,type,canon)]、variants[(书,type)] display→canon。"""
    total = defaultdict(int)
    variants = {}
    generated = {}
    for book in books:
        path = CONCORDANCE_DIR / f"{book}.json"
        if not path.exists():
            continue
        data = load_json(path)
        if data.get("book") and data["book"] != book:     # 排除试点分回片段
            continue
        generated[book] = data.get("generated")
        for ent in data.get("entities") or []:
            typ, canon = ent.get("type"), ent.get("canonical")
            if not typ or not canon:
                continue
            total[(book, typ, canon)] += int(ent.get("total") or 0)
            vm = variants.setdefault((book, typ), {})
            vm[canon] = canon
            for v in ent.get("variants") or []:
                d = v.get("display")
                if d:
                    vm[d] = canon
    return {"total": total, "variants": variants, "generated": generated}


def node_lookup(book: str, typ: str, canonical: str, conc: dict, reg: dict) -> tuple:
    """节点在指定书的 (出现次数, 命中 canonical|None)；alias/变体感知。"""
    vm = conc["variants"].get((book, typ), {})
    candidates = [canonical]
    candidates += sorted(reg["canon_aliases"].get((typ, canonical), set()))
    # canonical 本身若是别名（非 registry canonical），也补其规范名候选
    for target in reg["alias_to_canon"].get((typ, canonical), set()):
        candidates.append(target)
    for cand in candidates:
        target = vm.get(cand)
        if target is None:
            continue
        n = conc["total"].get((book, typ, target), 0)
        if n:
            return n, target
    return 0, None


# ---------------------------------------------------------------- 关系边
def load_relations(books: list) -> list:
    """N5 relations → [{book, payload, edges}]。"""
    out = []
    for book in books:
        path = REL_DIR / f"{book}.json"
        if not path.exists():
            continue
        payload = load_json(path)
        out.append({"book": book,
                    "generated": payload.get("generated_at") or payload.get("generated"),
                    "n5_counts": payload.get("counts") or {},
                    "edges": payload.get("edges") or []})
    return out


def edge_label(edge: dict) -> str:
    """subtype/params → graph label（旧 graph label 为自由字符串）。"""
    parts = []
    subtype = (edge.get("subtype") or "").strip()
    if subtype:
        parts.append(subtype)
    for k, v in (edge.get("params") or {}).items():
        if v in (None, "", [], {}):
            continue
        parts.append(f"{k}={v}")
    return "; ".join(parts)


def build_edges(rel_books: list) -> tuple:
    """跨书聚合 N5 边 → graph edges。键=(s,t,kind,label)；n 求和、books 并集、locs ≤3。"""
    agg = {}
    conf_total = Counter()
    for rb in rel_books:
        book = rb["book"]
        for e in rb["edges"]:
            s = (e.get("subject") or "").strip()
            t = (e.get("object") or "").strip()
            kind = (e.get("predicate") or "").strip()
            if not s or not t or not kind or s == t:
                continue
            label = edge_label(e)
            key = (s, t, kind, label)
            item = agg.get(key)
            if item is None:
                item = agg[key] = {"s": s, "t": t, "kind": kind, "label": label,
                                   "n": 0, "books": set(), "locs": []}
            item["n"] += int(e.get("count") or 1)
            item["books"].add(book)
            conf_total[e.get("confidence") or "unknown"] += int(e.get("count") or 1)
            ev_locs = [x.get("loc") for x in (e.get("evidence") or []) if x.get("loc")]
            if not ev_locs:
                ev_locs = [e.get("loc") or ""]
            for ev_loc in ev_locs:
                if len(item["locs"]) >= LOCS_MAX:
                    break
                loc = f"{book}·{ev_loc}"
                if loc not in item["locs"]:
                    item["locs"].append(loc)
    edges = []
    for item in agg.values():
        locs = item["locs"] if item["locs"] else [""]
        edges.append({"s": item["s"], "t": item["t"], "kind": item["kind"],
                      "n": int(item["n"]), "label": item["label"],
                      "locs": locs, "books": sorted(item["books"])})
    edges.sort(key=lambda e: (-e["n"], e["kind"], e["s"], e["t"]))
    return edges, dict(conf_total)


# ---------------------------------------------------------------- 节点
def build_nodes(edges: list, rel_books: list, conc: dict, reg: dict) -> tuple:
    """边端点 → nodes（跨书 canonical 合并）；n/books 由 concordance 口径补齐。"""
    books = [rb["book"] for rb in rel_books]
    endpoint = {}   # canonical -> {"types": Counter, "books": set}
    # 端点类型需从 N5 原始边取（graph 边不带 type）
    for rb in rel_books:
        book = rb["book"]
        for e in rb["edges"]:
            for side in ("subject", "object"):
                canon = (e.get(side) or "").strip()
                typ = (e.get(side + "_type") or "").strip()
                if not canon:
                    continue
                item = endpoint.setdefault(canon, {"types": Counter(), "books": set()})
                if typ:
                    item["types"][typ] += int(e.get("count") or 1)
                item["books"].add(book)
    nodes = []
    conflicts = {}
    for canon, item in endpoint.items():
        typ = max(item["types"], key=lambda t: (item["types"][t],
                                                -NODE_TYPE_PRIORITY.get(t, 99))) \
            if item["types"] else "@"
        if len(item["types"]) > 1:
            conflicts[canon] = {"merged_types": dict(item["types"]), "chosen": typ}
        n_total = 0
        books_hit = set()
        for book in books:
            n, _target = node_lookup(book, typ, canon, conc, reg)
            if n:
                n_total += n
                books_hit.add(book)
            # 同一 canonical 其它类型的出现也计入（合并节点）
            for other in item["types"]:
                if other == typ:
                    continue
                n2, _ = node_lookup(book, other, canon, conc, reg)
                if n2:
                    n_total += n2
                    books_hit.add(book)
        node_books = sorted(books_hit | item["books"])
        nodes.append({"id": canon, "type": typ, "n": int(n_total),
                      "books": node_books})
    nodes.sort(key=lambda n: (-n["n"], NODE_TYPE_PRIORITY.get(n["type"], 99), n["id"]))
    return nodes, conflicts


# ---------------------------------------------------------------- 与旧站对照
KIND_MAP = {"师承": "师承", "对局": "交手", "救助": "解救",
            "修习": "修习", "传授": "传授"}


def compare_old(payload: dict) -> dict:
    """旧 graph.json（2026-11-02 基线）vs 新产出记录级对照。"""
    old = esc.load_site("graph.json")
    result = {"available": bool(old)}
    if not old:
        return result
    old_nodes = old.get("nodes") or []
    old_edges = old.get("edges") or []
    new_nodes = payload["nodes"]
    new_edges = payload["edges"]
    old_node_ids = {n["id"] for n in old_nodes}
    new_node_ids = {n["id"] for n in new_nodes}
    old_pair = defaultdict(set)    # (s,t) -> {kind}
    for e in old_edges:
        old_pair[(e["s"], e["t"])].add(e["kind"])
    new_pair = defaultdict(set)
    for e in new_edges:
        new_pair[(e["s"], e["t"])].add(e["kind"])
    mapped_kinds = Counter()
    old_only_kinds = Counter()
    for e in old_edges:
        if e["kind"] in KIND_MAP:
            mapped_kinds[e["kind"]] += 1
        else:
            old_only_kinds[e["kind"]] += 1
    # 同 (s,t) 且 kind 映射后可对上的边数
    overlap_edges = 0
    for (s, t), kinds in old_pair.items():
        mapped = {KIND_MAP[k] for k in kinds if k in KIND_MAP}
        if not mapped:
            continue
        if mapped & new_pair.get((s, t), set()):
            overlap_edges += 1
    return {
        "available": True, "old_generated": (old.get("meta") or {}).get("generated"),
        "old_nodes": len(old_nodes), "old_edges": len(old_edges),
        "new_nodes": len(new_nodes), "new_edges": len(new_edges),
        "node_type_old": dict(Counter(n["type"] for n in old_nodes)),
        "node_type_new": dict(Counter(n["type"] for n in new_nodes)),
        "kind_old": dict(Counter(e["kind"] for e in old_edges).most_common()),
        "kind_new": dict(Counter(e["kind"] for e in new_edges).most_common()),
        "node_overlap": len(old_node_ids & new_node_ids),
        "old_only_nodes": len(old_node_ids - new_node_ids),
        "new_only_nodes": len(new_node_ids - old_node_ids),
        "mapped_old_kinds": dict(mapped_kinds),
        "old_only_kinds": dict(old_only_kinds),
        "pair_overlap_edges": overlap_edges,
        "label_old": dict(Counter(e.get("label") or "" for e in old_edges).most_common(10)),
    }


def render_notes(payload: dict, cmp: dict) -> str:
    lines = [
        "### 记录数与旧站 graph.json 对照",
        "",
        "| 项 | 旧站（2026-11-02） | 新产出（EX-4） |",
        "|---|---:|---:|",
        f"| nodes | {cmp.get('old_nodes', '—')} | {cmp.get('new_nodes')} |",
        f"| edges | {cmp.get('old_edges', '—')} | {cmp.get('new_edges')} |",
        f"| 节点类型 | {cmp.get('node_type_old', {})} | {cmp.get('node_type_new', {})} |",
        f"| 边 kind | {cmp.get('kind_old', {})} | {cmp.get('kind_new', {})} |",
        f"| canonical 交集 | — | {cmp.get('node_overlap')}（旧独有 {cmp.get('old_only_nodes')} / 新独有 {cmp.get('new_only_nodes')}） |",
        "",
        "### 旧 kind → 新 kind 对位（仅语义可对位者）",
        "",
        "| 旧 kind | 边数 | 新对位 | 说明 |",
        "|---|---:|---|---|",
        f"| 师承 | {cmp.get('mapped_old_kinds', {}).get('师承', 0)} | 师承 | 旧 kb 师承边 vs N5 师承候选（同 (s,t) 交集见下） |",
        f"| 对局 | {cmp.get('mapped_old_kinds', {}).get('对局', 0)} | 交手 | 旧 matches/对局边 vs N5 交手候选（语义近似，非同事件集） |",
        f"| 救助 | {cmp.get('mapped_old_kinds', {}).get('救助', 0)} | 解救 | 旧事件启发式 vs N5 解救候选 |",
        f"| 修习 | {cmp.get('mapped_old_kinds', {}).get('修习', 0)} | 修习 | D06 #25 可对位，但 N5 当前未产出 修习 边（新边 0） |",
        f"| 传授 | {cmp.get('mapped_old_kinds', {}).get('传授', 0)} | 传授 | D06 #36 可对位，但 N5 当前未产出 传授 边（新边 0） |",
        "| 拥有/独门/创制/镇山/恩义 | "
        f"{sum(cmp.get('old_only_kinds', {}).values())} | — | 旧武功考订语义/离线层，D06 55 谓词无对应 → 本导出不产出（旧表只读保留） |",
        "",
        f"- 同 (s,t) 且 kind 可对位的交集边数：**{cmp.get('pair_overlap_edges')}**"
        f"（旧边 {cmp.get('old_edges')} / 新边 {cmp.get('new_edges')}，两库口径不同，数量不可直接相减）。",
        f"- 旧 label 取值（对局 win/draw/loss 等）：{cmp.get('label_old', {})}；"
        "新版 label 来自 N5 subtype/params（如 夺; 物=宝剑 / 收…为徒），大多数快照边为空串。",
        "",
        "### 5 书覆盖（graph 投影后逐书口径）",
        "",
        "| 书 | N5 原始边 | graph 参与边 | graph 参与节点 | N5 生成时间 |",
        "|---|---:|---:|---:|---|",
        *[f"| {b} | {v.get('edges', 0)} | {payload['meta']['snapshot'].get('graph_by_book', {}).get(b, {}).get('edges', 0)} | "
          f"{payload['meta']['snapshot'].get('graph_by_book', {}).get(b, {}).get('nodes', 0)} | "
          f"{v.get('generated') or ''} |"
          for b, v in (payload['meta']['snapshot'].get('relations_by_book') or {}).items()],
        "",
        "### 口径说明（差异均写入 meta.field_gaps / meta.notes）",
        "- 旧 graph 由旧 kb（事件表/关系表/matches/dossiers）构建，含旧武功考订边；"
        "EX-4 只消费 N5 关系表（tagged 现算候选层），二者**不可按边数直接比较**。",
        "- 旧图仅 @/☆/◆ 三类节点（孤立节点已剪除）；新版保留 N5 端点的全部符号类型"
        "（地点/群组/家族等节点使 nodes 数量结构不同于旧图），站点 NetworkGraph 目前把非 @/☆/◆ 归入「人物」分类。",
        "- 旧图 edges.books 因旧 build_graph 缺陷恒为空；新版 books 为跨书并集（修正该历史缺陷）。",
        "",
        "### 与 N5 字段映射（EX-4 消费口径）",
        "",
        "| N5 relations-v0.1 | graph.json |",
        "|---|---|",
        "| `edges[].predicate` | `edges[].kind` |",
        "| `edges[].count` | `edges[].n`（同键跨书求和） |",
        "| `edges[].evidence[].loc` | `edges[].locs`（`书·NNN:段`，≤3 去重） |",
        "| `edges[].subtype` / `params` | `edges[].label`（`; ` 连接） |",
        "| `edges[].subject/object` + `subject_type/object_type` | `edges[].s/t` + `nodes[].type` |",
        "| `edges[].books` | `edges[].books`（并集，sorted） |",
        "| 端点 canonical | `nodes[].id`（与 site characters/dossiers canonical 一致） |",
        "| concordance entity total | `nodes[].n`（跨书合计） |",
        "| concordance 出现书 ∪ 边书 | `nodes[].books` |",
        "",
        "### 复现命令",
        "```",
        "python scripts/export_site_graph.py        # dry-run（默认，只写 staging/reports）",
        "```",
        "### 遗留",
        "- 无 ◆/• 端点：N5 当前未产出 组织成员/隶属终止（◆）与 持有/制造（•）边，"
        "sects=0；后续 N5 规则扩充后本导出自动扩展。",
        "- 置信分层未进 graph 契约字段：`meta.edge_confidence` 保留 strong/ok/weak 边数分布供 W 组消费。",
        "- 旧图的 拥有/独门/创制/镇山 边需 D06 新谓词或 W 组重建；本阶段 bridge 不导出。",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- 主流程
def build_payload() -> tuple:
    books = relations_books()
    rel = load_relations(books)
    reg = load_registry()
    conc = load_concordance(books)
    edges, conf_counts = build_edges(rel)
    nodes, conflicts = build_nodes(edges, rel, conc, reg)
    node_types = dict(Counter(n["type"] for n in nodes))
    edge_kinds = dict(Counter(e["kind"] for e in edges))
    totals = {
        "nodes": len(nodes),
        "edges": len(edges),
        "persons": node_types.get("@", 0),
        "arts": node_types.get("☆", 0),
        "sects": node_types.get("◆", 0),
    }
    book_edge_cov = {rb["book"]: sum(1 for e in edges if rb["book"] in e["books"])
                     for rb in rel}
    book_node_cov = {rb["book"]: sum(1 for n in nodes if rb["book"] in n["books"])
                     for rb in rel}
    snapshot = {
        "exported_at": esc.now_iso(),
        "relations_by_book": {rb["book"]: {"edges": len(rb["edges"]),
                                           "generated": rb["generated"]} for rb in rel},
        "relations_raw_edges": sum(len(rb["edges"]) for rb in rel),
        "relations_books_count": len(rel),
        "graph_by_book": {b: {"nodes": book_node_cov.get(b, 0),
                              "edges": book_edge_cov.get(b, 0)} for b in book_edge_cov},
        "registry_entities": reg["count"],
        "registry_generated": reg["generated"],
        "concordance_generated": conc["generated"],
    }
    payload = {
        "meta": {
            "generated": esc.today(),
            "schema": SCHEMA,
            "totals": totals,
            "source": SOURCE,
            "note": ("由 N5 关系表投影：节点=边端点 canonical 跨书合并，边按 "
                     "(s,t,kind,label) 聚合、n=证据数求和、locs=≤3 定位符、books 跨书并集；"
                     "旧图对局为 matches 来源，本版以 N5 交手近似；旧武功考订边（拥有/独门/创制/镇山）"
                     "D06 无对应谓词，未导出。"),
            "notes": [
                "node.n=concordance 各书 entity total 合计（alias-aware）；"
                "node.books=concordance 出现书 ∪ 边涉及书。",
                "node.id=registry canonical（与 site characters/dossiers/entity-index 一致）；"
                "display 展示层不参与身份（见 registry/display_canonical.json）。",
                "节点类型保留 N5 端点符号（@/=/◎/&/;/☆）；站点 NetworkGraph 当前仅区分 @/☆/◆，"
                "其余归入人物分类（桥接期已知偏差）。",
                "边聚合键含 label：同一人物对的多 mode/不同武功 转移不会被合并丢失。",
            ],
            "field_gaps": [
                "对局：旧 graph 的对局边来自旧 matches.json（实体层对局表），"
                "EX-4 以 N5『交手』边近似（语义接近，非同一事件集）",
                "拥有/独门/创制/镇山：旧武功考订边，D06 55 谓词无对应 → 不导出（旧 kb 表只读保留）",
                "恩义/救助：旧为关系表/事件启发式；N5 以解救近似救助，恩义属离线表（D06 §6.4）不导出",
                "sects：N5 当前无 ◆ 端点（组织成员/隶属终止 0 边），totals.sects=0；"
                "旧 17 门派节点无新对应来源",
                "namespace：N5 为候选层（strong/ok/weak 混合），非人工校订；旧图为旧 kb 校订产物",
            ],
            "node_types": node_types,
            "edge_kinds": edge_kinds,
            "edge_confidence": conf_counts,
            "canonical_type_conflicts": conflicts,
            "snapshot": snapshot,
        },
        "nodes": nodes,
        "edges": edges,
    }
    return payload, {"books": books, "rel": rel, "reg": reg, "conc": conc}


def main() -> int:
    if "--apply" in sys.argv:
        print("[EX-4] 注意：--apply 经 export_site_common 备份后写 site/data；"
              "阶段 2 默认先 dry-run，由 Lead 统一收口 apply。")
    payload, _ctx = build_payload()
    cmp = compare_old(payload)
    notes = render_notes(payload, cmp)
    diff = esc.finish("graph.json", payload, exporter=EXPORTER, notes=notes)
    print(f"[EX-4] nodes={payload['meta']['totals']['nodes']} "
          f"(person={payload['meta']['totals']['persons']} art={payload['meta']['totals']['arts']} "
          f"sect={payload['meta']['totals']['sects']}) · edges={payload['meta']['totals']['edges']} "
          f"· kinds={payload['meta']['edge_kinds']}")
    hard = diff["hard_gap_count"]
    if hard:
        print(f"[EX-4] ✗ 契约硬缺口 {hard}，见 reports/graph_report.md")
        return 1
    print("[EX-4] ✓ 契约字段不缺、类型不破；dry-run 完成（staging + reports）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
