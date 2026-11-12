# -*- coding: utf-8 -*-
"""D6 · 专栏 build_stories v2 泛化 + story-v2 契约 + 三篇扩编切片测试。

对应《专栏页重构设计.md》§四（五段式）/ §五（管线泛化）/ §六（三篇命题）/ §七（锚点同源）/ §十二（验收）。

只测纯函数与 site/data 已产物（同 W0-T3b 风格），不写 site/data。
被测对象（scripts/build_stories.py v2）：
  STORIES            {story_id: {template, subject, book, rivals?, title, tag}}  配置注册表
  story_payloads     v2 统一出口：五篇 story-v2 payload（scope gate 沿用 W0-T3b）
  slice_relation     双人共现极性切片（v1 temp_curve 参数化，零失真迁移）
  slice_growth       逐回主客切片（v1 growth_curve 参数化；known_end 改事件层）
  slice_density      复仇线密度切片（吕四娘篇：逐回对抗事件数）
  markers_for        锚点表取数（char_plots.json，主角锚点子集）
  known_end_of       事件层终局（last eventful chapter + 对手——修 S4"诛天德上人"）

口径固化（测试即规范）：
  - schema story-v2：{meta, story_id, template, editorial{thesis,reads,evidence,method_note,teaser},
                      per_chapter, markers, chart}；两篇旧文 per_chapter 与 v1 golden 逐字段一致（工程红线）。
  - markers 全部来自剧情锚点轨（char_plots.json），温度曲线 001:103 / 026:053 必须在表中可查。
  - 楚昭南锚点补录（editor=agent-D6）：char_plots 含楚昭南 ≥8 条（人物页剧情区点亮）。
  - 三篇新切片：凌未风（七剑 0–30 回 31 行，被囚窗 26–27 主客归零）、
                楚昭南（31 行，末回 29 客>主——伏诛）、
                吕四娘（三女侠 48 行密度，峰值 20 回 26 起、终章 48 回 5 起）。
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
import export_site_common as esc  # noqa: E402

SITE_DATA = REPO_ROOT / "site" / "data"
GOLDEN = json.loads(
    (Path(__file__).resolve().parent / "golden" / "stories_v1_migration.json").read_text(encoding="utf-8"))

# F5 扩编：第六篇名物型 wanderer-sword 入册（旧五篇篇名/口径不变——回归红线由 golden 守护）
ALL_SLUGS = ["temperature-curve", "growth-curve", "ling-weifeng", "chu-zhaonan", "lv-siniang",
             "wanderer-sword"]


def _bai_fa_slice():
    """真实白发魔女传 atlas 切片（v1 两篇的数据源）。"""
    return json.loads((SITE_DATA / "atlas" / "白发魔女传.json").read_text(encoding="utf-8"))


def _real_dossiers():
    return json.loads((SITE_DATA / "dossiers.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def payloads_all() -> dict:
    """全量口径（scope=None）五篇 payload——真实 site/data。"""
    out = dict(build_stories.story_payloads(_bai_fa_slice(), _real_dossiers(), scope=None))
    return out


# ================================================================ 1. 配置注册表（管线泛化）
class TestRegistry:
    def test_registry_shape_and_user_tags(self):
        """STORIES 六篇齐（F5 加名物篇）；每条含 template/subject/book/title/tag；tag 全用户词（无 B1/B6 内部编号）。"""
        assert set(build_stories.STORIES) == set(ALL_SLUGS)
        for sid, cfg in build_stories.STORIES.items():
            for key in ("template", "subject", "book", "title", "tag"):
                assert cfg.get(key), f"{sid} 缺 {key}"
            assert cfg["template"] in ("growth", "relation", "artifact")
            assert cfg["tag"] in ("关系", "成长", "名物"), f"{sid} tag 非用户词：{cfg['tag']}"
        assert build_stories.STORIES["temperature-curve"]["template"] == "relation"
        assert build_stories.STORIES["growth-curve"]["book"] == "白发魔女传"
        assert build_stories.STORIES["ling-weifeng"]["book"] == "七剑下天山"
        assert build_stories.STORIES["lv-siniang"]["book"] == "江湖三女侠"

    def test_pair_config_for_relation(self):
        """关系篇必须声明对手（rivals）——双人共现切片的参数化取数。"""
        assert build_stories.STORIES["temperature-curve"]["rivals"] == ["练霓裳"]
        assert build_stories.STORIES["temperature-curve"]["subject"] == "卓一航"


# ================================================================ 2. story-v2 契约
class TestSchemaV2:
    def test_five_payloads_schema(self, payloads_all):
        """全量口径五篇齐；schema=story-v2；story_id/template/editorial/per_chapter/markers/chart 齐。"""
        assert set(payloads_all) == set(ALL_SLUGS)
        for sid, p in payloads_all.items():
            assert p["meta"]["schema"] == "story-v2", sid
            assert p["meta"]["script"] == "scripts/build_stories.py"
            assert p["story_id"] == sid
            assert p["template"] == build_stories.STORIES[sid]["template"]
            assert isinstance(p["per_chapter"], list) and p["per_chapter"]
            assert isinstance(p["markers"], list)
            assert isinstance(p["chart"], dict) and p["chart"].get("kind")
        # scope meta（W0-T3b 契约沿用）：全量口径 meta 无 scope 键
        for sid, p in payloads_all.items():
            assert "scope" not in p["meta"]

    def test_editorial_five_sections(self, payloads_all):
        """五段式的数据侧：命题（thesis）/读图（reads 2–3 问）/证据链（evidence ≥3 带 loc）/方法（method_note）。"""
        for sid, p in payloads_all.items():
            ed = p["editorial"]
            for key in ("thesis", "reads", "evidence", "method_note", "teaser"):
                assert ed.get(key), f"{sid} editorial 缺 {key}"
            assert 2 <= len(ed["reads"]) <= 3
            for qa in ed["reads"]:
                assert set(qa) == {"q", "a"}, sid
                assert qa["q"] and qa["a"]
            assert len(ed["evidence"]) >= 3
            for ev in ed["evidence"]:
                assert re.fullmatch(r"\d{3}:\d{3}", ev["loc"]), f"{sid} evidence loc 非定位符：{ev}"
                assert ev["text"]
            # 复跑命令 + 数据版本号（诚实栏）
            assert "build_stories.py" in ed["method_note"]

    def test_teaser_contains_computed_number(self, payloads_all):
        """teaser 数字实算（决策 5）：温度篇 teaser 必含其冲突总数（131）。"""
        t = payloads_all["temperature-curve"]
        total_neg = sum(r["neg"] for r in t["per_chapter"])
        assert total_neg == 131
        assert str(total_neg) in t["editorial"]["teaser"]


# ================================================================ 3. markers 接锚点表（决策 4 / §七）
class TestMarkersFromAnchorTable:
    def test_temperature_markers_in_anchor_table(self, payloads_all):
        """温度曲线 markers 可在锚点表查得：练霓裳 001:103（劫镖初会）/ 026:053（一夜白头）。"""
        cp = json.loads((SITE_DATA / "char_plots.json").read_text(encoding="utf-8"))
        table_locs = {}
        for person, rec in cp["characters"].items():
            for pl in rec.get("plots", []):
                table_locs.setdefault(pl["loc"], set()).add(person)
        t = payloads_all["temperature-curve"]
        locs = [m["loc"] for m in t["markers"]]
        assert "001:103" in locs and "026:053" in locs
        for loc in locs:
            assert loc in table_locs, f"marker {loc} 不在锚点表"
            assert table_locs[loc] & {"卓一航", "练霓裳"}, f"marker {loc} 非本篇主角锚点"

    def test_new_story_markers_from_table(self, payloads_all):
        """三篇新文 markers 同源锚点表：凌未风含 025:078（冰崖蒙难）/029:008（迷宫脱囚）；
        楚昭南含 029:079（伏诛）；吕四娘含 048:041（内苑屠龙）。"""
        cp = json.loads((SITE_DATA / "char_plots.json").read_text(encoding="utf-8"))["characters"]
        expect = {
            "ling-weifeng": ("凌未风", {"025:078", "029:008", "030:073"}),
            "chu-zhaonan": ("楚昭南", {"029:079"}),
            "lv-siniang": ("吕四娘", {"048:041"}),
        }
        for sid, (person, must) in expect.items():
            table = {pl["loc"] for pl in cp[person]["plots"]}
            locs = {m["loc"] for m in payloads_all[sid]["markers"]}
            assert must <= locs, f"{sid} 缺锚点 {must - locs}"
            assert locs <= table, f"{sid} markers 超出 {person} 锚点表：{locs - table}"


# ================================================================ 4. 旧文迁移零失真（工程红线）
class TestV1Migration:
    def test_temperature_curve_zero_loss(self, payloads_all):
        """v2 temperature-curve per_chapter / shared_chapters / 关键 totals 与 v1 golden 逐字段一致。"""
        g = GOLDEN["temp-curve"]
        t = payloads_all["temperature-curve"]
        assert t["per_chapter"] == g["per_chapter"]
        assert t["shared_chapters"] == g["shared_chapters"]
        assert t["a"] == g["a"] and t["b"] == g["b"] and t["book"] == g["book"]
        assert [[m["c"], m["label"]] for m in t["markers"]] == g["markers_c_label"]

    def test_growth_curve_zero_loss(self, payloads_all):
        """v2 growth-curve per_chapter 与里程碑（known_end 除外——S4 修正项）与 v1 golden 一致。"""
        g = GOLDEN["growth-curve"]
        p = payloads_all["growth-curve"]
        assert p["per_chapter"] == g["per_chapter"]
        ms = p["milestones"]
        assert ms["first_dominant_chapter"] == g["milestones"]["first_dominant_chapter"]
        assert ms["first_kill_chapter"] == g["milestones"]["first_kill_chapter"]


# ================================================================ 5. known_end 修正（S4）
class TestKnownEnd:
    def test_event_layer_known_end(self, payloads_all):
        """growth-curve known_end 以事件层为准：含天龙上人、无诛天德上人（032 回终局对手）。"""
        ke = payloads_all["growth-curve"]["milestones"]["known_end"]
        assert "天龙上人" in ke
        assert "诛天德上人" not in ke
        assert ke.startswith("032")

    def test_known_end_helper_pure(self):
        """known_end_of 纯函数：空事件 → None；合成事件 → 末回 + 对手。"""
        events = {c: [] for c in range(1, 4)}
        assert build_stories.known_end_of(events, "甲") is None
        events[3] = [{"a": "甲", "b": "乙", "code": "◈"}, {"a": "甲", "b": "丙", "code": "◈"},
                     {"a": "甲", "b": "乙", "code": "▲"}]
        ke = build_stories.known_end_of(events, "甲")
        assert ke and ke.startswith("003") and "乙" in ke and "丙" in ke


# ================================================================ 6. 三篇新切片（§六命题卡）
class TestNewSlices:
    def test_ling_weifeng_prisoner_window(self, payloads_all):
        """凌未风篇：七剑 0–30 回 31 行；被囚窗 26–27 主客归零（合计 ≤1 起）；峰值 24（19/25 回）。"""
        rows = {r["c"]: r for r in payloads_all["ling-weifeng"]["per_chapter"]}
        assert sorted(rows) == list(range(0, 31))
        assert rows[26]["active"] == 0 and rows[26]["passive"] == 0
        assert rows[27]["active"] == 0 and rows[27]["passive"] == 1
        assert rows[25]["active"] == 24 and rows[19]["active"] == 23

    def test_chu_zhaonan_decline(self, payloads_all):
        """楚昭南篇：31 行；末回 29 客>主（伏诛于被动）；25 回主客持平（10/10）。"""
        rows = {r["c"]: r for r in payloads_all["chu-zhaonan"]["per_chapter"]}
        assert sorted(rows) == list(range(0, 31))
        assert rows[29]["passive"] > rows[29]["active"]
        assert rows[25]["active"] == 10 and rows[25]["passive"] == 10
        ms = payloads_all["chu-zhaonan"]["milestones"]
        assert ms["known_end"].startswith("029") and "易兰珠" in ms["known_end"]

    def test_lv_siniang_density(self, payloads_all):
        """吕四娘篇：三女侠 1–48 回 48 行；逐回密度=主+客；峰值 20 回 26 起、终章 48 回 5 起。"""
        p = payloads_all["lv-siniang"]
        rows = {r["c"]: r for r in p["per_chapter"]}
        assert sorted(rows) == list(range(1, 49))
        for r in p["per_chapter"]:
            assert r["active"] + r["passive"] == r["total"]
        assert rows[20]["total"] == 26 and rows[20]["active"] + rows[20]["passive"] == 26
        assert rows[48]["total"] == 5
        assert max(rows.values(), key=lambda r: r["total"])["c"] == 20


# ================================================================ 7. 年谱确日联动（吕四娘篇）
class TestAnnalsLinkage:
    def test_e1735_yuanxiao_in_evidence(self, payloads_all):
        """evidence 含 E-1735 元宵确日（047:001，雍正十三年 01-15）+ annals 联动字段。"""
        ev = payloads_all["lv-siniang"]["editorial"]["evidence"]
        hit = [e for e in ev if e["loc"] == "047:001"]
        assert hit, "缺 047:001 元宵确日证据"
        assert "01-15" in hit[0]["text"] and "E-1735" in hit[0]["text"]
        assert hit[0].get("annals"), "元宵确日证据缺 annals 联动标记"


# ================================================================ 8. scope gate（W0-T3b 契约沿用）
class TestScopeGate:
    def test_scope_filters_stories(self, tmp_path, monkeypatch):
        """scope 只含七剑 → 凌未风/楚昭南/游龙剑（主书=七剑）；只含三女侠 → 仅吕四娘篇。"""
        monkeypatch.setattr(build_stories, "SITE_DATA", SITE_DATA)  # 新切片读真实 qa-events
        qijian = {"profile": "p", "books": ["七剑下天山"]}
        out = dict(build_stories.story_payloads(_bai_fa_slice(), _real_dossiers(), scope=qijian))
        assert set(out) == {"ling-weifeng", "chu-zhaonan", "wanderer-sword"}
        nv = {"profile": "p", "books": ["江湖三女侠"]}
        out2 = dict(build_stories.story_payloads(_bai_fa_slice(), _real_dossiers(), scope=nv))
        assert set(out2) == {"lv-siniang"}
        for p in out.values():
            assert p["meta"]["scope"] == "p"

    def test_out_of_scope_empty(self, tmp_path, monkeypatch):
        """scope 不含白发 → 旧两篇不产出（v1 契约保持）；新篇事件层文件缺失 → 诚实跳过（宁缺毋滥）。"""
        monkeypatch.setattr(build_stories, "SITE_DATA", tmp_path)
        monkeypatch.setattr(build_stories, "KB", tmp_path)
        out = build_stories.story_payloads(_bai_fa_slice(), {"dossiers": []},
                                           scope={"profile": "p", "books": ["七剑下天山"]},
                                           markers=[])
        assert out == []


# ================================================================ 9. 楚昭南锚点补录（editor=agent-D6）
class TestChuZhaoNanAnchors:
    def test_char_plots_has_chuzhaonan(self):
        """char_plots 含楚昭南 ≥8 条（人物页剧情区点亮）；loc 格式合法；book ∈ 两书。"""
        cp = json.loads((SITE_DATA / "char_plots.json").read_text(encoding="utf-8"))
        plots = cp["characters"].get("楚昭南", {}).get("plots", [])
        assert len(plots) >= 8
        for pl in plots:
            assert re.fullmatch(r"\d{3}:\d{3}", pl["loc"])
            assert pl["book"] in ("塞外奇侠传", "七剑下天山")
            assert pl["name"] and pl["line"]
        chapters = sorted({int(p["loc"][:3]) for p in plots})
        assert chapters[-1] >= 29  # 伏诛锚点在末回段

    def test_chuzhaonan_anchor_locs_in_corpus(self):
        """补录锚点 tagged 核实：loc 指向的 tagged 行必含楚昭南或为该场景明文行。"""
        plots = json.loads((SITE_DATA / "char_plots.json").read_text(encoding="utf-8")
                           )["characters"]["楚昭南"]["plots"]
        cache = {}
        for pl in plots:
            ch, ln = int(pl["loc"][:3]), int(pl["loc"][4:])
            f = next((REPO_ROOT / "kb" / "tagged" / pl["book"]).glob(f"{ch:03d}_*.tagged.md"), None)
            assert f, f"{pl['loc']} tagged 文件缺失"
            lines = cache.setdefault(f, f.read_text(encoding="utf-8").splitlines())
            assert ln <= len(lines) and lines[ln - 1].strip(), f"{pl['loc']} 指向空行"


# ================================================================ 10. index 数据供给（决策 5）
class TestIndexSupply:
    def test_meta_copyright_and_generated(self, payloads_all):
        for sid, p in payloads_all.items():
            assert p["meta"]["generated"]
            assert "L0" in p["meta"]["copyright"]


def test_all_payloads_have_subject(payloads_all):
    """回归（2026-11-13）：subject 必须透传全部模板——缺者会在专栏页渲染 /characters/undefined/ 死链（验收扫描 links 检查抓到 5 处）。"""
    for sid, p in payloads_all.items():
        assert p.get("subject"), f"{sid} payload 缺 subject"
        assert "undefined" not in json.dumps(p, ensure_ascii=False)
