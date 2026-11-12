# -*- coding: utf-8 -*-
"""W2-B4 · book_states（跨书生命弧）并入测试（天山演示版总体方案 §4.2 B4，2026-11-10）。

被测（scripts/build_plots.py W2-B4 增量）：
  parse_book_states(rows, in_scope)   书内状态.tsv 行 → {person: [{book, state}]}
  load_book_states(scope, path)       读 kb/校订/书内状态.tsv（默认路径），scope 过滤
  build_payload(..., book_states=...) 并入 char_plots.characters[person].book_states

口径固化（测试即规范）：
  - 并入：status=校定 的状态行 → characters[person].book_states = [{book, state}, …]，
    顺序 = TSV 文件行序（编年由考订人在表内自控）；
  - 缺失不生成：人物在锚点表有剧情但状态表无行 → 不带 book_states 键（宇宙页 arcOf 静默）；
  - 校定过滤：status=draft（或空）的状态行不并入；
  - scope 过滤：book 不在 scope 书单内 → 剔除（全量口径 scope=None 不过滤）；
  - 生产表冒烟：kb/校订/书内状态.tsv 存在、表头 4 列、演示 6 人全覆盖且全为校定。
"""
import csv
import sys
from pathlib import Path

import pytest

# 被测模块（父仓 scripts/）；export_site_common（wuxia-kb/scripts/）——两处显式入 path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "wuxia-kb" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_plots as bp  # noqa: E402
import export_site_common as esc  # noqa: E402


def write_states_tsv(path: Path, rows: list) -> None:
    """写状态表（正式 4 列 schema：person/book/state/status）。"""
    lines = ["person\tbook\tstate\tstatus"]
    for r in rows:
        lines.append("\t".join([r["person"], r["book"], r["state"], r.get("status", "校定")]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


PLOT_ROW = {
    "person": "凌未风", "seq": "1", "name": "荒坟血战", "tags": "恩怨仇杀",
    "book": "七剑下天山", "chap": "0", "line": "27", "date_value": "清初", "date_grade": "段",
    "date_basis": "楔子年代段", "place_name": "", "place_anchor": "", "place_status": "无",
    "place_candidates": "", "one_liner": "荒坟月下双剑迎敌。", "status": "校定",
    "editor": "test", "date": "2026-11-10",
}


def _payload(state_rows, scope=None, path=None):
    states = bp.load_book_states(scope=scope, path=path) if path else \
        bp.parse_book_states(state_rows, lambda b: esc.in_scope(b, scope))
    return bp.build_payload([dict(PLOT_ROW)], {}, scope=scope, book_states=states)


# ---------------------------------------------------------------- 并入
def test_merged_into_characters(tmp_path):
    """校定状态行 → characters[person].book_states 按文件行序并入。"""
    p = tmp_path / "书内状态.tsv"
    write_states_tsv(p, [
        {"person": "凌未风", "book": "七剑下天山", "state": "天山神芒 · 七剑之魂"},
        {"person": "凌未风", "book": "江湖三女侠", "state": "已成传说"},
    ])
    payload = _payload([], scope=None, path=p)
    arc = payload["characters"]["凌未风"].get("book_states")
    assert arc == [
        {"book": "七剑下天山", "state": "天山神芒 · 七剑之魂"},
        {"book": "江湖三女侠", "state": "已成传说"},
    ]


# ---------------------------------------------------------------- 缺失不生成
def test_missing_person_no_book_states():
    """锚点表有人物、状态表无行 → 不生成 book_states 键（渲染层静默）。"""
    payload = _payload([], scope=None)
    assert "凌未风" in payload["characters"]
    assert "book_states" not in payload["characters"]["凌未风"]


# ---------------------------------------------------------------- 校定过滤
def test_draft_status_excluded(tmp_path):
    """status=draft/空 的状态行不并入。"""
    p = tmp_path / "书内状态.tsv"
    write_states_tsv(p, [
        {"person": "凌未风", "book": "七剑下天山", "state": "草稿状态", "status": "draft"},
        {"person": "凌未风", "book": "江湖三女侠", "state": "校定状态", "status": "校定"},
    ])
    payload = _payload([], scope=None, path=p)
    arc = payload["characters"]["凌未风"]["book_states"]
    assert arc == [{"book": "江湖三女侠", "state": "校定状态"}]


# ---------------------------------------------------------------- scope 过滤
def test_scope_filters_book():
    """scope 口径：状态行 book ∈ scope 才保留；全量口径不过滤。"""
    rows = [
        {"person": "凌未风", "book": "七剑下天山", "state": "在 scope", "status": "校定"},
        {"person": "凌未风", "book": "云海玉弓缘", "state": "scope 外", "status": "校定"},
    ]
    scope = esc.load_scope("tianshan-demo")
    payload = _payload(rows, scope=scope)
    assert payload["characters"]["凌未风"]["book_states"] == [
        {"book": "七剑下天山", "state": "在 scope"}]
    payload_all = _payload(rows, scope=None)
    assert [s["book"] for s in payload_all["characters"]["凌未风"]["book_states"]] == \
        ["七剑下天山", "云海玉弓缘"]


# ---------------------------------------------------------------- 生产表冒烟
def test_production_tsv_smoke():
    """生产状态表存在、4 列表头、演示 6 人全覆盖、全行校定、状态句 ≤20 字。"""
    p = REPO_ROOT / "kb" / "校订" / "书内状态.tsv"
    assert p.exists(), "缺 kb/校订/书内状态.tsv"
    with open(p, encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        rows = [r for r in reader if r]
    assert header == ["person", "book", "state", "status"]
    demo6 = {"凌云凤", "霍天都", "岳鸣珂", "凌未风", "易兰珠", "吕四娘"}
    persons = {r[0] for r in rows}
    assert demo6 <= persons, f"演示 6 人缺：{demo6 - persons}"
    assert all(r[3] == "校定" for r in rows), "存在非校定状态行"
    assert all(len(r[2]) <= 20 for r in rows), "状态句超过 20 字"
