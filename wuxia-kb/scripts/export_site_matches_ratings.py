# -*- coding: utf-8 -*-
"""EX-5 · matches.json + ratings.json 导出器（消费 D03 事件层 / EX-5）

数据源（新管线，只读）：
  registry/events/<书>.json    event_extractor（D03/13 类）产出（events: type/outcome/
                              subject/object/loc/pn/confidence/source_type/condition_tags）
  tagged/<书>/*.tagged.md      场景胜负词证据（canonical 归一后的场景文本；原文不发布）

导出（按 site/data 2026-11-02 契约）：
  matches.json  {meta, matches[], fighters[]}
    对局单位=场景（同回 pn 距 ≤15 的 T01/T02 事件聚合；一景内同类对手对一场）；
    裁决=旧 build_matches v0.1 胜负词表（强胜1.0/常规0.8/险胜0.6/平0.7）投影到场景文本；
    modifiers=中毒/带伤/偷袭/诈败/放水/切磋（权重乘子同旧 v0.1）；kind=单挑/围攻。
    D03 outcome 五值（胜/负/平/未决/未知）→ 契约值 win/loss/draw；未决/未知不进榜。
  ratings.json  {meta, players[], conflicts[]}
    Glicko-2（r0=1500, rd0=350, σ=0.06, τ=0.5；每场一周期；宇宙编年+回序）；
    展示分长尾收缩 (W·r+5·1500)/(W+5)；分档分位 95/90/70/30 → 绝顶/超一流/一流/二流/三流；
    per_book 每书独立重跑；conflicts=明文×数据倒置（Δdisplay≥120，高置信非平局）。
    引擎参数/词表版本/校准说明全部落 meta。

默认 dry-run（staging + 差异报告）；--apply 才由 export_site_common 备份后写 site/data；
不修改 scripts/export_site_all.py（Lead 统一注册）。不发布原文引文（L0）。

CLI：
  python scripts/export_site_matches_ratings.py                # 全量 dry-run
  python scripts/export_site_matches_ratings.py --book 白发魔女传  # 单书（调试；仍写两文件）
  python scripts/export_site_matches_ratings.py --scope tianshan-demo   # 天山 7 书裁剪口径（W0-T3a）

W0-T3a（天山演示版总体方案 §1.2，2026-11-08）scope 口径：
  - matches/ratings/conflicts 按 book ∈ scope 过滤（对局书单先裁剪）；fighters 按
    过滤后对局重算；players/w-d-l/per_book/conflicts 由过滤后对局重算（build_ratings）；
  - 全量口径（不带 --scope）行为与现状完全一致（方案 R6）。

W2-C1（天山演示版总体方案 §3.1 P0-2/§4.3 C1/§5.5，2026-11-09）legacy 中间层声明：
  本导出器的 matches-v1/glicko2 产物为 legacy 中间层——正式 live 由工具 E
  scripts/clean_matches.py（matches-v2）与 scripts/ratings_whr.py（whr）覆盖；
  部署序列必须保证本导出器先跑、工具 E 后跑（scripts/run_pipeline.py 已固化 §5.5
  唯一顺序），否则页面宣称 WHR 而数据是 glicko2（P0-2 根因复现）。
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict

import config
import export_site_common as esc
import symbols
import relation_validator as rv          # canon 归并（与事件层同口径）
import event_extractor as ev             # 事件层工具（胜负词表/场景/围栏解析复用）

EVENTS_DIR = config.DIR_REGISTRY / "events"
SCHEMA_MATCHES = "matches-v1"
SCHEMA_RATINGS = "ratings-v1"
EXPORTER = "EX-5 export_site_matches_ratings"
SOURCE = "D03 事件层 registry/events（EX-5 event_extractor）+ tagged 场景胜负词证据"

COMBAT_TYPES = {"T01", "T02"}
SCENE_GAP = 15
CHRONO = ["白发魔女传", "塞外奇侠传", "七剑下天山", "江湖三女侠", "冰魄寒光剑"]
R0, RD0, SIGMA, TAU, P_SHRINK = 1500.0, 350.0, 0.06, 0.5, 5
Q = 0.0057565
SCALE = 173.7178
TIER_QUANTILES = [("绝顶", 0.95), ("超一流", 0.90), ("一流", 0.70), ("二流", 0.30)]
WORDLIST_VERSION = "event-v1/胜负词v0.1(移植)"
SCENE_SPLITTER = "pn-gap15/v1"


# ---------------------------------------------------------------- tagged 场景文本
_TEXT_CACHE = {}


def book_texts(book: str) -> dict:
    """{(章, 段): 规范名归一后的场景文本}（原文不发布，仅本地胜负词匹配）。"""
    if book in _TEXT_CACHE:
        return _TEXT_CACHE[book]
    ctx = rv.Ctx(book)
    out = {}
    for path in sorted((rv.TAG / book).glob("*.tagged.md")):
        ch = int(path.name[:3])
        for pn, text in ev.iter_paragraphs(path):
            def repl(m):
                kind, code, body, display, pipe, err = symbols.parse_token(m.group(0))
                if err:
                    return ""
                if kind == "entity":
                    return ctx.canon(display or "", pipe, code) or ""
                return body[1:].split("|", 1)[0]
            out[(ch, pn)] = symbols.TOKEN_RE.sub(repl, text)
    _TEXT_CACHE[book] = out
    return out


def scene_text(texts: dict, chapter: int, pns: list) -> str:
    lo = max(0, min(pns) - 3)
    hi = min(pns) + 3
    parts = [texts.get((chapter, pn), "") for pn in range(lo, hi + 1)]
    return "".join(parts)


# ---------------------------------------------------------------- 对局构建
def build_matches(events_by_book: dict, books: list) -> tuple:
    matches = []
    fighters = set()
    excluded = {"dropped": 0, "in_quote": 0, "no_participants": 0}
    evidence_src = Counter({"scene_word": 0, "event_outcome": 0})
    covered = set()          # (book, chapter, sorted pair) 场景已出对局（同回同场景去重）
    mid = 0
    for book in books:
        combat = [e for e in events_by_book.get(book, []) if e.get("type") in COMBAT_TYPES]
        if not combat:
            continue
        texts = book_texts(book)
        by_ch = defaultdict(list)
        for e in combat:
            by_ch[int(e["chapter"])].append(e)
        for ch in sorted(by_ch):
            group = sorted(by_ch[ch], key=lambda e: (int(e["pn"]), e.get("event_id", "")))
            scenes, cur = [], [group[0]]
            for e in group[1:]:
                if int(e["pn"]) - int(cur[-1]["pn"]) <= SCENE_GAP:
                    cur.append(e)
                else:
                    scenes.append(cur)
                    cur = [e]
            scenes.append(cur)
            for si, scene in enumerate(scenes):
                text = scene_text(texts, ch, [int(e["pn"]) for e in scene])
                mods = ev.modifiers_of(text)
                weight_mult = 1.0
                for mo in mods:
                    weight_mult *= ev.MOD_MULT.get(mo, 1.0)
                has_zhabai = "诈败" in mods
                has_draw = any(w in text for w in ev.DRAW_WORDS)
                pair_count = Counter()
                pair_event = {}
                for e in scene:
                    gate = e.get("gate")
                    reason = e.get("gate_reason") or ""
                    if gate == "excluded":
                        if "R1" in reason or "R2" in reason:
                            excluded["no_participants"] += 1
                        else:
                            excluded["dropped"] += 1
                        continue
                    if gate == "review" and "R4" in reason:
                        excluded["in_quote"] += 1
                        continue
                    a = (e.get("subject") or "").strip()
                    b = (e.get("object") or "").strip()
                    if not a or not b or a == b:
                        excluded["no_participants"] += 1
                        continue
                    if e.get("source_type") == "人物发言":
                        excluded["in_quote"] += 1
                        continue
                    key = tuple(sorted((a, b)))
                    pair_count[key] += 1
                    if e.get("outcome") in ("胜", "负", "平"):
                        pair_event.setdefault(key, e)
                persons = {p for pair in pair_count for p in pair}
                if len(persons) < 2:
                    continue
                kind = "围攻" if len(persons) > 2 else "单挑"
                for (a, b), _cnt in pair_count.most_common():
                    winner, wcls, _hits = ev.winner_from_words(text, a, b)
                    if winner in (a, b):
                        outcome = "win" if winner == a else "loss"
                        base = wcls or 0.8
                        if has_zhabai:
                            outcome, base = "draw", 0.5
                    elif has_draw or winner == "draw":
                        outcome, base = "draw", 0.7
                    else:
                        pe = pair_event.get((a, b))
                        if pe is None:
                            continue   # 无明文裁决 → 不入榜（避免噪声）
                        # 回退：事件层单事件 outcome（胜/负=主体视角）
                        if pe["outcome"] == "平":
                            outcome, base = "draw", 0.7
                        else:
                            winner = pe["subject"] if pe["outcome"] == "胜" else pe["object"]
                            outcome = "win" if winner == a else "loss"
                            base = pe.get("outcome_weight") or 0.8
                    weight = round(min(1.0, base) * weight_mult, 2)
                    mid += 1
                    src = "scene_word" if (wcls or winner == "draw") else "event_outcome"
                    evidence_src[src] += 1
                    covered.add((book, ch, tuple(sorted((a, b)))))
                    matches.append({
                        "id": f"M{mid:03d}", "a": a, "b": b, "outcome": outcome,
                        "weight": weight,
                        "confidence": "high" if (wcls or 0) >= 1.0 else "medium",
                        "modifiers": list(mods), "kind": kind, "book": book,
                        "loc": f"{ch:03d}:{int(scene[0]['pn']):03d}",
                        "scene": f"S{ch:03d}-{si + 1:02d}",
                        "evidence": {"source": src,
                                     "rule": "胜负词表（场景）" if src == "scene_word"
                                             else "事件层 outcome 回退"},
                    })
                    fighters.update((a, b))
    # D2③ 覆盖增强：场景未出对局（或该回该对未覆盖）的事件层 outcome 直接成局
    for book in books:
        for e in events_by_book.get(book, []):
            if e.get("type") not in COMBAT_TYPES or e.get("gate") != "ok":
                continue
            a = (e.get("subject") or "").strip()
            b = (e.get("object") or "").strip()
            if not a or not b or a == b or e.get("outcome") not in ("胜", "负", "平"):
                continue
            ch = int(e["chapter"])
            pair = tuple(sorted((a, b)))
            if (book, ch, pair) in covered:
                continue
            if e["outcome"] == "平":
                outcome, base = "draw", 0.7
            else:
                winner = e["subject"] if e["outcome"] == "胜" else e["object"]
                # 用展示序（a<=b）表达 win/loss：胜者=a 则 win
                outcome = "win" if winner == a else "loss"
                base = e.get("outcome_weight") or 0.8
            weight = round(min(1.0, base), 2)
            mid += 1
            evidence_src["event_outcome"] += 1
            covered.add((book, ch, pair))
            matches.append({
                "id": f"M{mid:03d}", "a": a, "b": b, "outcome": outcome, "weight": weight,
                "confidence": "medium", "modifiers": list(e.get("condition_tags") or []),
                "kind": "单挑", "book": book, "loc": e.get("loc") or f"{ch:03d}:{int(e['pn']):03d}",
                "scene": f"S{ch:03d}-E{int(e['pn']) // 15 + 1:02d}",
                "evidence": {"source": "event_outcome",
                             "rule": "事件层 outcome（触发词/胜负词投影）"},
            })
            fighters.update((a, b))
    return matches, sorted(fighters), excluded, dict(evidence_src)


# ---------------------------------------------------------------- scope 过滤（W0-T3a）
def filter_matches(matches: list, scope) -> list:
    """对局按 book ∈ scope 过滤（方案 §1.2）；全量口径（scope=None）原样返回（R6）。"""
    if scope is None:
        return list(matches)
    return [m for m in matches if esc.in_scope(m.get("book"), scope)]


def fighters_of(matches: list) -> list:
    """对局集 → 出场者（fighters 按过滤后对局重算的单一来源）。"""
    return sorted({p for m in matches for p in (m.get("a"), m.get("b")) if p})


# ---------------------------------------------------------------- Glicko-2（PORT build_ratings.py v0.1）
def glicko2_update(mu, phi, sigma, opponents):
    def g(p):
        return 1.0 / math.sqrt(1 + 3 * Q * Q * p * p / math.pi ** 2)

    def E(mu, mj, pj):
        return 1.0 / (1 + math.exp(-g(pj) * (mu - mj)))

    if not opponents:
        return mu, math.sqrt(phi * phi + sigma * sigma), sigma
    v_inv = sum((g(pj) ** 2) * E(mu, mj, pj) * (1 - E(mu, mj, pj)) for mj, pj, _ in opponents)
    v = 1.0 / v_inv
    delta = v * Q * sum(g(pj) * (s - E(mu, mj, pj)) for mj, pj, s in opponents)
    delta_sq = delta * delta
    a = math.log(sigma * sigma)
    A = a
    if delta_sq > v + phi * phi:
        B = math.log(delta_sq - v - phi * phi)
    else:
        k = 1
        while a - k * TAU < math.log(v + phi * phi) and k < 200:
            k += 1
        B = a - k * TAU

    def f(x):
        num = math.exp(x) * (delta_sq - phi * phi - v - math.exp(x))
        den = 2 * (phi * phi + v + math.exp(x)) ** 2
        return num / den - (x - a) / (TAU * TAU)

    fa, fb = f(A), f(B)
    it = 0
    while abs(A - B) > 1e-6 and it < 100 and not (math.isnan(fa) or math.isnan(fb) or fb == fa):
        C = A + (A - B) * fa / (fb - fa)
        fc = f(C)
        if fc * fb < 0:
            A, fa = B, fb
        else:
            fa = fa / 2
        B, fb = C, fc
        it += 1
    sigma_new = math.exp(A / 2)
    phi_star = math.sqrt(phi * phi + sigma_new * sigma_new)
    phi_prime = 1.0 / math.sqrt(1 / (phi_star * phi_star) + 1 / v)
    sum_term = sum(g(pj) * (s - E(mu, mj, pj)) for mj, pj, s in opponents)
    mu_prime = mu + phi_prime * sum_term
    return mu_prime, phi_prime, sigma_new


def run_glicko(matches: list) -> dict:
    players = {}
    for m in matches:
        for n in (m["a"], m["b"]):
            players.setdefault(n, {"r": R0, "rd": RD0, "sigma": SIGMA, "w": 0, "d": 0, "l": 0})
    order = sorted(matches, key=lambda m: (CHRONO.index(m["book"]) if m["book"] in CHRONO else 9,
                                           int(m["loc"][:3]), int(m["loc"][4:7] or 0)))
    for m in order:
        pa, pb = players[m["a"]], players[m["b"]]
        mu_a, phi_a = (pa["r"] - R0) / SCALE, pa["rd"] / SCALE
        mu_b, phi_b = (pb["r"] - R0) / SCALE, pb["rd"] / SCALE
        s_a = {"win": 1.0, "draw": 0.5, "loss": 0.0}[m["outcome"]]
        s_b = 1.0 - s_a
        # 标准 Glicko-2 同一 rating period：双方均基于对方赛前值更新
        # （2026-11-05 修复：原实现 B 方误用 A 方赛后值，更新量随处理顺序漂移）
        pre_a, pre_b = (mu_a, phi_a), (mu_b, phi_b)
        mu_a, phi_a, sig_a = glicko2_update(mu_a, phi_a, pa["sigma"], [(*pre_b, s_a)])
        mu_b, phi_b, sig_b = glicko2_update(mu_b, phi_b, pb["sigma"], [(*pre_a, s_b)])
        for p, mu, phi, sig in ((pa, mu_a, phi_a, sig_a), (pb, mu_b, phi_b, sig_b)):
            p["r"], p["rd"], p["sigma"] = R0 + SCALE * mu, SCALE * phi, sig
        if s_a > s_b:
            pa["w"] += 1
            pb["l"] += 1
        elif s_a < s_b:
            pa["l"] += 1
            pb["w"] += 1
        else:
            pa["d"] += 1
            pb["d"] += 1
    return players


def quantile(values: list, q: float) -> float:
    if not values:
        return R0
    i = min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))
    return values[i]


def build_ratings(matches: list, books: list | None = None) -> dict:
    """Glicko-2 榜单（W0-T3a：books 参数指定 per_book 覆盖书；缺省 CHRONO，全量口径不变）。

    matches 应已按 scope 过滤（filter_matches）——players/conflicts/per_book 均由
    过滤后对局重算（方案 §1.2）。
    """
    players = run_glicko(matches)
    per_book = defaultdict(dict)
    for book in (books if books is not None else CHRONO):
        bm = [m for m in matches if m["book"] == book]
        if not bm:
            continue
        for n, p in run_glicko(bm).items():
            per_book[n][book] = round(p["r"])
    rows = []
    for n, p in players.items():
        W = p["w"] + p["d"] + p["l"]
        display = (W * p["r"] + P_SHRINK * R0) / (W + P_SHRINK) if W else R0
        rows.append({"name": n, "r": p["r"], "rd": p["rd"], "w": p["w"], "d": p["d"],
                     "l": p["l"], "n": W, "display": display})
    displays = sorted(r["display"] for r in rows)
    thresholds = {name: round(quantile(displays, q)) for name, q in TIER_QUANTILES}

    def tier_of(v):
        if v >= thresholds["绝顶"]:
            return "绝顶"
        if v >= thresholds["超一流"]:
            return "超一流"
        if v >= thresholds["一流"]:
            return "一流"
        if v >= thresholds["二流"]:
            return "二流"
        return "三流"

    disp = {r["name"]: r["display"] for r in rows}
    conflicts = []
    for m in matches:
        if m["outcome"] == "draw" or m["confidence"] != "high" or m["weight"] < 0.8:
            continue
        winner = m["a"] if m["outcome"] == "win" else m["b"]
        loser = m["b"] if m["outcome"] == "win" else m["a"]
        delta = disp.get(loser, R0) - disp.get(winner, R0)
        if delta >= 120:
            conflicts.append({"type": "明文×数据",
                              "claim": "胜词命中（事件层 outcome，句证见定位符）",
                              "claim_loc": f"{m['book']}·{m['loc']}",
                              "data": {"winner": winner, "loser": loser,
                                       "delta": round(delta), "match": m["id"]},
                              "note": "剧情保护候选：可能是主角光环/旁白夸张/抽取误差——冲突≠穿帮；"
                                      "（claim 为口径标签，原文/摘录不发布）"})
    conflicts.sort(key=lambda c: -c["data"]["delta"])
    idx = defaultdict(list)
    for m in matches:
        idx[m["a"]].append(m["id"])
        idx[m["b"]].append(m["id"])
    players_out = []
    per_book_books = books if books is not None else CHRONO
    for r in sorted(rows, key=lambda r: -r["display"]):
        players_out.append({
            "name": r["name"], "rating": round(r["display"]), "rd": round(r["rd"]),
            "tier": tier_of(r["display"]), "matches_n": r["n"],
            "w/d/l": [r["w"], r["d"], r["l"]],
            "per_book": {b: per_book.get(r["name"], {}).get(b) for b in per_book_books
                         if per_book.get(r["name"], {}).get(b) is not None},
            "prior_applied": [],
            "top_evidence": idx.get(r["name"], [])[:3],
        })
    return {"players": players_out, "conflicts": conflicts[:20], "thresholds": thresholds}


# ---------------------------------------------------------------- 落库
def build_matches_payload(matches: list, fighters: list, excluded: dict, evidence_src: dict,
                          stats: dict, scope=None) -> dict:
    """matches.json payload（W0-T3a：scope 口径 meta 加 scope 键；stats=事件层统计）。"""
    ev_total = stats.get("ev_total", 0)
    combat_total = stats.get("combat_total", 0)
    meta = {
        "generated": esc.today(),
        "schema": SCHEMA_MATCHES,
        "wordlist_version": WORDLIST_VERSION,
        "scene_splitter_version": SCENE_SPLITTER,
        "totals": {"matches": len(matches), "fighters": len(fighters),
                   "excluded_narrative": sum(excluded.values())},
        "excluded_detail": excluded,
        "note": "对局=场景内 T01/T02 事件对手对；裁决=旧 build_matches v0.1 胜负词表投影到场景"
                "文本；D03 outcome 五值→win/loss/draw（未决/未知不进榜）；原文/词表命中词不发布（L0）。"
                "本产物为 legacy 中间层（EX-5 matches-v1/glicko2）：正式 live 由工具 E "
                "clean_matches/ratings_whr 覆盖（管线顺序见 scripts/run_pipeline.py，方案 §5.5）。",
        "source": SOURCE,
        "notes": [
            f"输入事件层：{ev_total} 事件（其中 T01/T02 对抗事件 {combat_total} 条）；"
            f"场景切分=同回 PN 距 ≤{SCENE_GAP}",
            "canonical 归并与事件层/registry 同口径；fighters/top_evidence 可回溯事件 loc",
            "与旧站 matches（2026-11-02：484 场/206 人，旧事件表 + ◈◉▲ 三码）口径不同："
            "新数据为 D03 13 类候选层的 T01/T02 子集，数量不可直接相减",
        ],
        "coverage": {"matches": len(matches),
                     "evidence_source": evidence_src,
                     "dedupe": "同回同场景同对手对只出一场；事件层回退按 (书,回,对手对) 去重",
                     "scene_gap_pn": SCENE_GAP},
        "field_gaps": [
            "旧契约 outcome 仅 win/loss/draw：D03『未决/未知』不映射为契约值，"
            "未分胜负或证据不足的对局不入 matches（避免虚增战绩）",
            "旧站 modifiers/weight 词表为 build_matches v0.1；本导出以同词表移植+事件层"
            "condition_tags 合成，词表命中词与摘录按 L0 不发布",
            "围攻 v0 整场一对（与旧口径一致）；连续交锋合并/子事件留 v1",
        ],
    }
    if scope is not None:
        meta["scope"] = scope["profile"]
        meta["field_gaps"].append(
            f"scope 口径（{scope['profile']}）：matches/fighters 仅收 scope 内书目的对局"
            f"（books={'、'.join(scope.get('books', []))}）；fighters 为过滤后对局重算值。")
    return {"meta": meta, "matches": matches, "fighters": fighters}


def build_ratings_payload(ratings: dict, matches: list, scope=None) -> dict:
    """ratings.json payload（W0-T3a：scope 口径 meta 加 scope 键；players/conflicts 已随
    过滤后对局重算——调用方先 filter_matches 再 build_ratings）。"""
    meta = {
        "generated": esc.today(),
        "engine": "glicko2",
        # W2-C1：legacy 中间层声明（EX-5 v1 产物正式 live 由工具 E 覆盖——防部署序列踩踏）
        "note": "本产物为 legacy 中间层（EX-5 matches-v1/glicko2）：正式 live 由工具 E "
                "clean_matches/ratings_whr 覆盖（管线顺序见 scripts/run_pipeline.py，方案 §5.5）。",
        "params": {"r0": R0, "rd0": RD0, "vol": SIGMA, "tau": TAU, "shrink_P": P_SHRINK},
        "wordlist_version": WORDLIST_VERSION,
        "calibration": {"holdout_n": 0, "direction_recall": None,
                        "note": "v0 未做 holdout 抽检；方向来自事件层 outcome 投影，"
                                "人工抽检 100 场待办（与旧站口径一致）"},
        "tiers": ratings["thresholds"],
        "totals": {"players": len(ratings["players"]), "matches": len(matches)},
        "source": SOURCE,
        "notes": [f"宇宙编年顺序：{CHRONO}（旧 4 书顺序 + 冰魄寒光剑追加；N4 未给跨书编年，"
                  f"按旧口径延展）",
                  "rating/rd 为展示分/评分偏差（Glicko-2 + 长尾收缩）；per_book 每书独立 1500 起评",
                  "conflicts 阈值与旧站一致：高置信非平局且败方展示分高出 ≥120"],
        "field_gaps": [
            "旧站 tiers 由旧 matches 分布决定；新 matches 为 D03 T01/T02 子集，分档阈值随之变化"
            "（方法口径不变，数值不可直接对比）",
            "旧站 players=206/conflicts=4（2026-11-02）；新数量见 totals，均为候选级数据",
            "prior_applied 恒空（无先验分修订流程）；direction_recall 未做 holdout",
        ],
    }
    if scope is not None:
        meta["scope"] = scope["profile"]
        meta["field_gaps"].append(
            f"scope 口径（{scope['profile']}）：players/w-d-l/per_book/conflicts 按过滤后对局"
            "（book ∈ scope）重算；分档阈值随 scope 内分布变化。")
    return {"meta": meta, "players": ratings["players"], "conflicts": ratings["conflicts"]}


def write_outputs(books: list | None = None, scope=None) -> int:
    all_books = [b for b in config.book_names() if (EVENTS_DIR / f"{b}.json").exists()]
    events_by_book = {}
    for book in all_books:
        payload = esc.load_json(EVENTS_DIR / f"{book}.json")
        events_by_book[book] = payload.get("events") or []
    books = books or all_books
    # W0-T3a：scope 口径下对局书单先裁剪（build_matches 只遍历 books → matches 天然过滤）
    if scope is not None:
        books = [b for b in books if esc.in_scope(b, scope)]
        missing = [b for b in scope["books"] if b not in all_books]
        if missing:
            print(f"[EX-5] ⚠ scope {scope['profile']} 缺事件层书目：{'、'.join(missing)}")
    matches, fighters, excluded, evidence_src = build_matches(events_by_book, books)
    # 事件层统计（报告口径：scope 口径按 scope 书统计，全量口径不变）
    stat_books = books if scope is not None else all_books
    ev_total = sum(len(events_by_book.get(b) or []) for b in stat_books)
    combat_total = sum(1 for b in stat_books for e in events_by_book.get(b) or []
                       if e.get("type") in COMBAT_TYPES)
    ratings = build_ratings(matches, books=books if scope is not None else None)

    matches_payload = build_matches_payload(matches, fighters, excluded, evidence_src,
                                            {"ev_total": ev_total, "combat_total": combat_total},
                                            scope=scope)
    diff1 = esc.finish("matches.json", matches_payload, exporter=EXPORTER,
                       notes=render_matches_notes(matches_payload, events_by_book))
    ratings_payload = build_ratings_payload(ratings, matches, scope=scope)
    diff2 = esc.finish("ratings.json", ratings_payload, exporter=EXPORTER,
                       notes=render_ratings_notes(ratings_payload, matches_payload))
    print(f"[EX-5] events={ev_total}（combat {combat_total}）→ matches={len(matches)} "
          f"(fighters {len(fighters)}, excluded {excluded}) · players={len(ratings['players'])} "
          f"conflicts={len(ratings['conflicts'])} · tiers={ratings['thresholds']}")
    by_out = Counter(m["outcome"] for m in matches)
    print(f"[EX-5] matches outcome: {dict(by_out)}")
    hard = diff1["hard_gap_count"] + diff2["hard_gap_count"]
    if hard:
        print(f"[EX-5] ✗ 契约硬缺口 {hard}（matches={diff1['hard_gap_count']} "
              f"ratings={diff2['hard_gap_count']}）")
        return 1
    print("[EX-5] ✓ matches/ratings 契约字段不缺、类型不破（dry-run）")
    return 0


def render_matches_notes(payload: dict, events_by_book: dict) -> str:
    meta = payload["meta"]
    by_book = Counter(m["book"] for m in payload["matches"])
    by_out = Counter(m["outcome"] for m in payload["matches"])
    by_kind = Counter(m["kind"] for m in payload["matches"])
    lines = [
        "### 记录数与来源",
        "",
        "| 项 | 值 |",
        "|---|---:|",
        f"| matches | {meta['totals']['matches']} |",
        f"| fighters | {meta['totals']['fighters']} |",
        f"| excluded_narrative | {meta['totals']['excluded_narrative']} |",
        f"| excluded_detail | {meta['excluded_detail']} |",
        f"| outcome | {dict(by_out)} |",
        f"| kind | {dict(by_kind)} |",
        f"| 逐书 | {dict(by_book)} |",
        "",
        "### 口径",
        "",
        "- 输入 = `registry/events/<书>.json`（D03 13 类事件，EX-5 event_extractor）中 T01 比武较技/"
        "T02 生死杀伐、主宾俱全、非对白的事件；场景=同回 PN 距 ≤15 聚合；",
        "- 裁决 = 旧 `build_matches.py` v0.1 胜负词表（强胜1.0/常规0.8/险胜0.6/平0.7）投影到场景"
        "canonical 文本；modifiers 乘子同旧（中毒×0.3/带伤×0.5/偷袭×0.5/诈败→平/放水×0.5/切磋×0.3）；",
        "- D03 outcome 五值 → 契约 win/loss/draw；『未决/未知』不进榜（避免虚增战绩）；",
        f"- D2 覆盖：证据来源 {meta.get('coverage', {}).get('evidence_source')}；"
        "同回同场景同对手对去重；低置信/无参与方事件按 gate 规则排除；",
        "- 不发布原文/词表命中词/摘录（L0 版权口径）；定位符可回溯事件层。",
        "",
        "### 与旧站对照（2026-11-02 matches.json：484 场 / 206 fighters / 1305 excluded）",
        "",
        "- 旧站点为旧 kb 事件表（◈◉▲ 三码 + LLM 校订）产物；新站为 D03 13 类候选层 T01/T02 子集，"
        "两库口径不同，数量不可直接相减；新增冰魄寒光剑（旧站未含）。",
        "",
        "### 复现命令",
        "```",
        "python scripts/export_site_matches_ratings.py        # 默认 dry-run",
        "```",
    ]
    return "\n".join(lines)


def render_ratings_notes(payload: dict, matches_payload: dict) -> str:
    meta = payload["meta"]
    rows = [p for p in payload["players"] if p["matches_n"] > 0]
    lines = [
        "### 记录数与参数",
        "",
        "| 项 | 值 |",
        "|---|---:|",
        f"| players | {meta['totals']['players']} |",
        f"| matches | {meta['totals']['matches']} |",
        f"| conflicts | {len(payload['conflicts'])} |",
        f"| tiers | {meta['tiers']} |",
        f"| params | {meta['params']} |",
        "",
        "### Top 10（有对局者，按展示分）",
        "",
        "| 名次 | 玩家 | tier | rating±rd | 胜/平/负 | matches_n |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for i, p in enumerate(rows[:10], 1):
        w, d, l = p["w/d/l"]
        lines.append(f"| {i} | {p['name']} | {p['tier']} | {p['rating']}±{p['rd']} | "
                     f"{w}/{d}/{l} | {p['matches_n']} |")
    lines += [
        "",
        "### 口径",
        "",
        "- Glicko-2（r0=1500, rd0=350, σ=0.06, τ=0.5）逐场更新；展示分=(W·r+5·1500)/(W+5)；"
        "分档按展示分分位 95/90/70/30 → 绝顶/超一流/一流/二流/三流；",
        "- 宇宙编年 = 白发→塞外→七剑→江湖→冰魄（旧站 4 书顺序 + 冰魄追加；N4 无跨书编年）；",
        "- per_book：每书独立 1500 起评（书内榜）；conflicts：高置信非平局且败方展示分高出 ≥120"
        "（明文×数据倒置候选，非断言，claim 为口径标签、不引原文）；",
        "- 与旧站对照（2026-11-02 ratings.json：206 players / 484 matches / 4 conflicts / "
        "tiers 1576·1549·1517·1493）：新数据来自 D03 T01/T02 子集，分档阈值随分布变化，"
        "数值不可直接对比。",
        "",
        "### 复现命令",
        "```",
        "python scripts/export_site_matches_ratings.py        # 默认 dry-run（同时产 matches/ratings）",
        "```",
    ]
    return "\n".join(lines)


def main() -> int:
    if "--apply" in sys.argv:
        print("[EX-5] 注意：--apply 经 export_site_common 备份后写 site/data；本阶段默认 dry-run。")
    # W0-T3a：--scope <profile> 裁剪口径（W0-T1 基础设施；不带 --scope = 全量口径，向后兼容）
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    books = None
    if "--book" in sys.argv:
        i = sys.argv.index("--book")
        if i + 1 < len(sys.argv):
            books = [sys.argv[i + 1]]
    return write_outputs(books, scope=scope)


if __name__ == "__main__":
    sys.exit(main())
