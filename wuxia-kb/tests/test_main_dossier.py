# -*- coding: utf-8 -*-
"""W0-T2 · 人物别名归并前置 + 主档圈定 + entity-index page 标志测试
（天山演示版总体方案 §二 / §1.2，2026-11-08）。

只测纯函数与合成数据聚合：不读真实 site/data / registry / kb；归并 TSV 用临时目录构造。
被测对象（W0-T2 新增/改造）：
  scripts/export_site_characters.py
    load_alias_merges / resolve_alias                 —— B7 别名归并 TSV 机制（缺文件 no-op、链式禁止）
    aggregate_entities(merges=…) / trace_entity(merges=…)  —— 归并在频次聚合之前生效
    scope_book_total / is_content_bearing / is_major_dossier / decide_major / major_rule_meta
    build_entity_index_payload（page 标志 + meta.major_rule + scope 频次重算）
  scripts/export_site_dossiers.py
    build_dossiers(scope=…) 主档圈定过滤 / build_payload(scope=…) meta.major_rule

口径固化（测试即规范）：
  - 主档规则：total≥30 ∪ 有实质内容（key_events 非空 ∪ lineage.masters/disciples 非空 ∪
    combat.kills/slain_by 非空 ∪ arts 非空）；阈值经参数可调、进 meta 不硬编码（方案 §2.2）。
  - 归并链式：**显式禁止**（merge_to 不得再为任一行的 form），不做 TSV 行序解析。
  - scope：频次按 scope 内 books 计数重算（不是全库 total）再圈定；scope 内 0 次者先被过滤
    （方案 §2.2 顺序：7 书过滤 → 频次重算 → 主档圈定）。
  - 向后兼容（R6）：无 scope 无 TSV 时 dossiers 全量保留；规则随 meta.major_rule.scope 走。
  - ☆/◆ 恒 page=true（武功/门派有独立页）；@ 主档 true、存目 false。
"""
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（被测模块依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_characters as exc  # noqa: E402
import export_site_dossiers as exd    # noqa: E402


# ---------------------------------------------------------------- 合成数据工厂
BOOK_A, BOOK_B = "测试书甲", "测试书乙"
SCOPE_DEMO = {"profile": "demo", "books": [BOOK_A]}
TSV_HEADER = "form\tmerge_to\tnote"


def _ent(etype, canon, total, variants=None):
    """concordance 单条实体（最小形状：type/canonical/total/chapter_counts/variants）。"""
    return {
        "type": etype,
        "canonical": canon,
        "total": total,
        "chapter_counts": [{"chapter": 1, "count": total}],
        "variants": variants if variants is not None else [{"display": canon, "count": total}],
    }


def _bp(book, entities):
    """concordance 书载荷（最小形状）。"""
    return {"book": book, "path": None, "data": {"entities": entities}}


def _agg(payloads, merges=None):
    agg, _stats = exc.aggregate_entities(payloads, {}, merges=merges)
    return agg


def _derived(key_events=(), masters=(), disciples=(), kills=(), slain_by=(), arts=()):
    """派生字段骨架（与旧站 dossiers 派生字段同形，可作 content_index/fallback 值）。"""
    return {
        "key_events": list(key_events),
        "lineage": {"masters": list(masters), "disciples": list(disciples)},
        "combat": {"kills": list(kills), "slain_by": list(slain_by)},
        "arts": list(arts),
    }


EMPTY_DERIVED = _derived()


def _write_tsv(tmp_path, *rows, header=TSV_HEADER, name="别名归并.tsv"):
    p = tmp_path / name
    lines = [header] + list(rows)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ================================================================ 1. 别名归并前置
class TestAliasMergeLoad:
    """kb/校订/别名归并.tsv 加载：缺文件 no-op；表头/行校验；链式显式禁止。"""

    def test_missing_file_noop(self, tmp_path):
        merges, meta = exc.load_alias_merges(tmp_path / "别名归并.tsv")
        assert merges == {}
        assert meta["exists"] is False

    def test_parse_rows_and_note(self, tmp_path):
        p = _write_tsv(tmp_path, "一瓢大师\t一瓢\t同一人（凌一瓢）", "一瓢道长\t一瓢\t", "")
        merges, meta = exc.load_alias_merges(p)
        assert merges == {"一瓢大师": "一瓢", "一瓢道长": "一瓢"}
        assert meta["exists"] is True and meta["rows"] == 2

    def test_bad_header_raises(self, tmp_path):
        p = _write_tsv(tmp_path, "甲\t乙", header="alias\ttarget")
        with pytest.raises(ValueError, match="表头"):
            exc.load_alias_merges(p)

    def test_bad_row_raises(self, tmp_path):
        p = _write_tsv(tmp_path, "只有一列")
        with pytest.raises(ValueError, match="行"):
            exc.load_alias_merges(p)

    def test_chain_forbidden(self, tmp_path):
        """链式归并显式禁止（选型固化）：merge_to 不得再为任一行的 form。"""
        p = _write_tsv(tmp_path, "甲\t乙\t", "乙\t丙\t")
        with pytest.raises(ValueError, match="链式"):
            exc.load_alias_merges(p)

    def test_self_merge_forbidden(self, tmp_path):
        p = _write_tsv(tmp_path, "甲\t甲\t")
        with pytest.raises(ValueError, match="链式"):
            exc.load_alias_merges(p)


class TestAliasMergeApply:
    """归并映射在频次聚合之前生效：两簇频次合并为一人；无 TSV = 现状。"""

    PAYLOADS = [
        _bp(BOOK_A, [_ent("@", "一瓢", 10), _ent("@", "一瓢大师", 12)]),
        _bp(BOOK_B, [_ent("@", "一瓢", 8), _ent("@", "一瓢大师", 5)]),
    ]

    def test_merge_before_aggregation(self, tmp_path):
        p = _write_tsv(tmp_path, "一瓢大师\t一瓢\t同一人")
        merges, _ = exc.load_alias_merges(p)
        agg = _agg(self.PAYLOADS, merges)
        assert ("@", "一瓢大师") not in agg
        rec = agg[("@", "一瓢")]
        assert rec["total"] == 35                      # 10+12+8+5：频次合并为一人
        assert rec["books"][BOOK_A]["count"] == 22
        assert rec["books"][BOOK_B]["count"] == 13
        aliases = rec["books"][BOOK_A]["aliases"]
        assert aliases["一瓢"] == 10 and aliases["一瓢大师"] == 12  # 表层形式保留为别名

    def test_no_tsv_is_status_quo(self):
        """TSV 不存在（merges=None / {}）时行为与现状一致。"""
        agg_none = _agg(self.PAYLOADS, None)
        agg_empty = _agg(self.PAYLOADS, {})
        assert agg_none[("@", "一瓢")]["total"] == 18        # 10+8
        assert agg_none[("@", "一瓢大师")]["total"] == 17    # 12+5
        assert set(agg_none) == set(agg_empty)
        assert {k: v["total"] for k, v in agg_none.items()} == \
               {k: v["total"] for k, v in agg_empty.items()}

    def test_resolve_alias_single_step(self):
        assert exc.resolve_alias("一瓢大师", {"一瓢大师": "一瓢"}) == "一瓢"
        assert exc.resolve_alias("无此人", {"一瓢大师": "一瓢"}) == "无此人"
        assert exc.resolve_alias("一瓢大师", {}) == "一瓢大师"

    def test_merge_uniform_across_types(self, tmp_path):
        """归并按 form 统一生效（与类型无关）；首批数据仅人物。"""
        p = _write_tsv(tmp_path, "一瓢大师\t一瓢\t")
        merges, _ = exc.load_alias_merges(p)
        payloads = [_bp(BOOK_A, [_ent("☆", "一瓢", 3), _ent("☆", "一瓢大师", 7)])]
        agg = _agg(payloads, merges)
        assert agg[("☆", "一瓢")]["total"] == 10
        assert ("☆", "一瓢大师") not in agg

    def test_merge_after_registry_norm(self, tmp_path):
        """方案 §2.2 顺序：registry 归一在前、TSV 归并在后。"""
        p = _write_tsv(tmp_path, "一瓢道人\t一瓢\t")
        merges, _ = exc.load_alias_merges(p)
        reg = {"r1": {"id": "r1", "type": "@", "canonical": "一瓢道人"}}
        entry = {"type": "@", "canonical": "凌一瓢", "total": 7,
                 "chapter_counts": [{"chapter": 1, "count": 7}],
                 "variants": [{"display": "凌一瓢", "count": 7}],
                 "registration": {"status": "alias_mapped", "id": "r1"}}
        payloads = [_bp(BOOK_A, [entry, _ent("@", "一瓢", 3)])]
        agg, _ = exc.aggregate_entities(payloads, reg, merges=merges)
        assert agg[("@", "一瓢")]["total"] == 10
        assert ("@", "一瓢道人") not in agg and ("@", "凌一瓢") not in agg


# ================================================================ 2. 主档圈定规则
class TestMajorRule:
    """total≥30 ∪ 有实质内容；阈值参数化（进 meta 不硬编码）。"""

    def test_29_no_content_false(self):
        assert exc.is_major_dossier(29, EMPTY_DERIVED) is False

    def test_30_no_content_true(self):
        assert exc.is_major_dossier(30, EMPTY_DERIVED) is True

    def test_5_with_key_events_true(self):
        assert exc.is_major_dossier(5, _derived(key_events=[{"chapter": 1}])) is True

    @pytest.mark.parametrize("derived", [
        _derived(masters=["师父"]),
        _derived(disciples=["徒弟"]),
        _derived(kills=["敌"]),
        _derived(slain_by=["仇"]),
        _derived(arts=["天山剑法"]),
    ], ids=["masters", "disciples", "kills", "slain_by", "arts"])
    def test_content_groups(self, derived):
        assert exc.is_content_bearing(derived) is True
        assert exc.is_major_dossier(1, derived) is True

    def test_min_total_parametrizable(self):
        assert exc.is_major_dossier(29, EMPTY_DERIVED, min_total=29) is True
        assert exc.is_major_dossier(30, EMPTY_DERIVED, min_total=31) is False

    def test_none_derived_threshold_only(self):
        assert exc.is_major_dossier(5, None) is False
        assert exc.is_major_dossier(50, None) is True

    def test_sect_affinity_ranks_not_counted(self):
        """规则字面仅 4 组：key_events / lineage.masters|disciples / combat.kills|slain_by / arts；
        sect_affinity、ranks 不算实质内容。"""
        derived = {"key_events": [], "lineage": {"masters": [], "disciples": []},
                   "combat": {"kills": [], "slain_by": []}, "arts": [],
                   "sect_affinity": [{"sect": "天山派"}], "ranks": [{"rank": "掌门"}]}
        assert exc.is_content_bearing(derived) is False
        assert exc.is_major_dossier(5, derived) is False


# ================================================================ 3. scope 交互
class TestScopeInteraction:
    """scope 传入时频次按 scope 内 books 重算再圈定；scope=None 用全库 total。"""

    REC = {"type": "@", "canonical": "某甲", "total": 35,
           "books": {BOOK_A: {"count": 20}, BOOK_B: {"count": 15}}}

    def test_scope_book_total_recount(self):
        assert exc.scope_book_total(self.REC, SCOPE_DEMO) == 20

    def test_scope_book_total_none_full(self):
        assert exc.scope_book_total(self.REC, None) == 35

    def test_decide_major_scope_vs_full(self):
        # scope 内 20 次（<30 无内容）→ 存目；全库 35 次 → 主档
        assert exc.decide_major(self.REC, EMPTY_DERIVED, scope=SCOPE_DEMO) is False
        assert exc.decide_major(self.REC, EMPTY_DERIVED, scope=None) is True

    def test_decide_major_scope_content_bearing(self):
        rec = {"type": "@", "canonical": "某乙", "total": 5, "books": {BOOK_A: {"count": 5}}}
        assert exc.decide_major(rec, _derived(key_events=[{"chapter": 1}]),
                                scope=SCOPE_DEMO) is True

    def test_scope_zero_excluded_even_with_content(self):
        """方案 §2.2 顺序：先 7 书过滤再圈定——scope 内 0 次不参与（有实质内容也不救）。"""
        rec = {"type": "@", "canonical": "某丙", "total": 100, "books": {BOOK_B: {"count": 100}}}
        derived = _derived(key_events=[{"chapter": 1}])
        assert exc.decide_major(rec, derived, scope=SCOPE_DEMO) is False
        assert exc.decide_major(rec, derived, scope=None) is True

    def test_decide_major_min_total_passthrough(self):
        assert exc.decide_major(self.REC, EMPTY_DERIVED, scope=SCOPE_DEMO, min_total=20) is True

    def test_major_rule_meta(self):
        assert exc.major_rule_meta(None) == {"min_total": 30, "content_bearing": True, "scope": None}
        assert exc.major_rule_meta(SCOPE_DEMO) == {"min_total": 30, "content_bearing": True,
                                                   "scope": "demo"}


# ================================================================ 4/5. entity-index page 标志 + meta.major_rule
class TestEntityIndexPage:
    CONTENT = {"有事件者": _derived(key_events=[{"chapter": 1}])}

    def _items(self):
        payloads = [_bp(BOOK_A, [
            _ent("@", "高手", 100),
            _ent("@", "龙套", 1),
            _ent("@", "有事件者", 5),
            _ent("☆", "天山剑法", 9),
            _ent("◆", "天山派", 40),
        ])]
        return exc.build_characters(_agg(payloads), [BOOK_A])

    def test_page_flags_by_type(self):
        """@ 主档→true；@ 非主档→false；☆/◆→true（武功/门派有独立页）。"""
        payload = exc.build_entity_index_payload(self._items(), [BOOK_A], {},
                                                 content_index=self.CONTENT)
        rows = {(r["t"], r["c"]): r for r in payload["entities"]}
        assert rows[("@", "高手")]["page"] is True
        assert rows[("@", "龙套")]["page"] is False
        assert rows[("@", "有事件者")]["page"] is True      # 5 次但有 key_events → 主档
        assert rows[("☆", "天山剑法")]["page"] is True
        assert rows[("◆", "天山派")]["page"] is True

    def test_row_keeps_legacy_fields(self):
        payload = exc.build_entity_index_payload(self._items(), [BOOK_A], {},
                                                 content_index=self.CONTENT)
        row = payload["entities"][0]
        assert {"t", "c", "display", "n", "b", "x"} <= set(row)   # 旧契约字段不缺
        assert "page" in row                                       # 新增 page（只增字段）

    def test_meta_major_rule_full(self):
        payload = exc.build_entity_index_payload(self._items(), [BOOK_A], {},
                                                 content_index=self.CONTENT)
        assert payload["meta"]["major_rule"] == \
               {"min_total": 30, "content_bearing": True, "scope": None}

    def test_meta_major_rule_scope(self):
        payload = exc.build_entity_index_payload(self._items(), [BOOK_A], {},
                                                 scope=SCOPE_DEMO, content_index=self.CONTENT)
        assert payload["meta"]["major_rule"] == \
               {"min_total": 30, "content_bearing": True, "scope": "demo"}
        assert payload["meta"]["scope"] == "demo"

    def test_scope_page_uses_scope_recount(self):
        payloads = [_bp(BOOK_A, [_ent("@", "甲", 35), _ent("@", "乙", 10)]),
                    _bp(BOOK_B, [_ent("@", "甲", 100), _ent("@", "乙", 100)])]
        items = exc.build_characters(_agg(payloads), [BOOK_A, BOOK_B])
        payload = exc.build_entity_index_payload(items, [BOOK_A, BOOK_B], {},
                                                 scope=SCOPE_DEMO, content_index={})
        rows = {r["c"]: r for r in payload["entities"] if r["t"] == "@"}
        # 全库 total 甲135/乙110 都≥30；scope 内重算 甲35→主档、乙10→存目（不是全库 total）
        assert rows["甲"]["page"] is True and rows["甲"]["n"] == 35
        assert rows["乙"]["page"] is False and rows["乙"]["n"] == 10
        assert rows["乙"]["b"] == {BOOK_A: 10}

    def test_scope_excludes_zero_rows(self):
        payloads = [_bp(BOOK_A, [_ent("@", "甲", 35)]),
                    _bp(BOOK_B, [_ent("@", "仅乙书", 50)])]
        items = exc.build_characters(_agg(payloads), [BOOK_A, BOOK_B])
        payload = exc.build_entity_index_payload(items, [BOOK_A, BOOK_B], {},
                                                 scope=SCOPE_DEMO, content_index={})
        assert "仅乙书" not in {r["c"] for r in payload["entities"]}
        # 全量口径仍保留（轻索引=全库出现实体）
        payload_full = exc.build_entity_index_payload(items, [BOOK_A, BOOK_B], {}, content_index={})
        assert "仅乙书" in {r["c"] for r in payload_full["entities"]}


# ================================================================ 6. dossiers 输出
class TestDossiersOutput:
    BOOKS = [BOOK_A]
    FALLBACK = {"配角": _derived(key_events=[{"chapter": 3}])}

    def _agg(self):
        payloads = [_bp(BOOK_A, [
            _ent("@", "高手", 35),      # ≥30 无内容 → 主档
            _ent("@", "配角", 5),       # <30 有 key_events → 主档
            _ent("@", "路人", 2),       # <30 无内容 → 存目
            _ent("☆", "天山剑法", 9),   # 非人物，不进 dossiers
        ])]
        return _agg(payloads)

    def test_full_mode_keeps_all(self):
        """向后兼容（R6）：无 scope 时存目不裁剪，dossiers 全量保留。"""
        dossiers, stats = exd.build_dossiers(self._agg(), self.BOOKS, self.FALLBACK)
        assert {d["canonical"] for d in dossiers} == {"高手", "配角", "路人"}
        assert stats.get("archived", 0) == 0

    def test_scope_only_major_in_dossiers(self):
        dossiers, stats = exd.build_dossiers(self._agg(), self.BOOKS, self.FALLBACK,
                                             scope=SCOPE_DEMO)
        assert {d["canonical"] for d in dossiers} == {"高手", "配角"}
        assert stats["archived"] == 1          # 路人：2 次无内容 → 存目

    def test_archived_in_index_not_in_dossiers(self):
        """存目不出现在 dossiers 但出现在 entity-index（page=false）。"""
        agg = self._agg()
        items = exc.build_characters(agg, self.BOOKS)
        index = exc.build_entity_index_payload(items, self.BOOKS, {},
                                               content_index=self.FALLBACK)
        dossiers, _ = exd.build_dossiers(agg, self.BOOKS, self.FALLBACK, scope=SCOPE_DEMO)
        rows = {(r["t"], r["c"]): r for r in index["entities"]}
        assert rows[("@", "路人")]["page"] is False
        assert "路人" not in {d["canonical"] for d in dossiers}
        assert rows[("@", "配角")]["page"] is True

    def test_dossier_record_shape_unchanged(self):
        dossiers, _ = exd.build_dossiers(self._agg(), self.BOOKS, self.FALLBACK, scope=SCOPE_DEMO)
        expected = {"id", "canonical", "display", "display_name", "cross_book", "books",
                    "aliases", "appearance_total", "chapter_curves", "sect_affinity",
                    "lineage", "ranks", "combat", "arts", "key_events", "summary",
                    "summary_status"}
        assert set(dossiers[0]) == expected

    def test_dossiers_meta_major_rule(self):
        dossiers, stats = exd.build_dossiers(self._agg(), self.BOOKS, self.FALLBACK,
                                             scope=SCOPE_DEMO)
        payload = exd.build_payload(dossiers, self.BOOKS, stats, self.FALLBACK, "（测试）", {},
                                    scope=SCOPE_DEMO)
        assert payload["meta"]["major_rule"] == \
               {"min_total": 30, "content_bearing": True, "scope": "demo"}
        assert payload["meta"]["scope"] == "demo"
        assert payload["meta"]["totals"]["archived"] == 1
        payload_full = exd.build_payload(dossiers, self.BOOKS, stats, self.FALLBACK,
                                         "（测试）", {})
        assert payload_full["meta"]["major_rule"]["scope"] is None
        assert "scope" not in payload_full["meta"]
        assert "archived" not in payload_full["meta"]["totals"]
