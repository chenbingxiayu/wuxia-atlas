#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/lint_text_integrity.py（2026-11-03）；改动：
#   1. 剥标注改统一入口：Markdown 结构剥离内置（标题/围栏标记行 ^:::.*$ 规则
#      免改照搬/列表/段号/表格分隔线），语义令牌剥到显示串走 symbols.strip_markup
#      （替换原内联 18 类字符类的多段正则）；
#   2. 多书路径接 config：底本 config.CORPUS_ROOT/<书>/NNN*.txt，
#      标注 config.DIR_TAGGED/<书>/NNN.tagged.md；支持 --book 单书/缺省全部，
#      位置参数仍是回号列表（如 001 002）；
#   3. _NORM_TABLE 繁简/异体规范化映射表保留但逐条标注 TODO（武侠底本重审），
#      默认关闭：新增 --norm 开关；武侠首轮对账用字符级严格模式（默认只做
#      结构性清理：管道/PUA/[rN] 行标，不做字形翻译）；
#   4. 白名单机制保留（scripts/lint_whitelist.txt，键改"书名/回号"），内容清空
#      待试点回填——文件不存在时机制静默生效（零条目）；
#   5. 原文首行回目标题跳过规则改为武侠口径（首行含"第…回"即视为回目行，
#      待试点校准）；
#   6. 嵌套标注检测正则改由 symbols 码位动态构建（替换内联字符类）。

import argparse
import difflib
import io
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols

# ── 白名单：已确认的正确校勘 ─────────────────────────────
# 文件格式（TSV）：书名/回号 \t 原文片段 \t 标注片段（# 开头为注释）
# 内容清空待试点回填：文件缺失 = 白名单为空（机制保留）。
WHITELIST_PATH = config.DIR_SCRIPTS / "lint_whitelist.txt"


def _load_whitelist(path: Path) -> dict:
    """读取 lint_whitelist.txt，返回 {"书名/回号": [(orig, tagged), ...]}；
    兼容旧格式（仅回号）作为通配键。"""
    wl = {}
    if not path.exists():
        return wl
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        key = parts[0].strip()
        if re.match(r"^\d{1,3}$", key):
            key = key.zfill(3)          # 旧格式：仅回号（通配）
        wl.setdefault(key, []).append((parts[1], parts[2]))
    return wl


# ── 预处理规范化映射 ──────────────────────────────────────
# 对原文和标注各自做同样的规范化，然后比较规范化结果。
# 差异 = 规范化后仍存在 → 实质差异；差异 = 规范化后消失 → 标点/编码规范化。
# 武侠纪律：默认关闭（--norm 启用），逐条 TODO 待武侠底本重审——
# 史记文言通假结论对梁羽生白话底本一律不预设成立。

_NORM_TABLE = str.maketrans({
    # TODO（武侠底本重审）：各式引号 → 统一删除（底本若自带引号则此条不成立）
    "\u201c": "",   # " (左双引号)
    "\u201d": "",   # " (右双引号)
    "\u300c": "",   # 「
    "\u300d": "",   # 」
    "\u300e": "",   # 『
    "\u300f": "",   # 』
    "\u2018": "",   # ' (左单引号)
    "\u2019": "",   # ' (右单引号)
    "\"": "",       # 半角双引号（历史遗留）
    "'": "",        # 半角单引号（历史遗留）
    # TODO（武侠底本重审）：字形变体 巿→市
    "\u5dff": "\u5e02",
    # TODO（武侠底本重审）：通假/异体字对（史记文本常见，武侠白话底本逐条核对）
    "\u4e8e": "\u65bc",  # 于 → 於
    "\u4e0e": "\u8207",  # 与 → 與
    "\u4e3a": "\u70ba",  # 为 → 為
    # TODO（武侠底本重审）：繁简变体
    "\u540e": "\u5f8c",  # 后 → 後
    "\u4f59": "\u9980",  # 余 → 馀
    "\u4fee": "\u8129",  # 修 → 脩
    "\u8c37": "\u7a40",  # 谷 → 穀
    "\u9002": "\u9069",  # 适 → 適
    "\u85e9": "\u7c53",  # 藩 → 籓
    "\u8912": "\u8943",  # 褒 → 襃
    "\u513f": "\u5152",  # 儿 → 兒
    "\u95f2": "\u95f4",  # 闲 → 间（年表语境等价）
    "\u9638": "\u6239",  # 阸 → 戹
    "\u5e72": "\u5e79",  # 干 → 幹
})


def _norm(text: str, translate: bool = False) -> str:
    """规范化：结构性清理恒做（管道/[rN]/PUA）；字形翻译仅 --norm 时做。"""
    if translate:
        text = text.translate(_NORM_TABLE)
    # 表格管道 | 是结构性添加，不影响文本内容
    text = text.replace("|", "")
    # 行内标记 [r1] [r2] 等行标
    text = re.sub(r"\[r\d+\]", "", text)
    # PUA 私用区字符：两侧都去掉，避免影响对齐
    text = re.sub(r"[\ue000-\uf8ff]", "", text)
    return text


# ═══════════════════════════════════════════════════════════
# 标注去除
# ═══════════════════════════════════════════════════════════

def strip_markup(text: str) -> str:
    """去除全部结构层与语义标注，保留原文显示串。"""
    # 1. Markdown 标题行（不在原文中）
    text = re.sub(r"^#{1,6}.*$", "", text, flags=re.MULTILINE)
    # 2. ::: 围栏块标记行（规则免改照搬；围栏内容本身保留参与对账）
    text = re.sub(r"^:::.*$", "", text, flags=re.MULTILINE)
    # 3. 行首引用符 "> "
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # 4. 行首列表符 "- "（含缩进子列表）
    text = re.sub(r"^\s*-\s", "", text, flags=re.MULTILINE)
    # 5. 段落编号 [1] [1.1] 等
    text = re.sub(r"^\[\d+(?:\.\d+)*\]\s*", "", text, flags=re.MULTILINE)
    # 6. 粗体 **content** → content
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    # 7. Markdown 分隔线
    text = re.sub(r"^-{3,}\s*$", "", text, flags=re.MULTILINE)
    # 8. Markdown 表格分隔行
    text = re.sub(r"^\|[\s\-|]+\|?\s*$", "", text, flags=re.MULTILINE)
    # 9. 语义标注 → 显示串（统一入口 symbols.strip_markup：
    #    〖@显示名|规范名〗→显示名、⟦⊞动词|消歧⟧→动词、〘※…〙→内容）
    return symbols.strip_markup(text)


def to_flat(text: str) -> str:
    """去除全部空白，返回单一字符序列（用于逐字比对）。"""
    return re.sub(r"\s+", "", text)


# ═══════════════════════════════════════════════════════════
# 差异分类
# ═══════════════════════════════════════════════════════════

def _ctx(flat: str, pos: int, half: int = 22) -> str:
    lo = max(0, pos - half)
    hi = min(len(flat), pos + half)
    pre = "…" if lo > 0 else ""
    suf = "…" if hi < len(flat) else ""
    return f"{pre}{flat[lo:hi]}{suf}"


def compare_texts(orig_flat: str, tagged_flat: str, translate: bool = False) -> dict:
    """比对两段平铺文本；规范化版本找实质差异，原始版本取上下文。"""
    orig_norm = _norm(orig_flat, translate)
    tagged_norm = _norm(tagged_flat, translate)

    real_diffs = []
    sm_norm = difflib.SequenceMatcher(None, orig_norm, tagged_norm, autojunk=False)
    for tag, i1, i2, j1, j2 in sm_norm.get_opcodes():
        if tag == "equal":
            continue
        real_diffs.append({
            "tag": tag,
            "orig": orig_norm[i1:i2],
            "tagged": tagged_norm[j1:j2],
            "orig_ctx": _ctx(orig_norm, i1),
            "tagged_ctx": _ctx(tagged_norm, j1),
        })

    # 标点/编码差异总数（严格比对 - 规范化比对 = 变体差异）
    sm_raw = difflib.SequenceMatcher(None, orig_flat, tagged_flat, autojunk=False)
    raw_count = sum(1 for t, *_ in sm_raw.get_opcodes() if t != "equal")
    encoding_count = sum(
        1 for t, i1, i2, j1, j2 in sm_raw.get_opcodes()
        if t != "equal" and (
            any(0xE000 <= ord(c) <= 0xF8FF for c in orig_flat[i1:i2]) or
            any(0xE000 <= ord(c) <= 0xF8FF for c in tagged_flat[j1:j2])
        )
    )
    total_variant = raw_count - len(real_diffs) - encoding_count
    return {
        "real": real_diffs,
        "punct_count": max(0, total_variant),
        "encoding_count": encoding_count,
    }


# ═══════════════════════════════════════════════════════════
# 嵌套标注检测（正则由 symbols 码位动态构建）
# ═══════════════════════════════════════════════════════════

def _cls(codes):
    return "[" + "".join(re.escape(c) for c in sorted(codes)) + "]"


_ALL_BRACKETS = "\u3016\u3017\u27e6\u27e7\u3018\u3019"
_NOT_BRACKET = "[^" + _ALL_BRACKETS + "]*?"
_NOUN_NESTED = re.compile(
    "〖" + _cls(symbols.ENTITY_CODES) + _NOT_BRACKET
    + "〖" + _cls(symbols.ENTITY_CODES) + _NOT_BRACKET + "〗" + _NOT_BRACKET + "〗")
_VERB_NESTED = re.compile(
    "⟦" + _cls(symbols.VERB_CODES) + _NOT_BRACKET
    + "[⟦〖]" + _NOT_BRACKET + "[⟧〗]" + _NOT_BRACKET + "⟧")


def detect_nested_annotations(text: str) -> list:
    nested = []
    lines = text.split("\n")
    for line_num, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("#") or s.startswith(":::"):
            continue
        for rex, label in ((_NOUN_NESTED, "nested_noun"),
                           (_VERB_NESTED, "nested_verb")):
            for match in rex.finditer(line):
                nested.append({
                    "type": label,
                    "match": match.group(),
                    "line": line_num,
                    "context": _ctx(line, match.start(), half=30),
                })
    return nested


# ═══════════════════════════════════════════════════════════
# 单回检查
# ═══════════════════════════════════════════════════════════

def find_orig_file(book: str, no: int):
    """回号 → 底本文件路径（config.CHAPTER_FILE_RE 按三位回号前缀/中文回号双匹配）"""
    try:
        return config.chapter_path(book, no)
    except FileNotFoundError:
        return None


def check_chapter(book: str, no: int, check_nested=False, translate=False):
    orig_file = find_orig_file(book, no)
    tagged_file = config.tagged_path(book, no)
    if orig_file is None or not orig_file.exists():
        return None, None, "找不到原文底本文件", None
    if not tagged_file.exists():
        return None, None, "找不到标注文件", None

    tagged_text = tagged_file.read_text("utf-8")
    nested = detect_nested_annotations(tagged_text) if check_nested else None

    orig_text = orig_file.read_text("utf-8")
    # 原文首行为回目标题行（武侠口径：含"第…回"即视为标题，跳过；待试点校准）
    orig_lines = orig_text.splitlines(keepends=True)
    if orig_lines:
        first = orig_lines[0].strip()
        if re.search(r"第.{1,12}回", first[:30]):
            orig_text = "".join(orig_lines[1:]) if len(orig_lines) > 1 else ""
    orig_flat = to_flat(orig_text)
    tagged_flat = to_flat(strip_markup(tagged_text))
    result = compare_texts(orig_flat, tagged_flat, translate)
    return orig_file.stem, result, None, nested


# ═══════════════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════════════

_TAG_ZH = {
    "replace": "替换",
    "insert": "插入（标注多字）",
    "delete": "删除（标注少字）",
}


def fmt_diff(d, idx):
    label = _TAG_ZH.get(d["tag"], d["tag"])
    orig_s = repr(d["orig"]) if d["orig"] else "（空）"
    tagged_s = repr(d["tagged"]) if d["tagged"] else "（空）"
    return (
        f"  [{idx}] {label}\n"
        f"      原文  : {orig_s}\n"
        f"      标注  : {tagged_s}\n"
        f"      原文上下文 : {d['orig_ctx']}\n"
        f"      标注上下文 : {d['tagged_ctx']}"
    )


def _is_whitelisted(d, wl_entries):
    for wl_orig, wl_tagged in wl_entries:
        if d["orig"] == wl_orig and d["tagged"] == wl_tagged:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(
        description="标注文本完整性检查（剥标后与锁定底本逐字对账；默认字符级严格模式）")
    ap.add_argument("chapters", nargs="*", help="回号列表（如 001 002；缺省查全部）")
    ap.add_argument("--book", default=None, help="只查指定书（缺省全部书）")
    ap.add_argument("--all", action="store_true", help="包含标点/编码差异详情")
    ap.add_argument("--check-nested", action="store_true", help="检测嵌套标注")
    ap.add_argument("--norm", action="store_true",
                    help="启用繁简/异体规范化映射（默认关闭；武侠底本重审前勿开）")
    args = ap.parse_args()

    show_all = args.all
    check_nested = args.check_nested
    translate = args.norm

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

    whitelist = _load_whitelist(WHITELIST_PATH)
    mode_note = "规范化模式(--norm)" if translate else "字符级严格模式(默认)"

    results = []
    for book in book_list:
        # 回号清单：位置参数指定，或该书全部已标注回
        if args.chapters:
            nos = [int(c) for c in args.chapters]
        else:
            files_ib = list((config.DIR_TAGGED / book).glob("*.struct.md")) +                 list((config.DIR_TAGGED / book).glob("*.tagged.md"))
            # 2026-11-05 修复：struct+tagged 双 glob 会把同一回计两次（48 回→96 回，
            # 全局完成门耗时翻倍，江湖 accept 94–96% 时间耗在此处）；去重后每回只查一次。
            nos = sorted({int(m.group(1)) for f in files_ib
                          if (m := re.match(r"^(\d{1,3})\.(?:struct|tagged)\.md$", f.name))})
        for no in nos:
            name, result, err, nested = check_chapter(book, no,
                                                      check_nested, translate)
            results.append((book, no, name, result, err, nested))
            wl_key = f"{book}/{no:03d}"
            wl_entries = whitelist.get(wl_key, []) + whitelist.get(f"{no:03d}", [])
            if err:
                print(f"  {book} {no:03d}: ⚠ {err}")
                continue
            nr_raw = len(result["real"])
            nr = sum(1 for d in result["real"] if not _is_whitelisted(d, wl_entries))
            n_wl = nr_raw - nr
            nn = len(nested) if nested else 0
            mark = "✓" if nr == 0 and nn == 0 else "✗"
            wl_note = f"  校勘:{n_wl}" if n_wl else ""
            nest_note = f"  嵌套:{nn}" if check_nested else ""
            print(f"  {mark} {book} {no:03d}（{name}）: {nr}处实质差异"
                  f"  {result['punct_count']}处标点  "
                  f"{result['encoding_count']}处编码{wl_note}{nest_note}")

    # ── 报告 ──
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    suffix = ("_" + args.book) if args.book else ""
    if args.chapters:
        suffix += "_" + "_".join(c.zfill(3) for c in args.chapters)
    config.DIR_LOGS.mkdir(parents=True, exist_ok=True)
    out = config.DIR_LOGS / f"lint_text_integrity{suffix}.txt"

    lines = [
        "# 标注文本完整性检查报告",
        f"# 生成时间: {ts}",
        f"# 比对模式: {mode_note}",
        f"# 检查范围: {len(book_list)} 部书 {len(results)} 回",
        "",
        "分类说明:",
        "  【实质差异】= 汉字字符增/删/改，需要人工修复",
        "  【标点规范化】= 全角↔半角等价转换（，→, 等），可忽略",
        "  【编码规范化】= 原文PUA私用字符→标准Unicode，可忽略",
    ]
    if check_nested:
        lines.append("  【嵌套标注】= 标注符号内包含其他标注符号，必须修复")
    lines += ["", "─" * 50]

    total_real = total_punct = total_enc = total_nested = prob_chapters = 0

    for book, no, name, result, err, nested in results:
        head = f"{book} {no:03d}（{name}）"
        if err:
            lines += ["", f"=== {head} ===  ⚠ {err}"]
            continue
        wl_key = f"{book}/{no:03d}"
        wl_entries = (whitelist.get(wl_key, [])
                      + whitelist.get(f"{no:03d}", []))
        real_diffs = result["real"]
        if wl_entries:
            whitelisted = [d for d in real_diffs if _is_whitelisted(d, wl_entries)]
            real_diffs = [d for d in real_diffs if not _is_whitelisted(d, wl_entries)]
            n_wl = len(whitelisted)
        else:
            n_wl = 0
        nr, np_, ne = len(real_diffs), result["punct_count"], result["encoding_count"]
        nn = len(nested) if nested else 0
        total_real += nr
        total_punct += np_
        total_enc += ne
        total_nested += nn
        if nr or nn:
            prob_chapters += 1
        if nr == 0 and nn == 0 and not show_all:
            continue

        wl_note = f"  校勘:{n_wl}" if n_wl else ""
        nest_note = f"  嵌套:{nn}" if check_nested else ""
        lines += ["", f"=== {head} ===  实质:{nr}  标点:{np_}  编码:{ne}{wl_note}{nest_note}"]

        if nr:
            lines.append(f"  ■ 实质差异 {nr} 处：")
            for i, d in enumerate(real_diffs, 1):
                lines.append(fmt_diff(d, i))
        if nn:
            lines.append(f"  ■ 嵌套标注 {nn} 处：")
            for i, n in enumerate(nested, 1):
                type_label = "名词嵌套" if n["type"] == "nested_noun" else "动词嵌套"
                lines.append(f"  [{i}] {type_label} (行{n['line']})")
                lines.append(f"      标注: {repr(n['match'])}")
                lines.append(f"      上下文: {n['context']}")
        lines.append("")

    lines += [
        "─" * 50,
        "汇总:",
        f"  检查回数    : {len(results)} 回",
        f"  有实质差异  : {prob_chapters} 回，共 {total_real} 处  ← 需要修复",
        f"  标点规范化  : {total_punct} 处  ← 可忽略",
        f"  编码规范化  : {total_enc} 处  ← 可忽略",
    ]
    if check_nested:
        lines.append(f"  嵌套标注    : {total_nested} 处  ← 需要修复")
    lines += [
        "",
        "差异类型说明:",
        "  插入（标注多字）— 标注时擅自加字，应删除多余字符",
        "  删除（标注少字）— 标注时丢失字符，应补回",
        "  替换            — 字符被改写，需核对是字形变体还是错误",
        "  （--norm 尚未对武侠底本重审，替换类差异先按实质差异处置）",
    ]

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已保存: {out}")
    if check_nested:
        print(f"汇总: {prob_chapters}/{len(results)} 回有问题，"
              f"实质差异 {total_real} 处，嵌套标注 {total_nested} 处")
    else:
        print(f"汇总: {prob_chapters}/{len(results)} 回有实质差异，共 {total_real} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
