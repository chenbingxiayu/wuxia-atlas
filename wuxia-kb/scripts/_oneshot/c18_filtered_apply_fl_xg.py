# -*- coding: utf-8 -*-
"""C18 过滤后补标（2026-11-07 P3 批次：风雷震九州/侠骨丹心）。

依据：docs/77 §七.2 遗留（C18 未跑）；逐词人工裁决（SKILL_01g/03a D1/D2 负规则 +
书内既有标注约定双依据，docs/69 §四 / docs/54 §5 / docs/76 §四 先例）。
只对 registry/patches/<书>/*_aliases.tsv 中列入白名单的词落标；经
scan_untagged_aliases._apply_word 按原文偏移精确插入（保护区 + 剥标断言 +
令牌数守恒 + 逐回失败回滚 + 写前备份）。

裁决要点：
  * D1 称谓/描述性代称、D2 泛称概念（爹爹/武林/教主/老婆婆/少爷/大汉/皇帝/朝廷…）全剔；
  * 历史/典故名（荆轲/曹操/秦始皇/伯牙/张士诚…）剔；
  * 书内既有标注约定优先：义军/清军/官军/朝廷/虎营/镖局/镖行/大内/清廷 等 ◆ 组织词
    按既有令牌口径补标；江家/杨家 按 & 家族补标；
  * OCR 变体经管道纠偏：江海夭→江海天、大悲掸师→大悲禅师、黑煞神→秦柱尊、秀妹→钟秀；
  * 短称按书内约定 〖@短称|全名〗（海天/海哥/海儿→江海天、仲帮主→仲长统…）。

用法：python -X utf8 scripts/_oneshot/c18_filtered_apply_fl_xg.py [--dry-run]
"""
import io
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import config                      # noqa: E402
import symbols                     # noqa: E402
import scan_untagged_aliases as c18    # noqa: E402

DRY = "--dry-run" in sys.argv
BOOKS = ["风雷震九州", "侠骨丹心"]
PATCH_DIR = ROOT / "registry" / "patches"
BACKUP = ROOT / "logs" / "backup" / "c18_fl_xg_20261107"

A = "@"
FL = "风雷震九州"
XG = "侠骨丹心"
WORD_APPROVE = {
    FL: {
        # ---- 人物（本名/既有令牌约定，bare）----
        ("江海天", "江海天"): (A, "江海天"),
        ("羊吞虎", "羊吞虎"): (A, "羊吞虎"),
        ("祈圣因", "祈圣因"): (A, "祈圣因"),
        ("鹿克犀", "鹿克犀"): (A, "鹿克犀"),
        ("风从龙", "风从龙"): (A, "风从龙"),
        ("宇文雄", "宇文雄"): (A, "宇文雄"),
        ("叶慕华", "叶慕华"): (A, "叶慕华"),
        ("上官泰", "上官泰"): (A, "上官泰"),
        ("岳霆", "岳霆"): (A, "岳霆"),
        ("冷铁樵", "冷铁樵"): (A, "冷铁樵"),
        ("李大典", "李大典"): (A, "李大典"),
        ("上官纨", "上官纨"): (A, "上官纨"),
        ("李光夏", "李光夏"): (A, "李光夏"),
        ("马胜龙", "马胜龙"): (A, "马胜龙"),
        ("林道轩", "林道轩"): (A, "林道轩"),
        ("卫涣", "卫涣"): (A, "卫涣"),
        ("葛三娘", "葛三娘"): (A, "葛三娘"),
        ("华天风", "华天风"): (A, "华天风"),
        ("褚蒙", "褚蒙"): (A, "褚蒙"),
        ("褚元", "褚元"): (A, "褚元"),
        ("了因", "了因"): (A, "了因"),
        ("叶屠户", "叶屠户"): (A, "叶屠户"),
        ("甘凤池", "甘凤池"): (A, "甘凤池"),
        ("朴鼎查", "朴鼎查"): (A, "朴鼎查"),
        ("李文成", "李文成"): (A, "李文成"),
        ("谢云真", "谢云真"): (A, "谢云真"),
        ("杨仲英", "杨仲英"): (A, "杨仲英"),
        ("仲长统", "仲长统"): (A, "仲长统"),
        ("杨钲", "杨钲"): (A, "杨钲"),
        ("林清", "林清"): (A, "林清"),
        ("辛隐农", "辛隐农"): (A, "辛隐农"),
        ("梁少英", "梁少英"): (A, "梁少英"),
        ("马驰", "马驰"): (A, "马驰"),
        ("耿秀凤", "耿秀凤"): (A, "耿秀凤"),
        ("黑衣少年", "黑衣少年"): (A, "黑衣少年"),
        ("青衣汉子", "青衣汉子"): ("#", "青衣汉子"),
        ("青袍怪客", "青袍怪客"): (A, "青袍怪客"),
        # ---- 短称/OCR 纠偏（管道）----
        ("海天", "海天"): (A, "江海天"),
        ("海哥", "海哥"): (A, "江海天"),
        ("海儿", "海儿"): (A, "江海天"),
        ("仲帮主", "仲帮主"): (A, "仲长统"),
        ("江海夭", "江海夭"): (A, "江海天"),
        ("大悲掸师", "大悲掸师"): (A, "大悲禅师"),
        ("黑煞神", "黑煞神"): (A, "秦柱尊"),
        ("秀妹", "秀妹"): (A, "钟秀"),
        # ---- 组织（◆，书内既有约定）----
        ("义军", "义军"): ("◆", "义军"),
        ("清军", "清军"): ("◆", "清军"),
        ("官军", "官军"): ("#", "官军"),
        ("朝廷", "朝廷"): ("◆", "朝廷"),
        ("大内", "大内"): ("=", "大内"),
        ("虎营", "虎营"): ("◆", "虎营"),
        ("镖局", "镖局"): ("◆", "镖局"),
        ("镖行", "镖行"): ("◆", "镖行"),
        ("清廷", "清廷"): ("◆", "清廷"),
        ("密宗", "密宗"): ("◆", "密宗"),
        ("清宫", "清宫"): ("◆", "清宫"),
        ("天理教", "天理教"): ("◆", "天理教"),
        ("御林军", "御林军"): ("◆", "御林军"),
        ("巡逻队", "巡逻队"): ("◆", "巡逻队"),
        ("武当", "武当派"): ("◆", "武当"),
        ("天山派", "天山派"): ("◆", "天山派"),
        # ---- 家族（&）----
        ("江家", "江家"): ("&", "江家"),
        ("杨家", "杨家"): ("&", "杨家"),
        # ---- 地域（=，docs/72 拍板 =中国 归一）----
        ("中国", "中国"): ("=", "中国"),
    },
    XG: {
        # ---- 人物（本名/既有令牌约定，bare）----
        ("金逐流", "金逐流"): (A, "金逐流"),
        ("史红英", "史红英"): (A, "史红英"),
        ("江海天", "江海天"): (A, "江海天"),
        ("史白都", "史白都"): (A, "史白都"),
        ("仲长统", "仲长统"): (A, "仲长统"),
        ("文道庄", "文道庄"): (A, "文道庄"),
        ("文胜中", "文胜中"): (A, "文胜中"),
        ("公孙燕", "公孙燕"): (A, "公孙燕"),
        ("封妙嫦", "封妙嫦"): (A, "封妙嫦"),
        ("封子超", "封子超"): (A, "封子超"),
        ("连城虎", "连城虎"): (A, "连城虎"),
        ("何老大", "何老大"): (A, "何老大"),
        ("帅孟雄", "帅孟雄"): (A, "帅孟雄"),
        ("宫秉藩", "宫秉藩"): (A, "宫秉藩"),
        ("厉南星", "厉南星"): (A, "厉南星"),
        ("秦元浩", "秦元浩"): (A, "秦元浩"),
        ("郑雄图", "郑雄图"): (A, "郑雄图"),
        ("陈天宇", "陈天宇"): (A, "陈天宇"),
        ("公孙宏", "公孙宏"): (A, "公孙宏"),
        ("华天风", "华天风"): (A, "华天风"),
        ("金世遗", "金世遗"): (A, "金世遗"),
        ("彭巨嵘", "彭巨嵘"): (A, "彭巨嵘"),
        ("李敦", "李敦"): (A, "李敦"),
        ("上官泰", "上官泰"): (A, "上官泰"),
        ("张鹏飞", "张鹏飞"): (A, "张鹏飞"),
        ("焦老三", "焦老三"): (A, "焦磊"),
        ("青袍怪客", "青袍怪客"): (A, "青袍怪客"),
        # ---- 短称（管道）----
        ("江师兄", "江师兄"): (A, "江海天"),
        ("世遗", "世遗"): (A, "金世遗"),
        ("海天", "海天"): (A, "江海天"),
        ("海哥", "海哥"): (A, "江海天"),
        ("仲帮主", "仲帮主"): (A, "仲长统"),
        # ---- 组织（◆）----
        ("义军", "义军"): ("◆", "义军"),
        ("清兵", "清兵"): ("#", "清兵"),
        ("御林军", "御林军"): ("◆", "御林军"),
        ("镖局", "镖局"): ("◆", "镖局"),
        ("大内", "大内"): ("=", "大内"),
        ("朝廷", "朝廷"): ("◆", "朝廷"),
        ("清廷", "清廷"): ("◆", "清廷"),
        ("天魔教", "天魔教"): ("◆", "天魔教"),
        ("乐家班", "乐家班"): ("◆", "乐家班"),
        ("武当", "武当派"): ("◆", "武当"),
        # ---- 家族（&）----
        ("江家", "江家"): ("&", "江家"),
        # ---- 地域（=）----
        ("中国", "中国"): ("=", "中国"),
    },
}

# 行级守卫（子串/固定搭配）
SUFFIX_GUARD = {
    (FL, "中国"): ("话", "画"),
    (XG, "中国"): ("话", "画"),
}
PREFIX_GUARD = {}
NEIGHBOR_GUARD = {}


def _load_rows(book: str):
    rows = []
    for f in sorted((PATCH_DIR / book).glob("*_aliases.tsv")):
        for ln in io.open(f, encoding="utf-8").read().split("\n")[1:]:
            if not ln.strip():
                continue
            c = ln.split("\t")
            if len(c) >= 8:
                rows.append({"chapter": c[0], "canonical": c[1], "word": c[2],
                             "pos": c[3], "context": c[6]})
    return rows


def main():
    total = {"approve": 0, "skip_word": 0, "skip_row": 0, "inserted": 0,
             "rolled_back": []}
    for book in BOOKS:
        table = WORD_APPROVE.get(book, {})
        rows = _load_rows(book)
        plan, skip_word, skip_row = [], 0, 0
        for r in rows:
            key = (r["word"], r["canonical"])
            guard = SUFFIX_GUARD.get((book, r["word"]))
            if guard:
                i = r["context"].find(r["word"])
                tail = r["context"][i + len(r["word"]):][:2] if i >= 0 else ""
                if any(tail.startswith(g[:2]) for g in guard):
                    skip_row += 1
                    continue
            pguard = PREFIX_GUARD.get((book, r["word"]))
            if pguard:
                i = r["context"].find(r["word"])
                head = r["context"][max(0, i - 3):i] if i >= 0 else ""
                if any(head.endswith(g) for g in pguard):
                    skip_row += 1
                    continue
            nguard = NEIGHBOR_GUARD.get((book, r["word"]))
            if nguard and any(g in r["context"] for g in nguard):
                skip_row += 1
                continue
            if key in table:
                code, canon = table[key]
                plan.append(dict(r, code=code, canon=canon))
            else:
                skip_word += 1
        total["approve"] += len(plan)
        total["skip_word"] += skip_word
        total["skip_row"] += skip_row
        print(f"[{book}] 建议 {len(rows)} → 批准 {len(plan)} / "
              f"词级剔除 {skip_word} / 行级剔除 {skip_row}")
        if DRY:
            by_w = defaultdict(int)
            for p in plan:
                by_w[(p["word"], p["canon"], p["code"])] += 1
            for (w, c, k), n in sorted(by_w.items(), key=lambda x: -x[1]):
                print(f"   + {w}→{c} [{k}] ×{n}")
            continue
        by_ch = defaultdict(list)
        for p in plan:
            by_ch[p["chapter"]].append(p)
        for ch, rs in sorted(by_ch.items()):
            fpath = config.tagged_path(book, int(ch))
            old = io.open(fpath, encoding="utf-8").read()
            text = old
            n_ins = 0
            for p in sorted(rs, key=lambda x: -int(x["pos"])):
                text, n = c18._apply_word(text, p["word"], p["code"], p["canon"],
                                          pos=int(p["pos"]))
                n_ins += n
            old_tokens = len(list(symbols.TOKEN_RE.finditer(old)))
            new_tokens = len(list(symbols.TOKEN_RE.finditer(text)))
            ok = (symbols.strip_markup(text) == symbols.strip_markup(old)
                  and new_tokens - old_tokens == n_ins)
            print(f"   {ch}: 插入 {n_ins}/{len(rs)} {'OK' if ok else 'FAIL→回滚'}")
            if ok and n_ins:
                BACKUP.mkdir(parents=True, exist_ok=True)
                bdir = BACKUP / book
                bdir.mkdir(exist_ok=True)
                if not (bdir / f"{ch}.tagged.md").exists():
                    shutil.copy2(fpath, bdir / f"{ch}.tagged.md")
                io.open(fpath, "w", encoding="utf-8", newline="\n").write(text)
                total["inserted"] += n_ins
            elif ok:
                pass
            else:
                total["rolled_back"].append(f"{book}/{ch}")
    print(f"\n合计: 批准 {total['approve']} / 落盘 {total['inserted']} / "
          f"词级剔除 {total['skip_word']} / 行级剔除 {total['skip_row']} / "
          f"回滚 {total['rolled_back'] or '无'}")


if __name__ == "__main__":
    main()
