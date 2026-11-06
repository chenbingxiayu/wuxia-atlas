#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/lint_heading_numbers.py（2026-11-03）；改动：
#   1. 路径改经 config：扫 config.DIR_TAGGED/<书>/NNN.tagged.md（新增 --book 单书），
#      原 chapter_md 相对路径删除；
#   2. 措辞"篇名"→"回目"（# [0] 回目行合法，02ab §2.2）；
#   3. 检测逻辑不变：##/### 标题不含编号（本移植同时覆盖 ##-###### 深层标题，
#      与 lint_purple_numbers E4 同口径）。

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

HEADING_PN_RE = re.compile(r"^(#{2,6})\s+\[(\d+(?:\.\d+)*)\]\s+(.+)$")


def check_heading_numbers(file_path):
    """检查文件中标题是否包含段落编号"""
    errors = []

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 跳过一级标题（# [0] 回目是合法的，02ab §2.2）
        if stripped.startswith('# '):
            continue

        # 检测二级及更深标题中的编号
        match = HEADING_PN_RE.match(stripped)
        if match:
            level = len(match.group(1))
            errors.append({
                'line': i + 1,
                'original': stripped,
                'pn': match.group(2),
                'title': match.group(3),
                'level': level,
                'fixed': f"{'#' * level} {match.group(3)}"
            })

    return errors


def main():
    parser = argparse.ArgumentParser(description="标题编号检查（##/### 不含 [N]）")
    parser.add_argument('--book', default=None,
                        help="只查指定书（config.DIR_TAGGED/<书名>/）")
    args = parser.parse_args()

    if not config.DIR_TAGGED.exists():
        print(f"标注目录不存在：{config.DIR_TAGGED}")
        return 1

    if args.book:
        book_dirs = [config.DIR_TAGGED / args.book]
        if not book_dirs[0].is_dir():
            print(f"未找到书目录：{book_dirs[0]}")
            return 1
    else:
        book_dirs = sorted(p for p in config.DIR_TAGGED.iterdir() if p.is_dir())

    tagged_files = []
    for d in book_dirs:
        tagged_files.extend(sorted(d.glob('*.tagged.md')))

    total_errors = 0
    files_with_errors = []

    print("=" * 80)
    print("标题编号检查报告")
    print("=" * 80)
    print()

    for file_path in tagged_files:
        errors = check_heading_numbers(file_path)

        if errors:
            total_errors += len(errors)
            files_with_errors.append((file_path.name, errors))

            print(f"【{file_path.name}】发现 {len(errors)} 处错误")
            print("-" * 80)

            for err in errors:
                print(f"  行 {err['line']}: {err['original']}")
                print(f"    → 应改为: {err['fixed']}")
                print(f"    → 编号 [{err['pn']}] 应该移除")
                print()

            print()

    # 汇总报告
    print("=" * 80)
    print("汇总")
    print("=" * 80)
    print(f"检查文件数: {len(tagged_files)}")
    print(f"有错误的文件数: {len(files_with_errors)}")
    print(f"错误总数: {total_errors}")
    print()

    if files_with_errors:
        print("有错误的文件列表:")
        for filename, errors in files_with_errors:
            print(f"  - {filename}: {len(errors)}处错误")
        print()
        return 1
    else:
        print("✓ 所有文件检查通过！")
        return 0


if __name__ == '__main__':
    sys.exit(main())
