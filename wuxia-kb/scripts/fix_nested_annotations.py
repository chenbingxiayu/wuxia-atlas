#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/fix_nested_annotations.py（2026-11-03）；改动：
#   1. 嵌套检测正则不再内联实体字符类，改按 symbols.TOKEN_RE 语义由
#      ENTITY/VERB/RHETORIC_CODES + BRACKETS 动态构建：三层括号（〖〗⟦⟧〘〙）
#      互不嵌套、互不交叉——同层互嵌（如 〖@练〖=天山〗霓裳〗）与跨层交叉
#      （如 ⟦⊞…〖@剑〗…⟧）均检测；
#   2. 修复建议保持原文风格：同层嵌套照原版规则取外层类型、合并内容；
#      跨层交叉保留外层令牌、内层取显示串（去类型码、去 |消歧说明），
#      不改写底本汉字；
#   3. 路径接 config：批处理 config.DIR_TAGGED（新增 --book 单书、
#      --dry-run 预览；原版无 CLI 参数、路径写死 chapter_md）。

import argparse
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols

# ------------------------------------------- 按 symbols 构建嵌套模式 ----
def _cls(codes):
    return "[" + "".join(re.escape(c) for c in sorted(codes)) + "]"


# 三层括号（TOKEN_RE 语义：令牌体不含任何一层括号字符）
_ALL_BRACKETS = "\u3016\u3017\u27e6\u27e7\u3018\u3019"   # 〖〗⟦⟧〘〙
_NOT_BRACKET = "[^" + _ALL_BRACKETS + "]*?"

LAYERS = [
    ("entity", *symbols.BRACKETS["entity"], symbols.ENTITY_CODES),
    ("verb", *symbols.BRACKETS["verb"], symbols.VERB_CODES),
    ("rhetoric", *symbols.BRACKETS["rhetoric"], symbols.RHETORIC_CODES),
]

# 同层互嵌：外层类型 + 前缀 + 内层令牌 + 后缀 + 外层闭合
SAME_LAYER_RES = [
    (name, re.compile(
        re.escape(op) + "(" + _cls(codes) + ")(" + _NOT_BRACKET + ")"
        + re.escape(op) + "(" + _cls(codes) + ")(" + _NOT_BRACKET + ")"
        + re.escape(cl) + "(" + _NOT_BRACKET + ")" + re.escape(cl)))
    for name, op, cl, codes in LAYERS
]

# 跨层交叉：外层令牌体内出现内层完整令牌（6 组有序对）
CROSS_RES = [
    (outer[0], inner[0], re.compile(
        re.escape(outer[1]) + "(" + _cls(outer[3]) + ")(" + _NOT_BRACKET + ")"
        + re.escape(inner[1]) + "(" + _cls(inner[3]) + ")([^"
        + re.escape(inner[1]) + re.escape(inner[2]) + "]+)"
        + re.escape(inner[2]) + "(" + _NOT_BRACKET + ")"
        + re.escape(outer[2])))
    for outer in LAYERS for inner in LAYERS if outer[1] != inner[1]
]


def _display(body: str) -> str:
    """内层令牌体的显示串：去类型码，去 |消歧说明（保持原文风格，不改字）"""
    rest = body[1:]
    return rest.split(symbols.PIPE, 1)[0] if symbols.PIPE in rest else rest


def fix_nested_annotations(text: str):
    """修复文本中的嵌套/交叉标注

    Returns:
        (修复后的文本, 修复数量, 修复模式统计)
    """
    fixed_count = 0
    pattern_stats = defaultdict(int)

    def same_layer_replace(name, match):
        nonlocal fixed_count
        type1, prefix = match.group(1), match.group(2)
        _type2, inner = match.group(3), match.group(4)
        suffix = match.group(5)
        pattern_stats[f"同层嵌套[{name}] 〖T1…〖T2…〗…〗"] += 1
        fixed_count += 1
        # 规则1: 外层无前缀后缀 → 保留外层类型（〖^〖_仁义〗〗→〖^仁义〗）
        # 规则2: 有前缀/后缀 → 内层内容合并进外层（〖@司〖~马〗季主〗→〖@司马季主〗）
        combined = prefix + inner + suffix
        op, cl = next((op, cl) for n, op, cl, _ in LAYERS if n == name)
        return f"{op}{type1}{combined}{cl}"

    def cross_replace(outer_name, inner_name, match):
        nonlocal fixed_count
        type1, prefix = match.group(1), match.group(2)
        _type2, inner_body = match.group(3), match.group(4)
        suffix = match.group(5)
        pattern_stats[f"跨层交叉[{outer_name}∋{inner_name}]"] += 1
        fixed_count += 1
        # 保留外层令牌，内层取显示串（不改写底本汉字）
        op, cl = next((op, cl) for n, op, cl, _ in LAYERS if n == outer_name)
        return f"{op}{type1}{prefix}{_display(inner_body)}{suffix}{cl}"

    # 多次替换，直到没有嵌套为止（处理多层嵌套）
    max_iterations = 10
    for _ in range(max_iterations):
        new_text = text
        for name, rex in SAME_LAYER_RES:
            new_text = rex.sub(lambda m, n=name: same_layer_replace(n, m), new_text)
        for out_name, in_name, rex in CROSS_RES:
            new_text = rex.sub(
                lambda m, o=out_name, i=in_name: cross_replace(o, i, m), new_text)
        if new_text == text:
            break
        text = new_text

    return text, fixed_count, dict(pattern_stats)


def fix_file(file_path: Path, dry_run: bool = False):
    """修复单个文件中的嵌套标注 → (修复数量, 修复模式统计)"""
    content = file_path.read_text(encoding="utf-8")
    new_content, fixed_count, pattern_stats = fix_nested_annotations(content)
    if new_content != content and not dry_run:
        file_path.write_text(new_content, encoding="utf-8")
    return fixed_count, pattern_stats


def main():
    ap = argparse.ArgumentParser(
        description="拍平嵌套/交叉标注（symbols.TOKEN_RE 语义：三层括号互不嵌套）")
    ap.add_argument("--book", default=None,
                    help="只处理指定书（config.DIR_TAGGED/<书名>/；缺省全库）")
    ap.add_argument("--dry-run", action="store_true",
                    help="仅预览统计，不写入文件")
    args = ap.parse_args()

    if not config.DIR_TAGGED.exists():
        print(f"标注目录不存在: {config.DIR_TAGGED}")
        return 1
    book_dirs = ([config.DIR_TAGGED / args.book] if args.book
                 else sorted(p for p in config.DIR_TAGGED.iterdir() if p.is_dir()))
    tagged_files = []
    for d in book_dirs:
        if d.is_dir():
            tagged_files.extend(sorted(d.glob("*.tagged.md")))

    if not tagged_files:
        print("未找到任何 .tagged.md 文件")
        return 1

    print(f"找到 {len(tagged_files)} 个文件"
          f"{'（预览模式）' if args.dry_run else ''}")
    print("=" * 60)

    total_files_fixed = 0
    total_fixed = 0
    total_pattern_stats = defaultdict(int)

    for file_path in tagged_files:
        fixed_count, pattern_stats = fix_file(file_path, dry_run=args.dry_run)
        if fixed_count > 0:
            total_files_fixed += 1
            total_fixed += fixed_count
            for pattern, count in pattern_stats.items():
                total_pattern_stats[pattern] += count
            print(f"\n✓ {file_path.parent.name}/{file_path.name}")
            print(f"   修复 {fixed_count} 处嵌套标注")
            top_patterns = sorted(pattern_stats.items(),
                                  key=lambda x: x[1], reverse=True)[:3]
            for pattern, count in top_patterns:
                print(f"   - {pattern}: {count}处")

    print("\n" + "=" * 60)
    print("修复完成:")
    print(f"   - 修复文件数: {total_files_fixed}")
    print(f"   - 修复总数: {total_fixed}")

    if total_pattern_stats:
        print("\n嵌套模式统计（Top 10）:")
        top_patterns = sorted(total_pattern_stats.items(),
                              key=lambda x: x[1], reverse=True)[:10]
        for pattern, count in top_patterns:
            print(f"   - {pattern}: {count}处")

    print("\n建议:")
    print("   1. 运行验证: python scripts/lint_symbol_conflicts.py --check-types nested")
    print("   2. 使用 git diff 检查修改是否正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
