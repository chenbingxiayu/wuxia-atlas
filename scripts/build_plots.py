# -*- coding: utf-8 -*-
"""build_plots.py v1.2 —— 剧情锚点轨切片（spec 004 T1 正式管线）。

读 kb/校订/剧情锚点考订.tsv（status=校定）→ site/data/char_plots.json。
place 三级：实锚（〖=〗同行标记，coords=gaz[place]）＞ 推理（anchor_coords 包含式，◌ 渲染）＞ 待考/无（不落图）。
W0-T3b（天山演示版总体方案 §1.2，2026-11-08）新增 --scope：
  - --scope <profile>：TSV 行 book ∈ scope 才保留（book 缺失=不可归书，scope 下裁）；
  - 不带 --scope：全量口径，行为与现状一致（meta 无 scope 键，方案 R6）。
W2-B4（天山演示版总体方案 §4.2 B4，2026-11-10）新增 book_states（跨书生命弧）：
  - 读 kb/校订/书内状态.tsv（person/book/state/status，status=校定）；
  - 并入 characters[person].book_states = [{book, state}, …]（顺序=TSV 文件行序）；
  - scope 口径：状态行 book ∈ scope 才保留；人物无状态行 → 不生成键（宇宙页 arcOf 静默）。
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TSV = ROOT / "kb" / "校订" / "剧情锚点考订.tsv"
BOOK_STATES = ROOT / "kb" / "校订" / "书内状态.tsv"
OUT = ROOT / "site" / "data" / "char_plots.json"
TAG_COLOR = {"情感": "#a63a2b", "恩怨仇杀": "#34546e", "武道进境": "#b8860b",
             "家国大业": "#5e7d5a", "身世师门": "#8a6607"}
GAZ = ROOT / "site" / "data" / "gazetteer.json"

# W0-T3b：scope 基础设施复用（export_site_common 在 wuxia-kb/scripts，import 胜过复制）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / "wuxia-kb" / "scripts"
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402


def load_gaz():
    try:
        return {p["name"]: p for p in json.loads(GAZ.read_text(encoding="utf-8"))["places"]}
    except FileNotFoundError:
        return {}


def collect(rows, coords_of, scope=None):
    """TSV 行 → characters dict（status=校定；scope 口径按行 book ∈ scope 过滤）。"""
    characters: dict[str, dict] = {}
    for row in rows:
        if (row.get("status") or "").strip() != "校定":
            continue
        book = (row.get("book") or "").strip() or None
        if not esc.in_scope(book, scope):
            continue
        person = row["person"].strip()
        rec = characters.setdefault(person, {"plots": []})
        tags = [t for t in (row.get("tags") or "").split(";") if t]
        status = (row.get("place_status") or "").strip() or "无"
        place = (row.get("place_name") or "").strip() or None
        anchor = (row.get("place_anchor") or "").strip() or None
        rec["plots"].append({
            "id": f"plot-{person}-{row['seq']}",
            "seq": int(row["seq"]),
            "name": row["name"].strip(),
            "tags": tags,
            "tag_colors": [TAG_COLOR.get(t, "#8c8477") for t in tags],
            "book": book,
            "loc": f"{int(row['chap']):03d}:{int(row['line']):03d}",
            "story_date": {"value": (row.get("date_value") or "").strip() or None,
                           "grade": (row.get("date_grade") or "").strip() or "不详",
                           "basis": (row.get("date_basis") or "").strip() or None},
            "place": {"name": place, "status": status, "anchor": anchor,
                      "coords": coords_of(status, place, anchor),
                      "candidates": (row.get("place_candidates") or "").strip() or None},
            "line": (row.get("one_liner") or "").strip(),
        })
    for rec in characters.values():
        rec["plots"].sort(key=lambda p: p["seq"])
    return characters


def parse_book_states(rows, in_scope):
    """书内状态.tsv 行 → {person: [{book, state}]}（status=校定；scope 过滤；保持文件行序）。"""
    out: dict[str, list] = {}
    for row in rows:
        if (row.get("status") or "").strip() != "校定":
            continue
        book = (row.get("book") or "").strip()
        person = (row.get("person") or "").strip()
        state = (row.get("state") or "").strip()
        if not person or not book or not state:
            continue
        if not in_scope(book):
            continue
        out.setdefault(person, []).append({"book": book, "state": state})
    return out


def load_book_states(scope=None, path=None):
    """读书内状态.tsv（默认 kb/校订/书内状态.tsv）；scope=None 为全量口径。"""
    p = Path(path) if path else BOOK_STATES
    if not p.exists():
        return {}
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f.read().splitlines(), delimiter="\t"))
    return parse_book_states(rows, lambda b: esc.in_scope(b, scope))


def build_payload(rows, gaz, scope=None, book_states=None):
    """payload 组装（meta + characters + book_states）；scope 口径 meta 加 scope/books。"""

    def coords_of(status, place, anchor):
        if status == "实锚" and place in gaz:
            p = gaz[place]
            return [p["lng"], p["lat"]]
        if status == "推理" and anchor:
            p = gaz.get(anchor) or next((v for k, v in gaz.items() if anchor in k or k in anchor), None)
            if p:
                return [p["lng"], p["lat"]]
        return None

    if book_states is None:
        book_states = load_book_states(scope)
    meta = {"schema": "char-plots-v1.2", "script": "scripts/build_plots.py",
            "source": "kb/校订/剧情锚点考订.tsv",
            "book_states_source": "kb/校订/书内状态.tsv",
            "note": "实锚●/推理◌/待考不落图；推理锚 tooltip 必带依据；book_states=跨书生命弧"}
    smeta = esc.scope_meta(scope)
    if smeta:
        meta.update(smeta)
    characters = collect(rows, coords_of, scope)
    for person, rec in characters.items():
        bs = book_states.get(person)
        if bs:
            rec["book_states"] = bs
    return {"meta": meta, "characters": characters}


def main() -> int:
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    gaz = load_gaz()
    with open(TSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f.read().splitlines(), delimiter="\t"))
    payload = build_payload(rows, gaz, scope)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    characters = payload["characters"]
    n_coords = sum(1 for r in characters.values() for p in r["plots"] if p["place"]["coords"])
    n_total = sum(len(r["plots"]) for r in characters.values())
    scope_note = f"（scope={scope['profile']}）" if scope is not None else ""
    print(f"-> {OUT} · 人物 {len(characters)} · 锚点 {n_total}（落点 {n_coords}）{scope_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
