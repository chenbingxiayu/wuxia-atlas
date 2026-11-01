# -*- coding: utf-8 -*-
"""M2：武功数据切片 → site/data/arts.json。

从各已点亮书目的 关系表.json 聚合 ☆ 武功：
  - 跨书按规范名归并（kb_discovery.canon）
  - 归属（门派 镇山/拥有/独门）与修习/传授者（人物）
  - 别名（关系表 art_aliases）
  - 品类自动分类（名称后缀规则，'其他' 兜底）
书目自动发现；新书面作后重跑即并入。

用法：python scripts/build_arts_data.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import lit_books, canon, today, dump_json, KB  # noqa: E402


def load_json_local(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

# 品类分类：按后缀，长词优先
CATEGORY_RULES = [
    ('一百零八式', '剑法'), ('连环夺命剑', '剑法'),
    ('阵法', '阵法'), ('剑阵', '阵法'),
    ('剑法', '剑法'), ('剑术', '剑法'), ('剑', '剑法'),
    ('掌法', '掌法'), ('掌力', '掌法'), ('掌', '掌法'),
    ('拳法', '拳法'), ('拳', '拳法'),
    ('腿法', '腿法'), ('腿', '腿法'),
    ('轻功', '轻功'), ('身法', '身法'), ('步法', '身法'),
    ('内功', '内功'), ('心法', '内功'), ('神功', '内功'), ('真气', '内功'),
    ('暗器', '暗器'), ('手法', '暗器'), ('针法', '暗器'),
    ('刀法', '刀法'), ('刀', '刀法'),
    ('枪法', '枪法'), ('棍法', '棍法'), ('杖法', '杖法'), ('鞭法', '鞭法'),
    ('指法', '指法'), ('点穴', '点穴'), ('抓手', '擒拿'), ('擒拿', '擒拿'),
    ('爪', '爪法'), ('功', '内功'), ('式', '招式'),
]


def category(name: str) -> str:
    for suf, cat in CATEGORY_RULES:
        if name.endswith(suf):
            return cat
    return '其他'


def main() -> None:
    books = lit_books()
    arts = defaultdict(lambda: {'books': {}, 'aliases': set(), 'ev_total': 0})
    for book in books:
        with open(KB / book / '关系表.json', encoding='utf-8') as f:
            rel = json.load(f)
        alias_of = {}
        for canon_art, variants in rel.get('art_aliases', {}).items():
            for v in variants:
                alias_of[v] = canon_art
            arts[canon_art]['aliases'].update(variants)
        for r in rel['relations']:
            if r['object_type'] != '☆':
                continue
            art = canon(r['object'])
            a = arts[art]
            a['ev_total'] += r.get('evidence_count', 1)
            b = a['books'].setdefault(book, {'relations': []})
            b['relations'].append({
                's': r['subject'], 'st': r['subject_type'], 'pred': r['predicate'],
                'locs': r['evidence_locators'][:4], 'ev': r.get('evidence_count', 1),
                'note': r.get('note', ''),
            })
        # 别名指向的规范名若未直接出现在 relations 中（纯别名组）也保留
        for canon_art, variants in rel.get('art_aliases', {}).items():
            arts.setdefault(canon_art, {'books': {}, 'aliases': set(), 'ev_total': 0})
            arts[canon_art]['aliases'].update(variants)

    items = []
    for art, a in arts.items():
        items.append({
            'canonical': art,
            'category': category(art),
            'aliases': sorted(a['aliases']),
            'ev_total': a['ev_total'],
            'books': sorted(a['books']),
            'cross_book': len(a['books']) > 1,
            'relations': a['books'],
        })
    items.sort(key=lambda x: (-x['ev_total'], x['canonical']))

    # arts v2：挂招式 children（来自招式表，仅 strong/ok 且未 rejected）
    mp = KB / '招式表.json'
    if mp.exists():
        moves = load_json_local(mp).get('moves', [])
        kids = defaultdict(list)
        for m in moves:
            if m.get('conf') in ('strong', 'ok') and m.get('status') != 'rejected'                     and m.get('parent_art') not in (None, '待考'):
                kids[m['parent_art']].append({'name': m['canonical'], 'conf': m['conf'], 'sect': m.get('sect')})
        for it in items:
            ch = kids.get(it['canonical'])
            if ch:
                it['children'] = ch

    by_cat = defaultdict(int)
    for it in items:
        by_cat[it['category']] += 1
    payload = {
        'meta': {
            'generated': today(), 'schema': 'arts-v1',
            'books': books,
            'totals': {'arts': len(items), 'cross_book': sum(1 for i in items if i['cross_book']),
                       'by_category': dict(sorted(by_cat.items(), key=lambda kv: -kv[1]))},
        },
        'arts': items,
    }
    dump_json('arts.json', payload)


if __name__ == '__main__':
    sys.exit(main())
