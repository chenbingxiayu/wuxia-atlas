---
name: meta-07-readability-wuxia
title: META-07 可读性记录（武侠版）—— 脚本与 SKILL 的可读性规范、规模与检查表
description: META-07 可读性记录的武侠版。当需要新增/重构脚本、写或改 SKILL、做命名与分层评审、或统计项目规模时使用。含当前规模（69 脚本 34,294 行/60+ skills）、命名前缀表、L0-L4 分层、CLI 契约、SKILL 结构规范、可读性检查表与真实正反案例。
version: 0.1-draft
last_updated: 2026-11-05
---

> ## 武侠适配说明（迁移纪律）
>
> - **改造依据**：`docs/04-META元技能逐项改造分析.md` §2.12（M07 轻度适配：符号语义表按武侠类型表重写；分类树换武功谱系树/门派树并处理跨书变体；错误消息断言范围改"武侠宇宙年代约束"）；波次见 `docs/17` §2.6 第三波。
> - **源文件**：shiji-kb 的 META-07 可读性记录（人类优先格式与可读性纪律照搬；史记示例/分类树/错误消息替换）。
> - **照搬（方法论框架层，明确声明）**：人类优先的数据格式（Token/Markdown/Git 友好）、命名规范、PASS/FAIL 返回码、ERROR-WARNING-INFO 分级、目录与产物路径纪律、"可读性是可检查的"（lint 化）。
> - **已替换（示例层全部武侠化）**：符号语义表=01g 的 15 实体+6 动词域；分类树=五树 64 叶（武功谱系/门派树）+跨书变体（D07 双层 canonical）；错误消息断言=武侠宇宙年代约束（N4 时点/时代锚）。
> - **补写（硬缺口）**：§二 当前规模统计（69 脚本/60+ skills）；§三 脚本命名前缀表与 L0-L4 分层；§四 SKILL 结构规范（lint_skills 100/100 门槛）；§六 正反案例。
> - **待回填（上线后回填）**：W 组 38 件与 references/templates 落地后的目录规范；规模数字随时点更新；错误消息清单随 N4/N8 规则扩展。

# META-07 可读性记录（武侠版）

---

## 快速开始

1. **新增脚本**：按 §三 命名前缀表取名 → 放 L0-L4 对应层 → 写文件头 docstring → CLI 默认 dry-run + `--selftest` → 登记 `scripts/README.md`。
2. **新增/改 SKILL**：复制现有主文件骨架（frontmatter/快速开始/工具与脚本/检查清单/成功标准/附录）→ 跑 `scripts/lint_skills.py` 至 PASS ≥90。
3. **评审**：按 §五 检查表逐项打勾；命名/分层/接口违规即返工。
4. **登记**：脚本登记 scripts/README；SKILL 登记 skills/README（文件/行数/版本/状态）；批次记录写 docs 编号。
5. **统计**：规模数字带统计时点与口径（见 §二 注）。

> 成功标准：新脚本/新 SKILL 一次评审通过率 ≥90%；`scripts/lint_skills.py` PASS 100/100；登记与产物 24h 内同步。

---

## 一、当前规模（统计时点 2026-11-05 19:1x）

| 类别 | 数量 | 行数 | 说明 |
|---|---:|---:|---|
| `scripts/` 下 .py | **69** | **34,294** | 含地基 4 + C 族移植 + N 族新写 + 验收/导出工具 |
| `skills/*.md` | **62** | **20,923** | 53 SKILL + 8 META + README（本波 4 件 META 完成后 66） |
| `references/*.md` | 2 | 684 | README + 03c1 规律库（48 条） |
| `docs/*.md` | 60+ | — | 编号记录 01-58 + 专项报告 |
| `registry/` | 14 类子目录 | — | entities/time/relations/consistency/gazetteer/sku/crossover/intertext/… |
| `logs/` | 6 类子目录 | — | qa/annotate/export/time/relations/sku/… |

> 口径注：docs/58 §八 记为"69 脚本 / 60 skills（51 SKILL+8 META+README）"；本件统计时点并发补写已至 62 件。**规模数字必须带时点**，引用旧值时注明来源。
> 参照：docs/42 审计时 45 脚本/25 主文件；docs/56 时 60 脚本；docs/57 时 66 脚本。

## 二、四原则（可读性的可检查化）

| 原则 | 含义 | 检查方式 |
|---|---|---|
| 单一来源 | 路径/符号/词表/映射解析各只有一个实现 | `import config/symbols/masker`，禁本地字符类与相对路径 |
| 分层 | 地基→移植→新写→验收→导出，依赖单向 | §三 L0-L4；上层可依赖下层，反向禁止 |
| 命名即文档 | 前缀表明动作（lint/tag/build/export/fix/apply），后缀表明对象 | §三 前缀表；`wuxia` 后缀仅用于跨书通用件 |
| 契约化 CLI | dry-run 默认、`--apply` 才写、`--selftest` 自检、`--strict` 门禁 | 逐脚本 `--help` 检查；写操作必须备份+断言 |

## 三、脚本规范

### 3.1 命名前缀表

| 前缀 | 语义 | 代表 |
|---|---|---|
| `config` / `symbols` / `masker` / `wordlist_compiler` | 地基四模块（无前缀，全脚本依赖） | 路径/符号/词表唯一来源 |
| `lint_` | 只读检查，返回 error/warning 计数 | `lint_text_integrity.py`、`lint_consistency.py`、`lint_skills.py` |
| `tag_` | 候选召回/补标建议（默认 TSV，不写 tagged） | `tag_quantity_entities.py`、`tag_new_entity_types.py` |
| `build_` | 从上游产物聚合生成数据 | `build_entity_concordance.py`、`build_sku_cards.py` |
| `export_site_` | 新管线→site/data 导出（EX 组） | `export_site_all.py`、`export_site_graph.py` |
| `detect_` / `generate_` | 检测与生成（结构层） | `detect_verse_wuxia.py`、`generate_pn_wuxia.py` |
| `fix_` / `repair_` / `apply_` | 机械修复与应用（必须备份+剥标断言） | `fix_annotation_mechanical.py`、`apply_entity_registration.py` |
| `merge_` / `validate_` / `finalize_` | 归并/校验/终签 | `merge_crossover.py`、`validate_verb_tagging_wuxia.py`、`finalize_judgment.py` |
| `accept_` / `qa_` / `annotate_` | 验收/质检/标注执行 | `accept_batch.py`、`qa_annotation_report.py`、`annotate_chapter_llm.py` |
| `_oneshot/` | 一次性历史脚本（不登记为主链） | `rebuild_tagged_from_struct.py`、`fix_ethnicity_type.py` |

> 命名纪律：**动作+对象**（`lint_fence_format` 而非 `check_fence`）；同一动作不混用同义词（检查统一 `lint_`，不用 `check_/verify_/audit_`）；跨书通用件才加 `_wuxia`（`time_resolver_wuxia`、`detect_verse_wuxia`），单书件不加。

### 3.2 分层（L0-L4，依赖单向）

| 层 | 内容 | 纪律 |
|---|---|---|
| L0 地基 | `config` / `symbols` / `masker` / `wordlist_compiler` | 全脚本 import；禁本地字符类/拼路径（修 shiji 三种路径写死+15 处符号矛盾债） |
| L1 移植改造 | C 族（lint/tag/extract/apply 等） | 接 L0；差异记各件附录 A |
| L2 新写 | N 族（`generate_pn_wuxia`/`detect_verse_wuxia`/`validate_verb_tagging_wuxia`/`time_resolver_wuxia`/`relation_validator`/`merge_crossover`/`gazetteer_migrate`/`lint_consistency`/`lint_taxonomy`/`build_sku_cards`/`update_intertext_loc`） | 依赖设计稿（D0x）+ L0 |
| L3 验收/终签 | `accept_batch` / `qa_annotation_report` / `finalize_judgment` | 只读上游，产物落 registry/logs |
| L4 导出 | `export_site_*` | 只读新管线产物；契约 hard_gap=0 |

### 3.3 文件头与 CLI 契约

```python
"""<一句话职责>（<节点号>，<设计源 D0x>）。

输入：<只读源>
输出：<产物路径>
用法：python scripts/<name>.py [--book 书] [--all] [--selftest]
纪律：默认 dry-run；--apply 备份+写后断言；--strict 有 error exit 1。
"""
```

| 契约 | 要求 |
|---|---|
| 默认 | dry-run（只报告/只写 staging） |
| 写操作 | `--apply` 才落盘；先备份（`backup/`/`logs/backup/`）+ 写后断言 |
| 自检 | `--selftest` 内置用例（如 N4 30/30、N6 21/21） |
| 门禁 | `--strict` 有 error 时 exit 1 |
| 输出 | 统一走 `config.DIR_*`；日志落 `logs/<domain>/` |
| 编码 | Windows 控制台 `io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')` |
| 密钥 | 一律经 `api_config`（env `WUXIA_API_*` 优先），禁硬编码 |

## 四、SKILL 规范

| 项 | 要求 | 检查 |
|---|---|---|
| frontmatter | `name/title/description/version/last_updated` | lint 10 分项 |
| 快速开始 | ≤150 字步骤（1-6 步） | lint 5 分项 |
| 工具与脚本 | 表：工具 → 用途（引用真实存在的 `scripts/` 下脚本） | lint 10 分项（引用不存在即扣分） |
| 检查清单 | `## …检查清单` + `- [ ]` 项 | lint 10 分项 |
| 成功标准 | 可量化（数量/率/门槛） | lint 10 分项 |
| 示例 | ≥1 代码块/模板 | lint 10 分项 |
| 附录 | A 差异对照 / B 待补或待回填 | 人工评审 |
| 长度 | <600 行（超长仅 warning，如 SKILL_03b 716 行 PASS 90） | lint length 项 |
| 版本登记 | skills/README 登记文件/行数/版本/状态 | Lead 收口 |

> lint 门槛：`python -X utf8 scripts/lint_skills.py <file>` PASS ≥90；本波 META 目标 100/100。

## 五、可读性检查清单

**脚本**
- [ ] 命名符合前缀表（动作+对象，无同义混用）；
- [ ] 位于正确层级，依赖单向（不反向 import 上层）；
- [ ] 路径/符号/词表均经 L0（无本地字符类、无硬编码路径）；
- [ ] 文件头 docstring（职责/输入/输出/用法/纪律）；
- [ ] CLI 默认 dry-run，写操作有 `--apply`+备份+断言；
- [ ] `--selftest` 通过；`--strict` 语义明确；
- [ ] 输出路径经 `config`，日志落 `logs/<domain>/`；
- [ ] 已登记 `scripts/README.md`。

**SKILL**
- [ ] frontmatter 五字段齐全；
- [ ] 快速开始 ≤150 字且步骤可执行；
- [ ] 工具与脚本引用真实存在；
- [ ] 检查清单/成功标准/示例齐全；
- [ ] `scripts/lint_skills.py` PASS ≥90（本波目标 100）；
- [ ] 版本号与 last_updated 已更新；
- [ ] 已登记 `skills/README.md`；
- [ ] 附录 A/B 与上游设计稿对齐。

## 六、真实案例（正反各半）

### 正例 1 · 四地基模块消灭历史债
shiji 债：路径三种写死风格、符号 15 处字符类互相矛盾。C0a-C0d 落地后：`config.py`（34 部书自动发现+指纹）、`symbols.py`（15 实体+6 域+围栏 10 类，全脚本 import）、`masker.py`、`wordlist_compiler.py`——可读性从"每脚本各自为政"变为"单一来源"。（docs/17 §2.1、docs/19 §1.2）

### 正例 2 · 解析单一来源
loader 回级作用域只在 `accept_batch.py` 实现（`_chapter_set/_item_scope/_pairs_from_items/…`），`qa_annotation_report.py`/`annotate_chapter_llm.py` 延迟 import 复用，旧 API 保留兼容包装——避免三处解析逻辑漂移。（docs/56 §一）

### 正例 3 · 一行修复的可读性
`lint_text_integrity.py` 无章号时 `glob(struct)+glob(tagged)` 同一回计两次（江湖 48→96 回、174.7s）；`nos = sorted({...})` 一行去重后 87.0s——**可读性问题的修复常是一行，但发现需要可观测指标**。（docs/57 §二）

### 正例 4 · 导出层公共设施
`export_site_common.py` 统一契约快照/差异比对/staging/备份/`load_baseline`，8 个导出器只写业务映射——新增导出器成本从"复制一套设施"降为"一个函数"。（docs/51 §三、docs/52 §一）

### 反例 1 · SKILL 超长
`SKILL_03b_人名消歧_武侠版.md` 716 行，lint PASS 90/100（唯一 warning 为总长超标）——超长不阻塞但降低可读性，后续拆分候选（附录/案例外置）。（skills/README）

### 反例 2 · 登记滞后与口径不一
docs/57 §八 遗留"skills/README 需补登 10 份 SKILL"；docs/58 §九 遗留"scripts/README 需补登"；SKU 卡数 docs/58 记 1,536、scripts/README 记 1,457（时点/口径差）——**登记与数字是同一可读性问题**：引用前必须统一时点与口径。

## 七、工具与脚本

| 工具 | 用途 |
|---|---|
| `scripts/lint_skills.py` | SKILL 结构/可读性门（PASS ≥90） |
| `scripts/config.py` | 路径唯一来源（规模统计入口） |
| `scripts/symbols.py` | 符号语义表（15+6，可读性核心） |
| `scripts/wordlist_compiler.py` | 词表双轨编译（数据/代码分离） |
| `scripts/export_site_common.py` | 导出公共设施（契约/差异/备份） |

## 八、成功标准

1. 新增脚本/SKILL 一次评审通过率 ≥90%；
2. `lint_skills.py` 新 SKILL 100/100（存量至少 PASS 90）；
3. 命名/分层违规 0（评审返工项计 0 遗留）；
4. 登记同步率 100%（产物 24h 内进 README）；
5. 规模统计每次引用带时点与口径。

## 附录 A · 命名前缀速查

```
L0: config symbols masker wordlist_compiler
L1: lint_* tag_* extract_* compute_* find_* compare_* apply_* fix_* infer_* scan_*
L2: generate_* detect_* validate_* time_resolver_* relation_validator merge_* gazetteer_migrate lint_consistency lint_taxonomy build_sku_cards update_intertext_loc
L3: accept_batch qa_annotation_report finalize_judgment
L4: export_site_*  (all/common/books_chapters/characters/dossiers/sects_weapons_arts/graph/gazetteer_universe/audit)
一次性: _oneshot/*
```

## 附录 B · 目录与产物约定

| 路径 | 用途 |
|---|---|
| `scripts/` | 全部管线脚本（新脚本落此，词表数据落 `wordlists/`） |
| `skills/` | SKILL/META 主文件（文件名不含版本号，存档在 `backup/skills/`） |
| `references/` | 规律库/参考件（03c1 等，8 字段 schema） |
| `registry/` | 登记/验收/派生产物（acceptance/entities/time/relations/…） |
| `tagged/` `struct/` | 标注产物与结构层（只由管线写） |
| `logs/` | qa/annotate/export/<domain>/ 报告与证据 |
| `backup/` `logs/backup/` | 写操作前备份（可回滚） |

## 附录 C · 来源对照

| 来源 | 用途 |
|---|---|
| docs/04 §2.12 | M07 改造要求（符号表/分类树/错误消息） |
| docs/17 §2.1 | 地基四模块与历史债 |
| docs/42、docs/50 | 规模审计与剩余清单（45 脚本/25 主文件基线） |
| docs/56、docs/57、docs/58 | 规模演化（60/66/69 脚本）、登记遗留、口径差 |
| scripts/README、skills/README | 登记与约定（命名/路径/编码/密钥） |
| `scripts/lint_skills.py` | 可读性检查的代码化 |
