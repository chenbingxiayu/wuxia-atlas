# -*- coding: utf-8 -*-
"""E2a · llms.txt 新鲜度测试（天山演示版任务 E2a，2026-11-12）。

被测对象：父仓 scripts/build_llms.py（读 site/data → site/public/llms.txt；
dist 副本随 astro build 由 public/ 整体拷贝，不单独手抄）。
背景：site/data 已切天山演示口径（books.json meta.scope=tianshan-demo，仅 7 部），
但 llms.txt 停在 11-07（"深度解析 15 部"＋硬编码"34 部"×2，且无秘籍谱/丹药谱——D11 新切片新页）。

口径固化（测试即规范）：
  - 两谱条目：生成文本含 /manuals/ 秘籍谱、/elixirs/ 丹药谱一节，
    件数与毒解配对组数取自 site/data/manuals.json、elixirs.json meta.totals（禁硬编码）。
  - 7 书演示口径：「深度解析 7 部」＋ 7 书名逐一点名（scope 自动生效）。
  - 无全量/旧口径残留：「34 部」「未点亮部仅元数据」不得出现。
  - 发布层不落后于构建器：site/public/llms.txt 与生成函数输出逐字一致。
  - dist 副本与 public 一致（dist 为构建产物，缺席 skip 不误报）。
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_llms  # noqa: E402

SITE = REPO_ROOT / "site"
SITE_DATA = SITE / "data"


def _load(name):
    return json.loads((SITE_DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def text():
    return "\n".join(build_llms.collect())


# ================================================================ 1. 两谱条目（D11）
class TestSpectrumSection:
    def test_manuals_listed_with_count(self, text):
        """秘籍谱条目：页链接 /manuals/ + 件数（读 manuals.json meta.totals，禁硬编码）。"""
        manuals_n = _load("manuals.json")["meta"]["totals"]["manuals"]
        assert "/manuals/" in text, "llms.txt 缺秘籍谱页条目"
        assert "秘籍谱" in text
        assert f"{manuals_n} 件" in text, f"秘籍谱件数 {manuals_n} 未进 llms.txt"

    def test_elixirs_listed_with_counts(self, text):
        """丹药谱条目：页链接 /elixirs/ + 丹药/药材分计 + 毒解配对组数（D16）。"""
        totals = _load("elixirs.json")["meta"]["totals"]
        assert "/elixirs/" in text, "llms.txt 缺丹药谱页条目"
        assert "丹药谱" in text
        assert f"{totals['丹药']} 件" in text and f"{totals['药材']} 件" in text
        assert f"毒解配对 {totals['毒解配对']} 组" in text, "毒解配对组数未进 llms.txt"


# ================================================================ 2. 7 书演示口径（scope 自动生效）
class TestDemoScope:
    def test_seven_book_scale_line(self, text):
        books = _load("books.json")
        assert books["meta"].get("scope") == "tianshan-demo"
        assert len(books["books"]) == 7
        assert "深度解析 7 部" in text, "llms.txt 未按演示口径输出 7 部"
        for w in books["books"]:
            assert w["book"] in text, f"演示书目「{w['book']}」未在 llms.txt 点名"

    def test_no_full_corpus_residual(self, text):
        """全量口径残留清零：硬编码「34 部」与旧「未点亮部仅元数据」文案。"""
        assert "34 部" not in text, "llms.txt 仍有「34 部」全量残留"
        assert "未点亮部仅元数据" not in text
        assert "15 部" not in text, "llms.txt 仍有 11-07 旧快照的 15 部口径"


# ================================================================ 3. 发布层与构建器同步
class TestPublishedFresh:
    def test_public_file_matches_builder(self, text):
        """site/public/llms.txt 与生成函数逐字一致（重建后不落后）。"""
        p = SITE / "public" / "llms.txt"
        assert p.exists(), "site/public/llms.txt 不存在"
        assert p.read_text(encoding="utf-8") == text + "\n"

    def test_dist_copy_matches_public(self):
        """dist 副本随 astro build 同步（构建产物，缺席则 skip）。"""
        pub = SITE / "public" / "llms.txt"
        dist = SITE / "dist" / "llms.txt"
        if not dist.exists():
            pytest.skip("site/dist 未构建（构建产物不入库）")
        assert dist.read_text(encoding="utf-8") == pub.read_text(encoding="utf-8")

    def test_version_line_present(self, text):
        assert "数据版本：" in text
