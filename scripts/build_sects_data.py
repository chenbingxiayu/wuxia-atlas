# -*- coding: utf-8 -*-
"""M2：门派/组织数据切片 → site/data/sects.json。

从各已点亮书目聚合 ◆ 实体：
  - 武功册（镇山/拥有/独门 关系，带证据与考订注记）
  - 成员册（dossiers 的门派线索：strong/ok 级自动入册，weak 仅 strong 门派显示）
  - 事件参与数（含围战/军阵类 ◆ 主体）
书目自动发现；新书面作后重跑即并入。

用法：python scripts/build_sects_data.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import lit_books, canon, today, dump_json, KB  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / 'site' / 'data'


def main() -> None:
    books = lit_books()
    sects = defaultdict(lambda: {'books': {}, 'ev_total': 0})
    # 招式级武功集合（工具 A 招式表）——门派武功册只列功法级
    moves = set()
    mf = KB / '招式表.json'
    if mf.exists():
        for m in json.loads(mf.read_text(encoding='utf-8')).get('moves', []):
            if m.get('level') == '招式':
                moves.add(m['canonical'])
    # 门派世系表（工具 B）——每掌门在位期 + 门下成员
    lineages = {}
    lf = KB / '门派世系表.json'
    if lf.exists():
        for sec in json.loads(lf.read_text(encoding='utf-8')).get('sects', []):
            lineages[sec['sect']] = sec

    for book in books:
        with open(KB / book / '关系表.json', encoding='utf-8') as f:
            rel = json.load(f)
        for r in rel['relations']:
            if r['subject_type'] != '◆':
                continue
            s = canon(r['subject'])
            sec = sects[s]
            sec['ev_total'] += 0  # 事件数在事件表阶段累计
            b = sec['books'].setdefault(book, {'arts': []})
            b['arts'].append({
                'art': r['object'], 'pred': r['predicate'],
                'level': '招式' if r['object'] in moves else '功法',
                'locs': r['evidence_locators'][:4], 'ev': r.get('evidence_count', 1),
                'note': r.get('note', ''),
            })

        with open(KB / book / '事件表.json', encoding='utf-8') as f:
            ev = json.load(f)
        for e in ev['events']:
            if e.get('dropped'):
                continue
            for side in ('subject', 'object'):
                v = e.get(side)
                if v and v in sects:
                    sects[v]['ev_total'] += 1

    # 成员册：dossiers 的门派线索（derived）
    members = defaultdict(list)
    try:
        with open(OUT / 'dossiers.json', encoding='utf-8') as f:
            dossiers = json.load(f)['dossiers']
        for d in dossiers:
            for a in d.get('sect_affinity', []):
                if a['tier'] in ('strong', 'ok'):
                    members[canon(a['sect'])].append({
                        'name': d['canonical'], 'tier': a['tier'],
                        'via': a['via_arts'][:4],
                    })
    except FileNotFoundError:
        print('! dossiers.json 不存在——请先运行 build_dossiers.py（成员册将缺失）')

    items = []
    for name, s in sects.items():
        arts_all = defaultdict(list)
        for book, b in s['books'].items():
            for a in b['arts']:
                arts_all[a['pred']].append({**a, 'book': book})
        items.append({
            'canonical': name,
            'books': sorted(s['books']),
            'cross_book': len(s['books']) > 1,
            'ev_total': s['ev_total'],
            'arts_by_pred': {k: v for k, v in sorted(arts_all.items())},
            'members': sorted(members.get(name, []), key=lambda m: -len(m['via'])),
            'tenures': (lineages.get(name) or {}).get('tenures', []),
            'lineage_gaps': (lineages.get(name) or {}).get('gaps', []),
            'lineage_todo': (lineages.get(name) or {}).get('open_questions', []),
        })
    items.sort(key=lambda x: (-x['ev_total'], x['canonical']))

    payload = {
        'meta': {
            'generated': today(), 'schema': 'sects-v1',
            'books': books,
            'totals': {'sects': len(items), 'cross_book': sum(1 for i in items if i['cross_book'])},
            'note': '成员册来自人物档案的门派线索（derived，strong/ok 级）；恩怨对头待 M4 与侠谱评分一同上线',
        },
        'sects': items,
    }
    dump_json('sects.json', payload)


if __name__ == '__main__':
    sys.exit(main())
