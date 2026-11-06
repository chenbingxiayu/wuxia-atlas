# -*- coding: utf-8 -*-
"""B1-1 翻案执行器：泛称"武功/武艺/功夫"不标（2026-11-05 用户拍板，docs/63 §七）。

背景：01g 附录 B1-1 曾裁"总称→`^`"，SKILL_03a v1.6 P3-1 则一直规定"泛称武功不入 ^"。
2026-11-05 晚用户拍板**泛称不标**（03a 口径胜出）：泛指武学能力的"武功/武艺/功夫"
一律裸文本。本脚本把 5 部在册书 tagged 中的 〖^武功〗〖^武艺〗〖^功夫〗（含带管道
变体）整 token 摘除为裸词。

范围纪律：
  * 只动 `tagged/<书>/NNN.tagged.md`（5 部在册书）；`tagged/_xval/**`（含
    _backup_rhetoric 备份与历史一次性脚本）**一律不动**；
  * 写前逐文件备份 → logs/backup/strip_generic_wugong_<时间戳>/<书>/<回>.tagged.md；
  * 写前断言：摘标后 `symbols.strip_markup` 前后逐字一致（正文零增删，仅去符号）；
  * 词表侧零改动：`wordlists/new_entity_types_source.md` 负规则本就列明
    "通名不标（…武功/功夫…）"，无词表回填需要。

用法：python scripts/_oneshot/strip_generic_wugong_tokens.py [--apply]
"""
import argparse
import io
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
import config      # noqa: E402
import symbols     # noqa: E402

# 泛称能力域总称（B1-1 翻案范围；〖^上乘〗〖^穴道〗等非泛称 ^ 令牌不在范围内）
GENERIC_RE = re.compile(r"〖\^(武功|武艺|功夫)(?:\|[^〗]*)?〗")
BOOKS = ["白发魔女传", "江湖三女侠", "七剑下天山", "塞外奇侠传", "冰魄寒光剑"]


def main() -> int:
    ap = argparse.ArgumentParser(description="摘除泛称 ^武功/武艺/功夫 令牌（B1-1 翻案）")
    ap.add_argument("--apply", action="store_true", help="默认 dry-run")
    args = ap.parse_args()

    backup_root = None
    if args.apply:
        backup_root = config.DIR_LOGS / "backup" / \
            f"strip_generic_wugong_{datetime.now():%Y%m%d_%H%M%S}"

    per_book: dict[str, int] = {}
    per_word: dict[str, int] = {}
    files_changed = 0
    for book in BOOKS:
        book_dir = config.DIR_TAGGED / book
        if not book_dir.is_dir():
            print(f"[skip] 无目录：{book}")
            continue
        for path in sorted(book_dir.glob("*.tagged.md")):
            text = path.read_text(encoding="utf-8")
            hits = GENERIC_RE.findall(text)
            if not hits:
                continue
            new = GENERIC_RE.sub(lambda m: m.group(1), text)
            n = len(hits)
            # 断言：仅去符号，正文逐字不变
            assert symbols.strip_markup(new) == symbols.strip_markup(text), \
                f"{path} 剥标不一致，拒写"
            per_book[book] = per_book.get(book, 0) + n
            for w in hits:
                per_word[w] = per_word.get(w, 0) + 1
            print(f"  {book}/{path.name}: {n} 处")
            if args.apply:
                bdir = backup_root / book
                bdir.mkdir(parents=True, exist_ok=True)
                if not (bdir / path.name).exists():
                    shutil.copy2(path, bdir / path.name)
                io.open(path, "w", encoding="utf-8", newline="\n").write(new)
                files_changed += 1

    total = sum(per_book.values())
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n[{mode}] 合计 {total} 处 token 摘除；按书 {per_book}；按词 {per_word}")
    if args.apply:
        print(f"[ok] 备份 → {backup_root}（{files_changed} 文件）")
    else:
        print("(dry-run；确认后加 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
