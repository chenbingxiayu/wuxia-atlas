# -*- coding: utf-8 -*-
"""W0-T1 · 导出层书目范围（scope）基础设施测试（天山演示版总体方案 §一，2026-11-08）。

只测纯函数与配置加载：不依赖 site/data；错误路径用临时目录 + monkeypatch 构造。
被测对象：scripts/export_site_common.py 的 ScopeError / load_scope / in_scope /
scope_meta / scope_from_args（W0-T1 新增；接线到各导出器是 W0-T3 的范围）。
"""
import json
import sys
from pathlib import Path

import pytest

# 导出脚本目录入 path（export_site_common 依赖同目录的 scripts/config.py）
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import export_site_common as esc  # noqa: E402

PROFILE = "tianshan-demo"
# 7 部天山系列书（方案 §1.1；顺序 = site_scope.json 配置顺序，不得重排）
BOOKS_7 = ["散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
           "七剑下天山", "冰魄寒光剑", "江湖三女侠"]


# ---------------------------------------------------------------- 全量口径（不带 --scope，向后兼容）
class TestFullScope:
    """scope 为 None = 全量口径：任何书都在范围内，meta 不带 scope 字段。"""

    def test_in_scope_none_is_always_true(self):
        for book in ("白发魔女传", "大唐游侠传", "七剑下天山", "不存在的书"):
            assert esc.in_scope(book, None) is True

    def test_scope_meta_none(self):
        assert esc.scope_meta(None) is None

    def test_scope_from_args_absent(self):
        assert esc.scope_from_args([]) is None
        assert esc.scope_from_args(["x"]) is None
        assert esc.scope_from_args(["--apply"]) is None


# ---------------------------------------------------------------- profile 加载（真实 config/site_scope.json）
class TestLoadScope:
    def test_load_tianshan_demo(self):
        """合法加载：profile 名、books 顺序保持、desc 保留。"""
        scope = esc.load_scope(PROFILE)
        assert scope["profile"] == PROFILE
        assert scope["books"] == BOOKS_7  # 顺序保持
        assert isinstance(scope.get("desc"), str) and scope["desc"]  # desc 保留

    def test_in_scope_hit(self):
        scope = esc.load_scope(PROFILE)
        assert esc.in_scope("白发魔女传", scope) is True

    def test_in_scope_miss(self):
        scope = esc.load_scope(PROFILE)
        assert esc.in_scope("大唐游侠传", scope) is False

    def test_scope_meta_profile(self):
        """meta 形态：{"scope": profile 名, "books": [...]}（前端 ScopeNote 消费）。"""
        scope = esc.load_scope(PROFILE)
        meta = esc.scope_meta(scope)
        assert meta["scope"] == PROFILE
        assert meta["books"] == BOOKS_7


# ---------------------------------------------------------------- 错误路径（临时目录构造，不碰真实 config）
def _patch_cfg(tmp_path, monkeypatch):
    """把 SITE_SCOPE_CONFIG 指向临时文件并返回该路径（此文件默认不存在）。"""
    p = tmp_path / "site_scope.json"
    monkeypatch.setattr(esc, "SITE_SCOPE_CONFIG", p)
    return p


class TestLoadScopeErrors:
    def test_file_missing(self, tmp_path, monkeypatch):
        _patch_cfg(tmp_path, monkeypatch)  # 不写文件
        with pytest.raises(esc.ScopeError, match="scope"):
            esc.load_scope(PROFILE)

    def test_broken_json(self, tmp_path, monkeypatch):
        p = _patch_cfg(tmp_path, monkeypatch)
        p.write_text('{"profiles": [broken', encoding="utf-8")
        with pytest.raises(esc.ScopeError, match="scope"):
            esc.load_scope(PROFILE)

    def test_profile_missing(self, tmp_path, monkeypatch):
        p = _patch_cfg(tmp_path, monkeypatch)
        p.write_text(
            json.dumps({"profiles": {"other": {"desc": "x", "books": ["散花女侠"]}}},
                       ensure_ascii=False),
            encoding="utf-8",
        )
        with pytest.raises(esc.ScopeError, match="scope"):
            esc.load_scope(PROFILE)

    def test_books_invalid(self, tmp_path, monkeypatch):
        """profile 存在但 books 为空列表 → 同样算配置错误。"""
        p = _patch_cfg(tmp_path, monkeypatch)
        p.write_text(
            json.dumps({"profiles": {PROFILE: {"desc": "x", "books": []}}},
                       ensure_ascii=False),
            encoding="utf-8",
        )
        with pytest.raises(esc.ScopeError, match="scope"):
            esc.load_scope(PROFILE)


# ---------------------------------------------------------------- --scope 命令行参数解析
class TestScopeFromArgs:
    def test_space_form(self):
        assert esc.scope_from_args(["--scope", PROFILE]) == PROFILE

    def test_eq_form(self):
        assert esc.scope_from_args([f"--scope={PROFILE}"]) == PROFILE

    def test_among_other_args(self):
        assert esc.scope_from_args(["--apply", "--scope", PROFILE, "extra"]) == PROFILE

    def test_all_means_full(self):
        """方案 §1.1：--scope all 与不带参数同为全量口径（返回 None）。"""
        assert esc.scope_from_args(["--scope", "all"]) is None

    def test_missing_value_raises(self):
        with pytest.raises(esc.ScopeError, match="scope"):
            esc.scope_from_args(["--scope"])
