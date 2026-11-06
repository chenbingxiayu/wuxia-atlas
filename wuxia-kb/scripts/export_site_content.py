#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_site_content.py —— content/ W8 演示页 → 站点内容索引（task-88）

读 `content/**/*.md` 的 frontmatter（page_type/display/canonical/card_ref/book_scope/
confidence/publish_state/demo/quotes[]/evidence[]），产出：
  `site/data/content-index.json`（列表页数据源；只索引元数据，不含正文）

设计纪律：
  * 只读 content/，只写 site/data/content-index.json（--apply 时）；
  * 全部页面 `demo: true` → 站点列表页标「演示预览」，不发布正文；
  * 正文仍留在 content/，详情页暂不做（页面内展示源文件路径）；
  * 列表页加 noindex + data-pagefind-ignore，不进主导航/搜索索引。

用法：
  python -X utf8 scripts/export_site_content.py            # dry-run（默认，只打印摘要）
  python -X utf8 scripts/export_site_content.py --apply    # 写 site/data/content-index.json
  python -X utf8 scripts/export_site_content.py --selftest # 合成 frontmatter 自检
  python -X utf8 scripts/export_site_content.py --check    # 校验现有索引与 content 一致
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

SCHEMA = "site-content-v0.1"
CONTENT_DIR = config.ROOT / "content"
OUT_PATH = config.ROOT.parent / "site" / "data" / "content-index.json"

TYPE_LABELS = {
    "person": "人物档案页",
    "faction": "门派档案页",
    "art": "武功档案页",
    "artifact": "兵器档案页",
    "manual": "秘籍档案页",
}
TYPE_ORDER = ("person", "faction", "art", "artifact", "manual")

FRONT_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def split_frontmatter(text: str):
    m = FRONT_RE.match(text)
    if not m:
        return None
    return m.group(1)


def fm_scalar(fm: str, key: str, default: str = "") -> str:
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", fm, re.M)
    if not m:
        return default
    v = m.group(1).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v


def fm_list(fm: str, key: str):
    """读取 `key:` 下 `  - item` 块列表（只处理一层）。"""
    lines = fm.split("\n")
    out, active = [], False
    for ln in lines:
        if re.match(rf"^{re.escape(key)}:\s*$", ln):
            active = True
            continue
        if active:
            m = re.match(r"^\s+-\s+(.*)$", ln)
            if m:
                v = m.group(1).strip().strip("\"'")
                # 只取纯标量；对象项（如 evidence 的 kind:）不计入
                if not re.match(r"^[A-Za-z_]+:\s", v):
                    out.append(v)
            elif ln.strip() and not ln.startswith((" ", "\t")):
                break
    return out


def count_block_items(fm: str, key: str, item_prefix: str) -> int:
    """统计 `key:` 块内以 item_prefix 开头的条目数（如 quotes 的 `- text:`）。"""
    lines = fm.split("\n")
    active, n = False, 0
    for ln in lines:
        if re.match(rf"^{re.escape(key)}:\s*$", ln):
            active = True
            continue
        if active:
            if re.match(r"^\s+-\s+", ln):
                if item_prefix in ln:
                    n += 1
            elif ln.strip() and not ln.startswith((" ", "\t")):
                break
    return n


def parse_page(path: Path, content_dir: Path):
    """→ dict | None（无 frontmatter 返回 None）。"""
    text = path.read_text(encoding="utf-8")
    fm = split_frontmatter(text)
    if fm is None:
        return None
    rel = path.relative_to(content_dir).as_posix()
    typ = rel.split("/")[0]
    page_type = fm_scalar(fm, "page_type") or TYPE_LABELS.get(typ, typ)
    canonical = fm_scalar(fm, "canonical")
    display = fm_scalar(fm, "display")
    demo_raw = fm_scalar(fm, "demo").lower()
    return {
        "id": "",  # 由 slug 去重后回填
        "slug": canonical or path.stem,
        "title": display or canonical or path.stem,
        "canonical": canonical,
        "type": typ,
        "page_type": page_type,
        "card_ref": fm_scalar(fm, "card_ref"),
        "books": fm_list(fm, "book_scope"),
        "confidence": fm_scalar(fm, "confidence"),
        "publish_state": fm_scalar(fm, "publish_state"),
        "demo": demo_raw in ("true", "yes", "1"),
        "quotes_n": count_block_items(fm, "quotes", "- text:"),
        "evidence_n": count_block_items(fm, "evidence", "- kind:"),
        "path": f"content/{rel}",
        "file": path.name,
    }


def collect(content_dir: Path):
    items, errors = [], []
    for p in sorted(content_dir.glob("*/*.md")):
        rec = parse_page(p, content_dir)
        if rec is None:
            errors.append(f"无 frontmatter: {p}")
            continue
        items.append(rec)
    # slug 去重（同类型内）：type/slug → type/slug-2
    seen = {}
    for rec in items:
        key = (rec["type"], rec["slug"])
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            rec["slug"] = f"{rec['slug']}-{seen[key]}"
        rec["id"] = f"{rec['type']}/{rec['slug']}"
    items.sort(key=lambda r: (TYPE_ORDER.index(r["type"]) if r["type"] in TYPE_ORDER else 99,
                              r["slug"]))
    return items, errors


def build_payload(items, errors):
    by_type = {}
    for rec in items:
        by_type[rec["type"]] = by_type.get(rec["type"], 0) + 1
    return {
        "meta": {
            "schema": SCHEMA,
            "generated": datetime.now().isoformat(timespec="seconds"),
            "source": "content/**/*.md frontmatter（W8 演示页）",
            "totals": {
                "pages": len(items),
                "by_type": by_type,
                "demo_pages": sum(1 for r in items if r["demo"]),
                "with_quotes": sum(1 for r in items if r["quotes_n"] > 0),
                "quotes_total": sum(r["quotes_n"] for r in items),
                "evidence_total": sum(r["evidence_n"] for r in items),
            },
            "notes": [
                "全部页面 demo:true —— 站点仅作「演示预览」，不发布正文（正文留在 content/）。",
                "列表页 noindex + data-pagefind-ignore，不进主导航/搜索索引。",
                "详情页暂未接入：页面内展示 content/ 源文件路径。",
            ],
            "type_labels": {k: TYPE_LABELS.get(k, k) for k in by_type},
            "errors": errors,
        },
        "items": items,
    }


def write_index(payload, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    out_path.write_text(text, encoding="utf-8", newline="\n")
    return out_path, len(text.encode("utf-8"))


def selftest() -> int:
    import shutil
    import tempfile
    base = Path(tempfile.mkdtemp(prefix="content_index_selftest_"))
    try:
        (base / "content" / "person").mkdir(parents=True)
        (base / "content" / "art").mkdir(parents=True)
        (base / "content" / "person" / "a.md").write_text(
            "---\npage_type: 人物档案页\ncanonical: 李四\ndisplay: 李四\ndemo: true\n"
            "confidence: C\npublish_state: draft\nbook_scope:\n  - 七剑下天山\n"
            "quotes:\n  - text: \"甲\"\n    loc: \"x#pn-r1.1\"\n    source: \"corpus:x/001\"\n"
            "evidence:\n  - kind: pn\n    ref: \"x#pn-r1.1\"\n---\n\n# 李四\n", encoding="utf-8")
        (base / "content" / "art" / "b.md").write_text(
            "---\npage_type: 武功档案页\ncanonical: 天山剑术\ndisplay: 天山剑术\ndemo: true\n"
            "confidence: B\npublish_state: in-review\nbook_scope:\n  - 冰魄寒光剑\n"
            "  - 七剑下天山\nquotes: []\nevidence: []\n---\n\n# 天山剑术\n", encoding="utf-8")
        items, errors = collect(base / "content")
        payload = build_payload(items, errors)
        out, size = write_index(payload, base / "content-index.json")
        checks = [
            ("A01 页面数=2", len(items) == 2),
            ("A02 类型计数", payload["meta"]["totals"]["by_type"] == {"person": 1, "art": 1}),
            ("A03 demo 全标", payload["meta"]["totals"]["demo_pages"] == 2),
            ("A04 quotes_n 解析", items[0]["quotes_n"] == 1),
            ("A05 books 列表", len(items[1]["books"]) == 2),
            ("A06 evidence_n", any(r["evidence_n"] == 1 for r in items)),
            ("A07 slug/id", all(r["id"] == f"{r['type']}/{r['slug']}" for r in items)),
            ("A08 输出可回读", json.loads(out.read_text(encoding="utf-8"))["meta"]["schema"] == SCHEMA),
            ("A09 无错误", not errors),
            ("A10 排序 person 在前", items[0]["type"] == "person"),
        ]
        passed = sum(1 for _n, ok in checks if ok)
        print(f"[selftest] {passed}/{len(checks)} PASS")
        for name, ok in checks:
            print(f"  {'✅' if ok else '❌'} {name}")
        return 0 if passed == len(checks) else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


def check_index(items, out_path: Path) -> int:
    if not out_path.exists():
        print(f"[check] 索引不存在：{out_path}")
        return 2
    cur = json.loads(out_path.read_text(encoding="utf-8"))
    old_ids = [r["id"] for r in cur.get("items", [])]
    new_ids = [r["id"] for r in items]
    print(f"[check] 现有 {len(old_ids)} 条 / content {len(new_ids)} 条")
    if old_ids != new_ids:
        print("[check] ⚠️ 索引与 content 不一致（需重跑 --apply）")
        return 1
    print("[check] ✅ 索引与 content 一致")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="content 演示页 → site/data/content-index.json")
    ap.add_argument("--apply", action="store_true", help="写 site/data/content-index.json")
    ap.add_argument("--selftest", action="store_true", help="合成 frontmatter 自检")
    ap.add_argument("--check", action="store_true", help="校验现有索引与 content 一致")
    ap.add_argument("--content-dir", default=str(CONTENT_DIR))
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    content_dir = Path(args.content_dir)
    if not content_dir.is_dir():
        print(f"[content-index] content 目录不存在：{content_dir}", file=sys.stderr)
        return 2
    items, errors = collect(content_dir)
    payload = build_payload(items, errors)
    t = payload["meta"]["totals"]
    print(f"[content-index] 页面 {t['pages']} / demo {t['demo_pages']} / "
          f"有引文 {t['with_quotes']} / 引文 {t['quotes_total']} / 类型 {t['by_type']}")
    if errors:
        print(f"  ⚠️ 解析错误 {len(errors)}：{errors[:3]}")
    if args.check:
        return check_index(items, Path(args.out))
    if not args.apply:
        print("  （dry-run；--apply 写 site/data/content-index.json）")
        return 0
    out, size = write_index(payload, Path(args.out))
    print(f"  ✅ 写入 {out}（{size:,} B）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
