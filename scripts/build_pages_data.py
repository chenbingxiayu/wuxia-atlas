# -*- coding: utf-8 -*-
"""M1：页面级数据切片 → site/data/chapters.json。

供书页/回目页消费：
  - 全 34 部逐回回目（取自章回版文件名；回目为短句元数据，随书页发布）
  - 已点亮三部曲：逐章叙事事件流（A—动词—B，含定位符）、逐章动词密度（节奏指纹）、
    逐章出场人物（登记表定位符聚合计数，Top 30）
  - KB 统计（实体/叙事事件/关系）

版权档位：事件流与计数为 L0 图谱事实（不含摘录）；回目为短句元数据。

用法：python scripts/build_pages_data.py
"""
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZH = ROOT / '章回版'
KB = ROOT / 'kb'
OUT = ROOT / 'site' / 'data'

LIT = ['白发魔女传', '塞外奇侠传', '七剑下天山']
VERB_CODES = ['◈', '◉', '▲', '◇', '○']


def chapter_meta(book: str) -> list:
    """回目元数据（全部书目）：[{no, title}]"""
    out = []
    for fp in sorted((ZH / book).glob('*.txt')):
        parts = fp.stem.split('　')
        out.append({'no': int(fp.name[:3]), 'title': '　'.join(parts[1:])})
    return out


def lit_book_data(book: str, chapter_nos: list):
    """已点亮书目：逐章事件/动词密度/出场人物 + KB 统计"""
    with open(KB / book / '事件表.json', encoding='utf-8') as f:
        ev = json.load(f)
    with open(KB / book / '实体登记表.json', encoding='utf-8') as f:
        reg = json.load(f)
    with open(KB / book / '关系表.json', encoding='utf-8') as f:
        rel = json.load(f)

    stream = defaultdict(list)      # no -> [{s,v,o,loc}]
    verbs = defaultdict(Counter)    # no -> {verb_code: n}
    for e in ev['events']:
        if e.get('dropped'):
            continue
        no = int(e['loc'].split(':')[0].lstrip('0') or 0)
        verbs[no][e['verb_code']] += 1
        if not e.get('in_quote') and e.get('subject') and e.get('object'):
            stream[no].append({'s': e['subject'], 'v': e['verb'], 'o': e['object'],
                               'loc': e['loc'], 'c': e.get('confidence', '')})

    chars = defaultdict(Counter)    # no -> {canonical: n}
    for key, ent in reg['entities'].items():
        if ent['type'] != '@':
            continue
        for loc in ent.get('locators', []):
            no = int(loc.split(':')[0].lstrip('0') or 0)
            chars[no][ent['canonical']] += 1

    chapters = []
    for no in chapter_nos:
        top = chars.get(no, {})
        chapters.append({
            'no': no,
            'title': next((c['title'] for c in chapter_meta(book) if c['no'] == no), f'第{no}回'),
            'events': len(stream.get(no, [])),
            'verbs': {v: verbs.get(no, {}).get(v, 0) for v in VERB_CODES},
            'chars': [{'name': n, 'n': c} for n, c in top.most_common(30)],
            'stream': stream.get(no, []),
        })

    kb_stats = {
        'entities': len(reg['entities']),
        'events_narrative': ev['meta'].get('events_narrative'),
        'events_total': ev['meta'].get('events_total'),
        'relations': len(rel['relations']),
    }
    return chapters, kb_stats


def main() -> None:
    payload = {}
    for d in sorted(p for p in ZH.iterdir() if p.is_dir()):
        book = d.name
        meta = chapter_meta(book)
        entry = {'chapters': meta, 'lit': False}
        if book in LIT:
            nos = [c['no'] for c in meta]
            chapters, kb_stats = lit_book_data(book, nos)
            entry.update({'chapters': chapters, 'lit': True, 'kb': kb_stats})
        payload[book] = entry

    out = {
        'meta': {'generated': str(date.today()), 'schema': 'chapters-v1',
                 'lit_books': LIT,
                 'note': '回目取自章回版文件名（短句元数据）；事件流为 L0 图谱事实，不含摘录'},
    }
    out.update(payload)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / 'chapters.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    lit_info = {b: {'chapters': len(payload[b]['chapters']),
                    'stream_events': sum(len(c['stream']) for c in payload[b]['chapters']),
                    **payload[b].get('kb', {})} for b in LIT}
    print(json.dumps(lit_info, ensure_ascii=False, indent=1))
    print(f"-> {OUT / 'chapters.json'} ({(OUT / 'chapters.json').stat().st_size // 1024} KB)")


if __name__ == '__main__':
    sys.exit(main())
