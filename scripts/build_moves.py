# -*- coding: utf-8 -*-
"""考订工具 A：招式底表构建器（v2 · 纯解析结果 · 可增量扩展）。

只消费解析结果（lit_books() 自动发现）：实体登记表 + tagged 标注语料 + 事件表 + 关系表。
把 ☆ 层拆为 功法/招式 两级，招式归属父武功与门派，产出 kb/招式表.json。

扩展语义：工具=纯函数（解析结果→结果表全量重算）；人工裁定存 TSV
（kb/校订/招式表-考订.tsv，稳定键=招式规范名）跨版本存活；每次重跑产出 delta。

用法：python scripts/build_moves.py
"""
import json
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import lit_books, today, KB  # noqa: E402

# ---- 常量 ----
ART_SUFFIX = ('剑法', '掌法', '刀法', '拳法', '神功', '心法', '内功', '阵法', '剑术',
              '身法', '步法', '指法', '棍法', '杖法', '鞭法', '枪法', '腿法', '爪法',
              '轻功', '点穴', '擒拿', '剑阵', '拳', '剑', '掌', '刀', '鞭', '杖', '枪')
GENERIC_MOVE_WORDS = set(
    '一招 这招 那招 出招 还招 绝招 妙招 虚招 实招 拆招 招式 招架 接招 连招 发招 '
    '招数 使招 快招 毒招 阴招 招法 后招 前招 高招 招儿'.split())
Q = '“”\'\'「」'  # 引号族

NAME = r'[\u4e00-\u9fa5]{2,6}'
# 明文归属：功法名 + 中/里的 一招'X'
ARTNAME = r'[一-龥]{2,10}(?:剑法|掌法|刀法|拳法|剑术|神功|心法|内功|功法|剑阵|阵法)'
SECT_ALT = None  # 运行时由 ◆ 规范名构建
P_PARENT_BY_ART = re.compile(r'(' + ARTNAME + r')(?:中|里)(?:的)?(?:一)?(?:招|式)?[“”''](' + NAME + r')[””'']')
P_PARENT_BY_SECT_TPL = '({sects})(?:中|里)的?[“”''](' + NAME + r')[””'']'

P_MOVE_QUOTED = [
    re.compile(r'[“”''](' + NAME + r')[””''](?:这|那)?一(?:招|式)'),
    re.compile(r'一(?:招|式)[“”''](' + NAME + r')[””'']'),
    re.compile(r'第[一二三四五六七八九十百千零○0-9]{1,6}(?:式|招)[“”'']?(' + NAME + r')'),
    re.compile(r'[“”''](' + NAME + r')[””'']之(?:式|招)'),
]
GENERIC_NEAR = re.compile(r'(一招|招式|一式|这一招|那一招|绝招|看招|招数|出招)')

CONF_RANK = {'weak': 0, 'ok': 1, 'strong': 2}


def load_json(p: Path):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def strip_marks(raw: str) -> str:
    """去标留文（lint 语义）：〖☆ 无常夺命〗→无常夺命；〖@ 玉罗刹|练霓裳〗→玉罗刹"""
    raw = re.sub(r'〖([^〗]*)〗', lambda m: m.group(1).split('|')[0].strip(), raw)
    return re.sub(r'⟦([^⟧]*)⟧', r'', raw)


def norm_marks(raw: str) -> str:
    """规范名归一：〖☆ 无常夺命|无常夺命〗→无常夺命（管道名优先），供功法名识别"""
    def repl(m):
        body = m.group(1)
        name = body.split('|')[-1].strip() if '|' in body else body.split('|')[0].strip()
        return re.sub(r'^[@=◆%☆•\[§+]', '', name)
    raw = re.sub(r'〖([^〗]*)〗', repl, raw)
    return re.sub(r'⟦([^⟧]*)⟧', lambda m: m.group(1).split()[-1], raw)


def mark_names(raw: str, code: str):
    """〖@ surface|canonical 〗 → 规范名列表（无管道取 surface）"""
    out = []
    for tok in re.findall(r'〖' + code + r'([^〗]*)〗', raw):
        tok = tok.strip()
        out.append(tok.split('|')[-1].strip() if '|' in tok else tok)
    return out


def read_tagged(book: str):
    """yield (chap, lineno, raw, clean, persons, sects, arts)；clean=规范名归一文本"""
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
            yield chap, lineno, s, norm_marks(s), mark_names(s, '@'),                 mark_names(s, '◆'), mark_names(s, '☆')

def clean_art_name(s: str) -> str:
    """父名清洗：功法后缀+≤4字，再去前导虚词/动词（'航用的是武当掌法'→'武当掌法'）"""
    m = re.search(r'[一-龥]{1,4}(?:剑法|掌法|刀法|拳法|剑术|神功|心法|内功|功法|剑阵|阵法)$', s)
    if not m:
        return s
    name = m.group(0)
    part = '的是了用使施展变疾急连就地这那回第'
    while len(name) > 4 and name[0] in part:
        name = name[1:]
    return name


def main() -> int:
    books = lit_books()
    print(f'输入书目（lit_books）：{books}')

    # ---- 1) 实体与别名（☆ 层）----
    art_alias2canon = {}      # 任意名 → ☆ 规范名
    art_canon_set = set()
    rel_art_sect = {}         # 功法 → 拥有它的 ◆（先验）
    rel_sect_ev = {}          # 功法 → [(book, loc, sect)] 关系表门派证据
    char_art = defaultdict(dict)   # 人物 → {武功: [谓词]}
    for book in books:
        reg = load_json(KB / book / '实体登记表.json')
        for key, e in reg['entities'].items():
            if e['type'] != '☆':
                continue
            art_canon_set.add(e['canonical'])
            art_alias2canon[e['canonical']] = e['canonical']
            for a in e.get('aliases', {}):
                art_alias2canon.setdefault(a, e['canonical'])
        rel = load_json(KB / book / '关系表.json')
        for r in rel['relations']:
            if r['object_type'] == '☆':
                art_canon_set.add(r['object'])
                art_alias2canon.setdefault(r['object'], r['object'])
                if r['subject_type'] == '◆':
                    rel_art_sect.setdefault(r['object'], Counter())[r['subject']] += 1
                    rel_sect_ev.setdefault(r['object'], []).append((book, r['evidence_locators'][0] if r.get('evidence_locators') else '', r['subject']))
                if r['subject_type'] == '@':
                    char_art[r['subject']].setdefault(r['object'], []).append(r['predicate'])

    # ---- 2) tagged 收集：☆ 出现处 + 上下文窗口 ----
    windows = defaultdict(dict)     # (book, chap) -> {lineno: clean}
    occ = defaultdict(list)         # ☆规范名 -> [(book, chap, lineno, persons, sects)]
    for book in books:
        for chap, lineno, raw, clean, persons, sects, arts in read_tagged(book):
            windows[(book, chap)][lineno] = clean
            for a in arts:
                canon = art_alias2canon.get(a, a)
                occ[canon].append((book, chap, lineno, persons, sects))

    def window(book, chap, lineno, radius=1):
        lines = windows.get((book, chap), {})
        return ''.join(lines.get(l, '') for l in range(lineno - radius, lineno + radius + 1))

    # ---- 3) 归层 ----
    level = {}          # canon -> 功法|招式|待定
    move_ev = defaultdict(list)   # canon -> [(book, loc, kind)]
    for canon, occs in occ.items():
        if canon.endswith(ART_SUFFIX) or canon in GENERIC_MOVE_WORDS:
            level[canon] = '功法'
            continue
        lv = '待定'
        for book, chap, lineno, _p, _s in occs:
            w = window(book, chap, lineno)
            # 明文招式：模式捕获名 == 本实体
            for pat in P_MOVE_QUOTED:
                for m in pat.finditer(w):
                    if art_alias2canon.get(m.group(1), m.group(1)) == canon:
                        lv = '招式'
                        move_ev[canon].append((book, f'{chap}:{lineno}', '明文招式'))
                        break
                if lv == '招式':
                    break
            if lv != '招式':
                # 弱信号：名字附近有 招/式 通用词
                for m in re.finditer(re.escape(canon), w):
                    lo, hi = max(0, m.start() - 8), min(len(w), m.end() + 8)
                    if GENERIC_NEAR.search(w[lo:hi]):
                        lv = '招式' if lv == '待定' else lv
                        move_ev[canon].append((book, f'{chap}:{lineno}', '共现招式'))
                        break
        level[canon] = lv

    moves = {c for c, lv in level.items() if lv == '招式'}

    # ◆ 门派名交替式（明文派级归属："武当派中的'X'一招"）
    sect_names = set()
    for book in books:
        reg = load_json(KB / book / '实体登记表.json')
        for key, e in reg['entities'].items():
            if e['type'] == '◆':
                sect_names.add(e['canonical'])
    sect_alt = '|'.join(sorted((re.escape(s) for s in sect_names), key=len, reverse=True))
    P_PARENT_BY_SECT = re.compile(r'(' + sect_alt + r')(?:中|里)的?[“”''](' + NAME + r')[””'']')

    # ---- 4) 归属（招式 → 父武功）----
    parent_votes = defaultdict(lambda: defaultdict(Counter))  # move -> tier -> Counter(parent)
    move_sect = defaultdict(Counter)
    used_by = defaultdict(Counter)
    for canon in sorted(moves):
        for book, chap, lineno, persons, sects in occ[canon]:
            w = window(book, chap, lineno)
            tier = None
            # strong：功法级明文归属（"达摩剑法中的'X'"）
            for m in P_PARENT_BY_ART.finditer(w):
                mv = art_alias2canon.get(m.group(2), m.group(2))
                if mv == canon:
                    parent = clean_art_name(art_alias2canon.get(m.group(1), m.group(1)))
                    parent_votes[canon]['strong'][parent] += 1
                    move_ev[canon].append((book, f'{chap}:{lineno}', '明文归属(功法)'))
                    tier = 'strong'
            # strong：派级明文归属（"武当派中的'X'"）→ 定门派
            for m in P_PARENT_BY_SECT.finditer(w):
                mv = art_alias2canon.get(m.group(2), m.group(2))
                if mv == canon:
                    move_sect[canon][m.group(1)] += 3
                    move_ev[canon].append((book, f'{chap}:{lineno}', '明文归属(派)'))
                    tier = tier or 'ok'
            if tier == 'strong':
                for p in persons:
                    used_by[canon][p] += 1
                for s in sects:
                    move_sect[canon][s] += 1
                continue
            # ok：窗口共现唯一父；多父用使用者先验
            arts_in_w = [a for a in art_canon_set if a != canon and a in w and level.get(a) == '功法']
            if arts_in_w:
                chosen = None
                if len(arts_in_w) == 1:
                    chosen = arts_in_w[0]
                else:
                    user_arts = Counter()
                    for p in persons:
                        for a, preds in char_art.get(p, {}).items():
                            if a in arts_in_w:
                                user_arts[a] += len(preds)
                    if user_arts:
                        chosen = user_arts.most_common(1)[0][0]
                    else:
                        chosen = min(arts_in_w, key=lambda a: w.find(a))
                parent_votes[canon]['ok'][chosen] += 1
                move_ev[canon].append((book, f'{chap}:{lineno}', '共现归属'))
            else:
                for s in sects:
                    move_sect[canon][s] += 1
            for p in persons:
                used_by[canon][p] += 1

    # ---- 5) 汇总条目 ----
    def best_parent(votes):
        """(parent, conf, alternates, conflict)"""
        strong = votes.get('strong', {})
        ok = votes.get('ok', {})
        if strong:
            top = strong.most_common()
            parent, n = top[0]
            conflict = len([1 for _, c in top if c == n]) > 1 or bool(ok)
            return parent, 'strong', [p for p, _ in top[1:]], conflict and len(top) > 1
        if ok:
            top = ok.most_common()
            parent, n = top[0]
            return parent, 'ok', [p for p, _ in top[1:]], len(top) > 1
        return None, 'weak', [], False

    def best_sect(canon, parent):
        c = move_sect.get(canon)
        if c and c.most_common(1)[0][1] >= 3:   # 明文派级归属优先
            return c.most_common(1)[0][0]
        if parent and rel_art_sect.get(parent):
            return rel_art_sect[parent].most_common(1)[0][0]
        if c:
            return c.most_common(1)[0][0]
        if canon in rel_sect_ev:
            return rel_sect_ev[canon][0][2]
        return None

    items, conflicts = [], []
    for canon in sorted(moves):
        votes = parent_votes.get(canon, {})
        parent, conf, alts, conflict = best_parent(votes)
        if conflict and parent:
            conflicts.append({'canonical': canon,
                              'parents': [{'art': parent, 'conf': conf}] +
                                         [{'art': a, 'conf': 'ok'} for a in alts],
                              'note': '多父归属，待人工裁'})
        sect = best_sect(canon, parent)
        if conf == 'weak':
            parent = '待考'
        items.append({
            'canonical': canon,
            'level': '招式',
            'parent_art': parent or '待考',
            'sect': sect,
            'conf': conf if parent else 'weak',
            'evidence': [{'book': b, 'loc': loc, 'kind': k}
                         for b, loc, k in move_ev.get(canon, [])[:12]],
            'used_by': [{'name': n, 'n': c} for n, c in used_by.get(canon, Counter()).most_common(5)],
            'status': 'auto',
        })

    # ---- 6) 人工 TSV（稳定键=规范名）----
    tsv = KB / '校订' / '招式表-考订.tsv'
    rulings = {}
    if tsv.exists():
        for ln in tsv.read_text(encoding='utf-8').splitlines()[1:]:
            parts = ln.split('\t')
            if len(parts) >= 4 and parts[0].strip():
                rulings[parts[0].strip()] = parts  # name,parent,conf,裁决,...
    orphans = []
    for it in items:
        r = rulings.get(it['canonical'])
        if not r:
            continue
        verdict = r[3].strip() if len(r) > 3 else 'accept'
        if verdict == 'reject':
            it['status'] = 'rejected'
        elif verdict.startswith('alias-of:'):
            it['status'] = 'alias'
            it['alias_of'] = verdict.split(':', 1)[1]
        else:
            it['status'] = 'reviewed'
            if r[1].strip():
                it['parent_art'] = r[1].strip()
            if r[2].strip():
                it['conf'] = r[2].strip()
    for name in rulings:
        if name not in {i['canonical'] for i in items}:
            orphans.append(name)

    # ---- 7) delta（对比上一版）----
    out_json = KB / '招式表.json'
    prev = load_json(out_json) if out_json.exists() else None
    delta = {'new_moves': [], 'conf_upgraded': [], 'new_conflicts': len(conflicts), 'orphans': orphans}
    if prev:
        prev_moves = {m['canonical']: m for m in prev.get('moves', [])}
        cur_names = {i['canonical'] for i in items}
        delta['new_moves'] = sorted(cur_names - set(prev_moves))
        for it in items:
            pm = prev_moves.get(it['canonical'])
            if pm and CONF_RANK.get(it['conf'], 0) > CONF_RANK.get(pm.get('conf', 'weak'), 0):
                delta['conf_upgraded'].append(f"{it['canonical']} {pm.get('conf')}→{it['conf']}")
    rev = (prev or {}).get('meta', {}).get('rev', 0) + 1
    payload = {
        'meta': {'generated': today(), 'rev': rev, 'schema': 'moves-v1',
                 'based_on': {'books': books, 'kb_date': today()},
                 'wordlist': 'moves-v0.1',
                 'totals': {'moves': len(items), 'reviewed': sum(1 for i in items if i['status'] == 'reviewed'),
                            'conflicts': len(conflicts)},
                 'conf_legend': 'strong=明文归属 ok=窗口共现 weak=先验（不发布）'},
        'moves': items,
        'conflicts': conflicts,
        'delta_since_last_review': delta,
    }
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # ---- 8) MD ----
    L = ['# 招式表（考订工具 A · 自动生成）\n']
    L.append(f'> rev{rev} · 基于 {len(books)} 书（{ "、".join(books) }）· 招式 {len(items)} 条 ·'
             f' conflicts {len(conflicts)} · 人工裁定 {payload["meta"]["totals"]["reviewed"]} 条\n')
    L.append('## 归属成立（strong/ok）\n')
    L.append('| 招式 | 父武功 | 门派 | 置信 | 证据 |')
    L.append('|---|---|---|---|---|')
    for it in items:
        if it['conf'] in ('strong', 'ok') and it['status'] != 'rejected':
            ev = '，'.join(f"{e['book']}·{e['loc']}" for e in it['evidence'][:3])
            L.append(f"| {it['canonical']} | {it['parent_art']} | {it['sect'] or '—'} | {it['conf']} | {ev} |")
    L.append('\n## 待考（weak）\n')
    L.append('，'.join(it['canonical'] for it in items if it['conf'] == 'weak') or '—')
    L.append('\n## 冲突（多父待裁）\n')
    for c in conflicts:
        L.append(f"- {c['canonical']}：{' vs '.join(p['art'] for p in c['parents'])}")
    L.append('\n## delta\n')
    L.append(f"- 新增招式 {len(delta['new_moves'])}：{('，'.join(delta['new_moves'][:15])) or '—'}")
    L.append(f"- 置信升级 {len(delta['conf_upgraded'])}：{('，'.join(delta['conf_upgraded'])) or '—'}")
    L.append(f"- 孤儿裁定 {len(orphans)}：{('，'.join(orphans)) or '—'}\n")
    (KB / '招式表.md').write_text('\n'.join(L) + '\n', encoding='utf-8')

    strong_n = sum(1 for i in items if i['conf'] == 'strong')
    ok_n = sum(1 for i in items if i['conf'] == 'ok')
    weak_n = sum(1 for i in items if i['conf'] == 'weak')
    print(f"招式 {len(items)}（strong {strong_n} / ok {ok_n} / weak {weak_n}）· conflicts {len(conflicts)} ·"
          f" reviewed {payload['meta']['totals']['reviewed']} · 孤儿 {len(orphans)} · rev{rev}")
    for it in items:
        if it['conf'] == 'strong':
            print(f"  strong: {it['canonical']} ← {it['parent_art']}（{it['sect']}）"
                  f" ev: {it['evidence'][0]['book']}·{it['evidence'][0]['loc']}")
    print(f"-> {out_json}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
