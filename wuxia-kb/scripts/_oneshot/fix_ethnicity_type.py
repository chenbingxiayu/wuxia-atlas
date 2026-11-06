# -*- coding: utf-8 -*-
"""B1-3 + B1-2 落地：族群名本体统一为 `~`，并清掉「X族人」人义复合词误标。

依据（见 docs/53 §一）：
- 01g §2.2.1：`~`=具名民族/族群；`&`=家族世系；`◆`=组织/政权；`◎`=人物群组；
  `#`=职业/社会身份/处境身份。罗布族/哈萨克是民族共同体（"民族共同体不能压缩成政权或职业"），
  族名本体一律 `~`。
- B1-2（2026-11-05 已裁）：「X族人」人义复合词**不标**（成员指称，拆词插入语义错位）。
- C1 R4 已把金标准 `#罗布族` → `~罗布族`；本轮收口剩余机器误类型。

修正集（仅族名本体，不含「X族人」复合词）：
  〖&罗布族〗/〖◆罗布族〗/〖◎罗布族〗 → 〖~罗布族〗
  〖&哈萨克〗 → 〖~哈萨克〗；〖&哈萨克族〗 → 〖~哈萨克族〗
  〖#罗布族人〗 → 罗布族人（剥标，B1-2）
不处理（记入待考）：哈萨克 的 @/#/=/◆ 多类型、风砂堡(&/=)、客氏(&/@)、爱新觉罗氏(&，正确保留)。

用法：
  python scripts/_oneshot/fix_ethnicity_type.py [--apply]
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAGGED = ROOT / "tagged"
BACKUP = ROOT / "backup" / "tagged" / "ethnicity-fix-20261105"

# (正则, 替换) —— 顺序敏感：先本体再复合词
RULES = [
    (re.compile(r"〖[&◆◎](罗布族)(?:[|｜][^〗]*)?〗"), r"〖~\1〗"),
    (re.compile(r"〖[&◆◎](哈萨克族?)(?:[|｜][^〗]*)?〗"), r"〖~\1〗"),
    (re.compile(r"〖#罗布族人〗"), "罗布族人"),
]


def strip_markup(s: str) -> str:
    s = re.sub(r"〖(.)([^〖〗｜|]*)(?:[｜|]([^〖〗]*))?〗", lambda m: m.group(2), s)
    s = re.sub(r"⟦(.)([^⟧｜|]*)(?:[｜|]([^⟧]*))?⟧", lambda m: m.group(2), s)
    return re.sub(r"〘(.)?([^〙]*)〙", lambda m: m.group(2), s)


def main() -> int:
    apply = "--apply" in sys.argv
    BACKUP.mkdir(parents=True, exist_ok=True)
    total = 0
    touched = []
    for p in sorted(TAGGED.glob("*/*.tagged.md")):
        text = p.read_text(encoding="utf-8")
        new = text
        hits = []
        for pat, rep in RULES:
            n = len(pat.findall(new))
            if n:
                hits.append((pat.pattern, n))
                new = pat.sub(rep, new)
        if new == text:
            continue
        assert strip_markup(text) == strip_markup(new), f"{p}: 剥标正文变化"
        cnt = sum(n for _, n in hits)
        print(f"[need] {p.relative_to(ROOT)}: {hits} 共 {cnt}")
        if apply:
            bp = BACKUP / p.relative_to(TAGGED)
            bp.parent.mkdir(parents=True, exist_ok=True)
            if not bp.exists():
                shutil.copy2(p, bp)
            p.write_text(new, encoding="utf-8")
            after = p.read_text(encoding="utf-8")
            assert strip_markup(after) == strip_markup(text)
            print(f"[ok]   {p.relative_to(ROOT)}: 已替换；备份 → {bp}")
        touched.append(str(p.relative_to(ROOT)))
        total += cnt
    print(f"\n{'已替换' if apply else '待替换'}合计 {total} 处，涉及 {len(touched)} 文件")
    if touched:
        print("涉及书：", sorted({t.split('\\\\')[0] for t in touched}))
    if not apply:
        print("（dry-run，加 --apply 落盘）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
