# -*- coding: utf-8 -*-
"""一次性：楔子（000 底本）struct 生成 —— 复用 generate_pn_wuxia.process_chapter 内核。

楔子底本文件名形如 `000　楔子　…….txt`，行首无"第N回"，被 config.CHAPTER_FILE_RE 与
TITLE_RE 排除在自动发现之外；本脚本对这两个入口做最小 monkeypatch 后复用原流水
（章首词探测/段落编号/围栏/回末检测/可逆性自检全部不变）。

用法：python scripts/_oneshot/make_struct_prologue.py --book 七剑下天山 [--verify]
产物：tagged/<书>/000.struct.md + 000.struct.json（sidecar chapter=0）
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config                    # noqa: E402
import generate_pn_wuxia as g    # noqa: E402


def find_prologue(book: str):
    """000 开头的底本文件（楔子）。"""
    d = config.corpus_dir(book)
    for p in sorted(d.glob("*.txt")):
        if p.name.startswith("000"):
            return p
    raise SystemExit(f"未找到楔子底本（000 开头）：{d}")


def main():
    ap = argparse.ArgumentParser(description="楔子(000) struct 生成（复用 N1 流水）")
    ap.add_argument("--book", required=True, help="书名（config.books() 键）")
    ap.add_argument("--verify", action="store_true", help="生成后重读产物做可逆性复核")
    args = ap.parse_args()

    path = find_prologue(args.book)
    g.TITLE_RE = re.compile(r"^\s*楔子")           # 楔子标题行（无"第N回"）
    g.config.chapter_path = lambda book_, no: path  # 本章定位到楔子底本
    s = g.process_chapter(args.book, 0, verify_flag=args.verify)
    print(f"{args.book} 楔子 → {s['path']}\n"
          f"  PN 总数 {s['pn_total']}；围栏 {len(s['fences'])} 处："
          + ("；".join(f"[{f['pn']}]{f['type']}({f.get('branch')},"
                      f"{f.get('score', '-')})" for f in s["fences"]) or "无")
          + f"；存疑 {len(s['doubts'])} 条；可逆性 {s['reversibility']}")
    for w in s["warnings"]:
        print(f"  [warning] {w}")
    for d_ in s["doubts"]:
        print(f"  [doubt] {d_['where']}: {d_['what']}")


if __name__ == "__main__":
    main()
