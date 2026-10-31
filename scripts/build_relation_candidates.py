# -*- coding: utf-8 -*-
"""关系候选抽取器：为「门派—拥有—武功」关系规范化收集证据。

用法：python scripts/build_relation_candidates.py [书名]   （默认 白发魔女传）

从 kb/tagged/<书>/ 抽取：
  - 每个 ☆武功 token 的 canonical、定位符、上下文
  - 同句/近邻的 ◆组织 与 @人物（±60 字窗）
  - 归属强标记词：镇山/独门/家传/本门/所授/所传/绝技/成名/号称/自创
  - 形态蕴含：武功名内含组织根（武当剑法⊃武当；组织根映射读自 pipeline配置.json 的 org_roots）
输出 kb/<书>/关系候选报告.md（供主对话 LLM 考订）。
"""
import io, os, re, sys, glob, json
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK = sys.argv[1] if len(sys.argv) > 1 else "白发魔女传"
TAGGED_DIR = os.path.join(ROOT, "kb", "tagged", BOOK)
REGISTRY = os.path.join(ROOT, "kb", BOOK, "实体登记表.json")
OUT = os.path.join(ROOT, "kb", BOOK, "关系候选报告.md")

ENT = re.compile(r'〖([^〖〗]*)〗')
KEYWORDS = ['镇山', '独门', '家传', '本门', '所授', '所传', '绝技', '成名', '号称', '自创', '祖传', '秘传']

# 组织根 → 归一组织名（形态蕴含用）；书专属映射外置 kb/<书>/pipeline配置.json
ORG_ROOTS = {
    '武当': '武当派', '峨眉': '峨嵋派', '峨嵋': '峨嵋派', '少林': '少林派',
    '天龙': '天龙派', '太极': '太极派', '嵩阳': '嵩阳派', '崐卢': '崐卢剑派',
    '华山': '华山派', '天山': '天山派', '唐家': '唐家', '红教': '红教（密宗）',
    '密宗': '红教（密宗）', '达摩': '武当派（达摩祖师）',
}
_CFG = os.path.join(ROOT, "kb", BOOK, "pipeline配置.json")
if os.path.exists(_CFG):
    ORG_ROOTS = json.load(open(_CFG, encoding='utf-8')).get("org_roots", ORG_ROOTS)


def strip_marks(text):
    def ent_repl(m):
        inner = m.group(0)[1:-1]
        rest = inner[1:]
        if '|' in rest:
            rest = rest.split('|', 1)[0]
        return rest
    text = re.sub(r'〖[^〖〗]*〗', ent_repl, text)
    text = re.sub(r'⟦[^⟦⟧]*⟧', lambda m: m.group(0)[1:-1][1:], text)
    return text


def canon_of(inner):
    rest = inner[1:]
    return rest.split('|', 1)[1] if '|' in rest else rest


def main():
    with open(REGISTRY, encoding='utf-8') as f:
        reg = json.load(f)
    name_map = {}
    for key, e in reg["entities"].items():
        if e["type"] in ('@', '◆', '☆'):
            name_map[e["canonical"]] = e["canonical"]
            for s in e.get("surfaces", {}):
                name_map.setdefault(s, e["canonical"])
            for a in e.get("aliases", {}):
                name_map.setdefault(a, e["canonical"])

    arts = defaultdict(lambda: {"count": 0, "locs": [], "ctxs": [],
                                "orgs": defaultdict(int), "persons": defaultdict(int),
                                "keywords": defaultdict(int)})
    for fp in sorted(glob.glob(os.path.join(TAGGED_DIR, "*.tagged.md"))):
        ch = int(re.search(r'(\d{3})_', os.path.basename(fp)).group(1))
        with open(fp, encoding='utf-8') as f:
            lines = f.read().split('\n')
        end = lines.index('---', 1)
        body = lines[end + 1:]
        for ln_no, ln in enumerate(body, 1):
            if re.match(r'^:::', ln):
                continue
            marks = []
            for m in ENT.finditer(ln):
                inner = m.group(1)
                code = inner[0]
                if code in '☆◆@':
                    marks.append((m.start(), m.end(), code, canon_of(inner)))
            plain = strip_marks(ln)
            # plain 映射：粗略按 strip 前后长度差不可靠，改用逐字映射
            pm = [None] * len(ln)
            i = 0
            pi = 0
            while i < len(ln):
                c = ln[i]
                if c in '〖⟦':
                    close = '〗' if c == '〖' else '⟧'
                    j = ln.index(close, i)
                    inner = ln[i + 1:j]
                    if c == '〖':
                        bar = inner.find('|')
                        e2 = bar if bar >= 0 else len(inner)
                    else:
                        e2 = len(inner)
                    for m in range(1, e2):
                        pm[i + 1 + m] = pi
                        pi += 1
                    i = j + 1
                else:
                    pm[i] = pi
                    pi += 1
                    i += 1
            inv = {}
            for tpos, p in enumerate(pm):
                if p is not None and p not in inv:
                    inv[p] = tpos
            for s, e, code, canon in marks:
                if code != '☆':
                    continue
                a = arts[canon]
                a["count"] += 1
                loc = f"{ch:03d}:{ln_no}"
                a["locs"].append(loc)
                p0 = inv.get(pm[s + 2]) if s + 2 < len(pm) else None
                if p0 is None:
                    continue
                ctx = plain[max(0, p0 - 55):p0 + len(canon) + 55]
                if len(a["ctxs"]) < 2:
                    a["ctxs"].append((loc, ctx))
                # 近邻组织/人物（plain 距离 ≤60）
                for s2, e2, code2, canon2 in marks:
                    if code2 == '☆' or (s2, e2) == (s, e):
                        continue
                    p2 = inv.get(pm[s2 + 2]) if s2 + 2 < len(pm) else None
                    if p2 is None:
                        continue
                    d = abs(p2 - p0)
                    if d <= 60:
                        cc = name_map.get(canon2, canon2)
                        if code2 == '◆':
                            a["orgs"][cc] += 1
                        else:
                            a["persons"][cc] += 1
                # 强标记词
                for kw in KEYWORDS:
                    if kw in ctx:
                        a["keywords"][kw] += 1

    # 输出报告 -------------------------------------------------------------
    def morph(canon):
        for root, org in ORG_ROOTS.items():
            if root in canon:
                return org
        return None

    rows = sorted(arts.items(), key=lambda kv: -kv[1]["count"])
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write("# 关系候选报告（门派—拥有—武功）\n\n"
                "> 由 scripts/build_relation_candidates.py 生成；供主对话 LLM 考订。\n"
                "> 「形⊂」=武功名内含组织根（形态蕴含归属）；近邻=±60 字内出现的组织/人物。\n\n")
        f.write(f"☆ canonical 总数：{len(arts)}，token 总数：{sum(a['count'] for a in arts.values())}\n\n")
        for canon, a in rows:
            mo = morph(canon)
            orgs = "、".join(f"{k}({v})" for k, v in
                             sorted(a["orgs"].items(), key=lambda kv: -kv[1])[:4]) or "—"
            pers = "、".join(f"{k}({v})" for k, v in
                             sorted(a["persons"].items(), key=lambda kv: -kv[1])[:4]) or "—"
            kws = "、".join(a["keywords"]) or "—"
            f.write(f"## {canon}　×{a['count']}"
                    f"{'　【形⊂' + mo + '】' if mo else ''}\n")
            f.write(f"- 近邻组织: {orgs}｜近邻人物: {pers}｜标记词: {kws}\n")
            f.write(f"- 章节: {a['locs'][0]}…{a['locs'][-1]}\n")
            for loc, ctx in a["ctxs"]:
                f.write(f"- 例[{loc}]: …{ctx}…\n")
            f.write("\n")
    print(f"arts={len(arts)} tokens={sum(a['count'] for a in arts.values())}")
    print("report ->", os.path.relpath(OUT, ROOT))


if __name__ == '__main__':
    main()
