# -*- coding: utf-8 -*-
"""D11 · 秘籍谱/丹药谱数据层测试（名物页重构设计 §七、§十一，2026-11-12）。

被测对象：scripts/export_site_manuals_elixirs.py（EX-6b）
  load_manual_tsv / load_elixir_tsv   两张人工校定底表（唯一真源）：表头/状态词/类别词/
                                      定位符/重复行/未知书名/loc∈books 逐项报错；
  load_concordance                    canonical 聚合（不分类型）——ev_total 口径；
  scan_corpus                         KB 标注层 struct 原文扫描（canonical+别名）——locs 口径；
  manual_category                     秘籍后缀分组；
  build_spectrum                      manuals-v1 / elixirs-v1 构建：
                                      - 覆盖闸（仅 scope 口径）：语料覆盖书 ⊆ 校定行 books；
                                      - draft 行不入站（宁缺毋滥）；
                                      - ev_total=concordance，未收者回退扫描计数并声明；
                                      - 毒解配对 D16：antidote_to/antidoted_by/negative_notes
                                        三键恒在（无数据=[]），poison/antidote 占位键移除；
                                      - 全量口径（scope=None）不设闸、books=并集（方案 R6）。

口径固化（测试即规范）：
  - TSV 为人工校定稿：语料漂移（concordance/扫描覆盖书超出校定行 books）→ 导出报错，
    不静默改写；全量口径不设闸（TSV 只核 7 书），field_gaps 声明书外覆盖。
  - 真实底表 pinning：秘籍 18 校定 + 1 draft（F2 增 6：金针度世/梵文秘典/达摩真经/青城古谱/
    梅花谱/武当秘笈，2026-11-12 用户裁定候选全收）、丹药谱 34 校定 + 1 draft（朱砂比喻用法；
    F3 增毒药 5 条孔雀粪/蛇焰箭/七煞白眉针/孔雀胆/赤毒珠 + F4 玉匣解药；类别词表丹药/药材/毒药）。
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_manuals_elixirs as exb  # noqa: E402

SCOPE_7 = {"profile": "tianshan-demo",
           "books": ["散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
                     "七剑下天山", "冰魄寒光剑", "江湖三女侠"]}

MANUAL_HEADER = "\t".join(exb.MANUAL_HEADER)
ELIXIR_HEADER = "\t".join(exb.ELIXIR_HEADER)


# ================================================================ fixtures
def _write_tsv(tmp_path: Path, name: str, header: str, rows: list[str]) -> Path:
    p = tmp_path / name
    p.write_text("\n".join([header] + rows) + "\n", encoding="utf-8")
    return p


def _manual_tsv(rows: list[str], tmp_path: Path) -> Path:
    return _write_tsv(tmp_path, "秘籍谱.tsv", MANUAL_HEADER, rows)


def _conc(*entries: tuple[str, list[tuple[str, int]]]) -> dict:
    """entries: (canonical, [(book, total), …]) → load_concordance 同构 dict（回目集默认空，
    回目并集口径由 scan 端与真实 concordance 覆盖）。"""
    out: dict[str, dict] = {}
    for canon, per in entries:
        rec = out.setdefault(canon, {"count": 0, "books": {}, "chapters": {}})
        for b, total in per:
            rec["count"] += total
            rec["books"][b] = rec["books"].get(b, 0) + total
    return out


def _fake_scan(monkeypatch, mapping: dict[str, list[tuple[str, str]]]):
    """monkeypatch scan_corpus：mapping {name: [(book, 'NNN:NNN'), …]}。"""

    def _scan(names, books):
        locs, hit = {}, {}
        for n in names:
            hits = [(b, loc) for b, loc in mapping.get(n, []) if b in books]
            locs[n] = [{"book": b, "loc": loc} for b, loc in hits]
            hit[n] = {b for b, _ in hits}
        return locs, hit

    monkeypatch.setattr(exb, "scan_corpus", _scan)


# ================================================================ 1. TSV 装载与校验
class TestTsvLoading:
    def test_manual_tsv_rows_and_status(self, tmp_path):
        p = _manual_tsv([
            "百毒真经\t\t\t联剑风云录\t联剑风云录·023:35\t毒经\t校定",
            "拳经剑谱\t\t\t联剑风云录\t联剑风云录·008:13\t存疑\tdraft",
        ], tmp_path)
        rows, stats = exb.load_manual_tsv(p)
        assert stats == {"rows": 2, "consumed": 1, "draft": 1, "exists": True}
        assert [r["status"] for r in rows] == ["校定", "draft"]
        assert rows[0]["book"] == "联剑风云录" and rows[0]["loc"] == "023:35"
        assert rows[0]["books"] == ["联剑风云录"]

    def test_manual_tsv_aliases_and_arts(self, tmp_path):
        p = _manual_tsv([
            "拳经剑诀\t拳经剑决、拳经剑法\t天山剑法\t七剑下天山、江湖三女侠\t七剑下天山·025:49\t同名两本\t校定",
        ], tmp_path)
        rows, _ = exb.load_manual_tsv(p)
        assert rows[0]["aliases"] == ["拳经剑决", "拳经剑法"]
        assert rows[0]["arts"] == ["天山剑法"]

    def test_elixir_tsv_kind_column(self, tmp_path):
        p = _write_tsv(tmp_path, "丹药谱.tsv", ELIXIR_HEADER, [
            "碧灵丹\t丹药\t\t联剑风云录\t联剑风云录·019:11\t解毒丹\t校定\t",
            "雪莲\t药材\t\t白发魔女传\t白发魔女传·010:61\t主料\t校定\t对某毒无效——联剑风云录·020:1",
        ])
        rows, stats = exb.load_elixir_tsv(p)
        assert stats["consumed"] == 2
        assert rows[0]["kind"] == "丹药" and rows[1]["kind"] == "药材"
        assert rows[0]["arts"] == []          # 丹药谱无 arts 列
        assert rows[0]["negative_notes"] == []   # D16：负证据列（空单元格 → []）
        assert rows[1]["negative_notes"][0]["desc"] == "对某毒无效"

    def test_error_bad_header(self, tmp_path):
        p = _write_tsv(tmp_path, "秘籍谱.tsv",
                       "manual\taliases\twrong\tbooks\tloc\tnote\tstatus",
                       ["百毒真经\t\t\t联剑风云录\t联剑风云录·023:35\t毒经\t校定"])
        with pytest.raises(exb.ManualsElixirsError, match="表头"):
            exb.load_manual_tsv(p)

    def test_error_bad_status(self, tmp_path):
        p = _manual_tsv(["百毒真经\t\t\t联剑风云录\t联剑风云录·023:35\t毒经\t待定"], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="不在校定档"):
            exb.load_manual_tsv(p)

    def test_error_duplicate_row(self, tmp_path):
        p = _manual_tsv([
            "百毒真经\t\t\t联剑风云录\t联剑风云录·023:35\t毒经\t校定",
            "百毒真经\t\t\t联剑风云录\t联剑风云录·024:16\t毒经\t校定",
        ], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="重复行"):
            exb.load_manual_tsv(p)

    def test_error_bad_loc_format(self, tmp_path):
        p = _manual_tsv(["百毒真经\t\t\t联剑风云录\t023:35\t毒经\t校定"], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="书名·NNN:NNN"):
            exb.load_manual_tsv(p)

    def test_error_empty_required_cell(self, tmp_path):
        p = _manual_tsv(["百毒真经\t\t\t\t联剑风云录·023:35\t毒经\t校定"], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="空值"):
            exb.load_manual_tsv(p)

    def test_error_unknown_book(self, tmp_path):
        p = _manual_tsv(["百毒真经\t\t\t不存在的书\t不存在的书·023:35\t毒经\t校定"], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="未知书名"):
            exb.load_manual_tsv(p)

    def test_error_loc_book_not_in_books(self, tmp_path):
        p = _manual_tsv(["百毒真经\t\t\t联剑风云录\t白发魔女传·010:36\t毒经\t校定"], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="定位符与覆盖书不一致"):
            exb.load_manual_tsv(p)

    def test_error_elixir_kind_out_of_vocabulary(self, tmp_path):
        p = _write_tsv(tmp_path, "丹药谱.tsv", ELIXIR_HEADER,
                       ["金创药\t成药\t\t七剑下天山\t七剑下天山·011:53\t成药\t校定\t"])
        with pytest.raises(exb.ManualsElixirsError, match="类别词表"):
            exb.load_elixir_tsv(p)

    def test_elixir_kind_poison_in_vocabulary(self, tmp_path):
        """F3：类别词表扩「毒药」——毒物名物实体入丹药谱（孔雀粪/蛇焰箭/七煞白眉针/孔雀胆/赤毒珠）。"""
        p = _write_tsv(tmp_path, "丹药谱.tsv", ELIXIR_HEADER, [
            "孔雀粪\t毒药\t\t七剑下天山\t七剑下天山·003:77\t剧毒名物\t校定\t",
            "赤毒珠\t毒药\t\t白发魔女传\t白发魔女传·015:67\t红花鬼母独门暗器\t校定\t",
        ])
        rows, stats = exb.load_elixir_tsv(p)
        assert stats["consumed"] == 2
        assert all(r["kind"] == "毒药" for r in rows)
        assert "毒药" in exb.ELIXIR_KINDS

    def test_missing_tsv_returns_empty(self, tmp_path):
        rows, stats = exb.load_manual_tsv(tmp_path / "不存在.tsv")
        assert rows == [] and stats["exists"] is False


# ================================================================ 2. 构建（合成口径）
class TestBuildScope:
    def test_manual_record_shape_and_gate_pass(self, tmp_path, monkeypatch):
        p = _manual_tsv(["百毒真经\t\t\t联剑风云录\t联剑风云录·023:35\t毒经\t校定"], tmp_path)
        rows, stats = exb.load_manual_tsv(p)
        _fake_scan(monkeypatch, {"百毒真经": [("联剑风云录", "023:35"), ("联剑风云录", "024:16")]})
        payload = exb.build_spectrum(rows, stats, SCOPE_7, _conc(("百毒真经", [("联剑风云录", 56)])),
                                     scan_books=[], spectrum="manuals")
        assert payload["meta"]["schema"] == "manuals-v1"
        assert payload["meta"]["scope"] == "tianshan-demo"
        assert payload["meta"]["totals"]["manuals"] == 1
        rec = payload["manuals"][0]
        assert rec["name"] == "百毒真经"
        assert rec["category"] == "经"
        assert rec["ev_total"] == 56 and rec["ev_basis"] == "concordance"
        assert rec["count"] == 2
        assert rec["books"] == {"联剑风云录": [23, 24]}
        assert rec["locs"] == [{"book": "联剑风云录", "loc": "023:35"},
                               {"book": "联剑风云录", "loc": "024:16"}]
        assert rec["evidence"][0]["kind"] == "原文扫描"
        assert rec["anchor"] == {"book": "联剑风云录", "loc": "023:35"}
        assert rec["related_arts"] == []            # 配不上 → 留空（契约统一键，不伪造配对）
        assert "poison" not in rec and "antidote" not in rec   # 秘籍不带毒药字段

    def test_gate_unattested_book_raises(self, tmp_path, monkeypatch):
        p = _manual_tsv(["百毒真经\t\t\t联剑风云录\t联剑风云录·023:35\t毒经\t校定"], tmp_path)
        rows, stats = exb.load_manual_tsv(p)
        _fake_scan(monkeypatch, {"百毒真经": [("联剑风云录", "023:35")]})
        conc = _conc(("百毒真经", [("联剑风云录", 50), ("七剑下天山", 6)]))
        with pytest.raises(exb.ManualsElixirsError, match="未列入校定行 books"):
            exb.build_spectrum(rows, stats, SCOPE_7, conc, scan_books=[], spectrum="manuals")

    def test_gate_scan_book_raises(self, tmp_path, monkeypatch):
        p = _manual_tsv(["百毒真经\t\t\t联剑风云录\t联剑风云录·023:35\t毒经\t校定"], tmp_path)
        rows, stats = exb.load_manual_tsv(p)
        _fake_scan(monkeypatch, {"百毒真经": [("联剑风云录", "023:35"), ("江湖三女侠", "002:37")]})
        conc = _conc(("百毒真经", [("联剑风云录", 56)]))
        with pytest.raises(exb.ManualsElixirsError, match="未列入校定行 books"):
            exb.build_spectrum(rows, stats, SCOPE_7, conc, scan_books=[], spectrum="manuals")

    def test_gate_empty_scope_presence_raises(self, tmp_path, monkeypatch):
        p = _manual_tsv(["幽灵秘册\t\t\t联剑风云录\t联剑风云录·001:1\t空壳\t校定"], tmp_path)
        rows, stats = exb.load_manual_tsv(p)
        _fake_scan(monkeypatch, {})
        with pytest.raises(exb.ManualsElixirsError, match="无任何语料出现"):
            exb.build_spectrum(rows, stats, SCOPE_7, {}, scan_books=[], spectrum="manuals")

    def test_draft_rows_filtered(self, tmp_path, monkeypatch):
        p = _manual_tsv([
            "百毒真经\t\t\t联剑风云录\t联剑风云录·023:35\t毒经\t校定",
            "拳经剑谱\t\t\t联剑风云录\t联剑风云录·008:13\t存疑\tdraft",
        ], tmp_path)
        rows, stats = exb.load_manual_tsv(p)
        _fake_scan(monkeypatch, {"百毒真经": [("联剑风云录", "023:35")]})
        payload = exb.build_spectrum(rows, stats, SCOPE_7,
                                     _conc(("百毒真经", [("联剑风云录", 56)])),
                                     scan_books=[], spectrum="manuals")
        assert [r["name"] for r in payload["manuals"]] == ["百毒真经"]
        assert payload["meta"]["totals"]["draft"] == 1
        assert any("draft" in g for g in payload["meta"]["field_gaps"])

    def test_related_arts_pairing_and_gap(self, tmp_path, monkeypatch):
        # arts.json 存在且不含 惊涛剑法 → 数据保留 + field_gaps 点名
        fake_site = tmp_path / "sitedata"
        fake_site.mkdir()
        (fake_site / "arts.json").write_text(json.dumps(
            {"arts": [{"canonical": "天山剑法"}]}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(exb.esc, "SITE_DATA", fake_site)
        p = _manual_tsv(_manual_tsv_text().split("\n"), tmp_path)
        rows, stats = exb.load_manual_tsv(p)
        _fake_scan(monkeypatch, {
            "天山剑诀": [("七剑下天山", "021:13")],
            "惊涛剑谱": [("联剑风云录", "005:60")],
        })
        conc = _conc(("天山剑诀", [("七剑下天山", 1)]), ("惊涛剑谱", [("联剑风云录", 2)]))
        payload = exb.build_spectrum(rows, stats, SCOPE_7, conc, scan_books=[], spectrum="manuals")
        by = {r["name"]: r for r in payload["manuals"]}
        assert by["天山剑诀"]["related_arts"] == ["天山剑法"]
        assert by["惊涛剑谱"]["related_arts"] == ["惊涛剑法"]   # 数据保留
        assert any("惊涛剑谱↔惊涛剑法" in g for g in payload["meta"]["field_gaps"])

    def test_ev_total_fallback_for_unlisted_herbs(self, tmp_path, monkeypatch):
        p = _write_tsv(tmp_path, "丹药谱.tsv", ELIXIR_HEADER,
                       ["曼陀罗花\t药材\t\t七剑下天山\t七剑下天山·003:38\t解药方\t校定\t"])
        rows, stats = exb.load_elixir_tsv(p)
        _fake_scan(monkeypatch, {"曼陀罗花": [("七剑下天山", "003:38")]})
        payload = exb.build_spectrum(rows, stats, SCOPE_7, {}, scan_books=[], spectrum="elixirs")
        rec = payload["elixirs"][0]
        assert rec["ev_total"] == 1 and rec["ev_basis"].startswith("原文扫描")
        assert "poison" not in rec and "antidote" not in rec   # D16：null 占位键移除
        assert rec["antidote_to"] == [] and rec["antidoted_by"] == []
        assert rec["negative_notes"] == []
        assert payload["meta"]["totals"]["毒解配对"] == 0
        assert any("未入标注实体层" in g for g in payload["meta"]["field_gaps"])
        assert payload["meta"]["totals"]["药材"] == 1

    def test_ev_total_fallback_includes_alias_scan(self, tmp_path, monkeypatch):
        """F4 玉匣解药（考订定名，canonical 未入 concordance、原文无连称）：ev_total 回退
        =canonical+别名扫描计数（别名 玉匣 携定位符），ev_basis 如实声明。"""
        p = _write_tsv(tmp_path, "丹药谱.tsv", ELIXIR_HEADER,
                       ["玉匣解药\t丹药\t玉匣\t联剑风云录、江湖三女侠\t联剑风云录·025:7\t考订定名\t校定\t"])
        rows, stats = exb.load_elixir_tsv(p)
        _fake_scan(monkeypatch, {
            "玉匣解药": [],
            "玉匣": [("联剑风云录", "024:91"), ("联剑风云录", "025:3"), ("江湖三女侠", "022:143")],
        })
        payload = exb.build_spectrum(rows, stats, SCOPE_7, {}, scan_books=[], spectrum="elixirs")
        rec = payload["elixirs"][0]
        assert rec["ev_total"] == 3 and rec["ev_basis"].startswith("原文扫描")
        assert rec["count"] == 3
        assert set(rec["books"]) == {"联剑风云录", "江湖三女侠"}
        assert rec["anchor"] == {"book": "联剑风云录", "loc": "025:7"}
        assert any("未入标注实体层" in g for g in payload["meta"]["field_gaps"])
        assert payload["meta"]["totals"]["丹药"] == 1

    def test_full_caliber_no_gate_union_books(self, tmp_path, monkeypatch):
        """方案 R6：全量口径（scope=None）不设覆盖闸，books=concordance ∪ 扫描 ∪ 底表并集。"""
        p = _manual_tsv(["百毒真经\t\t\t联剑风云录\t联剑风云录·023:35\t毒经\t校定"], tmp_path)
        rows, stats = exb.load_manual_tsv(p)
        _fake_scan(monkeypatch, {"百毒真经": [("联剑风云录", "023:35")]})
        conc = _conc(("百毒真经", [("联剑风云录", 56), ("七剑下天山", 10), ("云海玉弓缘", 3)]))
        payload = exb.build_spectrum(rows, stats, None, conc,
                                     scan_books=["联剑风云录", "七剑下天山"], spectrum="manuals")
        rec = payload["manuals"][0]
        assert set(rec["books"]) == {"联剑风云录", "七剑下天山", "云海玉弓缘"}
        assert "scope" not in payload["meta"]
        assert any("全量口径" in g for g in payload["meta"]["field_gaps"])

    def test_alias_scan_and_books_union(self, tmp_path, monkeypatch):
        """别名（如 少阳小还丹）参与扫描与覆盖书并集——books 覆盖散花女侠须在底表 books 内。"""
        p = _write_tsv(tmp_path, "丹药谱.tsv", ELIXIR_HEADER,
                       ["小还丹\t丹药\t少阳小还丹\t散花女侠、联剑风云录、白发魔女传\t白发魔女传·009:16\t保元丹\t校定\t"])
        rows, stats = exb.load_elixir_tsv(p)
        _fake_scan(monkeypatch, {
            "小还丹": [("联剑风云录", "010:2"), ("白发魔女传", "009:16")],
            "少阳小还丹": [("散花女侠", "009:52")],
        })
        conc = _conc(("小还丹", [("白发魔女传", 11), ("联剑风云录", 10)]))
        payload = exb.build_spectrum(rows, stats, SCOPE_7, conc, scan_books=[], spectrum="elixirs")
        rec = payload["elixirs"][0]
        assert set(rec["books"]) == {"散花女侠", "联剑风云录", "白发魔女传"}
        assert rec["count"] == 3                    # 扫描 2 + 别名扫描 1
        assert rec["ev_total"] == 21                # concordance canonical 口径（不含别名）

    def test_sort_by_ev_total_desc(self, tmp_path, monkeypatch):
        p = _manual_tsv([
            "甲谱\t\t\t联剑风云录\t联剑风云录·001:1\t甲\t校定",
            "乙经\t\t\t联剑风云录\t联剑风云录·001:1\t乙\t校定",
        ], tmp_path)
        rows, stats = exb.load_manual_tsv(p)
        _fake_scan(monkeypatch, {"甲谱": [("联剑风云录", "001:1")],
                                 "乙经": [("联剑风云录", "001:1")]})
        conc = _conc(("甲谱", [("联剑风云录", 2)]), ("乙经", [("联剑风云录", 9)]))
        payload = exb.build_spectrum(rows, stats, SCOPE_7, conc, scan_books=[], spectrum="manuals")
        assert [r["name"] for r in payload["manuals"]] == ["乙经", "甲谱"]


def _manual_tsv_text() -> str:
    return "\n".join([
        "天山剑诀\t\t天山剑法\t七剑下天山\t七剑下天山·021:13\t遗物\t校定",
        "惊涛剑谱\t\t惊涛剑法\t联剑风云录\t联剑风云录·005:60\t石惊涛剑谱\t校定",
    ])


# ================================================================ 3. 分组
class TestCategory:
    def test_manual_category_suffix_rules(self):
        assert exb.manual_category("天山剑诀") == "剑诀·剑谱"
        assert exb.manual_category("惊涛剑谱") == "剑诀·剑谱"
        assert exb.manual_category("百毒真经") == "经"
        assert exb.manual_category("晦明拳经") == "经"
        assert exb.manual_category("玄功要诀") == "诀"
        assert exb.manual_category("黏字诀") == "诀"
        assert exb.manual_category("达摩秘笈") == "秘笈"
        assert exb.manual_category("无名册") == "其他"


# ================================================================ 4. 真实底表 pinning（首批裁定固化）
class TestRealTsvPin:
    def test_manual_first_batch(self):
        """F2（2026-11-12 用户裁定「候选全收」）：D11 首批 12 + 金针度世/梵文秘典/达摩真经/
        青城古谱/梅花谱/武当秘笈 6 条 = 18 校定；红丸不收（无 何首乌合剂/红丸 行）。"""
        rows, stats = exb.load_manual_tsv()
        calib = [r for r in rows if r["status"] == "校定"]
        drafts = [r for r in rows if r["status"] == "draft"]
        assert stats["consumed"] == 18 and stats["draft"] == 1
        names = {r["name"] for r in calib}
        assert names == {"百毒真经", "玄功要诀", "拳经剑诀", "龙泉百炼诀", "惊涛剑谱",
                         "易筋经", "达摩秘笈", "天山剑诀", "晦明拳经", "追风剑诀",
                         "玄女剑诀", "黏字诀",
                         "金针度世", "梵文秘典", "达摩真经", "青城古谱", "梅花谱", "武当秘笈"}
        assert [r["name"] for r in drafts] == ["拳经剑谱"]      # 同物两可，待裁
        by = {r["name"]: r for r in calib}
        assert by["百毒真经"]["books"] == ["联剑风云录"]
        assert by["拳经剑诀"]["arts"] == ["天山剑法"]
        assert by["追风剑诀"]["arts"] == ["追风剑法"]
        assert by["易筋经"]["aliases"] == ["达摩易筋经"]
        # F2 新六条：锚点与覆盖书（金针度世 books 含白发=剑招同名异实的扫描闸如实申报）
        assert by["金针度世"]["book"] == "江湖三女侠" and by["金针度世"]["loc"] == "028:103"
        assert by["金针度世"]["books"] == ["江湖三女侠", "白发魔女传"]
        assert by["梵文秘典"]["aliases"] == ["梵文秘笈"]
        assert by["梵文秘典"]["books"] == ["冰魄寒光剑"]
        assert by["达摩真经"]["books"] == ["冰魄寒光剑"]
        assert by["青城古谱"]["books"] == ["联剑风云录"]
        assert by["梅花谱"]["books"] == ["七剑下天山"]
        assert by["武当秘笈"]["books"] == ["白发魔女传"]
        assert by["武当秘笈"]["loc"] == "031:91"

    def test_elixir_first_batch(self):
        """F3/F4（2026-11-12）：D11 首批 25 + 化毒丹/阳和丸/六合宁神丸（丹药）+
        孔雀粪/蛇焰箭/七煞白眉针/孔雀胆/赤毒珠（毒药）+ 玉匣解药（丹药，考订定名）= 34 校定。"""
        rows, stats = exb.load_elixir_tsv()
        calib = [r for r in rows if r["status"] == "校定"]
        drafts = [r for r in rows if r["status"] == "draft"]
        assert stats["consumed"] == 34 and stats["draft"] == 1
        elixirs = [r["name"] for r in calib if r["kind"] == "丹药"]
        herbs = [r["name"] for r in calib if r["kind"] == "药材"]
        poisons = [r["name"] for r in calib if r["kind"] == "毒药"]
        assert len(elixirs) == 11 and len(herbs) == 18 and len(poisons) == 5
        assert {"碧灵丹", "小还丹", "易容丹", "少还丹", "消魂蚀骨散", "五毒散",
                "云南白药", "化毒丹", "阳和丸", "六合宁神丸", "玉匣解药"} == set(elixirs)
        assert {"孔雀粪", "蛇焰箭", "七煞白眉针", "孔雀胆", "赤毒珠"} == set(poisons)
        assert len(herbs) == 18 and "朱砂" not in herbs          # 朱砂 比喻用法 → draft
        assert [r["name"] for r in drafts] == ["朱砂"]
        by = {r["name"]: r for r in calib}
        assert len(by["碧灵丹"]["books"]) == 6
        assert by["小还丹"]["aliases"] == ["少阳小还丹"]
        # F3 毒物：蛇焰箭五书覆盖（讯号/火攻两用如实申报）；玉匣解药别名=玉匣
        assert by["蛇焰箭"]["books"] == ["散花女侠", "联剑风云录", "白发魔女传",
                                         "七剑下天山", "江湖三女侠"]
        assert by["玉匣解药"]["aliases"] == ["玉匣"]
        assert by["玉匣解药"]["book"] == "联剑风云录" and by["玉匣解药"]["loc"] == "025:7"

    def test_real_scope_build_integration(self, monkeypatch):
        """真底表 × 真 concordance × 真语料扫描——覆盖闸全绿（语料与校定一致）；首批固化断言。"""
        rows, stats = exb.load_manual_tsv()
        calib = [r for r in rows if r["status"] == "校定"]
        conc = exb.load_concordance(SCOPE_7["books"])
        payload = exb.build_spectrum(calib, stats, SCOPE_7, conc,
                                     scan_books=exb.tagged_book_dirs(), spectrum="manuals")
        by = {r["name"]: r for r in payload["manuals"]}
        assert len(payload["manuals"]) == 18
        assert by["百毒真经"]["ev_total"] == 56
        assert set(by["百毒真经"]["books"]) == {"联剑风云录"}
        # locs=段落去重定位符（同段多次提及合一），56 处提及收敛为 40 个出场定位符
        assert len(by["百毒真经"]["locs"]) == 40
        assert by["百毒真经"]["locs"][0] == {"book": "联剑风云录", "loc": "023:35"}
        assert by["拳经剑诀"]["ev_total"] == 17
        assert set(by["拳经剑诀"]["books"]) == {"七剑下天山", "江湖三女侠"}
        assert by["玄功要诀"]["ev_total"] == 25
        assert by["黏字诀"]["category"] == "诀"
        assert any("惊涛剑谱↔惊涛剑法" in g for g in payload["meta"]["field_gaps"])
        # F2 新六条：双口径如实（金针度世 concordance 8 见=三女侠 6 书见+白发 2 剑招同名见；
        # 梵文秘典 concordance 2 见、扫描 4 定位符；低频行按原文扫描回退）
        assert by["金针度世"]["ev_total"] == 8
        assert set(by["金针度世"]["books"]) == {"白发魔女传", "江湖三女侠"}
        assert by["梵文秘典"]["ev_total"] == 2
        assert by["梵文秘典"]["count"] == 5          # 扫描：canonical 4 段 + 别名 梵文秘笈 1 段
        assert set(by["梵文秘典"]["books"]) == {"冰魄寒光剑"}
        assert by["达摩真经"]["ev_total"] == 1
        assert by["青城古谱"]["ev_total"] == 1
        assert by["梅花谱"]["ev_total"] == 1
        assert by["武当秘笈"]["ev_total"] == 1
        assert set(by["武当秘笈"]["books"]) == {"白发魔女传"}

    def test_real_scope_build_elixirs_integration(self, monkeypatch):
        rows, stats = exb.load_elixir_tsv()
        calib = [r for r in rows if r["status"] == "校定"]
        conc = exb.load_concordance(SCOPE_7["books"])
        pairs, _ = exb.load_antidote_tsv()                     # D16：配对底表入构建（同 main 口径）
        payload = exb.build_spectrum(calib, stats, SCOPE_7, conc,
                                     scan_books=exb.tagged_book_dirs(), spectrum="elixirs",
                                     pairs=pairs)
        by = {r["name"]: r for r in payload["elixirs"]}
        assert len(payload["elixirs"]) == 34
        assert by["碧灵丹"]["ev_total"] == 42
        assert set(by["碧灵丹"]["books"]) == {"联剑风云录", "白发魔女传", "塞外奇侠传",
                                              "七剑下天山", "冰魄寒光剑", "江湖三女侠"}
        assert by["小还丹"]["ev_total"] == 21
        assert "散花女侠" in by["小还丹"]["books"]              # 别名 少阳小还丹 并入
        assert by["曼陀罗花"]["ev_basis"].startswith("原文扫描")
        # D16：poison/antidote null 占位键移除；三键恒在（无配对=[]）
        assert all("poison" not in r and "antidote" not in r for r in payload["elixirs"])
        assert all(r["antidote_to"] == [] or isinstance(r["antidote_to"], list)
                   for r in payload["elixirs"])
        # F3/F4：毒解配对 14→15 组（+九阳毒掌↔玉匣解药）；毒药 5 条入谱（meta 分类计数）
        assert payload["meta"]["totals"]["毒解配对"] == 15
        assert payload["meta"]["totals"]["毒药"] == 5
        assert payload["meta"]["totals"]["丹药"] == 11
        assert payload["meta"]["totals"]["药材"] == 18
        # 毒物条「可被解」互链（antidoted_by 键=解药名，前端互链）
        assert sorted(g["antidote"] for g in by["孔雀粪"]["antidoted_by"]) == \
            sorted(["碧灵丹", "长白山人参", "天山雪莲", "曼陀罗花"])
        assert [g["antidote"] for g in by["蛇焰箭"]["antidoted_by"]] == ["天山雪莲"]
        assert [g["antidote"] for g in by["七煞白眉针"]["antidoted_by"]] == ["少还丹"]
        assert [g["antidote"] for g in by["孔雀胆"]["antidoted_by"]] == ["天山雪莲"]
        assert by["赤毒珠"]["antidoted_by"] == []               # 无专名解药明文，不立
        # F4：玉匣解药「可解」=九阳毒掌(掌毒)（025:7 对症明文）
        assert [g["poison"] for g in by["玉匣解药"]["antidote_to"]] == ["九阳毒掌(掌毒)"]
        # 碧灵丹页「可解」清单不变（14 组保持；新组解药=玉匣解药，不涉碧灵丹）
        assert sorted(g["poison"] for g in by["碧灵丹"]["antidote_to"]) == \
            sorted(["孔雀粪", "鹤顶红", "九阳毒掌(掌毒)"])
        assert all("玉匣解药" in g["note"] for g in by["玉匣解药"]["antidote_to"])
