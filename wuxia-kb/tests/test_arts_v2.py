# -*- coding: utf-8 -*-
"""W3-T4 · 武功详情页数据层测试（武功页重构设计 §5.2/§5.3/§六/§九；总体方案 §3.2/§4.2 B9/A4）。

被测对象：scripts/export_site_sects_weapons_arts.py 的 arts 部分（W3-T4 新增，weapons/sects 零影响）：
  load_art_comments(path)  读 kb/校订/武功评语.tsv（表头 art/quote/loc/status）→
                           {art: [{quote, book, loc}]}；L1 闸门：
                           单条 quote ≤16 字、每门 ≤2 条、status ∈ {校定, draft}（只消费 校定）、
                           loc 须为「书名·NNN:NNN」式（书名不带空白）、重复行报错——
                           违例 ArtCommentError（不静默改写人工校定稿）；
  parse_lineage_note(note) 传授行 note → s→l 配对候选纯函数（武功页重构设计 §6.2 数据源 2 层：
                           「从关系表方向性 + note 解析」）→ [{l, loc, tier}]（tier ∈
                           正式/记名/挂名/点拨）；解析不出返回 []（不伪造配对）；
  build_arts(…)            records 注入 comments（评语卡数据，不计入 ev_total）与
                           lineage（传授真边：学生须在同门武功关系表出现，解析不出/
                           未出现不入表）；scope 口径下 scope 外评语书不消费；
                           meta.field_gaps/notes 声明口径；weapons/sects 不受影响。

测试口径（先红后绿；除「真实 TSV 内容纪律」一节外全部用合成 fixture，不写 site/data）：
  - 评语是 L1 短引文档位（全站首个），红线=引文必须明文、可定位、限量；
  - 传承树真边红线=无配对不强造（note 解析不出 → 空列表，进 meta 报告）。
"""
import csv
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（被测模块依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_sects_weapons_arts as exs  # noqa: E402

BOOK_A, BOOK_B = "测试书甲", "测试书乙"
SCOPE_A = {"profile": "demo", "books": [BOOK_A]}


# ================================================================ fixtures（合成）
def _write_comment_tsv(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    """rows: (art, quote, loc, status) → tab 分隔 TSV（W3-T4 表头）。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["art", "quote", "loc", "status"])
        for r in rows:
            w.writerow(r)


def _art(canonical, relations, **extra):
    rec = {"canonical": canonical, "category": "剑法", "aliases": [],
           "ev_total": 3, "books": sorted({b for b in relations}), "cross_book": False,
           "relations": relations}
    rec.update(extra)
    return rec


def _src(arts: list[dict]) -> dict:
    """最小合成 src：old_arts 为底（relations 已是站点契约形状），其余源为空。"""
    return {
        "old_arts": {"arts": arts, "meta": {"totals": {"by_category": {"其他": 0}}}},
        "old_sects": {"sects": [], "meta": {"note": ""}},
        "old_weapons": {"weapons": []},
        "lineage": {"sects": []},
        "artifacts": {"artifacts": [], "alias_candidates": [], "meta": {}},
        "moves": {"moves": [], "conflicts": []},
        "works": {},
        "entities": [], "wordlist": [],
        "sect_alias": {}, "art_alias": {}, "weapon_alias": {},
        "sect_canon": set(), "art_canon": set(), "weapon_canon": set(),
        "conc": {}, "conc_books": [BOOK_A, BOOK_B],
    }


def _relations_tianshan() -> dict:
    """合成天山剑法式 relations：创制 1 + 传授 2（note 带配对）+ 修习 3，书内证据池共享。
    学生名用真实人名样（弟子/师徒等群称字本就在学生名黑名单——真实数据同样如此）。"""
    locs_a = ["000:10", "000:20"]
    locs_b = ["001:30"]
    return {
        BOOK_A: {"relations": [
            {"s": "创制者甲", "st": "@", "pred": "创制", "locs": locs_a, "ev": 2, "note": "明文创制"},
            {"s": "祖师甲", "st": "@", "pred": "传授", "locs": locs_a, "ev": 2, "note": "传陈大勇（000:10）"},
            {"s": "陈大勇", "st": "@", "pred": "修习", "locs": locs_a, "ev": 2, "note": "明文修习"},
            {"s": "陈大勇", "st": "@", "pred": "传授", "locs": locs_b, "ev": 1, "note": "009:7 传给李小虎"},
            {"s": "李小虎", "st": "@", "pred": "修习", "locs": locs_b, "ev": 1, "note": "明文修习"},
        ]},
        BOOK_B: {"relations": [
            {"s": "传艺者乙", "st": "@", "pred": "传授", "locs": ["002:99"], "ev": 1, "note": "002:99 指点王二麻"},
            {"s": "王二麻", "st": "@", "pred": "修习", "locs": ["002:99"], "ev": 1, "note": "明文修习"},
        ]},
    }


COMMENTS_A = {"天山剑法-测试": [{"quote": "天下无敌的剑法", "book": BOOK_A, "loc": "000:125"}]}


def _by_canon(payload):
    return {a["canonical"]: a for a in payload["arts"]}


# ================================================================ 1. load_art_comments（读取与闸门）
class TestLoadArtComments:
    def test_missing_file_returns_empty(self, tmp_path):
        """文件不存在 → ({}, 统计零)（build_arts 以 field_gaps 声明缺 TSV 口径）。"""
        comments, stats = exs.load_art_comments(tmp_path / "不存在.tsv")
        assert comments == {} and stats["consumed"] == 0

    def test_parses_rows_to_book_loc(self, tmp_path):
        """数据行 → {art: [{quote, book, loc}]}；loc 列「书·NNN:NNN」（· 或空格分隔）拆出 book/loc。"""
        p = tmp_path / "武功评语.tsv"
        _write_comment_tsv(p, [("甲剑法", "快得像风", f"{BOOK_A}·003:21", "校定"),
                               ("乙掌法", "重若泰山", f"{BOOK_B} 012:9", "校定")])
        comments, _st = exs.load_art_comments(p)
        assert comments == {"甲剑法": [{"quote": "快得像风", "book": BOOK_A, "loc": "003:21"}],
                            "乙掌法": [{"quote": "重若泰山", "book": BOOK_B, "loc": "012:9"}]}

    def test_quote_over_16_raises(self, tmp_path):
        """quote 超 16 字 → ArtCommentError（L1 长度红线，构建即报错）。"""
        p = tmp_path / "武功评语.tsv"
        _write_comment_tsv(p, [("甲剑法", "这一句超过十六个字的评语不能被消费掉", f"{BOOK_A}·001:1")])
        with pytest.raises(exs.ArtCommentError, match="16"):
            exs.load_art_comments(p)

    def test_over_two_rows_per_art_raises(self, tmp_path):
        """同 art 第 3 行 → ArtCommentError（每门 ≤2 条红线）。"""
        p = tmp_path / "武功评语.tsv"
        _write_comment_tsv(p, [("甲剑法", "评语一", f"{BOOK_A}·001:1"),
                               ("甲剑法", "评语二", f"{BOOK_A}·001:2"),
                               ("甲剑法", "评语三", f"{BOOK_A}·001:3")])
        with pytest.raises(exs.ArtCommentError, match="2"):
            exs.load_art_comments(p)

    def test_draft_rows_not_consumed(self, tmp_path):
        """status=draft 行不消费（评语判断是编辑工作，未校定不入站），stats 记行数。"""
        p = tmp_path / "武功评语.tsv"
        _write_comment_tsv(p, [("甲剑法", "已校定评语", f"{BOOK_A}·001:1", "校定"),
                               ("乙剑法", "草案评语", f"{BOOK_A}·001:2", "draft")])
        comments, stats = exs.load_art_comments(p)
        assert set(comments) == {"甲剑法"}
        assert stats["consumed"] == 1 and stats["draft"] == 1

    def test_unknown_status_raises(self, tmp_path):
        """status 不在 {校定, draft} → ArtCommentError（拼错不静默丢弃）。"""
        p = tmp_path / "武功评语.tsv"
        _write_comment_tsv(p, [("甲剑法", "评语", f"{BOOK_A}·001:1", "已审定")])
        with pytest.raises(exs.ArtCommentError, match="status"):
            exs.load_art_comments(p)

    def test_bad_loc_format_raises(self, tmp_path):
        """loc 非「书·NNN:NNN」式（缺书名/缺定位符）→ ArtCommentError（定位必须真实可点）。"""
        p = tmp_path / "武功评语.tsv"
        _write_comment_tsv(p, [("甲剑法", "评语一", "001:1"),
                               ("乙剑法", "评语二", f"{BOOK_A}·第一章")])
        with pytest.raises(exs.ArtCommentError, match="loc"):
            exs.load_art_comments(p)

    def test_bad_header_and_empty_fields_raise(self, tmp_path):
        """表头错 / art·quote 空值 → ArtCommentError。"""
        p = tmp_path / "武功评语.tsv"
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("art\t引文\tloc\tstatus\n")
        with pytest.raises(exs.ArtCommentError, match="表头"):
            exs.load_art_comments(p)
        p2 = tmp_path / "武功评语2.tsv"
        _write_comment_tsv(p2, [("甲剑法", "", f"{BOOK_A}·001:1")])
        with pytest.raises(exs.ArtCommentError):
            exs.load_art_comments(p2)

    def test_duplicate_row_raises(self, tmp_path):
        """同 art+quote+loc 重复行 → ArtCommentError（唯一真源）。"""
        p = tmp_path / "武功评语.tsv"
        _write_comment_tsv(p, [("甲剑法", "评语", f"{BOOK_A}·001:1", "校定"),
                               ("甲剑法", "评语", f"{BOOK_A}·001:1", "校定")])
        with pytest.raises(exs.ArtCommentError, match="重复"):
            exs.load_art_comments(p)


# ================================================================ 2. parse_lineage_note（纯函数）
class TestParseLineageNote:
    def test_verb_paren_pair(self):
        """「传岳鸣珂（004:57）」→ 单边（学生+定位符+正式）。"""
        assert exs.parse_lineage_note("传岳鸣珂（004:57）") == [
            {"l": "岳鸣珂", "loc": "004:57", "tier": "正式"}]

    def test_multi_names_each_paren(self):
        """多名单「传A（loc…）、B（loc…）、C（loc…）」→ 各自配对，括注内定位符取首个。"""
        note = ("传杨云骢（000:125 血书\"上天山去见我的师父晦明禅师\"）、"
                "楚昭南（001:123 徒弟）、凌未风（004:99 习技十年；025:99 授拳经剑诀）")
        assert exs.parse_lineage_note(note) == [
            {"l": "杨云骢", "loc": "000:125", "tier": "正式"},
            {"l": "楚昭南", "loc": "001:123", "tier": "正式"},
            {"l": "凌未风", "loc": "004:99", "tier": "正式"},
        ]

    def test_slash_names_paired_locs(self):
        """「传A/B（loc1、loc2）」→ 按序配对。"""
        assert exs.parse_lineage_note("为晦明禅师时传杨云骢/楚昭南（028:5、028:75）") == [
            {"l": "杨云骢", "loc": "028:5", "tier": "正式"},
            {"l": "楚昭南", "loc": "028:75", "tier": "正式"},
        ]

    def test_tier_guaming_and_regular(self):
        """「授X本门剑术（挂名师徒）；专心教X武艺」→ 挂名 + 正式两档。"""
        note = "009:31 授唐晓澜本门剑术（挂名师徒）；046:67 专心教唐晓澜武艺"
        assert exs.parse_lineage_note(note) == [
            {"l": "唐晓澜", "loc": "009:31", "tier": "挂名"},
            {"l": "唐晓澜", "loc": "046:67", "tier": "正式"},
        ]

    def test_tier_dianbo(self):
        """「实地拆招指点X」→ 点拨档。"""
        assert exs.parse_lineage_note("001:83 实地拆招指点唐晓澜") == [
            {"l": "唐晓澜", "loc": "001:83", "tier": "点拨"}]

    def test_chuan_gei(self):
        """「把毕生心得全都传给X」→ 学生在传给之后。"""
        assert exs.parse_lineage_note("009:7 凌未风把毕生心得全都传给易兰珠") == [
            {"l": "易兰珠", "loc": "009:7", "tier": "正式"}]

    def test_song_wei_tu_and_dai_shi(self):
        """「A送他为徒学十年；「代师传授」B」→ 分段各配对。"""
        assert exs.parse_lineage_note("001:32 杨云骢送他为徒学十年；005:47「代师传授」楚昭南") == [
            {"l": "杨云骢", "loc": "001:32", "tier": "正式"},
            {"l": "楚昭南", "loc": "005:47", "tier": "正式"},
        ]

    def test_editor_paren_note(self):
        """引文后的编者括注「（传X）」→ 学生取段首定位符。"""
        assert exs.parse_lineage_note("022:5 明文\"另外我再教你几路拐杖点穴法\"（传张华昭）") == [
            {"l": "张华昭", "loc": "022:5", "tier": "正式"}]

    def test_xue_lai_pattern(self):
        """「A从B处学来」→ 学生在学来之前。"""
        assert exs.parse_lineage_note("044:7 冯琳从八臂神魔处学来（四皇府传艺）") == [
            {"l": "冯琳", "loc": "044:7", "tier": "正式"}]

    def test_no_parse_returns_empty(self):
        """无学生名的授业表述（传衣钵/传下来的）→ []（不伪造配对）。"""
        assert exs.parse_lineage_note("030:147 明文\"凌未风传了晦明禅师的衣钵，光大天山剑派\"") == []
        assert exs.parse_lineage_note("009:53「桂仲明传下来的达摩剑法」") == []

    def test_pronoun_and_artifact_blacklist(self):
        """代词宾语（教她）与武功词宾语（传八卦紫金刀法）不当作学生。"""
        assert exs.parse_lineage_note("028:43 明文「允祯亲自教她」") == []
        assert exs.parse_lineage_note("027:41 门徒各有独特技艺，路民瞻传八卦紫金刀法") == []

    def test_empty_note(self):
        assert exs.parse_lineage_note("") == [] and exs.parse_lineage_note(None) == []


# ================================================================ 3. build_arts 注入（合成 fixture）
class TestBuildArtsCommentsLineage:
    def test_comments_injected(self):
        """TSV 校定行 → 对应 arts 记录带 comments=[{quote,book,loc}]；ev_total 不变（评语非证据）。"""
        payload, _st = exs.build_arts(_src([_art("甲剑法", _relations_tianshan())]),
                                      art_comments={"甲剑法": COMMENTS_A["天山剑法-测试"]})
        rec = _by_canon(payload)["甲剑法"]
        assert rec["comments"] == COMMENTS_A["天山剑法-测试"]
        assert rec["ev_total"] == 3   # 评语非证据：ev_total 保持旧站关系证据口径不变

    def test_no_comment_art_has_no_key(self):
        """无评语武功无 comments 键（不是空数组——前端按字段存在性渲染）。"""
        payload, _st = exs.build_arts(_src([_art("甲剑法", _relations_tianshan())]),
                                      art_comments={})
        assert "comments" not in _by_canon(payload)["甲剑法"]

    def test_scope_drops_out_of_scope_comment_books(self):
        """scope 口径：评语书在 scope 外 → 不消费（行不报错）；scope 内正常注入。"""
        rec = _art("甲剑法", _relations_tianshan())
        rec["books"] = [BOOK_A, BOOK_B]
        payload, _st = exs.build_arts(_src([rec]), scope=SCOPE_A,
                                      art_comments={"甲剑法": [
                                          {"quote": "甲书评语", "book": BOOK_A, "loc": "000:1"},
                                          {"quote": "乙书评语", "book": BOOK_B, "loc": "002:99"}]})
        rec = _by_canon(payload)["甲剑法"]
        assert rec["comments"] == [{"quote": "甲书评语", "book": BOOK_A, "loc": "000:1"}]

    def test_lineage_edges_from_notes(self):
        """传授 note 配对 → lineage=[{t,l,book,loc,tier}]；学生已在同门关系表 → 入表。"""
        payload, _st = exs.build_arts(_src([_art("甲剑法", _relations_tianshan())]),
                                      art_comments={})
        rec = _by_canon(payload)["甲剑法"]
        assert rec["lineage"] == [
            {"t": "祖师甲", "l": "陈大勇", "book": BOOK_A, "loc": "000:10", "tier": "正式"},
            {"t": "陈大勇", "l": "李小虎", "book": BOOK_A, "loc": "009:7", "tier": "正式"},
            {"t": "传艺者乙", "l": "王二麻", "book": BOOK_B, "loc": "002:99", "tier": "点拨"},
        ]

    def test_lineage_student_unattested_dropped(self):
        """学生未在同门武功关系表出现（王二麻缺行）→ 该边不入表（不造跨表配对）。"""
        rels = _relations_tianshan()
        rels[BOOK_B]["relations"] = [
            {"s": "传艺者乙", "st": "@", "pred": "传授", "locs": ["002:99"], "ev": 1,
             "note": "002:99 指点王二麻"}]
        payload, _st = exs.build_arts(_src([_art("甲剑法", rels)]), art_comments={})
        rec = _by_canon(payload)["甲剑法"]
        assert all(e["t"] != "传艺者乙" for e in rec.get("lineage", []))
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "lineage" in gaps and "未出现" in gaps

    def test_lineage_no_fake_when_unparsable(self):
        """note 解析不出学生 → 无 lineage 键（不伪造配对），meta 报告未解析传授行数。"""
        rels = {BOOK_A: {"relations": [
            {"s": "祖师甲", "st": "@", "pred": "传授", "locs": ["000:1"], "ev": 1,
             "note": "030:147 明文\"祖师甲传了衣钵\""}]}}
        payload, _st = exs.build_arts(_src([_art("甲剑法", rels)]), art_comments={})
        rec = _by_canon(payload)["甲剑法"]
        assert "lineage" not in rec
        assert "未解出" in "\n".join(payload["meta"]["field_gaps"])

    def test_self_loop_dropped(self):
        """学生=传授者本人（note 提到自己传下）→ 不成边。"""
        rels = {BOOK_A: {"relations": [
            {"s": "陈大勇", "st": "@", "pred": "传授", "locs": ["000:1"], "ev": 1,
             "note": "000:1 陈大勇传给陈大勇"}]}}
        payload, _st = exs.build_arts(_src([_art("甲剑法", rels)]), art_comments={})
        assert "lineage" not in _by_canon(payload)["甲剑法"]

    def test_weapons_sects_untouched(self):
        """weapons/sects 与本任务零关系：build_weapons/build_sects 无 comments/lineage 注入路径。"""
        src = _src([])
        wp, _w = exs.build_weapons(src)
        sp, _s = exs.build_sects(src)
        assert all("comments" not in w and "lineage" not in w for w in wp["weapons"])
        assert all("comments" not in s and "lineage" not in s for s in sp["sects"])

    def test_meta_declares_l1_and_lineage(self, monkeypatch, tmp_path):
        """meta.field_gaps 声明评语 L1 口径（≤16 字×≤2 条）与传承真边口径。"""
        monkeypatch.setattr(exs, "ART_COMMENT_TSV", tmp_path / "不存在.tsv")
        payload, _st = exs.build_arts(_src([_art("甲剑法", _relations_tianshan())]),
                                      art_comments=COMMENTS_A and {})
        gaps = "\n".join(payload["meta"]["field_gaps"])
        assert "武功评语.tsv" in gaps and "16" in gaps and "lineage" in gaps

    def test_missing_tsv_no_comments_field(self, monkeypatch, tmp_path):
        """缺 TSV → 全部武功无 comments 键，field_gaps 声明「不存在」。"""
        monkeypatch.setattr(exs, "ART_COMMENT_TSV", tmp_path / "不存在.tsv")
        payload, _st = exs.build_arts(_src([_art("甲剑法", _relations_tianshan())]),
                                      art_comments=None)
        assert all("comments" not in a for a in payload["arts"])
        assert "不存在" in "\n".join(payload["meta"]["field_gaps"])


# ================================================================ 4. 真实 TSV 内容纪律（人工校定稿把关）
class TestRealArtCommentTsv:
    """真实 kb/校订/武功评语.tsv 的 L1 纪律（内容即规范；loc 已按章回版源行号逐一核实）。"""

    def setup_method(self):
        assert exs.ART_COMMENT_TSV.exists(), "kb/校订/武功评语.tsv 不存在（W3-T4 应已建）"
        self.comments, self.stats = exs.load_art_comments()   # 闸门在读取即生效

    def test_four_arts_first_batch(self):
        """首批 4 门（天山剑法 + 原文明文三套），每门 1 条（≤2 红线内）。"""
        assert set(self.comments) == {"天山剑法", "追风剑法", "须弥剑法", "寒涛剑法"}
        assert all(len(v) == 1 for v in self.comments.values())

    def test_quotes_short_and_literal(self):
        """全部 quote ≤16 字、非空、无引号（引号由渲染层加，避免嵌套）。"""
        for art, rows in self.comments.items():
            for r in rows:
                assert 0 < len(r["quote"]) <= 16, (art, r["quote"])
                assert "「" not in r["quote"] and "」" not in r["quote"]

    def test_locs_in_scope_books(self):
        """loc 书名全部在 scope 7 书内（天山演示版口径）。"""
        scope_books = {"散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
                       "七剑下天山", "冰魄寒光剑", "江湖三女侠"}
        for art, rows in self.comments.items():
            for r in rows:
                assert r["book"] in scope_books, (art, r["book"])

    def test_key_quotes(self):
        """关键行固化：四条评语原文与定位（tagged/章回版 grep 核实）。"""
        assert self.comments["天山剑法"] == [{"quote": "天下独步的剑法", "book": "七剑下天山", "loc": "000:125"}]
        assert self.comments["追风剑法"][0]["quote"] == "追风剑法，迅捷无伦"
        assert self.comments["须弥剑法"][0]["quote"] == "须弥剑法攻守兼备"
        assert self.comments["寒涛剑法"][0]["quote"] == "真如寒涛卷地，浪花飞空"

    def test_stats_shape(self):
        """读取统计：consumed=4、draft=0（首批全校定）。"""
        assert self.stats["consumed"] == 4 and self.stats["draft"] == 0


# ================================================================ 5. 真实 note 全量解析覆盖（数据源调查固化）
class TestRealLineageParseCoverage:
    """site/data/arts.json 全部传授行（39 条）经 parse_lineage_note 的真实覆盖口径。
    固化数据源调查结论：传授配对只活在 note（relations 无 object 字段；graph 传授边
    与武功无配对字段），解析不出者不伪造。"""

    def test_majority_notes_parse_and_no_garbage(self):
        import json
        data = json.loads((Path(__file__).resolve().parents[2] / "site" / "data"
                           / "arts.json").read_text(encoding="utf-8"))
        total = parsed = 0
        tiers = {}
        for a in data["arts"]:
            for bv in (a.get("relations") or {}).values():
                for r in bv["relations"]:
                    if r.get("pred") != "传授":
                        continue
                    total += 1
                    edges = exs.parse_lineage_note(r.get("note") or "")
                    for e in edges:
                        tiers[e["tier"]] = tiers.get(e["tier"], 0) + 1
                    if edges:
                        parsed += 1
                    # 学生名不得是武功词/代词（黑名单兜底的真实数据抽查）
                    for e in edges:
                        assert not e["l"].endswith(("法", "式", "拳", "掌", "刀", "剑", "功", "招"))
                        assert e["l"] not in ("她", "他", "我")
        assert total >= 39          # 数据源规模固化（方案 A4「传授 39 条」）
        assert parsed >= total * 0.6   # 覆盖下限：六成以上传授行可解出配对
        assert tiers.get("挂名", 0) >= 1 and tiers.get("点拨", 0) >= 1  # 四档档位至少两档在真实数据出现
