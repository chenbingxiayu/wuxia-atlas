# -*- coding: utf-8 -*-
"""一次性：生成 SKILL_06d/08c/08f 武侠版。2026-11-06。"""
import io
import re
from pathlib import Path

S = Path(r"C:/Users/YANG Ruosong/Documents/workspace/shiji-kb/skills")
TODAY = "2026-11-06"


def split_fm(text):
    if text.startswith('---'):
        m = re.match(r'^---\n.*?\n---\n', text, re.S)
        return text[m.end():].lstrip('\n')
    return text


def transplant(src, head, repls, fname, tail):
    body = split_fm((S / src).read_text(encoding='utf-8'))
    missing = []
    for old, new in repls:
        if old in body:
            body = body.replace(old, new)
        else:
            missing.append(old[:40])
    out = head + body.rstrip('\n') + '\n' + tail
    (Path('skills') / fname).write_text(out, encoding='utf-8', newline='\n')
    print('written', fname, len(out.splitlines()), 'lines; missing repl:', missing)


HEAD_06D = """---
name: skill-06d-wuxia
title: 推理机构建（武侠版·规划）——本体推理、规则执行与冲突检测
description: 武侠本体层的推理机构建规划（06 组框架件，未实装）：本体推理（师承传递/同门对称/师徒互逆）、规则推理（前向链补全知识/后向链解释评级）、约束检查（结构/语义/领域三层）与冲突检测（师承环/时点矛盾/跨书身份冲突）。现役承载是 N8 lint_consistency（约束检查）与 N5 relation_validator（关系核验），本文规划推理引擎形态。当需要设计自动化推理或解释生成时使用。
version: v0.1-draft
last_updated: 2026-11-06
---

# SKILL 06d：推理机构建（武侠版·规划）

> **上游声明**：本文从 shiji-kb `skills/SKILL_06d_推理机构建.md` 移植改写（🟢 轻度 85:15——框架照搬，示例与依赖换成武侠口径；依据 `docs/03-skill与脚本改造清单.md` L144）。
> **定位警示**：**本文是规划稿。** 现役承载：约束检查＝N8 `lint_consistency`；关系核验＝N5 `relation_validator`；时间单调性＝N4 `time_resolver`；分类校验＝N9 `lint_taxonomy`。本文规划的是其上的自动推理层（引擎选型见 §三）。

## 快速开始（武侠版三步）

```text
Step 1 看现役   N8 五项检查 + N5 语义角色核验已覆盖哪些推理（勿重复建设）
Step 2 定需求   要自动推导什么（师祖链/同门网）？要解释什么（07e 评级依据）？
Step 3 立项    引擎选型对比（§三）先出 docs/NN 设计稿；推理结果必须可溯源
```

---

"""

REPL_06D = [
 ('- 属性传递性：如果"祖先"关系是传递的，自动推导祖先链', '- 属性传递性：如果"师承"关系是传递的，自动推导师承链（师祖/徒孙）'),
 ('- 属性对称性：如果"兄弟"关系是对称的，自动补全反向关系', '- 属性对称性：如果"同门"关系是对称的，自动补全反向关系'),
 ('- 逆属性：自动推导逆关系（如"父亲"的逆是"子女"）', '- 逆属性：自动推导逆关系（如"师父"的逆是"弟子"）'),
 ('- 例：从父子关系推导祖孙关系', '- 例：从师承关系推导师祖—徒孙关系'),
 ('- 例：为什么X是Y的祖父？追溯推理链', '- 例：为什么X被评 07e"可信"？追溯评级依据链（书证+规则）'),
 ('- 属性冲突：属性值矛盾（如生年>卒年）', '- 属性冲突：属性值矛盾（如初登场回晚于成名回）'),
 ('- 关系冲突：关系链矛盾（如A是B的祖父，B也是A的祖父）', '- 关系冲突：关系链矛盾（如A是B的师父，B也是A的师父——师承环）'),
 ('|[SKILL_06c](SKILL_06c_规则构建.md)', '| `SKILL_06c_规则构建_武侠版.md`'),
 ('[SKILL_06c](SKILL_06c_规则构建.md)', '`SKILL_06c_规则构建_武侠版.md`'),
 ('**当前状态**：规划阶段', '**当前状态**：规划阶段（武侠版同状态；约束/核验现役件为 N8/N5/N4/N9）'),
]

TAIL_06D = """
---

## 工具与脚本

现役联动件：`scripts/lint_consistency.py`（N8）、`scripts/relation_validator.py`（N5）、`scripts/time_resolver_wuxia.py`（N4）、`scripts/lint_taxonomy.py`（N9）；上游设计 `docs/05`（G6 认识论转写）、`docs/11`（真实性评级）。

## 检查清单

- [ ] 明确"规划稿"身份；推理结果必须可溯源（规则 ID + 书证链）
- [ ] 与 N8 规则表分工明确：确定性检查归 N8，推导式推理归本文规划范畴
- [ ] 引擎选型先出对比设计稿（docs/NN）再立项，不引入第二套数据栈
- [ ] lint_skills PASS（score ≥ 90）

## 成功标准

- 推理结论（师祖链/同门网/评级依据）全部可回溯到 tagged 书证与规则 ID
- 不与 N4/N5/N8 的确定性检查重复建设
- lint_skills PASS（score ≥ 90），无 error
"""

HEAD_08C = """---
name: skill-08c-wuxia
title: 成本管控与 Token 节约（武侠版）——从费率表到批次账本
description: 武侠知识库的成本管控规范：成本来源（LLM 标注为主）、token 节约策略（提示词优化/context 压缩/模型分级/批处理/缓存）、成本监控（实时+汇总+预算）与性价比评估。武侠库现役工具：token_tracker.py 记账、summarize_annotate_cost.py 汇总、.token_cost_config.json 费率表；实测背景为 5 书 151 回机器标注。当需要控成本、估预算或分析性价比时使用。
version: v0.1-draft
last_updated: 2026-11-06
---

# SKILL 08c：成本管控与 Token 节约（武侠版）

> **上游声明**：本文从 shiji-kb `skills/SKILL_08c_成本管控和Token节约.md` 移植（🟢 轻度 90:10——机制照搬、不含史记内容；依据 `docs/03-skill与脚本改造清单.md` L161"08c/08f ✅ 全部照搬"）。
> **武侠适配注**：成本侧现役件——`scripts/token_tracker.py`（记账）、`scripts/summarize_annotate_cost.py`（按书/按批汇总，docs/47-49 各批次 token 表）、`$KB/.token_cost_config.json`（费率）与 `$KB/.api_config.json`（密钥，**均已 gitignore**）。主消耗：`scripts/annotate_chapter_llm.py`（SKILL_03a v1.9 SYSTEM_PROMPT，temperature=0，few-shot 种子注入）；缓存策略见其 mapping/种子注入的幂等设计。

## 快速开始（武侠版三步）

```text
Step 1 记账   标注批次开启 token_tracker；费率取 .token_cost_config.json
Step 2 汇总   批次收口跑 summarize_annotate_cost → docs/NN 记总账
Step 3 优化   按 §三 策略逐项检查：提示词块长（few-shot ≤800 块约束）、模型分级、批处理
```

---

"""

TAIL_08C = """
---

## 武侠库成本速查（2026-11 实测口径）

| 项 | 口径 |
|---|---|
| 记账 | `token_tracker.py`；费率 `.token_cost_config.json` |
| 汇总 | `summarize_annotate_cost.py`；批次 docs/NN 留总账 |
| 主消耗 | `annotate_chapter_llm.py`（LLM 标注，按章计费，temperature=0） |
| 已控成本 | few-shot 块长 ≤800（03a §5.2 断言）；种子幂等注入不重复计费 |
| 敏感件 | `.api_config.json` / `.token_cost_config.json` 不进提交清单（docs/65） |

## 检查清单

- [ ] 每个调 LLM 的批次有 token 账；汇总进 docs/NN
- [ ] few-shot/提示词膨胀有断言拦（03a §5.2 块长检查）
- [ ] 预算估算先于换书决策（按历史单回均摊）
- [ ] 敏感配置不在提交清单
- [ ] lint_skills PASS（score ≥ 90）

## 成功标准

- 任一批次可答：token 多少、费用多少、单回均摊多少
- 成本优化不降质量（质量门 03a 两级完成门 + accept 不松动）
- lint_skills PASS（score ≥ 90），无 error
"""

HEAD_08F = """---
name: skill-08f-wuxia
title: 置信度函数设计（武侠版·规划）——从反思样本归纳证据权重
description: 置信度函数的设计方法论（08 组规划件）：反思归纳式——从标注/反思样本中归纳证据强度权重，四种通用模式（多源票数/分层兜底/三级不确定度/反思驱动进化）与信号源强度排序。武侠库现役承载：registry 两态（approved/proposed）、SKILL_07e 真实性评级、N5 关系核验置信；本文是函数化设计的规划起点。当需要给登记层/评级层设计显式置信度函数时使用。
version: v0.1-draft
last_updated: 2026-11-06
---

# SKILL 08f：置信度函数设计（武侠版·规划）

> **上游声明**：本文从 shiji-kb `skills/SKILL_08f_置信度函数设计.md` 移植（🟢 轻度 90:10——方法论照搬；依据 `docs/03-skill与脚本改造清单.md` L161；"置信度从反思样本归纳"的核心立场保留，见 docs/_audit/skills-coverage.md #16）。
> **武侠适配注（现役对照）**：① 登记层置信＝`registry/entities.json` 两态（approved 68 / proposed 357，提案走 propose/apply_entity_registration CAS 流程）；② 结论置信＝`SKILL_07e_真实性评级_武侠版.md`（证据状态+评级方法，现行）；③ 关系置信＝N5 `relation_validator`（27 行联动候选×语义角色核验）。**本文的"置信度函数"是把上述三处隐式置信显式化为可计算函数的规划**——核心立场：权重从反思样本归纳（references/ 规律库供料），不拍脑袋定数。

## 快速开始（武侠版三步）

```text
Step 1 选模式   按 §三 四模式对号：多源票数（跨书共现）/分层兜底（证据状态）/三级标记（07e）/反思进化（03c1）
Step 2 定信号源 按 §四 强度排序取武侠信号源：原文明写>书内互证>跨书互证>常识推断
Step 3 归纳权重 从 references/ 反思样本统计权重；样本不足时标"待标定"而非拍数
```

---

"""

TAIL_08F = """
---

## 武侠库信号源速查（§四 的武侠对照）

| 强度 | 信号源 | 武侠库对应 |
|---|---|---|
| 强 | 原文明写 | tagged 书证（W7 引文核验可定位） |
| 中 | 书内互证 | 同书多回共现 + N5 联动候选 |
| 中 | 跨书互证 | 互文引用表 + D07 双层 canonical |
| 弱 | 登记层人工核定 | registry approved（含 patches 裁定链） |
| 最弱 | 常识推断 | 07e"推断"档；N8 常识规则命中 |

## 检查清单

- [ ] 函数权重有归纳来源（反思样本/规律库统计），无拍脑袋常数
- [ ] 样本不足的权重显式标"待标定"，随 03c 反思循环更新
- [ ] 与 registry 两态、07e 评级口径不冲突（函数是显式化，不是第三套体系）
- [ ] lint_skills PASS（score ≥ 90）

## 成功标准

- 任何置信度数值可追溯到"哪些样本、什么分布"（归纳可复算）
- 信号源强度排序与 01g 证据状态、07e 评级口径一致
- lint_skills PASS（score ≥ 90），无 error
"""

transplant("SKILL_06d_推理机构建.md", HEAD_06D, REPL_06D, "SKILL_06d_推理机构建_武侠版.md", TAIL_06D)
transplant("SKILL_08c_成本管控和Token节约.md", HEAD_08C, [], "SKILL_08c_成本管控与Token节约_武侠版.md", TAIL_08C)
transplant("SKILL_08f_置信度函数设计.md", HEAD_08F, [], "SKILL_08f_置信度函数设计_武侠版.md", TAIL_08F)
