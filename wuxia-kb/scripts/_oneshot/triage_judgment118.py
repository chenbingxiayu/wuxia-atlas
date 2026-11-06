# -*- coding: utf-8 -*-
"""一次性（2026-11-05）：S2 fresh 稿 judgment 118 条裁决执行（docs/45 方法复用）。

裁决原则（全部有 docs/45 §三 先例或 01g/03a 条文背书）：
  Q  quantity_boundary×51 → 摘（单字裸数词/裸量词，docs/45 已裁口径）
  P  plan_negation_verb   → 摘 25 / 留 5（§3.6；保留=已发生/既成捕获）
  D  verb_domain_risk     → 改 2（逐出宫 ■→⊡，docs/45 #56/#58）/ 留 8
  W  verb_wordlist_candidate → 改 2（中剑 ⊞→⊠，04f §2.2 受创结果）/ 摘 1（022[69] 要+杀）/ 留 18
  T  time_boundary        → 改 3（招/次 计数误挂 %时长：两招类→$；三五次→摘）/ 留 1（早上 真实时点）
  F  fence_entity_real_only → 打印现场后按「围栏限实指」裁决
落盘前后逐段剥标断言；仅摘/换标记，正文零增删改。
"""
import io
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parents[2]
TAG = ROOT / "tagged" / "白发魔女传"


def sk(s: str) -> str:
    s = re.sub(r"〖(.)([^〖〗｜|]*)(?:[｜|]([^〖〗]*))?〗", lambda m: m.group(2), s)
    s = re.sub(r"⟦(.)([^⟧｜|]*)(?:[｜|]([^⟧]*))?⟧", lambda m: m.group(2), s)
    return re.sub(r"〘(.)?([^〙]*)〙", lambda m: m.group(2), s)


# (回, 段) → 该段需摘除的单字 $ 量/数词（来自 51 条 flagged display 集合）
j = json.load(io.open(ROOT / "registry/acceptance/白发魔女传_020-032.json", encoding="utf-8"))
qty: dict[tuple[int, int], set[str]] = {}
plan: dict[tuple[int, int], set[str]] = {}
for k, v in j["chapters_data"].items():
    for it in v.get("judgment_items", []):
        ch, pn = int(k), it["pn"]
        if it["type"] == "quantity_boundary" and len(it["display"]) == 1:
            qty.setdefault((ch, pn), set()).add(it["display"])
        elif it["type"] == "plan_negation_verb":
            plan.setdefault((ch, pn), set()).add(it["display"])

# plan_neg 保留白名单（已发生/既成事实；docs/45 #64/#70 同例）
PLAN_KEEP_LAST = {(29, 54)}          # 追到：仅摘最后一处（也将追到），首处「已追到」保留
PLAN_KEEP_ALL = {(29, 12), (29, 101)}  # 拜别下山（已发生）；捉着/捉（既成捕获）

stats = {"qty": 0, "plan": 0, "domain": 0, "wordlist": 0, "time": 0, "fence": 0}
log: list[str] = []

for ch in range(20, 33):
    p = TAG / f"{ch:03d}.tagged.md"
    t = io.open(p, encoding="utf-8").read()
    before = sk(t)
    paras = t.split("\n\n")

    # ---- Q: 单字 $ 摘除 ----
    for (c, pn), disp in qty.items():
        if c != ch:
            continue
        for i, para in enumerate(paras):
            if para.startswith(f"[{pn}] "):
                new = re.sub(
                    "〖[" + re.escape("$") + "][" + "|".join(map(re.escape, sorted(disp))) + r"]〗",
                    lambda m: m.group(0)[2:-1], para)
                if new != para:
                    stats["qty"] += len(re.findall(
                        "〖[" + re.escape("$") + "][" + "|".join(map(re.escape, sorted(disp))) + r"]〗", para))
                    paras[i] = new
                break

    # ---- P: plan_neg 摘除（白名单例外）----
    for (c, pn), disp in plan.items():
        if c != ch:
            continue
        for i, para in enumerate(paras):
            if not para.startswith(f"[{pn}] "):
                continue
            for d in sorted(disp):
                pat = "⟦[..]" + re.escape(d) + "⟧"
                pat = re.sub(r"\[\.\.\]", r"[^⟧｜|]*(?:[｜|][^⟧]*)?", pat)
                hits = re.findall(pat, para)
                if not hits:
                    continue
                if (c, pn) in PLAN_KEEP_ALL:
                    continue
                if (c, pn) in PLAN_KEEP_LAST:
                    # 仅摘最后一处
                    idx = [m for m in re.finditer(pat, para)][-1]
                    tok = idx.group(0)
                    disp = tok[1:-1].split("｜")[0].split("|")[0][1:]
                    para = para[:idx.start()] + disp + para[idx.end():]
                    stats["plan"] += 1
                    log.append(f"{ch:03d}[{pn}] plan 摘(末处) {d}")
                else:
                    def _plan_un(m):
                        inner = m.group(0)[1:-1]
                        return inner.split("｜")[0].split("|")[0][1:]
                    para = re.sub(pat, _plan_un, para)
                    stats["plan"] += len(hits)
                    log.append(f"{ch:03d}[{pn}] plan 摘 {d}×{len(hits)}")
            paras[i] = para

    # ---- D/W/T: 精确替换 ----
    REPL = {
        (28, 19): [("⟦■逐出⟧〖=宫〗", "⟦⊡逐出⟧〖=宫〗", "domain")],
        (28, 33): [("⟦■逐出⟧〖=宫〗", "⟦⊡逐出⟧〖=宫〗", "domain")],
        (22, 88): [("⟦⊞中剑⟧", "⟦⊠中剑⟧", "wordlist")],
        (28, 28): [("⟦⊞中剑⟧", "⟦⊠中剑⟧", "wordlist")],
        (28, 27): [("〖%五六十招|时长〗", "〖$五六十招〗", "time")],
        (31, 71): [("〖%三十招|时长〗", "〖$三十招〗", "time")],
        (30, 50): [("〖%三五次|时长〗", "三五次", "time")],
        # F fence：诗词泛指（docs/45 #45/#77 同例；fresh 复发）
        (24, 69): [("〖%一年|时长〗", "一年", "fence")],
        (30, 69): [("〖=沙漠〗", "沙漠", "fence")],
    }
    for (c, pn), ops in REPL.items():
        if c != ch:
            continue
        for i, para in enumerate(paras):
            if not para.startswith(f"[{pn}] "):
                continue
            for old, new, kind in ops:
                if old in para:
                    para = para.replace(old, new)
                    stats[kind] += 1
                    log.append(f"{ch:03d}[{pn}] {kind} {old} → {new}")
            paras[i] = para

    # ---- W 摘：022[69] 要+杀（未遂意图）----
    if ch == 22:
        for i, para in enumerate(paras):
            if para.startswith("[69] "):
                new = para.replace("⟦⊞杀⟧一通", "杀一通")
                if new != para:
                    para = new
                    stats["wordlist"] += 1
                    log.append("022[69] wordlist 摘 要+杀（未遂）")
                paras[i] = para

    t2 = "\n\n".join(paras)
    assert sk(t2) == before, f"{ch:03d} 剥标不一致"
    if t2 != t:
        io.open(p, "w", encoding="utf-8").write(t2)

print("stats:", stats)
io.open(ROOT / "logs/qa/judgment118_triage_log.txt", "w", encoding="utf-8").write(
    "\n".join(log) or "(none)")
print(f"log: {len(log)} 条 → logs/qa/judgment118_triage_log.txt")
