# -*- coding: utf-8 -*-
"""EX-2 · characters.json + entity-index.json 导出器（桥接层，docs/51 §三/§五）。

数据源（新管线唯一真源）：
  - registry/entities.json              实体身份层（id/type/canonical/aliases/status）
  - registry/concordance/<书>.json       5 书逐回统计（total/chapter_counts/variants/registration）
  - registry/display_canonical.json      展示层覆盖（canonical→display；默认 canonical==display）
旧站 site/data/characters.json、entity-index.json 只作契约签名与记录级形状基线；
本表全部字段可由新数据产出，**不触发旧值 fallback**（fallback 只在 EX-3 dossiers 发生）。

展示层（task-24 / SKILL_03b 附录 B B-1/B-2）：
  - 每条记录新增 `display` 字段（**只增字段，不改名/删字段**）：display = display_canonical 表覆盖值，
    未登记条目回落 canonical；canonical/type 等身份口径不受影响；
  - 例：玄烨→康熙、朱由检→崇祯、福临→顺治、胤禛→雍正（帝王展示年号）、哈玛雅→飞红巾（系列展示）。

归一化口径（meta.field_gaps 中逐项声明）：
  1) 跨书按 (type, canonical) 聚合，total 为出现次数之和，books 为逐书 {count, chapters, aliases}；
  2) alias_mapped 条目按 concordance.registration.id 回查 registry（规范名 + 类型）后并入规范实体
     （例：白发魔女/哈玛雅/晦明禅师 → 练霓裳/飞红巾/岳鸣珂）；registered 条目天然同规范名；
  3) 15 类实体符号照旧契约格式输出（单字符 symbol + 中文 type_legend），
     旧站 "[秘籍文书"/"§丹药" 两个历史类型保留键位（新管线无产出，计数 0），不做 15→10 强制映射。

用法：
  python scripts/export_site_characters.py           # dry-run（staging + 报告）
  python scripts/export_site_characters.py --apply   # 写 site/data（export_site_common 先备份）
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

import config
import export_site_common as esc
import symbols

REGISTRY_PATH = config.DIR_REGISTRY / "entities.json"
CONCORDANCE_DIR = config.DIR_REGISTRY / "concordance"
DISPLAY_CANONICAL_PATH = config.DIR_REGISTRY / "display_canonical.json"   # 展示层覆盖表（只增字段用）
BOOK_META_PATH = config.LEGACY_KB / "作品元数据表.json"      # 只读：书序

SCHEMA_CHARACTERS = "site-characters-v1"
SCHEMA_ENTITY_INDEX = "entity-index-v1"
SCHEMA_DISPLAY = "display-canonical-v1"
SOURCE = "wuxia-kb 新管线 + 旧站 fallback（桥接层 EX-2/EX-3）"
EXPORTER = "scripts/export_site_characters.py（EX-2）"
DISPLAY_SAMPLE_CANONICALS = ("玄烨", "朱由检", "福临", "胤禛", "哈玛雅")

# 旧站 type_legend（../scripts/build_site_data.py L132-134，只读基线，10 类）
OLD_TYPE_LEGEND = {
    "@": "人物", "=": "地点", "◆": "组织", ";": "职衔称谓", "%": "时间",
    "☆": "武功", "•": "兵器宝物", "[": "秘籍文书", "§": "丹药", "+": "坐骑",
}
# 轻索引仅收录旧契约的 3 类（对齐 ../scripts/build_site_data.py build_entity_index）
INDEX_TYPES = ("@", "☆", "◆")
IN_SCOPE_STATUS = ("registered", "alias_mapped")


# ---------------------------------------------------------------- 数据源
def load_registry() -> dict[str, dict]:
    """registry/entities.json → {id: entity}（id 唯一，身份层权威）。"""
    payload = esc.load_json(REGISTRY_PATH)
    by_id: dict[str, dict] = {}
    for e in payload.get("entities", []):
        by_id.setdefault(e["id"], e)
    return by_id


def load_display_map() -> tuple[dict[str, str], dict]:
    """registry/display_canonical.json → ({canonical: display}, meta)。

    缺省/文件缺失 → 空映射（display==canonical 恒等回落）；本表只用于**展示层字段**，
    不影响 canonical/type/归并/accept 判定。
    """
    if not DISPLAY_CANONICAL_PATH.exists():
        return {}, {"schema": SCHEMA_DISPLAY, "entries": 0,
                    "source": "（display_canonical.json 缺失，回退 canonical==display）",
                    "policy": "canonical==display"}
    payload = esc.load_json(DISPLAY_CANONICAL_PATH)
    mapping: dict[str, str] = {}
    for e in payload.get("entries") or []:
        canon = (e.get("canonical") or "").strip()
        disp = (e.get("display") or "").strip()
        if canon and disp:
            mapping[canon] = disp
    meta = payload.get("meta") or {}
    return mapping, {
        "schema": meta.get("schema") or SCHEMA_DISPLAY,
        "entries": len(mapping),
        "source": DISPLAY_CANONICAL_PATH.relative_to(config.ROOT).as_posix(),
        "policy": meta.get("policy") or "",
        "default": "canonical==display",
    }


def display_of(canonical: str, display_map: dict[str, str]) -> str:
    """展示名：display_canonical 覆盖优先，缺省回落 canonical。"""
    return display_map.get(canonical, canonical)


def book_order() -> dict[str, int]:
    """../kb/作品元数据表.json → {书名: 书序 no}（只读迁移输入）。"""
    if not BOOK_META_PATH.exists():
        return {}
    payload = esc.load_json(BOOK_META_PATH)
    return {w["book"]: int(w.get("no") or 10 ** 6) for w in payload.get("works", [])}


def load_book_payloads() -> list[dict]:
    """发现 5 书全量 concordance：书序排序；排除单回试点文件（如 白发魔女传_001-001.json）。"""
    order = book_order()
    known = set(config.books())
    best: dict[str, dict] = {}
    for p in sorted(CONCORDANCE_DIR.glob("*.json")):
        try:
            data = esc.load_json(p)
        except (json.JSONDecodeError, OSError):
            continue
        book = data.get("book") or p.stem
        if p.stem != book:          # 试点/分回片段：文件名与 book 字段不一致
            continue
        if known and book not in known and book not in order:
            continue
        if int(data.get("chapter_count") or 0) < 2:
            continue
        prev = best.get(book)
        if prev is None or int(data.get("chapter_count") or 0) > int(prev["data"].get("chapter_count") or 0):
            best[book] = {"book": book, "path": p, "data": data}
    if not best:
        raise SystemExit(f"[EX-2] 未发现可用 concordance 文件：{CONCORDANCE_DIR}")
    payloads = sorted(best.values(), key=lambda b: (order.get(b["book"], 10 ** 6), b["book"]))
    return payloads


# ---------------------------------------------------------------- 归一化 + 聚合
def normalize_identity(entry: dict, reg_by_id: dict) -> tuple[str, str, dict | None]:
    """concordance 条目 → (type, canonical, 归一化变更说明|None)。

    registered / alias_mapped 条目带 registration.id，回查 registry 取权威 (type, canonical)；
    out_of_scope / unregistered 保持 concordance 原值（如 ☆、% 等非身份层类型）。
    """
    etype = entry.get("type") or ""
    canon = entry.get("canonical") or ""
    reg = entry.get("registration") or {}
    if reg.get("status") in IN_SCOPE_STATUS:
        r = reg_by_id.get(reg.get("id"))
        if r:
            rtype = r.get("type") or etype
            rcanon = r.get("canonical") or canon
            if (rtype, rcanon) != (etype, canon):
                return rtype, rcanon, {
                    "from_type": etype, "from_canonical": canon,
                    "to_type": rtype, "to_canonical": rcanon,
                    "status": reg.get("status"),
                }
            return rtype, rcanon, None
    return etype, canon, None


def aggregate_entities(book_payloads: list[dict], reg_by_id: dict) -> tuple[dict, dict]:
    """5 书 concordance → {(type, canonical): {type, canonical, total, books{book:{count,chapters,aliases}}}}。"""
    agg: dict[tuple[str, str], dict] = {}
    stats = {"norm_entries": 0, "alias_merges": [], "type_norms": []}
    for bp in book_payloads:
        book = bp["book"]
        for e in bp["data"].get("entities", []):
            etype, canon, change = normalize_identity(e, reg_by_id)
            if change:
                stats["norm_entries"] += 1
                bucket = "type_norms" if change["from_type"] != change["to_type"] else "alias_merges"
                stats[bucket].append((book, change))
            key = (etype, canon)
            rec = agg.get(key)
            if rec is None:
                rec = agg[key] = {"type": etype, "canonical": canon, "total": 0, "books": {}}
            total = int(e.get("total") or 0)
            rec["total"] += total
            binfo = rec["books"].get(book)
            if binfo is None:
                binfo = rec["books"][book] = {
                    "count": 0,
                    "chapters": Counter(),
                    "aliases": defaultdict(int),
                }
            binfo["count"] += total
            for cc in e.get("chapter_counts") or []:
                binfo["chapters"][int(cc.get("chapter") or 0)] += int(cc.get("count") or 0)
            for v in e.get("variants") or []:
                binfo["aliases"][v.get("display") or canon] += int(v.get("count") or 0)
    return agg, stats


# ---------------------------------------------------------------- 产物构造
def build_characters(agg: dict, books: list[str], display_map: dict[str, str] | None = None) -> list[dict]:
    """聚合结构 → characters.json entities（旧契约记录形状 + 新增展示层 display）。

    字段：type/canonical/books/total/cross_book（旧契约，不变）+ display（task-24 新增展示名）。
    """
    display_map = display_map or {}
    items = []
    for rec in agg.values():
        book_map = {}
        for book in books:                       # 书序输出，仅含出现书目
            binfo = rec["books"].get(book)
            if not binfo:
                continue
            aliases = {a: n for a, n in
                       sorted(binfo["aliases"].items(), key=lambda kv: (-kv[1], kv[0]))}
            book_map[book] = {
                "count": binfo["count"],
                "chapters": sorted(binfo["chapters"]),
                "aliases": aliases,
            }
        items.append({
            "type": rec["type"],
            "canonical": rec["canonical"],
            "display": display_of(rec["canonical"], display_map),   # task-24：只增字段
            "books": book_map,
            "total": rec["total"],
            "cross_book": len(book_map) > 1,
        })
    items.sort(key=lambda m: (-m["total"], m["type"], m["canonical"]))
    return items


def type_legend() -> dict:
    """旧站 10 类中文名沿用 + symbols.ENTITIES 新增 7 类（15 类全覆盖；19 类键位）。"""
    legend = dict(OLD_TYPE_LEGEND)
    for code, label in symbols.ENTITIES.items():
        legend.setdefault(code, label)
    return legend


def summarize_types(items: list[dict]) -> dict:
    """by_type 计数：保留旧契约 10 个键位（含 0），并列出新管线全部类型。"""
    counter = Counter(item["type"] for item in items)
    for code in OLD_TYPE_LEGEND:
        counter.setdefault(code, 0)
    return {code: counter[code] for code in sorted(counter)}


def build_characters_payload(items: list[dict], books: list[str], stats: dict,
                             display_meta: dict | None = None) -> dict:
    merged = len(items)
    cross = sum(1 for m in items if m["cross_book"])
    by_type = summarize_types(items)
    new_types = [c for c in sorted({i["type"] for i in items}) if c not in OLD_TYPE_LEGEND]
    merged_targets = sorted({(ch["to_type"], ch["to_canonical"]) for _, ch in stats["alias_merges"]})
    display_meta = display_meta or {}
    shown = [f"{c}→{d}" for c, d in sorted(display_meta.get("map", {}).items())]
    gaps = [
        f"展示层字段 display（task-24 新增，只增不改）：每条记录 display 取 registry/display_canonical.json "
        f"覆盖值（{display_meta.get('entries', 0)} 条覆盖：{'、'.join(shown)}），未登记条目回落 canonical（默认 canonical==display）；"
        "display 仅影响展示文案，不参与归并/accept/concordance 判定，canonical 仍是身份层唯一值。",
        "类型体系：新管线 15 类实体符号（scripts/symbols.py ENTITIES）；characters 保留全部 15 类"
        "（照旧契约“单字符 symbol + 中文 type_legend”格式），旧站 §丹药/[秘籍文书 保留键位、计数 0，"
        "不做 15→10 强制映射以免伪造语义；旧站无对应类型的新增符号="
        + "、".join(f"{c}{symbols.ENTITIES.get(c, '')}" for c in new_types) + "。",
        "旧站 10 类兼容视图（**未执行**，供 Lead 裁决）：如需严格旧 10 类，可近似映射 "
        "@◎→@、=→=、◆&~→◆、;/#→;、☆→☆、•→•、+→+、{→[、^→[、%→%、$→%（或弃 $数量）；"
        "本次按“不得伪造”原则未自动映射，保留 15 类原符号。",
        f"记录数：旧站 2390（3 书，每书实体登记表合并）→ 新 {merged}（5 书 concordance 聚合）；"
        "差异主因：书目 +2（冰魄寒光剑、江湖三女侠）、标注覆盖扩大、新管线类型粒度更细"
        "（$数量/#身份/^专门概念 等旧站无对应类型）。books/total 口径与旧站一致（total=出现次数）。",
        "书目范围：旧站 meta.books=七剑下天山/塞外奇侠传/白发魔女传（3 书）；"
        "新 meta.books=" + "、".join(books) + "（书序取自 ../kb/作品元数据表.json，只读）。",
        f"身份归一化：alias_mapped 条目按 concordance.registration.id 回查 registry（规范名 + 类型）"
        f"后并入，共 {stats['norm_entries']} 条入书条目 → {len(merged_targets)} 个规范实体"
        f"（{'、'.join(c for _, c in merged_targets)}）；registered 条目天然同规范名（零类型改写）；"
        "unregistered 变体（如 晦明 vs 晦明禅师）未归并。",
        "books[book].chapters 取 concordance chapter_counts（含 chapter 0=回目标题行，"
        "与旧站 50 条 chapter 0 口径一致）；books[book].aliases 取 variants 全量"
        "（含 canonical 显示，逐书 aliases 计数和 = 该书记数）。",
        "跨书合并键=(type, canonical)：同名不同类（如 天山 为 =/◆ 两条）按旧站口径保留为不同记录。",
    ]
    return {
        "meta": {
            "generated": esc.now_iso(),
            "schema": SCHEMA_CHARACTERS,
            "books": list(books),
            "source": SOURCE,
            "source_detail": (
                f"registry/entities.json（{stats['registry_ids']} 条身份层）+ "
                f"registry/concordance/{{{','.join(books)}}}.json（5 书逐回统计）；"
                "旧站 fallback 未触发（characters/entity-index 全字段可由新数据产出）"
            ),
            "display_layer": display_meta,
            "type_legend": type_legend(),
            "totals": {
                "merged_entities": merged,
                "cross_book": cross,
                "by_type": by_type,
            },
            "field_gaps": gaps,
        },
        "entities": items,
    }


def build_entity_index_payload(items: list[dict], books: list[str],
                               display_meta: dict | None = None) -> dict:
    display_meta = display_meta or {}
    rows = []
    for item in items:
        if item["type"] not in INDEX_TYPES:
            continue
        rows.append({
            "t": item["type"],
            "c": item["canonical"],
            "display": item.get("display") or item["canonical"],   # task-24：只增字段
            "n": item["total"],
            "b": {book: info["count"] for book, info in item["books"].items()},
            "x": item["cross_book"],
        })
    rows.sort(key=lambda r: (-r["n"], r["t"], r["c"]))
    by_type = {t: sum(1 for r in rows if r["t"] == t) for t in INDEX_TYPES}
    gaps = [
        f"展示层字段 display（task-24 新增，只增不改）：取 characters.json 同批 display，"
        f"覆盖 {display_meta.get('entries', 0)} 条（默认 canonical==display）；t/c 身份口径不变。",
        f"轻索引类型口径：仅 {'/'.join(INDEX_TYPES)}（对齐旧站 build_entity_index：@人物/☆武功/◆组织）；"
        "新管线 ◎&~#{$^ 等类型不进入轻索引（旧契约轻索引只有 3 类）。",
        f"记录数：旧 1034（@436/☆451/◆147，3 书）→ 新 {len(rows)}"
        f"（@/☆/◆={by_type['@']}/{by_type['☆']}/{by_type['◆']}，5 书）。"
        "☆/◆ 条目对应的 arts.json/sects.json 页面覆盖率取决于 EX-6 导出；"
        "旧站本身亦仅 103/451（arts=116）、15/147（sects=18）可跳转，桥接期同类链接缺口不属本表字段问题。",
        "n=总频次（concordance total 求和）、b=逐书频次、x=跨书（len(b)>1）；排序 -n，"
        "与旧站 entity-index 字段语义逐字段一致（t/c/n/b/x）。",
    ]
    return {
        "meta": {
            "generated": esc.now_iso(),
            "schema": SCHEMA_ENTITY_INDEX,
            "note": "轻索引：t=类型 c=规范名 n=总频次 b=逐书频次 x=跨书",
            "source": SOURCE,
            "source_detail": "派生自本脚本 characters.json 同批聚合结果（filter t∈@/☆/◆）",
            "display_layer": display_meta,
            "totals": {"entities": len(rows), "by_type": by_type},
            "field_gaps": gaps,
        },
        "entities": rows,
    }


# ---------------------------------------------------------------- 抽样回溯（验收 §七.3）
SAMPLE_TYPES = ("@", "☆", "◆", "=", "•", "%", "^", "#", "$", "{")


def trace_entity(key: tuple[str, str], book_payloads: list[dict], reg_by_id: dict) -> tuple[dict, dict | None]:
    """独立回溯：重新遍历 concordance 原始条目，按归一化键重算逐书频次与首见锚点。"""
    etype, canon = key
    per_book: Counter = Counter()
    anchor = None
    for bp in book_payloads:
        for e in bp["data"].get("entities", []):
            t, c, _ = normalize_identity(e, reg_by_id)
            if (t, c) != key:
                continue
            per_book[bp["book"]] += int(e.get("total") or 0)
            first = e.get("first") or {}
            rank = int(e.get("first_rank") or 10 ** 9)
            if first.get("anchor") and (anchor is None or rank < anchor[0]):
                anchor = (rank, bp["book"], first.get("anchor"), first.get("loc"))
    return dict(per_book), anchor


def character_samples(items: list[dict], book_payloads: list[dict], reg_by_id: dict) -> tuple[list[str], list[dict]]:
    """每类型取频次最高 1 条（最多 10 类），重算校验并生成回溯行。"""
    picked: dict[str, dict] = {}
    for item in items:
        picked.setdefault(item["type"], item)
    lines, failures = [], []
    for etype in SAMPLE_TYPES:
        item = picked.get(etype)
        if not item:
            continue
        key = (item["type"], item["canonical"])
        per_book, anchor = trace_entity(key, book_payloads, reg_by_id)
        if sum(per_book.values()) != item["total"] or dict(per_book) != {
                b: info["count"] for b, info in item["books"].items()}:
            failures.append(f"{item['canonical']} 频次回溯不一致")
        loc = f"{anchor[1]}·{anchor[3]}（{anchor[2]}）" if anchor else "—"
        lines.append(
            f"| {item['canonical']} | {item['type']} | {item['total']} | "
            + "、".join(f"{b}:{n}" for b, n in per_book.items()) + f" | {loc} |"
        )
    return lines, failures


def index_samples(rows: list[dict], items: list[dict]) -> list[str]:
    """轻索引抽样 10 条：n/b 与 characters 同源记录逐字段比对。"""
    by_key = {(i["type"], i["canonical"]): i for i in items}
    lines, failures = [], []
    for row in rows[:10]:
        item = by_key.get((row["t"], row["c"]))
        if not item:
            failures.append(f"索引条目 {row['c']} 在 characters 中缺失")
            continue
        if row["n"] != item["total"] or row["b"] != {b: v["count"] for b, v in item["books"].items()}:
            failures.append(f"索引条目 {row['c']} 频次不一致")
        lines.append(f"| {row['c']} | {row['t']} | {row['n']} | "
                     + "、".join(f"{b}:{n}" for b, n in row["b"].items()) + f" | {row['x']} |")
    return lines, failures


# ---------------------------------------------------------------- 展示层抽样（task-24）
def display_samples(items: list[dict], index_rows: list[dict],
                    display_map: dict[str, str]) -> tuple[list[str], list[str]]:
    """5 个覆盖条目（4 帝王 + 飞红巾）在 characters / entity-index 的 display 校验。"""
    chars_by = {(i["type"], i["canonical"]): i for i in items}
    idx_by = {(r["t"], r["c"]): r for r in index_rows}
    lines, failures = [], []
    for canon in DISPLAY_SAMPLE_CANONICALS:
        expected = display_map.get(canon)
        if expected is None:
            failures.append(f"display_canonical 表缺 {canon}")
            continue
        item = chars_by.get(("@", canon))
        row = idx_by.get(("@", canon))
        if item is None:
            failures.append(f"characters 缺 @{canon}")
            continue
        if row is None:
            failures.append(f"entity-index 缺 @{canon}")
            continue
        if item.get("display") != expected:
            failures.append(f"characters {canon} display={item.get('display')} 预期 {expected}")
        if row.get("display") != expected:
            failures.append(f"entity-index {canon} display={row.get('display')} 预期 {expected}")
        if item.get("canonical") != canon or row.get("c") != canon:
            failures.append(f"{canon} canonical 被展示层改写（只增字段被违反）")
        lines.append(f"| {canon} | {expected} | {item.get('display')} | {row.get('display')} | {item.get('total')} |")
    return lines, failures


# ---------------------------------------------------------------- 主流程
def main() -> int:
    book_payloads = load_book_payloads()
    books = [bp["book"] for bp in book_payloads]
    reg_by_id = load_registry()
    display_map, display_meta = load_display_map()
    display_meta = dict(display_meta, map=display_map)
    agg, stats = aggregate_entities(book_payloads, reg_by_id)
    stats["registry_ids"] = len(reg_by_id)
    items = build_characters(agg, books, display_map)
    chars = build_characters_payload(items, books, stats, display_meta)
    index_payload = build_entity_index_payload(items, books, display_meta)

    # 抽样回溯（验收：10 条可回溯到 concordance/registry）+ 展示层抽样（task-24）
    sample_lines, sample_fail = character_samples(items, book_payloads, reg_by_id)
    index_lines, index_fail = index_samples(index_payload["entities"], items)
    display_lines, display_fail = display_samples(items, index_payload["entities"], display_map)
    if sample_fail or index_fail or display_fail:
        raise SystemExit("[EX-2] 抽样/展示层校验失败：" + "；".join(sample_fail + index_fail + display_fail))

    notes = "\n".join([
        "### 记录数对比旧站",
        f"- characters.json：旧 2390（3 书）→ 新 {len(items)}（5 书：{'、'.join(books)}）；"
        f"cross_book：旧 405 → 新 {chars['meta']['totals']['cross_book']}。",
        f"- entity-index.json：旧 1034 → 新 {len(index_payload['entities'])}；"
        f"by_type {index_payload['meta']['totals']['by_type']}。",
        "- 字段覆盖：契约 hard_gap=0（见下 diff 段）；meta 额外提供 source/source_detail/field_gaps/display_layer（允许新增）。",
        "",
        "### 展示层（display，task-24）",
        f"- registry/display_canonical.json **{display_meta.get('entries', 0)} 条覆盖**"
        f"（{'、'.join(f'{c}→{d}' for c, d in sorted(display_map.items()))}）；"
        "未登记条目 display==canonical（默认恒等回落）。",
        "- **只增字段**：characters/entity-index 每条记录新增 `display`；canonical/type/books/total/cross_book 等既有字段与上版逐字段一致（未改名/未删字段）。",
        "",
        "| canonical | 预期 display | characters.display | entity-index.display | total |",
        "|---|---|---|---|---:|",
        *display_lines,
        "",
        "### fallback 策略",
        "- characters/entity-index：**无旧站 fallback**——type/canonical/books/total/cross_book 全部由"
        "registry + concordance 新数据产出；旧站文件仅用于契约签名比对。",
        "",
        "### 抽样回溯（独立重算 concordance 原始条目，10 条）",
        "| canonical | type | total | 逐书频次（重算=产出） | 首见（书·行 / 机器锚点） |",
        "|---|---|---:|---|---|",
        *sample_lines,
        "",
        "轻索引抽样：",
        "| c | t | n | b | x |",
        "|---|---|---:|---|---|",
        *index_lines,
        "",
        "### 遗留风险",
        "- 桥接期双 schema：characters/entity-index 采用新管线 15 类符号（扩展 type_legend），"
        "旧站页面仅消费 type==='@' 与 entity-index 的 @/☆/◆ 三 tab，预计不受影响；W 组落地后本导出器退役。",
        "- entity-index 的 ☆/◆ 跳转页（arts/sects）由 EX-6 导出，覆盖率不在本表可控范围（旧站同类缺口更大）。",
        "- 身份归并只做 registry 显式 alias（29 条入书 alias_mapped）；语料 unregistered 同形变体（如 晦明 vs 晦明禅师）"
        "保留为独立记录，属上游标注口径问题。",
    ])

    diff1 = esc.finish("characters.json", chars, exporter=EXPORTER, notes=notes)
    diff2 = esc.finish("entity-index.json", index_payload, exporter=EXPORTER, notes=notes)
    print(f"[EX-2] characters={len(items)} entity-index={len(index_payload['entities'])} "
          f"display_overrides={len(display_map)} "
          f"hard_gaps={diff1['hard_gap_count']}/{diff2['hard_gap_count']}")
    return 0 if diff1["hard_gap_count"] == 0 and diff2["hard_gap_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
