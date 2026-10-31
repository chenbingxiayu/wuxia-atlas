# -*- coding: utf-8 -*-
"""修复 017 三处：动词闭合、金名戈、疾刺"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PATH = r"kb/tagged/白发魔女传/017_第十七回.tagged.md"
with open(PATH, encoding='utf-8') as f:
    text = f.read()

# 1. ⟦◇收〗 → ⟦◇收⟧
n = text.count("⟦◇收〗")
text = text.replace("⟦◇收〗", "⟦◇收⟧")
print(f"◇收 闭合修复: {n}")

# 2. 化名先不标（批次2教训：揭示后回填）
old2 = "那小子自称姓〖@金戈|铁珊瑚〗，他们都住在楼上"
new2 = "那小子自称姓金名戈，他们都住在楼上"
assert old2 in text, "pattern2 not found"
text = text.replace(old2, new2)

# 3. 补漏字 疾
old3 = "向〖@玉罗刹|练霓裳〗平胸⟦◈刺⟧"
new3 = "向〖@玉罗刹|练霓裳〗平胸⟦◈疾刺⟧"
assert old3 in text, "pattern3 not found"
text = text.replace(old3, new3)

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(text)
print("done")
