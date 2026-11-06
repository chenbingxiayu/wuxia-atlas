---
name: skill-02h-wuxia
title: 词表维护（双轨·统一 Schema·三档运营·20 表）
description: 武侠知识库词表体系的维护执行规范：20 张词表（WL-01~WL-20）的清单与优先级、统一 Schema 八字段（surface/canonical/type|domain/tier/conf/evidence/status/version）、双轨五铁律（源表唯一编辑面/派生单向再生成/候选不直写/视图分离/一致性校验）、三档运营（auto/review/watch）与派生规则、验证五分类（tagged/verbatim/partial/narrative/unverified）、版本协议与消费方接口，以及 wordlist_compiler 编译/校验操作。当需要"新增或修订词表条目、判断档位、做源表与派生 JSON 对账、升版本"时使用；词表设计总纲见 SKILL_词表体系规划（D09）。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 02h 武侠版：词表维护

> **上游声明**：本文是 D09 词表体系规划（`SKILL_词表体系规划_武侠版.md`，v0.3-draft）的**维护执行件**：20 表清单、统一 Schema、双轨三档、验证五分类、版本协议由 D09 定版；本文只负责"日常怎么改词表、怎么编译、怎么对账、怎么升版本"。词表消费方（masker/标注/lint/搜索/分类树）与符号体系分别由 `SKILL_01g_标注符号集合原则.md`（D01）、`SKILL_分类树五件套_武侠版.md`（D08）定版；编译器为 C0 `scripts/wordlist_compiler.py`。
> **移植依据**：`docs/05-管线技能与脚本逐项改造分析.md`（02h 词表维护：双轨/三档/schema 迁移）；`docs/17` §2.5（S-02h ←D09）；`docs/56`/`docs/57`（词表现状：19 文件=8 源+10 表+1 候选池；`wordlist_compiler --check` 8/8 PASS；全部 `auto_ready=0`）。
> **核心原则**：**源表唯一编辑面，派生单向再生成**。手改派生 JSON 无效且会被下次编译冲掉；候选永不直写派生；档位（tier）由 conf×status 派生，不手填。

---

## 一、技能定位与边界

### 1.1 工序位置（词表数据面）

```text
wordlists/<wl>_source.md|json（人工可读可 diff 的唯一编辑面）
        ↓ wordlist_compiler.py（编译）
wordlists/<wl>.json（发布视图） + <wl>_watch.json（观察视图）
        ↓ 消费
A LLM 标注提示词 · B lint 家族 · C 全站搜索 · D 分类树五件套 · E 阅读器 · F 考订工具
        ↓
标注批次/页面/词表版本留痕（tagged meta.wordlists_version）
```

- **前置**：D09 统一 Schema 定版、`wordlist_compiler.py` 可用、词表源文件在 `wordlists/`。
- **后继**：标注批次消费、lint 拦截、搜索联想、分类树叶子表（WL-15~19）。
- **现行事实（2026-11-05）**：`wordlists/` 共 **19 文件**＝8 源 + 10 表（8 编译 + 2 手工：rhetoric 49、fossil_verb_objects 3）+ 1 候选池；`wordlist_compiler.py --check` **8/8 PASS**；全部表 `auto_ready=0`（tier 全 review/watch，禁批量）。

### 1.2 本文做什么（六件事）

1. **维护 20 表**：清单、优先级、规模、负责人角色（§三）；
2. **统一 Schema**：八字段与扩展池（§四）；
3. **双轨流程**：源表修改 → 编译 → 对账 → 版本（§五）；
4. **三档运营**：auto/review/watch 的准入、晋升、降级（§六）；
5. **验证五分类**：tagged/verbatim/partial/narrative/unverified 与 conf 联动（§七）；
6. **版本协议**：批次声明、语料留痕、消费方接口（§八）。

### 1.3 本文不做什么（边界，越界即错）

- **不手改派生 JSON**：`<wl>.json`/`<wl>_watch.json` 只能由编译器生成（T2/W01）；
- **不直写候选**：扫描候选只进源表候选区，经门槛确认才转正式条目（T3）；
- **不重定档位语义**：tier 三档语义以 04f 定版为准，conf 图例以招式表定版为准（D09 §3.7）；
- **不设计新表**：新增词表走 D09 §二清单修订（附录 B），不在维护环节临时加表。

---

## 二、快速开始（五步维护序）

> 目标：改一条词表 → 编译 → 对账 → 升版本 → 通知消费方。命令只读或只写词表产物。

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
$env:PYTHONIOENCODING='utf-8'

# Step 1 改源表（唯一编辑面）：wordlists/<wl>_source.md 或 _source.json
#   骨架八字段 + 登记扩展；候选只写「候选区」（带扫描批次号）

# Step 2 编译单表 / 全部 / 校验（--check 只校验不写）
python -X utf8 scripts\wordlist_compiler.py --name identity
python -X utf8 scripts\wordlist_compiler.py --all
python -X utf8 scripts\wordlist_compiler.py --check

# Step 3 对账：源表行数 = 派生 totals；watch 未混入发布视图；auto_ready 符合预期
python -X utf8 -c "import json;d=json.load(open('wordlists/identity.json',encoding='utf-8'));print(d['meta']['totals'])"

# Step 4 升版本：条目增删改升 MINOR；字段/枚举变更升 MAJOR 并同步 D09 §3.7 字典
# Step 5 通知消费方：批次声明词表快照（meta.version 集合），标注产物回写 wordlists_version
```

**判读口径**：Step 2 的 `--check` 应 8/8 PASS（当前 8 张编译表）；Step 3 的 `totals.auto_ready` 当前为 0（批量门控生效，符合"禁批量"纪律）。

---

## 三、20 表清单（D09 §2.2，摘要）

| 编号 | 词表 | 实体码/域 | 优先级 | 规模预估 | 构建 |
|---|---|---|---|---|---|
| WL-01 | 绰号-本名映射表 | `@` 别名 | P0 | 500-1,500 | S+M2 |
| WL-02 | 职衔表 | `;` | P0 | 200-400 | M2×M3 |
| WL-03 | 时间词表 | `%` | P0 | 60-100 | M2 |
| WL-04 | 停用泛称表 | 域=停用 | P0 | 100-200 | M1 |
| WL-05 | 动词域词表族 | 域=动词（⊞ 等六域） | P0 | 约 140 起 | S |
| WL-06 | 招式表 | `☆` 招式 | P0 | 222→约 500 | T+M2 |
| WL-07 | 武功表 | `☆` 功法 | P1 | 150-300 | M2+M1 |
| WL-08 | 门派及别名表 | `◆` | P1 | 约 100（含别名 200） | M2+M3 |
| WL-09 | 兵器表 | `•` | P1 | 226→约 300 | T |
| WL-10 | 套语信号表 | 域=套语 | P1 | 60-100 词族 | S+M2 |
| WL-11 | detection 语式表 | 域=语式 | P1 | 30-60 | S+M1 |
| WL-12 | 身份表 | `#` | P2 | 100-200 | M2+M1 |
| WL-13 | 亲属称谓表 | 域=称谓 | P2 | 80-120 | M1 |
| WL-14 | 数量词表 | `$` | P2 | 50-80 | M2 |
| WL-15~19 | 五树叶子表（地点/职衔/身份/势力/武功） | `=`/`;`/`#`/`◆`/`☆` | P2 | 每树 10-20 叶 | 占位（D08 交付） |
| WL-20 | 地名表（gazetteer 接口） | `=` | P1（接口） | 约 650 | T |

> **WL-20 接口注记**：gazetteer 的 conf/status/verify 与词表骨架**字段名相近不等于同字段**——按 D10 定稿执行，本体系只定接口对齐（D09 §2.2 注记）。

---

## 四、统一 Schema（八字段，D09 §3.2）

| # | 字段 | 必填 | 语义 |
|---|---|---|---|
| 1 | surface | 必填 | 词形（字面串或受控模板；模板须给 surface_kind） |
| 2 | canonical | 条件必填 | 规范形式（稳定键）；**缺省=surface 自指**；消歧/映射类表必填 |
| 3 | type 或 domain | 必填（二选一） | 实体表用 15 类实体码；非实体表用域码（动词域/套语/语式/停用/称谓） |
| 4 | tier | 必填 | 运营档位：auto/review/watch（语义以 04f 定版为准） |
| 5 | conf | 必填 | 证据强度：strong/ok/weak（图例承招式表 conf_legend） |
| 6 | evidence | 条件必填 | 证据锚 `[{book, loc, kind}]`，loc=`回:段` |
| 7 | status | 必填 | 生命周期：auto/待审/已核准 |
| 8 | version | 必填 | 条目修订号（入库=1，每次修订 +1）；文件级版本在 meta |

**扩展字段**：扁平顶层、snake_case、经共享池登记后使用（`surface_kind/disambig/book_scope/…`）；**不用 ext 包裹、不双轨兼容**（D09 §3.5）。

---

## 五、双轨五铁律与更新流程

### 5.1 五铁律（D09 §4.1）

| # | 铁律 | 要点 |
|---|---|---|
| T1 | 源表唯一编辑面 | 增删改只发生在 `<wl>_source.md`（可读可 diff） |
| T2 | 派生单向再生成 | `<wl>.json`/`<wl>_watch.json` 只由编译器生成；手改无效（W01） |
| T3 | 候选不直写 | 扫描候选只进源表候选区（折叠节+批次号），确认后转正式条目 |
| T4 | 视图分离 | 发布视图与观察视图物理分文件；晋升/降级经再生成自然流转 |
| T5 | 一致性自动校验 | 源表与派生 totals/版本不一致即报警阻断合并 |

### 5.2 源表更新流程（D09 §4.2）

1. 改 `<wl>_source.md`（含八字段与登记扩展）；
2. 跑该表编译（源表 → 发布/观察两视图）；
3. 对账：totals 与源表行数一致、watch 未混入发布；
4. `meta.version` 递增（MINOR/MAJOR）；
5. `_registry.json` 再生成（登记最新版本号）；
6. 消费方声明新版本；旧批次 tagged 不强制重标；回滚 = 源表 git revert + 重跑编译。

---

## 六、三档运营（auto/review/watch）

### 6.1 派生规则（conf×status→tier，D09 §3.3）

| conf＼status | auto（机核通过） | 待审 | 已核准 |
|---|---|---|---|
| strong | **auto** | review | auto |
| ok | review | review | auto |
| weak | **watch**（恒定） | watch | watch* |

\* 核准 weak 条目须先补证据把 conf 升到 ok/strong；"人工核准一个无锚条目"被禁止（W02）。

### 6.2 三档运营动作

| 档 | 准入 | 运营 | 晋升 | 降级 |
|---|---|---|---|---|
| auto | strong+已核准；或 auto+计数验证+剥标还原（≥95%） | 进 LLM 提示词词表正则兜底层 | — | lint 误标→降 review |
| review | ok；或 strong 未过机核；或 watch 晋升 | 逐条语境判定，核准后 status=已核准；争议双人复核 | 连续两批剥标还原 ≥95% 且抽样 20 条零误标 → auto | 歧义/撞名 → 降 watch 并补 disambig |
| watch | weak；或 verify∈{narrative,先验无锚}；或负清单例外 | 观察回填：每轮重扫描统计命中 | 命中 ≥3 独立案例（不同回/书）→ review | 连续两轮零命中且无考订 → 归档（不删） |

### 6.3 发布规则（D09 §3.3）

- R1：conf=weak ⇒ tier=watch ⇒ 只进 `<wl>_watch.json`，永不进发布视图；
- R2：verify=unverified 的条目禁入任何视图（先修正或删除）；
- R3：tier=auto 的额外前置（计数验证/剥标还原）在运营层执行。

---

## 七、验证五分类（D09 §六）

| 分类 | 定义 | 判定 | conf |
|---|---|---|---|
| tagged | tagged.md 中已有 01g 直接标注（别名形由 WL-01 回链） | 有标注符号锚 | strong |
| verbatim | 规范化后在纯文本原样出现（含回目、白话引语） | 逐字命中 | strong |
| partial | 变体命中：绰号截称/加缀/模板部分命中 | 可还原到完整词形 | ok |
| narrative | **非正文原文的概括（语料外来源）**：考订/研究/集合概念 | 语料外来源 | weak |
| unverified | 纯文本找不到且无标注 | — | **禁入**（修正/删除） |

> **关键差异**（D09 §6.1）：文言版 narrative 指"括号叙事"；武侠版推广为"一切语料外来源"。"人称玉罗刹"中的"玉罗刹"是语料内可证文本（partial），**不是 narrative**——不得把语料内文本错降为 weak。

---

## 八、版本协议与消费方接口

### 8.1 版本协议（D09 §4.4）

- P1 批次声明：标注批次启动时声明词表快照（各表 meta.version 集合）；
- P2 语料留痕：标注产物 meta 回写 `wordlists_version`；
- P3 lint 校验：比对语料 meta 与 `_registry.json`，不一致 → WARN（不阻断）；
- P4 同批同版：同批次禁混版本；中途升版必须重开批次；
- P5 MAJOR 升版：字段/枚举变更后旧语料不强制重标，但渲染层需显示"该标注产生于 v1.x"。

### 8.2 消费方接口

| 消费方 | 读取与过滤 | 版本要求 |
|---|---|---|
| A LLM 标注提示词 | 发布视图；按 tier（兜底层只用 auto）+type/domain | 必须指定版本 |
| B lint 家族 | 发布+观察视图；按 signal_role+type | 必须指定版本 |
| C 全站搜索 | 发布视图；按 surface/canonical 索引 | 取最新 |
| D 分类树五件套 | 叶子表引用键；消费主表 tier/conf | 随主表 |
| E 阅读器/渲染 | 发布视图；按 surface 匹配专名候选 | 取最新 |
| F 考订工具 | 全条目（含观察）；按 conf/status 过滤 | 必须指定版本 |

---

## 九、现有实现对照（2026-11-05 实测）

| 项 | 现状 |
|---|---|
| 文件数 | 19 = 8 源 + 10 表（8 编译 + 2 手工）+ 1 候选池 |
| 编译表 | verbs 165 / structure_markers 12 / stopwords 18 / time_words 19 / quantity 36 / identity 212 / kinship 62 / new_entity_types 268（8 张） |
| 手工表 | rhetoric 49 / fossil_verb_objects 3（无 _source） |
| `--check` | 8/8 PASS；全部 `auto_ready=0`（禁批量门控生效） |
| 候选池 | rhetoric_candidates_v0.json（53 条，docs/35 已裁定，不计入 10 表） |
| 待补 | senses 运营（verbs 多义未分型）；WL-15~19 叶子表填充；WL-01~03 等 P0 表落地 |

---

## 十、工具与脚本

| 工具 | 用途 | 关键参数 |
|---|---|---|
| `scripts/wordlist_compiler.py`（C0） | 双轨编译：源表 → 发布/观察 JSON；校验 | `--all/--name/--check` |
| `scripts/masker.py`（C0） | 词表驱动候选召回与掩码（消费方） | import |
| `scripts/symbols.py`（C0） | 15 类符号唯一来源（type 字段校验） | import |

产物：`wordlists/*.json`（10 表）、`wordlists/*_source.*`（8 源）、候选池；报告建议 `logs/qa/wordlist_<name>_report.md`。

---

## 十一、检查清单

**改表前**
- [ ] 改的是源表（不是派生 JSON）；候选进候选区；
- [ ] 八字段齐全（canonical 缺省=surface 自指）；
- [ ] tier 由 conf×status 派生，非手填；evidence 可锚。

**改表中**
- [ ] type/domain 二选一且与表一致；
- [ ] 模板条目带 surface_kind；模板命中≠实词；
- [ ] weak 条目只进观察视图；unverified 不入库；
- [ ] 版本号按 MINOR/MAJOR 规则递增。

**改表后**
- [ ] `wordlist_compiler --check` PASS；totals 与源表行数一致；
- [ ] watch 未混入发布视图；auto_ready 符合门控预期；
- [ ] `_registry.json` 已更新；消费方已声明新版本；
- [ ] 若涉及词表结构/枚举，D09 §3.7 字典已同步。

---

## 十二、成功标准（Success Criteria）

1. **单一编辑面**：派生 JSON 手改 = 0；源表与派生可对账（T1/T2）。
2. **档位合规**：tier 由规则派生率 100%；weak 不进发布视图；unverified 入库 = 0。
3. **编译稳定**：`--check` 8/8 PASS；同源表重编译幂等。
4. **版本可溯**：每次改动 meta.version 递增；批次声明与语料留痕可查。
5. **消费一致**：A-F 消费方版本声明齐全；lint 版本不一致有 WARN。

---

## 十三、相关文档

- `SKILL_词表体系规划_武侠版.md`（D09，20 表/Schema/双轨三档/验证五分类/版本协议）
- `SKILL_01g_标注符号集合原则.md`（D01，15 类符号与 tier 语义）
- `SKILL_分类树五件套_武侠版.md`（D08，WL-15~19 叶子表）
- `SKILL_地名gazetteer_武侠版.md`（D10，WL-20 接口注记）
- `SKILL_03a_实体标注.md`、`SKILL_04f_动词标注.md`（词表消费方 A）
- `docs/56-loader回级与N4N5实现记录-2026-11-05.md`、`docs/57-依赖分波与8路并行执行记录-2026-11-05.md`

---

## 附录 A · 源表行模板

```markdown
| surface | canonical | type/domain | tier | conf | evidence | status | version |
|---|---|---|---|---|---|---|---|
| 白发魔女 | 练霓裳 | @ | review | strong | 白发魔女传:20:12 | 已核准 | 1 |
| 掌门 | 掌门 | ; | review | ok | 白发魔女传:3:7 | 待审 | 1 |
```

```json
{"surface": "白发魔女", "canonical": "练霓裳", "type": "@",
 "tier": "review", "conf": "strong",
 "evidence": [{"book": "白发魔女传", "loc": "20:12", "kind": "别名直证"}],
 "status": "已核准", "version": 1}
```

## 附录 B · 待拍板（引 D09 附录 B，不在本文重开）

1. P0 排序口径（按实验盲区/先建表优先）——B-1；
2. surface 模板算子集（三种/受限正则）——B-2；
3. weak 条目对搜索联想例外——B-3；
4. 04f 迁移 conf 推导规则——B-4；
5. signal_role 枚举（三值/四值）——B-5；
6. 亲属称谓/数量词表去留——B-6；
7. 词表正则编译目标（提示词片段/lint 规则）——B-7；
8. 每表负责人到人——B-8。

*本文为词表维护执行件；Schema/档位/版本协议冲突时以 D09（`SKILL_词表体系规划_武侠版.md`）为准。*
