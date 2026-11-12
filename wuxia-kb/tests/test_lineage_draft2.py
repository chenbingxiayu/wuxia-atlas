# -*- coding: utf-8 -*-
"""D15 · 武功传承补链第二批落地测试（草案2 全量 11 条 + 独臂老尼→路民瞻 正向读法 +
钟万堂→冯琳 原文裁定边；用户三项裁定 2026-11-12）。

被测事实链（先红后绿）：
  1) kb/校订/武功传承补链.tsv：D10 首批 3 边 + D15 新增 13 边 = 校定行 16（draft 0）；
     13 条新边 (art,from,to,tier,book,loc) 逐条断言；loc 全部为章回版源文件行号口径，
     逐条对 章回版/<书>/<NNN>*.txt grep 复核（防草案定位符漂移——D13 已修正 6 处，
     本次落地前再复核一遍）；
  2) 档位裁定：草案2 11 条 + 路民瞻（正向读法：027:37「路民瞻传的是八卦紫金刀法」在
     「独臂神尼……每个门徒……都有独特的技艺」师门综述语境下读作独臂老尼所传，
     有传授动词，取正式档）+ 钟万堂→冯琳（001:103「我收她做女徒弟」+ 013:59「已得了他的
     衣钵真传」+ 039:121 邝琏「你的夺命神刀不是钟万堂所传的么」明文徒名，取正式档；
     038:125「你又不是钟万堂的弟子」系李治对冯琳「无极派传人」戏言的误推，非师承否认——
     用户裁定「冯琳就是钟万堂的徒弟，否认只是误会」）；
  3) 莹儿→吕四娘 别名归并（kb/校订/别名归并.tsv 追加 1 行）：005:51 同句明文
     「吕四娘见过了师傅后……独臂老尼道：莹儿，你在我门下九年」——莹儿=吕四娘幼年乳名；
     莹儿 作独立实体仅 江湖三女侠 第 5 回 3 次（total=3）、无跨类型同名、共书单书，
     并入无损；重导后 characters.json 无独立 莹儿 实体、吕四娘频次 +3；
  4) site/data/arts.json 重导对账：13 条新边入 lineage；meta.field_gaps 声明校定行 16；
     sects/weapons 与本批零关系（机制测试见 test_lineage_manual.py）。

档位分布口径（落地前后对比，自检脚本口径同）：落地前 正式28/挂名1/点拨1/记名3（33 边）；
落地后 正式41/挂名1/点拨1/记名3（46 边，+13 全部正式档）。
"""
import csv
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_sects_weapons_arts as exs  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LINEAGE_TSV = REPO / "kb" / "校订" / "武功传承补链.tsv"
ALIAS_TSV = REPO / "kb" / "校订" / "别名归并.tsv"
CHAPTERS = REPO / "章回版"

# D15 新增 13 边（art, from, to, tier, book, loc）——草案2 全 11 条 + 路民瞻 + 钟万堂
D15_ROWS = [
    ("达摩剑法", "允祯", "冯琳", "正式", "江湖三女侠", "028:43"),
    ("阴风毒砂掌", "金独异", "金千岩", "正式", "白发魔女传", "007:11"),
    ("猫鹰扑击", "萨天剌", "冯琳", "正式", "江湖三女侠", "039:5"),
    ("风雷剑法", "齐真君", "纽祜卢", "正式", "七剑下天山", "019:13"),
    ("风雷剑法", "齐真君", "邱东洛", "正式", "七剑下天山", "019:13"),
    ("鸳鸯连环腿", "卓一航", "石天成", "正式", "七剑下天山", "010:75"),
    ("沾衣十八跌", "独臂老尼", "了因", "正式", "江湖三女侠", "017:105"),
    ("沾衣十八跌", "独臂老尼", "甘凤池", "正式", "江湖三女侠", "017:105"),
    ("流云飞袖", "傅青主", "武成化", "正式", "江湖三女侠", "019:135"),
    ("无常夺命", "练霓裳", "武琼瑶", "正式", "七剑下天山", "021:5"),
    ("罗汉伏虎拳", "本空大师", "年羹尧", "正式", "江湖三女侠", "010:97"),
    ("八卦紫金刀法", "独臂老尼", "路民瞻", "正式", "江湖三女侠", "027:37"),
    ("无极剑法", "钟万堂", "冯琳", "正式", "江湖三女侠", "011:9"),
]
SCOPE_BOOKS = {"散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
               "七剑下天山", "冰魄寒光剑", "江湖三女侠"}


def _chapter_line(book: str, loc: str) -> str:
    ch, no = loc.split(":")
    files = sorted(CHAPTERS.glob(f"{book}/{ch}*.txt"))
    assert files, f"章回版/{book}/{ch} 缺失"
    return files[0].read_text(encoding="utf-8").splitlines()[int(no) - 1]


# ================================================================ 1. 正式 TSV 内容纪律
class TestLineageTsvD15:
    """真实 kb/校订/武功传承补链.tsv：D15 批次 13 边落地（先红：行未追加时全红）。"""

    def setup_method(self):
        assert LINEAGE_TSV.exists()
        self.rows, self.stats = exs.load_lineage_supplement()
        self.keys = {(r["art"], r["t"], r["l"], r["tier"], r["book"], r["loc"])
                     for r in self.rows}

    def test_d15_thirteen_rows_consumed(self):
        """校定行 = D10 首批 3 + D15 新增 13 = 16（draft 0——草案2 全量裁定落地）。"""
        assert self.stats["consumed"] == 16
        assert self.stats["draft"] == 0
        missing = [k for k in D15_ROWS if k not in self.keys]
        assert not missing, f"D15 边缺行：{missing}"

    def test_d15_rows_all_zhengshi_and_in_scope(self):
        """13 条新边全部 正式 档（用户逐条裁定：萨天剌→冯琳 取正式档；路民瞻正向读法
        有传授动词取正式；钟万堂→冯琳 明文徒名取正式）；书名全部在 scope 7 书内。"""
        for art, t, l, tier, book, loc in D15_ROWS:
            assert tier == "正式", f"{art} {t}→{l} 档位非正式"
            assert book in SCOPE_BOOKS, f"{art} {t}→{l} 书 {book} 不在 scope"
            assert loc in {r["loc"] for r in self.rows if r["art"] == art}

    def test_loc_028_43_yunzhen_jiaofenglin_damo(self):
        """028:43 明文「允祯亲自教她的少林派达摩剑法」（同句主语=冯琳）。"""
        line = _chapter_line("江湖三女侠", "028:43")
        assert "允祯亲自教她" in line and "达摩剑法" in line and "冯琳" in line

    def test_loc_007_11_jinduyi_jinqianyan(self):
        """007:11 明文：金独异练阴风毒砂掌、金千岩所得不过六七成（叔传侄）。"""
        line = _chapter_line("白发魔女传", "007:11")
        assert "金独异" in line and "阴风毒砂掌" in line and "金千岩" in line

    def test_loc_039_5_satianla_fenglin_maying(self):
        """039:5 明文「施展从八臂神魔那里学来的猎鹰扑击」（主语=冯琳；八臂神魔=萨天剌）。"""
        line = _chapter_line("江湖三女侠", "039:5")
        assert "八臂神魔" in line and "猎鹰扑击" in line and "冯琳" in line

    def test_loc_019_13_qizhenjun_two_disciples(self):
        """019:13 明文：齐真君独创风雷剑法，纽祜卢与邱东洛「都是他的弟子」（一源两弟子）。"""
        line = _chapter_line("七剑下天山", "019:13")
        assert "齐真君" in line and "纽祜卢" in line and "邱东洛" in line
        assert "都是他的弟子" in line

    def test_loc_010_75_zhuoyihang_shitiancheng(self):
        """010:75 明文「武当名宿卓一航，跟他学了九宫神行掌和鸳鸯连环腿」（说话人=石天成）。"""
        line = _chapter_line("七剑下天山", "010:75")
        assert "卓一航" in line and "鸳鸯连环腿" in line

    def test_loc_017_105_zhanyi_two_disciples(self):
        """017:105 明文「独臂神尼秘传的沾衣十八跌……门下只有了因和甘凤池会使」（一源两弟子）。"""
        line = _chapter_line("江湖三女侠", "017:105")
        assert "独臂神尼" in line and "沾衣十八跌" in line and "了因" in line and "甘凤池" in line

    def test_loc_019_135_fuqingzhu_wuchenghua(self):
        """019:135 明文「（太师祖傅青主）曾传了他流云飞袖的绝技」（受者=武成化）。"""
        line = _chapter_line("江湖三女侠", "019:135")
        assert "武成化" in line and "流云飞袖" in line

    def test_loc_021_5_baimo_guanmen_disciple(self):
        """021:5 明文「她是白发魔女的关门弟子」（晦明禅师语，受者=武琼瑶，复证 024:21）。"""
        line = _chapter_line("七剑下天山", "021:5")
        assert "白发魔女" in line and "关门弟子" in line

    def test_loc_010_97_benkong_niangengyao(self):
        """010:97 明文：本空方丈传授年羹尧武功——少林镇山拳法罗汉伏虎拳。"""
        line = _chapter_line("江湖三女侠", "010:97")
        assert "罗汉伏虎拳" in line and "传授" in line

    def test_loc_027_37_luminzhan_bagua_zhengxiang_read(self):
        """027:37 正向读法明文：独臂神尼门下「每个门徒……都有独特的技艺，路民瞻传的是
        八卦紫金刀法」（读作独臂老尼传路民瞻——用户裁定读法①；art=八卦紫金刀法，
        与 D13 证据包 #12 一致；沾衣十八跌门下唯了因甘凤池，见 017:105 同书互证）。"""
        line = _chapter_line("江湖三女侠", "027:37")
        assert "路民瞻" in line and "八卦紫金刀法" in line and "独特的技艺" in line

    def test_loc_011_9_zhongwantang_chuanfenglin(self):
        """011:9 明文：钟万堂「传她武艺」（受者=冯琳，年家六年教养；徒名复证
        001:103/013:59/039:121，无极剑法挂边=无极派师承口径，同 011:43 年羹尧边）。"""
        line = _chapter_line("江湖三女侠", "011:9")
        assert "钟万堂" in line and "传她武艺" in line and "冯琳" in line

    def test_note_kept_for_manual_audit(self):
        """每条新边 note 列非空（人工考订依据摘要，供复核；不进 lineage 边契约）。"""
        by_key = {(r["art"], r["t"], r["l"], r["loc"]): r for r in self.rows}
        for art, t, l, _tier, _book, loc in D15_ROWS:
            assert by_key[(art, t, l, loc)]["note"].strip(), f"{art} {t}→{l} note 空"


# ================================================================ 2. 莹儿→吕四娘 别名归并
class TestAliasMergeYingEr:
    """别名归并.tsv 追加 莹儿→吕四娘（005:51 乳名明文 + 用户裁定）。"""

    def test_alias_row_present_and_no_chain(self):
        """莹儿→吕四娘 行在案；归并表整体可被 load_alias_merges 解析（链式禁令不触发）。"""
        from export_site_characters import load_alias_merges
        merges, meta = load_alias_merges()
        assert merges.get("莹儿") == "吕四娘"
        assert meta["rows"] >= 1
        # 链式禁令：吕四娘 不得再为任何行的 form（load_alias_merges 内置校验，到此处即已通过）
        assert "吕四娘" not in merges

    def test_yinger_no_cross_type_same_name(self):
        """跨类型同名核实：registry entities.json 无「莹儿」规范名（独立 form 仅人物 @ 类，
        江湖三女侠 total=3——并入无损）。"""
        reg = json.loads((REPO / "wuxia-kb" / "registry" / "entities.json")
                         .read_text(encoding="utf-8"))
        hits = [e for e in reg["entities"] if e.get("canonical") == "莹儿"]
        assert all(e.get("type") == "@" for e in hits)
        conc = json.loads((REPO / "wuxia-kb" / "registry" / "concordance" / "江湖三女侠.json")
                          .read_text(encoding="utf-8"))
        ying = [e for e in conc["entities"] if e["canonical"] == "莹儿"]
        assert len(ying) == 1 and ying[0]["total"] == 3
        assert [cc["chapter"] for cc in ying[0]["chapter_counts"]] == [5]

    def test_loc_005_51_ruming_mingwen(self):
        """005:51 乳名明文：同句「吕四娘见过了师傅后」＋独臂老尼当面称「莹儿，你在我门下九年」
        ——莹儿=吕四娘幼年乳名（005:27 试招/005:69「收了莹儿之后已发誓不再收徒」同景互证）。"""
        line = _chapter_line("江湖三女侠", "005:51")
        assert "吕四娘见过了师傅后" in line and "莹儿" in line and "你在我门下九年" in line

    def test_characters_json_yinger_absorbed(self):
        """重导后 characters.json：无独立 莹儿 实体；吕四娘 江湖三女侠 频次 +3
        （1842→1845），aliases 含 莹儿 ≥3（并入不丢频次）。"""
        ch = json.loads((REPO / "site" / "data" / "characters.json")
                        .read_text(encoding="utf-8"))
        assert all(e["canonical"] != "莹儿" for e in ch["entities"]), "莹儿 独立实体未并掉"
        lv = next(e for e in ch["entities"] if e["canonical"] == "吕四娘")
        bj = lv["books"]["江湖三女侠"]
        assert bj["count"] == 1845 and bj["aliases"].get("莹儿", 0) >= 3

    def test_dossiers_json_lvsiniang_total_grew(self):
        """重导后 dossiers.json：吕四娘 appearance_total 1845→1848（+3 莹儿并入）。"""
        dos = json.loads((REPO / "site" / "data" / "dossiers.json").read_text(encoding="utf-8"))
        d = next(x for x in dos["dossiers"] if x["canonical"] == "吕四娘")
        assert d["appearance_total"] == 1848
        assert all(x["canonical"] != "莹儿" for x in dos["dossiers"])


# ================================================================ 3. site/data 重导对账
class TestRealDataArtsD15:
    """重导后真实 arts.json：13 条新边入 lineage + meta 声明（数据即规范）。"""

    def _data(self):
        return json.loads((REPO / "site" / "data" / "arts.json").read_text(encoding="utf-8"))

    def _edge_in(self, rec, art, t, l, tier, book, loc):
        return any(e["t"] == t and e["l"] == l and e["book"] == book
                   and e["loc"] == loc and e["tier"] == tier
                   for e in rec.get("lineage") or [])

    def test_all_thirteen_edges_in_arts_json(self):
        data = self._data()
        byc = {a["canonical"]: a for a in data["arts"]}
        missing = []
        for art, t, l, tier, book, loc in D15_ROWS:
            rec = byc.get(art)
            if rec is None or not self._edge_in(rec, art, t, l, tier, book, loc):
                missing.append((art, t, l, loc))
        assert not missing, f"arts.json 缺 D15 边：{missing}"

    def test_meta_declares_d15_batch(self):
        """meta.field_gaps 声明校定行 16（D10 3 + D15 13）。"""
        gaps = "\n".join(self._data()["meta"]["field_gaps"])
        assert "校定行 16" in gaps

    def test_tier_distribution_after_d15(self):
        """档位计数（落地前后对比）：正式 28→41、挂名 1、点拨 1、记名 3（+13 全正式）。"""
        from collections import Counter
        c = Counter()
        for a in self._data()["arts"]:
            for e in a.get("lineage") or []:
                c[e["tier"]] += 1
        assert c == Counter({"正式": 41, "记名": 3, "挂名": 1, "点拨": 1})
