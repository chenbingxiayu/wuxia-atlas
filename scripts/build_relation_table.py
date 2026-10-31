# -*- coding: utf-8 -*-
"""关系表合成器：门派/人物—拥有/独门/修习/传授—武功。

用法：python scripts/build_relation_table.py [书名]   （默认 白发魔女传）

输入：kb/<书>/关系考订.tsv（主对话 LLM 考订结果）
扫描 kb/tagged/<书>/ 采集 ☆/• token 定位符，按别名归一后作为关系证据。
输出：kb/<书>/关系表.json + 武功归属表.md
"""
import io, os, re, sys, glob, json
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK = sys.argv[1] if len(sys.argv) > 1 else "白发魔女传"
TAGGED_DIR = os.path.join(ROOT, "kb", "tagged", BOOK)
REGISTRY = os.path.join(ROOT, "kb", BOOK, "实体登记表.json")
TSV = os.path.join(ROOT, "kb", BOOK, "关系考订.tsv")
OUT_JSON = os.path.join(ROOT, "kb", BOOK, "关系表.json")
OUT_MD = os.path.join(ROOT, "kb", BOOK, "武功归属表.md")

ENT = re.compile(r'〖([^〖〗]*)〗')


def canon_of(inner):
    rest = inner[1:]
    return rest.split('|', 1)[1] if '|' in rest else rest


def main():
    with open(REGISTRY, encoding='utf-8') as f:
        reg = json.load(f)
    name_map = {}
    for key, e in reg["entities"].items():
        name_map.setdefault(e["canonical"], e["canonical"])
        for s in e.get("surfaces", {}):
            name_map.setdefault(s, e["canonical"])
        for a in e.get("aliases", {}):
            name_map.setdefault(a, e["canonical"])

    # 1) 扫描 ☆/• token 定位符
    locs = defaultdict(list)     # canonical -> [loc]
    for fp in sorted(glob.glob(os.path.join(TAGGED_DIR, "*.tagged.md"))):
        ch = int(re.search(r'(\d{3})_', os.path.basename(fp)).group(1))
        with open(fp, encoding='utf-8') as f:
            lines = f.read().split('\n')
        end = lines.index('---', 1)
        for ln_no, ln in enumerate(lines[end + 1:], 1):
            for m in ENT.finditer(ln):
                inner = m.group(1)
                if inner[0] in '☆•':
                    locs[canon_of(inner)].append(f"{ch:03d}:{ln_no}")
    for k in locs:
        locs[k] = sorted(set(locs[k]))

    # 2) 读考订 TSV
    relations = []
    alias = defaultdict(set)     # canonical art -> {variant}
    with open(TSV, encoding='utf-8') as f:
        for ln in f:
            ln = ln.rstrip('\n')
            if not ln.strip() or ln.startswith('subject'):
                continue
            p = ln.split('\t')
            if len(p) < 6:
                continue
            subj, stype, pred, obj, otype, note = [x.strip() for x in p[:6]]
            if pred == '别名':
                alias[subj].add(obj)
            else:
                relations.append({"subject": name_map.get(subj, subj),
                                  "subject_type": stype, "predicate": pred,
                                  "object": obj, "object_type": otype,
                                  "note": note})

    # 3) 证据挂接
    for r in relations:
        ev = set(locs.get(r["object"], []))
        for v in alias.get(r["object"], ()):
            ev.update(locs.get(v, []))
        r["evidence_locators"] = sorted(ev)
        r["evidence_count"] = len(r["evidence_locators"])

    # 4) 输出
    out = {
        "meta": {
            "book": BOOK, "schema": "wuxia-tagged-v0.2",
            "relation_types": ["镇山", "拥有", "独门", "创制", "修习", "传授", "别名"],
            "subject_types": ["◆ 门派/家族", "@ 人物"],
            "note": "subject/object 均经实体登记表 canonical 归一；evidence_locators=回号:正文行号（武功 token 出现处，别名并入）",
        },
        "relations": relations,
        "art_aliases": {k: sorted(v) for k, v in alias.items()},
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # md：按 subject 分组
    order = {"镇山": 0, "拥有": 1, "独门": 2, "创制": 3, "修习": 4, "传授": 5}
    L = ["# 武功归属表（门派—拥有—武功 关系规范化）", "",
         "> 由 scripts/build_relation_table.py 合成；考订=主对话 LLM 逐条裁定（关系考订.tsv）。",
         "> 证据 = 该武功 token（含别名）在 32 回中的定位符；subject/object 已 canonical 归一。", ""]
    subs = []
    for r in relations:
        if r["subject"] not in subs:
            subs.append(r["subject"])
    for s in subs:
        rs = [r for r in relations if r["subject"] == s]
        rs.sort(key=lambda r: order.get(r["predicate"], 9))
        st = rs[0]["subject_type"]
        f.write = None  # noop guard
        L.append(f"## {s}（{st}）")
        L.append("")
        L.append("| 谓词 | 武功 | 证据数 | 证据（首3+跨度） | 备注 |")
        L.append("|---|---|---|---|---|")
        for r in rs:
            ev = r["evidence_locators"]
            ev_s = f"{ev[0]}…{ev[-1]}" if ev else "—"
            L.append(f"| {r['predicate']} | {r['object']}（{r['object_type']}） "
                     f"| {r['evidence_count']} | {ev_s} | {r['note']} |")
        L.append("")
    L.append("## 武功别名归一")
    L.append("")
    L.append("| 规范名 | 别名（语料面值） |")
    L.append("|---|---|")
    for k in sorted(alias):
        L.append(f"| {k} | {'、'.join(sorted(alias[k]))} |")
    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')

    n_org = sum(1 for r in relations if r["subject_type"] == '◆')
    n_per = len(relations) - n_org
    print(f"relations={len(relations)} (org={n_org}, person={n_per}), "
          f"aliases={sum(len(v) for v in alias.values())}")
    print("->", os.path.relpath(OUT_JSON, ROOT))
    print("->", os.path.relpath(OUT_MD, ROOT))


if __name__ == '__main__':
    main()
