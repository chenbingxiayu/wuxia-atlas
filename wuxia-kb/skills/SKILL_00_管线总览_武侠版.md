---
name: skill-00-wuxia
title: 管线总览（武侠版）——从底本到发布包的全链路地图
description: wuxia-kb 标注管线的总览与阶段地图：机械阶段（structure/verse-scan/五门 lint/coverage/candidates/concordance/verb-validate/time-resolve）、LLM 契约阶段（annotate/review）、验收链（accept_batch → finalize_judgment）、导出层（EX-1..8 → site/data 14 契约）与发布（release_site.py）；各阶段对应脚本与 SKILL 入口。当需要确定"某道工序在管线哪个位置、由哪个脚本/SKILL 承载、上下游是什么"时使用。
version: v0.1-draft
last_updated: 2026-11-06
---

# SKILL 00：管线总览（武侠版）

> **上游声明**：本文按 `scripts/pipeline_wuxia.py` 阶段注册表与 `docs/17-技能脚本改造实现图与拓扑排序.md` 波次编写（机制类总览，非移植件）。

> **核心原则**：底本锁定只读（`章回版/`）→ 标注语料是唯一真源（`tagged/`）→ 登记层沉淀（`registry/`）→ 导出层适配展示（`site/data/` 14 契约）→ 发布一键 GO。任一阶段失败即停，可从失败阶段重跑（`pipeline_wuxia.py <书> <阶段>`）。

---

## 一、快速开始（三步）

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
# 全链阶段清单
python -X utf8 scripts/pipeline_wuxia.py
# 某书全阶段跑 / 单阶段重跑 / 批次完成门
python -X utf8 scripts/pipeline_wuxia.py 白发魔女传 structure
python -X utf8 scripts/pipeline_wuxia.py 白发魔女传 check
# 一键发布（GO 门：构建+搜索+链接检查+版权闸门）
python -X utf8 scripts/release_site.py
```

---

## 二、阶段地图（机械阶段 → LLM 契约阶段 → 验收 → 导出 → 发布）

```text
章回版/<书>/NNN.txt（锁定底本，只读）
   │ structure(N1) → tagged/<书>/NNN.struct.md
   │ verse-scan(N2) → 韵文/词牌/对联候选
   ↓
annotate【LLM 契约：SKILL_03a v1.9 SYSTEM_PROMPT，annotate_chapter_llm.py 执行】
   │   → tagged/<书>/NNN.tagged.md（15 实体 + 6 动词域，原文零增删）
   ↓
check 完成门 = lint-pn(E1-E17) → integrity(剥标对账) → symbol-lint → md-lint → fence-format
   ↓
coverage → para-structure → yunwen → candidates → concordance
   ↓
verb-validate(04f) → time-resolve(N4)
   ↓
accept_batch（语义验收：高风险全查+10% 抽样，structurally_valid → accepted）
   ↓
finalize_judgment（终签：应摘/改域/保留/人工）→ review（LLM 契约：复核）
   ↓
N5 relation_validator / N6 merge_crossover / N8 lint_consistency / N9 lint_taxonomy / N10 build_sku_cards
   ↓
EX-1..8 导出器（docs/51 方案 C）→ site/data/ 14 个 JSON 契约（Astro 38 页零改动）
   ↓
release_site.py（构建 + Pagefind 搜索 + 链接检查 + 版权闸门 → GO / 发布包）
```

### 阶段 ↔ SKILL 对照（生产入口）

| 阶段 | 脚本 | SKILL 入口 |
|---|---|---|
| structure / verse-scan / lint-pn | generate_pn_wuxia / detect_verse_wuxia / lint_purple_numbers | `SKILL_02a_02b`（结构与韵文） |
| annotate / review（LLM） | annotate_chapter_llm.py | `SKILL_03a_实体标注.md`（唯一生产提示词入口） |
| check 五门 | lint_* 五件 | `SKILL_01g`（符号规范）、03a §三完成门 |
| coverage / candidates / concordance | compute_annotation_coverage 等 | `SKILL_02e`（词法）、`SKILL_03l`（出现统计） |
| verb-validate | validate_verb_tagging_wuxia | `SKILL_04f_动词标注.md` |
| time-resolve | time_resolver_wuxia | `SKILL_时间体系_武侠版.md`（D05） |
| accept / finalize | accept_batch / finalize_judgment | 03a §三·阶段5、`SKILL_03b`（消歧语境） |
| N5/N8/N9/N10 | relation_validator 等 | `SKILL_05_关系分析总览`、`SKILL_06c`（规则）、`SKILL_08_SKU与评估总览` |
| EX 导出 / 发布 | export_site_*.py / release_site.py | `SKILL_09_应用总览`、W 组页型 |

---

## 三、多书与换书

- 书名来自 `config.books()`（`章回版/` 自动发现，现 6 书：5 部在册 + 冰川天女传在制）
- 换书标准工具（2026-11-06 正式化）：`build_legacy_mapping` / `verify_batch` / `rebuild_tagged_from_struct` / `normalize_pipe_canonicals` / `apply_judgment_a/b` / `repair_tao_tokens`（见 `scripts/README.md` 换书工具节）
- 每书验收账本：`registry/acceptance/<书>_001-0NN.json`；全库口径快照见 `docs/66`

## 检查清单

- [ ] 新工序先在本文地图上找位置（不并行造第二套编排）
- [ ] 机械阶段失败即停重跑，不跳门；check 五门全 0 才算批次完成
- [ ] LLM 阶段只认 SKILL_03a §二 SYSTEM_PROMPT（不私改提示词）
- [ ] 导出只走 EX 层（不直改 site/data）；发布只走 release_site.py
- [ ] lint_skills PASS（score ≥ 90）

## 成功标准

- 任一工序可答："我在管线哪一步、上游给什么、下游等什么、门在哪"
- 全链可复现：底本→标注→验收→导出→发布一条命令链跑通
- lint_skills PASS（score ≥ 90），无 error
