# -*- coding: utf-8 -*-
"""七剑批称号碎片合并（2026-11-06，glacier 碎片专项的跨书延伸，docs/69 补记 2 G2 后续）。

考订裁定（语境证据）：
  E102070 常叔叔 → E22262 常英   ch14"常叔叔、程叔叔你们也在这儿？"下一段
                                  直接同位复指"这两人是〖丧门神常英〗和〖铁塔程通〗"
  E102414 程叔叔 → E23982 程通   同上
  E82462  傅大哥 → E1966  傅青主 ch01 对话直接接续（武元英托事，傅青主应答）
  E83150  傅前辈 → E1966  傅青主 ch01 同场景（通明和尚"不如我随傅前辈去"，
                                  冒浣莲接话，远行领队=傅青主）
  E95190  卢大哥 → E14694 卢大楞子 ch10 罗达当面称"卢大哥，且慢"（称呼对象即其人）
  E77302  马大哥 → E17446 马方   ch28 周青自介"和马方是最好的朋友"→紧接
                                  "马大哥今日恰巧当值，由我替他践约"（同人异称）

缓置（专项考订，不在本批）：E94846 石大哥（石家簇 石天成/石大成/石仲明/石大娘/
石老太太/石老嫂子 互相纠缠，含疑似底本异写，需 merge_crossover 专项）；E60790 老婆婆
（ch10 身份待考订）。

动作：tagged 回挂 7 处（〖@X〗→〖@X|实名〗）+ registry aliases 补 + 删 6 碎片实体
（备份+sk 剥标断言；目标实体 sources 已含碎片来源章，核对后吸收）。
用法：python -I scripts/_oneshot/merge_qijian_fragments.py --apply
"""
import argparse
import glob
import io
import json
import os
import re
import shutil
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import apply_gold_c1_cleanup as _C1  # noqa: E402

BOOK = "七剑下天山"
MERGES = {
    "常叔叔": ("E102070", "E22262", "常英"),
    "程叔叔": ("E102414", "E23982", "程通"),
    "傅大哥": ("E82462", "E1966", "傅青主"),
    "傅前辈": ("E83150", "E1966", "傅青主"),
    "卢大哥": ("E95190", "E14694", "卢大楞子"),
    "马大哥": ("E77302", "E17446", "马方"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ---- A. tagged 回挂 ----
    total = 0
    for f in sorted(glob.glob(f"tagged/{BOOK}/*.tagged.md")):
        raw = open(f, encoding="utf-8", newline="").read()
        out, n = raw, 0
        for disp, (_fid, _tid, canon) in MERGES.items():
            old = f"〖@{disp}〗"
            if old in out:
                n += out.count(old)
                out = out.replace(old, f"〖@{disp}|{canon}〗")
        if not n:
            continue
        assert _C1.sk(out) == _C1.sk(raw), f"剥标断言失败 {f}"
        print(f"  {os.path.basename(f)}: 回挂 {n} 处")
        total += n
        if args.apply:
            bak = f"logs/backup/qijian_frag_{ts}/{BOOK}"
            os.makedirs(bak, exist_ok=True)
            if not os.path.exists(os.path.join(bak, os.path.basename(f))):
                open(os.path.join(bak, os.path.basename(f)), "w",
                     encoding="utf-8", newline="").write(raw)
            open(f, "w", encoding="utf-8", newline="").write(out)
    print(f"A. 回挂合计 {total} 处（{'已落盘' if args.apply else 'dry-run'}）")

    # ---- B. registry：aliases 补 + 删碎片 ----
    reg = json.load(open("registry/entities.json", encoding="utf-8"))
    by_id = {e["id"]: e for e in reg["entities"]}
    drop_ids, alias_added = [], 0
    for disp, (fid, tid, canon) in MERGES.items():
        frag, target = by_id[fid], by_id[tid]
        assert frag["canonical"] == disp and target["canonical"] == canon, \
            f"{fid}/{tid} 断言失败: {frag['canonical']}/{target['canonical']}"
        # 来源章吸收核对（目标须已覆盖碎片来源章，否则并入）
        newly = [s for s in frag.get("sources", []) if s not in target.setdefault("sources", [])]
        if newly:
            target["sources"] = sorted(set(target["sources"]) | set(frag["sources"]),
                                       key=int)
            print(f"  {tid} {canon}: sources 吸收 {newly}")
        if disp not in target.setdefault("aliases", []):
            target["aliases"].append(disp)
            alias_added += 1
        drop_ids.append(fid)
    n_before = len(reg["entities"])
    reg["entities"] = [e for e in reg["entities"] if e["id"] not in drop_ids]
    print(f"B. aliases +{alias_added} · 删碎片 {len(drop_ids)} 个："
          f"{n_before} → {len(reg['entities'])}（{'已落盘' if args.apply else 'dry-run'}）")
    if args.apply:
        bak = f"logs/backup/registry_qijianfrag_{ts}"
        os.makedirs(bak, exist_ok=True)
        shutil.copy2("registry/entities.json", os.path.join(bak, "entities.json"))
        tmp = "registry/entities.json.tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            json.dump(reg, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp, "registry/entities.json")
        assert not any(e["id"] in drop_ids
                       for e in json.load(open("registry/entities.json", encoding="utf-8"))["entities"])
        print(f"   registry 落盘完成，备份 {bak}")
    else:
        print("\ndry-run 结束（未写盘）。加 --apply 落盘。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
