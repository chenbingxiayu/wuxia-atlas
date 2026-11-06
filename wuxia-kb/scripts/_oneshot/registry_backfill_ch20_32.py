# -*- coding: utf-8 -*-
"""一次性：从 C24 concordance 回填 020-032 相关未登记 @ 人物到 registry/entities.json。

依据：
  - registry/concordance/白发魔女传.json 的 unregistered @ 实体（出现在第 20-32 回、total≥25）；
  - 001-019 金标准 + 020-032 机器 tagged 中实际使用的 @ 管道对（别名/称谓佐证）；
  - 人工核定表（下方 CURATED）：只收「名形式」别名（绰号/省称），纯关系称谓入 contextual，
    时代依赖与泛称（皇帝/贵妃/大人 等）一律不收。
幂等：canonical 已存在（作为 canonical 或他人 alias）则跳过。
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "registry" / "entities.json"
CONC = ROOT / "registry" / "concordance" / "白发魔女传.json"
TAGGED = ROOT / "tagged" / "白发魔女传"

# 人工核定：canonical -> (aliases 名形式, contextual 称谓, note)
CURATED = {
    "慕容冲": ([], ["慕容总管"], "卫士统领/都头级头目（020 文内称慕容总管）"),
    "白石道人": (["白石"], [], "武当四长老之一（026 文内：黄叶白石红云青蓑四个长老）"),
    "公孙大娘": (["红花鬼母"], [], "绰号红花鬼母；金独异之妻（020 文内多次连称）"),
    "金独异": ([], ["金老前辈", "金老大", "金老爹"], "红花鬼母之夫（020 文内称谓）"),
    "客娉婷": ([], [], ""),
    "黄叶道人": (["黄叶"], [], "武当四长老之一（026 文内并称）"),
    "李天扬": ([], [], ""),
    "镜明长老": ([], [], ""),
    "何绿华": ([], [], ""),
    "杨涟": ([], [], "史实人物（左副都御史）"),
    "客氏": ([], [], ""),
    "连城虎": ([], [], ""),
    "唐努": ([], [], ""),
    "李申时": ([], [], ""),
    "龙达三": ([], [], ""),
    "龙啸云": ([], [], ""),
    "何萼华": ([], [], ""),
    "成章五": ([], [], ""),
    "霍元仲": ([], [], ""),
    "袁崇焕": ([], [], "史实人物"),
    "天德上人": ([], [], ""),
    "神大元": (["神老大"], [], ""),
    "由校": ([], [], "即天启帝（明熹宗朱由校）"),
    "李自成": ([], [], "史实人物"),
    "李岩": ([], [], ""),
    "罗铁臂": ([], [], ""),
    "朱宝椿": ([], [], "绰号火灵猿（001 文内）"),
    "归有章": ([], [], ""),
    "天龙上人": ([], [], ""),
    "哈川": ([], [], ""),
    "巴龙": ([], [], ""),
    "红娘子": ([], [], ""),
    "神一元": ([], [], ""),
    "虞新城": ([], [], ""),
    "杜明忠": (["明忠"], [], ""),
    "飞红巾": ([], [], "回疆女杰（030/032 塞外线）"),
    "辛五": ([], [], ""),
    "孟萨思": ([], [], ""),
    "青蓑道人": (["青蓑"], [], "武当四长老之一（026 文内并称）"),
}

# 追加到既有实体的别名（canonical -> aliases to add）
ALIAS_APPEND = {
    "练霓裳": ["白发魔女"],   # 020-032 管道 〖@白发魔女|练霓裳〗×88
}


def pipe_pairs():
    pairs: dict[str, set[str]] = {}
    for n in list(range(1, 33)):
        t = io.open(TAGGED / f"{n:03d}.tagged.md", encoding="utf-8").read()
        for m in re.finditer(r"〖@([^〖〗]+)〗", t):
            body = m.group(1)
            for sep in ("｜", "|"):
                if sep in body:
                    a, c = body.split(sep, 1)
                    pairs.setdefault(c.strip(), set()).add(a.strip())
    return pairs


def main() -> int:
    reg = json.load(io.open(REG, encoding="utf-8"))
    conc = json.load(io.open(CONC, encoding="utf-8"))
    pairs = pipe_pairs()

    existing_canon = {e["canonical"] for e in reg["entities"]}
    existing_alias = {
        a for e in reg["entities"] for a in e.get("aliases", [])
    }

    cand = {}
    for e in conc["unregistered"]:
        if e["type"] != "@" or e["total"] < 25:
            continue
        chs = [c["chapter"] for c in e.get("chapter_counts", [])]
        if not any(20 <= c <= 32 for c in chs):
            continue
        cand[e["canonical"]] = chs

    # id 分配：从现有最大数字 +1 起
    nums = [int(re.search(r"\d+", e["id"]).group()) for e in reg["entities"]]
    next_id = max(nums) + 1

    added, skipped = [], []
    for canon, chs in sorted(cand.items()):
        if canon in existing_canon or canon in existing_alias:
            skipped.append((canon, "已登记"))
            continue
        cur = CURATED.get(canon)
        if cur is None:
            skipped.append((canon, "不在人工核定表"))
            continue
        aliases, contextual, note = cur
        # 管道对佐证补充（只收名形式：长度≥2 且非纯关系后缀）
        for a in sorted(pairs.get(canon, [])):
            if len(a) >= 2 and a not in aliases and a not in contextual:
                if re.search(r"(兄|弟|姐|妹|叔|伯|公公|姑娘|小姐|前辈|老爷|大人)$", a):
                    continue
                aliases.append(a)
        ent = {
            "id": f"E{next_id:04d}",
            "type": "@",
            "canonical": canon,
            "aliases": sorted(set(aliases)),
            "contextual": sorted(set(contextual)),
            "sources": [f"{c:03d}" for c in sorted(set(chs))[:4]],
            "status": "proposed",
            "note": note or f"C24 concordance 未登记回填（首现 0{sorted(set(chs))[0]} 回）",
        }
        next_id += 1
        reg["entities"].append(ent)
        added.append(canon)

    # 追加别名（幂等）
    appended = []
    for e in reg["entities"]:
        if e["canonical"] in ALIAS_APPEND:
            for a in ALIAS_APPEND[e["canonical"]]:
                if a not in e.get("aliases", []) and a != e["canonical"]:
                    e.setdefault("aliases", []).append(a)
                    appended.append((e["canonical"], a))

    # 冲突自检：同一 surface 不得指向两个 canonical（名形式）
    owner: dict[str, str] = {}
    conflict = []
    for e in reg["entities"]:
        for s in [e["canonical"], *e.get("aliases", [])]:
            if s in owner and owner[s] != e["canonical"]:
                conflict.append((s, owner[s], e["canonical"]))
            owner[s] = e["canonical"]

    io.open(REG, "w", encoding="utf-8").write(
        json.dumps(reg, ensure_ascii=False, indent=2) + "\n")
    print(f"added={len(added)}  appended_alias={len(appended)}  skipped={len(skipped)}")
    print("added:", ", ".join(added))
    print("appended:", appended)
    if skipped:
        print("skipped:", skipped[:10], "..." if len(skipped) > 10 else "")
    if conflict:
        print("!! surface conflicts:", conflict)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
