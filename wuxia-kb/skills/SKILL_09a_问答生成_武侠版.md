---
name: skill-09a-wuxia
title: 问答生成（武侠版）——QA 对生成、证据检索与 W7 引文核验挂点
description: 武侠知识库问答（QA）生成规范：问题类型学（人物/关系/时间/地点/统计/设定/穿帮）、证据检索（N10 SKU/N5 关系/N4 时间/EX-5 事件/09j 地图/EX-8 一致性）、答案合成与证据字段、07e A-C 评级门控与"未知不猜"、W7 引文核验挂点（答案禁原文片段）、QA 对 schema、评测与回归。当需要从知识库生成可发布问答对、或设计问答检索链路时使用。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 09a 武侠版：问答生成 — 有证据才回答

> **上游声明**：本文从 shiji-kb `SKILL_09` 应用组移植重造（对应 docs/03 §3.10 问答/文献类应用，docs/05 §2.5 判定 09 组轻度 75-88%/09k 照搬），属本批 C1 应用组新划定的 09a。**无专属设计稿**：由 01g §9.8（江湖问答页）、07e 评级门控、W7 引文核验、N10 SKU/EX 数据接口综合而成（v0.1 框架）。
> **接口**：N10 `registry/sku/cards.json`（1,536 卡，含 confidence/publish_state/sources）、N5 `registry/relations`（910 边）、N4 `registry/time`、EX-5 `registry/events`（22,978）、EX-8 `registry/consistency`（44 条）、09j `registry/gazetteer.json`（619）、W7 `logs/w_group/quote_verify.json`。
> **核心原则**：**问答的每个答案都必须能指回证据；不确定就说不确定。** 未知不得猜答（01g §9.8 红线），原文片段不得作答案（W7/01g §9.10）。

---

## 一、定位与边界

### 1.1 工序位置

```text
数据层（SKU/relations/time/events/gazetteer/consistency）
        ↓
09a 问答生成（本文）→ QA 对（question/answer/evidence/grade/sources）
        ↓
评测/发布门控（07e A-C + W7 引文核验）→ 站点问答页/API（09h）
```

### 1.2 本文做什么

1. **问题类型学**：7 类问题与可回答性判定；
2. **证据检索**：每类问题的检索源与检索顺序；
3. **答案合成**：模板/句式、证据字段、置信与"参考/存疑"标注；
4. **门控**：07e A-C、未知不猜、脱敏、W7 引文核验；
5. **QA schema 与评测回归**。

### 1.3 本文不做什么

| 不做 | 归属 |
|---|---|
| 改数据/补登记 | 上游工序（只读） |
| 对话式 LLM 推理（自由生成） | v0.1 只做"检索+模板/受控生成" |
| 引文核验算法 | W7 `scripts/verify_quotes.py` |
| 评级算法 | 07e |
| 页面/API 服务 | W 组/09h |

### 1.4 关键约束

- **只答知识库内有证据的**；知识库外→"未知/建议查阅原文"；
- **A-C 才可答**：A/B 可直接答；C 必须标注"推算/存疑/参考"；D/E 拒答（或转内部记录）；
- **禁止原文**：答案不得包含原文连续片段；引文一律概括+回锚（loc_r/卡 ID）；
- **W7 挂点**：答案生成后抽样过 W7（`verify_quotes.py --file <qa.json>`），未命中不得发布。

---

## 二、快速开始（五步）

````text
Step 1 分类   问题属哪类（人物/关系/时间/地点/统计/设定/穿帮）？
Step 2 检索   按 §三 检索源取证据（SKU/edge/time/event/gazetteer/consistency）
Step 3 判定   证据是否充分？→ 可答/存疑答/拒答（07e 门控）
Step 4 合成   模板答案 + evidence/sources + grade + convention
Step 5 核验   W7 引文核验（如有引文/片段）+ 抽检 + 发布
````

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
$env:PYTHONIOENCODING='utf-8'

# 证据源体检
python -X utf8 -c "import json;d=json.load(open('registry/sku/cards.json',encoding='utf-8'));print(d['meta']['counts_total'],d['validation'])"
python -X utf8 scripts/verify_quotes.py --sku --strict

# 站点问答页数据（EX 导出后）
python -X utf8 scripts/export_site_all.py --apply
```

**成功标准**：① 每个答案有 evidence（loc_r/卡 ID/边 ID）+ grade；② 无证据不答/答"未知"；③ 答案无原文连续片段（W7 通过率 100%）；④ C 级答案有"存疑/推算"标注；⑤ 抽检 10% 答案与数据源一致；⑥ 拒答率/覆盖率可统计。

---

## 三、问题类型学与检索源

| 类 | 例 | 主检索源 | 可回答条件 |
|---|---|---|---|
| Q1 人物事实 | ××是谁/门派/结局 | SKU 卡 person/brief/fields | 卡 confidence ≥C 且字段非空 |
| Q2 人物关系 | ××与××什么关系 | N5 边（subject/predicate/object）+ 05c 双树 | 边存在且 strong/ok |
| Q3 时间 | ××发生在何时/年龄 | N4 time_points+book_anchors | 置信 high/medium（low 标注） |
| Q4 地点 | ××在哪里/怎么去 | EX-7 gazetteer + 09j | 地点已登记（real/unlocatable 标注） |
| Q5 统计 | 谁出现最多/多少回 | 03l 口径 + concordance | 口径声明齐全 |
| Q6 设定/一致性 | ××是否穿帮 | EX-8 consistency + 07c | 记录存在（A-E 分级） |
| Q7 跨书 | ××在两书是否同一人/先后 | 03b series + 07a 年代 | 系列身份 + low 标注 |
| Q8 原文类 | 原文怎么写的 | **拒答**（01g §9.10） | — |

### 3.1 检索顺序（每类固定）

```text
① 精确定位（实体 ID/canonical/边/PN）→ ② 别名/同义（03b aliases）→ ③ 跨书系列（series）
→ ④ 相关上下文（同段/同回）→ ⑤ 无 → 拒答/未知
```

---

## 四、答案合成与 QA schema

### 4.1 QA 对 schema（v0.1 约定）

```json
{"qa_id":"QA-20261105-001","question":"吕四娘的师父是谁？","answer":"吕四娘的师父是独臂神尼。",
 "answer_type":"factual","grade":"B",
 "evidence":[{"kind":"relation_edge","id":"…","subject":"吕四娘","predicate":"师承","object":"独臂神尼","loc":"…"}],
 "sources":["registry/relations/江湖三女侠.json"],
 "convention":"grade B：N5 明示师承边（E2）+ 卡字段一致；无原文片段",
 "unknown":false,"w7":{"checked":true,"hit":true}}
```

### 4.2 句式与标注规则

| 情形 | 句式 | 标注 |
|---|---|---|
| A/B 级事实 | 直接陈述 + 回锚 | 无 |
| C 级推算 | "据…推算/一般认为…" | `grade=C`、`confidence_note` |
| 跨书 low | "参考区间/两说并存" | `grade=C`、`cross_book=true` |
| 多源冲突 | "一说…另一说…" | `conflicts[]` 双记 |
| 无证据 | "知识库暂无可靠记载（可查阅原文）" | `unknown=true` |
| 原文类问题 | "本库不提供原文内容" | `refused=true` |

### 4.3 禁止项

- 原文连续片段（W7 + 01g §9.10）；
- 未核实内容表述为确定事实（07e）；
- 跨书结论当单书事实（07a）；
- 用"作者本意/常识"替代证据。

---

## 五、门控与评测

### 5.1 门控链

```text
证据存在？→ 否 → 拒答/未知
证据等级？→ D/E → 拒答；C → 标注；A/B → 直接答
脱敏？→ R1-R5 检查（SKU desensitization）
引文？→ W7 核验（verify_quotes --file）
→ 发布
```

### 5.2 评测指标

| 指标 | 目标 | 方法 |
|---|---|---|
| 证据覆盖率 | ≥95% 答案有 evidence | 自动校验 |
| 答案正确率 | 抽样 ≥90% | 人工抽检 10% |
| 拒答正确率 | 未知类 100% 不猜 | 构造未知集 |
| W7 通过率 | 100% 无原文片段 | verify_quotes |
| 一致性 | 与数据源零矛盾 | 交叉核对 |

---

## 六、工具与脚本

| 用途 | 工具 | 说明 |
|---|---|---|
| SKU 卡数据 | `scripts/build_sku_cards.py` | N10（卡字段/置信/脱敏） |
| 关系检索 | `scripts/relation_validator.py` | N5 边（产物） |
| 事件检索 | `scripts/event_extractor.py` | EX-5 事件（产物） |
| 时间检索 | `scripts/time_resolver_wuxia.py` | N4（产物） |
| 一致性检索 | `scripts/lint_consistency.py` | EX-8 数据源 |
| 引文核验 | `scripts/verify_quotes.py` | W7（禁原文出口） |
| 导出 | `scripts/export_site_all.py` | 站点问答数据 |

---

## 七、错误模式库（QA 系列）

| # | 错误 | 检测 | 修正 |
|---|---|---|---|
| QA-01 | 无证据作答 | evidence 字段校验 | 拒答 |
| QA-02 | 未知当确定答 | unknown 集抽检 | 改"未知" |
| QA-03 | 答案含原文片段 | W7 核验 | 改概括+回锚 |
| QA-04 | C 级当 A/B 答 | grade 审计 | 降级/标注 |
| QA-05 | 跨书结论当单书 | 层检查 | 标参考 |
| QA-06 | 多源冲突只取一说 | conflicts 检查 | 双记 |
| QA-07 | 无版本/来源 | schema 校验 | 补 |
| QA-08 | 拒答话术泄漏未核实结论 | 话术审计 | 中性化 |

---

## 八、检查清单

### 生成前
- [ ] 数据层导出/核验完成（SKU/N5/N4/EX-5/EX-8）；
- [ ] 问题集与类型分布确定；
- [ ] 门控规则（A-C/W7/脱敏）确认。

### 生成中
- [ ] 每题有检索路径与证据；
- [ ] unknown/refused 三类分明；
- [ ] grade 与 convention 字段齐全；
- [ ] 无原文片段。

### 生成后
- [ ] W7 核验通过；
- [ ] 抽检 10% 正确率达标；
- [ ] 指标统计（覆盖率/拒答率）；
- [ ] 发布/版本记录。

---

## 九、FAQ（首批 5 问）

**Q1 知识库答不了的问题怎么办？**
答"暂无可靠记载（可查阅原文）"，并记入问题集反馈；不得用常识猜。

**Q2 能不能让 LLM 自由生成答案？**
v0.1 不做；受控生成（模板+证据）优先。自由生成须过门控+W7，风险高。

**Q3 原文类问题为什么拒答？**
01g §9.10 禁止原文/连续片段出口；可给"概括+回锚定位"。

**Q4 多本书说法冲突怎么答？**
双记（conflicts）+ 按 D07 权威层级取高层级；不硬裁。

**Q5 W7 核验没过的答案怎么办？**
拦截不发布；改概括/换证据；W7 只给定位/长度/hash，不回传原文。

---

## 十、相关文档

| 文档 | 关系 |
|---|---|
| `SKILL_09_应用总览_武侠版.md` | 09 组索引/边界 |
| `SKILL_09h_数据开放_武侠版.md` | QA API 出口 |
| `SKILL_07e_真实性评级_武侠版.md` | A-E 门控 |
| `SKILL_08a_SKU字段_武侠版.md` | 卡字段/脱敏 |
| `SKILL_09j_地名应用_武侠版.md` | 地点问答 |
| `SKILL_01g_标注符号集合原则.md` | §9.8 江湖问答/§9.10 边界 |
| `scripts/verify_quotes.py` | W7 核验 |

---

## 附录 A · 与 shiji 09 原版差异对照（本件为综合）

| 史记 09 应用 | 处置 | 武侠版 |
|---|---|---|
| 问答/文献类应用 | [综合] | QA 对生成（证据+门控） |
| 无 W7 接口 | [新增] | W7 引文核验挂点 |
| 无 A-E 门控 | [新增] | 07e 评级门控 |
| 原文出口 | [替换] | 概括+回锚（禁原文） |

## 附录 B · v0.1 待补清单

| # | 待补 | 前置 |
|---|---|---|
| A-1 | 问答生成器（模板/检索/合成）未实现 | 工具化 |
| A-2 | 评测集（gold QA）未建 | 人工标注 |
| A-3 | 拒答/未知集构造 | 评测 |
| A-4 | 问答 API 出口（09h 协同） | 工程 |
| A-5 | 统计类问答的口径模板落地（03l） | 03l |
| A-6 | 跨书问答的 series 检索字段 | 03b/D07 |

---

## 结语

问答生成不是"让模型聊天"，而是**把知识库的证据翻译成一句可核验的话**：有问题类型、有检索路径、有证据字段、有评级门控、有引文核验。答不了就说不知道，这比答错更有价值。
