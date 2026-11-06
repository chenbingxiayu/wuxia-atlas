# -*- coding: utf-8 -*-
"""一次性：judgment 118 条的原始 token 语境检视（裁决输入）。"""
import io
import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

j = json.load(io.open("registry/acceptance/白发魔女传_020-032.json", encoding="utf-8"))
FOCUS_TYPES = {"time_boundary", "fence_entity_real_only"}
FOCUS_VERBS = {"劈", "逐出", "掳", "折断", "重伤", "削断", "中剑", "驱逐", "杀", "刺"}
FOCUS_PLAN = {"下山", "跳下来", "回山", "追到", "回到家", "回家"}

seen = set()
for k, v in j["chapters_data"].items():
    t = io.open(f"tagged/白发魔女传/{int(k):03d}.tagged.md", encoding="utf-8").read()
    paras = {}
    for p in t.split("\n\n"):
        m = re.match(r"\[(\d+)\] ", p)
        if m:
            paras[int(m.group(1))] = p
    for it in v.get("judgment_items", []):
        typ, disp, pn = it["type"], it["display"], it["pn"]
        hit = (typ in FOCUS_TYPES
               or (typ == "verb_domain_risk" and disp in FOCUS_VERBS)
               or (typ == "verb_wordlist_candidate" and disp in FOCUS_VERBS)
               or (typ == "plan_negation_verb" and disp in FOCUS_PLAN))
        if not hit:
            continue
        tag = f"{int(k):03d}[{pn}] {typ[:8]} {disp}"
        if tag in seen:
            continue
        seen.add(tag)
        p = paras.get(pn, "")
        shown = 0
        for m in re.finditer(r"[〖⟦][^〖〗⟧]*[〗⟧]", p):
            inner = re.sub(r"[〖⟦〗⟧]", "", m.group(0)).split("｜")[0].split("|")[0]
            if disp in inner:
                a = max(0, m.start() - 20)
                b = min(len(p), m.end() + 16)
                print(f"{tag} → {p[a:b]}")
                shown += 1
                if shown >= 3:
                    break
