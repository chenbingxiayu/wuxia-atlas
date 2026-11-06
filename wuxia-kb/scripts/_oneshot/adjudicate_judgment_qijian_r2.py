# -*- coding: utf-8 -*-
"""一次性：《七剑下天山》judgment 裁决第二轮（r2，2026-11-05）。

r1（adjudicate_judgment_qijian.py）的 edits 结构 setdefault(pn, ...) 使**同段多条
编辑只应用第一条**（020[43] 打中中靶/练到被丢、026[21] 回到应用/伤被丢、
019[1] 押 occ2 被丢），且首轮清单漏 028 两条、001[37] 目标错定为 绕道而行。
本脚本以"同段多 span 逆序应用"的正确结构补齐 8 条删标：

  001[37] 突围（看看就要突围→未遂）      003[19] 下山（就要下山搜查→意图）
  017[34] 杀（我就是要杀你→威胁）        018[103] 拔（怎能够不拔→假设，r1 删的是第一处）
  019[1]  押（弥留者转述计划第二处）     020[43] 练到（还未练到→否定完成）
  026[21] 伤（险些就要伤→未遂）          028[8]  打（若夜袭只恐未打进去→假设）

保留判定不变：003[19]"自行下山"（已发生）、17[34]"她杀了你丈夫"（过去事实）、
28[25]"擒着的武士"（定语实际）等均为实际事件。
--dry 打印 diff；--apply 写盘（写前剥标断言 + 行唯一性断言）。
"""
import argparse
import difflib
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
import config      # noqa: E402
import symbols     # noqa: E402

REMOVALS = [
    (1, 37, "突围", "看看就要"),
    (3, 19, "下山", "搜查"),
    (17, 34, "杀", "就是要"),
    (18, 103, "拔", None),
    (19, 1, "押", None),
    (20, 43, "练到", "还未"),
    (26, 21, "伤", "险些"),
    (28, 8, "打", "只恐未"),
]

TOKEN_RE = re.compile(r"([〖⟦〘])(.)([^〖〗⟦⟧〘〙]*?)([〗⟧〙])")
PARA_RE = re.compile(r"^\[(\d+)\] (.*)$", re.M)


def load_paras(ch: int):
    p = config.tagged_path("七剑下天山", ch)
    t = io.open(p, encoding="utf-8").read()
    return p, {int(m.group(1)): m.group(2) for m in PARA_RE.finditer(t)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    # path -> {pn: [(start, end, replacement, tok)]}（坐标均属原段文本）
    edits, unresolved = {}, []
    for ch, pn, display, anchor in REMOVALS:
        p, paras = load_paras(ch)
        text = paras[pn]
        cands = [(m.start(), m.end(), m.group(0), m.group(3))
                 for m in TOKEN_RE.finditer(text)
                 if display in m.group(3).split("|")[0]]
        if anchor:
            cands = [c for c in cands
                     if anchor in text[max(0, c[0] - 20):min(len(text), c[1] + 20)]]
        if len(cands) != 1:
            unresolved.append((ch, pn, display, anchor, [c[2] for c in cands][:4]))
            continue
        s, e, tok, body = cands[0]
        edits.setdefault(p, {}).setdefault(pn, []).append((s, e, body.split("|")[0], tok))
        print(f"[{ch:03d}][{pn}] {tok} ⇒ {body.split('|')[0]}   "
              f"…{text[max(0, s - 14):e + 14]}…")

    print(f"\n定位 {len(REMOVALS) - len(unresolved)}/{len(REMOVALS)}；未定位 {len(unresolved)}")
    for u in unresolved:
        print("  UNRESOLVED:", u)
    if not args.apply:
        print("\n(dry-run，未写盘)")
        return
    if unresolved:
        print("\n[abort] 存在未定位条目")
        return
    for p, per in edits.items():
        t = io.open(p, encoding="utf-8").read()
        for pn, spans in per.items():
            m = re.search(rf"^\[{pn}\] (.*)$", t, re.M)
            old = m.group(1)
            new = old
            for s, e, repl, tok in sorted(spans, key=lambda x: -x[0]):  # 逆序应用
                new = new[:s] + repl + new[e:]
            assert symbols.strip_markup(new) == symbols.strip_markup(old), \
                f"剥标不一致 {p.name} [{pn}]"
            old_line, new_line = f"[{pn}] {old}", f"[{pn}] {new}"
            assert t.count(old_line) == 1, f"行定位失败 {p.name} [{pn}]"
            t = t.replace(old_line, new_line)
            print(f"written: {p.name} [{pn}]（{len(spans)} 处）")
        io.open(p, "w", encoding="utf-8", newline="").write(t)


if __name__ == "__main__":
    main()
