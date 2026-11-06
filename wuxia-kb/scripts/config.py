# -*- coding: utf-8 -*-
"""C0a · 多书注册表 —— 34 部书的路径解析与配置唯一来源。

解决 docs/05 §1.2-1 的 shiji 技术债：路径写死三种风格（相对 cwd ×8、__file__ 推导 ×11）。
所有脚本 import 本文件取路径与书目，禁止自行拼路径。

目录约定（新产物一律落 wuxia-kb/ 大目录下）：
  wuxia-kb/            本包根（config.ROOT）
  wuxia-kb/scripts/    管线脚本
  wuxia-kb/wordlists/  词表双轨数据
  wuxia-kb/skills/     SKILL 文档
  <repo>/章回版/<书>/NNN*.txt   锁定底本（只读输入）
  <repo>/kb/           既有 KB 资产（只读输入：招式表/神兵表/gazetteer/互文引用表…）
  wuxia-kb/tagged/     标注语料产出（G1 已收口 2026-11-03：试点回 003/004 已产出）
  wuxia-kb/logs/       运行日志（IT-only，不进 git 的报告类产物）

底本状态：白发魔女传（试点书）与江湖三女侠（2026-11-05 首批换书批次）已在
BOOK_OVERRIDES 回填 sha256 组合指纹（hexdigest 前 16 位）并锁定；其余书走自动发现，
锁定前 fingerprint=None（status 显示"未锁定"）。
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # wuxia-kb/
REPO_ROOT = ROOT.parent                              # Wuxiaxiaoshuo/
CORPUS_ROOT = REPO_ROOT / "章回版"                   # 锁定底本（只读）
LEGACY_KB = REPO_ROOT / "kb"                         # 既有资产（只读）
SHIJI_SCRIPTS = Path(os.environ.get(
    "SHIJI_KB", r"C:\Users\YANG Ruosong\Documents\workspace\shiji-kb")) / "scripts"

DIR_SCRIPTS = ROOT / "scripts"
DIR_WORDLISTS = ROOT / "wordlists"
DIR_SKILLS = ROOT / "skills"
DIR_TAGGED = ROOT / "tagged"                         # 新管线标注产出
DIR_REGISTRY = ROOT / "registry"                     # 实体/关系登记层产出
DIR_LOGS = ROOT / "logs"


def patches_dir(book: str):
    """补标建议 TSV 按书子目录（2026-11-05 子目录化）：registry/patches/<book>/。
    起因：扁平目录下章号无书前缀，江湖三女侠 034-048 与白发魔女传 001-032 同占
    一目录（docs/47 §7.5/§八）。"""
    return DIR_REGISTRY / "patches" / book

SPEC_VERSION = "0.3-draft"

# 章回文件名模式：`001　第一回　…….txt`（全角空格分隔；两位/三位回号均容忍）
CHAPTER_FILE_RE = re.compile(r"^(\d{1,3})\s+第([一二三四五六七八九十百零〇\d]+)回")

# G0 拍板（2026-11-03）：底本=章回版锁定；试点书=白发魔女传
PILOT_BOOK = "白发魔女传"
# 手工覆盖表（自动发现失败或需修正时在此登记；slug 待回填）
BOOK_OVERRIDES = {
    # 指纹 = 该书底本目录下章回文件（按文件名排序）字节拼接后的 sha256，取 hexdigest 前 16 位。
    # 白发魔女传 32 回：3843aeb3e2b0e4b4（试点书，2026-11-04 复核）
    "白发魔女传": {"slug": None, "fingerprint": "sha256:3843aeb3e2b0e4b4", "chapters": 32},
    # 江湖三女侠 48 回（2026-11-05 首批换书批次；同法复算）
    "江湖三女侠": {"slug": None, "fingerprint": "sha256:db56249aba01a746", "chapters": 48},
}

_CHAPTER_NUM_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
                   "八": 8, "九": 9, "十": 10, "百": 100, "零": 0, "〇": 0}


def cn_num_to_int(s: str):
    """'四十三'→43 的保守转换（只处理十/百内组合；阿拉伯数字直转）。失败返回 None。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    total, tens = 0, 0
    for ch in s:
        v = _CHAPTER_NUM_CN.get(ch)
        if v is None:
            return None
        if ch in ("十",):
            tens = (tens or 1) * 10
        elif ch in ("百",):
            total = (total + tens) * 100 or 100
            tens = 0
        else:
            tens += v
    return total + tens


def discover_books():
    """扫描章回版目录 → {书名: {chapters, slug, fingerprint, chapter_files}}。

    只发现不修改；字段缺省满足"未锁定"语义（fingerprint=None）。
    """
    books = {}
    if not CORPUS_ROOT.exists():
        return books
    for entry in sorted(CORPUS_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        files = sorted(p for p in entry.glob("*.txt") if CHAPTER_FILE_RE.match(p.name))
        if not files:
            continue
        meta = {
            "chapters": len(files),
            "slug": None,           # G0 拍板后回填（锚点用作品 ID）
            "fingerprint": None,    # 底本锁定后回填（sha256 或版本说明）
            "chapter_files": [p.name for p in files],
        }
        meta.update(BOOK_OVERRIDES.get(entry.name, {}))
        books[entry.name] = meta
    return books


_BOOKS_CACHE = None


def books(force=False):
    global _BOOKS_CACHE
    if _BOOKS_CACHE is None or force:
        _BOOKS_CACHE = discover_books()
    return _BOOKS_CACHE


def book_names():
    return sorted(books().keys())


def corpus_dir(name: str) -> Path:
    return CORPUS_ROOT / name


def chapter_path(name: str, no: int) -> Path:
    """回号(1-based) → 底本文件路径；找不到抛 FileNotFoundError。"""
    prefix = f"{no:03d}"
    d = corpus_dir(name)
    for p in sorted(d.glob("*.txt")):
        m = CHAPTER_FILE_RE.match(p.name)
        if m and m.group(1).lstrip("0") == prefix.lstrip("0") and (m.group(1) == prefix or p.name.startswith(prefix)):
            return p
    # 兜底：按中文回号匹配
    for p in sorted(d.glob("*.txt")):
        m = CHAPTER_FILE_RE.match(p.name)
        if m and cn_num_to_int(m.group(2)) == no:
            return p
    raise FileNotFoundError(f"{name} 第 {no} 回底本未找到（{d}）")


def tagged_path(name: str, no: int) -> Path:
    return DIR_TAGGED / name / f"{no:03d}.tagged.md"


def struct_path(name: str, no: int) -> Path:
    """结构文件路径（N1 管线产物，SKILL_02a/02b §8.1 阶段流水）：DIR_TAGGED/<书>/NNN.struct.md。"""
    return DIR_TAGGED / name / f"{no:03d}.struct.md"


def ensure_dirs():
    for d in (DIR_SCRIPTS, DIR_WORDLISTS, DIR_SKILLS, DIR_TAGGED, DIR_REGISTRY, DIR_LOGS):
        d.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    bs = books()
    print(f"发现 {len(bs)} 部书：")
    for k, v in bs.items():
        print(f"  {k}: {v['chapters']} 回, slug={v['slug']}, fingerprint={'未锁定' if not v['fingerprint'] else '已锁定'}")
