# 42 · Skill 与脚本实现完整性审计（对 docs/03/04/05/17 计划的逐项对账）

> **问题**：迁移方案（docs/03/04/05/17）里的全部 skill 与脚本，是否已经实现？
> **结论**：**没有。** P0/P1 已落地且可运行；P2 起大面积未实现；另有 13 个计划外脚本把 LLM 标注链做成了（020-032 回产物），但这不改变"计划整体未实现"的判定。
> **方法**：3 路并行审计（SKILL / 脚本 / 文档声明）+ Lead 独立复核；全部证据落在文件路径/行号/可复跑命令上。
> **详细证据**：`docs/_audit/skills-coverage.md`（SKILL 逐项）、`docs/_audit/scripts-coverage.md` + `scripts-run.log`（脚本逐项+实跑）、`docs/_audit/doc-consistency.md`（文档声明对账）。本文是汇总判定层。
> **快照**：2026-11-04 18:40（Asia/Shanghai）。只读审计，未改源码与 tagged 正文，未调用任何 LLM API。

---

## 一、一句话结论与关键数字

**按 docs/17 的 198 个计划节点：已实现 46 个（≈23%），其中 12 个是设计稿**；只看需要落地的实现件（186 个：50 脚本 + 134 SKILL/META/W/references + 2 模板），**已实现 34 个（≈18%）**。

| 类别 | 计划 | ✅ 已实现 | ◐ 部分 | ❌ 未实现/不可用 | 覆盖率 |
|---|---:|---:|---:|---:|---:|
| 脚本（C0 4 + C 24 + N 11 + E 11） | 50 | 21（文件落地 24，其中 C6 崩溃、C5/C7 未实跑） | 6 | 23 | **42%**（文件口径 48%） |
| SKILL 武侠版（S 组，轻30/中21/重3） | 54 | 9 | 5（仅设计稿覆盖） | 40 | 16.7% |
| META 武侠版（M00-M13） | 14 | 4 | 1 | 9 | 28.6% |
| W 组（组级流水线） | 38 | 0 | 0 | 38 | **0%** |
| references 支撑文档 | 28 | 0 | 0 | 28 | **0%** |
| 设计稿（D01-D12，上游） | 12 | 12 | 0 | 0 | 100% |
| templates 模板 | 2 | 0 | 0 | 2 | 0% |
| **合计** | **198** | **46** | **12** | **140** | **≈23%** |

> 说明：脚本"✅21"是**可运行/有实跑证据**口径；文件落地共 24 个（含 C6 —— 有文件但 `candidates` 批处理必崩，计 ❌；C5/C7 仅 `--help`，计 ◐）。两种口径都远未"全部实现"。

**门与波次**：G0 ✅、G1 ✅（但版本锁定断裂）、G2 记录性收口但质量门未过、G3 未启动；P0/P1 ✅、P2 部分、P3 产物完成（验收未做）、P4-P6 未启动。

---

## 二、审计口径（什么算"已实现"）

1. **SKILL 实现** = `skills/` 有该节点的专属主文件、且为武侠版实质内容；"设计稿存在"不等于"skill 已实现"（12 份设计稿覆盖 18 个 doc05 节点，只记为 ◐）。
2. **脚本实现** = 文件存在 **且** 能运行/能对接：`py_compile` 通过 + 关键路径实跑有证据；"文件在但批处理必崩"记为 ❌。
3. **E 组对接** = 既有站点管线真正消费新符号表/新 schema；"另写了一个新编排器"只算旁路，不算 E 组完成。
4. **计划基数**取 docs/17 §二节点展开（S 组按"轻 30 / 中 21 / 重 3"逐节点展开为 54；W 组 = W0-W6 7 + W7 1 + W8-W9 2 + W10x 24 + W11-W14 4 = 38）。

---

## 三、脚本：50 个计划节点，可运行 21（文件落地 24）

### 3.1 分组总表

| 组 | 计划 | ✅ 可运行 | ◐ 部分/未实跑 | ❌ 缺失/不可用 |
|---|---:|---:|---:|---:|
| C0 地基（config/symbols/masker/wordlist_compiler） | 4 | 4 | 0 | 0 |
| C 移植/改造（C1-C24） | 24 | 15 | 2（C5/C7） | 7（C6 崩溃 + C16-C20、C24 缺） |
| N 武侠新写（N1-N11） | 11 | 2 | 0 | 9（N3-N11 全缺） |
| E 既有管线对接（E1-E11） | 11 | 0（完全对接） | 4（E1/E4/E8/E11） | 7（E2/E3/E5/E6/E7/E9/E10） |
| **合计** | **50** | **21** | **6** | **23** |

> 文件落地共 24 个（C6 有文件但不可用，已计入 ❌；C5/C7 计入 ◐）。

### 3.2 已实现（有实跑证据）

- **C0 四件全绿**：`config.py`（34 部书自动发现）、`symbols.py`（15 实体 + 6 动词域 + 围栏 10 类）、`masker.py`、`wordlist_compiler.py`（`--check` 5 表全 PASS：quantity 36 / stopwords 18 / structure_markers 12 / time_words 19 / verbs 165，`auto_ready=0` 门控生效）。
- **C1-C15、C21-C23**：`py_compile` 全过；五门 lint 实跑 `pipeline_wuxia.py 白发魔女传 check` 退出码 0（lint-pn / integrity / symbol-lint / md-lint / fence-format 全 0，64 文件）；PN 合计 **2,263**、`reversibility=pass` 32/32；coverage 28.36%（96,020/338,586）；韵文 36 篇；段落结构 32 回。
- **N1/N2**：`generate_pn_wuxia.py`（产物 32/32 struct 齐）、`detect_verse_wuxia.py`（单回扫描实跑 exit 0）。

### 3.3 缺失/不可用（23 项，按波次）

| 波次 | 缺什么 | 证据 |
|---|---|---|
| P1 尾巴 | **C6 `find_candidate_entities.py` 批处理必崩**：`pipeline_wuxia.py 白发魔女传 candidates` → `KeyError: '白发魔女传:001'`（`find_candidate_entities.py:164`，`f.stem` 未剥 `.tagged.md` 与 `chapter_id` 不一致）；一行可修，当前 `logs/candidates/` 为空 | 已复现，退出码 1 |
| P1 尾巴 | C5/C7 仅有文件+`--help`，未实跑（C5 会原地写 tagged，C7 无 patch 输入）；C24 `build_entity_concordance` 缺失，**且 docs/17 §四波次表未给 C24 排任何波次**（计划漏排） | 文件清单/波次表 |
| **P2** | **C16 tag_new_entity_types、C17 tag_identity_kinship、C18 scan_untagged_aliases、C19 infer_single_char_names、C20 detect_entity_boundary_errors** 全缺（全库 glob + 内容检索无改名/等价实现；shiji 源件都在，只是未移植） | 全盘检索 |
| **P2/P3** | **N3 validate_verb_tagging、N4 time_resolver、N5 relation_validator** 缺；`qa_annotation_report.py` 只统计密度/分布，不做白名单/消歧/单调性校验，不等价 | 源码核对 |
| **P4** | **N6 merge_crossover、N7 gazetteer_migrate、N8 lint_consistency、N9 lint_taxonomy、N11 update_intertext_loc** 缺；父目录 `build_audit.py` 仅 R1 死亡一致性（R2/R3 明标挂账），`互文引用表.json` 无 `loc_r` 字段 | schema 实测 |
| **P5** | **N10 build_sku_cards** 缺（最下游）；**E2/E3/E5/E6/E7/E9/E10 完全未对接** | 见 3.4 |

**E 组（既有站点管线）现实**：父目录 `Wuxiaxiaoshuo/scripts/` 44 个 .py **零 import** `symbols.py`/`config.py`；`lint_annotation.py` 仍是旧码（`@=◆;%☆•+[§`，动词 `◉◈○▲◇`）；`repair_tags.py`、`build_entity_registry.py`、`build_event_table.py` 仍用旧 5 码；`matches.json` 仅 win/draw/loss 三值（非 D03 五值）；`gazetteer.json` 无 `nature` 四值；互文表无 `loc_r`。**新 `wuxia-kb/` 与旧站点管线目前是两套并行体系，尚未合流。**

### 3.4 计划外已实现脚本（13 个，旁路成果）

`annotate_llm.py`、`annotate_chapter_llm.py`（020-032 批产执行器）、`annotate_rhetoric_llm.py`、`qa_annotation_report.py`、`analyze_annotation_gap.py`、`compare_annotation_gold.py`、`qwen_review_chapter.py`、`summarize_annotate_cost.py`、`build_03a_fewshot.py`、`fix_annotation_mechanical.py`、`xval_analyze.py`、`api_config.py`、`pipeline_wuxia.py`（12 机械阶段 + check 门 + 2 个 LLM 契约占位）。

> 这 13 件把"种子→few-shot→LLM 标注→回锚保真→机械修复→计费→缺口分析→对账→外部复核"链跑通了，是真实增量；但它们不能替代 N3-N11 的质量/时间/关系/跨书/SKU 层，也不改变 P2-P5 计划未实现的判定。

---

## 四、SKILL / META / W / references：134 个对象，实现 13（9.7%）

### 4.1 现有资产

`skills/` 共 26 个 .md = README + **25 份主文件**（12 设计稿 + 8 P1 管线 SKILL + 4 META 第一波 + 1 重件 03a），合计 16,130 行；**无骨架/空模板文件**（最小 184 行），无史记内容泄漏（31 处"太史公/十表/三家注"全在差异对照/删除说明语境）。

### 4.2 S 组（计划 54）

- **已实现 9**：S-01a、S-01b、S-01f、S-02、S-02d、S-02f、S-02j、S-02k、S-03a（正文 v1.8）。
- **仅设计稿覆盖 5**：S-03b、S-04d、S-05e、S-07b、S-09a（规范主体散在 D07/D05/D03/D06/D01 中，无专属主文件）。
- **未实现 40**：S-02e、S-02i、S-03c、S-03c1、S-03d、S-03e、S-03f、S-03l、S-04、S-05、S-05d、S-06 组（4）、S-07 组、S-07f、S-08b/c/d/e/f、S-09b/c/d/e/f/g/h/i/k/m、S-10 组（8）等。
- **docs/17 §2.5 漏列 6 个 doc05 节点**：INDEX、SKILL_00、SKILL_03、SKILL_03f（边界错误反思，且无设计稿，风险最高）、SKILL_08、SKILL_09 总览——这些也应计入"全部"。
- **18 个节点"设计已备、SKILL 未成稿"**（写稿即可，无需再设计）：03g/04c/04e/07a（←D05）、05a/05b/05c（←D06）、03h/03i/03j/03k/06a/06e（←D08）、02h（←D09）、09j（←D10）、07c/07e（←D11）、08a/08e（←D12）。

### 4.3 META（计划 14）与 W / references

| 组 | 已实现 | 缺 |
|---|---|---|
| META | M13 / M08 / M10 / M04（第一波 4/4） | M01/M09/M02/M03（第二波）、M00/M06/M07（第三波）、M05/M11（第四波）、M12 适配说明（由 D07 吸收设计，◐） |
| W 组 | **0/38** | W0-W6、W7、W8-W9、W10x（24）、W11-W14 全缺（`site/` 在上级仓库，为既有 Astro 站点，无 Butler/wiki 流水线） |
| references | **0/28** | 含关键件 03c1 反思规律库（1,329 行 140 条）、04f1 动词规律库、02e1、02a1——随对应 SKILL 未成稿 |
| templates | 0/2 | `SKILL_template.md`（100:0 可直接用）也未建 |

### 4.4 成稿质量问题（不是缺失，但会挡"全部实现"验收）

- `SKILL_03a` **版本三口径打架**：§二标题 v1.1、版本锁定 `prompt_version v1.5`、正文修订线已到 v1.8；frontmatter **无 version 字段**；且 **seed 003 哈希失配**（manifest `dc9381b11802` vs 实际 `4af0c18c8d56`）——docs/37 改种子后未重跑 `build_03a_fewshot.py`，DEF-10 型漂移再现。
- `SKILL_分类树五件套` **15 个叶节点"典例"仍为"（待回填）"**。
- `lint_skills.py --all`：5 FAIL / 16 WARN / 0 PASS（均分 67.6），META-10 60 FAIL；但脚本 **exit code 恒为 0**，不能当门禁。
- 12 条真实悬空引用：`kb/gazetteer.json` 等 4 个资产实为上级目录 `Wuxiaxiaoshuo/kb/`（`wuxia-kb/kb/` 不存在）；`wordlists/verbs_source.md` 实为 `.json`；`wordlists/chengyu_source.md`/`chengyu.json` 未建；`scripts/lint_consistency.py` 待建（N8）；META-10 把未建脚本写进可执行命令块。

---

## 五、文档声明 vs 事实：大量"过时/夸大/自相矛盾"

> 结论：**硬数字基本真实，进度叙述与索引层严重滞后**。以下按严重度列，完整 60+ 条对账见 `docs/_audit/doc-consistency.md`。

### 5.1 真实波次/门状态（审计判定）

| 波次 | docs/17 定义 | 判定 |
|---|---|---|
| P0 地基 | 4 脚本+5 词表+G0 | ✅ 完成 |
| P1 校勘结构 | C1-C15+C21-C23+N1/N2+8 SKILL+pipeline | ✅ 完成（仅 C6 崩溃、E2/E3 未接、C24 漏排） |
| P2 实体层 | G1+03a+C16-C20/N3+11 SKILL | ⚠️ 仅 G1+03a 完成；脚本 0/6、SKILL 1/11 |
| P3 试点标注 | 32 回全书标注+N4/N5 | 🔶 32/32 回产物齐，但 020-032 仅 `structurally_valid`（accepted 未做）；N4/N5 缺 |
| P4 反思跨书 | S-03c+规律库+M 第二波+N6-N9/N11 | ❌ 未启动（仅"反思记录"文档层存在） |
| P5 应用发布 | N10+S-09 组+E4-E11+W 全组 | ❌ 未启动 |
| P6 上线回填 | M 第三/四波 | ❌ 未启动 |

| 门 | 判定 | 关键证据 |
|---|---|---|
| G0 拍板 | ✅ 通过 | 32 回 concat sha256[:16]=`3843aeb3e2b0e4b4` 与 `config.py:48` 一致；裁决已回写 04f/时间/01g/02ab；但 META-13 仍写"终选归 G0"（②未回写）、`config.py:17-18` 注释仍写"G0 未过" |
| G1 种子 | ✅ 收口，**版本锁定未闭环** | 种子 158E+27V / 775E+116V 与 docs/24 一致；但 manifest 6 项哈希 1 项失配、prompt_version 停在 v1.5 |
| G2 试点+反思 | ⚠️ 记录性收口，质量门未过 | docs/26/34 条款已入 03a v1.7/v1.8；但 S-03c 未建、020-032 无 accepted、密度 5.98 vs 金标准 9.77、001 金标准含 212 处旧口径 |
| G3 上线 | ❌ 未启动 | 无 site 对接、无穿帮/评分数据 |

### 5.2 主要过时/错误声明（摘要）

| 出处 | 声明 | 实际 |
|---|---|---|
| 根 README:6-19 | 文档索引 10 行（01-06、38-41） | docs 实有 **44 篇**，**缺 07-37 共 33 篇**；`07`、`24` 各有两个同编号文件 |
| docs/17 §七 | "P0-P1 完成，下一波 P2 入口"（2026-11-03） | 已过 G0/G1、完成 P3 32/32 产出；structure_markers 实为 12（写 10）、词表 5 表（写 4 表） |
| docs/19 | "P2-P5 待完成"；AMD xval "82E+54V 保真全过" | P3 已跑；`amd_001.EV.md` 实为 136E+4V 且完整性 FAIL（82E 属于 `amd_001.E.md`） |
| docs/27 §7.1 | 03a 六项哈希"全部一致 ✓" | 5/6 一致，seed 003 失配；`SHIJI_SCRIPTS` 非死常量（`_oneshot` 有引用，docs/34 亦如此说） |
| docs/27 | 登记表 v0.3 = approved 56/proposed 9/pending 5 | 实测 **70 条：approved 61/proposed 9/pending 0**，文件 `version` 仍 `0.1-draft` |
| docs/27/31 | "DEF-14 已入缺陷库" | `SKILL_03a` 仅 DEF-01~13，无 DEF-14 |
| docs/38 | "001-019 不动"；"全 32 回、52 文件"；文末"（待填）" | 同文又改 012-019；check 日志写 **64 文件**；文末确有占位 |
| docs/40 | "修正 docs/39 方案 3 条" | docs/39 未回写（mtime 早于 docs/40，全文无相关引用） |
| docs/41 | 5 项"采纳→删除该标/补负例表" | 未执行：`logs/_eval_001/001.tagged.md` 仍含 `⊠凌迟`，无负例表，`verbs.json` 无 negative 字段 |
| scripts/README | "P1 进行中/待排 N3-N11"、四表 | P1 已完成；5 源 + 7 编译表（+rhetoric 49、fossil 3）；缺登 11-04 的 8 个新脚本 |
| skills/README | 03a "v1.5（主文件）"、DEF-01~10、"8 块" | 正文 v1.8、DEF-01~13、9 块；同文件同节 8/9 块自相矛盾；重复段落 1 处 |
| docs/02 | "实体类型体系 10 类定版"、P0-P6 路线图 | 实际 15 实体+6 动词；路线图与 docs/17 同名异义，骨架产物（CLAUDE.md/INDEX/templates）未建 |
| docs/39 | S1-S5 补标方案 | 全部未实施（`wordlists/identity.json` 不存在；quantity 未扩表；无场所后缀/器物词表） |

### 5.3 悬空引用与未登记产物（双向）

- 文档引用但不存在：`backup/backup/skills/...`（双 backup，docs/07）、`wordlists/identity.json`（docs/39）、`lint_consistency.py`/`lint_setting_baseline.py`（META-10）、DEF-14（docs/27/31）、`tagged/白发魔女传/020-032.tagged.md`（单文件写法，docs/38）。
- 存在但未登记：**007-019 回产物 13 个 tagged 无任何批次执行/验收文档**；`tagged/_xval/_annotate_007-019.py`/`_verbfy_1819*.py` 未入其 README；`logs/yunwen/`、`logs/entity_stats/`、`registry/structure/` 等新产物无文档登记；`wordlists/rhetoric.json`/`fossil_verb_objects.json` 未入 README 词表清单。

---

## 六、"全部实现"还差什么（按执行顺序）

### 6.1 立即（当天，低成本高收益）

> **状态更新（2026-11-04 晚）**：本节 1-3 项已全部完成，修复与回归证据见 §九；§6.2 波次缺口仍未动。

1. **修 C6**：`find_candidate_entities.py:158` 的 `file_by_id` 键改为剥 `.tagged.md`（一行），恢复 `candidates` 阶段。
2. **03a 版本锁闭环**：构建器回填 `prompt_version`；重跑 `build_03a_fewshot.py`（seed 003 已变更）；统一 §二标题/manifest/正文版本；补 frontmatter `version`。
3. **文档最小回写**：根 README 补 07-37 索引（重复编号加 04a/04f、(003修订)/(G1收口) 后缀）；docs/17 加 §八"11-04 进度"；docs/19 标"历史快照"并修正 AMD 数字；skills/scripts README 按 4.x/3.x 修正；docs/38 收尾（52→64、删"待填"、改"不动"）。

### 6.2 按波次补齐（这才是"全部实现"的主体）

| 波次 | 还差（节点） | 说明 |
|---|---|---|
| P2 | C16、C17、C18、C19、C20、C24、N3；S-03b/03d/03e/03f/03l/02i/04/04d/05/05d/05e（11 份 SKILL） | 其中 18 个"设计已备"节点（03g/04c/04e/07a/05a-c/03h-k/06a/06e/02h/09j/07c/07e/08a/08e）可批量成稿 |
| P3 | N4 time_resolver、N5 relation_validator；020-032 语义验收（accepted）；13 处 verse 存疑处置（021/022/024/027/031/032） | 产物已在，缺质量层与验收 |
| P4 | N6、N7、N8、N9、N11；S-03c + 03c1 规律库；M01/M09/M02/M03 | docs/26/34 的条款是输入，需脚本/skill 收口 |
| P5 | N10；S-09 组（a/b/c/e/m）、S-06 组、S-07f、S-08c/f、S-10 组、09 轻组；E4-E11；W 全组 38；templates 2 | E 组需决定"对接改造"还是"声明新管线取代旧管线" |
| P6 | M00/M06/M07、M05/M11（+M12 适配说明） | 上线后滚动 |
| 贯穿 | references 28（03c1 与 S-03c 同批）；docs/39 S1-S5（identity.json/quantity 扩表/场所规则/器物词表 → few-shot S2 → 裁决器 S3 → P/R 门 S4 → 人工验收 S5） | S1 为 $0 API 成本，应优先 |

### 6.3 判定口径建议

- 完成度建议按 **"文件 + 可运行 + 对接"** 三档统计，而不是按"设计稿/文档提到"统计；本报告即按此口径。
- E 组建议尽快二选一：要么按 docs/17 §2.4 改造旧站点脚本（工作量大、但数据合流），要么正式声明 `pipeline_wuxia.py` + 新 tagged 取代旧管线，并冻结/归档 `Wuxiaxiaoshuo/scripts/` 的旧 build_* 消费层（否则两套 schema 长期并行）。

---

## 七、复核证据（Lead 独立验证，2026-11-04 18:40 审计快照）

> 以下为审计当时的原始证据；其中 seed 哈希失配、prompt_version 滞后、docs 索引、docs/38 两项与 C6 崩溃已修复，现状以 §九 为准。

| 结论 | 复验 |
|---|---|
| seed 003 哈希失配 | 实测 `sha256(003.tagged.md)[:12] = 4af0c18c8d56`，manifest 记 `dc9381b11802` ✗ |
| prompt_version 停在 v1.5 | `SKILL_03a` L340 `prompt_version | v1.5`；正文 v1.8（L74-75） |
| registry 70 条 | `entities.json` n=70，approved 61 / proposed 9；`version=0.1-draft` |
| docs 44 篇、索引仅 10 行 | `(Get-ChildItem docs -File).Count=44`；README 索引表 10 行 |
| docs/38 文件数写错 | `logs/check_full_20261104.log:6,1162` = "回文件数: 64"；docs/38 写 52 |
| docs/38 未收尾 | 文末确有"（待填）" |
| C6 崩溃 | `pipeline_wuxia.py 白发魔女传 candidates` → `KeyError: '白发魔女传:001'`，exit 1 |
| 81 个 .py 可编译 | A 37 + B 44 全过（见 scripts-run.log） |

**复现入口**：
```
python scripts/wordlist_compiler.py --check
python scripts/pipeline_wuxia.py 白发魔女传 check
python scripts/pipeline_wuxia.py 白发魔女传 candidates   # 当前必然失败（C6）
python -m py_compile scripts/*.py
```

---

## 八、最终判定

1. **"全部 skill 和脚本是否已实现"——否。** 脚本可运行 21/50（文件落地 24/50）、SKILL/META/W/references 13/134（9.7%）；把 12 份设计稿计入后 198 个计划节点实现 46 个（≈23%）。
2. **已实现的是"地基+校勘结构+标注主链"**：C0/C1-C15/C21-C23、N1/N2、9 份 SKILL、4 份 META、12 份设计稿、32 回 tagged 语料（其中 020-032 为机器初稿）+ 13 个计划外标注工具，且五门 lint 全绿、费用与 docs/38 精确对账（$0.651138）。
3. **未实现的是"实体/时间/关系/跨书/质量/应用"整条后半程**：C16-C20/C24、N3-N11、E 组对接、约 40 份 S 组 SKILL、10 份 META、W 全组、references、templates，以及 docs/39-41 新提出的 S1-S5 补标/验收方案。
4. **文档层需先"止损"**：进度叙述与索引停在 2026-11-03；03a 版本锁失配；若干"已完成"声明与实物不符（清单见 §5）。建议先做 §6.1 的当天修复，再按 §6.2 波次推进。**（2026-11-04 晚：§6.1 三项已修复，证据见 §九。）**

---

## 九、修复记录（2026-11-04 21:40–21:55，用户指示"先修复硬伤"）

### 9.1 已修三项（对应 §6.1）

| # | 硬伤 | 修复动作 | 验证结果 |
|---|---|---|---|
| 1 | **C6 `find_candidate_entities.py` 批处理必崩**（`KeyError: '白发魔女传:001'`） | 抽出 `chapter_id()` 统一章节键（剥 `.tagged.md`/`.struct.md`），`parse_chapter()` 与 `write_outputs()` 的 `file_by_id` 同源；同时消除同名局部变量遮蔽 | `pipeline_wuxia.py 白发魔女传 candidates` **exit 0**：30 个输出（`logs/candidates/summary.md` + 29 回 TSV），候选 7 条（修复前 exit 1、0 输出） |
| 2 | **SKILL_03a 版本锁失配**（seed003 哈希旧值、`prompt_version` v1.5、§二标题 v1.1、缺 frontmatter version、DEF-14 未入库） | ① `build_03a_fewshot.py` 升级 v3：`prompt_version` 自动回填、版本一致性断言（frontmatter＝§二标题＝manifest）、种子修辞层 `〘※…〙` 注入前剥离（保留显示串）、新增 `--check` 干跑；② `SKILL_03a` 补 `version: v1.8`/`last_updated`、§二标题改 v1.8、补 **DEF-14**、§5.1 "8 块"→"9 块"、附录 A "DEF-01~10"→"DEF-01~14"、加 v1.8 补记 | 重跑构建器全部断言 PASS：6 项哈希一致（seed003=`4af0c18c8d56`）、`prompt_version=v1.8`、9 块/占位 0、SYSTEM_PROMPT 10,519 字；`--check` 幂等通过；`load_system_prompt()` 返回 **v1.8** |
| 3 | **文档最小回写**（索引缺 33 篇、进度陈述过时、AMD 数字错、03a 登记过时、脚本 README 过时、docs/38 未收尾、docs/40 未回写 docs/39） | ① 根 README 全量分组索引（**45 篇全链接**，07/24 同号区分，docs/40 行改"提出 3 条修正"）；② docs/17 §七标历史快照 + 新增 **§八**（门/波次、C6、C24、structure_markers 10→12、四表→五表、verse 98 行）+ C 件数 22→24；③ docs/19 加历史快照注 + §1.5 AMD 更正（82E+0V / 136E+4V，均 FAIL）；④ skills/README 03a→v1.8、DEF-01~14、9 块、删重复段、04f 注；⑤ scripts/README 波次 P0-P3、5 源+7 编译表、补登 9 脚本；⑥ docs/38 52→64 文件、删"（待填）"、改"不动"表述；⑦ docs/39 补 §六（3 条修正均"未执行"）；⑧ docs/27 §7.1 加复核更正 | README 45 个 `docs/*.md` 链接 Test-Path 全过、docs 45/45 覆盖；docs/42 自身已入索引；docs/38 无"（待填）"残留 |

### 9.2 回归验证（修复后全量）

| 检查 | 结果 |
|---|---|
| `python -m py_compile scripts/*.py`（37 件） | 0 失败 |
| `python scripts/wordlist_compiler.py --check` | 5 表 PASS（quantity 36 / stopwords 18 / structure_markers 12 / time_words 19 / verbs 165） |
| `python scripts/pipeline_wuxia.py 白发魔女传 check` | 5 项 lint 全 0，exit 0（64 文件） |
| `python scripts/pipeline_wuxia.py 白发魔女传 candidates` | exit 0（修复前 exit 1） |
| `python scripts/build_03a_fewshot.py --check` | 检查 1-10 全 PASS（含版本一致性） |
| `python scripts/lint_skills.py --all` | exit 0（仅 WARN；脚本本身非门禁，见 §4.4） |
| `tagged/` 正文 | 零改动（构建器只改 `skills/SKILL_03a` 的 few-shot 区与版本锁定表） |

### 9.3 仍未修（不属于"当天硬伤"，按 §6.2 波次推进）

- **P2 起的实现缺口**：C16-C20/C24/N3、N4-N11、S 组 40 份、META 9 份、W 38、references 28、E4-E11、templates 2。
- **E 组双体系合流决策**：改造旧站点脚本，或正式声明 `pipeline_wuxia.py` + 新 tagged 取代旧管线并冻结旧 build_*。
- **质量收口**：020-032 accepted 语义验收、13 处 verse 存疑、001-019 旧口径 212 处清洗、docs/41 P0 建议（负例表/词表补标）与 docs/39 S1-S5。

---

## 十、P2 实施与 020-032 accepted 验收（2026-11-04 22:00–22:35，本报告后续进展）

> 本节为本审计报告落盘后的实施回写；扫描基线仍以 §一/§八 为准，最新完成度以本节与 docs/44 为准。

### 10.1 已交付（P2 脚本层）

| 节点 | 交付 | 实跑要点 |
|---|---|---|
| C16 | `tag_new_entity_types.py` + `new_entity_types.json`（268 条） | 32 回建议 53 条/13 词种；默认只出 C7 兼容 TSV |
| C17 | `tag_identity_kinship.py` + `identity.json`（212）/`kinship.json`（62） | 32 回建议 917 条；kinship 按 03a D1 仅领属结构建议 |
| C18 | `scan_untagged_aliases.py` | registry 70→97 词条；101 条建议/23 回 |
| C19 | `infer_single_char_names.py` | 单字 @ 11 → 映射 10（新推断 0）；歧义 1 |
| C20 | `detect_entity_boundary_errors.py` | 19 条（error 4/warn 10/info 5）；selftest 8/8 PASS |
| C24 | `build_entity_concordance.py` | 4,992 实体/32,731 次；registry 命中 69；unregistered 301 |
| N3 | `validate_verb_tagging_wuxia.py` | 5,869 动词；error 0 / warning 317（词表域冲突已降 warning）；pipeline `verb-validate` |
| 验收 | `accept_batch.py` | 13 回 accepted（见 10.2） |

**脚本完成度**：可运行 **21/50 → 28/50**（C0 4 + C 22 + N 2；E 0；C5/C7 仍静态）；`scripts/*.py` 37→45；词表 7→10 张编译表。

### 10.2 020-032 accepted 验收（两段式）

- 初验收（docs/43）：accepted 13/13、hard 0、judgment 85、pipe_unsourced 0、抽样 117 段（10%±1）。
- judgment 处置（docs/45）：85 条裁决 → 真违规 58、保留 27；修 **52 处 token**（删标 48 + 改域 4）+ N3 E-PUNCT 2 处（019 标点外置）。
- 重跑：**accepted 13/13、hard 0、judgment 27、warnings 2、pipe_unsourced 0**；五门 lint 全 0；剥标 != 底本 0 段；正文零增删改（E 32,731→32,716、V 5,869→5,836）。
- 残留：27 条保留 judgment 待终签；032 两条 `卓某` 映射冲突待 S-03b；13 处 verse 存疑。

### 10.3 对 §八 判定的更新

- §八 第 1 条"脚本可运行 21/50"→ **28/50**；第 3 条中"C16-C20/C24、N3"已不再是缺口（N3 已交付；N4-N11 仍缺）。
- P3 状态由"产物完成、accepted 未做"→ **accepted 完成**（13/13，详见 docs/43/45）。
- P2 仍缺的是 **11 份 SKILL**（03b/03d/03e/03f/03l/02i/04/04d/05/05d/05e）与 E 组对接，不是脚本地基。

---

---

## 十一、E 组合流决策（2026-11-05，用户拍板，关闭 §6.3/§9.3 挂账）

- **决策**：选定 **方案 C「冻结旧件 + 薄导出适配层」**，详见 [`docs/51-E组合流决策与导出适配层方案.md`](51-E组合流决策与导出适配层方案.md)。
- **要点**：① 新管线（`pipeline_wuxia.py` + tagged/registry/concordance/acceptance）为唯一真源；② 父仓 `Wuxiaxiaoshuo/scripts/` 44 个 .py 与旧 `kb/tagged/`、旧 `site/data/` 冻结为只读（旧 kb 的 7 个考订数据表继续作为只读迁移输入）；③ 在 `wuxia-kb/scripts/` 新建 **EX-1..EX-8 导出器**，按 `site/data/` 现有 14 个 JSON 契约导出，桥接期 Astro 38 页零改动；W 组仍按新 schema 设计、不依赖导出器，W 组落地后导出器退役。
- **E 组节点变更**：**E1/E2/E3 裁撤**（由新管线/五门 lint/`fix_annotation_mechanical` 取代）；**E4-E11 → EX-1..EX-8**（阶段 1 的 EX-1/2/3/6 可立即与 N4/N5 并行；EX-4/5/7 依赖 N5/N7；EX-8 依赖 N8）。
- **对本文结论的影响**：§六.3 与 §九.3 的"E 组二选一"关闭；"两套 schema 长期并行"风险降级为"桥接期并行、可退役"。E 组完成判定改为"EX 阶段 1 交付 + site 构建通过"即不阻塞 G3。

---

*生成：2026-11-04；证据文件：`docs/_audit/skills-coverage.md`、`docs/_audit/scripts-coverage.md`、`docs/_audit/doc-consistency.md`、`docs/_audit/scripts-run.log`。修复记录见 §九；P2 实施见 §十 / `docs/44`；E 组决策见 §十一 / `docs/51`。*
