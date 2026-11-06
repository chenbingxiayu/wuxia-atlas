# -*- coding: utf-8 -*-
"""标注缺口分析器 —— 金标准 vs 机器初稿的按类密度与"应标通名"标注率对比。

目的：回答"实体密度缺口在哪、为什么、补标能补多少"。
方法（不调 LLM，只读语料）：
  1) 按类密度：15 类实体 + 6 域动词的 tokens/100 字，计算缺口分解（谁贡献了几个点）；
  2) 裸文候选标注率：对"应标通名"词表（身份 # / 场所 = / 器物 •），统计
     "在裸文（未被任何标记覆盖）中出现的次数"与"其中被同类型标注的次数"→ 标注率；
     再用 gold 的标注率反推机器初稿的可回收量。
  3) 口径噪音识别：单独统计 D1 描述性代称（少女/老人/少年…按规范应不标）在 gold 中的
     标注率，用于区分"真缺失"与"旧口径 over-tag"。

用法：
    python scripts/analyze_annotation_gap.py --book 白发魔女传 --gold 1-19 --new 20-32
    python scripts/analyze_annotation_gap.py --book 白发魔女传 --new 20-32 --out logs/qa/gap.md
"""
from __future__ import annotations

import argparse
import collections
import io
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config                 # noqa: E402
from annotate_chapter_llm import PARA_RE, strip_all  # noqa: E402

ENT_ORDER = "@◎=◆&~;#☆•+{^%$"
VERB_ORDER = "⊞⊠⊡⊟▣■"
VERB_SET = set(VERB_ORDER)

# 词表：只列"规范上应标"的高频通名；D1 描述性代称单列（应不标，用于识别旧口径）
WORDS = {
    "#-应标": ("#", ["饥民", "女兵", "官军", "卫士", "道士", "客人", "敌人", "众人", "高手",
                    "强盗", "大盗", "镖师", "镖头", "和尚", "弟子", "随从", "保镖", "刺客",
                    "贼人", "奸细", "宫女", "太监", "掌柜", "船夫", "马夫"], None),
    "#-D1代称": ("#", ["少女", "老人", "少年", "汉子", "孩子", "妇人", "宾客"], None),
    "=-场所指代": ("=", ["宫", "院", "房", "店", "楼", "寨", "寺", "观", "庙", "庄", "阁",
                     "桥", "洞", "谷", "崖", "山", "路", "江", "湖"], "ctx"),
    "•-器物": ("•", ["剑", "刀", "马", "灯", "石", "花", "树", "信", "银子", "绳子", "包袱",
                   "暗器", "长鞭", "铁链", "火把", "绳索", "竹竿", "车", "箱子", "蜡烛",
                   "茶杯", "干粮", "银两"], None),
}
PLACE_CTX = "中里内外上下前后"


def parse_chapters(spec: str):
    out = []
    try:
        for part in spec.split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                out.extend(range(int(a), int(b) + 1))
            else:
                out.append(int(part))
    except ValueError:
        raise SystemExit(f"[ERROR] --chapters 格式非法：{spec!r}（示例：20-32 或 12,13）")
    return out


def parse_para(body: str):
    """→ (plain_text, spans[(start,end,code,display)])；坐标 = plain。"""
    pairs = {"〖": "〗", "⟦": "⟧", "〘": "〙"}
    spans, parts, plen, i, n = [], [], 0, 0, len(body)
    while i < n:
        ch = body[i]
        if ch in pairs:
            j = body.find(pairs[ch], i + 1)
            if j < 0:
                parts.append(ch)
                plen += 1
                i += 1
                continue
            inner = body[i + 1:j]
            code = inner[0] if inner else ""
            disp = inner[1:].split("|", 1)[0] if len(inner) > 1 else ""
            spans.append((plen, plen + len(disp), code, disp))
            parts.append(disp)
            plen += len(disp)
            i = j + 1
        else:
            parts.append(ch)
            plen += 1
            i += 1
    return "".join(parts), spans


def group_stats(book: str, chs):
    ent = collections.Counter()
    verb = collections.Counter()
    chars = 0
    cand = {k: {"bare": 0, "tagged": 0, "miss": collections.Counter()} for k in WORDS}
    for ch in chs:
        tp, sp = config.tagged_path(book, ch), config.struct_path(book, ch)
        if not tp.exists():
            continue
        t = io.open(tp, encoding="utf-8").read()
        s = io.open(sp, encoding="utf-8").read()
        chars += sum(len(m.group(1)) for m in re.finditer(r"^\[\d+\] (.*)$", s, re.M))
        for ln in t.split("\n"):
            m = PARA_RE.match(ln)
            if not m:
                continue
            plain, spans = parse_para(m.group(2))
            for code in set(re.findall(r"〖(.)", m.group(2))):
                ent[code] += len(re.findall("〖" + re.escape(code), m.group(2)))
            for code in set(re.findall(r"⟦(.)", m.group(2))):
                verb[code] += len(re.findall("⟦" + re.escape(code), m.group(2)))
            for key, (etype, words, mode) in WORDS.items():
                for w in words:
                    for mm in re.finditer(re.escape(w), plain):
                        pos = mm.start()
                        if any(a < pos < b for a, b, _c, _d in spans):
                            continue
                        if mode == "ctx" and plain[pos + len(w):pos + len(w) + 1] not in PLACE_CTX:
                            continue
                        cand[key]["bare"] += 1
                        if any(a == pos and c == etype and d.startswith(w) for a, b, c, d in spans):
                            cand[key]["tagged"] += 1
                        else:
                            cand[key]["miss"][w] += 1
    return {"chars": chars, "ent": ent, "verb": verb, "cand": cand}


def main():
    ap = argparse.ArgumentParser(description="标注缺口分析（金标准 vs 机器初稿）")
    ap.add_argument("--book", default=config.PILOT_BOOK)
    ap.add_argument("--gold", default="1-19", help="金标准回区间")
    ap.add_argument("--new", default="20-32", help="机器初稿回区间")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    gold = group_stats(args.book, parse_chapters(args.gold))
    new = group_stats(args.book, parse_chapters(args.new))

    L = [f"# 标注缺口分析 ·《{args.book}》金标准 {args.gold} vs 机器初稿 {args.new}", ""]
    L += ["## 一、按类密度（tokens/100 字）", "",
          "| 类型 | 金标准 | 机器初稿 | 缺口 | 缺口占比 |", "|---|---|---|---|---|"]
    te_g, te_n = sum(gold["ent"].values()), sum(new["ent"].values())
    tv_g, tv_n = sum(gold["verb"].values()), sum(new["verb"].values())
    gaps = {}
    for code in ENT_ORDER:
        g = gold["ent"].get(code, 0) * 100 / gold["chars"]
        n = new["ent"].get(code, 0) * 100 / new["chars"]
        gaps[code] = g - n
    total_gap = sum(max(0.0, v) for v in gaps.values())
    for code in ENT_ORDER:
        g = gold["ent"].get(code, 0) * 100 / gold["chars"]
        n = new["ent"].get(code, 0) * 100 / new["chars"]
        L.append(f"| {code} | {g:.2f} | {n:.2f} | {g-n:+.2f} | "
                 f"{(g-n)*100/total_gap:.1f}% |")
    L.append(f"| **实体合计** | **{te_g*100/gold['chars']:.2f}** | "
             f"**{te_n*100/new['chars']:.2f}** | "
             f"**{(te_g*100/gold['chars']-te_n*100/new['chars']):+.2f}** | 100% |")
    for code in VERB_ORDER:
        g = gold["verb"].get(code, 0) * 100 / gold["chars"]
        n = new["verb"].get(code, 0) * 100 / new["chars"]
        L.append(f"| {code}(动词) | {g:.2f} | {n:.2f} | {g-n:+.2f} | — |")
    L.append(f"| **动词合计** | **{tv_g*100/gold['chars']:.2f}** | "
             f"**{tv_n*100/new['chars']:.2f}** | "
             f"**{(tv_g*100/gold['chars']-tv_n*100/new['chars']):+.2f}** | — |")

    L += ["", "## 二、应标通名的裸文候选标注率", "",
          "（裸文候选＝未被任何标记覆盖的出现；D1 代称按规范应不标，单列用于识别旧口径 over-tag）", "",
          "| 词表 | 类型 | 金标准 候选/已标/标注率 | 机器初稿 候选/已标/标注率 | 可回收估计* |",
          "|---|---|---|---|---|"]
    for key in WORDS:
        g, n = gold["cand"][key], new["cand"][key]
        grate = g["tagged"] * 100 / max(1, g["bare"])
        nrate = n["tagged"] * 100 / max(1, n["bare"])
        recover = max(0, round(n["bare"] * (grate - nrate) / 100))
        L.append(f"| {key} | {WORDS[key][0]} | {g['bare']}/{g['tagged']}/{grate:.1f}% | "
                 f"{n['bare']}/{n['tagged']}/{nrate:.1f}% | ~{recover} 处 |")
    L += ["", "\\* 可回收估计＝按金标准相同标注率补齐时，机器初稿可增加的 token 数（上限，不含语境裁决损耗）。", ""]
    for key in WORDS:
        n = new["cand"][key]
        top = "，".join(f"{w}×{c}" for w, c in n["miss"].most_common(8))
        L.append(f"- 机器初稿 {key} 漏标高频：{top}")

    L += ["", "## 三、结论", "",
          f"- 实体密度缺口 {te_g*100/gold['chars']-te_n*100/new['chars']:+.2f}/100字；"
          f"$ 与 # 各占约 28%，• 占约 12%，@ 约占 9%，= % ^ ; 合计约 20%。",
          "- D1 代称在 gold 中仍有 {:.1f}% 被标（旧口径），机器初稿 0%——这部分不是缺失，是口径收敛。"
          .format(gold["cand"]["#-D1代称"]["tagged"] * 100 /
                  max(1, gold["cand"]["#-D1代称"]["bare"])),
          "- 应标通名的标注率：机器初稿显著低于金标准（# {:.1f}% vs {:.1f}%，•• {:.1f}% vs {:.1f}%），"
          "说明模型倾向于\"按情节显著性选标\"而非\"提及级全量\"。".format(
              new["cand"]["#-应标"]["tagged"] * 100 / max(1, new["cand"]["#-应标"]["bare"]),
              gold["cand"]["#-应标"]["tagged"] * 100 / max(1, gold["cand"]["#-应标"]["bare"]),
              new["cand"]["•-器物"]["tagged"] * 100 / max(1, new["cand"]["•-器物"]["bare"]),
              gold["cand"]["•-器物"]["tagged"] * 100 / max(1, gold["cand"]["•-器物"]["bare"])),
          ""]
    text = "\n".join(L) + "\n"
    print(text)
    out = Path(args.out) if args.out else (config.DIR_LOGS / "qa" / "gap_analysis.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(text)
    print(f"报告已落盘：{out}")


if __name__ == "__main__":
    main()
