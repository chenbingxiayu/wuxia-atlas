# -*- coding: utf-8 -*-
"""C25 · 金标准标定式通名/别名召回补标（武侠版，默认 dry-run，--apply 落盘）。

背景（docs/39 S1 / docs/47）：020-032 机器初稿对通名类（# 身份、; 职衔）、
已知别名裸文、门派通名存在系统性召回缺口；直接套用 C16/C17 候选 TSV 有两类风险
（kinship watch 行违反 DEF-04「纯关系词不标」；无金标准证据的新词精度未知）。
本工具按 docs/39 S1 纪律实现「先在金标准上标定，再放行」：

  - W1 身份/职衔：词表 = 金标准 001-019 中 〖#w〗/〖;w〗 token 数 ≥5 且
    裸文标注率 ≥85% 的词（即金标准自身几乎不留裸文的词），D1 描述性代称负表排除；
    插入 〖#w〗/〖;w〗。
  - W2 别名/称谓：surface 来自 registry 别名 ∪ 金标准管道 ∪ 目标章回管道；
    准入 = (金标准管道≥5 且 金标准裸文=0) 或 (registry 别名 且 金标准裸文=0 且
    管道总数≥3)；泛称/关系称谓负表与歧义（多 canonical）拦截；「名+衔」省称
    （黄叶/红云/白石/青蓑 等）加自然物象上下文守卫；插入 〖@w|规范名〗。
  - W3 门派等新类型：取 C16 建议词中有金标准证据者（token≥5 且裸文=0），
    符号按金标准该词主符号；无证据者仅报告不插入。

保护：复用 C18 build_masked（既有令牌/围栏/标题/回目掩码）；单遍最长匹配；
插入按位置倒序；落盘前后逐回断言 strip_markup 一致；--apply 前自动备份。

用法：
  python scripts/apply_gold_calibrated_recall.py --book 白发魔女传 \
      --chapters 020-032 --gold 001-019 --dry-run
  python scripts/apply_gold_calibrated_recall.py --book 白发魔女传 \
      --chapters 020-032 --gold 001-019 --apply
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config           # noqa: E402
import symbols          # noqa: E402
from scan_untagged_aliases import build_masked  # noqa: E402

TAO_RE = re.compile(r"欲知|下回分解|且听下回")   # 回末套语（accept_batch 同口径）

BOOK = "白发魔女传"

# ---- 负规则表 ---------------------------------------------------------------
# D1 描述性代称（docs/39 §1.2：规范应不标；金标准 19.4% 为旧口径残留）
D1_DENY = {
    "少年", "少女", "老人", "老者", "汉子", "大汉", "壮汉", "小子", "孩子",
    "小孩", "娃娃", "婴儿", "幼童", "孩童", "妇人", "妇女", "女子", "男子",
    "老儿", "女郎", "姑娘", "美人", "老头", "老妇", "书生", "美女", "丑汉",
    # 2026-11-05 追加（DEF-04 纯亲属不标；C25 一轮曾误收 舅舅，已回滚 5 处）
    "舅舅", "姑姑", "前夫", "姨母", "舅父",
}
# 泛称/纯关系称谓（不可作别名 surface；「姓+衔」复合形式不受此限）
GENERIC_DENY = {
    "皇帝", "皇上", "天子", "太子", "大人", "老爷", "贵妃", "娘娘", "姑姑",
    "哥哥", "大哥", "姐姐", "妹妹", "弟弟", "兄弟", "叔叔", "伯伯", "婶婶",
    "嫂嫂", "堡主", "宗主", "寨主", "宫主", "掌柜", "员外", "管家", "廷弼",
    "公主", "太子妃", "太后", "皇后", "妃子", "公公", "老前辈", "老英雄",
    "客魏", "阉党", "朝臣", "万岁", "今上", "兄台", "陛下",
}
# 自然物象守卫：这些 surface 在指人歧义（字面物象）语境需跳过
NATURE_AMBIG = {"黄叶", "红云", "白石", "青蓑", "晦明", "明忠", "一航", "裳儿"}
PREV_NATURE = set("片朵团抹缕似如点阵")
NEXT_NATURE = set("飘落飞满卷似如漫滚翻涌散缭绕残暮斜压罩")
# 子串歧义负表：作为更长词的子串风险高，机械补标不安全
SUBSTR_RISKY = {"练女", "霓裳", "九娘", "阿瑚", "铁老", "罗布族"}

# 符号裁定覆盖（新裁定优先于金标准旧口径）：docs/46 §8.2——寨主/宫主归 ; 职衔
SYMBOL_OVERRIDE = {"寨主": ";", "宫主": ";"}

# 词性歧义负表（W1）：名词/动词两读且机械不可判（如「指挥女兵掘地」的指挥=动词）
W1_POS_RISKY = {"指挥"}

# W3 同形异义否决：gold 〖^剑诀〗=法门/公式义（5 token），机器裸文「捏剑诀/剑诀一领」
# 全为剑指手诀义——非同一词义，不补标（2026-11-05 考订）
W3_SENSE_DENY = {"剑诀"}

MIN_GOLD_TOKENS = 5          # W1/W3 词准入：金标准 token 数
MIN_GOLD_RATE = 0.85         # W1 词准入：金标准标注率（1-裸文率）
W2_MIN_GOLD_PIPE = 5         # W2 纯金标准佐证准入
W2_MIN_TOTAL_PIPE = 3        # W2 registry 佐证准入的管道总数下限

# ---- W4 · $ 数量层（docs/39 S1 $ 扩表的新口径子集）--------------------------
# 口径依据：docs/45 已裁「裸数词/裸量词不标」；docs/39 负例「事件量（一掌/一声喊）、
# 纯泛指（一个）、习语量（千里迢迢）」。W4 只补「信息承载计数」（两个/三招/一封/两名
# 类），量词分两档：
#   独立计数量词（数+量 自成计数，无需名词跟随）：人-计数/招/剑/杯/名/位/朵/件/只/…
#   依赖量词（需名词跟随才成立）：条/道/股/缕/丝/行 —— 插入时要求后一可见字符为 CJK
# 负例：时间量词（日/月/年/天/时 → % 层辖域）、事件量（声/掌/拳/眼/步/句/次/遍/番/
# 阵/场/回/合/看）、程度量（点/片）、一头（「一头撞去」副词性）、一路（副词性）、
# 头/路/带（副词性/区域义）、一个（纯泛指）。
QTY_NUM = r"(二三十|三十余|二十余|十余|数十|十多|百多|三十|四十|五十|六十|七十|八十|九十|六七|七八|三五|一|两|三|四|五|六|七|八|九|十|几|数|半|廿|卅|百|千|万)"
QTY_M_INDEP = ("人|名|位|招|剑|杯|朵|件|只|页|双|副|套|门|部|对|列|包|堆|处|间|"
               "座|根|截|升|锭|批|笔|节|章|则|项|担|碗|坛|缸|瓮|箱|笼|匹|"
               "艘|轿|车|骑|斗|石")
QTY_M_DEP = "条|道|股|缕|行|封"
QTY_SKIP_SURFACE = {"一个", "一笔", "千条", "万条", "四处", "一道"}
# surface 级后接负例（保留机制供后续词微调；当前无启用项）
QTY_SURFACE_NEXT_DENY: dict[str, set[str]] = {}
QTY_PREV_DENY = set("哪这每另第") | set("一二两三四五六七八九十百千万几数半廿卅零")
QTY_NEXT_DEP_DENY = set("，。！？；：、）」』\"'…— \ufffd\r\n")
QTY_DEP_SET = set(QTY_M_DEP.split("|"))
QTY_SKIP_NAME = {"一个": "一个(纯泛指)", "一笔": "一笔(勾销习语)"}


def parse_chapters(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part.strip():
            out.append(int(part))
    return out


def tag_paths(book: str, n: int) -> Path:
    return config.DIR_TAGGED / book / f"{n:03d}.tagged.md"


def load_pairs(paths: list[Path]) -> tuple[dict[str, set[str]], Counter]:
    """(alias|canonical) 管道对 + canonical 直标 token 计数。"""
    pairs: dict[str, set[str]] = defaultdict(set)
    canon_hits: Counter = Counter()
    for p in paths:
        t = io.open(p, encoding="utf-8").read()
        for m in re.finditer(r"〖@([^〖〗]+)〗", t):
            body = m.group(1)
            for sep in ("｜", "|"):
                if sep in body:
                    a, c = body.split(sep, 1)
                    pairs[a.strip()].add(c.strip())
                    break
            else:
                canon_hits[body.strip()] += 1
    return pairs, canon_hits


def load_registry_pairs() -> tuple[dict[str, set[str]], set[str]]:
    a2c, surfaces, _ctx = load_registry_pairs_ctx()
    return a2c, surfaces


def load_registry_pairs_ctx() -> tuple[dict[str, set[str]], set[str], dict[str, set[str]]]:
    reg = json.load(io.open(config.DIR_REGISTRY / "entities.json", encoding="utf-8"))
    a2c: dict[str, set[str]] = defaultdict(set)
    ctx: dict[str, set[str]] = defaultdict(set)
    surfaces: set[str] = set()
    for e in reg["entities"]:
        if e["type"] != "@":
            continue
        a2c[e["canonical"]].add(e["canonical"])
        surfaces.add(e["canonical"])
        for a in e.get("aliases", []):
            a = re.sub(r"（[^）]*）", "", a).strip()
            if a:
                a2c[a].add(e["canonical"])
                surfaces.add(a)
        for c in e.get("contextual", []):
            c = re.sub(r"（[^）]*）", "", c).strip()
            if c:
                ctx[e["canonical"]].add(c)
    return a2c, surfaces, ctx


def gold_stats(gold_paths: list[Path]) -> tuple[Counter, Counter, dict[str, Counter]]:
    """金标准统计：#/; token 计数、各类型 token 计数、全部 token 符号分布。"""
    idn: Counter = Counter()          # word -> count for #/;
    allsym: dict[str, Counter] = defaultdict(Counter)
    for p in gold_paths:
        t = io.open(p, encoding="utf-8").read()
        for m in symbols.TOKEN_RE.finditer(t):
            info = symbols.parse_token(m.group(0))
            if not info or info[5] or info[1] is None:
                continue
            layer, code, disp = info[0], info[1], info[3]
            if layer == "entity":
                allsym[disp][code] += 1
                if code in ("#", ";"):
                    idn[disp] += 1
    return idn, allsym, allsym


def gold_bare(paths: list[Path], words: set[str]) -> Counter:
    bare: Counter = Counter()
    pat = re.compile("|".join(re.escape(w) for w in words))
    for p in paths:
        t = io.open(p, encoding="utf-8").read()
        masked = build_masked(t)
        stripped = symbols.strip_markup(masked)
        for m in pat.finditer(stripped):
            bare[m.group(0)] += 1
    return bare


def build_w1_vocab(gold_paths: list[Path], report: list[str]) -> dict[str, str]:
    idn, _, _ = gold_stats(gold_paths)
    words = {w for w, c in idn.items() if c >= MIN_GOLD_TOKENS and len(w) >= 2}
    bare = gold_bare(gold_paths, words)
    vocab: dict[str, str] = {}
    sym: dict[str, Counter] = defaultdict(Counter)
    for p in gold_paths:
        t = io.open(p, encoding="utf-8").read()
        for m in symbols.TOKEN_RE.finditer(t):
            info = symbols.parse_token(m.group(0))
            if info and not info[5] and info[1] in ("#", ";"):
                sym[info[3]][info[1]] += 1
    for w in sorted(words):
        if w in D1_DENY:
            report.append(f"[W1-DENY-D1] {w}（D1 描述性代称，不标）")
            continue
        if w in SUBSTR_RISKY:
            report.append(f"[W1-DROP] {w}（子串歧义风险负表）")
            continue
        if w in W1_POS_RISKY:
            report.append(f"[W1-DROP] {w}（词性歧义负表：名词/动词两读）")
            continue
        total = idn[w] + bare[w]
        rate = idn[w] / total if total else 0
        if rate < MIN_GOLD_RATE:
            report.append(f"[W1-DROP] {w} 金标准标注率 {rate:.0%}（{idn[w]}/{total}）< {MIN_GOLD_RATE:.0%}")
            continue
        vocab[w] = SYMBOL_OVERRIDE.get(w, sym[w].most_common(1)[0][0])
    return vocab


def build_w2_vocab(gold_paths: list[Path], target_paths: list[Path],
                   report: list[str]) -> dict[str, tuple[str, str]]:
    """返回 surface -> ("alias", canonical)。三类证据（出现次数口径）：
    A 金标准惯例：gold_tagged（管道+直标）≥5 且 裸文率 ≤2%；
    B registry+管道：registry 别名/正名 且 gold 裸文 ≤1 且 (gold_tagged+目标回管道) ≥3；
    C 正名直标：surface==canonical 且 gold/machine 直标 token ≥5 且 裸文率 ≤2%。"""
    gpairs, gcanon = load_pairs(gold_paths)
    tpairs, tcanon = load_pairs(target_paths)
    reg_a2c, _, reg_ctx = load_registry_pairs_ctx()

    merged: dict[str, set[str]] = defaultdict(set)
    for src in (gpairs, tpairs, reg_a2c):
        for a, cs in src.items():
            merged[a] |= cs

    # 批量预取：金标准裸文计数 + @ token display 计数（一次遍历，避免逐词重读）
    all_surfaces = {w for w in merged if len(w) >= 2}
    bare_all = gold_bare(gold_paths, all_surfaces) if all_surfaces else Counter()
    g_total, g_pipe, m_pipe = batch_display_counts(gold_paths, target_paths)

    vocab: dict[str, tuple[str, str]] = {}
    for w, cs in sorted(merged.items()):
        if len(w) < 2:
            continue
        if len(cs) > 1:
            report.append(f"[W2-AMBIG] {w} → {sorted(cs)}（多 canonical，跳过）")
            continue
        c = next(iter(cs))
        if w in GENERIC_DENY or w in D1_DENY:
            report.append(f"[W2-DENY] {w}（泛称/关系负表）")
            continue
        if w in SUBSTR_RISKY:
            report.append(f"[W2-DROP] {w}（子串歧义风险负表）")
            continue
        gold_tok_occ, gold_pipe_occ, mach_pipe_occ = (
            g_total.get(w, 0), g_pipe.get(w, 0), m_pipe.get(w, 0))
        reg_ok = w in reg_a2c and c in reg_a2c[w]
        gb = bare_all[w]
        gtotal = gold_tok_occ + gb
        grate = gb / gtotal if gtotal else 0.0
        if w == c:
            # 正名直标：machine 已大量 〖@w〗，补裸文为同形态直标
            if (gold_tok_occ + tcanon.get(w, 0)) >= W2_MIN_GOLD_PIPE and grate <= 0.02:
                vocab[w] = ("alias-self", c)
                report.append(f"[W2-OK-SELF] {w}（直标 token {gold_tok_occ}+"
                              f"{tcanon.get(w, 0)}，裸文 {gb}）")
            else:
                report.append(f"[W2-DEFER] {w} 证据不足（直标 {gold_tok_occ}+"
                              f"{tcanon.get(w, 0)}，裸文 {gb}）")
            continue
        if grate > 0.02 and gb > 1:
            report.append(f"[W2-DROP] {w}→{c} 金标准裸文 {gb}/{gtotal}")
            continue
        cond_a = gold_tok_occ >= W2_MIN_GOLD_PIPE and grate <= 0.02
        cond_b = reg_ok and gb <= 1 and (gold_tok_occ + mach_pipe_occ) >= W2_MIN_TOTAL_PIPE
        # cond_c（2026-11-05 二轮）：registry contextual 在册的「姓+称谓」+ 机器自身管道
        # 先例 ≥2 + gold 裸文 0 —— 修复机器批内部不一致（卓公子×7 管道 vs 裸文并存）
        cond_c = c in reg_ctx and w in reg_ctx[c] and mach_pipe_occ >= 2 and gb == 0
        if cond_a or cond_b or cond_c:
            vocab[w] = ("alias", c)
            tag = "cond_c" if cond_c and not (cond_a or cond_b) else ""
            report.append(f"[W2-OK{tag}] {w}→{c}（gold token {gold_tok_occ}/machine 管道 "
                          f"{mach_pipe_occ}/裸文 {gb}/registry={'Y' if reg_ok else 'N'}）")
        else:
            report.append(
                f"[W2-DEFER] {w}→{c}（gold token {gold_tok_occ}/machine 管道 "
                          f"{mach_pipe_occ}/裸文 {gb}/registry={'Y' if reg_ok else 'N'}）")
    return vocab


def build_w4_vocab(target_paths: list[Path], report: list[str]) -> dict[str, tuple[str, str]]:
    """$ 数量层：bare 文本中的「数词+量词」信息承载计数（docs/39 S1 $ 扩表新口径子集）。"""
    qty_pat = re.compile(QTY_NUM + "(" + QTY_M_INDEP + "|" + QTY_M_DEP + ")")
    vocab: dict[str, tuple[str, str]] = {}
    stats: Counter = Counter()
    for p in target_paths:
        t = io.open(p, encoding="utf-8").read()
        s = symbols.strip_markup(build_masked(t))          # 掩既有令牌/围栏/标题后计数
        s = TAO_RE.sub("\ufffd" * 6, s)                     # 回末套语段粗掩（不计入候选）
        for m in qty_pat.finditer(s):
            w = m.group(0)
            if w in QTY_SKIP_SURFACE:
                stats[QTY_SKIP_NAME.get(w, w)] += 1
                continue
            prev = s[m.start() - 1] if m.start() > 0 else ""
            if prev in QTY_PREV_DENY:
                stats["prev-deny"] += 1
                continue
            vocab.setdefault(w, ("sym", "$"))
            stats["ok"] += 1
    report.append("[W4-SURFACES] " + "、".join(sorted(vocab)))
    n_dep = sum(1 for w in vocab if w[-1] in QTY_DEP_SET)
    report.append(f"[W4-STATS] 独立 {len(vocab) - n_dep} surface / 依赖 {n_dep} surface")
    return vocab


def token_occurrences(gold_paths: list[Path], target_paths: list[Path],
                      w: str) -> tuple[int, int, int]:
    """(gold @token 出现次数, gold 其中管道次数, 目标回 @管道出现次数)——display==w。"""
    gold_tok = gold_pipe = mach_pipe = 0
    pat = re.compile(r"〖@" + re.escape(w) + r"(?:[｜|]([^〖〗]*))?〗")
    for p in gold_paths:
        for m in pat.finditer(io.open(p, encoding="utf-8").read()):
            gold_tok += 1
            if m.group(1):
                gold_pipe += 1
    for p in target_paths:
        for m in pat.finditer(io.open(p, encoding="utf-8").read()):
            if m.group(1):
                mach_pipe += 1
    return gold_tok, gold_pipe, mach_pipe


def batch_display_counts(gold_paths: list[Path],
                         target_paths: list[Path]) -> tuple[Counter, Counter, Counter]:
    """一次遍历统计：gold @token display 总数 / 其中管道数 / 目标回管道数。"""
    pat = re.compile(r"〖@([^〖〗]+)〗")
    g_total: Counter = Counter()
    g_pipe: Counter = Counter()
    m_pipe: Counter = Counter()
    for p, is_gold in [(p, True) for p in gold_paths] + [(p, False) for p in target_paths]:
        for m in pat.finditer(io.open(p, encoding="utf-8").read()):
            body = m.group(1)
            for sep in ("｜", "|"):
                if sep in body:
                    disp, note = body.split(sep, 1)
                    if is_gold:
                        g_total[disp.strip()] += 1
                        g_pipe[disp.strip()] += 1
                    else:
                        m_pipe[disp.strip()] += 1
                    break
            else:
                if is_gold:
                    g_total[body.strip()] += 1
    return g_total, g_pipe, m_pipe


def build_w3_vocab(gold_paths: list[Path], target_chapters: list[int],
                   report: list[str], book: str = BOOK) -> dict[str, str]:
    # C16 建议词（目标章回的 new_entities TSV）
    words: set[str] = set()
    for n in target_chapters:
        p = config.patches_dir(book) / f"{n:03d}_new_entities.tsv"
        if not p.exists():
            continue
        for line in io.open(p, encoding="utf-8").read().splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) >= 3 and cols[2]:
                words.add(cols[2])
    for w in sorted(W3_SENSE_DENY):
        report.append(f"[W3-DENY] {w}（同形异义否决：gold 法门义 vs 机器 手诀义）")
    words = {w for w in words if len(w) >= 2} - W3_SENSE_DENY
    if not words:
        return {}
    _, allsym, _ = gold_stats(gold_paths)
    bare = gold_bare(gold_paths, words)
    vocab: dict[str, str] = {}
    for w in sorted(words):
        tok = allsym.get(w, Counter())
        n = sum(tok.values())
        if n >= MIN_GOLD_TOKENS and bare[w] == 0:
            vocab[w] = tok.most_common(1)[0][0]
        else:
            report.append(
                f"[W3-DEFER] {w} 金标准 token={n} 裸文={bare[w]}（证据不足，仅报告）")
    return vocab


def scan_file(text: str, vocab: dict[str, tuple[str, str]]) -> tuple[list[tuple[int, int, str]], list[str]]:
    """单遍最长匹配；返回 (插入区间+token, 跳过日志)。"""
    masked = build_masked(text)
    # 回末套语段负区域（accept_batch TAO_RE 同口径：欲知/下回分解/且听下回）
    mlist = list(masked)
    off = 0
    for para in text.split("\n\n"):
        if TAO_RE.search(para):
            for k in range(off, min(off + len(para), len(mlist))):
                mlist[k] = "\ufffd"
        off += len(para) + 2
    masked = "".join(mlist)
    surfaces = sorted(vocab, key=len, reverse=True)
    inserts: list[tuple[int, int, str]] = []
    skips: list[str] = []
    i, L = 0, len(text)
    while i < L:
        if masked[i] == "\ufffd":
            i += 1
            continue
        hit = None
        for w in surfaces:
            e = i + len(w)
            if masked[i:e] == w:
                hit = (w, e)
                break
        if not hit:
            i += 1
            continue
        w, e = hit
        prev = masked[i - 1] if i > 0 else ""
        nxt = masked[e] if e < L else ""
        if w in NATURE_AMBIG and (prev in PREV_NATURE or nxt in NEXT_NATURE):
            skips.append(f"{w}@{i} prev={prev!r} next={nxt!r}（物象守卫）")
            i = e
            continue
        kind, val = vocab[w]
        if kind == "sym" and val == "$":
            # $ 守卫：前置否定（哪一位/这位…）+ 依赖量词需名词跟随 + surface 级后接负例
            if prev in QTY_PREV_DENY:
                skips.append(f"{w}@{i} prev={prev!r}（数量前置否定）")
                i = e
                continue
            if w in QTY_SURFACE_NEXT_DENY and nxt in QTY_SURFACE_NEXT_DENY[w]:
                skips.append(f"{w}@{i} next={nxt!r}（surface 后接负例）")
                i = e
                continue
            if w[-1] in QTY_DEP_SET and (not nxt or nxt in QTY_NEXT_DEP_DENY
                                         or not ("\u4e00" <= nxt <= "\u9fff")):
                skips.append(f"{w}@{i} next={nxt!r}（依赖量词无名词跟随）")
                i = e
                continue
        if kind == "sym":
            tok = f"〖{val}{w}〗"
        elif kind == "alias-self":
            tok = f"〖@{w}〗"
        else:
            tok = f"〖@{w}|{val}〗"
        inserts.append((i, e, tok))
        i = e
    return inserts, skips


def apply_to_chapter(n: int, vocab_all: dict[str, tuple[str, str]],
                     dry: bool, backup_dir: Path | None,
                     book: str = BOOK) -> dict:
    p = tag_paths(book, n)
    t = io.open(p, encoding="utf-8").read()
    inserts, skips = scan_file(t, vocab_all)
    new = t
    for a, b, tok in sorted(inserts, key=lambda x: -x[0]):
        new = new[:a] + tok + new[b:]
    if not dry and inserts:
        assert symbols.strip_markup(new) == symbols.strip_markup(t), f"{n:03d} strip 不一致"
        if backup_dir:
            dst = backup_dir / p.name
            if not dst.exists():
                shutil.copy2(p, dst)
        io.open(p, "w", encoding="utf-8", newline="\n").write(new)
    return {"n": n, "inserts": inserts, "skips": skips, "changed": new != t}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default=BOOK)
    ap.add_argument("--chapters", required=True)
    ap.add_argument("--gold", required=True, help="如 001-019")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.apply == args.dry_run:
        ap.error("必须且只能选 --apply 或 --dry-run 之一")

    gold = parse_chapters(args.gold)
    targets = parse_chapters(args.chapters)
    gold_paths = [tag_paths(args.book, n) for n in gold]
    target_paths = [tag_paths(args.book, n) for n in targets]

    report: list[str] = []
    w1 = build_w1_vocab(gold_paths, report)
    w2 = build_w2_vocab(gold_paths, target_paths, report)
    w3 = build_w3_vocab(gold_paths, targets, report, book=args.book)
    w4 = build_w4_vocab(target_paths, report)
    # 统一值形态：W1/W3 → ("sym", code)
    w1 = {w: ("sym", c) for w, c in w1.items()}
    w3 = {w: ("sym", c) for w, c in w3.items()}
    # 合并四波次：先到先得，实际优先级 ◆/^ > #/; > @ > $（w3→w1→w2→w4）。
    # 2026-11-05 用户拍板：保持现有实现顺序不动、只修注释（原注释"@ > #/;/◆ > $"与
    # 实现相反系笔误）；同 surface 双波命中时以先入波次落标并记 [MERGE-SKIP]。
    vocab_all: dict[str, tuple[str, str]] = {}
    for src in (w3, w1, w2, w4):
        for w, v in src.items():
            if w in vocab_all:
                report.append(f"[MERGE-SKIP] {w} 已在更高优先波次（{vocab_all[w][1]}）")
                continue
            vocab_all[w] = v
    report.append("[VOCAB-W1] " + "、".join(f"{w}({v[1]})" for w, v in sorted(w1.items())))
    report.append("[VOCAB-W2] " + "、".join(
        (f"{w}→{v[1]}" if v[0] == "alias" else f"{w}(self)") for w, v in sorted(w2.items())))
    report.append("[VOCAB-W3] " + "、".join(f"{w}({v[1]})" for w, v in sorted(w3.items())))
    print(f"W1 身份/职衔 {len(w1)} 词 | W2 别名 {len(w2)} 词 | W3 门派 {len(w3)} 词"
          f" | W4 数量 {len(w4)} surface"
          f" | 合计 {len(vocab_all)} surface")

    # --apply 时先建备份目录（2026-11-05 修复：原 backup_dir 恒 None，备份分支为死代码）
    backup_dir = None
    if args.apply:
        backup_dir = config.DIR_LOGS / "backup" / \
            f"recall_pass_{args.book}_{datetime.now():%Y%m%d_%H%M%S}"
        backup_dir.mkdir(parents=True, exist_ok=True)
    results = [apply_to_chapter(n, vocab_all, not args.apply, backup_dir,
                                book=args.book) for n in targets]
    total = sum(len(r["inserts"]) for r in results)
    byw = Counter(tok for r in results for _, _, tok in r["inserts"])
    print(f"{'DRY-RUN' if not args.apply else 'APPLIED'}: 插入 {total} 处；"
          f"按符号 {dict(byw)}")
    for r in results:
        if r["skips"]:
            for s in r["skips"]:
                print(f"  {r['n']:03d} skip: {s}")

    # ---- 报告落盘 ----
    out_md = config.DIR_LOGS / "qa" / f"recall_pass_{args.book}_{args.chapters}.md"
    lines = [
        f"# C25 金标准标定式召回补标 — {args.book} {args.chapters}",
        "",
        f"- 生成：{datetime.now().isoformat(timespec='seconds')}  "
        f"模式：{'APPLY' if args.apply else 'DRY-RUN'}",
        f"- 词表：W1={len(w1)} W2={len(w2)} W3={len(w3)}；插入 {total} 处",
        "",
        "## 一、插入明细（回 / token / 次数）",
        "",
    ]
    per_tok = Counter()
    for r in results:
        c = Counter(tok for _, _, tok in r["inserts"])
        if c:
            lines.append(f"### {r['n']:03d}（{sum(c.values())} 处）")
            lines.append("```text")
            for tok, k in sorted(c.items(), key=lambda x: -x[1]):
                lines.append(f"{tok} ×{k}")
            lines.append("```")
        per_tok.update(c)
    lines += ["", "## 二、词表准入报告（DROP/DEFER/DENY 全记录）", ""]
    lines += [f"- {x}" for x in report] or ["- （无）"]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告：{out_md}")

    # ---- 审计 TSV ----
    tsv_dir = config.patches_dir(args.book)
    tsv_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        if not r["inserts"]:
            continue
        p = tsv_dir / f"{r['n']:03d}_recall_pass.tsv"
        rows = ["章节\t词\t位置\t插入token"]
        for a, b, tok in r["inserts"]:
            rows.append(f"{r['n']:03d}\t{symbols.strip_markup(tok)}\t{a}\t{tok}")
        p.write_text("\n".join(rows), encoding="utf-8")
    print(f"审计 TSV：registry/patches/NNN_recall_pass.tsv（{sum(1 for r in results if r['inserts'])} 张）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
