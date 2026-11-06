---
name: skill-09f-wuxia
title: 可视化（武侠版）——图谱/时间轴/地图/排行榜的数据契约与渲染边界
description: 武侠知识库可视化规范：五类可视化（关系网络/时间轴/地图/排行榜/覆盖热力）的数据源与契约（EX-4 graph、EX-5 matches/ratings、EX-7 gazetteer/atlas/universe、N5 relations、N4 time、08b 覆盖数据）、交互与降级、渲染边界（03d AST/HTML；站点组件 NetworkGraph/MapTrail 已有）、口径声明与发布边界。当需要为武侠数据设计图/时间轴/地图/榜单，或扩展站点可视化组件时使用。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 09f 武侠版：可视化 — 让关系、时间、地理"看得见"

> **上游声明**：本件属本批 C1 应用组新划定 09f，对应 docs/03 §3.10 原 09i 信息图 / 09j 历史地图 / 09d 语义搜索可视化（判定：09i ✅ 照搬、09j 中度 65:35 方法照搬+虚构地名硬缺口；docs/05 §2.5 09d/f/g/h 轻度 75-88%）。**无专属设计稿**：由 03d 渲染契约、EX-4/EX-5/EX-7 数据契约、D10 双图层、D07 系列谱系综合而成（v0.1 框架）。
> **接口**：EX-4 `graph.json`（489 节点/907 边）；EX-5 `matches.json`（215 场/161 选手）+`ratings.json`（Glicko-2 161 玩家/4 档）；EX-7 `gazetteer.json`（619 点）/`universe.json`（6 lines/14 chronology_spine/22 seeds）/`atlas/<书>.json`（4 书+冰魄 staging）；N5 `registry/relations`（910 边）；N4 `registry/time`；08b 覆盖数据。
> **核心原则**：**可视化只映射数据，不制造数据。** 每个图形元素可回溯到数据记录；榜单/排名必须带口径声明；地图不伪造坐标（unlocatable 显式弃权）。

---

## 一、定位与边界

### 1.1 工序位置

```text
数据层（EX-4/5/7、N4/N5、08b）→ 09f 可视化（契约/交互/降级）→ 站点组件/阅读器
        ↓
口径声明 + 发布边界（01g §9.10）→ 用户
```

### 1.2 本文做什么

1. **五类可视化的数据契约**：关系网络/时间轴/地图/排行榜/覆盖热力；
2. **交互设计**：点击/筛选/联动/图例/无障碍；
3. **降级策略**：数据缺失/低置信/跨书 low 的展示规则；
4. **渲染边界**：03d AST/HTML 契约、站点组件现状（NetworkGraph/MapTrail/PathFinder 等）；
5. **口径与发布**：统计口径声明、原文不出、版权。

### 1.3 本文不做什么

| 不做 | 归属 |
|---|---|
| 数据生成/导出器 | EX-4/5/7（已落地） |
| 页面样式/复杂前端 | `../site/`（W/前端批次） |
| 地图坐标考订 | D10/N7/09j |
| 榜单规则拍板（如评分体系） | 09h/应用决策（本文只要求口径） |

### 1.4 关键约束

- **可回溯**：节点/边/点/条目带 id/loc/数据版本；
- **不伪造**：地图无坐标→unlocatable 显式弃权；榜单无样本→不排名；
- **low 标注**：跨书年代/低置信关系/推算统计必须标"参考"；
- **原文不出**：可视化不渲染原文段落/连续片段（01g §9.10）。

---

## 二、快速开始（四步）

````text
Step 1 选型   关系网络/时间轴/地图/排行榜/覆盖热力
Step 2 取数   EX-4/EX-5/EX-7/N4/N5/08b（只读；记数据版本）
Step 3 定契约 节点/边/轴/点/榜字段 + 交互 + 降级 + 口径
Step 4 验收   可回溯抽检、口径声明、发布边界、构建 exit 0
````

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
$env:PYTHONIOENCODING='utf-8'

# 数据体检
python -X utf8 -c "import json;d=json.load(open('../site/data/graph.json',encoding='utf-8'));print(len(d['nodes']),len(d['edges']))"
python -X utf8 -c "import json;d=json.load(open('../site/data/ratings.json',encoding='utf-8'));print(len(d['players']))"
python -X utf8 -c "import json;d=json.load(open('../site/data/gazetteer.json',encoding='utf-8'));print(len(d['places']))"

# 站点构建
cd ..\site; npm run build; cd ..\wuxia-kb
```

**成功标准**：① 每类图有字段契约与数据源版本；② 元素可回溯（id/loc）；③ 榜单带口径声明与样本量；④ 地图 unlocatable 正确弃权；⑤ 低置信视觉降级；⑥ 构建 exit 0、组件无契约报错；⑦ 无原文片段。

---

## 三、五类可视化与数据契约

### 3.1 关系网络（EX-4 graph）

| 字段 | 用途 | 降级 |
|---|---|---|
| `nodes[].id/type/n/books` | 节点大小=度数/次数 | 无数据→不渲染 |
| `edges[].s/t/kind/n/label/locs/books` | 边种类/权重/定位 | weak 边虚线/隐藏 |
| `meta.edge_confidence` | 置信分层 | 低置信降透明 |

- 交互：点击节点→实体档案；筛选 kind/type/书；高亮路径；
- 注意：sects=0（N5 无 ◆/• 端点）、前端仅区分 @/☆/◆ 类型（W 组重设计后扩展）。

### 3.2 时间轴（EX-7 universe + N4 time）

| 数据 | 用途 | 降级 |
|---|---|---|
| `universe.chronology_spine`（14 段） | 系列编年骨架 | 无锚→只列书序 |
| `universe.lines`（6 线） | 系列谱系 | — |
| `N4 time_points`（书内刻度） | 单书时间轴 | 未解析→不定位 |
| 跨书年代（07a low） | 参考区间 | 标"参考/区间" |

- 纪律：跨书年代只显示区间+"参考"，不显示伪精确年份（07a）。

### 3.3 地图（EX-7 gazetteer/atlas + 09j）

| 数据 | 用途 | 降级 |
|---|---|---|
| `gazetteer.places[].lat/lng/precision/kind/real` | 真实/虚构双图层 | unlocatable→列表/无坐标 |
| `atlas/<书>.json` chapters/persons/places/bychap/events | 分回行踪/事件 | 无数据→空层 |
| 09j 双图层 | 真实经纬度 vs 虚构相对锚点 | 虚构不配坐标 |

- 纪律：unlocatable 显式弃权（D10）；虚构地名用相对锚点展示；不伪造坐标。

### 3.4 排行榜（EX-5 matches/ratings）

| 数据 | 用途 | 口径要求 |
|---|---|---|
| `ratings.players[].rating/rd/tier/matches_n/w-d-l` | Glicko-2 榜 | 起评/样本/口径声明 |
| `matches[].outcome/weight/kind` | 对局明细 | 胜负五值/未决不入榜 |

- 纪律：榜单必须标注"样本量/口径/数据版本"（01g §9.9 + 03l）；低样本不排名。

### 3.5 覆盖热力（08b）

| 数据 | 用途 | 口径 |
|---|---|---|
| 08b 五维覆盖/缺口 | 书×维热力图 | 分母声明（正文/全文） |
| N9 taxonomy 覆盖 | 64 叶挂叶状态 | 挂叶率 |

- 纪律：热力图分母必须声明（08b §3.1）；覆盖≠正确（标 08d）。

---

## 四、交互与降级规则

| 场景 | 规则 |
|---|---|
| 低置信（weak/low） | 虚线/半透明/默认隐藏（可开） |
| 数据缺失 | 显式"暂无数据"，不补造 |
| 跨书数据 | 标"跨书/参考"，不与单书事实混排 |
| 冲突（多源） | 争议区双记（D07 §3.4） |
| 点击 | 可跳实体档案/证据面板（id 可回溯） |
| 无障碍 | 颜色+形状双编码；图例可读；键盘可达 |
| 性能 | 大数据分片/懒加载（1,536 卡/22,978 事件不一次渲染） |

---

## 五、渲染边界与站点现状

| 组件（现状） | 数据 | 扩展点 |
|---|---|---|
| NetworkGraph | graph.json | 扩展类型/边筛选/置信分层 |
| MapTrail / PathFinder | gazetteer/atlas | 双图层/unlocatable 列表 |
| RatingExplorer | ratings/matches | 口径声明/样本量 |
| EntityExplorer | characters/dossiers | display 字段（已切） |
| QaExplorer | QA 数据 | 09a 问答接口 |

- 渲染契约：遵循 03d AST/HTML（阅读器内嵌图）；站点侧遵循 site/data 14 契约（docs/51 §五）；
- 禁止：地图伪造坐标、榜单无口径、图内嵌原文片段。

---

## 六、工具与脚本

| 用途 | 工具 | 说明 |
|---|---|---|
| 图导出 | `scripts/export_site_graph.py` | EX-4 |
| 地图导出 | `scripts/export_site_gazetteer_universe.py` | EX-7 |
| 评分导出 | `scripts/export_site_matches_ratings.py` | EX-5 |
| 数据统一导出 | `scripts/export_site_all.py` | 8 导出器 |
| 覆盖数据 | `scripts/lint_taxonomy.py` / `compute_annotation_coverage.py` | 08b/N9 |

---

## 七、错误模式库（VZ 系列）

| # | 错误 | 检测 | 修正 |
|---|---|---|---|
| VZ-01 | 伪造地图坐标 | 坐标来源核对 | unlocatable/相对锚点 |
| VZ-02 | 榜单无口径/样本 | 口径检查 | 补声明/撤榜 |
| VZ-03 | 低置信数据当强边 | 置信渲染检查 | 降级 |
| VZ-04 | 跨书当年表事实 | 层检查 | 标参考 |
| VZ-05 | 图元素不可回溯 | id/loc 检查 | 补 |
| VZ-06 | 图内嵌原文片段 | 内容检查 | 删/换摘要 |
| VZ-07 | 类型混排（地点当人物） | 类型检查 | 修正分类 |
| VZ-08 | 大数据全量渲染卡顿 | 性能测试 | 分片/懒加载 |

---

## 八、检查清单

### 开发前
- [ ] 选型与数据源确认；
- [ ] 数据版本/口径记录；
- [ ] 降级规则（低置信/缺失/跨书）确认。

### 开发中
- [ ] 字段契约与数据一致；
- [ ] 元素可回溯；
- [ ] 口径声明（榜单/统计）；
- [ ] 无障碍/性能考虑。

### 交付前
- [ ] 构建 exit 0、无契约报错；
- [ ] 抽检可回溯；
- [ ] 发布边界合规；
- [ ] 数据版本/回归记录。

---

## 九、FAQ（首批 5 问）

**Q1 为什么有些门派/地点在关系图上没有？**
N5 当前无 ◆/• 端点（sects=0）、前端仅区分部分类型；属数据/前端阶段缺口（附录 B）。

**Q2 榜单能当官方战力排名吗？**
不能。Glicko-2 是统计参考，必须标注样本量/口径/版本；低样本不排名（09f 纪律+01g §9.9）。

**Q3 跨书时间轴上的"年份"可靠吗？**
参考级（07a low）。只显示区间+参考标记，不显示伪精确年份。

**Q4 虚构地名怎么画在地图上？**
不配坐标，用相对锚点/列表展示（D10 双图层）；unlocatable 显式弃权。

**Q5 可视化能直接读 tagged/原文吗？**
不。可视化消费结构化导出数据；原文/连续片段不出现在图内（01g §9.10）。

---

## 十、相关文档

| 文档 | 关系 |
|---|---|
| `SKILL_09_应用总览_武侠版.md` | 09 组索引 |
| `SKILL_09j_地名应用_武侠版.md` | 地图/地名消费 |
| `SKILL_03d_渲染发布_武侠版.md` | 渲染契约/发布边界 |
| `SKILL_07a_跨书年代推理_武侠版.md` | 时间轴 low 口径 |
| `SKILL_08b_覆盖度评估_武侠版.md` | 覆盖热力数据 |
| `SKILL_01g_标注符号集合原则.md` | §9.8/§9.9/§9.10 |
| `scripts/export_site_graph.py` / `export_site_gazetteer_universe.py` / `export_site_matches_ratings.py` | 数据源 |

---

## 附录 A · 与 shiji 原版差异对照（本件为综合）

| 史记 09i/09j | 处置 | 武侠版 |
|---|---|---|
| 信息图/地图工具链 | [保留骨架] | 五类可视化契约 |
| 谭图/CHGIS 真实地理 | [扩展] | 真实+虚构双图层（D10） |
| 单书图 | [扩展] | 跨书关系/系列时间轴 |
| 无置信降级 | [新增] | 低置信虚线/隐藏 |

## 附录 B · v0.1 待补清单

| # | 待补 | 前置 |
|---|---|---|
| V-1 | sects/weapons 端点入 N5（graph 覆盖 ◆/•） | N5 扩展 |
| V-2 | 前端类型分类扩展（地点/门派等） | W/前端批次 |
| V-3 | 时间轴跨书视图（low 区间） | 07a/EX-7 |
| V-4 | 榜单口径声明组件 | 09f/前端 |
| V-5 | 覆盖热力页面 | 08b/前端 |
| V-6 | 无障碍/性能规范细化 | 前端 |

---

## 结语

可视化是知识库的"仪表盘"：数据决定能画什么，契约决定画得对不对，口径决定别人能不能信。不伪造、可回溯、带口径、守边界——比炫技重要得多。
