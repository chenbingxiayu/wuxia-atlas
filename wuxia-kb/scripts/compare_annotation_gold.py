# -*- coding: utf-8 -*-
"""标注对比器 —— 同一回"新标注"与"金标准"的逐令牌对账（用于回归/合理性分析）。

对账口径（plain 坐标 = 剥标后正文坐标）：
  exact    同类型 + 同区间                     → 完全一致
  partial  同类型 + 区间重叠（边界/粒度差异）  → 视为命中（relaxed），另计边界差异
  conflict 不同类 + 区间重叠                   → 类型冲突（谁对需人工判）
  gold_only 金标准有、新标注无                  → 漏标
  new_only  新标注有、金标准无                  → 多标
输出：逐类型 P/R、差异样例（带上下文）、管道一致性、文本保真校验。

用法：
    python scripts/compare_annotation_gold.py --book 白发魔女传 --chapter 1 \
        --gold tagged/白发魔女传/001.tagged.md --new logs/_eval_001/001.tagged.md \
        --out logs/qa/compare_001.md
"""
from __future__ import annotations

import argparse
import collections
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
import config  # noqa: E402
from annotate_chapter_llm import PARA_RE, read_struct  # noqa: E402

ENT_ORDER = "@◎=◆&~;#☆•+{^%$"
VERB_ORDER = "⊞⊠⊡⊟▣■"


def parse_para(body: str):
    """→ (plain, spans[(start,end,code,display,raw)])；坐标 = plain。"""
    pairs = {"〖": "〗", "⟦": "⟧", "〘": "〙"}
    spans, parts, plen, i, n = [], [], 0, 0, len(body)
    while i < n:
        ch = body[i]
        if ch in pairs:
            j = body.find(pairs[ch], i + 1)
            if j < 0:
                parts.append(ch)
                plen += 1
                i += 1
                continue
            inner = body[i + 1:j]
            code = inner[0] if inner else ""
            rest = inner[1:] if len(inner) > 1 else ""
            disp, sep, note = rest.partition("|")
            spans.append((plen, plen + len(disp), code, disp, body[i:j + 1],
                          note if sep else None))
            parts.append(disp)
            plen += len(disp)
            i = j + 1
        else:
            parts.append(ch)
            plen += 1
            i += 1
    return "".join(parts), spans


def load(path: Path):
    paras, plains, spans = {}, {}, {}
    for ln in io.open(path, encoding="utf-8").read().split("\n"):
        m = PARA_RE.match(ln)
        if m:
            pn = int(m.group(1))
            plain, sp = parse_para(m.group(2))
            paras[pn] = m.group(2)
            plains[pn] = plain
            spans[pn] = sp
    return paras, plains, spans


def match(gold_sp, new_sp):
    g_used = [False] * len(gold_sp)
    n_used = [False] * len(new_sp)
    exact, partial, conflict = [], [], []
    # 1) exact
    g_index = collections.defaultdict(list)
    for i, (a, b, c, d, raw, note) in enumerate(gold_sp):
        g_index[(c, a, b)].append(i)
    for j, (a, b, c, d, raw, note) in enumerate(new_sp):
        key = (c, a, b)
        if g_index.get(key):
            i = g_index[key].pop()
            g_used[i] = n_used[j] = True
            exact.append((i, j))
    # 2) overlap（长重叠优先；同类型=partial，不同类型=conflict）
    pairs = []
    for i, (ga, gb, gc, gd, graw, gnote) in enumerate(gold_sp):
        if g_used[i]:
            continue
        for j, (na, nb, nc, nd, nraw, nnote) in enumerate(new_sp):
            if n_used[j]:
                continue
            ov = min(gb, nb) - max(ga, na)
            if ov > 0:
                pairs.append((ov, gc == nc, i, j))
    pairs.sort(key=lambda x: (-x[0], not x[1]))
    for _ov, same, i, j in pairs:
        if g_used[i] or n_used[j]:
            continue
        g_used[i] = n_used[j] = True
        (partial if same else conflict).append((i, j))
    g_only = [i for i, u in enumerate(g_used) if not u]
    n_only = [j for j, u in enumerate(n_used) if not u]
    return exact, partial, conflict, g_only, n_only


def snippet(plain, a, b, w=22):
    return plain[max(0, a - w):min(len(plain), b + w)].replace("\n", " ")


def main():
    ap = argparse.ArgumentParser(description="新标注 vs 金标准 逐令牌对账")
    ap.add_argument("--book", default=config.PILOT_BOOK)
    ap.add_argument("--chapter", type=int, default=1)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-examples", type=int, default=12, help="每类样例上限")
    args = ap.parse_args()

    gp, gplain, gspans = load(Path(args.gold))
    np_, nplain, nspans = load(Path(args.new))
    sp_path = config.struct_path(args.book, args.chapter)
    _, struct = read_struct(sp_path)

    # 文本保真
    text_err = [pn for pn in struct if gplain.get(pn) != struct[pn] or nplain.get(pn) != struct[pn]]

    # 对账
    gstat = collections.defaultdict(collections.Counter)
    nstat = collections.defaultdict(collections.Counter)
    examples = collections.defaultdict(list)
    pipe_diff = []
    conflicts_by_pair = collections.Counter()
    for pn in sorted(struct):
        g = gspans.get(pn, [])
        n = nspans.get(pn, [])
        exact, partial, conflict, g_only, n_only = match(g, n)
        for i, j in exact:
            gstat[g[i][2]]["exact"] += 1
            nstat[n[j][2]]["exact"] += 1
            if g[i][2] == "@" and g[i][5] != n[j][5]:
                pipe_diff.append((pn, g[i][4], n[j][4], snippet(gplain[pn], g[i][0], g[i][1])))
        for i, j in partial:
            gstat[g[i][2]]["partial"] += 1
            nstat[n[j][2]]["partial"] += 1
            examples["partial"].append((pn, g[i][2], g[i][3], g[i][0], g[i][1],
                                        n[j][3], n[j][0], n[j][1], gplain[pn]))
        for i, j in conflict:
            gstat[g[i][2]]["conflict"] += 1
            nstat[n[j][2]]["conflict"] += 1
            conflicts_by_pair[(g[i][2], n[j][2])] += 1
            examples["conflict"].append((pn, g[i][2], g[i][3], g[i][0], g[i][1],
                                         n[j][2], n[j][3], n[j][0], n[j][1], gplain[pn]))
        for i in g_only:
            gstat[g[i][2]]["only"] += 1
            examples["gold_only"].append((pn, g[i][2], g[i][3], g[i][0], g[i][1], gplain[pn]))
        for j in n_only:
            nstat[n[j][2]]["only"] += 1
            examples["new_only"].append((pn, n[j][2], n[j][3], n[j][0], n[j][1], gplain[pn]))

    # 汇总
    rows = []
    for code in ENT_ORDER + VERB_ORDER:
        gs, ns = gstat[code], nstat[code]
        gold_n = gs["exact"] + gs["partial"] + gs["conflict"] + gs["only"]
        new_n = ns["exact"] + ns["partial"] + ns["conflict"] + ns["only"]
        hit = gs["exact"] + gs["partial"]
        rows.append({"code": code, "gold": gold_n, "new": new_n, "exact": gs["exact"],
                     "partial": gs["partial"], "conflict": gs["conflict"],
                     "gold_only": gs["only"], "new_only": ns["only"],
                     "P": hit / new_n if new_n else 0, "R": hit / gold_n if gold_n else 0})

    def totals(sel_codes):
        r = [x for x in rows if x["code"] in sel_codes]
        gold_n = sum(x["gold"] for x in r)
        new_n = sum(x["new"] for x in r)
        hit = sum(x["exact"] + x["partial"] for x in r)
        return gold_n, new_n, hit, (hit / new_n if new_n else 0), (hit / gold_n if gold_n else 0)

    eg = totals(set(ENT_ORDER))
    ev = totals(set(VERB_ORDER))

    L = [f"# 标注对比报告 ·《{args.book}》第 {args.chapter:03d} 回", "",
         f"- 金标准：`{args.gold}`", f"- 新标注：`{args.new}`", "",
         "## 一、总览", "",
         f"- 文本保真：{'PASS（两稿剥标均等于 struct 底本）' if not text_err else 'FAIL ' + str(text_err[:5])}",
         f"- 实体：金标准 {eg[0]} / 新 {eg[1]} / 命中 {eg[2]}（含边界）→ "
         f"P={eg[3]:.3f} R={eg[4]:.3f} F1={2*eg[3]*eg[4]/max(1e-9, eg[3]+eg[4]):.3f}",
         f"- 动词：金标准 {ev[0]} / 新 {ev[1]} / 命中 {ev[2]}（含边界）→ "
         f"P={ev[3]:.3f} R={ev[4]:.3f} F1={2*ev[3]*ev[4]/max(1e-9, ev[3]+ev[4]):.3f}",
         "", "## 二、逐类型对账", "",
         "| 类 | 金标准 | 新 | exact | partial | 类型冲突 | 金only | 新only | P | R |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for x in rows:
        if x["gold"] == 0 and x["new"] == 0:
            continue
        L.append(f"| {x['code']} | {x['gold']} | {x['new']} | {x['exact']} | {x['partial']} | "
                 f"{x['conflict']} | {x['gold_only']} | {x['new_only']} | "
                 f"{x['P']:.2f} | {x['R']:.2f} |")
    L += ["", "## 三、类型冲突矩阵（金标准类 → 新标注类）", ""]
    for (gc, nc), cnt in conflicts_by_pair.most_common(15):
        L.append(f"- {gc} → {nc}：{cnt} 处")
    if not conflicts_by_pair:
        L.append("- （无）")
    L += ["", "## 四、管道差异（同区间 @ 令牌的规范名不一致）", ""]
    if pipe_diff:
        for pn, g, n, ctx in pipe_diff[:args.max_examples]:
            L.append(f"- [{pn}] 金 `{g}` vs 新 `{n}`：…{ctx}…")
    else:
        L.append("- （无）")

    def dump(name, title, render):
        L.append("")
        L.append(f"## {title}")
        L.append("")
        items = examples[name]
        if not items:
            L.append("- （无）")
            return
        for it in items[:args.max_examples]:
            L.append("- " + render(it))
        L.append(f"- …共 {len(items)} 处")

    dump("conflict", "五、类型冲突样例",
         lambda it: f"[{it[0]}] 金 {it[1]}「{it[2]}」({it[3]}:{it[4]}) vs 新 {it[5]}「{it[6]}」"
                    f"({it[7]}:{it[8]})：…{snippet(it[9], min(it[3], it[7]), max(it[4], it[8]))}…")
    dump("gold_only", "六、金标准独有（新标注漏标）样例",
         lambda it: f"[{it[0]}] {it[1]}「{it[2]}」：…{snippet(it[5], it[3], it[4])}…")
    dump("new_only", "七、新标注独有（金标准未标）样例",
         lambda it: f"[{it[0]}] {it[1]}「{it[2]}」：…{snippet(it[5], it[3], it[4])}…")
    dump("partial", "八、边界差异样例（同类型、区间不同）",
         lambda it: f"[{it[0]}] {it[1]} 金「{it[2]}」{it[3]}:{it[4]} vs 新「{it[5]}」{it[6]}:{it[7]}："
                    f"…{snippet(it[8], min(it[3], it[6]), max(it[4], it[7]))}…")

    text = "\n".join(L) + "\n"
    out = Path(args.out) if args.out else (config.DIR_LOGS / "qa" /
                                           f"compare_{args.chapter:03d}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(text)
    print(text)
    print(f"报告已落盘：{out}")


if __name__ == "__main__":
    main()
