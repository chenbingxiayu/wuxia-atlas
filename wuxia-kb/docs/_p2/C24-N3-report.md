# C24 + N3 实现报告（P2 实体一致性 / 动词校验）

- 日期：2026-11-04
- 执行：verify-builder（P2 实现工程师）
- 共享任务：`task-7`（C24 实体对照表 + N3 动词标注校验器）
- 状态：✅ 两脚本落地并实跑通过；tagged 零改动；未 commit、未调 LLM

## 〇、交付物

| 交付物 | 路径 | 规模 |
|---|---|---|
| C24 脚本 | `scripts/build_entity_concordance.py` | 591 行；移植自 shiji 同名脚本并结构适配 |
| N3 脚本 | `scripts/validate_verb_tagging_wuxia.py` | 1,070 行；新写（无源件） |
| C24 产物 | `registry/concordance/白发魔女传.json` / `.md` | JSON 4.49 MB；MD 486 行 |
| N3 产物 | `logs/verb_validation/白发魔女传.json` / `.md` | JSON 429 KB；MD 655 行 |
| 本报告 | `docs/_p2/C24-N3-report.md` | — |

权威依据：`docs/17 §2.2 C24 / §2.3 N3`、`docs/05 §2.8`、`skills/SKILL_04f_动词标注.md`
（§2.0 主域总表、§3.1 边界、§3.3 消歧、§3.5 嵌套、§4 联动、§5.2/§5.4 词表、§6.1 密度）；
符号契约：`scripts/symbols.py`（15 实体类 / 6 动词域 / `TOKEN_RE` / `parse_token` / `ANCHOR_FMT`）；
路径契约：`scripts/config.py`（`DIR_TAGGED` / `DIR_REGISTRY` / `DIR_WORDLISTS` / `DIR_LOGS`）。

---

## 一、C24 · 实体对照表（concordance）

### 1.1 相对移植源的改动（对应 docs/05 §2.8“砍 wiki 依赖、PREFIX_LABELS 补全”）

1. **路径接 config**：扫描 `config.DIR_TAGGED/<book>/NNN.tagged.md`，输出
   `config.DIR_REGISTRY/concordance/<book>.{json,md}`；原版相对 cwd + 写死
   `docs/wiki/data/entity_concordance.json`。
2. **符号接 symbols**：`PREFIX_LABELS` 直接取 `symbols.ENTITIES`（15 类），原版硬编码
   11 类并用 `SKIP_PREFIXES` 静默丢弃 `%$`，会漏 `◎☆{^` 等类；脚本内不再重写字符类。
3. **砍 wiki 依赖**：删除 `pages.json` / `redirect_map` / `has_page`；登记对照改读
   `registry/entities.json`（本仓登记层唯一来源，scope=人物/组织/家族）。
4. **归并键改为 (type, canonical)**：同名不同类分开；补显示串变体、分回次数、
   章回分布、首次出现 PN 锚点、管道映射统计、未登记清单、别名映射单列。
5. **输出 JSON + Markdown 双件**，并把 `--book/--chapters/--out/--min-count` 做成 CLI。

### 1.2 关键口径（均写入脚本 docstring）

| 口径 | 约定 | 理由 |
|---|---|---|
| canonical | 除 `%` 外，管道右侧即规范名（`〖@显示名\|规范名〗`） | 01g 管道语义 |
| `%` 时间类 | canonical = **显示串**；管道右侧（时点/时长/年龄，实测 1047/1048 带管道）作为 `subtype_tags` 另存 | 右侧是受控子标签而非规范名（SKILL_02d §3；`qa_annotation_report.py` 同口径）。若按普通管道归并，586 个时点会塌成“时点”一个实体 |
| 首次出现 | 行内 PN `[N]` → `symbols.ANCHOR_FMT` = `书#pn-r{回}.{段}`（如 `白发魔女传#pn-r1.41`） | 02ab 两级 PN，本批实测 124 个一级 PN、无 `[N.M]` |
| 回目 `[0]` | `# [0]` 行照扫但**不算正文段**：不做 first，计入 total；本批回目 0 个实体令牌 | 02ab 回目固定 PN |
| 围栏 | 围栏内正文照计实体；围栏标记行不计 PN | 实体层“限实指”是标注环节职责，本脚本只做索引 |
| 未登记 | registry scope（@◆&）：canonical 直登 → `registered`；aliases/contextual 命中 → `alias_mapped` 单列；否则 `unregistered` | registry/entities.json 自述 scope；scope 外 12 类单列 `out_of_scope`（地点→gazetteer、技艺/概念→词表） |

### 1.3 实跑结果（32 回全量，2026-11-04）

命令：`python scripts/build_entity_concordance.py --book 白发魔女传`

- **32,731 次实体出现 → 4,992 个 (类型, 规范名) 组**；解析跳过 0 个令牌；
  15 类全部有覆盖。
- 5,264 个显示串（分类型去重求和；同一写法跨类重复计入）；556 个实体含管道映射（5,365 次管道出现）。

| 类型 | 符号 | 实体数 | 出现数 | 出现占比 | 唯一显示串 |
|---|---|---:|---:|---:|---:|
| 人物 | 〖@〗 | 303 | 15,597 | 47.65% | 573 |
| 人物群组 | 〖◎〗 | 14 | 95 | 0.29% | 15 |
| 地点 | 〖=〗 | 657 | 2,370 | 7.24% | 657 |
| 组织 | 〖◆〗 | 62 | 694 | 2.12% | 63 |
| 家族世系 | 〖&〗 | 14 | 71 | 0.22% | 14 |
| 族群 | 〖~〗 | 8 | 52 | 0.16% | 8 |
| 职衔 | 〖;〗 | 122 | 567 | 1.73% | 122 |
| 身份 | 〖#〗 | 796 | 3,091 | 9.44% | 796 |
| 武功技艺 | 〖☆〗 | 252 | 783 | 2.39% | 252 |
| 器物 | 〖•〗 | 891 | 2,665 | 8.14% | 891 |
| 生物 | 〖+〗 | 55 | 130 | 0.40% | 55 |
| 作品文书 | 〖{〗 | 95 | 356 | 1.09% | 95 |
| 专门概念 | 〖^〗 | 367 | 943 | 2.88% | 367 |
| 时间 | 〖%〗 | 451 | 1,048 | 3.20% | 451 |
| 数量 | 〖$〗 | 905 | 4,269 | 13.04% | 905 |

TOP 实体（出现数）：练霓裳 2,587（18 变体，首见 `白发魔女传#pn-r1.41`）、卓一航 1,992、
铁飞龙 993、岳鸣珂 945、慕容冲 471、王照希 414。变体示例：练霓裳←
玉罗刹(2321)/白发魔女(88)/练姐姐(75)；卓一航←卓兄(50)/一航(34)；公孙大娘←红花鬼母(350)。

### 1.4 与 registry 对照（任务要求的核心验收）

`registry/entities.json`：version=0.1-draft，**70 条**（@52 / ◆15 / &3）。

| 指标 | 数值 |
|---|---:|
| registry 70 条中被语料命中（canonical 直登） | **69** |
| 未被语料使用 | 1（`◆ 东西两厂（东厂+西厂合称）`，语料以 `东西厂` 出现，走别名） |
| concordance 中 scope=@◆& 实体 | 379 |
| ├ registered（canonical 直登） | **69** |
| ├ alias_mapped（别名/上下文称谓命中） | **9** |
| └ **unregistered（未登记清单）** | **301**（@246 / ◆44 / &11） |

**未登记 Top 10**：慕容冲(471)、白石道人(402)、公孙大娘(381)、金独异(252)、客娉婷(245)、
黄叶道人(186)、李天扬(149)、晦明禅师(137)、何绿华(135)、杨涟(132) —— 均为语料高频但
registry 尚未收录的人物，可直接作为登记层补录队列（JSON `unregistered` 含全量 301 条）。

**别名可映射 9 条**（canonical 未直登但 aliases/contextual 命中，已在 JSON/报告单列）：
`武当→武当派(72)`、`珊瑚→铁珊瑚(18)`、`少林→少林派(7)`、`熊经略→熊廷弼(3)`、
`东西厂→东西两厂(2)`、`柳叔叔/柳伯伯→柳西铭(各1)`、`郑国舅→郑国泰(1)`、`嵩阳→嵩阳派(1)`。

**登记范围外 12 类**（不属 C24 责任，只给规模）：地点 657、身份 796、器物 891、
数量 905、时间 451、专门概念 367、武功技艺 252 等——权威登记分别归 gazetteer（docs/14）
与词表（docs/13）。

### 1.5 CLI 实测

| 命令 | 结果 |
|---|---|
| `--book 白发魔女传` | 4,992 实体 / 32,731 次 |
| `--chapters 1-3 --out <tmp> --min-count 5` | 3 回 989 组 → 输出 117 个（≥5 次）2,061 次 |
| `--chapters 1-2,99` | 正常输出 2 回；`missing_chapters:[99]` 并打印 ⚠ |
| 跨 cwd（从 repo 根调用） | 正常（路径全部经 config） |

---

## 二、N3 · 动词标注校验器

### 2.1 处理流程

1. **结构扫描**（不依赖 `TOKEN_RE` 的单遍括号栈）：三层括号 `〖〗/⟦⟧/〘〙` 配对与嵌套，
   产出 span 供“动词∩实体区间”重叠检测；未闭合/错配/嵌套/交叉重叠各自计数。
2. **令牌抽取**：逐行 `symbols.TOKEN_RE` 定位 + `symbols.parse_token` 解析，行内 PN 推锚点；
   同时累计剥标正文字数（密度分母）。
3. **逐令牌语义判定**：域码、空触发词、标点/空白、单字虚词、超长、空消歧说明、
   verbs.json 白名单域冲突、多域未消歧（词表多域 + 语料实测多域少数派域）、
   域混淆启发式、联动强制实体缺失、新词候选。
4. **全局后处理**：跨回词形多域统计、新词候选汇总 topN、单段 >10 处回查、分回密度阈值。
5. **输出**：JSON（机器消费）+ MD（错误/警告/建议/信息分列、分回表、Top 问题）。
   `--strict` 有 error 时 exit 1。

### 2.2 规则对照表（N3 每条 ↔ SKILL_04f 章节）

| 类别 | 级别 | 规则 | 04f 依据 | 实现要点 |
|---|---|---|---|---|
| E-DOMAIN | error | 类型码不在 6 域 | §2.0 / 01g §2.2.3 | `parse_token` 返回错误或码不在 `symbols.VERB_CODES` |
| E-UNCLOSED / E-CLOSE-MISMATCH | error | 括号闭合/配对 | §3.5 | 括号栈；本批 0 |
| E-NESTED | error | 动词内不得含任何标注、实体名内不得拆动词 | §3.5 | 栈内再开标注即记；本批 0 |
| E-OVERLAP | error | 与实体区间不重叠 | §3.5 | span 交叉（非包含）检测；本批 0 |
| E-PUNCT | error | 触发词含标点/空白 | §3.1 | 只看显示串（管道前）；消歧说明允许标点；本批 2 |
| E-DISAMBIG-EMPTY / E-EMPTY-SURFACE | error | 消歧说明/触发词不得为空 | §3.3 | 管道后空串判错；本批 0 |
| E-WL-DOMAIN / W-WL-DOMAIN | warning（`--wordlist-strict` 时 error） | surface 在 verbs.json 则域必须一致 | §5.2/§5.4 | 词表主域 vs 实际域；附 tier 与“补 senses”提示；本批 58（Lead 校准后默认 warning，见 §七） |
| W-LONG | warning | 触发词 > 8 字 | §3.1/§3.2 | 本批 0（最长 7 字） |
| W-FUNC | warning | 单字虚词（了/着/的/地） | §3.1 | 按任务允许的 warning 级处理（白话“着了一下”或具实义，交人工）；本批 1 |
| W-MULTIDOMAIN | warning | 一词多域未消歧 | §3.3 | ①verbs.json 同 surface 多 domain（当前 0 组，留钩子）；②**语料实测**同 surface ≥2 域、本处落少数派域且无 `|` 说明；本批 262 |
| W-DENSITY | warning | 分回 V/100 字 < 0.5 或 > 3.0 | §6.1 + G0 B-5 | 分母=剥标正文字符；本批 1（017 回 0.46） |
| S-CONF-ROB | suggestion | 劫人→■ / 劫财→⊟ | §2.0 P3-⑤ | 同句宾语线索（财物/包袱/金银 vs 孩子/带走/肉票），本批 4 |
| S-CONF-DETAIN | suggestion | 拘押/判刑→⊡ | §2.3 | 固定期望域；本批 0 |
| S-CONF-DEATH | suggestion | 处死/死亡→⊠ | §2.0/§2.2 | 固定期望域；本批 0 |
| S-CONF-BATTLE | suggestion | 战斗交锋→⊞ | §2.1 | 核心词直判；多义词（突围/挑战/动手…）需战斗语境佐证；本批 0 |
| S-CONF-TEACH | suggestion | 传习→▣ | §2.5 | 教/学/练/指点等需技艺语境佐证；本批 0 |
| S-CONF-CURE | suggestion | 治疗/中毒→⊠ | §2.2 | 固定期望域；本批 0 |
| S-CONF-MOVE | suggestion | 行程级→■；战斗现场脱离/追击→⊞ | §2.6/§2.1 | 明确行程词固定期望 ■；走/逃/退/追/跑 仅在战斗短语佐证时提示 ⊞；本批 4 |
| S-CONF-RESULT | suggestion | 结果决定主域（⊞ 动作 + 死亡结果 → ⊠） | §3.1 | 同句死亡/致害补语检测；本批 9 |
| S-POSTURE | suggestion | 姿态/身法不入 ■/⊞ | §2.1/§2.6（V1-2/V6-1） | 跳出/跃出/掠出/闪避…；本批 43 |
| S-USAGE | suggestion | 施用已会武功不重复标 ▣ | §2.5（V5-1） | 使出/施用/使用；本批 0 |
| S-PARA-DENSITY | suggestion | 单段触发词 >10 回查 | §6.1 规则 4 | 本批 79 段 |
| S-LINK-ART | suggestion | 传习强制联动 ☆ | §4.1 #1-#4 + §4.2 | 同句无 ☆ → 事件降级待审；本批 4 |
| S-LINK-PERSON | suggestion | 杀/疗伤等强制联动 @ | §4.1 #8-#10 | 同句无 @；本批 8 |
| S-LINK-OBJ | suggestion | 转移/毁损强制联动 •/{ | §4.1 #11-#15 | 同句无器物/文书；本批 0 |
| S-LINK-REL | suggestion | 关系类强制联动 @ | §4.1 #6/#19/#20 | 本批 0 |
| S-LINK-PLACE | suggestion | 行程类强制联动 = | §4.1 #21-#24 | 同句无地点；本批 12 |
| I-NEW-WORD | info | 词表外新词候选 | §5.2/§5.4 | 跨回汇总 topN（MD 50 / JSON 200） |

### 2.3 阈值与依据（脚本内常量均有注释）

**分回密度**（V/100 剥标正文字）：32 回实测 —— 均值 **1.441**、中位 1.418、p10 0.791、
p90 2.079、最小 **0.460**（017 回）、最大 **2.170**（013 回）。
- `DENSITY_LOW = 0.50`：取实测最小值附近（p10 以下），只标“整回动词层几乎缺标”；
- `DENSITY_HIGH = 3.00`：≈1.4×实测最大值，只用于回级捕捉“逐招轰炸”放大，避免误报武打密集回；
- `PARA_HIGH = 10`：04f §6.1 规则 4“每段 1-6 处正常、>10 回查”（G0 附录 B-5 裁决）；
- `MAX_SURFACE_LEN = 8`：04f §3.2 整词最长 5 字，>8 字几乎必然吞宾语/状语（§3.1）；
- 单字虚词 `{了,着,的,地}`：04f §3.1；按 warning（任务允许 error 或 warning）。
换书后应按新书分位重校，阈值集中在脚本顶部常量区。

### 2.4 实跑结果（32 回，2026-11-04）

命令：`python scripts/validate_verb_tagging_wuxia.py --book 白发魔女传`

- 校验 32 回，**5,869 个动词令牌**，剥标正文 **407,940 字**，基线 **1.439 V/100字**；
  结构面：嵌套 0 / 未闭合 0 / 错配 0 / 区间重叠 0。

| 级别 | 条数 | 构成 |
|---|---:|---|
| ❌ error | **60** | `E-WL-DOMAIN` 58（词表域冲突）+ `E-PUNCT` 2（`⟦■，四面了望⟧`、`⟦⊟，射上⟧`） |
| ⚠ warning | **264** | `W-MULTIDOMAIN` 262 + `W-FUNC` 1（`⟦⊞着⟧`）+ `W-DENSITY` 1（017 回 0.46） |
| 💡 suggestion | **163** | 单段回查 79 + 姿态/身法 43 + 联动缺失 24（地点12/人物8/传习4）+ 域混淆 17（结果9/劫夺4/位移4） |
| ℹ info | **2,210** | 词表外 distinct surface（覆盖 5,367 处）；MD Top 50 / JSON Top 200 |

Top 问题词形：跳出(S-POSTURE×22)、杀(E-WL-DOMAIN×17 / W-MULTIDOMAIN×9 / S-LINK-PERSON×5)、
交换(E-WL-DOMAIN×8)、劫(W-MULTIDOMAIN×8)、中(W-MULTIDOMAIN×8)、离开(S-LINK-PLACE×8)、
刺(E-WL-DOMAIN×7)。问题最多回：020(54)、022(41)、029(25)、016(24)、023(22)。

分回密度最低 017 回 **0.460**（62 V / 13,470 字；触发下界）、最高 013 回 **2.170**
（324 V / 14,931 字）；其余均在 0.5–3.0 区间内。新词候选 top10：
到63、走63、打54、斗52、抓45、挡40、走出40、点39、送35、追31。

### 2.5 CLI 实测

| 命令 | 结果 |
|---|---|
| 默认全量 | error 60 / warning 264 / suggestion 163 / info 2,210 |
| `--chapters 1-2 --json` | stdout 输出合法 JSON（chapter_count=2），不落盘 |
| `--chapters 1-2 --out-dir <tmp>` | 写入 `<tmp>/白发魔女传.{json,md}` |
| `--strict --chapters 19-20`（有 error） | **exit 1** |
| `--strict --chapters 1`（ch1 无 error） | **exit 0** |
| `--strict` 全量 | **exit 1** |
| 跨 cwd（repo 根调用） | 正常 |

---

## 三、抽样复核（N3，人工逐条核对原文）

| # | 位置 | 令牌 | 机器判定 | 原文/复核结论 |
|---|---|---|---|---|
| 1 | 019[1] | `⟦■，四面了望⟧` | E-PUNCT（error） | 原文“……⟦■跳上⟧〖•岩石〗⟦■，四面了望⟧”；触发词吞了逗号，标点应外置→**确认 error** |
| 2 | 023[26] | `⟦⊞着⟧` | W-FUNC（warning） | 原文“左边面上，已⟦⊞着⟧了一下”；“着”在中招义上或为实义动词，但单字触发词不合 §3.1 最小单位/消歧要求→**warning 合理，交人工改标** |
| 3 | 002[13] | `⟦⊠斩|斩杀⟧` | E-WL-DOMAIN（error） | 原文“……把他⟦⊠斩|斩杀⟧为两截”；按 §3.1 结果决定主域，⊠ 正确；错在词表 `斩` 只收 ⊞ 主域→**确认是词表分型缺口** |
| 4 | 001[41] | `⟦■跳出⟧` | S-POSTURE（suggestion） | 原文“陡的⟦■跳出⟧〖=圈子〗”；§2.6 同场景单次跳跃/战斗身法不标 ■→**建议成立，宜改 ⊞ 脱离或不标** |
| 5 | 022[60] | `⟦⊞抢⟧` | S-CONF-ROB（suggestion） | 原文“都扑去⟦⊞抢⟧那包袱”；按 §2.0 劫财→⊟→**建议成立** |
| 6 | 001[27] | `⟦⊞劫⟧` | W-MULTIDOMAIN（warning） | 原文“他们要⟦⊞劫⟧的是我……劫了小弟”；全书 `劫` 主域 ⊟(14)/■(6)，本处涉“劫人”宜 ■ 且未消歧→**warning 成立** |
| 7 | 017 回 | — | W-DENSITY（warning） | 62 动词 / 13,470 字 = 0.460，全书最低；该回为低武打叙事，不能仅凭阈值判漏标→**warning 供人工判断，已在局限注明** |

C24 抽样：`练霓裳` 首见 `白发魔女传#pn-r1.41`（ch1 line 89，与原文一致）；
`◆武当派` 由 14 处 `〖◆武当|武当派〗` 管道归并（总 228 次/27 回）；
`武当→武当派` 走 registry contextual 命中，归入 `alias_mapped` 而非未登记。

---

## 四、验证记录（全部实测）

```text
# 1) 语法编译
python -m py_compile scripts/build_entity_concordance.py scripts/validate_verb_tagging_wuxia.py
→ exit 0

# 2) 全量实跑
python scripts/build_entity_concordance.py --book 白发魔女传
→ 4,992 实体 / 32,731 次 / registry: 70 条命中 69 / unregistered 301
python scripts/validate_verb_tagging_wuxia.py --book 白发魔女传
→ error 60 / warning 264 / suggestion 163 / info 2,210

# 3) CLI 分支
--chapters / --out / --min-count / --json / --out-dir / --strict（exit 1/0）均实测通过

# 4) tagged 只读验证
32 个 tagged/白发魔女传/NNN.tagged.md 的 sha256 在“全量实跑前后”逐一比对：
Compare-Object 结果为空 → 32/32 完全一致，零改动

# 5) 跨 cwd
从 Wuxiaxiaoshuo/ 根调用两脚本：正常（config 以 __file__ 解析）

# 6) 未 commit、未调 LLM（脚本无网络/模型调用）
```

产物核对：`registry/concordance/白发魔女传.json` 含 `type_counts`（15 类）、
`unregistered`（301 条全量）、`entities`（4,992 条，含 variants/chapter_counts/first/registration）；
`logs/verb_validation/白发魔女传.json` 含 `errors/warnings/suggestions/infos/top_issues/chapters_stat`。

---

## 五、已知局限

**C24**
1. 仅做形式归并，不做语义归并：同人异名若未接管道会留在两个条目（如 `白石` 与
   `白石道人` 各成一组；`白发魔女` 无管道出现 15 次 → 未登记清单可见）。这是本表
   提示登记层补管道/补别名的输入，不是索引错误。
2. `%` 未按时间子标签拆分/归并（子标签是受控标签而非规范名），时间语义归 N4 时间轴。
3. 未登记判定只覆盖 registry scope（@◆&）；地点/器物等由 gazetteer/词表负责（报告 5.3 仅给规模）。
4. 首次出现基于行内 PN；多行围栏续行已按上一 PN 继承但本批无样本（32 回实测 0 例），换书需复验。
5. registry 的合并称谓（`◆ 东西两厂（东厂+西厂合称）`）不会与字面 canonical 对齐，
   需别名表承接（本批 `东西厂` 已命中 contextual，故 registry 仅 1 条“未使用”）。

**N3**
1. **词表仅 165 条且全部 status=待审**：词表外 distinct surface 2,210 个、覆盖 5,367 处，
   `info` 量大是“候选召回器”定位的预期结果（04f §5.4），不是标注缺陷；补表后才宜收紧。
2. **白名单域冲突按 error**：词表主域为单词，语料中的合法多义（`刺` 词表 ⊞ 本批 7 处标 ⊠、
   `杀` 词表 ⊠ 本批 17 处标 ⊞）也会报 error；58 条中 26 条带消歧说明、32 条未带，
   需人工裁决“改标回主域”还是“补 `senses` 分型”。
3. `W-MULTIDOMAIN` 的“少数派域”由**语料自身**分布推得（词表未登记多域），属启发式提醒，
   不等于标注错误；换书后分布会变。
4. 域混淆启发式是**同句子串关键词**匹配，存在误报/漏报，且“已消歧（有 `|` 说明）”一律
   不再提示；建议类不阻断。
5. 联动缺失只查**同句**实体（按 。！？； 切分），跨句/代词指代不追（04f §4.2：联动是候选生成器）。
6. 分回密度按“回”聚合；04f §6.1“每段 1-6 处”由 S-PARA-DENSITY 单独提示，两套口径互补。
7. 阈值 0.5/3.0 以本批 32 回分位校准；换书需按新书重校（常量已集中并注释依据）。

---

## 六、后续建议

1. **登记层补录**：C24 `unregistered` 301 条（Top：慕容冲/白石道人/公孙大娘/金独异…）
   可直接转 E-build 登记任务；`alias_mapped` 9 条应回填 registry 别名表。
2. **词表扩词**：以 N3 `infos.new_word_candidates` Top 200 为候选池，按 04f §5.2/§5.4
   三档运营法逐条核定；对“杀/刺/还/斩/断/交换”等多义单字补 `senses` 分型，可消掉
   58 条 E-WL-DOMAIN 中的大部分。
3. **接入完成门**：建议把 `validate_verb_tagging_wuxia.py --strict` 挂入
   `pipeline_wuxia.py check`（当前 check 五门 lint；N3 可作为动词层门），但需先清零/降级
   本批 60 条 error，或将其限定为“新增错误”棘轮。
4. **C24 排期**：docs/17 §八曾记 C24 未列入波次；本次已随 P2 提前交付，建议回写
   docs/17 §2.2 与波次表（本任务不改 docs/17，交由 Lead 裁决）。
5. **N3 规则库化**：域混淆/联动规则已表驱动（`RULE_*`/`LINK_RULES`），后续可按
   04f §八错误模式库追加规则编号，不需要改主流程。

---

## 七、Lead 校准与集成（2026-11-04 22:20–22:35）

| 项 | 改动 | 复跑结果 |
|---|---|---|
| E-WL-DOMAIN 级别 | 词表仅 165 条且每词单主域，58 条"域冲突"多为合法多义；默认降级为 **W-WL-DOMAIN（warning）**，新增 `--wordlist-strict` 恢复 error，并在 RULE_SPEC 注明"补 senses 分型前降级" | 全书：**error 2（仅 E-PUNCT）/ warning 322（+58）/ suggestion 163 / info 2,210**；`--strict` 在 019 两条标点修复前 exit 1，修复后应 exit 0 |
| 子集输出覆盖 bug | 两脚本 `--chapters` 子集原先写同名文件，会覆盖全书报告；已加范围后缀（如 `白发魔女传_001-001.json`） | 子集与全量报告并存 |
| 管线注册 | `pipeline_wuxia.py` 新增机械阶段 **`concordance`**（C24）与 **`verb-validate`**（N3），并登记 5 个 P2 辅助工具 + accept_batch | `pipeline_wuxia.py 白发魔女传 concordance --chapter N` / `verb-validate --chapter N` 实跑 exit 0 |
| E-PUNCT 2 条 | 019[1] `⟦■，四面了望⟧`、019[15] `⟦⊟，射上⟧` 属金标准内标点误入 token；由 task-9 修复（标点外置、strip 断言） | 修复后预期 error 0 |

**结论**：N3 的"error"现仅剩真实结构类问题；词表多义类转入 warning，避免把词表缺口误判成语料错误。集成后 N3 可作为 P2/P3 的动词层体检阶段（暂不入门禁，等 019 标点修完且多域 warning 收敛后再评估）。

---

## 八、P2-C 健壮性修复（task-12，2026-11-05）

> 说明：本报告 §一/§二 为 task-7 当时口径（N3 error 60 等）；N3 级别经 §七 Lead 校准、语料经 task-9 验收修复后，**现行数字以本节为准**。

### 8.1 修复项（4 文件，7 处；含 Lead 补充的 2 处 JSON 顶层结构容错）

| # | 文件/函数 | 原问题 | 修复 |
|---|---|---|---|
| 1 | `validate_verb_tagging_wuxia.py:scan_structure` | 错配（closing 与栈顶不同层）且栈内找不到同层开括号时直接 `continue`，残留开括号会把后续闭合/文本并入假 span，产生级联误报 | `idx is None` 分支先对栈内全部未闭合项记 `unclosed`，再 `stack.clear()`；后续文本重新从干净栈开始 |
| 2 | `validate_verb_tagging_wuxia.py:parse_chapters` | `1-abc`/`a-b`/空段等输入抛裸 `ValueError`，pipeline 透传时不可读 | 统一友好 `SystemExit`：空段、非数字、`1-abc`、`a-b`、`1-`、`-3`、倒置区间（8-5）、0/负数、`1.5` 均给一行可操作提示 |
| 3 | `build_entity_concordance.py:parse_chapters` | 同上 | 同款友好 `SystemExit`（错误文案一致，便于两阶段共用） |
| 4 | `build_entity_concordance.py:load_registry` | `entities.json` JSON 解析失败直接抛 `JSONDecodeError`，C24 整体中断 | `try/except json.JSONDecodeError` → 打印警告、返回空 registry（meta.error 记录原因）；脚本继续，MD/JSON 注明"按空登记表输出、@◆& 全部 unregistered" |
| 5 | `pipeline_wuxia.py:run_stage` | `subprocess.run` 在脚本缺失/解释器不可用时抛 `FileNotFoundError/OSError`，check 五门在第一项即中断 | `try/except (FileNotFoundError, OSError)` → 打印 `[stage] 子进程启动失败: ...` 并返回 `-1`；`stage_check` 将 -1 计入失败项，5 项逐项记录、不短路，最后汇总 exit 1 |
| 6 | `validate_verb_tagging_wuxia.py:load_wordlist`（Lead 补充） | 词表 JSON 顶层为 list 时 `data.get("items")` → `AttributeError` | `isinstance(data, list)` → 直接取 `items=data`、`meta={}`；顶层非 dict/list 时打印警告并按空词表继续 |
| 7 | `build_entity_concordance.py:load_registry`（Lead 补充） | 登记 JSON 顶层为 list（或 `entities` 非 list / 顶层标量）时 `data.get("entities")` 或遍历 → `AttributeError` | list → `entries=data`；顶层非 dict/list 或 `entities` 非 list → 警告 + 空表（`meta.error` 记录 `unexpected top-level …` / `entities is not a list`），脚本继续 |

### 8.2 自测（全部实测，独立进程）

| 测试 | 结果 |
|---|---|
| N3 结构栈 + parse_chapters | **PASS 18 / FAIL 0** |
| C24 parse_chapters + 坏 registry 容错（含 main 端到端） | **PASS 17 / FAIL 0** |
| pipeline run_stage 异常 + stage_check 不短路 | **PASS 4 / FAIL 0** |
| N3 `load_wordlist` 顶层 list / 标量 JSON 容错（Lead 补充） | **PASS 4 / FAIL 0** |
| C24 `load_registry` 顶层 list / 标量 / `entities` 非 list 容错（Lead 补充） | **PASS 5 / FAIL 0** |

- **脏样本**：`⟦⊞甲〗⟧` → `issues=['mismatch','unclosed','unmatched_close']`、`spans=[]`（修复前会把 `⟦⊞甲〗⟧` 当作一个 verb span）；`正文⟦⊞甲〗⟧后文〖@乙〗。` → 清栈后 `〖@乙〗` 正常闭合，无级联。
- **坏 registry**：`load_registry` 返回空 canonical/alias + `meta.error=JSONDecodeError…`；`main()` 仍 exit 0，输出 JSON 带 `registry.meta.error`、`@◆&` 全部 unregistered（001 回 40/40）、MD 注明"登记表解析失败"。
- **pipeline 异常**：模拟 `FileNotFoundError` / `OSError` 时 `run_stage` 均返回 **-1** 且打印"子进程启动失败"；模拟 5 项全失败时 `stage_check` 输出 `lint-pn=-1 integrity=-1 symbol-lint=-1 md-lint=-1 fence-format=-1` 后 exit 1（五门全跑、不短路）。
- **CLI 非法参数**：`--chapters 1-abc` / `a-b` 两脚本均 exit 1 + 友好提示（非 Python traceback）。
- **JSON 顶层结构容错（Lead 补充）**：N3 词表顶层为 list 时正常读取 2 条（`surface_count=2`、`meta={}`、`by_surface` 正常）；顶层标量时警告 + 空词表。C24 登记表顶层为 list 时正常建立 2 条 canonical/alias、`meta={}`；顶层标量/`entities` 非 list 时警告 + 空表并写 `meta.error`，不 AttributeError。

### 8.3 回归复跑

| 命令/项 | 结果 |
|---|---|
| `validate_verb_tagging_wuxia.py --book 白发魔女传` | **error 0 / warning 317 / suggestion 162 / info 2,204**；verbs 5,836；基线 1.431 V/100字（与 task-12 期望一致） |
| `validate_verb_tagging_wuxia.py --book 白发魔女传 --chapters 1-2` | exit 0；2 回 / 192 verbs / error 0 / warning 1 / suggestion 3；子集产物 `白发魔女传_001-002.*` |
| `build_entity_concordance.py --book 白发魔女传` | exit 0；**4,988 实体 / 32,716 次**；registry 70 条命中 69、unregistered 301（见下方差异说明） |
| `pipeline_wuxia.py 白发魔女传 concordance --chapter 1` | exit 0；001 回 653 组 / 1,831 次，写 `白发魔女传_001-001.json`（子集后缀，不覆盖全书） |
| `pipeline_wuxia.py 白发魔女传 verb-validate --chapter 1` | exit 0；1 回 / 130 verbs / error 0，写 `白发魔女传_001-001.*` |
| `python -m py_compile`（3 脚本） | exit 0 |
| tagged 只读 | 32 个 `*.tagged.md` sha256 跑前/跑后逐一比对一致（零改动） |

**C24 4,988/32,716 vs 任务书 4,992/32,731 的差异说明（不是脚本回归）**：
- 4,992/32,731 是 **task-9 之前**的基线；用 task-9 备份重建旧语料实跑 C24 = **4,992/32,731**（已实测确认）。
- task-9 按验收裁决删除了 **15 个实体 token**（`$` 13 个、`%` 1 个、`=` 1 个）；对应 C24 减少 **4 组**（`$口`、`$张`、`$把`、`%老`）与 **15 次**，与当前值差值逐项吻合。
- 因此 **C24 脚本行为未变**，当前值 4,988/32,716 为 task-9 修复后的正确基线。

### 8.4 结论

task-12 的 7 处健壮性修复全部实测通过：N3 结构扫描不再因单个错配产生级联假 span、两脚本非法参数给出可读 `SystemExit`、C24 登记表损坏/结构异常可降级继续、pipeline 子进程启动失败不再中断五门 check、词表与登记表顶层 list 不再 AttributeError。回归复跑 N3/C24/pipeline 单回阶段均 exit 0；tagged 零改动。
