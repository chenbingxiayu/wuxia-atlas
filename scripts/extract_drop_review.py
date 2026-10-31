# -*- coding: utf-8 -*-
"""Drop 复核材料生成器：指定校订批次的全部 drop 判定 + 上下文 → 校对文件与回填模板。

用法：python scripts/extract_drop_review.py [书名] [批次号...]   （默认 白发魔女传 全部◈批次）

输出（kb/<书>/校订/）：
  drop复核-<批次>.md     — 全部 drop 逐条：定位/动词/代理理由/宽上下文/复核栏
  drop复核-<批次>.tsv    — 回填模板（前 5 列预填，复核结论/修正列留空待填）
复核结论取值：维持 | 误删（可附修正主语/宾语；留空则恢复启发式原值）
apply_curation.py 会自动应用 kb/<书>/校订/drop复核-*.tsv 中结论非空的行。
"""
import io, os, re, sys, glob
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK = sys.argv[1] if len(sys.argv) > 1 else "白发魔女传"
CUR = os.path.join(ROOT, 'kb', BOOK, '校订')

# 批次集：argv 指定批次号，否则取全部已有 ◈ 批次
if len(sys.argv) > 2:
    nums = [int(x) for x in sys.argv[2:]]
else:
    nums = sorted(int(re.search(r'(\d+)\.txt$', p).group(1))
                  for p in glob.glob(os.path.join(CUR, '◈-*.txt')))
BATCHES = [(f'批次{k}', f'◈-{k}.txt', f'校订-◈-{k}.tsv') for k in nums]
SUFFIX = '-'.join(str(k) for k in nums) if nums else '全部'

REASON_CATS = [
    ('同句重复', ('重复', '同句', '复指')),
    ('假设未遂', ('假设', '未遂', '几乎', '险', '若', '欲', '正想', '不敢', '未')),
    ('回述旧事', ('回述', '旧事', '已叙', '已录', '他录')),
    ('非战斗用法', ('非战斗', '打话', '打法', '打量', '打照面', '打哈哈', '打趣', '打赌',
                '助拳', '斗口', '点头', '拍门', '打滚', '拉手', '打定', '打寒', '斗气',
                '表演', '泛述', '移动', '疗伤', '器物')),
]


def categorize(note):
    for cat, kws in REASON_CATS:
        if any(k in note for k in kws):
            return cat
    return '其他'


def parse_ctx(path):
    blocks = {}
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    i = 0
    while i < len(lines):
        m = re.match(r'^### (E\d+) \| (\S+) \| (\S+) \| 启发 主=(\S*) 宾=(\S*) \| (\S+)',
                     lines[i])
        if m:
            eid, loc, verb, subj, obj, conf = m.groups()
            ctx = lines[i + 1] if i + 1 < len(lines) else ''
            blocks[eid] = {"loc": loc, "verb": verb, "subj": subj or '—',
                           "obj": obj or '—', "conf": conf, "ctx": ctx}
            i += 2
        else:
            i += 1
    return blocks


def main():
    entries = []
    for bname, ctx_f, tsv_f in BATCHES:
        blocks = parse_ctx(os.path.join(CUR, ctx_f))
        with open(os.path.join(CUR, tsv_f), encoding='utf-8') as f:
            for ln in f:
                ln = ln.rstrip('\n')
                if not ln.strip():
                    continue
                p = ln.split('\t')
                if len(p) < 5 or not p[0].startswith('E'):
                    continue
                if p[1].strip() != 'drop':
                    continue
                eid = p[0]
                b = blocks.get(eid, {})
                entries.append({
                    "batch": bname, "eid": eid,
                    "loc": b.get('loc', '?'), "verb": b.get('verb', '?'),
                    "heur": f"主={b.get('subj','—')} 宾={b.get('obj','—')}",
                    "note": p[4].strip() if len(p) > 4 else '',
                    "ctx": b.get('ctx', ''),
                })

    cats = Counter(categorize(e["note"]) for e in entries)
    by_batch = Counter(e["batch"] for e in entries)
    print('total drops:', len(entries), dict(by_batch))
    print('by reason:', dict(cats))

    # md
    L = [f"# Drop 复核材料（{BOOK}，{'/'.join(b[0] for b in BATCHES)}）", "",
         f"共 {len(entries)} 条 drop，",
         "按理由类别分组；每条给出代理判定理由与 ±170 字上下文，请逐条复核。",
         "复核结论：**维持**（确非事件）或 **误删**（应保留；可附修正主/宾）。",
         f"校对结果可直接填入 `drop复核-{SUFFIX}.tsv` 的「复核结论/修正主语/修正宾语」列（未填行按维持处理）。", ""]
    by_cat = defaultdict(list)
    for e in entries:
        by_cat[categorize(e["note"])].append(e)
    for cat in ['同句重复', '假设未遂', '回述旧事', '非战斗用法', '其他']:
        es = by_cat.get(cat, [])
        L.append(f"## {cat}（{len(es)} 条）")
        L.append("")
        for e in sorted(es, key=lambda x: (x['batch'], int(x['eid'][1:]))):
            L.append(f"### {e['batch']}-{e['eid']} | {e['loc']} | {e['verb']} "
                     f"| {e['heur']}")
            L.append(f"- 代理理由：{e['note'] or '（未注明）'}")
            L.append(f"- 上下文：…{e['ctx']}…")
            L.append("")
    with open(os.path.join(CUR, f'drop复核-{SUFFIX}.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')

    # tsv 模板
    with open(os.path.join(CUR, f'drop复核-{SUFFIX}.tsv'), 'w', encoding='utf-8') as f:
        f.write('eid\tbatch\tloc\tverb\t代理理由\t复核结论\t修正主语\t修正宾语\t备注\n')
        for e in sorted(entries, key=lambda x: (x['batch'], int(x['eid'][1:]))):
            f.write(f"{e['eid']}\t{e['batch']}\t{e['loc']}\t{e['verb']}\t{e['note']}\t\t\t\t\n")
    print(f'-> drop复核-{SUFFIX}.md / drop复核-{SUFFIX}.tsv')


if __name__ == '__main__':
    main()
