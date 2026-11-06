---
name: w0-butler-wuxia
title: W0 Butler 定位（武侠版）——W 组总则、六不变量与发布边界
description: 武侠知识库 W 组（内容流水线）总则。定义 Butler 的定位（厨师而非生产者）、六不变量武侠适配、与 S 组（规则/技能生产）及 N/EX 组的分工、发布与版权边界、轮次与队列消费、动作留痕与回滚、健康度与反思接口。当需要启动/审阅 Butler 轮次、判定一个动作是否越界、确认发布/回滚纪律、或衔接 W1-W14 时使用。W1 资料地图见 `skills/W1_资料地图_武侠版.md`；W7 引文核验见 `scripts/verify_quotes.py`；组级设计见 `logs/qa/w_group_design_brief.md`。
version: v0.1-draft
last_updated: 2026-11-05
scope: W 组内容流水线总则（W0）；不产事实、不改 tagged/registry/site、不重算上游
source: shiji-kb/skills/SKILL_W0_Butler总则.md（哲学/六不变量/队列/invocation 骨架迁移，20:80）；docs/01 §三「九步管线与 Skill 编号体系」；docs/05 §2.6「W 系列 38 个」判定（W0-W6 70:30）；logs/qa/w_group_design_brief.md（W0-W14 38 节点）
---

# W0 Butler 定位（武侠版）—— W 组总则

> **本文是什么**：W 组（内容/页面流水线）的总则与永续运行框架。它回答四个问题：Butler 是谁（定位）、什么绝对不能做（边界/六不变量）、每轮怎么运转（队列与节奏）、结果如何可信（评估/留痕/回滚）。
>
> **上游依赖**：`logs/qa/w_group_design_brief.md`（W 组 38 节点与波次）；`skills/W1_资料地图_武侠版.md`（六源食物地图与数据契约）。
>
> **一句话**：Butler 是**厨师**——原材料（registry/tagged/SKU/references/docs/logs）在别处，Butler 只负责**摆盘**（组织成读者页面/专题/洞察）并持续改进摆盘方式本身；它不是事实生产者。

---

## 快速开始

> 每次 invocation（一轮）按以下 7 步执行；每步产物落 `logs/w_group/`（本批只建该目录）。

1. **读总则与队列**：本文件 + `skills/W1_资料地图_武侠版.md` + `logs/w_group/queue.md`（P0/P1/P2）。
2. **领轮次**：单实例期由 Lead/脚本分配轮号；多实例期须用轮次锁（`logs/w_group/round_counter.txt` + 轮次锁文件，见 §五）。轮号写入本轮 `actions.jsonl`。
3. **选动作**：按 W1 队列取 P0→P1→P2；每轮按 **2:1** 在"顺藤摸瓜（trail，沿关系/事件/引用链）"与"无约束探索（explore，随机页/随机实体诊断）"间配比；动作必须来自 W2 原子动作目录（24 类），禁止自由发挥。
4. **查素材与门槛**：按 W1 六源取数；页面字段必须有来源（PN/registry ID/卡字段），引文必须过 W7；缺源字段显式"未明示"，不补写。
5. **小步执行**：单动作 diff ≤20 行（精品页例外但一动作一 commit）；失败立即回滚工作区；每动作前在 `actions.jsonl` 写动机/前置/后置/来源。
6. **评估**：按 W4 四问（引文过 W7？事实有源？结构过 lint？diff 合规？）判 accept/fail；fail 进 `failures.jsonl`。
7. **反思与回写**：每 10 轮看健康度（W10 六指标）；每 20 次 action 触发 W5 反思（改规则）；每轮结束跑 W9 页面图式反思（改模板）；在本轮 `actions.jsonl` 末行记结果与 commit。

> **成功标准（W0 验收）**：① 每轮有 7 步痕迹（轮号/动作/评估/留痕齐全）；② 越界动作 = 0（见 §四）；③ 叙事引文疑似编造 = 0（W7 `--strict` 通过）；④ 失败可一键回滚（commit/revert 可查）；⑤ 十轮内 W5/W9 至少各触发一次。

---

## 一、Butler 定位：厨师，不是生产者

### 1.1 可做（做什么）

| # | 职责 | 武侠载体 | 说明 |
|---|---|---|---|
| 1 | **组织** | `content/` 页面草稿、专题/列表页配置 | 把 registry/SKU/tagged 已存在的事实搬到读者页面合适位置 |
| 2 | **综合** | W8 精品页（featured） | 跨多源综合叙述，用 PN 引文/关系边/事件锚定（引文过 W7） |
| 3 | **维护** | 站内链、infobox、tags、时间线、内务整理 | 对齐 site 页面与 EX 导出字段（不直接改 site） |
| 4 | **分析** | 以有源断言为基础的分析性段落 | 每段至少 1 条 PN/registry 证据；无源不写 |
| 5 | **自改** | W5 反思（改 W1-W4 规则）、W9（改页型模板） | 改进"摆盘方式本身"，diff ≤20 行 |

### 1.2 不做（越界即错）

- **不做实体识别/消歧/归并**：`tagged/`、`registry/entities.json`、mapping 表属 S/N 组，Butler 只读；
- **不做事件/关系抽取**：D03/D06 的判定与 ID 生产属 N4/N5，Butler 只引用与投影（K6）；
- **不改 `tagged/`、`registry/`、`site/`**：本批 hard 约束；页面落 `content/`，经 EX 导出层进站点；
- **不凭空造事实**：所有断言必须有源（PN 引文 > registry ID > 统计），"未知"写"未明示"；
- **不携带原文片段**：页面/卡面不得与原文连续重合 ≥10 字（R1/R2），引文只存指针；W7 输出亦不输出原文。

### 1.3 与 S 组 / N 组 / EX 组的分工

| 组 | 职责 | 产物 | 与 W 组接口 |
|---|---|---|---|
| **S 组**（规则/技能生产） | 写/改 `skills/SKILL_*`、`references/`、`templates/` | SKILL 规范、规律库、页型模板 | W 组消费规范与模板；S 产出变更须复跑 W3/W8 |
| **N 组**（管线脚本） | 标注/事件/关系/时间/分类/卡生成 | `tagged/`、`registry/`、`registry/sku/` | W 组只读取其 schema 与字段 |
| **EX 组**（导出层） | `registry/site` 数据导出器 → `site/data/*.json` | `export_site_*.py`、`export_site_all.py` | W 组 `content/` → EX 字段/页面 config；W 组不直接改 site |
| **W 组**（本组） | 内容组织/质检/洞察 | `content/`、`logs/w_group/`、`templates/`（W9） | 不重算上游；输出交 EX/发布 |
| **META/审计** | 复盘/质量审计 | docs 记录、审计报告 | 引用 W 组健康度与 failures |

---

## 二、六个不变量（武侠适配，绝对不可违背）

> 来源：shiji W0 六不变量；武侠落地口径见下表。任一条违反即回滚该动作并记 failures。

| # | 原义（shiji） | 武侠落地 | 检查/证据 |
|---|---|---|---|
| 1 | **小步** | 单动作 diff ≤20 行（含空行）；精品页单页整体可超 20 行，但仍是一动作一 commit | `git diff --stat`；超限必须拆 |
| 2 | **可逆** | 每个动作对应 1 个 commit（或 `content/` 文件的备份+恢复点）；失败 `git revert`/恢复备份 | commit sha 写入 actions.jsonl；备份路径可查 |
| 3 | **留痕** | 动作前写 `logs/w_group/actions.jsonl`：ts/mode/action/target/source/rationale/result/commit | JSONL 每轮追加；缺行 = 未执行 |
| 4 | **只追加不替换** | 已有页面/段落改写走"新段+标注旧段"（`<!-- superseded -->` 或 frontmatter `supersedes`）；不静默删除历史 | diff 中不得整段无痕替换 |
| 5 | **专用脚本写页** | 页面/资产写入统一走生成器（如 `scripts/generate_w8_pages.py`）或模板化脚本；禁手工直接编辑已生成内容 | 生成器/脚本路径记入 actions.jsonl |
| 6 | **来源必填** | 每条断言/引文挂 PN（`书#pn-r{回}.{段}`）、registry ID（`E...`/`#R...`）或卡字段；无源不写 | W7 + W4 四问；未明示项单列 |

**补充纪律（武侠版新增）**

7. **不输出原文**：W 组报告/日志/JSON 只给定位符/长度/hash/统计；页面引文 ≤60 字/块且过 W7；
8. **demo 隔离**：`demo: true` 的页面/卡不得进入发布库（R4/K3）；发布状态三档见 §四；
9. **并发错峰**：W 组与 EX 导出/站点构建错峰；多实例需页级锁（同一轮不操作同一页面）。

---

## 三、轮次、队列与节奏

### 3.1 三队列（P0/P1/P2）

| 优先级 | 判据（示例） | 来源 | 典型动作 |
|---|---|---|---|
| **P0** | 高频实体/卡已就绪但无页面；断链指向高频实体；已知事实错误 | W1-A/B/F | 建 stub、修事实、补页 |
| **P1** | 结构内务：链接密度、PN 缺注、重复内容、分类缺叶 | W1-A/C/E | 补引文、链接化、分类、去重 |
| **P2** | 探索/洞察：随机页诊断、W14 洞察候选、精品页候选 | W1-E/F/W14 | 精品页、洞察页、列表页 |

### 3.2 选取算法（每轮）

```text
输入：queue.md（P0/P1/P2）+ 健康度快照 + 上轮 failures
1) P0 非空 → 取 1-2 条（防饥饿：同实体 3 轮未动降权）
2) 否则 trail : explore = 2:1 选模式
   trail  = 沿关系边/事件/跨书互文/被引链扩展（W1 源 A/C）
   explore= 随机实体/随机页/覆盖缺口抽样（W1 源 E/F）
3) 按 WU 批量执行同类动作至 ~1000WU/轮（首轮 200WU 起）
4) 记录本轮 actions 与 accept/fail
```

### 3.3 节奏

| 频率 | 动作 | 产物 |
|---|---|---|
| 每轮 | 7 步 invocation（快速开始） | actions.jsonl + 页面/动作 |
| 每 10 轮 | W10 健康度快照、队列补充、W14 轻量洞察扫描 | `health.jsonl`、`housekeeping_queue.md` |
| 每 20 次 action | **W5 反思**：failure 聚类→改 W1-W4 规则 | `reflections/R<N>.md` + skill diff |
| 每轮结束 | **W9 页型反思**：3 个新页 vs 同类历史页 | `templates/*.md` 更新提案 |
| 每 13 轮 | W11 概念分类元反思 | `type_audits/R<N>.md` |
| 每 30 轮 | W10 元反思（委托 W5） | 规则版本记录 |

---

## 四、发布边界（版权/隐私/可信）

### 4.1 引用档位（L0 图谱层）

- **L0**：定位符（`书#pn-r{回}.{段}`）+ 短语概括 + ≤60 字短引文；**不贴原文整段**；
- 页面/卡面连续重合 ≥10 字即违反 R1（SKU 脱敏规则），生成器须自检；
- W7 输出的 near/miss 清单不输出原文，仅长度/hash/定位符（`logs/w_group/quote_verify.json`）。

### 4.2 发布状态三档（与 N10 卡对齐）

| 状态 | 含义 | 允许发布 |
|---|---|---|
| `draft` | 生成/待审 | 否 |
| `in-review` | 人工复核中 | 否（站点可用 `preview` 标记展示但不入正式索引） |
| `approved` | 过 W3/W4/W7 门禁 + 人工签核 | 是（EX 导出层按 `publish_state` 过滤） |

> **demo 页**：`demo: true` 永远 blocked（R4/K3）——本批 `content/` 生成页全部 `demo: true` + `publish_state: draft`。

### 4.3 发布门禁（四问 + W7）

1. 引文过 W7（`--strict` 通过；near 需人工复核，miss 拒绝）；
2. 事实有源（PN/registry ID/卡字段）；
3. 结构过 lint（N8/N9/02ab 相关项）且 EX 字段契约通过（`export_site_all.py` dry-run）；
4. diff ≤20 行（精品页例外）且只追加不替换。

---

## 五、动作留痕与回滚

### 5.1 `logs/w_group/actions.jsonl` 行格式

```json
{"ts": "2026-11-05T19:40:00+08:00", "round": 12, "mode": "trail", "action": "enrich-relations",
 "target": "content/person/card.person.e0019.md", "source": "registry/sku/cards.json#card.person.e0019 + registry/relations/白发魔女传.json#R0163",
 "rationale": "卡面师承边未投影为页面关系行", "result": "accept", "diff_lines": 6,
 "quotes_verified": 0, "commit": "<sha>", "rollback": "git revert <sha>"}
```

### 5.2 回滚

- 工作区失败：`git restore <file>`（或生成器 `--apply` 备份目录恢复）；
- 已提交：`git revert <sha>`；`actions.jsonl` 保留原行并追加 `{"result":"rollback","rollback_of":"<sha>"}`；
- 生成器批量写页：`--apply` 前自动备份到 `logs/qa/w8_content_backup/<run_id>/`，manifest 含 sha256；恢复按 manifest 逆序覆盖。

---

## 六、健康度与接口（W4/W5/W9/W10）

六指标（shiji W10 原典 → 武侠口径，完整定义见 W10 SKILL）：K 知识量 / link_density（站内链密度）/ stub_ratio / source_coverage（PN 引注占比）/ citation_error_rate（W7+W6 open 数）/ disambiguation_coverage（同名消歧覆盖）。

| 接口 | 消费方 | 给什么 | 拿什么 |
|---|---|---|---|
| W4 评估 | 每个动作后 | 动作产物 | accept/fail/rollback |
| W5 反思 | 每 20 action | failures 聚类 | W1-W4 规则 patch |
| W7 引文核验 | 引文动作 | 引文清单 | hit/near/miss + 定位符 |
| W9 页型反思 | 每轮 | 3 个新页 | 模板提案（templates/） |
| W10 主循环 | 每 10 轮 | 健康度快照 | 下轮队列 |
| W13/W14 | 覆盖/洞察 | 覆盖缺口/洞察候选 | 页面选题 |

---

## 七、工具与脚本

| 工具 | 用途 | 命令（可复跑） |
|---|---|---|
| `scripts/generate_w8_pages.py` | W8 页生成器（person 卡页型；demo 默认；dry-run/--apply/--selftest） | `python scripts/generate_w8_pages.py --selftest` |
| `scripts/verify_quotes.py` | W7 引文核验（发布门禁） | `python scripts/verify_quotes.py --all --strict` |
| `scripts/build_sku_cards.py` | N10 SKU 卡（W 组主要素材源） | `python scripts/build_sku_cards.py --help` |
| `scripts/export_site_all.py` | EX 导出层串行收口（W 组输出下游） | `python scripts/export_site_all.py --dry-run` |
| `scripts/lint_consistency.py` | N8 一致性 lint（事实/PN 门槛） | `python scripts/lint_consistency.py --help` |
| `scripts/lint_taxonomy.py` | N9 分类树 lint（W11/W10i 依据） | `python scripts/lint_taxonomy.py --selftest` |

> 规范引用：SKU 字段见 `skills/SKILL_08a_SKU字段_武侠版.md`；关系边见 `skills/SKILL_关系体系_武侠版.md`；时间锚见 `skills/SKILL_时间体系_武侠版.md`；跨书 canonical/display 见 `skills/SKILL_跨书治理_武侠版.md`；分类树见 `skills/SKILL_分类树五件套_武侠版.md`；渲染/发布契约见 `skills/SKILL_03d_渲染发布_武侠版.md`；页型模板见 `templates/忠义殉主者.md`。

---

## 八、检查清单（每轮 invocation）

- [ ] 本轮轮号/模式/队列来源已记录；P0 无饥饿；
- [ ] 动作来自 W2 目录且单动作 diff ≤20 行（精品页例外）；
- [ ] 页面字段有来源；未知字段=未明示；无原文连续 ≥10 字片段；
- [ ] 引文已过 W7（或列 `quote_status: pending` 不入发布）；
- [ ] `actions.jsonl` 已写；失败有 rollback 记录；
- [ ] 未触碰 tagged/registry/site；demo 页仍 demo:true；
- [ ] 本轮结束跑 W9 反思（若新增页面 ≥3）；
- [ ] 每 10 轮出健康度快照；每 20 action 触发 W5。

## 九、成功标准（W0 上线判据）

1. 连续 20 轮 invocation 零越界（tagged/registry/site 写入 = 0、无源断言 = 0、原文片段 = 0）；
2. 每轮 7 步痕迹完整率 100%；failures 100% 有分类与回滚记录；
3. W7 `--strict` 在门禁批次中 exit 0；near 清单人工复核率 100%；
4. 20 轮内 W5、W9 各至少触发 1 次且产出可执行 patch/模板；
5. 健康度六指标可复跑（`logs/w_group/health.jsonl` 连续快照）。

## 附录 A · 与 shiji `SKILL_W0_Butler总则` 差异对照

| shiji 要素 | 武侠处理（20:80） | 说明 |
|---|---|---|
| 厨师哲学/永续 loop | **照搬**（框架层） | 内容不迁移；运行载体换武侠路径 |
| 六不变量 | **照搬并补第 7-9 条** | 增"不输出原文/demo 隔离/并发错峰"武侠红线 |
| 四队列（P0/P1/P2）/WU | **照搬**，字段换 W1 六源 | W1 食物地图按武侠 registry 重写 |
| wiki/public/pages 写入 | 换 `content/` 草稿 + EX 导出 | 不直接写 site；发布状态三档 |
| actions.jsonl/memory | 照搬，路径换 `logs/w_group/` | 保留 round/action/target/source/rationale |
| 14 子 SKILL 分工 | 换 W1-W14 38 节点（见设计 brief） | W 组拆分口径 38（docs/05/17） |

## 附录 B · 待补/待拍板

| # | 待补 | 默认立场 | 影响 |
|---|---|---|---|
| B-1 | W0 运行载体（脚本化 round 调度 vs 人工/Lead 驱动） | 先人工+日志，脚本化延后 | 并发与节奏 |
| B-2 | 发布状态三档是否与 site `publish_state` 字段同源 | 以 EX 导出层字段为准 | 发布门禁 |
| B-3 | W5 反思触发阈值（20 action vs 10 轮） | 20 action（shiji 原典） | 自改频率 |
| B-4 | 多实例锁实现 | 首期单实例，多实例按 shiji claim_round 移植 | 并发 |
| B-5 | W 组与 META 复盘接口（W 组健康度进 META-00 批次复盘） | 批次收口引用 health.jsonl | 复盘质量 |
