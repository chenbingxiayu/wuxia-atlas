# -*- coding: utf-8 -*-
"""G4 动词消歧 wave-1 执行器（冰川天女传 刺/杀 68 处，2026-11-06）。

背景：刺/杀 在 verbs.json 为词表多域条目（刺 ⊞/⊠），任何无注记 token 触发
W-MULTIDOMAIN（validate_verb_tagging_wuxia.py:588 分支 i）。修复 = 按 SKILL_04f §3.3
补非空消歧说明。裁定（logs/qa/verb_disamb_冰川天女传_wave1.md 全 68 语境已读）：

  统一域对齐说明（域即消歧，说明显式化；幂等精确匹配，不触碰已带注记/复合词令牌）：
    ⟦⊞刺⟧ ×45 → ⟦⊞刺|刺击动作⟧
    ⟦⊟刺⟧ ×1  → ⟦⊟刺|刺破器物⟧        （035[61] 神芒刺破袈裟）
    ⟦⊞杀⟧ ×5  → ⟦⊞杀|冲杀(交战义)⟧    （杀得难解难分/望风披靡/连连后退/痛快 等 5 处全为交战义）
    ⟦⊠刺杀⟧ ×1 → ⟦⊠刺杀|刺杀致死⟧
  ⟦⊠杀⟧ ×16 逐段语境说明（意图/威胁/推测与实际致死分型）：
    002[49] 欲杀(意图) · 003[18] 杀死 · 003[21] 诛杀 · 003[34] 屠杀 · 003[58] 欲杀(意图)
    005[59] 誓杀(意图) · 009[42] 欲杀(未遂) · 011[49] 弑君 · 014[66] 疑杀(推测)
    015[44] 杀死 · 026[07] 误杀 · 029[26] 刺杀(弑主) · 033[76] 胁杀(威胁)
    038[28] 弑(被害) · 038[30] 誓杀(意图) · 038[32] 惨杀

  两处疑似 §3.1 结果主域候选（018[56] "刺个正着"/036[25] 长针刺了一下）不改域，
  留 P4/类型反思批次裁决（本批只消歧不重判域）。

安全纪律：备份（逐文件首写前）+ sk 剥标断言 + 逐条计数断言；幂等（带注记令牌不匹配）。
用法：python -I scripts/_oneshot/verb_disamb_wave1_apply.py --apply
"""
import argparse
import glob
import io
import os
import re
import shutil
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import apply_gold_c1_cleanup as _C1  # noqa: E402

BOOK = "冰川天女传"
UNIFORM = {
    "⟦⊞刺⟧": "⟦⊞刺|刺击动作⟧",
    "⟦⊟刺⟧": "⟦⊟刺|刺破器物⟧",
    "⟦⊞杀⟧": "⟦⊞杀|冲杀(交战义)⟧",
    "⟦⊠刺杀⟧": "⟦⊠刺杀|刺杀致死⟧",
}
SHA_BOX = {
    ("002", 49): "欲杀(意图)", ("003", 18): "杀死", ("003", 21): "诛杀",
    ("003", 34): "屠杀", ("003", 58): "欲杀(意图)", ("005", 59): "誓杀(意图)",
    ("009", 42): "欲杀(未遂)", ("011", 49): "弑君", ("014", 66): "疑杀(推测)",
    ("015", 44): "杀死", ("026", 7): "误杀", ("029", 26): "刺杀(弑主)",
    ("033", 76): "胁杀(威胁)", ("038", 28): "弑(被害)", ("038", 30): "誓杀(意图)",
    ("038", 32): "惨杀",
}


def segment_spans(t: str):
    """[(pn, start, end)] 段范围（含尾段）；pn 为 [n] 标号。"""
    marks = [(int(m.group(1)), m.end()) for m in re.finditer(r"\[(\d+)\]", t)]
    spans = []
    for i, (pn, start) in enumerate(marks):
        end = marks[i + 1][1] - len(re.search(r"\[(\d+)\]",
                                              t[marks[i + 1][1] - 12:marks[i + 1][1]]).group(0)) \
            if i + 1 < len(marks) else len(t)
        # 简化：直接用下一标记的 start-标记长度 不可靠，改用查找
        spans.append((pn, start, None))
    # 二次计算 end：下一个标记的 m.start()
    ms = list(re.finditer(r"\[(\d+)\]", t))
    spans = []
    for i, m in enumerate(ms):
        pn = int(m.group(1))
        start = m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(t)
        spans.append((pn, start, end))
    return spans


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    files = sorted(glob.glob(f"tagged/{BOOK}/*.tagged.md"))
    u_cnt = {k: 0 for k in UNIFORM}
    s_cnt = 0
    pending = dict(SHA_BOX)
    for f in files:
        ch = os.path.basename(f)[:3]
        raw = open(f, encoding="utf-8", newline="").read()
        out = raw
        for old, new in UNIFORM.items():
            u_cnt[old] += out.count(old)
            out = out.replace(old, new)
        # ⊠杀 段级：倒序按偏移替换，避免位置漂移
        spans = [(pn, a, b) for (pn, a, b) in segment_spans(out)
                 if (ch, pn) in pending]
        for pn, a, b in sorted(spans, key=lambda x: -x[1]):
            note = pending[(ch, pn)]
            seg = out[a:b]
            n = seg.count("⟦⊠杀⟧")
            assert n == 1, f"{ch}[{pn}] ⟦⊠杀⟧ 数量 {n} != 1，需人工"
            out = out[:a] + seg.replace("⟦⊠杀⟧", f"⟦⊠杀|{note}⟧") + out[b:]
            del pending[(ch, pn)]
            s_cnt += 1
        if out != raw:
            assert _C1.sk(out) == _C1.sk(raw), f"剥标断言失败 {f}"
            print(f"  {os.path.basename(f)}: 已改")
            if args.apply:
                bak = f"logs/backup/verb_wave1_{ts}/{BOOK}"
                os.makedirs(bak, exist_ok=True)
                if not os.path.exists(os.path.join(bak, os.path.basename(f))):
                    open(os.path.join(bak, os.path.basename(f)), "w",
                         encoding="utf-8", newline="").write(raw)
                open(f, "w", encoding="utf-8", newline="").write(out)
    print(f"统一替换：{ {k[1:-1]: v for k, v in u_cnt.items()} }")
    print(f"⊠杀 语境说明：{s_cnt}/16（{'已落盘' if args.apply else 'dry-run'}）")
    if pending:
        print(f"未命中（需人工）: {sorted(pending.keys())}")
    if not args.apply:
        print("\ndry-run 结束（未写盘）。加 --apply 落盘。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
