#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/tag_quantity_entities.py（2026-11-03）；改动：
#   1. 外置词表模式：量词/数量模式词表改读 --wordlist quantity（缺省即该表），
#      经 masker.load_wordlist 消费 wordlists/quantity.json（词表是数据不是代码；
#      原版读 kg/quantity/data/quantity_wordlist.json 的 always_quantity 嵌套结构）；
#   2. 正则核心（数字+量词）保留，但量词集合来自词表（词表单字 surface = 量词，
#      多字 surface = 整串数量模式词，走 masker.find_candidates 最长匹配）；
#   3. 已有标注保护改用 symbols.TOKEN_RE（原版内联 17 类字符类）；
#   4. 围栏内容行跳过（02ab §4.4：词/诗/歌等围栏标注豁免，数量不自动补标）；
#      回目/PN 行保护照搬；
#   5. 路径接 config：批处理 config.DIR_TAGGED（--book 单书/--chapter 单回/
#      --dry-run 预览），替换原 chapter_md + --all 互斥组。

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
import masker

# 数词字符（正则核心的"数字"半边；量词半边来自词表单字 surface）
NUM_CHARS = "零一二三四五六七八九十百千万亿两数几半0123456789"

TAGGED_FILE_RE = re.compile(r"^(\d{1,3})\.tagged\.md$")


def load_quantity_resources(wordlist_name: str):
    """加载量词词表 → (整串 matcher, 量词单字集合)

    词表约定（wordlists/quantity_source.md）：单字 surface=量词（进数字+量词
    正则），多字 surface=数量模式词（整串最长匹配）。
    """
    wl_path = config.DIR_WORDLISTS / f"{wordlist_name}.json"
    if not wl_path.exists():
        print(f"词表不存在：{wl_path}（先跑 python wordlist_compiler.py "
              f"--name {wordlist_name}）")
        sys.exit(1)
    matcher = masker.load_wordlist(wl_path, field="surface")
    measures = sorted({w for words in matcher["index"].values()
                       for w in words if len(w) == 1})
    num_measure_re = re.compile(
        "([" + re.escape(NUM_CHARS) + "]+)"
        "([" + "".join(re.escape(c) for c in measures) + "])")
    return matcher, measures, num_measure_re


def fence_line_set(lines):
    """围栏内容行号集合（0-based；含围栏标记行）——数量实体不在围栏内补标"""
    fenced = set()
    cur = False
    for i, raw in enumerate(lines):
        s = raw.strip()
        if cur:
            fenced.add(i)
            if symbols.is_fence_close(s):
                cur = False
        elif symbols.fence_opens(s) is not None:
            fenced.add(i)
            cur = True
    return fenced


def tag_line(line, matcher, num_measure_re, stats):
    """对单行文本进行数量标注（保护已有标注与 PN；从后往前插入避免偏移）"""
    if line.startswith("#") or not line.strip():
        return line

    # 已有标注区间（symbols.TOKEN_RE 语义）
    protected = [(m.start(), m.end()) for m in symbols.TOKEN_RE.finditer(line)]
    # PN 行首编号 [N]/[N.M] 也是保护区
    m = re.match(r"^(\s*)(\[\d+(?:\.\d+)*\])", line)
    if m:
        protected.append((m.start(2), m.end(2)))

    def is_protected(pos, length):
        return any(not (pos + length <= ps or pos >= pe) for ps, pe in protected)

    matches = []
    matched_ranges = []

    def overlaps_matched(pos, length):
        return any(not (pos + length <= ms or pos >= me)
                   for ms, me in matched_ranges)

    # 1) 正则核心：数字串+量词（量词集合来自词表）
    for m in num_measure_re.finditer(line):
        pos, end = m.start(), m.end()
        if is_protected(pos, end - pos) or overlaps_matched(pos, end - pos):
            continue
        matches.append((pos, end, m.group(0)))
        matched_ranges.append((pos, end))
        stats[m.group(0)] += 1

    # 2) 词表整串匹配（数量模式词，masker 最长优先不重叠）
    #    2026-11-04 修：单字 surface 是"量词"，只应参与上面 数字+量词 正则，不能单独
    #    整串匹配——否则"把/石/里/年/成/折"等每个单字都会被误标 〖$X〗（020 试跑实测
    #    179 处误标，修复后仅保留多字数量模式词）。
    for word, pos, end in masker.find_candidates(line, matcher):
        if len(word) <= 1:
            continue
        if is_protected(pos, end - pos) or overlaps_matched(pos, end - pos):
            continue
        matches.append((pos, end, word))
        matched_ranges.append((pos, end))
        stats[word] += 1

    if not matches:
        return line

    # 从后往前插入标注（避免偏移问题）；数量实体码 symbols'$'（ENTITIES 定版）
    qty = "$" if "$" in symbols.ENTITY_CODES else sorted(symbols.ENTITY_CODES)[0]
    matches.sort(key=lambda x: x[0], reverse=True)
    result = line
    for ms, me, word in matches:
        result = result[:ms] + f"〖{qty}{word}〗" + result[me:]
    return result


def process_chapter(chapter_file: Path, matcher, num_measure_re,
                    dry_run=False):
    content = chapter_file.read_text(encoding="utf-8")
    lines = content.split("\n")
    fenced = fence_line_set(lines)
    stats = defaultdict(int)
    new_lines = []
    for i, line in enumerate(lines):
        if i in fenced:
            new_lines.append(line)   # 围栏内容与标记行跳过
            continue
        new_lines.append(tag_line(line, matcher, num_measure_re, stats))

    total = sum(stats.values())
    if total > 0:
        name = f"{chapter_file.parent.name}/{chapter_file.name}"
        print(f"  {name}: {total} 处标注 ({len(stats)} 种表达)")
        if not dry_run:
            chapter_file.write_text("\n".join(new_lines), encoding="utf-8")
    return stats


def main():
    ap = argparse.ArgumentParser(description="数量实体自动标注（外置词表 quantity）")
    ap.add_argument("--book", default=None,
                    help="只处理指定书（缺省全库）")
    ap.add_argument("--chapter", default=None, help="单回编号（如 001）")
    ap.add_argument("--dry-run", action="store_true", help="仅预览，不写入文件")
    ap.add_argument("--wordlist", default="quantity",
                    help="词表名（wordlists/<名>.json，缺省 quantity）")
    args = ap.parse_args()

    matcher, measures, num_measure_re = load_quantity_resources(args.wordlist)
    multi = sum(1 for ws in matcher["index"].values() for w in ws if len(w) > 1)
    print(f"词表加载完成：量词 {len(measures)} 个（{''.join(measures)}），"
          f"整串模式词 {multi} 个")

    if not config.DIR_TAGGED.exists():
        print(f"标注目录不存在：{config.DIR_TAGGED}")
        return 1
    book_dirs = ([config.DIR_TAGGED / args.book] if args.book
                 else sorted(p for p in config.DIR_TAGGED.iterdir() if p.is_dir()))
    files = []
    for d in book_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.tagged.md")):
            if args.chapter and f.name != f"{args.chapter.zfill(3)}.tagged.md":
                continue
            files.append(f)
    if not files:
        print("未找到匹配的标注文件")
        return 1

    print(f"{'预览模式' if args.dry_run else '标注模式'}：处理 {len(files)} 个文件\n")

    global_stats = defaultdict(int)
    chapter_count = 0
    for f in files:
        stats = process_chapter(f, matcher, num_measure_re, dry_run=args.dry_run)
        if sum(stats.values()) > 0:
            chapter_count += 1
        for k, v in stats.items():
            global_stats[k] += v

    total = sum(global_stats.values())
    print(f"\n{'=' * 50}")
    print(f"总计：{total} 处标注，{len(global_stats)} 种表达，{chapter_count} 回涉及")

    if global_stats:
        print("\nTop 20 高频表达：")
        for word, count in sorted(global_stats.items(), key=lambda x: -x[1])[:20]:
            print(f"  {word}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
