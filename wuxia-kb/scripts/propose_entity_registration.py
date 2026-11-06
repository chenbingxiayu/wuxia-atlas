# -*- coding: utf-8 -*-
"""S-03b 前置 · 新书实体登记提案构建器（2026-11-05，《七剑下天山》首个使用件）。

从 concordance 聚合管线（复用 build_entity_concordance 的 scan_entity_tokens/aggregate）
取 scope 内（@人物/◆组织/&家族）未登记实体，产出登记提案 JSON：

    registry/patches/<书>_entity_registration.json

  * entities: {type, canonical, aliases[], sources[], status:"proposed", note}
    —— aliases=显示串变体（len≥2，剔除与 canonical 相同/含括注者）；
       sources=出现回号（3 位）；按出现次数降序（人工核准时按重要性排序）；
  * alias_additions: 未登记 canonical 命中既有条目别名者 → 建议并入既有条目的
    aliases（不新建，避免同实体双条）；
  * 不分配最终 id（合并时由 apply 脚本按 max(existing)+1 顺延，防并发冲突）；
  * status="proposed"（status_legend：试点新增待核）——会进映射表消费
    （load_mapping_table 取 status≠pending），与既有 52 条 proposed 同口径。

本脚本只产提案、不改 entities.json；合并用 scripts/apply_entity_registration.py
（--apply 前须确认并发批次已结束，写前备份 + 二次去重断言）。

用法：python scripts/propose_entity_registration.py --book 七剑下天山
"""
import argparse
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config               # noqa: E402
import build_entity_concordance as bc   # noqa: E402

PAREN_RE = re.compile(r"[（(]")


def main():
    ap = argparse.ArgumentParser(description="构建新书实体登记提案（不写 entities.json）")
    ap.add_argument("--book", required=True, help="书名（config.books() 键）")
    args = ap.parse_args()

    meta = config.books()[args.book]
    chapters = list(range(1, meta["chapters"] + 1))
    if config.tagged_path(args.book, 0).exists():
        chapters = [0] + chapters          # 楔子（000）纳入扫描（如存在）
    registry = bc.load_registry()
    occ, _skipped, _examples, _missing, _files = bc.scan_entity_tokens(args.book, chapters)
    entities = bc.aggregate(occ, registry, args.book)

    proposals, alias_adds, skipped = [], [], []
    seen = set()
    for e in entities:
        if e["type"] not in bc.REGISTRY_SCOPE:
            continue
        reg = e["registration"]
        canon = e["canonical"].strip()
        if not canon or PAREN_RE.search(canon):
            skipped.append((canon, "空名/带括注"))
            continue
        if len(canon) == 1:
            skipped.append((canon, "单字不收（歧义过大，映射表同口径）"))
            continue
        if reg["status"] == "registered":
            continue                     # 已在册（含 proposed），不动
        if reg["status"] == "alias_mapped":
            alias_adds.append({
                "target_id": reg["id"],
                "target_canonical": reg["registry_canonical"],
                "type": e["type"],
                "add_alias": canon,
                "occurrences": e["total"],
            })
            continue
        key = (e["type"], canon)
        if key in seen:
            continue
        seen.add(key)
        aliases = []
        for v in e["variants"]:
            d = v["display"].strip()
            if (d == canon or len(d) < 2 or PAREN_RE.search(d) or d in aliases):
                continue
            aliases.append(d)
        sources = [f"{c['chapter']:03d}" for c in e["chapter_counts"]]
        proposals.append({
            "type": e["type"],
            "canonical": canon,
            "aliases": aliases[:12],          # 变体过多只留高频前 12
            "sources": sources,
            "status": "proposed",
            "note": f"出现{e['total']}次/{e['chapter_count']}回；"
                    f"首见 {e['first']['anchor'] if e['first'] else '—'}",
        })

    proposals.sort(key=lambda x: -int(re.match(r"出现(\d+)次", x["note"]).group(1)))
    out = {
        "schema": "entity_registration_proposal/v1",
        "book": args.book,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": f"registry/concordance/{args.book}（scan+aggregate 复算）",
        "scope_types": list(bc.REGISTRY_SCOPE),
        "status_policy": "proposed（试点新增待核；合并后进映射表消费，与既有 proposed 同口径）",
        "counts": {"proposals": len(proposals), "alias_additions": len(alias_adds),
                   "skipped": len(skipped)},
        "entities": proposals,
        "alias_additions": alias_adds,
        "skipped": [{"canonical": c, "reason": r} for c, r in skipped],
    }
    out_dir = config.patches_dir(args.book)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.book}_entity_registration.json"
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n")

    print(f"[ok] 提案 {len(proposals)} 条 / 别名并入 {len(alias_adds)} 条 / 跳过 {len(skipped)}")
    print(f"     → {out_path}")
    by_type = {}
    for p in proposals:
        by_type[p["type"]] = by_type.get(p["type"], 0) + 1
    print(f"     按类型：{by_type}")
    top = [f"{p['canonical']}（{p['note'].split('；')[0]}）" for p in proposals[:8]]
    print("     TOP8: " + "、".join(top))
    if alias_adds:
        sample = "；".join(
            f"{a['add_alias']}→{a['target_canonical']}({a['target_id']})"
            for a in alias_adds[:5])
        print("     别名并入样例：" + sample)


if __name__ == "__main__":
    main()
