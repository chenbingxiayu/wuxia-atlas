# -*- coding: utf-8 -*-
"""一次性：从旧标注（kb/tagged/<书>，wuxia-tagged-v0.2，无 PN）抽取 @ 人物管道映射，
按回累积生成每回《已核准映射表》快照，供 annotate_chapter_llm.py --mapping-file 并行批次用。

规则（2026-11-05 江湖三女侠首次使用）：
  1. 只取 〖@显示串|规范名〗；显示串、规范名均非空且不同；
  2. 单字显示串不收（歧义过大，留交登记层人工核准；新方法 D1 口径也不支持凭单字猜名）；
  3. 第 N 回的映射表 = 第 1..N-1 回旧标注中已出现的映射（模拟顺序标注时的累积核准），
     不引入本回及以后才出现的身份揭示，避免"未来知识"泄漏；
  4. 同一显示串多个规范名时，按累积出现次数取多者（并列取先出现者）；
  5. 排序按 (-len(显示串), 显示串)，与 annotate_chapter_llm.mapping_text 的截断顺序一致。

用法：
    python scripts/_oneshot/build_legacy_mapping.py 江湖三女侠
产物：
    logs/mapping_<书>/ch_NNN.json   每回快照（[[显示串, 规范名], ...]）
    logs/mapping_<书>/summary.md    统计
"""
from __future__ import annotations

import glob
import io
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

PIPE_RE = re.compile(r"〖@([^〖〗|]+)\|([^〖〗|]+)〗")


def legacy_dir(book: str) -> Path:
    return config.REPO_ROOT / "kb" / "tagged" / book


def chapter_files(book: str) -> dict:
    out = {}
    for p in glob.glob(str(legacy_dir(book) / "*.tagged.md")):
        name = os.path.basename(p)
        m = re.match(r"^(\d{1,3})_", name)
        if m:
            out[int(m.group(1))] = Path(p)
    return out


def main():
    book = sys.argv[1] if len(sys.argv) > 1 else config.PILOT_BOOK
    files = chapter_files(book)
    if not files:
        raise SystemExit(f"旧标注目录无 *.tagged.md：{legacy_dir(book)}")
    total = max(files)
    out_dir = config.DIR_LOGS / f"mapping_{book}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 逐回抽取本回新增映射（首次遇到即登记，次数并行累计）
    per_ch = {}
    for ch in range(1, total + 1):
        pairs = PIPE_RE.findall(io.open(files[ch], encoding="utf-8").read()) if ch in files else []
        per_ch[ch] = pairs

    acc_disp = Counter()          # display -> count
    acc_canon = {}                # display -> Counter(canonical)
    seen = set()
    summary = []
    for ch in range(1, total + 1):
        # 第 ch 回的映射表只含前 ch-1 回（空映射用于第 1 回）
        snapshot = []
        for disp, cnt in acc_disp.items():
            canon_cnt = acc_canon[disp]
            canon = canon_cnt.most_common(1)[0][0]
            snapshot.append([disp, canon])
        snapshot.sort(key=lambda kv: (-len(kv[0]), kv[0]))
        io.open(out_dir / f"ch_{ch:03d}.json", "w", encoding="utf-8", newline="\n").write(
            json.dumps(snapshot, ensure_ascii=False, indent=0))
        summary.append((ch, len(snapshot), len(per_ch[ch])))
        # 把本回映射并入累计（单字显示串不收）
        for disp, canon in per_ch[ch]:
            disp, canon = disp.strip(), canon.strip()
            if not disp or not canon or disp == canon or len(disp) < 2:
                continue
            acc_disp[disp] += 1
            acc_canon.setdefault(disp, Counter())[canon] += 1

    lines = [f"# 旧标注 → 《已核准映射表》快照（{book}）", "",
             f"- 旧标注目录：`{legacy_dir(book)}`",
             f"- 回数：{total}；快照目录：`{out_dir}`",
             "- 口径：第 N 回快照 = 第 1..N-1 回旧标注 @ 管道累积；单字显示串不收", "",
             "| 回 | 快照条数 | 本回旧标注管道数 |", "|---|---|---|"]
    lines += [f"| {ch:03d} | {n} | {k} |" for ch, n, k in summary]
    io.open(out_dir / "summary.md", "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print(f"[ok] {book}: {total} 回快照 → {out_dir}")
    print(f"     首回 {len(summary[0])} 条 / 末回前 {summary[-2][1]} 条 / 末回 {summary[-1][1]} 条")


if __name__ == "__main__":
    main()
