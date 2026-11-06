# -*- coding: utf-8 -*-
"""调用 deepseek-v4-flash 生成 SKILL_02a/02b 武侠版 v2（T04 上下文适配版，一次性历史脚本）。

模型 32k 总窗口：参考件一（02a）、二（02b）、三（02a1）、五（02b2）替换为忠实缩写，
参考件四（02b1 韵文识别规则）保留全文（Q3 合成决策树的直接对象）。
预算自适应 max_tokens（0.67 token/char 估算）+ 截断续写。
P1 修复（2026-11-03）：凭据经 api_config 外部加载；路径接 config
（原 ROOT 按脚本所在目录推导，脚本迁入 scripts/_oneshot/ 后已失效）。
"""
import io
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # wuxia-kb/scripts
import api_config  # noqa: E402
import config      # noqa: E402

SCAFFOLD = str(config.ROOT / "prompts" / "T04-武侠章回结构与韵文检测-提示词.md")
DST = str(config.DIR_SKILLS / "SKILL_02a_02b_章回结构与韵文处理_v2.md")
RAW = str(config.DIR_SKILLS / "_raw_02ab_v2.md")

MODEL = "deepseek-v4-flash"
CTX = 32768
TEMP = 0.3
MAX_ROUNDS = 5

REF_02A_DIGEST = """--- 参考件一开始（原文过长，此处为忠实缩写，方法论要点不减）---

# SKILL 02a: 古籍章节切分与编号 — Purple Numbers 与语义分段（缩写）

**三层结构**：篇章（独立文件，三位编号）→ 小节（语义段落组，##/###）→ 段落（带 PN 的原子单元）。

**PN（Purple Numbers）**：每段唯一、永久、不可变标识符，格式 `[0]` 篇名 / `[1]` / `[1.1]` / `[1.1.1]`（最多三级）。一旦分配永不更改；外部引用（实体索引、事件索引、跨文档引用 `092_淮阴侯列传#pn-3.1`）全部依赖它；插入新段落用子编号，不改已有编号。

**篇章拆分**：`{三位编号}_{篇名}.txt`，按体裁关键词切分；编号补零；保持原文完整。

**段落修复（误分段合并）四条**：行末有句末标点不合并；当前行或下一行为空不合并；当前行 <10 字不合并（可能是标题）；其余合并（行末无句末标点多为误分段）。

**编号规则**：
- 父子关系：必须有父才有子；多段 section 需独立成行的父编号 `[N]`；**空父段落允许**（容器）。
- 连续性：同层级不得跳号（[1]→[3] 错误）；lint 检查。
- 何时用子编号：段落超 500 字按语义拆；多人对话每句一项（`- [12.1] @尧@曰：…`）；短列表不拆、长列表（完整句/对话）拆；引用块 `>` 不独立编号。
- 篇名固定 `[0]`：`# [0] 五帝本纪`。
- 表格行用 `[rN]`（十表专用，章内递增，渲染锚点 #pn-rN）。
- 位置：`[编号] + 空格 + 内容`；列表项 `- [N.M] 内容`。

**语义小节**：
- `# [0] 篇名`（一级，每篇唯一）/ `##`（二级）/ `###`（三级）。
- **二级三级标题不应包含段落编号**（`## [6] 论法家` 错误）；标题必须在顶级段落之前（在子段落前错误，需移位或插入空父段）。
- 两种格式：A 标题带编号 `## [1] 早年困顿`（锚点取标题）；B 标题不带编号 `## 项羽早年`（锚点取节内第一段）。
- 体裁定制：本纪按帝王、世家按世代、列传按人生阶段/人物、书按制度主题。
- 每篇小节 5-15 个（sections_data.json：anchor+title，title 去实体标记）；超 20 段的小节应拆分。
- 自动小节生成（每 10 段启发式标题）仅是建议，准确率约 60%，必须人工审核。

**lint_purple_numbers.py 六检查项**：编号格式（禁字母/中文）、同层连续性、父子关系、标题编号、重复编号、篇名 `[0]`。配套修复脚本（缺父插入、标题去号、分节位置）。

**特殊情况**：赞（太史公评论）多行合并为单编号，各句换行不分段；对话拆分只改物理换行，**不得改变原文任何字符（含引号层级）**；术语解释段（"右XX书"）独立编号。

**超长小节参数**：MAX_SECTIONS_PER_CHAPTER=15、MIN_PARAGRAPHS_PER_SECTION=3、MAX_PARAGRAPHS_PER_SECTION=20。

**经验教训**：编号是基础设施（最早期确定且不可变）；语义分段优于机械分段；体裁决定结构；自动生成只是起点；小节数量克制（5-15）；两种标题格式都要支持；锚点格式统一 `#pn-{number}` 贯穿全系统；**先切分后标注**（顺序反了每次改编号都要重关联实体）。

--- 参考件一结束 ---"""

REF_02B_DIGEST = """--- 参考件二开始（原文过长，此处为忠实缩写，方法论要点不减）---

# SKILL 02b: 区块与韵文处理 — Fenced Div 语义块与赞体韵文（缩写）

**问题**：篇末"太史公曰"（散文评论）与"赞"（四言韵文）需用 Pandoc Fenced Div 标注为语义块，使渲染器可应用不同样式、韵文保持硬换行、标签显示为 tooltip。

**语法**：`::: 标签名` 开头（中文语义标签），`:::` 单独一行结尾；块内内容无需前缀。

**标签类型**：太史公曰/赞/诗歌/谏言/策论/制度/传说/自定义（年表等特殊章有变体；标签可查询、可提取成专项索引——赞/诗歌/赋已实现 141 篇专项页）。

**渲染**：`::: tag` → `<div class="note-box note-{tag}" title="{tag}">`；**标签渲染为 title 属性而非 h4 标题**（不破坏文档目录）；赞/诗歌块内连续行用 `<br>` 连接，CSS `white-space: pre-line; line-height: 2.0`。

**核心规则**：
1. **区块绝不跨节**——`:::` 必须在 `##`/`###` 标题之前关闭，标题是结构边界（违者 HTML 嵌套错误）。
2. 太史公曰结构：`## 太史公论X` 标题 + `::: 太史公曰 [N] 散文 :::` + `## 赞` + `::: 赞 [N+1] 韵文 :::`。
3. 年表（整章即评论）不加包裹；太史公曰可能在开头或中间，按实际位置标。

**韵文检测（verse_score）**：
- 赞特征：四字句为主、对仗、押韵、每句带标点。
- 评分（先**清洗标注符号**——不清洗则句长虚增 2-3 倍，95% 韵文被误判散文）：按标点拆句统计句长 → 四字句占比>50% 得 0.95；3-5 字句占比>70% 得 0.80；4-7 字句占比>70% 得 0.70；均长 6-8 且方差<2.0 得 0.75（五七言诗）；均长>10 得 0.10（散文）；**阈值 >0.6 判韵文，0.4-0.6 人工确认**。
- **整组判断**（组内平均分）而非逐句——古文散文也有四字节奏（"荆王王也，由汉初定"）；3-20 行滑动窗口检测连续区块。

**韵文提取工作流五步**：深度检测（verse_score）→ 添加 ::: 赞 标记 → 排版检查（每行 8 字规范）→ 提取韵文 → 生成展示。深度挖掘曾发现 28 篇隐藏赞（97→110 篇，+29%）。

**手工标题保护**：韵文标题优先级 手工映射 > Markdown 标题 > 上下文提取（"作X赋"/"刻X石"模式）> 默认（章节名+赞）；标题必须具体化（"泰山刻石""垓下歌"，禁"本纪诗"式通用名）；同一章多个韵文需唯一 ID 锚点。

**对话分析**：直接引语 X曰"…"、嵌套引语外双内单、间接引语；对话占比列传 35-45%、本纪 30-40%。

**经验**：区块不跨节；韵文整组投票；阈值 0.6 分界；标签用 tooltip；年表不包裹；标注符号必须清洗；手工标题需保护；自动脚本后必须人工抽查（散文伪装韵文/书类章节/补注章节）。

--- 参考件二结束 ---"""

REF_02A1_DIGEST = """--- 参考件三开始（原文过长，此处为忠实缩写，方法论要点不减）---

# Purple Numbers 编号规范 · 详细（缩写）

- 多级编号 `[N]` / `[N.M]` / `[N.M.K]`；**二级 vs 三级的选择**：结构简单（每标题独立 section）用二级策略 A（每标题一个顶级号）；结构复杂（多标题归属同一逻辑大节）用三级策略 B（多标题共用顶级号，各标题为 [N.M]）。
- 单段 section：`[N] 内容`直接跟；多段：父编号独立一行 + `[N.1]` 起连续子号；三级中多段子 section 需两级父号 `[N]`、`[N.M]` 均独立成行（同一顶级 section 的不同子 section 会重复出现 `[N]` 行）。
- 无直接内容的标题（下挂的只有下级标题）不编号（二级策略）或作为分组容器（三级策略）。
- 连续性：顶级从 [1] 连续递增；子号从 [N.1] 连续递增，禁跳号。
- 特殊情况：原文章节标记符（如 ◎X）保留但不分配 PN；太史公赞作为独立 section 通常单段；"右XX书"术语段独立编号。
- 注意事项：PN 只添加标记不得修改原文字符；段落=前后空行的独立文本块；韵文（赞）作为整体编一号不按行拆。
- 验证与修复：lint_purple_numbers.py；三级转二级脚本、补父编号脚本。

--- 参考件三结束 ---"""

REF_02B2_DIGEST = """--- 参考件五开始（原文过长，此处为忠实缩写，方法论要点不减）---

# SKILL 02b2: 散文识别规则（缩写）

覆盖六类长篇非叙事散文：**诏令**（诏曰/制诏御史/制曰）、**奏疏**（上书曰/乃上疏曰/奏曰/上言曰）、**书信**（遗X书曰/报X书/与X书）、**檄文**（移檄/为檄告/谕X曰）、**策论**（对曰+长引文/献策曰；臣对君建议）、**议论**（作者名+曰+长论述；脱离情节的思辨）。

- 长度阈值 MIN_CHARS=120（纯文本去标注后），低于不收；重叠区间只保留第一个。
- 边界：论赞（太史公曰）归韵文集处理不重复收录；赋/诗歌归韵文集；短对话不收。
- 工作流三步：触发短语+H2 标题双路扫描 → 半自动 manifest（人工精选清单，自动采纳质量稳定的四类；策论只留 ≥400 字；手工补充遗漏名篇）→ 按段落区间抽取渲染。
- 段落边界：起点优先 H2/H3 标题后第一个 [N] 段，次选触发短语所在段；终点优先下一个 H2 前最后一段，次选"书奏/上览之曰"等收束标志；支持跨段子段号区间（[117]-[124.2]，含 17.99 式上界）。
- 散文集不改 tagged.md（MVP 用 manifest 段落范围），后续可选回写 ::: 块标记统一处理。

--- 参考件五结束 ---"""


def load_body():
    text = io.open(SCAFFOLD, encoding="utf-8").read()
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "````text")
    end = next(i for i, l in enumerate(lines[start + 1:], start + 1) if l.strip() == "````")
    return "\n".join(lines[start + 1:end])


def build_prompt():
    body = load_body()
    s2a = body.find("--- 参考件一开始 ---")
    e2a = body.find("--- 参考件一结束 ---") + len("--- 参考件一结束 ---")
    s2b = body.find("--- 参考件二开始 ---")
    e2b = body.find("--- 参考件二结束 ---") + len("--- 参考件二结束 ---")
    s2a1 = body.find("--- 参考件三开始 ---")
    e2a1 = body.find("--- 参考件三结束 ---") + len("--- 参考件三结束 ---")
    s2b1 = body.find("--- 参考件四开始 ---")
    e2b1 = body.find("--- 参考件四结束 ---") + len("--- 参考件四结束 ---")
    s2b2 = body.find("--- 参考件五开始 ---")
    e2b2 = body.find("--- 参考件五结束 ---") + len("--- 参考件五结束 ---")
    shiji = str(config.SHIJI_SCRIPTS.parent / "skills")   # workspace/shiji-kb/skills
    full = lambda p: io.open(shiji + "/" + p, encoding="utf-8").read().strip()
    # 替换顺序从后往前，避免位移
    out = body[:s2b2] + REF_02B2_DIGEST + body[e2b2:]
    out = out[:s2b1] + full("references/SKILL_02b1_韵文识别规则.md") + out[e2b1:]  # 全文保留
    out = out[:s2a1] + REF_02A1_DIGEST + out[e2a1:]
    out = out[:s2b] + REF_02B_DIGEST + out[e2b:]
    out = out[:s2a] + REF_02A_DIGEST + out[e2a:]
    return out.strip()


def call(messages, max_tokens):
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": TEMP,
        "max_tokens": max_tokens,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {
        "Content-Type": "application/json",
        "CF-Access-Client-Id": api_config.get("polylink", "cf_id"),
        "CF-Access-Client-Secret": api_config.get("polylink", "cf_secret"),
        "Authorization": "Bearer " + api_config.get("polylink", "key"),
    }
    last_err = None
    for attempt in range(1, 4):
        t0 = time.time()
        try:
            r = requests.post(api_config.get("polylink", "url"), headers=headers, json=payload,
                              timeout=(60, 300), stream=True)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            parts, finish = [], None
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)["choices"][0]
                delta = chunk.get("delta", {})
                if delta.get("content"):
                    parts.append(delta["content"])
                if chunk.get("finish_reason"):
                    finish = chunk["finish_reason"]
            if not parts:
                raise RuntimeError("空响应")
            print(f"  ok {time.time()-t0:.0f}s {sum(map(len, parts))} 字 finish={finish}",
                  flush=True)
            return "".join(parts), finish
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  attempt {attempt} failed: {e}", flush=True)
            time.sleep(5 * attempt)
    raise RuntimeError(f"全部重试失败: {last_err}")


def budget(chars):
    return max(2048, CTX - int(chars * 0.67) - 1024)


def clean(text):
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def main():
    prompt = build_prompt()
    print(f"compact prompt {len(prompt)} 字", flush=True)
    full = ""
    messages = [{"role": "user", "content": prompt}]
    for rnd in range(1, MAX_ROUNDS + 1):
        mt = budget(len(prompt) if rnd == 1 else len(prompt) + len(full))
        print(f"round {rnd} max_tokens={mt} ...", flush=True)
        part, finish = call(messages, mt)
        full += part
        io.open(RAW, "w", encoding="utf-8", newline="\n").write(full)
        if finish != "length":
            break
        p5 = prompt[prompt.find("第 5 部分"):]
        anchor = full if len(full) < 9000 else "（前文从略）……\n" + full[-7000:]
        cont_user = (
            "你正在写一份武侠章回结构标注规范设计稿（SKILL_02a/02b 武侠版）。以下是输出格式合同与你已写出的内容结尾，"
            "请从中断处直接续写剩余章节，不要重复任何已输出内容，不要加开场白。\n\n"
            + p5 + "\n\n【你已写出的内容结尾】\n" + anchor
        )
        messages = [
            {"role": "user", "content": cont_user},
            {"role": "assistant", "content": anchor},
            {"role": "user", "content": "从中断处继续输出，不要重复。"},
        ]
        prompt = cont_user
    full = clean(full)
    io.open(DST, "w", encoding="utf-8", newline="\n").write(full + "\n")
    print(f"saved {DST}: {full.count(chr(10)) + 1} 行, {len(full)} 字", flush=True)


if __name__ == "__main__":
    main()
