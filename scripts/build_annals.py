# -*- coding: utf-8 -*-
"""build_annals.py —— 年谱切片（spec 005 T1）。

读 kb/校订/史实锚年谱.tsv（status=校定）→
  site/data/annals.json（events + 纪年对照透传）
  site/data/annals-daily.json（{MM-DD: event}——「小说中的今天」查表；月日按原著书写（多为农历））
纪律：史实日期只出现在 conflict_hist/对照位，不冒充小说纪年；月日不齐不入 daily_index。
W2-B3（天山演示版总体方案 §4.2，2026-11-10）daily 纪年档守门：
  推定/段/不详 纵有月日也不入 daily_index（「小说中的今天」只收 明文/史实 档确日）；
  事件本体仍全量保留在 annals.json。
W0-T3b（天山演示版总体方案 §1.2，2026-11-08）新增 --scope：
  - --scope <profile>：事件 book ∈ scope 才保留（book 缺失=不可归书，scope 下裁），
    annals-daily 同步按过滤后事件重建；
  - 不带 --scope：全量口径，行为与现状一致（meta 无 scope 键，方案 R6）。
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TSV = ROOT / "kb" / "校订" / "史实锚年谱.tsv"
OUT_A = ROOT / "site" / "data" / "annals.json"
OUT_D = ROOT / "site" / "data" / "annals-daily.json"

# W0-T3b：scope 基础设施复用（export_site_common 在 wuxia-kb/scripts，import 胜过复制）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / "wuxia-kb" / "scripts"
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402


def collect(rows, scope=None):
    """TSV 行 → (events, daily)（status=校定；scope 口径按事件 book ∈ scope 过滤，daily 同步）。

    W2-B3 纪年档守门：推定/段/不详 不入 daily_index（纵有月日）；明文/史实 月日齐才入。
    """
    events = []
    daily: dict[str, list] = {}
    for r in rows:
        if (r.get("status") or "").strip() != "校定":
            continue
        book = (r.get("book") or "").strip() or None
        if not esc.in_scope(book, scope):
            continue
        m, d = r.get("m") or "", r.get("d") or ""
        grade = r.get("date_grade") or "不详"
        ev = {
            "id": r["id"], "type": r["type"], "name": r["name"].strip(),
            "date": {"y": r.get("y") or None, "m": m or None, "d": d or None,
                     "grade": grade or "不详",
                     "basis": (r.get("date_basis") or "").strip() or None},
            "book": book,
            "loc": (r.get("loc") or "").strip() or None,
            "people": [p for p in (r.get("people") or "").split(";") if p],
            "line": (r.get("line") or "").strip(),
            "conflict_hist": (r.get("conflict_hist") or "").strip() or None,
        }
        events.append(ev)
        if m and d and grade not in ("推定", "段", "不详"):
            key = f"{int(m):02d}-{int(d):02d}"
            daily.setdefault(key, []).append(ev)

    for k in daily:
        daily[k].sort(key=lambda e: (e["type"] != "史实", e["id"]))
    return events, daily


def build_payloads(rows, scope=None):
    """两份 payload 组装（annals + annals-daily）；scope 口径 meta 加 scope/books。"""
    events, daily = collect(rows, scope)
    meta_a = {"schema": "annals-v1", "source": "kb/校订/史实锚年谱.tsv",
              "note": "纪年对照只陈列不断言；月日按原著书写（多为农历）"}
    meta_d = {"schema": "annals-daily-v1", "note": "月-日 → 事件（原著书写口径）"}
    smeta = esc.scope_meta(scope)
    if smeta:
        meta_a.update(smeta)
        meta_d.update(smeta)
    return ({"meta": meta_a, "events": events},
            {"meta": meta_d, "index": daily})


def main() -> int:
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    with open(TSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f.read().splitlines(), delimiter="\t"))
    annals, daily_p = build_payloads(rows, scope)
    OUT_A.write_text(json.dumps(annals, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_D.write_text(json.dumps(daily_p, ensure_ascii=False), encoding="utf-8")
    scope_note = f"（scope={scope['profile']}）" if scope is not None else ""
    print(f"-> {OUT_A}（事件 {len(annals['events'])}）· {OUT_D}（确日键 {len(daily_p['index'])}）{scope_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
