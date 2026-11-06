#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/extract_yunwen.py（2026-11-03）；改动：
#   1. 韵文类型扩为围栏类型：由 symbols.FENCE_FORMAL 动态构建韵文子集
#      （词/诗/歌/对联/回末对；排除 回末/书信 两类非韵文），不再硬编码
#      "赞/诗歌/赋"三类型；
#   2. 删除"太史公曰"赞变体匹配（::: 太史公赞/褚先生赞/赞语）与
#      刻石/赋 标题启发式（shiji 特有）；标题改从围栏前最近的 ## 标题行
#      或 [N] 段落首行提取，缺省用 "{回目}之{类型}"；
#   3. 围栏扫描改走 symbols.fence_opens / symbols.is_fence_close（不再
#      按类型拼正则逐个搜全文，且天然兼容枚举外类型跳过）；
#   4. 分母 130 硬编码删除：改 config.books() 分书统计（每书覆盖回数/总回数）；
#   5. 路径接 config：输入 config.DIR_TAGGED/<书>/NNN.tagged.md，
#      输出 config.DIR_LOGS/yunwen/{yunwen.json,yunwen.md}；新增 --book。

import argparse
import io
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols

# 韵文围栏类型：由 FENCE_FORMAL 动态构建（排除非韵文的 回末/书信）
NON_VERSE_FENCES = ("回末", "书信")
YUNWEN_DESC = {
    "词": "词牌韵文（长短句）", "诗": "诗句韵文", "歌": "歌谣韵文",
    "对联": "楹联/门联/回目对", "回末对": "回末收束对句",
}
YUNWEN_TYPES = {t: YUNWEN_DESC.get(t, "围栏韵文")
                for t in symbols.FENCE_FORMAL if t not in NON_VERSE_FENCES}

TITLE_H2_RE = re.compile(r"^##\s+(.+?)$", re.MULTILINE)
PN_TITLE_RE = re.compile(r"^\[(\d+)\]\s*(.+)$")
H1_TITLE_RE = re.compile(r"^#\s+\[" + re.escape(symbols.PN_TITLE.strip("[]")) + r"\]\s*(.*)$")


def chapter_title_of(content: str) -> str:
    """回目标题：# [0] 行剥标注后的文本"""
    m = H1_TITLE_RE.search(content)
    if m:
        return symbols.strip_markup(m.group(1)).strip()
    return ""


def title_from_context(lines_before: list) -> str:
    """从围栏开启行之前最近的标题线索提取标题（## 标题行 或 [N] 段落首行）"""
    for line in reversed(lines_before[-30:]):
        s = line.strip()
        if not s:
            continue
        if s.startswith("## "):
            return symbols.strip_markup(s[3:]).strip().rstrip("，。、；：")
        m = PN_TITLE_RE.match(s)
        if m:
            return symbols.strip_markup(m.group(2)).strip().rstrip("，。、；：")
    return ""


def extract_yunwen_blocks(chapter_file: Path):
    """从单回文件中提取全部韵文围栏 → [(type, content, title), ...]"""
    content = chapter_file.read_text(encoding="utf-8")
    lines = content.split("\n")
    blocks = []
    cur_type, cur_lines, lines_before = None, [], []

    for raw in lines:
        s = raw.strip()
        if cur_type is None:
            ftype = symbols.fence_opens(s)
            if ftype in YUNWEN_TYPES:
                cur_type = ftype
                cur_lines = []
            elif s:
                lines_before.append(s)
            continue
        # 围栏内容态
        if symbols.is_fence_close(s):
            block_content = "\n".join(cur_lines).strip()
            if block_content:
                title = title_from_context(lines_before)
                blocks.append((cur_type, block_content, title))
            cur_type = None
        else:
            cur_lines.append(s)

    return blocks


def main():
    ap = argparse.ArgumentParser(description="提取武侠标注文本中的韵文围栏（词/诗/歌/对联/回末对）")
    ap.add_argument("--book", default=None,
                    help="只提取指定书（缺省遍历 config.DIR_TAGGED 全部书）")
    args = ap.parse_args()

    if not config.DIR_TAGGED.exists():
        print(f"标注目录不存在：{config.DIR_TAGGED}")
        return 1
    if args.book:
        book_list = [args.book]
    else:
        book_list = sorted(p.name for p in config.DIR_TAGGED.iterdir() if p.is_dir())

    output_dir = config.DIR_LOGS / "yunwen"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_yunwen = []
    per_book_stat = {}
    corpus_books = config.books()

    for book in book_list:
        chapter_files = sorted((config.DIR_TAGGED / book).glob("*.tagged.md"))
        book_count = 0
        book_chapters_covered = set()
        for chapter_file in chapter_files:
            chapter_num = re.sub(r"\.tagged$", "", chapter_file.stem)
            blocks = extract_yunwen_blocks(chapter_file)
            if blocks:
                chapter_files_txt = chapter_file.read_text(encoding="utf-8")
                ch_title = chapter_title_of(chapter_files_txt)
                type_counter = {}
                for yunwen_type, content, title in blocks:
                    type_counter[yunwen_type] = type_counter.get(yunwen_type, 0) + 1
                    seq = type_counter[yunwen_type]
                    if not title:
                        title = f"{ch_title or chapter_num}之{yunwen_type}"
                        if seq > 1:
                            title += f"（{seq}）"
                    all_yunwen.append({
                        "book": book,
                        "chapter": chapter_num,
                        "chapter_title": ch_title,
                        "type": yunwen_type,
                        "type_desc": YUNWEN_TYPES[yunwen_type],
                        "title": title,
                        "content": content,
                    })
                    book_count += 1
                    book_chapters_covered.add(chapter_num)
        total_chapters = corpus_books.get(book, {}).get("chapters",
                                                        len(chapter_files))
        per_book_stat[book] = {"blocks": book_count,
                               "chapters_covered": len(book_chapters_covered),
                               "chapters_total": total_chapters}

    print("\n提取结果：")
    print(f"  总计: {len(all_yunwen)} 篇韵文")
    type_counts = {}
    for item in all_yunwen:
        type_counts[item["type"]] = type_counts.get(item["type"], 0) + 1
    for yunwen_type in YUNWEN_TYPES:
        if type_counts.get(yunwen_type):
            print(f"  {yunwen_type}: {type_counts[yunwen_type]} 篇")

    # JSON
    output_json = output_dir / "yunwen.json"
    output_json.write_text(json.dumps(all_yunwen, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"\n✓ JSON 已保存: {output_json}")

    # Markdown
    output_md = output_dir / "yunwen.md"
    with open(output_md, "w", encoding="utf-8") as f:
        f.write("# 武侠知识库韵文集\n\n")
        f.write(f"共提取 {len(all_yunwen)} 篇韵文围栏\n\n")
        for yunwen_type, desc in YUNWEN_TYPES.items():
            items = [item for item in all_yunwen if item["type"] == yunwen_type]
            if not items:
                continue
            f.write(f"## {yunwen_type}（{len(items)}篇）\n\n")
            f.write(f"{desc}\n\n")
            for item in items:
                f.write(f"### {item['title']}\n\n")
                f.write(f"*{item['book']} {item['chapter']} "
                        f"{item['chapter_title']}*\n\n")
                f.write(f"{item['content']}\n\n")
                f.write("---\n\n")

    print(f"✓ Markdown 已保存: {output_md}")

    # 分书统计（分母来自 config.books()，无 130 硬编码）
    print("\n分书统计：")
    for book, st in per_book_stat.items():
        print(f"  {book}: {st['blocks']} 篇 · 覆盖 {st['chapters_covered']}"
              f"/{st['chapters_total']} 回")
    return 0


if __name__ == "__main__":
    sys.exit(main())
