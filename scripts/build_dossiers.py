# -*- coding: utf-8 -*-
"""P1 ①：人物档案页 SKU 数据（已点亮书目全量 @ 实体；可传参数只做前 N）。

join 三类 kb 产物：实体登记表（身份/别名/出场）× 事件表（师承/战绩/关键事件）
× 关系表（武功/门派线索），为每个人物生成可独立加载的知识单元（SKU）。
书目由 kb_discovery.lit_books() 自动发现——新书面作后无需改本脚本。

版权档位：本文件为 L0——只含定位符（书·回:行）与图谱事实，**不含原文摘录**；
语料摘录仅存在于 kb/ 本地事件表中，站点渲染时如需 L1 短引文须另行走编辑流程。

派生逻辑（全部带证据，不凭印象）：
  师承/传人   ◇传艺事件（主→客，动词分级）＋ ○拜师/收徒事件（方向随动词）
  受立/继任   ○事件动词=立/指定/拥立/公推/封/追赠
  战绩        ◉杀伐/▲擒控 按主客双向聚合（排除 dropped）
  门派线索    人物修习/独门武功 ∩ 门派镇山/拥有武功（跨书匹配，derived=true）

用法：python scripts/build_dossiers.py [TOP_N]   # 默认全部已点亮书目的 @ 实体
"""
import json
import sys
from collections import defaultdict, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import lit_books, canon, BOOK_CANON, today, ROOT, KB, OUT  # noqa: E402
# ◇ 动词分级：强=正式传授；弱=点拨/演示（不算师承，只算"指点过"）
ART_STRONG = {'传授', '教', '传', '授', '授艺', '相授', '收', '收徒'}
ART_WEAK = {'指点', '讲解', '演', '相传'}
# ○ 师承按动词定方向：收/认 类主语=师父；拜师 类主语=徒弟。
# （'拜'单字歧义——007:59"拜铁飞龙做义父"为认亲非拜师——不入师承）
O_MASTER_SIDE = {'收', '收徒', '认'}
O_DISCIPLE_SIDE = {'拜师'}
O_RANK = {'立', '指定', '拥立', '公推', '封', '追赠'}
SECT_PREDICATES = {'镇山', '拥有', '独门'}


def load_book(book: str) -> dict:
    out = {}
    for name in ('实体登记表', '事件表', '关系表'):
        with open(KB / book / f'{name}.json', encoding='utf-8') as f:
            out[name] = json.load(f)
    return out


def chapter_curve(locators: list) -> dict:
    """定位符列表 -> {回号: 出现次数}"""
    c = Counter(loc.split(':')[0].lstrip('0') or '0' for loc in locators)
    return dict(sorted(((int(k), v) for k, v in c.items())))


def build() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    books = {b: load_book(b) for b in lit_books()}

    # ---- 合并 @ 实体（跨书 canonical 归并＋跨书规范名归并）----
    persons = {}
    for book, data in books.items():
        for key, e in data['实体登记表']['entities'].items():
            if e['type'] != '@':
                continue
            cn = canon(e['canonical'])
            m = persons.setdefault(cn, {'canonical': cn, 'books': {}})
            if book in m['books']:
                # 同书多个实体归并到同一规范名（如塞外的 练霓裳+白发魔女）：聚合不覆盖
                b = m['books'][book]
                b['count'] += e['count']
                for a, n in e.get('aliases', {}).items():
                    b['aliases'][a] = b['aliases'].get(a, 0) + n
                b['locators'].extend(e.get('locators', []))
                b['chapters'] = sorted(set(b['chapters']) | set(e.get('chapters', [])))
            else:
                m['books'][book] = {
                    'count': e['count'],
                    'aliases': dict(e.get('aliases', {})),
                    'locators': list(e.get('locators', [])),
                    'chapters': list(e.get('chapters', [])),
                }
    ranked = sorted(persons.values(), key=lambda m: -sum(b['count'] for b in m['books'].values()))
    if limit:
        ranked = ranked[:limit]

    # ---- 别名→规范名解析（跨书目 @ 实体；一名多主者不解析）----
    alias2canon = defaultdict(set)
    for book, data in books.items():
        for key, e in data['实体登记表']['entities'].items():
            if e['type'] != '@':
                continue
            cn = canon(e['canonical'])
            for n in set(e.get('aliases', {})) | {e['canonical']}:
                alias2canon[n].add(cn)
    canon_of = {a: next(iter(s)) for a, s in alias2canon.items() if len(s) == 1}
    # 跨书规范名本身也注册为解析目标（如"晦明禅师"作为别名指向岳鸣珂）
    for a, c in BOOK_CANON.items():
        canon_of.setdefault(a, c)

    # ---- 索引事件/关系 ----
    def iter_events():
        """yield (book, event, subject规范名, object规范名)"""
        for book, data in books.items():
            for e in data['事件表']['events']:
                if e.get('dropped'):
                    continue
                yield (book, e,
                       canon_of.get(e.get('subject'), e.get('subject')),
                       canon_of.get(e.get('object'), e.get('object')))

    def ev_item(book, e, s, o):
        return {'book': book, 'loc': e['loc'], 'verb_code': e['verb_code'],
                'verb': e['verb'], 'subject': s, 'object': o,
                'confidence': e.get('confidence'), 'in_quote': e.get('in_quote', False)}

    sect_arts = defaultdict(set)      # 门派 -> 武功集合
    sect_zhens = defaultdict(set)     # 门派 -> 镇山武功集合
    art_owner_count = Counter()       # 武功 -> 拥有它的门派数（独占性）
    art_ev = Counter()                # (主体,武功) -> 最大证据数
    art_locs = defaultdict(list)      # (主体,武功) -> 定位符
    char_art = defaultdict(dict)      # 人物 -> {武功: [谓词]}
    char_art_books = defaultdict(set)  # (人物,武功) -> 出现书目
    sect_zhen_books = defaultdict(set)  # (门派,武功) -> 镇山关系所在书目
    for book, data in books.items():
        for r in data['关系表']['relations']:
            pair = (r['subject'], r['object'])
            art_locs[pair].append(f"{book}·{'，'.join(r['evidence_locators'][:3])}")
            art_ev[pair] = max(art_ev[pair], r.get('evidence_count', 1))
            if r['subject_type'] == '◆' and r['predicate'] in SECT_PREDICATES:
                sect_arts[r['subject']].add(r['object'])
                art_owner_count[r['object']] += 1
                if r['predicate'] == '镇山':
                    sect_zhens[r['subject']].add(r['object'])
                    sect_zhen_books[(r['subject'], r['object'])].add(book)
            if r['subject_type'] == '@' and r['object_type'] == '☆':
                char_art[r['subject']].setdefault(r['object'], []).append(r['predicate'])
                char_art_books[(r['subject'], r['object'])].add(book)

    dossiers = []
    for m in ranked:
        name = m['canonical']
        books_present = sorted(m['books'])
        # 事实卡
        aliases = {}
        for book, info in m['books'].items():
            for a, n in info['aliases'].items():
                aliases[a] = aliases.get(a, 0) + n
        top_aliases = sorted(aliases.items(), key=lambda kv: -kv[1])[:8]

        # 师承/传人/受立（动词分级：强=传授类/拜师收徒；弱=指点演示类）
        masters, disciples, ranks = [], [], []
        for book, e, s, o in iter_events():
            if not s or not o:
                continue
            v = e['verb']
            if e['verb_code'] == '◇':
                tier = 'strong' if v in ART_STRONG else 'weak'
                if o == name and s != name:
                    masters.append({'person': s, 'book': book, 'loc': e['loc'], 'verb': v, 'tier': tier})
                if s == name and o != name:
                    disciples.append({'person': o, 'book': book, 'loc': e['loc'], 'verb': v, 'tier': tier})
            elif e['verb_code'] == '○' and v in O_MASTER_SIDE:
                if s == name and o != name:
                    disciples.append({'person': o, 'book': book, 'loc': e['loc'], 'verb': v, 'tier': 'strong'})
                if o == name and s != name:
                    masters.append({'person': s, 'book': book, 'loc': e['loc'], 'verb': v, 'tier': 'strong'})
            elif e['verb_code'] == '○' and v in O_DISCIPLE_SIDE:
                if s == name and o != name:
                    masters.append({'person': o, 'book': book, 'loc': e['loc'], 'verb': v, 'tier': 'strong'})
                if o == name and s != name:
                    disciples.append({'person': s, 'book': book, 'loc': e['loc'], 'verb': v, 'tier': 'strong'})
            elif e['verb_code'] == '○' and v in O_RANK and o == name:
                ranks.append({'by': s, 'book': book, 'loc': e['loc'], 'verb': v})

        def dedup_lineage(lst):
            agg = defaultdict(lambda: {'locs': [], 'verbs': Counter(), 'tiers': set()})
            for it in lst:
                a = agg[it['person']]
                a['locs'].append(f"{it['book']}·{it['loc']}")
                a['verbs'][it['verb']] += 1
                a['tiers'].add(it['tier'])
            return [{'person': k, 'tier': 'strong' if 'strong' in v['tiers'] else 'weak',
                     'verbs': [f"{vv}×{n}" for vv, n in v['verbs'].most_common()],
                     'locs': v['locs']}
                    for k, v in sorted(agg.items(),
                                       key=lambda kv: (-('strong' in kv[1]['tiers']), -len(kv[1]['locs'])))]
        masters, disciples = dedup_lineage(masters), dedup_lineage(disciples)

        def dedup(lst, key='person'):
            agg = defaultdict(list)
            for it in lst:
                agg[it[key]].append({'book': it['book'], 'loc': it['loc'], 'verb': it['verb']})
            return [{'person': k, 'records': v} for k, v in
                    sorted(agg.items(), key=lambda kv: -len(kv[1]))]
        ranks = dedup(ranks, 'by')

        # 战绩（◉/▲）与对手
        kills, slain_by, captures, captured_by = [], [], [], []
        opponents = Counter()
        conf_dist = Counter()
        for book, e, s, o in iter_events():
            if not s or not o or name not in (s, o):
                continue
            conf_dist[e.get('confidence', '?')] += 1
            if s == name and o != name:
                opponents[o] += 1
            if o == name and s != name:
                opponents[s] += 1
            if e['verb_code'] == '◉':
                if s == name:
                    kills.append({'target': o, 'book': book, 'loc': e['loc'],
                                  'confidence': e.get('confidence')})
                else:
                    slain_by.append({'by': s, 'book': book, 'loc': e['loc'],
                                     'confidence': e.get('confidence')})
            elif e['verb_code'] == '▲':
                if s == name:
                    captures.append({'target': o, 'book': book, 'loc': e['loc'],
                                     'confidence': e.get('confidence')})
                else:
                    captured_by.append({'by': s, 'book': book, 'loc': e['loc'],
                                        'confidence': e.get('confidence')})

        def agg_combat(lst, key):
            agg = defaultdict(list)
            for it in lst:
                agg[it[key]].append({'book': it['book'], 'loc': it['loc'],
                                     'confidence': it['confidence']})
            return [{'person': k, 'records': v} for k, v in
                    sorted(agg.items(), key=lambda kv: -len(kv[1]))]

        # 关键事件（high 优先，取 12 条）
        key_events = []
        for book, e, s, o in iter_events():
            if name in (s, o) and e.get('confidence') == 'high':
                key_events.append(ev_item(book, e, s, o))
        key_events.sort(key=lambda x: x['loc'])

        # 武功卡（关系表）＋ 门派线索（修习武功 ∩ 门派武功，跨书）
        arts = []
        for art, preds in char_art.get(name, {}).items():
            arts.append({'art': art, 'predicates': sorted(set(preds)),
                         'evidence': art_locs.get((name, art), [])[:3]})
        # 三级置信：strong=门派镇山武功且人物"修习"；ok=修习且(≥2 独占招或证据≥3)；
        # weak=单招低证/无修习/多门派共有招（大擒拿手类通名不构成归属线索）。
        owned = char_art.get(name, {})
        sect_affinity = []
        if owned:
            for sect, sarts in sect_arts.items():
                overlap = sorted(set(owned) & sarts)
                if not overlap:
                    continue
                distinctive = [a for a in overlap if art_owner_count[a] == 1]
                has_xiu = any('修习' in owned[a] for a in distinctive or overlap)
                max_ev = max((art_ev.get((name, a), 1) for a in overlap), default=1)
                # strong 要求"书内同证"：同一本书中人物修习 X 且门派镇山 X
                zhen_same_book = any(
                    '修习' in owned[a] and
                    (char_art_books.get((name, a), set()) & sect_zhen_books.get((sect, a), set()))
                    for a in overlap)
                if zhen_same_book:
                    tier = 'strong'
                elif distinctive and has_xiu and (len(distinctive) >= 2 or max_ev >= 3):
                    tier = 'ok'
                else:
                    tier = 'weak'
                sect_affinity.append({
                    'sect': sect, 'tier': tier, 'via_arts': overlap, 'derived': True,
                    'evidence': [{'art': a, 'char_preds': sorted(set(owned[a])),
                                  'char_evidence': art_locs.get((name, a), [])[:2],
                                  'sect_evidence': art_locs.get((sect, a), [])[:2]}
                                 for a in overlap]})
            order = {'strong': 0, 'ok': 1, 'weak': 2}
            sect_affinity.sort(key=lambda x: (order[x['tier']], -len(x['via_arts'])))

        curves = {book: chapter_curve(info['locators'])
                  for book, info in m['books'].items()}

        dossiers.append({
            'id': f"@{name}",
            'canonical': name,
            'cross_book': len(books_present) > 1,
            'books': books_present,
            'aliases': [{'alias': a, 'count': n} for a, n in top_aliases],
            'appearance_total': sum(b['count'] for b in m['books'].values()),
            'chapter_curves': curves,
            'sect_affinity': sect_affinity,          # derived=true；tier: strong(镇山+修习)/ok(≥2招+修习)/weak(单招线索)
            'lineage': {'masters': masters, 'disciples': disciples},
            'ranks': ranks,
            'combat': {
                'kills': agg_combat(kills, 'target'),
                'slain_by': agg_combat(slain_by, 'by'),
                'captures': agg_combat(captures, 'target'),
                'captured_by': agg_combat(captured_by, 'by'),
                'top_opponents': [{'person': p, 'n': n} for p, n in opponents.most_common(10)],
                'confidence_dist': dict(conf_dist),
            },
            'arts': arts,
            'key_events': key_events[:12],
            'summary': None,                          # 编辑流程：LLM 草拟→人工校→入定稿区
            'summary_status': '待撰写',
        })

    payload = {
        'meta': {
            'generated': today(), 'schema': 'site-dossiers-v1',
            'limit': limit, 'books': list(books),
            'copyright': 'L0 档位：仅定位符与图谱事实，不含原文摘录',
            'totals': {'entities_indexed': len(persons), 'dossiers_built': len(dossiers),
                       'cross_book': sum(1 for d in dossiers if d['cross_book'])},
        },
        'dossiers': dossiers,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / 'dossiers.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"dossiers={len(dossiers)} (of {len(persons)} persons)")
    for d in dossiers[:10]:
        aff = '，'.join(f"{s['sect']}({s['tier']})" for s in d['sect_affinity'][:2])
        print(f"  {d['canonical']}: 出场{d['appearance_total']} 跨书={d['cross_book']} "
              f"师{len(d['lineage']['masters'])}/徒{len(d['lineage']['disciples'])} 门派线索=[{aff}]")
    print(f"-> {OUT / 'dossiers.json'}")


if __name__ == '__main__':
    sys.exit(build())
