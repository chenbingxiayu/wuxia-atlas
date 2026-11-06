#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N3 · 动词标注校验器（武侠版）—— 六域白名单 + 消歧 + 嵌套 + 边界 + 密度 + 联动

权威依据（规则逐条对照，详见 docs/_p2/C24-N3-report.md §二）：
  - SKILL_04f §2.0 主域裁决总表 / §2.1-§2.7 六域收词与排除
      → 域码合法性、域混淆启发式（劫人■/劫财⊟、拘押判刑⊡、处死死亡⊠、
        战斗交锋⊞、传习▣、位移■）；
  - SKILL_04f §3.1 触发词边界与"结果决定主域" + §3.5 嵌套禁令
      → 闭合、无嵌套、与实体区间不重叠、触发词不含标点/空白、单字虚词、
        >8 字超长、死/伤结果补语主域提示；
  - SKILL_04f §3.3 消歧语法（一词多域必须消歧、消歧说明非空）
      → 空消歧说明=error；语料内实际多域且未消歧（少数派域）=warning；
        词表内同 surface 多 domain 未消歧=warning（当前 verbs.json 无此类条目，留钩子）；
  - SKILL_04f §4 动词-实体联动（§4.1 总表 27 行 + §4.2 三铁律）
      → 强制档联动实体缺失时给"降级待审"建议（S-LINK-*）；
  - SKILL_04f §6.1 连续交锋合并标注 + G0 附录 B-5 裁决（每段 1-6 处、>10 回查）
      → 分回 V/100 字密度 warning；单段 >10 处触发词 suggestion；
  - SKILL_04f §5.2/§5.4 词表三档与"候选召回器"定位
      → verbs.json 为白名单（域必须一致）、词表外新词候选汇总 topN（info）。

数据契约：
  - 只读 `tagged/<book>/NNN.tagged.md`（不写回、不改 tagged）；实体/动词令牌
    一律 `symbols.TOKEN_RE` / `symbols.parse_token` 解析，脚本内不重写字符类；
  - 路径一律经 config（DIR_TAGGED / DIR_WORDS / DIR_LOGS）；
  - 不调 LLM、不 commit。

输出：`logs/verb_validation/<book>.json` + `.md`（错误/警告/建议分列、分回统计、
Top 问题、词表外新词候选）；`--strict` 有 error 时 exit 1。
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:  # Windows 控制台中文输出（scripts/README 约定 6）
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
except AttributeError:
    pass

import config  # noqa: E402
import symbols  # noqa: E402

# --------------------------------------------------------------------------- #
# 阈值常量 —— 每条注明依据（承 04f §3.1/§3.5/§6.1，可用 "本批实测分位" 校准）
# --------------------------------------------------------------------------- #
# 分回密度阈值（单位：动词触发词 / 100 个剥标正文字符）。
# 依据：本批《白发魔女传》32 回实测（scripts/validate_verb_tagging_wuxia.py 2026-11-04）——
#   全书均值 1.44/V100字、中位 1.42、p10 0.79、p90 2.08、最小 0.46（017 回）、
#   最大 2.17（013 回）。下界 0.50 取在实测最小值附近：整回低于此值说明动词层几乎
#   缺标（04f §6.1 密度异常，须回查该回是否只标了实体），017 回 0.46 会被标出；
#   上界 3.00 ≈ 1.4×实测最大值：只用于捕捉"逐招轰炸"（§6.1 规则 1/4 的回级放大），
#   避免把武打密集的 013/015 回误报。阈值以常量集中，换书后按新书分位重校。
DENSITY_LOW = 0.50
DENSITY_HIGH = 3.00

# 单段触发词数上限：04f §6.1 规则 4"每段 1-6 处正常，>10 处 almost certainly 逐招误标"；
# G0 附录 B-5 裁决采纳（1-6/段，>10 回查）。此处只作 suggestion（提示回查，不判错）。
PARA_HIGH = 10

# 触发词长度上限（字）：04f §3.1"最小连续单位"；§3.2 整词清单最长约 4-5 字
# （"化去内力"4、"废去武功"4），种子词表最长 5 字；>8 字几乎必然吞了宾语/状语
# （§3.1 触发词不吞宾语），故设 8 字为 warning 门槛（本批实测最长 7 字、0 例触发）。
MAX_SURFACE_LEN = 8

# 单字虚词黑名单：04f §3.1"不含主宾语、程度副词、标点"；"了/着/的/地"是体标记/
# 结构助词，不承载事件语义，作独立触发词=标注错误（本批实测 1 处 ⟦⊞着⟧）。
FUNC_WORDS = {"了", "着", "的", "地"}

# 词表域一致性档位（2026-11-04 Lead 校准）：
# verbs.json 仅 165 条且每条只有单一主域，语料中的合法多义（杀/刺/还/断/交换/斩…）
# 会被标出；在词表补 senses 分型前，域冲突默认按 warning（W-WL-DOMAIN），
# 不进入 --strict 硬门；设 --wordlist-strict 时恢复为 error（E-WL-DOMAIN）。
WORDLIST_STRICT = False

# 词表外新词候选：报告展示 topN（04f §5.4 词表是"候选召回器"，新词先入候选池）。
NEW_WORD_TOPN = 50
NEW_WORD_JSON_TOPN = 200

# 结构扫描：三层括号（symbols.BRACKETS 为唯一来源）
OPEN_LAYER = {symbols.BRACKETS[k][0]: k for k in symbols.BRACKETS}
CLOSE_LAYER = {symbols.BRACKETS[k][1]: k for k in symbols.BRACKETS}

PN_RE = re.compile(r"^\[(\d+)\]")
TITLE_PREFIX = "# "
SENT_END_RE = re.compile(r"[。！？；!?;]")
WS_RE = re.compile(r"\s")

# --------------------------------------------------------------------------- #
# 规则表：域混淆启发式（04f §2.0 总表 / §2.1-2.7 排除清单 / §3.3 分型卡）
#   surface 命中 + 同句上下文关键词 → 期望域；标注域不同且未消歧 → suggestion。
# --------------------------------------------------------------------------- #
# 劫夺分流：04f §2.0"劫夺财物→⊟；劫人→■（强制迁移）"（2026-11-04 裁定 P3-⑤）
# 关键词用**子串**匹配（见 ctx_hit）：多字词优先，避免单字误撞（"朱宝椿"的"宝"）。
RULE_ROB = {
    "id": "S-CONF-ROB",
    "title": "劫夺按宾语分流：劫人→■、劫财→⊟（04f §2.0 P3-⑤）",
    "surfaces": {"劫", "打劫", "抢劫", "劫夺", "劫走", "抢", "抢夺", "抢走"},
    "context": [
        ("■", {"带走", "掳", "押走", "绑架", "肉票", "妇人", "女子", "孩子", "小姐",
               "劫人", "捉去", "拉去", "人口"}),
        ("⊟", {"财物", "金银", "珠宝", "银子", "财宝", "箱子", "行李", "货物", "钱财",
               "宝贝", "马匹", "包裹", "包袱", "粮仓", "金马鞍", "银两"}),
    ],
}

# 固定期望域规则（无上下文条件）：surface 语义单一，标注到别域即提示复核。
RULE_DETAIN = {
    "id": "S-CONF-DETAIN",
    "title": "拘押/判刑→⊡（04f §2.3 拘押关系）",
    "surfaces": {"囚", "囚禁", "关押", "拘", "拘禁", "收监", "下狱", "关进", "判", "判刑",
                 "定罪", "监禁"},
    "expected": "⊡",
}
RULE_DEATH = {
    "id": "S-CONF-DEATH",
    "title": "处死/死亡→⊠（04f §2.0/§2.2 生命健康）",
    "surfaces": {"处死", "处决", "正法", "斩首", "凌迟", "问斩", "自尽", "自刎", "身亡",
                 "气绝", "丧命", "毙命", "死亡", "身故"},
    "expected": "⊠",
}
RULE_BATTLE = {
    "id": "S-CONF-BATTLE",
    "title": "战斗交锋→⊞（04f §2.1）",
    "surfaces": {"交手", "过招", "拆招", "斗", "战", "厮杀", "动手", "出手", "迎战",
                 "应战", "挑战", "突围", "格挡", "招架"},
    "expected": "⊞",
    # 语义多义/易混的 surface 需战斗语境佐证（如"突围入川"跨地域可归 ■）；
    # 其余核心交锋词（交手/过招/拆招/斗/战/厮杀）语义单一，直接按 §2.1 判。
    "gated_surfaces": {"动手", "出手", "迎战", "应战", "挑战", "突围", "格挡", "招架"},
    "battle_context": {"交战", "交手", "交锋", "厮杀", "战斗", "打斗", "围攻",
                       "出招", "过招", "战团", "圈外", "恋战"},
}
RULE_TEACH = {
    "id": "S-CONF-TEACH",
    "title": "技术传习→▣（04f §2.5）",
    "surfaces": {"教", "学", "练", "传授", "授艺", "传艺", "传功", "练成", "学会",
                 "悟出", "偷学", "指点", "修习", "研习"},
    "expected": "▣",
    # 单字/易混词（教/学/练/指点…）需技艺语境佐证，避免"指点说道""学者"类误伤
    "gated_surfaces": {"教", "学", "练", "传授", "指点", "修习", "研习"},
    "tech_context": {"武功", "剑法", "掌法", "拳法", "刀法", "内功",
                     "技艺", "心法", "秘诀", "招数", "招式", "练功", "授艺", "传艺",
                     "学艺", "练剑", "学剑", "教剑", "传授", "师父", "徒弟"},
}
RULE_CURE = {
    "id": "S-CONF-CURE",
    "title": "治疗/中毒→⊠（04f §2.2）",
    "surfaces": {"疗伤", "治伤", "救活", "救治", "解毒", "下毒", "投毒", "毒发", "中毒"},
    "expected": "⊠",
}
# 位移：行程级→■（§2.6）；战斗现场的脱离/追击→⊞（§2.1 分流）。
# 高风险单字（走/逃/退/追/跑）只在**战斗短语**佐证时才提示 ⊞，否则单字动作语境
# 太泛（"跑了一阵"""提剑追时"），会制造大量误报。
RULE_MOVE = {
    "id": "S-CONF-MOVE",
    "title": "行程级位移→■；战斗现场脱离/追击→⊞（04f §2.1/§2.6）",
    "surfaces": {"抵达", "到达", "来到", "离开", "押解", "押送", "潜入", "混入",
                 "迁居", "移居", "逃亡", "远遁", "走", "逃", "退", "追", "跑"},
    "expected": "■",
    "fixed_surfaces": {"抵达", "到达", "来到", "离开", "押解", "押送", "潜入", "混入",
                       "迁居", "移居", "逃亡", "远遁"},
    "battle_context": {"交战", "交手", "交锋", "厮杀", "战斗", "打斗", "围攻",
                       "出招", "过招", "战团", "圈外", "恋战", "逃命", "败走",
                       "追敌"},
    "battle_expected": "⊞",
    "battle_surfaces": {"走", "逃", "退", "追", "跑"},
}

# 姿态/身法不入行程或战斗（04f §2.1 排除、§2.6 排除；V1-2/V6-1 错误模式）
POSTURE = {"跳出", "跃出", "纵身", "闪过", "退步", "掠出", "疾退", "滚出", "跃上",
           "纵起", "跃起"}
# 施用已会武功不重复标 ▣（04f §2.5 排除、V5-1）
USAGE = {"使出", "施用", "使用"}
# "结果决定主域"⊠ 补语（04f §3.1 速查表）
DEATH_RESULT_SURFACES = {"斩", "杀", "劈", "刺", "打", "击", "震"}
DEATH_RESULT_WORDS = {"死", "两截", "毙", "气绝", "断气", "丧命", "身首", "归天"}

# 联动强制档（04f §4.1 总表；仅取高置信、上下位类型明确的行，避免误伤）
LINK_RULES = [
    {"id": "S-LINK-ART", "title": "传习类强制联动 ☆武功技艺（04f §4.1 #1-#4）",
     "surfaces": {"练成", "学会", "悟出", "参透", "领悟", "偷学", "传授", "授艺",
                  "传艺", "传功", "指点"},
     "entity_codes": {"☆"}},
    {"id": "S-LINK-PERSON", "title": "生命健康类强制联动 @人物（04f §4.1 #8-#10）",
     "surfaces": {"杀", "杀死", "斩杀", "击毙", "处死", "毒杀", "害命", "刺死",
                  "疗伤", "治伤", "救活", "救治", "解毒", "下毒", "投毒"},
     "entity_codes": {"@"}},
    {"id": "S-LINK-OBJ", "title": "物件转移/毁损强制联动 •器物 或 {文书（04f §4.1 #11-#15）",
     "surfaces": {"赠", "赠送", "相赠", "借给", "归还", "退还", "夺得", "抢走",
                  "窃取", "缴获", "买下", "卖给", "偷", "折断", "烧毁", "焚毁"},
     "entity_codes": {"•", "{"}},
    {"id": "S-LINK-REL", "title": "关系类强制联动 @人物（04f §4.1 #6/#19/#20）",
     "surfaces": {"拜师", "收徒", "娶", "嫁", "成亲", "结义", "结拜"},
     "entity_codes": {"@"}},
    {"id": "S-LINK-PLACE", "title": "行程类强制联动 =地点（04f §4.1 #21-#24）",
     "surfaces": {"抵达", "到达", "来到", "离开", "押解", "押送", "潜入", "混入"},
     "entity_codes": {"="}},
]

# 规则依据索引（JSON/MD 报告用）
RULE_SPEC = {
    "E-DOMAIN": "SKILL_04f §2.0 / SKILL_01g §2.2.3（6 域定版）",
    "E-UNCLOSED": "SKILL_04f §3.5 / 01g §3.1（令牌闭合）",
    "E-CLOSE-MISMATCH": "SKILL_04f §3.5（括号配对）",
    "E-NESTED": "SKILL_04f §3.5（嵌套禁令）",
    "E-OVERLAP": "SKILL_04f §3.5（实体名内不得拆动词 / 同一字符不双标）",
    "E-PUNCT": "SKILL_04f §3.1（触发词不含标点/空白）",
    "W-FUNC": "SKILL_04f §3.1（最小连续单位，虚词不承载事件）",
    "E-EMPTY-SURFACE": "SKILL_04f §3.3（触发词不得为空）",
    "E-DISAMBIG-EMPTY": "SKILL_04f §3.3（消歧说明必须非空）",
    "E-WL-DOMAIN": "SKILL_04f §5.2/§5.4（词表白名单域必须一致）",
    "W-WL-DOMAIN": "SKILL_04f §5.2/§5.4（词表主域仅参考；补 senses 分型前降级 warning）",
    "W-LONG": "SKILL_04f §3.1/§3.2（触发词不吞宾语/状语，>8 字复核）",
    "W-MULTIDOMAIN": "SKILL_04f §3.3（一词多域必须消歧）",
    "W-DENSITY": "SKILL_04f §6.1 + G0 附录 B-5（分回 V/100 字异常）",
    "S-CONF-ROB": "SKILL_04f §2.0 劫夺分流（P3-⑤）",
    "S-CONF-DETAIN": "SKILL_04f §2.3 拘押关系",
    "S-CONF-DEATH": "SKILL_04f §2.0/§2.2 生命健康",
    "S-CONF-BATTLE": "SKILL_04f §2.1 战斗交锋",
    "S-CONF-TEACH": "SKILL_04f §2.5 技术传习",
    "S-CONF-CURE": "SKILL_04f §2.2 治疗/中毒",
    "S-CONF-MOVE": "SKILL_04f §2.6 行踪迁移 / §2.1 脱离分流",
    "S-CONF-RESULT": "SKILL_04f §3.1 结果决定主域",
    "S-POSTURE": "SKILL_04f §2.1/§2.6 排除清单（V1-2/V6-1）",
    "S-USAGE": "SKILL_04f §2.5 排除清单（V5-1）",
    "S-PARA-DENSITY": "SKILL_04f §6.1 规则 4（每段 1-6 处、>10 回查）",
    "S-LINK-ART": "SKILL_04f §4.1 #1-#4 + §4.2 铁律 2",
    "S-LINK-PERSON": "SKILL_04f §4.1 #8-#10 + §4.2 铁律 2",
    "S-LINK-OBJ": "SKILL_04f §4.1 #11-#15 + §4.2 铁律 2",
    "S-LINK-REL": "SKILL_04f §4.1 #6/#19/#20 + §4.2 铁律 2",
    "S-LINK-PLACE": "SKILL_04f §4.1 #21-#24 + §4.2 铁律 2",
    "I-NEW-WORD": "SKILL_04f §5.2/§5.4 词表外候选召回",
}


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def parse_chapters(spec: str | None, available: list[int]) -> list[int]:
    """解析回号过滤表达式；非法输入给友好 SystemExit（不抛裸 ValueError）。

    支持 `all`/`None`（全部）与 `1-5,7,10-12`。以下输入显式报错：
    空段（如 `1,,2`/尾随逗号）、非数字回号（`a`）、非法区间（`1-abc`/`a-b`）、
    起止倒置（`8-5`）与 0/负数回号——均给一行可操作的提示，便于 pipeline 调用时定位。
    """
    if not spec or spec.strip().lower() == "all":
        return list(available)
    out: list[int] = []
    for i, part in enumerate(spec.split(","), 1):
        part = part.strip()
        if not part:
            raise SystemExit(
                f"✗ --chapters 第 {i} 段为空；示例：1-5,7,10-12（或 all）")
        if "-" in part:
            a, b = (x.strip() for x in part.split("-", 1))
            if not (a.isdigit() and b.isdigit()):
                raise SystemExit(
                    f"✗ --chapters 非法区间 {part!r}；只接受“正整数-正整数”，如 1-5")
            lo, hi = int(a), int(b)
            if lo <= 0 or hi <= 0:
                raise SystemExit(f"✗ --chapters 回号必须为正整数：{part!r}")
            if lo > hi:
                raise SystemExit(
                    f"✗ --chapters 区间起止倒置 {part!r}；应写 {hi}-{lo}")
            out.extend(range(lo, hi + 1))
        else:
            if not part.isdigit():
                raise SystemExit(
                    f"✗ --chapters 非法回号 {part!r}；只接受正整数，如 1,3,5")
            n = int(part)
            if n <= 0:
                raise SystemExit(f"✗ --chapters 回号必须为正整数：{part!r}")
            out.append(n)
    if not out:
        raise SystemExit("✗ --chapters 未解析出任何回号；示例：1-5,7（或 all）")
    return sorted(set(out))


def load_wordlist() -> dict:
    """载入 verbs.json → {path, meta, items, by_surface, multi_domain_surfaces}。

    task-12 补充：兼容顶层为 list 的词表（旧 schema/手工表），避免 `data.get` 的
    AttributeError；list 形式无 meta，按空 meta 处理，条目字段仍按 surface/domain 读取。
    """
    path = config.DIR_WORDLISTS / "verbs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        items, meta = data, {}
    elif isinstance(data, dict):
        items, meta = data.get("items", []), data.get("meta", {})
    else:
        print(f"⚠ 词表顶层结构异常（{type(data).__name__}）{path}；按空词表继续")
        items, meta = [], {}
    by_surface: dict[str, dict] = {}
    domain_of: dict[str, set] = defaultdict(set)
    for it in items:
        surface = (it.get("surface") or "").strip()
        if not surface:
            continue
        by_surface[surface] = it
        domain_of[surface].add(it.get("domain") or it.get("type"))
    multi = {s: sorted(d for d in ds if d) for s, ds in domain_of.items() if len(ds) > 1}
    # docs/70 §七：同 surface 多 senses 条目（P4 回写形态）→ 域集合整体合法
    return {"path": str(path), "meta": meta, "items": items,
            "domains_by_surface": {s: set(ds) for s, ds in domain_of.items()},
            "by_surface": by_surface, "multi_domain_surfaces": multi,
            "surface_count": len(by_surface)}


def pn_anchor(book: str, chapter: int, para: int | None) -> str | None:
    if para is None or para <= 0:
        return None
    return symbols.ANCHOR_FMT.format(book=book, chapter=chapter, para=para)


def split_sentence(line: str, pos: int) -> str:
    """取 token 所在句（按 。！？； 切分；无标点则整行）。"""
    bounds = [0]
    for m in SENT_END_RE.finditer(line):
        bounds.append(m.end())
    bounds.append(len(line))
    for i in range(1, len(bounds)):
        if bounds[i - 1] <= pos < bounds[i]:
            return line[bounds[i - 1]:bounds[i]]
    return line


def norm_text(sentence: str) -> str:
    """剥标后的上下文文本（关键词匹配用，避免实体/动词标记干扰）。"""
    return symbols.strip_markup(sentence)


def ctx_hit(ctx: str, keywords) -> bool:
    """上下文关键词命中：**子串**匹配（多字词优先），避免单字误撞（如人名含"宝"）。"""
    return any(kw in ctx for kw in keywords)


def make_issue(level: str, category: str, chapter: int, pn: int | None,
               token: str, message: str, **extra) -> dict:
    issue = {
        "level": level,
        "category": category,
        "chapter": f"{chapter:03d}",
        "pn": pn,
        "anchor": pn_anchor(extra.pop("book", ""), chapter, pn),
        "token": token,
        "message": message,
        "rule": RULE_SPEC.get(category, ""),
    }
    issue.update(extra)
    return issue


# --------------------------------------------------------------------------- #
# 结构扫描（闭合 / 嵌套 / 与实体区间重叠）——不依赖 TOKEN_RE 的单遍括号栈
# --------------------------------------------------------------------------- #
def scan_structure(text: str) -> dict:
    """扫描全文三层括号 → spans 与结构问题。

    即使存在嵌套/错配也尽量产出 span，供重叠检测使用；结构问题按类别聚合。
    错配（closing 与栈顶不同层）时：若栈内找不到同层开括号，先把栈内所有未闭合项
    记为 unclosed 并清空栈，避免残留开括号对后续闭合产生级联误配（task-12 修复）。
    """
    stack: list[tuple[str, int]] = []       # (layer, pos)
    spans: list[dict] = []
    issues: list[dict] = []
    for pos, ch in enumerate(text):
        opening = OPEN_LAYER.get(ch)
        closing = CLOSE_LAYER.get(ch)
        if opening:
            if stack:                       # 任何层内再开标注 = 嵌套（§3.5）
                issues.append({"kind": "nested", "pos": pos,
                               "outer": stack[-1][0], "inner": opening})
            stack.append((opening, pos))
        elif closing:
            if not stack:
                issues.append({"kind": "unmatched_close", "pos": pos, "layer": closing})
                continue
            if stack[-1][0] == closing:
                layer, start = stack.pop()
                spans.append({"layer": layer, "start": start, "end": pos + 1,
                              "text": text[start:pos + 1]})
            else:
                issues.append({"kind": "mismatch", "pos": pos, "layer": closing,
                               "open": stack[-1][0]})
                idx = next((k for k in range(len(stack) - 1, -1, -1)
                            if stack[k][0] == closing), None)
                if idx is None:
                    # 栈内无同层开括号：把所有未闭合开括号一次性记清后清栈，
                    # 否则残留开括号会让后续闭合被“错配/吞并”，产生假 span 级联。
                    for layer, start in stack:
                        issues.append({"kind": "unclosed", "pos": start,
                                       "layer": layer})
                    stack.clear()
                    continue
                for k in range(len(stack) - 1, idx, -1):
                    issues.append({"kind": "unclosed", "pos": stack[k][1],
                                   "layer": stack[k][0]})
                layer, start = stack.pop(idx)
                spans.append({"layer": layer, "start": start, "end": pos + 1,
                              "text": text[start:pos + 1]})
    for layer, start in stack:
        issues.append({"kind": "unclosed", "pos": start, "layer": layer})
    return {"spans": spans, "issues": issues}


def find_overlaps(spans: list[dict]) -> list[dict]:
    """动词 span 与实体 span 的交叉重叠（包含关系已由嵌套扫描覆盖）。"""
    verb_spans = [s for s in spans if s["layer"] == "verb"]
    ent_spans = [s for s in spans if s["layer"] == "entity"]
    out = []
    for v in verb_spans:
        for e in ent_spans:
            if v["start"] < e["end"] and e["start"] < v["end"]:
                contained = (v["start"] < e["start"] and e["end"] < v["end"]) or (
                    e["start"] < v["start"] and v["end"] < e["end"])
                if not contained:
                    out.append({"verb": v["text"], "entity": e["text"],
                                "start": v["start"]})
    return out


# --------------------------------------------------------------------------- #
# 逐回分析
# --------------------------------------------------------------------------- #
def analyze_chapter(book: str, ch: int) -> dict:
    """单回：结构扫描 + 动词令牌抽取 + 分回字数/密度（不做全局多域判定）。"""
    path = config.tagged_path(book, ch)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    structure = scan_structure(text)
    overlaps = find_overlaps(structure["spans"])
    structural_issues: list[dict] = []
    for issue in structure["issues"]:
        if issue["kind"] == "nested":
            cat = "E-NESTED"
            msg = (f"嵌套标注：{issue['inner']} 置于 {issue['outer']} 内"
                   f"（{issue['outer']} 内不得包含任何标注）")
        elif issue["kind"] == "unclosed":
            cat = "E-UNCLOSED"
            msg = f"未闭合的 {issue['layer']} 括号（open pos={issue['pos']}）"
        elif issue["kind"] == "mismatch":
            cat = "E-CLOSE-MISMATCH"
            msg = f"括号错配：闭合 {issue['layer']} 时栈顶为 {issue['open']}"
        else:
            cat = "E-UNCLOSED"
            msg = f"多余的闭合括号（{issue['layer']}，pos={issue['pos']}）"
        structural_issues.append({"category": cat, "message": msg,
                                  "pos": issue["pos"], "token": ""})
    for ov in overlaps:
        structural_issues.append({
            "category": "E-OVERLAP",
            "message": f"动词区间与实体区间交叉重叠：{ov['verb']} ∩ {ov['entity']}",
            "pos": ov["start"], "token": ov["verb"]})

    # 逐行抽动词令牌：行内 PN 推锚点；[0] 回目不计正文段（沿用上一段逻辑）
    tokens: list[dict] = []
    line_list = lines
    cur_pn: int | None = None
    chars = 0
    for line_no, line in enumerate(line_list, 1):
        if line.startswith(TITLE_PREFIX):
            cur_pn = 0
        elif symbols.fence_opens(line) or symbols.is_fence_close(line):
            continue
        else:
            m = PN_RE.match(line)
            if m:
                cur_pn = int(m.group(1))
            # 剥标正文字数（分母）：正文/韵文内容计入，回目与围栏标记行不计
            chars += len(WS_RE.sub("", symbols.strip_markup(line)))
        if cur_pn is None:
            continue
        for tm in symbols.TOKEN_RE.finditer(line):
            layer, code, body, display, note, err = symbols.parse_token(tm.group(0))
            if layer != "verb":
                continue
            tokens.append({
                "chapter": ch, "pn": cur_pn, "line": line_no,
                "token": tm.group(0), "body": body, "code": code,
                "surface": (display or "").strip(), "note": note,
                "pipe": "|" in body, "err": err, "pos": tm.start(),
                "line_text": line,
            })
    return {"chapter": ch, "tokens": tokens, "chars": chars,
            "structural": structural_issues, "path": str(path)}


# --------------------------------------------------------------------------- #
# 全局规则判定
# --------------------------------------------------------------------------- #
def check_tokens(chapter_data: dict, wordlist: dict, book: str) -> dict:
    """全局后处理：并入跨回的多域信息、新词候选、联动/启发式判定。"""
    all_tokens: list[dict] = []
    for cd in chapter_data.values():
        all_tokens.extend(cd["tokens"])

    # 语料内实际多域统计（用于"一词多域未消歧"）：surface → Counter(domain)
    surf_domains: dict[str, Counter] = defaultdict(Counter)
    for t in all_tokens:
        if t["code"] and not t["err"] and t["surface"]:
            surf_domains[t["surface"]][t["code"]] += 1
    obs_multi = {s: c for s, c in surf_domains.items() if len(c) > 1}

    errors: list[dict] = []
    warnings: list[dict] = []
    suggestions: list[dict] = []
    new_words: dict[str, dict] = {}

    def add(level, category, t, message, **extra):
        issue = make_issue(level, category, t["chapter"], t["pn"],
                           t["token"], message, book=book,
                           surface=t.get("surface"), domain=t.get("code"), **extra)
        (errors if level == "error" else warnings if level == "warning"
         else suggestions).append(issue)

    # 结构问题按回并入 errors（无令牌语义，单独构造）
    for ch, cd in chapter_data.items():
        for si in cd["structural"]:
            anchor = pn_anchor(book, ch, None)
            errors.append({
                "level": "error", "category": si["category"],
                "chapter": f"{ch:03d}", "pn": None, "anchor": anchor,
                "token": si.get("token", ""),
                "message": si["message"] + f"（回 {ch:03d}，pos={si['pos']}）",
                "rule": RULE_SPEC.get(si["category"], ""),
            })

    for t in all_tokens:
        surface = t["surface"]
        code = t["code"]
        note = t["note"]
        err = t["err"]
        # a1 域码合法性（symbols.parse_token 已校验；err 信息原样上报）
        if err is not None or not code or code not in symbols.VERB_CODES:
            add("error", "E-DOMAIN", t,
                f"动词域码非法：{err or ('空/未知码 ' + repr(code))}")
            continue
        # a2 触发词非空
        if not surface:
            add("error", "E-EMPTY-SURFACE", t, "触发词显示串为空（⟦码|说明⟧ 缺动词）")
            continue
        # d1 边界：标点/空白（只看显示串；消歧说明允许标点，04f §3.3）
        if re.search(r"[\s　，。？！、：；\"'“”‘’「」『』【】《》〈〉·…—～()（）\-！？,.;:]",
                     surface):
            add("error", "E-PUNCT", t,
                f"触发词含标点/空白：{surface!r}（标点应外置，04f §3.1）")
        # d2 单字虚词：按 warning 提示（04f §3.1 虚词不承载事件），但白话中
        #    "着了一下"（中着）等用法可能具实义，交人工复核而非直接判错。
        if surface in FUNC_WORDS:
            add("warning", "W-FUNC", t,
                f"单字虚词/体标记作触发词：{surface}（04f §3.1 不承载事件）；"
                f"若为白话实义用法（如「着了一下」）请消歧或改标完整动词")
        # d3 超长
        if len(surface) > MAX_SURFACE_LEN:
            add("warning", "W-LONG", t,
                f"触发词 {len(surface)} 字 > {MAX_SURFACE_LEN}：疑似吞宾语/状语"
                f"（04f §3.1 触发词不吞宾语）")
        # c1 管道消歧说明非空
        if t["pipe"] and not (note or "").strip():
            add("error", "E-DISAMBIG-EMPTY", t,
                f"消歧管道为空：{t['token']}（⟦域 动词|说明⟧ 说明不得为空，04f §3.3）")
        # b 白名单：verbs.json 域必须一致（04f §5.2/§5.4）
        #   默认 warning（词表单主域，多义合法）；--wordlist-strict 恢复 error。
        item = wordlist["by_surface"].get(surface)
        if item is not None:
            wl_domain = item.get("domain") or item.get("type")
            domains_all = wordlist.get("domains_by_surface", {}).get(surface, {wl_domain})
            if wl_domain != code and code not in domains_all:
                level = "error" if WORDLIST_STRICT else "warning"
                category = "E-WL-DOMAIN" if WORDLIST_STRICT else "W-WL-DOMAIN"
                add(level, category, t,
                    f"词表域冲突：{surface} 词表主域 {wl_domain}"
                    f"（{item.get('domain_name', '')}，tier={item.get('tier')}），"
                    f"实际标 {code}；若属多义用法应在 verbs_source.json 补 senses 分型"
                    + ("（当前按 warning，--wordlist-strict 可恢复 error）"
                       if not WORDLIST_STRICT else ""),
                    wordlist_domain=wl_domain, has_note=bool((note or "").strip()))
        # c2 多域未消歧：
        #    (i) 词表同 surface 多 domain（当前 verbs.json 无，留钩子）
        #    (ii) 语料内同 surface 出现 ≥2 域，本处落在少数派域且无消歧说明 → warning
        if surface in wordlist["multi_domain_surfaces"] and not (note or "").strip():
            add("warning", "W-MULTIDOMAIN", t,
                f"词表内一词多域未消歧：{surface} 词表域 "
                f"{'/'.join(wordlist['multi_domain_surfaces'][surface])}")
        elif surface in obs_multi:
            dom_counter = obs_multi[surface]
            major, major_n = dom_counter.most_common(1)[0]
            if not (note or "").strip() and code != major:
                doms = "、".join(f"{d}×{n}" for d, n in dom_counter.most_common())
                add("warning", "W-MULTIDOMAIN", t,
                    f"多域未消歧：{surface} 全书分布 [{doms}]，本处标 {code}"
                    f"（少数派域），建议补 ⟦{code}{surface}|说明⟧",
                    observed_domains=doms, major_domain=major,
                    major_count=major_n)
        # f 域混淆启发式（未消歧时给建议；已消歧尊重标注者判断）
        if not (note or "").strip():
            sentence = split_sentence(t["line_text"], t["pos"])
            ctx = norm_text(sentence)
            matched = False
            for rule in (RULE_DETAIN, RULE_DEATH, RULE_BATTLE, RULE_TEACH, RULE_CURE):
                if surface not in rule["surfaces"] or code == rule["expected"]:
                    continue
                if rule is RULE_BATTLE and surface in rule.get("gated_surfaces", set()):
                    if not ctx_hit(ctx, rule["battle_context"]):
                        continue
                if rule is RULE_TEACH and surface in rule.get("gated_surfaces", set()):
                    if not ctx_hit(ctx, rule["tech_context"]):
                        continue
                add("suggestion", rule["id"], t,
                    f"{rule['title']}：{surface} 标 {code}，建议 {rule['expected']}；"
                    f"上下文「{ctx[:40]}」", expected=rule["expected"])
                matched = True
                break
            if not matched and surface in RULE_ROB["surfaces"]:
                expected = None
                for dom, keywords in RULE_ROB["context"]:
                    if ctx_hit(ctx, keywords):
                        expected = dom
                        break
                if expected and code != expected:
                    add("suggestion", RULE_ROB["id"], t,
                        f"{RULE_ROB['title']}：{surface} 标 {code}，同句宾语线索建议 "
                        f"{expected}；上下文「{ctx[:40]}」", expected=expected)
                    matched = True
            if not matched and surface in RULE_MOVE["surfaces"]:
                battle = ctx_hit(ctx, RULE_MOVE["battle_context"])
                if surface in RULE_MOVE["battle_surfaces"]:
                    # 单字动作词：仅战斗短语佐证时才提示 ⊞（否则语境过泛）
                    if battle and code != RULE_MOVE["battle_expected"]:
                        add("suggestion", RULE_MOVE["id"], t,
                            f"{RULE_MOVE['title']}：{surface} 标 {code}，同句为战斗语境，"
                            f"建议 {RULE_MOVE['battle_expected']}/不标；"
                            f"上下文「{ctx[:40]}」",
                            expected=RULE_MOVE["battle_expected"])
                elif surface in RULE_MOVE["fixed_surfaces"] and code != RULE_MOVE["expected"]:
                    add("suggestion", RULE_MOVE["id"], t,
                        f"{RULE_MOVE['title']}：{surface} 标 {code}，建议 "
                        f"{RULE_MOVE['expected']}；上下文「{ctx[:40]}」",
                        expected=RULE_MOVE["expected"])
            # 姿态/身法排除
            if surface in POSTURE and code in {"■", "⊞"}:
                add("suggestion", "S-POSTURE", t,
                    f"姿态/身法词 {surface} 标 {code}：04f §2.1/§2.6 排除清单，"
                    f"建议不标（战斗中身法）或仅标战斗脱离")
            # 施用已会武功不重复标 ▣
            if surface in USAGE and code == "▣":
                add("suggestion", "S-USAGE", t,
                    f"施用已会武功 {surface} 不应标 ▣（04f §2.5 排除，V5-1），"
                    f"建议改标 ⊞ 或不标")
            # 结果决定主域：⊞ 动作 + 死亡结果 → ⊠
            if code == "⊞" and surface in DEATH_RESULT_SURFACES:
                if ctx_hit(ctx, DEATH_RESULT_WORDS):
                    add("suggestion", "S-CONF-RESULT", t,
                        f"结果决定主域：{surface} 标 ⊞ 但同句见死亡/致害结果，"
                        f"建议 ⊠（04f §3.1）")
            # 联动强制档缺失（同句须有对应实体类型）
            for rule in LINK_RULES:
                if surface not in rule["surfaces"]:
                    continue
                raw_ent_codes = set()
                for em in symbols.TOKEN_RE.finditer(sentence):
                    l2, c2, _b2, _d2, _n2, e2 = symbols.parse_token(em.group(0))
                    if l2 == "entity" and e2 is None:
                        raw_ent_codes.add(c2)
                if not (raw_ent_codes & rule["entity_codes"]):
                    want = "/".join(sorted(rule["entity_codes"]))
                    add("suggestion", rule["id"], t,
                        f"强制联动实体缺失：{surface} 同句未见 {want} 类实体——"
                        f"事件应降级待审（04f §4.2 铁律 2）；上下文「{ctx[:40]}」",
                        expected_entity=want)
                break
        # info：词表外新词候选（跨回汇总，JSON/MD 取 topN）
        if surface not in wordlist["by_surface"]:
            nw = new_words.get(surface)
            if nw is None:
                nw = new_words[surface] = {
                    "surface": surface, "count": 0, "domains": Counter(),
                    "chapters": set(), "first": None, "examples": [],
                }
            nw["count"] += 1
            nw["domains"][code] += 1
            nw["chapters"].add(f"{t['chapter']:03d}")
            if nw["first"] is None and t["pn"] and t["pn"] > 0:
                nw["first"] = {"chapter": t["chapter"], "pn": t["pn"],
                               "anchor": pn_anchor(book, t["chapter"], t["pn"])}
            if len(nw["examples"]) < 2:
                nw["examples"].append({"token": t["token"], "context": t["line_text"][
                    max(0, t["pos"] - 25):t["pos"] + 40]})

    return {"errors": errors, "warnings": warnings, "suggestions": suggestions,
            "new_words": new_words, "observed_multi_domains": obs_multi}


# --------------------------------------------------------------------------- #
# 汇总与报告
# --------------------------------------------------------------------------- #
def build_result(book: str, chapters: list[int], chapter_data: dict,
                 checked: dict, wordlist: dict) -> dict:
    errors = checked["errors"]
    warnings = checked["warnings"]
    suggestions = checked["suggestions"]

    # 分回统计
    rows = []
    total_v = 0
    total_chars = 0
    for ch in chapters:
        cd = chapter_data.get(ch)
        if cd is None:
            rows.append({"chapter": f"{ch:03d}", "missing": True})
            continue
        v = len(cd["tokens"])
        chars = cd["chars"]
        total_v += v
        total_chars += chars
        rows.append({"chapter": f"{ch:03d}", "verbs": v, "chars": chars,
                     "density": None, "errors": 0, "warnings": 0, "suggestions": 0})
    baseline = (total_v * 100 / total_chars) if total_chars else 0.0
    row_by_ch = {r["chapter"]: r for r in rows if not r.get("missing")}

    def ch_key(issue):
        return issue["chapter"]

    for issue in errors:
        row_by_ch.get(ch_key(issue), {})["errors"] = \
            row_by_ch.get(ch_key(issue), {}).get("errors", 0) + 1
    for issue in warnings:
        row_by_ch.get(ch_key(issue), {})["warnings"] = \
            row_by_ch.get(ch_key(issue), {}).get("warnings", 0) + 1
    for issue in suggestions:
        row_by_ch.get(ch_key(issue), {})["suggestions"] = \
            row_by_ch.get(ch_key(issue), {}).get("suggestions", 0) + 1

    for r in rows:
        if r.get("missing"):
            continue
        r["density"] = round(r["verbs"] * 100 / r["chars"], 3) if r["chars"] else None
        r["density_flag"] = None
        if r["density"] is not None:
            if r["density"] < DENSITY_LOW:
                r["density_flag"] = "low"
            elif r["density"] > DENSITY_HIGH:
                r["density_flag"] = "high"
            if r["density_flag"]:
                warnings.append({
                    "level": "warning", "category": "W-DENSITY",
                    "chapter": r["chapter"], "pn": None,
                    "anchor": pn_anchor(book, int(r["chapter"]), None),
                    "token": "", "surface": "",
                    "domain": "",
                    "message": (f"分回密度异常：{r['density']:.3f} V/100字"
                                f"（阈值 {DENSITY_LOW}–{DENSITY_HIGH}，"
                                f"全书基线 {baseline:.3f}）"
                                + ("——整回动词层可能缺标" if r["density_flag"] == "low"
                                   else "——疑似逐招轰炸（04f §6.1）")),
                    "rule": RULE_SPEC["W-DENSITY"],
                    "density": r["density"], "baseline": round(baseline, 3),
                })
                r["warnings"] += 1

    # 单段触发词 >10 处（04f §6.1 规则 4）→ suggestion
    for ch in chapters:
        cd = chapter_data.get(ch)
        if cd is None:
            continue
        per_pn = Counter(t["pn"] for t in cd["tokens"] if t["pn"] and t["pn"] > 0)
        for pn, count in per_pn.items():
            if count > PARA_HIGH:
                suggestions.append({
                    "level": "suggestion", "category": "S-PARA-DENSITY",
                    "chapter": f"{ch:03d}", "pn": pn,
                    "anchor": pn_anchor(book, ch, pn),
                    "token": "", "surface": "", "domain": "",
                    "message": (f"单段触发词 {count} 处 > {PARA_HIGH}：疑似逐招误标，"
                                f"请按 04f §6.1 合并标注回查"),
                    "rule": RULE_SPEC["S-PARA-DENSITY"],
                    "para_verbs": count,
                })
                row_by_ch[f"{ch:03d}"]["suggestions"] += 1

    new_word_list = []
    for surface, nw in sorted(checked["new_words"].items(),
                              key=lambda kv: (-kv[1]["count"], kv[0])):
        new_word_list.append({
            "surface": surface,
            "count": nw["count"],
            "domains": dict(nw["domains"]),
            "chapters": sorted(nw["chapters"]),
            "chapter_count": len(nw["chapters"]),
            "first": nw["first"],
            "examples": nw["examples"],
        })

    def by_category(items):
        c = Counter(i["category"] for i in items)
        return [{"category": k, "count": v, "rule": RULE_SPEC.get(k, "")}
                for k, v in c.most_common()]

    offending = Counter()
    for issue in errors + warnings + suggestions:
        if issue.get("surface"):
            offending[(issue["category"], issue["surface"])] += 1
    top_offending = [{"category": c, "surface": s, "count": n}
                     for (c, s), n in offending.most_common(20)]
    chapter_issue_counts = Counter(i["chapter"] for i in errors + warnings + suggestions)

    structural = {
        "nested": sum(1 for e in errors if e["category"] == "E-NESTED"),
        "unclosed": sum(1 for e in errors if e["category"] == "E-UNCLOSED"),
        "mismatch": sum(1 for e in errors if e["category"] == "E-CLOSE-MISMATCH"),
        "overlap": sum(1 for e in errors if e["category"] == "E-OVERLAP"),
    }

    return {
        "book": book,
        "generated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "spec_version": symbols.SPEC_VERSION,
        "source": (f"tagged/{book}/NNN.tagged.md（只读）；"
                   f"wordlists/verbs.json（白名单）"),
        "chapters": chapters,
        "chapter_count": len([c for c in chapters if c in chapter_data]),
        "missing_chapters": [c for c in chapters if c not in chapter_data],
        "wordlist": {
            "path": wordlist["path"],
            "schema": wordlist["meta"].get("schema"),
            "generated": wordlist["meta"].get("generated"),
            "spec_version": wordlist["meta"].get("spec_version"),
            "totals": wordlist["meta"].get("totals"),
            "surface_count": wordlist["surface_count"],
            "multi_domain_surfaces": wordlist["multi_domain_surfaces"],
        },
        "constants": {
            "DENSITY_LOW": DENSITY_LOW,
            "DENSITY_HIGH": DENSITY_HIGH,
            "PARA_HIGH": PARA_HIGH,
            "MAX_SURFACE_LEN": MAX_SURFACE_LEN,
            "FUNC_WORDS": sorted(FUNC_WORDS),
            "NEW_WORD_TOPN": NEW_WORD_TOPN,
            "basis": ("本批《白发魔女传》32 回实测：V/100字 均值 1.44、中位 1.42、"
                      "p10 0.79、p90 2.08、min 0.46、max 2.17；"
                      "详见 docs/_p2/C24-N3-report.md §八"),
        },
        "baseline": {"verb_tokens": total_v, "chars": total_chars,
                     "density_per_100": round(baseline, 4)},
        "summary": {
            "verb_tokens": total_v,
            "errors": len(errors),
            "warnings": len(warnings),
            "suggestions": len(suggestions),
            "info_new_word_candidates": len(new_word_list),
            "info_new_word_tokens": sum(n["count"] for n in new_word_list),
            "structural": structural,
            "by_category": {
                "errors": by_category(errors),
                "warnings": by_category(warnings),
                "suggestions": by_category(suggestions),
            },
        },
        "chapters_stat": rows,
        "errors": errors,
        "warnings": warnings,
        "suggestions": suggestions,
        "infos": {
            "note": "verb surface 不在 wordlists/verbs.json 的新词候选（04f §5.4："
                    "候选召回器，先积累再补词表；本批 165 词导致候选量大属预期）",
            "total_distinct": len(new_word_list),
            "total_tokens": sum(n["count"] for n in new_word_list),
            "new_word_candidates": new_word_list[:NEW_WORD_JSON_TOPN],
        },
        "top_issues": {
            "offending_surfaces": top_offending,
            "chapters": [{"chapter": k, "count": v}
                         for k, v in chapter_issue_counts.most_common(10)],
            "top_new_words": [{"surface": n["surface"], "count": n["count"]}
                              for n in new_word_list[:NEW_WORD_TOPN]],
        },
    }


def render_md(result: dict) -> str:
    book = result["book"]
    s = result["summary"]
    rows = result["chapters_stat"]
    baseline = result["baseline"]["density_per_100"]
    lines: list[str] = []
    add = lines.append

    add(f"# 动词标注校验报告 ·《{book}》")
    add("")
    add(f"- 生成时间：{result['generated']}")
    add(f"- 数据来源：`{result['source']}`")
    add(f"- 生成脚本：`scripts/validate_verb_tagging_wuxia.py`（N3，规则见 SKILL_04f）")
    add(f"- 校验范围：{result['chapter_count']} 回（"
        + (f"{result['chapters'][0]:03d}–{result['chapters'][-1]:03d}"
           if result["chapters"] else "—")
        + f"）；动词令牌 {s['verb_tokens']:,} 个；剥标正文 "
          f"{result['baseline']['chars']:,} 字；全书基线 "
          f"**{baseline:.3f} V/100字**")
    add(f"- 白名单：`{result['wordlist']['path']}`（"
        f"{result['wordlist']['surface_count']} 词，"
        f"{result['wordlist']['generated']} 编译，全部 status=待审）")
    if result["missing_chapters"]:
        add(f"- ⚠ 缺失回：{result['missing_chapters']}")
    add("")

    # 一、结论摘要
    add("## 一、结论摘要")
    add("")
    add("| 级别 | 条数 | 判定口径 |")
    add("|---|---:|---|")
    add(f"| ❌ 错误 | **{s['errors']}** | 域码非法 / 闭合·嵌套·重叠 / 触发词含标点 / "
        f"白名单域冲突 / 空消歧说明 |")
    add(f"| ⚠ 警告 | **{s['warnings']}** | 一词多域未消歧 / 单字虚词 / 触发词超长 / "
        f"分回密度异常 |")
    add(f"| 💡 建议 | **{s['suggestions']}** | 域混淆启发式 / 联动强制实体缺失 / "
        f"单段密度回查 / 姿态·施用排除 |")
    add(f"| ℹ 信息 | **{s['info_new_word_candidates']}** | 词表外新词候选（distinct "
        f"surface；覆盖 {s['info_new_word_tokens']:,} 处，见 §六 Top {NEW_WORD_TOPN}） |")
    add("")
    structural = s["structural"]
    add(f"结构面：嵌套 {structural['nested']} · 未闭合 {structural['unclosed']} · "
        f"括号错配 {structural['mismatch']} · 区间重叠 {structural['overlap']}。")
    add("")
    if s["errors"]:
        add("**结论**：存在错误，`--strict` 模式会 exit 1。错误主要集中在："
            + "、".join(f"{x['category']}×{x['count']}"
                        for x in s["by_category"]["errors"][:4]) + "。")
    else:
        add("**结论**：无 error 级问题（`--strict` 可通过）。")
    add("")

    # 二、分回统计
    add("## 二、分回统计")
    add("")
    add("| 回 | 动词 | 字数 | V/100字 | 相对基线 | 错误 | 警告 | 建议 | 密度标记 |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in rows:
        if r.get("missing"):
            add(f"| {r['chapter']} | — | — | — | — | — | — | — | 缺失 |")
            continue
        dens = r["density"] if r["density"] is not None else 0
        ratio = (dens / baseline) if baseline else 0
        flag = {"low": "⚠ 偏低", "high": "⚠ 偏高"}.get(r["density_flag"], "")
        add(f"| {r['chapter']} | {r['verbs']} | {r['chars']:,} | {dens:.3f} | "
            f"{ratio:.2f}× | {r['errors']} | {r['warnings']} | {r['suggestions']} | "
            f"{flag} |")
    add("")

    # 三、错误
    add("## 三、错误（必须修复）")
    add("")
    add("### 3.1 按类型汇总")
    add("")
    add("| 类别 | 条数 | 规则依据 |")
    add("|---|---:|---|")
    for x in s["by_category"]["errors"]:
        add(f"| {x['category']} | {x['count']} | {x['rule']} |")
    if not s["by_category"]["errors"]:
        add("| （无） | 0 | — |")
    add("")
    add("### 3.2 明细")
    add("")
    if result["errors"]:
        add("| # | 回 | PN | 令牌 | 类别 | 说明 |")
        add("|---:|---:|---:|---|---|---|")
        for i, e in enumerate(result["errors"], 1):
            pn = e["pn"] if e["pn"] is not None else "—"
            tok = e["token"] or "—"
            tok = tok.replace("|", "\\|")
            msg = e["message"].replace("|", "\\|")
            add(f"| {i} | {e['chapter']} | {pn} | `{tok}` | {e['category']} | {msg} |")
    else:
        add("（无）")
    add("")

    # 四、警告
    add("## 四、警告（建议复核）")
    add("")
    add("### 4.1 按类型汇总")
    add("")
    add("| 类别 | 条数 | 规则依据 |")
    add("|---|---:|---|")
    for x in s["by_category"]["warnings"]:
        add(f"| {x['category']} | {x['count']} | {x['rule']} |")
    if not s["by_category"]["warnings"]:
        add("| （无） | 0 | — |")
    add("")
    add("### 4.2 明细（一词多域 / 超长）")
    add("")
    token_warnings = [w for w in result["warnings"] if w["category"] != "W-DENSITY"]
    if token_warnings:
        add("| # | 回 | PN | 令牌 | 域 | 说明 |")
        add("|---:|---:|---:|---|---|---|")
        for i, w in enumerate(token_warnings[:200], 1):
            tok = w["token"].replace("|", "\\|")
            msg = w["message"].replace("|", "\\|")
            add(f"| {i} | {w['chapter']} | {w['pn']} | `{tok}` | {w.get('domain', '')} | "
                f"{msg} |")
        if len(token_warnings) > 200:
            add(f"\n> 其余 {len(token_warnings) - 200} 条见 JSON（`warnings`）。")
    else:
        add("（无）")
    add("")
    add("### 4.3 分回密度")
    add("")
    density_warnings = [w for w in result["warnings"] if w["category"] == "W-DENSITY"]
    if density_warnings:
        add("| 回 | V/100字 | 全书基线 | 判定 |")
        add("|---|---:|---:|---|")
        for w in density_warnings:
            add(f"| {w['chapter']} | {w['density']:.3f} | {w['baseline']:.3f} | "
                f"{w['message'].split('——')[-1]} |")
    else:
        add("（无：所有回密度均在阈值区间内）")
    add("")

    # 五、建议
    add("## 五、建议（域混淆启发式 / 联动核验）")
    add("")
    add("### 5.1 按类型汇总")
    add("")
    add("| 类别 | 条数 | 规则依据 |")
    add("|---|---:|---|")
    for x in s["by_category"]["suggestions"]:
        add(f"| {x['category']} | {x['count']} | {x['rule']} |")
    if not s["by_category"]["suggestions"]:
        add("| （无） | 0 | — |")
    add("")
    add("### 5.2 明细")
    add("")
    if result["suggestions"]:
        add("| # | 回 | PN | 令牌 | 类别 | 建议 |")
        add("|---:|---:|---:|---|---|---|")
        for i, sug in enumerate(result["suggestions"][:200], 1):
            tok = (sug["token"] or "—").replace("|", "\\|")
            msg = sug["message"].replace("|", "\\|")
            add(f"| {i} | {sug['chapter']} | {sug['pn'] if sug['pn'] else '—'} | "
                f"`{tok}` | {sug['category']} | {msg} |")
        if len(result["suggestions"]) > 200:
            add(f"\n> 其余 {len(result['suggestions']) - 200} 条见 JSON（`suggestions`）。")
    else:
        add("（无）")
    add("")

    # 六、新词候选
    add(f"## 六、词表外新词候选 Top {NEW_WORD_TOPN}")
    add("")
    add(f"> verbs.json 仅 {result['wordlist']['surface_count']} 词，"
        f"本批词表外 distinct surface 共 {s['info_new_word_candidates']:,} 个"
        f"（{s['info_new_word_tokens']:,} 处）。下表按出现次数排序，作为 §5.2 词表"
        f"扩词/降档候选（04f §5.4）；完整 Top {NEW_WORD_JSON_TOPN} 见 JSON。")
    add("")
    add("| # | surface | 出现 | 涉及回 | 域分布 | 首见 |")
    add("|---:|---|---:|---:|---|---|")
    for i, n in enumerate(result["infos"]["new_word_candidates"][:NEW_WORD_TOPN], 1):
        domains = "、".join(f"{d}×{c}" for d, c in
                            sorted(n["domains"].items(), key=lambda kv: -kv[1]))
        first = n["first"]["anchor"] if n["first"] else "—"
        add(f"| {i} | {n['surface']} | {n['count']} | {n['chapter_count']} | "
            f"{domains} | `{first}` |")
    add("")

    # 七、Top 问题
    add("## 七、Top 问题")
    add("")
    add("### 7.1 问题最多的词形（错误+警告+建议）")
    add("")
    add("| # | 类别 | surface | 次数 |")
    add("|---:|---|---|---:|")
    for i, x in enumerate(result["top_issues"]["offending_surfaces"], 1):
        add(f"| {i} | {x['category']} | {x['surface']} | {x['count']} |")
    add("")
    add("### 7.2 问题最多的回")
    add("")
    add("| # | 回 | 问题数 |")
    add("|---:|---|---:|")
    for i, x in enumerate(result["top_issues"]["chapters"], 1):
        add(f"| {i} | {x['chapter']} | {x['count']} |")
    add("")

    # 八、阈值与口径
    c = result["constants"]
    add("## 八、阈值与口径依据")
    add("")
    add(f"- 密度阈值：`DENSITY_LOW={c['DENSITY_LOW']}`、`DENSITY_HIGH={c['DENSITY_HIGH']}` "
        f"（V/100 剥标正文字）；依据：{c['basis']}。")
    add(f"- 单段回查：`PARA_HIGH={c['PARA_HIGH']}`（04f §6.1 规则 4：每段 1-6 处正常、"
        f">10 处 almost certainly 逐招误标；G0 附录 B-5 裁决）。")
    add(f"- 超长：`MAX_SURFACE_LEN={c['MAX_SURFACE_LEN']}`（04f §3.2 整词最长 5 字；"
        f">8 字几乎必然吞宾语/状语，§3.1）。")
    add(f"- 单字虚词：{'/'.join(c['FUNC_WORDS'])}（04f §3.1 虚词不承载事件；"
        f"按 warning 级提示，因白话中「着了一下」等可具实义，交人工复核）。")
    add("- 密度分母：剥除三层标注后的正文字符数，含韵文/回末对内容，不含回目标题行与"
        "围栏标记行（与 `qa_annotation_report.py` 的分回字数口径一致）。")
    add("- 多域判定：先按 `verbs.json` 同 surface 多 domain（当前 0 组），再按**语料实测**"
        "同 surface ≥2 域且本处落在少数派域、又无 `|` 说明 → warning（04f §3.3）。")
    add("")

    # 九、已知局限
    add("## 九、已知局限")
    add("")
    add("1. **词表仅 165 条**（且全部 status=待审）：`info` 新词候选会很多（"
        f"{s['info_new_word_candidates']:,} 个 distinct surface），"
        "这是候选召回器定位的预期结果，不是标注缺陷；补词表后才宜收紧。")
    add("2. **白名单域冲突按 error 处理**：词表主域为单词，语料中的合法多义用法"
        "（如 `刺` 词表 ⊞、本批 7 处标 ⊠）也会报错；26 条带消歧说明、32 条未带，"
        "需人工判定是「改标回主域」还是「补 senses 分型」。")
    add("3. 域混淆启发式是**关键词启发**（同句上下文），存在误报/漏报；建议类不阻断。")
    add("4. 联动缺失只查**同句**实体（按 。！？； 切分），跨句/代词指代不追"
        "（04f §4.2：联动是候选生成器，不是定论）。")
    add("5. 结构检查只覆盖三层括号记号（〖〗 / ⟦⟧ / 〘〙）；`|` 管道内容不参与括号配对。")
    add("6. 分回密度按「回」聚合，04f §6.1「每段 1-6 处」由 S-PARA-DENSITY 单独提示；"
        "两套口径互补。")
    add("7. 017 回密度 0.46 触发下界（全书最低）；该回为低武打密度叙事，"
        "需人工判定是「动词层漏标」还是「文戏正常低密度」，不能仅凭阈值断定错误。")
    add("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="N3 · 动词标注校验器（武侠版，规则见 SKILL_04f）",
        formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--book", default=config.PILOT_BOOK, help="书名（默认试点书）")
    ap.add_argument("--chapters", default="all",
                    help="回号过滤，如 1-5,7（默认 all=该书全部 tagged）")
    ap.add_argument("--strict", action="store_true",
                    help="有 error 时 exit 1（供 CI/完成门使用）")
    ap.add_argument("--wordlist-strict", action="store_true",
                    help="词表域冲突按 error 计（默认 warning；词表补 senses 分型后再开）")
    ap.add_argument("--json", action="store_true",
                    help="只把结果 JSON 打印到 stdout，不写报告文件")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="输出目录（默认 config.DIR_LOGS/verb_validation）")
    args = ap.parse_args()
    global WORDLIST_STRICT
    WORDLIST_STRICT = bool(args.wordlist_strict)

    book = args.book
    tagged_dir = config.DIR_TAGGED / book
    if not tagged_dir.is_dir():
        print(f"✗ 标注目录不存在：{tagged_dir}")
        return 1
    available = sorted(int(p.stem.split(".")[0]) for p in tagged_dir.glob("*.tagged.md"))
    if not available:
        print(f"✗ {tagged_dir} 下没有 *.tagged.md")
        return 1
    chapters = parse_chapters(args.chapters, available)

    wordlist = load_wordlist()
    chapter_data = {}
    for ch in chapters:
        if config.tagged_path(book, ch).exists():
            chapter_data[ch] = analyze_chapter(book, ch)
    checked = check_tokens(chapter_data, wordlist, book)
    result = build_result(book, chapters, chapter_data, checked, wordlist)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        out_dir = args.out_dir or (config.DIR_LOGS / "verb_validation")
        out_dir.mkdir(parents=True, exist_ok=True)
        # 子集校验不得覆盖全书报告（2026-11-04 Lead 修复）
        suffix = "" if chapters == available else \
            (f"_{chapters[0]:03d}-{chapters[-1]:03d}" if chapters else "_empty")
        json_path = out_dir / f"{book}{suffix}.json"
        md_path = out_dir / f"{book}{suffix}.md"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        md_path.write_text(render_md(result), encoding="utf-8")
        s = result["summary"]
        print(f"✓ 校验 {result['chapter_count']} 回 · 动词 {s['verb_tokens']:,} 个 · "
              f"基线 {result['baseline']['density_per_100']:.3f} V/100字")
        print(f"  error {s['errors']} · warning {s['warnings']} · "
              f"suggestion {s['suggestions']} · info 新词候选 "
              f"{s['info_new_word_candidates']:,}")
        print(f"✓ 写入 {json_path}")
        print(f"✓ 写入 {md_path}")

    return 1 if (args.strict and result["summary"]["errors"] > 0) else 0


if __name__ == "__main__":
    sys.exit(main())
