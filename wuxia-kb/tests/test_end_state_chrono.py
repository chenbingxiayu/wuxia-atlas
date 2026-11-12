# -*- coding: utf-8 -*-
"""D7 · 名物 end_state 按宇宙编年重算测试（天山演示版任务 D7，2026-11-11）。

背景（D5 发现的存量口径问题）：weapons.json end_state（最终归宿="末回持有记载"）由
scripts/build_artifacts.py 生成——`max(occs, key=(回,行))` **跨书只比回号**、并列取扫描序
首个，即 end_state 取「语料扫描顺序的最后一个提及」，不是「宇宙编年最晚的提及」
（如 虎头钩 end_state 末见=白发魔女传 23 回，而 rev17 新编年下其主线毁边=江湖三女侠 9:13
晚于该末见——end_state 与主线编年互相矛盾）。

被测对象：scripts/export_site_sects_weapons_arts.py 新增（EX-6 weapons 部分）
  recalc_end_state(rec, book_order)      scope 口径 end_state 编年重算（in-place，返回 changed/destroyed）
  _chrono_last_mention(rec, book_order)  编年最末提及 (书序, 回, 书)：books 回目集 + 主线边回号取 max
  _last_mainline_destroy(rec, …)         主线（非 suspect）编年最末「毁」边
  build_weapons 接线                     scope 口径 rev17 后调用；meta.totals 计数；全量口径不调用（R6）

口径固化（测试即规范）：
  - 主线 = 非 suspect 边（suspect 毁边已折叠为「疑似误伤」，不进主线——与前端同口径）；
  - 主线编年最末「毁」边的编年位置 = 全件编年最末提及（书序, 回）→ end_state=毁于：<边 persons>（书 · N 回）；
  - 否则 end_state=末见持有：<holders 前 2>（<编年最末提及的书>·<最大回> 回）——文案式样与旧生成
    （build_artifacts 「末见持有：A、B（书 · N 回）」）一致，只改计算口径；
  - 无提及或无持有人 → end_state=None（旧口径：不伪造）；
  - 全量口径（scope=None）：end_state 原样透传神兵表旧值（R6，含编年错误的旧值也不改）。
"""
import re
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_sects_weapons_arts as exs  # noqa: E402

# 合成宇宙编年：书甲在前、书乙在后（同 test_weapons_r17 口径）
BOOK_A, BOOK_B = "编年书甲", "编年书乙"
SCOPE_AB = {"profile": "demo", "books": [BOOK_A, BOOK_B]}
BOOK_ORDER = {BOOK_A: 0, BOOK_B: 1}
# 真实 scope（tianshan-demo）：白发魔女传(2) 早于 江湖三女侠(6)——虎头钩式案例用
SCOPE_TS = exs.esc.load_scope("tianshan-demo")
TS_ORDER = {b: i for i, b in enumerate(SCOPE_TS["books"])}
NOTE_LOC_RE = re.compile(r"（([^·（）]+)·(\d+) 回）$")


# ================================================================ 合成 fixture
def _edge(verb, persons, book, loc, conf="strong"):
    return {"verb": verb, "persons": list(persons), "book": book, "loc": loc, "conf": conf}


def _art(chain, books, holders=None, canonical="测试名物", end_state=None):
    return {
        "canonical": canonical, "kind": "剑", "level": "名物", "grade": "名物",
        "grade_basis": "明文", "conf": "ok", "status": "auto",
        "chain": list(chain),
        "holders": holders or [], "borrowers": [], "makers": [],
        "end_state": end_state,
        "books": dict(books),
        "count": 10, "ev_total": 2,
        "evidence": [{"book": BOOK_A, "loc": "1:2", "kind": "共现"}],
    }


def _src(arts):
    """最小合成 src（同 test_weapons_r17 口径；conc 无命中 → books 走神兵表原值）。"""
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


def _note_of(rec):
    es = rec.get("end_state")
    return es.get("note") if isinstance(es, dict) else es


# ================================================================ 1. 规则主形态
class TestRecalcRule:
    def test_destroy_at_late_book_end_state_hui(self):
        """合成（毁@晚期书）：主线编年最末提及=毁边 → end_state=毁于：<persons>（书 · N 回）。"""
        art = _art([_edge("夺", ["甲人"], BOOK_A, "1:1"),
                    _edge("毁", ["毁者甲", "毁者乙"], BOOK_B, "5:13")],
                   books={BOOK_A: [1], BOOK_B: [5]},
                   holders=[{"name": "甲人", "n": 3}])
        _payload, rec = _build(art)
        note = _note_of(rec)
        assert note == "毁于：毁者甲、毁者乙（编年书乙·5 回）"
        m = NOTE_LOC_RE.search(note)
        assert m and m.group(1) == BOOK_B and m.group(2) == "5"    # 用户向式样不变

    def test_hold_at_late_book_end_state_mojian(self):
        """合成（持有@晚期书）：毁@早期书（suspect 折叠）、持有@晚期书 → end_state=末见持有（晚期书·回）。"""
        art = _art([_edge("毁", ["毁者甲"], BOOK_A, "5:5"),
                    _edge("赠", ["乙人", "丙人"], BOOK_B, "1:2")],
                   books={BOOK_A: [5], BOOK_B: [1]},
                   holders=[{"name": "乙人", "n": 6}, {"name": "丙人", "n": 2}])
        payload, rec = _build(art)
        hui = [e for e in rec["chain"] if e["verb"] == "毁"][0]
        assert hui.get("suspect") is True                       # 毁边折叠出主线
        note = _note_of(rec)
        assert note is not None and note.startswith("末见持有")
        assert note == "末见持有：乙人、丙人（编年书乙·1 回）"
        assert payload["meta"]["totals"]["end_state_destroyed"] == 0

    def test_last_destroy_edge_when_multiple_mainline(self):
        """多条非 suspect 毁边（同书回 5、回 9）→ 取编年最末一条（回 9）做归宿。"""
        art = _art([_edge("毁", ["毁者一"], BOOK_A, "5:1"),
                    _edge("毁", ["毁者二"], BOOK_A, "9:1")],
                   books={BOOK_A: [5, 9]}, holders=[{"name": "甲人", "n": 1}])
        _payload, rec = _build(art)
        assert _note_of(rec) == "毁于：毁者二（编年书甲·9 回）"

    def test_no_holders_end_state_none(self):
        """无持有人 → end_state=None（旧口径不伪造：`if occs and holders` 同款闸门）。"""
        art = _art([_edge("夺", ["甲人"], BOOK_A, "1:1")], books={BOOK_A: [1]}, holders=[])
        _payload, rec = _build(art)
        assert rec["end_state"] is None


# ================================================================ 2. 虎头钩式案例（真 scope 序）
class TestHutougouCase:
    def test_legacy_end_state_earlier_than_destroy_edge(self):
        """虎头钩式：旧 end_state（白发魔女传·23 回）早于主线毁边（江湖三女侠 9:13）
        → 新 end_state=毁于…（江湖三女侠·9 回）——end_state 与主线编年不再矛盾。"""
        art = _art([_edge("交战侧证", ["铁飞龙"], "白发魔女传", "023:87", conf="ok"),
                    _edge("毁", ["了因和尚", "易兰珠", "白泰官"], "江湖三女侠", "9:13")],
                   books={"白发魔女传": [23], "江湖三女侠": [9]},
                   holders=[{"name": "哈玛雅", "n": 6}, {"name": "押不庐", "n": 5}],
                   canonical="虎头钩",
                   end_state={"note": "末见持有：哈玛雅、押不庐（白发魔女传·23 回）"})
        assert TS_ORDER["白发魔女传"] < TS_ORDER["江湖三女侠"]      # 前提：江湖三女侠编年更晚
        payload, rec = _build(art, scope=SCOPE_TS)
        note = _note_of(rec)
        assert note == "毁于：了因和尚、易兰珠、白泰官（江湖三女侠·9 回）"
        # meta：changed=1（旧值被替换）、destroyed=1
        assert payload["meta"]["totals"]["end_state_recalc"] == 1
        assert payload["meta"]["totals"]["end_state_destroyed"] == 1


# ================================================================ 3. suspect 折叠与 books 口径
class TestMentionCaliber:
    def test_suspect_destroy_via_books_later_chapter(self):
        """毁@书甲回 5、books 同书回 9 仍有出场 → 毁边 suspect 折叠 → end_state=末见持有（回 9）。"""
        art = _art([_edge("毁", ["毁者甲"], BOOK_A, "5:5")],
                   books={BOOK_A: [5, 9]}, holders=[{"name": "甲人", "n": 2}])
        payload, rec = _build(art)
        assert rec["chain"][0].get("suspect") is True
        assert _note_of(rec) == "末见持有：甲人（编年书甲·9 回）"
        assert payload["meta"]["totals"]["end_state_destroyed"] == 0

    def test_cross_book_chapter_comparison_bug_fixed(self):
        """跨书回号比较 bug 回归：books={书甲:[29], 书乙:[2]}、无 chain——旧口径
        max(回,行) 跨书比较取 书甲·29（扫描序并列兜底），新口径取编年最末 书乙·2。"""
        art = _art([], books={BOOK_A: [29], BOOK_B: [2]},
                   holders=[{"name": "甲人", "n": 3}, {"name": "乙人", "n": 2}],
                   end_state={"note": "末见持有：甲人、乙人（编年书甲·29 回）"})
        _payload, rec = _build(art)
        assert _note_of(rec) == "末见持有：甲人、乙人（编年书乙·2 回）"

    def test_destroy_edge_chapter_counts_as_mention(self):
        """毁边回号也是提及：books 缺该回（旧 books 未含）时，主线边回号兜底计入最末提及。"""
        art = _art([_edge("毁", ["毁者甲"], BOOK_B, "7:9")],
                   books={BOOK_B: [3]}, holders=[{"name": "甲人", "n": 1}])
        _payload, rec = _build(art)
        assert _note_of(rec) == "毁于：毁者甲（编年书乙·7 回）"


# ================================================================ 4. 一致性不变量（合成 sweep）
class TestConsistencyInvariant:
    def test_end_state_not_earlier_than_mainline_destroy(self):
        """不变量（全量扫口径）：每件 end_state 提及的（书序, 回）不早于任何主线毁边（书序, 回）。
        覆盖 毁于 / 末见持有 / suspect 折叠 / 无毁边 四种形态。"""
        cases = [
            _art([_edge("夺", ["甲人"], BOOK_A, "1:1"),
                  _edge("毁", ["毁者甲"], BOOK_B, "5:13")],
                 books={BOOK_A: [1], BOOK_B: [5]}, holders=[{"name": "甲人", "n": 3}],
                 canonical="件一毁终局"),
            _art([_edge("毁", ["毁者甲"], BOOK_A, "5:5"),
                  _edge("赠", ["乙人"], BOOK_B, "1:2")],
                 books={BOOK_A: [5], BOOK_B: [1]}, holders=[{"name": "乙人", "n": 2}],
                 canonical="件二毁误伤"),
            _art([_edge("毁", ["毁者甲"], BOOK_A, "5:5")],
                 books={BOOK_A: [5, 9]}, holders=[{"name": "甲人", "n": 2}],
                 canonical="件三毁后出场"),
            _art([_edge("夺", ["甲人"], BOOK_A, "2:2")],
                 books={BOOK_A: [2]}, holders=[{"name": "甲人", "n": 1}],
                 canonical="件四无毁边"),
        ]
        payload, _st = exs.build_weapons(_src(cases), scope=SCOPE_AB)
        by = {r["canonical"]: r for r in payload["weapons"]}
        assert set(by) == {"件一毁终局", "件二毁误伤", "件三毁后出场", "件四无毁边"}
        n_checked = 0
        for canon, rec in by.items():
            note = _note_of(rec) or ""
            m = NOTE_LOC_RE.search(note)
            if not m:
                assert rec["end_state"] is None
                continue
            end_key = (BOOK_ORDER[m.group(1)], int(m.group(2)))
            for e in rec["chain"]:
                if e["verb"] == "毁" and not e.get("suspect"):
                    n_checked += 1
                    ch, _ln = exs.parse_loc_pair(e["loc"])
                    assert end_key >= (BOOK_ORDER[e["book"]], ch), \
                        f"{canon}: end_state {end_key} 早于主线毁边 {e['book']}·{ch}"
        assert n_checked == 1    # 件二/件三的毁边均已 suspect 折叠，主线毁边只剩件一 1 条

    def test_real_scope_end_state_consistency_sweep(self):
        """真实数据 sweep（read-only）：site/data/weapons.json（tianshan-demo scope）全部有毁边名物，
        end_state 提及的（scope 书序, 回）不早于主线毁边——脚本断言（D7 §4 一致性全量扫）。"""
        data_path = SCRIPTS_DIR.parents[1] / "site" / "data" / "weapons.json"
        if not data_path.exists():
            pytest.skip("site/data/weapons.json 不存在（跳过真实数据 sweep）")
        import json
        data = json.loads(data_path.read_text(encoding="utf-8"))
        if (data.get("meta") or {}).get("scope") != "tianshan-demo":
            pytest.skip("site/data/weapons.json 非 tianshan-demo scope（跳过）")
        n_main_hui, n_end = 0, 0
        for w in data["weapons"]:
            note = (w.get("end_state") or {}).get("note") or ""
            m = NOTE_LOC_RE.search(note)
            for e in w.get("chain") or []:
                if e["verb"] == "毁" and not e.get("suspect") and e.get("book") in TS_ORDER:
                    n_main_hui += 1
                    assert m, f'{w["canonical"]}：有主线毁边而 end_state 缺（书·N 回）定位'
                    n_end += 1
                    ch, _ln = exs.parse_loc_pair(e["loc"])
                    assert (TS_ORDER[m.group(1)], int(m.group(2))) >= (TS_ORDER[e["book"]], ch), \
                        f'{w["canonical"]}: end_state={note} 早于主线毁边 {e["book"]}·{e["loc"]}'
        assert n_main_hui > 0     # 数据面上确有主线毁边（D7 前为 19 条）
        assert n_end == n_main_hui


# ================================================================ 5. R6 全量口径不变 + 纯函数/meta
class TestR6AndMeta:
    def test_full_caliber_end_state_passthrough(self):
        """R6：scope=None（全量口径）end_state 原样透传神兵表旧值——编年错误的旧值也不改。"""
        art = _art([_edge("交战侧证", ["铁飞龙"], "白发魔女传", "023:87", conf="ok"),
                    _edge("毁", ["了因和尚"], "江湖三女侠", "9:13")],
                   books={"白发魔女传": [23], "江湖三女侠": [9]},
                   holders=[{"name": "哈玛雅", "n": 6}], canonical="虎头钩",
                   end_state={"note": "末见持有：哈玛雅、押不庐（白发魔女传·23 回）"})
        payload, rec = _build(art, scope=None)
        assert rec["end_state"] == {"note": "末见持有：哈玛雅、押不庐（白发魔女传·23 回）"}
        assert "end_state_recalc" not in payload["meta"]["totals"]
        assert "end_state_destroyed" not in payload["meta"]["totals"]

    def test_recalc_end_state_pure_function(self):
        """纯函数直测：recalc_end_state 就地替换 + 返回 changed/destroyed 标志。"""
        rec = {"chain": [_edge("毁", ["毁者甲"], BOOK_B, "5:13")],
               "books": {BOOK_A: [1], BOOK_B: [5]},
               "holders": [{"name": "甲人", "n": 2}],
               "end_state": {"note": "末见持有：甲人（编年书甲·1 回）"}}
        st = exs.recalc_end_state(rec, BOOK_ORDER)
        assert st == {"changed": True, "destroyed": True}
        assert rec["end_state"] == {"note": "毁于：毁者甲（编年书乙·5 回）"}
        # 幂等：重算一次 changed=False
        st2 = exs.recalc_end_state(rec, BOOK_ORDER)
        assert st2 == {"changed": False, "destroyed": True}

    def test_chrono_last_mention_pure_function(self):
        """纯函数直测：_chrono_last_mention = books 回目集 ∪ 主线边回号 的编年 max（suspect 边不计）。"""
        rec = {"books": {BOOK_A: [3, 29], BOOK_B: [2]},
               "chain": [_edge("毁", ["x"], BOOK_A, "5:1"),        # suspect → 不计
                         _edge("夺", ["y"], BOOK_B, "4:2")],
               }
        rec["chain"][0]["suspect"] = True
        assert exs._chrono_last_mention(rec, BOOK_ORDER) == (1, 4, BOOK_B)

    def test_meta_field_gaps_declares_d7_rule(self):
        """scope 口径 meta.field_gaps 声明 D7 口径（end_state 编年重算规则入档）。"""
        art = _art([_edge("毁", ["毁者甲"], BOOK_B, "5:13")],
                   books={BOOK_A: [1], BOOK_B: [5]}, holders=[{"name": "甲人", "n": 2}])
        payload, _rec = _build(art)
        gaps = " ".join(payload["meta"]["field_gaps"])
        assert "end_state" in gaps and "编年" in gaps


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
