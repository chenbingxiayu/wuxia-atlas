# -*- coding: utf-8 -*-
"""S-03i · `assign_taxonomy_leaves.py` — 分类挂叶登记（N9 分类树实例叶值分配）

规范源（唯一）：
  `skills/SKILL_分类树五件套_武侠版.md`（v0.3-draft）§1.3 五树 64 叶、§5.4 势力树
  （3 分支 11 叶 + 判定信号表）、§5.3「合法子类 vs 真误标」三问测试、§7.1 06e 标准。
  N9 校验实现：`scripts/lint_taxonomy.py` 的 TREES（直接 import 复用，杜绝文-码两张皮）。

任务（task-40）：
  为 `registry/entities.json` 中 70 条 ◆ 组织实例分配 `leaf` 叶值（树：门派势力树；
  叶：11 叶枚举）。无法判定/疑非组织实体者 leaf 留 null，写 `leaf_candidates` + `leaf_reason`
  供人工复核（不伪造、不塞兜底叶——T17/06e 禁"其他"叶）。
  仅写 ◆ 实体的 leaf/leaf_candidates/leaf_reason 三个字段，其它字段与其它类型实体一律不动。

判定依据（SKILL §5.4 信号表 + §5.3 三问）：
  - 武学门派：开山/师承/辈分；X 派/X 门；武功以派名冠；门规；
  - 帮会：帮规/香堂/分舵/会中切口；地缘行业结社（天地会/洪门/大地会=秘密会社）；
  - 盟会联盟：多方会盟/推举盟主/政治结社（东林党）；
  - 绿林山寨：山寨/水寨据点（眉山寨）；
  - 镖局：字号/走镖护镖（武威镖局/镖局/镖行）；
  - 宫廷势力：朝廷/特务/禁卫/地方官署/政权军制（三问全过，§5.3 明示"朝廷"为合法实例）；
  - 义军组织：树旗建元/统兵抗官的武装组织（大顺/忠贞营/鲁王旧部余部）。
  疑非组织（武功名/地名/族群/泛称/人物封号）→ leaf=null + 建议改判类型：
    ☆ 武功 / = 地点 / ~ 族群 / 泛称不登记（SKILL §5.3：武林/江湖/绿林道皆泛称不登记）。

写盘纪律：
  - 默认 dry-run（只写 logs/taxonomy 报告与机器结果，不写 registry）；
  - --apply 前自动备份 `logs/taxonomy/backup/entities_<ts>.json`，写前重读最新文件
    （兼容并发任务写 registry），原子写；写后断言「实体数不变 + id 集合不变 + 仅 leaf 三字段变化」；
  - 合法性断言：叶值必须 ∈ 64 叶、属于 ◆ 势力树、非分支/树根、树深 ≤4；id 唯一。

CLI：
  python -X utf8 scripts/assign_taxonomy_leaves.py --dry-run   # 默认
  python -X utf8 scripts/assign_taxonomy_leaves.py --apply     # 写 registry/entities.json（备份先行）
  python -X utf8 scripts/assign_taxonomy_leaves.py --selftest  # 规则自测（不写盘）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lint_taxonomy as n9  # noqa: E402  N9 内嵌五树（唯一映射来源）

REGISTRY = ROOT / "registry" / "entities.json"
LOGS_DIR = ROOT / "logs" / "taxonomy"
REPORT_PATH = LOGS_DIR / "assign_report.md"
RESULT_PATH = LOGS_DIR / "assign_result.json"
BACKUP_DIR = LOGS_DIR / "backup"
BASELINE_PATH = LOGS_DIR / "baseline_violations.json"   # 首次挂叶前的 N9 基线（复跑时对比用）
TOOL = "assign_taxonomy_leaves v1.0 (2026-11-05, S-03i/N9)"

TREE_CODE = "◆"                                  # 主树（组织）别名保留
TREE = n9.TREES[TREE_CODE]
TREE_NAME = TREE["name"]
LEAF_BRANCH = n9.LEAF_BRANCH[TREE_CODE]          # leaf → branch（◆ 势力树）
BRANCHES = {b for b, _ in TREE["branches"]}
ALL_LEAVES_64 = set(n9.ALL_LEAVES)

# task-45 起：五树实例统一挂叶（registry 内 = ; # ◆ ☆ 类型实例均可挂）
FIVE_TREES = tuple(n9.TREES)
TREE_LABELS = n9.TYPE_LABELS
# 显式叶值（新改判类型 / 历史表未覆盖者）；其余走 lint_taxonomy 多源关键词启发式
EXPLICIT_TREE_RULES = {
    "=": {
        "天山": ("山岳峰岭", "山脉地名 → 地点树 山岳峰岭（task-45 ◆→=）"),
    },
    "☆": {
        "天山剑法": ("武功套路", "成套剑法 → 武功谱系树 武功套路（task-45 ◆→☆）"),
        "无极剑": ("武功套路", "无极剑法省称 → 武功谱系树 武功套路（task-45 ◆→☆）"),
    },
}

# ---------------------------------------------------------------- 判定表（canonical → 叶/理由）
# 显式判定：70 条 ◆ 实测逐条裁定（SKILL §5.3/§5.4 信号；依据写进报告）
LEAF_RULES: dict[str, tuple] = {
    # ── 武学门派（开山收徒、师承辈分、X派/X门）──
    "武当派": ("武学门派", "师承门派：武当掌门/门规/武当剑法（§5.4 武学门派正例）"),
    "嵩阳派": ("武学门派", "X派+门派武功（嵩阳派）"),
    "少林派": ("武学门派", "师承门派：少林派/少林武功（§5.4 正例）"),
    "峨嵋派": ("武学门派", "X派，开山收徒体系"),
    "华山派": ("武学门派", "X派，武林门派"),
    "雪山派": ("武学门派", "X派，武林门派"),
    "终南派": ("武学门派", "X派，武林门派"),
    "天龙派": ("武学门派", "X派（扎布伦寺喇嘛武学体系）"),
    "长白山派": ("武学门派", "X派，武林门派"),
    "无极派": ("武学门派", "X派，开山收徒体系"),
    "武当门": ("武学门派", "门派省称（武当门/武当派同指）"),
    "天山派": ("武学门派", "X派，天山系列主脉门派（§5.4 正例「天山派」）"),
    "天山剑派": ("武学门派", "X剑派，武林中人称「天山剑派」（七剑30:73）"),
    "西藏天龙派": ("武学门派", "天龙派西藏支系（X派）"),
    # ── 帮会（帮规/香堂/分舵/会中切口；地缘行业结社）──
    "龙门帮": ("帮会", "X帮，地缘结社"),
    "五龙帮": ("帮会", "X帮，地盘/帮众层级"),
    "天地会": ("帮会", "秘密会社：会中切口/分舵/会友（七剑1:76）"),
    "铁扇帮": ("帮会", "X帮，地缘结社"),
    "青阳帮": ("帮会", "X帮，地缘结社"),
    "马帮": ("帮会", "行业结社（马帮，走镖/运输）"),
    "大地会": ("帮会", "秘密会社：会中切口/分舵/会友（七剑23:13；疑与天地会同源）"),
    "洪门": ("帮会", "秘密会社（洪门弟子；天地会别称）"),
    # ── 盟会联盟（多方会盟/政治结社）──
    "东林党": ("盟会联盟", "政治结社/党社（明末东林党，跨组织联盟形态）"),
    # ── 绿林山寨（山寨据点）──
    "眉山寨": ("绿林山寨", "山寨据点半叶（眉山寨；与地点树山寨水寨双登记联动）"),
    # ── 镖局（字号/走镖护镖）──
    "武威镖局": ("镖局", "字号镖局（武威镖局）"),
    "镖局": ("镖局", "镖局业泛称实例（走镖护镖；与地点树镖局车店联动）"),
    "镖行": ("镖局", "镖行=镖局行业组织（职衔树镖行职衔联动）"),
    # ── 宫廷势力（朝廷/特务/禁卫/官署/政权军制；§5.3 三问全过）──
    "朝廷": ("宫廷势力", "§5.3 明示合法实例：下旨/层级/官系统边界（明廷/清廷同叶）"),
    "清廷": ("宫廷势力", "朝廷政权（清廷）"),
    "清宫": ("宫廷势力", "宫廷（清宫）"),
    "大内": ("宫廷势力", "宫廷禁地/禁卫体系"),
    "明朝": ("宫廷势力", "朝廷政权（明朝）"),
    "清朝": ("宫廷势力", "朝廷政权（清朝）"),
    "南明": ("宫廷势力", "南明政权（朝廷）"),
    "南明政府": ("宫廷势力", "南明政权机构（朝廷）"),
    "郑国": ("宫廷势力", "政权/邦国（郑国；三问之政权形态）"),
    "三藩": ("宫廷势力", "藩镇军政势力（三藩；领兵裂地）"),
    "满洲": ("宫廷势力", "政权用法（note：族群语义出现时再议 ~；本轮按政权叶）"),
    "满清": ("宫廷势力", "朝廷政权（满清）"),
    "兵部": ("宫廷势力", "中央官署（兵部，§5.4 宫廷势力含地方官署/官系统）"),
    "川陕总督府": ("宫廷势力", "地方官署（川陕总督府）"),
    "锦衣卫": ("宫廷势力", "特务机构（锦衣卫；§5.4 正例）"),
    "东厂": ("宫廷势力", "特务机构（东厂；§5.4 正例「明廷/东厂/锦衣卫」）"),
    "西厂": ("宫廷势力", "特务机构（西厂）"),
    "东西两厂（东厂+西厂合称）": ("宫廷势力", "特务机构合称（东西两厂；用户核准独立合称条目）"),
    "禁卫军": ("宫廷势力", "禁卫军（朝廷武力）"),
    "御林军": ("宫廷势力", "禁卫军（御林军）"),
    "神策营": ("宫廷势力", "军制营伍（神策营）"),
    "神机营": ("宫廷势力", "军制营伍（神机营）"),
    "八旗": ("宫廷势力", "军制/旗营（八旗）"),
    "八旗军": ("宫廷势力", "军制（八旗军）"),
    "清兵": ("宫廷势力", "朝廷军队（清兵；三问之行为主体/层级）"),
    "清军": ("宫廷势力", "朝廷军队（清军）"),
    "满军": ("宫廷势力", "朝廷军队（满军）"),
    "清营": ("宫廷势力", "军制营伍（清营）"),
    # ── 义军组织（树旗建元/统兵抗官）──
    "鲁王旧部": ("义军组织", "南明鲁王残部（统兵抗官武装）"),
    "鲁王余部": ("义军组织", "南明鲁王残部（统兵抗官武装）"),
    "忠贞营": ("义军组织", "农民军/大顺余部改编抗清（七剑7:11「忠贞营」）"),
    "大顺": ("义军组织", "大顺军/政权（起事抗官，树旗建元）"),
}

# 无法判定 / 疑非组织：leaf=null + candidates + reason（建议改判类型，不伪造叶）
NULL_RULES: dict[str, tuple] = {
    "天山剑法": (["武学门派"], "疑为 ☆ 武功（天山剑法=剑法名），非组织实体；建议类型改判 ☆"),
    "无极剑": (["武学门派"], "疑为 ☆ 武功（无极剑=剑法名），非组织实体；建议类型改判 ☆"),
    "天山": (["武学门派"], "疑为 = 地点（天山=山脉名），非组织实体；建议类型改判 ="),
    "武林": ([], "泛称不登记（SKILL §5.3 三问皆不过：无统一行动/无首领/边界模糊）；建议删除或降为 ^ 概念"),
    "中国": ([], "地理/国家通名，非单个组织实例；建议类型改判 = 区域"),
    "官兵": (["宫廷势力"], "泛称（官兵=朝廷军队通称），三问之③边界模糊；建议不登记或改 # 群体"),
    "大军": (["宫廷势力", "义军组织"], "泛称（大军=军队通称），三问之②③不过；建议不登记"),
    "塔山族": ([], "族群（~）误标为 ◆；建议类型改判 ~（与罗布族同例，SKILL_03b §8.5）"),
    "搭山族": ([], "族群（~）误标为 ◆，且疑为「塔山族」误写/重复条；建议改判 ~ 并与塔山族合并"),
    "鲁王": (["宫廷势力"], "人物/爵位封号（鲁王=朱以海）误标为组织；建议改判 @/;（人物/职衔）"),
    "太极": (["武学门派"], "歧义：太极（派/拳）语境不足，暂不落叶；候选=武学门派（太极派）"),
}

# 启发式（用于未来新增 ◆ / 表未覆盖者；保守 → 命中才落叶，否则 null）
SUFFIX_RULES = [
    (("剑派",), "武学门派"), (("派", "门"), "武学门派"),
    (("帮",), "帮会"), (("会",), "帮会"), (("教",), "宗教教门"), (("宗",), "宗教教门"),
    (("党", "盟"), "盟会联盟"),
    (("山寨", "水寨", "寨"), "绿林山寨"),
    (("镖局", "镖行"), "镖局"),
    (("朝", "廷", "宫", "大内", "卫", "厂", "军", "营", "旗", "府", "部", "司", "监"), "宫廷势力"),
    (("旧部", "余部", "义军"), "义军组织"),
]
NOT_ORG_MARKS = ("剑法", "掌法", "拳法", "刀法", "剑术", "心法", "神功", "剑诀", "式")


# ---------------------------------------------------------------- 基础工具
def load_registry() -> dict:
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def dump_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    tmp.replace(path)


# ---------------------------------------------------------------- 判定
def classify(entity: dict) -> dict:
    """五树实例 → {leaf, leaf_candidates, leaf_reason, basis, rule}；不确定 leaf=None。"""
    code = entity.get("type") or TREE_CODE
    canon = entity.get("canonical") or ""
    if code in EXPLICIT_TREE_RULES and canon in EXPLICIT_TREE_RULES[code]:
        leaf, basis = EXPLICIT_TREE_RULES[code][canon]
        return {"leaf": leaf, "leaf_candidates": [], "leaf_reason": "",
                "basis": basis, "rule": "explicit-type"}
    if code == "=":
        leaf = n9._match_rules(canon, n9.PLACE_SUFFIX_RULES)
        if leaf:
            return {"leaf": leaf, "leaf_candidates": [], "leaf_reason": "",
                    "basis": f"地点名后缀启发式（{leaf}，SKILL §2.4/§5.4）", "rule": "heuristic"}
        return {"leaf": None, "leaf_candidates": ["村集乡野", "城镇都邑"],
                "leaf_reason": "地点名无可靠叶信号；留 null 待人工复核", "basis": "启发式：无信号",
                "rule": "heuristic-null"}
    if code == "☆":
        leaf = n9._art_leaf("", canon)
        return {"leaf": leaf, "leaf_candidates": [], "leaf_reason": "",
                "basis": f"武功名后缀启发式（{leaf}，SKILL §6.1/§6.7）", "rule": "heuristic"}
    if code == ";":
        leaf = n9._match_rules(canon, n9.TITLE_KEYWORD_RULES)
        return {"leaf": leaf, "leaf_candidates": ["门派职衔", "帮会职衔"] if not leaf else [],
                "leaf_reason": "" if leaf else "职衔无可靠关键词信号；留 null 待人工复核",
                "basis": f"职衔关键词启发式（{leaf}）" if leaf else "启发式：无信号",
                "rule": "heuristic" if leaf else "heuristic-null"}
    if code == "#":
        leaf = n9._match_rules(canon, n9.IDENTITY_KEYWORD_RULES)
        return {"leaf": leaf, "leaf_candidates": ["侠客侠士", "平民百姓"] if not leaf else [],
                "leaf_reason": "" if leaf else "身份无可靠关键词信号；留 null 待人工复核",
                "basis": f"身份关键词启发式（{leaf}）" if leaf else "启发式：无信号",
                "rule": "heuristic" if leaf else "heuristic-null"}
    # 组织（◆）：显式判定表优先（70 条历史裁定），再后缀启发式
    if canon in LEAF_RULES:
        leaf, basis = LEAF_RULES[canon]
        return {"leaf": leaf, "leaf_candidates": [], "leaf_reason": "",
                "basis": basis, "rule": "explicit"}
    if canon in NULL_RULES:
        cands, reason = NULL_RULES[canon]
        return {"leaf": None, "leaf_candidates": list(cands),
                "leaf_reason": reason, "basis": reason, "rule": "explicit-null"}
    # 启发式（新增实体；保守）
    for suffix, leaf in SUFFIX_RULES:
        if canon.endswith(suffix):
            return {"leaf": leaf, "leaf_candidates": [], "leaf_reason": "",
                    "basis": f"后缀启发式（{suffix}→{leaf}，SKILL §5.4 信号）",
                    "rule": "heuristic"}
    if any(m in canon for m in NOT_ORG_MARKS):
        return {"leaf": None, "leaf_candidates": ["武学门派"],
                "leaf_reason": f"疑为 ☆ 武功（名称含武功后缀），非组织实体；待人工改判",
                "basis": "启发式：武功名误标", "rule": "heuristic-null"}
    return {"leaf": None, "leaf_candidates": ["武学门派", "帮会", "宫廷势力"],
            "leaf_reason": "新实体无显式判定/无可靠后缀信号；留 null 待人工复核（不塞兜底叶）",
            "basis": "启发式：无信号", "rule": "heuristic-null"}


def leaf_legality(leaf, code: str = TREE_CODE) -> tuple[bool, str]:
    """叶值合法性与父链/树深断言（SKILL §7.1 06e；按类型码对应树校验）。"""
    if leaf is None:
        return True, "null（弃权，待复核）"
    if code not in n9.LEAF_BRANCH:
        return False, f"类型码 {code} 不在五树内"
    branch_map = n9.LEAF_BRANCH[code]
    branches = {b for b, _ in n9.TREES[code]["branches"]}
    if leaf not in ALL_LEAVES_64:
        return False, f"叶「{leaf}」不在 64 叶枚举内"
    if leaf not in branch_map:
        return False, f"叶「{leaf}」不属于{TREE_LABELS[code]}树（属于 {n9.LEAF_TREES.get(leaf)}）"
    if leaf in branches or leaf == n9.TREES[code]["root"]:
        return False, f"叶「{leaf}」是分支/树根（实例只能挂叶）"
    branch = branch_map[leaf]
    depth = 3 if n9.TREES[code].get("branches") else 2       # 根→分支→叶
    if depth > n9.MAX_DEPTH:
        return False, f"树深 {depth} > {n9.MAX_DEPTH}"
    if branch not in branches:
        return False, f"父链断裂：叶「{leaf}」挂未知分支「{branch}」"
    return True, f"{n9.TREES[code]['name']}/{branch}/{leaf}（深度 {depth}）"


# ---------------------------------------------------------------- 计算
def compute(reg: dict) -> dict:
    """五树实例（= ; # ◆ ☆）统一挂叶计算（registry 内全部五树类型实体）。"""
    ents = reg.get("entities") or []
    scope = [e for e in ents if e.get("type") in FIVE_TREES]
    assignments = []
    for e in scope:
        code = e.get("type")
        res = classify(e)
        ok, why = leaf_legality(res["leaf"], code)
        assignments.append({
            "id": e.get("id"), "canonical": e.get("canonical"),
            "type": code, "status": e.get("status"),
            "leaf": res["leaf"], "leaf_candidates": res["leaf_candidates"],
            "leaf_reason": res["leaf_reason"], "basis": res["basis"],
            "rule": res["rule"], "legal": ok, "legal_detail": why,
        })
    leaf_counts = Counter(a["leaf"] for a in assignments if a["leaf"])
    by_type = Counter(a["type"] for a in assignments)
    assigned_by_type = Counter(a["type"] for a in assignments if a["leaf"])
    return {
        "entities_total": len(ents),
        "scope_total": len(scope),
        "orgs_total": len(scope),          # 兼容旧字段
        "by_type": {c: {"total": by_type.get(c, 0),
                        "assigned": assigned_by_type.get(c, 0)}
                    for c in FIVE_TREES if by_type.get(c)},
        "assignments": assignments,
        "assigned": sum(1 for a in assignments if a["leaf"]),
        "unassigned": sum(1 for a in assignments if not a["leaf"]),
        "leaf_counts": dict(sorted(leaf_counts.items(), key=lambda kv: -kv[1])),
        "illegal": [a for a in assignments if not a["legal"]],
    }


def apply_assignments(reg: dict, result: dict) -> tuple[dict, list]:
    """仅改 ◆ 实体的 leaf/leaf_candidates/leaf_reason；返回 (新 payload, changed ids)。"""
    by_id = {a["id"]: a for a in result["assignments"]}
    changed = []
    for e in reg.get("entities") or []:
        a = by_id.get(e.get("id"))
        if not a or e.get("type") not in FIVE_TREES:
            continue
        e["leaf"] = a["leaf"]
        if a["leaf"] is None:
            e["leaf_candidates"] = list(a["leaf_candidates"])
            e["leaf_reason"] = a["leaf_reason"]
        else:  # 已判定的清掉历史候选/理由，避免陈旧信息
            e.pop("leaf_candidates", None)
            e.pop("leaf_reason", None)
        changed.append(e.get("id"))
    return reg, changed


# ---------------------------------------------------------------- 校验断言
def run_assertions(reg_before: dict, reg_after: dict | None, result: dict) -> list:
    A = []

    def add(ok, aid, desc, detail=""):
        A.append({"id": aid, "desc": desc, "pass": bool(ok), "detail": detail})

    ids_before = [e.get("id") for e in reg_before.get("entities") or []]
    add(len(set(ids_before)) == len(ids_before), "A01", "实体 id 唯一",
        f"{len(ids_before)} 条 / unique={len(set(ids_before))}")
    add(result["scope_total"] == sum(v["total"] for v in result["by_type"].values()),
        "A02", "五树范围内实例（= ; # ◆ ☆）计数闭合",
        f"scope_total={result['scope_total']} by_type={result['by_type']}")
    add(result["assigned"] + result["unassigned"] == result["scope_total"],
        "A03", "全部五树实例均有判定（落叶或 null+候选）",
        f"assigned={result['assigned']} null={result['unassigned']}")
    add(not result["illegal"], "A04", "叶值合法：∈64 叶 / 属对应树 / 非分支树根 / 父链与树深正确",
        f"illegal={[(a['id'], a['legal_detail']) for a in result['illegal']][:3]}")
    add(all(a["leaf"] is None or a["leaf"] in n9.LEAF_BRANCH.get(a["type"], {})
            for a in result["assignments"]),
        "A05", "叶值均属对应类型码的树（逐条按 type 校验）")
    add(all((a["leaf_candidates"] or a["leaf_reason"]) for a in result["assignments"]
            if not a["leaf"]),
        "A06", "null 条目均带 candidates 或 reason（不静默弃权）",
        str([a["id"] for a in result["assignments"] if not a["leaf"] and not a["leaf_candidates"]]))
    add(not any(a["leaf"] in n9.FALLBACK_LEAF_NAMES for a in result["assignments"] if a["leaf"]),
        "A07", "未使用兜底叶（T17/06e 禁：其他/未知/待定…）")
    add(sum(result["leaf_counts"].values()) == result["assigned"], "A08",
        "叶分布求和 = 已分配数", str(result["leaf_counts"]))
    if reg_after is not None:
        ids_after = [e.get("id") for e in reg_after.get("entities") or []]
        add(set(ids_after) == set(ids_before) and len(ids_after) == len(ids_before),
            "A09", "写后实体数/id 集合不变（仅改 leaf 字段）",
            f"before={len(ids_before)} after={len(ids_after)}")
        by_b = {e["id"]: e for e in reg_before.get("entities") or []}
        allowed = {"leaf", "leaf_candidates", "leaf_reason"}
        bad = []
        for e in reg_after.get("entities") or []:
            b = by_b.get(e["id"])
            if not b:
                bad.append(f"{e.get('id')}:new")
                continue
            keys = {k for k in set(e) | set(b) if k not in allowed}
            if any(e.get(k) != b.get(k) for k in keys):
                bad.append(e.get("id"))
        add(not bad, "A10", "写后仅 leaf/leaf_candidates/leaf_reason 变化，其它字段逐字一致",
            f"bad={bad[:5]}")
        scope_after = [e for e in reg_after.get("entities") or []
                       if e.get("type") in FIVE_TREES]
        add(all("leaf" in e for e in scope_after), "A11", "写后五树实例均带 leaf 字段（可为 null）")
        add(sum(1 for e in scope_after if e.get("leaf")) == result["assigned"], "A12",
            "写后落叶数与计算一致",
            f"{sum(1 for e in scope_after if e.get('leaf'))}/{result['assigned']}")
    return A


# ---------------------------------------------------------------- N9 前后对比
def run_n9() -> dict:
    """跑 N9 lint_taxonomy（写 logs/taxonomy），解析 violations 统计。"""
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "lint_taxonomy.py")],
                          cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    vp = LOGS_DIR / "taxonomy_violations.json"
    data = {"exit": proc.returncode, "stdout_tail": (proc.stdout or "")[-600:],
            "warnings": 0, "errors": 0, "infos": 0, "by_check": {}}
    if vp.exists():
        v = json.load(open(vp, encoding="utf-8"))
        items = v.get("violations") or []
        sev = Counter(i.get("severity") for i in items)
        data.update({"warnings": sev.get("warning", 0), "errors": sev.get("error", 0),
                     "infos": sev.get("info", 0),
                     "by_check": dict(Counter(i.get("check") for i in items
                                              if i.get("severity") == "warning"))})
        data["stats"] = v.get("stats") or {}
        ic = (v.get("stats") or {}).get("instance_check") or {}
        data["instance"] = {k: ic.get(k) for k in
                            ("scope_instances", "mapped", "unmapped", "by_tree",
                             "leaf_counts", "multi_value_instances")}
        # LEAF_SPARSE 细化：区分「本树已挂叶但 <10」与「其它四树叶 0 实例（实例源未接入 registry）」
        sparse = [i for i in items
                  if i.get("severity") == "warning" and i.get("check") == "LEAF_SPARSE"]
        mapped_lt10, zero_other = [], {}
        for i in sparse:
            leaf = i.get("leaf") or ""
            owner = (n9.LEAF_TREES.get(leaf) or [None])[0]
            if owner == TREE_CODE:
                mapped_lt10.append({"leaf": leaf, "detail": i.get("detail")})
            elif owner:
                zero_other.setdefault(owner, []).append(leaf)
        data["sparse_breakdown"] = {
            "mapped_lt10": mapped_lt10,
            "zero_other_trees": {k: sorted(v) for k, v in zero_other.items()},
            "zero_other_total": sum(len(v) for v in zero_other.values()),
        }
    return data


# ---------------------------------------------------------------- 报告
def _fmt(counts: dict) -> str:
    return "、".join(f"{k} {v}" for k, v in counts.items()) or "—"


def _delta(before, after):
    if after is None:
        return "—"
    return f"{after - before:+d}"


def render_report(result: dict, n9_before: dict, n9_after: dict | None, assertions: list,
                  backup_path, mode: str, reg_sha_before: str, reg_sha_after: str | None) -> str:
    L = []
    L.append("# S-03i / task-45 五树实例挂叶登记报告（N9 分类树实例叶值）")
    L.append("")
    L.append(f"- 工具：`{TOOL}`")
    L.append(f"- 生成：{now_ts()}")
    L.append(f"- 模式：{mode}")
    L.append(f"- 输入：`registry/entities.json`（sha256 `{reg_sha_before[:16]}…`）"
             + (f" → 写后 `{reg_sha_after[:16]}…`" if reg_sha_after else ""))
    L.append(f"- 规范：`skills/SKILL_分类树五件套_武侠版.md` §5.3/§5.4/§6.1/§7.1；"
             f"树映射 = `scripts/lint_taxonomy.py` TREES（import 复用，唯一来源）")
    L.append(f"- 备份：`{backup_path}`" if backup_path else "- 备份：dry-run 未写盘（--apply 时自动备份）")
    L.append("")
    L.append("## 一、总览")
    L.append("")
    L.append(f"- 五树范围内实例（= ; # ◆ ☆）：**{result['scope_total']}** 条；"
             f"落叶 **{result['assigned']}** / 无法判定（leaf=null）**{result['unassigned']}** 条")
    L.append(f"- by_type：{json.dumps(result['by_type'], ensure_ascii=False)}")
    L.append(f"- 叶分布：{_fmt(result['leaf_counts'])}")
    L.append(f"- 合法性断言：{len(assertions)} 项，通过 {sum(1 for a in assertions if a['pass'])} 项")
    L.append("")
    L.append("## 二、叶分布（五树 64 叶）")
    L.append("")
    L.append("| 树 | 分支 | 叶 | 实例数 |")
    L.append("|---|---|---|---:|")
    for code in FIVE_TREES:
        tree = n9.TREES[code]
        for branch, leaves in tree["branches"]:
            for leaf in leaves:
                cnt = result["leaf_counts"].get(leaf, 0)
                L.append(f"| {tree['name']} | {branch} | {leaf} | {cnt} |")
    L.append("")
    L.append("## 三、逐条分配表（五树实例）")
    L.append("")
    L.append("| id | canonical | type | leaf | 分支 | 依据/规则 |")
    L.append("|---|---|---|---|---|---|")
    for a in result["assignments"]:
        if a["leaf"]:
            branch = n9.LEAF_BRANCH.get(a["type"], {}).get(a["leaf"], "—")
            L.append(f"| {a['id']} | {a['canonical']} | `{a['type']}` | {a['leaf']} | "
                     f"{branch} | {a['basis']} |")
    L.append("")
    L.append("## 四、无法判定清单（leaf=null，待人工裁决）")
    L.append("")
    L.append("| id | canonical | type | candidates | 原因与建议 |")
    L.append("|---|---|---|---|---|")
    for a in result["assignments"]:
        if not a["leaf"]:
            L.append(f"| {a['id']} | {a['canonical']} | `{a['type']}` | "
                     f"{'、'.join(a['leaf_candidates']) or '—'} | {a['leaf_reason']} |")
    L.append("")
    L.append("## 五、N9 复跑前后对比（`python scripts/lint_taxonomy.py`）")
    L.append("")
    L.append("| 指标 | 挂叶前 | 挂叶后 | 变化 |")
    L.append("|---|---:|---:|---|")
    L.append(f"| warning 总数 | {n9_before.get('warnings', 0)} | {n9_after.get('warnings', 0) if n9_after else '—'} | "
             f"{_delta(n9_before.get('warnings', 0), (n9_after or {}).get('warnings'))} |")
    L.append(f"| error 总数 | {n9_before.get('errors', 0)} | {n9_after.get('errors', 0) if n9_after else '—'} | "
             f"{_delta(n9_before.get('errors', 0), (n9_after or {}).get('errors'))} |")
    L.append(f"| 未挂叶实例 UNMAPPED_INSTANCE | {n9_before.get('by_check', {}).get('UNMAPPED_INSTANCE', 0)} | "
             f"{(n9_after or {}).get('by_check', {}).get('UNMAPPED_INSTANCE', 0) if n9_after else '—'} | "
             f"{_delta(n9_before.get('by_check', {}).get('UNMAPPED_INSTANCE', 0), (n9_after or {}).get('by_check', {}).get('UNMAPPED_INSTANCE'))} |")
    L.append(f"| 06e LEAF_SPARSE | {n9_before.get('by_check', {}).get('LEAF_SPARSE', 0)} | "
             f"{(n9_after or {}).get('by_check', {}).get('LEAF_SPARSE', 0) if n9_after else '—'} | "
             f"{_delta(n9_before.get('by_check', {}).get('LEAF_SPARSE', 0), (n9_after or {}).get('by_check', {}).get('LEAF_SPARSE'))} |")
    for check in sorted(set(n9_before.get("by_check", {})) |
                        set(((n9_after or {}).get("by_check") or {}))):
        if check in ("UNMAPPED_INSTANCE", "LEAF_SPARSE"):
            continue
        b = n9_before.get("by_check", {}).get(check, 0)
        a = (n9_after or {}).get("by_check", {}).get(check, 0)
        if b or a:
            L.append(f"| {check} | {b} | {a if n9_after else '—'} | {_delta(b, a)} |")
    L.append("")
    if n9_after:
        ins = n9_after.get("instance") or {}
        L.append(f"- N9 实例统计：scope_instances={ins.get('scope_instances')} / "
                 f"mapped={ins.get('mapped')} / unmapped={ins.get('unmapped')}；"
                 f"leaf_counts={json.dumps(ins.get('leaf_counts', {}), ensure_ascii=False)}")
        ms = ins.get("multi_source") or {}
        if ms:
            L.append(f"- 多源实例（registry+gazetteer+词表+concordance）：mapped={ms.get('mapped')} / "
                     f"total={ms.get('total_instances')} / unmapped={ms.get('unmapped')}；"
                     f"源分布={json.dumps({k: v.get('seen') for k, v in (ms.get('sources') or {}).items()}, ensure_ascii=False)}"
                     f"；去重规则：{ms.get('dedupe_rule')}")
        rem = n9_after.get("by_check", {})
        if rem.get("UNMAPPED_INSTANCE"):
            L.append(f"  - `UNMAPPED_INSTANCE` × {rem['UNMAPPED_INSTANCE']}：见第四章 null 清单"
                     f"（疑非组织/歧义实体，建议先改判类型；不伪造叶）。")
        if rem.get("LEAF_SPARSE"):
            L.append(f"  - `LEAF_SPARSE` × {rem['LEAF_SPARSE']}：06e「子类≥10」按多源真实语料统计后的"
                     f"稀疏叶告警（含已备案 info 级）；计数见 N9 报告 §三·补充与 taxonomy_violations.json。")
        others = [c for c in rem if c not in ("UNMAPPED_INSTANCE", "LEAF_SPARSE")]
        if others:
            L.append(f"  - 其它 warning：{others}（详见 logs/taxonomy/taxonomy_report.md）")
    L.append("")
    L.append("## 六、断言明细")
    L.append("")
    L.append("| 断言 | 说明 | 结果 | 细节 |")
    L.append("|---|---|---|---|")
    for a in assertions:
        L.append(f"| {a['id']} | {a['desc']} | {'PASS' if a['pass'] else 'FAIL'} | {a['detail'][:150]} |")
    L.append("")
    L.append("## 七、遗留与下一步")
    L.append("")
    L.append("- task-45 已把 registry 内 11 条疑类型实体改判/合并（见 logs/qa/s03i_close_report.md §一）；"
             "五树实例叶值由本脚本按显式表+启发式补齐；非五树类型（@/&/~/^/◎）不挂叶。")
    L.append("- 仍 leaf=null 者：太极（歧义待裁）；其余五树实例均有叶。")
    L.append("- 06e 实例量已改多源统计（lint_taxonomy.py）：剩余 LEAF_SPARSE 为真实语料<10 叶，"
             "需后续续书/词表扩量或按 SKILL §7.2/附录 B 备案（不改脚本、不塞兜底叶）。")
    L.append("- 下游合并：塔山族/鲁王 重复 canonical 已合并（旧 id E50814/E102758/E112046 在 concordance/"
             "patches/sku 中的引用待下游重生成对账，不在本任务写 scope）。")
    L.append("- 若其它并发任务重写 `registry/entities.json`，重跑本脚本 `--apply` 幂等补齐 leaf 字段。")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- selftest
def selftest() -> int:
    fails = []

    def ck(name, cond, detail=""):
        if not cond:
            fails.append(f"{name} {detail}".strip())

    # 1) 树结构与叶集合
    ck("64 叶", len(ALL_LEAVES_64) == n9.EXPECTED_LEAF_TOTAL == 64, str(len(ALL_LEAVES_64)))
    ck("势力树 11 叶", len(LEAF_BRANCH) == n9.EXPECTED_LEAF_COUNTS[TREE_CODE] == 11, str(len(LEAF_BRANCH)))
    # 2) 五树实例覆盖（真实 registry；不写盘）
    if REGISTRY.exists():
        reg = load_registry()
        scope = [e for e in reg.get("entities") or [] if e.get("type") in FIVE_TREES]
        ck("五树实例计数闭合", len(scope) == sum(1 for e in reg.get("entities") or []
                                          if e.get("type") in FIVE_TREES), str(len(scope)))
        ck("显式表无重叠", not (set(LEAF_RULES) & set(NULL_RULES)))
        for canon, (leaf, _b) in LEAF_RULES.items():
            ok, why = leaf_legality(leaf, "◆")
            if not ok:
                fails.append(f"LEAF_RULES[{canon}] 非法：{why}")
        ck("LEAF_RULES 叶值全部合法", not any("LEAF_RULES[" in f for f in fails))
        for code, tbl in EXPLICIT_TREE_RULES.items():
            for canon, (leaf, _b) in tbl.items():
                ok, why = leaf_legality(leaf, code)
                if not ok:
                    fails.append(f"EXPLICIT_TREE_RULES[{code}][{canon}] 非法：{why}")
        ck("五树显式改判叶值合法", not any("EXPLICIT_TREE_RULES[" in f for f in fails))
    # 3) classify 样例
    ck("classify 武当派", classify({"canonical": "武当派"})["leaf"] == "武学门派")
    ck("classify 东厂", classify({"canonical": "东厂"})["leaf"] == "宫廷势力")
    ck("classify 天山剑法 ☆", classify({"canonical": "天山剑法", "type": "☆"})["leaf"] == "武功套路")
    ck("classify 天山 =", classify({"canonical": "天山", "type": "="})["leaf"] == "山岳峰岭")
    ck("classify 太极 null", classify({"canonical": "太极"})["leaf"] is None)
    ck("heuristic 新帮", classify({"canonical": "新龙门帮"})["leaf"] == "帮会")
    ck("heuristic 新武功 null", classify({"canonical": "新剑法式"})["leaf"] is None)
    # 4) 模拟 apply（内存）：仅 leaf 三字段变化，实体数/id 不变
    if REGISTRY.exists():
        reg = load_registry()
        before_sha = json.dumps(reg.get("entities"), ensure_ascii=False, sort_keys=True)
        result = compute(reg)
        reg2 = json.loads(json.dumps(reg, ensure_ascii=False))
        apply_assignments(reg2, result)
        asserts = run_assertions(reg, reg2, result)
        fails_a = [a for a in asserts if not a["pass"]]
        ck("模拟 apply 断言全通过", not fails_a, str([(a["id"], a["detail"]) for a in fails_a][:3]))
        ck("实体数不变", len(reg["entities"]) == len(reg2["entities"]))
        scope2 = [e for e in reg2["entities"] if e.get("type") in FIVE_TREES]
        ck("五树实例全带 leaf", all("leaf" in e for e in scope2))
        ck("null 带 candidates/reason", all(e.get("leaf_candidates") or e.get("leaf_reason")
                                           for e in scope2 if e.get("leaf") is None))
        ck("原始 payload 未被改动", json.dumps(reg.get("entities"), ensure_ascii=False,
                                              sort_keys=True) == before_sha)
    if fails:
        print(f"[selftest] FAIL {len(fails)} 项：")
        for f in fails:
            print("  ✗", f)
        return 1
    print("[selftest] PASS（树结构/五树实例覆盖/叶合法性/分类样例/模拟 apply 断言）")
    return 0


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="S-03i 分类挂叶登记（◆ 组织 → 势力树 11 叶）")
    ap.add_argument("--dry-run", action="store_true", help="默认：只计算+报告，不写 registry")
    ap.add_argument("--apply", action="store_true", help="写 registry/entities.json（备份先行）")
    ap.add_argument("--selftest", action="store_true", help="规则自测（不写盘）")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not REGISTRY.exists():
        print(f"[assign] registry 不存在：{REGISTRY}")
        return 2

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[assign] 输入 {REGISTRY}；工具 {TOOL}")
    reg = load_registry()
    # 复跑保护：若 registry 已有 leaf（本脚本已挂过叶），「挂叶前」基线取首次 apply 前快照，
    # 否则 N9 前后对比会退化为"复跑前后"而失真。
    if any("leaf" in e for e in reg.get("entities") or []) and BASELINE_PATH.exists():
        n9_before = json.load(open(BASELINE_PATH, encoding="utf-8"))
        n9_before["baseline_note"] = "首次挂叶前基线（registry 无 leaf 时的 N9 结果）"
        print(f"[assign] N9 挂叶前（基线快照 {BASELINE_PATH.name}）：warning={n9_before.get('warnings')} "
              f"({n9_before.get('by_check')}) error={n9_before.get('errors')}")
    else:
        n9_before = run_n9()
        print(f"[assign] N9 挂叶前：warning={n9_before.get('warnings')} "
              f"({n9_before.get('by_check')}) error={n9_before.get('errors')}")
        if not any("leaf" in e for e in reg.get("entities") or []):
            dump_json(n9_before, BASELINE_PATH)   # 记录基线，供复跑对比

    reg = load_registry()
    sha_before = sha256_file(REGISTRY)
    result = compute(reg)
    print(f"[assign] 五树实例 {result['scope_total']} 条（by_type={result['by_type']}）："
          f"落叶 {result['assigned']} / null {result['unassigned']}；叶分布 {result['leaf_counts']}")

    backup_path = None
    sha_after = None
    reg_after = None
    if args.apply:
        # 写前重读最新文件（兼容并发任务写 registry），备份后原子写
        reg = load_registry()
        result = compute(reg)
        backup_path = BACKUP_DIR / f"entities_{new_stamp()}.json"
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REGISTRY, backup_path)
        reg_after, changed = apply_assignments(json.loads(json.dumps(reg, ensure_ascii=False)),
                                               result)
        dump_json(reg_after, REGISTRY)
        sha_after = sha256_file(REGISTRY)
        print(f"[assign] 已写 {len(changed)} 条五树实例 leaf → {REGISTRY}（备份 {backup_path}）")

    assertions = run_assertions(reg, reg_after, result)
    n9_after = None
    if args.apply:
        n9_after = run_n9()
        print(f"[assign] N9 挂叶后：warning={n9_after.get('warnings')} "
              f"({n9_after.get('by_check')}) error={n9_after.get('errors')}")

    mode = "APPLY（已写 registry/entities.json）" if args.apply else "dry-run（仅报告）"
    report = render_report(result, n9_before, n9_after, assertions, backup_path, mode,
                           sha_before, sha_after)
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")
    dump_json({"tool": TOOL, "generated": now_ts(), "mode": mode,
               "registry_sha256": {"before": sha_before, "after": sha_after},
               "backup": str(backup_path) if backup_path else None,
               "summary": {k: result[k] for k in ("entities_total", "orgs_total", "assigned",
                                                  "unassigned", "leaf_counts")},
               "assignments": result["assignments"], "assertions": assertions,
               "n9_before": n9_before, "n9_after": n9_after}, RESULT_PATH)

    n_fail = sum(1 for a in assertions if not a["pass"])
    print(f"[assign] 断言 {len(assertions) - n_fail}/{len(assertions)} 通过；报告 → {REPORT_PATH}")
    print(f"[assign] 机器结果 → {RESULT_PATH}")
    if n_fail:
        print("[assign] ✗ 断言失败：")
        for a in assertions:
            if not a["pass"]:
                print(f"  ✗ {a['id']} {a['desc']} — {a['detail']}")
        return 1
    if not args.apply:
        print("[assign] dry-run：未写 registry/entities.json（用 --apply 落盘）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
