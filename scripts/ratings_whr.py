# -*- coding: utf-8 -*-
"""ratings_whr.py —— 工具 E·E2 评分引擎（spec 007 T2）。

WHR 全历史等级分（Coulom 2008 简正实现）：
  每人物评分轨迹 r(t) 按时间随机游走先验联结；似然 = Bradley-Terry 连续软分；
  MAP 估计 = 逐人逐日 Newton 迭代（g'/g''），全人物 × R 轮。
输出：site/data/ratings.json（v2 · legacy 字段兼容）+ ratings-glicko-archive.json（重写前归档）。
分档：绝对锚定（吕四娘/了因/哈玛雅 终值校准）——锚定人物与微调记录入 meta。
W2-C1（天山演示版总体方案 §3.1 P0-2/§4.3 C1/§5.5，2026-11-09）新增 --scope：
  - --scope <profile>：对局按 book ∈ scope 过滤（players/conflicts/curve 随过滤后对局重算，
    口径与 EX 层一致）；meta 加 scope/books 键；--scope all 与不传参数同为全量口径（R6）。
  - players 双键：legacy（rating/rd/tier/w-d-l/per_book/top_evidence——RatingExplorer 现行
    契约）+ v2（final/uncertainty/curve/peak——武评 v2 契约）。
  - 管线顺序固化见 scripts/run_pipeline.py：本工具读 clean_matches.py 的 matches-v2 产物，
    必须排在其后（EX-5 v1 legacy 中间层不得后跑覆盖）。
用法：python scripts/ratings_whr.py [--scope tianshan-demo]
"""
import json
import math
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import SITE_DATA, today  # noqa: E402

# W2-C1：scope 基础设施复用（export_site_common 在 wuxia-kb/scripts，import 胜过复制——同 W0-T3b）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / "wuxia-kb" / "scripts"
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402

# F1（武评 4 书 → 7 书，2026-11-12）：CHRONO 扩至 site_scope tianshan-demo 编年序 7 书——
# book_day 时间轴与 per_book（榜域动态派生源）需要新 3 书键；引擎算法/参数零改动。
# 全量口径（scope=None）CHRONO 仍为列表本身——matches 无对应书目时自然不出现。
CHRONO = ["散花女侠", "联剑风云录", "白发魔女传", "塞外奇侠传",
          "七剑下天山", "冰魄寒光剑", "江湖三女侠"]
SIGMA = 0.6            # 单日随机游走 σ（自然 logit 单位 · Coulom 口径）
ROUNDS = 25
INIT = 0.0
ANCHORS = ["吕四娘", "了因", "哈玛雅"]
SCALE = 173.7  # 自然单位 → Elo 显示换算（400/ln10）
TIERS = [("绝顶", 20), ("超一流", 80), ("一流", 140), ("二流", 200)]


def book_day(book, loc):
    try:
        chap = int(str(loc)[:3])
    except (ValueError, TypeError):
        chap = 0
    return CHRONO.index(book) * 1000 + chap if book in CHRONO else 99000


def filter_matches(matches, scope=None):
    """对局按 book ∈ scope 过滤（W2-C1，口径与 EX 层 filter_matches 一致）。

    scope=None（全量口径）恒等返回（方案 R6）；scope 口径下 book 缺失/空（不可归书）即裁
    （演示口径宁缺毋滥）。
    """
    if scope is None:
        return list(matches)
    return [m for m in matches if esc.in_scope(m.get("book"), scope)]


def run_whr(matches):
    """WHR 引擎 + 聚合（纯函数，合成对局可直调）→ (players_out, thresholds, conflicts)。

    players 双键（W2-C1）：legacy（rating/rd/tier/w-d-l/per_book/top_evidence——RatingExplorer
    现行契约，rating=final 取整、rd=uncertainty 取整）+ v2（final/uncertainty/curve/peak）。
    """
    # 索引：games[person] = [(day, opp, s, mid)]；days[person] = sorted set
    games = defaultdict(list)
    days = defaultdict(set)
    for mt in matches:
        d = book_day(mt["book"], mt["loc"])
        s = float(mt.get("s", 0.5))
        games[mt["a"]].append((d, mt["b"], s, mt["id"]))
        games[mt["b"]].append((d, mt["a"], 1.0 - s, mt["id"]))
        days[mt["a"]].add(d)
        days[mt["b"]].add(d)
    blocks = {p: sorted(ds) for p, ds in days.items()}

    # 初始化
    r = defaultdict(dict)   # r[person][day] = rating
    for p, ds in blocks.items():
        for t in ds:
            r[p][t] = INIT

    def games_of(p, t):
        return [(o, s, mid) for (d, o, s, mid) in games[p] if d == t]

    # Newton 迭代
    for _round in range(ROUNDS):
        max_step = 0.0
        for p in blocks:
            ds = blocks[p]
            for idx, t in enumerate(ds):
                prev_t = ds[idx - 1] if idx > 0 else None
                next_t = ds[idx + 1] if idx + 1 < len(ds) else None
                rt = r[p][t]
                g1 = 0.0
                g2 = -1.0 / (SIGMA * SIGMA)
                if prev_t is not None:
                    diff = rt - r[p][prev_t]
                    gap = max(1, t - prev_t)
                    g1 += -diff / (SIGMA * SIGMA * gap)
                    g2 += -1.0 / (SIGMA * SIGMA * gap)
                if next_t is not None:
                    diff = rt - r[p][next_t]
                    gap = max(1, next_t - t)
                    g1 += -diff / (SIGMA * SIGMA * gap)
                    g2 += -1.0 / (SIGMA * SIGMA * gap)
                for opp, s, _mid in games_of(p, t):
                    ro = r[opp].get(t)
                    if ro is None:
                        continue
                    E = 1.0 / (1.0 + math.exp(-(rt - ro)))
                    g1 += s - E
                    g2 += -E * (1 - E)
                if abs(g2) < 1e-9:
                    continue
                step = g1 / g2
                rt = rt - step
                max_step = max(max_step, abs(step))
                r[p][t] = rt
        if max_step < 0.5:
            break

    # 聚合输出
    players_out = []
    for p in sorted(blocks):
        ds = blocks[p]
        # 不确定度：末日 Newton 曲率倒数（自然单位）→ 显示乘 SCALE
        ds_last = ds[-1]
        rt = r[p][ds_last]
        g2 = -1.0 / (SIGMA * SIGMA)
        if len(ds) > 1:
            g2 += -1.0 / (SIGMA * SIGMA * max(1, ds_last - ds[-2]))
        for opp, sc, _mid in games_of(p, ds_last):
            ro = r[opp].get(ds_last)
            if ro is None:
                continue
            E = 1.0 / (1.0 + math.exp(-(rt - ro)))
            g2 += -E * (1 - E)
        u = math.sqrt(1.0 / abs(g2)) if abs(g2) > 1e-12 else 300.0
        curve = [{"t": t, "r": round(1500 + SCALE * r[p][t]),
                  "u": round(min(300.0, SCALE * u * (1 + 0.15 * (len(ds) - 1 - i))), 1)}
                 for i, t in enumerate(ds)]
        final = curve[-1]["r"]
        uncertainty = curve[-1]["u"]
        peak = max(curve, key=lambda c: c["r"])
        wins = sum(1 for mt in matches if (mt["a"] == p and mt["outcome"] == "win") or (mt["b"] == p and mt["outcome"] == "loss"))
        losses = sum(1 for mt in matches if (mt["a"] == p and mt["outcome"] == "loss") or (mt["b"] == p and mt["outcome"] == "win"))
        draws = sum(1 for mt in matches if mt["a"] == p or mt["b"] == p) - wins - losses
        per_book = {}
        for bi, book in enumerate(CHRONO):
            lo, hi = bi * 1000, bi * 1000 + 1000
            seg = [c for c in curve if lo <= int(c["t"]) < hi]
            if seg:
                per_book[book] = seg[-1]["r"]
        top_evidence = sorted({mid for (d, o, s, mid) in games[p]})[:3]
        single_n = sum(1 for mt in matches if (mt["a"] == p or mt["b"] == p) and mt.get("layer") == "L1")
        players_out.append({
            "name": p, "rating": final, "rd": round(uncertainty),
            # tier 留待分档段赋值（matches_n<3 → "待考"）；不预置空串——否则
            # `if "tier" not in x` 兜底永不触发（W2-C1 测试发现的 tier 空 Bug，此处修复）
            "final": final, "uncertainty": uncertainty,          # v2 键（legacy 键 = 其取整）
            "matches_n": len(ds), "w/d/l": [wins, draws, losses],
            "per_book": per_book, "curve": curve, "peak": peak,
            "single_n": single_n, "top_evidence": top_evidence,
        })

    # 分档绝对锚定
    anchor_finals = [x["rating"] for x in players_out if x["name"] in ANCHORS and x["matches_n"] >= 1]
    if anchor_finals:
        A = min(anchor_finals)
    else:
        A = 1600
    thresholds = {"绝顶": round(A - TIERS[0][1]), "超一流": round(A - TIERS[1][1]),
                  "一流": round(A - TIERS[2][1]), "二流": round(A - TIERS[3][1])}

    def tier_of(v):
        for name, th in (("绝顶", thresholds["绝顶"]), ("超一流", thresholds["超一流"]),
                         ("一流", thresholds["一流"]), ("二流", thresholds["二流"])):
            if v >= th:
                return name
        return "三流"

    main_list = [x for x in players_out if x["matches_n"] >= 3]
    for x in main_list:
        x["tier"] = tier_of(x["rating"])
    for x in players_out:
        if "tier" not in x:
            x["tier"] = tier_of(x["rating"]) if x["matches_n"] >= 3 else "待考"

    conflicts = []
    disp = {x["name"]: x["rating"] for x in players_out}
    for mt in matches:
        if mt["outcome"] == "draw" or mt.get("trust") != "high":
            continue
        winner = mt["a"] if mt["outcome"] == "win" else mt["b"]
        loser = mt["b"] if mt["outcome"] == "win" else mt["a"]
        delta = disp.get(loser, INIT) - disp.get(winner, INIT)
        if delta >= 120:
            conflicts.append({"type": "明文×数据", "claim": f"（{mt['layer']} 层裁决，定位符见对局）",
                              "claim_loc": f"{mt['book']}·{mt['loc']}",
                              "data": {"winner": winner, "loser": loser, "delta": round(delta), "match": mt["id"]},
                              "note": "剧情保护候选：可能是主角光环/旁白夸张/抽取误差——冲突≠穿帮"})
    conflicts.sort(key=lambda c: -c["data"]["delta"])
    conflicts = conflicts[:20]
    return players_out, thresholds, conflicts


def build_payload(players_out, thresholds, conflicts, matches, scope=None):
    """ratings.json payload 组装（W2-C1：scope 口径 meta 加 scope/books；全量口径形态不变）。

    scope 口径 books = 过滤后对局实际覆盖的 CHRONO 书（编年序）；全量口径保持 CHRONO。
    """
    books = CHRONO
    note = ("全历史等级分：追溯重评、榜单稳定；软分数 s 为唯一输入；"
            "旧引擎见 ratings-glicko-archive.json")
    if scope is not None:
        books = [b for b in CHRONO if b in {m.get("book") for m in matches}]
        note += f"；scope={scope['profile']}：players/conflicts/curve 按过滤后对局重算"
    payload = {
        "meta": {"generated": today(), "engine": "whr",
                 "params": {"sigma_day": SIGMA, "rounds": ROUNDS, "init": INIT},
                 "tiers": thresholds,
                 "tier_anchors": {"names": ANCHORS, "rule": "终值下界−20 为绝顶线；每版本微调记录于 method"},
                 "calibration": {"sampled": 0, "precision": None, "recall": None,
                                 "note": "抽检 100 场待办（spec 007 T3 骨架已生成）"},
                 "books": books, "totals": {"players": len(players_out), "matches": len(matches)},
                 "note": note},
        "players": sorted(players_out, key=lambda x: -x["rating"]),
        "conflicts": conflicts,
    }
    if scope is not None:
        payload["meta"]["scope"] = scope["profile"]
    return payload


def main() -> int:
    # W2-C1：--scope 解析（--scope all / 不传 = 全量口径，None；同 W0-T3a/T3b）
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    matches_path = SITE_DATA / "matches.json"
    m = json.loads(matches_path.read_text(encoding="utf-8"))
    all_matches = m.get("matches", [])
    matches = filter_matches(all_matches, scope)
    if scope is not None:
        print(f"[whr] scope={scope['profile']}: 对局 {len(all_matches)} → {len(matches)}"
              f"（scope 外裁 {len(all_matches) - len(matches)}）")

    # 归档旧引擎产物
    old = SITE_DATA / "ratings.json"
    if old.exists():
        arch = SITE_DATA / "ratings-glicko-archive.json"
        shutil.copyfile(old, arch)
        print(f"-> 旧引擎产物已归档 {arch}")

    players_out, thresholds, conflicts = run_whr(matches)
    payload = build_payload(players_out, thresholds, conflicts, matches, scope=scope)
    out = SITE_DATA / "ratings.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    scope_note = f"（scope={scope['profile']}）" if scope is not None else ""
    print(f"-> {out} · players {len(players_out)} · conflicts {len(conflicts)} · tiers {thresholds}{scope_note}")
    named = [p for p in players_out if p["matches_n"] >= 3]
    named.sort(key=lambda x: -x["rating"])
    print("Top 10（主榜口径 n≥3）:")
    for p in named[:10]:
        w, dr, l = p["w/d/l"]
        print(f"  {p['tier']} {p['name']:<6} {p['rating']}±{p['rd']}  {w}胜{dr}平{l}负")
    for probe in ("凌未风", "练霓裳", "卓一航", "唐晓澜", "楚昭南"):
        x = next((y for y in players_out if y["name"] == probe), None)
        if x:
            print(f"  [核对] {probe}: {x['rating']}±{x['rd']} tier={x['tier']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
