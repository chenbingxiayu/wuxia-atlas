# -*- coding: utf-8 -*-
"""一次性（2026-11-05）：020-032 回两处考订修复 + registry 同步。

1. 028 回 〖@晦明禅师|镜明长老〗 → 〖@晦明禅师|岳鸣珂〗
   文内证据：028 昌钦法师认出「你是岳鸣珂，是也不是？」；该僧自述
   「我削发之前，随熊经略在关外巡边」；镜明长老为其少林师门长老
   （010 文内：岳鸣珂自述「镜明长老说我颇有慧根，曾传过我明心见性的真言」）。
2. 022/023/024/028 回 〖@皇帝|朱翊钧〗/〖@皇上|朱翊钧〗 → 管道规范名 由校
   时代证据：020 回熊廷弼已死（天启五年事）；022 回「二十岁的少年…傀儡皇帝」
   与天启帝年齿相符（万历 1620 年已 57 岁）；金标准 011-014 回天启朝人物
   直标 〖@由校〗（〖@熹宗|由校〗 管道先例）。030 回「十年之前…进贡」为
   万历朝回忆，保留 朱翊钧 不改。
   守卫：目标段若含回溯标记（十年之前/先帝/当年/万历）则跳过该处并记录。
3. registry：E0032 岳鸣珂 aliases+=晦明禅师；E0219 李天扬 aliases 调整；
   新增 昌钦法师/辛龙子/公孙雷/唐家璧。
幂等：替换目标不存在则记 0；实体 canonical 已存在则跳过。
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
TAGGED = ROOT / "tagged" / "白发魔女传"
REG = ROOT / "registry" / "entities.json"

FLASHBACK = ("十年之前", "先帝", "当年", "万历", "旧例")


def strip_markup(text: str) -> str:
    return re.sub(r"〖[^〖〗]*〗|⟦[^⟧]*⟧|〘[^〙]*〙", "", text)


def fix_tagged() -> None:
    # ---- 1) 028 晦明禅师 ----
    p = TAGGED / "028.tagged.md"
    t = io.open(p, encoding="utf-8").read()
    n = t.count("〖@晦明禅师|镜明长老〗")
    t2 = t.replace("〖@晦明禅师|镜明长老〗", "〖@晦明禅师|岳鸣珂〗")
    assert strip_markup(t2) == strip_markup(t), "strip mismatch (028 晦明)"
    io.open(p, "w", encoding="utf-8").write(t2)
    print(f"028 晦明禅师|镜明长老 → 岳鸣珂: {n} 处")

    # ---- 1b) 026 称谓连写拆分（金标准惯例：〖@名|规范〗〖#称谓〗；可重放）----
    p = TAGGED / "026.tagged.md"
    t = io.open(p, encoding="utf-8").read()
    for old, new in (("〖@青蓑师叔〗", "〖@青蓑|青蓑道人〗〖#师叔〗"),
                     ("〖@新城师兄〗", "〖@新城|虞新城〗〖#师兄〗")):
        c = t.count(old)
        if c:
            t2 = t.replace(old, new)
            assert strip_markup(t2) == strip_markup(t)
            io.open(p, "w", encoding="utf-8").write(t2)
        print(f"026 拆分 {old}: {c} 处")

    # ---- 2) 皇帝时代 ----
    total = 0
    for ch in (22, 23, 24, 28):
        p = TAGGED / f"{ch:03d}.tagged.md"
        t = io.open(p, encoding="utf-8").read()
        paras = t.split("\n\n")
        changed = 0
        for i, para in enumerate(paras):
            hits = re.findall(r"〖@(?:皇帝|皇上)[｜|]朱翊钧〗", para)
            if not hits:
                continue
            if any(k in para for k in FLASHBACK):
                print(f"  [{ch}] 段 {i} 含回溯标记，跳过 {len(hits)} 处")
                continue
            new = para.replace("〖@皇帝|朱翊钧〗", "〖@皇帝|由校〗").replace(
                "〖@皇上|朱翊钧〗", "〖@皇上|由校〗")
            assert strip_markup(new) == strip_markup(para)
            paras[i] = new
            changed += len(hits)
        if changed:
            io.open(p, "w", encoding="utf-8").write("\n\n".join(paras))
        total += changed
        print(f"0{ch} 皇帝/皇上|朱翊钧 → 由校: {changed} 处")
    print(f"皇帝时代修复合计: {total} 处")


def fix_registry() -> None:
    reg = json.load(io.open(REG, encoding="utf-8"))
    ents = reg["entities"]

    def find(canon: str):
        for e in ents:
            if e["canonical"] == canon:
                return e
        return None

    # 岳鸣珂 += 晦明禅师
    ymk = find("岳鸣珂")
    assert ymk is not None
    if "晦明禅师" not in ymk["aliases"]:
        ymk["aliases"].append("晦明禅师")
        ymk["note"] = (ymk["note"] + "；" if ymk["note"] else "") + (
            "2026-11-05 考订：028 文内证据（昌钦法师认出「你是岳鸣珂」+自述随熊经略"
            "巡边后削发），出家后法号晦明禅师；镜明长老（少林）为其师，非同一人"
            "（010 文内：岳鸣珂自述「镜明长老说我颇有慧根」）")

    # 李天扬：李钦差 剔除（E0047 已考订为另一人/存疑），李指挥 移 contextual
    lt = find("李天扬")
    if lt and "李钦差" in lt["aliases"]:
        lt["aliases"].remove("李钦差")
    if lt and "李指挥" in lt["aliases"]:
        lt["aliases"].remove("李指挥")
        lt.setdefault("contextual", []).append("李指挥")
    if lt:
        lt["note"] = (lt["note"] + "；" if lt["note"] else "") + (
            "2026-11-05：与 E0047「李钦差」（005 回，考订本名未揭示）是否同一人存疑——"
            "008 金标管道 〖@李钦差|李天扬〗 与 E0047 收口结论矛盾（管道注释不参与"
            "正文检索，疑漏），留 S-03b/考订裁定，本表暂不合并")

    # 新增：昌钦法师 / 辛龙子 / 公孙雷 / 唐家璧
    nums = [int(re.search(r"\d+", e["id"]).group()) for e in ents]
    nid = max(nums) + 1
    NEW = [
        ("昌钦法师", ["昌钦大法师", "昌钦大喇嘛"], [],
         "红衣喇嘛；028 文内与岳鸣珂（晦明禅师）相认并交手；024 为宫中护身法师"),
        ("辛龙子", [], [], "029-032 塞外线少年（晦明禅师门下线索，028 收徒段）"),
        ("公孙雷", [], [], "C24 concordance 未登记回填"),
        ("唐家璧", [], [], "C24 concordance 未登记回填"),
    ]
    added = []
    for canon, aliases, contextual, note in NEW:
        if find(canon) is None and canon not in {
            a for e in ents for a in e.get("aliases", [])
        }:
            ents.append({
                "id": f"E{nid:04d}", "type": "@", "canonical": canon,
                "aliases": aliases, "contextual": contextual,
                "sources": [], "status": "proposed", "note": note,
            })
            added.append(canon)
            nid += 1

    io.open(REG, "w", encoding="utf-8").write(
        json.dumps(reg, ensure_ascii=False, indent=2) + "\n")
    print(f"registry: 岳鸣珂+晦明禅师 / 李天扬 调整 / 新增 {added}")


if __name__ == "__main__":
    fix_tagged()
    fix_registry()
    print("done")
