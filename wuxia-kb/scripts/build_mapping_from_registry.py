# -*- coding: utf-8 -*-
"""registry + 已过审 gold 管道 → 每回《已核准映射表》快照（换书工具 · 扩书前置）

背景（docs/71 §七.1）：
    换新书时，旧标注映射只有 4 部书有（kb/tagged/<书>），其余书 build_legacy_mapping
    无输入 → mapping 只能空表，@ 管道率会掉到 2-4%。本工具改用两路来源，为新书生成
    逐回累积快照：

      来源 A（主）：`registry/entities.json` 的 @ 人物
        A1 全局别名（aliases，字符串）
        A2 书级语境注记（contextual dict）：仅收 `book == 本书` 的条目；跨书注记不搬运
      来源 B（辅，`--gold-transfer`，默认开）：已过审 tagged 的 @ 管道
        只搬运"规范名已登记 且 该规范名在本书正文出现"的跨书别名，并过滤：
        · 出现 <2 次、含注记括号、长度 <2 的显示串不收；
        · 通用称谓/头衔（相公/皇子/前辈/大侠…）不收；
        · 显示串是其他实体 canonical 的不收（防同形冲突）；
        · 显示串是 canonical 的真子串且长度 <3 的不收（短称交给模型按最小完整单位判断）；
        · 同显示串多规范名 → 跳过（宁缺勿错）；人工复核记录见 review.tsv。

口径（与 build_legacy_mapping.py 对齐）：
    1. 只取 @ 类；显示串须在本书正文出现；单字显示串不收；
    2. 第 N 回快照 = 在 1..N-1 回正文中出现过的映射（模拟顺序标注，不引入未来知识）；
    3. 按 (-len(显示串), 显示串) 排序；
    4. 只读 registry/tagged/../章回版，不改任何既有产物。

产物：
    logs/mapping_<书>/ch_NNN.json     逐回累积快照 [[显示串, 规范名], ...]
    logs/mapping_<书>/mapping.json    合并映射（= 末回快照，供 --mapping-file 单文件）
    logs/mapping_<书>/review.tsv      来源 B 的逐条候选（显示串/规范名/来源/计数/首现回/上下文）
    logs/mapping_<书>/summary.md      统计与来源说明

用法：
    python -X utf8 scripts/build_mapping_from_registry.py <书名> [--dry-run] [--check]
    python -X utf8 scripts/build_mapping_from_registry.py <书名> --no-gold-transfer
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

REGISTRY = config.DIR_REGISTRY / "entities.json"
BAD_ALIAS_RE = re.compile(r"[（(]")
# 通用称谓 / 头衔 / 时代名：不进入人物别名映射
GENERIC = {
    "相公", "皇子", "王子", "神医", "少主", "公子", "大人", "前辈", "大侠", "女侠", "夫人",
    "姑娘", "老师", "师父", "师兄", "师姐", "师弟", "师妹", "掌柜", "老汉", "老者", "婆婆",
    "大娘", "大嫂", "丫头", "贤弟", "仁兄", "老兄", "老弟", "世兄", "世侄", "小兄弟",
    "老前辈", "掌门", "帮主", "长老", "方丈", "道长", "真人", "居士", "皇上", "皇帝",
    "太后", "王爷", "贝勒", "将军", "元帅", "成化", "万历", "嘉靖", "康熙", "雍正", "乾隆",
    "嘉庆", "道光", "顺治", "崇祯", "太子", "天子", "活佛", "兄台", "老爷", "宗主", "国王",
    "公公", "人妖", "武家兄弟", "尼泊尔国王",
}
TITLE_RE = re.compile(
    r"(前辈|大侠|女侠|夫人|公子|少主|叔叔|哥哥|姐姐|师兄|师弟|师姐|师妹|师叔|师伯|师父|"
    r"姑姑|婶婶|兄|姐|哥|先生|姑娘|老汉|老者|老头|婆婆|大娘|大嫂|大婶|大人|阁下|丫头|"
    r"公公|国王|活佛|太子|天子|相公|老爷|宗主|某|们|儿|老|少)$")
# 器物/技艺名形（防止"游龙剑→楚昭南""金刚手（武功）→董岳"这类错误搬运）
OBJECT_RE = re.compile(r"(剑|刀|鞭|棍|拳|掌|手|神芒|剑法|刀法|掌法|神功|心法|秘籍|丹|丸|散|膏|药)$")
# 已知跨书管道噪声（人工复核排除：2026-11-06 云海/冰河 逐条上下文核验）
TRANSFER_DENY = {
    "天山神芒",   # 暗器名，被误记为凌未风别名
    "游龙剑",     # 兵器名（楚昭南佩剑）
    "自发魔女",   # "白发魔女"讹字形
    "华妹",       # 云海·之华妹妹 → 谷之华，非何绿华
    "霞妹",       # 冰河·霞妹 → 邹绛霞（江南之妻），非孟秋霞
}


def cjk_len(s: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def bad_display(disp: str, canon: str, canon_set: set) -> bool:
    """映射显示串通用噪声过滤（registry/gold 两路共用）。"""
    if not disp or cjk_len(disp) < 2 or disp == canon:
        return True
    if BAD_ALIAS_RE.search(disp) or disp in GENERIC or disp in TRANSFER_DENY:
        return True
    if TITLE_RE.search(disp) or OBJECT_RE.search(disp):
        return True
    if disp in canon_set:              # 是别的实体 canonical → 同形冲突
        return True
    return False


def read_text(path: Path) -> str:
    try:
        return io.open(path, encoding="utf-8").read()
    except UnicodeDecodeError:
        return io.open(path, encoding="gb18030").read()


def load_registry(book: str):
    """registry → ({display: canonical}, 统计, 冲突, 全部 @ canonical 集合)。"""
    data = json.loads(io.open(REGISTRY, encoding="utf-8").read())
    entities = data.get("entities", []) if isinstance(data, dict) else []
    canon_set = {
        (e.get("canonical") or "").strip()
        for e in entities
        if e.get("type") == "@" and e.get("canonical") and e.get("status") != "pending"
    }
    canon_set.discard("")
    disp2canon: dict[str, Counter] = defaultdict(Counter)
    stat = Counter()
    for e in entities:
        if e.get("type") != "@":
            continue
        canon = (e.get("canonical") or "").strip()
        if not canon or e.get("status") == "pending":
            continue
        stat["entities"] += 1
        # A1 全局别名（过滤上下文标题/器物形）
        for a in e.get("aliases") or []:
            if isinstance(a, dict):
                continue
            a = (a or "").strip()
            if bad_display(a, canon, canon_set):
                continue
            disp2canon[a][canon] += 1
            stat["alias_pairs"] += 1
        # A2 书级语境注记：只收本书
        for a in e.get("contextual") or []:
            if not isinstance(a, dict):
                a = {"display": a}
            disp = (a.get("display") or "").strip()
            bk = a.get("book")
            if not disp:
                continue
            if bk and bk != book:
                stat["ctx_skipped_other_book"] += 1
                continue
            if bad_display(disp, canon, canon_set):
                continue
            disp2canon[disp][canon] += 1
            stat["ctx_pairs"] += 1
    pairs, conflicts = {}, {}
    for disp, cnt in disp2canon.items():
        if len(cnt) > 1:
            conflicts[disp] = dict(cnt)
            stat["conflicts"] += 1
            continue
        pairs[disp] = next(iter(cnt))
    return pairs, dict(stat), conflicts, canon_set


def load_gold_transfer(book: str, canon_set: set):
    """已过审 tagged 的 @ 管道 → 可搬运到本书的（显示串→规范名）与复核记录。"""
    tagged_root = config.DIR_TAGGED
    cnt: Counter = Counter()
    first_book = {}
    for d in sorted(tagged_root.iterdir() if tagged_root.is_dir() else []):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        for f in sorted(d.glob("*.tagged.md")):
            t = read_text(f)
            for m in re.finditer(r"〖@([^|〗]+)\|([^〗]+)〗", t):
                disp, canon = m.group(1).strip(), m.group(2).strip()
                if cjk_len(disp) >= 2 and disp != canon and not BAD_ALIAS_RE.search(disp):
                    cnt[(disp, canon)] += 1
                    first_book.setdefault((disp, canon), d.name)
    cand = {}
    for (disp, canon), n in cnt.items():
        if n < 2 or canon not in canon_set:
            continue
        if bad_display(disp, canon, canon_set):
            continue
        if disp in canon and cjk_len(disp) < 3:   # 短称（四娘/凤池）交给模型按最小完整单位判断
            continue
        cand.setdefault(disp, Counter())[canon] += n
    out, review = {}, []
    for disp, c in cand.items():
        if len(c) > 1:
            review.append({"display": disp, "canonical": ",".join(c), "source": "gold",
                           "count": sum(c.values()), "status": "conflict_skip"})
            continue
        canon = next(iter(c))
        out[disp] = (canon, sum(c.values()), first_book.get((disp, canon), ""))
        review.append({"display": disp, "canonical": canon, "source": "gold",
                       "count": sum(c.values()), "status": "candidate"})
    return out, review


def main() -> int:
    ap = argparse.ArgumentParser(description="registry+gold → 逐回《已核准映射表》快照（换书工具）")
    ap.add_argument("book", help="书名（../章回版/<书>、logs/mapping_<书> 同名）")
    ap.add_argument("--out-dir", default=None, help="输出目录（缺省 logs/mapping_<书>）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    ap.add_argument("--check", action="store_true",
                    help="与既有 logs/mapping_<书>/ch_NNN.json 对账后退出")
    ap.add_argument("--no-gold-transfer", action="store_true", help="不搬运 gold 管道别名")
    args = ap.parse_args()
    book = args.book

    reg_pairs, reg_stat, conflicts, canon_set = load_registry(book)
    gold_pairs, review = ({}, []) if args.no_gold_transfer else load_gold_transfer(book, canon_set)

    cdir = config.corpus_dir(book)
    if not cdir.is_dir():
        raise SystemExit(f"[ERROR] 底本目录不存在：{cdir}")
    chapter_files = {}
    for p in sorted(cdir.glob("*.txt")):
        m = re.match(r"^(\d{1,3})", p.name)
        if m:
            chapter_files[int(m.group(1))] = p
    if not chapter_files:
        raise SystemExit(f"[ERROR] 底本文件名无回号前缀：{cdir}")
    total = max(chapter_files)
    texts = {ch: read_text(p) for ch, p in chapter_files.items()}

    # 合并两路来源：gold 只补 registry 没有的显示串；registry 优先
    merged = {}
    for disp, canon in reg_pairs.items():
        merged[disp] = ("registry", canon, 0)
    for disp, (canon, n, first) in gold_pairs.items():
        if disp in merged and merged[disp][1] != canon:
            review.append({"display": disp, "canonical": canon, "source": "gold",
                           "count": n, "status": "registry_conflict_skip"})
            continue
        if disp not in merged:
            merged[disp] = ("gold", canon, n)
    used = {d: v for d, v in merged.items() if any(d in texts.get(ch, "") for ch in texts)}
    for r in review:
        r["appears"] = bool(any(r["display"] in texts.get(ch, "") for ch in texts))
    print(f"[registry] @实体 {reg_stat.get('entities', 0)}；候选 {len(reg_pairs)} 条；"
          f"冲突跳过 {len(conflicts)}；跨书注记跳过 {reg_stat.get('ctx_skipped_other_book', 0)}")
    print(f"[gold] 可搬运候选 {len(gold_pairs)} 条（复核表 review.tsv，含冲突/未命中）")
    print(f"[merge] 合并候选 {len(merged)} 条；本书正文命中 {len(used)} 条")

    # 首次出现回
    first_seen = {}
    per_ch_new = {}
    for ch in range(1, total + 1):
        t = texts.get(ch, "")
        n_hit = 0
        for disp in used:
            if disp in first_seen:
                continue
            if disp in t:
                first_seen[disp] = ch
                n_hit += 1
        per_ch_new[ch] = n_hit

    snapshots, sizes, acc = {}, [], {}
    for ch in range(1, total + 1):
        snap = sorted(acc.items(), key=lambda kv: (-len(kv[0]), kv[0]))
        snapshots[ch] = [[d, c] for d, c in snap]
        sizes.append((ch, len(snap)))
        for disp in used:
            if first_seen.get(disp) == ch:
                acc[disp] = used[disp][1]
    final = sorted(acc.items(), key=lambda kv: (-len(kv[0]), kv[0]))

    if args.check:
        old_dir = config.DIR_LOGS / f"mapping_{book}"
        old_final = {}
        old_file = old_dir / f"ch_{total:03d}.json"
        if old_file.exists():
            try:
                old_final = {d: c for d, c in json.loads(io.open(old_file, encoding="utf-8").read())}
            except (ValueError, TypeError):
                old_final = {}
        covered = sum(1 for d in old_final if d in acc)
        print(f"[check] legacy 末回 {len(old_final)} 条；新工具 {len(final)} 条；"
              f"legacy 显示串被覆盖 {covered}/{len(old_final)}")
        return 0

    if args.dry_run:
        print(f"[dry-run] 末回映射 {len(final)} 条（来源："
              f"registry {sum(1 for d, c in final if merged.get(d, ('',))[0] == 'registry')} / "
              f"gold {sum(1 for d, c in final if merged.get(d, ('',))[0] == 'gold')}）；不写文件")
        print("前 10 条：", final[:10])
        return 0

    out_dir = Path(args.out_dir) if args.out_dir else (config.DIR_LOGS / f"mapping_{book}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for ch in range(1, total + 1):
        io.open(out_dir / f"ch_{ch:03d}.json", "w", encoding="utf-8", newline="\n").write(
            json.dumps(snapshots[ch], ensure_ascii=False, indent=0))
    io.open(out_dir / "mapping.json", "w", encoding="utf-8", newline="\n").write(
        json.dumps(final, ensure_ascii=False, indent=0))
    # review.tsv：gold 逐条（含未采用原因）
    lines = ["display\tcanonical\tsource\tcount\tfirst_seen_ch\tappears\tapplied"]
    for r in review:
        d = r["display"]
        applied = (d in acc) and merged.get(d, ("",))[0] == "gold"
        lines.append(f"{d}\t{r['canonical']}\t{r['source']}\t{r['count']}\t"
                     f"{first_seen.get(d, '')}\t{r['appears']}\t{applied}\t{r['status']}")
    io.open(out_dir / "review.tsv", "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    n_reg = sum(1 for d in acc if merged.get(d, ("",))[0] == "registry")
    n_gold = len(acc) - n_reg
    summary = [
        f"# 映射快照（{book}）", "",
        f"- 来源：`registry/entities.json`（A：@实体别名/本书语境注记）"
        f" + 已过审 `tagged/` 的 @管道（B：仅跨书共享规范名，严格过滤）",
        f"- 回数：{total}；`ch_NNN.json` = 第 N 回快照（仅含首次出现在 <N 回的映射）；"
        f"`mapping.json` = 末回合并映射",
        f"- 末回映射 **{len(final)}** 条（A registry {n_reg} / B gold {n_gold}）；"
        f"本书正文命中 {len(used)} / 合并候选 {len(merged)}",
        f"- registry：@实体 {reg_stat.get('entities', 0)}；候选 {len(reg_pairs)}；"
        f"同显示串冲突跳过 {len(conflicts)}；跨书语境注记跳过 {reg_stat.get('ctx_skipped_other_book', 0)}",
        f"- gold 搬运：候选 {len(gold_pairs)}；复核明细 `review.tsv`（含冲突跳过/未命中）",
        "", "| 回 | 快照条数 | 本回首次出现 |", "|---|---:|---:|",
    ]
    summary += [f"| {ch:03d} | {n} | {per_ch_new.get(ch, 0)} |" for ch, n in sizes]
    io.open(out_dir / "summary.md", "w", encoding="utf-8", newline="\n").write(
        "\n".join(summary) + "\n")
    print(f"[ok] {book}: {total} 回快照 + mapping.json（{len(final)} 条：registry {n_reg} / gold {n_gold}）→ {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
