# -*- coding: utf-8 -*-
"""校订合并应用器：把核心 TSV + ◈ 子代理 TSV 应用回事件表。

用法：python scripts/apply_curation.py [书名]   （默认 白发魔女传）
前置：scripts/build_event_table.py 已导出内部定位字段（_vs/_ve/_line）。
产出：
  kb/<书>/事件表.json        — v2：curation 字段 + 修正后的主宾 + dropped 标记
  kb/<书>/事件表.md          — v2：剔除 dropped，置信为校订后值（✎ 标记校订行）
  kb/<书>/校订报告.md        — 校订统计与明细
"""
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_event_table as bet  # noqa: E402
import glob as _glob, re as _re, json as _json

if len(sys.argv) > 1:
    bet.BOOK = sys.argv[1]
BOOK = bet.BOOK

CUR_DIR = os.path.join(bet.ROOT, "kb", BOOK, "校订")
TSV_CORE = os.path.join(CUR_DIR, "校订-核心.tsv")
TSV_WU = sorted(_glob.glob(os.path.join(CUR_DIR, "校订-◈-*.tsv")),
                key=lambda p: int(_re.search(r'(\d+)\.tsv$', p).group(1)))
OUT_JSON = os.path.join(bet.ROOT, "kb", BOOK, "事件表.json")
OUT_MD = os.path.join(bet.ROOT, "kb", BOOK, "事件表.md")
OUT_REPORT = os.path.join(bet.ROOT, "kb", BOOK, "校订报告.md")


def load_tsv(path):
    rows = {}
    if not os.path.exists(path):
        return rows, 0
    with open(path, encoding='utf-8') as f:
        for ln in f:
            ln = ln.rstrip('\n')
            if not ln.strip():
                continue
            parts = ln.split('\t')
            if len(parts) < 5 or not parts[0].startswith('E'):
                continue
            eid = int(parts[0][1:])
            rows[eid] = {"verdict": parts[1].strip(),
                         "subject": None if parts[2].strip() == '-' else parts[2].strip(),
                         "object": None if parts[3].strip() == '-' else parts[3].strip(),
                         "note": parts[4].strip() if len(parts) > 4 else ''}
    return rows, len(rows)


def main():
    name_map = bet.load_name_map()
    reg, events, stats = bet.extract()
    ml = [e for e in events if not e["in_quote"]
          and e["confidence"] in ("medium", "low")]
    # 与 extract_curation_contexts.py 相同的稳定序号
    for i, e in enumerate(ml):
        e["_eid"] = i

    all_rows = {}
    loaded = []
    for p in [TSV_CORE] + TSV_WU:
        rows, n = load_tsv(p)
        loaded.append((os.path.basename(p), n))
        all_rows.update(rows)

    # 人工复核覆盖：drop复核-*.tsv（复核结论列非空的行生效）
    n_ov = 0
    for review_path in sorted(_glob.glob(os.path.join(CUR_DIR, 'drop复核-*.tsv'))):
        with open(review_path, encoding='utf-8') as f:
            next(f, None)
            for ln in f:
                p = ln.rstrip('\n').split('\t')
                if len(p) < 6 or not p[0].startswith('E'):
                    continue
                verdict = p[5].strip()
                if not verdict:
                    continue
                eid = int(p[0][1:])
                if verdict == '维持':
                    pass  # 保持 drop，无需改动
                elif verdict == '误删':
                    subj = p[6].strip() if len(p) > 6 else ''
                    obj = p[7].strip() if len(p) > 7 else ''
                    note = p[8].strip() if len(p) > 8 else ''
                    if subj or obj:
                        all_rows[eid] = {"verdict": "fix",
                                         "subject": subj or None,
                                         "object": obj or None,
                                         "note": f"复核误删恢复: {note}"}
                    else:
                        all_rows[eid] = {"verdict": "correct", "subject": None,
                                         "object": None,
                                         "note": "复核误删恢复(启发式原值)"}
                else:
                    print(f"WARNING: 未知复核结论 {verdict!r} @ {p[0]}（应为 维持/误删）")
                n_ov += 1
        if n_ov:
            print(f"review overrides: {n_ov} rows read")
    print("loaded:", loaded, "total unique eids:", len(all_rows))

    missing = [e["_eid"] for e in ml if e["_eid"] not in all_rows]
    if missing:
        print(f"WARNING: {len(missing)} events lack curation rows, e.g. {missing[:10]}")

    summary = {"correct": 0, "fixed": 0, "dropped": 0, "unsure": 0}
    fixes = []
    for e in ml:
        r = all_rows.get(e["_eid"])
        if not r:
            e["_curation"] = {"verdict": "uncurated"}
            continue
        v = r["verdict"]
        cur = {"verdict": v, "note": r["note"]}
        if v == "correct":
            summary["correct"] += 1
        elif v == "fix":
            summary["fixed"] += 1
            cur["before"] = [e["subject"], e["object"]]
            e["subject"] = name_map.get(r["subject"], r["subject"]) if r["subject"] else None
            e["object"] = name_map.get(r["object"], r["object"]) if r["object"] else None
            if e["subject"] and e["object"] and e["subject"] == e["object"]:
                e["object"] = None
            e["confidence"] = ("high" if e["subject"] and e["object"]
                               else "medium" if e["subject"] or e["object"] else "low")
            fixes.append((e["_eid"], e["loc"], e["verb_code"] + e["verb"],
                          cur["before"], [e["subject"], e["object"]], r["note"]))
        elif v == "drop":
            summary["dropped"] += 1
            e["_dropped"] = True
        else:
            summary["unsure"] += 1
        e["_curation"] = cur

    # 统计重算（剔除 dropped）
    st = {}
    narrative = [e for e in events if not e["in_quote"] and not e.get("_dropped")]
    for e in narrative:
        c = st.setdefault(e["verb_code"], {"total": 0, "in_quote": 0, "narr": 0,
                                           "high": 0, "medium": 0, "low": 0,
                                           "curated": 0})
        c["narr"] += 1
        c["total"] += 1
        c[e["confidence"]] += 1
        if e.get("_curation", {}).get("verdict") in ("correct", "fix"):
            c["curated"] += 1
    for e in events:
        if e["in_quote"]:
            st.setdefault(e["verb_code"], {"total": 0, "in_quote": 0, "narr": 0,
                                           "high": 0, "medium": 0, "low": 0,
                                           "curated": 0})
            st[e["verb_code"]]["in_quote"] += 1
            st[e["verb_code"]]["total"] += 1

    def public(e):
        d = {k: v for k, v in e.items() if not k.startswith('_')}
        d["curation"] = e.get("_curation", {"verdict": "none"})
        if e.get("_dropped"):
            d["dropped"] = True
        return d

    out = {
        "meta": {
            "book": BOOK,
            "chapters": len(_glob.glob(os.path.join(bet.ROOT, "kb", "tagged", BOOK, "*.tagged.md"))),
            "schema": "wuxia-tagged-v0.2",
            "events_total": len(events),
            "events_narrative": len(narrative),
            "events_dropped": summary["dropped"],
            "resolution": "启发式初解 + LLM 逐条语境校订（核心类型主对话内校订；◈ 交战分批并行子代理校订）",
            "curation_summary": summary,
            "note": "confidence 为校订后值；curation.verdict: correct=复核一致 fixed=已修正 dropped=判定非事件 unsure=存疑",
        },
        "stats": {bet.VERB_NAME[k]: v for k, v in sorted(st.items())},
        "events": [public(e) for e in events],
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        import json
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ---- 事件表.md v2 ----
    L = ["# 事件表（%s，校订版 v2）" % BOOK, "",
         "由 scripts/apply_curation.py 生成；定位符=回号:正文行号。",
         "主宾为「启发式初解 + LLM 逐条语境校订」后的值；置信列带 ✎ 者为 LLM 校订行。",
         "判定为非事件（比喻/假设/回述/重复）的条目已剔除，见《校订报告.md》。", ""]
    L.append("## 总量与消解质量（校订后）")
    L.append("")
    L.append("| 动词类 | 叙事层 | 校订 | high | medium | low | 引语内(不计) |")
    L.append("|---|---|---|---|---|---|---|")
    for k, v in sorted(st.items()):
        L.append(f"| {bet.VERB_NAME[k]}（{k}） | {v['narr']} | {v['curated']} "
                 f"| {v['high']} | {v['medium']} | {v['low']} | {v['in_quote']} |")
    L.append("")

    def rows_of(code):
        rs = [e for e in narrative if e["verb_code"] == code]
        rs.sort(key=lambda e: e["loc"])
        return rs

    def table(rows, title):
        L.append(f"## {title}（{len(rows)} 起）")
        L.append("")
        L.append("| 定位 | 施动 | 动词 | 受动 | 置信 | 摘录 |")
        L.append("|---|---|---|---|---|---|")
        for e in rows:
            mark = "✎" if e.get("_curation", {}).get("verdict") in ("correct", "fix") else ""
            L.append(f"| {e['loc']} | {e['subject'] or '—'} | {e['verb']} "
                     f"| {e['object'] or '—'} | {e['confidence']}{mark} | {e['excerpt']} |")
        L.append("")

    for code, name in (("◉", "杀伐事件"), ("○", "拜认结盟事件"), ("◇", "传艺事件"),
                       ("▲", "擒控事件")):
        table(rows_of(code), f"{name}（{code}）")

    pairs = {}
    for e in narrative:
        if e["verb_code"] == "◈" and e["subject"] and e["object"]:
            key = (e["subject"], e["object"])
            pairs[key] = pairs.get(key, 0) + 1
    L.append(f"## 交战（◈）对手对聚合 Top 40（共 {sum(pairs.values())} 次有向对）")
    L.append("")
    L.append("| 施动 | 受动 | 次数 |")
    L.append("|---|---|---|")
    for (a, b), n in sorted(pairs.items(), key=lambda kv: -kv[1])[:40]:
        L.append(f"| {a} | {b} | {n} |")
    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')

    # ---- 校订报告 ----
    R = ["# 事件校订报告（medium/low 档全量复核）", "",
         f"- 待校订事件：{len(ml)} 起（核心类型 {len([e for e in ml if e['verb_code']!='◈'])} 起 + ◈交战 {len([e for e in ml if e['verb_code']=='◈'])} 起）",
         f"- 覆盖：{sum(summary.values())} 起（correct {summary['correct']} / fixed {summary['fixed']} / dropped {summary['dropped']} / unsure {summary['unsure']}）",
         "- 校订方式：核心类型（◉▲○◇）由主对话 LLM 逐条阅读 ±170 字上下文裁定；◈交战由 6 个并行子代理按同一规则集逐条裁定。",
         "", "## 修正明细（fixed）", ""]
    R.append("| E | 定位 | 动词 | 原(主,宾) | 新(主,宾) | 理由 |")
    R.append("|---|---|---|---|---|---|")
    for eid, loc, verb, old, new, note in fixes:
        R.append(f"| E{eid} | {loc} | {verb} | {old[0] or '—'},{old[1] or '—'} "
                 f"| {new[0] or '—'},{new[1] or '—'} | {note} |")
    R.append("")
    R.append("## 剔除明细（dropped，判定为非事件）")
    R.append("")
    R.append("| E | 定位 | 动词 | 理由 |")
    R.append("|---|---|---|---|")
    for e in ml:
        c = e.get("_curation", {})
        if c.get("verdict") == "drop":
            R.append(f"| E{e['_eid']} | {e['loc']} | {e['verb_code']}{e['verb']} | {c.get('note','')} |")
    with open(OUT_REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(R) + '\n')

    print("summary:", summary)
    print("events json/md/report rewritten")


if __name__ == '__main__':
    main()
