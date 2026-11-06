# -*- coding: utf-8 -*-
"""glacier 碎片实体清理 + §五.1 书域/段级注记（2026-11-06，治理遗留 ②③ phase-2）。

一、称号型碎片实体考订（承接 冒大侠合并先例；docs/55 §六.4「分裂形剔除」专项 glacier 部分）
  回挂+合并（语境证据见 docs/69 补记）：
    桂大侠   E118409 跨章双指：ch05=祖父桂仲明（"你是桂大侠的孙女儿…七剑下天山…祖父祖母"），
             ch09/19=父桂华生（"父亲桂华生大侠，桂大侠幼承母教"/"令父是石大侠还是桂大侠"）
             → ch05 回挂 |桂仲明、ch09/19 回挂 |桂华生，删 E118409，双目标各加章级 dict 别名
    金大侠   E118464 ×2 ch34 → |金世遗（"这酒是留给金大侠吃的…你的金大侠早在沙漠中死掉啦"，江南语）
    萧老师   E118563 ×1 ch31 → |萧青峰（"一定是萧老师向你说我了"，江南称师）
    杨老前辈 E118567 ×1 ch32 → |杨仲英（"董太清当年受杨老前辈那一掌"=铁掌神弹）
    毒龙前辈 E118392 ×5 ch32 → |毒龙尊者（"毒龙师伯…坟墓…衣钵传人"，金世遗先师）
  孤儿删除（裸文形态已在册消失/回挂，无 tagged 支持）：
    E118358 唐大侠（陈旧来源，全书裸文 0）；E118375 冒老前辈 / E118446 冒伯伯 / E118550
    冒老师（冒川生合并回挂后失去支持；显示串已管道化+别名在册）
  保留（无名者称号指称，title-as-designator，列入专项清单）：
    麦大侠 E118435 / 邹伯伯 E118535 / 石大侠 E118537 / 土司夫人 E118556
  不动（七剑批碎片 E60790/E77302/E82462/E83150/E94846/E95190/E102070/E102414——属该书专项）。

二、§五.1 管道-登记表碰撞 silence（现行 29 条，8 组；机制 accept_batch.py:1047——回/段级
  作用域折叠进 reg_map 且优先于全局别名，task-11/50/65）：
    唐大侠→唐晓澜  E118280 chapters [11,17,35,38,39]   （全局别名属 E118270 唐经天）
    唐伯伯→唐晓澜  E118280 chapters [17]
    陈大人→陈天宇  E118271 chapters [10]               （全局别名属 E118288 陈定基）
    杨大侠→杨仲英  E99702 chapters [15]                （全局别名属 E9190 杨云骢）
    霞儿→邹绛霞    E118294 chapters [18,19,31,32,36]   （全局别名属 E0006 孟秋霞 等）
    霞妹→邹绛霞    E118294 chapters [19]
    唐伯母→冯琳    E99706 pn 级 (31,54)(32,21)(32,22)  （全局别名属 E118289 唐赛花）
    唐伯母→冯瑛    E118299 pn 级 (32,22)
  已知机制限制：ch32[pn22] 同段同显示串双指（冯瑛+冯琳），pn dict 单值 → 预期残留
  warning 1 条（后处理记录胜出，另一管道回落全局别名告警）；数据本身正确（双 pipes 显式）。

用法：python -I scripts/_oneshot/glacier_fragments_and_scope_notes.py --apply
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

BOOK = "冰川天女传"

# (章, 旧令牌, 新令牌)——桂大侠按章分拆双指
REPIPE = [
    (("005",), "〖@桂大侠〗", "〖@桂大侠|桂仲明〗"),
    (("009", "019"), "〖@桂大侠〗", "〖@桂大侠|桂华生〗"),
    (("034",), "〖@金大侠〗", "〖@金大侠|金世遗〗"),
    (("031",), "〖@萧老师〗", "〖@萧老师|萧青峰〗"),
    (("032",), "〖@杨老前辈〗", "〖@杨老前辈|杨仲英〗"),
    (("032",), "〖@毒龙前辈〗", "〖@毒龙前辈|毒龙尊者〗"),
]
DELETE = ["E118358", "E118375", "E118409", "E118446", "E118464",
          "E118550", "E118563", "E118567", "E118392"]

# 书域/段级 dict 别名（挂到管道指向的正确记录；book 限定冰川，task-50）
SCOPED = {
    "E118280": [  # 唐晓澜
        {"display": "唐大侠", "chapters": [11, 17, 35, 38, 39], "book": BOOK},
        {"display": "唐伯伯", "chapters": [17], "book": BOOK},
    ],
    "E118271": [{"display": "陈大人", "chapters": [10], "book": BOOK}],       # 陈天宇
    "E99702": [  # 杨仲英
        {"display": "杨大侠", "chapters": [15], "book": BOOK},
        {"display": "杨老前辈", "chapters": [32], "book": BOOK},
    ],
    "E118294": [  # 邹绛霞
        {"display": "霞儿", "chapters": [18, 19, 31, 32, 36], "book": BOOK},
        {"display": "霞妹", "chapters": [19], "book": BOOK},
    ],
    "E99706": [  # 冯琳（段级）
        {"chapter": 31, "pn": 54, "display": "唐伯母", "book": BOOK},
        {"chapter": 32, "pn": 21, "display": "唐伯母", "book": BOOK},
        {"chapter": 32, "pn": 22, "display": "唐伯母", "book": BOOK},
    ],
    "E118299": [{"chapter": 32, "pn": 22, "display": "唐伯母", "book": BOOK}],  # 冯瑛
    "E1622": [{"display": "桂大侠", "chapters": [5], "book": BOOK}],           # 桂仲明
    "E99707": [{"display": "桂大侠", "chapters": [9, 19], "book": BOOK}],      # 桂华生
    "E118272": [{"display": "金大侠", "chapters": [34], "book": BOOK}],        # 金世遗
    "E118274": [{"display": "萧老师", "chapters": [31], "book": BOOK}],        # 萧青峰
    "E118303": [{"display": "毒龙前辈", "chapters": [32], "book": BOOK}],      # 毒龙尊者
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ---- A. tagged 回挂 ----
    total = 0
    for f in sorted(glob.glob(f"tagged/{BOOK}/*.tagged.md")):
        ch = re.search(r"(\d{3})\.tagged", f).group(1)
        raw = open(f, encoding="utf-8", newline="").read()
        out, n = raw, 0
        for chs, old, new in REPIPE:
            if ch in chs and old in out:
                n += out.count(old)
                out = out.replace(old, new)
        if not n:
            continue
        assert _C1.sk(out) == _C1.sk(raw), f"剥标断言失败 {ch}"
        print(f"  {ch}: 回挂 {n} 处")
        total += n
        if args.apply:
            bak = f"logs/backup/glacier_frag_{ts}/{BOOK}"
            os.makedirs(bak, exist_ok=True)
            if not os.path.exists(os.path.join(bak, os.path.basename(f))):
                open(os.path.join(bak, os.path.basename(f)), "w",
                     encoding="utf-8", newline="").write(raw)
            open(f, "w", encoding="utf-8", newline="").write(out)
    print(f"A. tagged 回挂合计 {total} 处（{'已落盘' if args.apply else 'dry-run'}）")

    # ---- B. registry：书域注记 + 碎片删除 ----
    reg = json.load(open("registry/entities.json", encoding="utf-8"))
    by_id = {e["id"]: e for e in reg["entities"]}
    added = 0
    for eid, items in SCOPED.items():
        rec = by_id[eid]
        for it in items:
            if it not in (rec.get("contextual") or []) and it not in (rec.get("context_notes") or []):
                rec.setdefault("contextual", []).append(dict(it))
                added += 1
    n_before = len(reg["entities"])
    missing = [e for e in DELETE if e not in by_id]
    assert not missing, f"待删实体不在册: {missing}"
    reg["entities"] = [e for e in reg["entities"] if e["id"] not in DELETE]
    print(f"B. 书域/段级注记 +{added} · 删碎片 {len(DELETE)} 个："
          f"{n_before} → {len(reg['entities'])}（{'已落盘' if args.apply else 'dry-run'}）")
    if args.apply:
        bak = f"logs/backup/registry_frag_{ts}"
        os.makedirs(bak, exist_ok=True)
        shutil.copy2("registry/entities.json", os.path.join(bak, "entities.json"))
        tmp = "registry/entities.json.tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            json.dump(reg, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp, "registry/entities.json")
        reg2 = json.load(open("registry/entities.json", encoding="utf-8"))
        assert len(reg2["entities"]) == n_before - len(DELETE)
        print(f"   registry 落盘完成，备份 {bak}")
    else:
        print("\ndry-run 结束（未写盘）。加 --apply 落盘。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
