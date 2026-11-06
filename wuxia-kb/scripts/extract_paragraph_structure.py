#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/extract_paragraph_structure.py（2026-11-03）；改动：
#   1. shiji 领域规则删除：'帝'继承关系推断与"太史公曰"总结关系整段移除，
#      改为 fence 类型驱动——按 symbols.FENCE_ALL 逐围栏提取段落结构
#      （每围栏记录类型/PN/显示串摘要/行数，输出 JSON per 回）；
#   2. 关系推断只保留围栏驱动的通用规则：同节相邻段落 sequential；
#      回末对/回末围栏 → 章末收束关系（subtype=chapter_closing）；
#   3. 剥标注改走 symbols.strip_markup（替换内联实体字符类 clean_tags）；
#   4. 单文件（001_五帝本纪 硬编码）改批处理：--book <名> 或 --all（缺省），
#      输出 config.DIR_REGISTRY/structure/<书>/NNN.structure.json（登记层产物）。

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

PN_LINE_RE = re.compile(r"^(?:-\s*|>\s*)?\[(\d+(?:\.\d+)*)\]\s*(.*)")
H1_RE = re.compile(r"^#\s*\[(\d+(?:\.\d+)*)\]\s*(.+)")
H2_RE = re.compile(r"^##\s+(.+)$")
H3_RE = re.compile(r"^###\s+(.+)$")
SUMMARY_LEN = 100     # 摘要截断长度
FULLTEXT_MAX = 400    # full_text 截断上限（同原版）
# 章末收束围栏类型（fence 驱动；02ab §2.4 回末顺序）
CLOSING_FENCES = {"回末", "回末对"}


def extract_paragraph_structure(tagged_file: Path) -> dict:
    """提取单回段落结构（PN 段落 + FENCE_ALL 围栏块）"""
    content = tagged_file.read_text(encoding="utf-8")
    lines = content.split("\n")

    paragraphs = []
    fences = []
    current_section = None
    current_subsection = None
    chapter_title = ""
    cur_fence = None

    def clean_tags(text):
        # 剥语义标注到显示串（统一入口；动词令牌剥除）
        text = symbols.strip_markup(text)
        return text.strip()

    for i, line in enumerate(lines):
        s = line.strip()

        # ---- 围栏态：围栏内行归入围栏块，不按正文段落规则处理 ----
        if cur_fence is not None:
            if symbols.is_fence_close(s):
                cur_fence["close_line"] = i
                fences.append(cur_fence)
                cur_fence = None
            else:
                cur_fence["content_lines"].append(s)
            continue
        ftype = symbols.fence_opens(s)
        if ftype is not None:
            cur_fence = {"type": ftype, "open_line": i, "close_line": None,
                         "content_lines": [], "pn": None}
            continue

        # ---- 回目行 ----
        if s.startswith("# ") and not s.startswith("## "):
            m = H1_RE.match(s)
            if m:
                chapter_title = clean_tags(m.group(2))
                paragraphs.append({
                    "anchor": m.group(1),
                    "section": "",
                    "subsection": "",
                    "summary": chapter_title,
                    "full_text": chapter_title,
                })
            continue

        # ---- 大节/小节标题 ----
        m = H2_RE.match(s)
        if m and not s.startswith("### "):
            current_section = clean_tags(m.group(1)) or m.group(1).strip()
            current_subsection = None
            continue
        m = H3_RE.match(s)
        if m:
            current_subsection = clean_tags(m.group(1)) or m.group(1).strip()
            continue

        # ---- 段落标记 [N]/[N.M]（含列表项/引用块形式） ----
        m = PN_LINE_RE.match(s)
        if m:
            anchor = m.group(1)
            full_text = m.group(2)
            j = i + 1
            while j < len(lines) and lines[j].strip():
                nxt = lines[j].strip()
                if nxt.startswith("#") or nxt == "---" or symbols.fence_opens(nxt):
                    break
                if PN_LINE_RE.match(nxt):
                    break
                full_text += " " + (nxt[2:] if nxt.startswith("- ") else nxt)
                j += 1
            full_clean = clean_tags(full_text)
            summary = (full_clean[:SUMMARY_LEN] + "..."
                       if len(full_clean) > SUMMARY_LEN else full_clean)
            paragraphs.append({
                "anchor": anchor,
                "section": current_section or "",
                "subsection": current_subsection or "",
                "summary": summary,
                "full_text": full_clean[:FULLTEXT_MAX],
            })

    # 未闭合围栏兜底入表
    if cur_fence is not None:
        fences.append(cur_fence)

    # ---- 围栏块结构化（fence 类型驱动核心产出） ----
    fence_records = []
    for f in fences:
        body = "\n".join(f["content_lines"]).strip()
        pn = None
        first_text = ""
        for ln in f["content_lines"]:
            m = PN_LINE_RE.match(ln.strip())
            if m:
                pn = m.group(1)
                first_text = m.group(2)
                break
        if first_text == "" and f["content_lines"]:
            first_text = f["content_lines"][0]
        text_clean = clean_tags(PN_LINE_RE.sub("", first_text)) if first_text else ""
        fence_records.append({
            "type": f["type"],
            "in_enum": f["type"] in symbols.FENCE_ALL,
            "anchor": pn,
            "open_line": f["open_line"] + 1,
            "line_count": len(f["content_lines"]),
            "summary": text_clean[:SUMMARY_LEN],
            "full_text": clean_tags(body)[:FULLTEXT_MAX],
        })

    return {
        "chapter": tagged_file.stem.replace(".tagged", ""),
        "chapter_title": chapter_title,
        "paragraphs": paragraphs,
        "fences": fence_records,
    }


def infer_relations(paragraphs, fences):
    """围栏驱动的通用关系（shiji '帝'继承/太史公曰规则已删除）"""
    relations = []
    for i in range(len(paragraphs) - 1):
        curr, nxt = paragraphs[i], paragraphs[i + 1]
        if curr["section"] and curr["section"] == nxt["section"]:
            relations.append({
                "source": curr["anchor"],
                "target": nxt["anchor"],
                "type": "temporal",
                "subtype": "sequential",
                "description": f"同节「{curr['section']}」内相邻叙述",
            })
    # 章末收束：回末对/回末围栏锚点 → 本章全部正文段落
    closing = [f for f in fences if f["type"] in CLOSING_FENCES and f["anchor"]]
    body_anchors = [p["anchor"] for p in paragraphs
                    if p["anchor"] != symbols.PN_TITLE.strip("[]")]
    for f in closing:
        relations.append({
            "source": f["anchor"],
            "target": "all",
            "type": "hierarchy",
            "subtype": "chapter_closing",
            "description": f"围栏「{f['type']}」收束本章（{len(body_anchors)} 个正文段）",
        })
    return relations


def main():
    ap = argparse.ArgumentParser(
        description="提取段落结构与围栏块（fence 类型驱动，输出 JSON per 回）")
    ap.add_argument("--book", default=None,
                    help="只处理指定书（缺省 --all 全库）")
    ap.add_argument("--all", action="store_true",
                    help="处理全部书（缺省行为）")
    args = ap.parse_args()

    if not config.DIR_TAGGED.exists():
        print(f"标注目录不存在：{config.DIR_TAGGED}")
        return 1
    if args.book:
        book_list = [args.book]
    else:
        book_list = sorted(p.name for p in config.DIR_TAGGED.iterdir()
                           if p.is_dir())
    if not book_list:
        print("未找到书目录。")
        return 1

    out_root = config.DIR_REGISTRY / "structure"
    out_root.mkdir(parents=True, exist_ok=True)

    for book in book_list:
        tagged_files = sorted((config.DIR_TAGGED / book).glob("*.tagged.md"))
        if not tagged_files:
            print(f"[跳过] {book}: 无 .tagged.md")
            continue
        book_dir = out_root / book
        book_dir.mkdir(parents=True, exist_ok=True)
        total_paras = total_relations = total_fences = 0

        for tagged_file in tagged_files:
            structure = extract_paragraph_structure(tagged_file)
            relations = infer_relations(structure["paragraphs"],
                                        structure["fences"])
            result = {
                "book": book,
                "chapter": structure["chapter"],
                "chapter_title": structure["chapter_title"],
                "total_paragraphs": len(structure["paragraphs"]),
                "paragraphs": structure["paragraphs"],
                "fences": structure["fences"],
                "relations": relations,
            }
            out_file = book_dir / f"{structure['chapter']}.structure.json"
            out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                encoding="utf-8")
            total_paras += result["total_paragraphs"]
            total_relations += len(relations)
            total_fences += len(structure["fences"])

        print(f"[完成] {book}: {len(tagged_files)} 回 · "
              f"{total_paras} 段落 · {total_fences} 围栏 · "
              f"{total_relations} 关系 → {book_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
