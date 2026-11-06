# -*- coding: utf-8 -*-
"""G4 wave-2 全量语境提取（211 条 W-MULTIDOMAIN → 评审底稿）。"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)

book = "冰川天女传"
d = json.load(open(f"logs/verb_validation/{book}.json", encoding="utf-8"))
ws = [w for w in d["warnings"] if w.get("category") == "W-MULTIDOMAIN"]
by_ch = {}
for w in ws:
    by_ch.setdefault(w["chapter"], []).append(w)
out = ["# 冰川天女传 W-MULTIDOMAIN 全量评审底稿 wave-2（%d 条）" % len(ws), "",
       "裁定：gloss=补说明 · reDomain=改域 · strip=摘标。", ""]
for ch in sorted(by_ch):
    t = open(f"tagged/{book}/{ch}.tagged.md", encoding="utf-8").read()
    ms = list(re.finditer(r"\[(\d+)\]", t))
    paras = {}
    for i, m in enumerate(ms):
        pn = int(m.group(1))
        start = m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(t)
        paras[pn] = t[start:end]
    out.append("## " + ch)
    for w in sorted(by_ch[ch], key=lambda x: x["pn"]):
        p = paras.get(w["pn"], "")
        i = p.find(w["token"])
        ctx = p[max(0, i - 55): i + len(w["token"]) + 35].replace("\n", " ") if i >= 0 else p[:90]
        br = "词表" if "词表内" in w["message"] else "语料"
        out.append(f"- [{w['pn']}]`{w['token']}`({br})｜…{ctx}…")
    out.append("")
dst = "logs/qa/verb_disamb_冰川天女传_wave2.md"
open(dst, "w", encoding="utf-8", newline="").write("\n".join(out))
print("rows:", len(ws), "->", dst)
