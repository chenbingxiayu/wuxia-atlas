# prompts/ · 设计工单提示词目录

每个文件 = 一份可直接投喂大模型的**自包含提示词**（任务工单 + 网站目标 + 史记参考件全文 + 输出格式合同）。

| 文件 | 对应任务（见 docs/06 任务清单） | 状态 |
|---|---|---|
| `T01-实体类型体系与符号分配-提示词.md` | #1 实体类型体系与符号分配（SKILL_01g 武侠版） | ✅ 已完成（产出见 `skills/SKILL_01g_标注符号集合原则.md`） |
| `T02-武侠动词域与动词实体联动规范-提示词.md` | #2 武侠动词域与动词-实体联动规范（SKILL_04f 武侠版） | ✅ 已完成（v1/v2 双稿 + 对比合并，产出见 `skills/SKILL_04f_动词标注.md` 与 `docs/07-SKILL_04f双稿对比分析与合并说明.md`；注：v2 生成时把参考件二缩写为方法论摘要以适配 32k 上下文，差异在该文档 §0 声明） |
| `T03-武侠事件类型学-提示词.md` | #3 武侠事件类型学（SKILL_04a 武侠版） | ✅ 已完成（v1=GLM 子 agent、v2=deepseek-v4-flash 三段接力、对比合并见 `docs/07-SKILL_04a-双稿对比分析与合并记录.md`，主文件 `skills/SKILL_04a_事件识别.md`；注：双稿生成期间 05e 参考件曾被节录 81.8%，2026-11-03 已恢复全文并逐字符校验，影响声明见 docs/07 §0） |
| `T04-武侠章回结构与韵文检测-提示词.md` | #4 章回结构标注约定 + 韵文/套语检测设计（SKILL_02a/02b 武侠版） | ✅ 已完成（v1=GLM 子 agent 全量提示词稿、v2=deepseek-v4-flash 上下文适配稿（02a/02b/02a1/02b2 缩写、02b1 全文），对比合并见 `docs/08-SKILL_02a02b双稿对比分析与合并说明.md`，主文件 `skills/SKILL_02a_02b_章回结构与韵文处理.md`） |
| `T05-书内相对时间轴模型-提示词.md` | #5 书内相对时间轴模型（时间体系） | ✅ 已完成（v1=GLM 子 agent 全量稿 703 行、v2=deepseek compact 适配稿（五件参考件缩写，04c 43 条清单保留），对比合并见 `docs/09-…时间体系…md`，主文件 `skills/SKILL_时间体系_武侠版.md`） |
| `T06-武侠关系类型学-提示词.md` | #6 武侠关系类型学总设计（关系体系） | ✅ 已完成（v1=GLM 子 agent 稿 729 行 55 谓词、v2=deepseek compact 适配稿（05a/05c 缩写、05b 全文、META-12 节选），对比合并见 `docs/10-…关系体系…md`，主文件 `skills/SKILL_关系体系_武侠版.md`） |
| `T07-跨书同一性与权威层级-提示词.md` | #7 跨书同一性与权威层级模型（跨书治理） | ✅ 已完成（v1=GLM 子 agent 稿 751 行、v2=deepseek compact 适配稿（META-12/03b 缩写、02h 全文），对比合并见 `docs/11-…跨书治理…md`，主文件 `skills/SKILL_跨书治理_武侠版.md`） |
| `T08-武侠实体分类树五件套-提示词.md` | #8 武侠实体分类树五件套（分类树） | ✅ 已完成（v1=GLM 子 agent 稿 849 行 64 叶、v2=deepseek compact 适配稿（03h-03k/06a 缩写、06e 全文），对比合并见 `docs/12-…分类树…md`，主文件 `skills/SKILL_分类树五件套_武侠版.md`） |
| `T09-武侠词表体系总体规划-提示词.md` | #9 武侠词表体系总体规划（词表规划） | ✅ 已完成（v1=GLM 子 agent 稿 760 行、v2=deepseek 直投稿 778 行（11k 无需适配），对比合并见 `docs/13-…词表规划…md`，主文件 `skills/SKILL_词表体系规划_武侠版.md`） |
| `T10-虚构地名gazetteer规范-提示词.md` | #10 虚构地名 gazetteer 规范（gazetteer） | ✅ 已完成（v1=GLM 子 agent 稿 784 行、v2=deepseek 直投稿 399 行（偏短已在 docs/14 §0 声明），对比合并见 `docs/14-…gazetteer…md`，主文件 `skills/SKILL_地名gazetteer_武侠版.md`） |
| `T11-武侠常识与设定一致性-提示词.md` | #11 武侠常识基准库与设定一致性检查规则（常识一致性） | ✅ 已完成（v1=GLM 子 agent 稿 777 行、v2=deepseek compact 适配稿（07c/07e/META-10 缩写），对比合并见 `docs/15-…常识一致性…md`，主文件 `skills/SKILL_常识与设定一致性_武侠版.md`） |
| `T12-SKU卡片类型规划-提示词.md` | #12 SKU 卡片类型规划（SKU 卡片，收官件） | ✅ 已完成（v1=GLM 子 agent 稿 865 行、v2=deepseek compact 适配稿（08a 全文/08e 缩写留 §8.1），对比合并见 `docs/16-…SKU卡片…md`，主文件 `skills/SKILL_SKU卡片_武侠版.md`） |
| `A1-实体层标注提示词-v0.md` | xval 实验·实体层标注 Pass1（非 docs/06 工单） | ⚠️ v0 实验稿存档：六模型交叉验证（docs/19）用；其中"亲属词标 ;""镖头标 ;""X家标 ="等规则已被 docs/21 v2 口径推翻，**正式标注规则与 few-shot 以 `skills/SKILL_03a_实体标注.md` §二 SYSTEM_PROMPT 为唯一权威**（版本随种子再生成滚动，以文内"版本锁定"节为准），本文件仅作两遍分层协议参考 |
| `A2-动词层标注提示词-v0.md` | xval 实验·动词层标注 Pass2（非 docs/06 工单） | ⚠️ 同上；E+V 统一单遍模式经 003 全章验证为主用模式，两遍仅困难章 fallback |

使用方式：打开文件，复制"提示词正文"围栏内的全部内容，投喂给设计模型；产出按文内指定路径保存。

## 外部模型调用工具（`scripts/_oneshot/` 一次性脚本）

- `scripts/_oneshot/_tmp_gen_v2.py`：**预算自适应**调用器（`--prompt <compact工单> --dst <输出>`；0.67 token/字符估算 max_tokens + 截断续写），T05-T12 的 v2 均用此法。
- `scripts/_oneshot/_tmp_gen_skill.py`：参数化单稿调用（`--prompt <工单> --dst <输出> [--model deepseek-v4-flash]`）；注意端点上下文 32,768 token（输入+输出共享），`max_tokens` 不可超过"32768 − 提示词 token 数"。
- `scripts/_oneshot/_tmp_gen_04a_v2.py`：**三段接力**调用样板（同一完整提示词 + 分章输出范围 + 机械重组），适配"提示词大、产出长"的工单；T03 v2 即用此法。
- `scripts/_oneshot/_tmp_gen_skill_v2.py`、`_tmp_gen_02ab_v2.py`：T02/T04 历史一次性脚本（内嵌各任务参考件缩写配置）。
- `prompts/compact/_compact_T05..T12.md`：各任务上下文适配版提示词存档（由子 agent 按缩写合同生成，适配细节见 docs/09-16 各 §0）。
- API 约定（端点/鉴权/流式）承自 `_qwen_标注对比/qwen_reannotate_ch1.py`；**凭据已外部化**
  （P1 修复 2026-11-03：经 `scripts/api_config.py` 加载，env `WUXIA_API_*` 或 `wuxia-kb/.api_config.json`，
  源码不含密钥）。

双稿评审流程（T01-T12 通用）：同一提示词投喂两个模型——GLM（当前 Session 或其子 agent）出 v1、deepseek-v4-flash 出 v2（>24k 字符的工单用"参考件忠实缩写"适配版，差异在对比文档 §0 声明）——对比分析后合并定稿存 skills/ 主文件名，两稿以 `_v1`/`_v2` 后缀存档，对比文档存 `docs/07-16`。**12 项任务已全部走完该流程。**
