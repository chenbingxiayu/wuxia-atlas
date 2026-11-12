# -*- coding: utf-8 -*-
"""W2-B10 · qa-events 7 书全量 + qa-index 7 书覆盖测试（天山演示版总体方案 §4.2 B10，2026-11-11）。

背景（B10）：qa-events 仅 4 书（白发/塞外/七剑/三女侠——旧站冻结事件表），而 atlas/state.json
与 atlas/<书>.json 切片已 7 书（W0-T4 · EX-7 接管），build_qa_index --scope 按
state.json 书目 ∩ scope 取书——qa-index 轻索引（persons/chaps/places）7 书即可达；
qa-events/<书>.json 须 7 书全覆盖（QaExplorer 按 meta.events_files 逐书 fetch 的契约）。
散花女侠/联剑风云录/冰魄寒光剑无事件层（D03/EX-5 未上线，atlas 切片 events={}）→
最小实现：写空文件 {book, events: [], gap: true}，meta.field_gaps 声明缺口（不伪造事件，
EX-7「冰魄 events={} + field_gaps」同款纪律）。

测试口径（先红后绿）：
  - 纯函数（合成输入，不写 site/data）：plan_event_files（书目全覆盖 + 无事件层书 gap 占位）、
    build_meta（R6：全量口径 meta 无 scope 键、books=已索引书数 int；scope 口径
    books=书目列表 + field_gaps 仅在缺口存在时出现）。
  - 真实产物纪律（读 live site/data，只读不写）：qa-index.json meta.books=7 书列表、
    persons 按书覆盖 == atlas 切片 persons 数、places 全部经 gazetteer 去噪（spec 011 T26）、
    qa-events/ 文件数=7 且新 3 书自 W2-D12 起为真事件（registry/events 新源适配，非 gap）、
    旧 4 书事件数 >0。
"""
import json
import sys
from pathlib import Path

import pytest

# 被测模块（父仓 scripts/）+ scope 基础设施（wuxia-kb/scripts/）——同 test_build_slices_scope 接线
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "wuxia-kb" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import export_site_common as esc  # noqa: E402
import build_qa_index  # noqa: E402

SITE_DATA = REPO_ROOT / "site" / "data"
SCOPE = esc.load_scope("tianshan-demo")
BOOKS7 = list(SCOPE["books"])
NEW_BOOKS = ["散花女侠", "联剑风云录", "冰魄寒光剑"]   # B10 待扩散 3 书（无事件层）
OLD_BOOKS = ["白发魔女传", "塞外奇侠传", "七剑下天山", "江湖三女侠"]  # 旧站冻结事件表 4 书


def _synthetic_slice(title, chaps=3, places=2, events=1):
    """最小 atlas 切片：persons/bychap/events 三段齐备（index_slices 的输入契约）。"""
    bychap, events_by_chap = {}, {}
    for c in range(1, chaps + 1):
        bychap[str(c)] = {"p": [f"人物甲{title}"], "l": [f"地点{title}"] if places else []}
        if events:
            events_by_chap[str(c)] = [{"l": f"{c:03d}:010", "v": "胜", "a": f"人物甲{title}",
                                       "b": f"人物乙{title}", "code": "◈"}]
    return {"title": title, "persons": {f"人物甲{title}": {"n": 5, "chaps": [c for c in range(1, chaps + 1)]}},
            "bychap": bychap, "events": events_by_chap}


# ================================================================ 1. plan_event_files（书目全覆盖 + gap 占位）
class TestPlanEventFiles:
    def test_all_titles_get_event_file_entries(self):
        """qa-events/<书>.json 按书目全覆盖：有事件书 events>0，无事件书 events=0 + gap 占位。"""
        by_book = {"白发魔女传": [{"l": "001:010", "book": "白发魔女传"}]}
        titles = ["白发魔女传", "散花女侠"]
        entries, gaps = build_qa_index.plan_event_files(by_book, titles)
        assert [e["book"] for e in entries] == titles  # 顺序保持 titles（scope 口径=配置序）
        by = {e["book"]: e for e in entries}
        assert by["白发魔女传"]["events"] == 1 and "gap" not in by["白发魔女传"]
        assert by["散花女侠"]["events"] == 0 and by["散花女侠"]["gap"] is True
        assert all(e["file"] == f"qa-events/{e['book']}.json" for e in entries)
        assert gaps == ["散花女侠"]

    def test_empty_events_slice_counts_as_gap(self):
        """atlas 切片 events={}（EX-7 口径）的书 → gap 占位文件（不伪造事件）。"""
        by_book, _ = build_qa_index.split_events({"冰魄寒光剑": {"events": [], "chaps": {}, "places": {}}})
        assert by_book == {}
        entries, gaps = build_qa_index.plan_event_files(by_book, ["冰魄寒光剑"])
        assert entries[0]["gap"] is True and entries[0]["events"] == 0
        assert gaps == ["冰魄寒光剑"]

    def test_index_slices_gap_book_yields_persons_without_events(self):
        """无事件层切片仍产 persons/chaps（QA 行踪 7 书全量的数据来源）。"""
        persons, n = build_qa_index.index_slices([("散花女侠", _synthetic_slice("散花女侠", events=0))])
        assert n == 1
        assert "人物甲散花女侠" in persons and persons["人物甲散花女侠"]["chaps"]
        assert persons["人物甲散花女侠"]["events"] == []


# ================================================================ 2. build_meta（R6 双口径 + field_gaps 声明）
class TestBuildMetaR6:
    EF = [{"book": "白发魔女传", "file": "qa-events/白发魔女传.json", "events": 3},
          {"book": "散花女侠", "file": "qa-events/散花女侠.json", "events": 0, "gap": True}]

    def test_full_caliber_meta_no_scope_key(self):
        """全量口径（R6）：meta 无 scope 键，books=已索引书数（int，旧契约）。"""
        meta = build_qa_index.build_meta(2, {"x": {"chaps": {}, "places": []}}, self.EF, scope=None)
        assert "scope" not in meta and "field_gaps" not in meta
        assert meta["books"] == 2 and isinstance(meta["books"], int)
        assert meta["events_files"] == self.EF

    def test_scope_meta_books_is_title_list(self):
        """scope 口径：books=书目列表（§1.2 统一契约）。"""
        meta = build_qa_index.build_meta(2, {"x": {"chaps": {}, "places": []}}, self.EF, scope=SCOPE)
        assert meta["scope"] == "tianshan-demo"
        assert meta["books"] == BOOKS7

    def test_meta_declares_field_gaps_when_present(self):
        """缺口声明：gaps 非空 → meta.field_gaps 列出无事件层书（gate provenance 白名单键）。"""
        meta = build_qa_index.build_meta(2, {}, self.EF, scope=SCOPE, gaps=["散花女侠"])
        assert meta["field_gaps"] == ["散花女侠"]

    def test_meta_no_field_gaps_key_when_complete(self):
        meta = build_qa_index.build_meta(2, {}, self.EF, scope=None, gaps=[])
        assert "field_gaps" not in meta


# ================================================================ 3. 真实产物纪律（live site/data，只读）
class TestLiveSevenBooks:
    def test_select_titles_scope_equals_seven_books(self):
        """state.json 书目 ∩ scope = 7 书（顺序保持 scope 配置序）。"""
        state = json.loads((SITE_DATA / "atlas" / "state.json").read_text(encoding="utf-8"))
        assert build_qa_index.select_titles(state, SCOPE) == BOOKS7

    @pytest.mark.parametrize("book", BOOKS7)
    def test_live_qa_index_persons_cover_every_book_slice(self, book):
        """persons 按书覆盖 == atlas 切片 persons 数（7 书逐一断言；轻索引切片来源）。"""
        qa = json.loads((SITE_DATA / "qa-index.json").read_text(encoding="utf-8"))
        sl = json.loads((SITE_DATA / "atlas" / f"{book}.json").read_text(encoding="utf-8"))
        n = sum(1 for p in qa["persons"].values() if book in p.get("chaps", {}))
        assert n == len(sl["persons"]) > 0

    def test_live_qa_index_books_meta_is_seven_titles(self):
        qa = json.loads((SITE_DATA / "qa-index.json").read_text(encoding="utf-8"))
        assert qa["meta"]["books"] == BOOKS7
        assert qa["meta"]["scope"] == "tianshan-demo"

    def test_live_places_gazetteer_noise_filtered(self):
        """places 去噪（B10 后半，spec 011 T26）：全部行踪地名 ∈ gazetteer 收录（含虚构 4 处）。"""
        qa = json.loads((SITE_DATA / "qa-index.json").read_text(encoding="utf-8"))
        gaz = json.loads((SITE_DATA / "gazetteer.json").read_text(encoding="utf-8"))
        gaz_names = {p["name"] for p in gaz["places"]}
        places = [pl["name"] for p in qa["persons"].values() for pl in p.get("places", [])]
        assert places, "places 不应为空"
        assert {x for x in places if x not in gaz_names} == set()

    def test_live_qa_events_seven_files(self):
        """qa-events/ 文件数=7 且与 meta.events_files 一致（QaExplorer 逐书 fetch 契约）。"""
        ev_dir = SITE_DATA / "qa-events"
        files = sorted(p.name for p in ev_dir.glob("*.json"))
        assert files == sorted(f"{b}.json" for b in BOOKS7)
        qa = json.loads((SITE_DATA / "qa-index.json").read_text(encoding="utf-8"))
        meta_files = {e["book"]: e for e in qa["meta"]["events_files"]}
        assert set(meta_files) == set(BOOKS7)
        for b in files:
            payload = json.loads((ev_dir / b).read_text(encoding="utf-8"))
            entry = meta_files[b[:-len(".json")]]
            assert entry["file"] == f"qa-events/{b}"
            assert entry["events"] == len(payload["events"])

    @pytest.mark.parametrize("book", NEW_BOOKS)
    def test_live_new_books_event_files_are_real_events(self, book):
        """新 3 书事件层已上线（W2-D12 接管 registry/events 新源）：真事件行、无 gap 标记、
        meta.field_gaps 收窄清空（D12 前为 gap 空占位 + field_gaps 声明）。"""
        payload = json.loads((SITE_DATA / "qa-events" / f"{book}.json").read_text(encoding="utf-8"))
        assert payload["book"] == book and len(payload["events"]) > 0 and "gap" not in payload
        assert all(set(r.keys()) == {"l", "v", "a", "b", "code", "book"} for r in payload["events"])
        qa = json.loads((SITE_DATA / "qa-index.json").read_text(encoding="utf-8"))
        assert not (set(qa.get("meta", {}).get("field_gaps", [])) & set(NEW_BOOKS))

    @pytest.mark.parametrize("book", OLD_BOOKS)
    def test_live_old_books_keep_frozen_events(self, book):
        """旧 4 书事件照常产出（>0 条）且无 gap 标记——B10 只补覆盖，不动存量事件。"""
        payload = json.loads((SITE_DATA / "qa-events" / f"{book}.json").read_text(encoding="utf-8"))
        assert len(payload["events"]) > 0 and "gap" not in payload
