# -*- coding: utf-8 -*-
"""EX-7 · `export_site_gazetteer_universe.py` — gazetteer / universe / atlas 薄导出器

定位（docs/51 §三 EX-7，阶段 2）：
  消费 N7 迁移后的 `registry/gazetteer.json`（650 条，nature/kind/layer/precision/lat/lng/
  unlocatable/books）+ 只读 `kb/系列谱系考订表.json`（lines/chronology_spine/interchange_seeds/
  open_questions）+ 旧站 `site/data/atlas/*.json`（经纬度/章节键只读参考），按 site/data
  2026-11-02 契约导出三件：
    1) `gazetteer.json`  —— meta + places（id/name/aliases/kind/real/lat/lng/precision/verified/books）
    2) `universe.json`   —— meta + lines/chronology_spine/interchange_seeds/open_questions
    3) `atlas/<书>.json` —— meta/title/era/era_conf/chapters/persons/places/bychap/events（5 书）
  桥接期 Astro 38 页零改动；新增字段允许，旧字段不缺（docs/51 §五）。

数据口径：
  - gazetteer：N7 的 `loc_mode=coord` 619 条（旧站契约 places 仅含可落点条目）→ 站点坐标层；
    另 31 条 unlocatable（loc_mode=none）不入坐标层，清单写 meta.field_gaps 与本报告；
    kind 用 N7 §2.3 十三值新口径；real 沿用 N7 兼容派生列（nature=未定 → null）。
  - universe：四节数据来自 `kb/系列谱系考订表.json` 只读快照（人工考订权威数据）。
  - atlas：新数据来自 tagged 实体令牌（bychap 逐回 p/l）、registry/concordance（persons）、
    N7 gazetteer（places 坐标层）、kb/作品元数据表（era/era_conf）；旧站 atlas 只读参考用于
    「章节键/人物键/地点键」兜底（契约要求旧键不缺，docs/51 §五"不得静默丢弃"）；
    **事件层 events 无新管线产物（D03/EX-5 未上线），4 书沿用旧站冻结事件表并显式声明**，
    冰魄寒光剑 events={} 并写 meta.field_gaps（不伪造）。
  - tagged/struct/concordance/registry/kb 全部只读；只写 logs/export（staging+报告）。

CLI：默认 dry-run（只写 staging+reports）；`--apply` 由 export_site_common 统一处理（本任务
     明确不执行 --apply site/data，由 Lead 收口）。
用法：python scripts/export_site_gazetteer_universe.py [--apply]
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import export_site_common as esc  # noqa: E402

ROOT = config.ROOT
KB = config.LEGACY_KB
SITE_DATA = esc.SITE_DATA
REG_GAZETTEER = ROOT / "registry" / "gazetteer.json"
CONC_DIR = ROOT / "registry" / "concordance"
TAGGED_DIR = ROOT / "tagged"
EXPORTER = "EX-7 export_site_gazetteer_universe"

# 新管线 5 书（旧站 atlas 契约只有前 4 书；冰魄寒光剑无历史契约，用合成 signature 校验）
BOOKS = ["七剑下天山", "塞外奇侠传", "江湖三女侠", "白发魔女传", "冰魄寒光剑"]
CONTRACT_BOOKS = BOOKS[:4]

TOKEN_RE = re.compile(r"〖([^〖〗]+)〗")
PN_PARA_RE = re.compile(r"^\[(\d+)\] ")

# 冰魄寒光剑无旧站 atlas 契约：用同构 signature 做 diff（顶层字段 + 4 张 dict 的键集合不预置）
ATLAS_SYNTH_SCHEMA = {
    "type": "dict",
    "keys": {
        "meta": {"type": "dict", "keys": {"generated": {"type": "str"},
                                          "schema": {"type": "str"},
                                          "book": {"type": "str"},
                                          "copyright": {"type": "str"}}},
        "title": {"type": "str"},
        "era": {"type": "str"},
        "era_conf": {"type": "str"},
        "chapters": {"type": "int"},
        "persons": {"type": "dict", "keys": {}},
        "places": {"type": "dict", "keys": {}},
        "bychap": {"type": "dict", "keys": {}},
        "events": {"type": "dict", "keys": {}},
    },
}


# ---------------------------------------------------------------- 基础工具
def load_json(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def sort_chaps(nums) -> list:
    return sorted({int(n) for n in nums if n is not None})


# ---------------------------------------------------------------- 数据源装载
def load_sources() -> dict:
    src = {}
    src["gazetteer"] = load_json(REG_GAZETTEER) if REG_GAZETTEER.exists() else {"places": []}
    src["series"] = load_json(KB / "系列谱系考订表.json")
    src["works"] = load_json(KB / "作品元数据表.json")
    src["works_by_book"] = {w.get("book"): w for w in src["works"].get("works", [])
                            if w.get("book")}
    src["conc"] = {}
    for b in BOOKS:
        p = CONC_DIR / f"{b}.json"
        src["conc"][b] = load_json(p) if p.exists() else {"entities": []}
    src["old_gazetteer"] = esc.load_site("gazetteer.json")
    src["old_universe"] = esc.load_site("universe.json")
    src["old_atlas"] = {}
    for b in CONTRACT_BOOKS:
        src["old_atlas"][b] = esc.load_site(f"atlas/{b}.json")
    # tagged 实体令牌（逐书逐回）：{book: {chapter: {"p": [@canonical], "l": [non-@ canonical]}}}
    tagged = {}
    for b in BOOKS:
        d = TAGGED_DIR / b
        per_ch = {}
        if d.is_dir():
            for fp in sorted(d.glob("*.tagged.md")):
                try:
                    ch = int(fp.name[:3])
                except ValueError:
                    continue
                persons, others = [], []
                seen_p, seen_o = set(), set()
                for line in open(fp, encoding="utf-8"):
                    for m in TOKEN_RE.finditer(line):
                        body = m.group(1)
                        if not body:
                            continue
                        code, rest = body[0], body[1:]
                        # 管道右侧为规范名；% 例外（右侧是受控子标签，canonical=显示串，
                        # 见 registry/concordance spec.canonical_rule 与 symbols.parse_token）
                        canon = (rest.split("|")[0] if code == "%"
                                 else rest.split("|")[-1]).strip()
                        if not canon:
                            continue
                        if code == "@":
                            if canon not in seen_p:
                                seen_p.add(canon)
                                persons.append(canon)
                        else:
                            if canon not in seen_o:
                                seen_o.add(canon)
                                others.append(canon)
                per_ch[ch] = {"p": persons, "l": others}
        tagged[b] = per_ch
    src["tagged"] = tagged
    return src


# ---------------------------------------------------------------- gazetteer.json
def build_gazetteer(src: dict) -> tuple[dict, dict]:
    reg = src["gazetteer"]
    all_places = reg.get("places") or []
    coord = [p for p in all_places if p.get("loc_mode") == "coord"]
    unlocatable = [p for p in all_places if p.get("loc_mode") == "none"]
    books = (reg.get("meta", {}).get("books") or [])[:4]
    old_meta = (src["old_gazetteer"] or {}).get("meta", {})
    old_places = {p["id"]: p for p in (src["old_gazetteer"] or {}).get("places", [])}

    places, n_old_fallback, n_new = [], 0, 0
    for p in sorted(coord, key=lambda x: x["id"]):
        rec = {
            "id": p["id"],
            "name": p.get("name") or p["id"],
            "aliases": list(p.get("aliases") or []),
            "kind": p.get("kind"),
            "real": p.get("real"),
            "lat": p.get("lat"),
            "lng": p.get("lng"),
            "precision": p.get("precision"),
            "verified": bool(p.get("verified")),
            "books": p.get("books") or {},
        }
        old = old_places.get(p["id"])
        if old:
            # 旧站字段兜底（aliases/precision 值等），新值优先
            if not rec["aliases"] and old.get("aliases"):
                rec["aliases"] = list(old["aliases"])
        else:
            n_new += 1
        places.append(rec)
    n_old_fallback = len(places) - n_new
    payload = {
        "meta": {
            "generated": esc.today(),
            "rev": reg.get("meta", {}).get("rev", 1),
            "coord_system": reg.get("meta", {}).get("coord_system",
                                                   old_meta.get("coord_system", "WGS-84(EPSG:4326)")),
            "based_on": {
                "books": list(books or old_meta.get("based_on", {}).get("books", [])),
                "retrieval": old_meta.get("based_on", {}).get(
                    "retrieval", "Nominatim(OSM) + 人工坐标拾取器核验"),
            },
            "tsv_rulings": old_meta.get("tsv_rulings", "kb\\校订\\gazetteer-考订.tsv"),
            "tsv_seeds": old_meta.get("tsv_seeds", "kb\\校订\\gazetteer-seeds.tsv"),
            "strict": False,
            "source": "registry/gazetteer.json（N7 迁移，nature/kind/layer 新口径）",
            "field_gaps": [
                f"unlocatable {len(unlocatable)} 条（loc_mode=none，含风砂堡/木什塔克/喀沁草原等）"
                f"不进入站点坐标层 places（旧契约 places 619 条=有坐标条目）；清单见 "
                f"registry/gazetteer.json meta.stats 与 EX-7 报告。渲染端 D3 降级由下游决定（SKILL §3.6）。",
                "kind 采用 N7 §2.3 十三值归一（旧站为 OSM/中文脏值混用）；旧 kind 原值见 "
                "registry/gazetteer.json 各条 source.legacy_kind。",
                "real 为 N7 nature 兼容派生列：真实→true / 虚构·原型改造→false / 未定→null（迁移暂定，待复核）。",
            ],
        },
        "places": places,
    }
    stats = {"old": len(old_places), "new": len(places), "coord": len(coord),
             "unlocatable": len(unlocatable), "new_places": n_new,
             "legacy_matched": n_old_fallback}
    return payload, stats


# ---------------------------------------------------------------- universe.json
def build_universe(src: dict) -> tuple[dict, dict]:
    series = src["series"]
    payload = {
        "meta": {
            "generated": esc.today(),
            "schema": "site-universe-v1",
            "source": "kb/系列谱系考订表.json（只读；人工考订）",
            "field_gaps": [],
        },
        "lines": series.get("lines", []),
        "chronology_spine": series.get("chronology_spine", []),
        "interchange_seeds": series.get("interchange_seeds", []),
        "open_questions": series.get("open_questions", []),
    }
    stats = {"lines": len(payload["lines"]), "chronology_spine": len(payload["chronology_spine"]),
             "interchange_seeds": len(payload["interchange_seeds"]),
             "open_questions": len(payload["open_questions"])}
    return payload, stats


# ---------------------------------------------------------------- atlas/<书>.json
def _works_meta(src: dict, book: str) -> dict:
    return src["works_by_book"].get(book) or {}


def _conc_persons(src: dict, book: str) -> dict:
    out = {}
    for e in src["conc"].get(book, {}).get("entities", []):
        if e.get("type") != "@":
            continue
        out[e["canonical"]] = {
            "n": e.get("total", 0),
            "chaps": sort_chaps(c.get("chapter", 0) for c in e.get("chapter_counts", [])),
        }
    return out


def _conc_places(src: dict, book: str) -> dict:
    """concordance 的 = 实体（无坐标）→ atlas places 兜底（仅 5th book 需要）。"""
    out = {}
    for e in src["conc"].get(book, {}).get("entities", []):
        if e.get("type") != "=":
            continue
        out[e["canonical"]] = {
            "real": None, "lat": None, "lng": None, "precision": None,
            "aliases": [],
            "chaps": sort_chaps(c.get("chapter", 0) for c in e.get("chapter_counts", [])),
        }
    return out


def build_atlas(src: dict, book: str) -> tuple[dict, dict]:
    wm = _works_meta(src, book)
    old = src["old_atlas"].get(book)
    tagged = src["tagged"].get(book, {})
    reg_places = [p for p in (src["gazetteer"].get("places") or [])
                  if p.get("loc_mode") == "coord" and book in (p.get("books") or {})]

    # persons：新 concordance @ 实体；旧站 key 兜底（契约要求旧键不缺）
    persons = _conc_persons(src, book)
    if old:
        for name, val in (old.get("persons") or {}).items():
            persons.setdefault(name, {"n": val.get("n", 0),
                                      "chaps": sort_chaps(val.get("chaps") or [])})
    # leads 兜底（works 元数据）
    for lead in (wm.get("leads") or []):
        persons.setdefault(lead, {"n": (wm.get("lead_hits") or {}).get(lead, 0),
                                  "chaps": []})

    # places：N7 坐标层（按书过滤）；旧站 key 兜底；5th book 用 concordance = 实体（无坐标）
    places = {}
    for p in reg_places:
        places[p["id"]] = {
            "real": p.get("real"),
            "lat": p.get("lat"),
            "lng": p.get("lng"),
            "precision": p.get("precision"),
            "aliases": list(p.get("aliases") or []),
            "chaps": sort_chaps((p.get("books") or {}).get(book) or []),
        }
    if old:
        for name, val in (old.get("places") or {}).items():
            places.setdefault(name, {
                "real": val.get("real"), "lat": val.get("lat"), "lng": val.get("lng"),
                "precision": val.get("precision"), "aliases": list(val.get("aliases") or []),
                "chaps": sort_chaps(val.get("chaps") or []),
            })
    n_conc_places = 0
    if not old:
        cp = _conc_places(src, book)
        for name, val in cp.items():
            if name not in places:
                places[name] = val
                n_conc_places += 1

    # bychap：新 tagged 逐回 p/l；旧站章节键兜底（契约要求旧章节键不缺）
    bychap = {}
    for ch, slot in sorted(tagged.items()):
        bychap[str(ch)] = {"p": slot["p"], "l": slot["l"]}
    if old:
        for ch, val in (old.get("bychap") or {}).items():
            if ch not in bychap:
                bychap[ch] = {"p": list(val.get("p") or []), "l": list(val.get("l") or [])}
        for ch, val in (old.get("bychap") or {}).items():
            if ch in bychap and (not bychap[ch]["p"] and not bychap[ch]["l"]):
                bychap[ch] = {"p": list(val.get("p") or []), "l": list(val.get("l") or [])}

    # events：新管线无事件层（D03/EX-5 未上线）。4 书沿用旧站冻结事件表；5th book 空 + field_gaps
    if old:
        events = json.loads(json.dumps(old.get("events") or {}, ensure_ascii=False))
        events_src = "legacy-frozen"
    else:
        events = {}
        events_src = "empty"

    # chapters：旧契约=正文章回数（不含 000 楔子）；无旧站时用 works/chapters 或 tagged 最大回号
    if old:
        chapters = old.get("chapters") or len([c for c in bychap if int(c) > 0])
    else:
        chapters = wm.get("chapters") or len([c for c in bychap if int(c) > 0])

    era = wm.get("era") or (old or {}).get("era") or ""
    era_conf = wm.get("era_conf") or (old or {}).get("era_conf") or "todo"

    field_gaps = [
        "events：新管线事件层（D03/EX-5）未上线，"
        + ("沿用旧站 2026-11-02 冻结事件表（不伪造；EX-5 上线后替换）。"
           if old else "本表 events={}（冰魄寒光剑无历史事件表与事件产物；D03 未上线，不伪造）。"),
        "era/era_conf 来自 kb/作品元数据表（只读）；kb_status=待建/标注中的书其年代置信见 era_conf。",
        "persons：registry/concordance @ 实体（新口径，n=出现次数、chaps=出现回号）；"
        "旧站人物键保留兜底（契约不丢键）。",
        "places：registry/gazetteer N7 坐标层（loc_mode=coord）；"
        + ("冰魄寒光剑无历史坐标层，places 取自 concordance = 实体（无经纬度，lat/lng=null）。"
           if not old else "unlocatable 31 条不入图（见 gazetteer.json field_gaps）。"),
        "bychap：tagged 实体令牌逐回生成（p=@人物、l=其余实体规范名）；旧站章节键保留兜底。",
    ]
    payload = {
        "meta": {
            "generated": esc.today(),
            "schema": "atlas-slice-v1",
            "book": book,
            "copyright": "L0 图谱层：仅定位符与结构化事实，不含摘录",
            "source": "tagged/struct + registry/concordance + registry/gazetteer + kb/作品元数据表"
                      "（旧 site/data/atlas 只读兜底）",
            "events_source": events_src,
            "field_gaps": field_gaps,
        },
        "title": book,
        "era": era,
        "era_conf": era_conf,
        "chapters": chapters,
        "persons": persons,
        "places": places,
        "bychap": bychap,
        "events": events,
    }
    stats = {
        "book": book,
        "chapters": chapters,
        "persons": len(persons),
        "places": len(places),
        "bychap_chapters": len(bychap),
        "events_chapters": len(events),
        "events_edges": sum(len(v) for v in events.values() if isinstance(v, list)),
        "new_conc_places": n_conc_places,
        "contract": bool(old),
    }
    return payload, stats


# ---------------------------------------------------------------- finish（4 书有契约；冰魄合成校验）
def finish_with_contract(name: str, payload: dict, notes: str) -> dict:
    return esc.finish(name, payload, exporter=EXPORTER, notes=notes)


def finish_synth_contract(name: str, payload: dict, notes: str) -> dict:
    """无历史契约的落点（冰魄寒光剑）：合成 signature 做 diff，并手动落 staging/report；
    --apply 时与 esc.finish 同口径写 site/data（先备份）。2026-11-05 修复：原恒 dry-run，
    第 5 书 atlas 只进 staging、永不落盘，与集成器 "atlas 5 书" 声称不符。"""
    contract = {"name": name, "generated": esc.now_iso(), "schema": ATLAS_SYNTH_SCHEMA}
    diff = esc.diff_against_contract(name, payload, contract)
    esc.STAGING.mkdir(parents=True, exist_ok=True)
    staged = esc.atomic_write_json(payload, esc.STAGING / name)

    applied = None
    if esc.is_apply():
        target = esc.SITE_DATA / name
        if target.exists():
            backup_run = esc.BACKUP_ROOT / f"apply_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_run.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_run / name.replace("/", "_"))
        applied = esc.atomic_write_json(payload, target)

    report = esc._render_report(name, EXPORTER, diff, payload, staged, applied,
                                notes + "\n（本文件无 2026-11-02 历史契约，差异基线=4 书共同结构合成 signature）")
    report_path = esc.REPORTS_DIR / (name.replace("/", "_").replace(".json", "") + "_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8", newline="\n")
    print(f"[export] {name}: records={diff['new_record_count']} hard_gaps={diff['hard_gap_count']} "
          f"staging={staged} {'APPLIED→' + str(applied) if applied else '(dry-run / synth-contract)'}")
    return diff


def main() -> int:
    src = load_sources()
    results = {}

    # 1) gazetteer.json
    payload, stats = build_gazetteer(src)
    notes = (f"places {stats['new']} 条（N7 coord={stats['coord']}；unlocatable={stats['unlocatable']} "
             f"不入坐标层）；旧站 619 条键匹配 {stats['legacy_matched']}，新增 {stats['new_places']}；"
             f"kind=N7 十三值口径、real=N7 兼容派生列。")
    results["gazetteer.json"] = finish_with_contract("gazetteer.json", payload, notes)

    # 2) universe.json
    upayload, ustats = build_universe(src)
    unotes = (f"lines {ustats['lines']} / chronology_spine {ustats['chronology_spine']} / "
              f"interchange_seeds {ustats['interchange_seeds']} / open_questions {ustats['open_questions']}；"
              f"四节均来自 kb/系列谱系考订表.json 只读。")
    results["universe.json"] = finish_with_contract("universe.json", upayload, unotes)

    # 3) atlas/<书>.json ×5
    astats = {}
    for book in BOOKS:
        payload, st = build_atlas(src, book)
        astats[book] = st
        notes = (f"{book}：chapters={st['chapters']} persons={st['persons']} places={st['places']} "
                 f"bychap={st['bychap_chapters']} events_chapters={st['events_chapters']} "
                 f"events_edges={st['events_edges']}；"
                 f"persons=concordance @ + 旧键兜底；places=gazetteer 坐标层"
                 + ("（冰魄用 concordance = 实体无坐标）" if not st["contract"] else "")
                 + f"；events={payload['meta']['events_source']}。")
        name = f"atlas/{book}.json"
        if st["contract"]:
            results[name] = finish_with_contract(name, payload, notes)
        else:
            results[name] = finish_synth_contract(name, payload, notes)

    # 4) 汇总报告（跨文件）
    esc.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# EX-7 汇总报告（gazetteer / universe / atlas）",
        "",
        f"- 导出器：{EXPORTER}",
        f"- 时间：{esc.now_iso()}",
        f"- 模式：{'APPLY' if esc.is_apply() else 'dry-run（仅 staging）'}",
        "",
        "| 输出 | 旧契约记录 | 新产出 | hard_gap | staging |",
        "|---|---:|---:|---:|---|",
    ]
    for name, d in results.items():
        lines.append(f"| `{name}` | {d['old_record_count']} | {d['new_record_count']} | "
                     f"{d['hard_gap_count']} | `logs/export/staging/{name.replace('/', '_')}` |")
    lines += ["", "## atlas 逐书统计", "",
              "| 书 | chapters | persons | places | bychap 回 | events 回 | events 边 | 契约 |",
              "|---|---:|---:|---:|---:|---:|---:|---|"]
    for book in BOOKS:
        s = astats[book]
        lines.append(f"| {book} | {s['chapters']} | {s['persons']} | {s['places']} | "
                     f"{s['bychap_chapters']} | {s['events_chapters']} | {s['events_edges']} | "
                     f"{'历史契约' if s['contract'] else '合成 signature（无历史契约）'} |")
    lines += ["", "## 数据源与缺口", "",
              "- gazetteer：N7 `registry/gazetteer.json` coord 619 条入坐标层；unlocatable 31 条不入图（见文件 field_gaps）。",
              "- universe：`kb/系列谱系考订表.json` 四节只读快照（人工考订权威）。",
              "- atlas：persons=registry/concordance @；places=N7 坐标层；bychap=tagged 逐回实体令牌；"
              "era/era_conf=kb/作品元数据表；events 4 书沿用旧站冻结事件表（D03/EX-5 未上线），冰魄 events={}；"
              "旧站 atlas 章节/人物/地点键保留兜底（契约不丢键）。",
              "- 硬缺口合计：**%d**（目标 0；旧站 4 书契约逐项校验）。" % sum(
                  d["hard_gap_count"] for d in results.values()),
              ""]
    summary_path = esc.REPORTS_DIR / "ex7_summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    total = sum(d["hard_gap_count"] for d in results.values())
    print(f"\n[EX-7] 汇总：{len(results)} 个输出，契约硬缺口合计 = {total}")
    for name, d in results.items():
        print(f"  {name}: old={d['old_record_count']} new={d['new_record_count']} "
              f"hard_gap={d['hard_gap_count']} "
              f"(missing={len(d['missing_keys'])} type={len(d['type_mismatch'])} "
              f"item_missing={len(d['item_missing_keys'])})")
    print(f"[EX-7] 汇总报告 → {summary_path}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
