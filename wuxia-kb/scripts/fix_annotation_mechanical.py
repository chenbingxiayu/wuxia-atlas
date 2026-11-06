# -*- coding: utf-8 -*-
"""标注产物机械化修复（不调 LLM）：管道纪律归一 + 闭括号归一 + 非法令牌摘除 + 剥标复验。

用途：annotate 批次的收尾工序。只做 SKILL_03a §三·阶段 3 允许的确定性修复，
原文永不改动；修复后逐段剥标必须逐字等于 struct 底本，否则该段回退原样并报错。

用法：
    python scripts/fix_annotation_mechanical.py --book 白发魔女传 --chapters 20-32 --dry-run
    python scripts/fix_annotation_mechanical.py --book 白发魔女传 --chapters 20-32
    python scripts/fix_annotation_mechanical.py --book 白发魔女传 --chapters 12-19 --punct-outside
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config                 # noqa: E402
from annotate_chapter_llm import (PARA_RE, read_struct, split_blocks,  # noqa: E402
                                  strip_all, validate_and_repair)

PUNCT_IN_TOKEN = "，。、；：！？"


def punct_outside(text: str) -> str:
    """把 〖^X〗 内部的中文标点移到标记外（标点外置原则）。

    〖^如花美眷，似水流年〗 → 〖^如花美眷〗，〖^似水流年〗（同类型码按逗号切分）。
    仅处理含中文标点的实体令牌；切分后每段必须非空。
    """
    out, i, n = [], 0, len(text)
    pairs = {"〖": "〗", "⟦": "⟧", "〘": "〙"}
    while i < n:
        ch = text[i]
        if ch in pairs:
            j = text.find(pairs[ch], i + 1)
            if j < 0:
                out.append(ch)
                i += 1
                continue
            body = text[i + 1:j]
            code, rest = body[0], body[1:]
            disp, sep, note = rest.partition("|")
            if ch == "〖" and code not in ("@", "%") and any(p in disp for p in PUNCT_IN_TOKEN):
                pieces = re.split(r"([，。、；：！？])", disp)
                rebuilt, pend = [], None
                for p in pieces:
                    if p in PUNCT_IN_TOKEN:
                        pend = p
                        continue
                    if not p:
                        continue
                    if pend:
                        rebuilt.append(pend)
                        pend = None
                    rebuilt.append(f"{ch}{code}{p}{pairs[ch]}")
                out.append("".join(rebuilt))
                i = j + 1
                continue
            out.append(text[i:j + 1])
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def fix_chapter(book: str, ch: int, dry: bool, do_punct: bool) -> dict:
    sp, tp = config.struct_path(book, ch), config.tagged_path(book, ch)
    if not tp.exists():
        return {"chapter": ch, "error": "tagged 缺失"}
    lines, paras = read_struct(sp)
    tagged = io.open(tp, encoding="utf-8").read()
    tlines = tagged.split("\n")
    if len(tlines) != len(lines):
        return {"chapter": ch, "error": f"行数不一致 {len(tlines)}/{len(lines)}"}
    n_pipe = n_tok = n_punct = n_rollb = 0
    problems = []
    for idx, ln in enumerate(tlines):
        m = PARA_RE.match(ln)
        if not m:
            continue
        pn, text = int(m.group(1)), m.group(2)
        src = paras.get(pn)
        if src is None:
            problems.append(f"[{pn}] struct 无此段")
            continue
        if strip_all(text) != src:
            problems.append(f"[{pn}] 修复前剥标已不等于底本（跳过）")
            continue
        new = text
        if do_punct:
            cand = punct_outside(new)
            if cand != new:
                new = cand
                n_punct += 1
        fixed, probs, dropped = validate_and_repair(new, src)
        if fixed != new:
            n_pipe += sum(1 for p in probs if "管道归一" in p)
            n_tok += len(dropped)
            n_rollb += sum(1 for p in probs if "闭合符误写" in p)
            new = fixed
        if strip_all(new) != src:
            problems.append(f"[{pn}] 机械修复后剥标不一致（回退）")
            new = text
        if new != text:
            tlines[idx] = f"[{pn}] {new}"
    result = {"chapter": ch, "pipe": n_pipe, "token": n_tok, "bracket": n_rollb,
              "punct": n_punct, "problems": problems}
    if not dry:
        io.open(tp, "w", encoding="utf-8", newline="\n").write("\n".join(tlines))
    return result


def parse_chapters(spec: str) -> list:
    out = []
    try:
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                out.extend(range(int(a), int(b) + 1))
            else:
                out.append(int(part))
    except ValueError:
        raise SystemExit(f"[ERROR] --chapters 格式非法：{spec!r}（示例：20-32 或 12,13）")
    return out


def main():
    ap = argparse.ArgumentParser(description="标注产物机械化修复（管道/闭括号/非法令牌/标点外置）")
    ap.add_argument("--book", default=config.PILOT_BOOK)
    ap.add_argument("--chapters", required=True, help="如 20-32 或 12,13")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--punct-outside", action="store_true",
                    help="附带把实体令牌内部中文标点外置（修既有金标准 punct_in_annotation）")
    args = ap.parse_args()
    total = {"pipe": 0, "token": 0, "bracket": 0, "punct": 0}
    bad = 0
    for ch in parse_chapters(args.chapters):
        r = fix_chapter(args.book, ch, args.dry_run, args.punct_outside)
        if r.get("error"):
            print(f"  {ch:03d}: ERROR {r['error']}")
            bad += 1
            continue
        for k in total:
            total[k] += r[k]
        print(f"  {ch:03d}: 管道归一 {r['pipe']} 段 / 令牌摘除 {r['token']} / 闭括号修复 "
              f"{r['bracket']} / 标点外置 {r['punct']}" +
              (f" / 问题 {r['problems']}" if r["problems"] else ""))
        bad += len(r["problems"])
    print(f"\n合计：管道归一 {total['pipe']} 段，令牌摘除 {total['token']}，闭括号修复 "
          f"{total['bracket']}，标点外置 {total['punct']}；问题 {bad}"
          + ("（dry-run 未落盘）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
