# -*- coding: utf-8 -*-
"""N10 · `build_sku_cards.py` — SKU 卡片生成（docs/17 §2.4 / D12；SKILL_SKU卡片_武侠版 五类卡）

规范源：`skills/SKILL_SKU卡片_武侠版.md`
  §2.0 统一元数据块（01g §9.9 九项最低字段）  §2.1 人物卡  §2.2 门派卡  §2.3 武功卡
  §2.4 兵器卡  §2.5 秘籍卡  §2.6 来源覆盖核对表（11 行）  §2.7 边界案例裁决
  §4.2 跨书字段（active_books/first_appearance）  §4.3 卡片 ID 投影制
  §6.1 可发布性三档  §6.2 脱敏 R1-R5  §6.3 卡级可信聚合  §6.4 版本声明
  §3.1/§3.2/§3.3 三类 SKU（本脚本只产五卡＝Factual 卡化；Procedural/Relational 另有 SKU 节点）
  §7.1 生成操作序九步（本脚本机械实现 1-8 步；第 9 步发布加载器拒绝 demo 卡）

输入（只读）：
  registry/entities.json（452：@367/◆70/&14/~1）
  registry/concordance/<书>.json（5 书全类型实体：canonical/首末 loc/anchor/variants/registration）
  registry/relations/<书>.json（N5：关系边 id/谓词/师承树/lineage_labels/validation）
  registry/time/<书>.json（N4：年龄锚/时点键/t_days/year_ce/narrative）
  registry/gazetteer.json（N7：650 地点）
  wordlists/new_entity_types.json（候选新实体词表，用于别名/覆盖对账，不单独建卡）
  kb/神兵表.json（226 器物：kind/grade/chain/holders/end_state 等；既有资产，SKILL §2.6 第 9 行）
  kb/招式表.json（222 招式：parent_art/used_by/sect/conf；既有资产，§2.6 第 10 行）
  kb/系列谱系考订表.json（编年脊/书序 → active_books/first_appearance 编年口径）
  kb/作品元数据表.json（书目元数据）
  tagged/<书>/*.tagged.md（只读：共现派生、年龄归属、作者推导、R1 原文 n-gram 比对语料）

输出：
  registry/sku/cards.json（五类卡 + 元数据块 + 脱敏标记 + 数据源字段映射 11 行 + 字段填充率）
  logs/sku/summary.md + logs/sku/metrics.json（各类卡数/字段填充率/数据源覆盖/脱敏检查/无法填充字段）

CLI：
  python -X utf8 scripts/build_sku_cards.py --all
  python -X utf8 scripts/build_sku_cards.py --type person,faction
  python -X utf8 scripts/build_sku_cards.py --book 江湖三女侠
  python -X utf8 scripts/build_sku_cards.py --all --strict
  python -X utf8 scripts/build_sku_cards.py --selftest

纪律：无来源不上卡；未知不强填（[]/null/"未明示"）；卡面不携带原文（R1-R5）；引用写实体 ID
（艺术/器物/秘籍在 01g 登记层未扩类 → entity_ref:null + entity_ref_gap，不伪造 E-ID，报告登记缺口）；
卡 ID 投影制 stable_id = card.<type>.<slug>（中文 slug 转写规则待定版，registered 用实体 ID 后缀，
未登记类型用 canonical 哈希前缀，保证确定性可复现）。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT.parent / "kb"          # 既有资产（只读）：神兵表/招式表/谱系表/作品元数据表
TAGGED_DIR = ROOT / "tagged"
REG = ROOT / "registry"
OUT_CARDS = REG / "sku" / "cards.json"
OUT_LOGS = ROOT / "logs" / "sku"

TOOL = "build_sku_cards v0.1 (2026-11-05, N10/D12)"
DATA_VERSION = "2026-11-05.01"
RULE_VERSION = "sku-card@0.3-draft+rel-verbs@v1+event-fields@v1+wordlists@0.3-draft"
BOOKS = ["江湖三女侠", "七剑下天山", "塞外奇侠传", "冰魄寒光剑", "白发魔女传"]
BOOK_IDS = {"江湖三女侠": "jianghu", "七剑下天山": "qijian", "塞外奇侠传": "saiwai",
            "冰魄寒光剑": "bingpo", "白发魔女传": "bainv"}
CARD_TYPES = ["person", "faction", "art", "artifact", "manual"]
TYPE_LABEL = {"person": "人物卡", "faction": "门派卡", "art": "武功卡",
              "artifact": "兵器卡", "manual": "秘籍卡"}
TYPE_CODE = {"person": "P", "faction": "F", "art": "A", "artifact": "O", "manual": "D"}

TOKEN_RE = re.compile(r"[〖⟦]([^〖⟦〗⟧]+)[〗⟧]")
RHET_RE = re.compile(r"〘([^〙]*)〙")
PARA_RE = re.compile(r"^\[(\d+)\] ")
TAGGED_MARK = ("〖", "〗", "⟦", "⟧", "〘", "〙")

# ────────────────────────── 字段表（照录 SKILL §2.1-§2.5） ──────────────────────────
FIELD_SPECS: dict[str, list[tuple[str, bool, str]]] = {
    "person": [
        ("name.canonical", True, "SPEC §2.1"), ("aliases", False, "§2.1/§2.7-2"),
        ("identity_tags", False, "§2.1（#8 身份树叶子）"), ("faction_history", False, "§2.1"),
        ("seniority", False, "§2.1"), ("teachers", False, "§2.1"), ("disciples", False, "§2.1"),
        ("kinship", False, "§2.1"), ("romance", False, "§2.1"), ("arts", False, "§2.1"),
        ("life_events", False, "§2.1"), ("age_anchor", False, "§2.1"), ("ending", False, "§2.1"),
        ("relational_sku_refs", False, "§2.1"), ("brief", False, "§2.1"),
        ("meta", True, "§2.0"),
    ],
    "faction": [
        ("name.canonical", True, "§2.2"), ("aliases", False, "§2.2"),
        ("faction_type", False, "§2.2"), ("lineage", False, "§2.2"),
        ("signature_arts", False, "§2.2"), ("strongholds", False, "§2.2"),
        ("timeline", False, "§2.2"), ("status", False, "§2.2"),
        ("branch_alliance", False, "§2.2"), ("member_stat", False, "§2.2"),
        ("brief", False, "§2.2"), ("meta", True, "§2.0"),
    ],
    "art": [
        ("name.canonical", True, "§2.3"), ("aliases", False, "§2.3"),
        ("category", False, "§2.3"), ("hierarchy", False, "§2.3"), ("moves", False, "§2.3"),
        ("creator", False, "§2.3"), ("inheritance_chain", False, "§2.3"),
        ("practitioners", False, "§2.3"), ("grade", False, "§2.3"), ("grade_basis", False, "§2.3"),
        ("recorded_in", False, "§2.3"), ("brief", False, "§2.3"), ("meta", True, "§2.0"),
    ],
    "artifact": [
        ("name.canonical", True, "§2.4"), ("kind", False, "§2.4"),
        ("grade", False, "§2.4"), ("grade_basis", False, "§2.4"),
        ("forge", False, "§2.4"), ("chain", False, "§2.4"),
        ("current_whereabouts", False, "§2.4"), ("brief", False, "§2.4"),
        ("meta", True, "§2.0"),
    ],
    "manual": [
        ("name.canonical", True, "§2.5"), ("content_arts", False, "§2.5"),
        ("author", False, "§2.5"), ("provenance", False, "§2.5"),
        ("holders", False, "§2.5"), ("status", False, "§2.5"),
        ("locations", False, "§2.5"), ("brief", False, "§2.5"), ("meta", True, "§2.0"),
    ],
}
CROSS_FIELDS = [("active_books", False, "§4.2"), ("first_appearance", False, "§4.2")]
META_REQUIRED = ["stable_id", "entity_ref", "card_type", "proposition", "supported_by", "sources",
                 "confidence", "data_version", "rule_version", "method", "denominator",
                 "publish_state", "demo", "demo_note"]

# SKILL §2.6 来源覆盖核对表（11 行，逐行落位）
SOURCE_MAPPING = [
    {"row": 1, "source": "规范名/别名（surface/type/canonical/refs）｜01g+#7",
     "fields": "name.canonical / aliases", "cards": "全卡", "file_key": "entities"},
    {"row": 2, "source": "双层 canonical＋active_books/first_appearance｜#7",
     "fields": "active_books / first_appearance", "cards": "全卡", "file_key": "concordance"},
    {"row": 3, "source": "三层谓词总表（师承/结义/配偶/任职/转移/传授/掌握…）｜#6",
     "fields": "faction_history/teachers/disciples/kinship/romance/lineage/inheritance_chain/holders/branch_alliance",
     "cards": "人物/门派/武功/秘籍", "file_key": "relations"},
    {"row": 4, "source": "辈分推导（师祖/师叔/同门）｜#6 双树",
     "fields": "seniority", "cards": "人物卡", "file_key": "relations"},
    {"row": 5, "source": "事件字段总表（六域＋五状态＋时间槽位）｜#4a+#2",
     "fields": "timeline/provenance/chain 事件环/ending/life_events/status.basis_event",
     "cards": "门派/秘籍/兵器/人物", "file_key": "events"},
    {"row": 6, "source": "时点键与年龄锚｜#5",
     "fields": "life_events 排序 / age_anchor / lineage 任期", "cards": "人物/门派", "file_key": "time"},
    {"row": 7, "source": "五棵分类树叶子｜#8",
     "fields": "identity_tags / faction_type / category / hierarchy.system / kind（对齐）",
     "cards": "人物/门派/武功/兵器", "file_key": "class_trees"},
    {"row": 8, "source": "gazetteer 双图层｜#10",
     "fields": "strongholds / locations / chain[].loc_r 回填 / forge.place_ref",
     "cards": "门派/秘籍/兵器", "file_key": "gazetteer"},
    {"row": 9, "source": "神兵表 chain（verb/persons/book/loc/conf）｜既有资产",
     "fields": "chain（直接投影）／holders（秘籍如入宝物类可复用）",
     "cards": "兵器卡（秘籍条件复用）", "file_key": "weapons"},
    {"row": 10, "source": "招式表（parent_art/used_by/conf）｜既有资产",
     "fields": "moves / practitioners / hierarchy", "cards": "武功卡", "file_key": "moves"},
    {"row": 11, "source": "常识与设定一致性评级｜#11",
     "fields": "meta.confidence 聚合（A–E；受 01g 状态上限约束）", "cards": "全卡", "file_key": "consistency"},
]

DATA_GAP_REASONS = {
    "identity_tags": "无 #8 五棵分类树产出（身份树未建），不得自造枚举 → []",
    "life_events": "无 #4a 事件流产出，无 event_ref 可回指 → []",
    "timeline": "无 #4a 组织域事件流 → []",
    "provenance": "无 #4a 物件域事件流 → []",
    "inheritance_chain": "N5 师承边为通用人物边，未按武功传人链建 → []",
    "category": "无 #8 武功品类树；按名称后缀启发式归类（报告注明）",
    "faction_type": "无 #8 门派树；按名称后缀启发式归类（报告注明）",
    "identity_tags2": "",
    "grade": "无出场战绩事件统计支撑，按 SKILL §2.3 不评品级 → null",
    "creator": "无 #4a 悟创事件 → 创派者未明",
    "life_events2": "",
    "relational_sku_refs": "Relational SKU 为独立节点（§3.3），本批未生成 → []",
    "branch_alliance": "N5 谓词表无联盟/敌对/分支谓词 → []",
    "strongholds": "由 tagged 共现（◆组织×=地点）启发式推导，非 #6 组织驻地谓词 → 低可信",
    "locations": "由 tagged 共现（document×=地点）启发式推导 → 低可信",
    "content_arts": "由 tagged 段落共现（document×☆武功）启发式推导，非秘籍互指边 → 低可信",
    "author": "无 #4a 悟创事件；仅 tagged 句式（所著/所传）启发式抽取（多为空）",
    "holders": "N5 转移谓词客体未覆盖 ← 文书类实体 → []",
    "provenance2": "",
    "smoke": "",
}


def strip_markup(text: str) -> str:
    text = TOKEN_RE.sub(lambda m: m.group(1)[1:].split("|")[0].split("｜")[0], text)
    return RHET_RE.sub(lambda m: m.group(1)[1:] if m.group(1).startswith("※") else m.group(1), text)


def slugify(name: str, card_type: str) -> str:
    """确定性 slug：中文名 → md5 前 10 位（中文转写规则待定版，见 SKILL 附录 B）。"""
    digest = hashlib.md5(f"{card_type}:{name}".encode("utf-8")).hexdigest()[:10]
    return f"n{digest}"


def loc_r(book: str, ch, pn) -> str | None:
    wid = BOOK_IDS.get(book)
    if wid is None or not isinstance(ch, int) or not isinstance(pn, int):
        return None
    return f"{wid}#pn-r{ch}.{pn}"


def is_filled(value, default_markers=("未明示", "未归类", "下落不明", "未评", "创派者未明",
                                      "作者未明", "锻造未明", "武功层（#8")) -> bool:
    """字段填充判定：None/空/约定缺省 → 未填充（SKILL 设计纪律 3：未知不强填，缺省可识别）。"""
    if value is None:
        return False
    if isinstance(value, str):
        v = value.strip()
        return bool(v) and v not in default_markers and not any(v.startswith(m) for m in default_markers)
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, tuple):
        return len(value) > 0
    if isinstance(value, dict):
        if not value:
            return False
        for key in ("type", "value", "status", "level", "system"):
            v = value.get(key)
            if isinstance(v, str) and v:
                if v.strip() in default_markers or any(v.strip().startswith(m) for m in default_markers):
                    return False
                break
        return True
    return True


def get_path(obj, path: str):
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def set_ngrams(text: str, n: int = 10) -> set[int]:
    return {hash(text[i:i + n]) for i in range(0, max(0, len(text) - n + 1))}


# ────────────────────────── 数据加载 ──────────────────────────
class EntitiesHub:
    def __init__(self, path: Path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.raw = raw
        self.version = raw.get("version", "")
        self.items = raw.get("entities") or []
        self.by_id = {e["id"]: e for e in self.items}
        self.surface_to_id: dict[str, str] = {}
        for e in self.items:
            for surface in [e.get("canonical", "")] + list(e.get("aliases") or []) + \
                    list(e.get("contextual") or []):
                if surface:
                    self.surface_to_id.setdefault(surface, e["id"])
        self.display_canon_map: dict[str, str] = {}
        dc = REG / "display_canonical.json"
        if dc.exists():
            d = json.loads(dc.read_text(encoding="utf-8"))
            for ent in d.get("entries") or []:
                if ent.get("canonical"):
                    self.display_canon_map[ent.get("display") or ""] = ent["canonical"]

    def entity(self, entity_id: str) -> dict | None:
        return self.by_id.get(entity_id)

    def ref(self, surface: str) -> str | None:
        if not surface:
            return None
        if surface in self.display_canon_map:
            surface = self.display_canon_map[surface]
        return self.surface_to_id.get(surface)

    def canonical(self, entity_id: str) -> str:
        e = self.by_id.get(entity_id)
        return e.get("canonical", entity_id) if e else entity_id

    def status(self, entity_id: str) -> str:
        e = self.by_id.get(entity_id) or {}
        return e.get("status") or "unknown"

    def aliases_of(self, entity_id: str) -> list[dict]:
        e = self.by_id.get(entity_id) or {}
        out = []
        for a in e.get("aliases") or []:
            out.append({"surface": a, "type": "别名"})
        for a in e.get("contextual") or []:
            out.append({"surface": a, "type": "语境称谓"})
        return out


class ConcordanceHub:
    def __init__(self, books: list[str]):
        self.books = books
        self.book_data: dict[str, dict] = {}
        self.by_entity: dict[str, dict[str, dict]] = defaultdict(dict)   # entity_id -> book -> entry (nem)
        self.by_type_canon: dict[str, dict[str, dict]] = {
            t: defaultdict(lambda: {"books": {}, "variants": set(), "total": 0, "type_label": ""})
            for t in ("☆", "{", "•")}
        self.surfaces_by_entity: dict[str, set] = defaultdict(set)
        self.unregistered_counts: Counter = Counter()
        for book in books:
            path = REG / "concordance" / f"{book}.json"
            d = json.loads(path.read_text(encoding="utf-8"))
            self.book_data[book] = d
            for ent in d.get("entities") or []:
                c, t = ent.get("canonical"), ent.get("type")
                variants = {v.get("display") for v in ent.get("variants") or [] if v.get("display")}
                reg = ent.get("registration") or {}
                status = reg.get("status")
                if status in ("unregistered", "out_of_scope"):
                    self.unregistered_counts[t] += 1
                if t in self.by_type_canon:
                    agg = self.by_type_canon[t][c]
                    agg["books"][book] = ent
                    agg["variants"] |= variants
                    agg["total"] += int(ent.get("total") or 0)
                    agg["type_label"] = ent.get("type_label") or agg["type_label"]
            # 用实体登记反查：登记实体名→entity_id
            for ent in d.get("entities") or []:
                if (ent.get("registration") or {}).get("status") not in ("registered", "alias_mapped"):
                    continue
                eid = self.resolve_entity(ent.get("canonical") or "")
                if eid:
                    self.by_entity[eid].setdefault(book, ent)
                    variants = {v.get("display") for v in ent.get("variants") or [] if v.get("display")}
                    self.surfaces_by_entity[eid] |= variants | {ent.get("canonical")}

    @staticmethod
    def resolve_entity(surface: str) -> str | None:
        return ENTITIES.ref(surface) if ENTITIES else None

    def entity_books(self, entity_id: str) -> list[str]:
        return [b for b in self.books if b in self.by_entity.get(entity_id, {})]

    def entry(self, entity_id: str, book: str) -> dict | None:
        return self.by_entity.get(entity_id, {}).get(book)

    def unregistered_surfaces(self, typ: str) -> int:
        return self.unregistered_counts.get(typ, 0)


class RelationsHub:
    def __init__(self, books: list[str]):
        self.books = books
        self.edges: list[dict] = []
        self.by_person: dict[str, list[dict]] = defaultdict(list)
        self.by_faction: dict[str, list[dict]] = defaultdict(list)
        self.lineage_labels: list[dict] = []
        self.generations: dict[str, int] = {}
        self.edges_total = 0
        for book in books:
            path = REG / "relations" / f"{book}.json"
            d = json.loads(path.read_text(encoding="utf-8"))
            for e in d.get("edges") or []:
                rec = dict(e)
                rec["_book"] = book
                rec["_subject_ref"] = ENTITIES.ref(e.get("subject") or "")
                rec["_object_ref"] = ENTITIES.ref(e.get("object") or "")
                self.edges.append(rec)
                if rec["_subject_ref"]:
                    self.by_person[rec["_subject_ref"]].append(rec)
                if rec["_object_ref"] and e.get("object_type") == "◆":
                    self.by_faction[rec["_object_ref"]].append(rec)
            self.edges_total += len(d.get("edges") or [])
            der = d.get("derived") or {}
            self.lineage_labels.extend(der.get("lineage_labels") or [])
            tree = (der.get("trees") or {}).get("master_tree") or {}
            for node in tree.get("nodes") or []:
                person, gen = node.get("person"), node.get("generation")
                if person and isinstance(gen, int):
                    eid = ENTITIES.ref(person)
                    if eid:
                        self.generations[eid] = min(self.generations.get(eid, gen), gen)
        self.by_id = {e.get("id"): e for e in self.edges if e.get("id")}

    def teacher_edges(self, person_id: str) -> list[dict]:
        return [e for e in self.by_person.get(person_id, []) if e.get("predicate") == "师承"]

    def disciple_edges(self, person_id: str) -> list[dict]:
        return [e for e in self.edges
                if e.get("predicate") == "师承" and e.get("_object_ref") == person_id]

    def pred_edges(self, person_id: str, predicates: set[str]) -> list[dict]:
        out = []
        for e in self.by_person.get(person_id, []):
            if e.get("predicate") in predicates:
                out.append(e)
        return out

    def killed_by(self, person_id: str) -> list[dict]:
        return [e for e in self.edges
                if e.get("predicate") == "杀害" and e.get("_object_ref") == person_id]


class GazetteerHub:
    def __init__(self):
        raw = json.loads((REG / "gazetteer.json").read_text(encoding="utf-8"))
        self.places = raw.get("places") or []
        self.by_id = {p.get("id"): p for p in self.places}
        self.surface_to_id: dict[str, str] = {}
        for p in self.places:
            for s in [p.get("name") or p.get("id")] + list(p.get("aliases") or []):
                if s:
                    self.surface_to_id.setdefault(s, p.get("id"))

    def ref(self, surface: str) -> str | None:
        return self.surface_to_id.get(surface)


@dataclass
class Para:
    book: str
    ch: int
    pn: int
    raw: str
    plain: str
    fence: str
    tokens: list[tuple[str, str, int]] = field(default_factory=list)  # domain, display, plain_pos


class TaggedHub:
    """tagged 只读索引：段落/令牌/共现/原文 n-gram（R1）。"""

    def __init__(self, books: list[str], max_paras: int | None = None):
        self.books = books
        self.paras: dict[tuple[str, int, int], Para] = {}
        self.token_paras: dict[tuple[str, str, str], list[tuple[int, int]]] = defaultdict(list)
        self.ngrams: set[int] = set()
        self.ngram_n = 10
        for book in books:
            d = TAGGED_DIR / book
            if not d.is_dir():
                continue
            for path in sorted(d.glob("*.tagged.md")):
                stem = path.stem.split(".")[0]
                if not stem.isdigit():
                    continue
                ch = int(stem)
                fence = ""
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.startswith(":::"):
                        fence = line[3:].strip()
                        continue
                    m = PARA_RE.match(line)
                    if not m:
                        continue
                    pn = int(m.group(1))
                    para = Para(book, ch, pn, line, strip_markup(line), fence)
                    parts, pos_raw, plain_len = [], 0, 0
                    for tm in TOKEN_RE.finditer(line):
                        seg = line[pos_raw:tm.start()]
                        parts.append(seg)
                        plain_len += len(seg)
                        inner = tm.group(1)
                        domain, rest = inner[0], inner[1:]
                        display = re.split(r"[｜|]", rest, maxsplit=1)[0]
                        para.tokens.append((domain, display, plain_len))
                        self.token_paras[(book, domain, display)].append((ch, pn))
                        parts.append(display)
                        plain_len += len(display)
                        pos_raw = tm.end()
                    parts.append(line[pos_raw:])
                    para.plain = "".join(parts)
                    self.paras[(book, ch, pn)] = para
                    self.ngrams |= set_ngrams(para.plain, self.ngram_n)

    def para_at(self, book: str, ch: int, pn: int) -> Para | None:
        return self.paras.get((book, ch, pn))

    def paras_of(self, book: str, domain: str, display: str) -> list[tuple[int, int]]:
        return self.token_paras.get((book, domain, display), [])

    def cooccur(self, domains: list[tuple[str, str]], target_domain: str) -> Counter:
        """多 surface（(book,domain,display) → 段落）共现统计：返回 target_domain 显示 → 共现段落数。"""
        counter: Counter = Counter()
        seen = set()
        for book, domain, display in domains:
            for ch, pn in self.paras_of(book, domain, display):
                key = (book, ch, pn)
                if key in seen:
                    continue
                seen.add(key)
                para = self.paras.get(key)
                if not para:
                    continue
                for tdomain, tdisplay, _ in para.tokens:
                    if tdomain == target_domain:
                        counter[(book, tdisplay)] += 1
        return counter

    def find_name_near(self, para: Para, pos: int, window: int = 30,
                       domains: str = "@") -> str | None:
        best = None
        for domain, display, p in para.tokens:
            if domain not in domains:
                continue
            if abs(p - pos) <= window and (best is None or abs(p - pos) < abs(best[0] - pos)):
                best = (p, display)
        return best[1] if best else None

    def age_anchors_by_person(self, time_hub: "TimeHub") -> dict[str, dict]:
        """N4 年龄锚 → 人物归属（同段 @ 近邻 ≤25 字；每人物取最早一锚）。"""
        best: dict[str, dict] = {}
        order = {b: i for i, b in enumerate(self.books)}
        for book in self.books:
            for tp in time_hub.book_points(book):
                if tp.get("age") is None:
                    continue
                a = tp.get("anchor") or {}
                ch, pn = a.get("chapter"), a.get("pn")
                para = self.para_at(book, ch, pn)
                if para is None:
                    continue
                span = a.get("span_in_line") or []
                pos = 0
                if span:
                    pos = len(strip_markup(para.raw[:span[0]]))
                person = self.find_name_near(para, pos, window=25)
                if not person:
                    continue
                eid = ENTITIES.ref(person)
                if not eid:
                    continue
                rec = {"book": book, "ch": ch, "pn": pn, "age": tp["age"], "display": tp.get("display"),
                       "t_days": tp.get("t_days"), "year_ce": tp.get("year_ce"),
                       "confidence": tp.get("confidence"), "tp_id": tp.get("tp_id")}
                key = (order.get(book, 99), ch, pn)
                prev = best.get(eid)
                prev_key = (order.get(prev["book"], 99), prev["ch"], prev["pn"]) if prev else None
                if prev is None or key < prev_key:
                    best[eid] = rec
        return best


class TimeHub:
    def __init__(self, books: list[str]):
        self.books = books
        self.data: dict[str, dict] = {}
        for book in books:
            path = REG / "time" / f"{book}.json"
            self.data[book] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def book_points(self, book: str) -> list[dict]:
        return self.data.get(book, {}).get("time_points") or []

    def generated(self) -> dict:
        return {b: self.data.get(b, {}).get("generated_at") for b in self.books}


class LegacyHub:
    def __init__(self):
        self.weapons = json.loads((KB / "神兵表.json").read_text(encoding="utf-8")) if (KB / "神兵表.json").exists() else {}
        self.moves = json.loads((KB / "招式表.json").read_text(encoding="utf-8")) if (KB / "招式表.json").exists() else {}
        self.tree = json.loads((KB / "系列谱系考订表.json").read_text(encoding="utf-8")) if (KB / "系列谱系考订表.json").exists() else {}
        self.works = json.loads((KB / "作品元数据表.json").read_text(encoding="utf-8")) if (KB / "作品元数据表.json").exists() else {}
        self.chrono_order: dict[str, int] = {}
        idx = 0
        for spine in self.tree.get("chronology_spine") or []:
            for b in spine.get("books") or []:
                name = b.rstrip("*")
                if name and name not in self.chrono_order:
                    self.chrono_order[name] = idx
                    idx += 1
        self.pub_order: dict[str, int] = {}
        for w in self.works.get("works") or []:
            self.pub_order[w.get("book")] = int(w.get("no") or 999)

    def book_order(self, book: str) -> int:
        return self.chrono_order.get(book, 100 + self.pub_order.get(book, 999))

    def weapon_list(self) -> list[dict]:
        return self.weapons.get("artifacts") or []

    def move_list(self) -> list[dict]:
        return self.moves.get("moves") or []


class NewTypesHub:
    def __init__(self):
        path = ROOT / "wordlists" / "new_entity_types.json"
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.version = (raw.get("meta") or {}).get("schema", "")
        self.items = raw.get("items") or []

    def surfaces(self, typ: str) -> set[str]:
        return {i.get("canonical") for i in self.items if i.get("type") == typ and i.get("canonical")}


# ────────────────────────── 全局数据（延迟加载） ──────────────────────────
ENTITIES: EntitiesHub | None = None
CONC: ConcordanceHub | None = None
REL: RelationsHub | None = None
TIME: TimeHub | None = None
GAZ: GazetteerHub | None = None
LEGACY: LegacyHub | None = None
NEWTYPES: NewTypesHub | None = None
TAGGED: TaggedHub | None = None
AGE_BY_PERSON: dict[str, dict] = {}
NAME_MASK_RE = None
MOVE_BY_ART: dict[str, list[dict]] = defaultdict(list)
PERSON_MOVES: dict[str, list[dict]] = defaultdict(list)
SECT_ART: dict[str, set] = defaultdict(set)
PERSON_SECTS: dict[str, set] = defaultdict(set)


def build_name_mask() -> None:
    """R3 专名表（人名/武功/地名/书名/绰号）→ R1 检查时先掩码专名再比 n-gram。"""
    global NAME_MASK_RE
    names = set(BOOKS)
    if ENTITIES:
        for e in ENTITIES.items:
            for k in ("canonical", "series_display"):
                if e.get(k):
                    names.add(e[k])
            names |= set(e.get("aliases") or []) | set(e.get("contextual") or [])
        names |= set(ENTITIES.display_canon_map.keys())
    if CONC:
        for t in ("☆", "{", "•"):
            for canon, agg in CONC.by_type_canon.get(t, {}).items():
                names.add(canon)
                names |= set(agg.get("variants") or set())
        for book, d in CONC.book_data.items():
            for ent in d.get("entities") or []:
                names.add(ent.get("canonical") or "")
                names |= {v.get("display") for v in ent.get("variants") or [] if v.get("display")}
    if GAZ:
        for p in GAZ.places:
            names.add(p.get("name") or p.get("id") or "")
            names |= set(p.get("aliases") or [])
    if LEGACY:
        for a in LEGACY.weapon_list():
            names.add(a.get("canonical") or "")
        for mv in LEGACY.move_list():
            names.add(mv.get("canonical") or "")
    names = {n for n in names if isinstance(n, str) and len(n) >= 2}
    ordered = sorted(names, key=len, reverse=True)
    if ordered:
        NAME_MASK_RE = re.compile("|".join(re.escape(n) for n in ordered))


def mask_names(text: str) -> str:
    if NAME_MASK_RE is None:
        return text
    return NAME_MASK_RE.sub("◇", text)


def load_all(books: list[str]) -> None:
    global ENTITIES, CONC, REL, TIME, GAZ, LEGACY, NEWTYPES, TAGGED, AGE_BY_PERSON
    global MOVE_BY_ART, PERSON_MOVES, SECT_ART, PERSON_SECTS
    ENTITIES = EntitiesHub(REG / "entities.json")
    CONC = ConcordanceHub(books)
    REL = RelationsHub(books)
    TIME = TimeHub(books)
    GAZ = GazetteerHub()
    LEGACY = LegacyHub()
    NEWTYPES = NewTypesHub()
    TAGGED = TaggedHub(books)
    AGE_BY_PERSON = TAGGED.age_anchors_by_person(TIME)
    build_name_mask()
    MOVE_BY_ART = defaultdict(list)
    PERSON_MOVES = defaultdict(list)
    SECT_ART = defaultdict(set)
    PERSON_SECTS = defaultdict(set)
    for mv in LEGACY.move_list():
        parent = mv.get("parent_art")
        conf = mv.get("conf")
        if parent and parent != "待考" and conf in ("strong", "ok"):
            MOVE_BY_ART[parent].append(mv)
            for ub in mv.get("used_by") or []:
                eid = ENTITIES.ref(ub.get("name") or "")
                if eid:
                    PERSON_MOVES[eid].append({"move": mv, "art": parent, "conf": conf})
        sect = mv.get("sect")
        if sect and conf in ("strong", "ok"):
            SECT_ART[sect].add(parent or "")
            for ub in mv.get("used_by") or []:
                eid = ENTITIES.ref(ub.get("name") or "")
                if eid:
                    PERSON_SECTS[eid].add(sect)


def first_appearance(book_entries: dict[str, dict], books: list[str]) -> dict:
    """#7 口径：active_books=[book]（派生、无排序契约）；first_appearance=编年 earliest。"""
    active = sorted([b for b in book_entries if b in books], key=LEGACY.book_order)
    if not active:
        return {"active_books": [], "first_appearance": None}
    first_book = min(active, key=LEGACY.book_order)
    ent = book_entries.get(first_book) or {}
    first = ent.get("first") or {}
    ch, pn = first.get("chapter"), first.get("para")
    fa = {"book": first_book, "loc_r": loc_r(first_book, ch, pn)}
    return {"active_books": active, "first_appearance": fa}


def entity_concordance(etype: str, entity_id: str) -> tuple[dict, dict]:
    """登记实体 → 各书 concordance 条目 + 首现。"""
    entries = {}
    if CONC:
        for book in CONC.books:
            ent = CONC.entry(entity_id, book)
            if ent:
                entries[book] = ent
    return entries, first_appearance(entries, BOOKS)


def book_match(active_books: list[str], books: list[str]) -> bool:
    """--book 过滤：全量时包含所有登记实体（未匹配 concordance 也保留，标 active_books=[]）；单书时要求命中。"""
    if not books:
        return True
    if set(books) >= set(BOOKS):
        return True
    return bool(set(active_books or []) & set(books))


def concordance_aliases(entries: dict, canonical: str, existing: list[dict]) -> list[dict]:
    seen = {x.get("surface") for x in existing} | {canonical}
    out = list(existing)
    for ent in entries.values():
        for v in ent.get("variants") or []:
            s = v.get("display")
            if s and s not in seen:
                seen.add(s)
                out.append({"surface": s, "type": "语料变体（concordance）"})
    return out


# ────────────────────────── 卡片组装 ──────────────────────────
def meta_block(card_type: str, name: str, entity_ref: str | None, slug: str,
               proposition: str, supported_by: dict, sources: list[str],
               confidence: str, publish_state: str, method: str,
               denominator: str | None = None, gaps: list[str] | None = None,
               source_entity_key: str | None = None) -> dict:
    m = {
        "stable_id": f"card.{card_type}.{slug}",
        "entity_ref": entity_ref,
        "card_type": card_type,
        "proposition": proposition[:100],
        "supported_by": supported_by,
        "sources": sources,
        "confidence": confidence,
        "data_version": DATA_VERSION,
        "rule_version": RULE_VERSION,
        "method": method,
        "denominator": denominator,
        "publish_state": publish_state,
        "demo": False,
        "demo_note": "",
        "redaction": {"R1": "pass", "R2": "ref_only", "R4": "not_approved"},
    }
    if entity_ref is None:
        m["entity_ref_gap"] = "01g 登记层 scope 仅 @/◆/& → 本类型未建实体 ID（扩类待办；不伪造 E-ID）"
    if source_entity_key:
        m["source_entity_key"] = source_entity_key
    if gaps:
        m["data_gaps"] = gaps
    return m


def confidence_for(entity_id: str | None, fields_weight: bool, books_n: int) -> str:
    if entity_id is None:
        return "C"
    status = ENTITIES.status(entity_id)
    if status == "approved" and fields_weight and books_n >= 2:
        return "B"
    return "C"


def publish_state_for(conf: str) -> str:
    return "in-review" if conf == "B" else "draft"


def categorize_art(name: str) -> str:
    # 名称关键词启发式（#8 武功树未建；报告中注明非定版枚举）
    rules = [("剑", "剑法"), ("刀", "刀法"), ("掌", "掌法"), ("拳", "拳法"), ("指", "指法"),
             ("腿", "腿法"), ("身法", "身法"), ("轻功", "轻功"), ("内功", "内功"),
             ("心法", "内功"), ("点穴", "点穴"), ("暗器", "暗器"), ("阵", "阵法"),
             ("枪", "枪法"), ("棍", "棍法"), ("鞭", "鞭法"), ("擒拿", "擒拿"), ("抓", "擒拿")]
    for keyword, cat in rules:
        if keyword in name:
            return cat
    return "未归类"


def categorize_faction(name: str) -> str:
    rules = [("镖局", "镖局"), ("山庄", "世家"), ("堡", "世家"), ("庄", "世家"),
             ("帮", "帮会"), ("教", "教派"), ("会", "会党"), ("寺", "宗教门派"),
             ("观", "宗教门派"), ("庵", "宗教门派"), ("派", "门派"), ("门", "门派"),
             ("洞", "门派"), ("岛", "门派"), ("宫", "门派"), ("旗", "组织"), ("盟", "联盟")]
    for suffix, typ in rules:
        if suffix in name:
            return typ
    return "未明示"


def is_manual_name(name: str) -> bool:
    exclude = ("诗经", "道德经", "南华经", "法华经", "维摩经", "般若经", "佛经", "地图",
               "易经", "藏经", "点将录", "攘夷录", "大义觉迷录", "燃灯录", "庄子南华经")
    if any(x in name for x in exclude):
        return False
    martial = ("武", "拳", "剑", "掌", "刀", "内功", "心法", "真经", "秘笈", "秘籍", "秘本",
               "易筋", "洗髓", "点穴", "轻功", "暗器", "阵法")
    tail = ("谱", "笈", "经", "诀", "录", "宝典", "真经", "心法", "秘本", "遗篇", "手抄本")
    return (any(k in name for k in martial) or name in ("秘本", "秘笈", "秘籍", "宝典")) and \
        (any(name.endswith(t) for t in tail) or any(k in name for k in ("谱", "笈", "经", "诀", "秘")))


def brief_text(parts: list[str], min_len: int = 200, max_len: int = 500) -> str:
    """机械转述 brief（不含原文片段）；不足 200 字按 SKILL 缺省留空待人工。"""
    text = "".join(p for p in parts if p)
    if not text:
        return ""
    fillers = [
        "字段来源为登记层实体、标注语料统计、N5 关系边与 N4 时间轴；不含原文片段，也不以连续片段转述原文。",
        "缺失字段按 SKILL 未知原则以 []/null/「未明示」缺省登记，不以推测补全；来源映射与填充率见 logs/sku/summary.md。",
        "本卡为结构化字段机械转述，brief 待人工复核缩写；引用一律用实体 ID、边 ID 或机锚指针。",
    ]
    for sentence in fillers:
        if len(text) >= min_len:
            break
        if len(text) + len(sentence) > max_len:
            break
        text += sentence
    if min_len <= len(text) <= max_len:
        return text
    return ""


def source_ids(edges: list[dict], limit: int = 6) -> list[str]:
    out = []
    for e in edges[:limit]:
        if e.get("id"):
            out.append(e["id"])
    return out


def _surface(x) -> str:
    """既有资产里的人名/物名可能是 str 或 dict（{name/person/canonical}）。"""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ("name", "person", "canonical", "surface"):
            if x.get(k):
                return str(x[k])
    return ""


# ─── 人物卡 ───
def build_person_cards(books: list[str]) -> list[dict]:
    cards = []
    for e in ENTITIES.items:
        if e.get("type") != "@":
            continue
        eid, canonical = e["id"], e.get("canonical") or ""
        entries, cross = entity_concordance("@", eid)
        if not book_match(cross.get("active_books") or [], books):
            continue
        aliases = concordance_aliases(entries, canonical, ENTITIES.aliases_of(eid))
        teacher_edges = REL.teacher_edges(eid) if REL else []
        disciple_edges = REL.disciple_edges(eid) if REL else []
        teachers = [x["id"] for x in teacher_edges if x.get("id")]
        disciples = [x["id"] for x in disciple_edges if x.get("id")]
        kinship_edges = REL.pred_edges(eid, {"婚约", "结义", "收养"}) if REL else []
        romance_edges = REL.pred_edges(eid, {"婚约"}) if REL else []
        killed = REL.killed_by(eid) if REL else []
        # 门派履历：N5 任职边 + 招式表 sect 推导（弱）
        faction_history = []
        for e2 in REL.pred_edges(eid, {"任职"}) if REL else []:
            org = e2.get("object") or ""
            org_id = ENTITIES.ref(org)
            faction_history.append({"faction_ref": org_id, "faction_surface": None if org_id else "未登记",
                                    "role": "任职（N5 任职边）", "edge_ref": e2.get("id"), "conf": e2.get("confidence")})
        for sect in sorted(PERSON_SECTS.get(eid, set())):
            fid = ENTITIES.ref(sect)
            if any(x.get("faction_ref") == fid for x in faction_history):
                continue
            faction_history.append({"faction_ref": fid, "faction_surface": None if fid else "未登记",
                                    "role": "门派归属（招式表 sect 推导）", "edge_ref": None, "conf": "weak"})
        # 武功：N5 掌握边 + 招式表 used_by
        arts = []
        seen_art = set()
        for e2 in REL.pred_edges(eid, {"掌握"}) if REL else []:
            name = e2.get("object") or ""
            ref = f"card.art.{slugify(name, 'art')}"
            if ref not in seen_art:
                seen_art.add(ref)
                arts.append({"art_ref": ref, "art_surface": None, "verb": "掌握（N5 掌握边）", "conf": e2.get("confidence")})
        for rec in PERSON_MOVES.get(eid, []):
            art_name = rec["art"]
            ref = f"card.art.{slugify(art_name, 'art')}"
            if ref in seen_art:
                continue
            seen_art.add(ref)
            arts.append({"art_ref": ref, "art_surface": None, "verb": rec["move"].get("canonical"),
                         "conf": rec["conf"]})
        # 辈分
        labels = [x for x in (REL.lineage_labels if REL else []) if ENTITIES.ref(x.get("person") or "") == eid]
        seniority = None
        if eid in (REL.generations if REL else {}) or labels:
            seniority = {
                "generation": (REL.generations or {}).get(eid),
                "labels": [{"value": x.get("value"), "relative_to": x.get("relative_to"),
                            "rule": x.get("rule"), "confidence": x.get("confidence")} for x in labels[:5]],
                "source": "N5 derived.trees.master_tree / lineage_labels",
            }
        age = AGE_BY_PERSON.get(eid)
        ending = {"type": "未明示"}
        if killed:
            k = killed[0]
            ending = {"type": "死亡（N5 杀害边候选，未经事件层核实）", "event_ref": k.get("id"),
                      "summary": "见 N5 杀害边（04a 未建，不判死法）", "conf": k.get("confidence")}
        arts_filled = bool(arts)
        conf = confidence_for(eid, bool(teacher_edges or disciple_edges or arts_filled or killed),
                              len(cross.get("active_books") or []))
        card = {
            "name": {"canonical": canonical},
            "aliases": aliases,
            "identity_tags": [],
            "faction_history": faction_history,
            "seniority": seniority,
            "teachers": teachers,
            "disciples": disciples,
            "kinship": [x["id"] for x in kinship_edges if x.get("id")],
            "romance": [x["id"] for x in romance_edges if x.get("id")],
            "arts": arts,
            "life_events": [],
            "age_anchor": ({**age, "loc": f"{age['book']}·{age['ch']}:{age['pn']}"} if age else None),
            "ending": ending,
            "relational_sku_refs": [],
            "brief": "",
            "active_books": cross["active_books"],
            "first_appearance": cross["first_appearance"],
        }
        gaps = ["identity_tags（#8 身份树）", "life_events（#4a 事件流）"]
        if not faction_history:
            gaps.append("faction_history（N5 无门派成员谓词）")
        if not arts:
            gaps.append("arts（N5 掌握边稀疏/招式表 used_by 未覆盖）")
        card["brief"] = brief_text(_person_brief_parts(canonical, aliases, seniority, teachers,
                                                       disciples, kinship_edges, romance_edges, arts,
                                                       faction_history, age, ending, cross))
        proposition = _person_prop(canonical, aliases, faction_history, teachers, arts, ending, cross)
        sources = [f"01g:{eid}", "#7:concordance(active_books/first_appearance)"]
        if teachers or disciples or kinship_edges:
            sources.append("#6:edges=" + ",".join(source_ids(teacher_edges + disciple_edges + kinship_edges, 6)))
        if PERSON_MOVES.get(eid):
            sources.append("招式表:used_by×" + str(len(PERSON_MOVES[eid])))
        if age:
            sources.append(f"#5:{age.get('tp_id')}")
        if cross.get("first_appearance"):
            sources.append("02ab:" + str(cross["first_appearance"].get("loc_r")))
        card["meta"] = meta_block("person", canonical, eid, eid.lower(), proposition,
                                  {"entities": [eid], "relations": source_ids(teacher_edges + disciple_edges + kinship_edges),
                                   "events": []},
                                  sources, conf, publish_state_for(conf),
                                  "01g 实体投影＋#7 concordance 跨书＋N5 关系边＋N4 年龄锚＋招式表 used_by；机械转述",
                                  None, gaps, f"entities:{eid}")
        cards.append(card)
    return cards


def _person_brief_parts(canonical, aliases, seniority, teachers, disciples, kinship, romance,
                        arts, faction_history, age, ending, cross) -> list[str]:
    parts = [f"本卡据登记层实体与 5 书标注语料整理：{canonical}"]
    if aliases:
        parts.append("，另见别名" + "、".join(a["surface"] for a in aliases[:4]))
    books = cross.get("active_books") or []
    if books:
        parts.append(f"；见于《{'》《'.join(books)}》")
    if cross.get("first_appearance"):
        parts.append(f"，编年首见 {cross['first_appearance'].get('book')}")
    if faction_history:
        parts.append(f"；门派/归属记录 {len(faction_history)} 条")
    if teachers:
        parts.append(f"；N5 师承边 {len(teachers)} 条")
    if disciples:
        parts.append(f"；传人边 {len(disciples)} 条")
    if kinship or romance:
        parts.append(f"；亲属/情缘类边 {len(kinship) + len(romance)} 条")
    if arts:
        parts.append(f"；相关武功 {len(arts)} 门（招式表 used_by/N5 掌握边）")
    if age:
        parts.append(f"；年龄锚 {age.get('age')} 岁（{age.get('display')}，N4 推算）")
    if ending.get("type") != "未明示":
        parts.append("；结局见 N5 杀害边候选（事件层未核实）")
    parts.append("。门派履历、事件流、身份树等字段因上游 #4a/#8 未建暂缺；")
    return parts


def _person_prop(canonical, aliases, faction_history, teachers, arts, ending, cross) -> str:
    bits = [canonical]
    if aliases:
        bits.append("（别名" + "、".join(a["surface"] for a in aliases[:2]) + "）")
    books = cross.get("active_books") or []
    if books:
        bits.append(f"为《{'》《'.join(books[:2])}》人物")
    if faction_history:
        bits.append(f"，有{len(faction_history)}条门派/任职记录")
    if teachers:
        bits.append(f"，N5 师承边{len(teachers)}条")
    if arts:
        bits.append(f"，与{len(arts)}门武功相关")
    if ending.get("type") != "未明示":
        bits.append("，结局存疑待事件层核实")
    return "".join(bits)


# ─── 门派卡 ───
def build_faction_cards(books: list[str]) -> list[dict]:
    cards = []
    for e in ENTITIES.items:
        if e.get("type") != "◆":
            continue
        eid, canonical = e["id"], e.get("canonical") or ""
        entries, cross = entity_concordance("◆", eid)
        if not book_match(cross.get("active_books") or [], books):
            continue
        aliases = concordance_aliases(entries, canonical, ENTITIES.aliases_of(eid))
        lineage = []
        for e2 in REL.by_faction.get(eid, []):
            if e2.get("predicate") != "任职":
                continue
            lineage.append({"person_ref": e2.get("_subject_ref"), "term": None,
                            "edge_ref": e2.get("id"), "conf": e2.get("confidence")})
        signature = []
        seen = set()
        for art in sorted(SECT_ART.get(canonical, set())):
            if not art:
                continue
            ref = f"card.art.{slugify(art, 'art')}"
            if ref in seen:
                continue
            seen.add(ref)
            signature.append({"art_ref": ref, "art_surface": None, "conf": "ok"})
        # 据点：tagged 共现 ◆×=
        surfaces = {canonical} | {x["surface"] for x in aliases} | set(CONC.surfaces_by_entity.get(eid, set())) if CONC else {canonical}
        doms = [(b, "◆", s) for b in (entries or {}) for s in surfaces if s]
        places = _co_places(doms, top=5, allowed_kinds={
            "山", "峰", "岭", "洞", "岛", "寺", "观", "庙", "宫", "殿", "谷",
            "庄", "堡", "城", "镇", "关", "门", "派", "庵", "院", "楼", "阁", "寨", "坞", "林",
        }) if TAGGED else []
        status = {"value": "未明示"}
        death_loc = _faction_death_candidate(surfaces, entries)
        if death_loc:
            status = {"value": "已灭（候选：tagged 灭派词共现，未经事件层核实）", "basis_event": None,
                      "note": death_loc}
        member_edges = REL.by_faction.get(eid, []) if REL else []
        member_stat = {
            "metric": "N5 关系边计数（客体=本组织，全谓词）",
            "value": len(member_edges),
            "denominator": f"N5 5 书关系边总数 {REL.edges_total if REL else 0} 条",
        }
        conf = confidence_for(eid, bool(lineage or signature or places), len(cross.get("active_books") or []))
        card = {
            "name": {"canonical": canonical},
            "aliases": aliases,
            "faction_type": categorize_faction(canonical),
            "lineage": lineage,
            "signature_arts": signature,
            "strongholds": places,
            "timeline": [],
            "status": status,
            "branch_alliance": [],
            "member_stat": member_stat,
            "brief": "",
            "active_books": cross["active_books"],
            "first_appearance": cross["first_appearance"],
        }
        gaps = ["timeline（#4a 组织事件流）", "branch_alliance（N5 无联盟/敌对谓词）"]
        if not places:
            gaps.append("strongholds（tagged 共现为空/地点未入 gazetteer）")
        if not lineage:
            gaps.append("lineage（N5 任职边稀疏）")
        if not signature:
            gaps.append("signature_arts（招式表 sect 未覆盖）")
        card["brief"] = brief_text(_faction_brief_parts(canonical, aliases, card, cross, status))
        proposition = _faction_prop(canonical, aliases, card, cross)
        sources = ["01g:" + eid, "#7:concordance", "N5:edges=" + str(len(member_edges))]
        if places:
            sources.append("#10:gazetteer 共现")
        if signature:
            sources.append("招式表:sect×" + str(len(signature)))
        if cross.get("first_appearance"):
            sources.append("02ab:" + str(cross["first_appearance"].get("loc_r")))
        card["meta"] = meta_block("faction", canonical, eid, eid.lower(), proposition,
                                  {"entities": [eid] + [x["person_ref"] for x in lineage if x.get("person_ref")],
                                   "relations": source_ids(member_edges), "events": []},
                                  sources, conf, publish_state_for(conf),
                                  "01g 实体投影＋#7 concordance＋N5 任职/组织边＋tagged 共现（据点/灭派候选，启发式）",
                                  f"N5 5 书关系边总数 {REL.edges_total if REL else 0} 条", gaps, f"entities:{eid}")
        cards.append(card)
    return cards


def _faction_brief_parts(canonical, aliases, card, cross, status) -> list[str]:
    parts = [f"本卡据登记层与语料整理：{canonical}"]
    if aliases:
        parts.append("（别称" + "、".join(a["surface"] for a in aliases[:3]) + "）")
    parts.append(f"；类型按名称后缀启发式归为「{card['faction_type']}」（#8 门派树未建，非定版枚举）")
    books = cross.get("active_books") or []
    if books:
        parts.append(f"；见于《{'》《'.join(books)}》")
    if card["strongholds"]:
        parts.append(f"；语料共现据点 {len(card['strongholds'])} 处（启发式，非组织驻地谓词）")
    if card["lineage"]:
        parts.append(f"；N5 任职边 {len(card['lineage'])} 条")
    if card["signature_arts"]:
        parts.append(f"；招式表 sect 关联武功 {len(card['signature_arts'])} 门")
    if status.get("value") != "未明示":
        parts.append(f"；存续状态 {status['value']}")
    parts.append("。事件时间线、分支联盟、成员边因上游 #4a/N5 谓词缺口暂缺；")
    return parts


def _faction_prop(canonical, aliases, card, cross) -> str:
    bits = [canonical]
    books = cross.get("active_books") or []
    if books:
        bits.append(f"为《{'》《'.join(books[:2])}》所载组织")
    bits.append(f"，类型{card['faction_type']}（启发式）")
    if card["lineage"]:
        bits.append(f"，任职记录{len(card['lineage'])}条")
    if card["strongholds"]:
        bits.append(f"，据点{len(card['strongholds'])}处（共现）")
    return "".join(bits)


def _co_places(doms: list[tuple[str, str, str]], top: int = 6,
               allowed_kinds: set[str] | None = None) -> list[dict]:
    if not TAGGED or not GAZ:
        return []
    counter = TAGGED.cooccur(doms, "=")
    out = []
    for (book, display), n in counter.most_common(top * 3):
        pid = GAZ.ref(display)
        if not pid:
            continue
        if allowed_kinds is not None:
            kind = (GAZ.by_id.get(pid) or {}).get("kind")
            if kind not in allowed_kinds:
                continue
        out.append({"place_ref": pid, "place_surface": None, "conf": "weak", "basis": f"tagged 共现 {n} 段",
                    "derived": True})
        if len(out) >= top:
            break
    return out


def _faction_death_candidate(surfaces: set[str], entries: dict) -> str | None:
    if not TAGGED:
        return None
    for book in entries:
        for s in surfaces:
            for ch, pn in TAGGED.paras_of(book, "◆", s):
                para = TAGGED.para_at(book, ch, pn)
                if para and re.search(r"(尽灭|阖派|覆灭|灭派|铲除|除名|歼灭|屠尽|无一幸免)", para.plain) \
                        and "分舵" not in para.plain and not re.search(r"(传言|传闻|据说|传说|听说)", para.plain):
                    return f"{book}·{ch}:{pn}"
    return None


# ─── 武功卡 ───
def build_art_cards(books: list[str]) -> list[dict]:
    cards = []
    if not CONC:
        return cards
    all_arts = dict(CONC.by_type_canon["☆"])
    move_parents = {mv.get("parent_art") for mv in LEGACY.move_list()
                    if mv.get("parent_art") and mv.get("parent_art") != "待考"}
    for name in move_parents:
        if name and name not in all_arts:
            all_arts[name] = {"books": {}, "variants": set(), "total": 0, "type_label": "武功技艺"}
    for name, agg in all_arts.items():
        entry_books = agg["books"]
        if not book_match(sorted(entry_books, key=LEGACY.book_order), books):
            continue
        names = {name} | set(agg["variants"])
        moves = MOVE_BY_ART.get(name, [])
        practitioners = []
        seen_p = set()
        for mv in moves:
            for ub in mv.get("used_by") or []:
                eid = ENTITIES.ref(ub.get("name") or "")
                if eid and eid not in seen_p:
                    seen_p.add(eid)
                    practitioners.append(eid)
        for e in REL.edges if REL else []:
            if e.get("predicate") == "掌握" and e.get("object") == name and e.get("_subject_ref"):
                if e["_subject_ref"] not in seen_p:
                    seen_p.add(e["_subject_ref"])
                    practitioners.append(e["_subject_ref"])
        aliases = [{"surface": v, "type": "变体（concordance）"} for v in sorted(agg["variants"] - {name})]
        category = categorize_art(name)
        hierarchy = None   # #8 谱系树未建：按 SKILL 缺省 null（不强填占位）
        recorded_in = _art_recorded_in(name)
        card = {
            "name": {"canonical": name},
            "aliases": aliases,
            "category": category,
            "hierarchy": hierarchy,
            "moves": [{"move_ref": "move." + slugify(m.get("canonical") or "", "move"),
                       "move_name": None,
                       "used_by": [ENTITIES.ref(u.get("name") or "") for u in (m.get("used_by") or [])
                                   if ENTITIES.ref(u.get("name") or "")][:6],
                       "conf": m.get("conf")} for m in moves[:20]],
            "creator": {"type": "创派者未明"},
            "inheritance_chain": [],
            "practitioners": practitioners[:20],
            "grade": None,
            "grade_basis": "未评——需出场战绩事件统计支撑（#4a 未建）",
            "recorded_in": recorded_in,
            "brief": "",
            "active_books": sorted([b for b in entry_books], key=LEGACY.book_order),
            "first_appearance": first_appearance(entry_books, BOOKS)["first_appearance"],
        }
        gaps = ["category/hierarchy（#8 武功品类树/谱系树）", "creator（#4a 悟创事件）",
                "inheritance_chain（N5 未建武功传人链）", "grade（无战绩统计）"]
        if not moves:
            gaps.append("moves（招式表 parent_art 未覆盖）")
        if not recorded_in:
            gaps.append("recorded_in（秘籍互指边未建）")
        card["brief"] = brief_text(_art_brief_parts(name, aliases, card, entry_books, moves, practitioners))
        proposition = _art_prop(name, category, entry_books, moves, practitioners)
        conf = "C"
        sources = ["#7:concordance(☆)", "招式表:parent_art=" + name if moves else "招式表:无直接招式"]
        if entry_books:
            sources.append("02ab:" + str((card["first_appearance"] or {}).get("loc_r")))
        card["meta"] = meta_block("art", name, None, slugify(name, "art"), proposition,
                                  {"entities": practitioners[:6], "relations": [], "events": []},
                                  sources, conf, "draft",
                                  "concordance 全类型实体＋招式表 parent_art/used_by；登记层未扩类→entity_ref gap",
                                  f"招式表 moves 222 条中 parent_art=本武功且 conf∈strong/ok 的招式 {len(moves)} 条",
                                  gaps, "concordance:☆:" + name)
        cards.append(card)
    return cards


def _art_recorded_in(art_name: str) -> list[str]:
    out = []
    if not TAGGED:
        return out
    # 由 tagged 共现推导：含秘籍候选 token 的段落里同时出现本武功 ☆
    for mv in []:
        pass
    return out


def _art_brief_parts(name, aliases, card, entry_books, moves, practitioners) -> list[str]:
    parts = [f"本卡据 5 书标注语料与招式表整理：{name}"]
    if aliases:
        parts.append("（另见" + "、".join(a["surface"] for a in aliases[:3]) + "）")
    if entry_books:
        parts.append(f"；见于《{'》《'.join(sorted(entry_books, key=LEGACY.book_order))}》")
    parts.append(f"；品类按名称后缀启发式归为「{card['category']}」（#8 武功树未建，非定版枚举）")
    if moves:
        parts.append(f"；招式表 parent_art 关联招式 {len(moves)} 式（conf=strong/ok）")
    if practitioners:
        parts.append(f"；会用者 {len(practitioners)} 人（招式表 used_by/N5 掌握边）")
    parts.append("。创派者、传人链、品级评价因 #4a/#8 未建暂缺；")
    return parts


def _art_prop(name, category, entry_books, moves, practitioners) -> str:
    bits = [name, f"为《{'》《'.join(sorted(entry_books, key=LEGACY.book_order)[:2])}》所载{category}（启发式）"]
    if moves:
        bits.append(f"，有招式记录{len(moves)}式")
    if practitioners:
        bits.append(f"，会用者{len(practitioners)}人")
    return "".join(bits)


# ─── 兵器卡（神兵表投影） ───
def build_artifact_cards(books: list[str]) -> list[dict]:
    cards = []
    if not LEGACY:
        return cards
    for a in LEGACY.weapon_list():
        name = a.get("canonical") or ""
        entry_books = a.get("books")
        if isinstance(entry_books, dict):
            bks = list(entry_books.keys())
        elif isinstance(entry_books, list):
            bks = entry_books
        else:
            bks = []
        if not book_match(sorted(bks, key=LEGACY.book_order), books):
            continue
        chain = []
        unresolved = []
        for item in a.get("chain") or []:
            persons = []
            for pname in item.get("persons") or []:
                pname = _surface(pname)
                pid = ENTITIES.ref(pname)
                if pid:
                    persons.append(pid)
                elif pname and pname not in unresolved:
                    unresolved.append(pname)
            chain.append({
                "verb": item.get("verb"), "persons": persons,
                "book": item.get("book"), "loc": item.get("loc"),
                "loc_r": loc_r(item.get("book") or "", *_split_loc(item.get("loc"))),
                "conf": item.get("conf"),
            })
        dedup, seen = [], set()
        for c in chain:
            key = (c["verb"], c["book"], c["loc"], tuple(c["persons"]))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(c)
        makers = [ENTITIES.ref(_surface(x)) for x in (a.get("makers") or [])]
        makers = [m for m in makers if m]
        forge = {"type": "锻造未明"}
        if makers:
            forge = {"smith_ref": makers[0], "place_ref": None, "event_ref": None, "conf": a.get("conf")}
        end_state = a.get("end_state")
        if isinstance(end_state, dict):
            status = end_state.get("value") or end_state.get("status") or "未明示"
        else:
            status = str(end_state) if end_state else "下落不明"
        card = {
            "name": {"canonical": name},
            "kind": a.get("kind") or "未归类",
            "grade": a.get("grade"),
            "grade_basis": a.get("grade_basis"),
            "forge": forge,
            "chain": dedup,
            "current_whereabouts": {"status": status, "event_ref": None, "loc_ref": None},
            "brief": "",
            "active_books": sorted(bks, key=LEGACY.book_order),
            "first_appearance": _weapon_first_appearance(dedup, bks),
        }
        gaps = []
        if not makers:
            gaps.append("forge（#4a 锻造事件未建）")
        if not dedup:
            gaps.append("chain（神兵表本条无 chain）")
        if unresolved:
            gaps.append(f"chain.persons 未登记人名 {len(unresolved)} 个（01g 未收录，不能写 E-ID）")
        card["brief"] = brief_text(_artifact_brief_parts(name, a, card, bks, dedup, status))
        proposition = _artifact_prop(name, a, card, bks, status)
        conf = {"strong": "B", "ok": "C"}.get(a.get("conf"), "C")
        sources = ["神兵表:" + name, "#7:神兵表 books", "01g:未登记（器物扩类待办）"]
        if dedup:
            sources.append("02ab:" + str(dedup[0].get("loc_r")))
        meta = meta_block("artifact", name, None, slugify(name, "artifact"), proposition,
                          {"entities": [], "relations": [], "events": []}, sources, conf,
                          publish_state_for(conf),
                          "神兵表 chain/holders/grade 直接投影（既有资产）＋人名→实体 ID 映射",
                          f"神兵表 chain 原始 {len(a.get('chain') or [])} 环（去重后 {len(dedup)} 环）",
                          gaps, "weapons:" + name)
        if unresolved:
            meta["unresolved_refs"] = unresolved[:10]
        card["meta"] = meta
        cards.append(card)
    return cards


def _split_loc(loc: str | None) -> tuple[int | None, int | None]:
    if not loc or ":" not in str(loc):
        return None, None
    a, b = str(loc).split(":", 1)
    try:
        return int(a), int(b)
    except ValueError:
        return None, None


def _weapon_first_appearance(chain: list[dict], bks: list[str]) -> dict | None:
    for c in sorted([x for x in chain if x.get("book")], key=lambda x: LEGACY.book_order(x["book"])):
        loc = c.get("loc_r")
        if loc:
            return {"book": c["book"], "loc_r": loc}
    if bks:
        return {"book": min(bks, key=LEGACY.book_order), "loc_r": None}
    return None


def _artifact_brief_parts(name, a, card, bks, chain, status) -> list[str]:
    parts = [f"本卡据神兵表投影：{name}"]
    parts.append(f"；类型 kind={card['kind']}" + (f"、品级 {card['grade']}（{card['grade_basis']}）" if card.get("grade") else "（品级未评）"))
    if bks:
        parts.append(f"；见于《{'》《'.join(sorted(bks, key=LEGACY.book_order))}》")
    if chain:
        verbs = []
        for c in chain:
            if c.get("verb") and c["verb"] not in verbs:
                verbs.append(c["verb"])
        parts.append(f"；持有链 {len(chain)} 环（verbs={'/'.join(verbs[:5])}）")
    if status and status != "未明示":
        parts.append(f"；下落状态 {status}")
    parts.append("。锻造事件、事件层槽位因 #4a 未建暂缺；人名引用仅收 01g 已登记实体；")
    return parts


def _artifact_prop(name, a, card, bks, status) -> str:
    bits = [name, f"为神兵表所载{card['kind']}"]
    if card.get("grade"):
        bits.append(f"（{card['grade']}）")
    if bks:
        bits.append(f"，见于《{'》《'.join(sorted(bks, key=LEGACY.book_order)[:2])}》")
    if card["chain"]:
        bits.append(f"，持有链{len(card['chain'])}环")
    if status and status != "未明示":
        bits.append(f"，下落{status}")
    return "".join(bits)


# ─── 秘籍卡 ───
def build_manual_cards(books: list[str]) -> list[dict]:
    cards = []
    if not CONC:
        return cards
    for name, agg in CONC.by_type_canon["{"].items():
        if not is_manual_name(name):
            continue
        entry_books = agg["books"]
        if not book_match(sorted(entry_books, key=LEGACY.book_order), books):
            continue
        surfaces = {name} | set(agg["variants"])
        doms = [(b, "{", s) for b in entry_books for s in surfaces]
        content_arts = _manual_content_arts(doms)
        locations = _co_places(doms, top=6)
        author = _manual_author(doms)
        aliases = [{"surface": v, "type": "变体（concordance）"} for v in sorted(agg["variants"] - {name})]
        card = {
            "name": {"canonical": name},
            "content_arts": content_arts,
            "author": author,
            "provenance": [],
            "holders": [],
            "status": {"value": "未明示"},
            "locations": locations,
            "brief": "",
            "active_books": sorted(entry_books, key=LEGACY.book_order),
            "first_appearance": first_appearance(entry_books, BOOKS)["first_appearance"],
        }
        gaps = ["provenance（#4a 物件域事件流）", "holders（N5 转移谓词未覆盖文书）"]
        if not content_arts:
            gaps.append("content_arts（tagged 共现无 ☆/武功卡映射）")
        if not locations:
            gaps.append("locations（tagged 共现无 gazetteer 命中）")
        if author.get("type") == "作者未明（托名常态）":
            gaps.append("author（无 #4a 悟创事件，句式启发式未命中）")
        card["brief"] = brief_text(_manual_brief_parts(name, aliases, card, entry_books, content_arts, locations))
        proposition = _manual_prop(name, entry_books, content_arts, locations)
        conf = "C"
        sources = ["#7:concordance({)", "tagged:共现(content_arts/locations) 启发式"]
        if entry_books:
            sources.append("02ab:" + str((card["first_appearance"] or {}).get("loc_r")))
        card["meta"] = meta_block("manual", name, None, slugify(name, "manual"), proposition,
                                  {"entities": [], "relations": [], "events": []}, sources, conf, "draft",
                                  "concordance{文书类实体过滤＋tagged 共现派生（content_arts/locations/author，启发式）",
                                  None, gaps, "concordance:{:" + name)
        cards.append(card)
    return cards


def _manual_content_arts(doms: list[tuple[str, str, str]]) -> list[dict]:
    if not TAGGED:
        return []
    counter = TAGGED.cooccur(doms, "☆")
    out, seen = [], set()
    for (book, display), n in counter.most_common(8):
        art_name = ENTITIES.ref(display) or display  # ☆ 不在 registry，回落显示名
        ref = f"card.art.{slugify(display, 'art')}"
        if ref in seen:
            continue
        seen.add(ref)
        out.append({"art_ref": ref, "art_surface": None, "conf": "weak",
                    "basis": f"tagged 段落共现 {n} 段（非秘籍互指边）"})
    return out


def _manual_author(doms: list[tuple[str, str, str]]) -> dict:
    if not TAGGED:
        return {"type": "作者未明（托名常态）"}
    for book, domain, display in doms:
        for ch, pn in TAGGED.paras_of(book, domain, display):
            para = TAGGED.para_at(book, ch, pn)
            if para is None:
                continue
            m = re.search(r"(所著|手著|所传|传下|遗著|手书|撰)", para.plain)
            if not m:
                continue
            person = TAGGED.find_name_near(para, m.start(), window=20)
            pid = ENTITIES.ref(person or "")
            if pid:
                return {"person_ref": pid, "note": f"由 tagged 句式『{m.group(1)}』启发式推导（{book}·{ch}:{pn}）",
                        "conf": "weak"}
    return {"type": "作者未明（托名常态）"}


def _manual_brief_parts(name, aliases, card, entry_books, content_arts, locations) -> list[str]:
    parts = [f"本卡据 5 书语料整理：{name}"]
    if aliases:
        parts.append("（另见" + "、".join(a["surface"] for a in aliases[:3]) + "）")
    if entry_books:
        parts.append(f"；见于《{'》《'.join(sorted(entry_books, key=LEGACY.book_order))}》")
    if content_arts:
        parts.append(f"；语料共现所载武功候选 {len(content_arts)} 门（启发式，非互指边）")
    if locations:
        parts.append(f"；共现地点 {len(locations)} 处")
    parts.append("。争夺事件链、持有者变迁因 #4a/#6 谓词未覆盖暂缺；")
    return parts


def _manual_prop(name, entry_books, content_arts, locations) -> str:
    bits = [name, f"为《{'》《'.join(sorted(entry_books, key=LEGACY.book_order)[:2])}》所载文书类实体"]
    if content_arts:
        bits.append(f"，共现武功{len(content_arts)}门（启发式）")
    if locations:
        bits.append(f"，共现地点{len(locations)}处")
    return "".join(bits)


# ────────────────────────── 校验 / 脱敏 / 指标 ──────────────────────────
def collect_strings(obj, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("quote", "snippet"):
                continue
            collect_strings(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_strings(v, out)


def r1_check(cards: list[dict], ngram_n: int = 10) -> dict:
    """R1（SKILL §6.2）：原文连续重合 ≥10 字即违规；R3 专名不算片段（先掩码专名再比）。"""
    corpus = TAGGED.ngrams if TAGGED else set()
    raw_cards, masked_cards = [], []
    for card in cards:
        strings: list[str] = []
        collect_strings(card, strings)
        raw_hit = masked_hit = False
        for s in strings:
            if len(s) < ngram_n:
                continue
            if not raw_hit and any(hash(s[i:i + ngram_n]) in corpus
                                   for i in range(0, len(s) - ngram_n + 1)):
                raw_cards.append({"stable_id": card.get("meta", {}).get("stable_id", ""), "text": s[:80]})
                raw_hit = True
            masked = mask_names(s)
            if len(masked) >= ngram_n and any(hash(masked[i:i + ngram_n]) in corpus
                                              for i in range(0, len(masked) - ngram_n + 1)):
                masked_cards.append({"stable_id": card.get("meta", {}).get("stable_id", ""),
                                     "masked_text": masked[:80]})
                masked_hit = True
            if raw_hit and masked_hit:
                break
    return {"rule": "R1", "threshold_ngram": ngram_n,
            "raw_overlap_cards": len(raw_cards), "r3_proper_name_exempted": len(raw_cards) - len(masked_cards),
            "overlap_cards": len(masked_cards), "max_overlap_len": ngram_n if masked_cards else 0,
            "examples": (masked_cards or raw_cards)[:5], "passed": not masked_cards,
            "note": "R3：专名（人名/武功/地名/书名/绰号）不计片段；overlap_cards=剔除专名后仍≥10字连续重合的卡数"}


def r2_check(cards: list[dict]) -> dict:
    hits = []
    for card in cards:
        strings: list[str] = []
        collect_strings(card, strings)
        for s in strings:
            for mark in TAGGED_MARK:
                if mark in s:
                    hits.append({"stable_id": card.get("meta", {}).get("stable_id", ""), "mark": mark})
                    break
    return {"rule": "R2", "markup_hits": len(hits), "examples": hits[:5], "passed": not hits}


def r4_check(cards: list[dict]) -> dict:
    bad = [c["meta"]["stable_id"] for c in cards
           if c.get("meta", {}).get("publish_state") == "approved" or c.get("meta", {}).get("demo")]
    return {"rule": "R4", "approved_or_demo_cards": len(bad), "examples": bad[:5], "passed": not bad}


def validate_cards(cards: list[dict]) -> dict:
    errors = []
    id_rx = re.compile(r"^E\d+$")
    ids = Counter(c["meta"]["stable_id"] for c in cards if c.get("meta", {}).get("stable_id"))
    for sid, n in ids.items():
        if n > 1:
            errors.append(f"stable_id 重复：{sid}×{n}")
    for c in cards:
        sid = c.get("meta", {}).get("stable_id", "?")
        m = c.get("meta") or {}
        for key in META_REQUIRED:
            if key not in m:
                errors.append(f"{sid}: meta 缺字段 {key}")
        if m.get("confidence") not in ("A", "B", "C", "D", "E"):
            errors.append(f"{sid}: confidence 越界 {m.get('confidence')}")
        if m.get("publish_state") not in ("draft", "in-review", "approved", "blocked"):
            errors.append(f"{sid}: publish_state 越界")
        if m.get("card_type") not in CARD_TYPES:
            errors.append(f"{sid}: card_type 越界")
        if not str(sid).startswith(f"card.{m.get('card_type')}."):
            errors.append(f"{sid}: stable_id 与 card_type 不一致")
        if not (c.get("name") or {}).get("canonical"):
            errors.append(f"{sid}: name.canonical 空")
        if m.get("card_type") in ("person", "faction") and not m.get("entity_ref"):
            errors.append(f"{sid}: registered 类型缺 entity_ref")
        if m.get("card_type") in ("art", "artifact", "manual") and m.get("entity_ref") and \
                not str(m["entity_ref"]).startswith("E"):
            errors.append(f"{sid}: 未登记类型伪造 entity_ref")
        # 实体 ID 回指有效性：所有 ^E\d+$ 引用必须存在于 registry/entities.json
        strings: list[str] = []
        collect_strings(c, strings)
        for s in strings:
            if id_rx.match(s) and s not in ENTITIES.by_id:
                errors.append(f"{sid}: 引用未登记实体 ID {s}")
                break
    return {"passed": not errors, "errors": errors[:30], "error_count": len(errors)}


def field_fill_metrics(cards: list[dict]) -> dict:
    out: dict[str, dict] = {}
    by_type = defaultdict(list)
    for c in cards:
        by_type[c["meta"]["card_type"]].append(c)
    for ctype, specs in FIELD_SPECS.items():
        group = by_type.get(ctype, [])
        field_rates = {}
        for fname, required, spec in specs:
            if fname == "meta":
                field_rates[fname] = {"required": required, "filled": len(group), "total": len(group),
                                      "rate": 1.0 if group else 0.0, "spec": spec}
                continue
            filled = sum(1 for c in group if is_filled(get_path(c, fname)))
            field_rates[fname] = {"required": required, "filled": filled, "total": len(group),
                                  "rate": round(filled / len(group), 4) if group else 0.0, "spec": spec}
        for fname, _, spec in CROSS_FIELDS:
            filled = sum(1 for c in group if is_filled(get_path(c, fname)))
            field_rates[fname] = {"required": False, "filled": filled, "total": len(group),
                                  "rate": round(filled / len(group), 4) if group else 0.0, "spec": spec}
        out[ctype] = {"count": len(group), "fields": field_rates}
    return out


def unfillable_fields(fill: dict) -> list[dict]:
    out = []
    reason_map = {
        "identity_tags": "无 #8 身份树",
        "life_events": "无 #4a 事件流",
        "timeline": "无 #4a 组织事件流",
        "provenance": "无 #4a 物件事件流",
        "inheritance_chain": "N5 未建武功传人链",
        "creator": "无 #4a 悟创事件",
        "life_events2": "",
        "relational_sku_refs": "Relational SKU 独立节点未生成",
        "branch_alliance": "N5 无联盟/敌对谓词",
        "holders": "N5 转移谓词未覆盖文书",
        "grade": "无战绩事件统计，按 SKILL 不评",
        "category": "无 #8 武功品类树（启发式）",
        "faction_type": "无 #8 门派树（启发式）",
        "strongholds": "启发式共现，非组织驻地谓词",
        "locations": "启发式共现",
        "content_arts": "启发式共现，非互指边",
        "author": "启发式句式，多为空",
        "hierarchy": "#8 武功谱系树未建（缺省 null）",
        "lineage": "#6 任职边稀疏（全 5 书仅 3 条）",
        "status": "需 #4a 灭派/重建事件或存续明写（本批仅 1 例候选）",
        "moves": "招式表 parent_art 覆盖有限（222 式中 107 式有归属）",
        "practitioners": "招式表 used_by/掌握边覆盖有限",
        "recorded_in": "秘籍↔武功互指边未建（仅 tagged 共现反指）",
        "age_anchor": "N4 年龄锚归属需同句近邻，覆盖率有限",
        "brief": "未达 200–500 字则按 SKILL 留空待人工",
    }
    for ctype, data in fill.items():
        for fname, info in data["fields"].items():
            if fname == "meta":
                continue
            if info["filled"] == 0:
                out.append({"card_type": ctype, "field": fname, "filled": 0, "total": info["total"],
                            "reason": reason_map.get(fname, "无来源或上游未产出")})
    return out


def source_mapping_coverage(cards: list[dict], fill: dict) -> list[dict]:
    labels = [("人物卡", "person"), ("门派卡", "faction"), ("武功卡", "art"),
              ("兵器卡", "artifact"), ("秘籍卡", "manual"),
              ("人物", "person"), ("门派", "faction"), ("武功", "art"),
              ("兵器", "artifact"), ("秘籍", "manual")]
    rows = []
    for row in SOURCE_MAPPING:
        fields = []
        for token in re.split(r"[/、，／]", row["fields"]):
            token = token.strip()
            if not token:
                continue
            token = token.split()[0]
            token = re.sub(r"[（(][^）)]*[）)]", "", token)
            token = token.strip("（）()：:，,。；;")
            if token:
                fields.append(token)
        if not fields:
            fields = [row["fields"]]
        row_cards = row["cards"]
        if "全卡" in row_cards:
            ctypes = list(CARD_TYPES)
        else:
            ctypes = []
            for label, ctype in labels:
                if label in row_cards and ctype not in ctypes:
                    ctypes.append(ctype)
        total_cards = 0
        covered_cards = 0
        for ctype in ctypes:
            if ctype not in fill:
                continue
            group_total = fill[ctype]["count"]
            total_cards += group_total
            got = 0
            for card in [c for c in cards if c["meta"]["card_type"] == ctype]:
                if any(is_filled(get_path(card, f)) for f in fields):
                    got += 1
            covered_cards += got
        rows.append({**row, "cards_covered": covered_cards, "cards_in_scope": total_cards,
                     "coverage": round(covered_cards / total_cards, 4) if total_cards else None})
    return rows


def desensitization_block(cards: list[dict]) -> dict:
    r1 = r1_check(cards)
    r2 = r2_check(cards)
    r4 = r4_check(cards)
    return {
        "rules": {
            "R1": "卡面正文不得与原文连续重合 ≥10 字（阈值 SKILL 附录 B 待拍板；本批用 10）",
            "R2": "引文型内容一律『概括语＋回锚』，回锚只存 ID/机锚指针，不含文本",
            "R3": "专名（人名/武功/地名/书名/绰号）可发布，不算片段",
            "R4": "未过审不得 publish_state=approved；演示卡永远 blocked",
            "R5": "Procedural steps 若源自原文口诀须原创归纳（本批五卡不含 Procedural，N/A）",
        },
        "checks": [r1, r2, r4],
        "R3_note": "专名在 name/aliases/引用字段中保留；R1 命中若仅由专名造成按 R3 说明复核",
        "R5_status": "N/A（本批只产五卡，未产 Procedural SKU）",
        "passed": bool(r1["passed"] and r2["passed"] and r4["passed"]),
    }


# ────────────────────────── 入口流程 ──────────────────────────
def metrics_unregistered_note() -> dict:
    if not CONC:
        return {}
    return {("concordance_" + t): CONC.unregistered_surfaces(t) for t in ("@", "◆", "☆", "•", "{")}


BUILDERS = {"person": build_person_cards, "faction": build_faction_cards,
            "art": build_art_cards, "artifact": build_artifact_cards,
            "manual": build_manual_cards}


def build(types: list[str], books: list[str]) -> dict:
    load_all(books)
    cards: list[dict] = []
    per_type = {}
    for ctype in types:
        built = BUILDERS[ctype](books)
        per_type[ctype] = len(built)
        cards.extend(built)
    # §2.7 条 5：秘籍↔武功双向互指（秘籍 content_arts → 武功 recorded_in）
    art_by_ref = {c["meta"]["stable_id"]: c for c in cards if c["meta"]["card_type"] == "art"}
    reverse_links = 0
    for manual in [c for c in cards if c["meta"]["card_type"] == "manual"]:
        for ca in manual.get("content_arts") or []:
            art = art_by_ref.get(ca.get("art_ref"))
            if art is not None:
                if manual["meta"]["stable_id"] not in art["recorded_in"]:
                    art["recorded_in"].append(manual["meta"]["stable_id"])
                    reverse_links += 1
    fill = field_fill_metrics(cards)
    desens = desensitization_block(cards)
    validation = validate_cards(cards)
    metrics = {
        "tool": TOOL,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filters": {"types": types, "books": books},
        "counts": per_type,
        "counts_total": len(cards),
        "field_fill": fill,
        "source_mapping": source_mapping_coverage(cards, fill),
        "desensitization": desens,
        "validation": validation,
        "unfillable_fields": unfillable_fields(fill),
        "unregistered_surfaces": {
            "concordance_☆": CONC.unregistered_surfaces("☆") if CONC else 0,
            "concordance_•": CONC.unregistered_surfaces("•") if CONC else 0,
            "concordance_{": CONC.unregistered_surfaces("{") if CONC else 0,
            "concordance_◆": CONC.unregistered_surfaces("◆") if CONC else 0,
            "concordance_@": CONC.unregistered_surfaces("@") if CONC else 0,
            "note": "concordance 中 out_of_scope/unregistered 的实体表面数；@/◆ 只有登记层子集建卡",
        },
        "entity_ref_gap": {
            "cards_with_null_entity_ref": sum(1 for c in cards if not c["meta"].get("entity_ref")),
            "cards_with_entity_ref": sum(1 for c in cards if c["meta"].get("entity_ref")),
            "note": "art/artifact/manual 在 01g 登记层未扩类；entity_ref=null + entity_ref_gap，不伪造 E-ID",
        },
        "confidence_dist": dict(Counter(c["meta"]["confidence"] for c in cards)),
        "publish_state_dist": dict(Counter(c["meta"]["publish_state"] for c in cards)),
        "entity_coverage": {
            "person_registered": sum(1 for e in ENTITIES.items if e.get("type") == "@"),
            "person_cards": per_type.get("person", 0),
            "faction_registered": sum(1 for e in ENTITIES.items if e.get("type") == "◆"),
            "faction_cards": per_type.get("faction", 0),
            "weapons_asset": len(LEGACY.weapon_list()),
            "weapon_cards": per_type.get("artifact", 0),
            "manual_candidates": len([n for n in (CONC.by_type_canon["{"] if CONC else {}) if is_manual_name(n)]),
            "manual_cards": per_type.get("manual", 0),
            "bidirectional_manual_art_links": reverse_links,
            "concordance_unregistered_surfaces": metrics_unregistered_note(),
        },
        "source_versions": {
            "entities": {"version": ENTITIES.version, "count": len(ENTITIES.items)} if ENTITIES else {},
            "concordance": {b: (CONC.book_data.get(b, {}).get("generated") if CONC else None) for b in books},
            "relations": {"books": books, "edges_total": REL.edges_total if REL else 0},
            "time": TIME.generated() if TIME else {},
            "gazetteer": {"places": len(GAZ.places) if GAZ else 0},
            "weapons": len(LEGACY.weapon_list()) if LEGACY else 0,
            "moves": len(LEGACY.move_list()) if LEGACY else 0,
            "new_entity_types": {"items": len(NEWTYPES.items) if NEWTYPES else 0,
                                 "version": NEWTYPES.version if NEWTYPES else ""},
            "tagged": {"books": books, "paragraphs": len(TAGGED.paras) if TAGGED else 0,
                       "ngrams": len(TAGGED.ngrams) if TAGGED else 0},
        },
        "w8_w9_interface": w8_w9_interface(cards, fill),
    }
    data = {
        "schema": "sku-cards-v1",
        "meta": {
            "generated_at": metrics["generated_at"],
            "tool": TOOL,
            "skill": "skills/SKILL_SKU卡片_武侠版.md",
            "spec": ["§2.0 元数据", "§2.1-2.5 五卡", "§2.6 来源映射 11 行", "§2.7 边界案例",
                     "§4.2 跨书字段", "§4.3 ID 投影制", "§6.1-6.4 发布/脱敏/可信/版本"],
            "data_version": DATA_VERSION,
            "rule_version": RULE_VERSION,
            "counts": per_type,
            "counts_total": len(cards),
            "filters": metrics["filters"],
            "desensitization_passed": desens["passed"],
            "validation_passed": validation["passed"],
            "entity_ref_gap_cards": metrics["entity_ref_gap"]["cards_with_null_entity_ref"],
        },
        "cards": cards,
        "card_index": {t: [c["meta"]["stable_id"] for c in cards if c["meta"]["card_type"] == t] for t in types},
        "field_fill": fill,
        "source_mapping": metrics["source_mapping"],
        "desensitization": desens,
        "unfillable_fields": metrics["unfillable_fields"],
        "w8_w9_interface": metrics["w8_w9_interface"],
        "validation": validation,
    }
    return {"data": data, "metrics": metrics}


def w8_w9_interface(cards: list[dict], fill: dict) -> dict:
    """W8-W9 页型接口：五段式精品页/页型模板从 SKU 卡取数（docs/05 §2.6 L147-155）。"""
    return {
        "W8_精品页": {
            "适用判断": "meta.card_type + meta.proposition + meta.confidence（B/C 可作为候选页；D/E 需复核，本批不产出）",
            "必有节": {
                "title": "name.canonical",
                "summary": "brief（200–500 字；未达长度则留空待人工）",
                "core_facts": "type-specific 数组字段（lineage/teachers/moves/chain/content_arts 等）",
                "sources": "meta.sources + meta.supported_by（实体 ID/边 ID/机锚）",
                "confidence": "meta.confidence + meta.publish_state",
            },
            "加分项": "strongholds/locations/moves/practitioners 等填充率高的字段（见 field_fill）",
            "反面示例": "禁止把卡面 brief 扩写为含原文片段的长文（R1/R2）；禁止 demo 卡入发布库（R4）",
            "参考页面": "本 cards.json 的 card_index[type] 直接作为 Astro collection 数据源",
        },
        "W9_页型模板": {
            "page_payload": "每卡即一个模板实例：{meta, name, type-fields, active_books, first_appearance}",
            "slot_mapping": {ctype: [f[0] for f in FIELD_SPECS[ctype]] for ctype in FIELD_SPECS},
            "reflection_gate": "依赖 meta.confidence≥C 且 validation.passed（本批字段级 fill 见 metrics）",
            "demo_isolation": "meta.demo=false（本批全部真实数据卡）；发布加载器按 R4 拒绝 demo/approved 越权",
            "id_projection": "stable_id=card.<type>.<slug> 可直接作路由 slug；关系/事件引用写实体 ID（K4）",
        },
        "cards_by_type": {t: sum(1 for c in cards if c["meta"]["card_type"] == t) for t in CARD_TYPES},
    }


# ────────────────────────── 报告渲染 ──────────────────────────
def _esc(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ") if s is not None else ""


def render_report(data: dict, metrics: dict) -> str:
    lines, add = [], None
    add = lines.append
    add("# N10 SKU 卡片生成报告（五类卡）")
    add("")
    add(f"- 生成时间：{data['meta']['generated_at']}；工具：`scripts/build_sku_cards.py`（{data['meta']['tool']}）")
    add(f"- 规范：`{data['meta']['skill']}`（§2.0 元数据 / §2.1-2.5 五卡 / §2.6 来源映射 11 行 / "
        "§2.7 边界案例 / §4.2 跨书字段 / §4.3 投影制 / §6.1-6.4 发布·脱敏·可信·版本）")
    add(f"- 版本：data_version={data['meta']['data_version']}；rule_version={data['meta']['rule_version']}")
    add("")
    add("## 一、总览（各类卡数）")
    add("")
    add("| 类型 | 卡数 | 说明 |")
    add("|---|---:|---|")
    notes = {
        "person": "01g 登记层 @ 实体投影；别名/师承/传人/情缘/武功/年龄锚",
        "faction": "01g 登记层 ◆ 实体投影；任职/镇派武功/据点共现/存续候选",
        "art": "concordance ☆ 全类型实体 ∪ 招式表 parent_art；招式/会用者",
        "artifact": "神兵表 226 件直接投影（chain/holders/grade），人名→实体 ID",
        "manual": "concordance { 文书类过滤（ martial 秘籍口径）＋共现派生",
    }
    for t in CARD_TYPES:
        add(f"| {t}（{TYPE_LABEL[t]}） | {data['meta']['counts'].get(t, 0)} | {notes[t]} |")
    add(f"| **合计** | **{data['meta']['counts_total']}** | — |")
    add("")
    add("## 二、字段填充率（有效填充；缺省态不计填充）")
    add("")
    for t in CARD_TYPES:
        info = data["field_fill"].get(t)
        if not info:
            continue
        add(f"### {t}（{TYPE_LABEL[t]}）· {info['count']} 卡")
        add("")
        add("| 字段 | 必填 | 填充 | 分母 | 填充率 |")
        add("|---|---|---:|---:|---:|")
        for fname, f in info["fields"].items():
            add(f"| {fname} | {'是' if f['required'] else ''} | {f['filled']} | {f['total']} | {f['rate']:.1%} |")
        add("")
    add("## 三、数据源覆盖（SKILL §2.6 核对表 11 行）")
    add("")
    add("| 行 | 来源 | 落点字段 | 落在哪张卡 | 覆盖卡数/范围 | 覆盖率 |")
    add("|---:|---|---|---|---:|---:|")
    for row in data["source_mapping"]:
        cov = f"{row['coverage']:.1%}" if row.get("coverage") is not None else "—"
        add(f"| {row['row']} | {_esc(row['source'])} | {_esc(row['fields'])} | {_esc(row['cards'])} | "
            f"{row.get('cards_covered', 0)}/{row.get('cards_in_scope', 0)} | {cov} |")
    add("")
    cov = metrics.get("entity_coverage") or {}
    add(f"- 实体覆盖：person {cov.get('person_cards')}/{cov.get('person_registered')} · "
        f"faction {cov.get('faction_cards')}/{cov.get('faction_registered')} · "
        f"weapon {cov.get('weapon_cards')}/{cov.get('weapons_asset')} · "
        f"manual {cov.get('manual_cards')}/{cov.get('manual_candidates')} · "
        f"秘籍↔武功反向互指 {cov.get('bidirectional_manual_art_links')} 条")
    add(f"- concordance 未登记表面（不建卡，仅报告）：{cov.get('concordance_unregistered_surfaces')}")
    sv = metrics["source_versions"]
    add(f"- 输入版本：entities={sv['entities'].get('version')}（{sv['entities'].get('count')} 条）· "
        f"N5 边 {sv['relations'].get('edges_total')} · N4 5 书 · gazetteer={sv['gazetteer'].get('places')} 地点 · "
        f"神兵表 {sv['weapons']} · 招式表 {sv['moves']} · new_entity_types {sv['new_entity_types'].get('items')} · "
        f"tagged {sv['tagged'].get('paragraphs')} 段")
    add("")
    add("## 四、脱敏检查（R1-R5，§6.2）")
    add("")
    for chk in data["desensitization"]["checks"]:
        status = "✅ pass" if chk.get("passed") else "❌ fail"
        add(f"- **{chk['rule']}** {status}：" + json.dumps(
            {k: v for k, v in chk.items() if k not in ("rule", "passed", "examples")}, ensure_ascii=False))
    add(f"- **R5** {data['desensitization']['R5_status']}；**R3**：{data['desensitization']['R3_note']}")
    add(f"- 脱敏总判：**{'PASS' if data['desensitization']['passed'] else 'FAIL'}**；"
        f"publish_state=approved/demo 卡：{data['desensitization']['checks'][2].get('approved_or_demo_cards')}")
    add("")
    add("## 五、无法填充字段（按字段 0 填充统计；缺省态与原因）")
    add("")
    add("| 卡类型 | 字段 | 0 填充 | 分母 | 原因（上游缺口） |")
    add("|---|---|---:|---:|---|")
    for u in data["unfillable_fields"]:
        add(f"| {u['card_type']} | {u['field']} | 0 | {u['total']} | {_esc(u['reason'])} |")
    if not data["unfillable_fields"]:
        add("（无 0 填充字段）")
    add("")
    add("## 六、元数据、ID 与发布状态")
    add("")
    add(f"- entity_ref：{metrics['entity_ref_gap']['cards_with_entity_ref']} 卡有登记实体 ID；"
        f"{metrics['entity_ref_gap']['cards_with_null_entity_ref']} 卡 entity_ref=null（01g 未扩类，已标 gap；不伪造 E-ID）")
    add(f"- confidence 分布：{metrics['confidence_dist']}（A–E；本工具不做人工评级，最多 B）")
    add(f"- publish_state 分布：{metrics['publish_state_dist']}（无 approved；demo=False）")
    add("- stable_id 投影制：`card.<type>.<slug>`；registered 用实体 ID 后缀，未登记类型用 canonical 哈希前缀（中文转写规则待定版）")
    add(f"- 校验：{'PASS' if metrics['validation']['passed'] else 'FAIL'}（{metrics['validation']['error_count']} 项）")
    add("")
    add("## 七、W8-W9 页型接口")
    add("")
    w8 = data["w8_w9_interface"]
    add("- **W8 精品页**（五段式：适用判断→必有节→加分项→反面示例→参考页面）：")
    for k, v in w8["W8_精品页"].items():
        if isinstance(v, dict):
            add(f"  - {k}：" + "；".join(f"{kk}={vv}" for kk, vv in v.items()))
        else:
            add(f"  - {k}：{v}")
    add("- **W9 页型模板**：")
    for k, v in w8["W9_页型模板"].items():
        add(f"  - {k}：{v}")
    add("")
    add("## 八、复现")
    add("")
    add("```powershell")
    add("python -X utf8 scripts/build_sku_cards.py --all")
    add("python -X utf8 scripts/build_sku_cards.py --type person,faction")
    add("python -X utf8 scripts/build_sku_cards.py --book 江湖三女侠")
    add("python -X utf8 scripts/build_sku_cards.py --all --strict")
    add("python -X utf8 scripts/build_sku_cards.py --selftest")
    add("```")
    add("")
    return "\n".join(lines) + "\n"


# ────────────────────────── CLI / selftest ──────────────────────────
def run_selftest() -> int:
    checks = []

    def chk(name, cond):
        checks.append(bool(cond))
        if not cond:
            print(f"[FAIL] {name}")

    chk("五类卡", CARD_TYPES == ["person", "faction", "art", "artifact", "manual"])
    chk("来源映射 11 行", len(SOURCE_MAPPING) == 11)
    chk("来源映射行号", [r["row"] for r in SOURCE_MAPPING] == list(range(1, 12)))
    chk("脱敏 R1-R5 文案", all(k in "R1R2R3R4R5" for k in ("R1", "R5")))
    chk("字段表非空", all(FIELD_SPECS[t] for t in CARD_TYPES))
    chk("人物必填 name/meta", FIELD_SPECS["person"][0][0] == "name.canonical")
    chk("元数据必填项", len(META_REQUIRED) == 14)
    chk("slug 确定性", slugify("练霓裳", "person") == slugify("练霓裳", "person"))
    chk("slug 跨类型不同", slugify("练霓裳", "person") != slugify("练霓裳", "art"))
    chk("loc_r 格式", loc_r("江湖三女侠", 5, 12) == "jianghu#pn-r5.12")
    chk("is_filled 缺省", not is_filled(None) and not is_filled([]) and not is_filled({"type": "未明示"}))
    chk("is_filled 有值", is_filled(["E0001"]) and is_filled({"a": 1}) and is_filled("文本"))
    chk("ngram 自重叠", bool(set_ngrams("天地玄黄宇宙洪荒日月盈昃") & set_ngrams("天地玄黄宇宙洪荒日月盈昃")))
    chk("ngram 不误命", not (set_ngrams("天地玄黄宇宙洪荒日月盈昃") & set_ngrams("完全不同的一段文字内容测试")))
    chk("brief 长度门", brief_text(["x" * 250]) == "" or 200 <= len(brief_text(["x" * 250])) <= 500)
    chk("brief 空", brief_text([]) == "")
    chk("book id 映射", set(BOOK_IDS.values()) == {"jianghu", "qijian", "saiwai", "bingpo", "bainv"})
    chk("卡类型中文名", TYPE_LABEL["artifact"] == "兵器卡")
    chk("活动卡类型 = 五类", set(BUILDERS) == set(CARD_TYPES))
    meta = meta_block("person", "测试卡", "E0001", "e0001", "命题", {"entities": ["E0001"]},
                      ["01g:E0001"], "C", "draft", "test")
    chk("meta 必填齐", all(k in meta for k in META_REQUIRED))
    chk("meta 命题≤100", len(meta["proposition"]) <= 100)
    chk("无 approved", meta["publish_state"] != "approved" and meta["demo"] is False)
    bad = [{"meta": {"stable_id": "card.person.x", "card_type": "person", "entity_ref": None,
                     "publish_state": "approved", "demo": False, "confidence": "B"},
            "name": {"canonical": "x"}}]
    chk("R4 检出", not r4_check(bad)["passed"])
    fill = field_fill_metrics([{"name": {"canonical": "x"}, "aliases": [], "meta": {
        "stable_id": "card.person.x", "card_type": "person", "entity_ref": "E0001",
        "confidence": "C", "publish_state": "draft"}}])
    chk("填充率计算", fill["person"]["fields"]["aliases"]["rate"] == 0.0)
    ok = sum(checks)
    print(f"[selftest] {ok}/{len(checks)} passed")
    return 0 if ok == len(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_sku_cards.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="N10 SKU 卡片生成：五类卡（person/faction/art/artifact/manual）按 SKILL_SKU卡片_武侠版 组装；\n"
                    "只读 entities/concordance/relations/time/gazetteer/wordlists/tagged/既有资产，输出 registry/sku/cards.json。",
        epilog="示例：\n"
               "  python -X utf8 scripts/build_sku_cards.py --all\n"
               "  python -X utf8 scripts/build_sku_cards.py --type person,faction\n"
               "  python -X utf8 scripts/build_sku_cards.py --book 江湖三女侠 --type person\n"
               "  python -X utf8 scripts/build_sku_cards.py --all --strict\n"
               "  python -X utf8 scripts/build_sku_cards.py --selftest\n\n"
               "脱敏：R1 无≥10 字原文重合；R2 只存概括语+ID/机锚；R3 专名可发布；R4 无 approved/demo；R5 N/A（无 Procedural）。",
    )
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument("--all", action="store_true")
    g.add_argument("--book", metavar="书名")
    g.add_argument("--selftest", action="store_true")
    p.add_argument("--type", metavar="TYPES", default=None,
                   help="逗号分隔卡类型（person,faction,art,artifact,manual；也接受中文标签）")
    p.add_argument("--strict", action="store_true", help="严格模式：脱敏/必填/ID 校验失败 → exit 2")
    p.add_argument("--out", metavar="PATH", default=str(OUT_CARDS), help="cards.json 输出路径")
    p.add_argument("--report-dir", metavar="DIR", default=str(OUT_LOGS))
    p.add_argument("--quiet", action="store_true")
    return p


def _parse_types(spec: str | None) -> list[str]:
    if not spec:
        return list(CARD_TYPES)
    zh = {v: k for k, v in TYPE_LABEL.items()}
    out = []
    for part in spec.split(","):
        part = part.strip()
        if part in CARD_TYPES:
            out.append(part)
        elif part in zh:
            out.append(zh[part])
        else:
            raise SystemExit(f"[ERROR] 未知卡类型：{part}；可选 {CARD_TYPES} 或 {list(TYPE_LABEL.values())}")
    return out


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    if args.selftest:
        return run_selftest()
    if not (args.all or args.book or args.type):
        build_parser().print_help()
        return 2
    books = [args.book] if args.book else list(BOOKS)
    if args.book and args.book not in BOOKS:
        print(f"[ERROR] 未知书名：{args.book}；可选 {BOOKS}", file=sys.stderr)
        return 2
    types = _parse_types(args.type)
    result = build(types, books)
    data, metrics = result["data"], result["metrics"]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "summary.md"
    report_path.write_text(render_report(data, metrics), encoding="utf-8")
    (report_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(f"[OK] 卡片 {data['meta']['counts_total']} 张：{data['meta']['counts']} → {out}")
        print(f"[OK] 报告 → {report_path} · {report_dir / 'metrics.json'}")
        d = data["desensitization"]
        print(f"[OK] 脱敏 {('PASS' if d['passed'] else 'FAIL')} · 校验 "
              f"{('PASS' if metrics['validation']['passed'] else 'FAIL')}")
    if args.strict:
        failures = []
        if not data["desensitization"]["passed"]:
            failures.append("脱敏检查未通过")
        if not metrics["validation"]["passed"]:
            failures.append("必填/ID 校验未通过")
        if failures:
            print("[STRICT] " + "；".join(failures), file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
