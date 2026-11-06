# -*- coding: utf-8 -*-
"""C1 · 金标准 001-019 v1.8 口径清洗（docs/40 §八 C1 / docs/39 §六 C1 落地）。

规则（全部有条文/裁定背书，见 docs/48 §五）：
  R1 D1 剥标：〖#X〗 display ∈ D1_SET（描述性代称 + DEF-04 纯亲属）→ 剥标记留显示串
     —— docs/39 §1.2「D1 描述性代称规范应不标（金标准 19.4% 为旧口径残留）」
  R2 ☆/^ 归位（01g 附录 B1-1）：^轻功→☆轻功（分项技艺）；☆武功/☆武艺→^（能力域总称）
  R3 单字裸数词/裸量词：〖$X〗 len(X)==1 → 摘（docs/45 已裁数量新口径）
  R4 族群名本体：#罗布族 → ~罗布族（B1-3；2026-11-05 已单独执行，此处幂等兜底）

不触碰：@ 管道、动词令牌、% 时间、•/= 等其余类型、多字 $（两名/一把属新口径保留类）、
带职衔/姓名复合称谓（少年将军/狗强盗等——D1 集合为保守闭集）。

用法：
  python scripts/apply_gold_c1_cleanup.py --dry-run   # 预估分类计数 + 明细
  python scripts/apply_gold_c1_cleanup.py --apply     # 备份后落盘（逐段剥标断言）
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parents[1]
TAG = ROOT / "tagged" / "白发魔女传"
BK = ROOT / "backup" / "tagged" / "gold-c1-20261105"

# R1 D1 闭集（与 build_03a_fewshot.D1_UNTAG 同源 + kinship）
D1_SET = {
    "人", "人们", "大家", "自己人", "俺", "小鬼", "小", "老头", "老者", "老妇人",
    "老儿", "少年", "少女", "汉子", "大汉", "人物", "人声", "姑姑", "前夫", "舅舅",
}
# R3 单字 $ 集合（数词 + 高频量词，凡 len==1 一律摘，无需枚举——规则按长度）
SINGLE_CHAR_RE = re.compile(r"〖\$([^〖〗])〗")
# R2 归位映射
RETAG = {"^轻功": "☆轻功", "☆武功": "^武功", "☆武艺": "^武艺"}


def sk(s: str) -> str:
    s = re.sub(r"〖(.)([^〖〗｜|]*)(?:[｜|]([^〖〗]*))?〗", lambda m: m.group(2), s)
    s = re.sub(r"⟦(.)([^⟧｜|]*)(?:[｜|]([^⟧]*))?⟧", lambda m: m.group(2), s)
    return re.sub(r"〘(.)?([^〙]*)〙", lambda m: m.group(2), s)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    files = sorted(
        f for f in glob.glob(str(TAG / "*.tagged.md"))
        if int(os.path.basename(f)[:3]) <= 19
    )
    total = Counter()
    detail: list[str] = []
    for f in files:
        ch = os.path.basename(f)[:3]
        t = io.open(f, encoding="utf-8").read()
        before = sk(t)
        cnt = Counter()

        # R1 D1 剥标
        def _d1(m):
            cnt["R1_D1"] += 1
            detail.append(f"{ch} R1 〖#{m.group(1)}〗")
            return m.group(1)
        t = re.sub("〖#(" + "|".join(sorted(D1_SET)) + r")〗", _d1, t)

        # R2 ☆/^ 归位
        for old, new in RETAG.items():
            n = t.count(f"〖{old}〗")
            if n:
                t = t.replace(f"〖{old}〗", f"〖{new}〗")
                cnt[f"R2_{old}→{new}"] = n
                detail.append(f"{ch} R2 〖{old}〗→〖{new}〗 ×{n}")

        # R3 单字 $ 摘除
        def _q(m):
            cnt["R3_$单字"] += 1
            detail.append(f"{ch} R3 〖${m.group(1)}〗")
            return m.group(1)
        t = SINGLE_CHAR_RE.sub(_q, t)

        # R4 族群本体兜底（B1-3 已单独执行过，此处幂等）
        n = t.count("〖#罗布族〗")
        if n:
            t = t.replace("〖#罗布族〗", "〖~罗布族〗")
            cnt["R4_罗布族"] = n
            detail.append(f"{ch} R4 #→~ 罗布族 ×{n}")

        total.update(cnt)
        if cnt and args.apply:
            assert sk(t) == before, f"{ch} 剥标不一致"
            dst = BK / os.path.basename(f)
            if not dst.exists():
                shutil.copy2(f, dst)
            io.open(f, "w", encoding="utf-8").write(t)

    print("== 分类计数 ==")
    for k, v in sorted(total.items()):
        print(f"  {k}: {v}")
    print(f"  合计: {sum(total.values())}")
    if args.dry_run:
        io.open(ROOT / "logs/qa/c1_dryrun_detail.txt", "w", encoding="utf-8").write(
            "\n".join(detail))
        print(f"明细 {len(detail)} 条 → logs/qa/c1_dryrun_detail.txt")
    else:
        print(f"已落盘（备份 → {BK}，仅写有改动的文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
