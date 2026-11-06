#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/lint_symbol_conflicts.py（2026-11-03）；改动：
#   1. 原版 5 处内联实体字符类（[#@=;$%&'^~•!'+?{:\[_◆] 等，且 4 处缺 ◆、
#      与定版漂移）全部改接 symbols：TOKEN_RE 剥令牌、ENTITY/VERB/RHETORIC_CODES
#      动态构建检测正则（零内联字符类纪律）；
#   2. 新增检查项 legacy：symbols.LEGACY_VERB_CODES（◈◉○◇▲▷）与
#      LEGACY_ENTITY_CODES（! ? _ : [）出现在标注令牌 TYPE 位即 error，
#      另含 LEGACY_BRACKET_STYLES 旧式 @X@ 包裹（史记体系残留检测；
#      2026-11-03 004 试点修复：检测前剥除有效令牌，消除相邻 @ 标签跨标签误配对）；
#   3. 半角标点/直角引号/标点在标注内/Markdown 在标注内/嵌套/跨标点六项
#      检查逻辑照搬（标点集合为本工具常量，非标注符号）；
#   4. 路径接 config：文件位置参数可缺省（缺省扫 config.DIR_TAGGED 全库），
#      新增 --book 单书过滤；
#   5. 嵌套正则同层字符类排除全部三层括号（TOKEN_RE 语义：令牌体不含括号）。

import argparse
import io
import re
import sys
from collections import defaultdict
from pathlib import Path
from glob import glob

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols

# ------------------------------------------------- 由 symbols 派生的正则 ----
def _cls(codes):
    return "[" + "".join(re.escape(c) for c in sorted(codes)) + "]"


# 合法令牌（TYPE 位在定版内）——供剥除/对照
ENT_TOKEN_RE = re.compile("〖" + _cls(symbols.ENTITY_CODES) + r"[^〖〗]*〗")
VERB_TOKEN_RE = re.compile("⟦" + _cls(symbols.VERB_CODES) + r"[^⟦⟧]*⟧")
RHET_TOKEN_RE = re.compile("〘" + _cls(symbols.RHETORIC_CODES) + r"[^〘〙]*〙")

# 实体令牌（含任意 TYPE 位，供内容检查；嵌套正则同层排除全部括号字符）
ALL_BRACKETS = "\u3016\u3017\u27e6\u27e7\u3018\u3019"   # 〖〗⟦⟧〘〙
ENT_ANY_RE = re.compile("〖([^〗]+)〗")
NOUN_NESTED_RE = re.compile(
    "〖" + _cls(symbols.ENTITY_CODES) + "[^" + ALL_BRACKETS + "]*?〖"
    + _cls(symbols.ENTITY_CODES) + "[^" + ALL_BRACKETS + "]*?〗"
    + "[^" + ALL_BRACKETS + "]*?〗")
VERB_NESTED_RE = re.compile(
    "⟦" + _cls(symbols.VERB_CODES) + "[^" + ALL_BRACKETS + "]*?[⟦〖]"
    + "[^" + ALL_BRACKETS + "]*?[⟧〗]"
    + "[^" + ALL_BRACKETS + "]*?⟧")

# 旧符号残留检测（史记体系；新体系 15 实体 + 6 动词见 symbols.py）
LEGACY_ENT_TYPE_RE = re.compile(
    "〖(" + _cls(symbols.LEGACY_ENTITY_CODES) + ")")
LEGACY_VERB_TYPE_RE = re.compile(
    "⟦(" + _cls(symbols.LEGACY_VERB_CODES) + ")")
LEGACY_WRAP_RE = re.compile(
    "@[^@\\n]{1,30}@" if symbols.LEGACY_BRACKET_STYLES else r"(?!x)x")

PN_RE = re.compile(r"\[\d+(?:\.\d+)*\]")
FENCE_LINE_RE = re.compile(r"^:::.*$", re.MULTILINE)
HALFWIDTH_PUNCT_RE = re.compile(r"[,.:;?!\"]")
SQUARE_QUOTE_RE = re.compile(r"[「」『』]")
FULLWIDTH_PUNCT_RE = re.compile(r"[。，、；：？！“”‘’《》—…]")
SENTENCE_BOUNDARY_RE = re.compile(r"[。！？]")
MARKDOWN_SYM_RE = re.compile(r"[\*_`>\[\]]")


class SymbolConflictLinter:
    """符号冲突检查器（半角标点/直角引号/标注内外冲突/嵌套/跨标点/旧符号）"""

    def __init__(self):
        self.issues = defaultdict(list)

    # ---------------------------------------------------- 检查项 ----
    def check_halfwidth_punctuation(self, text, line_num=0):
        """检测半角标点（先剥标注令牌与 PN、围栏标记行，避免类型码误报）"""
        issues = []
        t = symbols.TOKEN_RE.sub("", text)
        t = PN_RE.sub("", t)
        t = FENCE_LINE_RE.sub("", t)
        for match in HALFWIDTH_PUNCT_RE.finditer(t):
            context = t[max(0, match.start() - 20):match.end() + 20]
            issues.append({
                "type": "halfwidth_punct",
                "char": match.group(),
                "pos": match.start(),
                "line": line_num,
                "context": context,
                "severity": "high",
                "message": f"禁止使用半角标点 {match.group()}，应使用全角"
                           "（02ab §4.2 铁律 4，围栏内同规）"
            })
        return issues

    def check_square_quotes(self, text, line_num=0):
        """检测直角引号（应使用弯引号“ ”）"""
        issues = []
        for match in SQUARE_QUOTE_RE.finditer(text):
            issues.append({
                "type": "square_quote",
                "char": match.group(),
                "pos": match.start(),
                "line": line_num,
                "context": text[max(0, match.start() - 20):match.end() + 20],
                "severity": "high",
                "message": "禁止使用直角引号 " + match.group()
                           + "，应使用弯引号“ ” ‘ ’"
            })
        return issues

    def _entity_content_issues(self, text, line_num, issue_type, severity,
                               pattern, message_fmt):
        """通用：实体令牌内容层冲突检测（标点/Markdown/跨句边界共用骨架）"""
        issues = []
        for match in ENT_ANY_RE.finditer(text):
            content = match.group(1)
            code_ok = bool(content) and (
                content[0] in symbols.ENTITY_CODES
                or content[0] in symbols.LEGACY_ENTITY_CODES)
            if not code_ok:
                continue
            body = content[1:]
            punct_match = pattern.search(body)
            if punct_match:
                issues.append({
                    "type": issue_type,
                    "annotation": match.group(),
                    "pos": match.start(),
                    "line": line_num,
                    "punct": punct_match.group(),
                    "context": text[max(0, match.start() - 20):match.end() + 20],
                    "severity": severity,
                    "message": message_fmt.format(punct_match.group())
                })
        return issues

    def check_punct_in_annotation(self, text, line_num=0):
        """检测标注内容内是否包含全角标点（消歧管道 | 除外）"""
        return self._entity_content_issues(
            text, line_num, "punct_in_annotation", "high",
            FULLWIDTH_PUNCT_RE,
            "标注内部不应包含标点符号 {}，标点应在标注外部")

    def check_markdown_in_annotation(self, text, line_num=0):
        """检测标注内容内是否包含 Markdown 语法（类型码 # 不算冲突）"""
        return self._entity_content_issues(
            text, line_num, "markdown_in_annotation", "medium",
            MARKDOWN_SYM_RE,
            "标注内部不应包含Markdown语法 {}")

    def check_nested_annotation(self, text, line_num=0):
        """检测嵌套标注（同层互嵌与动词层包实体层的交叉起步）"""
        issues = []
        for match in NOUN_NESTED_RE.finditer(text):
            issues.append({
                "type": "nested_annotation",
                "annotation": match.group(),
                "pos": match.start(),
                "line": line_num,
                "context": text[max(0, match.start() - 20):match.end() + 20],
                "severity": "high",
                "message": "检测到嵌套标注，应拍平或选择正确类型"
                           "（fix_nested_annotations.py 可自动拍平）"
            })
        for match in VERB_NESTED_RE.finditer(text):
            issues.append({
                "type": "nested_annotation",
                "annotation": match.group(),
                "pos": match.start(),
                "line": line_num,
                "context": text[max(0, match.start() - 20):match.end() + 20],
                "severity": "high",
                "message": "检测到嵌套/交叉标注（动词层含其他令牌），"
                           "应拍平或分开标注"
            })
        return issues

    def check_annotation_across_punct(self, text, line_num=0):
        """检测标注是否跨越句子边界标点（通常是错误的）"""
        return self._entity_content_issues(
            text, line_num, "annotation_across_punct", "high",
            SENTENCE_BOUNDARY_RE,
            "标注跨越句子边界标点 {}，应分开标注")

    def check_legacy_symbols(self, text, line_num=0):
        """检测史记体系旧符号：旧实体/动词码出现在令牌 TYPE 位，或旧式 @X@ 包裹"""
        issues = []
        for match in LEGACY_ENT_TYPE_RE.finditer(text):
            issues.append({
                "type": "legacy_symbol",
                "annotation": text[match.start():match.start() + 12],
                "pos": match.start(),
                "line": line_num,
                "context": text[max(0, match.start() - 20):match.start() + 40],
                "severity": "high",
                "message": f"史记体系残留：旧实体类型码 {match.group(1)} 出现在"
                           f" TYPE 位（现行 15 类实体见 symbols.ENTITIES）"
            })
        for match in LEGACY_VERB_TYPE_RE.finditer(text):
            issues.append({
                "type": "legacy_symbol",
                "annotation": text[match.start():match.start() + 12],
                "pos": match.start(),
                "line": line_num,
                "context": text[max(0, match.start() - 20):match.start() + 40],
                "severity": "high",
                "message": f"史记体系残留：旧动词域码 {match.group(1)} 出现在"
                           f" TYPE 位（现行 6 域动词见 symbols.VERBS）"
            })
        # 旧式 @X@ 检测须在剥除有效令牌后的残余文本上进行：
        # 相邻两个 〖@X〗 的 TYPE 位 @ 会在原始文本上跨标签误配对（004 试点发现）。
        residual = ENT_TOKEN_RE.sub("", text)
        residual = VERB_TOKEN_RE.sub("", residual)
        for match in LEGACY_WRAP_RE.finditer(residual):
            issues.append({
                "type": "legacy_symbol",
                "annotation": match.group(),
                "pos": match.start(),
                "line": line_num,
                "context": residual[max(0, match.start() - 20):match.end() + 20],
                "severity": "high",
                "message": "史记体系残留：旧式 @X@ 包裹标注，应改为 〖@X〗"
            })
        return issues

    # ---------------------------------------------------- 文件入口 ----
    CHECK_TYPES = ["halfwidth", "square", "punct_in", "markdown_in",
                   "nested", "across", "legacy"]

    def check_file(self, file_path: Path, check_types=None):
        if check_types is None:
            check_types = list(self.CHECK_TYPES)
        self.issues.clear()

        lines = Path(file_path).read_text(encoding="utf-8").splitlines()
        runners = {
            "halfwidth": self.check_halfwidth_punctuation,
            "square": self.check_square_quotes,
            "punct_in": self.check_punct_in_annotation,
            "markdown_in": self.check_markdown_in_annotation,
            "nested": self.check_nested_annotation,
            "across": self.check_annotation_across_punct,
            "legacy": self.check_legacy_symbols,
        }
        for line_num, line in enumerate(lines, 1):
            for ct in check_types:
                runner = runners.get(ct)
                if runner is None:
                    print(f"警告: 未知检查类型 {ct}", file=sys.stderr)
                    continue
                key = {"halfwidth": "halfwidth_punct", "square": "square_quote",
                       "punct_in": "punct_in_annotation",
                       "markdown_in": "markdown_in_annotation",
                       "nested": "nested_annotation",
                       "across": "annotation_across_punct",
                       "legacy": "legacy_symbol"}[ct]
                self.issues[key].extend(runner(line, line_num))
        return dict(self.issues)

    def format_report(self, file_path: Path, issues: dict) -> str:
        if not any(issues.values()):
            return f"✓ {file_path.name}: 无符号冲突问题\n"

        report = [f"\n{'=' * 60}"]
        report.append(f"文件: {file_path.name}")
        report.append("=" * 60)

        severity_order = {"high": 0, "medium": 1, "low": 2}
        all_issues = []
        for issue_list in issues.values():
            all_issues.extend(issue_list)
        all_issues.sort(key=lambda x: (severity_order[x["severity"]],
                                       x["line"], x["pos"]))

        for issue in all_issues:
            severity_label = {"high": "[高危]", "medium": "[中危]",
                              "low": "[低危]"}[issue["severity"]]
            report.append(f"\n{severity_label} 行{issue['line']}: {issue['type']}")
            report.append(f"  位置: {issue['context']}")
            report.append(f"  问题: {issue['message']}")

        return "\n".join(report)


def default_files(book=None):
    """缺省扫描 config.DIR_TAGGED 全库（--book 单书过滤）"""
    if not config.DIR_TAGGED.exists():
        print(f"标注目录不存在：{config.DIR_TAGGED}")
        return []
    book_dirs = ([config.DIR_TAGGED / book] if book
                 else sorted(p for p in config.DIR_TAGGED.iterdir() if p.is_dir()))
    files = []
    for d in book_dirs:
        if d.is_dir():
            files.extend(sorted(list(d.glob("*.struct.md")) + list(d.glob("*.tagged.md"))))
    return files


def main():
    parser = argparse.ArgumentParser(
        description="检查标点、标注、Markdown 符号的冲突和误用（含史记旧符号残留检测）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*",
                        help="要检查的文件（缺省扫 config.DIR_TAGGED 全库）")
    parser.add_argument("--book", default=None,
                        help="缺省扫描模式下只查指定书")
    parser.add_argument("--check-types",
                        help="检查类型（逗号分隔）：" + ",".join(
                            SymbolConflictLinter.CHECK_TYPES))
    parser.add_argument("--report", help="生成报告到文件")

    args = parser.parse_args()

    check_types = None
    if args.check_types:
        check_types = [t.strip() for t in args.check_types.split(",")]

    file_paths = [Path(p) for p in args.files] if args.files \
        else default_files(args.book)
    if not file_paths:
        print("未找到待检查文件。")
        return 1

    linter = SymbolConflictLinter()

    total_files = 0
    total_issues = defaultdict(int)
    reports = []

    for file_path in sorted(file_paths):
        if not file_path.exists():
            print(f"警告: 文件不存在 {file_path}", file=sys.stderr)
            continue
        total_files += 1
        issues = linter.check_file(file_path, check_types)
        for issue_type, issue_list in issues.items():
            total_issues[issue_type] += len(issue_list)
        report = linter.format_report(file_path, issues)
        reports.append(report)
        if any(issues.values()):
            print(report)

    summary = ["\n" + "=" * 60]
    summary.append("汇总统计")
    summary.append("=" * 60)
    summary.append(f"检查文件: {total_files} 个")
    total_count = sum(total_issues.values())
    summary.append(f"发现问题: {total_count} 处")

    if total_issues:
        summary.append("\n问题分类:")
        issue_type_names = {
            "halfwidth_punct": "半角标点",
            "square_quote": "直角引号",
            "punct_in_annotation": "标点在标注内",
            "markdown_in_annotation": "Markdown在标注内",
            "nested_annotation": "嵌套标注",
            "annotation_across_punct": "标注跨标点",
            "legacy_symbol": "旧符号残留（史记体系）",
        }
        for issue_type, count in sorted(total_issues.items(), key=lambda x: -x[1]):
            summary.append(f"  - {issue_type_names.get(issue_type, issue_type)}: {count} 处")

    summary_text = "\n".join(summary)
    print(summary_text)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("【符号冲突检查报告】\n")
            f.write(f"生成时间: {Path.cwd()}\n")
            f.write(f"检查文件: {total_files} 个\n\n")
            f.write("\n".join(reports))
            f.write("\n\n")
            f.write(summary_text)
        print(f"\n报告已保存到: {report_path}")

    return 0 if total_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
