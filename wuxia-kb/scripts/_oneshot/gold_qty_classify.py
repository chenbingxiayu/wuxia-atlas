# -*- coding: utf-8 -*-
"""金标准 001-019 $ 数量层口径分类器（只读 dry 工具，C1 二阶段前置盘点）。

口径依据（现行）：
- docs/45 裁定「裸数词/裸量词不标」；
- scripts/apply_gold_calibrated_recall.py W4 量词两档白名单 + 负例
  （事件量 声/掌/拳/眼/步/句/次/遍/番/阵/场/回/合/看；时间量→% 层；程度量 点/片；
  surface 负例 一个/一笔/千条/万条/四处/一道；前置 deny 哪/这/每/另/第）；
- wordlists/quantity.json（丈/尺/寸/里/年/两/成/式/重/层 等量词仍 review/待审）。

分桶：
  KEEP-独立量词 / KEEP-依赖量词  —— 数+白名单量词，与机器批口径一致，保留
  STRIP-skip表面 / STRIP-前置deny / STRIP-非数量词 / STRIP-事件量 / STRIP-时间量 /
  STRIP-程度量                  —— 现行口径明确不标（机器批已实测背书）
  MANUAL-复量词 / MANUAL-量词白名单外 —— 词表 review 档，未裁，不动

用法：python -I scripts/_oneshot/gold_qty_classify.py            # 汇总
      python -I scripts/_oneshot/gold_qty_classify.py --detail   # 逐 surface 明细
"""
import glob
import io
import json
import os
import re
import sys
import collections

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

BOOK = "白发魔女传"
GOLD_MAX = 19

# 权威表直接 import 机器脚本（避免转录漂移）
import apply_gold_calibrated_recall as _W  # noqa: E402

QTY_NUM = _W.QTY_NUM
INDEP = set(_W.QTY_M_INDEP.split("|"))
DEP = set(_W.QTY_M_DEP.split("|"))
SKIP = set(_W.QTY_SKIP_SURFACE)
EV = set("声 掌 拳 眼 步 句 次 遍 番 阵 场 回 合 看".split())  # W4 事件量负例
TIME = set("日 月 年 天 时 世 期 宵 朝".split())               # % 层辖域
DEG = set("点 片 丝 滴".split())                               # 程度量

TOKEN_RE = re.compile("〖\\$([^〖〗|]+)(\\|[^〖〗]*)?〗")
STAR_RE = re.compile("〖☆(武功|武艺|功夫)(\\|[^〖〗]*)?〗")


def classify(s: str) -> str:
    if s in SKIP:
        return "STRIP-skip表面"
    if s[0] in "第每这哪另":
        return "STRIP-前置deny"
    m = re.fullmatch(QTY_NUM + r"(.+)", s)
    if not m:
        return "STRIP-非数量词"
    unit = m.group(2)
    if not unit:
        return "STRIP-裸数词"
    if unit[-1] in EV:
        return "STRIP-事件量"
    if unit[-1] in TIME:
        return "STRIP-时间量"
    if unit[-1] in DEG:
        return "STRIP-程度量"
    if len(unit) == 1 and unit in INDEP:
        return "KEEP-独立量词"
    if len(unit) == 1 and unit in DEP:
        return "KEEP-依赖量词"
    if len(unit) >= 2:
        return "MANUAL-复量词"
    return "MANUAL-量词白名单外"


def machine_surfaces() -> set:
    """机器批 020-032 实际产出的 $ surface 集（对照标定用）。"""
    out = set()
    for f in glob.glob(f"tagged/{BOOK}/0[0-3][0-9].tagged.md"):
        n = int(re.search(r"(\d{3})", f).group(1))
        if not (20 <= n <= 32):
            continue
        t = open(f, encoding="utf-8").read()
        for m in TOKEN_RE.finditer(t):
            out.add(m.group(1))
    return out


def main() -> None:
    detail = "--detail" in sys.argv
    if "--mach" in sys.argv:
        import collections as _c
        mm = _c.Counter()
        for f in glob.glob(f"tagged/{BOOK}/0[0-3][0-9].tagged.md"):
            n = int(re.search(r"(\d{3})", f).group(1))
            if not (20 <= n <= 32):
                continue
            t = open(f, encoding="utf-8").read()
            for m in TOKEN_RE.finditer(t):
                mm[m.group(1)] += 1
        print(f"机器批020-032 $ token 总数: {sum(mm.values())} 种类: {len(mm)}")
        for s in ("一个", "两个", "一声", "一掌", "一定", "一般", "一道", "第一",
                  "一把", "几个", "一口", "一丈", "三舵", "一名", "三招", "一剑",
                  "一支", "一枚"):
            print(" ", s, mm.get(s, 0))
        return
    files = [f for f in sorted(glob.glob(f"tagged/{BOOK}/0[0-1][0-9].tagged.md"))
             if int(re.search(r"(\d{3})", f).group(1)) <= GOLD_MAX]
    mach = machine_surfaces()
    cnt: collections.Counter = collections.Counter()
    shared: collections.Counter = collections.Counter()
    surf: dict = collections.defaultdict(collections.Counter)
    locs: dict = collections.defaultdict(list)
    star = collections.Counter()
    for f in files:
        t = open(f, encoding="utf-8").read()
        ch = f[-10:-7]
        for m in TOKEN_RE.finditer(t):
            s = m.group(1)
            c = classify(s)
            cnt[c] += 1
            surf[c][s] += 1
            if s in mach:
                shared[c] += 1
            locs[s].append((ch, t[max(0, m.start() - 12):m.start() + len(m.group(0)) + 8].replace("\n", " ")))
        for m in STAR_RE.finditer(t):
            star[m.group(1)] += 1
    total = sum(cnt.values())
    print(f"gold $ tokens 总数: {total}（{len(files)} 文件）· 机器批 $ surface 种类: {len(mach)}")
    for k in sorted(cnt, key=lambda k: -cnt[k]):
        print(f"  {k}: {cnt[k]}（其中 surface 与机器面共享 {shared[k]} token）")
    print(f"gold ☆武功/武艺/功夫 残留: {dict(star)}")
    if detail:
        for k in sorted(surf):
            print(f"\n== {k} ==")
            for s, c in sorted(surf[k].items(), key=lambda x: -x[1]):
                flag = " ✔机" if s in mach else ""
                ex = locs[s][0]
                print(f"  {s}:{c}{flag}  例[{ex[0]}] …{ex[1]}…")
    json.dump({"mach_surfaces": sorted(mach),
               "buckets": {k: dict(v) for k, v in surf.items()}},
              open("logs/qa/gold_qty_classify.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("明细落盘 logs/qa/gold_qty_classify.json")


if __name__ == "__main__":
    main()
