#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N11 · 互文引用表 loc → loc_r 机锚回填 —— update_intertext_loc.py（D07 跨书治理 / D04 锚点）

背景与契约
----------
旧 KB `kb/互文引用表.json`（2026-10-31，34 书全量扫描，1,904 条互文边）的每条边带
`loc = "{chapter}:{line}"`（**源书**回号 : 该回底本文件内**绝对行号**，1-based；本轮以
真实数据反推并抽样验证：1,538/1,543 条可定位边的 snippet 在指定行命中，绝对行号口径成立）。
N11 负责把该粗定位升级为机读锚点（双锚体系，2026-11-05 收尾）：

    loc_r = "{book}#pn-r{chapter}.{para}"      （5 书 PN 锚；D04 格式，symbols.ANCHOR_FMT）
    loc_r = "{book}#ch{chapter}@L{line}"       （29 书行号锚；与 03d/W12 双 ID 同源）

数据源（只读）
--------------
1. `kb/互文引用表.json`            —— 输入边表（source/target/kind/probe/loc/snippet）；
2. `tagged/<书>/NNN.struct.md`      —— 5 书 PN 结构（回目 `# [0]`、围栏 `::: 类型`）；
3. `章回版/<书>/NNN*.txt`           —— 回底本行号（把 loc 的绝对行号映射到内容行）；
4. `registry/concordance/<书>.json` —— 书目/回号范围与 anchor_format 交叉校验。

回填算法（确定性，无 LLM；双锚体系 2026-11-05 收尾）
------------------------------------------------------
A. **PN 锚（5 书，有 struct）**：`loc_r = "{book}#pn-r{chapter}.{para}"`（D04 锚点格式；
   `symbols.ANCHOR_FMT`）。行号指纹 = 底本内容行 ↔ struct 内容行逐行对齐（生成器可逆性保证）。
B. **行号锚（其余 29 书，无 struct）**：`loc_r = "{book}#ch{chapter}@L{line}"`
   （与 03d/W12 双 ID 体系 `{book}.{chapter}.L{line}.s{n}` 同源；line = 底本文件绝对行号，
   与输入 `loc="{chapter}:{line}"` 同一口径）。规则：
   - 回文件：按数字文件名前缀定位（`{chapter:03d}*.txt`；不依赖中文回号兜底，
     避免"第一二○回"类中文数字解析失败）；chapter=0 仍支持楔子 `000*.txt`；
   - 行号校验：行号越界/空行/回目行 → 不直接锚定，退回**同回内容行文本检索**
     （probe + snippet 片段，长片段优先）：唯一命中 → 锚到命中行（校正 from_line 记录）；
     多候选 → **ambiguous**（保留候选列表）；无命中 → **unlocatable**；
   - 文本证据分级：行文本命中 probe/snippet=high；±2 行窗口命中=medium；
     行号精确但无文本证据=low（锚点仍按行号，标注 reason=line_snippet_mismatch）；
   - 行号锚无 PN，**置信上限 high/medium**；不冒充结构化 PN 锚。
C. 书范围：PN 范围 = 有 struct 的 5 书；行号范围 = 章回版全部 34 书（去重后 29 书无 struct）。
   任一 source 书不在两个范围 → unlocatable(reason=source_book_unknown)。

断言（写盘前）：PN 锚 `{book}#pn-r{ch}.{par}` / 行号锚 `{book}#ch{ch}@L{line}` 格式合法且
书=source；PN 锚回/段存在于 struct；行号锚回文件存在且行在文件范围内；resolved+ambiguous+
unlocatable == 边总数；ambiguous 不写 loc_r 且候选 ≥2。

产物
----
- `registry/intertext/intertext_loc.json` —— 边表副本 + loc_r/loc_status/resolution（含 stats）
- `logs/intertext/intertext_loc_report.md` —— 回填率/歧义/无法定位/按书按 kind 分布/断言
- `logs/intertext/intertext_loc_stats.json` —— 机器可读统计（供 N6/N10/E11 消费）

CLI
---
    python -X utf8 scripts/update_intertext_loc.py            # 默认回填并写盘（PN+行号双锚）
    python -X utf8 scripts/update_intertext_loc.py --dry-run  # 只算不写（打印统计）
    python -X utf8 scripts/update_intertext_loc.py --selftest # 自检（不写盘）
    python -X utf8 scripts/update_intertext_loc.py --books 七剑下天山,白发魔女传 --strict

退出码：0 成功；1 --strict 且存在超限歧义/无法定位/回填率低于 --min-rate；2 输入或断言失败。
（--strict 默认：全表回填率 ≥99.9%、无无法定位、歧义 ≤2 条——歧义清单仍逐条列出待人工。）
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import symbols  # noqa: E402

DEFAULT_INPUT = config.LEGACY_KB / "互文引用表.json"
OUT_JSON = config.DIR_REGISTRY / "intertext" / "intertext_loc.json"
LOG_DIR = config.DIR_LOGS / "intertext"
BACKUP_DIR = LOG_DIR / "_backup"
REPORT_MD = LOG_DIR / "intertext_loc_report.md"
STATS_JSON = LOG_DIR / "intertext_loc_stats.json"

ANCHOR_RE = re.compile(r"^(?P<book>[^#]+)#pn-r(?P<ch>\d+)\.(?P<par>\d+)$")
# 行号锚（29 书无 struct）：{book}#ch{chapter}@L{line}，与 03d/W12 双 ID 同源
LINE_ANCHOR_FMT = "{book}#ch{chapter}@L{line}"
LINE_ANCHOR_RE = re.compile(r"^(?P<book>[^#]+)#ch(?P<ch>\d+)@L(?P<line>\d+)$")
LOC_RE = re.compile(r"^\s*(?P<ch>\d{1,3})\s*[:：]\s*(?P<line>\d{1,6})\s*$")
TITLE_RE = re.compile(r"^\s*(?:第[一二三四五六七八九十百零〇\d]+回|楔子)")
PARA_RE = re.compile(r"^\[(\d+)\] (.*)$")
SNIPPET_SPLIT = "\u0001"   # 省略号替换符（临时，不入输出）
MIN_FRAGMENT = 6            # snippet 片段最短长度（像素级噪声过滤）
MAX_CANDIDATES_SHOWN = 12   # 歧义/不可定位样例候选数上限
LINE_WINDOW = 2             # 行号锚文本证据窗口（±2 行）


# ==================== 路径与书目 ====================
def tagged_books():
    """有 tagged 目录（struct 结构层）的书 → PN 锚范围。"""
    return sorted(p.name for p in config.DIR_TAGGED.iterdir()
                  if p.is_dir() and any(p.glob("*.struct.md")))


def line_books():
    """章回版全部书目（行号锚范围；含 5 书，5 书仍由 PN 锚优先处理）。"""
    root = Path(config.CORPUS_ROOT)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and any(p.glob("*.txt")))


def chapter_file_any(book: str, ch: int) -> Path:
    """行号锚专用回文件定位：按数字文件名前缀匹配。

    背景：`config.chapter_path` 的中文回号兜底对"第一二○回"这类混合中文数字会失败；
    本函数先按 `{ch:03d}*.txt` 前缀命中（覆盖 1-999 回），chapter=0 支持楔子 `000*.txt`，
    最后才回退 `config.chapter_path`。找不到抛 FileNotFoundError。
    """
    d = config.corpus_dir(book)
    if not d.exists():
        raise FileNotFoundError(f"{book} 无底本目录（{d}）")
    for pattern in (f"{ch:03d}*.txt", f"{ch}*.txt"):
        hits = sorted(d.glob(pattern))
        if hits:
            return hits[0]
    for p in sorted(d.glob("*.txt")):
        m = re.match(r"^(\d{1,3})", p.name)
        if m and int(m.group(1)) == ch:
            return p
    try:
        return config.chapter_path(book, ch)
    except Exception as exc:  # noqa: BLE001
        raise FileNotFoundError(f"{book} 第 {ch} 回底本未找到（{d}）") from exc


def raw_lines_any(book: str, ch: int):
    """→ (lines 列表, 文件 Path)：原始绝对行（1-based 索引 = 行号-1）。"""
    path = chapter_file_any(book, ch)
    return path.read_text(encoding="utf-8-sig").splitlines(), path


def chapter_raw_path(book: str, ch: int) -> Path:
    """回底本路径。七剑楔子为 `000*.txt`（行首无"第N回"），config.chapter_path 覆盖不到。"""
    if ch == 0:
        files = sorted(config.corpus_dir(book).glob("000*.txt"))
        if not files:
            raise FileNotFoundError(f"{book} 无 000 楔子底本")
        return files[0]
    return config.chapter_path(book, ch)


class LocError(Exception):
    """单条 loc 无法建立行号指纹（书/回/结构缺失）。"""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


# ==================== 行号指纹（底本行 ↔ PN） ====================
def raw_content_lines(book: str, ch: int):
    """→ [(绝对行号 1-based, 文本)]：跳过回目行与空行，保留其余内容行原始文本。"""
    path = chapter_raw_path(book, ch)          # FileNotFoundError → 调用方转 unlocatable
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    ti = next((i for i, ln in enumerate(lines) if TITLE_RE.match(ln)), None)
    start = (ti + 1) if ti is not None else 0
    return [(i + 1, lines[i]) for i in range(start, len(lines)) if lines[i].strip()], path.name


def struct_pn_lines(book: str, ch: int):
    """→ [(PN, 内容行文本)]（含围栏内续行；`# [0]` 回目行与 `:::` 围栏行不计）。"""
    sp = config.struct_path(book, ch)
    if not sp.exists():
        raise LocError("struct_missing", str(sp))
    out, cur = [], None
    for raw in sp.read_text(encoding="utf-8").split("\n"):
        s = raw.rstrip()
        if not s.strip() or s.startswith(":::") or s.startswith("# [0] "):
            continue
        m = PARA_RE.match(s)
        if m:
            cur = int(m.group(1))
            out.append((cur, m.group(2)))
        elif cur is not None:
            out.append((cur, s))       # 围栏内续行（多行诗/词/歌），归属首行 PN
    if not out:
        raise LocError("struct_empty", str(sp))
    return out


_CACHE = {}


def line_pn_index(book: str, ch: int):
    """构建并缓存 (book, ch) 的 {绝对行号→PN}, {PN→文本}, 内容行数。

    断言底本内容行序列与 struct 内容行序列逐行一致（PM 可逆性保证；不一致则拒绝回填该回，
    防"行号指纹"错位造成的假锚点）。
    """
    key = (book, ch)
    if key in _CACHE:
        return _CACHE[key]
    content, raw_name = raw_content_lines(book, ch)
    struct = struct_pn_lines(book, ch)
    if [t for _, t in content] != [t for _, t in struct]:
        raise LocError(
            "struct_content_mismatch",
            f"底本内容行 {len(content)} vs struct 内容行 {len(struct)}（{raw_name}）")
    line2pn = {abs_line: pn for (abs_line, _), (pn, _) in zip(content, struct)}
    pn_text = defaultdict(str)
    for pn, text in struct:
        pn_text[pn] += text
    info = {"raw_file": raw_name, "content_lines": len(content),
            "pn_count": len(pn_text), "chapter_title": content[0][1][:40] if content else ""}
    _CACHE[key] = (line2pn, dict(pn_text), info)
    return _CACHE[key]


# ==================== 解析工具 ====================
def parse_loc(loc: str):
    """`016:11` → (16, 11)；容忍全角冒号/空白；格式异常抛 ValueError。"""
    m = LOC_RE.match(loc or "")
    if not m:
        raise ValueError(f"loc 格式非法: {loc!r}（应如 '016:11'）")
    ch, line = int(m.group("ch")), int(m.group("line"))
    if line <= 0:
        raise ValueError(f"loc 行号必须 ≥1: {loc!r}")
    return ch, line


def build_anchor(book: str, ch: int, par: int) -> str:
    return symbols.ANCHOR_FMT.format(book=book, chapter=ch, para=par)


def build_line_anchor(book: str, ch: int, line: int) -> str:
    """行号锚：{book}#ch{chapter}@L{line}（03d/W12 双 ID 同源）。"""
    return LINE_ANCHOR_FMT.format(book=book, chapter=ch, line=line)


def parse_anchor(anchor: str):
    m = ANCHOR_RE.match(anchor or "")
    if not m:
        return None
    return m.group("book"), int(m.group("ch")), int(m.group("par"))


def parse_line_anchor(anchor: str):
    m = LINE_ANCHOR_RE.match(anchor or "")
    if not m:
        return None
    return m.group("book"), int(m.group("ch")), int(m.group("line"))


def snippet_fragments(edge: dict):
    """snippet 去省略号后 ≥MIN_FRAGMENT 字的片段，长片段优先（提高文本检索唯一性）。"""
    snip = edge.get("snippet") or ""
    frags = [f for f in snip.replace("…", SNIPPET_SPLIT).split(SNIPPET_SPLIT)
             if len(f) >= MIN_FRAGMENT]
    return sorted(set(frags), key=len, reverse=True)


def text_candidates(pn_text: dict, edge: dict):
    """在回内按 probe + snippet 片段检索候选 PN（长片段命中即收；probe 作补足）。"""
    frags = snippet_fragments(edge)
    cand = set()
    if frags:
        longest = frags[0]
        for pn, text in pn_text.items():
            if longest[:24] in text:
                cand.add(pn)
        if not cand:                      # 长片段不足 24 字或跨行，放宽到全部片段
            for pn, text in pn_text.items():
                if any(f[:12] in text for f in frags):
                    cand.add(pn)
    probe = (edge.get("probe") or "").strip()
    if probe:
        for pn, text in pn_text.items():
            if probe in text:
                cand.add(pn)
    return sorted(cand)


def verify_pn_text(pn_text: dict, pn: int, edge: dict):
    """校验锚点 PN 文本是否含 probe 或 snippet 片段 → (probe_match, snippet_match)。"""
    text = pn_text.get(pn, "")
    probe_match = bool(edge.get("probe")) and edge["probe"] in text
    frags = snippet_fragments(edge)
    snippet_match = any(f[:24] in text for f in frags) if frags else False
    return probe_match, snippet_match


# ==================== 行号锚（29 书无 struct） ====================
def line_text_match(text: str, edge: dict):
    """单行/窗口文本是否含 probe 或 snippet 片段 → 'probe' | 'snippet' | None。"""
    probe = (edge.get("probe") or "").strip()
    if probe and probe in text:
        return "probe"
    for frag in snippet_fragments(edge):
        if frag[:24] in text:
            return "snippet"
    return None


def line_content_lines(lines):
    """→ [(绝对行号, 文本)]：非空且非回目行（回目行作元数据，不作行号锚目标）。"""
    ti = next((i for i, ln in enumerate(lines) if TITLE_RE.match(ln)), None)
    out = []
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        if ti is not None and i == ti:
            continue
        out.append((i + 1, ln))
    return out


def search_line_candidates(lines, edge):
    """同回内容行文本检索（单行 + 相邻两行窗口）→ 候选绝对行号列表（去重升序）。"""
    content = line_content_lines(lines)
    hits = set()
    for ln_no, text in content:
        if line_text_match(text, edge):
            hits.add(ln_no)
    if hits:
        return sorted(hits)
    # 跨行 snippet：相邻两行拼接匹配（取起始行）
    for i in range(len(content) - 1):
        combined = content[i][1] + content[i + 1][1]
        if line_text_match(combined, edge):
            hits.add(content[i][0])
    return sorted(hits)


def resolve_line_edge(edge: dict, source: str, ch: int, line: int,
                      lines=None, raw_file: str | None = None) -> dict:
    """29 书无 struct → 行号锚决议：{book}#ch{ch}@L{line}（含文本证据分级/校正/歧义）。

    lines/raw_file 可注入（selftest 合成语料用）；缺省从章回版读取回文件。
    """
    res = {
        "status": "unlocatable", "method": None, "loc_r": None, "reason": None,
        "confidence": None, "candidates": [], "anchor_type": "line",
        "loc_chapter": ch, "loc_line": line, "line_is_content": False,
        "probe_match": False, "snippet_match": False, "matched": None,
        "line_corrected": False, "line_used": None,
    }
    if lines is None:
        try:
            lines, path = raw_lines_any(source, ch)
            raw_file = path.name
        except FileNotFoundError as exc:
            res.update(reason="chapter_not_found", detail=str(exc))
            return res
    res["raw_file"] = raw_file or "<synthetic>"
    ti = next((i for i, ln in enumerate(lines) if TITLE_RE.match(ln)), None)
    title_line = (ti + 1) if ti is not None else None
    in_range = 1 <= line <= len(lines)
    text = lines[line - 1] if in_range else ""
    valid_content = bool(in_range and text.strip() and line != title_line)
    res["line_is_content"] = valid_content
    if valid_content:
        kind = line_text_match(text, edge)
        if kind:
            res.update(status="resolved", method="loc_line", confidence="high",
                       matched="line", line_used=line,
                       probe_match=(kind == "probe"), snippet_match=(kind == "snippet"),
                       loc_r=build_line_anchor(source, ch, line),
                       candidates=[{"line": line, "anchor": build_line_anchor(source, ch, line),
                                    "match": kind}])
            return res
        window = "\n".join(lines[max(0, line - 1 - LINE_WINDOW):line + LINE_WINDOW])
        kind = line_text_match(window, edge)
        if kind:
            res.update(status="resolved", method="loc_line_window", confidence="medium",
                       matched="window", line_used=line,
                       probe_match=(kind == "probe"), snippet_match=(kind == "snippet"),
                       loc_r=build_line_anchor(source, ch, line),
                       candidates=[{"line": line, "anchor": build_line_anchor(source, ch, line),
                                    "match": kind}])
            return res
        # 行号有效但文本证据不足：仍按行号锚（低置信），标注原因
        res.update(status="resolved", method="loc_line", confidence="low",
                   matched=None, line_used=line,
                   loc_r=build_line_anchor(source, ch, line),
                   candidates=[{"line": line, "anchor": build_line_anchor(source, ch, line)}],
                   reason="line_snippet_mismatch")
        return res
    # 行号无效（空行/回目行/越界）→ 同回文本检索校正
    if not in_range:
        reason_base = "line_out_of_range"
    elif line == title_line:
        reason_base = "line_title"
    else:
        reason_base = "line_blank"
    cand = search_line_candidates(lines, edge)
    res["candidates"] = [{"line": ln, "anchor": build_line_anchor(source, ch, ln)} for ln in cand]
    if len(cand) == 1:
        ln = cand[0]
        res.update(status="resolved", method="text_unique_line", confidence="medium",
                   matched="text_search", line_used=ln, line_corrected=True,
                   loc_r=build_line_anchor(source, ch, ln),
                   reason=f"corrected_from_{reason_base}")
        return res
    if len(cand) >= 2:
        res.update(status="ambiguous", method="text_search_line", reason="multiple_candidates",
                   reason_detail=f"from_{reason_base}")
        return res
    res.update(reason=f"{reason_base}_no_text_match",
               detail=f"loc 行 {line} 非内容行，且 probe/snippet 在本回内容行无命中")
    return res


# ==================== 单边解析 ====================
def resolve_edge(edge: dict, books, line_scope=None):
    """→ 决议 dict：{status, method, loc_r, anchor_type(pn|line), candidates, ...}

    PN 范围（books=有 struct 的 5 书）→ PN 锚；行号范围（line_scope=章回版书目）→ 行号锚；
    都不在 → unlocatable(source_book_unknown)。
    """
    source = edge.get("source") or ""
    line_scope = line_books() if line_scope is None else line_scope
    res = {
        "status": "unlocatable", "method": None, "loc_r": None,
        "reason": None, "confidence": None, "candidates": [],
        "anchor_type": None, "loc_chapter": None, "loc_line": None,
        "line_is_content": False, "probe_match": False, "snippet_match": False,
        "matched": None, "line_corrected": False, "line_used": None,
        "target_in_scope": edge.get("target") in books,
    }
    try:
        ch, line = parse_loc(edge.get("loc"))
    except ValueError as exc:
        res.update(reason="loc_parse_error", detail=str(exc))
        return res
    res["loc_chapter"], res["loc_line"] = ch, line
    # ---- 行号锚范围：29 书（无 struct）----
    if source not in books:
        if source in line_scope:
            r = resolve_line_edge(edge, source, ch, line)
            r["target_in_scope"] = edge.get("target") in books
            return r
        res.update(reason="source_book_unknown",
                   detail=f"《{source}》不在 PN/行号锚范围内（PN {len(books)} 书 / 行号 {len(line_scope)} 书）")
        return res
    # ---- PN 锚范围：5 书（有 struct）----
    try:
        line2pn, pn_text, info = line_pn_index(source, ch)
    except FileNotFoundError as exc:
        res.update(reason="chapter_not_found", detail=str(exc))
        return res
    except LocError as exc:
        res.update(reason=exc.reason, detail=exc.detail)
        return res
    res["chapter_pn_count"] = info["pn_count"]
    # 1) 行号精确命中内容行 → 唯一候选
    pn = line2pn.get(line)
    if pn is not None:
        res["line_is_content"] = True
        anchor = build_anchor(source, ch, pn)
        probe_match, snippet_match = verify_pn_text(pn_text, pn, edge)
        verified = probe_match or snippet_match
        res.update(status="resolved", method="loc_line", loc_r=anchor, anchor_type="pn",
                   confidence="high" if verified else "low",
                   probe_match=probe_match, snippet_match=snippet_match,
                   matched=("probe" if probe_match else ("snippet" if snippet_match else None)),
                   candidates=[{"pn": pn, "anchor": anchor}],
                   reason=None if verified else "line_pn_snippet_mismatch")
        return res
    # 2) 行号指向回目/空行/越界 → 文本检索兜底
    cand = text_candidates(pn_text, edge)
    res["candidates"] = [{"pn": p, "anchor": build_anchor(source, ch, p)} for p in cand]
    if len(cand) == 1:
        probe_match, snippet_match = verify_pn_text(pn_text, cand[0], edge)
        res.update(status="resolved", method="text_unique", anchor_type="pn",
                   loc_r=build_anchor(source, ch, cand[0]), confidence="medium",
                   probe_match=probe_match, snippet_match=snippet_match,
                   matched=("probe" if probe_match else ("snippet" if snippet_match else None)))
        return res
    if len(cand) >= 2:
        res.update(status="ambiguous", method="text_search", reason="multiple_candidates",
                   confidence=None)
        return res
    res.update(reason="line_not_content_no_text_match",
               detail=f"loc 行 {line} 非内容行，且 probe/snippet 在本回无命中")
    return res


def strict_violations(stats, min_rate=0.999, max_ambiguous=2, max_unlocatable=0):
    """--strict 判据（可复跑）：回填率/无法定位/歧义上限。返回违规描述列表（空=通过）。"""
    bad = []
    if stats["ambiguous"] > max_ambiguous:
        bad.append(f"歧义 {stats['ambiguous']} 条 > 上限 {max_ambiguous}")
    if stats["unlocatable"] > max_unlocatable:
        bad.append(f"无法定位 {stats['unlocatable']} 条 > 上限 {max_unlocatable}")
    rate = stats.get("resolution_rate_in_scope", 0.0)
    if rate < min_rate:
        bad.append(f"全表回填率 {rate:.1%} < {min_rate:.1%}")
    return bad


# ==================== 主流程 ====================
def load_input(path: Path):
    if not path.exists():
        raise SystemExit(f"[N11] 输入不存在：{path}")
    payload = json.loads(io.open(path, encoding="utf-8").read())
    edges = payload.get("edges")
    if not isinstance(edges, list):
        raise SystemExit(f"[N11] 输入格式异常（缺 edges 列表）：{path}")
    return payload, edges


def run(input_path: Path, only_books=None, limit=None):
    payload, edges = load_input(input_path)
    books = tagged_books()
    line_scope = line_books()
    if only_books:                       # 调试：同时限定 PN/行号两个范围（其余书→source_book_unknown）
        books = [b for b in books if b in only_books]
        line_scope = [b for b in line_scope if b in only_books]
    if limit:
        edges = edges[:limit]
    # concordance 交叉校验（PN 书 anchor_format 与回号范围）
    concordance = {}
    for b in books:
        cp = config.DIR_REGISTRY / "concordance" / f"{b}.json"
        if cp.exists():
            cj = json.loads(io.open(cp, encoding="utf-8").read())
            concordance[b] = {"anchor_format": cj.get("anchor_format"),
                              "chapters": cj.get("chapters", [])}
    results = []
    for e in edges:
        r = resolve_edge(e, books, line_scope)
        row = dict(e)
        row["loc_r"] = r["loc_r"]
        row["loc_status"] = r["status"]
        row["anchor_type"] = r.get("anchor_type")
        row["resolution"] = {k: r.get(k) for k in
                             ("method", "reason", "confidence", "candidates", "anchor_type",
                              "loc_chapter", "loc_line", "line_is_content", "matched",
                              "line_corrected", "line_used", "probe_match", "snippet_match",
                              "target_in_scope")}
        if r["status"] == "ambiguous":
            if r.get("anchor_type") == "line":
                row["loc_r_candidates"] = [c["anchor"] for c in r["candidates"][:MAX_CANDIDATES_SHOWN]]
            else:
                row["loc_r_candidates"] = [c["anchor"] for c in r["candidates"][:MAX_CANDIDATES_SHOWN]]
        results.append(row)
    stats = compute_stats(results, edges, books, line_scope, concordance)
    return payload, results, stats


def compute_stats(results, edges, books, line_scope, concordance):
    status = Counter(r["loc_status"] for r in results)
    method = Counter((r["resolution"]["method"] or "-") for r in results)
    reasons = Counter((r["resolution"]["reason"] or "-") for r in results)
    anchor_types = Counter((r["resolution"].get("anchor_type") or "none") for r in results)
    resolved_anchor = Counter((r["resolution"].get("anchor_type") or "none")
                              for r in results if r["loc_status"] == "resolved")
    conf_by_anchor = defaultdict(Counter)
    line_quality = Counter()
    for r in results:
        if r["loc_status"] != "resolved":
            continue
        at = r["resolution"].get("anchor_type") or "none"
        conf_by_anchor[at][r["resolution"]["confidence"] or "?"] += 1
        if at == "line":
            line_quality[r["resolution"]["confidence"] or "?"] += 1
            if r["resolution"].get("line_corrected"):
                line_quality["corrected"] += 1
            if r["resolution"].get("reason") == "line_snippet_mismatch":
                line_quality["snippet_mismatch"] += 1
    by_book = defaultdict(Counter)
    for r in results:
        by_book[r.get("source", "?")][r["loc_status"]] += 1
    by_book_detail = {}
    for b, c in sorted(by_book.items()):
        total = sum(c.values())
        by_book_detail[b] = {
            "total": total,
            "resolved": c.get("resolved", 0),
            "ambiguous": c.get("ambiguous", 0),
            "unlocatable": c.get("unlocatable", 0),
            "rate": round(c.get("resolved", 0) / total, 4) if total else 0.0,
            "anchor_type": ("pn" if b in books else ("line" if b in line_scope else "none")),
        }
    by_kind = defaultdict(lambda: Counter())
    for r in results:
        by_kind[r.get("kind", "?")][r["loc_status"]] += 1
    total = len(results)
    resolved = status.get("resolved", 0)
    ambiguous = status.get("ambiguous", 0)
    unloc = status.get("unlocatable", 0)
    pn_scope_edges = sum(1 for r in results if r.get("source") in books)
    pn_only_resolved = sum(1 for r in results
                           if r.get("source") in books and r["loc_status"] == "resolved")
    target_in_scope = sum(1 for r in results if r["resolution"]["target_in_scope"])
    stats = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "schema": "intertext-loc-stats-v0.2",
        "input_edge_total": total,
        "anchor_format": {"pn": symbols.ANCHOR_FMT, "line": LINE_ANCHOR_FMT},
        "books_pn_scope": books,
        "books_line_scope": line_scope,
        "books_with_struct": books,                    # 兼容旧字段（= PN 范围）
        "books_with_edges": sorted(by_book),
        "pn_scope_edges": pn_scope_edges,
        "in_scope_edges": total,                        # 双锚后：全部边均在两类范围内的书
        "resolved": resolved,
        "ambiguous": ambiguous,
        "unlocatable": unloc,
        "resolution_rate_in_scope": round(resolved / total, 4) if total else 0.0,
        "resolution_rate_overall": round(resolved / total, 4) if total else 0.0,
        "anchor_types": dict(anchor_types),
        "resolved_by_anchor": dict(resolved_anchor),
        "confidence_by_anchor": {k: dict(v) for k, v in conf_by_anchor.items()},
        "line_anchor_quality": dict(line_quality),
        "by_status": dict(status),
        "by_method": dict(method),
        "unlocatable_reasons": dict(reasons),
        "by_source_book": by_book_detail,
        "by_kind": {k: dict(c) for k, c in sorted(by_kind.items())},
        "target_in_scope_edges": target_in_scope,
        "baseline_pn_only": {
            "description": "旧口径（仅 5 书 PN 锚，29 书 unlocatable）",
            "pn_scope_edges": pn_scope_edges,
            "resolved": pn_only_resolved,
            "rate_overall": round(pn_only_resolved / total, 4) if total else 0.0,
            "rate_in_scope": round(pn_only_resolved / pn_scope_edges, 4) if pn_scope_edges else 0.0,
        },
        "improvement": {
            "resolved_delta": resolved - pn_only_resolved,
            "rate_overall_delta": round((resolved - pn_only_resolved) / total, 4) if total else 0.0,
        },
        "concordance_checked": {b: {"anchor_format": c["anchor_format"],
                                    "chapters": len(c["chapters"])}
                                for b, c in concordance.items()},
    }
    return stats


def assertions(results, stats):
    """写盘前硬断言：双锚格式/存在性/文本证据/范围/计数闭合。返回 (ok, problems)。"""
    problems = []
    pn_books = set(stats["books_pn_scope"])
    line_scope = set(stats["books_line_scope"])
    status_count = Counter(r["loc_status"] for r in results)
    if (status_count.get("resolved", 0) + status_count.get("ambiguous", 0)
            + status_count.get("unlocatable", 0)) != len(results):
        problems.append("status 计数不闭合：resolved+ambiguous+unlocatable != 边总数")
    for r in results:
        anchor = r.get("loc_r")
        src = r.get("source")
        at = r.get("anchor_type")
        if r["loc_status"] == "resolved":
            if not anchor:
                problems.append(f"resolved 但无 loc_r：{src} {r.get('loc')}")
                continue
            if at == "pn":
                pa = parse_anchor(anchor)
                if pa is None:
                    problems.append(f"PN 锚格式非法：{anchor!r}")
                    continue
                book, ch, par = pa
                if book != src:
                    problems.append(f"PN 锚书与 source 不符：{anchor} vs {src}")
                if src not in pn_books:
                    problems.append(f"PN 锚但 source 不在 PN 范围：{src}")
                try:
                    line2pn, pn_text, info = line_pn_index(book, ch)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"PN 锚章节不可解析：{anchor}（{exc}）")
                    continue
                if par not in pn_text:
                    problems.append(f"PN 锚段号不存在：{anchor}")
                    continue
                pm, sm = verify_pn_text(pn_text, par, r)
                if not (pm or sm) and r["resolution"]["method"] == "text_unique":
                    problems.append(f"text_unique 锚点无文本证据：{anchor}")
            elif at == "line":
                pa = parse_line_anchor(anchor)
                if pa is None:
                    problems.append(f"行号锚格式非法：{anchor!r}")
                    continue
                book, ch, line = pa
                if book != src:
                    problems.append(f"行号锚书与 source 不符：{anchor} vs {src}")
                if src not in line_scope:
                    problems.append(f"行号锚但 source 不在行号范围：{src}")
                try:
                    lines, _ = raw_lines_any(book, ch)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"行号锚回文件不可读：{anchor}（{exc}）")
                    continue
                if not (1 <= line <= len(lines)):
                    problems.append(f"行号锚越界：{anchor}（文件 {len(lines)} 行）")
                    continue
                text = lines[line - 1]
                if not text.strip():
                    problems.append(f"行号锚指向空行：{anchor}")
                else:
                    ti = next((i for i, ln in enumerate(lines) if TITLE_RE.match(ln)), None)
                    if ti is not None and line == ti + 1:
                        problems.append(f"行号锚指向回目行：{anchor}")
                if r["resolution"]["method"] == "text_unique_line":
                    hit = search_line_candidates(lines, r)
                    if line not in hit:
                        problems.append(f"text_unique_line 锚点无文本证据：{anchor}")
            else:
                problems.append(f"resolved 但 anchor_type 非法：{at!r}（{src}）")
        elif r["loc_status"] == "ambiguous":
            if anchor:
                problems.append(f"ambiguous 不应写 loc_r：{src} {r.get('loc')}")
            if len(r.get("loc_r_candidates") or []) < 2:
                problems.append(f"ambiguous 候选 <2：{src} {r.get('loc')}")
        elif r["loc_status"] == "unlocatable":
            if anchor:
                problems.append(f"unlocatable 不应写 loc_r：{src} {r.get('loc')}")
        else:
            problems.append(f"未知 loc_status：{r['loc_status']}")
    # 范围：不在任何锚范围的书必须标 source_book_unknown；5 书必须走 PN 锚
    for r in results:
        src = r.get("source")
        if src not in pn_books and src not in line_scope:
            if r["resolution"]["reason"] != "source_book_unknown":
                problems.append(f"范围外源书未标 source_book_unknown：{src}")
        if src in pn_books and r["loc_status"] == "resolved":
            if r["resolution"].get("anchor_type") != "pn":
                problems.append(f"5 书 resolved 但非 PN 锚：{src}")
    # 统计口径
    if stats["resolved"] != status_count.get("resolved", 0):
        problems.append("stats.resolved 与结果不符")
    if sum(stats["resolved_by_anchor"].values()) != stats["resolved"]:
        problems.append("resolved_by_anchor 计数与 resolved 不符")
    return not problems, problems


def write_outputs(results, stats, payload, dry_run=False):
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "schema": "intertext-loc-v0.2",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": str(DEFAULT_INPUT.relative_to(config.ROOT.parent)
                      if DEFAULT_INPUT.is_relative_to(config.ROOT.parent) else DEFAULT_INPUT),
        "anchor_format": symbols.ANCHOR_FMT,
        "anchor_formats": {"pn": symbols.ANCHOR_FMT, "line": LINE_ANCHOR_FMT},
        "spec": "D07 跨书治理 / D04 锚点 / 03d·W12 双 ID；N11 update_intertext_loc（双锚：5 书 PN + 29 书行号）",
        "stats": stats,
        "edges": results,
    }
    lines = report_md(out)
    if dry_run:
        print(f"[N11] dry-run：不写盘（将输出 {OUT_JSON} / {REPORT_MD}）")
        print("\n".join(lines[:40]))
        return out
    if OUT_JSON.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(OUT_JSON, BACKUP_DIR / f"intertext_loc_{stamp}.json")
    io.open(OUT_JSON, "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, ensure_ascii=False, indent=2))
    io.open(STATS_JSON, "w", encoding="utf-8", newline="\n").write(
        json.dumps(stats, ensure_ascii=False, indent=2))
    io.open(REPORT_MD, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print(f"[N11] 写出：{OUT_JSON}\n[N11] 报告：{REPORT_MD}\n[N11] 统计：{STATS_JSON}")
    return out


def report_md(out):
    s = out["stats"]
    edges = out["edges"]
    pn_only = s["baseline_pn_only"]
    imp = s["improvement"]
    total = s["input_edge_total"]
    rate = s["resolution_rate_overall"]
    line = [
        "# 互文引用表 loc → loc_r 机锚回填报告（N11 · 双锚体系）", "",
        f"- 生成：{out['generated']}；schema：`{out['schema']}`",
        f"- 规范：D07 跨书治理 / D04 锚点 / 03d·W12 双 ID；"
        f"PN 锚 `{s['anchor_format']['pn']}`；行号锚 `{s['anchor_format']['line']}`",
        f"- 输入：`{out['source']}`（{total} 条互文边）",
        f"- 锚范围：PN 锚 {len(s['books_pn_scope'])} 书（" + "、".join(s["books_pn_scope"]) + "）；"
        f"行号锚范围 {len(s['books_line_scope'])} 书（5 书由 PN 优先，其余 29 书无 struct 走行号锚）",
        f"- 结论：**resolved {s['resolved']} / {total}（{s['resolution_rate_in_scope']:.2%}）**，"
        f"较旧口径 PN-only {pn_only['resolved']} 条（{pn_only['rate_overall']:.1%}）"
        f"提升 **+{imp['resolved_delta']} 条（+{imp['rate_overall_delta']:.1%}）**", "",
        "## 一、前后对比（核心）", "",
        "| 口径 | resolved | 可定位率（全表） | 说明 |", "|---|---|---|---|",
        f"| 旧口径：仅 5 书 PN 锚（29 书 unlocatable） | {pn_only['resolved']} | "
        f"{pn_only['rate_overall']:.2%} | 对应 2026-11-05 17:51 首版 |",
        f"| **新口径：PN + 行号双锚** | **{s['resolved']}** | **{rate:.2%}** | "
        f"5 书仍 PN（{s['resolved_by_anchor'].get('pn', 0)} 条）；29 书行号锚（{s['resolved_by_anchor'].get('line', 0)} 条） |",
        f"| 增量 | **+{imp['resolved_delta']}** | **+{imp['rate_overall_delta']:.2%}** | — |", "",
        "## 二、锚类型与置信度分布", "",
        "| 锚类型 | resolved | 说明 |", "|---|---|---|",
        f"| PN 锚 `#pn-r{{回}}.{{段}}` | {s['resolved_by_anchor'].get('pn', 0)} | 5 书（struct 可逆性逐行对齐） |",
        f"| 行号锚 `#ch{{回}}@L{{行}}` | {s['resolved_by_anchor'].get('line', 0)} | 29 书（底本绝对行号 + 文本证据分级） |",
        f"| 无锚（ambiguous/unlocatable） | {s['ambiguous'] + s['unlocatable']} | "
        f"ambiguous {s['ambiguous']} / unlocatable {s['unlocatable']} |", "",
        "| 置信度 | PN 锚 | 行号锚 | 说明 |", "|---|---|---|---|",
    ]
    for conf in ("high", "medium", "low"):
        line.append(f"| {conf} | {s['confidence_by_anchor'].get('pn', {}).get(conf, 0)} | "
                    f"{s['confidence_by_anchor'].get('line', {}).get(conf, 0)} | "
                    + {"high": "行文本/PN 文本命中 probe/snippet",
                       "medium": "±2 行窗口命中或同回文本唯一校正",
                       "low": "行号精确但文本证据不足（仅行号锚）"}[conf] + " |")
    line += ["", "| 行号锚质量 | 条数 |", "|---|---|",
             f"| 行文本命中（loc_line, high） | {s['confidence_by_anchor'].get('line', {}).get('high', 0)} |",
             f"| 文本唯一校正（text_unique_line, medium） | {s['by_method'].get('text_unique_line', 0)} |",
             f"| ±2 行窗口命中（loc_line_window） | {s['by_method'].get('loc_line_window', 0)} |",
             f"| 文本证据不足（low，仍回填） | {s['confidence_by_anchor'].get('line', {}).get('low', 0)} |",
             f"| 行号校正（blank/title/oob→文本唯一行） | {s['line_anchor_quality'].get('corrected', 0)} |",
             f"| 行号精确但 snippet 不匹配 | {s['line_anchor_quality'].get('snippet_mismatch', 0)} |", "",
             "## 三、按 source 书回填率", "",
             "| 书 | 总边 | resolved | ambiguous | unlocatable | 回填率 | 锚类型 |", "|---|---|---|---|---|---|---|"]
    for b, c in s["by_source_book"].items():
        line.append(f"| {b} | {c['total']} | {c['resolved']} | {c['ambiguous']} | "
                    f"{c['unlocatable']} | {c['rate']:.1%} | {c['anchor_type']} |")
    line += ["", "## 四、按互文级别（kind）", "", "| kind | resolved | ambiguous | unlocatable |", "|---|---|---|---|"]
    for k, c in s["by_kind"].items():
        line.append(f"| {k} | {c.get('resolved', 0)} | {c.get('ambiguous', 0)} | {c.get('unlocatable', 0)} |")
    line += ["", "## 五、方法与原因分布", "", "| 方法 | 条数 |", "|---|---|"]
    for m, c in sorted(s["by_method"].items(), key=lambda x: (x[0] == "-", x[0])):
        line.append(f"| {'（无方法，unlocatable）' if m == '-' else m} | {c} |")
    line += ["", "## 六、未回填原因分布（ambiguous + unlocatable）", "", "| reason | 条数 |", "|---|---|"]
    for r, c in sorted(s["unlocatable_reasons"].items(), key=lambda x: -x[1]):
        if r == "-":
            continue
        line.append(f"| {r} | {c} |")
    amb = [r for r in edges if r["loc_status"] == "ambiguous"]
    line += ["", "## 七、歧义清单", ""]
    if not amb:
        line.append("（无歧义：每条边唯一锚定）")
    else:
        line += ["| source | loc | kind | 候选 |", "|---|---|---|---|"]
        for r in amb[:30]:
            line.append(f"| {r['source']} | {r['loc']} | {r['kind']} | "
                        f"{'、'.join(r.get('loc_r_candidates') or [])} |")
    un = [r for r in edges if r["loc_status"] == "unlocatable"]
    line += ["", "## 八、无法定位清单", ""]
    if not un:
        line.append("（无：全部边均建立锚点）")
    else:
        line += ["| source | loc | kind | reason |", "|---|---|---|---|"]
        for r in un[:50]:
            line.append(f"| {r['source']} | {r['loc']} | {r['kind']} | {r['resolution']['reason']} |")
    line += ["", "## 九、样例（前 20 条；PN 与行号锚混合）", "",
             "| # | source | loc | kind | loc_r | 校验 |", "|---|---|---|---|---|---|"]
    n = 0
    for r in edges:
        if r["loc_status"] != "resolved":
            continue
        n += 1
        res = r["resolution"]
        check = "+".join(x for x in (("probe" if res.get("probe_match") else ""),
                                     ("snippet" if res.get("snippet_match") else "")) if x) or (res.get("matched") or "line")
        line.append(f"| {n} | {r['source']} | {r['loc']} | {r['kind']} | `{r['loc_r']}` | "
                    f"{r['anchor_type']}·{check}{'·校正' if res.get('line_corrected') else ''} |")
        if n >= 20:
            break
    line += ["", "## 十、断言与校验", "",
             "- PN 锚格式 `{book}#pn-r{ch}.{par}`（与 `symbols.ANCHOR_FMT`、concordance anchor_format 一致）；"
             "行号锚格式 `{book}#ch{ch}@L{line}`（与 03d/W12 双 ID 同源）",
             "- resolved 逐条回查：书=source；PN 锚回/段存在于 struct；行号锚回文件存在且行在范围内、"
             "目标行非空非回目行；text_unique(_line) 必须有文本证据",
             "- resolved + ambiguous + unlocatable == 边总数；ambiguous 不写 loc_r 且候选 ≥2",
             "- **5 书 resolved 必须为 PN 锚**（规则强制）；行号锚不冒充结构化 PN",
             "- 行号锚文本证据分级：high（行命中）/medium（±2 行窗口/文本唯一校正）/low（仅行号）", "",
             "## 十一、说明 / 遗留", "",
             f"1. 全表 {total} 条：PN 锚 {s['resolved_by_anchor'].get('pn', 0)} 条（5 书），"
             f"行号锚 {s['resolved_by_anchor'].get('line', 0)} 条（29 书）；"
             f"ambiguous {s['ambiguous']} 条、unlocatable {s['unlocatable']} 条（详见 §七/§八）。",
             "2. 行号锚为**过渡锚**：29 书无 tagged/struct，无法生成 PN；行号锚给出可机读、可回查的底本行定位，"
             "待这些书建 struct 后可重跑本脚本，行号锚可升级为 PN 锚（保留 loc_r 兼容旧消费）。",
             "3. 行号锚不携带原文，只给 `书#ch回@L行`；页面/消费侧如需展示证据，仍须走 W7/版权闸门（引文核验）。",
             "4. `--strict` 判据：全表回填率 ≥99.9%、无法定位 ≤0、歧义 ≤2（歧义清单逐条列出待人工；"
             "超限即退出码 1；阈值可用 --min-rate/--max-ambiguous/--max-unlocatable 调整）。",
             "5. 下游：N6 merge_crossover / N10 SKU / E11 series_tree 消费 `registry/intertext/intertext_loc.json`；"
             "行号锚消费方须支持 `#chN@LN` 格式（03d/W12 双 ID 约定）。"]
    return line


# ==================== 自检 ====================
def selftest() -> int:
    """自检：解析/锚点/候选逻辑（合成用例）+ 现网数据不变量（不写盘）。"""
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        ok = ok and bool(cond)

    print("[N11 selftest]")
    # 1) loc 解析
    check("parse_loc 正常", parse_loc("016:11") == (16, 11))
    check("parse_loc 全角冒号", parse_loc("007：3") == (7, 3))
    for bad in ("", "abc", "16-11", "016:0", "016:"):
        try:
            parse_loc(bad)
            check(f"parse_loc 非法输入应报错 {bad!r}", False)
        except ValueError:
            check(f"parse_loc 非法输入报错 {bad!r}", True)
    # 2) 锚点格式
    a = build_anchor("七剑下天山", 16, 5)
    check("anchor 格式", a == "七剑下天山#pn-r16.5", a)
    check("anchor 可反解", parse_anchor(a) == ("七剑下天山", 16, 5))
    check("anchor 非法串返回 None", parse_anchor("七剑下天山#r16.5") is None)
    # 3) snippet 片段 / 候选 / 校验（合成）
    edge = {"probe": "塞外奇侠传", "snippet": "…往事（详见拙著《塞外奇侠传》一书）。这些往事…"}
    frags = snippet_fragments(edge)
    check("snippet 片段提取", bool(frags) and all(len(f) >= MIN_FRAGMENT for f in frags),
          f"{len(frags)} 片段")
    pn_text = {1: "无关段落", 2: "往事（详见拙著《塞外奇侠传》一书）", 3: "另一段"}
    cand = text_candidates(pn_text, edge)
    check("文本候选唯一", cand == [2], str(cand))
    check("PN 文本校验", verify_pn_text(pn_text, 2, edge)[0] is True)
    pn_text2 = {1: "《塞外奇侠传》在此", 2: "又见《塞外奇侠传》"}
    check("文本候选多候选", text_candidates(pn_text2, edge) == [1, 2])
    # 4) 行号锚（29 书）合成用例：格式/分级/校正/歧义/无法定位
    la = build_line_anchor("狂侠天骄魔女", 12, 34)
    check("行号锚格式", la == "狂侠天骄魔女#ch12@L34", la)
    check("行号锚可反解", parse_line_anchor(la) == ("狂侠天骄魔女", 12, 34))
    check("行号锚非法串返回 None", parse_line_anchor("狂侠天骄魔女#pn-r12.34") is None)
    lines = ["第一回　测试回", "", "他道：“详见《塞外奇侠传》一书。”", "另一段无关内容。",
             "再一段：详见《塞外奇侠传》的往事。"]
    le = {"probe": "塞外奇侠传", "snippet": "…详见《塞外奇侠传》一书…", "loc": "001:3"}
    r = resolve_line_edge(le, "测试书", 1, 3, lines=lines, raw_file="001.txt")
    check("行号锚：行文本命中→high", r["status"] == "resolved" and r["confidence"] == "high"
          and r["loc_r"] == "测试书#ch1@L3" and r["method"] == "loc_line", str(r))
    r2 = resolve_line_edge({"probe": "另一段无关内容"}, "测试书", 1, 2, lines=lines)  # 空行→文本唯一
    check("行号锚：空行校正→text_unique_line", r2["status"] == "resolved"
          and r2["method"] == "text_unique_line" and r2["line_corrected"] is True, str(r2))
    r3 = resolve_line_edge({"probe": "无关词"}, "测试书", 1, 99, lines=lines)  # 越界无命中
    check("行号锚：越界无命中→unlocatable", r3["status"] == "unlocatable"
          and r3["reason"] == "line_out_of_range_no_text_match", str(r3))
    r4 = resolve_line_edge({"probe": "另一段无关内容"}, "测试书", 1, 99, lines=lines)  # 越界+唯一命中
    check("行号锚：越界校正→resolved", r4["status"] == "resolved" and r4["line_corrected"] is True, str(r4))
    r5 = resolve_line_edge({"probe": "塞外奇侠传"}, "测试书", 1, 1, lines=lines)  # 回目行→两候选
    check("行号锚：回目行多候选→ambiguous", r5["status"] == "ambiguous"
          and len(r5["candidates"]) >= 2, str(r5["candidates"]))
    # 4b) --strict 判据（合成统计）
    fake = {"ambiguous": 1, "unlocatable": 0, "resolution_rate_in_scope": 0.9995}
    check("strict：歧义/不可定位在限内→通过", strict_violations(fake) == [])
    check("strict：无法定位超限→失败",
          any("无法定位" in x for x in strict_violations({**fake, "unlocatable": 1})))
    check("strict：回填率不足→失败",
          any("回填率" in x for x in strict_violations({**fake, "resolution_rate_in_scope": 0.98})))
    check("strict：歧义超限→失败",
          any("歧义" in x for x in strict_violations({**fake, "ambiguous": 5})))
    # 5) 现网数据不变量（只读）
    if DEFAULT_INPUT.exists():
        payload, edges = load_input(DEFAULT_INPUT)
        check("现网输入可读且含 edges", len(edges) > 0, f"{len(edges)} 条")
        books = tagged_books()
        check("可回填书目非空", len(books) > 0, "、".join(books))
        conc = config.DIR_REGISTRY / "concordance"
        check("concordance 目录存在", conc.is_dir())
        for b in books:
            cp = conc / f"{b}.json"
            if cp.exists():
                cj = json.loads(io.open(cp, encoding="utf-8").read())
                check(f"concordance anchor_format ({b})",
                      cj.get("anchor_format") == symbols.ANCHOR_FMT, cj.get("anchor_format"))
        # 抽样：前 200 条双锚均可解析并生成合法锚点
        payload, results, stats = run(DEFAULT_INPUT, limit=200)
        res_ok = True
        for r in results:
            if r["loc_status"] != "resolved":
                continue
            if r["anchor_type"] == "pn":
                pa = parse_anchor(r["loc_r"])
                res_ok = res_ok and bool(pa) and pa[0] == r["source"]
            elif r["anchor_type"] == "line":
                pa = parse_line_anchor(r["loc_r"])
                res_ok = res_ok and bool(pa) and pa[0] == r["source"]
            else:
                res_ok = False
        check("抽样 resolved 锚点格式/书籍与 source 一致（PN+行号）", res_ok)
        check("抽样锚类型合法", all((r["loc_status"] != "resolved")
                              or r["anchor_type"] in ("pn", "line") for r in results))
        check("统计闭合（抽样）", stats["resolved"] + stats["ambiguous"]
              + stats["unlocatable"] == len(results))
        check("抽样含 PN 锚", stats["resolved_by_anchor"].get("pn", 0) >= 1,
              str(stats["resolved_by_anchor"]))
        ok_all, problems = assertions(results, stats)
        check("抽样断言通过", ok_all, "；".join(problems[:3]))
    else:
        check("现网输入存在（跳过现网不变量）", True, "输入缺失")
    print(f"[N11 selftest] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


# ==================== CLI ====================
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="N11 互文引用表 loc→loc_r 机锚回填（D07/D04；只读 kb/tagged，不写 tagged）")
    ap.add_argument("--input", default=str(DEFAULT_INPUT), help="互文引用表 JSON（缺省 kb/互文引用表.json）")
    ap.add_argument("--books", default=None,
                    help="调试：同时限定 PN/行号锚范围（逗号分隔；缺省=5 书 PN + 全部章回版行号）")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 条（调试）")
    ap.add_argument("--dry-run", action="store_true", help="只计算不写盘")
    ap.add_argument("--selftest", action="store_true", help="自检（不写盘）")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式：超限歧义/无法定位或全表回填率 < --min-rate 时退出码 1")
    ap.add_argument("--min-rate", type=float, default=0.999,
                    help="--strict 下全表最低回填率（默认 0.999）")
    ap.add_argument("--max-ambiguous", type=int, default=2,
                    help="--strict 允许的歧义上限（默认 2；歧义清单仍逐条报告）")
    ap.add_argument("--max-unlocatable", type=int, default=0,
                    help="--strict 允许的无法定位上限（默认 0）")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    books = [b.strip() for b in args.books.split(",")] if args.books else None
    payload, results, stats = run(Path(args.input), only_books=books, limit=args.limit)
    ok, problems = assertions(results, stats)
    if not ok:
        print("[N11] 断言失败，禁止写盘：")
        for p in problems[:20]:
            print("  -", p)
        return 2
    out = write_outputs(results, stats, payload, dry_run=args.dry_run)
    print(f"[N11] 边 {stats['input_edge_total']}：resolved {stats['resolved']} / "
          f"ambiguous {stats['ambiguous']} / unlocatable {stats['unlocatable']}"
          f"（全表回填率 {stats['resolution_rate_in_scope']:.2%}；"
          f"旧 PN-only {stats['baseline_pn_only']['resolved']} 条 "
          f"{stats['baseline_pn_only']['rate_overall']:.2%}）")
    print(f"[N11] 锚分布：{stats['resolved_by_anchor']}；行号锚质量：{stats['line_anchor_quality']}")
    if args.strict:
        bad = strict_violations(stats, args.min_rate, args.max_ambiguous, args.max_unlocatable)
        if bad:
            print("[N11] --strict 未通过：" + "；".join(bad))
            return 1
        print("[N11] --strict 通过（无超限歧义/无法定位，回填率达标）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
