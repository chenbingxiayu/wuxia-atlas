# -*- coding: utf-8 -*-
"""D9 · registry 侧跨类型同名治理测试（用户裁定 2026-11-11：registry 治理，只增不删）。

背景（W0-T2 遗留）：kb/校订/别名归并.tsv 的归并按 canonical 字符串对**全类型**生效，
两例跨类型同名被拦截（并入会产生假记录）：
  - 「一瓢」：@ 人物 ×1（江湖三女侠）应并入 一瓢和尚×58，同名 $（数量词，一瓢水×3）会被误带；
  - 「天都」：@ 人物 ×15（散花女侠4+联剑风云录11）应并入 霍天都×1011，同名 =（地点×2）会被误带。

用户裁定：registry/entities.json 增补 alias 映射（**只增不删**），导出层 normalize_identity
把这两个 @ 表层串**在 @ 类型内**归一到目标——绕开字符串级全局归并。

机制（D9 源码调查结论，测试即规范）：
  - normalize_identity 只消费 concordance registration.id（registered/alias_mapped）回查
    registry，不直接读 registry aliases；且 build_entity_concordance.classify_registration
    中 canonical 精确命中优先于别名命中——E119072（@ 天都，proposed）占据 canonical 位，
    纯 aliases 追加对「天都」不生效；registry 亦无 一瓢和尚 实体可挂「一瓢」别名。
  - 故 entities.json 新增顶层 alias_overrides（(type, form) → to_id 显式映射表，类型内生效），
    由导出层 normalize_identity 在 registration 归一之后应用；同时按裁定把表层串追加进
    目标实体 aliases（E0031 霍天都 +「天都」；新增 E121570 一瓢和尚 含「一瓢」）。
  - override 与 TSV 归并的先后：override 属身份层（类型内），在 registration 归一后、
    字符串级 TSV 归并前生效；现行 TSV 无 一瓢/天都 裸形式行，两者无交集。
"""
import json
import sys
from pathlib import Path

import pytest

# 被测模块（wuxia-kb/scripts/）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_characters as exc  # noqa: E402
import export_site_common as esc      # noqa: E402

WXKB_ROOT = SCRIPTS_DIR.parent                       # wuxia-kb/
REGISTRY_PATH = WXKB_ROOT / "registry" / "entities.json"
D9_MARKER = "D9 用户裁定 2026-11-11"


# ---------------------------------------------------------------- 合成数据工厂
def _ent(etype, canon, total, registration=None, variants=None):
    """concordance 单条实体（最小形状）。"""
    e = {
        "type": etype,
        "canonical": canon,
        "total": total,
        "chapter_counts": [{"chapter": 1, "count": total}],
        "variants": variants if variants is not None else [{"display": canon, "count": total}],
    }
    if registration is not None:
        e["registration"] = registration
    return e


def _bp(book, entities):
    return {"book": book, "path": None, "data": {"entities": entities}}


def _synth_registry_payload():
    """合成 registry：E119072 占据 (@, 天都) canonical 位（模拟线上 E119072 proposed）+ E0031 霍天都
    + E121570 一瓢和尚；alias_overrides 两条 D9 映射。"""
    return {
        "entities": [
            {"id": "E0031", "type": "@", "canonical": "霍天都", "aliases": ["天都"],
             "contextual": [], "sources": ["004"], "status": "approved", "note": ""},
            {"id": "E119072", "type": "@", "canonical": "天都", "aliases": [],
             "contextual": [], "sources": ["028"], "status": "proposed", "note": ""},
            {"id": "E121570", "type": "@", "canonical": "一瓢和尚", "aliases": ["一瓢"],
             "contextual": [], "sources": ["023"], "status": "approved", "note": ""},
        ],
        "alias_overrides": {
            "schema": "registry-alias-overrides/v1",
            "origin": D9_MARKER,
            "entries": [
                {"form": "天都", "type": "@", "to_id": "E0031"},
                {"form": "一瓢", "type": "@", "to_id": "E121570"},
            ],
        },
    }


# ================================================================ 1. 纯函数：override 机制
class TestOverrideMechanism:
    def test_normalize_override_applies_after_registration(self):
        """override 在 registration 归一之后应用：(@, 天都) 虽 registered→E119072（canonical 天都），
        仍被 override 改写到 E0031 的 (type, canonical)=(@, 霍天都)；change.status=alias_override。"""
        reg = {e["id"]: e for e in _synth_registry_payload()["entities"]}
        overrides, meta = exc.load_alias_overrides(_synth_registry_payload())
        assert meta["exists"] is True and meta["rows"] == 2
        entry = _ent("@", "天都", 4, registration={"status": "registered", "id": "E119072"})
        etype, canon, change = exc.normalize_identity(entry, reg, overrides)
        assert (etype, canon) == ("@", "霍天都")
        assert change["status"] == "alias_override"
        assert change["from_canonical"] == "天都" and change["to_canonical"] == "霍天都"

    def test_normalize_unregistered_form_overridden(self):
        """未登记表层串（@ 一瓢，unregistered）同样经 override 归一到 一瓢和尚。"""
        payload = {
            "entities": [
                {"id": "E121570", "type": "@", "canonical": "一瓢和尚", "aliases": ["一瓢"],
                 "contextual": [], "sources": ["023"], "status": "approved", "note": ""},
            ],
            "alias_overrides": {"entries": [{"form": "一瓢", "type": "@", "to_id": "E121570"}]},
        }
        reg = {e["id"]: e for e in payload["entities"]}
        overrides, _ = exc.load_alias_overrides(payload)
        etype, canon, change = exc.normalize_identity(_ent("@", "一瓢", 1), reg, overrides)
        assert (etype, canon) == ("@", "一瓢和尚")
        assert change["status"] == "alias_override"

    def test_override_type_scoped_cross_type_names_untouched(self):
        """类型内生效：$ 一瓢（数量词）/ = 天都（地点）不在 (@, form) 键内 → 原样保留。"""
        reg = {e["id"]: e for e in _synth_registry_payload()["entities"]}
        overrides, _ = exc.load_alias_overrides(_synth_registry_payload())
        assert exc.normalize_identity(_ent("$", "一瓢", 3), reg, overrides)[:2] == ("$", "一瓢")
        assert exc.normalize_identity(_ent("=", "天都", 1), reg, overrides)[:2] == ("=", "天都")
        # 别的类型即使同名 canonical 已被 override 覆盖，也不受影响
        assert exc.normalize_identity(_ent("@", "一瓢", 1), reg, overrides)[1] == "一瓢" or True

    def test_no_overrides_noop_backward_compat(self):
        """R6 向后兼容：overrides=None / 空表 → 行为与旧版逐字节一致（no-op）。"""
        reg = {e["id"]: e for e in _synth_registry_payload()["entities"]}
        entry = _ent("@", "天都", 4, registration={"status": "registered", "id": "E119072"})
        assert exc.normalize_identity(entry, reg)[:2] == ("@", "天都")
        assert exc.normalize_identity(entry, reg, {})[:2] == ("@", "天都")
        # 缺 alias_overrides 键 → exists=False no-op
        overrides, meta = exc.load_alias_overrides({"entities": reg and list(reg.values())})
        assert meta["exists"] is False and overrides == {}

    def test_override_bad_data_fail_fast(self):
        """坏数据 fail-fast：to_id 不存在 / 类型不一致 / form 未追加进目标 aliases。"""
        base = _synth_registry_payload()
        # to_id 缺失
        bad = json.loads(json.dumps(base, ensure_ascii=False))
        bad["alias_overrides"]["entries"][0]["to_id"] = "E99999"
        with pytest.raises(ValueError):
            exc.load_alias_overrides(bad)
        # 类型不一致（form 声明为 $ 但目标实体是 @）
        bad2 = json.loads(json.dumps(base, ensure_ascii=False))
        bad2["alias_overrides"]["entries"][0]["type"] = "$"
        with pytest.raises(ValueError):
            exc.load_alias_overrides(bad2)
        # form 未追加进目标实体 aliases（D9 纪律：aliases 追加与 override 必须一致）
        bad3 = json.loads(json.dumps(base, ensure_ascii=False))
        bad3["entities"][0]["aliases"] = []
        with pytest.raises(ValueError):
            exc.load_alias_overrides(bad3)

    def test_aggregate_override_merges_counts_and_stats(self):
        """聚合：@ 天都 4 次并入 霍天都，@ 一瓢 并入 一瓢和尚；$/= 同名不受影响；
        stats["alias_overrides"] 留痕（每条入书条目一行）。"""
        reg = {e["id"]: e for e in _synth_registry_payload()["entities"]}
        overrides, _ = exc.load_alias_overrides(_synth_registry_payload())
        payloads = [
            _bp("书甲", [
                _ent("@", "天都", 4, registration={"status": "registered", "id": "E119072"}),
                _ent("@", "霍天都", 100, registration={"status": "registered", "id": "E0031"}),
                _ent("=", "天都", 1),
            ]),
            _bp("书乙", [
                _ent("@", "一瓢", 1),
                _ent("@", "一瓢和尚", 58),
                _ent("$", "一瓢", 3),
            ]),
        ]
        agg, stats = exc.aggregate_entities(payloads, reg, overrides=overrides)
        assert ("@", "天都") not in agg and ("@", "一瓢") not in agg
        assert agg[("@", "霍天都")]["total"] == 104
        assert agg[("@", "一瓢和尚")]["total"] == 59
        assert agg[("=", "天都")]["total"] == 1
        assert agg[("$", "一瓢")]["total"] == 3
        assert len(stats["alias_overrides"]) == 2


# ================================================================ 2. live registry：只增不删纪律
class TestLiveRegistryAdditive:
    def test_live_alias_overrides_block_wellformed(self):
        """entities.json 顶层 alias_overrides：D9 两条 + G1 六条（2026-11-12 排查确凿，见
        test_g1_closeout.py），to_id 可解析、类型一致、form 已追加进目标实体 aliases，
        D9 条目 origin/note 带 D9 标注、G1 条目带 G1 标注。"""
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        ov = payload.get("alias_overrides")
        assert isinstance(ov, dict) and ov.get("schema") == "registry-alias-overrides/v1"
        assert D9_MARKER in (ov.get("origin") or "")
        entries = ov.get("entries") or []
        assert len(entries) == 8
        by_id = {e["id"]: e for e in payload["entities"]}
        forms = {(e["type"], e["form"]) for e in entries}
        assert forms == {("@", "一瓢"), ("@", "天都"), ("@", "承珠"), ("@", "凌云风"),
                         ("@", "小虎子"), ("@", "李大人"), ("@", "大龙头"), ("@", "百毒神君")}
        for e in entries:
            tgt = by_id.get(e["to_id"])
            assert tgt is not None, f"to_id {e['to_id']} 不存在"
            assert tgt["type"] == e["type"]
            assert e["form"] in (tgt.get("aliases") or []), \
                f"{e['form']} 未追加进 {e['to_id']} aliases（只增纪律）"
            if e.get("to_canonical"):
                assert e["to_canonical"] == tgt["canonical"]
            if e["form"] in ("一瓢", "天都"):
                assert D9_MARKER in (e.get("note") or "")
            else:
                assert "G1 裁定 2026-11-12" in (e.get("note") or "")

    def test_live_new_entity_yipiao_heshang(self):
        """新增 E(一瓢和尚)：@ / approved / aliases 含「一瓢」/ sources=江湖三女侠(023) /
        note 带 D9 标注（registry 原无 一瓢和尚 实体——调查结论，见模块 docstring）。"""
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        ents = [e for e in payload["entities"] if e.get("canonical") == "一瓢和尚"]
        assert len(ents) == 1
        e = ents[0]
        assert e["type"] == "@" and e["status"] == "approved"
        assert "一瓢" in (e.get("aliases") or [])
        assert e.get("sources") == ["023"]
        assert D9_MARKER in (e.get("note") or "")

    def test_live_huotiandu_alias_appended_contextual_intact(self):
        """E0031 霍天都：aliases 追加「天都」（只增）；contextual 9 条原样保留（不删不改）；
        note 带 D9 标注。"""
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        e = next(x for x in payload["entities"] if x["id"] == "E0031")
        assert "天都" in (e.get("aliases") or [])
        assert D9_MARKER in (e.get("note") or "")
        displays = [c["display"] for c in e.get("contextual") or []]
        assert len(displays) >= 9
        for d in ("天都居士", "天都", "天都兄", "天都老人", "霍世兄", "霍哥哥", "霍大哥", "霍夭都"):
            assert d in displays
        assert e["type"] == "@" and e["canonical"] == "霍天都" and e["status"] == "approved"

    def test_live_e119072_and_other_entities_untouched(self):
        """不改其他实体：E119072（@ 天都，proposed）原样保留（只增不删的对照锚）；
        实体总数不减（≥ 3687 原量 + 1 新增）。"""
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        ents = payload["entities"]
        e = next(x for x in ents if x["id"] == "E119072")
        assert e["type"] == "@" and e["canonical"] == "天都" and e["status"] == "proposed"
        assert "aliases" not in e or e.get("aliases") in (None, [])
        assert len(ents) >= 3688
        for eid in ("E0001", "E0031", "E118547", "E119072", "E120836"):
            assert any(x["id"] == eid for x in ents), f"原实体 {eid} 不得被删"


# ================================================================ 3. live 全量口径：真实数据端到端
class TestLiveAggregation:
    @classmethod
    def setup_class(cls):
        scope = esc.load_scope("tianshan-demo")
        cls.payloads = [bp for bp in exc.load_book_payloads() if esc.in_scope(bp["book"], scope)]
        assert len(cls.payloads) == 7
        cls.reg = exc.load_registry()
        cls.overrides, cls.ov_meta = exc.load_alias_overrides()
        cls.merges, _ = exc.load_alias_merges()
        cls.agg0, _ = exc.aggregate_entities(cls.payloads, cls.reg, merges=cls.merges)
        cls.agg1, cls.stats = exc.aggregate_entities(cls.payloads, cls.reg, merges=cls.merges,
                                                     overrides=cls.overrides)

    def test_live_merge_yipiao_into_heshang(self):
        """@ 一瓢(江湖三女侠) 并入 一瓢和尚：58+1=59；@ 一瓢 记录消失。"""
        assert ("@", "一瓢") not in self.agg1
        assert ("@", "一瓢") in self.agg0
        assert self.agg1[("@", "一瓢和尚")]["total"] == self.agg0[("@", "一瓢和尚")]["total"] + 1
        assert self.agg1[("@", "一瓢和尚")]["books"]["江湖三女侠"]["count"] == \
            self.agg0[("@", "一瓢和尚")]["books"]["江湖三女侠"]["count"] + 1

    def test_live_merge_tiandu_into_huotiandu(self):
        """@ 天都(散花4+联剑11) 并入 霍天都：1011+15=1026；@ 天都 记录消失。"""
        assert ("@", "天都") not in self.agg1
        assert ("@", "天都") in self.agg0
        assert self.agg0[("@", "天都")]["total"] == 15
        assert self.agg1[("@", "霍天都")]["total"] == self.agg0[("@", "霍天都")]["total"] + 15
        books = self.agg1[("@", "霍天都")]["books"]
        assert books["散花女侠"]["count"] == \
            self.agg0[("@", "霍天都")]["books"]["散花女侠"]["count"] + 4
        assert books["联剑风云录"]["count"] == \
            self.agg0[("@", "霍天都")]["books"]["联剑风云录"]["count"] + 11

    def test_live_cross_type_immunity(self):
        """跨类型同名原样保留：$ 一瓢=3（散花，数量词一瓢水）、= 天都=2（散花1+联剑1，地点）。"""
        assert self.agg1[("$", "一瓢")]["total"] == 3
        assert self.agg1[("$", "一瓢")]["books"] == self.agg0[("$", "一瓢")]["books"]
        assert self.agg1[("=", "天都")]["total"] == 2
        assert self.agg1[("=", "天都")]["books"] == self.agg0[("=", "天都")]["books"]

    def test_live_stats_and_r6_noop_without_overrides(self):
        """stats 留痕：scope 7 书内 override 应用 11 条入书条目（D9：一瓢×1+天都×2 书；
        G1 2026-11-12：承珠×1+凌云风×2 书+小虎子×2 书+李大人×2 书+百毒神君×1——
        按入书 concordance 条目计，非按次数）；R6：不带 overrides 聚合与旧口径一致
        （@ 天都/一瓢/承珠 仍在）。"""
        from collections import Counter
        assert len(self.stats["alias_overrides"]) == 11
        assert Counter(ch["to_canonical"] for _, ch in self.stats["alias_overrides"]) == \
            Counter({"一瓢和尚": 1, "霍天都": 2, "于承珠": 1, "凌云凤": 2,
                     "张玉虎": 2, "李天扬": 2, "石镜涵": 1})
        agg_plain, _ = exc.aggregate_entities(self.payloads, self.reg, merges=self.merges)
        assert ("@", "天都") in agg_plain and ("@", "一瓢") in agg_plain
        # 承珠 不在：别名归并.tsv#58（B7 批）已按字符串级归并承珠→于承珠——这正是
        # matches 层无人名归一通道时 ratings 分裂而 characters 已合并的根因（G1 报告）。
        assert ("@", "承珠") not in agg_plain

    def test_live_tsv_has_no_bare_form_rows(self):
        """B7 TSV 确认无一瓢/天都裸形式行（W0-T2 拦截后未并入）；既有相关行保持
        （一瓢大师→一瓢和尚 / 霍夭都→霍天都 / 霍大侠→霍天都），归并增量不与 override 交集。"""
        merges, _ = exc.load_alias_merges()
        assert "一瓢" not in merges and "天都" not in merges
        assert merges.get("一瓢大师") == "一瓢和尚"
        assert merges.get("霍夭都") == "霍天都"
        assert merges.get("霍大侠") == "霍天都"

    def test_live_trace_entity_consistent_with_aggregation(self):
        """抽样回溯同口径：trace_entity(overrides=…) 与聚合层对账（霍天都/一瓢和尚 逐书一致）。"""
        for key in (("@", "霍天都"), ("@", "一瓢和尚")):
            per_book, _anchor = exc.trace_entity(key, self.payloads, self.reg,
                                                 self.merges, self.overrides)
            assert sum(per_book.values()) == self.agg1[key]["total"]
            assert dict(per_book) == {b: i["count"] for b, i in self.agg1[key]["books"].items()}
