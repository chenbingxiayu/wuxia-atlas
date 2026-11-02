# -*- coding: utf-8 -*-
"""考订工具 C：神兵宝物底表构建器（v1 · 纯解析结果 · 可增量扩展）。

只消费解析结果（lit_books() 自动发现）：实体登记表 `•` 实体 + tagged 标注语料 + 事件表。
产出 kb/神兵表.json（归层/品阶/流转链）+ 站点切片 site/data/weapons.json（L0）。

归层三判（• 池混杂真神兵/泛称/药材——2026-11-01 抽样）：
  专名性（主信号，非泛称即名物候选）> 明文品阶（窗口品阶词）> 药材词表（转丹药谱原料）。
流转链（蓝图 B8 自动化）：窗口 ±1 行内 流转动词句式 + @人物 同现 → strong 明文边；
  同回 ▲/◈ 事件侧证 → ok；未见持有者 = end_state 候选。
扩展语义同工具 A/B：TSV（kb/校订/神兵表-考订.tsv，稳定键=名物规范名）跨版本存活；delta 只列增量。

用法：python scripts/build_artifacts.py
"""
import json
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import lit_books, today, KB, SITE_DATA  # noqa: E402

# ---- 词表（artifact-wordlist v0.1）----
# 药材（→ 丹药谱原料层，不入神兵谱）
MEDICINE = {'雪莲', '天山雪莲', '千年芝草', '优昙花', '优昙仙花', '熊胆', '何首乌', '蛇胆',
            '灵芝', '人参', '鹿茸', '朱砂', '雄黄', '麝香', '牛黄', '当归', '茯苓'}
# 药材含字规则（含 → 丹药谱原料层；先于器类后缀判定）
MEDICINE_CONTAINS = ('参', '首乌', '芝草', '雪莲', '优昙', '鹤顶红', '蜈蚣', '曼陀罗', '雄黄', '鹿茸')
# 器类泛称（整名命中 → 凡物层，仅数据不发布）
PLAIN_OBJECTS = {'匕首', '软鞭', '皮鞭', '弹弓', '珍珠', '胡琴', '皮带', '飞刀', '毒刀',
                 '银针', '毒针', '袖箭', '毒箭', '响箭', '令箭', '甩手箭', '飞抓', '飞锥',
                 '飞钹', '飞芒', '钢环', '金环', '金牌', '长剑', '短剑', '宝剑', '利剑',
                 '钢镖', '铁尺', '铁箭', '钢珠', '暗器', '兵器', '兵刃', '刀枪', '弓箭',
                 '长枪', '大刀', '钢刀', '戒刀', '铁棍', '铁棒', '铜锤', '铁锤', '宝杖'}
# 品阶词（窗口命中 → grade_basis=明文）
GRADE_WORDS = {'神兵': '神兵', '宝剑': '神兵', '名剑': '神兵', '宝刀': '神兵', '宝物': '神兵',
               '仙品': '神兵', '利器': '利器', '利剑': '利器', '削铁如泥': '利器',
               '吹毛断发': '利器', '锋利无比': '利器'}
# 器类后缀 → category
KIND_SUFFIX = [('剑', '剑'), ('刀', '刀'), ('针', '暗器'), ('镖', '暗器'), ('箭', '暗器'),
               ('钉', '暗器'), ('砂', '暗器'), ('蒺藜', '暗器'), ('抓', '奇门'), ('锥', '暗器'),
               ('钹', '奇门'), ('锤', '奇门'), ('钩', '奇门'), ('锉', '奇门'), ('杵', '奇门'),
               ('拐', '奇门'), ('杖', '奇门'), ('笔', '奇门'), ('烟杆', '奇门'), ('烟袋', '奇门'),
               ('软甲', '护甲'), ('镜', '护甲'), ('兜', '护甲'), ('符', '宝物'), ('牌', '宝物'),
               ('珠', '宝物'), ('车', '奇门'), ('花', '宝物'), ('草', '药材'), ('莲', '药材')]
VERB_LABEL = {'夺': '夺', '赠': '赠', '还': '还', '传': '传', '借': '借', '毁': '毁', '失': '失'}

P_CHAIN = [
    ('夺', re.compile(r'(夺|抢|缴|掳|劫)(?:去|走|了|来|过|到)')),
    ('赠', re.compile(r'(赠|送|递|交)(?:给|与|了|到)')),
    ('还', re.compile(r'(归还|送还|交还|还给|璧还)')),
    ('传', re.compile(r'(传给|传了|留给|交托|托付|遗给|传下)')),
    ('借', re.compile(r'(借给|借来|借用|借了|借用)')),
    ('毁', re.compile(r'(折断|毁去|毁|断成|掷|抛|沉入|砸)')),
    ('失', re.compile(r'(遗失|失落|丢失|失去)')),
]
CONF_RANK = {'weak': 0, 'ok': 1, 'strong': 2}
NAME = r'[\u4e00-\u9fa5]{2,8}'


def load_json(p: Path):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def norm_marks(raw: str) -> str:
    def repl(m):
        body = m.group(1)
        name = body.split('|')[-1].strip() if '|' in body else body.split('|')[0].strip()
        return re.sub(r'^[@=◆%☆•\[§+]', '', name)
    raw = re.sub(r'〖([^〗]*)〗', repl, raw)
    return re.sub(r'⟦([^⟧]*)⟧', lambda m: m.group(1).split()[-1], raw)


def mark_names(raw: str, code: str):
    out = []
    for tok in re.findall(r'〖' + code + r'([^〗]*)〗', raw):
        tok = tok.strip()
        out.append(tok.split('|')[-1].strip() if '|' in tok else tok)
    return out


def read_tagged(book: str):
    """yield (chap, lineno, clean, persons, weapons)；clean=规范名归一文本"""
    tdir = KB / 'tagged' / book
    if not tdir.is_dir():
        return
    for fp in sorted(tdir.glob('*.tagged.md')):
        chap = int(fp.name[:3])
        lines = fp.read_text(encoding='utf-8').splitlines()
        if lines and lines[0].strip() == '---':
            endfm = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
            body = lines[endfm + 1:] if endfm is not None else lines
        else:
            body = lines
        for lineno, s in enumerate(body, 1):
            clean = norm_marks(s)
            yield chap, lineno, clean, mark_names(s, '@'), mark_names(s, '•')


def classify_level(name: str):
    """→ (level 名物|凡物|药材, category)"""
    if name in MEDICINE or any(k in name for k in MEDICINE_CONTAINS):
        return '药材', '药材'
    if name in PLAIN_OBJECTS:
        return '凡物', next((cat for suf, cat in KIND_SUFFIX if name.endswith(suf)), '兵器')
    for suf, cat in KIND_SUFFIX:
        if name.endswith(suf):
            return '名物', cat
    return '名物', '宝物'


def main() -> int:
    books = lit_books()
    print(f'输入书目（lit_books）：{books}')

    # ---- 1) `•` 实体与别名 ----
    alias2canon, canon_set = {}, set()
    ent_meta = {}
    for book in books:
        reg = load_json(KB / book / '实体登记表.json')
        for key, e in reg['entities'].items():
            if e['type'] != '•':
                continue
            c = e['canonical']
            canon_set.add(c)
            alias2canon[c] = c
            for a in (e.get('aliases') or {}):
                alias2canon.setdefault(a, c)
            m = ent_meta.setdefault(c, {'count': 0, 'books': {}})
            m['count'] += e.get('count', 0)
            m['books'].setdefault(book, set()).update(e.get('chapters', []))

    # ---- 2) tagged 收集 ----
    windows = defaultdict(dict)
    occ = defaultdict(list)   # canon -> [(book, chap, lineno, persons)]
    for book in books:
        for chap, lineno, clean, persons, weapons in read_tagged(book):
            windows[(book, chap)][lineno] = clean
            for w in weapons:
                occ[alias2canon.get(w, w)].append((book, chap, lineno, persons))

    def window(book, chap, lineno, radius=1):
        lines = windows.get((book, chap), {})
        return ''.join(lines.get(l, '') for l in range(lineno - radius, lineno + radius + 1))

    # ---- 3) 同回事件索引（▲/◈/◉ 侧证）----
    ev_index = defaultdict(list)
    for book in books:
        evf = KB / book / '事件表.json'
        if not evf.exists():
            continue
        for e in load_json(evf).get('events', []):
            if e.get('dropped'):
                continue
            if e.get('verb_code') in ('▲', '◈', '◉'):
                chap = int(e['loc'][:3])
                ev_index[(book, chap)].append(e)

    # ---- 4) 归层 + 品阶 + 流转链 ----
    items, alias_cand = [], set()
    for canon in sorted(canon_set, key=lambda c: -ent_meta[c]['count']):
        level, kind = classify_level(canon)
        grade, grade_basis = None, None
        chain, holders = [], Counter()
        evidence = []
        occs = occ.get(canon, [])
        for book, chap, lineno, persons in occs:
            w = window(book, chap, lineno)
            loc = f'{chap}:{lineno}'
            for gw, g in GRADE_WORDS.items():
                if gw in w:
                    grade, grade_basis = g, '明文'
            for p in persons:
                holders[p] += 1
            edge = None
            uniq_persons = list(dict.fromkeys(persons))
            for verb, pat in P_CHAIN:
                if canon in w and pat.search(w) and uniq_persons:
                    edge = {'verb': verb, 'persons': uniq_persons[:3], 'book': book,
                            'loc': loc, 'conf': 'strong'}
                    break
            if edge:
                chain.append(edge)
                evidence.append({'book': book, 'loc': loc, 'kind': f'明文流转({edge["verb"]})'})
            else:
                evidence.append({'book': book, 'loc': loc, 'kind': '共现'})
        # ok：同回 ▲/◈ 事件侧证（事件主客与窗口人物相交）
        for (book, chap), evs in ev_index.items():
            here = [p for b2, c2, l2, ps in occs if b2 == book and c2 == chap for p in ps]
            if not here:
                continue
            for e in evs:
                if (e.get('subject') in here) or (e.get('object') in here):
                    chain.append({'verb': '交战侧证', 'persons': [x for x in (e.get('subject'), e.get('object')) if x],
                                  'book': book, 'loc': e['loc'], 'conf': 'ok'})
                    break

        if level != '名物':
            items.append({'canonical': canon, 'level': level, 'kind': kind,
                          'count': ent_meta[canon]['count'], 'status': 'auto'})
            continue
        # 异名候选：包含关系（游龙 ⊂ 游龙剑）
        for other in canon_set:
            if other != canon and (canon in other or other in canon):
                alias_cand.add((min(canon, other), max(canon, other)))
        conf = 'strong' if any(e['conf'] == 'strong' for e in chain) else ('ok' if chain else 'weak')
        items.append({
            'canonical': canon, 'level': '名物', 'kind': kind,
            'grade': grade,  # 品阶只认明文词；推断品阶留给人工考订（防"神兵"通胀）
            'grade_basis': grade_basis,
            'conf': conf,
            'chain': chain[:12],
            'holders': [{'name': n, 'n': c} for n, c in holders.most_common(6)],
            'end_state': {'note': f"末见持有：{'、'.join([n for n, _ in holders.most_common(2)]) or '—'}"
                                  f"（{max(occs, key=lambda o: (o[1], o[2]))[0]}·{max(occs, key=lambda o: (o[1], o[2]))[1]} 回）"} if occs and holders else None,
            'evidence': evidence[:12],
            'ev_total': len(evidence),
            'books': {b: sorted(cs) for b, cs in ent_meta[canon]['books'].items()},
            'count': ent_meta[canon]['count'],
            'status': 'auto',
        })

    # ---- 5) 人工 TSV（稳定键=规范名）----
    tsv = KB / '校订' / '神兵表-考订.tsv'
    rulings = {}
    if tsv.exists():
        for ln in tsv.read_text(encoding='utf-8').splitlines()[1:]:
            parts = ln.split('\t')
            if len(parts) >= 4 and parts[0].strip():
                rulings[parts[0].strip()] = parts
    orphans = []
    for it in items:
        r = rulings.get(it['canonical'])
        if not r:
            continue
        verdict = r[4].strip() if len(r) > 4 else 'accept'
        if verdict == 'reject':
            it['status'] = 'rejected'
        elif verdict.startswith('alias-of:'):
            it['status'] = 'alias'
            it['alias_of'] = verdict.split(':', 1)[1]
        else:
            it['status'] = 'reviewed'
            for i, field in ((1, 'level'), (2, 'kind'), (3, 'grade')):
                if r[i].strip():
                    it[field] = r[i].strip()
    for name in rulings:
        if name not in {i['canonical'] for i in items}:
            orphans.append(name)

    # ---- 6) delta ----
    out_json = KB / '神兵表.json'
    prev = load_json(out_json) if out_json.exists() else None
    delta = {'new_artifacts': [], 'conf_upgraded': [], 'new_alias_candidates': len(alias_cand), 'orphans': orphans}
    if prev:
        prev_m = {a['canonical']: a for a in prev.get('artifacts', [])}
        delta['new_artifacts'] = sorted({i['canonical'] for i in items} - set(prev_m))
        for it in items:
            pm = prev_m.get(it['canonical'])
            if pm and CONF_RANK.get(it.get('conf', 'weak'), 0) > CONF_RANK.get(pm.get('conf', 'weak'), 0):
                delta['conf_upgraded'].append(f"{it['canonical']} {pm.get('conf')}→{it.get('conf')}")
    rev = (prev or {}).get('meta', {}, ).get('rev', 0) + 1 if prev else 1

    named = [i for i in items if i['level'] == '名物' and i['status'] != 'rejected']
    payload = {
        'meta': {'generated': today(), 'rev': rev, 'schema': 'artifacts-v1',
                 'based_on': {'books': books, 'kb_date': today()},
                 'wordlist': 'artifact-wordlist-v0.1',
                 'totals': {'entities': len(canon_set),
                            '名物': sum(1 for i in items if i['level'] == '名物'),
                            '凡物': sum(1 for i in items if i['level'] == '凡物'),
                            '药材': sum(1 for i in items if i['level'] == '药材'),
                            'reviewed': sum(1 for i in items if i['status'] == 'reviewed'),
                            'chain_strong': sum(1 for i in named for e in i.get('chain', []) if e['conf'] == 'strong')},
                 'conf_legend': 'strong=明文流转句式 ok=交战/共现侧证 weak=仅出现'},
        'artifacts': items,
        'alias_candidates': sorted(f'{a} ⊂ {b}' if a in b else f'{b} ⊂ {a}' for a, b in alias_cand)[:30],
        'delta_since_last_review': delta,
    }
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # ---- 7) 站点切片（L0：名物 only，无摘录）----
    slice_items = []
    for it in named:
        slice_items.append({
            'canonical': it['canonical'], 'kind': it['kind'],
            'grade': it.get('grade'), 'grade_basis': it.get('grade_basis'),
            'conf': it.get('conf'), 'status': it['status'],
            'chain': [{'verb': e['verb'], 'persons': e['persons'], 'book': e['book'],
                       'loc': e['loc'], 'conf': e['conf']} for e in it.get('chain', [])],
            'holders': it.get('holders', []),
            'end_state': it.get('end_state'),
            'books': it['books'], 'count': it['count'], 'ev_total': it.get('ev_total', 0),
            'evidence': it.get('evidence', []),
        })
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    sp = SITE_DATA / 'weapons.json'
    sp.write_text(json.dumps({'meta': {**payload['meta']}, 'weapons': slice_items},
                             ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'-> {sp} ({sp.stat().st_size // 1024} KB, 名物 {len(slice_items)})')

    # ---- 8) MD ----
    L = ['# 神兵表（考订工具 C · 自动生成）\n']
    L.append(f'> rev{rev} · 基于 {len(books)} 书 · 实体 {len(canon_set)} · 名物 {payload["meta"]["totals"]["名物"]}'
             f' · 凡物 {payload["meta"]["totals"]["凡物"]} · 药材 {payload["meta"]["totals"]["药材"]}'
             f' · 明文流转边 {payload["meta"]["totals"]["chain_strong"]}\n')
    L.append('## 名物（有流转链或品阶）\n')
    L.append('| 名物 | 器类 | 品阶 | 置信 | 流转 | 持有人 |')
    L.append('|---|---|---|---|---|---|')
    for it in named:
        if it['conf'] in ('strong', 'ok'):
            ch = '→'.join(f"{e['verb']}" for e in it['chain'][:4]) or '—'
            hold = '、'.join(h['name'] for h in it.get('holders', [])[:3]) or '—'
            L.append(f"| {it['canonical']} | {it['kind']} | {it.get('grade') or '—'}{'（明文）' if it.get('grade_basis')=='明文' else ''} | {it['conf']} | {ch} | {hold} |")
    L.append('\n## 其余名物（仅共现证据，weak）\n')
    weak = [it['canonical'] for it in named if it['conf'] == 'weak']
    L.append('、'.join(weak) or '—')
    L.append('\n## 异名候选（⊂ 包含关系，待裁）\n')
    L.append('；'.join(payload['alias_candidates']) or '—')
    L.append('\n## delta\n')
    L.append(f"- 新增名物 {len(delta['new_artifacts'])}：{('，'.join(delta['new_artifacts'][:15])) or '—'}")
    L.append(f"- 孤儿裁定 {len(orphans)}：{('，'.join(orphans)) or '—'}\n")
    (KB / '神兵表.md').write_text('\n'.join(L) + '\n', encoding='utf-8')

    t = payload['meta']['totals']
    print(f"实体 {t['entities']}（名物 {t['名物']} / 凡物 {t['凡物']} / 药材 {t['药材']}）"
          f" · 明文流转边 {t['chain_strong']} · reviewed {t['reviewed']} · rev{rev}")
    for it in named:
        if it['conf'] == 'strong':
            ch = ' → '.join(f"[{e['verb']}]{'+'.join(e['persons'][:2])}" for e in it['chain'][:3])
            print(f"  strong: {it['canonical']}（{it['kind']}）{(' ★' + it['grade']) if it.get('grade') else ''} {ch}")
    print(f'-> {out_json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
