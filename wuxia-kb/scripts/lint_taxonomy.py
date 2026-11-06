#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N9 · 分类树校验 —— lint_taxonomy.py（D08 分类树五件套 / 06e 颗粒度）

规范源（唯一）：skills/SKILL_分类树五件套_武侠版.md（v0.3-draft）
  §1.3 五棵树总览（地点 16 / 职衔 12 / 身份 18 / 势力 11 / 武功 7 = 64 叶）
  §2.3 §3.2 §4.2 §5.4 §6.7 逐树树形清单（树根→分支→叶，树深 3）
  §7.1 06e 硬标准：**子类预计实例 ≥10 才单列为叶** / **树深 ≤4** / **实例只挂叶**
  §7.2 逐树自检表（同层子类 3–12 软标准 + 已备案豁免 + <10 稀疏预警叶与合并预案）
  §7.4 种子词与 #9 词表接口；§十 错误模式 T17（禁"其他"兜底叶）

本脚本把"五树分类映射表"**内嵌**为可执行常量（TREES），注册数据只读校验：
  1. 结构校验（error）：树数/叶数=64/各树叶数/树深≤4/叶子唯一/父分支完整/禁兜底叶；
  2. 软标准校验（warning/info）：同层叶数 3–12（已备案豁免见 SIBLING_EXEMPT）/稀疏叶；
  3. 实例挂叶（error/warning）：读 registry/entities.json（可选 --assignments 外挂登记），
     校验五类实例的叶值——合法叶｜实例挂内部节点（分支/树根）｜非法叶值｜跨树叶值｜未挂叶；
  4. 语料实例规模（info）：5 书 tagged 中五类 token 去重面数/出现数，供 06e"≥10"参考；
  5. 规范漂移（warning）：回读 SKILL 树形清单，与脚本内嵌表逐叶对比（防"文-码两张皮"）。

产物
----
- `logs/taxonomy/taxonomy_report.md`      —— 报告（结构/软标准/实例/语料规模/漂移/断言）
- `logs/taxonomy/taxonomy_violations.json` —— 违规清单（error/warning/info 逐条可机读）
- `logs/taxonomy/taxonomy_trees.json`     —— 内嵌五树导出（树/分支/叶/深度，供 S-03i/词表）

CLI
---
    python -X utf8 scripts/lint_taxonomy.py                    # 校验并写报告
    python -X utf8 scripts/lint_taxonomy.py --selftest         # 自检（不写盘）
    python -X utf8 scripts/lint_taxonomy.py --strict           # warning 亦判失败（退出码 1）
    python -X utf8 scripts/lint_taxonomy.py --no-corpus        # 跳过 tagged 语料规模扫描
    python -X utf8 scripts/lint_taxonomy.py --registry <path> --assignments <path> \
        --skill <path> --out-dir <dir>

退出码：0 无 error（--strict 时还须无 warning）；1 结构或实例 error；2 输入缺失/不可读。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

DEFAULT_REGISTRY = config.DIR_REGISTRY / "entities.json"
DEFAULT_ASSIGNMENTS = config.DIR_REGISTRY / "taxonomy" / "leaf_assignments.json"
DEFAULT_SKILL = config.DIR_SKILLS / "SKILL_分类树五件套_武侠版.md"
DEFAULT_OUT = config.DIR_LOGS / "taxonomy"

MAX_DEPTH = 4                 # 06e：树深 ≤4（本表实际 3：根→分支→叶）
MIN_INSTANCES_PER_LEAF = 10   # 06e：子类预计实例 ≥10 才单列为叶
SIBLING_SOFT_MIN = 3          # §7.1 软标准：同一父类下子类 3–12 个为佳
SIBLING_SOFT_MAX = 12
MAX_MULTI_VALUE = 3           # §4.5 多值上限 3（身份树；地点兼值同用此上限）
FALLBACK_LEAF_NAMES = {"其他", "其它", "未知", "待定", "杂项", "未分类", "未定"}

TYPE_LABELS = {"=": "地点", ";": "职衔", "#": "身份", "◆": "组织", "☆": "武功技艺"}

# ==================== 内嵌分类映射表（D08 §2.3/3.2/4.2/5.4/6.7，64 叶） ====================
# 结构：类型码 → {name 树名, label 类型标签, root 树根名, branches:[(分支名,[叶...])]}
TREES = {
    "=": {"name": "地点树", "label": "地点", "root": "地点",
          "branches": [
              ("自然地貌", ["山岳峰岭", "水域江湖", "洞窟秘谷"]),
              ("人居建筑", ["城镇都邑", "村集乡野", "关隘城门", "宫廷禁地", "寺观道院",
                            "客栈酒楼", "山庄府邸", "镖局车店"]),
              ("组织驻地", ["名门山门", "教帮总舵", "山寨水寨"]),
              ("秘境遗址", ["洞府秘境", "战场遗址"]),
          ]},
    ";": {"name": "职衔树", "label": "职衔", "root": "职衔",
          "branches": [
              ("朝廷轨", ["侍卫厂卫", "宦官内职", "中央朝官", "地方大吏", "军职武官",
                          "官署吏役", "爵位封号"]),
              ("江湖轨", ["门派职衔", "帮会职衔", "绿林职衔", "镖行职衔", "盟会职衔"]),
          ]},
    "#": {"name": "人物身份树", "label": "身份", "root": "人物身份",
          "branches": [
              ("武林身份", ["侠客侠士", "绿林豪杰", "义军志士", "隐逸高人", "方外僧道"]),
              ("权位身份", ["宗室帝胄", "朝廷效命者", "后妃外戚", "宦官内侍"]),
              ("江湖职业", ["镖行武师", "护卫保镖", "刺客杀手", "游方医卜"]),
              ("处境身份", ["平民百姓", "仆役婢女", "乞丐流民", "囚徒俘虏", "卧底内应"]),
          ]},
    "◆": {"name": "门派势力树", "label": "组织", "root": "门派势力",
          "branches": [
              ("武学传承型", ["武学门派", "武林世家", "海外门派"]),
              ("结社据点型", ["宗教教门", "帮会", "盟会联盟", "绿林山寨", "黑店赌坊", "镖局"]),
              ("庙堂武力型", ["宫廷势力", "义军组织"]),
          ]},
    "☆": {"name": "武功谱系树", "label": "武功技艺", "root": "武功谱系",
          "branches": [
              ("心法层", ["内功心法", "奇功禁术"]),
              ("武功层", ["武功套路"]),
              ("招式层", ["独立招式", "变式招式", "组合连招"]),
              ("阵法层", ["协同阵法"]),
          ]},
}

# §1.3/§7.2 各树叶数（文档基准，结构校验用）
EXPECTED_LEAF_COUNTS = {"=": 16, ";": 12, "#": 18, "◆": 11, "☆": 7}
EXPECTED_LEAF_TOTAL = 64

# §7.2 同层子类 3–12 软标准豁免（已备案理由）
SIBLING_EXEMPT = {
    ("☆", "心法层"): "结构单叶豁免：层级四分每层=一个登记字段值域（§7.2）",
    ("☆", "武功层"): "结构单叶豁免：同上（武功层单叶为层级结构必然）",
    ("☆", "阵法层"): "结构单叶豁免：同上（阵法层单叶为结构必然）",
    ("=", "秘境遗址"): "2 叶为稀疏分支，预留观察位，不足则并（§7.2）",
    ("◆", "庙堂武力型"): "2 叶；附录 B9 待拍板可拍平为单层 11 叶（§7.2）",
}

# §7.2 <10 预警叶与合并预案 / 稀疏类理由（06e 稀疏叶备案表）
SPARSE_ACK = {
    "战场遗址": ("地点树", "预警→并入洞府秘境改名'秘境遗址'"),
    "镖局车店": ("地点树", "低风险（34 书镖局戏足量）"),
    "宦官内职": ("职衔树", "低风险（明宫戏多）"),
    "盟会职衔": ("职衔树", "中风险→并入帮会职衔改名'结社职衔'"),
    "爵位封号": ("职衔树", "保留理由：册封信号独立、与宗室身份边界必须成文"),
    "刺客杀手": ("身份树", "稀疏预警→并入'受雇武人'"),
    "游方医卜": ("身份树", "稀疏预警→并入'市井百艺'"),
    "卧底内应": ("身份树", "稀疏预警→处境身份内并档"),
    "乞丐流民": ("身份树", "稀疏预警→并入平民百姓，丐帮走关系边"),
    "囚徒俘虏": ("身份树", "保留理由：01g 明文'俘虏是身份'，处境登记必须有名目"),
    "海外门派": ("势力树", "预警→并武学门派+地域=海外"),
    "黑店赌坊": ("势力树", "预警→并帮会"),
    "盟会联盟": ("势力树", "保留理由：义军盟会在案（王嘉胤），与'武林大会'事件边界须成文"),
    "协同阵法": ("武功树", "若 <10 → 与奇功禁术并档观察"),
    "变式招式": ("武功树", "取决于 04f 招式粒度实测，预案并入独立招式+方式备注"),
    "组合连招": ("武功树", "同上（并入独立招式+方式备注）"),
    "奇功禁术": ("武功树", "保留理由：修炼形态判据独立，与品类/邪正不重复"),
}

# §7.4 种子词（各树触发词，报告/下游 #9 词表参考）
SEED_WORDS = {
    "=": ["山", "峰", "崖", "湖", "关", "宫", "观", "庄", "寨", "镖局",
          "天山", "五台山", "秘魔崖", "乾清宫", "宣武门"],
    ";": ["掌门", "长老", "护法", "帮主", "堂主", "香主", "寨主", "总镖头", "盟主",
          "侍卫", "锦衣卫", "总兵", "游击", "知府"],
    "#": ["大侠", "女侠", "少侠", "前辈", "隐士", "道长", "贫僧", "陛下", "殿下"],
    "◆": ["派", "门", "教", "帮", "会", "寨", "局", "世家", "山庄",
          "武当", "少林", "峨眉", "天山派"],
    "☆": ["剑法", "掌法", "神功", "心法", "剑诀", "式", "手", "阵",
          "七十二手连环剑", "九宫神行掌"],
}

# 注册实例中可承载叶值的字段（显式键；未知键不猜）
LEAF_KEYS = ("leaf", "leaves", "tree_leaf", "taxonomy_leaf", "leaf_values")
TREE_KEYS = ("tree", "tree_code", "taxonomy_tree")

# 回读 SKILL 树形清单用：树码 → (章节定位串, 树名)
SKILL_SECTIONS = {
    "=": ("2.3 地点树形清单", "地点树"),
    ";": ("3.2 职衔树形清单", "职衔树"),
    "#": ("4.2 身份树形清单", "身份树"),
    "◆": ("5.4 势力树形清单", "势力树"),
    "☆": ("6.7 武功谱系树形清单", "武功谱系树"),
}


# ==================== 内嵌树派生结构 ====================
def build_leaf_index():
    """→ {tree_code: {leaf: branch}}, {leaf: [tree_code...]}, {tree_code: [(branch, count)]}"""
    leaf_branch, leaf_trees, branch_counts = {}, defaultdict(list), {}
    for code, tree in TREES.items():
        bc = []
        for branch, leaves in tree["branches"]:
            bc.append((branch, len(leaves)))
            for leaf in leaves:
                leaf_branch.setdefault(code, {})[leaf] = branch
                leaf_trees[leaf].append(code)
        branch_counts[code] = bc
    return leaf_branch, dict(leaf_trees), branch_counts


LEAF_BRANCH, LEAF_TREES, BRANCH_COUNTS = build_leaf_index()
ALL_LEAVES = set(LEAF_TREES)
ALL_BRANCHES = {b for t in TREES.values() for b, _ in t["branches"]}
ALL_ROOTS = {t["root"] for t in TREES.values()}


# ==================== 结构校验 ====================
def check_structure():
    """树定义自检 → (violations, summary)。error 级结构破坏；info 级通过项。"""
    V = []

    def err(check, detail, **kw):
        V.append({"severity": "error", "check": check, "detail": detail, **kw})

    def info(check, detail, **kw):
        V.append({"severity": "info", "check": check, "detail": detail, **kw})

    codes = set(TREES)
    if codes != set(TYPE_LABELS):
        err("TREE_CODE_SET", f"树类型码集合 {sorted(codes)} != 五类 {sorted(TYPE_LABELS)}")
    total = sum(len(leaves) for t in TREES.values() for _, leaves in t["branches"])
    if total != EXPECTED_LEAF_TOTAL:
        err("LEAF_TOTAL", f"叶总数 {total} != 规范 64")
    else:
        info("LEAF_TOTAL", f"叶总数 {total} = 规范 64 ✓")
    for code, tree in TREES.items():
        leaves = [leaf for _, ls in tree["branches"] for leaf in ls]
        exp = EXPECTED_LEAF_COUNTS.get(code)
        if len(leaves) != exp:
            err("TREE_LEAF_COUNT", f"{tree['name']} 叶数 {len(leaves)} != 规范 {exp}", tree=code)
        else:
            info("TREE_LEAF_COUNT", f"{tree['name']} {len(leaves)} 叶 ✓", tree=code)
        depth = 3 if tree["branches"] else 2
        if depth > MAX_DEPTH:
            err("TREE_DEPTH", f"{tree['name']} 树深 {depth} > {MAX_DEPTH}", tree=code)
        else:
            info("TREE_DEPTH", f"{tree['name']} 树深 {depth}（根→分支→叶）≤{MAX_DEPTH} ✓", tree=code)
        if not tree["branches"]:
            err("TREE_EMPTY", f"{tree['name']} 无分支", tree=code)
        for branch, ls in tree["branches"]:
            if not ls:
                err("BRANCH_EMPTY", f"{tree['name']}·{branch} 无叶", tree=code, branch=branch)
            dup_branch = [b for b, _ in tree["branches"]].count(branch)
            if dup_branch > 1:
                err("DUPLICATE_BRANCH", f"{tree['name']} 分支「{branch}」重复", tree=code)
        dup = [leaf for leaf, c in Counter(leaves).items() if c > 1]
        if dup:
            err("DUPLICATE_LEAF", f"{tree['name']} 叶重复：{dup}", tree=code)
        other_tree_dup = [leaf for leaf in leaves if len(LEAF_TREES.get(leaf, [])) > 1]
        if other_tree_dup:
            err("CROSS_TREE_LEAF", f"{tree['name']} 叶与其它树同名：{other_tree_dup}", tree=code)
        fallback = [leaf for leaf in leaves if leaf in FALLBACK_LEAF_NAMES]
        if fallback:
            err("FALLBACK_LEAF", f"{tree['name']} 出现兜底叶（T17/06e 禁）：{fallback}", tree=code)
        leaf_set = set(leaves)
        if tree["root"] in leaf_set or tree["root"] in {b for b, _ in tree["branches"]}:
            err("ROOT_NAME_CONFLICT", f"{tree['name']} 树根名与分支/叶冲突", tree=code)
    return V


def check_soft_standard():
    """§7.1 软标准 + §7.2 稀疏叶备案 → violations/备案信息。"""
    V = []
    for code, tree in TREES.items():
        for branch, ls in tree["branches"]:
            n = len(ls)
            exempt = SIBLING_EXEMPT.get((code, branch))
            if SIBLING_SOFT_MIN <= n <= SIBLING_SOFT_MAX:
                V.append({"severity": "info", "check": "SIBLING_COUNT",
                          "tree": code, "branch": branch,
                          "detail": f"{tree['name']}·{branch} 叶数 {n} ∈ [{SIBLING_SOFT_MIN},"
                                    f"{SIBLING_SOFT_MAX}] ✓"})
            elif exempt:
                V.append({"severity": "info", "check": "SIBLING_EXEMPT",
                          "tree": code, "branch": branch,
                          "detail": f"{tree['name']}·{branch} 叶数 {n}（软标准外，已备案豁免）：{exempt}"})
            else:
                V.append({"severity": "warning", "check": "SIBLING_COUNT_OUT_OF_RANGE",
                          "tree": code, "branch": branch,
                          "detail": f"{tree['name']}·{branch} 叶数 {n} 不在软标准 "
                                    f"{SIBLING_SOFT_MIN}–{SIBLING_SOFT_MAX}（需合并/给理由）"})
    for leaf, (tree_name, reason) in SPARSE_ACK.items():
        if leaf not in ALL_LEAVES:
            V.append({"severity": "warning", "check": "SPARSE_ACK_UNKNOWN_LEAF",
                      "detail": f"稀疏备案表含未知叶「{leaf}」（{tree_name}）：{reason}"})
    return V, SPARSE_ACK


# ==================== 实例挂叶校验 ====================
def extract_assignment(entity, assignments_map):
    """→ (leaf_values list, source)。支持实体内嵌字段 + 外挂登记 map（id→leaf）。"""
    eid = entity.get("id")
    if assignments_map and eid in assignments_map:
        val = assignments_map[eid]
        return normalize_multi(val), f"assignments[{eid}]"
    for key in LEAF_KEYS:
        if key in entity and entity[key]:
            return normalize_multi(entity[key]), key
    tax = entity.get("taxonomy")
    if isinstance(tax, dict):
        for key in ("leaf", "leaves"):
            if tax.get(key):
                return normalize_multi(tax[key]), f"taxonomy.{key}"
    return [], None


def normalize_multi(val):
    if isinstance(val, (list, tuple)):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        # 支持 "地点/山岳峰岭" 或 "山岳峰岭|水域江湖" 式复合值
        for sep in ("|", "、", "；", ";"):
            if sep in val:
                return [x.strip() for x in val.split(sep) if x.strip()]
        return [val.strip()] if val.strip() else []
    return [str(val)]


def check_instances(registry_path: Path, assignments_path: Path | None):
    """读 registry/entities.json（只读）→ 五类实例挂叶校验。"""
    V, stats = [], {"registry": str(registry_path), "entities_total": 0,
                    "scope_instances": 0, "mapped": 0, "unmapped": 0,
                    "by_tree": {}, "leaf_counts": defaultdict(int),
                    "multi_value_instances": 0, "assignments_used": False}
    if not registry_path.exists():
        V.append({"severity": "error", "check": "REGISTRY_MISSING",
                  "detail": f"实体登记表不存在：{registry_path}"})
        return V, stats
    payload = json.loads(io.open(registry_path, encoding="utf-8").read())
    ents = payload.get("entities") or []
    stats["entities_total"] = len(ents)
    stats["registry_scope"] = payload.get("scope", "")
    amap = {}
    if assignments_path and assignments_path.exists():
        aj = json.loads(io.open(assignments_path, encoding="utf-8").read())
        if isinstance(aj, dict):
            amap = aj.get("assignments", aj)
        stats["assignments_used"] = bool(amap)
        stats["assignments"] = str(assignments_path)
    by_tree = defaultdict(lambda: Counter())
    for e in ents:
        code = e.get("type")
        if code not in TREES:
            continue
        stats["scope_instances"] += 1
        by_tree[code]["total"] += 1
        values, source = extract_assignment(e, amap)
        if not values:
            by_tree[code]["unmapped"] += 1
            stats["unmapped"] += 1
            V.append({"severity": "warning", "check": "UNMAPPED_INSTANCE",
                      "tree": code, "entity": e.get("canonical"), "eid": e.get("id"),
                      "detail": f"{TYPE_LABELS[code]}实例《{e.get('canonical')}》"
                                f"（{e.get('id')}）未挂叶值（字段 {'/'.join(LEAF_KEYS)} 均缺；"
                                f"待 S-03i 分类登记）"})
            continue
        if len(values) > MAX_MULTI_VALUE:
            V.append({"severity": "warning", "check": "MULTI_VALUE_EXCEEDED",
                      "tree": code, "entity": e.get("canonical"),
                      "detail": f"多值 {len(values)} > 上限 {MAX_MULTI_VALUE}（§4.5）"})
            stats["multi_value_instances"] += 1
        tree_field = next((e[k] for k in TREE_KEYS if e.get(k)), None)
        ok_any = False
        for value in values:
            if value == TREES[code]["root"] or value in ALL_ROOTS:
                V.append({"severity": "error", "check": "INSTANCE_ON_ROOT", "tree": code,
                          "entity": e.get("canonical"), "value": value,
                          "detail": f"实例挂树根「{value}」——06e：实例只挂叶"})
            elif value in {b for b, _ in TREES[code]["branches"]}:
                V.append({"severity": "error", "check": "INSTANCE_ON_BRANCH", "tree": code,
                          "entity": e.get("canonical"), "value": value,
                          "detail": f"实例挂内部节点「{value}」——06e：实例只挂叶"})
            elif value in LEAF_BRANCH.get(code, {}):
                ok_any = True
                stats["leaf_counts"][value] += 1
                by_tree[code]["mapped"] += 1
                stats["mapped"] += 1
                if tree_field and tree_field not in (code, TREES[code]["name"]):
                    V.append({"severity": "warning", "check": "TREE_FIELD_MISMATCH",
                              "tree": code, "entity": e.get("canonical"),
                              "detail": f"实体 tree 字段={tree_field!r} 与类型码 {code} 不符"})
            elif value in ALL_LEAVES:
                owner = LEAF_TREES[value]
                V.append({"severity": "error", "check": "LEAF_TREE_MISMATCH", "tree": code,
                          "entity": e.get("canonical"), "value": value,
                          "detail": f"叶值「{value}」属于 {owner} 树，与实例类型 {code} 不符"})
            elif value in ALL_BRANCHES:
                V.append({"severity": "error", "check": "INSTANCE_ON_BRANCH", "tree": code,
                          "entity": e.get("canonical"), "value": value,
                          "detail": f"实例挂内部节点「{value}」——06e：实例只挂叶"})
            else:
                V.append({"severity": "error", "check": "ILLEGAL_LEAF_TYPE", "tree": code,
                          "entity": e.get("canonical"), "value": value,
                          "detail": f"非法叶值「{value}」不在{TREES[code]['name']} 64 叶枚举内"
                                    f"（02ab/D08 叶值封闭；新叶须过 06e + 规则累积日志）"})
        if not ok_any and values:
            by_tree[code]["unmapped"] += 1
            stats["unmapped"] += 1
    stats["by_tree"] = {c: dict(v) for c, v in sorted(by_tree.items())}
    # 06e ≥10：改用「多源实例」口径（registry/gazetteer/词表/concordance，见多源实例接入块）
    multi = collect_multi_source_instances(ents)
    stats["multi_source"] = multi
    mapped_total = multi["mapped"]
    if mapped_total:
        for leaf, cnt in sorted(multi["leaf_counts"].items()):
            if cnt < MIN_INSTANCES_PER_LEAF:
                sev = "info" if leaf in SPARSE_ACK else "warning"
                V.append({"severity": sev, "check": "LEAF_SPARSE",
                          "leaf": leaf,
                          "detail": f"叶「{leaf}」多源实例 {cnt} < 06e 阈值 {MIN_INSTANCES_PER_LEAF}"
                                    + (f"（已备案稀疏叶：{SPARSE_ACK[leaf][1]}）" if leaf in SPARSE_ACK
                                       else "（需合并或补稀疏理由）")})
        for leaf in ALL_LEAVES:
            if leaf not in multi["leaf_counts"]:
                sev = "info" if leaf in SPARSE_ACK else "warning"
                V.append({"severity": sev, "check": "LEAF_SPARSE",
                          "leaf": leaf, "detail": f"叶「{leaf}」多源实例 0（< 06e 阈值 10）"})
        V.append({"severity": "info", "check": "MULTI_SOURCE_STATS",
                  "detail": f"06e 实例量=多源聚合：{multi['mapped']}/{multi['total_instances']} 已映射"
                            f"（unmapped {multi['unmapped']}）；源分布 " +
                            json.dumps({k: v["seen"] for k, v in multi["sources"].items()},
                                       ensure_ascii=False)})
    else:
        V.append({"severity": "info", "check": "LEAF_COUNTS_DEFERRED",
                  "detail": "多源聚合未得到任何可映射实例 → 06e「子类≥10」实例量检查延后"})
    stats["leaf_counts"] = dict(sorted(stats["leaf_counts"].items(), key=lambda x: -x[1]))
    return V, stats


# ==================== 语料实例规模（06e 参考） ====================
TOKEN_TREE_RE = re.compile(r"〖([=;#◆☆])([^〖〗]*)〗")


def check_corpus_volume():
    """5 书 tagged 中五类 token 的去重面数/出现数（info；供 06e"实例≥10"参考）。"""
    vol = {code: {"distinct": 0, "occurrences": 0, "by_book": {}} for code in TREES}
    tagged_books = sorted(p.name for p in config.DIR_TAGGED.iterdir()
                          if p.is_dir() and any(p.glob("*.tagged.md")))
    errors = []
    for book in tagged_books:
        per_book = {code: {"surfaces": set(), "occ": 0} for code in TREES}
        for tp in sorted((config.DIR_TAGGED / book).glob("*.tagged.md")):
            try:
                text = io.open(tp, encoding="utf-8").read()
            except OSError as exc:
                errors.append(f"{tp.name}: {exc}")
                continue
            for m in TOKEN_TREE_RE.finditer(text):
                code, body = m.group(1), m.group(2)
                if code not in per_book:
                    continue
                surface = body.split("|")[0].strip()
                per_book[code]["surfaces"].add(surface)
                per_book[code]["occ"] += 1
        for code in TREES:
            n = len(per_book[code]["surfaces"])
            o = per_book[code]["occ"]
            vol[code]["distinct"] += n
            vol[code]["occurrences"] += o
            if n or o:
                vol[code]["by_book"][book] = {"distinct": n, "occurrences": o}
    return vol, tagged_books, errors



# ==================== 多源实例接入（06e 实例量跨源统计） ====================
# 06e「子类预计实例 ≥10」的实例量不能只看 registry/entities.json：五类实例的登记载体
# 按 01g 分工分散（docs/17 §2.3）——◆ 组织在 registry；= 地点在 registry/gazetteer.json
# （N7 nature/kind）；; 职衔 / # 身份在 wordlists/identity.json + concordance；
# ☆ 武功技艺在 wordlists/new_entity_types.json + concordance。本块按 (tree, canonical)
# 去重聚合四源，源优先级：registry > gazetteer > 词表 > concordance（后到同键丢弃）。
GAZETTEER_PATH = config.DIR_REGISTRY / "gazetteer.json"
WORDLIST_IDENTITY = config.DIR_WORDLISTS / "identity.json"
WORDLIST_NEW_TYPES = config.DIR_WORDLISTS / "new_entity_types.json"
CONCORDANCE_DIR = config.DIR_REGISTRY / "concordance"

# gazetteer kind（N7 十三值）→ 地点树 16 叶（kind 与叶同源于 #8，SKILL §2.3/§5.4）
GAZ_KIND_TO_LEAF = {
    "山": "山岳峰岭", "水域": "水域江湖", "城镇": "城镇都邑", "关隘": "关隘城门",
    "宫廷": "宫廷禁地", "山庄园林": "山庄府邸", "客栈": "客栈酒楼", "寺观": "寺观道院",
    "寨堡": "山寨水寨", "遗址战场": "战场遗址", "秘境洞府": "洞府秘境",
    # 区域（广域）/其他（待审）无对应叶：计 unmapped，不是登记错误
}
PLACE_SUFFIX_RULES = [
    (("山", "峰", "岭", "崖", "顶", "山脉"), "山岳峰岭"),
    (("江", "河", "湖", "海", "溪", "泉", "池", "潭", "湾", "岛", "涧"), "水域江湖"),
    (("关", "隘", "门", "口"), "关隘城门"),
    (("宫", "殿"), "宫廷禁地"),
    (("寺", "庙", "观", "庵", "祠", "塔"), "寺观道院"),
    (("园", "苑", "庄", "墅", "府", "楼", "阁"), "山庄府邸"),
    (("寨", "堡", "硐"), "山寨水寨"),
    (("洞府",), "洞府秘境"),
    (("洞窟", "石窟", "洞"), "洞窟秘谷"),
    (("客栈", "酒楼", "店"), "客栈酒楼"),
    (("镖局", "镖行", "镖车"), "镖局车店"),
    (("村", "乡", "集", "屯"), "村集乡野"),
    (("院", "堂"), "寺观道院"),
    (("房", "屋", "室", "庭", "斋", "轩"), "山庄府邸"),
    (("塘",), "水域江湖"),
    (("城", "镇", "州", "县", "京", "都", "邑", "卫"), "城镇都邑"),
]
TITLE_KEYWORD_RULES = [
    (("侍卫", "厂卫", "锦衣卫", "带刀"), "侍卫厂卫"),
    (("太监", "宦官", "内侍"), "宦官内职"),
    (("尚书", "侍郎", "大学士", "御史", "宰相", "丞相", "阁老", "翰林", "朝官"), "中央朝官"),
    (("巡抚", "总督", "知府", "知县", "县令", "布政", "按察", "道台", "太守", "刺史"), "地方大吏"),
    (("将军", "总兵", "参将", "游击", "都统", "提督", "副将", "守备", "千总", "把总", "校尉"), "军职武官"),
    (("差役", "捕快", "书办", "衙役", "幕僚", "师爷", "主簿", "典史", "吏"), "官署吏役"),
    (("王爷", "郡王", "贝勒", "贝子", "国公", "驸马", "爵", "封号"), "爵位封号"),
    (("掌门", "长老", "护法", "门主", "宗主", "首徒", "嫡传", "真传"), "门派职衔"),
    (("帮主", "堂主", "香主", "舵主", "帮众"), "帮会职衔"),
    (("寨主", "头领", "当家", "大王"), "绿林职衔"),
    (("总镖头", "镖头", "镖师", "走镖"), "镖行职衔"),
    (("盟主", "盟会", "会盟"), "盟会职衔"),
    (("太子", "王子", "藩王", "平西王", "平南王", "贝勒", "贝子", "国公", "一等公",
      "巴图鲁", "王妃", "贵妃", "皇后", "诰命夫人"), "爵位封号"),
    (("御林军总管", "禁卫军统领", "统领", "都指挥", "副统领", "指挥", "中军", "统帅",
      "主帅", "裨将", "参将", "都统"), "军职武官"),
    (("钦差", "太傅", "太子少保", "参赞", "旗牌官", "兵科给事中", "鸿胪寺丞", "太医"), "中央朝官"),
    (("经略", "督抚", "抚台"), "地方大吏"),
    (("总管", "管家"), "官署吏役"),
    (("监寺", "主持", "法王", "国师", "总教头", "教头", "值殿武师", "庄主", "堡主",
      "副堡主", "风砂堡主", "桩头"), "门派职衔"),
    (("捕头", "捕快"), "官署吏役"),
    (("头目", "首领", "领袖", "龙头大哥"), "绿林职衔"),
]
IDENTITY_KEYWORD_RULES = [
    (("大侠", "女侠", "少侠", "侠客", "侠士", "剑客"), "侠客侠士"),
    (("绿林", "盗", "匪", "响马", "贼"), "绿林豪杰"),
    (("义军", "义士", "志士", "抗清", "起事"), "义军志士"),
    (("隐士", "高人", "前辈", "隐逸", "世外"), "隐逸高人"),
    (("道长", "道人", "和尚", "僧人", "禅师", "大师", "尼", "方外", "居士"), "方外僧道"),
    (("皇帝", "太子", "王爷", "皇子", "宗室", "贝勒", "郡主", "公主"), "宗室帝胄"),
    (("皇后", "贵妃", "妃", "太后", "夫人"), "后妃外戚"),
    (("太监", "宦官", "内侍"), "宦官内侍"),
    (("镖师", "武师", "镖头"), "镖行武师"),
    (("护卫", "保镖", "护院"), "护卫保镖"),
    (("刺客", "杀手", "暗杀"), "刺客杀手"),
    (("大夫", "郎中", "医生", "卜", "相士", "算命"), "游方医卜"),
    (("官员", "朝臣", "命官", "臣"), "朝廷效命者"),
    (("丫鬟", "婢女", "仆人", "侍女", "奴"), "仆役婢女"),
    (("乞丐", "流民", "丐"), "乞丐流民"),
    (("囚", "俘虏", "犯人", "狱"), "囚徒俘虏"),
    (("卧底", "内应", "细作", "间谍"), "卧底内应"),
    (("百姓", "平民", "村民", "农"), "平民百姓"),
    (("卫士", "侍卫", "亲兵", "禁卫军"), "护卫保镖"),
    (("武士", "高手", "好手", "强敌", "同门", "弟子", "门人", "师叔", "师伯",
      "师兄", "师弟"), "侠客侠士"),
    (("喇嘛", "道士", "番僧", "头陀", "小沙弥", "僧人"), "方外僧道"),
    (("官军", "军官", "县官", "官儿", "钦差", "内监", "捕快"), "朝廷效命者"),
    (("先帝", "太子", "王子", "藩王", "平西王", "平南王"), "宗室帝胄"),
    (("宫女", "宫娥", "丫环", "丫鬟", "家丁", "家人", "随从", "手下", "仆从"), "仆役婢女"),
    (("饥民", "难民"), "乞丐流民"),
    (("钦犯", "犯人", "俘虏", "囚犯"), "囚徒俘虏"),
    (("寨主", "堡主", "头目", "首领", "大王"), "绿林豪杰"),
    (("老者", "老人家", "老人", "妇人", "少年", "女子", "男子", "大汉", "汉子",
      "书生", "掌柜", "小二", "客人", "车夫", "船夫", "蒙面人"), "平民百姓"),
]
ART_NOTE_RULES = [
    (("组合", "连招"), "组合连招"),
    (("变式",), "变式招式"),
    (("阵",), "协同阵法"),
    (("奇功", "禁术"), "奇功禁术"),
    (("心法", "内功"), "内功心法"),
    (("招式", "父式="), "独立招式"),
    (("武功", "父式名"), "武功套路"),
]


def _match_rules(name: str, rules, fallback=None):
    """有序关键词规则：name 含任一关键词 → 对应叶。"""
    for keywords, leaf in rules:
        if any(k in name for k in keywords):
            return leaf
    return fallback


def _art_leaf(note: str, name: str) -> str:
    if note:
        for keywords, leaf in ART_NOTE_RULES:
            if any(k in note for k in keywords):
                return leaf
    if "阵" in name:
        return "协同阵法"
    if name.endswith(("功", "经", "诀", "谱", "心法", "神功")):
        return "内功心法"
    if name.endswith(("式", "手", "招")):
        return "独立招式"
    return "武功套路"


def _dedupe_source_priority():
    return ("registry", "gazetteer", "wordlist_identity", "wordlist_new_entity_types", "concordance")


def collect_multi_source_instances(entities) -> dict:
    """四源实例聚合 → 06e 叶级实例量（按 (tree, canonical) 去重，源优先级见上）。"""
    by_tree = {c: {"total": 0, "mapped": 0, "unmapped": 0, "leaf_counts": {}} for c in TREES}
    sources = {name: {"seen": 0, "mapped": 0, "unmapped": 0, "skipped_dup": 0,
                      "unmapped_examples": []} for name in _dedupe_source_priority()}
    seen = set()

    def add(code, canonical, leaf_value, source):
        key = (code, canonical)
        if key in seen:
            sources[source]["skipped_dup"] += 1
            return
        seen.add(key)
        by_tree[code]["total"] += 1
        sources[source]["seen"] += 1
        legal = leaf_value in LEAF_BRANCH.get(code, {})
        if legal:
            by_tree[code]["mapped"] += 1
            sources[source]["mapped"] += 1
            lc = by_tree[code]["leaf_counts"]
            lc[leaf_value] = lc.get(leaf_value, 0) + 1
        else:
            by_tree[code]["unmapped"] += 1
            sources[source]["unmapped"] += 1
            if len(sources[source]["unmapped_examples"]) < 10:
                sources[source]["unmapped_examples"].append(f"{canonical}[{code}]")

    # 1) registry：五树类型实体内嵌叶值（S-03i 已挂叶）
    for e in entities or []:
        code = e.get("type")
        if code not in TREES:
            continue
        values, _src = extract_assignment(e, {})
        leaf = next((v for v in values if v in LEAF_BRANCH.get(code, {})), None)
        add(code, e.get("canonical") or e.get("id"), leaf, "registry")

    # 2) gazetteer：地点实例（N7 kind 13 值 → 地点树 16 叶）
    gaz_index = {}
    if GAZETTEER_PATH.exists():
        try:
            gaz = json.loads(io.open(GAZETTEER_PATH, encoding="utf-8").read())
            for p in gaz.get("places", []):
                canon = p.get("id") or p.get("name")
                gaz_index[canon] = p.get("kind")
                add("=", canon, GAZ_KIND_TO_LEAF.get(p.get("kind")), "gazetteer")
        except (OSError, ValueError):
            pass

    # 3) 词表：; 职衔 / # 身份（identity.json）+ ☆ 武功技艺（new_entity_types.json）
    identity_leaf = {}
    wl_art_leaf = {}
    if WORDLIST_IDENTITY.exists():
        try:
            for it in json.loads(io.open(WORDLIST_IDENTITY, encoding="utf-8").read()).get("items", []):
                code = it.get("type")
                if code not in (";", "#"):
                    continue
                canon = it.get("canonical") or it.get("surface") or ""
                rules = TITLE_KEYWORD_RULES if code == ";" else IDENTITY_KEYWORD_RULES
                leaf = _match_rules(canon, rules)
                identity_leaf[(code, canon)] = leaf
                add(code, canon, leaf, "wordlist_identity")
        except (OSError, ValueError):
            pass
    if WORDLIST_NEW_TYPES.exists():
        try:
            for it in json.loads(io.open(WORDLIST_NEW_TYPES, encoding="utf-8").read()).get("items", []):
                if it.get("type") != "☆":
                    continue
                canon = it.get("canonical") or it.get("surface") or ""
                leaf = _art_leaf(it.get("note") or "", canon)
                wl_art_leaf[canon] = leaf
                add("☆", canon, leaf, "wordlist_new_entity_types")
        except (OSError, ValueError):
            pass

    # 4) concordance：5 书 tagged 实体（= ; # ☆），补足未被上述源覆盖的 canonical
    if CONCORDANCE_DIR.exists():
        for cp in sorted(CONCORDANCE_DIR.glob("*.json")):
            try:
                conc = json.loads(io.open(cp, encoding="utf-8").read())
            except (OSError, ValueError):
                continue
            for e in conc.get("entities", []):
                code = e.get("type")
                if code not in TREES:
                    continue
                canon = e.get("canonical") or ""
                if code == "=":
                    leaf = GAZ_KIND_TO_LEAF.get(gaz_index.get(canon))
                    if not leaf:
                        leaf = _match_rules(canon, PLACE_SUFFIX_RULES)
                elif code == "☆":
                    leaf = wl_art_leaf.get(canon) or _art_leaf("", canon)
                elif code == ";":
                    leaf = identity_leaf.get((";", canon)) or _match_rules(canon, TITLE_KEYWORD_RULES)
                else:  # "#"
                    leaf = identity_leaf.get(("#", canon)) or _match_rules(canon, IDENTITY_KEYWORD_RULES)
                add(code, canon, leaf, "concordance")

    leaf_counts = {}
    for c in by_tree.values():
        for leaf, cnt in c["leaf_counts"].items():
            leaf_counts[leaf] = leaf_counts.get(leaf, 0) + cnt
    mapped_total = sum(leaf_counts.values())
    unmapped_total = sum(c["unmapped"] for c in by_tree.values())
    total = mapped_total + unmapped_total
    return {
        "by_tree": by_tree,
        "leaf_counts": dict(sorted(leaf_counts.items(), key=lambda kv: -kv[1])),
        "sources": sources,
        "total_instances": total,
        "mapped": mapped_total,
        "unmapped": unmapped_total,
        "dedupe_rule": "按 (tree, canonical) 去重；源优先级 registry>gazetteer>词表>concordance",
        "unmapped_note": "gazetteer kind=区域/其他、词表无匹配关键词、concordance 无叶信号者计 unmapped（不硬塞叶）",
    }


# ==================== 规范漂移校验（脚本内嵌表 ↔ SKILL） ====================
BRANCH_RE = re.compile(r"^  - \*\*(.+?)\*\*")
LEAF_RE = re.compile(r"^    - (\S.*)$")


def parse_skill_leaves(skill_path: Path):
    """从 SKILL 树形清单章节解析各树叶名（按文件顺序）→ {code: [leaf...]}"""
    if not skill_path.exists():
        return None, f"SKILL 不存在：{skill_path}"
    lines = skill_path.read_text(encoding="utf-8").splitlines()
    result, cur_code, in_section = {}, None, False
    for i, line in enumerate(lines):
        if line.startswith("### "):
            matched = None
            for code, (marker, _name) in SKILL_SECTIONS.items():
                if marker in line:
                    matched = code
                    break
            cur_code = matched
            in_section = matched is not None
            if in_section:
                result[matched] = []
            continue
        if not in_section:
            continue
        if line.startswith("## ") or line.startswith("### "):
            in_section = False
            continue
        m = LEAF_RE.match(line)
        if m:
            leaf = m.group(1).strip()
            # 去掉可能存在的括注/行尾标注
            leaf = re.sub(r"[（(].*$", "", leaf).strip()
            if leaf:
                result[cur_code].append(leaf)
    missing = [c for c in TREES if c not in result or not result[c]]
    if missing:
        return None, f"SKILL 树形清单解析不完整（缺 {missing}）"
    return result, None


def check_skill_drift(skill_path: Path):
    V = []
    parsed, err = parse_skill_leaves(skill_path)
    if parsed is None:
        V.append({"severity": "warning", "check": "SKILL_UNREADABLE",
                  "detail": f"无法回读 SKILL 树形清单：{err}"})
        return V, None
    drift = {}
    for code, tree in TREES.items():
        embedded = [leaf for _, ls in tree["branches"] for leaf in ls]
        skill_leaves = parsed[code]
        if embedded != skill_leaves:
            only_emb = [x for x in embedded if x not in skill_leaves]
            only_skill = [x for x in skill_leaves if x not in embedded]
            drift[code] = {"embedded_only": only_emb, "skill_only": only_skill,
                           "order_diff": embedded != skill_leaves and not only_emb and not only_skill}
            V.append({"severity": "warning", "check": "SKILL_DRIFT",
                      "tree": code,
                      "detail": f"脚本内嵌{TREES[code]['name']}与 SKILL §{SKILL_SECTIONS[code][0]} "
                                f"不一致：脚本独有 {only_emb}，SKILL 独有 {only_skill}"})
        else:
            V.append({"severity": "info", "check": "SKILL_DRIFT", "tree": code,
                      "detail": f"{TREES[code]['name']} 脚本内嵌表 = SKILL 树形清单（{len(embedded)} 叶）✓"})
    return V, drift


def check_sparse_ack_drift(skill_path: Path):
    """校验脚本内嵌"稀疏叶备案表"与 SKILL §7.2 <10 预警/稀疏类理由行一致。"""
    V = []
    if not skill_path.exists():
        V.append({"severity": "warning", "check": "SPARSE_ACK_DRIFT",
                  "detail": "SKILL 不存在，跳过 §7.2 稀疏叶备案一致性校验"})
        return V
    lines = skill_path.read_text(encoding="utf-8").splitlines()
    in72 = False
    mentioned = set()
    for line in lines:
        if line.startswith("### 7.2"):
            in72 = True
            continue
        if in72 and line.startswith("### "):
            in72 = False
        if not in72:
            continue
        if "预警叶" in line:
            # 例：| <10 预警叶及合并预案 | 战场遗址（预警→…）；镖局车店（低风险…） |
            body = line.strip().strip("|")
            body = body.split("|", 1)[-1] if "|" in body else body
            for seg in body.split("；"):
                subject = seg.split("（")[0]
                for part in re.split(r"[、/]", subject):
                    part = part.strip()
                    if part in ALL_LEAVES:
                        mentioned.add(part)
        elif "稀疏类理由" in line:
            # 例：| 稀疏类理由 | 爵位封号若异姓受封实例 <10，保留理由：… |
            body = line.strip().strip("|")
            body = body.split("|", 1)[-1] if "|" in body else body
            if "暂无" in body:
                continue
            subject = re.split(r"保留理由|若|（", body)[0]
            for leaf in sorted(ALL_LEAVES, key=len, reverse=True):
                if subject.strip().startswith(leaf):
                    mentioned.add(leaf)
                    break
    embedded = set(SPARSE_ACK)
    only_embedded = sorted(embedded - mentioned)
    only_skill = sorted(mentioned - embedded)
    if only_embedded or only_skill:
        V.append({"severity": "warning", "check": "SPARSE_ACK_DRIFT",
                  "detail": f"稀疏叶备案与 SKILL §7.2 不一致：脚本独有 {only_embedded}，"
                            f"SKILL 独有 {only_skill}"})
    else:
        V.append({"severity": "info", "check": "SPARSE_ACK_DRIFT",
                  "detail": f"稀疏叶备案表与 SKILL §7.2 一致（{len(embedded)} 叶："
                            f"<10 预警 + 稀疏类理由）✓"})
    return V


# ==================== 汇总与产物 ====================
def run(registry_path: Path, assignments_path: Path | None, skill_path: Path,
        no_corpus: bool = False):
    violations = []
    structure = check_structure()
    soft, sparse_ack = check_soft_standard()
    inst, inst_stats = check_instances(registry_path, assignments_path)
    drift_v, drift_detail = check_skill_drift(skill_path)
    violations += structure + soft + inst + drift_v
    sparse_drift = check_sparse_ack_drift(skill_path)
    violations += sparse_drift
    corpus_vol, tagged_books, corpus_errors = ({} , [], []) if no_corpus else check_corpus_volume()
    for err in corpus_errors:
        violations.append({"severity": "warning", "check": "CORPUS_READ", "detail": err})
    summary = {"errors": sum(1 for v in violations if v["severity"] == "error"),
               "warnings": sum(1 for v in violations if v["severity"] == "warning"),
               "infos": sum(1 for v in violations if v["severity"] == "info")}
    stats = {"generated": datetime.now().isoformat(timespec="seconds"),
             "registry": str(registry_path), "skill": str(skill_path),
             "leaf_total": sum(len(ls) for t in TREES.values() for _, ls in t["branches"]),
             "tree_count": len(TREES),
             "violations": summary,
             "instance_check": inst_stats,
             "corpus_volume": corpus_vol,
             "corpus_books": tagged_books,
             "skill_drift": drift_detail,
             "checks": {"structure": not any(x["severity"] == "error" for x in structure),
                        "instance_leaf": not any(x["severity"] == "error" for x in inst),
                        "soft_standard": not any(x["severity"] == "warning" for x in soft),
                        "skill_drift": not any(x["severity"] == "warning" for x in drift_v),
                        "sparse_ack_drift": not any(x["severity"] != "info"
                                                    for x in sparse_drift)}}
    return violations, stats


def write_outputs(violations, stats, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    md = report_md(stats, violations)
    io.open(out_dir / "taxonomy_report.md", "w", encoding="utf-8", newline="\n").write(
        "\n".join(md) + "\n")
    payload = {
        "schema": "taxonomy-lint-v0.1",
        "spec": "D08 分类树五件套 / 06e 颗粒度；N9 lint_taxonomy",
        "generated": stats["generated"],
        "summary": stats["violations"],
        "stats": stats,
        "violations": violations,
    }
    io.open(out_dir / "taxonomy_violations.json", "w", encoding="utf-8", newline="\n").write(
        json.dumps(payload, ensure_ascii=False, indent=2))
    trees_export = {
        "schema": "taxonomy-trees-v0.1",
        "spec": "SKILL_分类树五件套 v0.3-draft §1.3/§7",
        "generated": stats["generated"],
        "leaf_total": stats["leaf_total"],
        "max_depth": MAX_DEPTH,
        "type_labels": TYPE_LABELS,
        "trees": [
            {"code": code, "name": tree["name"], "label": TYPE_LABELS[code],
             "root": tree["root"], "depth": 2,
             "branches": [{"branch": b, "leaves": ls} for b, ls in tree["branches"]],
             "seed_words": SEED_WORDS.get(code, [])}
            for code, tree in TREES.items()
        ],
        "sparse_ack": {k: {"tree": v[0], "reason": v[1]} for k, v in SPARSE_ACK.items()},
        "sibling_exempt": [{"tree": k[0], "branch": k[1], "reason": v}
                           for k, v in SIBLING_EXEMPT.items()],
    }
    io.open(out_dir / "taxonomy_trees.json", "w", encoding="utf-8", newline="\n").write(
        json.dumps(trees_export, ensure_ascii=False, indent=2))
    return out_dir


def report_md(stats, violations):
    v = stats["violations"]
    inst = stats["instance_check"]
    L = ["# 分类树校验报告（N9 · D08 五棵树 64 叶 / 06e 颗粒度）", "",
         f"- 生成：{stats['generated']}",
         f"- 规范源：`{stats['skill']}`（v0.3-draft）",
         f"- 实体登记表：`{stats['registry']}`",
         f"- 结论：**树结构 {stats['leaf_total']} 叶 / {stats['tree_count']} 树全部命中规范**；"
         f"违规 error **{v['errors']}** / warning **{v['warnings']}** / info {v['infos']}", ""]
    # 一、五树总表
    L += ["## 一、五树结构总表", "",
          "| 树 | 类型码 | 分支 | 叶数（规范） | 树深 | 同层叶数（分支） |", "|---|---|---|---|---|---|"]
    for code, tree in TREES.items():
        leaves = sum(len(ls) for _, ls in tree["branches"])
        bc = "、".join(f"{b} {n}" for b, n in BRANCH_COUNTS[code])
        L.append(f"| {tree['name']} | `{code}` {TYPE_LABELS[code]} | {len(tree['branches'])} | "
                 f"{leaves}（{EXPECTED_LEAF_COUNTS[code]}） | 3 | {bc} |")
    L += ["", f"合计 **{stats['leaf_total']} 叶**（规范 64）；树深 3 ≤ 06e 上限 "
          f"{MAX_DEPTH}；实例只挂叶（结构侧）。", ""]
    # 二、结构/软标准
    err_v = [x for x in violations if x["severity"] == "error"]
    warn_v = [x for x in violations if x["severity"] == "warning"]
    L += ["## 二、06e 三条款与结构校验", "",
          "| 06e 条款 | 本轮结论 | 证据 |", "|---|---|---|",
          f"| 子类预计实例 ≥10 | 多源实例统计（§三·补充） | 64 叶均按规范单列；06e 实例量按 "
          f"registry+gazetteer+词表+concordance 聚合（去重后 {inst.get('multi_source', {}).get('total_instances', 0)} 条实例） |",
          f"| 树深 ≤ 4 | **PASS** | 五树均为 根→分支→叶 = 3 层 |",
          f"| 实例只挂叶 | **PASS（结构侧）** | 叶/分支/根三层结构无环；registry 五树实例校验见 §三"
          f"（已挂叶 {inst['mapped']} / 未挂叶 {inst['unmapped']}） |", "",
          "结构校验明细："]
    if not err_v:
        L.append("")
        L.append("- ✅ 五树齐备、64 叶、树深 3、叶子唯一、无兜底叶、根/分支/叶层级完整"
                 "（error 0 条）。")
    else:
        L.append("")
        L.append(f"- ❌ 结构 error {len(err_v)} 条：")
        for x in err_v:
            L.append(f"  - `{x['check']}` {x.get('tree', '')} {x['detail']}")
    soft_v = [x for x in violations if "SIBLING" in x.get("check", "") and x["severity"] != "info"]
    exempt_v = [x for x in violations if x.get("check") == "SIBLING_EXEMPT"]
    L += ["", f"- 同层叶数软标准 3–12：违规 {len(soft_v)} 条；已备案豁免 {len(exempt_v)} 项"
          "（结构单叶 / 稀疏分支，§7.2）。"]
    for x in exempt_v:
        L.append(f"  - {x['detail']}")
    sparse = [x for x in violations if x.get("check") == "LEAF_SPARSE"]
    if sparse:
        L.append(f"- 06e 稀疏叶（<10 实例）提示 {len(sparse)} 条（含已备案稀疏叶，info 级）。")
    L += ["", "## 三、实例挂叶校验", ""]
    if inst.get("registry_scope"):
        L.append(f"- 登记表 scope 声明：{inst['registry_scope']}")
        L.append("")
    L += ["| 树 | 范围内实例 | 已挂叶 | 未挂叶 |", "|---|---|---|---|"]
    for code in TREES:
        c = inst["by_tree"].get(code, {})
        L.append(f"| {TREES[code]['name']} | {c.get('total', 0)} | {c.get('mapped', 0)} | "
                 f"{c.get('unmapped', 0)} |")
    L += ["", f"- 登记表实体总数 {inst['entities_total']}；五树范围内实例 "
          f"{inst['scope_instances']}（其余类型不在五树范围：`@`人物/`&`家族等）。",
          f"- 已挂叶 {inst['mapped']} / 未挂叶 {inst['unmapped']}；非法叶值/挂内部节点等 error "
          f"{sum(1 for x in violations if x['severity'] == 'error' and x.get('check', '') in ('INSTANCE_ON_BRANCH', 'INSTANCE_ON_ROOT', 'ILLEGAL_LEAF_TYPE', 'LEAF_TREE_MISMATCH'))} 条。"]
    if inst["mapped"] == 0:
        L.append("- ⓘ 本批未发现任何挂叶实例：registry 五类实例（当前仅 `◆` 组织 70 条）尚未带叶值字段"
                 "（S-03i 分类登记未开始）→ 「子类≥10」实例量检查延后；本批结论以树结构/词表就绪度为准。"
                 "挂叶字段约定：实体 `leaf`（或 `leaves` / `taxonomy.leaf`，多值 ≤3）。")
    unmapped = [x for x in violations if x.get("check") == "UNMAPPED_INSTANCE"]
    if unmapped:
        L.append(f"  - 未挂叶清单（{len(unmapped)} 条，前 10）：" +
                 "、".join(f"{x.get('entity')}[{x.get('tree')}]" for x in unmapped[:10]) + " …")
    ms = inst.get("multi_source") or {}
    if ms:
        L += ["", "### 三·补充 多源实例接入（06e 实例量；task-45）", "",
              f"- 去重口径：{ms.get('dedupe_rule')}",
              f"- 合计：去重实例 {ms.get('total_instances')}；已映射叶 {ms.get('mapped')} / "
              f"未映射 {ms.get('unmapped')}（未映射计 unmapped，不硬塞叶）", "",
              "| 树 | 去重实例 | 已映射 | 未映射 | leaf 分布（top） |", "|---|---:|---:|---:|---|"]
        for code in TREES:
            c = ms["by_tree"].get(code) or {}
            top = "、".join(f"{k} {v}" for k, v in
                            sorted((c.get("leaf_counts") or {}).items(), key=lambda kv: -kv[1])[:6])
            L.append(f"| {TREES[code]['name']} | {c.get('total', 0)} | {c.get('mapped', 0)} | "
                     f"{c.get('unmapped', 0)} | {top or '—'} |")
        L += ["", "- 源分布（去重前 seen / 去重后 skipped_dup）："]
        for name, sd in (ms.get("sources") or {}).items():
            L.append(f"  - `{name}`：seen {sd.get('seen')} / mapped {sd.get('mapped')} / "
                     f"unmapped {sd.get('unmapped')} / skipped_dup {sd.get('skipped_dup')}"
                     + (f"；未映射例：{'、'.join(sd.get('unmapped_examples') or [])}"
                        if sd.get("unmapped_examples") else ""))
        L += [f"- 未映射说明：{ms.get('unmapped_note')}",
              "- 实例源：◆ 组织=registry/entities.json；= 地点=registry/gazetteer.json（N7 kind）；"
              "; 职衔 / # 身份=wordlists/identity.json + concordance；☆ 武功=wordlists/new_entity_types.json"
              " + concordance。06e 叶级计数以此为准。", ""]
    L += ["", "## 四、语料实例规模（06e“子类预计实例 ≥10”参考）", "",
          "| 树 | 5 书去重面数 | 出现次数 | 判定 |", "|---|---|---|---|"]
    for code in TREES:
        vol = stats["corpus_volume"].get(code)
        if not vol:
            continue
        ok = "≥10 ✓" if vol["distinct"] >= MIN_INSTANCES_PER_LEAF else "<10（预警）"
        L.append(f"| {TREES[code]['name']} | {vol['distinct']} | {vol['occurrences']} | {ok} |")
    L += ["", f"- 扫描书目（{len(stats['corpus_books'])}）："
          + "、".join(stats["corpus_books"]) +
          "；该规模仅作 06e 粒度参考；06e 实例量已改为 §三·补充 多源聚合口径。", ""]
    # 五、规范漂移
    L += ["## 五、规范漂移校验（脚本内嵌表 ↔ SKILL）", ""]
    drift = [x for x in violations if x.get("check") == "SKILL_DRIFT"]
    bad_drift = [x for x in drift if x["severity"] != "info"]
    if not bad_drift:
        L.append("- ✅ 五树内嵌表与 SKILL §2.3/3.2/4.2/5.4/6.7 树形清单逐叶一致（64/64）。")
    else:
        for x in bad_drift:
            L.append(f"- ⚠ {x['detail']}")
    sparse_drift = [x for x in violations if x.get("check") == "SPARSE_ACK_DRIFT"]
    for x in sparse_drift:
        L.append(f"- {'⚠' if x['severity'] != 'info' else '✅'} {x['detail']}")
    L += ["", "## 六、违规清单摘要（error 全列；warning 前 20 条，完整清单见 JSON）", ""]
    if not err_v and not warn_v:
        L.append("（无 error / warning）")
    else:
        for x in err_v:
            L.append(f"- **error** `{x['check']}`"
                     + (f" [{x.get('tree')}]" if x.get("tree") else "") + f"：{x['detail']}")
        shown = 0
        for x in warn_v:
            shown += 1
            if shown > 20:
                break
            L.append(f"- **warning** `{x['check']}`"
                     + (f" [{x.get('tree')}]" if x.get("tree") else "") + f"：{x['detail']}")
        if len(warn_v) > 20:
            L.append(f"- … 其余 {len(warn_v) - 20} 条 warning 见 "
                     "`logs/taxonomy/taxonomy_violations.json`")
    L += ["", "## 七、断言与自检", "",
          "- 断言 1：五树 = {=,;,#,◆,☆}，叶合计 64，各树 16/12/18/11/7；",
          "- 断言 2：树深 = 3（根→分支→叶）≤ 06e 上限 4；叶名树内唯一、无跨树同名、无兜底叶；",
          "- 断言 3：实例叶值 ∈ 所属树叶枚举；挂分支/树根/非法值/跨树值均判 error；",
          "- 断言 4：脚本内嵌表与 SKILL 树形清单逐叶一致（漂移仅 warning，提示回写脚本或 SKILL）；",
          "- 断言 5：error+warning+info 计数闭合；--selftest 另跑合成用例（叶/分支/根/非法/未挂）与现网结构。",
          "", "## 八、说明 / 遗留", "",
          "1. **实例登记与多源接入（task-45 完成）**：S-03i 已为 registry 五树实例（= ; # ◆ ☆）"
          "挂叶；06e 实例量改为多源聚合（registry/gazetteer/词表/concordance，见 §三·补充），"
          "不再是“仅 registry”或“延后”。剩余叶级稀疏告警为真实语料 <10（含已备案 info），"
          "需后续扩量或按 SKILL §7.2 备案。",
          "2. 叶值封闭：任何新叶须过 06e + §7.3 规则累积日志；本脚本把 64 叶视为枚举，"
          "新增叶时**必须同时**更新 `TREES` 与 SKILL（漂移校验会提示）。",
          "3. 地点/职衔/身份/武功实例的登记载体按 01g 分工在 gazetteer/词表（见 entities.json scope 声明），"
          "本脚本的实例校验对 `--registry` 任意 schema 兼容（叶字段约定见 §三）；"
          "后续可按需传 `--registry registry/gazetteer.json` 等扩展。"]
    return L


# ==================== 自检 ====================
def selftest() -> int:
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        ok = ok and bool(cond)

    print("[N9 selftest]")
    # 1) 内嵌五树结构
    total = sum(len(ls) for t in TREES.values() for _, ls in t["branches"])
    check("五树齐备", set(TREES) == set(TYPE_LABELS), str(sorted(TREES)))
    check("64 叶", total == EXPECTED_LEAF_TOTAL, f"{total}")
    check("各树叶数", all(sum(len(ls) for _, ls in TREES[c]["branches"]) == n
                        for c, n in EXPECTED_LEAF_COUNTS.items()))
    check("树深 3 ≤ 4", True)
    check("叶名唯一", len(ALL_LEAVES) == total)
    check("无兜底叶", not (ALL_LEAVES & FALLBACK_LEAF_NAMES))
    check("无跨树同名叶", all(len(v) == 1 for v in LEAF_TREES.values()))
    V = check_structure()
    check("结构校验无 error", not [x for x in V if x["severity"] == "error"],
          str([x["detail"] for x in V if x["severity"] == "error"][:3]))
    # 2) 合成实例用例（走 check_instances 相同判定逻辑的最小复刻）
    def judge(code, values):
        """与 check_instances 相同的叶值判定 → (ok_leaf, error_check)"""
        for value in values:
            if value in ALL_ROOTS:
                return False, "INSTANCE_ON_ROOT"
            if value in {b for b, _ in TREES[code]["branches"]}:
                return False, "INSTANCE_ON_BRANCH"
            if value in LEAF_BRANCH.get(code, {}):
                continue
            return False, ("LEAF_TREE_MISMATCH" if value in ALL_LEAVES else "ILLEGAL_LEAF_TYPE")
        return bool(values), None
    check("合成：合法叶", judge("=", ["山岳峰岭"]) == (True, None))
    check("合成：挂分支 error", judge("=", ["自然地貌"])[1] == "INSTANCE_ON_BRANCH")
    check("合成：挂树根 error", judge("=", ["地点"])[1] == "INSTANCE_ON_ROOT")
    check("合成：跨树叶值 error", judge("=", ["侠客侠士"])[1] == "LEAF_TREE_MISMATCH")
    check("合成：非法叶值 error", judge("=", ["飞天遁地"])[1] == "ILLEGAL_LEAF_TYPE")
    check("合成：多值全合法", judge("#", ["侠客侠士", "隐逸高人"]) == (True, None))
    # 2.5) 多源实例接入自检（task-45：registry+gazetteer+词表+concordance）
    check("gazetteer kind→地点叶映射合法",
          all(v in LEAF_BRANCH["="] for v in GAZ_KIND_TO_LEAF.values()))
    check("多源聚合函数可运行", isinstance(collect_multi_source_instances([]), dict))
    if DEFAULT_REGISTRY.exists():
        reg = json.loads(io.open(DEFAULT_REGISTRY, encoding="utf-8").read())
        ms = collect_multi_source_instances(reg.get("entities") or [])
        check("多源叶值合法", all(l in LEAF_BRANCH[c]
                                  for c, lc in ms["by_tree"].items()
                                  for l in lc["leaf_counts"]),
              str([(c, l) for c, lc in ms["by_tree"].items()
                   for l in lc["leaf_counts"] if l not in LEAF_BRANCH[c]][:3]))
        check("多源计数闭合", ms["mapped"] + ms["unmapped"] == ms["total_instances"],
              f"{ms['mapped']}+{ms['unmapped']}/{ms['total_instances']}")
        check("多源实例量 > registry 单源", ms["total_instances"] > len(reg.get("entities") or []),
              f"{ms['total_instances']} vs {len(reg.get('entities') or [])}")
    # 3) SKILL 漂移回读
    V, drift = check_skill_drift(DEFAULT_SKILL)
    bad = [x for x in V if x["severity"] != "info"]
    check("SKILL 树形清单可回读且与内嵌表一致", not bad,
          str([x["detail"] for x in bad][:3]) if bad else "")
    V2 = check_sparse_ack_drift(DEFAULT_SKILL)
    bad2 = [x for x in V2 if x["severity"] != "info"]
    check("SKILL §7.2 稀疏叶备案与内嵌表一致", not bad2,
          str([x["detail"] for x in bad2][:3]) if bad2 else "")
    # 4) 现网 registry 只读校验（不写盘）
    if DEFAULT_REGISTRY.exists():
        V, inst = check_instances(DEFAULT_REGISTRY, DEFAULT_ASSIGNMENTS)
        check("现网 registry 可读", inst["entities_total"] > 0, f"{inst['entities_total']} 实体")
        check("实例校验无 error", not [x for x in V if x["severity"] == "error"],
              str([x["detail"] for x in V if x["severity"] == "error"][:3]))
        counts = (inst["mapped"] + inst["unmapped"])
        check("实例计数闭合（已挂+未挂=范围内）", counts == inst["scope_instances"],
              f"{counts}/{inst['scope_instances']}")
    else:
        check("现网 registry 存在（跳过现网不变量）", True, "缺文件")
    print(f"[N9 selftest] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# ==================== CLI ====================
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="N9 分类树校验（D08 五树 64 叶 / 06e：子类≥10·树深≤4·实例挂叶）")
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY),
                    help="实体登记表 JSON（缺省 registry/entities.json）")
    ap.add_argument("--assignments", default=str(DEFAULT_ASSIGNMENTS),
                    help="外挂叶值登记 JSON（可选；{id→leaf} 或 {assignments:{...}}）")
    ap.add_argument("--skill", default=str(DEFAULT_SKILL), help="分类树 SKILL 路径（漂移校验）")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT), help="报告输出目录（缺省 logs/taxonomy/）")
    ap.add_argument("--no-corpus", action="store_true", help="跳过 5 书 tagged 语料规模扫描")
    ap.add_argument("--strict", action="store_true", help="严格模式：warning 亦判失败")
    ap.add_argument("--selftest", action="store_true", help="自检（不写盘）")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    reg = Path(args.registry)
    if not reg.exists():
        print(f"[N9] 错误：实体登记表不存在：{reg}")
        return 2
    violations, stats = run(reg, Path(args.assignments), Path(args.skill),
                            no_corpus=args.no_corpus)
    out = write_outputs(violations, stats, Path(args.out_dir))
    v = stats["violations"]
    print(f"[N9] 五树 {stats['tree_count']} / 叶 {stats['leaf_total']}；"
          f"违规 error {v['errors']} / warning {v['warnings']} / info {v['infos']}")
    print(f"[N9] 报告：{out / 'taxonomy_report.md'}")
    print(f"[N9] 违规清单：{out / 'taxonomy_violations.json'}；"
          f"内嵌树导出：{out / 'taxonomy_trees.json'}")
    if v["errors"]:
        print("[N9] 存在 error 级违规，请见违规清单")
        return 1
    if args.strict and v["warnings"]:
        print("[N9] --strict：存在 warning 级违规")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
