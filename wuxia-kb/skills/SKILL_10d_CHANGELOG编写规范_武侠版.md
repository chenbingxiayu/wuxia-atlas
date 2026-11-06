---
name: skill-10d-wuxia
title: CHANGELOG 编写规范（武侠版）——让用户看懂的版本叙事
description: 武侠知识库的 CHANGELOG 编写规范：Keep a Changelog 口径（Added/Changed/Fixed/Removed）、条目三要素（做了什么+凭证链接+影响面）、面向用户而非面向提交记录的叙述粒度、坏例子与好例子对照。武侠库现行示例取自 2026-11 批次（同位复指合并、^武功摘除、judgment 终签等）。当需要写版本发布说明、整理批次变更叙事时使用。
version: v0.1-draft
last_updated: 2026-11-06
---

# SKILL_10d CHANGELOG 编写规范（武侠版）

> **上游声明**：本文从 shiji-kb `skills/SKILL_10d_CHANGELOG编写规范.md` 移植（🟢 轻度照搬，机制零修改）；依据 `docs/03-skill与脚本改造清单.md` L175 与 `docs/05` §2.5。原文中的 GitHub 链接（baojie/shiji-kb）与史记条目（如"人名标注错误 615 处"）保留为**格式先例**，武侠库建立远程仓库后按同格式替换。

> **长度说明**：本文整体超 600 行（源文即长）——属"照搬零修改"口径的保留，机制内容未为凑长度而删。
> **武侠适配注**：武侠库的发布叙事分两层——批次层（docs/NN 执行记录，面向开发）与发布层（RELEASE_NOTES + 发布包 manifest，面向用户，见 `logs/release_artifacts/`）；本文规范用于发布层，条目素材从批次层提炼。**武侠库现行好例子**（2026-11-05/06 批次）：① 同位复指形 112 处合并为单标签（scripts/merge_apposition_names.py，正文零增删）；② 泛称"武功/武艺/功夫"292 处摘标（docs/63 §七 拍板）；③ 5 书 judgment 终签 153 条全量复核（docs/66）。

## 快速开始（武侠版四步）

```text
Step 1 定版   发布动作（release_site.py GO / 发布包）发生才写条目；批次内不写
Step 2 分类   Added / Changed / Fixed / Removed 四类归位
Step 3 成条   每条 = 用户视角一句话 + 凭证（脚本/docs 链接）+ 影响面数字
Step 4 链接   commit/Issue 引用按文末链接表格式；远程仓库启用前用 docs/NN 指代
```

# SKILL 10d: CHANGELOG编写规范 — 项目变更的时间线

> **核心理念**：CHANGELOG是给人看的项目历史，不是git log的复制品。高层次总结 + 详细日志链接 = 最佳实践。

---

## 一、CHANGELOG的定位

### 1.1 CHANGELOG vs 其他记录

| 记录类型 | 受众 | 详细程度 | 更新频率 |
|---------|------|---------|---------|
| **CHANGELOG** | 用户、贡献者、决策者 | 高层次总结 | 每日/每版本 |
| **每日工作日志** | 开发者、团队成员 | 详细技术细节 | 每日 |
| **Git Commit** | 开发者 | 代码级变更 | 每次提交 |
| **Release Notes** | 用户 | 用户可见变更 | 每个版本 |

### 1.2 CHANGELOG的作用

1. **对外展示** - 让外部人员快速了解项目进展
2. **版本回顾** - 快速定位某个功能/修复在哪个版本
3. **决策支持** - 为规划提供历史数据
4. **团队沟通** - 共享项目进展和成果

### 1.3 内容原则

**保留在CHANGELOG**：
- 核心功能的总体描述（1-2行概括）
- 重要的新增模块/系统名称和主要链接
- 关键数字（如修复数量、完成章节数）
- 用户可见的重大变更

**移入每日工作日志**：
- 详细的子项列表
- 具体的文件路径和技术细节
- 多层级的嵌套说明
- 每个SKILL/示例的完整列表
- 具体的技术实现方法

---

## 二、基本格式

### 2.1 标准模板

```markdown
## YYYY-MM-DD

### 新增 (Added)

- **功能名称**：简短描述 ([commit_id])

### 修复 (Fixed)

- **问题名称**：简短说明+关键数字 ([commit_id]) ([Issue #N](github_issue_url))

### 更改 (Changed)

- **模块名称**：变更概括 ([commit_id])

### 项目维护 (Maintenance)

- 文档重构 ([commit_id])
- 目录整理 ([commit_id])
- 每日工作日志 ([commit_id])

**详细工作日志**: [`logs/daily/YYYY-MM-DD.md`](logs/daily/YYYY-MM-DD.md)

[commit_id]: https://github.com/baojie/shiji-kb/commit/commit_id
```

### 2.2 日期格式

- **格式**：`## YYYY-MM-DD`
- **示例**：`## 2026-03-29`
- **顺序**：最新日期在最上方
- **频率**：每日更新（即使当日无提交也可添加条目）

### 2.3 分类体系

#### Added（新增）

**定义**：全新的功能、模块、文档

**示例**：
```markdown
### 新增 (Added)

- **SKILL_10项目管理体系** ([a1b2c3d])
  - 包含Issue管理、TODO跟踪、每日日志三大模块
  - 新增SKILL_10/10a/10b共3个文档
```

#### Changed（更改）

**定义**：对现有功能的改进、优化、重构

**示例**：
```markdown
### 更改 (Changed)

- **实体标注格式统一为v2.8** ([d4e5f6g])
  - 18类实体全部迁移为〖TYPE X〗格式
  - 影响全部130章标注文件
```

#### Fixed（修复）

**定义**：Bug修复、错误纠正

**示例**：
```markdown
### 修复 (Fixed)

- **人名实体跨章反思修正615处错误** ([g7h8i9j]) ([Issue #11](https://github.com/baojie/shiji-kb/issues/11))
  - 修正邦国名/氏族名/动词误标为人名
  - 详见跨章反思报告
```

#### Removed（删除）

**定义**：移除的功能、文件、依赖

**示例**：
```markdown
### 删除 (Removed)

- **清理过时的临时脚本** ([j0k1l2m])
  - 删除archive/temp/下的测试脚本
```

#### Maintenance（项目维护）

**定义**：不影响功能的维护性工作

**应归入Maintenance的内容**：
- ✅ 文档重构、README更新
- ✅ 每日工作日志
- ✅ SKILL审阅、完善
- ✅ HTML/索引重建
- ✅ 实体统计更新
- ✅ 参与指南

**不应归入Maintenance的内容**（应归入Added/Changed/Fixed）：
- ❌ 目录/代码重构 → Changed
- ❌ 工具脚本开发 → Added
- ❌ 数据统计工具 → Added
- ❌ CSS样式修复 → Fixed
- ❌ 文件夹重组 → Changed

**示例**：
```markdown
### 项目维护 (Maintenance)

- 更新README索引链接 ([m3n4o5p])
- 新增2026-03-25至03-29每日工作日志 ([p6q7r8s])
- 完善SKILL_03实体构建文档 ([s9t0u1v])
```

---

## 三、Commit链接格式

### 3.1 引用式链接（推荐）

**格式**：

```markdown
- **功能名称**：描述 ([commit_id])

[commit_id]: https://github.com/baojie/shiji-kb/commit/commit_id
```

**优点**：
- 链接集中管理，易于更新
- Markdown源码可读性更好
- 支持同一commit多次引用

**示例**：

```markdown
## 2026-03-29

### 新增 (Added)

- **SKILL_10项目管理体系** ([a1b2c3d] / [b2c3d4e])

### 更改 (Changed)

- **更新SKILL_00添加SKILL_10索引** ([a1b2c3d])

[a1b2c3d]: https://github.com/baojie/shiji-kb/commit/a1b2c3d
[b2c3d4e]: https://github.com/baojie/shiji-kb/commit/b2c3d4e
```

### 3.2 多个commit的表示

**斜杠分隔**（推荐）：

```markdown
- **功能名称** ([commit_1] / [commit_2] / [commit_3])
```

**逗号分隔**（备选）：

```markdown
- **功能名称** ([commit_1], [commit_2], [commit_3])
```

### 3.3 简化格式（GitHub自动识别）

**格式**：

```markdown
- **功能名称**：描述 (commit_id)
```

**说明**：GitHub会自动将7位短hash识别为commit链接

**示例**：

```markdown
- **SKILL_10项目管理体系** (a1b2c3d)
```

**推荐场景**：
- 只有少量commit
- 不需要多次引用同一commit
- 追求简洁

---

## 四、Issue链接格式

### 4.1 标准格式

**格式**：

```markdown
([Issue #N](https://github.com/baojie/shiji-kb/issues/N))
```

**示例**：

```markdown
- **修复标注完整性检查脚本编码问题** ([g7h8i9j]) ([Issue #15](https://github.com/baojie/shiji-kb/issues/15))
```

### 4.2 Issue与Commit的组合

**格式**：

```markdown
- **功能/修复名称** ([commit_id]) ([Issue #N](issue_url))
```

**顺序**：先commit，后Issue

**示例**：

```markdown
### 修复 (Fixed)

- **人名标注错误615处** ([abc1234]) ([Issue #11](https://github.com/baojie/shiji-kb/issues/11))
- **校勘问题修复** ([def5678]) ([Issue #15](https://github.com/baojie/shiji-kb/issues/15))
```

### 4.3 引用式Issue链接（可选）

**格式**：

```markdown
- **功能名称** ([commit_id]) ([Issue #N][i15])

[i15]: https://github.com/baojie/shiji-kb/issues/15
```

**适用场景**：同一Issue被多次引用

---

## 五、详略原则

### 5.1 精简示例对比

#### ❌ 过于详细（应简化）

```markdown
- **司马迁文风提炼实验** ([`labs/sima-qian-style/`](labs/sima-qian-style/))：
  - 三层SKILL架构：现代名词古化 → 白话转文言 → 太史公风格
  - 4个SKILL文件：
    - SKILL-太史公曰.md（主SKILL，高级层）
    - SKILL-白话转文言.md（基础层，9大类转换规则）
    - SKILL-现代名词古化.md（子技能，7大类名词词典）
    - SKILL-核心特征.md（太史公文笔8大维度）
  - 4个完整示例：
    - 乔布斯列传（人物传记体）
    - shiji-kb记（项目介绍，333字完整版）
    - 葛底斯堡演讲（经典演讲，272字）
    - 论Skill之道（技术概念）
  - 快速上手教程（三种使用方法）
```

#### ✅ 精简版本（推荐）

```markdown
- **司马迁文风提炼实验** ([`labs/sima-qian-style/`](labs/sima-qian-style/)) ([0117a82] / [c7a0d55])
  - 三层SKILL架构（现代名词古化 → 白话转文言 → 太史公风格）
  - 包含4个SKILL文件和4个完整示例（乔布斯列传、shiji-kb记、葛底斯堡演讲、Skill概念）
```

### 5.2 精简原则

1. **删除过深层级** - 最多2级列表
2. **合并相似项** - "4个SKILL文件" 代替逐一列举
3. **保留关键数字** - 4个SKILL、4个示例
4. **删除详细描述** - 文件名细节移到工作日志
5. **保留核心链接** - 目录链接、commit链接

### 5.3 关键数字的使用

**保留数字的场景**：

```markdown
✅ - 修正615处人名标注错误
✅ - 完成001-012共12章本纪标注
✅ - 新增4份校对报告
✅ - 实体统计更新至15,190词条
```

**删除数字的场景**：

```markdown
❌ - 更新了3个README文件（无意义）
❌ - 删除了27行代码（技术细节）
❌ - 修改了8个函数签名（技术细节）
```

**原则**：保留有业务意义的数字，删除纯技术指标。

---

## 六、详细日志链接

### 6.1 必须添加

每个日期条目**必须**在末尾添加详细工作日志链接：

```markdown
**详细工作日志**: [`logs/daily/YYYY-MM-DD.md`](logs/daily/YYYY-MM-DD.md)
```

### 6.2 完整示例

```markdown
## 2026-03-29

### 新增 (Added)

- **SKILL_10项目管理体系** ([a1b2c3d])
  - Issue管理、TODO跟踪、每日日志三大模块

### 更改 (Changed)

- **SKILL_00管线总览** ([b2c3d4e])
  - 新增SKILL_10项目管理索引

### 项目维护 (Maintenance)

- 新增2026-03-25至03-29每日工作日志 ([c3d4e5f])

**详细工作日志**: [`logs/daily/2026-03-29.md`](logs/daily/2026-03-29.md)

[a1b2c3d]: https://github.com/baojie/shiji-kb/commit/a1b2c3d
[b2c3d4e]: https://github.com/baojie/shiji-kb/commit/b2c3d4e
[c3d4e5f]: https://github.com/baojie/shiji-kb/commit/c3d4e5f
```

---

## 七、更新流程

### 7.1 每日更新流程

```
1. 每日工作完成后，生成详细工作日志
   ↓
2. 从详细日志中提取核心变更
   ↓
3. 按Added/Changed/Fixed/Maintenance分类
   ↓
4. 精简描述（删除技术细节）
   ↓
5. 添加commit链接和Issue链接
   ↓
6. 在CHANGELOG.md开头插入新条目
   ↓
7. 添加详细工作日志链接
```

### 7.2 工作流联动

```
Git提交 (SKILL_10c)
    ↓
每日工作日志生成 (SKILL_10b)
    ↓
CHANGELOG更新 (SKILL_10d) ← 当前
    ↓
对外发布/版本管理
```

### 7.3 时间节点

**每日更新**：
- 时间：当日工作结束后
- 内容：当日的所有commit
- 位置：CHANGELOG.md开头

**版本发布更新**（可选）：
- 时间：发布新版本时
- 内容：汇总该版本的所有变更
- 格式：`## v1.2.0 (2026-03-29)`

---

## 八、版本发布格式（可选）

### 8.1 版本号条目

**格式**：

```markdown
## v1.2.0 (2026-03-29)

**Release Highlights**:
- 核心功能1
- 核心功能2
- 核心功能3

### 新增 (Added)
...

### 更改 (Changed)
...

### 修复 (Fixed)
...

**详细变更**: 见下方2026-03-01至2026-03-29的每日更新
```

### 8.2 语义化版本号

**格式**：`vMAJOR.MINOR.PATCH`

- **MAJOR**（主版本号）：不兼容的API变更
- **MINOR**（次版本号）：向后兼容的功能新增
- **PATCH**（修订号）：向后兼容的Bug修复

**示例**：
- `v1.0.0` - 初始版本
- `v1.1.0` - 新增拼音注释功能
- `v1.1.1` - 修复拼音注释bug
- `v2.0.0` - 标注格式重大变更（不兼容）

---

## 九、质量检查清单

### 9.1 格式检查

- [ ] 日期格式正确（`## YYYY-MM-DD`）
- [ ] 使用了标准分类（Added/Changed/Fixed/Removed/Maintenance）
- [ ] commit链接格式正确（引用式或简化式）
- [ ] Issue链接格式正确（包含URL）
- [ ] 每个条目有commit链接
- [ ] 添加了详细工作日志链接

### 9.2 内容检查

- [ ] 首行描述清晰（功能名称加粗）
- [ ] 详细描述简洁（不超过2-3行）
- [ ] 保留了关键数字
- [ ] 删除了技术细节
- [ ] 分类准确（Maintenance vs Added/Changed）
- [ ] 最新条目在最上方

### 9.3 链接检查

- [ ] Commit链接可点击（本地测试）
- [ ] Issue链接可点击
- [ ] 详细工作日志链接正确
- [ ] 目录链接（如`labs/xxx/`）正确

---

## 十、常见错误

### 错误1：过于详细

❌ **错误**：

```markdown
- **实体标注更新**：
  - 更新了chapter_md/001_五帝本纪.tagged.md
  - 更新了chapter_md/002_夏本纪.tagged.md
  - 更新了chapter_md/003_殷本纪.tagged.md
  - 更新了chapter_md/004_周本纪.tagged.md
  - 修改了entity_stats.py脚本的第127行
  - 更新了kg/entities/人名.json
```

✅ **正确**：

```markdown
- **完成001-004本纪实体标注** ([abc1234])
  - 标注人名/地名/官职/制度等18类实体
  - 更新实体统计至15,190词条
```

### 错误2：分类不当

❌ **错误**：将工具开发归入Maintenance

```markdown
### 项目维护 (Maintenance)

- 开发标注完整性检查工具
```

✅ **正确**：归入Added

```markdown
### 新增 (Added)

- **标注完整性检查工具** ([def5678])
  - 自动检查标注文件与原文的一致性
```

### 错误3：缺少链接

❌ **错误**：

```markdown
- **修复人名标注错误**
```

✅ **正确**：

```markdown
- **修复615处人名标注错误** ([abc1234]) ([Issue #11](https://github.com/baojie/shiji-kb/issues/11))
```

### 错误4：描述模糊

❌ **错误**：

```markdown
- **更新了一些文件**
- **做了一些改进**
```

✅ **正确**：

```markdown
- **统一18类实体标注格式为v2.8** ([abc1234])
- **优化反思脚本性能提升3倍** ([def5678])
```

---

## 十一、工具支持

### 11.1 自动化脚本（可选）

**从每日日志生成CHANGELOG条目**：

```bash
# 生成CHANGELOG条目草稿
python scripts/changelog/generate_entry.py 2026-03-29

# 输出：
## 2026-03-29

### 新增 (Added)

- **SKILL_10项目管理体系**
  - （待添加commit链接）

### 更改 (Changed)
...

**详细工作日志**: [`logs/daily/2026-03-29.md`](logs/daily/2026-03-29.md)
```

### 11.2 验证脚本（可选）

```bash
# 验证CHANGELOG格式
python scripts/changelog/validate.py

# 检查：
# - 日期格式
# - commit链接有效性
# - Issue链接有效性
# - 详细日志链接存在性
```

---

## 十二、示例

### 12.1 完整示例

```markdown
# CHANGELOG

## 2026-03-29

### 新增 (Added)

- **SKILL_10项目管理体系** ([a1b2c3d] / [b2c3d4e])
  - Issue管理（7类分类）、TODO跟踪、每日日志三大模块
  - 包含SKILL_10/10a/10b共3个文档

- **Issue七类标签系统** ([c3d4e5f])
  - REF/FEAT/BUG/RES/DOC/HELP/QA分类
  - 批量管理脚本和统计工具

### 更改 (Changed)

- **SKILL_00管线总览** ([d4e5f6g])
  - 从"九大阶段"扩展为"十大模块"
  - 新增项目管理模块（横向支撑）

### 修复 (Fixed)

- **修复Issue #14联系方式** ([e5f6g7h]) ([Issue #14](https://github.com/baojie/shiji-kb/issues/14))
  - 添加HELP-求助标签

### 项目维护 (Maintenance)

- 新增2026-03-25至03-29每日工作日志 ([f6g7h8i])
- 更新README索引链接 ([g7h8i9j])

**详细工作日志**: [`logs/daily/2026-03-29.md`](logs/daily/2026-03-29.md)

[a1b2c3d]: https://github.com/baojie/shiji-kb/commit/a1b2c3d
[b2c3d4e]: https://github.com/baojie/shiji-kb/commit/b2c3d4e
[c3d4e5f]: https://github.com/baojie/shiji-kb/commit/c3d4e5f
[d4e5f6g]: https://github.com/baojie/shiji-kb/commit/d4e5f6g
[e5f6g7h]: https://github.com/baojie/shiji-kb/commit/e5f6g7h
[f6g7h8i]: https://github.com/baojie/shiji-kb/commit/f6g7h8i
[g7h8i9j]: https://github.com/baojie/shiji-kb/commit/g7h8i9j

---

## 2026-03-28

### 新增 (Added)

- **太史公曰无提交日处理规范** ([h8i9j0k])
  - 32字赞文（8个四字句）格式
  - 4个示例（休整/思考/持续/工程主题）

### 项目维护 (Maintenance)

- 补充03-25至03-27每日工作日志 ([i9j0k1l])
- 更新CHANGELOG编写规范 ([j0k1l2m])

**详细工作日志**: [`logs/daily/2026-03-28.md`](logs/daily/2026-03-28.md)

[h8i9j0k]: https://github.com/baojie/shiji-kb/commit/h8i9j0k
[i9j0k1l]: https://github.com/baojie/shiji-kb/commit/i9j0k1l
[j0k1l2m]: https://github.com/baojie/shiji-kb/commit/j0k1l2m
```

---

## 十三、与其他SKILL的关系

```
SKILL_10d CHANGELOG编写规范
    ├─ 输入来源：
    │   ├─ Git Commit历史 (SKILL_10c)
    │   └─ 每日工作日志 (SKILL_10b)
    │
    ├─ 输出：
    │   └─ CHANGELOG.md（项目变更历史）
    │
    └─ 联动：
        ├─ Issue管理 (SKILL_10a) - Issue链接
        ├─ Git提交 (SKILL_10c) - Commit链接
        └─ 每日日志 (SKILL_10b) - 详细日志链接
```

**完整工作流**：

```
代码/文档变更
    ↓
Git Commit (SKILL_10c) - 详细描述
    ↓
每日工作日志 (SKILL_10b) - 技术细节
    ↓
CHANGELOG (SKILL_10d) - 高层次总结 ← 当前
    ↓
对外展示/版本管理
```

---

## 十四、参考资源

- Keep a Changelog: https://keepachangelog.com/
- Semantic Versioning: https://semver.org/
- 项目CHANGELOG: `CHANGELOG.md`
- Git提交规范: `SKILL_10c_Git代码版本管理规范_武侠版.md`
- 每日日志规范: `SKILL_10b_每日工作日志维护_武侠版.md`

---

## 结语

**CHANGELOG不是给机器看的日志，是给人看的故事。** 每个条目都应该让读者快速理解：项目做了什么重要的事，解决了什么问题，有什么价值。

高层次总结 + 详细日志链接 = 最佳实践。让CHANGELOG成为项目进展的时间线，让每个里程碑都有迹可循。


---

## 工具与脚本

`scripts/release_site.py`（发布 GO 与 RELEASE_NOTES 生成）、`scripts/build_release_artifact.py`（发布包 manifest）、`logs/release_artifacts/latest.json`（版本事实源）；条目数字以 `logs/qa/` 实测为准。

---

## 检查清单（武侠版）

- [ ] 条目面向用户（不出现内部代号堆砌；docs/NN 只作凭证链接）
- [ ] 每条三要素齐：做了什么 + 凭证 + 影响面（页数/条数/回数）
- [ ] 分类正确（Added/Changed/Fixed/Removed），Removed 必须说明迁移去向
- [ ] 与 RELEASE_NOTES、发布包 manifest 数字一致（页数/文件数/sha256）

## 成功标准（武侠版）

- 发布包可独立阅读：不翻 docs 也能看懂这版变了什么
- 每条变更可溯源到脚本/文档/验收记录
- 无"修复若干问题"式空泛条目；数字与 `logs/qa/` 实测一致
- lint_skills PASS（score ≥ 90），无 error
