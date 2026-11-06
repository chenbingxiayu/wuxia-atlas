#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键发布编排（站点 · 防呆）：导出契约 → build → 搜索索引 → 可选 Pagefind → 版权闸门 → 验收扫描。

设计目标：把 `site/README.md` 的发布顺序固化为一条命令，**任一必需步骤失败即停**，
输出 go/no-go 汇总；发布前自动把上一版 `site/dist` 备份为 `dist.bak.<时间戳>`（可回滚）。

顺序（与 site/README「部署与验收」一致）：
  1. 导出契约校验（dry-run）：`python scripts/export_site_all.py`，要求 hard_gap=0；
  2. 前端构建：`cd site && npm run build`，要求 exit 0 且 pages>0；
  3. 搜索索引：`python scripts/build_search_index.py`（读 dist、写 site/data/search-index.json +
     dist/data/public/data 同步），要求 entries>0；
  4. 可选 Pagefind：`npx --yes pagefind@1.6.0 --site dist`（默认生成；`--skip-pagefind` 跳过）；
  5. 版权闸门：`python ../scripts/copyright_gate.py <site/dist> wuxia-atlas`，要求 exit 0；
  6. 验收扫描：`python logs/qa/_site_acceptance_scan.py`，要求 failures=[] 且链接缺失=0；
  7. go/no-go 汇总：`logs/qa/release_<ts>/{release.log,summary.json}`（并写 release_latest_summary.json）。

CLI：
  python -X utf8 scripts/release_site.py                 # 正式发布（会 build/备份）
  python -X utf8 scripts/release_site.py --dry-run       # 只做预检 + 打印命令序列，不执行、不备份
  python -X utf8 scripts/release_site.py --skip-pagefind # 跳过可选 Pagefind（索引仍走 JSON）
  python -X utf8 scripts/release_site.py --strict        # Pagefind 失败/缺失也阻断；默认仅警告
  python -X utf8 scripts/release_site.py --backup-dir D:\\tmp\\releases  # 备份目录（默认 site/）

退出码：0 = GO；1 = NO-GO（含步骤失败）；2 = 预检失败/用法错误。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

WUXIA_ROOT = Path(__file__).resolve().parents[1]        # wuxia-kb/
REPO_ROOT = WUXIA_ROOT.parent                          # Wuxiaxiaoshuo/
SITE = REPO_ROOT / "site"
DIST = SITE / "dist"
DIST_BAK_RE = re.compile(r"^dist\.bak\.\d{8}_\d{6}$")
BASE_SEG = "wuxia-atlas"
DEFAULT_TIMEOUTS = {"export": 1800, "build": 900, "search": 600, "pagefind": 600,
                    "gate": 600, "scan": 600}
EXPORT_SCRIPT = WUXIA_ROOT / "scripts" / "export_site_all.py"
SEARCH_SCRIPT = WUXIA_ROOT / "scripts" / "build_search_index.py"
SCAN_SCRIPT = WUXIA_ROOT / "logs" / "qa" / "_site_acceptance_scan.py"
GATE_SCRIPT = REPO_ROOT / "scripts" / "copyright_gate.py"
SCAN_JSON = WUXIA_ROOT / "logs" / "qa" / "site_acceptance_scan.json"
QA_DIR = WUXIA_ROOT / "logs" / "qa"


def _which(name: str) -> str | None:
    exe = shutil.which(name)
    if exe:
        return exe
    for suffix in (".cmd", ".exe", ".bat"):
        exe = shutil.which(name + suffix)
        if exe:
            return exe
    return None


def _fmt_cmd(cmd: list[str]) -> str:
    out = []
    for c in cmd:
        c = str(c)
        out.append(f'"{c}"' if " " in c else c)
    return " ".join(out)


class Runner:
    def __init__(self, log_path: Path, dry_run: bool = False):
        self.log_path = log_path
        self.dry_run = dry_run
        self.lines: list[str] = []
        self.steps: list[dict] = []

    def log(self, msg: str = "") -> None:
        print(msg)
        self.lines.append(msg)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(msg + "\n")

    def run(self, name: str, cmd: list[str], cwd: Path, timeout: int,
            required: bool = True, env: dict | None = None) -> dict:
        step = {"name": name, "cmd": _fmt_cmd([str(c) for c in cmd]), "cwd": str(cwd),
                "required": required, "ok": False, "code": None, "seconds": None,
                "stdout_tail": "", "stderr_tail": ""}
        self.log(f"\n[release] ▶ {name}")
        self.log(f"[release]   $ {step['cmd']}")
        if self.dry_run:
            self.log("[release]   (dry-run：未执行)")
            step.update(ok=True, code=0, seconds=0, skipped_dry_run=True)
            self.steps.append(step)
            return step
        t0 = datetime.now()
        try:
            proc = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout, env=env)
            step["code"] = proc.returncode
            step["stdout_tail"] = (proc.stdout or "")[-4000:]
            step["stderr_tail"] = (proc.stderr or "")[-2000:]
        except FileNotFoundError as e:
            step["code"] = 127
            step["stderr_tail"] = f"FileNotFoundError: {e}"
        except subprocess.TimeoutExpired as e:
            step["code"] = 124
            step["stderr_tail"] = f"TimeoutExpired({timeout}s): {e}"
        step["seconds"] = round((datetime.now() - t0).total_seconds(), 1)
        step["ok"] = step["code"] == 0 and required or (step["code"] == 0 and not required)
        if step["stdout_tail"]:
            self.log(step["stdout_tail"].rstrip()[-2500:])
        if step["stderr_tail"]:
            self.log("[stderr] " + step["stderr_tail"].rstrip()[-1200:])
        self.log(f"[release]   exit={step['code']} · {step['seconds']}s · "
                 f"{'OK' if step['ok'] else ('WARN（非阻断）' if not required else 'FAIL')}")
        self.steps.append(step)
        return step


def _parse_int(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text or "")
    return int(m.group(1)) if m else None


def _load_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def preflight() -> list[tuple[str, bool, str]]:
    npm = _which("npm")
    npx = _which("npx")
    checks = [
        ("export_site_all.py", EXPORT_SCRIPT.exists(), str(EXPORT_SCRIPT)),
        ("build_search_index.py", SEARCH_SCRIPT.exists(), str(SEARCH_SCRIPT)),
        ("_site_acceptance_scan.py", SCAN_SCRIPT.exists(), str(SCAN_SCRIPT)),
        ("copyright_gate.py", GATE_SCRIPT.exists(), str(GATE_SCRIPT)),
        ("site/package.json", (SITE / "package.json").exists(), str(SITE / "package.json")),
        ("npm", bool(npm), npm or "未找到"),
        ("npx", bool(npx), npx or "未找到（--skip-pagefind 可跳过）"),
        ("site/node_modules", (SITE / "node_modules").is_dir(), str(SITE / "node_modules")),
        ("python", True, sys.executable),
    ]
    return checks


def backup_dist(backup_dir: Path, log: Runner) -> Path | None:
    if not DIST.is_dir():
        log.log("[release] （无现有 dist，跳过备份——首次发布）")
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"dist.bak.{_ts()}"
    shutil.copytree(DIST, target)
    log.log(f"[release] 备份旧 dist → {target}")
    return target


def write_summary(log: Runner, result: dict) -> Path:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    out = log.log_path.parent / "summary.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    latest = QA_DIR / "release_latest_summary.json"
    latest.write_text(out.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    if result.get("go") is True:  # 成功发布快照（失败尝试只留 release_<ts>/ 供审计）
        last_go = QA_DIR / "release_last_go_summary.json"
        last_go.write_text(out.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="一键发布编排（导出契约→build→搜索索引→Pagefind→版权闸门→验收扫描）")
    ap.add_argument("--dry-run", action="store_true", help="只预检+打印命令序列，不执行、不备份")
    ap.add_argument("--skip-pagefind", action="store_true", help="跳过可选 Pagefind 全文索引（JSON 搜索仍工作）")
    ap.add_argument("--backup-dir", default=str(SITE), metavar="DIR",
                    help="旧 dist 备份目录（默认 site/，生成 dist.bak.<ts>）")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式：Pagefind 失败/缺失也计为阻断（默认仅警告；--skip-pagefind 时忽略）")
    args = ap.parse_args()

    ts = _ts()
    run_dir = QA_DIR / f"release_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    runner = Runner(run_dir / "release.log", dry_run=args.dry_run)
    runner.log(f"# 一站式发布 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    runner.log(f"- 模式：{'dry-run（预检）' if args.dry_run else '正式发布'}"
               f"{' · strict' if args.strict else ''}{' · skip-pagefind' if args.skip_pagefind else ''}")
    runner.log(f"- 站点：{SITE}")
    runner.log(f"- 日志目录：{run_dir}")

    # ---- 预检 ----
    checks = preflight()
    preflight_ok = all(ok for _, ok, _ in checks
                       if _ not in ("npx",) or not args.skip_pagefind)
    runner.log("\n[release] 预检：")
    for name, ok, detail in checks:
        mandatory = not (name == "npx" and args.skip_pagefind)
        runner.log(f"  {'✅' if ok else ('⚠️ ' if not mandatory else '❌')} {name}: {detail}")
    if not preflight_ok:
        runner.log("[release] ❌ 预检失败：缺少必需工具/文件")
        write_summary(runner, {"ts": ts, "mode": "dry-run" if args.dry_run else "release",
                               "go": False, "reason": "preflight_failed",
                               "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
                               "steps": []})
        return 2

    plan = [
        ("0 备份", "旧 dist → dist.bak.<ts>"),
        ("1 导出契约", f'"{sys.executable}" -X utf8 "{EXPORT_SCRIPT}"  (要求 hard_gap=0)'),
        ("2 构建", f'"{_which("npm")}" run build   (cwd={SITE})'),
        ("3 搜索索引", f'"{sys.executable}" -X utf8 "{SEARCH_SCRIPT}"'),
        ("4 Pagefind", "跳过（--skip-pagefind）" if args.skip_pagefind
         else f'"{_which("npx")}" --yes pagefind@1.6.0 --site dist'),
        ("5 版权闸门", f'"{sys.executable}" -X utf8 "{GATE_SCRIPT}" "{DIST}" {BASE_SEG}'),
        ("6 验收扫描", f'"{sys.executable}" -X utf8 "{SCAN_SCRIPT}"'),
        ("7 汇总", "go/no-go → logs/qa/release_<ts>/summary.json"),
    ]
    runner.log("\n[release] 计划：")
    for name, desc in plan:
        runner.log(f"  {name:<10} {desc}")

    if args.dry_run:
        runner.log("\n[release] dry-run 完成（未执行任何步骤、未备份）。")
        write_summary(runner, {"ts": ts, "mode": "dry-run", "go": None,
                               "preflight_ok": True, "plan": [{"step": n, "desc": d} for n, d in plan],
                               "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]})
        return 0

    # ---- 0 备份 ----
    backup = None
    try:
        backup = backup_dist(Path(args.backup_dir).expanduser().resolve(), runner)
    except OSError as e:
        runner.log(f"[release] ❌ 备份失败：{e}（为可回滚，终止发布）")
        write_summary(runner, {"ts": ts, "mode": "release", "go": False, "reason": "backup_failed",
                               "error": str(e), "steps": runner.steps})
        return 1

    # ---- 1 导出契约（dry-run）----
    st = runner.run("1 导出契约（dry-run）", [sys.executable, "-X", "utf8", str(EXPORT_SCRIPT)],
                    WUXIA_ROOT, DEFAULT_TIMEOUTS["export"])
    hard_gap = _parse_int(r"hard_gap\s*合计\s*=\s*(\d+)", st["stdout_tail"])
    export_ok = st["ok"] and hard_gap == 0
    if not export_ok:
        runner.log(f"[release] ❌ NO-GO @ 导出契约（exit={st['code']}, hard_gap={hard_gap}）")
        write_summary(runner, {"ts": ts, "mode": "release", "go": False, "reason": "export_contract",
                               "hard_gap": hard_gap, "backup": str(backup) if backup else None,
                               "steps": runner.steps})
        return 1

    # ---- 2 build ----
    npm = _which("npm")
    st = runner.run("2 构建（npm run build）", [npm, "run", "build"], SITE, DEFAULT_TIMEOUTS["build"])
    pages = _parse_int(r"(\d+)\s+page\(s\)\s+built", st["stdout_tail"])
    if not (st["ok"] and pages and pages > 0):
        runner.log(f"[release] ❌ NO-GO @ 构建（exit={st['code']}, pages={pages}）")
        write_summary(runner, {"ts": ts, "mode": "release", "go": False, "reason": "build",
                               "pages": pages, "backup": str(backup) if backup else None,
                               "steps": runner.steps})
        return 1

    # ---- 3 搜索索引 ----
    st = runner.run("3 搜索索引", [sys.executable, "-X", "utf8", str(SEARCH_SCRIPT)],
                    WUXIA_ROOT, DEFAULT_TIMEOUTS["search"])
    entries = _parse_int(r"entries=(\d+)", st["stdout_tail"])
    if not (st["ok"] and entries and entries > 0):
        runner.log(f"[release] ❌ NO-GO @ 搜索索引（exit={st['code']}, entries={entries}）")
        write_summary(runner, {"ts": ts, "mode": "release", "go": False, "reason": "search_index",
                               "entries": entries, "backup": str(backup) if backup else None,
                               "steps": runner.steps})
        return 1

    # ---- 4 Pagefind（可选）----
    pagefind = {"skipped": args.skip_pagefind, "ok": False, "required": args.strict}
    if args.skip_pagefind:
        runner.log("\n[release] ▶ 4 Pagefind：已跳过（--skip-pagefind）")
    else:
        npx = _which("npx")
        if not npx:
            pagefind.update(ok=False, error="未找到 npx")
            runner.log("[release] ▶ 4 Pagefind：未找到 npx → 跳过（JSON 搜索仍工作）")
        else:
            st = runner.run("4 Pagefind（可选）", [npx, "--yes", "pagefind@1.6.0", "--site", "dist"],
                            SITE, DEFAULT_TIMEOUTS["pagefind"], required=False)
            pf_pages = _parse_int(r"Indexed\s+(\d+)\s+pages", st["stdout_tail"])
            pf_entry = DIST / "pagefind" / "pagefind-entry.json"
            pagefind.update(ok=bool(st["ok"] and pf_entry.exists()),
                            pages=pf_pages, exit=st["code"])
            if pagefind["ok"]:
                runner.log(f"[release]   Pagefind OK（{pf_pages} 页）")
            elif args.strict:
                runner.log("[release] ❌ NO-GO @ Pagefind（--strict 要求成功）")
                write_summary(runner, {"ts": ts, "mode": "release", "go": False, "reason": "pagefind",
                                       "pagefind": pagefind, "backup": str(backup) if backup else None,
                                       "steps": runner.steps})
                return 1
            else:
                runner.log("[release]   Pagefind 失败 → 仅警告（JSON 搜索兜底；--strict 可阻断）")

    have_pagefind = (DIST / "pagefind" / "pagefind-entry.json").exists()
    env = os.environ.copy()
    if args.skip_pagefind or not have_pagefind:
        env["SITE_ACCEPT_SKIP_PAGEFIND"] = "1"

    # ---- 5 版权闸门 ----
    st = runner.run("5 版权闸门", [sys.executable, "-X", "utf8", str(GATE_SCRIPT), str(DIST), BASE_SEG],
                    WUXIA_ROOT, DEFAULT_TIMEOUTS["gate"])
    gate_ok = st["ok"] and "✓ 版权闸门通过" in st["stdout_tail"]
    if not gate_ok:
        runner.log("[release] ❌ NO-GO @ 版权闸门（详见日志）")
        write_summary(runner, {"ts": ts, "mode": "release", "go": False, "reason": "copyright_gate",
                               "backup": str(backup) if backup else None, "steps": runner.steps})
        return 1

    # ---- 6 验收扫描 ----
    st = runner.run("6 验收扫描", [sys.executable, "-X", "utf8", str(SCAN_SCRIPT)],
                    WUXIA_ROOT, DEFAULT_TIMEOUTS["scan"], env=env)
    scan = _load_json(SCAN_JSON) or {}
    failures = scan.get("failures") or []
    links = (scan.get("checks") or {}).get("links") or {}
    missing = links.get("missing_total")
    scan_ok = st["ok"] and not failures and missing == 0
    if not scan_ok:
        runner.log(f"[release] ❌ NO-GO @ 验收扫描（exit={st['code']}, failures={failures[:5]}, missing={missing}）")
        write_summary(runner, {"ts": ts, "mode": "release", "go": False, "reason": "acceptance_scan",
                               "scan_failures": failures, "missing_links": missing,
                               "backup": str(backup) if backup else None, "steps": runner.steps})
        return 1

    # ---- 7 GO 汇总 ----
    counts = (scan.get("checks") or {}).get("counts") or {}
    display = (scan.get("checks") or {}).get("display") or {}
    search = (scan.get("checks") or {}).get("search") or {}
    result = {
        "ts": ts, "mode": "release", "go": True, "strict": args.strict,
        "backup": str(backup) if backup else None,
        "export": {"hard_gap": hard_gap},
        "build": {"pages": pages},
        "search_index": {"entries": entries},
        "pagefind": pagefind,
        "copyright_gate": {"ok": True},
        "acceptance": {"failures": failures, "missing_links": missing,
                       "links_checked": links.get("checked"),
                       "pages": counts, "display_overrides": display.get("pages_title_differs_from_canonical"),
                       "search_entries": search.get("entries")},
        "steps": runner.steps,
    }
    summary = write_summary(runner, result)
    runner.log("\n[release] ✅ GO — 发布链全部通过")
    runner.log(f"[release]   构建 {pages} 页 · 搜索索引 {entries} 条 · 链接检查 {links.get('checked')} 条（缺失 0）")
    runner.log(f"[release]   备份：{backup if backup else '（无旧 dist）'}")
    runner.log(f"[release]   汇总：{summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
