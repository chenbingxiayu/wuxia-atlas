# -*- coding: utf-8 -*-
"""工具 D：Gazetteer 地理底座构建器 —— 小说地名 → 真实经纬度。

用法：
  python scripts/build_gazetteer.py              # 离线：收集+判实+合并缓存/考订/种子 → kb/gazetteer.json + 站点切片
  python scripts/build_gazetteer.py --fetch 40   # 向 Nominatim 补拉 40 个缺坐标候选（1.1s/个，缓存可续跑）
  python scripts/build_gazetteer.py --strict     # 站点切片只收 verified 坐标（发布口径）

架构（同《考订工具实现设计》v3）：
  解析结果 → 结果表是纯函数，工具永远重算全量；人工裁定唯一载体 = TSV（稳定键 = 地名规范名），
  重跑按键回填；delta_since_last_review 只列增量。
数据源：各书 实体登记表.json 的 `=` 实体（lit_books() 自动发现）。
检索：Nominatim (OpenStreetMap)，缓存 kb/校订/gazetteer-cache/；核验：人工坐标拾取器 → gazetteer-考订.tsv。
坐标系：WGS-84 (EPSG:4326)。虚构地名不发布经纬度，只发布 锚点+方位+距离（渲染期偏移安放）。
"""
import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

from kb_discovery import KB, ROOT, SITE_DATA, canon, dump_json, lit_books, today

GAZ_KB = KB / 'gazetteer.json'
DIR_CUR = KB / '校订'
TSV_RULINGS = DIR_CUR / 'gazetteer-考订.tsv'
TSV_SEEDS = DIR_CUR / 'gazetteer-seeds.tsv'
DIR_CACHE = DIR_CUR / 'gazetteer-cache'
UA = 'wuxia-atlas-gazetteer/0.1 (knowledge-base build; contact: repo maintainer)'

# ---- 判实词表（Stage 2）------------------------------------------------
# 后缀 → (kind, real_guess)。顺序即优先级（先专后泛）。
SUFFIX_RULES = [
    ('寺观', ['寺', '观', '庙', '庵', '祠', '塔', '禅院', '道观'], True),
    ('关隘', ['关', '隘口', '隘'], True),
    ('山', ['山', '峰', '岭', '岗', '岩', '崖', '洞', '峡', '谷'], True),
    ('水域', ['江', '河', '湖', '海', '溪', '潭', '泉', '泊', '泽'], True),
    ('聚落', ['村', '庄', '镇', '堡', '寨', '集', '巷', '街', '铺', '店'], True),
    ('政区', ['省', '县', '州', '府', '郡', '卫', '所', '京', '都', '城'], True),
    ('边域', ['疆', '塞', '漠', '原', '外'], True),
]
# 泛称/纯方向词不单独成地（有专名前缀才算，如"天山"vs"山"）
GENERIC = {'山', '河', '江', '湖', '海', '城', '关', '村', '镇', '堡', '谷', '峡', '洞', '崖',
           '中原', '塞外', '关外', '江南', '漠北', '西域', '大漠', '京华', '江湖', '边关',
           ' East'.strip(), '东', '西', '南', '北', '上', '下'}
# 明文虚构（蓝图 A1 点名）——只收语料/考订点过名的，不猜
FICTION_KNOWN = {'风砂堡', '木什塔克', '喀沁草原'}

KIND_ALIASES = {  # kind → Nominatim type 加分词
    '山': {'peak', 'volcano', 'hill', 'mountain_range'},
    '寺观': {'monastery', 'temple', 'place_of_worship', 'church'},
    '关隘': {'pass'},
    '水域': {'river', 'lake', 'water', 'bay', 'sea'},
    '聚落': {'village', 'town', 'hamlet'},
    '政区': {'city', 'town', 'county', 'province', 'state', 'administrative', 'municipality'},
}


# ---- Stage 1：收集 ------------------------------------------------------
def load_places():
    """各书 `=` 实体 → {canonical: {books: {书: {chaps, locs}}, aliases, count}}。"""
    places = {}
    for book in lit_books():
        reg = json.loads((KB / book / '实体登记表.json').read_text(encoding='utf-8'))
        for key, ent in reg['entities'].items():
            if not key.startswith('='):
                continue
            name = canon(ent.get('canonical') or key[1:])
            chaps = [int(loc[:3]) for loc in ent.get('locators', []) if len(loc) >= 3]
            p = places.setdefault(name, {'aliases': set(), 'count': 0, 'books': {}})
            p['aliases'].update(a for a in (ent.get('aliases') or {}) if a != name)
            p['count'] += ent.get('count', 0)
            b = p['books'].setdefault(book, {'chaps': set(), 'locs': []})
            b['chaps'].update(chaps)
            b['locs'].extend(ent.get('locators', []))
    return places


# ---- Stage 2：判实 ------------------------------------------------------
def classify(name):
    if name in FICTION_KNOWN:
        return '场景', False
    if name in GENERIC:
        return '泛称', None
    for kind, suffixes, real in SUFFIX_RULES:
        if any(name.endswith(s) for s in suffixes):
            return kind, real
    return '地名', None  # 待判：交给检索/人工


# ---- TSV（裁定唯一载体）-------------------------------------------------
def read_tsv(path: Path):
    rows = []
    if not path.exists():
        return rows
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    if len(lines) < 2:
        return rows
    head = lines[0].lstrip('\ufeff').split('\t')
    for ln in lines[1:]:
        if not ln.strip() or ln.lstrip().startswith('#'):
            continue
        cells = ln.split('\t') + [''] * (len(head) - len(ln.split('\t')))
        rows.append({h.strip(): c.strip() for h, c in zip(head, cells)})
    return rows


def load_rulings():
    out = {}
    for r in read_tsv(TSV_RULINGS):
        key = r.get('键') or r.get('地名') or ''
        if not key:
            continue
        out[key] = {
            'ruling': r.get('裁决', 'accept') or 'accept',
            'real': r.get('real', '').lower() in ('1', 'true', '是', 'y') if r.get('real') else None,
            'lat': float(r['lat']) if r.get('lat') else None,
            'lng': float(r['lng']) if r.get('lng') else None,
            'precision': r.get('precision') or None,
            'kind': r.get('kind') or None,
            'anchor': r.get('anchor') or None,
            'bearing': r.get('bearing') or None,
            'dist_km': float(r['dist_km']) if r.get('dist_km') else None,
            'reviewer': r.get('reviewer') or None,
            'date': r.get('日期') or None,
        }
    return out


def load_seeds():
    out = {}
    for r in read_tsv(TSV_SEEDS):
        key = r.get('键') or r.get('地名') or ''
        if not key or not (r.get('lat') and r.get('lng')):
            continue
        out[key] = {
            'lat': float(r['lat']), 'lng': float(r['lng']),
            'precision': r.get('precision') or 'approx',
            'note': r.get('note') or 'seed:待人工核验',
        }
    return out


# ---- Stage 3：Nominatim 检索（缓存可续跑）--------------------------------
def fetch_one(name, kind):
    cache = DIR_CACHE / f'{name}.json'
    if cache.exists():
        return json.loads(cache.read_text(encoding='utf-8'))
    params = urllib.parse.urlencode({
        'q': name, 'format': 'jsonv2', 'limit': 3, 'countrycodes': 'cn',
        'accept-language': 'zh', 'addressdetails': 0,
    })
    url = f'https://nominatim.openstreetmap.org/search?{params}'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:  # 网络失败不阻塞构建：记错误缓存，下次重试
        data = [{'error': str(e)}]
    data = [{'name': c.get('name'), 'lat': float(c['lat']), 'lng': float(c['lon']),
             'type': c.get('type'), 'category': c.get('category'),
             'display': c.get('display_name'), 'importance': c.get('importance', 0),
             'error': c.get('error')} for c in data] or [{'error': 'no-result'}]
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    time.sleep(1.1)  # Nominatim 公共实例限速：≤1 req/s
    return data


def score(cand, name, kind, ref, place_books=None):
    """候选打分：类型吻合 + importance×2（同类型间的主信号）> 精确同名 > 行程链邻接。
    ref 锚点为 (lat, lng, books|None)：books=None（人工考订/种子）全局有效，
    否则仅对与该锚点**共书**的地名生效——行程链约束是书内的，跨书强锚会互相污染
    （山东强锚曾把河南"嵩山"带偏到威海同名，2026-11-02 勘误）。"""
    s = (cand.get('importance') or 0) * 2
    if kind in KIND_ALIASES and cand.get('type') in KIND_ALIASES[kind]:
        s += 1.5
    if (cand.get('name') or '') == name:
        s += 0.4  # 精确同名是小奖励：同类型候选间 importance 才是主信号（嵩山/华山勘误）
    elif name in (cand.get('display') or ''):
        s += 0.3
    if ref:  # 行程链邻接（<500km）加分
        for rlat, rlng, rbooks in ref:
            if rbooks is not None and place_books and not (rbooks & place_books):
                continue
            if haversine(rlat, rlng, cand['lat'], cand['lng']) < 500:
                s += 0.5
                break
    return s


def haversine(lat1, lng1, lat2, lng2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---- 构建 ---------------------------------------------------------------
def build(fetch_n: int, strict: bool):
    places = load_places()
    rulings = load_rulings()
    seeds = load_seeds()

    # --fetch：补拉缺坐标的真实候选（不含已裁定/虚构）
    if fetch_n:
        done = 0
        for name in sorted(places, key=lambda n: -places[n]['count']):
            if done >= fetch_n:
                break
            if name in rulings and rulings[name]['lat']:
                continue
            kind, guess = classify(name)
            if guess is False or kind == '泛称':
                continue
            if (DIR_CACHE / f'{name}.json').exists():
                continue
            print(f'  fetch [{done + 1}/{fetch_n}] {name} ({kind})')
            fetch_one(name, kind)
            done += 1

    # 已确认坐标（考订 > 种子）：人工裁定可信，作全局锚
    confirmed = []
    for name, r in rulings.items():
        if r['lat'] and r['ruling'] != 'reject':
            confirmed.append((r['lat'], r['lng']))
    for name, s in seeds.items():
        if name not in rulings:
            confirmed.append((s['lat'], s['lng']))

    # 锚点集（考订/种子 = 全局；自动强判定 = 同书有效），两轮传播消歧
    ref0 = [(lat, lng, None) for (lat, lng) in confirmed]

    def candidates_of(name):
        cache_f = DIR_CACHE / f'{name}.json'
        if not cache_f.exists():
            return []
        return [c for c in json.loads(cache_f.read_text(encoding='utf-8')) if not c.get('error')]

    def pick(name, kind, ref, place_books):
        cands = candidates_of(name)
        if not cands:
            return None, []
        best = max(cands, key=lambda c: score(c, name, kind, ref, place_books))
        return best, cands

    def is_strong(name, kind, best):
        """强判定：精确同名 + 类型吻合 + importance 达标——可作同书消歧的锚。"""
        return ((best.get('name') or '') == name
                and kind in KIND_ALIASES and best.get('type') in KIND_ALIASES[kind]
                and (best.get('importance') or 0) >= 0.2)

    picks = {}
    for name in places:
        kind, guess = classify(name)
        if guess is False or kind == '泛称':
            continue
        books = set(places[name]['books'])
        best, cands = pick(name, kind, ref0, books)
        if best:
            picks[name] = (kind, best, cands)
            if is_strong(name, kind, best):
                ref0.append((best['lat'], best['lng'], books))
    ref1 = list(ref0)
    out_places = []
    stats = {'real': 0, 'fiction': 0, 'pending': 0, 'with_coord': 0, 'verified': 0}
    for name in sorted(places, key=lambda n: -places[n]['count']):
        info = places[name]
        kind, guess = classify(name)
        entry = {'id': name, 'name': name, 'aliases': sorted(info['aliases']),
                 'kind': kind, 'real': guess, 'books': {}}
        for book, b in info['books'].items():
            entry['books'][book] = sorted(b['chaps'])
        entry['count'] = info['count']
        entry['status'] = 'auto'
        entry['verified'] = False

        src, cands = None, []
        # 坐标来源优先级：人工考订 > 种子（人工先验）> 检索缓存
        if name in seeds:
            s = seeds[name]
            entry.update(lat=s['lat'], lng=s['lng'], precision=s['precision'],
                         source={'engine': 'seed', 'note': s['note'], 'checked': None})
        elif name in picks:
            kind, best, cands = picks[name]
            best2, _ = pick(name, kind, ref1, set(info['books']))  # 第二轮：锚点集扩充后重选
            best = best2 or best
            src = {'engine': 'nominatim', 'type': best.get('type'),
                   'display': best.get('display'), 'importance': best.get('importance'),
                   'n_candidates': len(cands), 'checked': None}
            entry['lat'], entry['lng'] = best['lat'], best['lng']
            entry['precision'] = 'approx' if entry['real'] is None else 'shifted'
            if entry['real'] is None:
                entry['real'] = True
                kind = entry['kind'] = best.get('type') or kind
            entry['source'] = src
        if name in rulings:
            r = rulings[name]
            entry['status'] = 'reviewed'
            entry['verified'] = bool(r['lat'] and r['ruling'] == 'accept')
            if r['ruling'] == 'reject':
                entry['real'] = False
                entry.pop('lat', None), entry.pop('lng', None)
                entry['excluded'] = '人工裁定排除（非地名/泛称/误归并）'
            elif r['ruling'] == 'fictional' or r['real'] is False:
                entry['real'] = False
                entry.update({k: r[k] for k in ('anchor', 'bearing', 'dist_km') if r[k]})
                entry.pop('lat', None), entry.pop('lng', None)
            elif r['lat']:
                entry.update(lat=r['lat'], lng=r['lng'],
                             precision=r['precision'] or 'exact',
                             source={'engine': 'manual', 'reviewer': r['reviewer'],
                                     'checked': r['date']})

        if entry.get('lat'):
            stats['with_coord'] += 1
            if entry['verified']:
                stats['verified'] += 1
        if entry['real'] is False:
            stats['fiction'] += 1
        elif entry['real']:
            stats['real'] += 1
            if not entry.get('lat'):
                entry['status'] = entry['status'] if entry['status'] == 'reviewed' else 'missing_coord'
        else:
            stats['pending'] += 1
        out_places.append(entry)

    # delta（对比上一版）
    delta = {'new_places': [], 'coord_changed': [], 'note': ''}
    if GAZ_KB.exists():
        prev = {p['id']: p for p in json.loads(GAZ_KB.read_text(encoding='utf-8'))['places']}
        delta['new_places'] = [p['id'] for p in out_places if p['id'] not in prev]
        for p in out_places:
            q = prev.get(p['id'])
            if q and (p.get('lat'), p.get('lng')) != (q.get('lat'), q.get('lng')) and p.get('lat'):
                delta['coord_changed'].append(p['id'])
    else:
        delta['note'] = '首版（无上一版可比）'

    payload = {'meta': {'generated': today(), 'rev': (json.loads(GAZ_KB.read_text(encoding='utf-8'))['meta']['rev'] + 1) if GAZ_KB.exists() else 1,
                        'coord_system': 'WGS-84(EPSG:4326)',
                        'based_on': {'books': lit_books(), 'retrieval': 'Nominatim(OSM) + 人工坐标拾取器核验'},
                        'tsv_rulings': str(TSV_RULINGS.relative_to(ROOT)), 'tsv_seeds': str(TSV_SEEDS.relative_to(ROOT))},
               'stats': stats, 'delta_since_last_review': delta, 'places': out_places}
    GAZ_KB.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"-> {GAZ_KB} ({GAZ_KB.stat().st_size // 1024} KB)  stats={stats}")
    print(f"   delta: 新增 {len(delta['new_places'])} · 坐标改判 {len(delta['coord_changed'])}")

    # 站点切片（L0；strict 只收 verified）
    slice_places = []
    for p in out_places:
        if p['real'] is False:
            if p.get('anchor'):
                slice_places.append({k: p[k] for k in
                                     ('id', 'name', 'kind', 'real', 'precision', 'books', 'anchor', 'bearing', 'dist_km') if k in p})
            continue
        if 'lat' not in p:
            continue
        if strict and not p['verified']:
            continue
        keep = ('id', 'name', 'aliases', 'kind', 'real', 'lat', 'lng', 'precision', 'verified', 'books')
        slice_places.append({k: p[k] for k in keep if k in p})
    dump_json('gazetteer.json', {'meta': {**payload['meta'], 'strict': strict}, 'places': slice_places})

    # 候选 TSV（缺坐标的待判/真实候选，供人工拾取核验；已有裁定行不覆盖）
    if TSV_RULINGS.parent.exists() is False:
        TSV_RULINGS.parent.mkdir(parents=True, exist_ok=True)
    ruled = set(rulings)
    rows = ['键\tkind\treal\tlat\tlng\tprecision\t裁决\treviewer\t日期']
    todo = [p for p in out_places if p['id'] not in ruled and (p['real'] is not False) and p['status'] != '泛称']
    for p in todo:
        rows.append('\t'.join([p['id'], p['kind'],
                               '' if p['real'] is None else str(int(p['real'])),
                               str(p.get('lat', '')), str(p.get('lng', '')),
                               p.get('precision', ''), '', '', '']))
    (DIR_CUR / 'gazetteer-候选.tsv').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    print(f'-> {DIR_CUR / "gazetteer-候选.tsv"}（待核验 {len(todo)} 行；已有裁定 {len(ruled)} 行不覆盖）')
    return payload


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='工具 D：Gazetteer 地理底座构建器')
    ap.add_argument('--fetch', type=int, default=0, metavar='N', help='向 Nominatim 补拉 N 个缺坐标候选')
    ap.add_argument('--strict', action='store_true', help='站点切片只收 verified 坐标')
    args = ap.parse_args()
    build(args.fetch, args.strict)
