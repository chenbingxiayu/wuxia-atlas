#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D4：从 site/dist 的 HTML 生成 site/data/search-index.json（零第三方依赖）。

用途：为 /search 页提供轻量客户端搜索索引。每条记录含
  标题(title) / URL(url，相对 base) / 摘要(summary) / 展示名(display) / 规范名(canonical) / 类型(type) / 别名(aliases，可选)
以便同时按 **display** 与 **canonical** 命中（如"康熙"与"玄烨"都能搜到同一人物页）。

数据流：
  site/dist/**/*.html（Astro 构建产物，标题/摘要/display 均已在 HTML 中）
    + site/data/dossiers.json（canonical→display/aliases 权威映射）
    → site/data/search-index.json
    →（可选同步）site/dist/data/search-index.json、site/public/data/search-index.json

注意：
  * 必须**在 `npm run build` 之后**运行（索引源是 dist）；
  * 若之后重新 build，请重跑本脚本；若构建前已有 site/data/search-index.json，Astro 会把
    site/data 镜像进 public/data → dist/data，搜索页仍可读到（旧索引，需按提示重跑）；
  * Pagefind 为可选增强：`--pagefind` 会调用 `npx --yes pagefind@1.6.0 --site dist`，
    不可用/失败不阻塞（搜索页自动回退 JSON 搜索）。

用法：
  python -X utf8 scripts/build_search_index.py                # 生成 + 同步 dist/public
  python -X utf8 scripts/build_search_index.py --no-emit-dist # 只写 site/data
  python -X utf8 scripts/build_search_index.py --pagefind     # 顺带生成 Pagefind 索引
  python -X utf8 scripts/build_search_index.py --selftest     # 生成后跑样例查询断言
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[2]
SITE = REPO_ROOT / "site"
DEFAULT_DIST = SITE / "dist"
DEFAULT_OUT = SITE / "data" / "search-index.json"
PUBLIC_DATA = SITE / "public" / "data"
SCHEMA = "site-search-v1"
GENERIC_DESC = "基于梁羽生小说图谱数据的原创研究站点：人物谱、武功志、宇宙地图，每条结论可溯源到原著定位符。"
SKIP_DIRS = {"_astro", "data", "pagefind", "geo", "_pagefind"}
SKIP_TOP_FILES = {"404.html"}
MAX_SUMMARY = 160
MAX_ALIASES = 8


class PageParser(HTMLParser):
    """极简 HTML 解析：收集 title / h1 / meta description / 首个 p 文本。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.h1: list[str] = []
        self.p_first = ""
        self.meta_desc = ""
        self._cur: list[str] | None = None
        self._tag: str | None = None
        self._skip = 0
        self._p_seen = False
        self._badge_tag: str | None = None  # class 含 badge 的元素（视觉徽标）文本不进标题/h1/摘要

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            return
        if self._cur is not None and self._badge_tag is None and \
                "badge" in (a.get("class") or "").split():
            self._badge_tag = tag
            return
        if tag == "title":
            self._tag, self._cur = "title", self.title
        elif tag == "h1":
            self._tag, self._cur = "h1", self.h1
        elif tag == "p" and not self._p_seen and not self.p_first:
            self._tag, self._cur = "p", []
        elif tag == "meta" and a.get("name") == "description" and not self.meta_desc:
            self.meta_desc = (a.get("content") or "").strip()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
            return
        if self._badge_tag is not None and tag == self._badge_tag:
            self._badge_tag = None
            return
        if tag == "title" and self._tag == "title":
            self._tag = self._cur = None
        elif tag == "h1" and self._tag == "h1":
            self._tag = self._cur = None
        elif tag == "p" and self._tag == "p":
            self.p_first = _norm("".join(self._cur or []))
            self._p_seen = True
            self._tag = self._cur = None

    def handle_data(self, data):
        if self._skip or self._cur is None or self._badge_tag is not None:
            return
        self._cur.append(data)


def _norm(s: str) -> str:
    s = html_lib.unescape(s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _truncate(s: str, n: int = MAX_SUMMARY) -> str:
    s = _norm(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _strip_title_suffix(t: str) -> str:
    t = _norm(t)
    t = re.sub(r"\s*[·•]\s*江湖图志\s*$", "", t)
    return t.strip()


def load_display_map() -> dict[str, dict]:
    """canonical → {display, aliases}；以 dossiers.json 为主，entity-index 补全。"""
    m: dict[str, dict] = {}
    dossiers = SITE / "data" / "dossiers.json"
    if dossiers.exists():
        d = json.loads(dossiers.read_text(encoding="utf-8"))
        for rec in d.get("dossiers") or []:
            c = rec.get("canonical")
            if not c:
                continue
            aliases = [a.get("alias") for a in (rec.get("aliases") or []) if a.get("alias")]
            m[c] = {"display": rec.get("display") or rec.get("display_name") or c,
                    "aliases": [a for a in aliases if a != c][:MAX_ALIASES]}
    ei = SITE / "data" / "entity-index.json"
    if ei.exists():
        d = json.loads(ei.read_text(encoding="utf-8"))
        for rec in d.get("entities") or []:
            c = rec.get("canonical")
            if not c:
                continue
            m.setdefault(c, {"display": rec.get("display") or c, "aliases": []})
    return m


def rel_to_url(rel: Path) -> str:
    """dist 内相对路径 → 站内相对 URL（不含 base，index.html 折叠为目录/；根为 ''）。"""
    s = rel.as_posix()
    if s == "index.html":
        return ""
    if s.endswith("/index.html"):
        return s[: -len("index.html")]
    return s


def entry_type(url: str) -> str:
    if "/" not in url:
        return "page"
    return url.split("/", 1)[0] or "page"


def build_entry(path: Path, rel: Path, display_map: dict[str, dict]) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    p = PageParser()
    try:
        p.feed(raw)
    except Exception:
        return None
    title = _strip_title_suffix(p.title[0]) if p.title else ""
    h1 = _norm("".join(p.h1))
    url = rel_to_url(rel)
    if not url and not title:
        return None
    ty = entry_type(url)
    segs = [unquote(x) for x in url.split("/") if x]
    canonical = ""
    display = h1 or title
    aliases: list[str] = []
    if ty == "characters" and len(segs) >= 2:
        canonical = segs[1]
        info = display_map.get(canonical)
        if info:
            display = info["display"] or display or canonical
            aliases = list(info.get("aliases") or [])
        else:
            display = display or canonical
    else:
        canonical = display or title
    title = title or display or canonical
    summary = p.meta_desc.strip()
    if not summary or summary == GENERIC_DESC:
        summary = p.p_first or GENERIC_DESC
    rec = {"url": url, "title": title, "display": display or title,
           "canonical": canonical or title, "type": ty,
           "summary": _truncate(summary)}
    if aliases:
        rec["aliases"] = aliases
    return rec


def site_base() -> str:
    """从 astro.config.mjs 读取 base（默认 /wuxia-atlas/），供 Pagefind 结果链接使用。"""
    cfg = SITE / "astro.config.mjs"
    try:
        m = re.search(r"base:\s*['\"]([^'\"]+)['\"]", cfg.read_text(encoding="utf-8"))
        if m:
            b = m.group(1)
            return b if b.endswith("/") else b + "/"
    except OSError:
        pass
    return "/wuxia-atlas/"


def run_pagefind(dist: Path) -> dict:
    """可选：npx pagefind（无 package.json 依赖）。失败返回 {ok:false, ...}。"""
    info = {"attempted": True, "ok": False}
    base_url = site_base()
    info["base_url"] = base_url
    npx = shutil.which("npx") or shutil.which("npx.cmd") or "npx"
    try:
        v = subprocess.run([npx, "--yes", "pagefind@1.6.0", "--version"], cwd=str(SITE),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        info["version_cmd"] = (v.stdout or v.stderr or "").strip().splitlines()[:1]
        info["version_code"] = v.returncode
        if v.returncode != 0:
            return info
        r = subprocess.run([npx, "--yes", "pagefind@1.6.0", "--site", str(dist)], cwd=str(SITE),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        info["build_code"] = r.returncode
        info["tail"] = (r.stdout or "").strip().splitlines()[-4:]
        info["ok"] = r.returncode == 0 and (dist / "pagefind").is_dir()
        info["dir"] = str((dist / "pagefind").relative_to(SITE)) if (dist / "pagefind").is_dir() else None
    except Exception as e:  # noqa: BLE001 - 不阻塞
        info["error"] = f"{type(e).__name__}: {e}"
    return info


def main() -> int:
    ap = argparse.ArgumentParser(description="从 site/dist HTML 生成站点搜索索引（site-search-v1）")
    ap.add_argument("--dist", type=Path, default=DEFAULT_DIST)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-emit-dist", action="store_true", help="不同步到 dist/data 与 public/data")
    ap.add_argument("--pagefind", action="store_true", help="顺带生成 Pagefind 索引（可选）")
    ap.add_argument("--selftest", action="store_true", help="生成后跑样例查询断言")
    args = ap.parse_args()

    dist = args.dist.resolve()
    if not dist.is_dir():
        print(f"[search-index] dist 不存在：{dist}（先 cd site && npm run build）", file=sys.stderr)
        return 2
    display_map = load_display_map()
    files = sorted(dist.rglob("*.html"))
    entries: list[dict] = []
    skipped = 0
    for f in files:
        rel = f.relative_to(dist)
        if rel.parts and (rel.parts[0] in SKIP_DIRS):
            skipped += 1
            continue
        if rel.name in SKIP_TOP_FILES:
            skipped += 1
            continue
        if rel.as_posix() == "search/index.html":
            skipped += 1
            continue
        rec = build_entry(f, rel, display_map)
        if rec:
            entries.append(rec)
        else:
            skipped += 1
    # gazetteer 地名入索引（type=places，链接到时空地图深链；名称已入索引的不重复收录）
    gaz_file = SITE / "data" / "gazetteer.json"
    if gaz_file.exists():
        try:
            gaz = json.loads(gaz_file.read_text(encoding="utf-8"))
            known_names = {e["display"] for e in entries} | {e.get("canonical", "") for e in entries}
            for pl in gaz.get("places") or []:
                name = (pl.get("name") or "").strip()
                if not name or name in known_names:
                    continue
                known_names.add(name)
                books = pl.get("books") or {}
                summary = "；".join(f"{b}·第{c[0]}回起" for b, c in sorted(books.items())[:3] if c)
                if pl.get("real"):
                    kind = pl.get("kind") or "地名"
                    summary = f"实锚地名（{kind}）" + (f"：{summary}" if summary else "")
                else:
                    summary = f"虚构/推理地名" + (f"：{summary}" if summary else "")
                entries.append({
                    "url": f"atlas/?place={quote(name)}",
                    "title": name, "display": name, "canonical": name,
                    "type": "places", "summary": _truncate(summary or name),
                })
        except (OSError, ValueError, KeyError) as e:
            print(f"[search-index] WARN gazetteer 地名入索引失败：{e}", file=sys.stderr)
    # URL 去重（保第一条）并按 type/url 排序
    seen = set()
    uniq = []
    for e in entries:
        if e["url"] in seen:
            continue
        seen.add(e["url"])
        uniq.append(e)
    uniq.sort(key=lambda e: (e["type"], e["url"]))
    by_type: dict[str, int] = {}
    for e in uniq:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    pagefind_info = run_pagefind(dist) if args.pagefind else {"attempted": False,
                                                              "available": (dist / "pagefind").is_dir()}
    payload = {
        "meta": {
            "schema": SCHEMA,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "site/dist/**/*.html + site/data/dossiers.json（display 权威表）",
            "totals": {"entries": len(uniq), "by_type": by_type, "skipped": skipped},
            "pagefind": pagefind_info,
        },
        "entries": uniq,
    }
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")
    emitted = [str(out)]
    if not args.no_emit_dist:
        for d in (dist / "data", PUBLIC_DATA):
            if d.is_dir():
                p = d / "search-index.json"
                p.write_text(text, encoding="utf-8", newline="\n")
                emitted.append(str(p))
    # 展示层抽样
    samples = {}
    for c, dname in (("玄烨", "康熙"), ("朱由检", "崇祯"), ("福临", "顺治"),
                     ("胤禛", "雍正"), ("哈玛雅", "飞红巾")):
        hit = [e for e in uniq if e.get("canonical") == c and e["type"] == "characters"]
        samples[c] = hit[0].get("display") if hit else None
        if hit and hit[0].get("display") != dname:
            print(f"[search-index] WARN display 映射异常：{c} → {hit[0].get('display')}（期望 {dname}）",
                  file=sys.stderr)
    print(f"[search-index] entries={len(uniq)} skipped={skipped} by_type={by_type}")
    print(f"[search-index] size={len(text.encode('utf-8'))/1024:.1f}KB pagefind={pagefind_info}")
    print(f"[search-index] display 抽样：{samples}")
    print(f"[search-index] 写入：{'; '.join(emitted)}")
    if args.selftest:
        return selftest(uniq, payload)
    return 0


def _score(entry: dict, tokens: list[str]) -> int:
    fields = [entry.get("display", ""), entry.get("canonical", ""), entry.get("title", ""),
              entry.get("summary", "")] + list(entry.get("aliases") or [])
    total = 0
    for tok in tokens:
        best = 0
        for f in fields:
            f = f or ""
            if f == tok:
                best = max(best, 100)
            elif f.startswith(tok):
                best = max(best, 80)
            elif tok in f:
                best = max(best, 60)
        if best == 0:
            return 0
        total += best
    return total


def search(entries: list[dict], q: str, limit: int = 20) -> list[dict]:
    tokens = [t for t in re.split(r"\s+", q.strip()) if t]
    if not tokens:
        return []
    scored = [(_score(e, tokens), e) for e in entries]
    hits = [(s, e) for s, e in scored if s > 0]
    if not hits:  # AND 无结果 → OR 兜底
        hits = []
        for e in entries:
            s = max((_score(e, [t]) for t in tokens), default=0)
            if s:
                hits.append((s, e))
    hits.sort(key=lambda x: (-x[0], x[1]["type"], x[1]["url"]))
    return [e for _, e in hits[:limit]]


def selftest(entries: list[dict], payload: dict) -> int:
    fails = 0
    cases = [("康熙", "characters/玄烨/"), ("玄烨", "characters/玄烨/"),
             ("崇祯", "characters/朱由检/"), ("顺治", "characters/福临/"),
             ("雍正", "characters/胤禛/"), ("飞红巾", "characters/哈玛雅/"),
             ("哈玛雅", "characters/哈玛雅/"), ("七剑下天山", "books/七剑下天山/"),
             ("白发魔女传", "books/白发魔女传/")]
    misses = ["不存在的词xyz"]
    for q, want in cases:
        hits = search(entries, q)
        urls = [h["url"] for h in hits]
        ok = want in urls
        print(f"[selftest] {q!r} → {urls[:3]}  {'PASS' if ok else 'FAIL'}")
        fails += 0 if ok else 1
    for q in misses:
        hits = search(entries, q)
        ok = len(hits) == 0
        print(f"[selftest] {q!r} → {len(hits)} hits（期望 0）  {'PASS' if ok else 'FAIL'}")
        fails += 0 if ok else 1
    print(f"[selftest] entries={payload['meta']['totals']['entries']} failures={fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
