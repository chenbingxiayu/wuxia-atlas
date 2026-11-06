# -*- coding: utf-8 -*-
"""一次性：《七剑下天山》judgment 213 条裁决执行器（docs/45 口径，2026-11-05）。

裁决依据 = skills/SKILL_03a_实体标注.md v1.8：
  - L127 纯计划/意图/条件/否定不标（正待/正想/若不/还未/就要/命令句…）；
  - L108 时间宽口径（可锚定情节时间流才标；纯模糊"一会"不标；非时间语义（距离/身高/招数）摘除；
  - $ 裸数词/裸量词不标（单字"张/杯/枝/三/双/两"裸标摘除；"一颗/一枝/一根"带数者保留）；
  - 动词域高风险 16 条逐一核验：域码全部正确（押/驱逐=■移动、刺/劈/戳=⊠杀伤）→ 保留；
  - 围栏实指 10 条逐一核验：018[1] 诗围栏内实体均实指、023[80] 对联江南/塞外实指 → 保留
    （018[1] 围栏本身系章首探测对散文段的误判，属 struct 层观察项，记录不改动）；
  - verb_wordlist_candidate 50 条：wordlist 候选域差异属词表池输入（verbs 全部"待审"状态），
    标注保留，抽验 5 条无域错误。

删标 = 摘除令牌括号与类型码，显示串原样保留（剥标后与底本逐字一致，integrity 把关）。
锚点 anchor：候选消歧（令牌前/后 ±20 字窗口内须含 anchor）；occ：同显示串第 N 处。
--dry 打印全部 diff；--apply 写盘（写前逐段剥标断言）。
"""
import argparse
import difflib
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
import config      # noqa: E402
import symbols     # noqa: E402

# (ch, pn, display, anchor, occ)  —— anchor/occ 可为 None
REMOVALS = [
    # ---- plan_negation_verb（真违规：纯计划/意图/条件/否定/命令） ----
    (1, 37, "绕道而行", "正待", None), (1, 38, "撤剑", "竟不", None),
    (1, 45, "收招", "若不", None), (1, 62, "刺中", "就要", None),
    (1, 69, "突围", "还未", None),
    (2, 2, "追去", "正待", None), (2, 7, "还击", "正待", None),
    (3, 14, "死", "不", 1), (3, 19, "下山", "赶快随我", None),
    (3, 43, "回到", "还是要", None), (3, 50, "到", "养老", None),
    (4, 38, "跳出", "就待", None), (4, 73, "收入", "正想", None),
    (5, 22, "补", "还想", None), (5, 45, "学", "根本", None),
    (5, 51, "抽笔进招", "正待", None),
    (6, 29, "追赶", "却不", None), (6, 34, "斩下", "正待", None),
    (6, 70, "削断", "还要", None),
    (7, 10, "到", "未", None), (7, 62, "冲出", "要想", None),
    (8, 71, "回去", "还要", None),
    # 8[72] 两处 ⊠杀 保留：持刀攻击已发生（非纯意图）+ 记忆中的过去事件
    (8, 74, "推翻", "叮嘱", None),
    (10, 22, "投奔", "义军", None), (10, 28, "动手", "正想", None),
    (10, 73, "到过", "从未", None),
    (11, 46, "进去", "何不", None), (11, 50, "飞越", "便待", None),
    (11, 83, "闯进", "就想", None), (11, 124, "回转", "故乡", None),
    (12, 11, "闪过", "方待", None), (12, 41, "洗脱", "还想", None),
    (12, 44, "逃出来", "为什么不", None),
    (13, 25, "劫", "我们不", None), (13, 46, "擒", "定要", None),
    (14, 2, "躲避", "若不", None), (14, 6, "追赶", "也不", None),
    (15, 9, "生擒", "只想", None), (15, 19, "救", "若", None),
    (15, 21, "挺剑前扑", "正想", None), (15, 35, "混战", "就要", None),
    (15, 59, "开赴", "就将", None),
    (16, 24, "进宫", "说不定", None), (16, 38, "割断", "却未", None),
    (16, 39, "反抗", "一点也不", None), (16, 48, "进宫", "仍未", None),
    (17, 7, "刺下", "并不", None), (17, 26, "丧命", "就要", None),
    (17, 34, "杀", "我吧", None), (17, 40, "砸中", "眼看要", None),
    # 8[72] 两处 ⊠杀 保留：持刀攻击已发生（非纯意图）+ 记忆中的过去事件
    (18, 103, "拔", None, 1),
    (19, 1, "押", None, 1), (19, 1, "押", None, 2), (19, 3, "逃走", "正要", None),
    (19, 26, "制服", "心想", None), (19, 29, "解", "刑部大堂", None),
    (19, 87, "堵截", "还待", 1),   # 仅删第一处（还待=未开始）；第二处"堵截得住"动作已发生，保留
    (19, 90, "救出", "你若", None),
    (20, 28, "爬至", "即将", None), (20, 31, "捉", "我要", None),
    (20, 43, "打中", "并未", None), (20, 43, "练到", "还未", None),
    (21, 39, "回山", "还未", None),
    (22, 24, "擒", "要", None),
    (23, 32, "反扑", "数度想", None), (23, 38, "救出", "宁死", None),
    (23, 54, "回", "我要", None),   # 纯意图（"我要回天山练剑"）；练 未被标记，不动
    (23, 60, "打中", "并未", None), (23, 70, "跟去", "也想", None),
    (24, 9, "进入", "只怕未", None), (24, 16, "追击", "正待", None),
    (25, 5, "到", "便将", None), (25, 23, "回到", "还要", None),
    (25, 65, "跳下", "本想", None),
    (26, 2, "进至", "尚未", None), (26, 3, "接剑", "并不", None),
    (26, 21, "回到", "将要", None), (26, 21, "伤", "险些", None),
    (27, 19, "下杀手", "正要", None), (27, 51, "战", "何时", None),
    (30, 24, "回", "本是要", None), (30, 25, "刺到", "尚未", None),
    (30, 30, "滚下山", "还不", None),
    # ---- time_boundary（纯模糊/非时间语义，删标） ----
    (10, 102, "一会", "过了", None), (14, 31, "一会", "过了", None),
    (18, 12, "千里迢迢", None, None),
    # ---- quantity_boundary（裸数词/裸量词，删标） ----
    (2, 6, "张", "黄绫帐", None), (2, 89, "杯", "冷水", None),
    (2, 90, "张", None, 3),        # 候选 [@张华昭, $张, @张华昭]，取第 3 处前的 $张
    (4, 43, "颗", "倒翻", None),   # 那颗（裸量词）；同段 〖$一颗〗 合规保留
    (6, 8, "枝", "讨过", None), (6, 38, "枝", "猜一猜", None),
    (10, 38, "三", "不肯", None), (10, 49, "双", "手提", None),
    (13, 22, "三", "魔之首", None), (15, 66, "杯", "捧着一", 1),
    (19, 58, "把", None, None), (20, 23, "三", "晦明", None),
    (21, 59, "根", "不想下山", None),
    (27, 21, "两", "父女", None),
]

# 改域（%→$：距离/招数/身高为数量非时间；先例 〖$七丈〗〖$五六十回合〗〖$三十个〗）
# (ch, pn, display, anchor, new_code)
RETYPES = [
    (20, 36, "五六十招", "拆到", "$"),
    (27, 22, "十余二十里路", "驰到", "$"),
    (30, 9, "六尺", "身高", "$"),
    (30, 9, "三尺", "不到", "$"),
]

# 仅核验（期望带数词，保留）：(ch, pn, display)
VERIFY_ONLY = [(4, 43, "颗"), (6, 38, "枝"), (21, 59, "根")]

TOKEN_RE = re.compile(r"([〖⟦〘])(.)([^〖〗⟦⟧〘〙]*?)([〗⟧〙])")
PARA_RE = re.compile(r"^\[(\d+)\] (.*)$", re.M)


def load_paras(ch: int):
    p = config.tagged_path("七剑下天山", ch)
    t = io.open(p, encoding="utf-8").read()
    return p, {int(m.group(1)): m.group(2) for m in PARA_RE.finditer(t)}


def find_token(text: str, display: str, anchor: str, occ):
    """返回 ((start, end, token_str, body), None) 或 (None, candidates)。"""
    cands = [(m.start(), m.end(), m.group(0), m.group(3))
             for m in TOKEN_RE.finditer(text)
             if display in m.group(3).split("|")[0]]
    if anchor:
        cands = [c for c in cands
                 if anchor in text[max(0, c[0] - 20):min(len(text), c[1] + 20)]]
    if occ is not None:
        cands = cands[occ - 1:occ]
    if len(cands) == 1:
        return cands[0], None
    return None, cands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    edits = {}   # path -> {pn: (old_para, new_para)}
    unresolved = []
    n_ok = 0
    for ch, pn, display, anchor, occ in REMOVALS:
        p, paras = load_paras(ch)
        text = paras[pn]
        found, cands = find_token(text, display, anchor, occ)
        if found is None:
            unresolved.append((ch, pn, display, anchor, occ,
                               [c[2] for c in cands][:4]))
            continue
        s, e, tok, body = found
        new = text[:s] + body.split("|")[0] + text[e:]
        assert symbols.strip_markup(new) == symbols.strip_markup(text), \
            f"剥标不一致 {ch}[{pn}] {tok}"
        edits.setdefault(p, {}).setdefault(pn, (text, new))
        n_ok += 1
        diff = " → ".join(filter(None, difflib.ndiff(
            [text[max(0, s - 12):e + 12]], [new[max(0, s - 12):e + 12]]))).replace("\n", "")
        print(f"[{ch:03d}][{pn}] {tok} ⇒ {body.split('|')[0]}   …{diff[:90]}…")

    print("\n== 改域（%→$）==")
    for ch, pn, display, anchor, new_code in RETYPES:
        p, paras = load_paras(ch)
        text = paras[pn]
        found, cands = find_token(text, display, anchor, None)
        if found is None:
            unresolved.append((ch, pn, display, anchor, "retype",
                               [c[2] for c in cands][:4]))
            continue
        s, e, tok, body = found
        disp = body.split("|")[0]
        new = text[:s] + "〖" + new_code + disp + "〗" + text[e:]
        assert symbols.strip_markup(new) == symbols.strip_markup(text), \
            f"剥标不一致 {ch}[{pn}] {tok}"
        edits.setdefault(p, {}).setdefault(pn, (text, new))
        n_ok += 1
        print(f"[{ch:03d}][{pn}] {tok} ⇒ 〖{new_code}{disp}〗")

    print("\n== 仅核验（应带数词，不改动）==")
    for ch, pn, display in VERIFY_ONLY:
        _, paras = load_paras(ch)
        toks = [m.group(0) for m in TOKEN_RE.finditer(paras[pn])
                if display in m.group(3).split("|")[0]]
        print(f"[{ch:03d}][{pn}] {display}: {toks}")

    print(f"\n定位成功 {n_ok}/{len(REMOVALS)}；未定位 {len(unresolved)}")
    for u in unresolved:
        print("  UNRESOLVED:", u)
    if not args.apply:
        print("\n(dry-run，未写盘；确认后加 --apply)")
        return
    if unresolved:
        print("\n[abort] 存在未定位条目，先消歧再 --apply")
        return
    for p, per in edits.items():
        t = io.open(p, encoding="utf-8").read()
        for pn, (old, new) in per.items():
            old_line = f"[{pn}] {old}"
            assert t.count(old_line) == 1, f"行定位失败 {p.name} [{pn}]"
            t = t.replace(old_line, f"[{pn}] {new}")
        io.open(p, "w", encoding="utf-8", newline="").write(t)
        print(f"written: {p.name} ({len(per)} 段)")


if __name__ == "__main__":
    main()
