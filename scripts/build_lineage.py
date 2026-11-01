# -*- coding: utf-8 -*-
"""考订工具 B：门派世系与成员收集器（v2 · 纯解析结果 · 可增量扩展）。

只消费解析结果：事件表（○ 立指定继任）＋ tagged 标注语料（掌门明文句式）＋
互文引用表（承继提示）＋ dossiers（成员与活跃回目）＋ 系列谱系考订表（编年排序）。
产出 kb/门派世系表.json：每派 tenure 链（掌门/时期/证据/置信）+ 分组成员册。

稳定键：世系裁定=(派, 掌门)；成员归组裁定=(派, 成员)。TSV 跨版本存活，重跑产出 delta。

用法：python scripts/build_lineage.py
"""
import json
import re
import sys
from bisect import bisect_right
from collections import defaultdict, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import lit_books, today, KB  # noqa: E402
from build_moves import load_json, read_tagged  # noqa: E402  # 复用 tagged 读取

OUT = Path(__file__).resolve().parents[1] / 'site' / 'data'

SUCCESSION_VERBS = {'立', '指定', '拥立', '公推', '传位', '让位', '继任', '接任'}
# tagged 明文句式（规范名归一文本上）
LEADER_PATS = [
    re.compile(r'掌门之?[位]?(?:传给|交给|落于|由)([\u4e00-\u9fa5·]{2,8})'),
    re.compile(r'([\u4e00-\u9fa5·]{2,8})(?:接任|继任|出任|接掌|执掌|接位|继位|嗣位)(?:了)?[^。]{0,4}掌门'),
    re.compile(r'(?:立|指定|拥立|公推|推)([\u4e00-\u9fa5·]{2,8})(?:为|接任|继任)?[^。]{0,4}掌门'),
    re.compile(r'新任[^。]{0,4}掌门(?:[^。]{0,6}为)?([\u4e00-\u9fa5·]{2,8})'),
    re.compile(r'掌门([\u4e00-\u9fa5·]{2,8})'),   # 在位称谓：掌门紫阳道长（噪声靠人名词典过滤）
]
LEADER_BLACKLIST = {'人之', '弟子', '之位', '大人', '师兄', '师弟', '师尊', '令狐', '一位', '继承'}


def book_order_map() -> dict:
    """书 → 故事序键 (spine_idx, book_pos)；不在谱系的书用大数兜底"""
    with open(KB / '系列谱系考订表.json', encoding='utf-8') as f:
        tree = json.load(f)
    order = {}
    for si, sp in enumerate(tree['chronology_spine']):
        for bi, b in enumerate(sp['books']):
            order[b.replace('*', '')] = (si, bi)
    return order


def main() -> int:
    books = lit_books()
    print(f'输入书目（lit_books）：{books}')

    # ---- 人名/门派词典 ----
    person_alias = {}
    sect_canons = set()
    for book in books:
        reg = load_json(KB / book / '实体登记表.json')
        for key, e in reg['entities'].items():
            if e['type'] == '@':
                person_alias[e['canonical']] = e['canonical']
                for a in e.get('aliases', {}):
                    person_alias.setdefault(a, e['canonical'])
            elif e['type'] == '◆':
                sect_canons.add(e['canonical'])
    person_alias = {k: v for k, v in person_alias.items()}

    # ---- 成员与活跃回目（dossiers）----
    dpath = OUT / 'dossiers.json'
    if not dpath.exists():
        print('! 缺 site/data/dossiers.json —— 请先运行 build_dossiers.py')
        return 2
    dossiers = load_json(dpath)['dossiers']
    members = defaultdict(list)          # sect -> [{name, tier, curves}]
    member_sect = defaultdict(set)       # 人 -> {sect}
    for d in dossiers:
        for a in d.get('sect_affinity', []):
            if a['tier'] in ('strong', 'ok'):
                members[a['sect']].append({'name': d['canonical'], 'tier': a['tier'],
                                           'curves': d.get('chapter_curves', {})})
                member_sect[d['canonical']].add(a['sect'])

    # ---- 候选收集 ----
    cands = defaultdict(lambda: {'evidence': [], 'kinds': set()})   # (sect, leader) -> ...
    unresolved = []

    def add_candidate(sect, leader_raw, book, loc, kind):
        leader = person_alias.get(leader_raw)
        if not sect:
            s = member_sect.get(leader, set())
            sect = sorted(s)[0] if s else None
        if not leader:
            unresolved.append({'sect': sect, 'name': leader_raw, 'book': book, 'loc': loc, 'kind': kind})
            return
        if not sect:
            unresolved.append({'sect': None, 'name': leader, 'book': book, 'loc': loc, 'kind': kind})
            return
        c = cands[(sect, leader)]
        c['evidence'].append({'book': book, 'loc': loc, 'kind': kind})
        c['kinds'].add(kind)

    def sect_of_line(line_sects, window_sects):
        for s in list(line_sects) + list(window_sects):
            if s in sect_canons:
                return s
        return None

    # 1) tagged 明文路
    for book in books:
        wbuf = defaultdict(dict)
        rows = list(read_tagged(book))
        for chap, lineno, raw, norm, persons, sects, _a in rows:
            wbuf[chap][lineno] = norm
        for chap, lineno, raw, norm, persons, sects, _a in rows:
            if '掌门' not in norm:
                continue
            w = ''.join(wbuf[chap].get(l, '') for l in (lineno - 1, lineno, lineno + 1))
            sect = sect_of_line(sects, set())
            for pat in LEADER_PATS:
                for m in pat.finditer(norm):
                    name = m.group(1)
                    if name in LEADER_BLACKLIST or len(name) < 2:
                        continue
                    kind = '明文在位' if pat.pattern.startswith('掌门(') else '明文继任'
                    add_candidate(sect, name, book, f'{chap}:{lineno}', kind)

    # 2) 事件路
    for book in books:
        ev = load_json(KB / book / '事件表.json')
        tagged_idx = defaultdict(str)
        for chap, lineno, raw, norm, _p, _s, _a in read_tagged(book):
            tagged_idx[f'{chap}:{lineno}'] = norm
        for e in ev['events']:
            if e.get('dropped') or e.get('verb_code') != '○' or e.get('verb') not in SUCCESSION_VERBS:
                continue
            leader = e.get('object') if e.get('verb') in ('立', '指定', '拥立', '公推', '继任', '接任') \
                else (e.get('object') or e.get('subject'))
            if not leader:
                continue
            line = tagged_idx.get(e['loc'], '')
            kind = '事件(明文同线)' if '掌门' in line else '事件'
            add_candidate(None, leader, book, e['loc'], kind)

    # 3) 互文路
    ipath = KB / '互文引用表.json'
    if ipath.exists():
        inter = load_json(ipath)
        for e in inter['edges']:
            if '掌门' in e.get('snippet', '') and re.search(r'继|接|传|立|让', e.get('snippet', '')):
                m = re.search(r'(?:掌门[^。]{0,4})?([\u4e00-\u9fa5·]{2,8})(?:接任|继任|出任)', e['snippet'])
                if m:
                    add_candidate(None, m.group(1), e['source'], e['loc'], '互文')

    border = book_order_map()
    gkey = lambda b, loc: (border.get(b, (99, 99)), int(loc.split(':')[0]), int(loc.split(':')[1]))

    # ---- 世系构建 ----
    sects_out = []
    sect_names = sorted({s for s, _ in cands} | set(members))
    for sect in sect_names:
        cands_s = [(k[1], v) for k, v in cands.items() if k[0] == sect]
        tenures = []
        if cands_s:
            cands_s.sort(key=lambda x: gkey(x[0], sorted(x[1]['evidence'], key=lambda e: gkey(e['book'], e['loc']))[0]['loc']))
            # 合并同掌门连续候选
            merged = []
            for leader, v in cands_s:
                if merged and merged[-1][0] == leader:
                    merged[-1][1]['evidence'].extend(v['evidence'])
                    merged[-1][1]['kinds'] |= v['kinds']
                else:
                    merged.append([leader, {'evidence': list(v['evidence']), 'kinds': set(v['kinds'])}])
            for i, (leader, v) in enumerate(merged):
                evs = sorted(v['evidence'], key=lambda e: gkey(e['book'], e['loc']))
                start = evs[0]
                conf = 'strong' if {'事件(明文同线)', '明文继任'} & v['kinds'] else ('ok' if v['kinds'] else 'weak')
                tenures.append({'leader': leader, 'start': start, 'evidence': evs, 'conf': conf,
                                'role_next': merged[i + 1][0] if i + 1 < len(merged) else None})
        # 成员归组
        bounds = [(gkey(t['start']['book'], t['start']['loc']), t['leader']) for t in tenures]
        bounds.sort()
        keys = [b[0] for b in bounds]
        cohort = defaultdict(list)
        for m in members.get(sect, []):
            assigned = None
            for b, curve in m['curves'].items():
                bk = border.get(b, (99, 99))
                for chap in curve:
                    pt = (bk, int(chap))
                    i = bisect_right(keys, pt)
                    if i > 0:
                        assigned = bounds[i - 1][1]
            cohort[assigned].append(m)
        # 期序与成员挂接
        tenure_out = []
        for i, t in enumerate(tenures):
            ms = []
            for m in cohort.get(t['leader'], []):
                role = '掌门' if m['name'] == t['leader'] else '成员'
                ms.append({'name': m['name'], 'role': role, 'tier': m['tier']})
            for m in cohort.get(None, []) + [mm for k, lst in cohort.items() if k is not None for mm in []]:
                pass
            tenure_out.append({
                'leader': t['leader'], 'conf': t['conf'],
                'period': {'from': f"{t['start']['book']}·{t['start']['loc']}",
                           'to': (f"{tenures[i+1]['start']['book']}·{tenures[i+1]['start']['loc']}"
                                  if i + 1 < len(tenures) else '≥最后出现')},
                'evidence': [{'book': e['book'], 'loc': e['loc'], 'kind': e['kind']} for e in t['evidence'][:6]],
                'members': sorted(ms, key=lambda x: 0 if x['tier'] == 'strong' else 1),
                'successor': t['role_next'],
            })
        # 前史缺口（首个继任证据之前的在位者不可知时，以继任证据自证前代存在）
        gaps = []
        if tenures:
            gaps.append({'before': tenures[0]['leader'],
                         'note': f"首条继任证据（{tenures[0]['evidence'][0]['book']}·{tenures[0]['evidence'][0]['loc']}）"
                                 f"证明此前有在位掌门，未解析出姓名"})
        # 未归组（无 tenure 可落的成员）
        ungrouped = cohort.get(None, [])
        if ungrouped and not tenures:
            ms = [{'name': m['name'], 'role': '待归组', 'tier': m['tier']} for m in ungrouped]
            tenure_out.append({'leader': None, 'conf': 'weak',
                               'period': {'from': '—', 'to': '—'}, 'evidence': [],
                               'members': sorted(ms, key=lambda x: 0 if x['tier'] == 'strong' else 1),
                               'successor': None})
        sects_out.append({
            'sect': sect,
            'tenures': tenure_out,
            'gaps': gaps,
            'ungrouped': [m['name'] for m in ungrouped],
            'open_questions': [u for u in unresolved if u['sect'] == sect][:6],
        })

    # ---- delta ----
    out_json = KB / '门派世系表.json'
    prev = load_json(out_json) if out_json.exists() else None
    delta = {'new_tenures': [], 'members_regrouped': 0, 'new_sects': []}
    if prev:
        prev_sects = {s['sect']: s for s in prev.get('sects', [])}
        for s in sects_out:
            if s['sect'] not in prev_sects:
                delta['new_sects'].append(s['sect'])
                continue
            ps = prev_sects[s['sect']]
            pl = [t['leader'] for t in ps.get('tenures', [])]
            for t in s['tenures']:
                if t['leader'] not in pl:
                    delta['new_tenures'].append(f"{s['sect']}·{t['leader']}")
    rev = (prev or {}).get('meta', {}).get('rev', 0) + 1
    payload = {
        'meta': {'generated': today(), 'rev': rev, 'schema': 'lineage-v1',
                 'based_on': {'books': books, 'kb_date': today()},
                 'conf_legend': 'strong=明文继任/事件明文同线 ok=事件或互文 weak=称谓推断',
                 'totals': {'sects': len(sects_out),
                            'tenures': sum(len(s['tenures']) for s in sects_out)}},
        'sects': sects_out,
        'delta_since_last_review': delta,
    }
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # ---- MD ----
    L = ['# 门派世系表（考订工具 B · 自动生成）\n']
    L.append(f'> rev{rev} · 基于 {len(books)} 书 · 派 {len(sects_out)} · tenure {payload["meta"]["totals"]["tenures"]}\n')
    for s in sects_out:
        L.append(f"## {s['sect']}\n")
        L.append('| 掌门 | 在位起点 | 终点 | 置信 | 证据 | 成员 |')
        L.append('|---|---|---|---|---|---|')
        for t in s['tenures']:
            ev = '，'.join(f"{e['book']}·{e['loc']}" for e in t['evidence'][:2]) or '—'
            ms = '，'.join(m['name'] for m in t['members'][:8]) or '—'
            L.append(f"| {t['leader'] or '（未解析）'} | {t['period']['from']} | {t['period']['to']} | {t['conf']} | {ev} | {ms} |")
        for g in s['gaps']:
            L.append(f"- 缺口：{g['note']}")
        if s['ungrouped']:
            L.append(f"- 未归组成员：{('，'.join(s['ungrouped'][:10])) or '—'}")
        L.append('')
    (KB / '门派世系表.md').write_text('\n'.join(L) + '\n', encoding='utf-8')

    print(f"派 {len(sects_out)} · tenure {payload['meta']['totals']['tenures']} · rev{rev}")
    for s in sects_out:
        if s['tenures']:
            chain = ' → '.join(t['leader'] or '?' for t in s['tenures'])
            print(f"  {s['sect']}: {chain}")
    print(f"-> {out_json}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
