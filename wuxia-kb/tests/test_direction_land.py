# -*- coding: utf-8 -*-
"""D17b · 名物流转方向化落地测试（用户裁定方案 A：草案 10 条全落 + 七剑 14:25 双行人工裁定，2026-11-12）。

被测对象：scripts/export_site_sects_weapons_arts.py D17b 新增
  DIRECTION_TSV                 kb/校订/名物流转方向.tsv（正式校定表，唯一真源）
  load_direction(path=None)     读表 → ([{weapon,verb,from,to,book,loc,note}], stats)；
                                只消费 校定 行（draft 计数不入站）；表头/必填/动词词表/loc 格式/
                                from=to 自环/同键重复行 → DirectionError（不静默改写人工校定稿）
  inject_direction(records, …)  校定行注入 chain 边 dir={"kind": verb, "who": [from, to]}（就地）；
                                键 weapon+book+loc（parse_loc_pair 归一比较，022:47 与 22:47 同键）；
                                无匹配边 / 无记录 / scope 外 / 边已有 dir（铸/借 rev17 口径不动）→
                                跳过并计数（不伪造、不覆盖）；一键只注一边
  build_weapons(src, …, direction_sup=None) 接线：scope 口径 rev17 之后注入（铸/借 dir 在先不覆盖）；
                                全量口径（scope=None）不消费（方案 R6，与 rev17 同门）

口径固化（测试即规范）：
  - dir.kind 来自 TSV verb（人工校定方向），可与 chain 边 verb 不同口径（14:25 边 verb=赠、
    dir.kind=传：chain 边 verb 是神兵表扫描口径不动，dir 是校定方向层）。
  - 14:25 双行各归其器：游龙剑=长剑传楚昭南、断玉剑=短剑传杨云骢（原文双句核实，两键均有边可注）。
  - 上站数据零语料：dir 只含 kind + who 两人名，TSV note（原创注记）不进 weapons.json。
"""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_sects_weapons_arts as exs  # noqa: E402

BOOK_A, BOOK_B = "编年书甲", "编年书乙"
SCOPE_AB = {"profile": "demo", "books": [BOOK_A, BOOK_B]}


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
    return {
        "artifacts": {"artifacts": arts, "meta": {"rev": 16}, "alias_candidates": []},
        "old_weapons": {"weapons": []},
        "weapon_alias": {}, "weapon_canon": set(),
        "conc": {}, "conc_books": [BOOK_A, BOOK_B],
        "wordlist": [],
    }


def _row(weapon, verb, frm, to, book=BOOK_A, loc="1:1", status="校定"):
    return {"weapon": weapon, "verb": verb, "from": frm, "to": to,
            "book": book, "loc": loc, "note": "", "status": status}


def _build(art, scope=SCOPE_AB, direction_sup="default"):
    """direction_sup="default"（真实 TSV 口径）/ list（显式注入）/ None 同 list 语义由调用方定。"""
    kw = {}
    if direction_sup != "default":
        kw["direction_sup"] = direction_sup
    payload, _st = exs.build_weapons(_src([art]), scope=scope, **kw)
    return payload, (payload["weapons"][0] if payload["weapons"] else None)


# ================================================================ 1. load_direction 读表
class TestLoadDirection:
    def test_real_tsv_14_rows_all_calibrated(self):
        """真实正式 TSV：14 校定行（D17b 12 + D17c 2：断玉剑 29:71 夺、碾玉人像 24:5 赠，用户批量确认
        转正）、零 draft、动词全在四档词表；F6 迁移后 24:15 行改挂游龙剑。"""
        rows, stats = exs.load_direction()
        assert stats["consumed"] == 14 and stats["draft"] == 0 and stats["rows"] == 14
        # 消费行只可能是校定行（draft 在 loader 内拦截），出表行无 status 键（schema 同 weapon_sup 通道）
        assert all(set(r.keys()) == {"weapon", "verb", "from", "to", "book", "loc", "note"} for r in rows)
        assert all(r["verb"] in exs.DIRECTION_VERBS for r in rows)
        keys = {(r["weapon"], r["book"], r["loc"]) for r in rows}
        assert len(keys) == 14                      # 一键一行
        assert ("游龙剑", "七剑下天山", "14:25") in keys
        assert ("断玉剑", "七剑下天山", "14:25") in keys
        # F6：24:15 行随链边迁移改挂游龙剑（方向冯瑛→夺→车辟邪不变）
        f6 = [r for r in rows if r["book"] == "江湖三女侠" and r["loc"] == "24:15"]
        assert len(f6) == 1 and f6[0]["weapon"] == "游龙剑"
        assert (f6[0]["from"], f6[0]["to"], f6[0]["verb"]) == ("冯瑛", "车辟邪", "夺")
        # D17c 两行
        by_key = {(r["weapon"], r["book"], r["loc"]): r for r in rows}
        d = by_key[("断玉剑", "七剑下天山", "29:71")]
        assert (d["verb"], d["from"], d["to"]) == ("夺", "易兰珠", "楚昭南")
        n = by_key[("碾玉人像", "白发魔女传", "24:5")]
        assert (n["verb"], n["from"], n["to"]) == ("赠", "客氏", "客娉婷")

    def test_draft_rows_not_consumed_but_counted(self, tmp_path):
        """draft 行不消费（计数入 stats），校定行照常出表。"""
        p = tmp_path / "方向.tsv"
        p.write_text(
            "weapon\tverb\tfrom\tto\tbook\tloc\tnote\tstatus\n"
            "甲剑\t夺\t张三\t李四\t编年书甲\t1:1\t注\t校定\n"
            "乙剑\t赠\t王五\t赵六\t编年书甲\t2:2\t注\tdraft\n",
            encoding="utf-8")
        rows, stats = exs.load_direction(p)
        assert stats["rows"] == 2 and stats["consumed"] == 1 and stats["draft"] == 1
        assert len(rows) == 1 and rows[0]["weapon"] == "甲剑"

    def test_missing_file_returns_empty(self, tmp_path):
        rows, stats = exs.load_direction(tmp_path / "不存在.tsv")
        assert rows == [] and stats == {"rows": 0, "consumed": 0, "draft": 0}

    def test_bad_header_raises(self, tmp_path):
        p = tmp_path / "坏.tsv"
        p.write_text("weapon\tverb\tfrom\tto\tbook\tloc\tstatus\n", encoding="utf-8")
        with pytest.raises(exs.DirectionError):
            exs.load_direction(p)

    @pytest.mark.parametrize("line,frag", [
        ("甲剑\t夺\t\t李四\t编年书甲\t1:1\t注\t校定", "空 from"),
        ("甲剑\t砍\t张三\t李四\t编年书甲\t1:1\t注\t校定", "动词词表外"),
        ("甲剑\t夺\t张三\t李四\t编年书甲\t1.1\t注\t校定", "loc 格式"),
        ("甲剑\t夺\t张三\t张三\t编年书甲\t1:1\t注\t校定", "自环"),
    ])
    def test_invalid_rows_raise(self, tmp_path, line, frag):
        p = tmp_path / "坏.tsv"
        p.write_text("weapon\tverb\tfrom\tto\tbook\tloc\tnote\tstatus\n" + line + "\n",
                     encoding="utf-8")
        with pytest.raises(exs.DirectionError):
            exs.load_direction(p)

    def test_duplicate_key_raises(self, tmp_path):
        """同 weapon+book+loc 重复校定行 → 报错（一键一边一 dir，不静默二注）。"""
        p = tmp_path / "重.tsv"
        body = "weapon\tverb\tfrom\tto\tbook\tloc\tnote\tstatus\n"
        body += "甲剑\t夺\t张三\t李四\t编年书甲\t1:1\t注\t校定\n"
        body += "甲剑\t赠\t张三\t王五\t编年书甲\t1:1\t注\t校定\n"
        p.write_text(body, encoding="utf-8")
        with pytest.raises(exs.DirectionError):
            exs.load_direction(p)


# ================================================================ 2. inject_direction 注入
class TestInjectDirection:
    def test_pair_dir_injected_on_matching_edge(self):
        """键 weapon+book+loc 命中 → dir={"kind": verb, "who": [from, to]}（who 恒两人序）。"""
        art = _art([_edge("夺", ["凌未风", "楚昭南"], BOOK_A, "5:7")],
                   books={BOOK_A: [5]}, canonical="游龙剑")
        _payload, rec = _build(art, direction_sup=[_row("游龙剑", "夺", "凌未风", "楚昭南", BOOK_A, "5:7")])
        e = rec["chain"][0]
        assert e["dir"] == {"kind": "夺", "who": ["凌未风", "楚昭南"]}
        # 铸/借 rev17 口径不变：无 makers/borrowers 时无 dir；夺边 dir 由本通道注入
        assert e["verb"] == "夺" and e["persons"] == ["凌未风", "楚昭南"]

    def test_loc_zero_pad_normalized(self):
        """loc 归一比较：TSV 22:11 命中 chain 022:11（parse_loc_pair 口径）。"""
        art = _art([_edge("夺", ["甲人", "乙人"], BOOK_A, "022:11")],
                   books={BOOK_A: [22]}, canonical="测试名物")
        _payload, rec = _build(art, direction_sup=[_row("测试名物", "夺", "甲人", "乙人", BOOK_A, "22:11")])
        assert rec["chain"][0]["dir"]["who"] == ["甲人", "乙人"]

    def test_dir_kind_from_tsv_not_edge_verb(self):
        """dir.kind 来自 TSV verb（校定方向层）：chain 边 verb=赠、dir.kind=传 并存（14:25 口径）。"""
        art = _art([_edge("赠", ["易兰珠", "楚昭南", "晦明禅师"], BOOK_A, "14:25")],
                   books={BOOK_A: [14]}, canonical="游龙剑")
        _payload, rec = _build(art, direction_sup=[_row("游龙剑", "传", "晦明禅师", "楚昭南", BOOK_A, "14:25")])
        e = rec["chain"][0]
        assert e["verb"] == "赠" and e["dir"] == {"kind": "传", "who": ["晦明禅师", "楚昭南"]}
        assert e["persons"] == ["易兰珠", "楚昭南", "晦明禅师"]   # chain 边本体不动

    def test_no_matching_edge_skipped_and_counted(self):
        """loc 无对应 chain 边 → 跳过 + no_edge 记账（不伪造边，field_gaps 报告通道）。"""
        art = _art([_edge("夺", ["甲人", "乙人"], BOOK_A, "1:1")],
                   books={BOOK_A: [1]}, canonical="测试名物")
        payload, rec = _build(art, direction_sup=[_row("测试名物", "夺", "甲人", "乙人", BOOK_A, "9:9")])
        assert all("dir" not in e for e in rec["chain"])
        gaps = " ".join(payload["meta"]["field_gaps"])
        assert "9:9" in gaps

    def test_weapon_without_record_reported(self):
        """TSV weapon 无 weapons 记录 → no_weapon 记账，不崩、不造空壳。"""
        art = _art([_edge("夺", ["甲人", "乙人"], BOOK_A, "1:1")],
                   books={BOOK_A: [1]}, canonical="测试名物")
        payload, _rec = _build(art, direction_sup=[_row("站外名物", "夺", "甲人", "乙人", BOOK_A, "1:1")])
        gaps = " ".join(payload["meta"]["field_gaps"])
        assert "站外名物" in gaps

    def test_existing_dir_not_overwritten(self):
        """边已有 dir（rev17 铸边口径）→ 不覆盖（铸/借保持现状不动），计数 has_dir。"""
        art = _art([_edge("铸", ["冯瑛", "路人乙"], BOOK_A, "1:1")],
                   books={BOOK_A: [1]}, makers=[{"name": "冯瑛", "n": 2}], canonical="断玉剑")
        payload, rec = _build(art, direction_sup=[_row("断玉剑", "夺", "路人乙", "冯瑛", BOOK_A, "1:1")])
        assert rec["chain"][0]["dir"] == {"kind": "铸", "who": ["冯瑛"]}   # rev17 原样
        gaps = " ".join(payload["meta"]["field_gaps"])
        assert "已有 dir" in gaps

    def test_out_of_scope_row_not_consumed(self):
        """scope 口径：书外行不消费（out_scope 计数），不注入。"""
        art = _art([_edge("夺", ["甲人", "乙人"], BOOK_A, "1:1")],
                   books={BOOK_A: [1]}, canonical="测试名物")
        payload, rec = _build(art, direction_sup=[_row("测试名物", "夺", "甲人", "乙人", "站外书", "2:2")])
        assert all("dir" not in e for e in rec["chain"])
        assert payload["meta"]["totals"].get("chain_dir_person", 0) == 0

    def test_meta_totals_and_notes(self):
        """meta.totals.chain_dir_person=注入数；field_gaps 有 TSV 通道口径声明。"""
        art = _art([_edge("夺", ["甲人", "乙人"], BOOK_A, "1:1"),
                    _edge("赠", ["丙人", "丁人"], BOOK_A, "2:2")],
                   books={BOOK_A: [1, 2]}, canonical="测试名物")
        payload, rec = _build(art, direction_sup=[
            _row("测试名物", "夺", "甲人", "乙人", BOOK_A, "1:1"),
            _row("测试名物", "赠", "丙人", "丁人", BOOK_A, "2:2")])
        assert payload["meta"]["totals"]["chain_dir_person"] == 2
        assert all("dir" in e for e in rec["chain"])
        gaps = " ".join(payload["meta"]["field_gaps"])
        assert "名物流转方向.tsv" in gaps and "2" in gaps

    def test_uppercase_columns_tolerated_via_strip(self):
        """行首尾空白容忍（人工编辑常态）：单元格 strip 后照常消费。"""
        art = _art([_edge("夺", ["甲人", "乙人"], BOOK_A, "1:1")],
                   books={BOOK_A: [1]}, canonical="测试名物")
        p = exs.KB / "校订" / "名物流转方向.tsv"
        rows, _stats = exs.load_direction(p)
        assert rows[0]["weapon"] == "游龙剑"          # 真实表无首尾空白回归守卫


# ================================================================ 3. 真实数据集成（14:25 双行 + 全链）
class TestRealDataIntegration:
    def test_real_tsv_keys_all_match_live_chain(self):
        """真实 TSV 12 键逐条命中 live weapons.json chain 边（14:25 双行=游龙剑+断玉剑均有边；
        loc 复核口径固化进 CI——漂移即红）。"""
        import json
        data = json.loads((SCRIPTS_DIR.parent.parent / "site" / "data" / "weapons.json")
                          .read_text(encoding="utf-8"))
        by = {w["canonical"]: w for w in data["weapons"]}
        rows, _stats = exs.load_direction()
        miss = []
        for r in rows:
            rec = by.get(r["weapon"])
            if rec is None:
                miss.append(r["weapon"])
                continue
            key = exs.parse_loc_pair(r["loc"])
            if not any(e.get("book") == r["book"] and exs.parse_loc_pair(e.get("loc")) == key
                       for e in rec["chain"]):
                miss.append(f"{r['weapon']}·{r['book']}·{r['loc']}")
        assert miss == []

    def test_real_build_youlong_and_duanyu_1425(self):
        """真实 TSV × 合成游龙剑/断玉剑链（真实 loc 键）：14:25 双边各注方向、5:7 注夺向。"""
        chain_y = [_edge("夺", ["凌未风", "楚昭南"], "七剑下天山", "5:7"),
                   _edge("赠", ["易兰珠", "楚昭南", "晦明禅师"], "七剑下天山", "14:25")]
        chain_d = [_edge("夺", ["杨云骢", "天蒙禅师", "天蒙"], "塞外奇侠传", "25:15"),
                   _edge("赠", ["易兰珠", "楚昭南", "晦明禅师"], "七剑下天山", "14:25")]
        src = _src([_art(chain_y, {"七剑下天山": [5, 14]}, canonical="游龙剑"),
                    _art(chain_d, {"塞外奇侠传": [25], "七剑下天山": [14]}, canonical="断玉剑")])
        payload, _st = exs.build_weapons(src, scope={"profile": "demo", "books": [
            "白发魔女传", "塞外奇侠传", "七剑下天山", "江湖三女侠"]})
        by = {w["canonical"]: w for w in payload["weapons"]}
        y7 = [e for e in by["游龙剑"]["chain"] if e["loc"] == "5:7"][0]
        y14 = [e for e in by["游龙剑"]["chain"] if e["loc"] == "14:25"][0]
        d14 = [e for e in by["断玉剑"]["chain"] if e["loc"] == "14:25"][0]
        d15 = [e for e in by["断玉剑"]["chain"] if e["loc"] == "25:15"][0]
        assert y7["dir"] == {"kind": "夺", "who": ["凌未风", "楚昭南"]}
        assert y14["dir"] == {"kind": "传", "who": ["晦明禅师", "楚昭南"]}   # 长剑=游龙剑
        assert d14["dir"] == {"kind": "传", "who": ["晦明禅师", "杨云骢"]}   # 短剑=断玉剑
        assert d15["dir"] == {"kind": "夺", "who": ["杨云骢", "天蒙禅师"]}
        assert payload["meta"]["totals"]["chain_dir_person"] >= 4

    def test_d17c_duanyu_2971_and_nianyu_245(self):
        """D17c 两行注入（用户批量确认转正）：断玉剑 29:71 夺边（边内第三人 刘郁芳 保持 rest）、
        碾玉人像 24:5 赠边（rest=魏忠贤）。"""
        chain_d = [_edge("毁", ["易兰珠", "楚昭南", "晦明禅师"], "七剑下天山", "29:49"),
                   _edge("夺", ["刘郁芳", "楚昭南", "易兰珠"], "七剑下天山", "29:71")]
        chain_n = [_edge("赠", ["魏忠贤", "客氏", "客娉婷"], "白发魔女传", "24:5")]
        src = _src([_art(chain_d, {"七剑下天山": [29]}, canonical="断玉剑"),
                    _art(chain_n, {"白发魔女传": [24]}, canonical="碾玉人像")])
        payload, _st = exs.build_weapons(src, scope={"profile": "demo", "books": [
            "白发魔女传", "塞外奇侠传", "七剑下天山", "江湖三女侠"]})
        by = {w["canonical"]: w for w in payload["weapons"]}
        d71 = [e for e in by["断玉剑"]["chain"] if e["loc"] == "29:71"][0]
        n5 = [e for e in by["碾玉人像"]["chain"] if e["loc"] == "24:5"][0]
        assert d71["dir"] == {"kind": "夺", "who": ["易兰珠", "楚昭南"]}
        assert d71["persons"] == ["刘郁芳", "楚昭南", "易兰珠"]   # 边本体不动
        assert n5["dir"] == {"kind": "赠", "who": ["客氏", "客娉婷"]}
        assert n5["persons"] == ["魏忠贤", "客氏", "客娉婷"]
        assert payload["meta"]["totals"]["chain_dir_person"] >= 2

    def test_full_caliber_no_direction_injection(self):
        """全量口径（scope=None）不消费方向 TSV：边无 dir（方案 R6，与 rev17 同门）。"""
        chain = [_edge("夺", ["凌未风", "楚昭南"], "七剑下天山", "5:7")]
        payload, rec = _build(_art(chain, {"七剑下天山": [5]}, canonical="游龙剑"),
                              scope=None, direction_sup=[])
        assert "dir" not in rec["chain"][0]
        assert "chain_dir_person" not in payload["meta"]["totals"]

    def test_notes_never_enter_payload(self):
        """上站数据零语料：dir 只含 kind/who 两键，TSV note 不入 weapons.json（任何边/记录）。"""
        art = _art([_edge("夺", ["甲人", "乙人"], BOOK_A, "1:1")],
                   books={BOOK_A: [1]}, canonical="测试名物")
        row = _row("测试名物", "夺", "甲人", "乙人", BOOK_A, "1:1")
        row["note"] = "考订依据注记留档（不入站）"
        payload, rec = _build(art, direction_sup=[row])
        blob = repr(payload)
        assert "考订依据注记留档" not in blob
        assert set(rec["chain"][0]["dir"].keys()) == {"kind", "who"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
