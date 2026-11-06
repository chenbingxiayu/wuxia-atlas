---
name: skill-03-wuxia
title: 实体分析总览（武侠版）——标注、消歧、反思、渲染的 03 组地图
description: 实体层（03 组）技能总览：03a 实体+动词统一标注（生产入口）、03b 人名消歧与登记、03c/03e/03f 三类反思（按章/类型/边界）、03d 渲染发布、03g-03k 时间轴/子类/登记/同形异义/类型扩展、03l 出现统计；各件分工、依赖与数据接口（tagged → registry → concordance）。当需要确定实体层某道工序由哪个 SKILL 承载、或为 03 组立项扩展时使用。
version: v0.1-draft
last_updated: 2026-11-06
---

# SKILL 03：实体分析总览（武侠版）

> **上游声明**：本文为 03 组导航总览（骨架参考 shiji-kb 的 SKILL_03_实体构建，内容按 `wuxia-kb/skills/` 现役 03 组件重写；机制类总览）。

> **一条主线**：底本 →（03a 标注）→ tagged →（03b 消歧登记）→ registry →（03c/03e/03f 反思循环）→ 规律库 references →（03d 渲染）→ 展示。**生产入口只有一个：03a。**

---

## 一、快速开始（三步）

```text
Step 1 要标注      → SKILL_03a（15 实体+6 动词域统一单遍，SKILL_00 管线 annotate 阶段）
Step 2 要消歧/登记 → SKILL_03b（多书 registry + 语境注记 + cross-book canonical 政策）
Step 3 要查覆盖/统计 → 03l 出现统计（registry/concordance）+ 02e 词法（漏标候选）
```

---

## 二、03 组件分工表

| 件 | 文件 | 一句话分工 | 关键接口 |
|---|---|---|---|
| 03a | `SKILL_03a_实体标注.md`（v1.9） | 实体+动词统一标注生产规范；§二 SYSTEM_PROMPT 唯一提示词入口 | tagged/*.tagged.md；build_03a_fewshot |
| 03b | `SKILL_03b_人名消歧_武侠版.md` | 同名/同指消解；已核准映射表；跨书 canonical | registry/entities.json（425 条两态） |
| 03c | `SKILL_03c_按章反思_武侠版.md` | 逐章反思循环（G2 收敛），产物回填 DEF 库 | references/03c1 规律库 |
| 03d | `SKILL_03d_渲染发布_武侠版.md` | 标注语料渲染/AST→HTML（H-1~H-10） | render_ast_html.py |
| 03e | `SKILL_03e_类型反思_武侠版.md` | 类型误标反思（跨类型冲突） | references/03e1 |
| 03f | `SKILL_03f_边界错误反思_武侠版.md` | 实体边界错误反思（夹心/吞并/分裂） | 02e 词法夹心检测供料 |
| 03g | `SKILL_03g_时间轴标注_武侠版.md` | 时间轴标注方法（←D05） | N4 time_resolver |
| 03h | `SKILL_03h_实体子类_武侠版.md` | 实体子类细分（←D08） | 分类树五件套 |
| 03i | `SKILL_03i_分类登记_武侠版.md` | 分类挂叶登记（N9 联动） | registry + N9 |
| 03j | `SKILL_03j_同形异义_武侠版.md` | 同形异义消解（01g 附录细则联动） | references/03j1 |
| 03k | `SKILL_03k_类型扩展_武侠版.md` | 新类型立项扩展（80 条 new_entity_types 先例） | wordlists/new_entity_types |
| 03l | `SKILL_03l_出现统计_武侠版.md` | 实体出现统计（L3 跨书聚合） | build_entity_concordance |

## 三、依赖与纪律

- **03a 是唯一生产入口**：其余 03 件消费或反哺它，不并列第二套标注规范；
- **反思闭环**：03c/03e/03f 的裁定 →（人工复核）→ 种子/规则 → 03a 再生成（§5.3 纪律：规则改在 docs，示例改在种子）；
- **登记层唯一**：03b 产出/维护 registry；任何"登记表 v2"不得另起目录；
- 扩展类型走 03k 立项（词表 source.md + 编译表成对），不直接改 symbols.py。

## 工具与脚本

本总览无专属脚本；组内件的脚本入口见各件"工具与脚本"节；全链阶段对照见 `SKILL_00_管线总览_武侠版.md`。

## 检查清单

- [ ] 找到的工序确属实体层（事件/关系分别归 04/05 组总览）
- [ ] 新增件已在本表登记；分工不与现役件重叠
- [ ] 反思产物进了对应 references 规律库（不止留在 docs）
- [ ] lint_skills PASS（score ≥ 90）

## 成功标准

- 实体层工序一件一位，不重复建设
- 03a 版本锁（v1.9）与 few-shot 版本一致（build_03a_fewshot --check 全绿）
- lint_skills PASS（score ≥ 90），无 error
