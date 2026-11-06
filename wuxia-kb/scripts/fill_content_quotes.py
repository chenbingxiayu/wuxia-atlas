#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_content_quotes.py —— content/ 页面引文填充（W7 硬门前置）

任务（task-72）：对 content/ 1,526 页（367 person + 1,159 四类）从对应 tagged/底本
抽取 1-2 条**直接引文**，写入页 frontmatter `quotes[]`（{text, loc, source}），并把
`quote_status: pending` 改为 `filled`；引文交 W7（verify_quotes.py）核验。

引文纪律（本脚本内置断言）：
  ① 精确子串：text 必须在对应回底本原文中**逐字存在**（不做近似、不改标点）；
  ② ≤60 字/条（L0 版权档）；每页 1-2 条、页内不重复；
  ③ 只取**叙事事实句**：含目标实体 + 至少一个动词令牌，且非围栏韵文、非对白主体、
     非「未明示」占位；
  ④ loc 用 W7 同款机锚 `{书}#pn-r{回}.{段}`；source 指底本章回（corpus:…）；
  ⑤ 只读 tagged/底本；只写 content 页 frontmatter 与 logs/qa（不写 site/registry）。

用法：
  python -X utf8 scripts/fill_content_quotes.py                 # dry-run（默认，不写页）
  python -X utf8 scripts/fill_content_quotes.py --apply         # 逐页备份 + 写 quotes[]
  python -X utf8 scripts/fill_content_quotes.py --selftest      # 合成语料自检（不碰真实 content）
  可选：--limit N（只处理前 N 页，便于抽查）/ --types person,art（限定页型）
        --report-dir DIR（报告目录，缺省 logs/qa）

退出码：0 正常；1 自检失败或 --apply 后断言失败；2 参数/环境错误。
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

# W7 引擎（只 import，不执行 main）：抽样核验复用其 CorpusIndex/normalize/verify_segment
try:
    import verify_quotes as w7  # noqa: E402
except Exception:  # pragma: no cover - 兜底：无 W7 时退化为本地精确核验
    w7 = None

# ==================== 常量 ====================
SCHEMA = "content-quotes-v0.1"
MAX_QUOTE_LEN = 60          # L0 版权档：单条引文 ≤60 字
MIN_QUOTE_LEN = 10          # 过短无叙事价值
MAX_PER_PAGE = 2            # 每页 1-2 条
CONTENT_TYPES = ("person", "faction", "art", "artifact", "manual")
PLACEHOLDERS = ("未明示", "待补", "待定", "（略）", "……略")
# 目标名候选：canonical + 卡别名；过滤占位/纯符号
NAME_MIN_LEN = 2
NAME_MAX_LEN = 12

FRONT_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
TOKEN_RE = re.compile(r"〖(.)(.+?)〗|⟦(.)(.+?)⟧")
PARA_RE = re.compile(r"^\[(\d+)\]\s?(.*)$")
PN_REF_RE = re.compile(r"([A-Za-z0-9\u4e00-\u9fff]+)#pn-r(\d+)\.(\d+)")
SENT_RE = re.compile(r"[^。！？]*[。！？]+|[^。！？]+$")
QUOTE_PAIR_RE = re.compile(r"“([^”]*)”")


# ==================== 基础工具 ====================
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256_12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def split_frontmatter(text: str):
    """→ (frontmatter_text, body_text)；无 frontmatter 返回 (None, text)。"""
    m = FRONT_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def fm_scalar(fm: str, key: str, default: str = "") -> str:
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", fm, re.M)
    if not m:
        return default
    v = m.group(1).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def fm_block_list(fm: str, key: str):
    """读取 `key:` 下的 `  - item` 块列表（不处理嵌套）。"""
    lines = fm.split("\n")
    out, active = [], False
    for ln in lines:
        if re.match(rf"^{re.escape(key)}:\s*$", ln):
            active = True
            continue
        if active:
            m = re.match(r"^\s+-\s+(.*)$", ln)
            if m:
                out.append(m.group(1).strip().strip("\"'"))
            elif ln.strip() and not ln.startswith((" ", "\t")):
                break
    return out


def yaml_scalar(value: str) -> str:
    """统一输出 YAML 双引号标量（JSON 转义在 YAML 中合法）。"""
    return json.dumps(value, ensure_ascii=False)


def strip_with_spans(raw: str):
    """标注文本 → (剥标文本, 实体 span[(s,e,type)], 动词 span[(s,e,type)])。"""
    out, ents, verbs, pos, cur = [], [], [], 0, 0
    for m in TOKEN_RE.finditer(raw):
        for ch in raw[pos:m.start()]:
            out.append(ch)
            cur += 1
        if m.group(1) is not None:                     # 〖type 显示串|canonical〗
            typ, inner = m.group(1), m.group(2)
            disp = inner.split("|", 1)[0]
            start = cur
            for ch in disp:
                out.append(ch)
                cur += 1
            ents.append((start, cur, typ))
        else:                                          # ⟦type 显示串|canonical⟧
            typ, inner = m.group(3), m.group(4)
            disp = inner.split("|", 1)[0]
            start = cur
            for ch in disp:
                out.append(ch)
                cur += 1
            verbs.append((start, cur, typ))
        pos = m.end()
    for ch in raw[pos:]:
        out.append(ch)
        cur += 1
    return "".join(out), ents, verbs


def iter_sentences(text: str):
    """→ [(start, end, sentence)]（按。！？切分，保留句末标点）。"""
    out = []
    for m in SENT_RE.finditer(text):
        s, e = m.start(), m.end()
        sent = text[s:e]
        if sent.strip():
            out.append((s, e, sent))
    return out


def _occurrences(text: str, names):
    """→ [(pos, len, name)]；长名优先、去重叠（同一位置只留最长名）。"""
    occ, taken = [], []
    for n in names:
        start = 0
        while True:
            i = text.find(n, start)
            if i < 0:
                break
            if not any(a < i + len(n) and i < b for a, b in taken):
                occ.append((i, len(n), n))
                taken.append((i, i + len(n)))
            start = i + 1
    occ.sort()
    return occ


def _clause_span(text: str, pos: int, nlen: int):
    """名称所在分句 [s,e)：向前/后找最近的 ，；：。！？ 或换行边界。"""
    left = max(text.rfind(ch, 0, pos) for ch in "，；：。！？\n")
    s = left + 1 if left >= 0 else 0
    rights = [text.find(ch, pos + nlen) for ch in "，；：。！？\n"]
    rights = [r for r in rights if r >= 0]
    e = min(rights) + 1 if rights else len(text)
    return s, e


def _window_span(text: str, pos: int, nlen: int, max_len: int):
    """≤max_len 的窗口：以名称为中心，尽量在标点处起止（保持可读）。"""
    if len(text) <= max_len:
        return 0, len(text)
    half = max(1, (max_len - nlen) // 2)
    s = max(0, pos - half)
    e = min(len(text), s + max_len)
    s = max(0, e - max_len)
    for delta in range(0, 12):
        cand = s + delta
        if cand < pos and text[cand - 1] in "，；：。！？\n":
            s = cand
            break
    for delta in range(0, 12):
        cand = e - delta
        if cand > pos + nlen and text[cand - 1] in "，。！？；：":
            e = cand
            break
    e = min(e, s + max_len)
    return s, e


def _trim_span(text: str, s: int, e: int):
    """引文边界清理：去掉首尾标点/引号/空白，避免以 ，。；：” 起止。"""
    lead = "”’，。；：！？、）】》\"' \t\n"
    tail = "“’（【《\"' \t\n，、；："
    while s < e and text[s] in lead:
        s += 1
    while e > s and text[e - 1] in tail:
        e -= 1
    return s, e


def _inside_quote(s: int, e: int, quote_spans):
    """候选是否落在对白引号内（对白不算叙事事实句）。"""
    for s2, e2 in quote_spans:
        if s2 <= s and e <= e2:
            return True
        overlap = min(e, e2) - max(s, s2)
        if overlap > 0 and overlap / max(1, e - s) > 0.5:
            return True
    return False


# 对白/强调引号判定：短引号（≤10 字、无句读、前后无说话动词）= 招式名/强调引号，
# 视为叙事文本；长引号或带说话动词 = 对白，不作叙事事实句。
SPEECH_VERBS = "道说问答喊叫笑喝曰骂嚷叹吟唱念嘱吩咐告诉"
SPEECH_AFTER_RE = re.compile(r"(道|说|问|答|喊|叫|笑|喝|曰)")
ALLOWED_FENCE = {"回末", "书信", "告示", "说书"}   # 叙事性围栏可取；词/诗/歌/对联/回末对/口诀仍禁
PREDICATE_CHARS = set("是有在为把被将得了着过道说问答笑喝叫想看听知觉悟能可会要须应")
NAME_VARIANT_PAIRS = [("术", "法"), ("法", "术"), ("功夫", "功"), ("功", "功夫")]


def is_speech_span(text: str, s: int, e: int) -> bool:
    """引号片段是否为对白（而非招式名/强调引号）。

    判据（任一）：内文 >10 字 / 内含句读 / 引号前紧贴说话动词（可带冒号）/
    引号后紧跟「道/说/问…」。
    """
    inner = text[s + 1:e - 1]
    if len(inner) > 10:
        return True
    if re.search(r"[？！。，、；：]", inner):
        return True
    if re.search(r"(道|说|问|答|喊|叫|笑|喝|曰|骂|嚷|叹|吟|唱|念)[：:]?$",
                 text[max(0, s - 3):s]):
        return True
    if re.match(r"^[”」]?(道|说|问|答|喊|叫|笑|喝|曰)", text[e:e + 4]):
        return True
    return False


def speech_spans(text: str):
    return [(m.start(), m.end()) for m in QUOTE_PAIR_RE.finditer(text)
            if is_speech_span(text, m.start(), m.end())]


def normalize_text(text: str) -> str:
    """NFKC + 只留汉字/字母/数字（与 W7 normalize 同口径，用于底本回查）。"""
    out = []
    for ch in unicodedata.normalize("NFKC", text):
        if "\u4e00" <= ch <= "\u9fff" or ch.isalnum():
            out.append(ch.lower())
    return "".join(out)


def _norm_with_map(raw: str):
    """原文 → (归一化串, 归一化位置→原文下标 映射)。"""
    out, idx = [], []
    for i, ch in enumerate(raw):
        for c in unicodedata.normalize("NFKC", ch):
            if "\u4e00" <= c <= "\u9fff" or c.isalnum():
                out.append(c.lower())
                idx.append(i)
    return "".join(out), idx


def _has_predicate(q: str) -> bool:
    return any(ch in PREDICATE_CHARS for ch in q)


def _variants(name: str, kind: str):
    """通名/俗称变体（保守）：术↔法、功夫↔功；仅武功页使用。"""
    out = []
    if kind == "art":
        for a, b in NAME_VARIANT_PAIRS:
            if a in name:
                v = name.replace(a, b, 1)
                if v != name and v not in out:
                    out.append(v)
    return out


def dialogue_ratio(sent: str) -> float:
    if not sent:
        return 0.0
    quoted = sum(len(m.group(1)) for m in QUOTE_PAIR_RE.finditer(sent))
    return quoted / max(1, len(sent))


def is_placeholder(sent: str) -> bool:
    return any(p in sent for p in PLACEHOLDERS)


def load_cards(path: Path):
    """SKU 卡 → {stable_id: {canonical, aliases[]}}；缺失返回 {}。"""
    if not path or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for card in data.get("cards", []):
        meta = card.get("meta") or {}
        sid = meta.get("stable_id")
        if not sid:
            continue
        name = card.get("name")
        canonical = name.get("canonical") if isinstance(name, dict) else name
        aliases = []
        for a in card.get("aliases") or []:
            surface = a.get("surface") if isinstance(a, dict) else a
            if surface:
                aliases.append(str(surface))
        out[sid] = {"canonical": canonical or "", "aliases": aliases}
    return out


def load_entity_aliases(registry_dir: Path):
    """registry/entities.json → {entity_id: [canonical + aliases + contextual]}。"""
    out = {}
    p = Path(registry_dir) / "entities.json"
    if not p.exists():
        return out
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return out
    for e in data.get("entities", []):
        eid = e.get("id")
        if not eid:
            continue
        vals = [e.get("canonical") or ""] + list(e.get("aliases") or []) \
            + list(e.get("contextual") or [])
        out[eid] = [v for v in vals if v]
    return out


def load_work_ids(registry_dir: Path):
    """registry/time/<书>.json 的 work_id → {book: work_id} + {work_id: book}。"""
    book2wid, wid2book = {}, {}
    time_dir = Path(registry_dir) / "time"
    if time_dir.exists():
        for p in sorted(time_dir.glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            wid = d.get("work_id")
            book = d.get("book") or p.stem
            if wid:
                book2wid[book] = wid
                wid2book[wid] = book
    return book2wid, wid2book


# ==================== 页面模型 ====================
class Page:
    __slots__ = ("path", "rel", "kind", "fm", "body", "text", "sha", "canonical",
                 "display", "entity_ref", "slug", "card_ref", "book_scope", "pn_refs")

    def __init__(self, path: Path, rel: str, kind: str, text: str):
        self.path = path
        self.rel = rel
        self.kind = kind
        self.text = text
        self.sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        fm, body = split_frontmatter(text)
        self.fm, self.body = fm, body
        self.canonical = fm_scalar(fm or "", "canonical")
        self.display = fm_scalar(fm or "", "display")
        self.entity_ref = fm_scalar(fm or "", "entity_ref")
        self.slug = fm_scalar(fm or "", "slug")
        self.card_ref = fm_scalar(fm or "", "card_ref")
        self.book_scope = fm_block_list(fm or "", "book_scope")
        self.pn_refs = []
        for m in PN_REF_RE.finditer(fm or ""):
            self.pn_refs.append((m.group(1), int(m.group(2)), int(m.group(3))))


# ==================== 抽取器 ====================
class QuoteFiller:
    def __init__(self, *, content_dir: Path, corpus_root: Path, tagged_dir: Path,
                 registry_dir: Path, cards_path: Path | None = None,
                 backup_dir: Path | None = None, work_ids: tuple | None = None,
                 allow_dialogue_facts: bool = False, allow_label_expansion: bool = False):
        self.content_dir = Path(content_dir)
        self.corpus_root = Path(corpus_root)
        self.tagged_dir = Path(tagged_dir)
        self.registry_dir = Path(registry_dir)
        self.backup_dir = Path(backup_dir) if backup_dir else None
        self.cards = load_cards(cards_path) if cards_path else {}
        self.entity_alias = load_entity_aliases(self.registry_dir)
        self.book2wid, self.wid2book = work_ids if work_ids else load_work_ids(self.registry_dir)
        self._tagged_cache = {}
        self._corpus_cache = {}
        self._norm_cache = {}
        # 可选兜底：允许「对白内的事实陈述句」入 quotes（默认关；来源标注为对白事实句）
        self.allow_dialogue_facts = allow_dialogue_facts
        # task-82 收尾：叙述标签扩窗（仅对白内、且所在句为陈述句；扩窗取 ≤60 字事实分句）
        self.allow_label_expansion = allow_label_expansion

    # ---- 缓存加载 ----
    def load_tagged(self, book: str, no: int):
        """tagged 章 → [{anchor,text,ents,verbs,in_fence}]；无文件返回 []。"""
        key = (book, no)
        if key in self._tagged_cache:
            return self._tagged_cache[key]
        p = self.tagged_dir / book / f"{no:03d}.tagged.md"
        paras = []
        if p.exists():
            fence = None
            for raw in p.read_text(encoding="utf-8").split("\n"):
                s = raw.rstrip()
                if not s.strip():
                    continue
                if s.startswith(":::"):
                    fence = None if s == ":::" else s[3:].strip()
                    continue
                if s.startswith("# [0]"):
                    continue
                m = PARA_RE.match(s)
                if m:
                    text, ents, verbs = strip_with_spans(m.group(2))
                    paras.append({"anchor": int(m.group(1)), "text": text,
                                  "ents": ents, "verbs": verbs,
                                  "fence": fence, "in_fence": fence is not None})
                elif paras:
                    # 续行（现仓 tagged 均为单行；保留兼容）
                    text, ents, verbs = strip_with_spans(s)
                    paras[-1]["text"] += "\n" + text
        self._tagged_cache[key] = paras
        return paras

    def load_corpus(self, book: str, no: int):
        """底本回原文（精确子串校验用）；找不到返回 None。"""
        key = (book, no)
        if key in self._corpus_cache:
            return self._corpus_cache[key]
        d = self.corpus_root / book
        raw = None
        if d.exists():
            for p in sorted(d.glob(f"{no:03d}*.txt")):
                raw = p.read_text(encoding="utf-8-sig")
                break
        self._corpus_cache[key] = raw
        return raw

    # ---- 页面遍历 ----
    def iter_pages(self, types=None, limit=None):
        types = tuple(types) if types else CONTENT_TYPES
        count = 0
        for kind in types:
            d = self.content_dir / kind
            if not d.exists():
                continue
            for p in sorted(d.glob("*.md")):
                if limit is not None and count >= limit:
                    return
                text = p.read_text(encoding="utf-8")
                yield Page(p, f"{kind}/{p.name}", kind, text)
                count += 1

    # ---- 名称候选 ----
    def names_for(self, page: Page):
        names = []
        card = self.cards.get(page.card_ref) or {}
        for n in [page.canonical, card.get("canonical")] + list(card.get("aliases") or []):
            if not n:
                continue
            n = str(n).strip()
            if not (NAME_MIN_LEN <= len(n) <= NAME_MAX_LEN):
                continue
            if any(p in n for p in PLACEHOLDERS):
                continue
            if n not in names:
                names.append(n)
        # display 层 + 实体登记层别名（registry/entities.json）
        extra = [page.display] + list(self.entity_alias.get(page.entity_ref, []))
        for n in extra:
            if not n:
                continue
            n = str(n).strip()
            if not (NAME_MIN_LEN <= len(n) <= NAME_MAX_LEN):
                continue
            if any(p in n for p in PLACEHOLDERS):
                continue
            if n not in names:
                names.append(n)
        # 人物/门派页正文「别名：A、B」兜底
        m = re.search(r"别名[:：]\s*(.+)", page.body or "")
        if m:
            for n in re.split(r"[、，,/]", m.group(1)):
                n = n.strip()
                if NAME_MIN_LEN <= len(n) <= NAME_MAX_LEN and n not in names \
                        and not any(p in n for p in PLACEHOLDERS):
                    names.append(n)
        if page.kind == "faction":
            stems = []
            for n in names:
                for suf in ("派", "帮", "会", "教", "门", "寺", "观", "山庄",
                            "镖局", "盟", "寨", "楼", "阁", "堂"):
                    if n.endswith(suf) and len(n) - len(suf) >= 2:
                        stems.append(n[: -len(suf)])
                        break
            for n in stems:
                if n not in names:
                    names.append(n)
        if page.kind == "art":
            for n in list(names):
                for v in _variants(n, page.kind):
                    if v not in names:
                        names.append(v)
        names.sort(key=len, reverse=True)
        return names

    def candidate_books(self, page: Page):
        books = []
        for wid, _ch, _pa in page.pn_refs:
            b = self.wid2book.get(wid)
            if b and b not in books:
                books.append(b)
        for b in page.book_scope:
            if b and b not in books:
                books.append(b)
        if not books and self.tagged_dir.exists():
            books = sorted(p.name for p in self.tagged_dir.iterdir() if p.is_dir())
        return books

    def candidate_chapters(self, page: Page, book: str):
        """回号顺序：PN 指针回优先，再按回号升序。"""
        pn_ch = [ch for wid, ch, _pa in page.pn_refs if self.wid2book.get(wid) == book]
        d = self.tagged_dir / book
        all_ch = []
        if d.exists():
            for p in sorted(d.glob("*.tagged.md")):
                m = re.match(r"^(\d+)\.tagged\.md$", p.name)
                if m:
                    all_ch.append(int(m.group(1)))
        ordered = []
        for ch in pn_ch + all_ch:
            if ch not in ordered:
                ordered.append(ch)
        return ordered

    # ---- 单页抽取 ----
    def extract(self, page: Page):
        """→ (quotes[], reason)；quotes 为空时 reason 说明原因。"""
        if page.fm is None:
            return [], "no_frontmatter"
        if re.search(r"^quotes:\s*$", page.fm, re.M) and \
                not re.search(r"^quotes:\s*\[\s*\]\s*$", page.fm, re.M):
            return [], "already_filled"
        names = self.names_for(page)
        if not names:
            return [], "no_name"
        books = self.candidate_books(page)
        if not books:
            return [], "no_book"
        pn_chapters = {}
        for wid, ch, _pa in page.pn_refs:
            b = self.wid2book.get(wid)
            if b:
                pn_chapters.setdefault(b, set()).add(ch)
        found = []      # (score, book, no, anchor, text)
        chapter_hits = collections.Counter()

        def scan(book_list):
            for book in book_list:
                for no in self.candidate_chapters(page, book):
                    corpus_raw = self.load_corpus(book, no)
                    if corpus_raw is None:
                        continue
                    bonus = 2 if no in pn_chapters.get(book, set()) else 0
                    for para in self.load_tagged(book, no):
                        fence = para.get("fence")
                        if fence is not None and fence not in ALLOWED_FENCE:
                            continue
                        text = para["text"]
                        if not text or is_placeholder(text):
                            continue
                        for score, qtext, src_tag in self._candidates_in_para(para, names, bonus):
                            exact = self._corpus_exact(book, no, corpus_raw, qtext, names)
                            if exact:
                                found.append((score, book, no, para["anchor"], exact, src_tag))
                                chapter_hits[(book, no)] += 1
                    # 早停：已覆盖 2 回且候选充足即收手（质量已由 score 排序保证）
                    if len(chapter_hits) >= 2 and sum(chapter_hits.values()) >= 10:
                        break
                if len(chapter_hits) >= 3 and sum(chapter_hits.values()) >= 14:
                    break

        scan(books)
        if not found and self.tagged_dir.exists():
            # 回退：book_scope 未覆盖全部点亮书时，全库再扫一遍
            all_books = sorted(p.name for p in self.tagged_dir.iterdir() if p.is_dir())
            extra = [b for b in all_books if b not in books]
            if extra:
                scan(extra)
        if not found:
            return [], "no_candidate_sentence"
        found.sort(key=lambda x: (-x[0], x[1], x[2], x[3]))
        picked, seen_text, seen_chapter = [], set(), set()
        for score, book, no, anchor, sent, tag in found:
            if sent in seen_text:
                continue
            if (book, no) not in seen_chapter and len(picked) < MAX_PER_PAGE:
                picked.append((book, no, anchor, sent, tag))
                seen_text.add(sent)
                seen_chapter.add((book, no))
            if len(picked) >= MAX_PER_PAGE:
                break
        if not picked:      # 同回兜底
            for score, book, no, anchor, sent, tag in found:
                if sent in seen_text:
                    continue
                picked.append((book, no, anchor, sent, tag))
                seen_text.add(sent)
                if len(picked) >= MAX_PER_PAGE:
                    break
        quotes = []
        for book, no, anchor, sent, tag in picked:
            src = f"corpus:{book}/{no:03d}" + (
                "（对白事实句）" if tag == "dialogue" else
                "（对白事实句·叙述标签扩窗）" if tag == "dialogue-expanded" else "")
            quotes.append({"text": sent, "loc": f"{book}#pn-r{no}.{anchor}", "source": src})
        return quotes, "ok"

    # ---- 单段候选 ----
    def _candidates_in_para(self, para, names, bonus):
        """段落 → [(score, 引文)]；叙事段（对白引号外）优先，再分句/窗口。"""
        text = para["text"]
        fence = para.get("fence")
        if fence is not None and fence not in ALLOWED_FENCE:
            return []
        spans = speech_spans(text)
        out, seen = [], set()
        for pos, nlen, hit in _occurrences(text, names):
            in_speech = next(((s2, e2) for s2, e2 in spans if s2 <= pos < e2), None)
            if in_speech:
                if self.allow_dialogue_facts:
                    for score, q in self._dialogue_fact_candidates(
                            text, pos, nlen, hit, in_speech):
                        out.append((score, q, "dialogue"))
                if self.allow_label_expansion:
                    for score, q in self._dialogue_label_expanded_candidates(
                            text, pos, nlen, hit, in_speech):
                        out.append((score, q, "dialogue-expanded"))
                continue            # 默认：名在对白内 → 不作叙事事实句
            # 名称所在叙事段（切掉对白引号）
            seg_s, seg_e = 0, len(text)
            for s2, e2 in spans:
                if e2 <= pos:
                    seg_s = max(seg_s, e2)
                elif s2 >= pos + nlen:
                    seg_e = min(seg_e, s2)
            if not (seg_s <= pos and pos + nlen <= seg_e):
                continue
            ent_ok = any(s2 <= pos < e2 and hit in text[s2:e2]
                         for s2, e2, _t in para["ents"])
            cands = []
            seg = text[seg_s:seg_e]
            for s, e, _sent in iter_sentences(seg):
                if s <= pos - seg_s and pos + nlen - seg_s <= e:
                    cands.append(("sentence", s + seg_s, e + seg_s))
                    break
            cs, ce = _clause_span(text, pos, nlen)
            cands.append(("clause", max(cs, seg_s), min(ce, seg_e)))
            ws, we = _window_span(text, pos, nlen, MAX_QUOTE_LEN)
            cands.append(("window", max(ws, seg_s), min(we, seg_e)))
            for kind, s, e in cands:
                s, e = _trim_span(text, s, e)
                q = text[s:e].strip()
                qlen = len(q)
                if not (MIN_QUOTE_LEN <= qlen <= MAX_QUOTE_LEN):
                    continue
                if hit not in q or is_placeholder(q) or q in seen:
                    continue
                if any(s2 < e and e2 > s for s2, e2 in spans):
                    continue        # 含对白引号 → 不收
                if kind == "window" and q[-1] not in "。！？" and qlen < 25:
                    continue        # 窗口过短且无句末标点 → 不收
                if q[0] in "，。；：、”" or q[-1] in "，、：；“":
                    continue        # 首尾残留标点/开引号；招式名引号（”）允许
                verb_cnt = sum(1 for s2, e2, _t in para["verbs"] if s2 < e and e2 > s)
                tier = 0            # 0=常规；1=名+谓词字；2=名+状态短语（最后兜底）
                if verb_cnt < 1 and not (ent_ok and qlen >= 12):
                    if ent_ok and _has_predicate(q) and qlen >= 12:
                        tier = 1
                    elif kind != "sentence" and qlen >= 12:
                        tier = 2
                    else:
                        continue
                score = {"sentence": 4, "clause": 2, "window": 0}[kind]
                score += 3 if ent_ok else 1
                score += min(verb_cnt, 2)
                score += 1 if 15 <= qlen <= 45 else 0
                score += bonus
                score -= 2 if tier == 1 else 0
                score -= 4 if tier == 2 else 0
                out.append((score, q, ""))
                seen.add(q)
        return out

    def _dialogue_fact_candidates(self, text, pos, nlen, hit, span):
        """对白内事实句（可选兜底）：引号内、含名、无 ？！、12-60 字、陈述语气。"""
        s2, e2 = span
        inner_s, inner_e = s2 + 1, e2 - 1
        if not (inner_s <= pos and pos + nlen <= inner_e):
            return []
        inner = text[inner_s:inner_e]
        out = []
        for cs, ce, _sent in iter_sentences(inner):
            if not (cs <= pos - inner_s and pos + nlen - inner_s <= ce):
                continue
            for kind, s, e in (("sentence", cs + inner_s, ce + inner_s),
                               ("clause", *_clause_span(text, pos, nlen))):
                s, e = _trim_span(text, s, e)
                s, e = max(s, inner_s), min(e, inner_e)
                q = text[s:e].strip()
                qlen = len(q)
                if not (12 <= qlen <= MAX_QUOTE_LEN):
                    continue
                if hit not in q or is_placeholder(q):
                    continue
                if re.search(r"[？！]", q):
                    continue            # 感叹/疑问不算事实陈述
                if q[0] in "，。；：、”" or q[-1] in "，、：；“":
                    continue
                out.append((-6 if kind == "sentence" else -7, q))
                break
        return out

    def _dialogue_label_expanded_candidates(self, text, pos, nlen, hit, span):
        """task-82：对白内「叙述标签扩窗 + 事实性判定」。

        只在名所在句为陈述句（无 ？！）时启用；句过长（>60）时在句内按
        逗号/分号/冒号边界扩窗取 12-60 字事实分句；不跨引号、不取疑问/感叹。
        """
        s2, e2 = span
        inner_s, inner_e = s2 + 1, e2 - 1
        if not (inner_s <= pos and pos + nlen <= inner_e):
            return []
        inner = text[inner_s:inner_e]
        rel = pos - inner_s
        # 名所在句：必须为陈述句（无 ？！）
        sent = None
        for cs, ce, _sent in iter_sentences(inner):
            if cs <= rel and rel + nlen <= ce:
                sent = (cs, ce, inner[cs:ce])
                break
        if not sent:
            return []
        cs, ce, sentence = sent
        if re.search(r"[？！!?]", sentence):
            return []
        out, seen = [], set()
        candidates = []
        if 12 <= len(sentence.strip()) <= MAX_QUOTE_LEN:
            candidates.append((cs, ce))
        elif len(sentence.strip()) < 12:
            # 短陈述句跨句扩窗：只并入相邻陈述句，遇到 ？！ 即停（仍须 ≤60 字）
            sents = list(iter_sentences(inner))
            idx = next((i for i, (a, b, _t) in enumerate(sents) if a <= rel < b), None)
            if idx is not None:
                start = idx
                end = idx
                cur_len = len(sentence.strip())
                while end + 1 < len(sents) and cur_len < 12:
                    nxt = sents[end + 1][2]
                    if re.search(r"[？！!?]", nxt):
                        break
                    cur_len += len(nxt.strip())
                    end += 1
                if end > start and cur_len <= MAX_QUOTE_LEN:
                    candidates.append((sents[start][0], sents[end][1]))
        # 句内按标点边界组合扩窗（含名，最多 3 个相邻片段，≤60 字）
        bounds = [cs]
        for m in re.finditer(r"[。！？；，、：]", inner[cs:ce]):
            bounds.append(cs + m.start() + 1)
        bounds.append(ce)
        bounds = sorted(set(bounds))
        for i in range(len(bounds) - 1):
            if not (bounds[i] <= rel < bounds[i + 1]):
                continue
            for j in range(i, min(len(bounds) - 1, i + 4)):
                a, b = bounds[i], bounds[j + 1]
                q = inner[a:b].strip()
                if not (12 <= len(q) <= MAX_QUOTE_LEN):
                    continue
                candidates.append((a, b))
        for a, b in candidates:
            q = _trim_span(inner, a, b)[0:2]
            s, e = q
            qtext = inner[s:e].strip()
            qlen = len(qtext)
            if not (12 <= qlen <= MAX_QUOTE_LEN):
                continue
            if hit not in qtext or is_placeholder(qtext) or qtext in seen:
                continue
            if re.search(r"[？！!?]", qtext):
                continue
            if qtext[0] in "，。；：、”" or qtext[-1] in "，、：；“":
                continue
            if not _has_predicate(qtext):
                continue
            # 单字/纯称呼（如「常叔叔、程叔叔」）不算事实句
            if not re.search(r"[。，；]", qtext) and len(qtext) < 18:
                continue
            seen.add(qtext)
            # 长句含句号 / 名+谓词的窗口优先；对白扩窗默认低分（保守）
            score = -5 + (1 if "。" in qtext else 0) + (1 if 18 <= qlen <= 45 else 0)
            out.append((score, qtext))
        return out

    def _corpus_exact(self, book: str, no: int, raw: str, q: str, names):
        """引文 → 底本精确子串（先直查；不中则归一化回查并回填底本切片）。"""
        if not raw:
            return None
        if q in raw:
            return q
        key = (book, no)
        if key not in self._norm_cache:
            self._norm_cache[key] = _norm_with_map(raw)
        norm_raw, idx = self._norm_cache[key]
        nq = normalize_text(q)
        if not nq:
            return None
        pos = norm_raw.find(nq)
        while pos != -1:
            s = idx[pos]
            e = idx[pos + len(nq) - 1] + 1
            slice_ = raw[s:e]
            if len(slice_) <= MAX_QUOTE_LEN and not is_placeholder(slice_) \
                    and any(n in slice_ for n in names):
                return slice_
            pos = norm_raw.find(nq, pos + 1)
        return None

    # ---- frontmatter 改写 ----
    @staticmethod
    def render_quotes_block(quotes) -> str:
        lines = ["quotes:"]
        for q in quotes:
            lines.append(f"  - text: {yaml_scalar(q['text'])}")
            lines.append(f"    loc: {yaml_scalar(q['loc'])}")
            lines.append(f"    source: {yaml_scalar(q['source'])}")
        return "\n".join(lines)

    def build_new_text(self, page: Page, quotes) -> str:
        fm = page.fm or ""
        block = self.render_quotes_block(quotes)
        lines = fm.split("\n")
        out, i, replaced = [], 0, False
        while i < len(lines):
            ln = lines[i]
            if re.match(r"^quotes:\s*(\[\s*\])?\s*$", ln):
                out.append(block)
                i += 1
                # 吞掉旧 quotes 块的缩进行
                while i < len(lines) and re.match(r"^\s+", lines[i]):
                    i += 1
                replaced = True
                continue
            if re.match(r"^quote_status:\s*", ln):
                out.append("quote_status: filled")
                i += 1
                continue
            if re.match(r"^quote_note:\s*", ln):
                out.append("quote_note: 引文由 fill_content_quotes.py 从底本抽取"
                           "（精确子串/≤60字/L0 档），待 W7 核验")
                i += 1
                continue
            out.append(ln)
            i += 1
        if not replaced:            # 无 quotes 键 → 插到 frontmatter 末尾
            out.append(block)
        new_fm = "\n".join(out)
        return f"---\n{new_fm}\n---\n{page.body}"

    # ---- 应用（备份 + 写 + 断言） ----
    def apply_page(self, page: Page, quotes):
        """→ (ok, msg)；写前重读比对 sha（防并发改动），写后逐项断言。"""
        current = page.path.read_text(encoding="utf-8")
        if hashlib.sha256(current.encode("utf-8")).hexdigest() != page.sha:
            return False, "concurrent_modified"
        new_text = self.build_new_text(page, quotes)
        backup = None
        if self.backup_dir:
            backup = self.backup_dir / page.rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(page.path, backup)
        page.path.write_text(new_text, encoding="utf-8")
        # ---- 断言 ----
        new_page = Page(page.path, page.rel, page.kind, new_text)
        fm = new_page.fm or ""
        parsed = self.parse_quotes_block(fm)
        errs = []
        if not (1 <= len(parsed) <= MAX_PER_PAGE):
            errs.append(f"quotes_count={len(parsed)}")
        if len({q['text'] for q in parsed}) != len(parsed):
            errs.append("duplicate_text")
        for q in parsed:
            if len(q["text"]) > MAX_QUOTE_LEN:
                errs.append(f"too_long={len(q['text'])}")
            raw = self.load_corpus(*self._loc_book_chapter(q["loc"])) if q.get("loc") else None
            if not raw or q["text"] not in raw:
                errs.append("not_in_corpus")
        if new_page.body != page.body:
            errs.append("body_changed")
        if fm_scalar(fm, "quote_status") != "filled":
            errs.append("quote_status_not_filled")
        if backup is not None and not backup.exists():
            errs.append("backup_missing")
        if errs:
            # 断言失败 → 回滚
            page.path.write_text(current, encoding="utf-8")
            return False, "assert_failed:" + ",".join(sorted(set(errs)))
        return True, "ok"

    @staticmethod
    def parse_quotes_block(fm: str):
        """从 frontmatter 文本解析 quotes 块（只认本脚本写出的格式）。"""
        quotes, cur = [], None
        active = False
        for ln in fm.split("\n"):
            if re.match(r"^quotes:\s*$", ln):
                active = True
                continue
            if active:
                m = re.match(r"^\s+-\s+text:\s*(.+)$", ln)
                if m:
                    if cur:
                        quotes.append(cur)
                    cur = {"text": json.loads(m.group(1)), "loc": "", "source": ""}
                    continue
                m = re.match(r"^\s+loc:\s*(.+)$", ln)
                if m and cur:
                    cur["loc"] = json.loads(m.group(1))
                    continue
                m = re.match(r"^\s+source:\s*(.+)$", ln)
                if m and cur:
                    cur["source"] = json.loads(m.group(1))
                    continue
                if ln.strip() and not ln.startswith((" ", "\t")):
                    break
        if cur:
            quotes.append(cur)
        return quotes

    def _loc_book_chapter(self, loc: str):
        m = re.match(r"^(.+)#pn-r(\d+)\.(\d+)$", loc or "")
        if not m:
            return ("", -1)
        return (m.group(1), int(m.group(2)))


# ==================== W7 抽样核验 ====================
def w7_sample_verify(quotes, limit=50):
    """用 W7 引擎对抽样引文做 verify_segment（hit/near/miss），并比对 loc 锚点。"""
    if not quotes:
        return {"n": 0, "hit": 0, "near": 0, "miss": 0, "anchor_match": 0, "rows": []}
    if w7 is None:
        return {"n": 0, "hit": 0, "near": 0, "miss": 0, "anchor_match": 0,
                "rows": [], "note": "W7 模块不可用"}
    try:
        index = w7.CorpusIndex(config.CORPUS_ROOT)
    except Exception as e:  # pragma: no cover
        return {"n": 0, "hit": 0, "near": 0, "miss": 0, "anchor_match": 0,
                "rows": [], "note": f"W7 底本载入失败：{e}"}
    step = max(1, len(quotes) // limit)
    sample = quotes[::step][:limit]
    stats = collections.Counter()
    rows = []
    for q in sample:
        r = index.verify_segment(w7.normalize(q["text"]))
        stats[r["status"]] += 1
        anchors = [c.get("anchor") for c in r.get("candidates") or [] if c.get("anchor")]
        anchor_match = q["loc"] in anchors
        stats["anchor_match"] += int(anchor_match)
        rows.append({"loc": q["loc"], "len": len(q["text"]), "sha": sha256_12(q["text"]),
                     "w7_status": r["status"], "w7_anchor": anchors[0] if anchors else "",
                     "anchor_match": anchor_match})
    return {"n": len(sample), "hit": stats["hit"], "near": stats["near"],
            "miss": stats["miss"], "anchor_match": stats["anchor_match"], "rows": rows}


# ==================== 报告 ====================
def count_content_pages(content_dir: Path):
    """→ (总页数, 已填充页数)；只读 frontmatter 头 4KB。"""
    total = filled = 0
    for p in Path(content_dir).glob("*/*.md"):
        total += 1
        try:
            head = p.read_text(encoding="utf-8")[:4000]
        except Exception:
            continue
        if re.search(r"^quote_status:\s*filled\s*$", head, re.M):
            filled += 1
    return total, filled


def write_report(report_dir: Path, summary: dict, by_type: dict, reasons: dict,
                 samples: dict, plan_rows: list, mode: str, elapsed: float,
                 report_name: str = "content_quotes_report"):
    report_dir.mkdir(parents=True, exist_ok=True)
    md = report_dir / f"{report_name}.md"
    js = report_dir / f"{report_name}.json"
    payload = {
        "schema": SCHEMA, "generated_at": now_iso(), "mode": mode,
        "elapsed_s": round(elapsed, 2), "summary": summary,
        "by_type": by_type, "unfilled_reasons": reasons,
        "w7_sample": {k: v for k, v in samples.items() if k != "rows"},
        "w7_sample_rows": samples.get("rows", []),
        "plan_rows": plan_rows,
    }
    js.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    L = []
    L.append("# content 引文填充报告（fill_content_quotes.py）\n")
    L.append(f"- 生成：{now_iso()}　模式：**{mode}**　耗时：{elapsed:.1f}s")
    L.append("- 纪律：精确子串（底本逐字存在）/ ≤60 字 / 每页 1-2 条 / 只取叙事事实句 / 不输出原文到报告")
    L.append("- 数据：`content/` 页 frontmatter `quotes[]` + `quote_status`；W7 抽样核验复用 `scripts/verify_quotes.py` 引擎")
    L.append("- 口径：本批只处理 `quote_status: pending` 页；「此前已填充 / 累计填充率」按全库 1,526 页计\n")
    L.append("## 一、总览\n")
    L.append("| 指标 | 数值 |")
    L.append("|---|---|")
    for k, v in summary.items():
        L.append(f"| {k} | {v} |")
    L.append("\n## 二、按页型\n")
    L.append("| 页型 | 页数 | 已填充 | 填充率 | 引文数 |")
    L.append("|---|---|---|---|---|")
    for kind, d in by_type.items():
        rate = f"{d['filled'] / d['pages'] * 100:.1f}%" if d["pages"] else "-"
        L.append(f"| {kind} | {d['pages']} | {d['filled']} | {rate} | {d['quotes']} |")
    L.append("\n## 三、未填充原因\n")
    L.append("| 原因 | 页数 |")
    L.append("|---|---|")
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        L.append(f"| {k} | {v} |")
    L.append("\n## 四、W7 抽样核验（不输出原文）\n")
    if samples.get("n"):
        L.append(f"- 抽样：{samples['n']} 条；**hit {samples['hit']} / near {samples['near']} / miss {samples['miss']}**")
        L.append(f"- loc 与 W7 候选锚点一致：{samples['anchor_match']}/{samples['n']}")
        L.append("")
        L.append("| loc | 字数 | sha256_12 | W7 状态 | W7 锚点 | 锚点一致 |")
        L.append("|---|---|---|---|---|---|")
        for r in samples.get("rows", [])[:30]:
            L.append(f"| {r['loc']} | {r['len']} | {r['sha']} | {r['w7_status']} | {r['w7_anchor']} | {r['anchor_match']} |")
    else:
        L.append(f"- 未抽样：{samples.get('note', '无引文')}")
    L.append("\n## 五、填充明细（前 40 页，loc 级）\n")
    L.append("| 页面 | 页型 | 引文数 | loc |")
    L.append("|---|---|---|---|")
    for row in plan_rows[:40]:
        locs = "；".join(q["loc"] for q in row.get("quotes", []))
        L.append(f"| {row['page']} | {row['kind']} | {len(row.get('quotes', []))} | {locs} |")
    L.append("\n> 说明：报告不含引文原文（仅 loc/字数/hash），与 W7 隐私纪律一致。\n")
    md.write_text("\n".join(L) + "\n", encoding="utf-8")
    return md, js


# ==================== 自检 ====================
def selftest() -> int:
    """合成语料自检（不碰真实 content/）：抽取 → 断言 → apply → 幂等。"""
    base = config.DIR_LOGS / "qa" / "_selftest_fill_quotes"
    if base.exists():
        shutil.rmtree(base)
    corpus = base / "corpus" / "TestBook"
    tagged = base / "tagged" / "TestBook"
    content = base / "content" / "person"
    backup = base / "backup"
    for d in (corpus, tagged, content):
        d.mkdir(parents=True, exist_ok=True)

    long_sentence = ("李四在雪地里走了三天三夜，终于在第四日清晨抵达山门，叩门求见掌门，"
                     "掌门却闭门不见，只让童子传话说来客请回，李四无奈只得在门外苦候七日七夜，"
                     "风雪交加饥寒交迫仍不肯离去。")
    extra_corpus = [
        "正是：李四一剑惊天下，从此名扬四海。",
        "李四拔剑吟诗一首。",
        "他使出一招“Test剑法”，剑光如练。",
        "赵六说道：“李四这人剑法通神，我自愧不如，日后定要再向他讨教一番。”",
        "李四听了这话大怒，拔剑出鞘：“赵六，你欺人太甚！”",
        "李四在雪夜里赶路，翻过三座大山，渡过两条大河，走了整整七天，终于在第八日清晨看见远处城楼的灯火。",
        "他施展出天山剑法，果然非同凡响。",
    ]
    corpus_text = (
        "第一回 测试回\n\n"
        "李四提剑走入客栈，看见王五坐在窗边。\n"
        "赵六笑道：“今日天气甚好，你我共饮一杯。”\n"
        "未明示\n"
        f"{long_sentence}\n"
        + "\n".join(extra_corpus) + "\n"
    )
    (corpus / "001　第一回　测试回.txt").write_text(corpus_text, encoding="utf-8")

    tagged_text = (
        "# [0] 测试回\n\n"
        "::: 诗\n[1] 〖@李四〗⟦■拔剑⟧，吟诗一首。\n:::\n\n"
        "[2] 〖@李四〗⟦■提剑⟧⟦■走入⟧客栈，⟦■看见⟧〖@王五〗坐在窗边。\n\n"
        "[3] 未明示\n\n"
        "[4] 〖@李四〗在雪地里⟦■走了⟧三天三夜，终于在第四日清晨⟦■抵达⟧山门，"
        "叩门求见掌门，掌门却闭门不见，只让童子传话说来客请回，"
        "李四无奈只得在门外苦候七日七夜，风雪交加饥寒交迫仍不肯离去。\n\n"
        "::: 回末\n[5] 正是：〖@李四〗⟦■一剑⟧惊天下，从此名扬四海。\n:::\n\n"
        "::: 诗\n[6] 〖@李四〗⟦■拔剑⟧吟诗一首。\n:::\n\n"
        "[7] 他⟦■使出⟧一招“Test剑法”，剑光如练。\n\n"
        "[8] 赵六说道：“李四这人剑法通神，我自愧不如，日后定要再向他讨教一番。”\n\n"
        "[9] 〖@李四〗⟦■听了⟧这话⟦■大怒⟧，⟦■拔剑⟧出鞘：“赵六，你欺人太甚！”\n\n"
        "[10] 〖@李四〗在雪夜里⟦■赶路⟧，翻过三座大山，渡过两条大河，"
        "走了整整七天，终于在第八日清晨看见远处城楼的灯火。\n\n"
        "[11] 他⟦■施展⟧出〖☆天山剑法〗，果然非同凡响。\n"
    )
    (tagged / "001.tagged.md").write_text(tagged_text, encoding="utf-8")
    (tagged / "001.struct.md").write_text(
        "# [0] 测试回\n\n::: 诗\n[1] 李四拔剑，吟诗一首。\n:::\n\n"
        "[2] 李四提剑走入客栈，看见王五坐在窗边。\n\n[3] 未明示\n\n"
        "[4] " + long_sentence + "\n\n"
        "[5] 正是：李四一剑惊天下，从此名扬四海。\n\n"
        "[6] 李四拔剑吟诗一首。\n\n[7] 他使出一招“Test剑法”，剑光如练。\n\n"
        "[8] 赵六说道：“李四这人剑法通神，我自愧不如，日后定要再向他讨教一番。”\n\n"
        "[9] 李四听了这话大怒，拔剑出鞘：“赵六，你欺人太甚！”\n\n"
        "[10] 李四在雪夜里赶路，翻过三座大山，渡过两条大河，走了整整七天，"
        "终于在第八日清晨看见远处城楼的灯火。\n\n"
        "[11] 他施展出天山剑法，果然非同凡响。\n",
        encoding="utf-8")

    page_text = (
        "---\npage_type: 人物档案页\ncard_ref: card.person.test\ncanonical: 李四\n"
        "slug: 李四\nbook_scope:\n  - TestBook\nconfidence: C\n"
        "quotes: []\nquote_status: pending\nquote_note: 待填\n---\n\n# 李四\n\n正文一行。\n"
    )
    page_path = content / "card.person.test.md"
    page_path.write_text(page_text, encoding="utf-8")

    art_page_text = (
        "---\npage_type: 武功档案页\ncard_ref: card.art.test\ncanonical: 天山剑术\n"
        "slug: 天山剑术\nbook_scope:\n  - TestBook\nconfidence: C\n"
        "quotes: []\nquote_status: pending\nquote_note: 待填\n---\n\n# 天山剑术\n\n正文。\n"
    )
    (base / "content" / "art").mkdir(parents=True, exist_ok=True)
    (base / "content" / "art" / "card.art.test.md").write_text(art_page_text, encoding="utf-8")

    cards = {"card.person.test": {"canonical": "李四", "aliases": []},
             "card.art.test": {"canonical": "天山剑术", "aliases": []}}
    filler = QuoteFiller(content_dir=base / "content", corpus_root=base / "corpus",
                         tagged_dir=base / "tagged", registry_dir=base / "registry",
                         cards_path=None, backup_dir=backup, work_ids=({}, {}))
    filler.cards = cards

    checks = []

    def ck(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    pages = list(filler.iter_pages())
    ck("A01 页面可枚举", len(pages) == 2, f"n={len(pages)}")
    page = pages[0]
    ck("A02 frontmatter 解析", page.fm is not None and page.canonical == "李四")
    quotes, reason = filler.extract(page)
    ck("A03 抽到 1-2 条引文", 1 <= len(quotes) <= 2, f"n={len(quotes)} reason={reason}")
    ck("A04 每条 ≤60 字", all(len(q["text"]) <= MAX_QUOTE_LEN for q in quotes))
    ck("A05 精确子串在底本", all(q["text"] in corpus_text for q in quotes))
    ck("A06 loc 格式", all(re.match(r"^TestBook#pn-r\d+\.\d+$", q["loc"]) for q in quotes))
    ck("A07 source 格式", all(q["source"].startswith("corpus:TestBook/001") for q in quotes))
    joined = "".join(q["text"] for q in quotes)
    ck("A08 跳过围栏韵文", "吟诗一首" not in joined, joined[:20])
    ck("A09 跳过占位", "未明示" not in joined)
    ck("A10 跳过超长句", "风雪交加" not in joined, joined[:20])

    ok, msg = filler.apply_page(page, quotes)
    ck("A11 apply 成功", ok, msg)
    after = page_path.read_text(encoding="utf-8")
    new_page = Page(page_path, "person/card.person.test.md", "person", after)
    parsed = filler.parse_quotes_block(new_page.fm or "")
    ck("A12 quotes 块可回读", len(parsed) == len(quotes), f"n={len(parsed)}")
    ck("A13 quote_status=filled", fm_scalar(new_page.fm or "", "quote_status") == "filled")
    ck("A14 body 未改动", new_page.body == page.body)
    ck("A15 备份存在", (backup / "person/card.person.test.md").exists())
    ck("A16 页内引文唯一", len({q["text"] for q in parsed}) == len(parsed))

    q2, reason2 = filler.extract(new_page)
    ck("A17 幂等（已填充跳过）", q2 == [] and reason2 == "already_filled", reason2)

    # ---- 规则级断言（batch2 新增规则） ----
    paras = {p["anchor"]: p for p in filler.load_tagged("TestBook", 1)}
    names = ["李四"]

    def cands(anchor, f=filler, nm=names):
        return f._candidates_in_para(paras[anchor], nm, 0)

    ck("A18 回末围栏可取", len(cands(5)) > 0, str(cands(5))[:80])
    ck("A19 诗围栏仍禁", cands(6) == [], str(cands(6))[:80])
    _p7 = paras[7]["text"]
    _qs = _p7.find("“")
    _qe = _p7.find("”", _qs) + 1
    ck("A20 招式名短引号视为叙事", _qs >= 0 and not is_speech_span(_p7, _qs, _qe))
    ck("A21 对白内名默认不收", cands(8) == [])
    ck("A22 对白事实句可选（flag 开）",
       len(filler.__class__(
           content_dir=base / "content", corpus_root=base / "corpus",
           tagged_dir=base / "tagged", registry_dir=base / "registry",
           cards_path=None, backup_dir=None, work_ids=({}, {}),
           allow_dialogue_facts=True
       )._candidates_in_para(paras[8], names, 0)) > 0)
    ck("A23 长句切分可取", any(len(q) <= MAX_QUOTE_LEN and "李四" in q for _s, q, _t in cands(10)))
    art_page = Page(base / "content" / "art" / "card.art.test.md",
                    "art/card.art.test.md", "art", art_page_text)
    art_names = filler.names_for(art_page)
    ck("A24 变体匹配（剑术→剑法）", "天山剑法" in art_names, str(art_names[:5]))
    ck("A25 变体段可取", any("天山剑法" in q for _s, q, _t in cands(11, nm=art_names)))

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"[selftest] {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        print(f"  {'✅' if ok else '❌'} {name}" + (f"  [{detail}]" if detail and not ok else ""))
    if passed != len(checks):
        return 1
    shutil.rmtree(base, ignore_errors=True)
    return 0


# ==================== 主流程 ====================
def run(args) -> int:
    started = datetime.now()
    filler = QuoteFiller(
        content_dir=config.ROOT / "content",
        corpus_root=config.CORPUS_ROOT,
        tagged_dir=config.DIR_TAGGED,
        registry_dir=config.DIR_REGISTRY,
        cards_path=config.DIR_REGISTRY / "sku" / "cards.json",
        backup_dir=config.DIR_LOGS / "qa" / "content_quotes_backup",
        allow_dialogue_facts=getattr(args, "allow_dialogue_facts", False),
        allow_label_expansion=getattr(args, "allow_label_expansion", False),
    )
    types = tuple(t.strip() for t in args.types.split(",")) if args.types else None
    mode = "apply" if args.apply else "dry-run"
    total_all, before_filled = count_content_pages(config.ROOT / "content")
    by_type = collections.defaultdict(lambda: {"pages": 0, "filled": 0, "quotes": 0})
    reasons = collections.Counter()
    all_quotes, plan_rows = [], []
    total = filled = q_total = q_chars = 0
    apply_ok = apply_fail = skipped_filled = 0
    for page in filler.iter_pages(types=types, limit=args.limit):
        if args.only_pending and re.search(r"^quote_status:\s*filled\s*$", page.text, re.M):
            skipped_filled += 1
            continue
        total += 1
        by_type[page.kind]["pages"] += 1
        quotes, reason = filler.extract(page)
        if not quotes:
            reasons[reason] += 1
            continue
        row = {"page": page.rel, "kind": page.kind, "quotes": quotes}
        if args.apply:
            ok, msg = filler.apply_page(page, quotes)
            if not ok:
                reasons[f"apply_failed:{msg}"] += 1
                apply_fail += 1
                continue
            apply_ok += 1
        filled += 1
        by_type[page.kind]["filled"] += 1
        by_type[page.kind]["quotes"] += len(quotes)
        q_total += len(quotes)
        q_chars += sum(len(q["text"]) for q in quotes)
        all_quotes.extend(quotes)
        plan_rows.append(row)

    elapsed = (datetime.now() - started).total_seconds()
    cumulative = before_filled + filled
    summary = {
        "总页数": total_all,
        "此前已填充": before_filled,
        "本次处理页数": total,
        "本次新增填充": filled,
        "本次填充率": f"{filled / total * 100:.1f}%" if total else "-",
        "累计填充页数": cumulative,
        "累计填充率": f"{cumulative / total_all * 100:.1f}%" if total_all else "-",
        "本次新增引文条数": q_total,
        "平均每条字数": round(q_chars / q_total, 1) if q_total else 0,
        "最长引文": max((len(q["text"]) for q in all_quotes), default=0),
        "最短引文": min((len(q["text"]) for q in all_quotes), default=0),
        "本次未填充页数": total - filled,
        "跳过（已填充）": skipped_filled,
        "apply 成功页": apply_ok,
        "apply 失败页": apply_fail,
    }
    samples = w7_sample_verify(all_quotes)
    md, js = write_report(Path(args.report_dir), summary, dict(by_type), dict(reasons),
                          samples, plan_rows, mode, elapsed, args.report_name)
    print(f"[fill_content_quotes] 模式={mode} 页={total} 填充={filled} "
          f"引文={q_total} 均长={summary['平均每条字数']} 耗时={elapsed:.1f}s")
    print(f"  W7 抽样：{samples.get('n', 0)} 条 hit={samples.get('hit', 0)} "
          f"near={samples.get('near', 0)} miss={samples.get('miss', 0)} "
          f"锚点一致={samples.get('anchor_match', 0)}")
    print(f"  报告：{md}")
    if reasons:
        top = "、".join(f"{k}={v}" for k, v in reasons.most_common(6))
        print(f"  未填充原因：{top}")
    if args.apply and apply_fail:
        print(f"  ⚠️ apply 失败 {apply_fail} 页（已回滚，详见报告）")
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="content 引文填充（W7 硬门前置）")
    ap.add_argument("--apply", action="store_true", help="写页 frontmatter（缺省 dry-run）")
    ap.add_argument("--selftest", action="store_true", help="合成语料自检（不碰真实 content）")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 页（抽查用）")
    ap.add_argument("--types", default="", help="限定页型，逗号分隔：person,faction,art,artifact,manual")
    ap.add_argument("--report-dir", default=str(config.DIR_LOGS / "qa"), help="报告目录")
    ap.add_argument("--report-name", default="content_quotes_report",
                    help="报告文件名（不含扩展名；批 2 用 content_quotes_batch2_report）")
    ap.add_argument("--only-pending", action="store_true",
                    help="只处理 quote_status: pending 页（补填批次用）")
    ap.add_argument("--allow-dialogue-facts", action="store_true",
                    help="可选兜底：允许对白内事实陈述句（来源标注「对白事实句」；默认关）")
    ap.add_argument("--allow-label-expansion", action="store_true",
                    help="task-82 收尾：叙述标签扩窗（仅对白内陈述句；来源标注「叙述标签扩窗」；默认关）")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not (config.ROOT / "content").exists():
        print("[fill_content_quotes] content/ 不存在", file=sys.stderr)
        return 2
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
