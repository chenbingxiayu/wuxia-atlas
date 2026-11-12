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
import csv
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
        b = {**{k: w[k] for k in
                ('no', 'book', 'year', 'year_conf', 'era', 'era_conf', 'series',
                 'series_conf', 'leads', 'leads_conf', 'chapters', 'chars',
                 'kb_status', 'intertext_out', 'intertext_in')},
             'out_refs': pack(out_edges, w['book']),
             'in_refs': pack(in_edges, w['book'])}
        # 宇宙页重构 C：简介消费链——build_work_metadata 仅对 approved 行写入 hook/summary，
        # 此处条件透传（缺省不加字段，schema 只增不改）
        for k in ('hook', 'summary'):
            if w.get(k):
                b[k] = w[k]
        books.append(b)
    return {
        'meta': {'generated': today(), 'schema': 'site-books-v1',
                 'totals': wmeta['meta']['totals']},
        'missing_works': wmeta['missing_works'],
        'books': books,
    }


def load_reading_guides() -> list:
    """宇宙页重构 D（宇宙 §4.2）：kb/校订/线路导读.tsv（列 line/start/peak/skip/note/status）
    → 仅 status=approved 行；TSV 不存在返回空表（0 approved → 不注入任何 reading_guide）。"""
    p = KB / '校订' / '线路导读.tsv'
    if not p.exists():
        return []
    rows = []
    with open(p, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            if (r.get('status') or '').strip() != 'approved':
                continue
            g = {k: (r.get(k) or '').strip() for k in ('line', 'start', 'peak', 'skip', 'note')}
            if any(g[k] for k in ('start', 'peak', 'skip', 'note')):
                rows.append(g)
    return rows


def build_universe() -> dict:
    with open(KB / '系列谱系考订表.json', encoding='utf-8') as f:
        tree = json.load(f)
    # spec 011 T21（宇宙 §4.3）：种子规范名映射——对照 dossiers（规范名 + 别名表），
    # 复合名「展示名（规范名）」先试全名再试括号内名；失败者不加 canonical（页面降级纯文本）
    seeds = tree['interchange_seeds']
    canon_set: set = set()
    alias_to_canon: dict = {}
    try:
        with open(OUT / 'dossiers.json', encoding='utf-8') as f:
            ds = json.load(f)
        for d in ds.get('dossiers', []):
            c = d.get('canonical')
            if c:
                canon_set.add(c)
            for al in d.get('aliases', []):
                nm = al.get('alias') if isinstance(al, dict) else al
                if nm and nm not in alias_to_canon:
                    alias_to_canon[nm] = c
    except FileNotFoundError:
        pass
    unresolved = []
    for s in seeds:
        name = s.get('name', '')
        cand = [name]
        if '（' in name:
            cand.append(name.split('（')[-1].rstrip('）'))
        resolved = None
        for c in cand:
            if c in canon_set:
                resolved = c
                break
            if c in alias_to_canon and alias_to_canon[c]:
                resolved = alias_to_canon[c]
                break
        if resolved:
            s['canonical'] = resolved
        else:
            unresolved.append(name)
    if unresolved:
        print('-> 种子 canonical 映射失败（降级纯文本）:', '、'.join(unresolved))
    # 宇宙页重构 D（宇宙 §4.2）：线路导读——仅 approved 行按 line 名包含式匹配注入
    # reading_guide（切片层注入，012 tasks 已备注口径）；无 approved → 不注入，页面整块隐藏
    n_guide = 0
    for g in load_reading_guides():
        hit = None
        for ln in tree['lines']:
            tsv_line, tree_line = g['line'], ln.get('line', '')
            if tsv_line and tree_line and (tsv_line in tree_line or tree_line in tsv_line):
                hit = ln
                print(f"-> 线路导读匹配: 「{tsv_line}」 ↔ 「{tree_line}」")
                break
        if hit is None:
            print(f"-> 线路导读未匹配线名: 「{g['line']}」（跳过）")
            continue
        hit['reading_guide'] = {k: g[k] for k in ('start', 'peak', 'skip', 'note')}
        n_guide += 1
    print(f"导读接入 {n_guide} 线（approved）")
    return {
        'meta': {'generated': today(), 'schema': 'site-universe-v1',
                 'source': 'kb/系列谱系考订表.json'},
        'lines': tree['lines'],
        'chronology_spine': tree['chronology_spine'],
        'interchange_seeds': seeds,
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
    # spec 011 T21（需求 B6）：dossiers 别名词频并入轻索引（a 字段）——搜索可命中别名
    alias_of: dict = {}
    try:
        with open(OUT / 'dossiers.json', encoding='utf-8') as f:
            ds = json.load(f)
        for d in ds.get('dossiers', []):
            m: dict = {}
            for al in d.get('aliases', []):
                name = al.get('alias') if isinstance(al, dict) else al
                cnt = al.get('count', 0) if isinstance(al, dict) else 0
                if name and name != d.get('canonical'):
                    m[name] = m.get(name, 0) + cnt
            if m and d.get('canonical'):
                alias_of[d['canonical']] = m
    except FileNotFoundError:
        print('-> dossiers.json 不存在，entity-index 本轮不含别名（a 字段）')
    items = []
    for e in chars['entities']:
        if e['type'] not in ('@', '☆', '◆'):
            continue
        it = {'t': e['type'], 'c': e['canonical'], 'n': e['total'],
              'b': {b: v['count'] for b, v in e['books'].items()}, 'x': e['cross_book']}
        if e['canonical'] in alias_of:
            it['a'] = alias_of[e['canonical']]
        items.append(it)
    items.sort(key=lambda x: -x['n'])
    n_alias = sum(1 for i in items if 'a' in i)
    return {
        'meta': {'generated': today(), 'schema': 'entity-index-v2',
                 'note': '轻索引：t=类型 c=规范名 n=总频次 b=逐书频次 x=跨书 a=别名词频（dossiers 并入，spec 011 T21）',
                 'totals': {'entities': len(items), 'with_aliases': n_alias,
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
