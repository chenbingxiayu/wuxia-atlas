# -*- coding: utf-8 -*-
"""实体登记表生成器（实体归一层 · shiji-kb 管线「实体构建」阶段产出）

用法：python scripts/build_entity_registry.py [书名]   （默认 白发魔女传）

从 kb/tagged/<书>/ 的全部标注文件抽取实体/动词标记，生成：
  kb/<书>/实体登记表.json
    - entities: 按 canonical 聚合（管道 | 规范名优先；别名链自动解析到根）
    - verb_anchors: ◉◈○▲◇ 锚点定位符（供事件层半自动抽取）
    - merge_candidates: 同类型柄的子串包含启发 + 人工核定别名组
人工核定别名组读自 kb/<书>/pipeline配置.json 的 manual_merges。
定位符格式：回号:正文行号（YAML 头之后第 1 行 = 1），与 版权合规 的引用方案一致。
"""
import io, json, os, re, sys, glob
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK = sys.argv[1] if len(sys.argv) > 1 else "白发魔女传"
TAGGED_DIR = os.path.join(ROOT, "kb", "tagged", BOOK)
OUT_JSON = os.path.join(ROOT, "kb", BOOK, "实体登记表.json")
OUT_MD = os.path.join(ROOT, "kb", BOOK, "实体归并清单.md")

CFG_PATH = os.path.join(ROOT, "kb", BOOK, "pipeline配置.json")
CFG = json.load(open(CFG_PATH, encoding='utf-8')) if os.path.exists(CFG_PATH) else {}

YAML_FENCE = re.compile(r'^---')
FENCE = re.compile(r'^:::')
ENT = re.compile(r'〖([^〖〗]*)〗')
VERB = re.compile(r'⟦([^⟦⟧]*)⟧')

# 人工核定别名组（同一人物的并列 handle，canonical 取实名/最常用正式全称）
# 读自 kb/<书>/pipeline配置.json；白发魔女传组表为历史基线（亦已外置）。
MANUAL_MERGES = CFG.get("manual_merges", [
    ["白石道人", "白石"],
    ["黄叶道人", "黄叶"],
    ["红云道人", "红云"],
    ["青蓑道人", "青蓑"],
    ["慈慧师太", "慈慧", "何绮霞", "绮霞"],
    ["镜明长老", "镜明大师", "镜明"],
    ["李天扬", "天扬"],
    ["卓一航", "一航"],
    ["何萼华", "萼华"],
    ["练霓裳", "玉罗刹", "白发魔女", "霓裳", "裳儿", "练姐姐"],
    ["铁飞龙", "铁老英雄", "铁老儿"],
    ["岳鸣珂", "晦明禅师", "鸣珂"],
    ["辛龙子", "龙子"],
    ["飞红巾", "哈玛雅", "小飞红巾"],
    ["李自成", "小闯王", "闯王"],
    ["高迎祥", "闯王"],
    ["慕容冲", "慕容总管"],
    ["连城虎", "连总管"],
    ["应修阳", "应都头"],
    ["金独异", "金老怪", "金老爹", "金老前辈", "金老大"],
    ["客娉婷", "娉婷", "婷儿"],
    ["魏忠贤", "魏公公", "魏宗主", "厂臣", "忠贤"],
    ["朱由校", "由校", "由哥儿"],
    ["朱由检", "崇祯", "信王"],
    ["朱翊钧", "神宗"],
    ["常洛", "光宗"],
    ["霍天都", "天都居士", "天都老人"],
    ["孟秋霞", "孟小姐", "孟师妹"],
    ["杨涟", "杨大人"],
    ["唐努", "唐努王爷"],
    ["成章五", "成堡主", "风砂堡主"],
    ["杜明忠", "杜明七", "杜明思", "杜兄", "明忠"],
    ["朱宝椿", "朱宝桩", "朱寨主", "火灵猿"],
    ["王照希", "王熙希", "照希"],
    ["张献忠", "八大王"],
    ["努尔哈赤", "大汗"],
    ["昌钦大喇嘛", "昌钦喇嘛", "昌钦法师", "昌钦大法师"],
    ["袁崇焕", "袁相公"],
])

def resolve_root(name, alias_map, depth=0):
    """别名链解析：若 canonical 本身又挂靠到另一 canonical，追到根。"""
    seen = set()
    while name in alias_map and name not in seen and depth < 10:
        seen.add(name)
        name = alias_map[name]
    return name

def main():
    files = sorted(glob.glob(os.path.join(TAGGED_DIR, "*.tagged.md")))
    n_ch = len(glob.glob(os.path.join(ROOT, "章回版", BOOK, "*.txt")))
    assert n_ch and len(files) == n_ch, \
        f"tagged {len(files)} != 章回版 {n_ch} 回，标注未完成或有缺漏"

    # token 级抽取 -----------------------------------------------------------
    ent_tokens = []   # (chapter, line_no, code, surface, canonical)
    verb_tokens = []  # (chapter, line_no, code, surface)
    type_dist = defaultdict(int)

    for fp in files:
        ch = int(re.search(r'(\d{3})_', os.path.basename(fp)).group(1))
        with open(fp, encoding='utf-8') as f:
            lines = f.read().split('\n')
        # 跳过 YAML 头
        assert lines[0].strip() == '---'
        end = lines.index('---', 1)
        body = lines[end + 1:]
        for i, ln in enumerate(body, 1):
            if FENCE.match(ln):
                continue
            for m in ENT.finditer(ln):
                inner = m.group(1)
                code, rest = inner[0], inner[1:]
                if '|' in rest:
                    surface, canon = rest.split('|', 1)
                else:
                    surface = canon = rest
                ent_tokens.append((ch, i, code, surface, canon))
                type_dist[code] += 1
            for m in VERB.finditer(ln):
                inner = m.group(1)
                verb_tokens.append((ch, i, inner[0], inner[1:]))

    # 聚合 -------------------------------------------------------------------
    # canonical_key = f"{code}{canon}"，别名链：pipe 指向的 canonical 若与另一些柄构成同人物组，
    # 用 MANUAL_MERGES 归组；组内取"出现次数最多的柄"为根（保证统计上以主流写法聚合）。
    counts = defaultdict(int)           # (code, name) -> n
    surfaces = defaultdict(lambda: defaultdict(int))  # (code, canon) -> {surface: n}
    chapters = defaultdict(set)         # (code, canon) -> set(ch)
    locators = defaultdict(list)        # (code, canon) -> ["016:12", ...]
    for ch, ln, code, surface, canon in ent_tokens:
        key = (code, canon)
        counts[key] += 1
        surfaces[key][surface] += 1
        chapters[key].add(ch)
        locators[key].append(f"{ch:03d}:{ln}")

    # 人工别名组 -> 组根取组内首个在库成员（列表首元素 = 规范名优先），其余挂靠
    alias_map = {}   # name -> group_root
    for group in MANUAL_MERGES:
        tally = defaultdict(int)
        for (c, n), cnt in counts.items():
            if n in group:
                tally[n] += cnt
        present_names = [n for n in group if tally.get(n, 0) > 0]
        if len(present_names) < 2:
            continue
        root = present_names[0]
        for n in present_names:
            if n != root:
                alias_map[n] = root

    entities = {}
    for (code, canon), cnt in counts.items():
        root = resolve_root(canon, alias_map)
        rkey = f"{code}{root}"
        e = entities.setdefault(rkey, {
            "type": code, "canonical": root, "aliases": {}, "count": 0,
            "chapters": [], "locators": [],
        })
        e["aliases"][canon if canon == root else canon] = \
            e["aliases"].get(canon, 0) + cnt
        # surface 明细并入组根
        for s, n in surfaces[(code, canon)].items():
            e["aliases"].setdefault(f"surface:{s}", 0)
            e["aliases"][f"surface:{s}"] += n
        e["count"] += cnt
        for c in chapters[(code, canon)]:
            if c not in e["chapters"]:
                e["chapters"].append(c)
        e["locators"].extend(locators[(code, canon)])

    for e in entities.values():
        e["chapters"].sort()
        e["locators"].sort()
        # aliases 里把 surface: 前缀项单独抽出来
        e["surfaces"] = {k[len('surface:'):]: v for k, v in e["aliases"].items()
                         if k.startswith('surface:')}
        e["aliases"] = {k: v for k, v in e["aliases"].items()
                        if not k.startswith('surface:')}

    # 归并候选 ---------------------------------------------------------------
    # 仅对 @（人物柄）做子串包含启发——时间/地名等的子串关系多为噪声（三年≠三十年）。
    merged_keys = set()
    for root in set(alias_map.values()):
        for (c, n) in list(counts.keys()):
            if resolve_root(n, alias_map) == root and n != root:
                merged_keys.add((c, n))

    cands = []
    by_type = defaultdict(list)
    for (code, canon) in counts:
        by_type[code].append(canon)
    for code, names in by_type.items():
        if code != '@':
            continue
        names = sorted(set(names), key=lambda x: -counts[(code, x)])
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if len(a) >= 2 and (a in b) and a != b:
                    if (resolve_root(a, alias_map) == resolve_root(b, alias_map)):
                        continue
                    cands.append({
                        "type": code, "a": a, "b": b,
                        "a_count": counts[(code, a)], "b_count": counts[(code, b)],
                        "hint": "子串包含，疑似同柄全称/简写",
                    })

    registry = {
        "meta": {
            "book": BOOK, "chapters": len(files), "schema": CFG.get("schema", "wuxia-tagged-v0.2"),
            "entity_tokens": len(ent_tokens), "verb_tokens": len(verb_tokens),
            "canonical_entities": len(entities),
            "alias_groups": len({r for r in alias_map.values()}),
            "note": "定位符=回号:正文行号（YAML 头后第 1 行=1）；别名链已解析到组根",
        },
        "type_distribution": dict(sorted(type_dist.items(),
                                         key=lambda kv: -kv[1])),
        "entities": dict(sorted(entities.items(),
                                key=lambda kv: -kv[1]["count"])),
        "merge_candidates": sorted(cands,
                                   key=lambda c: -(c["a_count"] + c["b_count"])),
        "verb_anchors": {},
    }
    va = defaultdict(list)
    for ch, ln, code, surface in verb_tokens:
        va[code].append(f"{ch:03d}:{ln}:{surface}")
    registry["verb_anchors"] = {k: sorted(v) for k, v in va.items()}

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=1)

    # 归并清单 markdown ------------------------------------------------------
    top = list(registry["entities"].items())
    lines = ["# 实体归并清单（%s）" % BOOK, "",
             "> 由 scripts/build_entity_registry.py 生成；定位符=回号:正文行号。",
             "> 「已归并」= 人工核定别名组（脚本 MANUAL_MERGES）；「候选」= 子串包含启发，待人工复核。",
             ""]
    lines.append(f"- 实体标记 {len(ent_tokens)} 处 → 规范实体 {len(entities)} 个"
                 f"（别名组 {registry['meta']['alias_groups']} 个）")
    lines.append(f"- 动词锚点 {len(verb_tokens)} 处")
    lines.append("")
    lines.append("## 已归并的别名组（组根 ← 组员）")
    lines.append("")
    groups = defaultdict(list)
    for member, root in alias_map.items():
        groups[root].append(member)
    for root in sorted(groups, key=lambda r: -sum(counts[(c, n)]
                       for (c, n) in counts if resolve_root(n, alias_map) == r)):
        members = ", ".join(sorted(groups[root]))
        total = sum(cnt for (c, n), cnt in counts.items()
                    if resolve_root(n, alias_map) == root)
        lines.append(f"- **{root}**（{total} 处）← {members}")
    lines.append("")
    lines.append("## 归并候选（待人工复核）")
    lines.append("")
    if cands:
        lines.append("| 类型 | 候选 A | 次数 | 候选 B | 次数 | 说明 |")
        lines.append("|---|---|---|---|---|---|")
        for c in cands:
            lines.append(f"| {c['type']} | {c['a']} | {c['a_count']} | "
                         f"{c['b']} | {c['b_count']} | {c['hint']} |")
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## Top 40 规范实体")
    lines.append("")
    lines.append("| 键 | 类型 | 规范名 | 出现 | 别名（→次数） | 章节跨度 |")
    lines.append("|---|---|---|---|---|---|")
    for key, e in top[:40]:
        al = "、".join(f"{k}({v})" for k, v in
                       sorted(e["aliases"].items(), key=lambda kv: -kv[1])[:6])
        lines.append(f"| {key} | {e['type']} | {e['canonical']} | {e['count']} "
                     f"| {al} | {e['chapters'][0]:03d}–{e['chapters'][-1]:03d} |")
    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"entity tokens: {len(ent_tokens)}, verb tokens: {len(verb_tokens)}")
    print(f"canonical entities: {len(entities)}, alias groups: {registry['meta']['alias_groups']}")
    print(f"merge candidates: {len(cands)}")
    print("Top 10:")
    for key, e in top[:10]:
        print(f"  {key}  {e['count']:4d}  aliases={list(e['aliases'])[:5]}")

if __name__ == '__main__':
    main()
