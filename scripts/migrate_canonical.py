# -*- coding: utf-8 -*-
"""跨回统一迁移（Phase 4 挂账 #1）：
裸柄 → 管道柄，与全书 canonical 对齐。管道在剥标时移除，不影响 lint 完整性。
  001/010/012/018/028
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

JOBS = [
    ("kb/tagged/白发魔女传/001_第一回.tagged.md", "〖@神宗〗", "〖@神宗|朱翊钧〗"),
    ("kb/tagged/白发魔女传/010_第十回.tagged.md", "〖@光宗〗", "〖@光宗|常洛〗"),
    ("kb/tagged/白发魔女传/012_第十二回.tagged.md", "〖@光宗〗", "〖@光宗|常洛〗"),
    ("kb/tagged/白发魔女传/018_第十八回.tagged.md", "〖@小闯王〗", "〖@小闯王|李自成〗"),
    ("kb/tagged/白发魔女传/028_第二十八回.tagged.md", "〖@天都居士〗", "〖@天都居士|霍天都〗"),
]

for path, old, new in JOBS:
    with open(path, encoding='utf-8') as f:
        t = f.read()
    n = t.count(old)
    assert n > 0, f"{path}: pattern not found: {old}"
    # 确认不存在已带管道的旧柄（避免误替换）
    assert old[:-1] + "|" not in t or old not in t.replace(old + "|", ""), path
    t = t.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(t)
    print(f"{path}: {old} -> {new}  x{n}")
print("migration done")
