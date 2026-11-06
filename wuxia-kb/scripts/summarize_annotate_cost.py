# -*- coding: utf-8 -*-
"""逐回标注费用汇总（读 logs/token_usage/annotate_*.json，取每回最新一条）。

用法：
    python scripts/summarize_annotate_cost.py --book 白发魔女传
    python scripts/summarize_annotate_cost.py --book 白发魔女传 --chapters 20-32 --markdown logs/cost.md

输出：控制台表格 + 可选 markdown 表（含实体/动词密度与合计）。
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config  # noqa: E402


def parse_chapters(spec: str):
    if not spec:
        return None
    out = []
    try:
        for part in spec.split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                out.extend(range(int(a), int(b) + 1))
            else:
                out.append(int(part))
    except ValueError:
        raise SystemExit(f"[ERROR] --chapters 格式非法：{spec!r}（示例：20-32 或 12,13）")
    return set(out)


def latest_records(book: str):
    pat = str(config.DIR_LOGS / "token_usage" / f"annotate_{book}_*.json")
    rec = {}
    for p in glob.glob(pat):
        m = re.search(r"_(\d{3})_(\d{8}_\d{6})\.json$", p)
        if not m:
            continue
        ch, ts = int(m.group(1)), m.group(2)
        if ch not in rec or ts > rec[ch][0]:
            rec[ch] = (ts, p)
    return {ch: json.loads(io.open(v[1], encoding="utf-8").read()) for ch, v in rec.items()}


def recount_from_tagged(book: str, ch: int, fallback: dict):
    """令牌计数以最终 tagged 产物为准（计费 JSON 记录的是当次执行时的计数，
    后续机械补标/修辞补标会变化）；字数以 struct 为准。"""
    tp = config.tagged_path(book, ch)
    sp = config.struct_path(book, ch)
    if not tp.exists() or not sp.exists():
        return fallback.get("E", 0), fallback.get("V", 0), fallback.get("R", 0), fallback.get("chars", 0)
    t = io.open(tp, encoding="utf-8").read()
    s = io.open(sp, encoding="utf-8").read()
    chars = sum(len(m.group(1)) for m in re.finditer(r"^\[\d+\] (.*)$", s, re.M))
    return t.count("〖"), t.count("⟦"), t.count("〘"), chars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default=config.PILOT_BOOK)
    ap.add_argument("--chapters", default=None, help="如 20-32；缺省全部")
    ap.add_argument("--markdown", default=None, help="另存 markdown 表路径")
    args = ap.parse_args()
    keep = parse_chapters(args.chapters)
    data = latest_records(args.book)
    rows = []
    for ch in sorted(data):
        if keep and ch not in keep:
            continue
        d = data[ch]
        tok = d.get("tokens", {})
        rhe = d.get("rhetoric", {}) or {}
        cost_ann = d.get("cost_usd", 0.0)
        cost_rhe = rhe.get("cost", 0.0) or 0.0
        E, V, R, chars = recount_from_tagged(args.book, ch, {
            "E": tok.get("E", 0), "V": tok.get("V", 0), "R": tok.get("R", 0),
            "chars": d.get("chars", 0) or 0})
        calls = sum((v.get("calls", 0) for v in (d.get("usage_by_stage") or {}).values()))
        rows.append({
            "ch": ch, "chars": chars,
            "E": E, "V": V, "R": R,
            "E100": round(E * 100 / chars, 1) if chars else 0,
            "V100": round(V * 100 / chars, 1) if chars else 0,
            "calls": calls,
            "rhe_calls": len(rhe.get("usage") or []),
            "cost": cost_ann + cost_rhe,
            "cost_ann": cost_ann, "cost_rhe": cost_rhe,
            "peak": any(r.get("peak") for r in (d.get("usage") or [])),
            "pass": d.get("reverify_pass", False),
            "rhe_in": rhe.get("inserted", 0),
        })
    if not rows:
        print("未找到匹配的费用记录")
        return
    tot = {k: sum(r[k] for r in rows) for k in ("chars", "E", "V", "R", "calls", "cost",
                                               "cost_ann", "cost_rhe")}
    print(f"《{args.book}》逐回标注费用（peak={'×2 含高峰' if any(r['peak'] for r in rows) else '非高峰'}）")
    print(f"{'回':>4} {'字数':>6} {'E':>5} {'V':>4} {'R':>3} {'E/100':>6} {'V/100':>6} "
          f"{'调用':>4} {' annotate':>10} {'rhetoric':>9} {'合计$':>10} 复验")
    for r in rows:
        print(f"{r['ch']:>4} {r['chars']:>6} {r['E']:>5} {r['V']:>4} {r['R']:>3} "
              f"{r['E100']:>6} {r['V100']:>6} {r['calls']:>4} {r['cost_ann']:>10.6f} "
              f"{r['cost_rhe']:>9.6f} {r['cost']:>10.6f} {'PASS' if r['pass'] else 'FAIL'}")
    print(f"{'合计':>4} {tot['chars']:>6} {tot['E']:>5} {tot['V']:>4} {tot['R']:>3} "
          f"{'':>6} {'':>6} {tot['calls']:>4} {tot['cost_ann']:>10.6f} "
          f"{tot['cost_rhe']:>9.6f} {tot['cost']:>10.6f}")
    print(f"\n平均每回：{tot['cost']/len(rows):.6f} USD；合计折人民币约 ¥{tot['cost']*7.1:.3f}"
          f"（按 1 USD≈7.1 CNY 粗算，仅参考）")
    if args.markdown:
        lines = ["| 回 | 字数 | 实体E | 动词V | 修辞R | E/100字 | V/100字 | API调用 | annotate $ | "
                 "rhetoric $ | 合计 $ | 复验 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['ch']:03d} | {r['chars']} | {r['E']} | {r['V']} | {r['R']} | "
                         f"{r['E100']} | {r['V100']} | {r['calls']} | {r['cost_ann']:.6f} | "
                         f"{r['cost_rhe']:.6f} | **{r['cost']:.6f}** | "
                         f"{'PASS' if r['pass'] else 'FAIL'} |")
        lines.append(f"| **合计** | {tot['chars']} | {tot['E']} | {tot['V']} | {tot['R']} | | | "
                     f"{tot['calls']} | {tot['cost_ann']:.6f} | {tot['cost_rhe']:.6f} | "
                     f"**{tot['cost']:.6f}** | |")
        p = Path(args.markdown)
        p.parent.mkdir(parents=True, exist_ok=True)
        io.open(p, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
        print(f"markdown 表已落盘：{p}")


if __name__ == "__main__":
    main()
