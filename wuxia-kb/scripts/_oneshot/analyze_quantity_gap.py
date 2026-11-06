# -*- coding: utf-8 -*-
"""一次性分析：020-032 的 $ 数量层 kept vs bare，按量词聚合，并抽金标准同形对照。"""
from __future__ import annotations

import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parents[2]
TAG = ROOT / "tagged" / "白发魔女传"
D = chr(36)
TOK = re.compile(r"〖[^〖〗]*〗|⟦[^⟧]*⟧|〘[^〙]*〙")
QTOK = re.compile("〖" + re.escape(D) + r"([^〖〗]+)〗")

NUM = r"(一|两|三|四|五|六|七|八|九|十|几|数|半|廿|卅|百|千|二三十|三十余|二十余|十余|数十|十多|百多|六七|七八|三五)"
M = ("个|名|位|人|声|掌|拳|眼|场|阵|口|步|回|次|遍|番|层|截|段|只|条|根|枝|片|股|堆|群|队|伙|年|月|日|"
     "里|丈|尺|寸|斤|石|柄|张|杯|朵|块|把|招|剑|笔|封|艘|匹|头|骑|间|座|点|滴|丝|缕|道|重|门|路|带|扇|"
     "亩|顷|斗|升|合|锭|批|行|字|句|页|卷|册|部|章|节|则|项|宗|件|套|双|对|副|串|排|列|艇|轿|车|担|包|"
     "裹|袋|箱|笼|窝|进|院|落|家|处|座")
PAT = re.compile(NUM + "(" + M + ")")

kept: Counter = Counter()
bare_forms: dict[str, Counter] = defaultdict(Counter)
for n in range(20, 33):
    t = io.open(TAG / f"{n:03d}.tagged.md", encoding="utf-8").read()
    for m in QTOK.finditer(t):
        kept[m.group(1)] += 1
    s = TOK.sub(lambda m: "\x00" * len(m.group(0)), t)
    for m in PAT.finditer(s):
        bare_forms[m.group(2)][m.group(0)] += 1

kept_by_m: Counter = Counter()
for w, c in kept.items():
    if w:
        kept_by_m[w[-1]] += c

print("machine kept $ vocab:", [f"{k}:{v}" for k, v in kept.most_common(30)])
print()
rows = []
for mw in set(kept_by_m) | set(bare_forms):
    rows.append((kept_by_m[mw], sum(bare_forms[mw].values()), mw,
                 dict(bare_forms[mw].most_common(4))))
rows.sort(key=lambda r: -(r[0] + r[1]))
print(f"{'量词':<3s} {'kept':>5s} {'bare':>5s}  bare 形态 top4")
for k, b, mw, top in rows:
    print(f"{mw:<3s} {k:>5d} {b:>5d}  {top}")

# 金标准对照：同样模式在 001-019 的 kept/bare（同码口径）
gkept: Counter = Counter()
gbare: dict[str, Counter] = defaultdict(Counter)
for n in range(1, 20):
    t = io.open(TAG / f"{n:03d}.tagged.md", encoding="utf-8").read()
    for m in QTOK.finditer(t):
        gkept[m.group(1)] += 1
    s = TOK.sub(lambda m: "\x00" * len(m.group(0)), t)
    for m in PAT.finditer(s):
        gbare[m.group(2)][m.group(0)] += 1
print()
print("gold kept $ total:", sum(gkept.values()), " gold bare matches:", sum(sum(v.values()) for v in gbare.values()))
print("gold kept by measure:", {k: v for k, v in gkept.most_common(0)})
g_by_m: Counter = Counter()
for w, c in gkept.items():
    if w:
        g_by_m[w[-1]] += c
print(f"{'量词':<3s} {'g_kept':>6s} {'g_bare':>6s}")
for k, b, mw, _ in rows[:40]:
    print(f"{mw:<3s} {g_by_m[mw]:>6d} {sum(gbare[mw].values()):>6d}")
