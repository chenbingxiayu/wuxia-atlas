# -*- coding: utf-8 -*-
"""G0.5：时空切片 —— 人-回-地共现序列 + 回目事件（L0）+ 内联江湖状态。

用法：python scripts/build_atlas_slices.py

输入（全部解析结果，lit_books() 自动发现）：
  kb/<书>/实体登记表.json   @ 人物 / = 地点 的 chapters（共现的粒度 = 同回在场，蓝图 A1）
  kb/<书>/事件表.json       回目事件流（L0 字段：loc/verb/主/客/置信；dropped 与 excerpt 剔除）
  site/data/gazetteer.json  地名 → 坐标/虚实（工具 D 产物，无坐标地点照收、标注 real/缺坐标）
  kb/作品元数据表.json       书内年代（内联状态框）
输出：
  site/data/atlas/<书>.json  每书一包（MapTrail 岛按书懒加载）
  site/data/atlas/state.json 书目清单 + 内联状态（皇帝年代；掌门位待工具 B 世系表接入）

语义约定：
  bychap[c].p / bychap[c].l = 第 c 回在场的全体人物/地点（登记表定位符归并）；
  人物 P 在第 c 回的行踪 = bychap[c].l 当且仅当 P ∈ bychap[c].p —— 客户端按滑块过滤即可，
  不预展开人×地矩阵（同一数据同时服务 行踪图 / 河流图 / G11 寻路 / 地名谱系卡）。
"""
import json
from pathlib import Path

from kb_discovery import KB, SITE_DATA, canon, dump_json, lit_books, today

OUT_DIR = SITE_DATA / 'atlas'
GAZ = SITE_DATA / 'gazetteer.json'


def load_gazetteer():
    g = json.loads(GAZ.read_text(encoding='utf-8')) if GAZ.exists() else {'places': []}
    return {p['name']: p for p in g['places']}


def chapter_of(loc: str) -> int:
    return int(loc[:3])


def build_book(book: str, gaz):
    reg = json.loads((KB / book / '实体登记表.json').read_text(encoding='utf-8'))
    persons, places, bychap = {}, {}, {}
    for key, ent in reg['entities'].items():
        code, canonical = key[0], canon(ent.get('canonical') or key[1:])
        if not ent.get('locators'):
            continue
        chaps = sorted({chapter_of(loc) for loc in ent['locators']})
        for c in chaps:
            slot = bychap.setdefault(c, {'p': [], 'l': []})
            (slot['p'] if code == '@' else slot['l']).append(canonical)
        if code == '@':
            cur = persons.setdefault(canonical, {'n': 0, 'chaps': set()})
            cur['n'] += ent.get('count', 0)
            cur['chaps'].update(chaps)
        elif code == '=':
            g = gaz.get(canonical, {})
            cur = places.setdefault(canonical, {'chaps': set(), 'real': g.get('real'),
                                                'lat': g.get('lat'), 'lng': g.get('lng'),
                                                'precision': g.get('precision'),
                                                'aliases': sorted(g.get('aliases', []))})
            cur['chaps'].update(chaps)
    for c in bychap:
        bychap[c]['p'] = sorted(set(bychap[c]['p']))
        bychap[c]['l'] = sorted(set(bychap[c]['l']))
    ev = json.loads((KB / book / '事件表.json').read_text(encoding='utf-8'))
    events = {}
    for e in ev.get('events', []):
        if e.get('dropped') or e.get('curation', {}).get('verdict') == 'drop':
            continue
        c = chapter_of(e['loc'])
        events.setdefault(c, []).append({
            'l': e['loc'], 'v': e.get('verb') or e.get('verb_code', ''),
            'a': e.get('subject'), 'b': e.get('object'),
            'code': e.get('verb_code'), 'conf': e.get('confidence'),
        })
    meta_w = json.loads((KB / '作品元数据表.json').read_text(encoding='utf-8'))
    w = next((w for w in meta_w['works'] if w['book'] == book), {})
    n_chapters = max([c for c in bychap] or [w.get('chapters', 0)])
    return {
        'meta': {'generated': today(), 'schema': 'atlas-slice-v1', 'book': book,
                 'copyright': 'L0 图谱层：仅定位符与结构化事实，不含摘录'},
        'title': book, 'era': w.get('era'), 'era_conf': w.get('era_conf'),
        'chapters': n_chapters,
        'persons': {k: {'n': v['n'], 'chaps': sorted(v['chaps'])} for k, v in
                    sorted(persons.items(), key=lambda kv: -kv[1]['n'])},
        'places': {k: {**{kk: vv for kk, vv in v.items() if kk != 'chaps'},
                       'chaps': sorted(v['chaps'])} for k, v in
                   sorted(places.items(), key=lambda kv: -len(kv[1]['chaps']))},
        'bychap': {str(c): bychap[c] for c in sorted(bychap)},
        'events': {str(c): events[c] for c in sorted(events)},
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gaz = load_gazetteer()
    manifest = []
    for book in lit_books():
        data = build_book(book, gaz)
        with_coord = sum(1 for p in data['places'].values() if p.get('lat') is not None)
        print(f"[{book}] 人物 {len(data['persons'])} · 地点 {len(data['places'])}"
              f"（有坐标 {with_coord}）· 事件 {sum(len(v) for v in data['events'].values())}"
              f"（未 drop）· 回数 {data['chapters']}")
        p = OUT_DIR / f'{book}.json'
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f"-> {p} ({p.stat().st_size // 1024} KB)")
        manifest.append({'slug': book, 'title': book, 'chapters': data['chapters'],
                         'era': data['era'], 'era_conf': data['era_conf']})
    md = json.loads((KB / '作品元数据表.json').read_text(encoding='utf-8'))
    lead_by_book = {w['book']: w.get('leads', []) for w in md['works']}
    for m in manifest:
        m['leads'] = lead_by_book.get(m['title'], [])
    state = {
        'meta': {'generated': today(), 'schema': 'atlas-state-v1',
                 'note': 'leaders（各派当前掌门）待工具 B 门派世系表接入后填充；era 来自作品元数据表'},
        'books': manifest,
    }
    p = OUT_DIR / 'state.json'
    p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"-> {p} ({p.stat().st_size // 1024} KB)")


if __name__ == '__main__':
    main()
