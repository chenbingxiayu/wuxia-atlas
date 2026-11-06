---
name: skill-sku-wuxia
title: SKU 卡片类型规划（武侠版）——五类卡片 Schema（双稿合并定稿 v0.3）
description: 为《梁羽生武侠全集》知识库（Astro SSG，约 5,000+ 页）规划五类卡片（人物/门派/武功/兵器/秘籍）的字段 Schema、来源管线映射、统一元数据块、粒度与卡片聚合、章级 v2 武侠化与发布边界。本技能是"标注→知识→页面"的收官件：消费 01g/02ab/#4a/#5/#6/#7/#8/#9/#10/#11 与神兵表、招式表等全部已定版上游产出，向人物档案页、门派页、武功词条页、神兵谱、秘籍页、游戏卡与说书人专栏供数。
version: 0.3-draft
last_updated: 2026-11-03
---

> **版本状态**：v0.3-draft 双稿合并定稿——由 v1（GLM 子 agent 全量稿，865 行）与 v2（deepseek compact 适配稿，777 行）合并而成：骨架取 v1，v2 全部独立亮点回收、两稿缺陷修复；逐条评审与裁决记录见 `docs/16-SKILL_SKU卡片双稿对比分析与合并说明.md`。
> **演示声明**：本文档全部 JSON 样例均为**演示数据非发布内容**（`meta.demo=true`＋`publish_state` 非 approved 双保险）；实体/边/事件/地点 ID 为占位序号（01g 不透明序号制 E-{类型码}-{序号} 式），以登记层与各管线实际 ID 为准；引用上游契约处（01g/02ab/#4a/#5/#6/#7/#8/#9/#10/#11）以各件定版文本为准，字段名为消费语义示意，最终以各件 schema 定版为准。
> **任务对应**：docs/06-武侠重设计任务清单 · 任务 12（★，软依赖 #1/#6 均已定版）。
> **版权红线**：卡面正文一律为原创转述、结构化事实、统计与原创分析；原文片段与标注正文永不上卡（第六章成文）。

---

# 一、技能定位

## 1.1 SKU＝标注→页面的最后一公里

- 前面 11 项任务解决"把原著读成结构化知识"；本技能解决"把这些知识变成 5,000+ 页面的数据结构"。
- **字段设计错了，前端返工；字段来源接错了，页面数据缺失**——因此本技能的核心纪律是：每个字段必须标明来源管线，无来源的字段不许上卡。
- SKU 同时是**可复跑原创分析**的单元（01g §9.9）：凡统计类字段必须说明分母，支撑"出现最多/打斗密度"类结论的可复跑。
- SKU 还是**可独立分发**的产品单元（08a §2.2）：同一张卡同时喂页面、游戏卡（14 个）与说书人专栏。

## 1.2 管线位置图（全管线数据源汇聚）

```
┌─ 标注层（本地，不对公网发布）────────────────────────────────────────┐
│ 01a/01f 原文与底本 · 02a/02b 章回结构(r{N}回锚/#pn-r{N}.{X}机锚)        │
│ 03 实体逐字标注 · 04a 事件层(六域⊞⊠⊡⊟▣■) · 04f 动词层(六域触发词)        │
│ 05 时间层(时点键/年龄锚)                                              │
└──────────────┬────────────────────────────────────────────────────┘
               ▼
┌─ 知识层（全部已定版）──────────────────────────────────────────────┐
│ 01g 实体登记(15 类/别名/9.9 SKU 最低字段/9.10 发布边界)               │
│ #6 关系三层谓词(师承/结义/配偶/任职/转移/传授/掌握…，双树辈分推导)      │
│ #7 跨书双层 canonical(active_books/first_appearance 派生)              │
│ #8 五棵分类树 · #9 词表版本协议 · #10 gazetteer 双图层                  │
│ #11 设定一致性评级(A–E) · 既有资产：神兵表(canonical/kind/grade/chain)  │
│                          既有资产：招式表(parent_art/used_by/conf)      │
└──────────────┬────────────────────────────────────────────────────┘
               ▼
┌─ 本技能 T12：五类卡片(人物/门派/武功/兵器/秘籍)＋章级 SKU ─────────────┐
│ 统一元数据块(01g §9.9 九项不可减) · 投影制 ID · 概要+详情分层 · 脱敏审查 │
└──────────────┬────────────────────────────────────────────────────┘
               ▼
┌─ 呈现层 ──────────────────────────────────────────────────────────┐
│ 人物档案页(3,000+) · 门派页 · 武功词条页(2,000+) · 神兵谱/weapons       │
│ 秘籍页(新增) · 游戏卡(14 个：抽卡/对战/每日挑战) · 说书人专栏(章级 SKU)   │
└──────────────────────────────────────────────────────────────────┘
```

## 1.3 与 08a/08e 的实例化关系声明

| 参考件 | 取什么 | 武侠实例化 |
|---|---|---|
| 08a 知识颗粒度管理 | Factual/Procedural/Relational 三类 SKU 结构、粒度标准、通用 Schema 思想 | 三类全部武侠化（第三章）；通用字段升级为统一元数据块（2.0）；粒度标准沿用并加武侠调整（4.1） |
| 08e 表格数据反思迭代提取 | **仅取 §8.1 章级 v2 结构**（README/eureka/mapping/facts） | 四件套武侠化（第五章）；五轮迭代法不引入——武侠以卡为单位、以管线为流水线，不按章逐轮深挖 |

## 1.4 设计纪律六条

1. **版权红线**：原文正文与标注正文仅本地使用；卡面不携带原文片段。
2. **无来源不上卡**：每个字段必须能指回 2.6 核对表所列管线；指不回的字段删除。
3. **未知不强填**：缺失即用约定缺省（空数组/null/"未明示"），不虚构（01g 未知原则）；"确认无所属"与"信息缺失"是两种缺省态，分开登记（2.7 条 1）。
4. **不与上游契约静默矛盾**：凡上游已定版的格式与取值（#7 跨书、#11 评级、#9 词表版本等），卡片只引用不改写。
5. **演示与发布隔离**：一切示例 JSON 携带 `demo:true/demo_note` 且 `publish_state` 不为 approved；发布库拒绝 demo 卡。
6. **统计必带分母**：凡"出现最多/密度"类字段，必须同时给出统计口径与分母（01g §9.9）。

---

# 二、五类卡片 Schema（Q1 核心交付物）

## 2.0 统一元数据块（全卡共用，01g §9.9 九项最低字段不可减）

每张卡的 JSON 顶层第一个键固定为 `meta`，九项最低字段全部落位于此，另加实体回指与演示隔离标记。规范名与别名不入 meta——它们是卡面业务字段（name/aliases），meta 只留 `entity_ref` 回指登记层主键，避免双存：

| 字段 | 类型 | 来源管线 | 对应 01g §9.9 |
|---|---|---|---|
| meta.stable_id | string | 本技能派生（自实体 ID，投影制见 4.3） | ① 稳定单元 ID |
| meta.entity_ref | string | 01g 实体登记层主键（不透明序号，E-{类型码}-{序号} 式） | ①（实体回指） |
| meta.card_type | enum：person/faction/art/artifact/manual | 本技能 | ①（类型维度） |
| meta.proposition | string ≤100 字 | 本技能（基于卡面结构化字段归纳的一句话命题） | ② 原创命题或结构化事实 |
| meta.supported_by | object{entities[],relations[],events[]} | 01g/#6/#4a/#5 回指（一律实体/边/事件 ID） | ③ 支撑实体、关系与事件 |
| meta.sources | array | 全部来源管线（含 r{N}/loc_r 定位指针，不含正文） | ④ 来源定位 |
| meta.confidence | enum A–E | #11 设定一致性评级聚合（6.3；受 01g 状态上限约束） | ⑤ 可信状态 |
| meta.data_version | string（日期.序号） | 本技能 | ⑥ 数据版本 |
| meta.rule_version | string | 本技能主 Schema 版＋#9 词表版本协议 | ⑦ 规则版本 |
| meta.method / meta.denominator | string / string|null | 本技能（统计字段必填分母） | ⑧ 分析方法与统计分母 |
| meta.publish_state | enum：draft/in-review/approved/blocked | 01g §9.10 审查（6.2） | ⑨ 发布许可状态 |
| meta.demo / meta.demo_note | bool / string | 本技能（演示隔离附加项） | —（本技能附加） |

> 取值约定：`confidence` 用 #11 的 A–E 五级，本技能只做聚合不做评级（6.3）；#11 定版的硬约束随聚合带入——"来源声称"级记载最高 C，"未知"≠E。字段级 conf 词表随来源管线照录（神兵表 strong 系、#6 边与 #4a 事件以各自定版为准），卡级才折算 A–E。

## 2.1 人物卡（人物档案页 3,000+ 页的主数据结构）

**字段表**：

| 字段 | 类型 | 来源管线 | 缺省（缺失时） |
|---|---|---|---|
| name.canonical | string | 01g+#7 别名表（type=本名/规范名） | 必填；确无本名者取最常用称谓并降可信 |
| aliases（绰号组） | array[{surface,type}] | 01g+#7 别名表（surface/type=绰号/诨号/字号/法号） | `[]` |
| identity_tags（身份） | enum[] | #8 身份树叶子 | `[]` |
| faction_history（门派履历） | array[{faction_ref,role,edge_ref,conf}] | #6 任职/师承/转移边＋#8 门派类型 | `[]`；散修见 2.7 条 1，不虚构 |
| seniority（辈分） | object | #6 双树辈分推导（师祖/师父/徒弟深度、同门/同辈） | `null` |
| teachers（师承） | array[edge_ref] | #6 师承树 | `[]` |
| disciples（传人） | array[edge_ref] | #6 传授边（反向） | `[]` |
| kinship（亲属/配偶/结义） | array[edge_ref] | #6 配偶/结义/亲属谓词 | `[]` |
| romance（情缘） | array[edge_ref] | #6 关系边（情缘类谓词，谓词名以 #6 总表为准） | `[]` |
| arts（武功列表） | array[{art_ref,verb,conf}] | #6 掌握边＋招式表 used_by | `[]` |
| life_events（生平大事） | array[event_ref] | #4a 事件流＋#5 时点键排序 | `[]` |
| age_anchor（年龄锚） | object | #5 年龄锚 | `null` |
| ending（结局） | object{type,event_ref,summary,conf} | #4a 结局事件（死亡/退隐等；事件五状态取值以 #4a 定版为准） | `{"type":"未明示"}` |
| relational_sku_refs | array[sku_ref] | 本技能（Relational SKU 登记，见 3.3/3.4） | `[]` |
| brief（小传） | string 200–500 字 | 原创分析（基于结构化字段转述，非原文） | 留空待人工 |
| meta | object | 见 2.0 | 必填 |

**JSON 演示样例**（练霓裳；演示数据非发布内容）：

```json
{
  "meta": {
    "stable_id": "card.person.demo-lian-nichang",
    "entity_ref": "E-P-0101",
    "card_type": "person",
    "proposition": "练霓裳（玉罗刹/白发魔女）为武当弃徒、天山创派掌门，与卓一航的正邪情缘是明末江湖阵营冲突的缩影",
    "supported_by": {
      "entities": ["E-P-0101", "E-P-0102", "E-F-0007", "E-F-0008"],
      "relations": ["edge.demo.001", "edge.demo.002", "edge.demo.003", "edge.demo.004"],
      "events": ["evt.demo.001", "evt.demo.002", "evt.demo.003"]
    },
    "sources": ["01g:E-P-0101", "#6:edge.demo.001-004", "#4a:evt.demo.001-003", "02ab:{作品ID}#pn-r{N}.{X}（演示占位，不含正文）"],
    "confidence": "B",
    "data_version": "2026-11-03.01",
    "rule_version": "sku-card@0.3-draft+rel-verbs@v1+event-fields@v1+glossary@v1",
    "method": "登记层投影＋关系边汇聚＋人工复核",
    "denominator": null,
    "publish_state": "draft",
    "demo": true,
    "demo_note": "演示数据非发布内容——实体/边/事件 ID 均为占位序号，条目经演示化处理，禁止直接上线"
  },
  "name": { "canonical": "练霓裳" },
  "aliases": [
    { "surface": "玉罗刹", "type": "绰号" },
    { "surface": "白发魔女", "type": "诨号" }
  ],
  "identity_tags": ["山寨首领", "门派掌门"],
  "faction_history": [
    { "faction_ref": "E-F-0007", "role": "弟子（后叛出）", "edge_ref": "edge.demo.001", "conf": "B" },
    { "faction_ref": "E-F-0008", "role": "创派掌门", "edge_ref": "edge.demo.002", "conf": "A" }
  ],
  "seniority": null,
  "teachers": [],
  "disciples": [{ "person_ref": "E-P-0104", "verb": "传授", "edge_ref": "edge.demo.003", "conf": "B" }],
  "kinship": [],
  "romance": [{ "person_ref": "E-P-0102", "verb": "情缘", "edge_ref": "edge.demo.004", "conf": "A" }],
  "arts": [{ "art_ref": "E-A-0012", "verb": "掌握", "conf": "B" }],
  "life_events": [
    { "event_ref": "evt.demo.001", "t_key": null, "brief": "山寨时期与武当诸侠冲突（原创转述）" },
    { "event_ref": "evt.demo.002", "t_key": null, "brief": "情变之夜一夜白头（原创转述）" }
  ],
  "age_anchor": null,
  "ending": { "type": "退隐", "event_ref": "evt.demo.003", "summary": "归隐天山，不履江湖（原创转述）", "conf": "A" },
  "relational_sku_refs": ["sku.rel.demo-lian-zhuo"],
  "brief": "练霓裳，绰号玉罗刹，后以白发魔女之名行世。早年自立山寨，行事快意恩仇，与武当弟子卓一航相恋而阵营对立。情变之后一夜白头，终归隐天山开宗授徒，成为天山一脉尊奉的祖师级人物。其一生贯穿明末江湖，是梁书痴情与执念主题的代表性人物。（本段为原创转述，非原文）"
}
```

> 演示注记：`teachers:[]` 系"未知不强填"缺省态演示（师承条目略）；`seniority:null`、`age_anchor:null` 同理。演示条目不得当真实设定引用。

## 2.2 门派卡（门派页主数据结构）

**字段表**：

| 字段 | 类型 | 来源管线 | 缺省（缺失时） |
|---|---|---|---|
| name.canonical | string | 01g+#7 别名表 | 必填 |
| aliases（别称/全称） | array[{surface,type}] | 01g+#7 别名表 | `[]` |
| faction_type（门派类型） | enum | #8 门派树叶子（取值以 #8 定版为准） | `"未明示"` |
| lineage（谱系·历代掌门） | array[{person_ref,term,edge_ref,conf}] | #6 任职边（掌门类谓词）＋#5 时点键定任期 | `[]` |
| signature_arts（镇派武功） | array[{art_ref,conf}] | #6 传授/持有边＋武功卡回指 | `[]` |
| strongholds（据点） | array[place_ref] | #10 gazetteer 双图层＋#6 组织驻地谓词 | `[]` |
| timeline（兴衰时间线） | array[event_ref] | #4a 事件流（组织域事件）＋#2 动词触发 | `[]`；超长按 4.1 分层 |
| status（存续状态） | object{value,basis_event} | #4a 灭派/重建/衰落事件推导（枚举词表见附录 B） | `{"value":"未明示"}` |
| branch_alliance（分支/盟友/敌对） | array[edge_ref] | #6 联盟/敌对/分支谓词 | `[]` |
| member_stat | object{metric,value,denominator} | #6 关系边统计（口径＋分母必填） | `null` |
| brief（门派简介） | string 200–500 字 | 原创分析（转述，非原文） | 留空待人工 |
| meta | object | 见 2.0 | 必填 |

**JSON 演示样例**（武当派；演示数据非发布内容）：

```json
{
  "meta": {
    "stable_id": "card.faction.demo-wudang",
    "entity_ref": "E-F-0007",
    "card_type": "faction",
    "proposition": "武当派为中原道门大派，紫阳道长执掌期间门风整肃，其弟子与玉罗刹的情缘牵入正邪恩怨",
    "supported_by": {
      "entities": ["E-F-0007", "E-P-0201", "E-P-0102", "E-P-0101"],
      "relations": ["edge.demo.005", "edge.demo.001"],
      "events": ["evt.demo.f001", "evt.demo.f002"]
    },
    "sources": ["01g:E-F-0007", "#6:edge.demo.005", "#4a:evt.demo.f001-f002", "#10:place 实体（演示占位）"],
    "confidence": "B",
    "data_version": "2026-11-03.01",
    "rule_version": "sku-card@0.3-draft+rel-verbs@v1+event-fields@v1",
    "method": "登记层投影＋任职边汇聚＋人工复核",
    "denominator": null,
    "publish_state": "draft",
    "demo": true,
    "demo_note": "演示数据非发布内容——条目经演示化处理，禁止直接上线"
  },
  "name": { "canonical": "武当派" },
  "aliases": [{ "surface": "武当", "type": "简称" }],
  "faction_type": "名门正派",
  "lineage": [
    { "person_ref": "E-P-0201", "term": null, "edge_ref": "edge.demo.005", "conf": "A" }
  ],
  "signature_arts": [{ "art_ref": "E-A-0021", "conf": "A" }],
  "strongholds": [{ "place_ref": "E-L-0001", "conf": "A" }],
  "timeline": [
    { "event_ref": "evt.demo.f001", "t_key": null, "brief": "紫阳道长执掌时期，门风整肃（原创转述）" },
    { "event_ref": "evt.demo.f002", "t_key": null, "brief": "弟子卓一航与玉罗刹情缘牵入门派恩怨（原创转述）" }
  ],
  "status": { "value": "兴盛", "basis_event": "evt.demo.f001" },
  "branch_alliance": [],
  "member_stat": {
    "metric": "登记弟子边计数",
    "value": 3,
    "denominator": "全 34 部 #6 登记关系边中谓词=任职∧客体=武当派 的边总数（演示分母）"
  },
  "relational_sku_refs": [],
  "brief": "武当派为中原道门大派，居武当山，门风端方，以内家剑法与森严门规著称。紫阳道长执掌期间声势正盛，门下弟子行侠仗义亦受门规约束。与各大名门并立，是江湖正道的中坚。（原创转述，非原文）"
}
```

> 演示注记：`lineage[].term:null` 系任期时点未锚定（#5 时点键待补）；`member_stat` 的 value 为演示数字，分母写法示范"统计对象＋谓词条件＋语料范围"三要素（K10）。

## 2.3 武功卡（武功词条页 2,000+ 页主数据结构）

**字段表**：

| 字段 | 类型 | 来源管线 | 缺省（缺失时） |
|---|---|---|---|
| name.canonical | string | 01g+#7 别名表 | 必填 |
| aliases（别称） | array[{surface,type}] | 01g+#7 别名表 | `[]` |
| category（品类） | enum | #8 武功品类树叶子（剑法/内功/轻功…） | `"未归类"` |
| hierarchy（层级归属） | object{system,parent_art,level} | #8 谱系树＋招式∈武功∈心法边 | `null` |
| moves（招式列表） | array[{move_ref,used_by,conf}] | 招式表（parent_art/used_by/conf） | `[]` |
| creator（创派人） | object{person_ref,conf} | #6 传承链首环＋#4a 创派/悟创事件 | `{"type":"创派者未明"}` |
| inheritance_chain（传人链） | array[{from_ref,to_ref,verb,edge_ref,conf}] | #6 师承/传授边（双树）；传闻孤证降可信（6.3） | `[]` |
| practitioners（会用者） | array[person_ref] | 招式表 used_by＋#6 掌握边 | `[]` |
| grade / grade_basis（品级评价） | enum / string | 原创分析（出场战绩事件统计支撑 basis）；写法对齐神兵表 grade/grade_basis；兵器 grade 实测词表=神兵/利器（未评=null），武功卡枚举扩充见附录 B | `null`（不评） |
| recorded_in（载于秘籍） | array[manual_ref] | 秘籍卡互指边（01g FAQ Q7/Q8 内容-技术分层） | `[]` |
| brief（武功说明） | string 200–500 字 | 原创分析（转述，非原文口诀） | 留空待人工 |
| meta | object | 见 2.0 | 必填 |

**JSON 演示样例**（七十二手连环剑；演示数据非发布内容）：

```json
{
  "meta": {
    "stable_id": "card.art.demo-lianhuan-jian",
    "entity_ref": "E-A-0021",
    "card_type": "art",
    "proposition": "七十二手连环剑为武当进阶剑术，共七十二式连环使出，经紫阳道长亲传卓一航",
    "supported_by": {
      "entities": ["E-A-0021", "E-P-0201", "E-P-0102", "E-F-0007"],
      "relations": ["edge.demo.006"],
      "events": []
    },
    "sources": ["01g:E-A-0021", "招式表:parent_art=E-A-0021", "#6:edge.demo.006"],
    "confidence": "A",
    "data_version": "2026-11-03.01",
    "rule_version": "sku-card@0.3-draft+rel-verbs@v1+event-fields@v1",
    "method": "登记层投影＋招式表对账＋人工复核",
    "denominator": null,
    "publish_state": "draft",
    "demo": true,
    "demo_note": "演示数据非发布内容——条目经演示化处理，禁止直接上线"
  },
  "name": { "canonical": "七十二手连环剑" },
  "aliases": [],
  "category": "剑法",
  "hierarchy": {
    "system": "E-T-0001（#8 谱系树节点，演示占位）",
    "parent_art": null,
    "level": "武功层"
  },
  "moves": [
    { "move_ref": "E-M-0001", "used_by": ["E-P-0102"], "conf": "B" },
    { "move_ref": "E-M-0002", "used_by": ["E-P-0102"], "conf": "B" }
  ],
  "creator": { "type": "创派者未明" },
  "inheritance_chain": [
    { "from_ref": "E-P-0201", "to_ref": "E-P-0102", "verb": "传授", "edge_ref": "edge.demo.006", "conf": "A" }
  ],
  "practitioners": ["E-P-0102"],
  "grade": null,
  "grade_basis": "未评——需出场战绩事件统计支撑",
  "recorded_in": ["card.manual.demo-jianpu"],
  "brief": "七十二手连环剑为武当剑法，共七十二式，连环使出、绵密不断，是武当入室弟子的进阶剑术。由掌门紫阳道长亲传弟子卓一航。本卡为创派者未明与品级不评两个缺省态的演示。（原创转述，非原文）"
}
```

> 演示注记：`creator` 缺省态与 `grade:null` 均系"未知不强填"演示——无战绩统计不评品级；`practitioners` 只收招式表 used_by 与 #6 掌握边实际支撑的人物，不因叙事声名扩列。

## 2.4 兵器卡（神兵谱 /weapons 主数据结构）

> 命名与覆盖面注记：卡类型沿用"兵器卡"（card_type=artifact），但神兵表实测 226 件的 kind 分布为 宝物 109/暗器 32/奇门 22/药材 19/刀 18/剑 13/兵器 10/护甲 3——本卡实际覆盖**器物全类**，kind 照录神兵表词表，页面分组按 kind 呈现。

**字段表**：

| 字段 | 类型 | 来源管线 | 缺省（缺失时） |
|---|---|---|---|
| name.canonical | string | 神兵表 canonical（对齐 01g+#7） | 必填 |
| kind（类型） | enum | 神兵表 kind（实测词表：宝物/暗器/奇门/药材/刀/剑/兵器/护甲；#8 器物树如有叶子则对齐） | `"未归类"` |
| grade / grade_basis（品级） | enum / string | 神兵表 grade/grade_basis（实测词表：神兵/利器，grade_basis 为出处标注式如"明文"） | `null`（不评） |
| forge（锻造） | object{smith_ref,place_ref,event_ref} | #4a 锻造事件（⊟域）＋#10 地点 | `{"type":"锻造未明"}` |
| chain（持有链） | array[{verb,persons,book,loc,loc_r,conf}] | 神兵表 chain 直接投影（verb/persons/book/loc/conf 照录）；loc_r 为 02ab 机锚回填位；排序可用 #4a 事件链槽位（chain_type/prev/next） | `[]` |
| current_whereabouts（下落） | object{status,event_ref,loc_ref} | #4a 毁损/失传/封存事件（chain 末环）＋#10 | `{"type":"下落不明"}` |
| brief（兵器说明） | string 200–500 字 | 原创分析（转述，非原文） | 留空待人工 |
| meta | object | 见 2.0 | 必填 |

**JSON 演示样例**（游龙剑，chain 为神兵表实测投影的简化演示；演示数据非发布内容）：

```json
{
  "meta": {
    "stable_id": "card.artifact.demo-youlong",
    "entity_ref": "E-O-0001",
    "card_type": "artifact",
    "proposition": "游龙剑为著名神兵，几经易手（凌未风夺自楚昭南等），终毁于江湖纷争",
    "supported_by": {
      "entities": ["E-O-0001", "E-P-0301", "E-P-0302"],
      "relations": [],
      "events": ["evt.demo.w001", "evt.demo.w002", "evt.demo.w003"]
    },
    "sources": ["神兵表:chain(E-O-0001)", "#4a:evt.demo.w001-w003", "02ab:{作品ID}#pn-r5.7 等"],
    "confidence": "A",
    "data_version": "2026-11-03.01",
    "rule_version": "sku-card@0.3-draft+event-fields@v1",
    "method": "神兵表 chain 投影＋人工复核",
    "denominator": null,
    "publish_state": "draft",
    "demo": true,
    "demo_note": "演示数据非发布内容——chain 为神兵表实测投影的简化（完整链另含 6:125 第二处毁损记载与 6:65 重复行，资产注记转神兵表维护方）；实体/事件 ID 为占位"
  },
  "name": { "canonical": "游龙剑" },
  "kind": "剑",
  "grade": "神兵",
  "grade_basis": "明文",
  "forge": { "type": "锻造未明" },
  "chain": [
    { "verb": "夺", "persons": ["E-P-0301", "E-P-0302"], "book": "七剑下天山", "loc": "5:7", "loc_r": "{作品ID}#pn-r5.7", "conf": "strong" },
    { "verb": "夺", "persons": ["E-P-0301", "E-P-0303", "E-P-0304"], "book": "七剑下天山", "loc": "6:65", "loc_r": "{作品ID}#pn-r6.65", "conf": "strong" },
    { "verb": "毁", "persons": ["E-P-0301", "E-P-0305", "E-P-0302"], "book": "七剑下天山", "loc": "6:69", "loc_r": "{作品ID}#pn-r6.69", "conf": "strong" }
  ],
  "current_whereabouts": { "status": "已毁", "event_ref": "evt.demo.w003", "loc_ref": null },
  "brief": "游龙剑为著名神兵，锋锐无匹，几经易手，终毁于江湖纷争。本卡持有链为神兵表 chain 字段（verb/persons/book/loc/conf）的直接投影，锻造环节缺省不填。（原创转述，非原文）"
}
```

## 2.5 秘籍卡（秘籍页新增主数据结构）

**字段表**：

| 字段 | 类型 | 来源管线 | 缺省（缺失时） |
|---|---|---|---|
| name.canonical（谱名） | string | 01g+#7 别名表 | 必填 |
| content_arts（所载武功） | array[art_ref] | 内容-技术分层（01g FAQ Q7/Q8）：秘籍=载体（文书），武功=技术，载体→技术引用 | `[]` |
| author（作者/托名） | object{person_ref,note,conf} | #6 创作/传授边＋#4a 悟创事件 | `{"type":"作者未明（托名常态）"}` |
| provenance（争夺事件链） | array[event_ref] | #4a 物件域（⊟）事件流（夺宝争谱类型）＋#2 触发词；链序用 #4a 事件链槽位（chain_type/prev/next） | `[]` |
| holders（持有者变迁） | array[edge_ref] | #6 转移/持有谓词；若该秘籍已按宝物入神兵表，chain 可同兵器卡投影 | `[]` |
| status（现存状态） | object{value,basis_event} | #4a 毁/藏/失传事件 | `{"value":"未明示"}` |
| locations（发生地） | array[place_ref] | #10 gazetteer 双图层 | `[]` |
| brief（秘籍说明） | string 200–500 字 | 原创分析（转述，非原文内容） | 留空待人工 |
| meta | object | 见 2.0 | 必填 |

> 不设 content_type（武功秘籍/内功心法/兵法）独立字段——该分类在 01g FAQ Q7/Q8 与 #8 树中无定版词表落点，按"无来源不上卡"纪律不入正文，存附录 B 待议。

**JSON 演示样例**（《某剑谱》——整体为演示虚构，自造示意；演示数据非发布内容）：

```json
{
  "meta": {
    "stable_id": "card.manual.demo-jianpu",
    "entity_ref": "E-D-0001",
    "card_type": "manual",
    "proposition": "《某剑谱》为演示虚构秘籍：载体与所载武功分离，争夺事件链以物件域事件为骨架",
    "supported_by": {
      "entities": ["E-D-0001", "E-A-0021", "E-P-0401"],
      "relations": ["edge.demo.007"],
      "events": ["evt.demo.m001", "evt.demo.m002", "evt.demo.m003"]
    },
    "sources": ["01g FAQ Q7/Q8 内容-技术分层", "#4a:evt.demo.m001-m003", "#6:edge.demo.007"],
    "confidence": "C",
    "data_version": "2026-11-03.01",
    "rule_version": "sku-card@0.3-draft+event-fields@v1",
    "method": "Schema 结构演示（自造虚构条目）",
    "denominator": null,
    "publish_state": "blocked",
    "demo": true,
    "demo_note": "演示数据非发布内容——本卡整体为演示虚构（占位名某剑谱），不含原著任何内容，publish_state 恒为 blocked"
  },
  "name": { "canonical": "《某剑谱》" },
  "content_arts": ["E-A-0021"],
  "author": { "person_ref": null, "note": "作者未明（托名常态，缺省示例）", "conf": null },
  "provenance": [
    { "event_ref": "evt.demo.m001", "verb": "现世", "brief": "剑谱重现江湖（原创虚构转述）", "conf": "C" },
    { "event_ref": "evt.demo.m002", "verb": "争夺", "brief": "多派争夺（原创虚构转述；事件类型归 #4a 夺宝争谱，⊟ 主导）", "conf": "C" },
    { "event_ref": "evt.demo.m003", "verb": "封存", "brief": "归于沉寂（原创虚构转述）", "conf": "C" }
  ],
  "holders": [{ "person_ref": "E-P-0401", "verb": "转移", "edge_ref": "edge.demo.007", "conf": "C" }],
  "status": { "value": "下落不明", "basis_event": "evt.demo.m003" },
  "locations": ["E-L-0002"],
  "brief": "（本卡整体为演示虚构：以某剑谱式占位示意秘籍卡结构——载体与所载武功分离、争夺事件链以物件域事件为骨架驱动叙事、与武功卡双向互指。演示数据非发布内容，不得与真实原著内容混用。）"
}
```

## 2.6 来源覆盖核对表（提示词 3.1 总表逐行落位，无一行遗漏）

| 3.1 总表行（数据→来源） | 落点字段 | 落在哪张卡 |
|---|---|---|
| 规范名/别名（surface/type/canonical/refs）｜01g+#7 | name.canonical / aliases | 全卡（人物卡绰号组为主） |
| 双层 canonical＋active_books/first_appearance｜#7 | meta 之上的全卡跨书字段（4.2，`active_books`=[book]；`first_appearance`={book,loc_r}） | 全卡统一 |
| 三层谓词总表（师承/结义/配偶/任职/转移/传授/掌握…）｜#6 | faction_history/teachers/disciples/kinship/romance/lineage/inheritance_chain/holders/branch_alliance | 人物/门派/武功/秘籍 |
| 辈分推导（师祖/师叔/同门）｜#6 双树 | seniority | 人物卡 |
| 事件字段总表（六域＋五状态＋时间槽位）｜#4a+#2 | timeline/provenance/chain 事件环/ending/life_events/status.basis_event | 门派/秘籍/兵器/人物 |
| 时点键与年龄锚｜#5 | life_events 排序 / age_anchor / lineage 任期 | 人物/门派 |
| 五棵分类树叶子｜#8 | identity_tags / faction_type / category / hierarchy.system / kind（对齐） | 人物/门派/武功/兵器 |
| gazetteer 双图层｜#10 | strongholds / locations / chain[].loc_r 回填 / forge.place_ref | 门派/秘籍/兵器 |
| 神兵表 chain（verb/persons/book/loc/conf）｜既有资产 | chain（直接投影）／holders（秘籍如入宝物类可复用） | 兵器卡（秘籍卡条件复用） |
| 招式表（parent_art/used_by/conf）｜既有资产 | moves / practitioners / hierarchy | 武功卡 |
| 常识与设定一致性评级｜#11 | meta.confidence 聚合（A–E；受 01g 状态上限约束） | 全卡统一 |

## 2.7 边界案例裁决（种子集八条，逐一可执行）

1. **无门派散修**：区分两种缺省——**信息缺失**记 `faction_history=[]`（页面显示"未明示"）；**确认无所属**（散修）记 `faction_history=[]`＋identity_tags 含"散修"叶（或 faction_history 记 `{"role":"散修","edge_ref":null}`），页面显示"散修（无所属）"。绝不虚构门派（K5）。
2. **改名人物（岳鸣珂/晦明禅师）**：一个实体一张卡；canonical 取 #7 双层 canonical 的定名，旧名入 `aliases(type=旧名)`；卡内一切引用指向同一实体 ID，页面上旧名可检索（别名索引来自 01g+#7）。
3. **灭派后的门派卡**：status 记"已灭"＋basis_event 指向灭派事件；卡不删除，门派页以存续状态呈现。
4. **无名兵器**：默认不建卡；仅当它进入 chain（持有/转移/毁损）或有生命周期叙事用途时，按 01g"无名实例粒度"以描述性 ID 建卡，canonical 用概括称谓并降可信。
5. **秘籍与武功互指**：秘籍卡.content_arts → 武功卡；武功卡.recorded_in → 秘籍卡；**双向必须同时建**（K12）；互指是"载体/技术"分层，不是同一实体。
6. **传闻中的武功**：inheritance_chain 条目降可信（孤证传闻按 #4a 可靠性矩阵降级），meta.confidence 随承重字段聚合下降；页面加"传闻"角标，不得按已证实传人链渲染。
7. **卡片聚合**：见 3.4 组装规则——页面=主卡＋子 SKU 引用，子 SKU 不复制主卡字段。
8. **演示数据与发布数据隔离**：所有示例 JSON 携带 `demo:true/demo_note`；发布加载器在 7.1 第 9 步拒绝 demo 卡；演示秘籍卡 publish_state 恒为 blocked。

---

# 三、三类 SKU 实例化（Q2）

## 3.1 Factual SKU（事实单元，200–500 字）

| 实例 | 内容 | 字段来源 |
|---|---|---|
| 人物小传 | 单人物客观生平概述 | 即人物卡 brief（结构化字段的转述底稿） |
| 门派简介 | 单门派客观概述 | 即门派卡 brief |
| 武功说明 | 单武功客观说明 | 即武功卡 brief |

> Factual SKU 与五卡的关系：五卡本体就是 Factual 事实单元的"卡片化"；brief 是其叙事投影。粒度同 08a：单实体级别、200–500 字、含核心属性与关键关系。

## 3.2 Procedural SKU（程序性知识，300–800 字；武侠三例）

Procedural 的 steps 是**原创命题**（01g §9.9 第②项），案例必须回指 #6 关系边与 #4a 事件；严禁把原文口诀/门规条文搬上卡（6.2 R5）。以下三例均为**演示型**（步骤为原创归纳，非作品记载；不作为作品证据）：

**例 P-1 门派规矩：《收徒规程（演示型）》**
- 背景：门派传承的第一道关口，决定人员质量与门风延续。
- 步骤（原创归纳）：投帖引荐 → 考察心性出身 → 引荐人担保 → 拜祖师行礼 → 授入门武功并载入门墙名录。
- 案例：演示条目——卓一航列入武当门墙（回指 #6 师承边＋#4a 拜师事件）。
- 效果/复核：解释门派人才来源；与门派卡 timeline 互引。

**例 P-2 武功修炼法门：《内功筑基次第（演示型）》**
- 背景：内功类武功的通用修习程序，是武功卡 hierarchy 心法层的过程面。
- 步骤（原创归纳）：正身调息 → 行气循经脉次第 → 通周天 → 内外功配合 → 逐层进境并防走火。
- 案例：演示条目——练功突破事件（#4a 习得域；时间跨度记偏移槽位）。
- 效果/复核：支撑武功卡"修炼条件"区；与 #11 主线设定（内力法则）对表。

**例 P-3 江湖礼数：《拜山投帖之礼（演示型）》**
- 背景：拜山是江湖冲突的高发场景，礼数是冲突的降级装置。
- 步骤（原创归纳）：山门递帖 → 通名报号亮明来意 → 守门人通报 → 见礼或约比武 → 事后回帖。
- 案例：演示条目——某拜山事件（#4a 事件回指）。
- 效果/复核：解释大量"先礼后兵"叙事；为说书人专栏提供分析单元。

## 3.3 Relational SKU（关系单元）：X 与 Y 的恩怨始末

- 定义：以一对实体（或多角关系）为中心的专题单元——引用 #6 关系边作骨架、#4a 关联事件作血肉、末段给原创评述（200–600 字）。
- 结构：`center_pair`（实体引用）＋`edges`（#6 谓词边列表）＋`event_chain`（#4a 事件引用，链序用事件链槽位）＋`commentary`（原创分析）。
- 示例（演示数据非发布内容）：

```json
{
  "meta": {
    "stable_id": "sku.rel.demo-lian-zhuo",
    "entity_ref": null,
    "card_type": "relational",
    "proposition": "练霓裳与卓一航的恩怨始末：身份对立压倒私人情义的关系悲剧",
    "supported_by": {
      "entities": ["E-P-0101", "E-P-0102"],
      "relations": ["edge.demo.004", "edge.demo.008"],
      "events": ["evt.demo.001", "evt.demo.002", "evt.demo.003"]
    },
    "sources": ["#6:edge.demo.004/008", "#4a:evt.demo.001-003"],
    "confidence": "B",
    "data_version": "2026-11-03.01",
    "rule_version": "sku-card@0.3-draft+rel-verbs@v1+event-fields@v1",
    "method": "关系边汇聚＋事件链对齐＋原创评述",
    "denominator": null,
    "publish_state": "draft",
    "demo": true,
    "demo_note": "演示数据非发布内容——仅示意 Schema，禁止直接上线"
  },
  "center_pair": ["E-P-0101", "E-P-0102"],
  "edges": [
    { "verb": "情缘", "edge_ref": "edge.demo.004", "conf": "A" },
    { "verb": "敌对", "edge_ref": "edge.demo.008", "conf": "B" }
  ],
  "event_chain": [
    { "event_ref": "evt.demo.001", "stage": "结识（原创转述）" },
    { "event_ref": "evt.demo.002", "stage": "情变白头（原创转述）" },
    { "event_ref": "evt.demo.003", "stage": "天山了断（原创转述）" }
  ],
  "commentary": "（原创评述：身份对立压倒私人情义，是本组关系的悲剧机制——此为分析性命题，可复跑核对事件链。演示数据非发布内容）"
}
```

## 3.4 三类与五卡的映射：卡片聚合结构

| 页面 | 主卡 | 组入的子 SKU | 组装规则 |
|---|---|---|---|
| 人物档案页 | 人物卡 | Factual 小传（并入 brief）；Relational SKU（恩怨/师承专题，relational_sku_refs）；生平时间线（#4a 投影） | 主卡唯一；子 SKU 只引用不改写；路由用实体 slug |
| 门派页 | 门派卡 | 掌门谱系（#6 任职边投影）；兴衰事件链（timeline）；分支/敌对（branch_alliance） | 同上 |
| 武功词条页 | 武功卡 | 传人链（inheritance_chain）；招式列表（招式表投影）；载于秘籍内嵌摘要（recorded_in → 秘籍卡摘要块） | 秘籍摘要只显示谱名＋链接，不带秘籍正文 |
| 神兵谱（列表）/ 单兵器页 | 兵器卡列表 / 兵器卡 | 持有链事件（chain）；锻造事件（forge） | 列表页字段：canonical/kind/grade/active_books |
| 秘籍页 | 秘籍卡 | 争夺事件链（provenance）；content_arts 武功卡内嵌摘要 | 同武功页对称规则 |
| 游戏卡（14 个） | 五卡衍生视图 | 抽卡/对战/每日挑战属性 | 另立命名空间 game.*，必须携带 derive_from 指回卡 ID（4.3） |
| 说书人专栏 | 章级 SKU（第五章） | eureka/mapping/facts | 章级 facts 合并入卡后以卡为准 |

---

# 四、粒度与统一 Schema（Q3）

## 4.1 粒度标准与"概要＋详情"分层裁决

| SKU 类 | 粒度标准 | 来源 |
|---|---|---|
| Factual | 200–500 字，单实体级 | 08a §4.1 沿用 |
| Procedural | 300–800 字，含背景/步骤/案例/效果 | 08a §4.2 沿用 |
| Relational | 以实体为中心的关系网＋200–600 字说明 | 08a §4.3 武侠化 |
| 卡面单字段上限 | ≤200 字（brief 与明细数组除外） | 本技能新增 |

**武侠调整（裁决）**：门派兴衰、人物生平、长持有链天然超长——采用**"概要＋详情"两层**：

- 卡面层：timeline/provenance/chain 只留**条目引用**（event_ref/edge_ref）＋一行式转述，brief ≤500 字；
- 详情层：超长内容拆为**事件 SKU 序列**（#4a 事件为最小件）或 Relational 专题，卡上以数组引用；
- 禁止把 3,000 字年表塞进 brief（K8）；详情层条目各自带 #5 时点键排序。

## 4.2 跨书字段统一 Schema（#7 已定版格式，全卡通用）

#7 定版：`active_books` 为 `[book]`（由系列身份表 members 聚合的**派生字段**，无排序契约）；`first_appearance` 为 `{book, loc_r}`（**编年 earliest，非出版序**；loc_r=02ab 机锚）。卡片**只引用、不重算、不自造 status 维度**（K6）：

```json
"active_books": ["白发魔女传", "七剑下天山"],
"first_appearance": { "book": "白发魔女传", "loc_r": "{作品ID}#pn-r3.1" }
```

- 值一律取自 #7 登记层派生输出；卡片不得自造 primary/supporting 之类的地位维度，也不得自加"按时间排序"之类 #7 没有的契约。
- `loc_r` 用 02ab 定版的机器锚点格式 `{作品ID}#pn-r{N}.{X}[.{Y}]`，只存指针不存文本；锚点归属 02a/02b 章回结构层（04f 是动词触发词层，与回锚无关）。

## 4.3 卡片 ID 裁决：投影制（卡＝实体的页面投影；双稿同判）

- **裁决**：采用投影制。卡不设独立主键空间，`stable_id = "card." + card_type + "." + 实体 slug`，与实体 ID 构成确定性可逆映射；登记层唯一主键仍是 01g 实体 ID（不透明序号，E-{类型码}-{序号} 式，不随改名变化）。
- **理由**：前端路由 `/characters/[slug]` 等由实体表直接生成 Astro collection；避免双 ID 对账与回链漂移。v2 亦裁决投影制（双稿同判），但其"卡 ID 加前缀、实体 ID 自造中文格式"的实现不采——实体 ID 必须是登记层既有主键，卡 ID 派生自实体 slug 而非另造实体格式。
- **三条规则**：
  1. 关系边、事件永远引用**实体 ID**；卡上引用他人一律写实体 ID，不写中文名（K4）。
  2. 卡 ID 只出现在 `meta.stable_id`，不进入任何关系/事件字段。
  3. 衍生视图（游戏卡、每日挑战）另立命名空间 `game.*`，必须携带 `derive_from` 指回卡 ID。
- **对照方案**（独立卡 ID 制）不采用，理由记入附录 B 备查；中文规范名→slug 的转写规则待定版（附录 B）。

---

# 五、章级 v2 武侠化（Q4）

## 5.1 08e §8.1 四件套的武侠对应

| 08e 四件套 | 武侠对应 | 落位 |
|---|---|---|
| README.md | 章级导览：本章出场实体清单（#7/01g）＋一句话章旨（原创）＋统计快照（含分母） | 说书人专栏每章页 |
| eureka.md | 跨领域洞察：武学体系规律、江湖生态规律等原创分析 | 专栏洞察条目 |
| mapping.md | 章节↔实体映射：r{N} 锚点↔实体/事件 ID 出场表 | 章页"出场人物/事件"区 |
| facts/ | 章级事实清单：待并入五卡的 Factual 草稿 | 专栏事实区＋卡片生成原料 |

章级 SKU 独立命名空间 `chap.{作品ID}.r{N}.*`，其 facts 并入五卡后以卡为准。

## 5.2 eureka 武侠化定义与 4 个候选

**定义**：eureka＝跨领域洞察——不是"某人使过某剑"（事实），而是"数据背后的机制"：必须非显性、有机制、可验证（给出统计方法与分母）、可跨书/跨域连接（08e 附录 C 检验表沿用）。

**候选一（武学体系）：命名即性格——梁书武功命名法与门派气质的系统对应**
- 现象：名门正派武功命名工整（数目字＋堂皇字眼，如"七十二手连环剑"式），邪派武功命名诡奇。
- 机制：命名是门派意识形态的外化——正派重法度、邪派重速成，命名法是低成本的气质标签。
- 验证：对全武功卡 category（#8）× 门派类型（#8 门派树）做命名模式交叉统计；分母＝全武功卡数，剔除无名武功。
- 呈现：专栏洞察条目；关联 #9 词表（命名套语表）。

**候选二（江湖生态）：镖局与王朝周期的共振——体制外武力在王朝衰落期的生存模式**
- 现象：镖局类组织活跃期多对应政权疲弱的纪年段。
- 机制：官府控制力下降 → 私人护送武力需求上升 → 镖局繁荣；政权稳固期被官驿与捕快替代。
- 验证：镖局实体卡 active_books 分布 × 各书纪年背景（#5 时间锚）统计；分母＝全镖局实体＋全书纪年跨度。
- 呈现：专栏生态观察；关联 #11 主线设定（时代背景层）。

**候选三（叙事结构）：秘籍争夺是"内容-载体分离"驱动的冲突引擎**
- 现象：争夺目标是载体（谱），价值在内容（武功）；谱毁/藏即冲突终点（#4a 夺宝争谱事件链大量出现）。
- 机制：武功内容不可独占、秘籍载体可独占——冲突向载体收敛；"毁谱"是消灭冲突源的叙事手段。
- 验证：全秘籍卡 provenance 事件链统计（分母＝全秘籍卡争夺事件数，⊟域）；对比"练成后毁谱"事件占比。
- 呈现：专栏叙事学条目；直接复用秘籍卡数据（卡片的 eureka 即卡片数据的增值分析）。

**候选四（武学传承，自 v2 回收）：高频传承的武功代际弱化假说**
- 现象（假说）：传承环数多的武功，其后代持有者的战绩表现呈弱化趋势。
- 机制（假说）：完整继承依赖天赋与际遇，代际传递天然衰减；门派以"镇派"名义维持体系但个体上限下降。
- 验证：以武功卡 inheritance_chain 环数 × 传人战绩事件统计（#4a）交叉；分母＝有明确传人链的武功卡数与其传人事件数；**先验证后立论**——若数据不支持即废弃，不得作为定论发布。
- 呈现：专栏武学观察；与武功卡 grade（战绩统计）联动。

## 5.3 mapping（章节↔实体映射）武侠字段

| 字段 | 类型 | 来源 |
|---|---|---|
| book / chapter | string | 01g 书目规范名＋回号 r{N} |
| anchor | string | 02a/02b 结构层（`{作品ID}#pn-r{N}.{X}` 机锚） |
| entities[] | array[ent_ref] | 01g 登记层（本章出场实体） |
| events[] | array[evt_ref] | #4a（本章事件） |
| role | enum | 出场强度标记——**词表未定版**（不得伪托 #7），候选与归属见附录 B |

JSON 演示（演示数据非发布内容）：

```json
{
  "book": "白发魔女传",
  "chapter": "r3",
  "anchor": "{作品ID}#pn-r3.1",
  "entities": ["E-P-0101", "E-F-0007"],
  "events": ["evt.demo.001"],
  "role": "主出场"
}
```

## 5.4 facts（事实清单）武侠字段

| 字段 | 类型 | 来源 |
|---|---|---|
| fact_id | string | 章级命名空间 chap.* |
| statement | string ≤200 字 | 原创转述（非原文） |
| anchors | array | 02a/02b r{N} 机锚（指针不携带文本） |
| entities / relations / events | array | 回指 01g/#6/#4a |
| confidence | enum A–E | #11 |
| merge_target | string | 拟并入的卡 ID（投影制可逆映射） |

JSON 演示（演示数据非发布内容）：

```json
{
  "fact_id": "chap.demo.r3-f001",
  "statement": "练霓裳初入场时以玉罗刹之名行事，与武当弟子发生冲突（原创转述）",
  "anchors": ["{作品ID}#pn-r3.4"],
  "entities": ["E-P-0101"],
  "relations": [],
  "events": ["evt.demo.001"],
  "confidence": "B",
  "merge_target": "card.person.demo-lian-nichang"
}
```

## 5.5 章级 SKU 与 02a/02b 结构层（r{N} 回锚）的挂接

- 章级 SKU 一切定位用 r{N} 机锚；卡 sources 可回指 loc_r（不含正文，符合 01g §9.10"不含正文的定位"）。
- 结构层重排（回号变更）→ 章级 SKU 重算 → 受影响卡重算（7.3 变更传播）。

---

# 六、发布边界与可信状态（Q5）

## 6.1 字段可发布性三档审查（对齐 01g §9.10 允许/禁止清单）

| 档 | 内容 | 五卡落点 |
|---|---|---|
| A 直接发布 | 经审核的结构化实体属性、关系/事件三元组引用、统计（含分母）、原创转述与原创分析、不含正文的定位 | 全部结构化字段；brief/评述类；grade_basis |
| B 脱敏后发布 | 引用型内容：兵器铭文、门规条文、口诀诗句、书信遗言——卡面只留"概括语＋回锚" | 各卡的引文性描述；绰号出处说明 |
| C 禁止上卡 | 原文正文、标注正文、可逐步还原正文的连续片段数据、大量逐字证据摘录伪装成图谱、尚未核实却表述为确定事实的问答 | **无字段允许落 C 档内容**——不存在"短原文可发布"的档位 |

## 6.2 原文片段脱敏审查规则（成文）

- **R1**：卡面正文不得出现与原文连续重合 ≥10 字的片段（阈值待拍板，附录 B）；n-gram 比对由复核 agent 执行。
- **R2**：引文型内容一律"概括语＋回锚"；回锚是 ID 指针（book/chapter/`#pn-r{N}.{X}`），不含文本。
- **R3**：专名（人名/武功名/地名/书名/绰号）可发布，不算片段。
- **R4**：未过审不得置 `publish_state=approved`；演示卡永远 blocked。
- **R5**：Procedural 的 steps 若源自原文口诀，必须改写为原创归纳并回锚（否则 K2）。

## 6.3 卡级可信聚合裁决

- **裁决**：卡级 confidence ＝ **承重字段可信的最低值**；参考字段只降自身、不拖累卡级。（否决"全字段一票最低"的粗聚合——别名拼写变体之类参考字段不应拖垮整卡。）
- 承重/参考划分（初版，定版见附录 B）：人物卡承重＝师承/门派履历/结局/绰号组归属；门派卡承重＝谱系/存续状态/据点；武功卡承重＝传人链/层级归属；兵器卡承重＝持有链/下落；秘籍卡承重＝content_arts/争夺链。别名拼写变体、辈分细节等为参考字段。
- 评级用 #11 的 A–E 五级；聚合只在本技能做，评级判定以 #11 定版为准。**#11 硬约束随聚合带入**：登记层"来源声称"级记载折算最高 C；"未知"≠E（未知按 01g 未知原则处理，缺省态不降级为 E）。
- **示例**：传闻中的武功——传人链仅孤证 → 该字段 C → 武功卡卡级 C，页面显示"传闻"角标（2.7 条 6）。

## 6.4 版本与规则版本声明（消费 #9 词表版本协议）

- `rule_version` 形如 `sku-card@0.3-draft + rel-verbs@v1 + event-fields@v1`：主 Schema 版＋所引词表/谓词总表/触发词表版本。
- `data_version` 每次重算递增（日期.序号）。
- #9 词表升级 → 版本比对 → 受影响字段重算 → 卡级可信重聚合 → data_version 递增（7.3）。

---

# 七、工作流程

## 7.1 卡片生成 agent 操作序（九步）

1. **锁版本**：记录 #9 词表与各管线 rule_version。
2. **取实体**：从 01g 登记层取实体与别名（canonical/绰号组）。
3. **拉关系**：#6 谓词边（含双树辈分推导）。
4. **拉事件**：#4a 事件流（按卡类型取域）＋#5 时点键排序。
5. **拉专项**：神兵表 chain / 招式表 parent_art / #10 据点 / #8 类型叶子 / #7 跨书派生字段。
6. **组装字段**：按 Schema 填充；无来源不上卡、未知不强填；关系字段去重（K13）。
7. **粒度裁决**：超限内容走"概要＋详情"分层（4.1）；事件条目按 #5 时点键排序（K14）。
8. **可信聚合＋脱敏审查**：按 6.2/6.3 执行。
9. **落元数据**：九项最低字段齐备＋demo 隔离检查 → 登记 publish_state。

## 7.2 复核 agent 操作序（五查）

1. **来源回查**：抽样字段逐个回溯到管线产出。
2. **脱敏抽检**：卡面文本对原文做连续重合检测（R1）。
3. **粒度抽检**：brief 字数、单字段上限、数组引用式（不塞全文）。
4. **元数据完备性**：九项最低字段＋投影制 ID＋demo 标记。
5. **对账上游**：与 2.6 核对表逐行核对（来源标注是否指向正确管线）。

## 7.3 变更传播

- 上游更新（实体合并/事件新增/关系边修订）→ 按"来源字段倒排索引"找受影响卡 → 重算 → data_version 递增。
- #9 词表升级 → 按 6.4；02ab 结构层回号变更 → 按 5.5。
- #7 归并/拆分 → active_books/first_appearance 派生重算 → 消费端（人物档案/宇宙编年史/搜索索引）刷新。
- 卡级 confidence 变化 → 页面角标与游戏卡引用同步刷新。

---

# 八、Agent 提示词

### SYSTEM（卡片生成 agent）

```
你是武侠知识库的卡片生成器。你只做一件事：把登记层与各管线的产出按
SKILL_SKU卡片_武侠版 的 Schema 组装成卡。四条红线：
1) 无来源的字段不上卡——每个字段必须能指回来源管线；
2) 未知不强填——缺省用 []/null/"未明示"，绝不虚构；
3) 卡面不出现原文片段——引文型内容只写概括语＋回锚；
4) 一切引用写实体 ID，卡 ID 不进入关系字段（投影制）。
输出：符合 Schema 的 JSON，含 meta 九项最低字段（含 proposition）与 demo 隔离标记。
```

### TASK（逐卡操作序）

```
按 7.1 九步执行。开始前先报告：本次 rule_version 与词表版本。
第 2–5 步每步列出实际拉到的数据条数；第 6 步逐字段标注来源并声明去重结果；
第 7 步声明是否触发分层与排序依据；第 8 步给出承重字段可信清单与聚合结果；
第 9 步输出最终 JSON 并自证九项最低字段齐备。
```

### REFLECTION（自检清单）

```
1. 是否存在无来源字段？
2. 是否有"未明示"被强填成具体值？
3. 卡面是否残留连续 ≥10 字原文？
4. 关系字段是否全部指向实体 ID（而非中文名）？
5. 统计字段是否都带口径与分母？
6. active_books/first_appearance 是否原样引用 #7 派生输出（无自造 status/排序）？
7. rule_version 是否含词表版本？
8. meta.proposition 是否就位且与卡面结构化字段一致？
9. demo 标记是否就位且演示条目未混入正式库？
任一不通过：回到对应步骤修正后再输出。
```

### few-shot（节选演示）

```
输入（登记层片段）：
  E-P-0102｜别名：卓一航(本名)
  edge.demo.006：紫阳道长 --传授--> 卓一航｜客体=七十二手连环剑｜conf=A
输出（人物卡字段片段）：
  "teachers": [{ "person_ref": "E-P-0201", "edge_ref": "edge.demo.006", "conf": "A" }],
  "arts": [{ "art_ref": "E-A-0021", "verb": "掌握", "conf": "A" }]
禁例：不得写"卓一航师从紫阳道长尽得真传"这类无边依据的修饰（K7）；
     不得把客体武功写成"卓一航的成名绝技"这种评价（grade 需战绩统计支撑）。
```

---

# 九、错误模式库（K 系列）

| 编号 | 错误模式 | 症状 | 后果 | 纠正 |
|---|---|---|---|---|
| K1 | 无来源字段上卡 | 字段值指不回任何管线 | 页面数据不可信、无法复核 | 按 2.6 核对表逐行验证，指不回即删 |
| K2 | 原文片段未脱敏 | 卡面残留连续原文/口诀/门规条文 | 版权违规（01g §9.10） | R1–R5 脱敏审查，改概括语＋回锚 |
| K3 | 演示数据混入发布 | demo:true 卡进入发布库 | 虚假设定上线 | 加载器拒绝 demo 卡；演示秘籍卡 publish_state 恒 blocked |
| K4 | 卡实 ID 混用 | 关系边/事件指向 card.* 或写中文名而非实体 ID | 图谱断链、对账失败 | 投影制三规则（4.3） |
| K5 | 未知强填 | "未明示"被写成具体门派/结局 | 设定造假 | 缺省纪律（1.4 条 3）；散修、创派者未明等缺省态 |
| K6 | 跨书字段私自重算 | 卡上重算 active_books、自造 status/排序契约 | 与 #7 派生输出漂移 | 只引用不重算（4.2） |
| K7 | 谓词边小说化 | 把关系边改写成无边依据的叙事断言 | 原创分析变二次创作事实 | 边即边、评述归评述（few-shot 禁例） |
| K8 | 粒度超限不分层 | 3,000 字年表塞进 brief | 页面渲染失控 | 概要＋详情分层（4.1） |
| K9 | 可信聚合虚高 | 按最高字段报卡级可信 | 低可信内容伪装可靠 | 承重字段最低值裁决（6.3） |
| K10 | 统计无分母 | "出现最多/密度"缺口径与分母，或分母只写"全书" | 结论不可复跑（01g §9.9） | 统计必带"对象＋谓词条件＋语料范围"三要素（1.4 条 6） |
| K11 | 版本漂移 | rule_version 缺词表版本或过期 | 词表升级后字段失配 | 版本声明（6.4）＋锁版本步骤 |
| K12 | 互指断裂 | 秘籍卡↔武功卡只建单向 | 页面回链缺失 | 双向必须同时建（2.7 条 5） |
| K13 | 关系字段重复未去重 | 同一关系边在卡内多次出现（多来源重复拉取未合并） | 数据冗余、页面重复渲染 | 去重检查（7.1 第 6 步；按 edge_ref 合并、保留最高 conf） |
| K14 | 事件时序未锚 | timeline/life_events 条目无时点键、排序凭叙述印象 | 生平叙事混乱、时间线渲染错序 | 每条事件带 #5 时点键，无锚条目排后并标"时点未锚" |

> 体量注记：K 系列 14 条，超合同 8–12 上限 2 条——系"亮点全回收"纪律的有意偏差（docs/10 R16–R18、docs/15 C13 先例），K13/K14 自 v2 错误模式库回收。

---

# 十、检查清单

### 前（生成前）

- [ ] 上游契约版本锁定：01g/02ab/#4a/#5/#6/#7/#8/#9/#10/#11 与神兵表、招式表版本号记录在案。
- [ ] 实体在登记层存在且 canonical 已定（改名人物用 #7 定名）。
- [ ] 卡类型判定正确（人物/门派/武功/兵器/秘籍；无名实例按 2.7 条 4 裁决）。

### 中（生成中）

- [ ] 每个字段可指回 2.6 核对表的来源行。
- [ ] 缺省态使用正确（[]/null/"未明示"；"确认无所属"与"信息缺失"分立）。
- [ ] 统计字段带口径与分母（三要素）。
- [ ] 超长内容已分层，brief 在 200–500 字。
- [ ] 双向互指已同时建立；关系字段已去重；事件条目已按 #5 时点键排序。

### 后（生成后）

- [ ] 九项最低字段齐备（含 proposition）且 rule_version 含词表版本。
- [ ] 脱敏审查通过（R1 n-gram 比对），publish_state 合规；demo 卡未进入发布库。
- [ ] 卡级 confidence 按承重字段最低值聚合（受 01g 状态上限约束，未知≠E）。
- [ ] 跨书字段原样引用 #7（active_books=[book]／first_appearance={book,loc_r}）。
- [ ] 路由可由实体 slug 生成（投影制验证）；卡上引用全部为实体 ID。

---

# 十一、FAQ

**Q1：卡和实体到底是什么关系？**
投影制：卡是实体的页面投影，卡 ID 由实体 ID（slug）确定性派生，可逆；主键只有实体 ID 一套（4.3）。实体 ID 用 01g 不透明序号，不随改名变化。

**Q2：为什么没有"事件卡"这一类？**
事件以 #4a 事件流为最小件，卡上以引用呈现；事件专题由 Relational SKU 与时间线承载。是否增设第六类事件卡记入附录 B。

**Q3：无名兵器到底建不建卡？**
默认不建；进入 chain 或有生命周期叙事用途时按 01g"无名实例粒度"以描述性 ID 建（2.7 条 4）。

**Q4：传闻中的武功怎么上卡？**
传人链照记但条目降可信，卡级可信按承重字段最低值聚合下降，页面加"传闻"角标（2.7 条 6、6.3）。

**Q5：brief 能直接抄原文吗？**
不能。brief 是原创转述（01g §9.9 第②项），需通过 R1 连续重合检测；原文只允许以回锚指针存在。不存在"50 字以内可发布"的豁免档（6.1 C 档）。

**Q6：品级 grade 谁说了算？**
战绩事件统计支撑 grade_basis，写法对齐神兵表（实测词表：神兵/利器，grade_basis 为出处标注式）；没有统计就不评（null），参考字段不承重。武功卡/秘籍卡是否扩充枚举见附录 B。

**Q7：演示 JSON 能当种子数据用吗？**
不能。demo:true 与 publish_state 非 approved 双保险；发布加载器直接拒绝（K3）。演示卡里的占位 ID 与演示条目一律不得混入正式库。

**Q8：active_books 有分歧听谁的？**
听 #7 派生输出的。卡片只引用不重算，不自造 status/排序契约（K6）；分歧走 #7 的 conflicts 双记区流程。

**Q9：无门派散修的门派字段填什么？**
分两种缺省：确认无所属（散修）记 identity_tags 含"散修"叶，页面显示"散修（无所属）"；信息缺失记 faction_history=[]，页面显示"未明示"。两种都不虚构门派（2.7 条 1）。

**Q10：一张卡字段越多越好吗？**
不。承重/参考分层，无来源的字段宁缺勿滥；字段数量由来源决定，不由页面野心决定。

**Q11：章级 facts 和五卡重复怎么办？**
章级 facts 是草稿与局部视角；并入卡后以卡为准，章页只显示"已并入"状态（5.1）。

**Q12：游戏卡算不算第六类卡？**
不算。游戏卡是五卡的衍生视图，命名空间 game.*，必须带 derive_from（4.3）。

**Q13：词表升级后已发布的卡要重算吗？**
要。按 rule_version 比对，受影响字段重算并递增 data_version，未重算的卡标记过期（6.4、7.3）。

---

# 十二、相关文档（全部已定版技能与资产）

| 文档 | 为本技能提供 |
|---|---|
| SKILL_01g 标注符号集合原则 | 实体登记层（不透明序号 ID）、别名表、§9.9 SKU 最低字段、§9.10 发布边界、无名实例粒度、FAQ Q7/Q8 内容-技术分层 |
| SKILL_02a/02b 章回结构与韵文处理 | r{N} 回锚与 `#pn-r{N}.{X}` 机锚格式（全部 loc_r/anchor 的锚点来源） |
| SKILL_04a 事件识别 | 事件字段总表（六域⊞⊠⊡⊟▣■＋五状态＋时间槽位）、事件链槽位（chain_type/prev/next）、夺宝争谱类型、可靠性矩阵 |
| SKILL_04f 动词标注 | 六域触发词（timeline/provenance 的事件触发依据） |
| SKILL_时间体系（#5） | 时点键、年龄锚、故事时间槽位 |
| SKILL_关系体系（#6） | 三层谓词总表、双树辈分推导 |
| SKILL_跨书治理（#7） | 双层 canonical、active_books=[book]／first_appearance={book,loc_r} 派生字段、conflicts 双记区 |
| SKILL_分类树五件套（#8） | 身份/门派类型/武功品类等五棵树叶子 |
| SKILL_词表体系规划（#9） | 词表版本协议（rule_version 消费方） |
| SKILL_地名gazetteer（#10） | 双图层地点引用（据点/发生地） |
| SKILL_常识与设定一致性（#11） | A–E 设定一致性评级（卡级可信聚合输入；来源声称最高 C、未知≠E） |
| 既有资产：神兵表（kb/神兵表.json） | canonical/kind/grade/grade_basis/chain（实测 226 件；兵器卡现状基础） |
| 既有资产：招式表 | parent_art/used_by/conf（武功卡现状基础） |
| 提示词 T12 | 本任务工单与 3.1 数据源映射总表 |
| docs/16 | 本件双稿对比分析与合并裁决记录 |

---

# 附录 A：与 08a/08e 差异对照表

| 维度 | 08a/08e 原设计 | 武侠版裁决 | 理由 |
|---|---|---|---|
| SKU 通用字段 | id/type/title/summary/tags/source/created/updated | 升级为统一元数据块：九项 01g §9.9 最低字段＋proposition＋投影制回指＋demo 隔离 | 管线可溯源与发布合规是武侠版硬约束 |
| Factual | 人物/事件/地点/制度卡 | 收敛为五卡（人物/门派/武功/兵器/秘籍）；事件不设卡、以引用呈现 | 页面清单决定卡类型（1.2 依赖表） |
| Procedural | 军事策略/治国方略等 | 门派规矩/修炼法门/江湖礼数三例（3.2，演示型） | 武侠领域实例化 |
| Relational | 关系图/因果链 | X 与 Y 恩怨始末专题（3.3） | 引用 #6/#4a，边＋事件＋评述三层 |
| 粒度 | 200–500 字（Factual） | 沿用＋"概要＋详情"分层裁决 | 门派兴衰/生平天然超长（4.1） |
| 08e 章级结构 | README/eureka/mapping/facts 四件套 | 结构沿用，字段武侠化（5.3/5.4）；eureka 定义为跨领域洞察并给四候选 | 五轮迭代法不引入：武侠按卡生产、按管线流水线更新 |
| 08e 洞察检验 | 非显性/有机制/可验证/跨时代 | 沿用，验证一律补"统计分母" | 01g §9.9 可复跑要求 |

# 附录 B：待拍板决策清单（10 项真开放）

1. **脱敏片段阈值**：R1 暂定连续 ≥10 字判为片段——需与 01g §9.10"可逐步还原正文的连续片段"口径对齐后定版。
2. **承重/参考字段清单**：6.3 初版划分需逐卡定版（尤其绰号组归属是否承重）。
3. **品级枚举扩充**：兵器 grade 实测词表=神兵/利器（未评 null）；武功卡/秘籍卡是否新增 grade 枚举（战绩统计维度）待定。
4. **存续状态枚举**：门派卡 status.value 的取值词表（兴盛/衰落/已灭/重建/未明示…）——来源管线归属（#4a 推导＋#8 树？）待定。
5. **是否增设事件卡（第六类）**：若问答页需要事件详情页再议。
6. **game.* 命名空间强制度**：derive_from 缺失是否直接 error 级 lint。
7. **brief 字数上限**：200–500（08a 标准）还是弹性 300–600，随试点数据定。
8. **章级 facts 并入卡的优先级**：按页面缺数程度排序，待试点章（建议《白发魔女传》）验证后定。
9. **stable_id slug 转写规则**：中文规范名→URL slug 的生成规则（拼音转写/音译/序号直用），影响路由与 SEO；定版后 4.3 的 stable_id 格式随之冻结。
10. **mapping.role 词表与秘籍 content_type**：出场强度标记是否设、由哪家管线产出（#7/#4a/本技能）；秘籍卡 content_type（武功秘籍/内功心法/兵法）是否设独立字段——两处词表均无既有定版落点，按"无来源不上卡"暂缓。

---

## 版本记录

- v0.3-draft（2026-11-03）：双稿合并定稿。骨架取 v1；统一元数据块补 meta.proposition（自 v2 回收，01g §9.9 ② 显式落点）、删 meta.canonical/aliases 双存；跨书字段对齐 #7 定版（active_books=[book]／first_appearance={book,loc_r}，双稿原格式均不合规，本轮修正）；可信状态维持 v1 承重/参考分层聚合并补 #11 上限约束（来源声称最高 C、未知≠E）；发布边界维持 v1 R1–R5（否决 v2"短原文可发布"档）；神兵表实测对账（grade=神兵/利器、kind 分布、游龙剑 chain 5:7/6:65/6:69＋资产注记）；回收 v2 亮点：散修"确认无所属/信息缺失"缺省分立、K13/K14 两条错误模式、mapping/facts JSON 演示、eureka 候选四；K 系列 12→14 条（超上限偏差已声明）；附录 B 收紧为 10 项真开放。
- v0.1-draft（2026-11-03）：v1 初稿（五类卡 Schema＋统一元数据块＋来源覆盖核对表＋边界案例裁决＋章级武侠化＋脱敏成文）。
