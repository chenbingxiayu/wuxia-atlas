# -*- coding: utf-8 -*-
"""F6 · 断玉剑 24:15 归属修正（chain_move/chain_drop 指令通道）测试（用户裁定，2026-11-12）。

背景（任务 F6）：江湖三女侠 24:15 明文「车辟邪手上拿着的正是唐晓澜那把游龙宝剑……冯瑛一见便认得，
所以才会硬抢了车辟邪的剑」——该段被夺之剑实指游龙剑（唐晓澜名下）。断玉剑 chain 边
（冯瑛→夺→车辟邪@24:15）方向正确但 weapon 归属错：修正方式=神兵表-补录.tsv 通道扩展（新增 cmd
指令列 chain_move:<目标器>/chain_drop），把该边从断玉剑迁至游龙剑（游龙剑无 24:15 边 → move 非
merge）；边本体（verb/persons/book/loc/conf）原样迁移，dir 由名物流转方向.tsv 24:15 行（F6 同步
改挂游龙剑）在注入阶段命中迁移后的边。

被测对象：scripts/export_site_sects_weapons_arts.py F6 新增
  load_weapon_supplement(path)  cmd 列扩展：空=holders 补录（原语义）/ chain_move:<目标器>/
                                chain_drop；chain 行 holders_add 必空、note 必填；词表外/
                                缺目标/混用 → WeaponSupError
  apply_chain_instructions(recs, rows, …)  指令应用（rev17 之前，编年/去重/毁证伪/end_state
                                看到迁移后 chain；全量口径同样应用——归属修正非呈现增强，不受
                                方案 R6 门槛）：move=源链删边+目标链追加（边本体原样）；
                                目标器已有完全同边 → 追加为重复边、scope 口径 rev17 dedupe
                                合并 ×n（全量口径维持重复边现状，与 R6 同门）；
                                无匹配边/指令涉及器无记录 → 跳过并记账（不伪造边、不丢源边）
  build_weapons(…, weapon_sup=…)  接线：chain 指令先于 rev17/方向注入应用；meta 记账

口径固化（测试即规范）：
  - chain_move 只迁移边本体；频次 count/books（concordance 口径）不动。
  - 目标器已有完全同边 → 重复边 dedupe 合并 ×n；同 loc 异 verb/persons → 各自成边（14:25 双边先例）。
  - 目标器无记录 → 不落边、源链不动（防丢边），no_weapon 记账。
"""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_sects_weapons_arts as exs  # noqa: E402

BOOK_A, BOOK_B = "编年书甲", "编年书乙"
SCOPE_AB = {"profile": "demo", "books": [BOOK_A, BOOK_B]}


# ================================================================ fixtures
def _edge(verb, persons, book, loc, conf="strong"):
    return {"verb": verb, "persons": list(persons), "book": book, "loc": loc, "conf": conf}


def _art(chain, books, holders=None, canonical="断玉剑"):
    return {
        "canonical": canonical, "kind": "剑", "level": "名物", "grade": "名物",
        "grade_basis": "明文", "conf": "ok", "status": "auto",
        "chain": list(chain),
        "holders": holders or [], "borrowers": [], "makers": [],
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


def _move_row(weapon="断玉剑", target="游龙剑", book=BOOK_A, loc="24:15", note="考订注记"):
    return {"kind": "chain_move", "weapon": weapon, "target": target,
            "book": book, "loc": loc, "note": note}


def _drop_row(weapon="断玉剑", book=BOOK_A, loc="24:15", note="考订注记"):
    return {"kind": "chain_drop", "weapon": weapon, "book": book, "loc": loc, "note": note}


def _build(art, sup, scope=SCOPE_AB):
    payload, _st = exs.build_weapons(_src([art]), scope=scope, weapon_sup=sup)
    return payload, (payload["weapons"][0] if payload["weapons"] else None)


# ================================================================ 1. apply_chain_instructions（合成链）
class TestApplyChainInstructions:
    def test_move_edge_between_records(self):
        """move：源链删边、目标链追加，边本体（verb/persons/book/loc/conf）原样
        （scope 口径 rev17 dedupe 对全部边补 n=1 基线）。"""
        art_d = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "24:15")], books={BOOK_A: [24]})
        art_y = _art([_edge("夺", ["凌未风", "楚昭南"], BOOK_A, "5:7")],
                     books={BOOK_A: [5]}, canonical="游龙剑")
        payload, _rec = exs.build_weapons(_src([art_d, art_y]), scope=SCOPE_AB,
                                          weapon_sup=[_move_row()])
        by = {w["canonical"]: w for w in payload["weapons"]}
        assert [e["loc"] for e in by["断玉剑"]["chain"]] == []          # 源链边已迁出
        moved = [e for e in by["游龙剑"]["chain"] if e["loc"] == "24:15"]
        assert len(moved) == 1
        assert moved[0] == {"verb": "夺", "persons": ["冯瑛", "车辟邪"],
                            "book": BOOK_A, "loc": "24:15", "conf": "strong", "n": 1}
        assert payload["meta"]["totals"]["chain_move"] == 1

    def test_move_merged_when_target_has_same_edge(self):
        """目标器已有完全同边（同 loc/verb/persons）→ 追加为重复边、rev17 dedupe 合并 ×n，
        不产生重复边（14:25 双边先例不适用：那是异 persons 边各自成边）。"""
        art_d = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "24:15")], books={BOOK_A: [24]})
        art_y = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "24:15")],
                     books={BOOK_A: [24]}, canonical="游龙剑")
        payload, _rec = exs.build_weapons(_src([art_d, art_y]), scope=SCOPE_AB,
                                          weapon_sup=[_move_row()])
        by = {w["canonical"]: w for w in payload["weapons"]}
        assert [e["loc"] for e in by["断玉剑"]["chain"]] == []
        tgt_edges = [e for e in by["游龙剑"]["chain"] if e["loc"] == "24:15"]
        assert len(tgt_edges) == 1 and tgt_edges[0].get("n") == 2      # 完全重复边合并 ×n
        assert payload["meta"]["totals"]["chain_move"] == 1

    def test_move_takes_all_duplicate_source_instances(self):
        """源链同边存在多个完全重复实例（神兵表扫描重复边，rev17 dedupe 前态）→ 迁移覆盖
        全部实例：源链清零、目标 dedupe 后 n=2（真实断玉剑 24:15 原始链即此形态）。"""
        art_d = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "24:15"),
                      _edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "24:15")], books={BOOK_A: [24]})
        art_y = _art([], books={BOOK_A: [24]}, canonical="游龙剑")
        payload, _rec = exs.build_weapons(_src([art_d, art_y]), scope=SCOPE_AB,
                                          weapon_sup=[_move_row()])
        by = {w["canonical"]: w for w in payload["weapons"]}
        assert by["断玉剑"]["chain"] == []
        tgt = [e for e in by["游龙剑"]["chain"] if e["loc"] == "24:15"]
        assert len(tgt) == 1 and tgt[0].get("n") == 2
        assert payload["meta"]["totals"]["chain_move"] == 1

    def test_move_keeps_distinct_edge_at_same_loc(self):
        """同 loc 异 verb/persons → 各自成边（14:25 双边先例），不合并。"""
        art_d = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "24:15")], books={BOOK_A: [24]})
        art_y = _art([_edge("赠", ["易兰珠", "车辟邪"], BOOK_A, "24:15")],
                     books={BOOK_A: [24]}, canonical="游龙剑")
        payload, _rec = exs.build_weapons(_src([art_d, art_y]), scope=SCOPE_AB,
                                          weapon_sup=[_move_row()])
        by = {w["canonical"]: w for w in payload["weapons"]}
        tgt = [e for e in by["游龙剑"]["chain"] if e["loc"] == "24:15"]
        assert {e["verb"] for e in tgt} == {"赠", "夺"}

    def test_chain_drop_removes_edge(self):
        """chain_drop：源链删边（无目标器）。"""
        art_d = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "24:15"),
                      _edge("赠", ["辛龙子", "杨云骢"], BOOK_A, "21:11")], books={BOOK_A: [21, 24]})
        payload, rec = _build(art_d, [_drop_row()])
        assert [e["loc"] for e in rec["chain"]] == ["21:11"]
        assert payload["meta"]["totals"]["chain_drop"] == 1

    def test_no_edge_and_no_weapon_accounted(self):
        """无匹配边 / 指令涉及器无 weapons 记录 → 跳过并记账；目标无记录时源边不丢（防丢边）。"""
        art_d = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "24:15")], books={BOOK_A: [24]})
        # ① 目标器不在 weapons → 源链保持原样
        payload, rec = _build(art_d, [_move_row(target="站外名物")])
        assert [e["loc"] for e in rec["chain"]] == ["24:15"]
        assert payload["meta"]["totals"].get("chain_move") in (0, None)
        assert "站外名物" in " ".join(payload["meta"]["field_gaps"])
        # ② 源边 loc 不存在 → no_edge 记账
        payload, rec = _build(art_d, [_move_row(loc="9:9")])
        assert [e["loc"] for e in rec["chain"]] == ["24:15"]
        assert "9:9" in " ".join(payload["meta"]["field_gaps"])

    def test_loc_zero_pad_normalized(self):
        """loc 归一比较：指令 24:15 命中 chain 024:15（parse_loc_pair 口径）。"""
        art_d = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "024:15")], books={BOOK_A: [24]})
        art_y = _art([], books={BOOK_A: [24]}, canonical="游龙剑")
        payload, _rec = exs.build_weapons(_src([art_d, art_y]), scope=SCOPE_AB,
                                          weapon_sup=[_move_row(loc="24:15")])
        by = {w["canonical"]: w for w in payload["weapons"]}
        assert [e["loc"] for e in by["游龙剑"]["chain"]] == ["024:15"]
        assert by["断玉剑"]["chain"] == []


# ================================================================ 2. build_weapons 接线（rev17/方向注入次序）
class TestBuildWiring:
    def test_move_precedes_rev17_and_direction(self):
        """指令先于 rev17（编年排序）/方向注入应用：迁移边在目标链内按编年归位，
        方向 TSV（改挂游龙剑的 24:15 行）命中迁移后的边 → dir 随边迁移。"""
        art_d = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_B, "24:15")], books={BOOK_B: [24]})
        art_y = _art([_edge("夺", ["凌未风", "楚昭南"], BOOK_A, "5:7")],
                     books={BOOK_A: [5]}, canonical="游龙剑")
        direction_sup = [{"weapon": "游龙剑", "verb": "夺", "from": "冯瑛", "to": "车辟邪",
                          "book": BOOK_B, "loc": "24:15", "note": ""}]
        payload, _rec = exs.build_weapons(_src([art_d, art_y]), scope=SCOPE_AB,
                                          weapon_sup=[_move_row(book=BOOK_B)],
                                          direction_sup=direction_sup)
        by = {w["canonical"]: w for w in payload["weapons"]}
        assert all(e["loc"] != "24:15" for e in by["断玉剑"]["chain"])
        moved = [e for e in by["游龙剑"]["chain"] if e["loc"] == "24:15"][0]
        assert moved["dir"] == {"kind": "夺", "who": ["冯瑛", "车辟邪"]}   # dir 随边迁移
        # 编年归位：BOOK_A(序0) 边在前、BOOK_B(序1) 迁入边在后
        assert [e["book"] for e in by["游龙剑"]["chain"]] == [BOOK_A, BOOK_B]

    def test_full_caliber_move_applies(self):
        """全量口径（scope=None）同样应用 chain 指令（归属修正非呈现增强，不受 R6 门槛）；
        方向注入仍不启用（与 rev17 同门）。"""
        art_d = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "24:15")], books={BOOK_A: [24]})
        art_y = _art([], books={BOOK_A: [24]}, canonical="游龙剑")
        payload, _rec = exs.build_weapons(_src([art_d, art_y]), scope=None,
                                          weapon_sup=[_move_row()],
                                          direction_sup=[])
        by = {w["canonical"]: w for w in payload["weapons"]}
        assert [e["loc"] for e in by["游龙剑"]["chain"]] == ["24:15"]
        assert by["断玉剑"]["chain"] == []
        assert payload["meta"]["totals"]["chain_move"] == 1

    def test_meta_gap_declares_channel(self):
        """meta.field_gaps 声明 F6 通道口径；note 不入站数据。"""
        art_d = _art([_edge("夺", ["冯瑛", "车辟邪"], BOOK_A, "24:15")], books={BOOK_A: [24]})
        art_y = _art([], books={BOOK_A: [24]}, canonical="游龙剑")
        row = _move_row(note="考订依据注记留档（不入站）")
        payload, _rec = exs.build_weapons(_src([art_d, art_y]), scope=SCOPE_AB,
                                          weapon_sup=[row])
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "chain_move" in gaps and "神兵表-补录.tsv" in gaps
        assert "考订依据注记留档" not in repr(payload)


# ================================================================ 3. 真实 TSV × 真实 loc 键
class TestRealF6Row:
    def test_real_row_moves_edge_on_real_loc(self):
        """真实 F6 行（断玉剑→游龙剑·江湖三女侠 24:15）× 合成双边链：边迁移、
        D17b 方向表（真实 TSV，24:15 行已改挂游龙剑）注入迁移后边。"""
        chain_d = [_edge("夺", ["冯瑛", "车辟邪", "唐晓澜"], "江湖三女侠", "24:15"),
                   _edge("传", ["晦明禅师", "杨云骢"], "七剑下天山", "14:25")]
        chain_y = [_edge("夺", ["凌未风", "楚昭南"], "七剑下天山", "5:7")]
        src = _src([_art(chain_d, {"江湖三女侠": [24], "七剑下天山": [14]}),
                    _art(chain_y, {"七剑下天山": [5]}, canonical="游龙剑")])
        payload, _st = exs.build_weapons(src, scope={"profile": "demo", "books": [
            "白发魔女传", "塞外奇侠传", "七剑下天山", "江湖三女侠"]})
        by = {w["canonical"]: w for w in payload["weapons"]}
        # 断玉剑：24:15 边消失（14:25 传边保留）；游龙剑：24:15 边出现且带 dir（方向随边迁移）
        assert all(e["loc"] != "24:15" for e in by["断玉剑"]["chain"])
        assert [e["loc"] for e in by["断玉剑"]["chain"]] == ["14:25"]
        moved = [e for e in by["游龙剑"]["chain"] if e["loc"] == "24:15"][0]
        assert moved["persons"] == ["冯瑛", "车辟邪", "唐晓澜"]
        assert moved["dir"] == {"kind": "夺", "who": ["冯瑛", "车辟邪"]}
        assert payload["meta"]["totals"]["chain_move"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
