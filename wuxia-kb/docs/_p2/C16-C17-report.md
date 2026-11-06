# C16 + C17 实现报告 · 武侠新增实体类型 / 身份·亲属词表外置化

> 任务：task-5（P2 实体层）。日期 2026-11-04。范围：`scripts/tag_new_entity_types.py`（C16）、
> `scripts/tag_identity_kinship.py`（C17）、`wordlists/{new_entity_types,identity,kinship}_source.md`
> 及其编译产物、`registry/patches/` 建议 TSV。**本轮不写 tagged、不 commit、不调 LLM。**
> 权威依据：docs/17 §2.2 C16/C17、docs/05 §2.8、skills/SKILL_01g（15 类 + D1/D2 + 负规则）、
> skills/SKILL_03a（v1.8 D1）、skills/SKILL_词表体系规划（D09 八字段 + 三档）、
> 移植源 shiji-kb/scripts/{tag_new_entity_types,tag_identity_words,tag_kinship_words}.py（只读）。

## 1. 交付清单

| 交付 | 路径 | 状态 |
|---|---|---|
| C16 脚本 | `scripts/tag_new_entity_types.py` | 完成（dry-run 全 32 回不崩，默认只出 TSV） |
| C17 脚本（identity+kinship 合并） | `scripts/tag_identity_kinship.py` | 完成（同上） |
| C16 词表人工源/派生 | `wordlists/new_entity_types_source.md` → `new_entity_types.json` | 268 条 |
| C17 身份词表 | `wordlists/identity_source.md` → `identity.json` | 212 条 |
| C17 亲属词表 | `wordlists/kinship_source.md` → `kinship.json` | 62 条 |
| 建议 TSV | `registry/patches/NNN_new_entities.tsv`（13 张）、`registry/patches/NNN_identity_kinship.tsv`（32 张） | 由脚本生成 |
| 本报告 | `docs/_p2/C16-C17-report.md` | — |

所有词表产物均为 `wordlist_compiler.py --name <表>` 单表编译，**未用 `--all`**（避免重写其他表）；
`.json` 是派生物，人工只改 `_source.md`。

## 2. 词表（人工源 + 编译校验）

统一列式：`| surface | type | tier | status | conf | evidence | note |`；evidence=`书:回`（楔子记 `书:楔子`）。
**tier 纪律：三张表一律 review/watch，零 auto**；status 一律 `待审`。conf 由证据强度定
（strong=明文直证 / ok=kb 表登记或跨书语料实证 / weak=先验或通名）。

| 表 | 条数 | type 分布 | tier 分布 | conf 分布 |
|---|---|---|---|---|
| new_entity_types | 268 | ☆115 / •80 / {24 / ◆49 | review 239 / watch 29 | strong 38 / ok 201 / weak 29 |
| identity | 212 | `;` 职衔 82 / `#` 身份 130 | review 191 / watch 21 | ok 185 / weak 27（2026-11-05 P1 修复：7 条无语料证据条目降 weak；P2-A 裁定 寨主/宫主 改 `;`、管家 定为 `#` 后 3 条 weak→ok） |
| kinship | 62 | `#` 身份 62 | watch 62 | weak 62 |

- **new_entity_types**：☆ 取 `kb/招式表.json` 中在白发语料出现的招式 + `parent_art` 父式名 +
  语料 ☆ 具名技艺 + 跨书 strong/ok 招式；• 取 `kb/神兵表.json` 的 183 条「名物」中抽 80 条具名条目
  （护甲/暗器/剑/刀/奇门/宝物）；{ 取跨书语料实证的秘籍与典籍（玄功要诀、毒龙秘笈、百毒真经、
  龙泉百炼诀、易筋经、达摩一百零八式、本草纲目、奇经八脉考、左传、西厢记…）；◆ 取门派世系表 7 派 +
  语料 ◆ 实体（武当派/少林/天龙派/峨嵋派/龙门帮/锦衣卫/东厂/西厂/兵部/朝廷/满洲…）。
- **identity**：职衔覆盖掌门/长老/帮主/盟主/舵主/总舵主/堂主/香主/坛主/教主/护法/寨主/堡主/庄主/
  方丈/知客/总管/教头/头目/首领/大帅/将军/统领/指挥/侍卫长/总督/巡抚/知府/知县/钦差/太监/内监/
  尚书/侍郎/御史/经略/提督/总兵/参将/大学士/首辅/宰相/皇室位号/镖行职衔…；身份覆盖武师/镖师/镖头/
  卫士/道士/尼姑/和尚/喇嘛/书生/士子/秀才/强盗/大盗/喽兵/官军/官兵/狱卒/店家/掌柜/伙计/客商/
  丫鬟/仆役/内应/细作/使者/太医/郎中/猎户/船家…（只收稳定职业/处境类别，不收评价词）。
- **kinship**：父母/兄弟/姐妹/哥弟姐妹/叔伯姑姨舅/岳父母/丈夫妻子/儿女孙/女婿儿媳/妾侍/堂表/
  外甥侄子侄女/继养义亲/干爹/亲家 等 62 条；**单字亲属词（父/母/兄/弟/姐/妹/妻/子/女）不收**
  （子串歧义：弟子/桌子/子弹），改收双音形式。

## 3. C16 设计：从「4 套内联史记词表」到「外置武侠词表」

对 shiji 原脚本的 6 处改造：

1. **词表外置**：原 4 套内联 set（典籍/礼仪/刑法/思想）删除，改读编译产物
   `wordlists/new_entity_types.json`，经 `masker.load_wordlist` / `masker.find_candidates`
   消费（词表是数据不是代码）；类型 = 01g 定版实体码。
2. **路径接 config**：原写死 `chapter_md` / `data/patches`；改为 `config.DIR_TAGGED` 枚举
   `<书>/NNN.tagged.md`，输出 `config.DIR_REGISTRY/patches`，支持 `--book/--chapter/--all/--out`。
3. **已标注保护**：原内联字符类 → `symbols.TOKEN_RE`；实现上把令牌整段掩成等长占位再匹配
   （mask 与原文等长），既保证「已标注区间不重复标注」，也避免跨令牌边界拼词。
   **TSV `位置` = 原文偏移（含标记）**（P2-A 修复）：`pos = line_start + 行内偏移`，
   `line_start` 为原文累计 `len(line)+1`；旧的「剥标累计行首 + masked 行内偏移」混基准口径已删，
   可用 `原文[pos:pos+len(word)] == word` 直接断言（docs/46 §二-5）。
4. **围栏与回目保护**：`::: 词/诗/歌/对联/回末对/回末/书信/…` 整块（含标记行）跳过——
   02ab §4.4 中「回末/回末对全不标」「词/诗/歌实体限实指」，词表召回无法判实指，故保守跳过；
   `# [0] 回目` 与标题行同样跳过；回末套语因处于 `::: 回末` 围栏内被一并跳过。
5. **最长优先、不重叠、单字不入建议**：`masker` 最长匹配；另设逐词/类型级负规则。
6. **只出建议 TSV**：默认不写 tagged；`--apply` 为可选（备份 → 调 C7 应用 → 剥标还原断言 →
   失败自动回滚），本轮未执行。

**负规则（C16，脚本层）**：
- 通名不标：剑法/武功/轻功/掌法/拳法/身法/武艺/功夫/绝技/手法 等不收；通名器物（短箭/佩刀/铁尺）
  与生物（汗血宝马）不入 • 表。
- 冻结名内部成分不拆（01g 负规则四/五）：整词最长匹配，不从「怪蟒翻身」抽「蟒」。
- 同形歧义词逐词黑名单：`大明`（天已大明=天亮，前缀 天/已/渐/微 跳过）、`神拳`（神拳无敌=绰号，
  后缀 无敌 跳过）、`剑诀`（剑诀一领=剑指手势，后缀 一/领/捏 跳过）、`武当`/`少林`（武当山/寺，
  后缀 山/寺/观 跳过）、`满洲`/`满州`（满洲话/满洲人=语族义，后缀 话/人 跳过）。
- 类型级：`◆` 组织后紧接 **☆ 武功令牌**（下一令牌码为 ☆，如 武当〖☆剑法〗）说明「门派+技艺」
  复合已被既有标注切段，不再把门派前缀拆成独立建议。
- **负规则跨令牌可见字符**（P2-A 修复，docs/46 §二-7）：前后缀规则的邻字若落在既有令牌内
  （右邻 〖 / 左邻 〗），改取该令牌**显示串首/末字**再匹配，避免 `〗`/`〖` 导致正则失配；
  无令牌时保留裸文分支。单元自检：`〖%天〗大明`→拦（前缀规则命中）、`满州〖#人〗`→拦、
  `满州〖#武师〗`→放行、`武当〖☆剑法〗`→拦、`武当〖#第二代弟子〗`→放行、裸文`武当的四个长老`→放行。
- kb 破损/误收条目不入表：铁门删、长鼓齐呜、辟云锄、乘龙引凰、凌未风（人名混入神兵表）、
  回环钧（回环钩异写）、左右开弓（在本书均为成语用法「左右开弓打耳光」）、断门刀/判官笔/
  独门剑法（通名或非具名）、九星定形针（跨类同形，归 • 器物——语料 ☆ 标注为误标）。

## 4. C17 设计：identity + kinship 合并、D1 硬前置

对 shiji 两脚本的合并与改造：

1. **两套内联规则 → 两张外置词表**：`identity.json`（`;` 职衔 / `#` 身份）+ `kinship.json`；
   经 `masker` 合并消费（同 surface 以 identity 优先）。
2. **保留 prefix/suffix 黑名单机制并升级**：逐词 `(前缀正则, 后缀正则)` 规则表；
   另加两类数据驱动规则（详见 §5）。
3. **已标注/围栏/回目保护**：与 C16 同（`symbols.TOKEN_RE` 掩码 + 围栏整块跳过 + 行首 `#` 跳过）；
   TSV `位置` = 原文偏移（含标记），与 C16 同口径（P2-A 修复）。
4. **只出建议 TSV**，默认不写 tagged；`--apply` 可选且同样带备份+剥标断言（本轮未执行）。
5. **类型裁定**：
   - 同一 surface 只入一类；**语料已标者从其既有类型**（G1/G2 语料一致性优先，避免同词跨类），
     冲突条目降 `watch/weak` 并在 note 标注「待人工裁定」。
   - 职衔 `;` = 可担任/履任/继任/任命的朝廷与江湖建制职位（03a §; 定义，含山庄/帮会建制：
     〖;庄主〗〖;堡主〗〖;舵主〗）；身份 `#` = 职业类别/处境身份（〖#武师〗〖#镖师〗〖#道士〗
     〖#随从〗…）。
   - **kinship 类型**：亲属关系词在 15 类中没有独立类型；语料既有先例把 〖#哥哥〗〖#妻子〗
     〖#爸爸妈妈〗 标为 `#` 身份，故本表沿用 `#` 身份码、tier 全 watch、conf=weak，最终
     归 `#` 还是转关系层（SKILL_关系体系 亲属边）留人工裁定。
   - **师承关系词不入 identity**：弟子/徒弟/门人/门徒/传人/师父/师兄/师弟/师姐/师妹/师叔/
     师伯/师祖 按 03a D1「无姓名纯关系词不标」处理（few-shot 甲中「这样一位好徒弟」即未标）；
     身份表只收「第二代弟子」「大弟子」「首徒」这类可类别的定名形式。

### 4.1 P2-A 修复记录（task-10：docs/46 §二 5/6/7 + 词表裁定 + 载入健壮性）

| # | 位置 | 修复 | 验证 |
|---|---|---|---|
| 1 | C16/C17 `scan_chapter` | TSV `pos` 改**原文偏移**：维护 `line_start`（原文累计 `len(line)+1`），`pos = line_start + 行内偏移`；删除 `display_offset` 逻辑；docstring 改「位置=原文偏移（含标记）」 | 45 张建议 TSV / 959 行断言 `原文[pos:pos+len(word)] == word`，**0 失败** |
| 2 | C16 `hit_blocked` | 新增 `token_display/token_ending_at/token_starting_at/prev_visible/next_visible`：前后缀负规则改在**可见字符**上判断（跨令牌仍生效）；`◆`+`ORG_BEFORE_MARTIAL` 改「**下一令牌码 = ☆**」判断；保留裸文分支 | 6 例单元自检全部符合预期（见 §3 末条） |
| 3 | C17 `kinship_blocked` | 左邻令牌必须 `symbols.parse_token(...)` 为 `layer=entity, code=@`（**人物令牌**）才作指称对象；`#`/`☆` 等其他类型令牌不放行 | 5 例单元自检：〖@卓一航〗父亲→放行；〖#臭老鬼〗丈夫→拦；〖☆剑法〗女儿→拦；他的父亲→放行；大丈夫→拦 |
| 4 | 两脚本词表载入 | 顶层兼容 `items = data if isinstance(data, list) else data.get("items", [])`（与 `masker`/`wordlist_compiler` 一致），源 JSON 顶层为 list 时不再 AttributeError | 临时裸 list 词表实测两脚本各载 1 条 OK；`py_compile` 通过 |

> 修复后全网复跑：C16 53 条（不变）、C17 **906** 条（原 917，−11 全部来自第 3 项——
> 此前 11 处 kinship 命中是靠 `#` 等非人物令牌左邻放行的，现已拦截：女儿 −3、父亲 −2、儿子 −2、
> 爹爹 −1、丈夫 −2、兄弟 −1）。pos 改为原文偏移后 C7 契约兼容性复测通过（C7 不消费 pos）。

## 5. 与 SKILL_03a D1 的一致性裁定

**kinship 硬前置（本轮明确裁定）**：03a D1「具有稳定识别信息、能够确认所指的称名照标；纯礼貌、
关系称呼和临时评价代称不标」+「无姓名纯关系词（父亲/祖父/女儿/女婿/师兄/岳父/徒儿/儿子/孙儿）
不标」。因此本脚本**不给 kinship 做无条件建议**，只在其左侧存在**明确指称对象标记**时建议：

1. 领属结构：`的` / `之` / `其`（可跨一个令牌闭括号）——「他的父亲」「卓氏之子」；
2. 紧邻**人物令牌**：左邻为 `〖@…〗` 闭括号——「〖@卓一航〗的父亲」；P2-A 起按令牌类型校验，
   仅 `layer=entity, code=@` 放行（`#`/`☆` 等其他类型令牌不作指称对象，docs/46 §二-6）；
3. 第一二人称领属：`我/你/他/她/俺/咱/自己/自家`（可带 的/之）——「你父亲」「他自己的孙儿」。

同时硬负规则：谦辞/自称（家父/家母/家兄/舍弟/犬子/小女/拙荆/贱内/内人…）不入表且 `NEVER_TAG`
兜底；称呼语（「父亲！」「哥哥！」）因无指称标记自然不产出；单字亲属词不收。
**裁定结论**：kinship 建议 = 「D1 允许的领属+指称结构」，不是「一切亲属词」；类型暂挂 `#` 身份。
`公公`（太监面称）不入表；`丈夫` 仅在领属结构下命中，「大丈夫」不触发。

**identity 负规则（与 01g §8.2 D1 / §8.4 负规则二一致）**：
- 谦辞·自称不标：家父/家母/家兄/舍弟/犬子/小女/拙荆/贱内/内人/愚兄/小弟/晚生/晚辈/卑职/
  小的/奴才/在下/贫道/贫僧/微臣/臣/俺；
- 纯礼貌称呼不标：前辈/先生/小姐/老伯/贤弟；描述评价代称不标：汉子/少年/少女/美妇人/女侠/
  英雄/豪杰；阵式战术角色不标：先锋/后卫/主帅（03a §; 明确「阵式战术角色非建制职不标」）；
- 专名前缀不标（吕太后式）：皇太后/皇后/公主/太子/王爷/藩王/皇子 前接专名汉字即跳过，
  功能字与序数字（把/将/立/为/的/一/二/大/小…）白名单不视为专名；
- 后接表字/人名不标（太子常洛式）：后紧接 `registry/entities.json` 的 @ 类 canonical/aliases
  （75 个人名否定集）即跳过；
- 逐词同形歧义：掌门（「回去掌门」「师叔掌门」动词义，前缀 去/回/作/当/继/接/叔/伯 跳过）、
  手下（「手下留情/手下败将」后缀 留/败 跳过）、杀手/保镖/主持/家人/领袖（动词义或评价义主导，
  不入表或 NEVER_TAG 兜底）、头子（老头子的 老/糟 前缀跳过）、大将（大将军不拆）、
  指挥（动词义：后接 女/兵/人/众/军/盗/马 或标点跳过）、经略（经略辽东）、副将（副将军）、
  师爷（祖师爷）、总管（大总管）、俘虏（俘虏了）、叛逆（谋叛逆/叛逆之名/叛逆实据）、
  大明（天已大明）、神拳/剑诀（见 C16）、老二/店小二（店 前缀）。

### 5.1 词表裁定记录（P2-A，task-10；按 01g/03a，不靠猜）

| 条目 | 原状态 | 裁定后 | 依据 |
|---|---|---|---|
| 寨主 | `#` watch/weak，note 自认「与职衔归类冲突，待人工裁定」 | **`;`** review/ok | 01g「金刀寨主是职位短语」示例 + 03a `;`=可任命/履任的建制职位 |
| 宫主 | `#` watch/weak，同上 | **`;`** review/ok | 同上（宫主为可担任的宫职名号） |
| 管家 | `#` watch/weak，同上 | **`#`** review/ok（保留身份） | 职业类别、非建制职位（不可履任/继任），按 03a `#`「职业类别/社会身份」定义保留 |
| 皇室 / 王室 / 朝廷 / 明朝 / 大清 / 满清 | ◆ review/ok | ◆ 不变，note 补「政权类（01g ◆ 定义含国家/政权）」 | 01g `◆` 定义含国家、政权 |

> note 按裁定重写：寨主/宫主=「按 01g 职位短语裁定改 ;（P2 修复）」；管家=「职业类别（非建制职位），
> 保留 #（P2 裁定）」。3 条原为「类型未定」的观察档（watch/weak），裁定后按 D09 §3.3 派生 review/ok；
> `identity` 重编译 212 条 PASS（type `;`82/`#`130、tier review191/watch21、conf ok185/weak27），
> `new_entity_types` 重编译 268 条 PASS（条数/档位不变）。

## 6. 类型映射（TSV 契约）

| 词表 type 码 | TSV「实体类型」列 | apply_annotation_patches.TYPE_NAME_TO_CODE 反向命中 |
|---|---|---|
| ☆ | 武功 | `'武功': '☆'` |
| • | 器物 | `'器物': '•'` |
| { | 作品 | `'作品': '{'` |
| ◆ | 门派 | `'门派': '◆'` |
| ; | 职衔 | `'职衔': ';'` |
| # | 身份 | `'身份': '#'` |

TSV 列：`章节 全名 词 位置 框架类型 匹配模式 上下文 实体类型` + 扩展列 `词表档位 证据`
（C17 另有 `词表来源`）。`load_tsv` 只读前 8 列（`parts[7]`=实体类型）、多余列忽略，
故扩展列不破坏契约；`位置` 为**原文偏移（含标记）**，`原文[pos:pos+len(word)]==word` 可断言
（C7 目前不消费 pos，实际按 `text.find` 全插定位）。
文件名：`NNN_new_entities.tsv` / `NNN_identity_kinship.tsv`；单书章节列写 `001`，
多书自动写 `书名/001` 消歧（02ab §2.6）。`--types` 支持中文名与实体码双向。

## 7. 实跑统计（白发魔女传，32 回）

### 7.1 单回 001

| 脚本 | 建议数 | 词种 | 回命中 | 类型分布 |
|---|---|---|---|---|
| C16 tag_new_entity_types | **0** | 0 | 0/1 | —（001 回 ☆/•/{ 具名实体已全部标注，唯一未标候选「左右开弓」为成语用法，已按质检剔除） |
| C17 tag_identity_kinship | **12** | 7 | 1/1 | 职衔 1 / 身份 11；identity 7 / kinship 5 |

### 7.2 全书 32 回（`--all --dry-run`）

| 脚本 | 建议数 | 词种 | 回命中 | 类型分布 | 备注 |
|---|---|---|---|---|---|
| C16 | **53** | 13 | 13/32 | 门派 48 / 作品 3 / 器物 2 / 武功 0 | 命中集中在组织省称（满州19、武当13、满洲7、朝廷3、明朝2、禁卫军2…）——☆/• 具名实体在 32 回中标注已较完整（语料实测 ☆783/•2665/{356/◆694），补标空间主要在 ◆ 与通名文书 |
| C17 | **906** | 110 | 32/32 | 职衔 201 / 身份 705；identity 622 / kinship 284 | Top：女儿68、掌门55、卫士53、父亲50、官军41、儿子40、喽兵35、爹爹31、堡主31、喇嘛27、手下21、和尚21、强盗20、掌柜19、妻子18、使者16、王爷15、道士14、母亲14、高手13 |

C16 类型为 0 的「武功」是**语料实况**而非漏召回：32 回中招式表的 118 次出现仅 6 次未标，且这 6 次
分别是成语「左右开弓」（2）、「摔角」（2）与另两书回目的 2 例（金刃劈风/冰河倒挂——白发语料无）；
剔除后无正当漏标。

## 8. 抽样 5 条人工核对

### C16（001 无命中，从全书最近批次抽 5 条）

| # | 回 | 建议 | 上下文 | 裁定 |
|---|---|---|---|---|
| 1 | 026 | 〖◆武当〗 | 武当的〖$四个〗长老… | ✅ 合理：武当=武当派省称，实指组织，与既有 〖◆武当〗 86 例用法一致 |
| 2 | 023 | 〖◆满洲〗 | 想冒充满洲使者 | ✅ 合理：政权/势力实指 |
| 3 | 023 | 〖◆禁卫军〗 | 神宗开榜招考禁卫军 | ✅ 合理：军队机构实指 |
| 4 | 026 | 〖{拳经〗 | 拳经所谓：“舍已从人” | ⚠️ 待审：通名典籍的内容对象指称，watch 档；与语料既有 〖{剑谱〗 处理一致，但需人工确认 |
| 5 | 030 | 〖◆明朝〗 | 此人乃明朝的奸阉 | ⚠️ 待审：朝代/政权指称，语料既有 〖◆明朝〗 先例；是否与 ~ 族群/^ 概念分工需裁定 |

### C17（001，12 条中取 5）

| # | 建议 | 上下文 | 裁定 |
|---|---|---|---|
| 1 | 〖;知府〗 | “三年清知府，〖$十万〗雪花银。” | ✅ 合理：职衔 ;（谚语中仍为官职指称） |
| 2 | 〖#儿子〗 | 〖@耿绍南〗却拿着他儿子的〖{信〗 | ✅ 合理：D1 领属结构 + 明确指称对象；kinship watch 档 |
| 3 | 〖#书生〗 | 心里想道，书生学剑 | ✅ 合理：身份 #（职业类别） |
| 4 | 〖#盗贼〗 | 〖=西北〗地瘠民贫，盗贼纷起 | ✅ 合理：身份 #（处境/职业类别） |
| 5 | 〖#手下〗 | 一声呼哨，手下早扶起了受伤的同伙 | ✅ 合理但 watch：泛称/两义，语料 # 先例一致 |

> 核对结论：C16 抽样 3 合理 2 待审（通名/政权边界），C17 抽样 5 全部合理。全量建议按词逐类审读
> （高频词全量看语境 + 低频词全覆盖抽样），共剔除/加规则约 10 类高误报词形（见 §3/§5），
> 剩余命中以组织省称与身份类别为主。

## 9. 验证结果（全部实测）

| 验证项 | 命令 | 结果 |
|---|---|---|
| 语法编译 | `python -m py_compile scripts/tag_new_entity_types.py scripts/tag_identity_kinship.py` | ✅ PASS |
| 词表全量校验 | `python scripts/wordlist_compiler.py --check` | ✅ 8/8 表 PASS（新增 3 表 errors=0 warns=0） |
| 单表编译 | `python scripts/wordlist_compiler.py --name new_entity_types` / `identity` / `kinship` | ✅ 268 / 212 / 62 条，均 errors=0（P2-A 裁定后重编译） |
| 词表载入兼容 | 临时裸 list 词表（`[{"surface":...}]`）分别喂两脚本 | ✅ 两脚本各载 1 条，无 AttributeError |
| **TSV pos 断言** | `python logs/_tmp_pos_assert.py`（临时脚本，不落库） | ✅ 45 张 TSV / **959 行** `原文[pos:pos+len(word)]==word`，**0 失败** |
| C16 全书 dry-run | `python scripts/tag_new_entity_types.py --all --dry-run` | ✅ 不崩，53 条建议 / 13 词种 / 13 回 |
| C17 全书 dry-run | `python scripts/tag_identity_kinship.py --all --dry-run` | ✅ 不崩，906 条建议 / 110 词种 / 32 回 |
| 001 单回 dry-run | `--book 白发魔女传 --chapter 001 --dry-run` | ✅ C16=0 条、C17=12 条 |
| C7 契约兼容 | `python scripts/apply_annotation_patches.py --file registry/patches/001_identity_kinship.tsv --dry-run` | ✅ `12 条建议, 实际插入 0 处`：load_tsv 解析、章节解析（001）、按词定位与插入点全部走通，无写入 |
| C7 契约兼容（C16） | `python scripts/apply_annotation_patches.py --file registry/patches/026_new_entities.tsv --dry-run` | ✅ `12 条建议` 解析成功（含 `〖◆…〗`/`〖{…〗` 类型映射），无写入 |
| tagged 无写入 | 32 个 `*.tagged.md` 前后 SHA256 对比 | ✅ 32/32 完全一致 |
| git | `git -C .. status --porcelain -- wuxia-kb/tagged` | ✅ 仅 `?? wuxia-kb/tagged/`（该目录整体未跟踪，0 个 tracked 文件），无任何 tracked tagged 改动 |
| 本轮未执行 | `--apply` / commit / LLM | ✅ 未调用 |

## 10. 已知局限

1. **C7 `--apply` 语义更宽**：`apply_annotation_patches` 按「同词多现全插」应用（位置/上下文只用于
   排序），比本脚本的逐位置建议宽——对依赖领属结构的 kinship 建议会过度应用。故本轮按约定不跑
   apply；将来若 apply，须人工确认或改用逐位置应用器；本脚本内置的「写前备份 + 剥标还原断言 +
   失败回滚」可兜住改写风险。
2. **C16 召回以通名/省称为主**：具名 ☆/• 在 32 回中标注已很完整，收通名会显著增加误报（已实测剔除
   短箭/佩刀/判官笔/断门刀/独门剑法等），故质量优先导致命中数偏低；扩书后（另 3 部 KB 书）应复跑。
3. **满洲/满州 未归一**：两个 surface 指向同一实体，D09 canonical 缺省=surface；建议后续用别名表
   归一（kb 神兵表 alias_candidates 已有机制）。
4. **kb 资产质量**：招式表存在破损/误收条目（铁门删、长鼓齐呜、辟云锄、乘龙引凰 等），神兵表混入
   人名（凌未风）、异写（回环钧），均已剔除；建议回写 kb 侧修订。
5. **kinship 类型归属待裁**：暂挂 `#` 身份（语料先例），严格 03a D1 是「纯亲属词不标」；本脚本取
   「仅领属结构建议」的中间档，最终归 `#`/改关系层需人工定。
6. **专名前缀白名单为近似**：`熊经略`（人名+职衔复合）仍有 1 例边界误判可能；人名否定集只覆盖
   `registry/entities.json` 75 个已登记名，未覆盖全书全部人名。
7. **围栏 `real_only` 未实现**：词/诗/歌围栏内一律跳过（02ab §4.4 的「实体限实指」未做自动判定），
   可能漏标围栏内真实体。
8. **单字词不收**：父/母/兄/弟/姐/妹/妻/子/女 等单字称谓因歧义不入表（档位纪律），会漏一部分。
9. **C7 `--apply` 仍按全插语义**：pos 口径已修正，但 `apply_annotation_patches` 不消费 pos；
   若将来用 C7 apply，仍会「同词全插」并可能覆盖本脚本的逐位置/领属限定语义——apply 前须人工确认，
   或改接支持 pos 精确插入的应用器。本轮未执行 `--apply`。
10. **词表证据缺口**：identity 7 条无语料证据条目已由 P1 修复降 `weak` 并在 note 标注「语料未检出
    （先验/待验证）」；kinship 2 条（叔母/婶母）亦语料未检出，按 D09「watch 档允许暂无 evidence」保留。

## 11. 复算命令

```powershell
$env:PYTHONIOENCODING='utf-8'
# 1) 词表（只编 3 张，禁 --all）
python scripts/wordlist_compiler.py --name new_entity_types
python scripts/wordlist_compiler.py --name identity
python scripts/wordlist_compiler.py --name kinship
python scripts/wordlist_compiler.py --check       # 8 表全 PASS
# 2) 语法
python -m py_compile scripts/tag_new_entity_types.py scripts/tag_identity_kinship.py
# 3) 单回 dry-run
python scripts/tag_new_entity_types.py --book 白发魔女传 --chapter 001 --dry-run
python scripts/tag_identity_kinship.py --book 白发魔女传 --chapter 001 --dry-run
# 4) 全书 dry-run / 出建议 TSV（默认出 TSV，不写 tagged）
python scripts/tag_new_entity_types.py --all --dry-run
python scripts/tag_identity_kinship.py --all --dry-run
python scripts/tag_new_entity_types.py --all
python scripts/tag_identity_kinship.py --all
# 5) C7 契约兼容（只 dry-run，不写）
python scripts/apply_annotation_patches.py --file registry/patches/001_identity_kinship.tsv --dry-run
python scripts/apply_annotation_patches.py --file registry/patches/026_new_entities.tsv --dry-run
# 5b) pos 断言（原文偏移；临时脚本，不落库）：45 张 TSV / 959 行全过
python logs/_tmp_pos_assert.py
# 6) optional --apply（写前备份 + 剥标断言 + 回滚；本轮未执行）
# python scripts/tag_new_entity_types.py --all --apply
# python scripts/tag_identity_kinship.py --all --apply
```

## 12. 附：TSV 样例 5 行（C17 / 001）

```text
章节	全名	词	位置	框架类型	匹配模式	上下文	实体类型	词表来源	词表档位	证据
001	知府	知府	443	词表匹配	知府	俗语说得好：“三年清知府，〖$十万〗雪花银。	职衔	identity	review	白发魔女传:1
001	儿子	儿子	760	词表匹配	儿子	〖@耿绍南〗却拿着他儿子的〖{信〗来了，信上	身份	kinship	watch	白发魔女传:1
001	书生	书生	861	词表匹配	书生	并不甚解，心里想道，书生学剑，武艺好也有限，	身份	identity	review	白发魔女传:1
001	盗贼	盗贼	1033	词表匹配	盗贼	〖=西北〗地瘠民贫，盗贼纷起，所以〖@卓仲廉	身份	identity	review	白发魔女传:1
001	手下	手下	2833	词表匹配	手下	说完之后，一声呼哨，手下早扶起了受伤的同伙，	身份	identity	watch	白发魔女传:1
```

（`位置` 已按 P2-A 改为**原文偏移（含标记）**，可直接 `原文[pos:pos+len(word)]==word` 断言；
C16 样例见 `registry/patches/026_new_entities.tsv`：〖◆武当〗×9、〖{拳经〗×1 等。）
