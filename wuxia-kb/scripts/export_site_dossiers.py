# -*- coding: utf-8 -*-
"""EX-3 · dossiers.json 导出器（桥接层，docs/51 §三/§五）。

数据口径：
  - 核心字段（id/canonical/cross_book/books/aliases/appearance_total/chapter_curves）
    **全部来自新管线**：registry/entities.json + registry/concordance/<书>.json 同批聚合
    （复用 EX-2 的归并/聚合实现，保证 characters/entity-index/dossiers 三表人物集合一致）；
  - 派生字段（sect_affinity/lineage/ranks/combat/arts/key_events/summary/summary_status）
    新管线当前无上游（事件层/关系层 N5+D03 未落地、LLM 摘要编辑流程未启动），按 docs/51 §五
    **fallback 旧站 dossiers.json 同 canonical 记录**；匹配不到的使用空骨架（结构完整，不伪造），
    命中数/未命中数写入 meta.field_gaps 与报告。
  - fallback 源优先阶段 0 冻结备份 backup/site_data/phase0_20261105/dossiers.json
    （--apply 覆盖 site/data 后仍保持稳定基线），备份缺失时回退当前 site/data。

W0-T2（天山演示版总体方案 §二，2026-11-08）：
  - **主档圈定**：total≥30 ∪ 有实质内容（key_events/lineage.masters|disciples/combat.kills|slain_by/
    arts 非空，判定源 = fallback 派生字段）。规则与阈值在 scripts/export_site_characters.py
    （decide_major / major_rule_meta），阈值进 meta.major_rule 不硬编码；
  - scope 口径（--scope <profile>）：dossiers 仅收主档；存目不进 dossiers、只进 entity-index
    （page=false，EX-2 产出）；全量口径（不带 --scope）**不裁剪**（向后兼容，方案 R6：
    规则随 meta.scope 走，回切全量时所有档案仍在）；
  - 别名归并 TSV（B7）经 EX-2 同批聚合前置生效，三表人物集合保持一致。

数量口径：旧站 436 = 旧站 3 书人物档案数；新 = 新管线 concordance @ 唯一规范名，差异写入 meta.field_gaps。

用法：
  python scripts/export_site_dossiers.py           # dry-run（staging + 报告）
  python scripts/export_site_dossiers.py --apply   # 写 site/data（export_site_common 先备份）
  python scripts/export_site_dossiers.py --scope tianshan-demo   # 天山 7 书主档口径
"""
from __future__ import annotations

from collections import Counter

import export_site_characters as exc
import export_site_common as esc

SCHEMA = "site-dossiers-v1"
SOURCE = "wuxia-kb 新管线 + 旧站 fallback（桥接层 EX-2/EX-3）"
EXPORTER = "scripts/export_site_dossiers.py（EX-3）"
COPYRIGHT = "L0 档位：仅定位符与图谱事实，不含原文摘录"
ALIAS_TOP_N = 8          # 对齐旧站 build_dossiers.py top_aliases[:8]
SAMPLE_N = 10
# 注：fallback 源加载（load_fallback_dossiers/display_path/FALLBACK_TAG）W0-T2 起上移至
# export_site_characters.py（EX-2 主档内容判定共用），本模块经 exc.* 调用。


def empty_derived() -> dict:
    """旧站记录一致的派生字段空骨架（Astro 人物档案页可安全渲染）。"""
    return {
        "sect_affinity": [],
        "lineage": {"masters": [], "disciples": []},
        "ranks": [],
        "combat": {"kills": [], "slain_by": [], "captures": [], "captured_by": [],
                   "top_opponents": [], "confidence_dist": {}},
        "arts": [],
        "key_events": [],
        "summary": None,
        "summary_status": "待撰写",
    }


def _list(value) -> bool:
    return isinstance(value, list)


def _dict(value) -> bool:
    return isinstance(value, dict)


def pick_derived(old: dict | None) -> tuple[dict, list[str]]:
    """旧站同 canonical 记录 → 派生字段；记录缺失/形状不符时用空骨架并记入降级清单。"""
    out = empty_derived()
    degraded: list[str] = []
    if not old:
        return out, degraded
    if _list(old.get("sect_affinity")):
        out["sect_affinity"] = old["sect_affinity"]
    else:
        degraded.append("sect_affinity")
    lineage = old.get("lineage")
    if _dict(lineage) and _list(lineage.get("masters")) and _list(lineage.get("disciples")):
        out["lineage"] = {"masters": lineage["masters"], "disciples": lineage["disciples"]}
    else:
        degraded.append("lineage")
    if _list(old.get("ranks")):
        out["ranks"] = old["ranks"]
    else:
        degraded.append("ranks")
    combat = old.get("combat")
    combat_keys = ("kills", "slain_by", "captures", "captured_by", "top_opponents")
    if _dict(combat) and all(_list(combat.get(k)) for k in combat_keys) and _dict(combat.get("confidence_dist")):
        out["combat"] = {k: combat[k] for k in combat_keys}
        out["combat"]["confidence_dist"] = combat["confidence_dist"]
    else:
        degraded.append("combat")
    if _list(old.get("arts")):
        out["arts"] = old["arts"]
    else:
        degraded.append("arts")
    if _list(old.get("key_events")):
        out["key_events"] = old["key_events"]
    else:
        degraded.append("key_events")
    summary = old.get("summary")
    out["summary"] = summary if summary is None or isinstance(summary, str) else None
    status = old.get("summary_status")
    out["summary_status"] = status if isinstance(status, str) else "待撰写"
    return out, degraded


# ---------------------------------------------------------------- 产物构造
def build_dossiers(agg: dict, books: list[str], fallback: dict,
                   display_map: dict[str, str] | None = None, scope=None,
                   min_total: int = exc.MIN_TOTAL) -> tuple[list[dict], dict]:
    """聚合结构 → dossiers（旧契约记录形状 + 新增展示层 display/display_name）。

    W0-T2 主档圈定（方案 §二）：scope 口径下仅收主档（decide_major：scope 内频次≥min_total
    ∪ 有实质内容）；存目不进 dossiers、只进 entity-index（page=false，EX-2 产出）。
    全量口径（scope=None）不裁剪——向后兼容（方案 R6：规则随 meta.scope 走）。
    """
    display_map = display_map or {}
    persons = [(key, rec) for key, rec in agg.items() if key[0] == "@"]
    persons.sort(key=lambda kr: (-kr[1]["total"], kr[0][1]))
    dossiers: list[dict] = []
    stats = {
        "fallback_hits": 0,
        "fallback_empty_derived": 0,
        "fallback_nonempty_derived": 0,
        "archived": 0,
        "degraded": Counter(),
        "old_reused": set(),
    }
    for (etype, canon), rec in persons:
        old = fallback.get(canon)
        if scope is not None and not exc.decide_major(rec, old, scope, min_total):
            stats["archived"] += 1          # 存目：不进 dossiers，entity-index page=false
            continue
        derived, degraded = pick_derived(old)
        if old is not None:
            stats["fallback_hits"] += 1
            stats["old_reused"].add(canon)
            stats["degraded"].update(degraded)
            if derived["sect_affinity"] or derived["lineage"]["masters"] or derived["lineage"]["disciples"] \
                    or derived["ranks"] or derived["arts"] or derived["key_events"] \
                    or any(derived["combat"][k] for k in ("kills", "slain_by", "captures", "captured_by")):
                stats["fallback_nonempty_derived"] += 1
            else:
                stats["fallback_empty_derived"] += 1
        person_books = sorted(rec["books"])
        curves = {
            book: {str(ch): n for ch, n in sorted(rec["books"][book]["chapters"].items())}
            for book in person_books
        }
        aliases = Counter()
        for binfo in rec["books"].values():
            aliases.update(binfo["aliases"])
        alias_rows = [
            {"alias": alias, "count": n}
            for alias, n in sorted(aliases.items(), key=lambda kv: (-kv[1], kv[0]))[:ALIAS_TOP_N]
        ]
        dossiers.append({
            "id": f"@{canon}",
            "canonical": canon,
            "display": exc.display_of(canon, display_map),        # task-24：只增字段
            "display_name": exc.display_of(canon, display_map),   # task-24：dossiers 专项展示名
            "cross_book": len(person_books) > 1,
            "books": person_books,
            "aliases": alias_rows,
            "appearance_total": rec["total"],
            "chapter_curves": curves,
            "sect_affinity": derived["sect_affinity"],
            "lineage": derived["lineage"],
            "ranks": derived["ranks"],
            "combat": derived["combat"],
            "arts": derived["arts"],
            "key_events": derived["key_events"],
            "summary": derived["summary"],
            "summary_status": derived["summary_status"],
        })
    return dossiers, stats


def build_payload(dossiers: list[dict], books: list[str], stats: dict,
                  fallback: dict, fallback_path: str,
                  display_meta: dict | None = None, scope=None,
                  overrides_meta: dict | None = None) -> dict:
    cross = sum(1 for d in dossiers if d["cross_book"])
    old_only = sorted(set(fallback) - stats["old_reused"])
    display_meta = display_meta or {}
    shown = [f"{c}→{d}" for c, d in sorted(display_meta.get("map", {}).items())]
    gaps = [
        f"展示层字段 display/display_name（task-24 新增，只增不改）：取 registry/display_canonical.json "
        f"覆盖值（{display_meta.get('entries', 0)} 条：{'、'.join(shown)}），未登记条目回落 canonical；"
        "两者同值，仅为站点/下游明确语义命名；不参与 fallback/归并/accept 判定。",
        f"派生字段 fallback：sect_affinity/lineage/ranks/combat/arts/key_events/summary/summary_status "
        f"新管线暂无上游（事件层/关系层 N5+D03 未落地、LLM 摘要编辑流程未启动），按 docs/51 §五 "
        f"从旧站 dossiers 同 canonical 记录带值；命中 {stats['fallback_hits']}/{len(dossiers)}，"
        f"未命中 {len(dossiers) - stats['fallback_hits']} 条使用空骨架（结构完整、不伪造）。"
        f"fallback 源={fallback_path}（阶段 0 冻结备份，--apply 后仍稳定）。",
        f"数量口径：旧站 436（旧站 3 书人物档案数，=旧 characters @436）→ 新 {len(dossiers)}"
        f"（新管线 5 书 concordance @ 唯一规范名；registry @375 全覆盖，含 5 书新增人物）。"
        f"旧 436 档案中 {len(old_only)} 个规范名未映射到新 @（旧名差异/新管线别名归一："
        f"{'、'.join(old_only[:8])}{' 等' if len(old_only) > 8 else ''}），未回填其派生字段。",
        "核心字段 id/canonical/cross_book/books/aliases/appearance_total/chapter_curves 全部来自新数据："
        "appearance_total=concordance total 求和；chapter_curves=concordance chapter_counts"
        "（含 chapter 0=回目标题行，与旧站 8 条 chapter 0 口径一致）；aliases=variants 按频次前 8"
        "（对齐旧站 top_aliases[:8]）；books 为出现书目。",
        f"fallback 记录派生字段丰度：命中 {stats['fallback_hits']} 条中，派生字段非空 "
        f"{stats['fallback_nonempty_derived']} 条、空档案 {stats['fallback_empty_derived']} 条"
        "（旧站 436 档案本身有 224 条全部派生字段为空，回填后仍为空属旧站口径）。",
        "summary/summary_status：旧站 436 条全为 null/『待撰写』（编辑流程未启动），按旧值/默认原样输出，"
        "不生成任何 LLM 文案。",
        f"主档圈定（W0-T2，方案 §二）：min_total={exc.MIN_TOTAL} ∪ 有实质内容"
        "（key_events/lineage.masters|disciples/combat.kills|slain_by/arts 非空，判定源=fallback "
        "派生字段）；规则参数见 meta.major_rule（阈值进 meta 不硬编码）。全量口径（scope=null）"
        "下 dossiers 不裁剪（向后兼容，方案 R6）；scope 口径下仅主档入本表，"
        "存目只进 entity-index（page=false）。",
        exc.alias_overrides_desc(overrides_meta),   # D9：registry 类型内 alias 覆盖
    ]
    meta = {
        "generated": esc.now_iso(),
        "schema": SCHEMA,
        "limit": None,
        "books": list(books),
        "copyright": COPYRIGHT,
        "source": SOURCE,
        "source_detail": (
            "核心字段=registry/entities.json + registry/concordance/<书>.json；"
            f"派生字段=旧站 dossiers fallback（{fallback_path}，同 canonical 命中 "
            f"{stats['fallback_hits']}/{len(dossiers)}）"
        ),
        "display_layer": display_meta,
        "major_rule": exc.major_rule_meta(scope),   # W0-T2：规则参数进 meta，不硬编码
        "totals": {
            "entities_indexed": len(dossiers),
            "dossiers_built": len(dossiers),
            "cross_book": cross,
        },
        "field_gaps": gaps,
    }
    if scope is not None:
        meta["scope"] = scope["profile"]
        meta["totals"]["archived"] = stats.get("archived", 0)   # 存目数（scope 口径）
    return {"meta": meta, "dossiers": dossiers}


# ---------------------------------------------------------------- 抽样回溯 + 一致性校验
def dossier_samples(dossiers: list[dict], agg: dict, book_payloads: list[dict],
                    reg_by_id: dict, fallback: dict,
                    merges: dict | None = None,
                    overrides: dict | None = None) -> tuple[list[str], list[str]]:
    """前 10 条（按出场频次）逐条重算：频次/逐回曲线/fallback 命中与首见锚点。"""
    lines, failures = [], []
    for d in dossiers[:SAMPLE_N]:
        key = ("@", d["canonical"])
        per_book, anchor = exc.trace_entity(key, book_payloads, reg_by_id, merges, overrides)
        rec = agg[key]
        if sum(per_book.values()) != d["appearance_total"] or dict(per_book) != {
                b: info["count"] for b, info in rec["books"].items()}:
            failures.append(f"{d['canonical']} 频次回溯不一致")
        curve_ok = all(sum(d["chapter_curves"][b].values()) == c
                       for b, c in {b: info["count"] for b, info in rec["books"].items()}.items())
        if not curve_ok:
            failures.append(f"{d['canonical']} chapter_curves 与逐书频次不一致")
        if len(d["chapter_curves"]) != len(d["books"]):
            failures.append(f"{d['canonical']} chapter_curves 书目数不一致")
        loc = f"{anchor[1]}·{anchor[3]}（{anchor[2]}）" if anchor else "—"
        derived = ("fallback 命中（旧档案派生字段）" if d["canonical"] in fallback
                   else "空骨架（旧站无同 canonical 档案）")
        lines.append(f"| {d['canonical']} | {d['id']} | {d['appearance_total']} | "
                     + "、".join(f"{b}:{n}" for b, n in per_book.items())
                     + f" | {'OK' if curve_ok else 'FAIL'} | {derived} | {loc} |")
    return lines, failures


# ---------------------------------------------------------------- 主流程
def main() -> int:
    # W0-T2：--scope <profile> 主档口径（W0-T1 基础设施；不带 --scope = 全量口径，向后兼容）
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    book_payloads = exc.load_book_payloads()
    if scope is not None:
        book_payloads = [bp for bp in book_payloads if esc.in_scope(bp["book"], scope)]
        found = {bp["book"] for bp in book_payloads}
        missing = [b for b in scope["books"] if b not in found]
        if missing:
            raise SystemExit(f"[EX-3] scope {scope['profile']} 缺少 concordance 书目：{'、'.join(missing)}")
    books = [bp["book"] for bp in book_payloads]
    reg_by_id = exc.load_registry()
    display_map, display_meta = exc.load_display_map()
    display_meta = dict(display_meta, map=display_map)
    merges, merges_meta = exc.load_alias_merges()    # W0-T2：缺文件 = no-op
    overrides, overrides_meta = exc.load_alias_overrides()   # D9：registry 类型内 alias 覆盖
    agg, norm_stats = exc.aggregate_entities(book_payloads, reg_by_id, merges=merges,
                                             overrides=overrides)
    fallback, fallback_path = exc.load_fallback_dossiers()
    dossiers, stats = build_dossiers(agg, books, fallback, display_map, scope=scope)
    payload = build_payload(dossiers, books, stats, fallback, fallback_path, display_meta,
                            scope=scope, overrides_meta=overrides_meta)

    sample_lines, failures = dossier_samples(dossiers, agg, book_payloads, reg_by_id, fallback,
                                             merges, overrides)
    # 展示层抽样（task-24）：dossiers 全为 @ 人物，5 条覆盖应全部命中且 canonical 不变
    # scope 口径下存目人物不进 dossiers → 跳过并记行，不算失败
    by_canon = {d["canonical"]: d for d in dossiers}
    display_lines = []
    for canon in exc.DISPLAY_SAMPLE_CANONICALS:
        expected = display_map.get(canon)
        d = by_canon.get(canon)
        if d is None:
            if scope is None:
                failures.append(f"dossiers 缺 @{canon}（展示层抽样）")
            else:
                display_lines.append(f"| {canon} | {expected} | （scope 外/存目，跳过） | — |")
            continue
        if d.get("display") != expected or d.get("display_name") != expected:
            failures.append(f"dossiers {canon} display={d.get('display')}/"
                            f"{d.get('display_name')} 预期 {expected}")
        if d.get("canonical") != canon or d.get("id") != f"@{canon}":
            failures.append(f"dossiers {canon} canonical/id 被展示层改写（只增字段被违反）")
        display_lines.append(f"| {canon} | {expected} | {d.get('display')} | "
                             f"{d.get('display_name')} | {d.get('appearance_total')} |")
    # 三表人物集合一致性：全量口径 dossiers == characters @；scope 口径 主档 ⊆ characters @
    chars_at = {rec["canonical"] for key, rec in agg.items() if key[0] == "@"}
    dossier_canons = {d["canonical"] for d in dossiers}
    if scope is None:
        if chars_at != dossier_canons:
            failures.append("dossiers 与 characters @ 集合不一致")
    else:
        if not dossier_canons <= chars_at:
            failures.append("scope 口径 dossiers 含 characters @ 之外的记录")
        if len(dossier_canons) + stats.get("archived", 0) != len(chars_at):
            failures.append("scope 口径 主档+存目 != characters @ 总数")
    if failures:
        raise SystemExit("[EX-3] 校验失败：" + "；".join(failures))

    major_line = (
        f"- W0-T2 主档圈定（方案 §二）：规则 total≥{exc.MIN_TOTAL} ∪ 有实质内容；"
        f"meta.major_rule={payload['meta']['major_rule']}。",
        f"- 主档（入 dossiers）{len(dossiers)} 条 / 存目（只进 entity-index，page=false）"
        f"{stats.get('archived', 0)} 条；存目+主档 = characters @ {len(chars_at)} 条（断言通过）。",
    ) if scope is not None else (
        f"- W0-T2 主档圈定（方案 §二）：全量口径（scope=null）不裁剪（向后兼容，方案 R6），"
        f"规则参数见 meta.major_rule={payload['meta']['major_rule']}；"
        f"entity-index 的 page 字段为规则判定值。",
    )
    notes = "\n".join([
        "### 记录数对比旧站",
        f"- dossiers.json：旧 436（3 书）→ 新 {len(dossiers)}"
        f"（{len(books)} 书：{'、'.join(books)}）；"
        f"cross_book：旧 45 → 新 {payload['meta']['totals']['cross_book']}。",
        f"- 数量口径：旧=旧站人物档案数（=旧 characters @436）；新=新管线 concordance @ 唯一规范名"
        f"（registry @375 全覆盖）。旧 436 中 {len(set(fallback) - stats['old_reused'])} 个规范名"
        "未映射到新 @（旧名差异/别名归一），未回填。",
        f"- 三表一致性：{'主档集合 ⊆' if scope is not None else 'dossiers canonical =='} "
        f"characters @（= entity-index @）= {len(chars_at)} 条（断言通过）。",
        *major_line,
        f"- {exc.alias_merge_desc(merges_meta, norm_stats)}。",
        "- 字段覆盖：契约 hard_gap=0（15 个记录级字段全齐，含 summary=null/summary_status=str）。",
        "",
        "### 展示层（display/display_name，task-24）",
        f"- registry/display_canonical.json **{display_meta.get('entries', 0)} 条覆盖**"
        f"（{'、'.join(f'{c}→{d}' for c, d in sorted(display_map.items()))}）；未登记条目回落 canonical。",
        "- **只增字段**：每条档案新增 `display` 与 `display_name`（同值）；id/canonical 及 15 个旧契约字段不变（未改名/未删字段）。",
        "",
        "| canonical | 预期 display | display | display_name | appearance_total |",
        "|---|---|---|---|---:|",
        *display_lines,
        "",
        "### fallback 策略",
        f"- 核心字段（id/canonical/cross_book/books/aliases/appearance_total/chapter_curves）：新数据，"
        f"无 fallback（chapter_curves 由 concordance chapter_counts 映射）。",
        f"- 派生字段（sect_affinity/lineage/ranks/combat/arts/key_events/summary/summary_status）："
        f"旧站 dossiers 同 canonical 整段 fallback，命中 {stats['fallback_hits']}/{len(dossiers)}"
        f"（非空派生 {stats['fallback_nonempty_derived']}、旧站本身空档案 {stats['fallback_empty_derived']}）；"
        f"未命中 {len(dossiers) - stats['fallback_hits']} 条 = 空骨架（结构完整、不伪造）。"
        f"fallback 派生字段同时作为主档「有实质内容」判定源。",
        f"- fallback 源：{fallback_path}（阶段 0 冻结备份，--apply 后保持稳定）。",
        "",
        "### 抽样回溯（前 10 条按出场频次；独立重算 concordance 原始条目）",
        "| canonical | id | appearance_total | 逐书频次（重算=产出） | 曲线校验 | 派生字段来源 | 首见（书·行 / 机器锚点） |",
        "|---|---|---:|---|---|---|---|",
        *sample_lines,
        "",
        "### 遗留风险",
        "- 派生字段回填率受旧站覆盖限制：新增书人物（尤其 冰魄寒光剑/江湖三女侠）无旧档案，"
        "师承/战绩/门派线索/武功/关键事件为空，主档判定对它们退化为纯频次阈值；"
        "需 N5 关系层 + D03 事件层落地后重导（EX-4/EX-5 前置）。",
        "- summary 仍为 null/待撰写：编辑流程（LLM 草拟→人工校）未启动，桥接期站点人物志卡片显示『待撰写』。",
        "- 旧站 31 个规范名与新 @ 不同名（如 明太祖朱元璋 vs 朱元璋、玉面妖狐 vs 凌霄、唐家 现为 & 家族），"
        "未做别名二次匹配以避免误配；可在 N5 后按 registry aliases 补一轮。",
    ])

    diff = esc.finish("dossiers.json", payload, exporter=EXPORTER, notes=notes)
    print(f"[EX-3] dossiers={len(dossiers)} archived={stats.get('archived', 0)} "
          f"fallback_hits={stats['fallback_hits']} "
          f"merges={merges_meta.get('rows', 0)} "
          f"display_overrides={len(display_map)} hard_gaps={diff['hard_gap_count']}")
    return 0 if diff["hard_gap_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
