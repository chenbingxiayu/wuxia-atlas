---
name: skill-09h-wuxia
title: 数据开放（武侠版）——开放数据集、只读 API 与脱敏/许可边界
description: 武侠知识库数据开放规范：数据集清单与字段字典（SKU 1,536 卡/事件 22,978/关系 910/图 489-907/地名 619/榜单 215-161）、只读 API 设计（版本化/分页/限流/字段选择）、脱敏 R1-R5（SKU 卡脱敏规则）、版权与许可边界（原文/标注正文/连续片段禁止出口）、数据分级（open/restricted/closed）、质量声明（07e/08d）与变更日志。当需要对外提供数据集/API 或审核开放范围时使用。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 09h 武侠版：数据开放 — 开放什么、怎么开放、绝不开放什么

> **上游声明**：本件属本批 C1 应用组新划定 09h（docs/03 无直接对应；docs/05 §2.5 09 组应用工具链通用 + D12 发布/脱敏规则）。**无专属设计稿**：由 01g §9.10 发布边界、N10 SKU 脱敏 R1-R5、EX 导出契约（docs/51 §五）、07e A-E 评级、D07 证据分级综合而成（v0.1 框架）。
> **接口**：EX-1..EX-8 `../site/data/*.json`（14 契约+atlas）；N10 `registry/sku/cards.json`（含 `desensitization.rules R1-R5`、`meta.field_fill`、`validation`）；`registry/events`、`registry/relations`、`registry/consistency`、`registry/gazetteer.json`；08d 正确性/07e 评级。
> **核心原则**：**开放"结构化知识"，不开放"原文"；开放"可核数据"，不开放"未核实断言"。** 数据分级、字段脱敏、版本可追、质量可查——这是数据开放的四根柱子。

---

## 一、定位与边界

### 1.1 工序位置

```text
知识库数据层（SKU/events/relations/graph/gazetteer/consistency/audit）
        ↓
09h 数据开放（本文：分级/脱敏/API 契约/许可）→ 开放数据集 / 只读 API
        ↓
外部研究者/开发者（09i 学术工具消费）
```

### 1.2 本文做什么

1. **数据集清单与字段字典**：哪些数据、什么字段、什么版本；
2. **只读 API 设计**：REST 风格、版本化、分页、限流、字段选择；
3. **脱敏**：执行 SKU `desensitization.rules R1-R5` 与 01g §9.10；
4. **数据分级**：open（公开）/restricted（受限研究）/closed（内部）；
5. **质量声明与变更日志**：07e A-E / 08d 正确性 / 数据版本。

### 1.3 本文不做什么

| 不做 | 归属 |
|---|---|
| 改知识库数据 | 只读 |
| 版权/许可最终决策 | 项目权利审核 |
| 前端/API 服务实现 | 工程（未实现，附录 B） |
| 原文数字化/分发 | 禁止 |

### 1.4 关键约束（硬边界）

- **原文/标注正文/连续片段**不得开放（01g §9.10）；
- **未核实内容**不得以确定事实形式开放（07e D/E 级）；
- **脱敏 R1-R5** 必须执行（SKU 卡脱敏规则，见 §四）；
- **版本必填**：每个数据集/响应带 data_version + rule_version；
- **不可逆原则**：开放数据不能拼回原文（防"连续片段拼图"）。

---

## 二、快速开始（四步）

````text
Step 1 列数据集   SKU/事件/关系/图/地名/榜单/审计（§三）
Step 2 定分级     open/restricted/closed + A-E 门控 + 脱敏 R1-R5
Step 3 定接口     API/文件导出（版本/分页/限流/字段字典）
Step 4 验收       脱敏检查 + 无原文片段 + 质量声明 + 变更日志
````

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
$env:PYTHONIOENCODING='utf-8'

# 数据体检（开放前必跑；只读）
python -X utf8 -c "import json;d=json.load(open('registry/sku/cards.json',encoding='utf-8'));print(d['meta']['counts_total'],d['desensitization']['checks'][0],d['validation'])"
python -X utf8 scripts/verify_quotes.py --sku --strict
python -X utf8 scripts/export_site_all.py            # dry-run 检查契约

# 站点构建（导出契约验收）
cd ..\site; npm run build; cd ..\wuxia-kb
```

**成功标准**：① 每个数据集有字段字典+版本+分级；② 脱敏 R1-R5 零违反（原文连续重合 0）；③ API 只读、版本化、分页/限流；④ 无原文/连续片段/可拼接片段；⑤ 未核实内容不开放或标"存疑"；⑥ 变更日志与质量声明齐全。

---

## 三、数据集清单与字段字典（v0.1）

| 数据集 | 路径 | 量级 | 分级 | 核心字段 |
|---|---|---|---|---|
| SKU 卡 | `registry/sku/cards.json` | 1,536 | restricted（研究） | name/aliases/brief/confidence/publish_state/sources |
| 事件 | `registry/events/<书>.json` | 22,978 | restricted | type/participants/outcome/time_ref/loc_r |
| 关系 | `registry/relations/<书>.json` | 910 边 | restricted | subject/predicate/object/confidence/loc/evidence |
| 图 | `../site/data/graph.json` | 489 节点/907 边 | open（聚合） | id/type/n/books/kind/locs |
| 地名 | `registry/gazetteer.json` | 619 | open（已考订） | id/name/kind/real/precision/books |
| 榜单 | `../site/data/ratings.json`/`matches.json` | 161/215 | open（附口径） | player/rating/rd/matches_n/meta口径 |
| 审计 | `../site/data/audit.json` | 44 | open（脱敏） | violations 摘要/rule_coverage |
| 统计 | 08b/03l 报告 | 五维 | open | 覆盖/口径/版本 |

> 字段字典与 schema 版本随 EX 契约（docs/51 §五）保持一致；新增字段不破坏旧契约。

---

## 四、脱敏规则（执行 SKU R1-R5）

| 规则 | 内容（SKU cards.desensitization） | 开放执行 |
|---|---|---|
| R1 | 卡面正文不得与原文连续重合 ≥10 字 | 开放前逐卡检查（desensitization.checks） |
| R2 | 引文型内容一律"概括语+回锚"，回锚只存 ID/机锚指针 | 开放字段不含文本片段 |
| R3 | 专名（人名/武功/地名/书名/绰号）可发布 | 白名单 |
| R4 | 未过审不得 publish_state=approved；演示卡永远 blocked | 只开放 approved（或明确标注等级） |
| R5 | Procedural steps 源自原文口诀须原创归纳 | 逐条审查 |

> 当前 SKU 实测：raw_overlap_cards 4 → R3 专名豁免 4 → overlap_cards 0（合规）；开放前复跑。

---

## 五、API 契约（v0.1 设计，未实现）

### 5.1 设计原则

| 项 | 规则 |
|---|---|
| 只读 | 仅 GET；无写接口 |
| 版本 | `/v1/…`；数据集带 `data_version/rule_version` |
| 分页 | `limit/offset` 或 cursor；默认 ≤100 |
| 限流 | 按 key；匿名低配额；研究 key 申请（v0.2） |
| 字段选择 | `fields=`（减少敏感字段） |
| 错误 | 标准错误体（错误码/消息/文档链接） |
| 缓存 | ETag/Last-Modified；变更日志可查 |

### 5.2 端点草案

```text
GET /v1/books
GET /v1/characters?book=&limit=&offset=
GET /v1/entities/{id}
GET /v1/relations?book=&predicate=
GET /v1/events?book=&type=&limit=
GET /v1/gazetteer?kind=&real=
GET /v1/graph?book=
GET /v1/ratings?sample_min=
GET /v1/meta/versions
```

### 5.3 响应包装

```json
{"data":[…],"meta":{"data_version":"2026-11-05.01","rule_version":"sku-card@0.3-draft",
 "total":1536,"limit":100,"offset":0,"license":"research-only",
 "quality":{"grade_distribution":{"B":85,"C":1451}},"generated_at":"…"}}
```

---

## 六、质量声明与变更日志

| 项 | 要求 |
|---|---|
| 质量声明 | 每数据集附 07e/08d 分布（A-E/正确性）与已知缺口 |
| 置信标注 | 每条记录带 confidence/publish_state（SKU 已有） |
| 变更日志 | 版本/日期/变更摘要/影响面（`meta.versions`） |
| 已知限制 | 例如"跨书年代 low"、"N8 无 D 级"、"T13 大会 0 命中" |
| 引用口径 | 统计类附分母/口径声明（03l） |

---

## 七、工具与脚本

| 用途 | 工具 | 说明 |
|---|---|---|
| 统一导出 | `scripts/export_site_all.py` | EX-1..EX-8（8 导出器） |
| SKU 脱敏 | `scripts/build_sku_cards.py` | cards.desensitization/validation |
| 引文核验 | `scripts/verify_quotes.py` | W7（开放前全量） |
| 一致性 | `scripts/lint_consistency.py` | audit 数据 |
| 覆盖/正确 | 08b/08d 报告 | 质量声明 |
| 事件/关系/图 | `event_extractor.py`/`relation_validator.py`/`export_site_graph.py` | 数据集源 |

---

## 八、错误模式库（OD 系列）

| # | 错误 | 检测 | 修正 |
|---|---|---|---|
| OD-01 | 开放原文/连续片段 | W7/R1-R5 | 拦截 |
| OD-02 | 脱敏未执行 | cards desensitization 检查 | 复跑 |
| OD-03 | 无版本/变更日志 | meta 校验 | 补 |
| OD-04 | 未核实当确定事实 | 07e/质量声明 | 标注/撤下 |
| OD-05 | 可拼接片段（跨记录拼原文） | 片段审计 | 删/摘要化 |
| OD-06 | API 可写 | 接口审计 | 只读 |
| OD-07 | 无分页/限流 | 接口规范 | 补 |
| OD-08 | 许可不明 | license 字段检查 | 补 |
| OD-09 | 统计无口径 | 03l 检查 | 补口径 |
| OD-10 | 质量分布不公开 | meta 校验 | 补 quality |

---

## 九、检查清单

### 开放前
- [ ] 数据集/字段字典/分级确定；
- [ ] 脱敏 R1-R5 复跑合规；
- [ ] 质量声明（07e/08d/缺口）齐全；
- [ ] 许可/版权口径确认（权利审核）。

### 开放中
- [ ] API 只读/版本化/分页/限流；
- [ ] 字段选择支持；
- [ ] 响应含版本与质量元数据；
- [ ] 错误体规范。

### 开放后
- [ ] 变更日志更新；
- [ ] 抽检无原文片段；
- [ ] 外部引用可回溯（09i）；
- [ ] 反馈渠道/下架机制。

---

## 十、FAQ（首批 5 问）

**Q1 能开放原文吗？**
不能。01g §9.10 禁止原文正文/标注正文/连续片段出口；只开放结构化知识、统计、原创分析。

**Q2 SKU 卡 brief 含"原文感"怎么办？**
走脱敏 R1-R5：连续重合 <10 字、回锚不带文本、未过审不 approved；当前实测合规（overlap 0）。

**Q3 榜单数据能开放吗？**
能，但必须附口径/样本量/版本（Glicko-2 参考非官方）；低样本不发布。

**Q4 跨书年代数据能开放吗？**
可作为"参考层"开放，标 low/区间；不得表述为确定事实（07a）。

**Q5 API 什么时候有？**
v0.1 只定契约（未实现）；当前可用 EX 导出 JSON 文件作为数据集交付（附录 B）。

---

## 十一、相关文档

| 文档 | 关系 |
|---|---|
| `SKILL_09_应用总览_武侠版.md` | 09 组索引/边界 |
| `SKILL_09i_学术工具_武侠版.md` | 开放数据的研究消费 |
| `SKILL_08a_SKU字段_武侠版.md` | 脱敏 R1-R5 |
| `SKILL_07e_真实性评级_武侠版.md` | 质量声明 A-E |
| `SKILL_08d_正确性评估_武侠版.md` | 正确性声明 |
| `SKILL_03l_出现统计_武侠版.md` | 统计口径 |
| `SKILL_01g_标注符号集合原则.md` | §9.10 发布边界 |
| `docs/51-E组合流决策与导出适配层方案.md` | EX 契约（§五） |

---

## 附录 A · 与 shiji 原版差异对照（本件为综合）

| 史记 09 组 | 处置 | 武侠版 |
|---|---|---|
| 无数据开放件 | [新增] | 09h 数据开放 |
| 发布边界 | [继承] | 01g §9.10 执行 |
| 脱敏 | [继承] | SKU R1-R5 |
| 质量声明 | [新增] | 07e/08d 分布 |

## 附录 B · v0.1 待补清单

| # | 待补 | 前置 |
|---|---|---|
| H-1 | API 服务未实现（仅契约） | 工程 |
| H-2 | 许可协议/研究 key | 权利审核 |
| H-3 | 字段字典机器化（schema JSON） | EX/工程 |
| H-4 | 可拼接片段审计工具 | 脱敏 |
| H-5 | 变更日志/版本接口 | 工程 |
| H-6 | 外部引用回溯规范（09i 协同） | 09i |

---

## 结语

数据开放的智慧在"舍"：舍掉原文、舍掉未核实结论、舍掉不可追溯的片段，留下**可核、可引、可复现的结构化知识**。开放得越克制，研究价值越长久。
