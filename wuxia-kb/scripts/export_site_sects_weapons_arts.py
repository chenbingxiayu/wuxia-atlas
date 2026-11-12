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
      python scripts/export_site_sects_weapons_arts.py --scope tianshan-demo   # 天山 7 书裁剪口径

W0-T3a（天山演示版总体方案 §1.2，2026-11-08）scope 口径：
  - sects：books ∩ scope（scope 内无出现的门派不入表）、arts_by_pred 按 book 过滤；
  - weapons：books/chain/evidence 按 book 过滤 + count 按 concordance scope 内计数重算
    （holders 无逐书归属保持原值，field_gaps 声明）；
  - arts：relations book 键过滤 + books 裁剪 + ev_total 重算（relations 证据优先，
    无 relations 者按 concordance scope 内计数）；
  - 全量口径（不带 --scope）行为与现状完全一致（方案 R6）。

W2-B6（门派志页重构设计 §一决策 1/3、§五、§八，2026-11-10）势力类型/驻地考订：
  - sects：读 kb/校订/门派驻地考订.tsv（人工校定行）→ 记录注入 type（名门正派/世家/绿林
    帮会/朝廷势力）+ seat{name,status,basis}；未入表门派无该字段（前端按字段存在性分区）；
  - 考订在案而管线未收的势力（大内等：组织后缀不在白名单）由 concordance ◆/& 证据入册
    （source="new"，books/ev_total 取 conc 口径）；库内无出现记录的行不入表（notes 声明）；
  - weapons/arts 不受影响（注入只发生在 build_sects）。

W3-T4（武功页重构设计 §5.2/§5.3/§六/§九，2026-11-10）武功详情页数据层：
  - arts.comments：读 kb/校订/武功评语.tsv（L1 短引文，人工校定稿唯一真源）→ 记录注入
    comments=[{quote,book,loc}]（评语卡渲染「引文—— 原著 · 书 NN:NN」）；闸门=单条 ≤16 字、
    每门 ≤2 条、status ∈ {校定, draft}（只消费 校定）、loc 须「书·NNN:NNN」式；评语非证据，
    不计入 ev_total；scope 口径下评语书 ∉ scope 不消费；
  - arts.lineage：传授行 note 解析（parse_lineage_note 纯函数）→ s→l 配对真边
    [{t,l,book,loc,tier}]（tier=正式/记名/挂名/点拨，档位从 note 词面判定）。数据源调查
    结论（W3-T4 报告）：relations 无 object 字段、配对只活在 note 明文；graph.json 传授边
    全站 1 条（移形换影）且师承边无武功标签，均不可用作武功内配对源。红线=无配对不强造：
    解析不出 / 学生未在同门武功关系表出现 / 学生=传授者本人 → 不入表，meta 报告待人工补链；
  - weapons/sects 不受影响（注入只发生在 build_arts）。

D10（武功传承树人工补链 + 游龙剑 holders 补录，武功页重构设计 §6.2 数据源三层第 3 层/
§八.5 首批裁定，2026-11-12）：
  - arts.lineage 合并 kb/校订/武功传承补链.tsv（人工校定稿唯一真源）：首批 3 边=
    凌未风—记名→周青、周青—记名→{冯广潮, 唐晓澜}（追风剑法五代链，三女侠 001:113/
    001:125/001:141 明文，loc 逐条 grep 核实）；TSV 行为人工考订，免「同门关系表
    attestation」闸；与 note 解析边同 (t,l,book,loc) 去重（跳过并记 field_gaps），同对
    新定位符并入多定位符（前端归组取最强档）；scope 口径书外行不消费；
  - weapons.holders 补录：读 kb/校订/神兵表-补录.tsv → holders 追加
    {name, n:0, sup:{book,loc,note}}（「考订补录」注；不伪造神兵表扫描频次）——
    首批：游龙剑 holders 补周青（三女侠 001:141「凌未风竟会送给周青」/002:31
    「靠着这把宝剑逃生」明文）；rev17/end_state 之后合并（不影响头部 holders 计算）；
  - 前端：weapons 页 holders 补录人渲染「考订补录」tag（arts 页传承树零改动——
    W3-T4 四档边型/图例/多定位符归组已就绪）。

D7（名物 end_state 按宇宙编年重算，scope 口径，2026-11-11）：
  - 现状（build_artifacts.py 生成口径，父仓冻结不改）：end_state=「末见持有：<holders 前 2>
    （<书>·<回> 回）」，书·回 = max(occs, key=(回,行))——跨书只比回号、并列取扫描序首个，
    即 end_state 取「语料扫描顺序的最后一个提及」而非「宇宙编年最晚的提及」（D5 发现：
    虎头钩 end_state 末见=白发魔女传 23 回，早于其主线毁边 江湖三女侠 9:13——归宿与主线
    编年互相矛盾）；
  - 新规则（recalc_end_state 纯函数，rev17 之后调用、chron_key 口径复用）：主线=非 suspect
    边（suspect 毁边已折叠「疑似误伤」，与前端同口径）；主线编年最末「毁」边的（书序, 回）=
    全件编年最末提及（books 回目集 ∪ 主线边回号 取 max）→ end_state=「毁于：<边 persons>
    （书 · N 回）」；否则「末见持有：<holders 前 2>（<编年最末提及的书>·<最大回> 回）」——
    文案式样与旧生成一致，只改计算口径；无提及或无持有人 → None（旧口径不伪造）；
  - meta.totals：end_state_recalc（与旧值不同件数）/ end_state_destroyed（毁于件数）；
  - 全量口径（scope=None）不调用：end_state 原样透传神兵表旧值（方案 R6）。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import export_site_common as esc  # noqa: E402

KB = config.LEGACY_KB
ROOT = config.ROOT

# 新管线书单（4 旧书 + 冰魄寒光剑 + 2026-11-07 扩书 P1-P3 批次 10 书 = 15 书）；旧站基线 4 书
# 注意：前 4 书顺序是旧站契约基线，不要重排；其余一律追加在末尾。
BOOKS = ["七剑下天山", "塞外奇侠传", "江湖三女侠", "白发魔女传", "冰魄寒光剑",
         "冰川天女传", "还剑奇情录", "萍踪侠影录", "散花女侠", "云海玉弓缘",
         "冰河洗剑录", "联剑风云录", "广陵剑", "风雷震九州", "侠骨丹心",
         "剑网尘丝", "幻剑灵旗", "大唐游侠传", "龙凤宝钗缘", "慧剑心魔",
         "飞凤潜龙", "草莽龙蛇传", "龙虎斗京华", "绝塞传烽录"]
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
# D5 rev17（名物页重构设计 §六毁噪声自动证伪 + §5.1 疑似误伤折叠，2026-11-11）：
# ①后续证伪 ②主语证伪 ③编年排序 ④去重 ⑤方向化——**仅 scope 口径接线**（build_weapons 内
# books 合并后调用 rev17_chain）；全量口径（scope=None）不调用，行为与现状逐字段一致（方案 R6）。
# 边新增字段（scope 口径）：n（去重计数 ≥1）/ suspect=True（毁边后续证伪，前端折叠）/
# subject_low=True（毁边主语降权注记，保留主线）/ dir={"kind": 铸|借, "who": [名…]}（方向化主语）。
REV17 = 17
DESTROY_VERB = "毁"
# 毁后不算「存活铁证」的动词：毁=毁句本身不自证；铸=可能是重铸（原物或已毁，存疑）——宁缺毋滥
NO_LIFE_VERBS = {"毁", "铸"}
SUBJECT_LOW_HOLDERS = 5      # 主语证伪「持有人高频」= holders 前 5（ holders 已按 n 降序）


def parse_loc_pair(loc) -> tuple[int, int]:
    """「章:行」→ (章, 行) int；「书名·NNN:NNN」书名前缀剥去；解析失败 → (0, 0)。"""
    if not isinstance(loc, str):
        return (0, 0)
    if esc.LOC_SEP in loc:
        loc = loc.partition(esc.LOC_SEP)[2]
    ch, _, ln = loc.partition(":")
    try:
        return (int(ch), int(ln) if ln else 0)
    except ValueError:
        return (0, 0)


def chron_key(edge: dict, book_order: dict) -> tuple:
    """编年键（宇宙书序, 章, 行, 书名）：书不在序内排最后（书名序稳定兜底）。"""
    b = edge.get("book") or ""
    ch, ln = parse_loc_pair(edge.get("loc"))
    return (book_order.get(b, len(book_order)), ch, ln, b)


def dedupe_chain(chain: list) -> list:
    """④ 完全重复边（verb+persons+book+loc 键）合并：保首现序，n=重复次数（≥1）。

    persons 为逐边拷贝（不共享可变列表）；conf 取首现值（键不含 conf，完全重复边实际同 conf）。
    """
    seen = {}
    out = []
    for e in chain:
        key = (e.get("verb"), tuple(e.get("persons") or []), e.get("book"), e.get("loc"))
        if key in seen:
            seen[key]["n"] += 1
            continue
        e2 = dict(e)
        e2["persons"] = list(e.get("persons") or [])
        e2["n"] = 1
        seen[key] = e2
        out.append(e2)
    return out


def sort_chain_chrono(chain: list, book_order: dict) -> list:
    """③ 编年排序（书按宇宙编年、回按章号、行号兜底；稳定排序）。"""
    return sorted(chain, key=lambda e: chron_key(e, book_order))


def mark_destroy_suspect(chain: list, books: dict, book_order: dict) -> int:
    """① 后续证伪（宁缺毋滥，in-place）：毁边之后（编年序）仍有存活铁证 → suspect=True。

    铁证两类（设计 §六 1「同书或后续书仍有持有/出场记录」）：
      a) 持有：编年序更后的 chain 边 verb ∉ NO_LIFE_VERBS（任何 conf——ok 档交战侧证=出场）；
      b) 出场：books 同书更大回号，或编年序更后的书任一回目（books=concordance 出现回目集）。
    无铁证 → 不标记（保留主线；毁边=终局时与 end_state 口径一致）。
    """
    n = 0
    for i, e in enumerate(chain):
        if e.get("verb") != DESTROY_VERB:
            continue
        kb = chron_key(e, book_order)
        # a) 后续 chain 边持有/出场铁证
        later_edge = any(chron_key(later, book_order) > kb
                         and later.get("verb") not in NO_LIFE_VERBS
                         for later in chain[i + 1:])
        # b) books 出场铁证：同书更大回号 / 编年序更后书任一回目
        b, (ch, _ln) = e.get("book") or "", parse_loc_pair(e.get("loc"))
        later_book = False
        if b in books and ch:
            later_book = any(c > ch for c in (books[b] or []) if isinstance(c, int))
        if not later_book:
            kb_rank = book_order.get(b, len(book_order))
            later_book = any(book_order.get(ob, len(book_order)) > kb_rank
                             for ob in books if ob != b and books[ob])
        if later_edge or later_book:
            e["suspect"] = True
            n += 1
    return n


def mark_destroy_subject_low(chain: list, holders: list) -> int:
    """② 主语证伪（降权注记，in-place，不折叠）：非 suspect 毁边 persons 首位
    ∉ 持有人高频前 5 → subject_low=True（前端主线内注记「存疑」，人工 TSV 裁定通道）。
    """
    if not holders:
        return 0
    freq = {h.get("name") for h in list(holders)[:SUBJECT_LOW_HOLDERS]}
    n = 0
    for e in chain:
        if e.get("verb") == DESTROY_VERB and not e.get("suspect"):
            persons = e.get("persons") or []
            if persons and persons[0] not in freq:
                e["subject_low"] = True
                n += 1
    return n


def attach_dir(chain: list, makers: list, borrowers: list) -> int:
    """⑤ 方向化（可方向化部分，in-place）：铸边主语=persons∩makers、借边主语=persons∩borrowers
    → dir={"kind": verb, "who": [命中名…]}（persons 序）。无命中不加（不伪造主语）；
    夺/赠/传无 object 数据不加（如实报告，方向化待 object 切片修复批次）。
    """
    maker_names = {m.get("name") for m in (makers or [])}
    borrower_names = {b.get("name") for b in (borrowers or [])}
    n = 0
    for e in chain:
        names = maker_names if e.get("verb") == "铸" else \
            borrower_names if e.get("verb") == "借" else None
        if not names:
            continue
        who = [p for p in (e.get("persons") or []) if p in names]
        if who:
            e["dir"] = {"kind": e["verb"], "who": who}
            n += 1
    return n


def rev17_chain(rec: dict, book_order: dict) -> dict:
    """rev17 五规则整体应用（scope 口径专用；rec 为 build_weapons 单条记录，in-place）。

    顺序：④去重 → ③编年排序 → ①后续证伪 → ②主语降权 → ⑤方向化。返回规则计数。
    """
    before = len(rec["chain"])
    rec["chain"] = sort_chain_chrono(dedupe_chain(rec["chain"]), book_order)
    suspect = mark_destroy_suspect(rec["chain"], rec.get("books") or {}, book_order)
    subject_low = mark_destroy_subject_low(rec["chain"], rec.get("holders") or [])
    ndir = attach_dir(rec["chain"], rec.get("makers") or [], rec.get("borrowers") or [])
    return {"suspect": suspect, "dedup_merged": max(0, before - len(rec["chain"])),
            "subject_low": subject_low, "dir": ndir}


# ---------------------------------------------------------------- end_state 编年重算（D7）
# 旧生成口径（build_artifacts.py，父仓冻结）：end_state=末见持有：<holders 前 2>（书·N 回），
# 书·回 = max(occs, key=(回,行)) —— 跨书只比回号、并列取扫描序首个 = 「扫描顺序的最后一个提及」。
# D7 新口径（scope 专用）：编年最末提及（books 回目集 ∪ 主线边回号）；主线最末「毁」边触达该
# 提及 → 毁于；文案式样不变（「末见持有：A、B（书 · N 回）」/「毁于：A、B（书 · N 回）」）。
END_STATE_HOLD = "末见持有"
END_STATE_DESTROY = "毁于"


def _chrono_last_mention(rec: dict, book_order: dict) -> tuple | None:
    """编年最末提及 (书序, 回, 书)：books（concordance 出现回目集，全量提及口径）∪
    主线（非 suspect）边回号，按 (书序, 回) 取 max；书不在编年序内不计（scope 口径已被裁剪）。"""
    best = None                                   # (rank, chapter, book)
    for b, chs in (rec.get("books") or {}).items():
        ints = [c for c in (chs or []) if isinstance(c, int)]
        if b in book_order and ints:
            k = (book_order[b], max(ints), b)
            if best is None or k[:2] > best[:2]:
                best = k
    for e in rec.get("chain") or []:
        if e.get("suspect"):
            continue                              # suspect 毁边已折叠出主线，不作为归宿提及
        b = e.get("book")
        if b in book_order:
            ch, _ln = parse_loc_pair(e.get("loc"))
            k = (book_order[b], ch, b)
            if best is None or k[:2] > best[:2]:
                best = k
    return best


def _last_mainline_destroy(rec: dict, book_order: dict) -> tuple | None:
    """主线（非 suspect）编年最末「毁」边 ((书序, 回, 行), edge)；无 → None。"""
    best = None
    for e in rec.get("chain") or []:
        if e.get("suspect") or e.get("verb") != DESTROY_VERB:
            continue
        b = e.get("book")
        if b not in book_order:
            continue
        k = (book_order[b], *parse_loc_pair(e.get("loc")))
        if best is None or k > best[0]:
            best = (k, e)
    return best


def _end_state_note_chrono(rec: dict, book_order: dict) -> str | None:
    """D7 规则注记（纯函数）：主线最末「毁」边的（书序, 回）= 编年最末提及 → 毁于：<边 persons>；
    否则 末见持有：<holders 前 2>（<编年最末提及的书>·<最大回> 回）；无提及或无持有人 → None。"""
    mention = _chrono_last_mention(rec, book_order)
    if mention is None:
        return None
    d = _last_mainline_destroy(rec, book_order)
    if d is not None and d[0][:2] == mention[:2]:
        e = d[1]
        names = "、".join(p for p in (e.get("persons") or []) if p) or "—"
        return f"{END_STATE_DESTROY}：{names}（{e['book']}·{d[0][1]} 回）"
    holders = [h.get("name") for h in (rec.get("holders") or []) if h.get("name")]
    if not holders:
        return None
    return f"{END_STATE_HOLD}：{'、'.join(holders[:2]) or '—'}（{mention[2]}·{mention[1]} 回）"


def recalc_end_state(rec: dict, book_order: dict) -> dict:
    """D7：scope 口径 end_state 按宇宙编年重算（in-place；rev17 之后调用——需 suspect 标记与
    编年 chain）。返回 {"changed": 与旧值不同, "destroyed": 毁于形态}。

    规则见 _end_state_note_chrono；end_state 结构保持 {"note": …}（契约不变）。
    """
    legacy = rec.get("end_state")
    legacy_note = legacy.get("note") if isinstance(legacy, dict) else legacy
    note = _end_state_note_chrono(rec, book_order)
    rec["end_state"] = {"note": note} if note else None
    return {"changed": note != legacy_note,
            "destroyed": bool(note and note.startswith(END_STATE_DESTROY))}


def scope_weapon_record(rec: dict, hit: dict | None, scope) -> dict:
    """单条 weapons 记录的 scope 裁剪（W0-T3a / 方案 §1.2）。

    chain/evidence 按 book ∈ scope 过滤；books 键过滤；count（出现次数）按 concordance
    scope 内书目计数重算。holders/borrowers/makers 的 n 神兵表无逐书归属，保持原值并
    在 meta.field_gaps 显式声明（不伪造逐书分解）。
    """
    rec["chain"] = [e for e in rec["chain"] if esc.in_scope(e.get("book"), scope)]
    rec["evidence"] = [e for e in rec["evidence"] if esc.in_scope(e.get("book"), scope)]
    rec["books"] = {b: v for b, v in rec["books"].items() if esc.in_scope(b, scope)}
    if hit:
        scoped = sum(int((hit.get("books") or {}).get(b) or 0) for b in scope.get("books", []))
        if scoped:
            rec["count"] = scoped
    return rec


def build_weapons(src: dict, scope=None, weapon_sup: list[dict] | None = None,
                  direction_sup: list[dict] | None = None) -> tuple[dict, dict]:
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
        if scope is not None:
            rec = scope_weapon_record(rec, hit, scope)     # W0-T3a：scope 裁剪 + count 重算
        records.append(rec)
        n_legacy += 1

    records.sort(key=lambda r: (-(r.get("count") or 0), r["canonical"]))

    # 若旧站记录含回号，优先保留旧 books（更细）（W0-T3a：scope 口径下旧书键同样过滤）
    for r in records:
        old = old_by.get(r["canonical"])
        if old and isinstance(old.get("books"), dict) and old["books"]:
            merged = {b: old["books"].get(b, []) for b in sort_books(set(old["books"]) | set(r["books"]))}
            for b in merged:
                if not merged[b] and isinstance(r["books"].get(b), list):
                    merged[b] = r["books"][b]
            if scope is not None:
                merged = {b: v for b, v in merged.items() if esc.in_scope(b, scope)}
            r["books"] = merged

    # W0-T3a：scope 口径下 scope 内无出现的名物不进表（books 过滤后为空）
    if scope is not None:
        records = [r for r in records if r["books"]]

    # D5 rev17（名物页重构设计 §六）：毁证伪/编年/去重/方向化——仅 scope 口径（方案 R6：
    # 全量口径不调用，chain 维持扫描序与重复边现状）。编年书序=scope["books"]（universe
    # lines 成员序，用户裁定 2026-11-08）；books 合并后调用（出场铁证取最终 books 口径）。
    # D7：rev17 之后 end_state 按宇宙编年重算（需 suspect 标记与编年 chain；全量口径不调用）。
    rev17_stats = {"suspect": 0, "dedup_merged": 0, "subject_low": 0, "dir": 0, "records": 0}
    end_stats = {"changed": 0, "destroyed": 0, "records": 0}
    # F6/D10（F6 前置装载）：神兵表-补录（holders 补录 + cmd 指令列 chain_move/chain_drop）。
    # chain 指令须先于 rev17 应用（编年/去重/毁证伪/end_state 看到迁移后 chain），全量口径
    # 同样应用（归属修正非呈现增强，不受方案 R6 门槛）；holders 补录仍在 rev17 之后合并
    #（补录人不在 holders 前 2/前 5，不影响 end_state 文案与毁边主语降权口径）。
    if weapon_sup is None:
        weapon_sup, wsup_stats = load_weapon_supplement()
        wsup_tsv_exists = WEAPON_SUP_TSV.exists()
    else:
        weapon_sup = weapon_sup or []
        wsup_stats = {"rows": len(weapon_sup), "consumed": len(weapon_sup), "draft": 0}
        wsup_tsv_exists = bool(weapon_sup)
    holder_rows = [r for r in weapon_sup if "kind" not in r]
    chain_rows = [r for r in weapon_sup if r.get("kind") in ("chain_move", "chain_drop")]
    chain_stats = apply_chain_instructions({r["canonical"]: r for r in records},
                                           chain_rows, alias, canon_set)
    if scope is not None:
        book_order = {b: i for i, b in enumerate(scope["books"])}
        for r in records:
            st = rev17_chain(r, book_order)
            rev17_stats["records"] += 1
            for k in ("suspect", "dedup_merged", "subject_low", "dir"):
                rev17_stats[k] += st[k]
            est = recalc_end_state(r, book_order)          # D7：end_state 编年重算（in-place）
            end_stats["records"] += 1
            end_stats["changed"] += int(est["changed"])
            end_stats["destroyed"] += int(est["destroyed"])

    # D10：holders 考订补录合并（§八.5「weapons 游龙剑 holders 补周青」）——holders 来自神兵表
    # 只读源（扫描频次），补录走校订 TSV 渠道不伪造频次：追加 {name, n:0, sup:{book,loc,note}}
    #（前端与 holders 合并显示 +「考订补录」注）。放在 rev17/end_state 之后：补录人不在
    # holders 前 2/前 5（end_state 文案与毁边主语降权只看头部），不影响既有计算。
    #（装载已在 rev17 之前完成——F6 chain 指令须先落链；此处只合并 holder_rows。）
    # D17b（前置）：名物流转方向注入——kb/校订/名物流转方向.tsv（人工校定稿唯一真源，用户
    # 裁定方案 A：草案 10 条全落 + 七剑 14:25 双行补入）。键 weapon+book+loc 命中 chain 边 →
    # dir={kind:行 verb, who:[from,to]}；rev17 之后调用（铸/借 dir 在先不覆盖）；无匹配边/
    # 无记录/书外行/已有 dir 跳过并计数（field_gaps 记账，不伪造不覆盖）。仅 scope 口径
    #（与 rev17 同门；全量口径方案 R6 不消费，夺/赠/传/还边保持 persons 并列现状）；
    # F6 迁移边在本注入之前已落位 → 方向 TSV 改挂目标器的行命中迁移后的边（dir 随边迁移）。
    if direction_sup is None:
        direction_sup, dir_stats = load_direction()
        dir_tsv_exists = DIRECTION_TSV.exists()
    else:
        direction_sup = direction_sup or []
        dir_stats = {"rows": len(direction_sup), "consumed": len(direction_sup), "draft": 0}
        dir_tsv_exists = bool(direction_sup)
    dir_inj = {"rows": len(direction_sup), "injected": 0, "out_scope": 0,
               "no_edge": [], "no_weapon": [], "has_dir": []}
    if scope is not None:
        dir_inj = inject_direction({r["canonical"]: r for r in records},
                                   direction_sup, alias, canon_set, scope)

    wsup_by_weapon: dict[str, list[dict]] = {}
    for row in holder_rows:
        canon = resolve(row["weapon"], alias, canon_set) or row["weapon"]
        wsup_by_weapon.setdefault(canon, []).append(row)
    n_wsup_merged = n_wsup_dup = n_wsup_out_scope = 0
    wsup_no_weapon: list[str] = []
    rec_by_canon = {r["canonical"]: r for r in records}
    for canon, rows in sorted(wsup_by_weapon.items()):
        rec = rec_by_canon.get(canon)
        if rec is None:
            wsup_no_weapon.append(canon)
            continue
        for row in rows:
            if scope is not None and not esc.in_scope(row["book"], scope):
                n_wsup_out_scope += 1
                continue
            have = {h.get("name") for h in rec["holders"]}
            for nm in row["names"]:
                if nm in have:
                    n_wsup_dup += 1        # holders 已有同名（神兵表在案），不重复加
                    continue
                rec["holders"].append({"name": nm, "n": 0,
                                       "sup": {"book": row["book"], "loc": row["loc"],
                                               "note": row["note"]}})
                have.add(nm)
                n_wsup_merged += 1

    levels = Counter(a.get("level") for a in artifacts["artifacts"])
    based_on_books = sort_books(set(src["conc_books"]) & set(scope["books"])) if scope is not None \
        else list(src["conc_books"])
    meta = {
        "generated": esc.today(),
        "rev": artifacts["meta"].get("rev", 16),
        "schema": "artifacts-v1",
        "based_on": {"books": based_on_books, "kb_date": artifacts["meta"].get("based_on", {}).get("kb_date", "2026-11-02")},
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
    if scope is not None:
        meta["scope"] = scope["profile"]
        meta["field_gaps"].append(
            f"scope 口径（{scope['profile']}）：chain/evidence/books 按 book ∈ scope 过滤，"
            "count 按 concordance scope 内书目计数重算；scope 内无出现的名物不入表；"
            "holders/borrowers/makers 的 n 神兵表无逐书归属，保持全量口径原值（不伪造逐书分解，"
            "待神兵表补逐书数据后重算）。")
        # D5 rev17（名物页重构设计 §六）：毁噪声自动证伪 + 编年 + 去重 + 方向化
        meta["rev"] = REV17
        meta["totals"]["chain_suspect"] = rev17_stats["suspect"]
        meta["totals"]["chain_dedup_merged"] = rev17_stats["dedup_merged"]
        meta["totals"]["chain_subject_low"] = rev17_stats["subject_low"]
        meta["totals"]["chain_dir"] = rev17_stats["dir"]
        # D7：end_state 编年重算计数
        meta["totals"]["end_state_recalc"] = end_stats["changed"]
        meta["totals"]["end_state_destroyed"] = end_stats["destroyed"]
        meta["field_gaps"].append(
            "rev17（名物页重构设计 §六，scope 口径）：chain 边新增 n（完全重复边合并 ×n 计数）/"
            "suspect（毁边后续证伪=毁后仍有持有或出场铁证，前端折叠进「疑似误伤」区，宁缺毋滥）/"
            "subject_low（毁边主语非高频持有人，降权注记不折叠）/"
            "dir（铸/借边方向化主语 persons∩makers|borrowers；夺/赠/传无 object 数据不方向化——"
            "后由 D17b 名物流转方向.tsv 通道补全，见下条 field_gaps）；"
            "chain 按宇宙编年（scope 书目序=universe lines 成员序）重排；"
            "全量口径（--scope all）不启用 rev17，行为与 rev16 一致（方案 R6）。")
        # D7（名物 end_state 按宇宙编年重算，scope 口径）：end_state 旧值=扫描序最后一个提及
        # （跨书只比回号），与主线编年矛盾（虎头钩式）；新值按编年最末提及/主线最末毁边。
        meta["field_gaps"].append(
            "end_state（D7，scope 口径）：按宇宙编年重算——主线（非 suspect 边）编年最末「毁」边的"
            "（书序, 回）=全件编年最末提及（books 回目集 ∪ 主线边回号）→「毁于：<边 persons>"
            "（书 · N 回）」；否则「末见持有：<holders 前 2>（<编年最末提及的书>·<最大回> 回）」，"
            "文案式样与旧生成一致、只改计算口径（旧值=扫描序 max(回,行) 的最后一个提及，跨书回号"
            "比较无编年意义）；无提及或无持有人 → null（不伪造）；全量口径（--scope all）不重算，"
            "end_state 保持神兵表旧值（方案 R6）。")
    # D10：holders 考订补录口径声明（§八.5「游龙剑 holders 补周青」；不伪造频次）
    if wsup_tsv_exists:
        wsup_draft_txt = f"（另有 draft {wsup_stats['draft']} 行未消费）" if wsup_stats["draft"] else ""
        no_weapon_txt = (f"；补录在案而 weapons 无记录不入表：{'、'.join(wsup_no_weapon)}。"
                         if wsup_no_weapon else "。")
        meta["field_gaps"].append(
            f"holders 补录：kb/校订/神兵表-补录.tsv（人工校定稿，§八.5 weapons 侧同步）"
            f"校定行 {wsup_stats['consumed']}{wsup_draft_txt}，注入 {n_wsup_merged} 人次"
            f"（holders 追加 n=0 + sup{{book,loc,note}}=「考订补录」注——频次 n 是神兵表扫描"
            f"口径，补录不伪造计数，前端与 holders 合并显示并注依据定位）；同名已有不重复加 "
            f"{n_wsup_dup} 处；scope 口径书外行不消费 {n_wsup_out_scope} 处"
            + no_weapon_txt)
    else:
        meta["field_gaps"].append(
            "holders 补录：kb/校订/神兵表-补录.tsv 不存在（无 holders 考订补录），"
            "holders 保持神兵表只读源原值。")
    # F6：chain_move/chain_drop 指令口径声明（边随器迁移，归属修正非呈现增强——全量口径同样应用）
    if chain_rows:
        meta["totals"]["chain_move"] = chain_stats["moved"]
        meta["totals"]["chain_drop"] = chain_stats["dropped"]
        no_edge_txt = (f"；无匹配 chain 边跳过（不伪造边）：{'、'.join(chain_stats['no_edge'])}"
                       if chain_stats["no_edge"] else "")
        no_weapon_txt = (f"；指令涉及而 weapons 无记录（源边不动防丢边）："
                         f"{'、'.join(sorted(set(chain_stats['no_weapon'])))}"
                         if chain_stats["no_weapon"] else "")
        meta["field_gaps"].append(
            f"chain 指令（F6，用户裁定）：kb/校订/神兵表-补录.tsv cmd 列（chain_move:<目标器>/"
            f"chain_drop）校定行 {len(chain_rows)} 行，执行 move {chain_stats['moved']} "
            f"drop {chain_stats['dropped']}——"
            "边本体（verb/persons/book/loc/conf）随器迁移/剔除，频次 count/books（concordance "
            "口径）不动；应用先于 rev17（编年/去重/毁证伪/end_state 看到迁移后 chain；目标器已有"
            "完全同边时追加为重复边由 rev17 dedupe 合并 ×n）与方向注入（方向 TSV 改挂目标器的行"
            "命中迁移后的边）；全量口径同样应用（归属修正非呈现增强，不受方案 R6 门槛）"
            + no_edge_txt + no_weapon_txt + "。")
    # D17b：名物流转方向口径声明（夺/赠/传/还边 who=[from,to] 人工校定方向层；铸/借 rev17 口径不动）
    if dir_tsv_exists:
        dir_draft_txt = f"（另有 draft {dir_stats['draft']} 行未消费）" if dir_stats["draft"] else ""
        no_edge_txt = (f"；无匹配 chain 边跳过（不伪造边）：{'、'.join(dir_inj['no_edge'])}"
                       if dir_inj["no_edge"] else "")
        no_weapon_txt = (f"；方向在案而 weapons 无记录不入表：{'、'.join(sorted(set(dir_inj['no_weapon'])))}"
                         if dir_inj["no_weapon"] else "")
        has_dir_txt = (f"；边已有 dir（铸/借 rev17 口径在先）不覆盖：{'、'.join(dir_inj['has_dir'])}"
                       if dir_inj["has_dir"] else "")
        meta["totals"]["chain_dir_person"] = dir_inj["injected"]
        meta["field_gaps"].append(
            f"chain 方向化补全（D17b，用户裁定方案 A）：kb/校订/名物流转方向.tsv（人工校定稿唯一真源，"
            f"草案 10 条全落 + 七剑下天山 14:25 双行人工裁定）校定行 {dir_stats['consumed']}"
            f"{dir_draft_txt}，注入 dir={{kind:行 verb, who:[from, to]}} {dir_inj['injected']} 处"
            f"（键 weapon+book+loc 命中 chain 边；kind 为校定方向层、可与边 verb 不同口径，"
            f"chain 边本体不动；who 恒两人=施者/受者，即「from → verb → to」）；scope 口径书外行"
            f"不消费 {dir_inj['out_scope']} 处{no_edge_txt}{no_weapon_txt}{has_dir_txt}；"
            "TSV note=原创注记留档不入站数据；全量口径（--scope all）不启用（与 rev17 同门，方案 R6）。")
    else:
        meta["field_gaps"].append(
            "chain 方向化补全：kb/校订/名物流转方向.tsv 不存在（夺/赠/传/还边保持 persons 并列"
            "无方向；rev17 铸/借方向化不受影响）。")
    payload = {"meta": meta, "weapons": records}

    notes = (f"记录数：旧站 {len(old_by)} → 新 {len(records)}（legacy={n_legacy} / new={n_new}）；"
             f"记录与旧站同集合（神兵表名物 183）；count 更新 {n_count_updated} 条、aliases 补充 {n_alias_added} 条。")
    if scope is not None:
        notes += (f" rev17：suspect 毁边 {rev17_stats['suspect']} 条（后续证伪折叠）、"
                  f"去重合并 {rev17_stats['dedup_merged']} 条、主语降权 {rev17_stats['subject_low']} 条、"
                  f"方向化（铸/借）{rev17_stats['dir']} 条（{rev17_stats['records']} 件名物）。"
                  f" D7：end_state 编年重算，改变 {end_stats['changed']} 件"
                  f"（其中「毁于」{end_stats['destroyed']} 件）。"
                  f" D17b：名物流转方向 TSV 校定行 {dir_stats['consumed']} 行注入方向 "
                  f"{dir_inj['injected']} 处（夺/赠/传/还边 who=[from, to]，"
                  f"无匹配边跳过 {len(dir_inj['no_edge'])} 处）。"
                  f" F6：chain 指令 {len(chain_rows)} 行（move {chain_stats['moved']}"
                  f"/drop {chain_stats['dropped']}）。")
    return payload, {"notes": notes, "legacy": n_legacy, "new": n_new}


# ---------------------------------------------------------------- arts.json
# W3-T4（武功页重构设计 §5.3，2026-11-10）：L1 原著评语 TSV（人工校定稿，唯一真源）——
# 全站首个 L1 短引文档位。闸门参数与 copyright_gate 参数化规则对齐（单条 ≤16 字 × 每门 ≤2 条）。
ART_COMMENT_TSV = KB / "校订" / "武功评语.tsv"
ART_COMMENT_HEADER = ["art", "quote", "loc", "status"]
COMMENT_STATUS = ("校定", "draft")          # 只消费 校定 行（评语判断是编辑工作，草案不入站）
MAX_COMMENT_LEN = 16                        # 单条引文 ≤16 字（len 全字计，含标点）
MAX_COMMENTS_PER_ART = 2                    # 每门武功 ≤2 条
# loc 列 =「书名·NNN:NNN」（·或空格分隔）；书名不得含空白（章回版源文件行号口径）
COMMENT_LOC_RE = re.compile(r"^(?P<book>[^\s·]+)\s*[·\s]\s*(?P<loc>\d{3}:\d{1,4})$")


class ArtCommentError(ValueError):
    """武功评语 TSV 非法（表头/引文长度/条数/状态词/定位符格式/重复行），消息中文，导出即报错。"""


def load_art_comments(path: Path | None = None) -> tuple[dict, dict]:
    """W3-T4：读 kb/校订/武功评语.tsv → ({art: [{quote, book, loc}]}, stats)。

    只有 status=校定 的行被消费（draft 行计入 stats["draft"] 供 meta 报告，不入站）；
    表头 / 空 art·quote·loc / quote>16 字 / 同门 >2 条（含 draft）/ status 词表外 /
    loc 非「书·NNN:NNN」式 / 同 art+quote+loc 重复行 → ArtCommentError（不静默改写
    人工校定稿）。文件不存在 → ({}, 统计零)（build_arts 以 field_gaps 声明缺表口径）。
    """
    p = Path(path) if path is not None else ART_COMMENT_TSV
    if not p.exists():
        return {}, {"rows": 0, "consumed": 0, "draft": 0}
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    if not rows or [c.strip() for c in rows[0][:len(ART_COMMENT_HEADER)]] != ART_COMMENT_HEADER:
        raise ArtCommentError(f"武功评语 TSV 表头必须为 {'/'.join(ART_COMMENT_HEADER)}：{p}")
    out: dict[str, list[dict]] = {}
    seen: set[tuple[str, str, str]] = set()
    stats = {"rows": 0, "consumed": 0, "draft": 0}
    for i, row in enumerate(rows[1:], 2):
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if len(cells) < 4:
            raise ArtCommentError(f"武功评语 TSV 第 {i} 行列不足（须 art/quote/loc/status）：{p}")
        art, quote, loc, status = cells[0], cells[1], cells[2], cells[3]
        stats["rows"] += 1
        if not art or not quote or not loc:
            raise ArtCommentError(f"武功评语 TSV 第 {i} 行 art/quote/loc 存在空值：{p}")
        if status not in COMMENT_STATUS:
            raise ArtCommentError(f"武功评语 TSV 第 {i} 行 status={status!r} 不在校定档"
                                  f"（{'/'.join(COMMENT_STATUS)}）：{p}")
        if len(quote) > MAX_COMMENT_LEN:
            raise ArtCommentError(f"武功评语 TSV 第 {i} 行 quote 超 {MAX_COMMENT_LEN} 字"
                                  f"（L1 红线）：{quote!r}（{len(quote)} 字）：{p}")
        m = COMMENT_LOC_RE.match(loc)
        if not m:
            raise ArtCommentError(f"武功评语 TSV 第 {i} 行 loc={loc!r} 非「书·NNN:NNN」式"
                                  f"（书名不得含空白）：{p}")
        key = (art, quote, m.group("loc"))
        if key in seen:
            raise ArtCommentError(f"武功评语 TSV 第 {i} 行：{art} 重复评语行（唯一真源）：{p}")
        seen.add(key)
        per_art = sum(len(v) for k, v in out.items() if k == art) + \
            (1 if status == "校定" else 0)
        if per_art >= MAX_COMMENTS_PER_ART and status == "校定":
            raise ArtCommentError(f"武功评语 TSV 第 {i} 行：{art} 校定评语将超过每门 "
                                  f"{MAX_COMMENTS_PER_ART} 条（L1 红线）：{p}")
        if status == "draft":
            stats["draft"] += 1
            continue
        out.setdefault(art, []).append({"quote": quote, "book": m.group("book"),
                                        "loc": m.group("loc")})
        stats["consumed"] += 1
    return out, stats


# ---------------------------------------------------------------- 人工考订补链（D10，武功页重构设计 §6.2 数据源三层第 3 层 / §八.5）
# note 解析（第 2 层）只收「学生已在同门关系表」的配对；周青案等系统性漏链（学生不在
# 关系表/note 未解出）由人工考订 TSV 补漏。首批 3 边=§八.5 原文裁定（用户「按设计首批
# 落地」2026-11-12）：凌未风—记名→周青、周青—记名→{冯广潮, 唐晓澜}（追风剑法五代链）。
LINEAGE_SUP_TSV = KB / "校订" / "武功传承补链.tsv"
LINEAGE_SUP_HEADER = ["art", "from", "to", "tier", "book", "loc", "note", "status"]
LINEAGE_SUP_STATUS = ("校定", "draft")      # 只消费 校定 行（人工校定稿唯一真源，draft 不入站）
LINEAGE_SUP_TIERS = ("正式", "记名", "挂名", "点拨")   # §6.1 边四档（前端 TIER_ORDER 同表）
LINEAGE_SUP_LOC_RE = re.compile(r"^\d{3}:\d{1,4}$")    # 章回版源文件行号口径（书名列单列）


class LineageSupError(ValueError):
    """武功传承补链 TSV 非法（表头/空值/档位/定位符/自环/重复行），消息中文，导出即报错。"""


def load_lineage_supplement(path: Path | None = None) -> tuple[list[dict], dict]:
    """D10：读 kb/校订/武功传承补链.tsv → ([{art,t,l,tier,book,loc,note}], stats)。

    只有 status=校定 的行被消费（draft 计入 stats["draft"] 供 meta 报告，不入站）；
    表头 / 空 art·from·to·loc / tier 不在四档 / loc 非「NNN:NNN」式 / from=to 自环 /
    同 art+from+to+book+loc 重复行 → LineageSupError（不静默改写人工校定稿）。
    文件不存在 → ([], 统计零)（build_arts 以 field_gaps 声明缺表口径）。
    note 列=依据摘要（人工核对用，不进 lineage 边——边契约 {t,l,book,loc,tier}）。
    """
    p = Path(path) if path is not None else LINEAGE_SUP_TSV
    if not p.exists():
        return [], {"rows": 0, "consumed": 0, "draft": 0}
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    if not rows or [c.strip() for c in rows[0][:len(LINEAGE_SUP_HEADER)]] != LINEAGE_SUP_HEADER:
        raise LineageSupError(f"武功传承补链 TSV 表头必须为 {'/'.join(LINEAGE_SUP_HEADER)}：{p}")
    out: list[dict] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    stats = {"rows": 0, "consumed": 0, "draft": 0}
    for i, row in enumerate(rows[1:], 2):
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if len(cells) < len(LINEAGE_SUP_HEADER):
            raise LineageSupError(f"武功传承补链 TSV 第 {i} 行列不足"
                                  f"（须 {'/'.join(LINEAGE_SUP_HEADER)}）：{p}")
        art, t, l, tier, book, loc, note, status = cells[:8]
        stats["rows"] += 1
        if not art or not t or not l or not book or not loc:
            raise LineageSupError(f"武功传承补链 TSV 第 {i} 行 art/from/to/book/loc 存在空值"
                                  f"（loc 必填——无定位符的补链不入站）：{p}")
        if status not in LINEAGE_SUP_STATUS:
            raise LineageSupError(f"武功传承补链 TSV 第 {i} 行 status={status!r} 不在校定档"
                                  f"（{'/'.join(LINEAGE_SUP_STATUS)}）：{p}")
        if tier not in LINEAGE_SUP_TIERS:
            raise LineageSupError(f"武功传承补链 TSV 第 {i} 行 tier={tier!r} 不在边四档"
                                  f"（{'/'.join(LINEAGE_SUP_TIERS)}，§6.1）：{p}")
        if not LINEAGE_SUP_LOC_RE.match(loc):
            raise LineageSupError(f"武功传承补链 TSV 第 {i} 行 loc={loc!r} 非「NNN:NNN」式"
                                  f"（章回版源文件行号口径）：{p}")
        if t == l:
            raise LineageSupError(f"武功传承补链 TSV 第 {i} 行自环（from=to={t}）：{p}")
        key = (art, t, l, book, loc)
        if key in seen:
            raise LineageSupError(f"武功传承补链 TSV 第 {i} 行：{art} {t}→{l}（{book} {loc}）"
                                  f"重复行（唯一真源）：{p}")
        seen.add(key)
        if status == "draft":
            stats["draft"] += 1
            continue
        out.append({"art": art, "t": t, "l": l, "tier": tier, "book": book,
                    "loc": loc, "note": note})
        stats["consumed"] += 1
    return out, stats


# ---------------------------------------------------------------- 游龙剑等 holders 考订补录（D10，§八.5：weapons 侧同步）
# holders 来自神兵表只读源（扫描频次 n）——不伪造：补录走校订 TSV 渠道，n=0 + sup 注记
#（「考订补录」），前端与 holders 合并显示并注依据定位（名物页重构设计 §相关人物）。
# F6（2026-11-12，用户裁定）：cmd 指令列扩展——空=holders 补录（原语义）/ chain_move:<目标器> /
# chain_drop。chain 指令把扫描共现误挂的 chain 边在器物间迁移/剔除（断玉剑 24:15 被夺之剑明文
# 实指游龙剑 → 边随器迁移），只动 chain 边本体（verb/persons/book/loc/conf 原样），频次
# count/books（concordance 口径）不动；应用时机=rev17 之前（编年/去重/毁证伪/end_state 看到
# 迁移后 chain），全量口径同样应用（归属修正非呈现增强，不受方案 R6 门槛）。
WEAPON_SUP_TSV = KB / "校订" / "神兵表-补录.tsv"
WEAPON_SUP_HEADER = ["weapon", "form", "aliases", "holders_add", "loc", "note", "status", "cmd"]
WEAPON_SUP_STATUS = ("校定", "draft")
# loc 列 =「书名·NNN:NNN」（·或空格分隔；与武功评语 loc 同口径，书名列不单设）
WEAPON_SUP_LOC_RE = re.compile(r"^(?P<book>[^\s·]+)\s*[·\s]\s*(?P<loc>\d{3}:\d{1,4})$")


class WeaponSupError(ValueError):
    """神兵表-补录 TSV 非法（表头/空值/定位符/重复行/cmd 指令词表），消息中文，导出即报错。"""


def load_weapon_supplement(path: Path | None = None) -> tuple[list[dict], dict]:
    """D10/F6：读 kb/校订/神兵表-补录.tsv → (rows, stats)。

    只有 status=校定 的行被消费（draft 计数不入站）。行形状按 cmd 列分流：
      cmd 空          → holders 补录行 {weapon, names, book, loc, note}（原 D10 契约不变：
                        weapon/holders_add/loc 必填，holders_add 支持顿号/逗号多人）；
      chain_move:<目标器> → {kind, weapon, target, book, loc, note}（weapon=源器，holders_add 必空、
                        note 必填——器物归属考订依据留档）；
      chain_drop      → {kind, weapon, book, loc, note}（同上必填约束）。
    loc 非「书名·NNN:NNN」式 / holders 行同 weapon+holders_add+loc 重复 / chain 行同
    weapon+cmd+loc 重复 / cmd 词表外或缺目标 → WeaponSupError（不静默改写人工校定稿）。
    文件不存在 → ([], 统计零)。
    """
    p = Path(path) if path is not None else WEAPON_SUP_TSV
    if not p.exists():
        return [], {"rows": 0, "consumed": 0, "draft": 0}
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    if not rows or [c.strip() for c in rows[0][:len(WEAPON_SUP_HEADER)]] != WEAPON_SUP_HEADER:
        raise WeaponSupError(f"神兵表-补录 TSV 表头必须为 {'/'.join(WEAPON_SUP_HEADER)}：{p}")
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    stats = {"rows": 0, "consumed": 0, "draft": 0}
    for i, row in enumerate(rows[1:], 2):
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if len(cells) < len(WEAPON_SUP_HEADER):
            raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行列不足"
                                 f"（须 {'/'.join(WEAPON_SUP_HEADER)}）：{p}")
        weapon, form, aliases, holders_add, loc, note, status, cmd = cells[:8]
        stats["rows"] += 1
        if not weapon or not loc:
            raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行 weapon/loc 存在空值"
                                 f"（loc 必填——无定位符的补录不入站）：{p}")
        if status not in WEAPON_SUP_STATUS:
            raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行 status={status!r} 不在校定档"
                                 f"（{'/'.join(WEAPON_SUP_STATUS)}）：{p}")
        m = WEAPON_SUP_LOC_RE.match(loc)
        if not m:
            raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行 loc={loc!r} 非「书名·NNN:NNN」式"
                                 f"（书名不得含空白）：{p}")
        if cmd.startswith("chain_move") or cmd == "chain_drop":        # F6：chain 指令行
            target = ""
            if cmd.startswith("chain_move"):
                parts = cmd.split(":")
                if len(parts) != 2 or not parts[1].strip():
                    raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行 cmd={cmd!r} 非法"
                                         f"（chain_move 须带唯一目标器名「chain_move:<目标器>」）：{p}")
                target = parts[1].strip()
            elif cmd != "chain_drop":
                raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行 cmd={cmd!r} 不在指令词表"
                                     f"（空=holders 补录 / chain_move:<目标器> / chain_drop）：{p}")
            if holders_add:
                raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行 chain 指令行 holders_add 应为空"
                                     f"（holders 补录与 chain 指令不混用）：{p}")
            if not note:
                raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行 chain 指令行 note 必填"
                                     f"（器物归属考订依据留档）：{p}")
            key = (weapon, cmd, loc)
            if key in seen:
                raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行：{weapon} {cmd}（{loc}）"
                                     f"重复行（唯一真源）：{p}")
            seen.add(key)
            if status == "draft":
                stats["draft"] += 1
                continue
            rec = {"kind": "chain_move" if target else "chain_drop", "weapon": weapon,
                   "book": m.group("book"), "loc": m.group("loc"), "note": note}
            if target:
                rec["target"] = target
            out.append(rec)
        elif cmd == "":                                                 # D10：holders 补录行
            if not holders_add:
                raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行 weapon/holders_add/loc 存在空值"
                                     f"（holders 补录行 holders_add 必填；chain 指令走 cmd 列）：{p}")
            names = [x for x in re.split(r"[、,，]", holders_add) if x]
            if not names:
                raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行 holders_add 解析不出人名：{p}")
            key = (weapon, holders_add, loc)
            if key in seen:
                raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行：{weapon} 补录 {holders_add}"
                                     f"（{loc}）重复行（唯一真源）：{p}")
            seen.add(key)
            if status == "draft":
                stats["draft"] += 1
                continue
            out.append({"weapon": weapon, "names": names,
                        "book": m.group("book"), "loc": m.group("loc"), "note": note})
        else:
            raise WeaponSupError(f"神兵表-补录 TSV 第 {i} 行 cmd={cmd!r} 不在指令词表"
                                 f"（空=holders 补录 / chain_move:<目标器> / chain_drop）：{p}")
        stats["consumed"] += 1
    return out, stats


def apply_chain_instructions(records: dict, rows: list[dict], alias: dict, canon_set: set) -> dict:
    """F6：chain_move/chain_drop 指令应用（就地）——键 weapon+book+loc（parse_loc_pair 归一比较）。

    move：源链删边 + 目标链追加（边本体 verb/persons/book/loc/conf 原样，不带 dir——dir 由
    名物流转方向通道在注入阶段命中迁移后的边）。源链同边可能有多个完全重复实例
    （神兵表扫描重复边，rev17 dedupe 前态）——迁移/剔除覆盖全部完全重复实例
    （同 book+loc+verb+persons），目标器已有同边时追加为重复边、由 scope 口径 rev17 dedupe
    合并为 ×n（全量口径维持重复边现状，与方案 R6 同门）。drop：源链删边（同覆盖全部实例）。
    无匹配边 / 源器或目标器无 weapons 记录 → 跳过并记账（不伪造边；目标无记录时源边不动，
    防丢边）。返回 stats 供 meta 记账（no_edge/no_weapon 点名进 field_gaps）。
    """
    stats = {"rows": len(rows), "moved": 0, "dropped": 0,
             "no_edge": [], "no_weapon": []}
    for row in rows:
        canon = resolve(row["weapon"], alias, canon_set) or row["weapon"]
        rec = records.get(canon)
        if rec is None:
            stats["no_weapon"].append(row["weapon"])
            continue
        key = parse_loc_pair(row["loc"])
        hits = [e for e in rec["chain"]
                if e.get("book") == row["book"] and parse_loc_pair(e.get("loc")) == key]
        if not hits:
            stats["no_edge"].append(f"{canon}·{row['book']}·{row['loc']}")
            continue
        edge = hits[0]
        same = [e for e in rec["chain"]                     # 全部完全重复实例（含 edge 自身）
                if e.get("book") == edge.get("book")
                and parse_loc_pair(e.get("loc")) == key
                and e.get("verb") == edge.get("verb")
                and list(e.get("persons") or []) == list(edge.get("persons") or [])]
        if row["kind"] == "chain_drop":
            for e in same:
                rec["chain"].remove(e)
            stats["dropped"] += 1
            continue
        tgt_canon = resolve(row["target"], alias, canon_set) or row["target"]
        tgt = records.get(tgt_canon)
        if tgt is None:
            stats["no_weapon"].append(row["target"])       # 源边不动（防丢边）
            continue
        for e in same:
            rec["chain"].remove(e)
        tgt["chain"].extend(dict(e) for e in same)
        stats["moved"] += 1
    return stats


# ---------------------------------------------------------------- 名物流转方向注入（D17b，用户裁定方案 A）
# D17a 草案（kb/校订/名物流转方向-草案.tsv，status=draft 摘样件留档）→ 正式校定表（本 TSV，唯一真源）：
# 草案 10 条 resolved 全落 + 七剑下天山 14:25 双行人工裁定补入（原文双句核实：短剑=断玉剑传杨云骢、
# 长剑=游龙剑传楚昭南，两剑 chain 均有 14:25 边可注）。rev17 attach_dir 只覆盖铸/借（主语=persons∩
# makers|borrowers），夺/赠/传/还无 object 数据不加——本 TSV 即该批次的人工校定方向层：dir.kind 来自
# 行内 verb（可与 chain 边 verb 不同口径，chain 边本体不动），who=[from, to] 恒两人。
DIRECTION_TSV = KB / "校订" / "名物流转方向.tsv"
DIRECTION_HEADER = ["weapon", "verb", "from", "to", "book", "loc", "note", "status"]
DIRECTION_STATUS = ("校定", "draft")            # 只消费 校定 行（人工校定稿唯一真源，draft 不入站）
DIRECTION_VERBS = ("夺", "赠", "传", "还")       # 方向化动词词表（铸/借维持 rev17 attach_dir 口径，不入表）
DIRECTION_LOC_RE = re.compile(r"^\d{1,3}:\d{1,4}$")   # 「章:行」式（零填充不强制，与 chain.loc 同口径）


class DirectionError(ValueError):
    """名物流转方向 TSV 非法（表头/必填/动词词表/loc 格式/自环/同键重复），消息中文，导出即报错。"""


def load_direction(path: Path | None = None) -> tuple[list[dict], dict]:
    """D17b：读 kb/校订/名物流转方向.tsv → ([{weapon,verb,from,to,book,loc,note}], stats)。

    # 注释行与空行跳过（行号报错按源文件行计，D16 毒解配对同款纪律）；只有 status=校定 的
    行被消费（draft 计入 stats["draft"] 供 meta 报告，不入站）；表头 / 空 weapon·verb·from·
    to·book·loc / verb 不在夺赠传还词表 / loc 非「章:行」式 / from=to 自环 / 同
    weapon+book+loc 重复行（一键一边一 dir）→ DirectionError（不静默改写人工校定稿）。
    文件不存在 → ([], 统计零)。note=原创注记（L0，考订依据留档），不进 dir 边。
    """
    p = Path(path) if path is not None else DIRECTION_TSV
    if not p.exists():
        return [], {"rows": 0, "consumed": 0, "draft": 0}
    with open(p, encoding="utf-8", newline="") as f:
        raw = list(csv.reader(f, delimiter="\t"))
    data = [(fi, r) for fi, r in enumerate(raw, 1)
            if r and r[0].strip() and not r[0].startswith("#")]
    if not data or [c.strip() for c in data[0][1][:len(DIRECTION_HEADER)]] != DIRECTION_HEADER:
        raise DirectionError(f"名物流转方向 TSV 表头必须为 {'/'.join(DIRECTION_HEADER)}：{p}")
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    stats = {"rows": 0, "consumed": 0, "draft": 0}
    for fi, row in data[1:]:
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if len(cells) < len(DIRECTION_HEADER):
            raise DirectionError(f"名物流转方向 TSV 第 {fi} 行列不足"
                                 f"（须 {'/'.join(DIRECTION_HEADER)}）：{p}")
        weapon, verb, frm, to, book, loc, note, status = cells[:8]
        stats["rows"] += 1
        if not weapon or not verb or not frm or not to or not book or not loc:
            raise DirectionError(f"名物流转方向 TSV 第 {fi} 行 weapon/verb/from/to/book/loc 存在空值"
                                 f"（六列必填——无键无方向）：{p}")
        if status not in DIRECTION_STATUS:
            raise DirectionError(f"名物流转方向 TSV 第 {fi} 行 status={status!r} 不在校定档"
                                 f"（{'/'.join(DIRECTION_STATUS)}）：{p}")
        if verb not in DIRECTION_VERBS:
            raise DirectionError(f"名物流转方向 TSV 第 {fi} 行 verb={verb!r} 不在方向动词词表"
                                 f"（{'/'.join(DIRECTION_VERBS)}；铸/借维持 rev17 口径不入本表）：{p}")
        if not DIRECTION_LOC_RE.match(loc):
            raise DirectionError(f"名物流转方向 TSV 第 {fi} 行 loc={loc!r} 非「章:行」式"
                                 f"（如 5:7 / 022:47，章回版源文件行号口径）：{p}")
        if frm == to:
            raise DirectionError(f"名物流转方向 TSV 第 {fi} 行自环（from=to={frm}）：{p}")
        key = (weapon, book, loc)
        if key in seen:
            raise DirectionError(f"名物流转方向 TSV 第 {fi} 行：{weapon}（{book} {loc}）重复键行"
                                 f"（一键一边一 dir，唯一真源）：{p}")
        seen.add(key)
        if status == "draft":
            stats["draft"] += 1
            continue
        out.append({"weapon": weapon, "verb": verb, "from": frm, "to": to,
                    "book": book, "loc": loc, "note": note})
        stats["consumed"] += 1
    return out, stats


def inject_direction(records: dict, rows: list[dict], alias: dict, canon_set: set,
                     scope) -> dict:
    """D17b：校定行注入 chain 边 dir（就地）——键 weapon+book+loc（parse_loc_pair 归一比较）。

    命中且边无 dir → e["dir"]={"kind": 行 verb, "who": [from, to]}；无匹配边（含 14:25 若
    chain 无边情形）/ weapon 无记录 / scope 外书行 / 边已有 dir（铸/借 rev17 在先）→ 跳过并
    计数（不伪造边、不覆盖既有方向）。返回 stats（no_edge/no_weapon 列表供 field_gaps 点名）。
    """
    stats = {"rows": len(rows), "injected": 0, "out_scope": 0,
             "no_edge": [], "no_weapon": [], "has_dir": []}
    by_canon: dict[str, list[dict]] = {}
    for row in rows:
        canon = resolve(row["weapon"], alias, canon_set) or row["weapon"]
        by_canon.setdefault(canon, []).append(row)
    for canon, rws in sorted(by_canon.items()):
        rec = records.get(canon)
        if rec is None:
            stats["no_weapon"].extend(sorted({r["weapon"] for r in rws}))
            continue
        for row in rws:
            if scope is not None and not esc.in_scope(row["book"], scope):
                stats["out_scope"] += 1
                continue
            key = parse_loc_pair(row["loc"])
            hits = [e for e in rec["chain"]
                    if e.get("book") == row["book"] and parse_loc_pair(e.get("loc")) == key]
            target = next((e for e in hits if "dir" not in e), None)
            if target is None:
                (stats["has_dir"] if hits else stats["no_edge"]).append(
                    f"{canon}·{row['book']}·{row['loc']}")
                continue
            target["dir"] = {"kind": row["verb"], "who": [row["from"], row["to"]]}
            stats["injected"] += 1
    return stats


# ---------------------------------------------------------------- 传授 note 配对解析（W3-T4 §6.2 数据源 2 层）
# 学生名清洗与黑名单：学生须像 2–4 字人名——武功/招式词、称谓、代词、句式字一律拒绝（不伪造配对）。
_NAME_STRIP_LEAD = re.compile(r"^(?:传给|传授|传|授|教|指点|胞侄|师侄|亲侄|侄|弟子|之子|人)")
_NAME_STRIP_TRAIL = re.compile(r"[一二三四五六七八九十百零两几余]+[载年月日天春秋]?$")
_NAME_BAD_CHARS = re.compile(
    r"[法式拳掌刀剑功招腿指诀术她他你我师徒门派宗处来去从学练使用施展得地出了八的]"
)
# 教学动词 + 学生名锚点（锚点=标点/引号/从属词/段尾，防止吃进后续评注）
_ANCHOR = r"(?=[（，,、；;）\s」』“”\"]|$|的|本门|武艺|剑法|刀法|拳法|掌法|神功|读|学|练|武)"
_LINEAGE_VERB = re.compile(
    r"(?:传授|传给|传|授|教|指点)[」』”\"]?(?:给)?(?P<name>[\u4e00-\u9fa5]{2,6}?)" + _ANCHOR)
_LINEAGE_PATTERNS = [
    # 编辑括注（传X）——引文之后编者补记的学生
    re.compile(r"（传(?P<name>[\u4e00-\u9fa5]{2,6}?)）"),
    # 斜杠多名单：传A/B（loc1、loc2）——按序配对
    re.compile(r"传(?P<names>[\u4e00-\u9fa5]{2,4}(?:/[\u4e00-\u9fa5]{2,4})+)（"
               r"(?P<det>[^（）]*\d{3}:\d{1,4}[^（）]*)）"),
    # 名（…loc…）括注——学生名紧邻含定位符的括注
    re.compile(r"(?P<name>[\u4e00-\u9fa5]{2,6})（(?P<det>[^（）]*\d{3}:\d{1,4}[^（）]*)）"),
    # 具名句式（按真实注记词面逐一列证；引文内表述以「明文X“…”」编辑前缀锚定学生）
    re.compile(r"(?:衣钵)?传人(?P<name>[\u4e00-\u9fa5]{2,4})"),                      # 衣钵传人X
    re.compile(r"遗命(?P<name>[\u4e00-\u9fa5]{2,4})"),                              # 遗命X（拜师）
    re.compile(r"(?P<name>[\u4e00-\u9fa5]{2,4})送他为徒"),                          # X送他为徒
    re.compile(r"(?P<name>[\u4e00-\u9fa5]{2,4})从[\u4e00-\u9fa5]{2,10}处学来"),     # X从Y处学来
    re.compile(r"明文(?P<name>[\u4e00-\u9fa5]{2,4})[”\"]?跟?他?学了"),              # 明文X“（跟他）学了”
    re.compile(r"明文(?P<name>[\u4e00-\u9fa5]{2,4})[”\"]?(?:自幼)?跟随"),           # 明文X“跟随”
    re.compile(r"明文(?P<name>[\u4e00-\u9fa5]{2,4})[”\"]?依着.{0,12}所教"),         # 明文X“依着…所教”
    re.compile(r"就是(?P<name>[\u4e00-\u9fa5]{2,4})后来的师父"),                    # 就是X后来的师父
    re.compile(r"明文(?P<name>[\u4e00-\u9fa5]{2,4})为[\u4e00-\u9fa5]{2,8}关门弟子"),  # 明文X为Y关门弟子
    re.compile(r"(?P<name>[\u4e00-\u9fa5]{2,4})系其嫡传"),                          # X系其嫡传
    re.compile(r"唯(?P<name>[\u4e00-\u9fa5]{2,4})得传"),                            # 唯X得传
    re.compile(r"留(?P<name>[\u4e00-\u9fa5]{2,4})一室"),                            # 留X一室（传授）
    re.compile(r"明文(?P<name>[\u4e00-\u9fa5]{2,4})[”\"]?得了.{0,12}真传"),         # 明文X“得了…真传”
    # 无名括注（」（雍正）——括注前接引号闭符时括注本身即学生）
    re.compile(r"(?<=[」』”\"]（)(?P<name>[\u4e00-\u9fa5]{2,4})(?=）)"),
]
_LOC_RE = re.compile(r"\d{3}:\d{1,4}")
_LINEAGE_TIER_WORDS = (("记名", "记名"), ("挂名", "挂名"), ("点拨", "点拨"),
                       ("指点", "点拨"), ("拆招", "点拨"))


def _clean_student(name: str) -> str | None:
    """学生名清洗：剥教学动词/称谓前缀（可叠两轮，如 传侄金千岩）与年数后缀 →
    过黑名单；须 2–4 字人名，否则 None。"""
    for _ in range(2):
        name = _NAME_STRIP_LEAD.sub("", name)
    name = _NAME_STRIP_TRAIL.sub("", name)
    if not 2 <= len(name) <= 4 or _NAME_BAD_CHARS.search(name):
        return None
    return name


def _note_segments(note: str) -> list[str]:
    """按 ；/; 分段（括注内深度 >0 不切，保住「X（…；…）」式括注完整性）。"""
    segs, depth, buf = [], 0, []
    for ch in note:
        if ch == "（":
            depth += 1
        elif ch == "）":
            depth = max(0, depth - 1)
        if ch in "；;" and depth == 0:
            segs.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    segs.append("".join(buf))
    return [s for s in (x.strip() for x in segs) if s]


def parse_lineage_note(note: str | None) -> list[dict]:
    """W3-T4：传授行 note → s→l 配对候选（纯函数；方向由调用方补 s/book）。

    返回 [{"l": 学生名, "loc": "NNN:NNN"|None, "tier": "正式"|"记名"|"挂名"|"点拨"}]，
    按 note 词序；同段内定位符就近锚定（已消费不重复用）；解析不出返回 []（不伪造配对）。
    同名学生多定位符保留（如 挂名@009:31 + 正式@046:67）；无定位符副本在有定位符版本
    出现后丢弃（词序在前的动词匹配与括注匹配合并）。
    """
    if not note:
        return []
    out: list[dict] = []
    for seg in _note_segments(note):
        locs = [(m.start(), m.group()) for m in _LOC_RE.finditer(seg)]
        used: set[str] = set()

        def take_loc(pos: int, det_loc: str | None = None) -> str | None:
            if det_loc:
                return det_loc
            cand = [(p, l) for p, l in locs if p < pos and l not in used]
            if cand:
                _p, l = cand[-1]
                used.add(l)
                return l
            return None

        # 段档位：note 词面（记名/挂名/点拨·指点·拆招），无词面=正式
        tier = "正式"
        for word, t in _LINEAGE_TIER_WORDS:
            if word in seg:
                tier = t
                break

        found: list[tuple[int, bool, int, str, str | None]] = []   # (pos, has_det, prio, name, det_loc)
        all_pats = [(pat, prio) for prio, pat in enumerate(_LINEAGE_PATTERNS)]
        all_pats.append((_LINEAGE_VERB, len(_LINEAGE_PATTERNS)))
        for pat, prio in all_pats:
            for m in pat.finditer(seg):
                if "names" in (pat.groupindex or {}):
                    raw_names = m.group("names").split("/")
                    det = m.group("det") or ""
                    seg_locs = _LOC_RE.findall(det)
                    cursor = m.start(1)
                    for k, raw in enumerate(raw_names):
                        nm = _clean_student(raw)
                        pos = seg.find(raw, cursor)
                        cursor = pos + len(raw)
                        if not nm:
                            continue
                        found.append((pos, True, prio, nm,
                                      seg_locs[k] if k < len(seg_locs) else None))
                    continue
                nm = _clean_student(m.group("name"))
                if not nm:
                    continue
                det = m.groupdict().get("det")
                det_loc = None
                if "det" in (pat.groupindex or {}) and det:
                    seg_locs = _LOC_RE.findall(det)
                    if seg_locs:
                        det_loc = seg_locs[0]
                found.append((m.start("name"), det_loc is not None, prio, nm, det_loc))
        # 同位置多策略命中：括注锚定（有定位符）优先，再按策略优先级，其余按词序
        seg_out: list[dict] = []
        seen_at: set[int] = set()
        for pos, _has_det, _prio, nm, det_loc in sorted(found, key=lambda x: (x[0], not x[1], x[2])):
            if pos in seen_at:
                continue
            seen_at.add(pos)
            loc = take_loc(pos, det_loc)
            # 段内同名学生去重（斜杠名单/括注/动词多策略重叠=同一配对，取首个——已按
            # 括注锚定优先排序）；跨段同名多定位符保留（挂名@009:31 + 正式@046:67 式）
            if any(e["l"] == nm for e in seg_out):
                continue
            seg_out.append({"l": nm, "loc": loc, "tier": tier})
        # 跨段合并：同名同 loc 丢弃；同名有定位符在先、无定位符在后丢弃
        for e in seg_out:
            dup = False
            for o in out:
                if o["l"] == e["l"] and (o["loc"] == e["loc"] or (o["loc"] and e["loc"] is None)):
                    dup = True
                    break
            if not dup:
                out.append(e)
    return out


def scope_arts_record(rec: dict, hit: dict | None, scope) -> dict:
    """单条 arts 记录的 scope 裁剪（W0-T3a / 方案 §1.2）。

    relations 按 book 键过滤（组内 locs 无书名前缀，随书键天然归属）；books 过滤；
    ev_total 重算：有 relations（考订关系证据）按过滤后证据 ev 合计；无 relations 的
    新增条目按 concordance scope 内书目计数重算；两者皆无保持原值（field_gaps 声明）。
    """
    rec["relations"] = {b: v for b, v in rec["relations"].items() if esc.in_scope(b, scope)}
    rec["books"] = [b for b in rec["books"] if esc.in_scope(b, scope)]
    if rec["relations"]:
        rec["ev_total"] = sum(int(r.get("ev") or 0)
                              for v in rec["relations"].values()
                              for r in (v.get("relations") or []))
    elif hit:
        scoped = sum(int((hit.get("books") or {}).get(b) or 0) for b in scope.get("books", []))
        if scoped:
            rec["ev_total"] = scoped
    rec["cross_book"] = len(rec["books"]) > 1
    return rec


def build_arts(src: dict, scope=None, art_comments: dict | None = None,
               lineage_sup: list[dict] | None = None) -> tuple[dict, dict]:
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

    # W0-T3a：scope 裁剪（relations book 键/books/ev_total 重算）+ scope 内无出现者不入表
    if scope is not None:
        for canon, rec in records.items():
            scope_arts_record(rec, conc.get(("☆", canon)), scope)
        records = {c: r for c, r in records.items() if r["books"]}

    # 6) W3-T4（武功页重构设计 §5.3/§六）：L1 评语 + 传授 note 配对真边（weapons/sects 零影响）
    if art_comments is None:
        art_comments, cstats = load_art_comments()
        comment_tsv_exists = ART_COMMENT_TSV.exists()
    else:
        cstats = {"rows": sum(len(v) for v in (art_comments or {}).values()),
                  "consumed": sum(len(v) for v in (art_comments or {}).values()), "draft": 0}
        comment_tsv_exists = bool(art_comments)
    art_comments = art_comments or {}
    # D10：人工考订补链（§6.2 数据源 3 层）——与 comments 同纪律（TSV 为人工校定稿唯一真源）
    if lineage_sup is None:
        lineage_sup, sup_stats = load_lineage_supplement()
        sup_tsv_exists = LINEAGE_SUP_TSV.exists()
    else:
        lineage_sup = lineage_sup or []
        sup_stats = {"rows": len(lineage_sup), "consumed": len(lineage_sup), "draft": 0}
        sup_tsv_exists = bool(lineage_sup)
    n_comments = 0
    n_comment_arts = 0
    comment_no_art: list[str] = []
    n_lineage = 0
    lineage_tiers: Counter = Counter()
    lineage_skip_notes: list[str] = []
    for canon, rec in records.items():
        cs = [c for c in (art_comments.get(canon) or [])
              if scope is None or esc.in_scope(c["book"], scope)]
        if cs:
            rec["comments"] = cs
            n_comments += len(cs)
            n_comment_arts += 1
        # 传授真边：学生须在同门武功关系表出现（解析不出/未出现/自环 → 不入表，不伪造配对）
        attested = {r["s"] for v in rec["relations"].values()
                    for r in (v.get("relations") or []) if r.get("st") == "@"}
        edges: list[dict] = []
        seen_pair: set[tuple[str, str, str]] = set()   # (t,l,book)——跨书同对边保留（§6.1 跨书角标）
        for book, bv in rec["relations"].items():
            for r in (bv.get("relations") or []):
                if r.get("pred") != "传授" or r.get("st") != "@":
                    continue
                cands = parse_lineage_note(r.get("note"))
                if not cands and (r.get("note") or "").strip():
                    lineage_skip_notes.append(f"{canon}·{r['s']}（{book}）：note 未解出学生")
                    continue
                for cand in cands:
                    l = cand["l"]
                    if l == r["s"]:
                        lineage_skip_notes.append(f"{canon}·{r['s']}（{book}）：自环，不入")
                        continue
                    if l not in attested:
                        lineage_skip_notes.append(
                            f"{canon}·{r['s']}→{l}（{book}）：学生不在同门关系表，不入")
                        continue
                    if (r["s"], l, book) in seen_pair:
                        continue
                    seen_pair.add((r["s"], l, book))
                    edges.append({"t": r["s"], "l": l, "book": book,
                                  "loc": cand["loc"], "tier": cand["tier"]})
                    lineage_tiers[cand["tier"]] += 1
        if edges:
            rec["lineage"] = edges
            n_lineage += len(edges)
    # D10：人工考订补链合并（§6.2 数据源 3 层）——tier 由 TSV 行给出；人工校定免「同门关系表
    # attestation」闸（周青/冯广潮 系统性漏链正是因不在关系表）；与 note 解析边去重：
    # 同 (t,l,book,loc) → 跳过并记 field_gaps（不产生重复边）；同 (t,l) 新定位符 → 并入为
    # 同对多定位符（与 parse_lineage_note 跨段多定位符同口径，如 挂名@009:31+正式@046:67，
    # 前端按 (t,l) 归组、线型取最强档）；scope 口径书外行不消费（与 comments 同裁剪）。
    sup_by_art: dict[str, list[dict]] = {}
    for row in lineage_sup:
        canon = resolve(row["art"], alias, canon_set) or row["art"]
        sup_by_art.setdefault(canon, []).append(row)
    n_sup_injected = n_sup_dedup = n_sup_multiloc = n_sup_out_scope = 0
    sup_no_art: list[str] = []
    for canon, rows in sorted(sup_by_art.items()):
        rec = records.get(canon)
        if rec is None:
            sup_no_art.append(canon)
            continue
        for row in rows:
            if scope is not None and not esc.in_scope(row["book"], scope):
                n_sup_out_scope += 1
                continue
            existing = rec.get("lineage") or []
            if any(e["t"] == row["t"] and e["l"] == row["l"] and e["book"] == row["book"]
                   and (e.get("loc") or "") == row["loc"] for e in existing):
                n_sup_dedup += 1          # 同对同定位符：note 解析已在案，跳过（不重复入表）
                continue
            if any(e["t"] == row["t"] and e["l"] == row["l"] for e in existing):
                n_sup_multiloc += 1       # 同对新定位符：多定位符同边（档位在边清单逐一呈现）
            rec.setdefault("lineage", []).append({"t": row["t"], "l": row["l"],
                                                  "book": row["book"], "loc": row["loc"],
                                                  "tier": row["tier"]})
            lineage_tiers[row["tier"]] += 1
            n_sup_injected += 1
    for art in art_comments:
        if art not in records:
            comment_no_art.append(art)
    tier_txt = "、".join(f"{k} {v}" for k, v in sorted(lineage_tiers.items())) or "—"

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
    meta_books = sort_books(set(src["conc_books"]) & set(scope["books"])) if scope is not None \
        else list(src["conc_books"])
    meta = {
        "generated": esc.today(),
        "schema": "arts-v1",
        "books": meta_books,
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
    # W3-T4：L1 评语卡 + 传承树真边口径声明（武功页重构设计 §5.3/§六）
    if comment_tsv_exists:
        draft_txt = f"（另有 draft {cstats['draft']} 行未消费）" if cstats["draft"] else ""
        no_art_txt = (f"武功评语在案而无 arts 记录不入表：{'、'.join(comment_no_art)}。"
                      if comment_no_art else "")
        meta["field_gaps"].append(
            f"comments：kb/校订/武功评语.tsv（L1 短引文，人工校定稿唯一真源）校定行 "
            f"{cstats['consumed']}{draft_txt}，注入 {n_comment_arts} 门 {n_comments} 条"
            f"（单条 ≤{MAX_COMMENT_LEN} 字 × 每门 ≤{MAX_COMMENTS_PER_ART} 条；"
            "scope 口径下评语书 ∉ scope 不消费）；comments 为评语卡数据不计入 ev_total。" + no_art_txt)
    else:
        meta["field_gaps"].append(
            "comments：kb/校订/武功评语.tsv 不存在（W3-T4 L1 评语未校定），全部武功无 comments "
            f"字段（单条 ≤{MAX_COMMENT_LEN} 字 × 每门 ≤{MAX_COMMENTS_PER_ART} 条红线不变）。")
    lineage_skip_txt = ("：" + "；".join(lineage_skip_notes[:8])
                        + ("…" if len(lineage_skip_notes) > 8 else "") if lineage_skip_notes else "")
    meta["field_gaps"].append(
        f"lineage：传授行 note 解析（parse_lineage_note，纯函数）s→l 配对真边 {n_lineage} 条"
        f"（档位：{tier_txt}）；数据源调查：配对只活在 note 明文（relations 无 object 字段，"
        "graph 传授边无武功标签不可用），学生须在同门武功关系表出现，解析不出/未出现/自环"
        f"不入表（不伪造配对）；未解出/未入配对 {len(lineage_skip_notes)} 处挂人工考订补链"
        "（武功页重构设计 §八.5）" + lineage_skip_txt)
    # D10：人工考订补链口径声明（§6.2 数据源 3 层；与 comments TSV 同纪律）
    if sup_tsv_exists:
        sup_draft_txt = f"（另有 draft {sup_stats['draft']} 行未消费）" if sup_stats["draft"] else ""
        no_art_txt = (f"；补链在案而无武功记录不入表：{'、'.join(sup_no_art)}。"
                      if sup_no_art else "。")
        meta["field_gaps"].append(
            f"lineage 补链：kb/校订/武功传承补链.tsv（人工校定稿唯一真源，§八.5 周青案首批）"
            f"校定行 {sup_stats['consumed']}{sup_draft_txt}，注入 {n_sup_injected} 条"
            f"（tier 由行内 tier 列给出；人工考订免「同门关系表 attestation」闸，loc 逐条"
            f"按章回版源文件行号核实）；同对同定位符与 note 解析边重复跳过 {n_sup_dedup} 处、"
            f"同对新定位符并入多定位符 {n_sup_multiloc} 处（前端按 (t,l) 归组、线型取最强档）；"
            f"scope 口径书外行不消费 {n_sup_out_scope} 处" + no_art_txt)
    else:
        meta["field_gaps"].append(
            "lineage 补链：kb/校订/武功传承补链.tsv 不存在（无人工考订补链），"
            "传承树仅 note 解析真边（§6.2 数据源 3 层未启用）。")
    if scope is not None:
        meta["scope"] = scope["profile"]
        meta["field_gaps"].append(
            f"scope 口径（{scope['profile']}）：relations 按 book ∈ scope 过滤（组内 locs 随书键"
            "归属）、books 裁到 scope；ev_total 重算=过滤后 relations 证据 ev 合计（无 relations 者"
            "按 concordance scope 内计数）；scope 内无出现的武功不入表；children 无逐书归属保持原值。")
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

# W2-B6（门派志页重构设计 §一决策 1/§五，2026-11-10）：势力类型/驻地考订 TSV（人工校定稿，唯一真源）
SECT_CALIB_TSV = KB / "校订" / "门派驻地考订.tsv"
CALIB_HEADER = ["sect", "type", "seat_name", "status", "anchor", "basis"]
SECT_TYPES = ("名门正派", "世家", "绿林帮会", "朝廷势力")   # 决策 1 类型词表（朝廷势力=另册）
SEAT_STATUS = ("实锚", "推理", "待考")                       # 驻地三级判定（决策 3 / 地图页设计 §4.9）


class SectCalibError(ValueError):
    """门派驻地考订 TSV 非法（表头/类型词表/驻地档/重复行），消息中文，导出即报错。"""


def load_sect_calib(path: Path | None = None) -> dict:
    """W2-B6：读 kb/校订/门派驻地考订.tsv → {派名: {"type":…, "seat":{name,status,basis}}}。

    全部数据行视为人工校定行（该 TSV 即考订产物，无 draft 状态列）；文件不存在 → {}
    （build_sects 以 field_gaps 声明缺表口径）。anchor 列是地图推理锚（sect_seats.json 消费），
    不入 seat——站点 sects.json 的 seat 只带 name/status/basis（任务口径）。
    表头/类型词表/驻地档/空值/重复行非法 → SectCalibError（不静默改写人工校定稿）。
    """
    p = Path(path) if path is not None else SECT_CALIB_TSV
    if not p.exists():
        return {}
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    if not rows or [c.strip() for c in rows[0][:len(CALIB_HEADER)]] != CALIB_HEADER:
        raise SectCalibError(f"门派驻地考订 TSV 表头必须为 {'/'.join(CALIB_HEADER)}：{p}")
    out: dict = {}
    for i, row in enumerate(rows[1:], 2):
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if len(cells) < 4:
            raise SectCalibError(f"门派驻地考订 TSV 第 {i} 行列不足（须 sect/type/seat_name/status[/anchor/basis]）：{p}")
        sect, typ, seat_name, status = cells[0], cells[1], cells[2], cells[3]
        basis = cells[5] if len(cells) > 5 else ""
        if not sect or not typ:
            raise SectCalibError(f"门派驻地考订 TSV 第 {i} 行 sect/type 存在空值：{p}")
        if typ not in SECT_TYPES:
            raise SectCalibError(f"门派驻地考订 TSV 第 {i} 行 type={typ!r} 不在类型词表"
                                 f"（{'/'.join(SECT_TYPES)}）：{p}")
        if status not in SEAT_STATUS:
            raise SectCalibError(f"门派驻地考订 TSV 第 {i} 行 status={status!r} 不在驻地判定档"
                                 f"（{'/'.join(SEAT_STATUS)}）：{p}")
        if sect in out:
            raise SectCalibError(f"门派驻地考订 TSV 第 {i} 行：{sect} 重复校定行（唯一真源，只允许一行）：{p}")
        out[sect] = {"type": typ,
                     "seat": {"name": seat_name or None, "status": status, "basis": basis}}
    return out


def inject_sect_calib(records: dict, source_of: dict, calib: dict, conc: dict,
                      alias: dict, canon_set: set, blank) -> dict:
    """W2-B6：考订行注入 records（就地）——type/seat 并入 + 考订在案势力入册。

    - 已有记录：只加 type/seat 两键（books/ev_total/tenures 等考订值不动）；
    - 无记录（如大内：组织后缀不在白名单被候选过滤）：由 concordance ◆/& 出现证据入册
      （blank 记录 + source="new"，books/ev_total 由调用方既有的 conc 补全步统一回填）；
    - 库内无 ◆/& 出现记录的行不入表（不造空壳，返回值 no_corpus 供 meta.notes 点名）。
    """
    stats = {"n_injected": 0, "n_created": 0, "created": [], "no_corpus": []}
    for sect_name, row in calib.items():
        canon = resolve(sect_name, alias, canon_set) or sect_name
        if canon not in records:
            hit = conc.get(("◆", canon)) or conc.get(("&", canon))
            if not hit or not hit.get("books"):
                stats["no_corpus"].append(sect_name)
                continue
            records[canon] = json.loads(json.dumps(blank(canon), ensure_ascii=False))
            source_of[canon] = "new"
            stats["n_created"] += 1
            stats["created"].append(canon)
        records[canon]["type"] = row["type"]
        records[canon]["seat"] = dict(row["seat"])
        stats["n_injected"] += 1
    return stats


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


def scope_sect_record(rec: dict, scope) -> dict:
    """单条 sects 记录的 scope 裁剪（W0-T3a / 方案 §1.2：books ∩ scope）。

    books 过滤、cross_book 重算、arts_by_pred 按 book ∈ scope 过滤（空组剔除）；
    members/tenures/ev_total 无逐书归属或属人工考订值，保持原值（meta.field_gaps 声明，
    成员/频次裁剪待 W0 后续批次）。
    """
    rec["books"] = [b for b in rec.get("books") or [] if esc.in_scope(b, scope)]
    kept_pred = {}
    for pred, items in (rec.get("arts_by_pred") or {}).items():
        kept = [it for it in items if esc.in_scope(it.get("book"), scope)]
        if kept:
            kept_pred[pred] = kept
    rec["arts_by_pred"] = kept_pred
    rec["cross_book"] = len(rec["books"]) > 1
    return rec


def build_sects(src: dict, scope=None, calib=None) -> tuple[dict, dict]:
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

    # 3.5) W2-B6：门派驻地考订 TSV（人工校定）——type/seat 注入 + 考订在案势力入册
    if calib is None:
        calib = load_sect_calib()
        tsv_exists = SECT_CALIB_TSV.exists()
    else:
        tsv_exists = True   # 调用方注入口径（测试/上游已读表），视同 TSV 在案
    calib = calib or {}
    calib_stats = inject_sect_calib(records, source_of, calib, conc, alias, canon_set, blank)

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

    # W0-T3a：scope 裁剪（books ∩ scope、arts_by_pred 按书过滤）+ scope 内无出现者不入表
    if scope is not None:
        for rec in records.values():
            scope_sect_record(rec, scope)
        records = {c: r for c, r in records.items() if r["books"]}

    items = sorted(records.values(), key=lambda r: (-(r.get("ev_total") or 0), r["canonical"]))
    items = [{"canonical": r["canonical"], "books": r["books"], "cross_book": r["cross_book"],
              "ev_total": r["ev_total"], "arts_by_pred": r["arts_by_pred"],
              "members": r["members"], "tenures": r["tenures"],
              "lineage_gaps": r["lineage_gaps"], "lineage_todo": r["lineage_todo"],
              "source": r["source"]} for r in items]
    # W2-B6：type/seat 只加给考订行覆盖的门派（无字段的键缺省——前端按字段存在性分区）
    for it, r in zip(items, sorted(records.values(),
                                   key=lambda r: (-(r.get("ev_total") or 0), r["canonical"]))):
        if r.get("type"):
            it["type"] = r["type"]
        if r.get("seat"):
            it["seat"] = r["seat"]
    n_legacy = sum(1 for r in items if r["source"] == "legacy")
    n_new = len(items) - n_legacy
    new_names = [r["canonical"] for r in items if r["source"] == "new"]
    meta_books = sort_books(set(src["conc_books"]) & set(scope["books"])) if scope is not None \
        else list(src["conc_books"])
    meta = {
        "generated": esc.today(),
        "schema": "sects-v1",
        "books": meta_books,
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
    if scope is not None:
        meta["scope"] = scope["profile"]
        meta["field_gaps"].append(
            f"scope 口径（{scope['profile']}）：books 裁到 scope（books ∩ scope，scope 内无出现"
            "的门派不入表）、arts_by_pred 按 book ∈ scope 过滤（空组剔除）；members/tenures/"
            "ev_total 无逐书归属或属人工考订值，保持全量口径原值（成员/频次裁剪待后续批次）。")
    # W2-B6：type/seat 考订口径声明（field_gaps 记缺口，notes 记源与规模——同 EX-1 作品简介口径）
    n_typed = sum(1 for it in items if "type" in it)
    if tsv_exists:
        meta["field_gaps"].append(
            f"type/seat：kb/校订/门派驻地考订.tsv 校定行 {len(calib)} 派（type + "
            f"seat{{name,status,basis}}），入表 {n_typed} 派；其余 {len(items) - n_typed} 派"
            "人工考订未覆盖（无 type/seat 字段，非 null）"
            + (f"；考订在案而库内无 ◆/& 出现记录不入表：{'、'.join(calib_stats['no_corpus'])}。"
               if calib_stats["no_corpus"] else "。"))
        meta["notes"] = [
            f"W2-B6 势力类型/驻地：kb/校订/门派驻地考订.tsv 校定行 {len(calib)} 派，"
            f"type/seat 注入 {calib_stats['n_injected']} 派；考订在案而管线未收、由 TSV 入册 "
            f"{calib_stats['n_created']} 派（{'、'.join(calib_stats['created']) or '—'}，"
            "books/ev_total 取 concordance ◆/& 口径，source=new）；"
            "未入表门派无 type/seat 字段（前端按字段存在性做势力分区/存目分组）。"
            + (f"库内无出现记录不入表 {len(calib_stats['no_corpus'])} 派"
               f"（{'、'.join(calib_stats['no_corpus'])}）。" if calib_stats["no_corpus"] else "")]
    else:
        meta["field_gaps"].append(
            "type/seat：kb/校订/门派驻地考订.tsv 不存在（W2-B6 势力类型未校定），"
            "全部门派无 type/seat 字段。")
        meta["notes"] = ["W2-B6 势力类型/驻地：kb/校订/门派驻地考订.tsv 不存在，未注入 type/seat。"]
    payload = {"meta": meta, "sects": items}
    notes = (f"记录数：旧站 {len(old_by)} → 新 {len(items)}（legacy={n_legacy} / new={n_new}）；"
             f"覆盖/次数更新 {n_count_updated} 条；世系表 7 派 tenures/gaps 已回填；"
             f"W2-B6 type/seat 注入 {calib_stats['n_injected']} 派（考订入册 "
             f"{calib_stats['n_created']} 派）。")
    return payload, {"notes": notes, "legacy": n_legacy, "new": n_new,
                     "calib": calib_stats}


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
        "comments": {"quote", "book", "loc"},          # W3-T4：L1 评语卡（可选键）
        "lineage": {"t", "l", "book", "loc", "tier"},  # W3-T4：传授 note 配对真边（可选键）
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
    # W0-T3a：--scope <profile> 裁剪口径（W0-T1 基础设施；不带 --scope = 全量口径，向后兼容）
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    src = load_sources()
    payloads = {}
    payloads["weapons"], w_stats = build_weapons(src, scope=scope)
    payloads["arts"], a_stats = build_arts(src, scope=scope)
    payloads["sects"], s_stats = build_sects(src, scope=scope)

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
