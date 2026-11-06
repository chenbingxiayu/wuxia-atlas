# -*- coding: utf-8 -*-
"""一次性：《七剑下天山》底本半角标点修复（docs/48 §七-1，2026-11-05）。

证据与裁定（docs/48 §四）：
  1. `宗达?完真`×17 + 变体 `宗达?完宗`/`宗达?宗真`（宗/完 OCR 互串，旧标注已裁定同一人）
     → `宗达完真`。依据：同一全集底本《侠骨丹心》部分该人物即写作"宗达完真"（×5，
     无分隔号）；百度百科词条名"宗达完真"。`?` 为数字化丢失字符。
  2. 半角 `,` ×1（008 回"肩头,就被"）→ 全角 `，`。

范围（全部先备份至 logs/_backup_corpus_repair_20261105/ 再改）：
  拆分/七剑下天山.txt · 章回版/七剑下天山/*.txt · 梁羽生武侠全集.txt ·
  wuxia-kb/tagged/七剑下天山/*.struct.md|.struct.json|.tagged.md
不改一章回版以外的书目；不改旧 kb/tagged（历史资产）。

用法：python scripts/_oneshot/repair_corpus_punct_qijian.py            # 扫描+修复
      python scripts/_oneshot/repair_corpus_punct_qijian.py --scan-only  # 只扫描报告
"""
import argparse
import io
import re
import shutil
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[3]          # Wuxiaxiaoshuo/（_oneshot → scripts → wuxia-kb → 根）
REPO = ROOT
WB = ROOT / "wuxia-kb"
BACKUP = WB / "logs" / "_backup_corpus_repair_20261105"

REPLACEMENTS = [
    ("宗达?完真", "宗达完真"),
    ("宗达?完宗", "宗达完真"),
    ("宗达?宗真", "宗达完真"),
    ("肩头,就被", "肩头，就被"),
    # 二轮补充（2026-11-05）：复扫发现的其余 3 处半角逗号（021×2 / 026×1，均在裸文本）
    ("音,也必能", "音，也必能"),
    ("飞红巾,你一定能成", "飞红巾，你一定能成"),
    ("置此札,君怀袖", "置此札，君怀袖"),
]

TARGETS = (
    [REPO / "拆分" / "七剑下天山.txt", REPO / "梁羽生武侠全集.txt"]
    + sorted((REPO / "章回版" / "七剑下天山").glob("*.txt"))
    + sorted((WB / "tagged" / "七剑下天山").glob("*.struct.md"))
    + sorted((WB / "tagged" / "七剑下天山").glob("*.struct.json"))
    + sorted((WB / "tagged" / "七剑下天山").glob("*.tagged.md"))
)

HALFWIDTH_RE = re.compile(r"[!-/:-@[-`{-~]")


def scan(text: str):
    """半角字符分布 + 上下文样例（修复校验用）。"""
    out = {}
    for m in HALFWIDTH_RE.finditer(text):
        out.setdefault(m.group(0), []).append(m.start())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-only", action="store_true")
    args = ap.parse_args()

    print("== 修复前全量半角扫描（拆分/七剑下天山.txt）==")
    src = io.open(REPO / "拆分" / "七剑下天山.txt", encoding="utf-8").read()
    dist = scan(src)
    for ch, pos in sorted(dist.items()):
        print(f"  {ch!r} ×{len(pos)}  例：{[src[max(0, p-10):p+10] for p in pos[:3]]}")

    if args.scan_only:
        return
    print("\n== 执行修复 ==")
    grand = 0
    for p in TARGETS:
        if not p.exists():
            print(f"  [skip] 不存在：{p}")
            continue
        text = io.open(p, encoding="utf-8").read()
        n_total, new = 0, text
        for old, repl in REPLACEMENTS:
            n = new.count(old)
            if n:
                new = new.replace(old, repl)
                n_total += n
        if not n_total:
            continue
        rel = p.relative_to(REPO)
        dst = BACKUP / rel
        if not dst.exists():                 # 首轮备份=原件；二轮不覆盖（保可逆）
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
        io.open(p, "w", encoding="utf-8", newline="").write(new)
        grand += n_total
        print(f"  {rel}: {n_total} 处（备份 → {dst.relative_to(REPO)}）")
    print(f"\n合计替换 {grand} 处；备份根目录：{BACKUP.relative_to(REPO)}")

    print("\n== 修复后复扫（应仅剩预期外半角=0）==")
    for p in (REPO / "拆分" / "七剑下天山.txt",):
        text = io.open(p, encoding="utf-8").read()
        dist2 = scan(text)
        print(f"  {p.name}: { {k: len(v) for k, v in dist2.items()} or '干净' }")


if __name__ == "__main__":
    main()
