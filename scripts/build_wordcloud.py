# -*- coding: utf-8 -*-
"""spec 001 T6：主角词云统计（build_wordcloud.py）。

n-gram 词频 → 停用过滤 → Top200 raw → 人工清洗闸门 → site/data/char_wordcloud.json。
两遍法控内存：pass1 计 2/3-gram 与高频 3-前缀集；pass2 仅计「3-前缀高频」的 4-gram。

W0-T3b（天山演示版总体方案 §1.2，2026-11-08）：--scope 接线（词目按 scope 书出现过滤）。

W2-B1（天山演示版总体方案 §4.2 B1，2026-11-10）：
  - **7 书语料重算**：--scope 下 n-gram 计数只扫 scope 书 → 词频 n=scope 书语料口径
    （W0-T3b 的「n 仍为全量口径」就此废止）；
  - **人工清洗闸门**：kb/校订/词云清洗.tsv 全部 status=校定 且 verdict ∈ {keep,merge,drop}
    且 merge_to=keep 行 且 Top200 词目全部入表 → meta.cleaned=true；任一不满足 → false
    （false 时 items 保持 raw Top200，与未清洗行为一致，不上页）；
  - **清洗语义**：drop=叙事碎片/泛称/非人名 剔除；merge=OCR/截断变体词频并入规范名目
    （叠加；目标可不在候选池——停用字阻断全名经「救援行」补入，如 霍天都/于承珠）；
    别名与绰号**不归并**（玉罗刹与练霓裳分列，宇宙页 §4.6 口径注自洽）；
  - **--apply**：默认 dry-run 写 wuxia-kb/logs/export/staging/；--apply 才写 site/data
    （先自动备份 site/data/char_wordcloud.json）；
  - 全量口径（不带 --scope）：n-gram 计数扫全部书、meta 无 scope 键（方案 R6）；
    清洗 TSV 存在时同样适用（TSV 是全量口径的清洗产物）；
  - 清洗表模板只在**文件不存在**时写出（绝不覆盖人工校定成果）。

用法：python -X utf8 scripts/build_wordcloud.py [--scope tianshan-demo] [--apply]
"""
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "章回版"
OUT_JSON = ROOT / "site" / "data" / "char_wordcloud.json"
OUT_TSV = ROOT / "kb" / "校订" / "词云清洗.tsv"
BACKUP_DIR = ROOT / "backup" / "wordcloud"

# W0-T3b：scope 基础设施复用（export_site_common 在 wuxia-kb/scripts，import 胜过复制）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / "wuxia-kb" / "scripts"
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402

TOP_N = 200
CAND_POOL = 800  # 候选池（most_common 截断，停用过滤前）
MIN4_PREFIX = 30  # 4-gram 的 3-前缀至少出现该次数才参与统计（控内存，不丢高频词）
CLEAN_TSV_HEADER = ["word", "n", "books", "verdict", "merge_to", "status", "note"]
VERDICTS = {"keep", "merge", "drop"}

STOP_CHARS = set("的了是在我你他她它们这那就和与或也被把让向从会能可以上有下中说要看听到想道去来过"
                 "着一不人都很便只如虽然而因此于为等地得着个"
                 "，。！？；：\"\"''（）《》…—·!?;:()[]{}<>0123456789十五二十三四六七八九十百千万亿第")
STOP_WORDS = {
    "心里想", "心里暗", "忽听得", "忽见", "冷笑道", "冷冷道", "哈哈大笑", "哈哈一笑",
    "这件事情", "这件事", "一声长啸", "一声大喝", "只见他", "只见她", "不知不", "当下",
    "之中", "之间", "什么", "怎么", "已经", "知道", "说道", "说道：", "问道", "喝道",
    "叫道", "想道", "自己", "咱们", "他们", "她们", "两个", "三个", "一声", "面上",
    "之时", "之际", "原来", "如此", "不是", "没有", "不敢", "但是", "可是", "只是",
    "之后", "事情", "武功", "剑法", "刀法", "掌法", "师父", "师兄", "师弟", "师妹",
    "功夫", "江湖", "大师", "兄弟", "徒弟", "弟子", "天下", "今日", "原来如此",
    "一声", "两面", "三招", "左右", "之中", "一个大", "这些人",
}

# ---------------------------------------------------------------- 语料与计数
def texts(scope=None, corpus_dir=None):
    """(book, 去符号正文) 迭代；scope 口径只产 scope 书（W0-T3b；W2-B1 重算后词频随之同口径）。"""
    base = Path(corpus_dir) if corpus_dir is not None else CORPUS
    for fp in sorted(base.glob("*/*.txt")):
        book = fp.parent.name
        if not esc.in_scope(book, scope):
            continue
        txt = fp.read_text(encoding="utf-8")
        txt = re.sub(r"[^\u4e00-\u9fff]", "", txt)
        yield book, txt


def count_ngrams(pairs):
    """(book, txt) 对 → 合并 2/3/4-gram Counter（两遍法：4-gram 走高频 3-前缀门控）。"""
    c2: Counter = Counter()
    c3: Counter = Counter()
    pairs = list(pairs)
    for _book, txt in pairs:
        for i in range(len(txt) - 1):
            c2[txt[i:i + 2]] += 1
        for i in range(len(txt) - 2):
            c3[txt[i:i + 3]] += 1

    prefix3 = {w for w, n in c3.items() if n >= MIN4_PREFIX}
    c4: Counter = Counter()
    for _book, txt in pairs:
        for i in range(len(txt) - 3):
            if txt[i:i + 3] in prefix3:
                c4[txt[i:i + 4]] += 1

    merged: Counter = Counter()
    for c in (c2, c3, c4):
        merged.update(c)
    return merged


def ok(w: str) -> bool:
    """停用过滤（字符级 + 词级）。"""
    if any(ch in STOP_CHARS for ch in w):
        return False
    return w not in STOP_WORDS


def top_pool(counter):
    """n-gram 计数 → Top200 候选池 [(w, n)]（停用过滤后；人工清洗的覆盖对象）。"""
    return [(w, n) for w, n in counter.most_common(CAND_POOL) if ok(w)][:TOP_N]


def scan_presence(pairs, want):
    """(book, txt) 对 → {词: 出现书集合}（按子串出现，与旧 books_of 口径一致）。"""
    books_of: dict[str, set] = {}
    for book, txt in pairs:
        for w in want:
            if w in txt:
                books_of.setdefault(w, set()).add(book)
    return books_of


def finalize_items(top, presence, scope=None):
    """top [(w, n)] + presence → items；scope 口径：词目须在 scope 书出现、books=scope 内书目数。"""
    items = []
    for w, n in top:
        books = {b for b in presence.get(w, set()) if esc.in_scope(b, scope)}
        if scope is not None and not books:
            continue  # scope 口径：scope 外书才出现的词目裁掉
        items.append({"w": w, "n": n, "books": len(books)})
    return items


# ---------------------------------------------------------------- 清洗表（W2-B1）
def load_clean_tsv(path=None):
    """读清洗表 → {exists, verdicts: {word:(verdict, merge_to)}, problems: [str]}。

    表级校验（problems 非空即闸门不过）：
      - status 必须=校定（draft/空 = 未校定）；
      - verdict ∈ {keep, merge, drop}；
      - merge 行必须给 merge_to，且 merge_to 必须是 **keep 行**（禁止链式/悬空 merge）。
    """
    path = Path(path) if path is not None else OUT_TSV
    state = {"path": path, "exists": path.exists(), "verdicts": {}, "rows": 0, "problems": []}
    if not path.exists():
        state["problems"].append(f"清洗表不存在：{path}")
        return state
    import csv

    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    parsed = []
    for i, row in enumerate(rows, start=2):
        w = (row.get("word") or "").strip()
        if not w:
            continue
        v = (row.get("verdict") or "").strip()
        s = (row.get("status") or "").strip()
        tgt = (row.get("merge_to") or "").strip()
        parsed.append((w, v, s, tgt))
        state["rows"] += 1
        if s != "校定":
            state["problems"].append(f"{w}: status={s or '空'}（未校定）")
        elif v not in VERDICTS:
            state["problems"].append(f"{w}: verdict={v or '空'} 非法（须 keep/merge/drop）")
        elif v == "merge" and not tgt:
            state["problems"].append(f"{w}: merge 缺 merge_to")
    keep_words = {w for w, v, s, _t in parsed if v == "keep" and s == "校定"}
    for w, v, s, tgt in parsed:
        if v == "merge" and s == "校定" and tgt and tgt not in keep_words:
            state["problems"].append(f"{w}: merge_to={tgt} 非 keep 规范名目（禁止链式/悬空）")
    state["verdicts"] = {w: (v, tgt) for w, v, s, tgt in parsed if s == "校定" and v in VERDICTS}
    state["words"] = {w for w, _v, _s, _t in parsed}  # 入表即可（无论校定与否），覆盖率用
    return state


def cleaned_gate(state, pool_words):
    """(bool, reasons)：清洗表全部校定+合法 且 候选池词目全部入表 → True。"""
    reasons = list(state["problems"])
    seen = state.get("words", set())
    missing = [w for w in pool_words if w not in seen]
    if missing:
        head = "、".join(missing[:8])
        more = f"… 等 {len(missing)} 个" if len(missing) > 8 else ""
        reasons.append(f"Top200 有 {len(missing)} 个词目未入清洗表：{head}{more}")
    return (not reasons), reasons


def apply_cleaning(top, verdicts, counter):
    """清洗语义（gate 通过后调用）→ (counts: {word: n}, stats)。

    - drop：直接剔除；
    - merge：源词词频并入 merge_to 目标（叠加），源词删除；目标若不在候选池，
      先按全量计数器补入目标自身频次（停用字阻断全名的救援通道）；
    - keep（含未列入但已校定的池内词，gate 已保证全覆盖）：保留原频次；
    - 救援行：keep 且不在候选池的词目，当前口径语料计数>0 时补入
      （停用字阻断全名 霍天都/于承珠/卓一航/吕四娘 等，及低于截断的关键名目）。
    """
    pool_n = dict(top)
    counts = {}
    stats = {"keep": 0, "merged_sources": 0, "dropped": 0, "rescued": 0}
    merged_in: dict[str, int] = {}
    for w, n in top:
        v, tgt = verdicts.get(w, (None, None))
        if v == "drop":
            stats["dropped"] += 1
            continue
        if v == "merge":
            merged_in[tgt] = merged_in.get(tgt, 0) + n
            stats["merged_sources"] += 1
            continue
        counts[w] = counts.get(w, 0) + n
        stats["keep"] += 1
    for tgt, add in merged_in.items():
        if tgt in pool_n and verdicts.get(tgt, (None,))[0] == "keep":
            counts[tgt] = counts.get(tgt, 0) + add      # 目标在池：池频次已入 counts
        else:
            counts[tgt] = counts.get(tgt, 0) + counter.get(tgt, 0) + add
            stats["rescued"] += 1
    # 救援行（keep 且不在候选池）：停用字阻断全名/低于截断的关键名目——
    # 当前口径语料中有出现（计数>0）即补入（如 卓一航/吕四娘/白发魔女/练霓裳）。
    for w, (v, _tgt) in verdicts.items():
        if v == "keep" and w not in counts and w not in pool_n:
            n0 = counter.get(w, 0)
            if n0 > 0:
                counts[w] = counts.get(w, 0) + n0
                stats["rescued"] += 1
    return counts, stats


# ---------------------------------------------------------------- meta 与组装
def wordcloud_meta(scope=None, cleaned=False, reasons=None, stats=None):
    """meta：schema/cleaned/note（口径注）+ scope 口径信息（W0-T3b 兼容签名）。"""
    meta = {"schema": "char-wordcloud-v1", "generated": "ngram-234",
            "method": "两遍法：2/3-gram 全量 + 4-gram 高频前缀门控",
            "cleaned": bool(cleaned),
            "note": "cleaned=true 需先人工清洗 kb/校订/词云清洗.tsv（keep/merge/drop）"}
    if cleaned:
        meta["note"] = (
            "人工清洗已完成（kb/校订/词云清洗.tsv 全部校定）：keep=名目保留；"
            "drop=叙事碎片/泛称/非人名剔除；merge=OCR/截断变体名目频次并入规范名目"
            "（并入后 n 为名目强度，高于该名逐次出现数）；别名与绰号不归并——玉罗刹与练霓裳分列；"
            "停用字阻断的全名（霍天都/于承珠等）经清洗救援行补入")
        if stats:
            meta["clean_stats"] = dict(stats)
    elif reasons:
        meta["note"] += "；当前未过闸门：" + "；".join(reasons[:6])
    if scope is not None:
        meta.update(esc.scope_meta(scope))
        meta["note"] += ("；scope 口径：词目按 scope 书出现过滤、books=scope 内书目数；"
                         "词频 n=scope 书语料重算（W2-B1）")
    return meta


def build_payload(scope=None, corpus_dir=None, tsv_path=None):
    """→ {"meta":…, "items":…}（纯计算不写盘；main 负责落盘）。

    scope=None → 全量口径（R6）；scope=profile dict → 7 书语料重算 + scope 过滤（W2-B1）。
    """
    pairs = list(texts(scope, corpus_dir))
    counter = count_ngrams(pairs)
    pool = top_pool(counter)
    state = load_clean_tsv(tsv_path)
    gate, reasons = cleaned_gate(state, [w for w, _ in pool])

    if gate:
        counts, stats = apply_cleaning(pool, state["verdicts"], counter)
        top = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:TOP_N]
        meta = wordcloud_meta(scope, cleaned=True, stats=stats)
    else:
        top = pool
        meta = wordcloud_meta(scope, cleaned=False, reasons=reasons)

    presence = scan_presence(pairs, {w for w, _ in top})
    items = finalize_items(top, presence, scope)
    return {"meta": meta, "items": items}


# ---------------------------------------------------------------- 落盘
def _backup_json(path: Path) -> Path | None:
    """--apply 前备份既有产物 → backup/wordcloud/char_wordcloud.json.bak-<stamp>。"""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"{path.name}.bak-{stamp}"
    shutil.copy2(path, dest)
    return dest


def _write_tsv_template():
    """清洗表模板（仅当文件不存在时写出；绝不覆盖人工校定成果）。"""
    lines = ["\t".join(CLEAN_TSV_HEADER)]
    for it in top_pool(count_ngrams(texts(None))):
        lines.append(f"{it[0]}\t{it[1]}\t\t\t\tdraft\t")
    OUT_TSV.parent.mkdir(parents=True, exist_ok=True)
    OUT_TSV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"-> {OUT_TSV}（人工清洗模板：verdict=keep/merge/drop，status=校定 后生效）")


def main() -> int:
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    payload = build_payload(scope)
    meta, items = payload["meta"], payload["items"]

    if esc.is_apply():
        backup = _backup_json(OUT_JSON)
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        esc.atomic_write_json(payload, OUT_JSON)
        print(f"-> {OUT_JSON}（top{len(items)}，cleaned={meta['cleaned']}）"
              + (f"［已备份旧产物 → {backup}］" if backup else ""))
    else:
        staging = esc.STAGING / OUT_JSON.name
        esc.atomic_write_json(payload, staging)
        print(f"-> {staging}（dry-run，top{len(items)}，cleaned={meta['cleaned']}；"
              f"--apply 写 {OUT_JSON}）")

    if scope is None and not OUT_TSV.exists():
        _write_tsv_template()
    elif scope is None:
        print(f"   清洗表已存在，跳过模板重写：{OUT_TSV}")
    else:
        print(f"   scope 口径不重写清洗表：{OUT_TSV}")

    print("   预览:", [(it["w"], it["n"]) for it in items[:12]])
    if not meta["cleaned"]:
        print("   [warn] 未过清洗闸门：" + "；".join(
            re.split("；", meta["note"].split("当前未过闸门：")[-1])[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
