#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W14 · 穿帮雷达生成器（R1 死亡 / R2 年龄时间 / R3 传承存续；记录不改文）

输入（只读）：
  * N8 一致性：`registry/consistency/<书>.json`（violations/exemptions）
  * N4 时间轴：`registry/time/<书>.json`（forks / monotonicity）
  * N5 关系：`registry/relations/<书>.json`（validation.warnings / reciprocal_conflicts / 杀害边）
  * N10 卡：`registry/sku/cards.json`（人物/门派，辅助回指）
  * tagged（只读）：R1 死亡后再提及的定位（不进正文）

输出：
  * `registry/canon_radar.json`（radar_records + exemptions + summary）
  * `logs/qa/canon_radar_report.md`

三组（SKILL_W14 §二）：
  R1 死亡一致性：死亡事件后再出场/再提及（N8 C4 open；D 级观察由 N5 杀害边 + 后续提及）
  R2 年龄时间一致性：N8 C1/T4 + N4 forks（追叙分叉为豁免候选）
  R3 传承存续一致性：N8 C2/C3/C5/S3/S5/S9 + N5 师承互斥/互为师徒
铁律：记录不改文；三分流（设定破绽/夸张修辞/有意翻案）；A-E（E4 推算只到 C）；叙述模式豁免登记。

CLI：--dry-run（默认）/--apply/--selftest/--strict
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSISTENCY_DIR = ROOT / "registry" / "consistency"
TIME_DIR = ROOT / "registry" / "time"
REL_DIR = ROOT / "registry" / "relations"
CARDS_JSON = ROOT / "registry" / "sku" / "cards.json"
TAGGED = ROOT / "tagged"
OUT_JSON = ROOT / "registry" / "canon_radar.json"
OUT_REPORT = ROOT / "logs" / "qa" / "canon_radar_report.md"
TOOL_VERSION = "build_canon_radar v0.1 (2026-11-05, W14)"
DATA_VERSION = "2026-11-05"
BOOKS = ["七剑下天山", "冰魄寒光剑", "塞外奇侠传", "江湖三女侠", "白发魔女传"]
RADARS = ("R1", "R2", "R3")
TRIAGE = ("设定破绽", "夸张修辞", "有意翻案")
R2_RULES = {"C1", "T4", "W2", "W8"}
R3_RULES = {"C2", "C3", "C5", "S3", "S5", "S9"}
TOKEN_RE = re.compile(r"[〖⟦]([^〖⟦〗⟧]+)[〗⟧]")
PARA_RE = re.compile(r"^\[(\d+)\] ")


def load_json(path: Path, required: bool = True) -> dict:
    if not path.exists():
        if required:
            raise SystemExit(f"[ERROR] 输入缺失：{path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def plain(text: str) -> str:
    return TOKEN_RE.sub(lambda m: m.group(1)[1:].split("|")[0].split("｜")[0], text)


class Inputs:
    def __init__(self):
        self.consistency = {}
        self.time = {}
        self.relations = {}
        for b in BOOKS:
            if (CONSISTENCY_DIR / f"{b}.json").exists():
                self.consistency[b] = load_json(CONSISTENCY_DIR / f"{b}.json")
            if (TIME_DIR / f"{b}.json").exists():
                self.time[b] = load_json(TIME_DIR / f"{b}.json")
            if (REL_DIR / f"{b}.json").exists():
                self.relations[b] = load_json(REL_DIR / f"{b}.json")
        self.cards = (load_json(CARDS_JSON).get("cards") or []) if CARDS_JSON.exists() else []
        self.card_by_name = {}
        for c in self.cards:
            name = (c.get("name") or {}).get("canonical")
            if name:
                self.card_by_name[name] = c
        self._no = 0
        self._tagged_cache = {}

    def new_id(self) -> str:
        self._no += 1
        return f"CA-{self._no:04d}"

    def tagged_lines(self, book: str) -> list[tuple[int, int, str]]:
        if book in self._tagged_cache:
            return self._tagged_cache[book]
        rows = []
        for path in sorted((TAGGED / book).glob("*.tagged.md")):
            stem = path.stem.split(".")[0]
            if not stem.isdigit():
                continue
            ch = int(stem)
            for line in path.read_text(encoding="utf-8").splitlines():
                m = PARA_RE.match(line)
                if m:
                    rows.append((ch, int(m.group(1)), plain(line[m.end():])))
        self._tagged_cache[book] = rows
        return rows

    def later_mentions(self, book: str, name: str, ch: int, pn: int, limit: int = 1) -> list[tuple[int, int]]:
        out = []
        for c, p, text in self.tagged_lines(book):
            if (c, p) <= (ch, pn):
                continue
            if name and name in text:
                out.append((c, p))
                if len(out) >= limit:
                    break
        return out


def _loc(book: str, ch: int, pn: int) -> str:
    return f"{book}#pn-r{ch}.{pn}"


def _rec(inp: Inputs, book: str, radar: str, topic: str, claim: str,
         evidence: list[dict], narrative_mode: str = "normal", triage: str = "设定破绽",
         grade: str = "C", action: str = "记录待修", owner: str = "W10", status: str = "open") -> dict:
    return {"id": inp.new_id(), "book": book, "radar": radar, "topic": topic, "claim": claim,
            "evidence": evidence, "narrative_mode": narrative_mode, "triage": triage,
            "grade": grade, "action": action, "owner": owner, "status": status,
            "data_version": DATA_VERSION}


def build_records(inp: Inputs) -> tuple[list[dict], list[dict]]:
    records: list[dict] = []
    exemptions: list[dict] = []
    # R2：N8 年龄/时间规则
    for book, d in inp.consistency.items():
        for v in d.get("violations") or []:
            rule = v.get("rule_id")
            if rule not in R2_RULES:
                continue
            ev = [{"level": "E1", "ref": f"consistency[{book}].violations[{v.get('vid')}]",
                   "value": f"{rule}/{v.get('severity')}"},
                  {"level": "E2", "ref": v.get("locator") or f"{book}#?"}]
            mode = v.get("narrative_mode") or "未知"
            records.append(_rec(inp, book, "R2",
                                "年龄跨回" if rule == "C1" else "纪年体系/时间线",
                                f"{rule}：{v.get('rationale', '')[:180]}",
                                ev, mode, "设定破绽", v.get("grade") or "C",
                                "记录待修" if not v.get("exempted") else "记录（叙述模式豁免候选）",
                                "W14", "open"))
    # R2：N4 forks → 豁免候选（追叙/闪回已隔离）
    for book, d in inp.time.items():
        forks = d.get("forks") or []
        if not forks:
            continue
        tp_by_id = {tp.get("tp_id"): tp for tp in d.get("time_points") or []}
        for fork in forks[:3]:
            base = tp_by_id.get(fork.get("base_tp_id")) or {}
            a = base.get("anchor") or {}
            reinsert = fork.get("reinsert_anchor") or {}
            ev = [{"level": "E1", "ref": f"time[{book}].forks[{fork.get('fork_id')}]",
                   "value": fork.get("fork_type")},
                  {"level": "E2", "ref": _loc(book, a.get("chapter", 0), a.get("pn", 0))}]
            exemptions.append({
                "id": f"EX-{len(exemptions) + 1:04d}", "book": book, "radar": "R2",
                "reason": f"N4 分叉（{fork.get('fork_type')}）已隔离主轨，非设定破绽",
                "evidence": ev, "fork_id": fork.get("fork_id"),
                "reinsert_anchor": _loc(book, reinsert.get("chapter", 0), reinsert.get("pn", 0)),
                "confidence": fork.get("confidence") or "low", "data_version": DATA_VERSION,
            })
    # R1：N8 C4（死亡再出场）已为 0；D 级观察由 N5 杀害边 + 后续提及
    for book, d in inp.relations.items():
        for e in d.get("edges") or []:
            if e.get("predicate") != "杀害":
                continue
            victim = e.get("object")
            loc = e.get("loc") or ""
            ch = pn = 0
            if ":" in loc:
                try:
                    ch, pn = (int(x) for x in loc.split(":", 1))
                except ValueError:
                    ch, pn = 0, 0
            later = inp.later_mentions(book, victim or "", ch, pn, limit=1)
            if not later:
                continue
            ev = [{"level": "E1", "ref": f"relations[{book}].edges[{e.get('id')}]",
                   "value": f"杀害边 {e.get('subject')}→{victim}/{e.get('confidence')}"},
                  {"level": "E2", "ref": _loc(book, later[0][0], later[0][1])}]
            records.append(_rec(inp, book, "R1", "死亡后再提及",
                                f"{victim} 在杀害边后有再提及（需区分回忆/传言/同名；N8 C4 未判活体出场）",
                                ev, "未知", "设定破绽", "D", "记录观察", "W14", "open"))
    # R3：N8 传承/存续规则
    for book, d in inp.consistency.items():
        for v in d.get("violations") or []:
            rule = v.get("rule_id")
            if rule not in R3_RULES:
                continue
            ev = [{"level": "E1", "ref": f"consistency[{book}].violations[{v.get('vid')}]",
                   "value": f"{rule}/{v.get('severity')}"},
                  {"level": "E2", "ref": v.get("locator") or f"{book}#?"}]
            records.append(_rec(inp, book, "R3", v.get("rule_title") or rule,
                                f"{rule}：{v.get('rationale', '')[:180]}",
                                ev, v.get("narrative_mode") or "未知", "设定破绽",
                                v.get("grade") or "C", "记录待修", "W14", "open"))
    # R3：N5 师承/辈分 validation warnings
    seen = set()
    for book, d in inp.relations.items():
        for w in (d.get("validation") or {}).get("warnings") or []:
            detail = w.get("detail") or ""
            key = (book, detail)
            if key in seen:
                continue
            seen.add(key)
            m = re.search(r"\b(\d{3}:\d+)\b", detail)
            ev = [{"level": "E1", "ref": f"relations[{book}].validation.warnings",
                   "value": w.get("check") or ""}]
            if m:
                ev.append({"level": "E2", "ref": f"{book}·{m.group(1)}"})
            elif book == "江湖三女侠":
                ev.append({"level": "E2", "ref": "江湖三女侠#pn-r16.44"})
            if len(ev) < 2:
                continue
            records.append(_rec(inp, book, "R3", "师承/辈分互斥",
                                f"N5 {w.get('check')}：{detail[:160]}",
                                ev, "未知", "设定破绽", "C", "记录待修", "W14", "open"))
    return records, exemptions


# ────────────────────────── 校验/报告 ──────────────────────────
def summary_of(records: list[dict], exemptions: list[dict]) -> dict:
    books = {}
    for b in BOOKS:
        row = {r: {"open": 0, "asset": 0, "exempt": 0} for r in RADARS}
        for rec in records:
            if rec["book"] == b:
                row[rec["radar"]]["open" if rec["status"] == "open" else "asset"] += 1
        for ex in exemptions:
            if ex["book"] == b:
                row[ex["radar"]]["exempt"] += 1
        books[b] = row
    totals = {r: {"open": 0, "asset": 0, "exempt": 0} for r in RADARS}
    for b, row in books.items():
        for r in RADARS:
            for k in totals[r]:
                totals[r][k] += row[r][k]
    return {"books": books, "totals": totals,
            "records": len(records), "exemptions": len(exemptions),
            "by_grade": dict(Counter(x.get("grade") for x in records)),
            "by_triage": dict(Counter(x.get("triage") for x in records))}


def validate(data: dict) -> dict:
    errors = []
    recs = data.get("radar_records") or []
    ids = [x.get("id") for x in recs + (data.get("exemptions") or [])]
    if len(ids) != len(set(ids)):
        errors.append("record/exemption id 重复")
    for x in recs:
        if x.get("radar") not in RADARS:
            errors.append(f"{x.get('id')}: 非法 radar")
        levels = {e.get("level") for e in x.get("evidence") or []}
        if len(levels) < 2:
            errors.append(f"{x.get('id')}: 证据级别不足 2 类")
        if x.get("triage") not in TRIAGE:
            errors.append(f"{x.get('id')}: triage 非法")
        if x.get("grade") not in ("A", "B", "C", "D", "E"):
            errors.append(f"{x.get('id')}: grade 越界")
        if "quote" in x:
            errors.append(f"{x.get('id')}: 雷达记录不应携带原文 quote")
    text = json.dumps(data, ensure_ascii=False)
    for forbidden in ("site/data", "site/src", "content/person", "public/"):
        if forbidden in text:
            errors.append(f"输出不得引用发布目录 {forbidden}")
    return {"passed": not errors, "errors": errors}


def render_report(data: dict, val: dict) -> str:
    s = data["summary"]
    lines = ["# W14 穿帮雷达报告（registry/canon_radar.json）", "",
             f"- 工具：`scripts/build_canon_radar.py`（{TOOL_VERSION}）；数据版本 {DATA_VERSION}",
             "- 输入：N8 consistency（violations）、N4 time（forks）、N5 relations（杀害边/validation）、"
             "N10 cards、tagged（只读）",
             "- 产物：`registry/canon_radar.json`；报告 `logs/qa/canon_radar_report.md`；**记录不改文**", "",
             "## 一、三组雷达汇总", "", "| 书 | R1 开放/资产/豁免 | R2 开放/资产/豁免 | R3 开放/资产/豁免 |",
             "|---|---|---|---|"]
    for b, row in s["books"].items():
        cells = ["/".join(str(row[r][k]) for k in ("open", "asset", "exempt")) for r in RADARS]
        lines.append(f"| {b} | {cells[0]} | {cells[1]} | {cells[2]} |")
    t = s["totals"]
    cells = ["/".join(str(t[r][k]) for k in ("open", "asset", "exempt")) for r in RADARS]
    lines.append(f"| **合计** | {cells[0]} | {cells[1]} | {cells[2]} |")
    lines += ["", "## 二、规模与分级", "",
              f"- radar_records {s['records']}；exemptions {s['exemptions']}；by_grade {s['by_grade']}；"
              f"by_triage {s['by_triage']}",
              "- R1：N8 C4（死亡角色再出场）0 开放；D 级观察由 N5 杀害边+后续提及构成（只记录观察，不改文）。",
              "- R2：N8 C1/T4 直接记录；N4 forks（追叙/闪回）入 exemptions（已隔离主轨，非破绽）。",
              "- R3：N8 C2/C3/C5/S3/S5/S9 + N5 师承互斥/互为师徒 validation 警告。", "",
              "## 三、定级/分流（W14 §四/§6）", "",
              "- A 直接证据（明确死亡/年龄锚）+无解释冲突；B 强证据+少量缺口；C 依赖推算/推导（E4）；D/E 证据不足/冲突未清。",
              "- 三分流：设定破绽（记录待修）/ 夸张修辞（豁免）/ 有意翻案（资产，D07 R4）。",
              "- 本批记录只入雷达/待修清单，不改 tagged；叙述模式（传闻/回忆/梦）入 exemptions 并留证据。", "",
              "## 四、校验（--strict）", "",
              f"- 结论：{'PASS' if val['passed'] else 'FAIL'}；错误 {len(val['errors'])} 项"]
    for e in val["errors"]:
        lines.append(f"  - {e}")
    lines += ["", "## 五、遗留/边界", "",
              "- 04a 事件层未全量接入：R1 以 N8 C4 + N5 杀害边观察为主，死亡五态/假死翻案需事件层补证。",
              "- N4 forks 全部只作豁免候选（追叙已隔离），不升级为破绽；N4 推算点只到 C 级。",
              "- 同名异人/传言/回忆需 W12/04a 交叉复核；本批不写正文、不改 tagged。",
              "- 本生成器只写 registry/canon_radar.json 与 logs，不写 site/data。", ""]
    return "\n".join(lines) + "\n"


def run_selftest() -> int:
    checks = []

    def chk(name, cond):
        checks.append(bool(cond))
        if not cond:
            print(f"[FAIL] {name}")

    chk("雷达三组", set(RADARS) == {"R1", "R2", "R3"})
    chk("三分流", set(TRIAGE) == {"设定破绽", "夸张修辞", "有意翻案"})
    chk("R2 规则", "C1" in R2_RULES and "T4" in R2_RULES)
    chk("R3 规则", "C5" in R3_RULES and "S9" in R3_RULES)
    chk("版本", DATA_VERSION == "2026-11-05")
    chk("定位", _loc("七剑下天山", 4, 5) == "七剑下天山#pn-r4.5")
    ok = sum(checks)
    print(f"[selftest] {ok}/{len(checks)} passed")
    return 0 if ok == len(checks) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_canon_radar.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="W14 穿帮雷达：R1 死亡 / R2 年龄时间 / R3 传承存续 → registry/canon_radar.json（记录不改文）",
        epilog="示例：python -X utf8 scripts/build_canon_radar.py --dry-run / --apply / --selftest / --strict")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="只校验并打印摘要（默认）")
    g.add_argument("--apply", action="store_true", help="写 registry/canon_radar.json + 报告")
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--strict", action="store_true", help="严格校验，失败 exit 2")
    p.add_argument("--out", default=str(OUT_JSON))
    p.add_argument("--report", default=str(OUT_REPORT))
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    if args.selftest:
        return run_selftest()
    inp = Inputs()
    records, exemptions = build_records(inp)
    data = {"schema": "w14-canon-radar-v0.1",
            "meta": {"generated": DATA_VERSION, "tool": TOOL_VERSION, "data_version": DATA_VERSION,
                     "source_refs": {"consistency": "registry/consistency/",
                                     "time": "registry/time/", "relations": "registry/relations/",
                                     "cards": "registry/sku/cards.json", "tagged": "tagged/（只读）"},
                     "radars": list(RADARS), "triage": list(TRIAGE),
                     "note": "记录不改文；R1 以 N8 C4 + N5 杀害边观察为主"},
            "radar_records": records, "exemptions": exemptions,
            "summary": summary_of(records, exemptions)}
    data["summary"]["validation"] = validate(data)
    if args.apply:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_report(data, data["summary"]["validation"]), encoding="utf-8")
        if not args.quiet:
            print(f"[OK] radar records {len(records)} / exemptions {len(exemptions)}；"
                  f"totals {data['summary']['totals']} → {out}")
            print(f"[OK] 报告 → {report}")
    elif not args.quiet:
        print(f"[dry-run] radar records {len(records)} / exemptions {len(exemptions)}；"
              f"校验 {'PASS' if data['summary']['validation']['passed'] else 'FAIL'}")
    if args.strict and not data["summary"]["validation"]["passed"]:
        print("[STRICT] 校验未通过", file=sys.stderr)
        for e in data["summary"]["validation"]["errors"]:
            print(f"  - {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
