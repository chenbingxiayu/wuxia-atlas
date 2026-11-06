# -*- coding: utf-8 -*-
"""按新 struct 重建 tagged：只迁移"结构壳"（围栏行/PN 编号），标注令牌沿内容行原样搬迁。

背景（docs/47 §六.1 修复）：结构层检测修好后重生成 struct 会新增/改类围栏行，并对
001 章首词、048 回末词做"多段合并一个 PN"。标注令牌属于**内容行**，与 PN 无关，
故按"内容行序列不变（仅结构行变化）"的构造性事实逐行搬运：

  1) 旧 tagged 的非结构行（非 `[N] ` / 非 `:::` / 非空 / 非 `# [0]`）按序取出 = 标注文本序列；
  2) 新 struct 的非结构行按序取出 = 纯文本序列；
  3) 断言序列等长且逐行剥标相等（构造保证；失败则该回报错中止）；
  4) 以新 struct 为骨架输出：结构行照抄，内容行换成对应标注文本（首行带新 PN）。

用法：python -X utf8 scripts/_oneshot/rebuild_tagged_from_struct.py 江湖三女侠 [--apply]
产物：tagged/<书>/NNN.tagged.md（--apply 写盘，先备份到 logs/backup/rebuild_tagged_<书>/）；
      报告 logs/qa/rebuild_tagged_<书>.md
"""
from __future__ import annotations

import argparse
import io
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402
import symbols  # noqa: E402

PARA_RE = re.compile(r"^\[(\d+)\] (.*)$")
TITLE_RE = re.compile(r"^# \[0\] ")


def content_lines(text: str):
    """抽出非结构行（保持顺序）：跳过空行、围栏行、回目行；[N] 行取正文部分。"""
    out = []
    for ln in text.split("\n"):
        if not ln.strip():
            continue
        if ln.startswith(":::"):
            continue
        if TITLE_RE.match(ln):
            continue
        m = PARA_RE.match(ln)
        out.append(m.group(2) if m else ln)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    book = args.book
    d = config.DIR_TAGGED / book
    backup = config.DIR_LOGS / "backup" / f"rebuild_tagged_{book}"
    rows, fails = [], []
    for no in range(1, config.books()[book]["chapters"] + 1):
        sp = d / f"{no:03d}.struct.md"
        tp = d / f"{no:03d}.tagged.md"
        if not (sp.exists() and tp.exists()):
            fails.append((no, "缺 struct/tagged"))
            continue
        struct_lines = io.open(sp, encoding="utf-8").read().split("\n")
        tagged_text = io.open(tp, encoding="utf-8").read()
        annotated = content_lines(tagged_text)
        plain = content_lines("\n".join(struct_lines))
        if len(annotated) != len(plain):
            fails.append((no, f"内容行数不一致 tagged {len(annotated)} vs struct {len(plain)}"))
            continue
        bad = [(i, a, p) for i, (a, p) in enumerate(zip(annotated, plain))
               if symbols.strip_markup(a) != p]
        if bad:
            fails.append((no, f"剥标不等 {len(bad)} 行，首例 #{bad[0][0]}: {bad[0][2][:40]}"))
            continue
        # 重建
        out, ai = [], 0
        cur_pn = None
        for ln in struct_lines:
            m = PARA_RE.match(ln)
            if m:
                cur_pn = int(m.group(1))
                out.append(f"[{cur_pn}] {annotated[ai]}")
                ai += 1
            elif (not ln.strip()) or ln.startswith(":::") or TITLE_RE.match(ln):
                out.append(ln)
            else:
                out.append(annotated[ai])
                ai += 1
        if ai != len(annotated):
            fails.append((no, f"重建消耗 {ai} != {len(annotated)}"))
            continue
        new_text = "\n".join(out)
        if symbols.strip_markup(new_text) != tagged_text and False:
            pass
        # 与 struct 逐段对齐复验
        ok = True
        gp = {}
        for ln in new_text.split("\n"):
            m = PARA_RE.match(ln)
            if m:
                gp[int(m.group(1))] = m.group(2)
        spn = {}
        for ln in struct_lines:
            m = PARA_RE.match(ln)
            if m:
                spn[int(m.group(1))] = m.group(2)
        if list(gp) != list(spn) or any(symbols.strip_markup(gp[k]) != spn[k] for k in spn):
            fails.append((no, "重建后与 struct 不一致"))
            continue
        if args.apply:
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tp, backup / tp.name)
            io.open(tp, "w", encoding="utf-8", newline="\n").write(new_text)
        rows.append((no, len(spn), len(annotated)))

    L = [f"# 按新 struct 重建 tagged ——《{book}》", "",
         f"- 模式：{'APPLY' if args.apply else 'DRY-RUN'}；成功 {len(rows)} 回；失败 {len(fails)} 回",
         "", "| 回 | PN 数 | 内容行数 |", "|---|---|---|"]
    L += [f"| {no:03d} | {pn} | {nl} |" for no, pn, nl in rows]
    if fails:
        L += ["", "## 失败", ""] + [f"- {no:03d}: {why}" for no, why in fails]
    out_md = config.DIR_LOGS / "qa" / f"rebuild_tagged_{book}.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    io.open(out_md, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    print(f"[{'apply' if args.apply else 'dry-run'}] 成功 {len(rows)} 回，失败 {len(fails)} 回 → {out_md}")
    for no, why in fails[:6]:
        print(f"  FAIL {no:03d}: {why}")


if __name__ == "__main__":
    main()
