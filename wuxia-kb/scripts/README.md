# scripts/ · KB 管线脚本目录

> 承 docs/17 拓扑排序；所有新脚本落本目录，词表数据落 `../wordlists/`。
> **终版口径快照（docs/66，2026-11-05 23:5x）**：`scripts/*.py` **87 个**（`_oneshot/` 26 另计）；registry 425 / SKU 1,501；5 书 judgment **153**、warnings **0/0/0/0/0**；搜索 **1,443** 条；content 引文 1,495 页/2,194 条（31 pending）；release GO `release_20261105_220127`、发布包 `wuxia-atlas-20261105_220331.zip`（9,126,782B/3,002 文件、sha `6bf4e9ae8411fa3d…`）。下方批次记录中的 45/79/85/263/1,451/1,326/2,007/e67e 等为历史时点，冲突时以 docs/66 §一为准。

## 地基模块（C0，最先落地，全脚本依赖）

| 模块 | 职责 | 关键 API |
|---|---|---|
| `config.py`（C0a） | 多书注册表与路径唯一来源；34 部书自动发现 | `books()/book_names()/chapter_path(书,回)/tagged_path(书,回)/DIR_*` |
| `symbols.py`（C0b） | 统一符号表（15 实体+6 动词域+围栏 10 类+PN/锚点/三档枚举）——**全脚本 import，禁本地字符类** | `ENTITIES/VERBS/FENCE_ALL/TOKEN_RE/parse_token()/strip_markup()/fence_opens()` |
| `masker.py`（C0c） | 词表驱动的候选召回与等长掩码 | `load_wordlist()/find_candidates()/mask_text()` |
| `wordlist_compiler.py`（C0d） | 双轨编译：`../wordlists/*_source.(md\|json)` → `<name>.json`；`--all/--name/--check` | tier=auto 且 status=已核准 才计入 auto_ready（批量前置） |

## 约定

1. **路径**：一律 `import config`，禁止脚本内拼相对路径（shiji 债：三种写死风格）。
2. **符号**：一律 `import symbols`（shiji 债：15 处字符类互相矛盾）。
3. **词表**：一律经 `masker` 消费编译产物；词表是数据不是代码。
4. **产物目录**：标注→`../tagged/`；登记→`../registry/`；日志→`../logs/`。
5. **批量纪律**：任何 auto 批量补标前备份、计数只增不减、剥标还原零差异（04f1 V0 红线）。
6. **编码**：Windows 控制台输出用 `io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')`。
7. **密钥**：一律经 `api_config` 加载（env `WUXIA_API_*` 优先，其次 `../.api_config.json`，
   已被 `.gitignore` 排除）；禁止硬编码入源码（P1 修复 2026-11-03）。

## 词表状态（2026-11-04 P2 后复核）

**8 个源**：`quantity_source.md`、`stopwords_source.md`、`structure_markers_source.md`、`time_words_source.md`、`verbs_source.json`、`new_entity_types_source.md`、`identity_source.md`、`kinship_source.md`（双轨源，经 `wordlist_compiler.py` 编译）。

**10 张词表**（其中 8 张为人工源编译产物；`rhetoric` / `fossil_verb_objects` 为手工维护、无 `_source`）：

| 词表 | 条数 | 说明 |
|---|---|---|
| `verbs` | 165 | ← SKILL_04f §5.2 程序化抽取；全部 status=待审（试点期只召回禁批量）；单字词已降 watch/complements |
| `structure_markers` | 12 | ← 02ab §6.2 套语分级；G0 普查回填"花开两朵/不在话下/有诗为证"（10→12）；词族为模板语法（`欲[知/如]后事…`），masker 字面匹配不展开——模板展开属编译器 TODO |
| `stopwords` | 18 | 泛称黑名单（01g 负规则+实验实测）；已核准（告警用途无批量语义） |
| `time_words` | 19 | ← D05 §3.3 实测频次+白话双轨补充；全部 review（时间多义，禁批量） |
| `quantity` | 36 | ← Agent B 创建（`tag_quantity_entities` 复标用；单字量词误标已修，docs/38） |
| `rhetoric` | 49 | ← docs/35 的 53 条候选逐条核定后收录 49 条（`〘※〙` 修辞层词表） |
| `fossil_verb_objects` | 3 | ← docs/33 新建（化石动宾/固定搭配，动词域负例） |
| `new_entity_types`（P2·C16） | 268 | ← ☆115 武功招式 / •80 神兵器物 / {24 典籍秘籍 / ◆49 门派组织；tier 全 review\|watch、零 auto（docs/_p2/C16-C17-report.md） |
| `identity`（P2·C17） | 212 | ← `;` 职衔 80 / `#` 身份 132；tier review\|watch、零 auto |
| `kinship`（P2·C17） | 62 | ← `#` 身份 62；全 watch/weak；按 SKILL_03a D1 仅在领属/指称结构下建议 |

> 另有候选池 `rhetoric_candidates_v0.json`（53 条，docs/35 已逐条裁定，不计入 10 表）；`wordlists/` 共 19 文件 = 8 源 + 10 表（8 编译 + 2 手工）+ 1 候选池。
> 新增三表一律**只出建议、不 auto 批量**（`tier=review|watch`）：`tag_new_entity_types` / `tag_identity_kinship` 默认写 `registry/patches/*.tsv`，`--apply` 才写 tagged（带备份+剥标断言）。

## 波次对照（docs/17，2026-11-04 P2 后状态）

- **P0 ✅ 完成**：C0a-C0d 地基（本文档四模块）。
- **P1 ✅ 完成**：18 C 族（第 1 波移植 8 + 加符号 7 + 领域改造 C21/C22/C23 共 3）+ N1/N2 + `pipeline_wuxia.py`；**C6 崩溃已修**（`find_candidate_entities.py` 的 `file_by_id` 键剥 `.tagged.md`，Lead，2026-11-04）。
- **P2 脚本层 ✅ / SKILL 层部分**：C16-C20、C24、N3 全部落地（当时 45 个 .py（终版 87 个）中 P2 新增 8 个 + 3 张词表；C18-C20 默认只出建议/报告）；`S-03a` 已成稿（v1.8），P2 11 份 SKILL 已于 2026-11-05 全部成稿（docs/66）。
- **P3 ✅ 产物+验收**：32/32 回 tagged；020-032 机器初稿完成 **accepted 验收**（13/13 accepted、hard_errors 0，见 docs/43；judgment 处置见 docs/45）。
- **P3+ 换书首批 ✅（2026-11-05）**：《江湖三女侠》48/48 回新管线标注 → **accepted 48/48**（五门 lint 全 0、hard 0；E=36,255/V=8,799；$1.2147），见 docs/47；换书过程修复 2 处跨书 bug、新增 5 个一次性工具（见下）。
- **P4-P6 未启动**（反思跨书/应用发布/上线回填）。

## 辅助与试点工具（非阶段，2026-11-03 首登；2026-11-04 补登 8 个执行/复核脚本 + 编排器 + 8 个 P2 工具）

| 脚本 | 用途 | 定位 |
|---|---|---|
| `annotate_llm.py` | LLM 标注运行器：分块→保真门（≥0.98）→difflib 回锚→拼装→剥标完整性校验 | 主模式=单遍（SKILL_03a §二 SYSTEM_PROMPT，`--prompt`）；两遍 A1/A2 为困难章 fallback 与交叉校验协议（`--prompt-e/--prompt-v`，承 docs/24 裁定） |
| `annotate_chapter_llm.py` | 章回标注执行器（pipeline `annotate` 阶段的 API 量产件）：两遍标注→回锚保真（令牌锚回 struct 原文）→结构校验→修辞层→逐回计费 | 2026-11-04 新增；020-032 批实际使用（docs/38）；2026-11-05《江湖三女侠》48 回量产（docs/47） |
| `annotate_rhetoric_llm.py` | 修辞层补标：`rhetoric.json` 精确候选索引 + LLM 逐处裁决（※/☆/skip）+ 机械插入 + 回读断言 + 花费聚合 | docs/37 执行（79/79 落标）；候选仅取正文、围栏/标题除外 |
| `pipeline_wuxia.py` | 阶段编排器：**14 个机械阶段**（含 P2 新增 `concordance`/`verb-validate`）+ `check` 完成门（五门 lint）+ `annotate/review` LLM 契约占位；多书阶段化驱动，路径一律经 config | 主入口；`status` 盘点产物 |
| `qa_annotation_report.py` | 标注质量自检报告：结构（剥标对账/令牌合法）、管道审计、分回密度与分布、空标/异常段 | 供 Lead 终验与文档引用（报告落 `logs/qa/`） |
| `analyze_annotation_gap.py` | 缺口分析器（不调 LLM）：按类密度缺口分解 + "应标通名"裸文标注率 + D1 旧口径噪音识别 | docs/39 全部数字的来源 |
| `compare_annotation_gold.py` | 逐令牌对账（新标注 vs 金标准）：exact/partial/conflict/gold_only/new_only + 逐类型 P/R + 管道一致性 | 回归/合理性分析（docs/40） |
| `fix_annotation_mechanical.py` | 机械修复（不调 LLM）：管道纪律归一/闭括号归一/非法令牌摘除/标点外置 + 剥标复验 | annotate 批次收尾；012-019 金标准修复用（docs/38 §5.4） |
| `qwen_review_chapter.py` | 外部模型复核器（Qwen3.8-Flash-Next/AMD）：输入 SKILL_03a v1.8 全文 + 两稿 + 机检摘要，输出 markdown 评审意见 | 结论须再用 `compare_annotation_gold.py` 程序化核验（docs/41） |
| `summarize_annotate_cost.py` | 逐回标注费用汇总：读 `logs/token_usage/annotate_*.json`（每回取最新），输出费用/密度表与合计 | 汇总落 `logs/annotate_cost_summary.md`（docs/38 §四） |
| `xval_analyze.py` | GLM vs deepseek vs 旧人工种子一致性分析（P2 试点实验件） | 读 `tagged/_xval/`，报告写回该目录 |
| `build_03a_fewshot.py` | SKILL_03a few-shot 注入器（G1 收口件；原 `tagged/_xval/_build_03a_fewshot.py` 迁入并接 config） | 种子修订后必须重跑（SKILL_03a §5.3 再生成纪律） |
| `tag_new_entity_types.py` | **P2·C16** 武侠新增实体类型补标建议：读 `new_entity_types.json`，掩码保护已标注，输出 C7 兼容 TSV | 默认只出 `registry/patches/*_new_entities.tsv`；`--apply` 可选（备份+剥标断言） |
| `tag_identity_kinship.py` | **P2·C17** 身份/亲属补标建议：identity+kinship 两表合并，保留 prefix/suffix 黑名单，kinship 按 D1 仅领属结构建议 | 同上，建议 TSV；`--apply` 可选 |
| `scan_untagged_aliases.py` | **P2·C18** 已知实体别名裸文扫描：从 registry 重建 entity_index，掩码后扫描，输出建议 TSV | 默认只出建议；`--apply` 可选：**按 TSV 位置精确插入 + 跳过令牌/围栏/标题保护区**（2026-11-05 P1 修复），`--selftest` 可回归 |
| `infer_single_char_names.py` | **P2·C19** 单字人名全名推断：同回多字名**末字**匹配（P1 修复移除首字）、唯一才映射、歧义/跨回冲突告警 | 默认报告 `logs/single_char_names/`；`--apply` 可选 |
| `detect_entity_boundary_errors.py` | **P2·C20** 实体边界体检：8 类模式（吞动词/粘语气/介词/职衔拆分/单字/标点/称谓/围栏），带 `--selftest` | 报告 `logs/boundary/` + 可选建议 TSV；`--strict` 有 error exit 1 |
| `build_entity_concordance.py` | **P2·C24** 实体对照表：32 回聚合（类型/规范名/变体/分回/首见锚点/登记对照），砍 wiki 依赖、15 类 PREFIX_LABELS | 产物 `registry/concordance/`；子集扫描自动加范围后缀 |
| `validate_verb_tagging_wuxia.py` | **P2·N3** 动词校验器：六域/闭合嵌套重叠/边界/消歧/密度/联动/域混淆；词表域冲突默认 warning（`--wordlist-strict` 恢复 error） | 产物 `logs/verb_validation/`；`--strict` 有 error exit 1；pipeline `verb-validate` 阶段 |
| `accept_batch.py` | **P3 验收器**：高风险 8 类全查 + 10% 确定性抽样 + 逐回状态机；报告全数据驱动（2026-11-05 P1 修复去硬编码）；`--llm` 仅预留接口 | 产物 `registry/acceptance/`、`logs/acceptance/`；docs/43 数据来源 |
| `qwen_review_files.py` | **外部复核器（通用文件评审）**：按 manifest 分组打包文件 → Qwen3.8-Flash-Next（AMD）评审；thinking 用 `chat_template_kwargs` 关闭；输出 md/json + 成本汇总 | 2026-11-04 新增；P2 复核见 docs/46，原始意见 `logs/qa/qwen_max_review/` |
| `_oneshot/` | 设计稿双稿生成一次性历史脚本（T02/T03/T04 等，prompts/README 登记） | 凭据已外部化（约定 7）；仅存档 |

### 换书批次工具与修复登记（2026-11-05，《江湖三女侠》48 回，docs/47）

| 工具 | 用途 | 说明 |
|---|---|---|
| `_oneshot/build_legacy_mapping.py` | 从旧标注 `kb/tagged/<书>/` 抽 @ 管道，按回累积生成《已核准映射表》快照（并行批次 `--mapping-file`） | 第 N 回快照=旧标注 1..N-1 回；单字显示串不收；产物 `logs/mapping_<书>/` |
| `_oneshot/compare_new_vs_legacy.py` | 新标注 vs 旧标注全局逐令牌对账（旧符号 `[→{`、`§→•`；剥标正文须一致） | 输出分回/分类型 P/R；docs/47 §4.3 数据来源 |
| `_oneshot/normalize_pipe_canonicals.py` | @ 管道规范名回填：以 `kb/<书>/实体登记表.json` canonical 为准，歧义 surface 不动，显示串==规范名则摘管道 | 只动管道元数据、剥标断言；默认 dry-run，`--apply` 备份 |
| `_oneshot/repair_tao_tokens.py` | 按验收 JSON 的 `tao_token` hard_errors 摘除回末套语段误标 | 剥标断言；备份 `logs/backup/` |
| `_oneshot/verify_batch.py` | 整批 tagged 复核（剥标==struct/段序/令牌合法）+ 逐回 E/V/R/字数统计 | 产物 `logs/qa/verify_batch_<书>.{md,json}` |
| `_oneshot/rebuild_tagged_from_struct.py` | 结构层重生成后按"内容行序列不变"把旧 tagged 令牌回灌到新 struct 骨架（PN 可重排；新增/改类围栏） | 逐段剥标断言；默认 dry-run，`--apply` 备份 `logs/backup/rebuild_tagged_<书>/` |
| `_oneshot/apply_judgment_a.py` / `apply_judgment_b.py` | judgment 裁决应用器（A：计划/否定+动词域风险；B：数量/时间/围栏+词表候选） | 按 (chapter,pn,display,occ) 定位、剥标断言、备份；`--dry-run` 默认；B 支持 `--allow-context-drift` |

### 登记层工具（2026-11-05，S-03b 前置，docs/48 §十，《七剑下天山》首用）

| 工具 | 用途 | 说明 |
|---|---|---|
| `propose_entity_registration.py` | scope（@◆&）内未登记实体 → `registry/patches/<书>_entity_registration.json` 提案（复用 concordance scan+aggregate） | aliases=变体(len≥2)、sources=回号、按次数降序；单字/括注不收；**不携带 id**；含楔子(000)扫描 |
| `apply_entity_registration.py` | 提案合并 → entities.json | 现读现写+二次去重+id 按 max+1 顺延（防并发冲突）+alias 并入+写前备份+唯一性断言；幂等可重放；默认 dry-run |

**修复登记（换书批次）**：
- `annotate_rhetoric_llm.build_candidates(chapters, items, book=PILOT_BOOK)`：原来写死 `白发魔女传`，换书会把别书 tagged 当候选源并把别书正文写回本书产物；已加 `book` 参数，`--book` 接入（旧调用行为不变）。
- `annotate_chapter_llm.add_rhetoric(book, chapter, tagged_path)`：调用 `build_candidates` 补传 `book`；报告目录按书隔离为 `logs/annotate/<书>/NNN.report.txt`（跨书并行批次需要，本批执行中落地）。
- `accept_batch.py` / `qa_annotation_report.py`（2026-11-05 G2）：新增 `--mapping-file` / `--registry`，换书批次传本书快照/登记表；缺省行为与旧版逐字节一致（A/B 已验证）；映射快照支持单文件/目录合并；登记表兼容 registry（list）与 `kb/<书>/实体登记表.json`（dict）两种 schema。
- `detect_verse_wuxia.py` / `generate_pn_wuxia.py`（2026-11-05 G1）：①`SIG_RE` 容忍"——自题《…》，调寄X"；②`plausible_verse` 句数门槛 3→2；③新增"词牌署名直判"（署名行+≥3 行+无引号+句长≤12+句数≥4 → 词）；④回末套语词族扩至"欲知任意…如何/怎样 + 请看下回(分解/再)"；⑤回末对新增"段末正是："信号（G-24 延伸，位置回末+支路 C 结构门槛）；⑥回末位置"对联"重归"回末对"；⑦新增"署名行收尾韵文组"（回末词/回中词整组一 PN）。《江湖三女侠》围栏 56→98，白发 32 回沙盒回归无 PN/类型回退。
- `config.py`（2026-11-05 G5）：`BOOK_OVERRIDES` 回填江湖三女侠指纹 `sha256:db56249aba01a746`（48 回 concat-sha256[:16]），`status` 显示"已锁定"。

逐回落盘断言脚本（`_annotate_003/004.py` 等）留 `tagged/_xval/`（数据区，见其 README）。

### 2026-11-05 下午批次新增（P3 脚本 / 导出层 / 终签与校准工具）

| 工具 | 用途 | 说明 |
|---|---|---|
| `time_resolver_wuxia.py` | **N4** 书内相对时间轴：`%` 令牌 → 时间类型/粒度/四类锚点 → 书内刻度 t → 单调性 E1/E2/E4 → T01-T15 错误清单；师承代数定年（low 封顶） | 产物 `registry/time/<书>.json`、`logs/time/`；pipeline `time-resolve` 阶段；`--selftest` 30/30 |
| `relation_validator.py` | **N5** 关系核验：55 谓词总表 + 04f 联动 27 行 + 语式表 → 联动候选核验 → `registry/relations/<书>.json`（edges 带 confidence/loc/evidence/rule）；双树/辈分派生 | `--strict` 门禁、`--selftest` 27/27；5 书 910 边（strong 105/ok 711/weak 94）；EX-4 字段映射见报告 §8 |
| `finalize_judgment.py` | judgment 终签工具：读 accept JSON `chapters_data[N].judgment_items`，38 条规则分类（应摘/改域/保留/人工）+ `--apply`（备份/span 逆序/剥标断言/幂等状态机） | v1.1；3 书 75 token 落地（docs/54）；5 书 336→263（历史；终版 judgment 153，docs/66） |
| `repair_corpus_titleline.py` | 底本书名行批量修复：自动扫描 34 部、`--apply` 备份+写后断言 | 修复 8 部（docs/53） |
| `_oneshot/fix_ethnicity_type.py` | 族群名本体 `&/◆/◎/#` → `~`；`#罗布族人` 剥标（B1-2/B1-3） | 13 处 5 文件（docs/53） |
| `export_site_common.py` / `export_site_all.py` | **EX 导出层**公共设施（契约快照/差异/备份/staging/`load_baseline`）+ 集成器（`--apply/--check-only`） | docs/51/52；Astro 38 页零改动 |
| `export_site_books_chapters.py` / `export_site_characters.py` / `export_site_dossiers.py` / `export_site_sects_weapons_arts.py` | EX-1/2/3/6 导出器（新 KB → `site/data` 现有 14 契约） | 12 个月 |

**loader 回级作用域（2026-11-05，S-03b v1.0 前置）**：`accept_batch.py` / `qa_annotation_report.py` / `annotate_chapter_llm.py` 支持映射快照条目级 `chapter/chapters/scope` 与 registry `context_notes` 回级注记，查找顺序 `(书,回,显示串)→(书,显示串)→全局`；缺省行为与旧版逐字节一致（A/B 全等，见 `logs/qa/loader_scope_report.md`）。

### P3 关键路径脚本（N6-N11，2026-11-05 晚，8 路并行批次 docs/57）

| 工具 | 用途 | 说明 |
|---|---|---|
| `merge_crossover.py` | **N6** 跨书归并工作台（D07）：候选 140 / 17 actionable / bare B0-B8 分流 / 双人复核状态机 | `registry/crossover/`；不自动合并；`--selftest` 21/21 |
| `gazetteer_migrate.py` | **N7** 虚构地名 gazetteer 迁移（D10）：旧 650 条 100% 守恒 → nature/kind/双图层 | `registry/gazetteer.json`；`--strict/--selftest`；kb 只读 |
| `lint_consistency.py` | **N8** 穿帮规则引擎（D11）：34 条 IF-THEN + 5 项检查；消费 N4/N5 | 5 书命中 44（error 0）；`registry/consistency/` |
| `lint_taxonomy.py` | **N9** 分类树校验（D08）：五树 64 叶结构/漂移/挂叶 | error 0 / warning 70；`logs/taxonomy/` |
| `update_intertext_loc.py` | **N11** 互文表 loc→loc_r 机锚回填（D07/D04）：行号指纹 + probe/snippet 双校验 | 5 书范围 21/21 resolved；`registry/intertext/` |
| `export_site_graph.py` | **EX-4** graph.json 导出（消费 N5 relations）：489 节点 / 907 边 | 已登记 `export_site_all.py`；`--selftest`、契约 hard_gap=0 |
| `registry/display_canonical.json` | **B-1/B-2** 展示层：玄烨→康熙/朱由检→崇祯/福临→顺治/胤禛→雍正/哈玛雅→飞红巾 | EX-2/EX-3 已消费（characters/entity-index/dossiers +display）；表缺失自动回落恒等 |

> 修复：`lint_text_integrity.py` 去重（struct+tagged 双 glob 曾把同一回计两次，江湖 48→96 回、integrity 174.7s→87.0s）。

### 第六波（2026-11-05 晚，docs/58）：N10 + EX-7 + EX-8

| 工具 | 用途 | 说明 |
|---|---|---|
| `build_sku_cards.py` | **N10** SKU 卡片生成（D12）：五类卡 + 元数据九项 + 脱敏 R1-R5 + 投影制 ID | 输出 `registry/sku/cards.json`：**1,536 张**（person 367/faction 70/art 852/artifact 226/manual 21）；`logs/sku/`；`--strict/--selftest` |
| `export_site_gazetteer_universe.py` | **EX-7** gazetteer/universe/atlas 导出（消费 N7 + 系列谱系考订表只读） | gazetteer 619（id 集合一致）/ universe 四节逐字段相等 / atlas 5 书；hard_gap=0；已 apply（冰魄 atlas 仅 staging） |
| `export_site_audit.py` | **EX-8** audit.json 导出（消费 N8 consistency） | 44 violations / 39 规则 / 脱敏（quote 不出口）；旧 R1→C4 映射预留；hard_gap=0；已 apply |
| `export_site_all.py` | EX 集成器升级 **8 导出器**（EX-1/2/3/4/5/6/7/8） | `--apply` 全跑 hard_gap=0 |

### 第七波（2026-11-05 晚，docs/59）：EX-5 事件层 + W7 + S-03i

| 工具 | 用途 | 说明 |
|---|---|---|
| `event_extractor.py` | **EX-5 事件抽取**（D03/04a 13 类 36 字段）：tagged+N4 time+N5 relations | `registry/events/` 5 书（schema event-v1，总 **22,978 事件**，41.2MB）；`--selftest` |
| `export_site_matches_ratings.py` | **EX-5** matches/ratings 导出（Glicko-2） | matches **215 场/161 fighters**、ratings **161 players/0 conflicts**；hard_gap=0；已 apply |
| `verify_quotes.py` | **W7 引文核验**：SKU/references 引文 vs 底本精确+近似匹配，不输出原文 | 2,383 引号片段 → hit 2/near 0/miss 3（叙事疑似编造 0）；`logs/w_group/` |
| `assign_taxonomy_leaves.py` | **S-03i 分类挂叶**：70 条 ◆ 组织 → 59 落叶/11 无法判定 | N9 UNMAPPED 70→11、warning 70→56；`logs/taxonomy/` |

### 第八波（2026-11-05 晚，docs/60）：P4 回写 / W 波1 / 站点搜索

| 工具 | 用途 | 说明 |
|---|---|---|
| `generate_w8_pages.py` | **W8 页型生成器**（W 波1）：五段式 + SKU 卡 + w8_w9_interface 槽位 | content/person/ **367 页**；quotes[]/demo:true；dry-run 默认/`--apply` 备份断言/`--selftest` 20/20 |
| `build_search_index.py` | **站点搜索索引**：dist → site/data/search-index.json（display/canonical/别名） | **1,443 条/终版；docs/66**；`--pagefind/--selftest`；build 后必跑 |

### 第九波（2026-11-05 晚，docs/61）：部署阻断 + W/S 续建

| 工具/改动 | 用途 | 说明 |
|---|---|---|
| `accept_batch.py`（改） | context_notes 回级 + display_canonical 白名单 + book 级过滤 | 江湖 warnings 212→**2**、七剑 167→**19**（历史；终版均 0）（89 条注记/36 管道修正） |
| `copyright_gate.py`（仓库根 scripts/，改） | 版权闸门 provenance 白名单 + `--selftest` 7/7 | 规则 1/2/3 全 0 PASS；go/no-go = GO |
| `export_site_common.py`（改） | meta.provenance 中性化（`tagged/`→`KB 标注层/`） | 8 导出器 hard_gap 0；闸门豁免归零 |
| `generate_w8_pages.py`（扩） | W8 四类卡页型（faction/art/artifact/manual） | 新增 **1,159 页** → content 合计 **1,526** |
| `build_search_index.py`（已有） | 搜索索引 + 可选 Pagefind | 1,451 条；Pagefind 1,452 页（发布需重跑） |

### 第十波（2026-11-05 夜，docs/62）：收尾 + 发布 GO

| 工具 | 用途 | 说明 |
|---|---|---|
| `render_ast_html.py` | **03d AST→HTML 转换器**（H-1~H-10 全实现） | 5 书样本各 1 回；selftest 12/12；23.3ms/章；`--out site/` 拒绝 |
| `build_reading_paths.py` | **09c 阅读路径**：main/theme/character/difficulty 四类 | `registry/reading_paths.json`：17 路径/171 steps/29 部 toc-only |
| `build_game_levels.py` | **09b 游戏化**：levels/achievements/sims | `registry/game/levels.json`：562 levels/33 achievements/12 sims |
| `release_site.py` | **一键发布编排**（备份→export 契约→build→搜索→Pagefind→闸门→扫描→GO/NO-GO） | `--dry-run/--skip-pagefind/--backup-dir/--strict`；退出码 0/1/2；失败即停 |
| `qa_annotation_report.py`（改） | book-aware registry（`--book` 只生效该书 context_notes） | A/B 5 书（塞外/冰魄/白发不变；江湖/七剑按书级注记收敛） |
| 验收扫描 `_site_acceptance_scan.py`（修） | 人物页期望由 dossiers.json 动态推导（原硬编码 885 已过期） | registry 归并后 881 属预期 |

### 第十一波（2026-11-05 夜，docs/64）：收尾 + 发布包

| 工具 | 用途 | 说明 |
|---|---|---|
| `render_ast_html.py`（扩） | 03d AST→HTML **全量 151 章**（`--all-books`） | HTML 17.15MB + AST gzip 3.16MB；H-4 差异 0/H-8 sha 一致；11.02s |
| `build_insights.py` | W11 洞察生成 | `registry/insights.json`：72 条（8 模式+证据≥2 类+反证+A-E） |
| `build_crossbook_threads.py` | W12 跨书叙事 | `registry/crossbook_threads.json`：61 条（char 25/同名异人 6/mention 10/intertext 20） |
| `build_sentence_index.py` | W13 句级双 ID 索引 | `registry/sentence_index/`：523,694 句（PN/行号双轨，99.5MB） |
| `build_canon_radar.py` | W14 穿帮雷达 | `registry/canon_radar.json`：53 记录+15 豁免（记录不改文） |
| `fill_content_quotes.py` | content 引文填充（W7 硬门） | 1,326/1,526 页（86.9%）、2,007 条（历史 22:0x；终版 1,495/1,526、2,194 条，docs/66）、均 38 字（≤60）；frontmatter quotes[] |
| `build_release_artifact.py` | 发布包 | `logs/release_artifacts/`：8.71MB zip + manifest（3,009 文件 sha256）+ RELEASE_NOTES（终版 220331：9,126,782B/3,002 文件/sha 6bf4e9ae…，docs/66） |
| `scan_untagged_aliases.py` | 别名瑕疵扫描（S-03b 配套） | alias==canonical/跨实体重复/alias==他人 canonical |
| `update_intertext_loc.py`（扩） | N11 行号锚双体系 | 可定位率 1.10%→**99.95%**（29 书 1,882 行号锚） |

### 第十二波（2026-11-05 深夜，docs/64 §十）：并发修正 + 收尾

| 工具 | 用途 | 说明 |
|---|---|---|
| `apply_entity_registration.py`（修） | 提案缺失友好报错 exit2 / 子目录+旧扁平探测 / 并发 CAS / 断言异常化 / schema 校验 | `--selftest` 7/7（含 `-O`）；真实七剑旧提案 dry-run 幂等 |
| `fill_content_quotes.py`（扩） | content 引文补填（新增 81 页/92 条） | 累计 1,407/1,526（92.2%）、2,099 条（终版 1,495/1,526、2,194 条，docs/66）；W7 抽样 50/50 hit |
| `build_sentence_index.py`（扩） | gzip 分片（99.5MB→**4.16MB**，4.2%）+ page_refs（6,037 句/1,356 页；后刷新 6,098 句/1,366 页，docs/64 §十.5） | `--page-refs/--read/--keep-jsonl`；selftest 15/15 |
| `repo_inventory.py` | 提交清单扫描（分类/大小/sha256/敏感/大文件/git 状态） | 12,117 文件/466MB；敏感 1 个已忽略的 api key；输出 repo_inventory.json |
| `verify_quotes.py`（W7 v0.2 扩） | `iter_yaml_quotes` + `--content` | content 全量（22:0x）2,007 条 hit 2,007/miss 0；content 引文已增至 2,194 条，需重跑（docs/66 §八）；W7 SKILL 补记 v0.2 |

> 并发外部 Session 修复保留（docs/63）：tagged 摘 292 处 `^武功`、8 脚本 P1 修复；本会话 4 书 re-accept 后 **5 书 warnings 全 0**、judgment 153；最终 release GO（1,444 页/33,254 链接缺失 0）；发布包 22:03 版 8.7MB/3,002 文件。

### 换书工具正式化 + 同位复指合并（2026-11-06，docs/50 S12 落地）

| 工具 | 用途 | 说明 |
|---|---|---|
| `merge_apposition_names.py` | 同位复指形合并：`〖@绰号\|本名〗本名` → `〖@绰号本名\|本名〗`（DEF-12 单标签化） | 5 稳定书 112 处 apply（冰川天女传由外部会话在写，排除）；剥标断言+备份 42 文件；5 书五门全 0 + re-accept 131/131、judgment 153 |
| `build_legacy_mapping.py` | 旧标注（kb/tagged/<书>）→ 每回《已核准映射表》快照（原 `_oneshot` 正式化） | `--legacy-dir` 可覆盖；冒烟：江湖 48 回快照末回 459 条（隔离输出验证后清理） |
| `verify_batch.py` | 整批 tagged 复核 + 逐回 E/V/R 统计（原 `_oneshot` 正式化） | 江湖 48/48 PASS，E=36,244 与 docs/54-0611 基线一致；fails 时 exit 1 |
| `rebuild_tagged_from_struct.py` | 按新 struct 重建 tagged，标注令牌沿内容行搬迁（原 `_oneshot` 正式化） | dry-run 江湖 48/48 成功 |
| `normalize_pipe_canonicals.py` | @ 管道规范名回填（原 `_oneshot` 正式化） | 新增 `--registry` 可传统一登记表（兼容 dict/list）；江湖 dry-run 0 变更（已归一） |
| `apply_judgment_a.py` | judgment 裁决执行器 A（动词层 remove/recode/keep；原 `_oneshot` 正式化） | 新增 `--book`；与原版 parity 校验逐字段一致（149/148/34，失败 106=历史已应用） |
| `apply_judgment_b.py` | judgment 裁决执行器 B（层定位+context 窗口；原 `_oneshot` 正式化） | 书名取 decisions JSON；parity 一致（失败 52） |
| `repair_tao_tokens.py` | 回末套语段 tao_token 误标摘除（原 `_oneshot` 正式化） | 当前 5 书无 tao_token 硬错误（预期 no-op） |

### 词法分析工具（2026-11-06，SKILL_02e 主工具）

| 工具 | 用途 | 说明 |
|---|---|---|
| `lexical_scan_wuxia.py` | jieba 分词 + 高频候选发现 + 夹心检测（同位复指/父术分裂自证分层） | 只读；报告落 `logs/qa/lexical_scan_<书>.md`；冰魄实测：117,136 字、同位复指 0（合并后基线） |
| `merge_apposition_names.py` | （见上节，同批） | 已登记 |

### 扩书 P1 新增工具（2026-11-06，docs/71 §七.1 → docs/73 执行）

| 工具 | 用途 | 说明 |
|---|---|---|
| `build_mapping_from_registry.py` | **无旧标注换书时的映射来源**：`registry/entities.json` 的 @ 人物别名（全局 aliases + 本书 contextual 注记）＋ 已过审 `tagged/` 的 @ 管道（仅跨书共享规范名，严格过滤）→ 每回《已核准映射表》快照 | 产物 `logs/mapping_<书>/{ch_NNN.json, mapping.json, review.tsv, summary.md}`；第 N 回=首现 <N 回（顺序标注纪律）；单字/通用称谓/器物形/短称/跨书冲突一律不收，人工复核记录在 review.tsv；`--dry-run/--check/--no-gold-transfer`；`--check` 可与 `build_legacy_mapping` 产物对账（江湖：新工具 227 条覆盖 legacy 440 条中的 167 条，其余为旧标注长描述形，属预期差异） |

> 原 `_oneshot/` 7 件保留为历史一次性记录，不再更新；换书一律用本批 `scripts/` 正式版。
