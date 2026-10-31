# -*- coding: utf-8 -*-
"""人工裁定两则（2026-10-31，站点人物档案考订触发，用户裁定）。

① 七剑下天山·027:15 ◇授「哈玛雅→练霓裳」主宾颠倒 →「练霓裳→哈玛雅」
   依据：019:21 明文"白发魔女就是飞红巾后来的师父"；019:37 飞红巾施展师门绝招
   "神魔夺命"；023:91/024:21 武琼瑶为关门弟子（师承链一致）。
② 白发魔女传·015:21 ○拜「None→公孙大娘」→ drop
   依据：未施行动词（"你若真能胜我，我拜你为师"为激将假设，拜师未成立）。

幂等：重复运行自动跳过已裁定条目。管线若重建事件表，重跑本脚本即可恢复裁定。
同步：七剑事件表.md 对应行、两书校订报告.md 补遗、meta 计数。
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]

MARK = '<!-- manual-rulings-20261031 -->'
NOTE_1 = ('主宾颠倒：练霓裳（白发魔女）授哈玛雅（飞红巾）。依据 019:21 明文'
          '"白发魔女就是飞红巾后来的师父"、019:37 飞红巾施展师门绝招；2026-10-31 人工裁定')
NOTE_2 = ('未施行动词："你若真能胜我，我拜你为师"为激将假设，拜师未成立；2026-10-31 人工裁定')


def dump(path: Path, data) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def append_report(path: Path, section: str) -> None:
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    if MARK in text:
        return
    with open(path, 'a', encoding='utf-8') as f:
        f.write(section)


def main() -> None:
    # ---- ① 七剑 027:15 主宾颠倒 ----
    p = ROOT / 'kb' / '七剑下天山' / '事件表.json'
    d = json.loads(p.read_text(encoding='utf-8'))
    hit = [e for e in d['events'] if e['loc'] == '027:15' and e['verb_code'] == '◇']
    assert len(hit) == 1, f'expect 1 event, got {len(hit)}'
    e = hit[0]
    if e.get('curation', {}).get('note') == NOTE_1:
        print('① 七剑027:15 已裁定，跳过')
    else:
        assert e['subject'] == '哈玛雅' and e['object'] == '练霓裳', 'record drifted'
        e['curation'] = {'verdict': 'fix', 'note': NOTE_1, 'before': ['哈玛雅', '练霓裳']}
        e['subject'], e['object'] = '练霓裳', '哈玛雅'
        cs = d['meta'].get('curation_summary', {})
        if 'fixed' in cs:
            cs['fixed'] += 1
        dump(p, d)
        print('① 七剑027:15 主宾已颠倒：练霓裳 → 哈玛雅')

    md = ROOT / 'kb' / '七剑下天山' / '事件表.md'
    if md.exists():
        t = md.read_text(encoding='utf-8')
        old = '| 027:15 | 哈玛雅 | 授 | 练霓裳 | high | 亲授的白发魔女独门 |'
        new = '| 027:15 | 练霓裳 | 授 | 哈玛雅 | high | 亲授的白发魔女独门 ✎ |'
        if old in t:
            md.write_text(t.replace(old, new), encoding='utf-8')
            print('  事件表.md 行已同步')

    append_report(ROOT / 'kb' / '七剑下天山' / '校订报告.md',
                  f"\n{MARK}\n## 人工裁定补遗（2026-10-31，站点档案考订触发）\n\n"
                  f"| 定位 | 动词 | 裁定 | 依据 |\n|---|---|---|---|\n"
                  f"| 027:15 | ◇授 | 主宾颠倒：哈玛雅→练霓裳 改为 练霓裳→哈玛雅 | "
                  f"019:21 明文师承；用户裁定确认 |\n")

    # ---- ② 白发 015:21 drop ----
    p2 = ROOT / 'kb' / '白发魔女传' / '事件表.json'
    d2 = json.loads(p2.read_text(encoding='utf-8'))
    hit2 = [e for e in d2['events'] if e['loc'] == '015:21' and e['verb_code'] == '○']
    assert len(hit2) == 1, f'expect 1 event, got {len(hit2)}'
    e2 = hit2[0]
    if e2.get('dropped'):
        print('② 白发015:21 已裁定，跳过')
    else:
        assert e2['subject'] is None and e2['verb'] == '拜', 'record drifted'
        e2['dropped'] = True
        e2['curation'] = {'verdict': 'drop', 'note': NOTE_2}
        d2['meta']['events_dropped'] = d2['meta'].get('events_dropped', 0) + 1
        cs2 = d2['meta'].get('curation_summary', {})
        if 'dropped' in cs2:
            cs2['dropped'] += 1
        dump(p2, d2)
        print('② 白发015:21 ○拜 已 drop')

    append_report(ROOT / 'kb' / '白发魔女传' / '校订报告.md',
                  f"\n{MARK}\n## 人工裁定补遗（2026-10-31，站点档案考订触发）\n\n"
                  f"| 定位 | 动词 | 裁定 | 依据 |\n|---|---|---|---|\n"
                  f"| 015:21 | ○拜 | drop | 未施行动词（激将假设），拜师未成立 |\n")

    print('done')


if __name__ == '__main__':
    main()
