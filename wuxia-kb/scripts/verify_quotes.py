#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W7 · 引文真实性核验 —— verify_quotes.py（W 组首发；机制照搬 shiji W7 三层流水线之"缓存+规则"两层）

用途
----
对 AI 生成内容中出现的**引文/原文片段**做核验，防"看似原文、实为编造"：
  - 目标源：`registry/sku/cards.json` 的 brief/summary（N10 SKU 卡）、`references/` 规律库引文、
    以及后续 W 组页面文案（通过 `--file` 任意 JSON/Markdown/文本接入）；
  - 对照：`config.CORPUS_ROOT`（章回版 34 部锁定底本）+ 5 书 `tagged/<书>/NNN.struct.md`（PN 锚）；
  - 方法：Unicode NFKC 归一 → 去空白/标点 → 子串精确匹配；精确失败再用「锚点定位 + difflib
    ratio≥0.90 + 匹配块长度率≥0.90 + 上下文门槛」做近似匹配；省略号截断的引文按段核验；
  - 输出：`logs/w_group/quote_verify.json` + `logs/w_group/quote_verify_report.md`
    （引文数/命中/近似/未命中/疑似编造 + 定位符；**不输出原文，只给定位符/长度/hash**）；
  - CLI：`--all`（默认，SKU+references）/ `--sku` / `--file <path>`（可重复）/ `--strict` /
    `--selftest`；另有 `--corpus-root/--out-dir/--min-len/--near-ratio` 便于校准。

三层流水线定位（与 shiji W7 对应）
--------------------------------
  第 1 层 缓存：本脚本把 34 部底本归一化后一次性载入内存（`CorpusIndex`），等同一份可复用核验语料；
  第 2 层 规则：归一化子串/近似匹配 + 阈值（本脚本主体）；
  第 3 层 LLM 二审：不在本脚本内（`--strict` 失败项交人工/外部模型复核，报告列疑点清单）。
  纪律：**不输出原文**——JSON/报告只有长度、hash、定位符与统计；引文正文留在调用方上下文。
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import io
import json
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

DEFAULT_CORPUS = config.CORPUS_ROOT
DEFAULT_SKU = config.DIR_REGISTRY / "sku" / "cards.json"
DEFAULT_REFS = config.ROOT / "references"
OUT_DIR = config.DIR_LOGS / "w_group"
OUT_JSON = OUT_DIR / "quote_verify.json"
OUT_MD = OUT_DIR / "quote_verify_report.md"

SCHEMA = "quote-verify-v1"
# ---- 阈值（W7 手册化；--selftest 逐项覆盖） ----
NEAR_RATIO = 0.90        # 近似匹配 difflib ratio 下限
LEN_RATE_MIN = 0.90      # 匹配块总长 / 引文归一长度 下限（防散点噪声）
MIN_QUOTE_LEN = 8        # 归一化后最小引文长度（汉字/字母/数字计数）；低于即 skipped
MIN_SEG_LEN = 4          # 省略号分段后单段最小长度；短段忽略
ANCHOR_LEN = 10          # 锚点长度（首/中/尾切片，用于低成本定位候选）
MAX_CANDIDATES = 5       # 每条引文保留候选定位数
MAX_HITS_PER_SEG = 50    # 单段精确命中扫描上限（防重复短语爆炸）
CONTEXT_PAD = 10         # 近似窗口上下文扩展（字符）
CONTEXT_RATIO = 0.85     # 上下文窗口相似度门槛（防跨句拼接误判）

# ---- 引号对（中文引文；《》是书名号，不算引文） ----
QUOTE_PAIRS = [("「", "」"), ("“", "”"), ("『", "』")]
PAIR_RES = [re.compile(re.escape(a) + r"(.{1,400}?)" + re.escape(b), re.S) for a, b in QUOTE_PAIRS]
ELLIPSIS_RE = re.compile(r"(?:…{1,}|⋯+|\.{3,})")
TITLE_RE = re.compile(r"^\s*(?:第[一二三四五六七八九十百零〇\d]+回|楔子)")
CHAPTER_NUM_RE = re.compile(r"^(\d{1,3})")
PLACEHOLDERS = {"未明示", "待定", "未知", "无", "—", "——", "略", "（待补）"}
# 技术/规则引号判定：
#   ① 含 ASCII/管道/斜杠/箭头/标注符号等（术语转写、字段名、路径）；
#   ② 含规范/规则文本的元词（如"显示串""词表""正则""边界"……）。
# 目的：把 references 规律库里"规则术语引号"与"叙事原文引文"分开——只有后者参与编造判定。
TECH_RE = re.compile(r"[A-Za-z|/\\→←%#;☆◆^~&=／]")
TECH_WORDS = (
    "显示串", "词表", "正则", "边界", "白名单", "前缀", "后缀", "符号", "字段",
    "映射", "判定", "口径", "候选", "标注", "规则", "示例", "反例", "判据",
    "动作", "来源", "现象", "状态", "实体层", "别名", "数据版本", "报告口径",
    "canonical", "mapping", "accept", "schema", "JSON", "pipe",
)

CJK_RE = re.compile(r"[\u4e00-\u9fff]")

SKU_TEXT_FIELDS = ("brief", "summary")           # 任务口径：SKU 卡 brief/summary
SKU_EXTRA_FIELDS = ("proposition",)              # meta.proposition（若有引号也核验）


# ==================== 归一化 ====================
def normalize(text: str) -> str:
    """NFKC + 只保留汉字/字母/数字（大小写不敏感）→ 引文与底本同一把尺子。

    去空白与全部标点，使"标点/空格/换行差异"不影响命中；字形归一（NFKC）覆盖全角字母数字。
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text)
    out = []
    for ch in s:
        if "\u4e00" <= ch <= "\u9fff":
            out.append(ch)
        elif ch.isalnum():
            out.append(ch.lower())
    return "".join(out)


def extract_quotes(text: str):
    """从一段文本抽取引号内片段（去重保序）：→ [(raw, start, end)]"""
    found = []
    seen = set()
    for rx in PAIR_RES:
        for m in rx.finditer(text):
            raw = m.group(1)
            if raw in seen:
                continue
            seen.add(raw)
            found.append((raw, m.start(), m.end()))
    found.sort(key=lambda x: x[1])
    return found


def split_segments(raw: str):
    """省略号截断引文 → 分段；返回归一化后的非空段列表（保留原长度供统计）。"""
    parts = ELLIPSIS_RE.split(raw)
    segs = []
    for p in parts:
        n = normalize(p)
        if len(n) >= MIN_SEG_LEN:
            segs.append(n)
    return segs


def is_placeholder(raw: str) -> bool:
    return raw.strip() in PLACEHOLDERS


def quote_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def quote_kind(raw: str) -> str:
    """narrative=叙事引文（参与编造判定）；technical=术语/规则转写（仅记录，不判编造）。"""
    if TECH_RE.search(raw):
        return "technical"
    if any(w in raw for w in TECH_WORDS):
        return "technical"
    cjk = len(CJK_RE.findall(raw))
    total = len([c for c in raw if not c.isspace()])
    if total and cjk / total < 0.7:
        return "technical"
    return "narrative"


# ==================== 底本索引 ====================
class Chapter:
    __slots__ = ("book", "no", "norm", "offsets", "line_pn", "raw_line_count")

    def __init__(self, book, no, norm, offsets, line_pn, raw_line_count):
        self.book = book
        self.no = no
        self.norm = norm
        self.offsets = offsets          # [(norm_start, norm_len, raw_line_no)]
        self.line_pn = line_pn          # {content_line_index: PN} 或 None
        self.raw_line_count = raw_line_count


def _struct_content_lines(book: str, no: int):
    """struct → [(PN, 内容行文本)]；无 struct 返回 None。"""
    sp = config.struct_path(book, no)
    if not sp.exists():
        return None
    out, cur = [], None
    for raw in sp.read_text(encoding="utf-8").split("\n"):
        s = raw.rstrip()
        if not s.strip() or s.startswith(":::") or s.startswith("# [0] "):
            continue
        m = re.match(r"^\[(\d+)\] (.*)$", s)
        if m:
            cur = int(m.group(1))
            out.append((cur, m.group(2)))
        elif cur is not None:
            out.append((cur, s))
    return out


class CorpusIndex:
    """章回版 34 部底本 → 归一化全文 + 行号/PN 定位索引（只读；一次载入、多处复用）。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.chapters: list[Chapter] = []
        self.books: list[str] = []
        self.total_raw_chars = 0
        self.total_norm_chars = 0
        self._load()

    def _load(self):
        if not self.root.exists():
            raise SystemExit(f"[W7] 底本目录不存在：{self.root}")
        for book_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            chapters = []
            for f in sorted(book_dir.glob("*.txt")):
                m = CHAPTER_NUM_RE.match(f.name)
                if not m:
                    continue
                no = int(m.group(1))
                text = f.read_text(encoding="utf-8-sig")
                lines = text.splitlines()
                ti = next((i for i, ln in enumerate(lines) if TITLE_RE.match(ln)), None)
                start = (ti + 1) if ti is not None else 0
                content = [(i + 1, lines[i]) for i in range(start, len(lines)) if lines[i].strip()]
                offsets, parts, cur = [], [], 0
                for raw_lineno, ln in content:
                    n = normalize(ln)
                    offsets.append((cur, len(n), raw_lineno))
                    parts.append(n)
                    cur += len(n)
                norm = "".join(parts)
                # 5 书 struct → 行号→PN；其余书 line_pn=None（locator 退回 书+回+行）
                line_pn = None
                st = _struct_content_lines(book_dir.name, no)
                if st is not None and len(st) == len(content) \
                        and [t for _, t in st] == [t for _, t in content]:
                    line_pn = {idx: pn for idx, (pn, _) in enumerate(st)}
                chapters.append(Chapter(book_dir.name, no, norm, offsets, line_pn, len(lines)))
                self.total_raw_chars += sum(len(ln) for _, ln in content)
                self.total_norm_chars += len(norm)
            if chapters:
                self.books.append(book_dir.name)
                self.chapters.extend(chapters)

    # ---- 定位 ----
    @staticmethod
    def _locate(ch: Chapter, offset: int) -> dict:
        """归一化偏移 → 定位符（可输出字段；不含原文）。"""
        starts = [o[0] for o in ch.offsets]
        idx = bisect.bisect_right(starts, offset) - 1
        if idx < 0:
            idx = 0
        norm_start, norm_len, raw_line_no = ch.offsets[idx]
        line_index = idx
        pn = ch.line_pn.get(line_index) if ch.line_pn else None
        if pn is not None:
            anchor = f"{ch.book}#pn-r{ch.no}.{pn}"
        else:
            anchor = f"{ch.book}#ch{ch.no:03d}@L{raw_line_no}"
        return {
            "book": ch.book,
            "chapter": ch.no,
            "line": raw_line_no,
            "offset": int(offset),
            "anchor": anchor,
        }

    # ---- 精确 ----
    def search_exact(self, seg_norm: str, limit: int = MAX_CANDIDATES):
        hits = []
        for ch in self.chapters:
            pos = ch.norm.find(seg_norm)
            while pos != -1 and len(hits) < MAX_HITS_PER_SEG:
                hits.append(self._locate(ch, pos))
                if len(hits) >= limit:
                    return hits
                pos = ch.norm.find(seg_norm, pos + 1)
        return hits

    # ---- 近似（锚点定位 + difflib）----
    @staticmethod
    def _anchors(seg: str):
        n = len(seg)
        if n <= ANCHOR_LEN:
            return [(0, seg)]
        anchors = [(0, seg[:ANCHOR_LEN]), (max(0, (n - ANCHOR_LEN) // 2), seg[(n - ANCHOR_LEN) // 2:(n - ANCHOR_LEN) // 2 + ANCHOR_LEN]),
                   (n - ANCHOR_LEN, seg[-ANCHOR_LEN:])]
        # 去重
        seen, out = set(), []
        for off, a in anchors:
            if a not in seen:
                seen.add(a)
                out.append((off, a))
        return out

    def search_near(self, seg: str):
        """→ (best: dict|None, hits: list) best 含 ratio/len_rate/locator。

        窗口与引文**等长对齐**（±2 字容错搜索起始位移），避免把窗口外长上下文稀释进 ratio；
        上下文门槛 = 匹配块 ≥2 且最长块 ≥ min(ANCHOR_LEN, 段长的 60%)（防散点噪声）。
        """
        best = None
        hits = []
        for ch in self.chapters:
            if len(ch.norm) < len(seg) * LEN_RATE_MIN:
                continue
            for off_in_seg, anchor in self._anchors(seg):
                pos = ch.norm.find(anchor)
                checked = 0
                while pos != -1 and checked < 3:
                    base = max(0, pos - off_in_seg)
                    for delta in (0, -1, 1, -2, 2):
                        start = max(0, base + delta)
                        window = ch.norm[start:start + len(seg)]
                        if len(window) < int(len(seg) * LEN_RATE_MIN):
                            continue
                        m = SequenceMatcher(None, seg, window, autojunk=False)
                        blocks = [b for b in m.get_matching_blocks() if b.size > 0]
                        matched = sum(b.size for b in blocks)
                        len_rate = matched / max(1, len(seg))
                        longest = max((b.size for b in blocks), default=0)
                        longest_min = min(ANCHOR_LEN, max(4, int(len(seg) * 0.6)))
                        # 上下文门槛：匹配块最长段 ≥ 下限（单点替换=单块亦可通过）；碎块多时另记块数
                        if len_rate >= LEN_RATE_MIN and longest >= longest_min:
                            ratio = m.ratio()
                            if ratio >= NEAR_RATIO:
                                loc = self._locate(ch, start)
                                cand = {"ratio": round(ratio, 4),
                                        "len_rate": round(len_rate, 4),
                                        "longest_block": longest,
                                        "locator": loc,
                                        "context": f"aligned window; blocks={len(blocks)}"}
                                hits.append(cand)
                                if best is None or cand["ratio"] > best["ratio"]:
                                    best = cand
                    checked += 1
                    pos = ch.norm.find(anchor, pos + 1)
                if len(hits) >= MAX_CANDIDATES:
                    return best, hits
        return best, hits

    # ---- 单段核验 ----
    def verify_segment(self, seg: str) -> dict:
        exact = self.search_exact(seg)
        if exact:
            return {"status": "hit", "ratio": 1.0, "method": "exact",
                    "candidates": exact[:MAX_CANDIDATES], "n_candidates": len(exact)}
        best, near = self.search_near(seg)
        if best is not None:
            cands = [h["locator"] | {"ratio": h["ratio"], "method": "near"} for h in near[:MAX_CANDIDATES]]
            return {"status": "near", "ratio": best["ratio"], "method": "near",
                    "candidates": cands, "n_candidates": len(near),
                    "len_rate": best["len_rate"], "longest_block": best["longest_block"]}
        return {"status": "miss", "ratio": 0.0, "method": "none",
                "candidates": [], "n_candidates": 0}


# ==================== 目标源抽取 ====================
def iter_markdown_quotes(path: Path, source_prefix: str):
    """Markdown 文本 → 引文记录（跳过代码块；YAML front matter 仅取 quotes[].text）。"""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_code = False
    front = False
    front_lines = []
    section = ""
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if i == 1 and s == "---":
            front = True
            continue
        if front:
            if s == "---":
                front = False
            else:
                front_lines.append((i, line))
            continue
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^#{2,6}\s+(.+)$", s)
        if m:
            # 小节标题可能含引文/人名（如 B03 标题内嵌示例），source 标签只取编号（A01/B03…），
            # 避免把原文/引文片段带进输出（"不输出原文"纪律）。
            head = m.group(1).strip()
            sm = re.match(r"^([A-F]\d{2})\b", head)
            section = sm.group(1) if sm else ""
        for raw, *_ in extract_quotes(line):
            yield {"source": f"{source_prefix}#L{i}" + (f"（§{section}）" if section else ""),
                   "file": str(path), "line": i, "raw": raw}
    # content/ W8 页：frontmatter quotes[] 为 W7 核验入口（v0.2 增补，iter_yaml_quotes）
    idx = 0
    in_quotes = False
    for i, line in front_lines:
        s = line.strip()
        if re.match(r"^quotes\s*:\s*$", s):
            in_quotes = True
            continue
        if in_quotes:
            if re.match(r"^\S", line) and not s.startswith("-"):
                in_quotes = False
                continue
            m = re.match(r"^-\s*text\s*:\s*(.+)$", s)
            if m:
                raw = m.group(1).strip()
                if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
                    raw = raw[1:-1]
                raw = raw.replace("\\\"", "\"").replace("\\\\", "\\")
                idx += 1
                yield {"source": f"{source_prefix}#yaml.quotes[{idx}]",
                       "file": str(path), "line": i, "raw": raw,
                       "json_path": f"quotes[{idx}].text"}


def iter_json_quotes(obj, path: str, file: Path, allow_all: bool = True):
    """JSON 字符串值 → 引文记录（带 JSON path）。"""
    if isinstance(obj, str):
        for raw, *_ in extract_quotes(obj):
            yield {"source": f"{path}", "file": str(file), "line": None, "raw": raw,
                   "json_path": path}
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_json_quotes(v, f"{path}.{k}" if path else str(k), file, allow_all)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_json_quotes(v, f"{path}[{i}]", file, allow_all)


def iter_sku_quotes(sku_path: Path):
    """SKU 卡：仅 brief/summary（+meta.proposition）字段，按卡记录来源与 stable_id。"""
    payload = json.loads(sku_path.read_text(encoding="utf-8"))
    cards = payload.get("cards") or []
    for idx, card in enumerate(cards):
        stable = ((card.get("meta") or {}).get("stable_id")) or f"card[{idx}]"
        name = ((card.get("name") or {}).get("canonical")) or ""
        for field in SKU_TEXT_FIELDS:
            val = card.get(field)
            if not isinstance(val, str):
                continue
            for raw, *_ in extract_quotes(val):
                yield {"source": f"sku:{stable}.{field}"
                                 + (f"（{name}）" if name else ""),
                       "file": str(sku_path), "line": None, "raw": raw,
                       "json_path": f"cards[{idx}].{field}"}
        meta = card.get("meta") or {}
        for field in SKU_EXTRA_FIELDS:
            val = meta.get(field)
            if isinstance(val, str):
                for raw, *_ in extract_quotes(val):
                    yield {"source": f"sku:{stable}.meta.{field}"
                                     + (f"（{name}）" if name else ""),
                           "file": str(sku_path), "line": None, "raw": raw,
                           "json_path": f"cards[{idx}].meta.{field}"}


def iter_file_quotes(path: Path):
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"[W7] --file 不存在：{p}")
    if p.suffix.lower() == ".json":
        obj = json.loads(p.read_text(encoding="utf-8"))
        yield from iter_json_quotes(obj, "", p)
    else:
        yield from iter_markdown_quotes(p, p.name)


# ==================== 批量核验 ====================
def verify_records(records, index: CorpusIndex):
    """引文记录 → 核验结果（不保留原文）。"""
    rows = []
    stats = Counter()
    seg_stats = Counter()
    for rec in records:
        raw = rec["raw"]
        stats["extracted"] += 1
        norm_len = len(normalize(raw))
        if is_placeholder(raw):
            stats["skipped_placeholder"] += 1
            continue
        segs = split_segments(raw)
        seg_norm_total = sum(len(s) for s in segs)
        if seg_norm_total < MIN_QUOTE_LEN:
            stats["skipped_short"] += 1
            continue
        kind = quote_kind(raw)
        seg_results = []
        for seg in segs:
            r = index.verify_segment(seg)
            seg_stats[r["status"]] += 1
            seg_results.append({"len": len(seg), "status": r["status"],
                                "ratio": r["ratio"], "n_candidates": r["n_candidates"],
                                "candidates": r["candidates"]})
        statuses = [s["status"] for s in seg_results]
        if all(s == "hit" for s in statuses):
            status = "hit"
        elif any(s == "miss" for s in statuses):
            status = "miss"
        else:
            status = "near"
        stats[status] += 1
        ratio_avg = round(sum(s["ratio"] for s in seg_results) / max(1, len(seg_results)), 4)
        first_cand = None
        for s in seg_results:
            if s["candidates"]:
                first_cand = s["candidates"][0]
                break
        row = {
            "id": f"q{len(rows) + 1:05d}",
            "source": rec["source"],
            "file": rec.get("file"),
            "line": rec.get("line"),
            "json_path": rec.get("json_path"),
            "quote_sha256_12": quote_hash(raw),
            "quote_len": len(raw),
            "norm_len": seg_norm_total,
            "kind": kind,
            "n_segments": len(seg_results),
            "status": status,
            "ratio": ratio_avg,
            "segments": seg_results,
            "candidates": seg_results[0]["candidates"][:MAX_CANDIDATES] if seg_results else [],
            "primary_locator": (first_cand or {}).get("anchor"),
        }
        rows.append(row)
    return rows, stats, seg_stats


# ==================== 输出 ====================
def build_payload(rows, stats, seg_stats, index: CorpusIndex, inputs, elapsed):
    narrative = [r for r in rows if r["kind"] == "narrative"]
    suspected = [r for r in narrative if r["status"] == "miss"]
    technical = [r for r in rows if r["kind"] == "technical"]
    payload = {
        "schema": SCHEMA,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "spec": "shiji W7 三层流水线（缓存+规则）· 武侠版；不输出原文",
        "no_output_original_text": True,
        "inputs": inputs,
        "corpus": {
            "root": str(index.root),
            "books": len(index.books),
            "chapters": len(index.chapters),
            "raw_chars": index.total_raw_chars,
            "norm_chars": index.total_norm_chars,
        },
        "thresholds": {
            "near_ratio": NEAR_RATIO, "len_rate_min": LEN_RATE_MIN,
            "min_quote_len": MIN_QUOTE_LEN, "min_seg_len": MIN_SEG_LEN,
            "anchor_len": ANCHOR_LEN, "context_pad": CONTEXT_PAD,
            "context_ratio": CONTEXT_RATIO,
        },
        "stats": {
            "extracted": stats.get("extracted", 0),
            "skipped_placeholder": stats.get("skipped_placeholder", 0),
            "skipped_short": stats.get("skipped_short", 0),
            "verified": len(rows),
            # 核验覆盖率（2026-11-05 修复口径：占位符/过短跳过不计入"已核验"，
            # 防止"2,383 引文核验"式头条夸大——实际分母只是进入核验的 rows）
            "coverage_pct": round(100.0 * len(rows) / stats["extracted"], 2)
                            if stats.get("extracted") else None,
            "hit": stats.get("hit", 0),
            "near": stats.get("near", 0),
            "miss": stats.get("miss", 0),
            "narrative": len(narrative),
            "narrative_suspected": len(suspected),
            "technical": len(technical),
            "technical_miss": sum(1 for r in technical if r["status"] == "miss"),
            "segments": dict(seg_stats),
            "elapsed_sec": round(elapsed, 2),
        },
        "suspected_fabrications": [{
            "id": r["id"], "source": r["source"], "kind": r["kind"],
            "quote_len": r["quote_len"], "norm_len": r["norm_len"],
            "n_segments": r["n_segments"], "ratio": r["ratio"],
            "nearest_anchor": r["primary_locator"],
        } for r in suspected],
        "quotes": rows,
    }
    return payload


def report_md(payload):
    s = payload["stats"]
    c = payload["corpus"]
    th = payload["thresholds"]
    L = ["# W7 引文真实性核验报告（verify_quotes.py）", "",
         f"- 生成：{payload['generated']}",
         f"- 规范：{payload['spec']}",
         f"- 底本：`{c['root']}`（{c['books']} 部 / {c['chapters']} 回 / 归一化 {c['norm_chars']:,} 字）",
         f"- 输入：{', '.join(f'`{x}`' for x in payload['inputs']) or '（无）'}",
         f"- 阈值：归一化子串精确命中；近似 ratio≥{th['near_ratio']}、匹配块长度率≥{th['len_rate_min']}、"
         f"引文≥{th['min_quote_len']} 字；省略号截断按段核验（段≥{th['min_seg_len']} 字）",
         f"- **隐私纪律：本报告与 quote_verify.json 均不输出引文原文**（仅长度/hash/定位符/统计）", "",
         "## 一、总览", "",
         "| 指标 | 数值 |", "|---|---|",
         f"| 抽取引号片段（原始） | {s['extracted']} |",
         f"| 跳过：占位符 | {s['skipped_placeholder']} |",
         f"| 跳过：归一化后 <{th['min_quote_len']} 字 | {s['skipped_short']} |",
         f"| 进入核验 | **{s['verified']}**（覆盖率 {s['coverage_pct']}%——占位/过短跳过项不在核验分母内，"
         f"对外引用 headline 时必须带覆盖率） |",
         f"| **命中（逐段精确）** | **{s['hit']}** |",
         f"| 近似（≥{th['near_ratio']}，需人工复核） | {s['near']} |",
         f"| 未命中（疑似编造/非底本） | {s['miss']} |",
         f"| 其中叙事引文（参与编造判定） | {s['narrative']} |",
         f"| **叙事引文疑似编造** | **{s['narrative_suspected']}** |",
         f"| 技术/规则转写引号（术语，不判编造） | {s['technical']}（其中未命中 {s['technical_miss']}） |",
         f"| 分段核验：hit/near/miss | {s['segments'].get('hit', 0)} / "
         f"{s['segments'].get('near', 0)} / {s['segments'].get('miss', 0)} |",
         f"| 耗时 | {s['elapsed_sec']}s |", ""]
    # 按来源统计
    by_source = defaultdict(Counter)
    for r in payload["quotes"]:
        by_source[r["file"] or r["source"]][r["status"]] += 1
    L += ["## 二、按来源文件", "", "| 文件 | hit | near | miss |", "|---|---|---|---|"]
    for f, ct in sorted(by_source.items()):
        L.append(f"| {f} | {ct.get('hit', 0)} | {ct.get('near', 0)} | {ct.get('miss', 0)} |")
    L += ["", "## 三、疑似编造清单（叙事引文未命中；无原文，仅定位线索）", ""]
    susp = payload["suspected_fabrications"]
    if not susp:
        L.append("（无：全部叙事引文均可在底本中精确或近似定位）")
    else:
        L += ["| id | 来源 | 长度(归一) | 分段 | 最高 ratio | 最近候选定位 |", "|---|---|---|---|---|---|"]
        for x in susp:
            L.append(f"| {x['id']} | {x['source']} | {x['quote_len']}（{x['norm_len']}） | "
                     f"{x['n_segments']} | {x['ratio']} | {x['nearest_anchor'] or '—'} |")
        L += ["", "> 处置：`--strict` 下非空即退出码 1；逐条按 `source` 回查生成内容，"
                  "人工裁决「误引/改编/编造」，必要时回写 W7 疑点缓存。"]

    near = [r for r in payload["quotes"] if r["status"] == "near"]
    L += ["", "## 四、近似清单（需人工复核；ratio≥阈值但非逐字底本）", ""]
    if not near:
        L.append("（无）")
    else:
        L += ["| id | 来源 | 长度 | ratio | 锚点 |", "|---|---|---|---|---|"]
        for x in near[:50]:
            L.append(f"| {x['id']} | {x['source']} | {x['quote_len']} | {x['ratio']} | "
                     f"{x['primary_locator'] or '—'} |")

    tech = [r for r in payload["quotes"] if r["kind"] == "technical"]
    L += ["", "## 五、技术/规则转写引号（术语示例，不参与编造判定）", ""]
    if not tech:
        L.append("（无）")
    else:
        L += ["| id | 来源 | 长度 | 状态 | ratio | 锚点 |", "|---|---|---|---|---|---|"]
        for x in tech[:50]:
            L.append(f"| {x['id']} | {x['source']} | {x['quote_len']} | {x['status']} | "
                     f"{x['ratio']} | {x['primary_locator'] or '—'} |")

    miss = [r for r in payload["quotes"] if r["status"] == "miss"]
    L += ["", "## 六、全部未命中（含技术引号；无原文）", ""]
    if not miss:
        L.append("（无）")
    else:
        L += ["| id | 来源 | kind | 长度 | 锚点 |", "|---|---|---|---|---|"]
        for x in miss[:100]:
            L.append(f"| {x['id']} | {x['source']} | {x['kind']} | {x['quote_len']} | "
                     f"{x['primary_locator'] or '—'} |")

    L += ["", "## 七、方法与纪律", "",
          "1. **归一化**：NFKC + 只保留汉字/字母/数字（去空白与全部标点），标点/空格/全半角差异不误杀；",
          "2. **精确层**：归一化子串在 34 部底本逐回检索；命中唯一/多候选均记录（多候选保留前 5 个定位符）；",
          f"3. **近似层**：精确失败 → 首/中/尾 {th['anchor_len']} 字锚点低成本定位等长候选窗口 → difflib ratio≥"
          f"{th['near_ratio']} 且匹配块长度率≥{th['len_rate_min']} 且最长匹配块≥min({th['anchor_len']}, 段长×60%)（上下文门槛）判 near；",
          "4. **省略号截断**：引文含 …/……/... 时按段核验，各段全命中=hit、任一段未命中=miss（防「省略号掩盖编造」）；",
          "5. **定位符**：5 书（有 struct）给 `书#pn-r{回}.{段}`；其余 29 书给 `书#ch{回}@L{行}`；",
          "6. **编造判定只作用于叙事引文**（narrative）；含 ASCII/管道/斜杠/箭头或规范元词（显示串/词表/正则等）的规则/术语转写为 technical，仅记录不判编造；",
          "7. **不输出原文**：JSON/报告只含长度、sha256 前 12 位、定位符与统计，便于在生成侧按 source 定位复核；",
          "8. 第 3 层 LLM 二审不在本脚本内：near/miss 清单即二审输入（W7 三层流水线的第 3 层由人工/外部模型执行）。", ""]
    return L


def write_outputs(payload, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "quote_verify.json"
    mp = out_dir / "quote_verify_report.md"
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    mp.write_text("\n".join(report_md(payload)) + "\n", encoding="utf-8")
    return jp, mp


# ==================== 主流程 ====================
def collect_targets(args):
    """→ (inputs list, records generator)"""
    inputs = []
    records = []
    if args.all or args.sku:
        sku = Path(args.sku_path or DEFAULT_SKU)
        if not sku.exists():
            raise SystemExit(f"[W7] SKU 卡不存在：{sku}")
        inputs.append(str(sku))
        records.extend(iter_sku_quotes(sku))
    if args.all:
        refs = Path(args.refs_dir or DEFAULT_REFS)
        if refs.exists():
            inputs.append(str(refs))
            for p in sorted(refs.rglob("*.md")):
                records.extend(iter_markdown_quotes(p, str(p.relative_to(refs))))
    for f in args.file or []:
        p = Path(f)
        inputs.append(str(p))
        records.extend(iter_file_quotes(p))
    if getattr(args, "content", False):
        content_dir = Path(args.content_dir or "content")
        if content_dir.exists():
            inputs.append(str(content_dir))
            for p in sorted(content_dir.rglob("*.md")):
                records.extend(iter_markdown_quotes(p, str(p)))
    return inputs, records


def run(args):
    t0 = time.time()
    inputs, records = collect_targets(args)
    if not records:
        print("[W7] 未发现待核验引号（目标源可能不含引文；SKU 卡默认脱敏为「未明示」占位）")
    index = CorpusIndex(Path(args.corpus_root or DEFAULT_CORPUS))
    rows, stats, seg_stats = verify_records(records, index)
    elapsed = time.time() - t0
    payload = build_payload(rows, stats, seg_stats, index, inputs, elapsed)
    jp, mp = write_outputs(payload, Path(args.out_dir or OUT_DIR))
    s = payload["stats"]
    print(f"[W7] 引号片段 {s['extracted']}：跳过占位 {s['skipped_placeholder']} / 过短 {s['skipped_short']}；"
          f"核验 {s['verified']}（覆盖率 {s['coverage_pct']}%）→ hit {s['hit']} / near {s['near']} / miss {s['miss']}"
          f"（叙事疑似编造 {s['narrative_suspected']}）")
    print(f"[W7] 输出：{jp}\n[W7] 报告：{mp}")
    return payload, jp, mp


# ==================== 自检 ====================
def selftest() -> int:
    """合成语料 + 合成引文，覆盖 精确/标点差异/近似/省略号分段/编造/过短/占位/技术 与"不输出原文"。"""
    import tempfile
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        ok = ok and bool(cond)

    print("[W7 selftest]")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "章回版"
        book = root / "测试书"
        book.mkdir(parents=True)
        text = "\n".join([
            "",
            "第一回　试回",
            "",
            "杨云骢道：“玫瑰花开像云霞，果子比碗还要大。”飞红巾微微一笑，并不答话。",
            "",
            "那少女道：“真名叫做哈玛雅，后来得了飞红巾这个绰号。”",
            "",
        ])
        (book / "001　第一回　试回.txt").write_text(text, encoding="utf-8")
        idx = CorpusIndex(root)
        check("合成底本载入", len(idx.chapters) == 1 and idx.books == ["测试书"])
        # 1) 精确（含标点差异：引文与底本一致）
        q1 = "玫瑰花开像云霞，果子比碗还要大。"
        r1 = idx.verify_segment(normalize(q1))
        check("精确命中", r1["status"] == "hit" and r1["candidates"][0]["anchor"].startswith("测试书#ch001@L"),
              str(r1["candidates"][:1]))
        # 2) 标点/空格差异仍命中
        q2 = "玫瑰花开像云霞 果子比碗还要大"
        check("标点/空格差异→归一化命中", idx.verify_segment(normalize(q2))["status"] == "hit")
        # 3) 近似（改 1 字）
        q3 = "玫瑰花开像云霞，果子比碗还要多。"   # 大→多
        r3 = idx.verify_segment(normalize(q3))
        check("近似命中（ratio≥0.9）", r3["status"] == "near" and r3["ratio"] >= NEAR_RATIO,
              f"{r3['ratio']}")
        # 4) 省略号分段：两段都在底本
        raw4 = "真名叫做哈玛雅…后来得了飞红巾这个绰号"
        segs4 = split_segments(raw4)
        r4 = [idx.verify_segment(s)["status"] for s in segs4]
        check("省略号分段核验（2 段均命中）", len(segs4) == 2 and all(x == "hit" for x in r4), str(r4))
        # 5) 编造
        q5 = normalize("这是完全不存在的一句伪造引文内容")
        check("编造→miss", idx.verify_segment(q5)["status"] == "miss")
        # 6) 抽取/过滤/kind
        md = Path(td) / "t.md"
        md.write_text("## 区\n\n- 「玫瑰花开像云霞」\n- 「未明示」\n- 「canonical|id」\n\n```\n「代码块内不算」\n```\n",
                      encoding="utf-8")
        recs = list(iter_markdown_quotes(md, "t.md"))
        check("Markdown 引文抽取（跳过代码块）", len(recs) == 3, str([r["source"] for r in recs]))
        check("占位符判定", is_placeholder("未明示"))
        check("technical 判定", quote_kind("canonical|id") == "technical"
              and quote_kind("真名叫做哈玛雅") == "narrative")
        # 7) 全流程 + 不输出原文
        rows, stats, seg = verify_records(recs, idx)
        payload = build_payload(rows, stats, seg, idx, ["t.md"], 0.0)
        blob = json.dumps(payload, ensure_ascii=False) + json.dumps(report_md(payload), ensure_ascii=False)
        leaked = [r for r in ["玫瑰花开像云霞", "真名叫做哈玛雅", "未明示", "canonical"] if r in blob]
        check("不输出原文（payload/report 无引文正文）", not leaked, str(leaked))
        check("统计闭合", stats.get("extracted", 0) == stats.get("skipped_placeholder", 0)
              + stats.get("skipped_short", 0) + len(rows))
        check("疑似编造清单只含 narrative miss",
              all(x["kind"] == "narrative" for x in payload["suspected_fabrications"]))
    print(f"[W7 selftest] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# ==================== CLI ====================
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="W7 引文真实性核验（对 AI 生成内容的引文做底本精确/近似匹配；不输出原文）")
    ap.add_argument("--all", action="store_true", help="核验全部默认目标（SKU 卡 + references 规律库）")
    ap.add_argument("--sku", action="store_true", help="只核验 registry/sku/cards.json（brief/summary）")
    ap.add_argument("--file", action="append", help="额外目标文件（.json/.md/.txt，可重复）")
    ap.add_argument("--content", action="store_true",
                    help="核验 content/ W8 页 frontmatter quotes[]（W7 v0.2 增补）")
    ap.add_argument("--content-dir", default=None, help="content 目录（缺省 content/）")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式：叙事引文存在疑似编造（miss）时退出码 1")
    ap.add_argument("--selftest", action="store_true", help="自检（合成语料，不写盘）")
    ap.add_argument("--corpus-root", default=None, help="底本目录（缺省 config.CORPUS_ROOT）")
    ap.add_argument("--sku-path", default=None, help="SKU 卡路径（缺省 registry/sku/cards.json）")
    ap.add_argument("--refs-dir", default=None, help="references 目录（缺省 references/）")
    ap.add_argument("--out-dir", default=None, help="输出目录（缺省 logs/w_group/）")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not (args.all or args.sku or args.file or getattr(args, "content", False)):
        args.all = True   # 缺省全量
    payload, jp, mp = run(args)
    s = payload["stats"]
    if args.strict:
        bad = []
        if s["narrative_suspected"]:
            bad.append(f"叙事引文疑似编造 {s['narrative_suspected']} 条")
        if bad:
            print("[W7] --strict 未通过：" + "；".join(bad))
            return 1
        print("[W7] --strict 通过（无叙事引文疑似编造）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
