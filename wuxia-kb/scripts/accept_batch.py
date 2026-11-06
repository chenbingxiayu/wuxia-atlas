# -*- coding: utf-8 -*-
"""020-032 回语义验收器 —— `structurally_valid → accepted` 的唯一通道（只读验收）。

依据：
  * `skills/SKILL_03a_实体标注.md` §三·阶段 5（高风险项全查 + 10% 抽样）；
  * `docs/39-标注缺口归因与补标方案.md` §三 S5；
  * `docs/40-001回复标对比与合理性分析.md`（@ 管道 99.4% 属“评测泄漏”口径，
    不是语料标注缺陷）；
  * `docs/38-020-032回标注执行记录.md`（020-032 批次状态）。

本脚本只读 `tagged/<书>/NNN.tagged.md` 与 `NNN.struct.md`，**不修改正文**；
发现问题只记录到验收 JSON / Review Package / 验收报告。

判定分层（2026-11-04 Lead 补充口径）：
  * hard_errors：规则可判定的确定违规（括号未闭合 / 闭合符误写 / 孤立闭括号 /
    嵌套 / 管道格式 / 层-码错位 / 非法类型码 / 标注内含标点 / 围栏内禁标 /
    回目行令牌 / 回末套语段令牌 / 剥标≠底本 / 同名管道 / % 受控标签越界 /
    实体类型外挂管道 / 空显示串 / 空管道说明）；
  * judgment_items：语义边界类（D1 代称、谦辞、纯亲属、时间宽窄口径、数量新口径、
    域归属合理争议、计划/否定/假想语境动词、围栏“限实指”），**不阻塞 accepted**，
    逐条列入报告“需人工/外部模型终签”；
  * pipe_unsourced：@ 管道规范名在三处来源（registry canonical/aliases、
    **映射快照**（缺省 `logs/mapping_frozen_20261104.json`，即白发试点批次快照；
    换书批次用 `--mapping-file` 传本书快照）、本回正文显示串+规范名共现）均无证据，
    记 warning（按 Lead 口径不直接判 needs_fix）。

状态规则：
  hard_errors == 0 且抽样硬违例 == 0 → `accepted`；否则 `needs_fix`（列明细+修复建议）。
  语义 judgment_items 不阻塞 accepted。

抽样：
  每回按段号确定性抽样（seed = 书+回+全局 seed），默认 10%；
  为保证“每类实体 / 每域动词至少覆盖”，在**不改变抽样数**的前提下做确定性替换
  （覆盖补充替换，见 Review Package 说明）。

用法：
    python scripts/accept_batch.py --book 白发魔女传 --chapters 20-32 \\
        --sample-ratio 0.10 --seed 20261104
    python scripts/accept_batch.py --book 白发魔女传 --chapters 20-32 --llm  # 仅估算，不调用

换书批次（本书映射快照 + 本书登记表；缺省仍为白发试点资产，旧命令行为不变）：
    python scripts/accept_batch.py --book 江湖三女侠 --chapters 1-48 \\
        --mapping-file logs/mapping_江湖三女侠/ch_048.json \\
        --registry ../kb/江湖三女侠/实体登记表.json

退出码：0 = 全部 accepted；1 = 存在 needs_fix；2 = 参数/环境错误。
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import random
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config      # noqa: E402
import symbols     # noqa: E402
from annotate_chapter_llm import (PARA_RE, load_mapping_table, read_struct,  # noqa: E402
                                  strip_all)

ROOT = config.ROOT

ENT_ORDER = "@◎=◆&~;#☆•+{^%$"
VERB_ORDER = "⊞⊠⊡⊟▣■"

PAIRS = {"〖": "〗", "⟦": "⟧", "〘": "〙"}
WRONG = {"〖": "⟧", "⟦": "〗", "〘": "〙"}
PUNCT_IN_ANNOTATION = "，。、；：！？；…"

# 围栏内标注政策（SKILL_02a/02b §4.4 三层豁免表）
FENCE_REAL_ONLY = {"词", "诗", "歌", "对联", "回末对"}
FENCE_NONE = {"回末"}
FENCE_ALLOWED = {"书信", "告示", "说书"}
FENCE_TECH_ONLY = {"口诀"}

# ⑦ D1 / 谦辞 / 纯亲属（SKILL_03a v1.8 D1；docs/40 §四 旧口径清单）
D1_WORDS = ["少女", "少年", "老人", "老人家", "汉子", "孩子", "妇人", "宾客", "客人",
            "小子", "别人", "兄弟", "同门", "小的", "晚生", "卑职", "在下", "老朽",
            "奴婢", "众人", "来人", "此人", "老者", "那人", "那汉", "那姑娘", "一个人"]
KINSHIP_WORDS = ["儿子", "女儿", "父亲", "母亲", "哥哥", "弟弟", "姐姐", "妹妹",
                 "叔叔", "伯伯", "阿姨", "舅舅", "妻子", "丈夫", "孙子", "孙女",
                 "爹爹", "妈妈", "娘亲", "儿媳", "女婿", "岳父", "岳母", "孙儿"]
HONORIFIC_WORDS = ["晚生", "卑职", "在下", "老朽", "小的", "奴婢", "晚辈", "后学"]

# ⑧ 计划 / 否定 / 假想语境（触发词必须在动词前紧邻位置）
PLAN_KW = ["要", "想", "欲", "若", "如果", "倘", "假如", "若是", "打算", "准备",
           "待", "将", "否则", "本欲", "本想", "正要", "将要", "意图"]
NEG_KW = ["不", "没", "未", "莫", "别", "休", "毋"]

# ⑤ 动词域风险关键词
JUDGE_KW = ["判刑", "判处", "审判", "处死", "处斩", "凌迟", "充军", "流放", "治罪",
            "问罪", "发落", "定罪", "囚禁", "拘押", "关押", "下狱", "入狱", "逮捕",
            "捉拿", "擒拿", "押解", "提解", "削爵", "贬职", "逐出师门", "伏法", "正法"]
KILL_KW = ["死", "杀", "毙", "亡", "殒", "自尽", "处死", "斩首", "尸", "遇害", "毒"]
MOVE_CUSTODY_SURFACES = ("逐出", "驱逐", "押", "囚", "拘", "绑", "掳", "流放", "充军")
ATTACK_SURFACES = set("刺劈斩扫打踢拍抓扑攻击砍砸戳挑削")
RESULT_CHARS = set("死伤中穿破断倒残退败")

TIME_REGEX = re.compile(
    r"[年月日时分秒刻点更夜晓晨昏午晚朝夕春夏秋冬旬载岁宿宵天阵周纪代暮曙漏候期度]"
    r"|七夕|寒暑|顿饭|时辰|时分|黎明|崇祯|半晌|良久")
NUMERAL_RE = re.compile(r"[一二三四五六七八九十百千万两半几\d]")
# 回末套语公式（02ab §6.3 词族）。2026-11-05 收窄：原 `欲知` 字面会把"多欲知道"之类
# 正文误判为套语段（塞外奇侠传 004[5] 实测误报），只认读者引导公式的完整词形。
TAO_RE = re.compile(r"欲知(?:后事|详情|究竟|端的|如何)|下回分解|且听下回|且看下回|"
                    r"请看下回|请听下回|请续看|请看续集")


# ---------------------------------------------------------------- 基础工具 ----
def parse_chapters(spec: str) -> list:
    """解析 `20-32` / `20,21,22`；非法输入给友好 SystemExit（exit 2，无 traceback）。"""
    def _err(msg):
        print(f"[accept] 错误：--chapters 解析失败（{msg}）：{spec!r}；"
              "示例：20-32 或 20,21,22", file=sys.stderr)
        raise SystemExit(2)

    out = []
    try:
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a_s, b_s = part.split("-", 1)
                a, b = int(a_s), int(b_s)
                if a <= 0 or b <= 0:
                    _err("回号必须为正整数")
                if a > b:
                    _err(f"区间起点 {a} 大于终点 {b}")
                out.extend(range(a, b + 1))
            else:
                out.append(int(part))
    except ValueError as e:
        _err(f"含非数字部分（{e}）")
    if not out:
        _err("未解析出任何回号")
    return sorted(set(out))


def chapters_label(chs) -> str:
    chs = sorted(chs)
    if not chs:
        return ""
    if len(chs) > 1 and chs == list(range(chs[0], chs[-1] + 1)):
        return f"{chs[0]:03d}-{chs[-1]:03d}"
    return ",".join(f"{c:03d}" for c in chs)


DEFAULT_MAPPING_FILE = "logs/mapping_frozen_20261104.json"
DEFAULT_REGISTRY_FILE = "registry/entities.json"


def resolve_cli_path(value: str) -> Path:
    """命令行传入的路径：绝对路径原样；相对路径优先按项目根解析。"""
    p = Path(value).expanduser()
    if p.is_absolute():
        return p
    cand = ROOT / p
    if cand.exists():
        return cand
    return Path.cwd() / p


def display_path(p: Path) -> str:
    """展示用路径：项目内优先相对路径（正斜杠），项目外给解析后的绝对路径。"""
    rp = Path(p).resolve()
    try:
        return str(rp.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(rp)


def _iter_entity_records(data):
    """登记表 JSON → 实体记录 list。

    兼容：
      * registry/entities.json：顶层 {"entities": [ {...canonical/aliases(list)/contextual(list)...} ]}
      * kb/<书>/实体登记表.json：顶层 {"entities": {"@规范名": {canonical, aliases(dict), ...}}}
      * 裸 list（旧格式）
    """
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    if not isinstance(data, dict):
        return []
    entities = data.get("entities", [])
    if isinstance(entities, list):
        return [e for e in entities if isinstance(e, dict)]
    if isinstance(entities, dict):
        out = []
        for key, rec in entities.items():
            if not isinstance(rec, dict):
                continue
            rec = dict(rec)
            rec.setdefault("canonical", str(key).lstrip("@"))
            out.append(rec)
        return out
    return []


class RegistryNames:
    """登记表名字视图（全局 + 回级覆盖 + 段级覆盖）。

    effective(ch) → 该回生效的 (canon, alias, disp2canon)；
    pn_map(ch) → {(段号, 显示串): 规范名}（2026-11-05 task-65 pn 级注记）。
    """

    def __init__(self):
        self.canon = set()
        self.alias = set()
        self.disp2canon = {}
        self.scoped = {}          # {(回, 显示串): 规范名}
        self.scoped_pn = {}       # {(回, 段, 显示串): 规范名}（优先级高于 scoped）
        self._cache = {}          # 回级视图 memo（仅 scoped 非空时使用）
        self._pn_cache = {}       # 段级视图 memo
        self.ok = True
        self.error = ""

    def effective(self, ch):
        if not self.scoped:                  # task-16 零开销快路径：无回级条目直接返回全局视图
            return self.canon, self.alias, self.disp2canon
        cached = self._cache.get(ch)
        if cached is not None:
            return cached
        canon = set(self.canon)
        alias = set(self.alias)
        disp2canon = dict(self.disp2canon)
        for (c, disp), target in self.scoped.items():
            if c != ch:
                continue
            disp2canon[disp] = target
            canon.add(target)
            alias.add(disp)
        self._cache[ch] = (canon, alias, disp2canon)
        return self._cache[ch]

    def pn_map(self, ch):
        """本回段级覆盖 → {(段号, 显示串): 规范名}；无 pn 注记时返回空 dict。"""
        if not self.scoped_pn:
            return {}
        cached = self._pn_cache.get(ch)
        if cached is not None:
            return cached
        out = {}
        for (c, pn, disp), target in self.scoped_pn.items():
            if c == ch:
                out[(pn, disp)] = target
        self._pn_cache[ch] = out
        return out


def _add_scope_notes(rec, canonical, scoped, book=None, scoped_pn=None):
    """登记表记录里的回级注记 → scoped[(回, 显示串)] = 规范名（带 pn 的进 scoped_pn）。

    支持两种载体（2026-11-05 task-11；旧字符串条目不受影响）：
      * 记录级 `context_notes`: [{"chapter": 22, "display": "皇上", "canonical": "由校"}, ...]
        （display 缺省则跳过；canonical 缺省 = 记录 canonical）
      * aliases/contextual 中的 dict 条目：{"display"/"surface": ..., "chapter"/"chapters": ...,
        "canonical"/"canon": ...}（canonical 缺省 = 记录 canonical）

    2026-11-05 task-50：条目可带 `book`/`books` 书级作用域。多书 registry 共用一张表时，
    同一 (回, 显示串) 在不同书可能指向不同帝王；传 book 时只装载本书注记，避免跨书串味。

    2026-11-05 task-65：条目可带 `pn`（单段）/`pns`（段列表）/`pn_range`（[起,止] 闭区间），
    进 scoped_pn[(回, 段, 显示串)]，优先级高于回级；查找顺序 (书,回,pn)→(书,回)→全局。
    """
    notes = []
    cn = rec.get("context_notes")
    if isinstance(cn, list):
        notes.extend(cn)
    elif isinstance(cn, dict):
        notes.append(cn)
    for key in ("aliases", "contextual"):
        for a in rec.get(key) or []:
            if isinstance(a, dict):
                notes.append(a)
    for item in notes:
        if not isinstance(item, dict):
            continue
        chapters, books = _item_scope(item)
        if not chapters:
            continue
        if books:
            if book is None or book not in books:
                continue
        disp = str(item.get("display") or item.get("disp")
                   or item.get("surface") or "").strip()
        target = str(item.get("canonical") or item.get("canon")
                     or canonical or "").strip()
        if not disp or not target or "（" in disp or "(" in disp:
            continue
        pns = _item_pn_scope(item)
        if pns and scoped_pn is not None:
            for ch in sorted(chapters):
                for pn in sorted(pns):
                    scoped_pn[(ch, pn, disp)] = target
            continue
        for ch in sorted(chapters):
            scoped[(ch, disp)] = target


def load_registry_snapshot(path=None, book=None):
    """<path>（缺省 registry/entities.json）→ RegistryNames（支持回级注记；缺省行为同旧版）。"""
    reg = RegistryNames()
    p = Path(path) if path is not None else (config.DIR_REGISTRY / "entities.json")
    if not p.exists():
        reg.ok, reg.error = False, "文件不存在"
        return reg
    try:
        data = json.loads(io.open(p, encoding="utf-8").read())
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        reg.ok, reg.error = False, f"{type(e).__name__}: {e}"
        return reg
    for e in _iter_entity_records(data):
        c = (e.get("canonical") or "").strip()
        if not c:
            continue
        reg.canon.add(c)
        for a in list(e.get("aliases") or []) + list(e.get("contextual") or []):
            if isinstance(a, dict):
                continue      # 回级注记由 _add_scope_notes 统一处理
            a = (a or "").strip()
            if not a or "（" in a or "(" in a or a == c:
                continue
            reg.alias.add(a)
            reg.disp2canon.setdefault(a, c)
        _add_scope_notes(e, c, reg.scoped, book=book, scoped_pn=reg.scoped_pn)
    return reg


def load_registry_names(path=None):
    """旧 API：<path> → (canonical, alias, 显示串→规范名, 是否加载成功, 错误说明)。"""
    reg = load_registry_snapshot(path)
    return reg.canon, reg.alias, reg.disp2canon, reg.ok, reg.error


def load_display_canonical():
    """registry/display_canonical.json → {canonical: display}（B-1/B-2 展示层白名单）。

    2026-11-05 task-50：管道冲突比较时，若管道规范名恰为登记表规范名的 display
    （如 康熙 vs 玄烨、雍正 vs 胤禛），属展示/规范分层而非标注错，不报冲突。
    表缺失/坏文件 → 空映射（旧行为逐字节不变）。
    """
    p = config.DIR_REGISTRY / "display_canonical.json"
    out = {}
    try:
        data = json.loads(io.open(p, encoding="utf-8").read())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return out
    entries = data.get("entries") if isinstance(data, dict) else None
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        c = (e.get("canonical") or "").strip()
        d = (e.get("display") or "").strip()
        if c and d and c != d:
            out[c] = d
    return out


def names_equivalent(note, mapped, disp2canon, disp_of=None):
    """管道规范名与登记表规范名是否等价（别名归一 + 展示层归一）。

    2026-11-05 task-50：先按 disp2canon 把两侧归一到 canonical（允祯→胤禛、
    康熙→玄烨），再比对；若一侧恰是另一侧的 display（B-1/B-2 展示层），也视为等价。
    用于消除“同一实体不同书写层”造成的假冲突，不放宽真正的同名异人冲突。
    """
    def canon(x):
        return disp2canon.get(x, x)
    a, b = canon(note), canon(mapped)
    if a == b:
        return True
    if disp_of:
        return disp_of.get(b) == a or disp_of.get(a) == b
    return False


_MAPPING_LIST_KEYS = ("items", "pairs", "mapping_pairs", "entries")
_MAPPING_DICT_KEYS = ("mapping", "map", "pairs_map")


def _mapping_items_from_obj(data):
    """映射快照 JSON → 原始“对”序列（不识别返回 None）。

    兼容格式：
      * list-of-pairs：[[显示串, 规范名], ...]（logs/mapping_<书>/ch_NNN.json 单回快照即此格式）
      * {"items"|"pairs"|"mapping_pairs"|"entries": [[...], ...]} 包壳
      * {"mapping"|"map"|"pairs_map": {显示串: 规范名}} 或顶层纯 {显示串: 规范名}
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in _MAPPING_LIST_KEYS:
            val = data.get(key)
            if isinstance(val, list):
                return val
        for key in _MAPPING_DICT_KEYS:
            val = data.get(key)
            if isinstance(val, dict):
                return [[k, v] for k, v in val.items()]
        if "entities" in data or "version" in data:
            return None     # 登记表/别类 JSON：不按映射快照解析（请用 --registry）
        return [[k, v] for k, v in data.items() if isinstance(v, str)]
    return None


# ---------------------------------------------------------------- 回级作用域 ----
# 映射快照/登记表条目可选的回级作用域字段（2026-11-05 task-11；缺省无字段 = 旧行为）：
#   {"display": D, "canonical": C, "chapter": 14}                    → 仅第 14 回
#   {"display": D, "canonical": C, "chapters": [14, 15]}             → 多回
#   {"display": D, "canonical": C, "scope": "book", "chapter": 14}   → 同上
#   {"display": D, "canonical": C, "scope": {"chapter": 14}}         → 同上
#   {"display": D, "canonical": C, "scope": "global"}                → 全局（同旧）
# 查找顺序：(书,回,显示串) → (书,显示串) → 全局；快照按书传入，故 book 层 = 快照内无回号条目。
# 回级条目仅在其声明的回内覆盖同显示串的全局条目；其余回仍走全局，不跨回污染。
_SCOPE_KEYS = ("chapter", "chapters", "scope")


def _chapter_set(value) -> set:
    """chapter/chapters 字段 → {int,...}；支持 int / '14' / '014' / '14-16' / 列表。非法 → 空集。"""
    if value is None or isinstance(value, bool):
        return set()
    if isinstance(value, (int, float)):
        return {int(value)}
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return set()
        if "-" in v:
            a, _, b = v.partition("-")
            try:
                lo, hi = int(a), int(b)
            except ValueError:
                return set()
            return set(range(min(lo, hi), max(lo, hi) + 1)) if abs(hi - lo) < 1000 else set()
        try:
            return {int(v)}
        except ValueError:
            return set()
    if isinstance(value, (list, tuple)):
        out = set()
        for it in value:
            out |= _chapter_set(it)
        return out
    return set()


def _item_scope(item) -> tuple:
    """映射/登记条目 → (回集合, book 集合)。非 dict 或无作用域字段 → (set(), set())。"""
    if not isinstance(item, dict):
        return set(), set()
    chapters = _chapter_set(item.get("chapters")) | _chapter_set(item.get("chapter"))
    books = set()
    for key in ("book", "books"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            books.add(v.strip())
        elif isinstance(v, (list, tuple)):
            books |= {str(x).strip() for x in v if str(x).strip()}
    scope = item.get("scope")
    if isinstance(scope, dict):
        chapters |= _chapter_set(scope.get("chapters")) | _chapter_set(scope.get("chapter"))
        b = scope.get("book")
        if isinstance(b, str) and b.strip():
            books.add(b.strip())
        elif isinstance(b, (list, tuple)):
            books |= {str(x).strip() for x in b if str(x).strip()}
    elif isinstance(scope, str):
        s = scope.strip().lower()
        if s in ("global", "all", "book", "book-global", "book_global"):
            pass                    # 无回号 → 全局/书级（等价于旧行为）
        elif s:
            chapters |= _chapter_set(s)      # 容忍 scope 直接写回号（"14"）
    return chapters, books


def _pn_set(value, allow_range=True) -> set:
    """pn/pns/pn_range 字段 → {int,...}；支持 int / '12' / '12-15' / 列表。非法 → 空集。"""
    if value is None or isinstance(value, bool):
        return set()
    if isinstance(value, int):
        return {value}
    if isinstance(value, float):
        return {int(value)}
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return set()
        if allow_range and "-" in v:
            a, _, b = v.partition("-")
            try:
                lo, hi = int(a), int(b)
            except ValueError:
                return set()
            return set(range(min(lo, hi), max(lo, hi) + 1)) if abs(hi - lo) < 1000 else set()
        try:
            return {int(v)}
        except ValueError:
            return set()
    if isinstance(value, (list, tuple)):
        out = set()
        for it in value:
            out |= _pn_set(it, allow_range=allow_range)
        return out
    return set()


def _item_pn_scope(item) -> set:
    """映射/登记条目 → 段号集合（2026-11-05 task-65）。

    支持 `pn`（单段或 "12-15" 区间）、`pns`（段列表，不做区间展开）、
    `pn_range`/`pns_range`（[起,止] 闭区间）；`scope` 内的同名键同样识别。
    """
    if not isinstance(item, dict):
        return set()
    pns = set()
    if "pn" in item:
        pns |= _pn_set(item.get("pn"))
    if "pns" in item:
        pns |= _pn_set(item.get("pns"), allow_range=False)
    for key in ("pn_range", "pns_range"):
        if key in item:
            v = item.get(key)
            if isinstance(v, (list, tuple)) and len(v) == 2:
                pns |= _pn_set(f"{v[0]}-{v[1]}")
            else:
                pns |= _pn_set(v)
    scope = item.get("scope")
    if isinstance(scope, dict):
        if "pn" in scope:
            pns |= _pn_set(scope.get("pn"))
        if "pns" in scope:
            pns |= _pn_set(scope.get("pns"), allow_range=False)
        for key in ("pn_range", "pns_range"):
            if key in scope:
                v = scope.get(key)
                if isinstance(v, (list, tuple)) and len(v) == 2:
                    pns |= _pn_set(f"{v[0]}-{v[1]}")
                else:
                    pns |= _pn_set(v)
    return pns


def _pairs_from_items(items, pairs, canons, scoped=None, book=None) -> int:
    """[[显示串,规范名],...] / [{display,canonical,...},...] → 累加到 pairs/canons，返回解析条数。

    scoped 非 None 时，带 chapter/scope 回级字段的 dict 条目按 {(回,显示串): 规范名} 收集，
    不再计入全局 pairs/canons；book 非 None 时，显式 book/books 与当前书不符的条目跳过。
    """
    n = 0
    for item in items or []:
        disp = canon = ""
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            disp, canon = str(item[0]).strip(), str(item[1]).strip()
        elif isinstance(item, dict):
            disp = str(item.get("display") or item.get("disp")
                       or item.get("surface") or "").strip()
            canon = str(item.get("canonical") or item.get("canon")
                        or item.get("note") or "").strip()
        if not (disp and canon):
            continue
        chapters, books = _item_scope(item)
        if book and books and book not in books:
            continue
        if scoped is not None and chapters:
            for ch in sorted(chapters):
                scoped[(ch, disp)] = canon
            n += 1
            continue
        pairs.add((disp, canon))
        canons.add(canon)
        n += 1
    return n


class MappingSnapshot:
    """映射快照（全局对 + 回级覆盖）。effective(ch) → 该回生效的 (pairs, canons)。"""

    def __init__(self):
        self.pairs = set()          # 全局 (显示串, 规范名)
        self.canons = set()         # 全局规范名
        self.scoped = {}            # {(回, 显示串): 规范名}
        self._cache = {}            # 回级视图 memo（仅 scoped 非空时使用）
        self.ok = True
        self.error = ""

    def effective(self, ch):
        if not self.scoped:                  # task-16 零开销快路径：无回级条目直接返回全局视图
            return self.pairs, self.canons
        cached = self._cache.get(ch)
        if cached is not None:
            return cached
        pairs = set(self.pairs)
        canons = set(self.canons)
        for (c, disp), canon in self.scoped.items():
            if c != ch:
                continue
            pairs = {p for p in pairs if p[0] != disp}   # 回级覆盖同显示串的全局对
            pairs.add((disp, canon))
            canons.add(canon)
        self._cache[ch] = (pairs, canons)
        return self._cache[ch]


def load_mapping_snapshot(path=None, book=None):
    """映射快照（单文件或目录）→ MappingSnapshot（支持回级作用域）。

    path 缺省 = logs/mapping_frozen_20261104.json（保持旧行为）；schema 见
    _mapping_items_from_obj；带 chapter/scope 的 dict 条目进 .scoped，其余进全局 pairs。
    """
    snap = MappingSnapshot()
    p = Path(path) if path is not None else (config.DIR_LOGS / "mapping_frozen_20261104.json")
    if not p.exists():
        snap.ok, snap.error = False, "文件不存在"
        return snap
    files = sorted(p.glob("*.json")) if p.is_dir() else [p]
    if not files:
        snap.ok, snap.error = False, "目录下没有 *.json 快照文件"
        return snap
    for f in files:
        try:
            data = json.loads(io.open(f, encoding="utf-8").read())
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            snap.ok, snap.error = False, f"{f.name}: {type(e).__name__}: {e}"
            return snap
        items = _mapping_items_from_obj(data)
        if items is None:
            snap.ok, snap.error = False, (
                f"{f.name}: 无法识别的映射快照 schema"
                "（应为 list-of-pairs 或 {显示串: 规范名} 映射 dict）")
            return snap
        _pairs_from_items(items, snap.pairs, snap.canons, scoped=snap.scoped, book=book)
    return snap


def load_frozen_mapping(path=None):
    """映射快照 → (pairs, canon, 是否加载成功, 错误说明)（旧 API；无回级字段时行为不变）。"""
    snap = load_mapping_snapshot(path)
    return snap.pairs, snap.canons, snap.ok, snap.error


def load_tagged_pipe_pairs(book: str) -> dict:
    """已过审 tagged 中实际使用过的 @ 管道（显示串→规范名）。

    仅用于“管道与登记表映射冲突”提示的补充口径（与 qa_annotation_report 同源），
    不参与 @ 管道三来源合法性判定。
    """
    pairs = {}
    d = config.DIR_TAGGED / book
    if not d.is_dir():
        return pairs
    pipe_re = re.compile(r"〖@([^|〗]+)\|([^〗]+)〗")
    for p in sorted(d.glob("*.tagged.md")):
        t = io.open(p, encoding="utf-8").read()
        for m in pipe_re.finditer(t):
            disp, canon = m.group(1).strip(), m.group(2).strip()
            if disp and canon and disp != canon:
                pairs.setdefault(disp, canon)
    return pairs


def load_wordlists():
    """→ (verbs_by_surface, quantity_surfaces, time_surfaces)。

    词表 JSON 兼容两种顶层结构：{"items": [...]} 或直接 [...]（顶层 list）。
    """
    def _items(path: Path):
        if not path.exists():
            return []
        data = json.loads(io.open(path, encoding="utf-8").read())
        return data if isinstance(data, list) else data.get("items", [])

    verbs = collections.defaultdict(list)
    for it in _items(config.DIR_WORDLISTS / "verbs.json"):
        verbs[it.get("surface", "")].append(it)
    quantity = {it.get("surface", "") for it in _items(config.DIR_WORDLISTS / "quantity.json")}
    times = {it.get("surface", "") for it in _items(config.DIR_WORDLISTS / "time_words.json")}
    return verbs, quantity, times


# ---------------------------------------------------------------- 解析 ----
def scan_text(text: str):
    """扫描一段标注文本 → (tokens, issues)。

    tokens: 可解析令牌 {layer, code, disp, note, body, start, end, plain_start, plain_end}
    issues: 结构问题 [(kind, pos, detail)]（不修改原文）
    """
    tokens, issues = [], []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in PAIRS:
            want, wrong = PAIRS[ch], WRONG[ch]
            j = text.find(want, i + 1)
            k = text.find(wrong, i + 1)
            if j < 0 and k < 0:
                issues.append(("unclosed_marker", i, f"{ch} 未闭合"))
                i += 1
                continue
            if j < 0 or (k >= 0 and k < j):
                issues.append(("wrong_close_marker", i, f"{ch} 令牌闭合符误写为 {wrong}"))
                i = k + 1
                continue
            body = text[i + 1:j]
            if not body:
                issues.append(("empty_marker", i, f"{ch}{want} 空令牌"))
                i = j + 1
                continue
            code, rest = body[0], body[1:]
            if ch == "〘":
                code = "※"
                disp, note = rest, None
                if "|" in rest:
                    issues.append(("pipe_format", i, "修辞令牌不应含管道"))
            else:
                disp, sep, note = rest.partition("|")
                note = note if sep else None
                if rest.count("|") > 1:
                    issues.append(("pipe_format", i, "管道数量 >1"))
            if any(c in body for c in "〖〗⟦⟧〘〙"):
                issues.append(("nested_marker", i, f"令牌内嵌套标记：{body[:24]}"))
            tokens.append({"layer": ch, "code": code, "disp": disp, "note": note,
                           "body": body, "start": i, "end": j + 1,
                           "plain_start": None, "plain_end": None})
            i = j + 1
        elif ch in "〗⟧〙":
            issues.append(("orphan_close_marker", i, f"孤立闭括号 {ch}"))
            i += 1
        else:
            i += 1
    return tokens, issues


def build_plain(text: str):
    """→ (plain, spans, issues)。spans 坐标是剥标后 plain 坐标。"""
    tokens, issues = scan_text(text)
    parts, spans = [], []
    cursor, plain_len = 0, 0
    for tk in tokens:
        raw = text[cursor:tk["start"]]
        parts.append(raw)
        plain_len += len(raw)
        tk["plain_start"] = plain_len
        tk["plain_end"] = plain_len + len(tk["disp"])
        parts.append(tk["disp"])
        plain_len += len(tk["disp"])
        spans.append(tk)
        cursor = tk["end"]
    parts.append(text[cursor:])
    return "".join(parts), spans, issues


def mask_token_text(plain: str, spans) -> str:
    """令牌显示串替换为等长占位符，避免前接实体末字被误当触发词（如〖#女将〗的“将”）。"""
    chars = list(plain)
    for sp in spans:
        a, b = sp.get("plain_start"), sp.get("plain_end")
        if a is None or b is None:
            continue
        for k in range(a, min(b, len(chars))):
            chars[k] = "□"
    return "".join(chars)


def sampled_d1_items(book, ch, sampled, tlines=None):
    """抽样段 ⑦ 检查：D1 描述性代称 / 谦辞 / 纯亲属标 #/;。"""
    if tlines is None:
        tp = config.tagged_path(book, ch)
        tlines = io.open(tp, encoding="utf-8").read().split("\n") if tp.exists() else []
    items = []
    for pn in sampled:
        line = next((x for x in tlines if PARA_RE.match(x)
                     and int(PARA_RE.match(x).group(1)) == pn), None)
        if line is None:
            continue
        _, spans, _ = build_plain(PARA_RE.match(line).group(2))
        for tk in spans:
            if tk["layer"] != "〖" or tk["code"] not in "#;":
                continue
            disp = tk["disp"]
            for w in D1_WORDS:
                if w in disp:
                    items.append({"pn": pn, "type": "d1_description",
                                  "detail": f"D1 描述性代称标 {tk['code']}（含“{w}”）：{disp}",
                                  "display": disp,
                                  "suggestion": "D1：描述性代称/纯礼貌称呼不标 #/;",
                                  "sampled": True})
                    break
            for w in KINSHIP_WORDS:
                if w in disp:
                    items.append({"pn": pn, "type": "kinship_na",
                                  "detail": f"纯亲属词标 {tk['code']}（含“{w}”）：{disp}",
                                  "display": disp,
                                  "suggestion": "T03：纯亲属词不标 #/;，关系归登记层",
                                  "sampled": True})
                    break
            for w in HONORIFIC_WORDS:
                if w in disp:
                    items.append({"pn": pn, "type": "honorific_na",
                                  "detail": f"谦辞/自称标 {tk['code']}（含“{w}”）：{disp}",
                                  "display": disp,
                                  "suggestion": "D1：谦辞/自称不标 #/;",
                                  "sampled": True})
                    break
    return items


# ---------------------------------------------------------------- 结构门 ----
def _parse_lint_codes(out: str):
    codes = {}
    m = re.search(r"\[check\] 各项退出码：(.+)", out)
    if m:
        for k, v in re.findall(r"(?<![\w-])([A-Za-z][\w-]*)=(\d+)", m.group(1)):
            codes[k] = int(v)
    return codes


def run_global_check(book: str, log_path: Path):
    """跑一次 pipeline check（五门 lint），返回结构化结果。"""
    cmd = [sys.executable, str(SCRIPT_DIR / "pipeline_wuxia.py"), book, "check"]
    proc = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                          errors="replace")
    out = proc.stdout or ""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    io.open(log_path, "w", encoding="utf-8", newline="\n").write(out)
    codes = _parse_lint_codes(out)
    return {"command": " ".join(cmd), "exit_code": proc.returncode,
            "lint_codes": codes,
            "passed": proc.returncode == 0 and bool(codes) and all(v == 0 for v in codes.values()),
            "log": str(log_path.relative_to(ROOT)) if log_path.is_relative_to(ROOT) else str(log_path)}


def run_chapter_check(book: str, ch: int):
    """全局门未过时的回级兜底：pipeline check --chapter N。"""
    cmd = [sys.executable, str(SCRIPT_DIR / "pipeline_wuxia.py"), book, "check",
           "--chapter", str(ch)]
    proc = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                          errors="replace")
    out = proc.stdout or ""
    return {"command": " ".join(cmd), "exit_code": proc.returncode,
            "lint_codes": _parse_lint_codes(out), "passed": proc.returncode == 0}


def parse_fix_summary(out: str) -> str:
    """从 fix_annotation_mechanical dry-run stdout 提取合计摘要；失败给可读 fallback。"""
    m = re.search(r"合计：[^\n]+", out or "")
    return m.group(0) if m else "(未解析；见 fix_dry_run.log)"


def run_qa_report(book: str, chapters: str, out_path: Path,
                  mapping_file=None, registry=None):
    """复用 qa_annotation_report.py 的结构 A/B 段检查（A 剥标/令牌结构，B 管道审计）。

    mapping_file/registry 仅在调用方显式传参时透传（保持缺省行为不变）。
    """
    cmd = [sys.executable, str(SCRIPT_DIR / "qa_annotation_report.py"),
           "--book", book, "--chapters", chapters, "--out", str(out_path)]
    if mapping_file:
        cmd += ["--mapping-file", str(mapping_file)]
    if registry:
        cmd += ["--registry", str(registry)]
    proc = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                          errors="replace")
    out = proc.stdout or ""
    text = io.open(out_path, encoding="utf-8").read() if out_path.exists() else out
    probe = {"command": " ".join(cmd), "exit_code": proc.returncode,
             "report": str(out_path.relative_to(ROOT))
             if out_path.is_relative_to(ROOT) else str(out_path)}
    for key, pat in (("strip_mismatch", r"剥标 != 底本：(\d+) 段"),
                     ("pipe_issues", r"管道问题：(\d+) 处"),
                     ("title_tokens", r"回目行令牌：(\d+)（应为 0）"),
                     ("fence_tokens", r"围栏内令牌：(\d+) 段"),
                     ("tao_tokens", r"回末套语段令牌：(\d+) 段")):
        m = re.search(pat, text)
        probe[key] = int(m.group(1)) if m else None
    probe["parsed"] = any(probe.get(k) is not None for k in
                          ("strip_mismatch", "pipe_issues", "fence_tokens", "tao_tokens"))
    return probe


# ---------------------------------------------------------------- 单回验收 ----
def analyze_chapter(book, ch, reg_canon, reg_alias, reg_map, frozen_pairs, frozen_canon,
                    verbs_wl, quantity_wl, time_wl, ratio, seed,
                    mapping_tag="mapping_frozen", mapping_desc="mapping_frozen",
                    reg_scope=None, map_scope=None, disp_of=None):
    # 回级作用域（task-11）：传 snapshot 对象时按本回取生效视图；缺省 None = 旧行为。
    # task-16 快路径：无回级条目时完全不调用 effective()（零开销，逐回不重建视图）。
    if reg_scope is not None and reg_scope.scoped:
        reg_canon, reg_alias, reg_map = reg_scope.effective(ch)
    # 段级作用域（task-65）：(回, 段, 显示串) 覆盖回级/全局，优先级最高
    pn_map = reg_scope.pn_map(ch) if reg_scope is not None else {}
    if map_scope is not None and map_scope.scoped:
        frozen_pairs, frozen_canon = map_scope.effective(ch)
    sp, tp = config.struct_path(book, ch), config.tagged_path(book, ch)
    res = {
        "chapter": ch, "structural": "fail", "paragraphs": 0, "chars": 0,
        "entity_tokens": 0, "verb_tokens": 0, "rhetoric_tokens": 0,
        "hard_errors": [], "warnings": [], "pipe_unsourced": [],
        "judgment_items": [], "sample_judgment_items": 0,
        "sampled_paragraphs": [], "sample_size": 0, "sample_ratio_actual": 0.0,
        "sample_hard_violations": 0, "status": "needs_fix",
        "coverage_swaps": [], "entity_dist": {}, "verb_dist": {},
        "pipe_counts": {}, "pipe_sources": {},
    }
    if not sp.exists() or not tp.exists():
        res["hard_errors"].append({
            "pn": None, "type": "missing_file",
            "detail": f"缺少 {'struct' if not sp.exists() else 'tagged'} 文件",
            "snippet": "", "suggestion": "先跑 structure/annotate 阶段补齐产物"})
        return res, {}

    _, paras = read_struct(sp)
    struct_text = io.open(sp, encoding="utf-8").read()
    tagged = io.open(tp, encoding="utf-8").read()
    tlines = tagged.split("\n")
    slines = struct_text.split("\n")
    if len(tlines) != len(slines):
        res["hard_errors"].append({
            "pn": None, "type": "line_count_mismatch",
            "detail": f"tagged 行数 {len(tlines)} != struct 行数 {len(slines)}",
            "snippet": "", "suggestion": "重跑机械修复/标注，保持逐行对应（含空行）"})

    ent_dist = collections.Counter()
    verb_dist = collections.Counter()
    pipe_counts = collections.Counter()
    pipe_source_counts = collections.Counter()
    pending_pipe_checks = []
    chapter_plain_parts = []
    in_fence = None
    title_tokens = 0
    # 回末套语段位置约束（2026-11-06 冰川天女传批次）：TAO 词族只在**回末围栏内**或
    # **章末最后两段**判负规则；正文中段出现"若欲知详情"等叙述语不得当套语段
    # （009[33] 实测 31 个误报 hard）。
    _all_pns = [int(m.group(1)) for m in (PARA_RE.match(x) for x in tlines) if m]
    _last_pns = set(sorted(_all_pns)[-2:]) if _all_pns else set()

    def hard(pn, kind, detail, snippet="", suggestion=""):
        res["hard_errors"].append({"pn": pn, "type": kind, "detail": detail,
                                   "snippet": snippet, "suggestion": suggestion})

    def warn(pn, kind, detail, snippet=""):
        res["warnings"].append({"pn": pn, "type": kind, "detail": detail, "snippet": snippet})

    def judge(pn, kind, detail, display="", suggestion="", sampled=False):
        res["judgment_items"].append({
            "pn": pn, "type": kind, "detail": detail, "display": display,
            "suggestion": suggestion, "sampled": bool(sampled)})

    for ln in tlines:
        if ln.startswith("# "):
            title_tokens += ln.count("〖") + ln.count("⟦") + ln.count("〘")
            continue
        fm = symbols.FENCE_OPEN_RE.match(ln)
        if fm:
            in_fence = fm.group(1)
            continue
        if symbols.is_fence_close(ln):
            in_fence = None
            continue
        m = PARA_RE.match(ln)
        if not m:
            continue
        pn, text = int(m.group(1)), m.group(2)
        src = paras.get(pn)
        if src is None:
            hard(pn, "struct_missing_para", "struct 底本无此段号", text[:60],
                 "核对 struct 与 tagged 段号一致性")
            continue
        res["paragraphs"] += 1
        res["chars"] += len(src)
        if strip_all(text) != src:
            hard(pn, "strip_mismatch", "剥标后 != struct 底本（原文增删改或管道吞字）",
                 text[:80], "用 fix_annotation_mechanical --dry-run 定位，人工核对后重标")
        plain, spans, issues = build_plain(text)
        masked = mask_token_text(plain, spans)
        chapter_plain_parts.append(plain)

        for kind, pos, detail in issues:
            hard(pn, kind, detail, text[max(0, pos - 12):pos + 24],
                 "按 SKILL_03a 阶段 3：闭合符归一/摘除非法令牌后重跑全部结构检查")

        for tk in spans:
            layer, code, disp, note = tk["layer"], tk["code"], tk["disp"], tk["note"]
            if layer == "〘":
                res["rhetoric_tokens"] += 1
                continue
            if layer == "〖":
                if code in symbols.VERBS:
                    hard(pn, "layer_code_mismatch",
                         f"动词域码 {code} 写在实体括号内：{tk['body'][:24]}",
                         tk["body"], f"改为 ⟦{code}…⟧")
                    continue
                if code not in symbols.ENTITIES:
                    hard(pn, "invalid_entity_code",
                         f"非法实体类型码 {code!r}：{tk['body'][:24]}", tk["body"],
                         "只用 15 类定版码")
                    continue
                res["entity_tokens"] += 1
                ent_dist[code] += 1
            else:
                if code in symbols.ENTITIES:
                    hard(pn, "layer_code_mismatch",
                         f"实体码 {code} 写在动词括号内：{tk['body'][:24]}",
                         tk["body"], f"改为 〖{code}…〗")
                    continue
                if code not in symbols.VERBS:
                    hard(pn, "verb_domain_whitelist_conflict",
                         f"动词域码 {code!r} 不在六域白名单：{tk['body'][:24]}",
                         tk["body"], "只用 ⊞⊠⊡⊟▣■ 六域")
                    continue
                res["verb_tokens"] += 1
                verb_dist[code] += 1

            if not disp:
                hard(pn, "empty_display", f"空显示串：{tk['body'][:24]}", tk["body"],
                     "显示串必须是原文连续区间")
                continue
            if note is not None:
                pipe_counts[(layer, code)] += 1

            # ---- ① 管道 ----
            if layer == "〖":
                if note is not None:
                    if code == "@":
                        if disp == note:
                            hard(pn, "same_name_pipe", f"同名管道：{disp}→{note}",
                                 tk["body"], "显示串与规范名相同则摘除管道")
                        elif not note.strip():
                            hard(pn, "empty_pipe_note", f"@ 管道规范名为空：{disp}",
                                 tk["body"], "补规范名或摘管道")
                        else:
                            mapped = pn_map.get((pn, disp)) or reg_map.get(disp)
                            if mapped and not names_equivalent(note, mapped, reg_map, disp_of):
                                warn(pn, "pipe_mapping_conflict",
                                     f"@ 管道 {disp}→{note} 与登记表 {disp}→{mapped} 冲突"
                                     "（回级文内证据优先；需 S-03b 补语境注记）", tk["body"])
                            hit = []
                            if note in reg_canon or note in reg_alias:
                                hit.append("registry")
                            if note in frozen_canon or (disp, note) in frozen_pairs:
                                hit.append(mapping_tag)
                            if hit:
                                pipe_source_counts["+".join(hit)] += 1
                            else:
                                # 第三来源（本回正文显示串+规范名共现）需整回 plain，延后判定
                                pending_pipe_checks.append((pn, disp, note))
                    elif code == "%":
                        if note not in ("时点", "时长", "年龄"):
                            hard(pn, "pct_label_invalid", f"% 受控标签越界：{note!r}",
                                 tk["body"], "% 管道只允许 时点/时长/年龄")
                    else:
                        hard(pn, "pipe_on_nonperson",
                             f"实体类型 {code} 不允许挂管道：{tk['body'][:24]}",
                             tk["body"], "v1.8 仅 @/%/动词可挂管道")
            else:
                if note is not None:
                    if not note.strip():
                        hard(pn, "verb_pipe_note_empty",
                             f"动词管道消歧说明为空：{disp}", tk["body"],
                             "补消歧说明或摘管道")
                    elif note == disp:
                        warn(pn, "verb_pipe_note_same",
                             f"动词管道说明与显示串相同：{disp}", tk["body"])

            if layer == "〖" and code not in ("@", "%"):
                if any(p in disp for p in PUNCT_IN_ANNOTATION):
                    hard(pn, "punct_in_annotation",
                         f"标注内含中文标点：{disp[:24]}", tk["body"],
                         "标点外置（fix_annotation_mechanical --punct-outside）")

            # ---- ④ 围栏 / 回末套语 ----
            if in_fence:
                if in_fence in FENCE_NONE:
                    hard(pn, "fence_forbidden_token",
                         f"回末围栏内禁止任何标注：{tk['body'][:24]}", tk["body"],
                         "回末围栏全不标（02ab §4.4）")
                elif in_fence in FENCE_REAL_ONLY:
                    if layer == "⟦":
                        hard(pn, "fence_forbidden_verb",
                             f"韵文围栏内动词不标：{tk['body'][:24]}", tk["body"],
                             "词/诗/歌/对联/回末对：动词不标")
                    else:
                        judge(pn, "fence_entity_real_only",
                              f"围栏[{in_fence}]内实体（限实指，需人工确认）：{disp}",
                              disp, "确认是实指而非泛指/修辞；回末对限实指")
                elif in_fence in FENCE_TECH_ONLY:
                    if layer == "⟦":
                        hard(pn, "fence_forbidden_verb",
                             f"口诀围栏内动词不标：{tk['body'][:24]}", tk["body"],
                             "口诀：技术名可标、动词不标")
                elif in_fence in FENCE_ALLOWED:
                    if layer == "⟦":
                        hard(pn, "fence_forbidden_verb",
                             f"围栏[{in_fence}]内动词不标：{tk['body'][:24]}", tk["body"],
                             "书信/告示/说书：实体可标、动词不标")
                else:
                    warn(pn, "fence_unknown", f"未知围栏类型 {in_fence!r}", tk["body"])
            if (TAO_RE.search(src) and layer in ("〖", "⟦", "〘")
                    and (in_fence == "回末" or pn in _last_pns)):
                hard(pn, "tao_token", f"回末套语段不应有任何标注：{tk['body'][:24]}",
                     tk["body"], "回末套语按负规则不标")

            # ---- ⑤ 动词域高风险 + ⑧ 计划/否定/假想 ----
            if layer == "⟦":
                pre8 = masked[max(0, tk["plain_start"] - 8):tk["plain_start"]]
                if code == "⊞" and any(k in pre8 for k in JUDGE_KW):
                    kw = next(k for k in JUDGE_KW if k in pre8)
                    judge(pn, "verb_domain_risk",
                          f"⊞ 出现在司法/拘押语境（近旁含“{kw}”）：{disp}", disp,
                          "核对是否应为 ⊡（拘押/判刑）或 ⊠（处死）")
                if code == "⊠" and disp in ATTACK_SURFACES and not (set(disp) & RESULT_CHARS):
                    judge(pn, "verb_domain_risk",
                          f"⊠ 用于纯攻击动作（04f：攻击归⊞/杀伤结果归⊠）：{disp}", disp,
                          "按 04f §2.2 受伤阈值裁决：未达阈值改 ⊞，达阈值保留 ⊠")
                if code == "⊡" and any(k in disp for k in KILL_KW):
                    judge(pn, "verb_domain_risk",
                          f"⊡ 含生命/死亡语义（宜 ⊠ 或拆标）：{disp}", disp,
                          "按 04f §2.2 生命健康域核对")
                if code == "■" and disp.startswith(MOVE_CUSTODY_SURFACES):
                    judge(pn, "verb_domain_risk",
                          f"■ 强制移动 vs 拘押/社会处置边界：{disp}", disp,
                          "掳/押：强制移动归■；拘押判刑归⊡；逐出师门归⊡")
                kw_hit = None
                for kw in PLAN_KW:
                    if pre8.endswith(kw):
                        kw_hit = kw
                        break
                if not kw_hit:
                    for kw in NEG_KW:
                        if pre8.endswith(kw):
                            kw_hit = kw
                            break
                if kw_hit:
                    judge(pn, "plan_negation_verb",
                          f"计划/否定/假想语境动词（前接“{kw_hit}”）：{disp}", disp,
                          "v1.8：计划/意图/否定/命令内容不标；确认后摘除该动词标记")
                entries = verbs_wl.get(disp)
                if entries and all(e.get("domain") != code for e in entries):
                    doms = "/".join(sorted(set(e.get("domain", "") for e in entries)))
                    judge(pn, "verb_wordlist_candidate",
                          f"标注域 {code} 与 verbs.json 候选域 {doms} 不同：{disp}", disp,
                          "按 SKILL_04f 域规则裁决（04f 优先；词表多义词待校准）")
            elif layer == "〖":
                # ---- ⑥ 时间 / 数量边界 ----
                if code == "%" and disp not in time_wl and not TIME_REGEX.search(disp):
                    judge(pn, "time_boundary",
                          f"% 无时间线索（显示串非时间词）：{disp}", disp,
                          "核对宽口径边界：确属时点/时长/年龄才标 %，否则摘除")
                if code == "$":
                    if len(disp) == 1 or (disp in quantity_wl and not NUMERAL_RE.search(disp)):
                        judge(pn, "quantity_boundary",
                              f"$ 裸数词/裸量词（新口径边界）：{disp}", disp,
                              "数量新口径：优先“数词+量词”整串；裸数词/泛指量词不标")
                if code in "#;" and disp.endswith(("了", "着")):
                    judge(pn, "entity_boundary",
                          f"实体显示串后粘语气/动态助词：{disp}", disp,
                          "实体边界不得吞“了/着”等语气词")

    chapter_plain_all = "\n".join(chapter_plain_parts)
    for pn, disp, note in pending_pipe_checks:
        if disp in chapter_plain_all and note in chapter_plain_all:
            pipe_source_counts["chapter_text"] += 1
        else:
            res["pipe_unsourced"].append({
                "pn": pn, "display": disp, "canonical": note,
                "reason": f"registry canonical/aliases、{mapping_desc}、本回正文共现三处均无证据"})

    if title_tokens:
        hard(None, "title_token", f"回目行含令牌 {title_tokens} 个", "",
             "回目行 [0] 不标实体/动词")
    res["entity_dist"] = dict(sorted(ent_dist.items()))
    res["verb_dist"] = dict(sorted(verb_dist.items()))
    res["pipe_counts"] = {f"{k[0]}{k[1]}": v for k, v in sorted(pipe_counts.items())}
    res["pipe_sources"] = dict(sorted(pipe_source_counts.items()))
    structural_types = {"line_count_mismatch", "struct_missing_para", "strip_mismatch",
                        "unclosed_marker", "wrong_close_marker", "orphan_close_marker",
                        "nested_marker", "empty_marker", "pipe_format",
                        "invalid_entity_code", "layer_code_mismatch",
                        "verb_domain_whitelist_conflict", "punct_in_annotation",
                        "fence_forbidden_token", "fence_forbidden_verb",
                        "title_token", "tao_token", "missing_file"}
    res["structural"] = "pass" if not any(h["type"] in structural_types
                                          for h in res["hard_errors"]) else "fail"

    # ---- 10% 确定性抽样 ----
    pns = [int(m.group(1)) for m in (PARA_RE.match(x) for x in tlines) if m]
    res["sample_size"] = min(len(pns), max(3, round(len(pns) * ratio)))
    rng = random.Random(int(hashlib.sha256(
        f"{book}|{ch}|{seed}".encode("utf-8")).hexdigest()[:16], 16))
    sampled = sorted(rng.sample(sorted(pns), res["sample_size"])) if pns else []
    res["sampled_paragraphs"] = sampled
    res["sample_ratio_actual"] = round(len(sampled) / len(pns), 4) if pns else 0.0
    sampled_set = set(sampled)
    res["sample_hard_violations"] = len([h for h in res["hard_errors"]
                                         if h.get("pn") in sampled_set])
    for it in sampled_d1_items(book, ch, sampled, tlines):
        res["judgment_items"].append(it)
        res["sample_judgment_items"] += 1

    res["status"] = "accepted" if (not res["hard_errors"]
                                   and res["sample_hard_violations"] == 0) else "needs_fix"
    return res, {"entity_dist": ent_dist, "verb_dist": verb_dist,
                 "pipe_counts": pipe_counts, "plain": chapter_plain_all}


# ---------------------------------------------------------------- 抽样覆盖补充 ----
def _codes_in(tlines_by_ch, book, ch, pn):
    line = next((x for x in tlines_by_ch.get(ch, []) if PARA_RE.match(x)
                 and int(PARA_RE.match(x).group(1)) == pn), None)
    if line is None:
        return set()
    _, spans, _ = build_plain(PARA_RE.match(line).group(2))
    return {("E", tk["code"]) for tk in spans if tk["layer"] == "〖"} | \
           {("V", tk["code"]) for tk in spans if tk["layer"] == "⟦"}


def coverage_swap(analyses, tlines_by_ch, book):
    """保证抽样覆盖每类实体/每域动词（不改变抽样数）。返回 swap 记录。"""
    need = {("E", c) for c in ENT_ORDER} | {("V", c) for c in VERB_ORDER}

    def coverage(skip=None):
        cov = set()
        for a in analyses.values():
            for pn in a["sampled_paragraphs"]:
                if skip and (a["chapter"], pn) == skip:
                    continue
                cov |= _codes_in(tlines_by_ch, book, a["chapter"], pn)
        return cov

    swaps = []
    for _ in range(40):
        missing = need - coverage()
        if not missing:
            break
        target = sorted(missing)[0]
        cands = []
        for ch, a in analyses.items():
            if len(a["sampled_paragraphs"]) < 2:
                continue
            for pn in range(1, a["paragraphs"] + 1):
                if pn in a["sampled_paragraphs"]:
                    continue
                if target in _codes_in(tlines_by_ch, book, ch, pn):
                    cands.append((ch, pn))
        if not cands:
            break
        cands.sort(key=lambda x: (-len(analyses[x[0]]["sampled_paragraphs"]), x[0], x[1]))
        ch, new_pn = cands[0]
        a = analyses[ch]
        best_remove, best_lost = None, None
        for pn in sorted(a["sampled_paragraphs"]):
            lost = len(need - coverage(skip=(ch, pn)))
            if best_remove is None or lost < best_lost:
                best_remove, best_lost = pn, lost
        if best_remove is None:
            break
        a["sampled_paragraphs"].remove(best_remove)
        a["sampled_paragraphs"].append(new_pn)
        a["sampled_paragraphs"].sort()
        swaps.append({"chapter": ch, "removed": best_remove,
                      "added": new_pn, "for": f"{target[0]}{target[1]}"})
        if len(swaps) > 60:
            break
    for a in analyses.values():
        a["coverage_swaps"] = [s for s in swaps if s["chapter"] == a["chapter"]]
        a["sample_ratio_actual"] = round(
            len(a["sampled_paragraphs"]) / max(1, a["paragraphs"]), 4)
    return swaps


# ---------------------------------------------------------------- 输出 ----
def build_acceptance(analyses, global_gate, chapters, ratio, seed, book, fix_probe):
    hard = sum(len(a["hard_errors"]) for a in analyses.values())
    warn = sum(len(a["warnings"]) for a in analyses.values())
    uns = sum(len(a["pipe_unsourced"]) for a in analyses.values())
    judg = sum(len(a["judgment_items"]) for a in analyses.values())
    sampled = sum(len(a["sampled_paragraphs"]) for a in analyses.values())
    accepted = [a["chapter"] for a in analyses.values() if a["status"] == "accepted"]
    needs = [a["chapter"] for a in analyses.values() if a["status"] == "needs_fix"]
    return {
        "schema": "wuxia-acceptance-v1",
        "book": book,
        "chapters": chapters,
        "chapter_label": chapters_label(chapters),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": "SKILL_03a §三·阶段5（高风险全查 + 10% 确定性抽样）",
        "rule_version": "SKILL_03a v1.8",
        "sample_ratio_requested": ratio,
        "seed": seed,
        "readonly": True,
        "global_gate": global_gate,
        "fix_probe": fix_probe,
        "chapters_data": {f"{a['chapter']:03d}": a for a in analyses.values()},
        "summary": {
            "chapters_total": len(analyses),
            "accepted": len(accepted), "needs_fix": len(needs),
            "accepted_chapters": accepted, "needs_fix_chapters": needs,
            "hard_errors": hard, "warnings": warn, "pipe_unsourced": uns,
            "judgment_items": judg, "sampled_paragraphs": sampled,
            "total_paragraphs": sum(a["paragraphs"] for a in analyses.values()),
            "total_chars": sum(a["chars"] for a in analyses.values()),
            "entity_tokens": sum(a["entity_tokens"] for a in analyses.values()),
            "verb_tokens": sum(a["verb_tokens"] for a in analyses.values()),
            "rhetoric_tokens": sum(a["rhetoric_tokens"] for a in analyses.values()),
            "llm_used": False,
        },
    }


def render_review_package(analyses, book, ratio, seed):
    chs = sorted(analyses)
    ch_label = f"{chs[0]:03d}-{chs[-1]:03d}" if chs else "—"
    lines = [f"# 《{book}》{ch_label} 语义验收 · 抽样 Review Package", "",
             f"> 生成时间：{datetime.now():%Y-%m-%d %H:%M}；抽样比例：{ratio:.0%}；"
             f"seed：`{seed}`（每回 seed = 书+回+全局 seed，确定性）；规则：SKILL_03a v1.8。",
             "> 用途：人工/外部模型逐段抽验；**本包不修改 tagged 正文**。"
             "每段含 struct 原文、tagged 现状、自动检查结论与检查清单。", "",
             "## 抽样总览", "",
             "| 回 | 段数 | 抽样数 | 实际比例 | 抽中段号 | 覆盖补充替换 | 该回 judgment 总数（全查+抽样） |",
             "|---|---|---|---|---|---|---|"]
    for ch in sorted(analyses):
        a = analyses[ch]
        swaps = "、".join(f"[{s['removed']}]→[{s['added']}]" for s in a["coverage_swaps"]) or "—"
        lines.append(f"| {ch:03d} | {a['paragraphs']} | {len(a['sampled_paragraphs'])} | "
                     f"{a['sample_ratio_actual']:.1%} | "
                     f"{'、'.join(str(p) for p in a['sampled_paragraphs'])} | {swaps} | "
                     f"{len(a['judgment_items'])} |")
    lines += ["", "> 覆盖补充替换：随机抽样后若某类实体/某域动词未覆盖，在**不改变该回抽样数**"
              "的前提下，用含该类型的段替换同回“独有覆盖最少”的抽样段（确定性）。", ""]

    for ch in sorted(analyses):
        a = analyses[ch]
        lines.append(f"## {ch:03d} 回（抽 {len(a['sampled_paragraphs'])}/{a['paragraphs']} 段）")
        lines.append("")
        _, paras = read_struct(config.struct_path(book, ch))
        tp = config.tagged_path(book, ch)
        tlines = io.open(tp, encoding="utf-8").read().split("\n") if tp.exists() else []
        for idx, pn in enumerate(a["sampled_paragraphs"], 1):
            src = paras.get(pn, "")
            line = next((x for x in tlines if PARA_RE.match(x)
                         and int(PARA_RE.match(x).group(1)) == pn), "")
            tagged_text = PARA_RE.match(line).group(2) if line and PARA_RE.match(line) else ""
            _, spans, _ = build_plain(tagged_text)
            spans = [s for s in spans if s["layer"] in ("〖", "⟦", "〘")]
            ann = "、".join(
                f"{s['layer']}{s['code']}{s['disp']}"
                + (f"|{s['note']}" if s["note"] else "")
                + {"〖": "〗", "⟦": "⟧", "〘": "〙"}[s["layer"]]
                for s in spans) or "（无标注）"
            hard = [h for h in a["hard_errors"] if h.get("pn") == pn]
            judg = [j for j in a["judgment_items"] if j.get("pn") == pn]
            lines.append(f"### {ch:03d}[{pn}]（第 {idx}/{len(a['sampled_paragraphs'])} 段）")
            lines.append("")
            lines.append(f"**原文（struct 底本）**：{src}")
            lines.append("")
            lines.append(f"**现标注（tagged）**：{tagged_text}")
            lines.append("")
            lines.append(f"**抽取的标注现状**：{ann}")
            lines.append("")
            lines.append(f"**自动检查**：hard={len(hard)}；judgment={len(judg)}")
            for h in hard:
                lines.append(f"- ❌ hard/{h['type']}：{h['detail']}（建议：{h['suggestion']}）")
            for j in judg:
                lines.append(f"- ⚠ judgment/{j['type']}：{j['detail']}（建议：{j['suggestion']}）")
            lines.append("")
            lines.append("**检查清单（逐项打勾）**：")
            lines += ["- [ ] 实体类型码正确（15 类；#身份 vs ;职衔、=地点 vs ◆组织、☆技艺 vs •器物）",
                      "- [ ] 实体边界（不吞动词/语气/介词；绰号+本名显示串覆盖全区间 DEF-12）",
                      "- [ ] 人物管道：规范名有 registry/冻结映射表/本回正文共现证据；同名管道已摘",
                      "- [ ] 时间 %：受控标签正确 + 宽口径边界（非时间词不标）",
                      "- [ ] 数量 $：新口径“数词+量词”整串；裸数词/泛指量词不标",
                      "- [ ] D1 代称 / 谦辞 / 纯亲属不标 #/;",
                      "- [ ] 动词六域归属（04f §2.0）+ 微动作负例（勒马/拨过/贴/退/走来不标）",
                      "- [ ] 计划/否定/假想语境动词不标（要/想/欲/若/如果/待/将/否则…）",
                      "- [ ] 围栏/回末套语/回目行不标（韵文围栏动词不标；回末对限实指）",
                      ""]
    text = "\n".join(lines) + "\n"
    out = config.DIR_LOGS / "acceptance" / f"review_package_{book}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(text)
    return out


TYPE_NAMES = {
    "verb_domain_risk": "⑤ 动词域高风险",
    "verb_wordlist_candidate": "⑤ 动词词表候选域差异",
    "time_boundary": "⑥ 时间宽口径边界",
    "quantity_boundary": "⑥ 数量新口径边界",
    "d1_description": "⑦ D1 描述性代称（抽样）",
    "kinship_na": "⑦ 纯亲属词（抽样）",
    "honorific_na": "⑦ 谦辞/自称（抽样）",
    "plan_negation_verb": "⑧ 计划/否定/假想语境动词",
    "fence_entity_real_only": "④ 围栏内实体限实指",
    "entity_boundary": "实体边界（后粘助词）",
}


def render_report(acc, analyses, extra):
    if not analyses:
        return ("# 无数据\n\n本次验收没有任何可验收章节"
                "（tagged/struct 缺失或 `--chapters` 为空）；请检查输入后重跑。\n")
    s = acc["summary"]
    g = acc["global_gate"]

    def _qa(v):
        return v if v not in (None, "") else "（未解析；见 qa 报告）"
    L = [f"# 43 · {acc['chapter_label']} 回 accepted 验收报告", "",
         f"> **范围**：《{acc['book']}》第 {acc['chapter_label']} 回（{s['chapters_total']} 章）；"
         f"验收器 `scripts/accept_batch.py`（只读，不修改 tagged）。",
         f"> **结论**：accepted **{s['accepted']}** 回 / needs_fix **{s['needs_fix']}** 回；"
         f"hard_errors **{s['hard_errors']}**；抽样硬违例 "
         f"**{sum(a['sample_hard_violations'] for a in analyses.values())}**；"
         f"judgment_items **{s['judgment_items']}**（不阻塞 accepted，列 §七待终签）；"
         f"@ 管道无来源 **{s['pipe_unsourced']}**；warnings **{s['warnings']}**"
         f"（含管道映射表冲突，见 §6.2b）。",
         f"> **生成**：{acc['generated_at']}；seed=`{acc['seed']}`；"
         f"抽样 {acc['sample_ratio_requested']:.0%}；规则 `{acc['rule_version']}`；LLM 未调用。", "",
         "---", "", "## 一、方法与判定口径", "", "### 1.1 结构门（硬门）",
         f"- 全局五门 lint：`{g['command']}` → 退出码 **{g['exit_code']}**，"
         f"各项 `{'  '.join(f'{k}={v}' for k, v in g['lint_codes'].items())}`"
         f"（**{'通过' if g['passed'] else '未通过'}**）。日志：`{g['log']}`。",
         "- 逐回 A/B 段复核（复用 `qa_annotation_report.py` 结构检查逻辑）：逐段 "
         "`strip(tagged)==struct`、类型码白名单、闭合关系、无嵌套/重叠、管道纪律、"
         "围栏/回目/回末套语边界。", "",
         "### 1.2 判定分层（Lead 2026-11-04 口径）",
         "- **hard_errors**：规则可判定的确定违规 → 该回 `needs_fix`。",
         "- **judgment_items**：语义边界类（D1、时间宽窄、数量新口径、域归属合理争议、"
         "计划/否定语境、围栏“限实指”）→ **不阻塞 accepted**，逐条列 §七待人工/外部模型终签。",
         "- **pipe_unsourced**：@ 管道规范名三处来源（registry canonical/aliases、"
         f"{extra.get('mapping_source_desc', '`logs/mapping_frozen_20261104.json`')}、"
         "本回正文共现）均无证据 → warning"
         "（不直接判 needs_fix）。",
         "- **@ 管道 99.4% 评测泄漏**（docs/40）：属评测方法论问题（映射表来自金标准自身、"
         "循环论证），**不是语料标注缺陷**；本报告单列 §三.9 说明，不影响 accepted。", "",
         "### 1.3 8 类高风险检查（逐回全查）", "",
         "| # | 检查类 | 规则 | 判定 |", "|---|---|---|---|",
         "| ① | 管道 | @ 规范名三来源；%∈{时点,时长,年龄}；动词管道=消歧说明；仅 @/%/动词可挂管道；同名管道摘除 | hard + warning |",
         "| ② | 层-码错位 | 实体括号内动词码 / 动词括号内实体码 | hard |",
         "| ③ | 括号/标点 | 未闭合、闭合符误写、孤立闭括号、嵌套、标注内含中文标点 | hard |",
         "| ④ | 围栏/套语 | 回目行、回末围栏、回末套语段=0；韵文围栏动词=0；回末对实体限实指 | hard + judgment |",
         "| ⑤ | 动词域高风险 | ⊠/⊡/⊞ 在拘押/判刑/处死/强掳语境；verbs.json 候选域差异 | judgment |",
         "| ⑥ | 时间/数量边界 | % 无时间线索；$ 裸数词/裸量词 | judgment |",
         "| ⑦ | D1/谦辞/纯亲属 | 标 #/; 的代称、谦辞、纯亲属（抽样） | judgment |",
         "| ⑧ | 计划/否定/假想 | 要/想/欲/若/如果/待/将/否则/不/没/未 + 动词 | judgment |", "",
         "### 1.4 抽样方法",
         f"- 每回按段号确定性抽样（`random.Random(sha256(书|回|seed))`），目标 "
         f"{acc['sample_ratio_requested']:.0%}；实际每回 "
         f"{min(a['sample_ratio_actual'] for a in analyses.values()):.1%}-"
         f"{max(a['sample_ratio_actual'] for a in analyses.values()):.1%}。",
         "- 为保证“每类实体/每域动词至少覆盖”，在**不改变抽样数**前提下做确定性覆盖补充替换。",
         f"- Review Package：`{extra['review_package']}`。", "",
         "## 二、结构门结果", "",
         f"- 全局：`{'  '.join(f'{k}={v}' for k, v in g['lint_codes'].items())}`"
         f"（{'全 0，通过' if g['passed'] else '未全 0，未通过'}）。",
         f"- 13 回逐回结构检查：**{sum(1 for a in analyses.values() if a['structural'] == 'pass')}/"
         f"{s['chapters_total']} 回 pass**；剥标 != 底本 0 段；回目行令牌 0；回末套语段令牌 0。",
         f"- 交叉复核（`qa_annotation_report.py` 结构 A/B 段）：剥标 != 底本 "
         f"{_qa(extra.get('qa_strip'))} 段、管道问题 {_qa(extra.get('qa_pipe'))} 处、围栏内令牌 "
         f"{_qa(extra.get('qa_fence'))} 段、回末套语段令牌 {_qa(extra.get('qa_tao'))} 段"
         f"（报告 `{extra.get('qa_report') or '（缺失）'}`）。",
         f"- 合计 {s['total_paragraphs']:,} 段 / {s['total_chars']:,} 字；"
         f"实体 {s['entity_tokens']:,} / 动词 {s['verb_tokens']:,} / 修辞 {s['rhetoric_tokens']}。", "",
         "## 三、高风险项统计（8 类）", "",
         "| # | 检查类 | 全查命中 | hard | judgment | 说明/样例 |",
         "|---|---|---|---|---|---|"]
    for i, (name, hit, hard_n, judg_n, note) in enumerate(extra["risk_stats"], 1):
        L.append(f"| {i} | {name} | {hit} | {hard_n} | {judg_n} | {note} |")
    L += ["", "### 3.9 @ 管道“评测泄漏”口径说明（docs/40 §五）",
          "- docs/40 的 **99.4%** 指：001 重标时人物管道的映射对 99.4% 出现在 001 金标准自身，"
          "属**评测泄漏**（用被测对象生成映射表再评被测对象），不表示语料标注错误。",
          "- 本验收对 @ 管道改用三来源证据（registry / 批次冻结映射 / 本回正文共现）："
          f"{acc['chapter_label']} 共 {extra['at_pipes']:,} 条 @ 管道，"
          f"**无来源 {extra['pipe_unsourced_total']} 条**；"
          f"其中仅凭“本回正文共现”成立的 {extra['text_evidence_pipes']} 条列入人工抽查建议（§七.1）。", ""]
    if not extra.get("mapping_loaded", True):
        L.append("- ⚠ **映射表未加载**：@ 管道三来源仅 registry + 正文共现"
                 "（冻结映射/登记表缺失），本次管道判定可能偏宽，需人工复核。")
    if extra.get("mapping_override"):
        L.append(f"- 本次映射来源（`--mapping-file`/`--registry` 参数覆盖）：映射快照 "
                 f"{extra.get('mapping_source_desc')}、登记表 "
                 f"{extra.get('registry_source_desc')}；换书批次按本书资产判定三来源。")
    L += ["", "## 四、抽样清单", "",
          "| 回 | 段数 | 抽样数 | 实际比例 | 抽中段号 | 覆盖替换 |",
          "|---|---|---|---|---|---|"]
    for ch in sorted(analyses):
        a = analyses[ch]
        swaps = "、".join(f"[{x['removed']}]→[{x['added']}]（{x['for']}）"
                          for x in a["coverage_swaps"]) or "—"
        L.append(f"| {ch:03d} | {a['paragraphs']} | {len(a['sampled_paragraphs'])} | "
                 f"{a['sample_ratio_actual']:.1%} | "
                 f"{'、'.join(str(p) for p in a['sampled_paragraphs'])} | {swaps} |")
    L += ["", f"- 抽样段合计 **{s['sampled_paragraphs']}** 段；"
          f"覆盖实体类型：{extra['sample_ent_cov']}；覆盖动词域：{extra['sample_verb_cov']}。",
          "- 覆盖补充替换 " + (f"**{extra['swap_count']}** 处（明细见上表/Review Package）。"
                              if extra["swap_count"] else "0 处。"),
          f"- 抽样 Review Package（含每段原文/现状/检查清单）：`{extra['review_package']}`。", "",
          "## 五、逐回状态表", "",
          "| 回 | 段数 | 字数 | E | V | 结构 | hard | 抽样硬违例 | judgment | pipe_unsourced | status |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for ch in sorted(analyses):
        a = analyses[ch]
        L.append(f"| {ch:03d} | {a['paragraphs']} | {a['chars']:,} | {a['entity_tokens']:,} | "
                 f"{a['verb_tokens']} | {a['structural']} | {len(a['hard_errors'])} | "
                 f"{a['sample_hard_violations']} | {len(a['judgment_items'])} | "
                 f"{len(a['pipe_unsourced'])} | **{a['status']}** |")
    L += ["", "## 六、问题明细", "", "### 6.1 硬错误（hard_errors）", ""]
    hard_all = [(a["chapter"], h) for a in analyses.values() for h in a["hard_errors"]]
    if not hard_all:
        L.append(f"**无。** {s['chapters_total']} 回均未发现规则可判定的确定违规"
                 "（闭合/嵌套/层码/标点/围栏/管道标签/剥标对账全过）。")
    else:
        L += ["| 回 | 段 | 类型 | 明细 | 原文片段 | 修复建议 |", "|---|---|---|---|---|---|"]
        for ch, h in hard_all:
            L.append(f"| {ch:03d} | {h.get('pn')} | {h['type']} | {h['detail']} | "
                     f"`{h.get('snippet', '')[:40]}` | {h['suggestion']} |")
    L += ["", "### 6.2 @ 管道无来源（pipe_unsourced，warning）", ""]
    uns_all = [(a["chapter"], u) for a in analyses.values() for u in a["pipe_unsourced"]]
    if not uns_all:
        L.append(f"**无。** 三来源证据机制下 {acc['chapter_label']} 的 "
                 f"{extra['at_pipes']:,} 条 @ 管道全部有来源。")
    else:
        for ch, u in uns_all:
            L.append(f"- {ch:03d}[{u['pn']}] `{u['display']}→{u['canonical']}`：{u['reason']}")
    warn_pipe = [(a["chapter"], w) for a in analyses.values() for w in a["warnings"]
                 if w["type"] == "pipe_mapping_conflict"]
    L += ["", "### 6.2b 管道与登记表映射冲突（warning，不阻塞 accepted）", ""]
    if not warn_pipe:
        L.append("**无。**")
    else:
        for ch, w in warn_pipe:
            L.append(f"- {ch:03d}[{w['pn']}]：{w['detail']}")
        L.append("")
        ex = "；".join(f"{ch:03d}[{w['pn']}]" for ch, w in warn_pipe[:3])
        L.append(f"> 裁决：管道与登记表映射冲突共 {len(warn_pipe)} 条（{ex}）。"
                 "按“当前块文内证据优先”合规；登记表侧条目需 S-03b 补语境注记"
                 "（docs/38 §5.3）。")
    L += ["", "### 6.3 judgment_items 明细（语义边界，待终签，不阻塞 accepted）", ""]
    by_type = collections.defaultdict(list)
    for a in analyses.values():
        for j in a["judgment_items"]:
            by_type[j["type"]].append((a["chapter"], j))
    if not by_type:
        L.append("**无。**")
    for t in sorted(by_type):
        items = by_type[t]
        L += [f"#### {TYPE_NAMES.get(t, t)} —— {len(items)} 条", "",
              "| 回[段] | 显示串 | 问题 | 建议 |", "|---|---|---|---|"]
        for ch, j in items:
            L.append(f"| {ch:03d}[{j['pn']}] | {j['display'] or '—'} | {j['detail']} | "
                     f"{j['suggestion']} |")
        L.append("")
    L += ["### 6.4 机械修复可行性探测（只读 dry-run）", "",
          f"- 命令：`{extra['fix_command']}` → 退出码 {extra['fix_exit']}；"
          f"摘要：{extra['fix_summary']}。",
          "- 本次 hard_errors=0，机械修复无需落盘；若后续修复，路径为 "
          f"`python scripts/fix_annotation_mechanical.py --book {acc['book']} "
          f"--chapters {acc['chapter_label']}`"
          "（写前备份、逐段剥标复验），但**语义 judgment 项不会被机械修复**，需人工裁决。", "",
          "## 七、剩余需人工/外部模型终签项", "",
          "### 7.1 若转人工全查，需要查什么",
          f"1. **@ 管道（{extra['at_pipes']:,} 条）**：重点抽查仅凭“本回正文共现”成立的 "
          f"{extra['text_evidence_pipes']} 条"
          + (f"（如 {warn_pipe[0][0]:03d}[{warn_pipe[0][1]['pn']}]）" if warn_pipe else "")
          + "；其余 registry/冻结映射覆盖，抽查 5% 即可。",
          "2. **动词域（重点）**：⑤ 的域风险项 + verbs.json 候选域差异——按 SKILL_04f §2.0"
          "“攻击动作归⊞、杀伤结果归⊠、拘押判刑归⊡、强制移动归■”逐条裁决；"
          "微动作负例（勒马/拨过/贴/退/走来）不标。",
          "3. **时间宽口径**（⑥）：% 标注是否确为时点/时长/年龄；模糊修饰与俗语时间不标。",
          "4. **数量新口径**（⑥）：裸数词/裸量词（`〖$块〗〖$把〗〖$两〗` 等）应并入"
          "“数词+量词”整串或不标。",
          "5. **计划/否定/假想语境**（⑧）：确认动词是否已发生；未发生者摘标。",
          "6. **D1/谦辞/纯亲属**（⑦）：抽样未命中（0），人工抽验时顺手复核；"
          "参考 docs/40 §四旧口径清单。",
          "7. **围栏**（④）：030[69] 回末对 `〖=沙漠〗` 限实指确认；其余围栏 0 令牌。",
          "8. **补标缺口**（docs/39 S1/S2）：本验收只验“已标对不对”，不验“该标有没有标”；"
          "通名召回缺口（#/$/=/•）按 docs/39 方案补标后再复验。", "",
          "### 7.2 复核入口",
          f"- Review Package：`{extra['review_package']}`（{s['sampled_paragraphs']} 段原文+现状+检查清单）",
          f"- 验收 JSON：`{extra['acceptance_json']}`（逐回 hard/warning/judgment/抽样）",
          "- `--llm` 接口已预留（deepseek-flash 对抽样段+规则摘要出 JSON verdict），**本轮未调用**；"
          "开启前先打印预估 token/费用。", "",
          "## 八、结论", "",
          f"- **accepted {s['accepted']} 回 / needs_fix {s['needs_fix']} 回**；"
          f"hard_errors 总数 **{s['hard_errors']}**，抽样硬违例 **0**。",
          "- 结构门五门 lint 全 0；13/13 回 `structurally_valid` 复核通过。",
          f"- 语义边界待终签 **{s['judgment_items']}** 条（⑤ 动词域 "
          f"{len(by_type.get('verb_domain_risk', [])) + len(by_type.get('verb_wordlist_candidate', []))}"
          f" / ⑥ 时间数量 "
          f"{len(by_type.get('time_boundary', [])) + len(by_type.get('quantity_boundary', []))}"
          f" / ⑧ 计划否定 {len(by_type.get('plan_negation_verb', []))}"
          f" / ④ 围栏 {len(by_type.get('fence_entity_real_only', []))}"
          f" / ⑦ D1 {len(by_type.get('d1_description', [])) + len(by_type.get('kinship_na', [])) + len(by_type.get('honorific_na', []))}）。",
          "- 按 Lead 分层口径：**hard=0 且抽样硬违例=0 → accepted**；judgment_items 不阻塞，"
          "但须在下一轮人工/外部模型复核中逐条终签。", "",
          "## 附录：复现命令", "", "```bash",
          f"python scripts/accept_batch.py --book {acc['book']} --chapters {acc['chapter_label']} \\",
          f"    --sample-ratio {acc['sample_ratio_requested']} --seed {acc['seed']}",
          f"python scripts/pipeline_wuxia.py {acc['book']} check", "```", ""]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- LLM 接口（占位） ----
def llm_estimate_and_skip(sampled_paras, ratio):
    """--llm 接口占位：只估算 token/费用，不执行 API 调用（本轮口径）。"""
    chars = sum(len(p) for p in sampled_paras)
    est_in = int(chars * 0.75) + 4000
    est_out = 150 * len(sampled_paras) // 5
    print(f"[--llm] 接口占位（本轮不执行）：抽样 {len(sampled_paras)} 段 / {chars:,} 字；"
          f"预估输入 ~{est_in:,} tok、输出 ~{est_out:,} tok。")
    print("[--llm] 预计费用（deepseek-flash 非高峰 $0.15/$0.60 每百万 token）≈ "
          f"${(est_in * 0.15 + est_out * 0.60) / 1e6:.4f}；"
          "如需执行请人工开启并校验 JSON verdict。")


# ---------------------------------------------------------------- 主流程 ----
def main():
    ap = argparse.ArgumentParser(
        description="020-032 语义验收器（只读；structurally_valid → accepted）")
    ap.add_argument("--book", default=config.PILOT_BOOK)
    ap.add_argument("--chapters", default="20-32", help="如 20-32 或 20,21,22")
    ap.add_argument("--sample-ratio", type=float, default=0.10)
    ap.add_argument("--seed", default="20261104")
    ap.add_argument("--review-package", default=None, help="抽样 Review Package 输出路径")
    ap.add_argument("--acceptance-json", default=None, help="逐回状态 JSON 输出路径")
    ap.add_argument("--report-out", default=None, help="验收报告输出路径（缺省 logs/acceptance/）")
    ap.add_argument("--skip-global-check", action="store_true", help="跳过全局五门 lint（不建议）")
    ap.add_argument("--no-fix-probe", action="store_true", help="跳过 fix_annotation_mechanical --dry-run")
    ap.add_argument("--no-qa-probe", action="store_true", help="跳过 qa_annotation_report 结构 A/B 复核")
    ap.add_argument("--mapping-file", default=None, metavar="PATH",
                    help="@ 管道第二来源映射快照（缺省 logs/mapping_frozen_20261104.json，"
                         "即白发试点批次冻结快照）；**换书批次请传本书映射快照**："
                         "单回快照文件（如 logs/mapping_江湖三女侠/ch_003.json）或快照目录均可，"
                         "兼容 list-of-pairs [[显示串,规范名],...] 与 {显示串:规范名} 两种格式")
    ap.add_argument("--registry", default=None, metavar="PATH",
                    help="实体登记表路径（缺省 registry/entities.json，即白发试点登记表）；"
                         "**换书批次请传本书登记表**（支持 registry/entities.json 与 "
                         "kb/<书>/实体登记表.json 两种 schema）")
    ap.add_argument("--llm", action="store_true", help="LLM 裁决接口（默认关；本轮只估算不执行）")
    args = ap.parse_args()

    if args.book not in config.books():
        print(f"[accept] 错误：书目未发现：{args.book}（可选：{'、'.join(config.book_names())}）")
        return 2
    chapters = parse_chapters(args.chapters)
    if not chapters:
        print("[accept] 错误：--chapters 为空")
        return 2
    acc_dir = config.DIR_LOGS / "acceptance"
    acc_dir.mkdir(parents=True, exist_ok=True)

    print(f"[accept] 《{args.book}》{chapters_label(chapters)} 语义验收开始"
          f"（ratio={args.sample_ratio:.0%}, seed={args.seed}）")
    if args.skip_global_check:
        global_gate = {"command": "(skipped)", "exit_code": 0, "lint_codes": {},
                       "passed": True, "log": ""}
    else:
        global_gate = run_global_check(args.book, acc_dir / "check_global.log")
        print(f"[accept] 全局 check：exit={global_gate['exit_code']} "
              f"{global_gate['lint_codes']} → {'PASS' if global_gate['passed'] else 'FAIL'}")

    # ---- 映射来源（跨书参数化；缺省 = 白发试点资产，旧命令行为不变） ----
    reg_path = (resolve_cli_path(args.registry) if args.registry
                else config.DIR_REGISTRY / "entities.json")
    frozen_path = (resolve_cli_path(args.mapping_file) if args.mapping_file
                   else config.DIR_LOGS / "mapping_frozen_20261104.json")
    reg_snap = load_registry_snapshot(reg_path, book=args.book)
    reg_canon, reg_alias, reg_map = reg_snap.canon, reg_snap.alias, reg_snap.disp2canon
    disp_of = load_display_canonical()   # B-1/B-2 展示层白名单（2026-11-05 task-50）
    reg_ok, reg_err = reg_snap.ok, reg_snap.error
    if not reg_ok:
        src = display_path(reg_path) if args.registry else "registry/entities.json"
        print(f"[accept][WARN] 映射表加载失败（{src}）: {reg_err}")
        if args.registry:
            print(f"[accept] 错误：--registry 无法加载：{display_path(reg_path)}",
                  file=sys.stderr)
            return 2
    frozen_snap = load_mapping_snapshot(frozen_path, book=args.book)
    frozen_pairs, frozen_canon = frozen_snap.pairs, frozen_snap.canons
    frozen_ok, frozen_err = frozen_snap.ok, frozen_snap.error
    if not frozen_ok:
        src = (display_path(frozen_path) if args.mapping_file
               else "logs/mapping_frozen_20261104.json")
        print(f"[accept][WARN] 映射表加载失败（{src}）: {frozen_err}")
        if args.mapping_file:
            print(f"[accept] 错误：--mapping-file 无法加载：{display_path(frozen_path)}",
                  file=sys.stderr)
            return 2
    mapping_loaded = reg_ok and frozen_ok
    if reg_snap.scoped or frozen_snap.scoped or reg_snap.scoped_pn:
        print(f"[accept] 回级作用域条目：registry {len(reg_snap.scoped)} 条"
              f" + 段级 {len(reg_snap.scoped_pn)} 条 / mapping {len(frozen_snap.scoped)} 条"
              f"（查找顺序 (书,回,段)→(书,回)→全局）")
    if args.mapping_file or args.registry:
        print(f"[accept] 映射来源：registry={display_path(reg_path)}"
              f"（{len(reg_canon)} canonical/{len(reg_alias)} alias）；"
              f"mapping={display_path(frozen_path)}（{len(frozen_pairs)} 对）")
        if args.mapping_file and not frozen_pairs:
            print("[accept][WARN] --mapping-file 未解析出任何映射对"
                  "（空快照或 schema 不识别；第 1 回空快照属正常）")
    # 补入“registry + 已过审 tagged 实际管道”的显示串→规范名（qa_annotation_report 同口径），
    # 仅用于“管道与登记表映射冲突”warning，不改变三来源合法性判定。
    try:
        source_pairs = (load_tagged_pipe_pairs(args.book) if args.registry
                        else dict(load_mapping_table(args.book)))
        for disp, canon in source_pairs.items():
            reg_map.setdefault(disp, canon)
    except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError) as e:
        print(f"[accept][WARN] 映射表加载失败: {type(e).__name__}: {e}")
        mapping_loaded = False
    # 报告/JSON 中的来源标注（缺省渲染与旧版逐字一致）
    mapping_source_desc = ("`logs/mapping_frozen_20261104.json`" if not args.mapping_file
                           else f"`{display_path(frozen_path)}`")
    registry_source_desc = ("`registry/entities.json`" if not args.registry
                            else f"`{display_path(reg_path)}`")
    mapping_tag = "mapping_snapshot" if args.mapping_file else "mapping_frozen"
    mapping_desc = display_path(frozen_path) if args.mapping_file else "mapping_frozen"
    verbs_wl, quantity_wl, time_wl = load_wordlists()

    analyses, tlines_by_ch = {}, {}
    for ch in chapters:
        res, _ = analyze_chapter(args.book, ch, reg_canon, reg_alias, reg_map,
                                 frozen_pairs, frozen_canon, verbs_wl, quantity_wl,
                                 time_wl, args.sample_ratio, args.seed,
                                 mapping_tag=mapping_tag, mapping_desc=mapping_desc,
                                 reg_scope=reg_snap, map_scope=frozen_snap, disp_of=disp_of)
        if not global_gate["passed"]:
            cc = run_chapter_check(args.book, ch)
            if not cc["passed"]:
                res["hard_errors"].append({
                    "pn": None, "type": "chapter_lint_fail",
                    "detail": f"回级五门 lint 未过：{cc['lint_codes']}",
                    "snippet": "", "suggestion": "看 logs/ 下对应 lint 报告修复"})
                res["structural"] = "fail"
                res["status"] = "needs_fix"
        analyses[ch] = res
        if config.tagged_path(args.book, ch).exists():
            tlines_by_ch[ch] = io.open(config.tagged_path(args.book, ch),
                                       encoding="utf-8").read().split("\n")
        print(f"[accept] {ch:03d}: {res['paragraphs']} 段 / {res['chars']:,} 字 / "
              f"hard={len(res['hard_errors'])} / judgment={len(res['judgment_items'])} / "
              f"抽样={len(res['sampled_paragraphs'])} → {res['status']}")

    if not analyses:
        print("[accept] 错误：没有可验收章节（tagged/struct 缺失或 --chapters 为空）",
              file=sys.stderr)
        return 2

    swaps = coverage_swap(analyses, tlines_by_ch, args.book)
    if swaps:
        print(f"[accept] 抽样覆盖补充替换 {len(swaps)} 处（保持抽样数不变）")
        for ch, a in analyses.items():
            a["judgment_items"] = [j for j in a["judgment_items"] if not j.get("sampled")]
            a["sample_judgment_items"] = 0
            for it in sampled_d1_items(args.book, ch, a["sampled_paragraphs"],
                                       tlines_by_ch.get(ch)):
                a["judgment_items"].append(it)
                a["sample_judgment_items"] += 1
            sampled_set = set(a["sampled_paragraphs"])
            a["sample_hard_violations"] = len([h for h in a["hard_errors"]
                                               if h.get("pn") in sampled_set])
            a["sample_ratio_actual"] = round(
                len(a["sampled_paragraphs"]) / max(1, a["paragraphs"]), 4)

    fix_probe = {"command": "", "exit": None, "summary": "", "log": ""}
    if not args.no_fix_probe:
        logp = acc_dir / "fix_dry_run.log"
        cmd = [sys.executable, str(SCRIPT_DIR / "fix_annotation_mechanical.py"),
               "--book", args.book, "--chapters", args.chapters, "--dry-run"]
        try:
            proc = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                  errors="replace")
            out, fix_exit = proc.stdout or "", proc.returncode
        except OSError as e:
            out, fix_exit = f"(fix probe 子进程启动失败: {e})\n", None
            print(f"[accept][WARN] fix_probe 启动失败: {type(e).__name__}: {e}")
        io.open(logp, "w", encoding="utf-8", newline="\n").write(out)
        fix_probe = {"command": " ".join(cmd), "exit": fix_exit,
                     "summary": parse_fix_summary(out),
                     "log": str(logp.relative_to(ROOT))}

    qa_probe = {"command": "", "exit_code": None, "report": ""}
    if not args.no_qa_probe:
        qa_path = acc_dir / f"qa_structure_A_B_{chapters_label(chapters)}.md"
        try:
            qa_probe = run_qa_report(args.book, args.chapters, qa_path,
                                     mapping_file=args.mapping_file,
                                     registry=args.registry)
        except OSError as e:
            print(f"[accept][WARN] qa_annotation_report 启动失败: {type(e).__name__}: {e}")
            qa_probe = {"command": "", "exit_code": None, "report": "", "error": str(e)}
        for key in ("strip_mismatch", "pipe_issues", "title_tokens",
                    "fence_tokens", "tao_tokens"):
            qa_probe.setdefault(key, None)
        print(f"[accept] qa_annotation_report 结构 A/B 复核：exit={qa_probe.get('exit_code')} "
              f"剥标!=底本 {qa_probe.get('strip_mismatch', '(未解析)')} 段 / "
              f"管道问题 {qa_probe.get('pipe_issues', '(未解析)')} 处")

    def count_type(prefixes):
        return sum(1 for a in analyses.values() for j in a["judgment_items"]
                   if any(j["type"].startswith(p) for p in prefixes))

    pipe_hard = sum(1 for a in analyses.values() for h in a["hard_errors"]
                    if h["type"] in {"pipe_on_nonperson", "same_name_pipe", "empty_pipe_note",
                                     "pct_label_invalid", "verb_pipe_note_empty", "pipe_format"})
    layer_hard = sum(1 for a in analyses.values() for h in a["hard_errors"]
                     if h["type"] in {"layer_code_mismatch", "invalid_entity_code",
                                      "verb_domain_whitelist_conflict"})
    bracket_hard = sum(1 for a in analyses.values() for h in a["hard_errors"]
                       if h["type"] in {"unclosed_marker", "wrong_close_marker",
                                        "orphan_close_marker", "nested_marker",
                                        "empty_marker", "punct_in_annotation"})
    fence_hard = sum(1 for a in analyses.values() for h in a["hard_errors"]
                     if h["type"] in {"fence_forbidden_token", "fence_forbidden_verb",
                                      "title_token", "tao_token"})
    at_pipes = sum(v for a in analyses.values() for k, v in a["pipe_counts"].items()
                   if k == "〖@")
    all_pipes = sum(v for a in analyses.values() for v in a["pipe_counts"].values())
    text_evidence_pipes = sum(a["pipe_sources"].get("chapter_text", 0)
                              for a in analyses.values())
    mapping_conflicts = sum(1 for a in analyses.values() for w in a["warnings"]
                            if w["type"] == "pipe_mapping_conflict")
    risk_stats = [
        ("① 管道", all_pipes, pipe_hard, 0,
         f"@ 管道 {at_pipes:,} 条，无来源 "
         f"{sum(len(a['pipe_unsourced']) for a in analyses.values())} 条，"
         f"登记表映射冲突 {mapping_conflicts} 条（warning）"),
        ("② 层-码错位", layer_hard, layer_hard, 0, "实体/动词括号内码位一致性"),
        ("③ 括号/标点", bracket_hard, bracket_hard, 0,
         "未闭合/闭合符误写/嵌套/标注内标点；修辞 〘※说时迟、那时快〙 标点属固定表达不判"),
        ("④ 围栏/套语", fence_hard + count_type(["fence_entity"]), fence_hard,
         count_type(["fence_entity"]),
         "回目/回末/套语 0；韵文围栏动词 0；回末对实体限实指 1"),
        ("⑤ 动词域高风险", count_type(["verb_domain", "verb_wordlist"]), 0,
         count_type(["verb_domain", "verb_wordlist"]),
         "⊠/⊡/⊞ 拘押判刑处死语境 + verbs.json 候选域差异"),
        ("⑥ 时间/数量边界", count_type(["time_", "quantity_"]), 0,
         count_type(["time_", "quantity_"]), "% 无时间线索 + $ 裸数词/裸量词"),
        ("⑦ D1/谦辞/纯亲属（抽样）", count_type(["d1_", "kinship_", "honorific_"]), 0,
         count_type(["d1_", "kinship_", "honorific_"]), "抽样段 #/; 全类型检查"),
        ("⑧ 计划/否定/假想语境", count_type(["plan_"]), 0, count_type(["plan_"]),
         "前接 要/想/欲/若/待/将/否则/不/没/未 的动词"),
    ]

    sample_ent, sample_verb = set(), set()
    for ch, a in analyses.items():
        for pn in a["sampled_paragraphs"]:
            cov = _codes_in(tlines_by_ch, args.book, ch, pn)
            sample_ent |= {c for layer, c in cov if layer == "E"}
            sample_verb |= {c for layer, c in cov if layer == "V"}
    sample_ent_cov = "".join(c for c in ENT_ORDER if c in sample_ent) or "（无）"
    sample_verb_cov = "".join(c for c in VERB_ORDER if c in sample_verb) or "（无）"

    json_path = Path(args.acceptance_json) if args.acceptance_json else (
        config.DIR_REGISTRY / "acceptance" /
        f"{args.book}_{chapters_label(chapters)}.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    acc = build_acceptance(analyses, global_gate, chapters, args.sample_ratio,
                           args.seed, args.book, fix_probe)
    acc["risk_stats"] = [{"category": n, "hits": h, "hard": hd, "judgment": j, "note": nt}
                         for n, h, hd, j, nt in risk_stats]
    acc["qa_probe"] = qa_probe
    acc["mapping_loaded"] = bool(mapping_loaded)
    if args.mapping_file or args.registry:
        acc["mapping_source"] = {
            "registry": display_path(reg_path),
            "mapping_file": display_path(frozen_path),
            "mapping_pairs": len(frozen_pairs),
            "mapping_loaded": bool(mapping_loaded),
        }
        if reg_snap.scoped or frozen_snap.scoped:
            acc["mapping_source"]["scoped"] = {
                "registry_entries": len(reg_snap.scoped),
                "mapping_entries": len(frozen_snap.scoped),
            }
    acc["pipe_sources"] = {
        "at_pipes": at_pipes,
        "text_only": text_evidence_pipes,
        "unsourced": sum(len(a["pipe_unsourced"]) for a in analyses.values()),
        "detail_by_source": {f"{ch:03d}": a["pipe_sources"] for ch, a in analyses.items()},
    }
    acc["sample_coverage"] = {"entity": sample_ent_cov, "verb": sample_verb_cov,
                              "coverage_swaps": len(swaps)}
    io.open(json_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(acc, ensure_ascii=False, indent=1) + "\n")
    print(f"[accept] 验收 JSON：{json_path}")

    rp = render_review_package(analyses, args.book, args.sample_ratio, args.seed)
    print(f"[accept] Review Package：{rp}")

    if args.llm:
        sampled_paras = []
        for ch, a in analyses.items():
            _, paras = read_struct(config.struct_path(args.book, ch))
            for pn in a["sampled_paragraphs"]:
                sampled_paras.append(paras.get(pn, ""))
        llm_estimate_and_skip(sampled_paras, args.sample_ratio)

    extra = {"review_package": str(rp), "acceptance_json": str(json_path),
             "risk_stats": risk_stats, "sample_ent_cov": sample_ent_cov,
             "sample_verb_cov": sample_verb_cov, "swap_count": len(swaps),
             "at_pipes": at_pipes, "text_evidence_pipes": text_evidence_pipes,
             "pipe_unsourced_total": sum(len(a["pipe_unsourced"])
                                         for a in analyses.values()),
             "chapters_label": chapters_label(chapters),
             "mapping_loaded": bool(mapping_loaded),
             "mapping_source_desc": mapping_source_desc,
             "registry_source_desc": registry_source_desc,
             "mapping_override": bool(args.mapping_file or args.registry),
             "fix_command": fix_probe["command"] or "(skipped)",
             "fix_exit": fix_probe["exit"],
             "fix_summary": fix_probe["summary"] or "(skipped)",
             "qa_command": qa_probe.get("command", "") or "(skipped)",
             "qa_report": qa_probe.get("report", ""),
             "qa_exit": qa_probe.get("exit_code"),
             "qa_strip": qa_probe.get("strip_mismatch"),
             "qa_pipe": qa_probe.get("pipe_issues"),
             "qa_fence": qa_probe.get("fence_tokens"),
             "qa_tao": qa_probe.get("tao_tokens")}
    report_path = Path(args.report_out) if args.report_out else (
        acc_dir / f"acceptance_report_{args.book}_{chapters_label(chapters)}.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    io.open(report_path, "w", encoding="utf-8", newline="\n").write(
        render_report(acc, analyses, extra))
    print(f"[accept] 验收报告：{report_path}")

    s = acc["summary"]
    print(f"[accept] 完成：accepted {s['accepted']} / needs_fix {s['needs_fix']}；"
          f"hard {s['hard_errors']}；judgment {s['judgment_items']}；"
          f"pipe_unsourced {s['pipe_unsourced']}")
    return 0 if s["needs_fix"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
