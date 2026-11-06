# -*- coding: utf-8 -*-
"""按验收 hard_errors 逐处摘除误标 —— 回末套语段（tao_token）负规则修复。

换书标准工具（原 scripts/_oneshot/repair_tao_tokens.py 正式化，docs/50 S12）。
来源：registry/acceptance/<书>_*.json 的 hard_errors（type=tao_token）：
回末套语段（"欲知后事如何…"）按 02ab §4.4 负规则不得有任何标注；
生成结构时部分变体未被围栏识别，模型遂按正文误标 → 机械摘除该段全部令牌（保留显示串）。

纪律：只动指定 回/段 的令牌括号与类型码；显示串与正文零改动 → 剥标逐字断言；--apply 前备份。
用法：
    python -X utf8 scripts/repair_tao_tokens.py <书名> \
        --acceptance registry/acceptance/<书>_001-0NN.json [--apply]
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import symbols  # noqa: E402

PARA_RE = re.compile(r"^\[(\d+)\] (.*)$")
TOKEN_RE = symbols.TOKEN_RE


def _strip(text: str) -> str:
    def repl(m):
        body = m.group(0)
        inner = body[1:-1]
        rest = inner[1:] if len(inner) > 1 else ""
        disp = rest.split("|", 1)[0]
        return disp
    return TOKEN_RE.sub(repl, text)


def main() -> int:
    ap = argparse.ArgumentParser(description="回末套语段 tao_token 误标摘除（换书工具）")
    ap.add_argument("book", help="书名（tagged/<书> 同名）")
    ap.add_argument("--acceptance", required=True, help="验收 JSON 路径")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    data = json.loads(io.open(args.acceptance, encoding="utf-8").read())
    analyses = data.get("chapters_data") or {}
    targets = defaultdict(set)
    for key, a in analyses.items():
        for h in a.get("hard_errors", []):
            if h.get("type") in ("tao_token",):
                ch = int(a.get("chapter") or key)
                targets[ch].add(int(h["pn"]))
    if not targets:
        raise SystemExit("验收 JSON 中无 tao_token 硬错误")
    print("目标：", {k: sorted(v) for k, v in targets.items()})
    d = config.DIR_TAGGED / args.book
    backup = config.DIR_LOGS / "backup" / f"repair_tao_{args.book}"
    total = 0
    for ch, pns in sorted(targets.items()):
        p = d / f"{ch:03d}.tagged.md"
        lines = io.open(p, encoding="utf-8").read().split("\n")
        n = 0
        for i, ln in enumerate(lines):
            m = PARA_RE.match(ln)
            if not m or int(m.group(1)) not in pns:
                continue
            before = m.group(2)
            after = _strip(before)
            if after != before:
                lines[i] = f"[{m.group(1)}] {after}"
                n += before.count("〖") + before.count("⟦") + before.count("〘")
        if not n:
            continue
        new_text = "\n".join(lines)
        t = io.open(p, encoding="utf-8").read()
        if symbols.strip_markup(new_text) != symbols.strip_markup(t):
            raise SystemExit(f"{p.name} 剥标不一致，中止")
        if args.apply:
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, backup / p.name)
            io.open(p, "w", encoding="utf-8", newline="\n").write(new_text)
        total += n
        print(f"  {ch:03d}: 摘除段 {sorted(pns)} 令牌 {n} 个")
    print(f"[{'apply' if args.apply else 'dry-run'}] 共摘除 {total} 个令牌")
    return 0


if __name__ == "__main__":
    sys.exit(main())
