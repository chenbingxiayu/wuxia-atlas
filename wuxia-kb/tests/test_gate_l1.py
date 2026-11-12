# -*- coding: utf-8 -*-
"""W2-D4-C · copyright_gate L1 规则（武功评语 ≤16 字 × ≤2 条 + 「—— 原著 · 」署名式样）测试。

背景（§5.5 数据契约：L1 参数进 copyright_gate 参数化规则）：武功评语（kb/校订/武功评语.tsv →
arts.json comments → dist /arts/<武功>/ 详情页「原著怎么说」评语卡）属 L1 短引文，发布口径
= 单条 ≤16 字、每页 ≤2 条、逐条带「—— 原著 · <书名>」署名。超限即为违规（ruleL1），
闸门 FAIL。现有 4 门数据（天山剑法/追风剑法/须弥剑法/寒涛剑法）全合规。

检测定位（任务书）：按 dist HTML 的评语区块标记定位——quote-line 块（引文「…」 +
quote-src 署名 span）。署名式样缺失也是违规（quote 块存在而没有「—— 原著 · 」标记）。

测试口径（先红后绿；除「真实 dist」一节外全部合成 HTML / 临时 dist 子集，不写真实站点）：
  - scan_l1_html（纯函数）：16 字边界（16 合规 / 17 违规）、每页 2 条上限（2 合规 / 3 违规）、
    署名式样缺失报违规、合规样本（真实 dist 同款 markup，含 astro-cid 属性与换行）0 违规。
  - scan 集成（临时 dist）：合规页 ruleL1=0 且 ok=True（rule1/2/3 同绿）；超长样本 →
    ok=False、violations 含 ruleL1（构造 FAIL 验证）。
  - 真实 dist（live site/dist，只读）：ruleL1=0；rule1/2 与既有基线一致（0）；JSON 照常解析。
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import copyright_gate as cg  # noqa: E402

REAL_DIST = REPO_ROOT / "site" / "dist"

# 真实 dist 同款评语块 markup（dist/arts/天山剑法/index.html，含 astro-cid 属性与换行；
# 链接带 base 前缀——rule3 口径，见 copyright_gate 3b）
PAGE = ('<html><body><section><h2>原著怎么说</h2><div class="card quotes">'
        '<p class="quote-line" data-astro-cid-x>「{quote}」\n'
        '<span class="quote-src" data-astro-cid-x>—— 原著 · {book} '
        '<a href="/wuxia-atlas/books/%E4%B8%83/000/">000:125</a></span> </p>'
        '</div></section></body></html>')


def _page(quote="天下独步的剑法", book="七剑下天山", n=1):
    return PAGE.format(quote=quote, book=book) * 1 if n == 1 else "".join(
        PAGE.format(quote=q, book=book) for q in ([quote] * n))


def _kinds(violations):
    return {v[0] for v in violations}


# ================================================================ 1. scan_l1_html（纯函数）
class TestScanL1Html:
    def test_quote_at_16_chars_is_compliant(self):
        q = "一二三四五六七八九十甲乙丙丁戊己"  # 恰 16 字
        assert len(q) == 16
        assert cg.scan_l1_html(_page(quote=q), "arts/x/index.html") == []

    def test_quote_17_chars_violates(self):
        q = "一二三四五六七八九十甲乙丙丁戊己庚"  # 17 字
        v = cg.scan_l1_html(_page(quote=q), "arts/x/index.html")
        assert v and all(k == "ruleL1" for k, *_ in v)
        assert "17" in v[0][1]

    def test_two_quotes_per_page_ok_three_violate(self):
        assert cg.scan_l1_html(_page(n=2), "arts/x/index.html") == []
        v = cg.scan_l1_html(_page(n=3), "arts/x/index.html")
        assert any(k == "ruleL1" and "3 条" in d for k, d, _c in v)

    def test_missing_signature_violates(self):
        """署名式样缺失（无「—— 原著 · 」标记）→ ruleL1 违规。"""
        html = ('<section><div class="card quotes">'
                '<p class="quote-line">「天下独步的剑法」<span class="quote-src">出处不详</span></p>'
                '</div></section>')
        v = cg.scan_l1_html(html, "arts/x/index.html")
        assert v and v[0][0] == "ruleL1" and "署名" in v[0][1]

    def test_compliant_real_markup_zero_violations(self):
        html = _page(quote="追风剑法，迅捷无伦", book="白发魔女传")
        assert cg.scan_l1_html(html, "arts/追风剑法/index.html") == []

    def test_non_quote_pages_ignored(self):
        """无评语块的页面（正文含「—— 原著」字样但无 quote-line 块）不触发。"""
        html = '<p>这段正文提到 —— 原著 · 某书，但没有评语块。</p>'
        assert cg.scan_l1_html(html, "characters/x/index.html") == []


# ================================================================ 2. scan 集成（临时 dist 子集）
class TestScanIntegration:
    def _dist(self, tmp_path, html, name="index.html"):
        d = tmp_path / "dist" / "arts" / "x"
        d.mkdir(parents=True)
        (d / name).write_text(html, encoding="utf-8")
        return tmp_path / "dist"

    def test_compliant_dist_passes_all_rules(self, tmp_path):
        d = self._dist(tmp_path, _page())
        res = cg.scan(d, "wuxia-atlas", corpus_root=tmp_path / "corpus")
        assert res["ruleL1_hits"] == 0
        assert res["rule1_corpus_leaks"] == 0 and res["rule2_hits"] == 0 and res["rule3_hits"] == 0
        assert res["ok"] is True

    def test_oversized_quote_fails_gate(self, tmp_path):
        """构造超长样本（17 字评语）→ 闸门 FAIL（ok=False，violations 报 ruleL1）。"""
        q = "一二三四五六七八九十甲乙丙丁戊己庚"
        d = self._dist(tmp_path, _page(quote=q))
        res = cg.scan(d, "wuxia-atlas", corpus_root=tmp_path / "corpus")
        assert res["ruleL1_hits"] == 1
        assert res["ok"] is False
        assert _kinds(res["violations"]) == {"ruleL1"}

    def test_three_quotes_fails_gate(self, tmp_path):
        d = self._dist(tmp_path, _page(n=3))
        res = cg.scan(d, "wuxia-atlas", corpus_root=tmp_path / "corpus")
        assert res["ruleL1_hits"] >= 1 and res["ok"] is False


# ================================================================ 3. 真实 dist（live site/dist，只读）
@pytest.mark.skipif(not REAL_DIST.exists(), reason="site/dist 不存在（未构建）")
class TestRealDist:
    def test_real_dist_ruleL1_zero_violations(self):
        res = cg.scan(REAL_DIST, "wuxia-atlas")
        assert res["ruleL1_hits"] == 0, [v for v in res["violations"] if v[0] == "ruleL1"]

    def test_real_dist_rule1_rule2_unchanged(self):
        res = cg.scan(REAL_DIST, "wuxia-atlas")
        assert res["rule1_corpus_leaks"] == 0
        assert res["rule2_hits"] == 0
        assert res["json_parsed"] == res["json_files"] > 0

    def test_real_dist_l1_quote_pages_detected(self):
        """4 门带评语的 /arts/ 详情页被 ruleL1 覆盖到（每页 1 条、全部带署名 → 0 违规）。"""
        arts = REAL_DIST / "arts"
        pages = [p for p in arts.glob("*/index.html")] if arts.exists() else []
        with_sig = [p for p in pages if "—— 原著 ·" in p.read_text(encoding="utf-8", errors="ignore")]
        assert len(with_sig) >= 4
        for p in with_sig:
            assert cg.scan_l1_html(p.read_text(encoding="utf-8", errors="ignore"),
                                   str(p.relative_to(REAL_DIST))) == []
