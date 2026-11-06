---
name: skill-09b-wuxia
title: 游戏化（武侠版）——关卡、成就与可回溯的玩法映射
description: 武侠知识库游戏化规范：把 EX-4 关系图（489 节点/907 边）、N10 SKU 卡（1,502）、EX-5 对局与评级（341 场/194 人，Glicko-2）、事件层（22,978 条）与章回结构映射为关卡/成就/图鉴/对局推演。坚持映射法（数据字段→玩法要素）、开关架构（每种玩法可独立关闭）、六法则（目标/规则/反馈/自愿/叙事/社交）；所有难度/段位/阈值必须由公式从数据派生，推演必须标 simulate，禁虚构战绩、禁输出原文、禁把 demo 卡当考订。当需要设计关卡、成就、收集图鉴或对局推演时使用。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 09b 武侠版：游戏化 — 让考订数据"可玩"，但不可编造

> **上游声明**：本件属 S 组 P5 应用层，对应 docs/03 §3.10 原 09b 游戏化（**中度 60-65%**：映射法/开关架构/六法则照搬，换映射对象即用）。**无专属设计稿**：由 EX-4 `graph.json`、N10 `cards.json`、EX-5 `matches/ratings`、事件层、`01g §9.10` 发布边界、`03d H-1~H-10` 渲染契约、09g 隐私原则综合而成（v0.1 框架，附录 A/B 已标骨架与待补）。
> **接口**：`../site/data/graph.json`（EX-4）、`../site/data/matches.json` + `../site/data/ratings.json`（EX-5）、`registry/sku/cards.json`（N10，1,502 卡）、`registry/events/`（EX-5 事件层）、`../site/data/books.json` + `../site/data/chapters.json`（EX-1）、`content/person/`（W8 卡页，`demo:true`）。
> **核心原则**：**玩法要素必须是数据的投影，不是设定的发明；推演必须标"推演"，考订必须标"考订"。** 武侠 IP 自带游戏化传统（门派/比武/奇遇/收集），本层的任务是把已有考订数据映射成玩法，而不是替原著编战绩。

---

## 一、定位与边界

### 1.1 工序位置

```text
registry / EX 导出层（graph / matches / ratings / cards / events / chapters）
        ↓  只读
09b 游戏化（玩法映射 → 关卡 / 成就 / 图鉴 / 推演 schema）
        ↓
本地游戏态数据（progress / achievements / sim_runs）  ← 不入 site/data（H-10 同理）
```

### 1.2 本文做什么

1. **玩法映射**：把 6 类数据源映射为图鉴收集、关系地图、章节关卡、对局推演、事件任务、段位六种玩法要素；
2. **关卡/成就 schema**：给出可校验的 JSON 契约，每个字段挂 `source_refs`；
3. **数值派生**：章节难度 D、段位分位、成就阈值三类公式，禁止手填；
4. **推演规范**：基于 Glicko-2 评级与历史对局给概率，必须标 `simulate:true` + 免责声明；
5. **边界守卫**：无原文、无埋点、未审核实体不入关卡、demo 卡不当考订。

### 1.3 本文不做什么

| 不做 | 归属 |
|---|---|
| 改 registry / 事件 / 关系数据 | 只读（写操作属 P4 回写，需授权） |
| 实体/事件/关系考订 | `SKILL_07e_真实性评级_武侠版.md`、04/05 组 |
| 重新计算评级或改胜负 | EX-5 导出层（`scripts/export_site_matches_ratings.py`） |
| 输出原文段落 / 全文 | 禁（`01g §9.10`） |
| 用户行为埋点 / 云端同步 | 禁（对齐 09g：本地优先、可关闭） |
| 游戏引擎 / 前端实现 | 应用工程（本件只定契约，v0.1 无生成器，见附录 B） |

### 1.4 关键约束

- **可回溯**：关卡、成就、推演的每个数值都要能解析回数据字段或文件路径，抽检 10% 可复算；
- **推演标识**：概率结果一律 `simulate:true` + `disclaimer`，不得表述为"原著结局"或"史实胜负"；
- **开关架构**：每种玩法模块带 `enabled` 开关，默认全关；demo 态只读不写进度；
- **不发布原文**：关卡目标用实体/事件/定位符描述，不嵌正文片段；卡面来自 `content/person/` 且 `demo:true` 不可当考订；
- **未审核不入**：`registry status=pending` 的实体不得成为关卡目标或成就条件（对应 `03d H-9`）；
- **本地进度**：progress 文件只落本地目录，禁止进 `site/data` 或公网静态目录（对应 `03d H-10`）。

---

## 二、快速开始（五步）

````text
Step 1 取数   只读读取 graph / matches / ratings / cards / chapters（导出脚本默认 dry-run）
Step 2 选玩法 图鉴收集 / 关系地图 / 章节关卡 / 对局推演 / 事件任务 / 段位（可多选，各自开关）
Step 3 映射   按 §三 映射表把数据字段接到玩法要素，逐条写 source_refs
Step 4 定值   难度 D / 段位分位 / 成就阈值全部按 §五 公式派生，禁手填
Step 5 校验   跑 §七 检查清单：可回溯、无原文、无 pending 实体、进度不入 site
````

只读取数示例（字段名以各导出文件 `meta.schema` 为准）：

```python
import json
from pathlib import Path

D = Path('../site/data')
graph = json.load(open(D / 'graph.json', encoding='utf-8'))
matches = json.load(open(D / 'matches.json', encoding='utf-8'))
ratings = json.load(open(D / 'ratings.json', encoding='utf-8'))
books = json.load(open(D / 'books.json', encoding='utf-8'))
cards = json.load(open('registry/sku/cards.json', encoding='utf-8'))

print(graph['meta']['totals'])                    # nodes/edges/persons（489/907/260）
print(matches['meta']['totals'])                  # matches/fighters（341/194）
print(ratings['meta']['totals'], ratings['meta']['tiers'])   # players + 段位边界
print(books['meta']['totals'])                    # books/chapters/chars（34/1378/17,004,474）
print(cards['meta']['counts'])                    # 五类卡计数（合计 1,502）
```

> 取数只读；`scripts/export_site_all.py` 缺省 dry-run，只有显式 `--apply` 才写 `site/data`（写操作不在本件范围）。

---

## 三、玩法映射表（映射法核心）

| 数据源 | 可用字段 | 玩法要素 | 硬约束 |
|---|---|---|---|
| `graph.json` | `nodes[].id/type/n/books`、`edges[].s/t/kind/label/n/locs` | 关系地图、师承链、对手网、关系收集 | 只用 `kind` 已存在的谓词，不自造关系；`locs` 只作定位展示 |
| `cards.json` | `cards[].name/aliases/faction_history/seniority/teachers/arts/brief/meta` | 图鉴收集、卡面、门派归属 | `brief` 随卡展示来源与置信；demo 卡标 demo |
| `matches.json` | `matches[]` 对手对、`fighters` | 对局回顾、战绩页、宿敌识别 | 只回放已抽取对局（341 场），不补写未抽取场次 |
| `ratings.json` | `players[].r/rd`、`meta.tiers` | 段位、匹配权重 | 段位 = 分位映射，公示分位边界与 `data_version` |
| `registry/events/` | 22,978 条事件：13 类（T01-T13）、`outcome` 五态、`confidence` | 事件任务、章节关卡目标 | `outcome=未决/未知` 不得被写成胜负；低置信事件不作唯一目标 |
| `books/chapters` | 34 部/1,378 回；`chapters[]` 的 `events/verbs/chars/stream` | 章节关卡骨架、目录、难度基数 | 回目取自 `chapters.json`，不改写、不补写 |
| `content/person/` | W8 卡页 367 页，`demo:true`、`quotes[]` | 卡面/收集展示 | demo 卡不得当考订结论；引文入口走 W7 |

**六法则（照搬，仅换映射对象）**：目标明确（每关一个可判定目标）、规则简单（目标一句话说清）、反馈即时（进度/图鉴即时可见）、自愿参与（全部可关）、叙事包裹（用回目/门派/关系做壳，不新增设定）、社交可选（分享只分享进度摘要，不上传原始数据）。

---

## 四、产物 schema（v0.1 约定）

### 4.1 关卡 `level`

```json
{
  "id": "lv-qijian-004",
  "type": "chapter",
  "name": "七剑下天山·第四回",
  "source_refs": ["七剑下天山#pn-r4", "chapters.json#七剑下天山/chapters[4]"],
  "difficulty": 2,
  "difficulty_basis": {"events": 12, "entities": 31, "fences": 1, "chars": 2800},
  "objectives": [{"kind": "identify", "target": "@练霓裳", "evidence": "graph:nodes/练霓裳"}],
  "gates": ["完成上一回"],
  "reward": {"kind": "card", "ref": "cards.json#cards[name=练霓裳]"},
  "simulate": false,
  "publish_state": "local-only"
}
```

`type ∈ {chapter, event, relation, person, match, sect}`；`objectives[].kind ∈ {identify, connect, collect, resolve, replay}`。

### 4.2 成就 `achievement`

```json
{
  "id": "ach-sect-wudang-01",
  "name": "武当门下",
  "tier": "bronze",
  "condition": {"kind": "collect", "where": {"faction_history": "武当"}, "count": 12},
  "progress_source": "cards.json#cards[].faction_history",
  "evidence": ["cards.json#card_index"],
  "computable": true
}
```

`condition.kind ∈ {collect, complete, connect, identify, replay}`；`computable=false` 的成就**不得上线**（无法校验等于无法判真）。

### 4.3 进度 `progress`（本地）

```json
{"schema": "game-progress-v0.1", "local_only": true, "levels": {}, "achievements": {}, "sim_runs": [], "updated_at": null}
```

`updated_at` 只在运行时写入；progress 不得进入 `site/data`、`content/`、`public/` 任一发布目录。

### 4.4 推演 `sim`

```json
{
  "simulate": true,
  "a": "凌未风",
  "b": "楚昭南",
  "basis": {"ratings": {"a": {"r": 1500, "rd": 350}, "b": {"r": 1500, "rd": 350}},
            "h2h": {"matches": null, "note": "由 matches.json 统计填入，禁手填"}},
  "result": {"p_a": null, "note": "由 §五 公式计算后填入"},
  "disclaimer": "推演基于 Glicko-2 评级与历史对局，非原著结局，非考订结论。"
}
```

**铁律**：`result.p_a` 必须由公式算出并留计算输入；`basis.h2h.matches` 必须来自 `matches.json` 实际计数；任一输入缺失时输出 `p_a:null` 并降级为"不可推演"，不得用常识估一个数。

---

## 五、数值派生公式（禁手填）

### 5.1 章节难度 D ∈ [1,5]

```text
raw = 0.4*事件数 + 0.3*实体数 + 0.2*围栏块数 + 0.1*(章长/全书章长中位数)
D   = 1 + 4 * pct_rank(raw)        # pct_rank 为全书（或全系列）分位，∈[0,1]
```

输入全部来自 `chapters.json`（`events` / `chars` / `verbs` / 长度）与 struct 围栏计数；分位分母必须写明（全书/系列/五书点亮集）。

### 5.2 段位分位（基于 `ratings.json`）

`meta.tiers` 已给边界（绝顶 1581 / 超一流 1552 / 一流 1520 / 二流 1486）：段位判定必须用**同一 `data_version` 的边界**，换版本必须重算；公示文案写明"评级由 341 场对局 + Glicko-2 拟合，v0 未做 holdout 抽检"（见 `ratings.meta.calibration`）。

### 5.3 成就阈值三档

```text
收集类：count = round(该类卡总量 * k)，k ∈ {0.1, 0.3, 0.6}   # 铜/银/金
事件类：count ≤ 该 T 类型事件总数（先查 registry/events 计数）
关系类：count ≤ 图内该类 kind 边数（先查 graph.meta.totals 与按 kind 统计）
```

任一类可用总量为 0 时，该成就不得生成（例如 T13 容器类事件极少，不得设"完成 10 次容器战"）。

---

## 六、工具与脚本

| 脚本/文件 | 用途 | 备注 |
|---|---|---|
| `scripts/export_site_all.py` | 8 类 EX 导出（含 graph/matches/ratings） | 缺省 dry-run，`--apply` 才写盘 |
| `scripts/export_site_graph.py` | EX-4 关系图 | 节点/边聚合规则见 `graph.meta.notes` |
| `scripts/export_site_matches_ratings.py` | EX-5 对局 + Glicko-2 评级 | 胜负来自事件层 `outcome` 投影 |
| `scripts/build_sku_cards.py` | N10 SKU 卡（1,502） | 五卡字段与 `w8_w9_interface` |
| `scripts/generate_w8_pages.py` | W8 卡页（367 页，`demo:true`） | 其余四类卡留 `build_page()` 接口 |
| `scripts/lint_skills.py` | 本件自检 | `python -X utf8 scripts/lint_skills.py "skills/SKILL_09b_游戏化_武侠版.md"` |

> **v0.1 无游戏化生成器**：当前玩法产物靠本文映射表 + 只读脚本取数 + 人工/前端按 schema 组装；生成器与校验器列入附录 B。

---

## 七、错误模式库（GM 系列）

| ID | 错误 | 表现 | 检测 | 修正 |
|---|---|---|---|---|
| GM-01 | 虚构战绩 | 关卡/推演出现原著没有的胜负 | 与 `matches.json` 对局表比对 | 删改，改标 `simulate:true` 或降级为"不可推演" |
| GM-02 | 难度手填 | `difficulty_basis` 与公式复算不符 | 抽检 10% 复算 | 全部改公式派生 |
| GM-03 | 引用 pending 实体 | 关卡目标含 `status=pending` 实体 | 与 registry status 对照 | 剔除或等审核 |
| GM-04 | demo 当考订 | 卡面 demo 字段被写成结论 | 检查 `meta.demo`/`demo:true` | 加"演示数据"标注，不进入成就证据 |
| GM-05 | 输出原文 | 关卡描述/推演文案嵌正文片段 | 发布产物与底本子串比对 | 删除，改定位符 |
| GM-06 | 玩法不可关 | 模块无 `enabled` 开关 | schema 校验 | 补开关，默认关 |
| GM-07 | 成就不可计算 | `computable=false` 仍上线 | 校验 `progress_source` 可解析 | 下线或改条件 |
| GM-08 | 进度入站 | progress 出现在 `site/data` | 路径审计（对应 H-10） | 移出并加 `.gitignore` 类防护 |

---

## 八、检查清单

### 设计前

- [ ] 已确认 `graph/matches/ratings/cards/chapters` 的 `meta.schema` 与 `data_version`；
- [ ] 已选定玩法模块并逐项声明 `enabled`（默认关）；
- [ ] 已确认目标实体/事件不在 `status=pending` 集合；
- [ ] 已确认所需 T 类型/关系 kind 的实际总量 > 0。

### 产出前

- [ ] 每个关卡/成就的 `source_refs` 可解析到具体文件与字段；
- [ ] 难度/段位/阈值均由 §五 公式派生，附计算输入；
- [ ] 推演带 `simulate:true` + `disclaimer`，缺失输入时为 `null`；
- [ ] 无正文片段；卡面标 demo；无埋点字段。

### 交付前

- [ ] 抽检 10% 关卡复算一致；
- [ ] progress/sim_runs 不在任何发布目录（`site/data`、`content/`、`public/`）；
- [ ] 开关默认全关，可一键停用全部玩法；
- [ ] 附数据版本/规则版本与已知偏差说明（评级 v0 未做 holdout）。

## 九、成功标准（v0.1）

1. **可回溯率 100%**：关卡/成就/推演字段均可解析回数据源，抽检 10% 复算误差 0；
2. **手填率 0**：难度/段位/阈值无一处人工拍数；
3. **原文泄漏 0**：发布产物与底本子串比对为空；
4. **推演标识 100%**：所有概率结果带 `simulate:true` + 免责声明；
5. **越界 0**：无 pending 实体入目标、无 demo 卡作考订、无进度入站；
6. **可关停**：任一玩法模块可独立关闭且不影响其他模块。

---

## 十、FAQ（首批 5 问）

**Q1：武侠 IP 不是自带游戏化吗，为什么还要"映射法"？**
自带的是题材联想（门派/比武），不是可校验的玩法数据。映射法要求每个玩法要素都指回 `graph/matches/cards/events` 的具体字段，否则就是同人设定。

**Q2：对局推演会不会误导用户以为是原著结果？**
所以强制 `simulate:true` + `disclaimer`，且 `p_a` 必须由公式与真实输入算出；输入缺失时输出 `null` 并显示"不可推演"。

**Q3：评级只有 341 场、v0 未做 holdout，能用来做段位吗？**
可以，但只能作**游戏化段位**，不能作考订结论；文案必须同时给"341 场 / Glicko-2 / v0 未抽检"三个限定，边界换版本必须重算。

**Q4：为什么不用全部 22,978 条事件做关卡？**
事件质量分层：`confidence=low` 与 `outcome=未知` 的事件不宜作唯一目标；关卡目标优先 `high` 且 `outcome` 明确的 T01/T02/T03/T11。

**Q5：图鉴收集会不会把 demo 卡当成真数据？**
卡面随卡展示 `demo:true` 与来源；成就证据只认 `cards.json` 字段，不认卡面演示文案。

---

## 十一、相关文档

- `SKILL_09_应用总览_武侠版.md`（应用层命名与 P5 状态）
- `SKILL_09g_个性化_武侠版.md`（隐私/开关/本地优先，本件沿用）
- `SKILL_09f_可视化_武侠版.md`（graph/universe 五类可视化契约）
- `SKILL_03d_渲染发布_武侠版.md`（H-1~H-10 渲染与发布边界）
- `SKILL_07e_真实性评级_武侠版.md`（A-E 评级；本件不重算）
- `docs/59`（EX-5 事件层与 W7）、`docs/60`（S 组 P5 与站点验收）

---

## 附录 A · 与 shiji 原版差异对照（本件为骨架+综合）

| 维度 | shiji 09b 游戏化 | 本件（武侠版） | 性质 |
|---|---|---|---|
| 映射法 | 数据→玩法要素 | 照搬，映射对象换为 graph/cards/matches/events | 照搬 |
| 开关架构 | 每玩法可独立关闭 | 照搬（`enabled` 默认关） | 照搬 |
| 六法则 | 目标/规则/反馈/自愿/叙事/社交 | 照搬，叙事壳换为回目/门派/关系 | 照搬 |
| 数值派生 | 原设计给公式框架 | 本件自拟 D/分位/三档阈值公式（无专属设计稿） | 骨架+综合 |
| 推演 | 原设计未细化 | 本件加 `simulate:true` + 缺失输入 `null` 铁律 | 骨架+综合 |
| 边界 | 通用发布边界 | 接 `01g §9.10`、`03d H-9/H-10`、09g 隐私 | 骨架+综合 |
| 原文 | 不适用 | 禁输出正文，关卡用定位符 | 武侠特有 |

## 附录 B · v0.1 待补清单

1. **游戏化生成器**：scripts/build_game_levels.py（关卡/成就/推演生成 + schema 校验）未实现；
2. **校验器**：`source_refs` 解析、难度复算、pending 实体扫描、原文泄漏扫描未脚本化；
3. **进度存储**：本地存储格式与恢复策略未定（v0.1 只给 schema）；
4. **关系地图玩法**：`graph` 仅 5 书 N5 投影（907 边），跨书对局/武功边未导出，玩法覆盖面受限；
5. **评级可信度**：Glicko-2 v0 未做 holdout，方向抽检 100 场待办；
6. **前端契约**：与站点 `NetworkGraph`/卡页组件的接口未对接（当前 NetworkGraph 只区分 @/☆/◆）。

---

## 结语

游戏化在本项目里的位置是**数据的下游**：它只能放大已有考订的可玩性，不能反过来生产"看起来像考订"的设定。守住"可回溯 + 推演标识 + 开关 + 无原文"四条，玩法才能既好玩又不污染知识库。
