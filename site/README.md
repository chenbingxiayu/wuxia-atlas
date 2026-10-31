# site/ — 梁羽生武侠宇宙 · 公开站点（图谱层）

> 版权边界：本目录及其部署产物**只含图谱层**（实体/关系/事件三元组、统计、定位符、原创考订），
> 语料层（标注正文/长引文）仅在本地阅读器，永不上公网（梁作版权至 2059）。
> 架构决策见《[网站设计方案](../网站设计方案.md)》，内容规格见《[网站内容文档](../网站内容文档.md)》。

## 数据契约 v1（site/data/，由 `scripts/build_site_data.py` 生成）

| 文件 | schema | 消费方 | 内容 |
|---|---|---|---|
| `books.json` | site-books-v1 | 作品列表/书页 | 34 部元数据卡（初刊年/背景年代/系列/主角/回数/字数/KB 状态）＋互文出入边明细（kind/定位符/片段≤60字）＋缺佚作品 3 部 |
| `universe.json` | site-universe-v1 | 宇宙页/地铁图 | 六条线路（成员＋故事内序＋排序置信＋证据定位符）＋宇宙编年主线＋22 个换乘站种子＋7 项考订问题 |
| `characters.json` | site-characters-v1 | 人物索引/全站搜索底座 | 三部曲 2,393 规范实体（10 类），跨书归并（406 个跨书实体），含逐书频次/章节跨度/别名 Top6 |
| `dossiers.json` | site-dossiers-v1 | 人物档案页（Top 40） | SKU 知识单元：别名组/出场曲线（逐回）/师承传人（动词分级 strong=传授拜师，weak=指点演示）/受立继任/战绩（◉▲双向聚合）/武功卡/门派线索（strong=书内同证镇山+修习；ok=独占招+修习；weak=单招或多门派共有招）/关键事件 12 条。**L0 版权档：仅定位符，不含原文摘录**；`summary` 留空待编辑流程 |

## 重建

```bash
python scripts/build_intertext.py       # 互文引用表
python scripts/build_work_metadata.py   # 作品元数据表
python scripts/build_series_tree.py     # 系列谱系考订表
python scripts/build_site_data.py       # books/universe/characters
python scripts/build_dossiers.py [N]    # 人物档案 Top N（默认 40）
```

上游链：`章回版/ → 互文引用表 → 作品元数据表 → 系列谱系考订表 → site/data/`
任一上游更新后按序重跑即可；`site/data/` 全部为生成物，不手改。

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
