# -*- coding: utf-8 -*-
"""D12 · qa-events 3 书真事件接入测试（registry/events 新源适配器，2026-11-12）。

背景（D12）：qa-events 的 散花女侠/联剑风云录/冰魄寒光剑 此前为 gap 空占位
（W2-B10：D03/EX-5 未上线）。D03 新事件层 registry/events/<书>.json（event-v1）
已在库——build_qa_index.py 对缺旧事件表（atlas 切片 events={}）的书改读新源适配；
旧表存在的书保持旧路径（两源并存不迁移）。

新旧源字段映射（adapter = registry_event_rows，逐项固化于下列测试）：
  loc   "001:002"（段号 3 位补零） → l "001:2"（旧产物格式，段号不补零）
  anchor_verbs[].verb              → v（1 事件 1 锚动词，逐动词成行；0 锚动词容器行丢弃）
  subject（空则 施者 参与者）        → a（人物，可 null）
  object （空则 受者 参与者）        → b（人物/物件，可 null——旧产物含单侧空行）
  type  T01/T02/T04/T06            → code ◈/◉/◇/○（旧 5 类 verb_code 家族延续；
                                      旧 ▲ 擒控无对应新类型，擒拿动词已入 T01→◈）
  其余互动族 type                  → code = anchor 动词 verb_domain 符号（⊟/⊠/⊡，降级映射）
  过滤纪律对齐旧产物（build_atlas_slices 口径）：
    - gate=excluded（R1 无参与方 / R3 非事实叙述）丢弃 ≈ 旧 dropped/verdict=drop 不入切片
      （旧产物 0 双空行）；gate=review（R2 单方降级 / R4 对白内）保留
      ≈ 旧产物保留单侧空行与 in_quote 行（白发 247 条非 drop in_quote 中 216 条在旧 qa-events）；
    - 非互动族（T05 练功/T07 门派/T08 朝廷/T09 战争/T12 行踪/T13 大会容器）不入 qa-events
      —— 行语义=人物间作用行（旧事件表同构）；行踪职能在 qa-index persons。
"""
import json
import re
import sys
from pathlib import Path

import pytest

# 被测模块（父仓 scripts/）+ scope 基础设施（wuxia-kb/scripts/）——同 test_qa_seven_books 接线
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "wuxia-kb" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import export_site_common as esc  # noqa: E402
import build_qa_index as bqi  # noqa: E402

SITE_DATA = REPO_ROOT / "site" / "data"
REG_EVENTS = REPO_ROOT / "wuxia-kb" / "registry" / "events"
NEW_BOOKS = ["散花女侠", "联剑风云录", "冰魄寒光剑"]   # D12 接入 3 书（registry 新源）
OLD_BOOKS = ["白发魔女传", "塞外奇侠传", "七剑下天山", "江湖三女侠"]  # 旧事件表 4 书（保持旧路径）
OLD_CODES = {"◈", "◉", "▲", "○", "◇"}                 # 旧产物 verb_code 符号集
DOMAIN_CODES = {"■", "⊡", "⊞", "⊟", "⊠", "▣"}          # 新源 verb_domain 符号集（降级回落）


def _ev(**kw):
    """合成 registry event-v1 事件（缺省=gate ok 双方齐备单锚动词，镜像真实产物结构）。"""
    base = {
        "event_id": "001.002.01", "type": "T01", "type_label": "比武较技",
        "verb_domain": "⊞",
        "anchor_verbs": [{"verb": "刺", "domain": "⊞", "pos": 10, "in_quote": False}],
        "subject": "卓一航", "object": "练霓裳",
        "participants": [{"role": "施者", "name": "卓一航", "entity_type": "@"},
                         {"role": "受者", "name": "练霓裳", "entity_type": "@"}],
        "book": "冰魄寒光剑", "chapter": 1, "pn": 2, "loc": "001:002",
        "gate": "ok", "gate_reason": "", "narrative_mode": "正常叙事",
        "source_type": "叙述", "confidence": "high", "seq": 1,
    }
    base.update(kw)
    return base


def _payload(evs):
    """最小 event-v1 payload（真实产物顶层含 events 数组；meta 段适配器不消费）。"""
    return {"schema": "event-v1", "book": "冰魄寒光剑", "events": evs}


# ============================================================ 1. schema/字段映射（纯函数）
class TestRegistryEventRows:
    def test_rows_emitted_in_old_schema(self):
        """适配器输出旧 qa-events 行 schema：恰 {l,v,a,b,code,book} 6 键；a=subject b=object。"""
        rows = bqi.registry_event_rows("冰魄寒光剑", _payload([_ev()]))
        assert len(rows) == 1
        r = rows[0]
        assert set(r.keys()) == {"l", "v", "a", "b", "code", "book"}
        assert r == {"l": "001:2", "v": "刺", "a": "卓一航", "b": "练霓裳",
                     "code": "◈", "book": "冰魄寒光剑"}

    def test_loc_para_padding_stripped_matches_old_format(self):
        """loc 段号去补零："001:002"→"001:2"（旧产物格式；前端 parseInt(e.l) 取回号兼容）。"""
        rows = bqi.registry_event_rows("冰魄寒光剑", _payload(
            [_ev(loc="001:002"), _ev(loc="012:100", event_id="012.100.01")]))
        assert [r["l"] for r in rows] == ["001:2", "012:100"]
        assert all(re.fullmatch(r"\d{3}:\d+", r["l"]) for r in rows)

    def test_gate_excluded_dropped_ok_review_kept(self):
        """过滤纪律对齐旧产物：excluded（R1/R3）丢弃；ok 与 review（R2 单方/R4 对白）保留。"""
        evs = [_ev(),
               _ev(gate="excluded", gate_reason="R1 无参与方", subject="", object="",
                   participants=[], event_id="x1"),
               _ev(gate="excluded", gate_reason="R3 非事实叙述模式",
                   narrative_mode="假想", event_id="x2"),
               _ev(gate="review", gate_reason="R2 单方参与者（降级）", object="",
                   participants=[{"role": "施者", "name": "卓一航", "entity_type": "@"}],
                   event_id="x3"),
               _ev(anchor_verbs=[{"verb": "让", "domain": "⊞", "pos": 3, "in_quote": True}],
                   gate="review", gate_reason="R4 对白内（视角/转述，事实待核）",
                   source_type="人物发言", event_id="x4")]
        rows = bqi.registry_event_rows("冰魄寒光剑", _payload(evs))
        assert len(rows) == 3  # x1(R1)/x2(R3) 不入；ok + R2 + R4 入（旧纪律：in_quote 行保留）
        assert [r["a"] for r in rows] == ["卓一航", "卓一航", "卓一航"]
        assert rows[1]["b"] is None  # R2 单方 → b=null（旧产物单侧空行同款）

    def test_container_without_anchor_verb_skipped(self):
        """T13 容器聚合行 anchor_verbs=[]（无动词锚）→ 丢弃（无 v 不成行）。"""
        rows = bqi.registry_event_rows("冰魄寒光剑", _payload(
            [_ev(type="T13", anchor_verbs=[], subject="", object="",
                 participants=[{"role": "参与者", "name": "卓一航", "entity_type": "@"}],
                 event_id="022.049.C01")]))
        assert rows == []

    def test_type_scope_interaction_families_only(self):
        """行语义=人物间作用族（T01/02/03/04/06/10/11）；非互动族（T05/07/08/09/12/13）不入。"""
        keep = ["T01", "T02", "T03", "T04", "T06", "T10", "T11"]
        drop = ["T05", "T07", "T08", "T09", "T12", "T13"]
        evs = [_ev(type=t, event_id=f"e{t}", loc=f"{i + 1:03d}:002")
               for i, t in enumerate(keep + drop)]
        rows = bqi.registry_event_rows("冰魄寒光剑", _payload(evs))
        assert len(rows) == len(keep)

    def test_code_degraded_mapping_old_families_continue_else_domain(self):
        """code 降级映射：T01→◈ T02→◉ T04→◇ T06→○（旧家族延续）；其余互动族回落
        anchor 动词 verb_domain 符号（⊟/⊠/⊡）。"""
        cases = {"T01": "◈", "T02": "◉", "T04": "◇", "T06": "○"}
        evs = [_ev(type=t, event_id=f"e{t}") for t in cases]
        evs += [_ev(type="T03", anchor_verbs=[{"verb": "夺", "domain": "⊟", "pos": 1, "in_quote": False}],
                    event_id="eT03"),
                _ev(type="T11", anchor_verbs=[{"verb": "救", "domain": "⊠", "pos": 1, "in_quote": False}],
                    event_id="eT11"),
                _ev(type="T10", anchor_verbs=[{"verb": "许嫁", "domain": "⊡", "pos": 1, "in_quote": False}],
                    event_id="eT10")]
        rows = bqi.registry_event_rows("冰魄寒光剑", _payload(evs))
        assert len(rows) == len(evs)
        got = {}
        for e in evs:  # 逐事件对照（每事件 1 锚动词，v 唯一可索引）
            sub = bqi.registry_event_rows("冰魄寒光剑", _payload([e]))
            got[e["type"]] = sub[0]["code"]
        assert got == {"T01": "◈", "T02": "◉", "T04": "◇", "T06": "○",
                       "T03": "⊟", "T11": "⊠", "T10": "⊡"}
        assert set(got.values()) <= OLD_CODES | DOMAIN_CODES

    def test_single_side_rows_and_no_both_null_rows(self):
        """事件方向：a=施者行 b=受者行；单侧参与→另一侧 null（旧产物含 477/1179 单侧行）；
        双侧皆空（无参与者）→ 丢弃（旧产物 0 双空行纪律）。"""
        solo = _ev(object="", participants=[{"role": "施者", "name": "卓一航", "entity_type": "@"}],
                   gate="review", gate_reason="R2 单方参与者（降级）", event_id="s1")
        rows = bqi.registry_event_rows("冰魄寒光剑", _payload([solo]))
        assert rows[0]["a"] == "卓一航" and rows[0]["b"] is None
        rev = _ev(subject="", participants=[{"role": "受者", "name": "练霓裳", "entity_type": "@"}],
                  gate="review", gate_reason="R2 单方参与者（降级）", event_id="s2")
        rows = bqi.registry_event_rows("冰魄寒光剑", _payload([rev]))
        assert rows[0]["a"] is None and rows[0]["b"] == "练霓裳"
        none = _ev(subject="", object="", participants=[], event_id="s3")
        assert bqi.registry_event_rows("冰魄寒光剑", _payload([none])) == []

    def test_exact_duplicate_rows_deduped(self):
        """完全重复行去重（同 split_events 整行口径）；镜像行（a/b 互换）独立保留。"""
        evs = [_ev(), _ev(event_id="001.002.02"),  # 同 loc 同 verb 同双方（不同 event_id）
               _ev(subject="练霓裳", object="卓一航", event_id="001.002.03")]  # 镜像
        rows = bqi.registry_event_rows("冰魄寒光剑", _payload(evs))
        assert len(rows) == 2  # 重复行去 1；镜像行保留
        assert {(r["a"], r["b"]) for r in rows} == {("卓一航", "练霓裳"), ("练霓裳", "卓一航")}


# ============================================================ 2. 接线（两源并存 + gap 收窄）
class TestMergeRegistryGaps:
    def test_merge_fills_only_missing_books(self, tmp_path):
        """两源并存不迁移：atlas 已有事件的书（旧 4 书）不被 registry 覆盖；
        仅补 by_book 缺失的书（旧行=旧路径产物不动）。"""
        old_row = [{"l": "001:27", "v": "打", "a": "耿绍南", "b": None,
                    "code": "◈", "book": "白发魔女传"}]
        by_book = {"白发魔女传": old_row}
        (tmp_path / "白发魔女传.json").write_text('{"schema":"event-v1"}', encoding="utf-8")
        (tmp_path / "散花女侠.json").write_text(json.dumps(
            _payload([_ev(book="散花女侠", subject="张丹枫", object="瑛子",
                          anchor_verbs=[{"verb": "杀", "domain": "⊠", "pos": 5, "in_quote": False}],
                          type="T02")]), ensure_ascii=False), encoding="utf-8")
        filled = bqi.merge_registry_gaps(by_book, ["白发魔女传", "散花女侠"], reg_dir=tmp_path)
        assert filled == [("散花女侠", 1)]
        assert by_book["白发魔女传"] is old_row  # 旧路径原对象不动（旧表存在的书保持旧路径）
        assert by_book["散花女侠"][0]["book"] == "散花女侠"

    def test_merge_missing_registry_file_stays_gap(self, tmp_path):
        """registry 文件也不存在的书 → 不补（plan_event_files 仍判 gap 占位——纪律兜底）。"""
        by_book = {}
        filled = bqi.merge_registry_gaps(by_book, ["冰魄寒光剑"], reg_dir=tmp_path)
        assert filled == [] and by_book == {}
        entries, gaps = bqi.plan_event_files(by_book, ["冰魄寒光剑"])
        assert entries[0]["gap"] is True and gaps == ["冰魄寒光剑"]

    def test_plan_and_meta_no_gap_after_merge(self, tmp_path):
        """D12 验收路径：3 书接入后 plan_event_files 无 gap、build_meta 无 field_gaps。"""
        for b in NEW_BOOKS:
            (tmp_path / f"{b}.json").write_text(json.dumps(
                _payload([_ev(book=b)]), ensure_ascii=False), encoding="utf-8")
        by_book = {}
        bqi.merge_registry_gaps(by_book, NEW_BOOKS, reg_dir=tmp_path)
        entries, gaps = bqi.plan_event_files(by_book, NEW_BOOKS)
        assert gaps == [] and all("gap" not in e and e["events"] == 1 for e in entries)
        meta = bqi.build_meta(3, {}, entries, scope=esc.load_scope("tianshan-demo"), gaps=gaps)
        assert "field_gaps" not in meta


# ============================================================ 3. 真实产物纪律（live 只读）
class TestLiveRegistrySource:
    @pytest.mark.parametrize("book", NEW_BOOKS)
    def test_live_registry_file_event_v1(self, book):
        """新源在库且 schema=event-v1（D03 管线产物，只读不碰）。"""
        payload = json.loads((REG_EVENTS / f"{book}.json").read_text(encoding="utf-8"))
        assert payload["schema"] == "event-v1" and payload["book"] == book
        assert len(payload["events"]) > 0

    @pytest.mark.parametrize("book", NEW_BOOKS)
    def test_live_adapted_rows_schema_loc_codes(self, book):
        """适配真实新源：行非空、schema 6 键、loc=旧产物格式、code ∈ 旧符号∪新域符号。"""
        payload = json.loads((REG_EVENTS / f"{book}.json").read_text(encoding="utf-8"))
        rows = bqi.registry_event_rows(book, payload)
        assert len(rows) > 0
        assert all(set(r.keys()) == {"l", "v", "a", "b", "code", "book"} for r in rows)
        assert all(re.fullmatch(r"\d{3}:\d+", r["l"]) for r in rows)
        assert all(r["book"] == book for r in rows)
        assert all(r["code"] in OLD_CODES | DOMAIN_CODES for r in rows)
        assert all(r["v"] for r in rows)

    @pytest.mark.parametrize("book,victim", [("散花女侠", "张丹枫"), ("联剑风云录", "盘天罗"),
                                             ("冰魄寒光剑", "年羹尧")])
    def test_live_kill_rows_resolvable_victims(self, book, victim):
        """killer 模板可解：每书有 /杀|诛|毙/ 动词行且宾语=entity-index 规范人物
        （QaExplorer 口径 verb∈{杀,诛,毙…} 且 b=X）。"""
        payload = json.loads((REG_EVENTS / f"{book}.json").read_text(encoding="utf-8"))
        rows = bqi.registry_event_rows(book, payload)
        ei = json.loads((SITE_DATA / "entity-index.json").read_text(encoding="utf-8"))
        canon = {e["c"] for e in ei["entities"] if e.get("t") == "@"}
        hits = [(r["a"], r["v"], r["b"], r["l"]) for r in rows
                if r["b"] and re.search(r"杀|诛|毙", r["v"])]
        assert hits, f"{book} 无杀伐行"
        resolvable = [h for h in hits if h[2] in canon]
        assert resolvable, f"{book} 杀伐行宾语均不可解析"
        assert any(h[2] == victim for h in resolvable), \
            f"{book} 未见可解被杀者 {victim}（实测 {resolvable[:5]}）"

    @pytest.mark.parametrize("book,pair", [("散花女侠", ("周山民", "娄桐荪")),
                                           ("联剑风云录", ("张玉虎", "龙剑虹")),
                                           ("冰魄寒光剑", ("提摩达多", "桂华生"))])
    def test_live_versus_pairs_have_both_sides(self, book, pair):
        """versus 模板可解：每书有双侧齐备行；指定真实人物对（entity-index 可解析）在案。"""
        payload = json.loads((REG_EVENTS / f"{book}.json").read_text(encoding="utf-8"))
        rows = bqi.registry_event_rows(book, payload)
        both = [r for r in rows if r["a"] and r["b"]]
        assert both, f"{book} 无双侧行"
        x, y = pair
        hit = [r for r in both if {r["a"], r["b"]} == {x, y}]
        assert hit, f"{book} 未见 {x}×{y} 交手行"

    def test_live_old_books_have_registry_files_but_merge_must_not_touch(self, tmp_path=None):
        """两源并存实证：白发魔女传等旧 4 书在 registry 也有事件文件（新层全覆盖），
        但 merge 只补 atlas 无事件书——旧 4 书不得被新源覆盖。"""
        present = [b for b in OLD_BOOKS if (REG_EVENTS / f"{b}.json").exists()]
        assert len(present) == len(OLD_BOOKS)  # 新源覆盖旧 4 书——恰是并存风险所在
        by_book = {b: [{"l": "001:1", "v": "旧", "a": "x", "b": None, "code": "◈",
                        "book": b}] for b in OLD_BOOKS}
        sentinel = by_book["白发魔女传"]
        filled = bqi.merge_registry_gaps(by_book, OLD_BOOKS, reg_dir=REG_EVENTS)
        assert filled == [] and by_book["白发魔女传"] is sentinel
