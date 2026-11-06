# -*- coding: utf-8 -*-
"""LLM 标注运行器 —— wuxia-kb 管线 LLM 契约阶段（annotate）的 API 执行件。

定位（承 docs/24 G1 收口裁定）：
  - 主模式 = 单遍 E+V 统一标注：--prompt 传 SKILL_03a §二 SYSTEM_PROMPT
    （唯一权威版，由 scripts/build_03a_fewshot.py 随种子再生成；把该节复制存为
    文本文件后传入）；
  - fallback 模式 = 两遍分层 --prompt-e/--prompt-v（prompts/A1、A2 v0）：
    仅困难章或模型对比实验使用；A1/A2 v0 中与过审种子冲突的规则已被 03a 显式
    废止（prompts/README 状态栏），不得作为规则来源。

流程：片段按段落贪心打包成 ≤max_chars 的块 → 逐块调 LLM → 保真门（ratio≥GATE，
      违规摘要警示重试一次）→ difflib 回锚三重校验（位置+长度+内容，失败丢弃，
      唯一命中 salvage）→ 拼装全文 → 剥标完整性校验。
符号纪律：令牌解析/剥标一律走 symbols（P2 修复：原本地 TOKEN_RE 缺 〘〙 修辞层，
      且与 parse_token/strip_markup 语义重复）。
密钥纪律：一律经 api_config 加载（P1 修复：env 优先，其次 .api_config.json，
      均不入代码库）。
输出编码：控制台走 TextIOWrapper（scripts/README 约定 6）。

用法：
  # 单遍主模式（推荐；SKILL_03a SYSTEM_PROMPT）
  python annotate_llm.py --fragment <片段> --prompt <system_prompt.txt> \
      --out-prefix <前缀> [--model deepseek-v4-flash] [--max-chars 700]
  # 两遍 fallback（A1 实体层 → A2 动词层；xval 交叉校验协议用此形态）
  python annotate_llm.py --fragment <片段> --prompt-e <A1文件> --prompt-v <A2文件> \
      --out-prefix <前缀> [--model ...]

产物：<out-prefix>.EV.md（单遍）或 .E.md/.EV.md（两遍）+ .report.txt。
"""
import argparse
import difflib
import io
import json
import re
import sys
import time
from pathlib import Path

import requests

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config      # noqa: E402  （取 api_config 配置文件位置）
import symbols     # noqa: E402  （令牌正则/解析/剥标唯一来源）
import api_config  # noqa: E402  （API 凭据外部加载）

GATE = 0.98


def call(model, system, user):
    if model.startswith("z-ai/") or "nim" in model.lower():
        return call_nim(model, system, user)
    if "amd" in model.lower() or model in ("DeepSeek-V4-Flash", "Qwen3.8-Flash-Next", "Qwen3.8-27B", "GLM-5.3-Flash"):
        return call_amd(model, system, user)
    payload = {"model": model, "temperature": 0.1, "top_p": 0.8, "max_tokens": 8000,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": "以下是需要标注的正文。只输出标注后的全文，除插入标记外一字不改：\n\n" + user}]}
    headers = {"Content-Type": "application/json",
               "CF-Access-Client-Id": api_config.get("polylink", "cf_id"),
               "CF-Access-Client-Secret": api_config.get("polylink", "cf_secret"),
               "Authorization": "Bearer " + api_config.get("polylink", "key")}
    for attempt in range(1, 4):
        t0 = time.time()
        try:
            r = requests.post(api_config.get("polylink", "url"), headers=headers,
                              json=payload, timeout=(60, 600))
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:150]}")
            txt = r.json()["choices"][0]["message"]["content"]
            if "</think>" in txt:
                txt = txt.split("</think>", 1)[1]
            txt = txt.strip()
            if txt.startswith("```"):
                txt = re.sub(r"^```[a-z]*\n|\n```$", "", txt)
            print(f"    API ok {time.time()-t0:.0f}s {len(txt)} 字", flush=True)
            return txt
        except Exception as e:  # noqa: BLE001
            print(f"    attempt {attempt} failed: {e}", flush=True)
            time.sleep(5 * attempt)
    raise RuntimeError("API 重试耗尽")


def call_amd(model, system, user):
    payload = {"model": model, "temperature": 0.1, "top_p": 0.8, "max_tokens": 16000,
               "stream": True,
               "chat_template_kwargs": {"enable_thinking": False},
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": "以下是需要标注的正文。只输出标注后的全文，除插入标记外一字不改：\n\n" + user}]}
    headers = {"Authorization": "Bearer " + api_config.get("amd", "key"),
               "Content-Type": "application/json"}
    for attempt in range(1, 4):
        t0 = time.time()
        try:
            r = requests.post(api_config.get("amd", "url"), headers=headers, json=payload,
                              timeout=(60, 600), stream=True)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:150]}")
            parts = []
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)["choices"][0]
                    delta = chunk.get("delta", {})
                    c = delta.get("content") or ""
                    if c:
                        parts.append(c)
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass
            txt = "".join(parts)
            if "</think>" in txt:
                txt = txt.split("</think>", 1)[1]
            txt = txt.strip()
            if txt.startswith("```"):
                txt = re.sub(r"^```[a-z]*\n|\n```$", "", txt)
            print(f"    AMD ok {time.time()-t0:.0f}s {len(txt)} 字", flush=True)
            return txt
        except Exception as e:
            elapsed = time.time() - t0
            print(f"    attempt {attempt} failed ({elapsed:.0f}s): {e}", flush=True)
            time.sleep(5 * attempt)
    raise RuntimeError("AMD 重试耗尽")


def call_nim(model, system, user):
    payload = {"model": model, "temperature": 0.1, "top_p": 0.8, "max_tokens": 8000,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": "以下是需要标注的正文。只输出标注后的全文，除插入标记外一字不改：\n\n" + user}]}
    headers = {"Authorization": "Bearer " + api_config.get("nim", "key"),
               "Content-Type": "application/json"}
    for attempt in range(1, 8):
        t0 = time.time()
        try:
            r = requests.post(api_config.get("nim", "url"), headers=headers, json=payload,
                              timeout=(60, 600))
            if r.status_code == 429:
                wait = min(30, 8 * attempt)
                print(f"    429 限流，等待 {wait}s (attempt {attempt})", flush=True)
                time.sleep(wait)
                continue
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:150]}")
            txt = r.json()["choices"][0]["message"]["content"]
            if "</think>" in txt:
                txt = txt.split("</think>", 1)[1]
            txt = txt.strip()
            if txt.startswith("```"):
                txt = re.sub(r"^```[a-z]*\n|\n```$", "", txt)
            print(f"    NIM ok {time.time()-t0:.0f}s {len(txt)} 字", flush=True)
            return txt
        except Exception as e:
            print(f"    attempt {attempt} failed: {e}", flush=True)
            time.sleep(10)
    raise RuntimeError("NIM 重试耗尽")


def surface(tok):
    """令牌 → 显示串（管道前），语义走 symbols.parse_token。

    解析失败分支兜底：括号不配对时 parse_token 原样返回——按三层括号手工剥；
    括号完好但类型码不在定版内时仍按 body 取显示串（回锚按字面锚定）。
    """
    _layer, _code, body, display, _note, err = symbols.parse_token(tok)
    if err is None:
        return display
    if err == "令牌括号不配对或类型未知":
        for open_b, close_b in symbols.BRACKETS.values():
            if len(tok) >= 2 and tok.startswith(open_b) and tok.endswith(close_b):
                rest = tok[1:-1]
                return rest[1:].split(symbols.PIPE, 1)[0] if symbols.PIPE in rest[1:] else rest[1:]
        return tok
    rest = body[1:]
    return rest.split(symbols.PIPE, 1)[0] if symbols.PIPE in rest else rest


def strip_marks(text):
    return symbols.strip_markup(text)


def tokens_of(text):
    return [(m.group(0), m.start(), m.end()) for m in symbols.TOKEN_RE.finditer(text)]


def split_chunks(text, max_chars):
    """按段落（[N] 块）贪心打包成 ≤max_chars 的块。段落=非空行组。"""
    units, cur = [], []
    for line in text.split("\n"):
        if line.strip():
            cur.append(line)
        elif cur:
            units.append("\n".join(cur))
            cur = []
    if cur:
        units.append("\n".join(cur))
    chunks, buf = [], ""
    for u in units:
        cand = (buf + "\n\n" + u) if buf else u
        if len(cand) <= max_chars or not buf:
            buf = cand
        else:
            chunks.append(buf)
            buf = u
    if buf:
        chunks.append(buf)
    return chunks


def reanchor(original, model_out):
    """把模型令牌回锚到 original：位置映射 + 长度 + 内容三重校验，不过则丢弃。"""
    plain_m = strip_marks(model_out)
    sm = difflib.SequenceMatcher(None, plain_m, original, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size > 0]

    def m2o(pos):
        for b in blocks:
            if b.a <= pos < b.a + b.size:
                return b.b + (pos - b.a)
        return None

    out = list(original)
    marks, dropped = [], []
    for tok, s, e in tokens_of(model_out):
        a, b = m2o(s), m2o(e)
        if a is None or b is None or b - a != e - s or original[a:b] != plain_m[s:e]:
            dropped.append((tok, plain_m[s:e][:20] if a is not None else "?"))
            continue
        marks.append((a, b, tok))
    occupied = []
    for a, b, tok in sorted(marks, key=lambda x: x[0], reverse=True):
        if any(not (b <= c or a >= d) for c, d in occupied):
            dropped.append((tok, "与已插标记区间重叠"))
            continue
        out[a:b] = [tok]
        occupied.append((a, b))
    # salvage：映射失败令牌按 surface 在原文唯一串查找锚定（誊写度高时几乎必中）
    for tok, _why in dropped[:]:
        sv = surface(tok)
        hits = [m.start() for m in re.finditer(re.escape(sv), original)]
        if len(hits) == 1 and not any(not (hits[0] + len(sv) <= c or hits[0] >= d)
                                      for c, d in occupied):
            a, b = hits[0], hits[0] + len(sv)
            out[a:b] = [tok]
            occupied.append((a, b))
            dropped = [x for x in dropped if x[0] != tok]
    return "".join(out), dropped


def annotate_chunk(model, prompt, chunk, stage, report):
    """单块单遍：调用+回锚+保真门。返回标注文本；两次未过返回 None。"""
    base = strip_marks(chunk)
    user_try = chunk
    for attempt in range(1, 3):
        raw = call(model, prompt, user_try)
        sm = difflib.SequenceMatcher(None, base, strip_marks(raw), autojunk=False)
        ratio = sm.ratio()
        print(f"    [{stage}] 保真度 {ratio:.4f}", flush=True)
        if ratio >= GATE:
            anchored, dropped = reanchor(chunk, raw)
            if dropped:
                report.append(f"  - [{stage}] 回锚丢弃 {len(dropped)}："
                              + "；".join(f"{t}({why[:18]})" for t, why in dropped[:4]))
            return anchored
        diffs = [f"基线[{t[1]}:{t[2]}]={base[t[1]:t[2]][:22]!r}→{strip_marks(raw)[t[3]:t[4]][:22]!r}"
                 for t in sm.get_opcodes() if t[0] != "equal"][:2]
        report.append(f"  - [{stage}] 第 {attempt} 次保真度 {ratio:.4f} < {GATE}，拒收。违规：" + "；".join(diffs))
        user_try = (chunk + "\n\n【上一稿违规警示】你上一稿改动了原文（如：" + "；".join(diffs) +
                    "）。逐字誊写是铁律：除插入标记外一字不动，包括每一个标点与虚词。重新输出完整标注稿。")
    return None


def main():
    ap = argparse.ArgumentParser(description="LLM 标注运行器（单遍主模式 / 两遍 fallback）")
    ap.add_argument("--fragment", required=True)
    ap.add_argument("--prompt", default=None,
                    help="单遍主模式 SYSTEM_PROMPT（SKILL_03a §二随种子再生成产物存为文本文件）")
    ap.add_argument("--prompt-e", default=None,
                    help="fallback 两遍 Pass1：A1 实体层（prompts/A1-实体层标注提示词-v0.md）")
    ap.add_argument("--prompt-v", default=None,
                    help="fallback 两遍 Pass2：A2 动词层（prompts/A2-动词层标注提示词-v0.md）")
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--max-chars", type=int, default=700)
    a = ap.parse_args()
    single = bool(a.prompt)
    two_pass = bool(a.prompt_e or a.prompt_v)
    if single == two_pass:
        ap.error("单遍与两遍二选一：--prompt（主模式）或 --prompt-e + --prompt-v（fallback）")
    if two_pass and not (a.prompt_e and a.prompt_v):
        ap.error("两遍 fallback 需要 --prompt-e 与 --prompt-v 同时提供")

    frag = io.open(a.fragment, encoding="utf-8").read()
    prompt_single = io.open(a.prompt, encoding="utf-8").read() if single else None
    pe = io.open(a.prompt_e, encoding="utf-8").read() if a.prompt_e else None
    pv = io.open(a.prompt_v, encoding="utf-8").read() if a.prompt_v else None
    chunks = split_chunks(frag, a.max_chars)
    mode = "single(03a主模式)" if single else "two-pass(A1/A2 fallback)"
    report = [f"# 分块标注运行报告 · {a.model} · max_chars={a.max_chars} · mode={mode}",
              f"- 片段 {len(frag)} 字 → {len(chunks)} 块", ""]
    print(f"片段 {len(frag)} 字 → {len(chunks)} 块（{mode}）", flush=True)

    e_full = ev_full = None
    ok_e = None
    if single:
        parts, s_fail = [], []
        for i, ch in enumerate(chunks, 1):
            print(f"  [S {i}/{len(chunks)}] {len(ch)} 字", flush=True)
            r = annotate_chunk(a.model, prompt_single, ch, f"S{i}", report)
            if r is None:
                s_fail.append(i)
                parts.append(ch)       # 保底：未过块保留原文（报告留痕，人工补）
            else:
                parts.append(r)
        ev_full = "\n\n".join(parts)
        report += ["", "## 汇总",
                   f"- EV 完整性 {'PASS' if strip_marks(ev_full) == strip_marks(frag) else 'FAIL'}；"
                   f"令牌 {len(tokens_of(ev_full))}",
                   f"- 保真门未过块：S={s_fail or '无'}"]
    else:
        e_parts, e_fail = [], []
        for i, ch in enumerate(chunks, 1):
            print(f"  [E {i}/{len(chunks)}] {len(ch)} 字", flush=True)
            r = annotate_chunk(a.model, pe, ch, f"E{i}", report)
            if r is None:
                e_fail.append(i)
                e_parts.append(ch)     # 保底：未过块保留原文（报告留痕，人工补）
            else:
                e_parts.append(r)
        e_full = "\n\n".join(e_parts)

        v_parts, v_fail = [], []
        for i, ec in enumerate(e_parts, 1):   # E 产物块与原文块一一对应，无需重新定位
            print(f"  [V {i}/{len(chunks)}] {len(ec)} 字", flush=True)
            r = annotate_chunk(a.model, pv, ec, f"V{i}", report)
            if r is None:
                v_fail.append(i)
                v_parts.append(ec)
            else:
                v_parts.append(r)
        ev_full = "\n\n".join(v_parts)

        ok_e = strip_marks(e_full) == strip_marks(frag)
        n_e, n_v = len(tokens_of(e_full)), len(tokens_of(ev_full))
        report += ["", "## 汇总",
                   f"- E 完整性 {'PASS' if ok_e else 'FAIL'}；令牌 {n_e}",
                   f"- EV 完整性 {'PASS' if strip_marks(ev_full) == strip_marks(frag) else 'FAIL'}；"
                   f"令牌 {n_v}（动词 {n_v - n_e}）",
                   f"- 保真门未过块：E={e_fail or '无'} V={v_fail or '无'}"]

    counts = {}
    for tok, _, _ in tokens_of(ev_full):
        counts[tok[0]] = counts.get(tok[0], 0) + 1
    report.append("- 令牌分布：```text\n" + json.dumps(counts, ensure_ascii=False, indent=1) + "\n```")

    if not single:
        io.open(a.out_prefix + ".E.md", "w", encoding="utf-8", newline="\n").write(e_full + "\n")
    io.open(a.out_prefix + ".EV.md", "w", encoding="utf-8", newline="\n").write(ev_full + "\n")
    io.open(a.out_prefix + ".report.txt", "w", encoding="utf-8", newline="\n").write("\n".join(report) + "\n")
    print(f"E 完整性 {ok_e if ok_e is not None else '（单遍无独立 E 产物）'} | EV 完整性 "
          f"{strip_marks(ev_full) == strip_marks(frag)}", flush=True)
    print(f"saved {a.out_prefix}.EV.md" + ("" if single else " / .E.md") + " / .report.txt", flush=True)


if __name__ == "__main__":
    main()
