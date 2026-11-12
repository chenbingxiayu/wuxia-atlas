# -*- coding: utf-8 -*-
"""clean_matches.py —— 工具 E·E1 对局清洗器（spec 007 T1，取代 build_matches.py）。

管线：C0 上游修复（别名归并/自对丢/组织转记）→ 在场感知场景重切（验收 ≤8 人）
  → L1/L2 裁决（事件方向动词优先 · 事件层 outcome · 词表 v0.2 兜底）→ 软分数 s → 三通道日志。
口径基准：《武评工具实现设计》；宪法原则 8 已由用户裁定解除（当前 Session 管线为权威）。

输出：site/data/matches.json（matches-v2 · legacy 键兼容）+ site/data/ratings-cleanlog.json
W2-C1（天山演示版总体方案 §3.1 P0-2/§4.3 C1/§5.5，2026-11-09）新增 --scope：
  - --scope <profile>：书目按 book ∈ scope 过滤（对局/选手随之裁剪）；meta 加 scope 键
    （口径与 EX 层一致）；--scope all 与不传参数同为全量口径（meta 无 scope 键，方案 R6）；
  - 管线顺序固化见 scripts/run_pipeline.py：本工具必须在 export_site_all（EX-5 v1 legacy
    中间层）之后跑，其 matches-v2 产物再由 ratings_whr.py 消费。
F1（武评 4 书 → 7 书，2026-11-12）registry/events 新源适配（仿 D12 qa-index 模式）：
  - scope 口径下无 kb 事件表的书（散花女侠/联剑风云录/冰魄寒光剑）改读
    wuxia-kb/registry/events/<书>.json（D03 新事件层 event-v1，只读）；旧表存在的书保持
    旧路径——两源并存不迁移。字段映射复用 D12 适配口径（build_qa_index.registry_norm_loc /
    REG_TYPE_CODE 家族：T01→◈ T02→◉；gate=excluded 丢弃、R4 对白内丢弃 ≈ 旧 in_quote、
    单侧不入、participants 须 @ 人物），映射纪律固化于 tests/test_matches_seven_books.py；
  - **全量口径（scope=None）不消费新源（方案 R6：避免 24 书全量爆炸，adapter 仅限 scope 书）**
    ——available_books(None) == lit_books()，无旧表的书全量口径下不进候选；
  - BOOKS 前 4 位保持原序（match id/scene 码逐场不变，旧 4 书可复算），新 3 书按编年序追加；
  - 事件层 outcome 裁决（胜/负/平，D03 抽取器旧 v0.1 词表移植）→ 新增裁决通道 ①b
    「事件方向outcome」：pair 级败方明确归位（L2 可录），强度映射对齐 STRENGTH 档；
    其余裁决纪律不变（L1 恰两人景照录、词表兜底低信任 + L2 ×0.6、平词限 L1、无明文不打分）；
  - **F1 方向修正（spec 对齐，2026-11-12）**：设计文档《武评工具实现设计》§82 要求 s 为
    a 侧 BT 得分、outcome 为其离散化（s≥0.75 win / s≤0.35 loss）——旧实现 s=强度×修正
    不带方向，outcome/WHR 恒按字典序 a 侧判胜，基线审计 65/129 场与明文相反（「朱翊钧杀
    卓继贤」记卓继贤胜 s=1.0）。修正：verdict=loss → s=1−强度×修正（平不动）——对两源
    统一生效（旧 4 书受影响场次见报告/基线 diff，逐场可对质；关闭此修正旧源可逐场复现
    f1_baseline——旧路径本身未被 F1 适配器扰动）。
  - 新源书场景文本：无 kb/tagged，改读 wuxia-kb/tagged/<书>/*.tagged.md（[N] 段号版式，
    registry loc 段号与之对齐；markup 清洗与 read_tagged 同源标注体系）。
G1（2026-11-12）：canon() 消费 registry alias_overrides（D9 机制照用，@ 类型内显式裁定）——
  承珠/凌云风/小虎子/李大人/大龙头/百毒神君 六个 @ 表层串并入目标人物（排查确凿：
  别名互证≥2 且共书/pipe 别名实证）；match id/scene 结构不受影响（仅人名归一）。
用法：python scripts/clean_matches.py [--scope tianshan-demo]
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import KB, SITE_DATA, lit_books, today  # noqa: E402

# W2-C1：scope 基础设施复用（export_site_common 在 wuxia-kb/scripts，import 胜过复制——同 W0-T3b）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / "wuxia-kb" / "scripts"
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402
# G1（2026-11-12）：D9 alias_overrides 机制照用——canon() 消费 registry 类型内显式裁定
# （load_alias_overrides 单一校验源：to_id/类型一致/aliases 成对/fail-fast，export_site_characters）
import export_site_characters as exc  # noqa: E402
# F1：D12 适配口径复用（registry loc 归一化）——import 胜过复制，两处映射同源不漂移
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_qa_index as bqi  # noqa: E402

WORDLIST = "v0.2"
SCENE_SPLITTER = "v2-presence"
GAP = 40
# 候选书目：前 4 = 旧事件表书（W2-C1 原序——match id/scene 码逐场不变，可复算纪律）；
# 后 3 = F1 新增（registry 新源；书间按编年序，同 site_scope profile）。
# 实际书目 = BOOKS ∩ 可用源（旧表 kb/ 或 registry/events 新源，scope 口径）。
BOOKS = ["白发魔女传", "塞外奇侠传", "七剑下天山", "江湖三女侠",
         "散花女侠", "联剑风云录", "冰魄寒光剑"]
# F1：新事件层（D03 event-v1，只读）与新源书场景文本层
REG_EVENTS = Path(__file__).resolve().parents[1] / "wuxia-kb" / "registry" / "events"
WXKB_TAGGED = Path(__file__).resolve().parents[1] / "wuxia-kb" / "tagged"
# 对局仅战斗族（T01→◈ 比武较技 / T02→◉ 生死杀伐；T04◇传艺/T06○结盟非战斗不入——旧
# verb_code ∈ ◈◉▲ 过滤语义的 D12 同源延续）
REG_COMBAT_TYPES = {"T01", "T02"}

# ---- 词表 v0.2（方向动词表 + 场景胜负词表）----
WINNER_SUBJ_STRONG = {"杀", "诛", "毙", "刺死", "击毙", "斩", "擒", "擒下", "活捉"}
WINNER_SUBJ_SOFT = {"击败", "战胜", "大败", "杀退", "打退", "迫退", "逼退", "震退", "荡开", "打伤", "重创"}
LOSER_SUBJ = {"被擒", "被活捉", "被杀", "被斩", "败于", "负于", "不敌", "输给"}
STRENGTH = {"强胜": 1.0, "常规胜": 0.85, "险胜": 0.7, "下风": 0.6, "平": 0.5}
LOSS_CLASSES = [
    (1.0, ["大败", "击败", "战败", "打败", "击倒", "击毙", "刺死", "擒下", "活捉",
           "毙于", "斩于", "死于", "杀退", "败走", "倒地", "栽倒"]),
    (0.85, ["占得上风", "大占上风", "占尽上风", "迫退", "逼退", "震退", "荡开",
            "迫得后退", "逼得后退", "伤在"]),
    (0.7, ["险胜", "堪堪取胜", "略胜一筹", "侥幸获胜", "略占上风", "不敌", "甘拜下风", "技逊一筹"]),
    (0.6, ["下风", "难以招架", "渐落下风", "只有招架", "招架不住", "招架之功",
           "败象渐露", "遮拦不住", "再难支撑"]),
]
DRAW_WORDS = ["不分胜负", "平分秋色", "难分高下", "势均力敌", "旗鼓相当", "打个平手",
              "战个平手", "战成平手", "相持不下", "两败俱伤", "斗个两败俱伤",
              "平手", "不分高下", "斗了三百", "拆了三百", "百余招", "数十招", "三百余招"]
MODIFIERS = [("中毒", ["中毒", "服毒", "下药"]), ("状态不佳", ["带伤", "伤重", "力竭", "久战"]),
             ("偷袭", ["偷袭", "暗算", "冷箭", "背后偷袭"]), ("诈败", ["诈败", "卖个破绽", "佯输"]),
             ("放水", ["留手", "未出全力", "手下留情"]), ("切磋", ["切磋", "指点", "印证武功"])]
MOD_MULT = {"中毒": 0.3, "状态不佳": 0.5, "偷袭": 0.5, "诈败": 0.5, "放水": 0.5, "切磋": 0.3}

# ---- 群目/组织（与 lib/groups.ts、audit_r1.py 三处同源——修改需同步）----
GROUP_LABELS = {
    "清兵", "清军", "清军水师", "明军", "官兵", "官军", "满洲军队", "满洲军", "神策营",
    "锦衣卫", "御林军", "禁卫军", "大内", "大内卫士", "清宫", "血滴子",
    "武当弟子", "少林弟子", "峨嵋弟子", "众人", "侍卫", "卫士",
    "关东四侠", "江南七侠", "桑家三妖", "五龙帮", "铁扇帮", "满洲", "喀达尔族",
}
ORG_SUFFIX = ("派", "军", "寺", "帮", "教", "寨", "营", "卫", "宫")


def is_org(name: str) -> bool:
    if name in GROUP_LABELS:
        return True
    return len(name) >= 3 and name.endswith(ORG_SUFFIX)


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build_alias_map(books):
    m = {}
    for book in books:
        reg_fp = KB / book / "实体登记表.json"
        if not reg_fp.exists():
            continue  # F1：新源书无 kb 登记表（registry 规范名已 canonical，别名归并仅旧书）
        reg = load_json(reg_fp)
        for key, e in reg["entities"].items():
            c = e.get("canonical")
            if not c:
                continue
            m.setdefault(c, c)
            for a in (e.get("aliases") or {}):
                m.setdefault(a, c)
    from kb_discovery import BOOK_CANON
    for k, v in BOOK_CANON.items():
        m.setdefault(k, v)
    return m


def read_tagged(book):
    tdir = KB / "tagged" / book
    if not tdir.is_dir():
        return
    for fp in sorted(tdir.glob("*.tagged.md")):
        chap = int(fp.name[:3])
        lines = fp.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].strip() == "---":
            endfm = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
            body = lines[endfm + 1:] if endfm is not None else lines
        else:
            body = lines
        for lineno, s in enumerate(body, 1):
            def repl(m):
                body = m.group(1)
                name = body.split("|")[-1].strip() if "|" in body else body.split("|")[0].strip()
                return re.sub(r"^[@=◆%☆\[§+]", "", name)
            clean = re.sub(r"〖([^〗]*)〗", repl, s)
            clean = re.sub(r"⟦([^⟧]*)⟧", lambda m: m.group(1).split()[-1], clean)
            yield chap, lineno, clean


def _clean_markup(s: str) -> str:
    """标注 markup 清洗（read_tagged 同款规则提为共用：〖〗取规范名、⟦⟧取动词）。"""
    def repl(m):
        body = m.group(1)
        name = body.split("|")[-1].strip() if "|" in body else body.split("|")[0].strip()
        return re.sub(r"^[@=◆%☆\[§+]", "", name)
    clean = re.sub(r"〖([^〗]*)〗", repl, s)
    clean = re.sub(r"⟦([^⟧]*)⟧", lambda m: m.group(1).split()[-1], clean)
    return clean


def read_wxkb_tagged(book):
    """F1：新源书场景文本（wuxia-kb/tagged/<书>/*.tagged.md，[N] 段号版式）。

    段号 = registry event loc 段号（对齐实证：散花女侠 001:080 ↔ [80] 段 童家骏×张风府）；
    [N] 段跨物理行（词牌换行）并入前段；markup 清洗与 read_tagged 同源（_clean_markup）。
    yield (chap, para, clean_text)——与 read_tagged 的 (chap, lineno, text) 同构。
    """
    tdir = WXKB_TAGGED / book
    if not tdir.is_dir():
        return
    for fp in sorted(tdir.glob("*.tagged.md")):
        chap = int(fp.name[:3])
        cur_no, cur_lines = None, []
        for s in fp.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\[(\d+)\]\s?(.*)$", s)
            if m is None:
                if cur_no is not None and s.strip():
                    cur_lines.append(s.strip())  # 段内换行（词牌/长段折行）
                continue
            if cur_no is not None:
                yield chap, cur_no, _clean_markup("".join(cur_lines))
            cur_no, cur_lines = int(m.group(1)), [m.group(2)]
        if cur_no is not None:
            yield chap, cur_no, _clean_markup("".join(cur_lines))


# ================================================================ F1：registry 新源适配
def reg_outcome(e):
    """registry 事件层 outcome 裁决 → ("win_a"|"win_b"|"draw", 强度)；未决/未知 → None。

    D03 抽取器 outcome = 句级胜败裁决（旧 v0.1 词表移植 + T02 杀伐触发 + 胜负投影，
    outcome_basis 记录依据、outcome_weight 记录权重）——作为新源专用通道 ①b 的方向依据
    （pair 级败方明确归位，L2 多人景可录不硬拆）。强度对齐 STRENGTH 档：
      T02 致死 → 强胜 1.0；触发词胜负投影 → 常规胜 0.85（保守档：投影混 强/常规 动词）；
      胜败词表命中 → outcome_weight 分档 1.0/0.85/0.7/0.6（cond 折叠行保守降档）；
      平 → 0.5（draw 与平词同档；入榜仍限 L1——多人景平局属噪声通道，纪律不变）。
    """
    oc = e.get("outcome")
    if oc not in ("胜", "负", "平"):
        return None
    if oc == "平":
        return ("draw", STRENGTH["平"])
    basis = e.get("outcome_basis") or ""
    w = e.get("outcome_weight") or 0.0
    if "致死" in basis:
        st = STRENGTH["强胜"]
    elif "投影" in basis:
        st = STRENGTH["常规胜"]
    elif w >= 0.95:
        st = STRENGTH["强胜"]
    elif w >= 0.75:
        st = STRENGTH["常规胜"]
    elif w >= 0.65:
        st = STRENGTH["险胜"]
    else:
        st = STRENGTH["下风"]
    return ("win_a" if oc == "胜" else "win_b", st)


def registry_book_rows(book, log, payload=None):
    """F1：registry/events/<书>.json（event-v1）→ 旧 evs 同构行 [{chap,line,v,a,b,oc}]。

    映射复用 D12 适配口径（build_qa_index 同源）：loc 经 registry_norm_loc（"001:002"→
    "001:2"，段号去补零对齐旧事件表行格式，parse 出 chap/line）；v=首个锚动词 verb；
    a/b=subject/object 经 canon（别名归并同源）。过滤纪律（测试固化）：
      - 非战斗族 type（≠T01/T02）静默不入（旧 verb_code ∈ ◈◉▲ 过滤语义）；
      - gate=excluded（R1 无参与方/R3 非事实叙述）→ 丢弃计 dropped_events（≈旧 dropped）；
      - 单侧参与（R2 单方降级）→ 不入计 reg_single_side（对局需双侧主宾，同旧路径主宾过滤）；
      - gate=review + R4 对白内（视角/转述，事实待核）→ 丢弃计 in_quote（≈旧 in_quote 纪律，
        宁可榜小不可榜错）；
      - participants 须 @ 人物：subject/object 任一方无 @ 参与方（武器/名物名）→ 丢弃计
        reg_non_person；
      - outcome 胜/负/平 → oc=(方向, 强度) 随行（reg_outcome），供裁决通道 ①b。
    payload=None 时读 REG_EVENTS/<书>.json（合成 fixture 可注入 payload 直测）。
    """
    if payload is None:
        fp = REG_EVENTS / f"{book}.json"
        if not fp.exists():
            return []
        payload = load_json(fp)
    rows = []
    if payload.get("schema") != "event-v1":
        return rows
    for e in payload.get("events", []):
        if e.get("type") not in REG_COMBAT_TYPES:
            continue
        if e.get("gate") == "excluded":
            log["dropped"]["dropped_events"] += 1
            continue
        both = bool(e.get("subject")) and bool(e.get("object"))
        if not both:
            log["dropped"]["reg_single_side"] += 1
            continue
        if e.get("gate") == "review" and (e.get("gate_reason") or "").startswith("R4"):
            log["dropped"]["in_quote"] += 1
            continue
        anchors = e.get("anchor_verbs") or []
        if not anchors:
            continue  # 无动词锚不成行（同 D12：无 v 不入）
        etype = {p.get("name"): p.get("entity_type") for p in (e.get("participants") or [])}
        if etype.get(e["subject"]) != "@" or etype.get(e["object"]) != "@":
            log["dropped"]["reg_non_person"] += 1
            continue
        loc = bqi.registry_norm_loc(e["loc"])  # "001:002" → "001:2"（旧事件表行格式）
        chap, line = loc.split(":")
        rows.append({"chap": int(chap), "line": int(line),
                     "v": anchors[0].get("verb") or "",
                     "a": canon(e["subject"]), "b": canon(e["object"]),
                     "oc": reg_outcome(e)})
    return rows


def load_book_events(book, scope=None, log=None):
    """书目事件装载（两源并存分派）：kb/<书>/事件表.json 存在 → 旧路径（原样不动）；
    否则 scope 口径且 registry/events/<书>.json 在库 → 新源适配（F1）。
    全量口径（scope=None）绝不读新源（方案 R6）。返回 (evs, source)：
    source ∈ {"kb-events", "registry-events", None}。"""
    log = log if log is not None else _blank_log()
    old_fp = KB / book / "事件表.json"
    if old_fp.exists():
        evs = []
        for e in load_json(old_fp).get("events", []):
            if e.get("dropped") or e.get("curation", {}).get("verdict") == "drop":
                log["dropped"]["dropped_events"] += 1
                continue
            if e.get("in_quote"):
                log["dropped"]["in_quote"] += 1
                continue
            if not e.get("subject") or not e.get("object") or e.get("verb_code") not in ("◈", "◉", "▲"):
                continue
            loc = e.get("loc", "")
            try:
                chap, line = int(loc[:3]), int(loc[4:7])
            except ValueError:
                continue
            evs.append({"chap": chap, "line": line, "v": e.get("verb") or "",
                        "a": canon(e["subject"]), "b": canon(e["object"])})
        return evs, "kb-events"
    if scope is not None:
        evs = registry_book_rows(book, log)
        if evs:
            return evs, "registry-events"
    return [], None


def _blank_log():
    """load_book_events 独立调用（无主日志语境）时的空白 cleanlog 骨架。"""
    return {"kept": {"L1": 0, "L2": 0, "L3": 0},
            "dropped": {"self_pair": 0, "no_verdict": 0, "group_label": 0, "in_quote": 0,
                        "dropped_events": 0, "reg_single_side": 0, "reg_non_person": 0},
            "transferred": {"org": 0}, "downgraded": {"attribution_fallback": 0},
            "scenes": {"count": 0, "max_persons": 0}, "wordlist_hit": Counter()}


def available_books(scope=None):
    """清洗可用书目集合（select_books 的 available 实参）。

    全量口径 = lit_books()（kb 旧路径书，R6：新源仅限 scope 口径消费——全量不爆炸）；
    scope 口径 = lit_books() ∪ BOOKS 中有 registry 新源的书（旧表书仍走旧路径——
    两源并存，load_book_events 按"旧表优先"分派）。
    """
    avail = set(lit_books())
    if scope is not None:
        avail |= {b for b in BOOKS if (REG_EVENTS / f"{b}.json").exists()}
    return sorted(avail)


def nearest_name(text: str, pos: int, names: set, back: int = 10):
    lo = max(0, pos - back)
    seg = text[lo:pos]
    best, bestp = None, -1
    for n in names:
        p = seg.rfind(n)
        if p >= 0 and p > bestp:
            best, bestp = n, p
    return best


def select_books(available, scope=None):
    """实际清洗书目 = BOOKS（编年序）∩ available（kb 已点亮）∩ scope（W2-C1）。

    scope=None（全量口径）不裁剪（方案 R6）；scope 口径下 book ∈ scope["books"] 才保留——
    对局/选手由逐书循环生成，书目过滤即对局过滤的单一来源。
    F1：available 由 available_books(scope) 供给（scope 口径并集 registry 新源 3 书）。
    """
    books = [b for b in BOOKS if b in available]
    if scope is not None:
        books = [b for b in books if esc.in_scope(b, scope)]
    return books


# ---- 别名归并（模块级：load_book_events/registry_book_rows 与 main 共用同一映射）----
_ALIAS = {}


def canon(name: str) -> str:
    """规范名映射（跨书同人异名 → 站点统一名；main 启动时 set_alias_map 装载）。"""
    return _ALIAS.get(name, name)


def set_alias_map(books):
    """装载别名映射（main 每次运行按实际书目重建）。

    G1（2026-11-12）：registry alias_overrides（D9 机制照用，@ 类型内显式裁定）在 kb 表
    别名之后覆盖——显式裁定优先于兜底映射。只消费 @ 条目（matches 参与方恒为 @ 人物）；
    alias_overrides 缺键 → 空 map（行为与 G1 前逐字节一致）。"""
    _ALIAS.clear()
    _ALIAS.update(build_alias_map(books))
    _ALIAS.update(load_override_alias_map())


def override_alias_map(overrides):
    """{(type, form): (to_type, to_canonical)} → {form: to_canonical}（纯函数）。

    仅取 @ 条目（matches 参与方恒为 @ 人物；$/= 等同名其他类型不进 matches 层映射）；
    overrides 为 None/空 → 空 dict。
    """
    if not overrides:
        return {}
    return {form: to_canon for (ftype, form), (to_type, to_canon) in overrides.items()
            if ftype == "@" and to_canon}


def load_override_alias_map():
    """registry alias_overrides → canon 名映射（D9 loader 单一校验源；坏数据 fail-fast 上抛）。"""
    overrides, _meta = exc.load_alias_overrides()
    return override_alias_map(overrides)


def pair_verdict(scene, pair, aa, bb, text, layer, has_draw):
    """单pair裁决通道（纯函数；main 按 via 施加折扣/软分数组装）→
    (verdict, strength, trust, via) 或 None（无明文不打分——宁可榜小）。

    ① 事件方向动词（L2 主通道 / L1 同样适用）→
    ①b 事件层 outcome（F1 新源行 oc=(方向,强度)：pair 级方向，败方明确归位，L2 可录）→
    ② 词表近名兜底（限 L1，低信任——L2 的词表兜底属噪声通道）→
    ③ 平词/outcome 平（限 L1；多人景平局属噪声，纪律不变）。
    旧源行无 oc 键——①b 恒空转，行为与 F1 前逐分支一致（两源并存语义隔离）。
    """
    verdict, strength, trust, via = None, None, "medium", None

    # ① 事件方向动词
    for e in scene:
        if {e["a"], e["b"]} != pair:
            continue
        v = e["v"]
        if v in WINNER_SUBJ_STRONG:
            verdict, strength, via = ("win" if e["a"] == aa else "loss"), STRENGTH["强胜"], "事件方向动词"
            break
        if v in WINNER_SUBJ_SOFT:
            verdict, strength, via = ("win" if e["a"] == aa else "loss"), STRENGTH["常规胜"], "事件方向动词"
            break
        if v in LOSER_SUBJ:
            verdict, strength, via = ("loss" if e["a"] == aa else "win"), STRENGTH["常规胜"], "事件方向动词"
            break

    # ①b 事件层 outcome（F1 新源；方向 pair 级归位——subject 胜→a 胜 / object 胜→b 胜）
    oc_draw = False
    if verdict is None:
        for e in scene:
            if {e["a"], e["b"]} != pair:
                continue
            oc = e.get("oc")
            if not oc:
                continue
            side, st = oc
            if side == "draw":
                oc_draw = True  # 平 → 与平词同通道（入榜仍限 L1）
                continue
            subj_is_aa = e["a"] == aa
            verdict = ("win" if subj_is_aa else "loss") if side == "win_a" \
                else ("loss" if subj_is_aa else "win")
            strength, via = st, "事件方向outcome"
            break

    # ② 词表 v0.2（兜底，限 L1）
    if verdict is None:
        votes = defaultdict(float)
        for w, cw in all_loss_words():
            start = 0
            while True:
                pp = text.find(w, start)
                if pp < 0:
                    break
                loser = nearest_name(text, pp, pair)
                if loser and loser in pair:
                    winner = next(n for n in pair if n != loser)
                    votes[(winner, loser)] += cw
                start = pp + len(w)
        if votes and layer == "L1":
            (winner, loser), wsum = sorted(votes.items(), key=lambda kv: -kv[1])[0]
            for cw, _ws in LOSS_CLASSES:
                if abs(wsum - cw) < 1e-6:
                    strength = cw
                    break
            strength = strength or 0.85
            verdict = "win" if winner == aa else "loss"
            via = "词表近名兜底"
            trust = "low"
        elif (has_draw or oc_draw) and layer == "L1":
            verdict, strength, via = "draw", STRENGTH["平"], ("平词" if has_draw else "事件方向outcome")
        else:
            return None  # 宁可榜小：多人景词表兜底/平词属噪声通道——不入评分
    return verdict, strength, trust, via


def all_loss_words():
    """词表全集（LOSS_CLASSES 4 档 + 下风补词——原 main 内联表提为共用）。"""
    return [(w, cw) for cw, ws in LOSS_CLASSES for w in ws] + \
        [(w, 0.6) for w in ["连连后退", "只有招架", "招架不住", "招架之功", "败象渐露",
                            "遮拦不住", "再难支撑"]]


def s_of(verdict, base):
    """F1 方向修正（纯函数）：base=round(强度×修正, 2)（胜方侧强度）→ a 侧 BT 得分 s。

    spec《武评工具实现设计》§82：s 为 a 侧得分、outcome 为其离散化（s≥0.75 win /
    s≤0.35 loss / else draw——展示用）。旧实现恒 s=base（方向不入）→ outcome/WHR 按
    字典序 a 侧恒判胜。修正：verdict=loss（a 为败方）→ s=1−base；win/draw → s=base
    （平=0.5×修正，与旧口径一致）。monkeypatch 本函数恒等返回 base 即旧口径复现
    （重构安全证明：diff 恰为方向翻转）。
    """
    return round(1.0 - base, 2) if verdict == "loss" else base


def build_payload(matches, org_matches, fighters, books, scope=None, event_source=None,
                  field_gaps=None):
    """matches.json payload 组装（meta + matches + org_matches + fighters）。

    W2-C1：scope 口径 meta 加 scope 键（= profile 名，口径与 EX 层一致）并在 note 尾注
    说明裁剪口径；全量口径 meta 形态与现状逐字段一致（无 scope 键，方案 R6）。
    F1：event_source={书: "kb-events"|"registry-events"}（两源并存声明，scope 口径）；
    field_gaps=scope 书目中 0 场入榜的书（诚实声明——不得为凑数放宽裁决）。
    """
    meta = {"generated": today(), "schema": "matches-v2",
            "wordlist": WORDLIST, "scene_splitter": SCENE_SPLITTER,
            "pipeline": "tool-e/clean_matches",
            "books": books,
            "totals": {"matches": len(matches), "fighters": len(fighters)},
            "cleanlog_ref": "ratings-cleanlog.json",
            "note": "软分数 s 为评分唯一输入；L1=双人景 · L2=多人景归位 · 无明文不打分"}
    if scope is not None:
        meta["scope"] = scope["profile"]
        meta["note"] += (f"；scope={scope['profile']}：仅收 scope 内书目"
                         f"（{'、'.join(books) or '∅'}）的对局")
    if event_source is not None:
        meta["event_source"] = event_source
        reg_books = [b for b, s in event_source.items() if s == "registry-events"]
        if reg_books:
            meta["note"] += (f"；事件源两源并存：{'、'.join(reg_books)}=registry/events 新事件层"
                             "（event-v1，D12 同源适配，outcome 通道裁决），其余=kb 事件表（未动）")
    if field_gaps:
        meta["field_gaps"] = list(field_gaps)
        meta["note"] += f"；field_gaps：{'、'.join(field_gaps)} 无入榜对局（裁决归位不了不硬拆）"
    return {"meta": meta, "matches": matches, "org_matches": org_matches,
            "fighters": sorted(fighters)}


def main() -> int:
    # W2-C1：--scope 解析（--scope all / 不传 = 全量口径，None；同 W0-T3a/T3b）
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    # F1：可用源书（scope 口径并集 registry 新源 3 书；全量口径 lit_books()——R6 不消费新源）
    books = select_books(available_books(scope), scope)
    book_idx = {b: i for i, b in enumerate(books)}
    set_alias_map(books)

    matches, org_matches = [], []
    fighters = set()
    log = {"kept": {"L1": 0, "L2": 0, "L3": 0},
           "dropped": {"self_pair": 0, "no_verdict": 0, "group_label": 0, "in_quote": 0,
                       "dropped_events": 0, "reg_single_side": 0, "reg_non_person": 0},
           "transferred": {"org": 0}, "downgraded": {"attribution_fallback": 0},
           "scenes": {"count": 0, "max_persons": 0},
           "wordlist_hit": Counter()}
    mid = 0
    max_scene_persons = 0
    source_map = {}

    for book in books:
        # F1：两源并存分派（旧表书=kb-events 原样；无旧表书=registry-events 新源；全量不读新源）
        evs, src = load_book_events(book, scope=scope, log=log)
        if src is None:
            continue
        source_map[book] = src
        if src == "registry-events":
            reg_n = len(evs)
            print(f"[clean] {book}: registry/events 新源适配 {reg_n} 行（gate/dropped 计入日志）")

        # 场景文本：旧书读 kb/tagged（行号=物理行）；新源书读 wuxia-kb/tagged（[N] 段号，
        # 与 registry loc 对齐）——(chap, line) 键同构
        text_by_line = {(c, l): t for c, l, t in
                        (read_tagged(book) if src == "kb-events" else read_wxkb_tagged(book))}
        by_chap = defaultdict(list)
        for e in evs:
            by_chap[e["chap"]].append(e)

        for chap in sorted(by_chap):
            group = sorted(by_chap[chap], key=lambda e: e["line"])
            scenes, cur, cur_set = [], [], set()
            for e in group:
                pair = {e["a"], e["b"]}
                if cur:
                    gap = e["line"] - cur[-1]["line"]
                    last_pair = {cur[-1]["a"], cur[-1]["b"]}
                    # 在场感知重切：与上一事件对有交集 且 行距≤GAP 且 景人数≤8 才续景
                    if gap > GAP or not (pair & last_pair) or len(cur_set | pair) > 8:
                        scenes.append(cur)
                        cur, cur_set = [], set()
                cur.append(e)
                cur_set |= pair
            if cur:
                scenes.append(cur)

            for si, scene in enumerate(scenes):
                persons = {x for e in scene for x in (e["a"], e["b"]) if x}
                max_scene_persons = max(max_scene_persons, len(persons))
                log["scenes"]["count"] += 1
                log["scenes"]["max_persons"] = max(log["scenes"]["max_persons"], len(persons))
                if len(persons) < 2:
                    continue

                lines = sorted({l for e in scene for l in range(e["line"] - 2, e["line"] + 3)})
                text = "".join(text_by_line.get((chap, l), "") for l in lines)
                layer = "L1" if len(persons) == 2 else "L2"

                mods = [name for name, kws in MODIFIERS if any(k in text for k in kws)]
                mult = 1.0
                for mo in mods:
                    mult *= MOD_MULT.get(mo, 1.0)
                has_draw = any(k in text for k in DRAW_WORDS)
                has_zhabai = any(k in text for k in MODIFIERS[3][1])

                pairs = Counter()
                for e in scene:
                    if e["a"] != e["b"]:
                        pairs[frozenset((e["a"], e["b"]))] += 1

                for pair_fs, _c in pairs.most_common():
                    pair = set(pair_fs)
                    aa, bb = sorted(pair)
                    # C0：自对丢弃（别名归并后同名）与组织转记
                    if aa == bb:
                        log["dropped"]["self_pair"] += 1
                        continue
                    if is_org(aa) or is_org(bb):
                        org_matches.append({"a": aa, "b": bb, "book": book,
                                            "loc": f"{chap:03d}:{scene[0]['line']:03d}",
                                            "source": "E1-org", "note": "组织对局转记门派恩怨"})
                        log["transferred"]["org"] += 1
                        continue

                    # 裁决：① 事件方向动词 → ①b 事件层 outcome（F1 新源）→ ② 词表近名兜底
                    #（L1）→ 平词/outcome 平（L1）→ None（无明文不打分）
                    res = pair_verdict(scene, pair, aa, bb, text, layer, has_draw)
                    if res is None:
                        log["dropped"]["no_verdict"] += 1
                        continue
                    verdict, strength, trust, via = res

                    log["wordlist_hit"][via or "词表"] += 1
                    if has_zhabai and verdict != "draw":
                        verdict, strength = "draw", 0.5
                    if "诈败" in mods and verdict != "draw":
                        verdict = "draw"
                    if layer == "L2" and via == "词表近名兜底":
                        mult *= 0.6
                    # F1 方向修正（设计文档 §82：s 为 a 侧 BT 得分，outcome 为其离散化）：
                    # 旧实现 s=强度×修正 只记强度不带方向，outcome/WHR 按 a 侧（字典序在先）
                    # 恒判胜——与明文相反（基线审计 65/129 场，如「朱翊钧杀卓继贤」记卓继贤
                    # 胜）。修正：败方在 a → s=1−强度×修正；胜方在 a → s=强度×修正；平不动。
                    s = s_of(verdict, round(min(1.0, strength) * mult, 2))
                    outcome = "win" if s >= 0.75 else ("loss" if s <= 0.35 else "draw")
                    confidence = "high" if (trust == "high" and strength >= 1.0) else ("medium" if trust == "medium" else "low")
                    mid += 1
                    matches.append({
                        "id": f"M{mid:03d}", "a": aa, "b": bb, "outcome": outcome,
                        "s": s, "weight": s, "confidence": confidence,
                        "layer": layer, "trust": trust, "via": via,
                        "modifiers": mods, "kind": "单挑" if layer == "L1" else "围攻",
                        "book": book, "loc": f"{chap:03d}:{scene[0]['line']:03d}",
                        "scene": f"S{book_idx[book]:02d}{chap:03d}-{si + 1:03d}",
                    })
                    fighters.update(pair)
                    log["kept"][layer] += 1

    # F1：scope 口径 0 场入榜书如实声明（无源或有源裁决全丢——不凑数）
    field_gaps = None
    if scope is not None:
        field_gaps = [b for b in BOOKS if esc.in_scope(b, scope)
                      and b not in {m["book"] for m in matches}] or None
    payload = build_payload(matches, org_matches, fighters, books, scope=scope,
                            event_source=source_map if scope is not None else None,
                            field_gaps=field_gaps)
    out = SITE_DATA / "matches.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    scope_note = f"（scope={scope['profile']}）" if scope is not None else ""
    print(f"-> {out} · 对局 {len(matches)} · 参战 {len(fighters)}{scope_note}")
    print(f"   日志: {json.dumps(log['kept'])} / 丢 {json.dumps(log['dropped'])} / 最大景人数 {max_scene_persons}")

    # cleanlog 落盘（wordlist Counter → dict；scope 口径补 scope/books/event_source，
    # method 页消费 kept/dropped 键不变）
    log2 = dict(log)
    log2["wordlist_hit"] = dict(log["wordlist_hit"])
    if scope is not None:
        log2["scope"] = scope["profile"]
        log2["books"] = books
        log2["event_source"] = source_map
        if field_gaps:
            log2["field_gaps"] = list(field_gaps)
    (SITE_DATA / "ratings-cleanlog.json").write_text(
        json.dumps(log2, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
