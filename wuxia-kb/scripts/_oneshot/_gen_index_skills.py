# -*- coding: utf-8 -*-
"""一次性：生成 skills/INDEX.md 底稿（提取各件 frontmatter 的 title/description 自动分组）。

用法：python -X utf8 scripts/_oneshot/_gen_index_skills.py
产物：skills/INDEX.md（整文件重写；分组表人工核对后由本脚本固化）
注意：重跑会覆盖 INDEX.md 的人工补充段——如手工编辑过，先 diff 再合并。
"""
import io
import re
from pathlib import Path

skills = Path('skills')
rows = {}
for p in sorted(skills.glob('*.md')):
    if p.name in ('INDEX.md', 'README.md'):
        continue
    t = p.read_text(encoding='utf-8')
    m = re.match(r'^---\n(.*?)\n---\n', t, re.S)
    title, desc = p.stem, ''
    if m:
        fm = m.group(1)
        mt = re.search(r'^title:\s*(.+)$', fm, re.M)
        md_ = re.search(r'^description:\s*(.+)$', fm, re.M)
        if mt:
            title = mt.group(1).strip()
        if md_:
            desc = md_.group(1).strip()
    rows[p.name] = (title, desc.split('；')[0].split('。')[0][:60])

GROUPS = [
 ('00 管线总览', ['SKILL_00_管线总览_武侠版.md']),
 ('01 基础与符号', [n for n in rows if re.match(r'SKILL_01', n)]),
 ('02 结构与词法', [n for n in rows if re.match(r'SKILL_02', n)]),
 ('03 实体层', [n for n in rows if re.match(r'SKILL_03', n)]),
 ('04 事件层', [n for n in rows if re.match(r'SKILL_04', n)]),
 ('05 关系层', [n for n in rows if re.match(r'SKILL_05', n)]),
 ('06 本体层', [n for n in rows if re.match(r'SKILL_06', n)]),
 ('07 推理层', [n for n in rows if re.match(r'SKILL_07', n)]),
 ('08 SKU 与评估', [n for n in rows if re.match(r'SKILL_08', n)]),
 ('09 应用层', [n for n in rows if re.match(r'SKILL_09', n)]),
 ('合并稿（体系总纲）', [n for n in rows if re.match(r'SKILL_(SKU卡片|关系体系|分类树五件套|地名gazetteer|常识与设定一致性|时间体系|词表体系规划|跨书治理)', n)]),
 ('10 项目管理', [n for n in rows if re.match(r'SKILL_10', n)]),
 ('META 元技能', [n for n in rows if n.startswith('META-')]),
 ('W 组（站点/洞察）', [n for n in rows if re.match(r'W\d', n)]),
]
covered = {n for _, ns in GROUPS for n in ns}
other = [n for n in rows if n not in covered]

L = ["""---
name: skills-index-wuxia
title: skills/ 全库索引——100+ 方法件的分组导航
description: wuxia-kb/skills/ 全部 SKILL/META/W 方件（含 2026-11-06 新增 19 件）的分组索引：00 管线总览、01-10 管线组、合并稿总纲、META 元技能、W 组站点件；每件一行说明。当需要快速定位"某类工作该读哪份方法件"时使用。
version: v0.1-draft
last_updated: 2026-11-06
scope: skills/ 导航件（自动生成底稿+人工分组；新增方法件后重跑 scripts/_oneshot/_gen_index_skills.py 同步）
---

# skills/ 全库索引（武侠版）

> 完整方法件索引：管线技能（00-10 组）+ 合并稿总纲 + META 元技能 + W 组站点件。
> 用法：按组找文件 → 读该文件 frontmatter 的 description 与"快速开始"。
> 配套：管线阶段地图见 `SKILL_00_管线总览_武侠版.md`；规律库索引见 `../references/README.md`。
"""]
for gname, files in GROUPS:
    if not files:
        continue
    L.append(f"\n## {gname}（{len(files)} 件）\n")
    L.append("| 文件 | 说明 |")
    L.append("|---|---|")
    for n in files:
        _, short = rows[n]
        L.append(f"| [{n}]({n}) | {short} |")
if other:
    L.append(f"\n## 其他（{len(other)} 件）\n")
    L.append("| 文件 | 说明 |")
    L.append("|---|---|")
    for n in other:
        _, short = rows[n]
        L.append(f"| [{n}]({n}) | {short} |")
L.append("""
---

## 快速开始（如何用本索引）

```text
Step 1 定组   按"管线总览 → 01-10 组 → 合并稿 → META → W"顺序找到工作所属组
Step 2 点件   进文件先读 frontmatter description + "快速开始"节
Step 3 查靠   阶段位置看 SKILL_00；规律支撑看 ../references/README.md
```

**使用示例**：要跑一批新书标注 → 00 管线总览（阶段图）→ 03a（生产入口）→ 02a_02b（结构门）
→ 08c（成本记账）→ 10 组（批次记录与提交纪律）。

---

## 工具与脚本

本索引由 `scripts/_oneshot/_gen_index_skills.py` 生成底稿（提取各件 frontmatter 的
title/description 自动分组），人工核对后落盘；新增方法件后重跑同步。

## 检查清单

- [ ] 新增/更名方法件后索引已同步（重跑生成脚本）
- [ ] 每件说明来自其 frontmatter，不手写二手描述
- [ ] 与 `SKILL_00_管线总览_武侠版.md` 的阶段对照表不冲突
- [ ] lint_skills PASS（score ≥ 90）

## 成功标准

- 任何方法件 30 秒内可从本索引定位
- 索引与实际文件集合零漂移（件数一致）
- lint_skills PASS（score ≥ 90），无 error
""")
L.append(f"\n合计 {len(rows)} 件（不含本索引与 README）。最后更新：2026-11-06。\n")
io.open(skills / 'INDEX.md', 'w', encoding='utf-8', newline='\n').write('\n'.join(L))
print('INDEX.md regenerated;', len(rows), 'files indexed; other-group:', other)
