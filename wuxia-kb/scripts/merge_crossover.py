# -*- coding: utf-8 -*-
"""N6 · 跨书归并工作台（merge_crossover）—— docs/17 §2.3 / D07 跨书治理。

定位：只产候选 + 证据分级 + 双人复核队列，**不自动合并 registry、不写 tagged**。
输入（只读）：
  * skills/SKILL_跨书治理_武侠版.md 的规则（同一性证据 E1-E4 / 权威 L1-L4 /
    双层 canonical / bare B0-B8 / 双人复核门槛）在本脚本内以可审计的确定性规则实现；
  * registry/entities.json（跨书登记层，452 条）；
  * registry/concordance/<书>.json（5 书：书内 canonical / variants / registration）；
  * kb/系列谱系考订表.json（22 interchange_seeds，人工考订接力边+回指+编年三证）；
  * kb/互文引用表.json（authorial 98 / quoted 31 / bare 1775）；
  * kb/作品元数据表.json（series / era / leads）；kb/神兵表.json、kb/门派世系表.json（bare B1 转移用）；
  * logs/mapping_<书>/ch_*.json（本书已核准映射快照，取最后一回累积快照）。
输出：
  * registry/crossover/merge_candidates.json（候选 + 证据 + 建议动作 + 复核状态）
  * registry/crossover/review_queue.md（双人复核队列 + 状态机 + 逐候选证据卡）
  * logs/crossover/merge_crossover_<ts>.md（运行报告）与 summary.json

CLI：
  python scripts/merge_crossover.py --all [--strict] [--series [NAME]]
  python scripts/merge_crossover.py --selftest
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config  # noqa: E402

SPEC_VERSION = "n6-v1.0"
DEFAULT_BOOKS = ["白发魔女传", "江湖三女侠", "七剑下天山", "塞外奇侠传", "冰魄寒光剑"]
IN_SCOPE_TYPES = {"@", "◆", "&"}                 # D07 §4.6：强/中治理（人物/组织/家族）
TYPE_LABEL = {"@": "人物", "◆": "组织", "&": "家族"}
GRADE_ORDER = {"E1": 0, "E2": 1, "E3": 2, "E4": 3}
GRADE_CONF = {"E1": "strong", "E2": "strong", "E3": "ok", "E4": "todo"}
GRADE_AUTHORITY = {"E1": "L1", "E2": "L3", "E3": "governance", "E4": "todo"}
ACTION_BY_GRADE = {"E1": "merge", "E2": "merge", "E3": "proposal", "E4": "proposal"}
MERGE_ALLOWED = {"E1": True, "E2": True, "E3": True, "E4": False}
REVIEW_REQUIRED = {"E1": False, "E2": True, "E3": True, "E4": False}  # E4 不进归并（D07 §8.2）
REVIEW_SAMPLING = {"E1": "抽验 5%（D07 §8.2）", "E2": "全量双人", "E3": "全量双人",
                   "E4": "不进归并（仅候选池）"}

# 时代依赖通称：不得作为跨书同人归并依据（task-8/task-11 的教训；只登记不归并）
ERA_GENERIC = {
    "皇上", "皇帝", "圣上", "万岁", "今上", "陛下", "先帝", "太后", "皇太后", "贵妃",
    "娘娘", "太子", "王爷", "大人", "老爷", "公子", "姑娘", "女侠", "少侠", "师父",
    "师傅", "师兄", "师姐", "师弟", "师妹", "师叔", "师伯", "师祖", "掌门", "帮主",
    "寨主", "宫主", "堡主", "庄主", "掌柜", "员外", "将军", "统领", "总兵", "知府",
    "知县", "太监", "宫女", "卫士", "侍卫", "军士", "官兵", "百姓", "众人", "群雄",
    "江湖", "武林", "天下", "人间", "世外", "一方", "此地", "那人", "此人", "老者",
    "少年", "少女", "妇人", "汉子", "大汉", "道士", "和尚", "尼姑", "书生",
    # 地域/政权/泛称（跨书=关联，不是同一性归并对象；D07 §4.6）
    "中国", "中原", "江南", "塞外", "关内", "关外", "京城", "京师", "皇宫", "朝廷",
    "明朝", "清朝", "大清", "满洲", "清廷", "明廷", "八旗军", "官军", "清兵", "明兵",
    "大内", "宫中", "天下人", "四海", "九州", "中原武林", "江湖人",
}
IDENTITY_CUES = re.compile(
    r"正是|便是|就是|原来|本名|原名|法号|道号|绰号|外号|人称|改名|化名|出家|即(?=[^，。]{2,6})")
GUIDE_CUES = re.compile(r"详见|事见|参见|拙著|本传|一书|见拙|请续看|请阅|另见")
NOISE_CUES = re.compile(r"书架|藏书|评弹|说唱|书摊|列举|看过|读过|传说|据闻|传闻")
B2_VERBS = re.compile(r"传下|传授|传给|传人|传于|传与")
POEM_CUES = re.compile(r"请看|喜在|正是：|有诗为证|诗曰|词曰")
# D07 §7.3 实测画像（人工核定）：绰号/兵器/群组/短语撞书名 → B1 噪声 + 转投
KNOWN_B1 = {
    "武林天骄": ("q4_alias_pool", "人物绰号撞书名（檀羽冲）"),
    "冰魄寒光剑": ("artifact_layer", "兵器撞书名"),
    "散花女侠": ("q4_alias_pool", "人物绰号撞书名（于承珠）"),
    "江湖三女侠": ("group_layer", "群体称号撞书名"),
    "幻剑灵旗": ("artifact_layer", "信物撞书名"),
    "武林三绝": ("phrase_layer", "短语称名（三法并称）"),
}
HONORIFIC_SUFFIX = re.compile(
    r"^[\u4e00-\u9fa5]{1,2}(大哥|大侠|公子|姑娘|小姐|兄|老|前辈|先生|大人|兄台|"
    r"女侠|少侠|师父|师兄|师姐|师弟|师妹|叔叔|伯伯|婆婆|婶婶|夫人|太太)$")


# ------------------------------------------------------------------ 工具 ----
def read_json(path: Path):
    return json.loads(io.open(path, encoding="utf-8").read())


def sha12(path: Path) -> str:
    return hashlib.sha256(io.open(path, "rb").read()).hexdigest()[:12]


def norm_surface(s: str) -> str:
    return (s or "").strip()


def load_registry(path: Path):
    """registry/entities.json → (entities, surface→entity_id 闭包, id→entity)。"""
    data = read_json(path)
    ents = data.get("entities", []) if isinstance(data, dict) else []
    closure, by_id = {}, {}
    for e in ents:
        eid = e.get("id") or ""
        by_id[eid] = e
        names = [e.get("canonical")] + list(e.get("aliases") or []) + list(e.get("contextual") or [])
        for s in names:
            s = norm_surface(s)
            if not s or "（" in s or "(" in s:
                continue
            closure.setdefault(s, eid)
    return ents, closure, by_id


def load_concordance(books):
    """5 书 concordance → {book: {canonical: entity}}；仅 in-scope 类型。"""
    out = {}
    for b in books:
        p = config.DIR_REGISTRY / "concordance" / f"{b}.json"
        if not p.exists():
            continue
        d = read_json(p)
        ents = {}
        for e in d.get("entities", []):
            if e.get("type") not in IN_SCOPE_TYPES:
                continue
            st = (e.get("registration") or {}).get("status")
            if st == "out_of_scope":
                continue
            ents[e["canonical"]] = e
        out[b] = ents
    return out


def build_surface_index(conc):
    """surface → [{book, canonical, type, count, is_canonical}]（书内 canonical+variants）。"""
    idx = defaultdict(list)
    for b, ents in conc.items():
        for canon, e in ents.items():
            idx[canon].append({"book": b, "canonical": canon, "type": e.get("type"),
                               "count": e.get("total", 0), "is_canonical": True})
            for v in e.get("variants") or []:
                s = norm_surface(v.get("display"))
                if not s or s == canon:
                    continue
                idx[s].append({"book": b, "canonical": canon, "type": e.get("type"),
                               "count": v.get("count", 0), "is_canonical": False})
    return idx


def load_series_assets():
    """系列谱系考订表 + 作品元数据表 → (seeds, series_of, era_of, work_books)。"""
    seeds, series_of, era_of, work_books = [], {}, {}, set()
    p = config.LEGACY_KB / "系列谱系考订表.json"
    if p.exists():
        d = read_json(p)
        seeds = d.get("interchange_seeds", []) or []
        for line in d.get("lines", []) or []:
            sname = line.get("line", "")
            for m in line.get("members", []) or []:
                series_of[m.get("book")] = sname
    p = config.LEGACY_KB / "作品元数据表.json"
    if p.exists():
        d = read_json(p)
        for w in d.get("works", []) or []:
            work_books.add(w.get("book"))
            series_of.setdefault(w.get("book"), w.get("series"))
            era_of[w.get("book")] = w.get("era")
    return seeds, series_of, era_of, work_books


def load_intertext():
    p = config.LEGACY_KB / "互文引用表.json"
    if not p.exists():
        return []
    return read_json(p).get("edges", []) or []


def load_mapping_latest(book: str):
    """logs/mapping_<书>/ch_*.json 最后一回累积快照 → {display: canonical}。"""
    d = config.DIR_LOGS / f"mapping_{book}"
    if not d.is_dir():
        return {}
    files = sorted(d.glob("ch_*.json"))
    if not files:
        return {}
    try:
        items = read_json(files[-1])
    except (json.JSONDecodeError, OSError):
        return {}
    out = {}
    if isinstance(items, list):
        for it in items:
            if isinstance(it, (list, tuple)) and len(it) >= 2:
                out.setdefault(norm_surface(it[0]), norm_surface(it[1]))
            elif isinstance(it, dict):
                disp = it.get("display") or it.get("surface")
                canon = it.get("canonical")
                if disp and canon:
                    out.setdefault(norm_surface(disp), norm_surface(canon))
    return out


def load_stopwords():
    out = set(ERA_GENERIC)
    p = config.DIR_WORDLISTS / "stopwords.json"
    if p.exists():
        try:
            d = read_json(p)
            items = d if isinstance(d, list) else d.get("items", [])
            for it in items:
                s = it if isinstance(it, str) else (it.get("surface") or it.get("word") or "")
                if s:
                    out.add(norm_surface(s))
        except (json.JSONDecodeError, OSError):
            pass
    return out


def load_artifact_names():
    names = set()
    p = config.LEGACY_KB / "神兵表.json"
    if p.exists():
        try:
            d = read_json(p)
            for key in ("items", "artifacts", "weapons"):
                for it in d.get(key, []) or []:
                    for k in ("name", "canonical", "display"):
                        if it.get(k):
                            names.add(norm_surface(it[k]))
        except (json.JSONDecodeError, OSError):
            pass
    p = config.LEGACY_KB / "门派世系表.json"
    if p.exists():
        try:
            d = read_json(p)
            for it in (d.get("items") or d.get("sects") or []):
                for k in ("name", "canonical"):
                    if isinstance(it, dict) and it.get(k):
                        names.add(norm_surface(it[k]))
        except (json.JSONDecodeError, OSError):
            pass
    return names


# -------------------------------------------------------------- 候选生成 ----
def _member(book, canonical, conc, surfaces):
    e = conc.get(book, {}).get(canonical, {})
    return {
        "book": book,
        "book_canonical": canonical,
        "type": e.get("type"),
        "total": e.get("total", 0),
        "chapter_count": e.get("chapter_count", 0),
        "surfaces": sorted({s for s in surfaces if s})[:20],
        "registration": (e.get("registration") or {}).get("status"),
    }


def _registry_coverage(names, closure):
    """names → (是否同一 registry 实体, entity_id 或 None, 覆盖的 name 列表)。"""
    ids = {closure.get(n) for n in names if closure.get(n)}
    if len(ids) == 1:
        eid = next(iter(ids))
        return True, eid, [n for n in names if closure.get(n) == eid]
    return False, None, [n for n in names if closure.get(n)]


def _pair_key(a, b):
    return tuple(sorted([a, b]))


def _series_of_pair(book_a, book_b, series_of):
    sa, sb = series_of.get(book_a), series_of.get(book_b)
    if sa and sb and sa == sb:
        return sa
    return None


def _relay_edges(edges, book_a, book_b):
    """两书之间的 authorial/quoted 互文边（双向）。"""
    out = []
    for e in edges:
        if e.get("kind") not in ("authorial", "quoted"):
            continue
        s, t = e.get("source"), e.get("target")
        if {s, t} == {book_a, book_b}:
            out.append(e)
    return out


def generate_candidates(books, conc, surface_idx, registry, closure, by_id,
                        seeds, series_of, era_of, edges, mapping, stopwords,
                        artifact_names, work_books, strict=False, series_filter=None):
    """返回 (candidates, stats, notes)。确定性排序：grade → 证据数 → 名称。"""
    cands, seen = [], set()
    stats = Counter()
    notes = []

    # ---- 1) 系列种子（D07 §8.4 interchange_seeds；人工考订三证） ----
    for seed in seeds:
        name = seed.get("name", "")
        seed_books = [b for b in (seed.get("books") or []) if b in books]
        if len(seed_books) < 2:
            continue
        if series_filter and series_filter not in ("", None):
            if all(series_of.get(b) != series_filter for b in seed_books):
                continue
        # 解析种子显示名：A（B）/ A（B、C）
        raw = re.findall(r"([^（）()、,，]+)", name)
        raw = [norm_surface(x) for x in raw if norm_surface(x)]
        members, used_surfaces = [], {}
        for b in seed_books:
            hit = None
            for s in raw:
                for m in surface_idx.get(s, []):
                    if m["book"] == b:
                        hit = (m["canonical"], s)
                        break
                if hit:
                    break
            if not hit:
                continue
            canon, surf = hit
            members.append(_member(b, canon, conc, [surf] + raw))
            used_surfaces.setdefault(b, set()).add(surf)
        if len(members) < 2:
            continue
        names = [m["book_canonical"] for m in members] + raw
        covered, eid, covered_names = _registry_coverage(names, closure)
        key = ("seed", tuple(sorted(m["book"] for m in members)), tuple(sorted(names)))
        if key in seen:
            continue
        seen.add(key)
        relay = _relay_edges(edges, members[0]["book"], members[-1]["book"])
        grade = "E3"
        conf = "strong"  # 种子三证（接力边+回指+编年）→ E3+strong
        cand = {
            "candidate_id": None,
            "source": ["series_seed"],
            "seed": {"name": name, "books": seed_books, "note": seed.get("note", "")},
            "entity_type": TYPE_LABEL.get(members[0]["type"], members[0]["type"]),
            "type_code": members[0]["type"],
            "members": members,
            "series": _series_of_pair(members[0]["book"], members[-1]["book"], series_of),
            "proposed_series": _propose_series(members, covered, eid, by_id),
            "evidence": [{
                "level": grade, "kind": "series_seed", "authority_layer": "governance",
                "source_channel": "series_interchange_seed",
                "note": f"系列谱系考订表 interchange_seed：{seed.get('note','')}",
                "relay_edges": [{"source": e.get("source"), "target": e.get("target"),
                                 "kind": e.get("kind"), "probe": e.get("probe"),
                                 "loc": e.get("loc")} for e in relay[:3]],
            }],
            "evidence_grade": grade,
            "conf": conf,
            "authority_layer": "governance",
            "bare_rule": None,
            "conflicts": [],
            "suggested_action": "reject" if covered else "proposal",
            "merge_allowed": False if covered else True,
            "rationale": ("种子已归并（registry 同一实体覆盖全部成员）" if covered
                          else "种子成员未被同一 registry 实体覆盖，需补归并/补别名"),
            "review": _review_state(grade),
        }
        if covered:
            cand["resolution"] = "already_merged"
            cand["registry_entity"] = eid
            stats["already_merged"] += 1
        else:
            stats["proposal"] += 1
        cands.append(cand)

    # ---- 2) 跨书同名 canonical（同 surface 同 canonical，≥2 书） ----
    for surf, hits in sorted(surface_idx.items()):
        if surf in stopwords or len(surf) < 2:
            continue
        by_canon = defaultdict(list)
        for h in hits:
            by_canon[h["canonical"]].append(h)
        if len(by_canon) != 1 or len({h["book"] for h in hits}) < 2:
            continue
        canon = next(iter(by_canon))
        book_hits = {}
        for h in by_canon[canon]:
            book_hits.setdefault(h["book"], h)
        if len(book_hits) < 2:
            continue
        names = [canon]
        covered, eid, _ = _registry_coverage(names, closure)
        # 已归并（同一 registry 实体）→ 拒绝但留审计
        if covered:
            key = ("same_canon_merged", canon, tuple(sorted(book_hits)))
            if key in seen:
                continue
            seen.add(key)
            members = [_member(b, canon, conc, [surf]) for b in sorted(book_hits)]
            cands.append({
                "candidate_id": None, "source": ["cross_book_same_canonical"],
                "entity_type": TYPE_LABEL.get(members[0]["type"], ""),
                "type_code": members[0]["type"], "members": members,
                "series": _series_of_pair(members[0]["book"], members[-1]["book"], series_of),
                "proposed_series": _propose_series(members, True, eid, by_id),
                "evidence": [{"level": "E4", "kind": "same_surface", "authority_layer": "governance",
                              "note": f"同名 canonical「{canon}」跨 {len(members)} 书；registry 已同实体",
                              "surfaces": [surf]}],
                "evidence_grade": "E4", "conf": "todo", "authority_layer": "governance",
                "bare_rule": None, "conflicts": [],
                "suggested_action": "reject", "merge_allowed": False,
                "resolution": "already_merged", "registry_entity": eid,
                "rationale": "registry 同一实体已覆盖该 canonical（无需归并）",
                "review": _review_state("E4"),
            })
            stats["already_merged"] += 1
            continue
        grade, ev = _grade_same_canonical(canon, book_hits, series_of, era_of, edges,
                                          by_id, closure, mapping, seeds)
        key = ("same_canon", canon, tuple(sorted(book_hits)))
        if key in seen:
            continue
        seen.add(key)
        members = [_member(b, canon, conc, [surf]) for b in sorted(book_hits)]
        if members[0]["type"] == "◆":
            # D07 §4.6：组织跨书=关联（surface 恒定，无归并操作），不建同一性归并
            cands.append({
                "candidate_id": None, "source": ["cross_book_same_canonical"],
                "entity_type": "组织", "type_code": "◆", "members": members,
                "series": _series_of_pair(members[0]["book"], members[-1]["book"], series_of),
                "proposed_series": {"display_canonical": canon, "entity_id": None,
                                    "rule": "组织跨书=关联，不做同一性归并（D07 §4.6）"},
                "evidence": [{"level": "E4", "kind": "org_association_only",
                              "authority_layer": "governance",
                              "note": f"同名组织「{canon}」跨书：按时代切面关联，不归并"}],
                "evidence_grade": "E4", "conf": "todo", "authority_layer": "governance",
                "bare_rule": None, "conflicts": [],
                "suggested_action": "reject", "merge_allowed": False,
                "resolution": "org_association_only",
                "rationale": "组织跨书=关联（D07 §4.6）：surface 恒定无归并操作，档案按时代切面",
                "review": _review_state("E4"),
            })
            stats["org_association_only"] += 1
            continue
        conflicts = _type_conflicts(members, by_id, closure)
        action = ACTION_BY_GRADE[grade]
        if conflicts:
            action = "proposal"
        cands.append({
            "candidate_id": None, "source": ["cross_book_same_canonical"],
            "entity_type": TYPE_LABEL.get(members[0]["type"], ""),
            "type_code": members[0]["type"], "members": members,
            "series": _series_of_pair(members[0]["book"], members[-1]["book"], series_of),
            "proposed_series": _propose_series(members, False, None, by_id),
            "evidence": ev, "evidence_grade": grade, "conf": GRADE_CONF[grade],
            "authority_layer": GRADE_AUTHORITY[grade], "bare_rule": None,
            "conflicts": conflicts, "suggested_action": action,
            "merge_allowed": MERGE_ALLOWED[grade] and not conflicts,
            "rationale": _rationale_same_canonical(grade, canon, members),
            "review": _review_state(grade),
        })
        stats[action] += 1

    # ---- 3) 同 surface 不同书 canonical（异名/同名异人歧义） ----
    for surf, hits in sorted(surface_idx.items()):
        if surf in stopwords or len(surf) < 2:
            continue
        canon_by_book = defaultdict(set)
        for h in hits:
            canon_by_book[h["book"]].add(h["canonical"])
        if len(canon_by_book) < 2:          # 必须跨 ≥2 书（书内歧义留给书内消歧）
            continue
        if any(len(cs) > 1 for cs in canon_by_book.values()):
            stats["within_book_ambiguous"] += 1   # 先书内后系列（D07 §4.4），本批不归并
            continue
        canon_set = {c for cs in canon_by_book.values() for c in cs}
        if len(canon_set) < 2:
            continue
        if surf in ERA_GENERIC:
            stats["reject_era_generic"] += 1
            continue
        names = sorted(canon_set)
        covered, eid, _ = _registry_coverage(names, closure)
        key = ("diff_canon", surf, tuple(names))
        if key in seen:
            continue
        seen.add(key)
        members = []
        for b in sorted(canon_by_book):
            for c in sorted(canon_by_book[b]):
                members.append(_member(b, c, conc, [surf]))
        grade, ev = _grade_diff_canonical(surf, members, series_of, era_of, edges,
                                          by_id, closure, mapping, seeds)
        conflicts = _type_conflicts(members, by_id, closure)
        if HONORIFIC_SUFFIX.match(surf):
            # D07 §5.4 同名异人限定：姓+称谓型 surface 不得据以归并（先书内消歧）
            conflicts.append({"type": "surname_honorific_ambiguous", "values": [surf],
                              "resolution": "pending_manual"})
            if grade != "E4":
                grade = "E4"
                ev.append({"level": "E4", "kind": "surname_honorific",
                           "authority_layer": "governance",
                           "note": f"surface「{surf}」为姓+称谓型，跨书同名异人风险高（D07 §5.4）"})
        if covered:
            stats["already_merged"] += 1
            continue
        action = ACTION_BY_GRADE[grade]
        if conflicts:
            # 同名异人风险 / registry 多实体冲突：按 D07 §5.4/§6.2 分流为拒绝（留审计）
            action = "reject"
        cands.append({
            "candidate_id": None, "source": ["cross_book_alias_divergence"],
            "entity_type": TYPE_LABEL.get(members[0]["type"], ""),
            "type_code": members[0]["type"], "members": members,
            "series": _series_of_pair(members[0]["book"], members[-1]["book"], series_of),
            "proposed_series": _propose_series(members, False, None, by_id),
            "evidence": ev, "evidence_grade": grade, "conf": GRADE_CONF[grade],
            "authority_layer": GRADE_AUTHORITY[grade], "bare_rule": None,
            "conflicts": conflicts, "suggested_action": action,
            "merge_allowed": False,
            "resolution": conflicts[0].get("type") if conflicts else None,
            "rationale": _rationale_diff(surf, grade, members),
            "review": _review_state(grade),
        })
        stats[action] += 1

    # ---- 4) 映射快照分歧（同 display 跨书不同 canonical） ----
    disp_map = defaultdict(dict)  # display -> {book: canonical}
    for b, m in mapping.items():
        for disp, canon in m.items():
            disp_map[disp][b] = canon
    for disp, bm in sorted(disp_map.items()):
        if len(bm) < 2 or len(disp) < 2:
            continue
        if len(set(bm.values())) < 2:
            continue
        key = ("mapping_div", disp, tuple(sorted(bm.items())))
        if key in seen:
            continue
        seen.add(key)
        is_generic = disp in ERA_GENERIC or disp.endswith(("大人", "公子", "姑娘", "师父"))
        names = sorted(set(bm.values()))
        covered, eid, _ = _registry_coverage(names, closure)
        if covered:
            stats["already_merged"] += 1
            cands.append({
                "candidate_id": None, "source": ["mapping_divergence"],
                "entity_type": "人物", "type_code": "@",
                "members": [{"book": b, "book_canonical": c, "type": "@",
                             "surfaces": [disp], "total": 0, "chapter_count": 0,
                             "registration": "mapping"} for b, c in sorted(bm.items())],
                "series": None,
                "proposed_series": {"display_canonical": eid and by_id.get(eid, {}).get("canonical"),
                                    "entity_id": eid,
                                    "rule": "registry 同一实体已覆盖（映射分歧=书内层投影差异）"},
                "evidence": [{"level": "E4", "kind": "mapping_divergence",
                              "authority_layer": "governance",
                              "note": f"映射分歧「{disp}」各书 canonical 已在 registry 同一实体",
                              "pairs": sorted(bm.items())}],
                "evidence_grade": "E4", "conf": "todo", "authority_layer": "governance",
                "bare_rule": None, "conflicts": [], "suggested_action": "reject",
                "merge_allowed": False, "resolution": "already_merged",
                "rationale": "registry 同一实体已覆盖各书 canonical（映射分歧仅为书内层投影）",
                "review": _review_state("E4"),
            })
            continue
        cands.append({
            "candidate_id": None, "source": ["mapping_divergence"],
            "entity_type": "人物", "type_code": "@",
            "members": [{"book": b, "book_canonical": c, "type": "@", "surfaces": [disp],
                         "total": 0, "chapter_count": 0, "registration": "mapping"}
                        for b, c in sorted(bm.items())],
            "series": None,
            "proposed_series": {"display_canonical": None, "entity_id": None,
                                "rule": "映射分歧：先按 (书,回) 语境裁定，不自动归并"},
            "evidence": [{"level": "E4", "kind": "mapping_divergence",
                          "authority_layer": "governance",
                          "note": f"映射快照同一 display「{disp}」跨书指向不同 canonical",
                          "pairs": sorted(bm.items())}],
            "evidence_grade": "E4", "conf": "todo", "authority_layer": "governance",
            "bare_rule": None,
            "conflicts": [{"type": "same_display_multi_canonical",
                           "values": sorted(set(bm.values())),
                           "resolution": "pending_era_context"}],
            "suggested_action": "reject" if is_generic else "proposal",
            "merge_allowed": False,
            "resolution": "era_dependent_generic" if is_generic else None,
            "rationale": ("时代依赖通称：按回级语境/回级映射处理（task-11 已支持），不归并"
                          if is_generic else "映射分歧：可能同名异人，进复核队列"),
            "review": _review_state("E4"),
        })
        stats["reject_era_generic" if is_generic else "proposal"] += 1

    # ---- 5) 互文 authorial 边：仅作 relay 证据与统计（不单独生成人物归并） ----
    relay_stats = Counter()
    for e in edges:
        relay_stats[e.get("kind", "?")] += 1

    # ---- 去重：同一成员集合只保留最高优先级来源（seed > 同名 > 异名 > 映射） ----
    prio = {"series_seed": 0, "cross_book_same_canonical": 1,
            "cross_book_alias_divergence": 2, "mapping_divergence": 3}
    uniq = {}
    for c in cands:
        sig = tuple(sorted((m["book"], m["book_canonical"]) for m in c["members"]))
        p = prio.get((c["source"] or [""])[0], 9)
        if sig not in uniq or p < uniq[sig][0]:
            uniq[sig] = (p, c)
    cands = [c for _p, c in uniq.values()]

    # 拒绝/已归并候选：复核状态关闭（审计留痕，不进复核队列）
    for c in cands:
        if c["suggested_action"] == "reject":
            c["review"]["state"] = "closed_rejected"
            c["review"]["required"] = False
    # ---- 编号/排序 ----
    cands.sort(key=lambda c: (GRADE_ORDER.get(c["evidence_grade"], 9),
                              -len(c.get("evidence") or []),
                              c.get("members")[0]["book_canonical"] if c.get("members") else "",
                              c.get("source")))
    for i, c in enumerate(cands, 1):
        c["candidate_id"] = f"N6-{i:04d}"
        c["dedupe_key"] = hashlib.sha1(
            json.dumps([c["source"], sorted(m["book"] for m in c["members"]),
                        sorted({m["book_canonical"] for m in c["members"]})],
                       ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    if strict:
        pending = [c for c in cands if c["suggested_action"] in ("merge", "proposal")
                   and c["evidence_grade"] in ("E3", "E4")]
        cands = [c for c in cands
                 if c["suggested_action"] in ("merge", "proposal")
                 and (c["evidence_grade"] in ("E1", "E2")
                      or (c["evidence_grade"] == "E3" and c["conf"] == "strong"
                          and c.get("seed")))]
        for i, c in enumerate(cands, 1):
            c["candidate_id"] = f"N6-{i:04d}"
        stats["strict_pending"] = len(pending)
    stats["candidates_total"] = len(cands)
    stats["relay_edges"] = dict(relay_stats)
    return cands, stats, notes


def _review_state(grade):
    return {
        "state": "pending_sample" if grade == "E1" else "pending",
        "reviewer_a": None, "reviewer_b": None,
        "required": REVIEW_REQUIRED[grade],
        "sampling": REVIEW_SAMPLING[grade],
        "history": [],
    }


def _propose_series(members, covered, eid, by_id):
    """系列层建议（不落库）：registry canonical 优先，否则跨书总频最高 surface（D07 §4.3）。"""
    if covered and eid and eid in by_id:
        canon = by_id[eid].get("canonical")
        return {"display_canonical": canon, "entity_id": eid,
                "rule": "registry 已有实体 canonical（书内层→系列层投影）"}
    freq = Counter()
    for m in members:
        freq[m["book_canonical"]] += max(1, int(m.get("total") or 1))
    best = freq.most_common(1)[0][0] if freq else None
    return {"display_canonical": best, "entity_id": None,
            "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}


def _grade_same_canonical(canon, book_hits, series_of, era_of, edges, by_id, closure,
                          mapping, seeds):
    books = sorted(book_hits)
    same_series = len({series_of.get(b) for b in books}) == 1 and series_of.get(books[0])
    relay = []
    for i in range(len(books)):
        for j in range(i + 1, len(books)):
            relay.extend(_relay_edges(edges, books[i], books[j]))
    ev = []
    # D07：authorial 只证明"有互文"，不自动等于可归并；同名跨书最高只能到 E3（同系列+接力/种子）
    seed_hit = any(canon in (s.get("name") or "") for s in seeds)
    if same_series and (seed_hit or relay):
        ev.append({"level": "E3", "kind": "series_relay",
                   "authority_layer": "governance",
                   "note": f"同系列（{series_of.get(books[0])}）+ 接力边/种子；同名「{canon}」跨书",
                   "relay_edges": [{"source": e.get("source"), "target": e.get("target"),
                                    "kind": e.get("kind"), "loc": e.get("loc")}
                                   for e in relay[:3]]})
        return "E3", ev
    ev.append({"level": "E4", "kind": "same_surface", "authority_layer": "governance",
               "note": f"仅同名 canonical「{canon}」跨 {len(books)} 书，无正文/种子锚点"})
    return "E4", ev


def _grade_diff_canonical(surf, members, series_of, era_of, edges, by_id, closure,
                          mapping, seeds):
    books = sorted({m["book"] for m in members})
    names = sorted({m["book_canonical"] for m in members})
    covered, eid, _ = _registry_coverage(names, closure)
    relay = []
    for i in range(len(books)):
        for j in range(i + 1, len(books)):
            relay.extend(_relay_edges(edges, books[i], books[j]))
    ev = []
    # E1：书内层已由同一 registry 实体证明两名为同人（别名闭包）+ 跨书 authorial 锚点互证
    if covered and any(e.get("kind") == "authorial" for e in relay):
        ev.append({"level": "E1", "kind": "authorial_anchor",
                   "authority_layer": "L1",
                   "note": f"registry {eid} 别名闭包证明两名为同一实体；跨书 authorial 锚点互证",
                   "relay_edges": [{"source": e.get("source"), "target": e.get("target"),
                                    "loc": e.get("loc"), "probe": e.get("probe")}
                                   for e in relay[:3] if e.get("kind") == "authorial"]})
        return "E1", ev
    same_series = len({series_of.get(b) for b in books}) == 1 and series_of.get(books[0])
    seed_hit = any(surf in (s.get("name") or "") for s in seeds)
    if same_series and (relay or seed_hit or covered):
        ev.append({"level": "E3", "kind": "series_relay", "authority_layer": "governance",
                   "note": f"同系列 + 接力边/种子/registry 别名闭包；同 surface「{surf}」跨书异名",
                   "relay_edges": [{"source": e.get("source"), "target": e.get("target"),
                                    "kind": e.get("kind"), "loc": e.get("loc")}
                                   for e in relay[:3]]})
        return "E3", ev
    ev.append({"level": "E4", "kind": "same_surface_multi_canonical",
               "authority_layer": "governance",
               "note": f"同 surface「{surf}」跨书 canonical 不同，无正文/种子锚点"})
    return "E4", ev


def _type_conflicts(members, by_id, closure):
    conflicts = []
    types = {m.get("type") for m in members if m.get("type")}
    if len(types) > 1:
        conflicts.append({"type": "entity_type_mismatch", "values": sorted(types),
                          "resolution": "pending_manual"})
    ids = {closure.get(m["book_canonical"]) for m in members if closure.get(m["book_canonical"])}
    if len(ids) > 1:
        conflicts.append({"type": "registry_multi_entity", "values": sorted(ids),
                          "resolution": "pending_manual"})
    return conflicts


def _rationale_same_canonical(grade, canon, members):
    books = "、".join(m["book"] for m in members)
    if grade == "E1":
        return f"同名「{canon}」跨书且互文正文直证（{books}）→ 可归并（E1 免双人，抽验 5%）"
    if grade == "E3":
        return f"同名「{canon}」跨书 + 同系列接力/种子（{books}）→ 提案，全量双人复核"
    return f"仅同名「{canon}」（{books}）→ 候选池，无证据不归并（E4）"


def _rationale_diff(surf, grade, members):
    names = "、".join(sorted({m["book_canonical"] for m in members}))
    if grade == "E1":
        return f"同 surface「{surf}」跨书异名（{names}）+ 互文正文直证 → 提案（需确认非同名异人）"
    if grade == "E3":
        return f"同 surface「{surf}」跨书异名（{names}）+ 同系列接力 → 提案，双人复核"
    return f"同 surface「{surf}」跨书异名（{names}）→ 候选池（E4），不自动归并"


# ---------------------------------------------------------------- bare B0-B8 ----
def _fence_checker(books):
    """5 书 struct 缓存 → 判断 (book, chapter, para) 是否在围栏内（用于 B3）。"""
    cache = {}

    def in_fence(book, loc):
        if book not in books or not loc or ":" not in str(loc):
            return None
        try:
            ch_s, para_s = str(loc).split(":", 1)
            ch, para = int(ch_s), int(para_s)
        except ValueError:
            return None
        key = (book, ch)
        if key not in cache:
            p = config.struct_path(book, ch)
            fence_map = {}
            if p.exists():
                cur = None
                for ln in io.open(p, encoding="utf-8").read().split("\n"):
                    m = re.match(r"^:::\s*(\S+)\s*$", ln)
                    if m:
                        cur = m.group(1)
                        continue
                    if re.match(r"^:::\s*$", ln):
                        cur = None
                        continue
                    pm = re.match(r"^\[(\d+)\] ", ln)
                    if pm:
                        fence_map[int(pm.group(1))] = cur
            cache[key] = fence_map
        return bool(cache[key].get(para))
    return in_fence


def classify_bare(edges, books, surface_idx, artifact_names, work_books, generic):
    """bare 边 B0-B8 分流（D07 §7.2）→ (dispatch counts, transfers, review_items, examples)。"""
    in_fence = _fence_checker(books)
    counts = Counter()
    transfers, review_items, examples = [], [], []
    entity_surface = {}
    for s, hits in surface_idx.items():
        for h in hits:
            entity_surface.setdefault(s, h)
    for e in edges:
        if e.get("kind") != "bare":
            continue
        probe = norm_surface(e.get("probe"))
        snippet = e.get("snippet", "") or ""
        loc = e.get("loc", "")
        src, tgt = e.get("source"), e.get("target")
        rule = "B8"
        if not probe:
            rule = "B8"
        elif probe in generic:
            rule = "B0"
        elif probe in KNOWN_B1:
            pool, note = KNOWN_B1[probe]
            rule = "B1"
            transfers.append({"probe": probe, "target_pool": pool, "source": src,
                              "loc": loc, "count": 0, "note": note})
        elif probe in entity_surface or probe in artifact_names:
            h = entity_surface.get(probe, {})
            t = h.get("type")
            rule = "B1"
            if t == "@":
                transfers.append({"probe": probe, "target_pool": "q4_alias_pool",
                                  "source": src, "loc": loc,
                                  "note": f"人物绰号/称名撞书名（书内 canonical={h.get('canonical')}）"})
            elif t in ("◆", "&"):
                transfers.append({"probe": probe, "target_pool": "group_layer",
                                  "source": src, "loc": loc, "note": "群组/组织称号撞书名"})
            else:
                transfers.append({"probe": probe, "target_pool": "artifact_layer",
                                  "source": src, "loc": loc, "note": "器物/技艺名撞书名"})
        elif probe.endswith("传") and B2_VERBS.search(snippet):
            rule = "B2"
        elif probe in work_books and GUIDE_CUES.search(snippet):
            rule = "B5"
        elif probe in work_books and NOISE_CUES.search(snippet):
            rule = "B7"
        elif probe in work_books and POEM_CUES.search(snippet):
            rule = "B3"
        elif probe in work_books and re.search(r"想当年|当年|往事|史事", snippet):
            rule = "B4"
        elif in_fence(src, loc) or in_fence(tgt, loc):
            rule = "B3"
        elif probe in entity_surface:
            rule = "B6"
            h = entity_surface[probe]
            transfers.append({"probe": probe, "target_pool": "review_or_layer",
                              "source": src, "loc": loc,
                              "note": f"对象名（{h.get('type')}）非互文语境，按层转投/人工核验"})
        counts[rule] += 1
        if rule in ("B5", "B6", "B7", "B8"):
            if rule == "B8" and (src not in books or tgt not in books):
                counts["B8_deferred_out_of_kb"] += 1   # 34 书 bare 边、仅 5 书有实体索引 → 本批挂起
                continue
            review_items.append({"probe": probe, "rule": rule, "source": src,
                                 "target": tgt, "loc": loc, "snippet": snippet[:120],
                                 "action": {"B5": "升级 authorial→E1 流程（补解析 probe）",
                                            "B6": "按对象类型转层/人工核验",
                                            "B7": "中间态：评述性提及（弱互文 E3）",
                                            "B8": "转人工队列"}[rule]})
        if len(examples) < 40:
            examples.append({"probe": probe, "rule": rule, "source": src,
                             "target": tgt, "loc": loc, "snippet": snippet[:100]})
    # 转投按 (probe,pool,note) 聚合计数（1775 条 bare 中大量同 probe）
    agg = {}
    for t in transfers:
        k = (t["probe"], t["target_pool"], t.get("note", ""))
        if k in agg:
            agg[k]["count"] += 1
        else:
            agg[k] = dict(t)
            agg[k]["count"] = 1
    transfers = list(agg.values())
    return dict(counts), transfers, review_items, examples


# ---------------------------------------------------------------- 报告/落盘 ----
def _render_review_queue(cands, stats, meta, transfers=None, review_items=None):
    transfers = transfers or []
    review_items = review_items or []
    actionable = [c for c in cands if c["suggested_action"] in ("merge", "proposal")]
    rejects = [c for c in cands if c["suggested_action"] not in ("merge", "proposal")]
    L = ["# N6 跨书归并 · 双人复核队列", ""]
    L += [f"- 生成：{meta['generated']}；规格：{meta['spec_version']}",
          f"- 候选：{len(cands)} 条（E1 {stats.get('grade_E1',0)} / E2 {stats.get('grade_E2',0)}"
          f" / E3 {stats.get('grade_E3',0)} / E4 {stats.get('grade_E4',0)}）",
          "- 规则：`skills/SKILL_跨书治理_武侠版.md` §2（E1-E4）/§3（L1-L4）/§4（双层 canonical）"
          "/§7.2（bare B0-B8）/§8.2（双人门槛）",
          "", "## 一、状态机", "",
          "```",
          "pending ──A通过──▶ reviewer_a ──B通过──▶ approved ──回写──▶ merged",
          "   │                  │",
          "   └──A拒绝───────────┴──B拒绝──▶ rejected（保留候选与证据，可撤销重判）",
          "E1（免双人）：pending_sample ──5% 抽验通过──▶ approved",
          "```",
          "状态取值：pending / pending_sample / reviewer_a / reviewer_b / approved / "
          "rejected / deferred；每次流转在 `history` 追加 {by,date,from,to,note}。",
          "", "## 二、复核门槛（D07 §8.2）", "",
          "| 证据级 | 门槛 | 抽验 |", "|---|---|---|",
          "| E1 正文明示 | 免双人 | 5% |",
          "| E2 序跋 / E3 情节暗示 | 全量双人 | — |",
          "| E4 读者推断 | 不进归并（仅候选池） | — |",
          "| display_canonical 变更 / unmerge / 底本切换 | 全量双人 | — |",
          "", "## 三、复核队列（proposal / merge；双人复核门槛见 §二）", "",
          "| # | candidate_id | 级 | conf | 建议动作 | 书/成员 | 系列建议 | 状态 | reviewer_a | reviewer_b |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(actionable, 1):
        books = "、".join(sorted({m["book"] for m in c["members"]}))
        names = "、".join(sorted({m["book_canonical"] for m in c["members"]}))
        disp = (c.get("proposed_series") or {}).get("display_canonical") or "—"
        L.append(f"| {i} | {c['candidate_id']} | {c['evidence_grade']} | {c['conf']} | "
                 f"{c['suggested_action']} | {books}：{names} | {disp} | "
                 f"{c['review']['state']} | （待填） | （待填） |")
    L += ["", f"> 待复核 {len(actionable)} 条（E2/E3/E4 全量双人；E1 免双人抽验 5%）。"
          f"另有 {len(rejects)} 条已判定不归并（审计记录见 §四）。", ""]
    L += ["## 四、已判定不归并（审计记录）", "",
          "| candidate_id | 处置 | 成员 | 理由 |", "|---|---|---|---|"]
    for c in rejects[:200]:
        names = "、".join(sorted({f"{m['book']}→{m['book_canonical']}" for m in c["members"]}))
        L.append(f"| {c['candidate_id']} | {c.get('resolution') or c['suggested_action']} | "
                 f"{names} | {c.get('rationale','')[:80]} |")
    L += ["", "## 五、逐候选证据卡（actionable，前 80 条；全量见 merge_candidates.json）", ""]
    for c in actionable[:80]:
        L += [f"### {c['candidate_id']} · {c['evidence_grade']} · {c['conf']} · "
              f"{c['suggested_action']}", ""]
        L += [f"- 来源：{', '.join(c['source'])}；类型：{c.get('entity_type','')}"
              f"（{c.get('type_code','')}）；系列：{c.get('series') or '—'}",
              f"- 成员（书内层）：" + "；".join(
                  f"{m['book']}→{m['book_canonical']}（{m['type']}，{m['total']} 次）"
                  for m in c["members"]),
              f"- 系列层建议：{json.dumps(c.get('proposed_series'), ensure_ascii=False)}",
              f"- 理由：{c.get('rationale','')}"]
        if c.get("conflicts"):
            L.append(f"- 冲突：{json.dumps(c['conflicts'], ensure_ascii=False)}")
        for ev in c.get("evidence") or []:
            L.append(f"- 证据 [{ev.get('level')}/{ev.get('kind')}] "
                     f"{ev.get('note','')} loc={ev.get('loc','—')}")
        L += [f"- 复核状态：{c['review']['state']}（{c['review']['sampling']}）", ""]
    L += ["## 六、bare B0-B8 转投与人工复核（D07 §7.2）", ""]
    if transfers:
        L += ["| probe | 转投池 | 条数 | 说明 |", "|---|---|---|---|"]
        for t in sorted(transfers, key=lambda x: -x.get("count", 0))[:30]:
            L.append(f"| {t['probe']} | {t['target_pool']} | {t.get('count',0)} | "
                     f"{t.get('note','')} |")
    else:
        L.append("- 本批无转投条目。")
    L += ["", f"B8 转人工复核 {len(review_items)} 条（明细见 merge_candidates.json "
          "`bare_dispatch.review_items`）；其余 bare 边按 B0-B8 自动归因。", ""]
    L += ["## 七、回写与撤销（D07 §8.1/§8.3）", "",
          "1. 顺序：book_aliases → series_identities → 派生视图重建（先书内后系列）；",
          "2. 归并/撤销均须留 review 记录；entity_id 封存不删不复用；",
          "3. 本工作台**不自动回写 registry**：approved 后的回写由登记层工具执行并留痕。", ""]
    return "\n".join(L)


def _render_report(meta, stats, cands, bare_counts, transfers, review_items,
                   data_gaps):
    L = ["# N6 跨书归并工作台 · 运行报告", ""]
    L += [f"- 生成：{meta['generated']}；规格：{meta['spec_version']}；耗时：{meta['elapsed_s']}s",
          f"- 输入：registry {meta['registry_total']} 条；concordance {len(meta['books'])} 书；"
          f"互文 {meta['intertext_total']} 边；种子 {meta['seed_total']} 条",
          f"- 输出：`registry/crossover/merge_candidates.json`、"
          f"`registry/crossover/review_queue.md`", ""]
    L += ["## 一、候选规模与分级", "",
          "| 指标 | 值 |", "|---|---|",
          f"| 候选总数 | {stats.get('candidates_total', 0)} |",
          f"| E1 正文明示 | {stats.get('grade_E1', 0)} |",
          f"| E2 序跋后记 | {stats.get('grade_E2', 0)}（当前语料无独立序跋集 → 数据缺口） |",
          f"| E3 情节暗示 | {stats.get('grade_E3', 0)} |",
          f"| E4 读者推断（仅候选池） | {stats.get('grade_E4', 0)} |",
          f"| 建议动作 merge / proposal / reject | {stats.get('merge',0)} / "
          f"{stats.get('proposal',0)} / {stats.get('reject',0)} |",
          f"| 已归并（registry 覆盖，审计用 reject） | {stats.get('already_merged',0)} |",
          f"| 时代通称（reject，回级语境处理） | {stats.get('reject_era_generic',0)} |",
          f"| 组织跨书关联（不归并，D07 §4.6） | {stats.get('org_association_only',0)} |",
          f"| 书内同名歧义（先书内消歧，D07 §4.4） | {stats.get('within_book_ambiguous',0)} |", ""]
    L += [f"- **E1=0 说明**：可由 registry 别名闭包 + 跨书 authorial 锚点支撑的对，"
          f"当前已全部落在同一 registry 实体（already_merged 审计 "
          f"{stats.get('already_merged',0)} 条）——无新增正文直证对；",
          "- **E2=0**：当前语料无独立序跋/后记集（接口已预留 `source_channel=partext`）。", ""]
    L += ["## 二、与 D07 口径对照", "",
          "| D07 条款 | 本工作台实现 |", "|---|---|",
          "| §2.1 E1-E4 四级 | 候选 `evidence_grade`；E1 需正文/互文锚点；E3 需同系列接力/种子；"
          "E4 仅候选池（merge_allowed=false） |",
          "| §2.3 conf 映射 | E1/E2→strong、E3→ok、E4→todo（`conf` 字段） |",
          "| §3.1 权威四层 | `authority_layer`：正文证据=L1；登记/映射/种子=governance；"
          "E4=todo；序跋 L3 无数据 |",
          "| §4.1-4.3 双层 canonical | `members`（书内层）+ `proposed_series`（系列层建议，"
          "不落库、ID 留空待复核颁发） |",
          "| §4.6 类型强度 | 只处理 @/◆/&（强/中治理）；地点/生物/职衔等不归并 |",
          "| §7.2 bare B0-B8 | `bare_dispatch` 分流统计 + 转投清单 + 人工队列 |",
          "| §8.2 双人门槛 | review_queue 状态机 + 各证据级门槛/抽验列 |",
          "| §8.1/§8.3 回写/撤销 | 仅产队列，不自动回写；回写顺序与 ID 封存规则写入队列文档 |", ""]
    L += ["## 三、bare B0-B8 分流", "", "| 规则 | 条数 | 处置 |", "|---|---|---|"]
    action = {"B0": "噪声丢弃", "B1": "噪声 + 转投（绰号/群组/器物候选池）",
              "B2": "分词陷阱噪声", "B3": "韵文/回目噪声", "B4": "事件称名噪声",
              "B5": "升级 authorial→E1 流程", "B6": "对象名按层转投/人工核验",
              "B7": "中间态（弱互文 E3）", "B8": "转人工队列"}
    for r in [f"B{i}" for i in range(9)]:
        L.append(f"| {r} | {bare_counts.get(r, 0)} | {action[r]} |")
    if bare_counts.get("B8_deferred_out_of_kb"):
        L.append(f"| B8（挂起） | {bare_counts.get('B8_deferred_out_of_kb', 0)} | "
                 "涉及未建 KB 的 34 书（实体索引仅 5 书）→ 本批挂起，不阻塞")
    L += ["", f"转投条目 {len(transfers)} 条、人工复核条目 {len(review_items)} 条"
          "（明细见 merge_candidates.json `bare_dispatch`）。", ""]
    L += ["## 四、冲突与数据缺口", ""]
    conflict_c = Counter()
    for c in cands:
        for cf in c.get("conflicts") or []:
            conflict_c[cf.get("type")] += 1
    if conflict_c:
        L += ["| 冲突类型 | 条数 |", "|---|---|"]
        for k, v in conflict_c.most_common():
            L.append(f"| {k} | {v} |")
    else:
        L.append("- 本批无候选级冲突。")
    L += ["", "数据缺口（不阻塞本批，供后续批次）："]
    L += [f"- {g}" for g in data_gaps]
    L += ["", "## 五、复核队列与回写", "",
          f"- 待复核：{sum(1 for c in cands if c['review']['required'])} 条（E2/E3 全量双人）；"
          f"E4 仅候选池（不进归并）；E1 抽验 {sum(1 for c in cands if c['evidence_grade']=='E1')} 条（5%）。",
          "- 本工作台不写 registry/tagged；approved 后回写由登记层工具执行（顺序见 review_queue §七）。", ""]
    L += ["## 六、接口说明（供下游消费）", "",
          "- CLI：`--all`（全部 5 书）/`--series [NAME]`（同系列配对或指定系列）/`--strict`"
          "（仅 E1/E2 或 seed-strong E3；存在未决 E3/E4 可行动候选时 exit 1）/`--selftest`；",
          "- `registry/crossover/merge_candidates.json` 顶层：`meta`（规格/输入/图例/状态机）、"
          "`stats`、`bare_dispatch`（B0-B8 计数/转投/人工队列）、`candidates[]`；",
          "- `candidates[]` 关键字段：`candidate_id`、`source`、`members[{book,book_canonical,"
          "type,total,surfaces}]`（书内层）、`proposed_series{display_canonical,entity_id}`"
          "（系列层建议，不落库）、`evidence[{level,kind,authority_layer,loc,note}]`、"
          "`evidence_grade`、`conf`、`conflicts[]`、`suggested_action`、`merge_allowed`、"
          "`review{state,required,sampling,reviewer_a,reviewer_b,history}`；",
          "- 下游：approved 后由登记层工具按 `members` 生成 book_aliases / series_identities；"
          "`proposed_series.entity_id` 留空，由登记层按 D07 §4.3 不透明序号颁发（不复用）。", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- 主流程 ----
def run(books, strict=False, series_filter=None):
    t0 = time.time()
    reg_path = config.DIR_REGISTRY / "entities.json"
    reg, closure, by_id = load_registry(reg_path)
    conc = load_concordance(books)
    surface_idx = build_surface_index(conc)
    seeds, series_of, era_of, work_books = load_series_assets()
    edges = load_intertext()
    mapping = {b: load_mapping_latest(b) for b in books}
    stopwords = load_stopwords()
    artifacts = load_artifact_names()

    cands, stats, notes = generate_candidates(
        books, conc, surface_idx, reg, closure, by_id, seeds, series_of, era_of,
        edges, mapping, stopwords, artifacts, work_books, strict=strict,
        series_filter=series_filter)
    # 系列过滤（--series）："" = 仅保留同系列配对；NAME = 仅该系列
    if series_filter is not None:
        if series_filter:
            cands = [c for c in cands if c.get("series") == series_filter]
        else:
            cands = [c for c in cands
                     if len({series_of.get(m["book"]) for m in c["members"]}) == 1
                     and series_of.get(c["members"][0]["book"])]
        for i, c in enumerate(cands, 1):
            c["candidate_id"] = f"N6-{i:04d}"
    for c in cands:
        stats[f"grade_{c['evidence_grade']}"] += 1
    # 统计以最终候选为准（避免生成阶段多分支重复计数）
    gen_stats = Counter(stats)
    stats = Counter()
    for c in cands:
        stats[f"grade_{c['evidence_grade']}"] += 1
        stats[c["suggested_action"]] += 1
        if c.get("resolution"):
            stats[c["resolution"]] += 1
    for k in ("within_book_ambiguous", "reject_era_generic", "org_association_only",
              "strict_pending"):
        if gen_stats.get(k):
            stats[k] = gen_stats[k]
    stats["candidates_total"] = len(cands)
    stats["relay_edges"] = {"authorial": sum(1 for e in edges if e.get("kind") == "authorial"),
                            "quoted": sum(1 for e in edges if e.get("kind") == "quoted"),
                            "bare": sum(1 for e in edges if e.get("kind") == "bare")}
    bare_counts, transfers, review_items, bare_examples = classify_bare(
        edges, books, surface_idx, artifacts, work_books, stopwords)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    meta = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "spec_version": SPEC_VERSION,
        "books": books,
        "registry_total": len(reg),
        "intertext_total": len(edges),
        "seed_total": len(seeds),
        "elapsed_s": round(time.time() - t0, 2),
        "inputs": {
            "registry": str(reg_path.relative_to(config.ROOT)),
            "concordance": [f"registry/concordance/{b}.json" for b in books],
            "series": "kb/系列谱系考订表.json",
            "intertext": "kb/互文引用表.json",
            "works": "kb/作品元数据表.json",
            "mapping": [f"logs/mapping_{b}" for b in books],
        },
        "rules": "skills/SKILL_跨书治理_武侠版.md §2/§3/§4/§7.2/§8",
        "grading_legend": {
            "E1": "正文明示（互文 authorial 锚点 + 正文直证；可归并，抽验 5%）",
            "E2": "作者序跋后记（当前语料无独立序跋集 → 本批 0）",
            "E3": "情节暗示（同系列接力边/种子/引文；全量双人）",
            "E4": "读者推断/仅同名（只登记，不归并）",
        },
        "action_legend": {
            "merge": "E1/E2：可进入归并（E1 免双人抽验 5%；本工具不自动回写）",
            "proposal": "E3/E4：提案，进双人复核队列",
            "reject": "噪声/时代通称/已归并：记录理由，不归并",
        },
        "state_machine": ["pending", "pending_sample", "reviewer_a", "reviewer_b",
                          "approved", "rejected", "deferred"],
        "strict": bool(strict),
        "series_filter": series_filter or None,
        "strict_pending": stats.get("strict_pending", 0),
    }
    out_dir = config.DIR_REGISTRY / "crossover"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = config.DIR_LOGS / "crossover"
    log_dir.mkdir(parents=True, exist_ok=True)
    data_gaps = [
        "registry/entities.json 缺 book/series 列（D07 §4.5 series_identities schema）："
        "本工具用 concordance 反推书内层成员，回写前需登记层补 book 维度",
        "序跋/后记语料未独立成集：E2 级本批 0 条（接口已预留 source_channel=paratext）",
        "作品 ID（slug）未回填：loc_r 机锚暂以 {book}#pn-r{回}.{段} 形式给出并标 pending",
        "bare 边来自 34 书，但实体索引仅 5 书 → B1/B6 对未建书覆盖有限（B8 转人工兜底）",
        "registry sources 字段为回号而非书名：跨书成员判定以 concordance 为准",
    ]
    payload = {
        "meta": meta,
        "stats": dict(stats),
        "bare_dispatch": {
            "counts": bare_counts,
            "transfers": transfers,
            "review_items": review_items,
            "examples": bare_examples,
            "rules": "D07 §7.2 B0-B8",
        },
        "candidates": cands,
    }
    (out_dir / "merge_candidates.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / "review_queue.md").write_text(
        _render_review_queue(cands, stats, meta, transfers, review_items) + "\n",
        encoding="utf-8")
    report = _render_report(meta, stats, cands, bare_counts, transfers,
                            review_items, data_gaps)
    (log_dir / f"merge_crossover_{ts}.md").write_text(report + "\n", encoding="utf-8")
    (log_dir / f"summary_{ts}.json").write_text(
        json.dumps({"meta": meta, "stats": dict(stats), "bare_counts": bare_counts},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return payload, report, ts


# ---------------------------------------------------------------- selftest ----
def selftest():
    """合成夹具自检：不读项目数据、不写文件。"""
    fails = []

    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" [{detail}]"))
        if not cond:
            fails.append(name)

    # 1) 候选生成（合成）
    conc = {
        "甲书": {"张三": {"type": "@", "total": 10, "chapter_count": 2,
                          "variants": [{"display": "三哥", "count": 2}],
                          "registration": {"status": "registered"}},
                 "武当派": {"type": "◆", "total": 5, "chapter_count": 1, "variants": [],
                            "registration": {"status": "registered"}}},
        "乙书": {"张三": {"type": "@", "total": 8, "chapter_count": 1, "variants": [],
                          "registration": {"status": "registered"}},
                 "李四": {"type": "@", "total": 3, "chapter_count": 1, "variants": [],
                          "registration": {"status": "unregistered"}}},
    }
    surface_idx = build_surface_index(conc)
    check("surface index: 张三 in 2 books", len(surface_idx["张三"]) == 2)
    check("surface index: 三哥 alias", any(h["canonical"] == "张三" for h in surface_idx["三哥"]))
    reg = [{"id": "E1", "type": "@", "canonical": "张三", "aliases": ["三哥"],
            "contextual": [], "status": "approved"}]
    closure, by_id = {}, {}
    for e in reg:
        by_id[e["id"]] = e
        for s in [e["canonical"]] + e["aliases"]:
            closure[s] = e["id"]
    seeds = [{"name": "张三（三哥）", "books": ["甲书", "乙书"], "note": "test"}]
    series_of = {"甲书": "测试系列", "乙书": "测试系列"}
    era_of = {"甲书": "明", "乙书": "清"}
    edges = [{"source": "乙书", "target": "甲书", "kind": "authorial",
              "probe": "甲书", "loc": "001:1", "snippet": "详见拙著《甲书》"}]
    mapping = {"甲书": {"皇上": "甲帝"}, "乙书": {"皇上": "乙帝"}}
    stopwords = set(ERA_GENERIC) | {"三哥"}
    cands, stats, _ = generate_candidates(
        ["甲书", "乙书"], conc, surface_idx, reg, closure, by_id, seeds,
        series_of, era_of, edges, mapping, stopwords, set(), {"甲书", "乙书"})
    ids = {c["candidate_id"] for c in cands}
    check("candidate: 有候选", bool(cands), str(stats))
    check("candidate: 种子已归并→reject/already_merged",
          any(c.get("source") == ["series_seed"] and c.get("resolution") == "already_merged"
              for c in cands))
    check("candidate: 同 surface 映射分歧→reject(era_generic)",
          any(c["source"] == ["mapping_divergence"] and c["suggested_action"] == "reject"
              for c in cands))
    check("candidate: 编号连续", all(c["candidate_id"].startswith("N6-") for c in cands))
    # 2) 分级规则
    g1, ev1 = _grade_same_canonical("张三", {"甲书": {}, "乙书": {}}, series_of, era_of,
                                    edges, by_id, closure, mapping, [])
    check("grade: 同名跨书最高 E3（authorial 不自动归并）", g1 == "E3", g1)
    diff_members = [{"book": "甲书", "book_canonical": "张三", "type": "@", "total": 10},
                    {"book": "乙书", "book_canonical": "三哥", "type": "@", "total": 8}]
    gd, _ = _grade_diff_canonical("张三", diff_members, series_of, era_of, edges,
                                  by_id, closure, mapping, [])
    check("grade: registry 别名闭包 + authorial 锚点 → E1", gd == "E1", gd)
    g2, _ = _grade_same_canonical("李四", {"甲书": {}, "乙书": {}}, series_of, era_of,
                                  [], by_id, closure, mapping, [])
    check("grade: 无证据 → E4", g2 == "E4", g2)
    check("grade: E4 merge_allowed=False", MERGE_ALLOWED["E4"] is False)
    # 3) 双层 canonical
    members = [{"book": "甲书", "book_canonical": "张三", "total": 10},
               {"book": "乙书", "book_canonical": "张三", "total": 8}]
    ps = _propose_series(members, False, None, by_id)
    check("dual-layer: display_canonical 取高频名", ps["display_canonical"] == "张三", str(ps))
    check("dual-layer: entity_id 不预分配", ps["entity_id"] is None)
    # 4) bare B0-B8
    bare_edges = [
        {"kind": "bare", "probe": "江湖", "source": "甲书", "target": "乙书", "loc": "001:1",
         "snippet": "江湖"},
        {"kind": "bare", "probe": "张三", "source": "甲书", "target": "乙书", "loc": "001:2",
         "snippet": "张三"},
        {"kind": "bare", "probe": "甲书", "source": "乙书", "target": "甲书", "loc": "002:1",
         "snippet": "详见拙著《甲书》"},
        {"kind": "bare", "probe": "乙书", "source": "甲书", "target": "乙书", "loc": "003:1",
         "snippet": "想当年，乙书"},
        {"kind": "bare", "probe": "甲书传", "source": "乙书", "target": "甲书", "loc": "004:1",
         "snippet": "甲书传下两个徒弟"},
        {"kind": "bare", "probe": "未知词", "source": "甲书", "target": "乙书", "loc": "005:1",
         "snippet": "未知词"},
    ]
    counts, transfers, review, _ = classify_bare(
        bare_edges, ["甲书", "乙书"], surface_idx, set(), {"甲书", "乙书"}, stopwords)
    check("bare: B0 噪声", counts.get("B0", 0) == 1, str(counts))
    check("bare: B1 转投", counts.get("B1", 0) == 1 and transfers, str(counts))
    check("bare: B5 升级", counts.get("B5", 0) == 1, str(counts))
    check("bare: B4 事件称名", counts.get("B4", 0) == 1, str(counts))
    check("bare: B2 分词陷阱", counts.get("B2", 0) == 1, str(counts))
    check("bare: B8 兜底转人工", counts.get("B8", 0) == 1 and review, str(counts))
    # 5) 状态机/复核门槛
    st = _review_state("E1")
    check("review: E1 pending_sample", st["state"] == "pending_sample" and not st["required"])
    st3 = _review_state("E3")
    check("review: E3 双人必审", st3["required"] and st3["state"] == "pending")
    # 6) 严格模式
    strict_cands, _, _ = generate_candidates(
        ["甲书", "乙书"], conc, surface_idx, reg, closure, by_id, seeds, series_of,
        era_of, edges, mapping, stopwords, set(), {"甲书", "乙书"}, strict=True)
    check("strict: 仅 E1/E2 或 seed-strong E3",
          all(c["evidence_grade"] in ("E1", "E2") or
              (c["evidence_grade"] == "E3" and c["conf"] == "strong" and c.get("seed"))
              for c in strict_cands), str([c["evidence_grade"] for c in strict_cands]))
    print("\nRESULT:", "PASS" if not fails else f"FAIL {len(fails)}: {fails}")
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(
        description="N6 跨书归并工作台（只产候选+复核队列，不自动合并 registry）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="处理全部有 concordance 的书")
    g.add_argument("--series", nargs="?", const="", default=None, metavar="NAME",
                   help="按系列过滤：不带值=仅同系列配对；带值=仅该系列")
    g.add_argument("--selftest", action="store_true", help="合成夹具自检（不读写项目数据）")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式：仅输出 E1/E2 或 seed-strong E3 候选；存在 E3/E4 未决时 exit 1")
    ap.add_argument("--book", action="append", default=None, help="限定书（可多次）")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.book:
        books = [b for b in args.book if b in DEFAULT_BOOKS] or DEFAULT_BOOKS
    else:
        books = [b for b in DEFAULT_BOOKS
                 if (config.DIR_REGISTRY / "concordance" / f"{b}.json").exists()]
    if len(books) < 2:
        print("[N6] 错误：可用 concordance 少于 2 书", file=sys.stderr)
        return 2
    series_filter = None
    if args.series is not None:
        series_filter = args.series or ""   # "" = 仅同系列
    payload, report, ts = run(books, strict=args.strict, series_filter=series_filter)
    st = payload["stats"]
    print(f"[N6] 候选 {st.get('candidates_total',0)} 条："
          f"E1 {st.get('grade_E1',0)} / E2 {st.get('grade_E2',0)} / "
          f"E3 {st.get('grade_E3',0)} / E4 {st.get('grade_E4',0)}；"
          f"merge {st.get('merge',0)} / proposal {st.get('proposal',0)} / "
          f"reject {st.get('reject',0)}")
    print(f"[N6] 输出：registry/crossover/merge_candidates.json、"
          f"registry/crossover/review_queue.md、logs/crossover/merge_crossover_{ts}.md")
    if args.strict and payload["meta"].get("strict_pending"):
        print(f"[N6][strict] 仍有 {payload['meta']['strict_pending']} 条 E3/E4 "
              "可行动候选未决 → exit 1", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
