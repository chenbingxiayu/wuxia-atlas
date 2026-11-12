# -*- coding: utf-8 -*-
"""游戏数据管线（M5 · G1 武林二十问答 + G7 每日一谜）。

G1：从 dossiers 提取人物属性向量（跨书/书目/师承/杀伤/兵器/出场量……12 问），
    岛端以信息增益选问、是非题收缩候选集（≤20 问）。
G7：从图谱生成确定性谜题库（谁杀了X / 门派武功归属 / 名物流转），岛上按日期哈希选题——
    全网同题、零后端；谜底唯一且带定位符（KB 的确定性 = 零幻觉题库）。

输出：site/data/games/{twenty,daily}.json
W0-T3b（天山演示版总体方案 §1.2，2026-11-08）新增 --scope（题库按 book ∈ scope 过滤重建）：
  - twenty：dossiers 人物按 books ∩ scope 非空保留，books 裁到 scope 后重建属性；
  - daily：killer 只取 scope 书 atlas 切片事件；sectart/holder 按关系/明文边 book ∈ scope 过滤
    （audit-r1 已是 scope 口径时 killer 核验天然对齐；图鉴 collection 走 weapons scope 口径，随 EX-4）；
  - 不带 --scope：全量口径，行为与现状一致（meta 无 scope 键，方案 R6）。
用法：python scripts/build_games_data.py [--scope tianshan-demo]
"""
import hashlib
import json
import sys
from collections import Counter  # noqa: F401
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import SITE_DATA, lit_books, today  # noqa: E402

# W0-T3b：scope 基础设施复用（export_site_common 在 wuxia-kb/scripts，import 胜过复制）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / 'wuxia-kb' / 'scripts'
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402

OUT = SITE_DATA / 'games'


def build_twenty(dossiers, atlas_slices, scope=None):
    chars = []
    for d in dossiers.get('dossiers', []):
        name = d['canonical']
        books = {b for b in d.get('books', []) if esc.in_scope(b, scope)}
        if scope is not None and not books:
            continue  # scope 口径：仅 scope 外书出场的人物不入题库
        combat = d.get('combat') or {}
        lineage = d.get('lineage') or {}
        sect = ''
        # spec 002 T2：仅 strong/ok 级门派线索进属性（weak 推测级排除——如练霓裳≠武当派）
        sa_ok = [s for s in (d.get('sect_affinity') or []) if s.get('tier') in ('strong', 'ok')]
        if sa_ok:
            sect = sa_ok[0].get('sect', '')
        attrs = {
            'cross': len(books) > 1,
            'b_baimo': '白发魔女传' in books,
            'b_qijian': '七剑下天山' in books,
            'b_sannvxia': '江湖三女侠' in books,
            'master': bool(lineage.get('masters')),
            'disciple': bool(lineage.get('disciples')),
            'kills': len(combat.get('kills', [])) > 0,
            'slain': len(combat.get('slain_by', [])) > 0,
            'n': d.get('appearance_total', 0) >= 500,
            'top': d.get('appearance_total', 0) >= 100,
        }
        chars.append({'name': name, 'books': sorted(books), 'sect': sect, 'a': attrs,
                      'href': name, 'total': d.get('appearance_total', 0)})
    questions = [
        {'id': 'cross', 'text': '这位人物跨过多部书出场吗？', 'key': 'cross'},
        {'id': 'b_baimo', 'text': '主要故事发生在《白发魔女传》时期吗？', 'key': 'b_baimo'},
        {'id': 'b_qijian', 'text': '（也）出现在《七剑下天山》吗？', 'key': 'b_qijian'},
        {'id': 'b_sannvxia', 'text': '（也）出现在《江湖三女侠》吗？', 'key': 'b_sannvxia'},
        {'id': 'master', 'text': '有明确的师承记载吗？', 'key': 'master'},
        {'id': 'disciple', 'text': '有明确的传人吗？', 'key': 'disciple'},
        {'id': 'kills', 'text': '事件层有他/她的杀伤记录吗？', 'key': 'kills'},
        {'id': 'slain', 'text': '他/她被杀或败亡过吗？', 'key': 'slain'},
        {'id': 'n', 'text': '出场量很大吗（≥500 次）？', 'key': 'n'},
        {'id': 'top', 'text': '算得上全书主要人物吗（≥100 次）？', 'key': 'top'},
    ]
    meta = {'generated': today(), 'schema': 'g1-v1', 'note': '岛端信息增益选问，≤20 问；候选=人物谱全集'}
    smeta = esc.scope_meta(scope)
    if smeta:
        meta.update(smeta)
    return {'meta': meta, 'chars': chars, 'questions': questions}


def build_daily(atlas_slices, arts, weapons, audit_passes, scope=None):
    puzzles = []
    # 类型 A：谁杀了 X —— 死者必须通过 audit-r1 宽松核验（未死/两可不出题，spec 002 T2）
    death = {}
    for s in atlas_slices:
        if not esc.in_scope(s.get('title'), scope):
            continue  # scope 口径：只取 scope 书切片事件
        for evs in s['events'].values():
            for e in evs:
                if e.get('v') in ('杀', '诛', '毙') and e.get('b') and e.get('a'):
                    death.setdefault(e['b'], []).append((s['title'], e['a'], e['l']))
    skipped_killer = 0
    for victim, rows in sorted(death.items(), key=lambda kv: -len(kv[1])):
        if len(rows) < 1 or victim not in audit_passes:
            skipped_killer += 1
            continue
        book, killer, loc = rows[0]
        chaps = sorted({int(r[2][:3]) for r in rows})
        chap_hint = f'死者登场于第 {chaps[0]} 回' if len(chaps) == 1 else f'死者登场于第 {chaps[0]}–{chaps[-1]} 回'
        puzzles.append({
            'id': f'killer-{victim}', 'type': 'killer',
            'q': f'谁杀了「{victim}」？', 'answer': killer,
            'aliases': [killer],
            'hints': [f'案发在《{book}》', chap_hint, f'凶手姓名 {len(killer)} 个字'],
            'loc': f'{book}·{loc}', 'explain': f'{killer} {victim}（{book}·{loc}，事件表 verb=杀）',
        })
    # 类型 B：镇派/拥有武功归属（证据≥5 的强关系）
    for a in (arts or {}).get('arts', []):
        for book, bb in (a.get('relations') or {}).items():
            if not esc.in_scope(book, scope):
                continue  # scope 口径：归属证据的书 ∈ scope 才取
            for r in bb.get('relations', []):
                if r.get('st') == '◆' and r.get('pred') in ('镇山', '拥有') and r.get('ev', 0) >= 5:
                    puzzles.append({
                        'id': f"art-{a['canonical']}", 'type': 'sectart',
                        'q': f'「{a["canonical"]}」是哪一派的名下武功（{r["pred"]}）？', 'answer': r['s'],
                        'aliases': [r['s']],
                        'hints': [f'关系录自《{book}》', f'证据 {r["ev"]} 处', f'门派名 {len(r["s"])} 个字'],
                        'loc': f'{book}·{(r.get("locs") or [""])[0]}',
                        'explain': f'{r["s"]} {r["pred"]} {a["canonical"]}（{book}·{(r.get("locs") or [""])[0]}，关系表 ev={r["ev"]}）',
                    })
                    break  # 每武功取最强一门
    # 类型 C：名物首见/主要持有人（holders Top1，且明文边≥1）
    for wpn in (weapons or {}).get('weapons', []):
        books_hint = [b for b in (wpn.get('books') or {}) if esc.in_scope(b, scope)]
        if wpn.get('conf') == 'strong' and wpn.get('holders') and books_hint:
            h = wpn['holders'][0]
            strong = next((e for e in wpn.get('chain', [])
                           if e.get('conf') == 'strong' and esc.in_scope(e.get('book'), scope)), None)
            if strong is None:
                continue  # scope 口径：无 scope 书明文边不出题
            puzzles.append({
                'id': f"wpn-{wpn['canonical']}", 'type': 'holder',
                'q': f'名物「{wpn["canonical"]}」的主要持有人是谁？', 'answer': h['name'],
                'aliases': [h['name']],
                'hints': [f'这是一件「{wpn["kind"]}」', f'见于《{"》《".join(books_hint)}》', f'同场出现 {h["n"]} 次'],
                'loc': f'{strong["book"]}·{strong["loc"]}',
                'explain': f'{wpn["canonical"]} 与 {h["name"]} 共现 {h["n"]} 次；明文流转 [{strong["verb"]}]（{strong["book"]}·{strong["loc"]}）——暂持 ≠ 归属',
            })
    # 去重 + 稳定排序（id 哈希序，保证任何日期取到的都是同一题）
    seen, uniq = set(), []
    for p in puzzles:
        if p['id'] not in seen:
            seen.add(p['id'])
            uniq.append(p)
    uniq.sort(key=lambda p: hashlib.sha1(p['id'].encode()).hexdigest())
    meta = {'generated': today(), 'schema': 'g7-v1', 'note': '日期哈希选题：day=YYYYMMDD 的 sha1 取模；全网同题、零后端',
            'answer_policy': '答案唯一且带定位符；提示三级递进；killer 死者须通过 audit-r1 核验',
            'audit_filter': {'passes': len(audit_passes), 'killer_skipped': skipped_killer}}
    smeta = esc.scope_meta(scope)
    if smeta:
        meta.update(smeta)
    return {'meta': meta, 'puzzles': uniq}


def main() -> int:
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    OUT.mkdir(parents=True, exist_ok=True)
    dossiers = json.loads((SITE_DATA / 'dossiers.json').read_text(encoding='utf-8'))
    # W0-T3b：切片书目 scope 口径只取 scope 书（全量口径 lit_books()，现状不变）
    if scope is None:
        slice_books = lit_books()
    else:
        slice_books = [b for b in scope['books'] if (SITE_DATA / 'atlas' / f'{b}.json').exists()]
    slices = [json.loads((SITE_DATA / 'atlas' / f'{b}.json').read_text(encoding='utf-8'))
              for b in slice_books]
    arts = json.loads((SITE_DATA / 'arts.json').read_text(encoding='utf-8'))
    weapons = json.loads((SITE_DATA / 'weapons.json').read_text(encoding='utf-8'))
    audit_r1 = json.loads((SITE_DATA / 'audit-r1.json').read_text(encoding='utf-8'))
    passes = {p['name'] for p in audit_r1.get('passes', [])}
    for name, payload in (('twenty', build_twenty(dossiers, slices, scope=scope)),
                          ('daily', build_daily(slices, arts, weapons, passes, scope=scope))):
        p = OUT / f'{name}.json'
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'-> {p} ({p.stat().st_size // 1024} KB)')
    print(f"每日谜题库：{len(json.loads((OUT / 'daily.json').read_text(encoding='utf-8'))['puzzles'])} 题")
    return 0


if __name__ == '__main__':
    sys.exit(main())
