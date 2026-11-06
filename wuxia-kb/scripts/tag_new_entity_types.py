#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/tag_new_entity_types.py（2026-11-04，C16）；改动：
#   1. 四套内联史记词表（典籍/礼仪/刑法/思想）改为**武侠新增类型外置词表**：
#      只读编译产物 wordlists/new_entity_types.json（人工源 new_entity_types_source.md），
#      经 masker.load_wordlist / masker.find_candidates 消费；词表是数据不是代码。
#      类型=01g 定版实体码：☆ 武功技艺 / • 器物 / { 作品文书 / ◆ 组织。
#   2. 路径一律走 config（原版写死 chapter_md/data/patches）；文件枚举改用
#      config.DIR_TAGGED/<书>/NNN.tagged.md，支持 --book/--chapter/--all。
#   3. 已标注保护改用 symbols.TOKEN_RE（原版内联字符类）：先把令牌整段掩成等长占位再
#      做最长匹配，天然保证「已标注区间不重复标注」且不会跨令牌边界拼词。
#   4. 围栏块（::: 词/诗/歌/…/回末/回末对）整块跳过——02ab §4.4 三层豁免表里
#      回末/回末对为「全不标」，词/诗/歌为「实体限实指」，词表召回无法判实指，故保守跳过；
#      回目行（# [0] …）与标题行同样跳过。
#   5. 只出**建议 TSV**，默认不写 tagged（原版直接改 chapter_md）。TSV 列与
#      scripts/apply_annotation_patches.py 的 load_tsv 契约兼容（前 8 列：章节/全名/词/
#      位置/框架类型/匹配模式/上下文/实体类型），第 9-10 列（词表档位/证据）为复核用扩展列，
#      load_tsv 会忽略多余列。
#   6. --apply 可选：写前备份 + 应用后「剥标还原断言」（剥标文本必须与写前逐字相同），
#      断言失败自动回滚。默认关闭；本轮验收不跑 apply。
#
# 用法：
#   python scripts/tag_new_entity_types.py --book 白发魔女传 --chapter 001
#   python scripts/tag_new_entity_types.py --all                 # 全库 dry（只出 TSV）
#   python scripts/tag_new_entity_types.py --all --dry-run       # 不落盘，只看统计
#   python scripts/tag_new_entity_types.py --all --types 武功 器物
#   python scripts/tag_new_entity_types.py --book 白发魔女传 --chapter 001 --apply

import argparse
import io
import json
import re
import shutil
import sys
from collections import Counter, OrderedDict
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols
import masker

# 实体码 → 建议 TSV 中文类型名（对齐 apply_annotation_patches.TYPE_NAME_TO_CODE 的键）
CODE_TO_TYPE_NAME = {
    "☆": "武功",
    "•": "器物",
    "{": "作品",
    "◆": "门派",
}
# 中文类型名 / 实体码 → 实体码（--types 用）
TYPE_ALIASES = {
    "武功": "☆", "武功技艺": "☆", "技艺": "☆", "招式": "☆", "☆": "☆",
    "器物": "•", "神兵": "•", "•": "•",
    "作品": "{", "作品文书": "{", "典籍": "{", "{": "{",
    "门派": "◆", "组织": "◆", "◆": "◆",
}
# 逐词 (前缀正则, 后缀正则) 负规则——词形同形歧义（保留 shiji 的 prefix/suffix 机制）：
#   大明＝天亮 / 神拳无敌＝绰号 / 剑诀一领＝剑指手势 / 武当山＝地点 / 满洲话＝语族义
WORD_RULES = {
    "大明": (r"[天已渐微]", None),
    "神拳": (None, r"无敌"),
    "剑诀": (None, r"[一领捏]"),
    "武当": (None, r"[山寺观]"),
    "少林": (None, r"[寺]"),
    "满洲": (None, r"[话人]"),
    "满州": (None, r"[话人]"),
}
# 类型级负规则（在 hit_blocked 内以「下一令牌码」判断）：◆ 组织后紧接 ☆ 武功标注
# （如 武当〖☆剑法〗）说明「门派+技艺」复合词被既有标注切成两段，不应再拆组织前缀。

# ts 扩展列（load_tsv 忽略；供人工复核 tier/evidence，落实「watch 只观察」纪律）
TSV_HEADER = ("章节\t全名\t词\t位置\t框架类型\t匹配模式\t上下文\t实体类型"
              "\t词表档位\t证据\n")
PLACEHOLDER = "\uFFFD"
TAGGED_FILE_RE = re.compile(r"^(\d{1,3})\.tagged\.md$")


# ── 资源加载 ────────────────────────────────────────────────────────────────
def load_resources(wordlist_name: str):
    """读编译后词表 → (matcher, 元数据 dict)。"""
    wl_path = config.DIR_WORDLISTS / f"{wordlist_name}.json"
    if not wl_path.exists():
        print(f"词表不存在：{wl_path}\n先跑 python scripts/wordlist_compiler.py "
              f"--name {wordlist_name}（禁 --all）")
        sys.exit(1)
    matcher = masker.load_wordlist(wl_path, field="surface")
    data = json.loads(wl_path.read_text(encoding="utf-8"))
    # 顶层兼容：D09 产物为 {"items": [...]}，也接受裸 list（与 masker/wordlist_compiler 一致）
    items = data if isinstance(data, list) else data.get("items", [])
    meta = {}
    for it in items:
        surface = it.get("surface", "").strip()
        if surface:
            meta[surface] = {
                "canonical": it.get("canonical") or surface,
                "type": it.get("type"),
                "tier": it.get("tier", "watch"),
                "conf": it.get("conf", "weak"),
                "evidence": " ".join(it.get("evidence") or []),
            }
    return matcher, meta


# ── 行级工具 ────────────────────────────────────────────────────────────────
def fence_line_set(lines):
    """围栏块行号集合（含 ::: 标记行与整块内容行；0-based）。

    02ab §4.4：回末/回末对全不标；词/诗/歌等实体限实指，词表召回无法判实指 → 保守跳过。
    """
    fenced = set()
    in_fence = False
    for i, raw in enumerate(lines):
        s = raw.strip()
        if in_fence:
            fenced.add(i)
            if symbols.is_fence_close(s):
                in_fence = False
        elif symbols.fence_opens(s) is not None:
            fenced.add(i)
            in_fence = True
    return fenced


def mask_tokens(line: str):
    """把已标注令牌整段掩成等长占位（位置与原文 1:1 对齐），返回 (masked, spans)。"""
    spans = [(m.start(), m.end()) for m in symbols.TOKEN_RE.finditer(line)]
    if not spans:
        return line, spans
    chars = list(line)
    for a, b in spans:
        for j in range(a, b):
            chars[j] = PLACEHOLDER
    return "".join(chars), spans


def is_skippable_line(line: str):
    """回目行/标题行跳过（# [0] 回目、## 场景小节、空行）。"""
    s = line.lstrip()
    return (not s.strip()) or s.startswith("#")


def context_of(line: str, pos: int, word: str, width: int = 10):
    a = max(0, pos - width)
    b = min(len(line), pos + len(word) + width)
    return line[a:b].replace("\n", "↵")


# ── 令牌边界辅助（负规则跨令牌可见字符）────────────────────────────────────
def token_display(m):
    """TOKEN_RE 匹配 → (显示串, 类型码)。"""
    body = m.group("ent") or m.group("verb") or m.group("rhet") or ""
    if not body:
        return "", None
    code, rest = body[0], body[1:]
    return rest.split("|", 1)[0], code


def token_ending_at(line: str, pos: int):
    """结束于 pos 的令牌（pos 处紧邻 〗）→ (显示串, 类型码)；无则 None。"""
    if pos <= 0 or line[pos - 1] != "〗":
        return None
    for m in symbols.TOKEN_RE.finditer(line):
        if m.end() == pos:
            return token_display(m)
    return None


def token_starting_at(line: str, pos: int):
    """起始于 pos 的令牌（pos 处紧邻 〖）→ (显示串, 类型码)；无则 None。"""
    if pos >= len(line) or line[pos] != "〖":
        return None
    for m in symbols.TOKEN_RE.finditer(line):
        if m.start() == pos:
            return token_display(m)
    return None


def prev_visible(line: str, pos: int) -> str:
    """pos 左侧可见字符：紧邻 〗 时取该令牌显示串末字，跨令牌边界仍能命中前缀规则。"""
    tok = token_ending_at(line, pos)
    if tok:
        return tok[0][-1] if tok[0] else ""
    return line[pos - 1] if pos > 0 else ""


def next_visible(line: str, end: int) -> str:
    """end 右侧可见文本：紧邻 〖 时取该令牌显示串，跨令牌边界仍能命后缀规则。"""
    tok = token_starting_at(line, end)
    if tok:
        return tok[0]
    return line[end:]


def hit_blocked(line: str, pos: int, word: str, code: str) -> bool:
    """逐词/类型级负规则：同形歧义词与复合词前缀不产出建议。

    前缀/后缀负规则在**可见字符**上判断（docs/46 §二-7）：负规则要用的邻字若落在既有
    标注令牌内（右侧紧邻 〖 / 左侧紧邻 〗），改取该令牌显示串的首/末字，避免因括号
    导致正则失配；没有令牌时仍走裸文分支。`◆` 组织后紧接 ☆ 武功令牌（武当〖☆剑法〗）
    说明「门派+技艺」复合被既有标注切成两段，不拆组织前缀。
    """
    pre, suf = WORD_RULES.get(word, (None, None))
    prev = prev_visible(line, pos)
    nxt = next_visible(line, pos + len(word))
    if pre and prev and re.match(pre, prev):
        return True
    if suf and nxt and re.match(suf, nxt):
        return True
    if code == "◆":
        nxt_tok = token_starting_at(line, pos + len(word))
        if nxt_tok and nxt_tok[1] == "☆":
            return True
    return False


# ── 扫描 ────────────────────────────────────────────────────────────────────
def scan_chapter(fpath: Path, matcher, meta, type_filter=None, min_freq=1):
    """扫描单回，返回建议列表（dict：chapter/full_name/word/pos/frame_type/pattern/
    context/entity_type/tier/evidence）。

    - 已标注区间：令牌掩码保护，不重复标注；
    - 最长优先、不重叠：masker.find_candidates(overlap_free=True)；
    - 围栏块 / 回目行 / 标题行跳过；
    - 位置 = **原文偏移（含标记）**：`line_start + 行内偏移`；masked 与原文等长
      （mask_tokens 整段占位），故 masked 行内索引 == 原文行内索引；TSV `位置` 可直接
      用 `原文[pos:pos+len(word)] == word` 断言。
    """
    content = fpath.read_text(encoding="utf-8")
    lines = content.split("\n")
    fenced = fence_line_set(lines)

    suggestions = []
    line_start = 0
    for i, line in enumerate(lines):
        if i in fenced or is_skippable_line(line):
            line_start += len(line) + 1
            continue
        masked, _spans = mask_tokens(line)
        for word, pos, end in masker.find_candidates(masked, matcher):
            if len(word) <= 1:                     # 单字不入建议（档位纪律）
                continue
            item = meta.get(word)
            if item is None:
                continue
            code = item["type"]
            if type_filter and code not in type_filter:
                continue
            if hit_blocked(line, pos, word, code):
                continue
            suggestions.append({
                "chapter": fpath.stem.replace(".tagged", ""),
                "full_name": item["canonical"],
                "word": word,
                "pos": line_start + pos,
                "frame_type": "词表匹配",
                "pattern": word,
                "context": context_of(line, pos, word),
                "entity_type": CODE_TO_TYPE_NAME.get(
                    code, symbols.ENTITIES.get(code, "")),
                "tier": item["tier"],
                "evidence": item["evidence"],
            })
        line_start += len(line) + 1

    # 章内词频门槛（--min-freq）
    freq = Counter(s["word"] for s in suggestions)
    suggestions = [s for s in suggestions if freq[s["word"]] >= min_freq]
    suggestions.sort(key=lambda s: s["pos"])
    return suggestions


# ── 输出 ────────────────────────────────────────────────────────────────────
def tsv_chapter_field(book: str, stem: str, multi_book: bool):
    """章节列：单书写 001（与 C7 既有补丁惯例一致）；多书写 书名/001 消歧（§2.6）。"""
    return f"{book}/{stem}" if multi_book else stem


def write_tsv(out_path: Path, suggestions, multi_book, book):
    lines = [TSV_HEADER]
    for s in suggestions:
        chapter = tsv_chapter_field(book, s["chapter"], multi_book)
        lines.append("\t".join([
            chapter, s["full_name"], s["word"], str(s["pos"]),
            s["frame_type"], s["pattern"], s["context"],
            s["entity_type"], s["tier"], s["evidence"],
        ]) + "\n")
    out_path.write_text("".join(lines), encoding="utf-8")


def backup_file(fpath: Path):
    bdir = config.ROOT / "backup" / "apply_patches"
    bdir.mkdir(parents=True, exist_ok=True)
    dst = bdir / f"{fpath.parent.name}_{fpath.name}"
    shutil.copy2(fpath, dst)
    return dst


def apply_tsv(tsv_path: Path, fpath: Path):
    """可选 --apply：备份 → 调 C7 应用 → 剥标还原断言 → 失败回滚。"""
    import apply_annotation_patches as c7
    before = symbols.strip_markup(fpath.read_text(encoding="utf-8"))
    bak = backup_file(fpath)
    res = c7.apply_tsv_to_chapter(tsv_path, dry_run=False)
    after_text = fpath.read_text(encoding="utf-8")
    after = symbols.strip_markup(after_text)
    # 剥标还原断言：标注只加不改，剥标后必须与写前逐字相同（01g 原文无损）
    if after != before:
        shutil.copy2(bak, fpath)
        print(f"  [FATAL] 剥标还原断言失败，已回滚：{fpath}")
        return False
    print(f"  [apply] {fpath.name}: 插入 {res['applied']} 处（备份 {bak.name}，"
          f"剥标断言 PASS）")
    return True


# ── 主流程 ──────────────────────────────────────────────────────────────────
def iter_chapter_files(book=None, chapter=None):
    if not config.DIR_TAGGED.exists():
        return []
    book_dirs = ([config.DIR_TAGGED / book] if book
                 else sorted(p for p in config.DIR_TAGGED.iterdir()
                             if p.is_dir() and not p.name.startswith("_")))
    files = []
    for d in book_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.tagged.md")):
            if not TAGGED_FILE_RE.match(f.name):
                continue
            if chapter and f.name != f"{chapter.zfill(3)}.tagged.md":
                continue
            files.append(f)
    return files


def main():
    ap = argparse.ArgumentParser(
        description="武侠新增实体类型（☆武功/•器物/{作品/◆组织）建议标注：只出建议 TSV，"
                    "默认不写 tagged")
    ap.add_argument("--book", default=None, help="只处理指定书（缺省全库）")
    ap.add_argument("--chapter", default=None, help="单回编号（如 001）")
    ap.add_argument("--all", action="store_true", help="全库全部回（与 --book/--chapter 互斥）")
    ap.add_argument("--types", nargs="+", default=None,
                    help="只扫描指定类型：武功/器物/作品/门派（或实体码 ☆•{◆）")
    ap.add_argument("--min-freq", type=int, default=1,
                    help="章内最少出现次数（默认 1）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只统计不落盘（默认会写建议 TSV，但仍不写 tagged）")
    ap.add_argument("--out", default=None,
                    help=f"建议 TSV 输出目录（缺省 {config.DIR_REGISTRY / 'patches'}）")
    ap.add_argument("--wordlist", default="new_entity_types",
                    help="词表名（wordlists/<名>.json，缺省 new_entity_types）")
    ap.add_argument("--apply", action="store_true",
                    help="[可选] 应用建议到 tagged（写前备份 + 剥标断言）；默认关闭")
    args = ap.parse_args()

    if args.all and (args.book or args.chapter):
        ap.error("--all 与 --book/--chapter 互斥")

    type_filter = None
    if args.types:
        type_filter = set()
        for t in args.types:
            code = TYPE_ALIASES.get(t)
            if code is None:
                ap.error(f"未知类型「{t}」；可用：{' '.join(sorted(TYPE_ALIASES))}")
            type_filter.add(code)

    matcher, meta = load_resources(args.wordlist)
    kept = [s for s, it in meta.items() if len(s) > 1]
    print(f"词表 {args.wordlist}：{matcher['count']} 条（单字 {matcher['count'] - len(kept)} 条不入标）"
          f" 类型分布：{dict(Counter(it['type'] for it in meta.values()))}")

    files = iter_chapter_files(args.book, args.chapter)
    if not files:
        print("未找到匹配的 tagged 文件")
        return 1
    books = sorted({f.parent.name for f in files})
    multi_book = len(books) > 1
    out_dir = Path(args.out) if args.out else config.patches_dir(args.book)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    mode = "预览（不落盘）" if args.dry_run else "建议 TSV"
    print(f"{mode}：{len(files)} 回，{len(books)} 书 {books}\n")

    total = 0
    n_files = 0
    by_type = Counter()
    by_word = Counter()
    for f in files:
        sug = scan_chapter(f, matcher, meta, type_filter, args.min_freq)
        if not sug:
            continue
        n_files += 1
        total += len(sug)
        by_type.update(s["entity_type"] for s in sug)
        by_word.update(s["word"] for s in sug)
        if not args.dry_run:
            out = out_dir / f"{f.name.replace('.tagged.md', '')}_new_entities.tsv"
            write_tsv(out, sug, multi_book, f.parent.name)
            print(f"  {f.parent.name}/{f.name}: {len(sug)} 条建议 → {out.name}")
        else:
            print(f"  {f.parent.name}/{f.name}: {len(sug)} 条建议")

    print(f"\n{'=' * 60}")
    print(f"合计 {total} 条建议，{len(by_word)} 个词种，{n_files} 回有命中")
    if by_type:
        print(f"类型分布：{dict(by_type)}")
    if by_word:
        print("Top 15 高频词：")
        for w, n in by_word.most_common(15):
            print(f"  {w}: {n}")

    if args.apply:
        if args.dry_run:
            print("--apply 与 --dry-run 互斥，跳过应用")
            return 0
        print("\n[--apply] 开始应用建议（写前备份 + 剥标断言）")
        ok = True
        for f in files:
            out = out_dir / f"{f.name.replace('.tagged.md', '')}_new_entities.tsv"
            if out.exists():
                ok = apply_tsv(out, f) and ok
        print("应用完成" if ok else "应用失败（见上）")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
