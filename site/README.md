# site/ — 梁羽生武侠宇宙 · 公开站点（图谱层）

> 版权边界：本目录及其部署产物**只含图谱层**（实体/关系/事件三元组、统计、定位符、原创考订），
> 语料层（标注正文/长引文）仅在本地阅读器，永不上公网（梁作版权至 2059）。
> 架构决策见《[网站设计方案](../设计文档/网站设计方案.md)》，内容规格见《[网站内容文档](../设计文档/网站内容文档.md)》。

## 数据契约 v1（site/data/，由 `scripts/build_site_data.py` 生成）

| 文件 | schema | 消费方 | 内容 |
|---|---|---|---|
| `books.json` | site-books-v1 | 作品列表/书页 | 34 部元数据卡（初刊年/背景年代/系列/主角/回数/字数/KB 状态）＋互文出入边明细（kind/定位符/片段≤60字）＋缺佚作品 3 部 |
| `universe.json` | site-universe-v1 | 宇宙页/地铁图 | 六条线路（成员＋故事内序＋排序置信＋证据定位符）＋宇宙编年主线＋22 个换乘站种子＋7 项考订问题 |
| `characters.json` | site-characters-v1 | 实体底座 | 全类型规范实体（2,390），跨书归并（405），含逐书频次/章节跨度/别名 |
| `entity-index.json` | entity-index-v1 | 实体联想岛（EntityExplorer） | 轻索引（@/☆/◆ 共 1,034 条）：规范名/频次/逐书/跨书 |
| `dossiers.json` | site-dossiers-v1 | 人物档案页（**全部 @ 实体**，现 436 页） | SKU：别名组/出场曲线/师承传人（动词分级）/受立/战绩/武功/门派线索（三级置信）/关键事件。**L0 版权档：仅定位符，不含原文摘录**；`summary` 留空待编辑流程 |
| `chapters.json` | chapters-v1 | 书页/回目页 | 34 部回目＋三部曲逐章事件流/动词密度/出场人物 |
| `arts.json` | arts-v1 | 武功谱（102 门） | 品类自动分类/归属/修习传授者/别名/证据注记 |
| `sects.json` | sects-v1 | 门派志（16 门派） | 武功册（镇山/拥有/独门）/成员册（derived strong/ok）/事件参与 |

## 可扩展性约定（新小说接入 = 零代码改动）

- 书目**自动发现**：管线产出到 `kb/<书>/实体登记表.json` 即视为已点亮——全部 build 脚本基于 `kb_discovery.lit_books()` 运行，无硬编码书目；
- 跨书统一规范名收口在 `kb_discovery.BOOK_CANON`（依据 kb/README"跨书接口"节，登记表归并后可移除对应项）；
- 页面由 getStaticPaths 遍历数据生成：重跑管线 → 新书/新实体页面自动出现，dossiers/arts/sects/entity-index 全量生长。

## 重建

```bash
python scripts/build_intertext.py       # 互文引用表
python scripts/build_work_metadata.py   # 作品元数据表
python scripts/build_series_tree.py     # 系列谱系考订表
python scripts/build_site_data.py       # books/universe/characters/entity-index
python scripts/build_dossiers.py        # 人物档案（全部 @ 实体；可传参数只做前 N）
python scripts/build_pages_data.py      # chapters（回目+事件流切片）
python scripts/build_arts_data.py       # arts（武功）
python scripts/build_sects_data.py      # sects（门派，依赖 dossiers）
cd site && npm ci && npm run build && npx pagefind --site dist
python scripts/copyright_gate.py site/dist   # 版权闸门（本地部署前必跑；CI 接入 M4）
```

## 已就绪 / 待建

- ✅ 数据层 v1（books/universe/characters）
- ✅ 人物档案页 SKU 数据（`dossiers.json`，Top 40，L0 版权档；summary 待编辑流程）
- ⬜ 站点骨架（Astro SSG：宇宙地铁图 hero、书页、人物档案页、KG-QA 预置查询）
- ⬜ 本地阅读器（独立目录，L2 语料档，永不部署）

## 数据裁定记录（2026-10-31，用户裁定，已应用）

- ✅ 七剑·027:15「哈玛雅 授 练霓裳」**主宾颠倒已修正**为「练霓裳 授 哈玛雅」（019:21 明文师承＋用户确认）——`scripts/fix_events_20261031.py`（幂等，管线重建后可重跑），同步 事件表.md 与 校订报告.md 补遗；
- ✅ 白发·015:21「None 拜 公孙大娘」**已 drop**（未施行动词，激将假设）；
- 依据 kb/README"跨书接口"节的跨书统一规范名（飞红巾=哈玛雅、晦明禅师=岳鸣珂、白发魔女=练霓裳），`build_site_data.py` 与 `build_dossiers.py` 在数据层归并（kb 登记表未动；塞外 登记表中 飞红巾/哈玛雅 双实体、晦明禅师/岳鸣珂 分立等归并候选待 kb 侧处理，处理后脚本可移除该映射）。

## 已知数据问题（kb 考订挂账，站点不改数据）

（暂无——前两项已于 2026-10-31 裁定修复，见上。）

## 部署与验收（2026-11-05 起，D4 搜索/首部署准备）

> 上文「重建」节为 2026-10-31 历史参考；现行构建顺序以下节为准。

### 环境

| 项 | 要求 / 实测 |
|---|---|
| Node.js | ≥ 20（实测 v24.21.0）；npm 实测 11.6.4；依赖由 `package-lock.json` 锁定 |
| Python | 3.11+（实测 3.13）；站点数据/搜索索引脚本仅用标准库，无第三方依赖 |
| 前端 | Astro 5 + `@astrojs/react` + ECharts（`site/package.json`）；**搜索不引入 npm 依赖** |
| 部署目标 | GitHub Pages 项目站点，`base=/wuxia-atlas/`（见 `astro.config.mjs`）；自定义域名/根路径需改 `base` 并同步全站链接 |

### 构建顺序（必须按序）

```bash
# 1) 数据层（wuxia-kb 导出层；dry-run 先看契约报告，--apply 才写 site/data，写前备份）
cd wuxia-kb && python -X utf8 scripts/export_site_all.py            # 或 --apply（需 hard_gap=0）

# 2) 前端构建（构建时自动 mirror site/data → public/data → dist/data）
cd site && npm ci && npm run build                                  # → site/dist（约 1452 页，~40-50s）

# 3) 搜索索引（必须在 build 之后；读 dist、写 site/data/search-index.json，并同步 dist/data + public/data）
cd wuxia-kb && python -X utf8 scripts/build_search_index.py

# 4) （可选）Pagefind 全文索引：无 package.json 依赖；离线不可用不阻塞（搜索页自动回退 JSON）
cd site && npx --yes pagefind@1.6.0 --site dist

# 5) 部署前验收
python -X utf8 ../scripts/copyright_gate.py dist wuxia-atlas   # 第二参数为 base 段（注意）
# 链接 404 / 页面抽检：见 wuxia-kb/logs/qa/site_acceptance_report.md
```

### 搜索方案（D4）

- **主搜索（无依赖）**：`site/data/search-index.json`（schema `site-search-v1`，约 1,451 条：标题 / URL / 摘要 / display / canonical / type / aliases）。`/search` 页内嵌 JS 直接读取，支持 **展示名与规范名双匹配**（康熙↔玄烨、飞红巾↔哈玛雅、崇祯↔朱由检、顺治↔福临、雍正↔胤禛）、别名匹配与标题/摘要匹配；索引约 390KB。
- **可选全文**：Pagefind 1.6.0（`dist/pagefind/`，Component UI；`<pagefind-config base-url="/wuxia-atlas/">` 支持子路径）。构建时若生成索引，/search 自动出现「全文检索（可选）」区块；未生成则隐藏。
- **索引重生成**：数据或页面更新后重跑第 3 步（脚本幂等；已同步 dist/public 副本）。
- **备注**：Pagefind 1.6.0 无 `--base-url` CLI 参数；子路径由 Component UI 的 `base-url` 属性处理（已在 `search.astro` 内置）。

### 回滚

- **前端/搜索**：保留上一版 `dist/`（建议 `dist.bak.YYYYMMDD_HHMM`）→ 回滚时整目录替换（搜索索引随 dist 一起回滚）。
- **数据**：`site/data/` 由 wuxia-kb 导出层重生成；回滚 = 用上一版 staging/备份重新 `--apply`（导出脚本自带契约报告与备份）。
- **仅索引**：恢复 `site/data/search-index.json` 旧版后重跑 `npm run build`（或直接覆盖 dist/data 与 public/data 同名文件做热修）。
- **不提交** `node_modules/`、`dist/`（见 `.gitignore`）；部署产物仅 `dist/`。

### 首部署已知问题（2026-11-05）

1. **链接 404：190 处 / 64 目标**（来源页：characters 59、weapons 55、arts 13、sects 10、stories 9、universe 2、index 1）。分类：display-as-href 63（飞红巾/康熙/顺治被当 URL）、alias-as-href 57（允祯/晦明禅师/董鄂妃/鄂王妃/张公子 等别名未映射 canonical）、无档案页实体 42（清兵/清军/群称/地名等被盲目链接）、book/chapter 13（stories 章节号未补零 03→003；《挑灯看剑录》未点亮却被 index/universe 链接）、sect/arts/null slug 15。**均属其它页面/数据层问题，D4 只改搜索页，未越权修复**；逐条清单见 `wuxia-kb/logs/qa/site_acceptance_report.md` §四。
2. **版权闸门**：`copyright_gate.py dist wuxia-atlas` 结果——语料整行泄漏 **0**；规则 2 命中 1 类（6 个 data JSON 的 `source`/`meta` 字符串含 `tagged/` 出处说明）；规则 3（base 前缀）通过。建议给 provenance 字符串加白名单，或导出层移除 `tagged/` 字样后重跑。
3. 站点构建/页面/display/搜索功能验收均 PASS（详见验收报告）。
