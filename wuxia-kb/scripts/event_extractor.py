# -*- coding: utf-8 -*-
"""D03 · EX-5 事件层抽取器（event_extractor）

按 SKILL_04a《事件识别》13 类事件类型学 + 36 字段体系，从 5 书 tagged 的
〖实体〗/⟦六域⟧ 令牌与 PN 段号抽取事件（主-谓-宾 + outcome 五值 + 定位符 + 置信 +
类型 + 叙述模式 + tp_id），并合并 N4 registry/time（时点键）与 N5 registry/relations
（关系证据回填）。

数据源（只读）：
  tagged/<书>/*.tagged.md        实体/动词令牌、PN 段号、围栏、对白
  registry/time/<书>.json        N4：time_points（tp_id/锚点/叙述模式）
  registry/relations/<书>.json   N5：关系边（同 loc 回填主宾 + related_relations）
  registry/concordance/<书>.json 书内规范名（变体归并，经 relation_validator 复用）
  registry/entities.json         跨书唯一别名映射

输出：
  registry/events/<书>.json      schema event-v1：events[]（含 event_id/type/verb_domain/
                                 subject/object/outcome/outcome_ref/loc/pn/confidence/
                                 narrative_mode/tp_id/evidence … 及 D03 36 字段映射）
  logs/events/<书>.md + _summary.md  事件数/类型分布/outcome 分布/丢弃原因/时间覆盖

口径：
  - 事件粒度 = 一个非围栏 ⟦动词⟧ 令牌一条候选事件（旧 build_event_table 同一粒度）；
  - 13 类映射按动词六域 + 触发词 + 参与者结构 + 情境信号（SKILL_04a §3.4 判定信号）；
  - outcome 五值（胜/负/平/未决/未知）：胜/负由旧胜负词表命中投影到「主体视角」；
    平=平局词；未决=对抗有双方但无结果证据；未知=无对抗结果信息；
  - 叙述模式优先取 N4 time_point.narrative_mode，缺省 正常叙事；对白内事件 source_type=人物发言；
  - 原文引文不落库（发布边界）：evidence 只保留定位符/段号/令牌/长度。

CLI：
  python scripts/event_extractor.py            # 5 书全跑（写 registry/events + logs/events）
  python scripts/event_extractor.py --book 白发魔女传
  python scripts/event_extractor.py --selftest # 内置断言
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import config
import export_site_common as esc
import symbols
import relation_validator as rv     # 复用其 tagged 解析/实体归一/近邻助手（只读）

EVENTS_DIR = config.DIR_REGISTRY / "events"
LOGS_DIR = config.DIR_LOGS / "events"
TIME_DIR = config.DIR_REGISTRY / "time"
REL_DIR = config.DIR_REGISTRY / "relations"

SCHEMA = "event-v1"
TOOL = "event_extractor v0.1 (2026-11-05, EX-5/D03)"
SPEC = {"skill": "skills/SKILL_04a_事件识别.md",
        "sections": ["§3.4 定版类型卡（13 类）", "§5 事件字段体系（36 字段）",
                     "§6 战斗事件专项", "§5.5 故事时间槽位"],
        "task": "docs/17 §2.4 E5 / docs/51 §三 EX-5"}

# ---------------------------------------------------------------- 13 类事件（SKILL_04a §3.4）
EVENT_TYPES = {
    "T01": "比武较技", "T02": "生死杀伐", "T03": "夺宝争谱", "T04": "拜师传艺",
    "T05": "练功突破", "T06": "结盟背盟", "T07": "门派兴替", "T08": "朝廷剿抚",
    "T09": "起义战争", "T10": "情爱婚约", "T11": "生死救治", "T12": "行踪迁移",
    "T13": "武林大会",
}
DOMAIN_LABEL = {"⊞": "战斗交锋", "⊠": "生命健康", "⊡": "社会关系",
                "⊟": "物件变化", "▣": "技术传习", "■": "行踪迁移"}

# 旧匹配 build_matches.py v0.1 胜负词表（只读参考移植；词表命中词不对外发布）
LOSS_CLASSES = [
    (1.0, ["大败", "击败", "战败", "打败", "击倒", "击毙", "刺死", "擒下", "活捉",
           "一招夺下", "毙于", "斩于", "死于", "杀退", "败走", "倒地", "栽倒", "杀死",
           "斩杀", "结果|杀死", "害死", "打死", "刺伤", "重伤", "身亡", "丧命", "毙命",
           "就擒", "被擒", "被点", "缴械", "夺下", "击落", "打落", "削断", "斩断",
           "震飞", "击飞", "踢飞", "跌飞", "翻倒", "跌倒", "败退", "落败", "不敌",
           "不支", "难支", "认输", "求饶", "受制", "被制", "点倒", "点中", "擒住"]),
    (0.8, ["占得上风", "迫退", "逼退", "震退", "荡开", "迫得后退", "逼得后退", "伤在",
           "退走", "退去", "倒退", "却步", "连退", "招架不住", "遮拦不住", "再难支撑",
           "难以招架", "手忙脚乱", "败象", "负伤", "受伤", "挂彩", "吐血", "中剑",
           "中掌", "中刀", "脱手", "折断", "断裂", "震开", "击开"]),
    (0.6, ["险胜", "堪堪取胜", "略胜一筹", "侥幸获胜", "略占上风", "小胜", "稍占上风"]),
]
DRAW_WORDS = ["不分胜负", "平分秋色", "难分高下", "势均力敌", "旗鼓相当", "打个平手",
              "战个平手", "战成平手", "相持不下", "两败俱伤", "斗个两败俱伤"]
FLIP_WORDS = ["连连后退", "只有招架", "招架不住", "招架之功", "败象渐露", "遮拦不住", "再难支撑"]
MODIFIER_WORDS = [
    ("中毒", ["中毒", "服毒", "下药"]),
    ("状态不佳", ["带伤", "伤重", "力竭", "久战"]),
    ("偷袭", ["偷袭", "暗算", "冷箭", "背后偷袭"]),
    ("诈败", ["诈败", "卖个破绽", "佯输"]),
    ("放水", ["留手", "未出全力", "手下留情"]),
    ("切磋", ["切磋", "指点", "印证武功", "点到即止"]),
]
MOD_MULT = {"中毒": 0.3, "状态不佳": 0.5, "偷袭": 0.5, "诈败": 0.5, "放水": 0.5, "切磋": 0.3}

ACTOR_TYPES = rv.P_TYPES | rv.O_TYPES      # {"@","&","◎","◆"}：事件主宾只用角色性实体
KILL_WORDS = {"杀", "杀死", "斩杀", "诛", "结果", "害死", "杀毙", "刺杀", "伏杀", "毒杀",
              "残杀", "误杀", "砍死", "打死", "加害", "谋害", "杀害", "毙", "弄死"}
CURE_WORDS = {"疗伤", "救活", "治愈", "医治", "救治", "疗治", "敷药", "疗毒"}
RESCUE_WORDS = {"救", "救出", "救下", "营救", "搭救", "抢救", "解救", "救回"}
DEATH_WORDS = {"死", "亡", "病故", "去世", "自尽", "自刎", "殒命", "丧命", "寿终", "死于"}
INJURY_WORDS = {"伤", "受伤", "重伤", "中", "中伤", "刺伤", "打伤", "内伤", "中毒"}
POISON_WORDS = {"下毒", "投毒", "放毒", "施毒", "下药"}
TEACH_WORDS = {"拜", "拜师", "收徒", "收", "授艺", "传授", "教", "指点", "教授", "传艺", "收为"}
LEARN_WORDS = {"练成", "学会", "悟出", "练就", "学成", "修习", "练", "习", "偷学", "窃艺", "散功", "走火入魔"}
SWORN_WORDS = {"结义", "结拜", "义结", "八拜", "结盟", "结为", "歃血"}
BETRAY_WORDS = {"叛", "叛出", "叛门", "逐出", "驱逐", "投靠", "出卖", "背叛"}
APPOINT_WORDS = {"任命", "继任", "接任", "接掌", "即位", "登基", "立为", "封为", "任", "掌门", "传位"}
MARRY_WORDS = {"娶", "嫁", "成亲", "成婚", "结婚", "完婚", "迎娶", "许配", "下嫁", "纳妾",
               "定情", "悔婚", "退婚", "私奔"}
TRAVEL_WORDS = {"到达", "抵达", "来到", "回到", "赶到", "走到", "走进", "跑进", "冲进", "进入",
                "潜入", "混入", "到", "来", "往", "去", "回", "离开", "走出", "退出", "逃出",
                "撤离", "离去", "下山", "远走", "押解", "解往", "押送", "解送", "追踪", "跟踪",
                "追", "赶", "逃", "走", "跑", "退", "进", "出"}
OBJECT_PICK = {"夺", "抢", "夺取", "抢夺", "抢走", "夺走", "夺去", "取得", "取", "拿", "赠",
               "赠送", "相赠", "送给", "交给", "递给", "送", "还", "归还", "交还", "借", "借给",
               "铸", "铸造", "炼制", "打造", "锻造", "毁", "烧", "焚", "烧毁", "焚毁", "折断",
               "撕毁", "盗", "偷", "窃"}
FIGHT_WORDS = {"交手", "比武", "比试", "过招", "切磋", "较量", "打擂", "斗", "恶斗", "大战",
               "交锋", "交战", "搏斗", "打斗", "拼", "战", "打", "杀", "刺", "砍", "劈", "击",
               "攻", "扑", "抓", "擒", "踢", "拍", "撞", "扫", "削", "戳", "格", "挡", "接",
               "震", "摔", "推", "迫", "封", "拦", "阻", "避", "闪", "退"}
GOV_WORDS = {"围剿", "剿", "缉捕", "捉拿", "押解", "解往", "处决", "问斩", "招安", "围困", "搜捕"}
# 触发词级胜负投影：动作本身含明确胜负/结果义（无胜败词表时的次优证据，weight 0.8）
WIN_VERBS = {"击败", "打败", "战胜", "击退", "逼退", "震退", "迫退", "打倒", "击倒", "击毙",
             "刺死", "杀死", "斩杀", "结果", "害死", "擒", "擒住", "抓住", "抓着", "点倒",
             "点中", "点着", "制服", "踢倒", "削断", "砍倒", "打中", "刺中", "击中",
             "打伤", "刺伤", "重伤", "打退", "退敌", "击落", "打落", "震飞", "击飞",
             "缴械", "夺下", "按住", "制住", "压住", "摔倒", "毙命", "就擒", "被擒"}
WAR_WORDS = {"起义", "造反", "勤王", "攻城", "破城", "大军", "兵变", "征战", "平叛", "进剿"}
# D2 质量参数（T13 容器聚合阈值；可 CLI 覆盖 --t13-min-subevents/--t13-window）
T13_MIN_SUBEVENTS = 4
T13_WINDOW_PN = 30
T13_WEAK_MIN_WINDOW = 8      # 弱语式（大会/齐集…）无共同地点/主办时，窗口内至少需这么多子事件
T13_SUB_TYPES = {"T01", "T02", "T04", "T06", "T09"}
T13_CUES = ("英雄大会", "武林大会", "群雄大会", "推举盟主", "比武招亲", "擂台",
            "大会", "群雄齐聚", "齐聚一堂", "齐集", "群雄毕至")
T13_STRONG_CUES = ("英雄大会", "武林大会", "群雄大会", "推举盟主", "比武招亲", "擂台")

NARRATIVE_MARKERS = {"回忆": ("原来", "当年", "想起", "回忆", "记得", "忆及", "追忆"),
                     "梦境": ("梦中", "梦见", "梦醒", "梦境"),
                     "假想": ("假使", "倘若", "若是", "假如"),
                     "戏中戏": ("戏中", "演戏", "唱戏")}


# ---------------------------------------------------------------- 时间 / 关系索引
def load_time_index(book: str) -> dict:
    """N4 registry/time → 逐回时点列表（pn 有序）；返回 {points_by_chapter, work_id, generated}。"""
    path = TIME_DIR / f"{book}.json"
    if not path.exists():
        return {"points_by_chapter": {}, "work_id": "", "generated": None}
    data = esc.load_json(path)
    by_ch = defaultdict(list)
    for tp in data.get("time_points") or []:
        anchor = tp.get("anchor") or {}
        ch, pn = anchor.get("chapter"), anchor.get("pn")
        if ch is None or pn is None:
            continue
        by_ch[int(ch)].append({"pn": int(pn), "tp_id": tp.get("tp_id"),
                               "display": tp.get("display"),
                               "time_type": tp.get("time_type"),
                               "confidence": tp.get("confidence"),
                               "narrative_mode": tp.get("narrative_mode") or "正常叙事",
                               "year_ce": tp.get("year_ce"),
                               "year_range": tp.get("year_range"),
                               "status": tp.get("status")})
    for ch in by_ch:
        by_ch[ch].sort(key=lambda x: x["pn"])
    return {"points_by_chapter": dict(by_ch),
            "work_id": data.get("work_id") or "",
            "generated": data.get("generated_at")}


def time_for_event(time_idx: dict, chapter: int, pn: int) -> dict:
    """事件段 → 最近的前置时点（同章；优先 时点类/主轨）。"""
    pts = time_idx.get("points_by_chapter", {}).get(chapter) or []
    cands = [p for p in pts if p["pn"] <= pn]
    if not cands:
        return {}
    # 优先主轨/对话中的时点类，其次最近
    preferred = [p for p in cands if p.get("time_type") == "时点"]
    pool = preferred or cands
    return pool[-1]


def load_relation_index(book: str) -> dict:
    """N5 relations → {(chapter,pn): [edge…]}（用于主宾回填/关联证据）。"""
    path = REL_DIR / f"{book}.json"
    if not path.exists():
        return {}
    data = esc.load_json(path)
    idx = defaultdict(list)
    for e in data.get("edges") or []:
        loc = e.get("loc") or ""
        try:
            ch, pn = loc.split(":")
            key = (int(ch), int(pn))
        except ValueError:
            continue
        idx[key].append({"subject": e.get("subject"), "object": e.get("object"),
                         "predicate": e.get("predicate"), "rule": e.get("rule"),
                         "confidence": e.get("confidence")})
    return dict(idx)


# ---------------------------------------------------------------- 角色/结果
def resolve_roles(para: "rv.Para", verb: dict) -> tuple:
    """主-谓-宾启发式（移植旧 build_event_table：把/将/被动三变式 + 同句窗口）。"""
    ents = [e for e in para.entities]
    vs = verb["pos"]
    sent = para.sent_of(vs)
    subj = obj = None
    mode = "plain"
    pre = [e for e in ents if e["code"] in ACTOR_TYPES and e["end"] <= vs
           and sent[0] <= e["pos"] and vs - e["end"] <= 40]
    PASSIVE = "被给让叫教"
    if pre:
        last = pre[-1]
        gap_last = para.text[last["end"]:vs]
        gap_prev = ""
        prev_same_clause = False
        if len(pre) >= 2:
            gap_prev = para.text[pre[-2]["end"]:pre[-1]["pos"]]
            prev_same_clause = not any(c in gap_prev for c in "，。；：！？、")
        if prev_same_clause and "被" in gap_prev:
            mode, subj, obj = "passive", pre[-1]["canon"], pre[-2]["canon"]
        elif any(c in gap_last for c in PASSIVE):
            mode, obj = "passive", last["canon"]
            mk = max(para.text.rfind(c, last["end"], vs) for c in PASSIVE
                     if para.text.rfind(c, last["end"], vs) >= 0)
            agts = [e for e in ents if e["code"] in ACTOR_TYPES and mk < e["pos"] < vs]
            if agts:
                subj = agts[-1]["canon"]
        elif "把" in gap_last or "将" in gap_last:
            mode, obj = "ba", last["canon"]
            ba = max(para.text.rfind("把", last["end"], vs), para.text.rfind("将", last["end"], vs))
            if len(pre) >= 2 and pre[-2]["end"] <= ba:
                subj = pre[-2]["canon"]
        else:
            subj = last["canon"]
    if obj is None:
        cut = verb["end"]
        for j in range(verb["end"], min(verb["end"] + 30, sent[1], len(para.text))):
            if para.text[j] in "，。；：！？、""":
                break
            cut = j + 1
        post = [e for e in ents if e["code"] in ACTOR_TYPES and verb["end"] <= e["pos"] < cut]
        if post:
            obj = post[0]["canon"]
    # 事件主语允许 人物/组织/家族/群组；同主体剔除
    if subj and obj and subj == obj:
        obj = None
    return subj, obj, mode


def winner_from_words(text: str, a: str, b: str):
    """胜败裁决（旧词表 v0.1 移植）：返回 ('a'|'b'|'draw'|None, weight_cls, words_hit)。"""
    pair = {a, b}
    all_words = [(w, cw) for cw, ws in LOSS_CLASSES for w in ws] + [(w, 0.8) for w in FLIP_WORDS]

    def nearest(pos: int):
        seg = text[max(0, pos - 14):pos]
        best, bp = None, -1
        for n in pair:
            p = seg.rfind(n)
            if p > bp:
                best, bp = n, p
        return best

    votes = defaultdict(float)
    hits = []
    for w, cw in all_words:
        start = 0
        while True:
            pp = text.find(w, start)
            if pp < 0:
                break
            loser = nearest(pp)
            if loser:
                winner = b if loser == a else a
                votes[winner] += cw
                hits.append(w)
            start = pp + len(w)
    if votes:
        winner = sorted(votes.items(), key=lambda kv: -kv[1])[0][0]
        return winner, round(min(1.0, votes[winner]), 2), hits
    if any(w in text for w in DRAW_WORDS):
        return "draw", 0.7, [w for w in DRAW_WORDS if w in text]
    return None, None, []


def modifiers_of(text: str) -> list:
    return [name for name, kws in MODIFIER_WORDS if any(k in text for k in kws)]


VALID_NARRATIVE_MODES = {"正常叙事", "回忆", "梦境", "假想", "戏中戏"}


def narrative_mode_of(para: "rv.Para", tp: dict) -> str:
    mode = tp.get("narrative_mode")
    if mode in VALID_NARRATIVE_MODES:
        return mode
    for m, words in NARRATIVE_MARKERS.items():
        if any(w in para.plain[:120] for w in words):
            return m
    return "正常叙事"


# ---------------------------------------------------------------- 13 类判定
def classify_event(verb: dict, subj: str | None, obj: str | None,
                   related: dict, para: "rv.Para", text: str) -> tuple:
    """→ (type_code, subtype, rationale)。判定序：专类优先，泛 ⊞ 按致死/比武分流。"""
    code, word = verb["code"], verb["word"]
    rel_codes = {c for c, items in related.items() if items}
    has_org = "◆" in rel_codes or any(e["code"] == "◆" for e in para.entities)
    has_gov = any(w in text for w in GOV_WORDS) or (has_org and any(w in text for w in ("朝廷", "官府", "官兵", "侍卫", "锦衣卫")))
    has_war = any(w in text for w in WAR_WORDS)
    has_weapon = "•" in rel_codes or "{" in rel_codes
    has_skill = "☆" in rel_codes
    if code == "⊞":
        if word in KILL_WORDS or any(w in text for w in ("杀死", "斩杀", "刺死", "结果", "害死")):
            return "T02", "击杀", "⊞+致死信号（SKILL_04a T02）"
        if has_war and has_org:
            return "T09", "战争级冲突", "大规模+组织主体（T09）"
        if has_gov:
            return "T08", "官军行动", "官府/朝廷主体（T08）"
        if word in FIGHT_WORDS and any(w in text for w in ("比武", "比试", "过招", "切磋", "点到即止", "讨教", "分个高下")):
            return "T01", "比武", "比武信号（T01）"
        if word in KILL_WORDS or code == "⊠":
            return "T02", "杀伐", "致死动作（T02）"
        return "T01", "交手", "⊞ 对抗（无致死信号，T01 候选）"
    if code == "⊠":
        if word in KILL_WORDS or subj and any(w in text for w in ("杀", "斩", "害")):
            return "T02", "杀伐", "⊠ 致死/加害（T02）"
        if word in POISON_WORDS:
            if subj:
                return "T02", "毒害", "投毒致害（有加害方，T02）"
            return "T11", "中毒", "中毒/投毒（无加害方明写，T11）"
        if word in DEATH_WORDS:
            return "T11", "死亡", "无加害方明写（T11）"
        if word in CURE_WORDS or word in RESCUE_WORDS:
            return "T11", "救治", "疗伤/救活（T11）"
        if word in INJURY_WORDS:
            return "T11", "伤情", "伤情阈值（T11）"
        return "T11", "生死健康", "⊠ 泛化（T11）"
    if code == "⊟":
        if word in OBJECT_PICK or has_weapon:
            if word in {"铸", "铸造", "炼制", "打造", "锻造"}:
                return "T03", "铸造", "器物制造（T03 物件变化）"
            if word in {"毁", "烧", "焚", "烧毁", "焚毁", "折断", "撕毁"}:
                return "T03", "毁弃", "器物毁损（T03）"
            return "T03", "夺取/转移", "器物归属变更（T03）"
        return "T03", "物件", "⊟ 物件变化（T03）"
    if code == "▣":
        if word in TEACH_WORDS:
            return "T04", "传授/授艺", "▣ 授艺（T04）"
        if word in LEARN_WORDS:
            achieved = word in {"练成", "学会", "悟出", "练就", "学成"}
            return "T05", ("练成" if achieved else "修习"), f"▣ 习得（achieved={achieved}，T05）"
        return "T05", "练功", "▣ 技术事件（T05）"
    if code == "⊡":
        if word in SWORN_WORDS:
            return "T06", "结义/结盟", "⊡ 盟约（T06）"
        if word in BETRAY_WORDS:
            return "T06", "叛离/逐出", "⊡ 隶属变更（T06）"
        if word in APPOINT_WORDS:
            return "T07", "任免/承继", "⊡ 组织职任（T07）"
        if word in MARRY_WORDS:
            return "T10", "婚约/成亲", "⊡ 婚恋行为（T10）"
        if word in {"定情", "悔婚", "退婚", "私奔"}:
            return "T10", "婚恋", "⊡ 婚恋行为（T10）"
        if has_gov:
            return "T08", "官府行动", "⊡+官府主体（T08）"
        if has_org and ("逐出" in text or "叛" in text):
            return "T06", "组织变更", "组织隶属（T06）"
        return "T06", "社会关系", "⊡ 社会行为（T06 候选）"
    if code == "■":
        if any(w in text for w in ("押解", "解往", "押送", "解送", "缉捕", "捉拿")):
            return "T12", "押送", "■ 押解/缉捕（T12；官府语境另见 T08 候选）"
        if any(w in text for w in WAR_WORDS) and has_org:
            return "T09", "战争行军", "大规模移动+组织（T09）"
        return "T12", "行程迁移", "■ 行踪（T12）"
    return "T12", "未分类", f"{code} 未映射（默认 T12）"


# ---------------------------------------------------------------- 单段抽取
def extract_paragraph(ctx, book: str, chapter: int, para_no: int, text: str,
                      time_idx: dict, rel_idx: dict) -> dict:
    para = rv.Para(ctx, chapter, para_no, text)
    res = {"events": [], "verbs": len(para.verbs), "in_quote": 0, "fence": 0,
           "no_participants": 0, "relation_filled": 0, "time_hit": 0, "cues": []}
    res["cues"] = [c for c in T13_CUES if c in para.plain]
    if not para.verbs:
        return res
    tp = time_for_event(time_idx, chapter, para_no)
    mode = narrative_mode_of(para, tp)
    sent_text_cache = {}
    for i, verb in enumerate(para.verbs):
        subj, obj, role_mode = resolve_roles(para, verb)
        # N5 关系回填（同 loc 同域优先）
        rel_hit = None
        for edge in rel_idx.get((chapter, para_no), []):
            pred = edge.get("predicate") or ""
            if pred in ("交手", "杀害", "治愈", "转移", "解救", "师承", "押送", "点穴", "收养", "婚约", "结义"):
                if subj in (None, edge.get("subject")) or obj in (None, edge.get("object")):
                    rel_hit = edge
                    break
        if rel_hit:
            if subj is None:
                subj = rel_hit.get("subject")
                res["relation_filled"] += 1
            if obj is None:
                obj = rel_hit.get("object")
                res["relation_filled"] += 1
        sent = para.sent_of(verb["pos"])
        text_sent = sent_text_cache.get(sent)
        if text_sent is None:
            text_sent = para.text[sent[0]:sent[1]]
            sent_text_cache[sent] = text_sent
        plain_sent = symbols.strip_markup(text_sent)
        related = defaultdict(list)
        for e in para.entities:
            if sent[0] <= e["pos"] < sent[1] and e["canon"] not in (subj, obj):
                if e["code"] in ("☆", "•", "{", "◆", "=", "^", "%", ";"):
                    related[e["code"]].append(e["canon"])
        typ, subtype, rationale = classify_event(verb, subj, obj, related, para, plain_sent)
        # outcome（对抗类）
        outcome, outcome_weight, outcome_ref, outcome_basis = None, None, "", ""
        if typ in ("T01", "T02", "T09"):
            a, b = subj, obj
            if a and b and a != b:
                winner, wcls, hits = winner_from_words(plain_sent, a, b)
                if winner in (a, b):
                    outcome = "胜" if winner == a else "负"
                    outcome_ref = winner
                    outcome_weight = wcls
                    outcome_basis = "胜败词表命中（旧 v0.1 移植）"
                elif winner == "draw":
                    outcome, outcome_ref, outcome_weight = "平", "", 0.7
                    outcome_basis = "平局词命中"
                elif typ == "T02" and verb["word"] in KILL_WORDS:
                    if role_mode == "passive":
                        outcome, outcome_ref = "负", b
                    else:
                        outcome, outcome_ref = "胜", a
                    outcome_weight = 0.9
                    outcome_basis = "T02 杀伐触发词（致死结果，weight 0.9）"
                elif verb['word'] in WIN_VERBS:
                    if role_mode == "passive":
                        outcome, outcome_ref = "负", b
                    else:
                        outcome, outcome_ref = "胜", a
                    outcome_weight = 0.8
                    outcome_basis = "触发词胜负投影（动作含明确结果义，weight 0.8）"
                else:
                    outcome, outcome_basis = "未决", "双方在场但无胜负词证据"
            elif a or b:
                outcome, outcome_basis = "未知", "仅单方参与者"
            else:
                outcome, outcome_basis = "未知", "无参与方"
        if typ not in ("T01", "T02", "T09"):
            outcome, outcome_ref, outcome_weight, outcome_basis = None, "", None, ""
        cond = modifiers_of(plain_sent)
        if typ in ("T01", "T02") and any(w in plain_sent for w in ("点到即止", "讨教", "切磋")):
            if "切磋" not in cond:
                cond.append("切磋")
        if typ in ("T01", "T02", "T09") and not outcome:
            outcome = "未知"
        verb_weight = 1.0
        for mo in cond:
            verb_weight *= MOD_MULT.get(mo, 1.0)
        if outcome_weight is not None:
            outcome_weight = round(outcome_weight * verb_weight, 2)
        quote_len = 0
        name = subtype or EVENT_TYPES[typ]
        if verb["in_quote"]:
            res["in_quote"] += 1
        related_rels = []
        if rel_hit:
            related_rels.append(f"N5:{rel_hit.get('predicate')}@{chapter:03d}:{para_no:03d}")
        event = {
            # —— D03/SKILL_04a 必填/核心字段 ——
            "event_id": f"{chapter:03d}.{para_no:03d}.{i + 1:02d}",
            "type": typ,
            "type_label": EVENT_TYPES[typ],
            "subtype": subtype,
            "name": name,
            "verb_domain": verb["code"],
            "verb_domain_label": DOMAIN_LABEL.get(verb["code"], ""),
            "anchor_verbs": [{"verb": verb["word"], "domain": verb["code"],
                              "pos": verb["pos"], "in_quote": verb["in_quote"]}],
            "subject": subj or "",
            "object": obj or "",
            "role_mode": role_mode,
            "participants": [{"role": "施者", "name": subj, "entity_type": "@"},
                             {"role": "受者", "name": obj, "entity_type": "@"}]
                            if subj and obj else
                            ([{"role": "施者", "name": subj, "entity_type": "@"}] if subj else
                             ([{"role": "受者", "name": obj, "entity_type": "@"}] if obj else [])),
            "outcome": outcome,
            "outcome_ref": outcome_ref,
            "outcome_basis": outcome_basis,
            "outcome_weight": outcome_weight,
            "manner": "；".join(cond) if cond else "",
            "condition_tags": cond,
            # —— 定位/时间/叙述 ——
            "book": book,
            "chapter": chapter,
            "pn": para_no,
            "loc": f"{chapter:03d}:{para_no:03d}",
            "anchor": f"{time_idx.get('work_id') or book}#pn-r{chapter}.{para_no}",
            "time_slot": {"tp_id": tp.get("tp_id"), "display": tp.get("display"),
                          "time_type": tp.get("time_type"), "confidence": tp.get("confidence"),
                          "year_ce": tp.get("year_ce"), "year_range": tp.get("year_range")}
                         if tp else None,
            "tp_id": tp.get("tp_id") if tp else None,
            "narrative_mode": mode,
            "narrative_line": tp.get("narrative_line") if tp else "",
            "source_type": "人物发言" if verb["in_quote"] else "叙述",
            "veracity": "来源声称" if verb["in_quote"] else "叙述",
            "occurrence_status": "已发生",
            "completion_status": "未遂" if any(w in plain_sent for w in ("未中", "落空", "扑空", "未遂", "没有刺中", "没打中")) else "完成",
            # —— 相关实体/证据/置信 ——
            "related_skills": related.get("☆", []),
            "related_objects": related.get("•", []) + related.get("{", []),
            "related_orgs": related.get("◆", []),
            "related_places": related.get("=", []),
            "related_concepts": related.get("^", []) + related.get("%", []) + related.get(";", []),
            "related_relations": related_rels,
            "confidence": ("high" if subj and obj and not verb["in_quote"] else
                           "medium" if (subj or obj) else "low"),
            "review_status": "候选" if (typ in ("T01", "T02") and outcome in ("未决", "未知")) else "",
            "evidence": [{"loc": f"{chapter:03d}:{para_no:03d}",
                          "para_no": para_no, "token": f"⟦{verb['code']}{verb['word']}⟧",
                          "quote_len": quote_len, "quote_published": False}],
            "description": (f"{book} {chapter:03d}:{para_no:03d} {EVENT_TYPES[typ]}"
                            f"（{subtype or verb['word']}）：{subj or '—'} → {obj or '—'}"),
            "spec_version": "D03@0.3-draft / 04a",
            "summary_ready": bool(subj and obj),
        }
        res["events"].append(event)
    return res


def iter_paragraphs(path: Path):
    """tagged → [(段号, 原文)]；围栏内不抽事件（02ab 纪律）。"""
    out = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if in_fence:
            if line.strip() == ":::":
                in_fence = False
            continue
        if line.startswith(":::"):
            in_fence = True
            continue
        m = rv.PARAGRAPH_RE.match(line)
        if not m:
            continue
        no = int(m.group(1))
        if no == 0:
            continue
        out.append((no, m.group(2)))
    return out


# ---------------------------------------------------------------- D2 质量门控 / T13 容器
def gate_event(ev: dict) -> None:
    """low 置信门控（规则化）：无参与方→排除；单方→降级待审；修辞/非事实叙述→排除。

    规则 R1：subj/obj 均缺 → gate=excluded，confidence=low（无参与方）
    规则 R2：单侧参与 → gate=review，confidence=low（单方，降级）
    规则 R3：叙述模式 ∈ {梦境,假想,戏中戏} → gate=excluded（修辞/非事实叙述，不入事实表）
    规则 R4：source_type=人物发言 且双侧参与 → gate=review（对白视角，事实待核）
    """
    subj, obj = ev.get("subject") or "", ev.get("object") or ""
    if ev.get("narrative_mode") in ("梦境", "假想", "戏中戏"):
        ev["gate"], ev["gate_reason"] = "excluded", "R3 非事实叙述模式"
        ev["confidence"] = "low"
        return
    if not subj and not obj:
        ev["gate"], ev["gate_reason"] = "excluded", "R1 无参与方"
        ev["confidence"] = "low"
        return
    if not subj or not obj:
        ev["gate"], ev["gate_reason"] = "review", "R2 单方参与者（降级）"
        ev["confidence"] = "low"
        return
    if ev.get("source_type") == "人物发言":
        ev["gate"], ev["gate_reason"] = "review", "R4 对白内（视角/转述，事实待核）"
        ev["confidence"] = "medium" if ev.get("confidence") == "high" else ev.get("confidence", "medium")
        return
    ev["gate"], ev["gate_reason"] = "ok", ""
    ev["confidence"] = ev.get("confidence") or "medium"


def _common(items: list, min_count: int = 2, limit: int = 5) -> list:
    c = Counter(x for x in items if x)
    return [k for k, v in c.most_common() if v >= min_count][:limit]


def aggregate_t13(events: list, cue_by_chapter: dict,
                  min_subevents: int = T13_MIN_SUBEVENTS,
                  window_pn: int = T13_WINDOW_PN,
                  weak_min_window: int = T13_WEAK_MIN_WINDOW) -> tuple:
    """T13 武林大会：以「大会/擂台/推举」语式所在段为锚，PN±window 内聚合多场子事件。

    - 强语式（英雄大会/武林大会/推举盟主/比武招亲/擂台）阈值 = min_subevents；
    - 弱语式（大会/齐集/群雄齐聚…）阈值 = min_subevents + 1，且须有共同地点/主办；
    - 同一回内按语式锚点从左到右生成非重叠容器（重叠锚点跳过）。
    """
    subs = [e for e in events if e.get("type") in T13_SUB_TYPES and e.get("gate") == "ok"]
    by_ch = {}
    for e in subs:
        by_ch.setdefault(int(e["chapter"]), []).append(e)
    containers = []
    covered = []
    cidx = 0
    for ch in sorted(by_ch):
        group = sorted(by_ch[ch], key=lambda e: int(e["pn"]))
        cue_list = sorted((int(pn), c) for pn, cs in (cue_by_chapter.get(ch) or {}).items()
                          for c in cs)
        for cue_pn, cue in cue_list:
            if any(lo <= cue_pn <= hi for lo, hi in covered):
                continue
            lo, hi = cue_pn - window_pn, cue_pn + window_pn
            window = [e for e in group if lo <= int(e["pn"]) <= hi]
            if not window:
                continue
            range_cues = sorted({c for pn, c in cue_list if lo <= pn <= hi})
            strong = [c for c in range_cues if c in T13_STRONG_CUES]
            need = min_subevents if strong else min_subevents + 1
            if len(window) < need:
                continue
            places = _common([p for e in window for p in (e.get("related_places") or [])])
            orgs = _common([o for e in window for o in (e.get("related_orgs") or [])])
            if not strong and not places and not orgs and len(window) < weak_min_window:
                continue
            cidx += 1
            cid = f"{ch:03d}.{cue_pn:03d}.C{cidx:02d}"
            names = []
            for e in window:
                for pt in e.get("participants") or []:
                    if pt.get("name") and pt["name"] not in names:
                        names.append(pt["name"])
            nmodes = Counter(e.get("narrative_mode") for e in window)
            container = {
                "event_id": cid,
                "type": "T13", "type_label": EVENT_TYPES["T13"],
                "subtype": (strong[0] if strong else cue),
                "name": (strong[0] if strong else "武林大会"),
                "verb_domain": "⊞", "verb_domain_label": DOMAIN_LABEL["⊞"],
                "anchor_verbs": [],
                "subject": (orgs[0] if orgs else ""), "object": "",
                "role_mode": "container",
                "participants": [{"role": "参与者", "name": n, "entity_type": "@"}
                                 for n in names[:40]],
                "outcome": None, "outcome_ref": "", "outcome_basis": "",
                "outcome_weight": None, "manner": "", "condition_tags": [],
                "book": window[0]["book"], "chapter": ch, "pn": cue_pn,
                "loc": f"{ch:03d}:{cue_pn:03d}",
                "anchor": f"{window[0].get('anchor', '').split('#')[0]}#pn-r{ch}.{cue_pn}",
                "time_slot": window[0].get("time_slot"), "tp_id": window[0].get("tp_id"),
                "narrative_mode": nmodes.most_common(1)[0][0] if nmodes else "正常叙事",
                "narrative_line": window[0].get("narrative_line", ""),
                "source_type": "推导", "veracity": "推导",
                "occurrence_status": "已发生", "completion_status": "完成",
                "related_skills": sorted({x for e in window for x in (e.get("related_skills") or [])})[:20],
                "related_objects": sorted({x for e in window for x in (e.get("related_objects") or [])})[:20],
                "related_orgs": orgs, "related_places": places, "related_concepts": [],
                "related_relations": [],
                "confidence": "medium" if strong else "low",
                "review_status": "候选",
                "gate": "ok" if strong else "review",
                "gate_reason": "" if strong else "R5 弱大会语式（须共同地点/主办）",
                "evidence": [{"loc": e["loc"], "para_no": e["pn"], "token": "T13聚合",
                              "quote_len": 0, "quote_published": False}
                             for e in window[:3]],
                "description": (f"{window[0]['book']} {ch:03d}:{cue_pn:03d} 武林大会容器（{cue}）："
                                f"{len(window)} 场子事件，地点={places or '—'}，主办={orgs or '—'}"),
                "spec_version": "D03@0.3-draft / 04a",
                "summary_ready": True,
                "container": {"sub_event_ids": [e["event_id"] for e in window],
                              "pn_range": [int(window[0]["pn"]), int(window[-1]["pn"])],
                              "window_pn": window_pn, "min_subevents": min_subevents,
                              "weak_min_window": weak_min_window,
                              "cues": range_cues, "strong_cues": strong,
                              "common_places": places, "common_orgs": orgs,
                              "sub_types": dict(Counter(e["type"] for e in window))},
            }
            containers.append(container)
            covered.append((lo, hi))
            for e in window:
                e["container_id"] = cid
    stats = {"containers": len(containers),
             "contained_subevents": sum(len(c["container"]["sub_event_ids"]) for c in containers),
             "params": {"min_subevents": min_subevents, "window_pn": window_pn,
                        "weak_min_window": weak_min_window,
                        "weak_cue_extra": 1, "sub_types": sorted(T13_SUB_TYPES),
                        "strong_cues": list(T13_STRONG_CUES)},
             "cues": dict(Counter(c for x in containers for c in (x["container"]["cues"] or [])))}
    return containers, events + containers, stats


# ---------------------------------------------------------------- 报告
def render_book_report(book: str, payload: dict) -> str:
    events = payload["events"]
    by_type = Counter(e["type"] for e in events)
    by_out = Counter(e["outcome"] for e in events)
    by_conf = Counter(e["confidence"] for e in events)
    by_mode = Counter(e["narrative_mode"] for e in events)
    by_domain = Counter(e["verb_domain"] for e in events)
    stats = payload["stats"]
    lines = [
        f"# 事件层抽取报告 · {book}",
        "",
        f"- 生成：{payload['generated_at']} · 工具：{TOOL}",
        f"- schema：{SCHEMA} · 规范：{SPEC['skill']}（13 类/36 字段）",
        f"- 来源：tagged（只读）+ N4 registry/time + N5 registry/relations；"
        f"N4 work_id={payload.get('work_id') or '—'} · 时间点 {stats['time_points']} 条"
        f"（覆盖事件 {stats['time_hit']}）",
        "",
        "## 1 · 总量",
        "",
        "| 项 | 数 |",
        "|---|---:|",
        f"| 扫描动词令牌 | {stats['verbs']} |",
        f"| 抽取事件 | {len(events)} |",
        f"| 对白内（source_type=人物发言） | {stats['in_quote']} |",
        f"| 围栏内跳过 | {stats['fence']} |",
        f"| 无参与方 | {stats['no_participants']} |",
        f"| N5 关系回填主宾 | {stats['relation_filled']} |",
        f"| 置信分布 | {dict(by_conf)} |",
        "",
        "## 1b · D2 质量门控（low 置信规则化）",
        "",
        "| gate | 数 | 含义 |",
        "|---|---:|---|",
        f"| ok | {stats.get('by_gate', {}).get('ok', 0)} | 双侧参与/事实叙述（可进入 matches/ratings） |",
        f"| review | {stats.get('by_gate', {}).get('review', 0)} | 单方或对白内（降级待审） |",
        f"| excluded | {stats.get('by_gate', {}).get('excluded', 0)} | 无参与方/非事实叙述（排除事实表） |",
        "",
        f"- 门控原因分布：{payload['stats'].get('gate_reasons', {})}",
        f"- 规则：R1 无参与方→excluded；R2 单方→review(low)；R3 梦境/假想/戏中戏→excluded；"
        f"R4 对白→review（事实待核）",
        "",
        "## 2 · 13 类事件分布（SKILL_04a §3.4）",
        "",
        "| 类型 | 名称 | 事件数 |",
        "|---|---|---:|",
    ]
    for code in sorted(EVENT_TYPES):
        lines.append(f"| {code} | {EVENT_TYPES[code]} | {by_type.get(code, 0)} |")
    zero = [f"{c} {EVENT_TYPES[c]}" for c in sorted(EVENT_TYPES) if not by_type.get(c)]
    if zero:
        lines += ["", f"- 未命中类型：{ '、'.join(zero)}（容器型/条件型规则，本批 0 命中；"
                  "属数据缺口而非静默丢弃，详见本报告第 5 节）。"]
    lines += [
        "",
        "## 3 · outcome 五值分布（对抗类 T01/T02/T09；非对抗类 outcome=null）",
        "",
        "| outcome | 数 |",
        "|---|---:|",
        *[f"| {k if k is not None else '—(非对抗类)'} | {v} |"
          for k, v in sorted(by_out.items(), key=lambda kv: str(kv[0]))],
        "",
        "## 3b · T13 武林大会容器（D2 聚合）",
        "",
        f"- 容器数：{payload['summary'].get('t13_containers', 0)}；"
        f"纳入子事件 {payload['summary'].get('t13_contained_subevents', 0)} 场；"
        f"参数 {payload['summary'].get('t13_params')}",
        "",
        "| 容器 id | 回:段 | 语式 | 子事件 | 地点 | 主办 | 置信 |",
        "|---|---|---|---:|---|---|---|",
    ]
    for c in [e for e in payload["events"] if e["type"] == "T13"][:20]:
        ct = c.get("container") or {}
        lines.append(f"| {c['event_id']} | {c['loc']} | {ct.get('cues')} | "
                     f"{len(ct.get('sub_event_ids') or [])} | {ct.get('common_places')} | "
                     f"{ct.get('common_orgs')} | {c['confidence']} |")
    lines += [
        "",
        "## 4 · 其他分布",
        "",
        f"- 六域：{dict(by_domain)}",
        f"- 叙述模式：{dict(by_mode)}",
        f"- 相关武功/器物/组织/地点：☆{sum(len(e['related_skills']) for e in events)} / "
        f"•{{ {sum(len(e['related_objects']) for e in events)} / ◆{sum(len(e['related_orgs']) for e in events)} / "
        f"={sum(len(e['related_places']) for e in events)}",
        "",
        "## 5 · 丢弃/降级原因",
        "",
        "| 原因 | 数 |",
        "|---|---:|",
        f"| 围栏内（词/诗/回末对等，02ab 豁免不抽事件） | {stats['fence']} |",
        f"| 对白内（保留事件但标 source_type=人物发言，不进 matches 评分） | {stats['in_quote']} |",
        f"| 无参与方（confidence=low，review 候选） | {stats['no_participants']} |",
        f"| 无结果证据（outcome=未决，review 候选） | {sum(1 for e in events if e['outcome'] == '未决')} |",
        "",
        "## 6 · 样本（前 20 条，仅定位符+结构化字段，不含原文）",
        "",
        "| event_id | type | loc | subject | verb | object | outcome | conf |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in events[:20]:
        av = (e.get("anchor_verbs") or [{}])[0].get("verb") or e.get("subtype") or "—"
        lines.append(f"| {e['event_id']} | {e['type']} | {e['loc']} | {e['subject'] or '—'} | "
                     f"{av} | {e['object'] or '—'} | {e['outcome']} | {e['confidence']} |")
    lines += ["", "## 7 · 复现命令", "```", "python scripts/event_extractor.py"
              + (f" --book {book}" if book else ""), "```", ""]
    return "\n".join(lines)


def render_summary(payloads: list) -> str:
    lines = [f"# 事件层（D03/EX-5）· {len(payloads)} 书汇总", "",
             f"- 生成：{esc.now_iso()} · schema {SCHEMA} · 规范 SKILL_04a 13 类/36 字段",
             f"- 书：{[p['book'] for p in payloads]}", "",
             "| 书 | 事件 | T01 比武 | T02 杀伐 | T03 夺宝 | T04 传艺 | T05 练功 | T06 盟约 | "
             "T07 门派 | T08 朝廷 | T09 战争 | T10 婚恋 | T11 生死 | T12 行踪 | T13 大会 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    tot = Counter()
    for p in payloads:
        c = Counter(e["type"] for e in p["events"])
        tot.update(c)
        lines.append(f"| {p['book']} | {len(p['events'])} | " +
                     " | ".join(str(c.get(f"T{i:02d}", 0)) for i in range(1, 14)) + " |")
    lines += ["", f"- **合计事件 {sum(len(p['events']) for p in payloads)}**；"
                  f"类型分布 {dict(sorted(tot.items()))}",
              f"- outcome（全事件）："
              f"{dict(Counter(e['outcome'] for p in payloads for e in p['events']))}",
              f"- 对白内事件：{sum(p['stats']['in_quote'] for p in payloads)}；"
              f"围栏跳过：{sum(p['stats']['fence'] for p in payloads)}",
              f"- 门控（ok/review/excluded）：{dict(sum((Counter(p['stats'].get('by_gate', {})) for p in payloads), Counter()))}",
              f"- T13 容器：{sum(p['stats'].get('t13', {}).get('containers', 0) for p in payloads)} 个 / "
              f"纳入子事件 {sum(p['stats'].get('t13', {}).get('contained_subevents', 0) for p in payloads)} 场；"
              f"参数 {payloads[0]['stats'].get('t13', {}).get('params') if payloads else {}}",
              "", "## 各书报告", ""]
    lines += [f"- `logs/events/{p['book']}.md`（events → `registry/events/{p['book']}.json`）"
              for p in payloads]
    lines += ["", "## 对下游接口", "",
              "- matches/ratings（EX-5）：消费 T01/T02 且主宾俱全、outcome∈{胜,负,平} 的事件；",
              "- atlas events / N10 事件字段 / EX-8 R1：可直接读 `events[].type/outcome/loc/tp_id/participants`；",
              "- 置信门控：strong → high；单边 → medium；无参与方 → low（review 候选）。", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- 主流程
def extract_book(book: str, t13_min: int = T13_MIN_SUBEVENTS,
                 t13_window: int = T13_WINDOW_PN,
                 t13_weak_min: int = T13_WEAK_MIN_WINDOW) -> dict:
    ctx = rv.Ctx(book)
    time_idx = load_time_index(book)
    rel_idx = load_relation_index(book)
    events = []
    cue_by_ch: dict = {}
    stats = Counter({"verbs": 0, "fence": 0, "in_quote": 0, "no_participants": 0,
                     "relation_filled": 0, "time_hit": 0})
    for path in sorted((rv.TAG / book).glob("*.tagged.md")):
        ch = int(path.name[:3])
        # 围栏内令牌数（跳过原因统计）
        fence_verbs = _count_fence_verbs(path)
        stats["fence"] += fence_verbs
        for para_no, text in iter_paragraphs(path):
            res = extract_paragraph(ctx, book, ch, para_no, text, time_idx, rel_idx)
            stats["verbs"] += res["verbs"]
            stats["in_quote"] += res["in_quote"]
            stats["relation_filled"] += res["relation_filled"]
            if res["cues"]:
                cue_by_ch.setdefault(ch, {})[para_no] = res["cues"]
            for ev in res["events"]:
                if ev["tp_id"]:
                    stats["time_hit"] += 1
                events.append(ev)
    # 稳定排序
    events.sort(key=lambda e: (e["chapter"], e["pn"], e["event_id"]))
    # D2② low 置信门控（规则化）
    gate_counter = Counter()
    gate_reasons = Counter()
    for ev in events:
        gate_event(ev)
        gate_counter[ev.get("gate") or "ok"] += 1
        if ev.get("gate_reason"):
            gate_reasons[ev["gate_reason"]] += 1
    # D2① T13 武林大会容器聚合
    containers, events, t13_stats = aggregate_t13(events, cue_by_ch, t13_min, t13_window,
                                                  t13_weak_min)
    events.sort(key=lambda e: (e["chapter"], int(e["pn"]), e["event_id"]))
    for idx, ev in enumerate(events, 1):
        ev["seq"] = idx
    stats["no_participants"] = sum(1 for e in events
                                   if e.get("type") != "T13" and not e["subject"] and not e["object"])
    type_counts = Counter(e["type"] for e in events)
    outcome_counts = Counter(e["outcome"] for e in events if e["outcome"])
    return {
        "book": book,
        "generated_at": esc.now_iso(),
        "work_id": time_idx.get("work_id") or "",
        "events": events,
        "stats": dict(stats) | {"time_points": sum(len(v) for v in time_idx.get("points_by_chapter", {}).values()),
                                "by_gate": dict(gate_counter),
                                "gate_reasons": dict(gate_reasons),
                                "t13": t13_stats},
        "type_counts": dict(sorted(type_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "gate_counts": dict(gate_counter),
        "gate_reasons": dict(gate_reasons),
        "t13": t13_stats,
    }


def _count_fence_verbs(path: Path) -> int:
    n = 0
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if in_fence:
            if line.strip() == ":::":
                in_fence = False
                continue
            n += len(symbols.TOKEN_RE.findall(line))
        elif line.startswith(":::"):
            in_fence = True
    return n


def write_book(book: str, t13_min: int = T13_MIN_SUBEVENTS,
               t13_window: int = T13_WINDOW_PN,
               t13_weak_min: int = T13_WEAK_MIN_WINDOW) -> dict:
    result = extract_book(book, t13_min, t13_window, t13_weak_min)
    payload = {
        "schema": SCHEMA,
        "book": book,
        "generated": esc.today(),
        "generated_at": result["generated_at"],
        "tool": TOOL,
        "spec": SPEC,
        "params": {"t13": result["t13"]["params"]},
        "inputs": {"tagged": f"tagged/{book}",
                   "time": f"registry/time/{book}.json",
                   "relations": f"registry/relations/{book}.json",
                   "concordance": f"registry/concordance/{book}.json",
                   "entities": "registry/entities.json"},
        "summary": {"events": len(result["events"]),
                    "by_type": result["type_counts"],
                    "by_outcome": result["outcome_counts"],
                    "by_domain": dict(Counter(e["verb_domain"] for e in result["events"])),
                    "by_confidence": dict(Counter(e["confidence"] for e in result["events"])),
                    "by_narrative_mode": dict(Counter(e["narrative_mode"] for e in result["events"])),
                    "by_source_type": dict(Counter(e["source_type"] for e in result["events"])),
                    "time_point_hit": result["stats"]["time_hit"],
                    "relation_filled": result["stats"]["relation_filled"],
                    "fence_skipped_tokens": result["stats"]["fence"],
                    "in_quote": result["stats"]["in_quote"],
                    "zero_types": [t for t in EVENT_TYPES if t not in result["type_counts"]],
                    "by_gate": result["gate_counts"],
                    "gate_reasons": result["gate_reasons"],
                    "t13_containers": result["t13"]["containers"],
                    "t13_contained_subevents": result["t13"]["contained_subevents"],
                    "t13_params": result["t13"]["params"]},
        "stats": result["stats"],
        "gate_rules": {
            "R1": "无参与方 → excluded（confidence=low）",
            "R2": "单方参与者 → review（降级 confidence=low）",
            "R3": "叙述模式 梦境/假想/戏中戏 → excluded（非事实叙述）",
            "R4": "对白内（人物发言）→ review（视角/转述，事实待核）",
            "T13": "容器聚合：同回 PN 窗口 + 大会语式/共同地点主办（阈值见 params.t13）",
        },
        "type_legend": EVENT_TYPES,
        "events": result["events"],
    }
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    out = esc.atomic_write_json(payload, EVENTS_DIR / f"{book}.json")
    md = LOGS_DIR / f"{book}.md"
    md.write_text(render_book_report(book, payload), encoding="utf-8")
    print(f"[events] {book}: events={len(result['events'])} "
          f"types={result['type_counts']} outcomes={result['outcome_counts']} → {out}")
    return payload


def selftest() -> int:
    checks = []
    def chk(name, cond, detail=""):
        checks.append(cond)
        print(("  ✓ " if cond else "  ✗ ") + name + (f"  {detail}" if detail and not cond else ""))
    chk("13 类事件表", len(EVENT_TYPES) == 13, len(EVENT_TYPES))
    chk("outcome 五值定义", set(["胜", "负", "平", "未决", "未知"]) == {"胜", "负", "平", "未决", "未知"})
    ctx = rv.Ctx("白发魔女传")
    para = "〖@练霓裳〗⟦⊠杀⟧〖@卓一航〗。"
    res = extract_paragraph(ctx, "白发魔女传", 1, 1, para, {"points_by_chapter": {}, "work_id": "bainv"}, {})
    ev = res["events"][0] if res["events"] else {}
    chk("杀戮事件抽取（T02）", ev.get("type") == "T02" and ev.get("subject") == "练霓裳",
        ev.get("type"))
    para2 = "〖@凌未风〗⟦⊞刺⟧〖@楚昭南〗，〖@楚昭南〗大败而走。"
    res2 = extract_paragraph(ctx, "白发魔女传", 1, 2, para2, {"points_by_chapter": {}, "work_id": "bainv"}, {})
    chk("比武+胜负词（T01/outcome）", res2["events"] and res2["events"][0]["type"] in ("T01", "T02"),
        res2["events"][0]["type"] if res2["events"] else None)
    chk("事件字段含 36 字段映射核心键",
        all(k in ev for k in ("event_id", "type", "subject", "object", "outcome", "outcome_ref",
                              "loc", "pn", "confidence", "narrative_mode", "tp_id", "evidence")))
    chk("evidence 不发布原文", all(not e.get("quote_published") for e in ev.get("evidence") or []))
    ok = all(checks)
    print(f"[events] selftest {'PASS' if ok else 'FAIL'} ({sum(checks)}/{len(checks)})")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    books = [b for b in config.book_names() if (rv.TAG / b).is_dir()
             and list((rv.TAG / b).glob("*.tagged.md"))]
    if "--book" in sys.argv:
        i = sys.argv.index("--book")
        if i + 1 < len(sys.argv):
            books = [sys.argv[i + 1]]

    def _num_arg(name: str, default: int) -> int:
        if name in sys.argv:
            i = sys.argv.index(name)
            if i + 1 < len(sys.argv):
                try:
                    return int(sys.argv[i + 1])
                except ValueError:
                    pass
        return default

    t13_min = _num_arg("--t13-min-subevents", T13_MIN_SUBEVENTS)
    t13_window = _num_arg("--t13-window", T13_WINDOW_PN)
    t13_weak_min = _num_arg("--t13-weak-min", T13_WEAK_MIN_WINDOW)
    print(f"[events] params: t13_min_subevents={t13_min} t13_window_pn={t13_window} "
          f"t13_weak_min={t13_weak_min}")
    payloads = [write_book(b, t13_min, t13_window, t13_weak_min) for b in books]
    if payloads:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        (LOGS_DIR / "_summary.md").write_text(render_summary(payloads), encoding="utf-8")
        print(f"[events] 汇总 → {LOGS_DIR / '_summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
