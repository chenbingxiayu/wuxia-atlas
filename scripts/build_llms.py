# -*- coding: utf-8 -*-
"""生成 site/public/llms.txt —— AI 可读站点规范（N17 · 借 jiangshan-map 范式）。
规模与口径从预构建切片读取，构建期生成，与站点同版本。用法：python scripts/build_llms.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import SITE_DATA, lit_books, today  # noqa: E402

OUT = SITE_DATA.parent / 'public' / 'llms.txt'

# scope profile → 用户可见名（与 site/src/lib/scope.ts SCOPE_PROFILE_LABELS 同表；无 scope = 全量口径）
SCOPE_LABELS = {'tianshan-demo': '天山系列'}


def load(name):
    p = SITE_DATA / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def scope_note(books) -> str | None:
    """演示口径括注（如「天山系列 7 部」）——书目数走 books.json 现载（scope.ts 同语义）。"""
    meta = (books or {}).get('meta', {})
    prof = meta.get('scope')
    prof = prof.get('scope') if isinstance(prof, dict) else prof
    if not prof:
        return None
    n = len((books or {}).get('books', []))
    return f"{SCOPE_LABELS.get(prof, prof)} {n} 部"


def collect() -> list:
    """生成 llms.txt 行数组（纯函数，读 site/data；测试读这里——test_llms_fresh.py）。"""
    books = load('books.json')
    # 深度解析口径与站点一致：books.json kb_status（lit_books() 读旧 kb/ 目录，已滞后——spec 011-T5）
    lit = sorted(w['book'] for w in (books or {}).get('books', [])
                 if w.get('kb_status') in ('已点亮', 'lit'))
    chars = load('entity-index.json')
    gaz = load('gazetteer.json')
    weapons = load('weapons.json')
    n_ent = sum(e.get('n', 0) and 1 for e in (chars or {}).get('entities', [])) if chars else 0
    n_place = sum(1 for p in (gaz or {}).get('places', []) if p.get('lat') is not None)
    n_weap = len((weapons or {}).get('weapons', []))
    events = sum(len(v.get('events', {})) and sum(len(x) for x in v.get('events', {}).values())
                 for v in (load('chapters.json') or {}).values() if isinstance(v, dict)) or '见各书事件表'
    note = scope_note(books)
    n_books = len((books or {}).get('books', []))

    L = []
    A = L.append
    A('# 江湖图志 Liang Yusheng Wuxia Atlas')
    A('')
    head = '梁羽生武侠小说宇宙的知识图谱站点'
    rest = '：人物/武功/门派/名物/时空/评分，每个结论可溯源到「书·回:行」定位符。' \
           '严格限于小说文本，不做史料考证。'
    if note:
        A(f'> {head}（演示口径：{note}）{rest}')
    else:
        A(f'> {head}{rest}')
    A('')
    A('## 数据规模')
    A(f'- 深度解析 {len(lit)} 部：{"、".join(lit)}')
    A(f'- 图谱实体 {n_ent}+（人物/武功等，见 entity-index.json）· 地理坐标点 {n_place}（WGS-84，Nominatim 检索·逐点核验进行中）'
      f'· 入谱名物 {n_weap}')
    A('- 事件层（叙事层，含定位符）见各书图谱下载；引用档位 L0 定位符 / L1 单句 / L2 仅本地（语料层永不发布）')
    A('')
    # 名物两谱（D11 秘籍谱/丹药谱）：件数/口径读切片 meta，缺文件则整节省略
    spectrum = []
    manuals = load('manuals.json')
    if manuals:
        mt = manuals.get('meta', {}).get('totals', {})
        m_n = mt.get('manuals', len(manuals.get('manuals', [])))
        spectrum.append(f'- /manuals/ 秘籍谱：考订秘籍 {m_n} 件（来历/传承/见于书目，逐处出场挂定位符；通名不入谱）')
    elixirs = load('elixirs.json')
    if elixirs:
        et = elixirs.get('meta', {}).get('totals', {})
        spectrum.append(f'- /elixirs/ 丹药谱：丹药 {et.get("丹药", "—")} 件 · 药材 {et.get("药材", "—")} 件'
                        f'（出处频次+定位符）；毒解配对 {et.get("毒解配对", 0)} 组（双向结构化）')
    if spectrum:
        A('## 名物两谱')
        L.extend(spectrum)
        A('')
    A('## 页面')
    if note:
        A(f'- /books/ 作品库（{note}全有页）')
    else:
        A(f'- /books/ 作品库（{n_books} 部全有页；未点亮部仅元数据）')
    A('- /characters/ 人物谱（别名/师承/战绩/出场曲线，全带定位符）')
    A('- /arts/ 武功谱 · /weapons/ 神兵谱（品阶+历代流转链）· /sects/ 门派志')
    A('- /atlas 时空行踪地图（真实省界底图 DataV；回目滑块/地名谱系卡/虚实透镜；支持 ?book=&chap=&person=&place=&lens= 深链）')
    A('- /universe 宇宙地铁图 · /ratings 武评（江湖座次） · /qa 江湖问答 · /audit 穿帮雷达')
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
    return L


def main() -> int:
    L = collect()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(f'-> {OUT} ({OUT.stat().st_size} bytes)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
