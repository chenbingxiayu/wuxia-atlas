# -*- coding: utf-8 -*-
"""侠谱评分 M2/M3：Glicko-2 引擎 + 评分表（build_ratings.py）。

按《侠谱评分功能规格》§五（参数落定）：
  Glicko-2：r0=1500, rd0=350, σ=0.06, τ=0.5；每场一个评分周期，按宇宙编年（白发→塞外→七剑→三女侠）+ 回序更新；
  长尾收缩：展示分 = (W·r + P·1500)/(W+5)；
  分档：合成榜展示分分位 95/90/70/30 → 绝顶/超一流/一流/二流/三流；
  per_book：每书独立重跑（1500 起评）供书内榜；
  conflicts：高置信非平局、且败方展示分高出差 ≥120 的"明文×数据"倒置（剧情保护候选，L1 单句）。
输出：site/data/ratings.json（规格 §3.2 契约）。评分不可手改——唯一入口本脚本。

用法：python scripts/build_ratings.py
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import SITE_DATA, today  # noqa: E402

R0, RD0, SIGMA, TAU, P_SHRINK = 1500.0, 350.0, 0.06, 0.5, 5
Q = 0.0057565
SCALE = 173.7178
CHRONO = ['白发魔女传', '塞外奇侠传', '七剑下天山', '江湖三女侠']
TIER_QUANTILES = [('绝顶', 0.95), ('超一流', 0.90), ('一流', 0.70), ('二流', 0.30)]


def glicko2_update(mu, phi, sigma, opponents):
    """opponents = [(mu_j, phi_j, score)]；标准 Glicko-2（Glickman 2012）。"""
    def g(phi):
        return 1.0 / math.sqrt(1 + 3 * Q * Q * phi * phi / math.pi ** 2)

    def E(mu, mu_j, phi_j):
        return 1.0 / (1 + math.exp(-g(phi_j) * (mu - mu_j)))

    if not opponents:
        phi_prime = math.sqrt(phi * phi + sigma * sigma)
        return mu, phi_prime, sigma
    v_inv = sum((g(pj) ** 2) * E(mu, mj, pj) * (1 - E(mu, mj, pj)) for mj, pj, _ in opponents)
    v = 1.0 / v_inv
    delta = v * Q * sum(g(pj) * (s - E(mu, mj, pj)) for mj, pj, s in opponents)
    delta_sq = delta * delta
    a = math.log(sigma * sigma)
    A = a
    if delta_sq > v + phi * phi:
        B = math.log(delta_sq - v - phi * phi)
    else:
        k = 1
        while a - k * TAU < math.log(v + phi * phi) and k < 200:
            k += 1
        B = a - k * TAU

    def f(x):
        num = math.exp(x) * (delta_sq - phi * phi - v - math.exp(x))
        den = 2 * (phi * phi + v + math.exp(x)) ** 2
        return num / den - (x - a) / (TAU * TAU)

    fa, fb = f(A), f(B)
    it = 0
    while abs(A - B) > 1e-6 and it < 100 and not (math.isnan(fa) or math.isnan(fb) or fb == fa):
        C = A + (A - B) * fa / (fb - fa)
        fc = f(C)
        if fc * fb < 0:
            A, fa = B, fb
        else:
            fa = fa / 2
        B, fb = C, fc
        it += 1
    sigma_new = math.exp(A / 2)
    phi_star = math.sqrt(phi * phi + sigma_new * sigma_new)
    phi_prime = 1.0 / math.sqrt(1 / (phi_star * phi_star) + 1 / v)
    sum_term = sum(g(pj) * (s - E(mu, mj, pj)) for mj, pj, s in opponents)
    mu_prime = mu + phi_prime * sum_term  # Glickman 2012 §5.3：µ′ = µ + φ′·Σg(s−E)（无 q）
    return mu_prime, phi_prime, sigma_new


def run_glicko(matches):
    """按宇宙编年逐场更新；返回 {name: (rating, rd, w, d, l, per_match_rating)}。"""
    players = {}
    for m in matches:
        for n in (m['a'], m['b']):
            players.setdefault(n, {'r': R0, 'rd': RD0, 'sigma': SIGMA, 'w': 0, 'd': 0, 'l': 0})
    order = sorted(matches, key=lambda m: (CHRONO.index(m['book']) if m['book'] in CHRONO else 9,
                                           int(m['loc'][:3]), int(m['loc'][4:7] or 0)))
    for m in order:
        pa, pb = players[m['a']], players[m['b']]
        mu_a = (pa['r'] - R0) / SCALE
        phi_a = pa['rd'] / SCALE
        mu_b = (pb['r'] - R0) / SCALE
        phi_b = pb['rd'] / SCALE
        s_a = {'win': 1.0, 'draw': 0.5, 'loss': 0.0}[m['outcome']]
        s_b = 1.0 - s_a
        w_a, w_b = m['weight'], m['weight']
        mu_a, phi_a, sig_a = glicko2_update(mu_a, phi_a, pa['sigma'], [(mu_b, phi_b, s_a)])
        mu_b, phi_b, sig_b = glicko2_update(mu_b, phi_b, pb['sigma'], [(mu_a, phi_a, s_b)])
        for p, mu, phi, sig, s in ((pa, mu_a, phi_a, sig_a, s_a), (pb, mu_b, phi_b, sig_b, s_b)):
            p['r'] = R0 + SCALE * mu
            p['rd'] = SCALE * phi
            p['sigma'] = sig
        if s_a > s_b:
            pa['w'] += 1; pb['l'] += 1
        elif s_a < s_b:
            pa['l'] += 1; pb['w'] += 1
        else:
            pa['d'] += 1; pb['d'] += 1
    return players


def main() -> int:
    md = json.loads((SITE_DATA / 'matches.json').read_text(encoding='utf-8'))
    matches = md['matches']

    # 合成榜（宇宙编年）
    players = run_glicko(matches)
    # 书内榜（每书独立 1500 起评）
    per_book_final = defaultdict(dict)
    for book in CHRONO:
        bm = [m for m in matches if m['book'] == book]
        if not bm:
            continue
        bp = run_glicko(bm)
        for n, p in bp.items():
            per_book_final[n][book] = round(p['r'])

    # 展示分（长尾收缩）+ 分档分位
    rows = []
    for n, p in players.items():
        W = p['w'] + p['d'] + p['l']
        display = (W * p['r'] + P_SHRINK * R0) / (W + P_SHRINK) if W else R0
        rows.append({'name': n, 'r': p['r'], 'rd': p['rd'], 'w': p['w'], 'd': p['d'], 'l': p['l'],
                     'n': W, 'display': display})
    displays = sorted(r['display'] for r in rows)

    def quantile(qs):
        if not displays:
            return 1500.0
        i = min(len(displays) - 1, max(0, int(round(qs * (len(displays) - 1)))))
        return displays[i]

    thresholds = {name: round(quantile(q)) for name, q in TIER_QUANTILES}

    def tier_of(v):
        if v >= thresholds['绝顶']:
            return '绝顶'
        if v >= thresholds['超一流']:
            return '超一流'
        if v >= thresholds['一流']:
            return '一流'
        if v >= thresholds['二流']:
            return '二流'
        return '三流'

    # 冲突（明文×数据倒置）：高置信非平局 + 败方展示分高出 ≥120
    disp = {r['name']: r['display'] for r in rows}
    raw_events = {}
    conflicts = []
    for book in CHRONO:
        p = Path(__file__).resolve().parents[1] / 'kb' / book / '事件表.json'
        if p.exists():
            for e in json.loads(p.read_text(encoding='utf-8')).get('events', []):
                raw_events[(book, e.get('loc'))] = e
    for m in matches:
        if m['outcome'] == 'draw' or m['confidence'] != 'high' or m['weight'] < 0.8:
            continue
        winner = m['a'] if m['outcome'] == 'win' else m['b']
        loser = m['b'] if m['outcome'] == 'win' else m['a']
        delta = disp.get(loser, R0) - disp.get(winner, R0)
        if delta >= 120:
            e = raw_events.get((m['book'], m['loc'].replace(':', ':', 1))) or {}
            excerpt = (e.get('excerpt') or '').strip()
            if len(excerpt) > 60:
                excerpt = excerpt[:57] + '…'
            conflicts.append({'type': '明文×数据', 'claim': excerpt or '（胜词命中，句证见定位符）',
                              'claim_loc': f"{m['book']}·{m['loc']}",
                              'data': {'winner': winner, 'loser': loser,
                                       'delta': round(delta), 'match': m['id']},
                              'note': '剧情保护候选：可能是主角光环/旁白夸张/抽取误差——冲突≠穿帮'})
    conflicts.sort(key=lambda c: -c['data']['delta'])
    conflicts = conflicts[:20]

    players_out = []
    match_idx = defaultdict(list)
    for m in matches:
        match_idx[m['a']].append(m['id'])
        match_idx[m['b']].append(m['id'])
    for r in sorted(rows, key=lambda r: -r['display']):
        players_out.append({
            'name': r['name'], 'rating': round(r['display']), 'rd': round(r['rd']),
            'tier': tier_of(r['display']),
            'matches_n': r['n'], 'w/d/l': [r['w'], r['d'], r['l']],
            'per_book': {b: per_book_final.get(r['name'], {}).get(b) for b in CHRONO
                         if per_book_final.get(r['name'], {}).get(b) is not None},
            'prior_applied': [],
            'top_evidence': match_idx.get(r['name'], [])[:3],
        })

    payload = {
        'meta': {'generated': today(), 'engine': 'glicko2',
                 'params': {'r0': R0, 'rd0': RD0, 'vol': SIGMA, 'tau': TAU, 'shrink_P': P_SHRINK},
                 'wordlist_version': md['meta']['wordlist_version'],
                 'calibration': {'holdout_n': 0, 'direction_recall': None,
                                 'note': 'v0 未做 holdout 抽检——方法论页如实标注，人工抽检 100 场待办'},
                 'tiers': thresholds,
                 'totals': {'players': len(players_out), 'matches': len(matches)}},
        'players': players_out,
        'conflicts': conflicts,
    }
    out = SITE_DATA / 'ratings.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"-> {out} ({out.stat().st_size // 1024} KB)")
    print(f"players {len(players_out)} · conflicts {len(conflicts)} · tiers {thresholds}")
    named = [p for p in players_out if p['matches_n'] > 0]
    print('Top 12（有对局者）:')
    for p in named[:12]:
        w, d, l = p['w/d/l']
        print(f"  {p['tier']} {p['name']:<6} {p['rating']}±{p['rd']}  {w}胜{d}平{l}负")
    return 0


if __name__ == '__main__':
    sys.exit(main())
