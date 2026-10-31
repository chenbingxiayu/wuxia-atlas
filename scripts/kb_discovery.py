# -*- coding: utf-8 -*-
"""共享模块：已点亮书目自动发现 + 跨书统一规范名。

扩展约定（新小说接入 = 零代码改动）：
  1. 管线（标注→登记→事件→关系）产出一个新目录 kb/<书>/，含 实体登记表.json；
  2. lit_books() 自动发现该书——build_dossiers / build_site_data / build_pages_data /
     build_arts_data / build_sects_data 全部基于发现结果运行；
  3. 站点页面由 getStaticPaths 遍历数据生成，重跑管线后新书页面自动出现。
"""
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / 'kb'
SITE_DATA = ROOT / 'site' / 'data'
OUT = SITE_DATA  # 兼容旧脚本命名


def lit_books() -> list:
    """已点亮书目 = kb/ 下存在 实体登记表.json 的目录（自动发现，勿硬编码）。"""
    return sorted(
        p.name for p in KB.iterdir()
        if p.is_dir() and (p / '实体登记表.json').exists()
    )


# 跨书统一规范名（依据 kb/README"跨书接口"节）：各书登记表未归并的同人异名，
# 在站点数据层归并到右侧规范名。新书登记表完成归并后可移除对应项。
BOOK_CANON = {'哈玛雅': '飞红巾', '晦明禅师': '岳鸣珂', '白发魔女': '练霓裳'}


def canon(name: str) -> str:
    """规范名映射（跨书同人异名 → 站点统一名）。"""
    return BOOK_CANON.get(name, name)


def dump_json(name: str, payload) -> Path:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    p = SITE_DATA / name
    with open(p, 'w', encoding='utf-8') as f:
        json_dump(payload, f)
    print(f"-> {p} ({p.stat().st_size // 1024} KB)")
    return p


def json_dump(payload, f) -> None:
    import json
    json.dump(payload, f, ensure_ascii=False, indent=1)


def today() -> str:
    return str(date.today())
