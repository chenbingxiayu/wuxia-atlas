# -*- coding: utf-8 -*-
"""W2-B8 · 作品简介.tsv → books.json hook/summary 测试（作品页重构设计 §四②/§六，2026-11-10）。

被测对象：scripts/export_site_books_chapters.py 的
  load_intro_tsv(path)   读 kb/校订/作品简介.tsv（仅 status=校定 行；hook 超长报错不截断）
  build_books(…, intro=…) hook/summary 并入 books 对应书记录（scope 口径只并 scope 内书）
  _books_field_gaps      缺 TSV / 缺行时 field_gaps 显式声明（现状不变口径）
  _intro_notes           并入时 meta.notes 记源与规模

测试口径（先红后绿；除「真实 TSV 内容纪律」一节外全部用合成 fixture，不写 site/data）：
  - 缺 TSV → hook/summary 字段缺省（""）且 meta.field_gaps 声明（B8 前现状不变）；
  - scope 口径只并 scope 内书，scope 外校定行不消费；
  - hook 超长 → IntroError 报错（选定「报错」并固化：简介是人工校定稿，静默截断会改写编辑文本）；
  - 真实 kb/校订/作品简介.tsv 内容纪律：7 部校定行、hook ≤30 字、summary 3–5 句、
    不含书名号引文、不含站外书名（冰川天女传/云海玉弓缘等 27 部不得出现在 7 部 summary）。
"""
import csv
import json
import re
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（被测模块依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_books_chapters as exb  # noqa: E402

BOOK_A, BOOK_B = "测试书甲", "测试书乙"
SCOPE_A = {"profile": "demo", "books": [BOOK_A]}
HOOK_OK = "一句话钩子，不超过三十字。"
SUMMARY_OK = "第一句交代背景与人物。第二句讲人物关系。第三句止于第一幕的期待。"


def _wmeta(*books):
    return {"works": [{"book": b, "no": i + 1, "chars": 100 + i} for i, b in enumerate(books)],
            "missing_works": []}


def _corpus(*books):
    return {b: [{"no": 1, "title": "第一回"}, {"no": 2, "title": "第二回"}] for b in books}


def _write_tsv(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    """rows: (book, hook, summary, status) → tab 分隔 TSV（W2-B8 表头）。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["book", "hook", "summary", "status", "editor", "date"])
        for book, hook, summary, status in rows:
            w.writerow([book, hook, summary, status, "test", "2026-11-10"])


# ================================================================ 1. load_intro_tsv（读取与闸门）
class TestLoadIntroTsv:
    def test_missing_file_returns_empty(self, tmp_path):
        """文件不存在 → {}（缺省口径：字段置空 + field_gaps 声明，B8 前现状）。"""
        assert exb.load_intro_tsv(tmp_path / "不存在.tsv") == {}

    def test_parses_and_only_kept_status(self, tmp_path):
        """解析行 → {书: {hook, summary}}；仅 status=校定 行消费，draft/待校 行不进站点。"""
        p = tmp_path / "作品简介.tsv"
        _write_tsv(p, [
            (BOOK_A, HOOK_OK, SUMMARY_OK, "校定"),
            (BOOK_B, HOOK_OK, SUMMARY_OK, "draft"),
        ])
        intro = exb.load_intro_tsv(p)
        assert set(intro) == {BOOK_A}
        assert intro[BOOK_A] == {"hook": HOOK_OK, "summary": SUMMARY_OK}

    def test_hook_overlong_raises_not_truncate(self, tmp_path):
        """hook 超长（31 字 > 30 上限）→ IntroError 报错（固化：不静默截断编辑文本）。"""
        p = tmp_path / "作品简介.tsv"
        _write_tsv(p, [(BOOK_A, "钩" * 31, SUMMARY_OK, "校定")])
        with pytest.raises(exb.IntroError, match="超长"):
            exb.load_intro_tsv(p)

    def test_hook_at_limit_passes(self, tmp_path):
        """边界：hook 恰 30 字合法（30 字闸门不被误伤）。"""
        p = tmp_path / "作品简介.tsv"
        _write_tsv(p, [(BOOK_A, "钩" * 30, SUMMARY_OK, "校定")])
        assert exb.load_intro_tsv(p)[BOOK_A]["hook"] == "钩" * 30

    def test_duplicate_book_raises(self, tmp_path):
        """同书两行校定 → IntroError（唯一真源，不允许二义）。"""
        p = tmp_path / "作品简介.tsv"
        _write_tsv(p, [(BOOK_A, HOOK_OK, SUMMARY_OK, "校定"),
                       (BOOK_A, "另一句钩子。", SUMMARY_OK, "校定")])
        with pytest.raises(exb.IntroError, match="重复"):
            exb.load_intro_tsv(p)


# ================================================================ 2. build_books 并入（合成 fixture）
class TestBuildBooksIntro:
    def _legacy(self):
        return {"wmeta": _wmeta(BOOK_A, BOOK_B), "inter": {"edges": []}}

    def test_intro_merged_into_records(self):
        """校定行 → 对应书记录带 hook/summary；meta.notes 记源。"""
        intro = {BOOK_A: {"hook": HOOK_OK, "summary": SUMMARY_OK}}
        payload, _ = exb.build_books(_corpus(BOOK_A, BOOK_B), {}, legacy=self._legacy(), intro=intro)
        rec = {b["book"]: b for b in payload["books"]}
        assert rec[BOOK_A]["hook"] == HOOK_OK
        assert rec[BOOK_A]["summary"] == SUMMARY_OK
        assert any("hook/summary" in n for n in payload["meta"]["notes"])

    def test_missing_tsv_defaults_and_field_gaps(self, tmp_path, monkeypatch):
        """缺 TSV → hook/summary 字段缺省（""）且 field_gaps 声明（现状不变口径）。"""
        monkeypatch.setattr(exb, "INTRO_TSV", tmp_path / "不存在.tsv")
        payload, _ = exb.build_books(_corpus(BOOK_A, BOOK_B), {}, legacy=self._legacy(), intro=None)
        rec = {b["book"]: b for b in payload["books"]}
        assert rec[BOOK_A]["hook"] == "" and rec[BOOK_A]["summary"] == ""
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "hook/summary" in gaps and ("不存在" in gaps or "占位" in gaps)

    def test_scope_merges_only_scope_books(self):
        """scope 口径只并 scope 内书：乙书不在导出，甲书并入；scope 外校定行不消费不报错。"""
        intro = {BOOK_A: {"hook": HOOK_OK, "summary": SUMMARY_OK},
                 BOOK_B: {"hook": "乙书的钩子。", "summary": SUMMARY_OK}}
        payload, _ = exb.build_books(_corpus(BOOK_A, BOOK_B), {}, scope=SCOPE_A,
                                     legacy=self._legacy(), intro=intro)
        assert [b["book"] for b in payload["books"]] == [BOOK_A]
        assert payload["books"][0]["hook"] == HOOK_OK
        assert all(b["hook"] in ("", HOOK_OK) for b in payload["books"])
        assert "scope" in payload["meta"]

    def test_partial_coverage_declares_gap(self):
        """TSV 存在但部分书缺校定行 → 有行的并入，缺行的置空且 field_gaps 点名。"""
        intro = {BOOK_A: {"hook": HOOK_OK, "summary": SUMMARY_OK}}
        payload, _ = exb.build_books(_corpus(BOOK_A, BOOK_B), {}, legacy=self._legacy(), intro=intro)
        rec = {b["book"]: b for b in payload["books"]}
        assert rec[BOOK_A]["hook"] == HOOK_OK
        assert rec[BOOK_B]["hook"] == ""
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert BOOK_B in gaps and "hook/summary" in gaps

    def test_unmatched_rows_noted(self):
        """TSV 有行但书名不在导出书目（如全量外的误名）→ 不并入，meta.notes 记录。"""
        intro = {"不存在的书": {"hook": HOOK_OK, "summary": SUMMARY_OK}}
        payload, _ = exb.build_books(_corpus(BOOK_A), {}, legacy=self._legacy(), intro=intro)
        rec = {b["book"]: b for b in payload["books"]}
        assert rec[BOOK_A]["hook"] == ""
        assert any("不存在的书" in n for n in payload["meta"]["notes"])

    def test_records_shape_stable(self):
        """记录字段集合 = 旧契约字段 + {hook, summary}（W2-B8 只增不破）。"""
        payload, _ = exb.build_books(_corpus(BOOK_A), {}, legacy=self._legacy(), intro={})
        keys = set(payload["books"][0])
        assert {"hook", "summary"} <= keys
        assert keys - {"hook", "summary"} == {
            "no", "book", "year", "year_conf", "era", "era_conf", "series", "series_conf",
            "leads", "leads_conf", "chapters", "chars", "kb_status",
            "intertext_out", "intertext_in", "out_refs", "in_refs",
        }


# ================================================================ 3. 真实 TSV 内容纪律（L0 合规）
SCOPE_7 = ["散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
           "七剑下天山", "冰魄寒光剑", "江湖三女侠"]
OUT_OF_SCOPE_TITLES = ["冰川天女传", "云海玉弓缘", "萍踪侠影录", "大唐游侠传",
                       "女帝奇英传", "龙虎斗京华", "武当一剑", "狂侠天骄魔女"]


def _sentences(text: str) -> list:
    return [s for s in re.split(r"[。！？…]+", text) if s.strip()]


class TestRealIntroTsv:
    """真实 kb/校订/作品简介.tsv 的编辑纪律（内容即规范，供人工复核前把关）。"""

    def setup_method(self):
        assert exb.INTRO_TSV.exists(), "kb/校订/作品简介.tsv 不存在（W2-B8 应已建）"
        self.intro = exb.load_intro_tsv()   # 超长/重复/空值在此即报错

    def test_seven_scope_books_all_kept(self):
        assert set(SCOPE_7) <= set(self.intro)

    def test_hooks_within_limit(self):
        for book, row in self.intro.items():
            assert len(row["hook"]) <= 30, (book, len(row["hook"]))

    def test_summaries_three_to_five_sentences(self):
        for book, row in self.intro.items():
            n = len(_sentences(row["summary"]))
            assert 3 <= n <= 5, (book, n)

    def test_no_book_title_marks_no_quotes(self):
        """不含书名号（不引站内外书名）与弯引号（不含原文引文）。"""
        for book, row in self.intro.items():
            for field in ("hook", "summary"):
                assert "《" not in row[field] and "》" not in row[field], (book, field)
                assert "“" not in row[field] and "”" not in row[field], (book, field)

    def test_summaries_free_of_out_of_scope_titles(self):
        """内容纪律：7 部书的 summary 不得出现站外书名（scope 外 27 部抽样 + 全表对照）。"""
        wmeta = json.loads((exb.config.LEGACY_KB / "作品元数据表.json").read_text(encoding="utf-8"))
        all_books = {w["book"] for w in wmeta.get("works") or []}
        others = sorted(all_books - set(SCOPE_7))
        assert "冰川天女传" in others and "云海玉弓缘" in others  # 对照：确属站外
        for book, row in self.intro.items():
            hit = [t for t in others if t in row["summary"]]
            assert not hit, (book, hit)

    def test_scope_books_covered_by_real_loader(self):
        """真实口径整链：load_intro_tsv 默认路径 → 7 部全齐（并入无缺行）。"""
        assert set(self.intro) == set(SCOPE_7)
        for book in SCOPE_7:
            assert self.intro[book]["hook"] and self.intro[book]["summary"]
