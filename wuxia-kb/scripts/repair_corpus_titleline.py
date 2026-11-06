# -*- coding: utf-8 -*-
"""底本书名行统一修复（docs/49 §2.1/§五.5 的批量版；Phase 收尾 2026-11-05）。

背景：`split_novels.py`/`split_chapters.py` 把书名行写进部分书的 000/001 回文件夹首，
`generate_pn_wuxia` 的可逆性自检与 `lint_text_integrity` 要求底本首行即回目/楔子行（E6）。
先前仅人工修了《塞外奇侠传》《冰魄寒光剑》2 部；本脚本自动发现并批量修复其余同格式书。

识别规则：该书按文件名排序的第一个 .txt 文件，其首行 strip() == 书名 →
删除首行及其后紧随的空行（保留回目/楔子行成为新首行）。

用法：
  python scripts/repair_corpus_titleline.py            # dry-run（默认，列出 34 部书的判定）
  python scripts/repair_corpus_titleline.py --apply    # 备份后落盘
  python scripts/repair_corpus_titleline.py --book 广陵剑 --apply
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import config

BACKUP = config.ROOT / "backup" / "corpus_titleline_20261105"


def first_file(book: str) -> Path | None:
    d = config.CORPUS_ROOT / book
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.txt"))
    return files[0] if files else None


def scan(book: str) -> dict:
    p = first_file(book)
    if p is None:
        return {"book": book, "file": None, "need_fix": False, "reason": "无底本"}
    text = p.read_text(encoding="utf-8-sig")
    lines = text.split("\n")
    first = lines[0].strip() if lines else ""
    need = first == book
    # 新首行（删书名行 + 紧随空行）
    idx = 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    new_first = lines[idx].strip() if idx < len(lines) else ""
    return {
        "book": book,
        "file": p,
        "need_fix": need,
        "first": first,
        "new_first": new_first,
        "removed": idx if need else 0,
        "reason": "首行=书名行" if need else ("已正常" if first != book else "?"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="底本书名行统一修复（默认 dry-run）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--dry-run", action="store_true", help="默认行为，显式指定亦可")
    ap.add_argument("--book", default=None, help="只处理指定书")
    args = ap.parse_args()

    books = [args.book] if args.book else list(config.books().keys())
    targets = []
    for b in books:
        r = scan(b)
        if r["file"] is None:
            print(f"[skip] {b}: 无底本")
            continue
        rel = r["file"].relative_to(config.CORPUS_ROOT)
        if r["need_fix"]:
            targets.append(r)
            print(f"[need] {rel}: 首行 [{r['first']}] → 新首行 [{r['new_first'][:40]}]（删 {r['removed']} 行含空行）")
        else:
            print(f"[ok]   {rel}: 首行 [{r['first'][:40]}]")

    print(f"\n待修 {len(targets)} 部：{[t['book'] for t in targets]}")
    if not (args.apply and targets):
        if targets:
            print("（dry-run；加 --apply 落盘，备份", BACKUP, "）")
        return 0

    BACKUP.mkdir(parents=True, exist_ok=True)
    for r in targets:
        p: Path = r["file"]
        text = p.read_text(encoding="utf-8-sig")
        lines = text.split("\n")
        idx = 1
        while idx < len(lines) and lines[idx].strip() == "":
            idx += 1
        assert lines[0].strip() == r["book"], p
        assert idx < len(lines), f"{p}: 删行后无内容"
        backup_path = BACKUP / p.name
        if not backup_path.exists():
            shutil.copy2(p, backup_path)
        p.write_text("\n".join(lines[idx:]), encoding="utf-8")
        # 写后断言：新首行不再是书名、且不再是空行
        after = p.read_text(encoding="utf-8").split("\n")[0].strip()
        assert after and after != r["book"], (p, after)
        print(f"[ok] {p.name}: 新首行 [{after[:40]}]；备份 → {backup_path}")

    print(f"\n已修复 {len(targets)} 部，备份目录 {BACKUP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
