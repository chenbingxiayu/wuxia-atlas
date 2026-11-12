# -*- coding: utf-8 -*-
"""F5 · 名物型命题第六篇《游龙剑流转记》（wanderer-sword，template=artifact）测试。

对应《专栏页重构设计.md》§四（五段式）/ §五（模板注册表 template 含 artifact）/ §十（名物篇挂账候选
——用户裁定解除挂账，editorial 文案由 agent 原创生成，L0 纪律）。

只测纯函数与 site/data 已产物（同 test_stories_v2 风格），不写 site/data。
被测对象（scripts/build_stories.py F5 扩展）：
  STORIES['wanderer-sword']   {template:'artifact', subject:'游龙剑', book:'七剑下天山'(主书), tag:'名物'}
  slice_artifact              weapons.json 游龙剑 chain → per_chapter（流转事件序列）+ markers（dir 关键点）
  chart_spec('flow')          横向流转时间线图纸：nodes==chain 事件数，edges==dir 方向边
  editorial_for               原创文案（thesis/reads/evidence/method_note/teaser）+ 实算数字

口径固化（测试即规范）：
  - 数据源只读 site/data/weapons.json 游龙剑条目（artifacts-v1 · rev17 编年序）——切片链序
    与 weapons.json chain 逐边一致（抽首/中/末 3 边对账），不碰数据源；
  - per_chapter 行 = 流转事件（c=编年序号 seq/book/ch/loc/verb/frm/to/persons/name/suspect/w）；
    frm/to 仅 dir 方向边有值（无 dir 不推断归属——名物谱口径）；
  - chart.kind='flow'：nodes=11==len(chain)，lanes=链内书序，edges=dir 边（3 条，带箭头文案）；
  - editorial 数字实算：命题/teaser 中的数字 == 切片统计（11 段/7 任/4 书/4 毁记/3 方向边）；
  - L0：无原文引文——evidence 定位符指向的 tagged 行不做长片段复述（14 字滑窗守护）。
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "wuxia-kb" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_stories  # noqa: E402

SITE_DATA = REPO_ROOT / "site" / "data"
SID = "wanderer-sword"

# rev17 weapons.json 游龙剑 chain 抽样对账边（首/中/末——编年序回归守护）
SAMPLE_EDGES = [
    {"i": 0, "verb": "夺", "loc": "5:7", "book": "七剑下天山"},
    {"i": 7, "verb": "赠", "loc": "14:25", "book": "七剑下天山"},
    {"i": 10, "verb": "夺", "loc": "24:15", "book": "江湖三女侠"},
]


def _weapon_entry() -> dict:
    d = json.loads((SITE_DATA / "weapons.json").read_text(encoding="utf-8"))
    hit = [w for w in d["weapons"] if w.get("canonical") == "游龙剑"]
    assert hit, "weapons.json 缺游龙剑条目（数据源基线）"
    return hit[0]


def _bai_fa_slice():
    return json.loads((SITE_DATA / "atlas" / "白发魔女传.json").read_text(encoding="utf-8"))


def _real_dossiers():
    return json.loads((SITE_DATA / "dossiers.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def payload() -> dict:
    out = dict(build_stories.story_payloads(_bai_fa_slice(), _real_dossiers(), scope=None))
    assert SID in out, "wanderer-sword 未产出（切片器/editorial 缺失？）"
    return out[SID]


@pytest.fixture(scope="module")
def weapon() -> dict:
    return _weapon_entry()


# ================================================================ 1. 注册表（§五：artifact 模板入册）
class TestRegistry:
    def test_wanderer_sword_registered(self):
        """wanderer-sword 入册：template='artifact'（六篇唯一名物）、subject='游龙剑'、tag='名物'（用户词）。"""
        cfg = build_stories.STORIES.get(SID)
        assert cfg, "STORIES 缺 wanderer-sword"
        assert cfg["template"] == "artifact"
        assert cfg["subject"] == "游龙剑"
        assert cfg["tag"] == "名物"
        assert cfg["book"] == "七剑下天山"  # 多书流转，book=主书（跨书说明走 editorial/页面）
        assert cfg["title"] and "游龙剑" in cfg["title"]

    def test_old_five_orders_untouched(self):
        """旧五篇注册零扰动：order 1–5 与模板不变——F5 只追加不重排（回归红线）。"""
        old = {"temperature-curve": ("relation", 1), "growth-curve": ("growth", 2),
               "ling-weifeng": ("growth", 3), "chu-zhaonan": ("growth", 4), "lv-siniang": ("growth", 5)}
        for sid, (tpl, order) in old.items():
            cfg = build_stories.STORIES[sid]
            assert cfg["template"] == tpl and cfg["order"] == order, sid
        assert build_stories.STORIES[SID]["order"] == 6

    def test_payload_set_is_six(self):
        """story_payloads 全量口径产出六篇（旧五 + wanderer-sword）。"""
        out = dict(build_stories.story_payloads(_bai_fa_slice(), _real_dossiers(), scope=None))
        assert set(out) == {"temperature-curve", "growth-curve", "ling-weifeng",
                            "chu-zhaonan", "lv-siniang", SID}


# ================================================================ 2. 切片：链序与 weapons.json 一致
class TestSliceArtifact:
    def test_chain_length_and_sample_edges(self, payload, weapon):
        """per_chapter=chain 事件序列：长度==len(chain)；首/中/末 3 边 编年序/书/回/动词 逐字段一致。"""
        rows = payload["per_chapter"]
        chain = weapon["chain"]
        assert len(rows) == len(chain) == 11
        for s in SAMPLE_EDGES:
            r, e = rows[s["i"]], chain[s["i"]]
            assert (r["book"], r["verb"]) == (e["book"], e["verb"]), f"seq{s['i'] + 1} 书/动词漂移"
            assert f'{int(e["loc"].split(":")[0]):03d}:{int(e["loc"].split(":")[1]):03d}' == r["loc"]
            assert set(e["persons"]) == set(r["persons"])

    def test_row_shape_and_no_invented_attribution(self, payload):
        """行契约：c/seq/book/ch/loc/verb/persons/name 齐；frm/to 仅 dir 边有值（无方向不推断归属）。"""
        rows = payload["per_chapter"]
        assert [r["c"] for r in rows] == list(range(1, len(rows) + 1))  # c=编年序号
        for r in rows:
            for key in ("seq", "book", "ch", "loc", "verb", "persons", "name", "suspect", "w"):
                assert key in r, f"行缺 {key}：{r}"
            assert re.fullmatch(r"\d{3}:\d{3}", r["loc"])
            if r.get("dir"):
                assert r["frm"] == r["dir"]["who"][0] and r["to"] == r["dir"]["who"][1]
            else:
                assert r.get("frm") is None and r.get("to") is None, "无 dir 边不得推断 from→to"

    def test_suspect_destroyed_edges(self, payload):
        """毁记折叠口径：4 条 verb=毁 全部 suspect=True（rev17 证伪标记），且不入 dir 方向边。"""
        rows = payload["per_chapter"]
        destroyed = [r for r in rows if r["verb"] == "毁"]
        assert len(destroyed) == 4
        assert all(r["suspect"] for r in destroyed)
        assert not any(r.get("dir") for r in destroyed)

    def test_direction_edges_match_weapons(self, payload, weapon):
        """dir 方向边 3 条：kind/who 与 weapons.json dir 逐边一致；方向文案 = who[0] → kind → who[1]。"""
        got = {(r["loc"]): (r["dir"]["kind"], tuple(r["dir"]["who"]))
               for r in payload["per_chapter"] if r.get("dir")}
        expect = {(f'{int(e["loc"].split(":")[0]):03d}:{int(e["loc"].split(":")[1]):03d}'):
                  (e["dir"]["kind"], tuple(e["dir"]["who"])) for e in weapon["chain"] if e.get("dir")}
        assert got == expect
        assert len(got) == 3
        arrow = {loc: f"{who[0]} → {kind} → {who[1]}" for loc, (kind, who) in got.items()}
        assert arrow["005:007"] == "凌未风 → 夺 → 楚昭南"
        assert arrow["014:025"] == "晦明禅师 → 传 → 楚昭南"
        assert arrow["024:015"] == "冯瑛 → 夺 → 车辟邪"

    def test_markers_key_flow_points(self, payload):
        """markers=关键流转点（dir 边定位符必在）；loc 均出自 chain；c=对应事件序号。"""
        marks = payload["markers"]
        assert marks, "markers 空"
        locs = {r["loc"]: r["c"] for r in payload["per_chapter"]}
        assert {m["loc"] for m in marks} <= set(locs)
        assert {"005:007", "014:025", "024:015"} <= {m["loc"] for m in marks}
        for m in marks:
            assert m["c"] == locs[m["loc"]] and m["label"]

    def test_summary_stats_match_weapons(self, payload, weapon):
        """summary 实算：n_chain/n_hold/n_books/n_destroyed/n_dir 与 weapons.json 条目实数一致。"""
        s = payload["summary"]
        assert s["n_chain"] == len(weapon["chain"]) == 11
        assert s["n_hold"] == len(weapon["holders"]) == 7
        assert s["n_books"] == len(weapon["books"]) == 4
        assert s["n_destroyed"] == sum(1 for e in weapon["chain"] if e["verb"] == "毁") == 4
        assert s["n_dir"] == sum(1 for e in weapon["chain"] if e.get("dir")) == 3
        assert s["end_state"] == weapon["end_state"]["note"]


# ================================================================ 3. chart flow 图纸
class TestChartFlow:
    def test_flow_chart_structure(self, payload):
        """kind='flow'：nodes==chain 事件数（11）；lanes=链内书出现序；节点全挂定位符。"""
        ch = payload["chart"]
        assert ch["kind"] == "flow"
        rows = payload["per_chapter"]
        assert len(ch["nodes"]) == len(rows) == 11
        books_in_order = list(dict.fromkeys(r["book"] for r in rows))
        assert [l["book"] for l in ch["lanes"]] == books_in_order == ["七剑下天山", "江湖三女侠"]
        for n in ch["nodes"]:
            assert n["loc"] and n["verb"] and isinstance(n["seq"], int)
        suspect = {n["loc"] for n in ch["nodes"] if n.get("suspect")}
        assert suspect == {"006:069", "006:125", "006:139", "007:123"}

    def test_flow_edges_directional(self, payload):
        """flow edges=dir 方向边（3 条），每条带箭头文案（who → kind → who）与定位符。"""
        edges = payload["chart"]["edges"]
        assert len(edges) == 3
        for e in edges:
            assert e["label"] == f'{e["who"][0]} → {e["kind"]} → {e["who"][1]}'
            assert re.fullmatch(r"\d{3}:\d{3}", e["loc"])
        assert "凌未风 → 夺 → 楚昭南" in {e["label"] for e in edges}


# ================================================================ 4. editorial 文案（原创 L0 + 实算数字）
class TestEditorialArtifact:
    def test_five_sections_present(self, payload):
        """五段式数据侧齐：thesis/reads(3 问)/evidence(4–6 条)/method_note(含复跑+数据源)/teaser。"""
        ed = payload["editorial"]
        for key in ("thesis", "reads", "evidence", "method_note", "teaser"):
            assert ed.get(key), f"editorial 缺 {key}"
        assert len(ed["reads"]) == 3
        assert all(set(qa) == {"q", "a"} and qa["q"] and qa["a"] for qa in ed["reads"])
        assert 4 <= len(ed["evidence"]) <= 6
        assert "build_stories.py" in ed["method_note"] and "weapons.json" in ed["method_note"]

    def test_thesis_numbers_match_slice(self, payload):
        """命题数字实算：命题句中的 11/7/4/4 与切片 summary 逐一相等（数字==切片数）。"""
        th = payload["editorial"]["thesis"]
        s = payload["summary"]
        for n in (s["n_chain"], s["n_hold"], s["n_books"], s["n_destroyed"]):
            assert str(n) in th, f"命题缺实算数字 {n}：{th}"
        # 命题可判真伪：断言核心词在场（退场/证伪/长寿）
        assert "证伪" in th and ("长寿" in th or "退场" in th)

    def test_reads_consistent_with_slice(self, payload):
        """读图三问与切片/口径一致：毁记 4 条证伪（答案含 007:123→014:25 反证链）、
        暂持不入谱（口径词）、末见持有 vs 永久归属（不推断）。"""
        ed = payload["editorial"]
        qa_text = "".join(qa["q"] + qa["a"] for qa in ed["reads"])
        assert "4" in qa_text and "证伪" in qa_text          # 毁边问题：数字与口径
        assert "暂" in qa_text and "持有" in qa_text          # 借与暂持问题
        assert "末见持有" in qa_text and "永久归属" in qa_text  # 归宿问题
        assert "推断" in qa_text                              # 口径诚实栏
        # 毁后仍传世的反证链：最后一次毁记 007:123 之后是 014:025 明文
        rows = payload["per_chapter"]
        i7 = next(i for i, r in enumerate(rows) if r["loc"] == "007:123")
        assert rows[i7 + 1]["loc"] == "014:025"

    def test_evidence_locs_verifiable(self, payload, weapon):
        """证据链 4–6 条：loc 合法且可对质——铸边 028:025 在白发覆盖章；dir 边 005:007/014:025/024:015 必在；
        chain locs 与 evidence locs 同源；evidence 带书名字段（跨书回目链接用）。"""
        ev = payload["editorial"]["evidence"]
        assert all(re.fullmatch(r"\d{3}:\d{3}", e["loc"]) and e["text"] for e in ev)
        assert all(e.get("book") for e in ev), "跨书证据须带 book 字段"
        books = weapon["books"]
        forge = [e for e in ev if e["book"] == "白发魔女传"]
        assert forge and int(forge[0]["loc"][:3]) in books["白发魔女传"]  # 028 ∈ 覆盖章
        chain_locs = {f'{int(e["loc"].split(":")[0]):03d}:{int(e["loc"].split(":")[1]):03d}'
                      for e in weapon["chain"]}
        ev_locs = {e["loc"] for e in ev}
        assert {"005:007", "014:025", "024:015"} <= ev_locs
        assert ev_locs - {"028:025"} <= chain_locs  # 非铸边证据全部出自 chain

    def test_teaser_computed_numbers(self, payload):
        """teaser 实算句：7 任持有者 / 11 段明文 / 4 书 全部来自切片（决策 5）。"""
        t = payload["editorial"]["teaser"]
        s = payload["summary"]
        for n in (s["n_hold"], s["n_chain"], s["n_books"]):
            assert str(n) in t, f"teaser 缺实算数字 {n}：{t}"

    def test_l0_no_verbatim_corpus(self, payload):
        """L0 纪律：editorial 全部文本不复制原文——对 evidence/markers 定位符指向的 tagged 行
        做 14 字滑窗抽查，命中即判违规；payload 无 excerpt 类字段。"""
        ed = payload["editorial"]
        texts = [ed["thesis"], ed["method_note"], ed["teaser"]] + \
                [qa["q"] + qa["a"] for qa in ed["reads"]] + [e["text"] for e in ed["evidence"]]
        blob = "".join(texts)
        assert "excerpt" not in json.dumps(payload, ensure_ascii=False)
        locs = [e["loc"] for e in ed["evidence"]]
        books = {e.get("book") or payload["book"] for e in ed["evidence"]}
        for book in books:
            tag_dir = REPO_ROOT / "kb" / "tagged" / book
            assert tag_dir.is_dir()
        for loc in locs:
            ch, ln = int(loc[:3]), int(loc[4:])
            f = next((REPO_ROOT / "kb" / "tagged" /
                      next(e["book"] for e in ed["evidence"] if e["loc"] == loc)
                      ).glob(f"{ch:03d}_*.tagged.md"), None)
            assert f, f"{loc} tagged 文件缺失"
            line = f.read_text(encoding="utf-8").splitlines()[ln - 1]
            plain = re.sub(r"〖[^〗]*〗|⟦[^⟧]*⟧", "", line)
            plain = re.sub(r"[，。：；！？“”‘’（）《》—…\s]", "", plain)
            for i in range(0, max(len(plain) - 13, 0)):
                win = plain[i:i + 14]
                assert win not in blob, f"L0 违规：{loc} 原文片段「{win}」进入 editorial"


# ================================================================ 5. scope gate（W0-T3b 契约沿用）
class TestScopeGate:
    def test_scope_gate_by_main_book(self):
        """gate 按主书：scope 含七剑 → 产出；scope 只含三女侠 → 不产出（book=主书口径）。"""
        qijian = {"profile": "p", "books": ["七剑下天山"]}
        out = dict(build_stories.story_payloads(_bai_fa_slice(), _real_dossiers(), scope=qijian))
        assert SID in out
        nv = {"profile": "p", "books": ["江湖三女侠"]}
        out2 = dict(build_stories.story_payloads(_bai_fa_slice(), _real_dossiers(), scope=nv))
        assert SID not in out2
        assert "lv-siniang" in out2

    def test_weapons_source_missing_honest_skip(self, tmp_path, monkeypatch):
        """weapons.json 缺失/无游龙剑 → 该篇诚实跳过（宁缺毋滥），其余篇不受影响。"""
        monkeypatch.setattr(build_stories, "SITE_DATA", tmp_path)
        monkeypatch.setattr(build_stories, "KB", tmp_path)
        (tmp_path / "atlas").mkdir()
        (tmp_path / "atlas" / "白发魔女传.json").write_text(
            json.dumps(_bai_fa_slice(), ensure_ascii=False), encoding="utf-8")
        (tmp_path / "qa-events").mkdir()
        for book in ("七剑下天山", "江湖三女侠"):
            src = SITE_DATA / "qa-events" / f"{book}.json"
            (tmp_path / "qa-events" / f"{book}.json").write_text(src.read_text(encoding="utf-8"),
                                                                 encoding="utf-8")
        out = build_stories.story_payloads({"chapters": 32, "persons": {}, "events": {}, "title": "白发魔女传"},
                                           {"dossiers": []}, scope=None, markers=[])
        assert SID not in {sid for sid, _ in out}
