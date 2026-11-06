# -*- coding: utf-8 -*-
"""一次性：新标注 vs 旧标注（kb/tagged/<书>，v0.2 无 PN）的全局逐令牌对账。

用途：〈江湖三女侠〉48 回新管线机器标注与旧人工种子标注（视为旧口径金标准）的
P/R 与类型冲突量化，作为 docs/40 式质量证据。两稿剥标后的正文必须逐字一致；
不一致则退回该回不参与统计（保证坐标可比）。

口径：
  - 旧符号归一：'[' → '{'（作品文书）、'§' → '•'（药物成品并入器物）；
  - exact/partial/conflict/gold_only/new_only 同 compare_annotation_gold.py；
  - P/R 按类型：P = (exact+partial) / new_total，R = (exact+partial) / gold_total；
  - 管道一致性单独统计（同类同区间，显示串相同、规范名不同 → 记为 pipe_diff）。

用法：
    python scripts/_oneshot/compare_new_vs_legacy.py 江湖三女侠
产物：
    logs/qa/compare_legacy_<书>.md / .json
"""
from __future__ import annotations

import collections
import glob
import io
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402
from compare_annotation_gold import match  # noqa: E402

BOOK = sys.argv[1] if len(sys.argv) > 1 else "江湖三女侠"
LEGACY_CODE = {"[": "{", "§": "•"}
PARA_RE = re.compile(r"^\[(\d+)\] (.*)$")
TITLE_RE = re.compile(r"^# \[0\] ")


def strip_plain_global(text: str):
    """整篇剥标 → (plain, spans)；spans 坐标属于 plain。"""
    pairs = {"〖": "〗", "⟦": "⟧", "〘": "〙"}
    spans, parts, plen, i, n = [], [], 0, 0, len(text)
    while i < n:
        ch = text[i]
        if ch in pairs:
            j = text.find(pairs[ch], i + 1)
            if j < 0:
                parts.append(ch); plen += 1; i += 1; continue
            inner = text[i + 1:j]
            code = inner[0] if inner else ""
            rest = inner[1:] if len(inner) > 1 else ""
            disp = rest.split("|", 1)[0]
            spans.append((plen, plen + len(disp), LEGACY_CODE.get(code, code), disp))
            parts.append(disp); plen += len(disp); i = j + 1
        else:
            parts.append(ch); plen += 1; i += 1
    return "".join(parts), spans


def _strip_fence_lines(text: str) -> str:
    """去掉 ::: 围栏行（结构层围栏识别口径两稿不一致，对账只看正文与令牌）。"""
    return "\n".join(ln for ln in text.split("\n") if not ln.startswith(":::"))


def load_new(path: Path):
    """新 tagged：段首 [N] 前缀剥掉；回目行 '# [0] 标题' → '标题'；围栏行删除。"""
    out = []
    for ln in io.open(path, encoding="utf-8").read().split("\n"):
        m = PARA_RE.match(ln)
        if m:
            out.append(m.group(2))
        elif ln.startswith("# [0] "):
            out.append(ln[len("# [0] "):])
        else:
            out.append(ln)
    return strip_plain_global(_strip_fence_lines("\n".join(out)))


def load_legacy(path: Path):
    """旧 tagged：去 YAML 头；首行标题保留；围栏行删除。"""
    t = io.open(path, encoding="utf-8").read()
    if t.startswith("---"):
        parts = t.split("\n---\n", 1)
        t = parts[1] if len(parts) == 2 else t
    return strip_plain_global(_strip_fence_lines(t))


def main():
    d_new = config.DIR_TAGGED / BOOK
    d_old = config.REPO_ROOT / "kb" / "tagged" / BOOK
    files = sorted(glob.glob(str(d_old / "*.tagged.md")))
    per_type = {c: {"gold": 0, "new": 0, "hit": 0, "exact": 0} for c in "@◎=◆&~;#☆•+{^%$"}
    totals = collections.Counter()
    pipe_diff, per_ch, bad = [], [], []
    for p in files:
        ch = int(os.path.basename(p)[:3])
        new_p = d_new / f"{ch:03d}.tagged.md"
        if not new_p.exists():
            bad.append((ch, "新标注缺失"))
            continue
        g_plain, g_sp = load_legacy(Path(p))
        n_plain, n_sp = load_new(new_p)
        if g_plain != n_plain:
            bad.append((ch, f"正文不一致 gold={len(g_plain)} new={len(n_plain)}"))
            continue
        gsp = [(a, b, c, d, "", None) for a, b, c, d in g_sp if c in per_type]
        nsp = [(a, b, c, d, "", None) for a, b, c, d in n_sp if c in per_type]
        exact, partial, conflict, g_only, n_only = match(gsp, nsp)
        for i in range(len(gsp)):
            per_type[gsp[i][2]]["gold"] += 1
        for j in range(len(nsp)):
            per_type[nsp[j][2]]["new"] += 1
        for i, j in exact:
            per_type[gsp[i][2]]["hit"] += 1
            per_type[gsp[i][2]]["exact"] += 1
        for i, j in partial:
            per_type[gsp[i][2]]["hit"] += 1
        # 管道一致性
        gp = {(gsp[i][0], gsp[i][1], gsp[i][2]): gsp[i][3] for i in range(len(gsp))}
        for i, j in exact:
            ga, gb, gc, gd, _, _ = gsp[i]
            na, nb, nc, nd, _, _ = nsp[j]
            if gd != nd and (gc, ga, gb) in gp:
                pipe_diff.append((ch, gc, gd, nd))
        cnt = {"exact": len(exact), "partial": len(partial), "conflict": len(conflict),
               "gold_only": len(g_only), "new_only": len(n_only)}
        per_ch.append((ch, len(gsp), len(nsp), cnt["exact"], cnt["partial"], cnt["conflict"],
                       cnt["gold_only"], cnt["new_only"]))
        totals.update(cnt)

    # ---- 汇总 ----
    L = [f"# 新管线标注 vs 旧标注（金标准口径）对账 ——《{BOOK}》", "",
         f"- 新稿：`{d_new}`；旧稿：`{d_old}`",
         "- 旧符号归一：`[`→`{`、`§`→`•`；逐回剥标后正文必须逐字一致才参与统计", ""]
    if bad:
        L += ["## 未参与对账的回", ""] + [f"- {ch:03d}: {why}" for ch, why in bad] + [""]
    L += ["## 分回统计", "",
          "| 回 | gold 令牌 | new 令牌 | exact | partial | conflict | gold_only | new_only |",
          "|---|---|---|---|---|---|---|---|"]
    for r in per_ch:
        L.append("| " + " | ".join(str(x) for x in r) + " |")
    L += ["", "## 分类型 P/R（旧稿=金标准）", "",
          "| 类型 | gold | new | 命中(exact+partial) | P | R |", "|---|---|---|---|---|---|"]
    for c in "@◎=◆&~;#☆•+{^%$":
        s = per_type[c]
        if not s["gold"] and not s["new"]:
            continue
        p = s["hit"] / s["new"] if s["new"] else 0
        r = s["hit"] / s["gold"] if s["gold"] else 0
        L.append(f"| {c} | {s['gold']} | {s['new']} | {s['hit']} | {p:.3f} | {r:.3f} |")
    g_all = sum(per_type[c]["gold"] for c in per_type)
    n_all = sum(per_type[c]["new"] for c in per_type)
    h_all = sum(per_type[c]["hit"] for c in per_type)
    L += ["", f"- 实体总：gold {g_all} / new {n_all} / 命中 {h_all} → "
              f"**P={h_all/n_all:.3f} R={h_all/g_all:.3f}**",
          f"- 逐令牌：exact {totals['exact']} · partial {totals['partial']} · "
          f"conflict {totals['conflict']} · gold_only {totals['gold_only']} · "
          f"new_only {totals['new_only']}",
          f"- 管道规范名差异（同类同区间）{len(pipe_diff)} 处"
          + ("；样例：" + "；".join(f"{ch:03d} {c} {g}→{n}" for ch, c, g, n in pipe_diff[:8]) if pipe_diff else ""),
          ""]
    out_md = config.DIR_LOGS / "qa" / f"compare_legacy_{BOOK}.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    io.open(out_md, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    io.open(config.DIR_LOGS / "qa" / f"compare_legacy_{BOOK}.json", "w", encoding="utf-8").write(
        json.dumps({"per_chapter": per_ch, "per_type": per_type, "totals": dict(totals),
                    "pipe_diff": pipe_diff[:200], "skipped": bad}, ensure_ascii=False, indent=1))
    print(f"[ok] {len(per_ch)} 回对账；实体 gold={g_all} new={n_all} 命中={h_all} "
          f"P={h_all/n_all:.3f} R={h_all/g_all:.3f}")
    if bad:
        print(f"[warn] 跳过 {len(bad)} 回：{bad[:6]}")
    print(f"→ {out_md}")


if __name__ == "__main__":
    main()
