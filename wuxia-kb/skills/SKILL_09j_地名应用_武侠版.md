---
name: skill-09j-wuxia
title: 地名应用（gazetteer 消费：双图层渲染·行踪地图·问答降级）
description: 武侠知识库地名库（gazetteer）的应用层规范：把 registry/gazetteer.json（650 条、nature 四值、kind 13 值、loc_mode 四值）消费为行踪地图、地点详情、人物轨迹、地点筛选与江湖问答，包括双图层渲染协议（real/fiction）、相对锚点与锚点链、unlocatable 显式弃权的问答话术、conf 降级显示与升级路径，以及 N7 迁移产物的字段口径。当需要"把地点数据画到地图上、地点页字段怎么取、问答问位置怎么答、弃权条目怎么显示"时使用；地名登记规范见 SKILL_地名gazetteer（D10）。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 09j 武侠版：地名应用

> **上游声明**：本文是 D10 地名 Gazetteer（`SKILL_地名gazetteer_武侠版.md`）的**应用层执行件**：F01-F20 schema、双图层策略、显式弃权 U1-U4、相对锚点语法、status/verified/conf 档位由 D10 定版；本文只负责"已登记的地名数据怎么被页面/地图/问答消费"。数据迁移与登记校验为 N7 `scripts/gazetteer_migrate.py`（`registry/gazetteer.json`，650 条 100% 守恒迁移、30 项断言 PASS）；地点分类树由 `SKILL_分类树五件套_武侠版.md`（D08）定版。
> **移植依据**：`docs/05-管线技能与脚本逐项改造分析.md`（09j 历史地图：M01-M13 迁移映射/双图层/nature 四值）；`docs/17` §2.5（S-09j ←D10）；`docs/57` §五（N7 实跑：nature 真实 624/虚构 3/未定 23；kind 76 脏值→13 值；loc_mode coord 619/none 31；30 项断言 PASS）。
> **核心原则**：**真实图层给坐标，虚构图层给锚点，定位不了给弃权**。渲染端不得为虚构点编造坐标；问答端不得为 unlocatable 条目编造方位。

---

## 一、技能定位与边界

### 1.1 工序位置（地名消费层）

```text
D10 gazetteer 登记规范（F01-F20/双图层/弃权）
        ↓ N7 迁移/登记
registry/gazetteer.json（650 条；meta + places[]）
        ↓
S-09j 地名应用（本文）：过滤 → 图层分流 → 落位 → 渲染 → 问答话术 → 统计
        ↓
行踪地图 /atlas · 地点详情页 · 人物轨迹 · 地点筛选着色 · 江湖问答 · 全站搜索
```

- **前置**：`registry/gazetteer.json` 可用（N7 已 apply）、D08 地点树 kind 与 gazetteer kind 同源、PN 定位符（02ab）可用。
- **后继**：行踪地图/地点页（W 组）、人物档案轨迹、问答、搜索。
- **现行事实（2026-11-05）**：gazetteer 650 条（真实 624/未定 23/虚构 3）；kind 13 值；loc_mode coord 619/none 31；layer real 628/fiction 22；conf ok 612/strong 3/weak 35；status 全 auto；30 项断言 hard_fail 0。

### 1.2 本文做什么（五件事）

1. **过滤与分流**：status/nature/layer/loc_mode 的消费过滤（§四）；
2. **双图层落位**：真实图层坐标落点、虚构图层锚点 join、锚点链渲染（§五）；
3. **渲染协议**：必读字段与降级显示（§六）；
4. **问答话术**：unlocatable/weak/conf 的降级回答模板（§七）；
5. **运营与升级**：候选→登记→校准→升级路径的消费侧配合（§八）。

### 1.3 本文不做什么（边界，越界即错）

- **不登记地名**：新增/修订条目走 D10 登记流程（本文只消费）；
- **不给虚构点配坐标**：虚构图层只渲染锚点落位，禁止折算经纬度（D10 G02）；
- **不重算 conf/status**：conf 由 D10 §6.4 派生、status 由 D10 §6.3 生命周期管理，本文只读取；
- **不重定义 kind**：kind 与 D08 地点树同源，本文只做色板映射。

---

## 二、快速开始（四步消费序）

> 目标：把 gazetteer 消费到地图/页面/问答。命令只读。

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
$env:PYTHONIOENCODING='utf-8'

# Step 1 读库与总览（meta.stats：nature/kind/loc_mode/layer/conf/status）
python -X utf8 -c "import json;d=json.load(open('registry/gazetteer.json',encoding='utf-8'));print(json.dumps(d['meta']['stats'],ensure_ascii=False))"

# Step 2 过滤：status≠已弃用；按 nature/layer 分流（真实→坐标；虚构→锚点；none→降级）

# Step 3 落位：real+coord 直接落点；fiction+anchor 按 ref/bearing/distance join；none 显示问号

# Step 4 渲染/问答：按 §六 必读字段与 §七 话术输出
python -X utf8 -c "import json;d=json.load(open('registry/gazetteer.json',encoding='utf-8'));p=[x for x in d['places'] if x['loc_mode']=='none'][:3];print(json.dumps(p,ensure_ascii=False))"
```

**判读口径**：Step 1 的 stats 是消费总账（650 条/真实 624/虚构 3/未定 23/coord 619/none 31）；Step 2 的"已弃用"硬过滤必须执行（D10 §6.3）；Step 3 的虚构锚点渲染取 conf 最高者。

---

## 三、数据接口（registry/gazetteer.json）

### 3.1 顶层结构

| 字段 | 内容 |
|---|---|
| `meta.schema` | `wuxia-gazetteer-v1`（N7 产物） |
| `meta.generated/rev/source` | 生成时间/版本/来源（kb/gazetteer.json 迁移） |
| `meta.coord_system` | WGS-84（EPSG:4326） |
| `meta.books` | 书集 |
| `meta.stats` | total 650；by_nature/by_kind/by_loc_mode/by_layer/by_conf/by_status；unlocatable 31；with_coord 619；review_flags |
| `meta.assertions` | 30 项断言（hard_fail 0 / warn_fail 0） |
| `places[]` | 650 条（F01-F20 字段） |

### 3.2 单条字段（F01-F20 摘要，D10 §2.1）

`id`（中文规范名，永不改写）/`name`/`aliases`/`kind`（13 值）/`nature`（四值权威）/`real`（兼容派生）/`layer`（派生 real/fiction）/`books`/`first_seen`（`书名#pn-X.Y`）/`count`/`status`（auto/待审/已核准/已弃用）/`verified`/`loc_mode`（coord/proto/anchor/none）/`lat`/`lng`/`precision`（五级）/`anchor`（ref/bearing/distance/text/evidence/chain）/`unlocatable_reason`（no_clue/contradictory/chain_broken/legendary）/`source`/`hq_of`/`conf`（strong/ok/weak）。

### 3.3 现状统计（2026-11-05，N7 迁移）

| 维度 | 分布 |
|---|---|
| nature | 真实 624 / 未定 23 / 虚构 3 |
| kind | 城镇 210 / 山 96 / 山庄园林 72 / 区域 59 / 水域 57 / 寺观 31 / 关隘 28 / 宫廷 26 / 其他 65 / 寨堡 4 / 客栈 1 / 遗址战场 1（13 值；76 脏值已归一） |
| loc_mode | coord 619 / none 31 |
| layer | real 628 / fiction 22 |
| conf | ok 612 / strong 3 / weak 35 |
| status | auto 650（全部未人工校准，verified 全 false） |

---

## 四、过滤与分流（消费第一步）

### 4.1 硬过滤与软分流

| 过滤 | 规则 | 依据 |
|---|---|---|
| 硬过滤 | `status=已弃用` 条目一律不渲染（保留引用不物理删除） | D10 §6.3 |
| 硬过滤 | `verified` 语义：true ⟺ status=已核准 且定位经人工核验；auto/待审一律 false | D10 §6.3 |
| 软分流 | nature/layer → 真实图层/虚构图层 | D10 §三 |
| 软分流 | loc_mode → coord 落点 / proto 原型示意 / anchor 锚点 join / none 弃权 | D10 §三 |
| 降级显示 | conf=weak 不进"精确位置"类回答；未定条目加"待审"徽标 | D10 §6.4 |

### 4.2 分流决策表

| nature | loc_mode | 图层 | 渲染方式 |
|---|---|---|---|
| 真实 | coord | real | 坐标落点（precision=region 画范围圈） |
| 虚构 | anchor | fiction | 相对锚点 join（链深≥2 放大落点半径） |
| 虚构 | none | fiction | 弃权显示（问号/未知标记） |
| 原型改造 | proto/anchor | fiction | 原型示意坐标（加徽标）或锚点 |
| 未定 | 随 loc_mode | 随 loc_mode | 按 loc_mode 渲染 + "待审"徽标 |

---

## 五、双图层落位与锚点渲染

### 5.1 真实图层

- 坐标系 WGS-84；`lat/lng` 只在 loc_mode=coord 时使用；
- `precision` 五级消费：exact 精确点 / approx 约测点 / shifted 移位点 / region 画范围圈不画针 / proto 仅原型示意（加徽标）；
- 粒度纪律：区域给 exact = 错；具体建筑给 region = 错（D10 G09）。

### 5.2 虚构图层（锚点 join）

- 锚点三元组：`ref`（已登记条目 id，优先真实图层）+ `bearing`（八方位/拓扑词）+ `distance`（近 ≤50 里/中 50–500 里/远 >500 里，或确切里数）；
- 锚点链：`风砂堡 ← 天山道(chain2) ← 天山(真实,chain1)`；**链深上限 3 级**；逐级降信（链深 +1 → conf 降档）；禁止循环/断链；
- 多锚点：取 conf 最高者渲染，其余为备选证据；矛盾锚点按 D10 G11 登记冲突，不静默取舍；
- **禁止**把"京师以西三百里"折算成精确经纬度（G02）；示意落点只存在于渲染期。

### 5.3 弃权条目（none）

- 渲染为"位置未知"标记（D3 显示），不参与地图落点；
- 但**保留检索/统计/消歧/问答降级能力**（D10 §4.4）；
- 升级通道：新文证 → 补 anchor（none→anchor）；原型考订 → proto；真实考订 → coord（D10 §4.5）。

---

## 六、渲染消费协议（必读字段，D10 §6.5）

| 字段 | 用途 |
|---|---|
| `status≠已弃用` | 硬过滤 |
| `nature`/`layer` | 图层分流与样式（虚构/原型/待审徽标） |
| `loc_mode`（或派生 unlocatable） | coord 落点 / proto 示意 / anchor join / none 降级 |
| `lat`/`lng`+`precision` | 真实图层落点；region 画范围圈 |
| `anchor`（ref/bearing/distance/evidence/chain） | 虚构图层 join 落位 |
| `kind` | 分类着色（K01-K13 色板，页面侧定义） |
| `hq_of` | 门派驻地双身份（门派页联动） |
| `conf` | 渲染排序与问答置信（weak 不进精确回答） |

> **色板与样式**由页面侧定义；本文只规定"取哪些字段、怎么降级"，不规定视觉实现。

---

## 七、问答与降级话术

### 7.1 回答分级

| 条目状态 | 回答口径 | 例 |
|---|---|---|
| coord + exact/approx | 给出位置/坐标/方位，注明精度 | "天山位于今新疆中部（约测点）" |
| coord + region | 给出区域范围，不给点 | "陕北为区域泛称，约指陕西北部" |
| anchor + 一级/确切里数 | 给出相对方位与距离 | "风砂堡在天山以北（约近带）" |
| anchor + 链深≥2/拓扑词 | 给相对方位，明确"约略/不确定" | "冰窟位于天池附近，位置为书中相对描述" |
| none（unlocatable） | **"书中未交代确切位置"** + 已知线索（首现/出现回目/关联门派） | 不得编造方位 |
| 未定 nature | 回答加"地点性质待考" | 不得默认真实 |

### 7.2 话术纪律

- 不得把 weak 锚点说成精确位置；不得把 region 说成点；不得为 none 编造方位（D10 弃权原则）；
- 跨书同名地点回答须带书名限定（`龙门镇@白发魔女传`）；
- 冲突锚点回答须并列两说（不静默取一）；
- 引用定位用 `书名#pn-X.Y` 指针，不引原文长句（版权红线）。

---

## 八、运营与升级（消费侧配合）

### 8.1 候选→登记→校准→消费

```text
候选（01g 扫描/别名表/词表兜底）→ 判重归并 → 初判登记(auto) → 人工校准(待审) → 终审(已核准) → 渲染消费
```

消费侧职责：只消费 `status=已核准`（或显式允许 auto 的展示层）；待审/未定条目加徽标；发现矛盾（新书写了不同方位）反馈登记侧回退待审。

### 8.2 升级路径（D10 §4.5）

1. 新文证（后文方位表述）→ 补 anchor，none→anchor，reason 清空，status 走 auto→待审→已核准；
2. 考订发现原型 → 原型改造（nature 改判 + loc_mode=proto）或真实（nature 改判 + coord）；
3. 一切升级走校订台账留痕，不原地静默覆盖。

### 8.3 与 N7 的配合

- N7 `scripts/gazetteer_migrate.py`：`--dry-run`（默认，算+写报告）／`--apply`（写 registry，写前备份）／`--strict`／`--selftest`；
- 迁移纪律：kb 只读（sha256 不变）、100% 守恒、30 项断言；
- 复跑迁移前确认无消费侧依赖破坏（id 不变、字段只增不删）。

---

## 九、工具与脚本

| 工具 | 用途 | 关键参数 |
|---|---|---|
| `scripts/gazetteer_migrate.py`（N7） | kb/gazetteer.json → registry/gazetteer.json 迁移/校验 | `--dry-run/--apply/--strict/--selftest` |
| `scripts/build_entity_concordance.py` | 地点实体对照（books/first_seen 旁证） | `--book` |
| `scripts/export_site_all.py` | 站点导出（地图/地点页数据消费） | `--apply` |
| `scripts/lint_consistency.py`（N8） | 设定一致性（地点矛盾旁证） | `--selftest` |

产物：`registry/gazetteer.json`（523KB）、`logs/gazetteer/migrate_report.md`；渲染数据由 EX 导出器产出（site/data）。

---

## 十、检查清单

**消费前**
- [ ] `registry/gazetteer.json` 版本/断言核对（hard_fail 0）；
- [ ] 硬过滤已实现（status=已弃用不渲染）；
- [ ] nature/layer/loc_mode 分流逻辑就绪。

**消费中**
- [ ] 真实图层只用 coord 坐标；虚构图层只用 anchor；
- [ ] 锚点链 ≤3 级、无循环/断链；多锚点取 conf 最高；
- [ ] region 不画针、proto 带徽标、none 显示未知；
- [ ] weak 不进精确回答；未定加"待考"徽标；
- [ ] 引用定位只用 `书名#pn-X.Y` 指针。

**消费后**
- [ ] 问答话术按 §7.1 分级；
- [ ] 跨书同名带书名限定；
- [ ] 发现矛盾已反馈登记侧（冲突登记）；
- [ ] 统计口径（分母/范围）随页面标注。

---

## 十一、成功标准（Success Criteria）

1. **零编造**：虚构点配坐标 = 0；none 条目编造方位 = 0。
2. **图层正确**：real/fiction 分流 100%；region/proto/anchor/none 渲染方式正确。
3. **降级合规**：weak/未定/待审条目全部有降级显示或话术限定。
4. **可追溯**：每个落点可回链 `first_seen`/anchor.evidence 的 `书名#pn-X.Y`。
5. **数据守恒**：N7 迁移后 650 条 id 不变、字段只增不删、断言 PASS。
6. **问答可用**：位置类问答 100% 按分级话术回答，无臆造方位。

---

## 十二、相关文档

- `SKILL_地名gazetteer_武侠版.md`（D10，schema/双图层/弃权/锚点/运营）
- `SKILL_分类树五件套_武侠版.md`（D08，地点树 kind 同源）
- `SKILL_词表体系规划_武侠版.md`（D09，WL-20 接口注记）
- `SKILL_02a_02b_章回结构与韵文处理.md`（PN 定位符）
- `SKILL_03b_人名消歧_武侠版.md`、`SKILL_跨书治理_武侠版.md`（同名地点消歧）
- `docs/57-依赖分波与8路并行执行记录-2026-11-05.md`（N7 基线）

---

## 附录 A · 查询/渲染示例

### A.1 真实图层条目（节选）

```json
{"id": "天山", "name": "天山", "kind": "山", "nature": "真实", "real": true,
 "layer": "real", "loc_mode": "coord", "lat": 42.213, "lng": 80.71,
 "precision": "approx", "books": {"七剑下天山": [0,1,3], "塞外奇侠传": [1,2]},
 "first_seen": "七剑下天山#pn-0.1", "count": 295, "status": "auto",
 "verified": false, "conf": "ok"}
```

### A.2 虚构图层条目（节选）

```json
{"id": "风砂堡", "kind": "寨堡", "nature": "虚构", "layer": "fiction",
 "loc_mode": "anchor",
 "anchor": [{"ref": "天山道", "bearing": "北", "distance": {"value": null, "unit": "里", "tier": null},
             "text": "天山道以北", "evidence": "白发魔女传#pn-31.0", "chain": 2}],
 "count": 11, "status": "auto", "verified": false, "conf": "weak"}
```

### A.3 弃权条目（节选）

```json
{"id": "某山庄", "kind": "山庄园林", "nature": "未定", "loc_mode": "none",
 "unlocatable_reason": "no_clue", "status": "auto", "verified": false, "conf": "weak"}
```

## 附录 B · 待拍板（引 D10 附录 B，不在本文重开）

1. 距离档 `unit=日路程` 的换算口径（B14 类）；
2. `precision` 阈值与区域圈半径口径；
3. 锚点链深上限与落点半径放大系数（语义已定，数值待试点校准）；
4. 跨书同名地点限定符命名规范（与 D07/S-03j 统一）；
5. 弃权条目的问答话术是否统一模板（本文 §7.1 为建议稿）。

*本文为地名应用执行件；数据口径冲突时以 D10（`SKILL_地名gazetteer_武侠版.md`）为准。*
