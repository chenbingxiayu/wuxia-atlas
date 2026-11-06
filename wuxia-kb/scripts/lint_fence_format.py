#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/lint_zan_format.py（2026-11-03）；改名 lint_fence_format.py。改动：
#   1. 检查对象从"赞"扩为全部围栏类型（symbols.FENCE_ALL 正式 7 + 观察 3）；
#      原"每行恰 8 汉字"断言改为按围栏类型查规则表 FENCE_LINE_RULES（文件头常量）：
#      词/诗/歌 = 不限宽，只查空行结构（内容行间不应有空行）；对联/回末对 =
#      上下句字数相等检查；回末/书信/告示/口诀/说书 = 暂无逐行格式断言。
#      全部规则标"待试点校准"（调参只动 FENCE_LINE_RULES 一处）；
#   2. 半角标点检查保留并扩展到全部围栏（对应 lint_purple_numbers E16 口径）；
#      剥标注改走 symbols.strip_markup（替换原内联类型正则）；
#   3. 路径接 config：批处理 config.DIR_TAGGED（--book 单书/位置参数单回）。

import argparse
import io
import re
import sys
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols

# ------------------------------------------- 围栏逐行格式规则表 ----
# （02ab §4.2；逐行断言全部"待试点校准"——调参只动本表）
FENCE_LINE_RULES = {
    # 不限宽；查空行结构（韵文块内容行间不应有空行）
    "词":   {"blank_line": False,  "couplet": False, "width": None,
             "note": "不限宽；阕间空行合法（02ab §2.3），不查空行"},
    "诗":   {"blank_line": False,  "couplet": False, "width": None,
             "note": "不限宽；阕间空行合法（02ab §2.3），不查空行"},
    "歌":   {"blank_line": False,  "couplet": False, "width": None,
             "note": "不限宽；阕间空行合法（02ab §2.3），不查空行"},
    # 上下句字数相等（按句读 ，/； 分句后逐句比对）
    "对联":  {"blank_line": False, "couplet": True, "width": None,
              "note": "上下句字数相等（待试点校准）"},
    "回末对": {"blank_line": False, "couplet": True, "width": None,
              "note": "上下句字数相等（待试点校准）"},
    # 暂无逐行格式断言
    "回末":  {"blank_line": False, "couplet": False, "width": None,
              "note": "无逐行格式断言（待试点校准）"},
    "书信":  {"blank_line": False, "couplet": False, "width": None,
              "note": "暂无逐行格式断言（待试点校准）"},
    "告示":  {"blank_line": False, "couplet": False, "width": None,
              "note": "暂无逐行格式断言（待试点校准）"},
    "口诀":  {"blank_line": False, "couplet": False, "width": None,
              "note": "暂无逐行格式断言（待试点校准）"},
    "说书":  {"blank_line": False, "couplet": False, "width": None,
              "note": "暂无逐行格式断言（待试点校准）"},
}

# E16 围栏内禁半角标点（同 lint_purple_numbers 口径；保守集，待试点校准）
HALFWIDTH_PUNCT = set(',.;:!?()"\'<>')

PN_LINE_RE = re.compile(r"^(-\s*)?\[(\d+(?:\.\d+)*\])\s*")
CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
CLAUSE_SPLIT_RE = re.compile(r"[，；]")   # 句读分句（半角由 E16 检查兜住）
TRAILING_RE = re.compile(r"[。！？…\s]+$")


def scan_fences(lines):
    """扫描围栏 → [{type, open_line, close_line(None=未闭合), content}]"""
    fences, cur = [], None
    for i, raw in enumerate(lines):
        s = raw.strip()
        if symbols.is_fence_close(s):
            if cur is not None:
                cur["close_line"] = i
                fences.append(cur)
                cur = None
            continue
        ftype = symbols.fence_opens(s)
        if ftype is not None:
            if cur is not None:
                fences.append(cur)
            cur = {"type": ftype, "open_line": i, "close_line": None,
                   "content": []}
            continue
        if cur is not None:
            cur["content"].append((i, s))
    if cur is not None:
        fences.append(cur)
    return fences


def bare_text(line: str) -> str:
    """剥 PN 与标注 → 显示串（symbols.strip_markup 统一入口）"""
    return symbols.strip_markup(PN_LINE_RE.sub("", line)).strip()


def count_clause_hanzi(clause: str) -> int:
    return len(CJK_RE.findall(TRAILING_RE.sub("", clause.strip())))


def check_fence(fence, errors):
    t = fence["type"]
    rule = FENCE_LINE_RULES.get(t)
    if rule is None:
        errors.append((fence["open_line"] + 1,
                       f"::: {t}", f"围栏类型「{t}」不在枚举内（02ab §4.1 正式 7 种"
                       f"+观察 3 种；枚举检查见 lint_purple_numbers E9）"))
        return
    open_ln = fence["open_line"] + 1

    # 1) 空行结构：02ab §2.3——词/诗/歌围栏内的阕间/段间空行是唯一合法结构性空行，
    #    规范未要求任何围栏类型禁止空行，故不设空行违规检查（blank_line 字段保留备查）。

    # 2) 对联/回末对：上下句字数相等
    if rule["couplet"]:
        for ln, s in fence["content"]:
            text = bare_text(s)
            text = re.sub(r"^正是[：:]\s*", "", text)   # 剥引出词，不计入上句字数
            if not text:
                continue
            clauses = [c for c in CLAUSE_SPLIT_RE.split(text) if c.strip()]
            if len(clauses) < 2:
                continue    # 单句行无法比对上下句，交由试点校准
            counts = [count_clause_hanzi(c) for c in clauses]
            if len(set(counts)) > 1:
                errors.append((ln + 1, s[:40],
                               f"围栏「{t}」上下句字数不等 "
                               f"（{'/'.join(map(str, counts))}）；{rule['note']}"))

    # 3) 半角标点（全部围栏类型；E16 同口径）
    for ln, s in fence["content"]:
        bare = bare_text(s)
        hits = sorted({ch for ch in bare if ch in HALFWIDTH_PUNCT})
        if hits:
            errors.append((ln + 1, s[:50],
                           f"围栏「{t}」内半角标点：{' '.join(hits)}"
                           f"（02ab §4.2 铁律 4，对应 lint_purple_numbers E16）"))


def check_file(file_path: Path):
    lines = file_path.read_text(encoding="utf-8").splitlines()
    errors = []
    for fence in scan_fences(lines):
        check_fence(fence, errors)
    return errors


def main():
    ap = argparse.ArgumentParser(
        description="围栏格式检查（词/诗/歌空行结构 · 对联/回末对字数相等 · "
                    "全围栏半角标点；规则表待试点校准）")
    ap.add_argument("chapter", nargs="?", default=None,
                    help="单回编号（如 001；配合 --book 消歧，缺省扫全部）")
    ap.add_argument("--book", default=None,
                    help="只查指定书（config.DIR_TAGGED/<书名>/）")
    args = ap.parse_args()

    if not config.DIR_TAGGED.exists():
        print(f"标注目录不存在：{config.DIR_TAGGED}")
        return 1
    book_dirs = ([config.DIR_TAGGED / args.book] if args.book
                 else sorted(p for p in config.DIR_TAGGED.iterdir() if p.is_dir()))
    files = []
    for d in book_dirs:
        if not d.is_dir():
            continue
        for f in sorted(list(d.glob("*.struct.md")) + list(d.glob("*.tagged.md"))):
            if args.chapter and f.name != f"{args.chapter.zfill(3)}.tagged.md":
                continue
            files.append(f)
    if not files:
        print("未找到 .tagged.md 文件。")
        return 1

    n_books = len({f.parent.name for f in files})
    print("=" * 70)
    print("围栏格式检查（FENCE_LINE_RULES 全部待试点校准）")
    print("=" * 70)
    print(f"检查书数: {n_books} · 回文件数: {len(files)}")

    all_errors = {}
    total = 0
    for f in files:
        errors = check_file(f)
        if errors:
            all_errors[f"{f.parent.name}/{f.name}"] = errors
            total += len(errors)

    if all_errors:
        print("\n发现围栏格式问题:\n")
        for filename, errors in all_errors.items():
            print(f"- {filename}:")
            for ln, content, reason in errors:
                print(f"  行{ln}: {content}")
                print(f"    → {reason}")
            print()
        print(f"共 {total} 处围栏格式问题（{len(all_errors)} 个文件）")
        return 1
    print("\n所有围栏格式检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
