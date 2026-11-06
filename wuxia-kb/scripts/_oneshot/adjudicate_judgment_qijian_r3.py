# -*- coding: utf-8 -*-
"""一次性：《七剑下天山》judgment 裁决第三轮（r3 收尾，2026-11-05）。

r1 遗留三处 + 一处误删回修（均剥标中性，字面唯一匹配）：
  1. 002[90] r1 occ 笔误删掉了 〖@张华昭〗 人名令牌（候选序取 3 实为第三个人名）——
     回插人名令牌，并按原裁定删裸量词 〖$张〗；
  2. 019[56] 漏删 ⟦⊞插手⟧（想要插手→未遂，纯意图）；
  3. 030[9] 〖%三尺|年龄〗 retype 被 r1 的 setdefault 同段覆盖丢弃 → 改 〖$三尺〗
     （r1 只应用了同段的六尺；身高为数量，先例 〖$七丈〗）。
"""
import argparse
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]   # wuxia-kb/
sys.path.insert(0, str(ROOT / "scripts"))
import symbols  # noqa: E402

FIXES = [  # (file, old, new, reason)
    ("tagged/七剑下天山/002.tagged.md",
     "把一〖$张〗〖•鸭绒被〗，将张华昭蒙头盖过",
     "把一张〖•鸭绒被〗，将〖@张华昭〗蒙头盖过",
     "r1 occ 笔误回修：恢复@张华昭；删裸量词$张"),
    ("tagged/七剑下天山/019.tagged.md",
     "想要⟦⊞插手⟧，给剑风迫荡",
     "想要插手，给剑风迫荡",
     "纯意图未遂（r1 漏收）"),
    ("tagged/七剑下天山/030.tagged.md",
     "不到〖%三尺|年龄〗",
     "不到〖$三尺〗",
     "身高为数量非年龄（r1 setdefault 丢弃补做）"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    for rel, old, new, reason in FIXES:
        p = ROOT / rel
        t = io.open(p, encoding="utf-8").read()
        n = t.count(old)
        tag = "APPLY" if args.apply else "DRY  "
        if n != 1:
            print(f"[{tag}] {rel}: 匹配 {n} 次（预期 1）—— {reason}\n    old={old!r}")
            continue
        strip = symbols.strip_markup
        assert strip(old) == strip(new), f"剥标不一致: {rel}"
        print(f"[{tag}] {rel}: {old[:24]}… ⇒ {new[:24]}…  （{reason}）")
        if args.apply:
            io.open(p, "w", encoding="utf-8", newline="").write(t.replace(old, new))
    if not args.apply:
        print("\n(dry-run，未写盘)")


if __name__ == "__main__":
    main()
