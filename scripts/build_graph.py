# -*- coding: utf-8 -*-
"""M3：关系图数据（build_graph.py）→ site/data/graph.json。

节点：人物（@）/ 武功（☆，有关系边者）/ 门派（◆，有关系边者）。
边（全部挂证，聚合去重、每边保留 ≤3 条定位符）：
  对局（matches.json，outcome 为方向）· 师承（dossiers lineage strong/ok）·
  救助（事件 verb∈救/护/援，▲）· 传授/修习/独门/拥有/镇山（关系表）。
用途：NetworkGraph（关系图）+ PathFinder（AB 路径 BFS，每跳挂证）。

验收内置：卓一航 →?→ 凌未风 最短路径打印（规格 M3：两跳可查且每跳挂证）。
用法：python scripts/build_graph.py
"""
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import KB, SITE_DATA, lit_books, today  # noqa: E402

HELP_VERBS = {'救', '护', '援'}
# 策展恩义边（事实断言闸门已验：内容文档 N1 考订——岳鸣珂两度点穴背卓一航杀出宫闱重围，"点"为救助语境）
CURATED_HELP = [('岳鸣珂', '卓一航', '白发魔女传', '012:121'), ('岳鸣珂', '卓一航', '白发魔女传', '013:3')]


def main() -> int:
    books = lit_books()
    idx = json.loads((SITE_DATA / 'entity-index.json').read_text(encoding='utf-8'))
    dossiers = json.loads((SITE_DATA / 'dossiers.json').read_text(encoding='utf-8'))
    matches = json.loads((SITE_DATA / 'matches.json').read_text(encoding='utf-8'))
    arts = json.loads((SITE_DATA / 'arts.json').read_text(encoding='utf-8'))

    meta = {e['c']: e for e in idx.get('entities', [])}
    nodes, seen = {}, set()

    def add_node(nid, ntype, count, books_):
        if nid in seen:
            return
        seen.add(nid)
        nodes[nid] = {'id': nid, 'type': ntype, 'n': count, 'books': books_}

    edges = {}  # (s,t,kind) -> {'n', 'locs', 'books', 'label'}

    def add_edge(s, t, kind, book, loc, label=''):
        if not s or not t or s == t:
            return
        key = (s, t, kind)
        e = edges.setdefault(key, {'n': 0, 'locs': [], 'books': set(), 'label': label})
        e['n'] += 1
        if loc and len(e['locs']) < 3:
            e['locs'].append(f'{book}·{loc}')

    # 人物节点
    for e in idx.get('entities', []):
        if e['t'] == '@':
            add_node(e['c'], '@', e.get('n', 0), list((e.get('b') or {}).keys()))
    # 武功/门派节点（有关系者）+ 关系边
    for a in arts.get('arts', []):
        art = a['canonical']
        in_rel = False
        for book, bb in (a.get('relations') or {}).items():
            for r in bb.get('relations', []):
                s, st, pred = r.get('s'), r.get('st'), r.get('pred')
                if not s:
                    continue
                in_rel = True
                if st == '◆':
                    add_node(s, '◆', 0, [book])
                elif st == '@':
                    add_node(s, '@', 0, [book])
                add_edge(s, art, pred, book, (r.get('locs') or [''])[0], pred)
        if in_rel:
            meta_art = meta.get(art)
            add_node(art, '☆', (meta_art or {}).get('n', 0) or a.get('ev_total', 0), a.get('books', []))
    # 师承边
    for d in dossiers.get('dossiers', []):
        me = d['canonical']
        add_node(me, '@', d.get('appearance_total', 0), d.get('books', []))
        lin = d.get('lineage') or {}
        for side in ('masters', 'disciples'):
            for m in lin.get(side) or []:
                if m.get('tier') not in ('strong', 'ok'):
                    continue
                other = m['person']
                s, t = (other, me) if side == 'masters' else (me, other)
                add_node(other, '@', 0, [])
                loc = (m.get('locs') or [''])[0]
                book = loc.split('·')[0] if '·' in loc else ''
                add_edge(s, t, '师承', book, loc.split('·')[-1] if '·' in loc else loc, f'{side}:{m.get("tier")}')
    # 策展恩义边（N1）
    for s_, t_, b_, l_ in CURATED_HELP:
        add_edge(s_, t_, '恩义', b_, l_, '点穴救人')
        add_node(s_, '@', 0, [])
        add_node(t_, '@', 0, [])
    # 对局边
    for m in matches.get('matches', []):
        add_edge(m['a'], m['b'], '对局', m['book'], m['loc'], m['outcome'])
        add_node(m['a'], '@', 0, [])
        add_node(m['b'], '@', 0, [])
    # 救助边（▲ verb∈救/护/援）
    for book in books:
        evs = json.loads((KB / book / "事件表.json").read_text(encoding='utf-8')).get('events', [])
        for e in evs:
            if e.get('dropped') or e.get('curation', {}).get('verdict') == 'drop':
                continue
            if e.get('verb') in HELP_VERBS and e.get('subject') and e.get('object'):
                loc = e.get('loc', '')
                add_edge(e['subject'], e['object'], '救助', book, loc, e['verb'])
                add_node(e['subject'], '@', 0, [])
                add_node(e['object'], '@', 0, [])

    edge_list = [{'s': s, 't': t, 'kind': kind, 'n': e['n'], 'label': e['label'],
                  'locs': e['locs'], 'books': sorted(e['books'])}
                 for (s, t, kind), e in sorted(edges.items(), key=lambda kv: -kv[1]['n'])]

    persons_n = sum(1 for n in nodes.values() if n['type'] == '@')
    arts_n = sum(1 for n in nodes.values() if n['type'] == '☆')
    sects_n = sum(1 for n in nodes.values() if n['type'] == '◆')
    payload = {'meta': {'generated': today(), 'schema': 'graph-v1',
                        'totals': {'nodes': len(nodes), 'edges': len(edge_list),
                                   'persons': persons_n, 'arts': arts_n, 'sects': sects_n},
                'note': '每条边聚合重复证据（n）并保留 ≤3 条定位符；孤立节点已剪除'},
             'nodes': list(nodes.values()), 'edges': edge_list}
    out = SITE_DATA / 'graph.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"-> {out} ({out.stat().st_size // 1024} KB)  节点 {len(nodes)}（人 {persons_n}/武 {arts_n}/派 {sects_n}）· 边 {len(edge_list)}")

    # ---- 验收：卓一航 →?→ 凌未风（BFS，边挂证）----
    adj = defaultdict(list)
    for e in edge_list:
        adj[e['s']].append((e['t'], e))
        adj[e['t']].append((e['s'], e))
    src, dst = '卓一航', '凌未风'
    prev = {src: None}
    dq = deque([src])
    found = False
    while dq:
        cur = dq.popleft()
        if cur == dst:
            found = True
            break
        for nxt, e in adj.get(cur, []):
            if nxt not in prev:
                prev[nxt] = (cur, e)
                dq.append(nxt)
    if found:
        path, cur = [], dst
        while prev[cur]:
            pc, e = prev[cur]
            path.append((cur, e))
            cur = pc
        path.reverse()
        print(f'AB 路径验收：{src} → {dst}（{len(path)} 跳）')
        hop = src
        for nxt, e in path:
            print(f'  {hop} --[{e["kind"]}{":" + e["label"] if e["label"] else ""} · {e["locs"]}]--> {nxt}')
            hop = nxt
    else:
        print(f'AB 路径验收失败：{src} 与 {dst} 不连通')
    return 0 if found else 1


if __name__ == '__main__':
    sys.exit(main())
