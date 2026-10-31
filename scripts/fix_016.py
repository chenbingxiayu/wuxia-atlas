# -*- coding: utf-8 -*-
"""修复 016 残余问题：
1. 补回遗漏的（忠贤）
2. 清理混用闭合符：⟦…〗 → ⟦…⟧，以及残留 〧 〒
"""
import io, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PATH = r"kb/tagged/白发魔女传/016_第十六回.tagged.md"

with open(PATH, encoding='utf-8') as f:
    text = f.read()

# 1. 补回（忠贤）
old1 = "〖@魏宗主|魏忠贤〗除此心腹大患"
new1 = "〖@魏宗主〗（忠贤）除此心腹大患"
assert old1 in text, "pattern1 not found"
text = text.replace(old1, new1)

# 2. 动词标记混用闭合：⟦…〗 → ⟦…⟧
before = len(re.findall(r'⟦[^⟦⟧]*〗', text))
text = re.sub(r'⟦([^⟦⟧]*)〗', r'⟦\1⟧', text)
print(f"混用闭合修复: {before}")

# 3. 残留装饰性错字
for ch in ['〧', '〒', '〶', '〸', '〹', '〺']:
    if ch in text:
        print(f"残留字符 {ch!r}: {text.count(ch)} 处")

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(text)
print("done")
