# 46 · Qwen3.8-Flash-Next 外部复核：P2 新生成文件（2026-11-04）

> **任务**：用 Qwen（AMD Radeon API，`Qwen3.8-Flash-Next`）对 P2 新生成的文件做独立评审并给出建议；Lead 对每条意见回读源码/数据核验，剔除误报后汇总。
> **端点**：`https://developer.amd.com.cn/radeon/api/v1`（OpenAI 兼容）；`temperature=0`；**thinking 关闭**（该端点须用 `chat_template_kwargs: {"enable_thinking": false}`，顶层参数无效——初跑曾因 reasoning 吃满 max_tokens 得到半截推理，已修正重跑）。
> **输入**：9 组、18 个文件（8 个新脚本 + pipeline + 3 张词表源 + docs/43/44/45 + 3 份 `docs/_p2` 子报告）；每组 prompt 约 1.0-2.9 万 token。
> **产物**：原始意见 `logs/qa/qwen_max_review/G1…G9.md`（+ 同名 `.json` 含 usage/cost）、汇总 `summary.json`；评审器 `scripts/qwen_review_files.py`。
> **成本**：prompt 162,773 tok / completion 9,790 tok / **合计 $0.025498**；9/9 组成功。
> **纪律**：评审器只读文件；未修改被评审文件（本报告仅新增 + 3 处文档口径补注，见 §五）。

---

## 一、分组结论

| 组 | 文件 | 模型结论 | Lead 核验后判定 |
|---|---|---|---|
| G1 | C16/C17/C19 脚本 | 需返工（P0 位置偏移、C19 首字歧义） | **部分成立**：C19 首字匹配风险属实（潜在）；"位置偏移 P0"降为 P2（C7 不消费 pos，且为显示偏移设计） |
| G2 | C18/C20 脚本 | 需返工（C20 selftest 依赖外部 registry、C18 apply 边界） | **基本成立**：selftest 非 hermetic 属实；C18 `--apply` 会写入围栏/标题（源码确认） |
| G3 | C24 + pipeline | 小修后可接受（run_stage 异常、render_md 空章节崩溃） | **一半成立**：run_stage 缺异常捕获属实；**render_md 空章节已有 ternary 保护 → 误报** |
| G4 | N3 动词校验器 | 小修后可接受（mismatch 栈清理、密度分母） | **部分成立**：mismatch 栈未清属实（脏数据级联）；密度分母无实证问题 |
| G5 | accept_batch 上半 | 需返工（coverage_swap 截断、不可运行） | **误报**：分组按行切分导致"截断"；文件完整、实跑 13/13 |
| G6 | accept_batch 下半 | 需返工（报告硬编码本批事实、裸 except） | **成立**：`render_report` 确有硬编码"032[31][33]…"与"无来源 0 条"；裸 except 属实 |
| G7 | 3 张词表源 | 需返工（C16 通名/父式误收、C17 职衔冲突） | **部分成立**：identity 7 条空 evidence、寨主/宫主/管家类型冲突属实；"天山剑法父式误收"**不采纳**（G-29 允许父术+子式双标）；"轻功"表中不存在 |
| G8 | docs/43/44/45 | 小修后可接受（docs/43 状态滞后、warnings 口径） | **部分成立**：docs/43 正文仍 85 属实（头部已加注）；warnings 差异经查为 22:17/22:19 两次快照 + 检查项增加，已补注说明（非矛盾） |
| G9 | 3 份 P2 子报告 | 可接受（C18 apply 风险、N3 级别文档不同步） | **成立**：N3 报告 §2.2 仍写 E-WL-DOMAIN=error（§七已改默认 warning）→ 已同步；C18 apply 风险与 §四一致 |

**没有一条 P0 被核验为真**（两条 P0 分别是分组截断与已有防护的误报）；**确认的 P1 有 4 项**（见 §二）。

---

## 二、核验后的问题清单（按优先级）

> **修复状态（2026-11-05 00:15–00:40）**：P1 四项**已全部修复并回归**，详见 §七；P2 未动（按需排期）。

### P1（建议修）

| # | 位置 | 问题（已核验） | 建议 |
|---|---|---|---|
| 1 | `scan_untagged_aliases.py:_apply_word` / `do_apply` | **`--apply` 会把词插入围栏块与标题行**：`_apply_word` 只在全文找裸词并跳过"已标注区间"，不跳过围栏/标题；而扫描阶段 `build_masked` 明确跳过这些区域 → apply 与 scan 语义不一致。另：apply 忽略 TSV `pos`，按"同词全插"处理（与 C7 一致，但放大了围栏风险）。 | apply 前复用 `build_masked` 生成掩码区间，或在围栏/标题区间跳过；更稳妥：默认禁止 `--apply`，统一走 C7（C7 同样有全插语义，需先补围栏过滤）。 |
| 2 | `accept_batch.py:render_report`（约 L948、L1000） | **报告硬编码本批事实**：`"020-032 共 … 条 @ 管道，**无来源 0 条**"` 中"0 条"是字面量；`"032[31][33] 卓某→卓一航…"` 为写死案例。换书/换批次会输出错误结论。 | 改为从 `extra["pipe_unsourced_total"]` 等字段动态渲染；具体案例从 `warnings` 列表取前 N 条生成，而不是写死。 |
| 3 | `infer_single_char_names.py:infer_chapter` | **单字人名首字匹配歧义**：`cands = [n for n in names if n[-1] == char or n[0] == char]`；若同回只有"李寻欢"一个李姓多字名，单字"李"会被唯一映射到李寻欢（实际可能指李选侍）。当前语料"新推断 0"（单字基本已挂管道），属**潜在**风险。 | 移除首字匹配，仅保留末字匹配（武侠单字称呼多为名末字）；或首字匹配须有"老/小/阿+姓"或姓氏表佐证。 |
| 4 | `wordlists/identity_source.md` | **7 条 identity 条目 evidence 为空**（坛主/护卫长/军校/驿卒/学徒/舞女/挑夫），与"evidence=书:回"的源规范不一致（compiler 只告警不报错，故未拦）。 | 补 1 条语料证据，或降 conf=weak 并在 note 标"先验/待验证"。 |

### P2（可排期）

| # | 位置 | 问题（已核验） | 建议 |
|---|---|---|---|
| 5 | C16/C17 `scan_chapter` | TSV `pos = display_offset(剥标累计) + masked 行内偏移`，两者基准不同（剥标会去掉标记字符）；docstring 称"剥标显示文本偏移"但实现不是纯显示偏移。C7 不消费 `pos`（只用上下文/全插），故无数据损坏。 | 统一坐标：要么按原文偏移输出（`masked` 行内偏移 + 原文行起点），要么按剥标显示文本重算；并在 TSV 头注明坐标口径。 |
| 6 | `tag_identity_kinship.py:kinship_blocked` | `left.endswith("〗")` 只判断左侧以令牌结尾，未校验该令牌是 `〖@…〗`；若左侧是 `〖#…〗`/`〖☆…〗` 也会放行。 | 解析左侧最后一个令牌，仅 `code=="@"` 视为指称对象。 |
| 7 | `tag_new_entity_types.py:hit_blocked` | 前缀负规则取 `line[pos-1]`，若前一个字符是令牌闭括号（`〗`）则前缀正则失配，负规则可能失效（`ORG_BEFORE_MARTIAL="〖☆"` 的 `startswith` 判断本身正确）。 | 负规则改在 `strip_markup(line)` 上判断上下文，或先把左侧令牌折叠为一个占位符再匹配。 |
| 8 | `detect_entity_boundary_errors.py:selftest` | selftest 传入真实 `registry`/WN（注释自述 P4 依赖"玉罗刹=练霓裳"、P5 依赖"卓仲廉"），非 hermetic；registry 变更会让自检结果漂移。 | 用内置 mock registry 跑 selftest；真实数据另做集成用例。 |
| 9 | `validate_verb_tagging_wuxia.py:scan_structure` | mismatch 且栈中找不到对应开括号时 `continue`，**未清理残留开括号**；后续闭合会级联误报（仅脏数据触发）。 | `idx is None` 时清栈或标记"结构已损坏"并跳过该行剩余检查。 |
| 10 | 多脚本 | `parse_chapters` 对非法输入（`1-abc`、空段）直接 `int()` 崩溃；`load_stopwords`/`load_wn` 对"顶层为 list 的 JSON"会 `data.get` AttributeError（当前文件均为 dict，latent）。 | 统一加友好报错与 list/dict 兼容分支（C0 级小工具可抽公共函数）。 |
| 11 | `pipeline_wuxia.py:run_stage` | 未捕获 `subprocess` 异常（如脚本缺失 `FileNotFoundError`），`check` 会中断而非"逐项记录"。 | `run_stage` 包 `try/except` 返回 -1，保证 check 跑完并汇总。 |
| 12 | `accept_batch.py` | `load_mapping_table` 裸 `except Exception: pass`（静默）；`min(a['sample_ratio_actual'] …)` 在 analyses 为空时 `ValueError`；`fix_annotation_mechanical` 摘要用正则解析 stdout，格式一变即失效。 | 记录 warning 并在报告标注；空集保护；改结构化 JSON 输出。 |
| 13 | `scan_untagged_aliases.py:do_apply` | `stats["tsv"] += 1` 在回循环内，多回 TSV 会计成多次；同章多 TSV 时备份文件名相同会覆盖（同 stamp）。 | 按 TSV 计数、备份名加 TSV 序号。 |
| 14 | `build_entity_concordance.py:load_registry` | registry JSON 损坏时直接抛异常（无友好降级）。 | `try/except JSONDecodeError` → 空 registry + 显式警告。 |
| 15 | `docs/43` / `docs/45` / `C24-N3 报告` | 文档口径：docs/43 正文仍写 judgment 85（头部已注明快照）；warnings 2 vs 0 已查明为 22:17/22:19 两次快照 + 检查项增加；N3 报告 §2.2 仍写 E-WL-DOMAIN=error。 | 已补 3 处注（docs/43 快照口径、docs/45 before 时间、N3 报告级别行）；docs/43 正文数字保留历史快照并在头部指向 docs/45。 |

### 词表专项（G7，需人工裁定，不属代码缺陷）

| 项 | 核验 | 建议 |
|---|---|---|
| 寨主/宫主/管家 标 `#` 身份 | 属实；表 note 自认"与职衔归类冲突，待人工裁定"，tier=watch | 按 03a `;`=可任命建制职衔，统一改 `;` 或保留 `#` 但写入 01g 裁定；二选一后同步 C17 报告 |
| 剑谱/剑诀/拳经/秘笈（`{`，watch/weak） | 属实，已标通名并 watch | 维持 watch；若 apply 需加"内容对象指称"上下文规则（如"一本/这本/那部+词"） |
| 铜钹/拂尘/飞叉/佩玉（`•`） | 属实，均来自 kb 神兵表且标 evidence | 属"器物通名"边缘；建议降 watch 或加"具名限定"规则（如"XX的拂尘"不算具名） |
| 皇室/王室/朝廷/明朝/大清/满清（`◆`） | 属实，表标"政权"类 | 需 01g 裁定"政权/朝代是否归 ◆"；若归，补类型说明；若不归，移出并改标 ^/◆ 规则 |
| 柔功/神拳（`☆`） | 表中存在且 evidence 为"语料☆具名技艺 5 例" | 复核是否确为具名技艺；"神拳"已有"无敌"后缀负规则，可保留 |
| 天山剑法（`☆` 父式名） | **不采纳删除建议**：SKILL_03a v1.7 G-29 明确"父术+子式双层双标"；表中 note 标 `parent_art` | 保留；可在表 note 加"父式名，允许与子式同段双标"说明 |

---

## 三、误报/不采纳（附核验证据）

| 模型意见 | 核验 | 结论 |
|---|---|---|
| G5：`coverage_swap` 在 L728 截断、脚本不可运行（P0） | 评审时按行切成 1-728 / 729-1303 两半；文件共 1303 行且函数完整；`accept_batch.py` 实跑 accepted 13/13 | **误报（分组截断）** |
| G3：`render_md` 空 chapters 会 `IndexError`（P1） | 源码已用 `if result["chapters"] else "- 数据来源：无"` ternary 保护 | **误报** |
| G2：`build_masked` 对 `\r\n` 偏移算错（P1） | `text.split("\n")` 时 `\r` 留在行内，`offset=end+1` 恰好跨过 `\n`，偏移正确 | **误报** |
| G7：天山剑法属父式误收（P0） | SKILL_03a v1.7 G-29 允许父术+子式双标；表 note 已标 parent_art | **不采纳** |
| G7：轻功泛称误收（P0） | 三张词表中无"轻功"条目（grep 确认） | **误报** |
| G8：docs/44 与 docs/45 warnings 矛盾（P1） | docs/43 为 22:19 快照（warnings 2，含新增 pipe_mapping_conflict 检查）；docs/45 before 为 22:17 快照（warnings 0）；judgment 均 85 | **非矛盾**，已补注快照口径 |
| G4：密度分母与 `strip_markup` 不同步（P1） | 代码为 `WS_RE.sub("", symbols.strip_markup(line))`，剥标后正文去空白；未发现与分母口径冲突的实证 | **不成立**（保留 P2 观察） |

---

## 四、建议的修复顺序

1. **P1-1 C18 `--apply` 围栏/标题插入**（数据安全，仅 apply 路径；默认流程无影响）——要么修 apply，要么在文档/CLI 明令禁止，统一走 C7。
2. **P1-2 accept_batch 报告硬编码**（影响报告可信度与复用）——改数据驱动，10 行内可修。
3. **P1-3 C19 首字匹配**（潜在误映射）——去掉首字匹配或加姓氏/上下文条件。
4. **P1-4 identity 7 条空 evidence**（词表规范）——补证或降档。
5. **P2 批量**：`kinship_blocked` token 类型校验、`scan_structure` 清栈、`parse_chapters`/`load_*` 健壮性、`pipeline run_stage` 异常、`pos` 坐标口径、C20 selftest mock、`stats["tsv"]`、备份覆盖。
6. **词表裁定**：寨主/宫主/管家 `#` vs `;`、政权/朝代 `◆` 归属 → 建议作为 01g 附录 B 的下一批裁定项；其余通名条目维持 watch，apply 前先做 precision 标定（docs/39 S1 流程）。

---

## 五、本次复核附带的文档修正（3 处）

1. `docs/43` 头部补"快照口径"注（22:19 快照 / warnings 2；docs/45 before 为 22:17 / warnings 0，差异来自检查项增加）。
2. `docs/45` §〇 的 before 快照补 `generated_at 22:17:28` 与 warnings 0。
3. `docs/_p2/C24-N3-report.md` §2.2 的 `E-WL-DOMAIN` 行改为"warning（`--wordlist-strict` 时 error）"，与代码默认行为一致。

> 其余代码问题本轮**只报告不改**（等待指示）；如需要，可按 §四 顺序批量修复并重跑五门 lint + 验收。

---

## 六、复现

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
$env:QWEN_API_KEY='<你的 AMD Radeon key>'   # 不入库
$env:PYTHONIOENCODING='utf-8'
python scripts/qwen_review_files.py `
    --manifest logs/qa/qwen_max_review/manifest.json `
    --out-dir logs/qa/qwen_max_review --workers 3
```

- 评审器：`scripts/qwen_review_files.py`（只读；manifest 定义分组/行范围；`chat_template_kwargs` 关闭 thinking）。
- 原始意见：`logs/qa/qwen_max_review/G{1..9}_*.md`；usage/cost：同名 `.json` 与 `summary.json`。
- 模型：`Qwen3.8-Flash-Next` @ `https://developer.amd.com.cn/radeon/api/v1`；9 组共 $0.025498。

---

## 七、P1 修复记录（2026-11-05 00:15–00:40，用户指示"先修复 P1"）

### 7.1 改动

| # | 文件 | 修复 | 关键实现 |
|---|---|---|---|
| 1 | `scripts/scan_untagged_aliases.py` | **C18 `--apply` 保护区**：只按 TSV 原文偏移 `pos` 精确插入；缺 pos 的外部 TSV 退回"同词全插"但跳过 `build_masked` 保护区（令牌/围栏/标题/回目）；备份名含 TSV 名；`stats["tsv"]` 按文件计数；新增 `--selftest` 回归 | `_apply_word(..., pos)` + `_token_text()`；`do_apply()` 按 pos 降序处理；`selftest()` 断言围栏/标题零插入、正文零改动 |
| 2 | `scripts/accept_batch.py` | **报告去硬编码**：标题/范围/无来源数/裁决案例/修复命令全部改为数据驱动（`extra["pipe_unsourced_total"]`、`warn_pipe` 列表、`acc["chapter_label"]`、`chapters_label`）；`warn_pipe` 为空时不再输出写死案例 | `render_report()` 动态渲染；`render_review_package()` 标题按 analyses 回号生成 |
| 3 | `scripts/infer_single_char_names.py` | **C19 移除首字匹配**：`cands` 仅按末字（名末字）匹配，避免同回仅"李寻欢"时把单字"李"误映射；证据/原因文案同步改"末字匹配" | 一行过滤 + 三处文案/注释；全量复跑映射数不变（10，新推断 0） |
| 4 | `wordlists/identity_source.md` → `identity.json` | **7 条空 evidence 条目**（坛主/护卫长/军校/驿卒/学徒/舞女/挑夫）：34 章回版全库检索确认语料未检出 → conf 降 `weak`，note 补"语料未检出（先验/待验证）"；重编译 | `wordlist_compiler --name identity`：212 条 PASS；conf ok 182 / weak 30（原 188/24） |

### 7.2 回归验证（全部实测）

| 检查 | 结果 |
|---|---|
| `py_compile` 三个脚本 | exit 0 |
| C18 `--selftest` | **PASS**：pos 模式插入 1 处、全插模式 2 处；围栏/标题均未插入；strip 后正文一致 |
| C18 `do_apply` 集成测试（临时文件 + monkeypatch，不碰真 tagged） | 2 行按 pos 插入；围栏"武当在围栏内"、标题"# 武当标题"零改动；`strip_markup` 前后一致；令牌数 1→3 符合预期 |
| C18 全书扫描复跑 | 101 条建议 / 32 回（与修复前一致，无回归） |
| C19 全书复跑 | 映射 10 条（新推断 0）、歧义 1，与修复前一致（首字匹配在现语料无产出，属 latent 风险） |
| `wordlist_compiler.py --check` | 8/8 PASS（identity 212 条，auto_ready=0） |
| `accept_batch` 020-032 复跑 | **accepted 13/13、hard 0、judgment 27、pipe_unsourced 0**；报告重生成，`grep` 确认无 `无来源 0`/`032[31]`/`020-032 共`/`13 回均` 硬编码 |
| `pipeline_wuxia.py check` | 五门 lint 全 0，exit 0 |

### 7.3 未修（仍为 P2）

- `scan_untagged_aliases` 的 apply 在"外部 TSV 无 pos"模式下仍可能把词插进更长的未登记词内部（如 `武当派` 未登记时对 `武当` 全插）；C18 自身 TSV 带 pos，不受影响。
- 其余 P2 见 §二 表（kinship token 类型、scan_structure 清栈、parse_chapters 健壮性、pipeline 异常、pos 坐标口径、C20 selftest mock、备份命名等）。→ **已于 §八 全部修复**（2026-11-05 00:40–00:55）。
- 词表裁定项（寨主/宫主/管家 `#` vs `;`、政权/朝代 `◆` 归属）仍待 01g 附录 B 裁定。→ **已按 01g 正文裁定并落地，见 §八.2**。

*修复人：Lead；验证命令见 §七.2；原始评审意见未改动。*

---

## 八、P2 修复记录（2026-11-05 00:40–00:55，用户指示"继续修复 P2"）

### 8.1 改动（§二 第 5–15 项 + 词表专项）

| # | 文件 | 修复 | 关键实现 / 验证 |
|---|---|---|---|
| 5 | `tag_new_entity_types.py` / `tag_identity_kinship.py` `scan_chapter` | **TSV `pos` 统一为原文偏移**：迭代行维护 `line_start`（原文累计 `len(line)+1`），`pos = line_start + 行内偏移`；删除 `display_offset` 混基准逻辑；docstring 改"位置=原文偏移（含标记）" | 45 张 TSV / **959 行** 逐行断言 `原文[pos:pos+len(word)] == word` **0 失败** |
| 6 | `tag_identity_kinship.py` `kinship_blocked` | 左邻令牌必须 `parse_token` 为 `entity+@` 才视为指称对象，`#`/`☆` 不再放行 | 5 例单元自检通过；全网 C17 **917→906**（−11 全为原 `#` 令牌误放行：女儿3/父亲2/儿子2/爹爹1/丈夫2/兄弟1） |
| 7 | `tag_new_entity_types.py` `hit_blocked` | 前后缀负规则改在**跨令牌可见字符**上判断（`token_display/token_ending_at/token_starting_at/prev_visible/next_visible`）；`◆`+武功改为"下一令牌码=☆"；保留裸文分支 | 6 例自检：`〖%天〗大明`→拦、`满州〖#武师〗`→放行、`武当〖☆剑法〗`→拦 等 |
| 8 | `detect_entity_boundary_errors.py` `selftest` | **hermetic 自检**：内置 `MOCK_REGISTRY`（canon={卓仲廉,练霓裳}、alias2canon={玉罗刹→练霓裳}）+ `MOCK_WN`，`--selftest` 在真实加载前返回；主流程仍用真实 `load_wn/load_registry` | 把 registry/rhetoric/stopwords 路径全指向不存在文件后 `--selftest` 仍 **8/8 PASS**、exit 0 |
| 9 | `validate_verb_tagging_wuxia.py` `scan_structure` | mismatch 且栈中无同层开括号时：先记栈内全部 `unclosed` → `stack.clear()` → continue，避免残留开括号级联误报 | 脏样本 `⟦⊞甲〗⟧` 不再产生假 verb span / 级联；48 项自测 0 FAIL（含结构 18 项） |
| 10 | 多脚本 `parse_chapters` + JSON 载入 | **9 个脚本**加友好 `SystemExit`（`1-abc`/`a-b`/`20-`/倒置区间等）：analyze_annotation_gap、annotate_chapter_llm、fix_annotation_mechanical、qa_annotation_report、summarize_annotate_cost（Lead）；infer_single_char_names、accept_batch、build_entity_concordance、validate_verb_tagging_wuxia（P2）。**顶层 list 兼容**：`items = data if isinstance(data, list) else data.get("items", [])` 落到 masker、wordlist_compiler、C16/C17/C18/C19/C20（各 2 处）/N3/accept_batch | Lead 冒烟：5 个旧脚本对 `1-abc`/`a-b`/`20-` 三类均 `[ERROR] --chapters 格式非法…`、无 traceback（`12,,13` 空段按历史行为忽略，不视为非法）；顶层 list 词表/JSON 实测各载入点正常 |
| 11 | `pipeline_wuxia.py` `run_stage` | `subprocess.run` 包 `try/except (FileNotFoundError, OSError)` → 打印 `[stage] 子进程启动失败: …` 并返回 -1；`stage_check` 逐项记录不短路，汇总 exit 1 | 模拟子进程启动失败实测：check 跑完并汇总 |
| 12 | `accept_batch.py` | 映射表加载：裸 `except Exception: pass` → 捕获 `FileNotFoundError/JSONDecodeError/OSError`（+AttributeError），打印 `[accept][WARN] 映射表加载失败: …`、置 `extra["mapping_loaded"]=False`、报告 §3.9 注明"@ 管道三来源仅 registry+正文共现"；`render_report` 空 analyses 返回「# 无数据」+ main 空集 exit 2；`fix_probe` 摘要解析失败 → `(未解析；见 fix_dry_run.log)`；`qa_probe` 缺失字段 fallback | monkeypatch 映射缺失路径实测：WARN + `mapping_loaded:false` + 报告注明均生效；`--chapters 20-abc` 友好报错 exit 2、无 traceback |
| 14 | `build_entity_concordance.py` `load_registry` | `JSONDecodeError` → 警告 + 空 registry（`meta.error` 写入 JSON/MD），脚本继续输出空对照；另兼容登记表顶层为 list、顶层标量/`entities` 非 list → 警告+空表 | 坏 JSON 端到端实测：exit 0、JSON/MD 均含 `meta.error` |
| 补充 | `scan_untagged_aliases.py` `do_apply` | **无 pos 全插模式的长词保护**：传入 `known_words=set(word_map)`，若存在更长已知词以该词为前缀且 `text.startswith(longer, i)` 跳过该位置（`武当` 不切进未登记 `武当派`）；pos 模式不变；`--selftest` 增补断言 | selftest：pos 1 处 / 全插 2 处 / known 保护后全插 1 处且**无 `〖◆武当〗派`**；临时文件集成 strip 一致 |
| 补充 | C16/C17 词表载入 | 裸 list 词表兼容（Lead 追加项），两脚本各实测载 1 条 OK | `py_compile` PASS |
| 15 | 文档口径 | 已在 §五 完成 3 处注（docs/43 快照口径、docs/45 before 时间、N3 报告级别行） | — |

> 第 13 项（C18 `stats["tsv"]` 按文件计数、备份名含 TSV 名）已在 P1 一并修复，见 §七.1 #1，不再重复。

### 8.2 词表裁定（G7 专项，按 01g/03a 正文而非猜测）

| surface | 旧 | 新 | 依据 |
|---|---|---|---|
| 寨主 / 宫主 | `#`（身份） | `;`（可任命建制职位） | 01g 例："金刀寨主是职位短语 → 〖◆金刀寨寨〗〖;主〗"；03a `;`=可任命建制职位 |
| 管家 | `#` | `#`（保留） | 职业类别，非建制职位；note 写明"P2 裁定" |
| 皇室/王室/朝廷/明朝/大清/满清 | ◆ | ◆（保留） | 01g ◆ 定义含"国家、政权"；note 补"政权类" |

重编译：identity **212 条**（`;` 82 / `#` 130；review 191 / watch 21；conf ok 185 / weak 27）、new_entity_types **268 条**；`wordlist_compiler --check` **8/8 PASS**（auto_ready=0）。

### 8.3 回归验证（Lead 独立复跑，2026-11-05 00:48–00:56）

| 检查 | 结果 |
|---|---|
| `py_compile` scripts/*.py（46 件） | **0 失败** |
| `wordlist_compiler.py --check` | **8/8 PASS**（identity 212 / kinship 62 / new_entity_types 268 / quantity 36 / stopwords 18 / structure_markers 12 / time_words 19 / verbs 165） |
| `pipeline_wuxia.py 白发魔女传 check` | 五门 lint 全 0（64 文件），exit 0 |
| C16 全书 dry-run | **53 条** / 13 词种 / 13 回；TSV 13 张 |
| C17 全书 dry-run | **906 条** / 110 词种 / 32 回；TSV 32 张 |
| C18 `--selftest` + 全书 | selftest PASS；**101 条 / 23 回** / 23 TSV |
| C19 全书 | 映射 **10** 条、新推断 0、歧义 0、无匹配 1（011「李」末字规则不猜） |
| C20 `--selftest` + 全书 | selftest **8/8 PASS**；**16 条**（error 2 / warning 10 / info 4） |
| C24 全书 | **4,988 实体 / 32,716 次**；登记命中 69/70、alias_mapped 9、unregistered 301 |
| N3 全书 | error **0** / warning 317 / suggestion 162 / info 2,204（动词 5,836，基线 1.431 V/100字） |
| `accept_batch` 020-032 | **accepted 13/13、needs_fix 0、hard 0、judgment 27、warnings 2、pipe_unsourced 0**；抽样 117 段（10%±1）；qa A/B 剥标差异 0 段 |
| tagged 完整性 | 32 个 `*.tagged.md` SHA256 跑前/跑后一致；docs/43、docs/45 快照 mtime 未变（11-04 23:55） |

**C24 条数口径说明**：4,988/32,716 是 docs/45 验收处置后的当前值；docs/44 §四 记录的 4,992/32,731 为处置前基线，差 −4 组/−15 次 = task-9 删掉的 15 个实体 token（$ 13、% 1、= 1），非脚本回归（verify-builder 已用备份重建旧语料复核）。

### 8.4 仍遗留（不属本轮 P2 缺陷）

1. **P2 SKILL 11 份**（03b/03d/03e/03f/03l/02i/04/04d/05/05d/05e）仍未写——P2 代码面已收口，SKILL 面是下一批。
2. C16/C17/C18 建议 TSV（53/906/101 条）全为 review/watch，`auto_ready=0`，是否 `--apply` 待人工抽验后分波放开。
3. C24 unregistered 301 条 + alias_mapped 9 条待回填 registry。
4. 27 条保留 judgment 待终签；13 处 verse 存疑待处置。
5. C20 当前 16 条（原首跑 19 条）——差异来自 docs/45 已修 019/030 三处；旧形态内存回填可复得 19，检测器无回归。

*P2 执行：Lead（第 10/13/15 项与全局回归）+ tag-builder（5/6/7 + 词表裁定）+ scan-builder（8 + C18 长词保护）+ verify-builder（9/11/14）+ accept-runner（12）；本记录 2026-11-05 00:56。*

*生成：2026-11-04 23:5x；执行：Lead；原始评审未经修改，本报告为核验后汇总。*
