# -*- coding: utf-8 -*-
"""build_relations.py —— 人物关系轨切片（W0-T3b 常设化，接替 spec 003 一次性 build_tracks.py T2）。

读 kb/校订/人物关系考订.tsv（status=校定）→ site/data/char_relations.json。
产出与 spec 003 一次性脚本逐字段一致（a/b/type/tier/book/loc/note；schema char-relations-v1）；
W0-T3b（天山演示版总体方案 §1.2，2026-11-08）新增 --scope：
  - --scope <profile>：TSV 行 book ∈ scope 才保留（book 缺失=不可归书，scope 下裁）；
  - 不带 --scope：全量口径，行为与现状一致（meta 无 scope 键，方案 R6）；
  - meta 加 {"scope": profile, "books": […]}（export_site_common.scope_meta，前端 ScopeNote 消费）。

用法：python scripts/build_relations.py [--scope tianshan-demo]
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TSV = ROOT / "kb" / "校订" / "人物关系考订.tsv"
OUT = ROOT / "site" / "data" / "char_relations.json"

# W0-T3b：scope 基础设施复用（export_site_common 在 wuxia-kb/scripts，import 胜过复制）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / "wuxia-kb" / "scripts"
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402

TYPES = ["情缘", "亲缘", "仇敌", "恩义"]


def collect(rows, scope=None):
    """TSV 行 → relations 列表（status=校定；scope 口径按行 book ∈ scope 过滤）。"""
    relations = []
    for r in rows:
        if (r.get("status") or "").strip() != "校定":
            continue
        book = (r.get("book") or "").strip() or None
        if not esc.in_scope(book, scope):
            continue
        relations.append({
            "a": (r.get("a") or "").strip(),
            "b": (r.get("b") or "").strip(),
            "type": (r.get("type") or "").strip(),
            "tier": (r.get("tier") or "").strip(),
            "book": book,
            "loc": (r.get("loc") or "").strip(),
            "note": (r.get("note") or "").strip(),
        })
    return relations


def build_payload(rows, scope=None):
    """payload 组装（meta + relations）；scope 口径 meta 加 scope/books。"""
    meta = {"schema": "char-relations-v1", "script": "scripts/build_relations.py",
            "source": "kb/校订/人物关系考订.tsv", "types": list(TYPES),
            "note": "师承沿用 lineage 不入本表"}
    smeta = esc.scope_meta(scope)
    if smeta:
        meta.update(smeta)
    return {"meta": meta, "relations": collect(rows, scope)}


def main() -> int:
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    with open(TSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f.read().splitlines(), delimiter="\t"))
    payload = build_payload(rows, scope)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    n_total = sum(1 for r in rows if (r.get("status") or "").strip() == "校定")
    scope_note = f"（scope={scope['profile']}，裁 {n_total - len(payload['relations'])} 条 scope 外）" \
        if scope is not None else ""
    print(f"-> {OUT} · 关系 {len(payload['relations'])} 条{scope_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
