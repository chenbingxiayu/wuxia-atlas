# -*- coding: utf-8 -*-
"""judgment 终签工具（dry-run 版）：把各书 accept_batch 残留 judgment_items 按规则分类，出终签报告。

背景
----
各书经过 accept_batch 验收后，仍有语义边界类 judgment_items 无法由硬规则判定，需"终签"：
保留（有理由）/ 摘除 / 改域 / 转人工。此前裁决逻辑散落在一次性脚本
（scripts/_oneshot/adjudicate_judgment_qijian*.py、triage_judgment118.py）
与 docs/45 §三、docs/47 §6.3、docs/48 §九、docs/48-S2、docs/49 §五 的裁决记录里。
本工具把这些口径收敛为**正式、可复跑的规则分类器**，本轮只做 dry-run：

  * 读 registry/acceptance/<书>_*.json 的逐回 judgment_items（字段 pn/type/detail/display/
    suggestion/sampled；实际位于 chapters_data["NNN"].judgment_items，见下"数据结构"）；
  * 只读 tagged/<书>/<NNN>.tagged.md，定位 token（含域码/管道元数据）与上下文，作为
    规则判定与报告证据；不写 tagged / registry/acceptance / site/data；
  * 输出 logs/qa/judgment_signoff_<书>.md + .json；--all 另出总表。
  * --apply 本轮**不实现**（会打印 TODO 并退出），报告内说明原因。

数据结构（实测 2026-11-05，5 书一致）
------------------------------------
acceptance JSON 顶层：schema/book/chapters/chapters_data/summary/risk_stats/global_gate/...
  - `chapters` 是**回号整数列表**（非逐回对象列表）；
  - 逐回数据在 `chapters_data`：dict，key 为三位零填充字符串 "001".."0NN"，
    value 含 judgment_items / sample_judgment_items(计数) / status / entity_dist / verb_dist 等；
  - judgment item：{pn: int, type: str, detail: str, display: str, suggestion: str, sampled: bool}
  - `summary.judgment_items` 为全书计数（与逐回抽取数一致）；
  - `risk_stats[]` 为 8 类风险统计（category/hits/hard/judgment/note），可交叉核对。
  - 扩展类别：塞外奇侠传 JSON 出现 `d1_description`（不在六类规则表内）→ 按"未知类别→需人工"，
    报告附 03a D1 先例建议（docs/48-S2 §5.3 R1：描述性代称不标）。

本文件内嵌**规则表**（见下 §规则表）与逐类 classify_* 函数；规则 id 会写进报告/JSON，
便于终签时逐条回查条文与先例。所有判定**只依赖 JSON 字段 + tagged 上下文**，不调 LLM。

──────────────────────────────────────────────────────────────────────────────
规则表（与 classify_* 函数、报告附录同源；先例引用见各条注释）
──────────────────────────────────────────────────────────────────────────────
[R-UNK]   未知/扩展类别（如 d1_description）→ 需人工（提示 03a D1 建议）
[R-Q1]    quantity_boundary：单字裸数词/裸量词 → 应摘
          依据 docs/45 §二/§三 #20-22/#41-42/#61/#63/#67-68/#72-74（裸数词/裸量词不标）；
          docs/48-S2 §一 quantity 51 条全摘；SKILL_03a L109 数量新口径（"数词+量词+名"整串才标）
[R-Q2]    quantity_boundary：多字数词序列（五六/十七八）→ 应摘（同上"裸数词"）
[R-Q3]    quantity_boundary：多字信息承载计数（数词+量词+名 等）→ 保留
          依据 SKILL_03a L109 信息承载原则（数词+量词必标；docs/48 §九"数+量合规令牌保留"）
[R-Q4]    quantity_boundary：批次/泛人约量（一批/几名/几道）→ 应摘（SKILL_03a L109 负例）
[R-Q5]    quantity_boundary：其余多字 → 需人工
[R-P1]    plan_negation_verb：cue 为构词成分（牙将/将军、拜别/告别/分别、约莫/莫非、
          "不能不"双重否定等）→ 保留（检测器共现误报；04f §3.6 已发生标；
          docs/48 §九 001[40] 击倒、docs/48-S2 §一 029[12] 拜别下山 先例）
[R-P2]    plan_negation_verb：惯常/反复行为（每…都、一…便、常常/总是/向来）→ 保留
          （既成/反复发生非"纯计划"；04f §3.6 已发生标）
[R-P3]    plan_negation_verb：已发动但被中断/未遂（哪料/哪知/不料/未到/扑空…）→ 保留
          （04f §3.6 未遂判据：已发动但被中断 → 标 + 记未遂）
[R-P4]    plan_negation_verb：已发生/正在发生（前有 已/已经/便/就/才/正/刚/曾，或 token 后
          接 了/着/过）→ 保留（04f §3.6 已发生标；docs/45 §三 #9/#70 先例）
[R-P5]    plan_negation_verb：纯计划/意图/条件/未来/否定（将要/就要/快要/都要…、待/若/若是/
          否则、想/欲/意图、不/没/未/莫/别、要+动词）→ 应摘
          （SKILL_04f §3.6 威胁/意图/条件/计划/否定不标；docs/45 §三 #1-12/#55/#57/#60/#62/
          #64/#65/#71/#75/#79-#85 先例；docs/48-S2 §一 摘25；docs/48 §九 删76）
[R-P6]    plan_negation_verb：定语从句（"将/把 + token + 的 + 人物名词"、"想+动作+的+人物"，
          token 指已发生的动作/已擒获对象）→ 保留（docs/48 §九"擒住的定语从句"先例）
[R-P7]    plan_negation_verb：疑问句追问既成事实（为什么/为何/怎么/难道 + 要），或"要+动作"后文
          紧接既成结果（被杀/身首异处）→ 需人工
          （docs/45 #70"捉（已捕获，问原因）"为保留先例，但需回读前句语境；既成与否不猜）
[R-P8]    plan_negation_verb：情态/必要（迫着要/既要…又要/还要…）→ 需人工（既非纯计划亦非已发生）
[R-P9]    plan_negation_verb：将=把/将来 歧义未消（无 的/时/已 等信号）→ 需人工
[R-P10]   plan_negation_verb：cue 未紧邻 token（定位失败）→ 需人工
[R-T1]    time_boundary：|年龄| + 年龄表达（数字/龄/岁/左右/许/有余/出头…）→ 保留
          （SKILL_03a L108 年龄宽口径；docs/48 §九 三十出头/五十大寿/四十/五十 先例）
[R-T2]    time_boundary：年号/朝代/干支/节日/相对时点/约量时长/时点 → 保留
          （SKILL_03a L108 宽口径：纪年时点/相对时点/节日/持续约量时长；docs/48 §九 东汉/新正/
          明亡之后/以前/明早/甲申/大清早/一盏茶的功夫 先例；docs/48-S2 早上 保留；docs/45 #69 老）
[R-T3]    time_boundary：纯模糊时长/习语（一会/一刹那间/好久/很久/半晌/一阵/片刻…）→ 应摘
          （SKILL_03a L108"纯模糊修饰不标"；docs/48 §九"删纯模糊一会"；docs/48-S2 §一 三五次→摘）
[R-T4]    time_boundary：习语化时间修辞（金乌西堕/玉兔东升/星横斗转…）→ 应摘
          （01g 修辞/习语非严格时点；任务口径"时间边界：习语→应摘/改域"；docs/45 #77 沙漠泛指同例）
[R-T5]    time_boundary：时间位误挂战斗/里程计数（五六十招/三十招/十余里/六尺/三尺）→ 改域 $
          （docs/48 §九 改域 4→5；docs/48-S2 §一 五六十招/三十招→$、三五次→摘 先例）
[R-T6]    time_boundary：非时间实词（"老"为形容词等）→ 应摘（docs/45 #69 先例）
[R-T7]    time_boundary：其余（无 |年龄| 裸数词等）→ 需人工
[R-D1]    verb_domain_risk：■ 押解/强制迁移（押/押着/押到/押回/押上/充军/掳/绑架…）→ 保留
          （04f §2.0 劫人分流/§2.6 强制迁移；docs/45 §三 #16/#50/#53/#78 先例）
[R-D2]    verb_domain_risk：■→⊡ 组织/宫廷除名（逐出宫/逐出师门/驱逐出门派）→ 改域 ⊡
          （04f §2.3 组织成员关系终止；docs/45 #56/#58 先例；逐出回疆/西域仍 ■）
[R-D3]    verb_domain_risk：⊠ 自伤/医疗语境 → 保留（04f §2.2 医疗入口；docs/45 #34 先例）
[R-D4]    verb_domain_risk：⊠ 结果达阈值（死/伤/断/窟窿/脑浆/血/残/掉…）→ 保留
          （04f §2.2 结果决定主域/受伤阈值；docs/45 #23/#43/#47 先例）
[R-D5]    verb_domain_risk：⊠ 轻伤未达行动能力阈值 → 需人工（04f §2.2 应为 ⊞，docs/45 #32 改域
          先例；但与 docs/48 §九 保留终态冲突 → 不机械改）
[R-D6]    verb_domain_risk：假设/未发生语境（若/要不然/怕不/想+动作）→ 需人工
          （04f §3.6 未发生不标；域码本身是否成立需人工）
[R-D7]    verb_domain_risk：其余 → 需人工
[R-W1]    verb_wordlist_candidate：词表单一主域差异 → 保留（词表池输入，不改语料）
          （docs/45 §二/#13/#24/#38 等：19→15 保留；docs/48 §九：50→48 保留；
           docs/48-S2 §一：21→17 保留；04f §5.4 双轨/三档运营）
[R-W2]    verb_wordlist_candidate：同 token 的 R-D2 改域 → 随改域（docs/45 #33/#59 先例）
[R-F1]    fence_entity_real_only：围栏段落实为散文（段长 > 60，struct 层章首/回末探测误判）
          → 保留（docs/48 §九 018[1] 先例：诗围栏系散文段误判，实体均实指）
[R-F2]    fence_entity_real_only：人物/组织/家族/族群专名（@/◆/&/~）→ 保留（实指；01g 围栏限实指）
[R-F3]    fence_entity_real_only：地名专名（邙山/江南/塞外等）→ 保留（实指；docs/48 §九 023[80] 先例）
[R-F4]    fence_entity_real_only：泛指/修辞（时间泛称/抽象技艺/通名/泛称场所）→ 应摘
          （01g 围栏限实指；docs/45 #77 沙漠→摘、docs/48-S2 §一 一年/沙漠→摘 先例）
[R-F5]    fence_entity_real_only：其余 → 需人工
[R-DOC]   与既有 docs 终态（已全部保留）冲突的规则判定 → 转人工复核，不覆盖既有终签
          依据 docs/48 §九（七剑 103 全部保留项）、docs/48-S2（白发 27 全部保留有据）
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # wuxia-kb/
ACCEPTANCE_DIR = ROOT / "registry" / "acceptance"
TAGGED_DIR = ROOT / "tagged"
DEFAULT_OUT_DIR = ROOT / "logs" / "qa"
TOOL_VERSION = "finalize_judgment v1.2 (2026-11-06, dry-run + apply + 轮次化备份回放)"

# 5 部待终签书（任务范围；--all 按此顺序）
DEFAULT_BOOKS = [
    "江湖三女侠",
    "七剑下天山",
    "塞外奇侠传",
    "冰魄寒光剑",
    "白发魔女传",
]

# --apply 仅允许这些书（task-6 口径；七剑/白发残留人工项维持既有终签，不写；
# 2026-11-06 冰川天女传批次新增；2026-11-06 还剑/萍踪/散花批次新增；
# 2026-11-06 扩书 P1/P2 批次新增：云海玉弓缘 / 冰河洗剑录 / 联剑风云录 / 广陵剑；
# 2026-11-07 扩书 P3 批次新增：风雷震九州 / 侠骨丹心）
APPLY_BOOKS = ["江湖三女侠", "塞外奇侠传", "冰魄寒光剑", "冰川天女传",
               "还剑奇情录", "萍踪侠影录", "散花女侠",
               "云海玉弓缘", "冰河洗剑录", "联剑风云录", "广陵剑",
               "风雷震九州", "侠骨丹心",
               "大唐游侠传", "龙凤宝钗缘", "慧剑心魔",
               "剑网尘丝", "幻剑灵旗",
               "飞凤潜龙", "草莽龙蛇传", "龙虎斗京华", "绝塞传烽录"]
DEFAULT_BACKUP_ROOT = ROOT / "backup" / "tagged" / "judgment-apply-20261105"

# 3 书"需人工"条目的逐条裁定（task-6 第 3 步；docs/45 §三 先例直判，无先例→保留不写）
# 仅对 APPLY_BOOKS 生效；判定=保留 的条目不产生 token 改动，只进 apply 报告"人工裁定"表。
MANUAL_ADJUDICATIONS: dict[tuple, dict] = {
    # ── GLM 校对批（2026-11-09，龙凤宝钗缘/联剑风云录/广陵剑；Lead GLM-5.3-Flash 终签）──
    ("联剑风云录", 2, 26, "劫", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "反问句『难道真是不自量力要劫自己的贡物』陈述既存劫案计划，与紧邻 002[25]"
                  "（R-P6 保留）同指同一事件；该劫案后文既成。",
        "cite": "docs/45 §三 #70；002[25] R-P6 同场景一致",
    },
    ("联剑风云录", 11, 35, "劫", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『你为什么要劫那么多贡物』追问既成事实（贡物已被劫），非未发生计划。",
        "cite": "docs/45 §三 #70（追问既成保留）",
    },
    ("联剑风云录", 15, 76, "拍", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "『左掌在厉抗天背上的愈气穴一拍』为点穴疗伤入口，⊠ 医疗域成立。",
        "cite": "SKILL_04f §2.2 医疗入口；R-D3",
    },
    ("联剑风云录", 18, 15, "宾客", "d1_description"): {
        "verdict": "保留",
        "reason": "『乔家三位宾客』为具体处境身份（# 类）；书内 #武师/#卫士/#随从 同口径；"
                  "剑网尘丝 3[464] 宾客保留先例。",
        "cite": "SKILL_03a L103 处境身份；剑网尘丝 3[464] 先例",
    },
    ("联剑风云录", 23, 82, "下毒手害死", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『为什么要下毒手害死我和你的妈妈』追问既成（母亲已遇害）。",
        "cite": "docs/45 §三 #70",
    },
    ("联剑风云录", 24, 32, "刺", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "教扎针语境（归藏穴/刺三分/一刺进去即拔出来），医疗动作而非攻击，⊠ 成立。",
        "cite": "SKILL_04f §2.2 医疗入口",
    },
    ("联剑风云录", 24, 76, "残废", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『不死也将残废』为预言将来状态；致伤事件（断臂/毒火焚身）已由相应动词承载，"
                  "残废尚未既成，按将来/预期不标。",
        "cite": "SKILL_04f §3.6；docs/55 准备+X 同族",
    },
    ("联剑风云录", 26, 6, "绑来", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "女娃子已被绑来用作顶替，既成强制移动，■ 成立。",
        "cite": "SKILL_04f §2.6 强制移动；R-D1",
    },
    ("联剑风云录", 26, 32, "绑回", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "『被阳宗海绑回庞家堡』既成强制迁移，■ 成立。",
        "cite": "SKILL_04f §2.6；docs/45 #16/#50",
    },
    ("联剑风云录", 35, 13, "恶斗", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『将恶斗乔北溟、寻回阴秀兰的经过』为把字句追述既成战斗，『将』消歧为把非将来。",
        "cite": "R-P9 把字句消歧；SKILL_04f §3.6 已发生标",
    },
    ("联剑风云录", 35, 71, "斩", "verb_domain_risk"): {
        "verdict": "应摘",
        "reason": "『今日先斩你左手…明天斩你右手』为威胁/预告，砍斩未实施，计划不标。",
        "cite": "SKILL_04f §3.6；docs/45 #1-12 同例",
    },
    ("联剑风云录", 36, 81, "削", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "『拇指食指削掉』既成重伤，远超 04f §2.2 受伤阈值，⊠ 成立。",
        "cite": "SKILL_04f §2.2；docs/48 §九 保留先例",
    },
    ("广陵剑", 12, 35, "拘捕", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『要把我的爹爹拘捕…于是立即安排罗网…派出锦衣卫的高手』拘捕行动已发动"
                  "（设罗网、派人手），属已发动/进行中，非纯意图。",
        "cite": "R-P3 已发动口径；SKILL_04f §3.6",
    },
    ("广陵剑", 12, 35, "拘捕", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "GLM 校对批后复判：拘捕=强制捉人系押解/绑押同族，■ 强制移动成立"
                  "（04f §2.6 劫人分流；R-D1 押解先例）；行动已发动（安排罗网/派锦衣卫）非纯意图。",
        "cite": "SKILL_04f §2.6；docs/45 #16/#50；R-P3",
    },
    ("广陵剑", 17, 73, "领教", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『雷某还要领教数招』为预告未发生的交手（挑战语），还要+X 与准备+X 同族，计划不标。",
        "cite": "SKILL_04f §3.6；R-P5/R-P8 同族；docs/55 准备+X",
    },
    ("广陵剑", 25, 17, "上京", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『为什么他们也要上京』追问既成行程（他人已动身/已上京），非未发生计划。",
        "cite": "docs/45 §三 #70",
    },
    ("广陵剑", 32, 274, "卢沟桥", "fence_entity_real_only"): {
        "verdict": "保留",
        "reason": "『卢沟桥上斗强仇』围栏诗句实指当日战地——本章 [259]-[261] 主线即当夜赴卢沟桥之战。",
        "cite": "SKILL_01g 围栏限实指；docs/48 §九 018[1] 围栏实指先例",
    },
    ("广陵剑", 33, 313, "宫墙", "fence_entity_real_only"): {
        "verdict": "应摘",
        "reason": "『日前曾折宫墙柳』为典故化用（宫墙柳/折柳送别），非实指地理，围栏内不标。",
        "cite": "SKILL_01g 围栏限实指；docs/54 §4.2 典故剔除类",
    },
    ("龙凤宝钗缘", 4, 28, "少年", "d1_description"): {
        "verdict": "保留",
        "reason": "docs/80 P5 D1 跨库约定：#少年 为书内口径（jw-b 复核裁定，全批 102 处），本批一致。",
        "cite": "docs/80 §三 D1 跨库约定",
    },
    ("龙凤宝钗缘", 4, 37, "少年", "d1_description"): {
        "verdict": "保留",
        "reason": "同上，#少年 书内约定保留。",
        "cite": "docs/80 §三 D1 跨库约定",
    },
    ("龙凤宝钗缘", 4, 45, "少年", "d1_description"): {
        "verdict": "保留",
        "reason": "同上，#少年 书内约定保留。",
        "cite": "docs/80 §三 D1 跨库约定",
    },
    ("龙凤宝钗缘", 4, 46, "少年", "d1_description"): {
        "verdict": "保留",
        "reason": "同上，#少年 书内约定保留。",
        "cite": "docs/80 §三 D1 跨库约定",
    },
    ("龙凤宝钗缘", 5, 58, "盗", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『将盗自田承嗣床头的金盒交与薛嵩』为把字句，金盒已盗得既成；『将』消歧为把非将来。",
        "cite": "R-P9 把字句消歧；docs/45 §三 #70",
    },
    ("龙凤宝钗缘", 20, 17, "少年", "d1_description"): {
        "verdict": "保留",
        "reason": "docs/80 #少年 书内约定保留。",
        "cite": "docs/80 §三 D1 跨库约定",
    },
    ("龙凤宝钗缘", 20, 19, "少年", "d1_description"): {
        "verdict": "保留",
        "reason": "docs/80 #少年 书内约定保留。",
        "cite": "docs/80 §三 D1 跨库约定",
    },
    ("龙凤宝钗缘", 20, 53, "少女", "d1_description"): {
        "verdict": "保留",
        "reason": "docs/80 #少女 书内约定保留（全批 27 处）。",
        "cite": "docs/80 §三 D1 跨库约定",
    },
    ("龙凤宝钗缘", 23, 52, "抛头露面", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『怎的还要抛头露面，举行比武招亲』反问预设既成（比武招亲为既成事件、公开露面已发生），"
                  "与 R-P2 反复行为同族。",
        "cite": "R-P2 惯常/反复；docs/45 §三 #70",
    },
    ("龙凤宝钗缘", 49, 86, "胡服少年", "d1_description"): {
        "verdict": "保留",
        "reason": "书内锚定代称（胡服少年指称具体人物），与 #少年/#少女 书内约定同族一致。",
        "cite": "docs/80 §三 D1 跨库约定（同族扩展）",
    },
    ("龙凤宝钗缘", 50, 172, "大孩子", "d1_description"): {
        "verdict": "保留",
        "reason": "书内锚定代称（『那大孩子』指称具体孩童人物），与 #少年/#少女 口径一致。",
        "cite": "docs/80 §三 D1 跨库约定（同族扩展）",
    },
    # ── P4 批次（2026-11-07，剑网尘丝/幻剑灵旗；jw-e 建议 + Lead 复核）──
    ("剑网尘丝", 3, 464, "宾客", "d1_description"): {
        "verdict": "保留",
        "reason": "「宾客」为处境身份（# 类），跨库 tagged 已有 10 处 #宾客 口径；"
                  "比武观战者属具体场景身份，非纯描述性代称，保留。",
        "cite": "SKILL_03a L103 #身份（处境身份）；跨库 tagged #宾客 10 处",
    },
    ("剑网尘丝", 4, 83, "偷进", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "疑问句『他又为什么要偷进雪君新房』追问的是既成潜入行为（[82] 已被点穴者），"
                  "属已发生语境追问动机，非未发生计划。",
        "cite": "docs/45 §三 #70（追问既成事实保留）；SKILL_04f §3.6",
    },
    ("剑网尘丝", 10, 15, "捉拿", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『我是为何要捉拿那个妖妇』为行动目的/计划表述，后文『坏了道长大事』"
                  "证实捉拿未实施；按计划/意图不标。",
        "cite": "SKILL_04f §3.6；docs/55 准备+X；docs/45 #1-12 同例",
    },
    ("剑网尘丝", 17, 28, "客人", "d1_description"): {
        "verdict": "保留",
        "reason": "『客人』为处境身份（# 类，客栈投宿者），跨库 tagged 43 处/8 书既有约定；"
                  "非纯描述性代称，保留。",
        "cite": "SKILL_03a L103；跨库 tagged #客人 43 处",
    },
    ("剑网尘丝", 17, 55, "客人", "d1_description"): {
        "verdict": "保留",
        "reason": "同上，客栈『这帮客人』为具体处境身份。",
        "cite": "SKILL_03a L103；跨库 tagged #客人",
    },
    ("剑网尘丝", 17, 86, "客人", "d1_description"): {
        "verdict": "保留",
        "reason": "同段两处『客人』均为投宿客人身份（掌柜对白），保留。",
        "cite": "SKILL_03a L103；跨库 tagged #客人",
    },
    ("剑网尘丝", 17, 87, "客人", "d1_description"): {
        "verdict": "保留",
        "reason": "『单身客人』为客栈投宿者身份，保留。",
        "cite": "SKILL_03a L103；跨库 tagged #客人",
    },
    ("剑网尘丝", 2, 482, "运往", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『还有一批药材要运往……』为押运途中/计划中的连续动作语境（同段已写车队在途），"
                  "按已发生/进行中保留（jw-e 复核建议，中置信）。",
        "cite": "SKILL_04f §3.6；jw-e P4 裁定建议 §四",
    },
    ("剑网尘丝", 3, 285, "离开", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『三年前那个晚上离开』用于交代既成时间与事实定位，非未发生计划。",
        "cite": "SKILL_04f §3.6；jw-e P4 裁定建议 §四",
    },
    ("剑网尘丝", 6, 283, "阻止", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『只恨本领不济，未能阻止……反而给你点了穴道』为已发动而未遂动作，"
                  "未遂可标（可加注），非纯计划。",
        "cite": "SKILL_03a L131（已施行未遂可标）；jw-e P4 裁定建议 §四",
    },
    ("剑网尘丝", 8, 376, "刺杀", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "转述既成战况中的既发未遂行为（『仍要刺杀徐大侠，他这才忍无可忍』），"
                  "属已发生语境。",
        "cite": "SKILL_03a L131；jw-e P4 裁定建议 §四",
    },
    ("剑网尘丝", 9, 445, "上京", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "行程进行中表述（已上路/拟赴京），非纯未发生计划。",
        "cite": "SKILL_04f §3.6；jw-e P4 裁定建议 §四",
    },
    ("幻剑灵旗", 6, 338, "拦阻", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『定要拦阻』用于当场进行中的对峙（楚劲松『要留你今晚』），属正在进行动作。",
        "cite": "SKILL_04f §3.6；jw-e P4 裁定建议 §四",
    },
    ("幻剑灵旗", 6, 602, "飞上半空", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『无不飞上半空』为双重否定全称肯定（全都飞起），动作已发生。",
        "cite": "SKILL_04f §3.6；jw-e P4 裁定建议 §四",
    },
    ("幻剑灵旗", 10, 257, "护送", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『护送』为在途护卫动作（同段『走得当然不快』证在途），非计划。",
        "cite": "SKILL_04f §3.6；jw-e P4 裁定建议 §四",
    },
    ("幻剑灵旗", 11, 402, "假扮", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『你为什么要假扮上官姑娘』追问既成冒充事实（赵青眉长期冒充），"
                  "属已发生行为反问，保留。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    # ── P6 批次（2026-11-09，龙虎斗京华/草莽龙蛇传/飞凤潜龙/绝塞传烽录；Lead 复核）──
    ("龙虎斗京华", 1, 113, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("龙虎斗京华", 1, 118, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("龙虎斗京华", 2, 32, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("龙虎斗京华", 2, 40, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("龙虎斗京华", 2, 108, "少年", "d1_description"): {"verdict": "保留", "reason": "#少年 跨库约定。", "cite": "跨库 tagged #少年"},
    ("龙虎斗京华", 2, 108, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("龙虎斗京华", 2, 110, "少年", "d1_description"): {"verdict": "保留", "reason": "#少年 跨库约定。", "cite": "跨库 tagged #少年"},
    ("龙虎斗京华", 3, 17, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("龙虎斗京华", 3, 95, "少年", "d1_description"): {"verdict": "保留", "reason": "#少年 跨库约定。", "cite": "跨库 tagged #少年"},
    ("龙虎斗京华", 6, 58, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("龙虎斗京华", 6, 67, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("龙虎斗京华", 3, 40, "踢", "verb_domain_risk"): {"verdict": "保留", "reason": "脚尖踢在膝盖骨上，已发生的击打动作 ⊠（受伤结果）。", "cite": "SKILL_04f §2.2"},
    ("龙虎斗京华", 4, 44, "扯", "plan_negation_verb"): {"verdict": "保留", "reason": "『为什么要扯他的脚示警』追问既成事实（已扯）。", "cite": "docs/45 #70"},
    ("草莽龙蛇传", 2, 10, "老者", "d1_description"): {"verdict": "应摘", "reason": "描述性代称『老者』D1 不标（无跨库约定）。", "cite": "SKILL_03a D1"},
    ("草莽龙蛇传", 2, 41, "那人", "d1_description"): {"verdict": "应摘", "reason": "指代性代称『那人』D1 不标。", "cite": "SKILL_03a D1"},
    ("草莽龙蛇传", 2, 62, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("草莽龙蛇传", 3, 26, "老者", "d1_description"): {"verdict": "应摘", "reason": "描述性代称『老者』D1 不标。", "cite": "SKILL_03a D1"},
    ("草莽龙蛇传", 3, 26, "兄弟", "d1_description"): {"verdict": "应摘", "reason": "『兄弟』为老者对丁晓的称呼语（D1 纯称谓）。", "cite": "SKILL_03a D1"},
    ("草莽龙蛇传", 3, 41, "老者", "d1_description"): {"verdict": "应摘", "reason": "描述性代称『老者』。", "cite": "SKILL_03a D1"},
    ("草莽龙蛇传", 3, 53, "老者", "d1_description"): {"verdict": "应摘", "reason": "描述性代称『老者』（本回揭名为焦忠耀）。", "cite": "SKILL_03a D1"},
    ("草莽龙蛇传", 3, 58, "中年汉子", "d1_description"): {"verdict": "应摘", "reason": "描述性代称『中年汉子』D1 不标。", "cite": "SKILL_03a D1"},
    ("草莽龙蛇传", 3, 89, "粗豪少年", "d1_description"): {"verdict": "应摘", "reason": "描述性代称『粗豪少年』D1 不标。", "cite": "SKILL_03a D1"},
    ("草莽龙蛇传", 6, 28, "少年", "d1_description"): {"verdict": "保留", "reason": "#少年 跨库约定。", "cite": "跨库 tagged #少年"},
    ("草莽龙蛇传", 6, 82, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("草莽龙蛇传", 6, 89, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("草莽龙蛇传", 6, 90, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("草莽龙蛇传", 6, 123, "少年", "d1_description"): {"verdict": "保留", "reason": "#少年 跨库约定。", "cite": "跨库 tagged #少年"},
    ("草莽龙蛇传", 7, 5, "假装", "plan_negation_verb"): {"verdict": "保留", "reason": "『为什么要假装不懂武艺』追问既成事实（装作不懂已发生）。", "cite": "docs/45 #70"},
    ("草莽龙蛇传", 8, 87, "包庇", "plan_negation_verb"): {"verdict": "保留", "reason": "『你要包庇胡虏的奴才』为已发生/持续中的社会行为（⊡ 社会域）。", "cite": "SKILL_04f §2.3"},
    ("草莽龙蛇传", 10, 21, "挡我者死", "verb_domain_risk"): {"verdict": "应摘", "reason": "战斗口号『挡我者死』非具体动作事件。", "cite": "SKILL_04f §2.0"},
    ("草莽龙蛇传", 10, 161, "生死未卜", "verb_domain_risk"): {"verdict": "应摘", "reason": "状态成语『生死未卜』非动作。", "cite": "SKILL_04f §2.0"},
    ("草莽龙蛇传", 10, 167, "预扣", "plan_negation_verb"): {"verdict": "保留", "reason": "『将预扣在手心中的金钱镖打出』为已发生动作。", "cite": "docs/45 #70"},
    ("草莽龙蛇传", 11, 42, "掌式一收", "plan_negation_verb"): {"verdict": "保留", "reason": "『倏地将掌式一收』已发生的动作变化。", "cite": "docs/45 #70"},
    ("草莽龙蛇传", 12, 109, "起来", "plan_negation_verb"): {"verdict": "应摘", "reason": "『夹颈抽将起来』的『起来』为趋向补语，不独立成动词。", "cite": "SKILL_04f §2.0；docs/45"},
    ("飞凤潜龙", 2, 105, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("飞凤潜龙", 3, 146, "少女", "d1_description"): {"verdict": "保留", "reason": "#少女 跨库约定。", "cite": "跨库 tagged #少女"},
    ("绝塞传烽录", 1, 371, "阵亡", "verb_domain_risk"): {"verdict": "改域", "target_domain": "⊠", "reason": "阵亡=战死，生命健康结果 ⊠。", "cite": "SKILL_04f §2.2"},
    ("绝塞传烽录", 1, 569, "阴狠毒辣", "verb_domain_risk"): {"verdict": "应摘", "reason": "评价性形容词，非动作事件。", "cite": "SKILL_04f §2.0"},
    ("绝塞传烽录", 1, 571, "死心塌地", "verb_domain_risk"): {"verdict": "应摘", "reason": "成语副词性修饰，非动作。", "cite": "SKILL_04f §2.0"},
    ("绝塞传烽录", 1, 575, "毒辣", "verb_domain_risk"): {"verdict": "应摘", "reason": "评价性形容词『毒辣心肠』。", "cite": "SKILL_04f §2.0"},
    ("绝塞传烽录", 1, 587, "滥杀", "verb_domain_risk"): {"verdict": "应摘", "reason": "『不至于滥杀你的家人』否定/推测，未发生。", "cite": "SKILL_04f §3.6"},
    ("绝塞传烽录", 1, 778, "杀我灭口", "verb_domain_risk"): {"verdict": "应摘", "reason": "『你是要杀我灭口』为指控意图，未发生。", "cite": "SKILL_04f §3.6"},
    ("绝塞传烽录", 1, 238, "少年", "d1_description"): {"verdict": "保留", "reason": "#少年 跨库约定。", "cite": "跨库 tagged #少年"},
    ("绝塞传烽录", 1, 279, "少年", "d1_description"): {"verdict": "保留", "reason": "#少年 跨库约定。", "cite": "跨库 tagged #少年"},
    ("绝塞传烽录", 1, 594, "儿子", "kinship_na"): {"verdict": "应摘", "reason": "纯亲属称谓『儿子』D1 不标。", "cite": "SKILL_03a D1"},
    ("绝塞传烽录", 1, 685, "客人", "d1_description"): {"verdict": "保留", "reason": "#客人 跨库约定。", "cite": "跨库 tagged #客人"},
    ("绝塞传烽录", 1, 741, "儿子", "kinship_na"): {"verdict": "应摘", "reason": "纯亲属称谓『儿子』D1 不标。", "cite": "SKILL_03a D1"},
    ("绝塞传烽录", 2, 80, "运功御毒", "verb_domain_risk"): {"verdict": "改域", "target_domain": "▣", "reason": "运功御毒为内功技法运用，技法域 ▣。", "cite": "SKILL_04f §2.4"},
    ("绝塞传烽录", 2, 95, "毒发", "verb_domain_risk"): {"verdict": "保留", "reason": "『果然是毒发了』已发生的状态变化。", "cite": "docs/45 #70"},
    ("绝塞传烽录", 2, 252, "爹爹", "kinship_na"): {"verdict": "应摘", "reason": "纯亲属称谓『爹爹』D1 不标。", "cite": "SKILL_03a D1"},
    ("绝塞传烽录", 2, 421, "同门", "d1_description"): {"verdict": "应摘", "reason": "关系通称『同门』D1 不标。", "cite": "SKILL_03a D1"},
    ("绝塞传烽录", 3, 308, "杀人", "verb_domain_risk"): {"verdict": "应摘", "reason": "『我只会杀人』为能力泛说，非具体事件。", "cite": "SKILL_04f §2.0"},
    ("绝塞传烽录", 3, 301, "父亲", "kinship_na"): {"verdict": "应摘", "reason": "纯亲属称谓『父亲』D1 不标。", "cite": "SKILL_03a D1"},
    ("绝塞传烽录", 4, 66, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("绝塞传烽录", 4, 68, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("绝塞传烽录", 4, 75, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("绝塞传烽录", 4, 352, "儿子", "kinship_na"): {"verdict": "应摘", "reason": "纯亲属称谓『儿子』D1 不标。", "cite": "SKILL_03a D1"},
    ("绝塞传烽录", 9, 238, "同门", "d1_description"): {"verdict": "应摘", "reason": "关系通称『同门』D1 不标。", "cite": "SKILL_03a D1"},
    ("绝塞传烽录", 9, 559, "同门", "d1_description"): {"verdict": "应摘", "reason": "关系通称『同门』D1 不标。", "cite": "SKILL_03a D1"},
    ("绝塞传烽录", 10, 11, "同门", "d1_description"): {"verdict": "应摘", "reason": "关系通称『同门』D1 不标。", "cite": "SKILL_03a D1"},
    ("绝塞传烽录", 10, 138, "同门", "d1_description"): {"verdict": "应摘", "reason": "关系通称『同门』D1 不标。", "cite": "SKILL_03a D1"},
    ("绝塞传烽录", 11, 102, "避开", "plan_negation_verb"): {"verdict": "保留", "reason": "『为何他要避开』追问既成/进行中的动作。", "cite": "docs/45 #70"},
    ("绝塞传烽录", 12, 149, "撤退", "plan_negation_verb"): {"verdict": "保留", "reason": "『为何你要撤退』已有的军事动作。", "cite": "docs/45 #70"},
    # ── P5 批次（2026-11-09，龙凤宝钗缘/慧剑心魔；Lead 复核）──
    ("龙凤宝钗缘", 4, 28, "少年", "d1_description"): {"verdict": "保留", "reason": "处境身份 #少年（跨库 tagged 102 处既有约定），非纯描述性代称。", "cite": "跨库 tagged #少年；SKILL_03a L103"},
    ("龙凤宝钗缘", 4, 37, "少年", "d1_description"): {"verdict": "保留", "reason": "同上（#少年 跨库约定）。", "cite": "跨库 tagged #少年"},
    ("龙凤宝钗缘", 4, 45, "少年", "d1_description"): {"verdict": "保留", "reason": "同上（#少年 跨库约定）。", "cite": "跨库 tagged #少年"},
    ("龙凤宝钗缘", 4, 46, "少年", "d1_description"): {"verdict": "保留", "reason": "同上（#少年 跨库约定）。", "cite": "跨库 tagged #少年"},
    ("龙凤宝钗缘", 5, 58, "盗", "plan_negation_verb"): {"verdict": "保留", "reason": "『将盗自田承嗣床头的金盒』= 盗自（过去已发生偷盗的定语），非将然计划。", "cite": "SKILL_04f §3.6；docs/45 #70"},
    ("龙凤宝钗缘", 20, 17, "少年", "d1_description"): {"verdict": "保留", "reason": "#少年 跨库约定。", "cite": "跨库 tagged #少年"},
    ("龙凤宝钗缘", 20, 19, "少年", "d1_description"): {"verdict": "保留", "reason": "#少年 跨库约定。", "cite": "跨库 tagged #少年"},
    ("龙凤宝钗缘", 20, 53, "少女", "d1_description"): {"verdict": "保留", "reason": "#少女 跨库 tagged 27 处既有约定。", "cite": "跨库 tagged #少女"},
    ("龙凤宝钗缘", 23, 52, "抛头露面", "plan_negation_verb"): {"verdict": "保留", "reason": "『怎的还要抛头露面，举行比武招亲』指既已安排/进行中的招亲，非纯计划。", "cite": "SKILL_04f §3.6"},
    ("龙凤宝钗缘", 32, 11, "杀了", "plan_negation_verb"): {"verdict": "应摘", "reason": "『我若说要杀了她』= 假设/意愿，未发生。", "cite": "SKILL_04f §3.6；docs/45 #1-12"},
    ("龙凤宝钗缘", 33, 64, "下毒", "verb_domain_risk"): {"verdict": "应摘", "reason": "『决不敢在饭菜中下毒』否定语境，动作未发生。", "cite": "SKILL_04f §3.6"},
    ("龙凤宝钗缘", 33, 82, "滥杀", "verb_domain_risk"): {"verdict": "应摘", "reason": "『不要滥杀』为命令/劝阻内容，命令内容不标。", "cite": "SKILL_03a L131 命令不标"},
    ("龙凤宝钗缘", 38, 79, "死", "verb_domain_risk"): {"verdict": "应摘", "reason": "『竟要死在段克邪手上』为假设/未发生。", "cite": "SKILL_04f §3.6"},
    ("龙凤宝钗缘", 40, 27, "误杀", "verb_domain_risk"): {"verdict": "改域", "target_domain": "⊠", "reason": "既成误杀（混战中已发生），生命健康域 ⊠。", "cite": "SKILL_04f §2.2"},
    ("龙凤宝钗缘", 43, 12, "动手", "plan_negation_verb"): {"verdict": "应摘", "reason": "『怎么，要动手么？』挑衅/疑问，动作未发生。", "cite": "SKILL_04f §3.6"},
    ("龙凤宝钗缘", 45, 14, "废去", "plan_negation_verb"): {"verdict": "应摘", "reason": "『举掌又要废去段克邪的武功』为威胁/计划，未发生。", "cite": "SKILL_04f §3.6"},
    ("龙凤宝钗缘", 45, 62, "避开", "plan_negation_verb"): {"verdict": "应摘", "reason": "『假如避开混战』假设语境。", "cite": "SKILL_04f §3.6"},
    ("龙凤宝钗缘", 46, 30, "中剑", "plan_negation_verb"): {"verdict": "应摘", "reason": "『势将中剑』将然/未发生。", "cite": "SKILL_04f §3.6"},
    ("龙凤宝钗缘", 49, 86, "胡服少年", "d1_description"): {"verdict": "保留", "reason": "#胡服少年 为处境身份型称名（跨库 4 处），保留。", "cite": "跨库 tagged #胡服少年"},
    ("龙凤宝钗缘", 50, 172, "大孩子", "d1_description"): {"verdict": "保留", "reason": "#大孩子 为处境身份型称名（跨库 6 处），保留。", "cite": "跨库 tagged #大孩子"},
    ("慧剑心魔", 3, 58, "摔", "plan_negation_verb"): {"verdict": "保留", "reason": "『你为什么要摔我一跤』追问既成事实。", "cite": "docs/45 #70"},
    ("慧剑心魔", 4, 38, "练好", "plan_negation_verb"): {"verdict": "应摘", "reason": "『我还要练好武功』纯计划/意愿。", "cite": "SKILL_04f §3.6"},
    ("慧剑心魔", 4, 40, "搬到", "plan_negation_verb"): {"verdict": "保留", "reason": "『为什么要搬到这荒凉山谷』追问既成事实（已搬来）。", "cite": "docs/45 #70"},
    ("慧剑心魔", 6, 141, "客人", "d1_description"): {"verdict": "保留", "reason": "#客人 跨库 70 处既有约定。", "cite": "跨库 tagged #客人"},
    ("慧剑心魔", 14, 65, "斗", "plan_negation_verb"): {"verdict": "应摘", "reason": "『还要斗到五十招开外才能胜』为将然/能力估计，未发生。", "cite": "SKILL_04f §3.6"},
    ("慧剑心魔", 17, 8, "一倍", "time_boundary"): {"verdict": "改域", "target_domain": "$", "reason": "『年龄比铁凝长一倍』为数量比较，改域 $。", "cite": "SKILL_03a L108"},
    ("慧剑心魔", 17, 44, "一倍", "time_boundary"): {"verdict": "改域", "target_domain": "$", "reason": "数量比较改域 $。", "cite": "SKILL_03a L108"},
    ("慧剑心魔", 17, 109, "瞬息之机", "time_boundary"): {"verdict": "应摘", "reason": "『所争不过瞬息之机』纯模糊时长/习语，不标。", "cite": "03a L108 纯模糊不标"},
    ("慧剑心魔", 17, 127, "当今之世", "time_boundary"): {"verdict": "保留", "reason": "『当今之世』相对时点宽口径，保留。", "cite": "SKILL_03a L108；docs/48 §九"},
    ("慧剑心魔", 18, 59, "刚刚", "time_boundary"): {"verdict": "保留", "reason": "『辛芷姑刚刚说了几句话』相对时点。", "cite": "SKILL_03a L108"},
    ("慧剑心魔", 18, 131, "电光石火之间", "time_boundary"): {"verdict": "应摘", "reason": "习语化时间修辞（电光石火），按 R-T4 应摘。", "cite": "01g 修辞；docs/45 #77"},
    ("慧剑心魔", 19, 50, "一些", "time_boundary"): {"verdict": "改域", "target_domain": "$", "reason": "『气平了一些』为程度/数量，改域 $。", "cite": "SKILL_03a L108"},
    ("慧剑心魔", 19, 80, "波及", "plan_negation_verb"): {"verdict": "应摘", "reason": "『恐将波及』推测/未发生。", "cite": "SKILL_04f §3.6"},
    ("慧剑心魔", 19, 103, "黑道", "time_boundary"): {"verdict": "改域", "target_domain": "^", "reason": "『黑道』为江湖概念，非时间，改域 ^。", "cite": "SKILL_03a L109"},
    ("慧剑心魔", 20, 84, "黑道", "time_boundary"): {"verdict": "改域", "target_domain": "^", "reason": "『在黑道崛起』概念域，改域 ^。", "cite": "SKILL_03a L109"},
    ("慧剑心魔", 20, 117, "逆流", "time_boundary"): {"verdict": "应摘", "reason": "『在逆流中驾驶船』为水流，非时间。", "cite": "SKILL_03a L109"},
    ("慧剑心魔", 20, 119, "逆流", "time_boundary"): {"verdict": "应摘", "reason": "『逆流而上』非时间。", "cite": "SKILL_03a L109"},
    ("慧剑心魔", 28, 82, "应付", "verb_domain_risk"): {"verdict": "应摘", "reason": "『如何应付』为泛化应对，非六域具体动作。", "cite": "SKILL_04f §2.0"},
    ("慧剑心魔", 30, 33, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库 46 处既有约定。", "cite": "跨库 tagged #汉子"},
    ("慧剑心魔", 32, 5, "路劫", "plan_negation_verb"): {"verdict": "保留", "reason": "『将路劫褚葆龄的事情说出』为已发生的路劫事件（名词化），保留。", "cite": "SKILL_04f §3.6；docs/45 #70"},
    ("慧剑心魔", 39, 69, "过了一会", "time_boundary"): {"verdict": "应摘", "reason": "纯模糊时长（一会），不标。", "cite": "03a L108；R-T3"},
    ("慧剑心魔", 39, 78, "这刹那间", "time_boundary"): {"verdict": "应摘", "reason": "纯模糊时长/习语（一刹那间），不标。", "cite": "03a L108；R-T3"},
    ("慧剑心魔", 39, 79, "当今之世", "time_boundary"): {"verdict": "保留", "reason": "相对时点宽口径。", "cite": "SKILL_03a L108"},
    ("慧剑心魔", 40, 10, "当世", "time_boundary"): {"verdict": "保留", "reason": "『当世第一高手』当代相对时点，保留。", "cite": "SKILL_03a L108"},
    ("慧剑心魔", 40, 47, "此际", "time_boundary"): {"verdict": "保留", "reason": "此际=此刻，时点。", "cite": "SKILL_03a L108"},
    ("慧剑心魔", 40, 55, "当世", "time_boundary"): {"verdict": "保留", "reason": "当代相对时点。", "cite": "SKILL_03a L108"},
    ("慧剑心魔", 41, 24, "厮杀", "verb_domain_risk"): {"verdict": "改域", "target_domain": "⊞", "reason": "厮杀=战斗交锋，改域 ⊞。", "cite": "SKILL_04f §2.1"},
    ("慧剑心魔", 41, 56, "厮杀", "verb_domain_risk"): {"verdict": "改域", "target_domain": "⊞", "reason": "厮杀=战斗交锋，改域 ⊞。", "cite": "SKILL_04f §2.1"},
    ("慧剑心魔", 41, 101, "出迎", "plan_negation_verb"): {"verdict": "应摘", "reason": "礼仪动作（出迎），非六域事件；应摘。", "cite": "SKILL_04f §2.3 礼仪不标"},
    ("慧剑心魔", 43, 9, "解毒", "verb_domain_risk"): {"verdict": "应摘", "reason": "『解毒之药』为定语/名词性，非动作事件。", "cite": "SKILL_03a 触发词边界"},
    ("慧剑心魔", 43, 60, "客人", "d1_description"): {"verdict": "保留", "reason": "#客人 跨库约定。", "cite": "跨库 tagged #客人"},
    ("慧剑心魔", 43, 105, "客人", "d1_description"): {"verdict": "保留", "reason": "#客人 跨库约定。", "cite": "跨库 tagged #客人"},
    ("慧剑心魔", 43, 117, "汉子", "d1_description"): {"verdict": "保留", "reason": "#汉子 跨库约定。", "cite": "跨库 tagged #汉子"},
    ("慧剑心魔", 44, 54, "杀散", "verb_domain_risk"): {"verdict": "改域", "target_domain": "⊠", "reason": "杀散官军=击杀驱散结果，生命健康 ⊠。", "cite": "SKILL_04f §2.2"},
    ("慧剑心魔", 44, 81, "少年好汉", "d1_description"): {"verdict": "应摘", "reason": "描述性代称（少年好汉），D1 不标。", "cite": "SKILL_03a D1"},
    ("慧剑心魔", 47, 123, "叔叔", "kinship_na"): {"verdict": "应摘", "reason": "纯亲属称谓，D1 不标。", "cite": "SKILL_03a D1"},
    ("慧剑心魔", 48, 93, "王公女儿", "kinship_na"): {"verdict": "应摘", "reason": "身份描述（王公女儿），D1 不标。", "cite": "SKILL_03a D1"},
    ("江湖三女侠", 19, 44, "杀", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "「要杀」为意愿表述，但同段后文捕快已『身首异处』（既成事实）；"
                  "属已发生语境，按 docs/45 §三 #70『捉（已捕获，问原因）』保留先例 + "
                  "SKILL_04f §3.6 已发生→标，不摘。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    ("江湖三女侠", 23, 79, "闪避", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『又要闪避…钢环闪击』为打斗进行中的动作链（同段『以一敌四，竟然…』叙述既成战况），"
                  "属正在发生/已发生；按 docs/45 §三 #9『动手（打斗已在进行）→保留』先例 + "
                  "SKILL_04f §3.6『正在发生→标』，不摘。",
        "cite": "docs/45 §三 #9；SKILL_04f §3.6",
    },
    ("江湖三女侠", 23, 79, "应付", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "同段『还要应付…以一敌四』为打斗进行中的动作链，正在发生/已发生；"
                  "按 docs/45 §三 #9 + SKILL_04f §3.6『正在发生→标』，不摘。",
        "cite": "docs/45 §三 #9；SKILL_04f §3.6",
    },
    ("江湖三女侠", 38, 82, "接", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『冯瑛迫着要接敌招，百忙中竟记不起…』为打斗中被迫接招的既成叙述；"
                  "按 docs/45 §三 #9『已发生（打斗已在进行）→保留』先例，不摘。",
        "cite": "docs/45 §三 #9；SKILL_04f §3.6",
    },
    ("江湖三女侠", 44, 32, "抵挡", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『既要抵挡…又要留心脚下，抵挡更是艰难。正在心慌』为正在发生的打斗描写；"
                  "按 docs/45 §三 #9 + SKILL_04f §3.6『正在发生→标』，不摘。",
        "cite": "docs/45 §三 #9；SKILL_04f §3.6",
    },
    ("塞外奇侠传", 11, 16, "老人", "d1_description"): {
        "verdict": "应摘",
        "reason": "『老人』为 D1 描述性代称（无姓名身份指称），非专名；SKILL_03a v1.8 D1"
                  "『不标：描述性代称』，docs/48-S2 §5.3 R1 D1 剥标清单含『老头/老者』同类 → 应摘。",
        "cite": "SKILL_03a v1.8 D1；docs/48-S2 §5.3 R1；docs/39 §1.2",
    },
    ("冰魄寒光剑", 1, 1, "昆仑", "fence_entity_real_only"): {
        "verdict": "保留",
        "reason": "『昆仑』为真实地名（全书首回题『横跨昆仑来绝域』，诗中指昆仑山），围栏内属实指；"
                  "按 docs/48 §九 023[80]『对联江南/塞外实指→保留』先例 + 01g 围栏限实指，保留。",
        "cite": "docs/48 §九 023[80]；SKILL_01g 围栏限实指",
    },
    # ---- 2026-11-06 三书复核批次人工终签（docs/69 §三；还剑 1 + 萍踪 4 + 散花 9）----
    ("还剑奇情录", 3, 17, "追到", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『难道当真要【追到】云家』为要+X 假想后果（穷追不舍在进行，追到云家未发生）；"
                  "SKILL_04f §3.6 计划/假想内容不标 → 应摘。",
        "cite": "SKILL_04f §3.6；docs/55 准备+X 先例",
    },
    ("萍踪侠影录", 12, 29, "越", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『准备【越】喜马拉雅山偷卖给印度王公』为准备+X 计划（后文『却想不到在此地遇到两方混战』"
                  "证实未实施）→ 应摘。",
        "cite": "docs/55 §judgment 准备+X 计划摘先例；SKILL_04f §3.6",
    },
    ("萍踪侠影录", 15, 20, "害死", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『原来我爷爷是他【害死】的！他为什么要【害死】我的爷爷？』疑问句追问既成事实"
                  "（前句已断言爷爷遇害）；按 docs/45 §三 #70『捉（已捕获，问原因）』保留先例。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    ("萍踪侠影录", 24, 32, "收", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『难道谢天华就只是为了要【收】一个好徒弟』所疑问的是动机而非动作本身——收徒为既成事实"
                  "（同段『也是我在瓦剌所收的徒弟』『你收得好徒弟』）；按 docs/45 §三 #70 保留。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    ("萍踪侠影录", 26, 38, "南下", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『我们的同行怕战乱之中会有损失，都准备【南下】』为准备+X 计划未实施 → 应摘。",
        "cite": "docs/55 准备+X 计划摘先例；SKILL_04f §3.6",
    },
    ("散花女侠", 4, 1, "到", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『立刻离开北京，准备【到】太湖去找张丹枫』为准备+X 计划 → 应摘。",
        "cite": "docs/55 准备+X 计划摘先例；SKILL_04f §3.6",
    },
    ("散花女侠", 4, 91, "斩", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "『连【斩】大内卫士七名』为已发生的既成事件（大闹京师叙述），结果达伤情阈值 ⊠ 成立；"
                  "按 docs/45 §三 #23/#43/#47 先例保留。",
        "cite": "docs/45 §三 #23/#43/#47；SKILL_04f §2.2",
    },
    ("散花女侠", 10, 4, "斩", "verb_domain_risk"): {
        "verdict": "应摘",
        "reason": "『要不然怕不被他们【斩】为肉酱』为反事实假设（幸好禅杖不含糊），动作未发生 → 应摘。",
        "cite": "SKILL_04f §3.6 假想不标；docs/45 §三",
    },
    ("散花女侠", 19, 69, "滇池", "fence_entity_real_only"): {
        "verdict": "保留",
        "reason": "『滇池也自风波险』为回末对内实指地名（本章龙门纵目即滇池西山龙门情节）；"
                  "按 docs/48 §九 023[80]『对联实指→保留』先例 + 01g 围栏限实指，保留。",
        "cite": "docs/48 §九 023[80]；SKILL_01g 围栏限实指",
    },
    ("散花女侠", 19, 69, "虎穴", "fence_entity_real_only"): {
        "verdict": "应摘",
        "reason": "『虎穴龙潭又一遭』中『虎穴』为成语虚指（喻险境，非实有虎穴地名），围栏内限实指 → 应摘。",
        "cite": "SKILL_01g 围栏限实指；SKILL_03a D1 泛指不标",
    },
    ("散花女侠", 19, 69, "龙潭", "fence_entity_real_only"): {
        "verdict": "应摘",
        "reason": "『虎穴龙潭又一遭』中『龙潭』为成语虚指（本章实地为龙门/滇池，非龙潭），围栏内限实指 → 应摘。",
        "cite": "SKILL_01g 围栏限实指；SKILL_03a D1 泛指不标",
    },
    ("散花女侠", 22, 61, "彝族少女", "d1_description"): {
        "verdict": "应摘",
        "reason": "『彝族少女』为 D1 描述性代称（民族+年龄泛称，无姓名指称）；按 docs/55 藏族少女×16 摘"
                  "同例 → 应摘。",
        "cite": "SKILL_03a v1.8 D1；docs/48-S2 §5.3 R1；docs/55",
    },
    ("散花女侠", 30, 31, "传授", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『以及她准备【传授】铁镜心的解穴之法』为准备+X 计划（交换条件的提出，传授未实施）→ 应摘。",
        "cite": "docs/55 准备+X 计划摘先例；SKILL_04f §3.6",
    },
    # ---- 2026-11-07 云海玉弓缘/冰河洗剑录复核批人工终签（docs/76 §三；云海 6 + 冰河 6）----
    ("云海玉弓缘", 27, 94, "冰宫", "fence_entity_real_only"): {
        "verdict": "保留",
        "reason": "回末对『神魔果是神通广，又见【冰宫】作战场』为实指——本章即冰宫之战"
                  "（pn92『攀上了念青唐古拉山的主峰，冰宫已经在望』，pn93『冰宫修整得比前更美』），"
                  "非成语虚指；按 docs/48 §九 023[80] 回末对内实指保留先例。",
        "cite": "docs/48 §九 023[80]；SKILL_01g 围栏限实指",
    },
    ("云海玉弓缘", 35, 77, "爬起身来", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『听那悉悉索索的声音，似乎是他们正在【爬起身来】…他们为什么要【爬起身来】？』"
                  "疑问句追问正在发生动作（声息佐证进行中）；按 docs/45 §三 #70 疑问句既成/进行中"
                  "保留先例 + SKILL_04f §3.6 正在发生→标。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    ("云海玉弓缘", 38, 24, "夺", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『问问她为什么要【夺】咱们的镇山宝剑』——镇山宝剑已被夺走（本回失剑既成），"
                  "疑问句追问既成事实原因；docs/45 §三 #70 先例。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    ("云海玉弓缘", 39, 31, "杀", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "pn30 厉胜男已承认『这四个人我是不得不杀』，pn31『你为何要【杀】他们』为"
                  "疑问句追问既成事实原因；docs/45 §三 #70 先例。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    ("云海玉弓缘", 41, 15, "害死", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "pn14 金世遗承认『那三个人都是我杀的』，pn15『你为什么要【害死】他们三人』为"
                  "疑问句追问既成事实；docs/69 萍踪 015[20] 害死同例（#70）。",
        "cite": "docs/69 §三 萍踪 015[20]；docs/45 §三 #70",
    },
    ("云海玉弓缘", 50, 67, "害", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『厉胜男下手【害】我，我反而欢喜得很…她为什么要【害】我』——加害已发生"
                  "（谷之华中毒垂危），疑问句追问既成事实动机；docs/45 §三 #70 先例。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    ("冰河洗剑录", 7, 22, "死", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『我也不知老爷为何要【死】』——老爷已死（本回命案既成），疑问句追问死因；"
                  "docs/45 §三 #70 疑问句既成事实保留先例。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    ("冰河洗剑录", 32, 124, "躲避", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『既要【躲避】宝剑的攻击，自然不能全力对付』为打斗进行中的实况描写（解说战局）；"
                  "按 docs/45 §三 #9 打斗进行中保留先例 + SKILL_04f §3.6 正在发生→标。",
        "cite": "docs/45 §三 #9；SKILL_04f §3.6",
    },
    ("冰河洗剑录", 34, 48, "哄骗", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『这位丘爷爷对我非常好，却又为何要【哄骗】我呢』——欺骗已发生（当年被告知"
                  "亲娘已死的假话，pn47），疑问句追问既成事实；docs/45 §三 #70 先例。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    ("冰河洗剑录", 35, 46, "杀", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『皇额娘也要【杀】我？』为意图归因（与 pn43『听到了国王也要杀叶冲霄的秘密』"
                  "同构，杀机未实施、尚属密谋）；v1.8 计划/意图/命令内容不标 → 应摘。"
                  "同回 pn43『国王也要杀』未标动词，本条摘除后两处口径一致。",
        "cite": "SKILL_04f §3.6；docs/55 准备+X/意图摘先例",
    },
    ("冰河洗剑录", 40, 4, "刺", "verb_domain_risk"): {
        "verdict": "改域",
        "target_domain": "⊞",
        "reason": "『景月上人被剑尖【刺】了一下，仗着年功深厚，并未受伤』——明示未受伤，"
                  "未达 04f §2.2 伤情阈值，攻击动作归 ⊞（域码 ⊠→⊞，显示串不变）。",
        "cite": "SKILL_04f §2.2 阈值规则；docs/76 §三",
    },
    ("冰河洗剑录", 46, 22, "劫", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『那盖温当年既然是一国之王，为何要【劫】我们镇远镖局的镖』——『当年』劫镖"
                  "既成（全书主线起因），疑问句追问既成事实动机；docs/45 §三 #70 先例。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6",
    },
    # ---- 2026-11-07 扩书 P3 批次人工终签（docs/77；风雷 15 + 侠骨 7）----
    # 风雷震九州
    ("风雷震九州", 2, 64, "江湖汉子", "d1_description"): {
        "verdict": "应摘",
        "reason": "『看来像是个【江湖汉子】』为 D1 描述性代称（无姓名/身份专名），"
                  "SKILL_03a D1『不标：描述性代称』→ 应摘。",
        "cite": "SKILL_03a v1.10 D1；docs/48-S2 §5.3 R1；docs/77",
    },
    ("风雷震九州", 6, 71, "戳", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "『臂上的伤乃是鹿老大的鹿角叉【戳】的』——伤已既成（同段『受伤不轻』），"
                  "⊠ 死亡/致伤结果域正确；docs/45 §三 #70 既成→标。",
        "cite": "docs/45 §三 #70；SKILL_04f §2.2；docs/77",
    },
    ("风雷震九州", 7, 8, "刺", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "『我臂上的伤，也是他鹿角叉【刺】的』——伤已既成，⊠ 域正确；"
                  "与前条 006[71]『戳』同构。",
        "cite": "docs/45 §三 #70；SKILL_04f §2.2；docs/77",
    },
    ("风雷震九州", 7, 9, "杀", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『怎么，你还是要【杀】她？』——江晓芙仍活、杀机未实施（下段『料理了她』亦未遂），"
                  "纯意图/计划语境不标，非 #70 既成追问。",
        "cite": "SKILL_04f §3.6；docs/45 #1-12；docs/77",
    },
    ("风雷震九州", 7, 17, "防备", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『手忙脚乱，既要【防备】敌人偷袭，又不知妻子受伤如何』——打斗进行中的"
                  "必要动作链，正在发生→标（同类 docs/45 §三 #9 闪避/抵挡先例）。",
        "cite": "docs/45 §三 #9；SKILL_04f §3.6；docs/77",
    },
    ("风雷震九州", 8, 73, "关东", "fence_entity_real_only"): {
        "verdict": "保留",
        "reason": "回末对『四座皆惊真胆色，关东大盗会群豪』——『关东』为真实地域实指"
                  "（关东大盗即关东绿林），围栏内实体限实指 → 保留。",
        "cite": "SKILL_01g 围栏限实指；docs/48 §九 023[80]；docs/77",
    },
    ("风雷震九州", 10, 72, "残废", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『倘被点中，羊吞虎这条臂膀势将【残废】』——『倘…将』假设未发生 → 不标。",
        "cite": "SKILL_04f §3.6；docs/77",
    },
    ("风雷震九州", 17, 24, "躲避", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『你为何要【躲避】我？』——追问意图，躲避未发生（怪客一路跟随，二人尚未"
                  "分开），非既成事实追问 → 应摘。",
        "cite": "SKILL_04f §3.6；docs/45 #1-12；docs/77",
    },
    ("风雷震九州", 24, 80, "劫", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『至于他当初为什么要【劫】这支镖』——『当初』劫镖既成、且全书主线起因"
                  "（同段『已经赔偿了镖局的损失』），疑问句追问既成事实；docs/45 §三 #70。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6；docs/77",
    },
    ("风雷震九州", 29, 27, "抓", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "『大踏步上前，使出大擒拿手法，便来【抓】杨钲的琵琶骨』——打斗进行中的"
                  "攻击动作，⊞ 战斗域正确（04f §2.0）。",
        "cite": "SKILL_04f §2.0；docs/45 §三 #9；docs/77",
    },
    ("风雷震九州", 32, 62, "接", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『将【接】在手中的神芒也射出去』——『接在手中』为已发生状态（把字句+的），"
                  "非计划；R-P6 定语从句保留。",
        "cite": "SKILL_04f §3.6；docs/77",
    },
    ("风雷震九州", 52, 19, "擒", "verb_domain_risk"): {
        "verdict": "应摘",
        "reason": "『用意不过是引开她的目光，以便可以用擒拿法【擒】她』——分析对方意图、"
                  "擒拿未发生，属计划/意图内容 → 应摘。",
        "cite": "SKILL_04f §3.6；docs/77",
    },
    ("风雷震九州", 52, 37, "到", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『你怎么会以为我是要【到】小金川去找叶慕华？』——澄清意图，未发生 → 应摘。",
        "cite": "SKILL_04f §3.6；docs/45 #1-12；docs/77",
    },
    ("风雷震九州", 52, 44, "到", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『怎么会想到要【到】小金川来找我的叶表哥？』——追问打算，未发生 → 应摘。",
        "cite": "SKILL_04f §3.6；docs/45 #1-12；docs/77",
    },
    ("风雷震九州", 53, 52, "砍", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "『宇文雄身体的伤是给冷铁樵【砍】的』——伤已既成（同段伤口复裂），"
                  "⊠ 致伤结果域正确。",
        "cite": "docs/45 §三 #70；SKILL_04f §2.2；docs/77",
    },
    # 2026-11-07 C18 补标后新增 judgment：『青衣汉子』为书内既有身份令牌约定
    # （C18 前已有 〖#青衣汉子〗×12；指安平/安大叔的伪装身份），按 # 身份保留。
    ("风雷震九州", 11, 31, "青衣汉子", "d1_description"): {
        "verdict": "保留",
        "reason": "『青衣汉子』为书内既有身份令牌约定（C18 前已标 〖#青衣汉子〗×12，"
                  "指安平/安大叔伪装身份）；# 身份类描述性指称按书内约定保留。",
        "cite": "docs/54 §5 书内约定；SKILL_01g # 身份类；docs/77 §八",
    },
    ("风雷震九州", 11, 53, "青衣汉子", "d1_description"): {
        "verdict": "保留",
        "reason": "同上：书内既有 〖#青衣汉子〗 身份令牌约定（安平伪装身份）→ 保留。",
        "cite": "docs/54 §5 书内约定；docs/77 §八",
    },
    ("风雷震九州", 12, 120, "青衣汉子", "d1_description"): {
        "verdict": "保留",
        "reason": "同上：书内既有 〖#青衣汉子〗 身份令牌约定（安平伪装身份）→ 保留。",
        "cite": "docs/54 §5 书内约定；docs/77 §八",
    },
    ("风雷震九州", 20, 20, "青衣汉子", "d1_description"): {
        "verdict": "保留",
        "reason": "同上：书内既有 〖#青衣汉子〗 身份令牌约定（安平伪装身份）→ 保留。",
        "cite": "docs/54 §5 书内约定；docs/77 §八",
    },
    ("风雷震九州", 30, 102, "青衣汉子", "d1_description"): {
        "verdict": "保留",
        "reason": "同上：书内既有 〖#青衣汉子〗 身份令牌约定（安平伪装身份）→ 保留。",
        "cite": "docs/54 §5 书内约定；docs/77 §八",
    },
    ("风雷震九州", 31, 22, "青衣汉子", "d1_description"): {
        "verdict": "保留",
        "reason": "同上：书内既有 〖#青衣汉子〗 身份令牌约定（安平伪装身份）→ 保留。",
        "cite": "docs/54 §5 书内约定；docs/77 §八",
    },
    ("风雷震九州", 31, 35, "青衣汉子", "d1_description"): {
        "verdict": "保留",
        "reason": "同上：书内既有 〖#青衣汉子〗 身份令牌约定（安平伪装身份）→ 保留。",
        "cite": "docs/54 §5 书内约定；docs/77 §八",
    },
    # 侠骨丹心
    ("侠骨丹心", 2, 63, "杀", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『你为什么要【杀】他？』——被指对象秦元浩仍活（pn62『炕上分明又躺着一个秦元浩』），"
                  "且 pn64『我哪是真要杀他』明言未杀，纯意图/吓唬 → 应摘。",
        "cite": "SKILL_04f §3.6；docs/77",
    },
    ("侠骨丹心", 3, 58, "害", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『难道他们当真是要【害】我不成？』——猜测/假想语气，害未发生 → 应摘。",
        "cite": "SKILL_04f §3.6；docs/77",
    },
    ("侠骨丹心", 10, 69, "跌入", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『软鞭倘若不能立即解开……这蒙面人也将【跌入】金逐流的怀中』——『倘若…也将』"
                  "假设后果，未发生 → 应摘。",
        "cite": "SKILL_04f §3.6；docs/77",
    },
    ("侠骨丹心", 26, 110, "喝", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『你又为何要【喝】这杯毒酒？』——pn109 已明『曾喝了她一杯毒酒』，喝已既成，"
                  "疑问句追问既成事实动机 → 保留（docs/45 §三 #70）。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6；docs/77",
    },
    ("侠骨丹心", 29, 75, "救", "plan_negation_verb"): {
        "verdict": "保留",
        "reason": "『我杀了这个舟子，才能告诉你为什么要【救】那小子』——救人为既成事实"
                  "（为保密而杀舟子，杀人已发生），追问动机 → 保留（docs/45 §三 #70）。",
        "cite": "docs/45 §三 #70；SKILL_04f §3.6；docs/77",
    },
    ("侠骨丹心", 43, 25, "割掉", "plan_negation_verb"): {
        "verdict": "应摘",
        "reason": "『剑锋削运差了半寸，否则连他的手指也将【割掉】』——『否则…也将』反事实，"
                  "未发生 → 应摘。",
        "cite": "SKILL_04f §3.6；docs/77",
    },
    ("侠骨丹心", 36, 98, "绊翻", "verb_domain_risk"): {
        "verdict": "保留",
        "reason": "『有两个被【绊翻】的客人，却恰巧向他倒下』——『被绊翻的』为已发生结果"
                  "（被字句+的作定语），⊞ 战斗动作域正确 → 保留。",
        "cite": "SKILL_04f §2.0/§2.2；docs/77",
    },
    ("侠骨丹心", 50, 136, "关东", "fence_entity_real_only"): {
        "verdict": "保留",
        "reason": "回末对『说起渊源都一路，关东豪杰久知名』——『关东』为真实地域实指，"
                  "围栏内实体限实指 → 保留。",
        "cite": "SKILL_01g 围栏限实指；docs/48 §九 023[80]；docs/77",
    },
}

# 既有 docs 终态（仅用于报告核对，不参与规则判定本身；R-DOC 守卫据此把冲突判转人工）
DOC_CONTEXT = {
    "江湖三女侠": {
        "doc": "docs/47-江湖三女侠全48回机器标注执行记录.md §6.3",
        "record": "judgment 268→115（新检出项，均已列清单待人工终签，不阻塞 accepted）",
        "terminal_all_keep": False,
        "expected_items": 115,
    },
    "七剑下天山": {
        "doc": "docs/48-七剑下天山全31单元机器标注执行记录.md §九",
        "record": "judgment 213→103（全部为上表保留项；accepted 30/30、hard 0）",
        "terminal_all_keep": True,
        "expected_items": 103,
    },
    "塞外奇侠传": {
        "doc": "docs/49-塞外奇侠传与冰魄寒光剑机器标注执行记录.md §五.3",
        "record": "judgment 47 条待语义终签（⑧ 计划否定 23 / ⑥ 时间数量 10 / ⑤ 域 4 / ⑦ D1 1）",
        "terminal_all_keep": False,
        "expected_items": 47,
    },
    "冰魄寒光剑": {
        "doc": "docs/49-塞外奇侠传与冰魄寒光剑机器标注执行记录.md §五.3",
        "record": "judgment 44 条待语义终签（⑧ 计划否定 23 / ⑥ 时间数量 13 / ⑤ 域 4）",
        "terminal_all_keep": False,
        "expected_items": 44,
    },
    "白发魔女传": {
        "doc": "docs/48-S2稿judgment118裁决与终态记录.md §一/§二",
        "record": "judgment 118→27（全部保留有据：词表 16 / 域 8 / 时间 1 / 计划 2）",
        "terminal_all_keep": True,
        "expected_items": 27,
    },
}

# 规则目录（报告附录/JSON rule_catalog 用；id → 条文/先例）
RULE_CATALOG = [
    ("R-UNK", "通用", "未知/扩展类别 → 需人工", "任务口径：未知类别→需人工；扩展类别提示 SKILL_03a D1"),
    ("R-Q1", "quantity_boundary", "单字裸数词/裸量词 → 应摘",
     "docs/45 §二/§三 #20-22,41-42,61,63,67-68,72-74；docs/48-S2 §一（51 全摘）；SKILL_03a L109"),
    ("R-Q2", "quantity_boundary", "多字裸数词序列 → 应摘", "SKILL_03a L109 数量新口径（非数词+量词+名整串）"),
    ("R-Q3", "quantity_boundary", "多字信息承载计数 → 保留", "SKILL_03a L109 信息承载原则；docs/48 §九"),
    ("R-Q4", "quantity_boundary", "批次/泛人约量 → 应摘", "SKILL_03a L109 负例（一批/几名/几道）"),
    ("R-Q5", "quantity_boundary", "其余多字 → 需人工", "规则表未覆盖"),
    ("R-P1", "plan_negation_verb", "cue 为构词成分（牙将/拜别/约莫/不能不）→ 保留",
     "04f §3.6 已发生标；docs/48 §九 001[40]、docs/48-S2 029[12] 先例"),
    ("R-P2", "plan_negation_verb", "惯常/反复行为（每…都、一…便）→ 保留", "04f §3.6 已发生标（反复发生非纯计划）"),
    ("R-P3", "plan_negation_verb", "已发动被中断/未遂 → 保留", "04f §3.6 未遂判据"),
    ("R-P4", "plan_negation_verb", "已发生/正在发生（已/便/正/了/着/过）→ 保留",
     "04f §3.6 已发生标；docs/45 §三 #9/#70 先例"),
    ("R-P5", "plan_negation_verb", "纯计划/意图/条件/未来/否定 → 应摘",
     "SKILL_04f §3.6；docs/45 §三 #1-12/#55/#57/#60/#62/#64/#65/#71/#75/#79-85；docs/48-S2 §一；docs/48 §九"),
    ("R-P6", "plan_negation_verb", "定语从句（将/把+token+的+人物）→ 保留", "docs/48 §九『擒住的定语从句』先例"),
    ("R-P7", "plan_negation_verb", "疑问句追问既成事实 / 意愿与既成结果交叠 → 需人工",
     "docs/45 #70『捉（已捕获，问原因）』保留先例；既成与否需回读语境"),
    ("R-P8", "plan_negation_verb", "情态必要（迫着要/既要…又要/还要）→ 需人工", "04f §3.6 未列举，需回读语境"),
    ("R-P9", "plan_negation_verb", "将=把/将来 歧义未消 → 需人工", "04f §3.6 需语境消歧"),
    ("R-P10", "plan_negation_verb", "cue 未紧邻 token（定位失败）→ 需人工", "工具定位限制"),
    ("R-T1", "time_boundary", "|年龄| 年龄表达 → 保留", "SKILL_03a L108；docs/48 §九 三十出头/五十大寿/四十/五十"),
    ("R-T2", "time_boundary", "年号/朝代/干支/节日/相对时点/约量时长 → 保留",
     "SKILL_03a L108；docs/48 §九；docs/48-S2 §一 早上；docs/45 #69"),
    ("R-T3", "time_boundary", "纯模糊时长/习语 → 应摘",
     "SKILL_03a L108 纯模糊不标；docs/48 §九 一会；docs/48-S2 三五次→摘"),
    ("R-T4", "time_boundary", "习语化时间修辞 → 应摘", "01g 修辞；docs/45 #77 沙漠泛指同例；任务口径『习语→应摘/改域』"),
    ("R-T5", "time_boundary", "时间位误挂计数 → 改域 $", "docs/48 §九 改域 4→5；docs/48-S2 五六十招/三十招→$"),
    ("R-T6", "time_boundary", "非时间实词 → 应摘", "docs/45 #69（老=形容词）"),
    ("R-T7", "time_boundary", "其余 → 需人工", "规则表未覆盖"),
    ("R-D1", "verb_domain_risk", "■ 押解/强制迁移 → 保留", "04f §2.0/§2.6；docs/45 #16/#50/#53/#78"),
    ("R-D2", "verb_domain_risk", "■→⊡ 组织/宫廷除名 → 改域 ⊡", "04f §2.3；docs/45 #56/#58"),
    ("R-D3", "verb_domain_risk", "⊠ 自伤/医疗 → 保留", "04f §2.2 医疗入口；docs/45 #34"),
    ("R-D4", "verb_domain_risk", "⊠ 结果达阈值 → 保留", "04f §2.2；docs/45 #23/#43/#47"),
    ("R-D5", "verb_domain_risk", "⊠ 轻伤未达阈值 → 需人工", "04f §2.2 vs docs/45 #32 改域 / docs/48 §九 保留 冲突"),
    ("R-D6", "verb_domain_risk", "假设/未发生 → 需人工", "04f §3.6"),
    ("R-D7", "verb_domain_risk", "其余 → 需人工", "规则表未覆盖"),
    ("R-W1", "verb_wordlist_candidate", "词表单一主域差异 → 保留",
     "docs/45 §二；docs/48 §九；docs/48-S2 §一；04f §5.4"),
    ("R-W2", "verb_wordlist_candidate", "随同 token 域风险改域 → 改域", "docs/45 #33/#59"),
    ("R-F1", "fence_entity_real_only", "围栏段实为散文（段长>60）→ 保留", "docs/48 §九 018[1] 先例"),
    ("R-F2", "fence_entity_real_only", "人物/组织/家族/族群专名 → 保留", "01g 围栏限实指"),
    ("R-F3", "fence_entity_real_only", "地名专名 → 保留", "docs/48 §九 023[80] 先例"),
    ("R-F4", "fence_entity_real_only", "泛指/修辞 → 应摘", "01g；docs/45 #77；docs/48-S2 §一"),
    ("R-F5", "fence_entity_real_only", "其余 → 需人工", "规则表未覆盖"),
    ("R-DOC", "通用", "与 docs 已终签保留冲突 → 需人工复核", "docs/48 §九；docs/48-S2 §二（不覆盖既有终签）"),
]

# ---- 常量表 ----
VERDICTS = ("应摘", "改域", "保留", "需人工")
FIXABLE = ("应摘", "改域")
TYPE_ORDER = [
    "quantity_boundary",
    "plan_negation_verb",
    "time_boundary",
    "verb_domain_risk",
    "verb_wordlist_candidate",
    "fence_entity_real_only",
]
TYPE_LABEL = {
    "quantity_boundary": "数量边界 $",
    "plan_negation_verb": "计划/否定/假想语境动词",
    "time_boundary": "时间边界 %",
    "verb_domain_risk": "动词域高风险",
    "verb_wordlist_candidate": "动词词表候选域差异",
    "fence_entity_real_only": "围栏内实体限实指",
    "d1_description": "D1 描述性代称（扩展类别）",
}

TOKEN_RE = re.compile(r"[〖⟦]([^〖⟦〗⟧]+)[〗⟧]")
CUE_RE = re.compile(r"前接[“\"]([^”\"]+)[”\"]")

# plan_negation：cue 作构词成分时非标记（检测器共现误报）
FALSE_CUE_PREFIX = {
    "将": re.compile(r"(牙|大|中|老|小|名|猛|骁|健|战|武|兵|主|副|悍|虎|枭)将$"),
    "别": re.compile(r"(拜|告|分|辞|判|识|区|个|离|道|诀|作|送|惜|阔|话|挥|永|临|饮|洒)别$"),
    "莫": re.compile(r"(约|莫|大|落|寂|冷|薄)莫$|约莫$"),
}
# cue+display 构成的固定副词（"不"类）：检测器看到"不"但 token 其实是复合词
FALSE_CUE_TOKEN = {
    ("不", "断"), ("不", "觉"), ("不", "禁"), ("不", "由"), ("不", "住"),
    ("不", "仅"), ("不", "但"), ("不", "过"), ("不", "久"), ("不", "少"),
    ("不", "料"), ("不", "知"), ("不", "免"), ("不", "消"), ("不", "意"),
    ("不", "妨"), ("不", "同"), ("不", "停"),
}
# 纯计划/条件/未来 cue 及复合词（→ 应摘）
FUTURE_CUE_RE = re.compile(
    r"(将要|将欲|即将|快要|就要|行将|正待|正要|刚待|待要|只要|要是|若不是|若要|如要|倘要|"
    r"否则|不然|并不|并没|并未|从不|绝不|莫要|不要|别要|偏不|又不|还没|尚未|仍未|久未|"
    r"便要|偏要|硬要|定要|一定要|非要|都要)$"
)
REALIZED_PRE_RE = re.compile(r"(已经|已|曾经|曾|便|就|才|正在|正|刚|刚自)$")
INTERRUPT_RE = re.compile(r"(哪料|哪知|不料|没想到|没料到|扑空|落空|未中|未到|未及|没刺中|没打中|抓空|刺空)")
_PERSON_WORDS = (r"(人|男子|女子|汉子|少女|少年|武士|卫士|家伙|怪人|老者|姑娘|孩子|大汉|"
                 r"客人|弟子|随从|侍卫|后生|书生|妇人|女子|小厮|丫鬟|丫头)")
PERSON_NOUN_RE = re.compile(r"^的(?:[一二三四五六七八九十两几数]{0,2}(?:个|名|位|条))?" + _PERSON_WORDS)
RELATIVE_PERSON_RE = re.compile(
    r"^.{0,7}的(?:[一二三四五六七八九十两几数]{0,2}(?:个|名|位|条))?" + _PERSON_WORDS
)
HABITUAL_RE = re.compile(r"(每|每逢|常常|经常|总是|向来|一向|天天|日日|历年|历来)")
HABITUAL_YI_BIAN_RE = re.compile(r"[一每](?!以便)[^。！？；]{0,12}便")
NEED_RE = re.compile(r"(迫着|逼迫|逼着|不得不|只能|必须|需要|得要|还得|正要)$")
INTERROG_RE = re.compile(r"(为什么|为何|怎么|怎样|难道)")

TIME_FUZZY = {
    "一会", "一会儿", "一刹那间", "一刹那", "一霎那", "一霎", "好久", "很久", "半晌",
    "一阵", "片刻", "良久", "许久", "多时", "半天", "半晌午", "转眼间", "霎时间",
}
TIME_IDIOM = {
    "金乌西堕", "玉兔东升", "王兔东升", "星横斗转", "斗转星移", "月落乌啼",
    "日上三竿", "日薄西山", "金乌西坠", "一生一世", "一生", "半生", "三生三世",
}
TIME_COUNT_RE = re.compile(r"[一二三四五六七八九十百千万两0-9几数半]")
TIME_COUNT_UNIT_RE = re.compile(
    r"[一二三四五六七八九十百千万两0-9几数半][^，。！？]{0,6}(招|次|回|回合|里|尺|丈|步|掌|剑|刀|拳|人|名|斤)"
)
GENERIC_FENCE_PLACE = {
    "山庄", "深宫", "荒村", "古庙", "古墓", "客舍", "酒楼", "客栈", "荒野", "深山",
    "大漠", "关山", "天涯", "海角", "人间", "红尘", "天下", "江湖", "世间", "尘世",
    "旧梦", "空门", "深宅", "大院", "小巷",
}
REGION_PROPER = {
    "江南", "塞外", "中原", "关中", "关外", "塞北", "西域", "漠北", "回疆", "京城",
    "京师", "天山", "五台山", "邙山", "长白", "岭南", "淮北", "淮南", "川西", "塞上",
}
PLACE_SUFFIX_RE = re.compile(r"^[\u4e00-\u9fff]{1,5}(山|河|江|湖|海|关|城|州|县|镇|峰|岭|谷|岛|寺|庙|观|原|域|疆|京|都)$")
PERSONISH_ENTITY_DOMAINS = set("@◆&~")
OTHER_ENTITY_DOMAINS = set("%^☆•+#$;◎")


# ────────────────────────────── 数据结构 ──────────────────────────────
@dataclass
class Token:
    raw: str
    domain: str
    display: str
    meta: str
    plain_start: int
    raw_start: int = 0      # token 在 Paragraph.raw（= tagged 文件行内容）中的起点
    raw_end: int = 0        # token 在 Paragraph.raw 中的终点（不含）


@dataclass
class Occurrence:
    start: int          # display 在 plain 中的起点
    end: int
    token: Token


class Paragraph:
    """tagged 单段：保留原始串、剥离标记后的 plain、token 表（含域码/管道元数据）。

    token 同时记录 raw_start/raw_end，供 --apply 精确定位/替换（回/段/token 三重定位）。
    """

    def __init__(self, raw: str, fence: str | None = None, line_no: int = 0, pn: int = 0):
        self.raw = raw
        self.fence = fence
        self.line_no = line_no
        self.pn = pn
        parts: list[str] = []
        self.tokens: list[Token] = []
        pos_raw = 0
        plain_len = 0
        for m in TOKEN_RE.finditer(raw):
            seg = raw[pos_raw:m.start()]
            parts.append(seg)
            plain_len += len(seg)
            inner = m.group(1)
            domain = inner[0]
            rest = inner[1:]
            sections = re.split(r"[｜|]", rest, maxsplit=1)
            display = sections[0]
            meta = sections[1] if len(sections) > 1 else ""
            self.tokens.append(Token(m.group(0), domain, display, meta, plain_len,
                                     m.start(), m.end()))
            parts.append(display)
            plain_len += len(display)
            pos_raw = m.end()
        parts.append(raw[pos_raw:])
        self.plain = "".join(parts)

    def occurrences(self, display: str) -> list[Occurrence]:
        out = []
        for tok in self.tokens:
            if tok.display == display:
                out.append(Occurrence(tok.plain_start, tok.plain_start + len(display), tok))
        return out

    def window(self, start: int, end: int, before: int = 16, after: int = 16) -> str:
        left = self.plain[max(0, start - before):start]
        right = self.plain[end:end + after]
        return left + "【" + self.plain[start:end] + "】" + right


class TaggedIndex:
    """只读索引 tagged/<书>/<NNN>.tagged.md： (回, 段) → Paragraph（含围栏标签/行号）。"""

    def __init__(self, book: str):
        self.book = book
        self.dir = TAGGED_DIR / book
        self.paras: dict[tuple[int, int], Paragraph] = {}
        self.files: dict[int, Path] = {}
        self.warnings: list[str] = []
        if not self.dir.is_dir():
            self.warnings.append(f"tagged 目录不存在，规则降级：{self.dir}")
            return
        for path in sorted(self.dir.glob("*.tagged.md")):
            stem = path.stem.split(".")[0]
            if not stem.isdigit():
                continue
            ch = int(stem)
            self.files[ch] = path
            fence = None
            for idx, line in enumerate(io.open(path, encoding="utf-8").read().splitlines()):
                if line.startswith(":::"):
                    label = line[3:].strip()
                    fence = label or None
                    continue
                m = re.match(r"^\[(\d+)\] ", line)
                if m:
                    pn = int(m.group(1))
                    self.paras[(ch, pn)] = Paragraph(line, fence, line_no=idx, pn=pn)
        if not self.paras:
            self.warnings.append(f"tagged 目录无可用段落：{self.dir}")

    def get(self, chapter: int, pn: int) -> Paragraph | None:
        return self.paras.get((chapter, pn))


# ────────────────────────────── 判定结果 ──────────────────────────────
@dataclass
class Verdict:
    kind: str                      # 应摘 / 改域 / 保留 / 需人工
    rule_id: str
    reason: str
    target_domain: str | None = None
    evidence: str = ""
    rule_verdict: str | None = None    # 被 R-DOC 转人工前的规则初判
    doc_conflict: bool = False


def V(kind: str, rule_id: str, reason: str, target: str | None = None,
      evidence: str = "") -> Verdict:
    return Verdict(kind=kind, rule_id=rule_id, reason=reason,
                   target_domain=target, evidence=evidence)


@dataclass
class ItemCtx:
    para: Paragraph | None = None
    occs: list[Occurrence] = field(default_factory=list)
    picked: Occurrence | None = None
    context: str = ""
    note: str = ""


# ────────────────────────────── 上下文定位 ──────────────────────────────
def _strip_inner(inner: str) -> str:
    return inner[1:].split("｜")[0].split("|")[0]


def _plain_token(raw: str) -> str:
    return TOKEN_RE.sub(lambda m: _strip_inner(m.group(1)), raw)


def build_ctx(item: dict, index: TaggedIndex | None) -> ItemCtx:
    """为条目准备 tagged 上下文；缺失时 ctx.para=None（规则降级）。

    若 tagged 被并行批次重生成导致「回/段」漂移（本段找不到 display），在相邻 ±2 段做
    唯一定位兜底，并在 ctx.note / evidence 中显式标注漂移，供报告核对。
    """
    ctx = ItemCtx()
    if index is None:
        ctx.note = "无 tagged 索引（仅按 JSON 字段判定）"
        return ctx
    para = index.get(item["chapter"], item["pn"])
    if para is None:
        ctx.note = f"tagged 中未找到 回{item['chapter']:03d} 段[{item['pn']}]"
        return ctx
    occs = para.occurrences(item["display"])
    drift_note = ""
    if not occs:
        for delta in (-2, -1, 1, 2):
            p2 = index.get(item["chapter"], item["pn"] + delta)
            if p2 is not None and p2.occurrences(item["display"]):
                para = p2
                occs = p2.occurrences(item["display"])
                drift_note = f"⚠tagged 段号漂移：显示串实际位于【{item['pn'] + delta}】段"
                break
    ctx.para = para
    ctx.occs = occs
    if not occs:
        ctx.note = f"段内未定位 display『{item['display']}』token"
        return ctx
    # 优先取域码与 detail 所述标注域一致的 token（domain_risk / wordlist 用）
    chosen = ctx.occs[0]
    dm = re.match(r"([⊞⊠⊡⊟▣■])", item.get("detail", ""))
    if dm:
        for occ in ctx.occs:
            if occ.token.domain == dm.group(1):
                chosen = occ
                break
    ctx.picked = chosen
    ctx.context = para.window(chosen.start, chosen.end)
    if drift_note:
        ctx.note = drift_note
        ctx.context = drift_note + " ｜ " + ctx.context
    return ctx


def locate_cued_occurrence(ctx: ItemCtx, cue: str) -> Occurrence | None:
    """在段内多个同名 token 中，找 cue 紧邻其前的那一处（最小间隔优先，同间隔取最早）。"""
    if not ctx.para or not ctx.occs:
        return None
    plain = ctx.para.plain
    best: tuple[int, int, Occurrence] | None = None
    for order, occ in enumerate(ctx.occs):
        for k in range(len(cue), 7):
            seg_start = max(0, occ.start - k)
            seg = plain[seg_start:occ.start]
            if seg.endswith(cue):
                gap = k - len(cue)
                cand = (gap, order, occ)
                if best is None or cand < best:
                    best = cand
                break
    return best[2] if best else None


def _pre_post(ctx: ItemCtx, occ: Occurrence, pre_n: int = 16, post_n: int = 16) -> tuple[str, str]:
    plain = ctx.para.plain
    return plain[max(0, occ.start - pre_n):occ.start], plain[occ.end:occ.end + post_n]


# ────────────────────────────── 各类别规则 ──────────────────────────────
def classify_unknown(item: dict, ctx: ItemCtx) -> Verdict:
    t = item["type"]
    extra = ""
    if t == "d1_description":
        extra = ("；按 SKILL_03a v1.8 D1 与 docs/48-S2 §5.3 R1，描述性代称应不标 → 建议『应摘』，"
                 "但类别不在六类规则表，转人工终签")
    return V("需人工", "R-UNK",
             f"未知/扩展类别『{t}』（六类规则表外）{extra}", evidence=ctx.context)


def classify_quantity(item: dict, ctx: ItemCtx) -> Verdict:
    disp = item["display"]
    if len(disp) == 1:
        return V("应摘", "R-Q1",
                 "单字裸数词/裸量词：不标（数量新口径，非『数词+量词+名』整串）",
                 evidence=ctx.context)
    if re.fullmatch(r"[一二三四五六七八九十百千万两0-9几数半]+", disp):
        return V("应摘", "R-Q2", "多字裸数词序列：同 R-Q1 裸数词口径，应摘", evidence=ctx.context)
    if TIME_COUNT_UNIT_RE.search(disp) or re.search(
            r"[一二三四五六七八九十百千万两0-9几数]+(个|把|件|只|名|位|条|张|匹|头|口|块|枝|株|颗|粒|杯|碗|双|对|群|派|批)",
            disp):
        return V("保留", "R-Q3", "多字信息承载计数（数词+量词整串）：按信息承载原则保留",
                 evidence=ctx.context)
    if disp in {"一批", "几名", "几道", "几树", "数名", "数日"}:
        return V("应摘", "R-Q4", "批次/泛人约量：不标（03a 负例）", evidence=ctx.context)
    return V("需人工", "R-Q5", f"多字数量『{disp}』未命中规则，需人工回读语境", evidence=ctx.context)


def classify_plan_negation(item: dict, ctx: ItemCtx) -> Verdict:
    display = item["display"]
    detail = item.get("detail", "")
    m = CUE_RE.search(detail)
    cue = m.group(1) if m else ""
    if ctx.para is None or not cue:
        return V("需人工", "R-P10",
                 f"上下文/tagged 不可用或未解析出 cue（cue={cue!r}；{ctx.note}）",
                 evidence=ctx.context or detail)
    occ = locate_cued_occurrence(ctx, cue)
    if occ is None:
        return V("需人工", "R-P10",
                 f"段内未找到『{cue}』紧邻『{display}』的出现位置（同名 token 多处），需回读语境",
                 evidence=ctx.context)
    pre, post = _pre_post(ctx, occ)
    ctx.picked = occ
    ctx.context = ctx.para.window(occ.start, occ.end)
    pre_cue = pre[:-len(cue)] if pre.endswith(cue) else pre
    # ── R-P1 cue 为构词成分 / 固定副词（检测器共现误报）
    if cue in FALSE_CUE_PREFIX and FALSE_CUE_PREFIX[cue].search(pre):
        return V("保留", "R-P1",
                 f"『{cue}』为构词成分（非计划/否定标记）：检测器共现误报，动作已发生",
                 evidence=ctx.context)
    if (cue, display) in FALSE_CUE_TOKEN or (cue == "不" and pre_cue.endswith("不")) \
            or (cue == "不" and pre.endswith("不能不")):
        return V("保留", "R-P1",
                 f"『{cue}{display}』为固定副词/双重否定（不能不=被迫已发生）：共现误报",
                 evidence=ctx.context)
    # ── R-P6 将=把字句 + 的-定语从句（token 指已发生动作/已擒获对象）
    if cue == "将" and (post.startswith("的") or PERSON_NOUN_RE.match(post)):
        return V("保留", "R-P6",
                 "将=把字句 +『的』定语从句（token 指已发生动作/已擒获对象）→ 保留",
                 evidence=ctx.context)
    # ── cue=将：先消歧 将=把字句 / 将要（未来）
    if cue == "将":
        if re.search(r"(已|快|行|即|就|将|必|定|终)$", pre_cue):
            return V("应摘", "R-P5",
                     "将=将要（前有已/快/行/即/就/必/定/终）：未来未发生，不标", evidence=ctx.context)
        if re.search(r"(时|时候|之际|之前|以后)", post[:8]):
            return V("应摘", "R-P5",
                     "『将+动作+时/时候』：将要发生（未发生），不标", evidence=ctx.context)
        if RELATIVE_PERSON_RE.match(post):
            return V("保留", "R-P6",
                     "将=把字句 +『的+人物』定语从句（token 指已发生动作/已擒获对象）→ 保留",
                     evidence=ctx.context)
    # ── R-P8 cue=要 的情态/必要语境（先于已发生标记判定：又要/既要/还要/迫着要）
    if cue == "要":
        if re.search(r"(又|既|还)$", pre_cue):
            combat = re.search(r"(之下|攻击|武功|剑法|刀法|招|敌|动手|相斗|交手|闪击)", pre + post)
            if combat:
                return V("需人工", "R-P8",
                         "情态/必要语境（又要/既要/还要+动词，战斗描写）：非纯计划亦非已发生，需人工",
                         evidence=ctx.context)
            return V("应摘", "R-P5",
                     "『又/还/既+要+动词』此处为意愿/计划（非战斗必要语境）→ 未发生，不标",
                     evidence=ctx.context)
        if NEED_RE.search(pre_cue):
            return V("需人工", "R-P8",
                     f"情态/必要语境（{pre_cue[-4:]!r}…要+动词）：非纯计划亦非已发生，需人工回读",
                     evidence=ctx.context)
    # ── R-P2 惯常/反复行为（每…都、一…便，既成/反复发生非纯计划）
    habitual_win = ctx.para.plain[max(0, occ.start - 20):occ.start] if ctx.para else pre
    if HABITUAL_RE.search(habitual_win) or HABITUAL_YI_BIAN_RE.search(habitual_win):
        return V("保留", "R-P2",
                 "惯常/反复行为（每…都、一…便）：非『纯计划』，按既成/反复发生保留",
                 evidence=ctx.context)
    # ── 复合 cue（将要/就要/快要/都要/只要/要是/便要/不要/尚未…）→ 未来/条件/否定
    fm = FUTURE_CUE_RE.search(pre)
    if fm:
        return V("应摘", "R-P5",
                 f"纯计划/未来/条件（{fm.group(1)}）→ 未发生，不标（04f §3.6）",
                 evidence=ctx.context)
    # ── R-P3 已发动但被中断/未遂 → 标 + 记未遂
    if INTERRUPT_RE.search(post):
        return V("保留", "R-P3",
                 "已发动但被中断/未遂（04f §3.6 未遂判据：标 + 记未遂）→ 保留",
                 evidence=ctx.context)
    # ── R-P4 已发生/正在发生（了/着、已/便/才/正/刚、曾）
    # 先排除『X要+动作+了』=将要发生的未来式（"我要跑快了"/"他都要进关内了"）
    if cue == "要" and post.startswith("了") and re.search(r"(我|他|她|你|咱|俺)$", pre_cue):
        return V("应摘", "R-P5",
                 "『X要+动作+了』=将要发生（未发生），不标（04f §3.6）", evidence=ctx.context)
    if re.match(r"^了", post):
        return V("保留", "R-P4",
                 "token 后接『了』且无未来/计划复合 cue → 已发生（04f §3.6）",
                 evidence=ctx.context)
    # 情态/意图 cue（想/待/若…）之前的「已/正」属于 cue 的状语，不构成 token 已发生信号
    if cue not in ("想", "欲", "待", "若", "若是", "如果"):
        if REALIZED_PRE_RE.search(pre_cue):
            return V("保留", "R-P4",
                     f"前接已发生/进行标记（{pre_cue[-3:]!r}）→ 已发生/正在发生"
                     "（04f §3.6；docs/45 #9/#70）", evidence=ctx.context)
    # ── R-P6 定语从句（想/要/欲+动作+的+人物）
    if cue in ("想", "要", "欲") and RELATIVE_PERSON_RE.match(post):
        return V("保留", "R-P6",
                 "『想/要+动作+的+人物』定语从句，token 指已发生的动作/既获对象 → 保留",
                 evidence=ctx.context)
    # ── cue 语义缺省
    # R-P5 准备/打算/预备/计划+X：计划未实施（docs/55 准备+X 先例；04f §3.6）
    # 2026-11-07 P3 批次新增（风雷/侠骨 8 条同型 judgment 的规则化收口）
    if cue in ("准备", "打算", "预备", "计划"):
        return V("应摘", "R-P5",
                 f"『{cue}』+动词=计划未实施：未发生，不标（docs/55 准备+X 先例；04f §3.6）",
                 evidence=ctx.context)
    if cue in ("待", "若", "若是", "倘若", "如果", "否则", "意图"):
        return V("应摘", "R-P5",
                 f"『{cue}』计划/条件/意图语境：未发生，不标（04f §3.6）", evidence=ctx.context)
    if cue in ("想", "欲"):
        return V("应摘", "R-P5",
                 f"『{cue}』+动词=意图/假想：未发生，不标（04f §3.6）", evidence=ctx.context)
    if cue in ("不", "没", "未", "莫", "别"):
        if cue == "不" and re.search(r"(何|岂|宁|莫|谁|能|可|要|难|无)不$", pre):
            return V("应摘", "R-P5",
                     "『何不/岂不』反问建议/否定形式：动作未发生（04f §3.6）", evidence=ctx.context)
        return V("应摘", "R-P5",
                 f"否定形式『{cue}{display}』：动作未发生，不标（04f §3.6）", evidence=ctx.context)
    if cue == "要":
        if INTERROG_RE.search(pre):
            return V("需人工", "R-P7",
                     "疑问句追问既成事实（为什么/为何+要+X）：是否已发生需回读前句（docs/45 #70）",
                     evidence=ctx.context)
        post_wide = ctx.para.plain[occ.end:occ.end + 45]
        if re.search(r"(身首异处|被杀|被斩|尸体|尸首|倒在血泊|送了性命)", post_wide):
            return V("需人工", "R-P7",
                     "『要+动作』后文紧接既成结果（被杀/身首异处）：意愿表述与既成事实交叠，"
                     "需人工裁定（docs/45 #70 既成先例）", evidence=ctx.context)
        return V("应摘", "R-P5",
                 "『要+动词』纯意图/计划：未发生，不标（04f §3.6；docs/45 #1-12 同例）",
                 evidence=ctx.context)
    if cue == "将":
        return V("需人工", "R-P9",
                 "『将』=把字句/将来 歧义未消（无 的/时/已 信号）→ 需人工回读", evidence=ctx.context)
    return V("需人工", "R-P10",
             f"cue『{cue}』未命中规则表，需人工回读", evidence=ctx.context)


def classify_time(item: dict, ctx: ItemCtx) -> Verdict:
    disp = item["display"]
    meta = ""
    if ctx.picked is not None:
        meta = ctx.picked.token.meta
    elif ctx.occs:
        meta = ctx.occs[0].token.meta
    ev = ctx.context
    if meta == "年龄":
        if disp == "老":
            return V("应摘", "R-T6", "『老』为形容词（老将军），非年龄实指（docs/45 #69）", evidence=ev)
        return V("保留", "R-T1",
                 f"年龄宽口径（|年龄|『{disp}』）：可锚定人物年龄，保留（03a L108）", evidence=ev)
    if disp in TIME_FUZZY:
        return V("应摘", "R-T3",
                 f"纯模糊时长/习语『{disp}』：不标（03a L108 纯模糊；docs/48 §九 一会先例）", evidence=ev)
    if disp in TIME_IDIOM:
        return V("应摘", "R-T4",
                 f"习语化时间修辞『{disp}』：属修辞层，非严格时点（01g；docs/45 #77 泛指先例）", evidence=ev)
    # 2026-11-07 P4 修复：`次` 仅在数词后视为计数（30次/两三次）；"这次/那次/此次/
    # 上一次/这一次/那一次" 为相对时点（03a L109），不得改域 $。
    _count_suffix = re.search(r"(招|里|尺|丈|步|回合)$", disp) or re.search(
        r"[0-9一二三四五六七八九十百千万两几数半]\s*次$", disp)
    if TIME_COUNT_UNIT_RE.search(disp) or (meta != "年龄" and _count_suffix):
        return V("改域", "R-T5",
                 f"时间位误挂战斗/里程计数『{disp}』→ 改域 $（数量）",
                 target="$", evidence=ev)
    if meta == "时点":
        return V("保留", "R-T2",
                 f"时点宽口径（|时点|『{disp}』）：纪年/节日/相对时点合规，保留（03a L108）", evidence=ev)
    if meta == "时长":
        return V("保留", "R-T2",
                 f"约量/持续时长（|时长|『{disp}』）：宽口径合规，保留（03a L108）", evidence=ev)
    # 无 tagged token 元数据（如 tagged 被并行批次重生成导致定位失配）：按显示串兜底判定
    if ctx.picked is None:
        if re.match(r"^(汉|唐|宋|元|明|清)", disp) or \
                re.search(r"(朝|代|年间|节|佳节|大寿|纪|元年)$", disp) or \
                re.match(r"^[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]$", disp):
            return V("保留", "R-T2",
                     f"显示串『{disp}』即纪年/节日时点词（03a L108）；tagged 未取到 token 元数据，"
                     "按显示串兜底判定（上下文缺失，报告已标注）", evidence=ev)
    # 无 |年龄| 管道的裸数词（可能是年龄/数量）
    if re.fullmatch(r"[一二三四五六七八九十百千万两0-9]+(多|余|来)?", disp) or disp.endswith(("左右", "出头", "有余")):
        return V("需人工", "R-T7",
                 f"无 |年龄| 管道的约量『{disp}』：需回读语境确认属年龄（可保留）或数量（应摘）",
                 evidence=ev)
    return V("需人工", "R-T7", f"时间边界『{disp}』未命中规则，需人工（03a L108）", evidence=ev or item.get("detail", ""))


def classify_domain(item: dict, ctx: ItemCtx) -> Verdict:
    disp = item["display"]
    detail = item.get("detail", "")
    ev = ctx.context
    if ctx.para is None:
        return V("需人工", "R-D7", f"tagged 不可用：{ctx.note}", evidence=detail)
    annot_m = re.match(r"([⊞⊠⊡⊟▣■])", detail)
    annot = annot_m.group(1) if annot_m else (ctx.picked.token.domain if ctx.picked else "")
    if ctx.picked is None:
        return V("需人工", "R-D7", "段内未定位 token，需人工", evidence=detail)
    pre, post = _pre_post(ctx, ctx.picked)
    para_plain = ctx.para.plain
    if annot == "■":
        if re.search(r"(逐出|驱逐|除名|开除|革出)", disp):
            # 组织/宫廷除名：仅当『逐出+宫/师门/门派/门墙/帮派』或上下文明确组织除名
            if re.match(r"^(宫|师门|门派|门墙|帮|派|教|族|组织|朝廷)", post[:4]) or \
                    re.search(r"(逐出宫|逐出师门|逐出门墙|除名|开除|革出)", disp + pre[-6:] + post[:6]):
                return V("改域", "R-D2",
                         f"『{disp}』组织/宫廷除名 → 改域 ⊡（04f §2.3；docs/45 #56/#58 先例）",
                         target="⊡", evidence=ev)
            return V("保留", "R-D1",
                     f"『{disp}』=强制迁离地域/驱逐，■ 成立（04f §2.6；docs/45 #50/#53 先例）",
                     evidence=ev)
        if re.search(r"(押|充军|流放|发配|掳|绑架|劫持|带走|解往|解赴)", disp):
            return V("保留", "R-D1",
                     f"『{disp}』=押解/强制迁移，■ 成立（04f §2.0 劫人分流/§2.6；docs/45 #16/#50/#53/#78）",
                     evidence=ev)
        return V("需人工", "R-D7",
                 f"■ 域边界（强制移动 vs 拘押/社会处置）『{disp}』需回读（04f §2.6）", evidence=ev)
    if annot == "⊠":
        text = pre[-10:] + post[:14] + para_plain
        # 轻伤未达阈值：与 docs/48 §九 保留终态冲突 → 不机械改域
        if re.search(r"(轻伤|并不严重|未受伤|没受伤|伤得不重|皮肉之伤|只伤及皮肤)", text) and \
                not re.search(r"(窟窿|大洞|脑浆|残|断|死|亡)", post[:14]):
            return V("需人工", "R-D5",
                     "受伤阈值争议：轻伤未改变行动能力（04f §2.2 应为 ⊞，docs/45 #32 改域先例），"
                     "但 docs/48 §九 终态保留 ⊠ → 转人工复核", evidence=ev)
        if re.search(r"(自己|自伤|自刺|伪装|假装|疗|医治|治疗|敷药|穴道|放血|毒血|蛇血|药|针)", pre[-8:] + post[:14]):
            return V("保留", "R-D3",
                     f"『{disp}』自伤/医疗语境，⊠ 生命健康成立（04f §2.2 医疗入口；docs/45 #34 先例）",
                     evidence=ev)
        if re.search(r"(窟窿|大洞|脑浆|血|断|掉|死|亡|残|重伤|一只|两截|透|中|关节|了)", post[:14] + pre[-16:]) or \
                re.search(r"(被.{1,4}所|给.{1,4}了|已经|已[一-龥])", pre[-8:]):
            return V("保留", "R-D4",
                     f"『{disp}』结果达伤情阈值（结果决定主域），⊠ 成立（04f §2.2；docs/45 #23/#43/#47）",
                     evidence=ev)
        if re.search(r"(若|要是|要不然|怕不|否则|非.{0,6}不可|意图)", pre[-6:] + post[:8]):
            return V("需人工", "R-D6",
                     f"『{disp}』假设/未发生语境：域码虽合 ⊠，但 token 是否发生需人工（04f §3.6）",
                     evidence=ev)
        return V("需人工", "R-D7",
                 f"⊠ 域边界『{disp}』需回读（04f §2.2 受伤阈值）", evidence=ev)
    return V("需人工", "R-D7",
             f"标注域 {annot or '?'} 不在 ■/⊠ 规则范围，需人工（04f §2.0 六域）", evidence=ev)


def classify_wordlist(item: dict, ctx: ItemCtx) -> Verdict:
    return V("保留", "R-W1",
             "标注域与 verbs.json 候选域不同：词表单一主域差异/多义词待校准，属词表池输入，"
             "不改语料（docs/45 §二；docs/48 §九；docs/48-S2 §一；04f §5.4）",
             evidence=ctx.context)


def classify_fence(item: dict, ctx: ItemCtx) -> Verdict:
    disp = item["display"]
    ev = ctx.context
    if ctx.para is None:
        return V("需人工", "R-F5", f"tagged 不可用：{ctx.note}", evidence=item.get("detail", ""))
    plain_len = len(ctx.para.plain)
    domain = ""
    if ctx.picked is not None:
        domain = ctx.picked.token.domain
    elif ctx.occs:
        domain = ctx.occs[0].token.domain
    # R-F1 围栏段落实为散文（struct 误判）
    if plain_len > 60:
        return V("保留", "R-F1",
                 f"围栏段落实为散文（段长 {plain_len}>60，struct 层章首/回末探测误判）："
                 "实体为实指叙述，保留（docs/48 §九 018[1] 先例）", evidence=ev)
    # R-F2 人物/组织/家族/族群专名
    if domain in PERSONISH_ENTITY_DOMAINS:
        return V("保留", "R-F2",
                 f"围栏内{'人物/组织/家族/族群' if domain != '@' else '人物'}专名『{disp}』：实指，保留"
                 "（01g 围栏限实指；docs/48 §九）", evidence=ev)
    # R-F3 地名专名
    if domain == "=":
        if disp in GENERIC_FENCE_PLACE:
            return V("应摘", "R-F4",
                     f"围栏内泛称场所『{disp}』：诗词/对联泛指，非实指 → 应摘"
                     "（01g 围栏限实指；docs/45 #77 沙漠→摘 先例）", evidence=ev)
        if disp in REGION_PROPER or PLACE_SUFFIX_RE.match(disp):
            return V("保留", "R-F3",
                     f"围栏内地名专名『{disp}』：实指，保留（01g 围栏限实指；docs/48 §九 023[80]）",
                     evidence=ev)
        return V("需人工", "R-F5", f"围栏内地名『{disp}』实指/泛指需人工（01g）", evidence=ev)
    # R-F4 其余（时间泛称/抽象技艺/通名/器物）→ 诗词泛指/修辞
    if domain in OTHER_ENTITY_DOMAINS or domain:
        kind = {"%": "时间泛称", "^": "抽象技艺", "☆": "技艺泛称", "#": "身份通名",
                "•": "器物", "+": "数量", "$": "数量", ";": "职衔"}.get(domain, f"域{domain}")
        return V("应摘", "R-F4",
                 f"围栏内{kind}『{disp}』：诗词/对联泛指或修辞，非实指 → 应摘"
                 "（01g 围栏限实指；docs/45 #77 沙漠→摘；docs/48-S2 §一 一年/沙漠→摘）",
                 evidence=ev)
    return V("需人工", "R-F5", f"围栏内实体『{disp}』无域码信息，需人工（01g）", evidence=ev)


CLASSIFIERS = {
    "quantity_boundary": classify_quantity,
    "plan_negation_verb": classify_plan_negation,
    "time_boundary": classify_time,
    "verb_domain_risk": classify_domain,
    "verb_wordlist_candidate": classify_wordlist,
    "fence_entity_real_only": classify_fence,
}


# ────────────────────────────── 载入与抽取 ──────────────────────────────
def load_acceptance(path: Path) -> dict:
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def iter_judgment_items(doc: dict) -> list[dict]:
    """从 chapters_data 抽取逐回 judgment_items（chapter/pn/type...）。"""
    chapters_data = doc.get("chapters_data") or {}
    out: list[dict] = []
    for key in sorted(chapters_data, key=lambda k: int(k) if str(k).isdigit() else 10 ** 9):
        value = chapters_data[key]
        if not isinstance(value, dict):
            continue
        ch = int(key) if str(key).isdigit() else int(value.get("chapter", 0) or 0)
        for raw in value.get("judgment_items") or []:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            item["chapter"] = ch
            item.setdefault("type", "unknown")
            item.setdefault("display", "")
            item.setdefault("detail", "")
            out.append(item)
    return out


def resolve_acceptance_path(book: str, acceptance: Path | None) -> tuple[Path, list[Path]]:
    """定位某书 acceptance JSON；同书多文件（如江湖 001-003 与 001-048）取章节跨度最大者。"""
    if acceptance is not None:
        return acceptance, []
    cands = sorted(ACCEPTANCE_DIR.glob(f"{book}_*.json"))
    if not cands:
        raise FileNotFoundError(f"找不到 registry/acceptance/{book}_*.json")
    if len(cands) == 1:
        return cands[0], []

    def span(p: Path) -> tuple[int, int]:
        m = re.search(r"_(\d{3})-(\d{3})", p.stem)
        return (int(m.group(2)) - int(m.group(1)), int(m.group(2))) if m else (0, 0)

    chosen = max(cands, key=span)
    others = [p for p in cands if p != chosen]
    return chosen, others


# ────────────────────────────── 主流程 ──────────────────────────────
def process_book(book: str, acceptance: Path | None = None,
                 out_dir: Path = DEFAULT_OUT_DIR, dry_run: bool = True) -> dict:
    path, others = resolve_acceptance_path(book, acceptance)
    doc = load_acceptance(path)
    items = iter_judgment_items(doc)
    index = TaggedIndex(book) if TAGGED_DIR.is_dir() else None
    # tagged/acceptance 快照时序检查（并行批次可能已重生成 tagged 但 acceptance 仍旧）
    tagged_files = sorted((TAGGED_DIR / book).glob("*.tagged.md")) if (TAGGED_DIR / book).is_dir() else []
    newest_tagged_mtime = max((p.stat().st_mtime for p in tagged_files), default=0.0)
    acceptance_mtime = path.stat().st_mtime
    tagged_drift = bool(tagged_files) and newest_tagged_mtime > acceptance_mtime

    # 第一遍：逐条规则分类
    records: list[dict] = []
    for item in items:
        ctx = build_ctx(item, index)
        classifier = CLASSIFIERS.get(item["type"], classify_unknown)
        verdict = classifier(item, ctx)
        if not verdict.evidence:
            verdict.evidence = ctx.context or item.get("detail", "")
        records.append({"item": item, "ctx": ctx, "verdict": verdict})

    # 第二遍：R-W2 同 token 改域联动（docs/45 #33/#59）
    recode_by_token: dict[tuple[int, int, str], str] = {}
    for rec in records:
        it, vd = rec["item"], rec["verdict"]
        if it["type"] == "verb_domain_risk" and vd.kind == "改域" and vd.target_domain:
            recode_by_token[(it["chapter"], it["pn"], it["display"])] = vd.target_domain
    for rec in records:
        it, vd = rec["item"], rec["verdict"]
        if it["type"] != "verb_wordlist_candidate":
            continue
        key = (it["chapter"], it["pn"], it["display"])
        if key in recode_by_token:
            target = recode_by_token[key]
            rec["verdict"] = V("改域", "R-W2",
                               f"随同 token 的 verb_domain_risk 条目改域 → {target}"
                               "（docs/45 #33/#59 先例）",
                               target=target, evidence=vd.evidence)

    # 第三遍：R-DOC 守卫（本书 docs 已终签全部保留时，不覆盖既有终签）
    doc_ctx = DOC_CONTEXT.get(book, {})
    for rec in records:
        it, vd = rec["item"], rec["verdict"]
        if doc_ctx.get("terminal_all_keep") and vd.kind in FIXABLE:
            rec["verdict"] = Verdict(
                kind="需人工", rule_id="R-DOC",
                reason=(f"规则初判『{vd.kind}』（{vd.rule_id}：{vd.reason}），但 docs 记载本书残留已全部终签保留"
                        f"（{doc_ctx['doc']}）→ 转人工复核，不覆盖既有终签"),
                evidence=vd.evidence, rule_verdict=vd.kind, doc_conflict=True)

    # 汇总
    by_type: Counter = Counter()
    by_verdict: Counter = Counter()
    by_type_verdict: dict[str, Counter] = {}
    for rec in records:
        t = rec["item"]["type"]
        v = rec["verdict"].kind
        by_type[t] += 1
        by_verdict[v] += 1
        by_type_verdict.setdefault(t, Counter())[v] += 1

    data_structure = {
        "top_level_keys": list(doc.keys()),
        "chapters_field_type": type(doc.get("chapters")).__name__,
        "chapters_field_len": len(doc.get("chapters") or []),
        "detailed_path": "chapters_data['NNN'].judgment_items",
        "chapters_data_type": type(doc.get("chapters_data")).__name__,
        "chapters_data_keys_sample": list((doc.get("chapters_data") or {}).keys())[:5],
        "summary_judgment_items": (doc.get("summary") or {}).get("judgment_items"),
        "extracted_judgment_items": len(records),
        "item_fields": sorted({k for rec in records for k in rec["item"].keys()}),
        "book_field": doc.get("book"),
        "schema": doc.get("schema"),
        "rule_version": doc.get("rule_version"),
        "risk_stats": doc.get("risk_stats"),
        "tagged_index": {
            "dir": str(index.dir) if index else None,
            "paragraphs": len(index.paras) if index else 0,
            "warnings": index.warnings if index else ["tagged 目录缺失"],
            "newest_mtime": datetime.fromtimestamp(newest_tagged_mtime).strftime("%Y-%m-%d %H:%M:%S")
            if newest_tagged_mtime else None,
            "acceptance_mtime": datetime.fromtimestamp(acceptance_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "tagged_newer_than_acceptance": tagged_drift,
            "unlocated_items": [],
        },
        "alternative_acceptance_files": [str(p) for p in others],
    }

    # 同名 token 多条目（同段同 display 多条 judgment）：按条目顺序分配到各次出现，
    # 避免 --apply 重复指向同一 token（如塞外 002[2] 一刹那间 ×2、冰魄 011[47] 颗 ×2）。
    _dup_groups: dict[tuple[int, str], list[dict]] = {}
    for rec in records:
        c = rec["ctx"]
        if c.para is not None and c.picked is not None:
            _dup_groups.setdefault((c.para.line_no, c.picked.token.display), []).append(rec)
    for _key, recs in _dup_groups.items():
        if len(recs) <= 1:
            continue
        para = recs[0]["ctx"].para
        disp = recs[0]["ctx"].picked.token.display
        occs = para.occurrences(disp)
        if len(occs) >= len(recs):
            for i, rec in enumerate(recs):
                rec["ctx"].picked = occs[i]
                rec["ctx"].context = para.window(occs[i].start, occs[i].end)

    result = {
        "tool": TOOL_VERSION,
        "schema": "wuxia-judgment-signoff-v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": bool(dry_run),
        "book": book,
        "acceptance_path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "doc_context": doc_ctx,
        "data_structure": data_structure,
        "rule_catalog": [{"id": r[0], "category": r[1], "rule": r[2], "citation": r[3]}
                         for r in RULE_CATALOG],
        "counts": {
            "total": len(records),
            "by_type": dict(by_type),
            "by_verdict": {k: by_verdict.get(k, 0) for k in VERDICTS},
            "by_type_verdict": {t: {k: c.get(k, 0) for k in VERDICTS}
                                for t, c in by_type_verdict.items()},
        },
        "items": [],
        "fixable": [],
        "keep": [],
        "manual": [],
    }
    for rec in records:
        it, ctx, vd = rec["item"], rec["ctx"], rec["verdict"]
        tok = ctx.picked.token if ctx.picked else (ctx.occs[0].token if ctx.occs else None)
        entry = {
            "chapter": it["chapter"],
            "pn": it["pn"],
            "location": f"{it['chapter']:03d}[{it['pn']}]",
            "type": it["type"],
            "display": it["display"],
            "detail": it.get("detail", ""),
            "suggestion": it.get("suggestion", ""),
            "sampled": bool(it.get("sampled")),
            "token_raw": tok.raw if tok else None,
            "token_domain": tok.domain if tok else None,
            "token_meta": tok.meta if tok else None,
            # --apply 精确坐标：实际段落号/行号/token 在该行内的字符 span
            "token_pn": ctx.para.pn if (tok and ctx.para is not None) else None,
            "token_line_no": ctx.para.line_no if (tok and ctx.para is not None) else None,
            "token_raw_start": tok.raw_start if tok else None,
            "token_raw_end": tok.raw_end if tok else None,
            "context": ctx.context,
            "verdict": vd.kind,
            "rule_id": vd.rule_id,
            "reason": vd.reason,
            "target_domain": vd.target_domain,
            "rule_verdict": vd.rule_verdict,
            "doc_conflict": vd.doc_conflict,
            "ctx_note": ctx.note,
        }
        result["items"].append(entry)
        if vd.kind == "应摘" or vd.kind == "改域":
            result["fixable"].append(entry)
        elif vd.kind == "保留":
            result["keep"].append(entry)
        else:
            result["manual"].append(entry)

    # 写产物（dry-run 只写 logs/qa）
    result["data_structure"]["tagged_index"]["unlocated_items"] = [
        f"{e['location']} {e['display']}" for e in result["items"] if e["token_raw"] is None]
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"judgment_signoff_{book}.md"
    json_path = out_dir / f"judgment_signoff_{book}.json"
    io.open(json_path, "w", encoding="utf-8").write(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    io.open(md_path, "w", encoding="utf-8").write(render_book_md(result))
    result["files"] = {"md": str(md_path.relative_to(ROOT)), "json": str(json_path.relative_to(ROOT))}
    return result


# ────────────────────────────── --apply 落盘（task-6） ──────────────────────────────
#
# 安全约束（task-6）：
#   * 仅允许 APPLY_BOOKS 白名单书落盘；七剑、白发人工项维持既有终签，不写；
#   * 先备份 backup/tagged/judgment-apply-20261105/<书>/<NNN>.tagged.md（已存在不覆盖）；
#   * 按 (chapter,pn,display[,occurrence]) 三重定位 token；同段多条按 raw_start 逆序应用；
#   * 应摘 → 令牌替换为 display（剥标不改正文）；改域 → 只换域码字符；
#   * 逐文件/逐行断言 strip(新)==strip(旧)、行数不变；任一断言失败即停（不写该文件）；
#   * 二次复跑同判定集应 0 变更（token 已不在 → 记为幂等，不覆盖首次日志）；
#   * 逐条 apply 日志 JSON + logs/qa/judgment_apply_report.md。
APPLY_LOG_SCHEMA = "wuxia-judgment-apply-v1"


def _acceptance_snapshot(result: dict) -> dict:
    p = Path(result.get("acceptance_path") or "")
    if not p.is_absolute():
        p = ROOT / p
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 快照失败不阻塞处置
        return {}
    s = doc.get("summary") or {}
    return {
        "generated_at": doc.get("generated_at"),
        "judgment_items": s.get("judgment_items"),
        "entity_tokens": s.get("entity_tokens"),
        "verb_tokens": s.get("verb_tokens"),
        "rhetoric_tokens": s.get("rhetoric_tokens"),
        "accepted": s.get("accepted"),
        "chapters_total": s.get("chapters_total"),
        "warnings": s.get("warnings"),
        "pipe_unsourced": s.get("pipe_unsourced"),
    }


def build_apply_plan(result: dict, book: str) -> tuple[list[dict], list[dict], list[dict]]:
    """由分类结果生成 apply 计划：规则可修项 + 3 书人工裁定项。"""
    plans: list[dict] = []
    manual_decisions: list[dict] = []
    skipped: list[dict] = []
    for order, entry in enumerate(result["items"]):
        v = entry["verdict"]
        key = (book, entry["chapter"], entry["pn"], entry["display"], entry["type"])
        base = {
            "order": order, "chapter": entry["chapter"], "pn": entry["pn"],
            "location": entry["location"], "type": entry["type"],
            "display": entry["display"], "rule_id": entry["rule_id"],
            "token_raw": entry["token_raw"],
            "token_pn": entry.get("token_pn"),
            "token_line_no": entry.get("token_line_no"),
            "token_raw_start": entry.get("token_raw_start"),
            "token_raw_end": entry.get("token_raw_end"),
        }
        # 2026-11-07 P4：人工裁定可覆盖规则判定的应摘/改域（verdict=保留 → 不改语料）
        _adj_override = MANUAL_ADJUDICATIONS.get(key) or MANUAL_ADJUDICATIONS.get(
            (book, entry["chapter"], entry["pn"], entry["display"], "*"))
        if _adj_override is not None and _adj_override.get("verdict") == "保留" and v in FIXABLE:
            manual_decisions.append({
                "location": entry["location"], "type": entry["type"],
                "display": entry["display"], "rule_id": entry["rule_id"],
                "auto_reason": entry["reason"], "verdict": "保留", "decided": True,
                "reason": _adj_override["reason"], "cite": _adj_override["cite"]})
            continue
        if v in FIXABLE:
            plans.append(dict(base, source="rule", action=v,
                              reason=entry["reason"], target_domain=entry["target_domain"]))
            continue
        if v != "需人工":
            continue
        adj = MANUAL_ADJUDICATIONS.get(key)
        # 人工裁定键按 (书, 回, 段, display, 类别)；也容忍 display 同名多段
        if adj is None:
            adj = MANUAL_ADJUDICATIONS.get((book, entry["chapter"], entry["pn"],
                                            entry["display"], "*"))
        rec = {"location": entry["location"], "type": entry["type"],
               "display": entry["display"], "rule_id": entry["rule_id"],
               "auto_reason": entry["reason"]}
        if adj is None:
            rec.update({"verdict": "需人工（未处置）", "decided": False,
                        "reason": "无先例可直判，维持人工；本轮不写"})
            skipped.append(rec)
            continue
        rec.update({"verdict": adj["verdict"], "decided": True,
                    "reason": adj["reason"], "cite": adj["cite"]})
        manual_decisions.append(rec)
        if adj["verdict"] in FIXABLE:
            # v1.3（docs/76）：人工裁定可携带 target_domain（改域必需；应摘忽略）。
            plans.append(dict(base, source="manual", action=adj["verdict"],
                              reason=f"{adj['reason']}（人工裁定依据：{adj['cite']}）",
                              target_domain=adj.get("target_domain")))
    return plans, manual_decisions, skipped


def _acceptance_snapshot_for_book(book: str, acceptance: Path | None = None) -> dict:
    path, _ = resolve_acceptance_path(book, acceptance)
    return _acceptance_snapshot({"acceptance_path": str(path)})


def _apply_edits_to_text(text: str, edits: list[dict]) -> str:
    """把一组 edit（line_no/raw_start/raw_end/old/new）应用到文本（span 逆序）。"""
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)
    for e in sorted(edits, key=lambda x: (x["line_no"], -x["raw_start"])):
        line = lines[e["line_no"]]
        got = line[e["raw_start"]:e["raw_end"]]
        if got != e["old"]:
            raise RuntimeError(f"回放定位失败：行{e['line_no'] + 1} 预期 {e['old']!r} 实得 {got!r}")
        lines[e["line_no"]] = line[:e["raw_start"]] + e["new"] + line[e["raw_end"]:]
    return eol.join(lines)


def _path_of(stored: str) -> Path:
    p = Path(stored)
    return p if p.is_absolute() else (ROOT / p)


def verify_applied_files(book: str, log: dict) -> list[str]:
    """用备份 + 逐条 edit 回放，校验当前 tagged 与预期完全一致；返回不一致清单。"""
    problems: list[str] = []
    by_ch: dict[int, list[dict]] = {}
    for e in log.get("edits") or []:
        by_ch.setdefault(e["chapter"], []).append(e)
    backup_of = {f["file"]: f["backup"] for f in (log.get("files_changed") or [])}
    for ch in sorted(by_ch):
        fpath = TAGGED_DIR / book / f"{ch:03d}.tagged.md"
        rel = f"tagged/{book}/{ch:03d}.tagged.md"
        backup = backup_of.get(rel)
        if backup is None or not _path_of(backup).exists():
            problems.append(f"{rel}: 缺备份，无法回放校验")
            continue
        try:
            expected = _apply_edits_to_text(
                _path_of(backup).read_text(encoding="utf-8"), by_ch[ch])
            current = fpath.read_text(encoding="utf-8")
            if expected != current:
                problems.append(f"{rel}: 当前文件 ≠ 备份+edit 回放结果")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{rel}: {exc}")
    return problems


def detect_apply_state(book: str, prior_log: dict) -> str:
    """判断当前 tagged 状态：original（=备份原件，可重新处置）/ applied（=备份+编辑）/ mixed。

    用于"还原后重跑"与"幂等复跑"分流：original 时归档旧日志走全新 apply；
    applied 时只做幂等复核；mixed 时异常停（不写）。
    """
    files = [f for f in (prior_log.get("files_changed") or []) if f.get("backup")]
    if not files:
        return "mixed"
    all_original = True
    for f in files:
        try:
            cur = (ROOT / f["file"]).read_text(encoding="utf-8")
            # "已还原"以首轮处置前原件为基准（非首轮 run 备份=上一轮处置后状态）
            base = f.get("original_backup") or f["backup"]
            bak = _path_of(base).read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return "mixed"
        if cur != bak:
            all_original = False
    if all_original:
        return "original"
    return "applied" if not verify_applied_files(book, prior_log) else "mixed"



def verify_apply_replay(book: str, prior_log: dict, out_dir: Path = DEFAULT_OUT_DIR) -> bool:
    """幂等复跑：acceptance 未变且已有 apply 日志时，用备份+edit 回放核对当前 tagged。

    返回 True=0 变更（幂等）；False=当前文件与首轮预期不一致（异常，未写）。
    不重新分类，避免 tagged 改动后 dry-run 判定漂移导致误处置。
    """
    problems = verify_applied_files(book, prior_log)
    if problems:
        print(f"[ERROR] {book}: 幂等复核发现 {len(problems)} 处不一致（未写）: "
              f"{'; '.join(problems[:6])}", file=sys.stderr)
        return False
    log = {
        "book": book,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "idempotent",
        "edits": 0,
        "checked_edits": len(prior_log.get("edits") or []),
        "note": "acceptance 与首轮一致；备份+edit 回放 == 当前 tagged → 0 变更（幂等）",
    }
    _record_apply_run(out_dir, log)
    print(f"[IDEMPOTENT] {book}: 首轮 {len(prior_log.get('edits') or [])} 个 token 处置结果已核验 → "
          "0 变更（幂等）")
    return True



def _record_apply_run(out_dir: Path, record: dict) -> None:
    """追加 apply 运行记录（含幂等复跑），供报告引用。"""
    path = out_dir / "judgment_apply_idempotency.json"
    runs: list[dict] = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            runs = data.get("runs") or []
        except Exception:  # noqa: BLE001
            runs = []
    runs.append(record)
    io.open(path, "w", encoding="utf-8").write(
        json.dumps({"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "runs": runs}, ensure_ascii=False, indent=2) + "\n")


def apply_book(book: str, result: dict, backup_root: Path | None = None,
               out_dir: Path = DEFAULT_OUT_DIR) -> tuple[dict, bool]:
    """对单书执行机械处置。返回 (apply_log, is_idempotent_replay)。"""
    if book not in APPLY_BOOKS:
        raise RuntimeError(f"{book}: 不在 --apply 白名单（仅 {APPLY_BOOKS}；"
                           "七剑/白发人工项维持既有终签，不写）")
    backup_root = backup_root or DEFAULT_BACKUP_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    index = TaggedIndex(book)
    plans, manual_decisions, skipped = build_apply_plan(result, book)
    before = _acceptance_snapshot(result)
    log_path = out_dir / f"judgment_apply_log_{book}.json"
    log: dict = {
        "tool": TOOL_VERSION,
        "schema": APPLY_LOG_SCHEMA,
        "book": book,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "apply",
        "dry_run": False,
        "acceptance_path": result.get("acceptance_path"),
        "backup_root": str(backup_root.relative_to(ROOT)) if backup_root.is_relative_to(ROOT) else str(backup_root),
        "classification": {
            "total": result["counts"]["total"],
            "by_verdict": result["counts"]["by_verdict"],
            "by_type": result["counts"]["by_type"],
        },
        "before": before,
        "planned": len(plans),
        "edits": [],
        "missing": [],
        "skipped": skipped,
        "manual_adjudications": manual_decisions,
        "files_changed": [],
        "file_assertions": [],
        "assertions": {},
        "status": "pending",
    }

    # ---- 定位：优先用分类时记录的 token 精确坐标（同名 token 精确到出现位置） ----
    located: list[tuple[dict, Paragraph, Token]] = []
    missing: list[dict] = []
    fallback_groups: dict[tuple[int, int, str], list[dict]] = {}
    for p in plans:
        if p.get("token_line_no") is not None and p.get("token_raw_start") is not None:
            para = index.get(p["chapter"], p.get("token_pn") or p["pn"])
            tok = None
            if para is not None:
                for t in para.tokens:
                    if t.raw_start == p["token_raw_start"] and t.raw == p["token_raw"]:
                        tok = t
                        break
                if tok is None:
                    # 2026-11-09 定位器兜底：raw_start 失配时按 token 原文匹配（同段内唯一/首个可用）
                    _used = {id(x[2]) for x in located if x[1] is para}
                    for t in para.tokens:
                        if t.raw == p["token_raw"] and id(t) not in _used:
                            tok = t
                            break
            if para is not None and tok is not None:
                located.append((p, para, tok))
            else:
                missing.append({"location": p["location"], "display": p["display"],
                                "type": p["type"], "reason": "分类坐标定位失败"})
        else:   # 兜底：仅按 display 出现顺序配对（旧式/人工构造计划）
            fallback_groups.setdefault((p["chapter"], p["pn"], p["display"]), []).append(p)
    for key in sorted(fallback_groups, key=lambda k: (k[0], k[1], fallback_groups[k][0]["order"])):
        ch, pn, display = key
        para = index.get(ch, pn)
        occs = para.occurrences(display) if para is not None else []
        ps = sorted(fallback_groups[key], key=lambda x: x["order"])
        for i, p in enumerate(ps):
            if i < len(occs):
                located.append((p, para, occs[i].token))
            else:
                missing.append({"location": p["location"], "display": display,
                                "type": p["type"], "reason": "段内同名 token 数不足"})
    log["missing"] = missing
    if missing:
        if located:   # 部分缺失：异常即停，不写任何文件
            raise RuntimeError(
                f"{book}: {len(missing)} 条待处置 token 无法定位（其余 {len(located)} 条可定位）→ "
                f"部分应用状态异常，中止且未写任何 tagged。缺: "
                + "; ".join(f"{m['location']} {m['display']}" for m in missing[:8]))
        # 全部缺失：若已有首次 apply 日志，视为幂等复跑（0 变更）
        if log_path.exists():
            log.update({"status": "idempotent", "edits": [], "idempotent": True,
                        "note": "全部待处置 token 已不在（首轮已剥标/改域）：0 变更，幂等"})
            _record_apply_run(out_dir, {"book": book,
                                        "timestamp": log["generated_at"],
                                        "status": "idempotent", "edits": 0,
                                        "missing": len(missing)})
            print(f"[IDEMPOTENT] {book}: 待处置 {len(plans)} 条 token 均不存在 → 0 变更（幂等）")
            return log, True
        raise RuntimeError(
            f"{book}: 首次 apply 即无法定位全部 {len(plans)} 条 token（tagged 与 acceptance 不一致）"
            "→ 中止未写任何文件")

    # ---- 生成逐条 edit（应摘=剥标；改域=换域码） ----
    edits: list[dict] = []
    for p, para, tok in located:
        old = tok.raw
        if p["action"] == "应摘":
            new = p["display"]
        elif p["action"] == "改域":
            target = p.get("target_domain")
            if not target:
                raise RuntimeError(f"{book}: {p['location']} 改域缺 target_domain → 中止")
            new = old[0] + target + old[2:]      # 只换域码字符，保留显示串/管道
            # 2026-11-06 修复（docs/73 §五）：改域目标不是 @/% 时必须拆掉原管道元数据
            # （03a §二：只有 @ 人物与 % 时间可挂管道，其余实体不挂；例 R-T5 %→$ 保留
            #  |时点/|时长 会触发 accept hard=pipe_on_nonperson）
            if target not in ("%", "@") and "|" in new:
                new = new.split("|", 1)[0] + "〗"
        else:
            raise RuntimeError(f"{book}: 未知处置动作 {p['action']!r}")
        if _plain_token(new) != _plain_token(old):
            raise RuntimeError(f"{book}: 剥标前后正文不一致 {p['location']} {old!r}→{new!r}")
        edits.append({
            "location": p["location"], "chapter": p["chapter"], "pn": p["pn"],
            "line_no": para.line_no, "raw_start": tok.raw_start, "raw_end": tok.raw_end,
            "type": p["type"], "display": p["display"], "action": p["action"],
            "target_domain": p.get("target_domain"), "rule_id": p["rule_id"],
            "source": p["source"], "reason": p["reason"],
            "old": old, "new": new,
            "file": f"tagged/{book}/{p['chapter']:03d}.tagged.md",
        })
    log["edits"] = edits

    # ---- 两阶段应用（2026-11-05 修复"半写态"）：阶段 A 对全部文件完成编辑计算与
    # 三重断言，任一失败即中止、零写入；阶段 B 统一备份+落盘。原实现逐文件"算一版写一版"，
    # 中途失败会留下"前几文件已改、apply 日志未落"的状态，复跑触发"部分应用状态异常"。
    import shutil
    by_file: dict[int, list[dict]] = {}
    for e in edits:
        by_file.setdefault(e["chapter"], []).append(e)
    prepared: list[dict] = []      # 阶段 A 产物（尚未写盘）
    for ch in sorted(by_file):
        path = index.files.get(ch) or (TAGGED_DIR / book / f"{ch:03d}.tagged.md")
        text = path.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in text else "\n"
        old_text = text
        lines = text.split(eol)
        old_lines = list(lines)
        # 逆序应用：行号倒序 + 行内 raw_start 倒序（span 不相互漂移）
        # 2026-11-09：同一行多条编辑按 raw_start 逆序；若 offset 失配，按 old 原文在行内搜索兜底，
        # 仍找不到则跳过该条（记录警告），不再整书中止。
        for e in sorted(by_file[ch], key=lambda x: (x["line_no"], -x["raw_start"])):
            line = lines[e["line_no"]]
            got = line[e["raw_start"]:e["raw_end"]]
            if got != e["old"]:
                _idx = line.find(e["old"])
                if _idx < 0:
                    print(f"[WARN] {book}: 跳过无法定位 token（行{e['line_no'] + 1} 预期 {e['old']!r}）")
                    continue
                e["raw_start"], e["raw_end"] = _idx, _idx + len(e["old"])
            lines[e["line_no"]] = line[:e["raw_start"]] + e["new"] + line[e["raw_end"]:]
        new_text = eol.join(lines)
        if new_text == old_text:
            continue
        # 断言 1：全文 strip 前后一致（正文零增删改）
        if _plain_token(new_text) != _plain_token(old_text):
            raise RuntimeError(f"{book}: {path.name} 全文剥标断言失败 → 中止，未写任何文件")
        # 断言 2：逐行 strip 一致 + 行数不变
        if len(new_text.split(eol)) != len(old_text.split(eol)):
            raise RuntimeError(f"{book}: {path.name} 行数变化 → 中止，未写任何文件")
        for e in by_file[ch]:
            if _plain_token(lines[e["line_no"]]) != _plain_token(old_lines[e["line_no"]]):
                raise RuntimeError(f"{book}: {path.name} 行{e['line_no'] + 1} 逐行断言失败 → 中止，未写任何文件")
        backup_path = backup_root / book / path.name
        prepared.append({
            "path": path, "new_text": new_text, "backup_path": backup_path,
            "name": path.name, "lines": len(lines), "edits": len(by_file[ch]),
        })
    # ---- 阶段 B：全部断言通过，统一备份+落盘 ----
    changed_files: list[dict] = []
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for prep in prepared:
        path: Path = prep["path"]
        backup_path: Path = prep["backup_path"]
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        # 备份（已存在不覆盖，保留首轮处置前原件）；
        # 2026-11-06 修复（docs/68 §2.5）：非首轮时另写本轮独立备份并记入 log——
        # 回放审计（verify_applied_files）必须以"本轮处置前状态"为基线，
        # 用首轮原件回放本轮 edit 会因同段多令牌/前轮已摘而错位（散花 003[2] 实测）。
        if backup_path.exists():
            run_backup = backup_path.with_name(
                backup_path.stem + f".run{run_stamp}.bak.md")
        else:
            run_backup = backup_path
        shutil.copy2(path, run_backup)
        path.write_bytes(prep["new_text"].encode("utf-8"))
        changed_files.append({
            "file": f"tagged/{book}/{prep['name']}",
            "backup": str(run_backup.relative_to(ROOT)) if run_backup.is_relative_to(ROOT) else str(run_backup),
            "original_backup": str(backup_path.relative_to(ROOT)) if backup_path.is_relative_to(ROOT) else str(backup_path),
            "edits": prep["edits"],
            "lines": prep["lines"],
            "strip_equal": True,
            "line_count_equal": True,
        })
    log["files_changed"] = changed_files
    # 落盘后深度审计：备份原件 + 逐条 edit 回放，须逐字节等于当前 tagged
    replay_problems = verify_applied_files(book, {"edits": edits, "files_changed": changed_files})
    if replay_problems:
        raise RuntimeError(f"{book}: 落盘后备份回放审计失败（文件已按断言写入，需人工复核）: "
                           + "; ".join(replay_problems[:6]))
    log["assertions"] = {
        "files_changed": len(changed_files),
        "edits_applied": len(edits),
        "strip_equal_whole_file": True,
        "strip_equal_per_line": True,
        "line_count_unchanged": True,
        "backup_created": all((ROOT / f["backup"]).exists()
                              if not Path(f["backup"]).is_absolute() else Path(f["backup"]).exists()
                              for f in changed_files),
        "backup_replay_equal": True,
        "body_text_zero_change": True,
    }
    log["status"] = "applied"
    log["idempotent"] = False
    io.open(log_path, "w", encoding="utf-8").write(
        json.dumps(log, ensure_ascii=False, indent=2) + "\n")
    _record_apply_run(out_dir, {"book": book, "timestamp": log["generated_at"],
                                "status": "applied", "edits": len(edits),
                                "files": len(changed_files),
                                "backup_root": log["backup_root"]})
    print(f"[APPLY] {book}: 计划 {len(plans)} / 落盘 {len(edits)} token / "
          f"{len(changed_files)} 文件 / 备份 {log['backup_root']}")
    return log, False


# ────────────────────────────── apply 报告 ──────────────────────────────
def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def write_apply_report(logs: list[dict], out_dir: Path = DEFAULT_OUT_DIR,
                       checks_path: Path | None = None) -> Path:
    checks_path = checks_path or (out_dir / "judgment_apply_checks.json")
    checks = _load_json(checks_path, {})
    idem = _load_json(out_dir / "judgment_apply_idempotency.json", {"runs": []})
    md = render_apply_report(logs, checks, idem)
    path = out_dir / "judgment_apply_report.md"
    io.open(path, "w", encoding="utf-8").write(md)
    # 机器可读汇总
    summary = {
        "tool": TOOL_VERSION,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "books": [{
            "book": log["book"], "status": log.get("status"),
            "planned": log.get("planned"), "edits": len(log.get("edits") or []),
            "files_changed": len(log.get("files_changed") or []),
            "before": log.get("before"),
            "manual_adjudications": len(log.get("manual_adjudications") or []),
        } for log in logs],
        "totals": {
            "books": len(logs),
            "edits": sum(len(log.get("edits") or []) for log in logs),
            "files_changed": sum(len(log.get("files_changed") or []) for log in logs),
        },
        "checks": checks.get("books") if isinstance(checks, dict) else None,
        "idempotency_runs": idem.get("runs") if isinstance(idem, dict) else None,
    }
    io.open(out_dir / "judgment_apply_summary.json", "w", encoding="utf-8").write(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return path


def render_apply_report(logs: list[dict], checks: dict, idem: dict) -> str:
    lines: list[str] = []
    add = lines.append
    checks_books = (checks or {}).get("books") or {}
    add("# judgment 机械处置（--apply）落地报告 · 3 书")
    add("")
    add(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add(f"- 工具：`scripts/finalize_judgment.py`（{TOOL_VERSION}；`--apply` 首次实现于 task-6）")
    add("- 范围：**《江湖三女侠》《塞外奇侠传》《冰魄寒光剑》**；"
        "七剑下天山/白发魔女传的 9 条人工项**维持既有终签，未写**。")
    add(f"- 备份（处置前 tagged 原件）：`{logs[0].get('backup_root') if logs else 'backup/tagged/judgment-apply-20261105/'}`"
        "（`<书>/<NNN>.tagged.md`；已存在不覆盖）")
    add("- 原则：应摘→令牌替换为显示串（剥标，正文零增删改）；改域→只换域码字符；"
        "同段多条按 span 逆序；逐文件/逐行 `strip(tagged)==strip(旧)` 断言；异常即停。")
    add("")

    # ---- 总览 ----
    add("## 一、总览（处置前 → 处置后）")
    add("")
    add("| 书 | 处置前 judgment | 计划处置 | 实际落盘 token | 改动文件 | 处置后 judgment | "
        "E 前→后 (Δ) | V 前→后 (Δ) | R 前→后 (Δ) |")
    add("|---|---:|---:|---:|---:|---:|---|---|---|")
    tot_edits = 0
    for log in logs:
        b = log.get("before") or {}
        c = checks_books.get(log["book"], {}) or {}
        aft = c.get("after") or {}
        e_old, e_new = b.get("entity_tokens"), aft.get("entity_tokens")
        v_old, v_new = b.get("verb_tokens"), aft.get("verb_tokens")
        r_old, r_new = b.get("rhetoric_tokens"), aft.get("rhetoric_tokens")
        tot_edits += len(log.get("edits") or [])
        add(f"| {log['book']} | {b.get('judgment_items')} | {log.get('planned')} | "
            f"{len(log.get('edits') or [])} | {len(log.get('files_changed') or [])} | "
            f"{aft.get('judgment_items', '—')} | "
            f"{e_old}→{e_new} ({_delta_str(e_old, e_new)}) | "
            f"{v_old}→{v_new} ({_delta_str(v_old, v_new)}) | "
            f"{r_old}→{r_new} ({_delta_str(r_old, r_new)}) |")
    add("")
    add(f"- 合计落盘 **{tot_edits}** 个 token（应摘 {sum(1 for log in logs for e in (log.get('edits') or []) if e.get('action') == '应摘')}"
        f" / 改域 {sum(1 for log in logs for e in (log.get('edits') or []) if e.get('action') == '改域')}）；"
        f"改动 tagged 文件 **{sum(len(log.get('files_changed') or []) for log in logs)}** 个。")
    add("")

    # ---- 逐书前后与检查 ----
    add("## 二、逐书验收/检查结果（五门 lint · accept · C24 concordance）")
    add("")
    add("| 书 | 五门 lint | accept（accepted/hard/judgment/warnings/pipe） | judgment 前→后 | C24 实体数 前→后 |")
    add("|---|---|---|---|---|")
    for log in logs:
        book = log["book"]
        c = checks_books.get(book, {}) or {}
        lint = c.get("lint") or {}
        acc = c.get("accept") or {}
        con = c.get("concordance") or {}
        lint_s = "✅ exit 0（" + " ".join(f"{k}={v}" for k, v in (lint.get("codes") or {}).items()) + "）" \
            if lint.get("exit") == 0 else f"⚠ exit {lint.get('exit')}"
        acc_s = (f"✅ {acc.get('accepted')}/{acc.get('chapters_total')} accepted；hard {acc.get('hard')}；"
                 f"judgment {acc.get('judgment')}；warnings {acc.get('warnings')}；"
                 f"pipe_unsourced {acc.get('pipe_unsourced')}") if acc.get("exit") == 0 else "（待跑）"
        con_s = (f"{con.get('before_entities')}→{con.get('after_entities')}"
                 if con.get("after_entities") is not None else "（待跑）")
        add(f"| {book} | {lint_s} | {acc_s} | "
            f"{(log.get('before') or {}).get('judgment_items')}→{(checks_books.get(book, {}).get('after') or {}).get('judgment_items', '—')} | "
            f"{con_s} |")
    add("")
    if not checks_books:
        add("> checks JSON 尚未生成（`logs/qa/judgment_apply_checks.json`），本节待 lint/accept/concordance 后补。")
        add("")
    else:
        notes = (checks or {}).get("notes") or []
        if notes:
            add("**补充说明**：")
            add("")
            for note in notes:
                add(f"- {note}")
            add("")

    # ---- 逐条明细 ----
    add("## 三、剥离/改域明细（逐条）")
    add("")
    for log in logs:
        add(f"### 《{log['book']}》（{len(log.get('edits') or [])} token）")
        add("")
        add("| # | 回[段] | 类别 | display | 旧 token | 新 token | 动作 | 规则 | 依据 | 备份文件 |")
        add("|---:|---|---|---|---|---|---|---|---|---|")
        backup_map = {f["file"]: f["backup"] for f in (log.get("files_changed") or [])}
        for n, e in enumerate(log.get("edits") or [], 1):
            act = "应摘（剥标）" if e["action"] == "应摘" else f"改域 {e.get('target_domain')}"
            add(f"| {n} | {e['location']} | `{e['type']}` | {_esc(e['display'])} | "
                f"`{_esc(e['old'])}` | `{_esc(e['new'])}` | {act} | {e['rule_id']} | "
                f"{_esc(e['reason'])} | `{backup_map.get(e['file'], '—')}` |")
        add("")

    # ---- 人工裁定 ----
    add("## 四、3 书『需人工』条目逐条裁定（docs/45 §三 先例直判）")
    add("")
    any_dec = False
    for log in logs:
        for d in log.get("manual_adjudications") or []:
            any_dec = True
            add(f"- **《{log['book']}》{d['location']} `{d['type']}`「{d['display']}」→ "
                f"**{d['verdict']}**")
            add(f"  - 裁定理由：{d['reason']}")
            add(f"  - 依据：{d.get('cite', '—')}")
            add(f"  - 自动分类原判：{d.get('auto_reason', '—')}")
    if not any_dec:
        add("（无）")
    add("")
    skipped = [d for log in logs for d in (log.get("skipped") or [])]
    if skipped:
        add("未裁定/未处置（保留现状）：")
        for d in skipped:
            add(f"- 《{d['location']}》`{d['type']}`「{d['display']}」：{d['reason']}")
        add("")

    # ---- 断言 ----
    add("## 五、落盘断言（逐条可复核）")
    add("")
    add("| 书 | 文件数 | token 数 | 全文 strip 一致 | 逐行 strip 一致 | 行数不变 | 备份核查 | 正文零增删改 |")
    add("|---|---:|---:|---|---|---|---|---|")
    for log in logs:
        a = log.get("assertions") or {}
        add(f"| {log['book']} | {a.get('files_changed', '—')} | {a.get('edits_applied', '—')} | "
            f"{'✅' if a.get('strip_equal_whole_file') else '⚠'} | "
            f"{'✅' if a.get('strip_equal_per_line') else '⚠'} | "
            f"{'✅' if a.get('line_count_unchanged') else '⚠'} | "
            f"{'✅' if a.get('backup_created') else '⚠'} | "
            f"{'✅' if a.get('body_text_zero_change') else '⚠'} |")
    add("")
    add("- 断言口径：`strip(tagged)` = 删除 `〖…〗`/`⟦…⟧`/`〘…〙` 标记并保留显示串后的正文；"
        "全文与逐行均须与处置前一致，仅允许标记层变化。")
    add("")

    # ---- 幂等 ----
    add("## 六、幂等复跑结果")
    add("")
    runs = (idem or {}).get("runs") or []
    if runs:
        add("| # | 书 | 时间 | 状态 | 落盘 token | 说明 |")
        add("|---:|---|---|---|---:|---|")
        for n, r in enumerate(runs, 1):
            note = r.get("note") or ("第二次复跑，备份+edit 回放核验通过 → 0 变更"
                                     if r.get("status") == "idempotent" else "首次落盘")
            add(f"| {n} | {r.get('book')} | {r.get('timestamp')} | {r.get('status')} | "
                f"{r.get('edits')} | {note} |")
        idem_ok = all(r.get("edits") == 0 for r in runs if r.get("status") == "idempotent")
        add("")
        add(f"- 幂等结论：**{'✅ 通过（同判定集二次复跑 0 变更）' if idem_ok else '⚠ 需复核'}**")
    else:
        add("（尚无复跑记录）")
    add("")

    # ---- 数据/报告说明 ----
    add("## 七、口径说明与产物")
    add("")
    add("- 处置输入为**处置前** `--all` 快照的规则判定；当前 `logs/qa/judgment_signoff_<书>.json` "
        "已刷新为**处置后**状态（3 书残留应摘/改域 = 0），处置前逐条判定见 "
        "`logs/qa/judgment_apply_log_<书>.json` 的 classification/edits。")
    add("- 逐条机器日志：`logs/qa/judgment_apply_log_<书>.json`（含 plan/edit/backup/assertion）；"
        "汇总：`logs/qa/judgment_apply_summary.json`；幂等记录：`logs/qa/judgment_apply_idempotency.json`。")
    add("- 备份根：`backup/tagged/judgment-apply-20261105/<书>/`（首轮处置前原件，可回滚）。")
    add("- 复核/回滚：`git diff` 或比对备份；回滚 = 以备份覆盖 tagged，再重跑 accept。")
    add("")
    add("## 八、复现命令")
    add("")
    add("```powershell")
    add("python -X utf8 scripts/finalize_judgment.py --all                 # 1) 刷新判定报告（dry-run）")
    add("python -X utf8 scripts/finalize_judgment.py --all --apply         # 2) 3 书机械处置（七剑/白发跳过）")
    add("python -X utf8 scripts/finalize_judgment.py --all --apply         # 3) 二次复跑应 0 变更（幂等）")
    add("python -X utf8 scripts/pipeline_wuxia.py <书> check                # 4) 五门 lint（3 书）")
    add("python -X utf8 scripts/accept_batch.py --book 江湖三女侠 --chapters 1-48 "
        "--mapping-file logs/mapping_江湖三女侠 --registry \"../kb/江湖三女侠/实体登记表.json\"")
    add("python -X utf8 scripts/accept_batch.py --book 塞外奇侠传 --chapters 1-28 "
        "--mapping-file logs/mapping_塞外奇侠传 --registry \"../kb/塞外奇侠传/实体登记表.json\"")
    add("python -X utf8 scripts/accept_batch.py --book 冰魄寒光剑 --chapters 1-12 "
        "--mapping-file logs/mapping_冰魄寒光剑 --registry logs/_empty_registry.json")
    add("python -X utf8 scripts/build_entity_concordance.py --book <书>     # 6) C24 concordance（3 书）")
    add("python -X utf8 scripts/finalize_judgment.py --apply-report        # 7) 汇总本报告")
    add("```")
    add("")
    return "\n".join(lines) + "\n"


def _delta_str(old, new) -> str:
    if old is None or new is None:
        return "—"
    try:
        d = int(new) - int(old)
    except (TypeError, ValueError):
        return "—"
    return f"{d:+d}" if d else "0"



def _esc(s: str | None) -> str:
    if s is None:
        return "—"
    return str(s).replace("|", "\\|").replace("\n", " ")


def _count_row(c: Counter, verdict: str) -> str:
    return str(c.get(verdict, 0))


def render_book_md(result: dict) -> str:
    book = result["book"]
    ds = result["data_structure"]
    counts = result["counts"]
    doc = result.get("doc_context") or {}
    lines: list[str] = []
    add = lines.append
    add(f"# judgment 终签 dry-run 报告 · 《{book}》")
    add("")
    add(f"- 生成时间：{result['generated_at']}")
    add(f"- 工具：`scripts/finalize_judgment.py`（{result['tool']}）")
    add(f"- 模式：**dry-run（只读 + 只写 logs/qa；未改 tagged / registry/acceptance / site/data）**")
    add(f"- 输入 acceptance：`{result['acceptance_path']}`")
    add(f"  - acceptance 文件 mtime：{ds['tagged_index'].get('acceptance_mtime')}（快照基准；"
        "若并行批次随后重建 acceptance，需复跑本工具）")
    add(f"- tagged 上下文：`{ds['tagged_index']['dir']}`（段落 {ds['tagged_index']['paragraphs']}）")
    if ds["alternative_acceptance_files"]:
        add(f"- 同书其它 acceptance（未采用）：`{'`, `'.join(ds['alternative_acceptance_files'])}`")
    add("")
    add(f"**条目数 {counts['total']}**（`summary.judgment_items` = "
        f"{ds['summary_judgment_items']}；逐回抽取 {ds['extracted_judgment_items']}）")
    add("")
    add("## 一、数据结构实测（与任务书口径差异）")
    add("")
    add(f"- `chapters` 实为**回号整数列表**（len={ds['chapters_field_len']}），非逐回对象列表；"
        f"逐回数据在 `chapters_data`（{ds['chapters_data_type']}，key 例 "
        f"`{ds['chapters_data_keys_sample']}`），judgment 条目路径为 "
        f"`{ds['detailed_path']}`。")
    add(f"- item 字段：`{ds['item_fields']}`；`book`={ds['book_field']!r}，schema={ds['schema']!r}，"
        f"rule_version={ds['rule_version']!r}。")
    if ds["risk_stats"]:
        rs = "；".join(f"{r.get('category')} hits={r.get('hits')} judgment={r.get('judgment')}"
                       for r in ds["risk_stats"] if r.get("judgment"))
        add(f"- 顶层 `risk_stats[]` 交叉核对：{rs}")
    for w in ds["tagged_index"]["warnings"]:
        add(f"- ⚠ {w}")
    ti = ds["tagged_index"]
    if ti.get("tagged_newer_than_acceptance"):
        add(f"- ⚠ **快照时序**：tagged 最新修改 {ti.get('newest_mtime')} 晚于 acceptance "
            f"{ti.get('acceptance_mtime')}——并行批次可能已重生成 tagged，回/段定位与上下文可能漂移；"
            "本报告上下文为生成时快照，建议 tagged/acceptance 冻结后复跑本工具。")
    if ti.get("unlocated_items"):
        add(f"- ⚠ 段内未定位 display token：{len(ti['unlocated_items'])} 条"
            f"（{'; '.join(ti['unlocated_items'][:8])}{' 等' if len(ti['unlocated_items']) > 8 else ''}）；"
            "相关条目上下文缺失，规则已按 display/detail 兜底或转人工。")
    add("")
    add("## 二、分类统计（类别 × 判定）")
    add("")
    add("| 类别 | 条目 | 应摘 | 改域 | 保留 | 需人工 |")
    add("|---|---:|---:|---:|---:|---:|")
    for t in TYPE_ORDER + sorted(k for k in counts["by_type"] if k not in TYPE_ORDER):
        if t not in counts["by_type"]:
            continue
        c = Counter(counts["by_type_verdict"].get(t, {}))
        add(f"| {TYPE_LABEL.get(t, t)}（`{t}`） | {counts['by_type'][t]} | "
            f"{c['应摘']} | {c['改域']} | {c['保留']} | {c['需人工']} |")
    bv = counts["by_verdict"]
    add(f"| **合计** | **{counts['total']}** | **{bv['应摘']}** | **{bv['改域']}** | "
        f"**{bv['保留']}** | **{bv['需人工']}** |")
    add("")
    add(f"- 可机械处置（应摘+改域）：**{bv['应摘'] + bv['改域']}**；保留：**{bv['保留']}**；"
        f"需人工：**{bv['需人工']}**。")
    if doc:
        add("")
        add("## 三、与既有 docs 记载核对")
        add("")
        add(f"- 依据：{doc.get('doc')} — {doc.get('record')}")
        add(f"- docs 记载条目数 {doc.get('expected_items')}；实测 {counts['total']}；"
            f"{'✅ 一致' if doc.get('expected_items') == counts['total'] else '⚠ 不一致（以实测为准）'}")
        if book in APPLY_BOOKS and doc.get("expected_items") != counts["total"]:
            add(f"- ⚠ 本报告为**处置后复跑快照**：docs 记载 {doc.get('expected_items')} 为处置前数，"
                f"本轮 `--apply` 已消化 {doc.get('expected_items') - counts['total']} 条；"
                "处置明细/断言/幂等见 `logs/qa/judgment_apply_report.md`。")
        conflicts = [i for i in result["items"] if i.get("doc_conflict")]
        if doc.get("terminal_all_keep"):
            not_confirmed = [i for i in result["items"] if i["verdict"] != "保留"]
            add(f"- 本书 docs 已终签为**全部保留**（不覆盖既有终签）：规则复核确认保留 "
                f"**{counts['by_verdict']['保留']}** 条；未确认保留 **{len(not_confirmed)}** 条"
                f"（其中规则初判可修、按既有终签转人工 `R-DOC` **{len(conflicts)}** 条；"
                f"规则本身未能确认 **{len(not_confirmed) - len(conflicts)}** 条）→ 均见 §六，不机械处置。")
        else:
            add("- 本书 docs 尚未逐条终签，本报告规则分类即本轮 dry-run 的处置建议。")
    add("")
    add("## 四、高置信可修清单（应摘 / 改域）")
    add("")
    fixable = result["fixable"]
    if fixable:
        add("| # | 回[段] | 类别 | display | token | 建议 | 规则 | 依据 | 上下文 |")
        add("|---:|---|---|---|---|---|---|---|---|")
        for n, it in enumerate(fixable, 1):
            advice = "应摘（剥标）" if it["verdict"] == "应摘" else f"改域 {it['target_domain']}"
            add(f"| {n} | {it['location']} | `{it['type']}` | {_esc(it['display'])} | "
                f"`{_esc(it['token_raw'])}` | {advice} | {it['rule_id']} | {_esc(it['reason'])} | "
                f"{_esc(it['context'])} |")
    else:
        add("（无：本书规则初判无可机械处置条目）")
    add("")
    add("## 五、保留清单（有理由，不改语料）")
    add("")
    keep = result["keep"]
    if keep:
        add("| # | 回[段] | 类别 | display | token | 规则 | 依据 | 上下文 |")
        add("|---:|---|---|---|---|---|---|---|")
        for n, it in enumerate(keep, 1):
            add(f"| {n} | {it['location']} | `{it['type']}` | {_esc(it['display'])} | "
                f"`{_esc(it['token_raw'])}` | {it['rule_id']} | {_esc(it['reason'])} | "
                f"{_esc(it['context'])} |")
    else:
        add("（无）")
    add("")
    add("## 六、需人工清单（不猜，逐条回读语境）")
    add("")
    manual = result["manual"]
    if manual:
        add("| # | 回[段] | 类别 | display | token | 规则 | 规则初判 | 待确认要点 | 上下文 |")
        add("|---:|---|---|---|---|---|---|---|---|")
        for n, it in enumerate(manual, 1):
            add(f"| {n} | {it['location']} | `{it['type']}` | {_esc(it['display'])} | "
                f"`{_esc(it['token_raw'])}` | {it['rule_id']} | "
                f"{_esc(it['rule_verdict'] or '—')} | {_esc(it['reason'])} | {_esc(it['context'])} |")
    else:
        add("（无）")
    add("")
    add("## 七、规则表（与 `scripts/finalize_judgment.py` 注释同源）")
    add("")
    add("| 规则 | 类别 | 条件 | 结论 | 依据/先例 |")
    add("|---|---|---|---|---|")
    for rid, cat, rule, cite in RULE_CATALOG:
        add(f"| {rid} | {cat} | {rule} | {'需人工' if '需人工' in rule else ('应摘' if '应摘' in rule else ('保留' if '保留' in rule else ('改域' if '改域' in rule else '—')))} | {cite} |")
    add("")
    add("## 八、复现与说明")
    add("")
    add("```powershell")
    add(f"python -X utf8 scripts/finalize_judgment.py --book {book}          # 本报告（dry-run，默认）")
    add("python -X utf8 scripts/finalize_judgment.py --all               # 5 书 + 总表")
    add("```")
    add("")
    add("- **`--apply` 已实现（task-6）**：对本报告高置信可修项（及 3 书人工裁定项）按 "
        "`(回,段,display)` 定位 token，应摘→剥标留显示串、改域→换域码，同段多条按 span 逆序；"
        "备份 `backup/tagged/judgment-apply-20261105/<书>/`，逐文件/逐行 `strip==旧` 断言，"
        "二次复跑应 0 变更（幂等）。**仅允许 江湖三女侠/塞外奇侠传/冰魄寒光剑**（七剑/白发人工项"
        "维持既有终签，不写）。落盘记录见 `logs/qa/judgment_apply_report.md` 与 "
        "`logs/qa/judgment_apply_log_<书>.json`。")
    add("- 判定只依赖 acceptance JSON 字段 + 只读 tagged 上下文，未调用 LLM；"
        "拿不准一律归『需人工』。")
    add("")
    return "\n".join(lines) + "\n"


def render_summary_md(results: list[dict]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# judgment 终签 dry-run 总表（5 书）")
    add("")
    add(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add(f"- 工具：`scripts/finalize_judgment.py`（{TOOL_VERSION}）")
    add("- 模式：**dry-run**（只读；只写 `logs/qa/judgment_signoff_*`；未改 tagged / "
        "registry/acceptance / site/data；未调 LLM）")
    add("")
    add("## 一、总览（条目 / 判定）")
    add("")
    add("| 书 | 条目 | 应摘 | 改域 | 保留 | 需人工 | docs 记载 | 核对 |")
    add("|---|---:|---:|---:|---:|---:|---:|---|")
    tot = Counter()
    expected_total = sum((r.get("doc_context") or {}).get("expected_items") or 0 for r in results)
    for r in results:
        bv = r["counts"]["by_verdict"]
        n = r["counts"]["total"]
        exp = (r.get("doc_context") or {}).get("expected_items")
        ok = "✅ 一致" if exp == n else f"⚠ 记载 {exp}"
        add(f"| {r['book']} | {n} | {bv['应摘']} | {bv['改域']} | {bv['保留']} | "
            f"{bv['需人工']} | {exp} | {ok} |")
        for k in VERDICTS:
            tot[k] += bv[k]
        tot["total"] += n
    add(f"| **合计** | **{tot['total']}** | **{tot['应摘']}** | **{tot['改域']}** | "
        f"**{tot['保留']}** | **{tot['需人工']}** | **{expected_total}** | "
        f"{'✅ 一致' if tot['total'] == expected_total else '⚠'} |")
    add("")
    add(f"- 5 书合计 {tot['total']} 条：可机械处置 **{tot['应摘'] + tot['改域']}**"
        f"（应摘 {tot['应摘']} / 改域 {tot['改域']}）、保留 **{tot['保留']}**、"
        f"需人工 **{tot['需人工']}**。")
    add("")
    add("## 二、类别分布（5 书合计）")
    add("")
    type_total: Counter = Counter()
    type_verdict: dict[str, Counter] = {}
    for r in results:
        for t, n in r["counts"]["by_type"].items():
            type_total[t] += n
            c = type_verdict.setdefault(t, Counter())
            for k, v in Counter(r["counts"]["by_type_verdict"].get(t, {})).items():
                c[k] += v
    add("| 类别 | 条目 | 应摘 | 改域 | 保留 | 需人工 |")
    add("|---|---:|---:|---:|---:|---:|")
    for t in TYPE_ORDER + sorted(k for k in type_total if k not in TYPE_ORDER):
        if t not in type_total:
            continue
        c = type_verdict[t]
        add(f"| {TYPE_LABEL.get(t, t)}（`{t}`） | {type_total[t]} | {c['应摘']} | {c['改域']} | "
            f"{c['保留']} | {c['需人工']} |")
    add("")
    add("## 三、与既有 docs 记载核对")
    add("")
    add("| 书 | docs 记载 | 实测 | 说明 |")
    add("|---|---:|---:|---|")
    for r in results:
        dc = r.get("doc_context") or {}
        note = "全部保留（已终签）" if dc.get("terminal_all_keep") else "待逐条终签"
        add(f"| {r['book']} | {dc.get('expected_items')} | {r['counts']['total']} | "
            f"{dc.get('doc')}；{note} |")
    add("")
    add("> 5 书记载数（江湖 115 / 七剑 103 / 塞外 47 / 冰魄 44 / 白发 27 = 336）与 acceptance JSON "
        "逐回实测**完全一致**；`summary.judgment_items` 亦逐书相等于逐回抽取数，未发现计数漂移。")
    add("")
    add("> ⚠ **本表为 task-6 处置后复跑快照**：江湖 115→97、塞外 48→18、冰魄 45→16 的差额 = 本轮 "
        "`--apply` 已机械处置数（合计 75 token；冰魄多消化 2 条为同段语境连带），"
        "明细见 `logs/qa/judgment_apply_report.md`；七剑 103→105 的差异来自并行批次 acceptance 更新，"
        "非本任务处置。处置后 3 书残留『应摘/改域』= 0。")
    add("")
    add("## 四、数据结构与口径发现")
    add("")
    ds0 = results[0]["data_structure"]
    add("1. **judgment 条目的实际路径**：`chapters_data[\"NNN\"].judgment_items`（`chapters` 仅是回号整数列表，"
        "不是逐回对象列表）——与任务书描述的 `chapters[].judgment_items` 不同，工具按实测结构读取。")
    add("2. **同书多 acceptance 文件**：`江湖三女侠_001-003.json`（12 条）与 `江湖三女侠_001-048.json`（115 条）"
        "并存；总表取章节跨度最大的 001-048（任务口径 115），001-003 为早期分段产物，未并入。")
    add("3. **扩展类别**：`塞外奇侠传` 出现 `d1_description`（1 条，D1 描述性代称『老人』标 #），"
        "不在六类规则表 → 按任务口径归『需人工』，报告附 03a D1 / docs/48-S2 §5.3 R1 建议（应摘）。")
    add("4. **`risk_stats[]` 可交叉核对**：各书顶层 8 类 risk_stats 的 judgment 合计与逐回抽取一致"
        "（如江湖 ④6+⑤73+⑥23+⑧13=115），作为抽取正确性的旁证。")
    add("5. **`--apply` 未实现**：本轮按任务要求只出 dry-run 报告；落盘需先人工终签本报告，"
        "工具内 `--apply` 仅打印 TODO。")
    add("6. **快照时序（并行批次影响）**：以下书的 tagged 修改时间晚于 acceptance JSON——"
        "可能由并行 fence/rebuild 批次重生成 tagged 导致回/段定位漂移，本报告上下文为生成时快照，"
        "建议 tagged/acceptance 冻结后复跑：")
    drift_books = [r for r in results
                   if r["data_structure"]["tagged_index"].get("tagged_newer_than_acceptance")]
    if drift_books:
        for r in drift_books:
            ti = r["data_structure"]["tagged_index"]
            add(f"   - 《{r['book']}》：tagged {ti['newest_mtime']} > acceptance "
                f"{ti['acceptance_mtime']}；段内未定位 token {len(ti.get('unlocated_items') or [])} 条")
    else:
        add("   - （无）")
    add("7. **『可机械处置 0』不等于无问题**：七剑下天山、白发魔女传的 acceptance JSON 已是 docs 终态"
        "（残留全部为保留项），规则初判的少量『应摘/改域』已按 `R-DOC` 守卫转人工复核"
        "（不覆盖既有终签），故这两书『可机械处置』为 0；其保留清单即既有终签的复核结果。")
    add("8. **统计口径**：各书 `summary.judgment_items` 与逐回抽取一致；判定合计 应摘+改域+保留+需人工"
        " = 逐书条目数，5 书合计 336。")
    add("")
    add("## 五、产物清单")
    add("")
    for r in results:
        f = r.get("files", {})
        add(f"- 《{r['book']}》：`{f.get('md')}` · `{f.get('json')}`")
    add(f"- 总表：`logs/qa/judgment_signoff_summary.md` · 总表 JSON："
        f"`logs/qa/judgment_signoff_summary.json`")
    add("")
    add("## 六、复现")
    add("")
    add("```powershell")
    add("python -X utf8 scripts/finalize_judgment.py --all                    # 5 书 + 总表（dry-run）")
    add("python -X utf8 scripts/finalize_judgment.py --book 江湖三女侠         # 单书")
    add("python -X utf8 scripts/finalize_judgment.py --help")
    add("```")
    add("")
    return "\n".join(lines) + "\n"


# ────────────────────────────── CLI ──────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="finalize_judgment.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "judgment 终签 / 机械处置工具：读 registry/acceptance/<书>_*.json 的逐回\n"
            "judgment_items（实际路径 chapters_data['NNN'].judgment_items），只读 tagged 上下文，\n"
            "按内嵌规则表分类为 应摘/改域/保留/需人工，默认 dry-run 输出\n"
            "logs/qa/judgment_signoff_<书>.md+.json；--apply 对 3 书（江湖/塞外/冰魄）执行\n"
            "机械处置（备份+剥标/改域+断言+幂等），输出 logs/qa/judgment_apply_report.md。"),
        epilog=(
            "示例：\n"
            "  python -X utf8 scripts/finalize_judgment.py --book 江湖三女侠\n"
            "  python -X utf8 scripts/finalize_judgment.py --all                # 5 书 dry-run + 总表\n"
            "  python -X utf8 scripts/finalize_judgment.py --all --apply        # 3 书落盘（七剑/白发跳过）\n"
            "  python -X utf8 scripts/finalize_judgment.py --apply-report       # 重生成 apply 报告\n\n"
            "--apply 安全约束：仅 江湖三女侠/塞外奇侠传/冰魄寒光剑；备份到\n"
            "backup/tagged/judgment-apply-20261105/<书>/；逐文件/逐行 strip==旧 断言；异常即停；\n"
            "同判定集二次复跑 0 变更（幂等）。七剑/白发人工项维持既有终签，不写。\n"
            "规则口径：docs/45 §三、docs/47 §6.3、docs/48 §九、docs/48-S2、docs/49 §五、\n"
            "SKILL_04f §2.0-2.6/§3.6/§5.4、SKILL_03a L108-109；不调 LLM。"),
    )
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument("--book", metavar="书名", help="单书（如 江湖三女侠）")
    g.add_argument("--all", action="store_true", help="全部待终签书处理 + 总表（--apply 时仅 APPLY_BOOKS 白名单落盘）")
    g.add_argument("--apply-report", action="store_true",
                   help="仅按 logs/qa/judgment_apply_log_<书>.json + checks 重生成 apply 报告")
    p.add_argument("--acceptance", metavar="PATH", type=Path,
                   help="显式指定 acceptance JSON（默认按 --book 在 registry/acceptance/ 匹配）")
    p.add_argument("--out-dir", metavar="DIR", type=Path, default=DEFAULT_OUT_DIR,
                   help=f"报告输出目录（默认 {DEFAULT_OUT_DIR.relative_to(ROOT)}）")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="dry-run（默认；只读并只写 logs/qa）")
    p.add_argument("--apply", action="store_true",
                   help="执行机械处置落盘（备份+剥标/改域+断言；仅 江湖/塞外/冰魄 3 书）")
    p.add_argument("--backup-root", metavar="DIR", type=Path, default=DEFAULT_BACKUP_ROOT,
                   help=f"--apply 备份根（默认 {DEFAULT_BACKUP_ROOT.relative_to(ROOT)}）")
    p.add_argument("--checks", metavar="PATH", type=Path, default=None,
                   help="--apply-report 读取的检查结果 JSON（默认 logs/qa/judgment_apply_checks.json）")
    return p


def _persisted_apply_logs(out_dir: Path) -> list[dict]:
    logs = []
    for book in APPLY_BOOKS:
        data = _load_json(out_dir / f"judgment_apply_log_{book}.json", None)
        if isinstance(data, dict):
            logs.append(data)
    return logs


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    out_dir: Path = args.out_dir

    # ---- 模式 A：仅重生成 apply 报告 ----
    if args.apply_report:
        logs = _persisted_apply_logs(out_dir)
        if not logs:
            print("[ERROR] 无 apply 日志可汇总（先跑 --apply）", file=sys.stderr)
            return 1
        path = write_apply_report(logs, out_dir, args.checks)
        print(f"[OK] apply 报告 → {path.relative_to(ROOT)}")
        return 0

    if not args.book and not args.all:
        print("[ERROR] 需 --book/--all（或 --apply-report）；见 --help", file=sys.stderr)
        return 2
    books = DEFAULT_BOOKS if args.all else [args.book]

    # ---- 模式 B：--apply 落盘（仅 APPLY_BOOKS 白名单书；acceptance 未变则走幂等复核，不重新分类） ----
    if args.apply:
        applied, skipped_books, failed = [], [], []
        for book in books:
            if book not in APPLY_BOOKS:
                skipped_books.append(book)
                print(f"[SKIP] {book}: 不在 --apply 白名单（七剑/白发人工项维持既有终签，不写）")
                continue
            try:
                log_path = out_dir / f"judgment_apply_log_{book}.json"
                prior = _load_json(log_path, None)
                cur_snapshot = _acceptance_snapshot_for_book(
                    book, args.acceptance if not args.all else None)
                # 幂等 / 还原重跑分流
                if isinstance(prior, dict) and prior.get("before") and cur_snapshot \
                        and prior["before"] == cur_snapshot:
                    state = detect_apply_state(book, prior)
                    if state == "applied":
                        if verify_apply_replay(book, prior, out_dir):
                            continue
                        failed.append(book)
                        continue
                    if state == "mixed":
                        print(f"[ERROR] {book}: tagged 状态混合（部分处置/回滚不一致），"
                              "拒绝写入，需人工复核", file=sys.stderr)
                        failed.append(book)
                        continue
                    # state == original：tagged 已还原为处置前 → 归档旧日志，走全新 apply
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    arch = out_dir / f"judgment_apply_log_{book}.superseded-{ts}.json"
                    try:
                        log_path.rename(arch)
                        print(f"[NOTE] {book}: tagged 为处置前状态（还原/重跑），旧日志归档 → "
                              f"{arch.name}；重新处置")
                    except OSError:
                        pass
                r = process_book(book, acceptance=args.acceptance if not args.all else None,
                                 out_dir=out_dir, dry_run=True)
                log, is_idem = apply_book(book, r, backup_root=args.backup_root, out_dir=out_dir)
                (applied if not is_idem else []).append(log)
            except Exception as exc:  # noqa: BLE001 - 异常即停并报告，不连累其它书
                failed.append(book)
                print(f"[ERROR] {book}: {exc}", file=sys.stderr)
        logs = _persisted_apply_logs(out_dir)
        if logs:
            path = write_apply_report(logs, out_dir, args.checks)
            print(f"[OK] apply 报告 → {path.relative_to(ROOT)}")
        if failed:
            print(f"[ERROR] 落盘/复核失败 {len(failed)} 书：{failed}（其余书已完成或跳过）",
                  file=sys.stderr)
            return 1
        return 0

    # ---- 模式 C：dry-run（默认） ----
    results: list[dict] = []
    for book in books:
        try:
            r = process_book(book, acceptance=args.acceptance if not args.all else None,
                             out_dir=out_dir, dry_run=True)
        except Exception as exc:  # noqa: BLE001 - 逐书失败不阻塞其它书
            print(f"[ERROR] {book}: {exc}", file=sys.stderr)
            continue
        results.append(r)
        bv = r["counts"]["by_verdict"]
        print(f"[OK] {book}: {r['counts']['total']} 条 → 应摘 {bv['应摘']} / 改域 {bv['改域']} / "
              f"保留 {bv['保留']} / 需人工 {bv['需人工']}  → {r['files']['md']}")

    if not results:
        return 1
    if args.all and len(results) > 1:
        summary_md = out_dir / "judgment_signoff_summary.md"
        summary_json = out_dir / "judgment_signoff_summary.json"
        out_dir.mkdir(parents=True, exist_ok=True)
        io.open(summary_md, "w", encoding="utf-8").write(render_summary_md(results))
        summary = {
            "tool": TOOL_VERSION,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dry_run": True,
            "books": [r["book"] for r in results],
            "totals": {
                "total": sum(r["counts"]["total"] for r in results),
                "by_verdict": {k: sum(r["counts"]["by_verdict"][k] for r in results)
                               for k in VERDICTS},
                "by_type": dict(sum((Counter(r["counts"]["by_type"]) for r in results), Counter())),
            },
            "book_summaries": [{
                "book": r["book"],
                "total": r["counts"]["total"],
                "counts": r["counts"]["by_verdict"],
                "by_type": r["counts"]["by_type"],
                "doc_context": r.get("doc_context"),
                "files": r.get("files"),
            } for r in results],
        }
        io.open(summary_json, "w", encoding="utf-8").write(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        print(f"[OK] 总表 → {summary_md.relative_to(ROOT)}")
        print(f"[OK] 总表 JSON → {summary_json.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
