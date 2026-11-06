#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/generate_entity_stats_report.py（2026-11-03）；改动：
#   1. 类型表不再硬编码 18+4，改接 symbols：ENTITIES 15 类（'^' 标签统一为
#      符号表口径"专门概念"，原版作"名物"）+ VERBS 6 域；
#   2. 示例表换武侠（〖@练霓裳〗〖=天山〗〖☆怪蟒翻身〗式）；
#   3. 抽取改用 symbols.TOKEN_RE + parse_token（消歧取管道左侧显示串，
#      条目按显示串去重，口径同原版）；
#   4. 路径接 config：扫描 config.DIR_TAGGED 分书（新增分书统计表与 --book），
#      报告默认落 config.DIR_LOGS/entity_stats/（原 doc/entities/实体标注统计/）；
#   5. 删除"版本更新人工填写"段落指引中的 shiji 报告路径引用。

from __future__ import annotations

import argparse
import datetime
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols

# 类型表：全部来自 symbols 定版（'^' → "专门概念" 等 15 类；动词 6 域）
NOUN_TYPES = dict(symbols.ENTITIES)
VERB_TYPES = dict(symbols.VERBS)

# 武侠示例（展示串；消歧写法见 skills/SKILL_01g）
EXAMPLES = {
    "@": "〖@练霓裳〗", "◎": "〖◎武当七侠〗", "=": "〖=天山〗",
    "◆": "〖◆武当派〗", "&": "〖&卓家〗", "~": "〖~回部〗",
    ";": "〖;总镖头〗", "#": "〖#钦犯〗", "☆": "〖☆怪蟒翻身〗",
    "•": "〖•寒玉床〗", "+": "〖+白猿〗", "{": "〖{葵花宝典〗",
    "^": "〖^内功〗", "%": "〖%三更〗", "$": "〖$三百斤〗",
    "⊞": "⟦⊞交手⟧", "⊠": "⟦⊠负伤⟧", "⊡": "⟦⊡结拜⟧",
    "⊟": "⟦⊟折剑⟧", "▣": "⟦▣传功⟧", "■": "⟦■出走⟧",
}


def scan_book(book: str) -> dict:
    """扫描单书全部 .tagged.md → {chapter_count, noun:{code:{label,entries,occurrences}}, verb:{...}}"""
    noun_occ = defaultdict(int)
    noun_entries = defaultdict(set)
    verb_occ = defaultdict(int)
    verb_entries = defaultdict(set)

    d = config.DIR_TAGGED / book
    files = sorted(p for p in d.glob("*.tagged.md")
                   if d.is_dir() and "backup" not in p.name)
    for f in files:
        text = f.read_text(encoding="utf-8")
        for m in symbols.TOKEN_RE.finditer(text):
            layer, code, _body, display, _note, err = symbols.parse_token(m.group(0))
            if err is not None or code is None:
                continue
            display = (display or "").strip()
            if layer == "entity" and code in NOUN_TYPES:
                noun_occ[code] += 1
                if display:
                    noun_entries[code].add(display)
            elif layer == "verb" and code in VERB_TYPES:
                verb_occ[code] += 1
                if display:
                    verb_entries[code].add(display)

    return {
        "chapter_count": len(files),
        "noun": {m: {"label": NOUN_TYPES[m],
                     "entries": len(noun_entries[m]),
                     "occurrences": noun_occ[m]}
                 for m in NOUN_TYPES},
        "verb": {m: {"label": VERB_TYPES[m],
                     "entries": len(verb_entries[m]),
                     "occurrences": verb_occ[m]}
                 for m in VERB_TYPES},
    }


def render_report(stats_by_book: dict, version: str, today: str) -> str:
    # 合并全库
    merged = {"chapter_count": 0, "noun": {}, "verb": {}}
    for code in NOUN_TYPES:
        merged["noun"][code] = {"label": NOUN_TYPES[code], "entries": 0, "occurrences": 0}
    for code in VERB_TYPES:
        merged["verb"][code] = {"label": VERB_TYPES[code], "entries": 0, "occurrences": 0}
    for book, st in stats_by_book.items():
        merged["chapter_count"] += st["chapter_count"]
        for layer in ("noun", "verb"):
            for code, v in st[layer].items():
                merged[layer][code]["entries"] += v["entries"]
                merged[layer][code]["occurrences"] += v["occurrences"]

    noun, verb = merged["noun"], merged["verb"]
    chapter_count = merged["chapter_count"]
    total_noun_occ = sum(v["occurrences"] for v in noun.values())
    total_noun_entries = sum(v["entries"] for v in noun.values())
    total_verb_occ = sum(v["occurrences"] for v in verb.values())
    total_verb_entries = sum(v["entries"] for v in verb.values())
    grand_occ = total_noun_occ + total_verb_occ
    grand_entries = total_noun_entries + total_verb_entries

    noun_sorted = sorted(noun.items(), key=lambda kv: -kv[1]["occurrences"])
    verb_sorted = sorted(verb.items(), key=lambda kv: -kv[1]["occurrences"])
    top10 = sorted(
        [(v["label"], m, v["occurrences"]) for m, v in noun.items()]
        + [(v["label"], m, v["occurrences"]) for m, v in verb.items()],
        key=lambda t: -t[2],
    )[:10]

    lines = []
    lines.append(f"# 武侠知识库实体标注统计报告 {version}")
    lines.append("")
    lines.append(f"生成时间: {today}")
    lines.append(f"数据来源: {len(stats_by_book)} 部书 {chapter_count} 回标注文本"
                 f"（tagged/<书>/NNN.tagged.md）")
    lines.append("生成依据: 直接扫描 〖TYPE X〗 与 ⟦VERB X⟧ 标注的条目数与出现次数"
                 "（条目=显示串去重，不做别名合并）")
    lines.append("生成脚本: `scripts/generate_entity_stats_report.py`")
    lines.append("")
    lines.append(f"## 一、名词实体统计（{len(NOUN_TYPES)} 类）")
    lines.append("")
    lines.append("| 类型 | 符号  | 条目数 | 出现数 | 占比（出现） | 示例 |")
    lines.append("| ---- | ----- | -----: | -----: | -----------: | ---- |")
    for m, v in noun_sorted:
        pct = 100 * v["occurrences"] / total_noun_occ if total_noun_occ else 0
        lines.append(
            f"| {v['label']} | 〖{m}〗 | {v['entries']:,} | {v['occurrences']:,} | "
            f"{pct:.1f}% | {EXAMPLES.get(m, '')} |")
    lines.append("")
    lines.append(f"**名词小计**：条目 {total_noun_entries:,} · 出现 {total_noun_occ:,}（100.0%）")
    lines.append("")
    lines.append(f"## 二、动词实体统计（{len(VERB_TYPES)} 域）")
    lines.append("")
    lines.append("| 类型 | 符号  | 条目数 | 出现数 | 占比（出现） | 示例 |")
    lines.append("| ---- | ----- | -----: | -----: | -----------: | ---- |")
    for m, v in verb_sorted:
        pct = 100 * v["occurrences"] / total_verb_occ if total_verb_occ else 0
        lines.append(
            f"| {v['label']} | ⟦{m}⟧ | {v['entries']:,} | {v['occurrences']:,} | "
            f"{pct:.1f}% | {EXAMPLES.get(m, '')} |")
    lines.append("")
    lines.append(f"**动词小计**：条目 {total_verb_entries:,} · 出现 {total_verb_occ:,}（100.0%）")
    lines.append("")
    lines.append("## 三、总体统计")
    lines.append("")
    lines.append("| 维度 | 条目数 | 出现数 | 类别 |")
    lines.append("| ---- | -----: | -----: | ---: |")
    lines.append(f"| 名词实体 | {total_noun_entries:,} | {total_noun_occ:,} | {len(NOUN_TYPES)} 类 |")
    lines.append(f"| 动词实体 | {total_verb_entries:,} | {total_verb_occ:,} | {len(VERB_TYPES)} 域 |")
    lines.append(
        f"| **总计** | **{grand_entries:,}** | **{grand_occ:,}** | "
        f"**{len(NOUN_TYPES) + len(VERB_TYPES)} 类** |")
    lines.append("")
    lines.append(f"章回数：{chapter_count} 回")
    avg_occ = grand_occ / chapter_count if chapter_count else 0
    avg_ent = grand_entries / chapter_count if chapter_count else 0
    lines.append(f"平均密度：约 {avg_occ:,.0f} 出现/回 · {avg_ent:,.0f} 条目/回（去重前聚合）")
    lines.append("")
    lines.append("## 四、分书统计")
    lines.append("")
    lines.append("| 书名 | 回数 | 名词条目 | 名词出现 | 动词条目 | 动词出现 |")
    lines.append("|------|-----:|---------:|---------:|---------:|---------:|")
    for book, st in sorted(stats_by_book.items()):
        n = sum(v["entries"] for v in st["noun"].values())
        no = sum(v["occurrences"] for v in st["noun"].values())
        v_e = sum(v["entries"] for v in st["verb"].values())
        vo = sum(v["occurrences"] for v in st["verb"].values())
        lines.append(f"| {book} | {st['chapter_count']} | {n:,} | {no:,} | "
                     f"{v_e:,} | {vo:,} |")
    lines.append("")
    lines.append("## 五、Top 10 实体类型（按出现数）")
    lines.append("")
    lines.append("| 排名 | 类型 | 出现数 | 占比 |")
    lines.append("| ---: | ---- | -----: | ---: |")
    for i, (label, marker, occ) in enumerate(top10, 1):
        pct = 100 * occ / grand_occ if grand_occ else 0
        symbol = f"⟦{marker}⟧" if marker in VERB_TYPES else ""
        name = f"{label} {symbol}".strip() if symbol else label
        lines.append(f"| {i:>2} | {name:<16} | {occ:,} | {pct:.1f}% |")
    lines.append("")
    lines.append(f"## 六、{version} 版本更新")
    lines.append("")
    lines.append("> 本节由人工填写：与上一版的规模变化、重点类别变化、反思贡献、相关文档链接。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--version", default=None,
                        help="报告版本号（如 v0.3）。默认用日期 v{YYMMDD}")
    parser.add_argument("--output", type=Path, default=None,
                        help="输出路径（默认写入 config.DIR_LOGS/entity_stats/）")
    parser.add_argument("--stdout", action="store_true",
                        help="只打印到 stdout，不写文件")
    parser.add_argument("--json", type=Path, default=None,
                        help="同时导出原始数据 JSON")
    parser.add_argument("--book", default=None, help="只统计指定书（缺省全库分书）")
    args = parser.parse_args()

    if not config.DIR_TAGGED.exists():
        print(f"标注目录不存在：{config.DIR_TAGGED}")
        return 1
    if args.book:
        book_list = [args.book]
    else:
        book_list = sorted(p.name for p in config.DIR_TAGGED.iterdir()
                           if p.is_dir() and any(p.glob("*.tagged.md")))
    if not book_list:
        print("未找到含 .tagged.md 的书目录。")
        return 1

    stats_by_book = {book: scan_book(book) for book in book_list}
    today = datetime.date.today().strftime("%Y-%m-%d")
    version = args.version or f"v{datetime.date.today().strftime('%y%m%d')}"
    report = render_report(stats_by_book, version, today)

    if args.stdout:
        sys.stdout.write(report)
    else:
        out = args.output or (config.DIR_LOGS / "entity_stats"
                              / f"实体标注统计报告_{version}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"✓ 写入报告：{out}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(stats_by_book, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        print(f"✓ 写入 JSON：{args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
