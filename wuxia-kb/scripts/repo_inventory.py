#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repo_inventory.py —— wuxia-kb 提交准备：仓库清单 / 生成物标记 / 大文件与敏感信息扫描

用途
----
在 git add/commit 之前做一次只读体检：
1. 分类扫描 wuxia-kb（docs/skills/references/templates/content/registry/logs/tagged/
   scripts/wordlists/prompts/design/backup + 根文件）与父仓 `../site`、`../scripts`；
2. 统计文件数/字节数/占比，标记 生成物 vs 源文件、语料限制层（tagged）、git 忽略项；
3. 列出 >5MB 超大文件（提交前须决定忽略/分片/LFS）；
4. 抽样 sha256（确定性：最大 20 个 + 每 50 个文件取 1）；
5. 敏感信息扫描（密钥/令牌/私钥/密码/本地绝对路径），**只报位置+长度+hash，不回显敏感值**；
6. 输出 `logs/qa/repo_inventory.json` + `.md`（默认；--out-dir 可覆盖）。

纪律
----
- 只读扫描：不写除输出目录外的任何文件；不执行 git 写操作（git status 仅只读调用）。
- 不打开 >2MB 文本做内容扫描（性能与误报控制）；不扫描二进制内容。
- 报告中的敏感命中一律脱敏（`len=… sha256=…`），不得把密钥写进日志。

用法
----
    python scripts/repo_inventory.py                 # 默认：扫描 + 写 logs/qa/repo_inventory.{json,md}
    python scripts/repo_inventory.py --out-dir logs/qa --no-git
    python scripts/repo_inventory.py --selftest      # 合成目录自检（不写盘）
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parents[1]          # wuxia-kb/
PARENT = ROOT.parent

# ---- 分类规则：目录前缀 -> (类别, 类型, 说明) --------------------------------
# kind: source=人工源文件 / generated=生成物 / corpus=语料限制层 / mixed=按子路径细分
CATEGORY_RULES = [
    ("docs", "docs/", "source", "设计/审计/执行记录文档"),
    ("skills", "skills/", "source", "SKILL/META/W 技能主文件"),
    ("references", "references/", "source", "规律库支撑文档"),
    ("templates", "templates/", "source", "页型/SKILL 模板"),
    ("prompts", "prompts/", "source", "设计任务提示词"),
    ("design", "design/", "source", "设计资料"),
    ("wordlists", "wordlists/", "mixed", "词表源（*_source.md）vs 编译 JSON"),
    ("content", "content/", "generated", "W8 页面（demo 生成页）"),
    ("registry", "registry/", "generated", "登记/产物层（events/ast/sentence_index 大字库）"),
    ("logs", "logs/", "generated", "运行日志/备份/发布包（git 忽略）"),
    ("backup", "backup/", "generated", "备份（git 忽略）"),
    ("tagged", "tagged/", "corpus", "标注语料（版权限制：仅本地）"),
    ("scripts", "scripts/", "source", "管线/工具脚本"),
]

PARENT_RULES = [
    ("site", "site/", None, "父仓 Astro 站点（src=源 / data=生成物入库 / dist=构建物忽略）"),
    ("parent_scripts", "scripts/", "source", "父仓旧管线脚本（已冻结，只读）"),
]

# git 忽略建议（本清单用于报告，不实际写 .gitignore）
GITIGNORE_SUGGEST = [
    "logs/", "backup/", "dist/", "dist.bak.*",
    "registry/events/", "registry/sentence_index/", "registry/ast/",
    "content/", "**/__pycache__/", "*.pyc",
    ".api_config.json", ".token_cost_config.json",
    "site/node_modules/", "site/dist/", "site/.astro/", "site/public/data/", "site/dist.bak.*",
    "tagged/",          # 版权限制：标注语料仅本地（父仓 kb/ 已有同类规则）
]

TEXT_EXT = {".md", ".py", ".json", ".jsonl", ".txt", ".tsv", ".yaml", ".yml",
            ".astro", ".js", ".ts", ".sh", ".ps1", ".html", ".css", ".toml", ".cfg", ".ini"}
SENSITIVE_FILE_NAMES = re.compile(r"(^\.env($|\.)|\.pem$|\.key$|^id_(rsa|ed25519)|credentials|secret)", re.I)
PATTERNS = [
    ("api_key_assign", re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{12,})")),
    ("openai_sk", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("aws_ak", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer", re.compile(r"(?i)\bBearer\s+([A-Za-z0-9._\-]{20,})")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("password_assign", re.compile(r"(?i)\bpassword\b\s*[:=]\s*['\"]([^'\"]{6,})")),
    ("local_path", re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"']+")),
]

MAX_SCAN_BYTES = 2 * 1024 * 1024
BIG_FILE_BYTES = 5 * 1024 * 1024
SHA_SAMPLE_EVERY = 50
SHA_TOP_N = 20


def _rel(p: Path, base: Path) -> str:
    try:
        return p.relative_to(base).as_posix()
    except ValueError:
        return p.as_posix()


def _sha256(p: Path, limit: int = 64 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        left = limit
        while left > 0:
            b = f.read(min(1 << 20, left))
            if not b:
                break
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def _is_text(p: Path) -> bool:
    return p.suffix.lower() in TEXT_EXT or p.name.startswith(".env")


def scan_sensitive(p: Path) -> list:
    """返回 [{pattern,line,length,sha8}]；不回显匹配值。"""
    hits = []
    try:
        if p.stat().st_size > MAX_SCAN_BYTES or not _is_text(p):
            return hits
        text = io.open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return hits
    for name, rx in PATTERNS:
        for m in rx.finditer(text):
            val = m.group(1) if m.lastindex else m.group(0)
            hits.append({
                "pattern": name,
                "line": text.count("\n", 0, m.start()) + 1,
                "length": len(val),
                "sha8": hashlib.sha256(val.encode("utf-8", "ignore")).hexdigest()[:8],
            })
    return hits


def classify_wuxia(rel: str) -> tuple:
    for cat, prefix, kind, note in CATEGORY_RULES:
        if rel == prefix.rstrip("/") or rel.startswith(prefix):
            if cat == "wordlists":
                kind = "source" if "_source" in rel or rel.endswith("README.md") else "generated"
            return cat, kind, note
    if rel.endswith(".md") and rel.count("/") == 0:
        return "root", "source", "仓库根文件"
    return "other", "source", "未分类（根级杂项）"


def classify_parent(rel: str) -> tuple:
    for cat, prefix, kind, note in PARENT_RULES:
        if rel.startswith(prefix):
            if cat == "site":
                if rel.startswith("site/src/"):
                    return cat, "source", note
                if rel.startswith("site/data/"):
                    return cat, "generated_committed", "站点数据（L0 生成物，保留入库）"
                if "dist.bak" in rel or rel.startswith("site/dist/"):
                    return cat, "generated_ignored", "站点构建产物/备份（忽略）"
                if rel.startswith("site/node_modules/") or rel.startswith("site/.astro/"):
                    return cat, "generated_ignored", "依赖/缓存（忽略）"
                return cat, "mixed", note
            return cat, kind, note
    return "parent_other", "source", "父仓其它文件"


def iter_files(base: Path, exclude_dirs: tuple):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        r = Path(root)
        for f in files:
            p = r / f
            try:
                if p.is_file() and not p.is_symlink():
                    yield p
            except OSError:
                continue


def build_inventory(root: Path, with_git: bool = True) -> dict:
    started = time.time()
    entries = []
    cats = {}
    sensitive = []
    scanned_sensitive = 0

    def add(p: Path, rel: str, cat: str, kind: str, note: str, base: Path):
        nonlocal scanned_sensitive
        try:
            sz = p.stat().st_size
        except OSError:
            return
        e = {"path": rel, "size": sz, "category": cat, "kind": kind, "note": note,
             "ext": p.suffix.lower(), "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")}
        if kind != "generated_ignored" and sz <= MAX_SCAN_BYTES and _is_text(p):
            scanned_sensitive += 1
            hits = scan_sensitive(p)
            if hits:
                sensitive.append({"path": rel, "hits": hits})
        entries.append(e)
        c = cats.setdefault(cat, {"files": 0, "bytes": 0, "kinds": {}})
        c["files"] += 1
        c["bytes"] += sz
        c["kinds"][kind] = c["kinds"].get(kind, 0) + 1

    # wuxia-kb
    for p in iter_files(root, exclude_dirs={"__pycache__", ".git", "node_modules"}):
        rel = _rel(p, root)
        cat, kind, note = classify_wuxia(rel)
        if cat == "logs" and "/qa/" in rel:
            note = "运行日志/备份/发布包/QA 报告（git 忽略）"
        add(p, rel, cat, kind, note, root)
    # 父仓 site/scripts（仅在扫描真实仓库根时；selftest 的临时根不扫父仓）
    skipped_site = []
    is_real_root = root.resolve() == ROOT.resolve()
    if is_real_root:
        for d in sorted((PARENT / "site").glob("dist*")):
            if d.is_dir():
                cnt = 0
                for _r, _ds, _fs in os.walk(d):
                    cnt += len(_fs)
                skipped_site.append({"path": _rel(d, PARENT), "files": cnt,
                                     "note": "构建产物/备份：仅计数不逐文件扫描"})
        for p in iter_files(PARENT / "site", exclude_dirs={"node_modules", ".astro", ".git", "dist"}):
            rel = _rel(p, PARENT)
            if rel.startswith("site/dist"):
                continue
            cat, kind, note = classify_parent(rel)
            add(p, rel, cat, kind, note, PARENT)
        for p in iter_files(PARENT / "scripts", exclude_dirs={"__pycache__", ".git"}):
            rel = _rel(p, PARENT)
            cat, kind, note = classify_parent(rel)
            add(p, rel, cat, kind, note, PARENT)

    # 大文件 / 抽样 sha
    over5 = sorted([e for e in entries if e["size"] > BIG_FILE_BYTES], key=lambda x: -x["size"])
    for e in over5:
        e["over_5mb"] = True
    sample = sorted(entries, key=lambda x: -x["size"])[:SHA_TOP_N]
    if len(entries) > SHA_SAMPLE_EVERY:
        step = max(1, len(entries) // SHA_SAMPLE_EVERY)
        sample += entries[::step]
    seen, sha_sample = set(), []
    for e in sample:
        if e["path"] in seen:
            continue
        seen.add(e["path"])
        base = PARENT if e["category"] in ("site", "parent_scripts") else root
        p = base / e["path"]
        try:
            sha = _sha256(p) if p.exists() else ""
        except OSError:
            sha = ""
        sha_sample.append({"path": e["path"], "size": e["size"], "sha256_16": sha[:16]})
    sha_sample.sort(key=lambda x: -x["size"])

    total_files = len(entries)
    total_bytes = sum(e["size"] for e in entries)
    inv = {
        "schema": "repo-inventory-v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "root": str(root),
        "parent": str(PARENT),
        "totals": {"files": total_files, "bytes": total_bytes, "mb": round(total_bytes / 1048576, 2),
                   "elapsed_s": round(time.time() - started, 2)},
        "categories": {k: {"files": v["files"], "bytes": v["bytes"], "mb": round(v["bytes"] / 1048576, 2),
                           "kinds": v["kinds"]} for k, v in sorted(cats.items())},
        "over_5mb": [{"path": e["path"], "size": e["size"], "mb": round(e["size"] / 1048576, 2),
                      "category": e["category"]} for e in over5],
        "sensitive": {"scanned_text_files": scanned_sensitive, "findings": sensitive,
                      "count": sum(len(s["hits"]) for s in sensitive)},
        "sha_sample": sha_sample,
        "gitignore_suggest": GITIGNORE_SUGGEST,
        "skipped_heavy_dirs": skipped_site,
    }
    if with_git:
        inv["git"] = git_summary(PARENT)
    return inv


def git_summary(repo: Path) -> dict:
    """只读 git 查询（不写、不 add、不 commit）。"""
    def run(args):
        try:
            r = subprocess.run(["git", "-C", str(repo)] + args, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=20)
            return r.returncode, r.stdout
        except (OSError, subprocess.SubprocessError) as e:
            return -1, f"ERROR: {e}"
    code, status = run(["status", "--porcelain"])
    code2, branch = run(["branch", "--show-current"])
    untracked = [l[3:] for l in status.splitlines() if l.startswith("??")]
    modified = [l[3:] for l in status.splitlines() if l[:2].strip() == "M"]
    return {
        "root": str(repo),
        "branch": branch.strip() if code2 == 0 else "",
        "status_ok": code == 0,
        "changed_lines": len(status.splitlines()),
        "untracked_count": len(untracked),
        "modified_count": len(modified),
        "wuxia_kb_untracked": any("wuxia-kb" in u for u in untracked),
        "sample_untracked": untracked[:10],
    }


def render_md(inv: dict) -> str:
    L = [f"# 仓库清单（repo_inventory）", "",
         f"> 生成：{inv['generated_at']}　根：`{inv['root']}`　父仓：`{inv['parent']}`",
         f"> 规模：**{inv['totals']['files']:,} 文件 / {inv['totals']['mb']:,} MB**（扫描 {inv['totals']['elapsed_s']}s）；"
         f"本报告只读生成，不含敏感值。", ""]
    L += ["## 一、分类统计", "", "| 类别 | 文件数 | 大小(MB) | 类型分布(generated/source/…) |", "|---|---:|---:|---|"]
    for cat, c in inv["categories"].items():
        kinds = "/".join(f"{k}:{v}" for k, v in sorted(c["kinds"].items()))
        L.append(f"| {cat} | {c['files']:,} | {c['mb']:,} | {kinds} |")
    L += ["", "## 二、>5MB 文件（提交前须忽略/分片/LFS 决策）", ""]
    if inv["over_5mb"]:
        L += ["| 文件 | 大小(MB) | 类别 |", "|---|---:|---|"]
        L += [f"| {e['path']} | {e['mb']} | {e['category']} |" for e in inv["over_5mb"]]
    else:
        L.append("（无）")
    L += ["", "## 三、敏感信息扫描（脱敏：只报位置/长度/hash）", "",
          f"扫描文本文件 {inv['sensitive']['scanned_text_files']:,} 个；命中 **{inv['sensitive']['count']}** 处。"]
    if inv["sensitive"]["findings"]:
        L += ["", "| 文件 | 命中 |", "|---|---|"]
        for f in inv["sensitive"]["findings"]:
            hits = "; ".join(f"{h['pattern']}@L{h['line']}(len={h['length']},sha8={h['sha8']})" for h in f["hits"])
            L.append(f"| {f['path']} | {hits} |")
    L += ["", "> 说明：本扫描为规则近似，不构成安全认证；`.api_config.json` 已由 wuxia-kb/.gitignore 忽略。"]
    L += ["", "## 四、sha256 抽样（确定性：最大 20 + 每 50 文件取 1）", ""]
    L += ["| 文件 | 大小(KB) | sha256[:16] |", "|---|---:|---|"]
    L += [f"| {s['path']} | {s['size'] // 1024:,} | {s['sha256_16']} |" for s in inv["sha_sample"][:30]]
    if "git" in inv:
        g = inv["git"]
        L += ["", "## 五、git 只读状态（未执行任何写操作）", "",
              f"- 分支：`{g['branch']}`；changed 行：{g['changed_lines']}；untracked：{g['untracked_count']}；modified：{g['modified_count']}；"
              f"`wuxia-kb/` 为 untracked：{'是' if g['wuxia_kb_untracked'] else '否'}"]
        L += ["- untracked 抽样：" + ", ".join(f"`{u}`" for u in g["sample_untracked"][:8])]
    L += ["", "## 六、.gitignore 建议（仅建议，未实际修改）", "", "```gitignore"]
    L += inv["gitignore_suggest"]
    L += ["```", "", "> 由 `scripts/repo_inventory.py` 生成（只读扫描，不写除本报告外的文件，不执行 git add/commit）。"]
    return "\n".join(L) + "\n"


def write_outputs(inv: dict, out_dir: Path) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / "repo_inventory.json", out_dir / "repo_inventory.md"
    io.open(jp, "w", encoding="utf-8", newline="\n").write(json.dumps(inv, ensure_ascii=False, indent=1))
    io.open(mp, "w", encoding="utf-8", newline="\n").write(render_md(inv))
    return [str(jp), str(mp)]


def selftest() -> int:
    """合成小目录验证分类/大文件/敏感扫描规则（不触碰真实仓库）。"""
    ok = 0
    total = 0

    def chk(cond, msg):
        nonlocal ok, total
        total += 1
        if cond:
            ok += 1
        else:
            print(f"  SELFTEST FAIL: {msg}")

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "docs").mkdir(); (base / "skills").mkdir(); (base / "logs" / "qa").mkdir(parents=True)
        (base / "registry" / "events").mkdir(parents=True)
        (base / "docs" / "a.md").write_text("# doc", encoding="utf-8")
        (base / "skills" / "S.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        (base / "logs" / "qa" / "x.json").write_text("{}", encoding="utf-8")
        (base / "registry" / "events" / "big.json").write_bytes(b"0" * (6 * 1024 * 1024))
        (base / ".env").write_text("API_KEY=sk-" + "a" * 24, encoding="utf-8")
        inv = build_inventory(base, with_git=False)
        cats = inv["categories"]
        chk(cats.get("docs", {}).get("files") == 1, "docs 分类")
        chk(cats.get("skills", {}).get("files") == 1, "skills 分类")
        chk(any(e["path"] == "registry/events/big.json" for e in inv["over_5mb"]), ">5MB 检出")
        chk(inv["sensitive"]["count"] >= 1, "敏感 key 检出")
        chk(all("a" * 24 not in json.dumps(inv) for _ in [0]), "敏感值未回显")
        chk(any(e["path"] == ".env" for e in [{"path": p} for p in [".env"]]), "占位")
        chk(inv["totals"]["files"] == 5, "文件总数")
    print(f"SELFTEST {'PASS' if ok == total else 'FAIL'} ({ok}/{total})")
    return 0 if ok == total else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="wuxia-kb 仓库清单/生成物/大文件/敏感扫描（只读）")
    ap.add_argument("--root", default=None, help="仓库根（缺省 scripts/..）")
    ap.add_argument("--out-dir", default=None, help="输出目录（缺省 <root>/logs/qa）")
    ap.add_argument("--no-git", action="store_true", help="跳过 git 只读状态")
    ap.add_argument("--selftest", action="store_true", help="合成目录自检（不写盘）")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    root = Path(args.root).resolve() if args.root else ROOT
    out_dir = Path(args.out_dir).resolve() if args.out_dir else root / "logs" / "qa"
    inv = build_inventory(root, with_git=not args.no_git)
    paths = write_outputs(inv, out_dir)
    print(f"[inventory] {inv['totals']['files']:,} 文件 / {inv['totals']['mb']:,} MB；"
          f">5MB {len(inv['over_5mb'])}；敏感命中 {inv['sensitive']['count']}")
    for p in paths:
        print("  ->", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
