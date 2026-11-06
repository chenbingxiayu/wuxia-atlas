# -*- coding: utf-8 -*-
"""docs/55 §五 冒大侠双条目考订执行（2026-11-06，冰川治理遗留 ②）。

考订结论（文本证据驱动）：
  E118362 冒大侠（8次/5回，全为裸显示串）= E118284 冒川生 的碎片化重复登记。
  证据：① 全书 〖@冒大侠|冒川生〗 显式管道 ×16（另 冒老前辈/冒老头子/冒老师→冒川生
  ×12）——同一显示串在本书已被裁定为冒川生；② 8 处裸 〖@冒大侠〗 语境全部指向同一人
  （峨嵋金光寺开山结缘盛会主人/冰川天女伯父/去世下土，ch25「办冒老师的大事」即丧事）；
  ③ 冒姓候选无第二人（冒浣莲/冒辟疆 各为独立实体且性别/时代不符）。
  合并先例：康熙三方归并（docs/48 §5.2）——保留信息最全条目，吸收别名+sources，删重复。

动作：
  A. tagged（冰川）：裸显示串回挂 〖冒大侠〗×8 〖冒老前辈〗×7 〖冒伯伯〗×2 〖冒老师〗×1
     → 〖@X|冒川生〗（docs/55「摘管管道可回挂」承诺；备份+sk 剥标断言）。
  B. registry/entities.json：
     - E118284 aliases += 冒伯伯（原缺，全书仅冰川 2 处且确指冒川生）；
     - E118284 sources ← 并集（既有 ∪ E118362.sources ∪ 回挂后实测章）；
     - note 追加考订裁定；删除 E118362（先 grep 确认无其他消费方——concordance 由
       tagged 再生，不手改）。
  C. 自检：实体总数 -1；E118362 全仓引用清零（concordance/relations/events 由下游
     重跑刷新，不在本脚本范围）。

用法：python -I scripts/_oneshot/merge_mao_daxia_duplicate.py --apply
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
KEEP, DROP = "E118284", "E118362"
REPIPE = {
    "〖@冒大侠〗": "〖@冒大侠|冒川生〗",
    "〖@冒老前辈〗": "〖@冒老前辈|冒川生〗",
    "〖@冒伯伯〗": "〖@冒伯伯|冒川生〗",
    "〖@冒老师〗": "〖@冒老师|冒川生〗",
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
        n = sum(raw.count(k) for k in REPIPE)
        if not n:
            continue
        out = raw
        for k, v in REPIPE.items():
            out = out.replace(k, v)
        assert _C1.sk(out) == _C1.sk(raw), f"剥标断言失败 {f}"
        print(f"  {os.path.basename(f)}: 回挂 {n} 处")
        total += n
        if args.apply:
            bak = f"logs/backup/mao_merge_{ts}/{BOOK}"
            os.makedirs(bak, exist_ok=True)
            if not os.path.exists(os.path.join(bak, os.path.basename(f))):
                open(os.path.join(bak, os.path.basename(f)), "w",
                     encoding="utf-8", newline="").write(raw)
            open(f, "w", encoding="utf-8", newline="").write(out)
    print(f"A. tagged 回挂合计 {total} 处（{'已落盘' if args.apply else 'dry-run'}）")

    # ---- B. registry 合并 ----
    reg = json.load(open("registry/entities.json", encoding="utf-8"))
    ents = {e["id"]: e for e in reg["entities"]}
    keep, drop = ents[KEEP], ents[DROP]
    assert keep["canonical"] == "冒川生" and drop["canonical"] == "冒大侠"
    if "冒伯伯" not in keep["aliases"]:
        keep["aliases"].append("冒伯伯")
    # 回挂后实测章（〖@X|冒川生〗 或 〖@冒川生…〗 令牌所在章）
    chs = set()
    for f in glob.glob(f"tagged/{BOOK}/*.tagged.md"):
        t = open(f, encoding="utf-8").read()
        if re.search("〖@冒川生[|〗]|〖@(?:冒大侠|冒老前辈|冒伯伯|冒老师|冒老头子)\\|冒川生〗", t):
            chs.add(re.search(r"(\d{3})\.tagged", f).group(1).lstrip("0"))
    merged_src = sorted(set(keep["sources"]) | set(drop["sources"]) | chs,
                        key=lambda s: int(s))
    print(f"B. sources: {len(keep['sources'])} ∪ {len(drop['sources'])} ∪ 实测{len(chs)} → {len(merged_src)} 章")
    keep["sources"] = merged_src
    keep["note"] = (keep.get("note", "") + "；2026-11-06 考订合并 E118362（裸冒大侠×8 同指"
                    "冒川生，docs/55 §五；证据：显式管道×16+语境逐点核，先例 docs/48 §5.2）"
                    ).lstrip("；")
    n_before = len(reg["entities"])
    reg["entities"] = [e for e in reg["entities"] if e["id"] != DROP]
    print(f"B. 删除 {DROP}：实体 {n_before} → {len(reg['entities'])}"
          f"（{'已落盘' if args.apply else 'dry-run'}）")
    if args.apply:
        bak = f"logs/backup/registry_mao_{ts}"
        os.makedirs(bak, exist_ok=True)
        shutil.copy2("registry/entities.json", os.path.join(bak, "entities.json"))
        tmp = "registry/entities.json.tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            json.dump(reg, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp, "registry/entities.json")
        reg2 = json.load(open("registry/entities.json", encoding="utf-8"))
        assert len(reg2["entities"]) == n_before - 1
        assert not any(e["id"] == DROP for e in reg2["entities"])
        print(f"   registry 落盘完成，备份 {bak}")
    else:
        print("\ndry-run 结束（未写盘）。加 --apply 落盘。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
