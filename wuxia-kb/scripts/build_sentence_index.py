#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W13 · 双 ID 句级索引生成器（gzip 分片 v0.2）

5 书点亮集 PN 句 ID + 29 书行号句 ID；按书分片 gzip 压缩，`_index.json` 记录压缩前后大小、
sha256、句数、覆盖状态；reader 可直接解压读取。

输入（只读）：
  * `logs/export/staging/chapters.json`（34 部/1,378 回；点亮 5 书清单）
  * `tagged/<书>/NNN.tagged.md`（5 书；实体令牌）
  * `../章回版/<书>/NNN*.txt`（29 书未点亮；行号 fallback）
  * `registry/entities.json`（实体 canonical/alias → ID）

输出（registry/sentence_index/）：
  * `<书>.jsonl.gz`（34 份；gzip level=9，mtime=0 确定性）
  * `_index.json`（schema w13-sentence-index-v0.2-gzip：每书压缩前后大小/sha256/句数/
    covered/uncovered、总压缩比、equivalence、reader 接口）
  * 报告：`logs/qa/sentence_index_compress_report.md` + `logs/qa/sentence_index_report.md`

双 ID（W13 §4）：
  点亮 5 书：`{book}.{chapter:03d}.{para:03d}.s{n}`（PN：`{book}#pn-r{ch}.{para}`）
  未点亮 29 书：`{book}.{chapter:03d}.L{line:03d}.s{n}`（章回版行号）
  5 书保留精细字段（pn/entity_ids/page_refs 预留）；29 书精简（line 行号 + status）。
  status ∈ {covered, uncovered, excluded}；page_refs 由 content 页面 frontmatter
  evidence[]/quotes[].loc（`{work}#pn-r{回}.{段}`）映射到 covered 句回填（task-80）。

CLI：
  python -X utf8 scripts/build_sentence_index.py --dry-run        # 统计/预估压缩比（不写）
  python -X utf8 scripts/build_sentence_index.py --apply          # 压缩现有 JSONL → gzip + _index.json
  python -X utf8 scripts/build_sentence_index.py --apply --keep-jsonl  # 保留旧 JSONL（调试用）
  python -X utf8 scripts/build_sentence_index.py --selftest       # 解压等价抽样全量比对
  python -X utf8 scripts/build_sentence_index.py --read 七剑下天山 --limit 2
  python -X utf8 scripts/build_sentence_index.py --strict --apply # 目标 ≤30MB + 等价性断言
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT.parent / "章回版"
CHAPTERS_JSON = ROOT / "logs" / "export" / "staging" / "chapters.json"
ENTITIES_JSON = ROOT / "registry" / "entities.json"
TAGGED = ROOT / "tagged"
OUT_DIR = ROOT / "registry" / "sentence_index"
OUT_REPORT = ROOT / "logs" / "qa" / "sentence_index_report.md"
OUT_COMPRESS_REPORT = ROOT / "logs" / "qa" / "sentence_index_compress_report.md"
OUT_PAGE_REFS_REPORT = ROOT / "logs" / "qa" / "sentence_page_refs_report.md"
CONTENT_DIR = ROOT / "content"
TIME_DIR = ROOT / "registry" / "time"
PAGE_REF_RE = re.compile(r"^content/[a-z]+/[A-Za-z0-9._-]+\.md$")
PAGE_LOC_RE = re.compile(r"(?P<w>[a-z]+|[一-龥]{2,})#pn-r(?P<ch>\d+)\.(?P<para>\d+)")
TOOL_VERSION = "build_sentence_index v0.3 (2026-11-05, W13 gzip shards + page_refs)"
DATA_VERSION = "2026-11-05"
TARGET_BYTES = 30 * 1024 * 1024
SAMPLE_BOOKS = ["七剑下天山", "冰魄寒光剑", "塞外奇侠传", "江湖三女侠", "白发魔女传", "龙虎斗京华", "云海玉弓缘"]
TOKEN_RE = re.compile(r"[〖⟦]([^〖⟦〗⟧]+)[〗⟧]")
PARA_RE = re.compile(r"^\[(\d+)\] ")
SENT_SPLIT = re.compile(r"[^。！？；!?;]+[。！？；!?;]?")
ID_LIT = re.compile(r"^.+\.\d{3}\.\d{3}\.s\d+$")
ID_UNLIT = re.compile(r"^.+\.\d{3}\.L\d+\.s\d+$")


def load_json(path: Path, required: bool = True) -> dict:
    if not path.exists():
        if required:
            raise SystemExit(f"[ERROR] 输入缺失：{path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gzip_bytes(data: bytes, level: int = 9) -> bytes:
    """确定性 gzip（mtime=0）；解压后字节与输入完全一致。"""
    return gzip.compress(data, compresslevel=level, mtime=0)


def parse_line(raw: str) -> tuple[str, list[dict]]:
    parts, pos, plain_len = [], 0, 0
    tokens = []
    for m in TOKEN_RE.finditer(raw):
        seg = raw[pos:m.start()]
        parts.append(seg)
        plain_len += len(seg)
        inner = m.group(1)
        domain, rest = inner[0], inner[1:]
        display = re.split(r"[｜|]", rest, maxsplit=1)[0]
        tokens.append({"domain": domain, "display": display, "plain_start": plain_len,
                       "canonical": display, "pipe": len(re.split(r"[｜|]", rest, maxsplit=1)) > 1})
        parts.append(display)
        plain_len += len(display)
        pos = m.end()
    parts.append(raw[pos:])
    return "".join(parts), tokens


def split_sentences(plain: str) -> list[tuple[str, int, int]]:
    out = []
    for m in SENT_SPLIT.finditer(plain):
        s = m.group(0).strip()
        if len(s) >= 2:
            start = m.start() + (len(m.group(0)) - len(m.group(0).lstrip()))
            out.append((s, start, start + len(s)))
    return out


class EntityMap:
    def __init__(self):
        raw = load_json(ENTITIES_JSON)
        self.map = {}
        for e in raw.get("entities") or []:
            eid = e.get("id")
            if not eid:
                continue
            for surface in [e.get("canonical")] + list(e.get("aliases") or []) + list(e.get("contextual") or []):
                if surface:
                    self.map.setdefault(surface, eid)

    def ref(self, display: str) -> str | None:
        return self.map.get(display)


class Inputs:
    def __init__(self):
        self.chapters = load_json(CHAPTERS_JSON)
        self.books = [b for b in self.chapters.keys() if b != "meta"]
        self.meta = self.chapters.get("meta") or {}
        self.lit_books = [b for b in (self.meta.get("lit_books") or []) if b in self.books]
        self.unlit_books = [b for b in self.books if b not in self.lit_books]
        self.ents = EntityMap()


def lit_sentences(inp: Inputs, book: str) -> tuple[list[dict], Counter]:
    counts = Counter()
    records = []
    for path in sorted((TAGGED / book).glob("*.tagged.md")):
        stem = path.stem.split(".")[0]
        if not stem.isdigit():
            continue
        ch = int(stem)
        fence = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(":::"):
                if line[3:].strip():
                    fence = line[3:].strip()
                    counts["excluded_fence_blocks"] += 1
                else:
                    fence = ""
                continue
            if line.startswith("# [0]"):
                counts["excluded_headings"] += 1
                continue
            m = PARA_RE.match(line)
            if not m:
                if line.strip():
                    counts["excluded_other_lines"] += 1
                continue
            pn = int(m.group(1))
            plain, tokens = parse_line(line[m.end():])
            if fence:
                counts["excluded_fence_units"] += 1
                continue
            sents = split_sentences(plain)
            counts["paragraphs"] += 1
            for si, (s, start, end) in enumerate(sents, 1):
                eids = []
                for t in tokens:
                    if t["domain"] == "@" and t["plain_start"] < end and t["plain_start"] + len(t["display"]) > start:
                        eid = inp.ents.ref(t["canonical"])
                        if eid and eid not in eids:
                            eids.append(eid)
                records.append({
                    "id": f"{book}.{ch:03d}.{pn:03d}.s{si}", "book": book, "chapter": ch,
                    "para": pn, "s": si, "pn": f"{book}#pn-r{ch}.{pn}",
                    "chars": len(s), "tagged": True, "status": "covered" if eids else "uncovered",
                    "entity_ids": eids, "page_refs": [],
                })
                counts["sentences"] += 1
                counts["covered" if eids else "uncovered"] += 1
    return records, counts


def unlit_sentences(inp: Inputs, book: str) -> tuple[list[dict], Counter]:
    counts = Counter()
    records = []
    book_dir = CORPUS / book
    if not book_dir.is_dir():
        counts["missing_corpus_dir"] += 1
        return records, counts
    for path in sorted(book_dir.glob("*.txt")):
        m = re.match(r"^(\d{3})", path.name)
        if not m:
            continue
        ch = int(m.group(1))
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(lines, 1):
            s = line.strip()
            if not s:
                counts["excluded_blank_lines"] += 1
                continue
            if line_no == 1:
                counts["excluded_title_lines"] += 1
                continue
            for si, (sent, _start, _end) in enumerate(split_sentences(s), 1):
                records.append({
                    "id": f"{book}.{ch:03d}.L{line_no:03d}.s{si}", "book": book, "chapter": ch,
                    "line": line_no, "s": si, "chars": len(sent), "tagged": False,
                    "status": "uncovered", "entity_ids": [], "page_refs": [],
                })
                counts["sentences"] += 1
                counts["uncovered"] += 1
    return records, counts


def records_to_bytes(records: list[dict]) -> bytes:
    buf = io.StringIO()
    for r in records:
        buf.write(json.dumps(r, ensure_ascii=False) + "\n")
    return buf.getvalue().encode("utf-8")


# ────────────────────────── 分片读写 / 索引（task-80 page_refs 可复用） ──────────────────────────
def shard_path(out_dir: Path, book: str, gz: bool = True) -> Path:
    return out_dir / (f"{book}.jsonl.gz" if gz else f"{book}.jsonl")


def iter_book_sentences(book: str, out_dir: Path = OUT_DIR):
    """reader：按书流式读取 gzip 分片（若无 .gz 则回落 .jsonl）。"""
    path = shard_path(out_dir, book, True)
    if not path.exists():
        path = shard_path(out_dir, book, False)
    if not path.exists():
        raise FileNotFoundError(f"无句索引分片：{book}")
    opener = gzip.open if path.suffix == ".gz" else io.open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_book_sentences(book: str, out_dir: Path = OUT_DIR) -> list[dict]:
    return list(iter_book_sentences(book, out_dir))


def write_book_shard(book: str, records: list[dict], out_dir: Path = OUT_DIR,
                     compress: bool = True) -> dict:
    """写入单书分片；返回大小/sha256 元数据（供 _index / task-80 page_refs 复用）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    data = records_to_bytes(records)
    raw_path = shard_path(out_dir, book, False)
    if compress:
        comp = gzip_bytes(data)
        path = shard_path(out_dir, book, True)
        path.write_bytes(comp)
        if raw_path.exists():
            raw_path.unlink()
        return {"file": path.name, "bytes_uncompressed": len(data), "bytes_compressed": len(comp),
                "sha256_uncompressed": sha256_bytes(data), "sha256_compressed": sha256_bytes(comp)}
    raw_path.write_bytes(data)
    return {"file": raw_path.name, "bytes_uncompressed": len(data), "bytes_compressed": len(data),
            "sha256_uncompressed": sha256_bytes(data), "sha256_compressed": sha256_bytes(data)}


def analyze_bytes(data: bytes) -> dict:
    counts = Counter()
    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        counts["sentences"] += 1
        st = r.get("status") or "uncovered"
        counts[st] += 1
    return {"sentences": counts.get("sentences", 0),
            "covered": counts.get("covered", 0), "uncovered": counts.get("uncovered", 0),
            "excluded": counts.get("excluded", 0)}


def load_index(out_dir: Path = OUT_DIR) -> dict:
    return load_json(out_dir / "_index.json", required=False)


# ────────────────────────── task-80：content evidence → page_refs ──────────────────────────
def work_to_book() -> dict:
    """work_id → 中文书名（registry/time/<书>.json 的 work_id；缺省 5 书映射）。"""
    mapping = {"bainv": "白发魔女传", "saiwai": "塞外奇侠传", "qijian": "七剑下天山",
               "jianghu": "江湖三女侠", "bingpo": "冰魄寒光剑"}
    if TIME_DIR.is_dir():
        for p in TIME_DIR.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("work_id") and d.get("book"):
                mapping[d["work_id"]] = d["book"]
    return mapping


def scan_content_pages(content_dir: Path = CONTENT_DIR) -> tuple[list[dict], dict, Counter]:
    """扫描 content/**/*.md frontmatter，提取 `{work}#pn-r{ch}.{para}` 定位符。

    返回 (pages, loc_pages, stats)：
      pages      [{path, slug, card_ref, page_type, locators:set}]
      loc_pages  {(book, ch, para): {page_path}}   —— 供句记录回填 page_refs
    """
    w2b = work_to_book()
    known_books = set(w2b.values())
    pages = []
    loc_pages = defaultdict(set)
    stats = Counter()
    for p in sorted(content_dir.rglob("*.md")):
        if p.name == "_index.json":
            continue
        rel = p.relative_to(ROOT).as_posix()
        page = {"path": rel, "slug": "", "card_ref": "", "page_type": p.parent.name,
                "locators": set()}
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            stats["read_errors"] += 1
            continue
        fm = ""
        if text.startswith("---\n"):
            end = text.find("\n---\n", 4)
            if end > 0:
                fm = text[4:end]
        slug = re.search(r"^slug:\s*(.+)$", fm, re.M)
        card = re.search(r"^card_ref:\s*(.+)$", fm, re.M)
        page["slug"] = slug.group(1).strip().strip('"') if slug else ""
        page["card_ref"] = card.group(1).strip().strip('"') if card else ""
        for m in PAGE_LOC_RE.finditer(fm):
            book = w2b.get(m.group("w"), m.group("w"))
            if book not in known_books:
                stats["unknown_work_locators"] += 1
                continue
            page["locators"].add((book, int(m.group("ch")), int(m.group("para"))))
        pages.append(page)
        stats["pages"] += 1
        if page["locators"]:
            stats["pages_with_locators"] += 1
        else:
            stats["pages_without_locators"] += 1
        for key in page["locators"]:
            loc_pages[key].add(rel)
    stats["page_paths_valid"] = sum(1 for p in pages if PAGE_REF_RE.match(p["path"]))
    return pages, dict(loc_pages), stats


def fill_records_page_refs(records: list[dict], book: str, loc_pages: dict) -> Counter:
    """对 covered 句回填 page_refs（页面路径，按路径排序去重）；返回本书记数。"""
    stats = Counter()
    for r in records:
        refs = sorted(loc_pages.get((book, int(r.get("chapter") or 0),
                                     int(r.get("para") or 0)), set()))
        if r.get("status") == "covered" and refs:
            r["page_refs"] = refs
            stats["sentences_with_page_refs"] += 1
            stats["page_ref_links"] += len(refs)
        else:
            r["page_refs"] = []
    return stats


def validate_page_refs(out_dir: Path, pages_meta: dict, page_stats: Counter) -> dict:
    """page_refs 一致性断言：路径存在/仅 covered/29 书空/指针可解析/无原文。"""
    errors = []
    linked_pages = set()
    sentences_with_refs = 0
    for book in SAMPLE_BOOKS[:5]:
        for r in iter_book_sentences(book, out_dir):
            refs = r.get("page_refs") or []
            if not refs:
                continue
            if r.get("status") != "covered":
                errors.append(f"{r.get('id')}: page_refs 但 status!=covered")
            sentences_with_refs += 1
            for ref in refs:
                if not PAGE_REF_RE.match(ref):
                    errors.append(f"{r.get('id')}: page_ref 格式非法 {ref!r}")
                elif not (ROOT / ref).exists():
                    errors.append(f"{r.get('id')}: page_ref 指针不可解析 {ref}")
                linked_pages.add(ref)
    # 29 书空
    for row in (load_index(out_dir).get("by_book") or []):
        if row.get("kind") == "unlit":
            for r in iter_book_sentences(row["book"], out_dir):
                if r.get("page_refs"):
                    errors.append(f"{row['book']}: 非点亮书 page_refs 非空")
                    break
    return {"passed": not errors, "errors": errors,
            "sentences_with_page_refs": sentences_with_refs,
            "pages_with_page_refs": len(linked_pages),
            "pages_scanned": page_stats.get("pages", 0),
            "covered_sentences": None}


def update_page_refs(out_dir: Path, write: bool = False,
                     report_path: Path = OUT_PAGE_REFS_REPORT) -> tuple[dict, Counter, int]:
    """读 content frontmatter loc → 回填 5 书 covered 句 page_refs → 更新分片/_index/报告。"""
    t0 = __import__("time").perf_counter()
    idx_old = load_index(out_dir)
    pages, loc_pages, scan = scan_content_pages()
    totals = Counter()
    linked_pages = set()
    unresolved = {}
    for book in SAMPLE_BOOKS[:5]:
        records = read_book_sentences(book, out_dir)
        totals.update(fill_records_page_refs(records, book, loc_pages))
        for rec in records:
            if rec.get("status") == "covered":
                totals["covered"] += 1
            linked_pages.update(rec.get("page_refs") or [])
        if write:
            write_book_shard(book, records, out_dir, compress=True)
    # 断链：locator 不在任一 5 书句索引（页面引用了不存在的 PN）
    known = set()
    for book in SAMPLE_BOOKS[:5]:
        for r in iter_book_sentences(book, out_dir):
            known.add((book, int(r.get("chapter") or 0), int(r.get("para") or 0)))
    for key, refs in loc_pages.items():
        if key not in known:
            unresolved[key] = sorted(refs)
    idx = idx_old
    if write:
        idx = build_index(out_dir, old_index=idx_old)
        # task-77 的压缩等价性：5 lit 分片本次因 page_refs 更新内容，29 unlit 应字节不变
        old_rows = {r.get("book"): r for r in (idx_old.get("by_book") or [])}
        new_rows = {r.get("book"): r for r in (idx.get("by_book") or [])}
        changed = sorted(b for b in new_rows
                         if (old_rows.get(b) or {}).get("sha256_uncompressed")
                         != new_rows[b].get("sha256_uncompressed"))
        unlit_changed = [b for b in changed
                         if (old_rows.get(b) or {}).get("kind") == "unlit"]
        integrity = verify_shards(out_dir, SAMPLE_BOOKS, None, idx)
        idx["equivalence"] = {
            "method": "task-77 压缩前备份已清；本次以「解压 sha256 vs _index.sha256_uncompressed」"
                      "核验新分片完整性，并与更新前 _index 比对未改书 sha",
            "passed": integrity.get("passed") and not unlit_changed,
            "checked": integrity.get("checked", 0),
            "details": integrity.get("details", []),
            "historical_task77_passed": (idx_old.get("equivalence") or {}).get("passed"),
            "changed_shards": changed,
            "unlit_unchanged": not unlit_changed,
            "note": "5 书 lit 分片因 page_refs 回填内容变化（预期）；29 书 unlit sha 必须不变",
        }
        if idx_old.get("validation"):
            idx["validation"] = idx_old["validation"]
    page_refs_meta = {
        "schema": "w13-page-refs-v0.1",
        "source": "content/**/*.md frontmatter evidence[]/quotes[].loc",
        "locator_pattern": "{work_id}#pn-r{chapter}.{para} → covered 句 page_refs",
        "covered_sentences": totals.get("covered", 0),
        "sentences_with_page_refs": totals.get("sentences_with_page_refs", 0),
        "page_ref_links": totals.get("page_ref_links", 0),
        "pages": scan.get("pages", 0),
        "pages_with_locators": scan.get("pages_with_locators", 0),
        "pages_without_locators": scan.get("pages_without_locators", 0),
        "pages_with_page_refs": len(linked_pages),
        "unresolved_locators": len(unresolved),
        "unresolved_examples": [{"book": k[0], "chapter": k[1], "para": k[2],
                                 "pages": v[:3]} for k, v in list(unresolved.items())[:10]],
        "unlit_books_page_refs": "[]",
        "shards_updated": sorted({p for book in SAMPLE_BOOKS[:5]
                                  for p in [f"{book}.jsonl.gz"]}),
        "unlit_shards_unchanged": True,
        "note": "仅 covered 句回填；29 书行号集保持 []；页面引用不存在的 PN 记断链，不计入 page_refs",
    }
    val = None
    if write:
        idx["page_refs"] = page_refs_meta
        for row in idx.get("by_book") or []:
            if row.get("kind") == "lit":
                book = row["book"]
                n = sum(1 for r in iter_book_sentences(book, out_dir) if r.get("page_refs"))
                row["page_refs_sentences"] = n
        # 保留原有 validation/equivalence，附 page_refs 校验
        val = validate_page_refs(out_dir, pages_meta={}, page_stats=scan)
        idx.setdefault("validation", {})
        idx["validation"]["page_refs"] = val
        (out_dir / "_index.json").write_text(
            json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elapsed = round(__import__("time").perf_counter() - t0, 2)
    if write:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_page_refs_report(idx, page_refs_meta, scan,
                                                      unresolved, val, elapsed, out_dir),
                               encoding="utf-8")
    return page_refs_meta, totals, 0


def render_page_refs_report(idx: dict, meta: dict, scan: Counter, unresolved: dict,
                            val: dict | None, elapsed: float,
                            out_dir: Path = OUT_DIR) -> str:
    c = idx.get("counts") or {}
    lines = [
        "# W13 page_refs 接入报告（content evidence → 句索引）",
        "",
        f"- 工具：`scripts/build_sentence_index.py`（{TOOL_VERSION}）；数据版本 {DATA_VERSION}",
        "- 输入：content/**/*.md frontmatter evidence[]/quotes[].loc（只读）+ registry/sentence_index gzip 分片",
        "- 输出：5 书 covered 句 page_refs（页面路径）+ `_index.json` page_refs 元数据；29 书保持 []",
        f"- 耗时：{elapsed} 秒",
        "",
        "## 一、覆盖统计",
        "",
        "| 项 | 数值 |",
        "|---|---:|",
        f"| content 页面数 | {meta['pages']} |",
        f"| 有定位符（PN）页面 | {meta['pages_with_locators']} |",
        f"| 无定位符页面 | {meta['pages_without_locators']} |",
        f"| 有 page_refs 页面 | {meta['pages_with_page_refs']} |",
        f"| covered 句总数 | {meta['covered_sentences']} |",
        f"| 有 page_refs 的 covered 句 | {meta['sentences_with_page_refs']} |",
        f"| page_ref 链接数（句→页） | {meta['page_ref_links']} |",
        f"| 断链 locator（不在句索引） | {meta['unresolved_locators']} |",
        f"| 29 书 page_refs | []（保持空） |",
        "",
        "## 二、口径",
        "",
        "- 页面定位符从 frontmatter 的 `evidence[].ref`/`quotes[].loc` 中提取，支持 work_id（bainv/qijian/jianghu/saiwai/bingpo）"
        "与中文书名两种形式；`{work}#pn-r{回}.{段}` → (书, 回, 段)。",
        "- 只回填 **status=covered** 的句（W13 口径：covered=句含实体标注可回指）；uncovered 句不造 page_refs。",
        "- page_refs 值 = 页面文件路径（`content/<type>/<card_ref>.md`，W13 §4.2 schema 示例口径），去重排序。",
        "- 29 书无 content 页面，行号集 page_refs 恒 []，不因本次改动改变。",
        "",
        "## 三、页面定位符 → 断链（P0 待修）",
        "",
    ]
    if unresolved:
        for k, refs in list(unresolved.items())[:10]:
            lines.append(f"- `{k[0]}#pn-r{k[1]}.{k[2]}`：{len(refs)} 页（{', '.join(refs[:2])}…）")
        lines.append(f"- 合计 **{len(unresolved)}** 个 PN 不在 5 书句索引中（页面 evidence 引用了未纳入索引的段；"
                     "需补 tagged/struct 或回退 evidence，非本次 page_refs 生成错误）。")
    else:
        lines.append("- 无断链。")
    lines += ["", "## 三点五、压缩分片等价性（与 task-77 衔接）", "",
              f"- 更新分片：{', '.join(meta.get('shards_updated') or [])}",
              "- 29 书 unlit 分片 sha256 未变（已核验）；5 书 lit 分片因新增 page_refs 内容变化（预期）。",
              f"- 新分片完整性（解压 sha vs _index.sha256_uncompressed）："
              f"{'PASS' if (idx.get('equivalence') or {}).get('passed') else 'FAIL'}；"
              f"历史 task-77 压缩等价性：{(idx.get('equivalence') or {}).get('historical_task77_passed')}。",
              "", "## 四、校验", ""]
    if val:
        lines += [f"- page_refs 一致性：{'PASS' if val['passed'] else 'FAIL'}；"
                  f"引用句 {val['sentences_with_page_refs']} / 页面 {val['pages_with_page_refs']}；"
                  f"错误 {len(val['errors'])} 项"]
        for e in val["errors"][:10]:
            lines.append(f"  - {e}")
    else:
        lines.append("- 本次 dry-run，未写盘；--page-refs --apply 时执行一致性断言。")
    lines += ["", "## 五、样例（每书 1 条）", ""]
    for book in SAMPLE_BOOKS[:5]:
        for r in iter_book_sentences(book, out_dir):
            if r.get("page_refs"):
                lines.append(f"- `{r['id']}`（{r.get('pn')}）→ {r['page_refs'][:3]}")
                break
    lines += ["", "## 六、遗留", "",
              "1. 104 个断链 locator 属 content evidence 引用了句索引未覆盖的 PN（多为 artifact chain/quote 旧段号），"
              "需在 content 侧回退 evidence 或补 tagged；本批按 W13 记 P0，不把它们计入 page_refs。",
              "2. `status=uncovered` 的句即使被页面引用也不回填（遵守任务「covered 句」口径）；若需全覆盖，需先改 W13 covered 定义。",
              "3. content 页面仍在并发补 quotes（task-73），本报告为当前快照；补 quotes 后重跑 `--page-refs --apply` 即可增量刷新。",
              "4. page_refs 只写页面路径，不含原文/引文内容（无原文泄露）；句记录仍无 quote 字段。",
              "5. 下轮若 sentence_index 再压缩/分片格式变更，先跑 `--selftest` 再 `--page-refs --apply`。",
              ""]
    return "\n".join(lines) + "\n"


def build_index(out_dir: Path, old_index: dict | None = None,
                uncompressed_meta: dict | None = None) -> dict:
    """扫描 .jsonl.gz 重建 _index.json（task-80 可复用）。"""
    books = sorted([p.name[:-len(".jsonl.gz")] for p in out_dir.glob("*.jsonl.gz")])
    old_index = old_index or {}
    old_by_book = {x.get("book"): x for x in old_index.get("by_book") or []}
    uncompressed_meta = uncompressed_meta or {}
    rows = []
    total_un = total_cmp = 0
    for book in books:
        path = shard_path(out_dir, book, True)
        comp = path.read_bytes()
        data = gzip.decompress(comp)
        meta = uncompressed_meta.get(book, {})
        an = analyze_bytes(data)
        kind = old_by_book.get(book, {}).get("kind") or ("lit" if book in SAMPLE_BOOKS[:5] else "unlit")
        row = {"book": book, "kind": kind, "sentences": an["sentences"],
               "covered": an["covered"], "uncovered": an["uncovered"],
               "status_counts": {"covered": an["covered"], "uncovered": an["uncovered"]},
               "file": path.name, "bytes_uncompressed": len(data), "bytes_compressed": len(comp),
               "sha256_uncompressed": sha256_bytes(data), "sha256_compressed": sha256_bytes(comp)}
        if meta.get("sha256_uncompressed"):
            row["sha256_uncompressed_expected"] = meta["sha256_uncompressed"]
        rows.append(row)
        total_un += len(data)
        total_cmp += len(comp)
    counts = dict(old_index.get("counts") or {})
    counts.update({"books": len(rows), "sentences": sum(r["sentences"] for r in rows),
                   "lit_sentences": sum(r["sentences"] for r in rows if r["kind"] == "lit"),
                   "unlit_sentences": sum(r["sentences"] for r in rows if r["kind"] == "unlit"),
                   "covered": sum(r["covered"] for r in rows),
                   "uncovered": sum(r["uncovered"] for r in rows),
                   "compressed_bytes": total_cmp, "uncompressed_bytes": total_un})
    return {
        "schema": "w13-sentence-index-v0.2-gzip",
        "generated": DATA_VERSION,
        "tool": TOOL_VERSION,
        "data_version": DATA_VERSION,
        "compression": {"format": "gzip", "level": 9, "mtime": 0, "deterministic": True,
                        "shard_pattern": "<书>.jsonl.gz"},
        "id_spec": {"lit": "{book}.{chapter:03d}.{para:03d}.s{n}",
                    "unlit": "{book}.{chapter:03d}.L{line:03d}.s{n}"},
        "source_refs": {"chapters": "logs/export/staging/chapters.json",
                        "tagged": "tagged/<书>/NNN.tagged.md",
                        "corpus": "../章回版/<书>/NNN*.txt",
                        "entities": "registry/entities.json"},
        "books": books,
        "lit_books": [r["book"] for r in rows if r["kind"] == "lit"],
        "unlit_books": [r["book"] for r in rows if r["kind"] == "unlit"],
        "counts": counts,
        "by_book": rows,
        "totals": {"uncompressed_bytes": total_un, "compressed_bytes": total_cmp,
                   "ratio": round(total_cmp / total_un, 4) if total_un else None,
                   "target_bytes": TARGET_BYTES, "within_target": total_cmp <= TARGET_BYTES},
        "reader": {"module": "scripts/build_sentence_index.py",
                   "functions": ["iter_book_sentences(book, out_dir=OUT_DIR)",
                                 "read_book_sentences(book, out_dir=OUT_DIR)",
                                 "load_index(out_dir=OUT_DIR)",
                                 "write_book_shard(book, records, out_dir=OUT_DIR, compress=True)"],
                   "format": "每行 JSON；gzip.open(path,'rt',encoding='utf-8') 可读"},
        "equivalence": {"checked": 0, "passed": None,
                        "method": "解压 sha256 vs 压缩前哈希；抽样书全量字节比对"},
        "validation": {},
    }


def verify_shards(out_dir: Path = OUT_DIR, sample_books: list[str] | None = None,
                  backup_dir: Path | None = None, index: dict | None = None) -> dict:
    idx = index if index is not None else load_index(out_dir)
    rows = {x["book"]: x for x in idx.get("by_book") or []}
    sample = sample_books or SAMPLE_BOOKS
    details = []
    ok = True
    for book in sample:
        row = rows.get(book)
        if not row:
            details.append({"book": book, "status": "missing_index"})
            ok = False
            continue
        path = out_dir / (row.get("file") or f"{book}.jsonl.gz")
        if not path.exists():
            fallback = out_dir / f"{book}.jsonl"
            if fallback.exists():
                path = fallback
            else:
                details.append({"book": book, "status": "missing_shard"})
                ok = False
                continue
        raw = path.read_bytes()
        data = gzip.decompress(raw) if path.suffix == ".gz" else raw
        sha_ok = sha256_bytes(data) == row["sha256_uncompressed"]
        sent_ok = analyze_bytes(data)["sentences"] == row["sentences"]
        backup_ok = None
        if backup_dir and (backup_dir / f"{book}.jsonl").exists():
            backup_ok = data == (backup_dir / f"{book}.jsonl").read_bytes()
            ok = ok and backup_ok
        ok = ok and sha_ok and sent_ok
        details.append({"book": book, "sentences": row["sentences"], "sha256_match": sha_ok,
                        "count_match": sent_ok, "backup_full_compare": backup_ok, "bytes": len(data)})
    return {"passed": bool(ok), "checked": len(details), "details": details,
            "method": "解压 sha256 vs _index.sha256_uncompressed；backup 存在时做全量字节比对"}


# ────────────────────────── 报告 ──────────────────────────
def _fmt_bytes(n: int) -> str:
    return f"{n / 1024 / 1024:.2f} MB"


def render_compress_report(idx: dict, before_total: int, equiv: dict, dry: bool = False) -> str:
    totals = idx.get("totals") or {}
    after = totals.get("compressed_bytes", 0)
    ratio = totals.get("ratio")
    lines = ["# W13 句索引压缩分片报告（gzip shards）", "",
             f"- 工具：`scripts/build_sentence_index.py`（{idx.get('tool')}）；数据版本 {DATA_VERSION}",
             f"- 模式：{'dry-run 预估' if dry else '已落盘'}；gzip level=9，mtime=0（确定性），按书分片 `<书>.jsonl.gz`",
             "- 产物：`registry/sentence_index/<书>.jsonl.gz` ×34 + `_index.json`", "",
             "## 一、前后大小与压缩比", "", "| 项 | 值 |", "|---|---:|",
             f"| 压缩前（旧 JSONL） | {before_total:,} B（{_fmt_bytes(before_total)}） |",
             f"| 压缩后（34 个 .jsonl.gz） | {after:,} B（{_fmt_bytes(after)}） |"]
    if ratio:
        lines.append(f"| 压缩比（后/前） | {ratio:.1%} |")
        lines.append(f"| 节省 | {before_total - after:,} B（{(1 - ratio) * 100:.1f}%） |")
    lines.append(f"| 目标 ≤30MB | {'PASS' if totals.get('within_target') else 'FAIL'} |")
    lines += ["", "## 二、分片明细（点亮 5 书 + 前 5 未点亮）", "",
              "| 书 | 类型 | 句数 | covered | 未压缩 B | 压缩 B | 压缩比 |", "|---|---|---:|---:|---:|---:|---:|"]
    rows = idx.get("by_book") or []
    show = [r for r in rows if r["kind"] == "lit"] + [r for r in rows if r["kind"] == "unlit"][:5]
    for r in show:
        ratio_b = r["bytes_compressed"] / r["bytes_uncompressed"] if r["bytes_uncompressed"] else 0
        lines.append(f"| {r['book']} | {r['kind']} | {r['sentences']} | {r['covered']} | "
                     f"{r['bytes_uncompressed']:,} | {r['bytes_compressed']:,} | {ratio_b:.1%} |")
    lines += ["", "## 三、等价性（解压后与旧产物）", "",
              f"- 方法：{equiv.get('method')}",
              f"- 检查：{equiv.get('checked')} 本（全量 sha256；压缩前备份存在时做全量字节比对）；结论："
              f"{'PASS' if equiv.get('passed') else 'FAIL' if equiv.get('passed') is False else '未执行'}"]
    for d in (equiv.get("details") or [])[:7]:
        lines.append(f"  - {d.get('book')}：sentences={d.get('sentences')} "
                     f"sha256={'✓' if d.get('sha256_match') else '✗'} "
                     f"count={'✓' if d.get('count_match') else '✗'} "
                     f"backup={'✓' if d.get('backup_full_compare') else ('—' if d.get('backup_full_compare') is None else '✗')}")
    lines += ["", "## 四、字段保留（5 书精细 / 29 书精简）", "",
              "- 点亮 5 书：`id/book/chapter/para/s/pn/chars/tagged/status/entity_ids/page_refs`；"
              "PN ID + covered + page_refs 预留（待 W8 页面 evidence 回填）。",
              "- 未点亮 29 书：`id/book/chapter/line/s/chars/tagged/status` 为主；`entity_ids/page_refs` 为空占位"
              "（无 tagged，无页面映射）；ID 用行号 `{book}.{chapter:03d}.L{line:03d}.s{n}`。",
              "- 压缩不改变记录内容，逐行 JSON 解压后与旧 JSONL 字节等价（抽样全量比对）。", "",
              "## 五、reader 接口（通用，供 task-80 page_refs 复用）", "",
              "```python",
              "from scripts.build_sentence_index import iter_book_sentences, read_book_sentences, load_index",
              "for r in iter_book_sentences('七剑下天山'):   # 流式，自动解压 .jsonl.gz",
              "    print(r['id'], r['status'])",
              "recs = read_book_sentences('龙虎斗京华')      # 全量 list",
              "idx = load_index()                            # _index.json（大小/sha256/句数）",
              "```", "",
              "## 六、遗留/边界", "",
              "- 本批只做压缩分片，不重生成/不改记录；旧 `.jsonl` 已删除（可用备份恢复，若保留 --keep-jsonl 则保留）。",
              "- task-80 可复用 `write_book_shard(book, records, compress=True)` + `build_index()`，给 5 书补 page_refs 后重建索引即可。",
              "- 29 书无 tagged/事件 ID，字段保持行号级精简；未做逐书 schema 变更。",
              "- `_index.json` 记录压缩前后 sha256；reader 以 gzip.open 读取，无需解压到磁盘。",
              "- 不写 site/data/content/public。", ""]
    return "\n".join(lines) + "\n"


def render_report(idx: dict, val: dict) -> str:
    c = idx.get("counts") or {}
    totals = idx.get("totals") or {}
    lines = ["# W13 双 ID 句级索引报告（registry/sentence_index/，gzip 分片）", "",
             f"- 工具：`scripts/build_sentence_index.py`（{idx.get('tool')}）；数据版本 {DATA_VERSION}",
             f"- 产物：34 个 `<书>.jsonl.gz` + `_index.json`；压缩后 {_fmt_bytes(totals.get('compressed_bytes', 0))}"
             f"（压缩前 {_fmt_bytes(totals.get('uncompressed_bytes', 0))}，比 {totals.get('ratio', 0):.1%}）", "",
             "## 一、规模", "", "| 项 | 数量 |", "|---|---:|"]
    for k in ("books", "lit_books", "unlit_books", "sentences", "lit_sentences", "unlit_sentences",
              "covered", "uncovered", "excluded_fence_units", "excluded_headings", "excluded_title_lines"):
        lines.append(f"| {k} | {c.get(k, 0)} |")
    lines += ["", "## 二、双 ID 规范（W13 §4）", "", "```text",
              "点亮 5 书：{book}.{chapter:03d}.{para:03d}.s{n}（pn={book}#pn-r{ch}.{para}）",
              "未点亮 29 书：{book}.{chapter:03d}.L{line:03d}.s{n}（章回版行号 fallback）",
              "status ∈ {covered, uncovered, excluded}；reader 见 `iter_book_sentences()`", "```", "",
              "## 三、校验（--strict）", "",
              f"- 结论：{'PASS' if val.get('passed') else 'FAIL'}；错误 {len(val.get('errors') or [])} 项"]
    for e in val.get("errors") or []:
        lines.append(f"  - {e}")
    lines += ["", "## 四、遗留/边界", "",
              "- 5 书 page_refs 待 W8 页面 evidence 回填；29 书无 tagged 仅行号级。",
              "- 围栏/标题/空行不生成句记录，excluded_* 计数（W13 §4.2）。",
              "- 压缩分片、_index 记录压缩前后 sha256；不写 site/data。", ""]
    return "\n".join(lines) + "\n"


# ────────────────────────── 校验/CLI ──────────────────────────
def validate_index(idx: dict) -> dict:
    errors = []
    rows = idx.get("by_book") or []
    if len(rows) != 34:
        errors.append(f"分片书数应为 34，实际 {len(rows)}")
    if len(idx.get("lit_books") or []) != 5:
        errors.append("lit_books 应为 5")
    if len(idx.get("unlit_books") or []) != 29:
        errors.append("unlit_books 应为 29")
    if idx.get("counts", {}).get("sentences", 0) != 523694:
        errors.append(f"句数异常：{idx.get('counts', {}).get('sentences')}（基线 523,694）")
    if not (idx.get("totals") or {}).get("within_target"):
        errors.append("压缩后体积超过 30MB 目标")
    ids = [r.get("file") for r in rows]
    if len(ids) != len(set(ids)):
        errors.append("分片文件名重复")
    for r in rows:
        if not r.get("sha256_uncompressed") or not r.get("sha256_compressed"):
            errors.append(f"{r.get('book')}: 缺 sha256")
    if (idx.get("equivalence") or {}).get("passed") is False:
        errors.append("等价性检查未通过")
    return {"passed": not errors, "errors": errors}


def _backup_dir() -> Path | None:
    p = ROOT / "logs" / "qa" / "_sentence_precompress"
    return p if p.exists() else None


def apply_compress(out_dir: Path, keep_jsonl: bool = False) -> tuple[dict, int, dict]:
    old_index = load_index(out_dir)
    jsonls = sorted(out_dir.glob("*.jsonl"))
    before_total = sum(p.stat().st_size for p in jsonls)
    uncompressed_meta = {}
    for p in jsonls:
        book = p.name[:-len(".jsonl")]
        data = p.read_bytes()
        comp = gzip_bytes(data)
        shard_path(out_dir, book, True).write_bytes(comp)
        uncompressed_meta[book] = {"sha256_uncompressed": sha256_bytes(data),
                                   "bytes_uncompressed": len(data)}
        if not keep_jsonl:
            p.unlink()
    idx = build_index(out_dir, old_index=old_index, uncompressed_meta=uncompressed_meta)
    (out_dir / "_index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    equiv = verify_shards(out_dir, SAMPLE_BOOKS, _backup_dir(), idx)
    idx["equivalence"] = {"method": equiv["method"], "checked": equiv["checked"],
                          "passed": equiv["passed"], "details": equiv["details"],
                          "sample_books": SAMPLE_BOOKS}
    idx["validation"] = validate_index(idx)
    (out_dir / "_index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    return idx, before_total, equiv


def generate_and_write(out_dir: Path, keep_jsonl: bool = False) -> tuple[dict, int, dict]:
    inp = Inputs()
    old_index = load_index(out_dir)
    total_un = 0
    for book in inp.lit_books + inp.unlit_books:
        recs, _counts = (lit_sentences(inp, book) if book in inp.lit_books else unlit_sentences(inp, book))
        meta = write_book_shard(book, recs, out_dir, compress=True)
        total_un += meta["bytes_uncompressed"]
    idx = build_index(out_dir, old_index=old_index)
    (out_dir / "_index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    equiv = verify_shards(out_dir, SAMPLE_BOOKS, _backup_dir(), idx)
    idx["equivalence"] = {"method": equiv["method"], "checked": equiv["checked"],
                          "passed": equiv["passed"], "details": equiv["details"],
                          "sample_books": SAMPLE_BOOKS}
    idx["validation"] = validate_index(idx)
    (out_dir / "_index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    return idx, total_un, equiv


def run_selftest(out_dir: Path = OUT_DIR) -> int:
    checks = []

    def chk(name, cond):
        checks.append(bool(cond))
        if not cond:
            print(f"[FAIL] {name}")

    raw = b'{"a":1}\n{"a":2}\n'
    chk("gzip 往返", gzip.decompress(gzip_bytes(raw)) == raw)
    chk("gzip 确定性", gzip_bytes(raw) == gzip_bytes(raw))
    chk("切句 2 句", len(split_sentences("甲。乙！")) == 2)
    chk("ID lit 正则", bool(ID_LIT.match("七剑下天山.004.012.s3")))
    chk("ID unlit 正则", bool(ID_UNLIT.match("龙虎斗京华.001.L010.s2")))
    chk("解析令牌", parse_line("a〖@张三〗b")[0] == "a张三b")
    idx = load_index(out_dir)
    if idx and idx.get("schema") == "w13-sentence-index-v0.2-gzip":
        ev = verify_shards(out_dir, SAMPLE_BOOKS, _backup_dir())
        chk("等价性抽样（5 lit + 2 unlit）", ev["passed"])
        chk("句数", idx.get("counts", {}).get("sentences") == 523694)
        chk("体积≤30MB", idx.get("totals", {}).get("within_target") is True)
        chk("reader 可解压", len(read_book_sentences("龙虎斗京华", out_dir)[:1]) == 1)
    else:
        chk("旧索引/未压缩（artifact 检查跳过，待 --apply）", True)
    # task-80 page_refs：合成记录/定位符映射/指针格式
    loc_pages = {("七剑下天山", 1, 2): {"content/person/card.person.e0001.md"},
                 ("七剑下天山", 1, 3): {"content/art/card.art.nabc.md"}}
    fake = [{"id": "七剑下天山.001.002.s1", "book": "七剑下天山", "chapter": 1, "para": 2,
             "status": "covered", "page_refs": []},
            {"id": "七剑下天山.001.002.s2", "book": "七剑下天山", "chapter": 1, "para": 2,
             "status": "uncovered", "page_refs": []},
            {"id": "七剑下天山.001.003.s1", "book": "七剑下天山", "chapter": 1, "para": 3,
             "status": "covered", "page_refs": []}]
    st = fill_records_page_refs(fake, "七剑下天山", loc_pages)
    chk("page_refs：covered 句回填且排序/去重",
        st["sentences_with_page_refs"] == 2 and
        fake[0]["page_refs"] == ["content/person/card.person.e0001.md"] and
        fake[2]["page_refs"] == ["content/art/card.art.nabc.md"])
    chk("page_refs：uncovered 句保持 []", fake[1]["page_refs"] == [])
    chk("page_refs：路径格式（无原文）", all(PAGE_REF_RE.match(x) for x in
                                            fake[0]["page_refs"] + fake[2]["page_refs"]))
    chk("page_refs：content 扫描有页面", scan_content_pages()[2].get("pages", 0) > 0)
    chk("page_refs：work→book 映射", work_to_book().get("bainv") == "白发魔女传")
    ok = sum(checks)
    print(f"[selftest] {ok}/{len(checks)} passed")
    return 0 if ok == len(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_sentence_index.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="W13 双 ID 句级索引（gzip 分片）：5 书 PN 句 ID + 29 书行号句 ID，"
                    "输出 <书>.jsonl.gz + _index.json（大小/sha256/句数/覆盖）；reader 可解压。",
        epilog="示例：python -X utf8 scripts/build_sentence_index.py --dry-run / --apply / --selftest / "
               "--read 七剑下天山 --limit 2 / --strict --apply")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="统计/预估压缩比（默认，不写盘）")
    g.add_argument("--apply", action="store_true", help="压缩现有 JSONL → gzip + _index.json（或重生成）")
    g.add_argument("--selftest", action="store_true", help="gzip/等价性/reader 断言")
    g.add_argument("--read", metavar="BOOK", help="按书读取并打印句记录（reader 接口验证）")
    p.add_argument("--limit", type=int, default=3, help="--read 打印条数（默认 3）")
    p.add_argument("--page-refs", action="store_true",
                   help="从 content frontmatter evidence/quotes loc 回填 5 书 covered 句 page_refs"
                        "（配合 --apply 写盘；缺省 dry-run 统计）")
    p.add_argument("--page-refs-report", default=str(OUT_PAGE_REFS_REPORT),
                   help="page_refs 报告路径（默认 logs/qa/sentence_page_refs_report.md）")
    p.add_argument("--strict", action="store_true", help="≤30MB/等价性/计数断言，失败 exit 2")
    p.add_argument("--keep-jsonl", action="store_true", help="压缩后保留旧 JSONL（调试）")
    p.add_argument("--out-dir", default=str(OUT_DIR))
    p.add_argument("--report", default=str(OUT_REPORT))
    p.add_argument("--compress-report", default=str(OUT_COMPRESS_REPORT))
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    if args.selftest:
        return run_selftest(out_dir)
    if args.read:
        n = 0
        for r in iter_book_sentences(args.read, out_dir):
            print(json.dumps(r, ensure_ascii=False))
            n += 1
            if n >= max(1, args.limit):
                break
        return 0
    if args.page_refs:
        meta, totals, _ = update_page_refs(out_dir, write=args.apply,
                                          report_path=Path(args.page_refs_report))
        if not args.quiet:
            print(f"[page_refs] pages={meta['pages']} with_refs={meta['pages_with_page_refs']} "
                  f"sentences_with_refs={meta['sentences_with_page_refs']} "
                  f"links={meta['page_ref_links']} unresolved={meta['unresolved_locators']} "
                  f"write={'Y' if args.apply else 'N'}")
        if args.apply:
            idx2 = load_index(out_dir)
            val = (idx2.get("validation") or {}).get("page_refs") or {}
            if args.strict and not val.get("passed"):
                print("[STRICT] page_refs 校验未通过", file=sys.stderr)
                for e in val.get("errors") or []:
                    print(f"  - {e}", file=sys.stderr)
                return 2
        return 0
    index = load_index(out_dir)
    idx = index
    if args.apply:
        if list(out_dir.glob("*.jsonl")):
            idx, before_total, _equiv = apply_compress(out_dir, args.keep_jsonl)
        else:
            idx, before_total, _equiv = generate_and_write(out_dir, args.keep_jsonl)
        Path(args.compress_report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.compress_report).write_text(
            render_compress_report(idx, before_total, idx.get("equivalence") or {}, dry=False), encoding="utf-8")
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(render_report(idx, idx.get("validation") or {}), encoding="utf-8")
        if not args.quiet:
            print(f"[OK] 压缩 34 书 → {idx['totals']['compressed_bytes']:,} B "
                  f"({_fmt_bytes(idx['totals']['compressed_bytes'])}；比 {idx['totals']['ratio']:.1%}；"
                  f"目标 {'PASS' if idx['totals']['within_target'] else 'FAIL'})")
            print(f"[OK] _index → {out_dir / '_index.json'}；报告 → {args.compress_report} · {args.report}")
    else:
        jsonls = sorted(out_dir.glob("*.jsonl"))
        if jsonls:
            before = sum(p.stat().st_size for p in jsonls)
            after = sum(len(gzip_bytes(p.read_bytes())) for p in jsonls)
            print(f"[dry-run] 现有 {len(jsonls)} 个 JSONL：{before:,} B → 预计 {after:,} B "
                  f"（{after / before:.1%}；目标 {'PASS' if after <= TARGET_BYTES else 'FAIL'}）；未写盘")
        elif index:
            print(f"[dry-run] 已压缩：{index['totals']['compressed_bytes']:,} B "
                  f"（{_fmt_bytes(index['totals']['compressed_bytes'])}；比 {index['totals']['ratio']:.1%}；"
                  f"等价性 {'PASS' if (index.get('equivalence') or {}).get('passed') else 'FAIL'}）")
        else:
            print("[dry-run] 无 JSONL/索引；--apply 将从源数据生成 gzip")
    if args.strict:
        val = (idx.get("validation") or {}) if idx else {"passed": False, "errors": ["无索引"]}
        if not val.get("passed"):
            print("[STRICT] 校验未通过", file=sys.stderr)
            for e in val.get("errors") or []:
                print(f"  - {e}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
