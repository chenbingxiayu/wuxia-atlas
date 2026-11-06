# -*- coding: utf-8 -*-
"""一次性：整批 tagged 复核（剥标==struct、令牌合法、段序一致）+ 逐回 E/V/R/字数统计。

复用 annotate_chapter_llm.final_verify / read_struct 与 symbols，不改任何产物。
用法：python scripts/_oneshot/verify_batch.py 江湖三女侠
产物：logs/qa/verify_batch_<书>.md / .json
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402
import symbols  # noqa: E402
from annotate_chapter_llm import final_verify, read_struct, summarize_tokens  # noqa: E402

PARA_RE = re.compile(r"^\[(\d+)\] (.*)$")


def main():
    book = sys.argv[1] if len(sys.argv) > 1 else "江湖三女侠"
    d = config.DIR_TAGGED / book
    total = config.books()[book]["chapters"]
    rows, fails, all_tok = [], [], {"E": 0, "V": 0, "R": 0}
    for ch in range(1, total + 1):
        sp = d / f"{ch:03d}.struct.md"
        tp = d / f"{ch:03d}.tagged.md"
        if not (sp.exists() and tp.exists()):
            fails.append((ch, "缺 struct/tagged"))
            continue
        _, paras = read_struct(sp)
        text = io.open(tp, encoding="utf-8").read()
        errs = final_verify(text, paras)
        tok = summarize_tokens(text)
        # 字数 = 内容行字符数合计（含围栏内续行；合并 PN 后 [N] 行只含首句）
        chars = 0
        for ln in io.open(sp, encoding="utf-8").read().split("\n"):
            if not ln.strip() or ln.startswith(":::") or ln.startswith("# [0]"):
                continue
            m = PARA_RE.match(ln)
            chars += len(m.group(2)) if m else len(ln)
        rows.append({"chapter": ch, "chars": chars, "paras": len(paras),
                     "E": tok["E_total"], "V": tok["V_total"], "R": tok["R_total"],
                     "pass": not errs, "errs": errs[:3],
                     "title_tagged": bool(re.search(r"^# \[0\] .*〖", text, re.M))})
        for k in all_tok:
            all_tok[k] += tok[f"{k}_total"]
        if errs:
            fails.append((ch, errs[:2]))

    L = [f"# 整批复核报告 ——《{book}》", "",
         f"- 回数：{total}；复核项：逐段剥标==struct、段号序列、令牌合法性（15+6+1 码白名单/闭合/嵌套/重叠）",
         f"- 结果：**{sum(1 for r in rows if r['pass'])}/{total} 回 PASS**", "",
         "| 回 | 段数 | 字数 | E | V | R | 复验 | 回目标注 |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['chapter']:03d} | {r['paras']} | {r['chars']:,} | {r['E']} | {r['V']} | "
                 f"{r['R']} | {'PASS' if r['pass'] else 'FAIL'} | {'有' if r['title_tagged'] else '无'} |")
    chars = sum(r["chars"] for r in rows)
    L += ["", f"- 合计：{len(rows)} 回 / {chars:,} 字 / "
              f"E={all_tok['E']} V={all_tok['V']} R={all_tok['R']}",
          f"- 实体密度 E/百字 = {all_tok['E'] / chars * 100:.2f}；"
          f"动词密度 V/百字 = {all_tok['V'] / chars * 100:.2f}", ""]
    if fails:
        L += ["## 失败项", ""] + [f"- {ch}: {msg}" for ch, msg in fails]
    out = config.DIR_LOGS / "qa" / f"verify_batch_{book}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    io.open(out.with_suffix(".json"), "w", encoding="utf-8").write(
        json.dumps({"rows": rows, "totals": dict(all_tok), "chars": chars, "fails": fails},
                   ensure_ascii=False, indent=1))
    print(f"[verify] {sum(1 for r in rows if r['pass'])}/{total} PASS; "
          f"chars={chars} E={all_tok['E']} V={all_tok['V']} R={all_tok['R']}; "
          f"fails={len(fails)} → {out}")
    for f in fails[:5]:
        print("  FAIL", f)


if __name__ == "__main__":
    main()
