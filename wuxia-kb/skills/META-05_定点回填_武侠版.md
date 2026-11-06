---
name: meta-05-wuxia
title: META-05 定点回填（武侠版）——从缺口清单到最小改动的闭环流程
description: 针对全库扫描/验收/反思已产出的缺口清单（judgment 终签、围栏漂移、类型个例、书名行、registry 个例、管道回填等），按"清单定位→最小改动→回归→记录"的定点回填流程完成小批量落盘，避免全库重写。实测批次见 docs/52（EX dry-run/apply）、docs/53（13 token/5 文件）、docs/54（75 token/41 文件）、docs/56（registry 校准 10 token/5 文件、loader 回级 A/B）。
version: 0.1-draft
last_updated: 2026-11-05
---

# META-05 定点回填（武侠版）——从缺口清单到最小改动的闭环流程

> **定位**：定点回填（targeted backfill）是"全库扫描已经告诉你哪里有问题"之后的**最小落盘工序**，不是重新设计标注/重写规则。本文给出清单→分类→最小改动集→备份/断言→dry-run→apply→回归→记录的完整闭环，并以 docs/52/53/54/56 的实测批次校准规模与验收口径。
>
> **边界**：本文只处理**已入清单、可定位到 token/文件级**的缺口；规则变更、类型体系调整、全库重标、跨书归并分别归 S-03a/03e/03f、03b、N6 等轴，不在此文越层处理（03c §1.3 纪律）。

## 一、适用场景与不适用

| 场景 | 典型表现 | 本文动作 |
|---|---|---|
| judgment 终签落地 | acceptance `judgment_items` 已分类为 应摘/改域/保留/需人工 | 按 verdict 取应摘/改域的最小 edit 集，dry-run→apply→回归 |
| 围栏漂移治理 | struct 重生成后 tagged 围栏与检测树不一致、栏内令牌需剥/留 | 回灌+栏内令牌定点处置（docs/54 白发/七剑：剥 6 留 2） |
| 类型/符号个例 | 少量 `&/◆/◎→~`、`#X族人→裸文` 等类型修正 | 按规则表批量定点替换（docs/53 13 token/5 文件） |
| 书名行/结构个例 | 部分书 000/001 回首行残留书名 | 定点删除+紧随空行（docs/53 8 部） |
| registry/别名个例 | canonical/alias 合并、纯衔移出、歧义面清退 | 定点 registry 校准（docs/56 454→452，10 token/5 文件） |
| 管道/显示串回填 | mapping 快照 typo、display 与 canonical 错位 | 修 mapping/registry 后复跑 accept（不直接改 tagged 正文） |

**不适用（须转轴）**：规则条款变更→S-03a/04f；类型体系重设计→S-03e；边界系统性问题→S-03f；跨书归并/canonical policy→S-03b；全库重标或重生成→N1/N2、02ab 流程；正文/情节修订→作者层（本 KB 不改正文）。

## 二、快速开始

1. **取缺口清单（唯一分母）**：从 acceptance JSON 的 `judgment_items`、`logs/qa/judgment_signoff_*.json`、`qa_structure_A_B_*.md`、`logs/consistency/<书>.md`、五门 lint 报告、人工 review 包中汇总；每条必须有 `书/回[段]/行号/显示串/原 token span/规则或依据/建议处置`，无 loc 不入清单。
2. **分三类处置**：机械可改（应摘/改域/类型替换/书名行删除）、语义待裁（需人工终签）、不修（保留/工具误报/正文问题）。先小样本 dry-run 验证规则命中。
3. **生成最小改动集**：只收清单内 token；edit 记录到 `(书, 回, 段, 行号, raw_start, raw_end, display, from, to, rule)`，同段多 edit 按 span 逆序；白名单外的书/回一律 SKIP（如 docs/54：七剑/白发维持既有终签）。
4. **备份 + 基线**：落盘前全量备份目标文件（含 sha256/文件数），记录 acceptance/lint 基线；准备"strip(新)==strip(旧)"逐文件断言脚本与令牌多重集核对。
5. **dry-run**：先跑工具默认 dry-run（`scripts/finalize_judgment.py --all`、`scripts/fix_annotation_mechanical.py --chapters ... --dry-run`、`scripts/repair_corpus_titleline.py` 默认 dry-run），核对清单命中数=预期数，异常数归零再继续。
6. **apply + 落盘断言**：仅对白名单执行 `--apply`；落盘后立即跑：剥标=底本、行数不变、令牌数/多重集按预期增减、备份原件+edit 回放逐字节复核；再跑一次 apply 验证**幂等 0 变更**（docs/54 二次 apply 0 变更）。
7. **回归**：`scripts/pipeline_wuxia.py <书> check` 五门 lint 全 0；`scripts/accept_batch.py` 按原范围复跑（hard 0、pipe_unsourced 不升、judgment 不升）；必要时重生成 concordance 并核对 E/V/R 变化与 edit 集一致。
8. **记录**：写批次 docs（如 docs/54 §一、docs/53 §一/三/四）＋报告（清单、edit 集、前后对照、回归证据、备份与回滚命令）；1 个 token 也要能回到 loc/规则/裁定证据。

## 三、工具与脚本

| 工具/脚本 | 用途 | 关键参数/默认 |
|---|---|---|
| `scripts/finalize_judgment.py` | judgment 终签分类与 `--apply`（备份/剥标/改域/断言/幂等） | 默认 dry-run；`--apply` 仅 3 书白名单；输出 `logs/qa/judgment_apply_*` |
| `scripts/fix_annotation_mechanical.py` | 管道归一/闭括号/非法令牌/标点外置的机械修复 | `--chapters` 必填；`--dry-run` 先跑；落盘走修复器 |
| `scripts/apply_annotation_patches.py` | 补丁式 token 级替换（按 loc/span） | 先 dry-run；备份+断言后 apply |
| `scripts/repair_corpus_titleline.py` | 底本书名行清理（结构个例） | 默认 dry-run；`--apply` 备份后落盘；写后断言 |
| `scripts/pipeline_wuxia.py` | 五门 lint/结构/验收等阶段编排 | `<书> check` 为回归门；失败即停 |
| `scripts/accept_batch.py` | 批次验收与 10% 抽样（seed 固定） | 复跑原范围，对比 hard/judgment/unsourced |
| `scripts/qa_annotation_report.py` | 结构/管道 A-B 复核 | 与 accept 同源 loader，复跑对比 |
| `scripts/build_entity_concordance.py` | concordance 重生成 | 与 edit 集核对 E/V/R 增减 |
| `scripts/lint_symbol_conflicts.py` | 符号/边界 lint | 落盘后回归必跑 |

> 纪律：写操作工具默认 dry-run，`--apply` 为显式动作；不改 tagged 正文，只动令牌标记；落盘前必须有备份与剥标断言，落盘后必须回归与幂等复核。

## 四、检查清单

**清单与改动集**
- [ ] 每条缺口有 `书/回[段]/行号/显示串/token span/依据/建议`，无 loc 不入清单
- [ ] 处置分为机械/语义/不修三类，语义项有人工终签责任人与依据
- [ ] 最小改动集只含清单内 token，白名单书/回明确，同段多 edit 按 span 逆序
- [ ] 预计变更数（应摘/改域/剥/留）与工具 dry-run 命中数一致

**备份与落盘**
- [ ] 目标文件全量备份 + sha256/文件数基线已记录
- [ ] dry-run 跑通，异常/未命中项逐条解释
- [ ] `--apply` 仅对授权白名单；落盘断言（strip 相等、行数不变、令牌多重集可解释）通过
- [ ] 二次 apply 为 0 变更（幂等）；备份原件+edit 回放逐字节复核通过

**回归与记录**
- [ ] 五门 lint 全 0；accept hard=0、pipe_unsourced 不升、judgment 不升
- [ ] concordance（若重生成）E/V/R 变化与 edit 集一致，无"凭空增减"
- [ ] 报告含前后对照、证据路径、回滚命令、快照版本；docs 批次记录已更新
- [ ] 残留项（人工/待裁/工具误报）已列下一批，不混入本批"已完成"

## 五、成功标准

- **命中率**：清单内可机械项 ≥95% 在当批落盘；未落盘项逐条注明"人工/待裁/证据不足/工具缺陷"，不静默丢弃。
- **零误改**：全部目标文件 `strip(新)==strip(旧)`；行数与令牌多重集变化可用 edit 集逐条解释；正文零增删改。
- **回归绿**：五门 lint 全 0；accept `hard=0`、`pipe_unsourced` 不升、`judgment` 不升；必要重生成后仍绿。
- **幂等**：二次 apply 输出 0 变更；dry-run 复跑差异仅 `generated` 时间戳（docs/52 staging 哈希幂等）。
- **规模可参照**：单批 10-100 token/5-45 文件为常态（docs/53：13 token/5 文件；docs/54：75 token/41 文件；docs/56：10 token/5 文件；docs/52：8 个导出文件 hard_gap=0）；超过 200 token 或跨 5 书需拆批。
- **可回滚**：任一批次回滚 ≤10 分钟，备份/恢复命令在报告内可直接执行。
- **可追溯**：每个 token 能回指 loc、规则/裁定编号、批次 docs、证据 JSON。

## 六、错误模式（定点回填专有）

| 编号 | 现象 | 处理 |
|---|---|---|
| M05-E1 | 借"回填"做全库重写/重标 | 退回清单制：只收清单内 token，其余转系统轴 |
| M05-E2 | 凭记忆/只看首个同名 token 定位 | 按 `(回,段,行号,span,display)` 精确定位（docs/54 §1.1 教训） |
| M05-E3 | 无备份直接 apply，误改无法回滚 | 备份先行；落盘前 sha256/文件数基线；报告写回滚命令 |
| M05-E4 | 只 apply 不回归，下批复发 | 强制五门 lint+accept+concordance 回归；复发记 03c1 |
| M05-E5 | 剥标断言只抽检，漏掉正文误删 | 逐文件/逐行 strip 相等 + 行数/令牌多重集全量断言 |
| M05-E6 | 语义项（计划/既成、实指/泛指）被机械规则误摘 | 语义项必须人工终签；机械规则只处理可判定项（docs/54 人工 7 条） |
| M05-E7 | 工具默认 apply 导致误落盘 | 写操作默认 dry-run、`--apply` 显式；CI 禁默认 apply |
| M05-E8 | 幂等未验，重复批次叠加改坏 | 二次 apply 0 变更；acceptance 快照+状态机分流（docs/54） |

## 七、反思挂钩

- 回填完成后按 S-03c 六问复盘：为什么产生缺口？归因 R/W/S/F/G；系统级（≥3）写 `references/03c1_反思规律库_武侠版.md` 候选，个案只记录。
- 回填批次报告进 docs/52-56 类批次记录；每批更新"残留项→下一批清单"，禁止把待裁项写成已完成。
- 与 03e/03f/03b 分工：类型/边界/管道问题分别回写对应轴；定点回填只提供证据与规模，不自行改规范。
- 回填工具自身缺陷（误定位、断言漏洞、幂等 bug）归 G 源，登记后修工具，不得用人工绕过长期掩盖。

## 八、实测回填批次（docs/52/53/54/56）

| 批次/文档 | 范围 | 规模 | 验证结果 | 证据 |
|---|---|---|---|---|
| docs/52 EX 导出层阶段 0-1 | 8 个 data 导出（dry-run/apply） | 8 文件；contracts 19 schema；备份 23 文件 | hard_gap=0；staging 复跑哈希一致；站点构建 exit 0；回滚可用 | `logs/export/contracts/`、`logs/export/reports/`、`backup/site_data/phase0_20261105/` |
| docs/53 半日收尾（B1-3 类型） | `&/◆/◎罗布族`→`~`、`#罗布族人`剥标 | 13 token / 5 文件 / 3 书 | 残留 0；五门 lint 3 书 0；accept 30/28/13、hard 0、unsourced 0 | `backup/tagged/ethnicity-fix-20261105/` |
| docs/53 书名行/围栏 | 8 部书名行删除；塞外/冰魄围栏 | 8 部；塞外 1→6、冰魄 0→2 | 结构/PN 回归；回灌剥标 0 失败；accept 28/12 | `backup/corpus_titleline_20261105/`、`logs/qa/fence_fix_*.md` |
| docs/54 judgment 落地 | 3 书 judgment 机械处置 | 75 token / 41 文件 | judgment 208→131；残留应摘/改域=0；二次 apply 0 变更；五门 0 | `logs/qa/judgment_apply_*`、`backup/tagged/judgment-apply-20261105/` |
| docs/54 围栏漂移 | 白发/七剑重生成+栏内令牌 | 白发 64→67；七剑 29→54；剥 6 留 2 | 令牌多重集 0 失败；accept 13/30；PN 可解释 | `logs/qa/fence_drift_final_verify.md`、`logs/backup/fence_drift_20261105/` |
| docs/56 registry 校准 | canonical/alias/纯衔/歧义面 | 454→452；10 token / 5 文件 | 3 书 accept 全绿；warnings 170→167；五门 0 | `logs/qa/task12_backup_20261105_150508/` |

> 说明：docs/53 的 336 条 judgment dry-run 是"清单阶段"（未落盘），docs/54 的 75 token 是"落盘阶段"；两批合看即"先清单后回填"的完整样例。

## 附录 A：最小改动集 schema（建议）

```json
{
  "batch": "2026-11-05_judgment_apply",
  "scope": {"books": ["江湖三女侠"], "chapters": "1-48", "whitelist_only": true},
  "backup": {"root": "backup/tagged/judgment-apply-20261105/", "sha256_manifest": "..."},
  "edits": [
    {
      "book": "江湖三女侠", "chapter": 12, "pn": 22, "line_no": 41,
      "raw_start": 128, "raw_end": 140, "display": "示例",
      "raw_before": "⟦∅示例⟧", "raw_after": "示例",
      "rule_id": "R-N1", "verdict": "应摘",
      "evidence": "logs/qa/judgment_signoff_江湖三女侠.json#L120"
    }
  ],
  "assertions": {"strip_equal": true, "line_count_equal": true, "token_multiset": "+0/-1"}
}
```

## 附录 B：回填报告必填项（模板）

1. 批次/触发来源/清单分母；2. 处置分类表（应摘/改域/剥/留/人工）；3. 最小改动集统计（token/文件/书）；4. 备份与基线（路径、sha256/文件数）；5. dry-run→apply→幂等证据；6. 回归结果（五门 lint/accept/concordance）；7. 前后对照（judgment/E/V/R 变化与解释）；8. 回滚命令；9. 残留与下一批；10. 快照版本（tagged/acceptance/generated_at）。
