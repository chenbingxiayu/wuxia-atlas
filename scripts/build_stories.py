# -*- coding: utf-8 -*-
"""数据说书专栏数据管线（M5）——两篇专栏的可复跑数据切片。

故事一《一夜白头：卓练温度曲线》（蓝图 B1）
  口径：同章在场（共同参与）的两人 + 情感极性三层信号：
    ① 联手对手（同回两人共同交战的对象数——"并肩"）
    ② 互动动词极性（救/护/赠/谢=正；刺/捉/扣/逼/斥=负）
    ③ 摘录情感词扫描（本地进行，只发布计数——L0 安全）
  考订锚点（全部有定位符依据）：001 劫镖初会 · 004 黄龙洞 · 013 武当 ·
  026 剑闯名山/一夜白头（026:53）· 029 银针暗救 · 032 天山守花相望。

故事二《武功食物链：卓一航成长曲线》（蓝图 B6 的可计算子集）
  口径：白发魔女传 事件表中 卓一航 作为 主/客 的 ◈◉▲ 事件——
    主客比（主动出击占比）逐回翻转、杀伤清单、对手"分量"（对手档案出场总量均值）。
  不做胜/负 NLP 判定（ fragile），只发布结构化事实与定位符。

输出：site/data/stories/*.json（L0：计数 + 定位符；摘录只本地使用、不入切片）
用法：python scripts/build_stories.py
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import SITE_DATA, today  # noqa: E402

try:
    from kb_discovery import KB  # noqa: E402
except Exception:
    KB = Path(__file__).resolve().parents[1] / 'kb'

BOOK = '白发魔女传'
A, B_ = '卓一航', '练霓裳'

POS_VERBS = {'救', '护', '赠', '送', '谢', '助', '寻', '访', '疗', '医', '陪', '安慰', '挡'}
NEG_VERBS = {'刺', '杀', '伤', '斥', '逐', '拒', '擒', '捉', '扣', '逼', '追', '罚', '掳', '胁'}
POS_KW = ['相救', '暗中', '心软', '柔情', '深情', '关切', '心爱', '爱慕', '喜', '谢', '赠']
NEG_KW = ['误会', '冷笑', '负心', '绝情', '斥', '怒', '泪', '恨', '悔']
MARKERS = [
    {'c': 1, 'label': '劫镖初会'},
    {'c': 4, 'label': '黄龙洞剑谱'},
    {'c': 13, 'label': '武当重逢'},
    {'c': 26, 'label': '剑闯名山 · 一夜白头（026:53）'},
    {'c': 29, 'label': '银针暗救（029）'},
    {'c': 32, 'label': '天山守花相望'},
]


def load_events():
    s = json.loads((SITE_DATA / 'atlas' / f'{BOOK}.json').read_text(encoding='utf-8'))
    return s


def temp_curve(slice_):
    per = {c: {'co_events': 0, 'pos': 0, 'neg': 0, 'allies': 0, 'kw_pos': 0, 'kw_neg': 0, 'key': []}
           for c in range(1, slice_['chapters'] + 1)}
    chaps_a = set(slice_['persons'].get(A, {}).get('chaps', []))
    chaps_b = set(slice_['persons'].get(B_, {}).get('chaps', []))
    shared = chaps_a & chaps_b
    for c in sorted(shared):
        row = per[c]
        targets_a, targets_b = set(), set()
        for e in slice_['events'].get(str(c), []):
            a_, b_, v = e.get('a'), e.get('b'), e.get('v') or e.get('code') or ''
            if a_ == A or a_ == B_:
                (targets_a if a_ == A else targets_b).add(b_ or '')
            involved = (a_ in (A, B_)) or (b_ in (A, B_))
            if involved:
                row['co_events'] += 1
                if v in POS_VERBS:
                    row['pos'] += 1
                elif v in NEG_VERBS:
                    row['neg'] += 1
                if {a_, b_} == {A, B_} and row['co_events'] and len(row['key']) < 3:
                    row['key'].append({'l': e['l'], 'v': v, 'a': a_, 'b': b_})
        row['allies'] = len((targets_a & targets_b) - {A, B_})
        # 摘录情感词（本地扫描；切片只留计数）
        evf = KB / BOOK / '事件表.json'
        if not hasattr(temp_curve, '_cache'):
            temp_curve._cache = json.loads(evf.read_text(encoding='utf-8')).get('events', [])
        for e in temp_curve._cache:
            loc = e.get('loc', '')
            try:
                lc = int(loc[:3])
            except Exception:
                continue
            if lc != c or e.get('dropped'):
                continue
            ex = e.get('excerpt') or ''
            row['kw_pos'] += sum(ex.count(k) for k in POS_KW)
            row['kw_neg'] += sum(ex.count(k) for k in NEG_KW)
    return {'book': BOOK, 'a': A, 'b': B_, 'shared_chapters': sorted(shared),
            'per_chapter': [{'c': c, **per[c]} for c in sorted(per)], 'markers': MARKERS}


def growth_curve(slice_, dossiers):
    weight = {}
    for d in dossiers.get('dossiers', []):
        weight[d['canonical']] = d.get('appearance_total', 0)
    rows = []
    for c in range(1, slice_['chapters'] + 1):
        active = passive = kills = 0
        opps = Counter()
        for e in slice_['events'].get(str(c), []):
            a_, b_, v, code = e.get('a'), e.get('b'), e.get('v') or '', e.get('code') or ''
            if code not in ('◈', '◉', '▲'):
                continue
            if a_ == A:
                active += 1
                if b_ and b_ != A:
                    opps[b_] += 1
                if v in ('杀', '诛', '毙'):
                    kills += 1
            elif b_ == A:
                passive += 1
                if a_ and a_ != A:
                    opps[a_] += 1
        known = [weight.get(o, 0) for o in opps if weight.get(o, 0)]
        rows.append({'c': c, 'active': active, 'passive': passive,
                     'kills': kills,
                     'opponents': [o for o, _ in opps.most_common(4)],
                     'opp_weight': round(sum(known) / len(known)) if known else 0})
    act = next((r['c'] for r in rows if r['c'] >= 5 and r['active'] > r['passive'] and (r['active'] + r['passive']) >= 3), None)
    first_kill = next((r['c'] for r in rows if r['kills'] > 0), None)
    return {'book': BOOK, 'person': A, 'per_chapter': rows,
            'milestones': {'first_dominant_chapter': act, 'first_kill_chapter': first_kill,
                           'known_end': '032 平成章五、诛天德上人（蓝图 B6 叙事锚点）'}}


def main() -> int:
    out = SITE_DATA / 'stories'
    out.mkdir(parents=True, exist_ok=True)
    slice_ = load_events()
    dossiers = json.loads((SITE_DATA / 'dossiers.json').read_text(encoding='utf-8'))
    for name, payload in (
        ('temp-curve', temp_curve(slice_)),
        ('growth-curve', growth_curve(slice_, dossiers)),
    ):
        payload = {'meta': {'generated': today(), 'schema': 'story-v1', 'script': 'scripts/build_stories.py',
                            'copyright': 'L0：计数+定位符；摘录仅本地使用，不入切片'}, **payload}
        p = out / f'{name}.json'
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'-> {p} ({p.stat().st_size // 1024} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
