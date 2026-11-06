#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/compute_annotation_coverage.py（2026-11-03）；改动：
#   1. 类型表不再硬编码 18+4，改接 symbols 15 实体 + 6 动词 + 修辞
#      （TYPE_LABELS = ENTITIES | VERBS | RHETORIC）；标注抽取改用
#      symbols.TOKEN_RE + parse_token（管道消歧取显示串）；
#   2. 删除硬编码基线对比段（shiji 130 章 579,584 字基线对武侠不适用）；
#   3. 统计改分书：遍历 config.books()，输出 per-book + 全库两张表；
#   4. Markdown 结构剥离内置（标题/段号/围栏标记行/列表/表格分隔线），
#      语义标注剥离统一走 symbols.strip_markup（原 semantic_tags.strip_markup）；
#   5. 输出落 config.DIR_LOGS/coverage/（原 doc/analysis/）；
#   6. 路径接 config，新增 --book 单书。

import argparse
import datetime
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

TODAY = datetime.date.today().strftime("%Y%m%d")
OUT_DIR = config.DIR_LOGS / "coverage"
OUT_MD = OUT_DIR / f"汉字标注覆盖率统计报告_{TODAY}.md"

CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")

# 类型表：15 实体 + 6 动词 + 修辞，全部来自 symbols 定版
TYPE_LABELS = {**symbols.ENTITIES, **symbols.VERBS, **symbols.RHETORIC}

# Markdown 结构剥离（非语义标注，绕过 symbols 职责；语义令牌走 strip_markup）
HEADING_LINE_RE = re.compile(r"^#{1,6}.*$", re.MULTILINE)
PN_LINE_RE = re.compile(r"^\[\d+(?:\.\d+)*\]\s*", re.MULTILINE)
LIST_LINE_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
QUOTE_LINE_RE = re.compile(r"^>\s?", re.MULTILINE)
TABLE_SEP_RE = re.compile(r"^\|[\s\-|]+\|?\s*$", re.MULTILINE)
RULE_LINE_RE = re.compile(r"^-{3,}\s*$", re.MULTILINE)
BOLD_RE = re.compile(r"\*\*([^*]*)\*\*")


def count_cjk(text: str) -> int:
    return len(CJK_RE.findall(text))


def strip_structure(text: str) -> str:
    """剥 Markdown 结构层（标题/段号/围栏标记行/列表/引用/表格分隔线/粗体）"""
    text = HEADING_LINE_RE.sub("", text)
    text = re.sub(r"^:::.*$", "", text, flags=re.MULTILINE)   # 围栏标记行
    text = QUOTE_LINE_RE.sub("", text)
    text = LIST_LINE_RE.sub("", text)
    text = PN_LINE_RE.sub("", text)
    text = BOLD_RE.sub(r"\1", text)
    text = RULE_LINE_RE.sub("", text)
    text = TABLE_SEP_RE.sub("", text)
    return text


def analyze_chapter(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    # 先抽标注（strip 之前做，因为 strip 会去掉标注符号）
    type_chars = defaultdict(int)
    type_tokens = defaultdict(int)
    annotated_cjk = 0
    skipped_tokens = 0

    for m in symbols.TOKEN_RE.finditer(raw):
        layer, code, _body, display, _note, err = symbols.parse_token(m.group(0))
        if err is not None or code is None or display is None:
            skipped_tokens += 1      # 类型码不在定版内等（另由 lint 工具把关）
            continue
        n = count_cjk(display)
        label = TYPE_LABELS.get(code, code)
        type_chars[label] += n
        type_tokens[label] += 1
        annotated_cjk += n

    # 再剥 Markdown 结构与全部标注，得到纯原文
    stripped = symbols.strip_markup(strip_structure(raw))
    total_cjk = count_cjk(stripped)
    return {
        "file": path.name,
        "total": total_cjk,
        "annotated": annotated_cjk,
        "unannotated": total_cjk - annotated_cjk,
        "type_chars": dict(type_chars),
        "type_tokens": dict(type_tokens),
        "skipped_tokens": skipped_tokens,
    }


def iter_book_chapter_files(book: str):
    d = config.DIR_TAGGED / book
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.tagged.md") if "backup" not in p.name)


def render_report(per_book: dict, lib_totals: dict, per_chapter: list,
                  today: str) -> str:
    lines = []
    lines.append("# 武侠知识库 - 汉字标注覆盖率统计报告")
    lines.append("")
    lines.append(f"> 统计日期: {datetime.date.today().isoformat()}")
    lines.append(f"> 扫描范围: `tagged/<书>/NNN.tagged.md`，"
                 f"{len(per_book)} 部书共 {sum(v['chapters'] for v in per_book.values())} 回")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 分书统计")
    lines.append("")
    lines.append("| 书名 | 回数 | 总汉字数 | 已标注汉字数 | 覆盖率 |")
    lines.append("|------|-----:|---------:|-------------:|-------:|")
    for book, v in sorted(per_book.items()):
        pct = v["annotated"] / v["total"] * 100 if v["total"] else 0
        lines.append(f"| {book} | {v['chapters']} | {v['total']:,} | "
                     f"{v['annotated']:,} | {pct:.2f}% |")
    lines.append("")
    lines.append("## 全库统计")
    lines.append("")
    lines.append("| 指标 | 数量 | 比例 |")
    lines.append("|------|------|------|")
    total = lib_totals["total"]
    annotated = lib_totals["annotated"]
    lines.append(f"| 总汉字数 | {total:,} | 100.00% |")
    lines.append(f"| 已标注汉字数 | {annotated:,} | "
                 f"{annotated / total * 100 if total else 0:.2f}% |")
    lines.append(f"| 未标注汉字数 | {total - annotated:,} | "
                 f"{(total - annotated) / total * 100 if total else 0:.2f}% |")
    lines.append("")
    lines.append("**说明**：")
    lines.append("- 已标注汉字 = 所有 `〖TYPE 显示串〗`（15 类实体）、"
                 "`⟦VERB 显示串⟧`（6 域动词）与 `〘※…〙` 标注中显示串部分的汉字数之和")
    lines.append("- 类型码不在定版内的令牌不计入已标注"
                 f"（本次跳过 {lib_totals['skipped']} 个，由 lint 工具把关）")
    lines.append("- 总字数已剔除 Markdown 结构（标题、段号 [N]、列表符、"
                 "围栏标记行、表格分隔行等）")
    lines.append("")

    # 按实体类型排序（全库）
    if annotated:
        lines.append("## 全库按类型统计")
        lines.append("")
        lines.append("| 排名 | 类型 | 条目数 | 汉字数 | 占已标注比例 |")
        lines.append("|------|------|-------:|-------:|-------------:|")
        sorted_types = sorted(lib_totals["type_chars"].items(), key=lambda x: -x[1])
        for i, (t, n) in enumerate(sorted_types, 1):
            tokens = lib_totals["type_tokens"].get(t, 0)
            pct = n / annotated * 100
            lines.append(f"| {i} | {t} | {tokens:,} | {n:,} | {pct:.2f}% |")
        lines.append("")

    # Top/Bottom 回（全库）
    for s in per_chapter:
        s["pct"] = s["annotated"] / s["total"] * 100 if s["total"] else 0
    top = sorted(per_chapter, key=lambda x: -x["pct"])[:10]
    bot = sorted(per_chapter, key=lambda x: x["pct"])[:10]
    if per_chapter:
        lines.append("## 覆盖率最高的 10 回")
        lines.append("")
        lines.append("| 排名 | 回 | 覆盖率 | 已标注 | 总字数 |")
        lines.append("|------|------|-------:|-------:|-------:|")
        for i, s in enumerate(top, 1):
            lines.append(f"| {i} | {s['file'].replace('.tagged.md', '')} | "
                         f"{s['pct']:.2f}% | {s['annotated']:,} | {s['total']:,} |")
        lines.append("")
        lines.append("## 覆盖率最低的 10 回")
        lines.append("")
        lines.append("| 排名 | 回 | 覆盖率 | 已标注 | 总字数 |")
        lines.append("|------|------|-------:|-------:|-------:|")
        for i, s in enumerate(bot, 1):
            lines.append(f"| {i} | {s['file'].replace('.tagged.md', '')} | "
                         f"{s['pct']:.2f}% | {s['annotated']:,} | {s['total']:,} |")
        lines.append("")

    lines.append("## 技术说明")
    lines.append("")
    lines.append("1. **汉字识别**：`[\\u4e00-\\u9fff\\u3400-\\u4dbf]`"
                 "（CJK 基本区 + 扩展 A）")
    lines.append("2. **标注抽取**：`symbols.TOKEN_RE` + `symbols.parse_token`"
                 " — 15 实体 + 6 动词 + 修辞，消歧取管道左侧显示串")
    lines.append("3. **结构剥离**：标题/段号/围栏标记行/列表/引用/表格分隔行内置；"
                 "语义令牌用 `symbols.strip_markup` 统一处理")
    lines.append("")
    lines.append("### 重跑命令")
    lines.append("")
    lines.append("```bash")
    lines.append("python scripts/compute_annotation_coverage.py [--book 书名]")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="计算分书汉字标注覆盖率（15+6+修辞）")
    ap.add_argument("--book", default=None,
                    help="只统计指定书（缺省遍历 config.books() 与 tagged 交集）")
    args = ap.parse_args()

    if args.book:
        book_list = [args.book]
    else:
        tagged_books = ({p.name for p in config.DIR_TAGGED.iterdir()
                         if p.is_dir()} if config.DIR_TAGGED.exists() else set())
        book_list = [b for b in config.book_names() if b in tagged_books]
        # 语料登记簿为空时回退到 tagged 目录（如试点小样）
        if not book_list:
            book_list = sorted(tagged_books)
    if not book_list:
        print("未找到可统计的书（config.DIR_TAGGED 为空？）")
        return 1

    per_book = {}
    per_chapter = []
    lib = {"total": 0, "annotated": 0, "skipped": 0,
           "type_chars": defaultdict(int), "type_tokens": defaultdict(int)}

    for book in book_list:
        files = iter_book_chapter_files(book)
        b_total = b_ann = b_skip = 0
        for f in files:
            stat = analyze_chapter(f)
            per_chapter.append({"book": book, **stat})
            b_total += stat["total"]
            b_ann += stat["annotated"]
            b_skip += stat["skipped_tokens"]
            lib["total"] += stat["total"]
            lib["annotated"] += stat["annotated"]
            lib["skipped"] += stat["skipped_tokens"]
            for t, n in stat["type_chars"].items():
                lib["type_chars"][t] += n
                lib["type_tokens"][t] += stat["type_tokens"].get(t, 0)
        per_book[book] = {"chapters": len(files), "total": b_total,
                          "annotated": b_ann, "skipped": b_skip}
        pct = b_ann / b_total * 100 if b_total else 0
        print(f"[统计] {book}: {len(files)} 回, 总 {b_total:,} 字, "
              f"已标注 {b_ann:,}（{pct:.2f}%）")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = render_report(per_book, lib, per_chapter,
                           datetime.date.today().isoformat())
    OUT_MD.write_text(report, encoding="utf-8")
    print(f"\n[输出] {OUT_MD}")

    total = lib["total"]
    annotated = lib["annotated"]
    print()
    print(f"总汉字数      {total:>10,}  100.00%")
    print(f"已标注汉字数  {annotated:>10,}  "
          f"{annotated / total * 100 if total else 0:>6.2f}%")
    print(f"未标注汉字数  {total - annotated:>10,}  "
          f"{(total - annotated) / total * 100 if total else 0:>6.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
