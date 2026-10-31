# -*- coding: utf-8 -*-
"""双主角（卓一航 × 练霓裳）轨迹与同场场景计算 v2。

v2 修正：
  - 轨迹改为「章回级地点序列」：在人物在场行 ±2 行窗口内统计 =地名 token 频次，
    按首现顺序输出该章地点序列（对话中提及的远处地名因不在人物行附近而被自然过滤）；
  - 官/宫 错变体归一（乾清官→乾清宫、景仁官→景仁宫）；
  - 场景地名 = 场景行范围 ±5 内频次最高地名，缺省回退到该章人物行的主地名。
"""
import io, os, re, sys, glob, json
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK = "白发魔女传"
REG = os.path.join(ROOT, "kb", BOOK, "实体登记表.json")
TAGGED = os.path.join(ROOT, "kb", "tagged", BOOK)
OUT_JSON = os.path.join(ROOT, "video", "双主角数据.json")
OUT_MD = os.path.join(ROOT, "video", "场景摘录-待总结.md")

P1, P2 = "卓一航", "练霓裳"
GAP = 20
WIN = 2          # 人物行 → 地点归属窗口
PLACE_FIX = {'乾清官': '乾清宫', '景仁官': '景仁宫'}

ENT = re.compile(r'〖([^〖〗]*)〗')


def canon_of(inner):
    rest = inner[1:]
    return rest.split('|', 1)[1] if '|' in rest else rest


def strip_line(ln):
    def ent(m):
        inner = m.group(0)[1:-1]
        rest = inner[1:]
        if '|' in rest:
            rest = rest.split('|', 1)[0]
        return rest
    ln = ENT.sub(ent, ln)
    return re.sub(r'⟦([^⟦⟧]*)⟧', lambda m: m.group(0)[1:-1][1:], ln)


def main():
    with open(REG, encoding='utf-8') as f:
        reg = json.load(f)

    def toks(name, typ):
        d = defaultdict(set)
        e = reg["entities"].get(f"{typ}{name}")
        if e:
            for loc in e["locators"]:
                ch, ln = loc.split(':')
                d[int(ch)].add(int(ln))
        return d

    p1, p2 = toks(P1, '@'), toks(P2, '@')
    place_toks = {}
    for key, e in reg["entities"].items():
        if e["type"] != '=':
            continue
        name = PLACE_FIX.get(e["canonical"], e["canonical"])
        for loc in e["locators"]:
            ch, ln = loc.split(':')
            place_toks.setdefault(name, {}).setdefault(int(ch), set()).add(int(ln))

    def places_near(ch, lo, hi, w):
        """行号区间 [lo,hi] ±w 内的地名计数（按首现顺序）。"""
        cnt = Counter()
        first = {}
        for name, d in place_toks.items():
            for l in d.get(ch, ()):
                if lo - w <= l <= hi + w:
                    cnt[name] += 1
                    first.setdefault(name, l)
        return [n for n, _ in sorted(cnt.items(), key=lambda kv: (-kv[1], first[kv[0]]))
                if cnt[n] >= 1]

    def chapter_places(presd):
        """{ch: [地点列表]}：人物在场行 ±WIN 内的地名频次统计，
        取 cnt≥2 者按频次降序（并列按首现），至多 4 个；全为 1 次时取首现的前 2 个。"""
        out = {}
        for ch in sorted(presd):
            cnt = Counter()
            first = {}
            for l in presd[ch]:
                for n in places_near(ch, l, l, WIN):
                    cnt[n] += 1
                    first.setdefault(n, l)
            main = [n for n, _ in sorted(cnt.items(),
                                         key=lambda kv: (-kv[1], first[kv[0]]))
                    if cnt[n] >= 2][:4]
            if not main:
                main = [n for n, _ in sorted(cnt.items(),
                                             key=lambda kv: first[kv[0]])][:2]
            out[ch] = main
        return out

    traj1, traj2 = chapter_places(p1), chapter_places(p2)

    # 同场场景：两人提及行的并集按间隙分组（叙述交替提及=同场；间隙≤3行视为连续）
    scenes = []
    for ch in sorted(set(p1) | set(p2)):
        union = sorted(set(p1.get(ch, set())) | set(p2.get(ch, set())))
        if not union:
            continue
        groups, cur = [], [union[0]]
        for l in union[1:]:
            if l - cur[-1] <= 3:
                cur.append(l)
            else:
                groups.append(cur)
                cur = [l]
        groups.append(cur)
        for g in groups:
            gset = set(g)
            n1 = len(gset & p1.get(ch, set()))
            n2 = len(gset & p2.get(ch, set()))
            if n1 == 0 or n2 == 0:
                continue          # 单方场景，不算同场
            ns = places_near(ch, g[0], g[-1], 5)
            if not ns:
                ns = places_near(ch, min(p1.get(ch, {0})), max(p1.get(ch, {0})), 0)
            scenes.append({"ch": ch, "from": g[0], "to": g[-1], "lines": len(g),
                           "n1": n1, "n2": n2, "place": ns[0] if ns else '?'})

    # 场景上下文摘录
    file_map = {os.path.basename(fp)[:3]: fp
                for fp in glob.glob(os.path.join(TAGGED, '*.tagged.md'))}
    for i, s in enumerate(scenes):
        with open(file_map[f"{s['ch']:03d}"], encoding='utf-8') as f:
            lines = f.read().split('\n')
        end = lines.index('---', 1)
        body = [l for l in lines[end + 1:] if not re.match(r'^:::', l)]
        ctx = ''.join(strip_line(l) for l in body[max(0, s['from'] - 1):s['to']])
        s["sid"] = f"S{i+1:02d}"
        s["ctx"] = ctx[:220]

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump({"P1": P1, "P2": P2,
                   "trajectory": {P1: traj1, P2: traj2},
                   "scenes": scenes}, f, ensure_ascii=False, indent=1)

    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write(f"# 同场场景摘录（{P1} × {P2}，共 {len(scenes)} 场）\n\n")
        for s in scenes:
            f.write(f"### {s['sid']} | {s['ch']:03d}:{s['from']:03d}–{s['to']:03d} "
                    f"| {s['place']} | {s['lines']}行\n{s['ctx']}\n\n")

    print(f"scenes={len(scenes)}")
    for name, tr in ((P1, traj1), (P2, traj2)):
        print(f"--- {name} 章回地点序列 ---")
        for ch in sorted(tr):
            print(f"  {ch:03d}: {' → '.join(tr[ch]) if tr[ch] else '(无地名)'}")


if __name__ == '__main__':
    main()
