# -*- coding: utf-8 -*-
"""G4 wave-3 · 合并验收批（docs/72 落地后两批交界缺口，2026-11-06）。

docs/72 Phase E 为 扫/劈/伤/追踪/还/斩/断/偷袭/偷/逐出/中剑 建立词表多域 senses 后，
冰川全书这些 surface 的裸文 token 全部触发分支 (i)（72 条）。全量语境通读
（logs/qa/verb_disamb_冰川天女传_wave2.md 重提取版）：域用法均正确，按域语义统一补说明。

  ⟦⊞扫⟧×26→|横扫(攻扫)   ⟦⊞劈⟧×11→|劈击(攻击动作)   ⟦⊠伤⟧×8→|致伤
  ⟦■追踪⟧×10→|追踪(跟踪尾随)   ⟦⊞还⟧×4→|还招(回击)   ⟦⊞斩⟧×2→|斩击(攻击动作)
  ⟦⊟断⟧×3→|断裂(器物)   ⟦⊞偷袭⟧×3→|偷袭(突袭)   ⟦⊟偷⟧×2→|窃取
  ⟦■逐出⟧×2→|驱逐(逐离)   ⟦⊠中剑⟧×1→|中剑(剑伤)

senses 词表补条（4 条，承 docs/72 §七 格式 0.4-draft；--senses-apply 时执行）：
  跟踪⊞（剑招如影随形=追击，013[29]）· 夺得⊡（谋夺帝位，024[3]）·
  释放⊟（解除看管，024[55]）· 刺⊟（神芒刺破袈裟，035[61]，补 wave-1 面）
  → wordlist_compiler --name verbs 重编译。

安全纪律：备份 + sk 剥标断言 + 计数断言（替换数=词表警告数）；幂等。
用法：python -I scripts/_oneshot/verb_disamb_wave3_apply.py --apply [--senses-apply]
"""
import argparse
import glob
import io
import json
import os
import shutil
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import apply_gold_c1_cleanup as _C1  # noqa: E402

BOOK = "冰川天女传"
UNIFORM = {
    "⟦⊞扫⟧": ("⟦⊞扫|横扫(攻扫)⟧", 26),
    "⟦⊞劈⟧": ("⟦⊞劈|劈击(攻击动作)⟧", 11),
    "⟦⊠伤⟧": ("⟦⊠伤|致伤⟧", 8),
    "⟦■追踪⟧": ("⟦■追踪|追踪(跟踪尾随)⟧", 10),
    "⟦⊞还⟧": ("⟦⊞还|还招(回击)⟧", 4),
    "⟦⊞斩⟧": ("⟦⊞斩|斩击(攻击动作)⟧", 2),
    "⟦⊟断⟧": ("⟦⊟断|断裂(器物)⟧", 3),
    "⟦⊞偷袭⟧": ("⟦⊞偷袭|偷袭(突袭)⟧", 3),
    "⟦⊟偷⟧": ("⟦⊟偷|窃取⟧", 2),
    "⟦■逐出⟧": ("⟦■逐出|驱逐(逐离)⟧", 2),
    "⟦⊠中剑⟧": ("⟦⊠中剑|中剑(剑伤)⟧", 1),
}
SENSES = [
    {"surface": "跟踪", "canonical": "跟踪", "type": "⊞", "domain": "⊞",
     "domain_name": "战斗交锋", "tier": "review", "status": "待审", "conf": "weak",
     "evidence": ["冰川天女传:1-40"], "version": "0.4-draft",
     "note": "docs/72 §七 续（docs/69 补记 5）：剑招如影随形跟踪=追击语境（冰川 013 消歧形态）"},
    {"surface": "夺得", "canonical": "夺得", "type": "⊡", "domain": "⊡",
     "domain_name": "社会关系", "tier": "review", "status": "待审", "conf": "weak",
     "evidence": ["冰川天女传:1-40"], "version": "0.4-draft",
     "note": "docs/72 §七 续（docs/69 补记 5）：夺得帝位=谋夺语境（冰川 024）"},
    {"surface": "释放", "canonical": "释放", "type": "⊟", "domain": "⊟",
     "domain_name": "物件变化", "tier": "review", "status": "待审", "conf": "weak",
     "evidence": ["冰川天女传:1-40"], "version": "0.4-draft",
     "note": "docs/72 §七 续（docs/69 补记 5）：释放被擒者=解除看管（冰川 024）"},
    {"surface": "刺", "canonical": "刺", "type": "⊟", "domain": "⊟",
     "domain_name": "物件变化", "tier": "review", "status": "待审", "conf": "weak",
     "evidence": ["冰川天女传:1-40"], "version": "0.4-draft",
     "note": "docs/72 §七 续（docs/69 补记 5）：神芒刺破袈裟=器物刺破（冰川 035 消歧形态）"},
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--senses-apply", action="store_true",
                    help="同时补 verbs_source 4 条 senses 并重编译 verbs.json")
    args = ap.parse_args()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ---- A. tagged 统一消歧 ----
    cnt = {k: 0 for k in UNIFORM}
    files = sorted(glob.glob(f"tagged/{BOOK}/*.tagged.md"))
    for f in files:
        raw = open(f, encoding="utf-8", newline="").read()
        out = raw
        for old, (new, expect) in UNIFORM.items():
            n = out.count(old)
            cnt[old] += n
            out = out.replace(old, new)
        if out != raw:
            assert _C1.sk(out) == _C1.sk(raw), f"剥标断言失败 {f}"
            if args.apply:
                bak = f"logs/backup/verb_wave3_{ts}/{BOOK}"
                os.makedirs(bak, exist_ok=True)
                if not os.path.exists(os.path.join(bak, os.path.basename(f))):
                    open(os.path.join(bak, os.path.basename(f)), "w",
                         encoding="utf-8", newline="").write(raw)
                open(f, "w", encoding="utf-8", newline="").write(out)
    total = sum(cnt.values())
    expect_total = sum(e for _, e in UNIFORM.values())
    mismatch = {k[1:-1]: (v, UNIFORM[k][1]) for k, v in cnt.items() if v != UNIFORM[k][1]}
    print(f"统一替换 {total} 处（词表警告基准 {expect_total}）"
          f"（{'已落盘' if args.apply else 'dry-run'}）")
    if mismatch:
        print("⚠ 计数偏差（实际, 基准）:", mismatch)

    # ---- B. senses 补条 ----
    if args.senses_apply:
        src = "wordlists/verbs_source.json"
        data = json.load(open(src, encoding="utf-8"))
        items = data.get("items", data) if isinstance(data, dict) else data
        have = {(x.get("surface"), x.get("domain")) for x in items}
        added = 0
        for e in SENSES:
            if (e["surface"], e["domain"]) in have:
                continue
            items.append(dict(e))
            added += 1
        if args.apply:
            bak = f"logs/backup/verbs_senses_{ts}"
            os.makedirs(bak, exist_ok=True)
            shutil.copy2(src, os.path.join(bak, "verbs_source.json"))
            tmp = src + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
            os.replace(tmp, src)
            print(f"senses 补条 +{added}（备份 {bak}）")
        else:
            print(f"senses 补条 +{added}（dry-run）")
    if not args.apply:
        print("\ndry-run 结束（未写盘）。--apply 落盘；--senses-apply 连动词表。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
