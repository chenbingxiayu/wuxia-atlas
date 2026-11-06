# -*- coding: utf-8 -*-
"""通用：以预算自适应方式调用 deepseek-v4-flash 生成设计稿 v2（一次性历史脚本）。

用法：python _tmp_gen_v2.py --prompt <compact提示词文件> --dst <输出md> [--tag 标签]
compact 文件 = 已完成上下文适配的最终提示词（四反引号围栏内取正文）。
P1 修复（2026-11-03）：API 凭据改经 api_config 外部加载，不再硬编码。
"""
import argparse
import io
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # wuxia-kb/scripts
import api_config  # noqa: E402

MODEL = "deepseek-v4-flash"
CTX = 32768
TEMP = 0.3
MAX_ROUNDS = 5


def load_prompt(path):
    text = io.open(path, encoding="utf-8").read()
    lines = text.split("\n")
    marks = [i for i, l in enumerate(lines) if l.strip().startswith("````")]
    if len(marks) >= 2:
        return "\n".join(lines[marks[0] + 1:marks[1]]).strip()
    return text.strip()


def call(messages, max_tokens):
    payload = {
        "model": MODEL, "messages": messages, "temperature": TEMP,
        "max_tokens": max_tokens, "stream": True,
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
                if chunk.get("delta", {}).get("content"):
                    parts.append(chunk["delta"]["content"])
                if chunk.get("finish_reason"):
                    finish = chunk["finish_reason"]
            if not parts:
                raise RuntimeError("空响应")
            print(f"  ok {time.time()-t0:.0f}s {sum(map(len, parts))} 字 finish={finish}", flush=True)
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--dst", required=True)
    a = ap.parse_args()
    prompt = load_prompt(a.prompt)
    print(f"prompt {len(prompt)} 字", flush=True)
    full = ""
    messages = [{"role": "user", "content": prompt}]
    cur = prompt
    for rnd in range(1, MAX_ROUNDS + 1):
        mt = budget(len(cur) if rnd == 1 else len(cur) + len(full))
        print(f"round {rnd} max_tokens={mt} ...", flush=True)
        part, finish = call(messages, mt)
        full += part
        io.open(a.dst + ".raw", "w", encoding="utf-8", newline="\n").write(full)
        if finish != "length":
            break
        p5 = cur[cur.find("第 5 部分"):] if "第 5 部分" in cur else ""
        anchor = full if len(full) < 9000 else "（前文从略）……\n" + full[-7000:]
        cur = ("你正在续写一份武侠标注体系设计稿。以下是输出格式合同与你已写出的内容结尾，"
               "请从中断处直接续写剩余章节，不要重复任何已输出内容，不要加开场白。\n\n"
               + p5 + "\n\n【你已写出的内容结尾】\n" + anchor)
        messages = [
            {"role": "user", "content": cur},
            {"role": "assistant", "content": anchor},
            {"role": "user", "content": "从中断处继续输出，不要重复。"},
        ]
    full = clean(full)
    io.open(a.dst, "w", encoding="utf-8", newline="\n").write(full + "\n")
    print(f"saved {a.dst}: {full.count(chr(10)) + 1} 行, {len(full)} 字", flush=True)


if __name__ == "__main__":
    main()
