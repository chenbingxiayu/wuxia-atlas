---
name: skill-08a-wuxia
title: SKU 字段（五卡 Schema·字段来源·粒度分层·脱敏发布）
description: 武侠知识库 SKU 卡片体系的字段执行规范：五类卡片（人物/门派/武功/兵器/秘籍）的统一元数据块（九项最低字段）、各卡字段表与缺省态、字段来源映射（#7/#6/#4a/#5/#8/#10/神兵表/招式表/#11）、粒度标准与"概要＋详情"分层、投影制卡片 ID、字段可发布性三档与脱敏 R1-R5、卡级可信聚合与版本声明，以及生成/复核/变更传播工作流。当需要"建一张卡、某字段从哪来、缺省怎么填、能不能发布、卡级可信怎么算"时使用；SKU 设计总纲见 SKILL_SKU卡片（D12），N10 生成器待建。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 08a 武侠版：SKU 字段

> **上游声明**：本文是 D12 SKU 卡片（`SKILL_SKU卡片_武侠版.md`，v0.3-draft）的**字段执行件**：五卡 Schema、统一元数据块、粒度标准、发布边界与脱敏规则、K 系列错误模式由 D12 定版；本文只负责"字段怎么取、怎么填、怎么验、怎么发"。上游数据契约：`SKILL_跨书治理_武侠版.md`（D07 双层 canonical/active_books/first_appearance）、`SKILL_关系体系_武侠版.md`（D06 谓词边/双树）、`SKILL_04a_事件识别.md`（D03 事件字段/五状态）、`SKILL_时间体系_武侠版.md`（D05 时点键）、`SKILL_分类树五件套_武侠版.md`（D08 叶子）、`SKILL_地名gazetteer_武侠版.md`（D10 据点）、`SKILL_常识与设定一致性_武侠版.md`（D11 A-E 评级）、`SKILL_词表体系规划_武侠版.md`（D09 版本协议）。
> **移植依据**：`docs/05-管线技能与脚本逐项改造分析.md`（08a SKU 字段：五卡 schema/数据源映射/脱敏 R1-R5）；`docs/17` §2.5（S-08a ←D12）；`docs/50` §三（N10 `build_sku_cards` 依赖 N6+N7，尚未开工；`registry/sku/` 未建）。
> **核心原则**：**无来源不上卡，未知不强填，原文片段不上卡**。卡是实体在页面上的投影，不是二次创作；每个字段必须能指回上游管线，指不回就删。

---

## 一、技能定位与边界

### 1.1 工序位置（标注→页面最后一公里）

```text
01g 实体/别名 · D07 跨书 · D06 关系边/双树 · D03 事件 · D05 时点键 · D08 类型叶子 · D10 据点
        ↓ 拉取/组装
S-08a SKU 字段（本文）：五卡 Schema + 元数据 + 粒度分层 + 脱敏 + 可信聚合
        ↓
N10 build_sku_cards（待建）→ registry/sku/（待建）→ 页面/搜索/游戏卡消费
```

- **前置**：上游数据资产就绪（entities/relations/time/events/gazetteer/concordance）；D12 Schema 定版。
- **后继**：N10 生成器（待建）、W 组页面、搜索索引、游戏卡衍生视图。
- **现行事实（2026-11-05）**：N4/N5/N6/N7/N8/N9 已落地、`registry/` 含 entities/gazetteer/relations/time/crossover/consistency/intertext/acceptance/concordance；**N10 `build_sku_cards` 与 `registry/sku/` 尚未开工**（docs/50 §三：依赖已满足、下一波）。

### 1.2 本文做什么（六件事）

1. **元数据**：九项最低字段 + 实体回指 + demo 隔离（§三）；
2. **五卡字段**：人物/门派/武功/兵器/秘籍的字段表与缺省态（§四）；
3. **来源映射**：每个字段指回上游管线（§五）；
4. **粒度分层**：Factual/Procedural/Relational 与"概要＋详情"（§六）；
5. **发布与脱敏**：A/B/C 三档、R1-R5、卡级可信聚合（§七）；
6. **工作流**：生成九步/复核五查/变更传播（§八）。

### 1.3 本文不做什么（边界，越界即错）

- **不重定义五卡 Schema**：字段名/语义以 D12 §二为准；
- **不重算上游**：active_books/first_appearance 只引用 D07 派生输出；事件/关系只引用 ID（K6/K4）；
- **不携带原文片段**：卡面不得出现与原文连续重合 ≥10 字片段（R1）；引文一律"概括语＋回锚"；
- **不做评级**：卡级 confidence 只用 D11 A-E 聚合，不自行评级。

---

## 二、快速开始（八步生成序）

> 目标：为一批实体生成卡（N10 未建前为手工/半自动）。命令只读；写卡落 `registry/sku/`（待建）。

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
$env:PYTHONIOENCODING='utf-8'

# Step 1 锁版本：记录 #9 词表版本 + 各管线 rule_version
python -X utf8 scripts\wordlist_compiler.py --check

# Step 2 取实体与别名（01g 登记层）
python -X utf8 -c "import json;d=json.load(open('registry/entities.json',encoding='utf-8'));print(len(d['entities']),'entities')"

# Step 3 拉关系边（D06/N5）与双树辈分
python -X utf8 scripts\relation_validator.py --report

# Step 4 拉事件流（D03）与时点键（D05/N4）
python -X utf8 scripts\time_resolver_wuxia.py --report

# Step 5 拉专项：#10 据点（registry/gazetteer.json）/#8 叶子（N9）/#7 跨书派生字段
python -X utf8 -c "import json;d=json.load(open('registry/gazetteer.json',encoding='utf-8'));print(len(d['places']),'places')"

# Step 6 组装字段（§四/§五）：无来源不上卡、未知不强填、关系去重
# Step 7 粒度分层（§六）+ 脱敏审查（§七 R1-R5）+ 可信聚合（§七）
# Step 8 落元数据与发布状态（§三）；N10 落地后由其自动执行 Step 6-8
```

**判读口径**：Step 2 的 entities 数（约 452）与 Step 3/4/5 的产物版本是卡的"上游快照"；卡必须记录这些版本（`rule_version`），否则不可复现。

---

## 三、统一元数据块（全卡共用）

### 3.1 九项最低字段（01g §9.9 不可减，D12 §2.0）

| 字段 | 来源 | 说明 |
|---|---|---|
| `meta.stable_id` | 本技能派生（投影制） | `card.<card_type>.<实体 slug>` |
| `meta.entity_ref` | 01g 实体登记层主键 | 不透明序号 `E-{类型码}-{序号}` |
| `meta.card_type` | 本技能 | person/faction/art/artifact/manual |
| `meta.proposition` | 本技能 | 一句话命题（≤100 字，基于结构化字段归纳） |
| `meta.supported_by` | 01g/D06/D03 | {entities[],relations[],events[]}（一律 ID） |
| `meta.sources` | 全部来源管线 | 含 r{N}/loc_r 定位指针，不含正文 |
| `meta.confidence` | D11 A-E 聚合 | 承重字段最低值（§七） |
| `meta.data_version` | 本技能 | 日期.序号 |
| `meta.rule_version` | 本技能 + D09 协议 | 主 Schema 版＋词表版本 |

### 3.2 附加字段（本技能）

| 字段 | 说明 |
|---|---|
| `meta.method` / `meta.denominator` | 统计字段必填"方法＋分母"（K10） |
| `meta.publish_state` | draft/in-review/approved/blocked（01g §9.10） |
| `meta.demo` / `meta.demo_note` | 演示隔离（demo 卡永不 approved，K3） |

> **投影制 ID**（D12 §4.3）：卡不设独立主键空间；`stable_id` 由实体 slug 派生，登记层唯一主键仍是实体 ID；关系/事件字段一律引用实体 ID，不写 `card.*`、不写中文名（K4）。

---

## 四、五卡字段（摘要，全表见 D12 §2.1-§2.5）

### 4.1 人物卡（person）

`name.canonical` / `aliases`（绰号组） / `identity_tags`（#8 身份叶） / `faction_history`（门派履历：faction_ref/role/edge_ref/conf） / `seniority`（辈分） / `teachers`/`disciples`（师承边） / `kinship`（亲属/配偶/结义） / `romance`（情缘边） / `arts`（武功列表） / `life_events`（事件引用，按 D05 时点键排序） / `age_anchor` / `ending`（结局：type/event_ref/summary/conf） / `relational_sku_refs` / `brief`（200-500 字） / `meta`。

### 4.2 门派卡（faction）

`name`/`aliases` / `faction_type`（#8 势力叶） / `strongholds`（D10 据点，hq_of 反查） / `lineage`（传承谱系：师承边/继任） / `branch_alliance`（分支/结盟边） / `status`（存续：存续/隐世/已灭 + basis_event） / `members`（组织成员边） / `moves`/`arts`（武功/招式，经 used_by） / `timeline`（事件引用） / `meta`。

### 4.3 武功卡（art）

`name`/`aliases` / `category`（品类属性） / `hierarchy`（层级：心法/武功/招式/阵法 + system） / `parent_art`（父式外键） / `moves`（招式列表） / `practitioners`（掌握/传授边） / `inheritance_chain`（传人链） / `recorded_in`（秘籍卡互指，双向必建 K12） / `meta`。

### 4.4 兵器卡（artifact）

`name`/`aliases` / `kind`（兵器子型） / `chain`（神兵表持有/转移/毁损链投影：verb/persons/book/loc/conf） / `holders`（持有区间） / `forge.place_ref`（铸造地，D10 地点引用） / `grade_basis`（品级依据，原创分析） / `meta`。

### 4.5 秘籍卡（manual）

`name`/`aliases` / `content_arts`（内容武功，→武功卡互指） / `争夺链`（夺宝争谱事件链） / `holders` / `recorded_events` / `meta`。

### 4.6 缺省态纪律（D12 §1.4 条 3）

- 缺失即用约定缺省：空数组 `[]` / `null` / "未明示"；**不虚构**；
- "确认无所属"（散修）与"信息缺失"（未明门派）两种缺省态分开登记（D12 §2.7 条 1）；
- 统计字段必带分母（K10）；结局未知用 `{"type":"未明示"}`。

---

## 五、字段来源映射（D12 §2.6 核对表，逐行落位）

| 上游数据 | 落点字段 | 卡片 |
|---|---|---|
| 规范名/别名（01g+D07） | name.canonical / aliases | 全卡 |
| 双层 canonical + active_books/first_appearance（D07） | 全卡跨书字段（active_books=[book]；first_appearance={book,loc_r}） | 全卡 |
| 三层谓词总表（D06） | faction_history/teachers/disciples/kinship/romance/lineage/inheritance_chain/holders/branch_alliance | 人物/门派/武功/秘籍 |
| 辈分推导（D06 双树） | seniority | 人物卡 |
| 事件字段总表（D03+D05） | timeline/provenance/chain/ending/life_events/status.basis_event | 门派/秘籍/兵器/人物 |
| 时点键与年龄锚（D05/N4） | life_events 排序 / age_anchor / lineage 任期 | 人物/门派 |
| 五树叶子（D08） | identity_tags/faction_type/category/hierarchy.system/kind | 人物/门派/武功/兵器 |
| gazetteer 双图层（D10） | strongholds/locations/chain[].loc_r/forge.place_ref | 门派/秘籍/兵器 |
| 神兵表 chain（既有资产） | chain / holders | 兵器卡 |
| 招式表（parent_art/used_by/conf） | moves/practitioners/hierarchy | 武功卡 |
| D11 一致性评级 | meta.confidence 聚合（A-E） | 全卡 |

> **无来源不上卡**：指不回上表的字段一律删除（K1）；不得用"原创分析"替代结构化来源（原创只进 brief/评述类字段）。

---

## 六、粒度标准与分层

### 6.1 粒度标准（D12 §4.1）

| SKU 类 | 粒度 | 来源 |
|---|---|---|
| Factual | 200–500 字，单实体级 | 08a §4.1 沿用 |
| Procedural | 300–800 字（背景/步骤/案例/效果） | 08a §4.2 沿用 |
| Relational | 实体关系网＋200–600 字说明 | 08a §4.3 武侠化 |
| 卡面单字段上限 | ≤200 字（brief 与明细数组除外） | D12 新增 |

### 6.2 "概要＋详情"分层（武侠调整）

- 卡面层：timeline/provenance/chain 只留**条目引用**（event_ref/edge_ref）＋一行式转述；brief ≤500 字；
- 详情层：超长内容拆为**事件 SKU 序列**（D03 事件为最小件）或 Relational 专题，卡上数组引用；
- 禁止把 3,000 字年表塞进 brief（K8）；详情层条目各自带 D05 时点键排序（K14）。

---

## 七、发布边界、脱敏与可信聚合

### 7.1 字段可发布性三档（D12 §6.1）

| 档 | 内容 | 落点 |
|---|---|---|
| A 直接发布 | 结构化属性、关系/事件三元组引用、统计（含分母）、原创转述/分析、不含正文的定位 | 全部结构化字段、brief、grade_basis |
| B 脱敏后发布 | 引用型内容：兵器铭文/门规条文/口诀诗句/书信遗言 → "概括语＋回锚" | 引文性描述、绰号出处说明 |
| C 禁止上卡 | 原文正文、标注正文、可还原正文的连续片段、逐字证据摘录伪装成图谱、未核实却表述为确定事实的问答 | **无字段允许落 C 档** |

### 7.2 脱敏规则 R1-R5（D12 §6.2）

- R1：卡面不得出现与原文连续重合 ≥10 字片段（阈值待拍板）；复核 agent 做 n-gram 比对；
- R2：引文型内容一律"概括语＋回锚"（回锚=ID 指针，不含文本）；
- R3：专名（人名/武功/地名/书名/绰号）可发布，不算片段；
- R4：未过审不得 `publish_state=approved`；demo 卡永远 blocked；
- R5：Procedural steps 若源自原文口诀，必须改写为原创归纳并回锚（否则 K2）。

### 7.3 卡级可信聚合（D12 §6.3）

- 卡级 confidence = **承重字段可信的最低值**；参考字段只降自身、不拖累卡级；
- 承重划分（初版）：人物=师承/门派履历/结局/绰号组归属；门派=谱系/存续/据点；武功=传人链/层级；兵器=持有链/下落；秘籍=content_arts/争夺链；
- 评级用 D11 A-E；**D11 硬约束随聚合带入**：登记层"来源声称"级最高 C；"未知"≠E。

---

## 八、工作流

### 8.1 生成九步（D12 §7.1）

锁版本 → 取实体 → 拉关系 → 拉事件 → 拉专项 → 组装字段 → 粒度裁决 → 可信聚合＋脱敏 → 落元数据（九项＋demo 检查）→ 登记 publish_state。

### 8.2 复核五查（D12 §7.2）

来源回查（抽样逐字段回溯）／脱敏抽检（R1 比对）／粒度抽检（brief 字数/单字段上限/数组引用）／元数据完备性（九项＋投影制 ID＋demo）／对账上游（§五 核对表逐行）。

### 8.3 变更传播（D12 §7.3）

上游更新（实体合并/事件新增/关系修订）→ 按"来源字段倒排索引"找受影响卡 → 重算 → `data_version` 递增；D09 词表升级 → `rule_version` 更新；D07 归并/拆分 → active_books/first_appearance 重算。

---

## 九、工具与脚本

| 工具 | 用途 | 现状 |
|---|---|---|
| N10 `build_sku_cards` | 五卡生成器（本技能自动化执行件） | **待建**（docs/50 §三：依赖已满足、下一波；不在 `scripts/`） |
| `registry/sku/` | 卡片产物目录 | **待建** |
| `scripts/relation_validator.py`（N5） | 关系边（卡字段来源） | ✅ |
| `scripts/time_resolver_wuxia.py`（N4） | 时点键（life_events 排序） | ✅ |
| `scripts/gazetteer_migrate.py`（N7） | 据点数据（strongholds） | ✅ |
| `scripts/lint_taxonomy.py`（N9） | 类型叶子（identity_tags/category） | ✅ |
| `scripts/build_entity_concordance.py` | 实体对照（canonical/变体） | ✅ |
| `scripts/export_site_all.py` | 页面导出（卡消费） | ✅ |

> 现状口径：**卡 Schema 已定版、数据源已就绪、生成器与产物目录未建**；本技能当前用于"手工/半自动建卡 + 复核"，N10 落地后由其自动执行 §八 九步。

---

## 十、检查清单

**生成前**
- [ ] 上游版本锁定（01g/D07/D06/D03/D05/D08/D10/D11 + 词表版本）记录在案；
- [ ] 实体在登记层存在、canonical 已定（改名人物用 D07 定名）；
- [ ] 卡类型判定正确（五类；无名实例按 D12 §2.7 条 4 裁决）。

**生成中**
- [ ] 每字段可指回 §五 来源表；指不回即删（K1）；
- [ ] 缺省态正确（[]/null/"未明示"；散修 vs 未明门派分开）；
- [ ] 统计字段带口径与分母（K10）；brief 200–500 字；
- [ ] 双向互指已建（秘籍↔武功，K12）；关系字段去重（K13）；事件按 D05 时点键排序（K14）；
- [ ] 超长内容已分层（K8）。

**生成后**
- [ ] 九项元数据齐备（含 proposition）；rule_version 含词表版本（K11）；
- [ ] 脱敏 R1-R5 通过；publish_state 合规；demo 卡未进发布库（K3）；
- [ ] 卡级 confidence 按承重字段最低值聚合（受 D11 上限约束）；
- [ ] 跨书字段原样引用 D07（active_books=[book]／first_appearance={book,loc_r}）（K6）；
- [ ] 路由可由实体 slug 生成（投影制）；卡上引用全部实体 ID（K4）。

---

## 十一、成功标准（Success Criteria）

1. **来源可溯**：100% 字段可指回 §五 来源表；无来源字段 = 0。
2. **零原文**：卡面连续重合 ≥10 字片段 = 0；C 档内容上卡 = 0。
3. **元数据完备**：九项最低字段 + 投影制 ID + demo 标记齐备率 100%。
4. **粒度合规**：brief 200–500 字；单字段 ≤200 字；超长已分层。
5. **可信合规**：卡级 confidence 按承重最低值聚合；无虚高（K9）。
6. **可复跑**：同上游快照重跑生成，卡产物幂等；`data_version` 递增可追。

---

## 十二、相关文档

- `SKILL_SKU卡片_武侠版.md`（D12，五卡 Schema/元数据/粒度/发布/工作流/K 系列）
- `SKILL_跨书治理_武侠版.md`（D07，双层 canonical/active_books/first_appearance）
- `SKILL_关系体系_武侠版.md`（D06）、`SKILL_04a_事件识别.md`（D03）、`SKILL_时间体系_武侠版.md`（D05）
- `SKILL_分类树五件套_武侠版.md`（D08）、`SKILL_地名gazetteer_武侠版.md`（D10）、`SKILL_常识与设定一致性_武侠版.md`（D11）
- `SKILL_词表体系规划_武侠版.md`（D09，版本协议）
- `docs/50-skill与脚本剩余实现清单-2026-11-05.md`（N10 缺口）

---

## 附录 A · 人物卡样例（节选，演示数据）

```json
{
  "meta": {
    "stable_id": "card.person.lian-nichang",
    "entity_ref": "E-P-0101",
    "card_type": "person",
    "proposition": "练霓裳为武当弃徒、天山创派掌门，与卓一航的正邪情缘是明末江湖阵营冲突的缩影",
    "supported_by": {"entities": ["E-P-0101", "E-P-0102"], "relations": ["edge.001"], "events": ["evt.001"]},
    "sources": ["01g:E-P-0101", "D06:edge.001", "D03:evt.001", "02ab:{作品ID}#pn-r{N}.{X}"],
    "confidence": "B",
    "data_version": "2026-11-05.01",
    "rule_version": "sku-card@0.3-draft+rel-verbs@v1+event-fields@v1",
    "method": "登记层投影＋关系边汇聚＋人工复核",
    "denominator": null,
    "publish_state": "in-review",
    "demo": true,
    "demo_note": "演示数据，非发布内容"
  },
  "name": {"canonical": "练霓裳"},
  "aliases": [{"surface": "白发魔女", "type": "绰号"}, {"surface": "玉罗刹", "type": "绰号"}],
  "identity_tags": ["绿林豪杰"],
  "faction_history": [{"faction_ref": "E-F-0007", "role": "掌门", "edge_ref": "edge.001", "conf": "strong"}],
  "teachers": ["edge.002"],
  "life_events": ["evt.001", "evt.002"],
  "brief": "（200–500 字原创转述，不含原文片段）"
}
```

## 附录 B · 待拍板（引 D12 附录 B，不在本文重开）

1. 脱敏阈值（连续重合 ≥10 字）——R1 待拍板；
2. 承重/参考字段划分定版；
3. 卡级 confidence 聚合细则（D11 映射边界）；
4. 中文规范名→slug 转写规则；
5. Procedural SKU 的武侠步骤模板；
6. Relational SKU 的卡片聚合结构；
7. 游戏卡等衍生视图命名空间（`game.*`）与 `derive_from` 规则；
8. 章级 v2 四件套的武侠字段落地顺序；
9. 卡级可信与页面角标展示规则；
10. N10 生成器的实现方案（依赖 N6/N7 已满足）。

*本文为字段执行件；Schema/发布规则冲突时以 D12（`SKILL_SKU卡片_武侠版.md`）为准。*
