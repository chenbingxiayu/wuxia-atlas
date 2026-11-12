# -*- coding: utf-8 -*-
"""W0-T3b · 父仓 build_* 切片脚本 scope 接线测试（天山演示版总体方案 §1.2，2026-11-08）。

只测纯函数与合成输入（同 W0-T3a 风格），不跑全管线、不写 site/data。
被测对象（W0-T3b 改造/新增，均在父仓 scripts/；scope 基础设施 = wuxia-kb/scripts/export_site_common）：
  build_plots       build_payload(rows, gaz, scope=…)                    锚点行 book ∈ scope 过滤
  build_annals      build_payloads(rows, scope=…)                        事件 book ∈ scope + daily_index 同步
  build_relations   build_payload(rows, scope=…)（新常设脚本，接替 spec 003 一次性 build_tracks T2）
  build_wordcloud   scan_presence / finalize_items / wordcloud_meta      词目按 scope 书出现过滤
                                                                         （词频保持全量口径；7 书重算=W2-B1）
  build_games_data  build_twenty / build_daily(scope=…)                  题库按 book ∈ scope 过滤重建
  build_qa_index    select_titles / index_slices / slim_index /
                    split_events / build_meta                            persons/chaps/places/events 按书过滤
  build_stories     story_enabled / story_meta / story_payloads(scope=…) 专栏书 gate + meta

口径固化（测试即规范）：
  - 全量口径（scope=None）行为与现状逐字段一致（方案 R6）：meta 无 scope 键。
  - scope 口径：记录 book ∈ scope 才保留；meta 加 {"scope": profile, "books": […]}（esc.scope_meta）。
  - 接线方式固化：父仓脚本以 sys.path 指向 wuxia-kb/scripts 复用 export_site_common（import 胜过复制）。
  - 不可归书（book 缺失/空）在 scope 口径下裁剪：无法证明在 scope 内即不在（演示口径宁缺毋滥）。
"""
import csv
import json
import sys
from pathlib import Path

import pytest

# 被测模块（父仓 scripts/）；export_site_common（wuxia-kb/scripts/）——两处显式入 path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "wuxia-kb" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import export_site_common as esc  # noqa: E402
import build_plots  # noqa: E402
import build_annals  # noqa: E402
import build_relations  # noqa: E402
import build_wordcloud  # noqa: E402
import build_games_data  # noqa: E402
import build_qa_index  # noqa: E402
import build_stories  # noqa: E402

BOOK_IN = "白发魔女传"
BOOK_OUT = "萍踪侠影录"
SCOPE_IN = {"profile": "tianshan-demo", "books": [BOOK_IN]}


# ================================================================ 0. 接线方式与真实 profile
class TestScopeInfra:
    def test_scripts_reuse_export_site_common(self):
        """父仓脚本 import 复用 export_site_common（同一模块对象，非复制函数）。"""
        for mod in (build_plots, build_annals, build_relations, build_wordcloud,
                    build_games_data, build_qa_index, build_stories):
            assert mod.esc is esc

    def test_real_profile_tianshan_demo(self):
        scope = esc.load_scope("tianshan-demo")
        assert set(scope["books"]) == {"散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
                                       "七剑下天山", "冰魄寒光剑", "江湖三女侠"}


# ================================================================ 1. build_plots（char_plots.json）
def _plot_row(book, person, seq=1, status="校定"):
    return {"person": person, "seq": str(seq), "name": f"锚点{seq}", "tags": "情感",
            "book": book, "chap": "26", "line": "53", "date_value": "", "date_grade": "",
            "date_basis": "", "place_name": "", "place_anchor": "", "place_status": "",
            "place_candidates": "", "one_liner": "一行", "status": status}


class TestBuildPlots:
    def test_scope_filters_rows_and_meta(self):
        rows = [_plot_row(BOOK_IN, "卓一航"), _plot_row(BOOK_OUT, "张丹枫")]
        payload = build_plots.build_payload(rows, {}, scope=SCOPE_IN)
        assert set(payload["characters"]) == {"卓一航"}
        assert payload["characters"]["卓一航"]["plots"][0]["book"] == BOOK_IN
        assert payload["meta"]["scope"] == "tianshan-demo"
        assert payload["meta"]["books"] == [BOOK_IN]

    def test_full_caliber_unchanged(self):
        rows = [_plot_row(BOOK_IN, "卓一航"), _plot_row(BOOK_OUT, "张丹枫"),
                _plot_row(BOOK_IN, "练霓裳", status="草案")]
        payload = build_plots.build_payload(rows, {})
        assert set(payload["characters"]) == {"卓一航", "张丹枫"}   # 非校定行仍按 status 过滤
        assert "scope" not in payload["meta"]

    def test_unattributed_row_dropped_in_scope(self):
        rows = [_plot_row(BOOK_IN, "卓一航"), _plot_row("", "无名")]
        payload = build_plots.build_payload(rows, {}, scope=SCOPE_IN)
        assert set(payload["characters"]) == {"卓一航"}   # 无 book 不可归书 → scope 下裁


# ================================================================ 2. build_annals（annals.json / annals-daily.json）
def _annal_row(rid, book, m="", d="", status="校定"):
    return {"id": rid, "type": "剧情" if book == BOOK_IN else "史实",
            "name": f"事件{rid}", "y": "1640", "m": m, "d": d, "date_grade": "ok",
            "date_basis": "", "book": book, "loc": "001:5", "people": "吕四娘;冯瑛",
            "line": "一行", "conflict_hist": "", "status": status}


class TestBuildAnnals:
    def test_scope_filters_events_and_daily_rebuilt(self):
        rows = [_annal_row("A1", BOOK_IN, "3", "15"), _annal_row("A2", BOOK_OUT, "8", "1")]
        annals, daily_p = build_annals.build_payloads(rows, scope=SCOPE_IN)
        assert [e["id"] for e in annals["events"]] == ["A1"]
        assert set(daily_p["index"]) == {"03-15"}                  # daily_index 同步重建
        assert daily_p["index"]["03-15"][0]["id"] == "A1"
        assert annals["meta"]["scope"] == "tianshan-demo"
        assert daily_p["meta"]["scope"] == "tianshan-demo"

    def test_full_caliber_both_files_unchanged(self):
        rows = [_annal_row("A1", BOOK_IN, "3", "15"), _annal_row("A2", BOOK_OUT, "8", "1")]
        annals, daily_p = build_annals.build_payloads(rows)
        assert [e["id"] for e in annals["events"]] == ["A1", "A2"]
        assert set(daily_p["index"]) == {"03-15", "08-01"}
        assert "scope" not in annals["meta"] and "scope" not in daily_p["meta"]

    def test_scope_out_event_not_in_daily(self):
        annals, daily_p = build_annals.build_payloads([_annal_row("A2", BOOK_OUT, "8", "1")],
                                                      scope=SCOPE_IN)
        assert annals["events"] == [] and daily_p["index"] == {}


# ================================================================ 3. build_relations（char_relations.json，新常设脚本）
def _rel_row(a, b, book, status="校定"):
    return {"a": a, "b": b, "type": "情缘", "tier": "ok", "book": book,
            "loc": "026:53", "note": "考订注", "status": status}


class TestBuildRelations:
    def test_scope_filters_and_meta(self):
        rows = [_rel_row("卓一航", "练霓裳", BOOK_IN), _rel_row("张丹枫", "云蕾", BOOK_OUT)]
        rels = build_relations.collect(rows, scope=SCOPE_IN)
        assert [(r["a"], r["book"]) for r in rels] == [("卓一航", BOOK_IN)]
        payload = build_relations.build_payload(rows, scope=SCOPE_IN)
        assert payload["meta"]["scope"] == "tianshan-demo"
        assert payload["meta"]["schema"] == "char-relations-v1"
        assert payload["meta"]["types"] == ["情缘", "亲缘", "仇敌", "恩义"]

    def test_full_caliber_matches_current_file(self):
        """全量口径产出与现行 char_relations.json 逐字段一致（忠实接替 spec 003 一次性脚本）。

        注：W0-T5 apply 后 live 文件为 scope 口径（meta 多 scope 键；relations 因
        TSV 行全部属 scope 书而与全量一致），故 meta 对比豁免 scope 键。
        """
        current = json.loads((REPO_ROOT / "site" / "data" / "char_relations.json")
                             .read_text(encoding="utf-8"))
        tsv_rows = list(csv.DictReader(
            (REPO_ROOT / "kb" / "校订" / "人物关系考订.tsv").read_text(encoding="utf-8").splitlines(),
            delimiter="\t"))
        payload = build_relations.build_payload(tsv_rows)
        assert payload["relations"] == current["relations"]
        for k, v in current["meta"].items():
            if k in ("scope", "books"):  # scope 口径新增键，豁免
                continue
            assert payload["meta"][k] == v
        assert "scope" not in payload["meta"]


# ================================================================ 4. build_wordcloud（char_wordcloud.json）
class TestBuildWordcloud:
    def test_scan_presence(self):
        pairs = [(BOOK_IN, "张三练剑"), (BOOK_OUT, "李四练刀"), (BOOK_IN, "张三又练")]
        presence = build_wordcloud.scan_presence(pairs, {"张三", "李四", "王五"})
        assert presence["张三"] == {BOOK_IN}
        assert presence["李四"] == {BOOK_OUT}
        assert "王五" not in presence

    def test_scope_filters_items_and_books_count(self):
        """词目按 scope 书出现过滤；books = scope 内出现书目数（词频 n 保持全量口径）。"""
        top = [("张三", 100), ("李四", 50), ("王五", 10)]
        presence = {"张三": {BOOK_IN, BOOK_OUT}, "李四": {BOOK_OUT}, "王五": {BOOK_IN}}
        items = build_wordcloud.finalize_items(top, presence, SCOPE_IN)
        assert items == [{"w": "张三", "n": 100, "books": 1}, {"w": "王五", "n": 10, "books": 1}]

    def test_full_caliber_books_counts_all(self):
        top = [("张三", 100), ("李四", 50)]
        presence = {"张三": {BOOK_IN, BOOK_OUT}, "李四": {BOOK_OUT}}
        items = build_wordcloud.finalize_items(top, presence, None)
        assert items == [{"w": "张三", "n": 100, "books": 2}, {"w": "李四", "n": 50, "books": 1}]

    def test_meta_scope_and_w2b1_note(self):
        meta = build_wordcloud.wordcloud_meta(SCOPE_IN)
        assert meta["scope"] == "tianshan-demo" and meta["cleaned"] is False
        assert "W2-B1" in meta["note"]                            # 7 书语料重算依赖显式标注
        assert "scope" not in build_wordcloud.wordcloud_meta(None)


# ================================================================ 5. build_games_data（games/twenty + daily.json）
def _dossier(name, books, total=100):
    return {"canonical": name, "books": books, "combat": {}, "lineage": {}, "sect_affinity": [],
            "appearance_total": total}


def _slice(book, events):
    return {"title": book, "events": events}


class TestBuildGamesTwenty:
    def test_scope_filters_chars_and_books_trimmed(self):
        dossiers = {"dossiers": [_dossier("卓一航", [BOOK_IN]), _dossier("张丹枫", [BOOK_OUT]),
                                 _dossier("凌未风", [BOOK_IN, "七剑下天山"])]}
        payload = build_games_data.build_twenty(dossiers, [], scope=SCOPE_IN)
        assert {c["name"] for c in payload["chars"]} == {"卓一航", "凌未风"}
        ling = next(c for c in payload["chars"] if c["name"] == "凌未风")
        assert ling["books"] == [BOOK_IN]                          # books 裁到 scope
        assert payload["meta"]["scope"] == "tianshan-demo"

    def test_full_caliber_unchanged(self):
        dossiers = {"dossiers": [_dossier("卓一航", [BOOK_IN]), _dossier("张丹枫", [BOOK_OUT])]}
        payload = build_games_data.build_twenty(dossiers, [])
        assert {c["name"] for c in payload["chars"]} == {"卓一航", "张丹枫"}
        assert "scope" not in payload["meta"]


class TestBuildGamesDaily:
    def _arts(self):
        # BOOK_OUT 关系在前：全量口径先命中站外书，scope 口径被裁后回落 scope 书（差异可观测）
        return {"arts": [{"canonical": "测试剑法", "relations": {
            BOOK_OUT: {"relations": [{"s": "站外派", "st": "◆", "pred": "拥有", "ev": 9, "locs": ["2:1"]}]},
            BOOK_IN: {"relations": [{"s": "武当派", "st": "◆", "pred": "镇山", "ev": 6, "locs": ["1:2"]}]},
        }}]}

    def _weapons(self):
        return {"weapons": [{"canonical": "测试剑", "kind": "剑", "conf": "strong",
                             "books": {BOOK_IN: [1], BOOK_OUT: [2]},
                             "holders": [{"name": "卓一航", "n": 5}],
                             "chain": [{"verb": "夺", "book": BOOK_OUT, "loc": "2:1", "conf": "strong"},
                                       {"verb": "夺", "book": BOOK_IN, "loc": "1:2", "conf": "strong"}]},
                            {"canonical": "站外剑", "kind": "剑", "conf": "strong",
                             "books": {BOOK_OUT: [1]},
                             "holders": [{"name": "外人", "n": 3}],
                             "chain": [{"verb": "夺", "book": BOOK_OUT, "loc": "2:1", "conf": "strong"}]}]}

    def _slices(self):
        return [_slice(BOOK_IN, {"1": [{"v": "杀", "a": "卓一航", "b": "victim_in", "l": "001:005"}]}),
                _slice(BOOK_OUT, {"1": [{"v": "杀", "a": "张丹枫", "b": "victim_out", "l": "001:005"}]})]

    def test_scope_filters_all_puzzle_types(self):
        passes = {"victim_in", "victim_out"}   # audit-r1 已是 scope 口径时天然对齐（5 书全在 scope）
        payload = build_games_data.build_daily(self._slices(), self._arts(), self._weapons(),
                                               passes, scope=SCOPE_IN)
        by_type = {}
        for p in payload["puzzles"]:
            by_type.setdefault(p["type"], []).append(p)
        assert {p["id"] for p in by_type.get("killer", [])} == {"killer-victim_in"}
        sect = by_type["sectart"][0]
        assert sect["loc"].startswith(BOOK_IN)                     # 归属证据取 scope 书
        assert BOOK_OUT not in sect["hints"][0]
        wpn = by_type["holder"][0]
        assert wpn["id"] == "wpn-测试剑"                            # 站外剑整条裁掉
        assert BOOK_OUT not in wpn["hints"][1]                     # 书目提示裁到 scope
        assert wpn["loc"].startswith(BOOK_IN)                      # strong 明文边取 scope 书
        assert payload["meta"]["scope"] == "tianshan-demo"

    def test_full_caliber_all_puzzles(self):
        payload = build_games_data.build_daily(self._slices(), self._arts(), self._weapons(),
                                               {"victim_in", "victim_out"})
        ids = {p["id"] for p in payload["puzzles"]}
        assert {"killer-victim_in", "killer-victim_out", "art-测试剑法",
                "wpn-测试剑", "wpn-站外剑"} <= ids
        sect = next(p for p in payload["puzzles"] if p["type"] == "sectart")
        assert sect["loc"].startswith(BOOK_OUT)                    # 全量口径取字典序首本书（现状）
        assert "scope" not in payload["meta"]


# ================================================================ 6. build_qa_index（qa-index.json + qa-events/）
def _qa_slice(book):
    return {"title": book,
            "persons": {"甲": {"n": 3, "chaps": [1, 2]}},
            "bychap": {"1": {"p": ["甲"], "l": ["长安"]}, "2": {"p": ["甲"], "l": []}},
            "events": {"1": [{"l": "001:005", "v": "杀", "a": "甲", "b": "乙", "code": "◈", "conf": "ok"}]}}


class TestBuildQaIndex:
    def test_select_titles_scope_and_full(self):
        state = {"books": [{"title": BOOK_IN}, {"title": BOOK_OUT}, {"title": None}]}
        assert build_qa_index.select_titles(state, SCOPE_IN) == [BOOK_IN]
        assert build_qa_index.select_titles(state, None) == [BOOK_IN, BOOK_OUT]

    def test_index_and_events_scope_filtered(self):
        persons, n_books = build_qa_index.index_slices(
            [(BOOK_IN, _qa_slice(BOOK_IN)), (BOOK_OUT, _qa_slice(BOOK_OUT))])
        assert n_books == 2
        assert persons["甲"]["chaps"] == {BOOK_IN: [1, 2], BOOK_OUT: [1, 2]}   # 按切片归书
        slim = build_qa_index.slim_index(persons, {"长安": True}, {"长安"})
        assert slim["甲"]["places"] == [{"name": "长安", "first": f"{BOOK_IN}·001", "real": True}]
        by_book, dropped = build_qa_index.split_events(persons)
        assert set(by_book) == {BOOK_IN, BOOK_OUT}
        assert dropped == 2                                        # 参与者×聚合重复行去重（每书 1 条）
        assert by_book[BOOK_IN][0]["book"] == BOOK_IN
        events_files = [{"book": BOOK_IN, "file": f"qa-events/{BOOK_IN}.json", "events": 1}]
        meta = build_qa_index.build_meta(n_books, slim, events_files, scope=SCOPE_IN)
        assert meta["scope"] == "tianshan-demo"
        assert meta["books"] == [BOOK_IN]     # 统一契约：scope 口径 books=书目列表（旧 int 计数为全量口径）
        assert build_qa_index.build_meta(n_books, slim, [], None)["books"] == 2  # 全量口径保持 int 计数
        assert "scope" not in build_qa_index.build_meta(n_books, slim, [], None)


# ================================================================ 7. build_stories（stories/*.json）
def _story_slice():
    return {"title": BOOK_IN, "chapters": 2,
            "persons": {"卓一航": {"chaps": [1, 2]}, "练霓裳": {"chaps": [1]}},
            "events": {"1": [{"l": "001:005", "v": "救", "a": "卓一航", "b": "练霓裳", "code": "◈"}]}}


class TestBuildStories:
    def test_gate_and_meta_scope(self):
        assert build_stories.story_enabled(BOOK_IN, SCOPE_IN) is True
        assert build_stories.story_enabled(BOOK_IN, {"profile": "p", "books": ["七剑下天山"]}) is False
        assert build_stories.story_enabled(BOOK_IN, None) is True
        meta = build_stories.story_meta(SCOPE_IN)
        assert meta["scope"] == "tianshan-demo"
        assert meta["script"] == "scripts/build_stories.py"
        assert "scope" not in build_stories.story_meta(None)

    def test_payloads_filtered_by_scope(self, tmp_path, monkeypatch):
        """scope 不含白发魔女传 → 不产旧两篇（空表）；scope 含 → 旧两篇齐 + meta.scope。
        D6 起 story_id 即 URL slug（temperature-curve，原 temp-curve 更名）；
        新三篇依赖 qa-events（tmp_path 下缺文件 → 诚实跳过，见 test_stories_v2）。"""
        monkeypatch.setattr(build_stories, "SITE_DATA", tmp_path)   # 事件层缺 → 新篇诚实跳过
        monkeypatch.setattr(build_stories, "KB", tmp_path)          # 事件表缺 → 摘录词计数为 0
        payloads = build_stories.story_payloads(_story_slice(), {"dossiers": []},
                                                scope=SCOPE_IN, markers=[])
        assert [n for n, _ in payloads] == ["temperature-curve", "growth-curve"]
        for _n, p in payloads:
            assert p["meta"]["scope"] == "tianshan-demo"
            assert p["book"] == BOOK_IN
        out_scope = build_stories.story_payloads(_story_slice(), {"dossiers": []},
                                                 scope={"profile": "p", "books": ["七剑下天山"]},
                                                 markers=[])
        assert out_scope == []
