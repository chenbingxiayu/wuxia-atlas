# -*- coding: utf-8 -*-
"""D16 · 毒↔解药配对正式化测试（用户裁定「14 组全收」，2026-11-12）。

被测对象：
  scripts/export_site_manuals_elixirs.py（EX-6b 扩展）
    load_antidote_tsv                    毒解配对底表（kb/校订/毒解配对.tsv，19 证据行/15 配对——
                                         D16 14 组 + F4 九阳毒掌↔玉匣解药组，2026-11-12）
                                         装载：表头/状态词/定位符/已知书名/通名毒排除/同组注记一致/
                                         重复行逐项报错；
    negative_notes 列                     丹药谱.tsv 第 8 列（elixir 级负证据，碧灵丹 2 项）；
    build_spectrum（elixirs）            双向消费：antidote_to（解药条「可解」清单）/
                                         antidoted_by（毒条「可被解」清单）/ negative_notes——
                                         三键恒在（无数据为 []），poison/antidote null 占位键移除
                                         （契约演进：D16 重置基线）。

口径固化（测试即规范）：
  - 配对证据 loc=章回版 raw 行号（D13 复核 18/18 命中，无漂移）；负证据书名=江湖三女侠
    （031:227 皇帝毒酒无效、032:101/103 唐家暗器非对症——D13 汇报误写联剑，D16 修正）；
  - 上站注记全部原创 L0：不得含草案 verbatim 摘样（版权闸门前置，测试抽全量断言）；
  - 通名毒（毒酒/暗器等）不入 poison 列；新毒物实体（孔雀粪/蛇焰箭/七煞白眉针/孔雀胆）
    第二批入谱——本批毒名以文本列于解药页（不要求入谱实体）；
  - 五毒散↔消魂蚀骨散 同伤异名：两行分立（证据各异），注记互见（裁定④）。
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

PAIR_HEADER = "\t".join(exb.PAIR_HEADER)
ELIXIR_HEADER = "\t".join(exb.ELIXIR_HEADER)

# D13 草案 verbatim 摘样全集（QUOTE_OVERRIDES；正式注记不得含其中任何一句）
DRAFT_VERBATIM = [
    "是我给了他用天山雪莲炮制的碧灵丹",
    "解孔雀粪和鹤顶红的毒，须用上好的长白山人参",
    "蛇焰箭是硫磺火，火毒攻心",
    "虽然不是对症的解药，但在三五天内，却可将毒气止着不升",
    "吃了弘法大师所赠的“少还丹”，白眉针已被血液胶住",
    "服食少还丹后，白眉针本己给血液胶住",
    "兼有小还丹化毒补气",
    "将三粒小还丹给他服下",
    "孔雀胆、鹤顶红那样的剧毒，有了天山雪莲亦可以解救",
    "曾服了一颗用天山雪莲所制炼的碧灵丹，又服了半颗解药",
    "天山雪莲能解百毒，最少也可以减轻那股阴毒之气",
]


# ================================================================ fixtures
def _write_tsv(tmp_path: Path, name: str, header: str, rows: list[str]) -> Path:
    p = tmp_path / name
    p.write_text("\n".join([header] + rows) + "\n", encoding="utf-8")
    return p


def _pair_tsv(rows: list[str], tmp_path: Path) -> Path:
    return _write_tsv(tmp_path, "毒解配对.tsv", PAIR_HEADER, rows)


def _conc(*entries: tuple[str, list[tuple[str, int]]]) -> dict:
    out: dict[str, dict] = {}
    for canon, per in entries:
        rec = out.setdefault(canon, {"count": 0, "books": {}, "chapters": {}})
        for b, total in per:
            rec["count"] += total
            rec["books"][b] = rec["books"].get(b, 0) + total
    return out


def _fake_scan(monkeypatch, mapping: dict[str, list[tuple[str, str]]]):
    def _scan(names, books):
        locs, hit = {}, {}
        for n in names:
            hits = [(b, loc) for b, loc in mapping.get(n, []) if b in books]
            locs[n] = [{"book": b, "loc": loc} for b, loc in hits]
            hit[n] = {b for b, _ in hits}
        return locs, hit
    monkeypatch.setattr(exb, "scan_corpus", _scan)


# ================================================================ 1. 正式底表 pinning
class TestPairingTsv:
    def test_14_pairs_18_rows_all_calibrated(self):
        """用户裁定「14 组全收」（D16）+ F4 增 1 组（九阳毒掌↔玉匣解药，2026-11-12）：
        19 证据行收敛 15 配对，全部校定档。"""
        rows, stats = exb.load_antidote_tsv()
        assert stats["rows"] == 19 and stats["consumed"] == 19 and stats["draft"] == 0
        pairs = {(r["poison"], r["antidote"]) for r in rows}
        assert len(pairs) == 15
        assert pairs == {
            ("孔雀粪", "碧灵丹"), ("鹤顶红", "碧灵丹"),
            ("孔雀粪", "长白山人参"), ("鹤顶红", "长白山人参"),
            ("孔雀粪", "天山雪莲"), ("鹤顶红", "天山雪莲"),
            ("孔雀粪", "曼陀罗花"), ("鹤顶红", "曼陀罗花"),
            ("蛇焰箭", "天山雪莲"), ("孔雀胆", "天山雪莲"),
            ("七煞白眉针", "少还丹"), ("阴风毒砂掌(掌毒)", "小还丹"),
            ("九阳毒掌(掌毒)", "碧灵丹"), ("修罗阴煞功(功毒)", "天山雪莲"),
            ("九阳毒掌(掌毒)", "玉匣解药"),
        }
        # 武功毒 3 组带 (掌毒)/(功毒) 后缀（裁定①）
        suffixed = {p for p, _ in pairs if "(" in p}
        assert suffixed == {"阴风毒砂掌(掌毒)", "九阳毒掌(掌毒)", "修罗阴煞功(功毒)"}

    def test_locs_pin_d13_review(self):
        """D13 loc 逐组复核固化：18 证据行定位符全命中（漂移即失败）。"""
        rows, _ = exb.load_antidote_tsv()
        got = {(r["poison"], r["antidote"], r["book"], r["loc"]) for r in rows}
        for key in [
            ("孔雀粪", "碧灵丹", "七剑下天山", "003:77"),
            ("鹤顶红", "碧灵丹", "七剑下天山", "003:77"),
            ("孔雀粪", "长白山人参", "七剑下天山", "003:77"),
            ("鹤顶红", "长白山人参", "七剑下天山", "003:77"),
            ("孔雀粪", "天山雪莲", "七剑下天山", "003:77"),
            ("鹤顶红", "天山雪莲", "七剑下天山", "003:77"),
            ("孔雀粪", "曼陀罗花", "七剑下天山", "003:77"),
            ("鹤顶红", "曼陀罗花", "七剑下天山", "003:77"),
            ("蛇焰箭", "天山雪莲", "七剑下天山", "005:23"),
            ("七煞白眉针", "少还丹", "江湖三女侠", "028:19"),
            ("七煞白眉针", "少还丹", "江湖三女侠", "028:43"),
            ("七煞白眉针", "少还丹", "江湖三女侠", "028:49"),
            ("阴风毒砂掌(掌毒)", "小还丹", "白发魔女传", "010:67"),
            ("阴风毒砂掌(掌毒)", "小还丹", "白发魔女传", "010:69"),
            ("鹤顶红", "天山雪莲", "冰魄寒光剑", "008:5"),
            ("孔雀胆", "天山雪莲", "冰魄寒光剑", "008:5"),
            ("九阳毒掌(掌毒)", "碧灵丹", "联剑风云录", "027:65"),
            ("修罗阴煞功(功毒)", "天山雪莲", "联剑风云录", "032:3"),
            ("九阳毒掌(掌毒)", "玉匣解药", "联剑风云录", "025:7"),
        ]:
            assert key in got, f"配对证据漂移：{key}"

    def test_notes_original_not_verbatim(self):
        """版权闸门前置：正式注记为原创 L0——不得含草案 verbatim 摘样（全量断言）。"""
        rows, _ = exb.load_antidote_tsv()
        assert len(rows) == 19
        for r in rows:
            assert r["note"].strip(), f"{r['poison']}↔{r['antidote']} 注记为空"
            for q in DRAFT_VERBATIM:
                assert q not in r["note"], \
                    f"{r['poison']}↔{r['antidote']} 注记含草案 verbatim 摘样：{q}"

    def test_antidote_names_in_elixir_spectrum(self):
        """解药专名必须为丹药谱校定名/别名（互链总有效）；毒名非通名。"""
        pairs, _ = exb.load_antidote_tsv()
        e_rows, _ = exb.load_elixir_tsv()
        calib = [r for r in e_rows if r["status"] == "校定"]
        spectrum = set()
        for r in calib:
            spectrum.add(r["name"])
            spectrum.update(r["aliases"])
        for r in pairs:
            assert r["antidote"] in spectrum, \
                f"解药 {r['antidote']} 不在丹药谱校定名/别名——互链将断"
            assert r["poison"] not in exb.GENERIC_POISONS, f"通名毒入列：{r['poison']}"


# ================================================================ 2. 装载校验（合成口径）
class TestPairingLoaderErrors:
    ROW = "孔雀粪\t碧灵丹\t七剑下天山\t003:77\t傅青主明示解毒配方\t校定"

    def test_error_bad_header(self, tmp_path):
        p = _write_tsv(tmp_path, "毒解配对.tsv", "poison\tantidote\twrong\tbook\tloc\tnote\tstatus",
                       [self.ROW])
        with pytest.raises(exb.ManualsElixirsError, match="表头"):
            exb.load_antidote_tsv(p)

    def test_error_bad_status(self, tmp_path):
        p = _pair_tsv(["孔雀粪\t碧灵丹\t七剑下天山\t003:77\t注\t待定"], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="不在校定档"):
            exb.load_antidote_tsv(p)

    def test_error_bad_loc_format(self, tmp_path):
        p = _pair_tsv(["孔雀粪\t碧灵丹\t七剑下天山\t第3回\t注\t校定"], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="NNN:NNN"):
            exb.load_antidote_tsv(p)

    def test_error_unknown_book(self, tmp_path):
        p = _pair_tsv(["孔雀粪\t碧灵丹\t不存在的书\t003:77\t注\t校定"], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="未知书名"):
            exb.load_antidote_tsv(p)

    def test_error_generic_poison(self, tmp_path):
        p = _pair_tsv(["毒酒\t千年芝草\t七剑下天山\t003:77\t注\t校定"], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="通名"):
            exb.load_antidote_tsv(p)

    def test_error_duplicate_evidence(self, tmp_path):
        p = _pair_tsv([self.ROW, self.ROW], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="重复"):
            exb.load_antidote_tsv(p)

    def test_error_inconsistent_note_within_pair(self, tmp_path):
        p = _pair_tsv([
            "孔雀粪\t碧灵丹\t七剑下天山\t003:77\t注记甲\t校定",
            "孔雀粪\t碧灵丹\t七剑下天山\t004:12\t注记乙\t校定",
        ], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="同组注记"):
            exb.load_antidote_tsv(p)

    def test_error_empty_note(self, tmp_path):
        p = _pair_tsv(["孔雀粪\t碧灵丹\t七剑下天山\t003:77\t\t校定"], tmp_path)
        with pytest.raises(exb.ManualsElixirsError, match="注记"):
            exb.load_antidote_tsv(p)


# ================================================================ 3. 丹药谱 negative_notes 列（负证据注记）
class TestNegativeNotesColumn:
    def test_bilindan_negative_notes(self):
        """碧灵丹负证据 2 项（裁定③）：皇帝毒酒无效 031:227 / 唐家暗器非对症 032:101、032:103
        ——书名=江湖三女侠（D13 汇报误写联剑，D16 复核修正）。"""
        rows, _ = exb.load_elixir_tsv()
        by = {r["name"]: r for r in rows}
        neg = by["碧灵丹"]["negative_notes"]
        assert [(n["desc"], [(x["book"], x["loc"]) for x in n["locs"]]) for n in neg] == [
            ("对皇帝毒酒无效", [("江湖三女侠", "031:227")]),
            ("对唐家暗器毒非对症", [("江湖三女侠", "032:101"),
                                    ("江湖三女侠", "032:103")]),
        ]

    def test_negative_notes_empty_elsewhere(self):
        rows, _ = exb.load_elixir_tsv()
        assert all(r["negative_notes"] == [] for r in rows if r["name"] != "碧灵丹")

    def test_error_bad_negative_note_format(self, tmp_path):
        p = _write_tsv(tmp_path, "丹药谱.tsv", ELIXIR_HEADER,
                       ["碧灵丹\t丹药\t\t联剑风云录\t联剑风云录·019:11\t解毒丹\t校定\t坏格式段——缺定位符式"])
        with pytest.raises(exb.ManualsElixirsError, match="negative_notes"):
            exb.load_elixir_tsv(p)


# ================================================================ 4. 五毒散↔消魂蚀骨散 互见（裁定④）
class TestWuduXiaohunCrossRef:
    def test_two_rows_distinct_with_mutual_notes(self):
        rows, _ = exb.load_elixir_tsv()
        by = {r["name"]: r for r in rows}
        assert {"五毒散", "消魂蚀骨散"} <= set(by)          # 两行分立
        w, x = by["五毒散"], by["消魂蚀骨散"]
        assert "消魂蚀骨散" in w["note"]                    # 注记互见
        assert "五毒散" in x["note"]
        assert (w["book"], w["loc"]) != (x["book"], x["loc"])   # 证据各异（锚点不同）
        for r in (w, x):                                    # 第二批口径收口：不再挂「待第二批」
            assert "待第二批" not in r["note"]


# ================================================================ 5. EX-6b 双向消费（合成口径）
def _pair_rows():
    rows, stats = exb.load_antidote_tsv()
    return [r for r in rows if r["status"] == "校定"], stats


class TestBuildBidirectional:
    def _build(self, tmp_path, monkeypatch, pairs):
        p = _write_tsv(tmp_path, "丹药谱.tsv", ELIXIR_HEADER, [
            "碧灵丹\t丹药\t\t联剑风云录\t联剑风云录·019:11\t解毒丹\t校定\t",
            "小还丹\t丹药\t\t白发魔女传\t白发魔女传·009:16\t保元丹\t校定\t",
            "天山雪莲\t药材\t\t联剑风云录\t联剑风云录·032:3\t主料\t校定\t",
            "鹤顶红\t药材\t\t七剑下天山\t七剑下天山·003:38\t剧毒\t校定\t",
            "易容丹\t丹药\t\t七剑下天山\t七剑下天山·026:25\t易容\t校定\t",
        ])
        rows, stats = exb.load_elixir_tsv(p)
        _fake_scan(monkeypatch, {
            "碧灵丹": [("联剑风云录", "019:11")],
            "小还丹": [("白发魔女传", "009:16")],
            "天山雪莲": [("联剑风云录", "032:3")],
            "鹤顶红": [("七剑下天山", "003:38")],
            "易容丹": [("七剑下天山", "026:25")],
        })
        return exb.build_spectrum(rows, stats, SCOPE_7,
                                  _conc(("碧灵丹", [("联剑风云录", 5)]),
                                        ("小还丹", [("白发魔女传", 3)]),
                                        ("天山雪莲", [("联剑风云录", 2)]),
                                        ("鹤顶红", [("七剑下天山", 1)])),
                                  scan_books=[], spectrum="elixirs", pairs=pairs)

    def test_antidote_to_attached(self, tmp_path, monkeypatch):
        pairs, _ = _pair_rows()
        payload = self._build(tmp_path, monkeypatch, pairs)
        by = {r["name"]: r for r in payload["elixirs"]}
        g = {x["poison"]: x for x in by["碧灵丹"]["antidote_to"]}
        assert set(g) == {"孔雀粪", "鹤顶红", "九阳毒掌(掌毒)"}
        assert g["孔雀粪"]["locs"] == [{"book": "七剑下天山", "loc": "003:77"}]
        assert g["九阳毒掌(掌毒)"]["note"]
        # 负证据随底表流转（本合成 fixture 未写负证据 → []）
        assert by["易容丹"]["antidote_to"] == []            # 无配对 → 恒空键
        assert by["易容丹"]["antidoted_by"] == []
        assert by["易容丹"]["negative_notes"] == []

    def test_antidoted_by_reverse_direction(self, tmp_path, monkeypatch):
        pairs, _ = _pair_rows()
        payload = self._build(tmp_path, monkeypatch, pairs)
        by = {r["name"]: r for r in payload["elixirs"]}
        rev = {x["antidote"]: x for x in by["鹤顶红"]["antidoted_by"]}
        assert set(rev) == {"碧灵丹", "长白山人参", "天山雪莲", "曼陀罗花"}
        assert rev["天山雪莲"]["locs"] == [{"book": "七剑下天山", "loc": "003:77"},
                                           {"book": "冰魄寒光剑", "loc": "008:5"}]
        assert by["碧灵丹"]["antidoted_by"] == []           # 碧灵丹非毒物

    def test_alias_resolves_to_canonical(self, tmp_path, monkeypatch):
        """配对解药列写别名（少阳小还丹）时归并到正名记录（互链不断）。"""
        rows, stats = exb.load_antidote_tsv()
        pairs = [dict(r, antidote="少阳小还丹") if r["antidote"] == "小还丹" else r
                 for r in rows if r["status"] == "校定"]
        p = _write_tsv(tmp_path, "丹药谱.tsv", ELIXIR_HEADER, [
            "小还丹\t丹药\t少阳小还丹\t白发魔女传\t白发魔女传·009:16\t保元丹\t校定\t",
        ])
        rows_e, stats_e = exb.load_elixir_tsv(p)
        _fake_scan(monkeypatch, {"小还丹": [("白发魔女传", "009:16")]})
        payload = exb.build_spectrum(rows_e, stats_e, SCOPE_7,
                                     _conc(("小还丹", [("白发魔女传", 3)])),
                                     scan_books=[], spectrum="elixirs", pairs=pairs)
        rec = payload["elixirs"][0]
        assert [g["poison"] for g in rec["antidote_to"]] == ["阴风毒砂掌(掌毒)"]

    def test_legacy_placeholder_keys_removed(self, tmp_path, monkeypatch):
        pairs, _ = _pair_rows()
        payload = self._build(tmp_path, monkeypatch, pairs)
        for r in payload["elixirs"]:
            assert "poison" not in r and "antidote" not in r   # D16 契约演进：null 占位键移除
        assert payload["meta"]["totals"]["毒解配对"] == 15      # D16 14 组 + F4 玉匣解药组
        assert any("毒解配对" in g for g in payload["meta"]["field_gaps"])


# ================================================================ 6. 真底表 × 真语料集成
class TestRealIntegration:
    def test_real_scope_build_pairing(self):
        rows, stats = exb.load_elixir_tsv()
        calib = [r for r in rows if r["status"] == "校定"]
        pairs, _ = _pair_rows()
        conc = exb.load_concordance(SCOPE_7["books"])
        payload = exb.build_spectrum(calib, stats, SCOPE_7, conc,
                                     scan_books=exb.tagged_book_dirs(),
                                     spectrum="elixirs", pairs=pairs)
        by = {r["name"]: r for r in payload["elixirs"]}
        assert payload["meta"]["totals"]["毒解配对"] == 15      # D16 14 组 + F4 玉匣解药组
        # 碧灵丹：可解 3 毒 + 负证据 2 项（F4 新组解药=玉匣解药，碧灵丹「可解」清单不变）
        assert sorted(g["poison"] for g in by["碧灵丹"]["antidote_to"]) == \
            ["九阳毒掌(掌毒)", "孔雀粪", "鹤顶红"]
        locs_bilin = {(x["book"], x["loc"]) for g in by["碧灵丹"]["antidote_to"]
                      for x in g["locs"]}
        assert {("七剑下天山", "003:77"), ("联剑风云录", "027:65")} <= locs_bilin
        assert len(by["碧灵丹"]["negative_notes"]) == 2
        # 天山雪莲：可解 5 毒（含 蛇焰箭/孔雀胆/修罗阴煞功(功毒)——毒物实体 F3 已入谱互链）
        assert sorted(g["poison"] for g in by["天山雪莲"]["antidote_to"]) == \
            ["修罗阴煞功(功毒)", "孔雀粪", "孔雀胆", "蛇焰箭", "鹤顶红"]
        snake = next(g for g in by["天山雪莲"]["antidote_to"] if g["poison"] == "蛇焰箭")
        assert snake["locs"] == [{"book": "七剑下天山", "loc": "005:23"}]
        # 小还丹：可解 阴风毒砂掌(掌毒)，2 定位符
        xhd = by["小还丹"]["antidote_to"]
        assert [g["poison"] for g in xhd] == ["阴风毒砂掌(掌毒)"]
        assert [(x["book"], x["loc"]) for x in xhd[0]["locs"]] == \
            [("白发魔女传", "010:67"), ("白发魔女传", "010:69")]
        # 少还丹：可解 七煞白眉针，3 定位符
        shd = by["少还丹"]["antidote_to"]
        assert [g["poison"] for g in shd] == ["七煞白眉针"]
        assert len(shd[0]["locs"]) == 3
        # 鹤顶红（谱内毒物实体）：antidoted_by 4 解药双向互挂
        assert sorted(g["antidote"] for g in by["鹤顶红"]["antidoted_by"]) == \
            ["天山雪莲", "曼陀罗花", "碧灵丹", "长白山人参"]
        # 其余丹药三键恒空
        assert by["易容丹"]["antidote_to"] == [] and by["易容丹"]["antidoted_by"] == []
        # meta.field_gaps：D16 通名毒不配对口径 + F3 毒物实体已入谱（双向互链）声明
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "通名" in gaps and "毒物名物已入谱" in gaps
