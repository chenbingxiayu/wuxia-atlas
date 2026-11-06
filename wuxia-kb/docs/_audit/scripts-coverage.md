# 脚本覆盖率审计：docs/17 C0/C/N/E 组 vs 实际两个 scripts 目录

> 审计员：script-auditor（team task-2）｜日期：2026-11-04｜工作目录：`wuxia-kb/`
> 依据：`docs/17`（§2.1 C0a-C0d、§2.2 C1-C24、§2.3 N1-N11、§2.4 E1-E11、§七进度）、`docs/05` §2.8（shiji 30 脚本函数级判定）、`docs/38`、`docs/27` §7.1。
> 对象：目录 A `wuxia-kb/scripts/`（37 个 .py + `_oneshot/` 5 个历史脚本）；目录 B `Wuxiaxiaoshuo/scripts/`（44 个 .py）；参考源 `shiji-kb/scripts/`（仅核对移植源是否存在）。
> 约束执行：未调用任何付费 LLM API（annotate_*/qwen_review 均未运行）；未修改任何源码；未改 `tagged/` 正文；未 commit。原始命令输出见同目录 `scripts-run.log`。

---

## ① 一句话结论

迁移计划 50 个脚本节点（C0 4 + C 24 + N 11 + E 11）**只完成 24 个（48%）**：C0 4/4 与 P1 的 C1-C15/C21-C23、N1/N2 已落地可用，但 **C16-C20、C24 与 N3-N11 全部没有脚本**，E 组 0 个完全对接（4 个部分、7 个未动）；已实现件中 **C6 `find_candidate_entities.py` 在默认批处理模式下必崩**（`KeyError`），另有 **13 个计划外脚本**把 LLM 标注链（docs/38 的 020-032 回）做成了，但这是绕过 P2-P5 计划的旁路成果，不改变"计划脚本整体未实现"的结论。

---

## ② 汇总统计

| 组 | 计划节点 | 文件已落地 | ✅ 有运行证据 | ◐ 部分/未实跑 | ❌ 缺失或不可用 | 文件口径完成率 |
|---|---:|---:|---:|---:|---:|---:|
| C0 地基 | 4 | 4 | 4 | 0 | 0 | **100%** |
| C 移植/改造（C1-C24） | 24 | 18 | 15 | 2（C5/C7 未实跑） | 7（C6 + C16-C20、C24） | 75%（C6 可用性另计） |
| N 武侠新写（N1-N11） | 11 | 2 | 2（N1/N2） | 0 | 9（N3-N11） | **18%** |
| E 既有管线对接 | 11 | 0 | 0 | 4（E1/E4/E8/E11） | 7（E2/E3/E5/E6/E7/E9/E10） | **0%** 完全对接 |
| **合计** | **50** | **24** | **21** | **6** | **23** | **24/50 = 48%**（含 4 个部分对接 = 56%） |

> 两套口径说明：**文件口径** 24/50（C0 4 + C 18 + N 2 + E 0）；**运行证据口径** 21/50（C 中 C5/C7 仅有 `--help`/静态证据、C6 实跑崩溃，故 C 只计 15）；把 4 个部分对接的 E 节点计入后为 28/50 = 56%。核心数字与任务预期一致：**C0 4/4、C 18/24、N 2/11、E 0 完全对接 + 4 部分**。

**目录 A 文件账（37 个 .py）**：C0 4 + C 18（C1-C15、C21-C23）+ N 2（N1/N2）+ 计划外 13 + `pipeline_wuxia.py`（编排器，计划外/§七登记）= 37。`_oneshot/` 另有 5 个一次性生成器（T02/T03/T04 设计稿双稿生成，非管线，见 `scripts/README.md`）。

**静态校验**：81 个 .py（A 37 + B 44）`py_compile` **0 失败**；目录 A 本地 import 全部可解析（config/symbols/masker/api_config/wordlist_compiler 均存在，唯一三方依赖 `requests` 2.33.1 已安装）；被引用数据文件除 2 处已声明"规划/可选"外均存在（详见 ⑦）。

---

## ③ 逐节点表

### 3.1 C0 地基（4/4）

| 节点 | 实际文件 | 状态 | 证据（路径:行/API/运行） | 备注 |
|---|---|---|---|---|
| C0a | `scripts/config.py` | ✅ | `config.books()` L103 / `chapter_path()` L118 / `tagged_path()` L134 / `struct_path()` L138 / `DIR_*` L31-36；实跑 `python -c "len(config.books())"` → **34 部**（与章回版 34 目录一致） | 路径唯一来源；`slug` 未回填（G0 后补），`SHIJI_SCRIPTS` 死常量见 ⑦ |
| C0b | `scripts/symbols.py` | ✅ | `ENTITIES` L15（实测 15 类）/`VERBS` L34（实测 6 域）/`FENCE_FORMAL` L60 + `FENCE_OBSERVE` → `FENCE_ALL` L62（实测 10 类）/`TOKEN_RE` L100/`parse_token()` L107/`strip_markup()` L140/`fence_opens()` L154 | 全脚本 import，禁本地字符类；实测 `ENTITIES/VERBS/FENCE_ALL` 数量相符 |
| C0c | `scripts/masker.py` | ✅ | `build_matcher()` L24/`load_wordlist()` L44/`find_candidates()` L51/`mask_text()` L75；被 `tag_quantity_entities`（L29 import masker）与 `find_candidate_entities`（L33）消费；`tag_quantity --dry-run` 实跑 6 处命中 | 最长优先匹配；词表经 JSON 消费 |
| C0d | `scripts/wordlist_compiler.py` | ✅ | `compile_one()` L124/`main()` L155（`--all/--name/--check`）；实跑 `--check` **退出码 0**：quantity 36 / stopwords 18 / structure_markers 12 / time_words 19 / verbs 165，全部 PASS、errors=0、auto_ready=0 | 双轨（`*_source.md|json` → `<name>.json`）；auto_ready=0 批量门控生效 |

### 3.2 C1-C24 移植/改造（文件 18/24；✅15、◐2、❌7）

| 节点 | 计划脚本 | 实际文件/函数 | 状态 | 证据 | 备注 |
|---|---|---|---|---|---|
| C1 | lint_purple_numbers（+E7-E17） | `lint_purple_numbers.py`：`PurpleNumberLinter` L76、`main` L538 | ✅ | 实跑 `--book 白发魔女传 001` 退出码 0，E1-E17+AUX 全 0；源码 import symbols L30/config L29 | 全 32 回在 check 中亦 0 |
| C2 | lint_heading_numbers | `lint_heading_numbers.py`：`check_heading_numbers` L26、`main` L56 | ✅ | 实跑 `--book 白发魔女传`：32 文件、0 错误、退出码 0；import config L21 | — |
| C3 | lint_skills | `lint_skills.py`：`SkillLinter` L30、`main` L337 | ✅ | 实跑 `--all` 退出码 0（仅 WARN：规格型文档缺"快速开始"等，P4 已降级 warning）；import config L27 | 缺 `lint_scripts.py` 适配在 docs/19 仍挂账 |
| C4 | token_tracker | `token_tracker.py`：`TokenTracker` L42、`track_tokens` L274 | ✅ | `import token_tracker` 成功；`--help` 退出码 0 并跑示例函数（打印 Token 使用统计）；import config L25 | 库件，供 annotate/批次计费；计价表为占位待回填 |
| C5 | fix_halfwidth_quotes | `fix_halfwidth_quotes.py`：`fix_quotes_in_line` L25、`fix_file` L100 | ◐ | `--help` 退出码 0（`[--book] [target]`）；import config L22；**未实跑**（会原地写 tagged，受审计约束） | 码点状态机照搬；需一次 dry-run/副本验证 |
| C6 | find_candidate_entities | `find_candidate_entities.py`：`main` L222、`collect_candidates` L113、`write_outputs` L154 | ❌ | 实跑 `pipeline_wuxia 白发魔女传 candidates` **退出码 1**：`KeyError: '白发魔女传:001'` @ `find_candidate_entities.py:164`——`parse_chapter()` 的 chapter_id=`书:001`（L94-95）与 `file_by_id` 的 `f.stem`=`001.tagged`（L158）键不一致 | **移植 bug**：`--all/--book` 必崩，`logs/candidates/` 为空；一行可修（strip `.tagged.md`）但未修，按"不可用"计 |
| C7 | apply_annotation_patches | `apply_annotation_patches.py`：`type_to_symbol` L51、`apply_tsv_to_chapter` L179、`main` L235 | ◐ | `--help` 退出码 0（`--file/--dir --pattern --dry-run`）；import config L24/symbols L25；无 patch 输入（registry 无 patches 目录）故未实跑 | 保持"TSV 章节字段=文件 stem"约定 |
| C8 | section_extract | `section_extract.py`：`extract_sections_from_chapter` L43、`process_all_chapters` L68 | ✅ | 实跑 `python scripts/section_extract.py` 退出码 0，落 `registry/sections_data.json`；import config L26/symbols L27 | `##` 可选层工具（#4 已裁决降级保留） |
| C9 | lint_markdown（加符号） | `lint_markdown.py`：`MarkdownLinter` L62、`main` L287 | ✅ | check 中实跑退出码 0（64 文件，0 错误/0 警告/64 提示）；import symbols L27/config L26，类型正则由 `symbols.ALL_CODES+BRACKETS` 动态构建 | 对话动词表已扩白话（道/喝道/赞道…） |
| C10 | lint_symbol_conflicts（加符号） | `lint_symbol_conflicts.py`：`SymbolConflictLinter` L72、`main` L303 | ✅ | 实跑 `--book 白发魔女传`：**64 文件、0 问题**（半角/直角引号/标注内标点/Markdown/嵌套/跨标点/旧符号残留 7 类各 0），退出码 0；import config L30/symbols L31 | 旧符号残留检测已接 symbols.LEGACY_* |
| C11 | fix_nested_annotations | `fix_nested_annotations.py`：`fix_nested_annotations` L71、`main` L129 | ✅ | 实跑 `--book 白发魔女传 --dry-run`：修复文件 0/总数 0，退出码 0；import config L26/symbols L27 | 三层括号互不嵌套语义 |
| C12 | compute_annotation_coverage | `compute_annotation_coverage.py`：`analyze_chapter` L66、`main` L201 | ✅ | 实跑 `pipeline_wuxia coverage` 退出码 0：32 回、338,586 字、已标 96,020（28.36%），落 `logs/coverage/`；TYPE_LABELS=ENTITIES\|VERBS\|RHETORIC | 删硬编码基线、分书统计已落实 |
| C13 | generate_entity_stats_report | `generate_entity_stats_report.py`：`scan_book` L47、`main` L195 | ✅ | 实跑 `--book 白发魔女传` 退出码 0，写 `logs/entity_stats/实体标注统计报告_v261104.md`；import config L28/symbols L29 | `^` 统一为"专门概念"口径 |
| C14 | extract_yunwen | `extract_yunwen.py`：`extract_yunwen_blocks` L67、`main` L97 | ✅ | 实跑 `pipeline_wuxia yunwen` 退出码 0：36 篇、覆盖 32/32 回（词1/诗…/回末对31），落 `logs/yunwen/`；import config L28/symbols L29 | YUNWEN_TYPES 由 FENCE_FORMAL 动态构建 |
| C15 | tag_quantity_entities（外置词表） | `tag_quantity_entities.py`：`tag_line` L73、`main` L151 | ✅ | 实跑 `--book 白发魔女传 --chapter 001 --dry-run` 退出码 0：6 处/5 种表达（万里×2、三年、几年、一把、一斗）；import masker L29/symbols L28，消费 `wordlists/quantity.json` | docs/38 记录的 020-032 补标执行件 |
| C16 | tag_new_entity_types | **无文件** | ❌ | 全盘 glob（A/B 两目录）+ 内容检索：仅 docs 提及；shiji 源件存在（`shiji-kb/scripts/tag_new_entity_types.py`）但未移植 | 4 套内联词表未外置；武功/擒控/传授新类型未加 |
| C17 | tag_identity_kinship | **无文件** | ❌ | 同上；shiji 源 `tag_identity_words.py`/`tag_kinship_words.py` 均在但未合并移植 | 身份/亲属词表外置化缺失 |
| C18 | scan_untagged_aliases | **无文件** | ❌ | 同上；`analyze_annotation_gap.py` 只做"应标通名标注率"统计（L7），无 entity_index 重建/别名扫描 | 不等价 |
| C19 | infer_single_char_names | **无文件** | ❌ | 全库无 `single_char`/单字人名逻辑（仅 tag_quantity/wordlist_compiler 含"单字"字样，语义无关） | — |
| C20 | detect_entity_boundary_errors | **无文件** | ❌ | 无 `boundary`/边界错误检测实现（lint_symbol_conflicts 有 `SENTENCE_BOUNDARY_RE` L68，仅标点层） | 8 模式武侠动词表未迁移 |
| C21 | lint_text_integrity | `lint_text_integrity.py`：`strip_markup` L117、`check_chapter` L242、`main` L297 | ✅ | check 中实跑退出码 0（32 回 0 差异）；import config L32/symbols L33；白名单机制 L38-46（文件缺失=空表，非缺陷） | 多书+`^:::.*$` 剥离规则已接 |
| C22 | lint_fence_format（原 lint_zan_format） | `lint_fence_format.py`：`check_fence` L98、`main` L145 | ✅ | check 中实跑退出码 0：64 文件全部围栏格式通过；import config L24/symbols L25；按 `FENCE_LINE_RULES` 查规则（非"每行8字"） | 改名与 D04 规则表已落实 |
| C23 | extract_paragraph_structure | `extract_paragraph_structure.py`：`extract_paragraph_structure` L38、`infer_relations` L160 | ✅ | 实跑 `pipeline_wuxia para-structure` 退出码 0：32 回·2231 段落·64 围栏·59 关系 → `registry/structure/白发魔女传/` | fence 类型驱动，史記'帝/太史公曰'规则已删 |
| C24 | build_entity_concordance | **无文件** | ❌ | 全盘无 `concordance`/实体对照实现；shiji 源件存在但未移植 | **且 docs/17 §四波次表未给 C24 排任何波次**（P1 只列 C21-C23），计划表本身遗漏 |

**C 清单完整性核对（docs/05 §2.8，30 脚本 = 25 可移植 + lint_halfwidth_punct 暂缓 + 4 裁撤）**

| §2.8 脚本 | 判定 | docs/17 节点 | 状态 |
|---|---|---|---|
| lint_purple_numbers / lint_heading_numbers / lint_skills / token_tracker / fix_halfwidth_quotes / find_candidate_entities / apply_annotation_patches / section_extract | 直接移植 8 | C1-C8 | C6 ❌，C5/C7 ◐，其余 ✅ |
| lint_markdown / lint_symbol_conflicts / fix_nested_annotations / compute_annotation_coverage / generate_entity_stats_report / extract_yunwen / tag_quantity_entities | 加符号 7 | C9-C15 | ✅ |
| tag_new_entity_types / tag_identity_words+tag_kinship_words（合并）/ scan_untagged_aliases / infer_single_char_names / detect_entity_boundary_errors / lint_text_integrity / lint_zan_format（改名）/ extract_paragraph_structure / build_entity_concordance | 领域改造 10（合并后 9） | C16-C24 | C16-C20、C24 ❌；C21-C23 ✅ |
| lint_halfwidth_punct（暂缓）、generate_pn_mapping、build_complete_pn_mapping、analyze_tagged、analyze_error_patterns（裁撤 4） | 不进图 | — | 无需实现 |

**结论：C 清单对 §2.8 无"脚本级漏项"**——25 个可移植脚本全部有节点承接（identity+kinship 合并为 C17、zan→fence 改名 C22）。但 docs/17 自身件数口径矛盾：§2.2 标"22 件"而实列 **24 个节点**；§一.2 写"22 移植+5 裁撤+1 暂缓"与 §2.8 实表"25 可移植+4 裁撤+1 暂缓"不符（应为 24 节点）。属文档计数瑕疵，非清单漏项（详见 ⑦）。

### 3.3 N1-N11（2/11）

| 节点 | 计划脚本/功能 | 实际文件 | 状态 | 证据 | 备注 |
|---|---|---|---|---|---|
| N1 | generate_pn_wuxia（PN 生成） | `generate_pn_wuxia.py`：`process_chapter` L163、`main` L371 | ✅ | `--help` 退出码 0；`tagged/白发魔女传/*.struct.md` **32/32 齐**；复算 struct 内 `[N]` 令牌 = **2295 = 2263 内容 PN + 32 个回目 [0]**，与 docs/17 §七"2263 PN 全 pass"一致；围栏行 128=64 个围栏；import config L31/symbols L32 | 未重跑 structure（会覆写 struct 文件），以产物清点+计数为证 |
| N2 | detect_verse_wuxia（词牌/对联检测） | `detect_verse_wuxia.py`：`detect_block` L371、`scan_book` L482、`main` L576 | ✅ | 实跑 `--book 白发魔女传 --scan --chapter 1` 退出码 0：候选 3 行（成立 3/存疑 0）；历史全书报告 `logs/verse_scan/白发魔女传_scan_001-032.md` 存在；import config L28/symbols L29 | 全书 78 候选（58 成立/20 存疑）为 docs/17 记录值 |
| N3 | validate_verb_tagging_wuxia（六域白名单+消歧+嵌套+密度） | **无文件** | ❌ | 无 `validate_verb` 实现；`qa_annotation_report.py` 仅统计 V 密度/分布（`VERB_ORDER` L36），不做白名单/消歧校验 | 最接近的替代件也不等价 |
| N4 | time_resolver_wuxia（时点键/单调性） | **无文件** | ❌ | 无 `time_resolver`；`annotate_chapter_llm` 只在管道层限制 `%|时点/时长/年龄`（L277），无锚点解析/单调性校验 | — |
| N5 | relation_validator（联动核验→入表） | **无文件** | ❌ | 无 `relation_validator`；父目录 `build_relation_table.py` 只消费人工 TSV，无 27 行联动×语义角色核验 | — |
| N6 | merge_crossover（跨书归并工作台） | **无文件** | ❌ | 无 `merge_crossover`；`build_series_tree.py` 仅系列谱系考订+挂证 | — |
| N7 | gazetteer_migrate（650 条无损迁移） | **无文件** | ❌ | 无 `gazetteer_migrate`；父件 `build_gazetteer.py` 为既有工具（`kb/gazetteer.json` 现 650 条、字段 real/kind，无 D10 nature 四值/M01-M13） | 先有数据、无迁移脚本 |
| N8 | lint_consistency（34 条种子规则） | **无文件** | ❌ | 无 `lint_consistency`；父件 `build_audit.py` 只实现 R1 死亡一致性（L5-6、L69），R2/R3 明标挂账 | META-10 中该脚本标"待建"，非失效引用 |
| N9 | lint_taxonomy（分类树校验） | **无文件** | ❌ | 无 `lint_taxonomy`；分类树仅设计稿 `skills/SKILL_分类树五件套_武侠版.md` | — |
| N10 | build_sku_cards（五卡） | **无文件** | ❌ | 无 `build_sku_cards`；仅有 D12 设计稿 | 最下游，依赖 N4/N5/N6/N7 |
| N11 | update_intertext_loc（loc→loc_r） | **无文件** | ❌ | 无 `update_intertext_loc`；`kb/互文引用表.json` 条目键实测为 `kind/loc/probe/snippet/source/target`——**无 `loc_r` 字段** | N11 与 E11 共用同一缺口 |

### 3.4 E1-E11 一览（详见 ⑤；0 完全对接 / 4 部分 / 7 未对接）

| 节点 | 对象 | 结论 |
|---|---|---|
| E1 | pipeline.py 阶段注册表纳新 | ◐（本体未改，另有新编排器 `pipeline_wuxia.py` 旁路实现 12 机械阶段+check） |
| E2 | lint_annotation.py 类型白名单 | ❌（仍 04f 旧码 L22-23） |
| E3 | repair_tags.py 修复规则表 | ❌（旧码 L20/L34） |
| E4 | build_entity_registry 别名列/双层 canonical | ◐（有别名链，无 D06 别名列扩展/D07 双层 canonical+book/series） |
| E5 | build_event_table（D03 字段总表） | ❌（旧 5 码+旧 schema） |
| E6 | build_moves/arts_data/artifacts（D09 统一 Schema） | ❌（各自 v1/v2 旧骨架） |
| E7 | build_graph（D06 谓词总表） | ❌（7 类固定边） |
| E8 | build_atlas_slices/build_gazetteer（D10 双图层+nature） | ◐（real/kind+虚构不发坐标已有，无 nature 四值） |
| E9 | build_ratings（D03 outcome 五值） | ❌（win/draw/loss 三值） |
| E10 | build_audit（N8 报告格式） | ❌（仅 R1） |
| E11 | build_series_tree（锚点升级 loc_r） | ◐（strong/ok/todo 已一致，锚点仍 `loc`） |

---

## ④ 实跑结果（不调 LLM；tagged 正文未改）

环境：Python 3.13.5、`PYTHONIOENCODING=utf-8`；原始输出全文见 `docs/_audit/scripts-run.log`。**LLM 相关脚本（annotate_llm / annotate_chapter_llm / annotate_rhetoric_llm / qwen_review_chapter）一律未运行**，仅做 `--help` 校验。

| # | 命令 | 退出码 | 关键输出/结论 |
|---|---|---:|---|
| 1 | `python scripts/wordlist_compiler.py --check` | 0 | 5 表全 PASS：quantity 36 / stopwords 18 / structure_markers 12 / time_words 19 / verbs 165；errors=0、auto_ready=0 |
| 2 | `python scripts/pipeline_wuxia.py 白发魔女传 status` | 0 | struct 32/32、tagged 32/32；slug=未定、指纹=已锁定 |
| 3 | `python scripts/pipeline_wuxia.py 白发魔女传 check` | 0 | **五门 lint 全过**：lint-pn=0 integrity=0 symbol-lint=0 md-lint=0 fence-format=0（64 文件；md-lint 0 错误/0 警告/64 提示） |
| 4 | `python scripts/lint_purple_numbers.py --book 白发魔女传 001` | 0 | E1-E17+AUX 全 0；"所有文件的检查通过" |
| 5 | `python scripts/lint_symbol_conflicts.py --book 白发魔女传` | 0 | 64 文件、0 问题（7 类检查各 0，含"旧符号残留（史记体系）0"） |
| 6 | `python scripts/lint_heading_numbers.py --book 白发魔女传` | 0 | 32 文件、0 错误 |
| 7 | `python scripts/lint_skills.py --all` | 0 | 仅 WARN（规格型文档缺"快速开始"等，迁移期已降级） |
| 8 | `python scripts/pipeline_wuxia.py 白发魔女传 coverage` | 0 | 32 回 / 338,586 字 / 已标 96,020 / **28.36%**；写 `logs/coverage/` |
| 9 | `python scripts/pipeline_wuxia.py 白发魔女传 para-structure` | 0 | 32 回·2231 段落·64 围栏·59 关系 → `registry/structure/白发魔女传/` |
| 10 | `python scripts/pipeline_wuxia.py 白发魔女传 yunwen` | 0 | 36 篇韵文·覆盖 32/32 回 → `logs/yunwen/` |
| 11 | `python scripts/pipeline_wuxia.py 白发魔女传 candidates` | **1** | **C6 阻塞 bug**：`KeyError: '白发魔女传:001'` @ `find_candidate_entities.py:164`（`file_by_id` 用 `f.stem` 未剥 `.tagged.md`，与 `chapter_id` 不一致）；`logs/candidates/` 为空 |
| 12 | `python scripts/section_extract.py` | 0 | 落 `registry/sections_data.json` |
| 13 | `python scripts/generate_entity_stats_report.py --book 白发魔女传` | 0 | 写 `logs/entity_stats/实体标注统计报告_v261104.md` |
| 14 | `python scripts/fix_nested_annotations.py --book 白发魔女传 --dry-run` | 0 | 修复 0 文件/0 处（语料无嵌套） |
| 15 | `python scripts/tag_quantity_entities.py --book 白发魔女传 --chapter 001 --dry-run` | 0 | 6 处/5 种表达（万里×2、三年、几年、一把、一斗） |
| 16 | `python scripts/detect_verse_wuxia.py --book 白发魔女传 --scan --chapter 1` | 0 | 候选 3 行（成立 3/存疑 0）→ `logs/verse_scan/白发魔女传_scan_001-001.md` |
| 17 | `python -c "import token_tracker, masker, api_config, config, symbols"` | 0 | `imports OK` |
| 18 | `python -m py_compile`（A+B 全部 81 个 .py，逐个） | 0 | **total=81 fail=0**（pycache 重定向到 `docs/_audit/pycache`，未污染 scripts） |
| 19 | 11 个脚本 `--help`（C5/C7/generate_pn/annotate_chapter 等） | 全部 0 | CLI 参数面可用；annotate_* 仅 help，未触 API |
| 20 | 费用/产物对账脚本（只读 `logs/token_usage`） | 0 | 020-032 共 13 个 annotate usage JSON；`cost_usd` 合计 **0.648257** + rhetoric **0.002881** = **0.651138**，与 `logs/annotate_cost_summary.md` 合计行及 docs/38 §四一致；字数合计 165,275 一致 |

**写入说明**：本轮仅产生阶段产物/日志（`logs/coverage`、`logs/yunwen`、`logs/entity_stats`、`logs/verse_scan/白发魔女传_scan_001-001.md`、`registry/structure/`、`registry/sections_data.json`）与审计日志，未改任何 `tagged/` 文件。

---

## ⑤ E 组对接现状（父目录 `Wuxiaxiaoshuo/scripts/`，44 .py）

**全局判据（决定性证据）**：
- 对父目录全部 44 个 .py grep `symbols|wuxia-kb|import config` → **零命中**：E 组没有任何脚本 import `wuxia-kb/scripts/symbols.py` 或 `config.py`。
- 仍使用旧符号 `◉◈○▲◇` 的文件（grep `-List`）：`lint_annotation.py`、`repair_tags.py`、`build_entity_registry.py`、`diff_detail.py`、`fix_016b.py`。
- 旧数据层仍在跑：`kb/tagged/白发魔女传/` 32 个 `NNN_第一回.tagged.md`；抽样 001 回旧码计数 ◉7/◈11/○2/▲3（`⟦` 括号已在用但内部仍是旧码）；`kb/白发魔女传/实体登记表.json` meta.schema=`wuxia-tagged-v0.2`；`事件表.json` meta.schema=`wuxia-tagged-v0.1`。

| 节点 | 对接点 | 现状与证据（行号） | 判定 |
|---|---|---|---|
| E1 | pipeline.py 阶段注册表纳新；LLM 规范指针升级 | `pipeline.py:47-48` STAGES 仍为旧 11 机械阶段（status/diff/repair/lint/registry/events/contexts/apply-curation/drop-review/rel-candidates/rel-table），无 C21/C1/N1/N3/N4；`pipeline.py:60-62` 仍拼 `章回版/`、`kb/tagged` 旧路径；`pipeline.py:21` 规范仍= `kb/<书>/标注规范-v0.md`；`pipeline.py:13` 校订文件仍 `核心-◉▲○◇.txt`。**旁路替代**：`wuxia-kb/scripts/pipeline_wuxia.py:71-78` 已实现 12 机械阶段+check 完成门（且不短路），LLM 契约指向 SKILL_03a/04f；但该件无 repair/diff/registry/events/rel 链，且不是 E1 本体改造 | ◐ |
| E2 | lint_annotation.py 类型白名单接 C0b | `lint_annotation.py:22` `ENTITY_CODES = set("@=◆;%☆•+[§")`（04f/v0.2 旧码，缺 # ~ { ^ & ◎ 等）；`:23` `VERB_CODES = set("◉◈○▲◇")`（旧 5 码，非新 6 域 ⊞⊠⊡⊟▣■）；`:26` PAIRS/`:27` MARK_RE 亦本地内联 | ❌ |
| E3 | repair_tags.py 修复规则表接 C0b | `repair_tags.py:20` `⟦([◉◈○▲◇]…)〗`；`:34` `⟦([◉◈○▲◇]…)（〖）`——两处硬编码旧码，无 symbols import | ❌ |
| E4 | build_entity_registry 对接 D06 别名列+D07 双层 canonical | `build_entity_registry.py:9` verb_anchors 仍 `◉◈○▲◇`；`:21-22` 仍读 `kb/tagged`；`:152-155` 实体 schema=`type/canonical/aliases/count/chapters/locators`（无 book/series 跨书列、无双层 canonical）；`:206` meta.schema=`wuxia-tagged-v0.2`。已有别名链（`resolve_root` L77、MANUAL_MERGES L35）属部分能力 | ◐ |
| E5 | build_event_table 对接 D03 事件字段总表 | `build_event_table.py:9`/`:35` `VERB_NAME={'◉':'杀伐','◈':'交战','○':'拜认结盟','▲':'擒控','◇':'传艺'}`（旧 5 码）；`:199-205` 事件字段仅 loc/verb_code/verb/mode/in_quote/subject/object/confidence/excerpt（无 D03 13 类+36 字段+五状态）；`:227` schema=`wuxia-tagged-v0.2` | ❌ |
| E6 | build_moves/arts_data/artifacts 按 D09 统一 Schema 迁移 | `build_moves.py:2-5` "v2 · 纯解析结果"，产出 `kb/招式表.json`（功法/招式两级自有骨架）；`build_arts_data.py:2-11` 从各书 `关系表.json` 聚合 arts.json（别名=关系表 art_aliases）；`build_artifacts.py:2-5` "v1"，产出 `kb/神兵表.json`+`weapons.json`。父目录 grep `wordlists|schema_version` **零命中**——未接 D09 八字段统一 Schema/词表双轨 | ❌ |
| E7 | build_graph 关系边对接 D06 谓词总表 | `build_graph.py:5-7` 边类型固定 7 种（对局/师承/救助/传授/修习/独门/拥有/镇山），`:97` 对局边、`:21-23` 硬编码 CURATED_HELP；无 55 谓词总表/双树 | ❌ |
| E8 | build_atlas_slices/build_gazetteer 对接 D10 双图层+nature | `build_gazetteer.py:14` "虚构地名不发布经纬度，只发布 锚点+方位+距离"（双图层精神已有），`:26` GAZ_KB=`kb/gazetteer.json`；`build_atlas_slices.py:9` 消费 `real/缺坐标`，`:108` schema=`atlas-slice-v1`。数据实测 keys=`aliases/books/count/id/kind/lat/lng/name/precision/real/source/status/verified`——**无 `nature` 字段**，无 M01-M13 迁移映射 | ◐ |
| E9 | build_ratings 对接 D03 outcome 五值 | `build_ratings.py:93` `s_a={'win':1.0,'draw':0.5,'loss':0.0}[m['outcome']]`；`:165` 同判；`:218` 输出"胜/平/负"。`site/data/matches.json`（484 场）实测 outcome 仅 `{draw:175, win:163, loss:146}`——三值，非 D03 五值+参照方 | ❌ |
| E10 | build_audit 对接 N8 报告格式 | `build_audit.py:5-6` 仅规则 R1 死亡一致性，R2/R3 明标"待工具 A/C 接入（挂账）"；`:69` payload rules=`['R1 死亡一致性']`，schema=`audit-v0` | ❌ |
| E11 | build_series_tree 锚点升级 loc_r | `build_series_tree.py:25` conf=strong/ok/todo 与 D07 图例一致（唯一已对齐处）；`:188-195` `load_evidence()` 读 `kb/互文引用表.json` 的 `e['loc']`，`:214` 输出 `loc: f"{src}·{loc}"`；`kb/互文引用表.json` 条目实测无 `loc_r` 键 | ◐ |

**E 组小结**：0/11 完全对接；4 个部分（E1/E4/E8/E11 各只具备旧实现中与本节点部分同构的能力）；7 个完全未动（E2/E3/E5/E6/E7/E9/E10）。父目录脚本仍完整消费旧 `kb/` 资产（32 回旧码 tagged、650 条 gazetteer、互文表无 loc_r、三值 matches），新 `wuxia-kb/` 与旧站点管线目前是**两套并行体系**，尚未合流。

---

## ⑥ 计划外已实现脚本（13 个，均不在 docs/17 §2.1-2.4 节点表）

| 脚本 | 用途 | 关联文档/证据 |
|---|---|---|
| `annotate_llm.py` | LLM 标注运行器：分块→保真门≥0.98→difflib 回锚→拼装→剥标完整性校验；主模式单遍（`--prompt`=SKILL_03a §二），A1/A2 两遍为 fallback | `pipeline_wuxia.py:37` 契约；`scripts/README.md:44` |
| `annotate_chapter_llm.py` | 章回标注执行器：两遍（P1 首标+P2 自检补标）+回锚+修辞层+逐回计费；docs/38 的 020-032 回执行件 | `docs/38` §二；`--book/--chapter/--mapping-file` |
| `annotate_rhetoric_llm.py` | 修辞层补标：`wordlists/rhetoric.json` 精确匹配候选 + deepseek 逐处裁决，落 `〘※…〙` | docs/35、docs/37；`logs/token_usage/rhetoric_*` |
| `qa_annotation_report.py` | 标注质量自检：A 结构（剥标对账/类型码/嵌套）、B 管道审计、C 密度分布、D 空标段 | docs/38 §5；`--chapters` |
| `analyze_annotation_gap.py` | 标注缺口分析：15 类+6 域密度缺口分解、"应标通名"（#/= /•）裸文标注率、口径噪声 | docs/39；只读语料不调 LLM |
| `compare_annotation_gold.py` | 同回新标注 vs 金标准逐令牌对账（exact/partial/conflict/gold_only/new_only，plain 坐标） | `docs/40`；`--gold --new` |
| `qwen_review_chapter.py` | 外部模型复核器（Qwen3.8-Flash-Next / AMD API）评审金标准 vs 新标注（**付费外部 API，本轮未跑**） | `docs/41` |
| `summarize_annotate_cost.py` | 逐回标注费用汇总：读 `logs/token_usage/annotate_*.json` 取每回最新，输出控制台+markdown | 生成 `logs/annotate_cost_summary.md`（已对账） |
| `build_03a_fewshot.py` | SKILL_03a few-shot 注入器/构建器 v2：种子→注入→断言→哈希回填版本锁定；种子修订后须重跑 | docs/24；`scripts/README.md:46` |
| `fix_annotation_mechanical.py` | 标注产物机械修复：标点外置、管道归一、闭括号、层-码错位归一；剥标对账 | docs/38 §二（缺陷修复 #3/#4） |
| `xval_analyze.py` | GLM vs deepseek 实体/动词标注一致性 + 旧人工种子对照；输出 `tagged/_xval/xval_report.md` | docs/19 §1.5；`scripts/README.md:45` |
| `api_config.py` | API 凭据加载器：env `WUXIA_API_*` 优先 → 根 `.api_config.json`（已 gitignore），密钥不入源码 | `scripts/README.md` 约定 7；P1 修复 2026-11-03 |
| `pipeline_wuxia.py` | 新管线编排器：12 机械阶段（structure→…→candidates）+`check` 完成门（五门 lint 不短路）+2 个 LLM 契约占位（annotate/review） | `docs/17` §七已登记；`config` import L68 |

> `scripts/_oneshot/`（5 个 `_tmp_gen_*.py`）为设计稿双稿一次生成器，属历史存档，不计入计划/计划外管线件。

---

## ⑦ 失效 / 过时引用（重扫结果）

对 `skills/*.md` + `wuxia-kb/scripts/*.py` 重扫脚本与词表引用（37 个 `scripts/*.py` 引用、wordlists 引用）：

| # | 引用 | 现状 | 严重度/结论 |
|---|---|---|---|
| 1 | `config.py:28-29` `SHIJI_SCRIPTS` 指向 `shiji-kb/scripts` | 全库仅此定义、零使用（grep 确认） | 死常量，docs/27 §7.1 已挂"待用户确认清除"，仍在 |
| 2 | `skills/META-10_质量控制_武侠版.md:81/197/230` → `scripts/lint_consistency.py` | 文件不存在 | **已声明"待建"**（N8），属计划缺口而非失效引用；但 META 执行清单里是可直接复制的命令，建议标 TODO |
| 3 | `skills/SKILL_04f_动词标注.md:735` → `wordlists/verbs_source.md` | 实际文件为 `wordlists/verbs_source.json`（编译器两者都收，程序不报错） | 文档命名漂移，低危 |
| 4 | `skills/SKILL_02k_成语识别_武侠版.md:32/57/71/156/188/251` → `wordlists/chengyu_source.md`、`chengyu.json` | 两文件均不存在 | SKILL 同页 §八已标"规划"，属待建词表（P2/WL），但 `--name chengyu` 命令当前会报"未找到源" |
| 5 | `lint_purple_numbers.py:43/652` → `registry/observe_fences.json` | 文件不存在（仅 L652 提示语，不参与加载） | 功能不阻塞；E9 观察类登记目录待建 |
| 6 | `lint_text_integrity.py:38/45-46` → `scripts/lint_whitelist.txt` | 不存在，但 `_load_whitelist()` 显式处理"文件缺失=空表" | 设计如此，非缺陷 |
| 7 | `lint_fence_format.py` 头注"移植自 `shiji-kb/scripts/lint_zan_format.py`" | 源件在 shiji-kb（未在本库预期） | 历史溯源说明，非失效引用 |
| 8 | `scripts/README.md` | 仍写"P1 进行中"、词表只列 4 表（漏 quantity 36 条）、structure_markers 记 10 条（实际 12 条）、辅助工具仅列 4 件（未列 2026-11-04 的 annotate_chapter/qa/compare 等） | **目录级文档已过时**，建议随本轮审计更新 |
| 9 | `docs/17` §七进度 | 最后更新停在 2026-11-03（P0-P1），未反映 docs/38 的 020-032 回机器标注与新增 13 个脚本；`docs/19` 亦同日截止 | 文档漂移（不影响脚本可用性），"P2 入口"描述已过时 |
| 10 | `docs/17` §2.2 "22 件" vs 实列 C1-C24=24 节点；§一.2 "22 移植+5 裁撤+1 暂缓" vs §2.8 "25 可移植+4 裁撤+1 暂缓" | 计数自相矛盾 | 文档缺陷（清单本身完整） |
| 11 | `docs/17` §四波次表 | **C24 未列入任何波次**（P1 仅 C21/C22/C23；P2/P4/P5 均无 C24） | 计划遗漏，需补行 |
| 12 | `docs/38` §5.1 "全 32 回、52 文件" | 当前 check 为 64 文件（32 struct + 32 tagged） | 非错误：52 是执行当时（020-032 落盘前）的状态，后续回增加导致；docs/38 数据本身与文件系统一致 |

**docs/27 §7.1 "活跃脚本引用零缺失"复核**：在其自述口径（fewshot/registry/annotate×2）**仍成立**——`skill_03a` 版本锁定 manifest、`registry/entities.json`、`annotate_llm`/`annotate_chapter_llm` 引用均可解析；`logs/mapping_frozen_20261104.json` 存在。全库范围的唯一"缺文件"引用是已声明待建的 `lint_consistency.py`（N8）+ 规划中的 chengyu 词表，不构成新失效。

**docs/38 "13 回产物 + 五门 lint 全绿"复核（与文件系统一致）**：
- `tagged/白发魔女传/` 实测 **32 个 `.tagged.md` + 32 个 `.struct.md`**，020-032 **13 回齐**；
- `logs/annotate/` 有 **020-032 共 13 个 `NNN.report.txt`**（另 001/019 报告）；`logs/token_usage/` 有 020-032 共 13 个 `annotate_白发魔女传_NNN_*.json`；
- `logs/annotate_cost_summary.md` 合计 = 0.651138 USD / 165,275 字 / E 9,887 / V 2,348 / R 36 / API 338 次，与 docs/38 §三/§四数字**逐项一致**；用 usage JSON 复算 annotate 0.648257+rhetoric 0.002881=0.651138 一致；
- `logs/coverage/汉字标注覆盖率统计报告_20261104.md`：32 回、338,586 字、96,020 已标、28.36%，与 docs/38 一致；
- 本轮重跑 `pipeline_wuxia 白发魔女传 check` **五门 lint 退出码全 0**（与 docs/38 §5.1 一致）；`logs/check_full_20261104.log` 亦记录五门全绿。
- 唯一"降级项"：docs/38 自述交付状态是 `structurally_valid`，**语义验收 `accepted` 未做**（需人工/强模型复核），不属脚本缺口但应在"产物可用"口径中注明。

---

## ⑧ 缺口清单（按 docs/17 波次；"全部实现"还差什么）

| 波次 | 计划内容 | 已完成 | 仍缺（按节点） |
|---|---|---|---|
| P0 地基 | C0a-C0d + WL0 + META 第一波 | C0a-d ✅（wordlists 5 表 check PASS） | 无脚本缺口；`config.slug` 待 G0 回填、`SHIJI_SCRIPTS` 死常量待清 |
| P1 校勘结构 | C1-C15、C21/C22/C23、N1/N2、E1-E3 | C1-C4/C8-C15 ✅、C5/C7 ◐、C21-C23 ✅、N1/N2 ✅ | **C6（阻塞 bug 修复）**、**E2、E3**（E1 本体未改，仅旁路覆盖）；**C24 无波次归属**（计划表漏排） |
| P2 实体层 | C16/C17/C15、C18/C19/C20、N3 | 仅 C15（P1 已做，P2 复用） | **C16、C17、C18、C19、C20、N3**（6 个） |
| P3 试点标注 | N4、N5 | 标注语料 32/32 回已产（旁路 LLM 链，docs/38） | **N4 time_resolver、N5 relation_validator**（2 个） |
| P4 反思跨书 | N6、N11、N7、N8、N9 | 无 | **N6、N7、N8、N9、N11**（5 个；N11 与 E11 共用 loc_r 缺口） |
| P5 应用发布 | N10、E4-E11 | 无 | **N10**；**E4-E11 全部未完成对接**（0 完全，E4/E8/E11 部分；E5/E6/E7/E9/E10 未动） |
| P6 上线回填 | M 组，无脚本 | — | — |

**"全部实现"差额汇总**：50 个计划节点中
- 有运行证据的完全实现 21（C0×4、C×15、N×2、E×0）；
- 部分/未完全验证 6：C5、C7（有文件、仅静态+CLI，未实跑），E1/E4/E8/E11（旧件部分同构，未真正对接）；
- 完全缺失或不可用 23：**C6（有文件但实跑崩）、C16、C17、C18、C19、C20、C24（7 个 C）、N3、N4、N5、N6、N7、N8、N9、N10、N11（9 个 N）、E2、E3、E5、E6、E7、E9、E10（7 个 E）**。
- 按波次一句话：**P0-P1 基本收口（仅 C6 bug + E2/E3 + C24 排期）；P2 起（实体层、关系/时间、跨书、质量引擎、SKU、site 对接）整体未开工**——现有 020-032 回标注是绕开 P2-P5 的 LLM 旁路产物，不能替代 N3-N11 与 E 组。
- 另需注意：C6 的 bug 修复量极小（`find_candidate_entities.py:158` 键改 `f.name[:-len(".tagged.md")]`），但 `candidates` 阶段当前不可用；C24 需先补波次再实现。

---

### 附：复现方式

```
cd "C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb"
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPYCACHEPREFIX="$PWD\docs\_audit\pycache"
python -m py_compile scripts\*.py   # 逐个编译；本审计用脚本批量执行 81 件
python scripts\wordlist_compiler.py --check
python scripts\pipeline_wuxia.py 白发魔女传 check
python scripts\pipeline_wuxia.py 白发魔女传 status
```
（完整命令与逐条退出码见 `docs/_audit/scripts-run.log`；本报告所有 ✅ 均有对应文件行号或上述命令之一。）

*审计边界：未运行任何 LLM API；未改源码；未改 tagged 正文；E 组父目录脚本未执行（数据在旧 kb/ 体系，仅做源码与 schema 静态判定）。*
