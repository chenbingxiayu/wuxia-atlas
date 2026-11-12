# -*- coding: utf-8 -*-
"""C18 过滤后补标（2026-11-11 GLM 校对批：龙凤宝钗缘/联剑风云录/广陵剑）。

依据：词级裁决表 logs/qa/_glm_proofread/c18_adjudication.json（GLM 逐词裁决，
approve 292 词 / 2240 行；reject 259 词 / 2106 行一律不落），经
scan_untagged_aliases._apply_word 落盘（pos 精确插入 + 保护区 + 剥标断言 +
令牌数守恒 + 逐回失败回滚 + 写前备份）。脚本模式仿 docs/76 批
c18_filtered_apply_yh_bh.py；决策表外置为 JSON（不硬编码）。

用法：python -X utf8 scripts/_oneshot/c18_filtered_apply_glm_20261111.py [--dry-run]
"""
import io
import json
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
BOOKS = ["龙凤宝钗缘", "联剑风云录", "广陵剑"]
ADJ = ROOT / "logs" / "qa" / "_glm_proofread" / "c18_adjudication.json"
SCAN_DIR = ROOT / "logs" / "qa" / "_glm_proofread"
BACKUP = ROOT / "logs" / "backup" / "c18_glm_20261111"


def load_approve():
    """裁决表 → {(word, tsv_canonical): (type_code, canonical)}；仅取 approve。"""
    data = json.loads(ADJ.read_text(encoding="utf-8"))
    tables = {}
    for book, words in data.items():
        table = {}
        for key, item in words.items():
            if item.get("verdict") != "approve":
                continue
            word, _, tsv_canon = key.partition("|")
            table[(word, tsv_canon)] = (item["type"], item["canonical"] or tsv_canon)
        tables[book] = table
    return tables


def load_rows(book: str):
    rows = []
    tdir = SCAN_DIR / f"c18_{book}.tsv"
    for f in sorted(tdir.glob("*_aliases.tsv")):
        for ln in f.read_text(encoding="utf-8").split("\n")[1:]:
            if not ln.strip():
                continue
            c = ln.split("\t")
            if len(c) >= 8:
                rows.append({"chapter": c[0], "canonical": c[1], "word": c[2],
                             "pos": c[3], "context": c[6]})
    return rows


def main():
    tables = load_approve()
    total = {"approve": 0, "skip_reject": 0, "inserted": 0, "rolled_back": []}
    for book in BOOKS:
        table = tables.get(book, {})
        rows = load_rows(book)
        plan, skip = [], 0
        for r in rows:
            entry = table.get((r["word"], r["canonical"]))
            if entry is None:
                skip += 1   # reject 或词对不在 approve 表
                continue
            plan.append(dict(r, code=entry[0], canon=entry[1]))
        total["approve"] += len(plan)
        total["skip_reject"] += skip
        print(f"[{book}] 扫描 {len(rows)} 行 → approve {len(plan)} / 不落 {skip}"
              f"（词对表 {len(table)} 项）")
        if DRY:
            by_w = defaultdict(int)
            for p in plan:
                by_w[(p["word"], p["canon"], p["code"])] += 1
            for (w, c, k), n in sorted(by_w.items(), key=lambda x: -x[1])[:15]:
                print(f"   + {w}→{c} [{k}] ×{n}")
            if len(by_w) > 15:
                print(f"   … 其余 {len(by_w) - 15} 词对略")
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
                bdir = BACKUP / book
                bdir.mkdir(parents=True, exist_ok=True)
                if not (bdir / f"{ch}.tagged.md").exists():
                    shutil.copy2(fpath, bdir / f"{ch}.tagged.md")
                io.open(fpath, "w", encoding="utf-8", newline="\n").write(text)
                total["inserted"] += n_ins
            else:
                total["rolled_back"].append(f"{book}/{ch}")
    print(f"\n合计: approve {total['approve']} / 落盘 {total['inserted']} / "
          f"不落 {total['skip_reject']} / 回滚 {total['rolled_back'] or '无'}")


if __name__ == "__main__":
    main()
