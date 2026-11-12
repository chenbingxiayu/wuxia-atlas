# -*- coding: utf-8 -*-
"""数据说书专栏数据管线 v2（D6 泛化，2026-11-11）——《专栏页重构设计.md》§五 半自动生产管线。

v2 要点（相对 v1 的结构性变化）：
  - STORIES 配置注册表：{story_id: {template, subject, book, rivals?, title, tag}}——
    新增一篇的边际成本 = 选命题 + 加配置 + 写 editorial 文案（设计决策 3）；
  - 统一 story-v2 schema：{meta, story_id, template, editorial{thesis,reads,evidence,method_note,teaser},
    per_chapter, markers, chart}——[slug].astro 单一模板页按五段式渲染（§四）；
  - markers 全部从剧情锚点轨（char_plots.json）取数，markers=该篇主角锚点子集（决策 4 / §七）；
  - known_end 以事件层为准（S4 修正：v1 手写"诛天德上人"误记 → 事件层终局对手"天龙上人"）；
  - 三篇扩编切片（§六）：凌未风/楚昭南（qa-events 七剑 逐回主客计数）、
    吕四娘（qa-events 三女侠 复仇线密度=参与的对抗事件数）；
  - 旧两篇数值零失真迁移：温度/成长切片逻辑与 v1 逐字段一致（golden 测试守护）。

F5 扩编（2026-11-12，用户裁定名物篇解除挂账）：第六篇 wanderer-sword《游龙剑流转记》——
  - template='artifact'（§五 模板注册表预留的第四类，首次落地）；tag='名物'（§十 用户词）；
  - 切片器 slice_artifact：只读 site/data/weapons.json 游龙剑条目（artifacts-v1 · rev17 编年序）——
    per_chapter=chain 明文事件序列（夺/赠/毁，suspect 毁边折叠标注）、markers=dir 方向边关键流转点
    （名物数据自带，非锚点表口径）、holders/makers/end_state 原样引用不增删；
  - chart.kind='flow'：横向流转时间线图纸（书泳道 + verb 节点 + dir 边箭头文案），[slug].astro 渲染；
  - book 字段=主书'七剑下天山'（gate/回目链接主口径）；跨书事实由切片 summary（books_in_order/n_books）
    与 editorial method_note 说明——链末一段入三女侠 24:15，全条目覆盖白发/塞外/七剑/三女侠四书。

数据源分工：白发两篇沿用 atlas 切片（v1 口径不变）；三篇新文按任务口径读
site/data/qa-events/<书>.json（subject/object 统计）；名物篇读 site/data/weapons.json。
数据源文件缺失 → 该篇诚实跳过（宁缺毋滥）。

落盘约定（esc 统一纪律）：默认 dry-run 写 wuxia-kb/logs/export/staging/；
--apply 才写 site/data/stories/（先整目录备份到 backup/site_data/stories/）。
用法：python scripts/build_stories.py [--scope tianshan-demo] [--apply]
"""
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import SITE_DATA, today  # noqa: E402

# W0-T3b：scope 基础设施复用（export_site_common 在 wuxia-kb/scripts，import 胜过复制）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / 'wuxia-kb' / 'scripts'
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402

try:
    from kb_discovery import KB  # noqa: E402
except Exception:
    KB = Path(__file__).resolve().parents[1] / 'kb'

BOOK = '白发魔女传'  # atlas 切片书（v1 两篇的数据源，向后兼容）
OUT = SITE_DATA / 'stories'

# ================================================================ 配置注册表（§五：模板 + 数据切片参数）
# 新增一篇 = 此处加一条 + EDITORIAL 加一段文案。tag 用用户词（关系/成长/势力/名物）。
STORIES = {
    'temperature-curve': {
        'template': 'relation', 'subject': '卓一航', 'rivals': ['练霓裳'],
        'book': '白发魔女传', 'title': '一夜白头：卓练温度曲线', 'tag': '关系', 'order': 1,
    },
    'growth-curve': {
        'template': 'growth', 'subject': '卓一航',
        'book': '白发魔女传', 'title': '武功食物链：卓一航成长曲线', 'tag': '成长', 'order': 2,
    },
    'ling-weifeng': {
        'template': 'growth', 'subject': '凌未风',
        'book': '七剑下天山', 'title': '囚徒十年：凌未风主客曲线', 'tag': '成长', 'order': 3,
    },
    'chu-zhaonan': {
        'template': 'growth', 'subject': '楚昭南',
        'book': '七剑下天山', 'title': '堕落曲线：楚昭南主客下滑', 'tag': '成长', 'order': 4,
    },
    'lv-siniang': {
        'template': 'growth', 'subject': '吕四娘', 'chart': 'density',
        'book': '江湖三女侠', 'title': '刺雍正：吕四娘复仇线密度', 'tag': '成长', 'order': 5,
    },
    # F5 名物篇（§五 artifact 模板落地）：book=主书（gate/回目链接主口径），跨书流转见切片 summary
    'wanderer-sword': {
        'template': 'artifact', 'subject': '游龙剑',
        'book': '七剑下天山', 'title': '游龙剑流转记：名物的流传比人长寿', 'tag': '名物', 'order': 6,
    },
}

POS_VERBS = {'救', '护', '赠', '送', '谢', '助', '寻', '访', '疗', '医', '陪', '安慰', '挡'}
NEG_VERBS = {'刺', '杀', '伤', '斥', '逐', '拒', '擒', '捉', '扣', '逼', '追', '罚', '掳', '胁'}
POS_KW = ['相救', '暗中', '心软', '柔情', '深情', '关切', '心爱', '爱慕', '喜', '谢', '赠']
NEG_KW = ['误会', '冷笑', '负心', '绝情', '斥', '怒', '泪', '恨', '悔']


# ================================================================ 锚点表取数（决策 4 / §七）
def markers_for(persons, book) -> list:
    """剧情锚点轨（char_plots.json）→ 该篇主角锚点子集。

    只取 book 内锚点；loc 去重（双人共有的同一事件只记一次）；按回排序。
    锚点轨未就绪时诚实返回空表（图表无注记线，同 v1 纪律）。
    """
    try:
        cp = json.loads((SITE_DATA / 'char_plots.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    out, seen = [], set()
    for person in persons:
        plots = (cp.get('characters', {}).get(person) or {}).get('plots') or []
        for p in plots:
            if (p.get('book') or '').strip() != book:
                continue
            loc = (p.get('loc') or '').strip()
            m = re.fullmatch(r'(\d{3}):(\d{3})', loc)
            if not m or not p.get('name') or loc in seen:
                continue
            seen.add(loc)
            out.append({'c': int(m.group(1)), 'label': p['name'], 'loc': loc})
    out.sort(key=lambda x: (x['c'], x['loc']))
    return out


# ================================================================ scope / meta（W0-T3b 契约沿用）
def story_enabled(book, scope=None) -> bool:
    """专栏书 gate：全量口径恒 True；scope 口径按书 ∈ scope。"""
    return esc.in_scope(book, scope)


def story_meta(scope=None) -> dict:
    """专栏 payload 公共 meta（schema story-v2；scope 口径 meta 加 scope/books）。"""
    meta = {'generated': today(), 'schema': 'story-v2', 'script': 'scripts/build_stories.py',
            'copyright': 'L0：计数+定位符；摘录仅本地使用，不入切片'}
    smeta = esc.scope_meta(scope)
    if smeta:
        meta.update(smeta)
    return meta


# ================================================================ 事件层装载
def load_events():
    """白发魔女传 atlas 切片（v1 两篇数据源，v1 口径不变）。"""
    s = json.loads((SITE_DATA / 'atlas' / f'{BOOK}.json').read_text(encoding='utf-8'))
    return s


def _atlas_events(slice_):
    """atlas 切片 → (events_by_chapter, chapter_domain)。"""
    events = {int(k): v for k, v in (slice_.get('events') or {}).items()}
    domain = list(range(1, (slice_.get('chapters') or 0) + 1))
    return events, domain


def _qa_events(book):
    """qa-events/<书>.json → (events_by_chapter, chapter_domain)；文件缺失 → None（诚实跳过）。"""
    p = SITE_DATA / 'qa-events' / f'{book}.json'
    if not p.exists():
        return None
    evs = json.loads(p.read_text(encoding='utf-8')).get('events') or []
    events = defaultdict(list)
    lo = hi = None
    for e in evs:
        m = re.fullmatch(r'(\d{3})', (e.get('l') or '')[:3])
        if not m:
            continue
        c = int(m.group(1))
        events[c].append(e)
        lo = c if lo is None else min(lo, c)
        hi = c if hi is None else max(hi, c)
    if lo is None:
        return None
    return dict(events), list(range(lo, hi + 1))


def load_weapon(canonical):
    """weapons.json 名物条目（只读，F5 名物篇数据源）；文件缺失/无该条目 → None（诚实跳过）。"""
    p = SITE_DATA / 'weapons.json'
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return next((w for w in d.get('weapons') or [] if w.get('canonical') == canonical), None)


def _pad_loc(loc: str) -> str:
    """'5:7' → '005:007'（weapons chain loc 为短式；切片统一 3:3 定位符，与证据链同式样）。"""
    a, sep, b = (loc or '').partition(':')
    if not sep or not a.isdigit() or not b.strip().isdigit():
        return ''
    return f'{int(a):03d}:{int(b):03d}'


# flow verb → 事件名/色（L0 标签：机械转写 verb，不发明叙事）
FLOW_VERB_LABEL = {'夺': '夺剑', '赠': '赠剑', '传': '传剑', '还': '还剑', '失': '失剑',
                   '借': '借剑', '毁': '毁记', '铸': '铸剑'}
FLOW_VERB_COLOR = {'夺': '#a23527', '赠': '#31536c', '传': '#31536c', '还': '#31536c',
                   '毁': '#8a8172'}
FLOW_VERB_LEGEND = {'夺': '夺：武力易手', '赠': '赠／传：师门授受', '毁': '毁：存疑折叠（证伪）'}


def slice_artifact(weapon) -> dict:
    """名物流转切片（F5）：weapons.json 条目 → 五段式数据侧。

    口径（名物谱，与 weapons 页同源）：
      - per_chapter 行 = chain 明文事件（rev17 编年序 seq）：夺/赠/毁；suspect 毁边折叠标注（存疑）；
      - frm/to 仅 dir 方向边有值——无方向不推断归属（名物谱红线）；
      - markers = dir 方向边关键流转点（weapons 数据自带，非锚点表口径）；
      - holders/makers/end_state/borrowers 原样引用不增删；计数全部实算进 summary（决策 5）。
    """
    rows, dir_edges = [], []
    for e in weapon.get('chain') or []:
        loc = _pad_loc(e.get('loc') or '')
        m = re.fullmatch(r'(\d{3}):(\d{3})', loc)
        if not m:
            continue
        d = e.get('dir') or None
        verb = e.get('verb') or ''
        name = FLOW_VERB_LABEL.get((d or {}).get('kind') or verb, verb)
        if e.get('suspect'):
            name += '（存疑）'
        persons = list(e.get('persons') or [])
        row = {'c': len(rows) + 1, 'seq': len(rows) + 1, 'book': e.get('book') or '',
               'ch': int(m.group(1)), 'line': int(m.group(2)), 'loc': loc, 'verb': verb,
               'persons': persons, 'name': name, 'suspect': bool(e.get('suspect')),
               'conf': e.get('conf') or '', 'w': len(persons) or 1}
        if d and d.get('kind') and len(d.get('who') or []) == 2:
            row['dir'] = {'kind': d['kind'], 'who': list(d['who']),
                          'label': f"{d['who'][0]} → {d['kind']} → {d['who'][1]}"}
            row['frm'], row['to'] = d['who'][0], d['who'][1]
            dir_edges.append({'seq': row['seq'], 'kind': d['kind'], 'who': list(d['who']),
                              'label': row['dir']['label'], 'loc': loc})
        else:
            row['frm'] = row['to'] = None
        rows.append(row)
    books_in_order = list(dict.fromkeys(r['book'] for r in rows))
    summary = {
        'n_chain': len(rows),
        'n_hold': len(weapon.get('holders') or []),
        'n_books': len(weapon.get('books') or {}) or len(books_in_order),
        'n_destroyed': sum(1 for r in rows if r['verb'] == '毁'),
        'n_dir': len(dir_edges),
        'n_transfer': sum(1 for r in rows if r['verb'] in ('夺', '赠', '传', '还')),
        'end_state': (weapon.get('end_state') or {}).get('note', ''),
        'destroyed_locs': '、'.join(r['loc'] for r in rows if r['verb'] == '毁'),
        'books_in_order': books_in_order,
    }
    return {'subject': weapon.get('canonical') or '', 'per_chapter': rows,
            'markers': [{'c': e['seq'], 'label': e['label'], 'loc': e['loc']} for e in dir_edges],
            'edges': dir_edges, 'summary': summary,
            'holders': weapon.get('holders') or [], 'makers': weapon.get('makers') or [],
            'borrowers': weapon.get('borrowers') or [], 'end_state': weapon.get('end_state') or {}}


# ================================================================ 切片器（§五：模板复用的数据切片）
def _kw_cache() -> list:
    """白发事件表摘录缓存（kw 词频扫描用）；按 (路径, mtime) 键控，事件表未就绪 → []。"""
    evf = KB / BOOK / '事件表.json'
    try:
        key = (str(evf), evf.stat().st_mtime_ns)
    except OSError:
        return []
    cache = getattr(slice_relation, '_kw_cache', None)
    if cache is None or cache[0] != key:
        try:
            data = json.loads(evf.read_text(encoding='utf-8')).get('events', [])
        except (OSError, ValueError):
            data = []  # 事件表未就绪 → 诚实计 0（同 v1 纪律）
        cache = (key, data)
        slice_relation._kw_cache = cache
    return cache[1]


def slice_relation(slice_, A, B_):
    """双人共现极性切片——v1 temp_curve 逐字段保留（零失真迁移）。markers 由 _build_one 统一接锚点表。"""
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
        # 摘录情感词（本地扫描；切片只留计数）——缓存按 (路径, mtime) 键控，
        # 测试 monkeypatch KB 换路径后自动重建（进程级函数属性缓存的教训）。
        for e in _kw_cache():
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
    return {'book': slice_.get('title', BOOK), 'a': A, 'b': B_, 'shared_chapters': sorted(shared),
            'per_chapter': [{'c': c, **per[c]} for c in sorted(per)]}


def slice_growth_events(events, person, dossiers, domain) -> dict:
    """逐回主客切片——v1 growth_curve 参数化（白发篇零失真；三篇新文同法）。

    口径：◈◉▲ 事件中 person 为 a（主/发出者）或 b（客/承受者）的逐回计数；
    杀伤 = 动词 ∈ {杀,诛,毙}；对手分量 = 对手档案 appearance_total 均值；
    known_end 以事件层为准（S4 修正）。
    """
    weight = {}
    for d in dossiers.get('dossiers', []):
        weight[d['canonical']] = d.get('appearance_total', 0)
    rows = []
    for c in domain:
        active = passive = kills = 0
        opps = Counter()
        for e in events.get(c, []):
            a_, b_, v, code = e.get('a'), e.get('b'), e.get('v') or '', e.get('code') or ''
            if code not in ('◈', '◉', '▲'):
                continue
            if a_ == person:
                active += 1
                if b_ and b_ != person:
                    opps[b_] += 1
                if v in ('杀', '诛', '毙'):
                    kills += 1
            elif b_ == person:
                passive += 1
                if a_ and a_ != person:
                    opps[a_] += 1
        known = [weight.get(o, 0) for o in opps if weight.get(o, 0)]
        rows.append({'c': c, 'active': active, 'passive': passive,
                     'kills': kills,
                     'opponents': [o for o, _ in opps.most_common(4)],
                     'opp_weight': round(sum(known) / len(known)) if known else 0})
    act = next((r['c'] for r in rows if r['c'] >= 5 and r['active'] > r['passive'] and (r['active'] + r['passive']) >= 3), None)
    first_kill = next((r['c'] for r in rows if r['kills'] > 0), None)
    return {'person': person, 'per_chapter': rows,
            'milestones': {'first_dominant_chapter': act, 'first_kill_chapter': first_kill,
                           'known_end': known_end_of(events, person)}}


def known_end_of(events, person):
    """事件层终局（S4）：最后一个含该人物 ◈◉▲ 事件的回 + 当回对手（按出现次数）。

    以事件层考订为准，替代 v1 手写 known_end（"诛天德上人"误记已修）。
    """
    last_c, opps = None, Counter()
    for c in sorted(events):
        for e in events.get(c) or []:
            if e.get('code') not in ('◈', '◉', '▲'):
                continue
            a_, b_ = e.get('a'), e.get('b')
            if person not in (a_, b_):
                continue
            if last_c is None or c > last_c:
                last_c, opps = c, Counter()
            other = b_ if a_ == person else a_
            if other and other != person:
                opps[other] += 1
    if last_c is None:
        return None
    tops = [o for o, _ in opps.most_common(4)] or ['—']
    return f'{last_c:03d} 回 · 终局对手：{"、".join(tops)}'


# ================================================================ editorial（人工文案轨；{stat} 为实算占位）
# 文案纪律（§四）：命题与读图为原创编辑内容（L0）；不引原文段落；术语保留在方法段。
# 占位符一律由切片实算数字填充——teaser 数字来自切片（决策 5）。
_EDITORIAL = {
    'temperature-curve': {
        'thesis': '卓练之间正面互动事件为 0 起——全书 {n_chapters} 回、{total_co} 起同场事件、'
                  '{total_neg} 起冲突中，温情从未进入事件量级。',
        'reads': [
            {'q': '为什么正面事件是 0？',
             'a': '事件层收录的是人物—动词—人物的叙事动作（救/赠/护也未出现于二人之间）；'
                  '卓练之间发生的只有 捉、扣、刺、避。温情发生在动词够不着的地方：'
                  '029 回银针杀雷蒙救卓，事件登记为杀，温度藏在宾语之外。'},
            {'q': '峰值在 004–006 与 013？',
             'a': '前者是玉罗刹 domination 期（黄龙洞缴械、武当对峙），后者是重逢与弹弓误会——'
                  '两段高冲突都不是感情破裂，而是感情的存在证明。冲突密度 = 关系强度，'
                  '这是曲线最反直觉的读法。'},
            {'q': '026 之后呢？',
             'a': '一夜白头后冲突骤降（028–032 均值不到前期一半）——不是和好，是退出彼此的事件。'
                  '只剩关键词：029 一粒温情词，031 一记刺。'},
        ],
        'evidence': [
            {'loc': '003:081', 'text': '练霓裳 捉 卓一航（黄龙洞段）'},
            {'loc': '008:011', 'text': '卓一航 刺 练霓裳'},
            {'loc': '018:095', 'text': '练霓裳 扣 卓一航（明月峡）'},
            {'loc': '026:053', 'text': '秘魔崖一夜白头（全书转折）'},
            {'loc': '031:203', 'text': '练霓裳 刺 卓一航（塞外）'},
        ],
        'method_note': '口径：同章在场 = 登记表 chapters 交集（{shared} 回）；互动动词极性词表'
                       '（正 13 词/负 14 词）与摘录情感词表（正 11 词/负 9 词）见脚本头注释；'
                       '考订锚点 001/003/008/018/026/031 全部挂定位符（markers 自剧情锚点表取数）。'
                       '摘录仅在本地扫描，切片只含计数与定位符（L0）。',
        'teaser': '事件层里的卓练：全书 {n_chapters} 回、{shared} 回同场、{total_neg} 起冲突——'
                  '而温情事件是 {total_pos} 起。嘴上说放下的那个人，温情只藏在关键词与并肩的对手里。',
    },
    'growth-curve': {
        'thesis': '卓一航的武功长进是主客比翻转出来的：第 {first_dominant} 回起主动持续压过被动——'
                  '而开篇的他是被捉、被围的承受者，不是旁白说他变强了。',
        'reads': [
            {'q': '主客翻转发生在第几回？',
             'a': '第 {first_dominant} 回。此前的卓一航是事件表里的承受者（被捉、被围、被追）；'
                  '第 26 回是全书最低谷：武当四老围攻，主 1 客 3；第 29 回是最高峰：'
                  '主动 {peak_a} 次、杀伤 {peak_kills}（雷蒙法师等）——恰是三敌一支撑的塞外血战。'},
            {'q': '收官那一战呢？',
             'a': '第 32 回主 4 客 9：他面对全书最高密度的压力，但这一次的客是与他战平的'
                  '成章五、天龙上人——同样是被打，性质已经不同（known_end 以事件层为准）。'},
            {'q': '对手分量说明什么？',
             'a': '虚线在 026 回冲高：他的对手从散兵变成了有档案分量的人物（黄叶道人、红云道人）。'
                  '食物链的位置 = 你对手的分量，这条线与主客线的交叉就是成长四个字的全部数据内容。'},
        ],
        'evidence': [
            {'loc': '003:081', 'text': '黄龙洞缴械：开篇即被单手缴剑——承受者期的起点'},
            {'loc': '018:095', 'text': '明月峡被扣：主客翻转之前，他仍是事件表里的承受者'},
            {'loc': '026:053', 'text': '一夜白头之夜：本回主 1 客 3，全书最低谷'},
            {'loc': '031:203', 'text': '塞外一刺：旧关系的余波落在成长曲线的尾段'},
        ],
        'method_note': '口径：◈◉▲ 事件（含 medium/low，不含 dropped）中卓一航为主/客的逐回计数；'
                       '对手分量 = 对手档案 appearance_total 均值（√ 缩放）；不做胜/负 NLP 判定——'
                       '事件动词极性足以支撑主客口径，胜负词表属武评模块。'
                       '里程碑由脚本从数据计算，非手填；终局（known_end）自 v2 起以事件层为准'
                       '（v1 手写终局对手为误记，已复核修正：032 回事件层实为天龙上人）。',
        'teaser': '第 {first_passive_c} 回被{first_passive_opp}一把捉住，第 {first_dominant} 回主客翻转，'
                  '第 {peak_c} 回主动出击 {peak_a} 次——把武功长进画成可复算的曲线。',
    },
    'ling-weifeng': {
        'thesis': '囚禁把天山最强者的曲线打到归零（26–27 回主客合计 {prisoner_n} 起），'
                  '而他锁前的冰河血战单回主动 {peak_a} 起——最强者的下限，是被锁住也不脱事的耐心。',
        'reads': [
            {'q': '26–27 回为什么几乎是空段？',
             'a': '他被囚在布达拉宫：人不在江湖，事件层近乎静默——26 回 0 起、27 回仅 {prisoner_n} 起。'
                  '曲线的零段就是囚禁的形状，与锚点 025:078 冰崖蒙难、029:008 迷宫脱囚两相扣合。'},
            {'q': '单回主动 {peak_a} 起的高峰说明什么？',
             'a': '第 025 回冰河血战独战师兄楚昭南与四名大内高手，单回主动 {peak_a} 起'
                  '（第 019 回 {second_a} 起次之）——最强者的上限写在被锁之前。'},
            {'q': '出狱之后呢？',
             'a': '28 回的 {ch28_a} 主 {ch28_p} 客是救援夜战，30 回 {ch30_a} 主 {ch30_p} 客接掌天山——'
                  '爆发不在出狱后。这篇说的不是复仇爽感，是被锁十年不脱事的耐心。'},
        ],
        'evidence': [
            {'loc': '025:078', 'text': '冰崖蒙难：旧疾骤发，被楚昭南封穴捆缚生擒'},
            {'loc': '027:007', 'text': '剑诀托付：囚中仍把师父的拳经剑诀留在她手中'},
            {'loc': '029:008', 'text': '迷宫脱囚：义士伪装替死，断镣不忍，活着走出迷宫'},
            {'loc': '030:073', 'text': '衣钵光大：接晦明衣钵掌天山剑派'},
        ],
        'method_note': '口径：qa-events 七剑下天山事件切片（0–30 回全回目域），◈◉▲ 对抗事件按'
                       ' subject/object 逐回计数（主=凌未风为动作发出者，客=承受者）；不做胜负 NLP 判定。'
                       'markers 自剧情锚点表（凌未风·七剑锚点）取数，与曲线零段对照互证。',
        'teaser': '被锁的 26–27 回主客合计 {prisoner_n} 起；锁前的冰河血战单回主动 {peak_a} 起——'
                  '天山最强者的耐心怎么算。',
    },
    'chu-zhaonan': {
        'thesis': '楚昭南的主客曲线逐段下滑：前半程主动率 {r_early}%，收官段跌到 {r_end}%，'
                  '第 {last_c} 回死于被动承受——同一条食物链，师弟向上走，他向下走。',
        'reads': [
            {'q': '主动率下滑是断崖吗？',
             'a': '不是——他始终是一流高手：25 回与对手 10 比 10 打平。下滑的是姿态：'
                  '从前期 {r_early}% 的主动出手，到收官段 {r_end}% 的被动承受。堕落是选择，不是失能。'},
            {'q': '他最后输给谁？',
             'a': '{known_end}——事件层给出 14 起对手事件；锚点 029:079 暗道伏诛，'
                  '死讯由对手平静道出。'},
            {'q': '和师弟凌未风对照是什么形状？',
             'a': '同一条食物链的两种走法：凌未风 19/25 两回单回主动 24 起、被囚归零再出狱掌门；'
                  '楚昭南的曲线只向下——同门双曲线，一个向上一个向下。'},
        ],
        'evidence': [
            {'loc': '001:129', 'text': '石梁助清：一剑斩断锦云兜救下多铎，叛迹初露'},
            {'loc': '004:145', 'text': '粘字诀受制：师弟一剑搭住剑脊，游龙难脱'},
            {'loc': '025:165', 'text': '冰崖擒凌：封穴捆缚凌未风，献俘清廷以博功名'},
            {'loc': '028:069', 'text': '迷宫守囚：布达拉宫里得意于宿敌终成掌中囚'},
            {'loc': '029:079', 'text': '暗道伏诛：败于易兰珠剑下，堕落曲线到头'},
        ],
        'method_note': '口径：qa-events 七剑下天山事件切片（0–30 回全回目域），◈◉▲ 对抗事件按'
                       ' subject/object 逐回计数；主动率 = 主/(主+客)，分段实算（前半 0–14 回 / 收官 28–29 回）；'
                       '不做胜负 NLP 判定。markers 自剧情锚点表（楚昭南·七剑锚点，第二批补录）取数。',
        'teaser': '同一条食物链，师弟向上走，他向下走——主动率从前半程 {r_early}% 跌到收官段 {r_end}%，'
                  '第 {last_c} 回伏诛于被动。',
    },
    'lv-siniang': {
        'thesis': '吕四娘的复仇线密度峰值在第 {peak_c} 回（单回 {peak_n} 起对抗事件），'
                  '而刺雍正的终章只有 {finale_n} 起——复仇是长线积累，最后一击只是收束。',
        'reads': [
            {'q': '密度峰值为什么不在终章？',
             'a': '复仇线的形状是长线积累：08 回师门对决 {ch8_n} 起、20 回大混战 {peak_n} 起才是高峰；'
                  '刺雍正那一夜只有 {finale_n} 起对抗事件——积累越厚，最后一击越干净。'},
            {'q': '20 回的 {peak_n} 起是什么？',
             'a': '毒手害禅师那一回的大混战：她一人卷入全书最高的对抗密度——对手是血滴子与'
                  '大内高手的群战，不是雍正本人。'},
            {'q': '刺雍正的确日是怎么回事？',
             'a': '原著把宫中喋血写在元宵（E-1735：雍正十三年 01-15）；史实里雍正死于八月二十三。'
                  '两个日期并列陈列、不作断言，联动事件年谱（小说中的今天）。'},
        ],
        'evidence': [
            {'loc': '008:051', 'text': '师门对决：与师兄了因斗到酣处——复仇线中段高峰（本回 {ch8_n} 起）'},
            {'loc': '026:047', 'text': '仙霞苦修：五年潜修，复仇线进入低密度积累段'},
            {'loc': '047:001', 'text': 'E-1735 元宵确日：宫中喋血·吕四娘刺雍正——小说纪年雍正十三年 01-15（元宵）；'
                             '史实雍正死于 1735-08-23，并列陈列不作断言', 'annals': True},
            {'loc': '048:041', 'text': '内苑屠龙：传音入密历数罪状，内苑剑光终结暴君（本回 {finale_n} 起）'},
        ],
        'method_note': '口径：qa-events 江湖三女侠事件切片（1–48 回），吕四娘参与的 ◈◉▲ 对抗事件'
                       '逐回计数（密度 = 主+客）；不做胜负 NLP 判定。确日联动：史实锚年谱 E-1735'
                       '（元宵宫中喋血 01-15 / 雍正之死 08-23）并列陈列，不作断言。'
                       'markers 自剧情锚点表（吕四娘锚点）取数。',
        'teaser': '刺雍正那一天，原著写明了日期（雍正十三年 01-15 元宵）——复仇线的密度峰值却在'
                  '第 {peak_c} 回的 {peak_n} 起，终章只有 {finale_n} 起。',
    },
    # F5 名物篇（文案为 agent 原创生成，L0：计数+定位符，不引原文段落；数字全部实算占位）
    'wanderer-sword': {
        'thesis': '一柄剑，跨 {n_books} 部书、{n_chain} 段明文事件：{n_hold} 任持有者轮番上场，'
                  '{n_destroyed} 次「毁」的记载全部被毁后的明文出场证伪——'
                  '在名物的谱系里，流传比人长寿，没有一段记载能让这柄剑退场。',
        'reads': [
            {'q': '{n_destroyed} 次「毁剑」的记载，为什么被折叠成存疑边？',
             'a': 'rev17 的核查口径是「毁而不终则不立」：{destroyed_locs} 四条毁边之后，'
                  '剑都再次明文出场——四次毁记因此全部被证伪：最后一次毁记在七剑第 7 回，'
                  '第 14 回它又以师门亲传的身份回到明文里，直到三女侠 47 回仍在人手。'
                  '名物页把存疑毁边折出主线，本篇沿用同一口径：毁记入链、标注存疑，不当作事实。'},
            {'q': '《白发》里借它试过招的人，为什么不在持有者名单里？',
             'a': '名物谱的口径：持有由明文易手句式（铸／夺／赠／传）建立归属；'
                  '拿在手里用一招是暂持，不入谱——白发 28 回那场借剑试招，'
                  '发生在岳鸣珂（晦明禅师）持有期内，只算持有链上的一个瞬间。'
                  '借也要明文句式才立账：本条目 borrowers 为空，图谱不靠推断补名录。'},
            {'q': '最终归宿为什么写「末见持有」，而不是「永久归属」？',
             'a': '图谱只记明文：语料末章（三女侠·47 回）这柄剑仍明文在场，记作「末见持有」；'
                  '语料之外、回目之后的事，推不出来就不写。注记里与唐晓澜并列的楚昭南，'
                  '其名在该书出自追述性提及（001／002／011 回），他的持有段在《七剑》——'
                  '末见持有是索引级口径，不是叙事级断言，更不做「传家有序」的推断。'},
        ],
        'evidence': [
            {'loc': '028:025', 'book': '白发魔女传',
             'text': '铸与定名：晦明禅师（岳鸣珂）重铸师门双剑，长剑得「游龙」之名——'
                     '铸者即首任持有者，剑名自此入谱'},
            {'loc': '005:007', 'book': '七剑下天山',
             'text': '方向边·夺：凌未风 → 楚昭南——入谱第一段易手，游龙自师兄手中夺回'},
            {'loc': '006:065', 'book': '七剑下天山',
             'text': '连环段之始：同回随后并存 3 条毁记（006:069／125／139）——易手与毁记交织的第 6 回'},
            {'loc': '007:123', 'book': '七剑下天山',
             'text': '最后一次毁记（存疑）：此后 014:025／023:037／024:015 连续明文出场——毁而不终的直证'},
            {'loc': '014:025', 'book': '七剑下天山',
             'text': '方向边·传：晦明禅师 → 楚昭南——14:25 双行裁订，长剑游龙归楚昭南'},
            {'loc': '024:015', 'book': '江湖三女侠',
             'text': '方向边·夺：冯瑛 → 车辟邪——跨书流转的末段；归属经 F6 裁订随边迁移挂游龙剑'},
        ],
        'method_note': '口径：切片自 site/data/weapons.json 游龙剑条目（artifacts-v1 · rev17 编年序）——'
                       'per_chapter=chain 明文事件序列（夺／赠／毁，存疑毁边折叠标注），'
                       'markers=方向边关键流转点（名物数据自带，非锚点表口径）；'
                       'holders／makers／end_state 原样引用不增删，borrowers 为空如实呈现；'
                       '流转方向以 kb/校订/名物流转方向.tsv 人工裁订为准（14:25 双行按长短剑各归其器、'
                       '24:15 自断玉剑随边迁移），图谱不做「永久归属」推断。'
                       '（跨书说明：book=主书七剑下天山；链末一段入三女侠 24 回，'
                       '全条目覆盖白发／塞外／七剑／三女侠四书）',
        'teaser': '1 柄剑 · {n_hold} 任持有者 · {n_chain} 段明文跨 {n_books} 书 · '
                  '{n_destroyed} 次毁记无一成立——名物的流转比人长寿。',
    },
}


def _stats_for(sid, data) -> dict:
    """editorial 占位符的实算数字（决策 5：teaser/证据数字来自切片）。"""
    rows = data['per_chapter']
    if sid == 'temperature-curve':
        return {
            'n_chapters': len(rows),
            'shared': len(data['shared_chapters']),
            'total_co': sum(r['co_events'] for r in rows),
            'total_neg': sum(r['neg'] for r in rows),
            'total_pos': sum(r['pos'] for r in rows),
        }
    if sid == 'growth-curve':
        peak = max(rows, key=lambda r: (r['active'], r['kills'], r['c']))
        fp = next((r for r in rows if r['passive'] > 0), None) or max(rows, key=lambda r: (r['passive'], r['c']))
        return {'first_dominant': data['milestones']['first_dominant_chapter'],
                'peak_c': peak['c'], 'peak_a': peak['active'], 'peak_kills': peak['kills'],
                'first_passive_c': fp['c'],
                'first_passive_opp': (fp['opponents'] or ['——'])[0]}
    if sid == 'ling-weifeng':
        peak_a = max(r['active'] for r in rows)
        second_a = max((r['active'] for r in rows if r['active'] < peak_a), default=0)
        rd = rows_dict(rows)
        return {'prisoner_n': rd[26]['active'] + rd[26]['passive'] + rd[27]['active'] + rd[27]['passive'],
                'peak_a': peak_a, 'second_a': second_a,
                'ch28_a': rd[28]['active'], 'ch28_p': rd[28]['passive'],
                'ch30_a': rd[30]['active'], 'ch30_p': rd[30]['passive']}
    if sid == 'chu-zhaonan':
        def ratio(cs):
            a = sum(r['active'] for r in rows if r['c'] in cs)
            p = sum(r['passive'] for r in rows if r['c'] in cs)
            return round(a / (a + p) * 100) if (a + p) else 0
        last_c = max(r['c'] for r in rows if r['active'] + r['passive'] > 0)
        return {'r_early': ratio(set(range(0, 15))), 'r_end': ratio({28, 29}), 'last_c': last_c,
                'known_end': data['milestones']['known_end'] or '终局见事件层'}
    if sid == 'lv-siniang':
        peak = max(rows, key=lambda r: r['total'])
        return {'peak_c': peak['c'], 'peak_n': peak['total'],
                'finale_n': rows[-1]['total'],
                'ch8_n': rows_dict(rows)[8]['total']}
    if sid == 'wanderer-sword':
        s = data['summary']  # 名物篇数字全部来自切片 summary（实算，决策 5）
        return {'n_chain': s['n_chain'], 'n_hold': s['n_hold'], 'n_books': s['n_books'],
                'n_destroyed': s['n_destroyed'], 'n_dir': s['n_dir'],
                'n_transfer': s['n_transfer'], 'destroyed_locs': s['destroyed_locs'],
                'end_state': s['end_state'] or '末见持有见名物页'}
    return {}


def rows_dict(rows):
    return {r['c']: r for r in rows}


def editorial_for(sid, data) -> dict:
    """人工文案 + 实算数字（editorial 轨；缺失文案的篇目诚实报错——五段缺一不成篇）。"""
    tpl = _EDITORIAL.get(sid)
    if not tpl:
        raise KeyError(f'{sid} 缺 editorial 文案（五段式缺一不成篇）')
    stats = _stats_for(sid, data)
    stats = {k: ('—' if v is None else v) for k, v in stats.items()}  # 合成/空切片下诚实降级

    def fmt(s):
        return s.format(**stats) if isinstance(s, str) else s

    ed = {'thesis': fmt(tpl['thesis']),
          'reads': [{'q': fmt(qa['q']), 'a': fmt(qa['a'])} for qa in tpl['reads']],
          'evidence': [{**ev, 'text': fmt(ev['text'])} for ev in tpl['evidence']],
          'method_note': fmt(tpl['method_note']) + ' 复跑：python scripts/build_stories.py --scope tianshan-demo --apply · 图表为构建期 SVG，可整体复现。',
          'teaser': fmt(tpl['teaser'])}
    return ed


# ================================================================ chart spec（数据驱动 SVG 的图纸）
def chart_spec(sid, cfg, data) -> dict:
    """[slug].astro 构建期 SVG 的渲染图纸：系列/图例/注记全部来自数据，页面不硬编码回数。"""
    rows = data['per_chapter']
    if cfg['template'] == 'artifact':
        # F5 flow 图纸：横向流转时间线——书泳道 + verb 节点 + dir 边箭头文案（who → kind → who）
        legend = []
        for r in rows:
            if r['verb'] not in {l['verb'] for l in legend}:
                legend.append({'verb': r['verb'], 'color': FLOW_VERB_COLOR.get(r['verb'], '#8a8172'),
                               'label': FLOW_VERB_LEGEND.get(r['verb'], r['verb'])})
        nodes = [{'seq': r['seq'], 'lane': r['book'], 'verb': r['verb'], 'name': r['name'],
                  'loc': r['loc'], 'suspect': r['suspect'],
                  'color': FLOW_VERB_COLOR.get(r['verb'], '#8a8172'),
                  'dir': next((e for e in data['edges'] if e['seq'] == r['seq']), None)}
                 for r in rows]
        return {'kind': 'flow', 'nodes': nodes, 'edges': data['edges'],
                'lanes': [{'book': b} for b in data['summary']['books_in_order']],
                'legend': legend, 'end_state': data['summary']['end_state'],
                'title': f"{cfg['subject']}编年流转线（{len(rows)} 段明文 · rev17）"}
    if cfg['template'] == 'relation':
        total_co = sum(r['co_events'] for r in rows)
        total_neg = sum(r['neg'] for r in rows)
        return {'kind': 'relation',
                'series': [{'key': 'co_events', 'label': f'同场事件（二人共同参与，{total_co} 起）',
                            'color': '#31536c', 'area': True},
                           {'key': 'neg', 'label': f'负面/对抗事件（{total_neg} 起）',
                            'color': '#a23527', 'width': 2.2}],
                'bands': [{'pos': 'kw_pos', 'neg': 'kw_neg',
                           'label': '下带：温情/悲情关键词密度（本地词频）'}],
                'title': '卓练逐回共现与冲突曲线'}
    if cfg.get('chart') == 'density':
        return {'kind': 'density',
                'series': [{'key': 'total', 'label': '复仇线密度（主+客对抗事件）', 'color': '#a63a2b'}],
                'dots': {'key': 'kills', 'label': '杀伤', 'color': '#a23527'},
                'title': f"吕四娘逐回复仇线密度（《{cfg['book']}》）"}
    series = [{'key': 'active', 'label': f'主动（{cfg["subject"]}为动作发出者）', 'color': '#31536c', 'width': 2.2},
              {'key': 'passive', 'label': '被动（承受者）', 'color': '#8a8172', 'width': 1.8}]
    if any(r['opp_weight'] for r in rows):
        series.append({'key': 'opp_weight', 'label': '对手分量（√出场量，虚线）',
                       'color': '#8a8172', 'dashed': True, 'scale': 'sqrt', 'width': 1.2})
    annotations = []
    ms = data.get('milestones') or {}
    if ms.get('first_dominant_chapter'):
        annotations.append({'c': ms['first_dominant_chapter'], 'color': '#b8860b',
                            'label': f"主客翻转（第 {ms['first_dominant_chapter']} 回）", 'anchor': 'start'})
    if ms.get('first_kill_chapter'):
        annotations.append({'c': ms['first_kill_chapter'], 'color': '#a23527',
                            'label': f"首次杀伤（第 {ms['first_kill_chapter']} 回）", 'anchor': 'end'})
    return {'kind': 'growth', 'series': series,
            'dots': {'key': 'kills', 'label': '杀伤', 'color': '#a23527'},
            'annotations': annotations,
            'title': f"{cfg['subject']}逐回主动/被动交战曲线"}


# ================================================================ 组装
def _build_one(sid, cfg, slice_, dossiers, scope, markers_in):
    if cfg['template'] == 'relation':
        data = slice_relation(slice_, cfg['subject'], (cfg.get('rivals') or [''])[0])
    elif cfg['template'] == 'artifact':
        weapon = load_weapon(cfg['subject'])
        if weapon is None:
            return None  # 名物数据源未就绪 → 诚实跳过（宁缺毋滥）
        data = slice_artifact(weapon)  # markers 自带（dir 方向边），不走锚点表
    else:
        if cfg['book'] == BOOK:
            events, domain = _atlas_events(slice_)
        else:
            got = _qa_events(cfg['book'])
            if got is None:
                return None  # 事件层未就绪 → 诚实跳过（宁缺毋滥）
            events, domain = got
        data = slice_growth_events(events, cfg['subject'], dossiers, domain)
        if cfg.get('chart') == 'density':
            for r in data['per_chapter']:
                r['total'] = r['active'] + r['passive']
    if markers_in is None and cfg['template'] != 'artifact':
        data['markers'] = markers_for([cfg['subject']] + list(cfg.get('rivals') or []), cfg['book'])
    payload = {'meta': story_meta(scope), 'story_id': sid, 'template': cfg['template'],
               'title': cfg['title'], 'tag': cfg['tag'], 'book': cfg['book'], 'order': cfg['order'],
               'subject': cfg['subject'], **data,
               'editorial': editorial_for(sid, data), 'chart': chart_spec(sid, cfg, data)}
    return payload


def story_payloads(slice_, dossiers, scope=None, markers=None) -> list:
    """五篇专栏 payload（v2 统一出口）。

    markers None → 各篇按锚点表取数（正式管线）；注入（如 []）→ 全部用注入值（测试兼容 v1 签名）。
    scope 口径：篇目书 ∈ scope 才产出（W0-T3b 契约）；新篇事件层文件缺失 → 诚实跳过。
    """
    out = []
    for sid, cfg in STORIES.items():
        if not story_enabled(cfg['book'], scope):
            continue
        p = _build_one(sid, cfg, slice_, dossiers, scope, markers)
        if p is not None:
            out.append((sid, p))
    return out


# ================================================================ 落盘（esc 纪律：dry-run staging / --apply 备份直写）
def main() -> int:
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    slice_ = load_events()
    dossiers = json.loads((SITE_DATA / 'dossiers.json').read_text(encoding='utf-8'))
    payloads = story_payloads(slice_, dossiers, scope=scope)
    if not payloads:
        print('scope 口径：无在册专栏书 ∈ scope，跳过专栏产出')
        return 0
    new_names = {f'{sid}.json' for sid, _ in payloads}
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if esc.is_apply():
        backup_dir = esc.BACKUP_ROOT / 'stories'
        OUT.mkdir(parents=True, exist_ok=True)
        legacy = [p for p in sorted(OUT.glob('*.json')) if p.name not in new_names]
        if legacy or any(OUT.joinpath(n).exists() for n in new_names):
            backup_dir.mkdir(parents=True, exist_ok=True)
            for p in sorted(OUT.glob('*.json')):
                shutil.copy2(p, backup_dir / f'{p.name}.bak-{stamp}')
            print(f'[backup] 旧产物 -> {backup_dir}/（.bak-{stamp}）')
        for p in legacy:
            p.unlink()
            print(f'[retire] 旧件移除（已备份）：{p.name}')
        for sid, payload in payloads:
            target = esc.atomic_write_json(payload, OUT / f'{sid}.json')
            print(f'-> {target} ({target.stat().st_size // 1024} KB)')
    else:
        for sid, payload in payloads:
            staged = esc.atomic_write_json(payload, esc.STAGING / f'{sid}.json')
            print(f'-> {staged}（dry-run；--apply 写 {OUT}/{sid}.json）')
    print(f'篇目 {len(payloads)}：' + '、'.join(sorted(new_names)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
