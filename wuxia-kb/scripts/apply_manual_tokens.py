# -*- coding: utf-8 -*-
"""Session 内手工标注执行器（当前 Session 模型直标 · 稀疏令牌稿接入）。

定位：annotate_chapter_llm.py 的「LLM 语义判断」环节由当前 Session 模型直接完成
（不经外部 API 调用），本脚本承担其机械半区——与 API 执行器共用同一保真链：

  1) 稀疏令牌稿：每行 `pn<TAB>令牌体<TAB>序次`；令牌体如 `@铁摩勒`、`@铁兄|铁摩勒`、
     `⊠害死`、`%黄昏|时点`；序次 = 显示串（管道前部分）在该段文本中「未占用区间」的
     第几次出现（1 起始；`*` = 全部剩余出现）。同段内按稿中行序处理，已占用区间
     （既有令牌 + 本稿已插入）不参与计数——先标长区间、后标短区间即可正确消歧。
  2) 机械插入：只把标记包在原文字符区间外，正文零转写（DEF-02/09/14 免疫）；
  3) validate_and_repair + final_verify：直接复用 annotate_chapter_llm 同名函数；
  4) 修辞层：`--rhetoric-scan` 列候选 → 人工裁决 → `--rhetoric-verdicts <json>` 落标
     （复用 annotate_rhetoric_llm 的候选索引与 apply_marks，保持 raw|canonical 语义）。

增补模式：tagged 已存在时在既有令牌之外增量插入（既有令牌区间自动排除）。
安全：首次写盘前把既有 tagged 备份到 backup/manual_annotate/<书>/。
报告：logs/annotate/<书>/<NNN>.manual.report.txt + logs/token_usage/ 记账（provider=session，费用 0）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import annotate_chapter_llm as ac  # noqa: E402  复用保真链
import annotate_rhetoric_llm as rl  # noqa: E402  复用候选索引/裁决
import config  # noqa: E402

MODEL = "deepseek-v4.1-flash（当前 Session 模型直标 · opencode-go 订阅通道）"
PROVIDER = "session/opencode-go"

ENT_BR = ("〖", "〗")
VERB_BR = ("⟦", "⟧")
RHET_BR = ("〘", "〙")


def brackets_for(code: str):
    if code in ac.ENT_OK:
        return ENT_BR
    if code in ac.VERB_OK:
        return VERB_BR
    if code == "※":
        return RHET_BR
    raise SystemExit(f"[ERROR] 非法类型码 {code!r}（草稿令牌体以类型码开头）")


def load_draft(path: Path):
    """解析稀疏令牌稿 → {pn: [(body, occ), ...]}（保持稿内行序）。"""
    rows = {}
    for ln_no, raw in enumerate(io.open(path, encoding="utf-8"), 1):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            raise SystemExit(f"[ERROR] 草稿第 {ln_no} 行格式非法（需 3 列）：{line!r}")
        pn_s, body, occ_s = parts[0].strip(), parts[1].strip(), parts[2].strip()
        try:
            pn = int(pn_s)
        except ValueError:
            raise SystemExit(f"[ERROR] 草稿第 {ln_no} 行段号非法：{line!r}")
        occ = None if occ_s == "*" else int(occ_s)
        if occ is not None and occ < 1:
            raise SystemExit(f"[ERROR] 草稿第 {ln_no} 行序次非法：{line!r}")
        code = body[0] if body else ""
        brackets_for(code)  # 校验类型码
        rows.setdefault(pn, []).append((body, occ))
    return rows


def _overlaps(pos: int, end: int, claimed) -> bool:
    return any(not (end <= a or pos >= b) for a, b in claimed)


def insert_paragraph(text: str, rows, pn: int, report: list) -> str:
    """把一个段落的令牌稿插入该段当前文本；返回新文本。

    序次语义（绝对）：occ = 显示串在该段「未被既有令牌覆盖」的全文命中中的第几次
    出现（1 起始，与稿内行序无关；`*` = 全部剩余未占用命中）。目标命中若已被
    本稿先前行占用则报错（防同区间双标）。
    """
    edits, claimed = [], []
    for body, occ in rows:
        code = body[0]
        display = body.split("|", 1)[0][1:]  # 管道前、去掉类型码
        if not display:
            report.append(f"  [{pn}] 空显示串已丢弃：{body!r}")
            continue
        raw = rl.plain_hits(text, display, [])  # 不含既有令牌覆盖区的全文命中
        if occ is None:                      # `*` = 全部剩余未占用命中
            chosen = [h for h in raw if not _overlaps(h, h + len(display), claimed)]
        elif occ > len(raw):
            ctxs = [text[max(0, h - 10):h + len(display) + 10] for h in raw[:4]]
            report.append(f"  [{pn}] 定位失败（{display!r} 第 {occ} 次；命中 {len(raw)} 个）：{body!r} @ …"
                          + "…/…".join(ctxs) + "…")
            continue
        else:
            pos = raw[occ - 1]
            if _overlaps(pos, pos + len(display), claimed):
                report.append(f"  [{pn}] 目标已被占用（{display!r} 第 {occ} 次）：{body!r}")
                continue
            chosen = [pos]
        op, cl = brackets_for(code)
        tok = op + body + cl
        for pos in chosen:
            claimed.append((pos, pos + len(display)))
            edits.append((pos, pos + len(display), tok))
    if not edits:
        return text
    out = text
    for pos, end, tok in sorted(edits, key=lambda x: -x[0]):
        out = out[:pos] + tok + out[end:]
    if ac.strip_all(out) != ac.strip_all(text):
        report.append(f"  [{pn}] 剥标不一致，整段回退")
        return text
    fixed, probs, dropped = ac.validate_and_repair(out, ac.strip_all(out))
    for p in probs[:5]:
        report.append(f"  [{pn}] 修复：{p}")
    for d in dropped[:5]:
        report.append(f"  [{pn}] 摘除：{d}")
    return fixed


def backup_existing(tagged_path: Path, book: str, ch: int):
    if not tagged_path.exists():
        return None
    bdir = config.ROOT / "backup" / "manual_annotate" / book
    bdir.mkdir(parents=True, exist_ok=True)
    dst = bdir / f"{ch:03d}.{dt.datetime.now():%Y%m%d_%H%M%S}.tagged.md"
    shutil.copy2(tagged_path, dst)
    return dst


def write_report(book: str, ch: int, lines_out: list):
    d = config.DIR_LOGS / "annotate" / book
    d.mkdir(parents=True, exist_ok=True)
    io.open(d / f"{ch:03d}.manual.report.txt", "w", encoding="utf-8", newline="\n").write(
        "\n".join(lines_out) + "\n")


def run_tokens(book: str, ch: int, draft_path: Path) -> int:
    struct_p = config.struct_path(book, ch)
    if not struct_p.exists():
        raise SystemExit(f"[ERROR] struct 缺失：{struct_p}（先跑 generate_pn_wuxia.py）")
    struct_lines, struct_paras = ac.read_struct(struct_p)
    tagged_path = config.DIR_TAGGED / book / f"{ch:03d}.tagged.md"

    if tagged_path.exists():
        text = io.open(tagged_path, encoding="utf-8").read()
        lines = text.split("\n")
        src = "tagged（增补模式）"
    else:
        lines = list(struct_lines)
        src = "struct（新建）"

    rows = load_draft(draft_path)
    report = [f"# 第 {ch:03d} 回 Session 直标执行报告",
              f"- 书：{book}；源：{src}；草稿：{draft_path.name}（{sum(len(v) for v in rows.values())} 行）",
              f"- 模型：{MODEL}；开始：{dt.datetime.now():%Y-%m-%d %H:%M:%S}", ""]

    unknown = [pn for pn in rows if pn not in struct_paras]
    if unknown:
        raise SystemExit(f"[ERROR] 草稿段号不存在于 struct：{unknown[:10]}")

    touched = 0
    for pn, prows in rows.items():
        # 定位该段在文件中的行（可能位于围栏内）
        li = next((i for i, ln in enumerate(lines)
                   if ac.PARA_RE.match(ln) and int(ac.PARA_RE.match(ln).group(1)) == pn), None)
        if li is None:
            report.append(f"  [{pn}] 行未找到，跳过")
            continue
        m = ac.PARA_RE.match(lines[li])
        new_para = insert_paragraph(m.group(2), prows, pn, report)
        if new_para != m.group(2):
            lines[li] = f"[{pn}] {new_para}"
            touched += 1

    tagged_text = "\n".join(lines)
    errs = ac.final_verify(tagged_text, struct_paras)
    if tagged_path.exists():
        backup_existing(tagged_path, book, ch)
    tagged_path.parent.mkdir(parents=True, exist_ok=True)
    io.open(tagged_path, "w", encoding="utf-8", newline="\n").write(tagged_text)

    final_text = io.open(tagged_path, encoding="utf-8").read()
    errs2 = ac.final_verify(final_text, struct_paras)
    stats = ac.summarize_tokens(final_text)
    report += ["", "## 结果",
               f"- 改写段数：{touched}；令牌：E={stats['E_total']} V={stats['V_total']} R={stats['R_total']}",
               f"- final_verify：{'PASS' if not errs2 else 'FAIL ' + '；'.join(errs2[:5])}",
               f"- 草稿问题 {len([r for r in report if '定位失败' in r or '摘除' in r or '空显示串' in r])} 条（见上）"]
    write_report(book, ch, report)

    td = config.DIR_LOGS / "token_usage"
    td.mkdir(parents=True, exist_ok=True)
    rec = {"task": "章回标注（session 直标）", "book": book, "chapter": ch,
           "model": MODEL, "provider": PROVIDER, "prompt": "SKILL_03a v1.10",
           "started_at": dt.datetime.now().isoformat(),
           "draft": str(draft_path), "touched_paras": touched,
           "tokens": {"E": stats["E_total"], "V": stats["V_total"], "R": stats["R_total"]},
           "cost_usd": 0.0, "reverify_pass": not errs2}
    io.open(td / f"annotate_{book}_{ch:03d}_{dt.datetime.now():%Y%m%d_%H%M%S}.json",
            "w", encoding="utf-8", newline="\n").write(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")

    print(f"  E={stats['E_total']} V={stats['V_total']} R={stats['R_total']}；"
          f"复验 {'PASS' if not errs2 else 'FAIL ' + '；'.join(errs2[:3])}；"
          f"问题 {len([r for r in report if '定位失败' in r or '摘除' in r or '空显示串' in r])} 条")
    for r in report[3:]:
        if r.strip():
            print(r)
    return 0 if not errs2 else 1


def run_rhetoric_scan(book: str, ch: int) -> int:
    ch3 = f"{ch:03d}"
    items = rl.load_items()
    info = rl.build_candidates([ch3], items, book, base_dir=config.DIR_TAGGED / book)[ch3]
    print(f"候选 {len(info['cands'])} 条：")
    for c in info["cands"]:
        print(f"{c['id']}\t[{c['pn']}] {c['raw']} → {c['canonical']}（{c['category']}，#{c['occ']}）…{c['ctx']}…")
    return 0


def run_rhetoric_verdicts(book: str, ch: int, vpath: Path) -> int:
    ch3 = f"{ch:03d}"
    items = rl.load_items()
    tagged_path = config.DIR_TAGGED / book / f"{ch3}.tagged.md"
    info = rl.build_candidates([ch3], items, book, base_dir=tagged_path.parent)[ch3]
    vmap = {int(k): v for k, v in json.loads(io.open(vpath, encoding="utf-8").read()).items()}
    verdict_by_pn = {}
    for c in info["cands"]:
        verdict_by_pn.setdefault(c["pn"], {})[c["id"]] = vmap.get(c["id"], "skip")
    n_ins, n_star, n_skip = rl.apply_marks(ch3, info, verdict_by_pn)
    backup_existing(tagged_path, book, ch)
    io.open(tagged_path, "w", encoding="utf-8", newline="\n").write("\n".join(info["lines"]))
    _struct_lines, struct_paras = ac.read_struct(config.struct_path(book, ch))
    errs = ac.final_verify(io.open(tagged_path, encoding="utf-8").read(), struct_paras)
    print(f"修辞层：候选 {len(info['cands'])}，落标 {n_ins}，☆报告 {n_star}，skip {n_skip}；"
          f"复验 {'PASS' if not errs else 'FAIL ' + '；'.join(errs[:3])}")
    return 0 if not errs else 1


def main():
    ap = argparse.ArgumentParser(description="Session 直标执行器：稀疏令牌稿插入 + 回锚校验 + 修辞裁决")
    ap.add_argument("--book", required=True)
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--draft", default=None, help="稀疏令牌稿 TSV（pn/body/occ）")
    ap.add_argument("--rhetoric-scan", action="store_true", help="列出修辞层候选")
    ap.add_argument("--rhetoric-verdicts", default=None, help="修辞裁决 JSON：{id: \"※\"|\"skip\"}")
    args = ap.parse_args()
    if args.rhetoric_scan:
        sys.exit(run_rhetoric_scan(args.book, args.chapter))
    if args.rhetoric_verdicts:
        sys.exit(run_rhetoric_verdicts(args.book, args.chapter, Path(args.rhetoric_verdicts)))
    if not args.draft:
        raise SystemExit("[ERROR] 需要 --draft 或 --rhetoric-scan/--rhetoric-verdicts")
    sys.exit(run_tokens(args.book, args.chapter, Path(args.draft)))


if __name__ == "__main__":
    main()
