# -*- coding: utf-8 -*-
"""C18 过滤后补标（2026-11-06 复核批次：还剑奇情录/萍踪侠影录/散花女侠）。

依据：逐词人工裁决（SKILL_01g/03a D1/D2 负规则 + 书内既有管道约定，docs/54 §5 先例），
对 registry/patches/<书>/*_aliases.tsv 过滤后经 scan_untagged_aliases._apply_word
落盘（pos 精确插入 + 保护区 + 剥标断言 + 逐回失败回滚）。

裁决口径（docs/69 §四）：
  WORD_APPROVE     (word, tsv_canonical) → (类型码, canonical 覆写)。
                   书内约定优先于 registry（宝珠→云夫人、龙某→龙腾、张大人→张风府）。
  SPAN_ROWS        词为更长群体实体前缀时整段替换（还剑 007 武当五老×9 → 〖◎武当五老〗，
                   与书内 〖◎武当五老〗 群体标注同形）。
  CONTEXT_REQUIRE  行级语境前置条件（散花 江南 仅收「义军」行，诗行比喻剔除）。
  SUFFIX_GUARD     行级后缀守卫（中国话/中国画 语言艺术义；武当一派 派生词）。
  未收录词全剔除   D1 称谓（哥哥/大哥/公子/皇帝/皇上/公主/国王/大汗/张大人[萍踪]…）、
                   D2 泛称（大军/官兵）、描述性代称（白衣少年/老婆婆/老和尚/中年美妇）、
                   跨书噪声别名（定国/彩凤/明珠/黄叶/谢女侠…）、词表未决（武林/镖行/镖局）、
                   同位复指防形（太祖〖@朱元璋〗前缀行）、比喻（阎罗王/黑煞神/人妖）。

用法：python -X utf8 scripts/_oneshot/c18_filtered_apply_hps.py [--dry-run]
"""
import io
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
BOOKS = ["还剑奇情录", "萍踪侠影录", "散花女侠"]
PATCH_DIR = ROOT / "registry" / "patches"

# ---- 词级白名单（未收录即剔除） ---------------------------------------------
WORD_APPROVE = {
    "还剑奇情录": {
        ("宝珠", "易兰珠"): ("@", "云夫人"),   # 书内证据：石天铎称云夫人"宝珠"（004/006）
        ("明朝", "明朝"): ("◆", "明朝"),
        ("朝廷", "朝廷"): ("◆", "朝廷"),
        ("大内", "大内"): ("=", "大内"),
        ("江南", "江南"): ("=", "江南"),
    },
    "萍踪侠影录": {
        ("中国", "中国"): ("=", "中国"),       # 书内 =中国×46 主形（docs/54 遗留#5 跨书类型未决，从书内多数）
        ("明朝", "明朝"): ("◆", "明朝"),
        ("朝廷", "朝廷"): ("◆", "朝廷"),
        ("天朝", "天朝"): ("◆", "天朝"),
        ("御林军", "御林军"): ("◆", "御林军"),
        ("铁拐", "铁拐"): ("•", "铁拐"),       # 器物（蒙面人兵器，003 实指）
        ("石家", "石家"): ("&", "石家"),       # 书内 &石家×7（家族世系，docs/54 &唐家/&沐家 同例）
        ("诸葛武侯", "诸葛武侯"): ("@", "诸葛武侯"),
        ("西藏", "西藏"): ("=", "西藏"),
        ("江南", "江南"): ("=", "江南"),
    },
    "散花女侠": {
        ("中国", "中国"): ("=", "中国"),
        ("明朝", "明朝"): ("◆", "明朝"),
        ("朝廷", "朝廷"): ("◆", "朝廷"),
        ("天朝", "天朝"): ("◆", "天朝"),
        ("大内", "大内"): ("=", "大内"),
        ("御林军", "御林军"): ("◆", "御林军"),
        ("天山", "天山"): ("=", "天山"),       # 书内 =天山×17
        ("西藏", "西藏"): ("=", "西藏"),
        ("张大人", "张承斌"): ("@", "张风府"),  # 书内唯一管道 〖@张大人|张风府〗×22（registry 张承斌为江湖书噪声）
        ("龙某", "龙灵矫"): ("@", "龙腾"),      # 书内证据：032 〖@龙镖头|龙腾〗×6（registry 龙灵矫为跨书噪声）
    },
}

# ---- 行级整段替换：(书, 回) → [(TSV pos, 长词, 类型码, canonical)] ----------
SPAN_ROWS = defaultdict(list)
for _pos in (7760, 7813, 7841, 8110, 8342, 8441, 8569, 8633, 8795):
    SPAN_ROWS[("还剑奇情录", "007")].append((str(_pos), "武当五老", "◎", "武当五老"))

# ---- 行级语境前置条件：(书, 词) → 上下文必含子串 ---------------------------
CONTEXT_REQUIRE = {
    ("散花女侠", "江南"): "义军",   # 仅收"江南义军"行；036 诗行"江南玫瑰"比喻剔除
}

# ---- 行级后缀守卫：(书, 词) → 紧随后缀（命中即剔除该行） -------------------
SUFFIX_GUARD = {
    ("萍踪侠影录", "中国"): ("话", "画"),   # 中国话/中国画 = 语言/艺术，非国家实体
    ("散花女侠", "中国"): ("话", "画"),
}


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
            # 行级守卫先行（即使词在白名单，语义歧义行仍剔除）
            guard = SUFFIX_GUARD.get((book, r["word"]))
            if guard:
                i = r["context"].find(r["word"])
                tail = r["context"][i + len(r["word"]):][:2] if i >= 0 else ""
                if any(tail.startswith(g[:2]) for g in guard):
                    skip_row += 1
                    continue
            # SPAN_ROWS 优先（词为更长实体前缀 → 整段替换）
            spans = [s for s in SPAN_ROWS.get((book, r["chapter"]), [])
                     if s[0] == r["pos"]]
            if spans:
                _, w, code, canon = spans[0]
                plan.append(dict(r, word=w, code=code, canon=canon))
                continue
            if key in table:
                code, canon = table[key]
                plan.append(dict(r, code=code, canon=canon))
                continue
            req = CONTEXT_REQUIRE.get((book, r["word"]))
            if req and req in r["context"]:
                plan.append(dict(r, code="=", canon="江南"))
                continue
            if req:
                skip_row += 1      # CONTEXT_REQUIRE 未命中
                continue
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
            if ok:
                io.open(fpath, "w", encoding="utf-8", newline="\n").write(text)
                total["inserted"] += n_ins
            else:
                total["rolled_back"].append(f"{book}/{ch}")
    print(f"\n合计: 批准 {total['approve']} / 落盘 {total['inserted']} / "
          f"词级剔除 {total['skip_word']} / 行级剔除 {total['skip_row']} / "
          f"回滚 {total['rolled_back'] or '无'}")


if __name__ == "__main__":
    main()
