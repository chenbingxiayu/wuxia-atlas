# -*- coding: utf-8 -*-
"""EX 导出层集成器（docs/51 §六 阶段 1 收口 + 阶段 2/3：EX-4/7/8）。

按顺序运行 7 个导出器（默认 dry-run），汇总每个 data 文件的契约硬缺口与记录数，
写总报告 `logs/export/reports/_integration.md`；任一导出器失败或 hard_gap>0 则 exit 1。

W0-T3a（天山演示版总体方案 §1.2，2026-11-08）：--scope <profile> 解析后向每个子导出器
子进程透传（export_site_common.scope_from_args / load_scope）；`--scope all` 与不传参数
同为全量口径（不透传，现状不变，方案 R6）。scope 口径下契约复核对旧契约中的 scope 外
书键按"预期裁剪"处理（esc.diff_staging，不计 hard_gap）。

用法：
  python scripts/export_site_all.py              # dry-run（只写 staging/reports）
  python scripts/export_site_all.py --apply      # 应用（先自动备份 site/data，谨慎）
  python scripts/export_site_all.py --check-only # 只对现有 staging 做契约复核
  python scripts/export_site_all.py --scope tianshan-demo   # 天山 7 书裁剪口径（透传子导出器）
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import config
import export_site_common as esc

EXPORTERS = [
    ("EX-1 books/chapters", "export_site_books_chapters.py", ["books.json", "chapters.json"]),
    ("EX-2 characters/entity-index", "export_site_characters.py", ["characters.json", "entity-index.json"]),
    ("EX-3 dossiers", "export_site_dossiers.py", ["dossiers.json"]),
    ("EX-4 graph", "export_site_graph.py", ["graph.json"]),
    ("EX-5 matches/ratings", "export_site_matches_ratings.py", ["matches.json", "ratings.json"]),
    ("EX-6 sects/weapons/arts", "export_site_sects_weapons_arts.py", ["sects.json", "weapons.json", "arts.json"]),
    # EX-7 另含 atlas/<书>.json（嵌套切片由导出器自行落 staging）；W0-T4 起 atlas/state.json
    # 亦由 EX-7 接管产出（原 build_atlas_slices.py 已废弃标注），集成器一并校验
    ("EX-7 gazetteer/universe", "export_site_gazetteer_universe.py",
     ["gazetteer.json", "universe.json", "atlas/state.json"]),
    ("EX-8 audit", "export_site_audit.py", ["audit.json"]),
]

EXPORTED_FILES = [name for _, _, names in EXPORTERS for name in names]


def exporter_cmd(script_path: Path, apply: bool, scope=None) -> list:
    """子导出器命令行（W0-T3a：scope 口径向子进程透传 --scope <profile>；全量口径不透传）。"""
    cmd = [sys.executable, str(script_path)]
    if apply:
        cmd.append("--apply")
    if scope is not None:
        cmd += ["--scope", scope["profile"]]
    return cmd


def run_exporters(apply: bool, scope=None) -> dict:
    results = {}
    for label, script, names in EXPORTERS:
        script_path = config.DIR_SCRIPTS / script
        if not script_path.exists():
            results[label] = {"exit": 127, "names": names, "stderr": "脚本不存在"}
            print(f"[all] ✗ {label}: 脚本不存在 {script_path}")
            continue
        cmd = exporter_cmd(script_path, apply, scope)
        print(f"[all] → {label}: {' '.join(cmd)}")
        proc = subprocess.run(cmd, cwd=str(config.ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        tail = (proc.stdout or "")[-800:]
        print(tail)
        if proc.returncode != 0:
            print(f"[all] ✗ {label} exit={proc.returncode}\n{(proc.stderr or '')[-1200:]}")
        results[label] = {"exit": proc.returncode, "names": names,
                          "stdout_tail": tail, "stderr_tail": (proc.stderr or "")[-1200:]}
    return results


def check_staging() -> list[dict]:
    rows = []
    for name in EXPORTED_FILES:
        p = esc.STAGING / name
        row = {"name": name, "exists": p.exists()}
        if p.exists():
            payload = esc.load_json(p)
            # W0-T3a：scope 感知复核（payload meta.scope 存在时 scope 外书键=预期裁剪）
            diff = esc.diff_staging(name, payload)
            row.update({
                "hard_gap": diff["hard_gap_count"],
                "old_records": diff["old_record_count"],
                "new_records": diff["new_record_count"],
                "missing": len(diff["missing_keys"]),
                "type_mismatch": len(diff["type_mismatch"]),
                "item_missing": len(diff["item_missing_keys"]),
                "extra": len(diff["extra_keys"]),
                "bytes": p.stat().st_size,
                "field_gaps": len(payload.get("meta", {}).get("field_gaps", []) if isinstance(payload, dict) else []),
            })
        rows.append(row)
    return rows


def render(rows: list[dict], exporter_results: dict, apply: bool, scope=None) -> str:
    lines = [
        "# EX 导出层集成报告（阶段 1）",
        "",
        f"- 生成：{esc.now_iso()}",
        f"- 模式：{'APPLY（已写 site/data，执行前已备份）' if apply else 'dry-run（staging only）'}",
        f"- 导出器：{[label for label, _, _ in EXPORTERS]}",
        f"- 书目范围：{'全量口径（无 --scope）' if scope is None else f'scope={scope["profile"]}（{len(scope["books"])} 书）'}",
        "",
        "## 导出器执行",
        "",
        "| 导出器 | exit | 输出 |",
        "|---|---:|---|",
    ]
    for label, _, names in EXPORTERS:
        r = exporter_results.get(label, {})
        lines.append(f"| {label} | {r.get('exit', '—')} | {', '.join(names)} |")

    lines += [
        "",
        "## 契约复核（staging vs 2026-11-02 旧站契约）",
        "",
        "| 文件 | 旧记录 | 新记录 | hard_gap | 缺字段 | 类型不符 | 元素缺字段 | 新增字段 | field_gaps | 大小 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    total_hard = 0
    for row in rows:
        if not row["exists"]:
            lines.append(f"| {row['name']} | — | — | **MISSING** | — | — | — | — | — | — |")
            total_hard += 1
            continue
        total_hard += row["hard_gap"]
        lines.append(
            f"| {row['name']} | {row['old_records']} | {row['new_records']} | {row['hard_gap']} | "
            f"{row['missing']} | {row['type_mismatch']} | {row['item_missing']} | "
            f"{row['extra']} | {row['field_gaps']} | {row['bytes'] // 1024} KB |"
        )
    lines += [
        "",
        f"- **hard_gap 合计 = {total_hard}**（0 = 契约字段不缺、类型不破）",
        "",
        "## 判定",
        "",
        f"- {'✅ 阶段 1 dry-run 通过（待 --apply + 站点构建验收）' if total_hard == 0 else '❌ 存在契约硬缺口，见各文件报告'}",
        "",
        "## 下一步（--apply 验收）",
        "",
        "1. `python scripts/export_site_all.py --apply`（自动备份 site/data 到 backup/site_data/apply_<时间>/）；",
        "2. `cd ../site && npm run build`，检查 38 页构建 exit 0；",
        "3. 失败则从备份恢复 `backup/site_data/phase0_20261105/`（阶段 0 全量快照）。",
        "",
    ]
    return "\n".join(lines)


def main():
    apply = "--apply" in sys.argv
    check_only = "--check-only" in sys.argv
    # W0-T3a：--scope 解析（--scope all / 不传 = 全量口径，None）
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    exporter_results = {} if check_only else run_exporters(apply, scope)
    rows = check_staging()
    report = render(rows, exporter_results, apply, scope=scope)
    out = esc.REPORTS_DIR / "_integration.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"[all] 报告 → {out}")
    total_hard = sum(r.get("hard_gap", 1) for r in rows)
    failed = [label for label, r in exporter_results.items() if r.get("exit") not in (0, None)]
    if failed:
        print(f"[all] ❌ 导出器失败：{failed}")
    print(f"[all] hard_gap 合计 = {total_hard}")
    return 0 if total_hard == 0 and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
