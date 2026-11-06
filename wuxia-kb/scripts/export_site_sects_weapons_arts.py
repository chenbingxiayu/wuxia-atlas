# -*- coding: utf-8 -*-
"""EX-6：sects.json / weapons.json / arts.json 薄导出器（docs/51 §三/§五，阶段 1）。

数据源（只读）：
  - 旧考订表（主干）：kb/门派世系表.json、kb/神兵表.json、kb/招式表.json；作品元数据表.json
  - 新管线产物：registry/entities.json（460）、wordlists/new_entity_types.json（268）、
    registry/concordance/<书>.json（出现次数/变体）、tagged/（5 书）
  - 旧站基线：site/data/{sects,weapons,arts}.json（只读参考；旧站独有记录按 docs/51 §五
    "不得静默丢弃"原则保留，source="legacy"）

策略（三轮合并）：
  1. 旧考订表/旧站记录为底（legacy），字段优先保留既有考订值（relations/children/arts_by_pred 等）；
  2. 新 registry/词表校正 canonical/aliases（冲突变体经 alias 表归一，含招式表 conflicts、词表
     surface→canonical、神兵表 alias_candidates）；
  3. 出现次数与覆盖书更新为 concordance 新口径（5 书，含冰魄寒光剑）；新表独有的条目新增
     （source="new"）。排序：sects/arts 按 (-ev_total, canonical)，weapons 按 (-count, canonical)。

缺口（写入 meta.field_gaps，不伪造）：事件参与数、成员册、部分 relations、旧站独有条目等。
默认 dry-run：只写 logs/export/staging/ 与 logs/export/reports/；--apply 才写 site/data（先备份）。

用法：python scripts/export_site_sects_weapons_arts.py            # dry-run
      python scripts/export_site_sects_weapons_arts.py --apply    # 应用（谨慎）
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import export_site_common as esc  # noqa: E402

KB = config.LEGACY_KB
ROOT = config.ROOT

# 新管线覆盖 5 书（4 旧书 + 冰魄寒光剑）；旧站基线 4 书
BOOKS = ["七剑下天山", "塞外奇侠传", "江湖三女侠", "白发魔女传", "冰魄寒光剑"]
OLD_BOOKS = BOOKS[:4]

EXPORTER = "EX-6 export_site_sects_weapons_arts"

# 品类规则：沿用旧站 build_arts_data.CATEGORY_RULES（旧站契约口径，长词优先）
CATEGORY_RULES = [
    ("一百零八式", "剑法"), ("连环夺命剑", "剑法"),
    ("阵法", "阵法"), ("剑阵", "阵法"),
    ("剑法", "剑法"), ("剑术", "剑法"), ("剑", "剑法"),
    ("毒功", "毒"), ("毒掌", "毒"), ("毒砂", "毒"), ("毒爪", "毒"), ("毒", "毒"),
    ("音功", "音"), ("传音", "音"), ("箫", "音"), ("琴", "音"),
    ("掌法", "掌法"), ("掌力", "掌法"), ("掌", "掌法"),
    ("拳法", "拳法"), ("拳术", "拳法"), ("拳", "拳法"),
    ("腿法", "腿法"), ("腿", "腿法"),
    ("轻功", "轻功"), ("身法", "身法"), ("步法", "身法"),
    ("内功", "内功"), ("心法", "内功"), ("神功", "内功"), ("真气", "内功"),
    ("暗器", "暗器"), ("手法", "暗器"), ("针法", "暗器"),
    ("刀法", "刀法"), ("刀", "刀法"),
    ("枪法", "枪法"), ("棍法", "棍法"), ("杖法", "杖法"), ("鞭法", "鞭法"),
    ("指法", "指法"), ("点穴", "点穴"), ("抓手", "擒拿"), ("擒拿", "擒拿"),
    ("爪", "爪法"), ("功", "内功"), ("式", "招式"),
]
# 01g B1-1 能力域通名（属 ^ 专门概念，不作 ☆ 武功条目录入）
GENERIC_ART_NAMES = {"剑法", "剑术", "掌法", "掌力", "拳法", "拳术", "腿法", "指法",
                     "爪法", "杖法", "棍法", "枪法", "鞭法", "身法", "步法", "内功",
                     "心法", "神功", "轻功", "点穴", "擒拿", "暗器", "阵法", "招式",
                     "武艺", "武功", "功夫", "功力", "内力", "真气", "绝技", "拳脚",
                     "毒功", "音功", "武功招式", "兵刃", "兵器"}
# 具名功法后缀（用于保留词表 ☆ 中的专名功法）
ART_SUFFIX = ("剑法", "剑术", "刀法", "掌法", "掌力", "拳法", "拳术", "腿法", "指法",
              "爪法", "杖法", "棍法", "枪法", "鞭法", "身法", "步法", "内功", "心法",
              "神功", "轻功", "点穴", "擒拿", "暗器", "阵法", "剑阵", "毒", "音", "功",
              "诀", "手", "式", "拳", "掌", "爪", "腿", "指")
ACCESSORY_CATS = ["暗器", "身法", "内功", "刀法", "枪法", "棍法", "杖法", "鞭法",
                  "指法", "点穴", "擒拿", "爪法", "轻功", "阵法", "剑法", "掌法",
                  "拳法", "腿法", "招式", "其他"]

# 门派后缀白名单（用于新候选的组织过滤；政权/军队/官署另行排除）
SECT_SUFFIX = ("派", "门", "帮", "教", "会", "寺", "观", "庵", "阁", "山庄", "堡",
               "岛", "谷", "寨", "堂", "镖局", "镖行", "世家", "家", "宗", "盟")
# 政权/军队/官署/族属/泛称（旧站 18 派口径不含）
SECT_EXCLUDE_WORDS = ("天山剑法", "武当", "少林", "天山", "武林", "江湖", "中国", "大军",
                      "官兵", "兵部", "户部", "吏部", "礼部", "刑部", "工部", "皇室",
                      "朝廷", "宗人府", "总督府", "兵", "军", "旗", "族", "国")

# 新词表 ☆/• 的 note 结构：☆ "招式｜父式=X｜kb招式表" / "武功｜父式名（招式表 parent_art）"
#                        • "器物｜kind｜grade｜kb神兵表"
WL_MOVE_NOTE = "招式"
WL_ART_NOTE = "武功"


# ---------------------------------------------------------------- 基础 IO / 工具
def load_json(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def book_rank(b: str) -> int:
    return BOOKS.index(b) if b in BOOKS else len(BOOKS)


def sort_books(books) -> list:
    return sorted({b for b in books if b}, key=book_rank)


def category(name: str) -> str:
    for suf, cat in CATEGORY_RULES:
        if name.endswith(suf):
            return cat
    return "其他"


def dedupe(seq):
    seen, out = set(), []
    for x in seq:
        if x is not None and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def resolve(name, alias: dict, canon_set: set):
    """canonical 归一：精确 → 别名表 → 最长前后缀补全（≤2 字，如 天山剑→天山剑法）。"""
    if not name:
        return None
    name = name.strip()
    if name in canon_set:
        return name
    if name in alias:
        return alias[name]
    cands = [c for c in canon_set if c.startswith(name) and len(c) - len(name) <= 2]
    if len(cands) == 1:
        return cands[0]
    cands = [c for c in canon_set if name.startswith(c) and len(name) - len(c) <= 2]
    if len(cands) == 1:
        return cands[0]
    return name


# ---------------------------------------------------------------- 数据源装载
def load_sources():
    src = {}
    src["old_sects"] = esc.load_baseline("sects.json")
    src["old_weapons"] = esc.load_baseline("weapons.json")
    src["old_arts"] = esc.load_baseline("arts.json")
    src["lineage"] = load_json(KB / "门派世系表.json")
    src["artifacts"] = load_json(KB / "神兵表.json")
    src["moves"] = load_json(KB / "招式表.json")
    src["works"] = load_json(KB / "作品元数据表.json")
    src["entities"] = load_json(ROOT / "registry" / "entities.json")["entities"]
    src["wordlist"] = load_json(ROOT / "wordlists" / "new_entity_types.json")["items"]

    # concordance：{(type, canonical): {count, books: Counter, variants: set}}
    conc = {}
    books_in_conc = []
    for b in BOOKS:
        p = ROOT / "registry" / "concordance" / f"{b}.json"
        if not p.exists():
            continue
        books_in_conc.append(b)
        for e in load_json(p).get("entities", []):
            key = (e["type"], e["canonical"])
            rec = conc.setdefault(key, {"count": 0, "books": Counter(),
                                        "chapters": {}, "variants": set()})
            rec["count"] += e.get("total", 0)
            rec["books"][b] += e.get("total", 0)
            rec["chapters"][b] = sorted(c.get("chapter", 0) for c in e.get("chapter_counts", []) or [])
            for v in e.get("variants", []) or []:
                d = v.get("display") if isinstance(v, dict) else None
                if d:
                    rec["variants"].add(d)
    src["conc"] = conc
    src["conc_books"] = books_in_conc or BOOKS

    # 别名表（新 tables）
    sect_alias, art_alias, weapon_alias = {}, {}, {}
    sect_canon, art_canon, weapon_canon = set(), set(), set()
    for e in src["entities"]:
        if e["type"] in ("◆", "&"):
            sect_canon.add(e["canonical"])
            for a in e.get("aliases", []) or []:
                sect_alias.setdefault(a, e["canonical"])
    for it in src["wordlist"]:
        t, c, s = it.get("type"), it.get("canonical"), it.get("surface")
        if not c:
            continue
        if t == "◆":
            sect_canon.add(c)
            if s and s != c:
                sect_alias.setdefault(s, c)
        elif t == "☆":
            art_canon.add(c)
            if s and s != c:
                art_alias.setdefault(s, c)
        elif t == "•":
            weapon_canon.add(c)
            if s and s != c:
                weapon_alias.setdefault(s, c)
    for a in src["old_arts"]["arts"]:
        art_canon.add(a["canonical"])
        for al in a.get("aliases", []) or []:
            art_alias.setdefault(al, a["canonical"])
    for m in src["moves"]["moves"]:
        art_canon.add(m["canonical"])
    # 注：招式表 parent_art 不入 art_canon —— 由 alias/最长前后缀补全归一到旧站/招式表规范名
    #     （如 天山剑→天山剑法、达摩剑→达摩剑法；避免与招式名混淆）。
    # 招式表 conflicts：多父归属中的变体视为同父异名（取首个出现次数多者做规范名）
    for c in src["moves"].get("conflicts", []) or []:
        parts = [p.get("art") for p in c.get("parents", []) if p.get("art")]
        if len(parts) >= 2:
            canon = parts[0]
            for v in parts[1:]:
                art_alias.setdefault(v, canon)
    for a in src["artifacts"]["artifacts"]:
        weapon_canon.add(a["canonical"])
    for pair in src["artifacts"].get("alias_candidates", []) or []:
        if "⊂" in pair:
            left, right = [x.strip() for x in pair.split("⊂", 1)]
            weapon_alias.setdefault(left, right)
    src["sect_alias"], src["art_alias"], src["weapon_alias"] = sect_alias, art_alias, weapon_alias
    src["sect_canon"], src["art_canon"], src["weapon_canon"] = sect_canon, art_canon, weapon_canon
    return src


# ---------------------------------------------------------------- 契约字段自查
def _audit_records(name: str, records: list, record_keys: set, nested: dict) -> list:
    """逐记录/nested 数组元素字段覆盖自查（契约 diff 不含嵌套，这里补齐）。"""
    issues = []
    for i, r in enumerate(records):
        miss = sorted(record_keys - set(r.keys()))
        if miss:
            issues.append(f"{name}[{i}] 缺字段 {miss}")
            continue
        for path, keys in nested.items():
            val = r
            for part in path.split("."):
                if isinstance(val, dict) and part in val:
                    val = val[part]
                else:
                    val = None
                    break
            if isinstance(val, list):
                for j, el in enumerate(val):
                    if isinstance(el, dict):
                        m = sorted(keys - set(el.keys()))
                        if m:
                            issues.append(f"{name}[{i}].{path}[{j}] 缺 {m}")
                            break
            elif isinstance(val, dict):
                for k, sub in val.items():
                    if isinstance(sub, dict) and "relations" in sub:
                        for j, el in enumerate(sub["relations"]):
                            m = sorted(keys - set(el.keys()))
                            if m:
                                issues.append(f"{name}[{i}].{path}.{k}.relations[{j}] 缺 {m}")
                                break
    return issues[:20]


# ---------------------------------------------------------------- weapons.json
def build_weapons(src: dict) -> tuple[dict, dict]:
    artifacts = src["artifacts"]
    named = [a for a in artifacts["artifacts"]
             if a.get("level") == "名物" and a.get("status") != "rejected"]
    old_by = {w["canonical"]: w for w in src["old_weapons"]["weapons"]}
    alias, canon_set = src["weapon_alias"], src["weapon_canon"]
    conc = src["conc"]

    records, n_legacy, n_new = [], 0, 0
    n_count_updated = n_alias_added = 0
    for a in named:
        canon = resolve(a["canonical"], alias, canon_set) or a["canonical"]
        old = old_by.get(a["canonical"]) or old_by.get(canon) or {}
        chain = [{"verb": e.get("verb"), "persons": list(e.get("persons") or []),
                  "book": e.get("book"), "loc": e.get("loc"), "conf": e.get("conf")}
                 for e in (a.get("chain") or [])[:12]]
        borrowers = [{"name": b.get("name"), "n": b.get("n", 0)} for b in (a.get("borrowers") or [])]
        borrower_names = {b["name"] for b in borrowers}
        holders = [{"name": h.get("name"), "n": h.get("n", 0)} for h in (a.get("holders") or [])
                   if h.get("name") not in borrower_names]
        makers = [{"name": m.get("name"), "n": m.get("n", 0)} for m in (a.get("makers") or [])]
        books = dict(a.get("books") or {})
        count = a.get("count", 0)
        ev_total = a.get("ev_total", len(a.get("evidence") or []))
        # 3) 出现次数与覆盖书 → concordance 新口径
        key = ("•", canon)
        hit = conc.get(key) or conc.get(("•", a["canonical"]))
        if hit:
            if hit["count"] and hit["count"] != count:
                n_count_updated += 1
            count = hit["count"]
            books = {}
            for b in sort_books(hit["books"].keys()):
                books[b] = list(hit["chapters"].get(b) or [])
        # 2) aliases：concordance 变体 + 词表 surface + 神兵表 alias_candidates（新增字段）
        aliases = set(old.get("aliases") or [])
        aliases.update(hit["variants"] if hit else set())
        for it in src["wordlist"]:
            if it.get("type") == "•" and resolve(it.get("canonical", ""), alias, canon_set) == canon:
                if it.get("surface") and it["surface"] != canon:
                    aliases.add(it["surface"])
        for pair in artifacts.get("alias_candidates", []) or []:
            if "⊂" in pair:
                left, right = [x.strip() for x in pair.split("⊂", 1)]
                if right == canon and left != canon:
                    aliases.add(left)
        aliases.discard(canon)
        if aliases:
            n_alias_added += 1
        rec = {
            "canonical": canon,
            "kind": a.get("kind"),
            "grade": a.get("grade"),
            "grade_basis": a.get("grade_basis"),
            "conf": a.get("conf") or "weak",
            "status": a.get("status") or "auto",
            "chain": chain,
            "holders": holders,
            "borrowers": borrowers,
            "makers": makers,
            "end_state": a.get("end_state"),
            "books": books,
            "count": count,
            "ev_total": ev_total,
            "evidence": [{"book": e.get("book"), "loc": e.get("loc"), "kind": e.get("kind")}
                         for e in (a.get("evidence") or [])[:12]],
            "aliases": sorted(aliases),
            "source": "legacy",
        }
        records.append(rec)
        n_legacy += 1

    records.sort(key=lambda r: (-(r.get("count") or 0), r["canonical"]))
    levels = Counter(a.get("level") for a in artifacts["artifacts"])
    meta = {
        "generated": esc.today(),
        "rev": artifacts["meta"].get("rev", 16),
        "schema": "artifacts-v1",
        "based_on": {"books": list(src["conc_books"]), "kb_date": artifacts["meta"].get("based_on", {}).get("kb_date", "2026-11-02")},
        "wordlist": artifacts["meta"].get("wordlist", "artifact-wordlist-v0.1"),
        "conf_legend": artifacts["meta"].get("conf_legend", "strong=明文流转句式 ok=交战/共现侧证 weak=仅出现"),
        "totals": {
            "entities": len(artifacts["artifacts"]),
            "名物": levels.get("名物", 0),
            "凡物": levels.get("凡物", 0),
            "药材": levels.get("药材", 0),
            "reviewed": sum(1 for a in artifacts["artifacts"] if a.get("status") == "reviewed"),
            "chain_strong": sum(1 for r in records for e in r["chain"] if e.get("conf") == "strong"),
        },
        "source": "新 registry/词表 + 旧考订表只读（桥接层 EX-6）",
        "field_gaps": [
            "books/count：优先更新为 registry/concordance（5 书，含冰魄寒光剑）新口径（含逐回号）；未匹配记录保留神兵表旧值。",
            "aliases：新增字段（旧 weapons.json 契约无）；来源=concordance 变体/词表 • surface/神兵表 alias_candidates。",
            "ev_total：保留神兵表『证据条数』口径（旧站同口径），未随 concordance 出现次数改动。",
            "凡物 24 条 / 药材 19 条：按旧站 L0 切片口径（名物 only）不入 weapons.json。",
            "wordlist • 80 条均已在神兵表『名物』183 条内（canonical 对齐后无新增记录）。",
            "事件参与/价格等旧站未提供字段：无缺口（旧契约亦无）。",
        ],
    }
    payload = {"meta": meta, "weapons": records}

    # 若旧站记录含回号，优先保留旧 books（更细）
    for r in records:
        old = old_by.get(r["canonical"])
        if old and isinstance(old.get("books"), dict) and old["books"]:
            merged = {b: old["books"].get(b, []) for b in sort_books(set(old["books"]) | set(r["books"]))}
            for b in merged:
                if not merged[b] and isinstance(r["books"].get(b), list):
                    merged[b] = r["books"][b]
            r["books"] = merged

    notes = (f"记录数：旧站 {len(old_by)} → 新 {len(records)}（legacy={n_legacy} / new={n_new}）；"
             f"记录与旧站同集合（神兵表名物 183）；count 更新 {n_count_updated} 条、aliases 补充 {n_alias_added} 条。")
    return payload, {"notes": notes, "legacy": n_legacy, "new": n_new}


# ---------------------------------------------------------------- arts.json
def build_arts(src: dict) -> tuple[dict, dict]:
    old = {a["canonical"]: a for a in src["old_arts"]["arts"]}
    alias, canon_set = src["art_alias"], src["art_canon"]
    moves = src["moves"]["moves"]
    conc = src["conc"]
    move_names = {m["canonical"] for m in moves}
    parents = {m.get("parent_art") for m in moves if m.get("parent_art") not in (None, "", "待考")}

    records: dict[str, dict] = {}
    source_of: dict[str, str] = {}

    def ensure(canon: str) -> dict:
        canon = resolve(canon, alias, canon_set) or canon
        if canon not in records:
            records[canon] = {
                "canonical": canon, "category": category(canon), "aliases": [],
                "ev_total": 0, "books": [], "cross_book": False, "relations": {},
            }
            source_of[canon] = "legacy"
        return records[canon]

    # 1) 旧站 arts 全量保留（legacy 主干）
    for name, a in old.items():
        canon = resolve(name, alias, canon_set) or name
        rec = records.setdefault(canon, {})
        rec.update({
            "canonical": canon,
            "category": a.get("category") or category(canon),
            "aliases": list(a.get("aliases") or []),
            "ev_total": a.get("ev_total", 0),
            "books": sort_books(a.get("books") or []),
            "cross_book": bool(a.get("cross_book")),
            "relations": json.loads(json.dumps(a.get("relations") or {}, ensure_ascii=False)),
        })
        if a.get("children"):
            rec["children"] = [{"name": c.get("name"), "conf": c.get("conf", "ok"),
                                "sect": c.get("sect")} for c in a["children"]]
        source_of[canon] = "legacy"

    # 2) 旧考订表：招式表 moves 按 parent_art 聚合为「功法级」arts（招式只进 children，不占顶层）
    def _resolve_parent(p):
        p = resolve(p, alias, canon_set) or p
        if p in records:
            return p
        cands = [c for c in records if c.startswith(p) and len(c) - len(p) <= 2]
        return cands[0] if len(cands) == 1 else p

    parent_moves = defaultdict(list)
    for m in moves:
        p = m.get("parent_art")
        if p in (None, "", "待考"):
            continue
        parent_moves[_resolve_parent(p)].append(m)
    parents_added = 0
    for p, ms in sorted(parent_moves.items()):
        if p in records:
            continue
        ev = [e for m in ms for e in (m.get("evidence") or [])]
        books = sort_books(e.get("book") for e in ev if e.get("book"))
        rel = {}
        for m in ms:
            if m.get("conf") not in ("strong", "ok") or m.get("status") == "rejected":
                continue
            for e in (m.get("evidence") or [])[:1]:
                if not e.get("book"):
                    continue
                rel.setdefault(e["book"], {"relations": []})["relations"].append({
                    "s": m["canonical"], "st": "☆", "pred": "子式",
                    "locs": [e.get("loc")] if e.get("loc") else [],
                    "ev": 1, "note": f"招式表子式（conf={m.get('conf')}）",
                })
        records[p] = {
            "canonical": p, "category": category(p), "aliases": [],
            "ev_total": len(ev), "books": books, "cross_book": len(books) > 1,
            "relations": rel,
        }
        source_of[p] = "legacy"
        parents_added += 1

    # 3) 新词表 ☆：只补「已具名功法」（01g B1-1 能力域通名归 ^，不作 ☆ 条目录入）
    move_names = {m["canonical"] for m in moves}
    named_added = 0
    for it in src["wordlist"]:
        if it.get("type") != "☆":
            continue
        canon = resolve(it["canonical"], alias, canon_set) or it["canonical"]
        if canon in records:
            continue
        if canon in move_names:  # 招式名只入父式 children
            continue
        note = it.get("note") or ""
        # 只补语料 ☆ 具名技艺；「父式名」条目由招式表 parent_art 聚合覆盖，不重复建条
        if "具名技艺" not in note:
            continue
        if canon in GENERIC_ART_NAMES or canon.startswith(("上乘", "精妙", "绝顶", "上等")):
            continue
        if not canon.endswith(ART_SUFFIX):
            continue
        if len(canon) < 3 and canon not in parents and canon not in src["art_canon"]:
            continue
        hit = conc.get(("☆", canon)) or conc.get(("☆", it["canonical"]))
        books = sort_books(hit["books"].keys()) if hit else []
        records[canon] = {
            "canonical": canon, "category": category(canon), "aliases": [],
            "ev_total": hit["count"] if hit else 0, "books": books,
            "cross_book": len(books) > 1, "relations": {},
        }
        source_of[canon] = "new"
        named_added += 1

    # 4) children：招式表 strong/ok（未 rejected）→ 父式 arts
    n_children = 0
    for m in moves:
        if m.get("conf") not in ("strong", "ok") or m.get("status") == "rejected":
            continue
        parent = m.get("parent_art")
        if parent in (None, "", "待考"):
            continue
        parent = resolve(parent, alias, canon_set) or parent
        if parent not in records:
            continue
        children = records[parent].setdefault("children", [])
        if any(c["name"] == m["canonical"] for c in children):
            continue
        children.append({"name": m["canonical"], "conf": m["conf"], "sect": m.get("sect")})
        n_children += 1

    # 5) 覆盖/次数/别名/relations 补全（新口径）
    n_count_updated = 0
    for canon, rec in records.items():
        hit = conc.get(("☆", canon))
        old_books = rec.get("books") or []
        if hit:
            books = sort_books(set(old_books) | set(hit["books"].keys()))
            if hit["count"] and not source_of.get(canon) == "legacy":
                rec["ev_total"] = hit["count"]
            n_count_updated += 1
        else:
            books = sort_books(old_books)
        if not books:  # 招式表证据缺失时回退旧站
            books = sort_books(old.get(canon, {}).get("books") or [])
        rec["books"] = books
        rec["cross_book"] = len(books) > 1
        # aliases：旧 aliases + concordance 变体 + 词表 surface
        al = set(rec.get("aliases") or [])
        if hit:
            al.update(hit["variants"])
        for it in src["wordlist"]:
            if it.get("type") == "☆" and resolve(it.get("canonical", ""), alias, canon_set) == canon:
                if it.get("surface") and it["surface"] != canon:
                    al.add(it["surface"])
        al.discard(canon)
        rec["aliases"] = sorted(al)
        # relations：旧记录保留；新记录若为空，用招式表 children 派生（子式关系）
        if not rec["relations"] and rec.get("children"):
            rel = {}
            child_names = {c["name"] for c in rec["children"]}
            for m in moves:
                if m["canonical"] not in child_names:
                    continue
                for e in (m.get("evidence") or []):
                    rel.setdefault(e.get("book"), {"relations": []})
                    rel[e["book"]]["relations"].append({
                        "s": m["canonical"], "st": "☆", "pred": "子式",
                        "locs": [e.get("loc")] if e.get("loc") else [],
                        "ev": 1, "note": f"招式表子式（conf={m.get('conf')}）",
                    })
            if rel:
                rec["relations"] = rel
        rec["source"] = source_of.get(canon, "legacy")

    items = sorted(records.values(), key=lambda r: (-(r.get("ev_total") or 0), r["canonical"]))
    by_cat = Counter(r["category"] for r in items)
    # 契约基线 by_category 的全部 13 个品类键必须保留（值可为 0）
    base_cats = list((src["old_arts"]["meta"].get("totals", {}).get("by_category") or {}).keys())
    for c in ACCESSORY_CATS:
        if c not in base_cats:
            base_cats.append(c)
    by_category = {c: int(by_cat.get(c, 0)) for c in base_cats}
    n_legacy = sum(1 for r in items if r["source"] == "legacy")
    n_new = len(items) - n_legacy
    meta = {
        "generated": esc.today(),
        "schema": "arts-v1",
        "books": list(src["conc_books"]),
        "totals": {"arts": len(items),
                   "cross_book": sum(1 for r in items if r["cross_book"]),
                   "by_category": by_category},
        "source": "新 registry/词表 + 旧考订表只读（桥接层 EX-6）",
        "field_gaps": [
            "记录口径：arts 顶层=旧站武功/功法级 116 条全量保留 ∪ 招式表 moves 按 parent_art 聚合的父式功法（招式只进 children）；旧站 entries 与旧字段（relations/children）原样保留。",
            "relations：旧站记录保留旧考订 relation（4 书）；新增父式记录 relations 由招式表子式证据派生（pred=子式，无人工考订），无子式证据者为 {}。",
            "children：仅收 招式表 conf=strong/ok 且未 rejected 的招式；weak 不入 children（沿用旧站 arts v2 口径）。",
            "ev_total：旧站记录保留旧值（关系证据合计口径）；新增父式用招式表证据条数或 concordance 出现次数（口径不同，已在报告说明）。",
            "aliases：旧 aliases + concordance 变体 + 词表 surface 合并；招式表 conflicts 的多父变体经 alias 归一并入 aliases。",
            "☆ 词表补充：仅保留具名功法（含功法后缀且长度≥3，或 note 标注『武功｜父式名』）；01g B1-1 能力域通名（剑法/掌法/拳法/内功/轻功/身法/招式/武艺/武功/功夫/功力等）归 ^，不入 arts。",
            "books：覆盖更新为 5 书（含冰魄寒光剑）；旧站独有 8 条 tagged/concordance 无对应（八卦紫金刀连环六十四式等）保留旧 books。",
        ],
    }
    payload = {"meta": meta, "arts": items}
    n_children_total = sum(len(r.get("children") or []) for r in items)
    cat_dist = dict(sorted(by_cat.items(), key=lambda kv: -kv[1]))
    notes = (f"记录数：旧站 {len(old)} → 新 {len(items)}（legacy={n_legacy} / new={n_new}）；"
             f"新增父式 {parents_added} 条、词表具名 ☆ 补充 {named_added} 条；"
             f"children 派生 {n_children} 条（合 {n_children_total} 个，含旧站保留）；"
             f"覆盖/次数更新 {n_count_updated} 条；category 分布 {json.dumps(cat_dist, ensure_ascii=False)}"
             f"（『其他』= {by_cat.get('其他', 0)} 条）。")
    return payload, {"notes": notes, "legacy": n_legacy, "new": n_new,
                     "children": n_children_total, "categories": cat_dist}


# ---------------------------------------------------------------- sects.json
GENERIC_ORG = {"镖局", "镖行", "马帮", "武林", "江湖", "中国", "大军", "官兵"}


def _sect_is_martial(name: str, src: dict) -> bool:
    """新候选组织是否属旧站口径的『门派/组织』（排除政权/军队/官署/族属/泛称）。"""
    if not name or len(name) < 2 or name in GENERIC_ORG:
        return False
    if name in src["art_canon"] or resolve(name, src["art_alias"], src["art_canon"]) in src["art_canon"]:
        return False
    if any(w in name for w in SECT_EXCLUDE_WORDS):
        return False
    if name.endswith(("朝", "廷", "国", "洲", "军", "兵", "厂", "府", "院", "室", "党",
                      "族", "旗", "藩", "营", "氏", "部", "舵")):
        return False
    return name.endswith(SECT_SUFFIX)


def build_sects(src: dict) -> tuple[dict, dict]:
    lineage = {s["sect"]: s for s in src["lineage"].get("sects", [])}
    old_by = {s["canonical"]: s for s in src["old_sects"]["sects"]}
    alias, canon_set = src["sect_alias"], src["sect_canon"]
    conc = src["conc"]
    moves = src["moves"]["moves"]

    move_sect_counter = Counter()
    move_by_sect = defaultdict(list)
    for m in moves:
        s = m.get("sect")
        if not s:
            continue
        rs = resolve(s, alias, canon_set) or s
        move_sect_counter[rs] += 1
        move_by_sect[rs].append(m)

    records: dict[str, dict] = {}
    source_of: dict[str, str] = {}

    def blank(canon: str) -> dict:
        return {
            "canonical": canon, "books": [], "cross_book": False, "ev_total": 0,
            "arts_by_pred": {}, "members": [], "tenures": [],
            "lineage_gaps": [], "lineage_todo": [],
        }

    # 1) 旧站记录全量保留（legacy 主干）
    for name, s in old_by.items():
        canon = resolve(name, alias, canon_set) or name
        rec = json.loads(json.dumps(blank(canon), ensure_ascii=False))
        rec.update(s)
        rec["canonical"] = canon
        records[canon] = rec
        source_of[canon] = "legacy"

    # 2) 门派世系表 7 派（旧考订表主干：tenures/gaps/open_questions 权威值）
    for sect, d in lineage.items():
        canon = resolve(sect, alias, canon_set) or sect
        rec = records.get(canon) or json.loads(json.dumps(blank(canon), ensure_ascii=False))
        rec["tenures"] = json.loads(json.dumps(d.get("tenures") or [], ensure_ascii=False))
        rec["lineage_gaps"] = json.loads(json.dumps(d.get("gaps") or [], ensure_ascii=False))
        rec["lineage_todo"] = json.loads(json.dumps(d.get("open_questions") or [], ensure_ascii=False))
        # 成员：旧站记录优先，其次世系表 tenures 门下成员
        if not rec.get("members"):
            members = []
            for t in rec["tenures"]:
                for mm in (t.get("members") or []):
                    if isinstance(mm, dict) and mm.get("name"):
                        members.append({"name": mm["name"], "tier": mm.get("tier") or "ok", "via": []})
            rec["members"] = dedupe(sorted(members, key=lambda x: x["name"]))
        records[canon] = rec
        if source_of.get(canon) != "legacy":
            source_of[canon] = "legacy"

    # 3) 新表候选：registry ◆/&、wordlist ◆、招式表 sect（过滤政权/军队/官署/族属）
    fam_canon = {e["canonical"] for e in src["entities"] if e["type"] == "&"}
    candidates = {}
    for e in src["entities"]:
        if e["type"] in ("◆", "&"):
            candidates.setdefault(e["canonical"], "registry")
    for it in src["wordlist"]:
        if it.get("type") != "◆":
            continue
        note = it.get("note") or ""
        if any(w in note for w in ("政权", "官署", "朝廷机构", "机构")):
            continue
        candidates.setdefault(it["canonical"], "wordlist")
    for s in move_sect_counter:
        candidates.setdefault(s, "moves")
    for name, origin in candidates.items():
        canon = resolve(name, alias, canon_set) or name
        if canon in records:
            # 已有记录：补 books/ev（新口径），不改旧字段
            continue
        lineage_hit = lineage.get(canon) or lineage.get(name)
        if canon in fam_canon:
            qualify = bool(canon in move_sect_counter or lineage_hit)
        else:
            qualify = bool(_sect_is_martial(canon, src) or lineage_hit)
        if not qualify:
            continue
        rec = json.loads(json.dumps(blank(canon), ensure_ascii=False))
        # arts_by_pred：招式表 sect → parent_art（pred=拥有，旧站武功册口径）
        pred = defaultdict(list)
        for m in move_by_sect.get(canon, []):
            ev = m.get("evidence") or []
            locs = [e.get("loc") for e in ev if e.get("loc")][:4]
            parent = m.get("parent_art")
            level = "招式"
            art = m["canonical"]
            note = f"招式表：{m['canonical']}（conf={m.get('conf')}）"
            if parent not in (None, "", "待考"):
                art = resolve(parent, alias, canon_set) or parent
                level = "功法"
                note = f"招式表：{m['canonical']} 属 {art}（conf={m.get('conf')}）"
            for e in (ev[:1] or [{}]):
                pred["拥有"].append({
                    "art": art, "pred": "拥有", "level": level, "locs": locs,
                    "ev": len(ev), "note": note, "book": e.get("book") or (ev[0].get("book") if ev else None),
                })
        rec["arts_by_pred"] = dict(pred)
        # 成员：世系表 tenures（若有）
        if lineage_hit:
            rec["tenures"] = json.loads(json.dumps(lineage_hit.get("tenures") or [], ensure_ascii=False))
            rec["lineage_gaps"] = json.loads(json.dumps(lineage_hit.get("gaps") or [], ensure_ascii=False))
            rec["lineage_todo"] = json.loads(json.dumps(lineage_hit.get("open_questions") or [], ensure_ascii=False))
            members = []
            for t in rec["tenures"]:
                for mm in (t.get("members") or []):
                    if isinstance(mm, dict) and mm.get("name"):
                        members.append({"name": mm["name"], "tier": mm.get("tier") or "ok", "via": []})
            rec["members"] = dedupe(sorted(members, key=lambda x: x["name"]))
        records[canon] = rec
        source_of[canon] = "new"

    # 4) 覆盖/次数：concordance ◆（新口径）+ 招式表门派证据 books
    n_count_updated = 0
    for canon, rec in records.items():
        if rec.get("source") == "new":
            pass
        hit = conc.get(("◆", canon))
        books = set(rec.get("books") or [])
        if hit:
            books |= set(hit["books"].keys())
            rec["ev_total"] = max(rec.get("ev_total") or 0, hit["count"])
            n_count_updated += 1
        # 招式表门派证据覆盖书
        for m in move_by_sect.get(canon, []):
            for e in (m.get("evidence") or []):
                if e.get("book"):
                    books.add(e["book"])
        rec["books"] = sort_books(books)
        rec["cross_book"] = len(rec["books"]) > 1
        rec["source"] = source_of.get(canon, "legacy")
        rec.setdefault("members", [])
        rec.setdefault("tenures", [])
        rec.setdefault("lineage_gaps", [])
        rec.setdefault("lineage_todo", [])
        rec.setdefault("arts_by_pred", {})

    items = sorted(records.values(), key=lambda r: (-(r.get("ev_total") or 0), r["canonical"]))
    items = [{"canonical": r["canonical"], "books": r["books"], "cross_book": r["cross_book"],
              "ev_total": r["ev_total"], "arts_by_pred": r["arts_by_pred"],
              "members": r["members"], "tenures": r["tenures"],
              "lineage_gaps": r["lineage_gaps"], "lineage_todo": r["lineage_todo"],
              "source": r["source"]} for r in items]
    n_legacy = sum(1 for r in items if r["source"] == "legacy")
    n_new = len(items) - n_legacy
    new_names = [r["canonical"] for r in items if r["source"] == "new"]
    meta = {
        "generated": esc.today(),
        "schema": "sects-v1",
        "books": list(src["conc_books"]),
        "totals": {"sects": len(items), "cross_book": sum(1 for r in items if r["cross_book"])},
        "note": src["old_sects"]["meta"].get("note", "") + "（EX-6 桥接：旧站 18 派全量保留 + 新表候选，见 field_gaps）",
        "source": "新 registry/词表 + 旧考订表只读（桥接层 EX-6）",
        "field_gaps": [
            "arts_by_pred：旧站记录保留旧关系表考订值（冻结）；新增门派由招式表（sect+parent_art）派生，pred 统一记『拥有』（新关系层 N5 未上线）。",
            "members：旧站来自 dossiers 门派线索（EX-3 产物）；新门派暂以世系表 tenures 门下成员回填，无则 []（不伪造）。",
            "tenures/lineage_gaps/lineage_todo：仅门派世系表 7 派有考订值，其余门派为空数组；旧站记录已保留旧值。",
            "ev_total：旧口径=事件参与数（事件表冻结）；本次更新为 concordance/tagged 标注出现次数口径（D03 事件层未上线）。",
            "books：更新为 5 书（含冰魄寒光剑）；旧站 4 书。",
            f"新增新表候选 {n_new} 派：{('、'.join(new_names[:30]) + ('…' if len(new_names) > 30 else '')) or '—'}；政权/军队/官署/族属类组织按旧站口径排除。",
        ],
    }
    payload = {"meta": meta, "sects": items}
    notes = (f"记录数：旧站 {len(old_by)} → 新 {len(items)}（legacy={n_legacy} / new={n_new}）；"
             f"覆盖/次数更新 {n_count_updated} 条；世系表 7 派 tenures/gaps 已回填。")
    return payload, {"notes": notes, "legacy": n_legacy, "new": n_new}


# ---------------------------------------------------------------- 主流程
NESTED_KEYS = {
    "sects": {
        "arts_by_pred": {"art", "pred", "level", "locs", "ev", "note", "book"},
        "members": {"name", "tier", "via"},
        "tenures": {"leader", "conf", "period", "evidence", "members", "successor"},
        "lineage_gaps": {"before", "note"},
        "lineage_todo": {"sect", "name", "book", "loc", "kind"},
    },
    "weapons": {
        "chain": {"verb", "persons", "book", "loc", "conf"},
        "holders": {"name", "n"},
        "borrowers": {"name", "n"},
        "makers": {"name", "n"},
        "evidence": {"book", "loc", "kind"},
    },
    "arts": {
        "children": {"name", "conf", "sect"},
        "relations": {"s", "st", "pred", "locs", "ev", "note"},
    },
}
RECORD_KEYS = {
    "sects": {"canonical", "books", "cross_book", "ev_total", "arts_by_pred",
              "members", "tenures", "lineage_gaps", "lineage_todo"},
    "weapons": {"canonical", "kind", "grade", "grade_basis", "conf", "status", "chain",
                "holders", "borrowers", "makers", "end_state", "books", "count",
                "ev_total", "evidence"},
    "arts": {"canonical", "category", "aliases", "ev_total", "books", "cross_book", "relations"},
}


def main() -> int:
    src = load_sources()
    payloads = {}
    payloads["weapons"], w_stats = build_weapons(src)
    payloads["arts"], a_stats = build_arts(src)
    payloads["sects"], s_stats = build_sects(src)

    fails = []
    for name in ("sects", "weapons", "arts"):
        issues = _audit_records(name, payloads[name][name], RECORD_KEYS[name], NESTED_KEYS[name])
        if issues:
            fails.extend(issues)
            print(f"[audit] {name} 嵌套字段缺口 {len(issues)}：{issues[:3]}")

    notes_map = {
        "sects.json": s_stats["notes"] + " 口径：sects 按 (-ev_total, canonical) 排序；旧站 18 派全量保留，新表候选过滤政权/军队/官署/族属。",
        "weapons.json": w_stats["notes"] + " 口径：weapons 按神兵表名物 183 条直接映射，按 (-count, canonical) 排序；aliases 为新增字段。",
        "arts.json": a_stats["notes"] + " 口径：arts 按 (-ev_total, canonical) 排序；旧站 116 条全量保留 + 招式表/词表新增。",
    }
    diffs = {}
    for name in ("sects", "weapons", "arts"):
        fname = name + ".json"
        diffs[fname] = esc.finish(fname, payloads[name], exporter=EXPORTER, notes=notes_map[fname])

    print("\n[EX-6] 汇总（old → new / source 分布 / hard_gap）")
    for fname, d in diffs.items():
        st = {"sects.json": s_stats, "weapons.json": w_stats, "arts.json": a_stats}[fname]
        print(f"  {fname}: {d['old_record_count']} → {d['new_record_count']} "
              f"| legacy={st['legacy']} new={st['new']} | hard_gap={d['hard_gap_count']} "
              f"| missing={len(d['missing_keys'])} type={len(d['type_mismatch'])} item_missing={len(d['item_missing_keys'])}")
    total = sum(d["hard_gap_count"] for d in diffs.values())
    if fails:
        print(f"[audit] 嵌套字段自查未通过 {len(fails)} 项（见上）")
    print(f"[EX-6] 契约硬缺口合计 = {total}")
    return 0 if total == 0 and not fails else 1


if __name__ == "__main__":
    sys.exit(main())
