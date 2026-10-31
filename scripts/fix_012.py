#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""012 残留修复"""
p = "kb/tagged/白发魔女传/012_第十二回.tagged.md"
s = open(p, encoding="utf-8").read()
n = 0
for old, new in [
    ("〖@光宗〗最宠的妃子", "〖@光宗|常洛〗最宠的妃子"),
    ("一⟦◈摆五行轮从房中", "一⟦◈摆⟧〖•五行轮〗从房中"),
    ("来⟦▲抢熊廷弼宝剑", "来⟦▲抢⟧〖@熊廷弼〗宝剑"),
]:
    c = s.count(old)
    s = s.replace(old, new)
    n += c
open(p, "w", encoding="utf-8", newline="").write(s)
print("fixed", n)
