# -*- coding: utf-8 -*-
"""W2-A1 · entity-index 别名并入测试（天山演示版总体方案 §4.1 A1 / §1.2，2026-11-10）。

被测对象：scripts/export_site_characters.py
  - alias_rows_of（W2-A1 新增）：characters 聚合层 variants 别名 → [{alias, count}...]
  - build_entity_index_payload：每行新增 aliases 字段（只增字段）+ meta 说明新字段

口径固化（测试即规范，合成 fixture，不读真实 site/data / registry / kb）：
  - 来源=聚合层直接产：与 EX-3 dossiers.aliases 同源（concordance variants）、同排序
    （跨书 Counter 合并后 -count, alias 字典序），保证两表别名口径一致；
  - **排除 canonical 本名**：canonical/display 已是独立字段（搜索另路匹配；
    EX-4 build_search_index 同口径过滤 a != canonical），aliases 只收"其他叫法"；
  - count 保留 variants 频次（跨书求和，不丢不重）；
  - 无别名者给 **[]**（字段在场、空数组——不是省略键，前端可稳定消费）；
  - @/☆/◆ 三类均带（人物/武功/门派总览搜索同样消费，方案 §5.3 EntitySearch 复用）；
  - meta.note / field_gaps 说明新字段（数据契约：新增字段必须声明）。

验收锚点（人物页设计第一条）：搜「白发魔女」「玉罗刹」「晦明禅师」必须命中
练霓裳/练霓裳/岳鸣珂——对应 fixture 中三别名必须进入 entity-index aliases。
"""
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（被测模块依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_characters as exc  # noqa: E402


# ---------------------------------------------------------------- 合成数据工厂
BOOK_A, BOOK_B = "测试书甲", "测试书乙"


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


def _index_rows(payloads, books=None, **kw):
    """聚合 → characters items → entity-index rows（测试便捷通道）。"""
    agg, _stats = exc.aggregate_entities(payloads, {})
    items = exc.build_characters(agg, books or [BOOK_A, BOOK_B])
    payload = exc.build_entity_index_payload(items, books or [BOOK_A, BOOK_B],
                                             content_index={}, **kw)
    return payload, items


# ================================================================ 1. 别名并入正确（合成 fixture）
class TestAliasRowsMerged:
    """跨书 variants 合并为一人别名表；canonical 本名不混入。"""

    def test_alias_merged_across_books(self):
        """练霓裳形 fixture：玉罗刹 100+30、白发魔女 10 跨书合并；本名变体被排除。"""
        payloads = [
            _bp(BOOK_A, [_ent("@", "练霓裳", 140, variants=[
                {"display": "玉罗刹", "count": 100},
                {"display": "练霓裳", "count": 40},
            ])]),
            _bp(BOOK_B, [_ent("@", "练霓裳", 90, variants=[
                {"display": "玉罗刹", "count": 30},
                {"display": "白发魔女", "count": 10},
                {"display": "练霓裳", "count": 50},
            ])]),
        ]
        payload, _ = _index_rows(payloads)
        row = next(r for r in payload["entities"] if r["c"] == "练霓裳")
        assert row["aliases"] == [
            {"alias": "玉罗刹", "count": 130},     # 100 + 30 跨书合并
            {"alias": "白发魔女", "count": 10},
        ]

    def test_canonical_excluded(self):
        """canonical 本名不进 aliases（独立字段已覆盖；EX-4 搜索索引同口径）。"""
        payloads = [_bp(BOOK_A, [_ent("@", "岳鸣珂", 100, variants=[
            {"display": "岳鸣珂", "count": 70},
            {"display": "晦明禅师", "count": 30},
        ])])]
        payload, _ = _index_rows(payloads)
        row = next(r for r in payload["entities"] if r["c"] == "岳鸣珂")
        names = [a["alias"] for a in row["aliases"]]
        assert "岳鸣珂" not in names
        assert names == ["晦明禅师"]

    def test_sorted_by_count_desc_then_alias(self):
        """排序固化：-count 优先，同频次按别名字典序（Python 码点序，与 dossiers.aliases 同规则）。"""
        payloads = [_bp(BOOK_A, [_ent("@", "某人", 30, variants=[
            {"display": "乙名", "count": 5},
            {"display": "甲名", "count": 5},
            {"display": "高频", "count": 20},
            {"display": "某人", "count": 0},
        ])])]
        payload, _ = _index_rows(payloads)
        row = next(r for r in payload["entities"] if r["c"] == "某人")
        assert [a["alias"] for a in row["aliases"]] == ["高频", "乙名", "甲名"]

    def test_search_acceptance_anchors_in_aliases(self):
        """人物页验收第一条的数据前提：白发魔女/玉罗刹/晦明禅师均入 aliases。"""
        payloads = [
            _bp(BOOK_A, [_ent("@", "练霓裳", 130, variants=[
                {"display": "玉罗刹", "count": 100}, {"display": "白发魔女", "count": 30}])]),
            _bp(BOOK_A, [_ent("@", "岳鸣珂", 100, variants=[
                {"display": "岳鸣珂", "count": 70}, {"display": "晦明禅师", "count": 30}])]),
        ]
        payload, _ = _index_rows(payloads)
        rows = {r["c"]: r for r in payload["entities"] if r["t"] == "@"}
        assert "玉罗刹" in {a["alias"] for a in rows["练霓裳"]["aliases"]}
        assert "白发魔女" in {a["alias"] for a in rows["练霓裳"]["aliases"]}
        assert "晦明禅师" in {a["alias"] for a in rows["岳鸣珂"]["aliases"]}


# ================================================================ 2. count 保留 / 无别名空数组 / 形状
class TestAliasShape:
    """count 不丢不重；无别名者 []；旧契约字段不被破坏（只增字段）。"""

    def test_count_preserved_sum(self):
        """aliases count = 各书 variants 频次之和（不丢书、不改数）。"""
        payloads = [
            _bp(BOOK_A, [_ent("☆", "天山剑法", 60, variants=[
                {"display": "天山剑法", "count": 40},
                {"display": "大漠流沙", "count": 20},
            ])]),
            _bp(BOOK_B, [_ent("☆", "天山剑法", 15, variants=[
                {"display": "大漠流沙", "count": 15},
            ])]),
        ]
        payload, _ = _index_rows(payloads)
        row = next(r for r in payload["entities"] if r["c"] == "天山剑法")
        assert row["aliases"] == [{"alias": "大漠流沙", "count": 35}]   # 20 + 15

    def test_no_alias_empty_array_field_present(self):
        """无别名（variants 仅本名）→ aliases == [] 且字段在场（非省略键）。"""
        payloads = [_bp(BOOK_A, [_ent("@", "路人甲", 5)])]     # 默认 variants=本名
        payload, _ = _index_rows(payloads)
        row = next(r for r in payload["entities"] if r["c"] == "路人甲")
        assert "aliases" in row
        assert row["aliases"] == []

    def test_row_only_adds_field(self):
        """旧契约字段 t/c/display/n/b/x/page 逐字段保留，aliases 为新增键。"""
        payloads = [_bp(BOOK_A, [_ent("@", "甲", 35), _ent("@", "乙", 10)])]
        payload, _ = _index_rows(payloads)
        for row in payload["entities"]:
            assert {"t", "c", "display", "n", "b", "x", "page"} <= set(row)
            assert "aliases" in row
            assert isinstance(row["aliases"], list)

    def test_all_index_types_carry_aliases(self):
        """@/☆/◆ 三类均带 aliases（武功/门派总览搜索同样消费）。"""
        payloads = [_bp(BOOK_A, [
            _ent("@", "高手", 35, variants=[{"display": "高手", "count": 25},
                                            {"display": "高兄", "count": 10}]),
            _ent("☆", "天山剑法", 9, variants=[{"display": "天山剑法", "count": 6},
                                               {"display": "天山剑", "count": 3}]),
            _ent("◆", "天山派", 40, variants=[{"display": "天山派", "count": 40}]),
        ])]
        payload, _ = _index_rows(payloads)
        rows = {r["t"]: r for r in payload["entities"]}
        assert rows["@"]["aliases"] == [{"alias": "高兄", "count": 10}]
        assert rows["☆"]["aliases"] == [{"alias": "天山剑", "count": 3}]
        assert rows["◆"]["aliases"] == []          # 无其他叫法 → 空数组


# ================================================================ 3. meta 说明新字段
class TestMetaDocumentsField:
    """数据契约：meta.note 或 field_gaps 必须说明 aliases 新字段（A1）。"""

    def test_meta_note_mentions_aliases(self):
        payloads = [_bp(BOOK_A, [_ent("@", "甲", 35)])]
        payload, _ = _index_rows(payloads)
        assert "aliases" in payload["meta"]["note"]

    def test_meta_field_gaps_or_note_explains_a1(self):
        payloads = [_bp(BOOK_A, [_ent("@", "甲", 35)])]
        payload, _ = _index_rows(payloads)
        gaps = "\n".join(payload["meta"].get("field_gaps") or [])
        assert "别名" in gaps or "别名" in payload["meta"]["note"]

    def test_schema_unchanged_for_consumers(self):
        """schema 保持 entity-index-v1（只增字段不升版；下游 scope.ts/display.ts 不受影响）。"""
        payloads = [_bp(BOOK_A, [_ent("@", "甲", 35)])]
        payload, _ = _index_rows(payloads)
        assert payload["meta"]["schema"] == "entity-index-v1"


# ================================================================ 4. scope 口径一致性
class TestAliasScopeConsistency:
    """scope 模式下 aliases 与 n/b 同源：仅含 scope 内书的 variants（7 书裁剪口径）。"""

    def test_scope_aliases_from_scope_books_only(self):
        payloads = [
            _bp(BOOK_A, [_ent("@", "甲", 45, variants=[
                {"display": "甲", "count": 30}, {"display": "甲大侠", "count": 15}])]),
            _bp(BOOK_B, [_ent("@", "甲", 100, variants=[
                {"display": "甲", "count": 90}, {"display": "甲大侠", "count": 10}])]),
        ]
        scope = {"profile": "demo", "books": [BOOK_A]}
        payload, _ = _index_rows(payloads, books=[BOOK_A, BOOK_B], scope=scope)
        row = next(r for r in payload["entities"] if r["c"] == "甲")
        assert row["n"] == 45                                  # scope 内频次重算
        assert row["aliases"] == [{"alias": "甲大侠", "count": 15}]   # 仅 scope 内书 variants


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
