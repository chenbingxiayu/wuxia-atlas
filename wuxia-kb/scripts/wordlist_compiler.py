# -*- coding: utf-8 -*-
"""C0d · 词表双轨编译器 —— wordlists/ 人工源 → 机读 JSON（D09 双轨架构）。

双轨铁律（← 02h/09 词表规划）：
  人工源 = wordlists/<name>_source.md（简单表）或 <name>_source.json（复杂表，人工直改）
  派生产 = wordlists/<name>.json（本编译器产物，禁止手改；改源后重编译）
  互不冲掉：编译不删人工条目，人工源不经派生产回写。

源格式一：Markdown 表格（简单词表），列约定——
  | surface | type | tier | status | conf | evidence | note |
  tier ∈ auto/review/watch；status ∈ auto/待审/已核准；conf ∈ strong/ok/weak
  evidence 格式 `书:回`（多条空格分隔）；type 用实体码或词表自定类别字串。

源格式二：JSON 源（复杂词表，如 verbs 的 senses/collocations/complements），字段 =
  D09 八字段骨架（surface/canonical/type/tier/conf/evidence/status/version）+ 登记制扩展字段。

产物 schema：
  {"meta": {schema:"wordlist-v1", generated, source, totals:{all,auto,review,watch}},
   "items": [ {...八字段+扩展...} ]}
  auto 档纪律：tier=auto 且 status=已核准 的条目才允许批量补标消费（附 auto_ready 列表）。

用法：
  python wordlist_compiler.py --all          # 编译全部源
  python wordlist_compiler.py --name verbs   # 编译单个
  python wordlist_compiler.py --check        # 只校验不落盘（CI 用）
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import symbols  # noqa: E402
import config   # noqa: E402

WL_DIR = config.DIR_WORDLISTS
TIER = set(symbols.TIER_VALUES)
STATUS = set(symbols.STATUS_VALUES)
CONF = set(symbols.CONF_VALUES)
SCHEMA = "wordlist-v1"
SPEC_VERSION = symbols.SPEC_VERSION
EVIDENCE_RE = re.compile(r"^[^:\s]+:\S+$")  # 书:回（回可为数字/中文/区间）


def parse_md_source(path: Path):
    """解析 md 表格源 → items 列表 + 错误列表。"""
    items, errors = [], []
    lines = path.read_text(encoding="utf-8").splitlines()
    header, colmap = None, None
    for ln, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(">"):
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):     # 分隔行
                continue
            if header is None:
                header = cells
                colmap = {c: i for i, c in enumerate(cells)}
                if "surface" not in colmap:
                    errors.append(f"{path.name}:{ln} 表头缺 surface 列")
                    return items, errors
                continue
            get = lambda name: (cells[colmap[name]] if name in colmap and colmap[name] < len(cells) else "")
            surface = get("surface")
            if not surface or surface in ("—", "-"):
                continue
            tier = get("tier") or "watch"
            status = get("status") or "待审"
            conf = get("conf") or "weak"
            evidence = [e for e in get("evidence").split() if e]
            item = {
                "surface": surface,
                "canonical": get("canonical") or surface,
                "type": get("type") or get("domain") or None,
                "tier": tier, "status": status, "conf": conf,
                "evidence": evidence,
                "version": SPEC_VERSION,
            }
            if get("note"):
                item["note"] = get("note")
            items.append(item)
    return items, errors


def load_json_source(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("items", [])
    errors = []
    for it in items:
        if not it.get("surface"):
            errors.append(f"{path.name}: 缺 surface 的条目 {it}")
    return items, errors


def validate(items, name):
    errors, warns = [], []
    seen = {}
    for it in items:
        s = it.get("surface", "")
        if s in seen:
            errors.append(f"[{name}] 重复 surface：{s}（首见于第 {seen[s]} 条）")
        else:
            seen[s] = len(seen)
        if it.get("tier") not in TIER:
            errors.append(f"[{name}] {s}: tier 非法（{it.get('tier')}）")
        if it.get("status") not in STATUS:
            errors.append(f"[{name}] {s}: status 非法（{it.get('status')}）")
        if it.get("conf") and it["conf"] not in CONF:
            errors.append(f"[{name}] {s}: conf 非法（{it['conf']}）")
        if it.get("type") and len(it["type"]) == 1 and it["type"] not in symbols.ALL_CODES:
            errors.append(f"[{name}] {s}: 实体码 {it['type']} 不在定版内")
        for ev in it.get("evidence", []):
            if not EVIDENCE_RE.match(ev):
                warns.append(f"[{name}] {s}: evidence 『{ev}』非 书:回 格式")
        if it.get("tier") == "auto" and len(s) <= 1:
            errors.append(f"[{name}] {s}: 单字词不得入 auto 档（D09 档位纪律）")
    return errors, warns


def compile_one(src: Path, check_only=False):
    name = src.name.replace("_source.md", "").replace("_source.json", "")
    if src.suffix == ".md":
        items, errors = parse_md_source(src)
    else:
        items, errors = load_json_source(src)
    verrors, warns = validate(items, name)
    errors = errors + verrors
    if check_only:
        return name, items, errors, warns
    out = {
        "meta": {
            "schema": SCHEMA,
            "generated": datetime.date.today().isoformat(),
            "source": src.name,
            "spec_version": SPEC_VERSION,
            "totals": {
                "all": len(items),
                "auto": sum(1 for i in items if i["tier"] == "auto"),
                "review": sum(1 for i in items if i["tier"] == "review"),
                "watch": sum(1 for i in items if i["tier"] == "watch"),
                "auto_ready": sum(1 for i in items if i["tier"] == "auto" and i["status"] == "已核准"),
            },
        },
        "items": items,
    }
    dst = WL_DIR / f"{name}.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return name, items, errors, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--name")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    sources = sorted(list(WL_DIR.glob("*_source.md")) + list(WL_DIR.glob("*_source.json")))
    if a.name:
        cands = [p for p in sources if p.name.startswith(a.name + "_source")]
        if not cands:
            print(f"未找到源：{a.name}_source.(md|json)"); sys.exit(2)
        sources = cands
    if not a.all and not a.name and not a.check:
        ap.print_help(); sys.exit(2)
    if a.check:
        sources = sources  # check 走全量
    fail = 0
    for src in sources:
        name, items, errors, warns = compile_one(src, check_only=a.check)
        auto_ready = sum(1 for i in items if i["tier"] == "auto" and i["status"] == "已核准")
        status = "PASS" if not errors else "FAIL"
        print(f"[{status}] {name}: {len(items)} 条 (auto {auto_ready} 可批量) "
              f"errors={len(errors)} warns={len(warns)}" + ("" if a.check else f" -> {name}.json"))
        for e in errors:
            print("   ✗", e)
        for w in warns[:5]:
            print("   ⚠", w)
        if errors:
            fail += 1
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
