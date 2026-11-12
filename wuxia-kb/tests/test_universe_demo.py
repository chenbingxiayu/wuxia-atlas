# -*- coding: utf-8 -*-
"""W0-T4 · universe 演示口径重建 + 种子 canonical 映射 + atlas/state.json 接管测试
（天山演示版总体方案 §〇/§1.2，2026-11-08；用户裁定：天山演示版宇宙 = 单条线路「天山系列」）。

只测纯函数与真实只读源数据（kb/系列谱系考订表.json、config/site_scope.json），
不跑整管线、不写 site/data（staging characters.json 只读）。
被测对象（W0-T4 新增/改造）：
  export_site_gazetteer_universe  build_universe(scope=…, canon_index=…) 演示单线重建 +
                                  seeds 行经书∩scope 过滤 + canonical 映射（命中/降级）+
                                  演示新增种子（霍天都/凌云凤/易兰珠/吕四娘）+
                                  open_questions 关涉书 ⊆ scope 过滤 + 编年谱缺佚星标归书；
                                  load_canonical_index / resolve_seed_canonical（A2 对照）；
                                  build_state（atlas/state.json 接管，消费键兼容）
  export_site_books_chapters      build_books(scope=…) missing_works 缺佚书 scope 裁剪
  scripts/build_atlas_slices.py   顶部废弃标注（指向 EX-7，不删文件）

口径固化（测试即规范）：
  - 演示口径（--scope tianshan-demo）：lines = 单线「天山系列」（色沿用 #c0392b），成员 =
    用户裁定 2026-11-08 顺序（散花女侠→联剑风云录→白发魔女传→塞外奇侠传→七剑下天山→
    冰魄寒光剑→江湖三女侠；散花/联剑自明代系列并入），成员字段自原 lines join（照搬），
    order 按演示顺序重排、order_conf=「用户裁定 2026-11-08」（order/evidence 缺失 → user_ruling）。
  - 全量口径（scope=None）逐字段不变（方案 R6）：6 线结构、seeds 22 条、open_questions 7 条。
  - seeds canonical：映射成功 → 加 canonical 字段；失败（对照索引缺失/无 scope 出现）→ 保持
    纯文本（universe 页已支持降级）；新增种子 note 为原创编辑内容（L0，无原文引文）。
  - atlas/state.json：EX-7 接管（scope=7 书演示顺序；全量=BOOKS 契约顺序）；消费键兼容
    MapTrail.tsx Manifest（meta.note + books[].slug/title/chapters/era/era_conf/leads）与
    build_qa_index.select_titles（books[].title）。
"""
import json
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（被测模块依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_common as esc  # noqa: E402
import export_site_gazetteer_universe as exu  # noqa: E402
import export_site_books_chapters as exb  # noqa: E402

PROFILE = "tianshan-demo"
SCOPE = esc.load_scope(PROFILE)
# 用户裁定 2026-11-08：天山演示版 7 部顺序（= site_scope.json 配置顺序，不得重排）
DEMO_ORDER = ["散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
              "七剑下天山", "冰魄寒光剑", "江湖三女侠"]
ORDER_RULING = "用户裁定 2026-11-08"


def _series() -> dict:
    """真实只读源数据 kb/系列谱系考订表.json（EX-7 的 universe 四节唯一来源）。"""
    return exu.load_json(exu.KB / "系列谱系考订表.json")


def _demo_payload(series=None, canon_index="default"):
    if series is None:
        series = _series()
    if canon_index == "default":
        canon_index = exu.load_canonical_index()
    return exu.build_universe({"series": series}, scope=SCOPE, canon_index=canon_index)


# ================================================================ 1. 演示单线（lines 重建）
class TestDemoLine:
    """scope=tianshan-demo：lines 重建为单线「天山系列」（用户裁定顺序；散花/联剑并入）。"""

    def test_single_line_structure_and_order(self):
        payload, _st = _demo_payload()
        assert len(payload["lines"]) == 1
        ln = payload["lines"][0]
        assert ln["line"] == "天山系列"                      # 线名沿用「天山系列」
        assert ln["color"] == "#c0392b"                      # 沿用原天山线色
        assert [m["book"] for m in ln["members"]] == DEMO_ORDER
        assert [m["order"] for m in ln["members"]] == [1, 2, 3, 4, 5, 6, 7]

    def test_order_conf_user_ruling(self):
        payload, _st = _demo_payload()
        for m in payload["lines"][0]["members"]:
            assert m["order_conf"] == ORDER_RULING           # 顺序置信 = 用户裁定

    def test_members_joined_from_source_lines(self):
        """成员字段照搬原 lines 数据：散花/联剑自明代系列 join，其余自原天山线 join。"""
        series = _series()
        src = {}
        for ln in series["lines"]:
            for m in ln["members"]:
                src.setdefault(m["book"], m)
        payload, _st = _demo_payload(series)
        members = {m["book"]: m for m in payload["lines"][0]["members"]}
        for b in DEMO_ORDER:                                  # 全字段照搬（order/order_conf 除外）
            for k in ("conf", "missing", "year", "era", "leads", "kb_status", "why", "evidence"):
                assert members[b][k] == src[b][k], (b, k)
        # 并入实证：散花/联剑来自明代系列（year 1960/1961；evidence 非空）
        assert members["散花女侠"]["year"] == 1960 and members["散花女侠"]["evidence"]
        assert members["联剑风云录"]["year"] == 1961 and members["联剑风云录"]["evidence"]

    def test_full_caliber_six_lines_unchanged(self):
        """全量口径（scope=None）：6 线结构逐字段不变（方案 R6）。

        D2（2026-11-10）增补：lines[].reading_guide 是"线"属性人工编辑轨，两口径都消费
        同一行——全量口径下天山线（名带括注）多挂 reading_guide 一个键，其余字段仍逐字段
        一致（唯一允许的新键，其余 5 线不得有任何新增键）。
        """
        series = _series()
        assert len(series["lines"]) == 6                      # 源数据基线（6 线）
        payload, st = exu.build_universe({"series": series})
        assert len(payload["lines"]) == 6
        for src_ln, out_ln in zip(series["lines"], payload["lines"]):
            extra = set(out_ln) - set(src_ln)                 # 允许的新键白名单
            if exu.guide_line_key(src_ln["line"]) == exu.guide_line_key(exu.DEMO_LINE_NAME):
                assert extra == {"reading_guide"}             # 天山线：仅 reading_guide（D2）
                assert set(out_ln["reading_guide"]) <= {"start", "peak", "skip", "note"}
            else:
                assert extra == set()                         # 其余 5 线逐字段不变
            assert out_ln == dict(src_ln, **{k: out_ln[k] for k in extra})
        assert "scope" not in payload["meta"]
        assert st["reading_guide_attached"] == 1              # D2 统计：全量也挂载 1 行


class TestDemoLineFallback:
    """演示单线 join 兜底：evidence 缺失 / 书目不在任何线 → order_conf=user_ruling。"""

    def _series_min(self):
        evidence = [{"edge": "甲→乙", "loc": "白发魔女传·021:93", "kind": "authorial",
                     "snippet": "（synthetic）"}]
        return {"lines": [
            {"line": "天山系列（清代主脉）", "color": "#c0392b", "members": [
                {"book": "白发魔女传", "order": 1, "conf": "ok", "missing": False,
                 "year": 1957, "era": "明末", "leads": ["卓一航"], "kb_status": "已点亮",
                 "why": [], "evidence": evidence}]},
            {"line": "明代系列", "color": "#2980b9", "members": [
                {"book": "联剑风云录", "order": 4, "conf": "ok", "missing": False,
                 "year": 1961, "era": "明·成化", "leads": ["张玉虎"], "kb_status": "待建",
                 "why": [], "evidence": []},                   # evidence 空 → user_ruling
                {"book": "散花女侠", "order": 3, "conf": "ok", "missing": False,
                 "year": 1960},                                # 无 era/leads/evidence → user_ruling
            ]},
        ]}

    def test_missing_evidence_gets_user_ruling(self):
        payload, _st = exu.build_universe({"series": self._series_min()},
                                          scope=SCOPE, canon_index=None)
        members = {m["book"]: m for m in payload["lines"][0]["members"]}
        assert members["联剑风云录"]["order_conf"] == "user_ruling"
        assert members["散花女侠"]["order_conf"] == "user_ruling"
        assert members["白发魔女传"]["order_conf"] == ORDER_RULING
        assert members["白发魔女传"]["order"] == 3             # 演示顺序重排（原 order=1）

    def test_book_absent_from_source_lines_synthesized(self):
        payload, _st = exu.build_universe({"series": self._series_min()},
                                          scope=SCOPE, canon_index=None)
        members = {m["book"]: m for m in payload["lines"][0]["members"]}
        m = members["七剑下天山"]                              # 合成源数据无此书成员
        assert m["order"] == 5 and m["missing"] is True
        assert m["order_conf"] == "user_ruling"


# ================================================================ 2. 换乘站种子（过滤 + canonical + 新增）
class TestSeedsScope:
    def test_kept_seeds_intersect_scope(self):
        """行经书 ∩ scope 非空的种子保留，scope 外种子（金世遗/檀羽冲等宋代与乾隆后线）被裁。"""
        series = _series()
        payload, st = exu.build_universe({"series": series}, scope=SCOPE, canon_index=None)
        names = [s["name"] for s in payload["interchange_seeds"]]
        kept = [s["name"] for s in series["interchange_seeds"]
                if set(s.get("books") or []) & set(DEMO_ORDER)]
        dropped = [s["name"] for s in series["interchange_seeds"]
                   if not (set(s.get("books") or []) & set(DEMO_ORDER))]
        assert len(series["interchange_seeds"]) == 22          # 源基线
        for n in kept:
            assert n in names
        for n in dropped:
            assert n not in names
        assert st["seeds_kept"] == len(kept) == 11

    def test_new_seeds_huo_tian_du_ling_yun_feng(self):
        """新增霍天都/凌云凤两条种子：行经书=散花/联剑/白发，note 写明天山派创派（L0 原创编辑）。"""
        payload, _st = _demo_payload()
        seeds = payload["interchange_seeds"]
        names = [s["name"] for s in seeds]
        assert names[:2] == ["霍天都", "凌云凤"]               # 系列起点人物置首
        huo, ling = seeds[0], seeds[1]
        for s in (huo, ling):
            assert s["books"] == ["散花女侠", "联剑风云录", "白发魔女传"]
            assert "天山派创派" in s["note"]
            assert "《" not in s["note"] and "》" not in s["note"]   # L0：无原文引文

    def test_demo_seed_order_and_no_duplicates(self):
        payload, _st = _demo_payload()
        names = [s["name"] for s in payload["interchange_seeds"]]
        assert len(names) == len(set(names))                   # 无重复
        assert names[-2:] == ["易兰珠", "吕四娘"]              # 演示覆盖种子收尾（终点侧）

    def test_demo_covers_required_persons(self):
        """演示种子至少覆盖 9 个必有人物（用户指定名单）。"""
        payload, _st = _demo_payload()
        names = {s["name"] for s in payload["interchange_seeds"]}
        for n in ("晦明禅师（岳鸣珂）", "练霓裳（白发魔女）", "卓一航", "杨云骢",
                  "飞红巾（哈玛雅）", "凌未风", "易兰珠", "桂华生", "吕四娘"):
            assert n in names, n

    def test_seeds_canonical_resolved(self):
        """canonical 映射（真实 EX-2 产物对照）：复合名括注两侧均可解析；新种子直接命中。"""
        if exu.load_canonical_index() is None:
            pytest.skip("characters.json 不可用（staging 与 site/data 均缺失）")
        payload, st = _demo_payload()
        canon = {s["name"]: s.get("canonical") for s in payload["interchange_seeds"]}
        assert canon["晦明禅师（岳鸣珂）"] == "岳鸣珂"          # 括注内名 = canonical
        assert canon["练霓裳（白发魔女）"] == "练霓裳"          # 括注外名 = canonical
        assert canon["飞红巾（哈玛雅）"] == "哈玛雅"            # 展示名 → 规范名
        for n in ("卓一航", "杨云骢", "凌未风", "桂华生", "霍天都", "凌云凤",
                  "易兰珠", "吕四娘", "辛龙子", "桂仲明", "楚昭南", "张丹枫"):
            assert canon[n], n                                  # 全部种子 canonical 命中
        assert st["seeds_canonical"] == st["seeds_total"] == 15

    def test_seeds_canonical_degrade_without_index(self):
        """对照索引缺失 → 全部种子保持纯文本（不加 canonical 字段；页面已支持降级）。"""
        payload, st = exu.build_universe({"series": _series()}, scope=SCOPE, canon_index=None)
        for s in payload["interchange_seeds"]:
            assert "canonical" not in s
        assert st["seeds_canonical"] == 0
        assert st["seeds_total"] == 15                         # 11 源种子 + 4 演示新增

    def test_full_caliber_seeds_unchanged(self):
        series = _series()
        payload, _st = exu.build_universe({"series": series})
        assert payload["interchange_seeds"] == series["interchange_seeds"]   # 22 条逐字段一致


class TestResolveCanonical:
    """resolve_seed_canonical 单元：括注拆解 / 别名 / scope 出现门 / 无索引降级。"""

    @staticmethod
    def _idx():
        return {"by_name": {"岳鸣珂": "岳鸣珂", "晦明禅师": "岳鸣珂", "飞红巾": "哈玛雅",
                            "哈玛雅": "哈玛雅", "凌未风": "凌未风", "卓一航": "卓一航"},
                "books_of": {"岳鸣珂": ["白发魔女传", "塞外奇侠传"],
                             "哈玛雅": ["塞外奇侠传", "七剑下天山"],
                             "凌未风": ["七剑下天山"],
                             "卓一航": ["白发魔女传"]},
                "source": "synthetic"}

    def test_parenthesized_seed_resolves(self):
        idx = self._idx()
        assert exu.resolve_seed_canonical("晦明禅师（岳鸣珂）", idx, SCOPE) == "岳鸣珂"
        assert exu.resolve_seed_canonical("飞红巾（哈玛雅）", idx, SCOPE) == "哈玛雅"

    def test_plain_name_resolves(self):
        assert exu.resolve_seed_canonical("卓一航", self._idx(), SCOPE) == "卓一航"

    def test_no_scope_presence_returns_none(self):
        """解析成功但 scope 内无出现 → 不产 canonical（避免指向演示站不存在的页）。"""
        narrow = {"profile": "demo", "books": ["冰魄寒光剑"]}
        assert exu.resolve_seed_canonical("卓一航", self._idx(), narrow) is None

    def test_unresolvable_returns_none(self):
        assert exu.resolve_seed_canonical("无名氏", self._idx(), SCOPE) is None
        assert exu.resolve_seed_canonical("卓一航", None, SCOPE) is None
        assert exu.resolve_seed_canonical(None, self._idx(), SCOPE) is None


# ================================================================ 3. 悬案墙（open_questions 过滤）
class TestOpenQuestions:
    def test_scope_filters_by_related_books(self):
        """关涉书 ⊆ scope 的悬案保留；宋代/晚清/独立作品相关被裁（以实际数据为准）。"""
        series = _series()
        payload, st = exu.build_universe({"series": series}, scope=SCOPE, canon_index=None)
        kept = payload["open_questions"]
        assert len(series["open_questions"]) == 7              # 源基线
        assert len(kept) == st["open_questions_kept"]
        assert any("冰魄寒光剑" in q and "江湖三女侠" in q for q in kept)   # scope 内悬案保留
        for q in kept:                                         # scope 外关涉不得残留
            assert "宋代" not in q
            assert "草莽龙蛇传" not in q and "龙虎斗京华" not in q
            assert "武当一剑" not in q and "武林天骄" not in q and "鸣镝风云录" not in q

    def test_unattributed_question_kept(self):
        """无法归书（文本无书名命中）的悬案保守保留。"""
        series = {"lines": [], "chronology_spine": [], "interchange_seeds": [],
                  "open_questions": ["某两部书的先后待考（无书名）"]}
        payload, st = exu.build_universe({"series": series}, scope=SCOPE, canon_index=None)
        assert payload["open_questions"] == series["open_questions"]

    def test_full_caliber_unchanged(self):
        series = _series()
        payload, _st = exu.build_universe({"series": series})
        assert payload["open_questions"] == series["open_questions"]
        assert len(payload["open_questions"]) == 7


# ================================================================ 4. 编年谱（scope 书 + 缺佚星标）
class TestSpine:
    def test_scope_segments_only_scope_books(self):
        payload, st = exu.build_universe({"series": _series()}, scope=SCOPE, canon_index=None)
        segs = payload["chronology_spine"]
        all_books = [b for sp in segs for b in sp["books"]]
        assert {b.rstrip("*") for b in all_books} <= set(DEMO_ORDER)
        assert [sp["era"] for sp in segs] == ["明·景泰后—成化", "明末·万历—崇祯",
                                              "清·顺治", "清·康熙", "清·康熙—雍正"]

    def test_missing_star_book_matched_by_clean_name(self):
        """缺佚星标（冰魄寒光剑*）按裸名归书：scope 内保留且星标原样保留（W0-T4 修正）。"""
        payload, _st = exu.build_universe({"series": _series()}, scope=SCOPE, canon_index=None)
        seg = next(sp for sp in payload["chronology_spine"]
                   if sp["era"] == "清·康熙—雍正")
        assert seg["books"] == ["冰魄寒光剑*", "江湖三女侠"]

    def test_full_caliber_unchanged(self):
        series = _series()
        payload, _st = exu.build_universe({"series": series})
        assert payload["chronology_spine"] == series["chronology_spine"]
        assert len(payload["chronology_spine"]) == 14


# ================================================================ 5. atlas/state.json 接管
class TestAtlasState:
    _KEYS = {"slug", "title", "chapters", "era", "era_conf", "leads"}

    @staticmethod
    def _slices():
        return {b: {"meta": {"book": b}, "title": b, "era": f"era·{b}", "era_conf": "ok",
                    "chapters": 10 + i, "persons": {"甲": {"n": 1, "chaps": [1]}},
                    "places": {}, "bychap": {"1": {"p": ["甲"], "l": []}}, "events": {}}
                for i, b in enumerate(exu.BOOKS)}

    @staticmethod
    def _works():
        return {b: {"leads": [f"主-{b}"]} for b in exu.BOOKS}

    def test_scope_books_in_demo_order(self):
        state, st = exu.build_state(self._slices(), self._works(), scope=SCOPE)
        assert [b["slug"] for b in state["books"]] == DEMO_ORDER   # 演示顺序
        assert st["books"] == 7

    def test_maptrail_manifest_keys_compatible(self):
        """MapTrail.tsx Manifest 消费键：meta.note + books[].slug/title/chapters/era/era_conf/leads。"""
        state, _st = exu.build_state(self._slices(), self._works(), scope=SCOPE)
        assert isinstance(state["meta"].get("note"), str) and state["meta"]["note"]
        for b in state["books"]:
            assert self._KEYS <= set(b), b["slug"]
            assert isinstance(b["chapters"], int) and b["chapters"] > 0
            assert isinstance(b["leads"], list) and b["leads"] == [f"主-{b['slug']}"]
            assert b["title"] == b["slug"]
        assert state["meta"]["schema"] == "atlas-state-v1"
        assert state["meta"]["scope"] == PROFILE

    def test_build_qa_index_consumes_titles(self):
        """build_qa_index.select_titles 消费 books[].title（scope 口径 = 7 书）。"""
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import build_qa_index  # noqa: E402
        state, _st = exu.build_state(self._slices(), self._works(), scope=SCOPE)
        assert build_qa_index.select_titles(state, SCOPE) == DEMO_ORDER
        assert build_qa_index.select_titles(state, None) == DEMO_ORDER

    def test_full_caliber_all_books_contract_order(self):
        state, _st = exu.build_state(self._slices(), self._works(), scope=None)
        assert [b["slug"] for b in state["books"]] == exu.BOOKS    # 全量 = BOOKS 契约顺序
        assert set(state["books"][0]) == self._KEYS                # 与旧脚本 state.json 同构
        assert "scope" not in state["meta"]
        assert state["meta"]["note"] == "leaders（各派当前掌门）待工具 B 门派世系表接入后填充；" \
                                         "era 来自作品元数据表"      # 全量口径与旧脚本逐字一致

    def test_slice_missing_book_skipped(self):
        slices = {b: s for b, s in self._slices().items() if b != "白发魔女传"}
        state, st = exu.build_state(slices, self._works(), scope=SCOPE)
        assert "白发魔女传" not in [b["slug"] for b in state["books"]]
        assert st["books"] == 6


# ================================================================ 6. books.json missing_works 裁剪
class TestMissingWorks:
    BOOK_A, BOOK_B = "测试书甲", "测试书乙"
    SCOPE_A = {"profile": "demo", "books": [BOOK_A]}

    @staticmethod
    def _legacy():
        return {"wmeta": {"works": [{"book": TestMissingWorks.BOOK_A, "no": 1},
                                    {"book": TestMissingWorks.BOOK_B, "no": 2}],
                          "missing_works": [
                              {"book": TestMissingWorks.BOOK_A, "era": "待考", "note": "n1"},
                              {"book": TestMissingWorks.BOOK_B, "era": "待考", "note": "n2"}]},
                "inter": {"edges": []}}

    def test_scope_trims_out_of_scope_missing_works(self):
        payload, _st = exb.build_books({self.BOOK_A: [{"no": 1, "title": "一"}]}, {},
                                       scope=self.SCOPE_A, legacy=self._legacy())
        assert [mw["book"] for mw in payload["missing_works"]] == [self.BOOK_A]
        assert any("缺佚" in g for g in payload["meta"]["field_gaps"])

    def test_full_caliber_keeps_all_missing_works(self):
        payload, _st = exb.build_books({self.BOOK_A: [{"no": 1, "title": "一"}]}, {},
                                       legacy=self._legacy())
        assert [mw["book"] for mw in payload["missing_works"]] == [self.BOOK_A, self.BOOK_B]

    def test_real_data_scope_missing_works_empty(self):
        """真实元数据表 3 部缺佚书（挑灯看剑录/折戟沉沙录/武林三绝）均 scope 外 → 演示口径为空。"""
        legacy = exb.load_legacy_metadata()
        missing = legacy["wmeta"].get("missing_works") or []
        assert len(missing) == 3
        assert all(mw["book"] not in set(DEMO_ORDER) for mw in missing)


# ================================================================ 7. build_atlas_slices.py 废弃标注
class TestAtlasSlicesDeprecation:
    def test_header_deprecated_and_points_to_ex7(self):
        head = (REPO_ROOT / "scripts" / "build_atlas_slices.py").read_text(encoding="utf-8")[:3000]
        assert "废弃" in head
        assert "export_site_gazetteer_universe" in head
        assert "EX-7" in head

    def test_file_still_importable(self):
        """只加标注不破坏脚本（不删文件；历史参考可运行）。"""
        text = (REPO_ROOT / "scripts" / "build_atlas_slices.py").read_text(encoding="utf-8")
        assert "def main()" in text
