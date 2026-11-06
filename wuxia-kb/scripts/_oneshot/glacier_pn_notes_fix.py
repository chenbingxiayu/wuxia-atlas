# -*- coding: utf-8 -*-
"""glacier 混指章注记粒度修正：回级 → 段级（2026-11-06 phase-3）。

phase-2 的回级注记在两个"父子并存章"上粒度不足（回级 dict 单值，一章双指时另一批
管道回落全局别名告警，warning 29→15 后新增 14 条反向告警）：
  ch10 陈大人：pn23=陈天宇 / pn31,32,34=陈定基（父 ch10 均为 陈定基×6）
  ch35 唐大侠：pn7=唐晓澜 / pn48-54=唐经天（后者本就命中全局别名，无需注记）
本脚本把 E118280（唐晓澜）与 E118271（陈天宇）的回级 dict 条目替换为段级条目。
预期终态：pipe_mapping_conflict 15 → 1（唯一残留 ch32[pn22] 唐伯母同段双指
冯瑛/冯琳——pn dict 单值机制限制，数据本身正确，记录在案）。

用法：python -I scripts/_oneshot/glacier_pn_notes_fix.py --apply
"""
import argparse
import io
import json
import os
import shutil
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)

BOOK = "冰川天女传"

# E118280 唐晓澜：替换 {display:唐大侠, chapters:[...]} → 段级（实测 pn，phase-3 扫描）
PN_TANG_XL = [(11, 48), (11, 49), (17, 47), (35, 7), (38, 32), (38, 35),
              (38, 36), (38, 42), (39, 4), (39, 5), (39, 8)]
# E118271 陈天宇：替换 {display:陈大人, chapters:[10]} → 段级
PN_CHEN = [(10, 23)]

REPLACE = {
    "E118280": ("唐大侠", PN_TANG_XL),
    "E118271": ("陈大人", PN_CHEN),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    reg = json.load(open("registry/entities.json", encoding="utf-8"))
    by_id = {e["id"]: e for e in reg["entities"]}
    removed = added = 0
    for eid, (disp, pns) in REPLACE.items():
        rec = by_id[eid]
        ctx = rec.get("contextual") or []
        old = [a for a in ctx
               if isinstance(a, dict) and a.get("display") == disp
               and a.get("book") == BOOK and "chapters" in a and "pn" not in a]
        for o in old:
            ctx.remove(o)
        removed += len(old)
        for ch, pn in pns:
            it = {"chapter": ch, "pn": pn, "display": disp, "book": BOOK}
            if it not in ctx:
                ctx.append(it)
                added += 1
        rec["contextual"] = ctx
        print(f"  {eid} {rec['canonical']}: -{len(old)} 回级 → +{len(pns)} 段级")
    print(f"（{'已落盘' if args.apply else 'dry-run'}；-回级{removed} +段级{added}）")
    if args.apply:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = f"logs/backup/registry_pnfix_{ts}"
        os.makedirs(bak, exist_ok=True)
        shutil.copy2("registry/entities.json", os.path.join(bak, "entities.json"))
        tmp = "registry/entities.json.tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            json.dump(reg, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp, "registry/entities.json")
        print(f"   registry 落盘完成，备份 {bak}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
