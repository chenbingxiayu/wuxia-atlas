# -*- coding: utf-8 -*-
"""D5 · weapons rev17 毁噪声自动证伪五规则测试（名物页重构设计 §六、§5.1 疑似误伤折叠，2026-11-11）。

被测对象：scripts/export_site_sects_weapons_arts.py 新增 rev17 纯函数 + build_weapons 接线
  parse_loc_pair(loc)            「章:行」→ (章, 行) int（书名前缀剥去；解析失败 (0,0)）
  chron_key(edge, book_order)    编年键（宇宙书序, 章, 行, 书名）——书序来自 scope["books"]
                                 （= universe lines 成员序/用户裁定 2026-11-08）
  dedupe_chain(chain)            ④ 完全重复边（verb+persons+book+loc）合并 ×n（保首现序）
  sort_chain_chrono(chain, …)    ③ 编年排序（书按宇宙编年、回按章号、行号兜底）
  mark_destroy_suspect(chain, …) ① 后续证伪：毁边之后（编年序）仍有持有/出场铁证 → suspect=True
  mark_destroy_subject_low(…)    ② 主语证伪：非 suspect 毁边 persons 首位 ∉ 持有人前 5 → subject_low
  attach_dir(chain, makers, …)   ⑤ 方向化：铸/借边 dir={"kind": verb, "who": [persons∩makers/borrowers]}
  build_weapons(src, scope=…)    rev17 仅 scope 口径接线（meta.rev=17 + totals 三计数）；
                                 全量口径（scope=None）逐字段维持现状（方案 R6）

口径固化（测试即规范）：
  - suspect 宁缺毋滥：只有「毁后仍有出场」铁证才折叠——持有铁证=后续 chain 边 verb ∉ {毁, 铸}
    （毁句不自证、重铸=原物或已毁存疑）；出场铁证=books 同书更大回号或编年序更后书任一回目。
  - 主语证伪是降权注记（subject_low），**不折叠**——保留主线。
  - 夺/赠/传无 object 数据：不加 dir（不伪造方向），保持 persons 并列。
  - 全量口径（scope=None）：无 n/suspect/subject_low/dir 字段、不排序不去重、meta 无 rev17 计数。
"""
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（被测模块依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_sects_weapons_arts as exs  # noqa: E402

# 宇宙编年：书甲在前、书乙在后（scope["books"] 顺序 = universe lines 成员序）
BOOK_A, BOOK_B = "编年书甲", "编年书乙"
SCOPE_AB = {"profile": "demo", "books": [BOOK_A, BOOK_B]}
BOOK_ORDER = {BOOK_A: 0, BOOK_B: 1}


# ================================================================ 合成 fixture
def _edge(verb, persons, book, loc, conf="strong"):
    return {"verb": verb, "persons": list(persons), "book": book, "loc": loc, "conf": conf}


def _art(chain, books, holders=None, makers=None, borrowers=None, canonical="测试名物"):
    return {
        "canonical": canonical, "kind": "剑", "level": "名物", "grade": "名物",
        "grade_basis": "明文", "conf": "ok", "status": "auto",
        "chain": list(chain),
        "holders": holders or [], "borrowers": borrowers or [], "makers": makers or [],
        "end_state": None,
        "books": dict(books),
        "count": 10, "ev_total": 2,
        "evidence": [{"book": BOOK_A, "loc": "1:2", "kind": "共现"}],
    }


def _src(arts):
    """最小合成 src（同 test_export_scope_wiring.TestEX6Weapons 口径；conc 无命中 → books 走神兵表原值）。"""
    return {
        "artifacts": {"artifacts": arts, "meta": {"rev": 16}, "alias_candidates": []},
        "old_weapons": {"weapons": []},
        "weapon_alias": {}, "weapon_canon": set(),
        "conc": {}, "conc_books": [BOOK_A, BOOK_B],
        "wordlist": [],
    }


def _build(art, scope=SCOPE_AB):
    payload, _st = exs.build_weapons(_src([art]), scope=scope)
    assert len(payload["weapons"]) == 1
    return payload, payload["weapons"][0]


# ================================================================ 0. parse_loc_pair / chron_key
class TestLocAndChron:
    def test_parse_loc_pair(self):
        assert exs.parse_loc_pair("5:7") == (5, 7)
        assert exs.parse_loc_pair("47:163") == (47, 163)
        assert exs.parse_loc_pair("编年书甲·003:12") == (3, 12)   # 书名前缀剥去
        assert exs.parse_loc_pair("") == (0, 0)
        assert exs.parse_loc_pair(None) == (0, 0)
        assert exs.parse_loc_pair("x:y") == (0, 0)

    def test_chron_key_book_order_then_chapter(self):
        assert exs.chron_key(_edge("夺", ["甲"], BOOK_A, "3:5"), BOOK_ORDER) < \
               exs.chron_key(_edge("夺", ["甲"], BOOK_A, "9:1"), BOOK_ORDER)
        assert exs.chron_key(_edge("夺", ["甲"], BOOK_A, "9:1"), BOOK_ORDER) < \
               exs.chron_key(_edge("赠", ["乙"], BOOK_B, "1:2"), BOOK_ORDER)
        # 站外书（不在宇宙编年序）排最后，书名序稳定兜底
        assert exs.chron_key(_edge("夺", ["甲"], BOOK_B, "9:9"), BOOK_ORDER) < \
               exs.chron_key(_edge("夺", ["甲"], "站外书", "1:1"), BOOK_ORDER)


# ================================================================ 1. 编年排序（③）
class TestChronoSort:
    def test_chain_resorted_by_universe_order_and_chapter(self):
        """chain 按（宇宙书序, 回号）重排：输入乱序（乙书在前、同书回号倒序）→ 输出编年序。"""
        art = _art([_edge("赠", ["乙人"], BOOK_B, "1:2"),
                    _edge("夺", ["甲人"], BOOK_A, "9:1"),
                    _edge("夺", ["甲人"], BOOK_A, "3:5")],
                   books={BOOK_A: [3, 9], BOOK_B: [1]})
        _payload, rec = _build(art)
        assert [(e["book"], e["loc"]) for e in rec["chain"]] == [
            (BOOK_A, "3:5"), (BOOK_A, "9:1"), (BOOK_B, "1:2")]


# ================================================================ 2. 去重（④）
class TestDedupe:
    def test_full_duplicates_merged_with_n(self):
        """相同 verb+persons+book+loc 边合并 ×n；n 记在边字段，首现序保留。"""
        art = _art([_edge("夺", ["甲人"], BOOK_A, "1:1"),
                    _edge("夺", ["甲人"], BOOK_A, "1:1"),
                    _edge("赠", ["乙人"], BOOK_A, "2:2")],
                   books={BOOK_A: [1, 2]})
        _payload, rec = _build(art)
        assert len(rec["chain"]) == 2
        assert rec["chain"][0]["n"] == 2
        assert rec["chain"][1]["n"] == 1
        # meta 计数：合并掉 1 条
        assert rec is not None and _payload["meta"]["totals"]["chain_dedup_merged"] == 1

    def test_dedupe_chain_pure_function(self):
        chain = [_edge("夺", ["甲"], BOOK_A, "1:1"),
                 _edge("夺", ["甲"], BOOK_A, "1:1"),
                 _edge("夺", ["甲"], BOOK_A, "1:1"),
                 _edge("夺", ["乙"], BOOK_A, "1:1")]
        out = exs.dedupe_chain(chain)
        assert len(out) == 2
        assert out[0]["n"] == 3 and out[1]["n"] == 1
        # persons 是引用拷贝，不共享可变列表
        assert out[0]["persons"] == ["甲"] and out[0]["persons"] is not chain[0]["persons"]


# ================================================================ 3. 后续证伪（①）
class TestSuspectDestroy:
    def test_suspect_when_later_hold_edge(self):
        """合成 chain [毁@书甲回5, 赠@书乙回1] → 毁边 suspect=True（后续持有铁证）。"""
        art = _art([_edge("毁", ["甲人"], BOOK_A, "5:5"),
                    _edge("赠", ["乙人"], BOOK_B, "1:1")],
                   books={BOOK_A: [5], BOOK_B: [1]})
        _payload, rec = _build(art)
        hui = [e for e in rec["chain"] if e["verb"] == "毁"][0]
        assert hui.get("suspect") is True
        zeng = [e for e in rec["chain"] if e["verb"] == "赠"][0]
        assert "suspect" not in zeng           # 非毁边永不打 suspect

    def test_not_suspect_when_destroy_is_last(self):
        """编年内毁在最后出场之后（无后续 chain 边、无更大回号/更后书出场）→ 不 suspect。"""
        art = _art([_edge("夺", ["甲人"], BOOK_A, "1:1"),
                    _edge("毁", ["乙人"], BOOK_B, "3:3")],
                   books={BOOK_A: [1], BOOK_B: [3]})
        _payload, rec = _build(art)
        hui = [e for e in rec["chain"] if e["verb"] == "毁"][0]
        assert "suspect" not in hui

    def test_suspect_via_books_later_chapter_same_book(self):
        """无后续 chain 边，但同书更大回号有出场（books）→ suspect=True。"""
        art = _art([_edge("毁", ["甲人"], BOOK_A, "5:5")], books={BOOK_A: [1, 5, 9]})
        _payload, rec = _build(art)
        assert rec["chain"][0].get("suspect") is True

    def test_not_suspect_via_books_same_chapter_only(self):
        """books 只有同回（≤毁回）出场 → 无铁证，不 suspect（宁缺毋滥）。"""
        art = _art([_edge("毁", ["甲人"], BOOK_A, "5:5")], books={BOOK_A: [1, 5]})
        _payload, rec = _build(art)
        assert "suspect" not in rec["chain"][0]

    def test_destroy_and_forge_edges_are_not_life_evidence(self):
        """后续边只有 毁/铸 → 不构成存活铁证（毁句不自证、重铸存疑）；出场铁证另算。"""
        art = _art([_edge("毁", ["甲人"], BOOK_A, "5:5"),
                    _edge("毁", ["乙人"], BOOK_B, "1:1"),
                    _edge("铸", ["丙人"], BOOK_B, "2:2")],
                   books={BOOK_A: [5], BOOK_B: []})
        _payload, rec = _build(art)
        first = [e for e in rec["chain"] if e["book"] == BOOK_A][0]
        assert "suspect" not in first

    def test_scope_out_destroy_edge_dropped_no_crash(self):
        """毁边书在 scope 外被裁剪：幸存 chain 无 suspect 字段、不崩。"""
        art = _art([_edge("毁", ["站外人"], "站外书", "1:1"),
                    _edge("赠", ["甲人"], BOOK_A, "2:2")],
                   books={BOOK_A: [2]})
        _payload, rec = _build(art)
        assert [e["verb"] for e in rec["chain"]] == ["赠"]
        assert all("suspect" not in e for e in rec["chain"])


# ================================================================ 4. 主语证伪（②）——降权注记，不折叠
class TestSubjectLow:
    def test_subject_low_when_first_person_not_frequent_holder(self):
        """非 suspect 毁边 persons 首位 ∉ 持有人前 5 → subject_low=True（保留主线）。"""
        art = _art([_edge("毁", ["路人甲", "高频人"], BOOK_A, "9:1"),
                    _edge("毁", ["高频人"], BOOK_A, "9:5")],
                   books={BOOK_A: [9]},
                   holders=[{"name": "高频人", "n": 9}, {"name": "次高频", "n": 3}])
        _payload, rec = _build(art)
        e1, e2 = rec["chain"]
        assert e1.get("subject_low") is True and "suspect" not in e1
        assert "subject_low" not in e2           # 首位是高频持有人 → 不注记

    def test_subject_low_absent_on_suspect_edges(self):
        """suspect 毁边已折叠，不再叠加主语注记（互斥）。"""
        art = _art([_edge("毁", ["路人甲"], BOOK_A, "5:5"),
                    _edge("赠", ["乙人"], BOOK_B, "1:1")],
                   books={BOOK_A: [5], BOOK_B: [1]})
        _payload, rec = _build(art)
        hui = [e for e in rec["chain"] if e["verb"] == "毁"][0]
        assert hui.get("suspect") is True and "subject_low" not in hui


# ================================================================ 5. 方向化（⑤）
class TestDir:
    def test_forge_dir_from_makers(self):
        """铸边 persons ∩ makers → dir={"kind":"铸","who":[命中名]}（persons 序）。"""
        art = _art([_edge("铸", ["甘凤池", "路人乙", "冯瑛"], BOOK_A, "1:1"),
                    _edge("夺", ["冯瑛"], BOOK_A, "2:2")],
                   books={BOOK_A: [1, 2]}, makers=[{"name": "冯瑛", "n": 2}])
        _payload, rec = _build(art)
        zhu = [e for e in rec["chain"] if e["verb"] == "铸"][0]
        assert zhu["dir"] == {"kind": "铸", "who": ["冯瑛"]}
        duo = [e for e in rec["chain"] if e["verb"] == "夺"][0]
        assert "dir" not in duo                  # 夺无 object 数据 → 不方向化

    def test_forge_dir_absent_without_maker_overlap(self):
        """铸边 persons 与 makers 无交集 → 不加 dir（不伪造主语）。"""
        art = _art([_edge("铸", ["甘凤池", "路人乙"], BOOK_A, "1:1")],
                   books={BOOK_A: [1]}, makers=[{"name": "冯瑛", "n": 2}])
        _payload, rec = _build(art)
        assert "dir" not in rec["chain"][0]

    def test_borrow_dir_from_borrowers(self):
        """借边 persons ∩ borrowers → dir={"kind":"借","who":[…]}（borrowers 数据接入借边）。"""
        art = _art([_edge("借", ["唐晓澜", "冯瑛", "路人丙"], BOOK_A, "3:3")],
                   books={BOOK_A: [3]},
                   borrowers=[{"name": "冯瑛", "n": 1}, {"name": "唐晓澜", "n": 1}])
        _payload, rec = _build(art)
        assert rec["chain"][0]["dir"] == {"kind": "借", "who": ["唐晓澜", "冯瑛"]}


# ================================================================ 6. R6 全量口径不变 + meta 计数
class TestCalibers:
    def test_full_caliber_unchanged_no_rev17_fields(self):
        """scope=None（全量口径）：边无 n/suspect/subject_low/dir，不去重不排序，meta 无 rev17 计数。"""
        art = _art([_edge("赠", ["乙人"], BOOK_B, "1:2"),
                    _edge("夺", ["甲人"], BOOK_A, "1:1"),
                    _edge("夺", ["甲人"], BOOK_A, "1:1")],
                   books={BOOK_A: [1], BOOK_B: [1]})
        payload, rec = _build(art, scope=None)
        assert [(e["book"], e["loc"]) for e in rec["chain"]] == [
            (BOOK_B, "1:2"), (BOOK_A, "1:1"), (BOOK_A, "1:1")]     # 扫描序原样
        assert len(rec["chain"]) == 3                               # 重复保留
        for e in rec["chain"]:
            assert "n" not in e and "suspect" not in e \
                and "subject_low" not in e and "dir" not in e
        assert "chain_suspect" not in payload["meta"]["totals"]
        assert "chain_dedup_merged" not in payload["meta"]["totals"]
        assert payload["meta"]["rev"] == 16

    def test_scope_meta_rev17_and_totals(self):
        """scope 口径：meta.rev=17，totals 三计数（suspect/dedup_merged/dir）落盘。"""
        art = _art([_edge("毁", ["甲人"], BOOK_A, "5:5"),
                    _edge("夺", ["甲人"], BOOK_A, "1:1"),
                    _edge("夺", ["甲人"], BOOK_A, "1:1"),
                    _edge("赠", ["乙人"], BOOK_B, "1:1")],
                   books={BOOK_A: [1, 5], BOOK_B: [1]})
        payload, rec = _build(art)
        assert payload["meta"]["rev"] == 17
        totals = payload["meta"]["totals"]
        assert totals["chain_dedup_merged"] == 1
        assert totals["chain_suspect"] == 1
        # 毁边 suspect + 重复夺边合并
        hui = [e for e in rec["chain"] if e["verb"] == "毁"][0]
        assert hui.get("suspect") is True
        assert [e["n"] for e in rec["chain"] if e["verb"] == "夺"] == [2]

    def test_real_scope_books_chronology(self):
        """真实 profile（tianshan-demo）：scope["books"] 即宇宙编年序（universe lines 成员序）。"""
        scope = exs.esc.load_scope("tianshan-demo")
        assert scope["books"] == ["散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
                                  "七剑下天山", "冰魄寒光剑", "江湖三女侠"]
        order = {b: i for i, b in enumerate(scope["books"])}
        assert order["白发魔女传"] < order["塞外奇侠传"] < order["七剑下天山"] < order["江湖三女侠"]


# ================================================================ 7. 集成：build_weapons 真实形态抽查
class TestIntegration:
    def test_youlong_chain_scope(self):
        """游龙剑真实 chain（4 毁边 + 重复夺边）scope 口径：编年排序 + 毁边全 suspect + 重复 ×2。"""
        chain = [
            _edge("夺", ["凌未风", "楚昭南"], "七剑下天山", "5:7"),
            _edge("夺", ["凌未风", "郝继明", "刘郁芳"], "七剑下天山", "6:65"),
            _edge("夺", ["凌未风", "郝继明", "刘郁芳"], "七剑下天山", "6:65"),
            _edge("毁", ["刘郁芳", "郝继明", "凌未风"], "七剑下天山", "6:69"),
            _edge("毁", ["凌未风", "范铮", "楚昭南"], "七剑下天山", "6:125"),
            _edge("毁", ["凌未风", "范铮"], "七剑下天山", "6:139"),
            _edge("赠", ["凌未风", "吴三桂", "楚昭南"], "七剑下天山", "7:11"),
            _edge("毁", ["凌未风"], "七剑下天山", "7:123"),
            _edge("赠", ["易兰珠", "楚昭南", "晦明禅师"], "七剑下天山", "14:25"),
            _edge("夺", ["桂仲明", "凌未风"], "七剑下天山", "14:35"),
            _edge("夺", ["桂仲明", "凌未风"], "七剑下天山", "14:35"),
            _edge("夺", ["石天成", "卓一航", "辛龙子"], "七剑下天山", "23:37"),
        ]
        art = _art(chain, books={"七剑下天山": [5, 6, 7, 14, 23]}, canonical="游龙剑",
                   makers=[{"name": "岳鸣珂", "n": 2}],
                   holders=[{"name": "唐晓澜", "n": 79}, {"name": "楚昭南", "n": 45}])
        scope = {"profile": "demo", "books": ["白发魔女传", "塞外奇侠传",
                                              "七剑下天山", "江湖三女侠"]}
        _payload, rec = _build(art, scope=scope)
        locs = [e["loc"] for e in rec["chain"]]
        assert locs == sorted(locs, key=lambda l: exs.parse_loc_pair(l))   # 编年升序
        hui_locs = [e["loc"] for e in rec["chain"] if e["verb"] == "毁"]
        assert hui_locs == ["6:69", "6:125", "6:139", "7:123"]
        assert all(e.get("suspect") is True for e in rec["chain"] if e["verb"] == "毁")
        dup = [e for e in rec["chain"] if e["loc"] == "6:65"]
        assert len(dup) == 1 and dup[0]["n"] == 2
        assert [e["loc"] for e in rec["chain"] if e["verb"] != "毁"] == \
            ["5:7", "6:65", "7:11", "14:25", "14:35", "23:37"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
