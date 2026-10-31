# site/ — 梁羽生武侠宇宙 · 公开站点（图谱层）

> 版权边界：本目录及其部署产物**只含图谱层**（实体/关系/事件三元组、统计、定位符、原创考订），
> 语料层（标注正文/长引文）仅在本地阅读器，永不上公网（梁作版权至 2059）。
> 架构决策见《[网站设计方案](../网站设计方案.md)》，内容规格见《[网站内容文档](../网站内容文档.md)》。

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
