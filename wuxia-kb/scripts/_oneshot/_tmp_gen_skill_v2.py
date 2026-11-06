# -*- coding: utf-8 -*-
"""调用 deepseek-v4-flash 生成 SKILL_04f 武侠版 v2 设计稿（一次性历史脚本）。

模型 32k 总窗口（输入+输出），故：
1. 参考件二（04f1 规律库 14.8k 字符）替换为忠实方法论缩写（约 2k 字符）；
2. 每轮按剩余窗口自适应 max_tokens（0.75 token/char 保守估算）；
3. finish=length 时携带"格式合同+已输出尾部"续写，最多 5 轮。
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

PROMPT_PATH = str(config.ROOT / "prompts" / "T02-武侠动词域与动词实体联动规范-提示词.md")
RAW_PATH = str(config.DIR_SKILLS / "_raw_SKILL_04f_v2_deepseek.md")
DST_PATH = str(config.DIR_SKILLS / "SKILL_04f_动词标注_v2.md")

MODEL = "deepseek-v4-flash"
CTX = 32768
TEMP = 0.3
MAX_ROUNDS = 5

REF2_DIGEST = """--- 参考件二开始（原文过长，此处为忠实缩写，方法论要点不减；编号体系与运营法照此继承）---

# SKILL 04f1 规律库（130 章实战积累）· 方法论缩写

**结构**：V0 红线 + V.1-V.9 分区（每动词域一区）+ V.5 待补标候选清单 + E 格式残留扫描。规律按编号递增追加。

**V0 红线（A70，全书铁律）**：已标注动词格式不得在反思任务中顺手迁移/修改。允许：补标、修边界、增词条；禁止：改域、改格式、批量换写法。每轮反思结束前后动词计数必须只增不减。

**整词标注（V.2/V.3 经验）**：语义黏合的复合动作整词标注、不得拆分（自杀/追杀/阬杀/国除/封禅/自立）；并列双动词各自单独标（"赐益"→赐+益）；"前置字+动词"的边界错切要修复（"自〖杀〗"→"自杀"）。

**高频多义动词分型（V.5.2，核心方法论）**：对每个高频多义词做"应标语境 vs 禁标语境"分型表（四列：语境/标注/模板/安全条件），逐词独立跑、独立验证；过半场景为名词前缀的词列入第三档"不建议批量"。

**三档补标运营法（V.5）**：扫描全书"动词后紧邻实体标注"模式统计频次→第一档高置信可批量（动词语义由宾语实体类型锁定，如"守+地名"→军事守城）/第二档多义分型受限补标/第三档不批量。执行前备份、记录基线计数、批量后核对差异数≠0 立即停止抽查。

**跨域同词边界（V.3/V.4/V.6/V.9 经验）**：同一词形跨域按宾语与语境分域（迁官=政治迁 vs 迁都=位移迁；贡礼品=政治 vs 货物=经济；封人=政治 vs 封禅=礼仪；战场败走=军事 vs 奔国=位移）；警惕盲标正则的反例事故（"所食"不问语境批量翻车）。

**死亡动词的语义分化（V.2/V.3）**：处死（刑罚域）vs 崩/薨/卒（权力更替事件域）vs 自然死亡（不标）——死亡动词按事件性质分域。

**言说动词边界（V.7）**：有明确政治/外交目的、可记载为史料的言说（谏/谋/议/说）才标；纯对话引入词（曰/言/道）不标。

**E 格式残留**：旧格式 grep 定位→分类处理→验证归零；"前置字+动词"边界错切专项扫描。

--- 参考件二结束 ---"""


def load_prompt():
    """取四反引号围栏内正文，并把参考件二原文替换为缩写版。"""
    text = io.open(PROMPT_PATH, encoding="utf-8").read()
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "````text")
    end = next(i for i, l in enumerate(lines[start + 1:], start + 1) if l.strip() == "````")
    body = "\n".join(lines[start + 1:end])
    s = body.find("--- 参考件二开始 ---")
    e = body.find("--- 参考件二结束 ---") + len("--- 参考件二结束 ---")
    return (body[:s] + REF2_DIGEST + body[e:]).strip()


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


def budget(text_chars):
    """剩余窗口 -> 本轮 max_tokens（0.75 token/char 保守估算）。"""
    return max(2048, CTX - int(text_chars * 0.75) - 1024)


def clean(text):
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def main():
    prompt = load_prompt()
    print(f"compact prompt {len(prompt)} 字", flush=True)
    full = ""
    messages = [{"role": "user", "content": prompt}]
    for rnd in range(1, MAX_ROUNDS + 1):
        mt = budget(len(prompt) if rnd == 1 else len(prompt) + len(full))
        print(f"round {rnd} max_tokens={mt} ...", flush=True)
        part, finish = call(messages, mt)
        full += part
        io.open(RAW_PATH, "w", encoding="utf-8", newline="\n").write(full)
        if finish != "length":
            break
        # 续写：合同（第 5 部分）+ 已输出尾部作锚点；上下文超限时逐步收窄
        p5 = prompt[prompt.find("第 5 部分"):]
        anchor = full if len(full) < 9000 else "（前文从略）……\n" + full[-7000:]
        cont_user = (
            "你正在写一份武侠动词标注规范设计稿（SKILL_04f 武侠版）。以下是输出格式合同与你已写出的内容结尾，"
            "请从中断处直接续写剩余章节，不要重复任何已输出内容，不要加开场白。\n\n"
            + p5 + "\n\n【你已写出的内容结尾】\n" + anchor
        )
        messages = [
            {"role": "user", "content": cont_user},
            {"role": "assistant", "content": anchor},
            {"role": "user", "content": "从中断处继续输出，不要重复。"},
        ]
        prompt = cont_user  # 下一轮按此估算输入
    full = clean(full)
    io.open(DST_PATH, "w", encoding="utf-8", newline="\n").write(full + "\n")
    print(f"saved {DST_PATH}: {full.count(chr(10)) + 1} 行, {len(full)} 字", flush=True)


if __name__ == "__main__":
    main()
