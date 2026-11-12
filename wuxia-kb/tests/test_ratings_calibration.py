# -*- coding: utf-8 -*-
"""W2-D4-B · 武评 calibration 回填测试（天山演示版总体方案 §4.3 C1「calibration 回填」/§5.5，2026-11-11）。

背景：site/data/ratings.json meta.calibration 长期是 {sampled: 0, precision: null, …待办} 骨架；
kb/校订/武评抽检.tsv 已有人工抽检 100 场（id/layer/book/loc/a/b/outcome/s/manual_ok/manual_note）。
本任务：比对抽检表 manual 结论 vs matches.json 自动裁决（同 id 对局 outcome 一致性）→
precision = 一致数 / 抽检数 → 回填 ratings.json meta.calibration={sampled, precision, disagree,
tsv 路径, note}；不一致清单写 kb/校订/武评抽检-分歧.tsv 供人工复核（只回填统计、不改对局裁决）。

实现位置选型（任务书二选一）：**独立脚本 scripts/ratings_calibration.py 在 ratings_whr 之后跑**
（ratings_whr 每次重跑都会以占位骨架覆盖 meta.calibration——回填若做进 ratings_whr 输出组装，
单跑 E2 时仍会被下次 E2 重算覆盖为骨架；独立脚本 + run_pipeline 步骤列表固化顺序才稳）。

测试口径（先红后绿；除「live 产物纪律」一节外全部合成输入，不写 site/data）：
  - compare_rows：outcome 一致性比对（一致/分歧/缺行三分）；缺行（抽检表有 id、matches 无）
    不入 precision 分母、单独计数报告；输入不被修改（不改对局裁决的函数级固化）。
  - build_calibration：回填字段结构（sampled/precision/agree/disagree/missing/tsv/disagree_tsv/note）。
  - write_disagree_tsv：分歧 TSV 生成（列含 manual_outcome/auto_outcome；0 分歧 = 仅表头）。
  - run_pipeline：ratings_calibration 步骤紧跟 ratings_whr（顺序即规范——E2 覆盖风险闭环）。
  - live 产物纪律：ratings.json meta.calibration 已回填（sampled=100、precision∈[0,1]、
    tsv 路径指向抽检表）；matches.json 对局 outcome 未被回填改动（同 id 重比对仍与 TSV 一致）。
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
import run_pipeline  # noqa: E402

SITE_DATA = REPO_ROOT / "site" / "data"
TSV_PATH = REPO_ROOT / "kb" / "校订" / "武评抽检.tsv"


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


# ================================================================ 1. compare_rows（一致率计算 + 缺行处理）
class TestCompareRows:
    def test_precision_agreement_ratio(self):
        """precision = outcome 一致数 / 抽检数（同 id 对局 outcome 一致性）。"""
        tsv = [_row("M1", "win"), _row("M2", "draw"), _row("M3", "loss"), _row("M4", "win"), _row("M5", "draw")]
        matches = [_match("M1", "win"), _match("M2", "draw"), _match("M3", "loss"),
                   _match("M4", "draw"), _match("M5", "win")]
        res = rc.compare_rows(tsv, matches)
        assert res["sampled"] == 5
        assert res["agree"] == 3 and res["disagree"] == 2
        assert res["precision"] == pytest.approx(3 / 5)
        assert {d["id"] for d in res["disagree_rows"]} == {"M4", "M5"}

    def test_outcome_vocabulary_normalized(self):
        """outcome 词表两侧同域（win/loss/draw）：字面比较，不做别名换算。"""
        res = rc.compare_rows([_row("M1", "win")], [_match("M1", "win")])
        assert res["precision"] == 1.0
        res2 = rc.compare_rows([_row("M1", "胜")], [_match("M1", "win")])
        assert res2["disagree"] == 1  # 抽检表词表外取值 = 分歧（交人工复核），不猜

    def test_missing_rows_excluded_from_denominator(self):
        """抽检表缺行（matches 无该 id）：不入 precision 分母，单独 missing 计数并列 id。"""
        tsv = [_row("M1", "win"), _row("M404", "loss"), _row("M405", "draw")]
        matches = [_match("M1", "win")]
        res = rc.compare_rows(tsv, matches)
        assert res["sampled"] == 1 and res["agree"] == 1 and res["precision"] == 1.0
        assert res["missing"] == 2 and set(res["missing_ids"]) == {"M404", "M405"}

    def test_inputs_not_mutated(self):
        """只读比对：抽检行与对局行输入不被修改（不改对局裁决的函数级固化）。"""
        tsv = [_row("M1", "win")]
        matches = [_match("M1", "loss")]
        tsv_snapshot = json.dumps(tsv, ensure_ascii=False)
        matches_snapshot = json.dumps(matches, ensure_ascii=False)
        rc.compare_rows(tsv, matches)
        assert json.dumps(tsv, ensure_ascii=False) == tsv_snapshot
        assert json.dumps(matches, ensure_ascii=False) == matches_snapshot

    def test_real_tsv_ids_all_in_scope_matches(self):
        """真实抽检表 100 行：99 行 id 命中 live matches.json（scope 口径对局集）；
        1 行无后继（008:093 李大人×白石道人，G1 人名归并后退场，id 置空）计 missing。"""
        tsv = rc.load_tsv(TSV_PATH)
        matches = json.loads((SITE_DATA / "matches.json").read_text(encoding="utf-8"))["matches"]
        res = rc.compare_rows(tsv, matches)
        assert len(tsv) == 100
        assert res["missing"] == 1
        assert res["sampled"] == 99


# ================================================================ 2. build_calibration（回填字段结构）
class TestBuildCalibration:
    def test_payload_structure(self):
        res = {"sampled": 98, "agree": 95, "disagree": 3, "missing": 2,
               "precision": 95 / 98, "disagree_rows": [], "missing_ids": ["x"]}
        cal = rc.build_calibration(res)
        assert cal["sampled"] == 98
        assert cal["precision"] == round(95 / 98, 4)  # 统一 4 位小数（compare_rows 已舍入，双保险）
        assert cal["agree"] == 95 and cal["disagree"] == 3 and cal["missing"] == 2
        assert cal["tsv"] == "kb/校订/武评抽检.tsv"
        assert cal["disagree_tsv"] == "kb/校订/武评抽检-分歧.tsv"
        assert isinstance(cal["note"], str) and "不改对局裁决" in cal["note"]

    def test_precision_rounded_4dp(self):
        res = {"sampled": 3, "agree": 1, "disagree": 2, "missing": 0,
               "precision": 1 / 3, "disagree_rows": [], "missing_ids": []}
        cal = rc.build_calibration(res)
        assert cal["precision"] == round(1 / 3, 4)

    def test_zero_sampled_guard(self):
        """抽检表缺失/空 → sampled=0、precision=None（骨架形态，不除零）。"""
        cal = rc.build_calibration({"sampled": 0, "agree": 0, "disagree": 0, "missing": 0,
                                    "precision": None, "disagree_rows": [], "missing_ids": []})
        assert cal["sampled"] == 0 and cal["precision"] is None

    def test_backfill_preserves_rest_of_meta(self):
        """回填只替换 meta.calibration，meta 其余键与 players/conflicts 原样保留。"""
        payload = {"meta": {"engine": "whr", "generated": "d1", "calibration": {"old": True}},
                   "players": [{"name": "凌未风"}], "conflicts": []}
        rc.backfill(payload, {"sampled": 100, "precision": 1.0})
        assert payload["meta"]["engine"] == "whr" and payload["meta"]["generated"] == "d1"
        assert payload["players"] == [{"name": "凌未风"}]
        assert payload["meta"]["calibration"]["sampled"] == 100


# ================================================================ 3. write_disagree_tsv（分歧清单生成）
class TestDisagreeTsv:
    def test_disagree_rows_written_with_manual_auto_columns(self, tmp_path):
        rows = [{"id": "M4", "layer": "L1", "book": "白发魔女传", "loc": "005:029",
                 "a": "白敏", "b": "金千岩", "manual_outcome": "win", "auto_outcome": "loss",
                 "s": "0.25", "manual_ok": "", "manual_note": ""}]
        out = tmp_path / "分歧.tsv"
        n = rc.write_disagree_tsv(out, rows)
        assert n == 1 and out.exists()
        text = out.read_text(encoding="utf-8")
        rdr = list(csv.DictReader(text.splitlines(), delimiter="\t"))
        assert len(rdr) == 1
        assert rdr[0]["manual_outcome"] == "win" and rdr[0]["auto_outcome"] == "loss"
        assert rdr[0]["id"] == "M4" and rdr[0]["a"] == "白敏"

    def test_zero_disagree_header_only(self, tmp_path):
        """0 分歧 → 仅表头文件（显式记录「零分歧」，非不产出）。"""
        out = tmp_path / "分歧.tsv"
        n = rc.write_disagree_tsv(out, [])
        assert n == 0
        rdr = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines(), delimiter="\t"))
        assert rdr == [] and "manual_outcome" in out.read_text(encoding="utf-8")


# ================================================================ 4. run_pipeline 顺序固化（回填在 E2 之后）
class TestPipelineOrder:
    def test_calibration_step_right_after_ratings_whr(self):
        """ratings_calibration 紧跟 ratings_whr：E2 每次重跑覆盖 meta.calibration 后必须重回填。"""
        cmds = run_pipeline.pipeline_commands()
        labels = [c["label"] for c in cmds]
        assert "ratings_calibration" in labels
        assert labels.index("ratings_calibration") == labels.index("ratings_whr") + 1

    def test_calibration_script_exists_and_receives_scope(self):
        cmds = run_pipeline.pipeline_commands(scope="tianshan-demo")
        step = next(c for c in cmds if c["label"] == "ratings_calibration")
        assert Path(step["argv"][1]).exists()
        assert "--scope" in step["argv"] and "tianshan-demo" in step["argv"]

    def test_build_hint_still_last(self):
        cmds = run_pipeline.pipeline_commands()
        assert cmds[-1]["argv"] is None  # 构建提示仍为末步且不代跑 astro


# ================================================================ 5. live 产物纪律（回填后 ratings.json）
class TestLiveCalibration:
    def test_live_ratings_calibration_backfilled(self):
        cal = json.loads((SITE_DATA / "ratings.json").read_text(encoding="utf-8"))["meta"]["calibration"]
        assert cal["sampled"] == 99        # G1：100 行中 1 场随人名归并退场（缺行不入分母）
        assert isinstance(cal["precision"], float) and 0.0 <= cal["precision"] <= 1.0
        assert cal["tsv"] == "kb/校订/武评抽检.tsv"
        assert cal["disagree_tsv"] == "kb/校订/武评抽检-分歧.tsv"
        assert isinstance(cal["note"], str) and cal["note"]

    def test_live_matches_adjudication_untouched(self):
        """回填不改对局裁决：live matches 同 id 重比对与抽检表结论的一致数 == calibration.agree。"""
        cal = json.loads((SITE_DATA / "ratings.json").read_text(encoding="utf-8"))["meta"]["calibration"]
        tsv = rc.load_tsv(TSV_PATH)
        matches = json.loads((SITE_DATA / "matches.json").read_text(encoding="utf-8"))["matches"]
        res = rc.compare_rows(tsv, matches)
        assert res["agree"] == cal["agree"] and res["disagree"] == cal["disagree"]
        assert res["sampled"] == cal["sampled"]

    def test_live_disagree_tsv_exists(self):
        assert (REPO_ROOT / "kb" / "校订" / "武评抽检-分歧.tsv").exists()
