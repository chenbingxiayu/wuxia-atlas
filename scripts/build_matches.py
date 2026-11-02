# -*- coding: utf-8 -*-
"""侠谱评分 M1：对局表构建（build_matches.py）。

按《侠谱评分功能规格》§四：
  对局单位 = 场景（同回、行号连续 ≤15 行的 ◈/◉/▲ 事件聚合一景；一景一对局）；
  胜负裁决 = tagged 窗口（规范名归一文本）胜负词表 v0.1——
    强胜 1.0 / 常规胜 0.8 / 险胜 0.6 / 平 0.7；下风信号辅助判向；败方 = 败词前最近 @人物；
  modifiers：中毒×0.3 带伤×0.5 偷袭×0.5 诈败→draw×0.5 放水×0.5 切磋×0.3；围攻=景内人数>2（v0 整场一场）。
  排除：dropped / in_quote（假设句）/ 主宾缺失。
输出：site/data/matches.json（L0：结构化对局 + 定位符；词表命中词与摘录不发布）。

用法：python scripts/build_matches.py
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import KB, SITE_DATA, lit_books, today  # noqa: E402

WORDLIST = 'v0.1'
SCENE_SPLITTER = 'v0.1'
GAP = 15  # 场景行距阈值

# 胜负词表 v0.1（规格 §4.2；类别 → 权重）
LOSS_CLASSES = [
    (1.0, ['大败', '击败', '战败', '打败', '击倒', '击毙', '刺死', '擒下', '活捉', '一招夺下',
           '毙于', '斩于', '死于', '杀退', '败走', '倒地', '栽倒']),
    (0.8, ['占得上风', '迫退', '逼退', '震退', '荡开', '迫得后退', '逼得后退', '伤在']),
    (0.6, ['险胜', '堪堪取胜', '略胜一筹', '侥幸获胜', '略占上风']),
]
DRAW_WORDS = ['不分胜负', '平分秋色', '难分高下', '势均力敌', '旗鼓相当', '打个平手',
              '战个平手', '战成平手', '相持不下', '两败俱伤', '斗个两败俱伤']
FLIP_WORDS = ['连连后退', '只有招架', '招架不住', '招架之功', '败象渐露', '遮拦不住', '再难支撑']
MODIFIERS = [('中毒', ['中毒', '服毒', '下药']), ('状态不佳', ['带伤', '伤重', '力竭', '久战']),
             ('偷袭', ['偷袭', '暗算', '冷箭', '背后偷袭']), ('诈败', ['诈败', '卖个破绽', '佯输']),
             ('放水', ['留手', '未出全力', '手下留情']), ('切磋', ['切磋', '指点', '印证武功'])]
MOD_MULT = {'中毒': 0.3, '状态不佳': 0.5, '偷袭': 0.5, '诈败': 0.5, '放水': 0.5, '切磋': 0.3}


def load_json(p: Path):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def build_alias_map(books):
    """全类型实体 别名→规范名（事件表主宾可能是别名/称号）。"""
    m = {}
    for book in books:
        reg = load_json(KB / book / '实体登记表.json')
        for key, e in reg['entities'].items():
            c = e.get('canonical')
            if not c:
                continue
            m.setdefault(c, c)
            for a in (e.get('aliases') or {}):
                m.setdefault(a, c)
    from kb_discovery import BOOK_CANON
    for k, v in BOOK_CANON.items():
        m.setdefault(k, v)
    return m


def read_tagged(book):
    """yield (chap, lineno, clean)；clean=规范名归一文本（动词保留，名称=规范名）"""
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
            def repl(m):
                body = m.group(1)
                name = body.split('|')[-1].strip() if '|' in body else body.split('|')[0].strip()
                return re.sub(r'^[@=◆%☆•\[§+]', '', name)
            clean = re.sub(r'〖([^〗]*)〗', repl, s)
            clean = re.sub(r'⟦([^⟧]*)⟧', lambda m: m.group(1).split()[-1], clean)
            yield chap, lineno, clean


def nearest_name(text: str, pos: int, names: set, back: int = 14):
    """败词前最近的人物规范名（≤back 字符窗口内）。"""
    lo = max(0, pos - back)
    seg = text[lo:pos]
    best, bestp = None, -1
    for n in names:
        p = seg.rfind(n)
        if p >= 0 and p > bestp:
            best, bestp = n, p
    return best


def main() -> int:
    books = lit_books()
    alias = build_alias_map(books)
    canon = lambda n: alias.get(n, n)

    matches = []
    fighters = set()
    excluded = {'dropped': 0, 'in_quote': 0, 'no_participants': 0}
    mid = 0

    for book in ['白发魔女传', '塞外奇侠传', '七剑下天山', '江湖三女侠']:
        if book not in books:
            continue
        # 事件（排除 dropped / in_quote / 缺主宾）
        evs = []
        for e in load_json(KB / book / '事件表.json').get('events', []):
            if e.get('dropped') or e.get('curation', {}).get('verdict') == 'drop':
                excluded['dropped'] += 1
                continue
            if e.get('in_quote'):
                excluded['in_quote'] += 1
                continue
            if not e.get('subject') or not e.get('object') or e.get('verb_code') not in ('◈', '◉', '▲'):
                continue
            loc = e.get('loc', '')
            try:
                chap, line = int(loc[:3]), int(loc[4:7])
            except ValueError:
                continue
            evs.append({'chap': chap, 'line': line, 'code': e['verb_code'],
                        'a': canon(e['subject']), 'b': canon(e['object'])})
        # tagged 文本
        text_by_line = {(chap, ln): clean for chap, ln, clean in read_tagged(book)}
        # 按回分组 + 场景切分（行距 ≤ GAP）
        by_chap = defaultdict(list)
        for e in evs:
            by_chap[e['chap']].append(e)
        for chap in sorted(by_chap):
            group = sorted(by_chap[chap], key=lambda e: e['line'])
            scenes, cur = [], [group[0]]
            for e in group[1:]:
                if e['line'] - cur[-1]['line'] <= GAP:
                    cur.append(e)
                else:
                    scenes.append(cur)
                    cur = [e]
            scenes.append(cur)
            for si, scene in enumerate(scenes):
                # 景内文本（事件行 ±2 行合并）
                lines = sorted({l for e in scene for l in range(e['line'] - 2, e['line'] + 3)})
                text = ''.join(text_by_line.get((chap, l), '') for l in lines)
                n_ev_people = {x for e in scene for x in (e['a'], e['b'])}
                if len(n_ev_people) < 2:
                    excluded['no_participants'] += 1
                    continue
                kind = '围攻' if len(n_ev_people) > 2 else '单挑'
                mods = [name for name, kws in MODIFIERS if any(k in text for k in kws)]
                weight_mult = 1.0
                for mo in mods:
                    weight_mult *= MOD_MULT.get(mo, 1.0)
                # 对对各裁一场（按事件频次降序；同景多人=围攻，v0 整场一场/对）
                pair_count = Counter()
                for e in scene:
                    if e['a'] != e['b']:
                        pair_count[frozenset((e['a'], e['b']))] += 1
                all_loss_words = [(w, cw) for cw, ws in LOSS_CLASSES for w in ws] + [(w, 0.8) for w in FLIP_WORDS]
                has_draw_word = any(k in text for k in DRAW_WORDS)
                has_zhabai = any(k in text for k in MODIFIERS[3][1])
                for pair_fs, _cnt in pair_count.most_common():
                    pair = set(pair_fs)
                    outcome, weight_cls = None, None
                    if True:
                        votes = []
                        for w, cw in all_loss_words:
                            start = 0
                            while True:
                                pp = text.find(w, start)
                                if pp < 0:
                                    break
                                loser = nearest_name(text, pp, pair)
                                if loser and loser in pair:
                                    winner = next(n for n in pair if n != loser)
                                    votes.append((winner, loser, cw))
                                start = pp + len(w)
                        if votes:
                            tally = defaultdict(float)
                            for winner, loser, cw in votes:
                                tally[(winner, loser)] += cw
                            (winner, loser), wsum = sorted(tally.items(), key=lambda kv: -kv[1])[0]
                            aa, bb = sorted(pair)
                            outcome = 'win' if winner == aa else 'loss'
                            weight_cls = round(min(1.0, wsum), 2)
                            if has_zhabai:
                                outcome, weight_cls = 'draw', 0.5
                        elif has_draw_word:
                            outcome, weight_cls = 'draw', 0.7
                    if outcome is None:
                        continue  # 无明文裁决 → 不入评分（避免噪声）
                    if '诈败' in mods and outcome != 'draw':
                        outcome = 'draw'
                    weight = round(weight_cls * weight_mult, 2)
                    aa, bb = sorted(pair)
                    mid += 1
                    matches.append({
                        'id': f'M{mid:03d}', 'a': aa, 'b': bb, 'outcome': outcome,
                        'weight': weight, 'confidence': 'high' if (weight_cls or 0) >= 1.0 else 'medium',
                        'modifiers': mods, 'kind': kind,
                        'book': book, 'loc': f"{chap:03d}:{scene[0]['line']:03d}",
                        'scene': f'S{chap:03d}-{si + 1:02d}',
                    })
                    fighters.update(pair)


    fighters = sorted(fighters)
    payload = {'meta': {'generated': today(), 'schema': 'matches-v1',
                        'wordlist_version': WORDLIST, 'scene_splitter_version': SCENE_SPLITTER,
                        'totals': {'matches': len(matches), 'fighters': len(fighters),
                                   'excluded_narrative': sum(excluded.values())},
                        'excluded_detail': excluded,
                        'note': '词表命中词与摘录不发布（L0）；围攻 v0=整场一场；连续交锋合并留 v1'},
             'matches': matches, 'fighters': fighters}
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    out = SITE_DATA / 'matches.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    by_outcome = Counter(m['outcome'] for m in matches)
    print(f"-> {out} ({out.stat().st_size // 1024} KB)")
    print(f"对局 {len(matches)}（win {by_outcome['win']} / loss {by_outcome['loss']} / draw {by_outcome['draw']}）"
          f" · 参战者 {len(fighters)} · 排除 {sum(excluded.values())}（{excluded}）")
    top = sorted(matches, key=lambda m: -m['weight'])[:8]
    for m in top:
        print(f"  {m['id']} {m['a']} vs {m['b']} = {m['outcome']}（w{m['weight']} {m['kind']} {m['modifiers']}）{m['book']}·{m['loc']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
