# -*- coding: utf-8 -*-
"""G4 动词消歧批次 · 语境提取器（wave-1：刺/杀，2026-11-06）。

从 logs/verb_validation/<书>.json 的 W-MULTIDOMAIN warnings 中取指定 surface，
逐 token 提取所在段上下文 → logs/qa/verb_disamb_<书>_wave1.md（评审底稿）。
裁定流程：人工/模型逐条写裁定 TSV（列：章|pn|旧令牌|裁定[gloss/reDomain/strip]|新令牌或说明）
→ scripts/_oneshot/verb_disamb_apply.py 机械执行（备份+sk 断言）→ 复跑 verb-validate。

用法：python -I scripts/_oneshot/verb_disamb_extract.py 冰川天女传 刺,杀
"""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)


def main() -> int:
    book = sys.argv[1]
    surfaces = set(sys.argv[2].split(","))
    data = json.load(open(f"logs/verb_validation/{book}.json", encoding="utf-8"))
    warns = [w for w in data.get("warnings", [])
             if w.get("category") == "W-MULTIDOMAIN" and w.get("surface") in surfaces]
    print(f"{book} W-MULTIDOMAIN（{'/'.join(sorted(surfaces))}）: {len(warns)} 条")
    by_ch: dict = {}
    for w in warns:
        by_ch.setdefault(w["chapter"], []).append(w)
    out = [f"# {book} 动词消歧评审底稿 wave-1（{'/'.join(sorted(surfaces))}）",
           "",
           f"warning {len(warns)} 条；每条给出：pn / 令牌 / 全书分布 / 段内语境（-60..+40 字）。",
           "裁定列：gloss=补说明管道 · reDomain=改域 · strip=摘标。", ""]
    for ch in sorted(by_ch):
        t = open(f"tagged/{book}/{ch}.tagged.md", encoding="utf-8").read()
        # 段号 → 段文本
        paras = {}
        pn = None
        buf_start = 0
        for m in re.finditer(r"\[(\d+)\]", t):
            if pn is not None:
                paras[pn] = t[buf_start:m.start()]
            pn = int(m.group(1))
            buf_start = m.end()
        if pn is not None:
            paras[pn] = t[buf_start:]
        out.append(f"## {ch}")
        for w in sorted(by_ch[ch], key=lambda x: x["pn"]):
            p = paras.get(w["pn"], "")
            i = p.find(w["token"])
            ctx = p[max(0, i - 60): i + len(w["token"]) + 40].replace("\n", " ") if i >= 0 else p[:100]
            out.append(f"- [{w['pn']}] `{w['token']}` 分布[{w.get('observed_domains','')}] "
                       f"主域 {w.get('major_domain','?')}×{w.get('major_count','?')}｜…{ctx}…")
        out.append("")
    dst = f"logs/qa/verb_disamb_{book}_wave1.md"
    open(dst, "w", encoding="utf-8", newline="").write("\n".join(out))
    print(f"评审底稿 → {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
