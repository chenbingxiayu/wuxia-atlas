---
name: skill-10e-wuxia
title: 文件组织与目录结构（武侠版）——从 shiji 目录映射到 wuxia-kb 双区结构
description: 武侠知识库的文件组织规范：核心原则（职责分离/语义清晰/避免污染）照搬自 shiji §1，目录结构按 wuxia-kb 实际双区结构重写——新管线 wuxia-kb/（tagged/registry/wordlists/skills/references/scripts/docs/logs 等）为唯一真源，仓库根 kb/ 与旧 site/ 为冻结只读区；含文件创建决策树、九类常见错放案例（全部取自本项目实测）、根目录文件清单与 Git 管理口径。当不确定一个新文件该放哪、或发现文件放错位置时使用。
version: v0.1-draft
last_updated: 2026-11-06
---

# SKILL_10e 文件组织与目录结构（武侠版）

> **上游声明**：本文从 shiji-kb `skills/SKILL_10e_文件组织与目录结构.md` 移植改写（🟡 中度——§1 核心原则照搬，§2 起按 `docs/03-skill与脚本改造清单.md` L175"仅 10e 按目录映射改写"以 wuxia-kb 实际结构重写；§4 错误清单换用本项目实测案例）。

---

## 1. 核心原则（照搬自 shiji §1）

1. **职责分离**：区分"公开展示"与"内部工作"内容
2. **面向未来**：目录结构应具有可扩展性和通用性
3. **语义清晰**：目录命名准确反映其用途
4. **避免污染**：工作文档不应进入发布目录
5. **机器产物与人类文档分家**：`logs/` 只放机器生成的产物（lint 输出、acceptance JSON、备份、qa 报告），一切人类撰写的规范/反思/批次记录进 `docs/`（武侠版对应 shiji 的 `doc/`，编号文档制）

---

## 2. 标准目录结构（武侠版重写）

### 2.1 双区总览

```
Wuxiaxiaoshuo/                     # 仓库根
├── 章回版/                        # 锁定底本（34 部书 txt，只读；config.CORPUS_ROOT）
├── wuxia-kb/                      # ★ 新管线 = 唯一真源（本文件所言"项目根"均指这里）
│   ├── corpus 产物入口：tagged/    # 标注语料 + struct（tagged/<书>/NNN.tagged.md / .struct.md）
│   ├── registry/                  # 登记层：entities.json、sku/、acceptance/、concordance/、
│   │                              #   consistency/、patches/（全部脚本产物+人工核定层）
│   ├── wordlists/                 # 词表编译表（*.json + *_source.md，wordlist_compiler 管控）
│   ├── content/                   # SKU 展示层（person/faction/art/artifact/manual）
│   ├── skills/                    # 方法层：SKILL 69 + META 14 + W 16 + README（+本文件）
│   ├── references/                # 规律库 27 库 / templates/ 2 件
│   ├── scripts/                   # 正式脚本 87 个 .py；_oneshot/ 26 件历史一次性存档（不再更新）
│   ├── docs/                      # 人类文档：NN-*.md 编号执行记录（现 71 篇）、审计、设计
│   ├── design/                    # 设计稿（D01-D12 + 页面稿 dc.html；运行期 .log/.json 勿提交）
│   ├── prompts/                   # 提示词存档（A1/A2 v0 等）
│   ├── logs/                      # 机器产物：qa/、backup/、annotate/、acceptance/、export/…
│   ├── backup/                    # 历史备份快照（corpus_titleline_*、site_data/apply_*）
│   └── templates/                 # （并入 skills/templates/ 后保留兼容）
├── kb/                            # 旧管线冻结区（v0.2 标注 + 旧登记表，只读；映射快照来源）
├── site/                          # Astro 站点（site/data/ 14 个 JSON 契约 = EX 导出层产物）
├── designs/                       # 旧设计区（wuxia-atlas 等，只读）
└── scripts/                       # 仓库根散件（split_chapters.py 等入库前工具）
```

### 2.2 shiji → wuxia 概念映射表（读 shiji 原文时按此换算）

| shiji 目录 | wuxia-kb 对应 | 说明 |
|---|---|---|
| `data/`（核心数据资产） | `tagged/` + `registry/` + `wordlists/` + `content/` | 标注语料、登记层、词表、展示层 |
| `docs/`（公开发布站） | 仓库根 `site/`（Astro 构建产物 `site/dist/`） | 发布走 `scripts/release_site.py` |
| `doc/`（项目工作文档） | `wuxia-kb/docs/`（NN-*.md 编号制） | 反思/批次记录/审计全在这 |
| `labs/`（实验区） | `design/` + `scripts/_oneshot/` + `_qwen_标注对比/` | 设计稿与一次性实验；定稿升 `scripts/`（docs/50 S12 先例） |
| `resources/`（静态资料） | `design/`（dc.html 设计稿）+ `docs/`（方法论长文） | 无独立 publications 区 |
| `scripts/` | `wuxia-kb/scripts/` | 一次性实验脚本不进 `scripts/`（先进 `_oneshot/`，确需保留再正式化+README 登记） |
| `logs/`（仅 IT 日志） | `wuxia-kb/logs/` | 机器产物；qa 报告虽人类可读，但属脚本产物 |
| `archive/`（历史存档） | `backup/` + `kb/`（冻结）+ `tagged/_xval/`（旧试点备份） | 三处各有语义：备份/冻结/交叉验证留档 |

### 2.3 放置判据（快速三问）

1. **是脚本产物还是人写的？** 脚本产物 → `logs/`（或直接写 `registry/`）；人写的 → `docs/`
2. **是正式工具还是一次性实验？** 会再用的 → `scripts/` + `scripts/README.md` 登记；一次性的 → `_oneshot/` 或就地 `_tmp_*`
3. **新管线真源还是旧区？** 一切新产物只进 `wuxia-kb/`；`kb/`、旧 `site/`、`designs/` 只读（E 组方案 C 冻结，docs/51）

---

## 3. 文件创建决策树（武侠版）

```text
要创建一个新文件？
├─ 是代码（.py/.ps1）？
│  ├─ 会复用/属管线阶段 → scripts/ + README 登记（py_compile 过）
│  └─ 一次性 → scripts/_oneshot/（docstring 写清背景与日期）
├─ 是人写的文字？
│  ├─ 批次执行记录/收口 → docs/NN-*.md（编号续号，不回改历史编号）
│  ├─ 方法规范（SKILL） → skills/（templates/SKILL_template.md 起稿，lint PASS）
│  ├─ 规律条目 → references/（对应 XX1_规律库，frontmatter 计数同步）
│  └─ 设计讨论稿 → docs/（若成稿编号）或 design/（画布稿）
├─ 是脚本产出的数据/报告？
│  ├─ 登记层实体/卡/验收 → registry/
│  ├─ 语料标注 → tagged/<书>/
│  ├─ 词表 → wordlists/（.json + *_source.md 成对）
│  └─ 其余报告/备份/账本 → logs/
└─ 是配置/密钥？ → $KB 根（.api_config.json/.token_cost_config.json，已 gitignore）
```

---

## 4. 常见错误与纠正（本项目实测案例）

### ❌ 错误1：一次性脚本留在 `logs/` 里当正式工具
- **实测**：`logs/_repair_titleline.py`（书名行修复）长期散在 logs/
- **纠正**：正式化为 `scripts/repair_corpus_titleline.py`（docs/50 S3 落地）
- **原因**：`logs/` 只放产物；可复用工具属 `scripts/`

### ❌ 错误2：换书必需工具长期滞留 `_oneshot/`
- **实测**：`build_legacy_mapping`/`verify_batch`/`rebuild_tagged_from_struct` 等 7 件
- **纠正**：参数化迁入 `scripts/`（2026-11-06 批次，`scripts/README.md` 已登记；`_oneshot/` 原件保留为历史存档）
- **原因**：每本新书都要用的工具不是一次性工具

### ❌ 错误3：运行期文件混进提交清单
- **实测**：`design/.artifact-server.json/.log`、`.token_cost_config.json`（docs/66 补记 P0 待排除项）
- **纠正**：加入 `.gitignore` 或提交白名单排除
- **原因**：运行期状态不属于版本资产

### ❌ 错误4：人写的分析报告写进 `logs/` 后当作权威文档引用
- **实测**：早期 gap 分析散在 `logs/audit_*/`——引用时必须注明"快照时点"，权威口径以 `docs/NN` 为准（docs/66 §一 权威顺序）
- **纠正**：结论性内容升入 `docs/NN` 编号文档；`logs/` 版本只作证据
- **原因**：`logs/` 无版本治理，会被后续批次覆盖

### ❌ 错误5：标注候选/补丁 TSV 写进 `docs/` 或 `skills/`
- **纠正**：候选与补丁 TSV → `registry/patches/<书>/`（docs/47 §7.5 后按书分目录）
- **原因**：结构化数据归登记层

### ❌ 错误6：并发会话直接改冻结区
- **实测风险**：`kb/`、旧 `site/data/` 冻结后仍有旧管线脚本可写（E 组方案 C，docs/51）
- **纠正**：新产物一律走 EX 导出器写 `site/data/`；冻结区只读
- **原因**：双真源是最大一致性风险

---

## 5. 根目录文件（wuxia-kb）

**应在 `$KB` 根**：`.gitignore`、`.api_config.json`/`.token_cost_config.json`（敏感，已 ignore）、`README.md`（如有）

**不应在根**：工作文档 → `docs/`；临时脚本 → `_oneshot/` 或删除；产物 → `logs/`

**仓库根（`Wuxiaxiaoshuo/`）另有**：`site/`、`kb/`、`章回版/`、`designs/`——均非 `$KB` 新管线真源，注意相对路径基准（`config.REPO_ROOT` = 仓库根，`config.DIR_*` 指向 `$KB` 内）。

---

## 6. Git 管理建议（武侠版）

- **纳入版本管理**：`skills/`、`references/`、`templates/`、`scripts/`（含 `_oneshot/` 历史存档）、`docs/`、`wordlists/`、`registry/`（登记层资产）、`tagged/`（标注语料）、`design/`（设计稿本体）
- **排除**：`logs/`（机器产物，防 466MB 膨胀——docs/65 白名单口径）、`backup/`、`site/dist*`、`.api_config.json`、`.token_cost_config.json`、`design/` 运行期 `.log/.json`、`__pycache__`
- **提交纪律**：白名单制 + dry-run 先行 + 用户拍板（见 `SKILL_10c_Git代码版本管理规范_武侠版.md`）

---

## 7. 检查清单

- [ ] 新文件按 §3 决策树落位（脚本/文字/产物/配置四分）
- [ ] 正式脚本已登记 `scripts/README.md`；一次性脚本有 docstring 背景说明
- [ ] 人写结论进 `docs/NN`，`logs/` 只作证据引用并注明快照时点
- [ ] 未向冻结区（`kb/`、旧 `site/data/`、`designs/`）写入任何东西
- [ ] 敏感/运行期文件不在提交清单（对照 docs/65 白名单）

## 8. 成功标准

- 新会话/新人按本文件能在 5 分钟内给任意产物找到唯一正确位置
- `logs/` 与 `docs/` 职责不混（机器产物可随时重建，人写文档有编号治理）
- 提交清单不含运行期/敏感文件；仓库不因产物膨胀（docs/65 白名单可复跑）
- lint_skills PASS（score ≥ 90），无 error
