#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/find_candidate_entities.py（2026-11-03）；改动：
#   1. 路径改经 config：扫 config.DIR_TAGGED/<书>/NNN.tagged.md（--book 单书），
#      输出落 config.DIR_LOGS/candidates（报告类产物，不进 git）；
#   2. 候选词表不再内置：MINGWU 内置表删除，改 --wordlist <名> 从
#      config.DIR_WORDLISTS/<名>.json 经 masker.load_wordlist 构建，
#      缺省 stopwords（泛称黑名单反查未标注候选）；--filter-file（每行一词）
#      仍可覆盖；
#   3. 标注抹除正则改用 symbols.TOKEN_RE（15 实体+6 动词+修辞统一剥除，
#      消灭 shiji 内联字符类与 symbols 的矛盾债）；
#   4. **保留"标注换行占位防伪 n-gram"设计**：标注命中处以换行占位，
#      切断跨标注的伪 n-gram 合并；
#   5. 武侠适配：围栏块（词/诗/…）整块移除后再统计——围栏内按 02ab §4.4
#      基本不标注，参与候选统计只会制造伪候选。

from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols
import masker

OUT_DIR = config.DIR_LOGS / "candidates"
CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")

# 去除 Markdown 结构；标注片段由 symbols.TOKEN_RE **完全抹掉**（含内容，不保留），
# 抹除时用换行替换，切断跨标注的 n-gram。
PARA_NUM_RE = re.compile(r"^\[\d+(?:\.\d+)*\]\s*", re.MULTILINE)
LIST_PN_RE = re.compile(r"^-\s+\[\d+(?:\.\d+)*\]\s*", re.MULTILINE)  # 对话拆分子段
HEADER_RE = re.compile(r"^#{1,6}.*$", re.MULTILINE)
LIST_RE = re.compile(r"^\s*[-*]\s+", re.MULTILINE)
TABLE_SEP_RE = re.compile(r"^\|[\s\-|]+\|?\s*$", re.MULTILINE)
HR_RE = re.compile(r"^-{3,}\s*$", re.MULTILINE)


def strip_fence_blocks(text: str) -> str:
    """围栏块（::: 类型 … :::）整块移除（武侠适配，见文件头改动 5）。"""
    out_lines = []
    in_fence = False
    for line in text.split("\n"):
        s = line.strip()
        if not in_fence:
            if symbols.fence_opens(s):
                in_fence = True
            else:
                out_lines.append(line)
        else:
            if symbols.is_fence_close(s):
                in_fence = False
            # 围栏内容丢弃
    return "\n".join(out_lines)


def extract_unannotated(text: str) -> str:
    """移除围栏块、所有标注（含内容）和 Markdown 结构，返回仅剩的未标注纯文本。
    标注位置以换行占位，防止跨标注的 n-gram 伪合并。"""
    text = strip_fence_blocks(text)
    text = HEADER_RE.sub("", text)
    text = PARA_NUM_RE.sub("", text)
    text = LIST_PN_RE.sub("", text)
    text = LIST_RE.sub("", text)
    text = HR_RE.sub("", text)
    text = TABLE_SEP_RE.sub("", text)
    text = symbols.TOKEN_RE.sub("\n", text)  # 实体/动词/修辞统一抹除 + 换行占位
    return text


def load_filter_words(name: str) -> set[str]:
    """从 wordlists/<名>.json 经 masker.load_wordlist 构建过滤词集。"""
    path = config.DIR_WORDLISTS / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"[错误] 词表不存在：{path}（wordlists/ 双轨数据，"
                         f"先经 wordlist_compiler.py 编译）")
    matcher = masker.load_wordlist(path)   # field=surface
    return {w for ws in matcher["index"].values() for w in ws}


def chapter_id(path: Path) -> str:
    """章节标识 = "<书名>:<回号>"（多书体系，02ab §2.6）。

    兼容 .tagged.md 命名：`001.tagged.md` → `<书>:001`；
    亦兼容 struct 层文件（`001.struct.md` → `<书>:001`）。
    write_outputs 的 file_by_id 必须与本函数同源，否则 KeyError。
    """
    name = path.name
    for suffix in (".tagged.md", ".struct.md"):
        if name.endswith(suffix):
            return f"{path.parent.name}:{name[:-len(suffix)]}"
    return f"{path.parent.name}:{path.stem}"


def parse_chapter(path: Path) -> tuple[str, str]:
    """返回 (章节标识, 未标注部分的纯文本 — 已标注内容完全移除)。
    章节标识 = "<书名>:<回号>"（多书体系，02ab §2.6）。"""
    cid = chapter_id(path)
    raw = path.read_text(encoding="utf-8")
    unannotated = extract_unannotated(raw)
    return cid, unannotated


def ngrams(text: str, n: int) -> list[str]:
    """从 CJK 连续字段里抽 n-gram。"""
    grams: list[str] = []
    for m in CJK_RE.finditer(text):
        run = m.group()
        if len(run) < n:
            continue
        for i in range(len(run) - n + 1):
            grams.append(run[i: i + n])
    return grams


def collect_candidates(
    files: list[Path],
    n_values: tuple[int, ...] = (2, 3, 4),
    min_freq: int = 5,
    keyword_filter: set[str] | None = None,
) -> tuple[dict[str, dict], dict[str, Counter]]:
    """返回 (全局 gram -> {freq,chapters}, 每章 gram -> Counter)。"""
    global_freq: dict[str, dict] = defaultdict(lambda: {"freq": 0, "chapters": set()})
    per_chapter: dict[str, Counter] = {}

    for f in files:
        chapter_id, stripped = parse_chapter(f)
        ch_counter: Counter = Counter()
        for n in n_values:
            for g in ngrams(stripped, n):
                if keyword_filter is not None and g not in keyword_filter:
                    continue
                ch_counter[g] += 1
                global_freq[g]["freq"] += 1
                global_freq[g]["chapters"].add(chapter_id)
        # 章级过滤后再看阈值
        ch_counter = Counter({k: v for k, v in ch_counter.items() if v >= 1})
        per_chapter[chapter_id] = ch_counter

    # 全局阈值过滤
    global_freq = {
        k: v for k, v in global_freq.items() if v["freq"] >= min_freq
    }
    return global_freq, per_chapter


def first_context(chapter_text: str, term: str, radius: int = 20) -> str:
    idx = chapter_text.find(term)
    if idx < 0:
        return ""
    left = max(0, idx - radius)
    right = min(len(chapter_text), idx + len(term) + radius)
    return ("…" if left > 0 else "") + chapter_text[left:right] + \
           ("…" if right < len(chapter_text) else "")


def write_outputs(
    global_freq: dict, per_chapter: dict[str, Counter], files: list[Path]
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    file_by_id = {chapter_id(f): f for f in files}

    # 每章 TSV（文件名用 "_" 替代 ":"，保 Windows 文件名安全）
    for cid, counter in per_chapter.items():
        if not counter:
            continue
        _, stripped = parse_chapter(file_by_id[cid])
        tsv_path = OUT_DIR / f"{cid.replace(':', '_')}_candidates.tsv"
        lines = ["候选词\t频次\t长度\t上下文"]
        for term, freq in counter.most_common():
            ctx = first_context(stripped, term).replace("\t", " ")
            lines.append(f"{term}\t{freq}\t{len(term)}\t{ctx}")
        tsv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 汇总 MD
    summary = OUT_DIR / "summary.md"
    lines = [
        "# 未标注候选实体发现",
        "",
        f"扫描回数：{len(files)} · 候选词数（全局去重）：{len(global_freq)}",
        "",
        "## 全局 TOP 50（按总频次降序）",
        "",
        "| 候选词 | 长度 | 总频次 | 覆盖回数 |",
        "|--------|----:|------:|--------:|",
    ]
    sorted_global = sorted(
        global_freq.items(), key=lambda x: (-x[1]["freq"], -len(x[0]))
    )
    for term, info in sorted_global[:50]:
        lines.append(f"| {term} | {len(term)} | {info['freq']} | {len(info['chapters'])} |")
    lines.append("")
    lines.append("## 逐回候选清单")
    lines.append("")
    for cid in sorted(per_chapter):
        counter = per_chapter[cid]
        if not counter:
            continue
        fname = file_by_id[cid].name.replace(".tagged.md", "")
        tsv_name = f"{cid.replace(':', '_')}_candidates.tsv"
        lines.append(f"- [{cid}](candidates/{tsv_name}) — {len(counter)} 候选"
                     f"（{fname}）")
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[输出] {summary.relative_to(config.ROOT)}")


def discover_files(book: str | None, chapter: str | None) -> list[Path]:
    if not config.DIR_TAGGED.exists():
        raise SystemExit(f"[错误] 标注目录不存在：{config.DIR_TAGGED}")
    if book:
        book_dirs = [config.DIR_TAGGED / book]
        if not book_dirs[0].is_dir():
            raise SystemExit(f"[错误] 未找到书目录：{book_dirs[0]}")
    else:
        book_dirs = sorted(p for p in config.DIR_TAGGED.iterdir() if p.is_dir())
    files: list[Path] = []
    for d in book_dirs:
        if chapter:
            files.extend(sorted(d.glob(f"{chapter.zfill(3)}.tagged.md")))
        else:
            files.extend(sorted(d.glob("*.tagged.md")))
    return files


def main() -> None:
    ap = argparse.ArgumentParser(
        description="发现未标注候选实体（n-gram 频次 + 词表反查）")
    ap.add_argument("--chapter", help="单回（如 001），缺省扫全部已标注回")
    ap.add_argument("--all", action="store_true", help="扫全部书的全部回")
    ap.add_argument("--book", help="只扫指定书（config.DIR_TAGGED/<书名>/）")
    ap.add_argument("--n", default="2,3,4", help="n-gram 长度，逗号分隔，默认 2,3,4")
    ap.add_argument("--min-freq", type=int, default=5, help="全局最小频次，默认 5")
    ap.add_argument(
        "--wordlist", default="stopwords",
        help="词表名（config.DIR_WORDLISTS/<名>.json，经 masker.load_wordlist 构建），"
             "缺省 stopwords=泛称黑名单反查未标注候选")
    ap.add_argument(
        "--filter-file",
        help="自定义词表（每行一词），覆盖 --wordlist")
    args = ap.parse_args()

    if not args.chapter and not args.all:
        ap.error("必须指定 --chapter 或 --all 之一")

    files = discover_files(args.book, args.chapter)
    if not files:
        print("未找到匹配章节。")
        return

    n_values = tuple(int(x) for x in args.n.split(","))

    keyword_filter: set[str] | None = None
    if args.filter_file:
        keyword_filter = set(
            w.strip()
            for w in Path(args.filter_file).read_text(encoding="utf-8").splitlines()
            if w.strip() and not w.startswith("#")
        )
    else:
        keyword_filter = load_filter_words(args.wordlist)

    print(
        f"[扫描] {len(files)} 回 · n={n_values} · min-freq={args.min_freq} "
        f"· 词表 {len(keyword_filter)} 词"
        f"（{'--filter-file' if args.filter_file else 'wordlists/' + args.wordlist + '.json'}）"
    )

    global_freq, per_chapter = collect_candidates(
        files, n_values, args.min_freq, keyword_filter
    )

    print(f"[结果] 命中词表并满足阈值的候选：{len(global_freq)} 条")

    write_outputs(global_freq, per_chapter, files)


if __name__ == "__main__":
    main()
