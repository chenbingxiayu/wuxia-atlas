# -*- coding: utf-8 -*-
"""C19 · 单字人名映射体检与推断（武侠版，默认只出报告，不写 tagged）。

移植自 shiji-kb/scripts/infer_single_char_names.py（只读参考，2026-11-04），改动：
  1. CANONICAL_SINGLE（"单字即全名"名单）清空史记远古人名（舜/尧/禹/鲧/桀/纣/
     汤/契/稷/益/羿…），改为可配置：默认空集，若存在
     `wordlists/single_char_canonical.json` 则读入（items[].surface 或字符串列表）。
     武侠版如需"单字即规范名"（如某些法号/绰号）再登记，不在代码里写死。
  2. 语料改经 config（tagged/<书>/NNN.tagged.md），不再默认 1-10 章；
     章节参数支持 all / 1-32 / 005,006。
  3. 单字人名识别走 symbols.TOKEN_RE + parse_token（禁本地字符类），
     同时把「已挂管道的单字」纳入体检：管道规范名要与同回多字名/registry 对得上，
     否则告警（跨回同字异人是最容易埋雷的情形，如「金」在不同回指不同人物）。
  4. 推断规则（武侠版，2026-11-05 P1 修复）：同回多字人名（含管道规范名）**末字**匹配单字 → 候选；
     唯一候选才映射；多候选取频次最高并报歧义（频次 = 令牌次数，辅以全文
     `symbols.strip_markup` 后经 masker 的裸文频次）；无候选进"无匹配"。
  5. 默认输出 `logs/single_char_names/<book>.md`（映射/歧义/无匹配/告警四段）
     + 同名 JSON；`--apply` 可选：备份后只对**唯一新推断**插管道
     `〖@X〗 → 〖@X|全名〗`，写前备份、剥标断言、逐回校验。

用法：
    python scripts/infer_single_char_names.py --book 白发魔女传
    python scripts/infer_single_char_names.py --book 白发魔女传 --chapters 005,008
    python scripts/infer_single_char_names.py --book 白发魔女传 --chapters 1-32 --apply

边界：只处理 `〖@…〗` 人物单字 token；不推断地名/组织单字，不改原文，不调 LLM。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config      # noqa: E402
import symbols     # noqa: E402
import masker      # noqa: E402

CANONICAL_SINGLE_PATH = config.DIR_WORDLISTS / "single_char_canonical.json"
REGISTRY_PATH = config.DIR_REGISTRY / "entities.json"
LOG_DIR = config.DIR_LOGS / "single_char_names"
BACKUP_ROOT = config.ROOT / "backup" / "tagged"


def load_canonical_single(path: Path = CANONICAL_SINGLE_PATH) -> tuple[set, str]:
    """可配置"单字即全名"名单。文件不存在 → 空集（史记远古人名已全部清空）。"""
    if not path.exists():
        return set(), f"未建（默认空集）：{path}"
    data = json.loads(io.open(path, encoding="utf-8").read())
    items = data if isinstance(data, list) else data.get("items", [])
    words = set()
    for it in items:
        val = it.get("surface") if isinstance(it, dict) else it
        if isinstance(val, str) and val.strip():
            words.add(val.strip())
    return words, f"已读取 {path}（{len(words)} 条）"


def load_registry_words(path: Path = REGISTRY_PATH) -> set:
    """registry 的 canonical + aliases（含剥括号注释），用于"全名可唯一解析"体检。"""
    if not path.exists():
        return set()
    data = json.loads(io.open(path, encoding="utf-8").read())
    words = set()
    for ent in data.get("entities", []):
        names = [ent.get("canonical", "")] + list(ent.get("aliases") or [])
        for name in names:
            name = (name or "").strip()
            if "（" in name:
                name = name.split("（", 1)[0].strip()
            if name:
                words.add(name)
    return words


def parse_chapters(spec: str) -> list[int]:
    """'all' / '1-32' / '005,006,010-012' → 回号列表。

    健壮性（2026-11-05 P2-B）：非法输入（`1-abc`、`abc`、`3-1`、`0`）给出友好
    SystemExit 提示，不抛裸 ValueError；空片段忽略。
    """
    if not spec or spec.strip().lower() == "all":
        return []
    out = []
    for part in spec.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = part.split("-", 1)
                a_i, b_i = int(a.strip()), int(b.strip())
                if a_i < 1 or b_i < a_i:
                    raise ValueError
                out.extend(range(a_i, b_i + 1))
            else:
                n = int(part)
                if n < 1:
                    raise ValueError
                out.append(n)
        except ValueError:
            raise SystemExit(
                f"[ERROR] --chapters 解析失败：{part!r}"
                f"（格式：all / 1-32 / 005,006；回号须为正整数）") from None
    return sorted(set(out))


def collect_chapter(tagged_path: Path) -> dict:
    """抽取一回的 @ 人物令牌：多字名/管道规范名/单字 token 及其位置。"""
    text = io.open(tagged_path, encoding="utf-8").read()
    display_counts: Counter = Counter()      # 多字显示串频次
    canonical_counts: Counter = Counter()    # 多字管道规范名频次
    singles: list[dict] = []
    for m in symbols.TOKEN_RE.finditer(text):
        layer, code, body, disp, note, err = symbols.parse_token(m.group(0))
        if layer != "entity" or code != "@" or not disp:
            continue
        if len(disp) >= 2:
            display_counts[disp] += 1
        if note and len(note) >= 2:
            canonical_counts[note] += 1
        if len(disp) == 1:
            singles.append({"start": m.start(), "end": m.end(), "char": disp,
                            "canonical": note, "token": m.group(0)})
    names = set(display_counts) | set(canonical_counts)
    # 裸文频次（剥标后正文，供多候选排序的第二证据；经 masker 最长匹配）
    raw_text = symbols.strip_markup(text)
    raw_counts: Counter = Counter()
    if names:
        for word, _a, _b in masker.find_candidates(raw_text, masker.build_matcher(names)):
            raw_counts[word] += 1
    return {"text": text, "display_counts": display_counts,
            "canonical_counts": canonical_counts, "names": names,
            "singles": singles, "raw_counts": raw_counts}


def infer_chapter(chapter: str, info: dict, canonical_single: set) -> dict:
    """单回推断：已挂管道体检 + 未挂管道单字推断/歧义/无匹配。"""
    names = info["names"]
    display_counts, canonical_counts, raw_counts = (
        info["display_counts"], info["canonical_counts"], info["raw_counts"])
    mappings, ambiguous, unmatched, warnings = [], [], [], []

    def freq(name: str) -> int:
        return display_counts.get(name, 0) + canonical_counts.get(name, 0) + raw_counts.get(name, 0)

    for item in info["singles"]:
        char = item["char"]
        char_count = sum(1 for s in info["singles"] if s["char"] == char)
        if char in canonical_single:
            unmatched.append({"chapter": chapter, "char": char, "count": char_count,
                              "reason": "在 CANONICAL_SINGLE 名单（单字即全名），不推断"})
            continue
        if item["canonical"]:
            full = item["canonical"]
            mappings.append({"chapter": chapter, "char": char, "full": full,
                             "source": "管道已有", "char_count": char_count,
                             "full_freq": freq(full), "token": item["token"],
                             "evidence": "inline pipe"})
            if len(full) < 2:
                warnings.append({"chapter": chapter, "char": char, "full": full,
                                 "issue": f"管道规范名「{full}」不足 2 字，不合规范名口径"})
            elif full not in names:
                warnings.append({"chapter": chapter, "char": char, "full": full,
                                 "issue": "管道规范名未在同回多字人名中出现（需人工复核同一性）"})
            continue
        # 仅末字匹配：武侠单字称呼多为名末字（"欢/愁"）；首字多为姓氏，
        # 同回只有"李寻欢"时把单字"李"映射过去会误判（2026-11-05 P1 修复）。
        cands = [n for n in names if n[-1] == char]
        ranked = sorted(cands, key=lambda n: (-freq(n), n))
        if len(ranked) == 1:
            mappings.append({"chapter": chapter, "char": char, "full": ranked[0],
                             "source": "新推断", "char_count": char_count,
                             "full_freq": freq(ranked[0]), "token": item["token"],
                             "evidence": "同回唯一候选（末字匹配）"})
        elif len(ranked) > 1:
            ambiguous.append({"chapter": chapter, "char": char,
                              "candidates": [(n, freq(n)) for n in ranked],
                              "chosen": ranked[0], "token": item["token"]})
        else:
            unmatched.append({"chapter": chapter, "char": char, "count": char_count,
                              "reason": "同回无末字匹配的多字人名"})
    return {"chapter": chapter, "mappings": mappings, "ambiguous": ambiguous,
            "unmatched": unmatched, "warnings": warnings}


def write_report(book: str, chapters: list[int], params: dict, canonical_source: str,
                 results: list[dict], registry_words: set) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 子集扫描不覆盖全书报告（2026-11-04 Lead 修复）
    suffix = "" if params.get("chapters") in (None, "all") else \
        "_" + str(params["chapters"]).replace(",", "-").replace(" ", "")
    label = f"{book}{suffix}"
    mappings = [m for r in results for m in r["mappings"]]
    inferred = [m for m in mappings if m["source"] == "新推断"]
    piped = [m for m in mappings if m["source"] == "管道已有"]
    ambiguous = [a for r in results for a in r["ambiguous"]]
    unmatched = [u for r in results for u in r["unmatched"]]
    warnings = [w for r in results for w in r["warnings"]]

    # 跨回同字异人（同一单字在不同回指向不同全名）
    by_char: dict[str, dict] = defaultdict(set)
    for m in mappings:
        by_char[m["char"]].add(m["full"])
    conflicts = {ch: sorted(fulls) for ch, fulls in by_char.items() if len(fulls) > 1}
    not_in_registry = [m for m in mappings if m["full"] not in registry_words]

    lines = [
        f"# C19 单字人名映射体检与推断报告 — {book}",
        "",
        f"- 生成时间：{stamp}",
        f"- 语料：`tagged/{book}/` 扫描 {len(chapters)} 回 / 全书 {params.get('total_chapters', len(chapters))} 回",
        f"- 参数：{json.dumps(params, ensure_ascii=False)}",
        f"- CANONICAL_SINGLE：{canonical_source}（史记远古人名已清空，武侠名单可配置）",
        "- 写入范围：本报告 + 同名 JSON；tagged 未改动"
        + ("；`--apply` 已开启（仅唯一新推断）" if params.get("apply") else ""),
        "",
        "## 一、映射（共 {n} 条：管道已有 {p} / 新推断 {i}；去重 (回,单字) {u} 组）".format(
            n=len(mappings), p=len(piped), i=len(inferred),
            u=len({(m["chapter"], m["char"]) for m in mappings})),
        "",
        "| 回 | 单字 | 全名 | 来源 | 单字次数 | 全名频次 | 校验 |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in mappings:
        check = "registry ✓" if m["full"] in registry_words else "**不在 registry**"
        lines.append(f"| {m['chapter']} | {m['char']} | {m['full']} | {m['source']} | "
                     f"{m['char_count']} | {m['full_freq']} | {check} |")
    lines += [
        "",
        "## 二、歧义（共 {n} 条，多候选取频次最高，本轮不自动应用）".format(n=len(ambiguous)),
        "",
        "| 回 | 单字 | 候选（令牌+裸文频次） | 频次最高建议 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for a in ambiguous:
        cands = "、".join(f"{n}×{c}" for n, c in a["candidates"])
        lines.append(f"| {a['chapter']} | {a['char']} | {cands} | {a['chosen']} | "
                     f"多候选，须人工裁定后挂管道 |")
    lines += [
        "",
        "## 三、无匹配（共 {n} 条）".format(n=len(unmatched)),
        "",
        "| 回 | 单字 | 次数 | 原因 |",
        "|---|---|---|---|",
    ]
    for u in unmatched:
        lines.append(f"| {u['chapter']} | {u['char']} | {u['count']} | {u['reason']} |")
    if not unmatched:
        lines.append("| — | — | — | 无 |")
    lines += [
        "",
        "## 四、跨回同字异人与 registry 告警",
        "",
    ]
    if conflicts:
        lines.append("**同一单字在不同回映射到不同全名（禁止全书统一替换）**：")
        for char, fulls in conflicts.items():
            lines.append(f"- `{char}` → {fulls}")
    else:
        lines.append("- 跨回同字异人：无")
    lines.append("")
    if not_in_registry:
        lines.append("**管道规范名不在 `registry/entities.json`（实体层需补登或改口径）**：")
        for m in not_in_registry:
            lines.append(f"- {m['chapter']}：`{m['char']}` → `{m['full']}`（来源{m['source']}）")
    else:
        lines.append("- registry 校验：全部映射的规范名均可解析到 registry")
    if warnings:
        lines.append("")
        lines.append("**其他告警**：")
        for w in warnings:
            lines.append(f"- {w['chapter']}：`{w['char']}`→`{w['full']}`：{w['issue']}")
    lines += [
        "",
        "## 五、人工核对样例（3 条映射逐条核原文）",
        "",
    ]
    seen_chapters = set()
    samples = []
    for m in mappings:
        if m["chapter"] in seen_chapters:
            continue
        seen_chapters.add(m["chapter"])
        samples.append(m)
        if len(samples) >= 3:
            break
    for m in samples:
        lines.append(f"- {m['chapter']} 回：`{m['token']}` → `{m['full']}`"
                     f"（{m['source']}；同回全名频次 {m['full_freq']}；"
                     f"{'registry 已收' if m['full'] in registry_words else 'registry 未收，需补登'}）")
    lines += [
        "",
        "## 六、apply 语义（本轮默认不执行）",
        "",
        "- `--apply` 只处理 **唯一新推断**（source=新推断）的未挂管道单字；",
        "  替换 `〖@X〗` → `〖@X|全名〗`，已挂管道者不重复、歧义者不动。",
        "- 写前对每回做备份（`backup/tagged/<书>/`），写后 `symbols.strip_markup` 断言原文不变、",
        "  令牌数不变、每条映射替换数 > 0，任一失败即回滚该回。",
        "",
        f"- 机读结果：`logs/single_char_names/{label}.json`",
        "",
    ]
    path = LOG_DIR / f"{label}.md"
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    payload = {
        "book": book, "generated": stamp, "params": params,
        "canonical_single": canonical_source,
        "chapters": [f"{c:03d}" for c in chapters],
        "summary": {"mappings": len(mappings), "piped": len(piped),
                    "inferred": len(inferred), "ambiguous": len(ambiguous),
                    "unmatched": len(unmatched), "warnings": len(warnings),
                    "not_in_registry": len(not_in_registry),
                    "cross_chapter_conflicts": conflicts},
        "mappings": mappings, "ambiguous": ambiguous, "unmatched": unmatched,
        "warnings": warnings,
    }
    io.open(LOG_DIR / f"{label}.json", "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    return path


def apply_inferred(book: str, results: list[dict]) -> dict:
    """只对唯一新推断插管道；备份 + 剥标断言 + 令牌数断言 + 逐回校验。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / book
    backup_dir.mkdir(parents=True, exist_ok=True)
    stats = {"chapters": 0, "inserted": 0, "rolled_back": []}
    for r in results:
        inferred = [m for m in r["mappings"] if m["source"] == "新推断"]
        if not inferred:
            continue
        chapter = r["chapter"]
        fpath = config.tagged_path(book, int(chapter))
        old = io.open(fpath, encoding="utf-8").read()
        backup = backup_dir / f"{fpath.name}.{stamp}.bak"
        io.open(backup, "w", encoding="utf-8", newline="\n").write(old)
        by_char = {m["char"]: m["full"] for m in inferred}
        inserted = 0

        def repl(m):
            nonlocal inserted
            layer, code, body, disp, note, err = symbols.parse_token(m.group(0))
            if layer == "entity" and code == "@" and disp in by_char and not note:
                inserted += 1
                return symbols.BRACKETS["entity"][0] + "@" + disp + "|" + by_char[disp] \
                    + symbols.BRACKETS["entity"][1]
            return m.group(0)

        new = symbols.TOKEN_RE.sub(repl, old)
        problems = []
        if symbols.strip_markup(new) != symbols.strip_markup(old):
            problems.append("剥标后正文不一致")
        if len(list(symbols.TOKEN_RE.finditer(new))) != len(list(symbols.TOKEN_RE.finditer(old))):
            problems.append("令牌数变化")
        if inserted != len(inferred):
            problems.append(f"替换 {inserted} ≠ 映射 {len(inferred)}")
        if problems:
            io.open(fpath, "w", encoding="utf-8", newline="\n").write(old)
            stats["rolled_back"].append(f"{chapter}: {'；'.join(problems)}")
            continue
        io.open(fpath, "w", encoding="utf-8", newline="\n").write(new)
        stats["chapters"] += 1
        stats["inserted"] += inserted
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="C19 单字人名映射体检与推断（默认只出报告）")
    ap.add_argument("--book", default=config.PILOT_BOOK)
    ap.add_argument("--chapters", default="all", help="all / 1-32 / 005,006（默认 all）")
    ap.add_argument("--apply", action="store_true",
                    help="可选：仅对唯一新推断插管道（备份+剥标断言+逐回校验）")
    ap.add_argument("--canonical-single", default=str(CANONICAL_SINGLE_PATH),
                    help="单字即全名名单 JSON（缺省 wordlists/single_char_canonical.json）")
    args = ap.parse_args()

    canonical_single, canonical_source = load_canonical_single(Path(args.canonical_single))
    registry_words = load_registry_words()
    all_chapters = [int(p.name.split(".")[0]) for p in
                    sorted(config.DIR_TAGGED.joinpath(args.book).glob("*.tagged.md"))
                    if p.name.split(".")[0].isdigit()]
    if not all_chapters:
        raise SystemExit(f"[ERROR] 未找到 {args.book} 的 tagged 回目")
    chapters = parse_chapters(args.chapters) or all_chapters
    params = {"book": args.book, "chapters": args.chapters, "apply": args.apply,
              "total_chapters": len(all_chapters)}
    print(f"语料 {len(chapters)} 回；CANONICAL_SINGLE：{canonical_source}")

    results = []
    for ch in chapters:
        fpath = config.tagged_path(args.book, ch)
        if not fpath.exists():
            print(f"  [WARN] 缺 {ch:03d}.tagged.md")
            continue
        info = collect_chapter(fpath)
        r = infer_chapter(f"{ch:03d}", info, canonical_single)
        results.append(r)
        print(f"  {ch:03d}: 映射 {len(r['mappings'])}（新推断 "
              f"{sum(1 for m in r['mappings'] if m['source'] == '新推断')}）"
              f" / 歧义 {len(r['ambiguous'])} / 无匹配 {len(r['unmatched'])}")

    report_path = write_report(args.book, chapters, params, canonical_source,
                               results, registry_words)
    total = sum(len(r["mappings"]) for r in results)
    inferred = sum(1 for r in results for m in r["mappings"] if m["source"] == "新推断")
    print(f"\n合计映射 {total} 条（其中新推断 {inferred}）；报告：{report_path}")
    if args.apply:
        stats = apply_inferred(args.book, results)
        print(f"--apply：{stats['chapters']} 回 / 插入 {stats['inserted']} 处；"
              f"回滚 {stats['rolled_back'] or '无'}")
    else:
        print("（默认模式：只出报告，tagged 未改动）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
