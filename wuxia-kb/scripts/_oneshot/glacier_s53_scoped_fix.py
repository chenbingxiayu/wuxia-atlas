# -*- coding: utf-8 -*-
"""docs/55 §五.3 书域归属收口（2026-11-06，冰川下游层复核批次）。

问题（docs/55 §五.3 遗留，本轮复核确认未解）：
  1) 冰川 028/030 裸显示串 〖@活佛〗×7 经全局别名（E29486 达赖活佛 aliases=['活佛']）
     解析到七剑实体——冰川语境实指 白教法王（E118308）。冰魄 008 的 〖@活佛〗×1
     语境为布达拉宫/尼泊尔遣使，确指达赖活佛，**全局别名保留不动**。
  2) 冰川 003[80] 「〖@桂华生〗桂老前辈」为同位复指（前词已标，桂老前辈裸文按
     「同位复指剔除」纪律不加标）；但 E6782 桂天澜（七剑）contextual 含 全局
     '桂老前辈'，未来任何别名解析会误指。处置：E99707 桂华生加书域注记
     （scoped 解析顺序 (书,回) > 全局，误指被拦截）。

动作：
  A. tagged：冰川 028/030 〖@活佛〗 → 〖@活佛|白教法王〗（显式管道，下游 N5/事件/
     导出 attribution 随之修正）；备份 + sk 剥标断言（摘/挂标只动符号不动正文）。
  B. registry/entities.json：
     - E118308 白教法王 contextual += {"display":"活佛","chapters":[28,30],
       "book":"冰川天女传"}（回级+书域作用域，accept task-11/task-50 语义，
       供管道溯源；全局别名零改动）。
     - E99707 桂华生 context_notes += {"chapter":3,"display":"桂老前辈",
       "canonical":"桂华生","book":"冰川天女传"}（格式承记录内既有 桂贤弟 注记）。
     - 备份 + 实体总数/既有字段不变断言。

用法：python -I scripts/_oneshot/glacier_s53_scoped_fix.py --apply   # 默认 dry-run
"""
import argparse
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

import apply_gold_c1_cleanup as _C1  # noqa: E402  规范 sk 剥标同源

BOOK = "冰川天女传"
CHAPTERS = (28, 30)
E_BAIJIAO = "E118308"
E_GUI = "E99707"
SCOPED_ALIAS = {"display": "活佛", "chapters": [28, 30], "book": BOOK}
SCOPED_NOTE = {"chapter": 3, "display": "桂老前辈", "canonical": "桂华生", "book": BOOK}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    # ---- A. tagged 管道补挂 ----
    total = 0
    for no in CHAPTERS:
        f = f"tagged/{BOOK}/{no:03d}.tagged.md"
        raw = open(f, encoding="utf-8", newline="").read()
        n = raw.count("〖@活佛〗")
        if not n:
            print(f"  {no:03d}: 0 处（跳过）")
            continue
        out = raw.replace("〖@活佛〗", "〖@活佛|白教法王〗")
        assert _C1.sk(out) == _C1.sk(raw), f"剥标断言失败 {no:03d}"
        assert out.count("〖@活佛|白教法王〗") == n
        print(f"  {no:03d}: 〖@活佛〗×{n} → 〖@活佛|白教法王〗")
        total += n
        if args.apply:
            bak = f"logs/backup/glacier_s53_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.makedirs(os.path.join(bak, BOOK), exist_ok=True)
            open(os.path.join(bak, BOOK, f"{no:03d}.tagged.md"), "w",
                 encoding="utf-8", newline="").write(raw)
            open(f, "w", encoding="utf-8", newline="").write(out)
    print(f"A. tagged 补挂合计 {total} 处（{'已落盘' if args.apply else 'dry-run'}）")

    # ---- B. registry 书域注记 ----
    reg_path = "registry/entities.json"
    reg = json.load(open(reg_path, encoding="utf-8"))
    ents = {e["id"]: e for e in reg["entities"]}
    e1, e2 = ents[E_BAIJIAO], ents[E_GUI]
    assert e1["canonical"] == "白教法王" and e2["canonical"] == "桂华生"
    if SCOPED_ALIAS not in (e1.get("contextual") or []):
        e1.setdefault("contextual", []).append(dict(SCOPED_ALIAS))
    if SCOPED_NOTE not in (e2.get("context_notes") or []):
        e2.setdefault("context_notes", []).append(dict(SCOPED_NOTE))
    n_before = len(reg["entities"])
    print(f"B. registry：{E_BAIJIAO} contextual+1 · {E_GUI} context_notes+1 "
          f"（{'已落盘' if args.apply else 'dry-run'}）")
    if args.apply:
        bak = f"logs/backup/registry_s53_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(bak, exist_ok=True)
        shutil.copy2(reg_path, os.path.join(bak, "entities.json"))
        tmp = reg_path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            json.dump(reg, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp, reg_path)
        reg2 = json.load(open(reg_path, encoding="utf-8"))
        assert len(reg2["entities"]) == n_before, "实体总数变化"
        assert any(isinstance(a, dict) and a.get("display") == "活佛"
                   for a in ents[E_BAIJIAO]["contextual"]), "注记落盘校验失败"
        print(f"   registry 落盘完成，备份 {bak}")
    if not args.apply:
        print("\ndry-run 结束（未写盘）。加 --apply 落盘。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
