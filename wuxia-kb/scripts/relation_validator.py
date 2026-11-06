# -*- coding: utf-8 -*-
"""N5 · relation_validator —— 04f 联动候选 → D06 谓词核验 → 关系表落库。

规范源（只读）：
  - skills/SKILL_关系体系_武侠版.md v0.3-draft（D06）
      §7.2 谓词总表 55 条 SPO（本脚本 PREDICATES 逐条编码）、§五 双树/辈分 B1-B8、
      §6.2 离线表 schema、§8.1 证据三级（E1 明文 / E2 动作+共现 / E3 推导）、
      §8.2 候选→核验→入表流程、§8.3 传闻降权、§8.4 关系触发语式表、§9.3 质量验证
  - skills/SKILL_04f_动词标注.md §四 联动总表 27 行（本脚本 LINKAGE 逐行编码）；
    联动 = 候选生成器，不是定论；强制档缺失→降级待审（报告“放弃原因”）
  - skills/SKILL_04a_事件识别.md §五 事件字段总表 / §5.3 参与方语义角色
  - docs/17 §2.3：N5 消费 D06/D03；产出供 N8 穿帮雷达、N10 SKU、EX-4 graph.json

输入（只读，不写 tagged）：
  tagged/<书>/*.tagged.md 的 〖实体〗/⟦六域⟧ 令牌 + PN 段号
  registry/concordance/<书>.json 的变量→规范名（书内归并）
  registry/entities.json 的跨书唯一别名映射

输出：
  registry/relations/<书>.json   edges[]：subject/predicate/object/subject_type/
                                 object_type/confidence/loc/evidence/rule（对齐 D06 离线表）
                                 + 派生（同门/辈分标签/师承树）+ 放弃原因 + 校验
  logs/relations/<书>.md         报告：候选数/落库数/放弃原因/谓词分布/旧 kb 对照/EX-4 映射
  logs/relations/_summary.md     5 书汇总
  logs/qa/relation_validator_selftest.md  --selftest 断言报告

口径与纪律：
  - 只输出“可审计候选”：每条 edge 带规则 id + 定位符 + 证据级；不追求人工级准确率；
  - 名分类关系（师承/结义/配偶/婚约/收养）须 E1 明文实写，动作+共现只产事实类 SPO；
  - 传闻（听说/据说/传言…）降权不入正式表；对话内动词按视角/转述跳过（§8.3）；
  - 辈分/同门只做可推导子集（B1/B2/B3/B5），全部 derived=true、confidence=weak；
  - 不做时间轴对齐（N4 未上线）：互斥/时序只做定位符级校验并列入“待审”。

CLI：
  python scripts/relation_validator.py --all                 # 5 书全跑（默认）
  python scripts/relation_validator.py --book 白发魔女传
  python scripts/relation_validator.py --book 白发魔女传 --chapter 3   # 单回调试（只写 logs/relations/_debug）
  python scripts/relation_validator.py --report              # 只从 registry/relations/*.json 重出报告
  python scripts/relation_validator.py --strict              # 严格门禁：仅 27 行规则 + strong/ok；校验失败 exit 1
  python scripts/relation_validator.py --selftest            # 内置断言
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import config        # scripts/config.py：路径唯一来源
import symbols       # scripts/symbols.py：标注令牌唯一解析入口

# ---------------------------------------------------------------- 路径 / 版本
CORPUS = config.CORPUS_ROOT
TAG = config.DIR_TAGGED
REG = config.DIR_REGISTRY
LEGACY_KB = config.LEGACY_KB
CONCORDANCE = REG / "concordance"
OUT_REL = REG / "relations"
LOGS_REL = config.DIR_LOGS / "relations"
LOGS_QA = config.DIR_LOGS / "qa"
DEBUG_DIR = LOGS_REL / "_debug"

SPEC_VERSION = symbols.SPEC_VERSION            # 0.3-draft
SCHEMA = "relations-v0.1"
SCRIPT_VERSION = "0.1"
PREDICATE_TABLE_VERSION = "D06@0.3-draft"
SOURCE_LIST = ["tagged/<书>/*.tagged.md（只读）", "registry/concordance/<书>.json",
               "registry/entities.json", "skills/SKILL_关系体系_武侠版.md §7.2/§8",
               "skills/SKILL_04f_动词标注.md §四 联动总表 27 行"]

# ---------------------------------------------------------------- 文本/角色常量
PARAGRAPH_RE = re.compile(r"^\[(\d+)\]\s*(.*)$")
SENT_END = set("。！？；…")
CLAUSE_PUNCT = set("，、；：,;:")
QUOTE_OPEN = set("“‘「『")
QUOTE_CLOSE = set("”’」』")
RUMOR_WORDS = ("听说", "据说", "传言", "传闻", "风闻", "江湖传闻")

# 实体类型集合（D06 三分：P 人物、O 组织、L 地点、I 物件、T 技术、G 人物组；符号码为标注层）
P_TYPES = {"@", "&", "◎"}
G_TYPES = {"@", "◎"}
O_TYPES = {"◆"}
L_TYPES = {"="}
I_TYPES = {"•", "{"}
T_TYPES = {"☆"}
H_TYPES = {";"}
TYPE_SETS = {"P": P_TYPES, "O": O_TYPES, "L": L_TYPES, "I": I_TYPES, "T": T_TYPES,
             "G": G_TYPES, "H": H_TYPES, "PG": P_TYPES | G_TYPES, "PO": P_TYPES | O_TYPES,
             "ANY": set(), "E": set()}
GENERIC_PERSON_NAMES = {
    "师", "师父", "师傅", "恩师", "师尊", "弟子", "徒弟", "徒儿", "大师", "禅师", "道长",
    "上人", "前辈", "老者", "老汉", "和尚", "道士", "尼姑", "公子", "姑娘", "夫人",
    "皇帝", "皇上", "太子", "王爷", "大人", "阁下", "先生", "小姐", "孩子", "众人",
}
TYPE_LABELS = {"@": "人物", "◎": "人物群组", "&": "家族世系", "◆": "组织", "=": "地点",
               "•": "器物", "{": "作品文书", "☆": "武功技艺", ";": "职衔",
               "^": "专门概念", "%": "时间", "#": "身份", "$": "数量", "+": "生物", "~": "族群"}

# 宾语侧“紧邻”允许的虚词/趋向补语（A—动词—B 邻近对；与 EX-1 同口径）
OBJ_GAP_MAX = 8
OBJ_GAP_ALLOWED = set("了着在向给过出到和与至入往自被把对得地成为一之其并再又便就都也还已将")
# 主语与动词的最大距离（字符）
SUBJ_GAP_MAX = 40
# 三元谓词的参数实体搜索窗（字符）
PARAM_WINDOW = 35


def _type_set(key: str) -> set:
    return TYPE_SETS[key]


# ---------------------------------------------------------------- D06 谓词总表（55 条）
def _pred(num, name, layer, subj, obj, direction, symmetric, transitive, evidence,
          source, conf, note=""):
    return {"num": num, "name": name, "layer": layer,
            "subj": _type_set(subj), "obj": _type_set(obj), "subj_key": subj, "obj_key": obj,
            "direction": direction, "symmetric": symmetric, "transitive": transitive,
            "evidence": evidence, "source": source, "conf": conf, "note": note}


# 层：事=事件层、实=实体层、人=人物层；方向 →/↔/组
PREDICATES = [
    _pred(1, "sequel", "事", "E", "E", "→", False, False, "明", "05a", "强"),
    _pred(2, "causal", "事", "E", "E", "→", False, False, "明", "05a", "强"),
    _pred(3, "cross_causal", "事", "E", "E", "→", False, False, "明", "05a", "强"),
    _pred(4, "part_of", "事", "E", "E", "→", False, False, "明", "05a", "强"),
    _pred(5, "opposition", "事", "E", "E", "↔", True, False, "明", "05a", "中"),
    _pred(6, "cross_ref", "事", "E", "E", "↔", True, False, "明", "05a", "强"),
    _pred(7, "co_person", "事", "E", "E", "↔", True, False, "动", "05a", "弱"),
    _pred(8, "co_location", "事", "E", "E", "↔", True, False, "动", "05a", "弱"),
    _pred(9, "concurrent", "事", "E", "E", "↔", True, False, "明/动", "05a重定义", "中"),
    _pred(10, "inherit", "事", "E", "E", "→", False, False, "明", "新增", "强"),
    _pred(11, "foreshadow", "事", "E", "E", "→", False, False, "明(回收)/推(埋设)", "新增", "回收强/埋设中"),
    _pred(12, "cross_book_ref", "事", "E", "E", "↔", True, False, "明", "新增", "待#7"),
    _pred(13, "辖属", "实", "L", "L", "→", False, False, "明", "05b武侠化", "强"),
    _pred(14, "统属", "实", "O", "O", "→", False, True, "明", "新增", "强"),
    _pred(15, "山门", "实", "O", "L", "→", False, False, "明", "新增", "强"),
    _pred(16, "练功地", "实", "P", "L", "→", False, False, "明", "新增", "中"),
    _pred(17, "决战地", "实", "E", "L", "→", False, False, "明", "05b(战场)", "强"),
    _pred(18, "到达", "实", "P", "L", "→", False, False, "动", "04f/01g", "强"),
    _pred(19, "离开", "实", "P", "L", "→", False, False, "动", "01g", "强"),
    _pred(20, "所在", "实", "P", "L", "→", False, False, "动", "01g", "中"),
    _pred(21, "层级隶属", "实", "T", "T", "→", False, False, "明", "01g§9.3", "强"),
    _pred(22, "创派", "实", "P", "T", "→", False, False, "明", "新增", "强"),
    _pred(23, "归属", "实", "T", "O", "→", False, False, "明", "新增", "强"),
    _pred(24, "掌握", "实", "P", "T", "→", False, False, "明/动", "04f", "强"),
    _pred(25, "修习", "实", "P", "T", "→", False, False, "明/动", "01g", "中"),
    _pred(26, "持有", "实", "P", "I", "→", False, False, "明/动", "01g", "强"),
    _pred(27, "制造", "实", "P", "I", "→", False, False, "明", "01g", "强"),
    _pred(28, "转移", "实", "P", "P", "→", False, False, "动(事件)", "04f", "强",
          "二元核=施者→受者；物=参数；mode=赠/夺/借/还/传"),
    _pred(29, "组织成员", "实", "P", "O", "→", False, False, "明", "01g", "强"),
    _pred(30, "任职", "实", "P", "H", "→", False, False, "明", "04f", "强", "宾语=职衔；组织=参数"),
    _pred(31, "继任", "实", "P", "H", "→", False, False, "明", "01g", "强", "宾语=前任/职衔"),
    _pred(32, "隶属终止", "实", "P", "O", "→", False, False, "明", "04f", "强"),
    _pred(33, "群组成员", "实", "P", "G", "→", False, False, "明", "01g", "中"),
    _pred(34, "异名", "实", "ANY", "ANY", "↔", True, False, "明", "05b(62)武侠化", "强"),
    _pred(35, "师承", "人", "P", "P", "→", False, True, "明(拜师实写)", "04f", "强", "徒→师；传递仅出辈分标签"),
    _pred(36, "传授", "人", "P", "P", "→", False, False, "动", "04f", "强", "师→徒；武功=参数"),
    _pred(37, "结义", "人", "G", "G", "组", True, False, "明", "04f", "强", "组内两两成边"),
    _pred(38, "结盟", "人", "PG", "PO", "组", True, False, "明", "01g", "强"),
    _pred(39, "敌对", "人", "PO", "PO", "↔", True, False, "明/持续动", "01g", "中"),
    _pred(40, "配偶", "人", "P", "P", "↔", True, False, "明", "04f", "强"),
    _pred(41, "婚约", "人", "P", "P", "↔", True, False, "明", "新增", "强"),
    _pred(42, "收养", "人", "P", "P", "→", False, False, "明", "01g", "强"),
    _pred(43, "亲属", "人", "P", "P", "按类型", False, True, "明", "01g", "强", "亲长→幼辈；类型字段"),
    _pred(44, "仇怨", "人", "P", "P", "→或mutual", False, False, "明", "新增", "强", "event_ids 必填"),
    _pred(45, "同门", "人", "P", "P", "↔", True, False, "推", "推导", "中", "derived，不直接登记"),
    _pred(46, "冒名", "人", "P", "P", "→", False, False, "明", "新增", "强"),
    _pred(47, "杀害", "人", "P", "P", "→", False, False, "动", "04f", "强"),
    _pred(48, "治愈", "人", "P", "P", "→", False, False, "动", "04f", "强"),
    _pred(49, "投毒", "人", "P", "P", "→", False, False, "动", "04f", "强"),
    _pred(50, "拘押", "人", "P", "P", "→", False, False, "动", "01g", "强"),
    _pred(51, "解救", "人", "P", "P", "→", False, False, "动", "01g", "强"),
    _pred(52, "押送", "人", "P", "P", "→", False, False, "动", "04f", "强", "讫地=参数"),
    _pred(53, "交手", "人", "P", "P", "↔", True, False, "动", "04f", "强", "战斗ID=参数"),
    _pred(54, "点穴", "人", "P", "P", "→", False, False, "动", "04f", "强", "穴道=参数"),
    _pred(55, "同行", "人", "P", "P", "↔", True, False, "动", "01g", "中"),
]
PREDICATE_BY_NAME = {p["name"]: p for p in PREDICATES}
# D06 §8.1 E2 不得单独确立名分类关系
NAME_RELATIONS = {"师承", "结义", "配偶", "婚约", "收养"}

# ---------------------------------------------------------------- 04f 联动总表 27 行
# 每行：row/04f 触发词/建议谓词/强度/缺失处理；predicate=None 表示 D06 无对应 SPO（放弃并记因）
LINKAGE_ROWS = [
    {"row": 1, "triggers": "练成/学会/悟出", "predicate": "掌握", "strength": "强制"},
    {"row": 2, "triggers": "传授（具体武功名在句）", "predicate": "传授", "strength": "强制"},
    {"row": 3, "triggers": "授艺/教（泛指）", "predicate": None, "strength": "建议",
     "reason": "建议档泛指授艺（04f#3：记子型‘指点’，不生成三元组）"},
    {"row": 4, "triggers": "偷学/窃艺", "predicate": "掌握", "strength": "强制"},
    {"row": 5, "triggers": "点穴（穴道名在句）", "predicate": "点穴", "strength": "强制"},
    {"row": 6, "triggers": "拜师/拜…为师", "predicate": "师承", "strength": "强制"},
    {"row": 7, "triggers": "收徒/授艺（具体对象）", "predicate": "师承", "strength": "强制"},
    {"row": 8, "triggers": "杀/杀死/斩杀", "predicate": "杀害", "strength": "强制"},
    {"row": 9, "triggers": "疗伤/救活/治愈", "predicate": "治愈", "strength": "强制"},
    {"row": 10, "triggers": "下毒/投毒（致害成立）", "predicate": "投毒", "strength": "强制"},
    {"row": 11, "triggers": "赠/赠送/相赠", "predicate": "转移", "strength": "强制"},
    {"row": 12, "triggers": "夺/抢（夺物义）", "predicate": "转移", "strength": "强制"},
    {"row": 13, "triggers": "借/还", "predicate": "转移", "strength": "强制"},
    {"row": 14, "triggers": "铸/炼制/打造", "predicate": "制造", "strength": "强制"},
    {"row": 15, "triggers": "折断/烧毁/焚毁", "predicate": None, "strength": "强制",
     "reason": "D06 无『毁损』SPO 谓词（毁弃留事件层 ⊟）"},
    {"row": 16, "triggers": "拜师→◆组织", "predicate": "组织成员", "strength": "建议"},
    {"row": 17, "triggers": "任命/继任/接任", "predicate": "任职", "strength": "强制"},
    {"row": 18, "triggers": "逐出/叛出", "predicate": "隶属终止", "strength": "强制"},
    {"row": 19, "triggers": "结义/结拜", "predicate": "结义", "strength": "强制"},
    {"row": 20, "triggers": "娶/嫁/成亲", "predicate": "配偶", "strength": "强制"},
    {"row": 21, "triggers": "抵达/来到（行程级）", "predicate": "到达", "strength": "强制"},
    {"row": 22, "triggers": "离开（行程级）", "predicate": "离开", "strength": "强制"},
    {"row": 23, "triggers": "押解/解往", "predicate": "押送", "strength": "强制"},
    {"row": 24, "triggers": "潜入/混入", "predicate": "到达", "strength": "强制",
     "note": "04f『进入』在 D06 无同名谓词，按 §7.3 对号入座最近落位 #18 到达（weak）"},
    {"row": 25, "triggers": "追踪/跟踪（行程级）", "predicate": None, "strength": "建议",
     "reason": "D06 55 谓词无『追踪』（04f#25 建议档），留候选池不落库"},
    {"row": 26, "triggers": "交手/比武", "predicate": "交手", "strength": "建议"},
    {"row": 27, "triggers": "使用阵法（结阵/布阵）", "predicate": None, "strength": "建议",
     "reason": "D06 无『施用』谓词（04f#27 建议档），留候选池不落库"},
]
# 扩展规则（超出 27 行；--strict 下禁用）：均为 D06 已定谓词 + E2 动作+共现
EXTENSION_ROWS = [
    {"row": "X-COMBAT", "triggers": "⊞ 攻击/防御动词（近邻双角色）", "predicate": "交手",
     "strength": "扩展", "note": "04f 联动仅列『交手/比武』；本导出把 ⊞ 攻击类动作+双角色实写视为交手候选（E2）"},
    {"row": "X-ARRIVE", "triggers": "■ 行程动词（回到/走到/走进/赶到…）", "predicate": "到达",
     "strength": "扩展", "note": "04f#21 仅列抵达/来到；同域同义行程动词按 到达 候选（E2）"},
    {"row": "X-LEAVE", "triggers": "■ 离开类动词（走出/退出/逃出…）", "predicate": "离开",
     "strength": "扩展", "note": "04f#22 仅列离开；同域同义行程动词按 离开 候选（E2）"},
    {"row": "X-RESCUE", "triggers": "救/救出/救下/营救", "predicate": "解救",
     "strength": "扩展", "note": "04f#9 只列疗伤/救活/治愈；『救』按 D06#51 解救 候选（E2）"},
]

# 触发词表（同域同义扩展，规则行号仍记 04f 行）
KILL_WORDS = {"杀", "杀死", "斩杀", "诛", "结果", "害死", "杀毙", "刺杀", "伏杀", "毒杀",
              "残杀", "误杀", "砍死", "打死", "加害", "谋害", "杀害"}
CURE_WORDS = {"疗伤", "救活", "治愈", "医治", "救治", "疗治", "敷药", "疗毒"}
RESCUE_WORDS = {"救", "救出", "救下", "营救", "搭救", "抢救", "解救", "救回"}
POISON_WORDS = {"下毒", "投毒", "放毒", "施毒", "下药"}
GIVE_WORDS = {"赠", "赠送", "相赠", "送给", "交给", "递给", "送", "奉送", "赠与", "赐", "赏赐"}
TAKE_WORDS = {"夺", "夺取", "抢夺", "抢走", "夺走", "抢", "夺得", "抢去", "夺取", "夺去"}
LEND_WORDS = {"借", "借给", "出借"}
RETURN_WORDS = {"还", "归还", "交还", "还给", "退还给"}
FORGE_WORDS = {"铸", "铸造", "炼制", "打造", "锻造", "铸成", "炼成"}
DESTROY_WORDS = {"折断", "烧毁", "焚毁", "砸", "劈断", "毁", "烧", "焚", "毁掉", "撕毁"}
APPOINT_WORDS = {"任命", "继任", "接任", "接掌", "即位", "登基", "立为", "封为", "任", "委任"}
EXCLUDE_WORDS = {"逐出", "驱逐", "赶出", "叛出", "叛门", "开除", "逐出门墙"}
SWORN_WORDS = {"结义", "结拜", "义结", "八拜", "拜把"}
MARRY_WORDS = {"娶", "嫁", "成亲", "成婚", "结婚", "完婚", "迎娶", "许配", "下嫁", "纳妾"}
ARRIVE_CORE = {"抵达", "来到", "到达"}
LEAVE_CORE = {"离开"}
ESCORT_WORDS = {"押解", "解往", "押送", "解送", "押着"}
ENTER_WORDS = {"潜入", "混入", "进入"}
TRACK_WORDS = {"追踪", "跟踪"}
FIGHT_WORDS = {"交手", "比武", "比试", "过招", "切磋", "较量", "大战", "恶斗", "交锋"}
ARRAY_WORDS = {"结阵", "布阵", "布下"}
VISIT_WORDS = {"拜见", "拜访", "求见", "参见", "参见"}
ARRIVE_EXT = {"回到", "走到", "走进", "跑进", "冲进", "赶到", "逃到", "返回", "直抵",
              "登上", "踏上", "踏入", "到", "抵达"} 
LEAVE_EXT = {"走出", "退出", "逃出", "撤离", "离去", "下山", "远走", "溜出", "奔出"}
# 均为 ⊞ 战斗域，用于 X-COMBAT 兜底
FIGHT_EXCLUDE = {"点", "点穴", "点中"}       # 点穴专由 04f#5 处理，无穴道时回落 X-COMBAT

# 语式表（D06 §8.4；仅高价值明文语式）
CUE_SWORN = ("八拜之交", "义结金兰", "金兰之契", "结为兄弟", "结为姐妹", "结为异姓兄弟")
CUE_BETROTH = ("指腹为媒", "结成亲家", "未婚妻", "未婚夫", "聘为妻", "订婚", "定亲")
CUE_ADOPT = ("收为义子", "收为义女", "收为养子", "收为养女", "认为干亲", "认作义子", "认作干亲")
CUE_FEUD = ("杀父之仇", "报…之仇", "仇人", "仇家", "杀兄之仇", "灭门之仇")
CUE_GRACE = ("救命之恩", "大恩", "知遇之恩", "收留之恩")
CUE_CHENG = ("是", "的师父", "的师傅", "的徒弟", "的弟子", "拜", "为师", "收…为徒")

CONF_RANK = {"strong": 3, "ok": 2, "weak": 1}
CONF_ZH = {"strong": "强", "ok": "中", "weak": "弱"}


# ---------------------------------------------------------------- 小工具
def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(payload, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    tmp.replace(path)
    return path


def write_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def books() -> list:
    """有 tagged 产物的书（当前 5 部），按 config 书目顺序。"""
    out = []
    for name in config.book_names():
        if (TAG / name).is_dir() and list((TAG / name).glob("*.tagged.md")):
            out.append(name)
    return out


# ---------------------------------------------------------------- 规范名映射
_ALIAS_CACHE = None


def registry_alias_map() -> dict:
    """registry/entities.json → {别名: 规范名}（仅唯一映射、且别名本身不是规范名）。"""
    global _ALIAS_CACHE
    if _ALIAS_CACHE is not None:
        return _ALIAS_CACHE
    path = REG / "entities.json"
    if not path.exists():
        _ALIAS_CACHE = {}
        return _ALIAS_CACHE
    reg = read_json(path)
    canon_set = {e["canonical"] for e in reg.get("entities") or []}
    alias_to = defaultdict(set)
    for e in reg.get("entities") or []:
        for a in e.get("aliases") or []:
            alias_to[a].add(e["canonical"])
    _ALIAS_CACHE = {a: next(iter(v)) for a, v in alias_to.items()
                    if len(v) == 1 and a not in canon_set}
    return _ALIAS_CACHE


_VARIANT_CACHE = {}


def variant_map(book: str) -> dict:
    """concordance 的 显示变体→书内规范名（按实体类型分键，避免跨类型误归并）。"""
    if book in _VARIANT_CACHE:
        return _VARIANT_CACHE[book]
    path = CONCORDANCE / f"{book}.json"
    vmap = {}
    if path.exists():
        conc = read_json(path)
        for ent in conc.get("entities") or []:
            canon = ent.get("canonical")
            code = ent.get("type")
            if not canon or not code:
                continue
            vmap[(code, canon)] = canon
            for v in ent.get("variants") or []:
                d = v.get("display")
                if d:
                    vmap[(code, d)] = canon
    _VARIANT_CACHE[book] = vmap
    return vmap


class Ctx:
    """一书一次抽取的上下文（规范名映射 + 快照统计）。"""

    def __init__(self, book: str):
        self.book = book
        self.vmap = variant_map(book)
        self.alias = registry_alias_map()

    def canon(self, display: str, pipe: str | None, code: str) -> str:
        cand = (pipe or display or "").strip()
        name = (self.vmap.get((code, cand)) or self.vmap.get((code, display))
                or self.vmap.get((code, "")) or cand)
        if code in P_TYPES | O_TYPES:
            name = self.alias.get(name, name)
        if code in ("@", "◎", "&") and (len(name) <= 1 or name in GENERIC_PERSON_NAMES):
            return ""
        return name


# ---------------------------------------------------------------- 段落解析
def _plain_with_map(text: str):
    """剥标后的显示串 + 每个显示字符对应的原文位置（语式正则用）。"""
    out, mapping = [], []
    pos = 0
    for m in symbols.TOKEN_RE.finditer(text):
        out.append(text[pos:m.start()])
        mapping.extend(range(pos, m.start()))
        kind, code, body, display, pipe, err = symbols.parse_token(m.group(0))
        if kind == "entity":
            disp = (display or "").strip()
        else:
            disp = body[1:].split("|", 1)[0].strip()
        out.append(disp)
        mapping.extend([m.start()] * len(disp))
        pos = m.end()
    out.append(text[pos:])
    mapping.extend(range(pos, len(text) + 1))
    return "".join(out), mapping


class Para:
    """单段：实体/动词令牌 + 句界/小句界 + 引号深度 + 剥标显示串。"""

    def __init__(self, ctx: Ctx, chapter_no: int, para_no: int, text: str):
        self.ctx = ctx
        self.chapter = chapter_no
        self.no = para_no
        self.text = text
        self.plain, self.plain_map = _plain_with_map(text)
        self.loc = f"{chapter_no:03d}:{para_no}"
        self.entities: list = []
        self.verbs: list = []
        self._scan_tokens()
        self.sent = _bounds(text, SENT_END)
        self.clause = _bounds(text, SENT_END | CLAUSE_PUNCT)

    def _scan_tokens(self):
        text = self.text
        qdepth = _quote_depth(text)
        for m in symbols.TOKEN_RE.finditer(text):
            kind, code, body, display, pipe, err = symbols.parse_token(m.group(0))
            if err:
                continue
            if kind == "entity":
                name = self.ctx.canon(display or "", pipe, code)
                if not name:
                    continue
                self.entities.append({"pos": m.start(), "end": m.end(), "code": code,
                                      "display": display or "", "canon": name})
            elif kind == "verb" and code in symbols.VERB_CODES:
                word = (pipe or "").strip()
                # parse_token 的 pipe 对动词=消歧说明；触发词=body 的第一段
                raw = body[1:]
                word = raw.split("|", 1)[0].strip()
                self.verbs.append({"pos": m.start(), "end": m.end(), "code": code,
                                   "word": word,
                                   "in_quote": qdepth[m.start()] > 0 if m.start() < len(qdepth) else False})

    def sent_of(self, pos: int) -> tuple:
        return _seg_of(pos, self.sent)

    def clause_of(self, pos: int) -> tuple:
        return _seg_of(pos, self.clause)


def _quote_depth(text: str) -> list:
    depth = [0] * len(text)
    d = 0
    for i, ch in enumerate(text):
        depth[i] = d
        if ch in QUOTE_OPEN:
            d += 1
        elif ch in QUOTE_CLOSE:
            d = max(0, d - 1)
    return depth


def _bounds(text: str, marks: set) -> list:
    out = [(0, len(text) + 1)]
    start = 0
    for i, ch in enumerate(text):
        if ch in marks:
            out.append((start, i + 1))
            start = i + 1
    out.append((start, len(text) + 1))
    # 去掉空区间，保持有序
    return [(a, b) for a, b in out if b > a]


def _seg_of(pos: int, bounds: list) -> tuple:
    for a, b in bounds:
        if a <= pos < b:
            return (a, b)
    return bounds[-1]


def _gap_ok(gap: str, max_len: int = OBJ_GAP_MAX) -> bool:
    return len(gap) <= max_len and all(ch in OBJ_GAP_ALLOWED or ch.isspace() for ch in gap)


def near_before(para: Para, pos: int, types: set, max_gap: int = SUBJ_GAP_MAX,
                min_pos: int | None = None):
    """动词前最近的目标类型实体（同句、距离受限）。"""
    a, _b = para.sent_of(pos)
    lo = max(a, min_pos if min_pos is not None else a)
    best = None
    for ent in reversed(para.entities):
        if ent["end"] > pos:
            continue
        if ent["pos"] < lo:
            break
        if ent["code"] not in types:
            continue
        if pos - ent["end"] > max_gap:
            break
        best = ent
        break
    return best


def near_after(para: Para, pos_end: int, types: set, max_gap: int = OBJ_GAP_MAX,
               strict_gap: bool = True, clause_only: bool = True):
    """动词后最近的目标类型实体（同句；strict_gap 时要求间隔仅虚词）。"""
    _a, b = para.sent_of(pos_end)
    best = None
    for ent in para.entities:
        if ent["pos"] < pos_end:
            continue
        if ent["pos"] >= b:
            break
        if ent["code"] not in types:
            continue
        gap = para.text[pos_end:ent["pos"]]
        if strict_gap and not _gap_ok(gap, max_gap):
            continue
        if clause_only and para.clause_of(ent["pos"]) != para.clause_of(pos_end):
            continue
        best = ent
        break
    return best


def nearest_param(para: Para, verb: dict, types: set, window: int = PARAM_WINDOW):
    """动词窗口内最近的目标类型实体（参数用：物/武功/穴道/地点/职衔）。"""
    a, b = para.sent_of(verb["pos"])
    lo = max(a, verb["pos"] - window)
    hi = min(b, verb["end"] + window)
    best, best_d = None, None
    for ent in para.entities:
        if ent["pos"] < lo or ent["end"] > hi:
            continue
        if ent["code"] not in types:
            continue
        d = min(abs(ent["pos"] - verb["pos"]), abs(ent["pos"] - verb["end"]))
        if best_d is None or d < best_d:
            best, best_d = ent, d
    return best


PASSIVE_WINDOW = 16


def person_pair(para: Para, verb: dict):
    """A—动词—B 人物对：返回 (subj_ent, obj_ent, basis_note)；缺失返回 (None, None, None)。

    先做被动句施受核验（§8.2 步骤 2 / 04f §4.2 铁律 1）：`A 被 B ⟦动词⟧` 中
    B=施事、A=受事；再回落到“动词前最近人物 + 动词后紧邻人物”。
    """
    vs, ve = verb["pos"], verb["end"]
    seg = para.sent_of(vs)
    win_lo = max(seg[0], vs - PASSIVE_WINDOW)
    bei = para.text.rfind("被", win_lo, vs)
    if bei != -1:
        agent = near_before(para, vs, P_TYPES, max_gap=8, min_pos=bei + 1)
        patient = near_before(para, bei, P_TYPES, max_gap=24)
        if agent and patient and agent["canon"] != patient["canon"]:
            return agent, patient, "E2动作+共现（被动句施受核验）"
    subj = near_before(para, vs, P_TYPES)
    if not subj:
        return None, None, None
    obj = near_after(para, ve, P_TYPES, max_gap=OBJ_GAP_MAX, strict_gap=True)
    if not obj:
        # 放宽：同句内宾语侧含“向/朝/对/把”等介词引导，允许更长间隔
        obj = near_after(para, ve, P_TYPES, max_gap=12, strict_gap=False)
        if obj:
            gap = para.text[ve:obj["pos"]]
            if not any(ch in "向朝对把将" for ch in gap):
                obj = None
    if not obj:
        return None, None, None
    return subj, obj, "E2动作+共现"


# ---------------------------------------------------------------- 候选/放弃 结构
def make_candidate(para: Para, predicate: str, subj, obj, *, confidence: str,
                   evidence_type: str, rule: str, rule_row, subtype: str = "",
                   params: dict | None = None, notes: str = "",
                   subject=None, object_=None) -> dict:
    """生成候选（subject/object 可显式覆盖，缺省取 subj/obj 实体）。"""
    s = subject if subject is not None else subj
    o = object_ if object_ is not None else obj
    return {
        "subject": s["canon"] if isinstance(s, dict) else str(s),
        "subject_type": s["code"] if isinstance(s, dict) else "",
        "object": o["canon"] if isinstance(o, dict) else str(o),
        "object_type": o["code"] if isinstance(o, dict) else "",
        "predicate": predicate,
        "confidence": confidence,
        "evidence_type": evidence_type,
        "rule": rule,
        "rule_row": rule_row,
        "subtype": subtype,
        "params": params or {},
        "notes": notes,
        "loc": para.loc,
        "chapter": para.chapter,
        "para": para.no,
    }


def make_drop(para: Para, reason: str, *, rule: str = "", rule_row=None,
              predicate: str = "", note: str = "") -> dict:
    return {"reason": reason, "rule": rule, "rule_row": rule_row,
            "predicate": predicate, "loc": para.loc, "note": note}


# ---------------------------------------------------------------- 规则处理函数
# 每个 handler(para, verb) → {"candidates": [...], "drops": [...]} 或 None（不适用，继续后续规则）
def _h_zhangwo(para: Para, verb: dict, meta: dict):
    target = nearest_param(para, verb, T_TYPES)
    if target is None:
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#1/#4 武功名未在句）", rule=meta["rule"],
            rule_row=meta["row"], predicate="掌握")]}
    subj = near_before(para, verb["pos"], P_TYPES)
    if subj is None:
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（掌握主语人物未在句）", rule=meta["rule"],
            rule_row=meta["row"], predicate="掌握")]}
    mode = "偷学" if verb["word"] in {"偷学", "窃艺", "偷习"} else ""
    return {"candidates": [make_candidate(
        para, "掌握", subj, target, confidence=meta.get("conf", "strong"),
        evidence_type="E2动作+共现", rule=meta["rule"], rule_row=meta["row"],
        subtype=mode, params={"武功": target["canon"]})]}


def _h_chuanshou(para: Para, verb: dict, meta: dict):
    target = nearest_param(para, verb, T_TYPES)
    subj = near_before(para, verb["pos"], P_TYPES)
    obj = near_after(para, verb["end"], P_TYPES, max_gap=OBJ_GAP_MAX, strict_gap=True)
    if target is None or subj is None or obj is None:
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#2 传授须师+徒+武功名齐备）",
            rule=meta["rule"], rule_row=meta["row"], predicate="传授")]}
    return {"candidates": [make_candidate(
        para, "传授", subj, obj, confidence="strong", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"],
        params={"武功": target["canon"]},
        notes="传授≠师承（04f 移交语；D06#36）")]}


def _h_bai_shi(para: Para, verb: dict, meta: dict):
    """拜师/拜…为师 → 师承(徒→师)；收徒/收…为徒 → 师承（方向倒置）；E1 明文要求。"""
    word = verb["word"]
    plain = para.plain
    pos = verb["pos"]
    subj = near_before(para, pos, P_TYPES)
    obj = near_after(para, verb["end"], P_TYPES, max_gap=OBJ_GAP_MAX, strict_gap=True)
    if word in {"收", "收徒", "收下"} or "为徒" in plain:
        if re.search(r"收徒之[念想意]|收徒的念头|动了收徒", plain):
            return {"candidates": [], "drops": [make_drop(
                para, "意图不标（01g/04f R8：收徒之念=意图，须拜师/收徒实写）",
                rule=meta["rule"], rule_row=meta["row"], predicate="师承")]}
        # 收徒：A 收 B 为徒 / A 将 B 收为徒 → master, disciple
        master, disciple = subj, obj
        if not (master and disciple):
            disciple = near_before(para, pos, P_TYPES)
            sent = para.sent_of(pos)
            if disciple is not None:
                prefix = para.text[sent[0]:disciple["pos"]]
                j = max(prefix.rfind("将"), prefix.rfind("把"))
                if j != -1:
                    master = near_before(para, sent[0] + j, P_TYPES)
        if not (master and disciple):
            return {"candidates": [], "drops": [make_drop(
                para, "强制档实体缺失（04f#7 收徒双方未同现）",
                rule=meta["rule"], rule_row=meta["row"], predicate="师承")]}
        if master["canon"] == disciple["canon"]:
            return {"candidates": [], "drops": [make_drop(
                para, "自指/主宾同一实体", rule=meta["rule"],
                rule_row=meta["row"], predicate="师承")]}
        return {"candidates": [make_candidate(
            para, "师承", disciple, master, confidence="ok", evidence_type="E1明文",
            rule=meta["rule"], rule_row=meta["row"],
            notes="04f#7 收徒实写；方向倒置（徒→师）")]}
    # 拜师类：E1 明文须“拜师/拜…为师”
    if subj is None or obj is None:
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#6 拜师双方未同现）",
            rule=meta["rule"], rule_row=meta["row"], predicate="师承")]}
    explicit = ("拜师" in plain or "为师" in plain or
                re.search(r"拜[^。！？]{0,10}为师", plain) is not None or word in {"拜师", "投师", "求师"})
    if not explicit:
        return {"candidates": [], "drops": [make_drop(
            para, "E1 明文不足（师承须拜师实写；04f R1/R8、D06 §8.1）",
            rule=meta["rule"], rule_row=meta["row"], predicate="师承",
            note=f"触发词『{word}』无『为师/拜师』明文")]}
    disciple, master = subj, obj
    return {"candidates": [make_candidate(
        para, "师承", disciple, master, confidence="strong", evidence_type="E1明文",
        rule=meta["rule"], rule_row=meta["row"],
        notes="04f#6 拜师实写（E1 明文）")]}


def _h_kill(para: Para, verb: dict, meta: dict):
    subj, obj, basis = person_pair(para, verb)
    if not (subj and obj):
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#8 凶手/死者未同现）", rule=meta["rule"],
            rule_row=meta["row"], predicate="杀害")]}
    return {"candidates": [make_candidate(
        para, "杀害", subj, obj, confidence="strong", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"],
        notes="杀害边；死者事件留事件层（04a），另行触发亲属仇怨候选")]}


def _h_cure(para: Para, verb: dict, meta: dict):
    subj, obj, basis = person_pair(para, verb)
    if not (subj and obj):
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#9 医者/伤者未同现）", rule=meta["rule"],
            rule_row=meta["row"], predicate="治愈")]}
    return {"candidates": [make_candidate(
        para, "治愈", subj, obj, confidence="strong", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"],
        notes="治愈另触发恩义候选（离线表，§6.4；本脚本不落离线表）")]}


def _h_rescue(para: Para, verb: dict, meta: dict):
    subj, obj, basis = person_pair(para, verb)
    if not (subj and obj):
        if meta.get("extension"):
            return None      # 扩展规则机会式抽取，缺失不计放弃
        return {"candidates": [], "drops": [make_drop(
            para, "实体缺失（D06#51 解救须救者/被救者同现）", rule=meta["rule"],
            rule_row=meta["row"], predicate="解救")]}
    return {"candidates": [make_candidate(
        para, "解救", subj, obj, confidence="ok", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"],
        notes="一次救助不自动友盟（01g 铁律）")]}


def _h_poison(para: Para, verb: dict, meta: dict):
    subj, obj, basis = person_pair(para, verb)
    if not (subj and obj):
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#10 施毒者/被害人未同现）", rule=meta["rule"],
            rule_row=meta["row"], predicate="投毒")]}
    return {"candidates": [make_candidate(
        para, "投毒", subj, obj, confidence="strong", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"])]}


def _h_transfer(para: Para, verb: dict, meta: dict):
    """转移：二元核=施者→受者，物=参数，mode=赠/夺/借/还。"""
    mode = meta.get("mode", "")
    subst = make_subst(meta)
    item = nearest_param(para, verb, I_TYPES)
    subj, obj, basis = person_pair(para, verb)
    if item is None or subj is None or obj is None:
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#11-#13 转移须施者+受者+物齐备）",
            rule=meta["rule"], rule_row=meta["row"], predicate="转移",
            note=f"mode={mode}")]}
    # 借入方向：A 向 B 借物 → 施者=B、受者=A
    if mode == "借":
        gap = para.text[subj["end"]:verb["pos"]]
        if any(ch in gap for ch in "向跟问"):
            subj, obj = obj, subj
    return {"candidates": [make_candidate(
        para, "转移", subj, obj, confidence="strong", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"], subtype=mode,
        params={"物": item["canon"], "物类型": item["code"]},
        notes="转移二元核=施者→受者；物/mode 为参数（D06#28）")]}


def make_subst(meta: dict) -> dict:
    return {}


def _h_manufacture(para: Para, verb: dict, meta: dict):
    item = nearest_param(para, verb, I_TYPES)
    subj = near_before(para, verb["pos"], P_TYPES)
    if item is None or subj is None:
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#14 制造须人物+器物）", rule=meta["rule"],
            rule_row=meta["row"], predicate="制造")]}
    return {"candidates": [make_candidate(
        para, "制造", subj, item, confidence="strong", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"],
        params={"器物": item["canon"]})]}


def _h_destroy(para: Para, verb: dict, meta: dict):
    item = nearest_param(para, verb, I_TYPES)
    if item is None:
        return None
    return {"candidates": [], "drops": [make_drop(
        para, meta.get("reason") or "D06 无对应 SPO 谓词", rule=meta["rule"],
        rule_row=meta["row"], predicate="毁损", note=f"器物={item['canon']}")]}


def _h_appoint(para: Para, verb: dict, meta: dict):
    title = nearest_param(para, verb, H_TYPES)
    org = nearest_param(para, verb, O_TYPES)
    subj = near_before(para, verb["pos"], P_TYPES)
    if title is None or subj is None:
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#17 任职须人物+职衔）", rule=meta["rule"],
            rule_row=meta["row"], predicate="任职")]}
    return {"candidates": [make_candidate(
        para, "任职", subj, title, confidence="strong", evidence_type="E1明文",
        rule=meta["rule"], rule_row=meta["row"],
        params={"组织": org["canon"] if org else ""})]}


def _h_terminate(para: Para, verb: dict, meta: dict):
    person = near_before(para, verb["pos"], P_TYPES) or near_after(
        para, verb["end"], P_TYPES, max_gap=10, strict_gap=False, clause_only=False)
    org = nearest_param(para, verb, O_TYPES)
    if person is None or org is None:
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#18 隶属终止须人物+组织）", rule=meta["rule"],
            rule_row=meta["row"], predicate="隶属终止")]}
    return {"candidates": [make_candidate(
        para, "隶属终止", person, org, confidence="ok", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"],
        notes="与组织成员边配对；叛门投敌→离线表背叛候选（§6.4）")]}


def _h_sworn(para: Para, verb: dict, meta: dict):
    """结义：触发词附近（同小句、±40 字、≤4 人）的 N 元组，两两成边。"""
    vs, ve = verb["pos"], verb["end"]
    cl = para.clause_of(vs)
    actors = [e for e in para.entities
              if e["code"] in G_TYPES and cl[0] <= e["pos"] < cl[1]
              and vs - 40 <= e["pos"] <= ve + 40]
    if len(actors) < 2:
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#19 结义须≥2 人物）", rule=meta["rule"],
            rule_row=meta["row"], predicate="结义")]}
    actors.sort(key=lambda e: abs(e["pos"] - vs))
    actors = sorted(actors[:4], key=lambda e: e["pos"])
    out = []
    for i in range(len(actors)):
        for j in range(i + 1, len(actors)):
            a, b = actors[i], actors[j]
            if a["canon"] == b["canon"]:
                continue
            out.append(make_candidate(
                para, "结义", a, b, confidence="strong", evidence_type="E1明文",
                rule=meta["rule"], rule_row=meta["row"],
                params={"组规模": len(actors)}, notes="结义为 N 元组，组内两两成边"))
    return {"candidates": out}


def _h_marry(para: Para, verb: dict, meta: dict):
    subj, obj, basis = person_pair(para, verb)
    if not (subj and obj):
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#20 配偶须双方人物）", rule=meta["rule"],
            rule_row=meta["row"], predicate="配偶")]}
    return {"candidates": [make_candidate(
        para, "配偶", subj, obj, confidence="strong", evidence_type="E1明文",
        rule=meta["rule"], rule_row=meta["row"],
        notes="婚约→成婚状态机（D06 §4.4）；本边只记成婚实写")]}


def _h_travel(para: Para, verb: dict, meta: dict):
    """到达/离开：人物前、地点后（紧邻）。"""
    predicate = meta["predicate"]
    subj = near_before(para, verb["pos"], P_TYPES)
    place = near_after(para, verb["end"], L_TYPES, max_gap=OBJ_GAP_MAX, strict_gap=True)
    if place is None:
        place = near_after(para, verb["end"], L_TYPES, max_gap=8, strict_gap=False)
        if place is not None:
            gap = para.text[verb["end"]:place["pos"]]
            if not any(ch in "在到入往至向" for ch in gap):
                place = None
    if subj is None or place is None:
        if meta.get("extension"):
            return None      # 扩展规则机会式抽取，缺失不计放弃
        return {"candidates": [], "drops": [make_drop(
            para, "强制档实体缺失（04f#21/#22 行程动词须人物+地点）",
            rule=meta["rule"], rule_row=meta["row"], predicate=predicate)]}
    return {"candidates": [make_candidate(
        para, predicate, subj, place, confidence=meta.get("conf", "ok"),
        evidence_type="E2动作+共现", rule=meta["rule"], rule_row=meta["row"])]}


def _h_escort(para: Para, verb: dict, meta: dict):
    vs, ve = verb["pos"], verb["end"]
    sent = para.sent_of(vs)
    actors = [e for e in para.entities if e["code"] in P_TYPES and sent[0] <= e["pos"] < sent[1]]
    place = nearest_param(para, verb, L_TYPES)
    before = [e for e in actors if e["end"] <= vs]
    after = [e for e in actors if e["pos"] >= ve]
    if not before or not after:
        return {"candidates": [], "drops": [make_drop(
            para, "强制双实体缺失（04f#23 押送须押者+被押者[+讫地]）",
            rule=meta["rule"], rule_row=meta["row"], predicate="押送")]}
    subj = max(before, key=lambda e: e["end"])
    obj = min(after, key=lambda e: e["pos"])
    if subj["canon"] == obj["canon"]:
        return {"candidates": [], "drops": [make_drop(
            para, "自指/主宾同一实体", rule=meta["rule"], rule_row=meta["row"],
            predicate="押送")]}
    return {"candidates": [make_candidate(
        para, "押送", subj, obj, confidence="strong", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"],
        params={"讫地": place["canon"] if place else ""})]}


def _h_fight(para: Para, verb: dict, meta: dict):
    subj, obj, basis = person_pair(para, verb)
    if not (subj and obj):
        if meta.get("extension"):
            return None      # 扩展规则机会式抽取，缺失不计放弃
        return {"candidates": [], "drops": [make_drop(
            para, "实体缺失（04f#26 交手须双方人物角色）", rule=meta["rule"],
            rule_row=meta["row"], predicate="交手")]}
    return {"candidates": [make_candidate(
        para, "交手", subj, obj, confidence=meta.get("conf", "ok"),
        evidence_type="E2动作+共现", rule=meta["rule"], rule_row=meta["row"],
        notes="一次交手不自动敌对（01g 铁律）")]}


def _h_dianxue(para: Para, verb: dict, meta: dict):
    acupoint = None
    for ent in para.entities:
        if ent["code"] == "^" and "穴" in ent["display"]:
            if abs(ent["pos"] - verb["pos"]) <= PARAM_WINDOW:
                acupoint = ent
                break
    if acupoint is None and "穴" not in para.plain:
        return None      # 04f#5 缺失处理：无穴道名 → 回落 ⊞ 事件（X-COMBAT）
    subj, obj, basis = person_pair(para, verb)
    if not (subj and obj):
        return {"candidates": [], "drops": [make_drop(
            para, "实体缺失（04f#5 点穴须施者/受者）", rule=meta["rule"],
            rule_row=meta["row"], predicate="点穴")]}
    return {"candidates": [make_candidate(
        para, "点穴", subj, obj, confidence="ok", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"],
        params={"穴道": acupoint["canon"] if acupoint else ""})]}


def _h_drop_only(para: Para, verb: dict, meta: dict):
    return {"candidates": [], "drops": [make_drop(
        para, meta.get("reason") or "D06 无对应 SPO 谓词", rule=meta["rule"],
        rule_row=meta["row"], predicate="")]}


def _h_baishi_org(para: Para, verb: dict, meta: dict):
    org = nearest_param(para, verb, O_TYPES)
    subj = near_before(para, verb["pos"], P_TYPES)
    if org is None or subj is None:
        return None      # 建议档允许无组织（散修）
    return {"candidates": [make_candidate(
        para, "组织成员", subj, org, confidence="weak", evidence_type="E2动作+共现",
        rule=meta["rule"], rule_row=meta["row"],
        notes="04f#16 拜师→组织（建议档）：弱证据候选，待同门/辈分佐证")]}


# ---------------------------------------------------------------- 规则定义表
def _rule(rule, row, predicate, strength, handler, domains=None, triggers=None,
          match=None, conf=None, mode="", reason="", note="", extension=False):
    return {"rule": rule, "row": row, "predicate": predicate, "strength": strength,
            "handler": handler, "domains": domains, "triggers": triggers,
            "match": match, "conf": conf, "mode": mode, "reason": reason,
            "note": note, "extension": extension}


def _has(words):
    return lambda verb: verb["word"] in words


def _regex(pat):
    rx = re.compile(pat)
    return lambda verb: bool(rx.match(verb["word"]))


SPECIFIC_RULES = [
    _rule("04f-L01", 1, "掌握", "强制", _h_zhangwo, domains={"▣"},
          match=_has({"练成", "学会", "悟出", "练就", "学成"}), conf="strong"),
    _rule("04f-L02", 2, "传授", "强制", _h_chuanshou, domains={"▣"}, match=_has({"传授"})),
    _rule("04f-L03", 3, None, "建议", _h_drop_only, domains={"▣"},
          match=_has({"教", "授艺", "指点", "教授", "传艺", "传功"}),
          reason="建议档泛指授艺（04f#3：记子型‘指点’，不生成三元组）"),
    _rule("04f-L04", 4, "掌握", "强制", _h_zhangwo, domains={"▣"},
          match=_has({"偷学", "窃艺", "偷习"}), conf="strong"),
    _rule("04f-L05", 5, "点穴", "强制", _h_dianxue, domains={"⊞", "⊡"},
          match=_has({"点", "点穴", "点中", "点了", "点着", "点倒"}), conf="ok"),
    _rule("04f-L06", 6, "师承", "强制", _h_bai_shi, domains={"⊡"},
          match=_has({"拜", "拜师", "投师", "求师"})),
    _rule("04f-L07", 7, "师承", "强制", _h_bai_shi, domains={"⊡", "▣"},
          match=lambda v: v["word"] in {"收徒", "收下"} or
          (v["word"] == "收" and "为徒" in v.get("_plain", ""))),
    _rule("04f-L08", 8, "杀害", "强制", _h_kill, domains={"⊠", "⊞"},
          match=_has(KILL_WORDS)),
    _rule("04f-L09", 9, "治愈", "强制", _h_cure, domains={"⊠", "⊡", "⊞"},
          match=_has(CURE_WORDS)),
    _rule("04f-L10", 10, "投毒", "强制", _h_poison, domains={"⊠", "⊟"},
          match=_has(POISON_WORDS)),
    _rule("04f-L11", 11, "转移", "强制", _h_transfer, domains={"⊟", "⊞", "⊡"},
          match=_has(GIVE_WORDS), mode="赠", conf="strong"),
    _rule("04f-L12", 12, "转移", "强制", _h_transfer, domains={"⊟", "⊞"},
          match=_has(TAKE_WORDS), mode="夺", conf="strong"),
    _rule("04f-L13a", 13, "转移", "强制", _h_transfer, domains={"⊟", "⊞", "⊡"},
          match=_has(LEND_WORDS), mode="借", conf="strong"),
    _rule("04f-L13b", 13, "转移", "强制", _h_transfer, domains={"⊟", "⊡"},
          match=_has(RETURN_WORDS), mode="还", conf="strong"),
    _rule("04f-L14", 14, "制造", "强制", _h_manufacture, domains={"⊟", "▣"},
          match=_has(FORGE_WORDS)),
    _rule("04f-L15", 15, None, "强制", _h_destroy, domains={"⊟", "⊞"},
          match=_has(DESTROY_WORDS),
          reason="D06 无『毁损』SPO 谓词（毁弃留事件层 ⊟）"),
    _rule("04f-L16", 16, "组织成员", "建议", _h_baishi_org, domains={"⊡"},
          match=_has({"拜", "拜师", "投师", "求师"})),
    _rule("04f-L17", 17, "任职", "强制", _h_appoint, domains={"⊡"},
          match=_has(APPOINT_WORDS)),
    _rule("04f-L18", 18, "隶属终止", "强制", _h_terminate, domains={"⊡", "⊞"},
          match=_has(EXCLUDE_WORDS)),
    _rule("04f-L19", 19, "结义", "强制", _h_sworn, domains={"⊡"},
          match=_has(SWORN_WORDS)),
    _rule("04f-L20", 20, "配偶", "强制", _h_marry, domains={"⊡"},
          match=_has(MARRY_WORDS)),
    _rule("04f-L21", 21, "到达", "强制", _h_travel, domains={"■"},
          match=_has(ARRIVE_CORE), conf="strong"),
    _rule("04f-L22", 22, "离开", "强制", _h_travel, domains={"■"},
          match=_has(LEAVE_CORE), conf="strong"),
    _rule("04f-L23", 23, "押送", "强制", _h_escort, domains={"■"},
          match=_has(ESCORT_WORDS)),
    _rule("04f-L24", 24, "到达", "强制", _h_travel, domains={"■"},
          match=_has(ENTER_WORDS), conf="weak",
          note="04f『进入』无 D06 同名谓词，按 §7.3 对号入座最近落位 #18 到达（weak）"),
    _rule("04f-L25", 25, None, "建议", _h_drop_only, domains={"■"},
          match=_has(TRACK_WORDS),
          reason="D06 55 谓词无『追踪』（04f#25 建议档），留候选池不落库"),
    _rule("04f-L26", 26, "交手", "建议", _h_fight, domains={"⊞"},
          match=_has(FIGHT_WORDS), conf="ok"),
    _rule("04f-L27", 27, None, "建议", _h_drop_only, domains={"⊞", "▣"},
          match=_has(ARRAY_WORDS),
          reason="D06 无『施用』谓词（04f#27 建议档），留候选池不落库"),
]

EXTENSION_RULES = [
    _rule("X-RESCUE", "X-RESCUE", "解救", "扩展", _h_rescue, domains={"⊠", "⊡", "⊞"},
          match=_has(RESCUE_WORDS), conf="ok", extension=True,
          note="04f#9 只列疗伤/救活/治愈；『救』按 D06#51 解救 候选（E2）"),
    _rule("X-ARRIVE", "X-ARRIVE", "到达", "扩展", _h_travel, domains={"■"},
          match=_has(ARRIVE_EXT - ARRIVE_CORE - ENTER_WORDS), conf="ok", extension=True),
    _rule("X-LEAVE", "X-LEAVE", "离开", "扩展", _h_travel, domains={"■"},
          match=_has(LEAVE_EXT - LEAVE_CORE), conf="ok", extension=True),
    _rule("X-COMBAT", "X-COMBAT", "交手", "扩展", _h_fight, domains={"⊞"},
          match=lambda v: v["word"] not in FIGHT_EXCLUDE, conf="ok", extension=True),
]
ALL_RULES = SPECIFIC_RULES + EXTENSION_RULES


# ---------------------------------------------------------------- 语式规则（D06 §8.4）
def _sentence_actors(para: Para, pos: int) -> list:
    a, b = para.sent_of(pos)
    return sorted((e for e in para.entities
                   if e["code"] in P_TYPES and a <= e["pos"] < b),
                  key=lambda e: e["pos"])


def _cue_pair(para: Para, cue: str):
    """语式命中：返回 (cue 位置, 句内人物列表)。"""
    idx = para.plain.find(cue)
    if idx == -1:
        # plain 与原文长度可能因剥标不同：改在原文定位后折算
        raw_idx = para.text.find(cue)
        if raw_idx == -1:
            return None, []
        idx = raw_idx
    return idx, _sentence_actors(para, idx)


CUE_RULES = []


def _nearest_actors_to(para: Para, pos: int, radius: int = 40, limit: int = 2) -> list:
    """距 pos 最近的（光标半径内、同句）人物实体，按距离取前 limit 个。"""
    seg = para.sent_of(pos)
    cand = [e for e in para.entities
            if e["code"] in P_TYPES and seg[0] <= e["pos"] < seg[1]
            and abs(e["pos"] - pos) <= radius]
    cand.sort(key=lambda e: abs(e["pos"] - pos))
    return sorted(cand[:limit], key=lambda e: e["pos"])


def _actor_before(para: Para, pos: int) -> dict | None:
    return near_before(para, pos, P_TYPES, max_gap=60)


def _actor_after(para: Para, pos: int) -> dict | None:
    found = near_after(para, pos, P_TYPES, max_gap=25, strict_gap=False, clause_only=False)
    return found


def cue_candidates(para: Para) -> dict:
    """§8.4 语式表：高价值明文句式 → 名分关系候选/放弃（叙述者口吻限定）。"""
    out = {"candidates": [], "drops": []}
    qdepth = _quote_depth(para.text)

    def in_quote(idx: int) -> bool:
        return 0 <= idx < len(qdepth) and qdepth[idx] > 0

    def add_pair(predicate, a, b, cue, conf, rule, note="", quoted=False, row="语式"):
        if quoted:
            conf = "weak"
            note = (note + "；对话内自述/转述（§8.3 单方视角，weak，待人工复核）").strip("；")
        out["candidates"].append(make_candidate(
            para, predicate, a, b, confidence=conf, evidence_type="E1明文",
            rule=rule, rule_row=row, subtype=cue, notes=note))

    def cue_idx(cue: str) -> int:
        i = para.plain.find(cue)
        if i == -1 or i >= len(para.plain_map):
            return -1
        return para.plain_map[i]

    def cue_quoted(raw_idx: int) -> bool:
        return in_quote(raw_idx)

    # ---- 结义语式：cue 附近 ±30 内 2~4 人两两成边 ----
    for cue in CUE_SWORN:
        idx = cue_idx(cue)
        if idx == -1:
            continue
        quoted = cue_quoted(idx)
        actors = _nearest_actors_to(para, idx, radius=35, limit=4)
        if len(actors) < 2:
            out["drops"].append(make_drop(
                para, "语式命中但实体不足（结义须≥2 人物）", rule="语式-结义",
                rule_row="语式", predicate="结义", note=cue))
            continue
        for i in range(len(actors)):
            for j in range(i + 1, len(actors)):
                if actors[i]["canon"] != actors[j]["canon"]:
                    add_pair("结义", actors[i], actors[j], cue, "strong", "语式-结义",
                             note=f"语式『{cue}』", quoted=quoted, row=19)
    # ---- 婚约语式 ----
    for cue in CUE_BETROTH:
        idx = cue_idx(cue)
        if idx == -1:
            continue
        quoted = cue_quoted(idx)
        if cue in ("指腹为媒", "结成亲家"):
            out["drops"].append(make_drop(
                para, "婚约双方为下一代（指腹为媒/结成亲家），须亲属边推导；"
                      "本脚本无血缘树，不直接落库（D06 few-shot 甲）",
                rule="语式-婚约", rule_row="语式", predicate="婚约", note=cue))
            continue
        actors = _nearest_actors_to(para, idx, radius=25, limit=2)
        if len(actors) < 2:
            out["drops"].append(make_drop(
                para, "语式命中但实体不足（婚约须双方人物；一方未出场→待实体消歧）",
                rule="语式-婚约", rule_row="语式", predicate="婚约", note=cue))
            continue
        a, b = actors[0], actors[1]
        if a["canon"] != b["canon"]:
            add_pair("婚约", a, b, cue, "weak", "语式-婚约",
                     note=f"语式『{cue}』；近邻配对启发式，待人工复核；"
                          "婚约→配偶状态机（永不自动生成配偶边）", quoted=quoted, row=41)
    # ---- 收养语式 ----
    for cue in CUE_ADOPT:
        idx = cue_idx(cue)
        if idx == -1:
            continue
        quoted = cue_quoted(idx)
        before, after = _actor_before(para, idx), _actor_after(para, idx)
        if not (before and after) or before["canon"] == after["canon"]:
            out["drops"].append(make_drop(
                para, "语式命中但实体不足（收养须养亲+养子）", rule="语式-收养",
                rule_row="语式", predicate="收养", note=cue))
            continue
        add_pair("收养", before, after, cue, "strong", "语式-收养",
                 note=f"语式『{cue}』", quoted=quoted, row=42)
    # ---- 师承语式（D06 §8.4；叙述者口吻=ok，对话/第一人称=weak）----
    # 所属结构核验（possessor）：
    #   a) 紧邻“X 的 + 师父/弟子”；b) “自己的/他的/她的/其”→回指前文角色；
    #   c) “我的/你的”→说话人未知，按前文最近角色弱证据（conf=weak）。
    def _actors_upto(pos: int) -> list:
        return [e for e in para.entities if e["code"] in P_TYPES and e["pos"] < pos]

    def possessor_of(idx: int):
        seg = para.sent_of(idx)
        # a) 紧邻所有格 X 的
        for e in reversed(para.entities):
            if e["code"] not in P_TYPES or e["end"] > idx:
                continue
            gap = para.text[e["end"]:idx]
            if gap == "的" or gap.endswith("的") and len(gap) <= 2:
                return e, "adj"
            if e["end"] < idx - 10:
                break
        suffix = para.text[max(seg[0], idx - 6):idx]
        # b) 自己的 / 他的 / 她的 / 其
        if suffix.endswith("自己") or suffix.endswith("他的") or suffix.endswith("她的") \
                or suffix.endswith("其"):
            actors = [e for e in para.entities
                      if e["code"] in P_TYPES and seg[0] <= e["pos"] < idx]
            if actors:
                return actors[0], "pronoun"
            earlier = _actors_upto(idx)
            return (earlier[-1], "pronoun") if earlier else (None, "")
        # c) 我的 / 你的 → 第一/第二人称，按前文最近角色弱证据
        if suffix.endswith("我的") or suffix.endswith("你的"):
            earlier = _actors_upto(idx)
            return (earlier[-1], "first_person") if earlier else (None, "")
        return None, ""

    master_mark = next((c for c in ("的师父", "的师傅") if c in para.text), None)
    disc_mark = next((c for c in ("的徒弟", "的弟子") if c in para.text), None)
    for mark, is_master in ((master_mark, True), (disc_mark, False)):
        if not mark:
            continue
        idx = cue_idx(mark)
        if idx == -1:
            continue
        quoted = cue_quoted(idx)
        seg = para.sent_of(idx)
        # 系词校验：排除“要是/若是/可是…”等连词，且“是…的X”须同句无标点截断
        shi = para.text.rfind("是", seg[0], idx)
        BAD_SHI = ("要是", "若是", "如是", "似是", "算是", "可是", "但是", "只是",
                   "还是", "怕是", "想必", "倒是")
        while shi != -1:
            pre = para.text[max(seg[0], shi - 1):shi + 1]
            if not any(pre.endswith(w) for w in BAD_SHI):
                break
            shi = para.text.rfind("是", seg[0], shi)
        if shi != -1 and any(ch in CLAUSE_PUNCT or ch in SENT_END
                             for ch in para.text[shi:idx]):
            shi = -1
        after = _actor_after(para, idx + len(mark))
        if after is not None and (after["pos"] - (idx + len(mark))) > 6:
            after = None       # “的师父/弟子”后的直接同位语才作对方
        possessor, basis = possessor_of(idx)
        master = disciple = None
        conf = "ok"
        if is_master:                       # “的师父/的师傅”
            master = after
            disciple = possessor
            if not master and shi >= seg[0]:        # “X 是 Y 的师父”
                master = near_before(para, shi, P_TYPES, max_gap=25)
                cands = [e for e in _actors_upto(idx) if e["pos"] > shi]
                if cands:
                    disciple = cands[-1]
        else:                                # “的徒弟/的弟子”
            disciple = after
            master = possessor
            if shi >= seg[0]:                        # “X 是 Y 的弟子” / “Y 的弟子 X”
                mid = [e for e in para.entities
                       if e["code"] in P_TYPES and shi < e["pos"] < idx]
                if not master and mid:
                    master = mid[-1]
                if not disciple:
                    earlier = [e for e in para.entities
                               if e["code"] in P_TYPES and e["pos"] < shi]
                    disciple = earlier[-1] if earlier else None
        if basis == "first_person":
            conf = "weak"
        if master and disciple and master["canon"] != disciple["canon"]:
            add_pair("师承", disciple, master, mark, conf, "语式-师承",
                     note=f"语式『{mark}』（D06 §8.4；来源={basis or '字面'}）；须拜师实写复核",
                     quoted=quoted, row=6)
    # ---- 明文师承句式（正则：拜…为师 / 收…为徒 / 收徒；E1） ----
    for m in re.finditer(r"拜[^，。！？]{0,10}为师", para.plain):
        start = para.plain_map[m.start()]
        end = para.plain_map[min(m.end(), len(para.plain_map) - 1)]
        quoted = in_quote(start)
        disciple = _actor_before(para, start)
        master = None
        for e in para.entities:
            if start < e["pos"] < end:
                master = e
                break
        if master is None:
            master = _actor_after(para, end)
        if disciple and master and disciple["canon"] != master["canon"]:
            add_pair("师承", disciple, master, "拜…为师", "strong", "语式-拜师",
                     note="明文章式『拜…为师』（E1）", quoted=quoted, row=6)
    # 代词宾语变体：“拜他为师”（master=disciples 之外的最近角色）
    for m in re.finditer(r"拜[他她其你]为(?:师|师父)", para.plain):
        start = para.plain_map[m.start()]
        if in_quote(start):
            continue
    for m in re.finditer(r"拜[他她其你是]?为(?:师|师父)", para.plain):
        start = para.plain_map[m.start()]
        quoted = in_quote(start)
        disciple = _actor_before(para, start)
        if disciple is None:
            continue
        earlier = [e for e in para.entities
                   if e["code"] in P_TYPES and e["pos"] < disciple["pos"]]
        master = earlier[-1] if earlier else None
        if master and master["canon"] != disciple["canon"]:
            add_pair("师承", disciple, master, "拜…为师(代词)", "weak", "语式-拜师",
                     note="代词宾语句式启发式（master=前文最近角色）", quoted=quoted, row=6)
    for m in re.finditer(r"收[^，。！？]{0,8}为(?:徒|弟子)", para.plain):
        start = para.plain_map[m.start()]
        end = para.plain_map[min(m.end(), len(para.plain_map) - 1)]
        quoted = in_quote(start)
        inside = [e for e in para.entities if start < e["pos"] < end]
        disciple = inside[0] if inside else None
        master = None
        if disciple is None:
            # “A 将 B 收为徒”：B 在“收”前、A 在“将”前
            b = _actor_before(para, start)
            seg = para.sent_of(start)
            prefix = para.text[seg[0]:b["pos"]] if b else ""
            j = max(prefix.rfind("将"), prefix.rfind("把"))
            if b and j != -1:
                disciple = b
                master = _actor_before(para, seg[0] + j)
        else:
            # 他收徒 / 明确主语：“收”前 12 字内最近角色
            master = near_before(para, start, P_TYPES, max_gap=12)
        if master and disciple and master["canon"] != disciple["canon"]:
            add_pair("师承", disciple, master, "收…为徒", "strong", "语式-收徒",
                     note="明文章式『收…为徒』（E1；方向=徒→师）", quoted=quoted, row=7)
    # 代词宾语变体：“收他为徒”
    for m in re.finditer(r"收[他她其你][^，。！？]{0,4}为(?:徒|弟子)", para.plain):
        start = para.plain_map[m.start()]
        quoted = in_quote(start)
        master = _actor_before(para, start)
        if master is None:
            continue
        earlier = [e for e in para.entities
                   if e["code"] in P_TYPES and e["pos"] < master["pos"]]
        disciple = earlier[-1] if earlier else None
        if disciple and master["canon"] != disciple["canon"]:
            add_pair("师承", disciple, master, "收…为徒(代词)", "weak", "语式-收徒",
                     note="代词宾语句式启发式（disciple=前文最近角色）", quoted=quoted, row=7)
    for m in re.finditer(r"收徒(?!之念|之想|之意|的念头)", para.plain):
        start = para.plain_map[m.start()]
        end = para.plain_map[min(m.end(), len(para.plain_map) - 1)]
        quoted = in_quote(start)
        master = near_before(para, start, P_TYPES, max_gap=12)
        disciple = _actor_after(para, end)
        if master and disciple and master["canon"] != disciple["canon"]:
            add_pair("师承", disciple, master, "收徒", "ok", "语式-收徒",
                     note="『收徒』明文（E1，方向=徒→师）", quoted=quoted, row=7)
    # ---- 仇怨语式：event_ids 必填 → 只记放弃 ----
    for cue in CUE_FEUD:
        idx = cue_idx(cue)
        if idx == -1 or in_quote(idx):
            continue
        out["drops"].append(make_drop(
            para, "仇怨语式命中但 event_ids 必填（D06#44；事件层 N4/D03 未产出）",
            rule="语式-仇怨", rule_row="语式", predicate="仇怨", note=cue))
        break
    # ---- 恩义语式：离线表（§6.4），不进 SPO ----
    for cue in CUE_GRACE:
        idx = cue_idx(cue)
        if idx == -1 or in_quote(idx):
            continue
        out["drops"].append(make_drop(
            para, "恩义属离线表（D06 §6.4），不进 SPO 关系表",
            rule="语式-恩义", rule_row="语式", predicate="", note=cue))
        break
    return out


# ---------------------------------------------------------------- 抽取主流程
def extract_paragraph(ctx: Ctx, chapter_no: int, para_no: int, text: str,
                      rules: list) -> dict:
    """单段抽取：返回 {candidates, drops, verbs_scanned, verbs_in_quote, entity_counts}。"""
    para = Para(ctx, chapter_no, para_no, text)
    res = {"candidates": [], "drops": [], "verbs_scanned": len(para.verbs),
           "verbs_in_quote": 0, "entities": len(para.entities),
           "rumor": any(w in para.plain for w in RUMOR_WORDS)}
    # 语式扫描（§8.4）：与动词规则独立，先执行（叙述者口吻的明文名分句式可能无六域动词）
    cue_out = cue_candidates(para)
    for c in cue_out["candidates"]:
        c["_rule"] = {"rule": c["rule"], "row": c.get("rule_row", "语式"), "strength": "语式",
                      "predicate": c["predicate"], "extension": False}
        res["candidates"].append(c)
    for d in cue_out["drops"]:
        d["_rule"] = {"rule": d["rule"], "row": "语式", "strength": "语式",
                      "predicate": d["predicate"], "extension": False}
        res["drops"].append(d)
    if not para.verbs:
        return res
    extension_rules = [r for r in rules if r["extension"]]
    specific_rules = [r for r in rules if not r["extension"]]
    for verb in para.verbs:
        verb["_plain"] = para.plain
        if verb["in_quote"]:
            res["verbs_in_quote"] += 1
            continue
        matched = False
        for rule in specific_rules:
            if rule["domains"] is not None and verb["code"] not in rule["domains"]:
                continue
            if not rule["match"](verb):
                continue
            out = rule["handler"](para, verb, rule)
            if out is None:
                continue
            matched = True
            for c in out.get("candidates", []):
                c["_rule"] = rule
                res["candidates"].append(c)
            for d in out.get("drops", []):
                d["_rule"] = rule
                res["drops"].append(d)
        if matched:
            continue
        # 27 行未命中 → 扩展规则（超出 04f 联动表，--strict 下 rules 不含它们）
        for rule in extension_rules:
            if rule["domains"] is not None and verb["code"] not in rule["domains"]:
                continue
            if not rule["match"](verb):
                continue
            out = rule["handler"](para, verb, rule)
            if out is None:
                continue
            for c in out.get("candidates", []):
                c["_rule"] = rule
                res["candidates"].append(c)
            for d in out.get("drops", []):
                d["_rule"] = rule
                res["drops"].append(d)
    return res


def extract_book(book: str, strict: bool = False, only_chapter: int | None = None) -> dict:
    """整书抽取 → 聚合后的结果 dict（内存，不写盘）。"""
    ctx = Ctx(book)
    rules = SPECIFIC_RULES if strict else ALL_RULES
    rows_stats = {r["row"]: {"rule": r["rule"], "predicate": r["predicate"],
                             "triggers": r.get("triggers") or "", "strength": r["strength"],
                             "candidates": 0, "emitted": 0, "dropped": 0,
                             "extension": r["extension"], "note": r.get("note", "")}
                  for r in ALL_RULES}
    for lr in LINKAGE_ROWS:
        st = rows_stats.get(lr["row"])
        if st is not None:
            st["triggers"] = lr["triggers"]
            st["strength"] = lr["strength"]
    for er in EXTENSION_ROWS:
        st = rows_stats.get(er["row"])
        if st is not None:
            st["triggers"] = er["triggers"]
            st["extension"] = True
    row_of = {r["rule"]: r["row"] for r in ALL_RULES}

    chapters = []
    for path in sorted((TAG / book).glob("*.tagged.md")):
        no = int(path.name[:3])
        if only_chapter is not None and no != only_chapter:
            continue
        chapters.append((no, path))

    counters = Counter()
    candidates_all, drops_all = [], []
    chapter_stats = []
    for no, path in chapters:
        paragraphs = _iter_paragraphs(path)
        ch = {"chapter": no, "paragraphs": len(paragraphs), "verbs": 0,
              "verbs_in_quote": 0, "candidates": 0, "drops": 0}
        for para_no, text in paragraphs:
            res = extract_paragraph(ctx, no, para_no, text, rules)
            ch["verbs"] += res["verbs_scanned"]
            ch["verbs_in_quote"] += res["verbs_in_quote"]
            for c in res["candidates"]:
                rule = c["_rule"]
                stats = rows_stats.get(rule["row"])
                if stats is not None:
                    stats["candidates"] += 1
                if res["rumor"]:
                    drops_all.append(_finish_drop(para_of(c), "传闻降权（D06 §8.3，不入正式表）",
                                                  c, rule))
                    if stats is not None:
                        stats["dropped"] += 1
                    continue
                c["_loc"] = (no, para_no)
                c["_row"] = rule["row"]
                candidates_all.append(c)
                ch["candidates"] += 1
            for d in res["drops"]:
                rule = d["_rule"]
                stats = rows_stats.get(rule["row"])
                if stats is not None:
                    stats["dropped"] += 1
                drops_all.append(_normalize_drop(d, book, no, para_no))
                ch["drops"] += 1
            counters["paragraphs"] += 1
            counters["entities"] += res["entities"]
        counters["verbs"] += ch["verbs"]
        counters["verbs_in_quote"] += ch["verbs_in_quote"]
        chapter_stats.append(ch)

    edges, agg_drops = aggregate_candidates(book, candidates_all, strict)
    drops_all.extend(agg_drops)
    # 互为师徒（双向冲突）→ 双双放弃，交人工裁定（D06 §9.3 无环）
    edges, reciprocal = drop_reciprocal_lineage(edges)
    for a, b, loc_ab, loc_ba in reciprocal:
        drops_all.append({"reason": "互为师徒环（D06 §9.3 无环拦截）：双向证据冲突，双放弃待人工裁定",
                          "rule": "语式-师承", "rule_row": "B", "predicate": "师承",
                          "loc": loc_ab,
                          "note": f"{a}→{b}@{loc_ab} / {b}→{a}@{loc_ba}"})
    # 类型/谓词校验（聚合后，派生之前）
    valid_edges, invalid = validate_edges(book, edges)
    for e in invalid:
        drops_all.append({"reason": "主宾类型/谓词表校验不符（D06 §7.2）",
                          "rule": e.get("rule", ""), "rule_row": e.get("rule_row", ""),
                          "predicate": e.get("predicate", ""), "loc": e.get("loc", ""),
                          "note": f"{e['subject']}({e['subject_type']}) -> "
                                  f"{e['object']}({e['object_type']})"})
    # 派生层（基于已校验边）
    derived = derive_relations(book, edges=valid_edges)
    derived["reciprocal_conflicts"] = reciprocal
    for e in derived["tongmen_edges"]:
        valid_edges.append(e)
    edges = valid_edges
    edges.sort(key=lambda e: (-e["count"], e["predicate"], e["subject"], e["object"]))
    for i, e in enumerate(edges):
        e["id"] = f"{book}#R{i + 1:04d}"
    # 规则行统计 emit 数
    for e in valid_edges:
        row = e.get("rule_row")
        if isinstance(row, str) and row in rows_stats:
            rows_stats[row]["emitted"] += 1
            continue
        try:
            row = int(row)
        except (TypeError, ValueError):
            row = None
        if row in rows_stats:
            rows_stats[row]["emitted"] += 1
    # 校验层
    validation = validate_graph(book, valid_edges, derived)
    if strict:
        # 严格门禁：仅 strong/ok，且扩展规则边不进正式表（已在 rules 层禁用，此处兜底）
        valid_edges = [e for e in valid_edges
                       if e["confidence"] in ("strong", "ok") and not e.get("rule", "").startswith("X-")]
    counts = _summarize(book, valid_edges, candidates_all, drops_all, derived)
    return {"book": book, "strict": strict, "only_chapter": only_chapter,
            "chapters": chapter_stats, "counters": counters,
            "edges": valid_edges, "dropped": drops_all, "derived": derived,
            "validation": validation, "rows_stats": rows_stats,
            "counts": counts, "rule_rows": row_of}


def para_of(c: dict) -> Para:
    """候选 → 轻量 Para（只为记录 loc 构造）。"""
    class _P:
        loc = c.get("loc", "")
        chapter = c.get("chapter", 0)
        no = c.get("para", 0)
    return _P()  # type: ignore[return-value]


def _finish_drop(para, reason: str, c: dict, rule: dict) -> dict:
    return {"reason": reason, "rule": rule.get("rule", ""), "rule_row": rule.get("row", ""),
            "predicate": c.get("predicate", ""), "loc": c.get("loc", ""),
            "note": f"{c.get('subject','')} {c.get('predicate','')} {c.get('object','')}"}


def _normalize_drop(d: dict, book: str, chapter: int, para_no: int) -> dict:
    out = {k: d.get(k, "") for k in ("reason", "rule", "rule_row", "predicate", "note")}
    out["loc"] = d.get("loc") or f"{chapter:03d}:{para_no}"
    return out


def _iter_paragraphs(path: Path):
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
        m = PARAGRAPH_RE.match(line)
        if not m:
            continue
        no = int(m.group(1))
        if no == 0:
            continue
        out.append((no, m.group(2)))
    return out


# ---------------------------------------------------------------- 聚合/校验/派生
def aggregate_candidates(book: str, candidates: list, strict: bool) -> tuple:
    """同 (predicate, subject, object, subtype, params) 聚合：证据列表 + count + 最高置信。"""
    agg = {}
    drops = []
    for c in candidates:
        pred = c["predicate"]
        pmeta = PREDICATE_BY_NAME.get(pred)
        if pmeta is None:
            drops.append({"reason": "谓词不在 D06 55 条总表（不得自造谓词，D06 §7.1）",
                          "rule": c.get("rule", ""), "rule_row": c.get("rule_row", ""),
                          "predicate": pred, "loc": c.get("loc", ""),
                          "note": f"rule={c.get('rule','')}"})
            continue
        s, o = c["subject"], c["object"]
        if not s or not o:
            drops.append({"reason": "主宾缺失", "rule": c.get("rule", ""),
                          "rule_row": c.get("rule_row", ""), "predicate": pred,
                          "loc": c.get("loc", "")})
            continue
        if s == o:
            drops.append({"reason": "自指/主宾同一实体", "rule": c.get("rule", ""),
                          "rule_row": c.get("rule_row", ""), "predicate": pred,
                          "loc": c.get("loc", "")})
            continue
        if strict and c.get("rule", "").startswith("X-"):
            continue
        if pmeta["symmetric"]:
            if s <= o:
                st, ot = c["subject_type"], c["object_type"]
            else:
                s, o = o, s
                st, ot = c["object_type"], c["subject_type"]
        else:
            st, ot = c["subject_type"], c["object_type"]
        params = c.get("params") or {}
        subtype_key = c.get("subtype", "") if pred in {"转移", "结义", "任职", "婚约"} else ""
        key = (pred, s, o, subtype_key,
               json.dumps(params, ensure_ascii=False, sort_keys=True) if pred in {"转移"} else "")
        entry = agg.get(key)
        ev = {"loc": c["loc"], "type": c["evidence_type"], "rule": c.get("rule", "")}
        if entry is None:
            agg[key] = {
                "subject": s, "subject_type": st,
                "predicate": pred, "object": o, "object_type": ot,
                "confidence": c["confidence"], "evidence_type": c["evidence_type"],
                "rule": c.get("rule", ""), "rule_row": c.get("rule_row", ""),
                "subtype": c.get("subtype", ""), "params": params,
                "notes": [c.get("notes", "")] if c.get("notes") else [],
                "evidence": [ev], "count": 1, "loc": c["loc"],
                "chapter": c.get("chapter", 0), "para": c.get("para", 0),
                "derived": False, "veracity": "叙述", "books": [book],
            }
        else:
            entry["count"] += 1
            if len(entry["evidence"]) < 30:
                entry["evidence"].append(ev)
            if CONF_RANK[c["confidence"]] > CONF_RANK[entry["confidence"]]:
                entry["confidence"] = c["confidence"]
                entry["evidence_type"] = c["evidence_type"]
            if not entry["subtype"] and c.get("subtype"):
                entry["subtype"] = c["subtype"]
            if c.get("notes") and c["notes"] not in entry["notes"]:
                entry["notes"].append(c["notes"])
    edges = list(agg.values())
    # subject_type 在对称归并时可能互换：按实际实体类型重查（下面 validate 会兜底）
    for e in edges:
        e["notes"] = "；".join(e["notes"])
        e["locs"] = [x["loc"] for x in e["evidence"]]
        e["layer"] = PREDICATE_BY_NAME[e["predicate"]]["layer"]
        e["direction"] = PREDICATE_BY_NAME[e["predicate"]]["direction"]
        e["id"] = ""      # 排序后统一编号
    return edges, drops


def _type_of(name: str, s: str, c: dict) -> str:
    return c["subject_type"] if name == s else c["object_type"]


def drop_reciprocal_lineage(edges: list) -> tuple:
    """互为师徒（A→B 与 B→A）无法裁决：双双向放弃，并交回冲突清单。"""
    lin = {}
    for e in edges:
        if e["predicate"] == "师承":
            lin[(e["subject"], e["object"])] = e
    dropped = []
    for (a, b), e in list(lin.items()):
        if (b, a) in lin:
            dropped.append((a, b, e["loc"], lin[(b, a)]["loc"]))
    pairs = {(a, b) for a, b, _, _ in dropped}
    keep = [e for e in edges
            if not (e["predicate"] == "师承" and (e["subject"], e["object"]) in pairs)]
    return keep, dropped


PERSON_ONLY_PREDS = {
    "师承", "传授", "相爱", "配偶", "婚约", "收养", "亲属", "仇怨", "冒名", "杀害",
    "治愈", "投毒", "拘押", "解救", "押送", "点穴", "同门",
}


def validate_edges(book: str, edges: list) -> tuple:
    good, bad = [], []
    for e in edges:
        pmeta = PREDICATE_BY_NAME.get(e["predicate"])
        if pmeta is None:
            bad.append(e)
            continue
        if e["predicate"] in PERSON_ONLY_PREDS and (
                e["subject_type"] != "@" or e["object_type"] != "@"):
            bad.append(e)
            continue
        st, ot = e["subject_type"], e["object_type"]
        if pmeta["subj_key"] not in ("ANY", "E") and st not in pmeta["subj"]:
            bad.append(e)
            continue
        if pmeta["obj_key"] not in ("ANY", "E") and ot not in pmeta["obj"]:
            bad.append(e)
            continue
        good.append(e)
    for i, e in enumerate(good):
        e["id"] = f"{book}#R{i + 1:04d}"
    return good, bad


def derive_relations(book: str, edges: list) -> dict:
    """双树子集：师承树 + B1 师祖标签 + B2 师叔伯 + B3/B4 同门 + B5 长幼序（全部 derived/weak）。"""
    lineage = [e for e in edges if e["predicate"] == "师承"]
    by_master = defaultdict(list)
    master_of = {}
    for e in lineage:
        disciple, master = e["subject"], e["object"]
        by_master[master].append(disciple)
        master_of.setdefault(disciple, []).append(master)
    # 同门（B3 亲同门）：同师父两两
    tongmen_edges, tongmen_pairs = [], []
    for master, students in sorted(by_master.items()):
        students = sorted(set(students))
        if len(students) < 2:
            continue
        for i in range(len(students)):
            for j in range(i + 1, len(students)):
                a, b = students[i], students[j]
                if a == b:
                    continue
                related_ev = []
                for e in lineage:
                    if e["object"] == master:
                        related_ev.append({"loc": e["loc"], "type": "E3推导",
                                           "rule": "D06#45/B3"})
                        if len(related_ev) >= 3:
                            break
                tongmen_pairs.append({"a": a, "b": b, "master": master,
                                      "rule": "B3", "confidence": "weak"})
                edge = {
                    "subject": min(a, b), "subject_type": "@",
                    "predicate": "同门", "object": max(a, b), "object_type": "@",
                    "confidence": "weak", "evidence_type": "E3推导",
                    "rule": "D06#45/B3", "rule_row": "B3", "subtype": "亲同门",
                    "params": {"共同师父": master},
                    "notes": "推导关系（derived），不直接登记；不传递（R18）",
                    "evidence": related_ev[:3] if related_ev else
                    [{"loc": lineage[0]["loc"] if lineage else "", "type": "E3推导",
                      "rule": "D06#45/B3"}],
                    "count": 1, "loc": (related_ev[0]["loc"] if related_ev else
                                        (lineage[0]["loc"] if lineage else "")),
                    "chapter": 0, "para": 0, "derived": True, "veracity": "推导",
                    "books": [book], "layer": "人", "direction": "↔", "locs": [],
                    "id": "",
                }
                edge["locs"] = [x["loc"] for x in edge["evidence"]]
                tongmen_edges.append(edge)
    # B1 师祖标签 + B2 师叔伯标签 + B5 长幼序
    labels = []
    for d, masters in sorted(master_of.items()):
        for m in masters:
            for gm in master_of.get(m, []):
                labels.append({"kind": "辈分", "person": d, "value": "师祖",
                               "relative_to": gm, "chain": [d, m, gm], "rule": "B1",
                               "confidence": "weak"})
    for e in lineage:
        disciple, master = e["subject"], e["object"]
        masters_siblings = [p for p in by_master
                            if p != master and master in by_master[p]]
        # master 的同门 = 与 master 同师父者（需要 master 自身师承）
        if master in master_of:
            for teacher in master_of[master]:
                for sibling in by_master.get(teacher, []):
                    if sibling != master:
                        labels.append({"kind": "辈分", "person": disciple,
                                       "value": "师叔伯（性别未判）",
                                       "relative_to": sibling, "rule": "B2",
                                       "confidence": "weak"})
    for master, students in sorted(by_master.items()):
        ordered = []
        for st in sorted(set(students)):
            locs = [e["loc"] for e in lineage if e["subject"] == st and e["object"] == master]
            ordered.append((locs[0] if locs else "", st))
        ordered.sort()
        for prev, nxt in zip(ordered, ordered[1:]):
            labels.append({"kind": "长幼", "person": prev[1], "value": "师兄/姐（按拜师定位符时序）",
                           "relative_to": nxt[1], "rule": "B5", "confidence": "weak",
                           "basis": "拜师定位符时序，性别未判"})
    # 师承树
    nodes, roots = [], sorted(set(m for m in by_master) - set(master_of))
    gen = {}
    # 简化 BFS：从 roots 向下
    children = defaultdict(list)
    for e in lineage:
        children[e["object"]].append(e["subject"])
    queue = [(r, 0) for r in roots]
    while queue:
        person, g = queue.pop(0)
        if person in gen:
            continue
        gen[person] = g
        for child in sorted(children.get(person, [])):
            queue.append((child, g + 1))
    for person in sorted(set(list(gen) + list(master_of))):
        masters = master_of.get(person, [])
        nodes.append({"person": person, "master": masters[0] if masters else "",
                      "generation": gen.get(person), "status": "active",
                      "note": "师承树为 derived 视图（D06 §5.1/§5.2）"})
    cycles = detect_cycles(lineage)
    # B2 去重
    seen = set()
    uniq_labels = []
    for lb in labels:
        key = (lb["kind"], lb["person"], lb["relative_to"], lb["rule"])
        if key in seen:
            continue
        seen.add(key)
        uniq_labels.append(lb)
    return {"tongmen_edges": tongmen_edges, "tongmen_pairs": tongmen_pairs,
            "lineage_labels": uniq_labels,
            "trees": {"master_tree": {"nodes": nodes, "roots": roots,
                                      "edge_count": len(lineage)},
                      "blood_tree": {"nodes": [], "note": "亲属/血缘抽取不在 04f 27 行联动内，"
                                                         "留候选池待语式扩展（本脚本不产出）"}},
            "cycles": cycles}


def detect_cycles(lineage_edges: list) -> list:
    adj = defaultdict(list)
    for e in lineage_edges:
        adj[e["subject"]].append(e["object"])
    WHITE, GRAY, BLACK = 0, 1, 2
    color = defaultdict(int)
    cycles = []
    stack = []

    def dfs(u):
        color[u] = GRAY
        stack.append(u)
        for v in adj.get(u, []):
            if color[v] == GRAY:
                try:
                    i = stack.index(v)
                    cycles.append(stack[i:] + [v])
                except ValueError:
                    cycles.append([v, u])
            elif color[v] == WHITE:
                dfs(v)
        stack.pop()
        color[u] = BLACK

    for node in sorted(adj):
        if color[node] == WHITE:
            dfs(node)
    return cycles


def _summarize(book: str, edges: list, candidates: list, drops: list, derived: dict) -> dict:
    by_pred = Counter(e["predicate"] for e in edges)
    by_conf = Counter(e["confidence"] for e in edges)
    by_layer = Counter(e["layer"] for e in edges)
    by_rule = Counter(e["rule"] for e in edges)
    drop_by_reason = Counter(d["reason"] for d in drops)
    return {
        "candidates": len(candidates),
        "edges": len(edges),
        "dropped": len(drops),
        "derived_edges": sum(1 for e in edges if e.get("derived")),
        "tongmen_edges": len(derived["tongmen_edges"]),
        "lineage_labels": len(derived["lineage_labels"]),
        "by_predicate": dict(by_pred),
        "by_confidence": dict(by_conf),
        "by_layer": dict(by_layer),
        "by_rule": dict(by_rule),
        "drop_by_reason": dict(drop_by_reason),
    }


def validate_graph(book: str, edges: list, derived: dict) -> dict:
    hard, warnings = [], []
    # 师承环（互为师徒弟已在聚合后消解；残留环=硬伤）
    for cyc in derived.get("cycles") or []:
        hard.append({"check": "无环", "rule": "D06 §9.3", "detail": "师承环：" + " → ".join(cyc)})
    # 互为师徒 / 自指 / 类型（类型已在 validate_edges 过滤）
    lin = [(e["subject"], e["object"]) for e in edges if e["predicate"] == "师承"]
    lin_set = set(lin)
    for a, b in lin:
        if (b, a) in lin_set:
            hard.append({"check": "方向", "rule": "D06 #35",
                         "detail": f"互为师徒环：{a} ⇄ {b}"})
    # 师承 / 隶属终止 时序（定位符级）
    term = [e for e in edges if e["predicate"] == "隶属终止"]

    def loc_key(loc: str):
        try:
            a, b = loc.split(":")
            return (int(a), int(b))
        except Exception:
            return (9999, 9999)

    for e in edges:
        if e["predicate"] != "师承":
            continue
        for t in term:
            if t["subject"] == e["subject"] and loc_key(t["loc"]) < loc_key(e["loc"]):
                warnings.append({"check": "时序", "rule": "D06 #35",
                                 "detail": f"{e['subject']} 的『叛出/逐出』({t['loc']}) 早于拜师"
                                           f"({e['loc']})，须人工复核"})
    # 一人多师（互斥待审：N4 时间轴未上线无法判 active）
    masters = defaultdict(list)
    for e in edges:
        if e["predicate"] == "师承":
            masters[e["subject"]].append(e["object"])
    for person, ms in masters.items():
        if len(set(ms)) > 1:
            warnings.append({"check": "互斥", "rule": "D06 §4.2",
                             "detail": f"{person} 存在 {len(set(ms))} 位师父 "
                                       f"{sorted(set(ms))}，active 唯一性须 N4 时间轴复核"})
    # 交手 → 不自动敌对（拦截计数）
    fight_pairs = {(e["subject"], e["object"]) for e in edges if e["predicate"] == "交手"}
    hostiles = {(e["subject"], e["object"]) for e in edges if e["predicate"] == "敌对"}
    auto_hostile = fight_pairs & hostiles
    for a, b in sorted(auto_hostile):
        hard.append({"check": "共现生边", "rule": "01g 铁律/D06 R2",
                     "detail": f"交手对 {a}↔{b} 同时存在敌对边，若无明文须拦截"})
    # 名分类 E1 复核
    for e in edges:
        if e["predicate"] in NAME_RELATIONS and e["evidence_type"] != "E1明文":
            hard.append({"check": "证据", "rule": "D06 §8.1 E2 限制",
                         "detail": f"名分类 {e['predicate']}（{e['subject']}→{e['object']}）"
                                   f"证据级={e['evidence_type']}，非 E1 明文"})
    for a, b, loc_ab, loc_ba in derived.get("reciprocal_conflicts") or []:
        warnings.append({"check": "无环(已消解)", "rule": "D06 §9.3",
                         "detail": f"互为师徒对 {a} ⇄ {b}（{loc_ab}/{loc_ba}）双放弃，待人工裁定"})
    return {"hard_errors": hard, "warnings": warnings[:200],
            "checks": ["无环(师承)", "方向(徒→师/无互为师徒)", "类型(55 谓词主宾)",
                       "证据级(E1 名分类)", "自指", "传闻(§8.3)", "共现生边(交手≠敌对)",
                       "时序(师承 vs 隶属终止, 定位符级)"],
            "pending": ["N4 时间轴未上线：active 互斥（配偶唯一/师承唯一）无法按时段判定，"
                        "只做定位符级提示", "亲属/血缘树：04f 27 行联动无亲属触发词，未产出",
                        "仇怨：event_ids 必填（D06#44）而事件层 N4/D03 未产出"]}


# ---------------------------------------------------------------- 报告
def graph_projection(edges: list) -> dict:
    nodes = {}
    for e in edges:
        for name, typ in ((e["subject"], e["subject_type"]), (e["object"], e["object_type"])):
            if not name:
                continue
            n = nodes.setdefault(name, {"id": name, "type": typ, "n": 0, "books": set()})
            n["n"] += 1
            n["books"].add(e["books"][0] if e.get("books") else "")
    return {"nodes": len(nodes), "edges": len(edges),
            "node_types": dict(Counter(n["type"] for n in nodes.values()))}


def old_kb_relations(book: str) -> dict | None:
    path = LEGACY_KB / book / "关系表.json"
    if not path.exists():
        return None
    data = read_json(path)
    rels = data.get("relations") or []
    return {"path": str(path), "count": len(rels),
            "predicates": dict(Counter(r.get("predicate") or r.get("pred") for r in rels)),
            "schema": (data.get("meta") or {}).get("schema", "")}


def render_report(payload: dict) -> str:
    book = payload["book"]
    counts = payload["counts"]
    rows = payload.get("rows_stats") or {}
    rows = {str(k): v for k, v in rows.items()}
    old = old_kb_relations(book)
    gp = graph_projection(payload["edges"])
    lines = [
        f"# N5 关系核验报告 · {book}",
        "",
        f"- 生成：{payload['generated']} · 脚本：relation_validator.py v{SCRIPT_VERSION}",
        f"- 规范：{PREDICATE_TABLE_VERSION}（55 谓词）+ SKILL_04f 联动总表 27 行 + SKILL_04a 事件字段",
        f"- 模式：{'strict（仅 27 行规则 + strong/ok）' if payload.get('strict') else '默认（含扩展规则）'}",
        f"- 输入快照：tagged {payload['snapshot']['tagged_chapters']} 回 / concordance "
        f"{payload['snapshot']['concordance_generated'] or '缺'} / registry entities "
        f"{payload['snapshot']['registry_entities']} 条",
        "",
        "## 1 · 候选与落库",
        "",
        "| 项 | 数 |",
        "|---|---:|",
        f"| 扫描段落 | {payload['snapshot']['paragraphs']} |",
        f"| 扫描动词 | {payload['snapshot']['verbs']}（对话内跳过 {payload['snapshot']['verbs_in_quote']}） |",
        f"| 联动候选 | {counts['candidates']} |",
        f"| 落库 edges | {counts['edges']} |",
        f"| 放弃候选 | {counts['dropped']} |",
        f"| 其中派生（同门） | {counts['derived_edges']} |",
        f"| 辈分/长幼标签 | {counts['lineage_labels']} |",
        f"| 置信分布 | strong={counts['by_confidence'].get('strong', 0)} · "
        f"ok={counts['by_confidence'].get('ok', 0)} · weak={counts['by_confidence'].get('weak', 0)} |",
        "",
        "## 2 · 谓词分布（落库 edges）",
        "",
        "| 谓词 | 层 | 边数 | 置信 | 规则 |",
        "|---|---|---:|---|---|",
    ]
    for pred, n in sorted(counts["by_predicate"].items(), key=lambda kv: -kv[1]):
        pmeta = PREDICATE_BY_NAME.get(pred, {})
        confs = Counter(e["confidence"] for e in payload["edges"] if e["predicate"] == pred)
        rules = sorted({e["rule"] for e in payload["edges"] if e["predicate"] == pred})
        lines.append(f"| {pred} | {pmeta.get('layer','')} | {n} | "
                     f"{dict(confs)} | {', '.join(rules)} |")
    lines += ["", "## 3 · 04f 联动总表 27 行覆盖", "",
              "| 行 | 触发词 | 建议谓词 | 候选 | 落库 | 放弃 | 状态 |",
              "|---:|---|---|---:|---:|---:|---|"]
    for row in [r["row"] for r in LINKAGE_ROWS]:
        st = rows.get(str(row), {})
        pred = st.get("predicate") or "—"
        status = ("已落库" if st.get("emitted") else
                  ("无对应 SPO（不落库）" if st.get("predicate") is None else "无候选/待审"))
        if st.get("extension"):
            status = "扩展规则"
        lines.append(f"| {row} | {st.get('triggers','')} | {pred} | "
                     f"{st.get('candidates',0)} | {st.get('emitted',0)} | "
                     f"{st.get('dropped',0)} | {status} |")
    ext = [r for r in rows.values() if r.get("extension")]
    if ext:
        lines += ["", "扩展规则（超出 27 行；--strict 禁用）：", ""]
        lines += ["| 规则 | 触发口径 | 谓词 | 候选 | 落库 |",
                  "|---|---|---|---:|---:|"]
        for st in ext:
            lines.append(f"| {st['rule']} | {st.get('triggers','')} | {st['predicate']} | "
                         f"{st.get('candidates',0)} | {st.get('emitted',0)} |")
    lines += ["", "## 4 · 放弃原因", "",
              "| 原因 | 数 |", "|---|---:|"]
    for reason, n in sorted(counts["drop_by_reason"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {reason} | {n} |")
    samples = payload.get("dropped", {}).get("samples") or []
    if samples:
        lines += ["", "放弃样本（≤20）：", ""]
        for s in samples[:20]:
            lines.append(f"- `{s['loc']}` {s['reason']} "
                         f"[{s.get('rule','')}] {s.get('note','')}")
    lines += ["", "## 5 · 校验（D06 §9.3 子集）", ""]
    v = payload["validation"]
    lines += [f"- hard_errors：**{len(v['hard_errors'])}**（strict 模式下非 0 即失败）"]
    for h in v["hard_errors"][:20]:
        lines.append(f"  - [{h['check']}] {h['detail']}")
    lines += [f"- warnings：{len(v['warnings'])}（N4 时间轴未上线，互斥/时序只做定位符级提示）"]
    for w in v["warnings"][:10]:
        lines.append(f"  - [{w['check']}] {w['detail']}")
    lines += ["- 已执行检查：" + "、".join(v["checks"]),
              "- 待上游：" + "；".join(v["pending"]), ""]
    lines += ["## 6 · 派生层（双树子集，全部 derived=true / weak）", ""]
    trees = payload["derived"]["trees"]
    mt = trees["master_tree"]
    lines += [f"- 师承树：{mt['edge_count']} 条边 / {len(mt['nodes'])} 节点 / 根 {mt['roots']}",
              f"- 同门（B3/B4 子集）：{counts['by_predicate'].get('同门', 0)} 条派生边",
              f"- 辈分标签（B1 师祖/B2 师叔伯/B5 长幼）：{counts['lineage_labels']} 条",
              f"- 血缘树：{trees['blood_tree']['note']}",
              f"- 环检测：{'未发现' if not payload['derived'].get('cycles') else payload['derived']['cycles']}",
              ""]
    if mt["nodes"]:
        lines += ["师承树节点（示例 ≤30）：", ""]
        for n in mt["nodes"][:30]:
            lines.append(f"- {n['person']} ← 师 {n['master'] or '（根）'} "
                         f"（第 {n['generation']} 代）")
        lines.append("")
    lines += ["## 7 · 与旧 kb 关系表对照", ""]
    if old:
        lines += [f"- 旧表：`kb/{book}/关系表.json`（schema {old['schema']}）· {old['count']} 条",
                  f"- 旧谓词分布：{old['predicates']}",
                  "- 对位说明：旧 7 类中仅 `修习`/`传授`/`别名→异名` 可直接落 D06 谓词总表；"
                  "`拥有`/`镇山`/`独门`/`创制` 属旧武功考订语义，D06 无同名谓词（旧表只读保留，不合并）。",
                  "- 本导出为**事件/动作候选**（tagged 现算），旧表为**武功考订聚合**（人工/LLM 校订），"
                  "两表口径不同，边数不可直接相减。"]
    else:
        lines.append("- 旧 kb 无本书关系表（未点亮书），无对照基线。")
    lines += ["", "## 8 · 与 EX-4 `graph.json` 导出对接字段映射", "",
              "| registry/relations | site/data/graph.json | 说明 |",
              "|---|---|---|",
              "| `edges[].subject` / `.object` | `edges[].s` / `.t` | 对称谓词先按规范名序归一（配偶/结义/交手/同门） |",
              "| `edges[].predicate` | `edges[].kind` | 55 谓词总表即 kind 白名单（不另造名） |",
              "| `edges[].count` | `edges[].n` | 聚合重复证据数 |",
              "| `edges[].subtype` / `params` | `edges[].label` | 如 `赠`/`夺`/`武功=xxx`/`讫地=xxx` |",
              "| `edges[].evidence[].loc` | `edges[].locs` | 格式 `书·NNN:段`，EX-4 保留 ≤3 条 |",
              "| `edges[].books` | `edges[].books` | 跨书同 canonical 合并时取并集 |",
              "| `edges[].subject_type`/`.object_type` | `nodes[].type` | 节点类型符号（@/◆/☆/•/=/;） |",
              "| 端点 canonical | `nodes[].id` | 节点 id=规范名；`n` 由 concordance 实体频次提供 |",
              "| `derived.tongmen_edges` | `edges[].kind=同门` | derived=true 可作 label 标记 |",
              "| `derived.lineage_labels` | 节点/档案附注（**不生成边**） | B1 规定辈分只出标签不出边 |",
              "",
              f"- 本报告可投影 graph.json 规模：nodes={gp['nodes']}（{gp['node_types']}）/ "
              f"edges={gp['edges']}（当书单书口径；EX-4 跨书合并后节点数会减少）。",
              "- JSON 顶层另含 `edge_schema`（9 个必需字段/置信/证据三级枚举）与 "
              "`offline_interface`（D06 §6.2 情感/恩义/背叛/主仆四类离线表接口声明，N5 不写），"
              "EX-4/N10 可直接按声明消费。", ""]
    lines += ["## 9 · 遗留与已知限制", "",
              "1. 无事件层（N4/D03 未产出）：destroy/track/array 等无 D06 SPO 的候选只记放弃原因；"
              "仇怨 event_ids 必填无法满足。",
              "2. 无时间轴（N4 未上线）：active 互斥/时序只做定位符级提示，不做区间判定。",
              "3. 语义角色核验为规则+近邻启发式（被动句已做施受翻转）；建议下游按 confidence 门控"
              "（strong 直出 / ok 抽检 / weak 仅候选池）。",
              "4. 事件动词与实体均为 tagged 快照现算；并发会话若更新 tagged/registry，重跑即可。",
              "5. 亲属/血缘树未产出（04f 27 行联动无亲属触发词）。", ""]
    return "\n".join(lines)


def render_summary(payloads: list) -> str:
    lines = ["# N5 关系核验 · 5 书汇总（relation_validator.py）", "",
             f"- 生成：{today()} · 规范：{PREDICATE_TABLE_VERSION} · schema：{SCHEMA}",
             f"- 书：{[p['book'] for p in payloads]}", "",
             "| 书 | 回 | 候选 | 落库 | 派生 | 放弃 | strong | ok | weak | 主要谓词 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    tot = Counter()
    pred_tot = Counter()
    for p in payloads:
        c = p["counts"]
        for k in ("candidates", "edges", "dropped", "derived_edges"):
            tot[k] += c[k]
        for k, v in c["by_confidence"].items():
            tot["conf_" + k] += v
        pred_tot.update(c["by_predicate"])
        top = "、".join(f"{k}×{v}" for k, v in sorted(c["by_predicate"].items(),
                                                       key=lambda kv: -kv[1])[:6])
        lines.append(f"| {p['book']} | {p['snapshot']['tagged_chapters']} | {c['candidates']} | "
                     f"{c['edges']} | {c['derived_edges']} | {c['dropped']} | "
                     f"{c['by_confidence'].get('strong',0)} | {c['by_confidence'].get('ok',0)} | "
                     f"{c['by_confidence'].get('weak',0)} | {top} |")
    lines += ["", f"- **合计**：候选 {tot['candidates']} / 落库 {tot['edges']} / "
                  f"派生 {tot['derived_edges']} / 放弃 {tot['dropped']}；"
                  f"置信 strong={tot['conf_strong']} · ok={tot['conf_ok']} · weak={tot['conf_weak']}",
              f"- **谓词分布（全 5 书）**：{dict(sorted(pred_tot.items(), key=lambda kv: -kv[1]))}",
              "", "## 各书报告", ""]
    lines += [f"- `logs/relations/{p['book']}.md`（edges → `registry/relations/{p['book']}.json`）"
              for p in payloads]
    lines += ["", "## EX-4 graph.json 对接（全局）", "",
              "- 边 kind ← `predicate`（D06 55 谓词白名单）；n ← `count`；locs ← `evidence[].loc`；"
              "label ← subtype/params；books ← `books`；nodes.type ← `subject_type/object_type`；"
              "同门派生边可带 derived 标记；辈分标签不进边。",
              "- 跨书同 canonical 合并（registry 已做唯一别名归一）后，EX-4 负责节点去重与 books 并集。", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- 写盘
def snapshot_block(book: str) -> dict:
    conc = CONCORDANCE / f"{book}.json"
    conc_generated = None
    if conc.exists():
        conc_generated = (read_json(conc).get("generated"))
    chapters = len(list((TAG / book).glob("*.tagged.md")))
    reg_path = REG / "entities.json"
    reg_n = len((read_json(reg_path).get("entities") or [])) if reg_path.exists() else 0
    return {"exported_at": now_iso(), "tagged_chapters": chapters,
            "concordance_generated": conc_generated, "registry_entities": reg_n,
            "corpus_chapters": len(list((CORPUS / book).glob("*.txt"))) if (CORPUS / book).is_dir() else 0}


def dropped_summary(drops: list) -> dict:
    by_reason = Counter(d["reason"] for d in drops)
    samples = drops[:100]
    return {"total": len(drops), "by_reason": dict(by_reason), "samples": samples}


def build_payload(book: str, result: dict) -> dict:
    counts = dict(result["counts"])
    payload = {
        "book": book,
        "generated": today(),
        "generated_at": now_iso(),
        "script": "scripts/relation_validator.py",
        "script_version": SCRIPT_VERSION,
        "spec_version": SPEC_VERSION,
        "schema": SCHEMA,
        "mode": "strict" if result["strict"] else "default",
        "source": SOURCE_LIST,
        "snapshot": {**result.get("snapshot", {}), **snapshot_block(book),
                     "paragraphs": result["counters"]["paragraphs"],
                     "verbs": result["counters"]["verbs"],
                     "verbs_in_quote": result["counters"]["verbs_in_quote"],
                     "entities": result["counters"]["entities"]},
        "predicate_table": {"version": PREDICATE_TABLE_VERSION, "count": len(PREDICATES),
                            "used": sorted(counts["by_predicate"])},
        "edge_schema": {
            "required": ["subject", "predicate", "object", "subject_type", "object_type",
                         "confidence", "loc", "evidence", "rule"],
            "confidence_values": ["strong", "ok", "weak"],
            "subject_type": "标注层实体符号（@人物/◆组织/&家族/☆武功/•器物/=/地点/;职衔）",
            "evidence": {"fields": ["loc", "type", "rule"],
                         "type_values": ["E1明文", "E2动作+共现", "E3推导"]},
            "loc_format": "NNN:段（回号:PN 段号）",
            "source": "D06 §7.2 谓词总表 / §8.1 证据三级 / §6.2 离线表 schema",
        },
        "offline_interface": {
            "types": ["情感", "恩义", "背叛", "主仆"],
            "schema": "D06 §6.2（rel_id/subject/object/type/subtype/direction/states/manner/conf/evidence/event_ids/related_predicates/notes）",
            "emitted": [],
            "note": "四类离线关系行内不设符号（01g 铁律）；本脚本只出放弃原因（治愈/转移→恩义候选、"
                    "隶属终止→背叛候选等），离线表由人工裁定流程维护，N5 不写。",
        },
        "counts": counts,
        "edges": [dict(e) for e in result["edges"]],
        "derived": result["derived"],
        "dropped": dropped_summary(result["dropped"]),
        "validation": result["validation"],
        "rows_stats": {str(k): v for k, v in result["rows_stats"].items()},
    }
    return payload


def write_book(book: str, strict: bool = False, only_chapter: int | None = None) -> dict:
    result = extract_book(book, strict=strict, only_chapter=only_chapter)
    result["snapshot"] = {}
    payload = build_payload(book, result)
    payload["snapshot"].update({"tagged_chapters": snapshot_block(book)["tagged_chapters"]})
    counts = payload["counts"]
    # 重新计算谓词分布（占位计算已由 summarize 提供，这里确保无残留）
    if not counts.get("by_predicate"):
        counts["by_predicate"] = dict(Counter(e["predicate"] for e in payload["edges"]))
    if only_chapter is not None:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        json_path = DEBUG_DIR / f"{book}_{only_chapter:03d}.json"
        md_path = DEBUG_DIR / f"{book}_{only_chapter:03d}.md"
        write_json(payload, json_path)
        write_text(render_report(payload), md_path)
        print(f"[N5] 单回调试 → {json_path}")
        print(f"[N5] 单回调试报告 → {md_path}")
        return payload
    OUT_REL.mkdir(parents=True, exist_ok=True)
    LOGS_REL.mkdir(parents=True, exist_ok=True)
    json_path = write_json(payload, OUT_REL / f"{book}.json")
    md_path = write_text(render_report(payload), LOGS_REL / f"{book}.md")
    print(f"[N5] {book}: tagged {payload['snapshot']['tagged_chapters']} 回 · "
          f"候选 {counts['candidates']} → edges {counts['edges']} "
          f"(strong {counts['by_confidence'].get('strong',0)}/ok "
          f"{counts['by_confidence'].get('ok',0)}/weak "
          f"{counts['by_confidence'].get('weak',0)}) · 放弃 {counts['dropped']} · "
          f"派生 {counts['derived_edges']}")
    print(f"[N5]   → {json_path}")
    print(f"[N5]   → {md_path}")
    return payload


# ---------------------------------------------------------------- 自检
def selftest() -> int:
    """内置断言：规范表完整性 + 抽取/聚合/派生/无环/幂等。"""
    checks = []

    def chk(name, cond, detail=""):
        checks.append({"name": name, "ok": bool(cond), "detail": str(detail)})
        print(("  ✓ " if cond else "  ✗ ") + name + (f"  {detail}" if detail and not cond else ""))

    chk("D06 谓词总表 = 55 条", len(PREDICATES) == 55, len(PREDICATES))
    names = [p["name"] for p in PREDICATES]
    chk("谓词名唯一", len(names) == len(set(names)))
    chk("04f 联动总表 = 27 行", len(LINKAGE_ROWS) == 27, len(LINKAGE_ROWS))
    chk("04f 已用谓词全部在 D06 总表",
        all(r["predicate"] in PREDICATE_BY_NAME for r in LINKAGE_ROWS if r["predicate"]))
    chk("04f 已用名零改名（师承/结义/配偶/任职/隶属终止/杀害/治愈/投毒/转移/押送/交手/点穴/掌握/传授/到达/离开）",
        all(n in PREDICATE_BY_NAME for n in
            ["师承", "结义", "配偶", "任职", "隶属终止", "杀害", "治愈", "投毒", "转移",
             "押送", "交手", "点穴", "掌握", "传授", "到达", "离开"]))
    chk("名分类关系 ⊆ 师承/结义/配偶/婚约/收养",
        NAME_RELATIONS == {"师承", "结义", "配偶", "婚约", "收养"})
    # 合成文本抽取
    ctx = Ctx("白发魔女传")
    syn = [
        ("〖@练霓裳〗⟦⊠杀⟧〖@卓一航〗。", "杀害"),
        ("〖@紫阳道长〗将〖@卓一航〗⟦⊡收⟧为徒。", "师承"),
        ("〖@卓一航〗⟦▣练成⟧〖☆天山剑法〗。", "掌握"),
        ("〖@王嘉胤〗与〖@孟灿〗⟦⊡结拜⟧为兄弟。", "结义"),
        ("〖@凌未风〗⟦⊞刺⟧〖@楚昭南〗。", "交手"),
        ("〖@练霓裳〗⟦■离开⟧〖=天山〗。", "离开"),
        ("〖@桂华生〗⟦⊟铸⟧成〖•冰魄寒光剑〗。", "制造"),
    ]
    for text, want in syn:
        res = extract_paragraph(ctx, 1, 1, text, ALL_RULES)
        got = {c["predicate"] for c in res["candidates"]}
        chk(f"抽取：{want}（{text}）", want in got, f"got={got}")
    # A—V—B 邻近规则：无相邻人物 → 不产边
    res = extract_paragraph(ctx, 1, 1, "他⟦⊞刺⟧出一剑，没有人。", ALL_RULES)
    chk("无相邻人物 → 不产交手边",
        not any(c["predicate"] == "交手" for c in res["candidates"]))
    # 对话内跳过
    res = extract_paragraph(ctx, 1, 1, "他说：“〖@练霓裳〗⟦⊠杀⟧了〖@卓一航〗。”", ALL_RULES)
    chk("对话内事件跳过（§8.3）", not any(c["predicate"] == "杀害" for c in res["candidates"]))
    # 传闻降权由 extract_book 层处理，直接验证词表存在
    chk("传闻信号词表非空", len(RUMOR_WORDS) >= 5)
    # 聚合：对称谓词两向归一
    cands = []
    para = Para(ctx, 1, 1, "")
    e1 = make_candidate(para, "交手", {"canon": "A", "code": "@"}, {"canon": "B", "code": "@"},
                        confidence="ok", evidence_type="E2动作+共现", rule="R", rule_row="X",
                        subject={"canon": "A", "code": "@"}, object_={"canon": "B", "code": "@"})
    e2 = dict(e1, subject="B", object="A")
    for c in (e1, e2):
        c["_loc"] = (1, 1)
        c["_row"] = "X"
    edges, _ = aggregate_candidates("测试书", [e1, e2], False)
    chk("对称谓词 A-B/B-A 聚合为 1 条", len(edges) == 1, len(edges))
    chk("对称归一后 subject<object", edges[0]["subject"] == "A" and edges[0]["object"] == "B")
    # 无环检测
    fake = [{"subject": "A", "object": "B", "loc": "001:1"},
            {"subject": "B", "object": "A", "loc": "001:2"}]
    chk("师承环检测", bool(detect_cycles(fake)))
    fake2 = [{"subject": "A", "object": "B", "loc": "001:1"},
             {"subject": "B", "object": "C", "loc": "001:2"}]
    chk("师承 DAG 不误报", not detect_cycles(fake2))
    # 双树/辈分推导（合成 师承 边：D→A→B、C→B）
    fake_edges = [
        {"subject": "A", "subject_type": "@", "predicate": "师承", "object": "B",
         "object_type": "@", "confidence": "ok", "evidence_type": "E1明文", "rule": "R",
         "rule_row": "6", "subtype": "", "params": {}, "notes": "", "evidence": [{"loc": "001:1", "type": "E1明文", "rule": "R"}],
         "count": 1, "loc": "001:1", "chapter": 1, "para": 1, "derived": False,
         "veracity": "叙述", "books": ["测试书"], "layer": "人", "direction": "→", "locs": ["001:1"], "id": ""},
        {"subject": "C", "subject_type": "@", "predicate": "师承", "object": "B",
         "object_type": "@", "confidence": "ok", "evidence_type": "E1明文", "rule": "R",
         "rule_row": "6", "subtype": "", "params": {}, "notes": "", "evidence": [{"loc": "001:2", "type": "E1明文", "rule": "R"}],
         "count": 1, "loc": "001:2", "chapter": 1, "para": 2, "derived": False,
         "veracity": "叙述", "books": ["测试书"], "layer": "人", "direction": "→", "locs": ["001:2"], "id": ""},
        {"subject": "D", "subject_type": "@", "predicate": "师承", "object": "A",
         "object_type": "@", "confidence": "ok", "evidence_type": "E1明文", "rule": "R",
         "rule_row": "6", "subtype": "", "params": {}, "notes": "", "evidence": [{"loc": "001:3", "type": "E1明文", "rule": "R"}],
         "count": 1, "loc": "001:3", "chapter": 1, "para": 3, "derived": False,
         "veracity": "叙述", "books": ["测试书"], "layer": "人", "direction": "→", "locs": ["001:3"], "id": ""},
    ]
    dv = derive_relations("测试书", fake_edges)
    kinds = {(x["kind"], x["person"], x["relative_to"]) for x in dv["lineage_labels"]}
    chk("B3 同门推导（A-C 共同师父 B）",
        any(e["predicate"] == "同门" and {e["subject"], e["object"]} == {"A", "C"}
            for e in dv["tongmen_edges"]))
    chk("B1 师祖标签（D 师祖 B：D→A→B）",
        ("辈分", "D", "B") in kinds, sorted(kinds))
    chk("B5 长幼序标签（A/C 同门按拜师定位符）",
        any(k == "长幼" for k, _, _ in kinds), sorted(kinds))
    chk("派生边全部 weak+derived",
        all(e["confidence"] == "weak" and e["derived"] for e in dv["tongmen_edges"])
        and all(lb["confidence"] == "weak" for lb in dv["lineage_labels"]))
    # 规范名映射
    chk("concordance 变体归一（玉罗刹→练霓裳）",
        ctx.canon("玉罗刹", None, "@") == "练霓裳", ctx.canon("玉罗刹", None, "@"))
    # 幂等
    def _sig(res):
        return [(c["predicate"], c["subject"], c["object"], c["loc"],
                 c.get("subtype", ""), json.dumps(c.get("params") or {},
                                                 ensure_ascii=False, sort_keys=True))
                for c in res["candidates"]]

    r1 = extract_paragraph(ctx, 1, 1, syn[0][0], ALL_RULES)
    r2 = extract_paragraph(ctx, 1, 1, syn[0][0], ALL_RULES)
    chk("单段抽取幂等", _sig(r1) == _sig(r2))
    # 全流程（若 tagged 存在，抽 1 书 1 回做冒烟；跳过 000 楔子——叙事概述段少动宾）
    if books():
        b = books()[0]
        chs = sorted((TAG / b).glob("*.tagged.md"))
        ch = chs[1] if len(chs) > 1 else chs[0]
        paras = _iter_paragraphs(ch)
        r = {"candidates": 0}
        for no, text in paras:
            out = extract_paragraph(Ctx(b), int(ch.name[:3]), no, text, ALL_RULES)
            r["candidates"] += len(out["candidates"])
        chk(f"冒烟：{b} {ch.name} 全回候选 > 0", r["candidates"] > 0, r["candidates"])
    ok = all(c["ok"] for c in checks)
    lines = [f"# N5 relation_validator 自检报告", "",
             f"- 时间：{now_iso()} · 结果：{'✅ 全部通过' if ok else '❌ 失败'}",
             f"- 断言：{sum(c['ok'] for c in checks)}/{len(checks)}", "",
             "| # | 断言 | 结果 | 说明 |", "|---:|---|---|---|"]
    for i, c in enumerate(checks, 1):
        lines.append(f"| {i} | {c['name']} | {'✅' if c['ok'] else '❌'} | {c['detail']} |")
    write_text("\n".join(lines) + "\n", LOGS_QA / "relation_validator_selftest.md")
    print(f"[N5] selftest {'PASS' if ok else 'FAIL'} "
          f"({sum(c['ok'] for c in checks)}/{len(checks)}) → {LOGS_QA/'relation_validator_selftest.md'}")
    return 0 if ok else 1


# ---------------------------------------------------------------- 报告模式
def report_mode(book: str | None) -> int:
    if not OUT_REL.exists():
        print(f"[N5] 无关系表产物：{OUT_REL}")
        return 2
    payloads = []
    names = [book] if book else [p.stem for p in sorted(OUT_REL.glob("*.json"))]
    for name in names:
        path = OUT_REL / f"{name}.json"
        if not path.exists():
            print(f"[N5] 缺 {path}")
            continue
        payload = read_json(path)
        payload.setdefault("dropped", dropped_summary([]))
        write_text(render_report(payload), LOGS_REL / f"{name}.md")
        payloads.append(payload)
        print(f"[N5] 报告重生成 → {LOGS_REL / (name + '.md')}")
    if payloads:
        write_text(render_summary(payloads), LOGS_REL / "_summary.md")
        print(f"[N5] 汇总 → {LOGS_REL / '_summary.md'}")
    return 0


# ---------------------------------------------------------------- 主流程
def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="N5 relation_validator：04f 联动候选 → D06 谓词核验 → 关系表")
    parser.add_argument("--book", help="单书：如 白发魔女传")
    parser.add_argument("--all", action="store_true", help="全部已 tagged 书（默认）")
    parser.add_argument("--chapter", type=int, help="单回调试（须与 --book 连用；只写 logs/relations/_debug）")
    parser.add_argument("--report", action="store_true", help="只从 registry/relations/*.json 重出报告")
    parser.add_argument("--strict", action="store_true",
                        help="严格门禁：仅 27 行规则 + strong/ok；hard validation 失败 exit 1")
    parser.add_argument("--selftest", action="store_true", help="内置断言")
    args = parser.parse_args(argv)

    LOGS_REL.mkdir(parents=True, exist_ok=True)
    if args.selftest:
        return selftest()
    if args.report:
        return report_mode(args.book)
    targets = [args.book] if args.book else books()
    if not targets:
        print("[N5] 未发现 tagged 书")
        return 2
    if args.chapter is not None and not args.book:
        print("[N5] --chapter 须与 --book 连用")
        return 2
    payloads, failed = [], False
    for book in targets:
        if book not in books():
            print(f"[N5] 跳过：{book} 无 tagged 产物")
            continue
        payload = write_book(book, strict=args.strict, only_chapter=args.chapter)
        payloads.append(payload)
        errs = payload["validation"]["hard_errors"]
        if args.strict and errs:
            failed = True
            print(f"[N5] ✗ strict 校验失败 {book}: {len(errs)} 项 hard_errors")
            report_path = LOGS_REL / f"{book}_strict_fail.md"
            write_text(render_report(payload), report_path)
            print(f"[N5]   → {report_path}")
    if args.chapter is None and payloads and not args.strict:
        write_text(render_summary(payloads), LOGS_REL / "_summary.md")
        print(f"[N5] 汇总 → {LOGS_REL / '_summary.md'}")
    if args.strict:
        payloads = [p for p in payloads if p.get("mode") == "strict"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
