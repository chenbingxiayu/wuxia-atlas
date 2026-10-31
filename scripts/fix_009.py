#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""009 第九回残留差异修复"""
import re
import sys

p = "kb/tagged/白发魔女传/009_第九回.tagged.md"
s = open(p, encoding="utf-8").read()
n = 0
pairs = [
    ("⟧卓一航真是", "〖@卓一航〗真是"),
    ("〖@神手|孟飞〗”插口", "〖@神手〗”〖@孟飞〗插口"),
    ("他们⟦◉断⟧了两条腿", "他们不⟦◉断⟧了两条腿"),
    ("原来是⟧镜明长老在塔顶", "原来是〖@镜明老禅师|镜明长老〗在塔顶"),
    ("镜明长老合什赞道", "〖@镜明老禅师|镜明长老〗合什赞道"),
    ("⟧绵掌”", "〖☆绵掌〗”"),
    ("⟧尊胜禅师在", "〖@尊胜禅师〗在"),
    ("⟧岳鸣珂剑招催紧", "〖@岳鸣珂〗剑招催紧"),
]
for old, new in pairs:
    c = s.count(old)
    s = s.replace(old, new)
    n += c
# 镜明长老道：…师弟（引号通配）
s, c = re.subn(r"〖@镜明长老〗(道：.师弟)", r"〖@镜明老禅师|镜明长老〗\1", s)
n += c
open(p, "w", encoding="utf-8", newline="").write(s)
print("fixed", n)
