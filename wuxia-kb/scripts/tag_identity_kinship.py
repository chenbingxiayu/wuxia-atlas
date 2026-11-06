#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 合并移植 shiji-kb/scripts/tag_identity_words.py + tag_kinship_words.py（2026-11-04，C17）。
# 改动：
#   1. 两套内联规则 dict（IDENTITY_RULES / KIN_RULES）改为**武侠外置词表**：
#      wordlists/identity.json（身份 # / 职衔 ;，人工源 identity_source.md）+
#      wordlists/kinship.json（亲属称谓，人工源 kinship_source.md），经 masker 消费。
#   2. prefix/suffix 黑名单机制保留并升级：逐词 (前缀正则, 后缀正则) 规则表 +
#      专名前缀规则（太后/皇后/太子/王爷式：前接专名汉字即跳过，功能字/序数字白名单）
#      + 后接表字/人名规则（太子常洛式：后紧接已登记人物名即跳过，人名集取
#      registry/entities.json 的 @ 类 canonical+aliases）。
#   3. 已标注保护改用 symbols.TOKEN_RE（掩码等长占位）；围栏块与回目行跳过；
#      TSV「位置」= 原文偏移（含标记，line_start+行内偏移，docs/46 §二-5 统一口径）。
#   4. kinship 按 SKILL_03a D1 硬前置：纯亲属词默认不产出建议，仅当左侧有明确指称对象
#      标记（的/之/其 领属结构、紧邻**人物令牌**〖@…〗、第一二人称领属）时才建议；
#      谦辞/自称、师承关系称谓、纯礼貌称呼、描述/评价代称一律不产出（NEVER_TAG 兜底）。
#   5. 只出**建议 TSV**，默认不写 tagged；--apply 可选（备份 + 剥标还原断言 + 回滚）。
#      TSV 前 8 列与 apply_annotation_patches.load_tsv 契约兼容，第 9-11 列
#      （词表来源/词表档位/证据）为复核扩展列，load_tsv 忽略。
#
# 类型裁定：; 职衔（可履任的朝廷与江湖建制职位）；# 身份（职业类别/处境身份）。
# kinship 条目按语料既有先例（〖#哥哥〗〖#妻子〗）沿用 # 身份码，tier 全 watch，待人工裁定。
#
# 用法：
#   python scripts/tag_identity_kinship.py --book 白发魔女传 --chapter 001
#   python scripts/tag_identity_kinship.py --all
#   python scripts/tag_identity_kinship.py --all --dry-run
#   python scripts/tag_identity_kinship.py --all --types identity
#   python scripts/tag_identity_kinship.py --all --types 职衔

import argparse
import io
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols
import masker

# 身份表 type 码 → 建议 TSV 中文类型名（apply_annotation_patches.TYPE_NAME_TO_CODE 的键）
CODE_TO_TYPE_NAME = {"#": "身份", ";": "职衔"}
TYPE_ALIASES = {
    "身份": ("code", "#"), "#": ("code", "#"),
    "职衔": ("code", ";"), ";": ("code", ";"),
    "identity": ("table", "identity"), "kinship": ("table", "kinship"),
}
TSV_HEADER = ("章节\t全名\t词\t位置\t框架类型\t匹配模式\t上下文\t实体类型"
              "\t词表来源\t词表档位\t证据\n")
PLACEHOLDER = "\uFFFD"
TAGGED_FILE_RE = re.compile(r"^(\d{1,3})\.tagged\.md$")

# ── 硬负规则（SKILL_01g D1 / §8.4 负规则二；SKILL_03a D1）──────────────────
# ① 谦辞·自称：说话人自称，不标（D1「纯礼貌、关系称呼不标」）
# ② 师承关系称谓：无姓名纯关系词不标（03a few-shot「这样一位好徒弟」未标）
# ③ 纯礼貌称呼 / ④ 描述评价代称 / ⑤ 阵式战术角色
NEVER_TAG = set("""
家父 家母 家兄 舍弟 犬子 小女 拙荆 贱内 内人 愚兄 小弟 晚生 晚辈 卑职 小的 奴才 在下
贫道 贫僧 微臣 臣 俺 弟子 徒弟 门人 门徒 徒儿 传人 师父 师兄 师弟 师姐 师妹 师叔 师伯
师祖 前辈 先生 小姐 老伯 贤弟 后辈 小可 不才 末将 手下败将
汉子 少年 少女 美妇人 女侠 英雄 豪杰 那汉子 那姑娘 蒙面人 老汉 老者 公子哥
先锋 后卫 主帅 大丈夫 公公 老子 夫人小姐
家人 保镖 领袖 杀手
""".split())
# 谦辞前缀（kinship 边界：家父/舍弟式自称即使词形在表内也不标）
QIANCI_PREFIX = set("家舍拙贱犬内寒愚小贱")

# 逐词 (前缀正则, 后缀正则)；None=不限。保留 shiji 的 prefix/suffix 机制。
WORD_RULES = {
    # 掌门作动词用（「回去掌门」「师叔掌门」）时不是职衔实体
    "掌门": (r"[去回作当继接叔伯]", None),
    "掌门人": (r"[去回作当继接叔伯]", None),
    # 手下留情/手下败将 的「手下」不是人（下留情＝施恩），身份义才标
    "手下": (None, r"[留败]"),
    # 施展杀手/痛下杀手/杀手绝招 的「杀手」是致命招数，不是职业刺客（词表已不收，
    # 此处保留兜底）
    "杀手": (r"[施下出猛用动展]", r"[绝]"),
    # 叛逆 作「谋反/叛逆之名/叛逆实据」时是罪名，不是处境身份；搜捕叛逆/擒获叛逆 才是身份
    "叛逆": (r"[谋]", r"[之实]"),
    # 指挥作动词（「玉罗刹指挥，」「指挥女兵」）时不是职衔；职衔义才标
    "指挥": (None, r"[女兵人众军盗马，。！？、；：]"),
    # 「将军柏」是古柏名，不是职衔
    "将军": (r"[大]", r"[柏]"),
    # 经略作动词（「经略辽东」）时不是职衔
    "经略": (None, r"[辽边]"),
    # 副将军＝副将（称谓），不拆
    "副将": (None, r"[军]"),
    # 祖师爷 的「师爷」不是幕僚
    "师爷": (r"[祖]", None),
    # 大总管 是称谓整体，不拆；九千岁总管/连大总管 的「总管」才是职衔
    "总管": (r"[大]", None),
    # 俘虏作动词（「俘虏了十多个」）时不是身份
    "俘虏": (None, r"[了]"),
    # 老头子/糟老头子 是老者，不是匪首；强盗头子 才是身份
    "头子": (r"[老糟]", None),
    # 大将之材/心腹大将 才是身份
    "大将": (None, r"[军]"),
    # 店小二 的整体是身份，不拆「小二」
    "小二": (r"[店]", None),
    # 太子少保/太子太保 是另一职衔（本表已单列太子少保，最长优先会先吃掉长词）
    "太子": (None, r"[少太]"),
    "皇太子": (None, r"[少太]"),
    # 老镖头/副镖头/总镖头 已单列，避免把前缀词尾当独立词重复命中
    "镖头": (r"[老副总]", None),
    "镖师": (r"[老副总]", None),
    "武师": (r"[老副总]", None),
}
# 皇室位号：前接专名汉字（吕太后/郑贵妃式）跳过；功能字/序数字白名单不视为专名
ROYAL_TITLES = ("皇太后", "皇后", "公主", "太子", "王爷", "藩王", "皇子")
ROYAL_PREFIX_WHITELIST = set(
    "把将让立为封册是的这那个位与和及等诸其此一二三四五六七八九十两几众诸大小老新"
    "朝当在给对向从被由见请问怕知说叫想道")

PERSON_NAMES = []          # 已登记人物名（后接人名不标）

# kinship 领属/指称对象标记（SKILL_03a D1 硬前置：无明确指称对象不产出建议）
REFERENT_RE = re.compile(r"(的|之|其)(?:〗)?$")
PRONOUN_RE = re.compile(r"(我|你|他|她|它|俺|咱|自己|自家|人家|此人|那人|这人)(?:的|之)?$")


# ── 资源加载 ────────────────────────────────────────────────────────────────
def load_table(name: str):
    """读编译后词表 → (matcher, meta)。meta: surface → {canonical,type,tier,conf,evidence,source}"""
    wl_path = config.DIR_WORDLISTS / f"{name}.json"
    if not wl_path.exists():
        print(f"词表不存在：{wl_path}\n先跑 python scripts/wordlist_compiler.py "
              f"--name {name}（禁 --all）")
        sys.exit(1)
    matcher = masker.load_wordlist(wl_path, field="surface")
    data = json.loads(wl_path.read_text(encoding="utf-8"))
    # 顶层兼容：D09 产物为 {"items": [...]}，也接受裸 list（与 masker/wordlist_compiler 一致）
    items = data if isinstance(data, list) else data.get("items", [])
    meta = {}
    for it in items:
        surface = it.get("surface", "").strip()
        if not surface:
            continue
        meta[surface] = {
            "canonical": it.get("canonical") or surface,
            "type": it.get("type"),
            "tier": it.get("tier", "watch"),
            "conf": it.get("conf", "weak"),
            "evidence": " ".join(it.get("evidence") or []),
            "source": name,
        }
    return matcher, meta


def load_person_names():
    """registry/entities.json 的 @ 类 canonical+aliases → 人名集（后接人名不标）。"""
    p = config.DIR_REGISTRY / "entities.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    names = set()
    for e in data.get("entities", []):
        if e.get("type") != "@":
            continue
        for n in [e.get("canonical")] + list(e.get("aliases") or []):
            if n and len(n) >= 2:
                names.add(n)
    return sorted(names, key=len, reverse=True)


def merge_tables(*tables):
    """合并多表 matcher + meta（同 surface 以前表优先；本脚本 identity 优先于 kinship）。"""
    index, max_len, seen = {}, 0, set()
    meta = {}
    for m, mp in tables:
        for s, it in mp.items():
            meta.setdefault(s, it)
        for first, words in m["index"].items():
            bucket = index.setdefault(first, [])
            for w in words:
                if w in seen:
                    continue
                seen.add(w)
                bucket.append(w)
                max_len = max(max_len, len(w))
    for first in index:
        index[first].sort(key=len, reverse=True)
    return {"index": index, "max_len": max_len, "count": len(seen)}, meta


# ── 行级工具 ────────────────────────────────────────────────────────────────
def fence_line_set(lines):
    fenced, in_fence = set(), False
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
    spans = [(m.start(), m.end()) for m in symbols.TOKEN_RE.finditer(line)]
    if not spans:
        return line, spans
    chars = list(line)
    for a, b in spans:
        for j in range(a, b):
            chars[j] = PLACEHOLDER
    return "".join(chars), spans


def is_skippable_line(line: str):
    s = line.lstrip()
    return (not s.strip()) or s.startswith("#")


def context_of(line: str, pos: int, word: str, width: int = 10):
    a = max(0, pos - width)
    b = min(len(line), pos + len(word) + width)
    return line[a:b].replace("\n", "↵")


# ── 负规则判定 ──────────────────────────────────────────────────────────────
def followed_by_person_name(line: str, end: int) -> bool:
    """后接表字/人名不标（太子常洛式）。人名集 = registry @ 类 canonical+aliases。"""
    for name in PERSON_NAMES:
        if line.startswith(name, end):
            return True
    return False


def identity_blocked(line: str, pos: int, word: str) -> bool:
    """身份/职衔词的逐词负规则。pos 为原文（含令牌）偏移。"""
    if word in NEVER_TAG:
        return True
    pre, suf = WORD_RULES.get(word, (None, None))
    prev = line[pos - 1] if pos > 0 else ""
    nxt = line[pos + len(word)] if pos + len(word) < len(line) else ""
    # ① 专名前缀（吕太后式）：前接专名汉字即跳过；功能字/序数字白名单不视为专名
    if word in ROYAL_TITLES and prev and re.match(r"[\u4e00-\u9fff]", prev) \
            and prev not in ROYAL_PREFIX_WHITELIST:
        return True
    # ② 逐词前缀/后缀黑名单
    if pre and prev and re.match(pre, prev):
        return True
    if suf and nxt and re.match(suf, nxt):
        return True
    # ③ 后接表字/人名不标（太子常洛式）
    if followed_by_person_name(line, pos + len(word)):
        return True
    return False


def kinship_blocked(line: str, pos: int, word: str) -> bool:
    """kinship 按 03a D1：必须有明确指称对象标记，否则不产出建议。

    指称对象来源：① 领属结构「的/之/其」；② 第一二人称领属；③ 左邻**人物令牌**
    〖@…〗（docs/46 §二-6：必须解析令牌类型，仅 `@` 人物令牌放行；〖#…〗/〖☆…〗
    等其他类型令牌不作为亲属词的指称对象）。
    """
    if word in NEVER_TAG:
        return True
    if pos > 0 and line[pos - 1] in QIANCI_PREFIX:      # 家父/舍弟式谦辞前缀
        return True
    left = line[max(0, pos - 12):pos]
    if REFERENT_RE.search(left) or PRONOUN_RE.search(left):
        return False
    # 紧邻令牌：仅 〖@…〗 人物令牌视为明确指称对象
    if pos > 0 and line[pos - 1] == "〗":
        last_tok = None
        for m in symbols.TOKEN_RE.finditer(line):
            if m.end() == pos:
                last_tok = m
                break
        if last_tok is not None:
            layer, code = symbols.parse_token(last_tok.group(0))[:2]
            if layer == "entity" and code == "@":
                return False
    return True


# ── 扫描 ────────────────────────────────────────────────────────────────────
def scan_chapter(fpath: Path, matcher, meta, kind_filter=None, min_freq=1):
    """扫描单回，返回建议列表。

    - 已标注区间：令牌掩码保护（masked 与原文等长），不重复标注；
    - 最长优先、不重叠；围栏块 / 回目行 / 标题行跳过；
    - 位置 = **原文偏移（含标记）**：`line_start + 行内偏移`，TSV `位置` 可直接用
      `原文[pos:pos+len(word)] == word` 断言（docs/46 §二-5 统一坐标口径）。
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
            if len(word) <= 1:
                continue
            item = meta.get(word)
            if item is None:
                continue
            code = item["type"]
            if kind_filter:
                allow = False
                for kind, val in kind_filter:
                    if kind == "code" and code == val:
                        allow = True
                    elif kind == "table" and item["source"] == val:
                        allow = True
                if not allow:
                    continue
            if item["source"] == "kinship":
                if kinship_blocked(line, pos, word):
                    continue
            else:
                if identity_blocked(line, pos, word):
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
                "source": item["source"],
                "tier": item["tier"],
                "evidence": item["evidence"],
            })
        line_start += len(line) + 1

    freq = Counter(s["word"] for s in suggestions)
    suggestions = [s for s in suggestions if freq[s["word"]] >= min_freq]
    suggestions.sort(key=lambda s: s["pos"])
    return suggestions


# ── 输出 ────────────────────────────────────────────────────────────────────
def tsv_chapter_field(book: str, stem: str, multi_book: bool):
    return f"{book}/{stem}" if multi_book else stem


def write_tsv(out_path: Path, suggestions, multi_book, book):
    lines = [TSV_HEADER]
    for s in suggestions:
        chapter = tsv_chapter_field(book, s["chapter"], multi_book)
        lines.append("\t".join([
            chapter, s["full_name"], s["word"], str(s["pos"]),
            s["frame_type"], s["pattern"], s["context"],
            s["entity_type"], s["source"], s["tier"], s["evidence"],
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
    after = symbols.strip_markup(fpath.read_text(encoding="utf-8"))
    if after != before:
        shutil.copy2(bak, fpath)
        print(f"  [FATAL] 剥标还原断言失败，已回滚：{fpath}")
        return False
    print(f"  [apply] {fpath.name}: 插入 {res['applied']} 处（备份 {bak.name}，"
          f"剥标断言 PASS）")
    return True


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
        description="身份/职衔 + 亲属称谓建议标注（外置词表 identity+kinship；只出建议 TSV，"
                    "默认不写 tagged）")
    ap.add_argument("--book", default=None, help="只处理指定书（缺省全库）")
    ap.add_argument("--chapter", default=None, help="单回编号（如 001）")
    ap.add_argument("--all", action="store_true", help="全库全部回（与 --book/--chapter 互斥）")
    ap.add_argument("--types", nargs="+", default=None,
                    help="identity/kinship/身份/职衔（或实体码 # ;）")
    ap.add_argument("--min-freq", type=int, default=1,
                    help="章内最少出现次数（默认 1）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只统计不落盘（默认会写建议 TSV，但仍不写 tagged）")
    ap.add_argument("--out", default=None,
                    help=f"建议 TSV 输出目录（缺省 {config.DIR_REGISTRY / 'patches'}）")
    ap.add_argument("--apply", action="store_true",
                    help="[可选] 应用建议到 tagged（写前备份 + 剥标断言）；默认关闭")
    args = ap.parse_args()

    if args.all and (args.book or args.chapter):
        ap.error("--all 与 --book/--chapter 互斥")

    kind_filter = None
    if args.types:
        kind_filter = []
        for t in args.types:
            v = TYPE_ALIASES.get(t)
            if v is None:
                ap.error(f"未知类型「{t}」；可用：{' '.join(sorted(TYPE_ALIASES))}")
            kind_filter.append(v)

    m_id, meta_id = load_table("identity")
    m_kin, meta_kin = load_table("kinship")
    matcher, meta = merge_tables((m_id, meta_id), (m_kin, meta_kin))
    global PERSON_NAMES
    PERSON_NAMES = load_person_names()
    print(f"词表 identity {len(meta_id)} 条 + kinship {len(meta_kin)} 条 "
          f"→ 合并 {matcher['count']} 条；人名否定集 {len(PERSON_NAMES)} 个")
    print(f"类型分布：{dict(Counter(it['type'] for it in meta.values()))}；"
          f"NEVER_TAG 兜底 {len(NEVER_TAG)} 条")

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
    by_source = Counter()
    by_word = Counter()
    for f in files:
        sug = scan_chapter(f, matcher, meta, kind_filter, args.min_freq)
        if not sug:
            continue
        n_files += 1
        total += len(sug)
        by_type.update(s["entity_type"] for s in sug)
        by_source.update(s["source"] for s in sug)
        by_word.update(s["word"] for s in sug)
        if not args.dry_run:
            out = out_dir / f"{f.name.replace('.tagged.md', '')}_identity_kinship.tsv"
            write_tsv(out, sug, multi_book, f.parent.name)
            print(f"  {f.parent.name}/{f.name}: {len(sug)} 条建议 → {out.name}")
        else:
            print(f"  {f.parent.name}/{f.name}: {len(sug)} 条建议")

    print(f"\n{'=' * 60}")
    print(f"合计 {total} 条建议，{len(by_word)} 个词种，{n_files} 回有命中")
    if by_type:
        print(f"类型分布：{dict(by_type)}；来源：{dict(by_source)}")
    if by_word:
        print("Top 20 高频词：")
        for w, n in by_word.most_common(20):
            print(f"  {w}: {n}")

    if args.apply:
        if args.dry_run:
            print("--apply 与 --dry-run 互斥，跳过应用")
            return 0
        print("\n[--apply] 开始应用建议（写前备份 + 剥标断言）")
        ok = True
        for f in files:
            out = out_dir / f"{f.name.replace('.tagged.md', '')}_identity_kinship.tsv"
            if out.exists():
                ok = apply_tsv(out, f) and ok
        print("应用完成" if ok else "应用失败（见上）")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
