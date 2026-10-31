# -*- coding: utf-8 -*-
"""v0.2 迁移：丹药/药物成品类型 § 立项（v2 修正版）。

阶段一  存量迁移：〖•X〗→〖§X〗（幂等）
阶段二  回填：红丸/小还丹/雄黄 按原文出现位置包裹插入 〖§X〗，
        plain 对齐规则与 lint 一致（标记内部扣除类型码与 |管道 后计入 plain），
        插入后逐行剥标自校验，失败即回滚该行。
阶段三  Schema 版本号 v0.1 → v0.2（幂等）
"""
import io, os, re, sys, glob

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAGGED = os.path.join(ROOT, 'kb', 'tagged', '白发魔女传')
ORIG = os.path.join(ROOT, '章回版', '白发魔女传')

MIGRATE = ['百日醉', '碧灵丹', '止痛药丸', '药丸', '药末', '药粉', '药酒',
           '解药', '金创药', '金创圣药', '鸡鸣五鼓返魂香']
BACKFILL = ['红丸', '小还丹', '雄黄']


def plain_map(tl):
    """每个 tagged 字符对应的 plain 序号（码字/管道规范名为 None）；返回 (map, plain_len)。"""
    res = [None] * len(tl)
    plain = 0
    i = 0
    while i < len(tl):
        c = tl[i]
        if c in '〖⟦':
            close = '〗' if c == '〖' else '⟧'
            j = tl.index(close, i)
            inner = tl[i + 1:j]
            if c == '〖':
                bar = inner.find('|')
                end_surf = bar if bar >= 0 else len(inner)
            else:
                end_surf = len(inner)
            for m in range(1, end_surf):
                res[i + 1 + m] = plain
                plain += 1
            i = j + 1
        else:
            res[i] = plain
            plain += 1
            i += 1
    return res, plain


def strip_line(tl):
    """与 lint 同语义剥标。"""
    pm, _ = plain_map(tl)
    return ''.join(tl[k] for k in range(len(tl)) if pm[k] is not None)


def main():
    stat = {'migrate': 0, 'backfill': 0, 'skip_inside_mark': 0, 'verify_fail': 0}
    files = sorted(glob.glob(os.path.join(TAGGED, '*.tagged.md')))
    assert len(files) == 32

    # 阶段一 + 三
    for fp in files:
        with open(fp, encoding='utf-8') as f:
            t = f.read()
        for term in MIGRATE:
            old, new = f'〖•{term}〗', f'〖§{term}〗'
            n = t.count(old)
            if n:
                t = t.replace(old, new)
                stat['migrate'] += n
        t = t.replace('schema: wuxia-tagged-v0.1', 'schema: wuxia-tagged-v0.2')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(t)

    # 阶段二：对照原文回填（包裹式）
    for fp in files:
        name = os.path.basename(fp)
        op = next(iter(glob.glob(os.path.join(ORIG, name[:3] + '*.txt'))), None)
        assert op, name
        with open(fp, encoding='utf-8') as f:
            raw = f.read().split('\n')
        with open(op, encoding='utf-8') as f:
            olines = f.read().split('\n')
        assert raw[0].strip() == '---'
        end = raw.index('---', 1)
        body_idx = [i for i in range(end + 1, len(raw))
                    if not re.match(r'^:::', raw[i])]
        assert len(body_idx) == len(olines), name
        changed = False
        for k, ol in enumerate(olines):
            if not any(p in ol for p in BACKFILL):
                continue
            ti_raw = body_idx[k]
            tl = raw[ti_raw]
            pm, plain_len = plain_map(tl)
            if plain_len != len(ol):
                print(f'ALIGN-FAIL {name} 第{k+1}行 plain={plain_len} orig={len(ol)}')
                stat['verify_fail'] += 1
                continue
            inv = {}   # plain idx -> tagged idx
            for tpos, p in enumerate(pm):
                if p is not None and p not in inv:
                    inv[p] = tpos
            inserts = []
            for term in BACKFILL:
                start = 0
                while True:
                    j = ol.find(term, start)
                    if j < 0:
                        break
                    tpos = [inv.get(x) for x in range(j, j + len(term))]
                    if all(x is not None for x in tpos) and                             tpos == list(range(tpos[0], tpos[0] + len(term))):
                        inserts.append((tpos[0], tpos[-1], term))
                    else:
                        stat['skip_inside_mark'] += 1
                    start = j + 1
            for s, e, term in sorted(inserts, key=lambda x: -x[0]):
                tl = tl[:e + 1] + '〗' + tl[e + 1:]
                tl = tl[:s] + f'〖§' + tl[s:]
                stat['backfill'] += 1
            if inserts:
                if strip_line(tl) != ol:
                    print(f'VERIFY-FAIL {name} 第{k+1}行，回滚')
                    stat['verify_fail'] += 1
                else:
                    raw[ti_raw] = tl
                    changed = True
        if changed:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write('\n'.join(raw))

    print('migration stat:', stat)
    print('expected: migrate=25(首次) backfill=41 (红丸28+小还丹11+雄黄2)')


if __name__ == '__main__':
    main()
