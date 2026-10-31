# -*- coding: utf-8 -*-
"""P1 数据层：kb 产物 → site/data/*.json（站点数据契约 v1）。

站点是 kb 的纯函数：本脚本把四类 kb 产物转换为前端可直接消费的预构建数据，
不触碰 kb/ 原文件。重跑即全量重建；新书点亮后重跑即自动扩展。

输出（site/data/）：
  books.json       作品库索引＋每书卡片（含互文出入边明细）——书页/作品列表
  universe.json    地铁图数据（六线＋接力边＋编年主线＋换乘站种子）——宇宙页
  characters.json  三部曲规范实体索引（跨书归并，含别名/章节跨度）——人物索引/搜索底座

用法：python scripts/build_site_data.py
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / 'kb'
OUT = ROOT / 'site' / 'data'

# 书目与规范名：自动发现 + 跨书归并（见 kb_discovery.py，勿硬编码）
from kb_discovery import lit_books, canon as book_canon, today, ROOT, KB, OUT  # noqa: E402


def dump(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"-> {p}")


def build_books() -> dict:
    with open(KB / '作品元数据表.json', encoding='utf-8') as f:
        wmeta = json.load(f)
    with open(KB / '互文引用表.json', encoding='utf-8') as f:
        inter = json.load(f)

    out_edges = defaultdict(lambda: defaultdict(list))
    in_edges = defaultdict(lambda: defaultdict(list))
    for e in inter['edges']:
        if e['kind'] in ('authorial', 'quoted'):
            out_edges[e['source']][e['target']].append(e)
            in_edges[e['target']][e['source']].append(e)

    def pack(d, book):
        items = []
        for tgt, es in sorted(d.get(book, {}).items(), key=lambda kv: -len(kv[1])):
            items.append({
                'book': tgt,
                'kind': es[0]['kind'],
                'count': len(es),
                'locs': [f"{es[0]['source']}·{e['loc']}" for e in es[:5]],
                'sample': es[0]['snippet'][:60],
            })
        return items

    books = []
    for w in wmeta['works']:
        books.append({**{k: w[k] for k in
                         ('no', 'book', 'year', 'year_conf', 'era', 'era_conf', 'series',
                          'series_conf', 'leads', 'leads_conf', 'chapters', 'chars',
                          'kb_status', 'intertext_out', 'intertext_in')},
                      'out_refs': pack(out_edges, w['book']),
                      'in_refs': pack(in_edges, w['book'])})
    return {
        'meta': {'generated': today(), 'schema': 'site-books-v1',
                 'totals': wmeta['meta']['totals']},
        'missing_works': wmeta['missing_works'],
        'books': books,
    }


def build_universe() -> dict:
    with open(KB / '系列谱系考订表.json', encoding='utf-8') as f:
        tree = json.load(f)
    return {
        'meta': {'generated': today(), 'schema': 'site-universe-v1',
                 'source': 'kb/系列谱系考订表.json'},
        'lines': tree['lines'],
        'chronology_spine': tree['chronology_spine'],
        'interchange_seeds': tree['interchange_seeds'],
        'open_questions': tree['open_questions'],
    }


def build_characters() -> dict:
    per_book = {}
    for book in lit_books():
        with open(KB / book / '实体登记表.json', encoding='utf-8') as f:
            reg = json.load(f)
        per_book[book] = reg['entities']

    merged = {}
    for book, ents in per_book.items():
        for key, e in ents.items():
            canon = (book_canon(e['canonical']) if e['type'] == '@' else e['canonical'])
            ck = (e['type'], canon)
            m = merged.setdefault(ck, {
                'type': e['type'], 'canonical': canon,
                'books': {}, 'total': 0, 'cross_book': False})
            m['total'] += e['count']
            if book in m['books']:
                b = m['books'][book]
                b['count'] += e['count']
                for a, n in e.get('aliases', {}).items():
                    b['aliases'][a] = b['aliases'].get(a, 0) + n
                b['chapters'] = sorted(set(b['chapters']) | set(e.get('chapters', [])))
            else:
                m['books'][book] = {
                    'count': e['count'],
                    'chapters': list(e.get('chapters', [])),
                    'aliases': dict(e.get('aliases', {})),
                }
    items = []
    for (t, c), m in merged.items():
        m['cross_book'] = len(m['books']) > 1
        items.append(m)
    items.sort(key=lambda m: -m['total'])
    dist = defaultdict(int)
    for m in items:
        dist[m['type']] += 1
    return {
        'meta': {'generated': today(), 'schema': 'site-characters-v1',
                 'books': lit_books(),
                 'totals': {'merged_entities': len(items),
                            'cross_book': sum(1 for m in items if m['cross_book']),
                            'by_type': dict(sorted(dist.items()))},
                 'type_legend': {'@': '人物', '=': '地点', '◆': '组织', ';': '职衔称谓',
                                 '%': '时间', '☆': '武功', '•': '兵器宝物', '[': '秘籍文书',
                                 '§': '丹药', '+': '坐骑'}},
        'entities': items,
    }


def build_entity_index() -> dict:
    """轻量实体索引（@/☆/◆），供实体联想岛（EntityExplorer）与各索引页使用。"""
    with open(OUT / 'characters.json', encoding='utf-8') as f:
        chars = json.load(f)
    items = [
        {'t': e['type'], 'c': e['canonical'], 'n': e['total'],
         'b': {b: v['count'] for b, v in e['books'].items()}, 'x': e['cross_book']}
        for e in chars['entities'] if e['type'] in ('@', '☆', '◆')
    ]
    items.sort(key=lambda x: -x['n'])
    return {
        'meta': {'generated': today(), 'schema': 'entity-index-v1',
                 'note': '轻索引：t=类型 c=规范名 n=总频次 b=逐书频次 x=跨书',
                 'totals': {'entities': len(items),
                            'by_type': {t: sum(1 for i in items if i['t'] == t)
                                        for t in ('@', '☆', '◆')}}},
        'entities': items,
    }


def main() -> None:
    dump('books.json', build_books())
    dump('universe.json', build_universe())
    dump('characters.json', build_characters())
    dump('entity-index.json', build_entity_index())


if __name__ == '__main__':
    sys.exit(main())
