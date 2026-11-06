# -*- coding: utf-8 -*-
"""N4 · `time_resolver_wuxia.py` — 书内相对时间轴解析器（武侠版）

规范源（本文件每条规则均标注出处）：
  skills/SKILL_时间体系_武侠版.md
    §二 时点键双层结构（物理段锚 {作品ID}#pn-r{N}.{X} + 逻辑 tp_id；书内相对刻度 t 单位=日；
        粒度五级：纪元级/年级/季月级/日级/日内级；模糊表达归最低可保证级并标精度=约略）
    §三 四类锚点（朝代/事件/人物年龄/时令）与置信总排序
        朝代锚 ＞ 事件锚·强 ＞ 人物年龄锚 ＞ 事件锚·弱 ＞ 时令锚
    §四 同线单调性（E1 error / E2 warning / E3 warning / E4 info）、时轴分叉（七叉型）、
        叙述模式隔离（回忆/梦境/假想/戏中戏不进主轨）、叙述顺序≠发生顺序判据、线间同时
    §五 定年方法 M1-M7、师承代数定年（当量 1-2 代；跨度 25-30 年/当量；封顶 low）
    §六 43 种错误模式三分裁决（直迁/改写/报废，见 ERROR_MODE_TABLE）+ W1-W6 设定内时间扭曲
    §七 标注格式：% 三管道（年龄/时长/时点）与 $ 数量分流边界
    §八 confidence 三档（high 书内明确陈述 / medium 相对推算一致 / low 跨书推断）
  docs/17 §2.3 / docs/50 §三：N4 节点为「时点键解析+叙事单调性+分叉隔离（D05）」。

设计原则（对齐任务要求「不追求完美绝对纪年」）：
  1. **可审计**：每个 `%` 令牌落为一条 time_point，带 raw 原文、段锚、锚点类型、偏移、
     置信档与依据字段；无法解析者显式留未知并写"未确定原因"，不填默认年份（错误1/模式1 禁令）。
  2. **三档结构**：锚点（朝代/事件/年龄/时令）＋相对刻度 t（天）＋confidence（high/medium/low）；
     绝对公历年只作「换算/显示辅助」，不覆盖书内相对排序（SKILL §2.5 规则 2）。
  3. **不猜**：无朝代锚的书不借同名人物挂年份（§2.6）；跨书接力/师承代数只给 low 佐证。
  4. **只读**：只读 tagged/struct 与（可选）struct；写 registry/time/ + logs/time/。

主要步骤：
  S1 载入 tagged+struct，抽 `〖%…|管道〗` 全部令牌，记录（回,段,行内 span,上下文,是否对白,是否围栏）。
  S2 逐令牌分类：时间类型（时点/时长/年龄/周期/未知）→ 粒度（五级）→ 锚点类型（四类）→
     解析值（年号/干支→公历年候选；相对词→偏移；月日/时令→日序；年龄→数值；时长→天数）。
  S3 主轨排轨：按（回,段,行,字符）叙述序维护书内刻度 t；对白内时间不推进主轨（叙述模式隔离），
     追叙信号建 fork（分叉）并隔离，回指指向最近已登记同类时点，不新建（§4.2/§4.4）。
  S4 单调性校验：主轨（非隔离、非分叉）且 t 非空者，按叙述序检查单调不减；
     E1 硬倒流 / E2 一方约略 / E4 分叉内倒流（仅登记）；"与此同时"登记 simultaneous_to（E3 检查）。
  S5 错误清单：43 模式中可机械化的子集（T01-T14，见 CHECK_RULES）+ W 系列提示；
     单锚点塌缩（§6.2 例1 K=3）、重复标注（模式28）、非时点混入（模式29）、裸时点缺管（模式26）、
     管道误用（§7.3）、谚语虚指（W6）、围栏韵文不入轨（错误6）、跳变（W1）/周期（W5）登记等。
  S6 输出：registry/time/<书>.json（结构化全量）+ logs/time/<书>.md（人读报告）；
     --all 另出 logs/time/time_resolve_summary.md 与 summary.json。

CLI：
  python -X utf8 scripts/time_resolver_wuxia.py --selftest
  python -X utf8 scripts/time_resolver_wuxia.py --book 江湖三女侠
  python -X utf8 scripts/time_resolver_wuxia.py --all
  python -X utf8 scripts/time_resolver_wuxia.py --book 七剑下天山 --chapter 1-5
  python -X utf8 scripts/time_resolver_wuxia.py --book 冰魄寒光剑 --report logs/time/custom.md
  python -X utf8 scripts/time_resolver_wuxia.py --all --strict   # 主轨 E1 或 fatal>0 时 exit 2
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

ROOT = Path(__file__).resolve().parents[1]          # wuxia-kb/
TAGGED_DIR = ROOT / "tagged"
REGISTRY_TIME_DIR = ROOT / "registry" / "time"
LOGS_TIME_DIR = ROOT / "logs" / "time"
TOOL_VERSION = "time_resolver_wuxia v0.1 (2026-11-05, N4/D05)"

# --all 范围：动态发现（tagged/ 下有产物的书），避免硬编码清单随扩书漂移（docs/69）
DEFAULT_BOOKS = sorted(
    d.name for d in TAGGED_DIR.iterdir()
    if d.is_dir() and any(d.glob("*.tagged.md"))
)

# 作品 ID（工程口径；SKILL §2.1 示例 bainv-T017。正式 registry 主键后续与考订表对齐）
# 2026-11-06 补齐 4 部新书（docs/69）；缺书 hash 兜底 ID 跨运行不稳定（PYTHONHASHSEED）
BOOK_IDS = {
    "江湖三女侠": "jianghu",
    "七剑下天山": "qijian",
    "塞外奇侠传": "saiwai",
    "冰魄寒光剑": "bingpo",
    "白发魔女传": "bainv",
    "冰川天女传": "bingchuan",
    "萍踪侠影录": "pingzong",
    "还剑奇情录": "huanjian",
    "散花女侠": "sanhua",
}

# ────────────────────────── 朝代/年号换算表（§2.5 朝代锚；M1 直录法） ──────────────────────────
# 年号→元年公历年（年份按年号年 N=元年+ N-1 换算；与实际史历边界差异留待考订表回填）
REIGN_START = {
    "洪武": 1368, "建文": 1399, "永乐": 1403, "洪熙": 1425, "宣德": 1426,
    "正统": 1436, "景泰": 1450, "天顺": 1457, "成化": 1465, "弘治": 1488,
    "正德": 1506, "嘉靖": 1522, "隆庆": 1567, "万历": 1573, "泰昌": 1620,
    "天启": 1621, "崇祯": 1628,
    "天命": 1616, "天聪": 1627, "崇德": 1636, "顺治": 1644, "康熙": 1662,
    "雍正": 1723, "乾隆": 1736, "嘉庆": 1796, "道光": 1821, "咸丰": 1851,
    "同治": 1862, "光绪": 1875, "宣统": 1909,
}
# 帝王名→在位区间（用于"明熹宗时""康熙皇帝登位以后"类朝代锚；区间来自常见史历，待考订表回填）
EMPEROR_RANGE = {
    "明神宗": (1573, 1620), "明光宗": (1620, 1620), "明熹宗": (1621, 1627),
    "明思宗": (1628, 1644), "崇祯帝": (1628, 1644), "万历帝": (1573, 1620),
    "顺治帝": (1644, 1661), "康熙帝": (1662, 1722), "雍正帝": (1723, 1735),
    "乾隆帝": (1736, 1795),
}
# 年号单独出现（无年数）→ 在位区间（年级不可定，纪年级区间约束；§2.2/§3.1）
REIGN_RANGE = {
    "洪武": (1368, 1398), "永乐": (1403, 1424), "嘉靖": (1522, 1566), "隆庆": (1567, 1572),
    "万历": (1573, 1620), "泰昌": (1620, 1620), "天启": (1621, 1627), "崇祯": (1628, 1644),
    "天命": (1616, 1626), "天聪": (1627, 1635), "崇德": (1636, 1643), "顺治": (1644, 1661),
    "康熙": (1662, 1722), "雍正": (1723, 1735), "乾隆": (1736, 1795), "嘉庆": (1796, 1820),
    "道光": (1821, 1850), "咸丰": (1851, 1861), "同治": (1862, 1874), "光绪": (1875, 1908),
}
# 朝代/时代段（纪元级；§2.2 粒度五级；公元前用负数）
DYNASTY_RANGE = {
    "春秋": (-770, -476), "战国": (-475, -221), "秦": (-221, -207),
    "汉": (-202, 220), "东汉": (25, 220), "西汉": (-202, 9),
    "晋": (265, 420), "东晋": (317, 420), "隋": (581, 618),
    "唐": (618, 907), "五代": (907, 960), "宋": (960, 1279),
    "北宋": (960, 1127), "南宋": (1127, 1279), "元": (1271, 1368),
    "明": (1368, 1644), "清": (1644, 1912),
    "南朝": (420, 589), "南朝梁": (502, 557), "南朝陈": (557, 589),
    "北朝": (386, 581), "北魏": (386, 534), "梁": (502, 557),
}
GANZHI = list("甲乙丙丁戊己庚辛壬癸")
ZHI = list("子丑寅卯辰巳午未申酉戌亥")
GANZHI_BASE_YEAR = 4          # 公元 4 年=甲子（六十甲子循环基准）

# ────────────────────────── 粒度/时令/日转 词表（§2.2 / §7.6 词表需求清单的规则化落地） ──────────────────────────
# 注：SKILL §7.6 明确"词表正则只是盲区兜底，规则主体是显式清单＋正误例"；此处清单从 5 书实测词形抽取。
DAY_SHIFT = {  # 日级（+/-天）
    "翌日": 1, "次日": 1, "第二天": 1, "第二日": 1, "第二天一早": 1, "第二日一早": 1,
    "次日一早": 1, "翌晨": 1, "隔日": 1, "过了一日": 1,
    "明日": 1, "明天": 1, "明晚": 1, "明日一早": 1, "明天一早": 1,
    "今日": 0, "今天": 0, "当天": 0, "当日": 0, "今晚": 0, "今天一早": 0,
    "昨日": -1, "昨天": -1, "昨晚": -1, "昨夜": -1, "前日": -2, "前天": -2,
    "前晚": -2, "前一天": -1,
}
YEAR_SHIFT = {  # 年级相对（仅相对年份关系；§7.4 "这一年/是年"回指不新建）
    "今年": 0, "本年": 0, "当年": 0, "这一年": 0, "是年": 0, "同年": 0,
    "明年": 1, "下一年": 1, "转过年": 1, "第二年": 1,
    "去年": -1, "上一年": -1, "前年": -2,
}
ANAPHORIC = {  # 回指型（§4.4：回指已叙事件/人物 → 指向首叙时点，不新建）
    "这一年", "是年", "同年", "当年", "这日", "是日", "此时", "这时", "那时",
    "那一日", "那一年", "那一夜", "是夜", "当夜", "当晚", "这晚", "此夜",
    "今日", "今天", "昨晚", "昨日", "昨天", "昨夜", "前日", "前天", "前晚",
}
# 时令/节令（季月级；月-日序按西历近似，仅作年内区间与排序辅助，§3.1 时令锚 low~medium）
FESTIVAL_DAY = {
    "元宵": (1, 15), "元宵节": (1, 15), "上元": (1, 15), "清明": (4, 5),
    "端午": (5, 5), "端阳": (5, 5), "七夕": (7, 7), "中元": (7, 15),
    "中秋": (8, 15), "中秋佳节": (8, 15), "重阳": (9, 9), "腊八": (12, 8),
    "除夕": (12, 30), "大年夜": (12, 30), "新正": (1, 1), "新年": (1, 1),
}
SEASON_DAY = {
    "开春": (2, 15), "初春": (2, 15), "暮春": (4, 15), "春": (3, 15),
    "入夏": (5, 15), "初夏": (5, 15), "夏": (6, 15), "凉秋九月": (9, 1),
    "初秋": (8, 15), "秋": (9, 15), "秋收后": (10, 15), "入冬": (11, 15),
    "冬": (12, 15), "寒冬": (12, 15),
}
# 日内级词（§2.2 日内级：只保序不换钟点；日序仅作排序参考）
DAILY_TIME = {
    "五更": (3, 5), "五更时分": (3, 5), "三更": (23, 1), "三更天": (23, 1),
    "四更": (1, 3), "二更": (21, 23), "一更": (19, 21), "半夜": (0, 1),
    "午夜": (0, 1), "午夜时分": (0, 1), "夜深时分": (1, 2), "子时": (23, 1),
    "丑时": (1, 3), "寅时": (3, 5), "卯时": (5, 7), "辰时": (7, 9),
    "午时": (11, 13), "日中": (12, 12), "黄昏": (18, 19), "黄昏时分": (18, 19),
    "傍晚": (18, 19), "日落": (18, 19), "天色微明": (5, 5), "天亮": (5, 6),
    "天明": (5, 6), "拂晓": (5, 6), "黎明": (5, 6), "朝阳初上": (6, 7),
    "日出": (6, 7), "月亮东升": (19, 20), "月亮渐渐西移": (23, 24),
    "残月西沉": (5, 5), "曙色欲现": (5, 5), "星横斗转": (2, 3),
    "天近黄昏": (18, 19), "夜": (22, 23), "夜晚": (22, 23),
}
DAILY_SUFFIX = ("时分", "初上", "渐近中天", "东升", "西沉", "西移", "欲现")

# 季节/时令/节日/日内/日转/年转 统一识别（顺序即优先级）
REL_OFFSET_RE = re.compile(
    r"(?P<num>[一二三四五六七八九十百千零〇廿卅两\d]+)\s*个?\s*(?P<dur>多|余|来|几)?\s*"
    r"(?P<unit>年|载|个月|月|天|日|夜|个时辰|时辰|更)\s*(?P<dir>之前|以前|前|之后|以后|后)")
# "前几天/后几天/前些年"（方向词在前）与"半月/数年"（半/数/几 起首约量）
REL_PRE_RE = re.compile(
    r"(?P<pre>前|后)(?P<num>[一二三四五六七八九十百千零〇廿卅两几数\d]+)\s*(?P<unit>年|载|个月|月|天|日|夜|更)")
REL_HALF_RE = re.compile(r"半\s*(?P<unit>年|载|个月|月|天|日|个时辰|时辰|更)\s*(?P<dir>之前|以前|前|之后|以后|后)?")
FULL_YEAR_RE = re.compile(
    r"(?:(?P<dyn>明|清|元|宋|唐|汉|晋|隋)\s*)?"
    r"(?P<era>" + "|".join(sorted(REIGN_START, key=len, reverse=True)) + r")\s*"
    r"(?P<num>[一二三四五六七八九十百千零〇\d]+)\s*年")
YEAR_AFTER_ACCESSION_RE = re.compile(
    r"(?P<era>" + "|".join(sorted(REIGN_START, key=len, reverse=True)) + r")"
    r"(?:入关|登基|即位|称帝)?(?:之|以)?后(?:的)?第?(?P<num>[一二三四五六七八九十百千零〇\d]+)年")
MONTH_DAY_RE = re.compile(r"(?P<m>[一二三四五六七八九十]{1,2})月(?P<d>[一二三四五六七八九十]{1,3})?日?")
ERA_RANGE_RE = re.compile(
    r"(?P<dyn>" + "|".join(sorted(DYNASTY_RANGE, key=len, reverse=True)) + r")"
    r"(?P<sub>朝|代|初|末|中叶|前期|后期|以前|以后|之时|时候|年间)?")
GANZHI_RE = re.compile("[" + "".join(GANZHI) + "][" + "".join(ZHI) + "]")
AGE_RE = re.compile(
    r"(?P<num>[一二三四五六七八九十百千零〇廿卅\d]+)\s*(?:多|余|来|几|出)?\s*(?:岁|龄)|"
    r"年(?:近|过|方|已|将|逾|超|满)?\s*(?P<num2>[一二三四五六七八九十百千零〇廿卅\d]+)\s*(?:多|余|来|几)?\s*(?:岁|旬|龄)?|"
    r"年将弱冠|年逾弱冠|弱冠|而立之年|不惑之年|知命之年|花甲之年|年近古稀|古稀")

# 追叙/回忆/梦境信号（§4.2 fork 叉型；§4.3 叙述模式隔离）
# 注：SKILL §4.4 只把"当年/早在/想当年/N 年前"定为追叙信号；"那时/那一年"等弱回指走 anaphoric（不建 fork）。
FORK_SIGNAL_RE = re.compile(
    r"(当年|想当年|早在|昔年|从前|往年|多年以前|多年前|[一二三四五六七八九十百千\d]+[余几多]?年前|"
    r"十八年前|十六年前|十几年前|数年前|那一夜|回忆|追忆|追溯)")
MEMORY_SIGNAL_RE = re.compile(r"(回忆|追忆|忆起|想起|记得|梦中|梦见|恍惚|依稀|仿佛看见)")
DREAM_SIGNAL_RE = re.compile(r"(梦中|梦见|梦到|幻觉|恍惚)")
# W6 谚语/虚指（§6.3 W6；§7.5 与 $ 分流）
W6_RE = re.compile(
    r"(亿万年|亿万年之久|千余年功力|三百年功力|五百年功力|百年功力|三天三夜说不完|"
    r"三年清知府|不知多少年|数不清的岁月|千秋万载|万古长青)")
# W5 周期（§6.3 W5；"每三年/一年一度/每逢中秋"）
W5_RE = re.compile(r"(每|每逢|一年一度|每岁|逐日|日日|月月)\s*[^。！？；]{0,10}?([一二三四五六七八九十百千\d]+)?\s*(年|月|日|度|次)")
# W1 跳变语境（闭关/学艺/一晃）
W1_RE = re.compile(r"(闭关|练功|学艺|修习|一晃|转眼|倏忽|不知不觉|光阴似箭|岁月如流)")

# 围栏类型（§6.1 错误6：楔子/开场白/回末韵文评点不入故事时间轨；§4.3 隔离）
ISOLATED_FENCES = {"诗", "词", "回末", "回末对", "对联", "歌", "楔子"}

# 13 类机械检查（T 系列，报告编号；与 SKILL §4.1 的 E1-E4 并记）
CHECK_RULES = {
    "E1": ("error", "同线硬倒流：两时点均无分叉、精度非未知、t 递减（§4.1）"),
    "E2": ("warning", "疑似倒流：一方精度=约略（§4.1）"),
    "E3": ("warning", "出现『与此同时』类信号却未登记线间同时（§4.1）"),
    "E4": ("info", "分叉内倒流（合法，仅登记）（§4.1）"),
    "T01": ("warning", "单锚点塌缩：同回 ≥K=3 个事件共享同一推算刻度（§6.2 例1，K 待试点校准）"),
    "T02": ("warning", "追叙未建 fork：非对白叙述出现追叙信号却未隔离（§4.2）"),
    "T03": ("info", "同段同文重复标注/格式伪迹（模式28/34）"),
    "T04": ("warning", "非时间信息混入时间管道（模式29）"),
    "T05": ("warning", "裸时点缺 |时点| 管道（模式26：精度/类型须显式）"),
    "T06": ("warning", "管道误用：时点/时长/年龄三管道与语义不符（§7.3）"),
    "T07": ("warning", "谚语/虚指时间（W6：不入时间轨）"),
    "T08": ("info", "围栏内韵文/回末评点时间：不入故事时间轨（错误6/§4.3）"),
    "T09": ("info", "W1 闭关/学艺跳变候选：时长可作 t 跳变登记（§6.3 W1）"),
    "T10": ("info", "W5 周期性时长：需频次字段，不得按单次计（§6.3 W5）"),
    "T11": ("warning", "同段多锚点年份冲突：双值并存登记，不静默取一（§3.3）"),
    "T12": ("info", "low 置信缺『未确定原因』（§8.3/§2.3 字段要求）"),
    "T15": ("warning", "朝代锚与书内相对链冲突：朝代锚为主 + 登记换算冲突（§2.5 规则5）"),
}

# 43 种错误模式三分裁决（SKILL §6.1 全表；auto=本工具已机械化覆盖）
ERROR_MODE_TABLE = [
    ("错误1", "单锚点塌缩", "改写", "auto:T01（K=3，§6.2 例1）"),
    ("错误2", "锚点本身计算错误", "改写", "manual:锚点验证前置（§5.2）"),
    ("错误3", "前元/中元/后元混淆", "改写", "manual:真实朝代书专用"),
    ("错误4", "年号/帝王混淆", "改写", "auto:T11 初筛"),
    ("错误5", "追叙事件误用当前时间", "改写", "auto:T02/fork"),
    ("错误6", "写作时间≠事件时间", "改写", "auto:T08 围栏隔离"),
    ("错误7", "确定性标注不足", "直迁", "auto:confidence 三档"),
    ("错误8", "世代数≠年数", "改写", "auto:T09/§5.2 当量提示"),
    ("模式1", "夏代事件章节兜底值塌缩", "改写", "auto:T01"),
    ("模式2", "概览-详情双轨分裂", "改写", "manual:双轨同源纪律"),
    ("模式3", "事件误用生卒中点替代", "改写", "manual"),
    ("模式4", "复合总结段落单点标注", "改写", "manual:区间+约略"),
    ("模式5", "连续计年与改元计年混淆", "改写", "manual"),
    ("模式6", "祖先事件误用后裔年代", "改写", "manual"),
    ("模式7", "精确纪年被插值覆盖", "直迁", "auto:M1 直录优先"),
    ("模式8", "岁首十月跨年误标", "改写", "manual:年界归属"),
    ("模式9", "确定性标注批量不足", "直迁", "auto:confidence"),
    ("模式10", "通论章节多时代单锚点塌缩", "改写", "auto:T01+T02"),
    ("模式11", "朝代交替处年号归属", "改写", "manual:崇祯/顺治/康熙衔接"),
    ("模式12", "前后君主纪年衔接处错位", "改写", "manual"),
    ("模式13", "同名君主跨国混淆", "改写", "manual"),
    ("模式14", "即位年与元年纪年错位", "改写", "manual"),
    ("模式15", "概览-详情系统性分裂", "改写", "manual"),
    ("模式16", "纪年 off-by-one", "改写", "manual:偏移起算点规则"),
    ("模式17", "两书同事件年代分歧", "改写", "manual:跨书冲突登记（4.6，需 N5）"),
    ("模式18", "推断理由锚点引用错误", "直迁", "auto:anchor_ref 实填"),
    ("模式19", "拜师年代表整段学艺期", "改写", "auto:T09 提示"),
    ("模式20", "作者叙事框架与史实偏差", "改写", "manual:照记+设定期"),
    ("模式21", "沉寂期/约定时长被压缩", "直迁", "auto:时长→偏移"),
    ("模式22", "传说性人物跨世纪矛盾", "改写", "manual:W 系列接管"),
    ("模式23", "推断行位置错位", "直迁", "auto:段锚必填"),
    ("模式24", "称号语境时间下限", "改写", "manual"),
    ("模式25", "通论跨千年事件共享锚", "改写", "auto:T01/T02"),
    ("模式26", "裸年份缺确定性标记", "改写", "auto:T05"),
    ("模式27", "锚点间时序倒置", "改写", "auto:E1/E2"),
    ("模式28", "时间字段重复标注", "直迁", "auto:T03"),
    ("模式29", "非时间信息混入", "改写", "auto:T04"),
    ("模式30", "传说时代生卒中点不可靠", "改写", "manual:M4 era 区间"),
    ("模式31", "概览-详情双轨偏差", "改写", "manual"),
    ("模式32", "容器事件漏跨年子事件", "改写", "manual:起止成对"),
    ("模式33", "时间字段多重标注冗余", "直迁", "auto:T03"),
    ("模式34", "格式伪迹重复", "直迁", "auto:T03"),
    ("模式35", "脚本修正指令残留", "直迁", "manual:工作流纪律"),
]

TOKEN_RE = re.compile(r"[〖⟦]([^〖⟦〗⟧]+)[〗⟧]")
RHET_RE = re.compile(r"〘([^〙]*)〙")
PARA_RE = re.compile(r"^\[(\d+)\] ")


# ────────────────────────────── 基础工具 ──────────────────────────────
def cn_num(s: str) -> int | None:
    """中文数字/阿拉伯数字 → int（支持 廿/卅、十八、四十三年、一百四十八）。"""
    if not s:
        return None
    s = s.strip()
    s = s.replace("廿", "二十").replace("卅", "三十").replace("卌", "四十")
    if s.isdigit():
        return int(s)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000}
    total, section, num = 0, 0, None
    for ch in s:
        if ch in digits:
            num = digits[ch]
        elif ch in units:
            section += (num if num is not None else 1) * units[ch]
            num = None
        elif ch.isdigit():
            num = int(ch)
        else:
            continue
    if num is not None:
        section += num
    total += section
    return total if total or s.strip() in ("零", "〇") else None


def strip_markup(text: str) -> str:
    """删除标注括号保留显示串（与 tagged 剥标口径一致；管道取显示串；含修辞层 〘※…〙）。"""
    text = TOKEN_RE.sub(lambda m: m.group(1)[1:].split("|")[0].split("｜")[0], text)
    return RHET_RE.sub(lambda m: m.group(1)[1:] if m.group(1).startswith("※") else m.group(1), text)


def day_of_year(month: int, day: int) -> int:
    """月-日 → 年内日序（西历近似；只用于书内排序，不作公历承诺）。"""
    cum = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    return cum[max(0, min(12, month) - 1)] + day


def ganzhi_candidates(gz: str) -> list[int]:
    """干支 → 公历年候选（60 年一循环；基准 公元 4 年=甲子）。"""
    if len(gz) != 2 or gz[0] not in GANZHI or gz[1] not in ZHI:
        return []
    g = (GANZHI.index(gz[0]) - GANZHI.index("甲")) % 10
    z = (ZHI.index(gz[1]) - ZHI.index("子")) % 12
    # 解同余：year ≡ g+4 (mod 10), year ≡ z+4 (mod 12)
    cands = []
    for y in range(1300, 1901):
        if (y - GANZHI_BASE_YEAR) % 10 == g and (y - GANZHI_BASE_YEAR) % 12 == z:
            cands.append(y)
    return cands


def parse_era_anchor(display: str) -> dict | None:
    """识别朝代锚（§3.1 四类锚点之首）：年号+年 / 年号登基后第N年 / 帝王名 / 朝代时代段 / 干支。

    返回 {kind: year|range|ganzhi, year|range|candidates, basis, era_span}
    """
    m = FULL_YEAR_RE.search(display)
    if m:
        era = m.group("era")
        n = cn_num(m.group("num"))
        if era in REIGN_START and n:
            if era in ("顺治", "康熙", "雍正", "乾隆"):
                pass  # 清朝年号直接换算（明末清初书常见）
            return {"kind": "year", "year": REIGN_START[era] + n - 1,
                    "basis": f"年号换算：{era}元年={REIGN_START[era]} + {n}-1",
                    "anchor_type": "朝代锚", "granularity": "年级"}
    m = YEAR_AFTER_ACCESSION_RE.search(display)
    if m:
        era = m.group("era")
        n = cn_num(m.group("num"))
        if era in REIGN_START and n:
            return {"kind": "year", "year": REIGN_START[era] + n - 1,
                    "basis": f"年号换算（入关/登基后第{n}年）：{era}元年={REIGN_START[era]} + {n}-1",
                    "anchor_type": "朝代锚", "granularity": "年级"}
    for name, (lo, hi) in EMPEROR_RANGE.items():
        if name in display:
            return {"kind": "range", "range": [lo, hi],
                    "basis": f"帝王纪年区间：{name} {lo}-{hi}",
                    "anchor_type": "朝代锚", "granularity": "纪元级"}
    # 年号单独出现（乾隆/康熙皇帝/康熙年间）→ 在位区间（年级不可定）
    for name, (lo, hi) in REIGN_RANGE.items():
        if name in display:
            return {"kind": "range", "range": [lo, hi],
                    "basis": f"年号区间（无具体年数）：{name} {lo}-{hi}",
                    "anchor_type": "朝代锚", "granularity": "纪元级"}
    # 干支（甲申/乙酉…；候选在书内锚点年份附近择一，见 resolve_era）
    gzm = GANZHI_RE.search(display)
    if gzm and len(display) <= 4:
        cands = ganzhi_candidates(gzm.group(0))
        if cands:
            return {"kind": "ganzhi", "candidates": cands,
                    "basis": f"干支纪年 {gzm.group(0)}（60 年循环，候选 {cands[0]}…{cands[-1]}）",
                    "anchor_type": "朝代锚", "granularity": "年级"}
    # 朝代/时代段（纪元级；无具体年 → 只作区间约束，§2.2）；排除"明晚/明代词内"等假匹配
    m = ERA_RANGE_RE.search(display)
    if m and (m.group("sub") is not None or display.strip() in DYNASTY_RANGE):
        dyn = m.group("dyn")
        if dyn in DYNASTY_RANGE:
            lo, hi = DYNASTY_RANGE[dyn]
            sub = m.group("sub") or ""
            if "初" in sub:
                hi = min(hi, lo + 60)
            elif "末" in sub:
                lo = max(lo, hi - 60)
            elif "中叶" in sub:
                lo, hi = lo + 60, hi - 60
            return {"kind": "range", "range": [lo, hi],
                    "basis": f"朝代/时代段：{dyn}{sub} {lo}-{hi}（纪元级区间约束，§2.2/§2.5）",
                    "anchor_type": "朝代锚", "granularity": "纪元级"}
    return None


_APPROX_NUM = {"几": 3, "数": 3, "半": 0.5, "两": 2}


def _num_or_approx(s: str) -> float | None:
    if s in _APPROX_NUM:
        return float(_APPROX_NUM[s])
    n = cn_num(s)
    return float(n) if n is not None else None


def _unit_days(unit: str) -> tuple[float, str]:
    if unit in ("年", "载"):
        return 365.0, "年"
    if unit in ("个月", "月"):
        return 30.0, "月"
    if unit in ("天", "日", "夜"):
        return 1.0, "日"
    if unit in ("个时辰", "时辰"):
        return 1 / 12, "时辰"
    return 0.5, "更"


def parse_relative_offset(display: str) -> dict | None:
    """相对偏移（§3.1 事件锚·强/弱）：N年前/三日后/几个月后/十年前/前几天/半月之后。"""
    if display in DAILY_TIME:      # "半夜/五更"是时点词，不是"半个夜"时长（防半-夜误匹配）
        return None
    m = REL_OFFSET_RE.search(display)
    if m:
        n = _num_or_approx(m.group("num"))
        if n is not None:
            unit_days, unit_name = _unit_days(m.group("unit"))
            sign = -1 if m.group("dir") in ("之前", "以前", "前") else 1
            vague = bool(m.group("dur")) or m.group("num") in "几数" or "半" in m.group("num")
            return {
                "offset_days": sign * n * unit_days, "offset_value": sign * n,
                "offset_unit": unit_name, "direction": "前" if sign < 0 else "后",
                "precision": "约略" if vague else "精确",
                "anchor_type": "事件锚",
                "strong": unit_name in ("年", "月", "日") and not vague,
            }
    m = REL_PRE_RE.search(display)
    if m:
        n = _num_or_approx(m.group("num"))
        if n is not None:
            unit_days, unit_name = _unit_days(m.group("unit"))
            sign = -1 if m.group("pre") == "前" else 1
            return {
                "offset_days": sign * n * unit_days, "offset_value": sign * n,
                "offset_unit": unit_name, "direction": m.group("pre"),
                "precision": "约略", "anchor_type": "事件锚", "strong": False,
            }
    m = REL_HALF_RE.search(display)
    if m:
        unit_days, unit_name = _unit_days(m.group("unit"))
        sign = -1 if (m.group("dir") or "") in ("之前", "以前", "前") else 1
        return {
            "offset_days": sign * 0.5 * unit_days, "offset_value": sign * 0.5,
            "offset_unit": unit_name, "direction": "前" if sign < 0 else "后",
            "precision": "约略", "anchor_type": "事件锚", "strong": False,
        }
    return None


def parse_month_day_in(display: str) -> int | None:
    """从含年份的日期串中取月-日（如"康熙六十一年一月十三日"），返回年内日序。"""
    m = MONTH_DAY_RE.search(display)
    if not m:
        return None
    month = cn_num(m.group("m")) or 0
    day = cn_num(m.group("d") or "1") or 1
    if 1 <= month <= 12 and 1 <= day <= 31:
        return day_of_year(month, day)
    return None


def parse_age(display: str) -> dict | None:
    """年龄锚（§3.1 人物年龄锚；§7.2 年龄陈述句：框架词不入实体、原文无"岁"不补）。"""
    num = None
    for pat in (r"([一二三四五六七八九十百千零〇廿卅\d]+)\s*(?:多|余|来|几|出)?\s*(?:岁|龄)",):
        m = re.search(pat, display)
        if m:
            num = cn_num(m.group(1))
            break
    if num is None:
        m = re.search(r"([一二三四五六七八九十百千零〇廿卅\d]+)\s*(?:多|余|来|几)?\s*旬", display)
        if m:
            n = cn_num(m.group(1))
            num = n * 10 if n else None
    if num is None:
        m = re.search(r"年(?:近|过|方|已|将|逾|超|满)?\s*([一二三四五六七八九十百千零〇廿卅\d]+)", display)
        if m:
            num = cn_num(m.group(1))
    if num is None:
        # 裸数字 + 约量后缀（年龄管道已由上游确定语义，如"五十左右/四十许"；§7.2）
        m = re.search(r"([一二三四五六七八九十百千零〇廿卅\d]+)\s*(?:左右|上下|出头|开外|许|有余|将近|不到)", display)
        if m:
            num = cn_num(m.group(1))
    if num is None:
        for word, val in (("弱冠", 20), ("而立之年", 30), ("不惑之年", 40),
                          ("知命之年", 50), ("花甲之年", 60), ("古稀", 70)):
            if word in display:
                num = val
                break
    if num is None:
        return None
    vague = bool(re.search(r"(多|余|来|几|左右|上下|出头|开外|将近|不到)", display))
    return {"age": num, "precision": "约略" if vague else "精确"}


def parse_day_shift(display: str) -> dict | None:
    """日转扩展（§7.6 词表需求；"第三天/第四日/第二日中午/这晚/这日一早"）：+N-1 天/同时。"""
    m = re.fullmatch(r"第([一二三四五六七八九十百\d]+)(天|日|夜)(一早|早上|早晨|上午|中午|下午|傍晚|晚上|夜里|黎明|天亮|拂晓|黄昏)?", display)
    if m:
        n = cn_num(m.group(1)) or 1
        return {"offset_days": float(n - 1), "precision": "精确",
                "basis": f"第N日转：第{n}{m.group(2)}→+{n - 1}日（§4.4 前向偏移）"}
    m = re.fullmatch(r"(这|是|当|同)(日|天)(一早|早上|早晨|上午|中午|下午|傍晚|晚上|夜)?", display)
    if m:
        return {"offset_days": 0.0, "precision": "精确", "basis": "当日回指（±0 日；§4.4 回指）"}
    m = re.fullmatch(r"(一|某|那)(日|天)(下午|上午|中午|傍晚|晚上|一早|早上)?", display)
    if m:
        return {"offset_days": 0.0, "precision": "约略", "basis": "场景起句日指（±0 日；归最低可保证级）"}
    if display in ("这晚", "当晚", "是夜", "当夜", "此夜"):
        return {"offset_days": 0.0, "precision": "精确", "basis": "当夜/回指（±0 日）"}
    if display in ("次晚", "明夜", "翌晚"):
        return {"offset_days": 1.0, "precision": "精确", "basis": "次晚→+1日"}
    return None


def classify_time_type(display: str, meta: str) -> str:
    """时间类型四值（§2.3）：时点/时长/年龄/周期（跳变经 W1 入条件字段，不是表达类型）。"""
    if meta in ("时点", "时长", "年龄"):
        return meta
    if meta == "周期":
        return "周期"
    # 裸 %（无管道；§7.1 降级期历史示例）→ 依词形兜底推断并报 T05
    if parse_age(display) is not None and re.search(r"(岁|龄|弱冠|古稀|花甲|不惑|知命)", display):
        return "年龄"
    if re.search(r"(年|月|日|天|夜|时辰|更|载|世纪)$", display):
        return "时点" if re.search(r"(前|后|昨天|明日|翌日|次年|今日|今|明|昨|当年)", display) else "时长"
    return "时点"


def classify_granularity(display: str, ttype: str, era: dict | None) -> str:
    """粒度五级（§2.2）：纪元级/年级/季月级/日级/日内级；模糊表达归最低可保证级。"""
    if era:
        return era.get("granularity", "年级")
    if ttype == "时长":
        if re.search(r"(年|载)$", display):
            return "年级"
        if "月" in display:
            return "季月级"
        if re.search(r"(时辰|更)$", display):
            return "日内级"
        return "日级"
    if ttype == "年龄":
        return "年级"
    if re.fullmatch(r"[一二三四五六七八九十百千零〇廿卅\d]+(多|余|来|几)?(年|载)", display) and ttype == "时点":
        return "年级"
    if display in FESTIVAL_DAY or display in SEASON_DAY or "月" in display and "日" not in display:
        return "季月级"
    if MONTH_DAY_RE.fullmatch(display):
        return "日级"
    if display in DAILY_TIME or display.endswith(DAILY_SUFFIX) or re.search(r"(更|时分|半夜|午夜|黄昏|晌午|午时|夜|晓|曙)", display):
        return "日内级"
    if display in DAY_SHIFT:
        return "日级"
    if display in YEAR_SHIFT or REL_OFFSET_RE.search(display):
        return "年级"
    if ttype == "年龄":
        return "年级"
    if ttype == "时长":
        return "日级"
    return "未知"


def detect_narrative_signals(display: str, context: str) -> list[str]:
    """叙述模式/分叉信号（§4.2/§4.3）：追叙、回忆、梦境、同时（"与此同时"）。"""
    sig = []
    if re.search(r"(与此同时|就在这时|同一时候|在同一时候)", context):
        sig.append("simultaneous")
    if DREAM_SIGNAL_RE.search(context):
        sig.append("dream")
    elif MEMORY_SIGNAL_RE.search(context):
        sig.append("memory")
    if FORK_SIGNAL_RE.search(display) or FORK_SIGNAL_RE.search(context[MAX(0, len(context) // 2 - 25): len(context) // 2 + 25]):
        sig.append("flashback")
    return sig


# ────────────────────────────── 数据模型 ──────────────────────────────
@dataclass
class TimeToken:
    book: str
    chapter: int
    pn: int
    line_no: int
    raw_start: int
    raw_end: int
    raw: str
    display: str
    pipe: str          # 时点/时长/年龄/""（裸 %）
    context: str       # 剥标上下文（±28 字，token 以【】标出）
    fence: str         # 所在围栏类型；""=正文
    dialogic: bool     # 是否在中文引号对白内

    # 解析结果
    tp_id: str = ""
    ttype: str = "未知"
    granularity: str = "未知"
    anchor_type: str = "未知"
    anchor_ref: str = ""          # tp_id / era / event
    offset_days: float | None = None
    t_days: float | None = None
    year_ce: int | None = None
    year_range: list[int] | None = None
    age: int | None = None
    duration_days: float | None = None
    precision: str = "未知"
    confidence: str = "low"
    basis: str = ""
    status: str = "unresolved"    # mainline|dialogic|fence|fork|anaphoric|background|unresolved|duration|age
    fork_id: str = ""
    simultaneous_to: str = ""
    flags: list[str] = field(default_factory=list)
    unknown_reason: str = ""


@dataclass
class Paragraph:
    pn: int
    line_no: int
    raw: str
    plain: str
    fence: str


@dataclass
class Fork:
    fork_id: str
    fork_type: str
    base_tp_id: str
    offset_value: float
    offset_unit: str
    event_tp_ids: list[str]
    reinsert_anchor: dict
    confidence: str
    basis: str


class BookIndex:
    """只读索引 tagged/<书>/NNN.tagged.md（+ struct 对账）：段落、围栏、回目、% 令牌。"""

    def __init__(self, book: str):
        self.book = book
        self.dir = TAGGED_DIR / book
        self.paras: dict[tuple[int, int], Paragraph] = {}
        self.titles: dict[int, str] = {}
        self.chapters: list[int] = []
        self.warnings: list[str] = []
        self.struct_parity_ok = 0
        self.struct_parity_bad: list[str] = []
        if not self.dir.is_dir():
            self.warnings.append(f"tagged 目录不存在：{self.dir}")
            return
        for path in sorted(self.dir.glob("*.tagged.md")):
            stem = path.stem.split(".")[0]
            if not stem.isdigit():
                continue
            ch = int(stem)
            self.chapters.append(ch)
            fence = ""
            struct_lines: list[str] = []
            sp = self.dir / f"{stem}.struct.md"
            if sp.exists():
                struct_lines = sp.read_text(encoding="utf-8").splitlines()
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
                self.paras[(ch, pn)] = Paragraph(pn, i, line, strip_markup(line), fence)
                # struct 对账（剥标 == struct 行内容；可审计原则）
                if struct_lines:
                    for sl in struct_lines:
                        if sl.startswith(f"[{pn}] "):
                            if strip_markup(line) == sl:
                                self.struct_parity_ok += 1
                            else:
                                self.struct_parity_bad.append(f"{ch:03d}[{pn}]")
                            break

    def quote_mask(self, para: Paragraph, raw_start: int) -> bool:
        """粗判 token 是否位于中文引号对白内（“…”）。对白内时间不推进主轨（叙述模式隔离）。"""
        prefix = para.raw[:raw_start]
        return prefix.count("“") > prefix.count("”")

    def iter_tokens(self) -> list[TimeToken]:
        out: list[TimeToken] = []
        for (ch, pn), para in sorted(self.paras.items()):
            for m in TOKEN_RE.finditer(para.raw):
                inner = m.group(1)
                if not inner.startswith("%"):
                    continue
                body = inner[1:]
                parts = re.split(r"[|｜]", body, maxsplit=1)
                display = parts[0]
                pipe = parts[1] if len(parts) > 1 else ""
                plain = para.plain
                # token 在 plain 中的位置（用于上下文窗口）
                pstart = len(strip_markup(para.raw[:m.start()]))
                ctx = plain[max(0, pstart - 28):pstart] + "【" + display + "】" + \
                    plain[pstart + len(display):pstart + len(display) + 28]
                out.append(TimeToken(
                    book=self.book, chapter=ch, pn=pn, line_no=para.line_no,
                    raw_start=m.start(), raw_end=m.end(), raw=m.group(0),
                    display=display, pipe=pipe, context=ctx, fence=para.fence,
                    dialogic=self.quote_mask(para, m.start()),
                ))
        return out


# ────────────────────────────── 单令牌分类 ──────────────────────────────
def classify_token(tok: TimeToken, anchor_median_year: int | None) -> None:
    """S2：类型/粒度/锚点/解析值/置信度（§2.2/§2.3/§3.1/§3.2/§8.1）。"""
    tok.ttype = classify_time_type(tok.display, tok.pipe)
    era = None
    if tok.ttype == "时点":
        # 日转/年转词（明晚/第二日黎明/明年…）先排朝代词法假匹配（"明"在"黎明/明晚"中不是明朝）
        if tok.display not in DAY_SHIFT and tok.display not in YEAR_SHIFT \
                and parse_day_shift(tok.display) is None \
                and not re.match(r"^(明|清|元|宋|唐|汉|晋|隋)(晚|早|日|天|年|儿|晨|夜|朝暮)", tok.display):
            era = parse_era_anchor(tok.display)
    tok.granularity = classify_granularity(tok.display, tok.ttype, era)

    # ---- 围栏隔离（错误6/T08） ----
    fence_iso = bool(tok.fence) and any(f in tok.fence for f in ISOLATED_FENCES)
    if fence_iso:
        tok.flags.append("T08")

    # ---- 朝代锚（§3.1/§3.2 最高置信） ----
    if era:
        tok.anchor_type = "朝代锚"
        if era["kind"] == "year":
            tok.year_ce = era["year"]
            tok.precision = "精确"
            tok.confidence = "high"
            tok.basis = era["basis"] + "（M1 直录法，§5.1）"
            tok.anchor_ref = f"era:{tok.year_ce}"
        elif era["kind"] == "range":
            tok.year_range = list(era["range"])
            tok.precision = "约略"
            tok.confidence = "low" if era["range"][1] - era["range"][0] > 15 else "medium"
            tok.basis = era["basis"] + "（M4 朝代区间约束，§5.1）"
            tok.anchor_ref = f"era:{tok.year_range[0]}-{tok.year_range[1]}"
            if tok.year_range[1] - tok.year_range[0] > 15 and tok.confidence != "low":
                tok.confidence = "low"
        else:   # ganzhi → 候选在书内锚点年份附近择一（歧义显式登记）
            cands = era["candidates"]
            pick = None
            if anchor_median_year is not None:
                pick = min(cands, key=lambda y: abs(y - anchor_median_year))
                tok.flags.append("T13")
                tok.basis = era["basis"] + f"；按书内锚点中位年 {anchor_median_year} 择 {pick}"
            else:
                tok.basis = era["basis"] + "；书内无锚点年份，候选并列不猜"
            tok.year_ce = pick
            tok.year_range = [cands[0], cands[-1]]
            tok.precision = "精确" if pick else "未知"
            tok.confidence = "medium" if pick else "low"
            tok.anchor_ref = f"era:ganzhi:{cands[0]}"
        # 大跨度背景（纪元级/区间/远早于故事）后续在排轨时隔离为 background
        return

    # ---- 年龄锚（§3.1/§7.2） ----
    if tok.ttype == "年龄":
        age = parse_age(tok.display)
        if age:
            tok.anchor_type = "人物年龄锚"
            tok.age = age["age"]
            tok.precision = age["precision"]
            tok.confidence = "medium"
            tok.basis = f"年龄陈述直录（§7.2；M3 年龄锚定年，§5.1）"
        else:
            tok.anchor_type = "未知"
            tok.precision = "未知"
            tok.confidence = "low"
            tok.unknown_reason = "年龄词形不可解析"
            tok.flags.append("T04")
        # W2 外貌不作年龄证据（§6.3）
        if re.search(r"(驻颜|返老还童|容颜不变|白发童颜|容貌如昔)", tok.context):
            tok.flags.append("W2")
            tok.confidence = "low"
        return

    # ---- 时长（不产生时点；W1/W5/W6 条件字段，§6.3；非锚点类型） ----
    if tok.ttype == "时长":
        tok.anchor_type = "非锚点·时长"
        m = re.search(r"([一二三四五六七八九十百千零〇廿卅\d]+)\s*(多|余|来|几)?\s*(年|载|个月|月|天|日|夜|个时辰|时辰|更)",
                      tok.display)
        if m:
            n = cn_num(m.group(1))
            unit = m.group(3)
            unit_days = {"年": 365.0, "载": 365.0, "个月": 30.0, "月": 30.0,
                         "天": 1.0, "日": 1.0, "夜": 1.0, "个时辰": 1 / 12, "时辰": 1 / 12,
                         "更": 0.5}[unit]
            tok.duration_days = (n or 0) * unit_days
            tok.precision = "约略" if m.group(2) or "几" in tok.display else "精确"
            tok.basis = f"时长直录：{n}{unit}（§7.3；t 不跳变，W1 需显式登记）"
            tok.confidence = "high" if tok.precision == "精确" else "medium"
        else:
            tok.unknown_reason = "时长词形不可解析"
            tok.precision = "未知"
        if W6_RE.search(tok.display):
            tok.flags.append("T07")
            tok.confidence = "low"
            tok.duration_days = None
            tok.unknown_reason = "W6 谚语/虚指（§6.3）"
        if W1_RE.search(tok.context):
            tok.flags.append("T09")
        if W5_RE.search(tok.context):
            tok.flags.append("T10")
        return

    # ---- 时点：相对偏移 / 日转 / 年转 / 时令 / 日内 / 回指 / 未知 ----
    rel = parse_relative_offset(tok.display)
    if rel:
        tok.anchor_type = "事件锚"
        tok.offset_days = rel["offset_days"]
        tok.precision = rel["precision"]
        tok.confidence = "medium" if rel["strong"] else "low"
        tok.basis = f"相对偏移：{rel['offset_value']:+g}{rel['offset_unit']}（§3.1 事件锚{'·强' if rel['strong'] else '·弱'}）"
        return
    if tok.display in DAY_SHIFT:
        tok.anchor_type = "事件锚"
        tok.offset_days = float(DAY_SHIFT[tok.display])
        tok.precision = "精确"
        tok.confidence = "high"
        tok.basis = f"日转词：{tok.display}→{DAY_SHIFT[tok.display]:+d}日（§4.4 前向偏移）"
        return
    dayx = parse_day_shift(tok.display)
    if dayx:
        tok.anchor_type = "事件锚"
        tok.offset_days = dayx["offset_days"]
        tok.precision = dayx["precision"]
        tok.confidence = "high"
        tok.granularity = "日级"
        tok.basis = dayx["basis"]
        return
    if tok.display in YEAR_SHIFT:
        shift = YEAR_SHIFT[tok.display]
        tok.anchor_type = "事件锚"
        tok.offset_days = shift * 365.0
        tok.precision = "精确" if tok.display not in ANAPHORIC else "约略"
        tok.confidence = "high" if shift else "medium"
        tok.basis = f"年转/回指词：{tok.display}→{shift:+d}年（§7.4『这一年』回指不新建）"
        if tok.display in ANAPHORIC:
            tok.flags.append("回指")
        return
    if tok.display in FESTIVAL_DAY or tok.display in SEASON_DAY:
        month, day = FESTIVAL_DAY.get(tok.display) or SEASON_DAY[tok.display]
        tok.anchor_type = "时令锚"
        tok.offset_days = float(day_of_year(month, day))
        tok.precision = "精确" if tok.display in FESTIVAL_DAY else "约略"
        tok.confidence = "medium" if tok.display in FESTIVAL_DAY else "low"
        tok.basis = f"时令锚：{tok.display}≈{month}月{day}日（§3.1 时令锚；年内区间）"
        return
    # 时令词的模糊变体（"中秋将近""将近中秋"等；归最低可保证级，§2.2）
    for fname, (fm, fd) in FESTIVAL_DAY.items():
        if fname in tok.display:
            tok.anchor_type = "时令锚"
            tok.granularity = "季月级"
            tok.offset_days = float(day_of_year(fm, fd))
            tok.precision = "约略"
            tok.confidence = "low"
            tok.basis = f"时令锚（模糊变体）：{tok.display}⊃{fname}≈{fm}月{fd}日（§2.2 最低可保证级）"
            return
    m = MONTH_DAY_RE.fullmatch(tok.display)
    if m:
        month = cn_num(m.group("m")) or 0
        day = cn_num(m.group("d") or "1") or 1
        tok.anchor_type = "时令锚"
        tok.granularity = "日级"
        tok.offset_days = float(day_of_year(month, day))
        tok.precision = "精确"
        tok.confidence = "medium"
        tok.basis = f"月日表达：{month}月{day}日（需年份锚；年由主轨推定，§2.3 偏移字段）"
        return
    if tok.display in DAILY_TIME or tok.display.endswith(DAILY_SUFFIX) or \
            re.search(r"(更|时分|半夜|午夜|黄昏|午时|夜|晓|曙|日落|日出|月亮|残月|朝阳)", tok.display):
        tok.anchor_type = "时令锚"
        tok.granularity = "日内级"
        tok.precision = "约略"
        tok.confidence = "low"
        tok.basis = "日内级时点：只保序不换钟点（§2.2 日内级定版）"
        return
    # 修辞/天象时点（月华如练/月光/月近中天/曙色/暮色）：时令锚（§3.1；修辞化用降 low）
    if re.search(r"(月华|月光|月近|月已|月如|新月|天心|夜色|曙|暮色|暮霭|天光|日色|晨光|晓色|星斗|星河)", tok.display):
        tok.anchor_type = "时令锚"
        tok.granularity = "日内级"
        tok.precision = "约略"
        tok.confidence = "low"
        tok.basis = "修辞/天象时点：归时令锚最低可保证级（§2.2/§3.1）"
        return
    # 时段词（下午/晌午/夜里…；无日转词时的场景时段）
    if re.search(r"(下午|上午|中午|晌午|傍晚|夜里|晚上|清晨|早晨)", tok.display):
        tok.anchor_type = "时令锚"
        tok.granularity = "日内级"
        tok.precision = "约略"
        tok.confidence = "low"
        tok.basis = "日内时段词：只保序不换钟点（§2.2 日内级）"
        return
    if tok.display in ANAPHORIC:
        tok.anchor_type = "事件锚"
        tok.precision = "约略"
        tok.confidence = "medium"
        tok.basis = "回指已叙时点（§4.4：指向首叙时点，不新建）"
        tok.flags.append("回指")
        return
    # 未知（不猜；§8.4 未知原则）
    tok.anchor_type = "未知"
    tok.granularity = "未知"
    tok.precision = "未知"
    tok.confidence = "low"
    tok.unknown_reason = "原文未给/词形不在锚点表"
    tok.flags.append("T04")


# ────────────────────────────── 主轨排轨 ──────────────────────────────
def resolve_book(book: str, chapters: list[int] | None = None) -> dict:
    """S1-S6 主流程：分类 → 主轨排轨（含 fork/隔离）→ 单调性 → 检查 → 统计。"""
    index = BookIndex(book)
    if not index.paras:
        raise RuntimeError(f"{book}: 无可用 tagged 段落（{index.dir}）")
    tokens = [t for t in index.iter_tokens() if chapters is None or t.chapter in chapters]
    # 预扫：书内绝对年份中位数（供干支择年）
    year_hits = []
    for tok in tokens:
        era = parse_era_anchor(tok.display) if classify_time_type(tok.display, tok.pipe) == "时点" else None
        if era and era["kind"] == "year":
            year_hits.append(era["year"])
    anchor_median_year = sorted(year_hits)[len(year_hits) // 2] if year_hits else None
    for tok in tokens:
        classify_token(tok, anchor_median_year)

    work_id = BOOK_IDS.get(book, "book" + str(abs(hash(book)) % 10000))
    # §2.6 纯相对纪律：全无朝代年锚的书（如《冰魄寒光剑》）允许以首个主轨时点为 t=0 原点，
    # 只作书内相对排序，不做任何公历换算。
    allow_pseudo_origin = not any(t.year_ce is not None for t in tokens)
    origin_year: int | None = None
    cur_t: float | None = None
    cur_year: int | None = None
    last_main_tp: TimeToken | None = None
    tps: list[TimeToken] = []
    forks: list[Fork] = []
    anchor_conflict_events: list[dict] = []
    year_anchors = [t for t in tokens if t.year_ce is not None and t.anchor_type == "朝代锚"]
    if year_anchors:
        origin_year = year_anchors[0].year_ce
    mainline: list[TimeToken] = []
    dialogic: list[TimeToken] = []
    anaphoric: list[TimeToken] = []
    background: list[TimeToken] = []
    unresolved: list[TimeToken] = []
    tp_seq = 0

    def assign_tp(tok: TimeToken) -> str:
        nonlocal tp_seq
        tp_seq += 1
        tok.tp_id = f"{work_id}-T{tp_seq:03d}"
        return tok.tp_id

    for tok in tokens:
        tok.tp_id = f"{work_id}-T{tp_seq + 1:03d}"
        # ---- 围栏隔离（错误6/T08） ----
        if tok.fence and any(f in tok.fence for f in ISOLATED_FENCES):
            tok.status = "fence"
            tok.year_ce = None
            tok.t_days = None
            tok.unknown_reason = "围栏内韵文/回末评点，不入故事时间轨（错误6/§4.3）"
            assign_tp(tok)
            tps.append(tok)
            continue
        # ---- 朝代锚：主轨设定/背景隔离 ----
        if tok.anchor_type == "朝代锚":
            if tok.year_ce is not None:
                if origin_year is None:
                    origin_year = tok.year_ce
                if cur_year is None or tok.year_ce >= origin_year - 2:
                    # 主轨绝对锚（M1）；月-日部分并入年内日序
                    year_start = (tok.year_ce - origin_year) * 365.0
                    doy = parse_month_day_in(tok.display)
                    if doy is not None:
                        year_start += doy
                        tok.basis += f"；月日部分并入 +{doy} 日（§2.3 偏移）"
                    # 同/次年锚接在既有相对链之后时取 max，避免"年首日"回退（§2.2 年首日口径的排序折中）
                    new_t = max(cur_t, year_start) if cur_t is not None else year_start
                    # §2.5 规则5：朝代锚与书内相对链冲突 → 朝代锚为主，登记换算冲突（T15）
                    if cur_t is not None and abs(year_start - cur_t) > 2 * 365:
                        anchor_conflict_events.append({
                            "code": "T15", "level": "warning", "chapter": tok.chapter,
                            "message": (f"朝代锚 {tok.display}={tok.year_ce} 与相对链 t={cur_t:.0f} 日"
                                        f"冲突（Δ={new_t - cur_t:+.0f} 日）→ 朝代锚为主，登记换算冲突"),
                            "tp_ids": [tok.tp_id], "cite": "§2.5 规则5/模式11/模式12",
                        })
                        tok.flags.append("T15")
                        tok.basis += "；与相对链冲突→按 §2.5 规则5 以朝代锚为主并登记"
                    cur_year = tok.year_ce
                    cur_t = new_t
                    tok.t_days = cur_t
                    tok.status = "mainline"
                    tok.anchor_ref = f"era:{tok.year_ce}"
                    assign_tp(tok)
                    tps.append(tok)
                    last_main_tp = tok
                    mainline.append(tok)
                else:
                    tok.status = "background"
                    tok.unknown_reason = "历史背景朝代锚（远早于故事主轨），只作区间约束（§2.5）"
                    assign_tp(tok)
                    tps.append(tok)
                    background.append(tok)
            else:   # 区间/干支未决 → 区间约束/背景
                tok.status = "background"
                tok.t_days = None
                tok.unknown_reason = tok.unknown_reason or "朝代区间锚：只作 M4 区间约束，不落主轨"
                assign_tp(tok)
                tps.append(tok)
                background.append(tok)
            continue
        # ---- 年龄锚：记录，不推进主轨 ----
        if tok.ttype == "年龄":
            tok.status = "age"
            if tok.age is not None and cur_year is not None:
                tok.basis += f"；当前主轨年 {cur_year}−{tok.age}≈出生年 {cur_year - tok.age}（M3，合并置信=medium/low）"
                tok.confidence = "low"
            assign_tp(tok)
            tps.append(tok)
            anaphoric.append(tok)
            continue
        # ---- 时长：W1 跳变（主轨推进）/W5 周期登记/否则纯记录 ----
        if tok.ttype == "时长":
            tok.status = "duration"
            if "T09" in tok.flags and tok.duration_days and cur_t is not None and not tok.dialogic:
                cur_t += tok.duration_days
                tok.t_days = cur_t
                tok.status = "mainline"
                tok.basis += "；W1 跳变登记：t += Δ（§6.3 W1）"
                mainline.append(tok)
                assign_tp(tok)
                tps.append(tok)
                last_main_tp = tok
                continue
            assign_tp(tok)
            tps.append(tok)
            anaphoric.append(tok)
            continue
        # ---- 时点（相对/时令/回指/未知） ----
        # 追叙信号 → fork（仅非对白叙述；§4.2）
        if not tok.dialogic and FORK_SIGNAL_RE.search(tok.display):
            fid = f"{work_id}-F{len(forks) + 1:03d}"
            base = last_main_tp
            forks.append(Fork(
                fork_id=fid, fork_type="追叙",
                base_tp_id=base.tp_id if base else "",
                offset_value=(tok.offset_days or 0) / 365.0 if tok.offset_days is not None else 0.0,
                offset_unit="年" if (tok.offset_days or 0) and abs(tok.offset_days or 0) >= 30 else "日",
                event_tp_ids=[tok.tp_id], reinsert_anchor={"chapter": tok.chapter, "pn": tok.pn},
                confidence="low", basis="追叙信号词建 fork（§4.2 叉型=追叙；隔离主轨）"))
            tok.fork_id = fid
            tok.status = "fork"
            tok.t_days = (cur_t + (tok.offset_days or 0)) if cur_t is not None else None
            tok.basis += "；fork 隔离（§4.2）"
            assign_tp(tok)
            tps.append(tok)
            continue
        # 对白内时间：隔离，不推进主轨（§4.3 叙述模式；§4.4 回指/计划不新建）
        if tok.dialogic:
            tok.status = "dialogic"
            if tok.display in ANAPHORIC and last_main_tp is not None:
                tok.anchor_ref = last_main_tp.tp_id
                tok.t_days = last_main_tp.t_days
                tok.basis += "；对白回指主轨时点（不推进）"
            elif tok.offset_days is not None and cur_t is not None:
                tok.t_days = cur_t + tok.offset_days
                tok.basis += "；对白内相对时间（仅参照，不推进主轨）"
            assign_tp(tok)
            tps.append(tok)
            dialogic.append(tok)
            continue
        # 年转/回指（去年/明年/前年…）：参照型，不推进主轨、不参与单调（§4.4 回指不新建）
        if tok.display in YEAR_SHIFT and YEAR_SHIFT[tok.display] != 0:
            tok.status = "anaphoric"
            if cur_t is not None:
                tok.t_days = cur_t + YEAR_SHIFT[tok.display] * 365.0
                tok.basis += "；年转参照（隔离主轨，不参与单调，§4.4）"
            assign_tp(tok)
            tps.append(tok)
            anaphoric.append(tok)
            continue
        # 非对白主轨
        if tok.anchor_type == "未知":
            tok.status = "unresolved"
            if not tok.unknown_reason:
                tok.unknown_reason = "原文未给/词形不在锚点表"
            if tok.confidence == "low":
                tok.flags.append("T12")
            assign_tp(tok)
            tps.append(tok)
            unresolved.append(tok)
            continue
        # 计算 t
        t = cur_t
        if tok.offset_days is not None and cur_t is not None:
            t = cur_t + tok.offset_days
        elif tok.granularity in ("季月级", "日级") and tok.offset_days is not None and cur_year is not None:
            t = (cur_year - origin_year) * 365.0 + tok.offset_days
        elif tok.display in ANAPHORIC and last_main_tp is not None:
            t = last_main_tp.t_days
            tok.anchor_ref = last_main_tp.tp_id
        # §2.6 纯相对书：首个主轨时点 → t=0 原点（仅排序）
        if t is None and allow_pseudo_origin and tok.anchor_type != "未知" and not tok.dialogic:
            t = 0.0
            tok.basis += "；纯相对书：首个主轨时点为 t=0 原点（§2.6，仅书内排序，不换算公历）"
            tok.flags.append("纯相对原点")
        tok.t_days = t
        if t is None:
            tok.status = "unresolved"
            if not tok.unknown_reason:
                tok.unknown_reason = "主轨尚无锚点，无法定位（§8.4 未知原则）"
            assign_tp(tok)
            tps.append(tok)
            unresolved.append(tok)
            continue
        # 相对偏移为负（N年前/N日前）→ fork 隔离（§4.2：前向词触发分叉而非倒流）
        if tok.offset_days is not None and tok.offset_days < 0:
            fid = f"{work_id}-F{len(forks) + 1:03d}"
            forks.append(Fork(
                fork_id=fid, fork_type="追叙",
                base_tp_id=last_main_tp.tp_id if last_main_tp else "",
                offset_value=tok.offset_days, offset_unit="日",
                event_tp_ids=[tok.tp_id], reinsert_anchor={"chapter": tok.chapter, "pn": tok.pn},
                confidence="low", basis="前向偏移词（N年前/N日前）建 fork，不参与主轨单调（§4.2/§4.4）"))
            tok.fork_id = fid
            tok.status = "fork"
            assign_tp(tok)
            tps.append(tok)
            continue
        # 正向推进
        ok_advance = tok.granularity != "日内级"
        tok.status = "mainline"
        assign_tp(tok)
        tps.append(tok)
        mainline.append(tok)
        if last_main_tp is not None and t is not None and last_main_tp.t_days is not None \
                and t > last_main_tp.t_days:
            cur_t = t
        elif cur_t is None:
            cur_t = t
        elif t is not None and t > cur_t:
            cur_t = t
        last_main_tp = tok
        if tok.year_ce is not None:
            cur_year = tok.year_ce

    # 后补：主轨锚点前/后的相对时点，用最近主轨时点回填（§2.3 锚点+偏移；置信降档）
    main_ts = [t for t in mainline if t.t_days is not None]
    for tok in tps:
        if tok.status == "unresolved" and tok.offset_days is not None and main_ts:
            cand = None
            for x in main_ts:
                if (x.chapter, x.pn) < (tok.chapter, tok.pn):
                    cand = x
            if cand is None:
                # 叙述首锚之前的相对时点：用首个后续主轨锚点"前推"回填（low，仅排序用）
                if tok.anchor_type != "事件锚":
                    continue
                after = min(main_ts, key=lambda x: (abs(x.chapter - tok.chapter), abs(x.pn - tok.pn)))
                tok.t_days = after.t_days + tok.offset_days
                tok.status = "mainline"
                tok.confidence = "low"
                tok.basis += "；叙述首锚前回填（前推，low，仅排序用，§2.3/§8.1）"
                mainline.append(tok)
                continue
            tok.t_days = cand.t_days + tok.offset_days
            tok.status = "mainline"
            tok.confidence = "medium" if tok.confidence != "low" else "low"
            tok.basis += "；锚点后补（叙述序最近主轨时点+偏移，§2.3）"
            mainline.append(tok)

    # 回填后按 status 重建各集合（stats 不引用过期列表）
    mainline = [t for t in tps if t.status == "mainline"]
    dialogic = [t for t in tps if t.status == "dialogic"]
    background = [t for t in tps if t.status == "background"]
    unresolved = [t for t in tps if t.status == "unresolved"]

    # 单调性（§4.1）
    violations = []
    prev = None
    for tok in sorted(mainline, key=lambda x: (x.chapter, x.pn, x.raw_start)):
        if tok.t_days is None:
            continue
        if prev is not None and prev.t_days is not None:
            delta = tok.t_days - prev.t_days
            if delta < -1e-6:
                if tok.year_ce is not None and abs(delta) > 365:
                    # §2.5 规则5：朝代锚与相对链冲突已登记 T15，不重复报 E1
                    prev = tok
                    continue
                if tok.precision == "约略" or prev.precision == "约略":
                    level = "E2"
                else:
                    level = "E1"
                violations.append({
                    "level": level, "prev": prev.tp_id, "next": tok.tp_id,
                    "prev_location": f"{prev.chapter:03d}[{prev.pn}]", "next_location": f"{tok.chapter:03d}[{tok.pn}]",
                    "delta_days": round(delta, 2), "prev_display": prev.display, "next_display": tok.display,
                    "note": "同线硬倒流" if level == "E1" else "一方约略的疑似倒流",
                })
        prev = tok
    # 分叉内倒流只登记（E4）
    for f in forks:
        for tid in f.event_tp_ids:
            tp = next((x for x in tps if x.tp_id == tid), None)
            if tp is not None and tp.t_days is not None:
                violations.append({"level": "E4", "prev": f.base_tp_id, "next": tid,
                                   "prev_location": "", "next_location": f"{tp.chapter:03d}[{tp.pn}]",
                                   "delta_days": None, "prev_display": "", "next_display": tp.display,
                                   "note": f"分叉 {f.fork_id} 内时点（合法，仅登记）"})

    # 检查项（T01-T15；§6/§7）
    errors = list(anchor_conflict_events)
    # T01 单锚点塌缩（§6.2 例1）：同回 ≥K=3 个"推算年"事件共享同一年，且该回直录锚 ≤1
    by_ch = {}
    for tok in mainline:
        by_ch.setdefault(tok.chapter, []).append(tok)
    for ch, toks in by_ch.items():
        direct_years = {t.year_ce for t in toks if t.year_ce is not None and t.confidence == "high"}
        inferred = [t for t in toks if t.t_days is not None and t.year_ce is None
                    and t.offset_days is None and t.granularity in ("年级", "纪元级")
                    and t.confidence != "high"]
        buckets = {}
        for t in inferred:
            if origin_year is None:
                continue
            yr = int(origin_year + t.t_days // 365)
            buckets.setdefault(yr, []).append(t)
        for yr, group in buckets.items():
            if len(group) >= 3 and len(direct_years) <= 1:
                errors.append({"code": "T01", "level": "warning", "chapter": ch,
                               "message": f"同回 {len(group)} 个推算事件共享 {yr} 年（疑似单锚点塌缩，"
                                          f"直录锚={sorted(direct_years) or '无'}）",
                               "tp_ids": [x.tp_id for x in group][:10],
                               "cite": "§6.2 例1（K=3，待试点校准）"})
    # T03 重复标注：同段紧邻两次同文（模式28/34）
    last_tok: dict[tuple[int, int], TimeToken] = {}
    for tok in tokens:
        prev = last_tok.get((tok.chapter, tok.pn))
        if prev is not None and prev.display == tok.display and \
                tok.raw_start - prev.raw_start <= len(tok.display) + 6:
            errors.append({"code": "T03", "level": "info", "chapter": tok.chapter,
                           "message": f"同段紧邻重复时间标注：{tok.display}",
                           "tp_ids": [prev.tp_id, tok.tp_id], "cite": "模式28/34"})
        last_tok[(tok.chapter, tok.pn)] = tok
    # T05 裸时点缺管 / T06 管道误用
    for tok in tokens:
        if not tok.pipe and tok.ttype == "时点":
            errors.append({"code": "T05", "level": "warning", "chapter": tok.chapter,
                           "message": f"裸 % 时点缺 |时点| 管道：{tok.display}",
                           "tp_ids": [tok.tp_id], "cite": "§7.1/模式26"})
        if tok.pipe == "时长" and tok.ttype == "时点":
            errors.append({"code": "T06", "level": "warning", "chapter": tok.chapter,
                           "message": f"时点语义却挂 |时长| 管道：{tok.display}",
                           "tp_ids": [tok.tp_id], "cite": "§7.3"})
        if tok.pipe == "时点" and tok.ttype == "时长":
            errors.append({"code": "T06", "level": "warning", "chapter": tok.chapter,
                           "message": f"时长语义却挂 |时点| 管道：{tok.display}",
                           "tp_ids": [tok.tp_id], "cite": "§7.3"})
        if "T07" in tok.flags:
            errors.append({"code": "T07", "level": "warning", "chapter": tok.chapter,
                           "message": f"谚语/虚指时间（W6）：{tok.display}",
                           "tp_ids": [tok.tp_id], "cite": "§6.3 W6"})
    # T02 追叙未建 fork（非对白、有追叙信号但仍在主线）
    for tok in mainline:
        if FORK_SIGNAL_RE.search(tok.display) and not tok.fork_id:
            errors.append({"code": "T02", "level": "warning", "chapter": tok.chapter,
                           "message": f"追叙信号未隔离：{tok.display}",
                           "tp_ids": [tok.tp_id], "cite": "§4.2/错误5"})
    # T11 同段多锚点年份冲突
    by_para = {}
    for tok in tps:
        if tok.year_ce is not None:
            by_para.setdefault((tok.chapter, tok.pn), []).append(tok)
    for key, group in by_para.items():
        years = sorted({x.year_ce for x in group})
        if len(years) > 1 and years[-1] - years[0] > 2:
            errors.append({"code": "T11", "level": "warning", "chapter": key[0],
                           "message": f"同段多锚点年份冲突 {years}：双值并存登记，不静默取一",
                           "tp_ids": [x.tp_id for x in group], "cite": "§3.3 锚点冲突"})
    # T12 low 缺原因
    for tok in tokens:
        if tok.confidence == "low" and not tok.unknown_reason and tok.status in ("unresolved", "background"):
            errors.append({"code": "T12", "level": "info", "chapter": tok.chapter,
                           "message": f"low 置信缺未确定原因：{tok.display}",
                           "tp_ids": [tok.tp_id], "cite": "§8.3"})
    # 统计
    stats = build_stats(index, tokens, tps, mainline, dialogic, anaphoric, background,
                        unresolved, forks, violations, errors, chapters)
    discipleship = build_discipleship_estimates(tps)
    return {
        "schema": "wuxia-time-resolve-v1",
        "book": book,
        "work_id": work_id,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tool": TOOL_VERSION,
        "spec": {
            "skill": "skills/SKILL_时间体系_武侠版.md",
            "sections": ["§二 时点键双层结构", "§三 四类锚点与置信排序", "§四 单调性/分叉/隔离",
                         "§五 定年方法（M1-M7/师承代数）", "§六 43 错误模式三分裁决 + W1-W6",
                         "§七 % 三管道", "§八 confidence 三档"],
            "task": "docs/17 §2.3 / docs/50 §三（N4/D05）",
        },
        "inputs": {
            "tagged_dir": str(index.dir.relative_to(ROOT)) if index.dir.is_relative_to(ROOT) else str(index.dir),
            "chapters": index.chapters if chapters is None else sorted(chapters),
            "struct_parity": {"ok": index.struct_parity_ok, "bad": index.struct_parity_bad[:20],
                              "bad_count": len(index.struct_parity_bad)},
            "warnings": index.warnings,
        },
        "book_anchors": [{
            "tp_id": t.tp_id, "chapter": t.chapter, "pn": t.pn, "display": t.display,
            "year_ce": t.year_ce, "year_range": t.year_range, "basis": t.basis, "confidence": t.confidence,
        } for t in tps if t.anchor_type == "朝代锚"][:200],
        "time_points": [serialize_tp(t) for t in tps],
        "forks": [f.__dict__ for f in forks],
        "discipleship_estimates": discipleship,
        "monotonicity": {
            "mainline_tp": len(mainline),
            "violations": violations,
            "by_level": {lv: sum(1 for v in violations if v["level"] == lv) for lv in ("E1", "E2", "E4")},
        },
        "errors": errors,
        "error_index": {code: [e for e in errors if e["code"] == code] for code in CHECK_RULES},
        "error_mode_coverage": [{"id": a, "name": b, "verdict": c, "implemented": d}
                                for a, b, c, d in ERROR_MODE_TABLE],
        "stats": stats,
    }


def build_discipleship_estimates(tps) -> list[dict]:
    """师承代数定年佐证（§5.2/§5.3，M6）：时长词＋师承/闭关语境 → 当量区间与跨度区间。

    规则（§5.2）：一条传承边当量 1-2 代；跨度 = 当量 × 25–30 年；
    误差（§5.3）：E 当量链区间 = [25E−10, 30E+10] 年；封顶 low，仅排序佐证，不单独定编年。
    """
    out = []
    for t in tps:
        if t.ttype != "时长" or not t.duration_days:
            continue
        if not re.search(r"(拜师|收徒|传功|授艺|学艺|门下|弟子|出师|闭关)", t.context):
            continue
        years = t.duration_days / 365.0
        e_cands = [E for E in (1, 2, 3, 4)
                   if (25 * E - 10) <= years <= (30 * E + 10)]
        out.append({
            "tp_id": t.tp_id, "location": f"{t.chapter:03d}[{t.pn}]",
            "time_raw": t.raw, "display": t.display, "duration_days": round(t.duration_days, 1),
            "duration_years": round(years, 2),
            "equivalence_candidates": e_cands,
            "span_years_range": [round(years - (years * 0.2), 1), round(years + (years * 0.2), 1)],
            "confidence": "low",
            "basis": "M6 师承代数定年（§5.2）：时长仅是上下文证据，当量=1-2 代、跨度=当量×25-30 年；"
                     "E 条链区间=[25E−10,30E+10]（§5.3），封顶 low，仅作排序佐证",
            "spec_cases": "§5.4 校准演示（白发→晦明→七剑当量 2 代≈59 年）",
        })
    return out


def serialize_tp(t: TimeToken) -> dict:
    return {
        "tp_id": t.tp_id,
        "anchor": {"work_id": t.book, "chapter": t.chapter, "pn": t.pn,
                   "segment_anchor": f"{BOOK_IDS.get(t.book, 'book')}#pn-r{t.chapter}.{t.pn}",
                   "line_no": t.line_no, "span_in_line": [t.raw_start, t.raw_end]},
        "time_raw": t.raw,
        "display": t.display,
        "pipe": t.pipe,
        "time_type": t.ttype,
        "granularity": t.granularity,
        "anchor_type": t.anchor_type,
        "anchor_ref": t.anchor_ref,
        "offset": ({"value": round(t.offset_days, 3), "unit": "日"} if t.offset_days is not None else None),
        "t_days": round(t.t_days, 3) if t.t_days is not None else None,
        "year_ce": t.year_ce,
        "year_range": t.year_range,
        "age": t.age,
        "duration_days": round(t.duration_days, 3) if t.duration_days is not None else None,
        "precision": t.precision,
        "confidence": t.confidence,
        "calendar": "史历换算" if t.year_ce is not None else "书内相对",
        "narrative_line": ("L0-主线" if t.status == "mainline" else
                           (f"F-{t.fork_id}" if t.fork_id else "L0-参照")),
        "narrative_mode": ("韵文围栏" if t.status == "fence" else
                           ("对白" if t.status == "dialogic" else "正常叙事")),
        "fork_id": t.fork_id or None,
        "simultaneous_to": t.simultaneous_to or None,
        "status": t.status,
        "precision_basis": t.basis,
        "unknown_reason": t.unknown_reason or None,
        "flags": t.flags,
        "context": t.context,
    }


def build_stats(index: BookIndex, tokens, tps, mainline, dialogic, anaphoric, background,
                unresolved, forks, violations, errors, chapters) -> dict:
    from collections import Counter
    by_type = Counter(t.ttype for t in tps)
    by_pipe = Counter(t.pipe or "(裸%)" for t in tps)
    by_gran = Counter(t.granularity for t in tps)
    by_anchor = Counter(t.anchor_type for t in tps)
    by_conf = Counter(t.confidence for t in tps)
    by_status = Counter(t.status for t in tps)
    positioned = sum(1 for t in tps if t.t_days is not None)
    tp_tokens = [t for t in tps if t.ttype == "时点"]
    positioned_tp = sum(1 for t in tp_tokens if t.t_days is not None)
    resolved = sum(1 for t in tps if t.anchor_type != "未知" or t.duration_days is not None
                   or t.age is not None or t.year_ce is not None or t.year_range is not None)
    total = len(tps)
    year_vals = [t.year_ce for t in tps if t.year_ce is not None]
    return {
        "chapters_scanned": len(chapters or index.chapters),
        "time_tokens": total,
        "time_point_tokens": len(tp_tokens),
        "by_type": dict(by_type),
        "by_pipe": dict(by_pipe),
        "by_granularity": dict(by_gran),
        "by_anchor_type": dict(by_anchor),
        "by_confidence": {k: by_conf.get(k, 0) for k in ("high", "medium", "low")},
        "by_status": dict(by_status),
        "resolved": resolved,
        "resolved_rate": round(resolved / total, 4) if total else 0.0,
        "positioned": positioned,
        "positioned_rate": round(positioned / total, 4) if total else 0.0,
        "positioned_time_points": positioned_tp,
        "positioned_rate_time_points": round(positioned_tp / len(tp_tokens), 4) if tp_tokens else 0.0,
        "mainline_tokens": len(mainline),
        "dialogic_tokens": len(dialogic),
        "fork_count": len(forks),
        "fork_tokens": len(forks),
        "background_tokens": len(background),
        "unresolved_tokens": len(unresolved),
        "monotonic_violations": {k: sum(1 for v in violations if v["level"] == k)
                                 for k in ("E1", "E2", "E4")},
        "error_counts": dict(__import__("collections").Counter(e["code"] for e in errors)),
        "year_ce_min": min(year_vals) if year_vals else None,
        "year_ce_max": max(year_vals) if year_vals else None,
        "top_unresolved": [{"display": t.display, "location": f"{t.chapter:03d}[{t.pn}]",
                            "context": t.context[:80]}
                           for t in unresolved[:10]],
    }


def analyze_book(book: str, chapters: list[int] | None = None) -> dict:
    return resolve_book(book, chapters)


# ────────────────────────────── 报告渲染 ──────────────────────────────
def _esc(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ") if s is not None else ""


def render_book_md(result: dict) -> str:
    st = result["stats"]
    lines = []
    add = lines.append
    add(f"# N4 时间轴解析报告 · 《{result['book']}》")
    add("")
    add(f"- 生成时间：{result['generated_at']}；工具：`scripts/time_resolver_wuxia.py`（{result['tool']}）")
    add(f"- 规范：`{result['spec']['skill']}`（§二 时点键/§三 四类锚点/§四 单调性与分叉/§五 定年/"
        "§六 43 错误模式/§七 三管道/§八 confidence）；任务：docs/17 §2.3 / docs/50 §三")
    add(f"- 输入：`{result['inputs']['tagged_dir']}`（回 {st['chapters_scanned']} 回）；"
        f"struct 逐段剥标对账 ok={result['inputs']['struct_parity']['ok']} "
        f"bad={result['inputs']['struct_parity']['bad_count']}")
    add("- 输出：`registry/time/" + f"{result['book']}.json`（全量 time_points）· 本报告")
    add("")
    add("## 一、总览")
    add("")
    add(f"- 时间令牌 **{st['time_tokens']}**；解析率（锚点/数值已解析）**{st['resolved']} "
        f"({st['resolved_rate']:.1%})**；可定位 t 率 **{st['positioned']} ({st['positioned_rate']:.1%})**")
    add(f"- 时点令牌 {st['time_point_tokens']}：t 定位 {st['positioned_time_points']} "
        f"({st['positioned_rate_time_points']:.1%})；时长/年龄为非时点记录（不入主轨）")
    add(f"- 主轨 {st['mainline_tokens']} · 对白隔离 {st['dialogic_tokens']} · 分叉 {st['fork_tokens']} · "
        f"年龄/时长参照 {st['by_status'].get('age', 0) + st['by_status'].get('duration', 0)} · "
        f"背景 {st['background_tokens']} · 未解析 {st['unresolved_tokens']}")
    if st["year_ce_min"]:
        add(f"- 主轨可换算年份跨度：{st['year_ce_min']}–{st['year_ce_max']}（仅换算辅助，不覆盖书内相对序）")
    add(f"- 单调性违例：E1={st['monotonic_violations']['E1']} · E2={st['monotonic_violations']['E2']} · "
        f"E4={st['monotonic_violations']['E4']}（分叉内，合法）")
    add(f"- 错误清单：{', '.join(f'{k}×{v}' for k, v in sorted(st['error_counts'].items())) or '（无）'}")
    add("")
    add("## 二、分布（§二/§三/§八 三档）")
    add("")
    add("| 维度 | 分布 |")
    add("|---|---|")
    add(f"| 管道 | {_esc(st['by_pipe'])} |")
    add(f"| 时间类型 | {_esc(st['by_type'])} |")
    add(f"| 粒度五级 | {_esc(st['by_granularity'])} |")
    add(f"| 锚点类型 | {_esc(st['by_anchor_type'])} |")
    add(f"| confidence | {_esc(st['by_confidence'])} |")
    add(f"| 状态 | {_esc(st['by_status'])} |")
    add("")
    add("## 三、朝代锚清单（M1 直录；§2.5 换算只作显示辅助）")
    add("")
    anchors = result["book_anchors"]
    if anchors:
        add("| tp_id | 回[段] | 原文 | 公历年/区间 | 依据 | 置信 |")
        add("|---|---|---|---|---|---|")
        for a in anchors[:80]:
            yr = a["year_ce"] if a["year_ce"] is not None else (
                f"{a['year_range'][0]}–{a['year_range'][1]}" if a["year_range"] else "—")
            add(f"| {a['tp_id']} | {a['chapter']:03d}[{a['pn']}] | {_esc(a['display'])} | {yr} | "
                f"{_esc(a['basis'])} | {a['confidence']} |")
        if len(anchors) > 80:
            add(f"\n（仅列前 80 条，共 {len(anchors)} 条；全量见 JSON）")
    else:
        add("（无朝代锚：按 §2.6 纯相对纪律，不猜朝代/年份）")
    add("")
    add("## 四、单调性校验（§4.1）")
    add("")
    vs = result["monotonicity"]["violations"]
    if vs:
        add("| 级别 | 前项 | 后项 | Δ(日) | 说明 |")
        add("|---|---|---|---:|---|")
        for v in vs[:60]:
            add(f"| {v['level']} | {v['prev_location']} {_esc(v['prev_display'])} | "
                f"{v['next_location']} {_esc(v['next_display'])} | {v['delta_days'] if v['delta_days'] is not None else '—'} | "
                f"{_esc(v['note'])} |")
    else:
        add("（主轨单调不减，无 E1/E2；分叉内倒流按 E4 收藏）")
    add("")
    add("## 五、分叉/闪回登记（§4.2）")
    add("")
    forks = result["forks"]
    if forks:
        add("| fork_id | 叉型 | 基点 | 偏移 | 回插段锚 | 置信 |")
        add("|---|---|---|---|---|---|")
        for f in forks[:80]:
            add(f"| {f['fork_id']} | {f['fork_type']} | {f['base_tp_id'] or '—'} | "
                f"{f['offset_value']:g}{f['offset_unit']} | "
                f"{f['reinsert_anchor'].get('chapter')}[{f['reinsert_anchor'].get('pn')}] | {f['confidence']} |")
        if len(forks) > 80:
            add(f"\n（仅列前 80 条，共 {len(forks)} 条）")
    else:
        add("（无追叙/闪回分叉）")
    add("")
    add("**师承代数定年佐证（§5.2/§5.3，M6，封顶 low，仅排序佐证）**")
    add("")
    disc = result.get("discipleship_estimates") or []
    if disc:
        add("| tp_id | 回[段] | 原文 | 时长(年) | 当量候选(E) | 置信 | 依据 |")
        add("|---|---|---|---:|---|---|---|")
        for d in disc[:40]:
            add(f"| {d['tp_id']} | {d['location']} | {_esc(d['display'])} | {d['duration_years']} | "
                f"{d['equivalence_candidates']} | {d['confidence']} | {_esc(d['basis'])} |")
        if len(disc) > 40:
            add(f"\n（仅列前 40 条，共 {len(disc)} 条；全量见 JSON）")
    else:
        add("（无师承/闭关语境时长，未产生 M6 佐证）")
    add("")
    w1 = sum(1 for t in result["time_points"] if "T09" in (t.get("flags") or []))
    w5 = sum(1 for t in result["time_points"] if "T10" in (t.get("flags") or []))
    add(f"- W1 闭关/学艺跳变候选：{w1} 条（§6.3 W1）；W5 周期时长候选：{w5} 条（§6.3 W5）")
    add("")
    add("## 六、错误清单（T/E 系列；规则见 `CHECK_RULES`）")
    add("")
    if result["errors"]:
        add("| 代码 | 级别 | 回 | 说明 | tp_ids | 依据 |")
        add("|---|---|---:|---|---|---|")
        for e in result["errors"][:80]:
            add(f"| {e['code']} | {e['level']} | {e.get('chapter', '')} | {_esc(e['message'])} | "
                f"{_esc(', '.join(e.get('tp_ids', [])[:4]))} | {_esc(e.get('cite', ''))} |")
        if len(result["errors"]) > 80:
            add(f"\n（仅列前 80 条，共 {len(result['errors'])} 条）")
    else:
        add("（无）")
    add("")
    add("## 七、未解析/低置信抽样（§8.4 未知原则：不补默认值）")
    add("")
    tops = st["top_unresolved"]
    if tops:
        add("| 回[段] | display | 上下文 |")
        add("|---|---|---|")
        for t in tops:
            add(f"| {t['location']} | {_esc(t['display'])} | {_esc(t['context'])} |")
    else:
        add("（无）")
    add("")
    add("## 八、43 错误模式覆盖（§6.1 三分裁决；本工具机械化子集）")
    add("")
    auto = [m for m in result["error_mode_coverage"] if m["implemented"].startswith("auto")]
    add(f"- 43 条逐条裁决已录入工具（`ERROR_MODE_TABLE`）；本工具**自动覆盖 "
        f"{len(auto)} 条**，其余为人工/后续节点（N5/N8）责任，报告逐条可查。")
    add("- 自动覆盖：" + "、".join(f"{m['id']}{m['name']}（{m['implemented']}）" for m in auto[:20]) +
        ("……" if len(auto) > 20 else ""))
    add("")
    add("## 九、复现")
    add("")
    add("```powershell")
    add(f"python -X utf8 scripts/time_resolver_wuxia.py --book {result['book']}")
    add(f"python -X utf8 scripts/time_resolver_wuxia.py --book {result['book']} --chapter 1-5")
    add(f"python -X utf8 scripts/time_resolver_wuxia.py --book {result['book']} --report logs/time/custom.md")
    add("```")
    add("")
    return "\n".join(lines) + "\n"


def render_summary_md(results: list[dict]) -> str:
    lines = []
    add = lines.append
    add("# N4 时间轴解析 · 5 书汇总（time_resolver_wuxia）")
    add("")
    add(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；工具：{TOOL_VERSION}")
    add("- 规范：`skills/SKILL_时间体系_武侠版.md`（§二–§八）；只读 tagged/struct，写 "
        "`registry/time/` + `logs/time/`")
    add("")
    add("## 一、5 书总览")
    add("")
    add("| 书 | 时间令牌 | 解析率 | 时点定位率 | 主轨 | 对白隔离 | 分叉 | 未解析 | E1 | E2 | "
        "朝代锚 | 高/中/低 |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    tot = {"tokens": 0, "resolved": 0, "positioned": 0, "tp": 0, "tp_pos": 0,
           "mainline": 0, "dialogic": 0, "forks": 0, "unresolved": 0, "E1": 0, "E2": 0}
    for r in results:
        st = r["stats"]
        add(f"| {r['book']} | {st['time_tokens']} | {st['resolved_rate']:.1%} | "
            f"{st['positioned_rate_time_points']:.1%} | {st['mainline_tokens']} | {st['dialogic_tokens']} | "
            f"{st['fork_count']} | {st['unresolved_tokens']} | {st['monotonic_violations']['E1']} | "
            f"{st['monotonic_violations']['E2']} | {st['by_anchor_type'].get('朝代锚', 0)} | "
            f"{st['by_confidence'].get('high', 0)}/{st['by_confidence'].get('medium', 0)}/"
            f"{st['by_confidence'].get('low', 0)} |")
        for k, key in (("tokens", "time_tokens"), ("resolved", "resolved"),
                       ("positioned", "positioned"), ("tp", "time_point_tokens"),
                       ("tp_pos", "positioned_time_points"), ("mainline", "mainline_tokens"),
                       ("dialogic", "dialogic_tokens"), ("forks", "fork_count"),
                       ("unresolved", "unresolved_tokens")):
            tot[k] += st[key]
        tot["E1"] += st["monotonic_violations"]["E1"]
        tot["E2"] += st["monotonic_violations"]["E2"]
    add(f"| **合计** | **{tot['tokens']}** | {tot['resolved'] / tot['tokens']:.1%} | "
        f"{tot['tp_pos'] / tot['tp']:.1%} | **{tot['mainline']}** | **{tot['dialogic']}** | "
        f"**{tot['forks']}** | **{tot['unresolved']}** | **{tot['E1']}** | **{tot['E2']}** | — | — |")
    add("")
    add("## 二、锚点分布与错误分类（§三/§六；闪回候选=分叉数）")
    add("")
    add("| 书 | 朝代锚 | 事件锚 | 人物年龄锚 | 时令锚 | 非锚点·时长 | 未知类 | 错误分类（T/E） |")
    add("|---|---:|---:|---:|---:|---:|---:|---|")
    for r in results:
        st = r["stats"]
        bt = st["by_anchor_type"]
        errs = "、".join(f"{k}×{v}" for k, v in sorted(st["error_counts"].items())) or "（无）"
        add(f"| {r['book']} | {bt.get('朝代锚', 0)} | {bt.get('事件锚', 0)} | "
            f"{bt.get('人物年龄锚', 0)} | {bt.get('时令锚', 0)} | "
            f"{bt.get('非锚点·时长', 0)} | {bt.get('未知', 0)} | {_esc(errs)} |")
    add("")
    add("> 解析率 = 已完成锚点/数值解析的令牌占比（时长/年龄的数值解析计入）；"
        "时点定位率 = 时点令牌中可给出书内相对刻度 t 的比例（不含时长/年龄，二者不产生时点）。")
    add("")
    add("## 三、口径摘要")
    add("")
    add("- **时点键**：物理段锚 `{work_id}#pn-r{回}.{段}` + 逻辑 `tp_id`（§2.1）；"
        "`t_days` 为书内相对刻度（单位日，年首日口径；§2.1）。")
    add("- **锚点分级**（§3.2）：朝代锚 high（M1 直录；年号/干支/帝王区间换算）→ 事件锚（明确偏移 medium）"
        "→ 年龄锚 medium → 事件锚弱 low → 时令锚 low；跨书/师承只作 low 佐证。")
    add("- **置信三档**（§8.1）：high=书内明确陈述；medium=锚点+偏移/多信号一致；low=区间宽/推算/跨书。")
    add("- **隔离**：对白内时间不推进主轨（§4.3/§4.4）；围栏诗/词/回末评点不入故事时间轨（错误6）；"
        "追叙（N年前/当年）建 fork 并隔离（§4.2）；「回指」指向首叙时点不新建（§4.4）。")
    add("- **未知原则**（§8.4）：不补公历默认年、不借同名人物挂年、跳变期间不拆事件；"
        "未解析项显式留 `unknown_reason`。")
    add("- **43 错误模式**（§6.1）逐条录入 `ERROR_MODE_TABLE`（直迁 10/改写 33/报废 0）；"
        "本工具机械化覆盖其中 auto 子集（T01-T15 见 `CHECK_RULES`），其余为人工/后续 N5/N8 责任，"
        "逐书报告 §八 可查。")
    add("")
    add("## 四、产物")
    add("")
    for r in results:
        add(f"- 《{r['book']}》：`registry/time/{r['book']}.json` · `logs/time/{r['book']}.md`")
    add("- 汇总：`logs/time/time_resolve_summary.md` · `logs/time/time_resolve_summary.json`")
    add("")
    add("## 五、复现")
    add("")
    add("```powershell")
    add("python -X utf8 scripts/time_resolver_wuxia.py --selftest     # 单元断言")
    add("python -X utf8 scripts/time_resolver_wuxia.py --all          # 5 书 + 汇总")
    add("python -X utf8 scripts/pipeline_wuxia.py 江湖三女侠 time-resolve   # 管线阶段（可选）")
    add("```")
    add("")
    return "\n".join(lines) + "\n"


# ────────────────────────────── CLI / 运行 ──────────────────────────────
def parse_chapters(spec: str) -> list[int]:
    out = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return sorted(out)


def _rel(p: Path) -> str:
    """路径 → 相对 ROOT 的展示串（ROOT 外保留绝对路径）。"""
    p = Path(p).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def run_books(books: list[str], chapters: list[int] | None, out_dir: Path,
              report_path: Path | None, quiet: bool = False) -> list[dict]:
    out_dir = Path(out_dir).resolve()
    report_path = Path(report_path).resolve() if report_path else None
    REGISTRY_TIME_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_TIME_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for book in books:
        try:
            result = analyze_book(book, chapters)
        except Exception as exc:  # noqa: BLE001 - 逐书失败不阻塞
            print(f"[ERROR] {book}: {exc}", file=sys.stderr)
            continue
        jp = (out_dir / f"{book}.json").resolve()
        jp.parent.mkdir(parents=True, exist_ok=True)
        io.open(jp, "w", encoding="utf-8").write(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        mp = (report_path if (report_path and len(books) == 1)
              else (LOGS_TIME_DIR / f"{book}.md").resolve())
        mp.parent.mkdir(parents=True, exist_ok=True)
        io.open(mp, "w", encoding="utf-8").write(render_book_md(result))
        result["_files"] = {"json": _rel(jp), "md": _rel(mp)}
        results.append(result)
        st = result["stats"]
        if not quiet:
            print(f"[OK] {book}: {st['time_tokens']} token → 解析 {st['resolved_rate']:.1%} / "
                  f"定位 {st['positioned_rate']:.1%} · 主轨 {st['mainline_tokens']} · 分叉 "
                  f"{st['fork_tokens']} · E1/E2={st['monotonic_violations']['E1']}/"
                  f"{st['monotonic_violations']['E2']} → {result['_files']['json']}")
    if len(results) > 1:
        sm = LOGS_TIME_DIR / "time_resolve_summary.md"
        sj = LOGS_TIME_DIR / "time_resolve_summary.json"
        io.open(sm, "w", encoding="utf-8").write(render_summary_md(results))
        summary = {
            "tool": TOOL_VERSION, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "books": [r["book"] for r in results],
            "totals": {
                "time_tokens": sum(r["stats"]["time_tokens"] for r in results),
                "resolved": sum(r["stats"]["resolved"] for r in results),
                "positioned": sum(r["stats"]["positioned"] for r in results),
                "mainline": sum(r["stats"]["mainline_tokens"] for r in results),
                "dialogic": sum(r["stats"]["dialogic_tokens"] for r in results),
                "forks": sum(r["stats"]["fork_tokens"] for r in results),
                "unresolved": sum(r["stats"]["unresolved_tokens"] for r in results),
                "E1": sum(r["stats"]["monotonic_violations"]["E1"] for r in results),
                "E2": sum(r["stats"]["monotonic_violations"]["E2"] for r in results),
            },
            "book_stats": [{"book": r["book"], "stats": r["stats"],
                            "monotonicity": {"by_level": r["monotonicity"]["by_level"]},
                            "files": r["_files"]} for r in results],
        }
        io.open(sj, "w", encoding="utf-8").write(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        if not quiet:
            print(f"[OK] 汇总 → {sm.relative_to(ROOT)} · {sj.relative_to(ROOT)}")
    return results


# ────────────────────────────── selftest ──────────────────────────────
def run_selftest() -> int:
    """--selftest：解析/分类/单调性/分叉隔离的单元断言（无外部依赖）。"""
    checks = []

    def chk(name, cond):
        checks.append((name, bool(cond)))
        if not cond:
            print(f"[FAIL] {name}")

    chk("cn_num 十八=18", cn_num("十八") == 18)
    chk("cn_num 廿一=21", cn_num("廿一") == 21)
    chk("cn_num 四十=40", cn_num("四十") == 40)
    chk("cn_num 一百四十八=148", cn_num("一百四十八") == 148)
    chk("年号 明万历四十三年=1615", (parse_era_anchor("明万历四十三年") or {}).get("year") == 1615)
    chk("年号 康熙十三年=1674", (parse_era_anchor("康熙十三年") or {}).get("year") == 1674)
    chk("年号 康熙四十五年=1706", (parse_era_anchor("康熙四十五年") or {}).get("year") == 1706)
    chk("入关后第七年 顺治=1650", (parse_era_anchor("顺治入关后的第七年") or {}).get("year") == 1650)
    chk("干支 甲申 含1644", 1644 in ganzhi_candidates("甲申"))
    chk("祖先锚 东汉 区间", (parse_era_anchor("东汉") or {}).get("kind") == "range")
    rel = parse_relative_offset("三日后") or {}
    chk("相对偏移 三日后=+3", rel.get("offset_days") == 3.0)
    rel2 = parse_relative_offset("二十年前") or {}
    chk("相对偏移 二十年前=-7300", rel2.get("offset_days") == -7300.0)
    chk("年龄 十八岁=18", (parse_age("十八岁") or {}).get("age") == 18)
    chk("年龄 年近六旬=60", (parse_age("年近六旬") or {}).get("age") == 60)
    chk("年龄 五十左右=50 约略", (parse_age("五十左右") or {}).get("precision") == "约略")
    chk("粒度 三更=日内级", classify_granularity("三更", "时点", None) == "日内级")
    chk("粒度 第二日=日级", classify_granularity("第二日", "时点", None) == "日级")
    chk("粒度 中秋=季月级", classify_granularity("中秋", "时点", None) == "季月级")
    chk("粒度 康熙十三年=年级", classify_granularity("康熙十三年", "时点", parse_era_anchor("康熙十三年")) == "年级")
    chk("粒度 明朝=纪元级", classify_granularity("明朝", "时点", parse_era_anchor("明朝")) == "纪元级")
    chk("类型 年龄管道", classify_time_type("十八岁", "年龄") == "年龄")
    chk("类型 裸%时长兜底", classify_time_type("十年", "") == "时长")
    chk("W6 亿万年", bool(W6_RE.search("亿万年")))
    chk("W1 闭关语境", bool(W1_RE.search("闭关一十二年出关")))
    chk("W5 周期语境", bool(W5_RE.search("每三年带他回京一次")))
    chk("追叙信号 三年前", bool(FORK_SIGNAL_RE.search("三年前")))
    chk("干支 非法", ganzhi_candidates("甲甲") == [])
    # 单调性纯函数模拟（与 resolve_book 同口径：delta<0 → E1；一方约略 → E2）
    def mono(seq):
        out = []
        prev = None
        for t, prec in seq:
            if prev is not None and t - prev[0] < -1e-6:
                out.append("E2" if ("约略" in (prec, prev[1])) else "E1")
            prev = (t, prec)
        return out
    chk("单调递增通过", mono([(0, "精确"), (1, "精确"), (2, "精确")]) == [])
    chk("硬倒流 E1", mono([(0, "精确"), (5, "精确"), (3, "精确")]) == ["E1"])
    chk("约略倒流 E2", mono([(0, "精确"), (5, "约略"), (3, "精确")]) == ["E2"])
    ok = sum(1 for _, c in checks if c)
    print(f"[selftest] {ok}/{len(checks)} passed")
    return 0 if ok == len(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="time_resolver_wuxia.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "N4 书内相对时间轴解析（D05）：读 tagged/struct 的 % 时间令牌与 PN 锚点，\n"
            "按 SKILL_时间体系_武侠版 §二-§八 解析时点键/四类锚点/书内刻度 t/单调性/分叉隔离，\n"
            "输出 registry/time/<书>.json + logs/time/<书>.md。只读 tagged，不写语料。"),
        epilog=(
            "示例：\n"
            "  python -X utf8 scripts/time_resolver_wuxia.py --selftest\n"
            "  python -X utf8 scripts/time_resolver_wuxia.py --book 江湖三女侠\n"
            "  python -X utf8 scripts/time_resolver_wuxia.py --book 七剑下天山 --chapter 1-5\n"
            "  python -X utf8 scripts/time_resolver_wuxia.py --all\n\n"
            "输出 schema：wuxia-time-resolve-v1（time_points 全量，字段见 serialize_tp）：\n"
            "  tp_id/段锚/时间类型/粒度五级/锚点类型/偏移/t_days/year_ce/精度/\n"
            "  confidence/narrative_line/narrative_mode/fork_id/status/flags/context。\n"
            "规则见脚本注释与 SKILL §二-§八；不调 LLM。"),
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--book", metavar="书名", help="单书（如 江湖三女侠）")
    g.add_argument("--all", action="store_true", help="5 书全部 + 汇总")
    g.add_argument("--selftest", action="store_true", help="单元断言（解析/分类/单调性）")
    p.add_argument("--chapter", metavar="SPEC", default=None, help="回范围，如 1-5 或 12 或 1,3,5")
    p.add_argument("--report", metavar="PATH", type=Path, default=None,
                   help="单书报告输出路径（默认 logs/time/<书>.md）")
    p.add_argument("--out-registry", metavar="DIR", type=Path, default=REGISTRY_TIME_DIR,
                   help=f"JSON 输出目录（默认 {REGISTRY_TIME_DIR.relative_to(ROOT)}）")
    p.add_argument("--strict", action="store_true",
                   help="严格模式：主轨 E1>0 或 fatal>0 时 exit 2（默认只出报告 exit 0）")
    p.add_argument("--quiet", action="store_true", help="安静模式")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    if args.selftest:
        return run_selftest()
    chapters = parse_chapters(args.chapter) if args.chapter else None
    books = DEFAULT_BOOKS if args.all else [args.book]
    results = run_books(books, chapters, args.out_registry, args.report, args.quiet)
    if not results:
        return 1
    if args.strict:
        e1 = sum(r["stats"]["monotonic_violations"]["E1"] for r in results)
        fatal = sum(1 for r in results for e in r["errors"] if e["level"] == "error")
        if e1 or fatal:
            print(f"[STRICT] E1={e1} fatal={fatal} → exit 2", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
