# -*- coding: utf-8 -*-
"""交叉校验分析：GLM vs deepseek 实体/动词标注一致性 + 对照旧人工种子（实体部分）。

用法：python xval_analyze.py
输入：config.DIR_TAGGED/_xval/ 下 fragment / glm_001.E / glm_001.EV / dsk_001.E / dsk_001.EV
     + 旧人工种子 config.LEGACY_KB/tagged/白发魔女传/001_第一回.tagged.md（实体码 @=;◆☆%•+ 可比）
输出：config.DIR_TAGGED/_xval/xval_report.md
方法：各输出剥标自检 → 标记序列（surface,code）按阅读序提取 → difflib 序列对齐
     → 一致率（类型一致/边界一致）/ 单方标注 / 类型分歧清单 → 提示词有效性读出。
P3 修复（2026-11-03）：路径接 config（原 parents[] 相对推导）；令牌正则/剥标改走
     symbols（本地 TOKEN_RE 缺 〘〙 修辞层）；移除 OLD_MAP 死映射 "[→{"（映射后的
     "{" 不在 OLD_COMPAT，会被过滤——行为等价但语义误导；[ 旧秘籍码不参与对照，
     与文件头"可比码 @=;◆☆%•+"声明一致）。
"""
import difflib
import io
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config   # noqa: E402
import symbols  # noqa: E402

X = config.DIR_TAGGED / "_xval"
OLD_MAP = {"§": "•"}                     # 旧码→新码（丹药 § 并入器物 •）；[ 不参与对照
OLD_COMPAT = set("@=;◆☆%•+")            # 旧种子中与新规范直接可比的码


def strip_marks(text):
    return symbols.strip_markup(text)


def marks_seq(text, verbs=False):
    """按阅读序提取 (surface, code)；verbs=True 只取 ⟦⟧，否则只取 〖〗。"""
    out = []
    for m in symbols.TOKEN_RE.finditer(text):
        tok = m.group(0)
        if tok[0] == "〘":
            continue                      # 修辞层不参与实体/动词序列比对
        is_v = tok[0] == "⟦"
        if is_v != verbs:
            continue
        body = tok[1:-1]
        code, rest = body[0], body[1:]
        surf = rest.split("|", 1)[0] if "|" in rest else rest
        out.append((surf, code))
    return out


def align(a, b):
    """两个 (surface,code) 序列 difflib 对齐 → (matched, only_a, only_b, type_diff, pos_diff)。
    matched: [(i,j,surface,code_a,code_b)]；pos_diff 表示同码但处于非对齐位置（边界分歧代理）。"""
    sm = difflib.SequenceMatcher(None, [s for s, _ in a], [s for s, _ in b], autojunk=False)
    matched, only_a, only_b, type_diff = [], [], [], []
    bmap = defaultdict(list)
    for j, item in enumerate(b):
        bmap[item[0]].append(j)
    used_b = set()
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            i, j = block.a + k, block.b + k
            ca, cb = a[i][1], b[j][1]
            used_b.add(j)
            if ca == cb:
                matched.append((i, j, a[i][0], ca, cb))
            else:
                type_diff.append((i, j, a[i][0], ca, cb))
    for i, item in enumerate(a):
        if item[0] not in bmap or all(j not in used_b for j in bmap[item[0]]):
            only_a.append(item)
    for j, item in enumerate(b):
        if j not in used_b:
            only_b.append(item)
    return matched, only_a, only_b, type_diff


def fmt_items(items):
    return "；".join(f"{s}({c})" for s, c in items[:15]) + ("…" if len(items) > 15 else "")


def main():
    frag = (X / "fragment_001_L2-12.txt").read_text(encoding="utf-8")
    base = strip_marks(frag)
    files = {}
    for k in ["glm_001.E.md", "dsk_001.E.md", "glm_001.EV.md", "dsk_001.EV.md"]:
        p = X / k
        if p.exists():
            files[k] = p.read_text(encoding="utf-8")
        else:
            files[k] = None
            rep = [f"- {k}: 不存在（deepseek V 阶段保真门三次未过，无产物）"]
            (X / "_missing.txt").write_text("\n".join(rep), encoding="utf-8")
    rep = ["# 交叉校验报告（GLM vs deepseek · 001 回 [2]-[12] 片段）", "",
           f"片段基线：{len(base)} 字符（剥 PN 前缀后）", "", "## 0 · 完整性自检", ""]
    for k, t in files.items():
        if t is None:
            rep.append(f"- {k}: 无产物（V 阶段保真门三次未过，作废）")
            continue
        ok = strip_marks(t) == base
        rep.append(f"- {k}: 剥标与基线逐字一致 {'PASS' if ok else '**FAIL**'}")
    rep.append("")

    # ---- 实体层对比（E 产物互检 + EV 互检复核） ----
    rep.append("## 1 · 实体层一致性（glm.E vs dsk.E）")
    ge = marks_seq(files["glm_001.E.md"])
    de = marks_seq(files["dsk_001.E.md"]) if files.get("dsk_001.E.md") else []
    m, oa, ob, td = align(ge, de)
    n = len(ge) + len(de)
    rep += [f"- GLM 实体 {len(ge)} / deepseek 实体 {len(de)}",
            f"- 完全一致（同词同码）：{len(m)} 处 —— 一致率 {len(m)*2}/{n} = {len(m)*200/max(n,1):.0f}%",
            f"- 类型分歧（同词不同码）：{len(td)}", ]
    for i, j, s, ca, cb in td[:12]:
        rep.append(f"  - 「{s}」 GLM={ca} vs dsk={cb}")
    rep.append(f"- 仅 GLM 标注：{len(oa)} → {fmt_items(oa)}")
    rep.append(f"- 仅 dsk 标注：{len(ob)} → {fmt_items(ob)}")
    rep.append("")

    # ---- 动词层对比 ----
    rep.append("## 2 · 动词层一致性（glm.EV vs dsk.EV；dsk 无 EV 产物则仅列 GLM 侧供人工核）")
    gv = marks_seq(files["glm_001.EV.md"], verbs=True)
    dv = marks_seq(files["dsk_001.EV.md"], verbs=True) if files.get("dsk_001.EV.md") else []
    m, oa, ob, td = align(gv, dv)
    n = len(gv) + len(dv)
    rep += [f"- GLM 动词 {len(gv)} / deepseek 动词 {len(dv)}",
            f"- 完全一致：{len(m)} —— 一致率 {len(m)*200/max(n,1):.0f}%",
            f"- 类型分歧：{len(td)}"]
    for i, j, s, ca, cb in td[:12]:
        rep.append(f"  - 「{s}」 GLM={ca} vs dsk={cb}")
    rep.append(f"- 仅 GLM：{len(oa)} → {fmt_items(oa)}")
    rep.append(f"- 仅 dsk：{len(ob)} → {fmt_items(ob)}")
    rep.append("")

    # ---- 对照旧人工种子（实体可比子集） ----
    rep.append("## 3 · 与旧人工种子对照（实体可比码 @=;◆☆%•+，§→• 映射）")
    old = (config.LEGACY_KB / "tagged" / "白发魔女传" /
           "001_第一回.tagged.md").read_text(encoding="utf-8")
    old_marks = []
    for m2 in symbols.TOKEN_RE.finditer(old):
        tok = m2.group(0)
        if tok[0] != "〖":
            continue
        body = tok[1:-1]
        code, rest = body[0], body[1:]
        code = OLD_MAP.get(code, code)
        surf = rest.split("|", 1)[0] if "|" in rest else rest
        old_marks.append((surf, code))
    old_marks = [x for x in old_marks if x[1] in OLD_COMPAT]
    frag_text = strip_marks(frag)
    old_marks_in_frag = [x for x in old_marks if x[0] in base]   # 范围限定：仅片段内出现的旧标记
    old_marks_full = old_marks  # 全书对照仅作参考（范围伪影大）
    for name, seq in (("GLM", ge), ("dsk", de)):
        seq_c = [x for x in seq if x[1] in OLD_COMPAT]
        m, oa, ob, td = align(old_marks_in_frag, seq_c)
        n = len(old_marks) + len(seq_c)
        rep += [f"- {name}（可比码 {len(seq_c)}）vs 旧种子片段内标记（{len(old_marks_in_frag)}）："
                f"一致 {len(m)} = {len(m)*200/max(n,1):.0f}%",
                f"  - 旧有新无（候选漏标）：{fmt_items(oa)}",
                f"  - 新有旧无（新增规范产出或旧漏标）：{fmt_items(ob)}",
                f"  - 码分歧：{fmt_items([(s, f'{ca}→{cb}') for _, _, s, ca, cb in td][:10])}"]
    rep.append("")

    # ---- 提示词有效性读出 ----
    rep.append("## 4 · 提示词有效性读出（按分歧分类归因）")
    rep.append("""
- **一致率 ≥85% 的码**：规则无歧义，提示词有效；
- **类型分歧集中处**：提示词定义边界不清或两模型理解分歧——需补正误例或收紧定义；
- **单方标注集中处**：一方召回缺失——多为提示词未强调（对照"最易漏"条款核查）；
- **双方一致但与旧种子不一致处**：可能是新规范口径演进（D1/D2/G0）或旧种子漏标——人工复核时逐条裁定，裁定结果回填 few-shot。
""")

    out = X / "xval_report.md"
    out.write_text("\n".join(rep) + "\n", encoding="utf-8")
    print("report →", out)
    print("\n".join(rep[:30]))


if __name__ == "__main__":
    main()
