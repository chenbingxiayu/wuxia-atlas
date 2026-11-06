#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/lint_markdown.py（2026-11-03）；改动：
#   1. 实体/动词/修辞类型正则不再内联 18 类字符类（原版缺 ◆/#/◎ 等码位且与
#      定版漂移），改由 symbols.ALL_CODES + symbols.BRACKETS 动态构建；
#   2. 对话引入动词白名单改为白话武侠集（曰/道/说道/喝道/赞道/冷冷道/
#      娇叱道/问道/答道/笑道），替换史记文言 [曰云谓言]；
#   3. 路径接 config：缺省扫 config.DIR_TAGGED 全库，新增 --book 单书；
#      保留原"传文件/目录"位置参数用法；
#   4. 旧式 @X@ 包裹检测改接 symbols.LEGACY_BRACKET_STYLES（史记体系残留），
#      替换原 v1.0 @人名@ 遗留检查；
#   5. 全角数字警告收窄到 PN 行与标题行（正文全角数字属底本原文，不得改写）；
#   6. 嵌套警告改查三层括号字符（symbols.BRACKETS），管道 | 为合法消歧不算。

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

# ------------------------------------------------------- 动态构建的正则 ----
def _cls(codes):
    """码位集合 → 正则字符类（零内联字符类纪律：一律由 symbols 派生）"""
    return "[" + "".join(re.escape(c) for c in sorted(codes)) + "]"


_ENT_RE = re.compile("〖(" + _cls(symbols.ENTITY_CODES) + r")([^〖〗]*)〗")
_VERB_RE = re.compile("⟦(" + _cls(symbols.VERB_CODES) + r")([^⟦⟧]*)⟧")
_RHET_RE = re.compile("〘(" + _cls(symbols.RHETORIC_CODES) + r")([^〘〙]*)〙")
TOKEN_PATTERNS = [
    (symbols.ENTITIES, _ENT_RE),
    (symbols.VERBS, _VERB_RE),
    (symbols.RHETORIC, _RHET_RE),
]
# 三层括号字符（嵌套检测用；管道 | 为合法消歧符不算）
_ALL_BRACKET_CHARS = (symbols.BRACKETS["entity"] + symbols.BRACKETS["verb"]
                      + symbols.BRACKETS["rhetoric"])
# 旧式 @X@ 包裹（symbols.LEGACY_BRACKET_STYLES；史记体系残留）
_LEGACY_WRAP_RE = re.compile(
    "@([^@\\n]{1,30})@" if symbols.LEGACY_BRACKET_STYLES else r"(?!x)x")

# 对话引入动词白名单（白话武侠集；文言"曰"保留以兼容底本残存）
DIALOGUE_INTRO_VERBS = ["曰", "道", "说道", "喝道", "赞道", "冷冷道",
                        "娇叱道", "问道", "答道", "笑道"]
_DIALOGUE_RE = re.compile(
    "(?:" + "|".join(sorted(DIALOGUE_INTRO_VERBS, key=len, reverse=True)) +
    ")[:：]?\\s*[「『“\"]")

PN_LINE_RE = re.compile(r"^\[(\d+(?:\.\d+)*)\]")
FULLWIDTH_DIGIT_RE = re.compile(r"[０-９]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


class MarkdownLinter:
    """武侠知识库 Markdown 标注文件 Lint 检查器"""

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.content = self.file_path.read_text(encoding="utf-8")
        self.lines = self.content.split("\n")
        self.errors = []
        self.warnings = []
        self.info = []

    # ------------------------------------------------- 实体标注正确性 ----
    def check_entity_tags(self):
        total_entity_count = 0
        for _labels, pattern in TOKEN_PATTERNS:
            total_entity_count += len(pattern.findall(self.content))
        if total_entity_count == 0 and self.file_path.suffix != ".struct.md"                 and self.file_path.name.endswith(".tagged.md"):
            self.errors.append("文档中没有任何实体标注（〖@人物〗⟦⊞动作⟧ 等），"
                               "请检查是否遗漏标注")
        # struct.md（结构层，annotation 前产物）无实体标注属预期，不报错

        for labels, pattern in TOKEN_PATTERNS:
            for match in pattern.finditer(self.content):
                code, body = match.group(1), match.group(2)
                label = labels.get(code, code)
                line_no = self._get_line_num(match.start())

                if not body.strip():
                    self.warnings.append(f"第{line_no}行: 空{label}标注")
                # 嵌套检测：令牌体内出现任何一层括号（TOKEN_RE 语义：
                # 令牌体不含括号；管道 | 为合法消歧符，不警告）
                if any(ch in body for ch in _ALL_BRACKET_CHARS):
                    self.warnings.append(
                        f"第{line_no}行: {label}标注可能嵌套了其他标注: "
                        f"{match.group(0)[:30]}...")

        # 未闭合的半边令牌（剥掉全部合法令牌后仍残留单边括号）
        residue = symbols.TOKEN_RE.sub("", self.content)
        for opener, closer in (symbols.BRACKETS["entity"],
                               symbols.BRACKETS["verb"],
                               symbols.BRACKETS["rhetoric"]):
            if residue.count(opener) != residue.count(closer):
                self.warnings.append(
                    f"发现不配对的标注括号 {opener}/{closer}"
                    f"（开 {residue.count(opener)} 处，闭 {residue.count(closer)} 处）")

        # 旧式 @X@ 包裹（史记体系残留，symbols.LEGACY_BRACKET_STYLES）
        if _LEGACY_WRAP_RE.search(symbols.TOKEN_RE.sub("", self.content)):
            self.errors.append("发现旧式 @X@ 包裹标注（史记体系残留），"
                               "应改为 〖@X〗 三层括号格式")

    # ------------------------------------------- 段落编号连续性 ----
    def check_paragraph_numbers(self):
        paragraphs = []
        for i, line in enumerate(self.lines, 1):
            m = PN_LINE_RE.match(line.strip())
            if m:
                paragraphs.append({"num": m.group(1), "line": i,
                                   "parts": m.group(1).split(".")})

        for para in paragraphs:
            for part in para["parts"]:
                if not part.isdigit():
                    self.errors.append(
                        f"第{para['line']}行: 段落编号格式错误: [{para['num']}]"
                        f"（只允许数字和点，02ab §3.1 两级 [N]/[N.M]）")
            if len(para["parts"]) > symbols.PN_MAX_LEVEL:
                self.errors.append(
                    f"第{para['line']}行: 段落编号 [{para['num']}] 超过两级"
                    f"（02ab §3.1：PN_MAX_LEVEL={symbols.PN_MAX_LEVEL}）")

        top_level_nums = [int(p["parts"][0]) for p in paragraphs
                          if len(p["parts"]) == 1 and
                          all(x.isdigit() for x in p["parts"])]
        if top_level_nums:
            expected = set(range(top_level_nums[0], top_level_nums[-1] + 1))
            missing = sorted(expected - set(top_level_nums))
            if missing:
                self.warnings.append(f"一级段落编号不连续，缺失: {missing}")

    # ------------------------------------------------- 标题层级结构 ----
    def check_heading_structure(self):
        headings = []
        for i, line in enumerate(self.lines, 1):
            m = HEADING_RE.match(line.strip())
            if m:
                headings.append({"level": len(m.group(1)),
                                 "title": m.group(2), "line": i})

        h1_count = sum(1 for h in headings if h["level"] == 1)
        if h1_count == 0:
            self.errors.append("缺少一级标题（# [0] 回目行，02ab §2.2）")
        elif h1_count > 1:
            self.warnings.append(f"有多个一级标题（{h1_count}个），"
                                 "回目 [0] 应恰一个（lint_purple_numbers E6 同口径）")

        for i in range(1, len(headings)):
            prev_level = headings[i - 1]["level"]
            curr_level = headings[i]["level"]
            if curr_level > prev_level + 1:
                self.warnings.append(
                    f"第{headings[i]['line']}行: 标题层级跳跃 "
                    f"(从 {'#' * prev_level} 到 {'#' * curr_level})")

        for h in headings:
            # [0] 回目行是定版编号（02ab §2.2），不算误用
            if h["title"].startswith(symbols.PN_TITLE):
                continue
            if re.match(r"\[\d+(?:\.\d+)*\]", h["title"]):
                self.warnings.append(
                    f"第{h['line']}行: 标题中包含段落编号: {h['title'][:30]}..."
                    f"（# [0] 回目行例外）")

    # ------------------------------------------------- 对话引入检查 ----
    def check_quote_marks(self):
        for i, line in enumerate(self.lines, 1):
            s = line.strip()
            if s.startswith(">") or s.startswith(":::"):
                continue
            if _DIALOGUE_RE.search(line):
                self.info.append(
                    f"第{i}行: 可能是未标记的对话（含白话引语动词"
                    f"{'/'.join(DIALOGUE_INTRO_VERBS[:6])}…等）")

    # ------------------------------------------- 特殊字符与编码问题 ----
    def check_special_chars(self):
        # 全角数字：只查 PN 行与标题行（编号层应半角；正文全角数字属底本原文）
        for i, line in enumerate(self.lines, 1):
            s = line.strip()
            if PN_LINE_RE.match(s) or HEADING_RE.match(s):
                hits = FULLWIDTH_DIGIT_RE.findall(s)
                if hits:
                    self.warnings.append(
                        f"第{i}行: 编号/标题中发现全角数字 {' '.join(hits)}，"
                        "编号层应使用半角")

        # 零宽字符（底本原文与标注文件都不该有）
        zero_width_chars = ["\u200b", "\u200c", "\u200d", "\ufeff"]
        for char in zero_width_chars:
            if char in self.content:
                self.warnings.append(
                    f"发现零宽字符 (U+{ord(char):04X})，数量: "
                    f"{self.content.count(char)}")

    # ----------------------------------------------------- 行长建议 ----
    def check_line_length(self):
        max_length = 200
        long_lines = [(i, len(line)) for i, line in enumerate(self.lines, 1)
                      if len(line) > max_length and not PN_LINE_RE.match(line.strip())]
        if long_lines:
            self.info.append(
                f"有{len(long_lines)}行超过{max_length}字符（建议分段）")

    def _get_line_num(self, char_pos):
        return self.content[:char_pos].count("\n") + 1

    def lint(self):
        print(f"正在检查: {self.file_path.name}")
        print("=" * 70)

        self.check_entity_tags()
        self.check_paragraph_numbers()
        self.check_heading_structure()
        self.check_quote_marks()
        self.check_special_chars()
        self.check_line_length()

        return self._generate_report()

    def _generate_report(self):
        has_issues = bool(self.errors or self.warnings)

        if self.errors:
            print(f"\n错误 ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print(f"\n警告 ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")

        if self.info:
            print(f"\n提示 ({len(self.info)}):")
            for info_msg in self.info[:5]:
                print(f"  - {info_msg}")
            if len(self.info) > 5:
                print(f"  ... 还有 {len(self.info) - 5} 条提示")

        if not has_issues:
            print("\n没有发现错误或警告")

        print("=" * 70)
        print(f"总计: {len(self.errors)} 错误, {len(self.warnings)} 警告, "
              f"{len(self.info)} 提示\n")

        return len(self.errors) == 0


def iter_tagged_files(path, book=None):
    """路径解析：显式文件/目录优先；缺省扫 config.DIR_TAGGED（--book 单书）"""
    if path is not None:
        p = Path(path)
        if p.is_file():
            return [p]
        if p.is_dir():
            return sorted(list(p.glob("*.struct.md")) + list(p.glob("*.tagged.md")))
        print(f"错误: 路径不存在: {p}")
        sys.exit(1)
    if not config.DIR_TAGGED.exists():
        print(f"标注目录不存在：{config.DIR_TAGGED}")
        sys.exit(1)
    book_dirs = ([config.DIR_TAGGED / book] if book
                 else sorted(p for p in config.DIR_TAGGED.iterdir() if p.is_dir()))
    files = []
    for d in book_dirs:
        if not d.is_dir():
            if book:
                print(f"未找到书目录：{d}")
                sys.exit(1)
            continue
        files.extend(sorted(list(d.glob("*.struct.md")) + list(d.glob("*.tagged.md"))))
    return files


def main():
    ap = argparse.ArgumentParser(
        description="武侠知识库 Markdown 标注文件 Lint 检查"
                    "（实体语法/段落编号/标题层级/对话引入/特殊字符）")
    ap.add_argument("path", nargs="?", default=None,
                    help="标注文件或目录（缺省扫 config.DIR_TAGGED 全库）")
    ap.add_argument("--book", default=None,
                    help="只查指定书（config.DIR_TAGGED/<书名>/）")
    args = ap.parse_args()

    files = iter_tagged_files(args.path, args.book)
    if not files:
        print("未找到 .tagged.md 文件。")
        sys.exit(1)

    print(f"\n开始检查 {len(files)} 个文件...\n")

    total_errors = 0
    total_warnings = 0
    failed_files = []

    for md_file in files:
        linter = MarkdownLinter(md_file)
        success = linter.lint()
        total_errors += len(linter.errors)
        total_warnings += len(linter.warnings)
        if not success:
            failed_files.append(md_file.name)

    print("\n" + "=" * 70)
    print("检查完成")
    print("=" * 70)
    print(f"检查文件数: {len(files)}")
    print(f"总错误数: {total_errors}")
    print(f"总警告数: {total_warnings}")

    if failed_files:
        print(f"\n有错误的文件 ({len(failed_files)}):")
        for fname in failed_files[:10]:
            print(f"  - {fname}")
        if len(failed_files) > 10:
            print(f"  ... 还有 {len(failed_files) - 10} 个文件")

    sys.exit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()
