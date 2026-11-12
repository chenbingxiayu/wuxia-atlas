# -*- coding: utf-8 -*-
"""W0-T3a · EX 导出层 scope 全量接线测试（天山演示版总体方案 §一/§1.2，2026-11-08）。

只测纯函数与合成数据（构造最小输入 → 调用过滤函数），不跑整管线 E2E、不写 site/data。
被测对象（W0-T3a 新增/改造）：
  export_site_common          loc_book / loc_in_scope（「书名·章:行」拆解 helper）、
                              契约 diff 的 scope 感知（scope 外书键=预期裁剪，不计 hard_gap）
  export_site_books_chapters  build_books/build_chapters(scope=…) 书目过滤 +
                              scoped_refs 互文边三分（out_refs/in_refs/refs_ext 降级）
  export_site_graph           assemble_payload(scope=…) 边/节点=scope 书目出现者
  export_site_matches_ratings filter_matches/fighters_of/build_ratings(books=…) +
                              build_matches_payload/build_ratings_payload(scope=…) meta
  export_site_sects_weapons_arts  build_weapons/build_arts/build_sects(scope=…) 过滤+重算
  export_site_gazetteer_universe  build_gazetteer/build_universe(scope=…) +
                              atlas_books（W0-T4：universe 通用 profile 裁 lines 成员/编年谱 +
                              seeds 行经书∩scope 过滤 + open_questions 关涉书⊆scope 过滤；
                              tianshan-demo 单线重建与 canonical 映射见 test_universe_demo.py）
  export_site_audit           build_payload(docs, scope=…) 书目维度过滤
  export_site_all             exporter_cmd --scope 透传

口径固化（测试即规范）：
  - 全量口径（scope=None）行为与现状逐字段一致（方案 R6）：无 refs_ext 字段、meta 无 scope 键。
  - scope 口径：记录/边的书 ∈ scope 才保留；scope 内频次重算（不是全库 total）。
  - universe.json：lines 成员（book ∈ scope）与编年谱（books ∩ scope）裁剪（W0-T3a）；
    interchange_seeds / open_questions 按 scope 过滤（W0-T4；canon_index 未注入 → 种子纯文本降级）。
"""
import json
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（被测模块依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_common as esc  # noqa: E402
import export_site_books_chapters as exb  # noqa: E402
import export_site_graph as exg  # noqa: E402
import export_site_matches_ratings as exm  # noqa: E402
import export_site_sects_weapons_arts as exs  # noqa: E402
import export_site_gazetteer_universe as exu  # noqa: E402
import export_site_audit as exa  # noqa: E402
import export_site_all as exall  # noqa: E402

BOOK_A, BOOK_B = "测试书甲", "测试书乙"
SCOPE_A = {"profile": "demo", "books": [BOOK_A]}
SCOPE_AB = {"profile": "demo2", "books": [BOOK_A, BOOK_B]}
# 契约 diff 的 scope 感知测试须用真实书目（known_book_names 以 config 章回版书目为界）
REAL_IN, REAL_OUT = "白发魔女传", "大唐游侠传"


# ================================================================ 0. loc_book / loc_in_scope helper
class TestLocBook:
    """「书名·章:行」定位符拆解（EX-4 节点/边 locs 书名前缀判定的通用 helper）。"""

    def test_loc_book_basic(self):
        assert esc.loc_book("白发魔女传·003:12") == "白发魔女传"
        assert esc.loc_book("七剑下天山·021:93") == "七剑下天山"
        assert esc.loc_book("塞外奇侠传·027:5") == "塞外奇侠传"

    def test_loc_book_no_separator(self):
        """无书名前缀（裸 章:行）→ None（scope 下视为不可归书）。"""
        assert esc.loc_book("003:12") is None
        assert esc.loc_book("") is None
        assert esc.loc_book(None) is None
        assert esc.loc_book(123) is None

    def test_loc_in_scope(self):
        assert esc.loc_in_scope("测试书甲·001:2", SCOPE_A) is True
        assert esc.loc_in_scope("测试书乙·001:2", SCOPE_A) is False
        assert esc.loc_in_scope("001:2", SCOPE_A) is False       # 无前缀 → 不可归书
        assert esc.loc_in_scope("测试书乙·001:2", None) is True   # 全量口径恒 True


# ================================================================ 1. EX-1 books/chapters + refs_ext
def _edge(src, dst, kind="authorial", loc="016:11", snippet="……详见拙著。"):
    return {"source": src, "target": dst, "kind": kind, "probe": dst,
            "loc": loc, "snippet": snippet}


def _intertext():
    """互文索引：甲→乙、甲→丙(×2)、丁→甲、乙→甲。"""
    edges = [
        _edge(BOOK_A, BOOK_B, "authorial", "016:11"),
        _edge(BOOK_A, "测试书丙", "quoted", "003:2"),
        _edge(BOOK_A, "测试书丙", "quoted", "004:5"),
        _edge("测试书丁", BOOK_A, "authorial", "001:9"),
        _edge(BOOK_B, BOOK_A, "quoted", "002:3"),
    ]
    return exb.intertext_index(edges)


class TestEX1ScopedRefs:
    """互文边三分：对端 ∈ scope 留 out_refs/in_refs；对端 ∉ scope 降级 refs_ext（方案 §1.2）。"""

    def test_scope_edges_split_and_refs_ext(self):
        out_edges, in_edges = _intertext()
        out_refs, in_refs, refs_ext = exb.scoped_refs(out_edges, in_edges, BOOK_A, SCOPE_AB)
        # out：甲→乙 留下；甲→丙（scope 外）降级
        assert [r["book"] for r in out_refs] == [BOOK_B]
        # in：乙→甲 留下；丁→甲（scope 外）降级
        assert [r["book"] for r in in_refs] == [BOOK_B]
        ext = {(r["book"], r["dir"]): r for r in refs_ext}
        assert set(ext) == {("测试书丙", "out"), ("测试书丁", "in")}
        assert ext[("测试书丙", "out")]["count"] == 2
        assert ext[("测试书丁", "in")]["count"] == 1
        # refs_ext 与 out_refs 同构（book/kind/count/locs/sample）+ dir 方向标记
        for r in refs_ext:
            assert set(r) == {"book", "kind", "count", "locs", "sample", "dir"}
            assert r["locs"] and "·" in r["locs"][0]

    def test_scope_narrow_drops_peer(self):
        """scope 只含甲书时：乙书对端也属站外 → out_refs/in_refs 为空、对端入 refs_ext。"""
        out_edges, in_edges = _intertext()
        out_refs, in_refs, refs_ext = exb.scoped_refs(out_edges, in_edges, BOOK_A, SCOPE_A)
        assert out_refs == [] and in_refs == []
        # 甲→乙/甲→丙 降级 dir=out；丁→甲、乙→甲 降级 dir=in
        assert {(r["book"], r["dir"]) for r in refs_ext} == \
            {(BOOK_B, "out"), ("测试书丙", "out"), ("测试书丁", "in"), (BOOK_B, "in")}

    def test_full_caliber_unchanged(self):
        """全量口径：与 pack_refs 旧口径一致，refs_ext=None（不产出该字段）。"""
        out_edges, in_edges = _intertext()
        out_refs, in_refs, refs_ext = exb.scoped_refs(out_edges, in_edges, BOOK_A, None)
        assert refs_ext is None
        assert out_refs == exb.pack_refs(out_edges, BOOK_A)
        assert in_refs == exb.pack_refs(in_edges, BOOK_A)
        assert {r["book"] for r in out_refs} == {BOOK_B, "测试书丙"}

    def test_counts_follow_scope(self):
        """intertext_out/in 计数随边过滤（= out_refs/in_refs 的 count 合计）。"""
        out_edges, in_edges = _intertext()
        out_refs, in_refs, _ = exb.scoped_refs(out_edges, in_edges, BOOK_A, SCOPE_AB)
        assert sum(r["count"] for r in out_refs) == 1
        assert sum(r["count"] for r in in_refs) == 1


def _wmeta(*books):
    return {"works": [{"book": b, "no": i + 1, "chars": 100 + i} for i, b in enumerate(books)],
            "missing_works": []}


def _corpus(*books):
    return {b: [{"no": 1, "title": "第一回"}, {"no": 2, "title": "第二回"}] for b in books}


class TestEX1Books:
    def test_books_filtered_and_meta_scope(self):
        legacy = {"wmeta": _wmeta(BOOK_A, BOOK_B), "inter": {"edges": []}}
        payload, _stats = exb.build_books(_corpus(BOOK_A, BOOK_B), {}, scope=SCOPE_A, legacy=legacy)
        assert [b["book"] for b in payload["books"]] == [BOOK_A]
        assert payload["meta"]["totals"]["books"] == 1
        assert payload["meta"]["scope"] == "demo"
        assert any("scope" in g for g in payload["meta"]["field_gaps"])

    def test_scope_book_gets_refs_ext(self):
        legacy = {"wmeta": _wmeta(BOOK_A), "inter": {"edges": [
            _edge(BOOK_A, BOOK_B, "authorial"), _edge("测试书丁", BOOK_A, "quoted")]}}
        payload, _stats = exb.build_books(_corpus(BOOK_A), {}, scope=SCOPE_A, legacy=legacy)
        rec = payload["books"][0]
        assert [r["book"] for r in rec["out_refs"]] == []          # 乙 scope 外 → 不留
        assert {r["dir"] for r in rec["refs_ext"]} == {"out", "in"}

    def test_full_caliber_no_refs_ext_no_scope(self):
        legacy = {"wmeta": _wmeta(BOOK_A, BOOK_B), "inter": {"edges": [_edge(BOOK_A, BOOK_B)]}}
        payload, _stats = exb.build_books(_corpus(BOOK_A, BOOK_B), {}, legacy=legacy)
        assert len(payload["books"]) == 2
        assert "scope" not in payload["meta"]
        assert all("refs_ext" not in b for b in payload["books"])
        assert payload["books"][0]["out_refs"][0]["book"] == BOOK_B


class TestEX1Chapters:
    def test_chapters_filtered_and_meta_scope(self):
        payload, _stats = exb.build_chapters(_corpus(BOOK_A, BOOK_B), scope=SCOPE_A)
        book_keys = [k for k in payload if k != "meta"]
        assert book_keys == [BOOK_A]
        assert payload["meta"]["scope"] == "demo"

    def test_full_caliber_all_books(self):
        payload, _stats = exb.build_chapters(_corpus(BOOK_A, BOOK_B))
        assert [k for k in payload if k != "meta"] == sorted([BOOK_A, BOOK_B])
        assert "scope" not in payload["meta"]


# ================================================================ 2. EX-4 graph
def _rel_edge(s, sa, pred, o, oa, count=1, evidence=None, loc=None):
    e = {"subject": s, "subject_type": sa, "predicate": pred, "object": o, "object_type": oa,
         "count": count, "confidence": "ok"}
    if evidence is not None:
        e["evidence"] = evidence
    if loc is not None:
        e["loc"] = loc
    return e


def _rel():
    return [
        {"book": BOOK_A, "generated": "g1", "n5_counts": {}, "edges": [
            _rel_edge("张三", "@", "师承", "李四", "@", 2, evidence=[{"loc": "003:12"}]),
            _rel_edge("张三", "@", "交手", "王五", "@", 1, evidence=[], loc="004:3"),
        ]},
        {"book": BOOK_B, "generated": "g2", "n5_counts": {}, "edges": [
            _rel_edge("赵六", "@", "师承", "钱七", "@", 3, evidence=[{"loc": "001:1"}]),
        ]},
    ]


def _graph_ctx():
    reg = {"entities": [], "count": 0, "generated": None,
           "by_canon_type": {}, "canon_aliases": {}, "alias_to_canon": {}}
    conc = {"total": {}, "variants": {}, "generated": {}}
    return reg, conc


class TestEX4Graph:
    def test_scope_filters_edges_nodes_and_meta(self):
        reg, conc = _graph_ctx()
        payload, _ctx = exg.assemble_payload(_rel(), reg, conc, scope=SCOPE_A)
        # 边：只留 scope 书（甲）的 2 条；locs 书名前缀 ∈ scope
        assert len(payload["edges"]) == 2
        assert all(set(e["books"]) == {BOOK_A} for e in payload["edges"])
        assert all(esc.loc_book(loc) == BOOK_A for e in payload["edges"] for loc in e["locs"])
        # 节点：scope 书边端点（张三/李四/王五），不含 scope 外书的端点（赵六/钱七）
        ids = {n["id"] for n in payload["nodes"]}
        assert {"张三", "李四", "王五"} <= ids
        assert ids.isdisjoint({"赵六", "钱七"})
        assert all(set(n["books"]) <= {BOOK_A} for n in payload["nodes"])
        assert payload["meta"]["scope"] == "demo"

    def test_full_caliber_keeps_all_books(self):
        reg, conc = _graph_ctx()
        payload, _ctx = exg.assemble_payload(_rel(), reg, conc)
        assert len(payload["edges"]) == 3
        assert {n["id"] for n in payload["nodes"]} >= {"赵六", "钱七"}
        assert "scope" not in payload["meta"]


# ================================================================ 3. EX-5 matches/ratings
def _match(mid, a, b, outcome, book, conf="high"):
    return {"id": mid, "a": a, "b": b, "outcome": outcome, "weight": 0.8, "confidence": conf,
            "modifiers": [], "kind": "单挑", "book": book, "loc": "001:005",
            "scene": "S001-01", "evidence": {"source": "scene_word", "rule": "胜负词表（场景）"}}


def _matches():
    return [
        _match("M001", "张三", "李四", "win", BOOK_A),
        _match("M002", "丙七", "丁八", "loss", BOOK_B),
        _match("M003", "张三", "丙七", "draw", BOOK_B, conf="medium"),
    ]


class TestEX5Matches:
    def test_filter_matches_scope(self):
        kept = exm.filter_matches(_matches(), SCOPE_A)
        assert [m["id"] for m in kept] == ["M001"]
        assert exm.filter_matches(_matches(), None) == _matches()   # 全量口径 no-op

    def test_fighters_recomputed(self):
        """fighters 按过滤后对局重算：只在 scope 外出战者不出现。"""
        kept = exm.filter_matches(_matches(), SCOPE_A)
        assert exm.fighters_of(kept) == sorted({"张三", "李四"})
        assert "丙七" not in exm.fighters_of(kept)
        assert exm.fighters_of(_matches()) == sorted({"张三", "李四", "丙七", "丁八"})

    def test_ratings_recomputed_from_filtered(self):
        ratings = exm.build_ratings(exm.filter_matches(_matches(), SCOPE_A), books=[BOOK_A])
        assert {p["name"] for p in ratings["players"]} == {"张三", "李四"}
        by = {p["name"]: p for p in ratings["players"]}
        assert by["张三"]["w/d/l"] == [1, 0, 0]
        assert by["李四"]["w/d/l"] == [0, 0, 1]
        assert set(by["张三"]["per_book"]) == {BOOK_A}     # per_book 覆盖 scope 书

    def test_meta_scope_written(self):
        matches = exm.filter_matches(_matches(), SCOPE_A)
        mp = exm.build_matches_payload(matches, exm.fighters_of(matches),
                                       {"dropped": 0, "in_quote": 0, "no_participants": 0},
                                       {"scene_word": 1, "event_outcome": 0},
                                       {"ev_total": 10, "combat_total": 3}, scope=SCOPE_A)
        assert mp["meta"]["scope"] == "demo"
        assert any("scope" in g for g in mp["meta"]["field_gaps"])
        ratings = exm.build_ratings(matches, books=[BOOK_A])
        rp = exm.build_ratings_payload(ratings, matches, scope=SCOPE_A)
        assert rp["meta"]["scope"] == "demo"

    def test_full_caliber_meta_no_scope(self):
        matches = _matches()
        mp = exm.build_matches_payload(matches, exm.fighters_of(matches),
                                       {"dropped": 0, "in_quote": 0, "no_participants": 0},
                                       {"scene_word": 2, "event_outcome": 1},
                                       {"ev_total": 10, "combat_total": 3})
        assert "scope" not in mp["meta"]
        rp = exm.build_ratings_payload(exm.build_ratings(matches), matches)
        assert "scope" not in rp["meta"]


# ================================================================ 4. EX-6 sects/weapons/arts
class TestEX6Weapons:
    def _src(self, extra_art=None):
        art = {
            "canonical": "测试神兵", "kind": "剑", "level": "名物", "grade": "名物",
            "grade_basis": "x", "conf": "ok", "status": "auto",
            "chain": [{"verb": "夺", "persons": ["张三"], "book": BOOK_A, "loc": "1:2", "conf": "strong"},
                      {"verb": "夺", "persons": ["李四"], "book": BOOK_B, "loc": "1:3", "conf": "ok"}],
            "holders": [{"name": "张三", "n": 5}], "borrowers": [], "makers": [],
            "end_state": None,
            "books": {BOOK_A: [1, 2], BOOK_B: [3]},
            "count": 10, "ev_total": 2,
            "evidence": [{"book": BOOK_A, "loc": "1:2", "kind": "共现"},
                         {"book": BOOK_B, "loc": "1:3", "kind": "共现"}],
        }
        arts = [art] + ([extra_art] if extra_art else [])
        conc = {("•", "测试神兵"): {"count": 30, "books": {BOOK_A: 20, BOOK_B: 10},
                                    "chapters": {BOOK_A: [1, 2, 3], BOOK_B: [4]}, "variants": set()}}
        return {
            "artifacts": {"artifacts": arts, "meta": {"rev": 16}, "alias_candidates": []},
            "old_weapons": {"weapons": []},
            "weapon_alias": {}, "weapon_canon": set(),
            "conc": conc, "conc_books": [BOOK_A, BOOK_B], "wordlist": [],
        }

    def test_scope_filter_and_count_recalc(self):
        payload, _st = exs.build_weapons(self._src(), scope=SCOPE_A)
        assert len(payload["weapons"]) == 1
        rec = payload["weapons"][0]
        assert rec["books"] == {BOOK_A: [1, 2, 3]}          # books 过滤（chapters 取 conc）
        assert rec["count"] == 20                            # 频次按 scope 重算
        assert [e["book"] for e in rec["chain"]] == [BOOK_A]
        assert [e["book"] for e in rec["evidence"]] == [BOOK_A]
        assert payload["meta"]["scope"] == "demo"

    def test_scope_out_only_weapon_dropped(self):
        out_only = dict(self._src()["artifacts"]["artifacts"][0], canonical="站外神兵",
                        books={BOOK_B: [1]}, count=5,
                        chain=[{"verb": "夺", "persons": ["李四"], "book": BOOK_B, "loc": "1:3", "conf": "ok"}],
                        evidence=[{"book": BOOK_B, "loc": "1:3", "kind": "共现"}])
        src = self._src(extra_art=out_only)
        src["conc"][("•", "站外神兵")] = {"count": 5, "books": {BOOK_B: 5},
                                          "chapters": {BOOK_B: [1]}, "variants": set()}
        payload, _st = exs.build_weapons(src, scope=SCOPE_A)
        assert [r["canonical"] for r in payload["weapons"]] == ["测试神兵"]

    def test_full_caliber_unchanged(self):
        payload, _st = exs.build_weapons(self._src())
        rec = payload["weapons"][0]
        assert rec["count"] == 30
        assert set(rec["books"]) == {BOOK_A, BOOK_B}
        assert len(rec["chain"]) == 2 and len(rec["evidence"]) == 2
        assert "scope" not in payload["meta"]


class TestEX6Arts:
    def _src(self):
        old_art = {
            "canonical": "测试剑法", "category": "剑法", "aliases": [], "ev_total": 8,
            "books": [BOOK_A, BOOK_B], "cross_book": True,
            "relations": {
                BOOK_A: {"relations": [{"s": "子式甲", "st": "☆", "pred": "子式",
                                        "locs": ["1:2"], "ev": 3, "note": ""}]},
                BOOK_B: {"relations": [{"s": "子式乙", "st": "☆", "pred": "子式",
                                        "locs": ["1:5"], "ev": 5, "note": ""}]},
            },
        }
        return {
            "old_arts": {"arts": [old_art], "meta": {"totals": {"by_category": {"剑法": 1}}}},
            "art_alias": {}, "art_canon": {"测试剑法"},
            "moves": {"moves": []},
            "conc": {("☆", "测试剑法"): {"count": 100, "books": {BOOK_A: 60, BOOK_B: 40},
                                          "chapters": {}, "variants": set()},
                     ("☆", "测试拳法"): {"count": 100, "books": {BOOK_A: 60, BOOK_B: 40},
                                          "chapters": {}, "variants": set()}},
            "conc_books": [BOOK_A, BOOK_B],
            "wordlist": [{"type": "☆", "canonical": "测试拳法", "surface": "", "note": "具名技艺"}],
        }

    def test_scope_relations_books_ev_total(self):
        payload, _st = exs.build_arts(self._src(), scope=SCOPE_A)
        by = {r["canonical"]: r for r in payload["arts"]}
        sword = by["测试剑法"]
        assert sword["books"] == [BOOK_A]
        assert list(sword["relations"]) == [BOOK_A]          # relations book 键过滤
        assert sword["ev_total"] == 3                         # 按过滤后 relations 证据重算
        assert sword["cross_book"] is False
        fist = by["测试拳法"]                                  # 无 relations：按 conc scope 书重算
        assert fist["books"] == [BOOK_A]
        assert fist["ev_total"] == 60
        assert payload["meta"]["scope"] == "demo"
        assert payload["meta"]["books"] == [BOOK_A]

    def test_scope_out_only_art_dropped(self):
        src = self._src()
        src["old_arts"]["arts"].append(dict(src["old_arts"]["arts"][0], canonical="站外功法",
                                            books=[BOOK_B], cross_book=False,
                                            relations={BOOK_B: src["old_arts"]["arts"][0]["relations"][BOOK_B]}))
        src["art_canon"].add("站外功法")
        payload, _st = exs.build_arts(src, scope=SCOPE_A)
        assert "站外功法" not in {r["canonical"] for r in payload["arts"]}

    def test_full_caliber_unchanged(self):
        payload, _st = exs.build_arts(self._src())
        by = {r["canonical"]: r for r in payload["arts"]}
        sword = by["测试剑法"]
        assert sword["ev_total"] == 8 and sword["cross_book"] is True
        assert set(sword["relations"]) == {BOOK_A, BOOK_B}
        assert by["测试拳法"]["ev_total"] == 100
        assert "scope" not in payload["meta"]
        assert set(payload["meta"]["books"]) == {BOOK_A, BOOK_B}


class TestEX6Sects:
    def _src(self):
        sect = {
            "canonical": "测试派", "books": [BOOK_A, BOOK_B], "cross_book": True, "ev_total": 9,
            "arts_by_pred": {"拥有": [{"art": "测试剑法", "pred": "拥有", "level": "功法",
                                       "locs": ["1:2"], "ev": 1, "note": "", "book": BOOK_B}]},
            "members": [], "tenures": [], "lineage_gaps": [], "lineage_todo": [],
        }
        out_sect = json.loads(json.dumps(sect, ensure_ascii=False))
        out_sect.update({"canonical": "站外派", "books": [BOOK_B], "cross_book": False,
                         "ev_total": 2})
        return {
            "lineage": {"sects": []},
            "old_sects": {"sects": [sect, out_sect], "meta": {"note": ""}},
            "sect_alias": {}, "sect_canon": {"测试派", "站外派"},
            "conc": {("◆", "测试派"): {"count": 50, "books": {BOOK_A: 30, BOOK_B: 20},
                                        "chapters": {}, "variants": set()}},
            "conc_books": [BOOK_A, BOOK_B],
            "moves": {"moves": []},
            "entities": [], "wordlist": [],
        }

    def test_scope_books_intersect_and_pred_filter(self):
        payload, _st = exs.build_sects(self._src(), scope=SCOPE_A)
        assert [s["canonical"] for s in payload["sects"]] == ["测试派"]   # 站外派（仅乙书）被裁
        sect = payload["sects"][0]
        assert sect["books"] == [BOOK_A]
        assert sect["cross_book"] is False
        assert sect["arts_by_pred"] == {}                                # 拥有边 book=乙 → 过滤为空
        assert payload["meta"]["scope"] == "demo"
        assert payload["meta"]["books"] == [BOOK_A]

    def test_full_caliber_unchanged(self):
        payload, _st = exs.build_sects(self._src())
        assert {s["canonical"] for s in payload["sects"]} == {"测试派", "站外派"}
        sect = next(s for s in payload["sects"] if s["canonical"] == "测试派")
        assert set(sect["books"]) == {BOOK_A, BOOK_B} and sect["cross_book"] is True
        assert "scope" not in payload["meta"]


# ================================================================ 5. EX-7 gazetteer/universe/atlas
class TestEX7Gazetteer:
    def _src(self):
        return {"gazetteer": {"places": [
                    {"id": "p1", "name": "甲城", "loc_mode": "coord", "kind": "城市",
                     "real": None, "lat": 1.0, "lng": 2.0, "precision": "exact",
                     "verified": True, "aliases": [], "books": {BOOK_A: [1], BOOK_B: [2]}},
                    {"id": "p2", "name": "乙地", "loc_mode": "coord", "kind": "城市",
                     "real": None, "lat": 3.0, "lng": 4.0, "precision": "exact",
                     "verified": False, "aliases": [], "books": {BOOK_B: [3]}},
                    {"id": "p3", "name": "无书", "loc_mode": "coord", "kind": "城市",
                     "real": None, "lat": 5.0, "lng": 6.0, "precision": "exact",
                     "verified": False, "aliases": [], "books": {}},
                ], "meta": {}},
               "old_gazetteer": None}

    def test_scope_places_and_books(self):
        payload, _st = exu.build_gazetteer(self._src(), scope=SCOPE_A)
        assert [p["id"] for p in payload["places"]] == ["p1"]
        assert payload["places"][0]["books"] == {BOOK_A: [1]}
        assert payload["meta"]["scope"] == "demo"

    def test_full_caliber_unchanged(self):
        payload, _st = exu.build_gazetteer(self._src())
        assert len(payload["places"]) == 3
        assert "scope" not in payload["meta"]


class TestEX7Universe:
    def _series(self):
        return {
            "lines": [
                {"color": "#fff", "line": "测试线",
                 "members": [{"book": BOOK_A, "order": 1}, {"book": BOOK_B, "order": 2}]},
                {"color": "#000", "line": "站外线", "members": [{"book": BOOK_B, "order": 1}]},
            ],
            "chronology_spine": [
                {"era": "era1", "books": [BOOK_A, BOOK_B], "todo": False},
                {"era": "era2", "books": [BOOK_B], "todo": False},
            ],
            "interchange_seeds": [{"name": "seed1", "books": [BOOK_A, BOOK_B], "note": "n"}],
            "open_questions": ["问题一（关涉测试书乙）", "问题二（关涉测试书甲）"],
        }

    def test_scope_generic_profile_w0t4_sections(self):
        """W0-T4（非 tianshan-demo profile → 通用口径）：lines 成员裁剪（T3a）+
        seeds 行经书 ∩ scope 过滤 + open_questions 关涉书 ⊆ scope 过滤；
        canon_index 未提供 → 种子不加 canonical 字段（纯文本降级）。
        （tianshan-demo 的单线重建 + canonical 映射见 test_universe_demo.py）"""
        series = self._series()
        payload, st = exu.build_universe({"series": series}, scope=SCOPE_A)
        assert [ln["line"] for ln in payload["lines"]] == ["测试线"]
        assert [m["book"] for m in payload["lines"][0]["members"]] == [BOOK_A]
        assert [sp["era"] for sp in payload["chronology_spine"]] == ["era1"]
        assert payload["chronology_spine"][0]["books"] == [BOOK_A]
        # W0-T4 seeds：seed1 行经 [甲,乙] ∩ [甲] ≠ ∅ → 保留；无对照索引 → 无 canonical 字段
        assert [s["name"] for s in payload["interchange_seeds"]] == ["seed1"]
        assert "canonical" not in payload["interchange_seeds"][0]
        # W0-T4 open_questions：问题一关涉书 {乙} ⊄ scope → 裁；问题二关涉 {甲} ⊆ scope → 留
        assert payload["open_questions"] == ["问题二（关涉测试书甲）"]
        assert payload["meta"]["scope"] == "demo"
        assert st["lines_trimmed"] == 1 and st["spine_trimmed"] == 1

    def test_full_caliber_sections_identical(self):
        series = self._series()
        payload, _st = exu.build_universe({"series": series})
        for k in ("lines", "chronology_spine", "interchange_seeds", "open_questions"):
            assert payload[k] == series[k]
        assert "scope" not in payload["meta"]


class TestEX7Atlas:
    def test_atlas_books_scope(self):
        books = ["七剑下天山", "白发魔女传", "大唐游侠传", BOOK_A]
        assert exu.atlas_books(books, SCOPE_A) == [BOOK_A]
        assert exu.atlas_books(books, None) == books                      # 全量口径不裁

    def test_scope_books_from_real_list(self):
        scope = esc.load_scope("tianshan-demo")
        picked = exu.atlas_books(exu.BOOKS, scope)
        assert set(picked) == set(scope["books"])                         # 恰为 7 书
        assert picked == [b for b in exu.BOOKS if b in set(scope["books"])]  # 顺序 = BOOKS 契约基线


# ================================================================ 6. EX-8 audit
def _doc(book, rid="C2", hits=1):
    return {
        "book": book, "schema": "wuxia-consistency-v1", "generated_at": f"g-{book}",
        "tool": "lint_consistency", "spec": {}, "interfaces": {},
        "violations": [{"vid": f"v-{book}", "rule_id": rid, "rule_title": "规则" + rid,
                        "area": "时序", "severity": "warning", "grade": "B",
                        "confidence": "high", "locator": "001:5", "chapter": 1, "pn": 5,
                        "subject": "张三", "object": "李四", "narrative_mode": "",
                        "exempted": False, "exemption": "", "spec_cite": "",
                        "rationale": "原创分析", "extra": {}, "quote": "原文不发布"}],
        "exemptions": [{"rule_id": rid, "locator": "001:5", "reason": "豁免原因", "subject": "s"}],
        "summary": {"rules_total": 39, "rules_selected": 39, "rules_with_hits": hits},
        "inputs": {"chapters": 10, "paragraphs": 100},
        "rule_coverage": [{"rule_id": rid, "area": "时序", "title": "规则" + rid, "kind": "auto",
                           "spec_cite": "", "hits": hits, "status": "ok", "selected": True,
                           "note": ""}],
    }


class TestEX8Audit:
    def test_scope_filters_books_dimension(self):
        docs = [_doc(BOOK_A, "C2"), _doc(BOOK_B, "W9")]
        payload = exa.build_payload(docs, scope=SCOPE_A)
        assert {v["book"] for v in payload["violations"]} == {BOOK_A}
        assert list(payload["by_book"]) == [BOOK_A]
        assert {r["rule_id"] for r in payload["rule_coverage"]} == {"C2"}
        assert all(set(r["books"]) == {BOOK_A} for r in payload["rule_coverage"])
        assert payload["meta"]["scope"] == "demo"
        assert payload["meta"]["engine"]["books"] == [BOOK_A]

    def test_full_caliber_keeps_all_books(self):
        docs = [_doc(BOOK_A, "C2"), _doc(BOOK_B, "W9")]
        payload = exa.build_payload(docs)
        assert {v["book"] for v in payload["violations"]} == {BOOK_A, BOOK_B}
        assert {r["rule_id"] for r in payload["rule_coverage"]} == {"C2", "W9"}
        assert "scope" not in payload["meta"]


# ================================================================ 7. 总入口透传（export_site_all）
class TestExportAllPassthrough:
    def test_cmd_with_scope(self):
        cmd = exall.exporter_cmd(Path("x.py"), apply=False, scope=SCOPE_A)
        assert cmd == [sys.executable, "x.py", "--scope", "demo"]

    def test_cmd_without_scope_or_all(self):
        """全量口径与 --scope all 都不透传 --scope（现状不变）。"""
        assert exall.exporter_cmd(Path("x.py"), apply=False, scope=None) == [sys.executable, "x.py"]
        assert exall.exporter_cmd(Path("x.py"), apply=True, scope=None) == \
            [sys.executable, "x.py", "--apply"]

    def test_scope_arg_parsing_via_common(self):
        assert esc.scope_from_args(["--scope", "tianshan-demo"]) == "tianshan-demo"
        assert esc.scope_from_args(["--scope", "all"]) is None


# ================================================================ 8. 契约 diff 的 scope 感知
class TestScopeAwareContractDiff:
    """scope 口径下旧契约的 scope 外书键=预期裁剪：记录 scope_dropped_keys、不计 hard_gap。

    diff_staging 走真实解析路径（meta.scope → load_scope），契约文件用临时目录合成
    （避免耦合真实契约的递归形状）；书名用真实书目（known_book_names 以章回版书目为界）。
    """

    def _patch_contract(self, tmp_path, monkeypatch):
        def _slice():
            return {"type": "dict", "keys": {"chapters": {"type": "array"}, "lit": {"type": "bool"}}}
        contract = {"name": "chapters.json", "generated": "t", "schema": {"type": "dict", "keys": {
            "meta": {"type": "dict", "keys": {}}, REAL_IN: _slice(), REAL_OUT: _slice()}}}
        p = tmp_path / "chapters.json.schema.json"
        p.write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(esc, "contract_path", lambda name: p)
        return p

    def test_chapters_book_keys_dropped(self, tmp_path, monkeypatch):
        """scope 口径：chapters.json 的 scope 外书键（如 大唐游侠传）属预期裁剪，不计 hard_gap。"""
        self._patch_contract(tmp_path, monkeypatch)
        payload = {"meta": {"scope": "tianshan-demo"}, REAL_IN: {"chapters": [], "lit": False}}
        diff = esc.diff_staging("chapters.json", payload)
        assert diff["hard_gap_count"] == 0
        assert diff["scope_dropped_keys"] == [REAL_OUT]
        assert diff["missing_keys"] == []

    def test_full_caliber_still_counts_missing_keys(self, tmp_path, monkeypatch):
        """全量口径（meta 无 scope）：旧书键缺失仍计 hard_gap（R6：行为与现状一致）。"""
        self._patch_contract(tmp_path, monkeypatch)
        payload = {"meta": {}, REAL_IN: {"chapters": [], "lit": False}}
        diff = esc.diff_staging("chapters.json", payload)
        assert diff["hard_gap_count"] == 1
        assert diff["missing_keys"] == [REAL_OUT]
        assert diff["scope_dropped_keys"] == []

    def test_scope_books_of_payload(self):
        assert esc.scope_books_of({"meta": {"scope": "tianshan-demo"}}) == \
            esc.load_scope("tianshan-demo")["books"]
        assert esc.scope_books_of({"meta": {}}) is None
        assert esc.scope_books_of({"meta": {"scope": "不存在的profile"}}) is None
        assert esc.scope_books_of(None) is None

    def test_diff_against_contract_direct_scope_param(self):
        """diff_against_contract 的 scope_books 参数：合成契约直接验证（不经 meta.scope）。"""
        def _slice():
            return {"type": "dict", "keys": {"chapters": {"type": "array"}, "lit": {"type": "bool"}}}
        contract = {"name": "chapters.json", "schema": {"type": "dict", "keys": {
            "meta": {"type": "dict", "keys": {}}, REAL_IN: _slice(), REAL_OUT: _slice()}}}
        payload = {"meta": {"scope": "tianshan-demo"}, REAL_IN: {"chapters": [], "lit": False}}
        diff = esc.diff_against_contract("chapters.json", payload, contract, scope_books=[REAL_IN])
        assert diff["hard_gap_count"] == 0 and diff["scope_dropped_keys"] == [REAL_OUT]
        diff_full = esc.diff_against_contract("chapters.json", payload, contract)
        assert diff_full["hard_gap_count"] == 1 and diff_full["scope_dropped_keys"] == []
