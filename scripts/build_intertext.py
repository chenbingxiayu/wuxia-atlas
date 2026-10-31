# -*- coding: utf-8 -*-
"""P0/N8：跨书互文引用全量 grep。

在 章回版/ 全部 34 部正文中检索其余书名（含已知缺佚书目）的出现，
分级记录三类引用边，生成 kb/互文引用表.json / 互文引用表.md。

模式分级（证据强度从高到低）：
  authorial  作者明示互文：拙著《X》/ 拙作《X》/ 事见《X》/ 详见《X》
  quoted     书名引用：正文中出现《X》
  bare       裸书名提及（无书名号，可能为普通词组，仅作待复核线索）

用法：python scripts/build_intertext.py
"""
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZH = ROOT / '章回版'
OUT = ROOT / 'kb'

# 源文本错字变体（拆分/README.md 记录：目录区"大唐游侠转"）
VARIANTS = {'大唐游侠传': ['大唐游侠转']}

# 已知缺佚书目（仅被正文引用，无正文；见 拆分/README.md）
KNOWN_MISSING = ['挑灯看剑录', '折戟沉沙录', '武林三绝']

AUTHORIAL_PATTERNS = [
    re.compile(r'拙[著作]《([^》]{1,20})》'),
    re.compile(r'事见《([^》]{1,20})》'),
    re.compile(r'详见《([^》]{1,20})》'),
    re.compile(r'（事见[^（）]*《([^》]{1,20})》'),
]


def chapter_no(name: str) -> str:
    m = re.match(r'^(\d{3})', name)
    return m.group(1) if m else '000'


def snippet_at(line: str, pos: int, width: int = 60) -> str:
    s = line.strip()
    lo = max(0, pos - width // 3)
    hi = min(len(s), pos + width)
    pre = '…' if lo > 0 else ''
    suf = '…' if hi < len(s) else ''
    return pre + s[lo:hi] + suf


def main() -> None:
    books = sorted(p.name for p in ZH.iterdir() if p.is_dir())
    targets = books + KNOWN_MISSING
    # 变体表：变体串 -> 规范书名
    variant_of = {}
    for canon, vars_ in VARIANTS.items():
        for v in vars_:
            variant_of[v] = canon

    edges = []          # 全部原始命中
    seen = set()        # (source, target, kind, chap, line) 去重（每 loc 每 kind 一条）
    line_total = 0

    for src in books:
        files = sorted((ZH / src).glob('*.txt'))
        for fp in files:
            chap = chapter_no(fp.name)
            with open(fp, encoding='utf-8-sig') as f:
                for lineno, line in enumerate(f, 1):
                    line_total += 1
                    stripped = line.strip()
                    if not stripped:
                        continue

                    # 1) 作者明示模式（先匹配，命中者按 authorial 记）
                    authorial_titles = set()
                    for pat in AUTHORIAL_PATTERNS:
                        for t in pat.findall(stripped):
                            authorial_titles.add(t)

                    # 2) 各目标书名的引用检测
                    for tgt in targets:
                        if tgt == src:
                            continue
                        kind = None
                        pos = -1
                        probe = tgt
                        if f'《{tgt}》' in stripped:
                            kind, pos = 'quoted', stripped.find(f'《{tgt}》')
                        else:
                            v = next((x for x in variant_of
                                      if variant_of[x] == tgt and f'《{x}》' in stripped), None)
                            if v:
                                kind, pos, probe = 'quoted', stripped.find(f'《{v}》'), v
                            elif tgt in authorial_titles:
                                kind, pos = 'authorial', stripped.find(tgt)
                            elif tgt in stripped:
                                kind, pos = 'bare', stripped.find(tgt)
                            else:
                                v2 = next((x for x in variant_of
                                           if variant_of[x] == tgt and x in stripped), None)
                                if v2:
                                    kind, pos, probe = 'bare', stripped.find(v2), v2
                        if kind is None:
                            continue
                        # authorial 若同时命中《X》引用，取更强级别
                        if kind == 'quoted' and tgt in authorial_titles:
                            kind = 'authorial'
                        key = (src, tgt, kind, chap, lineno)
                        if key in seen:
                            continue
                        seen.add(key)
                        edges.append({
                            'source': src,
                            'target': tgt,
                            'kind': kind,
                            'probe': probe,
                            'loc': f'{chap}:{lineno}',
                            'snippet': snippet_at(stripped, pos),
                        })

    # ---- 汇总 ----
    def cnt(pred):
        return sum(1 for e in edges if pred(e))

    summary_out = defaultdict(lambda: defaultdict(int))   # source -> target -> 行数
    summary_in = defaultdict(lambda: defaultdict(int))
    for e in edges:
        summary_out[e['source']][e['target']] += 1
        summary_in[e['target']][e['source']] += 1

    meta = {
        'generated': str(date.today()),
        'corpus': '章回版/（34 部全量）',
        'books': len(books),
        'lines_scanned': line_total,
        'edge_total': len(edges),
        'edge_authorial': cnt(lambda e: e['kind'] == 'authorial'),
        'edge_quoted': cnt(lambda e: e['kind'] == 'quoted'),
        'edge_bare': cnt(lambda e: e['kind'] == 'bare'),
        'kind_priority': 'authorial > quoted > bare（同一行同一目标取最强级别）',
        'known_missing': KNOWN_MISSING,
        'variants': VARIANTS,
    }

    OUT.mkdir(exist_ok=True)
    with open(OUT / '互文引用表.json', 'w', encoding='utf-8') as f:
        json.dump({'meta': meta, 'edges': edges}, f, ensure_ascii=False, indent=1)

    # ---- MD 报告 ----
    L = []
    L.append('# 互文引用表（P0 · N8 数据）\n')
    L.append(f'> 生成：`scripts/build_intertext.py`（{meta["generated"]}）· 语料：{meta["corpus"]} · '
             f'扫描 {line_total} 行 · 命中 {len(edges)} 处'
             f'（authorial {meta["edge_authorial"]} / quoted {meta["edge_quoted"]} / bare {meta["edge_bare"]}）。\n')
    L.append('> 三级含义：**authorial**=作者明示"拙著/事见/详见"（最硬的跨书边）；'
             '**quoted**=正文出现《书名》；**bare**=裸书名（可能是普通词组，须人工复核）。\n')

    L.append('## 一、作者明示互文（authorial，全量）\n')
    L.append('| 来源书 | 指向 | 定位符 | 原文片段 |')
    L.append('|---|---|---|---|')
    for e in edges:
        if e['kind'] == 'authorial':
            L.append(f"| {e['source']} | 《{e['target']}》 | {e['source']}·{e['loc']} | {e['snippet']} |")
    L.append('')

    L.append('## 二、书名引用（《X》，按来源书分组）\n')
    for src in books:
        grp = defaultdict(int)
        for e in edges:
            if e['source'] == src and e['kind'] == 'quoted':
                grp[e['target']] += 1
        if not grp:
            continue
        items = '，'.join(f'《{t}》×{n}' for t, n in sorted(grp.items(), key=lambda kv: -kv[1]))
        L.append(f'- **{src}**（{sum(grp.values())} 处）：{items}')
    L.append('')

    L.append('## 三、裸书名提及（bare，待人工复核）\n')
    for src in books:
        grp = defaultdict(int)
        for e in edges:
            if e['source'] == src and e['kind'] == 'bare':
                grp[e['target']] += 1
        if not grp:
            continue
        items = '，'.join(f'{t}×{n}' for t, n in sorted(grp.items(), key=lambda kv: -kv[1]))
        L.append(f'- **{src}**（{sum(grp.values())} 处）：{items}')
    L.append('')

    L.append('## 四、缺佚作品的被引记录（仅存书名于正文）\n')
    for miss in KNOWN_MISSING:
        grp = summary_in.get(miss, {})
        if grp:
            srcs = '，'.join(f'{s}×{n}' for s, n in sorted(grp.items(), key=lambda kv: -kv[1]))
            L.append(f'- **《{miss}》**：{srcs}')
        else:
            L.append(f'- **《{miss}》**：本次扫描未检出引用')
    L.append('')

    L.append('## 五、出入边排行\n')
    L.append('**引用他人最多（出边）：**')
    for src, d in sorted(summary_out.items(), key=lambda kv: -sum(kv[1].values()))[:10]:
        L.append(f'- {src}：{sum(d.values())} 处 → {max(d, key=d.get)} 等')
    L.append('')
    L.append('**被他人引用最多（入边，不含缺佚）：**')
    for tgt, d in sorted(summary_in.items(), key=lambda kv: -sum(kv[1].values())):
        if tgt in KNOWN_MISSING:
            continue
        L.append(f'- 《{tgt}》：{sum(d.values())} 处 ← {max(d, key=d.get)} 等')
    L.append('')

    L.append('## 附注\n')
    L.append('- 变体处理：' + '，'.join(f'《{v}》→《{c}》' for c, vs in VARIANTS.items() for v in vs))
    L.append('- bare 级命中仅供线索，进入 N8 互文图谱前须逐条人工复核（同名普通词组会误中，如"武林天骄"）。')
    L.append('- JSON 全量（含每条定位符与片段）：`互文引用表.json`。')

    with open(OUT / '互文引用表.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')

    print(f"edges={len(edges)} (authorial={meta['edge_authorial']}, quoted={meta['edge_quoted']}, bare={meta['edge_bare']})")
    print(f"-> {OUT / '互文引用表.json'}")
    print(f"-> {OUT / '互文引用表.md'}")


if __name__ == '__main__':
    sys.exit(main())
