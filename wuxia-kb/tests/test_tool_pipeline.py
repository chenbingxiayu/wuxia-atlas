# -*- coding: utf-8 -*-
"""W2-C1 · 工具 E 接 live + 管线顺序修正测试（天山演示版总体方案 §3.1 P0-2/§4.3 C1/§5.5，2026-11-09）。

只测纯函数与合成输入（同 W0-T3a/T3b 风格），不跑全管线、不写 site/data。
被测对象（W2-C1 改造/新增）：
  clean_matches                select_books / build_payload —— 书目 scope 过滤 + meta.scope 写入
  ratings_whr                  filter_matches / run_whr / build_payload —— 对局 scope 过滤 +
                               players legacy/v2 双键（rating/rd × final/uncertainty/curve/peak）
  audit_r1                     select_books / scan / build_payload —— 书目 scope 过滤 + meta.scope
  run_pipeline                 pipeline_commands —— §5.5 有序命令列表（编排顺序即规范）+
                               backup_site_data_files（--apply 前备份受影响 site/data 文件）
  export_site_matches_ratings  docstring + meta.note 的 legacy 中间层声明（EX-5 产物正式 live
                               由工具 E 覆盖——防部署序列再次踩踏）

口径固化（测试即规范）：
  - 全量口径（scope=None）行为与现状一致（方案 R6）：meta 无 scope 键、命令不带 --scope。
  - ratings players 必须双键齐备：legacy（rating/rd/tier/w-d-l/per_book/top_evidence——
    RatingExplorer/VersusTool 现行契约）+ v2（final/uncertainty/curve/peak——武评 v2 契约），
    final==rating、round(uncertainty)==rd。
  - 管线唯一顺序（§5.5）：clean_matches 在 export_site_all 之后（EX-5 不得后跑覆盖工具 E）；
    ratings_whr 在 clean_matches 之后（E2 读 E1 的 matches.json）；audit_r1 在 games 切片
    之前（killer 消费 audit-r1 passes）；build 提示恒为末步且不代跑 astro。
"""
import sys
from pathlib import Path

import pytest

# 被测模块：父仓 scripts/（工具 E/切片/编排）+ wuxia-kb/scripts/（EX 层/scope 基础设施）
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "wuxia-kb" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import export_site_common as esc  # noqa: E402
import clean_matches  # noqa: E402
import ratings_whr  # noqa: E402
import audit_r1  # noqa: E402
import run_pipeline  # noqa: E402
import export_site_matches_ratings as exm  # noqa: E402

SCOPE = esc.load_scope("tianshan-demo")            # 真实 profile（7 书）
BOOK_IN, BOOK_OUT = "白发魔女传", "萍踪侠影录"
SCOPE_ONE = {"profile": "demo", "books": [BOOK_IN]}  # 合成窄 profile（剔除语义用）


# ================================================================ 1. clean_matches（工具 E·E1）
def _log():
    return {"kept": {"L1": 2, "L2": 1, "L3": 0},
            "dropped": {"self_pair": 0, "no_verdict": 0, "group_label": 0, "in_quote": 0,
                        "dropped_events": 0},
            "transferred": {"org": 0}, "downgraded": {"attribution_fallback": 0},
            "scenes": {"count": 2, "max_persons": 2}, "wordlist_hit": {}}


class TestCleanMatchesScope:
    def test_select_books_scope_drops_out_book(self):
        """命中（scope 内书保留）/剔除（scope 外书裁掉）；顺序保持 BOOKS 编年（白发→塞外→七剑→江湖）。"""
        books = clean_matches.select_books(clean_matches.BOOKS, SCOPE_ONE)
        assert books == [BOOK_IN]                                   # 剔除 scope 外 3 书
        assert clean_matches.select_books(clean_matches.BOOKS, SCOPE) == clean_matches.BOOKS
        # 7 书 profile：kb 事件层已点亮 4 书全在 scope（过滤为 no-op 但口径声明生效）
        assert clean_matches.select_books(clean_matches.BOOKS, None) == clean_matches.BOOKS

    def test_select_books_respects_available(self):
        """未点亮书目不进（BOOKS ∩ available），scope 过滤在可用书之内。"""
        assert clean_matches.select_books([BOOK_IN, "江湖三女侠"], SCOPE_ONE) == [BOOK_IN]
        assert clean_matches.select_books([BOOK_IN, "江湖三女侠"], None) == [BOOK_IN, "江湖三女侠"]

    def test_payload_meta_scope_written(self):
        """meta.scope 写入（口径与 EX 层一致：scope=profile 名字符串）。"""
        payload = clean_matches.build_payload([], [], set(), [BOOK_IN], scope=SCOPE)
        assert payload["meta"]["scope"] == "tianshan-demo"
        assert payload["meta"]["books"] == [BOOK_IN]
        assert payload["meta"]["schema"] == "matches-v2"

    def test_full_caliber_meta_no_scope(self):
        payload = clean_matches.build_payload([], [], set(), clean_matches.BOOKS)
        assert "scope" not in payload["meta"]
        assert payload["meta"]["schema"] == "matches-v2"
        assert payload["meta"]["books"] == clean_matches.BOOKS


# ================================================================ 2. ratings_whr（工具 E·E2）
def _whr_match(mid, a, b, outcome, book=BOOK_IN, loc="001:005", layer="L1", trust="high"):
    s = {"win": 1.0, "loss": 0.0, "draw": 0.5}[outcome]
    return {"id": mid, "a": a, "b": b, "outcome": outcome, "s": s, "weight": s,
            "confidence": "high", "layer": layer, "trust": trust, "via": "事件方向动词",
            "modifiers": [], "kind": "单挑" if layer == "L1" else "围攻", "book": book,
            "loc": loc, "scene": "S00-001"}


def _whr_matches():
    return [
        _whr_match("M001", "甲", "乙", "win", BOOK_IN, "001:005"),
        _whr_match("M002", "乙", "丙", "loss", BOOK_IN, "002:010"),
        _whr_match("M003", "甲", "丙", "draw", "七剑下天山", "010:003"),
        _whr_match("M004", "甲", "乙", "win", BOOK_IN, "003:020"),
        _whr_match("M005", "丁", "戊", "win", BOOK_OUT, "005:001"),
    ]


class TestRatingsWhrScope:
    def test_filter_matches_scope(self):
        """对局按 book ∈ scope 过滤：站外书（萍踪侠影录）对局剔除；全量口径恒等。"""
        kept = ratings_whr.filter_matches(_whr_matches(), SCOPE)
        assert [m["id"] for m in kept] == ["M001", "M002", "M003", "M004"]
        assert ratings_whr.filter_matches(_whr_matches(), None) == _whr_matches()

    def test_players_recomputed_from_filtered(self):
        """选手由过滤后对局重算：只在 scope 外出战者不进榜。"""
        ms = ratings_whr.filter_matches(_whr_matches(), SCOPE)
        players, _th, _cf = ratings_whr.run_whr(ms)
        names = {p["name"] for p in players}
        assert names == {"甲", "乙", "丙"}
        assert names.isdisjoint({"丁", "戊"})


class TestRatingsWhrLegacyCompat:
    def test_run_whr_mini_and_dual_keys(self):
        """合成对局跑迷你 WHR：players 双键齐备，final==rating、round(uncertainty)==rd。"""
        players, thresholds, conflicts = ratings_whr.run_whr(_whr_matches()[:4])
        by = {p["name"]: p for p in players}
        assert set(by) == {"甲", "乙", "丙"}
        legacy = {"name", "rating", "rd", "tier", "matches_n", "w/d/l", "per_book", "top_evidence"}
        v2 = {"final", "uncertainty", "curve", "peak"}
        for p in players:
            assert legacy <= set(p)                                  # RatingExplorer 现行契约
            assert v2 <= set(p)                                      # 武评 v2 契约
            assert p["final"] == p["rating"]
            assert round(p["uncertainty"]) == p["rd"]
            assert all({"t", "r", "u"} <= set(c) for c in p["curve"])
            assert {"t", "r", "u"} <= set(p["peak"])
        # 编年多日轨迹 + per_book 双书（甲：白发 001/003 + 七剑 010）
        assert by["甲"]["w/d/l"] == [2, 1, 0]
        assert set(by["甲"]["per_book"]) == {BOOK_IN, "七剑下天山"}
        assert by["甲"]["matches_n"] == 3 and by["甲"]["tier"] != "待考"
        assert by["丙"]["tier"] == "待考"                             # matches_n<3 → 待考（主榜门槛）
        assert thresholds and set(thresholds) == {"绝顶", "超一流", "一流", "二流"}
        assert conflicts == []                                       # 无倒置 → 无剧情保护候选

    def test_payload_meta_engine_whr_and_scope(self):
        players, thresholds, conflicts = ratings_whr.run_whr(_whr_matches()[:4])
        payload = ratings_whr.build_payload(players, thresholds, conflicts, _whr_matches()[:4],
                                            scope=SCOPE)
        assert payload["meta"]["engine"] == "whr"
        assert payload["meta"]["scope"] == "tianshan-demo"
        assert payload["meta"]["books"] == [BOOK_IN, "七剑下天山"]     # scope 内实际有对局的书
        assert payload["meta"]["tier_anchors"]["names"] == ratings_whr.ANCHORS
        assert payload["meta"]["totals"]["matches"] == 4
        ratings = [p["rating"] for p in payload["players"]]
        assert ratings == sorted(ratings, reverse=True)              # 主榜按评分降序

    def test_full_caliber_meta_no_scope(self):
        players, thresholds, conflicts = ratings_whr.run_whr(_whr_matches()[:4])
        payload = ratings_whr.build_payload(players, thresholds, conflicts, _whr_matches()[:4])
        assert "scope" not in payload["meta"]
        assert payload["meta"]["books"] == ratings_whr.CHRONO        # 全量口径 books 保持 CHRONO


# ================================================================ 3. audit_r1（死亡一致性）
class TestAuditR1Scope:
    def test_select_books_scope(self):
        assert audit_r1.select_books(audit_r1.CHRONO, SCOPE) == audit_r1.CHRONO
        assert audit_r1.select_books(audit_r1.CHRONO, SCOPE_ONE) == [BOOK_IN]   # 剔除 scope 外书
        assert audit_r1.select_books(audit_r1.CHRONO, None) == audit_r1.CHRONO

    def test_scan_and_payload_meta_scope(self):
        deaths = {"甲": [((0, 1, 5), BOOK_IN, "001:005", "乙")]}
        appearances = {"甲": [((0, 1, 5), BOOK_IN, "001:005", "杀", "object", False),
                              ((0, 2, 3), BOOK_IN, "002:003", "走", "subject", True)]}
        payload = audit_r1.build_payload(deaths, appearances, 0, [BOOK_IN], scope=SCOPE)
        assert payload["meta"]["scope"] == "tianshan-demo"
        assert payload["meta"]["books"] == [BOOK_IN]
        assert payload["meta"]["schema"] == "audit-r1-v1"
        assert payload["totals"]["deaths_persons"] == 1
        # 甲死后唯一再出场为引述 → passes（宽松核验口径不变）
        assert [p["name"] for p in payload["passes"]] == ["甲"]
        assert payload["ambiguous"] == []

    def test_full_caliber_meta_no_scope(self):
        payload = audit_r1.build_payload({}, {}, 0, audit_r1.CHRONO)
        assert "scope" not in payload["meta"]
        assert payload["meta"]["books"] == audit_r1.CHRONO


# ================================================================ 4. run_pipeline（§5.5 编排顺序）
class TestPipelineCommands:
    def test_core_order_tool_e_after_ex5(self):
        """clean_matches 在 export_site_all 之后（EX-5 不得后跑覆盖工具 E）；
        ratings_whr 在 clean_matches 之后（E2 读 E1 的 matches.json）。"""
        labels = [c["label"] for c in run_pipeline.pipeline_commands()]
        assert labels.index("clean_matches") > labels.index("export_site_all")
        assert labels.index("ratings_whr") > labels.index("clean_matches")
        assert labels.index("audit_r1") > labels.index("clean_matches")

    def test_slices_after_audit_and_build_hint_last(self):
        """切片在 audit_r1 之后（games killer 消费 audit-r1 passes）；build 提示恒为末步且不代跑。
        D11：manuals_elixirs（EX-6b，名物页重构设计 §七 秘籍谱/丹药谱）入列，且紧跟
        export_site_all 之后（related_arts 链接校验读取其刚产出的 arts.json）。"""
        cmds = run_pipeline.pipeline_commands()
        labels = [c["label"] for c in cmds]
        for s in ("plots", "relations", "annals", "wordcloud", "qa_index", "games_data", "stories"):
            assert labels.index(s) > labels.index("audit_r1")
        # W2-D4-B：ratings_calibration（E3 校准回填）入列——E2 重跑覆盖 meta.calibration 后必须重回填
        assert set(labels) == {"export_site_all", "manuals_elixirs", "clean_matches", "ratings_whr",
                               "ratings_calibration",
                               "audit_r1", "plots", "relations", "annals", "wordcloud", "qa_index",
                               "games_data", "stories", "build（不代跑）"}
        assert labels.index("ratings_calibration") == labels.index("ratings_whr") + 1
        assert labels.index("manuals_elixirs") == labels.index("export_site_all") + 1
        hint = cmds[-1]
        assert hint["argv"] is None                                  # 不代跑 astro
        assert "npm run build" in hint["note"]

    def test_command_scripts_exist(self):
        """命令指向的脚本真实存在（防编排表笔误）。"""
        for c in run_pipeline.pipeline_commands():
            if c["argv"] is not None:
                assert Path(c["argv"][1]).exists(), c["label"]

    def test_scope_argv_difference(self):
        """scope 口径逐条透传 --scope；全量口径不带；--apply 只加给 export_site_all 与
        manuals_elixirs（D11：EX-6b 同为 esc.finish 语义导出器，有 dry-run/apply 两态）。"""
        full = run_pipeline.pipeline_commands(scope=None, apply=True)
        scoped = run_pipeline.pipeline_commands(scope="tianshan-demo", apply=True)
        assert [c["label"] for c in full] == [c["label"] for c in scoped]
        for c in scoped:
            if c["argv"] is not None:
                assert "--scope" in c["argv"] and "tianshan-demo" in c["argv"]
        for c in full:
            if c["argv"] is not None:
                assert "--scope" not in c["argv"]
        assert "--apply" in full[0]["argv"]
        assert "--apply" in full[1]["argv"]                       # D11：EX-6b 同受 --apply
        assert "--apply" not in run_pipeline.pipeline_commands()[0]["argv"]
        assert "--apply" not in run_pipeline.pipeline_commands()[1]["argv"]
        # 工具 E/切片脚本无 dry-run 模式：apply 前后 argv 不变（仅打印 vs 真跑）
        assert run_pipeline.pipeline_commands(apply=False)[2]["argv"] == \
            run_pipeline.pipeline_commands(apply=True)[2]["argv"]

    def test_scope_all_equals_none(self):
        assert run_pipeline.pipeline_commands(scope="all") == run_pipeline.pipeline_commands(scope=None)

    def test_backup_targets_and_copy(self, tmp_path, monkeypatch):
        """--apply 前备份受影响文件到 site/data/backup/c1_<时间戳>/；缺失文件跳过不报错。
        D11：BACKUP_FILES 增补 manuals/elixirs（EX-6b 产物，存在才备份）。"""
        site_data = tmp_path / "data"
        site_data.mkdir()
        for name in ("matches.json", "audit-r1.json", "manuals.json"):
            (site_data / name).write_text("{}", encoding="utf-8")
        monkeypatch.setattr(run_pipeline, "SITE_DATA", site_data)
        dest, copied = run_pipeline.backup_site_data_files(tag_prefix="c1test")
        assert copied == ["matches.json", "audit-r1.json", "manuals.json"]
        assert dest.parent == site_data / "backup"
        assert dest.name.startswith("c1test_")
        assert (dest / "matches.json").read_text(encoding="utf-8") == "{}"
        assert run_pipeline.BACKUP_FILES == ["matches.json", "ratings.json",
                                             "ratings-cleanlog.json", "audit-r1.json",
                                             "manuals.json", "elixirs.json"]


# ================================================================ 5. EX-5 legacy 声明（防覆盖）
def _ex5_match(mid, a, b, outcome, book):
    return {"id": mid, "a": a, "b": b, "outcome": outcome, "weight": 0.8, "confidence": "high",
            "modifiers": [], "kind": "单挑", "book": book, "loc": "001:005",
            "scene": "S001-01", "evidence": {"source": "scene_word", "rule": "胜负词表（场景）"}}


class TestEX5LegacyDeclaration:
    """EX-5 v1/glicko2 产物 = legacy 中间层：docstring 与 meta.note 必须明示正式 live 由工具 E 覆盖。"""

    def test_meta_note_declares_legacy_middle_layer(self):
        matches = [_ex5_match("M001", "甲", "乙", "win", BOOK_IN),
                   _ex5_match("M002", "乙", "丙", "draw", BOOK_IN)]
        mp = exm.build_matches_payload(matches, ["甲", "乙", "丙"],
                                       {"dropped": 0, "in_quote": 0, "no_participants": 0},
                                       {"scene_word": 2, "event_outcome": 0},
                                       {"ev_total": 10, "combat_total": 3})
        assert "clean_matches/ratings_whr 覆盖" in mp["meta"]["note"]
        ratings = exm.build_ratings(matches)
        rp = exm.build_ratings_payload(ratings, matches)
        assert "clean_matches/ratings_whr 覆盖" in rp["meta"]["note"]

    def test_docstring_declares_legacy_middle_layer(self):
        assert "clean_matches" in exm.__doc__ and "覆盖" in exm.__doc__
