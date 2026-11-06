# -*- coding: utf-8 -*-
"""同位复指形人名合并：〖@绰号|本名〗本名 → 〖@绰号本名|本名〗（docs/54-0611 §六.2）。

背景：03a 连写规则（DEF-12，SKILL_03a）规定绰号+本名连写时"显示串覆盖全区间、
本名入管道"。标注期部分章回写成 `〖@铁掌神弹|杨仲英〗杨仲英`（绰号独占标签、
本名裸文本紧跟），即"同位复指形"，三书百+ 处。本脚本把它合并为单标签
`〖@铁掌神弹杨仲英|杨仲英〗`——显示串=原文区间全文，正文零增删。

范围纪律：
  * 默认 5 部在册稳定书；《冰川天女传》由外部会话在写，**一律排除**（--books 可覆盖）；
  * 只动 `tagged/<书>/NNN.tagged.md`；`tagged/_xval/**` 不在扫描范围；
  * 写前逐文件备份 → logs/backup/merge_apposition_<时间戳>/<书>/<回>.tagged.md；
  * 写前断言：symbols.strip_markup 前后逐字一致（合并后本名留在显示串内，剥标相等）；
  * 异常守卫：显示串已以规范名结尾、或合并后超长（>24 字）的命中不写、单列报告。

用法：python scripts/merge_apposition_names.py [--apply] [--books 书1,书2]
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

# 同位复指形：@标签（绰号|本名）后紧跟裸文本本名（仅限紧邻，有标点/空白即两次提及，不动）
APPOSITION_RE = re.compile(r"〖@([^〖〗|]+)\|([^〖〗|]+)〗\2")
MAX_HEAD = 24
STABLE_BOOKS = ["白发魔女传", "江湖三女侠", "七剑下天山", "塞外奇侠传", "冰魄寒光剑"]


def main() -> int:
    ap = argparse.ArgumentParser(description="同位复指形人名合并（DEF-12 单标签化）")
    ap.add_argument("--apply", action="store_true", help="默认 dry-run")
    ap.add_argument("--books", default=",".join(STABLE_BOOKS), help="书名逗号分隔（默认 5 部稳定书）")
    args = ap.parse_args()
    books = [b.strip() for b in args.books.split(",") if b.strip()]

    backup_root = None
    if args.apply:
        backup_root = config.DIR_LOGS / "backup" / \
            f"merge_apposition_{datetime.now():%Y%m%d_%H%M%S}"

    per_book: dict[str, int] = {}
    anomalies: list[str] = []
    files_changed = 0
    for book in books:
        book_dir = config.DIR_TAGGED / book
        if not book_dir.is_dir():
            print(f"[skip] 无目录：{book}")
            continue
        for path in sorted(book_dir.glob("*.tagged.md")):
            text = path.read_text(encoding="utf-8")
            n_here = 0
            anomalies_here: list[str] = []

            def repl(m: re.Match) -> str:
                nonlocal n_here
                head, canon = m.group(1), m.group(2)
                if head.endswith(canon):
                    anomalies_here.append(f"{path.name}: 显示串已含本名：{m.group(0)}")
                    return m.group(0)
                merged = f"〖@{head}{canon}|{canon}〗"
                if len(head) + len(canon) > MAX_HEAD:
                    anomalies_here.append(f"{path.name}: 合并超长：{m.group(0)}")
                    return m.group(0)
                n_here += 1
                return merged

            new = APPOSITION_RE.sub(repl, text)
            if n_here == 0 and not anomalies_here:
                continue
            if n_here == 0:
                anomalies.extend(anomalies_here)
                continue
            # 断言：正文零增删（本名由裸文本并入显示串，剥标相等）
            assert symbols.strip_markup(new) == symbols.strip_markup(text), \
                f"{path} 剥标不一致，拒写"
            per_book[book] = per_book.get(book, 0) + n_here
            anomalies.extend(anomalies_here)
            print(f"  {book}/{path.name}: {n_here} 处")
            if args.apply:
                bdir = backup_root / book
                bdir.mkdir(parents=True, exist_ok=True)
                if not (bdir / path.name).exists():
                    shutil.copy2(path, bdir / path.name)
                io.open(path, "w", encoding="utf-8", newline="\n").write(new)
                files_changed += 1

    total = sum(per_book.values())
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n[{mode}] 合计 {total} 处合并；按书 {per_book}")
    if anomalies:
        print(f"[anomaly] {len(anomalies)} 处未动（守卫拦截）：")
        for a in anomalies:
            print("  -", a)
    if args.apply:
        print(f"[ok] 备份 → {backup_root}（{files_changed} 文件）")
    else:
        print("(dry-run；确认后加 --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
