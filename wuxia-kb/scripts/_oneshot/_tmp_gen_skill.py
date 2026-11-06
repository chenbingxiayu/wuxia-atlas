# -*- coding: utf-8 -*-
"""通用：调用外部 API 生成设计稿（一次性任务脚本，参数化版本）。

用法：
  python _tmp_gen_skill.py --prompt <提示词文件> --dst <输出md> [--raw <中间存档>] [--model deepseek-v4-flash]
P1 修复（2026-11-03）：API 凭据改经 api_config 外部加载，不再硬编码。
"""
import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # wuxia-kb/scripts
import api_config  # noqa: E402

MAX_TOKENS = 32768
TEMP = 0.3
MAX_ROUNDS = 6


def load_prompt(path):
    """取四反引号围栏内的提示词正文。"""
    text = io.open(path, encoding="utf-8").read()
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == "````text")
    end = next(i for i, l in enumerate(lines[start + 1:], start + 1) if l.strip() == "````")
    return "\n".join(lines[start + 1:end]).strip()


def call(messages, model):
    payload = {
        "model": model,
        "messages": messages,
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
            print(f"  round ok {time.time()-t0:.0f}s {sum(map(len, parts))} 字 finish={finish}",
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", required=True)
    p.add_argument("--dst", required=True)
    p.add_argument("--raw", default=None)
    p.add_argument("--model", default="deepseek-v4-flash")
    a = p.parse_args()
    if a.raw is None:
        a.raw = a.dst + ".raw"
    prompt = load_prompt(a.prompt)
    print(f"prompt {len(prompt)} 字 model={a.model}", flush=True)
    messages = [{"role": "user", "content": prompt}]
    full = ""
    for rnd in range(1, MAX_ROUNDS + 1):
        print(f"round {rnd} ...", flush=True)
        part, finish = call(messages, a.model)
        full += part
        io.open(a.raw, "w", encoding="utf-8", newline="\n").write(full)
        if finish != "length":
            break
        messages = messages + [
            {"role": "assistant", "content": part},
            {"role": "user", "content": "继续输出剩余内容：从中断处直接接着写，不要重复任何已输出的内容，不要加开场白或结束语。"},
        ]
    full = clean(full)
    io.open(a.dst, "w", encoding="utf-8", newline="\n").write(full + "\n")
    print(f"saved {a.dst}: {full.count(chr(10)) + 1} 行, {len(full)} 字", flush=True)


if __name__ == "__main__":
    main()
