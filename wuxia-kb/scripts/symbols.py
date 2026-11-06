# -*- coding: utf-8 -*-
"""C0b · 统一符号表 —— 武侠标注体系符号的唯一来源。

设计纪律（承 docs/05 §1.2-2 shiji 技术债教训：符号散落 15+ 处互相矛盾）：
  所有 lint/fix/tag 脚本一律 import 本文件，禁止在脚本内重写字符类。
符号定版来源：
  - 实体/动词/修辞：skills/SKILL_01g_标注符号集合原则.md（v0.3-draft）
  - 围栏类型/文本模式/套语分级：skills/SKILL_02a_02b_章回结构与韵文处理.md（v0.3-draft）
"""
import re

SPEC_VERSION = "0.3-draft"

# ---- 实体层（15 类，01g §2.2.1 定版） ----
ENTITIES = {
    "@": "人物",
    "◎": "人物群组",
    "=": "地点",
    "◆": "组织",
    "&": "家族世系",
    "~": "族群",
    ";": "职衔",
    "#": "身份",
    "☆": "武功技艺",
    "•": "器物",
    "+": "生物",
    "{": "作品文书",
    "^": "专门概念",
    "%": "时间",
    "$": "数量",
}

# ---- 动词层（6 域，01g §2.2.3 定版，方形动词族） ----
VERBS = {
    "⊞": "战斗交锋",
    "⊠": "生命健康",
    "⊡": "社会关系",
    "⊟": "物件变化",
    "▣": "技术传习",
    "■": "行踪迁移",
}

# ---- 修辞层（01g §2.2.2，启用后置） ----
RHETORIC = {"※": "固定表达"}

ENTITY_CODES = set(ENTITIES)
VERB_CODES = set(VERBS)
RHETORIC_CODES = set(RHETORIC)
ALL_CODES = ENTITY_CODES | VERB_CODES | RHETORIC_CODES

# ---- 三层括号与管道 ----
BRACKETS = {
    "entity": ("〖", "〗"),   # U+3016 / U+3017
    "verb": ("⟦", "⟧"),      # U+27E6 / U+27E7
    "rhetoric": ("〘", "〙"), # U+3018 / U+3019
}
PIPE = "|"  # 消歧管道：〖@显示名|规范名〗 / ⟦⊞动词|消歧说明⟧

# ---- 围栏（02ab §4.1 枚举定版） ----
FENCE_FORMAL = ["词", "诗", "歌", "对联", "回末对", "回末", "书信"]
FENCE_OBSERVE = ["告示", "口诀", "说书"]
FENCE_ALL = FENCE_FORMAL + FENCE_OBSERVE

# 围栏内标注豁免（02ab §4.4 三层豁免表）：
#   词/诗/歌/对联/回末对 → 实体限实指，动词不标
#   回末 → 全不标
#   书信/告示 → 实体可标（称谓代词不标），动词不标，事件不核实
#   口诀 → 技术名可标，动词不标
#   说书 → 可标，不抽事件
FENCE_ENTITY_POLICY = {
    "词": "real_only", "诗": "real_only", "歌": "real_only",
    "对联": "real_only", "回末对": "real_only",
    "回末": "none", "书信": "allowed", "告示": "allowed",
    "口诀": "tech_only", "说书": "allowed",
}

# ---- 文本模式与叙述模式（01g 最低枚举 + 02ab 新增"套语"，只增不减） ----
TEXT_MODES = ["正文", "回目", "诗词", "歌词", "口诀", "书信", "告示", "套语"]
NARRATION_MODES = ["正常叙事", "回忆", "梦境", "假想", "戏中戏"]

# ---- 回目与 PN（02ab 定版） ----
PN_TITLE = "[0]"                      # 回目行固定编号
PN_MAX_LEVEL = 2                      # 只用两级 [N] / [N.M]，禁三级
ANCHOR_FMT = "{book}#pn-r{chapter}.{para}"   # 跨书锚点：{作品ID}#pn-r{回号}.{段}

# ---- 旧符号（历史版本/史记体系，lint_symbol_conflicts 检测对象） ----
LEGACY_VERB_CODES = ["◈", "◉", "○", "◇", "▲", "▷"]           # 旧动词域/旧建议稿
LEGACY_ENTITY_CODES = ["!", "?", "_", ":", "["]                # 史记 18 类中未启用的码位
LEGACY_BRACKET_STYLES = [("@", "@")]                            # 旧式 @X@ 包裹（非 〖@X〗）

# ---- 事件 outcome（01g/04a 定版五值） ----
OUTCOME_VALUES = ["胜", "负", "平", "未决", "未知"]

# ---- 置信与三档（01g 可信状态 / D09 全局三档） ----
CONF_VALUES = ["strong", "ok", "weak"]          # strong=明文 ok=窗口共现 weak=先验不发布
TIER_VALUES = ["auto", "review", "watch"]       # 高置信批量 / 多义待审 / 观察
STATUS_VALUES = ["auto", "待审", "已核准"]

# ---- 解析用正则（令牌优先于 Markdown 的受控解析顺序，01g §3.1） ----
TOKEN_RE = re.compile(
    r"〖(?P<ent>[^〖〗]+)〗|⟦(?P<verb>[^⟦⟧]+)⟧|〘(?P<rhet>[^〘〙]+)〙"
)
FENCE_OPEN_RE = re.compile(r"^:::\s*(\S+)\s*$")
FENCE_CLOSE_RE = re.compile(r"^:::\s*$")

# ---- 回末套语词族（02ab §6.3 单一来源；生成器 TAOYU 与 lint E12 共用，2026-11-05 对齐） ----
TAOYU_HEAD_RE = re.compile(r"欲[知如看][^。！？]{0,24}")
TAOYU_TAIL_RE = re.compile(r"(?:[请且要][听看])?下回(?:分解|再|见)?")


def is_taoyu(text: str) -> bool:
    """回末套语判定（02ab §6.3 词族：欲知/欲如/欲看 + 可选[请且要][听看] + 下回[分解/再/见]?）。"""
    return bool(TAOYU_HEAD_RE.search(text) and TAOYU_TAIL_RE.search(text))


def parse_token(token: str):
    """解析单个标注令牌 → (layer, type_code, body, display, canonical|None, note)。

    〖@玉罗刹|练霓裳〗 → ("entity", "@", "玉罗刹|练霓裳", "玉罗刹", "练霓裳", None)
    ⟦⊞走|败走⟧       → ("verb", "⊞", "走|败走", "走", "败走", None)
    解析失败返回 (layer, None, body, None, None, 错误说明)。
    """
    m = TOKEN_RE.fullmatch(token.strip())
    if not m:
        layer = "entity" if token.startswith(BRACKETS["entity"][0]) else (
            "verb" if token.startswith(BRACKETS["verb"][0]) else (
                "rhetoric" if token.startswith(BRACKETS["rhetoric"][0]) else None))
        return (layer, None, token, None, None, "令牌括号不配对或类型未知")
    if m.group("ent") is not None:
        layer, body = "entity", m.group("ent")
    elif m.group("verb") is not None:
        layer, body = "verb", m.group("verb")
    else:
        layer, body = "rhetoric", m.group("rhet")
    code, rest = body[0], body[1:]
    if layer == "entity" and code not in ENTITY_CODES:
        return (layer, code, body, None, None, "实体类型码不在 15 类定版内")
    if layer == "verb" and code not in VERB_CODES:
        return (layer, code, body, None, None, "动词域码不在 6 域定版内")
    if layer == "rhetoric" and code not in RHETORIC_CODES:
        return (layer, code, body, None, None, "修辞码不在定版内")
    if PIPE in rest:
        display, note = rest.split(PIPE, 1)
    else:
        display, note = rest, None
    return (layer, code, body, display, note, None)


def strip_markup(text: str) -> str:
    """剥除全部标注令牌，保留原文显示串（供韵文句长统计/剥标对账的共用入口）。

    注意：与 lint_text_integrity 的逐字对账不同——本函数按令牌语义剥到"显示串"，
    管道后的规范名/消歧说明一并去除。
    """
    def repl(m):
        body = m.group("ent") if m.group("ent") is not None else (
            m.group("verb") if m.group("verb") is not None else m.group("rhet"))
        code, rest = body[0], body[1:]
        return rest.split(PIPE, 1)[0] if PIPE in rest else rest
    return TOKEN_RE.sub(repl, text)


def fence_opens(line: str):
    m = FENCE_OPEN_RE.match(line)
    return m.group(1) if m else None


def is_fence_close(line: str) -> bool:
    return bool(FENCE_CLOSE_RE.match(line))
