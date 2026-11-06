---
name: skill-09c-wuxia
title: 个性化阅读（武侠版）——阅读路径、章节推荐与难度分级
description: 武侠知识库阅读体验层规范：以书/章/路径为粒度（区别于 09g 的实体/卡粒度），从 books.json（34 部/1,378 回）、chapters.json（章级 events/verbs/chars/stream，5 书已点亮）、EX-5 事件与评级生成阅读路径（主线/专题/角色线/难度渐进）、下一章与跳读推荐、章节难度 L1-L5 五维分级、剧透分级与本地阅读进度；推荐必须可解释、冷启动不假装个性化、无埋点、不输出原文。当需要编排阅读路径、推荐下一章或给章节定难度时使用。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 09c 武侠版：个性化阅读 — 把"读什么、怎么读"编排清楚

> **上游声明**：本件属 S 组 P5 应用层，对应 docs/03 §3.10 原 09c 个性化阅读（**中度 60-65%**：形式学与工具链通用，换选题即用）。**无专属设计稿**：由 EX-1 `books/chapters`、EX-5 事件/评级、`01g §9.10` 发布边界、09g 偏好与隐私原则、`08b` 覆盖度综合而成（v0.1 框架）。
> **与 09g 的分工（先读这条）**：09g 管**实体/卡粒度**的偏好模型与推荐引擎（同门派/同系列/同类事件/关系邻近/热门五类推荐 + 推荐理由）；本件管**书/章/路径粒度**的阅读编排（读哪本、按什么顺序、下一章读什么、这章难不难）。需要实体级推荐时**调用 09g**，本件不重复实现打分。
> **接口**：`../site/data/books.json`（34 部/1,378 回/17,004,474 字）、`../site/data/chapters.json`（`meta.lit_books` 5 书章级特征）、`../site/data/events` 侧 EX-5、`../site/data/ratings.json`、`../site/data/graph.json`、09g 推荐接口、`registry/sku/cards.json`（角色线入口）。
> **核心原则**：**路径是可解释的编排，不是算法黑箱；冷启动给编辑路径，不假装懂你。**

---

## 一、定位与边界

### 1.1 工序位置

```text
EX-1 books/chapters（书/章元数据 + 章级特征）
        ↓  只读
09c 阅读体验层（路径编排 / 下一章 / 难度分级 / 剧透分级 / 本地进度）
        ↓
阅读器 UI（本地进度 + 路径展示）   ← 实体级推荐转 09g
```

### 1.2 本文做什么

1. **阅读路径**：主线（系列+年表）、专题（师承/门派/情缘/战争）、角色线（某角色出现书目）、难度渐进（L1→L5）；
2. **章节推荐**：下一章、跳读建议、难度预警，每条带可解析理由；
3. **难度分级**：章节 L1-L5 五维公式（篇幅/人物/事件/动词/跨书牵连），全部由数据派生；
4. **剧透分级**：路径与推荐标 `spoiler_level`（0-3），跨书路径必须声明；
5. **本地阅读进度**：位置（书/回/PN）、笔记、偏好，本地存储、无埋点、可清空。

### 1.3 本文不做什么

| 不做 | 归属 |
|---|---|
| 实体级推荐/偏好模型 | 09g（`SKILL_09g_个性化_武侠版.md`） |
| 改 books/chapters/events | 只读（EX-1/EX-5 导出层） |
| 重新评级/考订难度为"客观难度" | 本件只给"阅读难度"（可解释的启发式，非考订） |
| 输出原文片段 | 禁（`01g §9.10`） |
| 埋点/账号/云端同步 | 禁（对齐 09g：本地优先） |
| 书单版权决策 | 权利审核（本库只给定位与结构） |

### 1.4 关键约束

- **粒度边界**：本件只处理 `book/chapter/path`，不输出"推荐某角色/某卡"（那是 09g）；
- **可解释**：每条推荐至少 1 个 `reason_code` + 1 条 `evidence`（字段级）；
- **数据诚实**：章级特征只对 `meta.lit_books`（5 书）可用；其余 29 部只有回目元数据，路径必须标 `features:"toc-only"`；
- **剧透自律**：默认 `spoiler_level=0`（不剧透结局）；跨书/结局向路径必须显式声明等级；
- **本地优先**：进度与笔记只落本地，禁止上传、禁止埋点；
- **无原文**：路径步骤用 `book/chapter/PN` 描述，不嵌正文。

---

## 二、快速开始（五步）

````text
Step 1 取数   读 books.json / chapters.json（只读），确认 lit_books 与 kb_status
Step 2 选题   主线 / 专题 / 角色线 / 难度渐进（四类路径，可并存）
Step 3 编排   按 §三 规则生成 steps，每步写 book/chapter/pn/difficulty/spoiler_level
Step 4 定难   按 §四 五维公式算 L1-L5，标注 features（full/toc-only）
Step 5 校验   理由可解析、无原文、剧透等级已声明、进度本地（§七）
````

只读取数示例：

```python
import json
from pathlib import Path

D = Path('../site/data')
books = json.load(open(D / 'books.json', encoding='utf-8'))
chaps = json.load(open(D / 'chapters.json', encoding='utf-8'))

lit = set(chaps['meta']['lit_books'])                 # 章级特征可用的 5 书
print('lit_books:', sorted(lit))
print('totals:', books['meta']['totals'])             # 34 部 / 1,378 回 / 17,004,474 字

b = chaps['七剑下天山']
print('lit:', b['lit'], 'chapters:', len(b['chapters']))
c = b['chapters'][4]
print('章级特征:', {'events': c['events'], 'chars': len(c['chars']),
                    'verbs': sum(c['verbs'].values()), 'stream': len(c['stream'])})
```

> `chapters.json` 为按书分组的 dict（`meta` + 每书 `{chapters, lit, kb}`）；`books.json` 的 `kb_status` 决定该书是否"已点亮"。

---

## 三、阅读路径编排（四类）

### 3.1 路径 schema

```json
{
  "id": "path-main-qijian",
  "type": "main",
  "title": "天山系列主线（七剑起读）",
  "steps": [
    {"book": "七剑下天山", "chapter": 1, "pn": "七剑下天山#pn-r1",
     "difficulty": 2, "spoiler_level": 0, "features": "full",
     "reason": {"codes": ["series_anchor"], "evidence": {"series": "天山", "year": 1956}}}
  ],
  "constraints": {"max_books": 5, "spoiler_cap": 1},
  "enabled": true
}
```

`type ∈ {main, theme, character, difficulty}`；`features ∈ {full, toc-only}`。

### 3.2 四类路径的生成规则

| 类型 | 依据字段 | 规则 | 约束 |
|---|---|---|---|
| 主线 `main` | `books[].series` + `year` + `series_conf` | 同系列按 `year` 升序；系列入口选 `leads` 明确且 `chapters` 适中的一部 | `series_conf≠ok` 的系列不自动排主线，需人工确认 |
| 专题 `theme` | `chapters[].events`（T 类型）+ `stream` + graph `kind` | 按主题选事件密度高的回目（如战争=T03/T11、情缘=关系边 `romance`） | 主题定义必须写进 `title`/`constraints`，不得暗示"唯一正确读法" |
| 角色线 `character` | `cards.json#active_books` + `chapters[].chars` | 角色出场回目按书/回排序；跨书按 `year` 排序 | 角色必须 `status` 非 pending；`active_books` 为空则不出路径 |
| 难度渐进 `difficulty` | §四 的 D 值 | 全书回目按 D 升序分档，取每档 3-5 回 | 不得跳读结局回（`spoiler_level` 上限 1） |

### 3.3 章节推荐（下一章 / 跳读 / 预警）

```json
{
  "book": "七剑下天山",
  "current": {"chapter": 4, "pn": "七剑下天山#pn-r4"},
  "next": {"chapter": 5, "difficulty": 3, "reason_codes": ["sequential", "difficulty_step"]},
  "skip_candidates": [{"chapter": 7, "reason_codes": ["low_event_density"], "evidence": {"events": 0}}],
  "warnings": [{"chapter": 6, "kind": "difficulty_spike", "evidence": {"difficulty": 5, "delta": 2}}],
  "spoiler_level": 0
}
```

`reason_codes` 只允许：`sequential`（顺读）、`difficulty_step`（难度递进）、`low_event_density`（事件稀薄可跳）、`difficulty_spike`（难度突增预警）、`series_bridge`（系列衔接）、`character_arc`（角色线）、`theme_match`（专题命中）。**禁止**输出无法映射到字段的理由（如"精彩""经典"）。

### 3.4 冷启动

无阅读历史时**只给编辑路径**（主线 + 难度渐进），并在 UI 标注"编辑推荐，非个性化"；不得用"猜你喜欢"话术。有本地进度后，推荐权重可加 `sequential`/`difficulty_step`，仍不得推断人口学属性。

---

## 四、章节难度分级 L1-L5（五维公式）

### 4.1 五维定义（全部来自 `chapters[]`）

| 维度 | 符号 | 字段 | 说明 |
|---|---|---|---|
| 篇幅 | L | 章长（去空白字符数） | 长章阅读负担高 |
| 人物负载 | P | `len(chars)` | 出场实体数（去重后） |
| 事件密度 | E | `events / (章长/1000)` | 每千字事件数 |
| 动词密度 | V | `sum(verbs.values()) / (章长/1000)` | 标注动词密度，近似动作/对话强度 |
| 跨书牵连 | X | `stream` 中实体在 `graph.nodes[].books` 的并集大小 | 跨书人物多则前置知识要求高 |

### 4.2 合成与分档

```text
raw = 0.20*z(L) + 0.25*z(P) + 0.25*z(E) + 0.15*z(V) + 0.15*z(X)
D   = L1..L5 = quintile(raw)          # 按全书回目分位切五档，边界随 data_version 冻结
```

`z()` 为该书内 z-score（样本不足 10 回时改用全 5 书点亮集合）；分位边界必须与 `data_version` 一同记录，换版本重算。

### 4.3 标注纪律

- 难度是**阅读负担启发式**，不是文学评价、不是考订结论；文案不得写"此章水平高/低"；
- `features:"toc-only"` 的书（未点亮 29 部）只能给 `D:null` + `reason:"no_chapter_features"`，**不得用字数估一个难度**；
- 难度突变（相邻回 D 差 ≥2）必须进 `warnings`，供阅读器提示。

---

## 五、剧透分级与进度

### 5.1 `spoiler_level`

| 级别 | 含义 | 允许出现在 |
|---|---|---|
| 0 | 无剧透（仅回目/结构） | 默认全部路径 |
| 1 | 轻度（人物关系/门派归属） | 专题、角色线（需声明） |
| 2 | 中度（关键事件结果，如胜负/生死） | 需用户显式开启 |
| 3 | 重度（结局/身份反转） | 默认禁止；仅"结局讨论"模式且二次确认 |

跨书路径必须取 `max(step.spoiler_level)` 作为路径级声明；`constraints.spoiler_cap` 默认 1。

### 5.2 本地进度 `reading-state`

```json
{
  "schema": "reading-state-v0.1",
  "local_only": true,
  "pos": {"七剑下天山": {"chapter": 4, "pn": "七剑下天山#pn-r4", "updated_at": null}},
  "notes": [],
  "prefs": {"spoiler_cap": 1, "difficulty_cap": 3},
  "cleared_at": null
}
```

`notes` 只存用户自己的笔记（可含原文摘录**仅限本地**）；`prefs` 只存本件所需三项，不存人口学字段；提供"一键清空"。

---

## 六、工具与脚本

| 脚本/文件 | 用途 | 备注 |
|---|---|---|
| `scripts/export_site_books_chapters.py` | EX-1 书/章导出 | 生成 `books.json`/`chapters.json` |
| `scripts/export_site_all.py` | 全量导出编排 | 缺省 dry-run |
| `scripts/compute_annotation_coverage.py` | 标注覆盖度（决定 `features` 是否 full） | 与 `08b` 覆盖度口径一致 |
| `scripts/build_search_index.py` | 站点检索索引 | 阅读器"找章"入口 |
| `scripts/lint_skills.py` | 本件自检 | `python -X utf8 scripts/lint_skills.py "skills/SKILL_09c_个性化阅读_武侠版.md"` |

> **v0.1 无路径生成器**：当前路径/难度靠本文规则 + 只读脚本取数 + 人工编排；生成器与校验器列入附录 B。

---

## 七、错误模式库（PR 系列）

| ID | 错误 | 表现 | 检测 | 修正 |
|---|---|---|---|---|
| PR-01 | 越界做实体推荐 | 输出"推荐练霓裳的卡" | 检查产物字段是否含实体/卡级推荐 | 转 09g 接口 |
| PR-02 | 难度无来源 | 难度是手填或"感觉" | 抽检复算 §四 公式 | 改公式派生或 `D:null` |
| PR-03 | 剧透未声明 | 跨书路径含结局回但 `spoiler_level=0` | 路径级取 max 校验 | 补声明或剔除结局回 |
| PR-04 | 未点亮书硬算特征 | 29 部未点亮书给出章级难度 | 对照 `meta.lit_books` | 标 `toc-only` + `D:null` |
| PR-05 | 埋点/上传 | 进度含设备/账号/上报字段 | schema 白名单校验 | 删除，仅本地 |
| PR-06 | 理由不可解析 | "经典必读""精彩" | `reason_codes` 白名单 | 改字段级理由 |
| PR-07 | 冷启动假装个性化 | 无历史却称"为你推荐" | 检查是否编辑路径 | 改"编辑推荐"话术 |
| PR-08 | 原文泄漏 | 路径/推荐嵌正文片段 | 与底本子串比对 | 改 `book/chapter/PN` |

---

## 八、检查清单

### 编排前

- [ ] 已确认 `books.meta.totals` 与 `chapters.meta.lit_books`；
- [ ] 目标书 `kb_status` 已知（未点亮 → `toc-only`）；
- [ ] 路径类型与 `spoiler_cap` 已声明；
- [ ] 若用角色线，角色 `status` 非 pending 且 `active_books` 非空。

### 编排中

- [ ] 每步 `book/chapter/pn` 可解析，`difficulty` 按 §四 派生；
- [ ] 每条推荐有 `reason_codes`（白名单内）+ `evidence`；
- [ ] 跨书路径按 `year`/`series` 排序且 `series_conf` 已核；
- [ ] 无正文片段，无"精彩/经典"类空理由。

### 交付前

- [ ] 路径级 `spoiler_level = max(steps)` 且 ≤ `spoiler_cap`；
- [ ] `reading-state` 字段白名单通过（无埋点字段）；
- [ ] 未点亮书全部标 `toc-only` 且 `D:null`；
- [ ] 难度分位边界与 `data_version` 一并记录。

## 九、成功标准（v0.1）

1. **边界清晰**：产物中 0 条实体/卡级推荐（全转 09g）；
2. **可解释率 100%**：每条推荐 ≥1 个白名单 `reason_code` + 1 条字段级 evidence；
3. **难度可复算**：抽检 10% 回目按 §四 复算一致（容差 0）；
4. **剧透 0 越级**：无路径 `spoiler_level` 超过声明上限；
5. **数据诚实**：未点亮书 0 处给出章级难度；
6. **隐私 0 埋点**：`reading-state` 无设备/账号/上报字段，可一键清空。

---

## 十、FAQ（首批 5 问）

**Q1：09c 和 09g 到底谁推荐什么？**
09g 推荐"实体/卡"（同门派、关系邻近…），09c 编排"读哪本、按什么顺序读、下一章读什么"。阅读器里两者可并存，但接口分开，理由字段分开。

**Q2：为什么只有 5 本书有章级难度？**
章级特征依赖 tagged/事件/动词标注，当前点亮 5 书（`meta.lit_books`）；其余 29 部只有回目元数据，硬算难度就是编数据。

**Q3：难度 L1-L5 是文学评价吗？**
不是。它是"阅读负担"启发式（篇幅/人物/事件/动词/跨书牵连五维分位），用于阅读提示，不用于评价作品。

**Q4：路径会不会替用户决定读法？**
路径是**可选编排**，默认只给主线与难度渐进；专题/角色线需用户主动选择，且理由可查、可关。

**Q5：笔记里可以摘原文吗？**
可以，但仅限本地 `reading-state.notes`；任何发布/分享行为必须走权利审核（`01g §9.10`）。

---

## 十一、相关文档

- `SKILL_09_应用总览_武侠版.md`（应用层命名与 P5 状态；附录 A 记录 09c 曾被并入 09g）
- `SKILL_09g_个性化_武侠版.md`（实体/卡粒度偏好与推荐引擎，本件的上游接口）
- `SKILL_09j_地名应用_武侠版.md`（地名/空间维度的阅读入口）
- `SKILL_08b_覆盖度评估_武侠版.md`（覆盖度口径，决定 `features`）
- `SKILL_03d_渲染发布_武侠版.md`（PN 锚点与发布边界）
- `docs/59`（EX-5 事件层）、`docs/60`（S 组 P5 与站点验收）

---

## 附录 A · 与 shiji 原版差异对照（本件为骨架+综合）

| 维度 | shiji 09c 个性化阅读 | 本件（武侠版） | 性质 |
|---|---|---|---|
| 阅读路径 | 主线/专题/角色线 | 照搬四类框架，映射到 series/year/T 类型/active_books | 照搬 |
| 章节推荐 | 下一章/跳读 | 照搬，理由码换为可解析白名单 | 照搬 |
| 难度分级 | 通用可读性维度 | 本件自拟五维（篇幅/人物/事件/动词/跨书牵连） | 骨架+综合 |
| 剧透控制 | 原设计未细化 | 本件加 `spoiler_level` 0-3 + `spoiler_cap` | 骨架+综合 |
| 与推荐引擎关系 | 独立模块 | 本件与 09g 分粒度协作（09c 编排、09g 打分） | 武侠项目特有 |
| 数据诚实 | 不适用 | 未点亮书 `toc-only` + `D:null` | 武侠项目特有 |

> **历史注记**：09 总览附录 A 曾记"09c 个性化阅读并入 09g"，本件按 docs/50 恢复为独立 P5 件并**限定为阅读体验层**，避免与 09g 重复。

## 附录 B · v0.1 待补清单

1. **路径生成器**：scripts/build_reading_paths.py（四类路径生成 + 难度计算 + schema 校验）未实现；
2. **难度校验器**：分位边界冻结与复算脚本未实现；
3. **推荐理由库**：`reason_codes` 已定白名单，尚未与前端文案表对齐；
4. **跨书年表**：`series_conf` 非 ok 的系列需人工确认，主线自动编排暂只覆盖 `ok` 系列；
5. **阅读器对接**：PN 锚点跳转与本地进度恢复接口未联调；
6. **标注扩容**：章级特征仅 5 书，扩到 34 部需 tagged/事件层继续产出。

---

## 结语

个性化阅读的价值不在"猜你喜欢"，而在**把 34 部 1,378 回的结构讲清楚**：哪本先读、这章难不难、会不会剧透、读到哪里了。把这四件事做成可解释、可关闭、可本地保存的编排，就是本层的全部任务。
