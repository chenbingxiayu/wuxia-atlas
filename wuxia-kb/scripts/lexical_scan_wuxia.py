# -*- coding: utf-8 -*-
"""武侠词法分析器（SKILL_02e 主工具，只读）：jieba 分词 + 高频候选词发现 +
夹心复合实体检测 + 词性分布粗统计。

用法：
    python -X utf8 scripts/lexical_scan_wuxia.py --book 冰魄寒光剑 [--top 50]
产物：
    logs/qa/lexical_scan_<书>.md（人类可读报告；本脚本不写任何语料/登记/词表）

分析口径（SKILL_02e 武侠版 §二）：
  * 第一遍：symbols.strip_markup 剥标后 jieba 分词，词性分布 + 高频多字词
    （排除集 = registry/entities.json surfaces/aliases/canonical + wordlists/*.json 词目；
    排除集读不到时降级为空并注明）；
  * 第二遍：夹心检测两类——
      同位复指形  〖@A|B〗B          （DEF-12 单标签化对象，2026-11-06 已合并 112 处）
      父术分裂形  裸字〖☆Y〗         （需语义判定泛称/专名，仅列候选）
  * 纪律：只读。不写 tagged/、registry/、wordlists/；--apply 不存在。
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config      # noqa: E402
import symbols     # noqa: E402

import jieba      # noqa: E402
import jieba.posseg as pseg   # noqa: E402

# 白话虚词/功能词表（SKILL_02e §3.1；封闭表，不标）
FUNCTION_WORDS = set(
    "的了呢吧吗啊呀么哦嘛哇哩啦呐之乎者也便只就都被把让向 往 从 在 是 与 和 或 但 然而 于是 因为 所以 虽然 "
    "即使 如果 尽管 何况 至于 因而 从而 并且 而且 不过 可是 只是 因此 由于 关于 对于 按 照 依 凭 令 叫 请 使 "
    "将 被 让 给 替 朝 沿 沿着 随着 随着 到 至 往 向 从 自 打 由".split()
) | {"", " "}
PARA_RE = re.compile(r"^\[(\d+)\] (.*)$")
APPOSITION_RE = re.compile(r"〖@([^〖〗|]+)\|([^〖〗|]+)〗\2")
SPLIT_ART_RE = re.compile(r"([一-龥]{1,4})(〖☆[^〖〗]+〗)")


def load_exclude_set() -> tuple[set[str], str]:
    """排除集：registry surfaces/aliases/canonical + wordlists 词目。"""
    excl: set[str] = set()
    srcs = []
    reg = config.DIR_REGISTRY / "entities.json"
    if reg.exists():
        try:
            data = json.loads(io.open(reg, encoding="utf-8").read())
            ents = data.get("entities", data)
            items = ents.values() if isinstance(ents, dict) else ents
            for e in items:
                if not isinstance(e, dict):
                    continue
                for k in ("canonical", "display_canonical"):
                    v = (e.get(k) or "").strip()
                    if v:
                        excl.add(v)
                for k in ("surfaces", "aliases"):
                    for s in (e.get(k) or {}):
                        if isinstance(s, str) and s.strip():
                            excl.add(s.strip())
                        elif isinstance(s, dict):
                            v2 = (s.get("name") or "").strip()
                            if v2:
                                excl.add(v2)
            srcs.append("registry/entities.json")
        except Exception as e:                          # noqa: BLE001
            print(f"[warn] registry 解析失败，降级：{e}")
    for wl in sorted(config.DIR_WORDLISTS.glob("*.json")):
        try:
            data = json.loads(io.open(wl, encoding="utf-8").read())
        except Exception:
            continue
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, str) and v.strip():
                    excl.add(v.strip())
                elif isinstance(v, list):
                    for x in v:
                        if isinstance(x, str) and x.strip():
                            excl.add(x.strip())
                        elif isinstance(x, dict) and (x.get("name") or x.get("term") or x.get("word")):
                            excl.add((x.get("name") or x.get("term") or x.get("word")).strip())
                elif isinstance(v, dict):
                    for k2 in ("name", "term", "word", "canonical"):
                        if (v.get(k2) or "").strip():
                            excl.add(v[k2].strip())
        srcs.append(wl.name)
    return excl, " + ".join(srcs) if srcs else "空（排除集文件均缺失）"


def main() -> int:
    ap = argparse.ArgumentParser(description="武侠词法分析器（只读，SKILL_02e）")
    ap.add_argument("--book", default=config.PILOT_BOOK, help="书名（默认 %(default)s）")
    ap.add_argument("--top", type=int, default=50, help="高频候选 TOP-N（默认 50）")
    args = ap.parse_args()
    book = args.book
    d = config.DIR_TAGGED / book
    files = sorted(d.glob("*.tagged.md"))
    if not files:
        raise SystemExit(f"无 tagged：{d}")
    excl, excl_src = load_exclude_set()

    pos_counter: collections.Counter = collections.Counter()
    word_counter: collections.Counter = collections.Counter()
    apposition_hits: list[str] = []
    split_hits: list[str] = []
    split_noise = 0
    n_raw_chars = 0
    # 先收集全书 ☆ 全名（自证集：别处已作为完整单标签出现者）
    known_art: collections.Counter = collections.Counter()
    for p in files:
        for m in re.finditer(r"〖☆([^〖〗]+)〗", p.read_text(encoding="utf-8")):
            known_art[m.group(1)] += 1

    for p in files:
        text = p.read_text(encoding="utf-8")
        n_raw_chars += len(symbols.strip_markup(text))
        for m in APPOSITION_RE.finditer(text):
            apposition_hits.append(f"{p.name[:3]} {m.group(0)}")
        for m in SPLIT_ART_RE.finditer(text):
            art = re.sub(r"[〖〗☆]", "", m.group(2))
            if (m.group(1) + art) in known_art:
                split_hits.append(f"{p.name[:3]} {m.group(0)}  ←“{m.group(1)}{art}”在全书另有完整单标签 {known_art[m.group(1) + art]} 处")
            else:
                split_noise += 1
        plain = symbols.strip_markup(text)
        for words in pseg.cut(plain):
            w, flag = words.word, words.flag
            if not w or w.isspace():
                continue
            pos_counter[flag] += len(w)
            if len(w) >= 2 and w not in FUNCTION_WORDS and w not in excl:
                word_counter[w] += 1

    total_pos = sum(pos_counter.values()) or 1
    L = [f"# 词法扫描报告 ——《{book}》", "",
         f"- 文件 {len(files)} 回；剥标总字数 {n_raw_chars:,}",
         f"- 排除集来源：{excl_src}（{len(excl):,} 词条）",
         "- 纪律：本报告只读产出；候选人工审核后才进补标/词表", ""]
    L += ["## 一、词性分布（剥标全文，按字符数）", "",
          "| 词性 | 字符数 | 占比 |", "|---|---:|---:|"]
    for flag, n in pos_counter.most_common(12):
        L.append(f"| {flag} | {n:,} | {n / total_pos * 100:.1f}% |")
    L += ["", f"## 二、高频候选词 TOP-{args.top}（≥2 字、不在排除集/虚词表）", "",
          "| 词 | 次数 |", "|---|---:|"]
    for w, c in word_counter.most_common(args.top):
        L.append(f"| {w} | {c} |")
    L += ["", "## 三、夹心检测——同位复指形 〖@A|B〗B（DEF-12；2026-11-06 基线 0）", ""]
    L += [f"- {h}" for h in apposition_hits] or ["- 0 处（基线达成）"]
    L += ["", "## 四、夹心检测——父术分裂（语料自证层：裸前缀+☆内容在全书另有完整单标签）", ""]
    L += [f"- {h}" for h in split_hits] or ["- 0 处"]
    L += ["", f"（另有裸前缀+☆出现 {split_noise} 处，多为正常句法（如“的〖☆剑法〗”），未列入；需要时人工复核）", ""]
    L += ["", "## 五、复核提示", "",
          "- 高频候选中属通名/泛称的不补标（03a P3-1 泛称口径）",
          "- 候选补标走 03a 批次；新词目走 02h 词表登记", ""]

    out = config.DIR_LOGS / "qa" / f"lexical_scan_{book}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print(f"[lexical] {book}: {len(files)} 回 / 剥标 {n_raw_chars:,} 字；"
          f"候选 TOP{args.top} 详见报告；同位复指 {len(apposition_hits)} / 父术分裂自证 {len(split_hits)}（噪声 {split_noise} 未列） → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
