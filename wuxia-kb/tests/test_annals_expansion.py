# -*- coding: utf-8 -*-
"""W2-B3 · 史实锚年谱扩容测试（天山演示版总体方案 §4.2 B3，2026-11-10）。

口径固化（测试即规范）：
  1. 校定行扩容 ≥30（现有 E-1735-yuanxiao / E-1735-death / E-1615-taiji 保留），覆盖天山
     7 书时代跨度（明·景泰后 → 清·雍正后），每书至少 1 条史实锚；
  2. 纪年档纪律：明文纪年必填 m/d 才进 daily_index；推定/段/不详纵有 m/d 也不进
     （build_annals.collect 新增守门——史实档沿现状，m/d 齐则入）；
  3. scope 过滤：book ∈ 7 书（tianshan-demo）才保留，daily 同步；全量口径（scope=None）
     meta 无 scope 键（方案 R6）；
  4. 史实/剧情双型：type ∈ {史实,剧情}，双型并存（史实→■、剧情→● 为页面消费约定）；
  5. 冲突对照：E-1735-death（史实）conflict_hist 以事件 id 回指 E-1735-yuanxiao（剧情），
     两者共享关联人物——页面配对机制（id 互指 / 共享人物）的数据契约；
  6. 朝代分段契约：年号关键词决定分段（timeline.astro DYN 表）——数字年 ≥1644 的行，
     y+basis 必含 清段 关键词（顺治/康熙/雍正/乾隆/嘉庆/道光）；≤1636 的行必不含。
  7. loc 红线：每行 loc 指向的 tagged 文件真实存在且行号不越界。
"""
import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "wuxia-kb" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_annals  # noqa: E402

TSV = REPO_ROOT / "kb" / "校订" / "史实锚年谱.tsv"
TAGGED = REPO_ROOT / "wuxia-kb" / "tagged"

SCOPE_BOOKS = ["散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
               "七剑下天山", "冰魄寒光剑", "江湖三女侠"]
SCOPE = {"profile": "tianshan-demo", "books": SCOPE_BOOKS}
LEGACY_IDS = {"E-1735-yuanxiao", "E-1735-death", "E-1615-taiji"}
QING_KEYS = ("顺治", "康熙", "雍正", "乾隆", "嘉庆", "道光")


def _load_rows():
    with open(TSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f.read().splitlines(), delimiter="\t"))


def _calibrated(rows):
    return [r for r in rows if (r.get("status") or "").strip() == "校定"]


def _book_col(rows):
    return [(r.get("book") or "").strip() for r in rows]


def _row(rid, book="白发魔女传", grade="史实", m="", d="", status="校定", y="1620"):
    return {"id": rid, "type": "史实", "name": f"事件{rid}", "y": y, "m": m, "d": d,
            "date_grade": grade, "date_basis": "", "book": book, "loc": "001:001",
            "people": "", "line": "一行", "conflict_hist": "", "status": status}


# ================================================================ 1. 扩容规模与覆盖（先红）
class TestExpansion:
    def test_calibrated_rows_at_least_30(self):
        """校定行 ≥30（B3：4→30–50），旧 3 行保留。"""
        rows = _calibrated(_load_rows())
        assert len(rows) >= 30, f"校定行仅 {len(rows)} 行（目标 ≥30）"
        assert LEGACY_IDS <= {r["id"] for r in rows}

    def test_era_span_and_per_book_coverage(self):
        """覆盖 7 书时代跨度：7 书各有 ≥1 条史实锚；明（≤1636）与清（≥1644）两段都有。"""
        rows = _calibrated(_load_rows())
        books = set(_book_col(rows))
        assert set(SCOPE_BOOKS) <= books, f"缺书：{set(SCOPE_BOOKS) - books}"
        ming = [r for r in rows if _num_year(r) and _num_year(r) <= 1636]
        qing = [r for r in rows if _num_year(r) and _num_year(r) >= 1644]
        assert ming and qing, "明/清两段须都有数字年锚点"

    def test_new_rows_keep_schema(self):
        """列结构与既有口径一致；type ∈ {史实,剧情}；grade ∈ 五档。"""
        with open(TSV, encoding="utf-8", newline="") as f:
            header = f.read().splitlines()[0].split("\t")
        assert header == ["id", "type", "name", "y", "m", "d", "date_grade", "date_basis",
                          "book", "loc", "people", "line", "conflict_hist", "status"]
        rows = _calibrated(_load_rows())
        for r in rows:
            assert r["type"] in ("史实", "剧情"), r["id"]
            assert r["date_grade"] in ("明文", "推定", "段", "不详", "史实"), r["id"]
            assert (r["line"] or "").strip(), f"{r['id']} 缺 L0 一句话"


def _num_year(row):
    y = (row.get("y") or "").strip()
    return int(y) if y.isdigit() else None


# ================================================================ 2. daily_index 纪年档纪律
class TestDailyDiscipline:
    def test_full_md_row_enters_daily(self):
        annals, daily = build_annals.build_payloads([_row("A1", m="3", d="15")])
        assert "03-15" in daily["index"]

    def test_grade_duan_tui_bu_excluded_even_with_md(self):
        """推定/段/不详 纵有 m/d 也不入 daily（B3 纪年纪律，collect 新守门）。"""
        for grade in ("推定", "段", "不详"):
            annals, daily = build_annals.build_payloads(
                [_row(f"A-{grade}", grade=grade, m="3", d="15")])
            assert daily["index"] == {}, f"grade={grade} 不应入 daily"
            assert len(annals["events"]) == 1        # 事件仍保留，只是不入确日索引

    def test_real_rows_daily_only_mingwen_or_shishi(self):
        """真实 TSV：daily 内条目的纪年档只许 明文/史实；明文有 m/d 必在 daily。"""
        rows = _calibrated(_load_rows())
        annals, daily = build_annals.build_payloads(rows)
        in_daily = {e["id"] for evs in daily["index"].values() for e in evs}
        by_id = {e["id"]: e for e in annals["events"]}
        for eid in in_daily:
            assert by_id[eid]["date"]["grade"] in ("明文", "史实"), eid
        for r in rows:
            if (r.get("date_grade") or "").strip() == "明文" and \
                    (r.get("m") or "").strip() and (r.get("d") or "").strip():
                key = f"{int(r['m']):02d}-{int(r['d']):02d}"
                assert r["id"] in {e["id"] for e in daily["index"].get(key, [])}


# ================================================================ 3. scope 过滤与全量口径 R6
class TestScopeAndFullCaliber:
    def test_scope_filters_out_of_scope_and_daily_rebuilt(self):
        rows = _calibrated(_load_rows()) + [_row("X-out", book="萍踪侠影录", m="1", d="1")]
        annals, daily = build_annals.build_payloads(rows, scope=SCOPE)
        assert "X-out" not in {e["id"] for e in annals["events"]}
        assert "X-out" not in {e["id"] for evs in daily["index"].values() for e in evs}
        assert set(_book_col(annals["events"])) <= set(SCOPE_BOOKS)

    def test_full_caliber_meta_no_scope_key(self):
        rows = _calibrated(_load_rows())
        annals, daily = build_annals.build_payloads(rows)
        assert "scope" not in annals["meta"] and "scope" not in daily["meta"]
        assert len(annals["events"]) == len(rows)


# ================================================================ 4. 双型与冲突对照
class TestTypesAndConflict:
    def test_dual_types_present(self):
        """史实/剧情双型并存（史实→■、剧情→● 由页面按 type 推导）。"""
        events = build_annals.build_payloads(_calibrated(_load_rows()))[0]["events"]
        types = {e["type"] for e in events}
        assert {"史实", "剧情"} <= types
        mark = {"史实": "■", "剧情": "●"}
        for e in events:
            assert mark[e["type"]] in ("■", "●")

    def test_conflict_pair_yuanxiao_death(self):
        """冲突对照固化 1 例：剧情锚 E-1735-yuanxiao × 史实锚 E-1735-death。

        页面配对沿 ①conflict_hist 事件 id 互指、②共享关联人物两条通道（timeline.astro）；
        此处固化数据契约：史实行 conflict_hist 回指剧情行 id，且共享人物非空。
        """
        events = build_annals.build_payloads(_calibrated(_load_rows()))[0]["events"]
        by_id = {e["id"]: e for e in events}
        p, h = by_id["E-1735-yuanxiao"], by_id["E-1735-death"]
        assert p["type"] == "剧情" and h["type"] == "史实"
        assert p["conflict_hist"] and h["conflict_hist"]
        assert "E-1735-yuanxiao" in h["conflict_hist"]          # id 互指通道
        assert set(p["people"]) & set(h["people"])              # 共享人物通道


# ================================================================ 5. 朝代分段契约（timeline DYN 表）
class TestDynastyContract:
    def test_numeric_qing_years_carry_reign_keyword(self):
        """数字年 ≥1644 的行，y+basis 必含 清段 年号词——否则 timeline 会被错归「元明」段。"""
        events = build_annals.build_payloads(_calibrated(_load_rows()))[0]["events"]
        for e in events:
            y = _num_year({"y": e["date"]["y"] or ""})
            if y is not None and y >= 1644:
                text = f"{e['date']['y'] or ''} {e['date']['basis'] or ''}"
                assert any(k in text for k in QING_KEYS), \
                    f"{e['id']}（y={y}）缺 清段 年号词（顺治/康熙/雍正/乾隆…）"

    def test_ming_years_free_of_qing_keywords(self):
        """数字年 ≤1636 的行不得含 清段 年号词（防错归清段）。"""
        events = build_annals.build_payloads(_calibrated(_load_rows()))[0]["events"]
        for e in events:
            y = _num_year({"y": e["date"]["y"] or ""})
            if y is not None and y <= 1636:
                text = f"{e['date']['y'] or ''} {e['date']['basis'] or ''}"
                assert not any(k in text for k in QING_KEYS), \
                    f"{e['id']}（y={y}）含 清段 年号词"


# ================================================================ 6. loc 红线：语料可查
class TestLocIntegrity:
    def test_all_locs_resolve_in_tagged_corpus(self):
        """每行 loc = 章:行 指向 wuxia-kb/tagged/<书>/<NNN>.tagged.md 的真实行。"""
        for r in _calibrated(_load_rows()):
            book, loc = r["book"], (r.get("loc") or "").strip()
            assert book and loc, r["id"]
            chap, line = loc.split(":")
            f = TAGGED / book / f"{int(chap):03d}.tagged.md"
            assert f.exists(), f"{r['id']}: tagged 文件缺失 {f}"
            n = len(f.read_text(encoding="utf-8").splitlines())
            assert 1 <= int(line) <= n, f"{r['id']}: 行号越界 {loc}（文件共 {n} 行）"
