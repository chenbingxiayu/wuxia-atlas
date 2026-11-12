# -*- coding: utf-8 -*-
"""D2 · 线路导读接线测试（宇宙页重构设计 §4.2，2026-11-10）。

数据源（人工编辑轨唯一真源）：kb/校订/线路导读.tsv（仅 status=校定 行）。
被测对象（D2 新增，export_site_gazetteer_universe）：
  guide_line_key          线名匹配键（去尾部「（…）」括注）
  load_reading_guide      TSV 读入（校定行过滤 + 重复校定闸门 + 文件缺失降级）
  attach_reading_guide    lines[].reading_guide 挂载（线成员书校验 + 站外降级）
  build_universe(..., guide=…)  两口径接线 + meta 来源声明 + 统计

口径固化（测试即规范）：
  - 只消费 status=校定 行（draft/待校 静默跳过，同 作品简介/武功评语 编辑流程口径）；
    文件缺失 → {}（线路导读是可选增强，不阻塞导出；前端全空隐藏区块）。
  - 同线重复校定行 → ReadingGuideError（唯一真源导出闸门，同 load_intro_tsv 口径）。
  - 线名按基名匹配（去尾部括注）：全量口径线「天山系列（清代主脉）」与演示口径线
    「天山系列」消费同一行——reading_guide 是"线"属性，两口径都生效
    （方案 R6 由 D2 增补：全量也渲染）。
  - 槽位书名 ∈ 该线成员书才挂载，否则**降级丢弃该槽位**（选"降级"不选"报错"：EX-7 是薄
    导出器，前端对缺槽/无 guide 均有降级渲染；演示口径旧稿 peak=云海玉弓缘〔站外书〕即
    由此降级——站外书不得入选，也不得渲染死链）。
  - 三槽位全空且 note 空 → 整行不挂载（宇宙页"无内容不渲染行"）。
  - 字段契约 = 前端消费键（site/src/pages/universe/index.astro guideRows）：
    lines[].reading_guide = {start, peak, skip, note?}——入坑起点=start、巅峰之作=peak、
    可跳过=skip、note=句尾导读说明。
  - 挂载只发生在导出产物层：build_universe 不得改写 src["series"] 只读源数据。
"""
import csv
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（被测模块依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_common as esc  # noqa: E402
import export_site_gazetteer_universe as exu  # noqa: E402

PROFILE = "tianshan-demo"
SCOPE = esc.load_scope(PROFILE)
DEMO_ORDER = ["散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
              "七剑下天山", "冰魄寒光剑", "江湖三女侠"]
GUIDE_TSV = REPO_ROOT / "kb" / "校订" / "线路导读.tsv"
NOTE_MAX = 40            # 宇宙页 §4.2：note 一句导读理由 ≤40 字（编辑闸门口径）


def _series() -> dict:
    """真实只读源数据 kb/系列谱系考订表.json（EX-7 的 universe 四节唯一来源）。"""
    return exu.load_json(exu.KB / "系列谱系考订表.json")


def _demo_payload(series=None):
    return exu.build_universe({"series": series if series is not None else _series()},
                              scope=SCOPE, canon_index=None)


def _write_tsv(rows: list) -> Path:
    """合成 TSV（tmp_path）：rows = dict 列表，键 = 表头列。"""
    cols = ["line", "start", "peak", "skip", "note", "status"]
    lines = ["\t".join(cols)]
    for r in rows:
        lines.append("\t".join(str(r.get(c) or "") for c in cols))
    p = exu.GUIDE_TSV.parent / "_test_guide.tsv"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ================================================================ 1. 线名匹配键
class TestGuideLineKey:
    """线名基名归一：去尾部「（…）」括注——全量/演示两口径同键。"""

    def test_paren_suffix_stripped(self):
        assert exu.guide_line_key("天山系列（清代主脉）") == "天山系列"
        assert exu.guide_line_key("天山系列") == "天山系列"          # 演示口径线名

    def test_no_paren_and_edge_cases(self):
        assert exu.guide_line_key("明代系列") == "明代系列"          # 无括注原样
        assert exu.guide_line_key(None) == ""                       # 防御：非字符串
        assert exu.guide_line_key(123) == ""
        assert exu.guide_line_key("  ") == ""


# ================================================================ 2. TSV 读入
class TestLoadReadingGuide:
    """TSV 读入：校定行过滤 / 重复校定闸门 / 文件缺失降级。"""

    def test_real_tsv_only_tianshan_calibrated_row(self):
        """真源 TSV（D2 重写后）：仅天山一行校定行；16 书口径草稿行不入消费。"""
        guide = exu.load_reading_guide()
        assert list(guide) == ["天山系列"]                          # 基名键唯一
        row = guide["天山系列"]
        assert row["line"] == "天山系列（清代主脉）"                # 原始线名保留
        # 三槽位必须是演示 7 书书名（站外书不得入选——编辑口径构建期校验）
        assert row["start"] in DEMO_ORDER and row["peak"] in DEMO_ORDER and row["skip"] in DEMO_ORDER
        assert row["start"] == "白发魔女传"
        assert row["peak"] == "七剑下天山"
        assert row["skip"] == "冰魄寒光剑"
        assert row["note"] and len(row["note"]) <= NOTE_MAX        # ≤40 字导读一句
        # 旧稿 6 线（draft）不消费：基名键里不得出现其他线
        for k in ("明代系列", "大唐三部曲", "宋代系列", "晚清民国线", "独立作品"):
            assert k not in guide

    def test_real_tsv_editorial_columns(self):
        """编辑轨留痕：status=校定、date=2026-11-10（TSV 原始列，非消费字段）。"""
        with open(GUIDE_TSV, encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f, delimiter="\t") if (r.get("line") or "").strip()]
        assert len(rows) == 1                                       # 只保留天山演示线一行
        assert rows[0]["status"] == "校定"
        assert rows[0]["date"] == "2026-11-10"
        # 其余 16 书口径行在备份文件（scope 外不消费，留档可溯；原稿 6 条数据行+表头）
        bak = GUIDE_TSV.parent / "线路导读.tsv.bak-20261110"
        assert bak.exists()
        with open(bak, encoding="utf-8", newline="") as f:
            bak_rows = [r for r in csv.DictReader(f, delimiter="\t") if (r.get("line") or "").strip()]
        assert len(bak_rows) == 6                                   # 原稿 6 条 16 书口径行留档

    def test_draft_rows_skipped_and_missing_file_degrades(self, tmp_path):
        """draft/待校 行静默跳过；文件缺失 → {}（可选增强，不阻塞导出）。"""
        p = _write_tsv([
            {"line": "天山系列（清代主脉）", "start": "白发魔女传", "peak": "七剑下天山",
             "skip": "冰魄寒光剑", "note": "草稿不该入站。", "status": "draft"},
            {"line": "明代系列", "start": "萍踪侠影录", "note": "待校。", "status": "待校"},
        ])
        assert exu.load_reading_guide(p) == {}
        assert exu.load_reading_guide(tmp_path / "不存在.tsv") == {}

    def test_duplicate_calibrated_row_raises(self):
        """同线重复校定行 → ReadingGuideError（唯一真源导出闸门，消息中文）。"""
        p = _write_tsv([
            {"line": "天山系列（清代主脉）", "start": "白发魔女传", "note": "第一行", "status": "校定"},
            {"line": "天山系列", "start": "七剑下天山", "note": "第二行", "status": "校定"},
        ])
        with pytest.raises(exu.ReadingGuideError) as ei:
            exu.load_reading_guide(p)
        assert "重复校定行" in str(ei.value)


# ================================================================ 3. 挂载（合成 lines）
class TestAttachReadingGuide:
    """挂载规则：站外槽位降级 / 全空不挂 / note 单独成行 / 统计。"""

    @staticmethod
    def _demo_lines():
        return [{"line": "天山系列", "color": "#c0392b",
                 "members": [{"book": b, "order": i} for i, b in enumerate(DEMO_ORDER, 1)]},
                {"line": "明代系列", "color": "#2980b9",
                 "members": [{"book": "萍踪侠影录", "order": 1}]}]

    def test_slot_out_of_members_dropped(self):
        """槽位书 ∉ 线成员书 → 该槽降级丢弃（不报错），其余槽位与 note 照常挂载。

        固化历史案例：旧稿 peak=云海玉弓缘 在演示口径（7 书成员）下属站外书 → 降级。
        """
        guide = {"天山系列": {"line": "天山系列（清代主脉）", "start": "白发魔女传",
                              "peak": "云海玉弓缘", "skip": "冰魄寒光剑", "note": "旧稿场景。"}}
        lines = self._demo_lines()
        stats = exu.attach_reading_guide(lines, guide)
        rg = lines[0]["reading_guide"]
        assert rg["start"] == "白发魔女传" and rg["skip"] == "冰魄寒光剑"
        assert "peak" not in rg                                     # 站外槽位降级
        assert rg["note"] == "旧稿场景。"
        assert set(rg) <= {"start", "peak", "skip", "note"}         # 前端消费键契约
        assert stats["reading_guide_attached"] == 1
        assert stats["reading_guide_dropped_slots"] == 1

    def test_all_slots_out_and_no_note_no_field(self):
        """三槽位全站外且无 note → 整行不挂载（无内容不渲染行）。"""
        guide = {"天山系列": {"line": "天山系列", "start": "云海玉弓缘", "peak": "萍踪侠影录",
                              "skip": "大唐游侠传"}}
        lines = self._demo_lines()
        stats = exu.attach_reading_guide(lines, guide)
        assert "reading_guide" not in lines[0]
        assert stats["reading_guide_attached"] == 0

    def test_note_only_row_attached(self):
        """仅 note 无有效槽位 → 行仍挂载（note 是内容；前端 note-only 行可渲染）。"""
        guide = {"天山系列": {"line": "天山系列", "note": "一句导读。"}}
        lines = self._demo_lines()
        stats = exu.attach_reading_guide(lines, guide)
        assert lines[0]["reading_guide"] == {"note": "一句导读。"}
        assert stats["reading_guide_attached"] == 1

    def test_line_name_mismatch_no_attach(self):
        """线名基名不匹配（TSV 行与 universe 线名不同线）→ 不挂载。"""
        guide = {"明代系列": {"line": "明代系列", "start": "萍踪侠影录", "note": "x"}}
        lines = self._demo_lines()
        stats = exu.attach_reading_guide(lines, guide)
        assert "reading_guide" not in lines[0]
        assert lines[1]["reading_guide"]["start"] == "萍踪侠影录"
        assert stats["reading_guide_attached"] == 1


# ================================================================ 4. build_universe 两口径接线
class TestBuildUniverseWiring:
    """两口径接线：演示单线与全量 16 书线消费同一行（D2 增补 R6）+ meta 声明 + 源数据只读。"""

    def test_demo_line_has_reading_guide(self):
        payload, st = _demo_payload()
        assert len(payload["lines"]) == 1
        rg = payload["lines"][0]["reading_guide"]
        assert rg["start"] == "白发魔女传"
        assert rg["peak"] == "七剑下天山"
        assert rg["skip"] == "冰魄寒光剑"
        assert rg["note"] and len(rg["note"]) <= NOTE_MAX
        assert set(rg) <= {"start", "peak", "skip", "note"}
        # 槽位书名都在演示 7 书成员内（构建期校验）
        members = {m["book"] for m in payload["lines"][0]["members"]}
        assert {rg["start"], rg["peak"], rg["skip"]} <= members
        assert st["reading_guide_attached"] == 1
        assert st["reading_guide_dropped_slots"] == 0

    def test_full_caliber_tianshan_line_also_guided(self):
        """全量口径（scope=None）：天山线（16 成员，名带括注）也挂载同一导读行。"""
        payload, st = exu.build_universe({"series": _series()}, guide=exu.load_reading_guide())
        by_name = {ln["line"]: ln for ln in payload["lines"]}
        assert len(payload["lines"]) == 6
        rg = by_name["天山系列（清代主脉）"]["reading_guide"]
        assert rg["start"] == "白发魔女传" and rg["peak"] == "七剑下天山" and rg["skip"] == "冰魄寒光剑"
        members = {m["book"] for m in by_name["天山系列（清代主脉）"]["members"]}
        assert {rg["start"], rg["peak"], rg["skip"]} <= members
        for name, ln in by_name.items():
            if name != "天山系列（清代主脉）":
                assert "reading_guide" not in ln                    # 其余 5 线无导读行
        assert st["reading_guide_attached"] == 1

    def test_meta_declares_source_and_stats(self):
        """meta 声明消费源（两口径一致）；stats 带行数统计。"""
        for payload, st in (_demo_payload(), exu.build_universe({"series": _series()})):
            assert "线路导读.tsv" in payload["meta"]["reading_guide_source"]
            assert st["reading_guide_rows"] == 1

    def test_source_series_not_mutated(self):
        """挂载只发生在导出产物层：只读源数据 kb/系列谱系考订表.json 快照不得被改写。"""
        series = _series()
        exu.build_universe({"series": series}, scope=SCOPE, canon_index=None)
        exu.build_universe({"series": series})                      # 全量口径再跑一遍
        for ln in series["lines"]:
            assert "reading_guide" not in ln
