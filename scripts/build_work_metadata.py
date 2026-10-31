# -*- coding: utf-8 -*-
"""P0：作品元数据表生成。

① 从 章回版/ 实测每部回数、字数（非空白字符）；
② 合并互文引用表（authorial+quoted 计出入边，bare 单列）；
③ 合并人工考订的文献字段（初刊年/背景年代/系列/主角），
   其中主角候选一律回语料验证出场，分级 ok / presence / todo；
④ 汇出 kb/作品元数据表.json / .md，含作者亲证连载接力边与待考清单。

用法：python scripts/build_work_metadata.py
"""
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZH = ROOT / '章回版'
KB = ROOT / 'kb'

# ---------------------------------------------------------------------------
# 人工考订字段（candidates 由脚本回语料验证出场后定级）
# year_conf: verified=2026-10-31 检索核实 / approx=通行年表，待复核
# era/series/leads_conf: ok=较高把握 / presence=出场已证实、主角身份待确认 / todo=待考
# ---------------------------------------------------------------------------
E = {
    '龙虎斗京华':   dict(year=1954, ord=1, yconf='verified', era='清末·庚子事变前后', eok=1, series='晚清民国', sok=1, leads=['柳梦蝶', '娄无畏', '丁晓']),
    '草莽龙蛇传':   dict(year=1954, ord=2, yconf='verified', era='清末民初', eok=1, series='晚清民国', sok=1, leads=['丁晓']),
    '塞外奇侠传':   dict(year=1955, yconf='verified', era='清初·顺治—康熙间', eok=0, series='天山系列', sok=1, leads=['杨云骢', '纳兰明慧', '飞红巾']),
    '七剑下天山':   dict(year=1956, yconf='verified', era='清·康熙', eok=1, series='天山系列', sok=1, leads=['凌未风', '易兰珠']),
    '白发魔女传':   dict(year=1957, yconf='verified', era='明末·万历—崇祯（001回梃击案=万历四十三年）', eok=1, series='天山系列', sok=1, leads=['卓一航', '练霓裳']),
    '江湖三女侠':   dict(year=1957, yconf='approx', era='清·雍正', eok=1, series='天山系列', sok=1, leads=['吕四娘', '冯瑛', '冯琳']),
    '萍踪侠影录':   dict(year=1959, yconf='verified', era='明·正统—景泰（土木堡之变前后）', eok=1, series='明代系列', sok=1, leads=['张丹枫', '云蕾']),
    '冰川天女传':   dict(year=1959, yconf='verified', era='清·乾隆', eok=1, series='天山系列', sok=1, leads=['唐经天', '桂冰娥']),
    '还剑奇情录':   dict(year=1959, yconf='verified', era='元末明初', eok=1, series='明代系列·序篇', sok=1, leads=['陈玄机']),
    '散花女侠':     dict(year=1960, yconf='verified', era='明·景泰后', eok=1, series='明代系列', sok=1, leads=['于承珠', '铁镜心']),
    '冰魄寒光剑':   dict(year=1960, yconf='verified', era='清·康熙—雍正间（待考）', eok=0, series='天山系列', sok=1, leads=['桂华生']),
    '女帝奇英传':   dict(year=1961, yconf='verified', era='唐·武周', eok=1, series='唐代·武周篇（独立）', sok=1, leads=['李逸', '武玄霜', '上官婉儿']),
    '联剑风云录':   dict(year=1961, yconf='approx', era='明·成化', eok=1, series='明代系列', sok=1, leads=['张玉虎', '龙剑虹']),
    '云海玉弓缘':   dict(year=1961, yconf='verified', era='清·乾隆', eok=1, series='天山系列', sok=1, leads=['金世遗', '厉胜男', '谷之华']),
    '冰河洗剑录':   dict(year=1963, yconf='approx', era='清·乾隆末（待考）', eok=0, series='天山系列', sok=1, leads=['江海天']),
    '大唐游侠传':   dict(year=1963, yconf='verified', era='唐·天宝（安史之乱）', eok=1, series='大唐三部曲', sok=1, leads=['段珪璋', '南霁云', '铁摩勒']),
    '龙凤宝钗缘':   dict(year=1964, yconf='approx', era='唐·安史乱后', eok=1, series='大唐三部曲', sok=1, leads=['段克邪', '史若梅']),
    '狂侠天骄魔女': dict(year=1964, yconf='approx', era='南宋·孝宗—光宗间（辛弃疾时代）', eok=1, series='宋代系列', sok=1, leads=['柳清瑶', '华谷涵', '檀羽冲']),
    '慧剑心魔':     dict(year=1966, yconf='approx', era='唐·代宗—德宗间（待考）', eok=0, series='大唐三部曲', sok=1, leads=['展伯承']),
    '飞凤潜龙':     dict(year=1966, yconf='approx', era='待考（穴道铜人来历，见武林天骄·007）', eok=0, series='宋代系列（互文实证）', sok=1, leads=[]),
    '瀚海雄风':     dict(year=1966, yconf='approx', era='南宋末·嘉定（成吉思汗崛起）', eok=1, series='宋代系列', sok=1, leads=['李思南', '杨婉']),
    '鸣镝风云录':   dict(year=1966, yconf='approx', era='南宋·开禧前后（待考）', eok=0, series='宋代系列', sok=1, leads=['谷啸风']),
    '风雷震九州':   dict(year=1967, yconf='approx', era='清·嘉庆（天理教林清事，见侠骨丹心·051 回指）', eok=1, series='天山系列', sok=1, leads=[]),
    '风云雷电':     dict(year=1970, yconf='approx', era='南宋中后期（承鸣镝风云录）', eok=0, series='宋代系列', sok=1, leads=['风天扬']),
    '武林天骄':     dict(year=1970, yconf='approx', era='宋（檀羽冲时代，待考）', eok=0, series='宋代系列', sok=1, leads=['檀羽冲']),
    '侠骨丹心':     dict(year=1971, yconf='approx', era='清·嘉庆（待考）', eok=0, series='天山系列', sok=1, leads=['金逐流']),
    '游剑江湖':     dict(year=1972, yconf='approx', era='清·嘉庆（承侠骨丹心，待考）', eok=0, series='天山系列', sok=1, leads=['缪长风', '云紫萝']),
    '广陵剑':       dict(year=1972, yconf='approx', era='明·成化末（承联剑风云录，待考）', eok=0, series='明代系列', sok=1, leads=['陈石星', '云瑚']),
    '牧野流星':     dict(year=1976, yconf='approx', era='清·嘉庆（待考）', eok=0, series='天山系列', sok=1, leads=['孟华']),
    '弹指惊雷':     dict(year=1977, yconf='approx', era='清·嘉庆—道光间（待考）', eok=0, series='天山系列', sok=1, leads=['杨炎', '龙灵珠']),
    '绝塞传烽录':   dict(year=1979, yconf='approx', era='清·道光前后（待考）', eok=0, series='天山系列', sok=1, leads=['杨炎', '冷冰儿']),
    '剑网尘丝':     dict(year=1980, yconf='approx', era='清（承绝塞传烽录，待考）', eok=0, series='天山系列', sok=1, leads=[]),
    '幻剑灵旗':     dict(year=1981, yconf='approx', era='清（剑网尘丝姐妹作，待考）', eok=0, series='天山系列', sok=1, leads=[]),
    '武当一剑':     dict(year=1983, yconf='verified', era='明末（待考）', eok=0, series='独立（互文连还剑奇情录）', sok=0, leads=['耿玉京']),
}

KB_STATUS = {'白发魔女传': '已点亮', '塞外奇侠传': '已点亮', '七剑下天山': '已点亮', '江湖三女侠': '标注中'}

MISSING = [
    dict(book='挑灯看剑录', era='南宋（狂侠天骄魔女前作）', note='正文 authorial/quoted 引用 20 处（鸣镝风云录×13、风云雷电×7），传主檀羽冲（武林天骄）、耿照'),
    dict(book='折戟沉沙录', era='待考', note='全量 grep 零引用；仅《牧野流星》末回回目含"折戟消兵/沉沙洗甲"字样'),
    dict(book='武林三绝', era='待考', note='全量 grep 零引用；两处 bare 命中均为"并称武林三绝"词组误中'),
]

FORWARD_PAT = re.compile(r'请续看|请看续集|姐妹作')


def corpus_stats() -> dict:
    stats = {}
    for d in sorted(p for p in ZH.iterdir() if p.is_dir()):
        chapters = 0
        chars = 0
        for fp in sorted(d.glob('*.txt')):
            chapters += 1
            with open(fp, encoding='utf-8-sig') as f:
                chars += sum(len(re.sub(r'\s', '', line)) for line in f)
        stats[d.name] = {'chapters': chapters, 'chars': chars}
    return stats


def verify_leads(stats_text: dict) -> dict:
    """在全书文本中验证主角候选出场，返回 书名 -> {name: count}。"""
    out = {}
    for book, info in E.items():
        text = stats_text.get(book, '')
        out[book] = {n: text.count(n) for n in info['leads']}
    return out


def main() -> None:
    stats = corpus_stats()
    # 一次性读入全书文本供主角验证（约 17M 字，可接受）
    stats_text = {}
    for d in sorted(p for p in ZH.iterdir() if p.is_dir()):
        buf = []
        for fp in sorted(d.glob('*.txt')):
            with open(fp, encoding='utf-8-sig') as f:
                buf.append(f.read())
        stats_text[d.name] = ''.join(buf)
    lead_hits = verify_leads(stats_text)

    with open(KB / '互文引用表.json', encoding='utf-8') as f:
        inter = json.load(f)
    out_cnt = defaultdict(int)
    in_cnt = defaultdict(int)
    bare_cnt = defaultdict(int)
    for e in inter['edges']:
        if e['kind'] in ('authorial', 'quoted'):
            out_cnt[e['source']] += 1
            in_cnt[e['target']] += 1
        else:
            bare_cnt[e['source']] += 1

    # 强证据：连载接力边（请续看/续集/姐妹作）
    forward = []
    for e in inter['edges']:
        if e['kind'] in ('authorial', 'quoted') and FORWARD_PAT.search(e['snippet']):
            forward.append(e)

    # 弱证据：回指（A 引 B ⇒ B 的故事早于 A）
    backref = defaultdict(lambda: defaultdict(int))
    for e in inter['edges']:
        if e['kind'] in ('authorial', 'quoted') and e['source'] != e['target']:
            backref[e['source']][e['target']] += 1

    works = []
    for i, (book, info) in enumerate(
            sorted(E.items(), key=lambda kv: (kv[1]['year'], kv[1].get('ord', 50), kv[0])), 1):
        s = stats[book]
        hits = lead_hits[book]
        if info['leads'] and all(v > 0 for v in hits.values()):
            lconf = 'ok'
        elif info['leads'] and any(v > 0 for v in hits.values()):
            lconf = 'presence'
        elif info['leads']:
            lconf = 'todo'   # 候选全部零命中——须回炉
        else:
            lconf = 'todo'
        works.append({
            'no': i,
            'book': book,
            'year': info['year'],
            'year_conf': info['yconf'],
            'era': info['era'],
            'era_conf': 'ok' if info['eok'] else 'todo',
            'series': info['series'],
            'series_conf': 'ok' if info['sok'] else 'todo',
            'leads': info['leads'],
            'lead_hits': hits,
            'leads_conf': lconf,
            'chapters': s['chapters'],
            'chars': s['chars'],
            'kb_status': KB_STATUS.get(book, '待建'),
            'intertext_out': out_cnt.get(book, 0),
            'intertext_in': in_cnt.get(book, 0),
            'intertext_bare': bare_cnt.get(book, 0),
        })

    todo_fields = []
    for w in works:
        if w['year_conf'] == 'approx':
            todo_fields.append(f"{w['book']}·初刊年（约{w['year']}，待复核）")
        if w['era_conf'] == 'todo':
            todo_fields.append(f"{w['book']}·背景年代")
        if w['series_conf'] == 'todo':
            todo_fields.append(f"{w['book']}·系列归属")
        if w['leads_conf'] in ('presence', 'todo'):
            todo_fields.append(f"{w['book']}·主角（{('出场已证实/' if w['leads_conf']=='presence' else '') + ('、'.join(w['leads']) if w['leads'] else '无候选')}）")

    meta = {
        'generated': str(date.today()),
        'corpus': '章回版/（34 部实测）',
        'year_sources': '初刊年 verified 项据维基百科/百度百科/中国作家网检索记录（2026-10-31）；approx 项据通行年表待复核',
        'totals': {'books': len(works), 'chapters': sum(w['chapters'] for w in works),
                   'chars': sum(w['chars'] for w in works)},
        'leads_conf_legend': 'ok=候选全部在本书语料中验证出场；presence=部分出场、主角身份待确认；todo=待考',
    }

    payload = {
        'meta': meta,
        'works': works,
        'missing_works': MISSING,
        'forward_edges': [{'source': e['source'], 'target': e['target'], 'loc': f"{e['source']}·{e['loc']}", 'snippet': e['snippet']} for e in forward],
        'backrefs': {s: dict(t) for s, t in sorted(backref.items())},
        'todo_fields': todo_fields,
    }
    with open(KB / '作品元数据表.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # ---------------- MD ----------------
    def clean(s: str) -> str:
        return re.sub(r'（待考）$', '', s)

    L = []
    L.append('# 作品元数据表（P0 · 作品库/谱系/编年史地基）\n')
    L.append(f'> 生成：`scripts/build_work_metadata.py`（{meta["generated"]}）· 语料：{meta["corpus"]} · '
             f'共 {meta["totals"]["books"]} 部 / {meta["totals"]["chapters"]} 回 / {meta["totals"]["chars"]:,} 字（非空白）。\n')
    L.append('> 字段置信分级：初刊年 verified=检索核实 / approx=通行年表待复核；'
             '主角 ok=候选全部经语料验证出场 / presence=出场已证实、主角身份待确认 / todo=待考。'
             '互文出/入只计 authorial+quoted（bare 单列，多为称号/兵器同名，见互文引用表）。\n')

    L.append('## 一、总表（按初刊年排序）\n')
    L.append('| 序 | 书名 | 初刊年 | 背景年代 | 系列 | 主角 | 回数 | 字数 | KB | 互文出/入 |')
    L.append('|---|---|---|---|---|---|---|---|---|---|')
    for w in works:
        year = f"{w['year']}{'*' if w['year_conf']=='approx' else ''}"
        era = clean(w['era']) + ('〔待考〕' if w['era_conf'] == 'todo' else '')
        series = clean(w['series']) + ('〔待考〕' if w['series_conf'] == 'todo' else '')
        if w['leads_conf'] == 'todo':
            leads = ('、'.join(w['leads']) if w['leads'] else '—') + '〔待考〕'
        elif w['leads_conf'] == 'presence':
            leads = '、'.join(w['leads']) + '〔主角待确认〕'
        else:
            leads = '、'.join(w['leads'])
        L.append(f"| {w['no']} | {w['book']} | {year} | {era} | {series} | {leads} "
                 f"| {w['chapters']} | {w['chars']:,} | {w['kb_status']} | {w['intertext_out']}/{w['intertext_in']} |")
    L.append('\n\\* 初刊年为通行年表值，待复核。\n')

    L.append('## 二、缺佚作品（3 部）\n')
    L.append('| 书名 | 背景年代 | 正文引用 | 说明 |')
    L.append('|---|---|---|---|')
    for m in MISSING:
        refs = in_cnt.get(m['book'], 0)
        L.append(f"| {m['book']} | {m['era']} | {refs} 处 | {m['note']} |")
    L.append('')

    L.append('## 三、作者亲证连载接力边（强证据：请续看/续集/姐妹作）\n')
    L.append('| 前作 | 续作 | 证据 |')
    L.append('|---|---|---|')
    for e in forward:
        L.append(f"| {e['source']} | 《{e['target']}》 | {e['source']}·{e['loc']} ｜ {e['snippet'][:40]} |")
    L.append('')

    L.append('## 四、故事顺序线索（互文回指：A 引 B ⇒ B 的故事早于 A；弱证据）\n')
    for src, tgts in sorted(backref.items(), key=lambda kv: -sum(kv[1].values())):
        items = '，'.join(f'《{t}》×{n}' for t, n in sorted(tgts.items(), key=lambda kv: -kv[1]))
        L.append(f'- **{src}** → {items}')
    L.append('')

    L.append(f'## 五、待考清单（{len(todo_fields)} 项）\n')
    for t in todo_fields:
        L.append(f'- [ ] {t}')
    L.append('')

    L.append('## 六、对账更正（对 拆分/README.md）\n')
    L.append('- 原记"《折戟沉沙录》《武林三绝》仅在正文中被作为前作引用"**经全量 grep 证实不成立**：'
             '两书名在全集源文件（含两处目录区）中零出现；正文对《武林三绝》仅有的两处 bare 命中'
             '（女帝奇英传·014、萍踪侠影录·022）均为"并称武林三绝"词组误中。'
             '正文真实引用过的缺佚前作只有《挑灯看剑录》（20 处）。')
    L.append('- 《大唐游侠传》错字"大唐游侠转"实测存在于源文件目录区（梁羽生武侠全集.txt 第 27747 行），拆分时已更正。')
    L.append('- 系列链新证：塞外→七剑、冰魄→冰川、大唐→龙凤、牧野→弹指→绝塞→剑网尘丝 六条"请续看"接力边'
             '为作者亲证续书顺序，可直接用于系列谱系考订。')
    L.append('')

    with open(KB / '作品元数据表.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')

    print(f"works={len(works)} chapters={meta['totals']['chapters']} chars={meta['totals']['chars']:,}")
    print(f"forward_edges={len(forward)}  todo_fields={len(todo_fields)}")
    print(f"-> {KB / '作品元数据表.json'}")
    print(f"-> {KB / '作品元数据表.md'}")


if __name__ == '__main__':
    sys.exit(main())
