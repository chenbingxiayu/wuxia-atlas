# -*- coding: utf-8 -*-
"""生成 site/public/llms.txt —— AI 可读站点规范（N17 · 借 jiangshan-map 范式）。
规模与口径从预构建切片读取，构建期生成，与站点同版本。用法：python scripts/build_llms.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import SITE_DATA, lit_books, today  # noqa: E402

OUT = SITE_DATA.parent / 'public' / 'llms.txt'


def load(name):
    p = SITE_DATA / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def main() -> int:
    books = load('books.json')
    lit = lit_books()
    chars = load('entity-index.json')
    gaz = load('gazetteer.json')
    weapons = load('weapons.json')
    n_ent = sum(e.get('n', 0) and 1 for e in (chars or {}).get('entities', [])) if chars else 0
    n_place = sum(1 for p in (gaz or {}).get('places', []) if p.get('lat') is not None)
    n_weap = len((weapons or {}).get('weapons', []))
    events = sum(len(v.get('events', {})) and sum(len(x) for x in v.get('events', {}).values())
                 for v in (load('chapters.json') or {}).values() if isinstance(v, dict)) or '见各书事件表'

    L = []
    A = L.append
    A('# 江湖图志 Liang Yusheng Wuxia Atlas')
    A('')
    A('> 梁羽生 34 部武侠小说宇宙的知识图谱站点：人物/武功/门派/名物/时空/评分，'
      '每个结论可溯源到「书·回:行」定位符。严格限于小说文本，不做史料考证。')
    A('')
    A('## 数据规模')
    A(f'- 已点亮（KB 完成）{len(lit)} 部：{"、".join(lit)}')
    A(f'- 规范实体 {n_ent}+（人物/武功等，见 entity-index.json）· 地理坐标点 {n_place}（WGS-84，Nominatim+人工核验）'
      f'· 入谱名物 {n_weap}')
    A('- 事件层（叙事层，含定位符）见各书图谱下载；引用档位 L0 定位符 / L1 单句 / L2 仅本地（语料层永不发布）')
    A('')
    A('## 页面')
    A('- /books/ 作品库（34 部全有页；未点亮部仅元数据）')
    A('- /characters/ 人物谱（别名/师承/战绩/出场曲线，全带定位符）')
    A('- /arts/ 武功谱 · /weapons/ 神兵谱（品阶+历代流转链）· /sects/ 门派志')
    A('- /atlas 时空行踪地图（真实省界底图 DataV；回目滑块/地名谱系卡/虚实透镜；支持 ?book=&chap=&person=&place=&lens= 深链）')
    A('- /universe 宇宙地铁图 · /ratings 侠谱评分 · /qa 江湖问答 · /audit 穿帮雷达')
    A('')
    A('## 机器接口')
    A('- MCP Server：`node scripts/mcp_server.js`（stdio，零依赖）— 工具：inspect_character / '
      'inspect_place / inspect_artifact / search_atlas；全部返回带定位符，档案未载答"档案未载"。')
    A('- 浏览器：`window.atlasAPI.resolve / inspect / locate`（见 /atlas-api.js）。')
    A('- 数据下载：/data/（图谱 JSON/CSV，CC BY-NC-SA）；schema 见各 JSON meta 字段。')
    A('')
    A('## 引用与版权')
    A('- 图谱层（实体/关系/事件三元组、定位符、统计）：CC BY-NC-SA。')
    A('- 语料层（原文）：版权至 2059 年底，永不发布；L1 短引文仅评论性单句且随页声明。')
    A(f'- 数据版本：{today()}（kb 快照；页脚随页标注）。')
    A('')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(f'-> {OUT} ({OUT.stat().st_size} bytes)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
