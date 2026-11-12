# -*- coding: utf-8 -*-
"""W2-B6 · 门派驻地考订.tsv → sects.json type/seat 测试（门派志页重构设计 §一决策 1/3、§五、§八；总体方案 §4.2 B6）。

被测对象：scripts/export_site_sects_weapons_arts.py 的
  load_sect_calib(path)   读 kb/校订/门派驻地考订.tsv（表头 sect/type/seat_name/status/anchor/basis；
                          类型词表 名门正派/世家/绿林帮会/朝廷势力；驻地档 实锚/推理/待考）
  build_sects(…, calib=…) type + seat{name,status,basis} 并入对应 sects 记录；
                          TSV 在案而管线未收的考订势力（大内等）由 concordance ◆/& 证据入册；
                          无库内出现记录的行不入表（notes 声明）；scope 口径同样裁剪；
                          meta.field_gaps/notes 声明并入口径

测试口径（先红后绿；除「真实 TSV 内容纪律」一节外全部用合成 fixture，不写 site/data）：
  - 未入表门派**无 type/seat 字段**（不是 null/空串——前端按字段存在性分区）；
  - TSV 行 scope 外（或库内无出现）→ 不消费不入表，不报错；
  - 新入册记录 source="new"、books/ev_total 取 concordance 口径，与其余管线记录同构。
"""
import csv
import json
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（被测模块依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_sects_weapons_arts as exs  # noqa: E402

BOOK_A, BOOK_B = "测试书甲", "测试书乙"
SCOPE_A = {"profile": "demo", "books": [BOOK_A]}

CALIB = {
    "测试派": {"type": "名门正派", "seat": {"name": "测试山", "status": "实锚", "basis": "明文：测试派驻测试山"}},
    "站外派": {"type": "世家", "seat": {"name": "某城", "status": "推理", "basis": "明文：某城为推理"}},
    "大内": {"type": "朝廷势力", "seat": {"name": "京城", "status": "实锚", "basis": "明文：大内卫士驻禁城"}},
    "山寨": {"type": "绿林帮会", "seat": {"name": "山寨", "status": "待考", "basis": "明文见 004 回"}},
}


def _sect(canonical, books, ev):
    return {"canonical": canonical, "books": list(books), "cross_book": len(books) > 1,
            "ev_total": ev, "arts_by_pred": {}, "members": [], "tenures": [],
            "lineage_gaps": [], "lineage_todo": []}


def _src():
    """最小合成 src：old_sects 两派（一派仅乙书=scope 外）+ conc（测试派/大内有 ◆，山寨无）。"""
    return {
        "old_sects": {"sects": [_sect("测试派", [BOOK_A, BOOK_B], 9),
                                _sect("站外派", [BOOK_B], 2),
                                _sect("无考订派", [BOOK_A], 1)],
                      "meta": {"note": ""}},
        "lineage": {"sects": []},
        "sect_alias": {}, "sect_canon": {"测试派", "站外派", "无考订派"},
        "art_alias": {}, "art_canon": set(),
        "weapon_alias": {}, "weapon_canon": set(),
        "conc": {("◆", "测试派"): {"count": 50, "books": {BOOK_A: 30, BOOK_B: 20},
                                   "chapters": {}, "variants": set()},
                 ("◆", "大内"): {"count": 8, "books": {BOOK_B: 8},
                                 "chapters": {}, "variants": set()}},
        "conc_books": [BOOK_A, BOOK_B],
        "moves": {"moves": []},
        "entities": [], "wordlist": [],
    }


def _write_tsv(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    """rows: (sect, type, seat_name, status) → tab 分隔 TSV（W2-B6 表头，anchor/basis 末两列）。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["sect", "type", "seat_name", "status", "anchor", "basis"])
        for sect, typ, seat_name, status in rows:
            w.writerow([sect, typ, seat_name, status, "锚点", "明文：测试依据"])


def _by_canon(payload):
    return {s["canonical"]: s for s in payload["sects"]}


# ================================================================ 1. load_sect_calib（读取与闸门）
class TestLoadSectCalib:
    def test_missing_file_returns_empty(self, tmp_path):
        """文件不存在 → {}（build_sects 以 field_gaps 声明缺 TSV 口径）。"""
        assert exs.load_sect_calib(tmp_path / "不存在.tsv") == {}

    def test_parses_rows_to_type_seat(self, tmp_path):
        """数据行 → {sect: {type, seat{name,status,basis}}}；anchor 列不入 seat（地图层消费）。"""
        p = tmp_path / "门派驻地考订.tsv"
        _write_tsv(p, [("测试派", "名门正派", "测试山", "实锚"),
                       ("大内", "朝廷势力", "京城", "实锚")])
        calib = exs.load_sect_calib(p)
        assert set(calib) == {"测试派", "大内"}
        assert calib["大内"] == {"type": "朝廷势力",
                                 "seat": {"name": "京城", "status": "实锚", "basis": "明文：测试依据"}}

    def test_unknown_type_raises(self, tmp_path):
        """type 不在类型词表（名门正派/世家/绿林帮会/朝廷势力）→ SectCalibError 报错。"""
        p = tmp_path / "门派驻地考订.tsv"
        _write_tsv(p, [("测试派", "魔道邪派", "测试山", "实锚")])
        with pytest.raises(exs.SectCalibError, match="类型词表"):
            exs.load_sect_calib(p)

    def test_unknown_status_raises(self, tmp_path):
        """status 不在驻地判定档（实锚/推理/待考）→ SectCalibError 报错。"""
        p = tmp_path / "门派驻地考订.tsv"
        _write_tsv(p, [("测试派", "名门正派", "测试山", "疑似")])
        with pytest.raises(exs.SectCalibError, match="驻地判定"):
            exs.load_sect_calib(p)

    def test_duplicate_sect_raises(self, tmp_path):
        """同派两行 → SectCalibError（唯一真源，只允许一行）。"""
        p = tmp_path / "门派驻地考订.tsv"
        _write_tsv(p, [("测试派", "名门正派", "测试山", "实锚"),
                       ("测试派", "世家", "某城", "推理")])
        with pytest.raises(exs.SectCalibError, match="重复"):
            exs.load_sect_calib(p)

    def test_bad_header_raises(self, tmp_path):
        """表头非 sect/type/seat_name/status/anchor/basis → SectCalibError。"""
        p = tmp_path / "门派驻地考订.tsv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("sect\t类型\t驻地\tstatus\tanchor\tbasis\n")
        with pytest.raises(exs.SectCalibError, match="表头"):
            exs.load_sect_calib(p)


# ================================================================ 2. build_sects 注入（合成 fixture）
class TestBuildSectsCalib:
    def test_type_seat_injected_into_existing(self):
        """TSV 校定行 → 对应记录带 type/seat；records 其余字段（books/ev_total/source）不动。"""
        payload, _st = exs.build_sects(_src(), calib=CALIB)
        rec = _by_canon(payload)["测试派"]
        assert rec["type"] == "名门正派"
        assert rec["seat"] == {"name": "测试山", "status": "实锚", "basis": "明文：测试派驻测试山"}
        assert set(rec["books"]) == {BOOK_A, BOOK_B} and rec["ev_total"] == 50
        assert rec["source"] == "legacy"

    def test_untyped_sect_has_no_type_key(self):
        """未入表门派**无 type/seat 字段**（不是 null/空串——前端按字段存在性分区）。"""
        payload, _st = exs.build_sects(_src(), calib=CALIB)
        rec = _by_canon(payload)["无考订派"]
        assert "type" not in rec and "seat" not in rec
        assert rec.get("type") is None and not isinstance(rec.get("type"), str)

    def test_seat_exact_keys(self):
        """seat 结构恰为 {name, status, basis}（不多不少）。"""
        payload, _st = exs.build_sects(_src(), calib=CALIB)
        seat = _by_canon(payload)["测试派"]["seat"]
        assert set(seat) == {"name", "status", "basis"}

    def test_tsv_creates_missing_court_org(self):
        """TSV 在案而管线未收（大内：组织后缀不在白名单被排除）→ 由 concordance ◆ 证据入册：
        source="new"、books/ev_total 取 conc 口径、type/seat 齐全。"""
        payload, _st = exs.build_sects(_src(), calib=CALIB)
        rec = _by_canon(payload)["大内"]
        assert rec["type"] == "朝廷势力"
        assert rec["seat"]["name"] == "京城"
        assert rec["books"] == [BOOK_B] and rec["ev_total"] == 8 and rec["cross_book"] is False
        assert rec["source"] == "new"
        assert rec["members"] == [] and rec["tenures"] == []

    def test_tsv_row_without_corpus_presence_not_created(self):
        """TSV 行库内无 ◆/& 出现记录（山寨）→ 不入表（不造空壳），meta.notes 点名。"""
        payload, _st = exs.build_sects(_src(), calib=CALIB)
        assert "山寨" not in _by_canon(payload)
        assert any("山寨" in n for n in payload["meta"]["notes"])

    def test_scope_drops_out_of_scope_rows(self):
        """scope 口径：scope 外门派行不消费——站外派（仅乙书）与大内（◆ 仅乙书）不入表，
        scope 内的测试派正常注入；scope 外行不报错。"""
        payload, _st = exs.build_sects(_src(), scope=SCOPE_A, calib=CALIB)
        by = _by_canon(payload)
        assert set(by) == {"测试派", "无考订派"}
        assert by["测试派"]["type"] == "名门正派"
        assert "站外派" not in by and "大内" not in by
        assert "type" not in by["无考订派"]

    def test_full_caliber_unchanged_shape(self):
        """全量口径（scope=None）：meta 无 scope 键；注入不破坏既有排序（-ev_total, canonical）。"""
        payload, _st = exs.build_sects(_src(), calib=CALIB)
        assert "scope" not in payload["meta"]
        assert [s["canonical"] for s in payload["sects"]] == ["测试派", "大内", "站外派", "无考订派"]

    def test_field_gaps_and_notes_declare(self):
        """meta.field_gaps 声明 type/seat 覆盖口径；meta.notes 记 TSV 源与规模。"""
        payload, _st = exs.build_sects(_src(), calib=CALIB)
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "type/seat" in gaps and "门派驻地考订.tsv" in gaps and "无 type/seat 字段" in gaps
        notes = "\n".join(payload["meta"]["notes"])
        assert "门派驻地考订.tsv" in notes and "校定行" in notes

    def test_missing_tsv_declares_gap_and_no_fields(self, tmp_path, monkeypatch):
        """缺 TSV → 全部门派无 type/seat 字段，field_gaps 声明「不存在」。"""
        monkeypatch.setattr(exs, "SECT_CALIB_TSV", tmp_path / "不存在.tsv")
        payload, _st = exs.build_sects(_src())
        assert all("type" not in s and "seat" not in s for s in payload["sects"])
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "type/seat" in gaps and "不存在" in gaps


# ================================================================ 3. 真实 TSV 内容纪律（人工校定稿把关）
REAL_SECTS = ["武当派", "少林派", "天山派", "峨嵋派", "华山派", "昆仑派", "终南派", "长白山派",
              "唐家", "大内", "明月峡", "五龙帮"]


class TestRealSectCalibTsv:
    """真实 kb/校订/门派驻地考订.tsv 的考订纪律（内容即规范）。"""

    def setup_method(self):
        assert exs.SECT_CALIB_TSV.exists(), "kb/校订/门派驻地考订.tsv 不存在（W2-B6 应已建）"
        self.calib = exs.load_sect_calib()   # 表头/类型词表/驻地档/重复行在此即报错

    def test_rows_and_vocab(self):
        """12 派校定行；type/status 全部在词表内（load_sect_calib 已闸门，这里固化解析规模）。"""
        assert set(self.calib) == set(REAL_SECTS)
        assert len(self.calib) == 12

    def test_type_distribution(self):
        """类型分布：名门正派 8 / 世家 1 / 绿林帮会 2 / 朝廷势力 1。"""
        dist = {}
        for row in self.calib.values():
            dist[row["type"]] = dist.get(row["type"], 0) + 1
        assert dist == {"名门正派": 8, "世家": 1, "绿林帮会": 2, "朝廷势力": 1}

    def test_key_sects_typed(self):
        """关键行：天山派/武当派=名门正派；大内=朝廷势力（另册）；五龙帮/明月峡=绿林帮会（入主册）。"""
        assert self.calib["天山派"]["type"] == "名门正派"
        assert self.calib["武当派"]["type"] == "名门正派"
        assert self.calib["大内"]["type"] == "朝廷势力"
        assert {s for s, r in self.calib.items() if r["type"] == "绿林帮会"} == {"明月峡", "五龙帮"}

    def test_seats_structured(self):
        """seat 结构 {name, status, basis}；basis 非空（每行挂考订依据）。"""
        for sect, row in self.calib.items():
            assert set(row["seat"]) == {"name", "status", "basis"}, sect
            assert row["seat"]["basis"], sect
            assert row["seat"]["status"] in ("实锚", "推理", "待考"), sect

    def test_real_chain_existing_sects_typed(self):
        """真实口径整链（全量口径合成 src 太重——这里只验 TSV→注入函数可消费真实行结构）：
        每行 type/seat 可被 build_sects 注入路径直接使用（键齐全、无多余嵌套）。"""
        for row in self.calib.values():
            assert set(row) == {"type", "seat"}
