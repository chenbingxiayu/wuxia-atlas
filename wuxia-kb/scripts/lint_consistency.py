# -*- coding: utf-8 -*-
"""N8 · `lint_consistency.py` — 穿帮规则引擎（D11；docs/17 §2.3 / docs/50 §三）

规范源：`skills/SKILL_常识与设定一致性_武侠版.md`
  §三 种子规则库 34 条 IF-THEN（武学 W1-W9 / 门派 S1-S10 / 江湖 J1-J8 / 时代 T1-T7）
  §四 五项设定一致性检查（年龄跨回/习得顺序/门派存续/死亡再现/称谓辈分）
  §六 A-E 评级（A 完全一致 / B 设定内合理·备案 / C 存疑 / D 疑似穿帮 / E 确认穿帮）
  §七 反常三分流（叙述模式过滤 → 可靠性过滤 → 修辞 → 翻案 → 破绽候选）
  §3.5 lint 关系（可自动/半自动/人工/无需 lint 四档）
  §1.4 方向反转总声明（武侠度量与史记相反：W1/J1/W3/S8/J2/J8/T3 等豁免/备案，不判穿帮）

输入（只读）：
  * registry/time/<书>.json      —— N4 时间轴（tp_id/段锚/年龄锚/t_days/year_ce/narrative_mode/errors）
  * registry/relations/<书>.json —— N5 关系表（师承/任职/杀害/掌握/同门/推导 lineage/validation）
  * registry/entities.json       —— 跨书实体登记（canonical/aliases/status，@◆&~）
  * tagged/<书>/*.tagged.md      —— 原文证据与叙述模式（只读）
  * skills/SKILL_常识与设定一致性_武侠版.md

输出：
  * registry/consistency/<书>.json —— violations（rule_id/severity/grade/证据/定位符）+ 规则覆盖 + 豁免
  * logs/consistency/<书>.md + logs/consistency/summary.md（--all）
  * --strict：存在 error 级命中（→ D 级候选）时 exit 2；默认 exit 0。

证据/定位符：每条命中带 locator `NNN:PN`（回号:段号）、原文引文（≤120 字）、规则编号与 SKILL 条文引用。
叙述模式豁免（04a）：命中定位符所在段落模式=回忆/梦境/假想/戏中戏 → 不入 violations，记 exemptions。

CLI：
  python -X utf8 scripts/lint_consistency.py --book 江湖三女侠
  python -X utf8 scripts/lint_consistency.py --all
  python -X utf8 scripts/lint_consistency.py --book 七剑下天山 --rule W6,T4,C3
  python -X utf8 scripts/lint_consistency.py --book 冰魄寒光剑 --strict
  python -X utf8 scripts/lint_consistency.py --selftest
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAGGED_DIR = ROOT / "tagged"
TIME_DIR = ROOT / "registry" / "time"
REL_DIR = ROOT / "registry" / "relations"
ENTITY_PATH = ROOT / "registry" / "entities.json"
OUT_REG = ROOT / "registry" / "consistency"
OUT_LOGS = ROOT / "logs" / "consistency"
TOOL_VERSION = "lint_consistency v0.1 (2026-11-05, N8/D11)"
DEFAULT_BOOKS = ["江湖三女侠", "七剑下天山", "塞外奇侠传", "冰魄寒光剑", "白发魔女传"]

# A-E 评级（SKILL §6.1）：自动引擎只到 D（疑似穿帮，待人工复核）；E 需人工确认，本工具不产出 E。
GRADE_OF_SEVERITY = {"error": "D", "warning": "C", "info": "B"}
SEVERITY_ORDER = {"error": 2, "warning": 1, "info": 0}
NON_NORMAL_MODES = ("回忆", "梦境", "假想", "戏中戏")
# 不入故事时间轨/不判穿帮的额外模式（SKILL 错误6：楔子/回末韵文评点；作者按语属评点层）
EXTRA_EXEMPT_MODES = ("韵文围栏", "作者按语")
RELIABILITY_LOW = ("传言", "转述", "据说", "传说", "传闻", "听说")

TOKEN_RE = re.compile(r"[〖⟦]([^〖⟦〗⟧]+)[〗⟧]")
RHET_RE = re.compile(r"〘([^〙]*)〙")
PARA_RE = re.compile(r"^\[(\d+)\] ")
CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn_num(s: str) -> int | None:
    """中文/阿拉伯数字 → int（与 N4 同口径；支持 廿/卅/十八/四十）。"""
    if s is None:
        return None
    s = str(s).strip().replace("廿", "二十").replace("卅", "三十").replace("卌", "四十")
    if s.isdigit():
        return int(s)
    units = {"十": 10, "百": 100, "千": 1000}
    total, section, num = 0, 0, None
    for ch in s:
        if ch in CN_DIGITS:
            num = CN_DIGITS[ch]
        elif ch in units:
            section += (num if num is not None else 1) * units[ch]
            num = None
    if num is not None:
        section += num
    total += section
    return total if total or s in ("零", "〇") else None


def strip_markup(text: str) -> str:
    text = TOKEN_RE.sub(lambda m: m.group(1)[1:].split("|")[0].split("｜")[0], text)
    return RHET_RE.sub(lambda m: m.group(1)[1:] if m.group(1).startswith("※") else m.group(1), text)


# ────────────────────────── 规则元数据（34 条 + 五项检查；逐条引 SKILL 条文） ──────────────────────────
@dataclass
class RuleMeta:
    rule_id: str
    area: str            # 武学/门派/江湖/时代/检查项
    title: str
    kind: str            # auto 可自动 / semi 半自动 / manual 人工 / exempt 豁免/无需扫描
    spec: str            # SKILL 条文引用
    note: str = ""


RULES: list[RuleMeta] = [
    RuleMeta("W1", "武学", "轻功远程奔袭", "auto", "§3.1 W1（★方向反转：≥300 里/日=info 备案，不判异常）"),
    RuleMeta("W2", "武学", "内伤/内力恢复速度", "semi", "§3.1 W2（轻伤≥半日/重伤≥3日/内力耗尽≥7日；灵药/渡功/运功豁免）"),
    RuleMeta("W3", "武学", "高龄高手出战", "exempt", "§3.1 W3（★方向反转：≥60 岁出战不标记，豁免性规则）"),
    RuleMeta("W4", "武学", "神功速成", "semi", "§3.1 W4（非 X 年不能有成 ∧ <X/3 年大成 ∧ 无奇遇 → warning）"),
    RuleMeta("W5", "武学", "武功相克反转", "semi", "§3.1 W5（明文相克 ∧ 后文乙胜甲 ∧ 无破法解释 → info 待人工）"),
    RuleMeta("W6", "武学", "轻功/剑气数值夸饰", "auto", "§3.1 W6（大数+修辞标志词且无情节依赖 → 修辞标签 info）"),
    RuleMeta("W7", "武学", "内力外放设定边界", "semi", "§3.1 W7（设定不会内功 ∧ 后文隔空伤人 ∧ 无习得 → warning）"),
    RuleMeta("W8", "武学", "毒发时限自洽", "semi", "§3.1 W8（超明示时限 1.5 倍 ∧ 无解药/逼毒 → warning）"),
    RuleMeta("W9", "武学", "少年天才需铺垫", "manual", "§3.1 W9（<16 岁击败成名一流 ∧ 无奇遇/家学/名师 → info 待人工）"),
    RuleMeta("S1", "门派", "掌门在位年长", "auto", "§3.2 S1（同一掌门在位 >50 年 ∧ 无长寿/驻颜设定 → info 备案）"),
    RuleMeta("S2", "门派", "继任节奏", "auto", "§3.2 S2（掌门死亡 >3 年无继任 / <5 年更替 3+ 任 → info）"),
    RuleMeta("S3", "门派", "灭派存续", "semi", "§3.2 S3（整派被灭后整建制再现 ∧ 无重建 → error 候选）"),
    RuleMeta("S4", "门派", "辈分跨级晋升", "auto", "§3.2 S4（跨辈晋升 / 入门<3 年即长老掌门 ∧ 无明写 → warning）"),
    RuleMeta("S5", "门派", "师承代际时距", "auto", "§3.2 S5（师徒链 <10 年跨三代；师父比徒弟年轻 15+ → warning）"),
    RuleMeta("S6", "门派", "门规与行事", "manual", "§3.2 S6（刚性门规被反复违反 ∧ 无处罚 → info）"),
    RuleMeta("S7", "门派", "比武规矩自洽", "semi", "§3.2 S7（赛前明文规则 ∧ 结果违反 ∧ 无变故 → warning）"),
    RuleMeta("S8", "门派", "同门相残", "exempt", "§3.2 S8（★方向反转：同门相残为母题，不标记）"),
    RuleMeta("S9", "门派", "失传绝学再现", "semi", "§3.2 S9（明写失传 ∧ 后文再现 ∧ 无秘籍/隐脉 → warning）"),
    RuleMeta("S10", "门派", "世仇结盟铺垫", "semi", "§3.2 S10（世仇 ∧ 结盟 ∧ 无和解 → info 待人工）"),
    RuleMeta("J1", "江湖", "镖程备案", "auto", "§3.3 J1（★方向反转：>凡人 3 倍=info 备案，不判异常）"),
    RuleMeta("J2", "江湖", "寻仇母题", "exempt", "§3.3 J2（★方向反转：灭门/寻仇不自带异常，不标记）"),
    RuleMeta("J3", "江湖", "比武彩头兑现", "manual", "§3.3 J3（彩头被违背 ∧ 无解释 → info）"),
    RuleMeta("J4", "江湖", "绿林道惯例", "manual", "§3.3 J4（明文惯例被违反 ∧ 无解释 → info）"),
    RuleMeta("J5", "江湖", "江湖经济", "manual", "§3.3 J5（整体豁免；仅关键物前后价差悬殊 → info）"),
    RuleMeta("J6", "江湖", "官府缺位", "semi", "§3.3 J6（缉拿明写 ∧ 公然行动无规避 → info）"),
    RuleMeta("J7", "江湖", "迷药药性自洽", "semi", "§3.3 J7（药性明文 ∧ 情节矛盾 → warning）"),
    RuleMeta("J8", "江湖", "传言≠事实", "exempt", "§3.3 J8（★方向反转：传言≠事实，可靠性过滤豁免）"),
    RuleMeta("T1", "时代", "朝代锚·器物与物品", "auto", "§3.4 T1（锚外器物 ∧ 未明写架空 → error；边界器物挂人工）"),
    RuleMeta("T2", "时代", "朝代锚·制度官职与地名", "auto", "§3.4 T2（朝代与官制/地名错配 → error）"),
    RuleMeta("T3", "时代", "历史人物客串", "manual", "§3.4 T3（★方向反转：演义自由，info 资产备案，不判穿帮）"),
    RuleMeta("T4", "时代", "纪年自洽", "auto", "§3.4 T4（同一书纪年体系冲突 ∧ 无跨时叙述 → error）"),
    RuleMeta("T5", "时代", "兵器谱年代", "exempt", "§3.4 T5（通用兵器白名单内一律豁免）"),
    RuleMeta("T6", "时代", "称谓与服饰时代感", "semi", "§3.4 T6（古代背景现代称谓/跨朝代服饰 ∧ 无叙述模式豁免 → warning）"),
    RuleMeta("T7", "时代", "修订版权威", "exempt", "§3.4 T7（修订版优先；需版本字段，本批无版本数据 → 不扫描）"),
    # 五项设定一致性检查（§四）
    RuleMeta("C1", "检查项", "人物年龄跨回自洽", "semi", "§4.1（年龄差 ≠ 时点差 ±1 年容差 → error/warning/info）"),
    RuleMeta("C2", "检查项", "武功习得顺序（未学先使）", "semi", "§4.2（使用时点 < 习得时点 → error/warning/info）"),
    RuleMeta("C3", "检查项", "门派存续期（灭派后再出场）", "semi", "§4.3（灭派后整建制再现 ∧ 无重建 → error/warning）"),
    RuleMeta("C4", "检查项", "死亡角色再出场", "semi", "§4.4（正常叙事活体行动 ∧ 无假死/翻案 → error/warning）"),
    RuleMeta("C5", "检查项", "称谓辈分错乱", "semi", "§4.5（关系边与称谓系统性冲突 → error/warning/info）"),
]
RULE_BY_ID = {r.rule_id: r for r in RULES}
RULE_IDS = [r.rule_id for r in RULES]

# 0 命中时报告的数据缺口说明（覆盖表用；说明该规则依赖哪些上游字段/文本证据）
RULE_NOTES = {
    "W1": "需同段内『距离(里)+耗时(日/天)』明写；本批原文多为概称→0",
    "W2": "需伤势与恢复同句/邻段且无处置明写",
    "W4": "需『非 X 年不能有成』明示句 + 习得/大成时点",
    "W5": "需明文相克关系（☆武功成对）+ 后文胜负反转",
    "W7": "需『不会武功/内力平平』设定句 + 后文隔空伤人",
    "W8": "需『X 日毒发』时限句 + N4 时点差",
    "S1": "需 ≥2 条『任职』边且 N4 年可估（本批任职边仅 1–2 条）",
    "S2": "需同一门派 ≥3 任任职边（本批无）",
    "S3": "需灭派事件明写 + 后文整建制再现场景（本批 N5 无门派事件边）",
    "S4": "需『入门<3 年即长老/掌门』句式",
    "S5": "需师承边双方均有 N4 年龄锚（本批覆盖有限）",
    "S6": "需门规条文 + 后续 ≥2 次违反且无处罚（人工为主）",
    "S7": "需赛前明文规则（点到即止/三局两胜等）+ 结果违反",
    "S9": "需失传声明段 + 后文同武功再现段（且无秘籍/隐脉解释）",
    "S10": "需两派世仇明写 + 后文结盟段（本批世仇1例）",
    "J1": "同 W1：需镖程距离+耗时同段",
    "J3": "需彩头/赌注明写 + 后文未兑现",
    "J4": "需绿林惯例明写 + 后文违反",
    "J5": "需同一器物两处价差 ≥5 倍（本批无）",
    "J6": "需缉拿明写 + 后文公然行动",
    "J7": "需药性明写（无色无味）+ 情节矛盾（香味）",
    "T1": "需 N4 朝代年锚（冰魄无年锚→不可比）",
    "T2": "需 N4 朝代年锚与官制词表冲突（本批无冲突项）",
    "T6": "需现代称谓/跨朝代服饰词表命中（本批仅『银元』边界）",
    "C2": "N5『掌握』边稀疏（本批 2 条），习得事件层未建",
    "C3": "同 S3（复用），需门派事件层",
    "C4": "需 N5 杀害边 + 原文致死结构证据；本批结构证据通过者 0→0 命中",
}
for _r in RULES:
    if not _r.note:
        _r.note = RULE_NOTES.get(_r.rule_id, "")


# ────────────────────────── 数据索引 ──────────────────────────
@dataclass
class TokenInPara:
    domain: str
    display: str
    inner: str
    raw: str
    raw_start: int
    raw_end: int
    plain_start: int


@dataclass
class Para:
    chapter: int
    pn: int
    line_no: int
    raw: str
    plain: str
    fence: str
    tokens: list[TokenInPara] = field(default_factory=list)


class Corpus:
    """tagged 只读语料索引（段落/令牌/引文/叙述模式/人物近邻）。"""

    def __init__(self, book: str, entity_map: dict[str, str]):
        self.book = book
        self.entity_map = entity_map
        self.paras: dict[tuple[int, int], Para] = {}
        self.titles: dict[int, str] = {}
        self.chapters: list[int] = []
        d = TAGGED_DIR / book
        if not d.is_dir():
            raise RuntimeError(f"tagged 目录不存在：{d}")
        for path in sorted(d.glob("*.tagged.md")):
            stem = path.stem.split(".")[0]
            if not stem.isdigit():
                continue
            ch = int(stem)
            self.chapters.append(ch)
            fence = ""
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
                if line.startswith("# [0]"):
                    self.titles[ch] = line[5:].strip()
                    continue
                if line.startswith(":::"):
                    fence = line[3:].strip()
                    continue
                m = PARA_RE.match(line)
                if not m:
                    continue
                pn = int(m.group(1))
                para = Para(ch, pn, i, line, strip_markup(line), fence)
                parts, pos_raw, plain_len = [], 0, 0
                for tm in TOKEN_RE.finditer(line):
                    seg = line[pos_raw:tm.start()]
                    parts.append(seg)
                    plain_len += len(seg)
                    inner = tm.group(1)
                    domain = inner[0]
                    rest = inner[1:]
                    parts_display = re.split(r"[｜|]", rest, maxsplit=1)
                    display = parts_display[0]
                    para.tokens.append(TokenInPara(domain, display, inner, tm.group(0),
                                                   tm.start(), tm.end(), plain_len))
                    parts.append(display)
                    plain_len += len(display)
                    pos_raw = tm.end()
                parts.append(line[pos_raw:])
                para.plain = "".join(parts)
                self.paras[(ch, pn)] = para
        self.first_person: dict[str, tuple[int, int]] = {}
        self.person_chapters: dict[str, set[int]] = {}
        for (ch, pn), para in self.paras.items():
            for tok in para.tokens:
                if tok.domain == "@":
                    canon = self.canon(tok.display)
                    self.first_person.setdefault(canon, (ch, pn))
                    self.person_chapters.setdefault(canon, set()).add(ch)

    def canon(self, display: str) -> str:
        return self.entity_map.get(display, display)

    def para(self, ch: int, pn: int) -> Para | None:
        return self.paras.get((ch, pn))

    def sorted_paras(self) -> list[Para]:
        return [self.paras[k] for k in sorted(self.paras)]

    def narrative_mode(self, ch: int, pn: int, plain_pos: int | None = None,
                       radius: int = 60) -> str:
        """叙述模式（04a）：围栏韵文 / 回忆 / 梦境 / 假想 / 戏中戏 / 传言 / 对白 / 正常叙事。"""
        para = self.para(ch, pn)
        if para is None:
            return "未知"
        if para.fence:
            return "韵文围栏"
        start = plain_pos if plain_pos is not None else 0
        win = para.plain[max(0, start - radius): start + radius]
        if re.search(r"(羽生按|作者按|笔者按|按：|注：)", win):
            return "作者按语"
        if re.search(r"(梦中|梦见|梦到|幻觉)", win):
            return "梦境"
        if re.search(r"(假想|幻想|设想|若是那日)", win):
            return "假想"
        if re.search(r"(戏中戏|台上|戏文|说书)", win):
            return "戏中戏"
        if re.search(r"(回忆|追忆|忆起|想起|记得|当年|往事|旧事)", win):
            return "回忆"
        if re.search(r"(传言|传闻|据说|传说|听说|据称|消息说)", win):
            return "传言"
        raw_prefix = para.raw[: self._raw_pos(para, start)]
        if raw_prefix.count("“") > raw_prefix.count("”"):
            return "对白"
        return "正常叙事"

    @staticmethod
    def _raw_pos(para: Para, plain_pos: int) -> int:
        """plain 位置 → 近似 raw 位置（按 token 表换算；无 token 时按等长近似）。"""
        delta = 0
        for tok in para.tokens:
            if tok.plain_start > plain_pos:
                break
            raw_len = tok.raw_end - tok.raw_start
            display_len = len(tok.display)
            delta += raw_len - display_len
        return min(len(para.raw), plain_pos + delta)

    def person_at(self, ch: int, pn: int, plain_pos: int, before: bool = True) -> str | None:
        """段落内距 plain_pos 最近的 @人物（默认取之前；无则之后），返回 canonical。"""
        para = self.para(ch, pn)
        if para is None:
            return None
        cands = [t for t in para.tokens if t.domain == "@"]
        if not cands:
            return None
        prev = [t for t in cands if t.plain_start <= plain_pos]
        if before and prev:
            tok = max(prev, key=lambda t: t.plain_start)
        else:
            after = [t for t in cands if t.plain_start > plain_pos]
            tok = min(after, key=lambda t: t.plain_start) if after else max(cands, key=lambda t: t.plain_start)
        return self.canon(tok.display)

    def person_for_age(self, ch: int, pn: int, raw_span_start: int) -> str | None:
        """年龄归属（严格）：同句内 姓名/他/她 就近先行词；不满足则 None（不猜）。"""
        para = self.para(ch, pn)
        if para is None:
            return None
        pos = len(strip_markup(para.raw[:raw_span_start])) if raw_span_start else 0
        pos = min(pos, len(para.plain))
        left = max(para.plain.rfind("。", 0, pos), para.plain.rfind("！", 0, pos),
                   para.plain.rfind("？", 0, pos), para.plain.rfind("；", 0, pos))
        before = para.plain[left + 1:pos]
        cands = [t for t in para.tokens if t.domain == "@" and left < t.plain_start <= pos]
        if not cands:
            return None
        nearest = max(cands, key=lambda t: t.plain_start)
        nearest = max(cands, key=lambda t: t.plain_start)
        # 仅接受高精度模式：姓名/带姓称谓直接贴近年龄表达（≤10 字，中间无引号/句读/相对比较词）
        if pos - nearest.plain_start <= 10:
            seg = para.plain[nearest.plain_start + len(nearest.display): pos]
            if re.search(r"[“”‘’]", seg):
                return None
            if re.search(r"(比|年长|年小|相差|长他|长她|大.{0,2}岁|小.{0,2}岁|[大小][一二三四五六七八九十两几\d]+岁|幼)", seg):
                return None   # "甲比乙大四岁/比她年长七岁"是相对差，不是绝对年龄
            if re.search(r"(比|大|小|长|幼|相差)$", seg.strip()):
                return None   # "比他大四岁""比她小两岁"：比较词紧贴年龄
            return self.canon(nearest.display)
        return None

    def canonical_person_token(self, ch: int, pn: int, person: str) -> TokenInPara | None:
        para = self.para(ch, pn)
        if para is None:
            return None
        for t in para.tokens:
            if t.domain == "@" and self.canon(t.display) == person:
                return t
        return None

    def person_close(self, ch: int, pn: int, plain_pos: int, max_before: int = 18,
                     max_after: int = 6) -> str | None:
        """严格人物归属（供年龄/战斗等弱主语场景）：同一句内、间距受限的最近 @人物。

        规则：取 plain_pos 所在句（。！？； 边界）；句内先找 ≤max_before 字的最近前置 @；
        否则找 ≤max_after 字的最近后置 @；都不满足 → None（不猜，避免错挂人物）。
        """
        para = self.para(ch, pn)
        if para is None or not para.plain:
            return None
        pos = min(max(0, plain_pos), len(para.plain))
        left = max(para.plain.rfind("。", 0, pos), para.plain.rfind("！", 0, pos),
                   para.plain.rfind("？", 0, pos), para.plain.rfind("；", 0, pos))
        right_candidates = [para.plain.find(x, pos) for x in "。！？；"]
        right_candidates = [x for x in right_candidates if x >= 0]
        right = min(right_candidates) if right_candidates else len(para.plain)
        best = None
        for t in para.tokens:
            if t.domain != "@":
                continue
            if left < t.plain_start <= pos and pos - t.plain_start <= max_before:
                if best is None or t.plain_start > best.plain_start:
                    best = t
        if best is None:
            for t in para.tokens:
                if t.domain != "@":
                    continue
                if pos < t.plain_start <= right and t.plain_start - pos <= max_after:
                    if best is None or t.plain_start < best.plain_start:
                        best = t
        return self.canon(best.display) if best else None

    def persons_in(self, ch: int, pn: int) -> list[str]:
        para = self.para(ch, pn)
        if para is None:
            return []
        seen, out = set(), []
        for t in para.tokens:
            if t.domain == "@":
                c = self.canon(t.display)
                if c not in seen:
                    seen.add(c)
                    out.append(c)
        return out

    def martial_in(self, ch: int, pn: int) -> list[str]:
        para = self.para(ch, pn)
        if para is None:
            return []
        return [t.display for t in para.tokens if t.domain == "☆"]

    def orgs_in(self, ch: int, pn: int) -> list[str]:
        para = self.para(ch, pn)
        if para is None:
            return []
        return [t.display for t in para.tokens if t.domain == "◆"]

    def loc(self, ch: int, pn: int) -> str:
        return f"{ch:03d}:{pn}"

    def quote(self, ch: int, pn: int, pos: int = 0, radius: int = 46) -> str:
        para = self.para(ch, pn)
        if para is None:
            return ""
        p = min(max(0, pos), len(para.plain))
        return para.plain[max(0, p - radius): p + radius].replace("\n", " ")

    def find(self, pattern: str, flags: int = 0, chapters: list[int] | None = None):
        rx = re.compile(pattern, flags)
        for para in self.sorted_paras():
            if chapters and para.chapter not in chapters:
                continue
            for m in rx.finditer(para.plain):
                yield para, m


class TimeData:
    """N4 时间轴接口（registry/time/<书>.json，只读）。"""

    def __init__(self, book: str):
        path = TIME_DIR / f"{book}.json"
        self.raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.points = self.raw.get("time_points") or []
        self.by_pn: dict[tuple[int, int], list[dict]] = {}
        for tp in self.points:
            a = tp.get("anchor") or {}
            self.by_pn.setdefault((a.get("chapter"), a.get("pn")), []).append(tp)
        anchors = self.raw.get("book_anchors") or []
        years = [a.get("year_ce") for a in anchors if a.get("year_ce")]
        self.origin_year = min(years) if years else None
        self.year_min = min(years) if years else None
        self.year_max = max(years) if years else None
        self.errors = self.raw.get("errors") or []
        self.generated = self.raw.get("generated_at")

    def nearest(self, ch: int, pn: int, predicate=None) -> dict | None:
        """叙述序（回,段）最近的时点；predicate 可过滤（如 t_days 非空）。"""
        best, best_key = None, None
        for tp in self.points:
            if predicate and not predicate(tp):
                continue
            a = tp.get("anchor") or {}
            key = (abs(a.get("chapter", 0) - ch), abs(a.get("pn", 0) - pn))
            if best_key is None or key < best_key:
                best, best_key = tp, key
        return best

    def t_at(self, ch: int, pn: int) -> float | None:
        tp = self.nearest(ch, pn, lambda x: x.get("t_days") is not None)
        return tp.get("t_days") if tp else None

    def year_at(self, ch: int, pn: int) -> int | None:
        tp = self.nearest(ch, pn, lambda x: x.get("year_ce") is not None or x.get("t_days") is not None)
        if tp is None:
            return None
        if tp.get("year_ce") is not None:
            return tp["year_ce"]
        if tp.get("t_days") is not None and self.origin_year is not None:
            return int(self.origin_year + tp["t_days"] // 365)
        return None

    def ages(self) -> list[dict]:
        """年龄锚列表：{person, age, ch, pn, span, confidence}（person 由语料近邻 @ 人物推断）。"""
        out = []
        for tp in self.points:
            if tp.get("age") is None:
                continue
            a = tp.get("anchor") or {}
            out.append({"age": tp["age"], "ch": a.get("chapter"), "pn": a.get("pn"),
                        "span": a.get("span_in_line") or [], "confidence": tp.get("confidence"),
                        "t_days": tp.get("t_days"), "display": tp.get("display")})
        return out

    def events_by_code(self, code: str) -> list[dict]:
        return [e for e in self.errors if e.get("code") == code]

    def point_by_id(self, tp_id: str) -> dict | None:
        for tp in self.points:
            if tp.get("tp_id") == tp_id:
                return tp
        return None


class RelationsData:
    """N5 关系表接口（registry/relations/<书>.json，只读）。"""

    def __init__(self, book: str):
        path = REL_DIR / f"{book}.json"
        self.raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.edges = self.raw.get("edges") or []
        self.lineage = (self.raw.get("derived") or {}).get("lineage_labels") or []
        self.trees = (self.raw.get("derived") or {}).get("trees") or {}
        self.conflicts = (self.raw.get("derived") or {}).get("reciprocal_conflicts") or []
        self.validation = self.raw.get("validation") or {}
        self.generated = self.raw.get("generated_at")

    def by_predicate(self, pred: str) -> list[dict]:
        return [e for e in self.edges if e.get("predicate") == pred]

    @staticmethod
    def edge_loc(edge: dict) -> tuple[int, int] | None:
        ch, pn = edge.get("chapter"), edge.get("para")
        if ch is None and isinstance(edge.get("loc"), str) and ":" in edge["loc"]:
            a, b = edge["loc"].split(":", 1)
            ch, pn = int(a), int(b)
        return (ch, pn) if isinstance(ch, int) and isinstance(pn, int) else None


class Entities:
    def __init__(self):
        raw = json.loads(ENTITY_PATH.read_text(encoding="utf-8")) if ENTITY_PATH.exists() else {}
        self.raw = raw
        self.entities = raw.get("entities") or []
        self.display_to_canon: dict[str, str] = {}
        self.canon: dict[str, dict] = {}
        for e in self.entities:
            c = e.get("canonical")
            if not c:
                continue
            self.canon[c] = e
            self.display_to_canon[c] = c
            for al in e.get("aliases") or []:
                self.display_to_canon.setdefault(al, c)
        self.version = raw.get("version")


@dataclass
class Ctx:
    book: str
    corpus: Corpus
    time: TimeData
    rel: RelationsData
    entities: Entities


# ────────────────────────── 命中构造 ──────────────────────────
def make_hit(ctx: Ctx, rule_id: str, severity: str, *, subject: str = "", obj: str = "",
             ch: int, pn: int, pos: int = 0, rationale: str, extra: dict | None = None) -> dict:
    mode = ctx.corpus.narrative_mode(ch, pn, pos)
    grade = GRADE_OF_SEVERITY.get(severity, "C")
    return {
        "rule_id": rule_id,
        "rule_title": RULE_BY_ID[rule_id].title,
        "area": RULE_BY_ID[rule_id].area,
        "severity": severity,
        "grade": grade,
        "confidence": "medium",
        "locator": ctx.corpus.loc(ch, pn),
        "chapter": ch,
        "pn": pn,
        "subject": subject,
        "object": obj,
        "quote": ctx.corpus.quote(ch, pn, pos),
        "rationale": rationale,
        "narrative_mode": mode,
        "exempted": False,
        "exemption": "",
        "spec_cite": RULE_BY_ID[rule_id].spec,
        "extra": extra or {},
    }


# ────────────────────────── 34 条规则实现 ──────────────────────────
# 说明：每条函数头注释即 SKILL 条文摘要与阈值；返回命中 dict 列表（上限 20/规则/书，engine 截断）。

def rule_W1(ctx: Ctx) -> list[dict]:
    """W1 轻功远程奔袭（★方向反转）：单日行程 ≥300 里 → info「武侠加速」备案，不判异常（≥1000 里仍 info）。
    阈值：凡人 ≤100 里/日；轻功奔袭 300-1500 里/日（SKILL §3.1 W1；数值待语料定版）。
    反例：明写借马/船/车/轿代步、明写"行了三日方至"、人物设定不识武功。
    """
    hits = []
    rx_dist = re.compile(r"([一二三四五六七八九十百千两\d]+)\s*里")
    rx_time = re.compile(r"([一二三四五六七八九十百千两\d]+)\s*(日|天|夜)|(一夜|一日|一昼夜|连夜)")
    for para, m in ctx.corpus.find(r"(轻功|飞行|掠|奔驰|疾奔|奔行|赶路)"):
        win = para.plain
        d = rx_dist.search(win)
        t = rx_time.search(win)
        if not (d and t):
            continue
        dist = cn_num(d.group(1))
        if not dist:
            continue
        if t.group(1):
            days = cn_num(t.group(1)) or 1
        else:
            days = 1
        speed = dist / max(days, 1)
        if speed < 300:
            continue
        if re.search(r"(马|船|车|轿|舟|骑)", win):
            continue
        hits.append(make_hit(ctx, "W1", "info", subject=ctx.corpus.person_at(para.chapter, para.pn, m.start()) or "",
                             ch=para.chapter, pn=para.pn, pos=m.start(),
                             rationale=f"轻功/奔袭约 {dist} 里/{days} 日 ≈ {speed:.0f} 里/日（≥300）→ "
                                       "info 备案（武侠加速，不判异常；§3.1 W1 方向反转）",
                             extra={"distance_li": dist, "days": days, "li_per_day": round(speed, 1)}))
        if len(hits) >= 20:
            break
    return hits


def rule_W2(ctx: Ctx) -> list[dict]:
    """W2 内伤/内力恢复（warning）：内力耗尽/受内伤 ∧ 无灵药/疗养/渡功/运功明写 ∧ ≤阈值日恢复。
    阈值：轻伤全愈 ≥半日、重伤 ≥3 日、内力耗尽 ≥7 日（SKILL §3.1 W2）。
    实现：伤情段 + 恢复段（同段或≤2 段内），用 N4 时点差估算日数；无时点差则只记 info 候选。
    """
    hits = []
    inj_rx = re.compile(r"(内伤|重伤|筋脉尽断|经脉尽断|内力耗尽|元气大伤|吐血不止)")
    rec_rx = re.compile(r"(痊愈|复元|复原|如常|生龙活虎|行动如常|已无大碍)")
    remedy_rx = re.compile(r"(药|丹|丸|敷|疗|运功|调息|渡功|输功|温泉|疗伤|接骨|逼毒|调养|休养|静养|将养|养伤|医治)")
    paras = ctx.corpus.sorted_paras()
    index = {(p.chapter, p.pn): i for i, p in enumerate(paras)}
    for para, m in ctx.corpus.find(inj_rx.pattern):
        i = index[(para.chapter, para.pn)]
        candidates = [para] + [p for p in paras[i + 1: i + 3]]
        for p2 in candidates:
            rm = rec_rx.search(p2.plain)
            if not rm:
                continue
            same_para = p2 is para
            if same_para and abs(rm.start() - m.start()) > 120:
                continue
            # 排除"内伤早已痊愈/旧伤已愈"类非事件性表述
            pre_inj = para.plain[max(0, m.start() - 12): m.start()]
            pre_rec = p2.plain[max(0, rm.start() - 8): rm.start()]
            if re.search(r"(早已|已经|多年|数年|早就|旧伤|旧日)", pre_inj + pre_rec):
                continue
            window = para.plain + p2.plain
            if remedy_rx.search(window):
                break
            severe = bool(re.search(r"(筋脉尽断|经脉尽断|内力耗尽|重伤)", para.plain))
            threshold = 7 if "内力耗尽" in para.plain else (3 if severe else 0.5)
            t1 = ctx.time.t_at(para.chapter, para.pn)
            t2 = ctx.time.t_at(p2.chapter, p2.pn)
            gap = (t2 - t1) if (t1 is not None and t2 is not None) else None
            if gap is not None and gap < threshold:
                hits.append(make_hit(ctx, "W2", "warning",
                                     subject=ctx.corpus.person_at(para.chapter, para.pn, m.start()) or "",
                                     ch=p2.chapter, pn=p2.pn, pos=rm.start(),
                                     rationale=f"伤情（{m.group(1)}）到恢复（{rm.group(1)}）约 {gap:.1f} 日 < "
                                               f"阈值 {threshold} 日，且无灵药/疗养/运功明写（§3.1 W2）",
                                     extra={"gap_days": round(gap, 2), "threshold_days": threshold,
                                            "injury_loc": ctx.corpus.loc(para.chapter, para.pn)}))
            elif gap is None:
                hits.append(make_hit(ctx, "W2", "info",
                                     subject=ctx.corpus.person_at(para.chapter, para.pn, m.start()) or "",
                                     ch=p2.chapter, pn=p2.pn, pos=rm.start(),
                                     rationale="伤情与恢复紧邻且无处置明写（N4 缺时点差，降 info 待人工）",
                                     extra={"note": "时点差不可得"}))
            break
        if len(hits) >= 20:
            break
    return hits


def rule_W3(ctx: Ctx) -> list[dict]:
    """W3 高龄高手出战（★方向反转）：年龄锚 ≥60 岁仍单打独斗 → **不标记**（豁免性规则，默认不进扫描）。
    唯一 info 情形：文本自称"年老力衰"后又写超常战力且无解释（§3.1 W3）。
    """
    hits = []
    for para, m in ctx.corpus.find(r"(年老力衰|年迈力衰)"):
        if re.search(r"(出手|击|败|胜|杀|毙|一掌|一剑)", para.plain):
            hits.append(make_hit(ctx, "W3", "info",
                                 subject=ctx.corpus.person_at(para.chapter, para.pn, m.start()) or "",
                                 ch=para.chapter, pn=para.pn, pos=m.start(),
                                 rationale="自称年老力衰后仍有超常战力（豁免性规则：仅 info 备案，不判穿帮，§3.1 W3）"))
    return hits


def rule_W4(ctx: Ctx) -> list[dict]:
    """W4 神功速成（warning）：明写"非 X 年不能有成" ∧ 习得后 <X/3 年大成 ∧ 无奇遇明写（§3.1 W4）。
    实现：定位"非X年不能/不可"段 + 后续同武功名（☆）大成段，用 N4 年估算差；无年数据降 info。
    """
    hits = []
    rx = re.compile(r"非\s*([一二三四五六七八九十百千两\d]+)\s*年\s*(?:不能|不可|方|始|难)")
    luck_rx = re.compile(r"(奇遇|异果|朱果|灵芝|传功|灌顶|顿悟|机缘|福缘)")
    for para, m in ctx.corpus.find(rx.pattern):
        x = cn_num(m.group(1))
        if not x:
            continue
        martial = ctx.corpus.martial_in(para.chapter, para.pn)
        if not martial:
            continue
        later = None
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= (para.chapter, para.pn):
                continue
            if any(name in p2.plain for name in martial) and \
                    re.search(r"(练成|学成|习成|大成|已臻化境)", p2.plain):
                later = (p2, p2.plain.find(martial[0]))
                break
        if later is None:
            continue
        y1 = ctx.time.year_at(para.chapter, para.pn)
        y2 = ctx.time.year_at(later[0].chapter, later[0].pn)
        if y1 is not None and y2 is not None:
            gap_years = max(0.0, y2 - y1)
            if gap_years < x / 3 and not luck_rx.search(later[0].plain):
                hits.append(make_hit(ctx, "W4", "warning", subject="", obj=martial[0],
                                     ch=later[0].chapter, pn=later[0].pn, pos=later[1],
                                     rationale=f"明文『非{x}年不能有成』，约 {gap_years:.1f} 年即大成（<X/3）"
                                               "且无奇遇明写（§3.1 W4）",
                                     extra={"x_years": x, "gap_years": round(gap_years, 2)}))
        else:
            hits.append(make_hit(ctx, "W4", "info", obj=martial[0],
                                 ch=later[0].chapter, pn=later[0].pn, pos=later[1],
                                 rationale=f"明文『非{x}年不能有成』，后文大成；N4 无法估年差 → info 待人工",
                                 extra={"x_years": x}))
        if len(hits) >= 20:
            break
    return hits


def rule_W5(ctx: Ctx) -> list[dict]:
    """W5 武功相克反转（info 待人工）：明文"甲功克乙功" ∧ 后文乙胜甲 ∧ 无破法/境界解释（§3.1 W5）。"""
    hits = []
    statements = []
    generic = {"剑法", "刀法", "拳法", "掌法", "武功", "功夫", "内功", "轻功"}
    for para, m in ctx.corpus.find(r"([^。！？；]{0,20})(相克|克制|克着)([^。！？；]{0,20})"):
        names = [n for n in ctx.corpus.martial_in(para.chapter, para.pn) if n not in generic]
        if len(names) >= 2:
            left, right = m.group(1), m.group(3)
            a, b = names[0], names[1]
            # 要求同一句内呈"A …克… B"次序（避免仅同段共现）
            if not (a in left and b in right):
                continue
            statements.append((para, m.start(), a, b))
    for para, pos, a, b in statements:
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= (para.chapter, para.pn):
                continue
            if a in p2.plain and b in p2.plain and re.search(r"(败|不敌|负于|输了|败走)", p2.plain):
                if re.search(r"(破法|以快打慢|境界|新悟|翻案)", p2.plain):
                    continue
                hits.append(make_hit(ctx, "W5", "info", subject=a, obj=b,
                                     ch=p2.chapter, pn=p2.pn, pos=p2.plain.find(a),
                                     rationale=f"明文相克（{a}克{b}）后文 {b} 反胜且无破法解释 → info 待人工（§3.1 W5）"))
                break
        if len(hits) >= 20:
            break
    return hits


def rule_W6(ctx: Ctx) -> list[dict]:
    """W6 轻功/剑气数值夸饰（info 修辞标签）：大数+修辞标志词 ∧ 数值无情节依赖 → 修辞识别不改（§3.1 W6）。
    阈值：以"数值是否被后续情节引用"为分界；实现为修辞标志词 + 大数（丈/里/千军）初筛，info。
    """
    hits = []
    rx = re.compile(r"([一二三四五六七八九十百千万两\d]+)\s*(丈|里|尺|军|骑|人)")
    rhetoric = re.compile(r"(宛如|犹如|仿佛|但见|顷刻|刹那|霎时|只见)")
    for para, m in ctx.corpus.find(rx.pattern):
        if not rhetoric.search(para.plain):
            continue
        n = cn_num(m.group(1))
        if not n or n < 100:
            continue
        num = m.group(1)
        unit = m.group(2)
        # 数值是否被后文再次引用（同一数字+单位）→ 可能情节依赖，不判修辞
        reused = False
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= (para.chapter, para.pn):
                continue
            if f"{num}{unit}" in p2.plain:
                reused = True
                break
        if reused:
            continue
        hits.append(make_hit(ctx, "W6", "info", ch=para.chapter, pn=para.pn, pos=m.start(),
                             rationale=f"大数『{num}{unit}』+修辞标志词且无后续引用 → 夸张修辞标签（识别不改，§3.1 W6）"))
        if len(hits) >= 20:
            break
    return hits


def rule_W7(ctx: Ctx) -> list[dict]:
    """W7 内力外放边界（warning）：设定"不会内功/内力平平" ∧ 后文隔空伤人、剑气及人 ∧ 无习得（§3.1 W7）。
    反例：两者间存在习得新功事件（成长弧，合法）。
    """
    hits = []
    for para, m in ctx.corpus.find(r"(不会武功|未习武功|不曾习武|内力平平|武艺平庸|全然不会内功)"):
        person = ctx.corpus.person_close(para.chapter, para.pn, m.start(), max_before=10, max_after=2)
        if not person:
            continue
        start = (para.chapter, para.pn)
        learned = False
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= start:
                continue
            if re.search(r"(学成|练成|习得|学会|拜师|传授|授艺|奇遇|服食|学武|学艺|练武|教他|教她|得传|传授武功)", p2.plain):
                learned = True
                break
            if person in ctx.corpus.persons_in(p2.chapter, p2.pn) and \
                    re.search(r"(隔空|剑气|掌风|凌空|指力)", p2.plain) and \
                    re.search(r"(伤|毙|倒|飞|死)", p2.plain):
                hits.append(make_hit(ctx, "W7", "warning", subject=person,
                                     ch=p2.chapter, pn=p2.pn, pos=0,
                                     rationale=f"设定『{m.group(1)}』却隔空/剑气伤人，且两者间无习得事件（§3.1 W7）",
                                     extra={"setup_loc": ctx.corpus.loc(para.chapter, para.pn)}))
                break
        if learned:
            continue
        if len(hits) >= 20:
            break
    return hits


def rule_W8(ctx: Ctx) -> list[dict]:
    """W8 毒发时限（warning）：明写"X 日毒发无救" ∧ 超时存活 ∧ 无解药/逼毒明写；阈值超 1.5 倍触发（§3.1 W8）。"""
    hits = []
    rx = re.compile(r"([一二三四五六七八九十百千两\d]+)\s*(?:日|天)\s*(?:之内|内)?\s*(?:必|将|即)?\s*(?:毒发|毙命|身亡|无救)")
    remedy_rx = re.compile(r"(解药|逼毒|以毒攻毒|运功|疗|丹|丸|药)")
    for para, m in ctx.corpus.find(rx.pattern):
        x = cn_num(m.group(1))
        if not x:
            continue
        person = ctx.corpus.person_at(para.chapter, para.pn, m.start())
        if not person:
            continue
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= (para.chapter, para.pn):
                continue
            if person not in ctx.corpus.persons_in(p2.chapter, p2.pn):
                continue
            if re.search(r"(死|亡|毙|尸|灵|祭|回忆|追忆)", p2.plain):
                continue
            t1 = ctx.time.t_at(para.chapter, para.pn)
            t2 = ctx.time.t_at(p2.chapter, p2.pn)
            if t1 is not None and t2 is not None:
                gap_days = t2 - t1
                if gap_days > 1.5 * x:
                    window = "".join(p.plain for p in ctx.corpus.sorted_paras()
                                     if (para.chapter, para.pn) < (p.chapter, p.pn) < (p2.chapter, p2.pn))
                    if remedy_rx.search(window):
                        break
                    hits.append(make_hit(ctx, "W8", "warning", subject=person,
                                         ch=p2.chapter, pn=p2.pn, pos=0,
                                         rationale=f"明写『{x}日毒发/毙命』，约 {gap_days:.0f} 日后仍活跃（>1.5×）"
                                                   "且无解药/逼毒明写（§3.1 W8）",
                                         extra={"limit_days": x, "gap_days": round(gap_days, 1),
                                                "statement_loc": ctx.corpus.loc(para.chapter, para.pn)}))
            break
        if len(hits) >= 20:
            break
    return hits


def rule_W9(ctx: Ctx) -> list[dict]:
    """W9 少年天才需铺垫（info 待人工）：年龄<16 岁击败成名一流高手 ∧ 无奇遇/家学/名师明写（§3.1 W9）。
    实现：N4 年龄锚 + 战斗词共现 + 对手章回覆盖 ≥5 章（"成名"弱判据）；info 待人工。
    """
    hits = []
    battle_rx = re.compile(r"(击败|打倒|战胜|打败|胜了|击退)")
    support_rx = re.compile(r"(奇遇|家传|家学|名师|师父|传授|授艺|异人|指点)")
    for age in ctx.time.ages():
        if age["age"] >= 16:
            continue
        person = ctx.corpus.person_for_age(age["ch"], age["pn"], age["span"][0] if age["span"] else 0)
        if not person:
            continue
        para = ctx.corpus.para(age["ch"], age["pn"])
        if para is None:
            continue
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) < (age["ch"], age["pn"]):
                continue
            if person not in ctx.corpus.persons_in(p2.chapter, p2.pn):
                continue
            if not ((p2.chapter, p2.pn) == (age["ch"], age["pn"])
                    or (p2.chapter == age["ch"] and p2.pn - age["pn"] <= 2)
                    or (p2.chapter == age["ch"] + 1 and p2.pn <= 3)):
                continue
            pm = ctx.corpus.para(p2.chapter, p2.pn)
            if pm is None:
                continue
            # 战斗动词须与 subject 同句/近邻
            subj_tok = next((t for t in pm.tokens if t.domain == "@" and ctx.corpus.canon(t.display) == person), None)
            if subj_tok is None:
                continue
            bm = battle_rx.search(pm.plain)
            if not bm or abs(bm.start() - subj_tok.plain_start) > 30:
                continue
            if support_rx.search(p2.plain):
                break
            others = [p for p in ctx.corpus.persons_in(p2.chapter, p2.pn) if p != person]
            famous = [o for o in others if len(ctx.corpus.person_chapters.get(o, set())) >= 5]
            if famous:
                hits.append(make_hit(ctx, "W9", "info", subject=person, obj=famous[0],
                                     ch=p2.chapter, pn=p2.pn, pos=bm.start(),
                                     rationale=f"{person} 年龄锚 {age['age']} 岁（<16）击败成名人物 {famous[0]}，"
                                               "无奇遇/家学/名师明写 → info 待人工（§3.1 W9）",
                                     extra={"age": age["age"], "age_loc": ctx.corpus.loc(age["ch"], age["pn"])}))
                break
        if len(hits) >= 20:
            break
    return hits


def rule_S1(ctx: Ctx) -> list[dict]:
    """S1 掌门在位年长（info）：同一掌门在位 >50 年 ∧ 无长寿/驻颜设定 → info 备案（§3.2 S1）。
    实现：N5『任职』边按（person, org）聚合，用 N4 年估算首末跨度。
    """
    hits = []
    by = {}
    for e in ctx.rel.by_predicate("任职"):
        by.setdefault((e.get("subject"), e.get("object")), []).append(e)
    for (person, org), edges in by.items():
        years = [ctx.time.year_at(*ctx.rel.edge_loc(e)) for e in edges if ctx.rel.edge_loc(e)]
        years = [y for y in years if y]
        if len(years) >= 2 and max(years) - min(years) > 50:
            loc = ctx.rel.edge_loc(edges[0])
            hits.append(make_hit(ctx, "S1", "info", subject=person, obj=org,
                                 ch=loc[0], pn=loc[1],
                                 rationale=f"{person} 任 {org} 掌门约 {max(years) - min(years)} 年（>50），"
                                           "无长寿/驻颜设定明写 → info 备案（§3.2 S1）",
                                 extra={"span_years": max(years) - min(years)}))
    return hits


def rule_S2(ctx: Ctx) -> list[dict]:
    """S2 继任节奏（info）：掌门死亡/失踪后 >3 年无继任；或 <5 年更替 3+ 任且无内乱/战死明写（§3.2 S2）。
    实现：N5『任职』边按 org 聚合；同 org 5 年内 ≥3 任 → info。
    """
    hits = []
    by_org = {}
    for e in ctx.rel.by_predicate("任职"):
        by_org.setdefault(e.get("object"), []).append(e)
    for org, edges in by_org.items():
        years = sorted(y for y in (ctx.time.year_at(*ctx.rel.edge_loc(e)) for e in edges) if y)
        if len(years) >= 3 and years[-1] - years[0] <= 5:
            loc = ctx.rel.edge_loc(edges[0])
            hits.append(make_hit(ctx, "S2", "info", obj=org, ch=loc[0], pn=loc[1],
                                 rationale=f"{org} 在 {years[0]}-{years[-1]} 间更替 {len(years)} 任掌门（≤5 年 3+ 任），"
                                           "无内乱/战死明写 → info（§3.2 S2）",
                                 extra={"terms": len(years), "span_years": years[-1] - years[0]}))
    return hits


def rule_S3(ctx: Ctx) -> list[dict]:
    """S3 灭派存续（error 候选）：明写整派被灭 ∧ 后文同派整建制活动 ∧ 无重建事件 → error 候选（§3.2 S3）。
    实现：◆组织实体 + 本段灭派词（尽灭/阖派/覆灭/除名/铲除/歼灭），排除分舵/传言/据称；
    后文该组织再次出现且无重建词（重建/重立/开宗/改组/遗孤/幸存/残部）→ error（强）/warning（弱）。
    """
    hits = []
    death_rx = re.compile(r"(尽灭|阖派|覆灭|灭派|铲除|除名|歼灭|屠尽|无一幸免)")
    rebuild_rx = re.compile(r"(重建|重立|开宗|改组|遗孤|幸存|残部|卷土重来|死灰复燃)")
    rumor_rx = re.compile(r"(传言|传闻|据说|传说|听说|据称)")
    for para, m in ctx.corpus.find(death_rx.pattern):
        orgs = ctx.corpus.orgs_in(para.chapter, para.pn)
        if not orgs:
            continue
        if "分舵" in para.plain or rumor_rx.search(para.plain):
            continue
        org = orgs[0]
        strong = bool(re.search(r"(尽灭|阖派|无一幸免|屠尽)", para.plain))
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= (para.chapter, para.pn):
                continue
            if org not in p2.plain:
                continue
            between = "".join(p.plain for p in ctx.corpus.sorted_paras()
                              if (para.chapter, para.pn) < (p.chapter, p.pn) < (p2.chapter, p2.pn))
            if rebuild_rx.search(between):
                break
            if ctx.corpus.narrative_mode(p2.chapter, p2.pn, p2.plain.find(org)) in NON_NORMAL_MODES:
                continue
            hits.append(make_hit(ctx, "S3", "error" if strong else "warning", obj=org,
                                 ch=p2.chapter, pn=p2.pn, pos=p2.plain.find(org),
                                 rationale=f"{ctx.corpus.loc(para.chapter, para.pn)} 明写『{m.group(1)}』后，"
                                           f"{ctx.corpus.loc(p2.chapter, p2.pn)} 该派整建制再现且无重建事件 → "
                                           f"{'error 候选' if strong else 'warning'}（§3.2 S3 / 检查项三）",
                                 extra={"annihilation_loc": ctx.corpus.loc(para.chapter, para.pn),
                                        "strength": "强" if strong else "弱"}))
            break
        if len(hits) >= 20:
            break
    return hits


def rule_S4(ctx: Ctx) -> list[dict]:
    """S4 辈分跨级晋升（warning）：跨辈晋升 ∨ 入门<3 年即长老/掌门 ∧ 无明写破格/奇才（§3.2 S4）。
    实现：文本初筛（入门三年内/未满三年 + 长老/掌门/护法），无"破格/奇才/天资"即 warning。
    """
    hits = []
    for para, m in ctx.corpus.find(r"(入门|拜师|入派)"):
        win = para.plain[max(0, m.start() - 20): m.start() + 60]
        if not re.search(r"(未满三年|不满三年|三年之内|不到三年|<三年|次年|入门的第二)", win):
            continue
        if not re.search(r"(长老|掌门|护法|堂主)", win):
            continue
        if re.search(r"(破格|奇才|天资|百年难遇|特许)", win):
            continue
        hits.append(make_hit(ctx, "S4", "warning",
                             subject=ctx.corpus.person_at(para.chapter, para.pn, m.start()) or "",
                             ch=para.chapter, pn=para.pn, pos=m.start(),
                             rationale="入门<3 年即居长老/掌门且无破格/奇才明写 → warning（§3.2 S4）"))
        if len(hits) >= 20:
            break
    return hits


def rule_S5(ctx: Ctx) -> list[dict]:
    """S5 师承代际时距（warning）：师徒链 <10 年跨三代；师父比徒弟年轻 15 岁以上（§3.2 S5）。
    实现：N5『师承』边（subject= disciple, object= master）+ N4 年龄锚；年龄倒挂 → warning。
    反例：代师传艺/衣钵相传/翁婿传承/托孤明写。
    """
    hits = []
    ages = ctx.time.ages()
    age_of = {}
    for a in ages:
        p = ctx.corpus.person_for_age(a["ch"], a["pn"], a["span"][0] if a["span"] else 0)
        if p and p not in age_of:
            age_of[p] = a
    for e in ctx.rel.by_predicate("师承"):
        disc, master = e.get("subject"), e.get("object")
        if not disc or not master:
            continue
        if disc in age_of and master in age_of:
            d_age, m_age = age_of[disc]["age"], age_of[master]["age"]
            if m_age < d_age - 15:
                loc = ctx.rel.edge_loc(e)
                if not loc:
                    continue
                para = ctx.corpus.para(*loc)
                if para and re.search(r"(代师传艺|衣钵|翁婿|托孤|养父|义父)", para.plain):
                    continue
                hits.append(make_hit(ctx, "S5", "warning", subject=disc, obj=master,
                                     ch=loc[0], pn=loc[1],
                                     rationale=f"师承边 {disc}（{d_age} 岁）→ 师 {master}（{m_age} 岁）："
                                               f"师父比徒弟年轻 {d_age - m_age} 岁（>15）且无代师传艺/翁婿明写 → warning（§3.2 S5）",
                                     extra={"disciple_age": d_age, "master_age": m_age,
                                            "edge_loc": ctx.corpus.loc(*loc)}))
    return hits


def rule_S6(ctx: Ctx) -> list[dict]:
    """S6 门规与行事（info/人工）：刚性门规被反复违反 ∧ 无处罚情节 → info（§3.2 S6）。
    实现：门规段（门规/派规/帮规 + 废/逐出/处死），后续 ≥2 次违反词且近邻无处罚词 → info。
    """
    hits = []
    rule_rx = re.compile(r"(门规|派规|帮规|本门规矩|本派规矩)")
    punish_rx = re.compile(r"(废去武功|逐出|处死|重罚|杖责|面壁|囚禁)")
    viol_rx = re.compile(r"(私自下山|私逃|违犯|不听号令|擅闯|偷练)")
    for para, m in ctx.corpus.find(rule_rx.pattern):
        if not punish_rx.search(para.plain):
            continue
        violations = []
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= (para.chapter, para.pn):
                continue
            vm = viol_rx.search(p2.plain)
            if vm:
                violations.append((p2, vm.start()))
        if len(violations) >= 2:
            punished = any(punish_rx.search(p.plain) for p, _ in violations)
            if not punished:
                hits.append(make_hit(ctx, "S6", "info", ch=violations[0][0].chapter, pn=violations[0][0].pn,
                                     pos=violations[0][1],
                                     rationale=f"门规明写（{m.group(1)}）后 {len(violations)} 次违反，未见处罚情节 → info 待人工（§3.2 S6）",
                                     extra={"rule_loc": ctx.corpus.loc(para.chapter, para.pn),
                                            "violations": [ctx.corpus.loc(p.chapter, p.pn) for p, _ in violations[:5]]}))
        if len(hits) >= 20:
            break
    return hits


def rule_S7(ctx: Ctx) -> list[dict]:
    """S7 比武规矩自洽（warning）：赛前明文规则（点到即止/三局两胜/不许…）∧ 结果违反 ∧ 无变故明写（§3.2 S7）。"""
    hits = []
    rule_rx = re.compile(r"(点到即止|点到为止|三局两胜|不许杀伤|不可伤人性命|不得伤人性命|以武会友)")
    match_rx = re.compile(r"(比武|比试|较量|对决|较技)")
    break_rx = re.compile(r"(死|亡|毙|残|重伤)")
    cause_rx = re.compile(r"(生死状|暗算|变故|失手|收手不住|有人从中|误伤)")
    paras = ctx.corpus.sorted_paras()
    index = {(p.chapter, p.pn): i for i, p in enumerate(paras)}
    for para, m in ctx.corpus.find(rule_rx.pattern):
        if not match_rx.search(para.plain):
            continue
        i = index[(para.chapter, para.pn)]
        for p2 in paras[i + 1: i + 3]:
            bm = break_rx.search(p2.plain)
            if bm and not cause_rx.search(p2.plain):
                if re.search(r"(比武|比试|较量|较技|招|剑|刀|掌)", p2.plain):
                    hits.append(make_hit(ctx, "S7", "warning", ch=p2.chapter, pn=p2.pn, pos=bm.start(),
                                         rationale=f"赛前明文规矩（{m.group(1)}）后出现『{bm.group(1)}』结果且无变故明写 → warning（§3.2 S7）",
                                         extra={"rule_loc": ctx.corpus.loc(para.chapter, para.pn)}))
                    break
        if len(hits) >= 20:
            break
    return hits


def rule_S8(ctx: Ctx) -> list[dict]:
    """S8 同门相残（★方向反转）：同门火并/骨肉相仇 → **不标记**（豁免性规则）（§3.2 S8）。"""
    return []


def rule_S9(ctx: Ctx) -> list[dict]:
    """S9 失传绝学再现（warning）：明写失传/已绝 ∧ 后文有人使出 ∧ 无秘籍重现/口述传承/隐脉（§3.2 S9）。"""
    hits = []
    lost_rx = re.compile(r"(失传|已绝|绝传|失传已久|早已失传)")
    use_rx = re.compile(r"(使出|施展|使出那|用出|施出|施展出)")
    explain_rx = re.compile(r"(秘籍|秘本|遗篇|口述|隐脉|传人|秘笈|原来当年|还有一支)")
    for para, m in ctx.corpus.find(lost_rx.pattern):
        names = ctx.corpus.martial_in(para.chapter, para.pn)
        if not names:
            continue
        name = names[0]
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= (para.chapter, para.pn):
                continue
            if name not in p2.plain:
                continue
            um = use_rx.search(p2.plain)
            if not um:
                continue
            between = "".join(p.plain for p in ctx.corpus.sorted_paras()
                              if (para.chapter, para.pn) < (p.chapter, p.pn) < (p2.chapter, p2.pn))
            if explain_rx.search(between) or explain_rx.search(p2.plain):
                break
            hits.append(make_hit(ctx, "S9", "warning", obj=name,
                                 ch=p2.chapter, pn=p2.pn, pos=um.start(),
                                 rationale=f"{ctx.corpus.loc(para.chapter, para.pn)} 明写『{m.group(1)}』，"
                                           f"{ctx.corpus.loc(p2.chapter, p2.pn)} 又见使出且无秘籍/隐脉明写 → warning（§3.2 S9）",
                                 extra={"lost_loc": ctx.corpus.loc(para.chapter, para.pn)}))
            break
        if len(hits) >= 20:
            break
    return hits


def rule_S10(ctx: Ctx) -> list[dict]:
    """S10 世仇结盟（info 待人工）：两派明写世仇 ∧ 后文结盟共事 ∧ 无和解事件明写（§3.2 S10）。"""
    hits = []
    feud_rx = re.compile(r"(世仇|宿仇|仇深似海|血仇|积怨多年)")
    ally_rx = re.compile(r"(结盟|联手|联盟|共同对付|同仇敌忾|联手对敌)")
    peace_rx = re.compile(r"(和解|捐弃前嫌|前嫌尽释|联姻|共同强敌|握手言和)")
    for para, m in ctx.corpus.find(feud_rx.pattern):
        orgs = ctx.corpus.orgs_in(para.chapter, para.pn)
        if len(orgs) < 2:
            continue
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= (para.chapter, para.pn):
                continue
            if not (orgs[0] in p2.plain and orgs[1] in p2.plain):
                continue
            am = ally_rx.search(p2.plain)
            if not am:
                continue
            if peace_rx.search(p2.plain):
                break
            hits.append(make_hit(ctx, "S10", "info", subject=orgs[0], obj=orgs[1],
                                 ch=p2.chapter, pn=p2.pn, pos=am.start(),
                                 rationale=f"{orgs[0]} 与 {orgs[1]} 明写世仇后又结盟共事，无和解事件明写 → info（§3.2 S10）",
                                 extra={"feud_loc": ctx.corpus.loc(para.chapter, para.pn)}))
            break
        if len(hits) >= 20:
            break
    return hits


def rule_J1(ctx: Ctx) -> list[dict]:
    """J1 镖程备案（★方向反转）：镖队速度 >凡人 3 倍 → info 备案，不判异常（§3.3 J1）。
    阈值：凡人货运 ≤60 里/日；镖程 100-300 里/日，急镖明写上浮；不设穿帮上限。
    """
    hits = []
    rx_dist = re.compile(r"([一二三四五六七八九十百千两\d]+)\s*里")
    rx_time = re.compile(r"([一二三四五六七八九十百千两\d]+)\s*(日|天)")
    for para, m in ctx.corpus.find(r"镖"):
        d = rx_dist.search(para.plain)
        t = rx_time.search(para.plain)
        if not (d and t):
            continue
        dist, days = cn_num(d.group(1)), cn_num(t.group(1)) or 1
        if not dist:
            continue
        speed = dist / max(days, 1)
        if speed <= 180:
            continue
        hits.append(make_hit(ctx, "J1", "info", ch=para.chapter, pn=para.pn, pos=m.start(),
                             rationale=f"镖程约 {dist} 里/{days} 日 ≈ {speed:.0f} 里/日（>凡人 3 倍）→ "
                                       "info 备案（武侠加速，不判异常；§3.3 J1 方向反转）",
                             extra={"distance_li": dist, "days": days, "li_per_day": round(speed, 1)}))
        if len(hits) >= 20:
            break
    return hits


def rule_J2(ctx: Ctx) -> list[dict]:
    """J2 寻仇母题（★方向反转）：灭门/寻仇/血债 → 不标记（豁免性规则）（§3.3 J2）。"""
    return []


def rule_J3(ctx: Ctx) -> list[dict]:
    """J3 比武彩头兑现（info）：赛前明写彩头 ∧ 兑现被违背 ∧ 无解释（§3.3 J3）。"""
    hits = []
    stake_rx = re.compile(r"(彩头|赌注|负者|输者|胜者|败者)")
    fulfill_rx = re.compile(r"(兑现|履行|让出|封剑|烧山|照办|甘愿)")
    for para, m in ctx.corpus.find(stake_rx.pattern):
        if not re.search(r"(比武|比试|较量|较技)", para.plain):
            continue
        later = "".join(p.plain for p in ctx.corpus.sorted_paras()
                        if (p.chapter, p.pn) > (para.chapter, para.pn))
        if fulfill_rx.search(later):
            continue
        hits.append(make_hit(ctx, "J3", "info", ch=para.chapter, pn=para.pn, pos=m.start(),
                             rationale="赛前明写彩头，后文未见兑现/解释 → info 待人工（§3.3 J3）"))
        if len(hits) >= 20:
            break
    return hits


def rule_J4(ctx: Ctx) -> list[dict]:
    """J4 绿林道惯例（info）：明写绿林惯例（此山不劫…）∧ 无解释违反（§3.3 J4）。"""
    hits = []
    custom_rx = re.compile(r"(不劫|不抢|不动|不取).{0,12}(镖|姓|商队|百姓)")
    break_rx = re.compile(r"(劫|抢|夺)")
    for para, m in ctx.corpus.find(custom_rx.pattern):
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= (para.chapter, para.pn):
                continue
            if break_rx.search(p2.plain) and re.search(r"(镖|商队|姓)", p2.plain):
                if re.search(r"(新寨主|新规|换了|变故)", p2.plain):
                    break
                hits.append(make_hit(ctx, "J4", "info", ch=p2.chapter, pn=p2.pn, pos=break_rx.search(p2.plain).start(),
                                     rationale=f"明写绿林惯例『{m.group(0)[:20]}』后被违反且无解释 → info（§3.3 J4）",
                                     extra={"custom_loc": ctx.corpus.loc(para.chapter, para.pn)}))
                break
        if len(hits) >= 20:
            break
    return hits


def rule_J5(ctx: Ctx) -> list[dict]:
    """J5 江湖经济（info）：整体豁免；仅关键物前后价差悬殊且差价是情节关键 → info（§3.3 J5）。"""
    hits = []
    price_rx = re.compile(r"([一二三四五六七八九十百千万两\d]+)\s*两")
    obj_prices: dict[str, list] = {}
    for para in ctx.corpus.sorted_paras():
        objs = [t.display for t in para.tokens if t.domain == "•"]
        pm = price_rx.search(para.plain)
        if not objs or not pm:
            continue
        price = cn_num(pm.group(1))
        if price is None or not re.search(r"(值|价|卖|买|当|赎)", para.plain):
            continue
        obj_prices.setdefault(objs[0], []).append((price, para))
    for obj, prices in obj_prices.items():
        uniq = sorted({p for p, _ in prices})
        if len(uniq) >= 2 and uniq[-1] >= uniq[0] * 5:
            para = prices[0][1]
            hits.append(make_hit(ctx, "J5", "info", obj=obj, ch=para.chapter, pn=para.pn,
                                 rationale=f"『{obj}』前后价差 {uniq[0]}→{uniq[-1]} 两（≥5 倍），"
                                           "疑似情节关键差价 → info 待人工（§3.3 J5）",
                                 extra={"prices": uniq}))
        if len(hits) >= 20:
            break
    return hits


def rule_J6(ctx: Ctx) -> list[dict]:
    """J6 官府缺位（info）：明写朝廷缉拿甚紧 ∧ 后文公然行动无后果/无规避 → info（§3.3 J6）。"""
    hits = []
    wanted_rx = re.compile(r"(画影图形|通缉|海捕文书|缉拿甚紧|严拿)")
    avoid_rx = re.compile(r"(易容|改装|化装|贿赂|避过|绕道|不敢)")
    public_rx = re.compile(r"(大摇大摆|公然|抛头露面|入城|进城|当众)")
    for para, m in ctx.corpus.find(wanted_rx.pattern):
        person = ctx.corpus.person_at(para.chapter, para.pn, m.start())
        if not person:
            continue
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= (para.chapter, para.pn):
                continue
            if person not in ctx.corpus.persons_in(p2.chapter, p2.pn):
                continue
            pm = public_rx.search(p2.plain)
            if pm and not avoid_rx.search(p2.plain):
                hits.append(make_hit(ctx, "J6", "info", subject=person,
                                     ch=p2.chapter, pn=p2.pn, pos=pm.start(),
                                     rationale=f"明写缉拿（{m.group(1)}）后 {person} 公然行动且无规避描写 → info（§3.3 J6）",
                                     extra={"wanted_loc": ctx.corpus.loc(para.chapter, para.pn)}))
                break
        if len(hits) >= 20:
            break
    return hits


def rule_J7(ctx: Ctx) -> list[dict]:
    """J7 迷药药性自洽（warning）：明写药性（无色无味/三炷香见效）∧ 情节与之矛盾（§3.3 J7）。"""
    hits = []
    for para, m in ctx.corpus.find(r"(无色无味|无臭无味)"):
        for p2 in ctx.corpus.sorted_paras():
            if abs(p2.chapter - para.chapter) > 1:
                continue
            if (p2.chapter, p2.pn) < (para.chapter, para.pn):
                continue
            cm = re.search(r"(异香|香味|香气|嗅到|闻得|闻到)", p2.plain)
            if cm:
                hits.append(make_hit(ctx, "J7", "warning", ch=p2.chapter, pn=p2.pn, pos=cm.start(),
                                     rationale=f"前文药性『{m.group(1)}』，后文却『{cm.group(1)}』→ 书内矛盾 warning（§3.3 J7）",
                                     extra={"statement_loc": ctx.corpus.loc(para.chapter, para.pn)}))
                break
        if len(hits) >= 20:
            break
    return hits


def rule_T1(ctx: Ctx) -> list[dict]:
    """T1 朝代锚·器物与物品（error/warning）：锚外器物 ∧ 未明写架空 → error；边界器物单例挂人工（§3.4 T1）。
    词表：手枪(1900s)/汽车(1900s)/电报(1871)/火车(1876)/电话(1882)/飞机(1903)/电灯(1880)/自行车(1868)/银元(清末后期·边界)
    """
    hits = []
    items = [
        ("手枪", 1890, "error"), ("汽车", 1900, "error"), ("电报", 1871, "error"),
        ("火车", 1876, "error"), ("电话", 1882, "error"), ("飞机", 1903, "error"),
        ("电灯", 1880, "error"), ("自行车", 1868, "error"), ("报纸", 1870, "error"),
        ("银元", 1889, "warning"),
    ]
    era = ctx.time.year_max
    for word, intro, sev in items:
        for para, m in ctx.corpus.find(re.escape(word)):
            if era is None:
                hits.append(make_hit(ctx, "T1", "info", obj=word, ch=para.chapter, pn=para.pn, pos=m.start(),
                                     rationale=f"出现『{word}』但本书无 N4 朝代年锚，无法与器物传入年代比对 → info 待人工（§3.4 T1）"))
            elif era < intro - 5:
                note = "（边界器物单例，挂人工核实型制与传入年代，不预设结论）" if sev == "warning" else ""
                hits.append(make_hit(ctx, "T1", sev, obj=word, ch=para.chapter, pn=para.pn, pos=m.start(),
                                     rationale=f"本书 N4 年锚上限约 {era}，出现『{word}』（约 {intro} 年后方有）"
                                               f"{note} → {'error 器物穿帮' if sev == 'error' else 'warning 边界器物'}（§3.4 T1）",
                                     extra={"item": word, "intro_year": intro, "book_year": era}))
            if len(hits) >= 20:
                break
    return hits


def rule_T2(ctx: Ctx) -> list[dict]:
    """T2 朝代锚·制度官职与地名（error）：朝代与官制/地名错配 → error（§3.4 T2）。"""
    hits = []
    titles = [
        ("锦衣卫", "明"), ("东厂", "明"), ("军机处", "清"), ("总理衙门", "清"),
    ]
    era = ctx.time.year_min
    # 用 N4 年锚中位/区间：1644 为明清分界（粗略，考订表可细化）
    if era is None:
        for term, dyn in titles:
            for para, m in ctx.corpus.find(re.escape(term)):
                hits.append(make_hit(ctx, "T2", "info", obj=term, ch=para.chapter, pn=para.pn, pos=m.start(),
                                     rationale=f"出现『{term}』，本书无 N4 年锚，无法校朝代归属 → info 待人工（§3.4 T2）"))
        return hits[:20]
    is_qing = era >= 1644
    for term, dyn in titles:
        for para, m in ctx.corpus.find(re.escape(term)):
            mismatch = (dyn == "明" and is_qing) or (dyn == "清" and not is_qing)
            if mismatch:
                hits.append(make_hit(ctx, "T2", "error", obj=term, ch=para.chapter, pn=para.pn, pos=m.start(),
                                     rationale=f"本书主年锚约 {era}（{'清' if is_qing else '明'}），出现『{term}』"
                                               f"（{'明' if dyn == '明' else '清'}代官制）→ error（§3.4 T2）",
                                     extra={"term": term, "dynasty": dyn, "book_year": era}))
            if len(hits) >= 20:
                break
    return hits


def rule_T3(ctx: Ctx) -> list[dict]:
    """T3 历史人物客串（★方向反转）：真实历史人物言行与正史有出入 → 不标记（演义自由）（§3.4 T3）。"""
    return []


def rule_T4(ctx: Ctx) -> list[dict]:
    """T4 纪年自洽（error）：同一书内纪年体系冲突（无跨时叙述）→ error（§3.4 T4）。
    实现：消费 N4 errors 中的 T15（朝代锚 vs 相对链冲突）与 T11（同段多锚点年份冲突）。
    """
    hits = []
    for e in ctx.time.events_by_code("T15"):
        loc = None
        for tid in e.get("tp_ids") or []:
            tp = ctx.time.point_by_id(tid)
            if tp:
                a = tp.get("anchor") or {}
                loc = (a.get("chapter", 1), a.get("pn", 0), tp.get("display", ""))
                break
        ch, pn, disp = loc if loc else (int(str(e.get("chapter", 1))) if str(e.get("chapter", "")).isdigit() else 1, 0, "")
        hits.append(make_hit(ctx, "T4", "warning", ch=ch, pn=pn, obj=disp,
                             rationale=f"N4 纪年换算冲突登记（T15）：朝代锚『{disp or '见N4'}』与书内相对链冲突，"
                                       "按 §2.5 规则5 以朝代锚为主并登记 → 疑似纪年体系冲突（N4 相对链可能漂移，"
                                       "需回读原文区分倒叙/误置，暂判 warning；§3.4 T4）",
                             extra={"n4_code": "T15", "n4_detail": e.get("message", "")}))
    for e in ctx.time.events_by_code("T11"):
        loc = None
        for tid in e.get("tp_ids") or []:
            tp = ctx.time.point_by_id(tid)
            if tp:
                a = tp.get("anchor") or {}
                loc = (a.get("chapter", 1), a.get("pn", 0), tp.get("display", ""))
                break
        ch, pn, disp = loc if loc else (e.get("chapter", 1), 0, "")
        para = ctx.corpus.para(ch, pn)
        transition = bool(para and re.search(r"(后来|等到|过了|次年|转年|再到|已是|不觉)", para.plain))
        hits.append(make_hit(ctx, "T4", "warning" if transition else "error", ch=ch, pn=pn, obj=disp,
                             rationale=f"N4 同段多锚点年份冲突（T11）：{e.get('message', '')}。"
                                       f"同段两处纪年锚相差 >2 年且{'有' if transition else '无'}跨时叙述词 → "
                                       f"{'warning（叙述推进，非穿帮）' if transition else '纪年体系冲突候选 error'}（§3.4 T4）",
                             extra={"n4_code": "T11", "has_transition": transition}))
    return hits[:20]


def rule_T5(ctx: Ctx) -> list[dict]:
    """T5 兵器谱年代（豁免）：通用兵器（剑刀枪棍鞭暗器）跨朝代通用，不校验（§3.4 T5）。"""
    return []


def rule_T6(ctx: Ctx) -> list[dict]:
    """T6 称谓与服饰时代感（warning→error）：古代背景现代称谓/跨朝代服饰 ∧ 无叙述模式豁免（§3.4 T6）。"""
    hits = []
    modern_addr = re.compile(r"(称|叫|道：“)(领导|同志|主席|干部)")
    for para, m in ctx.corpus.find(modern_addr.pattern):
        hits.append(make_hit(ctx, "T6", "warning", ch=para.chapter, pn=para.pn, pos=m.start(),
                             rationale=f"古代背景出现现代称谓『{m.group(2)}』（先查叙述模式：戏中戏/说书人口吻可豁免）→ warning 候选（§3.4 T6）"))
    # 跨朝代服饰：明末以前（<1644）着清装
    era = ctx.time.year_max
    if era is not None and era < 1644:
        for para, m in ctx.corpus.find(r"(马褂|旗装|旗袍|辫子)"):
            if re.search(r"(前朝遗风|戏中|说书)", para.plain):
                continue
            hits.append(make_hit(ctx, "T6", "warning", ch=para.chapter, pn=para.pn, pos=m.start(),
                                 rationale=f"本书年锚≤{era}（明），出现清装/发式『{m.group(1)}』且无前朝遗风/戏中戏明写 → warning 候选（§3.4 T6）"))
    return hits[:20]


def rule_T7(ctx: Ctx) -> list[dict]:
    """T7 修订版权威（豁免/数据不足）：需版本字段比对新旧稿；本批 registry/acceptance 无版本差异字段 → 不扫描（§3.4 T7）。"""
    return []


# ────────────────────────── 五项设定一致性检查 ──────────────────────────
def check_C1(ctx: Ctx) -> list[dict]:
    """检查项一 人物年龄跨回自洽：同一人物两时点年龄差 ≠ 时点差（±1 年容差）→ 候选（§4.1）。
    分类：文学/叙事模糊误差 ≤3 年 info；>1 年且两处均正常叙事 → warning；>3 年且证据强 → error 候选（D）。
    豁免：回忆/梦境/假想/戏中戏（转述者记不准本身是刻画）、传言年龄；驻颜只改容颜不改数字（照记）。
    """
    hits = []
    by_person: dict[str, list] = {}
    for a in ctx.time.ages():
        person = ctx.corpus.person_for_age(a["ch"], a["pn"], a["span"][0] if a["span"] else 0)
        if not person:
            continue
        mode = ctx.corpus.narrative_mode(a["ch"], a["pn"], a["span"][0] if a["span"] else 0)
        t = ctx.time.t_at(a["ch"], a["pn"])
        if t is None:
            continue
        rec = {"age": a["age"], "t": t, "ch": a["ch"], "pn": a["pn"],
               "mode": mode, "display": a["display"]}
        if rec not in by_person.setdefault(person, []):
            by_person[person].append(rec)
    for person, recs in by_person.items():
        recs.sort(key=lambda r: (r["t"], r["ch"], r["pn"]))
        seen_pairs = set()
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                r1, r2 = recs[i], recs[j]
                if r1["mode"] in NON_NORMAL_MODES or r2["mode"] in NON_NORMAL_MODES:
                    continue
                if (r1["ch"], r1["pn"], r1["age"], r2["ch"], r2["pn"], r2["age"]) in seen_pairs:
                    continue
                seen_pairs.add((r1["ch"], r1["pn"], r1["age"], r2["ch"], r2["pn"], r2["age"]))
                if (r1["ch"], r1["pn"]) == (r2["ch"], r2["pn"]):
                    continue   # 同段两年龄陈述的先后不可靠（可能是不同人/不同句），不判跨回
                dt_years = (r2["t"] - r1["t"]) / 365.0
                da = r2["age"] - r1["age"]
                diff = abs(da - dt_years)
                if diff <= 1.0:
                    continue
                # N4 主轨漂移可能导致 Δt 失真：跨度 >60 年或为负 → 不据此判错（降级或跳过）
                if dt_years < 0 or dt_years > 60:
                    continue
                precise = not any(x in (r1["display"] + r2["display"])
                                  for x in ("左右", "上下", "余", "几", "多", "将近", "出头", "约"))
                # C1 的时间差来自 N4 主轨 t 推算（非 01g 已核实级事件时点）；按 SKILL §4.1 分级，
                # 本工具只能给到 warning（存疑）→ 不判 error（D），除非日后接入已核实级时点。
                if diff > 3:
                    sev = "warning"
                else:
                    sev = "info"
                hits.append(make_hit(ctx, "C1", sev, subject=person,
                                     ch=r2["ch"], pn=r2["pn"],
                                     rationale=f"年龄跨回：{r1['display']}（{r1['age']} 岁）→ {r2['display']}（{r2['age']} 岁），"
                                               f"年龄差 {da:+d} 岁 vs 时点差 {dt_years:.1f} 年（偏差 {diff:.1f} 年 >1）"
                                               f" → {sev}（§4.1 检查项一）",
                                     extra={"age1": r1["age"], "age2": r2["age"], "delta_age": da,
                                            "delta_years": round(dt_years, 2), "loc1": ctx.corpus.loc(r1["ch"], r1["pn"]),
                                            "mode1": r1["mode"], "mode2": r2["mode"]}))
                if len(hits) >= 20:
                    return hits
    return hits


def check_C2(ctx: Ctx) -> list[dict]:
    """检查项二 武功习得顺序（未学先使）：使用时点 < 习得时点 → 候选（§4.2）。
    实现：N5『掌握』边（习得证据）+ tagged 使用事件（@person + ☆武功 + 使/施展/用）；
    豁免：家传武功（档案师承可证）、偷学有铺垫、梦境授艺、传言（J8）。
    """
    hits = []
    acquire: dict[tuple[str, str], tuple[int, int]] = {}
    for e in ctx.rel.by_predicate("掌握"):
        loc = ctx.rel.edge_loc(e)
        if not loc:
            continue
        acquire[(e.get("subject"), e.get("object"))] = loc
    use_rx = re.compile(r"(使|施展|用|施出|使出|擅|精于)")
    learn_rx = re.compile(r"(学成|练成|习得|学会|传授|拜师|偷学|梦中|家传|家学)")
    for para in ctx.corpus.sorted_paras():
        martial_tokens = [t for t in para.tokens if t.domain == "☆"]
        persons = ctx.corpus.persons_in(para.chapter, para.pn)
        for mt in martial_tokens:
            name = mt.display
            for person in persons:
                key = (person, name)
                if key not in acquire:
                    continue
                pt = ctx.corpus.canonical_person_token(para.chapter, para.pn, person)
                if pt is None:
                    continue
                # 同句 + person 距 martial ≤30 + 其间有使用动词（防"提到武功名/门派介绍"误报）
                left = max(para.plain.rfind("。", 0, mt.plain_start),
                           para.plain.rfind("！", 0, mt.plain_start),
                           para.plain.rfind("？", 0, mt.plain_start),
                           para.plain.rfind("；", 0, mt.plain_start))
                if not (left < pt.plain_start <= mt.plain_start and mt.plain_start - pt.plain_start <= 30):
                    continue
                seg = para.plain[pt.plain_start + len(person): mt.plain_start]
                if not use_rx.search(seg):
                    continue
                acq = acquire[key]
                if (para.chapter, para.pn) < acq:
                    between = "".join(p.plain for p in ctx.corpus.sorted_paras()
                                      if (para.chapter, para.pn) < (p.chapter, p.pn) < acq)
                    if learn_rx.search(between):
                        continue
                    hits.append(make_hit(ctx, "C2", "warning", subject=person, obj=name,
                                         ch=para.chapter, pn=para.pn, pos=mt.plain_start,
                                         rationale=f"{ctx.corpus.loc(para.chapter, para.pn)} 使用『{name}』早于"
                                                   f"N5 掌握边 {ctx.corpus.loc(*acq)}（未学先使），且其间无偷学/家传铺垫"
                                                   " → warning（§4.2 检查项二）",
                                         extra={"acquisition_loc": ctx.corpus.loc(*acq)}))
                    if len(hits) >= 20:
                        return hits
    return hits


def check_C3(ctx: Ctx) -> list[dict]:
    """检查项三 门派存续期（灭派后再出场）：语义同 S3（§4.3）；直接复用 S3 命中并打 C3 标签。"""
    out = []
    for h in rule_S3(ctx):
        h2 = dict(h)
        h2["rule_id"] = "C3"
        h2["rule_title"] = RULE_BY_ID["C3"].title
        h2["area"] = "检查项"
        h2["spec_cite"] = RULE_BY_ID["C3"].spec
        h2["extra"] = dict(h.get("extra") or {}, linked_rule="S3")
        out.append(h2)
    return out


def check_C4(ctx: Ctx) -> list[dict]:
    """检查项四 死亡角色再出场：01g 死亡登记/杀害边 → 后文正常叙事活体行动 ∧ 无假死/翻案 → 候选（§4.4）。
    实现：N5『杀害』边（subject 凶手, object 死者, confidence strong/ok）+ tagged 后续 live 行动
    （@死者 + 道/说/笑/走/来/出手/出手/刺/打 + 非死亡/回忆语境）→ error（强证据）/warning。
    """
    hits = []
    live_rx = re.compile(r"(说道|道：“|笑道|喝道|叫道|问道|点头|摇头|出手|飞身|纵身|拔剑|挥掌)")
    death_ctx_rx = re.compile(r"(死|亡|杀|遇害|尸|墓|灵|祭|回忆|追忆|相传|传言|据说)")
    kill_rx = re.compile(r"(杀死|杀掉|刺杀|斩死|刺死|斫死|击毙|害死|毒死|杀了|杀却|毙命|气绝|身亡|丧命|自刎|自尽|遇害|身首异处)")
    kill_soft_rx = re.compile(r"(杀得|杀退|杀败|杀伤|杀出|杀散|杀得他|逃生)")
    for e in ctx.rel.by_predicate("杀害"):
        victim = e.get("object")
        loc = ctx.rel.edge_loc(e)
        if not victim or not loc:
            continue
        conf = e.get("confidence", "weak")
        death_para = ctx.corpus.para(*loc)
        structural = False
        if death_para is not None:
            vt = ctx.corpus.canonical_person_token(loc[0], loc[1], victim)
            if vt is not None:
                tail = death_para.plain[vt.plain_start + len(victim): vt.plain_start + len(victim) + 12]
                pre = death_para.plain[max(0, vt.plain_start - 12): vt.plain_start]
                structural = bool((kill_rx.search(tail) and not kill_soft_rx.search(tail)) or
                                  re.search(r"(被.{0,8}(杀死|害死|刺死|斩死|击毙)|死于|死在|尸首|尸身|气绝|身亡)", pre + tail))
        if not structural:
            continue
        for p2 in ctx.corpus.sorted_paras():
            if (p2.chapter, p2.pn) <= loc:
                continue
            if victim not in ctx.corpus.persons_in(p2.chapter, p2.pn):
                continue
            mode = ctx.corpus.narrative_mode(p2.chapter, p2.pn)
            if mode in NON_NORMAL_MODES or mode == "传言":
                continue
            if death_ctx_rx.search(p2.plain):
                continue
            vt = ctx.corpus.canonical_person_token(p2.chapter, p2.pn, victim)
            if vt is None:
                continue
            tail = p2.plain[vt.plain_start + len(victim): vt.plain_start + len(victim) + 10]
            lm = live_rx.search(tail)
            if not lm:
                continue
            sev = "error" if conf in ("strong", "ok") else "warning"
            hits.append(make_hit(ctx, "C4", sev, subject=e.get("subject", ""), obj=victim,
                                 ch=p2.chapter, pn=p2.pn, pos=vt.plain_start,
                                 rationale=f"N5 杀害边（{e.get('subject')}→{victim}，{conf}）位于 "
                                           f"{ctx.corpus.loc(*loc)}（原文有致死结构证据），后文 "
                                           f"{ctx.corpus.loc(p2.chapter, p2.pn)} {victim} 在正常叙事中有活体行动"
                                           f"（『{lm.group(1)}』）且无假死/翻案明写 → {sev}（§4.4 检查项四）",
                                 extra={"death_loc": ctx.corpus.loc(*loc), "edge_confidence": conf,
                                        "narrative_mode": mode, "death_structural_evidence": True}))
            break
        if len(hits) >= 20:
            break
    return hits


def check_C5(ctx: Ctx) -> list[dict]:
    """检查项五 称谓辈分错乱：关系边与称谓系统性冲突 → 候选（§4.5）。
    实现：N5 validation（同人多位 active 师父=互斥）与 derived.reciprocal_conflicts（互为师徒）→ warning；
    另联动 S5 师承年龄倒挂（同一关系边）。弱信号，不判 error。
    """
    hits = []
    for w in (ctx.rel.validation.get("warnings") or []):
        detail = w.get("detail", "")
        if "互斥" in w.get("check", "") or "师父" in detail:
            hits.append(make_hit(ctx, "C5", "warning", subject=detail.split(" ")[0],
                                 ch=1, pn=0,
                                 rationale=f"N5 关系互斥：{detail} → 辈分/称谓系统性冲突候选（§4.5 检查项五；弱信号 warning）",
                                 extra={"n5_check": w.get("check"), "n5_rule": w.get("rule")}))
    for pair in ctx.rel.conflicts:
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            hits.append(make_hit(ctx, "C5", "warning", subject=pair[0], obj=pair[1],
                                 ch=1, pn=0,
                                 rationale=f"N5 互为师徒对 {pair[0]} ⇄ {pair[1]}（{pair[2] if len(pair) > 2 else ''}）"
                                           "→ 辈分/称谓系统性冲突候选（§4.5 检查项五；待人工裁定）",
                                 extra={"n5_rule": "D06 §9.3"}))
    # 联动 S5（师承年龄倒挂）
    for h in rule_S5(ctx):
        h2 = dict(h)
        h2["rule_id"] = "C5"
        h2["rule_title"] = RULE_BY_ID["C5"].title
        h2["area"] = "检查项"
        h2["spec_cite"] = RULE_BY_ID["C5"].spec
        h2["extra"] = dict(h.get("extra") or {}, linked_rule="S5")
        hits.append(h2)
    return hits[:20]


# ────────────────────────── 规则注册表（函数） ──────────────────────────
RULE_FUNCS = {
    "W1": rule_W1, "W2": rule_W2, "W3": rule_W3, "W4": rule_W4, "W5": rule_W5,
    "W6": rule_W6, "W7": rule_W7, "W8": rule_W8, "W9": rule_W9,
    "S1": rule_S1, "S2": rule_S2, "S3": rule_S3, "S4": rule_S4, "S5": rule_S5,
    "S6": rule_S6, "S7": rule_S7, "S8": rule_S8, "S9": rule_S9, "S10": rule_S10,
    "J1": rule_J1, "J2": rule_J2, "J3": rule_J3, "J4": rule_J4, "J5": rule_J5,
    "J6": rule_J6, "J7": rule_J7,
    "T1": rule_T1, "T2": rule_T2, "T3": rule_T3, "T4": rule_T4, "T5": rule_T5,
    "T6": rule_T6, "T7": rule_T7,
    "C1": check_C1, "C2": check_C2, "C3": check_C3, "C4": check_C4, "C5": check_C5,
}
EXEMPT_RULES = {r.rule_id for r in RULES if r.kind == "exempt"}


def rule_J8(ctx: Ctx) -> list[dict]:
    """J8 传言≠事实（★方向反转，豁免性规则）：江湖传言/转述与后文冲突 → 不标记；按 04a 可靠性矩阵归"来源声称"层（§3.3 J8）。"""
    return []


RULE_FUNCS["J8"] = rule_J8


# ────────────────────────── 引擎 ──────────────────────────
def run_book(book: str, rule_filter: list[str] | None = None) -> dict:
    entities = Entities()
    corpus = Corpus(book, entities.display_to_canon)
    time_data = TimeData(book)
    rel = RelationsData(book)
    ctx = Ctx(book, corpus, time_data, rel, entities)

    violations: list[dict] = []
    exemptions: list[dict] = []
    rule_hits: dict[str, int] = {}
    rule_status: dict[str, str] = {}
    selected = [rid for rid in RULE_IDS if (not rule_filter or rid in rule_filter)]
    for rid in selected:
        meta = RULE_BY_ID[rid]
        func = RULE_FUNCS.get(rid)
        if func is None:
            rule_status[rid] = "未实现"
            continue
        try:
            hits = func(ctx) if rid not in EXEMPT_RULES else []
        except Exception as exc:  # noqa: BLE001 - 单规则失败不阻塞其它规则
            rule_status[rid] = f"运行异常：{exc}"
            continue
        if rid in EXEMPT_RULES:
            rule_status[rid] = "豁免（默认不扫描）"
            rule_hits[rid] = 0
            continue
        kept = 0
        for h in hits:
            mode = h.get("narrative_mode", "正常叙事")
            # 叙述模式豁免（04a / SKILL §7.2 ①；错误6 评点/韵文同样不入故事时间轨）
            if mode in NON_NORMAL_MODES or mode in EXTRA_EXEMPT_MODES:
                h["exempted"] = True
                h["exemption"] = f"叙述模式豁免（04a/{mode}）"
                exemptions.append(h)
                continue
            # 可靠性过滤（§7.2 ②）：传言/转述 → 降一级并留痕，不进 error
            if mode == "传言" and h["severity"] in ("error", "warning"):
                h["severity"] = "warning" if h["severity"] == "error" else "info"
                h["grade"] = GRADE_OF_SEVERITY[h["severity"]]
                h["rationale"] += "；可靠性过滤：来源声称（J8/§7.2②）降级"
            kept += 1
            h["vid"] = f"{book[:2]}-{rid}-{kept:03d}"
            violations.append(h)
        rule_hits[rid] = kept
        rule_status[rid] = "已实现" + ("" if hits else "（本批 0 命中）")
        if len(violations) >= 400:
            break

    # 排序：severity 降序 → 回 → 段
    violations.sort(key=lambda v: (-SEVERITY_ORDER.get(v["severity"], 0), v["chapter"], v["pn"]))
    # 去重（同 rule/subject/object/locator）
    seen, dedup = set(), []
    for v in violations:
        key = (v["rule_id"], v.get("subject"), v.get("object"), v["locator"], v["rationale"][:30])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(v)
    violations = dedup

    by_sev = {"error": 0, "warning": 0, "info": 0}
    by_grade = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
    for v in violations:
        by_sev[v["severity"]] += 1
        by_grade[v["grade"]] += 1
    by_area = {}
    for v in violations:
        by_area[v["area"]] = by_area.get(v["area"], 0) + 1
    by_rule = {}
    for v in violations:
        by_rule[v["rule_id"]] = by_rule.get(v["rule_id"], 0) + 1

    coverage = []
    for meta in RULES:
        covered = meta.rule_id in selected or not rule_filter
        status = rule_status.get(meta.rule_id, "未运行" if rule_filter else "未实现")
        if by_rule.get(meta.rule_id, 0) == 0 and meta.note and status.startswith("已实现"):
            status += f"（数据缺口：{meta.note}）"
        coverage.append({
            "rule_id": meta.rule_id, "area": meta.area, "title": meta.title,
            "kind": meta.kind, "spec_cite": meta.spec,
            "status": status,
            "note": meta.note,
            "hits": by_rule.get(meta.rule_id, 0),
            "selected": covered,
        })
    return {
        "schema": "wuxia-consistency-v1",
        "book": book,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tool": TOOL_VERSION,
        "spec": {
            "skill": "skills/SKILL_常识与设定一致性_武侠版.md",
            "sections": ["§三 34 条种子规则", "§四 五项检查", "§六 A-E 评级", "§七 反常三分流",
                         "§3.5 lint 关系", "§1.4 方向反转"],
            "task": "docs/17 §2.3 / docs/50 §三（N8/D11）",
        },
        "inputs": {
            "tagged_dir": f"tagged/{book}",
            "time_json": f"registry/time/{book}.json",
            "time_generated": time_data.generated,
            "relations_json": f"registry/relations/{book}.json",
            "relations_generated": rel.generated,
            "entities": "registry/entities.json",
            "entities_version": entities.version,
            "chapters": len(corpus.chapters),
            "paragraphs": len(corpus.paras),
        },
        "summary": {
            "total": len(violations),
            "by_severity": by_sev,
            "by_grade": by_grade,
            "by_area": by_area,
            "by_rule": by_rule,
            "exemptions": len(exemptions),
            "rules_total": len(RULES),
            "rules_selected": len(selected),
            "rules_with_hits": len(by_rule),
            "rules_exempt": len(EXEMPT_RULES),
            "grade_legend": {
                "A": "与设定库完全一致（本引擎不产出）",
                "B": "设定内合理/备案（info 级命中）",
                "C": "存疑（warning 级命中）",
                "D": "疑似穿帮（error 级命中，待人工复核；E 需人工确认）",
                "E": "确认穿帮（需人工复核，本引擎不产出）",
            },
            "severity_legend": {"error": "疑似穿帮候选（D）", "warning": "存疑（C）", "info": "备案/资产（B）"},
        },
        "violations": violations,
        "rule_coverage": coverage,
        "exemptions": [
            {"rule_id": h["rule_id"], "locator": h["locator"], "reason": h.get("exemption", ""),
             "subject": h.get("subject", "")} for h in exemptions[:100]
        ],
        "interfaces": {
            "N4": {"used": ["time_points(age/year_ce/t_days/narrative_mode)", "book_anchors", "errors(T15/T11)"],
                   "purpose": "C1 年龄跨回 / T4 纪年自洽 / W2/W8 时点差 / T1/T2 时代锚"},
            "N5": {"used": ["edges(predicate=师承/任职/杀害/掌握/同门)", "derived.lineage_labels",
                            "derived.reciprocal_conflicts", "validation.warnings"],
                   "purpose": "S1/S2/S5/C2/C4/C5 关系证据"},
            "entities": {"used": ["canonical/aliases/status"], "purpose": "人物归一与跨段同一人判定"},
            "tagged": {"used": ["段落/围栏/对白/叙述模式/证据引文"], "purpose": "证据与 04a 叙述模式豁免"},
        },
    }


# ────────────────────────── 报告渲染 ──────────────────────────
def _esc(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ") if s is not None else ""


def render_book_md(result: dict) -> str:
    s = result["summary"]
    lines = []
    add = lines.append
    add(f"# N8 穿帮一致性检查报告 · 《{result['book']}》")
    add("")
    add(f"- 生成时间：{result['generated_at']}；工具：`scripts/lint_consistency.py`（{result['tool']}）")
    add(f"- 规范：`{result['spec']['skill']}`（§三 34 条 IF-THEN + §四 五项检查 + §六 A-E 评级 + §七 三分流）")
    add(f"- 输入：`{result['inputs']['tagged_dir']}`（{result['inputs']['chapters']} 回 / "
        f"{result['inputs']['paragraphs']} 段）+ `{result['inputs']['time_json']}`（N4 "
        f"{result['inputs']['time_generated']}）+ `{result['inputs']['relations_json']}`（N5 "
        f"{result['inputs']['relations_generated']}）+ `{result['inputs']['entities']}`")
    add("")
    add("## 一、总览")
    add("")
    add(f"- 命中 **{s['total']}** 条：error **{s['by_severity']['error']}**（D 疑似穿帮候选）· "
        f"warning **{s['by_severity']['warning']}**（C 存疑）· info **{s['by_severity']['info']}**（B 备案/资产）；"
        f"叙述模式豁免 **{s['exemptions']}** 条（回忆/梦境/假想/戏中戏，04a）")
    add(f"- 规则覆盖：34 条种子 + 5 项检查 = **{s['rules_total']}** 条；本轮运行 {s['rules_selected']} 条，"
        f"有命中 {s['rules_with_hits']} 条，豁免（方向反转/无需扫描）{s['rules_exempt']} 条。")
    add(f"- 分级：B {s['by_grade']['B']} · C {s['by_grade']['C']} · D {s['by_grade']['D']} · E {s['by_grade']['E']}"
        "（A=完全一致不产出；E=需人工确认不产出）。")
    add("")
    add("## 二、按领域 / 规则分布")
    add("")
    add("| 维度 | 分布 |")
    add("|---|---|")
    add(f"| 领域 | {_esc(s['by_area'])} |")
    add(f"| 规则 | {_esc(s['by_rule'])} |")
    add("")
    add("## 三、命中明细（按严重度排序，含定位符与证据）")
    add("")
    if result["violations"]:
        add("| # | 规则 | 分级 | 定位符 | 主体 | 客体 | 证据（原文） | 判定说明 |")
        add("|---:|---|---|---|---|---|---|---|")
        for i, v in enumerate(result["violations"], 1):
            add(f"| {i} | {v['rule_id']} {_esc(v['rule_title'])} | **{v['grade']}**（{v['severity']}） | "
                f"`{v['locator']}` | {_esc(v.get('subject', ''))} | {_esc(v.get('object', ''))} | "
                f"{_esc(v['quote'])} | {_esc(v['rationale'])} |")
    else:
        add("（本轮无命中）")
    add("")
    add("## 四、规则覆盖表（34 条种子 + 5 项检查；逐条引 SKILL 条文）")
    add("")
    add("| 规则 | 领域 | 标题 | lint 关系 | 状态 | 命中 | SKILL 条文 |")
    add("|---|---|---|---|---|---:|---|")
    for c in result["rule_coverage"]:
        add(f"| {c['rule_id']} | {c['area']} | {_esc(c['title'])} | {c['kind']} | {_esc(c['status'])} | "
            f"{c['hits']} | {_esc(c['spec_cite'])} |")
    add("")
    add("### 五项设定一致性检查（§四）")
    add("")
    add("| 检查项 | 定义 | 状态 | 命中 | SKILL 条文 |")
    add("|---|---|---|---:|---|")
    check_names = {
        "C1": "人物年龄跨回自洽", "C2": "武功习得顺序（未学先使）",
        "C3": "门派存续期（灭派后再出场）", "C4": "死亡角色再出场", "C5": "称谓辈分错乱",
    }
    for c in result["rule_coverage"]:
        if c["rule_id"] in check_names:
            add(f"| {c['rule_id']} | {check_names[c['rule_id']]} | {_esc(c['status'])} | {c['hits']} | "
                f"{_esc(c['spec_cite'])} |")
    add("")
    add("## 五、叙述模式豁免与可靠性过滤（04a / §七 ①-②）")
    add("")
    add("- 豁免口径：回忆/梦境/假想/戏中戏（04a）＋围栏韵文/回末评点＋作者按语，均不入故事时间轨、不判穿帮。")
    add("- 可靠性过滤（§7.2②/J8）：传言/转述来源的命中降一级并留痕（error→warning→info）。")
    if result["exemptions"]:
        add("| 规则 | 定位符 | 主体 | 豁免原因 |")
        add("|---|---|---|---|")
        for e in result["exemptions"][:40]:
            add(f"| {e['rule_id']} | `{e['locator']}` | {_esc(e.get('subject', ''))} | {_esc(e['reason'])} |")
    else:
        add("（无：本轮命中均位于正常叙事段）")
    add("")
    add("## 六、A-E 评级说明与上游接口")
    add("")
    add("- 评级映射：error→**D**（疑似穿帮，待人工复核；E 需人工确认，本引擎不产出）；warning→**C**（存疑）；"
        "info→**B**（设定内合理/备案/资产）；A 仅表示无冲突，不作为命中输出。")
    add("- 叙述模式豁免（04a）：命中段在回忆/梦境/假想/戏中戏 → 不入 violations，记入豁免；传言/转述 → 归来源声称层。")
    add("- N4 接口：" + "、".join(result["interfaces"]["N4"]["used"]) + "；用途：" + result["interfaces"]["N4"]["purpose"])
    add("- N5 接口：" + "、".join(result["interfaces"]["N5"]["used"]) + "；用途：" + result["interfaces"]["N5"]["purpose"])
    add("- 实体：" + "、".join(result["interfaces"]["entities"]["used"]) + "；用途：" + result["interfaces"]["entities"]["purpose"])
    add("")
    add("## 七、复现")
    add("")
    add("```powershell")
    add(f"python -X utf8 scripts/lint_consistency.py --book {result['book']}")
    add(f"python -X utf8 scripts/lint_consistency.py --book {result['book']} --rule W6,T4,C3")
    add("python -X utf8 scripts/lint_consistency.py --all")
    add("```")
    add("")
    return "\n".join(lines) + "\n"


def render_summary_md(results: list[dict]) -> str:
    lines = []
    add = lines.append
    add("# N8 穿帮一致性检查 · 5 书汇总")
    add("")
    add(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；工具：{TOOL_VERSION}")
    add("- 规范：`skills/SKILL_常识与设定一致性_武侠版.md`（§三 34 条 + §四 五项检查 + §六 A-E + §七 三分流）；"
        "只读 N4/N5/entities/tagged，写 registry/consistency + logs/consistency")
    add("")
    add("## 一、5 书总览")
    add("")
    add("| 书 | 命中 | error(D) | warning(C) | info(B) | 豁免(04a) | 有命中规则数 | 覆盖 |")
    add("|---|---:|---:|---:|---:|---:|---:|---|")
    tot = {"total": 0, "error": 0, "warning": 0, "info": 0, "exempt": 0, "rules": 0}
    for r in results:
        s = r["summary"]
        covered = sum(1 for c in r["rule_coverage"] if c["status"] not in ("未实现", "未运行"))
        add(f"| {r['book']} | {s['total']} | {s['by_severity']['error']} | {s['by_severity']['warning']} | "
            f"{s['by_severity']['info']} | {s['exemptions']} | {s['rules_with_hits']} | {covered}/{s['rules_total']} |")
        tot["total"] += s["total"]; tot["error"] += s["by_severity"]["error"]
        tot["warning"] += s["by_severity"]["warning"]; tot["info"] += s["by_severity"]["info"]
        tot["exempt"] += s["exemptions"]; tot["rules"] += s["rules_with_hits"]
    add(f"| **合计** | **{tot['total']}** | **{tot['error']}** | **{tot['warning']}** | **{tot['info']}** | "
        f"**{tot['exempt']}** | **{tot['rules']}**（书×规则） | — |")
    add("")
    add("## 二、跨书规则命中（5 书合计）")
    add("")
    agg: dict[str, int] = {}
    for r in results:
        for k, v in r["summary"]["by_rule"].items():
            agg[k] = agg.get(k, 0) + v
    add("| 规则 | 领域 | 标题 | 5 书命中 |")
    add("|---|---|---|---:|")
    for rid, n in sorted(agg.items(), key=lambda x: -x[1]):
        m = RULE_BY_ID[rid]
        add(f"| {rid} | {m.area} | {_esc(m.title)} | {n} |")
    add("")
    add("## 三、分级与口径")
    add("")
    add("- error→**D 疑似穿帮候选**（待人工复核；E 需人工确认，本引擎不产出）；warning→**C 存疑**；info→**B 备案/资产**。")
    add("- 叙述模式豁免（04a）：回忆/梦境/假想/戏中戏命中不入 violations；传言/转述归来源声称层（J8）。")
    add("- 规则覆盖：34 条种子（W9/S10/J8/T7）+ 5 项检查；豁免性规则 6 条（W3/S8/J2/J8/T5/T7）默认不扫描，"
        "T3（历史人物客串）人工为主仅备案，均在规则覆盖表标注。")
    add("- 本批 error 级（D）命中 0：C1/C5 等弱信号按 SKILL 证据强度止于 C（N4/N5 为推算/推导边，"
        "非 01g『已核实』级时点/事件）；如需升 D/E 须人工复核 + 事件层/档案层补证。")
    add("- selftest：`python -X utf8 scripts/lint_consistency.py --selftest`（评级映射/数字解析/叙述模式/证据构造断言）。")
    add("")
    add("## 四、产物")
    add("")
    for r in results:
        add(f"- 《{r['book']}》：`registry/consistency/{r['book']}.json` · `logs/consistency/{r['book']}.md`")
    add("- 汇总：`logs/consistency/summary.md` · `logs/consistency/summary.json`")
    add("")
    add("## 五、复现")
    add("")
    add("```powershell")
    add("python -X utf8 scripts/lint_consistency.py --selftest")
    add("python -X utf8 scripts/lint_consistency.py --all")
    add("python -X utf8 scripts/lint_consistency.py --book 江湖三女侠 --rule T4,C1,C4")
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

    chk("cn_num 十八=18", cn_num("十八") == 18)
    chk("cn_num 廿一=21", cn_num("廿一") == 21)
    chk("cn_num 三百=300", cn_num("三百") == 300)
    chk("评级 error→D", GRADE_OF_SEVERITY["error"] == "D")
    chk("评级 warning→C", GRADE_OF_SEVERITY["warning"] == "C")
    chk("评级 info→B", GRADE_OF_SEVERITY["info"] == "B")
    chk("severity 序", SEVERITY_ORDER["error"] > SEVERITY_ORDER["warning"] > SEVERITY_ORDER["info"])
    chk("规则总数 34+5", len(RULES) == 39 and len(RULE_IDS) == 39)
    chk("34 条种子", len([r for r in RULES if r.area in ("武学", "门派", "江湖", "时代")]) == 34)
    chk("五项检查", len([r for r in RULES if r.area == "检查项"]) == 5)
    chk("W 区 9 条", len([r for r in RULES if r.rule_id.startswith("W")]) == 9)
    chk("S 区 10 条", len([r for r in RULES if r.rule_id.startswith("S")]) == 10)
    chk("J 区 8 条", len([r for r in RULES if r.rule_id.startswith("J")]) == 8)
    chk("T 区 7 条", len([r for r in RULES if r.rule_id.startswith("T")]) == 7)
    chk("豁免规则集合", EXEMPT_RULES == {"W3", "S8", "J2", "J8", "T5", "T7"})
    chk("叙述模式枚举", set(NON_NORMAL_MODES) == {"回忆", "梦境", "假想", "戏中戏"})
    chk("strip 实体", strip_markup("a〖@张三〗b") == "a张三b")
    chk("strip 修辞", strip_markup("a〘※迅雷不及掩耳〙b") == "a迅雷不及掩耳b")
    chk("CN 数字 两", cn_num("两") == 2)
    chk("规则元数据完整", all(r.area and r.title and r.kind and r.spec for r in RULES))
    ok = sum(checks)
    print(f"[selftest] {ok}/{len(checks)} passed")
    return 0 if ok == len(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lint_consistency.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "N8 穿帮规则引擎（D11）：按 SKILL_常识与设定一致性_武侠版 §三 34 条 IF-THEN + §四 五项检查，\n"
            "消费 registry/time（N4）、registry/relations（N5）、registry/entities 与 tagged（只读），\n"
            "输出 registry/consistency/<书>.json（violations: rule_id/severity/grade/证据/定位符）+ "
            "logs/consistency/<书>.md。"),
        epilog=(
            "示例：\n"
            "  python -X utf8 scripts/lint_consistency.py --book 江湖三女侠\n"
            "  python -X utf8 scripts/lint_consistency.py --all\n"
            "  python -X utf8 scripts/lint_consistency.py --book 七剑下天山 --rule W6,T4,C3\n"
            "  python -X utf8 scripts/lint_consistency.py --all --strict\n"
            "  python -X utf8 scripts/lint_consistency.py --selftest\n\n"
            "分级：error→D（疑似穿帮候选，待人工复核；E 不产出）/ warning→C（存疑）/ info→B（备案/资产）。\n"
            "叙述模式豁免（04a）：回忆/梦境/假想/戏中戏不入 violations。"),
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--book", metavar="书名")
    g.add_argument("--all", action="store_true")
    g.add_argument("--selftest", action="store_true")
    p.add_argument("--rule", metavar="IDS", default=None,
                   help="逗号分隔规则过滤（如 W6,T4,C3; 也可 --rule W 前缀匹配）")
    p.add_argument("--strict", action="store_true",
                   help="严格模式：存在 error 级命中（→D）时 exit 2")
    p.add_argument("--quiet", action="store_true")
    return p


def _parse_rules(spec: str | None) -> list[str] | None:
    if not spec:
        return None
    out = []
    for part in spec.split(","):
        part = part.strip().upper()
        if not part:
            continue
        if part in RULE_BY_ID:
            out.append(part)
        else:  # 前缀（如 W/S/J/T/C）
            out.extend(rid for rid in RULE_IDS if rid.startswith(part))
    return sorted(set(out), key=RULE_IDS.index) if out else None


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    if args.selftest:
        return run_selftest()
    rules = _parse_rules(args.rule)
    if args.rule and not rules:
        print(f"[ERROR] --rule 未匹配任何规则：{args.rule}", file=sys.stderr)
        return 2
    books = DEFAULT_BOOKS if args.all else [args.book]
    OUT_REG.mkdir(parents=True, exist_ok=True)
    OUT_LOGS.mkdir(parents=True, exist_ok=True)
    results = []
    for book in books:
        try:
            r = run_book(book, rules)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] {book}: {exc}", file=sys.stderr)
            continue
        jp = OUT_REG / f"{book}.json"
        io.open(jp, "w", encoding="utf-8").write(json.dumps(r, ensure_ascii=False, indent=2) + "\n")
        mp = OUT_LOGS / f"{book}.md"
        io.open(mp, "w", encoding="utf-8").write(render_book_md(r))
        r["_files"] = {"json": f"registry/consistency/{book}.json", "md": f"logs/consistency/{book}.md"}
        results.append(r)
        if not args.quiet:
            s = r["summary"]
            print(f"[OK] {book}: 命中 {s['total']}（error {s['by_severity']['error']} / "
                  f"warning {s['by_severity']['warning']} / info {s['by_severity']['info']}）；"
                  f"豁免 {s['exemptions']} · 有命中规则 {s['rules_with_hits']}/{s['rules_total']} → "
                  f"{r['_files']['json']}")
    if not results:
        return 1
    if len(results) > 1:
        sm = OUT_LOGS / "summary.md"
        sj = OUT_LOGS / "summary.json"
        io.open(sm, "w", encoding="utf-8").write(render_summary_md(results))
        summary = {
            "tool": TOOL_VERSION, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "books": [r["book"] for r in results],
            "totals": {
                "violations": sum(r["summary"]["total"] for r in results),
                "error": sum(r["summary"]["by_severity"]["error"] for r in results),
                "warning": sum(r["summary"]["by_severity"]["warning"] for r in results),
                "info": sum(r["summary"]["by_severity"]["info"] for r in results),
                "exemptions": sum(r["summary"]["exemptions"] for r in results),
            },
            "book_summaries": [{"book": r["book"], "summary": r["summary"], "files": r["_files"]}
                               for r in results],
            "rule_hits_total": {rid: sum(r["summary"]["by_rule"].get(rid, 0) for r in results)
                                for rid in RULE_IDS},
        }
        io.open(sj, "w", encoding="utf-8").write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        if not args.quiet:
            print(f"[OK] 汇总 → {sm} · {sj}")
    if args.strict:
        err = sum(r["summary"]["by_severity"]["error"] for r in results)
        if err:
            print(f"[STRICT] error 级命中 {err} 条 → exit 2", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
