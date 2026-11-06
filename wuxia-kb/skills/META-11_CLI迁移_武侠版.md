---
name: meta-11-wuxia
title: META-11 CLI 迁移（武侠版）——脚本契约统一与 loader 回级迁移
description: 面向 wuxia-kb 现仓 75 个 Python 脚本的 CLI 契约迁移方法：参数命名、dry-run 默认、输出与退出码、幂等、只读边界、--strict/--selftest 自检，以及 docs/56 的 loader 回级（scoped mapping）迁移。给出可复用的契约矩阵、迁移步骤、回归验收与错误模式。
version: 0.1-draft
last_updated: 2026-11-05
---

# META-11 CLI 迁移（武侠版）——脚本契约统一与 loader 回级迁移

> **定位**：当新工具进入管线、旧脚本被移植/合并、或 loader 语义变更（如 docs/56 §一 的 mapping 回级作用域）时，按**统一 CLI 契约**完成迁移：参数/默认值/输出/退出码/幂等/只读/自检/文档八项一次对齐，并以 A/B 回归证明"旧行为逐字节不变"。
>
> **现状基线（2026-11-05）**：`scripts/` 目录下 `*.py` 共 **75** 个；`argparse` 55、含 `--dry-run`/dry_run 18、含 `--apply` 24、`--strict` 12、`--selftest` 15、`--book` 47、`--chapter` 25、`--out` 22、`sys.exit` 48、`def main` 68。迁移是把"多数一致"收敛成"全部可预期"，不是重写业务逻辑。

## 一、CLI 契约八件套（迁移目标）

| 契约项 | 规范（本仓既有惯例） | 现仓样例 |
|---|---|---|
| 参数命名 | 长选项 `--book/--all/--chapter/--type/--rule/--strict/--selftest/--quiet/--out/--report-dir/--seed`；范围类互斥（`--book` vs `--all`）；位置参数仅编排器 `<书名> <阶段>` | `scripts/finalize_judgment.py`、`scripts/build_sku_cards.py`、`scripts/lint_consistency.py` |
| 默认值 | **写操作默认 dry-run**；破坏性动作必须显式 `--apply`；`--strict` 为显式严格门；`--quiet` 可关摘要 | `scripts/finalize_judgment.py`（默认 dry-run）、`scripts/repair_corpus_titleline.py`（默认 dry-run）、`scripts/export_site_all.py`（默认 dry-run，`--apply`/`--check-only`） |
| 输出 | stdout 打人读摘要（`[OK]/[ERROR]/[STRICT]`），唯一结果落文件（JSON/MD，路径可由 `--out/--report-dir` 覆写）；stdout 不作为下游唯一数据源 | `scripts/build_sku_cards.py`（`registry/sku/cards.json` + `logs/sku/`）、`scripts/accept_batch.py` |
| 退出码 | `0` 成功；`2` 用法/严格校验/断言失败（argparse 约定 + `--strict`）；`1` 运行期异常；**失败不得 0**；子进程退出码原样传播 | `scripts/lint_consistency.py`、`scripts/build_sku_cards.py`（strict → 2）、`scripts/pipeline_wuxia.py`（子进程 exit 传播） |
| 幂等 | 同输入复跑同输出（仅 `generated` 时间戳可变）；apply 二次 0 变更；staging 哈希一致 | docs/52 staging 幂等；docs/54 judgment 二次 apply 0 变更（`judgment_apply_idempotency.json`） |
| 只读边界 | 输入 tagged/registry/kb/site 只读；写路径显式且限定在 logs/registry/backup；不静默写输入目录 | docs/52 "零旧写入"；本仓工具统一 `Path` 只读输入 + 报告输出 |
| 自检/严格 | 每个工具至少提供 `--selftest`（单元断言）或 `--strict`（输出断言）；文档给出复现命令 | `scripts/time_resolver_wuxia.py --selftest`、`scripts/relation_validator.py --strict`、`scripts/lint_skills.py --strict` |
| 文档/版本 | `--help` 含用途/参数/示例；脚本头注 `version/改动`；批次 docs 记录兼容性 | `scripts/pipeline_wuxia.py` 阶段清单、各脚本 argparse epilog |

## 二、快速开始

1. **盘点存量 CLI**：`grep`/脚本扫描统计 `argparse`、`--dry-run`、`--apply`、`--strict`、`--selftest`、`--book/--chapter/--out` 占比（本仓基线见文首）；列出"默认会写盘/退出码不统一/无自检"的脚本清单。
2. **定契约矩阵**：为目标脚本填八件套（参数/默认/输出/退出码/幂等/只读/自检/文档）；范围类参数必须互斥，写操作默认 dry-run。
3. **选迁移方式**：能兼容就保留旧 API 包装（如 docs/56 loader 回级的 `load_frozen_mapping/load_registry_names` 兼容包装）；破坏性改名必须一次性批量改调用点并留 A/B 证据。
4. **实现与自检**：argparse 定义 + `--selftest`（纯函数/契约断言）+ `--strict`（输出断言）；Windows 下固定 `-X utf8`/`sys.stdout.reconfigure(encoding='utf-8')`，避免 GBK 编码异常打断子进程。
5. **管线集成**：在 `scripts/pipeline_wuxia.py` 的 `MECHANICAL_STAGES`/`build_command` 增加阶段分支，保证 `python -X utf8 scripts/pipeline_wuxia.py <书> <stage>` 可直接跑、失败即停、退出码传播。
6. **A/B 回归**：同一数据快照下"旧实现 vs 新实现"输出逐字节/逐字段对比；loader 类迁移要求 summary 16 字段 + 逐章 chapters_data 0 差异（docs/56 §1.2）。
7. **记录与发布**：更新 `scripts/README`、批次 docs（如 docs/56 §一）、报告；标注"兼容/破坏性/待修"三类，给回滚方式。

## 三、工具与脚本

| 工具/脚本 | 迁移用途 | 契约要点 |
|---|---|---|
| `scripts/pipeline_wuxia.py` | 阶段编排/子进程退出码传播 | `<书> <stage> [--chapter]`；stage 命令集中在 `build_command`，子进程失败即停 |
| `scripts/accept_batch.py` | loader 回级单一来源（MappingSnapshot/RegistryNames） | `--book/--chapters/--seed/--mapping-file/--registry`；回级查找只在实现内，其他脚本延迟 import 复用 |
| `scripts/qa_annotation_report.py` | 结构/管道 A-B 复核（复用 loader） | 与 accept 同源 loader；回级生效后报告逐字节一致（docs/56） |
| `scripts/annotate_chapter_llm.py` | 标注侧 loader 兼容包装 | 旧 `load_mapping_table` API 保留，回级由 accept 单一来源提供 |
| `scripts/finalize_judgment.py` | 写操作默认 dry-run + `--apply` 范式 | `--book/--all/--apply/--dry-run/--out-dir`；apply 白名单+备份+断言+幂等 |
| `scripts/export_site_all.py` | dry-run/`--apply`/`--check-only` 集成器范式 | 默认 dry-run；apply 先备份；集成报告 `logs/export/reports/_integration.md` |
| `scripts/time_resolver_wuxia.py` | 新工具契约样板 | `--book/--all/--chapter/--report/--strict/--selftest/--quiet`；strict 失败 exit 2 |
| `scripts/build_sku_cards.py` | 过滤/子集/输出路径样板 | `--all/--book/--type/--strict/--selftest/--out/--report-dir/--quiet` |
| `scripts/lint_skills.py` | 文档类工具契约 | 文件参数/`--all`/`--strict`；单文件与批量一致 |

> 纪律：loader/映射/registry 解析**只允许一处实现**，其他脚本延迟 import；新增 CLI 参数必须同时出现在 `--help`、epilog 示例与批次 docs，禁止"隐藏参数"。

## 四、loader 回级迁移（docs/56 §一 专项）

**背景**：S-03b v1.0 前需要"同一显示串在不同回指向不同 canonical"的映射能力（通称/歧义面），旧 loader 是全局单值，docs/56 以**条目级可选作用域**实现回级而不破坏旧语义。

**契约（照 docs/56 §1.1）**
- 映射快照条目可含：`{"display","canonical","chapter":22}` / `"chapters":[23,24]` / `"scope":"book"|{"chapter":30}`，可选 `book/books`；**无字段=全局**（旧语义逐字节不变）。
- registry 记录级 `context_notes`（或 aliases/contextual 中 dict 条目）按回生效；旧字符串别名不变。
- 查找顺序：`(书,回,显示串) → (书,显示串) → 全局`；回级仅覆盖同显示串，其余回走全局（不跨回污染）。
- 单一来源：解析只在 `accept_batch.py` 实现（`MappingSnapshot`/`RegistryNames`、`_chapter_set/_item_scope/_pairs_from_items/_add_scope_notes`）；`scripts/qa_annotation_report.py`/`scripts/annotate_chapter_llm.py` 延迟 import 复用；旧 API `load_frozen_mapping/load_registry_names` 保留为兼容包装。

**回级条目示例**

```json
[
  {"display": "飞红巾", "canonical": "哈玛雅", "book": "塞外奇侠传"},
  {"display": "皇帝", "canonical": "玄烨", "chapters": [22, 23]},
  {"display": "李公子", "canonical": "李思永", "scope": {"chapter": 30}}
]
```

**A/B 验收（docs/56 §1.2）**：accept 5 书 summary 16 字段 + 逐章 chapters_data 逐项一致 0 差异（13/48/30/28/12、hard 0、unsourced 0、judgment 27/97/105/18/16 全不变）；qa 5 书报告 sha256 相同；旧 API 与 annotate 全量输出 `TOTAL_DIFFS 0`；回级样例 CLI 级 global→scoped 使 `pipe_unsourced` 1→0 并出现 `mapping_source.scoped`；合成书 e2e 10/10、单元 26/26。

**限制与性能（照 docs/56 §1.3/§七）**：回级条目仅在传入 chapter 时生效；annotate 的"已过审 tagged 管道"仍全局收集；registry 记录暂未加 book 字段；空闲期 A/B 江湖 1-48 162.0s vs 163.4s（1.009x）无 loader 回归——高负载期 7.5 分钟系同机 site build/N4/N5/多代理争用（改前脚本同样 6m55s）；真实热点是 `lint_text_integrity --book X` 无章节号时重复计 struct+tagged（江湖 48→96 回，153.7s），去重后预计全局门 ~77s（`logs/qa/loader_perf_report.md`）。

## 五、检查清单

**迁移前**
- [ ] 目标脚本八件套矩阵已填；哪些参数/默认/输出/退出码将变、哪些兼容，逐项写明
- [ ] 破坏性改名/默认值变更的调用点已全量检索（pipeline/README/docs/其他脚本）
- [ ] loader/registry 类变更确认"单一来源"，其他脚本仅延迟 import，不复制解析逻辑
- [ ] 基线快照（旧实现输出/退出码/耗时）已保存，供 A/B 对比

**实现与自检**
- [ ] argparse 参数互斥正确；写操作默认 dry-run，`--apply` 显式
- [ ] 退出码：0 成功/1 异常/2 用法或 strict 失败；子进程退出码原样传播
- [ ] `--help` 有用途/参数/示例；`--selftest` 覆盖纯函数与契约断言；`--strict` 覆盖输出断言
- [ ] Windows 编码固定（`-X utf8`/stdout reconfigure），printf 不含未编码字符导致子进程崩溃
- [ ] 输出文件路径可由 `--out/--report-dir` 覆写；默认路径不落在只读输入目录

**集成与回归**
- [ ] pipeline stage 分支已加并实测 exit 0；失败即停、错误可复现
- [ ] A/B：同快照旧/新输出 0 差异（loader：summary 16 字段+chapters_data；qa：sha256）
- [ ] 幂等：二次执行 0 变更；staging/apply 哈希或 JSON 等价
- [ ] 性能：关键书/批次耗时与基线比 ≤1.2x；异常热点有记录与修复计划
- [ ] README/docs/批次记录已更新；兼容包装与弃用期限写明

## 六、成功标准

- **契约一致**：目标脚本八件套全部落位；同族脚本参数命名/退出码/默认行为一致（如写操作默认 dry-run）。
- **行为不变**：兼容类迁移 A/B 输出 0 差异（逐字节或逐字段），退出码一致；无法 0 差异的项逐条列出原因与批准人。
- **可自检**：`--selftest` 全过；`--strict` 对坏输出返回 2；`--help` 可直接复制运行。
- **幂等可证**：二次执行 0 变更；apply 类工具有备份+断言+回滚命令（docs/54 幂等样例）。
- **管线可跑**：新增/迁移阶段在 `scripts/pipeline_wuxia.py` 实测 exit 0；失败时错误信息指向具体文件/参数。
- **性能达标**：loader 类 A/B 1.0x 量级；单书 accept 空闲期 ≤90s（docs/56 目标）；超 1.2x 需报告热点与修复计划。
- **文档闭环**：README/批次 docs/证据 JSON 三件齐；弃用 API 有期限与替代路径。

## 七、错误模式（CLI 迁移专有）

| 编号 | 现象 | 处理 |
|---|---|---|
| M11-E1 | 参数命名漂移（同义参数多种拼写/位置参数混用） | 以契约矩阵统一；别名保留一个弃用周期；README 列清单 |
| M11-E2 | 写操作默认 apply，误落盘 | 默认 dry-run，`--apply` 显式；CI 禁默认 apply（docs/54 范式） |
| M11-E3 | 失败仍 exit 0 / 子进程失败被吞 | 失败非 0；子进程退出码传播；pipeline 失败即停 |
| M11-E4 | stdout 唯一输出被下游当数据源 | 唯一结果落文件；stdout 只打摘要；JSON/MD 路径可覆写 |
| M11-E5 | loader 解析多源复制，回级后行为不一致 | 单一来源（accept_batch）+ 惰性 import；A/B 0 差异验收 |
| M11-E6 | dry-run 与 apply 掩码语义不一致（围栏/标题被写） | 统一 masked 区间；默认禁 apply，走修复器（03c1 F06） |
| M11-E7 | Windows 控制台 GBK 编码打断子进程 | 固定 `-X utf8`/stdout reconfigure；子进程同样处理 |
| M11-E8 | 性能回归被误判为代码问题 | A/B 同负载对比（docs/56：高负载 7.5min 系争用，非 loader）；记录真实热点 |
| M11-E9 | 兼容包装无限期保留，双实现漂移 | 写弃用期限与替代 API；批次 docs 记录删除计划 |

## 八、反思挂钩

- CLI 迁移缺陷按 S-03c 归因：契约类→R/S（规则/种子），编码/路径/退出码→G（工程），loader 语义→B（跨书管道）；系统级（≥3 脚本同病）写 `references/03c1_反思规律库_武侠版.md` 候选。
- 每批迁移更新 `docs/56` 类批次记录与 `scripts/README`；性能异常按 `logs/qa/loader_perf_report.md` 口径复核，不把并发争用当代码回归。
- 与 03b/03f 分工：canonical/loader 语义归 03b；边界/结构类 CLI 问题归 03f；本文只维护 CLI 契约与迁移方法。

## 附录 A：75 脚本 CLI 模式统计（2026-11-05 grep 实测）

| 指标 | 命中脚本数 | 说明 |
|---|---:|---|
| `scripts/` 下 `*.py` 总数 | 75 | 迁移分母 |
| `argparse`/`ArgumentParser` | 55 | 其余多为纯库/一次性脚本 |
| `--dry-run`/`dry_run` | 18 | 写操作默认 dry-run 仍是少数，迁移重点 |
| `--apply` | 24 | 破坏性动作显式化 |
| `--strict` | 12 | 严格门（断言/校验） |
| `--selftest` | 15 | 单元/契约自检 |
| `--book` | 47 | 范围参数主命名 |
| `--chapter` | 25 | 回级/单回限定 |
| `--out` | 22 | 输出路径覆写 |
| `sys.exit` | 48 | 退出码意识已有基础 |
| `def main(` | 68 | 入口统一，便于加 `--help`/`--selftest` |

> 解读：参数命名与 `main()` 入口已较统一；差距在"默认 dry-run/退出码/自检/输出契约"，迁移应按"写操作清单"优先，而非全量重写。

## 附录 B：迁移验收命令（模板）

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
$env:PYTHONIOENCODING='utf-8'

# 1) 自检/帮助/退出码
python -X utf8 scripts/<tool>.py --help
python -X utf8 scripts/<tool>.py --selftest        # 期望 exit 0
python -X utf8 scripts/<tool>.py --strict <args>   # 坏输出期望 exit 2

# 2) dry-run/apply/幂等（写操作）
python -X utf8 scripts/<tool>.py <args>            # 默认 dry-run
python -X utf8 scripts/<tool>.py --apply <args>    # 显式落盘+备份
python -X utf8 scripts/<tool>.py --apply <args>    # 二次 0 变更

# 3) 管线 stage 集成
python -X utf8 scripts/pipeline_wuxia.py <书> <stage>
# 期望最后一行 [stage] 完成（退出码 0），失败即停

# 4) A/B 回归（loader 类）
# 旧实现产物 vs 新实现产物逐字段/逐字节比较；期望 0 差异（docs/56 §1.2）
```
