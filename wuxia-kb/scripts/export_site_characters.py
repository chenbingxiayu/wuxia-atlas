# -*- coding: utf-8 -*-
"""EX-2 · characters.json + entity-index.json 导出器（桥接层，docs/51 §三/§五）。

数据源（新管线唯一真源）：
  - registry/entities.json              实体身份层（id/type/canonical/aliases/status）
  - registry/concordance/<书>.json       逐书逐回统计（total/chapter_counts/variants/registration）
  - registry/display_canonical.json      展示层覆盖（canonical→display；默认 canonical==display）
  - 旧站 dossiers.json（阶段 0 冻结备份优先，只读）  主档"有实质内容"判定源（W0-T2）
旧站 site/data/characters.json、entity-index.json 只作契约签名与记录级形状基线；
characters 本表全部字段可由新数据产出，**不触发旧值 fallback**
（fallback 仅用于 W0-T2 主档"有实质内容"判定与 EX-3 dossiers 派生字段回填）。

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

W2-A1（天山演示版总体方案 §4.1 A1 / §1.2，2026-11-10）：
  - **entity-index aliases 别名并入**：每行新增 `aliases:[{alias,count}...]`（只增字段），
    由本脚本聚合层 variants 跨书合并产出（与 EX-3 dossiers.aliases 同源同排序），
    排除 canonical 本名、不设 top-N 截断；无别名者 `[]`；
    @/☆/◆ 三类均带——人物/武功/门派总览搜索命中别名（白发魔女/玉罗刹/晦明禅师可搜）。

W0-T2（天山演示版总体方案 §二/§1.2/§4.2-B7，2026-11-08）：
  - **别名归并前置**：可选 TSV `kb/校订/别名归并.tsv`（form/merge_to/note，缺文件=no-op），
    归并映射在 registry 归一之后、频次聚合之前生效；链式归并显式禁止（merge_to 不得再为 form）；
  - **主档圈定**：total≥30 ∪ 有实质内容（key_events/lineage.masters|disciples/combat.kills|slain_by/
    arts 非空）；阈值与规则参数进 meta.major_rule，不硬编码（全量口径回切时规则随 meta.scope 走，R6）；
  - **entity-index page 标志**：@ 主档 true / 存目 false；☆/◆ 恒 true（武功/门派有独立页）——只增字段；
  - **scope**：--scope <profile> 时聚合仅含 scope 书目（entity-index 的 n/b/x 为 scope 内重算值，
    scope 外实体不进轻索引）；不带 --scope 保持全量口径（向后兼容）。

用法：
  python scripts/export_site_characters.py           # dry-run（staging + 报告）
  python scripts/export_site_characters.py --apply   # 写 site/data（export_site_common 先备份）
  python scripts/export_site_characters.py --scope tianshan-demo   # 天山 7 书裁剪口径
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import config
import export_site_common as esc
import symbols

REGISTRY_PATH = config.DIR_REGISTRY / "entities.json"
CONCORDANCE_DIR = config.DIR_REGISTRY / "concordance"
DISPLAY_CANONICAL_PATH = config.DIR_REGISTRY / "display_canonical.json"   # 展示层覆盖表（只增字段用）
BOOK_META_PATH = config.LEGACY_KB / "作品元数据表.json"      # 只读：书序
ALIAS_MERGE_TSV = config.LEGACY_KB / "校订" / "别名归并.tsv"  # 只读：B7 别名归并表（缺文件=no-op）

SCHEMA_CHARACTERS = "site-characters-v1"
SCHEMA_ENTITY_INDEX = "entity-index-v1"
SCHEMA_DISPLAY = "display-canonical-v1"
SOURCE = "wuxia-kb 新管线 + 旧站 fallback（桥接层 EX-2/EX-3）"
EXPORTER = "scripts/export_site_characters.py（EX-2）"
DISPLAY_SAMPLE_CANONICALS = ("玄烨", "朱由检", "福临", "胤禛", "哈玛雅")

# W0-T2 主档圈定阈值（方案 §2.2：阈值进 meta 不硬编码——调用点一律用本常量/参数，便于调整）
MIN_TOTAL = 30
# 旧站 dossiers fallback（主档内容判定 + EX-3 派生字段回填共用；只读）
FALLBACK_TAG = "phase0_20261105"

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


# ---------------------------------------------------------------- 旧站 dossiers fallback（只读）
# W0-T2 起由 EX-2/EX-3 共用：EX-2 用于主档"有实质内容"判定，EX-3 用于派生字段回填。
def display_path(p) -> str:
    """仓内相对路径（报告可移植）；仓外路径原样返回。"""
    for base in (config.ROOT, config.REPO_ROOT):
        try:
            return p.resolve().relative_to(base).as_posix()
        except (ValueError, AttributeError, TypeError):
            continue
    return str(p)


def load_fallback_dossiers() -> tuple[dict, str]:
    """旧站人物档案只读基线 → {canonical: record}；返回 (索引, 来源说明)。

    优先阶段 0 冻结备份（--apply 覆盖 site/data 后仍保持稳定基线），
    备份缺失时回退当前 site/data/dossiers.json。
    """
    candidates = [
        esc.BACKUP_ROOT / FALLBACK_TAG / "dossiers.json",   # 阶段 0 冻结备份（首选，稳定）
        esc.SITE_DATA / "dossiers.json",                     # 回退：当前站数据
    ]
    for p in candidates:
        if not p.exists():
            continue
        payload = esc.load_json(p)
        records = payload.get("dossiers") if isinstance(payload, dict) else payload
        index = {d["canonical"]: d for d in records or []
                 if isinstance(d, dict) and isinstance(d.get("canonical"), str)}
        return index, display_path(p)
    return {}, "（未找到旧站 dossiers.json → 主档按纯频次阈值判定；EX-3 派生字段全部空骨架）"


# ---------------------------------------------------------------- 别名归并前置（W0-T2 / §4.2-B7）
def load_alias_merges(path=None) -> tuple[dict[str, str], dict]:
    """读别名归并 TSV → ({form: merge_to}, meta)。

    口径（W0-T2 固化，tests/test_main_dossier.py 为规范）：
      - 制表符分隔 UTF-8（容忍 BOM），表头 `form\tmerge_to\tnote`（note 列可缺省）；
      - **缺文件 = no-op**（返回空映射，行为与现状完全一致；真实数据后续批次补）；
      - **链式显式禁止**：merge_to 若再为任一行的 form（含自指）→ ValueError（不做 TSV 行序解析，
        需改写为直连目标）；两遍校验，与行序无关；
      - 行列数 <2 或 form/merge_to 为空 → ValueError（坏数据宁可 fail-fast）；
      - 同 form 重复出现时后者覆盖前者（幂等）。
    """
    p = Path(path) if path is not None else ALIAS_MERGE_TSV
    if not p.exists():
        return {}, {
            "exists": False, "rows": 0, "path": display_path(p),
            "policy": "缺文件=no-op（B7 机制先行，归并数据后续批次补）",
        }
    rows: list[tuple[str, str]] = []
    header_seen = False
    for i, line in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        cols = [c.strip() for c in line.split("\t")]
        if not header_seen:
            if len(cols) < 2 or cols[0] != "form" or cols[1] != "merge_to":
                raise ValueError(f"别名归并 TSV 表头必须为 form/merge_to/note：{display_path(p)} 第 {i} 行")
            header_seen = True
            continue
        if len(cols) < 2 or not cols[0] or not cols[1]:
            raise ValueError(f"别名归并 TSV 第 {i} 行非法（须 ≥2 列且 form/merge_to 非空）：{display_path(p)}")
        rows.append((cols[0], cols[1]))
    if not header_seen:
        raise ValueError(f"别名归并 TSV 缺表头行：{display_path(p)}")
    forms = {form for form, _ in rows}
    for i, (form, target) in enumerate(rows, start=2):
        if form == target or target in forms:
            raise ValueError(
                f"别名归并 TSV 第 {i} 行 {form}→{target} 属链式/自指归并：B7 显式禁止链式"
                f"（merge_to 不得再为任一行的 form），请改写为直连目标：{display_path(p)}")
    merges = dict(rows)
    return merges, {
        "exists": True, "rows": len(merges), "path": display_path(p),
        "policy": "链式禁止（merge_to 不得再为 form）；频次聚合前生效",
    }


def resolve_alias(form: str, merges: dict | None) -> str:
    """表层字符串 → 归并目标（单步映射；链式在 load_alias_merges 已禁止，故单步即全解）。"""
    if not merges:
        return form
    return merges.get(form, form)


# ---------------------------------------------------------------- registry 类型内 alias 覆盖（D9）
ALIAS_OVERRIDES_KEY = "alias_overrides"   # entities.json 顶层键（D9 用户裁定 2026-11-11）


def load_alias_overrides(payload: dict | None = None,
                         path=None) -> tuple[dict[tuple[str, str], tuple[str, str]], dict]:
    """registry/entities.json 顶层 alias_overrides → ({(type, form): (to_type, to_canonical)}, meta)。

    D9（用户裁定 2026-11-11，registry 治理·只增不删）：跨类型同名治理——B7 TSV 归并按
    canonical 字符串对全类型生效（W0-T2 护栏拦截 一瓢/天都 两例），本表按 (type, form)
    显式映射、**类型内**生效，由 normalize_identity 在 registration 归一之后应用。
    口径：
      - 顶层键缺省 / entries 空 → no-op（返回空映射，行为与旧版完全一致，同 load_alias_merges）；
      - to_id 必须可解析且与 form 声明类型一致，且 form 已追加进目标实体 aliases
        （D9 纪律：aliases 数组追加与 override 成对出现）→ 违反 fail-fast ValueError；
      - to_canonical（如有）必须与目标实体 canonical 一致（防手写漂移）；
      - (type, form) 重复 → fail-fast（显式映射表不允许歧义）。
    """
    p = Path(path) if path is not None else REGISTRY_PATH
    if payload is None:
        payload = esc.load_json(p)
    block = payload.get(ALIAS_OVERRIDES_KEY) if isinstance(payload, dict) else None
    if not block:
        return {}, {
            "exists": False, "rows": 0, "path": display_path(p), "key": ALIAS_OVERRIDES_KEY,
            "policy": "缺键=no-op（D9 机制先行，映射数据随裁定追加）",
        }
    entries = block.get("entries") or []
    by_id = {e.get("id"): e for e in (payload.get("entities") or [])}
    mapping: dict[tuple[str, str], tuple[str, str]] = {}
    for i, e in enumerate(entries, start=1):
        form = str(e.get("form") or "").strip()
        ftype = str(e.get("type") or "").strip()
        tid = str(e.get("to_id") or "").strip()
        if not form or not ftype or not tid:
            raise ValueError(f"alias_overrides[{i}] form/type/to_id 皆必填：{display_path(p)}")
        tgt = by_id.get(tid)
        if tgt is None:
            raise ValueError(
                f"alias_overrides[{i}] to_id={tid} 在 entities 中不存在：{display_path(p)}")
        if (tgt.get("type") or "") != ftype:
            raise ValueError(
                f"alias_overrides[{i}] type={ftype} 与目标实体 {tid} type="
                f"{tgt.get('type')!r} 不一致：{display_path(p)}")
        if form not in (tgt.get("aliases") or []):
            raise ValueError(
                f"alias_overrides[{i}] form={form!r} 未追加进 {tid} aliases"
                f"（D9 只增纪律：aliases 与 override 成对）：{display_path(p)}")
        to_canon = e.get("to_canonical")
        if to_canon is not None and to_canon != tgt.get("canonical"):
            raise ValueError(
                f"alias_overrides[{i}] to_canonical={to_canon!r} 与目标实体 {tid} "
                f"canonical={tgt.get('canonical')!r} 不一致：{display_path(p)}")
        key = (ftype, form)
        if key in mapping:
            raise ValueError(
                f"alias_overrides[{i}] (type, form)={key} 重复：{display_path(p)}")
        mapping[key] = (tgt.get("type") or ftype, tgt.get("canonical") or "")
    return mapping, {
        "exists": True, "rows": len(mapping), "path": display_path(p),
        "key": ALIAS_OVERRIDES_KEY,
        "schema": block.get("schema") or "registry-alias-overrides/v1",
        "origin": block.get("origin") or "",
        "policy": "类型内生效（registration 归一后、TSV 归并前）；目标=registry 实体 (type, canonical)",
    }


def alias_overrides_desc(overrides_meta: dict | None, stats: dict | None = None) -> str:
    """D9 alias_overrides meta → 描述行（characters/entity-index/dossiers field_gaps 消费）。"""
    if not overrides_meta or not overrides_meta.get("exists"):
        return "registry 类型内 alias 覆盖（D9）：缺键=no-op（entities.json 无 alias_overrides）。"
    n = len((stats or {}).get("alias_overrides") or [])
    return (f"registry 类型内 alias 覆盖（D9 用户裁定 2026-11-11）：{overrides_meta.get('rows', 0)} 条 "
            f"(type, form)→registry 实体映射（{overrides_meta.get('origin') or ''}），"
            f"本次入书应用 {n} 条；类型内生效（$/= 等同名其他类型不受影响），"
            "registration 归一后、TSV 归并前应用；只增不删（目标实体 aliases 追加 + 本表显式映射）。")


# ---------------------------------------------------------------- 主档圈定（W0-T2 / 方案 §二）
def scope_book_total(rec: dict, scope) -> int:
    """记录的 scope 口径频次：scope 为 None → 全库 rec["total"]；
    否则只累加 scope 内书目的 count（方案 §1.2：频次按 scope 内 books 计数重算）。"""
    if scope is None:
        return int(rec.get("total") or 0)
    books = rec.get("books") or {}
    return sum(int((books.get(b) or {}).get("count") or 0) for b in scope.get("books", []))


def is_content_bearing(derived) -> bool:
    """有实质内容（方案 §2.2 字面 4 组，sect_affinity/ranks 不算）：
    key_events 非空 ∪ lineage.masters/disciples 非空 ∪ combat.kills/slain_by 非空 ∪ arts 非空。"""
    if not isinstance(derived, dict):
        return False
    ke = derived.get("key_events")
    if isinstance(ke, list) and ke:
        return True
    lineage = derived.get("lineage")
    if isinstance(lineage, dict):
        for k in ("masters", "disciples"):
            v = lineage.get(k)
            if isinstance(v, list) and v:
                return True
    combat = derived.get("combat")
    if isinstance(combat, dict):
        for k in ("kills", "slain_by"):
            v = combat.get(k)
            if isinstance(v, list) and v:
                return True
    arts = derived.get("arts")
    if isinstance(arts, list) and arts:
        return True
    return False


def is_major_dossier(total: int, derived, min_total: int = MIN_TOTAL) -> bool:
    """主档判定（纯函数）：total≥min_total ∪ 有实质内容。"""
    if total >= min_total:
        return True
    return is_content_bearing(derived)


def decide_major(rec: dict, derived, scope=None, min_total: int = MIN_TOTAL) -> bool:
    """主档判定（scope 口径，方案 §2.2 顺序）：先 7 书过滤（scope 内 0 次不参与，
    有实质内容也不救）→ 频次按 scope 内 books 重算 → 圈定。scope=None 时用全库 total。"""
    total = scope_book_total(rec, scope)
    if scope is not None and total <= 0:
        return False
    return is_major_dossier(total, derived, min_total)


def major_rule_meta(scope=None, min_total: int = MIN_TOTAL) -> dict:
    """meta.major_rule（方案 §2.2：规则参数进 meta，随 meta.scope 走，全量口径下 scope=null）。"""
    return {
        "min_total": int(min_total),
        "content_bearing": True,
        "scope": scope.get("profile") if scope else None,
    }


# ---------------------------------------------------------------- 归一化 + 聚合
def normalize_identity(entry: dict, reg_by_id: dict,
                       overrides: dict | None = None) -> tuple[str, str, dict | None]:
    """concordance 条目 → (type, canonical, 归一化变更说明|None)。

    registered / alias_mapped 条目带 registration.id，回查 registry 取权威 (type, canonical)；
    out_of_scope / unregistered 保持 concordance 原值（如 ☆、% 等非身份层类型）。
    D9：overrides（load_alias_overrides 产物，(type, form) → 目标实体 (type, canonical)）在
    registration 归一之后应用——registry 侧跨类型同名治理（类型内生效；E119072 类 canonical
    占位实体之上的显式裁定）；overrides=None/空时行为与旧版完全一致。
    """
    etype = entry.get("type") or ""
    canon = entry.get("canonical") or ""
    reg = entry.get("registration") or {}
    change = None
    if reg.get("status") in IN_SCOPE_STATUS:
        r = reg_by_id.get(reg.get("id"))
        if r:
            rtype = r.get("type") or etype
            rcanon = r.get("canonical") or canon
            if (rtype, rcanon) != (etype, canon):
                change = {
                    "from_type": etype, "from_canonical": canon,
                    "to_type": rtype, "to_canonical": rcanon,
                    "status": reg.get("status"),
                }
            etype, canon = rtype, rcanon
    if overrides:
        ov = overrides.get((etype, canon))
        if ov is not None:
            to_type, to_canon = ov
            if (to_type, to_canon) != (etype, canon):
                change = {
                    "from_type": etype, "from_canonical": canon,
                    "to_type": to_type, "to_canonical": to_canon,
                    "status": "alias_override",   # D9：覆盖 registration 变更说明（以最终态为准）
                }
            etype, canon = to_type, to_canon
    return etype, canon, change


def aggregate_entities(book_payloads: list[dict], reg_by_id: dict,
                       merges: dict | None = None,
                       overrides: dict | None = None) -> tuple[dict, dict]:
    """concordance → {(type, canonical): {type, canonical, total, books{book:{count,chapters,aliases}}}}。

    W0-T2：merges（load_alias_merges 产物）在 registry 归一之后、频次聚合之前生效——
    按 (type, 归并后 canonical) 重新归簇，两簇频次/逐书曲线/别名合并为一人；
    merges 为 None/空时行为与旧版完全一致（no-op）。
    D9：overrides（load_alias_overrides 产物）在 normalize_identity 内 registration 归一
    之后、merges 之前生效——registry 侧类型内 alias 映射（跨类型同名治理）；
    overrides 为 None/空时行为与旧版完全一致（no-op）。
    """
    agg: dict[tuple[str, str], dict] = {}
    stats = {"norm_entries": 0, "alias_merges": [], "type_norms": [], "tsv_merges": [],
             "alias_overrides": []}
    for bp in book_payloads:
        book = bp["book"]
        for e in bp["data"].get("entities", []):
            etype, canon, change = normalize_identity(e, reg_by_id, overrides)
            if change:
                stats["norm_entries"] += 1
                if change.get("status") == "alias_override":      # D9：类型内 alias 覆盖
                    stats["alias_overrides"].append((book, change))
                else:
                    bucket = "type_norms" if change["from_type"] != change["to_type"] else "alias_merges"
                    stats[bucket].append((book, change))
            if merges:
                merged = resolve_alias(canon, merges)
                if merged != canon:
                    stats["tsv_merges"].append((book, {"from": canon, "to": merged, "type": etype}))
                    canon = merged
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


def alias_merge_desc(merges_meta: dict | None, stats: dict | None = None) -> str:
    """别名归并 TSV 状态一句话（meta.field_gaps 用；merges_meta = load_alias_merges 产物）。"""
    meta = merges_meta or {}
    if not meta.get("exists"):
        return (f"别名归并 TSV（方案 §4.2 B7，机制先行）：{meta.get('path', ALIAS_MERGE_TSV)} 缺失 → no-op"
                "（与现状一致；归并数据后续批次补）")
    applied = len(stats.get("tsv_merges", [])) if stats else 0
    return (f"别名归并 TSV（方案 §4.2 B7）：{meta['path']} {meta['rows']} 行"
            f"（{meta['policy']}），在 registry 归一后、频次聚合前生效："
            f"{applied} 条入书条目按映射改写 canonical")


def build_characters_payload(items: list[dict], books: list[str], stats: dict,
                             display_meta: dict | None = None, scope=None,
                             merges_meta: dict | None = None,
                             overrides_meta: dict | None = None) -> dict:
    merged = len(items)
    cross = sum(1 for m in items if m["cross_book"])
    by_type = summarize_types(items)
    new_types = [c for c in sorted({i["type"] for i in items}) if c not in OLD_TYPE_LEGEND]
    merged_targets = sorted({(ch["to_type"], ch["to_canonical"]) for _, ch in stats["alias_merges"]})
    display_meta = display_meta or {}
    shown = [f"{c}→{d}" for c, d in sorted(display_meta.get("map", {}).items())]
    merge_line = alias_merge_desc(merges_meta, stats)
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
        merge_line,
        alias_overrides_desc(overrides_meta, stats),   # D9：registry 类型内 alias 覆盖
    ]
    if scope is not None:
        gaps.append(
            f"scope 口径（{scope['profile']}）：聚合仅含 scope 内书目（{len(books)} 书），"
            "实体 books/total/cross_book 均为 scope 内重算值；scope 外书目条目不参与。")
    payload = {
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
    if scope is not None:
        payload["meta"]["scope"] = scope["profile"]
    return payload


def index_row_values(item: dict, books: list[str], scope=None) -> tuple[int, dict, bool]:
    """entity-index 行的 n/b/x 计算（build 与抽样共用单一来源）。

    scope 口径：n=scope 内频次重算、b=仅 scope 内书目、x=scope 内跨书（方案 §1.2）；
    全量口径：n=total、b=全部出现书目（与旧版逐字段一致）。
    """
    if scope is not None:
        n = scope_book_total(item, scope)
        b = {book: int(item["books"][book]["count"]) for book in books
             if book in item["books"] and esc.in_scope(book, scope)}
    else:
        n = int(item["total"])
        b = {book: int(info["count"]) for book, info in item["books"].items()}
    return n, b, len(b) > 1


def alias_rows_of(item: dict, only_books=None) -> list[dict]:
    """characters 聚合条目的别名表（W2-A1，方案 §4.1 A1）→ [{alias, count}...]。

    口径（tests/test_entity_aliases.py 为规范）：
      - 来源=聚合层直接产：item["books"][book]["aliases"] 即 concordance variants
        （与 EX-3 dossiers.aliases 同源），跨书 Counter 合并、排序 -count 后别名字典序；
      - only_books：scope 口径下仅累加 scope 内书目（与 index_row_values 的 n/b 同源，
        测试 TestAliasScopeConsistency 固化）；
      - **排除 canonical 本名**：canonical/display 已是独立字段（搜索另路匹配，
        EX-4 build_search_index 同口径过滤 a != canonical），aliases 只收"其他叫法"；
      - 不设 top-N 截断（轻索引用于别名搜索全量保留；dossiers 的 [:8] 为展示口径）；
      - 无别名 → []（字段在场、空数组）。
    """
    canonical = item.get("canonical")
    aliases: dict[str, int] = {}
    for book, info in (item.get("books") or {}).items():
        if only_books is not None and book not in only_books:
            continue
        for alias, n in (info.get("aliases") or {}).items():
            if alias == canonical:
                continue
            aliases[alias] = aliases.get(alias, 0) + int(n or 0)
    return [{"alias": a, "count": n}
            for a, n in sorted(aliases.items(), key=lambda kv: (-kv[1], kv[0]))]


def build_entity_index_payload(items: list[dict], books: list[str],
                               display_meta: dict | None = None, scope=None,
                               content_index: dict | None = None,
                               merges_meta: dict | None = None,
                               overrides_meta: dict | None = None) -> dict:
    """轻索引 payload：旧契约字段 t/c/display/n/b/x + W0-T2 新增 page（只增字段）。

    page 标志（方案 §二）：@ 主档 true / 存目 false（total≥30 ∪ 有实质内容，见 major_rule_meta）；
    ☆/◆ 恒 true（武功/门派有独立页）。scope 口径下仅收 scope 内出现实体。
    """
    display_meta = display_meta or {}
    content_index = content_index or {}
    # W2-A1：scope 口径下 aliases 与 n/b 同源——仅累加 scope 内书目的 variants
    scope_books = None if scope is None else {b for b in books if esc.in_scope(b, scope)}
    rows = []
    for item in items:
        t = item["type"]
        if t not in INDEX_TYPES:
            continue
        n, b, x = index_row_values(item, books, scope)
        if scope is not None and n <= 0:
            continue          # 方案 §1.2：轻索引只收 scope 内出现实体
        page = True if t != "@" else is_major_dossier(n, content_index.get(item["canonical"]))
        rows.append({
            "t": t,
            "c": item["canonical"],
            "display": item.get("display") or item["canonical"],   # task-24：只增字段
            "n": n,
            "b": b,
            "x": x,
            "page": page,                                          # W0-T2：只增字段
            "aliases": alias_rows_of(item, scope_books),           # W2-A1：只增字段
        })
    rows.sort(key=lambda r: (-r["n"], r["t"], r["c"]))
    by_type = {t: sum(1 for r in rows if r["t"] == t) for t in INDEX_TYPES}
    gaps = [
        f"展示层字段 display（task-24 新增，只增不改）：取 characters.json 同批 display，"
        f"覆盖 {display_meta.get('entries', 0)} 条（默认 canonical==display）；t/c 身份口径不变。",
        f"page 标志（W0-T2 新增，只增字段）：@ 按 meta.major_rule 规则判定"
        f"（total≥{MIN_TOTAL} ∪ 有实质内容：key_events/lineage.masters|disciples/combat.kills|slain_by/"
        f"arts 非空）——主档 true、存目 false；☆/◆ 恒 true（武功/门派有独立页）。"
        "有实质内容判定取旧站 dossiers 同 canonical 派生字段（阶段 0 冻结备份优先，只读）。"
        "全量口径（scope=null）下 dossiers 不裁剪（向后兼容，方案 R6），page 为规则判定值；"
        "scope 口径下与 dossiers.json 主档集合一致。",
        alias_merge_desc(merges_meta),
        alias_overrides_desc(overrides_meta),          # D9：registry 类型内 alias 覆盖
        f"轻索引类型口径：仅 {'/'.join(INDEX_TYPES)}（对齐旧站 build_entity_index：@人物/☆武功/◆组织）；"
        "新管线 ◎&~#{$^ 等类型不进入轻索引（旧契约轻索引只有 3 类）。",
        f"记录数：旧 1034（@436/☆451/◆147，3 书）→ 新 {len(rows)}"
        f"（@/☆/◆={by_type['@']}/{by_type['☆']}/{by_type['◆']}）。"
        "☆/◆ 条目对应的 arts.json/sects.json 页面覆盖率取决于 EX-6 导出；"
        "旧站本身亦仅 103/451（arts=116）、15/147（sects=18）可跳转，桥接期同类链接缺口不属本表字段问题。",
        "n=总频次、b=逐书频次、x=跨书（len(b)>1）；排序 -n，"
        "与旧站 entity-index 字段语义逐字段一致（t/c/n/b/x）。",
        "aliases 别名频次（W2-A1 新增，只增字段，方案 §4.1 A1）：由本脚本聚合层 variants 跨书合并产出"
        "（与 EX-3 dossiers.aliases 同源同排序 -count,alias），排除 canonical 本名"
        "（canonical/display 独立匹配；EX-4 搜索索引同口径），不设 top-N 截断；无别名者为空数组 []；"
        "@/☆/◆ 三类均带——供人物/武功/门派总览搜索命中别名（白发魔女/玉罗刹/晦明禅师可搜）。",
    ]
    if scope is not None:
        gaps.append(
            f"scope 口径（{scope['profile']}）：n/b/x 为 scope 内重算值（非全库 total），"
            "scope 外实体不进轻索引；page 按 scope 内频次圈定。")
    meta = {
        "generated": esc.now_iso(),
        "schema": SCHEMA_ENTITY_INDEX,
        "note": "轻索引：t=类型 c=规范名 n=总频次 b=逐书频次 x=跨书 page=有独立页（W0-T2）"
                " aliases=别名频次表（W2-A1）",
        "source": SOURCE,
        "source_detail": "派生自本脚本 characters.json 同批聚合结果（filter t∈@/☆/◆）",
        "display_layer": display_meta,
        "totals": {
            "entities": len(rows),
            "by_type": by_type,
            "page_true": sum(1 for r in rows if r["page"] is True),
            "page_false": sum(1 for r in rows if r["page"] is False),
        },
        "major_rule": major_rule_meta(scope),   # W0-T2：规则参数进 meta，不硬编码
        "field_gaps": gaps,
    }
    if scope is not None:
        meta["scope"] = scope["profile"]
    return {"meta": meta, "entities": rows}


# ---------------------------------------------------------------- 抽样回溯（验收 §七.3）
SAMPLE_TYPES = ("@", "☆", "◆", "=", "•", "%", "^", "#", "$", "{")


def trace_entity(key: tuple[str, str], book_payloads: list[dict], reg_by_id: dict,
                 merges: dict | None = None,
                 overrides: dict | None = None) -> tuple[dict, dict | None]:
    """独立回溯：重新遍历 concordance 原始条目，按归一化键（registry 归一 + D9 override + TSV 归并）
    重算逐书频次与首见锚点。"""
    etype, canon = key
    per_book: Counter = Counter()
    anchor = None
    for bp in book_payloads:
        for e in bp["data"].get("entities", []):
            t, c, _ = normalize_identity(e, reg_by_id, overrides)
            if merges:
                c = resolve_alias(c, merges)
            if (t, c) != key:
                continue
            per_book[bp["book"]] += int(e.get("total") or 0)
            first = e.get("first") or {}
            rank = int(e.get("first_rank") or 10 ** 9)
            if first.get("anchor") and (anchor is None or rank < anchor[0]):
                anchor = (rank, bp["book"], first.get("anchor"), first.get("loc"))
    return dict(per_book), anchor


def character_samples(items: list[dict], book_payloads: list[dict], reg_by_id: dict,
                      merges: dict | None = None,
                      overrides: dict | None = None) -> tuple[list[str], list[dict]]:
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
        per_book, anchor = trace_entity(key, book_payloads, reg_by_id, merges, overrides)
        if sum(per_book.values()) != item["total"] or dict(per_book) != {
                b: info["count"] for b, info in item["books"].items()}:
            failures.append(f"{item['canonical']} 频次回溯不一致")
        loc = f"{anchor[1]}·{anchor[3]}（{anchor[2]}）" if anchor else "—"
        lines.append(
            f"| {item['canonical']} | {item['type']} | {item['total']} | "
            + "、".join(f"{b}:{n}" for b, n in per_book.items()) + f" | {loc} |"
        )
    return lines, failures


def index_samples(rows: list[dict], items: list[dict], books: list[str],
                  scope=None) -> list[str]:
    """轻索引抽样 10 条：n/b 与 characters 同源记录逐字段比对（scope 口径同源重算）。"""
    by_key = {(i["type"], i["canonical"]): i for i in items}
    lines, failures = [], []
    for row in rows[:10]:
        item = by_key.get((row["t"], row["c"]))
        if not item:
            failures.append(f"索引条目 {row['c']} 在 characters 中缺失")
            continue
        n, b, _x = index_row_values(item, books, scope)
        if row["n"] != n or row["b"] != b:
            failures.append(f"索引条目 {row['c']} 频次不一致")
        lines.append(f"| {row['c']} | {row['t']} | {row['n']} | "
                     + "、".join(f"{b}:{n}" for b, n in row["b"].items()) + f" | {row['x']} |")
    return lines, failures


# ---------------------------------------------------------------- 展示层抽样（task-24）
def display_samples(items: list[dict], index_rows: list[dict],
                    display_map: dict[str, str], scope=None) -> tuple[list[str], list[str]]:
    """5 个覆盖条目（4 帝王 + 飞红巾）在 characters / entity-index 的 display 校验。

    scope 口径下实体可能整条不在 scope（如仅站外书出现）→ 记跳过行而非失败；
    全量口径维持原严格校验。
    """
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
        if item is None or row is None:
            if scope is not None:
                lines.append(f"| {canon} | {expected} | （scope 外，跳过） | （scope 外，跳过） | — |")
                continue
            failures.append(f"characters 缺 @{canon}" if item is None else f"entity-index 缺 @{canon}")
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
    # W0-T2：--scope <profile> 裁剪口径（W0-T1 基础设施；不带 --scope = 全量口径，向后兼容）
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    book_payloads = load_book_payloads()
    if scope is not None:
        book_payloads = [bp for bp in book_payloads if esc.in_scope(bp["book"], scope)]
        found = {bp["book"] for bp in book_payloads}
        missing = [b for b in scope["books"] if b not in found]
        if missing:
            raise SystemExit(f"[EX-2] scope {scope['profile']} 缺少 concordance 书目：{'、'.join(missing)}")
    books = [bp["book"] for bp in book_payloads]
    reg_by_id = load_registry()
    display_map, display_meta = load_display_map()
    display_meta = dict(display_meta, map=display_map)
    merges, merges_meta = load_alias_merges()        # W0-T2：缺文件 = no-op
    overrides, overrides_meta = load_alias_overrides()   # D9：registry 类型内 alias 覆盖（缺键=no-op）
    agg, stats = aggregate_entities(book_payloads, reg_by_id, merges=merges, overrides=overrides)
    stats["registry_ids"] = len(reg_by_id)
    fallback_index, _fallback_src = load_fallback_dossiers()   # W0-T2：主档内容判定源（只读）
    items = build_characters(agg, books, display_map)
    chars = build_characters_payload(items, books, stats, display_meta,
                                     scope=scope, merges_meta=merges_meta,
                                     overrides_meta=overrides_meta)
    index_payload = build_entity_index_payload(items, books, display_meta, scope=scope,
                                               content_index=fallback_index,
                                               merges_meta=merges_meta,
                                               overrides_meta=overrides_meta)

    # 抽样回溯（验收：10 条可回溯到 concordance/registry）+ 展示层抽样（task-24）
    sample_lines, sample_fail = character_samples(items, book_payloads, reg_by_id, merges,
                                                  overrides)
    index_lines, index_fail = index_samples(index_payload["entities"], items, books, scope)
    display_lines, display_fail = display_samples(items, index_payload["entities"],
                                                  display_map, scope)
    if sample_fail or index_fail or display_fail:
        raise SystemExit("[EX-2] 抽样/展示层校验失败：" + "；".join(sample_fail + index_fail + display_fail))

    notes = "\n".join([
        "### 记录数对比旧站",
        f"- characters.json：旧 2390（3 书）→ 新 {len(items)}"
        f"（{len(books)} 书：{'、'.join(books)}）；"
        f"cross_book：旧 405 → 新 {chars['meta']['totals']['cross_book']}。",
        f"- entity-index.json：旧 1034 → 新 {len(index_payload['entities'])}；"
        f"by_type {index_payload['meta']['totals']['by_type']}；"
        f"page true/false = {index_payload['meta']['totals']['page_true']}/"
        f"{index_payload['meta']['totals']['page_false']}。",
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
        "- W0-T2 例外：entity-index 的 page 判定用旧站 dossiers 同 canonical 派生字段做"
        "「有实质内容」检查（只读，不影响身份字段）。",
        "",
        "### W0-T2 主档圈定（方案 §二）",
        f"- 规则：total≥{MIN_TOTAL} ∪ 有实质内容；meta.major_rule={index_payload['meta']['major_rule']}。",
        f"- {alias_merge_desc(merges_meta, stats)}。",
        f"- entity-index page：主档（true）{index_payload['meta']['totals']['page_true']} 条 / "
        f"存目（false）{index_payload['meta']['totals']['page_false']} 条。",
        "",
        "### W2-A1 别名并入（方案 §4.1）",
        f"- entity-index 每行新增 aliases=[{{alias,count}}…]（聚合层 variants 跨书合并、"
        "排除 canonical 本名、不截断）："
        f"共 {sum(len(r['aliases']) for r in index_payload['entities'])} 条别名记录，"
        f"覆盖 {sum(1 for r in index_payload['entities'] if r['aliases'])} / "
        f"{len(index_payload['entities'])} 条实体；无别名者空数组。"
        "消费方：site 人物/武功/门派总览搜索（EntitySearch 轻量模式）。",
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
        "- 身份归并只做 registry 显式 alias（29 条入书 alias_mapped）+ W0-T2 别名归并 TSV（现缺文件 no-op）；"
        "语料 unregistered 同形变体（如 晦明 vs 晦明禅师）保留为独立记录，属上游标注口径问题。",
    ])

    diff1 = esc.finish("characters.json", chars, exporter=EXPORTER, notes=notes)
    diff2 = esc.finish("entity-index.json", index_payload, exporter=EXPORTER, notes=notes)
    print(f"[EX-2] characters={len(items)} entity-index={len(index_payload['entities'])} "
          f"page_true={index_payload['meta']['totals']['page_true']} "
          f"page_false={index_payload['meta']['totals']['page_false']} "
          f"merges={merges_meta.get('rows', 0)} "
          f"overrides={overrides_meta.get('rows', 0)} "
          f"display_overrides={len(display_map)} "
          f"alias_rows={sum(len(r['aliases']) for r in index_payload['entities'])} "
          f"hard_gaps={diff1['hard_gap_count']}/{diff2['hard_gap_count']}")
    return 0 if diff1["hard_gap_count"] == 0 and diff2["hard_gap_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
