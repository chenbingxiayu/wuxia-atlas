# -*- coding: utf-8 -*-
"""修复 016 两处缺闭合的动词标记：⟦◈X〖 → ⟦◈X⟧〖"""
import io, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PATH = r"kb/tagged/白发魔女传/016_第十六回.tagged.md"
with open(PATH, encoding='utf-8') as f:
    text = f.read()

# ⟦动词X〖 → ⟦动词X⟧〖 （后随实体标记时缺动词闭合）
before = len(re.findall(r'⟦[◉◈○▲◇][^⟦⟧〖〗]*〖', text))
text = re.sub(r'⟦([◉◈○▲◇][^⟦⟧〖〗]*)〖', r'⟦\1⟧〖', text)
print(f"缺闭合修复: {before}")

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(text)
