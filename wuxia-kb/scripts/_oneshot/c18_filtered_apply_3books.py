# -*- coding: utf-8 -*-
"""C18 过滤后补标（2026-11-06 复核批次：江湖三女侠/塞外奇侠传/冰魄寒光剑）。

依据：逐词人工裁决（SKILL_01g/03a D1/D2/负规则 + 书内既有管道约定），
对 registry/patches/<书>/*_aliases.tsv 过滤后经 scan_untagged_aliases.do_apply
落盘（pos 精确插入 + 保护区 + 剥标断言 + 失败回滚）。

过滤规则（word 级白名单 + 行级黑名单 + 同义行守卫 + 覆写）：
  APPROVE  按 (word, canonical) 收录；可带 override: canonical/type 覆写。
  SKIP_WORDS  全剔除（D1 称谓/泛称/误报/书级约定不标）。
  SKIP_ROWS   (chapter, pos, word) 行级剔除（回末套语/年号/二世/底本乱序等）。
  EPEXE_GUARD 前文紧邻 `〖@X|word〗` 的同位行守卫（幂等安全网）。

用法：python -X utf8 scripts/_oneshot/c18_filtered_apply_3books.py [--dry-run]
"""
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import scan_untagged_aliases as c18  # noqa: E402

DRY = "--dry-run" in sys.argv
OUT_DIR = ROOT / "logs" / "qa" / "c18_filtered_20261106"

# ---- 词级裁决表 -------------------------------------------------------------
APPROVE = {
    "江湖三女侠": {
        ("琳丫头", "冯琳"): {},
        ("琳妹", "冯琳"): {},
        ("阿琳", "冯琳"): {},
        ("唐家", "唐家"): {},
        ("无住禅师", "无住禅师"): {},
        ("辛弃疾", "辛弃疾"): {},
        ("大内", "大内"): {"type": "地点"},
        ("清宫", "清宫"): {},
        ("明朝", "明朝"): {},
        ("清朝", "清朝"): {},
        ("清军", "清军"): {},
        ("天山", "天山"): {},
        ("爱新觉罗氏", "爱新觉罗氏"): {},
        ("无极剑", "无极剑"): {},
        ("桂华生", "桂华生"): {},
        ("李后主", "李后主"): {},
        ("雍正", "胤禛"): {"canonical": "允祯"},
        ("康熙", "玄烨"): {"canonical": "康熙"},
        ("龙大哥", "龙啸云"): {},
        ("张大人", "张承斌"): {},
        ("杨钟英", "杨仲英"): {},
    },
    "塞外奇侠传": {
        ("清兵", "清兵"): {},
        ("清军", "清军"): {},
        ("满洲", "满洲"): {},
        ("满清", "满清"): {},
        ("清廷", "清廷"): {},
        ("明朝", "明朝"): {},
        ("天蒙", "张天蒙"): {"canonical": "天蒙"},
        ("塔山族", "塔山族"): {},
        ("罗布族", "罗布族"): {},
        ("堪恰族", "堪恰族"): {},
        ("喀达尔族", "喀达尔族"): {},
        ("明慧", "纳兰明慧"): {},
        ("昭南", "楚昭南"): {},
        ("天龙禅师", "天龙禅师"): {},
        ("唐努", "唐努"): {},
        ("李闯王", "李闯王"): {},
        ("黄叶", "黄叶道人"): {},
        ("白石", "白石道人"): {},
        ("杨师兄", "杨云骢"): {},
        ("宝珠", "易兰珠"): {},
    },
    "冰魄寒光剑": {
        ("中国", "中国"): {"type": "地点"},
        ("桂华生", "桂华生"): {},
        ("御林军", "御林军"): {},
        ("达赖", "达赖活佛"): {},
        ("班禅", "班禅"): {},
        ("易兰珠", "易兰珠"): {},
        ("雍正", "胤禛"): {"canonical": "雍正"},
        ("晦明禅师", "岳鸣珂"): {"canonical": "晦明禅师"},
    },
}

# 全词剔除（D1 称谓 / D2 临时泛称 / 子串误报 / 多义误报 / 书级约定不标）
SKIP_WORDS = {
    "武林", "大军", "官兵", "贝勒", "太后", "老和尚", "老公婆", "老婆婆",
    "红衣喇嘛", "神医", "神医国手", "公子", "哥哥", "大哥", "龙大哥" if False else "",
    "王妃", "于中", "悟性", "定国", "通明", "珊瑚", "宝珠" if False else "",
    "洪涛", "冒姐姐", "明珠", "纳兰", "允禔", "允禵", "达摩", "凌未风", "周青",
    "齐真君", "杨仲英", "铁掌神弹", "铁拿神弹", "杨大哥", "冯琳", "冯瑛",
    "易兰珠" if False else "", "天山" if False else "",
}
SKIP_WORDS = {w for w in SKIP_WORDS if w}

# 行级剔除：(chapter, pos, word)——chapter 与 TSV 一致（三位零填充）
SKIP_ROWS = {
    ("江湖三女侠", "016", 9134, "天山"),     # 天山一派
    ("江湖三女侠", "016", 9517, "天山"),     # 天山门下
    ("江湖三女侠", "029", 9439, "天山"),     # 天山一派的传人
    ("江湖三女侠", "029", 9482, "天山"),     # 天山各人的关系
    ("江湖三女侠", "029", 9970, "天山"),     # 天山+〖☆剑法〗分裂形
    ("江湖三女侠", "031", 16897, "天山"),    # 天山一派
    ("江湖三女侠", "036", 4891, "天山"),     # 天山双剑
    ("江湖三女侠", "037", 11900, "天山"),    # 天山+〖☆剑法〗
    ("江湖三女侠", "037", 12527, "天山"),    # 天山+〖☆剑法〗
    ("江湖三女侠", "044", 8372, "天山"),     # 天山一派
    ("江湖三女侠", "046", 7347, "天山"),     # 天山一派
    ("江湖三女侠", "038", 7004, "明朝"),     # 明朝(=明天早上)
    ("江湖三女侠", "038", 16973, "明朝"),    # 明朝(=明天早上)
    ("江湖三女侠", "023", 11763, "雍正"),    # 年号“雍正”
    ("冰魄寒光剑", "005", 5121, "达赖"),     # 达赖二世
    ("冰魄寒光剑", "008", 7678, "班禅"),     # 底本乱序“达班禅赖活佛”
    ("冰魄寒光剑", "003", 2141, "天山"),     # 天山女侠
    ("冰魄寒光剑", "003", 2150, "天山"),     # 天山七剑
}

EPEXE_RE = re.compile(r"〖@[^〗|]*\|" + r"([^〗|]*)〗$")


def keep_row(book, ch, row, raw_line):
    word, canonical, pos = row["word"], row["canonical"], row["pos"]
    if (word, canonical) not in APPROVE.get(book, {}):
        return None
    if (book, ch, pos, word) in SKIP_ROWS or (book, ch, None, word) in SKIP_ROWS:
        return None
    # 同位守卫：紧邻前文 〖@X|word〗 结尾 → 同位复指，跳过
    m = EPEXE_RE.search(raw_line[:raw_line.find("\t") if "\t" in raw_line else len(raw_line)])
    return row


def main():
    total_kept = total_dropped = 0
    report = []
    for book, rules in APPROVE.items():
        tsv_paths = sorted((ROOT / "registry" / "patches" / book).glob("*_aliases.tsv"))
        out_book = OUT_DIR / book
        out_book.mkdir(parents=True, exist_ok=True)
        kept_paths = []
        for tsv in tsv_paths:
            lines = io.open(tsv, encoding="utf-8").read().splitlines()
            header, body = lines[0], lines[1:]
            out_lines = [header]
            for line in body:
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 8:
                    continue
                canonical, word, pos, etype = parts[1], parts[2], parts[3], parts[7]
                ov = rules.get((word, canonical))
                if ov is None:
                    total_dropped += 1
                    continue
                key = (book, parts[0], int(pos) if pos.isdigit() else None, word)
                if key in SKIP_ROWS or (book, parts[0], None, word) in SKIP_ROWS:
                    total_dropped += 1
                    continue
                # 同位守卫：上下文列末尾即 `〖@X|word〗`
                ctx = parts[6]
                if re.search(r"〖@[^〗|]*\|" + re.escape(word) + r"〗$", ctx):
                    total_dropped += 1
                    report.append(f"  [同位跳过] {book} {parts[0]} {word} pos={pos}")
                    continue
                if "canonical" in ov:
                    parts[1] = ov["canonical"]
                if "type" in ov:
                    parts[7] = ov["type"]
                out_lines.append("\t".join(parts))
                total_kept += 1
            if len(out_lines) > 1:
                outp = out_book / tsv.name
                io.open(outp, "w", encoding="utf-8", newline="\n").write("\n".join(out_lines) + "\n")
                kept_paths.append(outp)
        n_rows = sum(len(io.open(p, encoding="utf-8").read().splitlines()) - 1 for p in kept_paths)
        print(f"[{book}] 过滤后 {len(kept_paths)} 个 TSV / {n_rows} 行")
        if not DRY and n_rows:
            stats = c18.do_apply(book, kept_paths, known_words=None)
            print(f"  --apply：{stats['chapters']} 回 / 插入 {stats['inserted']}；回滚 {stats['rolled_back'] or '无'}")
    print(f"合计保留 {total_kept} 行 / 剔除 {total_dropped} 行"
          f"{'（dry-run：未写 tagged）' if DRY else ''}")
    if report:
        print("同位守卫明细：")
        for r in report:
            print(r)


if __name__ == "__main__":
    main()
