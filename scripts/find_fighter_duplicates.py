# -*- coding: utf-8 -*-
"""find_fighter_duplicates.py —— G1 预防性排查：武评榜内「同类同人多条目」候选扫描。

背景（任务 G1 第 3 项）：F1 后 ratings.json 241 fighters 出现 承珠（联剑）/于承珠（散花）
同一人两条目——排查其余 fighters 是否存在同类问题：
  - 一 fighter 名为另一 fighter 的别名（entity-index @ 行 aliases 互指）；
  - 两 fighter 名为同一 @ canonical 的别名（entity-index 聚合层归一证据）。
输出候选清单 → kb/校订/武评同人多条目-候选.tsv（机械证据 + auto_verdict + 人工裁定列），
**只排查不改动**——确凿者（别名互证≥2 且共书/目标实体书域覆盖两人书域）另行走
registry alias_overrides 修复（D9 机制照用，G1 已裁定 6 条）；两独立人物宁缺毋滥留档。

finder 纯函数（build_alias_index / find_candidates）测试固化于
wuxia-kb/tests/test_g1_closeout.py::TestFighterDedupeFinder（合成 fixture）。

auto_verdict 机械口径（必要条件，非充分——故事层两独立人物须人工裁定，见 ADJUDICATIONS）：
  confirmed_mech = 最大别名互证次数 ≥2 且（ratings per_book 共书非空 或 目标实体书域
                   覆盖两 fighter 书域之并）；否则 review。

用法：python -X utf8 scripts/find_fighter_duplicates.py            # live 扫描 + 清单 TSV
      python -X utf8 scripts/find_fighter_duplicates.py --quiet    # 只打印不写 TSV
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "site" / "data"
OUT_TSV = ROOT / "kb" / "校订" / "武评同人多条目-候选.tsv"

TSV_COLS = ["name_a", "name_b", "direction", "link_alias", "link_count", "target",
            "entity_books", "shared_books", "auto_verdict", "disposition", "note"]

MIN_LINK = 2  # 确凿线：别名互证次数（任务口径：别名互证≥2 且共书）

# G1 裁定（2026-11-12）：pair(name_a|name_b，排序序) → (disposition, note)。
# fixed = 已走 alias_overrides（每条证据在案）；hold = 两独立人物留档不并（宁缺毋滥）。
ADJUDICATIONS = {
    "于承珠|承珠": (
        "fixed->E118846",
        "G1 任务书指定：registry E119135（@ 承珠）与 E118846（@ 于承珠）两标注批次归一不一致；"
        "entity-index 于承珠 alias 承珠×61；联剑 concordance registered→E118846（散花 2 次挂 E119135）；"
        "词云清洗.tsv#68 校定 merge 承珠→于承珠（既有裁定先例）"),
    "凌云凤|凌云风": (
        "fixed->E118954",
        "凤/风字形变体：tagged 散花#27 pipe 〖@凌云风|凌云凤〗；entity-index 凌云凤 alias 凌云风×24"
        "（散花5+联剑19）；E119096（@ 凌云风）仅 3 次占位"),
    "张玉虎|小虎子": (
        "fixed->E119888",
        "幼名：E119888 张玉虎 aliases 本已含 小虎子（D9 aliases 纪律已满足）；entity-index 张玉虎"
        " alias 小虎子×718（散花580+联剑138）；E118950（@ 小虎子）582 次占位"),
    "李大人|李天扬": (
        "fixed->E0219",
        "敬称：tagged 白发#8 pipe 〖@李大人|李天扬〗×4；entity-index 李天扬 alias 李大人×45（白发）；"
        "kb-events 李大人 仅白发#8（10 行）——其余书无此名"),
    "大龙头|毕擎天": (
        "fixed->E118949",
        "职衔：tagged 散花#6 pipe 〖@大龙头|毕擎天〗；entity-index 毕擎天 alias 大龙头×14（散花）；"
        "7 书内 (@,大龙头) concordance 行仅散花#30×1（毕擎天任内；#4 武振东时代大龙头非 @ 行）"),
    "石镜涵|百毒神君": (
        "fixed->E119909",
        "诨号：tagged 联剑#21/23/35 pipe 〖@百毒神君|石镜涵〗多处 + 「石镜涵…得到了百毒神君的称号」；"
        "entity-index 石镜涵 alias 百毒神君×12；E119897（@ 百毒神君）131 次占位"),
    "冯琳|冯瑛": (
        "hold(两独立人物)",
        "江湖三女侠 双生姐妹两女主（canon 两独立人物）——alias 双向互指（137/74）系标注混淆嫌疑，"
        "不可机械合并；留档待人工复核"),
    "鱼壳|鱼娘": (
        "hold(两独立人物)",
        "江湖三女侠 两人（各自独立实体 296/95 次）——鱼壳行 alias 鱼娘×6 系混淆嫌疑；留档待人工复核"),
}


def build_alias_index(entity_index_entities: list) -> dict:
    """entity-index entities → {alias: {canonical: count}}（仅 @ 人物行；纯函数）。"""
    idx: dict = {}
    for e in entity_index_entities:
        if e.get("t") != "@":
            continue
        canon = e.get("c")
        for a in e.get("aliases") or []:
            alias, count = a.get("alias"), int(a.get("count") or 0)
            if alias:
                idx.setdefault(alias, {}).setdefault(canon, 0)
                idx[alias][canon] += count
    return idx


def find_candidates(fighters, alias_index, books_of=None, entity_books=None,
                    min_link=MIN_LINK) -> list:
    """fighters 两两扫描「同一人多条目」候选（纯函数）→ 证据行列表。

    判定（机械层）：a 为 b 实体别名 / b 为 a 实体别名 / 双向互指——以 entity-index
    aliases 互指为唯一候选源（无互指不产候选，防同名不同人误报）。
    books_of：fighter → set(书)（ratings per_book 键）；entity_books：canonical → set(书)
    （entity-index b 键）。auto_verdict：confirmed_mech = 最大互证 ≥min_link 且
    （共书非空 或 目标实体书域 ⊇ 两 fighter 书域之并——跨书单实体）。
    """
    books_of = books_of or {}
    entity_books = entity_books or {}
    names = sorted(set(fighters))
    rows = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ab = (alias_index.get(a) or {}).get(b)     # b 实体行携带别名 a → a 是 b 的别名
            ba = (alias_index.get(b) or {}).get(a)     # a 实体行携带别名 b
            if not ab and not ba:
                continue
            shared = sorted((books_of.get(a) or set()) & (books_of.get(b) or set()))
            if ab and ba:
                direction, link_alias, link_count, target = "双向", f"{a}/{b}", ab + ba, f"{a}/{b}"
                union = (books_of.get(a) or set()) | (books_of.get(b) or set())
                covered = any((entity_books.get(t) or set()) >= union for t in (a, b)) if union else bool(shared)
            elif ab:
                direction, link_alias, link_count, target = f"{a}→{b}", a, ab, b
                covered = (entity_books.get(b) or set()) >= ((books_of.get(a) or set()) | (books_of.get(b) or set()))
            else:
                direction, link_alias, link_count, target = f"{b}→{a}", b, ba, a
                covered = (entity_books.get(a) or set()) >= ((books_of.get(a) or set()) | (books_of.get(b) or set()))
            verdict = ("confirmed_mech"
                       if link_count >= min_link and (shared or covered or not books_of)
                       else "review")
            disp, note = (ADJUDICATIONS.get(f"{a}|{b}") or ADJUDICATIONS.get(f"{b}|{a}")
                          or ("", ""))
            rows.append({
                "name_a": a, "name_b": b, "direction": direction,
                "link_alias": link_alias, "link_count": link_count, "target": target,
                "entity_books": sorted(entity_books.get(target) or set()),
                "shared_books": shared,
                "auto_verdict": verdict, "disposition": disp, "note": note,
            })
    return rows


def load_live():
    """live 输入：ratings fighters（名 + per_book 书域）+ entity-index @ 行（aliases/books）。"""
    r = json.loads((SITE_DATA / "ratings.json").read_text(encoding="utf-8"))
    books_of = {p["name"]: set((p.get("per_book") or {}).keys()) for p in r["players"]}
    ei = json.loads((SITE_DATA / "entity-index.json").read_text(encoding="utf-8"))["entities"]
    entity_books = {e["c"]: set((e.get("b") or {}).keys()) for e in ei if e.get("t") == "@"}
    return sorted(books_of), books_of, ei, entity_books


def write_tsv(path, rows) -> int:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TSV_COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in rows:
            out = dict(r)
            for k in ("entity_books", "shared_books"):   # 证据列表 → TSV 顿号串
                if isinstance(out.get(k), list):
                    out[k] = "、".join(out[k])
            w.writerow(out)
    return len(rows)


def main() -> int:
    quiet = "--quiet" in sys.argv[1:]
    fighters, books_of, ei, entity_books = load_live()
    alias_index = build_alias_index(ei)
    rows = find_candidates(fighters, alias_index, books_of=books_of, entity_books=entity_books)
    print(f"[dup-fighters] fighters {len(fighters)} · 候选对 {len(rows)}"
          f"（confirmed_mech {sum(1 for r in rows if r['auto_verdict'] == 'confirmed_mech')} / "
          f"review {sum(1 for r in rows if r['auto_verdict'] == 'review')}）")
    for r in rows:
        print(f"  {r['name_a']} | {r['name_b']} · {r['direction']} · 互证 {r['link_count']} · "
              f"共书 {r['shared_books'] or '无'} · {r['auto_verdict']} · {r['disposition'] or '-'}")
    if not quiet:
        write_tsv(OUT_TSV, rows)
        print(f"-> {OUT_TSV}（{len(rows)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
