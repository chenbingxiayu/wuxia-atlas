# -*- coding: utf-8 -*-
"""事件表生成器（事件层 · shiji-kb 管线「事件/关系」阶段）

用法：python scripts/build_event_table.py [书名]   （默认 白发魔女传）

从 kb/tagged/<书>/ 的标注文件抽取全部动词标记 ⟦码 词⟧，按句子上下文
消解主语/宾语，生成：
  kb/<书>/事件表.json   — 全量事件（含引语内事件，带 in_quote 标记）
  kb/<书>/事件表.md     — 可读版：◉杀伐/○结盟/◇传艺/▲擒控 全列，◈交战按对 aggreg

主宾消解启发（单句窗口）：
  1. 动词前最近 @/◆ 实体为默认主语（间距 ≤40 字）；
  2. 间距含 把/将 → 该实体转为宾语，再向前找主语；
  3. 间距含 被   → 该实体转为宾语（被动），被-动词之间的实体为主语（施动者）；
  4. 动词后 ≤30 字内最近 @/◆ 实体为宾语。
canonical 通过 实体登记表.json 的别名链归到组根。引语（"…"）内事件仅统计不进正文表。
"""
import io, json, os, re, sys, glob
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK = sys.argv[1] if len(sys.argv) > 1 else "白发魔女传"
TAGGED_DIR = os.path.join(ROOT, "kb", "tagged", BOOK)
REGISTRY = os.path.join(ROOT, "kb", "白发魔女传", "实体登记表.json")
OUT_JSON = os.path.join(ROOT, "kb", BOOK, "事件表.json")
OUT_MD = os.path.join(ROOT, "kb", BOOK, "事件表.md")

ENT = re.compile(r'〖([^〖〗]*)〗')
VERB = re.compile(r'⟦([^⟦⟧]*)⟧')
SENT_END = "。！？；…"
ACTOR_CODES = ('@', '◆')

VERB_NAME = {'◉': '杀伐', '◈': '交战', '○': '拜认结盟', '▲': '擒控', '◇': '传艺'}


def load_name_map():
    with open(REGISTRY, encoding='utf-8') as f:
        reg = json.load(f)
    m = {}
    for key, e in reg["entities"].items():
        if e["type"] not in ACTOR_CODES:
            continue
        canon = e["canonical"]
        m.setdefault(canon, canon)
        for s in e.get("surfaces", {}):
            m.setdefault(s, canon)
        for a in e.get("aliases", {}):
            m.setdefault(a, canon)
    return m


def strip_marks(text):
    def ent_repl(m):
        inner = m.group(0)[1:-1]
        rest = inner[1:]
        if '|' in rest:
            rest = rest.split('|', 1)[0]
        return rest
    text = ENT.sub(ent_repl, text)
    text = VERB.sub(lambda m: m.group(0)[1:-1][1:], text)
    return text


def sentence_ranges(line):
    rs, start = [], 0
    for i, ch in enumerate(line):
        if ch in SENT_END:
            rs.append((start, i + 1))
            start = i + 1
    if start < len(line):
        rs.append((start, len(line)))
    return rs


def quote_ranges(line):
    """成对弯引号区间：开 U+201C，闭 U+201D。"""
    rs, stack = [], None
    for i, ch in enumerate(line):
        if ch == chr(0x201C):
            stack = i
        elif ch == chr(0x201D) and stack is not None:
            rs.append((stack, i))
            stack = None
    return rs


def clean_excerpt(s):
    """摘录窗口切在标记中间时，先裁掉两侧残缺标记，再剥全标记。"""
    s = re.sub(r'^[^〗⟧]*[〗⟧]', '', s)   # 左侧截断的标记尾
    s = re.sub(r'[〖⟦][^〗⟧]*$', '', s)   # 右侧截断的标记头
    s = strip_marks(s)
    return s.strip()


def extract():
    with open(REGISTRY, encoding='utf-8') as f:
        reg = json.load(f)
    name_map = load_name_map()

    files = sorted(glob.glob(os.path.join(TAGGED_DIR, "*.tagged.md")))
    n_ch = len(glob.glob(os.path.join(ROOT, "章回版", BOOK, "*.txt")))
    assert n_ch and len(files) == n_ch, \
        f"tagged {len(files)} != 章回版 {n_ch} 回，标注未完成或有缺漏"

    events = []
    for fp in files:
        ch = int(re.search(r'(\d{3})_', os.path.basename(fp)).group(1))
        with open(fp, encoding='utf-8') as f:
            lines = f.read().split('\n')
        end = lines.index('---', 1)
        body = lines[end + 1:]
        for ln_no, line in enumerate(body, 1):
            if re.match(r'^:::', line):
                continue
            if not VERB.search(line):
                continue
            ents = []
            for m in ENT.finditer(line):
                inner = m.group(1)
                code, rest = inner[0], inner[1:]
                if '|' in rest:
                    surface, canon = rest.split('|', 1)
                else:
                    surface = canon = rest
                ents.append((m.start(), m.end(), code, surface, canon))
            verbs = [(m.start(), m.end(), m.group(1)[0], m.group(1)[1:])
                     for m in VERB.finditer(line)]
            sents = sentence_ranges(line)
            quotes = quote_ranges(line)

            for vs, ve, code, surface in verbs:
                sent = next((r for r in sents if r[0] <= vs < r[1]), (0, len(line)))
                in_quote = any(qs <= vs < qe for qs, qe in quotes)
                subj = obj = None
                mode = 'plain'
                # 动词前窗口内的 @/◆ 实体（同句、间距≤40）
                pre = [e for e in ents
                       if e[2] in ACTOR_CODES and e[0] >= sent[0]
                       and e[1] <= vs and vs - e[1] <= 40]
                if pre:
                    les, lee, lcode, lsurf, lcanon = pre[-1]
                    gap_last = line[lee:vs]
                    gap_prev = (line[pre[-2][1]:pre[-1][0]]
                                if len(pre) >= 2 else '')
                    PASSIVE = '被给让叫教'
                    # 两实体须同分句（gap_prev 无分句标点）才可构成被动/把字对
                    prev_same_clause = not any(c in gap_prev for c in '，。；：！？、""')
                    if prev_same_clause and '被' in gap_prev:
                        # "OBJ 被 AGT 动词"：被字夹在同分句的两实体之间
                        mode = 'passive'
                        subj = pre[-1][4]
                        obj = pre[-2][4]
                    elif any(c in gap_last for c in PASSIVE):
                        # "… 被/给/让/叫/教 … 动词"：受动者在前
                        mode = 'passive'
                        obj = lcanon
                        mk = max(line.rfind(c, lee, vs) for c in PASSIVE
                                 if line.rfind(c, lee, vs) >= 0)
                        agts = [e for e in ents if e[2] in ACTOR_CODES
                                and mk < e[0] < vs]
                        if agts:
                            subj = agts[-1][4]
                    elif '把' in gap_last or '将' in gap_last:
                        # "（主语）把 OBJ 动词" 或 "（主语）将 OBJ 动词"
                        mode = 'ba'
                        obj = lcanon
                        ba = max(line.rfind('把', lee, vs),
                                 line.rfind('将', lee, vs))
                        if len(pre) >= 2 and pre[-2][1] <= ba \
                                and vs - pre[-2][1] <= 60:
                            subj = pre[-2][4]
                    else:
                        subj = lcanon
                if obj is None:
                    # 动词后窗口找宾语：遇分句标点/引号即截断，不跨分句
                    cut = ve
                    for j in range(ve, min(ve + 30, sent[1], len(line))):
                        if line[j] in '，。；：！？、""':
                            break
                        cut = j + 1
                    post = [e for e in ents
                            if e[2] in ACTOR_CODES and ve <= e[0] < cut]
                    if post:
                        obj = post[0][4]
                # canonical 归一
                subj = name_map.get(subj, subj) if subj else None
                obj = name_map.get(obj, obj) if obj else None
                # 同主体剔除：主宾同名视为无意义
                if subj and obj and subj == obj:
                    obj = None
                conf = ('high' if subj and obj else
                        'medium' if subj or obj else 'low')
                raw = line[max(sent[0], vs - 14):min(sent[1], ve + 14)]
                raw = line[max(sent[0], vs - 14):min(sent[1], ve + 14)]
                excerpt = clean_excerpt(raw) or strip_marks(raw)
                # 内部定位字段（导出 JSON 时剥离），供校订脚本取宽上下文
                events.append({
                    "loc": f"{ch:03d}:{ln_no}", "verb_code": code,
                    "verb": surface, "mode": mode, "in_quote": in_quote,
                    "subject": subj, "object": obj, "confidence": conf,
                    "excerpt": excerpt,
                    "_vs": vs, "_ve": ve, "_line": line,
                })

    stats = defaultdict(lambda: Counter())
    for e in events:
        c = stats[e["verb_code"]]
        c["total"] += 1
        if e["in_quote"]:
            c["in_quote"] += 1
        else:
            c["narr"] += 1
            c[e["confidence"]] += 1
    return reg, events, stats


def main():
    reg, events, stats = extract()
    narrative = [e for e in events if not e["in_quote"]]

    out = {
        "meta": {
            "book": BOOK,
            "chapters": len(glob.glob(os.path.join(TAGGED_DIR, "*.tagged.md"))),
            "schema": "wuxia-tagged-v0.2",
            "events_total": len(events),
            "events_narrative": len(narrative),
            "events_in_quote": len(events) - len(narrative),
            "resolution": "启发式：动词前窗口主语（把/将/被动变式）；动词后窗口宾语；canonical 经登记表别名链归一",
            "note": "confidence: high=主宾俱全 medium=单边 low=双缺；引语内事件不计入正文表",
        },
        "stats": {VERB_NAME[k]: dict(v) for k, v in sorted(stats.items())},
        "events": [{k: v for k, v in e.items() if not k.startswith('_')}
                   for e in events],
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # markdown ---------------------------------------------------------------
    L = ["# 事件表（%s）" % BOOK, "",
         "> 由 scripts/build_event_table.py 生成；定位符=回号:正文行号。",
         "> 主宾为启发式消解（把/将/被动三变式），canonical 已归一；high=主宾俱全。",
         "> 引语内事件不列入本表（仅计入统计）。", ""]

    L.append("## 总量与消解质量")
    L.append("")
    L.append("| 动词类 | 总数 | 引语内 | 叙事层 | high | medium | low |")
    L.append("|---|---|---|---|---|---|---|")
    for k, v in sorted(stats.items()):
        L.append(f"| {VERB_NAME[k]}（{k}） | {v['total']} | {v['in_quote']} "
                 f"| {v['narr']} | {v['high']} | {v['medium']} | {v['low']} |")
    L.append("")

    def rows_of(code):
        rows = [e for e in narrative if e["verb_code"] == code]
        rows.sort(key=lambda e: e["loc"])
        return rows

    for code in ('◉', '○', '◇'):
        rows = rows_of(code)
        L.append(f"## {VERB_NAME[code]}事件（{code}，{len(rows)} 起）")
        L.append("")
        L.append("| 定位 | 施动 | 动词 | 受动 | 置信 | 摘录 |")
        L.append("|---|---|---|---|---|---|")
        for e in rows:
            L.append(f"| {e['loc']} | {e['subject'] or '—'} | {e['verb']} "
                     f"| {e['object'] or '—'} | {e['confidence']} | {e['excerpt']} |")
        L.append("")

    rows = rows_of('▲')
    L.append(f"## 擒控事件（▲，{len(rows)} 起）")
    L.append("")
    L.append("| 定位 | 施动 | 动词 | 受动 | 置信 | 摘录 |")
    L.append("|---|---|---|---|---|---|")
    for e in rows:
        L.append(f"| {e['loc']} | {e['subject'] or '—'} | {e['verb']} "
                 f"| {e['object'] or '—'} | {e['confidence']} | {e['excerpt']} |")
    L.append("")

    # ◈ 聚合
    pairs = Counter()
    for e in narrative:
        if e["verb_code"] == '◈' and e["subject"] and e["object"]:
            pairs[(e["subject"], e["object"])] += 1
    L.append(f"## 交战（◈）对手对聚合 Top 40（共 {sum(pairs.values())} 次有向对）")
    L.append("")
    L.append("| 施动 | 受动 | 次数 |")
    L.append("|---|---|---|")
    for (a, b), n in pairs.most_common(40):
        L.append(f"| {a} | {b} | {n} |")
    L.append("")

    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')

    print(f"events total={len(events)} narrative={len(narrative)} "
          f"in_quote={len(events) - len(narrative)}")
    for k, v in sorted(stats.items()):
        print(f"  {VERB_NAME[k]}({k}): total={v['total']} narr={v['narr']} "
              f"high={v['high']} medium={v['medium']} low={v['low']}")


if __name__ == '__main__':
    main()
