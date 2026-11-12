# -*- coding: utf-8 -*-
"""EX-8 · audit.json 导出器（桥接层，docs/51 §三 E 组阶段 3）。

数据源（新管线唯一真源，只读）：
  registry/consistency/<书>.json   N8/D11 `lint_consistency` 产出
                                   （schema wuxia-consistency-v1：5 书 × 39 规则、44 命中；
                                    violations 带 rule_id/severity/grade/locator/quote/rationale/extra）
  tagged/ + registry/（N8 已在 consistency 中引用；本导出不重扫正文，只做字段映射与脱敏）

导出目标：按 site/data 现有 `audit.json` 契约（2026-11-02 基线）
  {meta, totals, r1_ambiguous, r1_passes}
  旧契约字段先读出（logs/export/contracts/audit.json.schema.json），语义映射到 N8：
    - 旧 R1「死亡一致性」→ N8 规则 C4「死亡角色再出场」（本批 5 书 C4 命中 0 → 两可清单为空）；
    - totals.death_events / checked / passes 旧 R1 计数无 N8 对应 → null（不伪造；meta.field_gaps 声明）；
    - totals.ambiguous = 映射后的 C4 候选数（当前 0）；r1_ambiguous 按旧 item schema 映射 C4 命中；
    - 其余 N8 明细（44 violations / 39 规则覆盖 / 豁免 / by_* 统计 / engine）为**新增字段**；
    - 原文引文（violations.quote）按 SKILL_01g §9.10 / SKILL_03d §6.1 发布边界**不出口**，
      只保留 quote_len + 定位符 + 结构化字段 + 原创分析 rationale（截断 ≤300 字）。

严格边界：
  - 只读 registry/consistency 与旧 site/data/audit.json（契约基线）；不写 tagged/registry；
  - 默认 dry-run（staging + 差异报告）；--apply 才由 export_site_common 备份后写 site/data；
  - **不修改 scripts/export_site_all.py**（EX 集成登记由 Lead 统一收口）。

CLI：
  python scripts/export_site_audit.py            # dry-run（默认）
  python scripts/export_site_audit.py --apply    # 写 site/data（common 先备份；本阶段默认不用）
  python scripts/export_site_audit.py --scope tianshan-demo   # 天山 7 书裁剪口径（W0-T3a）

W0-T3a（天山演示版总体方案 §1.2，2026-11-08）scope 口径：
  - consistency docs 按 book ∈ scope 过滤（build_payload 单点生效）：r1（C4 映射）/
    violations/rule_coverage/exemptions/by_* 的 books 维度随之收窄；
  - 全量口径（不带 --scope）行为与现状完全一致（方案 R6）。
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

import config
import export_site_common as esc

CONSISTENCY_DIR = config.DIR_REGISTRY / "consistency"
SITE_AUDIT = config.REPO_ROOT / "site" / "data" / "audit.json"

SCHEMA = "audit-v1"          # 旧 audit-v0 → 新 N8/D11 映射版
EXPORTER = "EX-8 export_site_audit"
SOURCE = "N8/D11 registry/consistency（lint_consistency v0.1，5 书）+ 旧 audit 契约基线"
RATIONALE_MAX = 300          # 原创分析性说明上限（不含原文引文）
TEXT_MAX = 200               # 规则引文/规范引用等结构化文本上限
QUOTE_POLICY = ("01g §9.10 / SKILL_03d §6.1：不发布原文正文、标注正文与可还原正文的连续片段；"
                "violations.quote 一律不出口（仅保留 quote_len + 定位符 + 结构化字段 + 原创分析）")


# ---------------------------------------------------------------- 数据源
def load_consistency() -> list[dict]:
    """发现 registry/consistency 下 5 书 N8 产出（书序按 config.books()）。"""
    order = {b: i for i, b in enumerate(config.book_names())}
    out = []
    for p in sorted(CONSISTENCY_DIR.glob("*.json")):
        try:
            data = esc.load_json(p)
        except (json.JSONDecodeError, OSError):
            continue
        book = data.get("book") or p.stem
        if book != p.stem:       # 只收整书文件（排除分回片段）
            continue
        if data.get("schema") != "wuxia-consistency-v1":
            continue
        out.append(data)
    out.sort(key=lambda d: order.get(d.get("book"), 10 ** 6))
    return out


# ---------------------------------------------------------------- 脱敏
def _clip(text, n: int) -> str:
    text = (text or "").strip() if isinstance(text, str) else ""
    return text if len(text) <= n else text[:n] + "…"


def sanitize_extra(extra: dict | None) -> dict:
    """extra 只保留标量/结构化字段；任何疑似原文的键（quote/text/snippet）丢弃。"""
    out = {}
    for k, v in (extra or {}).items():
        kl = str(k).lower()
        if any(t in kl for t in ("quote", "snippet", "text", "excerpt")):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[str(k)] = _clip(v, TEXT_MAX) if isinstance(v, str) else v
        elif isinstance(v, (list, dict)):
            out[str(k)] = json.loads(json.dumps(v, ensure_ascii=False))  # 结构化小字段原样
    return out


def sanitize_violation(v: dict, book: str) -> dict:
    """violations 记录：去掉原文 quote，保留定位符/规则/等级/原创分析。"""
    quote = v.get("quote") or ""
    return {
        "vid": v.get("vid") or "",
        "book": book,
        "rule_id": v.get("rule_id") or "",
        "rule_title": v.get("rule_title") or "",
        "area": v.get("area") or "",
        "severity": v.get("severity") or "",
        "grade": v.get("grade") or "",
        "confidence": v.get("confidence") or "",
        "locator": v.get("locator") or "",
        "chapter": v.get("chapter"),
        "pn": v.get("pn"),
        "subject": _clip(v.get("subject"), 80),
        "object": _clip(v.get("object"), 80),
        "narrative_mode": v.get("narrative_mode") or "",
        "exempted": bool(v.get("exempted")),
        "exemption": _clip(v.get("exemption"), TEXT_MAX),
        "spec_cite": _clip(v.get("spec_cite"), TEXT_MAX),
        "rationale": _clip(v.get("rationale"), RATIONALE_MAX),
        "extra": sanitize_extra(v.get("extra")),
        "quote_redacted": True,
        "quote_len": len(quote),
    }


# ---------------------------------------------------------------- 旧契约映射（R1 → N8 C4）
def map_c4_to_r1(violations: list[dict]) -> list[dict]:
    """N8 C4「死亡角色再出场」→ 旧 audit r1_ambiguous item schema。

    旧 item：{name, death{book,loc,by}, deaths_n, after_n, live_n, samples[{book,loc,role,v}]}
    C4 本批 0 命中 → 返回 []；映射逻辑保留，N5/N4 补齐致死结构证据后自动生效。
    """
    items = []
    for v in violations:
        if v.get("rule_id") != "C4":
            continue
        extra = v.get("extra") or {}
        samples = []
        for s in extra.get("samples") or []:
            if not isinstance(s, dict):
                continue
            samples.append({"book": s.get("book") or v.get("book") or "",
                            "loc": s.get("loc") or "",
                            "role": s.get("role") or "",
                            "v": s.get("v") or "",
                            **({"in_quote": True} if s.get("in_quote") else {})})
        items.append({
            "name": v.get("subject") or "",
            "death": {"book": v.get("book") or "",
                      "loc": extra.get("death_loc") or v.get("locator") or "",
                      "by": v.get("object") or extra.get("killer") or ""},
            "deaths_n": int(extra.get("deaths_n") or 1),
            "after_n": int(extra.get("after_n") or 0),
            "live_n": int(extra.get("live_n") or len(samples)),
            "samples": samples,
        })
    return items


# ---------------------------------------------------------------- 聚合
def build_rule_coverage(docs: list[dict]) -> list[dict]:
    """39 规则跨书合并：命中数求和、逐书 status/selected 保留、note 去重。"""
    merged = {}
    for doc in docs:
        book = doc.get("book")
        for r in doc.get("rule_coverage") or []:
            rid = r.get("rule_id")
            if not rid:
                continue
            item = merged.setdefault(rid, {
                "rule_id": rid, "area": r.get("area") or "", "title": r.get("title") or "",
                "kind": r.get("kind") or "", "spec_cite": _clip(r.get("spec_cite"), TEXT_MAX),
                "hits": 0, "books": [], "status_by_book": {}, "selected_by_book": {},
                "notes": [],
            })
            item["hits"] += int(r.get("hits") or 0)
            item["books"].append(book)
            item["status_by_book"][book] = r.get("status") or ""
            item["selected_by_book"][book] = bool(r.get("selected", True))
            note = (r.get("note") or "").strip()
            if note and note not in item["notes"]:
                item["notes"].append(_clip(note, TEXT_MAX))
    return [merged[k] for k in sorted(merged)]


def build_payload(docs: list[dict], scope=None) -> dict:
    """N8 consistency docs → audit.json payload。

    W0-T3a（方案 §1.2）：scope 口径下 docs 先按 book ∈ scope 过滤——violations/r1（C4 映射）/
    rule_coverage/exemptions/by_* 的 books 维度随之收窄；全量口径（scope=None）不变。
    """
    if scope is not None:
        docs = [d for d in docs if esc.in_scope(d.get("book"), scope)]
    books = [d.get("book") for d in docs]
    violations = []
    exemptions = []
    by_book = {}
    by_rule = defaultdict(lambda: {"title": "", "area": "", "hits": 0,
                                   "by_severity": Counter(), "by_grade": Counter(),
                                   "books": []})
    by_sev, by_grade, by_area = Counter(), Counter(), Counter()
    for doc in docs:
        book = doc.get("book")
        vs = [sanitize_violation(v, book) for v in doc.get("violations") or []]
        violations.extend(vs)
        for v in vs:
            by_sev[v["severity"]] += 1
            by_grade[v["grade"]] += 1
            by_area[v["area"]] += 1
            r = by_rule[v["rule_id"]]
            r["title"] = v["rule_title"] or r["title"]
            r["area"] = v["area"] or r["area"]
            r["hits"] += 1
            r["by_severity"][v["severity"]] += 1
            r["by_grade"][v["grade"]] += 1
            if book not in r["books"]:
                r["books"].append(book)
        for e in doc.get("exemptions") or []:
            exemptions.append({"book": book, "rule_id": e.get("rule_id") or "",
                               "locator": e.get("locator") or "",
                               "reason": _clip(e.get("reason"), TEXT_MAX),
                               "subject": _clip(e.get("subject"), 80)})
        summary = doc.get("summary") or {}
        inputs = doc.get("inputs") or {}
        by_book[book] = {
            "generated_at": doc.get("generated_at") or "",
            "chapters": inputs.get("chapters"),
            "paragraphs": inputs.get("paragraphs"),
            "violations": len(vs),
            "by_severity": dict(Counter(v["severity"] for v in vs)),
            "by_grade": dict(Counter(v["grade"] for v in vs)),
            "by_rule": dict(Counter(v["rule_id"] for v in vs)),
            "rules_total": summary.get("rules_total"),
            "rules_selected": summary.get("rules_selected"),
            "rules_with_hits": summary.get("rules_with_hits"),
            "exemptions": len(doc.get("exemptions") or []),
        }
    r1_ambiguous = map_c4_to_r1(violations)
    r1_passes: list = []      # N8 不产出 R1 pass 清单（field_gaps 声明）
    totals = {
        "death_events": None,   # 旧 R1 计数无 N8 对应（不伪造）
        "checked": None,
        "ambiguous": len(r1_ambiguous),
        "passes": None,
    }
    rule_coverage = build_rule_coverage(docs)
    # manual/exempt/数据缺口规则挂账（meta.pending_rules）
    by_kind = {}
    for r in rule_coverage:
        by_kind.setdefault(r["kind"], []).append(r["rule_id"])
    manual = by_kind.get("manual", []) + by_kind.get("exempt", [])
    data_gap = [r["rule_id"] for r in rule_coverage
                if r["kind"] not in ("manual", "exempt")
                and r["hits"] == 0
                and "数据缺口" in " ".join(r["status_by_book"].values())]
    c4 = next((r for r in rule_coverage if r["rule_id"] == "C4"), None)
    c4_note = ("；".join(c4["notes"]) if c4 else "") or "本批 0 命中"
    pending_rules = [
        f"C4 死亡角色再出场（旧 audit R1 字段对接规则）：5 书命中 0（{_clip(c4_note, TEXT_MAX)}）"
        f"→ 旧 R1 两可/通过清单为空，totals 旧 R1 计数置 null",
        f"manual/exempt 规则 {len(manual)} 条：{'、'.join(manual)}"
        f"（N8 kind=manual/exempt；其中 J3/J4/W9 本批有手工/半自动命中，详见 by_rule）",
        f"数据缺口规则 {len(data_gap)} 条：{'、'.join(data_gap[:20])}"
        + ("…" if len(data_gap) > 20 else "") + "（自动规则但本批缺数据，见 rule_coverage.status_by_book）",
    ]
    first = docs[0] if docs else {}
    engines = sorted({d.get("tool") or "" for d in docs if d.get("tool")})
    snap = {
        "exported_at": esc.now_iso(),
        "consistency_books": {d.get("book"): {"generated_at": d.get("generated_at"),
                                              "violations": len(d.get("violations") or []),
                                              "rules_with_hits": (d.get("summary") or {}).get("rules_with_hits"),
                                              "chapters": (d.get("inputs") or {}).get("chapters"),
                                              "paragraphs": (d.get("inputs") or {}).get("paragraphs")}
                              for d in docs},
        "engine_tool": engines,
        "schema_in": sorted({d.get("schema") for d in docs}),
        "old_audit": {"generated": (esc.load_site("audit.json") or {}).get("meta", {}).get("generated"),
                      "r1_ambiguous": len((esc.load_site("audit.json") or {}).get("r1_ambiguous") or []),
                      "r1_passes": len((esc.load_site("audit.json") or {}).get("r1_passes") or [])},
    }
    payload = {
        "meta": {
            "generated": esc.today(),
            "schema": SCHEMA,
            "rules": ["C4 死亡角色再出场（旧 audit R1 字段对接规则）",
                      "N8/D11 39 条常识与设定一致性规则（全集与逐书状态见 rule_coverage）"],
            "pending_rules": pending_rules,
            "note": ("N8/D11 lint_consistency 产出按旧 audit.json 契约投影：旧 R1『死亡一致性』"
                     "对应 N8 规则 C4（本批 0 命中 → 两可清单为空）；旧 R1 计数无新来源置 null；"
                     "新增 violations/rule_coverage/by_* 等字段承载 44 条命中与 39 规则覆盖。"
                     "原文引文按 01g §9.10 / 03d §6.1 发布边界不出口（仅定位符+结构化字段+原创分析）。"),
            "source": SOURCE,
            "engine": {
                "tool": engines[0] if engines else "",
                "tools": engines,
                "spec": first.get("spec") or {},
                "schema_in": sorted({d.get("schema") for d in docs}),
                "books": books,
                "generated_at_range": [min((d.get("generated_at") or "") for d in docs),
                                       max((d.get("generated_at") or "") for d in docs)] if docs else [],
            },
            "interfaces": first.get("interfaces") or {},
            "field_gaps": [
                "totals.death_events / totals.checked：旧 audit v0 的『杀事件数/死者检查数』来自旧事件表 R1 引擎；"
                "N8 当前无对应计数（C4 需 N5 杀害边+原文致死结构证据），置 null（非 0，避免误读）",
                "totals.passes / r1_passes：N8 不产出 R1 通过清单（旧 R1 的 5 条验证通过展品无新来源），置 null/[]；"
                "C4 规则状态见 rule_coverage",
                "r1_ambiguous：旧 R1 字段，N8 对应规则=C4（死亡角色再出场）；本批 5 书 C4 命中 0 → 空数组；"
                "若未来 C4 有命中，EX-8 按旧 item schema（name/death/deaths_n/after_n/live_n/samples）自动映射",
                "quote：violations 原文引文按 01g §9.10 / SKILL_03d §6.1 发布边界一律不出口"
                "（只保留 quote_len + 定位符 + 规则 + 原创分析性 rationale，rationale ≤300 字截断）",
                "旧 meta.rules/pending_rules 的 R1/R2/R3 体系已由 N8 39 规则体系取代："
                "R2 武功习得时序→C2、R3 毒理一致性→W8/J7（本批均为数据缺口/0 命中，见 rule_coverage）",
            ],
            "notes": [
                f"N8 5 书合计 violations {len(violations)} 条（48h 快照）："
                f"severity={dict(by_sev)} · grade={dict(by_grade)} · area={dict(by_area)}",
                f"N8 规则覆盖 {len(rule_coverage)} 条：命中规则 {sum(1 for r in rule_coverage if r['hits'])} 条、"
                f"豁免 {len(exemptions)} 次；逐书明细见 by_book",
                "脱敏：violations.quote 已移除（quote_redacted=true / quote_len 保留长度）；"
                "extra 中疑似原文键（quote/snippet/text/excerpt）一并剔除",
                "旧 audit 页面（site/src/pages/audit/index.astro）只读 r1_ambiguous/r1_passes/totals，"
                "本批两可清单为空且不报错；N8 明细在新增字段，待 W 组重建审计页消费",
            ],
            "redaction": {"policy": QUOTE_POLICY, "quote_in_output": False,
                          "rationale_max_chars": RATIONALE_MAX, "text_max_chars": TEXT_MAX},
            "snapshot": snap,
        },
        "totals": totals,
        "r1_ambiguous": r1_ambiguous,
        "r1_passes": r1_passes,
        # ---- 新增字段（N8 明细；契约外，供 W 组/审计页重建） ----
        "violations": violations,
        "rule_coverage": rule_coverage,
        "exemptions": exemptions,
        "by_severity": dict(by_sev),
        "by_grade": dict(by_grade),
        "by_area": dict(by_area),
        "by_rule": {k: {"title": v["title"], "area": v["area"], "hits": v["hits"],
                        "by_severity": dict(v["by_severity"]), "by_grade": dict(v["by_grade"]),
                        "books": v["books"]}
                    for k, v in sorted(by_rule.items())},
        "by_book": by_book,
    }
    if scope is not None:
        payload["meta"]["scope"] = scope["profile"]
        payload["meta"]["field_gaps"].append(
            f"scope 口径（{scope['profile']}）：consistency docs 按 book ∈ scope 过滤——"
            "violations/r1（C4 映射）/rule_coverage/exemptions/by_* 的 books 维度随之收窄；"
            f"本批收 {len(docs)} 书（{'、'.join(books)}）。")
    return payload


# ---------------------------------------------------------------- 报告
def render_notes(payload: dict) -> str:
    meta = payload["meta"]
    by_book = payload["by_book"]
    by_rule = payload["by_rule"]
    old = meta["snapshot"].get("old_audit") or {}
    lines = [
        "### 记录数（旧 audit vs N8 新产出）",
        "",
        f"| 项 | 旧站 audit.json（generated={old.get('generated') or '2026-11-02'}） | 新产出（EX-8 / N8） |",
        "|---|---:|---:|",
        f"| R1 两可清单 | {old.get('r1_ambiguous')} | {len(payload['r1_ambiguous'])}（= N8 C4 命中映射） |",
        f"| R1 通过展品 | {old.get('r1_passes')} | {len(payload['r1_passes'])}（N8 无 pass 清单） |",
        f"| violations 明细 | —（旧引擎无此结构） | {len(payload['violations'])}（新增字段） |",
        f"| rule_coverage 规则 | 1（R1） | {len(payload['rule_coverage'])}（N8/D11 39 规则） |",
        f"| exemptions 豁免 | — | {len(payload['exemptions'])} |",
        f"| totals | death_events/checked/ambiguous/passes（旧 R1） "
        f"| {payload['totals']}（旧 R1 计数置 null，ambiguous=C4 映射数） |",
        "",
        "### 旧 audit 契约字段 → N8 映射表",
        "",
        "| 旧字段 | 新来源 | 状态 |",
        "|---|---|---|",
        "| meta.rules | N8 rules 索引（C4 + 39 规则全集） | ✅ 映射 |",
        "| meta.pending_rules | N8 C4 数据缺口 + manual/exempt/数据缺口规则挂账 | ✅ 映射（语义扩展） |",
        "| meta.note / meta.schema | 重写为 N8/D11 audit-v1 口径 | ✅ 映射 |",
        "| totals.death_events / totals.checked | 无 N8 对应 | ⚠️ null（field_gaps 声明） |",
        "| totals.ambiguous | N8 C4 命中映射数 | ✅ 0（C4 本批 0 命中） |",
        "| totals.passes | N8 无 pass 清单 | ⚠️ null（field_gaps 声明） |",
        "| r1_ambiguous[] | N8 C4 violations → 旧 item schema | ✅ 映射逻辑就绪，本批 [] |",
        "| r1_passes[] | N8 无对应 | ⚠️ []（field_gaps 声明） |",
        "| （新增）violations / rule_coverage / by_* / books / exemptions / engine / redaction "
        "| N8 全量明细 | ✅ 新增字段（契约外，供 W 组审计页重建） |",
        "",
        "### 5 书逐书统计",
        "",
        "| 书 | 回 | 段 | violations | warning | info | B | C | 有命中规则 | 豁免 | N8 生成 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for book, b in by_book.items():
        sev = b.get("by_severity") or {}
        grade = b.get("by_grade") or {}
        lines.append(
            f"| {book} | {b.get('chapters') or '—'} | {b.get('paragraphs') or '—'} | {b.get('violations')} | "
            f"{sev.get('warning', 0)} | {sev.get('info', 0)} | {grade.get('B', 0)} | {grade.get('C', 0)} | "
            f"{b.get('rules_with_hits') or 0} | {b.get('exemptions') or 0} | {_clip(b.get('generated_at'), 20)} |")
    lines += [
        "",
        f"- 合计：{len(payload['violations'])} 条命中 / {sum(1 for r in payload['rule_coverage'] if r['hits'])} 条规则有命中 / "
        f"severity={payload['by_severity']} · grade={payload['by_grade']}",
        "",
        "### 规则命中分布（by_rule）",
        "",
        "| 规则 | 标题 | 领域 | 命中 | 书 | severity | grade |",
        "|---|---|---|---:|---|---|---|",
    ]
    for rid, r in by_rule.items():
        lines.append(f"| {rid} | {r['title']} | {r['area']} | {r['hits']} | "
                     f"{'、'.join(r['books'])} | {r['by_severity']} | {r['by_grade']} |")
    lines += [
        "",
        "### 规则覆盖（rule_coverage 摘要）",
        "",
        f"- 39 规则：命中 {sum(1 for r in payload['rule_coverage'] if r['hits'])} 条 / 0 命中 "
        f"{sum(1 for r in payload['rule_coverage'] if not r['hits'])} 条；kind 分布 "
        f"{dict(Counter(r['kind'] for r in payload['rule_coverage']))}",
        f"- manual/exempt 规则（不自动产出）：{[r['rule_id'] for r in payload['rule_coverage'] if r['kind'] in ('manual', 'exempt')]}",
        "- 逐书 status/selected/note 见 `audit.json.rule_coverage[*].status_by_book`；"
        "数据缺口原因逐条保留（非静默丢弃）。",
        "",
        "### 发布边界（脱敏）",
        "",
        f"- {QUOTE_POLICY}",
        f"- 输出中不存在 `violations[].quote` 原文；仅 `quote_redacted=true` / `quote_len` 与定位符、"
        f"结构化字段、原创分析 `rationale`（≤{RATIONALE_MAX} 字）。",
        "",
        "### 复现命令",
        "```",
        "python scripts/export_site_audit.py        # dry-run（默认，只写 staging/reports）",
        "```",
        "### 遗留",
        "- 旧 R1 引擎（旧 kb 事件表）未重实现：N8 C4 需 N5 杀害边 + 原文致死结构证据，本批 0 命中，"
        "故 r1_ambiguous/r1_passes 为空、totals 旧 R1 计数 null；补齐上游后 EX-8 自动映射（无需改契约）。",
        "- N8 39 规则中多数为 manual/exempt/数据缺口（见 rule_coverage），44 条命中均为候选级"
        "（warning 28 / info 16；C 28 / B 16），非最终断言。",
        "- 旧 audit 页面仍按 R1 语义渲染（两可清单空、统计 blank 不报错）；N8 明细待 W 组审计页重建消费。",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- 主流程
def main() -> int:
    if "--apply" in sys.argv:
        print("[EX-8] 注意：--apply 经 export_site_common 备份后写 site/data；阶段 3 默认先 dry-run。")
    # W0-T3a：--scope <profile> 裁剪口径（W0-T1 基础设施；不带 --scope = 全量口径，向后兼容）
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    docs = load_consistency()
    if scope is not None:
        docs = [d for d in docs if esc.in_scope(d.get("book"), scope)]
    if not docs:
        print(f"[EX-8] 未发现 N8 consistency 产出"
              f"{'（scope 口径下无书目）' if scope is not None else ''}：{CONSISTENCY_DIR}")
        return 2
    payload = build_payload(docs, scope=scope)
    notes = render_notes(payload)
    diff = esc.finish("audit.json", payload, exporter=EXPORTER, notes=notes)
    print(f"[EX-8] 书 {len(docs)} 本 · violations {len(payload['violations'])} · "
          f"规则覆盖 {len(payload['rule_coverage'])} · r1_ambiguous {len(payload['r1_ambiguous'])} / "
          f"r1_passes {len(payload['r1_passes'])} · totals {payload['totals']}")
    hard = diff["hard_gap_count"]
    if hard:
        print(f"[EX-8] ✗ 契约硬缺口 {hard}，见 reports/audit_report.md")
        return 1
    print("[EX-8] ✓ 契约字段不缺、类型不破（旧 R1 无来源字段 null/[] 已声明）；dry-run 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
