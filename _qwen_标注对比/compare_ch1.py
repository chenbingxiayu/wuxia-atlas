# -*- coding: utf-8 -*-
"""对比已有第一回标注（manual-seed）与 qwen3.8-27B 重标注结果，生成差异报告。"""
import io
import os
import re
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "_qwen_标注对比")

OLD = os.path.join(ROOT, "kb", "tagged", "白发魔女传", "001_第一回.tagged.md")
NEW = os.path.join(OUT_DIR, "001_第一回.tagged.md")
REPORT = os.path.join(OUT_DIR, "对比报告-第一回.md")

TAG_RE = re.compile(r"(〖[^〖〗]*〗|⟦[^⟦⟧]*⟧)")
CODE_NAME = {
    "@": "人物", "=": "地点", "◆": "组织", ";": "职衔称谓", "%": "时间",
    "☆": "武功", "•": "兵器宝物", "§": "丹药", "+": "坐骑", "[": "秘籍文书",
    "◉": "杀伐", "◈": "交战", "○": "拜认结盟", "▲": "擒控", "◇": "传艺",
}


def parse(path):
    """返回 (paras, tags)。paras=含标记的段落行；tags=[(para_idx, kind, code, surface, canonical)]"""
    raw = open(path, encoding="utf-8").read()
    if raw.startswith("---"):
        end = raw.index("\n---", 3)
        body = raw[raw.index("\n", end + 1) + 1:]
    paras, tags = [], []
    for ln in body.split("\n"):
        if re.match(r"^:::(\s+\S+)?\s*$", ln):
            continue
        if not ln.strip():
            continue
        pi = len(paras)
        paras.append(ln)
        for m in TAG_RE.finditer(ln):
            tok = m.group(0)
            inner = tok[1:-1]
            code, surface = inner[0], inner[1:]
            canonical = ""
            if "|" in surface:
                surface, canonical = surface.split("|", 1)
            kind = "entity" if tok[0] == "〖" else "verb"
            tags.append((pi, kind, code, surface, canonical))
    return paras, tags


def norm_key(t):
    """实体语义身份：挂管道者以规范名为准。"""
    _, kind, code, surface, canonical = t
    return (kind, code, canonical or surface)


def main():
    old_paras, old_tags = parse(OLD)
    new_paras, new_tags = parse(NEW)

    assert len(old_paras) == len(new_paras), \
        f"段数不一致 old={len(old_paras)} new={len(new_paras)}"

    rows = []
    rows.append("# qwen3.8-27B 重标注第一回 · 对比报告\n")
    rows.append("- 基线：`kb/tagged/白发魔女传/001_第一回.tagged.md`（annotator: manual-seed，人工种子）")
    rows.append("- 新标：`_qwen_标注对比/001_第一回.tagged.md`（annotator: qwen3.8-27B-api，分块调用 + 机械回锚）")
    rows.append(f"- 段落数：{len(old_paras)}（两文件一致，段序即原文叙事段序）\n")

    # 一、总量与分布
    oc = Counter(t[2] for t in old_tags)
    nc = Counter(t[2] for t in new_tags)
    rows.append("## 一、标记总量与类型分布\n")
    rows.append("| 类型码 | 含义 | 旧(人工) | 新(qwen) | 差值 |")
    rows.append("|---|---|---:|---:|---:|")
    for code in sorted(set(oc) | set(nc), key=lambda c: -max(oc.get(c, 0), nc.get(c, 0))):
        rows.append(f"| {code} | {CODE_NAME.get(code,'?')} | {oc.get(code,0)} | {nc.get(code,0)} | {nc.get(code,0)-oc.get(code,0):+d} |")
    rows.append(f"| **合计** | | **{len(old_tags)}** | **{len(new_tags)}** | **{len(new_tags)-len(old_tags):+d}** |\n")

    # 二、实体语义身份差异
    ok = Counter(norm_key(t) for t in old_tags if t[1] == "entity")
    nk = Counter(norm_key(t) for t in new_tags if t[1] == "entity")
    only_old, only_new = ok - nk, nk - ok
    rows.append("## 二、实体差异（挂管道者按规范名归一后计数）\n")
    def ent_table(counter, title):
        rows.append(f"### {title}（共 {sum(counter.values())} 处）\n")
        if not counter:
            rows.append("无\n")
            return
        rows.append("| 实体（规范名） | 类型 | 旧 | 新 |")
        rows.append("|---|---|---:|---:|")
        for (kind, code, name), v in sorted(counter.items(), key=lambda kv: -kv[1]):
            rows.append(f"| {name} | {CODE_NAME.get(code,'?')} | {ok.get((kind,code,name),0)} | {nk.get((kind,code,name),0)} |")
        rows.append("")
    ent_table(only_old, "旧标有、qwen 漏标")
    ent_table(only_new, "qwen 有、旧标无")

    # 三、管道覆盖
    op = Counter((t[3], t[4]) for t in old_tags if t[1] == "entity" and t[4])
    np_ = Counter((t[3], t[4]) for t in new_tags if t[1] == "entity" and t[4])
    rows.append("## 三、别名管道覆盖\n")
    rows.append(f"- 旧标管道对 {len(op)} 种（{sum(op.values())} 处），新标 {len(np_)} 种（{sum(np_.values())} 处），"
                f"一致 {len(op & np_)} 种。")
    miss = sorted((op - np_).items(), key=lambda kv: -kv[1])
    extra = sorted((np_ - op).items(), key=lambda kv: -kv[1])
    if miss:
        rows.append("- qwen 缺失的管道：\n")
        rows.append("| surface\\|规范名 | 旧次数 | 新次数 |")
        rows.append("|---|---:|---:|")
        for (a, b), v in miss:
            rows.append(f"| {a}\\|{b} | {v} | {np_.get((a,b),0)} |")
        rows.append("")
    if extra:
        rows.append("- qwen 新增的管道：\n")
        rows.append("| surface\\|规范名 | 新次数 | 旧次数 |")
        rows.append("|---|---:|---:|")
        for (a, b), v in extra:
            rows.append(f"| {a}\\|{b} | {v} | {op.get((a,b),0)} |")
        rows.append("")

    # 四、动词差异
    ov = Counter((t[2], t[3]) for t in old_tags if t[1] == "verb")
    nv = Counter((t[2], t[3]) for t in new_tags if t[1] == "verb")
    vo, vn = ov - nv, nv - ov
    rows.append("## 四、动词差异\n")
    def verb_table(counter, title):
        rows.append(f"### {title}（共 {sum(counter.values())} 处）\n")
        if not counter:
            rows.append("无\n")
            return
        rows.append("| 动词 | 码 | 旧 | 新 |")
        rows.append("|---|---|---:|---:|")
        for (code, w), v in sorted(counter.items(), key=lambda kv: -kv[1]):
            rows.append(f"| {w} | {code} | {ov.get((code,w),0)} | {nv.get((code,w),0)} |")
        rows.append("")
    verb_table(vo, "旧标有、qwen 漏标")
    verb_table(vn, "qwen 有、旧标无")

    # 五、逐段密度
    ocount = Counter(t[0] for t in old_tags)
    ncount = Counter(t[0] for t in new_tags)
    rows.append("## 五、逐段密度对比（只列 |差|≥3 或存在零标注的段落）\n")
    rows.append("| 段 | 首十字 | 旧 | 新 | 差 |")
    rows.append("|---|---|---:|---:|---:|")
    shown = 0
    for pi, text in enumerate(new_paras):
        o, n = ocount.get(pi, 0), ncount.get(pi, 0)
        if abs(o - n) >= 3 or (o == 0) != (n == 0):
            rows.append(f"| {pi+1} | {text[:10]}… | {o} | {n} | {n-o:+d} |")
            shown += 1
    if not shown:
        rows.append("| — | 所有段落 | | | 差值均 <3 且无零标注段 |")
    rows.append("")

    # 六、抽样对照
    deltas = sorted((abs(ocount.get(pi,0) - ncount.get(pi,0)), pi) for pi in range(len(new_paras)))
    rows.append("## 六、抽样对照（密度差最大的 2 段）\n")
    for _, pi in deltas[-2:]:
        rows.append(f"### 段 {pi+1}（旧 {ocount.get(pi,0)} 处 / 新 {ncount.get(pi,0)} 处）\n")
        rows.append(f"- 旧：`{old_paras[pi][:500]}`")
        rows.append(f"- 新：`{new_paras[pi][:500]}`\n")

    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(rows) + "\n")

    print(f"报告写入 {REPORT}")
    print(f"总标记：旧 {len(old_tags)} vs 新 {len(new_tags)}")
    print(f"实体语义差异：漏 {sum((ok-nk).values())}，增 {sum((nk-ok).values())}")
    print(f"动词差异：漏 {sum(vo.values())}，增 {sum(vn.values())}")


if __name__ == "__main__":
    main()
