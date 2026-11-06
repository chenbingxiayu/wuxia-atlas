# -*- coding: utf-8 -*-
"""外部模型复核器（Qwen3.8-Flash-Next / AMD Radeon API）：对"金标准 vs 新标注"做独立评审。

用法：
    python scripts/qwen_review_chapter.py --book 白发魔女传 --chapter 1 \
        --gold tagged/白发魔女传/001.tagged.md --new logs/_eval_001/001.tagged.md \
        --out logs/qa/qwen_review_001.md
参数可用 env 覆盖：QWEN_BASE_URL / QWEN_API_KEY / QWEN_MODEL。
输入 = SKILL_03a v1.8 规范全文 + 两稿全文 + 机检对账摘要；输出 = markdown 评审意见。
注意：外部模型的具体例证与数字可能幻觉，必须再用 compare_annotation_gold.py 程序化核验。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config  # noqa: E402
from compare_annotation_gold import load, match  # noqa: E402
from annotate_chapter_llm import load_system_prompt, read_struct  # noqa: E402

BASE = os.environ.get("QWEN_BASE_URL", "https://developer.amd.com.cn/radeon/api/v1")
KEY = os.environ.get("QWEN_API_KEY", "")
MODEL = os.environ.get("QWEN_MODEL", "Qwen3.8-Flash-Next")


def call(messages, max_tokens=12000, think=False, timeout=900, model=None):
    model = model or MODEL
    payload = {"model": model, "messages": messages, "temperature": 0,
               "max_tokens": max_tokens, "stream": False}
    if not think:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        payload["enable_thinking"] = False
    req = urllib.request.Request(BASE.rstrip("/") + "/chat/completions",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + KEY})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d, time.time() - t0


def build_material(book: str, chapter: int, gold_path: Path, new_path: Path):
    system, ver = load_system_prompt()
    _, struct = read_struct(config.struct_path(book, chapter))
    gp, gplain, gsp = load(gold_path)
    np_, nplain, nsp = load(new_path)

    conflicts, gold_only, new_only = [], [], []
    for pn in sorted(struct):
        g, n = gsp.get(pn, []), nsp.get(pn, [])
        exact, partial, conflict, go, no = match(g, n)
        for i, j in conflict:
            a, b, c, d, raw, _ = g[i]
            na, nb, nc, nd, nraw, _ = n[j]
            ctx = gplain[pn][max(0, min(a, na) - 16):max(b, nb) + 16]
            conflicts.append((pn, raw, d, nraw, nd, ctx))
        for i in go:
            a, b, c, d, raw, _ = g[i]
            gold_only.append((pn, c, d, gplain[pn][max(0, a - 14):b + 14]))
        for j in no:
            a, b, c, d, raw, _ = n[j]
            new_only.append((pn, c, d, nplain[pn][max(0, a - 14):b + 14]))
    g_n = sum(len(v) for v in gsp.values())
    n_n = sum(len(v) for v in nsp.values())
    hit = 0
    for pn in struct:
        e, p, _cf, _go, _no = match(gsp.get(pn, []), nsp.get(pn, []))
        hit += len(e) + len(p)
    return system, ver, gplain, nplain, conflicts, gold_only, new_only, (g_n, n_n, hit)


def render_text(plains):
    return "\n\n".join(f"[{pn}] {plains[pn]}" for pn in sorted(plains))


def main():
    ap = argparse.ArgumentParser(description="外部模型复核两稿标注（Qwen/AMD 端点）")
    ap.add_argument("--book", default=config.PILOT_BOOK)
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--no-think", action="store_true", default=True)
    args = ap.parse_args()
    model = args.model
    if not KEY:
        raise SystemExit("缺少 API key：设 QWEN_API_KEY 环境变量（或改脚本默认值，勿提交密钥）")
    gold_path, new_path = Path(args.gold), Path(args.new)
    (system, ver, gplain, nplain, conflicts, gold_only, new_only,
     (g_n, n_n, hit)) = build_material(args.book, args.chapter, gold_path, new_path)
    print(f"规范 {len(system)} 字；两稿各 {sum(len(v) for v in gplain.values())}/"
          f"{sum(len(v) for v in nplain.values())} 字；冲突 {len(conflicts)}；"
          f"金only {len(gold_only)}；新only {len(new_only)}")

    conflict_txt = "\n".join(
        f"{k+1}. [段{pn}] 金标准 {raw}  vs  新标注 {nraw}   上下文：…{ctx}…"
        for k, (pn, raw, d, nraw, nd, ctx) in enumerate(conflicts))
    goldonly_txt = "\n".join(f"[段{pn}] {c}「{d}」 …{ctx}…" for pn, c, d, ctx in gold_only)
    newonly_txt = "\n".join(f"[段{pn}] {c}「{d}」 …{ctx}…" for pn, c, d, ctx in new_only)
    user = f"""你是武侠小说语料标注的外部评审专家。依据 A 规范独立判断 B（金标准，可能为旧口径）
与 C（新标注）的合理性，不要偏袒任何一方。

## A. 权威规范（SKILL_03a v1.8）
````text
{system}
````

## B. 金标准 第 {args.chapter:03d} 回
{render_text(gplain)}

## C. 新标注 第 {args.chapter:03d} 回
{render_text(nplain)}

## D. 机器对账摘要（仅参考，不保证正确）
- 实体：金标准 {g_n} / 新 {n_n} / 命中 {hit}
- 类型冲突 {len(conflicts)} 处：
{conflict_txt}
- 金标准独有（节选）：
{goldonly_txt[:6000]}
- 新标注独有（节选）：
{newonly_txt[:4000]}

## 请输出（markdown，中文，具体可执行，不要空话）
### 1. 总体判断（结构合规/类型正确性/边界粒度/召回覆盖/口径一致性/动词质量，各 0-10 分+理由）
### 2. 两稿各自主要问题（各 5-8 条，每条 1 个原文例子+规范条款）
### 3. 类型冲突逐条裁决（编号|金|新|谁更符合规范|依据）
### 4. 你不同意"机器对账"的地方（逐条）
### 5. 对下一步标注生产的建议（P0/P1/P2，含动作/收益/风险）
### 6. 结论（一句话）
"""
    d, dt = call([{"role": "user", "content": user}], max_tokens=12000, model=model)
    u = d.get("usage", {})
    content = d["choices"][0]["message"].get("content") or ""
    out = Path(args.out) if args.out else (config.DIR_LOGS / "qa" /
                                           f"qwen_review_{args.chapter:03d}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(content + "\n")
    meta = out.with_suffix(".meta.json")
    io.open(meta, "w", encoding="utf-8", newline="\n").write(
        json.dumps({"model": model, "base_url": BASE, "elapsed_s": round(dt, 1),
                    "usage": u, "prompt_chars": len(user), "output_chars": len(content)},
                   ensure_ascii=False, indent=1) + "\n")
    print(f"elapsed {dt:.1f}s；usage {json.dumps(u, ensure_ascii=False)[:200]}")
    print(f"→ {out}\n→ {meta}")


if __name__ == "__main__":
    main()
