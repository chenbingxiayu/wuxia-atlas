# -*- coding: utf-8 -*-
"""D10 · 武功传承树人工补链测试（武功页重构设计 §6.2 数据源三层第 3 层 / §八.5；用户裁定
「按设计首批落地」2026-11-12）。

被测对象：scripts/export_site_sects_weapons_arts.py 的 D10 新增部分：
  load_lineage_supplement(path)  读 kb/校订/武功传承补链.tsv（表头
                                 art/from/to/tier/book/loc/note/status）→
                                 [{art,t,l,tier,book,loc,note}]；只有 status=校定 的行
                                 被消费（draft 计 stats 不入站）；tier ∈ 四档；loc 须为
                                 「NNN:NNN」（章回版源文件行号口径）；art/from/to/loc 空、
                                 loc 缺失、档位词表外、自环（from=to）、重复行 →
                                 LineageSupError（不静默改写人工校定稿）；
  build_arts(…, lineage_sup=…)   lineage 边组装时合并 TSV 补链：与 note 解析边
                                 同 (t,l,book,loc) → 跳过并记 field_gaps（不产生重复边）；
                                 同 (t,l) 新定位符 → 并入为同边多定位符（与 parse_lineage_note
                                 跨段多定位符同口径，前端取最强档）；TSV 行为人工考订，
                                 免「学生须在同门关系表 attestation」闸（§6.2 第 3 层的
                                 存在意义=补系统性漏链）；scope 口径书外行不消费；
                                 meta.field_gaps 声明口径；缺表 → 无补链、声明「不存在」；
  load_weapon_supplement(path)   读 kb/校订/神兵表-补录.tsv（表头
                                 weapon/form/aliases/holders_add/loc/note/status）→
                                 holders 考订补录（loc=「书名·NNN:NNN」式）；
  build_weapons(…, weapon_sup=…) holders 合并补录人：{name, n:0, sup:{book,loc,note}}
                                 追加（不伪造频次 n；同名已有不重复加）；scope 书外行不消费。

测试口径（先红后绿；除「真实 TSV 内容纪律」一节外全部用合成 fixture，不写 site/data）：
  - 补链是人工考订稿（唯一真源）：loc 必须真实（真实 TSV 一节逐条对章回版源文件 grep 核对）；
  - 首批 3 边=设计 §八.5 原文：凌未风—记名→周青、周青—记名→{冯广潮, 唐晓澜}（追风剑法）；
  - 游龙剑 holders 补周青=三女侠 001:141/002:31 明文（不伪造 holders 频次）。
"""
import csv
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（被测模块依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_sects_weapons_arts as exs  # noqa: E402

BOOK_A, BOOK_B = "测试书甲", "测试书乙"
SCOPE_A = {"profile": "demo", "books": [BOOK_A]}
REPO = Path(__file__).resolve().parents[2]


# ================================================================ fixtures（合成）
def _write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def _sup_rows(rows: list[dict]) -> list[dict]:
    """合成 build_arts 的 lineage_sup 入参（已过读取闸的行形状）。"""
    return rows


def _art(canonical, relations, **extra):
    rec = {"canonical": canonical, "category": "剑法", "aliases": [],
           "ev_total": 3, "books": sorted({b for b in relations}), "cross_book": False,
           "relations": relations}
    rec.update(extra)
    return rec


def _src(arts: list[dict], weapons: list[dict] | None = None) -> dict:
    """最小合成 src（与 test_arts_v2 同口径；weapons 部分供 build_weapons 用）。"""
    return {
        "old_arts": {"arts": arts, "meta": {"totals": {"by_category": {"其他": 0}}}},
        "old_sects": {"sects": [], "meta": {"note": ""}},
        "old_weapons": {"weapons": weapons or []},
        "lineage": {"sects": []},
        "artifacts": {"artifacts": [], "alias_candidates": [], "meta": {}},
        "moves": {"moves": [], "conflicts": []},
        "works": {},
        "entities": [], "wordlist": [],
        "sect_alias": {}, "art_alias": {}, "weapon_alias": {},
        "sect_canon": set(), "art_canon": set(), "weapon_canon": set(),
        "conc": {}, "conc_books": [BOOK_A, BOOK_B],
    }


def _relations_attest(master: str, student: str, book: str = BOOK_A) -> dict:
    """最小同门关系表：master 传授（note 不可解析——补链测试不依赖 note 解析路径）+ 学生修习。"""
    return {book: {"relations": [
        {"s": master, "st": "@", "pred": "修习", "locs": ["000:5"], "ev": 1, "note": "明文修习"},
        {"s": student, "st": "@", "pred": "修习", "locs": ["000:5"], "ev": 1, "note": "明文修习"},
    ]}}


def _weapon_rec(canonical, holders=None, books=None):
    return {"canonical": canonical, "kind": "剑", "grade": "神兵", "grade_basis": "",
            "conf": "ok", "status": "auto", "chain": [], "holders": holders or [],
            "borrowers": [], "makers": [], "end_state": None,
            "books": books or {BOOK_A: [1]}, "count": 3, "ev_total": 3,
            "evidence": [], "aliases": [], "source": "legacy"}


def _artifacts_src(recs: list[dict]) -> dict:
    """合成 build_weapons 的完整 src（artifacts=神兵表形状；其余源为空）。"""
    arts = []
    for r in recs:
        arts.append({"canonical": r["canonical"], "level": "名物", "status": "auto",
                     "kind": r["kind"], "grade": r["grade"], "grade_basis": "",
                     "conf": "ok", "chain": [], "holders": r["holders"],
                     "borrowers": [], "makers": [], "end_state": None,
                     "books": r["books"], "count": r["count"], "ev_total": 3,
                     "evidence": []})
    src = _src([])
    src["artifacts"] = {"artifacts": arts, "alias_candidates": [], "meta": {}}
    return src


def _by_canon(payload):
    return {a["canonical"]: a for a in payload["arts"]}


# ================================================================ 1. load_lineage_supplement（读取与闸门）
class TestLoadLineageSupplement:
    H = exs.LINEAGE_SUP_HEADER

    def test_reads_rows_and_filters_draft(self, tmp_path):
        """校定行 → 结构化行；draft 行计入 stats 不消费（评语 TSV 同纪律）。"""
        p = tmp_path / "sup.tsv"
        _write_tsv(p, self.H, [
            ["甲剑法", "祖师甲", "陈大勇", "记名", BOOK_A, "001:113", "明文记名弟子", "校定"],
            ["甲剑法", "祖师甲", "李小虎", "记名", BOOK_A, "001:125", "草案未校", "draft"],
        ])
        rows, stats = exs.load_lineage_supplement(p)
        assert stats == {"rows": 2, "consumed": 1, "draft": 1}
        assert rows == [{"art": "甲剑法", "t": "祖师甲", "l": "陈大勇", "tier": "记名",
                         "book": BOOK_A, "loc": "001:113", "note": "明文记名弟子"}]

    def test_missing_loc_raises(self, tmp_path):
        """loc 缺失（空值）→ 报错（人工考订稿不许无定位符行）。"""
        p = tmp_path / "sup.tsv"
        _write_tsv(p, self.H, [["甲剑法", "祖师甲", "陈大勇", "记名", BOOK_A, "", "x", "校定"]])
        with pytest.raises(exs.LineageSupError):
            exs.load_lineage_supplement(p)

    def test_bad_loc_format_raises(self, tmp_path):
        """loc 非「NNN:NNN」式（章回版源文件行号口径）→ 报错。"""
        p = tmp_path / "sup.tsv"
        _write_tsv(p, self.H, [["甲剑法", "祖师甲", "陈大勇", "记名", BOOK_A, "第13回", "x", "校定"]])
        with pytest.raises(exs.LineageSupError):
            exs.load_lineage_supplement(p)

    def test_bad_tier_raises(self, tmp_path):
        """tier 不在四档（正式/记名/挂名/点拨）→ 报错（传承树四档边型契约）。"""
        p = tmp_path / "sup.tsv"
        _write_tsv(p, self.H, [["甲剑法", "祖师甲", "陈大勇", "师承", BOOK_A, "001:1", "x", "校定"]])
        with pytest.raises(exs.LineageSupError):
            exs.load_lineage_supplement(p)

    def test_bad_header_and_empty_fields_raise(self, tmp_path):
        """表头错 / art·from·to 空值 → 报错（表头即契约）。"""
        p = tmp_path / "sup.tsv"
        _write_tsv(p, ["art", "from", "to"], [["甲剑法", "祖师甲", "陈大勇"]])
        with pytest.raises(exs.LineageSupError):
            exs.load_lineage_supplement(p)
        p2 = tmp_path / "sup2.tsv"
        _write_tsv(p2, self.H, [["", "祖师甲", "陈大勇", "记名", BOOK_A, "001:1", "", "校定"]])
        with pytest.raises(exs.LineageSupError):
            exs.load_lineage_supplement(p2)

    def test_self_loop_raises(self, tmp_path):
        """from=to 自环 → 报错（考订稿层面即拦截，不入组装）。"""
        p = tmp_path / "sup.tsv"
        _write_tsv(p, self.H, [["甲剑法", "陈大勇", "陈大勇", "记名", BOOK_A, "001:1", "x", "校定"]])
        with pytest.raises(exs.LineageSupError):
            exs.load_lineage_supplement(p)

    def test_duplicate_row_raises(self, tmp_path):
        """同 art+from+to+book+loc 重复行 → 报错（唯一真源）。"""
        p = tmp_path / "sup.tsv"
        _write_tsv(p, self.H, [
            ["甲剑法", "祖师甲", "陈大勇", "记名", BOOK_A, "001:1", "x", "校定"],
            ["甲剑法", "祖师甲", "陈大勇", "记名", BOOK_A, "001:1", "y", "校定"],
        ])
        with pytest.raises(exs.LineageSupError):
            exs.load_lineage_supplement(p)

    def test_missing_file_returns_empty(self, tmp_path):
        """缺表 → 空补链 + 统计零（build_arts 以 field_gaps 声明缺表口径）。"""
        rows, stats = exs.load_lineage_supplement(tmp_path / "不存在.tsv")
        assert rows == [] and stats == {"rows": 0, "consumed": 0, "draft": 0}


# ================================================================ 2. build_arts 合并补链
class TestBuildArtsLineageSupplement:
    def test_supplement_edges_merged_bypassing_attestation(self):
        """TSV 补链注入 lineage；学生不在同门关系表也入表（人工考订免 attestation 闸——
        这正是 §6.2 第 3 层的存在意义：周青/冯广潮 系统性漏链不在关系表）。"""
        rows = [{"art": "甲剑法", "t": "凌未风", "l": "周青", "tier": "记名",
                 "book": BOOK_A, "loc": "001:113", "note": ""}]
        payload, _st = exs.build_arts(_src([_art("甲剑法", _relations_attest("祖师甲", "陈大勇"))]),
                                      art_comments={}, lineage_sup=rows)
        rec = _by_canon(payload)["甲剑法"]
        assert rec["lineage"] == [{"t": "凌未风", "l": "周青", "book": BOOK_A,
                                   "loc": "001:113", "tier": "记名"}]

    def test_exact_duplicate_of_note_edge_skipped(self):
        """与 note 解析边同 (t,l,book,loc) → 跳过（不产生重复边）并记 field_gaps。"""
        rels = {BOOK_A: {"relations": [
            {"s": "祖师甲", "st": "@", "pred": "传授", "locs": ["000:5"], "ev": 1,
             "note": "000:5 传给陈大勇"},
            {"s": "陈大勇", "st": "@", "pred": "修习", "locs": ["000:5"], "ev": 1, "note": "明文修习"},
        ]}}
        rows = [{"art": "甲剑法", "t": "祖师甲", "l": "陈大勇", "tier": "正式",
                 "book": BOOK_A, "loc": "000:5", "note": "与解析边同源"}]
        payload, _st = exs.build_arts(_src([_art("甲剑法", rels)]),
                                      art_comments={}, lineage_sup=rows)
        rec = _by_canon(payload)["甲剑法"]
        assert rec["lineage"] == [{"t": "祖师甲", "l": "陈大勇", "book": BOOK_A,
                                   "loc": "000:5", "tier": "正式"}]
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "跳过" in gaps or "重复" in gaps

    def test_same_pair_new_loc_merged_as_multiloc(self):
        """同 (t,l) 新定位符 → 并入为同对第二条边（多定位符口径，前端归组取最强档），
        记 field_gaps；三条首批边各带定位符全部可见。"""
        rels = {BOOK_A: {"relations": [
            {"s": "周青", "st": "@", "pred": "传授", "locs": ["000:5"], "ev": 1,
             "note": "000:5 指点唐晓澜"},
            {"s": "唐晓澜", "st": "@", "pred": "修习", "locs": ["000:5"], "ev": 1, "note": "明文修习"},
        ]}}
        rows = [{"art": "甲剑法", "t": "周青", "l": "唐晓澜", "tier": "记名",
                 "book": BOOK_A, "loc": "001:141", "note": "记名档明文"}]
        payload, _st = exs.build_arts(_src([_art("甲剑法", rels)]),
                                      art_comments={}, lineage_sup=rows)
        rec = _by_canon(payload)["甲剑法"]
        locs = {(e["loc"], e["tier"]) for e in rec["lineage"]}
        assert locs == {("000:5", "点拨"), ("001:141", "记名")}
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "多定位符" in gaps

    def test_scope_drops_out_of_scope_rows(self):
        """scope 口径：补链书 ∉ scope → 不消费（不报错）；scope 内正常注入。"""
        rows = [{"art": "甲剑法", "t": "凌未风", "l": "周青", "tier": "记名",
                 "book": BOOK_A, "loc": "001:113", "note": ""},
                {"art": "甲剑法", "t": "周青", "l": "冯广潮", "tier": "记名",
                 "book": BOOK_B, "loc": "002:31", "note": ""}]
        rec = _art("甲剑法", _relations_attest("祖师甲", "陈大勇"))
        rec["books"] = [BOOK_A, BOOK_B]
        payload, _st = exs.build_arts(_src([rec]), scope=SCOPE_A,
                                      art_comments={}, lineage_sup=rows)
        got = _by_canon(payload)["甲剑法"]["lineage"]
        assert all(e["book"] == BOOK_A for e in got)
        assert {"t": "凌未风", "l": "周青", "book": BOOK_A, "loc": "001:113",
                "tier": "记名"} in got
        assert all(e["l"] != "冯广潮" for e in got)

    def test_meta_declares_supplement_and_unknown_art(self):
        """meta.field_gaps 声明补链口径；补链在案而无武功记录 → 记名不入表（不报错）。"""
        rows = [{"art": "无此武功", "t": "凌未风", "l": "周青", "tier": "记名",
                 "book": BOOK_A, "loc": "001:113", "note": ""}]
        payload, _st = exs.build_arts(_src([_art("甲剑法", _relations_attest("祖师甲", "陈大勇"))]),
                                      art_comments={}, lineage_sup=rows)
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "武功传承补链.tsv" in gaps and "无此武功" in gaps

    def test_missing_tsv_declared_in_field_gaps(self, monkeypatch, tmp_path):
        """缺 TSV → 全部武功无补链边注入路径照旧，field_gaps 声明「不存在」。"""
        monkeypatch.setattr(exs, "LINEAGE_SUP_TSV", tmp_path / "不存在.tsv")
        payload, _st = exs.build_arts(_src([_art("甲剑法", _relations_attest("祖师甲", "陈大勇"))]),
                                      art_comments={}, lineage_sup=None)
        assert "不存在" in "\n".join(payload["meta"]["field_gaps"])

    def test_weapons_sects_untouched_by_arts_supplement(self):
        """weapons/sects 与 arts 补链零关系（weapons 补录走神兵表-补录.tsv 独立通道）。"""
        rows = [{"art": "甲剑法", "t": "凌未风", "l": "周青", "tier": "记名",
                 "book": BOOK_A, "loc": "001:113", "note": ""}]
        src = _src([_art("甲剑法", _relations_attest("祖师甲", "陈大勇"))])
        wp, _w = exs.build_weapons(src)
        sp, _s = exs.build_sects(src)
        assert all("lineage" not in w for w in wp["weapons"])
        assert all("lineage" not in s for s in sp["sects"])


# ================================================================ 3. load_weapon_supplement + build_weapons 补录
class TestWeaponSupplement:
    H = exs.WEAPON_SUP_HEADER

    def _row(self, weapon="游龙剑", names="周青", loc="江湖三女侠·002:31",
             status="校定", form="剑", aliases="游龙宝剑", note="明文", cmd=""):
        return [weapon, form, aliases, names, loc, note, status, cmd]

    def test_reads_and_filters_draft(self, tmp_path):
        p = tmp_path / "wsup.tsv"
        _write_tsv(p, self.H, [self._row(), self._row(weapon="断玉剑", status="draft")])
        rows, stats = exs.load_weapon_supplement(p)
        assert stats["rows"] == 2 and stats["consumed"] == 1 and stats["draft"] == 1
        assert rows == [{"weapon": "游龙剑", "names": ["周青"], "book": "江湖三女侠",
                         "loc": "002:31", "note": "明文"}]

    def test_missing_loc_or_names_raises(self, tmp_path):
        p = tmp_path / "wsup.tsv"
        _write_tsv(p, self.H, [self._row(loc="")])
        with pytest.raises(exs.WeaponSupError):
            exs.load_weapon_supplement(p)
        p2 = tmp_path / "wsup2.tsv"
        _write_tsv(p2, self.H, [self._row(names="")])
        with pytest.raises(exs.WeaponSupError):
            exs.load_weapon_supplement(p2)

    def test_bad_loc_format_raises(self, tmp_path):
        """loc 非「书名·NNN:NNN」式 → 报错（与武功评语 loc 同口径）。"""
        p = tmp_path / "wsup.tsv"
        _write_tsv(p, self.H, [self._row(loc="002:31")])
        with pytest.raises(exs.WeaponSupError):
            exs.load_weapon_supplement(p)

    def test_chain_move_row_parsed(self, tmp_path):
        """F6：cmd=chain_move:<目标器> 行出表为 {kind, weapon, target, book, loc, note}（holders_add 空）。"""
        p = tmp_path / "wsup.tsv"
        _write_tsv(p, self.H, [self._row(weapon="断玉剑", names="", loc="江湖三女侠·024:15",
                                         note="被夺之剑实指游龙剑", form="", aliases="",
                                         cmd="chain_move:游龙剑")])
        rows, stats = exs.load_weapon_supplement(p)
        assert stats["rows"] == 1 and stats["consumed"] == 1 and stats["draft"] == 0
        assert rows == [{"kind": "chain_move", "weapon": "断玉剑", "target": "游龙剑",
                         "book": "江湖三女侠", "loc": "024:15", "note": "被夺之剑实指游龙剑"}]

    def test_chain_drop_row_parsed(self, tmp_path):
        p = tmp_path / "wsup.tsv"
        _write_tsv(p, self.H, [self._row(weapon="断玉剑", names="", loc="江湖三女侠·024:15",
                                         note="误挂边剔除", form="", aliases="", cmd="chain_drop")])
        rows, stats = exs.load_weapon_supplement(p)
        assert stats["consumed"] == 1
        assert rows == [{"kind": "chain_drop", "weapon": "断玉剑",
                         "book": "江湖三女侠", "loc": "024:15", "note": "误挂边剔除"}]

    @pytest.mark.parametrize("cmd", ["", "chain_move", "chain_move:", "nonsense", "chain_move:a:b"])
    def test_bad_cmd_raises(self, tmp_path, cmd):
        """cmd 指令词表（空=holders 补录 / chain_move:<目标> / chain_drop）：词表外或缺目标 → 报错。"""
        p = tmp_path / "wsup.tsv"
        _write_tsv(p, self.H, [self._row(weapon="断玉剑", names="", loc="江湖三女侠·024:15",
                                         note="", form="", aliases="", cmd=cmd)])
        with pytest.raises(exs.WeaponSupError):
            exs.load_weapon_supplement(p)

    def test_chain_row_with_holders_add_raises(self, tmp_path):
        """chain 指令行与 holders 补录不混用：holders_add 非空 → 报错（防呆）。"""
        p = tmp_path / "wsup.tsv"
        _write_tsv(p, self.H, [self._row(weapon="断玉剑", names="冯瑛", loc="江湖三女侠·024:15",
                                         note="", form="", aliases="", cmd="chain_move:游龙剑")])
        with pytest.raises(exs.WeaponSupError):
            exs.load_weapon_supplement(p)

    def test_chain_row_without_note_raises(self, tmp_path):
        """chain 指令行 note 必填（器物归属考订依据留档）。"""
        p = tmp_path / "wsup.tsv"
        _write_tsv(p, self.H, [self._row(weapon="断玉剑", names="", loc="江湖三女侠·024:15",
                                         note="", form="", aliases="", cmd="chain_move:游龙剑")])
        with pytest.raises(exs.WeaponSupError):
            exs.load_weapon_supplement(p)

    def test_chain_row_draft_counted_not_consumed(self, tmp_path):
        p = tmp_path / "wsup.tsv"
        _write_tsv(p, self.H, [self._row(weapon="断玉剑", names="", loc="江湖三女侠·024:15",
                                         note="待裁", form="", aliases="",
                                         status="draft", cmd="chain_move:游龙剑")])
        rows, stats = exs.load_weapon_supplement(p)
        assert rows == [] and stats["draft"] == 1 and stats["consumed"] == 0

    def test_holders_add_merged_with_sup_note(self):
        """holders 补录：追加 {name, n:0, sup:{book,loc,note}}（不伪造频次 n=0）；
        原有 holders 与排序不变。"""
        arts = _artifacts_src([_weapon_rec("游龙剑", holders=[{"name": "唐晓澜", "n": 79}])])
        rows = [{"weapon": "游龙剑", "names": ["周青"], "book": "江湖三女侠",
                 "loc": "002:31", "note": "靠着这把宝剑逃生"}]
        payload, _st = exs.build_weapons(arts, weapon_sup=rows)
        rec = next(w for w in payload["weapons"] if w["canonical"] == "游龙剑")
        assert rec["holders"][0] == {"name": "唐晓澜", "n": 79}
        assert rec["holders"][1] == {"name": "周青", "n": 0,
                                     "sup": {"book": "江湖三女侠", "loc": "002:31",
                                             "note": "靠着这把宝剑逃生"}}
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "神兵表-补录.tsv" in gaps and "n=0" in gaps

    def test_holders_add_dedup_existing_name(self):
        """holders 已有同名 → 不重复加（field_gaps 记账）。"""
        arts = _artifacts_src([_weapon_rec("游龙剑", holders=[{"name": "周青", "n": 5}])])
        rows = [{"weapon": "游龙剑", "names": ["周青"], "book": "江湖三女侠",
                 "loc": "002:31", "note": ""}]
        payload, _st = exs.build_weapons(arts, weapon_sup=rows)
        rec = next(w for w in payload["weapons"] if w["canonical"] == "游龙剑")
        assert rec["holders"] == [{"name": "周青", "n": 5}]

    def test_scope_drops_out_of_scope_rows(self):
        """scope 口径：补录书 ∉ scope → 不消费；scope 内正常注入。"""
        arts = _artifacts_src([_weapon_rec("游龙剑", holders=[])])
        arts["artifacts"]["artifacts"][0]["books"] = {BOOK_A: [1], BOOK_B: [1]}
        rows = [{"weapon": "游龙剑", "names": ["周青"], "book": BOOK_B,
                 "loc": "002:31", "note": ""}]
        payload, _st = exs.build_weapons(arts, scope=SCOPE_A, weapon_sup=rows)
        rec = next(w for w in payload["weapons"] if w["canonical"] == "游龙剑")
        assert rec["holders"] == []
        rows_a = [{"weapon": "游龙剑", "names": ["周青"], "book": BOOK_A,
                   "loc": "002:31", "note": ""}]
        payload, _st = exs.build_weapons(arts, scope=SCOPE_A, weapon_sup=rows_a)
        rec = next(w for w in payload["weapons"] if w["canonical"] == "游龙剑")
        assert [h["name"] for h in rec["holders"]] == ["周青"]

    def test_unknown_weapon_accounted_in_field_gaps(self):
        """补录在案而 weapons 无记录（scope 裁剪/未收录）→ 不报错，field_gaps 记名。"""
        arts = _artifacts_src([_weapon_rec("游龙剑", holders=[])])
        rows = [{"weapon": "无此名物", "names": ["周青"], "book": BOOK_A,
                 "loc": "002:31", "note": ""}]
        payload, _st = exs.build_weapons(arts, weapon_sup=rows)
        assert "无此名物" in "\n".join(payload["meta"]["field_gaps"])

    def test_missing_tsv_declared(self, monkeypatch, tmp_path):
        """缺 TSV → 无 holders 补录，field_gaps 声明「不存在」。"""
        monkeypatch.setattr(exs, "WEAPON_SUP_TSV", tmp_path / "不存在.tsv")
        payload, _st = exs.build_weapons(_artifacts_src([_weapon_rec("游龙剑")]),
                                         weapon_sup=None)
        assert "不存在" in "\n".join(payload["meta"]["field_gaps"])


# ================================================================ 4. 真实 TSV 内容纪律（人工校定稿把关）
class TestRealLineageSupplementTsv:
    """真实 kb/校订/武功传承补链.tsv 首批 3 边（设计 §八.5 原文裁定，用户「按设计首批落地」）。
    loc 全部为章回版源文件行号口径，逐条对 章回版/江湖三女侠 明文 grep 核对。"""

    def setup_method(self):
        assert exs.LINEAGE_SUP_TSV.exists(), "kb/校订/武功传承补链.tsv 不存在（D10 应已建）"
        self.rows, self.stats = exs.load_lineage_supplement()

    def _chapter_lines(self, chapter: str):
        files = sorted((REPO / "章回版" / "江湖三女侠").glob(f"{chapter}*.txt"))
        assert files, f"章回版/江湖三女侠/{chapter} 缺失"
        return files[0].read_text(encoding="utf-8").splitlines()

    def test_first_batch_three_edges(self):
        """首批 3 边=设计 §八.5：凌未风→周青、周青→{冯广潮,唐晓澜}，全部 记名@追风剑法。
        （D15 起同表追加第二批 13 边——第二批内容与 loc 纪律由 test_lineage_draft2.py
        为规范；本测试只锁首批三边仍居表首、行内容不变。）"""
        assert self.stats["consumed"] == 16 and self.stats["draft"] == 0
        assert [(r["t"], r["l"], r["tier"], r["book"]) for r in self.rows[:3]] == [
            ("凌未风", "周青", "记名", "江湖三女侠"),
            ("周青", "冯广潮", "记名", "江湖三女侠"),
            ("周青", "唐晓澜", "记名", "江湖三女侠")]
        assert all(r["art"] == "追风剑法" for r in self.rows[:3])

    def test_loc_001_113_ling_weifeng_jiming_zhouqing(self):
        """001:113 明文：凌未风教追风剑法、认周青为记名弟子（不是正式收徒）。"""
        line = self._chapter_lines("001")[112]
        assert "认他为记名弟子" in line and "不是正式收徒" in line and "追风剑法" in line
        assert "凌未风" in line and "周青" in line
        assert self.rows[0]["loc"] == "001:113"

    def test_loc_001_125_zhouqing_jiming_fengguangchao(self):
        """001:125 明文：冯广潮算周青记名弟子+七天传授追风剑法。"""
        line = self._chapter_lines("001")[124]
        assert "算是他的记名弟子" in line and "传授给我" in line
        assert self.rows[1]["loc"] == "001:125"

    def test_loc_001_141_zhouqing_tangxiaolan_shichengxian(self):
        """001:141 明文：周青赠唐晓澜游龙剑、称凌未风「你的祖师爷」（唐晓澜列周青师承线）。"""
        line = self._chapter_lines("001")[140]
        assert "你的祖师爷凌未风" in line and "游龙剑" in line and "唐晓澜" in line
        assert self.rows[2]["loc"] == "001:141"

    def test_corroboration_002_69_and_002_31(self):
        """002:69 复证凌未风—记名→周青；002:31 复证周青持游龙剑（神兵表-补录 loc）。"""
        l2 = self._chapter_lines("002")
        assert "凌未风的记名弟子" in l2[68] and "追风剑法" in l2[68]
        assert "靠着这把宝剑逃生" in l2[30]

    def test_real_rows_in_scope_books(self):
        """loc 书名全部在 scope 7 书内（天山演示版口径）。"""
        scope_books = {"散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
                       "七剑下天山", "冰魄寒光剑", "江湖三女侠"}
        assert all(r["book"] in scope_books for r in self.rows)


class TestRealWeaponSupplementTsv:
    """真实 kb/校订/神兵表-补录.tsv：D10 游龙剑 holders 补周青 + F6 chain_move（断玉剑→游龙剑·24:15）。
    F6 loc 明文核对：024:15「车辟邪手上拿着的正是唐晓澜那把游龙宝剑……所以才会硬抢了车辟邪的剑」。"""

    def setup_method(self):
        assert exs.WEAPON_SUP_TSV.exists(), "kb/校订/神兵表-补录.tsv 不存在（D10 应已建）"
        self.rows, self.stats = exs.load_weapon_supplement()

    def test_first_batch_youlong_zhouqing_plus_f6_chain_move(self):
        assert self.stats["consumed"] == 2 and self.stats["draft"] == 0
        assert self.rows[0] == {"weapon": "游龙剑", "names": ["周青"], "book": "江湖三女侠",
                                "loc": "002:31", "note": self.rows[0]["note"]}
        f6 = self.rows[1]
        assert f6["kind"] == "chain_move" and f6["weapon"] == "断玉剑" and f6["target"] == "游龙剑"
        assert f6["book"] == "江湖三女侠" and f6["loc"] == "024:15"

    def test_loc_002_31_zhouqing_holder_evidence(self):
        """002:31 明文：周青被围攻时靠着这把（游龙）宝剑逃生——持有人明文。"""
        files = sorted((REPO / "章回版" / "江湖三女侠").glob("002*.txt"))
        line = files[0].read_text(encoding="utf-8").splitlines()[30]
        assert "靠着这把宝剑逃生" in line and "游龙" in line

    def test_loc_024_15_seized_sword_is_youlong(self):
        """F6 loc 明文：024:15 被夺之剑实指游龙剑（唐晓澜名下），夺剑者冯瑛、被夺者车辟邪。"""
        files = sorted((REPO / "章回版" / "江湖三女侠").glob("024*.txt"))
        line = files[0].read_text(encoding="utf-8").splitlines()[14]
        assert "车辟邪手上拿着的正是唐晓澜那把游龙宝剑" in line
        assert "硬抢了车辟邪的剑" in line
        assert "游龙断玉二剑乃是天山之宝" in line


# ================================================================ 5. 真实数据链路（site/data 对账）
class TestRealDataLineage:
    """重导后真实 arts.json/weapons.json 的首批落地对账（数据即规范）。"""

    def _data(self, name):
        import json
        return json.loads((REPO / "site" / "data" / name).read_text(encoding="utf-8"))

    def test_zhuifeng_lineage_has_three_supplement_edges(self):
        data = self._data("arts.json")
        rec = next(a for a in data["arts"] if a["canonical"] == "追风剑法")
        edges = rec.get("lineage") or []
        assert {"t": "凌未风", "l": "周青", "book": "江湖三女侠", "loc": "001:113",
                "tier": "记名"} in edges
        assert {"t": "周青", "l": "冯广潮", "book": "江湖三女侠", "loc": "001:125",
                "tier": "记名"} in edges
        assert {"t": "周青", "l": "唐晓澜", "book": "江湖三女侠", "loc": "001:141",
                "tier": "记名"} in edges
        # 原解析边保留（多定位符口径）
        assert {"t": "周青", "l": "唐晓澜", "book": "江湖三女侠", "loc": "001:83",
                "tier": "点拨"} in edges

    def test_meta_declares_d10_supplement(self):
        data = self._data("arts.json")
        gaps = "\n".join(data["meta"]["field_gaps"])
        assert "武功传承补链.tsv" in gaps and "3" in gaps

    def test_youlong_holders_has_zhouqing_sup(self):
        data = self._data("weapons.json")
        rec = next(w for w in data["weapons"] if w["canonical"] == "游龙剑")
        sup = [h for h in rec["holders"] if h.get("name") == "周青"]
        assert len(sup) == 1 and sup[0]["n"] == 0
        assert sup[0]["sup"]["loc"] == "002:31" and sup[0]["sup"]["book"] == "江湖三女侠"
