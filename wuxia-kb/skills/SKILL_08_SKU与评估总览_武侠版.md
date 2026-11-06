---
name: skill-08-wuxia
title: SKU 与评估总览（武侠版）——卡片生成、覆盖、成本、正确性、置信的 08 组地图
description: SKU 卡与评估层（08 组）技能总览：08a SKU 字段、08b 覆盖度、08c 成本管控、08d 正确性评估、08e 表格反思、08f 置信度函数（规划）；现役产物 registry/sku/cards.json（1,501 张：person 342/faction 60/art 852/artifact 226/manual 21）由 N10 build_sku_cards 生成。当需要确定评估/卡片区某道工序的承载件、或读 SKU 数据口径时使用。
version: v0.1-draft
last_updated: 2026-11-06
---

# SKILL 08：SKU 与评估总览（武侠版）

> **上游声明**：本文为 08 组导航总览（骨架参考 shiji-kb 的 SKILL_08_知识库管驭，内容按 `wuxia-kb/skills/` 现役 08 组件重写；机制类总览）。

> **一条主线**：tagged/registry 数据 →（N10 build_sku_cards 五类卡）→ registry/sku/cards.json →（08b 覆盖 / 08d 正确性 / 08e 表格反思循环）→ W8 精品页 / EX 导出。08c 管成本，08f 规划置信函数。

---

## 一、快速开始（三步）

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
# 看卡片账本（1,501 张：person 342 / faction 60 / art 852 / artifact 226 / manual 21，docs/66）
python -X utf8 -c "import json;d=json.load(open('registry/sku/cards.json',encoding='utf-8'));print(d['meta'])"
# 生成/刷新 SKU 卡（N10，最下游）
python -X utf8 scripts/build_sku_cards.py
# 覆盖/正确性两镜
#   覆盖 → SKILL_08b（五维覆盖+10 组问题体系）；正确性 → SKILL_08d
```

---

## 二、08 组件分工表

| 件 | 文件 | 一句话分工 | 关键接口 |
|---|---|---|---|
| 08a | `SKILL_08a_SKU字段_武侠版.md` | 五类卡字段规范（person/faction/art/artifact/manual） | cards.json schema |
| 08b | `SKILL_08b_覆盖度评估_武侠版.md` | 五维覆盖+10 组问题体系（W13 式全文覆盖） | concordance / N9 / 词表 |
| 08c | `SKILL_08c_成本管控与Token节约_武侠版.md` | token 账本与成本策略 | token_tracker / .token_cost_config.json |
| 08d | `SKILL_08d_正确性评估_武侠版.md` | 卡片内容正确性评估 | registry + N8 报告 |
| 08e | `SKILL_08e_表格反思迭代_武侠版.md` | 表格类数据的反思迭代循环（G12 表格定义拍板后扩展） | docs/11 跨书治理 |
| 08f | `SKILL_08f_置信度函数设计_武侠版.md` | 置信度函数设计（规划；现役=registry 两态+07e） | propose/apply_entity_registration |
| N10 | `scripts/build_sku_cards.py` | 五类卡生成器（最下游，1,501 张实测） | registry/sku/cards.json |

## 三、数据口径纪律

- **cards.json 是唯一卡片真源**；W8 精品页/EX 导出消费它，不另建卡片层；
- 卡片字段以 08a 为准；字段填充率（field_fill）是 08b 覆盖评估的输入之一；
- 正确性问题（08d）走"评估→反思→登记层修正"链（patches 裁定），不直改卡片；
- 成本口径见 08c：`.api_config.json` / `.token_cost_config.json` 敏感件不进提交清单。

## 工具与脚本

本总览无专属脚本；组内件的脚本入口见各件"工具与脚本"节；全链阶段对照见 `SKILL_00_管线总览_武侠版.md`。

## 检查清单

- [ ] 找到的工序确属 SKU/评估层（知识抽取归 03-07 组）
- [ ] 卡片变更走 N10 再生成（不手改 cards.json 后不重生）
- [ ] 评估结论有 registry/N8 书证；置信表述区分两态与评级档
- [ ] lint_skills PASS（score ≥ 90）

## 成功标准

- 08 组工序一件一位；卡片从生成到展示全链可追溯
- 1,501 张卡的数字口径与 docs/66 终版一致（变动时同步）
- lint_skills PASS（score ≥ 90），无 error
