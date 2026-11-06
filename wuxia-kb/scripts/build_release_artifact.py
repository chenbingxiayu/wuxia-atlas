#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布包生成：把 site/dist 打包为 zip + manifest.json + RELEASE_NOTES.md（task-71）。

只读 `--dist`，只写 `--out`（默认 `logs/release_artifacts/`），**不写 site/**。

产物（out 目录内）：
  wuxia-atlas-<YYYYMMDD_HHMMSS>.zip   站点静态产物（dist 全量文件）
  manifest.json                        schema/版本/构建时间/页面与检查指标/逐文件 size+sha256/zip sha256
  RELEASE_NOTES.md                     本批指标（页面/搜索/链接/闸门/release GO）+ 证据路径 + 部署说明
  latest.json                         最近一次发布包指针（便于脚本消费）

CLI：
  python -X utf8 scripts/build_release_artifact.py                 # 打包当前 site/dist
  python -X utf8 scripts/build_release_artifact.py --version 0.2.0
  python -X utf8 scripts/build_release_artifact.py --dist PATH --out DIR
  python -X utf8 scripts/build_release_artifact.py --selftest      # 临时夹具自测（不碰真实 dist/out）

退出码：0=成功；1=运行失败；2=参数/输入错误。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]         # Wuxiaxiaoshuo/
KB = Path(__file__).resolve().parents[1]                # wuxia-kb/
SITE = REPO_ROOT / "site"
DEFAULT_DIST = SITE / "dist"
DEFAULT_OUT = KB / "logs" / "release_artifacts"
SCHEMA = "wuxia-atlas-release-v1"
EVIDENCE = {
    "release_log": KB / "logs" / "qa" / "release_latest_summary.json",
    "acceptance_scan": KB / "logs" / "qa" / "site_acceptance_scan.json",
    "search_index": SITE / "data" / "search-index.json",
    "pagefind_entry": SITE / "dist" / "pagefind" / "pagefind-entry.json",
}
ARTIFACT_RE = "wuxia-atlas-*.zip"


def _sha256_file(p: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} GB"


def _rel(p: str | Path) -> str:
    """仓库内相对路径（用于发布说明，避免暴露本机绝对路径）。"""
    try:
        return os.path.relpath(str(p), str(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def _version_from_package() -> str:
    pkg = _read_json(SITE / "package.json")
    return str(pkg.get("version") or "0.1.0")


def collect_dist(dist: Path) -> list[tuple[str, Path, int, str]]:
    """dist 下文件清单 [(arcname, abspath, size, sha256)]（跳过 OS 杂项）。"""
    out = []
    for dp, _dirs, files in os.walk(dist):
        for name in sorted(files):
            if name in ("Thumbs.db", ".DS_Store"):
                continue
            p = Path(dp) / name
            rel = p.relative_to(dist).as_posix()
            out.append((rel, p, p.stat().st_size, _sha256_file(p)))
    out.sort(key=lambda x: x[0])
    return out


def collect_evidence(dist: Path) -> dict:
    """从现成数据/日志读指标（缺失时返回 None，不伪造）。"""
    ev = {"paths": {k: str(v) for k, v in EVIDENCE.items()}, "missing": []}
    html = [p for p in dist.rglob("*.html")]
    ev["pages"] = len(html)
    ev["characters_pages"] = len([p for p in (dist / "characters").glob("*/index.html")]) if (dist / "characters").is_dir() else None
    ev["books_pages"] = len([p for p in (dist / "books").glob("*/index.html")]) if (dist / "books").is_dir() else None
    ev["built_at"] = datetime.fromtimestamp(max(p.stat().st_mtime for p in dist.rglob("*") if p.is_file())).strftime("%Y-%m-%d %H:%M:%S")
    # 搜索索引（dist 内副本优先，其次 site/data）
    search = _read_json(dist / "data" / "search-index.json") or _read_json(EVIDENCE["search_index"])
    ev["search_entries"] = ((search.get("meta") or {}).get("totals") or {}).get("entries")
    if not search:
        ev["missing"].append("search_index")
    # Pagefind
    pf = _read_json(dist / "pagefind" / "pagefind-entry.json")
    langs = (pf.get("languages") or {})
    ev["pagefind"] = {"version": pf.get("version"),
                      "pages": sum((v or {}).get("page_count", 0) for v in langs.values()) if langs else None}
    if not pf:
        ev["missing"].append("pagefind")
    # 验收扫描
    scan = _read_json(EVIDENCE["acceptance_scan"])
    if scan:
        links = (scan.get("checks") or {}).get("links") or {}
        counts = (scan.get("checks") or {}).get("counts") or {}
        display = (scan.get("checks") or {}).get("display") or {}
        ev["links_checked"] = links.get("checked")
        ev["links_missing"] = links.get("missing_total")
        ev["scan_failures"] = scan.get("failures")
        ev["scan_counts"] = counts
        ev["display_overrides"] = display.get("pages_title_differs_from_canonical")
    else:
        ev["missing"].append("acceptance_scan")
    # release go/no-go 快照
    rel = _read_json(EVIDENCE["release_log"])
    if rel:
        acc = rel.get("acceptance") or {}
        ev["release"] = {"ts": rel.get("ts"), "go": rel.get("go"),
                         "copyright_gate": (rel.get("copyright_gate") or {}).get("ok"),
                         "pages": (rel.get("build") or {}).get("pages"),
                         "search_entries": (rel.get("search_index") or {}).get("entries"),
                         "links_checked": acc.get("links_checked"), "links_missing": acc.get("missing_links")}
    else:
        ev["missing"].append("release_latest_summary")
    return ev


def write_manifest(out_dir: Path, artifact: Path, version: str, dist: Path,
                   files: list[tuple[str, Path, int, str]], ev: dict) -> dict:
    total = sum(size for _, _, size, _ in files)
    manifest = {
        "schema": SCHEMA,
        "version": version,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": {"dist": str(dist), "built_at": ev.get("built_at")},
        "artifact": {
            "name": artifact.name,
            "size": artifact.stat().st_size,
            "sha256": _sha256_file(artifact),
            "files": len(files),
            "uncompressed_size": total,
        },
        "site": {
            "pages": ev.get("pages"),
            "characters_pages": ev.get("characters_pages"),
            "books_pages": ev.get("books_pages"),
            "search_entries": ev.get("search_entries"),
            "pagefind": ev.get("pagefind"),
        },
        "checks": {
            "links_checked": ev.get("links_checked"),
            "links_missing": ev.get("links_missing"),
            "display_overrides": ev.get("display_overrides"),
            "acceptance_failures": ev.get("scan_failures"),
            "copyright_gate": (ev.get("release") or {}).get("copyright_gate"),
            "release_go": (ev.get("release") or {}).get("go"),
            "release_ts": (ev.get("release") or {}).get("ts"),
        },
        "evidence": ev.get("paths"),
        "missing_evidence": ev.get("missing") or [],
        "files": [{"path": rel, "size": size, "sha256": sha} for rel, _p, size, sha in files],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                           encoding="utf-8", newline="\n")
    return manifest


def write_notes(out_dir: Path, manifest: dict, artifact: Path) -> Path:
    ev = manifest.get("evidence") or {}
    rel = manifest["artifact"]
    s = manifest["site"]
    c = manifest["checks"]
    lines = [
        f"# 梁羽生武侠宇宙 · 江湖图志 — 发布包 {manifest['version']}",
        "",
        f"- 打包时间：{manifest['generated_at']}",
        f"- 源构建：`{_rel(manifest['source']['dist'])}`（构建于 {manifest['source']['built_at']}）",
        f"- 发布包：`{rel['name']}` · {_fmt_bytes(rel['size'])} · sha256 `{rel['sha256'][:16]}…`",
        "",
        "## 本批指标",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 页面（HTML） | **{s.get('pages'):,}** 页 |",
        f"| 搜索索引（site-search-v1） | **{s.get('search_entries'):,}** 条 |",
        f"| 内部链接 | **{c.get('links_checked'):,}** 检查 / **{c.get('links_missing'):,}** 缺失 |",
        f"| display 覆盖 | {c.get('display_overrides')} 页（title 用展示名、URL 保持 canonical） |",
        f"| Pagefind 全文索引 | {((s.get('pagefind') or {}).get('pages'))} 页（v{(s.get('pagefind') or {}).get('version')}） |",
        f"| 版权闸门 | **{'PASS' if c.get('copyright_gate') else 'FAIL/未取到'}** |",
        f"| 发布 go/no-go | **{'GO' if c.get('release_go') else 'NO-GO/未取到'}**（release {c.get('release_ts')}） |",
        "",
        "## 包内容",
        "",
        f"- 文件数：**{rel['files']}**；解压后 **{_fmt_bytes(rel['uncompressed_size'])}**；zip **{_fmt_bytes(rel['size'])}**",
        "- zip 内为 `site/dist/` 的相对路径（解压到站点根即可）；不含 `manifest.json`/本说明（二者与此文件同级）。",
        "",
        "## 证据路径",
        "",
        f"- 发布日志/汇总：`{_rel(ev.get('release_log') or '')}`",
        f"- 验收扫描：`{_rel(ev.get('acceptance_scan') or '')}`",
        f"- 搜索索引：`{_rel(ev.get('search_index') or '')}`（dist 内副本 `data/search-index.json`）",
        f"- Pagefind：`{_rel(ev.get('pagefind_entry') or '')}`",
        "- 逐文件 size/sha256 与 zip sha256：`manifest.json`",
        "- 回滚：发布前旧 dist 备份见 `site/dist.bak.<ts>`；恢复整目录后重新部署即可。",
        "",
        "## 部署",
        "",
        "1. 解压本 zip 到 Web 根目录下的 `/wuxia-atlas/`（GitHub Pages 项目站点 base）；",
        "2. 确认 `/wuxia-atlas/data/search-index.json` 与 `/wuxia-atlas/pagefind/` 可访问；",
        "3. 回滚 = 用上一版 dist（或 zip）覆盖 `/wuxia-atlas/`。",
        "",
        "---",
        "",
        "_由 `scripts/build_release_artifact.py` 生成（只读 dist，只写 logs/release_artifacts）。_",
        "",
    ]
    p = out_dir / "RELEASE_NOTES.md"
    p.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return p


def build_artifact(dist: Path, out_dir: Path, version: str) -> dict:
    if not dist.is_dir():
        raise FileNotFoundError(f"dist 不存在：{dist}")
    if not (dist / "index.html").exists():
        raise FileNotFoundError(f"dist 缺少 index.html：{dist}")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact = out_dir / f"wuxia-atlas-{ts}.zip"
    files = collect_dist(dist)
    if not files:
        raise ValueError(f"dist 下没有文件：{dist}")
    # 先写临时 zip，成功后原子改名，避免半成品残留
    tmp = artifact.with_suffix(".zip.part")
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for arcname, p, _size, _sha in files:
                info = zipfile.ZipInfo(arcname)
                info.date_time = datetime.fromtimestamp(p.stat().st_mtime).timetuple()[:6]
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(p, "rb") as f:
                    zf.writestr(info, f.read())
        if tmp.stat().st_size <= 0:
            raise ValueError("zip 文件为空")
        tmp.replace(artifact)
    finally:
        tmp.unlink(missing_ok=True)
    ev = collect_evidence(dist)
    manifest = write_manifest(out_dir, artifact, version, dist, files, ev)
    notes = write_notes(out_dir, manifest, artifact)
    latest = {"manifest": str(out_dir / "manifest.json"), "notes": str(notes),
              "artifact": str(artifact), "size": manifest["artifact"]["size"],
              "sha256": manifest["artifact"]["sha256"], "generated_at": manifest["generated_at"]}
    (out_dir / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8", newline="\n")
    return {"artifact": str(artifact), "manifest": str(out_dir / "manifest.json"),
            "notes": str(notes), "manifest_data": manifest, "files": len(files)}


def _selftest() -> int:
    """临时夹具：验证 zip/manifest/notes 三者一致，且不写真实 dist/out。"""
    print("[selftest] 构造临时 dist 夹具…")
    tmp = Path(tempfile.mkdtemp(prefix="wuxia_release_test_"))
    try:
        dist = tmp / "dist"
        (dist / "sub").mkdir(parents=True)
        (dist / "data").mkdir()
        (dist / "pagefind").mkdir()
        (dist / "index.html").write_text("<!doctype html><title>首页</title>", encoding="utf-8")
        (dist / "sub" / "page.html").write_text("<!doctype html><title>页面</title>", encoding="utf-8")
        (dist / "data" / "search-index.json").write_text(
            json.dumps({"meta": {"totals": {"entries": 2}}, "entries": []}, ensure_ascii=False), encoding="utf-8")
        (dist / "pagefind" / "pagefind-entry.json").write_text(
            json.dumps({"version": "1.6.0", "languages": {"zh-cn": {"page_count": 2}}}), encoding="utf-8")
        out = tmp / "out"
        r = build_artifact(dist, out, "selftest-1.0")
        man = r["manifest_data"]
        zpath = Path(r["artifact"])
        ok = True
        with zipfile.ZipFile(zpath) as zf:
            names = sorted(zf.namelist())
            expect = sorted(p.relative_to(dist).as_posix() for p in dist.rglob("*") if p.is_file())
            if names != expect:
                print("[selftest] ❌ zip 清单不一致", names, expect); ok = False
        if not Path(r["manifest"]).exists() or not Path(r["notes"]).exists():
            print("[selftest] ❌ manifest/notes 缺失"); ok = False
        if man["artifact"]["files"] != len(expect) or man["artifact"]["size"] != zpath.stat().st_size:
            print("[selftest] ❌ manifest 计数/大小不一致"); ok = False
        if man["artifact"]["sha256"] != _sha256_file(zpath):
            print("[selftest] ❌ manifest zip sha256 不一致"); ok = False
        for row in man["files"]:
            p = dist / row["path"]
            if _sha256_file(p) != row["sha256"] or p.stat().st_size != row["size"]:
                print("[selftest] ❌ 文件 sha/size 不一致:", row["path"]); ok = False
        if man["site"]["pages"] != 2 or man["site"]["search_entries"] != 2:
            print("[selftest] ❌ 页面/搜索指标解析错误", man["site"]); ok = False
        print(f"[selftest] {'PASS' if ok else 'FAIL'} · zip={zpath.name} · files={len(expect)} · "
              f"notes={Path(r['notes']).name}")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成站点发布包（zip + manifest.json + RELEASE_NOTES.md；只读 dist）")
    ap.add_argument("--dist", default=str(DEFAULT_DIST), help=f"站点构建产物目录（默认 {DEFAULT_DIST}）")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"输出目录（默认 {DEFAULT_OUT}）")
    ap.add_argument("--version", default=None, help="版本号（默认取 site/package.json version）")
    ap.add_argument("--selftest", action="store_true", help="临时夹具自测（不触碰真实 dist/out）")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    dist = Path(args.dist).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    version = (args.version or "").strip() or _version_from_package()
    try:
        r = build_artifact(dist, out_dir, version)
    except (FileNotFoundError, ValueError, OSError) as e:
        print(f"[release-artifact] ❌ {e}", file=sys.stderr)
        return 2
    m = r["manifest_data"]
    print(f"[release-artifact] ✅ {r['artifact']}")
    print(f"[release-artifact]    版本 {m['version']} · 文件 {m['artifact']['files']} · "
          f"zip {_fmt_bytes(m['artifact']['size'])}（解压 {_fmt_bytes(m['artifact']['uncompressed_size'])}）")
    print(f"[release-artifact]    页面 {m['site']['pages']} · 搜索 {m['site']['search_entries']} 条 · "
          f"链接缺失 {m['checks']['links_missing']} · 闸门 {m['checks']['copyright_gate']} · GO {m['checks']['release_go']}")
    print(f"[release-artifact]    manifest: {r['manifest']}")
    print(f"[release-artifact]    notes:    {r['notes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
