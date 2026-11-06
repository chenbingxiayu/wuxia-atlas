# -*- coding: utf-8 -*-
"""一次性：C1 dry-run 明细分布校验。"""
import collections
import io
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

rows = io.open("logs/qa/c1_dryrun_detail.txt", encoding="utf-8").read().splitlines()
r1 = collections.Counter(r.split()[2].strip("〖#〗") for r in rows if " R1 " in r)
print("R1 词分布:", dict(r1.most_common()))
r3 = collections.Counter(
    re.search(r"〖.(.)〗", r).group(1) for r in rows if " R3 " in r)
print("R3 字分布:", dict(r3.most_common()))
r2 = collections.Counter(r.split()[2] for r in rows if " R2 " in r)
print("R2 分布:", dict(r2.most_common()))
