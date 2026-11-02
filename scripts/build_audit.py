# -*- coding: utf-8 -*-
"""穿帮雷达 v0（build_audit.py）——规则引擎，构建期输出报告。

规则 R1 死亡一致性：事件层 verb∈{杀,诛,毙} 且宾语=X 视为死亡事件；此后 X 再以
  非引述（in_quote=false）出现在事件主/宾 → 疑似穿帮候选；此后出现全部为引述 → 验证通过展品。
规则 R2 武功习得时序 / R3 毒理一致性：待工具 A 招式表考订 / 工具 C 丹药扩展表接入（挂账）。

输出：site/data/audit.json（L0：计数 + 定位符；摘录不入切片）。
用法：python scripts/build_audit.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import KB, SITE_DATA, lit_books, today  # noqa: E402

CHRONO = ['白发魔女传', '塞外奇侠传', '七剑下天山', '江湖三女侠']
DEATH_VERBS = {'杀', '诛', '毙'}


def main() -> int:
    books = [b for b in CHRONO if b in lit_books()]
    deaths = {}   # name -> [{'book','loc','by'}]
    events_by_name = {}
    all_events = []
    for book in books:
        evs = json.loads((KB / book / '事件表.json').read_text(encoding='utf-8')).get('events', [])
        for e in evs:
            if e.get('dropped') or e.get('curation', {}).get('verdict') == 'drop':
                continue
            loc = e.get('loc', '')
            try:
                chap, line = int(loc[:3]), int(loc[4:7])
            except ValueError:
                continue
            all_events.append({'book': book, 'chap': chap, 'line': line, 'loc': loc,
                               'v': e.get('verb') or '', 'code': e.get('verb_code'),
                               'a': e.get('subject'), 'b': e.get('object'),
                               'in_quote': bool(e.get('in_quote'))})
            for n in (e.get('subject'), e.get('object')):
                if n:
                    events_by_name.setdefault(n, []).append(all_events[-1])
            if e.get('verb') in DEATH_VERBS and e.get('object'):
                deaths.setdefault(e['object'], []).append(
                    {'book': book, 'loc': loc, 'by': e.get('subject')})

    violations, passes = [], []
    for victim, ds in deaths.items():
        evs = events_by_name.get(victim, [])
        # 取最早死亡事件为基准（多次"死亡"本身记入 R1b 复活疑云）
        order = {b: i for i, b in enumerate(books)}
        ds_sorted = sorted(ds, key=lambda d: (order.get(d['book'], 9), int(d['loc'][:3]), int(d['loc'][4:7])))
        first = ds_sorted[0]
        after = [e for e in evs
                 if (order.get(e['book'], 9), e['chap'], e['line']) > (order.get(first['book'], 9), int(first['loc'][:3]), int(first['loc'][4:7]))]
        live = [e for e in after if not e['in_quote']]
        entry = {'name': victim, 'death': first, 'deaths_n': len(ds_sorted),
                 'after_n': len(after), 'live_n': len(live)}
        if live:
            entry['samples'] = [{'book': e['book'], 'loc': e['loc'], 'role': '主' if e['a'] == victim else '宾',
                                 'v': e['v']} for e in live[:5]]
            violations.append(entry)
        elif after:
            entry['samples'] = [{'book': e['book'], 'loc': e['loc'], 'in_quote': True} for e in after[:3]]
            passes.append(entry)

    violations.sort(key=lambda x: -x['live_n'])  # 死后仍活跃者排前
    payload = {'meta': {'generated': today(), 'schema': 'audit-v0', 'rules': ['R1 死亡一致性'],
                        'pending_rules': ['R2 武功习得时序（待工具 A 招式表考订接数）',
                                          'R3 毒理一致性（待工具 C 丹药扩展表）'],
                        'note': '两可清单："杀"事件可能非致死（未遂/重伤），也可能是真穿帮——每条都可点开定位符对质原文；v0 不做断言'},
              'totals': {'death_events': sum(len(v) for v in deaths.values()),
                         'checked': len(violations) + len(passes),
                         'ambiguous': len(violations), 'passes': len(passes)},
              'r1_ambiguous': violations[:30], 'r1_passes': passes[:30]}
    out = SITE_DATA / 'audit.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"-> {out} ({out.stat().st_size // 1024} KB)")
    print(f"死亡事件 {payload['totals']['death_events']} · 检查 {payload['totals']['checked']} · "
          f"疑似 {len(violations)} · 通过 {len(passes)}")
    for v in violations[:6]:
        print(f"  疑似: {v['name']}（死于 {v['death']['book']}·{v['death']['loc']}，"
              f"死后非引述出场 {v['live_n']} 次）")
    return 0


if __name__ == '__main__':
    sys.exit(main())
