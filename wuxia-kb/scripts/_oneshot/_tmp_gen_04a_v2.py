# -*- coding: utf-8 -*-
"""调用 deepseek-v4-flash 分三段生成 SKILL_04a 武侠版 v2 设计稿（一次性任务脚本）。

同一完整提示词投喂三次，每次限定输出章节范围；第 1 次调用要求在文末追加
【衔接摘要】（生成后剥离，不入正文），供第 2/3 次调用沿用定版结论，保证跨段一致。
"""
import io
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # wuxia-kb/scripts
import api_config  # noqa: E402
import config      # noqa: E402

# P1 修复（2026-11-03）：凭据经 api_config 外部加载；路径接 config
# （原 ROOT 按脚本所在目录推导，脚本迁入 scripts/_oneshot/ 后已失效）。
PROMPT_PATH = str(config.ROOT / "prompts" / "T03-武侠事件类型学-提示词.md")
RAW_DIR = str(config.DIR_SKILLS / "_raw_04a_v2")
DST_PATH = str(config.DIR_SKILLS / "SKILL_04a_事件识别_v2.md")
MODEL = "deepseek-v4-flash"
MAX_TOKENS = 10000
TEMP = 0.3

SPLIT_NOTE = """

════════════════════════════════════════════════════
【生成方式说明·本次调用】
上文完整提示词保持不变。因单次输出长度限制，本文档由同一提示词分三次调用接力生成，本次为第 {n}/3 次。
{scope}
"""

SCOPE_1 = """【本次输出范围】只输出：YAML frontmatter、第一章 技能定位、第二章 事件的定义与粒度、第三章 事件类型体系、第四章 群体事件处理。
- 文档以 `---` frontmatter 开始，不要任何开场白；
- 第三章必须完成工单 Q1 全部裁决（12-15 类定版表 + 每类定义/判定信号/锚点动词域组合/相邻边界对照例 + 主类型归属优先级 + 泛类型裁决 + 复合事件分层）；
- 输出至第四章末尾即停止，不要输出第五章及之后的任何内容；
- 然后在最末尾追加以下结构的一段（系统会剥离，不属于文档正文）：

【衔接摘要——供后续批次调用沿用，不属于文档正文】
- 事件类型枚举定版：<逐类列出最终类型名>
- 主类型归属优先级：<结论>
- 粒度判据：<三档判据与"比武打三页"拆分判据的结论>
- 群体事件记录：<参与者分级记录规则结论>
- 复合事件：<父子结构与字段结论>
- 其他影响后续章节的裁决：<逐条列出>"""

SCOPE_2 = """【本次输出范围】只输出：第五章 事件字段体系、第六章 战斗事件专项 Schema、第七章 叙述可靠性与重复叙述、第八章 事件 ID 与跨回跨书结构、第九章 事件识别工作流程。
- 直接从"## 五、"章标题开始输出；不要重复 frontmatter 与第一至四章，不要开场白、不要目录；
- 第五章字段总表必须以 01g §2.2.3a 完整事件最低字段为底座（字段可增不可减），并在表中标注每字段来源（自 01g 迁入 / 本文件新增）；
- 输出至第九章末尾即停止，不要输出第十章及之后内容。"""

SCOPE_3 = """【本次输出范围】只输出：第十章 Agent 提示词（武侠版）、第十一章 错误模式库（首批）、第十二章 输出格式与质量标准、第十三章 下游消费契约、第十四章 FAQ、第十五章 相关文档、附录 A · 与史记 04a/05e 差异对照表、附录 B · 待拍板决策清单。
- 直接从"## 十、"章标题开始输出；不要重复前九章，不要开场白；
- SYSTEM_PROMPT 三段（SYSTEM/TASK/REFLECTION）中每种期望行为至少配 1 个真实 few-shot 示例；
- FAQ ≥12 问且引用前文裁决；附录 A 须含"§2.2.3a 字段自 01g 迁入"的对齐说明；附录 B 收录全部待拍板项（允许为空但须声明"全部已定版"）；
- 输出至附录 B 末尾即收束全文。"""


def load_prompt():
    text = io.open(PROMPT_PATH, encoding="utf-8").read()
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "````text")
    end = next(i for i, l in enumerate(lines[start + 1:], start + 1) if l.strip() == "````")
    return "\n".join(lines[start + 1:end]).strip()


def call(user_content):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": user_content}],
        "temperature": TEMP,
        "max_tokens": MAX_TOKENS,
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
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
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


def clean(text):
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def extract_summary(text):
    """取【衔接摘要】段内容并从正文中剥离。"""
    idx = text.find("【衔接摘要")
    if idx < 0:
        return text, ""
    return text[:idx].rstrip() + "\n", text[idx:].strip()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(RAW_DIR, exist_ok=True)
    prompt = load_prompt()
    print(f"prompt {len(prompt)} 字 model={MODEL}", flush=True)

    parts = []
    summary = ""
    for n, scope in ((1, SCOPE_1), (2, SCOPE_2), (3, SCOPE_3)):
        raw_path = os.path.join(RAW_DIR, f"part{n}.md")
        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 1000:
            with open(raw_path, encoding="utf-8") as f:
                raw = f.read()
            print(f"part {n}: 复用已有 raw（断点续跑）", flush=True)
        else:
            if n == 1:
                user = prompt + SPLIT_NOTE.format(n=n, scope=scope)
            else:
                user = (prompt + SPLIT_NOTE.format(n=n, scope=scope)
                        + "\n\n【前序批次定版结论摘要（必须沿用，不得改名、不得推翻）】\n"
                        + summary)
            raw, finish = call(user)
            if finish == "length":
                print(f"  警告 part {n} 因长度截断（finish=length），续补一轮", flush=True)
                extra = ("\n\n继续输出剩余内容：从中断处直接接着写，不要重复任何已输出的内容，"
                         "不要加开场白或结束语。若已到本次输出范围的末尾则停止。")
                part2, _ = call(raw + extra)
                raw = raw + part2
            with open(raw_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(raw)
        raw = clean(raw)
        if n == 1:
            body, summary = extract_summary(raw)
            print(f"part 1 正文 {len(body)} 字，衔接摘要 {len(summary)} 字", flush=True)
            parts.append(body)
            io.open(os.path.join(RAW_DIR, "handoff_summary.txt"), "w",
                    encoding="utf-8", newline="\n").write(summary)
        else:
            parts.append(raw)

    full = "\n\n".join(p.rstrip() + "\n" for p in parts)
    io.open(DST_PATH, "w", encoding="utf-8", newline="\n").write(full)
    print(f"saved {DST_PATH}: {full.count(chr(10)) + 1} 行, {len(full)} 字", flush=True)


if __name__ == "__main__":
    main()
