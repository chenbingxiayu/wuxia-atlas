# -*- coding: utf-8 -*-
"""F1 · 武评 4 书 → 7 书测试（clean_matches registry/events 新源适配器 + WHR 全量重算，2026-11-12）。

背景（任务 F1 · 天山演示版总体方案 §3.1 P0-2 延伸）：matches-v2 现仅收旧事件表 4 书
（白发/塞外/七剑/三女侠，133 场）；散花女侠/联剑风云录/冰魄寒光剑 无旧表，D03 新事件层
registry/events/<书>.json（event-v1）已在库——clean_matches 仿 D12 qa-index 模式接入：
scope 口径下无旧事件表的书改读新源（两源并存不迁移）；**全量口径（scope=None）不消费新源
（方案 R6：避免 24 书全量爆炸）**。

适配口径（复用 D12 适配器 build_qa_index.registry_event_rows / registry_norm_loc，测试固化）：
  - 对局语义仅战斗族：type T01→◈ / T02→◉（T04◇/T06○ 非战斗不入对局）；
  - gate=excluded 丢弃 ≈ 旧 dropped；gate=review+R4 对白内丢弃 ≈ 旧 in_quote 纪律
    （宁可榜小不可榜错——转述/视角对局不打分）；R2 单方行不入（对局需双侧主宾）；
  - participants 须 @ 人物：武器/名物作 object 的行不入 matches；
  - loc "001:002"（段号补零）→ 旧事件表格式（registry_norm_loc：段号去补零）；
  - 事件层 outcome 裁决（胜/负/平，旧 v0.1 词表移植）→ 通道 ①b「事件方向outcome」：
    pair 级方向明确归位（L2 多人景败方归位即录，不硬拆）；强度映射对齐 STRENGTH 档
    （致死→强胜 1.0 · 胜负投影→常规胜 0.85 · 词表权重→1.0/0.85/0.7/0.6 · 平→0.5）。

裁决纪律不变：L1 恰两人景照录；L2 多人景败方明确归位；归位不了不硬拆（no_verdict）；
软分数/层折扣沿用（词表近名兜底 L2 ×0.6 不变——outcome 通道 pair 级不折）。

旧 4 书可复算性（两源并存纪律）：BOOKS 前 4 位保持原序——match id/scene 码逐场不变，
仅新增 3 书场次（live 断言读 site/data/backup/f1_baseline/ 基线）。

场景文本新源：散花/联剑/冰魄 无 kb/tagged，改读 wuxia-kb/tagged/<书>/*.tagged.md
（[N] 段号版式，registry loc 段号与之对齐；markup 清洗与 read_tagged 同源）。

WHR（ratings_whr）最小接线：CHRONO 扩至 site_scope 编年序 7 书（时间轴/榜域 per_book
需要；引擎算法零改动）；calibration note 加抽检覆盖声明；method 页 133 场硬编码构建期化。
"""
import json
import sys
from pathlib import Path

import pytest

# 被测模块（父仓 scripts/）+ scope 基础设施（wuxia-kb/scripts/）——同 test_tool_pipeline 接线
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "wuxia-kb" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import export_site_common as esc  # noqa: E402
import clean_matches as cm  # noqa: E402
import ratings_whr  # noqa: E402
import ratings_calibration as rc  # noqa: E402

SITE_DATA = REPO_ROOT / "site" / "data"
BASELINE = SITE_DATA / "backup" / "f1_baseline"          # F1 重算前基线（旧 4 书逐场一致断言）
OLD_BOOKS = ["白发魔女传", "塞外奇侠传", "七剑下天山", "江湖三女侠"]  # 旧事件表 4 书（旧路径）
NEW_BOOKS = ["散花女侠", "联剑风云录", "冰魄寒光剑"]        # F1 接入 3 书（registry 新源）
SCOPE = esc.load_scope("tianshan-demo")


def _ev(**kw):
    """合成 registry event-v1 事件（缺省=gate ok 双方 @ 齐备 T01 单锚动词，镜像真实产物）。"""
    base = {
        "event_id": "001.002.01", "type": "T01", "type_label": "比武较技",
        "verb_domain": "⊞",
        "anchor_verbs": [{"verb": "拍", "domain": "⊞", "pos": 10, "in_quote": False}],
        "subject": "卓一航", "object": "练霓裳",
        "participants": [{"role": "施者", "name": "卓一航", "entity_type": "@"},
                         {"role": "受者", "name": "练霓裳", "entity_type": "@"}],
        "outcome": "未决", "outcome_ref": "", "outcome_basis": "双方在场但无胜负词证据",
        "outcome_weight": None, "condition_tags": [],
        "book": "散花女侠", "chapter": 1, "pn": 2, "loc": "001:002",
        "gate": "ok", "gate_reason": "", "narrative_mode": "正常叙事",
    }
    base.update(kw)
    return base


def _log():
    """main 同款空白 cleanlog（含 F1 新增 dropped 键）。"""
    return {"kept": {"L1": 0, "L2": 0, "L3": 0},
            "dropped": {"self_pair": 0, "no_verdict": 0, "group_label": 0, "in_quote": 0,
                        "dropped_events": 0, "reg_single_side": 0, "reg_non_person": 0},
            "transferred": {"org": 0}, "downgraded": {"attribution_fallback": 0},
            "scenes": {"count": 0, "max_persons": 0}, "wordlist_hit": {}}


def _row(v="拍", a="卓一航", b="练霓裳", oc=None, chap=1, line=2):
    """合成 evs 行（load_book_events 旧/新源同构）。"""
    return {"chap": chap, "line": line, "v": v, "a": a, "b": b, "oc": oc}


# ============================================================ 1. 新源适配器（合成 fixture）
class TestRegistryAdapter:
    def test_rows_old_schema_and_loc_norm(self):
        """适配输出旧 evs 同构行：{chap,line,v,a,b,oc}；loc 段号去补零对齐旧事件表
        （registry "001:002"→(1,2)；"012:100"→(12,100)——D12 registry_norm_loc 口径）。"""
        rows = cm.registry_book_rows("散花女侠", _log(),
                                     payload={"schema": "event-v1", "events":
                                              [_ev(), _ev(loc="012:100", event_id="012.100.01")]})
        assert len(rows) == 2
        assert [(r["chap"], r["line"]) for r in rows] == [(1, 2), (12, 100)]
        assert rows[0]["a"] == "卓一航" and rows[0]["b"] == "练霓裳"
        assert rows[0]["v"] == "拍"

    def test_combat_types_only_t01_t02(self):
        """对局仅战斗族：T01/T02 入；T04◇/T06○（传艺/结盟）与 T09 战争/T12 行踪不入。"""
        evs = [_ev(type=t, event_id=f"e{t}", loc=f"{i + 1:03d}:002")
               for i, t in enumerate(["T01", "T02", "T04", "T06", "T09", "T12"])]
        evs[1] = dict(evs[1], type="T02", outcome="胜", outcome_basis="胜败词表命中（旧 v0.1 移植）",
                      outcome_weight=1.0, anchor_verbs=[{"verb": "打败", "domain": "⊞", "pos": 1,
                                                         "in_quote": False}])
        rows = cm.registry_book_rows("散花女侠", _log(), payload={"schema": "event-v1", "events": evs})
        assert len(rows) == 2

    def test_gate_excluded_dropped(self):
        """gate=excluded（R1 无参与方/R3 非事实叙述）→ 丢弃并计 dropped_events（≈旧 dropped）。"""
        evs = [_ev(),
               _ev(gate="excluded", gate_reason="R1 无参与方", subject="", object="",
                   participants=[], event_id="x1"),
               _ev(gate="excluded", gate_reason="R3 非事实叙述模式", narrative_mode="假想", event_id="x2")]
        log = _log()
        rows = cm.registry_book_rows("散花女侠", log, payload={"schema": "event-v1", "events": evs})
        assert len(rows) == 1
        assert log["dropped"]["dropped_events"] == 2

    def test_r4_in_quote_dropped_review_kept(self):
        """R4 对白内（review）→ 丢弃计 in_quote（≈旧 in_quote 纪律——转述不打分）；
        gate=ok 行保留。"""
        evs = [_ev(),
               _ev(gate="review", gate_reason="R4 对白内（视角/转述，事实待核）",
                   source_type="人物发言", event_id="x1"),
               _ev(anchor_verbs=[{"verb": "让", "domain": "⊞", "pos": 3, "in_quote": True}],
                   gate="review", gate_reason="R4 对白内（视角/转述，事实待核）", event_id="x2")]
        log = _log()
        rows = cm.registry_book_rows("散花女侠", log, payload={"schema": "event-v1", "events": evs})
        assert len(rows) == 1
        assert log["dropped"]["in_quote"] == 2

    def test_single_side_rows_not_admitted(self):
        """单侧参与（R2 单方降级）→ 不入对局并计 reg_single_side（对局需双侧主宾，同旧路径）。"""
        evs = [_ev(object="", participants=[{"role": "施者", "name": "卓一航", "entity_type": "@"}],
                   gate="review", gate_reason="R2 单方参与者（降级）", event_id="s1"),
               _ev(subject="", participants=[{"role": "受者", "name": "练霓裳", "entity_type": "@"}],
                   gate="review", gate_reason="R2 单方参与者（降级）", event_id="s2")]
        log = _log()
        rows = cm.registry_book_rows("散花女侠", log, payload={"schema": "event-v1", "events": evs})
        assert rows == []
        assert log["dropped"]["reg_single_side"] == 2

    def test_weapon_object_row_dropped_non_person(self):
        """跨类型人名拦截：武器/名物作 object 的 T01 行不得入 matches——participants 须 @ 人物。"""
        evs = [_ev(object="游龙剑", anchor_verbs=[{"verb": "削", "domain": "⊞", "pos": 1, "in_quote": False}],
                   participants=[{"role": "施者", "name": "卓一航", "entity_type": "@"},
                                 {"role": "受者", "name": "游龙剑", "entity_type": "W"}],
                   event_id="w1"),
               _ev(object="练霓裳", event_id="w2")]
        log = _log()
        rows = cm.registry_book_rows("散花女侠", log, payload={"schema": "event-v1", "events": evs})
        assert [(r["a"], r["b"]) for r in rows] == [("卓一航", "练霓裳")]
        assert log["dropped"]["reg_non_person"] == 1

    def test_outcome_channel_mapping(self):
        """事件层 outcome → 通道 ①b：胜→win_a / 负→win_b / 平→draw(0.5)；
        强度对齐 STRENGTH 档（致死 1.0 · 投影 0.85 · 词表权重 1.0/0.85/0.7/0.6）；
        未决/未知 → None（不打分）。"""
        assert cm.reg_outcome(_ev(outcome="胜", outcome_basis="T02 杀伐触发词（致死结果，weight 0.9）",
                                  outcome_weight=0.9)) == ("win_a", 1.0)
        assert cm.reg_outcome(_ev(outcome="胜", outcome_basis="触发词胜负投影（动作含明确结果义，weight 0.8）",
                                  outcome_weight=0.8)) == ("win_a", 0.85)
        assert cm.reg_outcome(_ev(outcome="负", outcome_basis="胜败词表命中（旧 v0.1 移植）",
                                  outcome_weight=0.85)) == ("win_b", 0.85)
        assert cm.reg_outcome(_ev(outcome="负", outcome_basis="胜败词表命中（旧 v0.1 移植）",
                                  outcome_weight=0.7)) == ("win_b", 0.7)
        assert cm.reg_outcome(_ev(outcome="负", outcome_basis="胜败词表命中（旧 v0.1 移植）",
                                  outcome_weight=0.6)) == ("win_b", 0.6)
        assert cm.reg_outcome(_ev(outcome="平", outcome_basis="平局词命中",
                                  outcome_weight=0.7)) == ("draw", 0.5)
        assert cm.reg_outcome(_ev(outcome="未决", outcome_basis="双方在场但无胜负词证据")) is None
        assert cm.reg_outcome(_ev(outcome="未知", outcome_basis="仅单方参与者")) is None

    def test_canon_and_row_shape(self):
        """行经别名归并（与 main 同一 _ALIAS 映射）+ oc 随行（胜→win_a 强度）。"""
        cm._ALIAS.clear()
        cm._ALIAS["哈玛雅"] = "飞红巾"                       # 注入同源映射（合成可断言）
        try:
            rows = cm.registry_book_rows("散花女侠", _log(), payload={
                "schema": "event-v1", "events": [
                    _ev(subject="哈玛雅", object="卓一航",
                        participants=[{"role": "施者", "name": "哈玛雅", "entity_type": "@"},
                                      {"role": "受者", "name": "卓一航", "entity_type": "@"}],
                        outcome="胜", outcome_basis="T02 杀伐触发词（致死结果，weight 0.9）",
                        outcome_weight=0.9, event_id="c1")]})
        finally:
            cm._ALIAS.clear()                                # 不污染其他测试
        assert rows[0]["a"] == "飞红巾"                      # 别名归并生效
        assert rows[0]["b"] == "卓一航"
        assert rows[0]["oc"] == ("win_a", 1.0)


# ============================================================ 2. 两源并存 + R6 全量不消费新源
class TestTwoSourcesAndR6:
    def test_full_caliber_never_consumes_registry(self):
        """R6：全量口径（scope=None）不消费 registry 新源——无旧表的书返回空（不读新源）；
        旧表书照常走旧路径。"""
        assert cm.load_book_events("散花女侠", scope=None, log=_log()) == ([], None)
        evs, src = cm.load_book_events("白发魔女传", scope=None, log=_log())
        assert src == "kb-events" and len(evs) > 0

    def test_scope_dispatches_registry_for_new_books(self):
        """scope 口径：无旧表的书改读 registry（src=registry-events）；旧表书保持旧路径
        （monkeypatch 新源函数——旧书绝不触发）。"""
        evs, src = cm.load_book_events("散花女侠", scope=SCOPE, log=_log())
        assert src == "registry-events" and len(evs) > 0
        assert all(isinstance(r["chap"], int) and isinstance(r["line"], int) for r in evs)

        orig = cm.registry_book_rows

        def _boom(*a, **k):
            raise AssertionError("旧表书不得消费新源（两源并存）")
        cm.registry_book_rows = _boom
        try:
            evs2, src2 = cm.load_book_events("白发魔女传", scope=SCOPE, log=_log())
        finally:
            cm.registry_book_rows = orig
        assert src2 == "kb-events" and len(evs2) > 0

    def test_available_books_full_vs_scope(self):
        """可用书目：全量口径 = lit_books()（kb 旧路径，R6）；scope 口径并集新源 3 书。"""
        assert cm.available_books(None) == cm.lit_books()
        avail = cm.available_books(SCOPE)
        for b in NEW_BOOKS + OLD_BOOKS:
            assert b in avail

    def test_books_order_old_four_first(self):
        """BOOKS 前 4 位保持原序（match id/scene 码逐场不变的可复算纪律）；
        新 3 书按编年序追加（共 7 书）。"""
        assert cm.BOOKS[:4] == OLD_BOOKS
        assert cm.BOOKS[4:] == NEW_BOOKS
        assert len(cm.BOOKS) == 7

    def test_select_books_seven_scope_noop(self):
        """scope 口径 BOOKS 7 书全命中（过滤 no-op）；窄 profile 剔除语义不变。"""
        assert cm.select_books(cm.BOOKS, SCOPE) == cm.BOOKS
        assert cm.select_books(cm.BOOKS, {"profile": "d", "books": ["白发魔女传"]}) == ["白发魔女传"]


# ============================================================ 3. 裁决通道与场景文本
class TestPairVerdict:
    def test_event_verb_channel_priority_over_outcome(self):
        """通道优先级：事件方向动词 ① 先于 outcome ①b——verb=杀（强胜）压过 oc 投影档。"""
        scene = [_row(v="杀", oc=("win_a", 0.85))]
        res = cm.pair_verdict(scene, {"卓一航", "练霓裳"}, "卓一航", "练霓裳", "", "L1", has_draw=False)
        assert res == ("win", 1.0, "medium", "事件方向动词")

    def test_outcome_channel_l2_winner_attribution(self):
        """①b outcome 通道：中性动词行 oc=win_b → 败方明确归位（L2 多人景可录），
        强度/通道名/信任档齐备。"""
        scene = [_row(v="挡", a="练霓裳", b="卓一航", oc=("win_b", 0.85))]
        res = cm.pair_verdict(scene, {"卓一航", "练霓裳"}, "卓一航", "练霓裳", "", "L2", has_draw=False)
        assert res == ("win", 0.85, "medium", "事件方向outcome")

    def test_oc_draw_only_l1(self):
        """outcome=平：L1 恰两人景照录（draw 0.5）；L2 多人景平局属噪声通道——不打分
        （裁决纪律不变：归位不了不硬拆）。"""
        scene = [_row(v="斗", oc=("draw", 0.5))]
        assert cm.pair_verdict(scene, {"卓一航", "练霓裳"}, "卓一航", "练霓裳", "", "L1",
                               has_draw=False) == ("draw", 0.5, "medium", "事件方向outcome")
        assert cm.pair_verdict(scene, {"卓一航", "练霓裳"}, "卓一航", "练霓裳", "", "L2",
                               has_draw=False) is None

    def test_wordlist_fallback_unchanged_and_none(self):
        """② 词表近名兜底语义不变（单命中 0.6 档 · trust=low——L2 ×0.6 折扣由 main 按 via 施加）；
        无任何明文 → None（宁可榜小）。"""
        scene = [_row(v="挡", oc=None)]
        res = cm.pair_verdict(scene, {"卓一航", "练霓裳"}, "卓一航", "练霓裳",
                              "卓一航略胜一筹。", "L1", has_draw=False)
        assert res == ("loss", 0.7, "low", "词表近名兜底")
        assert cm.pair_verdict(scene, {"卓一航", "练霓裳"}, "卓一航", "练霓裳", "", "L1",
                               has_draw=False) is None

    def test_old_style_rows_have_no_oc_channel(self):
        """旧源行（无 oc 键）行为不变：中性动词行不受 ①b 影响（两源并存语义隔离）。"""
        scene = [{"chap": 1, "line": 2, "v": "刺", "a": "卓一航", "b": "练霓裳"}]
        assert cm.pair_verdict(scene, {"卓一航", "练霓裳"}, "卓一航", "练霓裳", "", "L1",
                               has_draw=False) is None

    def test_read_wxkb_tagged_live_alignment(self):
        """新源场景文本：wuxia-kb/tagged [N] 段号与 registry loc 对齐（散花女侠 001:080
        ↔ [80] 段 童家骏×张风府）；markup 清洗（〖@名〗→名）；跨行段落并入前段。"""
        paras = dict(((c, l), t) for c, l, t in cm.read_wxkb_tagged("散花女侠"))
        t80 = paras[(1, 80)]
        assert "童家骏" in t80 and "张风府" in t80
        assert "〖" not in t80 and "⟦" not in t80
        assert any(t for (c, l), t in paras.items() if c == 1 and l == 1)

    def test_scene_text_window_feeds_wordlist_for_new_books(self):
        """接线：新源书场景文本来自 wxkb reader（main 按 source 选 reader——这里验证
        read_wxkb_tagged 产出的 (chap,line) 键与 adapter 行 (chap,line) 同构可查）。"""
        evs, src = cm.load_book_events("冰魄寒光剑", scope=SCOPE, log=_log())
        assert src == "registry-events" and evs
        paras = dict(((c, l), t) for c, l, t in cm.read_wxkb_tagged("冰魄寒光剑"))
        hit = [e for e in evs if (e["chap"], e["line"]) in paras]
        assert hit, "adapter 行 (chap,line) 必须能查到场景文本（loc 对齐）"


# ============================================================ 4. WHR/calibration 最小接线
class TestWhrWiring:
    def test_chrono_extended_chronological_order(self):
        """CHRONO 扩至 scope 编年序 7 书（site_scope 为权威）——时间轴/榜域 per_book 需要。"""
        assert ratings_whr.CHRONO == SCOPE["books"]
        assert set(NEW_BOOKS) <= set(ratings_whr.CHRONO)

    def test_per_book_covers_new_books(self):
        """新源书对局进 WHR：per_book 键出现该书（榜域动态派生的数据前提）。"""
        ms = [{"id": "M1", "a": "张玉虎", "b": "龙剑虹", "outcome": "win", "s": 0.85,
               "weight": 0.85, "layer": "L1", "trust": "medium", "book": "联剑风云录",
               "loc": "003:010"}]
        players, _th, _cf = ratings_whr.run_whr(ms)
        by = {p["name"]: p for p in players}
        assert "联剑风云录" in by["张玉虎"]["per_book"]

    def test_calibration_note_declares_coverage(self):
        """calibration note 加抽检覆盖声明（抽检 100 场全属旧事件层 4 书）。"""
        cal = rc.build_calibration({"sampled": 100, "agree": 100, "disagree": 0, "missing": 0,
                                    "missing_ids": [], "precision": 1.0, "disagree_rows": []})
        assert "抽检覆盖旧事件层 4 书场次" in cal["note"]
        assert "不改对局裁决" in cal["note"]


# ============================================================ 5. method 页构建期化（源级守卫）
class TestMethodPage:
    def test_no_hardcoded_total_in_method_page(self):
        """/ratings/method 硬编码“133 场”清零——总数改读 matches.meta.totals.matches
        （页面经 const totals = matches.meta.totals 转引）。"""
        src = (REPO_ROOT / "site" / "src" / "pages" / "ratings" / "method.astro").read_text(
            encoding="utf-8")
        assert "133 场" not in src
        assert "totals = matches.meta.totals" in src
        assert "{totals.matches}" in src


# ============================================================ 6. live 验收（管线重跑后转绿）
#
# F1 方向修正偏差说明（2026-11-12，审计发现的 spec 违反）：基线（f1_baseline）的 s 只记
# 强度不带方向，outcome/WHR 恒按字典序 a 侧判胜——65/129 场与原文明文相反（设计文档
# 《武评工具实现设计》§82 要求 s 为 a 侧 BT 得分）。F1 对两源统一修正（verdict=loss →
# s=1−强度×修正）。原「旧 4 书 byte-identical」验收由此升级为更强的双重证明：
#   ① 重构安全（适配器零扰动）：关闭方向修正（pair_verdict + 旧幅度带法）可从旧源
#      逐场复现基线——旧事件表装载/场景切分/裁决通道全部未动；
#   ② live diff 恰为方向翻转签名：改动行 id/a/b/loc/scene/layer/kind/via/modifiers
#      全等，仅 s→1−s（±0.01 舍入容差）且 outcome 按新 s 重新离散化。
class TestLiveSevenBooks:
    def _live(self):
        return json.loads((SITE_DATA / "matches.json").read_text(encoding="utf-8"))

    def test_s_of_direction_fold_semantics(self):
        """方向修正纯函数（spec §82）：胜/平 → s=base（旧口径不变）；败 → s=1−base。
        monkeypatch s_of 恒等返回 base 即旧口径（重构安全证明的开关）。"""
        assert cm.s_of("win", 0.85) == 0.85
        assert cm.s_of("draw", 0.5) == 0.5
        assert cm.s_of("loss", 1.0) == 0.0
        assert cm.s_of("loss", 0.85) == 0.15
        assert cm.s_of("loss", 0.4) == 0.6
        assert cm.s_of("win", 1.0) == 1.0

    def test_old_books_diff_is_direction_flip_only(self):
        """live diff 恰为方向翻转签名：旧 4 书改动行不变字段（loc/scene/layer/kind/
        via/trust/modifiers）全等，s 满足 s_new ≈ 1−s_old，outcome 随新 s 离散化。
        G1（2026-11-12）后按「场景身份」(book, loc, scene, 改名后{a,b}) 对账——人名归并
        （alias_overrides）会改名/去重/平移 id 序列：旧 4 书 133 场中 1 场退场
        （008:093 李大人×白石道人——场景变 L2 后词表兜底不再成立，宁缺毋滥）。"""
        base = json.loads((BASELINE / "matches.json").read_text(encoding="utf-8"))["matches"]
        live = self._live()["matches"]
        old4 = set(OLD_BOOKS)
        REN = {"承珠": "于承珠", "凌云风": "凌云凤", "小虎子": "张玉虎",
               "李大人": "李天扬", "大龙头": "毕擎天", "百毒神君": "石镜涵"}
        key = lambda m: (m["book"], m["loc"], m["scene"],
                         frozenset((REN.get(m["a"], m["a"]), REN.get(m["b"], m["b"]))))
        b_old = [m for m in base if m["book"] in old4]
        l_idx = {}
        for m in live:
            if m["book"] in old4:
                l_idx.setdefault(key(m), []).append(m)
        matched, gone, flipped = 0, [], 0
        for bm in b_old:
            cands = l_idx.get(key(bm)) or []
            if not cands:
                gone.append((bm["id"], bm["loc"], bm["a"], bm["b"]))
                continue
            assert len(cands) == 1, bm["id"]                  # 场景身份唯一命中（歧义不猜）
            lm = cands[0]
            matched += 1
            stable = ("loc", "scene", "layer", "kind", "via", "trust",
                      "modifiers", "book", "confidence")
            if all(bm[k] == lm[k] for k in stable) and bm["s"] == lm["s"]:
                continue                                      # 未受方向修正影响（胜方在 a/平局）
            flipped += 1
            for k in stable:
                assert bm[k] == lm[k], f"{bm['id']} 方向修正外字段变更: {k}"
            assert abs((bm["s"] + lm["s"]) - 1.0) <= 0.011, \
                f"{bm['id']} 非方向翻转: s {bm['s']}→{lm['s']}"
            exp = "win" if lm["s"] >= 0.75 else ("loss" if lm["s"] <= 0.35 else "draw")
            assert lm["outcome"] == exp, f"{bm['id']} outcome 未随新 s 离散化"
        assert matched == len(b_old) - 1 and flipped > 0, \
            f"旧 4 书 {len(b_old)} 场应 132 场对账 + 方向修正翻转（实测对账 {matched} 翻转 {flipped}）"
        assert gone == [("M009", "008:093", "李大人", "白石道人")]
        new_rows = [m for m in live if m["book"] not in old4]
        assert {m["book"] for m in new_rows} <= set(NEW_BOOKS)
        assert len(live) == len(base) - 1 + len(new_rows)

    def test_new_books_matches_have_provenance(self):
        """新 3 书入榜对局逐条可对质：layer/trust/via/book/loc/scene/s 齐备；
        方向自洽（s ∈ [0,1]，outcome 与 s 离散化一致）；若某书 0 场入榜 →
        meta.field_gaps 必须如实声明（不得静默）。"""
        live = self._live()
        by_book = {}
        for m in live["matches"]:
            by_book.setdefault(m["book"], []).append(m)
        for m in by_book.get("散花女侠", []) + by_book.get("联剑风云录", []) + \
                by_book.get("冰魄寒光剑", []):
            for k in ("layer", "trust", "via", "book", "loc", "scene", "s", "outcome"):
                assert m.get(k) is not None, m
            assert m["layer"] in ("L1", "L2") and m["via"] in (
                "事件方向动词", "事件方向outcome", "词表近名兜底", "平词")
            assert 0 <= m["s"] <= 1.0
            exp = "win" if m["s"] >= 0.75 else ("loss" if m["s"] <= 0.35 else "draw")
            assert m["outcome"] == exp, m
        gaps = set(live["meta"].get("field_gaps") or [])
        for b in NEW_BOOKS:
            if len(by_book.get(b, [])) == 0:
                assert b in gaps, f"{b} 0 场入榜必须 field_gaps 声明"
            else:
                assert b not in gaps

    def test_cleanlog_scope_and_sources(self):
        """cleanlog：scope/books/event_source 键齐备；kept L1+L2 == matches 总数（三通道对账）；
        F1 新增 dropped 键在案。"""
        live = self._live()
        log = json.loads((SITE_DATA / "ratings-cleanlog.json").read_text(encoding="utf-8"))
        assert log.get("scope") == "tianshan-demo"
        assert set(NEW_BOOKS) <= set(log.get("books") or [])
        esrc = log.get("event_source") or {}
        for b in NEW_BOOKS:
            assert esrc.get(b) == "registry-events"
        for b in OLD_BOOKS:
            assert esrc.get(b) == "kb-events"
        assert log["kept"]["L1"] + log["kept"]["L2"] == len(live["matches"])
        for k in ("reg_single_side", "reg_non_person"):
            assert k in log["dropped"]
        es = live["meta"].get("event_source") or {}
        assert es.get("散花女侠") == "registry-events"

    def test_ratings_recomputed_with_new_books(self):
        """ratings 全量重算：meta.books 含新 3 书（有对局者）；新 3 书人物在 players
        （per_book 榜域前提）；engine=whr。"""
        r = json.loads((SITE_DATA / "ratings.json").read_text(encoding="utf-8"))
        assert r["meta"]["engine"] == "whr"
        live = self._live()
        new_books_with_matches = ({m["book"] for m in live["matches"]} & set(NEW_BOOKS))
        assert new_books_with_matches <= set(r["meta"]["books"])
        names = {p["name"] for p in r["players"]}
        hits = [n for n in ("张玉虎", "龙剑虹", "于承珠", "桂华生") if n in names]
        assert len(hits) >= 2, f"新 3 书代表人物在榜不足（实测 {hits}）"

    def test_calibration_recomputed_and_note_declares_direction_fix(self):
        """calibration 真复算：precision 与「TSV × live matches」独立重算一致（防回填失真）；
        note 声明抽检覆盖口径与 TSV 系方向修正前副本（待人工重标，非自动裁决退步）。"""
        import csv
        r = json.loads((SITE_DATA / "ratings.json").read_text(encoding="utf-8"))
        live = self._live()
        by_id = {m["id"]: m for m in live["matches"]}
        rows = list(csv.DictReader(open(REPO_ROOT / "kb" / "校订" / "武评抽检.tsv",
                                        encoding="utf-8-sig"), delimiter="\t"))
        agree = sampled = 0
        for row in rows:
            m = by_id.get(row.get("id"))
            if m is None:
                continue
            sampled += 1
            if (row.get("outcome") or "").strip() == (m.get("outcome") or "").strip():
                agree += 1
        cal = r["meta"]["calibration"]
        assert cal["sampled"] == sampled and sampled == 99        # G1：1 场随人名归并退场
        assert cal["precision"] == round(agree / sampled, 4)
        assert "抽检覆盖旧事件层 4 书场次" in cal["note"]
        assert "方向修正" in cal["note"]
