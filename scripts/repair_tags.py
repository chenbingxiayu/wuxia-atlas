#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用标注修复器：处理三类机械损坏
  1) 实体标记被吞后其闭合符变成了 ⟧ —— 还原为 〗
  2) 动词标记缺闭合符（后面紧跟 〖）—— 在 〖 前补 ⟧
  3) 残留的 〒 / 〧 误字 —— 还原为 ⟧
用法：python scripts/repair_tags.py <tagged文件> ...
"""
import re
import sys

for p in sys.argv[1:]:
    s = open(p, encoding="utf-8").read()
    n0 = 0
    # 0) 动词标记闭合符误作 〗 —— 还原为 ⟧
    def fix_verb_close(m):
        global n0
        n0 += 1
        return "⟦" + m.group(1) + "⟧"
    s = re.sub(r"⟦([◉◈○▲◇][^〖〗⟦⟧\n]*)〗", fix_verb_close, s)
    n1 = 0
    # 1) 实体闭合符还原
    def fix_entity(m):
        global n1
        n1 += 1
        return "〖" + m.group(1) + "〗"
    s = re.sub(r"〖(@[^〖〗⟦⟧\n]*)⟧", fix_entity, s)
    # 2) 动词缺闭合符（⟦动词… 后直接跟 〖）
    n2 = 0
    def fix_verb(m):
        global n2
        n2 += 1
        return "⟦" + m.group(1) + "⟧" + m.group(2)
    s = re.sub(r"⟦([◉◈○▲◇][^〖〗⟦⟧\n]*?)(〖)", fix_verb, s)
    # 3) 误字
    n3 = s.count("〒") + s.count("〧")
    s = s.replace("〒", "⟧").replace("〧", "⟧")
    # 4) 孤儿闭合符（⟧ 紧贴标记开头）—— 删除
    n4 = 0
    # 孤儿闭合符：状态机逐行清理——闭合符只有在对应开标记未闭合时才合法；
    # 栈空（或与未闭合开标记不匹配）且后面紧跟开标记的闭合符是残留，删除。
    # （旧正则版会把 ⟦◈击⟧〖@…〗 的合法动词闭合误删，造成级联损伤，故弃用。）
    fixed_lines = []
    for ln in s.split("\n"):
        out = []
        stack = []
        i, n = 0, len(ln)
        while i < n:
            c = ln[i]
            if c in "〖⟦":
                stack.append(c)
                out.append(c)
                i += 1
            elif c in "〗⟧":
                want = "〖" if c == "〗" else "⟦"
                if stack and stack[-1] == want:
                    stack.pop()
                    out.append(c)
                elif i + 1 < n and ln[i + 1] in "〖⟦":
                    n4 += 1          # 孤儿：删除
                else:
                    out.append(c)    # 位置存疑，保留给 lint 判定
                i += 1
            else:
                out.append(c)
                i += 1
        fixed_lines.append("".join(out))
    s = "\n".join(fixed_lines)
    open(p, "w", encoding="utf-8", newline="").write(s)
    print(f"{p}: 实体闭合还原 {n1}, 动词补闭合 {n2}, 误字 {n3}, 孤儿清理 {n4}")
