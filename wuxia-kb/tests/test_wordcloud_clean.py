# -*- coding: utf-8 -*-
"""W2-B1 · 词云人工清洗闸门 + 7 书语料重算测试（天山演示版总体方案 §4.2 B1，2026-11-10）。

被测（scripts/build_wordcloud.py W2-B1 改造）：
  load_clean_tsv   读 kb/校订/词云清洗.tsv → verdicts + problems（表级校验）
  cleaned_gate     全部校定 + Top200 词目全覆盖 → True；存在 draft/未覆盖/非法 merge → False
  apply_cleaning   drop 剔除；merge 截断/OCR 变体词频并入规范名目（目标可不在池，按全量计数补入）
  count_ngrams     n-gram 计数（可注入临时小语料）
  top_pool         停用过滤 → Top200 候选池
  build_payload    meta.cleaned / meta.note / items 组织（写盘仍在 main，测试不落 site/data）
  texts / wordcloud_meta / scan_presence / finalize_items（W0-T3b 既有口径不回归）

口径固化（测试即规范）：
  - cleaned 闸门：TSV 全部 status=校定 且 verdict ∈ {keep, merge, drop} 且 merge_to=keep 行
    且 Top200 词目全部入表 → meta.cleaned=true；任一 draft 行 → false（且不套用清洗，
    items 保持 raw Top200，与 W0-T3b 行为一致）。
  - merge 语义：源词词频并入 merge_to 目标（叠加），源词从词目表删除；目标不在候选池时
    按全量计数器补入（停用字阻断全名的救援通道，如 霍天都/于承珠）。
  - drop：叙事碎片/泛称/非人名 直接剔除。
  - scope 语料重算（W2-B1）：--scope 下词频 n 为 scope 书语料口径——词在 scope 外书的
    出现不再计入（W0-T3b 的「n 仍为全量口径」就此废止）。
  - 全量口径（scope=None）：n-gram 计数扫全部书（方案 R6：不带 --scope 行为不变）。
  - 口径注（宇宙页 §4.6）：meta.note 写明「别名与绰号不归并」（玉罗刹与练霓裳分列）；
    merge 只并 OCR/截断变体，与该表述自洽。
"""
import sys
from collections import Counter
from pathlib import Path

import pytest

# 被测模块（父仓 scripts/）；export_site_common（wuxia-kb/scripts/）——两处显式入 path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "wuxia-kb" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import export_site_common as esc  # noqa: E402
import build_wordcloud as bw  # noqa: E402


# ---------------------------------------------------------------- fixtures
def write_tsv(path: Path, rows: list) -> None:
    """写清洗表（正式 7 列 schema：word/n/books/verdict/merge_to/status/note）。"""
    lines = ["word\tn\tbooks\tverdict\tmerge_to\tstatus\tnote"]
    for r in rows:
        lines.append("\t".join([
            r.get("w", ""), str(r.get("n", "")), str(r.get("books", "")),
            r.get("verdict", ""), r.get("merge_to", ""),
            r.get("status", "校定"), r.get("note", ""),
        ]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def corpus(tmp_path) -> Path:
    """临时小语料：scope 书 白发魔女传 + scope 外书 萍踪侠影录。"""
    d = tmp_path / "章回版"
    (d / "白发魔女传").mkdir(parents=True)
    (d / "萍踪侠影录").mkdir()
    (d / "白发魔女传" / "01.txt").write_text("凌未风练剑玉罗刹冷笑", encoding="utf-8")
    (d / "萍踪侠影录" / "01.txt").write_text("凌未风大笑张丹枫云蕾", encoding="utf-8")
    return d


SCOPE_BMF = {"profile": "tianshan-demo", "books": ["白发魔女传"]}


# ================================================================ 1. cleaned 闸门
class TestCleanedGate:
    def test_all_calibrated_true(self, tmp_path):
        """全部行 status=校定 且 verdict ∈ {keep,merge,drop} → 闸门通过。"""
        tsv = tmp_path / "词云清洗.tsv"
        write_tsv(tsv, [
            {"w": "凌未风", "verdict": "keep"},
            {"w": "凌未", "verdict": "merge", "merge_to": "凌未风"},
            {"w": "心里", "verdict": "drop"},
        ])
        state = bw.load_clean_tsv(tsv)
        ok, reasons = bw.cleaned_gate(state, {"凌未风", "凌未", "心里"})
        assert ok, reasons
        assert reasons == []

    def test_draft_row_blocks_gate(self, tmp_path):
        """存在 draft 行 → cleaned=false（方案要求的第一反例）。"""
        tsv = tmp_path / "词云清洗.tsv"
        write_tsv(tsv, [{"w": "凌未风", "verdict": "keep", "status": "draft"}])
        state = bw.load_clean_tsv(tsv)
        ok, reasons = bw.cleaned_gate(state, {"凌未风"})
        assert not ok
        assert any("draft" in r for r in reasons)

    def test_illegal_verdict_blocks_gate(self, tmp_path):
        """verdict 非法（空/未知值）→ 闸门不通过。"""
        tsv = tmp_path / "词云清洗.tsv"
        write_tsv(tsv, [{"w": "凌未风", "verdict": ""}, {"w": "心里", "verdict": "保留"}])
        ok, reasons = bw.cleaned_gate(bw.load_clean_tsv(tsv), {"凌未风", "心里"})
        assert not ok and len(reasons) == 2

    def test_merge_target_must_be_keep_row(self, tmp_path):
        """merge_to 必须指向 keep 的规范名目（表级校验；task B1 约束）。"""
        tsv = tmp_path / "词云清洗.tsv"
        write_tsv(tsv, [{"w": "凌未", "verdict": "merge", "merge_to": "不存在名"}])
        ok, reasons = bw.cleaned_gate(bw.load_clean_tsv(tsv), {"凌未"})
        assert not ok and any("merge_to" in r for r in reasons)

    def test_uncovered_pool_word_blocks_gate(self, tmp_path):
        """Top200 词目未入表 → 闸门不通过（新进词目必须补入并裁定）。"""
        tsv = tmp_path / "词云清洗.tsv"
        write_tsv(tsv, [{"w": "凌未风", "verdict": "keep"}])
        ok, reasons = bw.cleaned_gate(bw.load_clean_tsv(tsv), {"凌未风", "凌未"})
        assert not ok and any("凌未" in r for r in reasons)

    def test_missing_tsv_blocks_gate(self, tmp_path):
        tsv = tmp_path / "不存在.tsv"
        ok, _ = bw.cleaned_gate(bw.load_clean_tsv(tsv), {"凌未风"})
        assert not ok


# ================================================================ 2. 清洗语义（drop / merge）
class TestApplyCleaning:
    def test_drop_removes_entries(self):
        top = [("心里", 7895), ("凌未风", 100)]
        verdicts = {"心里": ("drop", ""), "凌未风": ("keep", "")}
        counts, stats = bw.apply_cleaning(top, verdicts, Counter(top))
        assert "心里" not in counts
        assert counts["凌未风"] == 100
        assert stats["dropped"] == 1

    def test_merge_folds_frequency_and_removes_source(self):
        """merge：词频并入目标（叠加）、源词删除——OCR 变体口径（task 测试项 2）。"""
        top = [("凌未风", 100), ("凌末风", 30)]
        verdicts = {"凌未风": ("keep", ""), "凌末风": ("merge", "凌未风")}
        counts, stats = bw.apply_cleaning(top, verdicts, Counter(top))
        assert counts == {"凌未风": 130}
        assert "凌末风" not in counts
        assert stats["merged_sources"] == 1

    def test_merge_target_outside_pool_rescued_from_counter(self):
        """目标不在候选池（停用字阻断全名）：按全量计数器补入目标再叠加。"""
        top = [("承珠", 3553)]
        verdicts = {"承珠": ("merge", "于承珠"), "于承珠": ("keep", "")}
        counter = Counter({"承珠": 3553, "于承珠": 3445})
        counts, _ = bw.apply_cleaning(top, verdicts, counter)
        assert counts == {"于承珠": 3445 + 3553}

    def test_merge_chain_forbidden_target_must_be_keep(self, tmp_path):
        """merge_to 指向另一 merge 行（链式）同样拦截：目标必须是 keep 行。"""
        tsv = tmp_path / "词云清洗.tsv"
        write_tsv(tsv, [
            {"w": "甲乙", "verdict": "merge", "merge_to": "丙丁"},
            {"w": "丙丁", "verdict": "merge", "merge_to": "戊己"},
        ])
        ok, reasons = bw.cleaned_gate(bw.load_clean_tsv(tsv), {"甲乙", "丙丁"})
        assert not ok and any("keep" in r for r in reasons)


# ================================================================ 3. scope 语料重算（W2-B1）
class TestScopeRecalc:
    def test_scope_counts_only_scope_books(self, corpus, monkeypatch):
        """7 书口径：词频 n 只统计 scope 书语料（词在 scope 外书的出现不计）。"""
        monkeypatch.setattr(bw, "CORPUS", corpus)
        c_scope = bw.count_ngrams(bw.texts(SCOPE_BMF))
        assert c_scope["凌未风"] == 1          # 仅 白发魔女传 的 1 次
        assert "张丹枫" not in c_scope         # scope 外书的词目不进计数

    def test_full_caliber_counts_all_books(self, corpus, monkeypatch):
        """全量口径（scope=None）：扫全部书（方案 R6：不带 --scope 行为不变）。"""
        monkeypatch.setattr(bw, "CORPUS", corpus)
        c_all = bw.count_ngrams(bw.texts(None))
        assert c_all["凌未风"] == 2            # 两书各 1 次
        assert c_all["张丹枫"] == 1

    def test_build_payload_scope_caliber_meta(self, corpus, monkeypatch, tmp_path):
        monkeypatch.setattr(bw, "CORPUS", corpus)
        pool = bw.top_pool(bw.count_ngrams(bw.texts(SCOPE_BMF)))
        tsv = tmp_path / "clean.tsv"
        write_tsv(tsv, [{"w": w, "n": n, "verdict": "keep"} for w, n in pool])
        payload = bw.build_payload(SCOPE_BMF, corpus_dir=corpus, tsv_path=tsv)
        assert payload["meta"]["scope"] == "tianshan-demo"
        assert "W2-B1" in payload["meta"]["note"]
        ws = {it["w"]: it["n"] for it in payload["items"]}
        assert ws["凌未风"] == 1               # scope 语料口径（W0-T3b 的全量 n 口径废止）


# ================================================================ 4. build_payload 端到端（闸门 → 清洗 → meta）
class TestBuildPayloadCleaned:
    def _tsv_all_keep(self, tmp_path, pool, extra=()):
        tsv = tmp_path / "clean.tsv"
        rows = [{"w": w, "n": n, "verdict": "keep"} for w, n in pool]
        write_tsv(tsv, rows + list(extra))
        return tsv

    def test_cleaned_true_and_merge_applied(self, corpus, monkeypatch, tmp_path):
        """全表校定 → meta.cleaned=true；merge 生效（凌未→凌未风），drop 生效。"""
        monkeypatch.setattr(bw, "CORPUS", corpus)
        pool = bw.top_pool(bw.count_ngrams(bw.texts(SCOPE_BMF)))
        assert {"凌未风", "凌未"} <= {w for w, _ in pool}   # fixture 前提：两词都在池
        tsv = tmp_path / "clean.tsv"
        rows = [{"w": w, "n": n,
                 "verdict": "merge" if w == "凌未" else "keep",
                 "merge_to": "凌未风" if w == "凌未" else ""}
                for w, n in pool]
        write_tsv(tsv, rows + [{"w": "心里", "verdict": "drop", "note": "叙事碎片"}])
        payload = bw.build_payload(SCOPE_BMF, corpus_dir=corpus, tsv_path=tsv)
        meta = payload["meta"]
        assert meta["cleaned"] is True
        assert "别名" in meta["note"]                       # 口径注：别名与绰号不归并
        ws = {it["w"]: it["n"] for it in payload["items"]}
        assert "心里" not in ws                              # drop 剔除（行在池外亦生效）
        assert ws["凌未风"] == 2                             # 自身 1 + 凌未(1) 并入
        assert "凌未" not in ws                              # 源词删除

    def test_draft_row_keeps_raw_output(self, corpus, monkeypatch, tmp_path):
        """存在 draft 行 → cleaned=false，items 保持 raw Top200（不套用清洗）。"""
        monkeypatch.setattr(bw, "CORPUS", corpus)
        pool = bw.top_pool(bw.count_ngrams(bw.texts(SCOPE_BMF)))
        tsv = tmp_path / "clean.tsv"
        rows = [{"w": w, "n": n, "verdict": "keep"} for w, n in pool]
        rows[0]["status"] = "draft"
        write_tsv(tsv, rows)
        payload = bw.build_payload(SCOPE_BMF, corpus_dir=corpus, tsv_path=tsv)
        assert payload["meta"]["cleaned"] is False
        ws = {it["w"]: it["n"] for it in payload["items"]}
        assert ws["凌未风"] == 1                             # 未并入（清洗未启用）
        assert ws["凌未"] == 1                               # 源词仍在（未清洗口径）

    def test_full_caliber_meta_has_no_scope_key(self, corpus, monkeypatch, tmp_path):
        """全量口径 R6：meta 无 scope 键；计数含 scope 外书（W0-T3b 行为不回归）。"""
        monkeypatch.setattr(bw, "CORPUS", corpus)
        pool = bw.top_pool(bw.count_ngrams(bw.texts(None)))
        tsv = self._tsv_all_keep(tmp_path, pool)
        payload = bw.build_payload(None, corpus_dir=corpus, tsv_path=tsv)
        assert "scope" not in payload["meta"]
        ws = {it["w"]: it["n"] for it in payload["items"]}
        assert ws["凌未风"] == 2                             # 全量=两书
        assert ws["张丹枫"] == 1

    def test_rescue_merge_target_outside_pool(self, corpus, monkeypatch, tmp_path):
        """救援通道（端到端）：池外 keep 目标按全量计数器补入输出（unit 语义见
        TestApplyCleaning.test_merge_target_outside_pool_rescued_from_counter）。"""
        monkeypatch.setattr(bw, "CORPUS", corpus)
        pool = bw.top_pool(bw.count_ngrams(bw.texts(SCOPE_BMF)))
        tsv = tmp_path / "clean.tsv"
        rows = [{"w": w, "n": n, "verdict": "keep"} for w, n in pool if w != "凌未"]
        # 源词 凌未 在池（merge 行覆盖）；目标「凌虚上人」fixture 语料中不存在（计数 0），
        # 计入后因 scope 出现过滤（books=0）被 finalize 裁掉——此处断言机制不抛错、源词删除。
        rows.append({"w": "凌未", "verdict": "merge", "merge_to": "凌虚上人"})
        rows.append({"w": "凌虚上人", "verdict": "keep"})  # merge_to 须为表内 keep 行
        write_tsv(tsv, rows)
        payload = bw.build_payload(SCOPE_BMF, corpus_dir=corpus, tsv_path=tsv)
        assert payload["meta"]["cleaned"] is True
        ws = {it["w"]: it["n"] for it in payload["items"]}
        assert "凌未" not in ws


# ================================================================ 5. W0-T3b 既有纯函数不回归
class TestW0T3bCompat:
    def test_scan_presence(self):
        pairs = [("白发魔女传", "张三练剑"), ("萍踪侠影录", "李四练刀")]
        presence = bw.scan_presence(pairs, {"张三", "李四", "王五"})
        assert presence["张三"] == {"白发魔女传"}
        assert "王五" not in presence

    def test_finalize_items_scope_filter(self):
        top = [("张三", 100), ("李四", 50)]
        presence = {"张三": {"白发魔女传", "萍踪侠影录"}, "李四": {"萍踪侠影录"}}
        items = bw.finalize_items(top, presence, SCOPE_BMF)
        assert items == [{"w": "张三", "n": 100, "books": 1}]
        assert bw.finalize_items(top, presence, None) == [
            {"w": "张三", "n": 100, "books": 2}, {"w": "李四", "n": 50, "books": 1}]

    def test_wordcloud_meta_defaults(self):
        meta = bw.wordcloud_meta(SCOPE_BMF)
        assert meta["cleaned"] is False            # 默认未清洗（旧测试兼容）
        assert "W2-B1" in meta["note"]
        assert "scope" not in bw.wordcloud_meta(None)

    def test_real_scope_books(self):
        scope = esc.load_scope("tianshan-demo")
        assert set(scope["books"]) == {"散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
                                       "七剑下天山", "冰魄寒光剑", "江湖三女侠"}
