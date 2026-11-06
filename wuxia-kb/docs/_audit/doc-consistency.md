# 文档一致性审计报告（wuxia-kb）

> 审计员：doc-auditor（共享任务 task-3）
> 快照时间：2026-11-04 18:24–18:40（Asia/Shanghai）
> 方法：只读检查 + 本地非 LLM 命令复算（`Get-FileHash` / `Get-Content` / JSON 解析 / `pipeline_wuxia.py check` / `symbols.ENTITIES`）。
> 未调用任何 LLM，未重建 `SKILL_03a`（会改写文件），除本文件外未主动修改任何文件。
> 范围：`docs/17-41`、根 `README.md`、`skills/README.md`、`scripts/README.md`、`prompts/README.md`、`wordlists/*_source.md`，对照 `docs/02`、`docs/06`，并落到 `tagged/`、`logs/`、`registry/`、`skills/`、`scripts/` 实物。
> 并发说明：18:26 起另一审计任务在写 `docs/_audit/scripts-run.log`、`registry/structure/`、`registry/sections_data.json`、`logs/yunwen/`、`logs/entity_stats/`、`logs/coverage/`、`logs/verse_scan/…_001-001.md`。本报告以 18:24 前已存在、18:40 复核未变的产物为准；受影响项在文中标注。

---

## ① 一句话结论

**G0/G1 两道门与 P0/P1 波、020-032 批次费用等"硬数字"基本真实（可逐项复算到文件/哈希/token），但整套进度叙述停在 2026-11-03：`docs/17 §七`、`docs/19`、三个目录 README 仍写 P1 进行中/P2-P5 待完成；实际已推进到 P3 产物齐备但语义验收未做的位置。真正的缺口在三处：(a) P2 的 7 类节点（C16-C20/C24/N3/S-03b 等）只有规范没有脚本/skill；(b) G2 只完成"反思记录"，质量门与 S-03c 未收口（020-032 仅 `structurally_valid`，实体密度 5.98 vs 金标准 9.77）；(c) SKILL_03a 版本锁定三处互相矛盾（§二标题 v1.1 / manifest v1.5 / 实际修订线 v1.8），且种子 003 哈希已失配（`dc9381b11802` vs 实际 `4af0c18c8d56`），docs/39-41 的 3 条修正与 P0 建议也未回写/未落盘。**

---

## ② 真实波次/门状态判定

### 2.1 波次（统一采用 `docs/17 §四` 的 P0-P6 定义；`docs/02 §七` 的 P0-P6 为早期方案阶段，同名异义，见 ④）

| 波次 | docs/17 定义 | 判定 | 证据 |
|---|---|---|---|
| **P0 地基** | 4 地基脚本+5 词表+G0 | ✅ **完成** | `scripts/{config,symbols,masker,wordlist_compiler}.py` 存在；`symbols.ENTITIES=15`、6 动词域；5 张首批准词表编译 PASS（`logs/_audit/scripts-run.log` 18:26 另一任务复跑亦 5/5 PASS） |
| **P1 校勘结构** | 第1波 15 件+C21-C23+N1/N2+8 SKILL+pipeline | ✅ **完成** | 18 个 C 族脚本（C1-C15、C21-C23）+N1/N2 全在 `scripts/`；`pipeline_wuxia.py check` 复跑退出码 0；PN 合计 2,263、32/32 回 `reversibility=pass`（`*.struct.json`） |
| **P2 实体层** | G1+03a+C16-C20/N3/S-03b/S-03d/e/f/l/02i/S-04/05 等 | ⚠️ **部分完成** | G1 收口、`SKILL_03a` 实物在；但 `tag_new_entity_types/tag_identity/scan_untagged_aliases/infer_single_char_names/detect_entity_boundary_errors/build_entity_concordance/validate_verb_tagging` 只出现在 docs/prompts 里，`scripts/` 无文件；无 `skills/SKILL_03b*`、无 S-03d/e/f/l/02i 文件 |
| **P3 试点标注** | 白发魔女传 32 回全书标注（LLM 作业）+N4/N5 | 🔶 **产物完成、验收未完成** | `tagged/白发魔女传/` 有 32×3=96 个文件，32/32 回 tagged；但 020-032 仅 `structurally_valid`（`docs/38:6-7,177-179`），语义 `accepted` 未做；N4/N5 无脚本 |
| **P4 反思跨书** | S-03c+规律库+M 第二波+N6/N11/N7/N8/N9 | ❌ **未启动** | 无 `skills/SKILL_03c*`；无 `merge_crossover/gazetteer_migrate/lint_consistency/lint_taxonomy` 脚本；M 第一波 4 件之后再无 META 新增 |
| **P5 应用发布** | N10 SKU、S-09 组、E4-E11、W 组 | ❌ **未启动** | 无 `build_sku_cards.py`、无 W 组产物 |
| **P6 上线回填** | G3、M 第三/四波 | ❌ **未启动** | 无相关产物 |

### 2.2 四道门

| 门 | 文档声称 | 实际判定 | 关键证据 |
|---|---|---|---|
| **G0 拍板** | 通过（`docs/18:35`；8 项+2 默认+普查） | ✅ **通过**（回写 6.5/7 处；②号回写缺 META-13 终选记录） | 指纹复算：32 回 concat sha256[:16] = `3843aeb3e2b0e4b4`，与 `scripts/config.py:48` 一致；`SKILL_04f:1022-1027` 的 B-1~B-6 均标"✅ G0 裁决"；`SKILL_时间体系:418,724`、`SKILL_01g:324` 有 |时点| 裁决；`SKILL_02a_02b:1019` 有底本裁决。**缺口**：`skills/META-13:137,252,417` 仍写"终选归 G0"，未记录"已终选白发魔女传"；`scripts/config.py:17-18` 的 docstring 还写"G0 未过、fingerprint 留 None"，与 `:44,48` 相反（陈旧注释） |
| **G1 种子** | 收口（`docs/24:3-7`） | ✅ **收口**，但**版本锁定未闭环** | 种子：`tagged/_xval/glm_001.EV.v2.md`=158E+27V、`tagged/白发魔女传/003.tagged.md`=775E+116V，与 docs/24 一致；`scripts/build_03a_fewshot.py` 存在；`SKILL_03a` 有 9 块 FS、SYSTEM_PROMPT=10,519 字符。**但**：`SKILL_03a:63` 标题"v1.1"、`:340` manifest"prompt_version v1.5"、正文修订线到 v1.8；manifest 6 项哈希中 5 项命中，seed 003 记 `dc9381b11802` 而实际 `4af0c18c8d56`（docs/37 在 15:22 给 003 补 8 处修辞后未重跑构建） |
| **G2 全书试点+反思** | 首轮"✅ 完成"（`docs/26:3`）、二轮"全部收口"（`docs/34:57`） | ⚠️ **记录性收口，质量门未过** | 首轮反思记录 `docs/26`（R-001~R-016）在；二轮 R-013/密谋归档条款已入 `SKILL_03a:75`、`SKILL_关系体系:165`。**但**：S-03c 未建（`skills/` 无文件）；020-032 无 `accepted` 记录；`docs/39` 量化实体密度仅金标准 61%（5.98 vs 9.77）；`docs/40` 指 001 金标准有 212 处旧口径。按 docs/17 的 G2 验收（全书标注+首轮反思）可称"记录齐"，按质量口径（accepted+S-03c）**未通过** |
| **G3 上线** | 未提及 | ❌ **未启动** | 无 E4-E11 site 对接、无穿帮/评分数据齐备证据 |

### 2.3 "规范已有但脚本/作业未收口"清单（本报告重点）

1. **03a 版本锁定构建器**：`scripts/build_03a_fewshot.py:151-159` 只回填 ruleset/ruling/symbols/两种子/generated_at，**不回填 `prompt_version`**；manifest 停在 v1.5、正文标题停在 v1.1，而修订线已到 v1.8。
2. **种子→few-shot 再生成纪律**（`docs/24 §五.3`）：docs/37 在 15:22 修改 001-019 种子（加 115 处 〘※〙，其中 003 有 8 处），构建器 `generated_at=2026-11-04` 但 seed 003 哈希失配，证明**种子改变后未重跑**（DEF-10 型漂移再现）。
3. **DEF-14 未入库**：`docs/27:186`、`docs/31:8,156` 把 DEF-14（草稿占位符禁止入产出脚本）当既成事实引用，但 `SKILL_03a` 缺陷库止于 DEF-13（`:254-257`）。
4. **P2/P4 节点无实物**：C16-C20、C24、N3、N4、N5、N6-N10、S-03b、S-03c、S-09、W 组在 `scripts/`、`skills/` 中均无文件（只在 docs/prompts/backup 的叙述中出现）。
5. **020-032 语义验收**：`docs/38:177-179` 自认未做；`docs/39` S1-S5 均为方案；`docs/40` 仅对 001 单回做对账；无任何 020-032 回 `accepted` 记录。
6. **金标准清洗**：`docs/40 §八`、`docs/41 §五 P1` 提出 001-019 至少 212 处旧口径需标 legacy/改标，未执行（`tagged/001` 仍 1,831E，未生成 docs/40 承诺的 ~1,758 token v1.8 校准集）。
7. **docs/41 的"采纳—删除/补负例表"**：未落到产物（见 ③-41、⑤）。
8. **G-24 后续章回**：005/015/017 已按 G-24 修复（`*.struct.json` branch=`回末正是惯例(G-24终裁)`，doubts=0）；但 020-032 仍有 13 处 verse 存疑（021:2、022:1、024:4、027:1、031:1、032:4）无处置记录。
9. **索引层**：root README 缺 07-37；`skills/README` 03a 版本停在 v1.5；`scripts/README` 停在"P1 进行中"；`wordlists/` 无 README 登记新增 2 表。

---

## ③ 进度声明对账表（按文档分组）

> 结论取值：成立 / 部分成立 / 不成立 / 已过时（当时成立、现被取代）。"可验证事实"均为 18:40 前实测。

### 3.1 `docs/17` §七 与波次表

| 出处（行） | 声明 | 可验证事实 | 结论 |
|---|---|---|---|
| 17:358 | "实施进度标记（2026-11-03，P0-P1 波完成）" | P0/P1 产物确实齐；但页内未反映 11-04 的 G0/G1 收口与 P3 批次 | 成立（已过时） |
| 17:362-366 | P0 四脚本 ✅，词表编译"四表 PASS" | 4 文件在；`wordlist_compiler --check` 为 **5 表**全 PASS（含 quantity） | 部分成立（4→5 表） |
| 17:367 | structure_markers **10** | `wordlists/structure_markers.json` `items=12`（G0 回填 有诗为证/花开两朵/不在话下 后） | **不成立**（应为 12；docs/19:45 也写 12） |
| 17:368 | M 第一波 4 件 ✅ | `skills/META-{13,08,10,04}_武侠版.md` 均在 | 成立 |
| 17:370-375 | P1 全部完成（8+7+3 脚本、N1/N2、8 SKILL、pipeline） | 对应文件全部存在；`pipeline_wuxia.py` 在 | 成立 |
| 17:373 | "全书 32 回回归：2263 PN 可逆性全 pass" | 32 个 `*.struct.json` 的 `pn_total` 合计 **2,263**；`reversibility=pass` **32/32** | 成立 |
| 17:383 | "五项 lint 全过（完成门达成）" | 18:33 复跑 `pipeline_wuxia.py 白发魔女传 check` → exit 0，五项退出码全 0 | 成立 |
| 17:383 | "verse-scan 全书 78 候选（58 成立/20 存疑）" | `logs/verse_scan/白发魔女传_scan_001-032.md` 现有 **99 数据行**：78 行为完整 8 列（58 成立+20 存疑），另 **21 行只有 6 列**（缺"类型/备注"，含 021-032 章） | 部分成立/已过时（报告未随新章更新且表格列有缺陷） |
| 17:385 | "下一波（P2）入口：G0→G1→S-03a" | G0/G1 已完成，03a 已到 v1.8，P3 已跑完 32 回 | **已过时** |

### 3.2 `docs/18`（G0 拍板）

| 出处 | 声明 | 可验证事实 | 结论 |
|---|---|---|---|
| 18:10-17 | 八项裁决均已回写 | ①`02ab:1019` ✅；③④⑤⑥⑦`04f:1022-1027` ✅；⑧`时间:418,724`+`01g:324` ✅；②`META-13:137,252,417` 仍"终选归 G0"，无终选记录；①`config:48` 指纹 ✅ 但 `config:17-18` 仍写"G0 未过" | 部分成立（②未回写、①注释陈旧） |
| 18:24 | "33/34 部书套语普查 已完成" | `章回版/` 下 34 个书目录；`skills/SKILL_02a_02b:1059` 标题写"33 部书"、`:1062` 正文写"34 部书全量" | 部分成立（"33/34"与 B7 标题数字未统一） |
| 18:35 | "G0 拍板门：通过" | 指纹/裁决/词表回填均可复核 | 成立 |

### 3.3 `docs/19`（Session 进度，2026-11-03）

| 出处 | 声明 | 可验证事实 | 结论 |
|---|---|---|---|
| 19:10-27 | docs/06 12 项全部交付 | `prompts/T01-T12`=12 个；12 个设计主文件在；`docs/07-16` 对比文档在 | 成立 |
| 19:27 | "旧符号回归 0""无 yaml 围栏""无日期偏置" | 当前 `pipeline` symbol-lint=0；其余项未逐条复核 | 部分成立（抽查项成立） |
| 19:31-38 | P0 4 脚本（含"五表编译全 PASS"） | 4 脚本在；`wordlist_compiler --check` 5/5 PASS | 成立 |
| 19:40-48 | 五表 165/12/18/19/36 | 数字全部命中 JSON；但当前已扩为 **7 张**编译表（+`rhetoric.json` 49、`fossil_verb_objects.json` 3） | 部分成立（"五表"已过时） |
| 19:50-56 | "P1 移植+新写（21 脚本）" | 实际 P1 范围脚本 **20** 个（C1-C15+C21-C23=18，加 N1/N2）；C16-C20/C24 未建 | **不成立**（无第 21 件；分类与 docs/17 的 P2 划分矛盾） |
| 19:58-63 | N1/N2 自检（2263 PN、78 候选） | PN 2263 ✅；verse 见 17:383 项 | 部分成立 |
| 19:85-107 | G1 前置验证 ✅；**amd_001.EV.md（82E+54V，保真全过）** | `tagged/_xval/amd_001.EV.md` 实测 **136E+4V**，`amd_001.report.txt` 自写"E/EV 完整性 **FAIL**"；82E 属于 `amd_001.E.md`（V=0）。GLM `glm_001.EV.md`=109E+24V 属实 | **不成立**（数字/文件错位，且保真非"全过"） |
| 19:113-117 | G1 种子标注待办（人工复核 001/003、产出 03a） | 已于 docs/24 收口，03a 实物存在 | **已过时** |
| 19:128-134 | P2-P5 待完成 | P3 已执行（32/32）；P2 仍部分 | **已过时**（整体停滞叙述） |
| 19:155 | 生成时间 2026-11-03 | 之后新增 docs/24-41 共 18 篇 | 已过时（未更新范围/时间） |

### 3.4 `docs/24-27`（G1 收口、004 试点、G2 首轮、待办池）

| 出处 | 声明 | 可验证事实 | 结论 |
|---|---|---|---|
| 24:3-7 | G1 ✅ 收口，种子 001 v2/003 全章人工复核通过 | 两文件在，158E+27V / 775E+116V 与文一致；03a、构建器在 | 成立 |
| 24:14 | 001 v1 = 109E+24V | `glm_001.EV.md`=109E+24V | 成立 |
| 24:42 | SYSTEM_PROMPT 6,705 字符（v1.0）；8/8 断言 | 当前 10,519 字符、9 块 FS | 已过时（历史值） |
| 24:60 | 主文件 v1.0→v1.1 | 文件已到 v1.8 修订线；标题 v1.1、锁 v1.5 | 已过时（版本三处不一） |
| 24:62 | 索引登记（skills/README 03a 节、prompts/README） | 两处均有 03a/A1/A2 条目 | 成立 |
| 25:19 | 004 = 798E+151V | 当前 835E+172V | 已过时（历史） |
| 25:75 | 独立终验外包 docs/28 | docs/28/29/30 齐 | 成立（已闭环） |
| 26:3 | G2 首轮反思 ✅ 完成 | `docs/26` 在，R-001~R-016 齐；S-03c 未建 | 成立（记录层） |
| 26:45 | R-013 战斗粒度**未决** | `docs/34:35` 已终裁并入 03a v1.8 | **已过时** |
| 27:103 | "03a 版本锁定 manifest 六项哈希 vs 实际：**全部一致 ✓**" | 5/6 一致；seed 003 锁 `dc9381b11802` ≠ 实际 `4af0c18c8d56`；prompt_version v1.5 ≠ 正文 v1.8 | **已过时（现失配）** |
| 27:106 | `config.py:28 SHIJI_SCRIPTS` 是死常量 | `scripts/_oneshot/_tmp_gen_02ab_v2.py:150` 仍引用；docs/34 #5 明确"非死常量、保留" | **不成立**（与 docs/34 冲突） |
| 27:156 | 006 = 758E+195V | 当前 745E+197V（docs/32 v3） | 已过时 |
| 27:176 | 登记表 v0.3 = 70 条（approved 56/proposed 9/pending 5） | `registry/entities.json` 70 条，实际 **approved 61/proposed 9/pending 0**；文件 `version` 字段仍为 `0.1-draft` | **不成立**（分布不符；版本字段陈旧） |
| 27:186 | 占位符事故"对策入 DEF 库：DEF-14" | `SKILL_03a` 缺陷库只有 DEF-01~13 | **不成立**（未入库） |
| 27:191 | "007 回继续" | 007-019 tagged 均在，但 `tagged/_xval/README.md` 未登记 `_annotate_007-019.py`/`_verbfy_1819*.py`，无任何执行/验收文档 | 部分成立（产物在、记录缺） |

### 3.5 `docs/28-32`（004/005 评审、006 验收）

| 出处 | 声明 | 可验证事实 | 结论 |
|---|---|---|---|
| 28:6 | 004→834E+171V、005→1003E+221V，03a v1.4 | 后经 docs/29 二轮→835/171、docs/33 v2.1→835/172；005→1005/222 | 已过时（历史快照） |
| 29:5 | "确定性修订已全部执行" | 004/005 当前计数与后续修订记录吻合 | 成立 |
| 29:28 vs 29:83 | 004 "834E+171V" vs "835E+171V" | 同文档前后不一致；实际 835E+**172V** | **不成立**（内部矛盾+与产物差 1 V） |
| 29:86 | SYSTEM_PROMPT 9,093 字符（v1.5） | 当前 10,519 | 已过时 |
| 29:88 | 004/005 判入库 | 后续 docs/33/34 沿用 | 成立 |
| 31:8,156 | 006 "占位符污染事故（DEF-14）" | 03a 无 DEF-14 | **不成立**（引用悬空） |
| 32:35-37 | 006 = 745E+197V | 实测 745/197 | 成立 |

### 3.6 `docs/33-37`（P3 定例、G2 二轮、修辞层）

| 出处 | 声明 | 可验证事实 | 结论 |
|---|---|---|---|
| 33:4 | 03a v1.5→v1.6 | `SKILL_03a:74` 有 v1.6 行 | 成立 |
| 33:26 | SKILL_04f → v2.1 | `SKILL_04f:148,384` 有 v2.1 块；但头 `:15` 与尾 `:1039` 仍写 v0.3-draft | 部分成立（版本标识未统一） |
| 33:50-56 | 001/002 `〖^武功〗` ×8/×4 撤标 | 001-006 `〖^武功〗` 实测全部 0 | 成立 |
| 33:83 | 004=835E+172V、005=1005E+222V | 实测一致 | 成立 |
| 33:90 | few-shot 重建 PASS（9,854 字符） | 未复跑构建器（会改写 SKILL）；现 manifest 与种子已失配 | 不可复验（存疑） |
| 34:5,57 | "G2 二轮全部收口" | v1.7/v1.8 条款已入 03a/关系体系；但 S-03c 未建、020-032 未 accepted | 部分成立（反思条目收口≠门收口） |
| 34:6 | SYSTEM_PROMPT 10,519 字符 | 实测 10,519 | 成立 |
| 34:14 | "全量 38 回 lint 0 实质差异" | 38 = 当时 19 章 × 2 文件（tagged+struct）；当前为 32 章/64 文件（`logs/check_full_20261104.log:6` 明写 64） | 部分成立（"回"应为"文件"） |
| 34:16 | 修辞层 53 条"维持待办" | `rhetoric.json` 已 49 收录/4 rejected，docs/35 已核定关闭 | 已过时 |
| 34:17 | registry 61 approved/9 proposed/pending 0 | 实测完全一致 | 成立 |
| 34:18 | SHIJI_SCRIPTS 非死常量 | `_oneshot` 引用存在 | 成立（反证 docs/27:106） |
| 35:5-7 | 49 收录/4 不收录/1 修正 | `rhetoric.json` items=49、totals approved 49/rejected 4/corrected 1 | 成立 |
| 35:86 | 候选池逐条注入 decision | `rhetoric_candidates_v0.json` 53 条中 **52 条有 decision**；idx49「人言过其实」无 `decision`/`id` | **不成立**（1/53 缺失） |
| 35:88 | 19 回落标 79 处 | 001-019 `〘※〙` 合计 **79** | 成立 |
| 36:5-6,42-44 | 005/015/017 回末对围栏修复 | 三章 `struct.json` fences 均含 `回末对` 且 branch=`回末正是惯例(G-24终裁)`、doubts=0 | 成立 |
| 36:50,52 | "全书 38 回文件通过""全书 19 回 tagged 未围栏 0" | 38=19×2 文件；001-019 全部有回末对围栏 | 部分成立（计数口径错，现为 64 文件/32 章） |
| 37:6,29-34 | 79 处 ※，逐回表 | 逐回 R 计数完全一致（001:5/003:8/004:23/…合计 79） | 成立 |
| 37:9 | 花费用 ≈$0.0104 | `logs/token_usage/rhetoric_*.json` 3 份合计 **$0.010166** | 成立 |
| 37:62,64 | "38 回 0 差异""38 文件 0 error" | 当前 32 章/64 文件；"38"是 19 章文件的旧口径 | 部分成立（口径已过时） |
| 37:76 | "待办池全部清零" | docs/39-41 随即开启缺口补标/金标清洗/外部复核新待办 | 已过时 |

### 3.7 `docs/38-41`（020-032 批次、缺口、001 复标、Qwen 复核）

| 出处 | 声明 | 可验证事实 | 结论 |
|---|---|---|---|
| 38:3 | "001-019 回为金标准，**不动**" | 38:55,172 明确修改 012-019（标点外置/类型修正）；docs/40 又指 001 有 212 处旧口径 | **不成立**（同文自相矛盾） |
| 38:6-7 | 13/13 产出、脚本内复验 PASS、五门 lint 全绿 | 13 个 tagged 在；复跑 `check` exit 0 | 成立 |
| 38:31 | 生产提示词 v1.8、10,519 字 | prompt 正文 10,519 ✓；但 17 份 token_usage JSON 的 `prompt` 字段均记 **"SKILL_03a v1.1"**（脚本从 §二标题提取） | 部分成立（实际用稿版本标识混乱） |
| 38:33 | 映射表 251 条 | `logs/mapping_frozen_20261104.json` 数组=251 | 成立 |
| 38:77 | 合计 1,171 段/165,275 字/9,887E/2,348V/36R | 逐项实测一致（E/V/R 从 tagged 计数，字/调用从 token_usage 汇总） | 成立 |
| 38:87 | 32/32 回齐备、覆盖率 28.36%（96,020/338,586） | coverage 报告同值；96=32×3 文件 | 成立 |
| 38:112 | 合计 $0.651138（≈¥4.62） | token_usage 020-032 `cost_usd` 合计 **0.648257** + 修辞 **0.002881** = **0.651138**（精确命中） | 成立 |
| 38:115 | 输入 3,961,515 / 输出 356,163 / 缓存 3,291,134（83.1%） | 逐次 usage 累计精确命中；调用 338 次亦命中 | 成立 |
| 38:119-121 | 019 校准 3 次≈$0.076；session≈$0.83 | 019 三份合计 $0.0757；可复算总支出约 $0.809（不含未落盘的 020 重跑），与"≈0.83"大致相符 | 成立（估算） |
| 38:130 | "全 32 回、**52 文件**" | `logs/check_full_20261104.log:6,1162` 明写"回文件数: **64**" | **不成立**（计数错） |
| 38:131 | 019 重标 E=477/V=132 vs 金标准 942/145 | token_usage 019 首份 E=477/V=132；tagged 019=942/145 | 成立 |
| 38:137-138 | 金标准 9.77 vs 本批 5.98 | 22,844/233,772×100=9.77；9,887/165,275×100=5.98 | 成立 |
| 38:177-179 | 状态 `structurally_valid`，accepted 未做 | 无 020-032 accepted 记录；这是当前真实状态 | 成立（自认未收口） |
| 38:208 | 文末"（待填）" | 文件尾残留未完成占位 | **不成立**（文档未收尾） |
| 39:3-8 | 缺口 61%、$/# 占 56%、5 条归因、S1-S5 | 5.98/9.77=61%；其余为派生数据；方案 S1 identity.json 等未落地 | 成立（分析）/方案属规划 |
| 39:67 | few-shot 只取 001/003 早期种子 | `build_03a_fewshot.py:19-20` 仅 S001/S003 | 成立 |
| 39:159 | P0 本轮已完成 | docs/38 批次+本文件均在 | 成立 |
| 40:17-19 | 001 金标准 1,831E+130V、新标注 1,013E+168V、73 段/16,881 字 | tagged 001=1,831/130；`logs/_eval_001/001.tagged.md`=1,013/168；001.struct pn_total=73；token_usage chars=16,881 | 成立 |
| 40:170-180 | "对 docs/39 补标方案的修正（新增 3 条）" | 仅写在 docs/40；`docs/39` mtime 17:46 **早于** docs/40 18:11，全文无 docs/40/校准集/holdout/微动作负例引用 | 不成立（未回写 docs/39） |
| 41:5-9 | Qwen 调用：58,190 字/44,863 tok/4,246 tok/172s/$0.00747 | `logs/qa/qwen_review_001.meta.json` 完全一致 | 成立 |
| 41:38-44 | 5 项"经核验成立→采纳"；处理=删除该标/补入负例表 | `logs/_eval_001/001.tagged.md`（mtime 17:55）仍含 `⊠凌迟` 1 处；`wordlists/verbs.json` **无 `negative` 字段**；无任何"负例表"文件；18:12 后无相关文件修改 | **不成立**（未执行） |
| 41:93-94 | P0/P1/P2 建议 | 无对应落地文件（identity.json 不存在、无 S2 重建、无评测门脚本） | 属规划（未执行） |

### 3.8 索引文档与对照文档

| 出处 | 声明/现状 | 可验证事实 | 结论 |
|---|---|---|---|
| 根 README:6-19 | 文档索引（仅 01-06、38-41 共 10 行） | `docs/` 实测 44 篇；**缺 07-37 共 33 篇**（含 07×2、24×2 编号冲突）+ `_tmp_qa_20_32.md` | **不成立**（索引不完整） |
| 根 README:18 | docs/40"并修正 docs/39 方案 3 条" | docs/39 未改动（见上） | **不成立**（夸大） |
| skills/README:61 vs :67 | 同一 03a 节先写"few-shot 8 块"、后写"9 块" | 实际 9 块（FS1-FS9） | 内部矛盾 |
| skills/README:67 | SKILL_03a "v1.5（主文件）" | 实际含 v1.6/v1.7/v1.8 修订（`SKILL_03a:74-75`） | **不成立**（落后 3 个版本） |
| skills/README:67 | 03a 缺陷库 DEF-01~10 | 实际 DEF-01~13 | **不成立**（少 3 项） |
| skills/README:49 | SKILL_04f "v0.3-draft（主文件）" | 正文 v2.1 条款已在；头/尾仍 v0.3-draft；docs/33 称 v2.1 | 部分成立（版本标识不统一） |
| skills/README:178 | "12 份主文件 v0.3-draft 齐备" | 文件齐；但 03a/04f 已多次修订，非统一 v0.3 | 部分成立 |
| skills/README:19-37 | 12 件行数（410/305/…/292） | 逐文件 `(Get-Content).Count` **12/12 完全一致** | 成立 |
| scripts/README:37 | "P1 进行中" | P1 已完成（18+2 脚本、pipeline、SKILL 全在） | **已过时** |
| scripts/README:38 | "待排 N3-N11" | N1/N2 已完成；N3-N10 仍缺；表述未更新 | 部分过时 |
| scripts/README:25-32 | 四张词表（verbs 165/sm 10/stopwords 18/time 19），stopwords"已核准" | 首批准实为 **5 表**（含 quantity 36）；sm 实 12；后续又加 rhetoric 49、fossil 3；stopwords 18 条中仅 15 条"已核准"、3 条"待审" | **不成立**（表数/条数/状态均不符） |
| scripts/README:44 | annotate_llm.py 为主执行器 | 批产执行器已是 `annotate_chapter_llm.py`（docs/38），README 未登记 | 已过时（缺新增脚本） |
| prompts/README:30 | `compact/_compact_T05..T12.md` | 实有 6 份（T05/T06/T07/T08/T11/T12）；T09/T10 为直投无 compact | 部分成立（范围写法过宽） |
| docs/02:104 | "实体类型体系：10 类定版" | `scripts/symbols.py` `ENTITIES=15`、VERBS=6 | **已过时**（被 docs/06/01g 取代） |
| docs/02:206-215 | P0-P6 路线图（骨架/规范定版/lint/存量/反思/试点/SKU） | 与 docs/17 P0-P6 同名异义；其 P0 骨架产物 `CLAUDE.md`、`skills/INDEX.md`、`templates/`、`SKILL_00_管线总览.md` 在本仓库及上级目录均**不存在** | 已过时/未声明作废 |
| docs/06:219-226 | 12 项排除事项（03a、S-03c 等） | 03a 已解锁完成；S-03c、词表填充、Lint 家族等仍排除 | 部分成立（未标完成状态） |

---

## ④ 过时文档清单（文档现状 vs 实际状态 vs 建议回写）

| 文档 | 文档现状 | 实际状态 | 类型 | 建议回写 |
|---|---|---|---|---|
| `docs/17` §七 | 止于 2026-11-03"P0-P1 完成、下一波 P2 入口" | 已过 G0/G1、完成 P3 产物；P2 部分、P4 未启动 | 过时 | 新增 §八"2026-11-04 进度"：G0/G1 收口、32/32 回产出、020-032 `structurally_valid`、P2 缺口清单；把 §七 标"历史快照" |
| `docs/19` | 通篇"P2-P5 待完成"、G1 待办、amd xval 数字错误 | P3 已跑、G1 已闭；amd 文件 136E+4V 且完整性 FAIL | 过时+错误 | 封面改"历史 Session 记录（2026-11-03）"；修正 amd 数字；或文首加"后续见 docs/24-41" |
| `docs/26` | R-013"未决"、待办 5 项 | 已终裁并关闭（docs/34/27） | 过时（历史记录） | 加"已被 docs/34 §三终裁"指针 |
| `docs/27` | 哈希"全部一致"、SHIJI 死常量、v0.3 分布 56/9/5、DEF-14 已入库 | 哈希失配、非死常量、61/9/0、DEF-14 未入库 | 过时+错误 | §七.1 改为"截至 11-04 02:09 校验结果"；加注"15:22 后 003 变更待重跑"；修 DEF-14/SHIJI 表述 |
| `docs/29/30/31/32/28` | 004=171V、SM=9,093、DEF-14 等 | 004=172V（docs/33）；SM 当前 10,519；DEF-14 不存在 | 历史快照，个别错误 | 统一加"历史批次快照"；DEF-14 补入 03a 或改称"DEF 候选" |
| `docs/34/36/37` | "38 回/38 文件""修辞 53 待办""待办清零" | 现 64 文件/32 章；53 已核定（docs/35）；新待办已开 | 口径过时 | "38 回"→"当时 19 章×2 文件=38 个文件"；"待办清零"加"后被 docs/39 重启" |
| `docs/38` | "金标准不动"、52 文件、文末"（待填）"、prompt 标 v1.8 | 012-019 被改动；实 64 文件；文末占位；运行日志记 v1.1 | 内部矛盾+未收尾 | 删"不动"或改"不整章重标，仅机械修复 012-019"；52→64；补收尾；prompt 版本随 03a 标题修正 |
| `docs/39` | 17:46 生成；S1-S5 方案 | 未包含 docs/40 §八 3 条修正；S1（identity.json）等未建 | 需增量回写 | 追加 §六"docs/40/41 回写"：v1.8 校准集、@ holdout、动词微动作负例表三条 + 状态 |
| `docs/40` | 含"修正 docs/39 3 条"（§八） | 只写在本文件，未回写 docs/39 | 悬空 | 把 §八 3 条并入 docs/39（或把 README 改成"提出 3 条修正"） |
| `docs/41` | §三 5 项"采纳→删除/补负例表" | eval 001 未改（mtime 17:55）、无负例表、verbs.json 无 negative 字段 | 未执行 | 要么执行并改 eval 文件/词表，要么把"处理"列改成"建议（未执行）" |
| 根 `README.md` | 索引仅 01-06、38-41 | 44 篇文档、33 篇未索引 | 不完整 | 补 07-37（07 与 24 需加后缀区分）+ 标注 `_tmp`；索引改为分组（设计/评审/执行/复盘） |
| `skills/README.md` | 03a v1.5、DEF-01~10、8/9 块混写 | 03a v1.8、DEF-01~13、9 块 | 过时 | 更新版本/缺陷库/块数；04f 标"v2.1（正文），文件头待统一" |
| `scripts/README.md` | "P1 进行中/待排 N3-N11"、四表 | P1 完成；5+2 表；缺新增执行器 | 过时 | 重写"波次对照"为 P0-P3 现状；补 quantity/rhetoric/fossil 与 8 个 11-04 新增脚本 |
| `prompts/README.md` | compact"T05..T12" | 实 6 份（T09/T10 直投） | 表述不精确 | 改为逐文件列 6 份并说明 T09/T10 无需适配 |
| `docs/02` | 10 类定版、P0-P6 路线图、P0 骨架含 CLAUDE.md/INDEX/templates | 实际 15 类、执行走 docs/17 波次、骨架产物未建 | 被取代 | 文首加"已被 docs/17/docs/06 取代，路线图仅历史参考"；或更新 10→15 类 |
| `docs/06` | 12 项排除项未标完成 | 12 项已交付，03a 已解锁 | 部分过时 | 给排除表加"完成/仍排除"列 |
| `tagged/_xval/README.md` | 只登记到 `_annotate_006` | 存有 `_annotate_007-019`、`_verbfy_1819*`、`_fix_006*` 等 | 漏登记 | 补登 007-019 一次性脚本与 007-019 标注来源说明 |

---

## ⑤ 悬空/未登记产物（双向）

### 5.1 文档引用但文件不存在（悬空）

| 引用位置 | 被引用对象 | 实际 | 证据 |
|---|---|---|---|
| `docs/07-SKILL_04a-…md:5,39,113,140,144` | `backup/backup/skills/...`（双 `backup/`） | 实际只存在 `backup/skills/`，无 `backup/backup/` | `Test-Path backup\backup`=False；`backup\skills` 54 文件 |
| `docs/38:177` | `tagged/白发魔女传/020-032.tagged.md`（单文件） | 实际为 020…032 共 13 个文件 | `Test-Path` 该字面路径=False |
| `docs/27:186`；`docs/31:8,156` | DEF-14（缺陷库条目） | `SKILL_03a` 仅 DEF-01~13 | `Select-String 'DEF-14'` 在 skills/ 零命中 |
| `docs/39:117` | `wordlists/identity.json` | 不存在（S1 方案未执行） | `Test-Path`=False |
| `docs/17:368` | `skills/META-13/08/10/04_武侠版.md`（字面路径） | 实为 4 个独立文件，非该路径 | `Test-Path`=False（属简写，可读性缺陷） |
| `docs/02:57,206-208` | `CLAUDE.md`、`skills/INDEX.md`、`templates/`、`scripts/migrate_v1_0.py`、`scripts/build_kb_stats.py` | 均不存在（规划产物） | `Test-Path` 全部 False（属"范围声明"，但未标规划状态） |
| `docs/01:55,160,188` | `skills/SKILL_00_管线总览.md`、`skills/INDEX.md`、`scripts/lint_whitelist.txt` 等 | 这些是 shiji-kb 源仓库对象，不在本仓库 | 需在文档中明示"shiji 侧路径"，否则读者误判悬空 |

### 5.2 文件存在但文档未登记

| 产物 | 数量/状态 | 缺登记点 |
|---|---|---|
| `docs/07`(两份)、`docs/08-37` | **33 篇**编号文档未进根 README 索引（07、24 各两份，编号冲突） | 根 README:6-19 |
| `docs/_tmp_qa_20_32.md` | 1 篇临时文件，无任何登记 | 根 README / docs 索引 |
| `tagged/白发魔女传/007-019.tagged.md` | 13 回产物存在（E 米 1,182/844/1,362/…/942），但**无任何执行记录/验收文档**；只有 `docs/38:24` 一句"已按 v1.5-v1.8 精标" | docs/ 无对应批次记录；`tagged/_xval/README.md` 未登记 `_annotate_007-019.py`、`_verbfy_1819.py` |
| `logs/_bak012/019/020.tagged.md` | 3 份修复前备份（019: 938E→942E；020: 1028E→1048E） | 无备份登记文档（只在操作过程隐含） |
| `logs/qa/qa_020.md`、`logs/qa/qa_test.md`、`logs/_survey_stats.json` | 中间产物 | docs/ 零引用 |
| `wordlists/rhetoric.json`、`rhetoric_candidates_v0.json`、`fossil_verb_objects.json` | 3 个 11-04 新增表/池 | `scripts/README.md` 词表清单未登记；无 `wordlists/README.md` |
| `registry/structure/白发魔女传/*.structure.json`、`registry/sections_data.json` | 18:28 新增 32+1 件 | 无文档登记（可能是并发任务产物） |
| `logs/yunwen/`、`logs/entity_stats/` | 18:28 新增产物 | 无文档登记（docs/17 只提阶段名） |
| `backup/skills/` 54 文件 | `_v1/_v2` 存档 + `_raw_04a_v2` | `skills/README` 有迁移说明，但无完整清单（可接受） |
| `scripts/` 11-04 新增 8 件（annotate_chapter_llm、annotate_rhetoric_llm、analyze_annotation_gap、compare_annotation_gold、fix_annotation_mechanical、qa_annotation_report、qwen_review_chapter、summarize_annotate_cost） | 批产/复核对账脚本 | `scripts/README.md` 未登记（仍只列 annotate_llm/xval_analyze/build_03a_fewshot） |

### 5.3 编号/索引冲突

- `docs/07` 同时存在 `07-SKILL_04a-双稿对比分析与合并记录.md` 与 `07-SKILL_04f双稿对比分析与合并说明.md`。
- `docs/24` 同时存在 `24-003回标注修订说明.md` 与 `24-G1收口-few-shot提取与SKILL_03a产出.md`。
- 根 README 的 `docs/07` 链接指向 04f 篇（prompts/README:8 也指向 04f），而 skills/README:73 指向 04a 篇——同一编号被两处索引到不同文件，读者无法从编号定位。
- `docs/38:24` 的"文档资历"列表漏 docs/29/30；`docs/38:206`、`docs/40:197-198`、`docs/41:98` 均以 `docs/39` 等编号简写，尚可读但不利机器对账。

---

## ⑥ 统计数字与复算命令

> 以下为 2026-11-04 18:40 快照；`tagged/` 最大 mtime 16:24:22，`docs/` 最大 mtime 18:12（docs/41），均早于审计时刻。

| 对象 | 实测 | 复算命令（PowerShell / Python） |
|---|---|---|
| docs 文档数 | **44**（43 篇编号 + `_tmp_qa_20_32.md`；编号 01-41，07/24 各重复一次） | `(Get-ChildItem docs -File).Count` |
| 根 README 已索引 docs | **10**（01-06、38-41）；未索引 **33** 篇（07-37） | `Select-String README.md 'docs/\d\d'` |
| prompts | T01-T12 = **12**；A1/A2 = 2；compact = **6**（T05-08/T11/T12）；共 21 文件 | `(Get-ChildItem prompts -File -Filter 'T*.md').Count` |
| wordlists | **13 文件 = 5 源 + 7 编译表 + 1 候选池**；条数：verbs 165、structure_markers **12**、stopwords 18、time_words 19、quantity 36、rhetoric **49**、fossil_verb_objects **3**；rhetoric_candidates_v0 **53** | `python -c "import json;[print(f, len(json.load(open('wordlists/'+f,encoding='utf-8'))['items'])) for f in [...]]"` |
| registry | `entities.json` **70 条**（approved 61 / proposed 9 / pending 0）；文件内 `version` 仍 `0.1-draft` | `python -c "...groupby status"` |
| mapping_frozen | **251** 条 | `(Get-Content logs/mapping_frozen_20261104.json -Raw | ConvertFrom-Json).Count` |
| tagged 主区 | **96 文件 = 32 章 × (.tagged.md/.struct.md/.struct.json)**；E **32,731**、V **5,869**、R **115** | 见附录 A-1 |
| 001-019 金标准 | E **22,844**、V **3,521**、R **79** | 同上 |
| 020-032 机器初稿 | E **9,887**、V **2,348**、R **36**（与 docs/38 表逐项一致） | 同上 |
| PN | 合计 **2,263**；`reversibility=pass` **32/32** | 附录 A-2 |
| 标注覆盖率 | 汉字 **338,586**，已标 **96,020**，**28.36%**（与 coverage 报告一致） | `logs/coverage/汉字标注覆盖率统计报告_20261104.md` |
| 五门 lint | 复跑 `check` exit **0**；`logs/check_full_20261104.log:6` 记 **64 回文件** | `python scripts/pipeline_wuxia.py 白发魔女传 check` |
| 020-032 费用 | annotate **$0.648257** + rhetoric **$0.002881** = **$0.651138**；338 次调用；入 3,961,515 / 出 356,163 tok（cache 3,291,134，83.1%） | 附录 A-3 |
| 修辞层 | 001-019 落标 **79** 处；rhetoric token_usage 3 份合计 **$0.010166** | 附录 A-1/A-3 |
| 语料 | `章回版/` **34** 个书目录；`白发魔女传/` **32** 个章回文件；指纹 concat-sha256[:16]=`3843aeb3e2b0e4b4` | 附录 A-4 |
| skills | 26 个 md（12 设计 + 8 管线 + 4 META + 03a/04a/04f）+ README | `(Get-ChildItem skills -File).Count` |
| scripts | 37 个 .py + README；`_oneshot/` 5 个 | `(Get-ChildItem scripts -File).Count` |
| logs | 100 个文件（含 token_usage 21、annotate report 15） | `(Get-ChildItem logs -Recurse -File).Count` |

---

## ⑦ 对 README / docs/17 的回写建议（按优先级）

**P0（当天可做，避免继续误读）**
1. **根 README**：把"文档索引"从 10 行扩为全量分组索引：`01-06 设计稿`、`07-16 双稿合并`、`17-19 实现/进度`、`20-24 种子与 G1`、`25-32 试点与评审`、`33-37 定例/修辞`、`38-41 20-32 批/缺口/001 复核`；为重复编号加 `(04a)/(04f)`、`(003 修订)/(G1 收口)` 后缀；把 `_tmp_qa_20_32.md` 标"临时"或移出 docs。
2. **docs/17 新增 §八**："2026-11-04 进度（G0/G1 收口、P3 32/32 产出、020-032 仅 structurally_valid、P2 未建节点清单）"，并把 §七 标"2026-11-03 历史快照"；更正 §七 的 structure_markers 10→12、"四表"→"五表"、verse 78→"99 行（78 完整/21 缺列）"。
3. **docs/19 封面**加"历史 Session 记录（截至 2026-11-03），后续见 docs/24-41"；更正 amd xval 数字为 `amd_001.E.md 82E+0V（完整性 FAIL）`、`amd_001.EV.md 136E+4V（完整性 FAIL）`，删除"82E+54V 保真全过"。
4. **skills/README**：SKILL_03a 版本 v1.5→**v1.8**；DEF-01~10→**DEF-01~13（DEF-14 未入库）**；"few-shot 8 块/9 块"统一为 9；SKILL_04f 标"v2.1（正文）/v0.3-draft（文件头，待统一）"。
5. **scripts/README**："P1 进行中→P0/P1 完成、P2 部分、P3 产物完成"；词表清单补 quantity/rhetoric/fossil 并按"5 源 + 7 编译表"表述；补登 11-04 的 8 个新脚本。

**P1（随下一次标注批次做）**
6. **修复 03a 版本锁定闭环**：构建器增加 `prompt_version` 回填；重跑 `build_03a_fewshot.py`（种子 003 已在 docs/37 变更），并把 §二标题改为当前版本；此后每次改种子/规则都重跑并复核 6 项哈希。
7. **DEF-14 入库**（03a §四.2）或把 docs/27/31 的引用改为"DEF-14 候选，未入库"。
8. **docs/39 回写 docs/40 §八 3 条**（v1.8 校准集、@ 映射 holdout、动词微动作负例表），并更新 README"修正 3 条"为"提出 3 条（已回写 docs/39）"；同步把 docs/41 P0-1 负例表落成 `wordlists/verb_negatives.json`（或在 verbs.json 增加 `negative` 字段），修正 docs/40 §八"reuse 现有 negative 字段"与实物不符的前提。
9. **docs/38 收尾**：删"（待填）"；"52 文件"→"64 文件"；"001-019 不动"改为"不整章重标，仅机械修复 012-019 的 9 处标点+1 处类型"。
10. **registry 版本字段**：`entities.json` `version` 0.1-draft→0.3（或与 docs 说法对齐）；补 `wordlists/README.md` 登记 7 表与状态。

**P2（质量门/收口）**
11. 建立 S-03c（按章反思）最小 skill 与 `review` 阶段执行件，把 docs/26/34 的规律条目变成可消费产物。
12. 020-032 的 accepted 验收：按 docs/39 S5（四类通名 + 高风险项，10% 抽样）执行并回写每回状态；处理 13 处 verse 存疑（021/022/024/027/031/032）。
13. 修 docs/07 的 `backup/backup/` 双前缀；给 007-019 补一份批次执行记录（含 `_annotate_007-019.py`/`_verbfy_1819` 的用途与产物对账）。

---

## 附录 A · 复算命令

**A-1 tag 计数（E/V/R）**
```powershell
python -c "
import re,glob,os
E=V=R=0
for f in sorted(glob.glob('tagged/白发魔女传/*.tagged.md')):
    t=open(f,encoding='utf-8').read()
    e=len(re.findall(r'〖',t)); v=len(re.findall(r'⟦',t)); r=len(re.findall(r'〘',t))
    E+=e; V+=v; R+=r
    print(os.path.basename(f)[:3],e,v,r)
print('TOTAL',E,V,R)"
```
**A-2 PN 与可逆性**
```powershell
python -c "
import json,glob
tot=ok=0
for f in glob.glob('tagged/白发魔女传/*.struct.json'):
    j=json.load(open(f,encoding='utf-8')); tot+=j['pn_total']; ok+=j.get('reversibility')=='pass'
print(tot,ok)"
```
**A-3 费用/token 汇总**
```powershell
python -c "
import json,glob
c=0; calls=0; inp=hit=out=0
for f in glob.glob('logs/token_usage/annotate_*.json'):
    j=json.load(open(f,encoding='utf-8'))
    if 20<=j['chapter']<=32:
        c+=j['cost_usd']
        for u in j['usage']:
            calls+=1; inp+=u['prompt_tokens']; hit+=u['prompt_cache_hit_tokens']; out+=u['completion_tokens']
print(round(c,6),calls,inp,out,round(hit/inp*100,1))"
```
**A-4 底本指纹**
```powershell
python -c "
import hashlib,glob
h=hashlib.sha256()
for f in sorted(glob.glob('../章回版/白发魔女传/*')): h.update(open(f,'rb').read())
print(h.hexdigest()[:16])"
```
**A-5 manifest 哈希对账**
```powershell
python -c "
import hashlib
for f in ['skills/SKILL_01g_标注符号集合原则.md','skills/SKILL_04f_动词标注.md','docs/21-第一回标注修订说明.md','scripts/symbols.py','tagged/_xval/glm_001.EV.v2.md','tagged/白发魔女传/003.tagged.md']:
    print(f, hashlib.sha256(open(f,'rb').read()).hexdigest()[:12])"
```

## 附录 B · 审计限制与未做项

- **未运行任何 LLM**；未运行 `scripts/build_03a_fewshot.py`（会改写 `skills/SKILL_03a_实体标注.md`，超出本任务写权限），03a 的 few-shot 质量只做哈希/版本对账。
- **未重标/未改任何 tagged**；`logs/_eval_001/001.tagged.md` 原样保留，仅用于验证 docs/41 的"删除该标"是否执行。
- 并发任务在 18:26-18:31 生成了 `registry/structure/`、`logs/yunwen/`、`logs/entity_stats/`、`logs/verse_scan/…_001-001.md` 等；本报告已区分"审计前已有"与"并发新增"，未把并发产物计入 docs 声称的完成度。
- `docs/03/04/05/07-16` 等设计/评审文档只做了抽读与路径核对，未逐句审计其技术论断（不在 task-3 的进度声明范围）。
