---
name: skill-03b-wuxia
title: 人名消歧与跨书 canonical（含语境注记）——从待核验称名到可溯源登记层
description: 武侠章回文本的人物称名消歧执行规范：三层判定模型（L1 文内证据 → L2 映射表/registry → L3 跨书推理）、语境注记机制（时代/身份/同形异义）、帝王年号庙号专门规则、多书 registry 校准流程，以及与 accept_batch 管道三来源、normalize_pipe_canonicals、annotate_chapter_llm《已核准映射表》的接口。当需要判定"某称名指谁 / 规范名写什么 / 管道挂不挂 / 同形如何分流 / 登记层如何合并"时使用；产出供给 SKILL_03a 的《已核准映射表》与跨书归并输入。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 03b 武侠版：人名消歧与跨书 canonical（含语境注记）

> **上游声明**：本文从 shiji-kb 的 SKILL_03b（人名消歧）移植重造，移植依据见 `docs/05-管线技能与脚本逐项改造分析.md` §2.3（中度 45:55：四层启发式阶梯、4 列别名结构、canonical 命名规范照搬；**谥号学→绰号学**，歧义源整体换；**硬缺口：4 列结构加 book/series 维度**，书内唯一+系列可区分两层 canonical）与 `docs/17-技能脚本改造实现图与拓扑排序.md` §2.5（S-03b 属 P2 中档，←D07/D09）。
> **上游规范（已定版，本文引用不重定义）**：`SKILL_跨书治理_武侠版.md`（D07，下称"跨书治理"）§二 同一性证据四级、§三 权威四层、§四 双层 canonical 与两表 schema、§五 绰号/化名消解与同名异人；`SKILL_词表体系规划_武侠版.md`（D09）§三 统一 Schema（WL-01 绰号-本名映射表、WL-11 detection 语式表）、§3.5 扩展字段（book_scope/disambig）；`SKILL_03a_实体标注.md` v1.9 管道规则/D1 称谓/皇帝指称 G-20（L84/L95/L101/L135/L142/L220）。
> **现行工具（wuxia-kb/scripts/）**：`accept_batch.py`（@ 管道三来源验收）、`annotate_chapter_llm.py::load_mapping_table`（《已核准映射表》消费）、`propose_entity_registration.py` + `apply_entity_registration.py`（登记提案/合并）、`_oneshot/normalize_pipe_canonicals.py`（管道规范名归一）、`_oneshot/build_legacy_mapping.py`（换书映射快照）。
> **核心原则**：**先书内、后系列；证据不足不猜名；管道必须可溯源；两层 canonical 不混层。** 本技能不重新设计跨书同一性方法论（那是 D07 的职责），只负责把 D07 的规则**执行到每一条称名、每一根管道、每一条登记记录**上。

> ⚠ **状态快照更新（2026-11-05 晚，docs/63 review 发现 D-3；正文为 15:0x 时点快照，拍板前先对照本注与 registry 实测）**：
> ① 本文所有"现存 458/454 条"为 14:38 前快照——当日多波校准后 registry 已持续收敛（docs/62 记 433→430，实测仍在变化），**条数与条目一律以 `registry/entities.json` 现读为准**；
> ② §8.5 "实测修正清单"八项**已全部落地**（玄烨/福临/胤禛/哈玛雅/皇上删除/别名清理，见 docs/55）；
> ③ 附录 B "task-11（loader 回级）pending" **已实现**：`accept_batch._add_scope_notes(book=)` + `context_notes` 回级注记（本批 89 条，docs/61），且 `annotate_chapter_llm` 两条映射路径已补传 book（docs/63 修复）；
> ④ 附录 B "display 缺口" **已闭合**：`registry/display_canonical.json`（5 映射）+ EX-2/EX-3 display 字段 + Astro 展示切换（docs/58）；
> ⑤ §10.6 "江湖 82 条 unsourced" 基线已清零（docs/55）。正文相关段落保留作历史快照不覆盖，**按附录 B 拍板前必读本注**。

---

## 一、技能定位与边界

### 1.1 工序位置（P2 实体层收口件）

```text
S-03a 实体标注（v1.9）──产出〖@显示串|规范名〗管道与待核验队列──┐
                                                              ↓
S-03b 人名消歧（本文）──书内消歧 + 登记层校准 + 语境注记──《已核准映射表》回到 03a 上下文包
                                                              ↓
accept_batch 管道三来源核验 ──pipe_unsourced / pipe_mapping_conflict──→ 处置闭环
                                                              ↓
S-03c 按章反思（P4）──错误模式沉淀──→ 本文错误模式库 B 系列
```

- 前置：S-03a 已产出 tagged 语料与管道；登记层 `registry/entities.json` 可用（现存 458 条，11-05 14:4x 实测；与 docs/48 §十 记录的 460 条有差，属登记层持续校准，现场实测为准）。
- 后继：S-03c 反思、S-09 应用层（搜索/阅读器别名联想）、W7 引文核验。

### 1.2 本文做什么（六件事）

1. **书内消歧执行**：把同一本书内的本名/绰号/法号/化名/带姓称谓归并到**书内 canonical**；
2. **跨书 canonical 判定**：按跨书治理 §四双层规则给出**系列层 canonical/display**，不混层；
3. **语境注记**：为"同形异义/时代依赖/身份依赖"的称名建立可复核的注记（§七）；
4. **帝王/年号/庙号专门规则**（§八）：历史实有人物的 canonical、旁白/对话处理、年号与时间词分流；
5. **多书 registry 校准**：登记提案→审阅→合并→别名扩展→冲突裁决→status 分级（§九）；
6. **管道裁决与接口对接**：与 `accept_batch` 三来源、`normalize_pipe_canonicals`、《已核准映射表》对齐（§十）。

### 1.3 本文不做什么（边界，越界即错）

| 不做 | 归属 |
|---|---|
| 重新定义跨书同一性方法论、证据四级、权威四层 | D07 跨书治理 §二/§三（本文只引用） |
| 给原文加/删标注令牌、改显示串 | S-03a（本文只改**管道注释**与登记层，且改管道必须剥标逐字断言） |
| 词表数据填充（WL-01/WL-11 条目入库） | D09 §四 双轨三档（本文只给**词表候选与负规则需求**） |
| 地理实体归属 | D10 gazetteer；本文只传 entity 引用 |
| 跨书身份最终裁决（系列归并表落库） | D07 §四 `series_identities`（本文供给成员与证据，不越权落系列表） |
| 反思规律沉淀 | S-03c（本文错误模式经其回填 03c1） |

### 1.4 现行资产与"双轨"现状（必须先认清）

| 资产 | 形态 | 口径 |
|---|---|---|
| `registry/entities.json` | 单文件跨书：`{version, generated, scope, status_legend, entities:[{id,type,canonical,aliases[],contextual[],sources[],status,note}]}` | 管道消费方（scope=人物/组织/家族）；地点→gazetteer、技艺/概念→词表 |
| `kb/<书>/实体登记表.json` | 旧 schema `wuxia-tagged-v0.2`：`entities:{@规范名:{type,canonical,aliases{surface:count},...}}` | 书内层旧资产，`accept_batch --registry` 可直接加载（见 §10.2） |
| `logs/mapping_<书>/ch_NNN.json` | 每回《已核准映射表》快照（`[[显示串,规范名],…]`） | 换书标注用；由 `build_legacy_mapping` 从旧标注累积生成 |
| `logs/mapping_frozen_20261104.json` | 白发试点批次冻结映射 | accept 缺省映射来源 |

**双轨事实**：registry（系列层近似）与 `kb/<书>`（书内层旧表）目前**各说各话**——`飞红巾` 在 registry 是 canonical、在塞外旧表里 `@飞红巾`/`@哈玛雅` 是双条；`晦明禅师` 在白发 registry 是 `岳鸣珂` 的别名、在塞外/七剑旧表里是书内 canonical。本文的校准流程（§九）就是消解这类双轨，**不是推倒重来**。

---

## 二、快速开始（五步操作序）

````text
Step 1 现状盘点   pipeline_wuxia.py <书> concordance；accept_batch --book <书> --chapters … --mapping-file logs/mapping_<书> --registry <登记表>
Step 2 缺口分类   读 accept 报告 §6.2 pipe_unsourced / §6.3 pipe_mapping_conflict，按 §10.6 五分类
Step 3 登记校准   propose_entity_registration.py --book <书> → 人工审阅 → apply_entity_registration.py --book <书> --apply
Step 4 管道归一   （如需）_oneshot/normalize_pipe_canonicals.py <书> --dry-run → --apply；同步书内登记表
Step 5 复验回写   accept_batch 复跑（pipe_unsourced 下降）；pipeline_wuxia.py check 五门；变更写入 docs 记录
````

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
$env:PYTHONIOENCODING='utf-8'

# Step 1 现状盘点（只读）
python -X utf8 scripts/pipeline_wuxia.py 江湖三女侠 concordance
python -X utf8 scripts/accept_batch.py --book 江湖三女侠 --chapters 1-48 `
    --mapping-file logs/mapping_江湖三女侠 --registry ..\kb\江湖三女侠\实体登记表.json

# Step 3 登记提案 / 合并（默认 dry-run，加 --apply 才落盘；写前自动备份）
python -X utf8 scripts/propose_entity_registration.py --book 七剑下天山
python -X utf8 scripts/apply_entity_registration.py --book 七剑下天山

# Step 4 管道归一（只动管道元数据，剥标逐字断言；歧义 surface 自动跳过）
python -X utf8 scripts/_oneshot/normalize_pipe_canonicals.py 江湖三女侠 --dry-run

# Step 5 复验
python -X utf8 scripts/pipeline_wuxia.py 江湖三女侠 check
```

**成功标准**：accept `hard_errors=0`；`pipe_unsourced` 相比基线**单调下降**（目标归零）；`pipe_mapping_conflict` 全部有归属（补齐或转注记）；五门 lint 全 0；`registry` 合并后 id 唯一、(type,canonical) 唯一、条目数=旧+新增；tagged 正文零增删改（剥标断言）。

---

## 三、术语与三层判定模型

### 3.1 两层 canonical（引 跨书治理 §四，铁律）

| 层 | 键 | 命名口径（引文） | 落点 |
|---|---|---|---|
| 书内层 | (book, surface) → book canonical | **本名优先**：本名 > 尊号 > 绰号 > 职衔型通名（§4.2） | `kb/<书>/实体登记表.json`（现状）/ D07 `book_aliases`（目标） |
| 系列层 | entity_id → display_canonical | **读者认知最高频名**（§4.3）；例：岳鸣珂→晦明禅师取"晦明禅师" | `registry/entities.json` 近似 / D07 `series_identities`（目标） |

**混层禁令**（引 §4.1 三例）：书内绰号不得直登系列 display；书内别名表不得写跨书映射；两层反向索引各自独立校验。

### 3.2 三层消歧流程（本文核心操作模型）

```text
L1 文内证据（同回/同段可证）  ──成立──→ 直接定案（可自动，需锚点）
        │不成立
        ↓
L2 表证据（registry / kb书表 / 映射快照）──唯一命中──→ 定案（人工抽验）
        │多义 / 缺失
        ↓
L3 跨书推理（E3 情节暗示 / E4 推断）──→ 只产候选，人工双核准后落盘（不自动）
```

**顺序不可交换**：L1 > L2 > L3。L1 与 L2 冲突时，L1 回级证据优先（03a v1.2 裁定：映射在本回后文建立的，凭回级证据挂管道），并把 L2 的冲突记录为待校准项（`pipe_mapping_conflict` 的处置落点，见 accept_batch L698-700 的 warning 文本"需 S-03b 补语境注记"）。

### 3.3 证据分级与置信档（引 跨书治理 §二/§三）

| 证据级 | 内容 | 可用于 | 置信档 |
|---|---|---|---|
| E1 | 正文明示（"法号晦明""原来X就是Y"、邻接同位"散花女侠于承珠"） | L1 定案、L3 系列归并 | strong |
| E2 | 作者序跋/再版说明/作品元数据明示 | L3 系列归并（`source_channel=paratext`） | ok |
| E3 | 情节暗示（武功/神兵传承、师承链） | 只产候选 | todo→ok（人工双核后升） |
| E4 | 读者推断/常识 | **不落盘**，只入候选池 | todo（不发布） |

权威四层（引 §三）：**正文 > 作者修订 > 序跋 > 派生资料**。冲突时高层级胜；"多源矛盾保留"哲学仍适用——不强行抹平，记 `conflicts` 双记。

### 3.4 停止规则（防止过度消歧）

1. L1 无证据、L2 无唯一命中、L3 只有 E4 → **不挂管道、不改名、保留显示串**（03a L84"无映射时不挂管道、不凭常识猜测"）；
2. 单字显示串（"李""岳"）一律**不建映射**（`build_legacy_mapping` 规则 2：单字歧义过大，留交登记层；03a D1 亦不支持凭单字猜名）；
3. 同名异人未过唯一性检验 → 按跨书治理 §5.4 建限定词，**不归并**；
4. 系列层（L3）任何改动必须双人复核（跨书治理 §8.2），单人只能产候选。

---

## 四、L1 文内证据规则

### 4.1 判同语式（引 跨书治理 §5.2，不重抄全表）

| 组 | 语式（X=候选绰号/称名，Y=候选本名） | 强度 |
|---|---|---|
| A 权威授予 | 人称X / 江湖人称X / 人送外号X / 号称X / 被称为X / 世称X | 强（只证"X 是称号"，绑定 Y 仍需 D 组） |
| B 自我立名 | 自号X / 自称X / 化名X / 改名X / 又名X | 强 |
| C 师门授名 | 法号X / 道号X / 赐名X / 出家后为X | 强 |
| D 叙述判同 | 那X正是Y / 原来X就是Y / X，即Y / X（Y）括注同位 | **书内判同直证** |
| E 疑似 | 莫非是X / 可是X / 想必是X | 弱：只入候选池 |
| F 群体称号 | 合称X / 并称X / 号称"X"（N 人组） | 强（落人物群组 ◎ 层） |

> ✅ 正例：`玉罗刹`↔`练霓裳`——书中"那白衣少女正是玉罗刹，也就是练霓裳"式 D 组判同；`散花女侠于承珠` 邻接同位 S1+D 双命中。
> ❌ 反例：见到"号称"就归并——"号称天下第一"是夸饰，无专名锚点；`女魔头/女飞贼` 是评价代称（D1 不标），不得作别名（docs/49 §2.2 已剔除此类映射 60 条）。

### 4.2 回级文内证据的边界（03a v1.2 裁定）

- 允许：映射在**本回后文**才建立（如本回先出现"应大哥"、后文揭示"应修阳"）——凭回级证据挂管道；
- 禁止：用**未来回**的身份揭示去改写前面回的管道（"未来知识泄漏"），跨回只可用**已核准映射表**；
- 锚点记录：`{book, loc, kind}`，loc=`回:段`（02ab 机锚 `书#pn-r{N}.{X}` 用于登记层 refs）。

### 4.3 显示串与管道（复述 03a 硬规则，本文只管判定）

| 规则 | 正 | 误 | 依据 |
|---|---|---|---|
| 显示串=原文连续区间 | `〖@玉罗刹|练霓裳〗` | `〖@玉罗刹玉罗刹|练霓裳〗` | 03a §二/输出契约 |
| 称号外置 | `明太祖〖@朱元璋〗`、`〖@崇祯|朱由检〗皇帝` | `〖@崇祯皇帝|朱由检〗`（吞身份词） | 03a L135 |
| 同名管道必摘 | `〖@练霓裳〗` | `〖@练霓裳|练霓裳〗` | accept `same_name_pipe` hard |
| 空规范名必补/摘 | — | `〖@玉罗刹|〗` | accept `empty_pipe_note` hard |
| 纯衔不挂人物管道 | `〖;庄主〗` | `〖@庄主|成章五〗` | 03a L101 |
| D1 称谓不标/不挂 | 当面"陛下/圣上/万岁爷"裸文 | 为尊称造 `@` 令牌 | 03a L142（G-20） |

### 4.4 L1 产出物

每条候选落一行：`(book, chapter, loc_r, display, canonical, evidence_level, pattern_hit, conf, status)`；写入登记提案（§九）或映射快照，**不直接改 tagged**（改管道走 §十.5 工具链）。

---

## 五、L2 映射表与 registry 证据

### 5.1 可读的三种表形态（accept 兼容口径，引 accept_batch L186-294）

| # | 形态 | 结构 | 加载点 |
|---|---|---|---|
| 1 | registry 统一登记 | `{"entities":[{canonical, aliases[], contextual[], status,...}]}` | `load_registry_names` |
| 2 | 书内旧登记表 | `{"entities":{"@规范名":{canonical, aliases{...}}}}` | 同上（`_iter_entity_records` 兼容 dict） |
| 3 | 映射快照 | `[[显示串,规范名],…]` 或 `{"mapping":{…}}` / `{"items":[…]} ` | `load_frozen_mapping`（单文件或**目录合并**） |

### 5.2 字段语义（registry）

| 字段 | 语义 | 填写纪律 |
|---|---|---|
| `id` | 不透明序号 `E%04d`，由 apply 时 max+1 发放 | 提案不携带 id（防并发冲突） |
| `type` | 01g 15 类实体码 | 只登记 @/◆/&（scope）；地点/技艺/概念不入此表 |
| `canonical` | 跨书统一规范名（管道目标主键） | **本名优先**（§8.2/§B-1）；全系列未揭示本名时退尊号/绰号 |
| `aliases[]` | 可自动回溯的表面形式（绰号/法号/年号/避讳形/带姓称谓） | 单值语义；**歧义 surface 禁入**（§7.2） |
| `contextual[]` | 语境称谓（"卓兄""魏公公"） | 仅书内单义；带说明括注者被 loader 过滤（accept L232-237） |
| `sources[]` | 出现回号（3 位） | 人工/提案自动 |
| `status` | `approved`=种子人工核准；`proposed`=试点新增待核；`pending`=证据不足不猜名 | 流转见 §9.5 |
| `note` | 复核留痕/限定词 | 不写未证结论 |

### 5.3 消费口径（两条不同的取用规则，必须分清）

- **accept_batch**：`aliases + contextual` 合并为单值 `disp2canon`（`setdefault`，先到先得）+ `canon/alias` 集合；用于"管道规范名是否有来源"核验（accept L213-238）。
- **annotate_chapter_llm**：`load_mapping_table(book)` 只取 `type=="@"` 且 `status!="pending"` 的 `aliases+contextual`（跳过含括注项），再并入**已过审金标准 tagged 中实际管道**；排序按 `-len(显示串)`，提示词截断 400 条（L92-120、`mapping_text` limit=400）。
- **不变量**：`pending` 不进任何映射（"证据不足不猜名"）；`proposed` **会进**映射消费（docs/48 §十 status_legend 口径）——因此把歧义项写成 proposed 别名，等价于给全书注入错误映射。

### 5.4 映射快照纪律（引 build_legacy_mapping 规则）

1. 只取 `〖@显示串|规范名〗` 且两者非空、不同；
2. 单字显示串不收；
3. 第 N 回快照 = 第 1..N−1 回旧标注的累积（模拟顺序标注的"已核准"，**不引未来揭示**）；
4. 同一显示串多规范名 → 按累积出现次数取多（并列取先出现）；
5. 排序 `(-len(显示串), 显示串)` 与 annotate 截断顺序一致。

> 本节即"换书批次映射口径"的规范源：新书接入时先在 `logs/mapping_<书>/` 建快照，再标注；旧 KB 无资产的书用**空表**（冰魄先例，docs/49 §2.2），@ 管道只允许块内文内证据。

---

## 六、L3 跨书推理（只给判定规则，方法论引 D07）

### 6.1 双层判定判例（已在 D07/实测中成立的口径）

| 实体 | 书内层 canonical（各书） | 系列层 display | 证据 | 结论 |
|---|---|---|---|---|
| 岳鸣珂/晦明禅师 | 白发=岳鸣珂；塞外/七剑=晦明禅师（本名未在本书明写） | 晦明禅师 | E1 出家法号明写（跨书治理 §4.5 示例） | 两书成员挂同一 entity_id；**书内 canonical 允许不同** |
| 飞红巾/哈玛雅 | 塞外=哈玛雅（本名明写）；七剑=哈玛雅（据本名先于称号） | 飞红巾（作品元数据 lead 名，认知最高频） | E1 明写 + 序跋/元数据 E2 | 管道 `〖@飞红巾|哈玛雅〗` 合法；反向管道（哈玛雅|飞红巾）不合法（docs/49 §2.5 已摘 26 处） |
| 玉罗刹/练霓裳/白发魔女 | 白发=练霓裳 | 练霓裳 | E1 + 书内 D 组判同 | 01g FAQ 范例；pipe target=练霓裳 |
| 卓某 | 回级：032 自称→卓一航；他书/他人叙述→卓仲廉 | 不得为系列 display | E1 同段自称语境 | **禁作全局别名**（§7.2） |

> 判例表明：**"谁是 canonical"不是单一口径，而是"哪一层、哪本书"的函数**。飞红巾/哈玛雅、晦明/岳鸣珂、卓某三类挂账（docs/50 §七.4）在本节给出可执行口径，决策项见附录 B。

### 6.2 同名异人（引 跨书治理 §5.4）

裸通名绰号（"铁掌""神剑"）不得作为任何一层 canonical 独立存在；书内登记带限定词 `〖@铁掌|铁掌·湘西〗`；限定词优先序：书中明示籍贯/门派/兵器/性别 > 系列名 > 登记表人工定名；**禁用书名作限定词**；系列层各建 entity_id、互不归并、加"同名组"互链。

### 6.3 化名/改名分治（引 §5.5）

改名（岳鸣珂→晦明禅师）：同一 entity_id，成员表各书挂书内 canonical，display 取认知最高频；化名（临时假名）：同书内表面归并（book_aliases），一般不产生跨书成员，display 不用化名。

### 6.4 跨书冲突（引 §六）

有意呼应（资产）→ 登记呼应关系；无意穿帮（作者疏漏）→ 记冲突日志进穿帮雷达（N8/S-07），不强行归并；判别信号见跨书治理 §6.1。**本文只登记、不裁决**：L3 冲突最终由 D07 系列归并复核（双人）拍板。

### 6.5 自动化边界

| 操作 | 可自动 | 必须人工 |
|---|---|---|
| L1 语式候选 | ✅ | 定案（E1 抽验） |
| L2 唯一命中 | ✅（落盘前抽验） | ✅（新增/改 canonical） |
| 系列归并（E2+） | ❌ | ✅ 双人复核 |
| 同名异人限定词 | ❌ | ✅ |
| 帝王/避讳 canonical | ❌ | ✅（史实口径，附录 B） |

---

## 七、语境注记机制（本文新增件）

### 7.1 三类语境注记

| 类 | 触发 | 例 | 载体 |
|---|---|---|---|
| **C1 时代注记** | 同一通称在不同时代/书指向不同人 | "皇上/今上/先帝"跨书跨回 | 回级映射快照 + `context_notes`（提议字段，§7.2） |
| **C2 身份注记** | 同形称名依赖身份线索 | "李公子"（多书多指）；孪生姐妹冯瑛/冯琳 | `contextual`（仅单义）+ 回级证据 |
| **C3 同形异义注记** | 同 surface 跨类型/跨实体 | 客氏（人物 vs 家族）；风砂堡（地点 vs 组织）；哈萨克（族 vs 身份） | 类型判定表（§7.5）+ 数据清洗项 |

### 7.2 载体现状与硬约束（重要）

1. **歧义 surface 禁入 `aliases`/`contextual` 单值表**：accept 与 annotate 的 loader 会把 contextual 摊平为单值映射（accept L232-237；annotate L106-110），写进去即等于给全书一个错误默认；
2. **通称禁作全局别名**：`皇上/陛下/圣上/今上/先帝/先朝/万岁` 不得作为任一帝王条目的 aliases（docs/47-语义 §四 的 32 条 warning 即"全局映射表无回级作用域"所致；实测 registry 现有独立条目 `E83494 皇上` 即为反例，应降级/删除）；
3. **C1 的正式载体**：回级映射快照（`logs/mapping_<书>/ch_NNN.json`）+ 提案字段 `context_notes:[{surface, canonical, scope:{book, chapters}, kind, evidence}]`（v0.1 约定：先记入登记提案/变更记录，待工具消费；**不新增生产字段前不得假装已生效**）；
4. **C2 单义称谓**可入 `contextual`（如"卓兄→卓一航""魏公公→魏忠贤"已由 03a 种子核准）；多义项必须拆回注记；
5. **C3 走类型判定**（§7.5），改类型属数据清洗，单独立项（docs/53 §1.3 待考三项）。

### 7.3 C1：时代注记与帝王通称

**书→时代锚（初版建议，须以作品元数据表/序跋核准后冻结）**：

| 书 | 时代背景（初版） | 帝王候选 | 证据状态 |
|---|---|---|---|
| 白发魔女传 | 明万历末—天启 | 朱翊钧（万历，030 回忆）/ 朱由校（天启，022-028）/ 崇祯朝视回而定 | docs/47-语义 §四（逐回实测） |
| 江湖三女侠 | 清康熙末—雍正 | 玄烨（康熙）/ 胤禛（雍正） | 待元数据表核准（附录 B-3） |
| 塞外奇侠传 / 七剑下天山 / 冰魄寒光剑 | 清康熙 | 玄烨（康熙） | 待元数据表核准（附录 B-3） |

**通称处理规则**（与 03a G-20 一致）：

| 语境 | 处理 | 例 |
|---|---|---|
| 对白当面尊称 | **不标**（D1） | "皇上圣明""陛下"裸文 |
| 旁白叙述指称 + 回级可定 | 标 @ + 管道挂本名 | `〖@皇上|朱翊钧〗`（该回为万历朝） |
| 旁白叙述指称 + 回级不可定 | 不挂管道（保留显示串）或按"未知不猜"挂 pending 队列 | 跨朝回忆混述回 |
| 前朝/先帝 | 先按时代注记定人；不能定则不标 | "先帝"在顺治/康熙语境歧义（§8.7） |

### 7.4 C2：身份注记（三类典型）

1. **孪生/同貌不同人**（冯瑛/冯琳类）：surface 相同或近同，只能靠回级身份线索（同伴、门派、对话对象）区分；**禁止**把其中一个 surface 写成另一个的别名；书内登记保持两条 distinct entity（docs/47 §6.6-2 已列为待校准项）。
2. **称谓型歧义**（"李公子"）：同一书内多指 → 不入 aliases；每处挂管道须有本回共现（display+canonical 同回）或映射快照支持；registry 现存的 `E4030 李思永`（alias 李公子）与 `E58726 李公子`（独立条目）属**重复身份**，按 §8.7 合并。
3. **自称式化名**（"卓某"）：只在自称语境成立，canonical 由**说话人身份**决定（032 回自称=卓一航）；他人叙述同一 surface 可能指另一人（卓仲廉）。管道仅在**同段/同回**证据下成立，不做全局别名（032[31]/[33] 冲突即此，见 docs/44 §三）。

### 7.5 C3：同形异义跨类型判定表

| surface | 现象 | 判定规则 | 处置 |
|---|---|---|---|
| 客氏 | `&`×1 / `@`×57（docs/53 §1.3） | 本处"客氏"指人物（明熹宗乳母），非家族；`&` 误标 | 改 `@`；"客魏"=客氏+魏忠贤**合称**→ 群组 `◎` 或关系层，不作客氏别名（registry `E0213` alias `客魏` 应移除） |
| 风砂堡 | `&`×2 / `=`×8（docs/53 §1.3） | 地名后缀"堡"且语义为聚落/要塞 → 地点 `=`（归 gazetteer）；`&` 误标 | 改 `=`；`风砂堡主` 是职衔型通名（03a L101 纯衔不挂人物管道）——registry `E0217 成章五` 的 aliases `堡主/成堡主/风砂堡主` 应移出 @ 别名（或按 01g §5.1 office 型另立规则） |
| 哈萨克 | `@`7/`#`5/`=`2/`◆`2（docs/53 §1.3） | 民族共同体的族名本体 → `~`（B1-3 已裁，2026-11-05） | 清洗为 `~`；"哈萨克人"人义复合词不标（B1-2 类比） |
| 氏/堡/族 后缀 | 同形 | **后缀不自动定类型**：`X氏` 可为人物（客氏）、家族（慕容氏）、年号式称谓；`X堡` 可为地点/组织；`X族` 可为民族（`~`）或家族（`&`） | 逐条按上下文 + 定义裁决，不设机械规则 |

---

## 八、帝王/年号/庙号专门规则（历史实有人物）

### 8.1 四类指称与 canonical 定版

| 指称类 | 例 | 处理 | canonical |
|---|---|---|---|
| 本名 | 朱由检、玄烨、福临、胤禛 | 标 @；alias 收录年号/庙号/避讳形 | **canonical 本体** |
| 年号 | 崇祯、康熙、顺治、雍正 | 指人时标 @（旁白）→ 管道指向本名；作纪年时归 `%` 时间（§8.4） | alias |
| 庙号 | 思宗、圣祖（清庙号） | 旁白可标 @ → 管道本名；批评/引语同 | alias |
| 通称 | 皇上、陛下、圣上、今上、先帝、万岁 | 对白当面不标；旁白回级可定则标挂管道 | **禁止作 alias**（§7.2） |

**定版（建议，附录 B-1/B-2 待拍）**：

| 人物 | canonical（本名优先） | aliases | 备注 |
|---|---|---|---|
| 明思宗 | `朱由检` | 崇祯、崇祯皇帝、思宗 | registry 现有 `E98630 朱由检`（alias 崇祯）方向正确，补庙号/全称 |
| 清圣祖 | `玄烨` | 康熙、康熙皇帝 | registry 现有 `E5062` canonical 仍是"康熙"（alias 康熙皇帝/玄烨）→ **需改 canonical=玄烨**（docs/47-§6.6 记"康熙→玄烨"为待补映射，方向即此） |
| 清世祖 | `福临` | 顺治、顺治皇帝 | registry 现有**三条重复**：`E31206 顺治`（alias 先帝/先朝）、`E43934 福临`（alias 顺治）、`E63886 顺治皇帝` → 合并为 `福临`，"先帝/先朝"移入 C1 时代注记（非别名） |
| 清世宗 | `胤禛` | 雍正、雍正帝、**允禛**（避讳改写形） | registry 现无条目 → 新增；冰魄已摘的 `允禛|雍正` 属"管道指向年号"的反向错误（docs/49 §2.5），正确方向为 `〖@允禛|胤禛〗` |

### 8.2 旁白 vs 对话（G-20 操作化）

1. **对白当面尊称**一律不标（"皇上""陛下""万岁爷"裸文）；
2. **旁白叙述**：可标 @，管道只在"本回时代可定 + 《已核准映射表》有映射/本回共现"时挂（03a L84/L95）；
3. **同一回内多朝回忆**（白发 030 万历/022-028 天启类）：逐回按 C1 时代注记判定，**不得用全局映射一把梭**；
4. **未知不猜**：时代不可定 → 不挂管道，显示串照标或裸文，进 pending 队列（03a §二 未知原则）。

### 8.3 年号 ≠ 时间词（同形异义，最高频误判）

| 形态 | 判定 | 标注 |
|---|---|---|
| 崇祯三年 / 康熙十二年 / 顺治元年 / 雍正年间 | 纪年 → 时间 | `〖%崇祯三年|时点〗`（作时间实体，不标 @） |
| "崇祯自缢于煤山" / "康熙即位" / "雍正登基" | 指人 → 人物 | `〖@崇祯|朱由检〗` / `〖@康熙|玄烨〗` |
| "崇祯皇帝" / "康熙皇帝" / "雍正帝" | 指人 + 身份词 | `〖@崇祯|朱由检〗皇帝`（称号外置，03a L135） |
| "崇祯朝" / "康熙朝" | 朝代/时代段 | 视上下文：可作时间（时点/时长）或裸文；**不标人名管道** |
| 年号+年+帝称混写 | 先分词再判定 | 不得整段吞入 @ 显示串 |

### 8.4 避讳/异体/改写形

- 清帝名避讳改写（如 `胤禛` 避讳作 `允禛`）→ **别名**，canonical 仍本名；
- 异体/俗写（`祐`/`佑`、`禛`/`桢`）→ 按 01g 符号宪法"原文不改"原则：显示串照原文，canonical 用登记层定版字；
- 错误方向示例：`〖@允禛|雍正〗`（surface→年号）❌ → `〖@允禛|胤禛〗` ✅（docs/49 §2.5 已摘 2 处）。

### 8.5 registry 实测修正清单（11-05 14:4x，可直接作 §九 校准输入）

| # | 现状（实查） | 问题 | 建议动作 |
|---|---|---|---|
| 1 | `E5062` canonical=康熙，aliases=[康熙皇帝, 玄烨] | canonical 用年号，违反本名优先；docs/47 §6.6 待补"康熙→玄烨" | 改 canonical=玄烨；康熙/康熙皇帝入 aliases |
| 2 | `E31206` canonical=顺治(先帝,先朝)；`E43934` canonical=福临(顺治)；`E63886` canonical=顺治皇帝 | 同一人三条；通称作别名 | 合并 → `福临`；先帝/先朝移 C1 注记 |
| 3 | 雍正/胤禛 | 缺条目 | 新增 canonical=胤禛，aliases=[雍正,雍正帝,允禛] |
| 4 | `E0238` canonical=飞红巾，alias=哈玛雅 | 书内层未统一（塞外旧表 @飞红巾/@哈玛雅 双条；七剑旧表以飞红巾为 canonical） | canonical=哈玛雅（本名优先）；飞红巾由系列 display（B-2）承载 |
| 5 | `E4030` 李思永 alias=李公子；`E58726` canonical=李公子 | 重复身份 + 歧义 surface 单值化 | 合并；李公子降为 C2 注记（禁 alias） |
| 6 | `E83494` canonical=皇上 | 通称独立成实体，跨朝必错 | 删除或改 pending 注记；不得消费 |
| 7 | `E0213` 客氏 alias=客魏 | "客魏"是合称（客氏+魏忠贤） | 移出别名；合称按 ◎/关系层处理 |
| 8 | `E0217` 成章五 aliases=[堡主,成堡主,风砂堡主] | 职衔型通名挂人物管道（03a L101 禁止） | 移出 @ 别名；风砂堡归 gazetteer |

> 上表只是**已实查到的样本**，不是全量；§九 的校准流程负责系统性收敛。

### 8.6 史实人物 vs 虚构人物

- 史实人物（帝王/名臣）canonical 用**史实本名**，年号/庙号入别名，status 建议 `proposed` 起（需人工核准后 approved）；
- 虚构人物 canonical 用**书内本名**；本名不存在（纯绰号角色）→ 取书内最高频形式作 canonical，并在 note 标 `no_real_name=true`；
- 虚构人物的"历史原型"（如以某帝王为原型）**不建同一性**——只在 note 记录，不归并。

### 8.7 顺治/雍正类"先帝"歧义

`先帝` 在康熙朝可指福临（顺治），在雍正朝指玄烨（康熙），在乾隆朝指胤禛——**跨书/跨回不一致**。规则：先按 C1 时代注记定"当前在位的帝王"，再定"先帝=前一任"；无法定的回不标；**禁止**把"先帝"写进任何一条 aliases（这就是 docs/47-语义 §四 32 条皇帝类 warning 的教训）。

---

## 九、多书 registry 校准流程

### 9.1 触发条件

1. 新书首次标注完成（concordance 出 unregistered 清单）；
2. accept 报告 `pipe_unsourced` / `pipe_mapping_conflict` 超阈值；
3. 跨书归并（D07 系列表）输入需求；
4. 词表/类型裁定变更（如 B1-3 族群归 `~`）后的连带清洗。

### 9.2 五步（提案→审阅→合并→扩展→验证）

```text
①提案  propose_entity_registration.py --book <书>
        产出 registry/patches/<书>_entity_registration.json（entities[] + alias_additions[]，status=proposed，不含 id）
②审阅  人工按"本名优先/证据级别"逐条核准；歧义项拒绝或转 C 注记（§7.2）
③合并  apply_entity_registration.py --book <书> --apply
        现读现写 + (type,canonical) 二次去重 + id max+1 顺延 + alias_additions 并入 + 写前备份 + 写后唯一性断言
④扩展  别名扩展：将经证实的 surface 并入既有条目 aliases（不新建重复条目）
⑤验证  重跑 accept / concordance；pipe_unsourced 不升；登记层断言通过；变更入 docs 记录
```

### 9.3 合并规则（引脚本设计要点，防并发/防重复）

| 规则 | 说明 |
|---|---|
| 现读现写 | 每次合并前重载 entities.json，不缓存（并发批次安全） |
| 二次去重 | `(type, canonical)` 已在册 → 跳过，只做 alias 扩展 |
| id 延迟分配 | 合并时按现存 max(id)+1 发放；提案不带 id（防与并发批次冲突） |
| 别名不覆盖 | `add_alias` 已有则跳过；目标条目缺失告警 |
| 备份+断言 | 写前 `_backup_entities_<时间戳>.json`；写后 id 唯一、(type,canonical) 唯一、条目数=旧+新增 |
| 幂等 | 重放 apply = 0 变更 |

### 9.4 冲突裁决（四类）

| 冲突 | 判别 | 裁决 |
|---|---|---|
| 同 surface 多 canonical | registry aliases 碰撞 / 映射冲突 warning | 按 L1>L2 与时代/身份注记分流；不能分流→该 surface 不写单值别名 |
| 同 canonical 多 id | `(type,canonical)` 重复 | 保留信息最全者（id 不变），其余 canonical 降为别名合并（docs/47-语义 §7.3 李钦差/李天扬先例） |
| 别名环 | A alias B、B alias A | 破除环：保留 canonical 侧，单向别名；跑反向索引校验 |
| 跨型同名 | 同 surface 出现在不同 type | 逐条按 §7.5 判定；同实体跨型=误标，不同实体=同名异人 |

### 9.5 status 分级与流转

| 流转 | 条件 | 动作 |
|---|---|---|
| `proposed` → `approved` | 人工双证（E1 + 至少一处跨回/跨书一致）+ 双人复核留痕 | 改 status、note 记复核人/日期 |
| `approved` → 修改 canonical | 发现更佳本名/裁定变更 | 走双人复核；旧名转别保留搜索（跨书治理 §4.2/§4.3） |
| 任意 → `pending` | 证据不足/出现反证 | 停止映射消费；进人工队列 |
| `pending` → `proposed` | 补足证据 | 重新审阅 |

### 9.6 双轨收敛路径（书内旧表 → registry）

1. **近期（v0.1 现行）**：`kb/<书>` 保留书内层 canonical；registry 提供**跨书统一 canonical + aliases 全集**，保证两层的表面形式互相可溯源；
2. **过渡**：书内层差异（如晦明禅师 vs 岳鸣珂）在 registry 该条 `note` 记 `book_canonical` 映射，供 normalize/accept 双向核对；
3. **目标（v1.0）**：按跨书治理 §4.5 落 `book_aliases` + `series_identities` 两表，registry 成为 `series_identities` 的派生/过渡视图（ID 制统一）；本文附录 B-4 记录迁移约定。

---

## 十、与管道的接口（accept / normalize / annotate）

### 10.1 @ 管道三来源（accept_batch 定义，L22-24/L685-710/L822-829）

| 来源 | 判定 | 本技能动作 |
|---|---|---|
| ① registry canonical/aliases（含 contextual 摊平） | `note in reg_canon or note in reg_alias` | 规范名必须已登记；缺则 §九 补 |
| ② 映射快照（`--mapping-file`，缺省 frozen） | `note in frozen_canon` 或 `(disp,note) in frozen_pairs` | 换书批次必须传本书快照/目录 |
| ③ 本回正文显示串+规范名共现 | 整回 plain 中 display 与 canonical 同时出现 | 弱证据（列入 §七.1 人工抽查建议） |

三处均无 → `pipe_unsourced` warning（不阻塞 accepted，但它是本文的主要输入）；管道与 registry 冲突 → `pipe_mapping_conflict` warning（"回级文内证据优先；需 S-03b 补语境注记"，accept L698-700）。**处置目标**：把 conflict 变成"有归属的补登记/注记"，把 unsourced 逐条清零或转 pending 记录。

### 10.2 registry 加载口径（accept `load_registry_names`，L213-238）

- 兼容 registry 统一表与 `kb/<书>` 旧表两种 schema；
- `aliases + contextual` 合并进单值映射（`setdefault` 先到先得）；含 `（`/`(` 的项被过滤（说明性 contextual 不参与自动映射）；
- 因此：**歧义项写进 aliases/contextual 会污染全书映射** → 只写单义（§7.2 硬约束）。

### 10.3 mapping 快照加载口径（L241-294）

支持单回文件、目录合并（`--mapping-file` 传目录取并集）、`[[disp,canon]]`/`items`/`pairs`/`mapping` 多格式；登记表 JSON 不会被误当映射快照（有守卫）。换书批次必须传本书资产，否则退化为 frozen 白发口径（七剑 246 条 unsourced 即此因，已按 docs/48 §四清零）。

### 10.4 annotate 端《已核准映射表》（`load_mapping_table`，L92-120）

- 只取 `@` 类、`status != pending`；`aliases + contextual` 摊平；跳过括注项；
- 并入**已过审金标准 tagged 的实际管道**（人工核准映射第二来源）；
- 排序/截断：`-len(显示串)`，提示词最多 400 条；
- **本文职责**：保证这张表"单义、可溯源、无 pending 泄漏、无跨书串味"。

### 10.5 normalize_pipe_canonicals 接口（管道归一工具）

- 输入：`kb/<书>/实体登记表.json` 的 `surface → set(canonical)`（@ 类，含 canonical 自身）；
- 行为：**仅当 surface 唯一对应一个 canonical** 时改写管道规范名；归一后显示串==规范名则**摘管道**；
- 歧义 surface（如"李公子"）**自动跳过**，留给本文 §七 语境注记界定；
- 只动管道元数据（`|` 之后），显示串与正文零改动，脚本内剥标断言；`--dry-run`/`--apply`（apply 前备份）。
- 使用顺序：先 §九 校准书内登记表 → 再 normalize → 再 accept 复验（工具是"执行器"，本文是"裁决源"）。

### 10.6 pipe_unsourced / conflict 五分类处置（把 82 条清零的操作法）

| 类 | 识别 | 动作 |
|---|---|---|
| A 映射缺失 | 规范名本身合法（本名/已裁名），只是登记层没收录 | §九 提案补登记 → 复跑 |
| B 歧义未定 | display 多 canonical 或时代依赖（皇上/李公子/卓某） | §七 注记；**不写单值别名**；管道按回级证据 |
| C 史实人物未入册 | 康熙/崇祯/顺治/雍正类 | §八 定版条目 → 补 registry |
| D 误挂管道 | display→canonical 方向错/纯衔/同名管道 | 摘管道或改管（剥标断言） |
| E 工具误报 | 本回共现/映射快照口径未传 | 传 `--mapping-file`/`--registry` 复跑；记录工具缺陷 |

> 当前基线：江湖 82 条 unsourced 为既有 S-03b 残余（docs/54 §四/§五.1），按本表逐类消化；白发/七剑/塞外/冰魄已 0。

---

## 十一、工作流程与 Agent 提示词

### 11.1 六阶段

```text
阶段1 取证：扫描待核验称名（concordance/accept 报告/反思清单），建候选表（display, 出现回, 上下文片段）
阶段2 分级：逐条标 L1/L2/L3 证据与 E1-E4；不确定即 pending
阶段3 判决：L1 定案 / L2 唯一命中 / L3 候选→双人复核
阶段4 落表：登记提案 → 审阅 → apply；管道变更走 normalize/手工（剥标断言）
阶段5 重跑：accept 三来源核验 + 五门 lint + concordance 对比
阶段6 回写：变更记录（docs）、错误模式入 B 系列、词表候选入 WL-01/WL-11
```

### 11.2 Agent 提示词（单条判定）

```text
SYSTEM：你是武侠知识库的人名消歧判定员。只依据给定规范与证据裁决，不臆测。
TASK：对以下称名给出判定：{display}（书={book} 回={chapter} 上下文={snippet}）
   A. 指称对象（本名/书内 canonical）；B. 证据级别（L1/L2/L3 × E1-E4）；
   C. 是否挂管道及目标规范名；D. 若歧义，给出语境注记类型（C1/C2/C3）与所需额外证据。
OUTPUT(JSON)：{"display":…, "canonical":…, "layer":"book|series", "evidence":"E1…", "pipe":"…|null",
   "note_type":"C1|C2|C3|null", "confidence":"strong|ok|todo", "needs_human":true|false}
```

### 11.3 批次编排

- 按书/按回分片；同书并发只读，**写 registry 前须确认无并发批次**（apply 已现读现写+幂等，但仍应串行落盘）；
- 跨书归并（L3）单列批次，双人复核；
- 每批产出：提案 JSON、变更日志、复验报告（accept 前/后对比）。

---

## 十二、错误模式库（B 系列，本文件自有命名空间）

| # | 错误 | 实例 | 检测 | 修正 |
|---|---|---|---|---|
| B01 | 年号当 canonical | registry `康熙` 未改 `玄烨` | 史实人物 canonical 检查 | 改本名，年号入别名 |
| B02 | 通称单值化 | `皇上|朱翊钧` 跨书泛用 15 处；`E83494` 独立"皇上" | accept conflict / 跨回不一致 | 撤全局别名，C1 注记 |
| B03 | 管道方向反 | `〖@允禛|雍正〗`；`〖@哈玛雅|飞红巾〗` | 方向校验（surface→canonical） | 改 `|胤禛` / 摘除 |
| B04 | 显示串吞身份词 | `〖@崇祯皇帝|朱由检〗` | 显示串边界检查 | `〖@崇祯|朱由检〗皇帝` |
| B05 | 纯衔挂人物管道 | `〖@庄主|成章五〗`、alias `风砂堡主` | 03a L101 检查 | 改 `〖;庄主〗`；移出 @ 别名 |
| B06 | 单字建映射 | `李→李可灼` | 单字显示串检查 | 不收；留人工 |
| B07 | 歧义 surface 入别名 | `李公子` 写进 aliases | aliases 唯一性审计 | 移出，C2 注记 |
| B08 | 重复身份 | `顺治`/`福临`/`顺治皇帝` 三条；`李思永`/`李公子` 两条 | `(type,canonical)` + 语义重复审计 | 合并（保留信息最全者，余降别名） |
| B09 | 合称当别名 | `客魏` 挂在客氏下 | 合称识别 | 移群组 ◎/关系层 |
| B10 | 跨型混标 | 客氏 `&`、风砂堡 `&`、哈萨克 `@/#/=/◆` | 类型一致性统计 | 按 §7.5 清洗 |
| B11 | 系列/书内混层 | 把跨书归并写进书内别名表 | 混层三例检查（跨书治理 §4.1） | 移对应层表 |
| B12 | 未来知识泄漏 | 用后回揭示改前回管道 | 映射快照累积规则（§5.4） | 回滚；按回级证据重判 |
| B13 | pending 泄漏 | pending 条目被映射消费 | `load_mapping_table` 口径检查 | 改 status 或删除 |
| B14 | 括号注释当别名 | `儿子名唤归属（001[4]）` 进别名 | loader 括注过滤 | 写 contextual/注记，不写 alias |

---

## 十三、检查清单与验收标准

### 执行前
- [ ] 底本/结构冻结（02ab 完成门通过）；五门 lint 全 0；
- [ ] 登记层可读：`registry/entities.json` + 本书 `kb/<书>/实体登记表.json`；
- [ ] 映射来源明确：换书批次传 `--mapping-file`（单文件/目录）与 `--registry`；
- [ ] 并发检查：确认无其他批次正在写 registry/tagged。

### 执行中
- [ ] 每一条判定带 evidence（书/回/段/语式组）；
- [ ] 歧义项一律不进 aliases/contextual 单值（§7.2）；
- [ ] 帝王/年号项按 §八 处理（旁白/对话/纪年三分）；
- [ ] 改管道 = 剥标逐字断言 + 备份；
- [ ] 双人复核仅限 L3/史实 canonical/同名异人。

### 执行后（验收门）
- [ ] `accept_batch`：`hard_errors=0`；`pipe_unsourced` 相比基线下降；conflict 均有归属；
- [ ] `pipeline_wuxia.py <书> check` 五门全 0；
- [ ] 登记层断言：id 唯一、(type,canonical) 唯一、条目数=旧+新增、别名环 0；
- [ ] `concordance` registered 比例上升（unregistered 项均有处置记录）；
- [ ] 变更记录：spec 提案 JSON、变更日志、复验报告齐全，docs 回写。

### 成功标准（可量化）
- 目标 1：单书 `pipe_unsourced` 归零（或每条转 pending 记录并标注原因）；
- 目标 2：`pipe_mapping_conflict` 全部转为"补登记/注记/摘管"三类动作之一；
- 目标 3：歧义 surface 零别名污染（审计脚本可查）；
- 目标 4：帝王/年号类条目 canonical 全部为本名（§8 清单清零）。

---

## 十四、与反思循环挂钩

1. **→ S-03c 按章反思**：本文明细表中反复出现的同类错误（B 系列）是 03c 单章反思的输入；每批校准后把新增错误模式登记到反思清单，由 03c 汇总入 03c1 规律库（P4，同批交付）。
2. **→ S-03a 缺陷库**：消歧类缺陷（如 B04 显示串吞身份词、B05 纯衔管道）回填 03a §四 DEF 库；管道规则变更须重跑 `build_03a_fewshot.py --check` 并核对版本锁定。
3. **→ judgment/finalize_judgment**：accept 的 judgment 条目中 D1/称谓类（d1_description）由本文提供终签口径；已裁决保留项随本文批次复核。
4. **→ META-10 质量控制**：本书技能的质量指标（消歧完整率 >90%、类型准确率 >95%、一致性 >98%）纳入 META-10 L4/L5 体系；每批记录实测值。
5. **→ D07 系列归并表**：本文产出的成员/证据（E1-E4）汇入 `series_identities.evidence`，不自行落系列表。
6. **→ D09 词表**：绰号检测语式（WL-11）与绰号-本名映射（WL-01）的候选/负规则需求提交词表任务（含"歧义 surface 负规则"）。

---

## 十五、FAQ（高频 10 问）

**Q1 一个称名在同一本书里指两个人怎么办？**
不入 aliases；按 C2 身份注记 + 回级证据逐一判管道；同名异人按跨书治理 §5.4 加限定词。

**Q2 "皇上"能不能统一写成某帝王？**
不能。对白当面不标；旁白按 C1 时代注记定人；任何 "皇上/陛下/圣上/今上/先帝" 不得作 aliases。

**Q3 "崇祯三年" 标 % 还是 @？**
年号+年/年间/元年 = 纪年 → `%`；年号单用指人（"崇祯自缢"）= `@`；"崇祯皇帝"= `@` + 称号外置。见 §8.3。

**Q4 registry 里已经有"康熙"这个 canonical，要改吗？**
要。按本名优先改 `玄烨`，康熙/康熙皇帝入别名；这是 docs/47 §6.6-2 待补映射的正向口径。

**Q5 飞红巾和哈玛雅，到底哪个 canonical？**
分层：书内层=`哈玛雅`（本名优先，塞外已明写）；系列 display=`飞红巾`（认知最高频，作品元数据 lead 名；决策点 B-2）。管道 `飞红巾|哈玛雅` 合法，反向不合法。

**Q6 晦明禅师在白发是岳鸣珂别名、在塞外/七剑是书内 canonical，冲突吗？**
不冲突——双层 canonical 的正常形态（D07 §4.2/§4.3）：书内 canonical 各书可不同，系列 display 取认知最高频；registry canonical 维持岳鸣珂，两张皮通过 members/别名互溯。

**Q7 卓某能不能直接写成 `〖@卓某|卓一航〗`？**
只在自称语境成立且同段可证；032 回自称=卓一航成立，但他书/他人叙述可能指卓仲廉。禁全局别名（§7.4）。

**Q8 一个新书没有旧 KB 资产，怎么建映射？**
映射快照用空表（冰魄先例）；@ 管道只允许块内文内证据；标注完成后按 §九 提案补登记，再 normalize + accept。

**Q9 注册表条目 status 怎么给？**
种子人工核准=approved；试点新增待核=proposed（会进映射消费！）；证据不足=pending（不消费）。歧义项不放任何 status 的别名。

**Q10 本文与 D07 系列归并表什么关系？**
本文=执行层（书内消歧 + 管道 + 登记层校准）；D07=方法论与系列归并表结构。本文只产成员/证据，系列层落库归 D07 双人复核。

---

## 十六、工具与脚本

| 用途 | 工具 | 说明 |
|---|---|---|
| 管道三来源验收 | `accept_batch.py` | `pipe_unsourced`/`pipe_mapping_conflict` 判定（§10.1） |
| 《已核准映射表》消费 | `annotate_chapter_llm.py`（`load_mapping_table`） | @ 且非 pending，400 条截断（§10.4） |
| 登记提案 | `propose_entity_registration.py` | 从 concordance 聚合未登记实体（§9.2） |
| 登记合并 | `apply_entity_registration.py` | 现读现写 + 二次去重 + id 顺延 + 备份断言 |
| 管道归一 | `normalize_pipe_canonicals.py`（`scripts/_oneshot/`） | 唯一 surface 才改管，歧义跳过，剥标断言 |
| 映射快照 | `build_legacy_mapping.py`（`scripts/_oneshot/`） | 换书批次每回《已核准映射表》（§5.4） |
| 结构完成门 | `pipeline_wuxia.py check` | 五门 lint（§13） |
| 映射核对 | `pipeline_wuxia.py <书> concordance` | registered/unregistered 基线 |

> 脚本路径与行号见§10/§16 与 `scripts/README.md`；本文只规定接口语义，不重写工具。

---
## 十七、相关文档

| 文档 | 关系 |
|---|---|
| `skills/SKILL_跨书治理_武侠版.md` | 上游方法论（证据四级/权威四层/双层 canonical/两表 schema） |
| `skills/SKILL_词表体系规划_武侠版.md` | WL-01 绰号映射、WL-11 检测语式、8 字段 Schema |
| `skills/SKILL_03a_实体标注.md` v1.9 | 管道规则/D1/G-20/回级证据/《已核准映射表》消费方 |
| `docs/47-020-032语义召回分析与补标处置记录.md` | 皇帝类 warning 与考订案例（§四/§7.3） |
| `docs/47-江湖三女侠全48回机器标注执行记录.md` | §6.6-2 registry 三项残余 + S-03b 挂账 |
| `docs/48-七剑下天山全31单元机器标注执行记录.md` | §十 新书登记工具（S-03b 前置） |
| `docs/49-塞外奇侠传与冰魄寒光剑机器标注执行记录.md` | §2.5 管道归一、§五.8 跨书规范名待裁 |
| `docs/53-半日收尾批次记录-2026-11-05.md` | B1-3 族群/待考数据清洗项 |
| `docs/54-judgment落地与围栏漂移治理记录-2026-11-05.md` | §四/§五.1 江湖 82 条 unsourced 基线 |
| `scripts/accept_batch.py` | 管道三来源验收实现（L22-24/L213-294/L685-710） |
| `scripts/propose_entity_registration.py` / `apply_entity_registration.py` | 登记提案/合并工具 |
| `normalize_pipe_canonicals.py`（`scripts/_oneshot/`） | 管道规范名归一执行器 |

---

## 附录 A · 与 shiji 03b 原版差异对照（META-13 纪律）

| 史记 03b | 处置 | 武侠版 |
|---|---|---|
| 谥号学/帝王庙号消歧 | [替换] | 绰号学 + 帝王四类指称（本名/年号/庙号/通称），§八 |
| 四层启发式阶梯 | [照搬+扩展] | 本文三层 L1-L3（阶梯合并为"证据层 × 证据级"二维），§三 |
| 4 列别名结构（surface/type/canonical/refs） | [扩展] | + book/series 双层、book_scope/disambig（D09 §3.5）；WL-01/WL-11 |
| 姓氏对照表 | [替换] | 门派字辈/辈分字（S-07b 承接，本文只留接口） |
| 在位年区间校验 | [替换] | 书内相对时间轴（D05 承接）；帝王年号→纪年归 `%`（§8.3） |
| 别名映射表 schema | [扩展] | registry 统一表 + kb/<书> 旧表双轨，schema 见 §5.1 |
| "同名异人"处理 | [照搬] | 跨书治理 §5.4 限定词规则 |
| 别名链解析（A→B→C） | [补写] | 别名环检测 + 反向索引校验（§9.4） |
| 数据源（汉书/rulers.json 类权威表） | [补写] | 无对应物 → 系列谱系考订表 + registry + 语料证据（对应 docs/05 G4 隐形缺口） |

## 附录 B · 六项决策建议（推荐选项 + 依据 + ⏳ 待用户确认）

> **状态声明**：本附录是**决策建议**，不是拍板记录。用户确认前：主文 §一—§十六按"现行实现"执行（可回滚）；确认后由 Lead 在本附录末尾追加"裁决记录（日期/批准人/决议）"并把状态改为 ✅，再回写 §7.3/§8.5/附录 C 与相关 docs。
> **"已实施"≠"已拍板"**：数据侧进展只证明推荐方案可落地，不构成口径批准。现状实测时点：2026-11-05 15:0x。
> **并行依赖**：task-11（loader 回级作用域）**pending 未落地**；task-12（registry 校准批2：飞红巾/李公子/客魏/成章五/皇帝）**in_progress**（registry 尚为 14:38 的 454 条快照）。B-2/B-4/B-5/B-6 落地须与二者串行。

### B.0 摘要

| # | 决策点 | 推荐选项（一句话） | 依据强度 | 状态 |
|---|---|---|---|---|
| B-1 | 史实人物 canonical | **本名优先**（玄烨/朱由检/福临/胤禛）+ 增设展示层 `display_canonical`（帝王展示年号） | 高（条文 + docs/55 已实施） | ⏳ 待确认（数据已先行实施） |
| B-2 | 飞红巾/哈玛雅 | 书内 canonical=**哈玛雅**；系列 display=**飞红巾** | 高（条文 + 实测） | ⏳ 待确认（task-12 在实施） |
| B-3 | 书→时代锚表 | 从 `作品元数据表`+`系列谱系考订表` 生成，按 conf **分级冻结** | 中高（数据源已备） | ⏳ 待确认 |
| B-4 | registry→两表 | **分三阶段**；Stage-3（切真源）延至 P4/P5 | 中（目标 schema 已定） | ⏳ 待确认 |
| B-5 | 纯衔入 aliases | **三分类**：泛衔禁入 / 专衔限 contextual / 宗教尊称可入 | 高（03a L101 + 实测 20 条） | ⏳ 待确认（task-12 处理 E0217） |
| B-6 | 歧义 surface 载体 | **两阶段**：v0.1 摘管（已做）→ v0.2 待 task-11 后启用 `context_notes` | 高（A/B 实测） | ⏳ 待确认 |

### B-1 帝王/史实人物 canonical 模式

**推荐选项**：canonical=史实本名（玄烨/朱由检/福临/胤禛；年号/庙号/避讳形入 aliases）；**另设展示层 `display_canonical`**：历史人物展示默认用读者最高频称名（康熙/崇祯/顺治/雍正），虚构人物取认知最高频名。

**设计依据**
1. 条文：D07 §4.2「书内 canonical 取本名优先：本名 > 尊号 > 绰号 > 职衔型通名」+ §4.3「系列 display 取读者认知最高频名」——canonical 与 display 是两层、不是二选一。
2. 条文：03a v1.9 种子方向 `神宗→朱翊钧`（03a L135）与 G-20「皇帝指称叙述照标挂映射」均指向本名 canonical；docs/47-江湖 §6.6-2 把「崇祯→朱由检 / 顺治→福临 / 康熙→玄烨」列为待补映射，方向同。
3. 实测：docs/55 §1.3 已实施（registry 458→454：E5062→玄烨、E31206/E43934/E63886 合并福临、E98630/E91062/E104822 合并朱由检、新增 E118269 胤禛、删除 E83494 皇上）；江湖 82 条 pipe_unsourced→0（docs/55 §1.1）；本文件 15:0x 实测 registry 454 条、帝王条 status 仍为 proposed。
4. **产品层缺口（用户可见）**：导出层目前 canonical 即展示名——`../site/data/dossiers.json` 实测记录只有 `id/canonical`（如 `@玄烨`）；若只改 canonical 不补 display 层，站点会把"康熙/崇祯"显示成"玄烨/朱由检"。**这是本项最需要用户知情的一点。**

**备选与代价**
- 备选①：年号作 canonical（旧 registry 现状）——违反 D07 §4.2、与种子方向相反；须改全部种子/映射/管道 ≥3,000 条，且"崇祯"不是人名、跨朝代引用失真；代价高收益低，不推荐。
- 备选②：canonical 用本名但**不做 display 层**——数据正确、读者侧显示退化（康熙→玄烨）；需用户接受或补 enabler。

**受影响文件/工具**：`registry/entities.json`（E65950「皇帝」余项待 task-12；帝王 6 条 status 待升 approved）、`scripts/export_site_characters.py`（L133/L170 canonical）、`scripts/export_site_dossiers.py`（L5/L62 canonical 索引）、`site/data` 契约（display 缺省回退）、docs/47-语义 §四 mapping、本文 §8.5/附录 C。

**若采纳实施清单（≈1.5–2 人日）**
1. registry 清理与状态：E65950/通称实体处置（task-12 同步）；帝王批 proposed→approved（人工双证留痕）——0.25
2. `display_canonical` 字段：registry schema + 导出器（characters/dossiers 加 display，缺省回退 canonical，旧契约不破坏；**与 B-2 共用 enabler**）——1.0
3. 年号→本名映射审计：5 书 mapping 快照与 frozen 表（江湖已补 4 对）——0.25
4. 回归：5 书 accept（unsourced=0 / hard=0 / judgment 不升）+ concordance + export + build——0.25
5. 文档回写：§8.5/附录 C、docs/47-语义 §四、docs/50 §七.4——0.25

**⏳ 待用户确认点**：展示层默认显示"康熙"类年号还是本名？（推荐年号；若选本名，实施项 2 可省但读者体验退化）

### B-2 飞红巾/哈玛雅：双层 canonical 与系列 display

**推荐选项**：**书内 canonical=哈玛雅**（塞外奇侠传本名明写；七剑按 member 映射同）；**系列 display=飞红巾**（作品元数据表 lead 名、读者认知最高频）；registry canonical=哈玛雅、aliases 收 飞红巾；现有 333 处 `〖@飞红巾|哈玛雅〗` 管道**合法保留**，反向（`哈玛雅|飞红巾`）不合法。

**设计依据**
1. D07 §4.2/§4.3 双层分工（同 B-1）；D07 §5.4 同名异人限定与 §5.5 改名/化名分治。
2. 实测：docs/49 §2.5 反向 26 处已摘、§五.8 明确"飞红巾（作品元数据 lead 名）与哈玛雅（本名）谁 canonical 留待 S-03b"；docs/50 §七.4 列为跨书 canonical 政策输入；task-12 任务书已按"书内哈玛雅 / 系列飞红巾"立项。
3. 管道方向规则：03a 只允许 surface→canonical；`飞红巾|哈玛雅` 方向正确，保留成本零。

**备选与代价**
- 备选①：canonical=飞红巾（旧 registry 现状）——本名优先失效，"哈玛雅"降别名后检索/历史一致性差，且与晦明/岳鸣珂（本名 priority 同型判例）不一致。
- 备选②：两书各用各的 canonical（塞外=哈玛雅、七剑=飞红巾）——`accept`/统计需双键，D07 §4.4 明确反对混层；代价高。

**受影响文件/工具**：`registry/entities.json`（E0238）、`kb/塞外奇侠传/实体登记表.json`（旧表 @飞红巾/@哈玛雅 双条合并）、`kb/七剑下天山/实体登记表.json`（@飞红巾 canonical）、`normalize_pipe_canonicals.py`（书内 canonical 归一）、accept/concordance/export/site（display=飞红巾，依赖 B-1 enabler）、task-12 报告。

**若采纳实施清单（≈1–1.5 人日，含与 task-12 联调）**
1. E0238 canonical→哈玛雅、aliases→[飞红巾]（task-12 同步）——0.1
2. 两书旧登记表合并双条、canonical→哈玛雅（保留 surface 频次）——0.3
3. 333 处管道合法性核验（确认无新反向）——0.2
4. display=飞红巾（依赖 B-1 的 display enabler）——0.2
5. 2 书 accept/concordance/export/build + 文档——0.3

**⏳ 待用户确认点**：系列展示名用"飞红巾"而非"哈玛雅"？（推荐飞红巾；若选本名，搜索/页面标题与读者习惯冲突）

### B-3 书→时代锚表（帝王候选与冻结策略）

**推荐选项**：新建 `registry/context/eras.json`（或 `wordlists/context_eras.tsv`）：每书 `{book, era_label, era_conf, emperors[{canonical, 年号, 在位回范围}], source, frozen}`；**按 conf 分级冻结**：era_conf=ok 的 3 书先冻结（白发/江湖/七剑），todo 的 2 书（塞外/冰魄）标 `frozen=false` 暂用、随考订升级。

**设计依据**
1. 权威数据已备（实测 `../kb/作品元数据表.json`）：白发"明末·万历—崇祯（001回梃击案=万历四十三年）"**ok**、江湖"清·雍正"**ok**、七剑"清·康熙"**ok**、塞外"清初·顺治—康熙间"**todo**、冰魄"清·康熙—雍正间（待考）"**todo**；`../kb/系列谱系考订表.json`：塞外 **strong**（回指 + 正文"顺治入关后第七年"）、冰魄 **todo**、其余 ok/strong。
2. 实测反例：皇帝类 warning 根因"全局映射无回级作用域"——docs/47-语义 §四（32 条）；docs/55 §1.2（全局写"皇上→本名"使 qa pipe_issues 136→321）。
3. 条文：D07 §三 权威层级（正文>修订>序跋>派生）+ §6.1 时间线自洽=有意呼应信号——时代锚是跨书"呼应/穿帮"判别的前置。

**⚠ 对主文的更正**：本文 §7.3 初版表写江湖"康熙末—雍正"、白发"万历末—天启"，与元数据表实测不符；按本项应为**江湖=清·雍正、白发=明末·万历—崇祯**。用户确认 B-3 后须同步回写 §7.3（按本轮 scope 未改主文）。

**备选与代价**
- 备选①：不冻结、逐回人工注记——成本随批次线性增长，跨回一致性不可保证。
- 备选②：按出版/创作年推断背景——创作年≠书内时代，直接错误。

**受影响文件/工具**：新建 eras 文件、task-11 loader（context_notes 消费）、accept/qa 规则、judgment（皇帝类）、docs/50 §七.3、`../kb/作品元数据表.json`（父仓只读，仅引用）。

**若采纳实施清单（≈0.75 人日 + task-11 依赖）**
1. 生成 eras 表（一次性派生脚本，读元数据表/谱系表/互文表）——0.25
2. 人工复核 5 书帝王候选与在位回范围（塞外/冰魄 标 provisional）——0.25
3. 冻结审查（3 书 ok）+ 裁决记录——0.1
4. task-11 落地后接 loader（(书,回)→帝王候选）——0.15（与 B-6 合批）

**⏳ 待用户确认点**：todo 的两书是否接受"provisional 可用"？（推荐接受；否则其皇帝指称只能继续摘管）

### B-4 registry → D07 两表迁移时机

**推荐选项**：**分三阶段、Stage-3 延后**：
- **Stage-1（现在，≈0.5 人日）**：registry 增可选字段 `book_scope[]`、`display_canonical`、`context_notes[]`（全部向后兼容；loader 不读即无影响）。
- **Stage-2（P4 前，≈1–1.5 人日）**：由 registry+concordance+kb 旧表**派生只读** `book_aliases`/`series_identities` 两份产物（D07 §4.5 字段），用 concordance 校验覆盖率；N6 就绪后接归并队列。
- **Stage-3（P4/P5，≈2–3 人日）**：切换真源为两表、registry 转派生视图；迁移各 loader 与导出器；双跑回归。

**设计依据**
1. D07 §4.4（裁决两表不取一表两键：证据语义/键结构/管线次序/采集边界四理由）+ §4.5 字段全展开 + §4.6 15 类治理强度。
2. D07 §3.4 记录层/发布层分工：记录层全保留、发布层单一权威——两表正是发布层结构的承载。
3. 现状：registry 单文件 454 条、双轨（kb 旧表）未收敛（docs/55 §五.1/§五.2 仍列 E0238/E4030/E0213/E0217/E65950）；task-11/12 未收口前切真源会放大双轨冲突。

**备选与代价**
- 备选①：立即全面迁移——6+ loader/导出器同时改，N6 未就绪无校验器，风险高。
- 备选②：永久不迁移——系列归并字段（members/evidence/conflicts/active_books）无处落，D07 归并表与 W 组系列页无法实现。

**受影响文件/工具**：registry schema、新 `registry/book_aliases.json`+`series_identities.json`、scripts/{accept_batch, qa_annotation_report, annotate_chapter_llm, normalize（正式化）, propose/apply_entity_registration, export_site_characters, export_site_dossiers, export_site_sects_weapons_arts}、concordance、N6、D07 §4.5、W 组系列页。

**若采纳实施清单**：Stage-1 字段 schema+兼容测试 0.5；Stage-2 派生器+校验 1~1.5；Stage-3 loader 迁移+双跑 2~3（依赖 N6 与 B-1/B-2 确认）。

**⏳ 待用户确认点**：Stage-3 时点是否接受"P4 之后"？（推荐接受；提前不划算）

### B-5 "堡主/庄主"类职衔型通名是否入 aliases

**推荐选项**：**三分类裁决**（对 registry 实测 20 条带衔别名）：

| 类 | 判定 | 处置 | 实测样本 |
|---|---|---|---|
| 泛衔 | 不带姓/地/名的职衔词本身（堡主/庄主/寨主/舵主/掌门/皇帝） | **禁入** @ aliases/contextual（不唯一指人） | 堡主、总舵主×2（3 条） |
| 专衔 | 带姓/带地/带名的职衔称谓（成堡主/风砂堡主/刘总舵主/武庄主） | 可入 **contextual**，书内唯一性检验通过才可作管道来源；不升 canonical | 11 条 |
| 宗教尊称 | 法号+尊称（晦明禅师/镜明长老/天蒙禅师） | 属 D07 §5.1 `hao` 子类，**可入 aliases** | 6 条 |

**设计依据**：03a v1.9 L101「纯衔不挂人物名管道」（`〖;庄主〗` 非 `〖@庄主|某人〗`）；D07 §5.1 别名 type 细分（office=职衔型通名、hao=尊号/法号；"金刀寨主"例注明拆分另计）；03a L220 带姓称谓可作管道来源；docs/53 §1.3 风砂堡/客氏待考。
**备选与代价**：① 全部禁入——误伤"晦明禅师/镜明长老"类已 approved 法号别名（E0032/E0236），检索退化；② 全部入 aliases——泛衔跨人污染（01g 正交性破坏）、accept 假冲突。
**受影响文件/工具**：registry（E0217 等 20 条，task-12 处理 E0217）、可选审计脚本 `audit_registry_aliases.py`（`scripts/`，待建）、03a L101 交叉引用、docs 记录。
**若采纳实施清单（≈0.5–1 人日）**：① 20 条逐条分类表 0.2；② E0217 泛衔/专衔重登记（task-12 同步）0.2；③ 新条目登记按三分类自检（写入 §5.4/§8.5）0.1；④ 5 书 accept 回归确认无假冲突 0.2。
**⏳ 待用户确认点**：专衔是否允许作管道来源？（推荐允许但限书内唯一；若从严，专衔只做展示别名不消费）

### B-6 歧义 surface（李公子/皇上/卓某）注记载体

**推荐选项**：**两阶段**：
- **v0.1（现行，已完成）**：歧义 surface **禁入** aliases/contextual 单值；时代通称（皇上/皇帝/先帝）**摘管道**、保留 `〖@皇上〗` 实体；证据只记提案/变更日志。docs/55 §1.2 实测：此路径使江湖 82→0 且 qa pipe_issues 136→134。
- **v0.2（待 task-11）**：registry 增 `context_notes[]` 结构化载体 + loader 回级查找 `(book,ch)→(book)→global`；A/B 保证缺省输入逐字节/逐指标一致；启用后按 evidence 恢复"回级可定"的 26 条通称管道。
**设计依据**
1. 实测反例：docs/55 §1.2——全局写"皇上→本名"使 qa pipe_issues **136→321**（118+ 条他回假冲突），退回摘管后 82 unsourced→0、qa 134（优于基线）。
2. 条文：D07 §3.4「记录层全保留 / 发布层单一权威值」+ §6.4 层内矛盾归雷达、层间走权威层级——歧义通称属于"发布层无唯一值→降 conf/记录"，不是硬造单值。
3. 实测：docs/47-语义 §四 32 条皇帝类 warning 根因即"全局映射表无回级作用域"；task-11 任务书已定 schema（scope/chapter、查找顺序、向后兼容 A/B、5 书回归）。
**备选与代价**：① 永久摘管——信息丢失、qa 残留 134 条无法消、`皇上` 类历史信息不可用；② 全局单值——已证伪（docs/55）；③ 每书单独 frozen 映射——不能解决同书跨回时代歧义（白发 030 万历/022-028 天启并存）。
**受影响文件/工具**：registry schema、`accept_batch.py`（load_mapping_table/load_registry_names/三来源）、`qa_annotation_report.py`、`annotate_chapter_llm.py`（loader 部分）、mapping 快照、本文 §7.2/§10.4、docs/55 后续。
**若采纳实施清单（≈1.5–2 人日，在 task-11 之后）**：① 消费 task-11 loader 0.1；② context_notes schema + 写入工具（提案/apply 扩展）0.4；③ 26 条摘管管道按回级 evidence 恢复或转注记 0.3；④ A/B 回归 5 书 0.3；⑤ 文档/§7.2 回写 0.2。task-11 未落地则保持 v0.1（成本 0）。
**⏳ 待用户确认点**：是否接受"v0.2 前通称一律摘管"？（推荐接受；这是当前最优稳定态）

### B.9 确认与执行约定

1. **确认方式**：用户回复"B-1~B-6 全部按推荐"或逐项指定例外；Lead 在本附录末尾追加"裁决记录"表（日期/批准人/决议/例外）。
2. **确认后更新**：本附录状态 ⏳→✅；§7.3/§8.5/附录 C 回写；docs/47-语义 §四、docs/50 §七.4、docs/55 §五.3 遗留勾销。
3. **总工期（全部确认）**：≈5–7 人日；关键依赖：task-12（B-2/B-5）→ B-1 display；task-11（B-3/B-6）；B-4 Stage-3 后置 P4/P5。
4. **不确认时**：维持现行实现（B-1/B-5/B-6 有部分落地；B-2/B-3/B-4 悬空），主文口径保持"建议"措辞。

## 附录 C · 实测挂账台账（证据路径）

| 案例 | 事实（实测） | 证据 |
|---|---|---|
| 帝王类 | 崇祯→朱由检 3 处 / 顺治→福临 1 处 / 康熙→玄烨，均未入本书登记表致 unsourced | docs/47-江湖 §6.6-2 |
| 皇上时代歧义 | 030 万历朝回忆=朱翊钧；022-028 天启朝=由校；32 条 warning 根因"全局映射无回级作用域" | docs/47-语义 §四 |
| 皇上|朱翊钧 误注入 | 15 处（SKILL few-shot 示例映射误用）→ 按书内年代改康熙/允祯/不挂 | docs/47-江湖 §6.6-2 |
| 允禛|雍正 | 冰魄 2 处反向管道已摘；正确 canonical=胤禛 | docs/49 §2.5 |
| 飞红巾/哈玛雅 | 保留 333 处 `飞红巾|哈玛雅`；反向 26 处已摘；旧 KB 塞外双条 | docs/49 §五.8 / §2.5 |
| 晦明/岳鸣珂 | 白发 registry=岳鸣珂；塞外/七剑旧表=晦明禅师；冻结表与 registry 冲突 1 条 warning | docs/49 §五.8；docs/47-语义 §四 |
| 卓某 | 032[31]/[33] `卓某→卓一航` 与登记表 `卓某→卓仲廉` 冲突，两条保留 judgment | docs/44 §三、docs/42 §十.2 |
| 江湖 82 unsourced | S-03b 残余，按 §10.6 五分类消化 | docs/54 §四/§五.1 |
| 客氏/风砂堡/哈萨克 | `&1/@57`、`&2/=8`、`@7/#5/=2/◆2` 待清洗 | docs/53 §1.3 |
| 李钦差=李天扬 | 检索式考订三面证据（散文/管道/映射）已并入 03a 附录 B | docs/47-语义 §7.3；03a 附录 B |

## 附录 D · 字段/命令速查

| 用途 | 命令/文件 |
|---|---|
| 登记提案 | `python -X utf8 scripts/propose_entity_registration.py --book <书>` |
| 合并落盘 | `python -X utf8 scripts/apply_entity_registration.py --book <书> --apply` |
| 管道归一 | `python -X utf8 scripts/_oneshot/normalize_pipe_canonicals.py <书> --dry-run\|--apply` |
| 三来源验收 | `python -X utf8 scripts/accept_batch.py --book <书> --chapters <范围> --mapping-file logs/mapping_<书> --registry <登记表>` |
| 映射快照 | `python -X utf8 scripts/_oneshot/build_legacy_mapping.py <书>` |
| registry 结构 | `registry/entities.json`（entities[]；458 条实测） |
| 消耗口径 | `annotate_chapter_llm.load_mapping_table`（@ 且非 pending；400 条截断） |

---

## 结语

人名消歧不是"给每个名字找一个唯一答案"，而是**在正确的层上、用可复核的证据、给出该层要求的那个答案**：书内层求"这本书里读者指的是谁"，系列层求"整个武侠宇宙里这是不是同一个人"，管道只回答"这个显示串的规范名有无来源"。把三层分清、把无证据的留白、把有证据的落表——这就是 S-03b 的全部工作。**宁可留 pending，不可造 canonical。**
