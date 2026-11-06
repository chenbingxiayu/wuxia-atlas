# C18 + C19 + C20 实现报告（P2 实体层：别名补标扫描 / 单字人名推断 / 实体边界体检）

- 执行：scan-builder（task-6，2026-11-04；task-11 P2-B 修订 2026-11-05）
- 移植源（只读）：`shiji-kb/scripts/{scan_untagged_aliases,infer_single_char_names,detect_entity_boundary_errors}.py`
- 权威依据：docs/17 §2.2（C18/C19/C20 三行）、docs/05 §2.8、`skills/SKILL_01g`（符号/负规则/管道）、
  `skills/SKILL_03a`（v1.8 管道纪律）、`skills/SKILL_跨书治理`（别名与双层 canonical 概念）、
  docs/46 §二 P2 批量（C20 selftest hermetic / C18 apply 长词保护 / 加载健壮性）
- 本轮纪律：**不写 `tagged/`**（默认只出建议 TSV 与报告）；`--apply` 代码已实现但未执行；不 commit、不调 LLM。
- 数据：`registry/entities.json`（70 条）、`wordlists/stopwords.json`（18 条泛称）、`tagged/白发魔女传/`（32 回）。

---

## 一、交付物

| 类型 | 路径 | 说明 |
|---|---|---|
| 脚本 | `scripts/scan_untagged_aliases.py` | C18 别名补标扫描（建议 TSV + 汇总报告，`--apply` 可选） |
| 脚本 | `scripts/infer_single_char_names.py` | C19 单字人名映射体检与推断（报告，`--apply` 可选） |
| 脚本 | `scripts/detect_entity_boundary_errors.py` | C20 实体边界体检（8 模式报告 + 可选建议 TSV） |
| 报告 | `logs/aliases/白发魔女传_alias_scan.md` / `.json` | C18 汇总（32 回全量） |
| 建议 TSV | `registry/patches/<回>_aliases.tsv` | C18：23 个（101 条建议），C7 契约兼容 |
| 报告 | `logs/single_char_names/白发魔女传.md` / `.json` | C19 映射/歧义/无匹配/告警 |
| 报告 | `logs/boundary/白发魔女传.md` / `.json` | C20 8 类计数 + 逐类样例 + 定位 + 自检 |
| 建议 TSV | `registry/patches/<回>_boundary_fix.tsv` | C20：10 个（人工审查用，非 C7 插入契约） |
| 验证证据 | `logs/_p2_c18c20/tagged_before.txt` / `tagged_after.txt` | 32 回 tagged SHA256 前后对照（零改动） |
| 本报告 | `docs/_p2/C18-C20-report.md` | — |

运行方式：

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/scan_untagged_aliases.py --book 白发魔女传 --all
python scripts/scan_untagged_aliases.py --selftest
python scripts/infer_single_char_names.py --book 白发魔女传
python scripts/detect_entity_boundary_errors.py --book 白发魔女传 --all --tsv
python scripts/detect_entity_boundary_errors.py --selftest
```

---

## 二、共同契约落实

1. **路径经 `config`**：tagged 用 `config.tagged_path(book, no)`，输出/词表/registry 用 `config.DIR_*`，
   不出现相对 cwd 的 `Path('chapter_md')` 式硬编码（shiji 技术债，docs/05 §1.2-1）。
2. **符号统一走 `symbols`**：所有令牌识别 = `symbols.TOKEN_RE`，令牌解析 = `symbols.parse_token`，
   插入 = `symbols.BRACKETS["entity"]`，围栏 = `symbols.FENCE_OPEN_RE/FENCE_CLOSE_RE/FENCE_ENTITY_POLICY`，
   实体类型 = `symbols.ENTITIES`（15 类）；三脚本内**无本地实体符号字符类**（仅 P7 的道号判断等使用普通字符串常量）。
3. **`masker` 复用**：C18 用 `masker.build_matcher`（最长优先、不重叠）+ `masker.find_candidates`；
   C19 用 masker 在剥标正文上做候选名频次；C20 用 masker 判断命中片段是否被 WN 白名单覆盖。
4. **TSV 兼容 C7**：列 = `章节 / 全名 / 省称·词 / 位置 / 框架类型 / 匹配模式 / 上下文 / 实体类型`
   （前 7 列必需，第 3 列 = 别名词、第 8 列 = 中文实体类型）。实测 `apply_annotation_patches.load_tsv`
   解析 23 个 TSV 共 101 行、`--dry-run` 正常打印插入位置（见 §六 验证 V4）。
5. **不写 tagged**：默认流程只写 `registry/patches/` 与 `logs/`；`--apply` 需显式开启，且实现为
   「备份 → 插入 → 剥标断言 → 令牌数/逐词断言 → 失败回滚」。
   **2026-11-05 P1 修复**：apply 改为按建议 TSV 的原文 `位置` 精确插入，并跳过
   `build_masked` 保护区（令牌/围栏块/标题行/回目）；外部 TSV 缺 pos 时退回"同词全插"但仍过滤保护区；
   新增 `--selftest`（围栏/标题零插入 + 正文零改动）。详见 docs/46 §七。
   **2026-11-05 P2-B 修复**：无 pos 回退模式增加**长词保护**——`do_apply(..., known_words=set(word_map))`
   传入 `_apply_word`，位置处若存在更长的已知词以该词为前缀则跳过（`武当` 不会切进 `武当派`）；
   `--selftest` 增补该断言（known 含 `武当派` 时不得产出 `〖◆武当〗派`）。
6. **健壮性（P2-B）**：三脚本 JSON 载入统一兼容"顶层 list"（共 4 处：
   `C18.load_stopwords`、`C19.load_canonical_single`、`C20.load_wn`×2）；
   `C19.parse_chapters` 对 `1-abc`/`abc`/`3-1` 等非法输入给友好 `SystemExit`（不抛裸 ValueError）。

---

## 三、C18 已知实体别名补标扫描

### 3.1 设计决策

- **实体索引重建**：`registry/entities.json` → `{词: (canonical, type_code)}`，词 = canonical + aliases；
  `aliases` 尾部括号说明（如「蒙面少女（005 旧称）」「金刚手（称谓前缀）」）剥注释后参与匹配；
  canonical 里的说明（「东西两厂（东厂+西厂合称）」）同样剥括号。
- **contextual 不入索引**：`卓兄/卓公子/练小姐/姓岳的` 等 31 条语境/关系称谓按 01g 负规则二不补标人物，
  避免制造「礼貌称呼→实体」噪声；registry 校验段落中留痕说明。
- **歧义不猜**：同一 alias 指向多个 canonical 时整体从索引移除并告警（本语料 registry 无此情况）。
- **只扫未标注正文**：`symbols.TOKEN_RE` 命中区间、围栏块（词/诗/歌/对联/回末对/回末/书信/告示/口诀/说书）、
  `#` 回目行全部等长掩码为 `\ufffd`（保偏移），回末套语随围栏一并跳过。
- **负规则**：`wordlists/stopwords.json` 泛称黑名单跳过（并在报告给出被拦截的裸文出现量 top10）；
  纯数词跳过；单字词默认跳过（`--allow-single` 放开）。
- **建议分级**：registry 中带「（旧称）」注释的描述性别名（蒙面少女/中年美妇/清风山老怪）命中后单独列
  「需人工裁定」段（01g 负规则一：描述性代称不标）。
- **`--apply` 管道纪律**：@ 类型写 `〖@别称|规范名〗`（v1.8 允许），非 @ 类型只落显示串
  （如 `〖◆武当〗`，因 `normalize_pipes` 会摘除 ◆ pipe）；C7 的纯插入路径不写管道，故本脚本自带 apply。
- **apply 长词保护（P2-B）**：无 pos 的外部 TSV 回退"同词全插"时，先由 `do_apply` 把
  `set(word_map)` 作为 `known_words` 传入；若某位置存在更长的已知词以该词为前缀
  （known 含「武当派」时的「武当」）且 `text.startswith(longer, i)`，跳过该位置，
  避免产出 `〖◆武当〗派`。pos 精确模式不受影响。`--selftest` 同时断言
  「pos 模式 1 处 / 全插 2 处 / known 保护后全插 1 处且无 `〖◆武当〗派` / 围栏标题零插入」。

### 3.2 实跑统计（32 回全书）

| 指标 | 值 |
|---|---|
| registry 实体 | 70（人物 52 / 组织 15 / 家族世系 3；approved 61 / proposed 9） |
| 可匹配词条（正名+别名去重） | 97（剥括号说明 4 条） |
| 扫描回数 | 32 |
| 有命中回数 | 23（001/009/011/014/015/016/021/022/024 共 9 回为 0） |
| 建议总数 | 101 |
| 命中词种 | 22 |
| 输出 TSV | 23 个 `<回>_aliases.tsv` |
| 跨实体歧义 | 0 |

命中 Top：玉罗刹→练霓裳 17、武当→武当派 17、蒙面少女→铁珊瑚 12、珊瑚→铁珊瑚 11、满洲 11、
铁家 9、朝廷 3、嵩阳→嵩阳派 3、中年美妇→穆九娘 2、熊廷弼 2；其中 020–032（机器初稿）以裸文
`玉罗刹/武当/满洲` 为主，说明「机器初稿回」是别名补标的主要受益区。

### 3.3 抽样 5 条（逐条原位复核：位置处原文逐字匹配、且未被令牌覆盖）

| 回 | 词 | 全名 | 类型 | 位置 | 原文上下文（TSV 原值，`↵`=换行） |
|---|---|---|---|---|---|
| 002 | 白敏 | 白敏 | 人物 | 4918 | 心想：这傻小子名叫“白敏”，却一点也不机敏。 |
| 002 | 东西厂 | 东西两厂 | 组织 | 11818 | 〗”〖$三个〗机关，东西厂由〖;太监〗掌握，“ |
| 003 | 朝廷 | 朝廷 | 组织 | 3442 | 。其中有督抚大员，有朝廷重臣，也有武林高手。 |
| 003 | 明太祖 | 朱元璋 | 人物 | 5842 | 〖•酒〗看技。”原来明太祖〖@朱元璋〗立国之后 |
| 003 | 明神宗 | 朱翊钧 | 人物 | 6012 | 〗所说的〖^祖训〗。明神宗〖@朱翊钧〗虽然宠爱 |

（5 条均通过 `text[pos:pos+len]==word` 且掩码位非 `\ufffd` 的自动断言；tsv 内「位置」为文件字符偏移。）

---

## 四、C19 单字人名映射体检与推断

### 4.1 设计决策

- **CANONICAL_SINGLE 清空+可配置**：shiji 的远古人名（舜/尧/禹/鲧/桀/纣/汤/契/稷/益/羿…）全部删除；
  默认空集，若存在 `wordlists/single_char_canonical.json` 则读入（`items[].surface` 或字符串列表）。
  该词表本轮**未创建**（不在本任务写作用域，避免与词表批次冲突），报告明确标注「未建（默认空集）」。
- **语料与章节**：经 config 读 `tagged/<书>/NNN.tagged.md`；`--chapters` 支持 `all` / `1-32` / `005,008`。
- **映射证据两类**：
  1. 已挂管道单字（`〖@云|云燕平〗`）：体检管道规范名是否 2 字以上、是否在同回多字人名中出现、
     是否可解析到 registry；
  2. 未挂管道单字：同回多字人名（含管道规范名）中「**末字**」匹配者为候选（2026-11-05 P1 修复：
     移除首字匹配——同回只有"李寻欢"时单字"李"会被误映射；现语料新推断仍为 0，属 latent 风险）；**唯一候选才判映射**，
     多候选按「令牌频次 + 剥标正文裸文频次」排序取最高并列入歧义（不自动应用）。
- **跨回体检**：同一单字在不同回指向不同全名 → 单列告警（禁止全书统一替换）。
- **`--apply`**：只处理唯一新推断，`〖@X〗 → 〖@X|全名〗`；备份 + 剥标断言 + 令牌数断言 + 逐回校验。
- **健壮性（P2-B）**：`--chapters` 非法输入（`1-abc` / `abc` / `3-1`）给友好 `SystemExit`
  （`[ERROR] --chapters 解析失败：…（格式：all / 1-32 / 005,006；回号须为正整数）`），
  不抛裸 `ValueError`；JSON 载入兼容顶层 list。

### 4.2 实跑统计（32 回）

| 指标 | 值 |
|---|---|
| 单字 `@` 令牌总数 | 11（分布：005×6、008×2、011×1、017×2） |
| 映射条目 | 10（按 token；去重 (回,单字) 8 组）：管道已有 10 / **新推断 0** |
| 歧义 | 0（末字匹配下 011 回单字 `李` 无候选；首字匹配已按 P1 修复移除） |
| 无匹配 | 1（011 回 `李`：同回多字名李可灼/李选侍均非「末字=李」，无法据末字唯一映射） |
| 跨回同字异人 | `金`：005 金千岩 / 017 金戈（已告警） |
| registry 未收规范名 | 3 条：008 李天扬、017 金戈（金/戈两处） |

结论：本语料 020–032 之前的人工回已把单字人名基本挂清管道（10/11 已映射），C19 的主要价值转为
**体检器**——发现「金」跨回异人、`李天扬` 与 registry `李钦差` 口径冲突、`金戈` 未登记三处风险；
011 回单字 `李` 属「姓」而非「名末字」，末字规则下进入无匹配（符合 P1 修复后的保守语义，不猜）。

### 4.3 抽样 3 条映射人工核对（原文逐条核）

| 回 | 单字 token | 全名 | 原文证据 | registry |
|---|---|---|---|---|
| 005 | `〖@云|云燕平〗` | 云燕平 | 同回另有 36 次 `云燕平` 令牌；`〖@卓一航〗知道〖@云|云燕平〗、〖@金|金千岩〗二人…` | E0040 ✓ |
| 008 | `〖@周|周钦差〗` | 周钦差 | `明明是〖@周|周钦差〗〖@李|李天扬〗两钦差之事`；周/李对应两位钦差 | E0048 ✓ |
| 017 | `〖@戈|金戈〗` | 金戈 | `自称姓〖@金|金戈〗名〖@戈|金戈〗`——姓金名戈，金/戈同指金戈 | **未收录（告警）** |

---

## 五、C20 实体边界体检（8 模式）

### 5.1 8 类模式与武侠化触发词

| 模式 | 判定规则（武侠版） | 严重度 |
|---|---|---|
| P1 实体跨动词吞入 | 实体令牌显示串含「说道/喝道/问道/笑道/叫道/骂道/怒道/沉声道/厉声道/朗声道/走了/来了/出来…」等；未挂管道的「姓X名Y」叙述句 | error |
| P2 实体后粘语气/动词 | `@` 令牌尾字 ∈ `道说喝问了着` | error |
| P3 介词误入 | 实体令牌尾字 ∈ `于在向从往到自`，或含「在…中/向…外」介词结构（「于」开头视为姓氏豁免） | warning |
| P4 官职/身份拆分错误 | 相邻同码令牌中，一个显示串是另一者的 canonical/alias，或拼接后命中 registry 名 | error |
| P5 单字实体边界 | 人物单字令牌后接裸文可补全 registry 名（如 `〖@卓〗仲廉`）→ error；单字无管道 → warning | error/warning |
| P6 括号内标点 | 令牌显示串（管道前）含 `，。、；：！？`：实体/动词层 error，修辞层固定表达 info | error/info |
| P7 实体覆盖人名+称谓 | `@` 令牌未挂管道且 = 名号 + 称谓后缀（大人/夫人/师叔/师兄/酋长…）或称谓前缀+名 | warning |
| P8 回末套语误标 | 按 `symbols.FENCE_ENTITY_POLICY`：回末=全不标；词/诗/歌/对联/回末对=仅实指；口诀=仅技术名；其他围栏动词不标；另查回末套语行 | error/warning/info |

**WN 白名单（按武侠职衔/门派/器物重建）** = 静态武侠词表 94 条（职衔/门派/道路/武功器物）+
registry 正名别名 97 条 + `rhetoric.json` 固定表达 49 条 + stopwords 18 条，经 masker 最长匹配整体豁免。
佛道名号构词（道人/道长/禅师/法师/喇嘛/居士）在 P7 单独豁免（紫阳道长/白石道人/晦明禅师等属名号）。

### 5.2 实跑统计（32 回，2026-11-05 复跑）

| 模式 | 名称 | 计数 | error | warning | info |
|---|---|---|---|---|---|
| P1 | 实体跨动词吞入 | 0 | 0 | 0 | 0 |
| P2 | 实体后粘语气/动词 | 1 | 1 | 0 | 0 |
| P3 | 介词误入 | 0 | 0 | 0 | 0 |
| P4 | 官职/身份拆分错误 | 1 | 1 | 0 | 0 |
| P5 | 单字实体边界 | 1 | 0 | 1 | 0 |
| P6 | 括号内标点 | 4 | 0 | 0 | 4 |
| P7 | 实体覆盖人名+称谓 | 9 | 0 | 9 | 0 |
| P8 | 回末套语误标 | 0 | 0 | 0 | 0 |
| **合计** | — | **16** | **2** | **10** | **4** |

命中 10 回（003/004/005/010/011/013/016/026/028/030），输出 10 个 `<回>_boundary_fix.tsv`。
P1/P3 为 0：语料机械结构较干净（无令牌内动词/介词粘连），规则由 `--selftest` 合成语料证明可触发。

**19 → 16 的说明（非检测回归，属语料被修复）**：2026-11-04 22:20 的验收处置批次（docs/45；非本任务）
改了 `tagged/019`、`tagged/030`，恰好消掉了本报告 11-04 首跑里的 3 条命中，且与 docs/45 的处置记录一致：
- `019`：N3 E-PUNCT 2 处标点外置（docs/45 §五），`⟦■，四面了望⟧` / `⟦⊟，射上⟧` →
  已修为 `⟦■四面了望⟧` / `⟦⊟射上⟧`（P6 error 2 → 0）；
- `030`：`fix_manifest.json` 记录 030[69] `〖=沙漠〗 → 沙漠`（delete，理由「回末对限实指；
  “沙漠”为泛指/修辞，摘除」），P8 info 1 → 0。

为证明检测器本身无回归，用**当前语料在内存中回填旧形态**复跑（不写文件）：
`019` 复得 P6×2 error、`030` 复得 P8×1 info，合计 **16 + 3 = 19 条**，与原首跑逐类一致。
即：19 条的旧口径 = 修复前语料；16 条 = 当前语料。两轮结论均留档，后续以当前语料 16 条为准。

### 5.3 抽样 5 条（当前语料，已核对原文）

| 定位 | 模式 | 命中 | 原文/上下文 | 建议 |
|---|---|---|---|---|
| 011:87（PN [43]） | P2 | `〖@白石贼道|白石道人〗` | 临行喝道："白石贼道，你三日之内若不回山…" | 尾字「道」属贬称「贼道」，不应并入人名；改 `〖@白石〗贼道` 或挂管道 `〖@白石贼道\|白石道人〗` 前先按 01g 裁定 |
| 003:79（PN [39]） | P4 | `〖@玉罗刹|练霓裳〗〖@练霓裳〗` | 看官们大约都知道这位少女就是〖@玉罗刹|练霓裳〗〖@练霓裳〗了 | 同一实体被拆成两令牌，合并/去重 |
| 003:7（PN [3]） | P6 | `〘※说时迟、那时快〙` | 却不料，〘※说时迟、那时快〙，四名东厂头目… | 修辞固定表达内标点按 02j 允许，计 info 供复核 |
| 010:93（PN [46]） | P7 | `〖@客氏夫人〗` | 皇太孙的乳母叫客氏夫人 | 「名号+称谓」整体入令牌，应 `〖@客氏〗夫人` 或挂管道 |
| 030:71（PN [35]） | P7 | `〖@哈萨克酋长〗` | 来到哈萨克酋长眼前，笑道… | 族群+职衔整体入人物令牌，应按实体类型拆分 |

（注：11-04 首跑样例中的 `019` P6 两条与 `030` P8 一条已在上一轮语料修复中消除，上表替换为当前仍存的样例。）

### 5.4 检测器自检（`--selftest`，**hermetic：内置 mock registry/WN**）

| 模式 | 合成语料命中 | 判定 |
|---|---|---|
| P1 | 1 | PASS |
| P2 | 2 | PASS |
| P3 | 1 | PASS |
| P4 | 1 | PASS |
| P5 | 1 | PASS |
| P6 | 1 | PASS |
| P7 | 2 | PASS |
| P8 | 1 | PASS |

`SELFTEST PASS`（8/8）。自检覆盖：`〖@张三说道〗`（P1）、`〖@李四道〗`（P2）、`〖@王五在〗`（P3）、
`〖@玉罗刹〗〖@练霓裳〗`（P4）、`〖@卓〗仲廉`（P5）、`〖=京城，〗`（P6）、`〖@青蓑师叔〗`（P7）、
回末对围栏内 `〖=沙漠〗`（P8）。

**P2-B hermetic 改造**：`selftest()` 不再接收真实 `load_wn()/load_registry()` 结果，改为内置
`MOCK_REGISTRY = {canon:{卓仲廉,练霓裳}, alias2canon:{玉罗刹→练霓裳}}` 与
`MOCK_WN = WUXIA_WN + mock 名`；`--selftest` 分支在 `load_wn()/load_registry()` **之前**返回，
因此无 registry/词表文件也能 8/8 PASS。实测：把 `REGISTRY_PATH/RHETORIC_PATH/STOPWORDS_PATH`
全部指向不存在路径后跑 `--selftest`，仍 8/8 PASS（见 §6 V12）。报告内嵌的自检表同样为 mock 结果，
主流程（`--chapter/--all`）仍用真实 `load_wn()/load_registry()`。

---

## 六、验证结果

| 编号 | 验证项 | 命令 | 结果 |
|---|---|---|---|
| V1 | 语法编译 | `python -m py_compile` 三脚本 | exit 0 |
| V2 | 三脚本 32 回全书 dry-run/只读跑 | 见 §一 命令 | 全部不崩；C18 101 条、C19 10 条映射、C20 **16 条**（当前语料；旧形态 19 条见 §5.2） |
| V3 | C18 产物覆盖 | 23 个 `_aliases.tsv` + 覆盖 32 回的汇总报告/JSON | ✅ |
| V4 | C7 TSV 契约 | `apply_annotation_patches.py --file registry/patches/003_aliases.tsv --dry-run`；并以 `load_tsv` 解析全部 23 个 TSV | 101 行全部解析成功，dry-run 打印插入位置 ✅ |
| V5 | C19 抽样 3 条 | 见 §4.3（原文+registry 双证据） | ✅（其中 1 条暴露 registry 漏登） |
| V6 | C20 8 类计数 + 抽样 5 条 | 见 §5.2/§5.3 | ✅（8 类计数 + 当前 5 条样例） |
| V7 | C20 自检 | `--selftest`（**内置 mock registry/WN**） | 8/8 PASS |
| V8 | C20 `--strict` 语义 | `--all --strict` | 当前语料 2 条 error → exit 1（符合约定；常规跑 exit 0） |
| V9 | CLI 分支 | `--chapter/--all/--types/--min-freq/--allow-single/--chapters/--dry-run/--tsv` | 逐项跑通 |
| V10 | **tagged 零改动（本轮）** | 32 个 `*.tagged.md` SHA256 前后对照（`logs/_p2_c18c20/tagged_before.txt` vs `_after.txt`） | **PASS：32/32 完全一致**。注：`019/030` 在 11-04 22:20 被验收处置批次（docs/45）修复（非本任务，mtime 证据），本轮基线已含该修复 |
| V11 | registry/词表未改 | 只读加载，无写入 | ✅ |
| V12 | **C20 selftest hermetic** | 把 `REGISTRY_PATH/RHETORIC_PATH/STOPWORDS_PATH` 全部 monkeypatch 为不存在路径后跑 `--selftest` | 8/8 PASS、exit 0（不依赖真实 registry/词表） |
| V13 | **C18 selftest（P2-B 长词保护）** | `python scripts/scan_untagged_aliases.py --selftest` | PASS：pos 1 处 / 全插 2 处 / known 保护后全插 1 处且无 `〖◆武当〗派` / 围栏标题零插入 |
| V14 | **C18 do_apply 长词保护（集成）** | 临时 tagged 文件 + monkeypatch `config.tagged_path`/`BACKUP_ROOT`，无 pos TSV 对「武当派与武当」执行 `do_apply(known_words={"武当派","武当"})` | 插入 1 处：`武当派与〖◆武当〗同现`，无 `〖◆武当〗派`；`strip_markup` 前后一致；回滚 0 |
| V15 | **JSON 顶层 list 兼容（4 处）** | 造 list 形态 JSON 分别喂 `C18.load_stopwords`、`C19.load_canonical_single`、`C20.load_wn`（rhetoric/stopwords 两处 monkeypatch） | 全部正常返回（stopwords 2 条 / canonical 2 条 / WN 计数正确，无 AttributeError） |
| V16 | **C19 `--chapters` 友好报错** | `--chapters 1-abc`、`abc`、`3-1` | 均 exit 1 且只打印 `[ERROR] --chapters 解析失败：…（格式：all / 1-32 / 005,006；回号须为正整数）`，无裸 Traceback |
| V17 | C20 19 条旧形态等价性 | 内存回填 019/030 旧片段后复跑（不写文件） | 16 + 3 = 19：019 复得 P6×2、030 复得 P8×1，与原首跑逐类一致 → 检测器无回归 |

**P2-B 修复清单（2026-11-05，task-11）**

| # | 文件 | 修复 | 证据 |
|---|---|---|---|
| 1 | `detect_entity_boundary_errors.py` | selftest 改 hermetic：内置 `MOCK_REGISTRY`/`MOCK_WN`，`--selftest` 在真实加载前返回 | V12：三路径指向不存在文件仍 8/8 PASS |
| 2 | `scan_untagged_aliases.py` | `do_apply` 传 `known_words=set(word_map)`；无 pos 回退跳过"更长已知词前缀"位置 | V13/V14：无 `〖◆武当〗派`，集成插入 1 处 |
| 3 | `infer_single_char_names.py` | `parse_chapters` 友好 SystemExit | V16：`1-abc`/`abc`/`3-1` 均友好报错 |
| 4 | 三脚本（C18/C19/C20×2） | JSON 顶层 list 兼容（4 处 `items` 载入） | V15：list 形态全部正常 |

`--apply` 未执行（本轮纪律）；其代码路径的插入/断言逻辑已用内存字符串单测 + 临时文件集成测试验证：
- C18：`玉罗刹 → 〖@玉罗刹|练霓裳〗`、`武当 → 〖◆武当〗`，`symbols.strip_markup` 前后相等；
  无 pos 回退时 known_words 保护长词（V14）；
- C19：唯一新推断才会替换 `〖@X〗`，替换后剥标不变、令牌数不变。

---

## 七、已知局限与后续建议

1. **C18 覆盖面受 registry 约束**：只补「已登记实体」的正名/别名，不做新实体发现（C16/词表与 C24 职责）。
   registry 仅 70 条，`白石道人/晦明禅师/慕容冲` 等高频人物未登记 → C18 不会建议补标，需先补 registry。
2. **C18 词形歧义需人工复核**：`珊瑚`（普通名词/人名）、`满洲`（族群/政权）、`朝廷`（泛称/组织）等
   建议应用前人工抽检；描述性旧称别名（蒙面少女×12、中年美妇×2、清风山老怪×0）已单列「需人工裁定」，
   与 01g 负规则一存在张力。
3. **C18 建议位置是「文件字符偏移」**：与 C7 的 `pos` 语义一致但 C7 实际用上下文中文定位；跨行上下文
   经 `↵` 编码后可能定位不到唯一位置，应用时以「同词全插 + 已标注保护」语义为准。
4. **C19 推断面小**：全语料仅 11 个单字 `@` 令牌（10 个已挂管道），唯一新推断 0；若后续新标注回出现
   更多单字简称，脚本即可直接产出映射。`CANONICAL_SINGLE` 词表按约定未建，武侠单字名号（如需）应
   在词表批次登记后再编译。
5. **C19 registry 口径冲突**：008 回 `李→李天扬` 与 registry `李钦差`（E0047，note 称本名未揭示）冲突；
   017 回 `金戈` 未登记。建议实体层补登/改口径，或回写机器初稿时去除未证实全名。
6. **C20 为启发式体检**：P1/P3 本轮 0 命中属语料干净而非规则缺陷（`--selftest` 已证明可触发）；
   P6/P8 在本轮复跑降为 0 error / 0 hit，是因上一轮已修复 `019` 的标点动词令牌与 `030` 回末对令牌
   （旧形态回填可复得 19 条，见 §5.2）；P7 称谓表为静态清单，未覆盖的称谓形式会漏报；
   P6 对修辞固定表达内标点只计 info（02j 允许）。
7. **跨脚本衔接**：C20 的建议 TSV 是「人工审查表」而非 C7 插入契约（修复动作是删/拆令牌，非插入），
   后续如需机械化修复，应按 `fix_annotation_mechanical.py` 的确定性修复路线扩展，而非 C7。
8. **`--apply` 上标前置条件**：执行前应先人工确认 `registry/patches/*_aliases.tsv`（尤其描述性旧称与
   词形歧义词），再跑 `--apply`；脚本会备份到 `backup/tagged/<书>/` 并逐回断言，失败自动回滚。

---

## 八、产物清单（可复算）

```text
scripts/scan_untagged_aliases.py            # C18
scripts/infer_single_char_names.py          # C19
scripts/detect_entity_boundary_errors.py    # C20
logs/aliases/白发魔女传_alias_scan.md|json  # C18 汇总（32 回）
logs/single_char_names/白发魔女传.md|json   # C19
logs/boundary/白发魔女传.md|json            # C20
registry/patches/*_aliases.tsv              # 23 个 C18 建议
registry/patches/*_boundary_fix.tsv         # 10 个 C20 审查表（当前语料）
logs/_p2_c18c20/tagged_before.txt|after.txt # tagged 零改动证据
```

## 九、P2-B 变更摘要（2026-11-05）

- **C20 selftest hermetic**：内置 mock registry/WN，`--selftest` 不再依赖真实 registry；
  无 registry 环境 8/8 PASS（V12）。主流程仍真实加载。
- **C18 apply 长词保护**：`known_words=set(word_map)` 传入 `_apply_word`，无 pos 回退跳过
  "更长已知词前缀"位置；`--selftest` 增补断言（V13），临时文件集成验证插入 1 处（V14）。
- **健壮性**：4 处 JSON `items` 载入兼容顶层 list（V15）；`C19.parse_chapters` 非法输入友好
  SystemExit（V16）。
- **复跑无回归**：C18 101 条 / 23 回、C19 映射 10（新推断 0）、C20 当前 16 条（旧形态回填 19 条，
  V17）；py_compile exit 0；tagged 32 回 SHA256 前后一致（V10）。
- **产物更新**：`logs/aliases`、`logs/single_char_names`、`logs/boundary` 报告与
  `registry/patches/*_boundary_fix.tsv`（10 个，删除已失效的 `019_boundary_fix.tsv`）已按当前语料重生成。
