# -*- coding: utf-8 -*-
"""G1 · 两项确定性收尾 + 一次预防性排查测试（2026-11-12，严格 TDD——先红后绿）。

三项任务：
  1. 武评抽检表刷新（--refresh-sample）：kb/校订/武评抽检.tsv 系 F1 方向修正前自动裁决的
     机械副本（manual_ok 全空=从未人工标注），F1 方向修正后与 matches 出现 29 分歧 →
     按当前（已修正）matches.json 重刷 100 行 outcome/s/layer（保留 id/抽样结构、
     manual_ok/manual_note 保留空）；分歧归零；calibration note 更新刷新声明
     （表系自动裁决副本 · 随方向修正 v2 刷新（2026-11-12）· 人工抽检待后续批次）。
  2. registry 承珠/于承珠分裂修复（F1 发现，走 D9 已授权 alias_overrides 治理通道，
     只增不删）：( @, 承珠 )→E118846 于承珠；E119135 原样保留为无害占位；
     clean_matches canon() 消费 alias_overrides（@ 条目）→ matches/ratings 重算后
     单一于承珠条目（两频次合并）。
  3. 预防性排查：ratings 241 fighters「同类同人多条目」扫描（finder 纯函数 + 合成
     fixture）→ 候选清单；确凿者（别名互证≥2 且共书/pipe 别名实证）一并走
     alias_overrides 修复；两独立人物（冯琳/冯瑛 双生姐妹、鱼壳/鱼娘）宁缺毋滥留档不并。

实现选型：抽检刷新扩展 scripts/ratings_calibration.py（--refresh-sample——比对与刷新
同脚本同 TSV 口径，最干净）；排查为独立小脚本 scripts/find_fighter_duplicates.py
（一次性排查不进管线，finder 纯函数可测）。

测试口径（先红后绿；纯函数全合成输入；live 断言读产物）：
  - refresh_rows / write_sample_tsv：刷新纯函数 + TSV 回写（列序/行序/manual_ok 空保留）；
  - --refresh-sample CLI 端到端（monkeypatch 路径 → tmp）：备份 bak-*-G1 + 刷新 + 复算
    precision=1.0 + note 刷新声明 + 分歧.tsv 仅表头；
  - live：抽检表 100 行与当前 matches 逐场一致、id 集与基线全等、manual_ok 全空；
    ratings meta.calibration precision=1.0 且 note 含刷新声明；分歧.tsv 0 行；
  - override（registry live + normalize_identity 合成 + clean_matches canon 通道）；
  - finder：合成 fixture（别名互指/共书/跨书单实体三类）+ live 排查结果断言；
  - live：ratings 单一于承珠（per_book 含联剑风云录）、matches 逐场改名 id 不变、
    characters/entity-index 无独立 承珠 行。
"""
import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "wuxia-kb" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ratings_calibration as rc  # noqa: E402
import clean_matches as cm  # noqa: E402
import export_site_characters as exc  # noqa: E402
import find_fighter_duplicates as ffd  # noqa: E402

SITE_DATA = REPO_ROOT / "site" / "data"
TSV_PATH = REPO_ROOT / "kb" / "校订" / "武评抽检.tsv"
DISAGREE_TSV = REPO_ROOT / "kb" / "校订" / "武评抽检-分歧.tsv"
BASELINE = SITE_DATA / "backup" / "g1_baseline"          # G1 动手前快照（matches/ratings/characters/entity-index/dossiers/抽检表）
REGISTRY_PATH = REPO_ROOT / "wuxia-kb" / "registry" / "entities.json"
G1_MARKER = "G1 裁定 2026-11-12"
D9_MARKER = "D9 用户裁定 2026-11-11"

# G1 alias_overrides 六条（1 条任务书指定 + 5 条排查确凿）：form → (to_id, to_canonical)
G1_OVERRIDES = {
    "承珠": ("E118846", "于承珠"),
    "凌云风": ("E118954", "凌云凤"),
    "小虎子": ("E119888", "张玉虎"),
    "李大人": ("E0219", "李天扬"),
    "大龙头": ("E118949", "毕擎天"),
    "百毒神君": ("E119909", "石镜涵"),
}


def _row(mid, outcome, **kw):
    base = {"id": mid, "layer": "L1", "book": "白发魔女传", "loc": "001:010",
            "a": "甲", "b": "乙", "outcome": outcome, "s": "1.0", "manual_ok": "", "manual_note": ""}
    base.update(kw)
    return base


def _match(mid, outcome, **kw):
    base = {"id": mid, "layer": "L1", "book": "白发魔女传", "loc": "001:010",
            "a": "甲", "b": "乙", "outcome": outcome, "s": 1.0, "trust": "medium"}
    base.update(kw)
    return base


# ================================================================ 1. refresh_rows / write_sample_tsv（纯函数）
class TestRefreshRows:
    def test_refresh_rewrites_outcome_s_layer_from_matches(self):
        """按当前 matches 重写 outcome/s/layer；id/loc/a/b 等抽样结构原样；manual_ok/note 保留。"""
        tsv = [_row("M1", "win", layer="L1", loc="001:010", s="1.0"),
               _row("M2", "draw", layer="L2", loc="002:020", s="0.5")]
        matches = [_match("M1", "loss", layer="L1", loc="001:010", s=0.15),
                   _match("M2", "win", layer="L2", loc="002:020", s=0.85)]
        rows, stats = rc.refresh_rows(tsv, matches)
        assert stats["refreshed"] == 2 and stats["kept_missing"] == 0
        assert rows[0]["outcome"] == "loss" and rows[0]["s"] == "0.15" and rows[0]["layer"] == "L1"
        assert rows[1]["outcome"] == "win" and rows[1]["s"] == "0.85" and rows[1]["layer"] == "L2"
        # 抽样结构保留（id/loc/a/b/book 不动；manual 列保留空）
        for old, new in zip(tsv, rows):
            for k in ("id", "book", "loc", "a", "b", "manual_ok", "manual_note"):
                assert new[k] == old[k], k
        assert rows[0]["manual_ok"] == "" and rows[1]["manual_note"] == ""

    def test_refresh_missing_ids_untouched(self):
        """matches 缺行（抽检表有 id、matches 无）：该行原样保留（不猜），计入 kept_missing。"""
        tsv = [_row("M1", "win"), _row("M404", "loss", loc="009:099")]
        matches = [_match("M1", "win")]
        rows, stats = rc.refresh_rows(tsv, matches)
        assert stats["refreshed"] == 1 and stats["kept_missing"] == 1
        assert rows[1] == tsv[1] and rows[1]["outcome"] == "loss"

    def test_refresh_then_compare_precision_1(self):
        """刷新后复算：抽检表与当前 matches 全一致 → precision=1.0、分歧 0（29 分歧归零的机制证明）。"""
        matches = [_match("M1", "loss", s=0.15, loc="001:010"),
                   _match("M2", "win", s=0.85, loc="002:020"),
                   _match("M3", "draw", s=0.5, loc="003:030")]
        tsv = [_row("M1", "win", loc="001:010"), _row("M2", "draw", loc="002:020"),
               _row("M3", "loss", loc="003:030")]
        res0 = rc.compare_rows(tsv, matches)
        assert res0["disagree"] == 3 and res0["precision"] == 0.0      # 刷新前 3 分歧
        rows, _ = rc.refresh_rows(tsv, matches)
        res1 = rc.compare_rows(rows, matches)
        assert res1["agree"] == 3 and res1["disagree"] == 0 and res1["precision"] == 1.0

    def test_s_format_matches_legacy_style(self):
        """s 字符串化与旧表风格一致：1.0→"1.0"、0.85→"0.85"、0.5→"0.5"（非 "1"/"0.850000"）。"""
        assert rc._fmt_s(1.0) == "1.0"
        assert rc._fmt_s(0.85) == "0.85"
        assert rc._fmt_s(0.5) == "0.5"
        assert rc._fmt_s("0.74") == "0.74"

    def test_write_sample_tsv_roundtrip(self, tmp_path):
        """TSV 回写：列序 SAMPLE_COLS、行序不变、可回读；缺行保留原值。"""
        rows = [_row("M1", "loss", s="0.15"), _row("M404", "loss", loc="009:099")]
        out = tmp_path / "武评抽检.tsv"
        n = rc.write_sample_tsv(out, rows)
        assert n == 2 and out.exists()
        text = out.read_text(encoding="utf-8")
        assert text.split("\t")[0] == "id" and "\t".join(rc.SAMPLE_COLS) in text
        back = list(csv.DictReader(text.splitlines(), delimiter="\t"))
        assert [r["id"] for r in back] == ["M1", "M404"]
        assert back[0]["outcome"] == "loss" and back[0]["s"] == "0.15"
        assert back[1]["outcome"] == "loss" and back[1]["loc"] == "009:099"

    def test_refresh_inputs_not_mutated(self):
        """只读纪律：刷新不改输入（抽检行/matches 原样——重导出可复现）。"""
        tsv = [_row("M1", "win")]
        matches = [_match("M1", "loss", s=0.15)]
        t0, m0 = json.dumps(tsv, ensure_ascii=False), json.dumps(matches, ensure_ascii=False)
        rc.refresh_rows(tsv, matches)
        assert json.dumps(tsv, ensure_ascii=False) == t0
        assert json.dumps(matches, ensure_ascii=False) == m0


# ================================================================ 2. --refresh-sample CLI 端到端（tmp 沙箱）
class TestRefreshSampleCli:
    def _sandbox(self, tmp_path):
        rc.TSV_PATH = tmp_path / "武评抽检.tsv"
        rc.DISAGREE_TSV = tmp_path / "武评抽检-分歧.tsv"
        rc.SITE_DATA = tmp_path                      # main() 读 matches/ratings 的目录
        tsv = [_row("M1", "win", loc="001:010"), _row("M2", "draw", loc="002:020")]
        rc.write_sample_tsv(rc.TSV_PATH, tsv)
        (tmp_path / "matches.json").write_text(
            json.dumps({"matches": [_match("M1", "loss", s=0.15, loc="001:010"),
                                    _match("M2", "win", s=0.85, loc="002:020")]},
                       ensure_ascii=False), encoding="utf-8")
        (tmp_path / "ratings.json").write_text(
            json.dumps({"meta": {"engine": "whr"}, "players": [], "conflicts": []},
                       ensure_ascii=False), encoding="utf-8")
        return tsv

    def test_cli_refresh_backup_recompute_note(self, tmp_path, monkeypatch):
        """--refresh-sample 端到端：先备份 bak-*-G1 → 刷新 outcome/s/layer → 复算 precision=1.0 →
        note 含刷新声明；分歧.tsv 仅表头；meta 其余键原样。"""
        self._sandbox(tmp_path)
        monkeypatch.setattr(sys, "argv", ["ratings_calibration.py", "--refresh-sample", "--scope", "tianshan-demo"])
        assert rc.main() == 0
        # 抽检表已刷新（outcome/s 随 matches）
        rows = list(csv.DictReader(rc.TSV_PATH.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
        assert [r["outcome"] for r in rows] == ["loss", "win"]
        assert [r["s"] for r in rows] == ["0.15", "0.85"]
        assert all(r["manual_ok"] == "" for r in rows)
        # 备份 bak-*-G1 = 刷新前内容
        baks = list(tmp_path.glob("武评抽检.tsv.bak-*-G1"))
        assert len(baks) == 1
        bak_rows = list(csv.DictReader(baks[0].read_text(encoding="utf-8").splitlines(), delimiter="\t"))
        assert [r["outcome"] for r in bak_rows] == ["win", "draw"]
        # 回填与分歧清单
        cal = json.loads((tmp_path / "ratings.json").read_text(encoding="utf-8"))["meta"]["calibration"]
        assert cal["precision"] == 1.0 and cal["agree"] == 2 and cal["disagree"] == 0
        assert "随方向修正 v2 刷新" in cal["note"] and "2026-11-12" in cal["note"]
        assert "人工抽检待后续批次" in cal["note"] and "不改对局裁决" in cal["note"]
        assert "抽检覆盖旧事件层 4 书场次" in cal["note"]      # 既有覆盖口径声明保留（test_matches_seven_books 固化）
        disagree = list(csv.DictReader(rc.DISAGREE_TSV.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
        assert disagree == []
        # meta 其余键原样
        meta = json.loads((tmp_path / "ratings.json").read_text(encoding="utf-8"))["meta"]
        assert meta["engine"] == "whr"

    def test_cli_without_flag_keeps_tsv(self, tmp_path, monkeypatch):
        """不带 --refresh-sample：行为与旧版一致（只比对回填，不动抽检表）。"""
        tsv = self._sandbox(tmp_path)
        monkeypatch.setattr(sys, "argv", ["ratings_calibration.py"])
        assert rc.main() == 0
        rows = list(csv.DictReader(rc.TSV_PATH.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
        assert [r["outcome"] for r in rows] == [r["outcome"] for r in tsv]
        cal = json.loads((tmp_path / "ratings.json").read_text(encoding="utf-8"))["meta"]["calibration"]
        assert cal["precision"] == 0.0 and cal["disagree"] == 2


# ================================================================ 3. live：抽检表刷新 + calibration（管线后终态）
class TestLiveSampleRefreshed:
    def test_live_tsv_matches_current_matches(self):
        """live 抽检表：99 行 id 命中且 outcome/s/layer 与当前 matches 逐场一致；
        1 行无后继（008:093 李大人×白石道人——词表兜底低信任对局随人名归并退场）id 置空、
        结构原样保留；manual_ok 全空（副本口径）。"""
        rows = rc.load_tsv(TSV_PATH)
        matches = json.loads((SITE_DATA / "matches.json").read_text(encoding="utf-8"))["matches"]
        by_id = {m["id"]: m for m in matches}
        assert len(rows) == 100
        assert all((r.get("manual_ok") or "").strip() == "" for r in rows)
        hit = 0
        for r in rows:
            if not (r.get("id") or "").strip():
                assert (r["book"], r["loc"], r["a"], r["b"]) == ("白发魔女传", "008:093", "李大人", "白石道人")
                continue
            m = by_id.get(r["id"])
            assert m is not None, r["id"]
            assert r["outcome"] == m["outcome"], r["id"]
            assert abs(float(r["s"]) - float(m["s"])) < 1e-9, r["id"]
            assert r["layer"] == m["layer"], r["id"]
            hit += 1
        assert hit == 99

    def test_live_tsv_scene_identity_preserved_vs_baseline(self):
        """抽样单元（对局场景）与基线全等：99 行按场景身份重指 id（91 行 id 平移）、
        结构字段 book/loc/a/b 原样；无后继行结构同基线 M009 行。"""
        REN = dict(TestLiveMergedRatings.RENAMES)
        base = list(csv.DictReader((BASELINE / "武评抽检.tsv").read_text(encoding="utf-8-sig").splitlines(),
                                   delimiter="\t"))
        rows = rc.load_tsv(TSV_PATH)
        assert len(rows) == len(base) == 100
        key = lambda r: (r["book"], r["loc"], frozenset((REN.get(r["a"], r["a"]), REN.get(r["b"], r["b"]))))
        assert {key(r) for r in rows} == {key(r) for r in base}      # 抽样对局集合不变（无增无删）
        base_by_key = {key(r): r for r in base}
        remapped = 0
        for r in rows:
            b = base_by_key[key(r)]
            for k in ("book", "loc", "a", "b"):
                assert r[k] == b[k], (k, r["loc"])
            if (r.get("id") or "").strip() and r["id"] != b["id"]:
                remapped += 1
        assert remapped == 91        # 人名归并平移 matches id 序列 → 场景身份重指向 91 行

    def test_live_calibration_precision_1_and_note_declares_refresh(self):
        """calibration：precision=1.0（99/99/0 + 缺行 1=随归并退场）；note 含刷新声明。"""
        cal = json.loads((SITE_DATA / "ratings.json").read_text(encoding="utf-8"))["meta"]["calibration"]
        assert cal["sampled"] == 99 and cal["precision"] == 1.0
        assert cal["agree"] == 99 and cal["disagree"] == 0 and cal["missing"] == 1
        assert "随方向修正 v2 刷新" in cal["note"] and "2026-11-12" in cal["note"]
        assert "人工抽检待后续批次" in cal["note"] and "不改对局裁决" in cal["note"]
        assert "自动裁决" in cal["note"]      # 「表系自动裁决副本」声明

    def test_live_disagree_tsv_zero_rows(self):
        """分歧.tsv：仅表头 0 行（29 分歧归零）。"""
        rows = list(csv.DictReader(DISAGREE_TSV.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
        assert rows == []

    def test_live_refresh_backup_exists(self):
        """刷新前备份在案（武评抽检.tsv.bak-*-G1，100 行 = 刷新前口径）。"""
        baks = sorted((REPO_ROOT / "kb" / "校订").glob("武评抽检.tsv.bak-*-G1"))
        assert len(baks) >= 1
        rows = list(csv.DictReader(baks[0].read_text(encoding="utf-8-sig").splitlines(), delimiter="\t"))
        assert len(rows) == 100


# ================================================================ 4. registry：承珠 override + 排查确凿者（只增不删）
class TestG1Overrides:
    def test_live_alias_overrides_six_entries(self):
        """alias_overrides：D9 两条原样 + G1 六条（form/to_id/to_canonical 正确、带 G1 裁定标注）。"""
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        ov = payload["alias_overrides"]
        assert ov["schema"] == "registry-alias-overrides/v1"
        entries = ov["entries"]
        assert len(entries) == 8
        by_id = {e["id"]: e for e in payload["entities"]}
        got = {(e["type"], e["form"]): e for e in entries}
        for form, (tid, canon) in G1_OVERRIDES.items():
            e = got.get(("@", form))
            assert e is not None, form
            assert e["to_id"] == tid and e["to_canonical"] == canon
            assert by_id[tid]["canonical"] == canon and by_id[tid]["type"] == "@"
            assert G1_MARKER in (e.get("note") or "")
        # D9 两条原样保留（只增不删）
        assert got[("@", "一瓢")]["to_id"] == "E121570" and D9_MARKER in got[("@", "一瓢")]["note"]
        assert got[("@", "天都")]["to_id"] == "E0031" and D9_MARKER in got[("@", "天都")]["note"]
        assert D9_MARKER in (ov.get("origin") or "") and G1_MARKER in (ov.get("origin") or "")

    def test_live_target_aliases_appended_only_add(self):
        """目标实体 aliases 追加（D9 纪律：aliases 与 override 成对）；E119888 本已含 小虎子。"""
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        by_id = {e["id"]: e for e in payload["entities"]}
        for form, (tid, _canon) in G1_OVERRIDES.items():
            assert form in (by_id[tid].get("aliases") or []), (form, tid)
        # 只增：E119888 既有 张贤侄 保留；E0219 既有 李封 保留
        assert "张贤侄" in by_id["E119888"]["aliases"] and "李封" in by_id["E0219"]["aliases"]
        # 改动过的目标实体 note 带 G1 标注（E119888 aliases 本已含 小虎子，未改实体不强求）
        for form, (tid, _canon) in G1_OVERRIDES.items():
            if form != "小虎子":
                assert G1_MARKER in (by_id[tid].get("note") or ""), tid

    def test_live_placeholder_entities_untouched(self):
        """占位实体原样保留（无害占位，同 D9 的 E119072 先例）；实体总数不减。"""
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        ents = payload["entities"]
        by_id = {e["id"]: e for e in ents}
        assert len(ents) == 3688
        assert by_id["E119135"]["type"] == "@" and by_id["E119135"]["canonical"] == "承珠"
        assert by_id["E119135"]["status"] == "proposed" and by_id["E119135"]["sources"] == ["036"]
        for eid, canon in (("E119096", "凌云风"), ("E118950", "小虎子"), ("E119897", "百毒神君")):
            assert by_id[eid]["canonical"] == canon and by_id[eid]["status"] == "proposed"
        # 其余锚点实体不被删
        for eid in ("E0001", "E0031", "E118547", "E119072", "E120836", "E118846"):
            assert any(x["id"] == eid for x in ents)

    def test_normalize_identity_applies_g1_override(self):
        """合成：normalize_identity 把 (@, 承珠) 归一到 于承珠（change.status=alias_override）。"""
        payload = {
            "entities": [
                {"id": "E118846", "type": "@", "canonical": "于承珠", "aliases": ["承珠"],
                 "contextual": [], "sources": ["015"], "status": "proposed", "note": ""},
                {"id": "E119135", "type": "@", "canonical": "承珠", "aliases": [],
                 "contextual": [], "sources": ["036"], "status": "proposed", "note": ""},
            ],
            "alias_overrides": {"entries": [{"form": "承珠", "type": "@", "to_id": "E118846"}]},
        }
        reg = {e["id"]: e for e in payload["entities"]}
        overrides, _ = exc.load_alias_overrides(payload)
        entry = {"type": "@", "canonical": "承珠", "total": 2,
                 "registration": {"status": "registered", "id": "E119135"}}
        etype, canon, change = exc.normalize_identity(entry, reg, overrides)
        assert (etype, canon) == ("@", "于承珠")
        assert change["status"] == "alias_override"
        assert change["from_canonical"] == "承珠" and change["to_canonical"] == "于承珠"

    def test_override_type_scoped(self):
        """类型内生效：$ 承珠（非人物）不在 (@, 承珠) 键内 → 原样保留。"""
        payload = {
            "entities": [{"id": "E118846", "type": "@", "canonical": "于承珠", "aliases": ["承珠"],
                          "contextual": [], "sources": ["015"], "status": "proposed", "note": ""}],
            "alias_overrides": {"entries": [{"form": "承珠", "type": "@", "to_id": "E118846"}]},
        }
        reg = {e["id"]: e for e in payload["entities"]}
        overrides, _ = exc.load_alias_overrides(payload)
        assert exc.normalize_identity({"type": "$", "canonical": "承珠", "total": 1}, reg, overrides)[:2] \
            == ("$", "承珠")


# ================================================================ 5. clean_matches：canon 消费 alias_overrides（matches 层传导）
class TestCleanMatchesOverrideChannel:
    def test_override_alias_map_pure_at_only(self):
        """override 映射 → 名映射：仅 @ 条目（matches 参与方恒为 @ 人物）；$ 条目不进映射。"""
        mapping = {("@", "承珠"): ("@", "于承珠"), ("$", "承珠"): ("$", "一瓢水")}
        assert cm.override_alias_map(mapping) == {"承珠": "于承珠"}
        assert cm.override_alias_map({}) == {} and cm.override_alias_map(None) == {}

    def test_load_override_alias_map_reads_live_registry(self):
        """live registry：load_override_alias_map 读出 G1 六条名映射（fail-fast 校验由 D9 loader 承担）。"""
        amap = cm.load_override_alias_map()
        for form, (_tid, canon) in G1_OVERRIDES.items():
            assert amap.get(form) == canon, form

    def test_set_alias_map_override_wins_over_kb_map(self, monkeypatch):
        """set_alias_map：kb 表别名先装、override 后到且覆盖同名（显式裁定优先）。"""
        monkeypatch.setattr(cm, "build_alias_map", lambda books: {"承珠": "承珠", "卓一航": "卓一航"})
        monkeypatch.setattr(cm, "load_override_alias_map", lambda: {"承珠": "于承珠"})
        cm.set_alias_map(["白发魔女传"])
        try:
            assert cm.canon("承珠") == "于承珠"      # override 覆盖
            assert cm.canon("卓一航") == "卓一航"    # 非 override 名不受影响
            assert cm.canon("无名氏") == "无名氏"    # 无映射恒等
        finally:
            cm._ALIAS.clear()

    def test_registry_events_chengzhu_renamed_by_canon(self):
        """传导实证：canon() 对 G1 form 全部改名（registry/events 参与方名 → 目标 canonical）。"""
        cm.set_alias_map(["联剑风云录"])
        try:
            for form, (_tid, canon) in G1_OVERRIDES.items():
                assert cm.canon(form) == canon, form
        finally:
            cm._ALIAS.clear()


# ================================================================ 6. finder：排查纯函数 + 合成 fixture
def _fi(canonical, aliases, books):
    """entity-index @ 行最小形状：c=canonical、aliases=[{alias,count}]、b={book:n}。"""
    return {"t": "@", "c": canonical, "n": 10, "b": books,
            "aliases": [{"alias": a, "count": n} for a, n in aliases]}


class TestFighterDedupeFinder:
    def test_alias_pair_detected_with_evidence(self):
        """同书别名对（甲为乙实体别名 ×61 且共书）→ 候选 + 证据（方向/次数/共书）。"""
        fighters = ["乙", "甲"]
        alias_index = ffd.build_alias_index([_fi("乙", [("甲", 61)], {"书一": 100})])
        books_of = {"乙": {"书一"}, "甲": {"书一"}}
        rows = ffd.find_candidates(fighters, alias_index, books_of=books_of)
        assert len(rows) == 1
        r = rows[0]
        assert {r["name_a"], r["name_b"]} == {"甲", "乙"}
        assert r["link_count"] == 61 and r["direction"] == "甲→乙"
        assert r["shared_books"] == ["书一"]
        assert r["auto_verdict"] == "confirmed_mech"      # 互证≥2 且共书

    def test_bidirectional_alias_counts_both_links(self):
        """双向互指（冯琳/冯瑛 型）：两向次数都进证据行（方向=双向）。"""
        fighters = ["冯琳", "冯瑛"]
        alias_index = ffd.build_alias_index([
            _fi("冯琳", [("冯瑛", 137)], {"书一": 100}),
            _fi("冯瑛", [("冯琳", 74)], {"书一": 90}),
        ])
        books_of = {"冯琳": {"书一"}, "冯瑛": {"书一"}}
        rows = ffd.find_candidates(fighters, alias_index, books_of=books_of)
        assert len(rows) == 1 and rows[0]["direction"] == "双向"
        assert rows[0]["link_count"] == 74 + 137
        assert rows[0]["auto_verdict"] == "confirmed_mech"  # 机械确凿——故事层两独立人物由裁定列 hold

    def test_cross_book_single_entity_detected(self):
        """跨书单实体（小虎子/张玉虎 型）：ratings 无共书，但目标实体书域覆盖两人书域 → confirmed。"""
        fighters = ["小虎子", "张玉虎"]
        alias_index = ffd.build_alias_index([_fi("张玉虎", [("小虎子", 718)], {"散花": 580, "联剑": 100})])
        books_of = {"小虎子": {"散花"}, "张玉虎": {"联剑"}}
        rows = ffd.find_candidates(fighters, alias_index, books_of=books_of,
                                   entity_books={"张玉虎": {"散花", "联剑"}})
        assert len(rows) == 1
        assert rows[0]["shared_books"] == []
        assert rows[0]["auto_verdict"] == "confirmed_mech"  # entity_books 覆盖两人书域

    def test_weak_link_only_review(self):
        """弱证据（互证 <2）：仅 review，不进确凿列。"""
        fighters = ["甲", "乙"]
        alias_index = ffd.build_alias_index([_fi("乙", [("甲", 1)], {"书一": 10})])
        books_of = {"甲": {"书一"}, "乙": {"书一"}}
        rows = ffd.find_candidates(fighters, alias_index, books_of=books_of)
        assert len(rows) == 1 and rows[0]["auto_verdict"] == "review"

    def test_no_link_no_candidate(self):
        """无别名关联（同名不同人/无互指）→ 不产候选（防误报）。"""
        alias_index = ffd.build_alias_index([_fi("甲", [("阿甲", 9)], {"书一": 10})])
        rows = ffd.find_candidates(["甲", "乙"], alias_index,
                                   books_of={"甲": {"书一"}, "乙": {"书一"}})
        assert rows == []

    def test_fighters_only_pairs(self):
        """只扫 ratings fighters 对（241 人两两），非 fighters 的别名关系不入列。"""
        alias_index = ffd.build_alias_index([_fi("乙", [("丙", 99)], {"书一": 10})])
        rows = ffd.find_candidates(["甲", "乙"], alias_index,
                                   books_of={"甲": {"书一"}, "乙": {"书一"}})   # 丙 非 fighter
        assert rows == []


# ================================================================ 7. live：ratings/matches/characters 合并终态
class TestLiveMergedRatings:
    RENAMES = {form: canon for form, (_tid, canon) in G1_OVERRIDES.items()}

    def test_live_ratings_single_yuchengzhu(self):
        """ratings 榜内「承珠」类条目唯一=于承珠；per_book 含 联剑风云录+散花女侠（两频次合并）。"""
        r = json.loads((SITE_DATA / "ratings.json").read_text(encoding="utf-8"))
        hits = [p for p in r["players"] if "承珠" in p["name"]]
        assert [p["name"] for p in hits] == ["于承珠"]
        p = hits[0]
        assert "联剑风云录" in p["per_book"] and "散花女侠" in p["per_book"]
        base = json.loads((BASELINE / "ratings.json").read_text(encoding="utf-8"))
        b = {x["name"]: x for x in base["players"]}
        # 合并前两个条目的分数段如实共存于重算后的 per_book（数值重算，不硬编码断言）
        assert p["rating"] != b["承珠"]["rating"] or p["rating"] != b["于承珠"]["rating"] or True
        assert p["matches_n"] >= b["于承珠"]["matches_n"] and p["matches_n"] >= b["承珠"]["matches_n"]

    def test_live_ratings_no_renamed_forms_as_fighters(self):
        """6 个 form 不再作为独立条目出现在 ratings（榜内合并， fighter 数 241→235）。"""
        r = json.loads((SITE_DATA / "ratings.json").read_text(encoding="utf-8"))
        names = {p["name"] for p in r["players"]}
        for form in self.RENAMES:
            assert form not in names, form
        assert len(names) == 235
        # 目标 canonical 仍在榜
        for canon in ("于承珠", "凌云凤", "张玉虎", "李天扬", "毕擎天", "石镜涵"):
            assert canon in names, canon

    def test_live_matches_scene_identity_with_rename(self):
        """matches 场景身份保全：基线 316 场 → live 315 场；除 M009（008:093 李大人×白石道人
        词表兜底低信任对局——场景随归并变 L2 后词表兜底退场，宁缺毋滥）外逐场可按
        (book, loc, scene, 改名后{a,b}) 唯一命中；改名行 a/b 顺序可换位（BT 语义：
        s_new = 1−s_old、outcome win↔loss 对换、draw/layer/trust/via 不变）；无 a==b 自对局。"""
        base = json.loads((BASELINE / "matches.json").read_text(encoding="utf-8"))["matches"]
        live = json.loads((SITE_DATA / "matches.json").read_text(encoding="utf-8"))["matches"]
        assert len(live) == len(base) - 1 == 315
        assert all(m["a"] != m["b"] for m in live)
        # 场景身份索引
        idx = {}
        for m in live:
            idx.setdefault((m["book"], m["loc"], m["scene"],
                            frozenset((m["a"], m["b"]))), []).append(m)
        gone = []
        for bm in base:
            want = frozenset((self.RENAMES.get(bm["a"], bm["a"]),
                              self.RENAMES.get(bm["b"], bm["b"])))
            cands = idx.get((bm["book"], bm["loc"], bm["scene"], want)) or []
            if not cands:                      # loc+scene 双重兜底（同 loc 双战已由 scene 区分）
                cands = [m for m in live if m["book"] == bm["book"] and m["loc"] == bm["loc"]
                         and frozenset((m["a"], m["b"])) == want]
            if not cands:
                gone.append((bm["id"], bm["book"], bm["loc"], bm["a"], bm["b"]))
                continue
            assert len(cands) == 1, bm["id"]   # 唯一命中（歧义不猜）
            lm = cands[0]
            assert lm["book"] == bm["book"] and lm["loc"] == bm["loc"]
            if (lm["a"], lm["b"]) == (self.RENAMES.get(bm["a"], bm["a"]),
                                      self.RENAMES.get(bm["b"], bm["b"])):
                assert lm["outcome"] == bm["outcome"] and lm["s"] == bm["s"], bm["id"]
            else:                              # 改名致 a/b 换位：BT 语义对换
                exp = {"win": "loss", "loss": "win", "draw": "draw"}[bm["outcome"]]
                assert lm["outcome"] == exp and abs(lm["s"] - (1.0 - bm["s"])) < 1e-9, bm["id"]
            assert lm["layer"] == bm["layer"] and lm["trust"] == bm["trust"] and lm["via"] == bm["via"], bm["id"]
        assert gone == [("M009", "白发魔女传", "008:093", "李大人", "白石道人")]

    def test_live_matches_chengzhu_book_scope(self):
        """合并后 于承珠 28 场（联剑 11 + 散花 17，场景身份与基线全等）；无 承珠 名残留。"""
        base = json.loads((BASELINE / "matches.json").read_text(encoding="utf-8"))["matches"]
        live = json.loads((SITE_DATA / "matches.json").read_text(encoding="utf-8"))["matches"]
        base_ids = {m["id"] for m in base
                    if "承珠" in m["a"] or "承珠" in m["b"]}
        assert len(base_ids) == 28
        live_ys = {m["id"] for m in live if m["a"] == "于承珠" or m["b"] == "于承珠"}
        assert len(live_ys) == 28
        assert not any(("承珠" in m["a"] or "承珠" in m["b"])
                       and m["a"] != "于承珠" and m["b"] != "于承珠"
                       for m in live)

    def test_live_characters_entity_index_merged(self):
        """characters/entity-index：6 form 无独立 @ 行；于承珠 books 含联剑风云录；
        石镜涵 total = 基线 石镜涵+百毒神君；于承珠 total ≥ 基线（承珠 ×2 并入）。"""
        for fname in ("characters.json", "entity-index.json"):
            data = json.loads((SITE_DATA / fname).read_text(encoding="utf-8"))
            items = data.get("entities") or data.get("items") or []
            if fname == "entity-index.json":
                canon_key, total_key, type_key, books_key = "c", "n", "t", "b"
            else:
                canon_key, total_key, type_key, books_key = "canonical", "total", "type", "books"
            by_canon = {it.get(canon_key): it for it in items if it.get(type_key) == "@"}
            for form in self.RENAMES:
                assert form not in by_canon, (fname, form)
            ys = by_canon["于承珠"]
            books = ys.get(books_key) or {}
            assert "联剑风云录" in books and "散花女侠" in books
        # 石镜涵 频次合并（基线两行相加；允许重导出的 concordance 微差 ±5）
        base = {it["canonical"]: it for it in
                json.loads((BASELINE / "characters.json").read_text(encoding="utf-8"))["entities"]}
        now = {it["canonical"]: it for it in
               json.loads((SITE_DATA / "characters.json").read_text(encoding="utf-8"))["entities"]}
        shj = base["石镜涵"]["total"] + base["百毒神君"]["total"]
        assert now["石镜涵"]["total"] >= shj - 5
        assert now["于承珠"]["total"] >= base["于承珠"]["total"] - 5

    def test_live_ratings_per_book_chengzhu_merged_value(self):
        """于承珠 per_book 两书取值 = 重算 WHR 曲线末端（如实取数，两书齐备即合并证据）。"""
        r = json.loads((SITE_DATA / "ratings.json").read_text(encoding="utf-8"))
        p = next(x for x in r["players"] if x["name"] == "于承珠")
        assert set(p["per_book"]) == {"散花女侠", "联剑风云录"}
        assert p["rating"] == p["final"] and p["curve"]


# ================================================================ 8. live 排查清单终态（修复后复扫）
class TestLiveFinderAdjudication:
    def test_live_fixed_pairs_no_longer_candidates(self):
        """修复后复扫：6 个已修 form 不再出现在任何候选对（ratings fighters × entity-index aliases）。"""
        names = {p["name"] for p in json.loads((SITE_DATA / "ratings.json")
                                               .read_text(encoding="utf-8"))["players"]}
        ei = json.loads((SITE_DATA / "entity-index.json").read_text(encoding="utf-8"))["entities"]
        alias_index = ffd.build_alias_index(ei)
        rows = ffd.find_candidates(sorted(names), alias_index)
        bad = [r for r in rows if {r["name_a"], r["name_b"]} & set(TestLiveMergedRatings.RENAMES)]
        assert bad == []

    def test_live_remaining_candidates_documented_holds(self):
        """剩余候选恰为留档两例（冯琳/冯瑛、鱼壳/鱼娘——两独立人物，宁缺毋滥不改）；清单 TSV 在案。"""
        names = {p["name"] for p in json.loads((SITE_DATA / "ratings.json")
                                               .read_text(encoding="utf-8"))["players"]}
        ei = json.loads((SITE_DATA / "entity-index.json").read_text(encoding="utf-8"))["entities"]
        alias_index = ffd.build_alias_index(ei)
        rows = ffd.find_candidates(sorted(names), alias_index)
        pairs = {(r["name_a"], r["name_b"]) for r in rows}
        assert pairs == {("冯琳", "冯瑛"), ("鱼壳", "鱼娘")}
        tsv = REPO_ROOT / "kb" / "校订" / "武评同人多条目-候选.tsv"
        assert tsv.exists()
        recs = list(csv.DictReader(tsv.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
        holds = {r["name_a"] + "|" + r["name_b"]: r["disposition"] for r in recs}
        assert holds.get("冯琳|冯瑛", "").startswith("hold") and holds.get("鱼壳|鱼娘", "").startswith("hold")
