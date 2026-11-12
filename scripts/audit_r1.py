# -*- coding: utf-8 -*-
"""audit_r1.py —— 死亡一致性·宽松核验服务（spec 002 T1）。

口径（穿帮雷达设计决策 3「双轨」之宽松轨）：
  死亡 = 事件表 verb∈{杀,诛,毙} 且 object=个人（群目滤）→ 首死为准，余为复杀疑云；
  死亡位次之后（宇宙编年）该人再以非引述身份出场 → ambiguous（两可，不下断言）；
  死后提及全部为引述 → passes（校订质量展品，games 谜题唯一合法死者来源）。
严格断言版在并行管线 audit.json 的 C4（N5 杀害边+致死结构证据）——本服务只做核验供给。

消费方：games（killer 过滤）· QA（存疑标注）· 武评（败方归属辅助）。
输出：site/data/audit-r1.json（L0）
W2-C1（天山演示版总体方案 §3.1 P0-2/§4.3 C1/§5.5，2026-11-09）新增 --scope：
  - --scope <profile>：核验书目按 book ∈ scope 过滤（死者/两可/通过随之裁剪）；meta 加
    scope 键；--scope all 与不传参数同为全量口径（R6）；
  - 管线顺序固化见 scripts/run_pipeline.py：本工具在工具 E 之后、games 切片之前
    （build_games_data 的 killer 谜题消费本产物 passes）。
用法：python scripts/audit_r1.py [--scope tianshan-demo]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import KB, SITE_DATA, lit_books, today  # noqa: E402

# W2-C1：scope 基础设施复用（export_site_common 在 wuxia-kb/scripts，import 胜过复制——同 W0-T3b）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / "wuxia-kb" / "scripts"
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402

DEATH_VERBS = {"杀", "诛", "毙"}
CHRONO = ["白发魔女传", "塞外奇侠传", "七剑下天山", "江湖三女侠"]

# 与 site/src/lib/groups.ts 同源（修改两处同步）
GROUP_LABELS = {
    "清兵", "清军", "清军水师", "明军", "官兵", "官军", "满洲军队", "满洲军", "神策营",
    "锦衣卫", "御林军", "禁卫军", "大内", "大内卫士", "清宫", "血滴子",
    "武当弟子", "少林弟子", "峨嵋弟子", "众人", "侍卫", "卫士",
    "关东四侠", "江南七侠", "桑家三妖", "五龙帮", "铁扇帮",
    # 族群/泛称（事件表实测漏网）
    "满洲", "喀达尔族", "回民", "汉人", "蒙古人",
}


def select_books(available, scope=None):
    """核验书目 = CHRONO（编年序）∩ available（kb 已点亮）∩ scope（W2-C1；None=全量口径）。"""
    books = [b for b in CHRONO if b in available]
    if scope is not None:
        books = [b for b in books if esc.in_scope(b, scope)]
    return books


def scan(books):
    """事件层死亡/出场扫描 → (deaths, appearances, groups_filtered)。"""
    deaths: dict[str, list] = {}   # person -> [ (ord, book, loc, by) ]
    appearances: dict[str, list] = {}  # person -> [ (ord, book, loc, verb, role, in_quote) ]
    groups_filtered = 0

    for book in books:
        ev = json.loads((KB / book / "事件表.json").read_text(encoding="utf-8"))
        for e in ev.get("events", []):
            loc = e.get("loc", "")
            subj, obj = e.get("subject") or "", e.get("object") or ""
            verb = e.get("verb") or ""
            in_quote = bool(e.get("in_quote"))
            for role, who in (("subject", subj), ("object", obj)):
                if not who:
                    continue
                if who in GROUP_LABELS:
                    groups_filtered += 1
                    continue
                ord_ = (CHRONO.index(book), int(loc[:3] or 0), int(loc[4:7] or 0) if len(loc) > 4 else 0)
                appearances.setdefault(who, []).append((ord_, book, loc, verb, role, in_quote))
            is_composite = "、" in obj  # 顿号组合死者（"白石、红云、青蓑"）按组合实体滤
            if verb in DEATH_VERBS and obj and obj not in GROUP_LABELS and not is_composite:
                ord_ = (CHRONO.index(book), int(loc[:3] or 0), int(loc[4:7] or 0) if len(loc) > 4 else 0)
                deaths.setdefault(obj, []).append((ord_, book, loc, subj))
    return deaths, appearances, groups_filtered


def build_payload(deaths, appearances, groups_filtered, books, scope=None):
    """audit-r1.json payload 组装（W2-C1：scope 口径 meta 加 scope 键；全量口径形态不变）。"""
    ambiguous, passes = [], []
    for person, ds in deaths.items():
        ds.sort(key=lambda x: x[0])
        first_ord, dbook, dloc, dby = ds[0]
        aps = sorted(appearances.get(person, []), key=lambda x: x[0])
        after = [a for a in aps if a[0] > first_ord]
        live = [a for a in after if not a[5]]
        rec = {
            "name": person,
            "death": {"book": dbook, "loc": dloc, "by": dby or None},
            "after_n": len(after),
            "deaths_n": len(ds),
        }
        if live:
            rec["live_n"] = len(live)
            rec["samples"] = [
                {"book": b, "loc": l, "v": v, "role": r}
                for (_o, b, l, v, r, _q) in live[:5]
            ]
            ambiguous.append(rec)
        else:
            rec["note"] = "死后提及全部为引述" if after else "死后无提及"
            passes.append(rec)

    ambiguous.sort(key=lambda x: -x.get("live_n", 0))
    meta = {
        "schema": "audit-r1-v1", "generated": today(),
        "caliber": "宽松核验（verb∈{杀,诛,毙}；首死为准）——严格断言版见 audit.json C4",
        "books": books, "groups_filtered": groups_filtered,
        "consumers": ["games killer 过滤（仅 passes）", "qa killer 存疑标注", "武评败方归属辅助"],
    }
    if scope is not None:
        meta["scope"] = scope["profile"]
    payload = {
        "meta": meta,
        "totals": {"deaths_persons": len(deaths), "ambiguous": len(ambiguous), "passes": len(passes),
                   "events_scanned_books": len(books)},
        "ambiguous": ambiguous,
        "passes": passes,
    }
    return payload


def main() -> int:
    # W2-C1：--scope 解析（--scope all / 不传 = 全量口径，None；同 W0-T3a/T3b）
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    books = select_books(lit_books(), scope)
    deaths, appearances, groups_filtered = scan(books)
    payload = build_payload(deaths, appearances, groups_filtered, books, scope=scope)
    out = SITE_DATA / "audit-r1.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    scope_note = f"（scope={scope['profile']}）" if scope is not None else ""
    ambiguous, passes = payload["ambiguous"], payload["passes"]
    print(f"-> {out} · 死者 {len(deaths)} · 两可 {len(ambiguous)} · 通过 {len(passes)} · "
          f"群目滤 {groups_filtered}{scope_note}")
    top = [(a["name"], a["live_n"]) for a in ambiguous[:8]]
    print("   两可 top:", top)
    print("   练霓裳 在两可?" , any(a["name"] == "练霓裳" for a in ambiguous),
          "· 武琼瑶 在两可?", any(a["name"] == "武琼瑶" for a in ambiguous))
    return 0


if __name__ == "__main__":
    sys.exit(main())
