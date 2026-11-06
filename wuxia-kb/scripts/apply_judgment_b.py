# -*- coding: utf-8 -*-
"""judgment 裁决执行器 B（task-7 / fix-judg-b 口径，docs/45；换书标准工具，docs/50 S12 正式化）。

输入：decisions JSON（默认 logs/qa/judgment_decisions_b.json；书名取 JSON 内 book 字段）
动作：
  - remove = 摘括号与类型码、保留显示串（管道标签一并摘除）；
  - recode = 仅改域码（实体重编码到非 @/% 时自动摘管道标签；动词保留管道注记）；
  - keep   = 不写盘，仅做 token 存在性与 context 一致性核验。

纪律：
  * 按 (chapter, pn, layer, display, occ) 定位；用 decisions.context 的 ⟪token⟫ 窗口做二次校验，
    防止 occ 漂移/文件被他人改动后误改；
  * 同一段多条目一次性在原文坐标上从后往前替换，避免坐标失效；
  * 逐段断言 symbols.strip_markup(new) == symbols.strip_markup(old)（正文零增删改）；
  * --apply 前备份到 logs/backup/judgment_b/<ts>/；存在失败条目则整体不写盘（只报清单，不崩溃）。

用法：
  python -X utf8 scripts/apply_judgment_b.py --dry-run [--decisions 路径]
  python -X utf8 scripts/apply_judgment_b.py --apply [--allow-context-drift]
"""
import argparse
import difflib
import hashlib
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config      # noqa: E402
import symbols     # noqa: E402

DEC_PATH = config.DIR_LOGS / "qa" / "judgment_decisions_b.json"
BACKUP_DIR = config.DIR_LOGS / "backup" / "judgment_b"
PARA_RE = re.compile(r"^\[(\d+)\] (.*)$", re.M)
TOKEN_RE = re.compile(
    r"([\u3016\u27e6])(.)([^\u3016\u3017\u27e6\u27e7]*?)([\u3017\u27e7])")
OPEN = {"〖": "〗", "⟦": "⟧"}
LAYERS = {
    "quantity_boundary": "〖",
    "time_boundary": "〖",
    "fence_entity_real_only": "〖",
    "verb_wordlist_candidate": "⟦",
}
PIPE_OK_ENTITY = {"@", "%"}      # 实体层仅 @/% 允许管道
CTX = 42


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_paras(book, ch):
    path = config.tagged_path(book, ch)
    text = io.open(path, encoding="utf-8").read()
    paras = {int(m.group(1)): m.group(2) for m in PARA_RE.finditer(text)}
    return Path(path), text, paras


def iter_tokens(para, layer):
    for m in TOKEN_RE.finditer(para):
        if m.group(1) != layer:
            continue
        if OPEN[layer] != m.group(4):
            continue
        yield m


def make_token(layer, code, body):
    display, sep, note = body.partition("|")
    if layer == "〖":
        keep_note = sep and code in PIPE_OK_ENTITY
    else:
        keep_note = bool(sep)          # 动词管道＝完成状态/词义注记，保留
    out = code + display
    if keep_note:
        out += "|" + note
    return OPEN_OPEN[layer] + out + OPEN[layer]


OPEN_OPEN = {"〖": "〖", "⟦": "⟦"}

# --allow-context-drift：主定位 (chapter,pn,layer,display,occ) 命中但 context 窗口
# 因前序批次已改同段而漂移时，降级为告警不阻断（2026-11-05 A 批先应用后需要）。
TOLERANT = False
CTX_DRIFT = []


def locate(para, layer, display, occ, context):
    """返回 (match, err)。occ 1-based；context 用 ⟪token⟫ 窗口二次校验。"""
    cands = [m for m in iter_tokens(para, layer)
             if m.group(3).split("|")[0] == display]
    if len(cands) < occ:
        return None, f"候选不足（{len(cands)} < occ={occ}）"
    m = cands[occ - 1]
    ctx = (para[max(0, m.start() - CTX):m.start()] + "⟪" + m.group(0) + "⟫"
           + para[m.end():m.end() + CTX])
    if context and ctx != context:
        if TOLERANT:
            CTX_DRIFT.append({"display": display, "occ": occ,
                              "expected": context, "actual": ctx})
            return m, None
        return None, "context 不匹配（文件可能已被改动/occ 漂移）"
    return m, None


def plan_paragraph(para, decs):
    """返回 (new_para, edits, failures)。decs 为同一段内的裁决条目。"""
    edits, failures = [], []
    for d in decs:
        layer = LAYERS[d["type"]]
        m, err = locate(para, layer, d["display"], d["occ"], d.get("context"))
        if err:
            failures.append({**d, "error": err})
            continue
        edits.append((m, d))
    # 重叠检查
    spans = sorted((m.start(), m.end(), d) for m, d in edits)
    for (s1, e1, d1), (s2, e2, d2) in zip(spans, spans[1:]):
        if s2 < e1:
            failures.append({**d2, "error": f"与另一条目区间重叠（{s1}-{e1}）"})
    applied = []
    new = para
    for m, d in sorted(edits, key=lambda x: -x[0].start()):
        body = m.group(3)
        if d["action"] == "remove":
            repl = body.split("|")[0]
        elif d["action"] == "recode":
            code = d.get("new_code")
            if not code or code == m.group(2):
                failures.append({**d, "error": "recode 缺少有效 new_code"})
                continue
            repl = make_token(LAYERS[d["type"]], code, body)
        else:  # keep
            continue
        new = new[:m.start()] + repl + new[m.end():]
        applied.append((d, m.group(0), repl))
    return new, applied, failures


def short_diff(old, new, width=34):
    sm = difflib.SequenceMatcher(None, old, new)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            return (old[max(0, i1 - width):i2 + width].replace("\n", "⏎"),
                    new[max(0, j1 - width):j2 + width].replace("\n", "⏎"))
    return "", ""


def main() -> int:
    ap = argparse.ArgumentParser(description="judgment 裁决执行器 B（层定位 + context 窗口校验）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="只打印 diff（默认）")
    ap.add_argument("--allow-context-drift", action="store_true",
                    help="context 窗口漂移时降级为告警（A 批先应用后使用）")
    g.add_argument("--apply", action="store_true", help="写盘（先备份）")
    ap.add_argument("--decisions", default=str(DEC_PATH))
    args = ap.parse_args()
    global TOLERANT
    TOLERANT = bool(getattr(args, 'allow_context_drift', False))
    apply_mode = bool(args.apply)

    dec_path = Path(args.decisions)
    if not dec_path.exists():
        print(f"[FATAL] 决策文件不存在：{dec_path}")
        return 2
    data = json.load(io.open(dec_path, encoding="utf-8"))
    book = data["book"]
    decisions = data["decisions"]
    by_ch = {}
    for d in decisions:
        by_ch.setdefault(d["chapter"], []).append(d)

    failures = []
    file_plans = {}      # path -> {"old_text","new_text","changes":[...]}
    keep_ok = 0
    for ch in sorted(by_ch):
        try:
            path, text, paras = load_paras(book, ch)
        except Exception as e:                              # noqa: BLE001
            failures.append({"chapter": ch, "error": f"读取失败：{e}"})
            continue
        per_para = {}
        for d in by_ch[ch]:
            per_para.setdefault(d["pn"], []).append(d)
        new_text = text
        changes = []
        for pn in sorted(per_para):
            para = paras.get(pn)
            if para is None:
                failures.extend({**d, "error": f"[{pn}] 段不存在"}
                                for d in per_para[pn])
                continue
            new_para, applied, fails = plan_paragraph(para, per_para[pn])
            failures.extend({**{k: v for k, v in f.items() if k != "context"},
                             "chapter": ch, "pn": pn} for f in fails)
            keep_ok += sum(1 for d in per_para[pn] if d["action"] == "keep")
            if new_para != para:
                # 正文零增删改断言
                try:
                    assert symbols.strip_markup(new_para) == symbols.strip_markup(para)
                except AssertionError:
                    failures.append({"chapter": ch, "pn": pn,
                                     "error": "strip_markup 不一致（正文被改动）"})
                    continue
                old_line, new_line = f"[{pn}] {para}", f"[{pn}] {new_para}"
                if text.count(old_line) != 1:
                    failures.append({"chapter": ch, "pn": pn,
                                     "error": "段落在文件中定位不唯一"})
                    continue
                new_text = new_text.replace(old_line, new_line)
                changes.extend({"pn": pn, "display": d["display"],
                                "action": d["action"], "occ": d["occ"],
                                "old_token": tok, "new_token": repl}
                               for d, tok, repl in applied)
        if new_text != text:
            file_plans[path] = {"old_text": text, "new_text": new_text,
                                "changes": changes, "chapter": ch}

    n_remove = sum(1 for d in decisions if d["action"] == "remove")
    n_recode = sum(1 for d in decisions if d["action"] == "recode")
    print(f"== {book} judgment 决策执行（{'APPLY' if apply_mode else 'DRY-RUN'}） ==")
    print(f"决策条目：{len(decisions)}（remove {n_remove} / recode {n_recode} / "
          f"keep {len(decisions) - n_remove - n_recode}）")
    print(f"命中文件：{len(file_plans)}；保留核验通过：{keep_ok}；失败：{len(failures)}")
    for path in sorted(file_plans):
        info = file_plans[path]
        print(f"\n--- {path.name}（{len(info['changes'])} 处改动）")
        for c in info["changes"]:
            print(f"  [{c['pn']}] {c['action']:<6} {c['old_token']} ⇒ {c['new_token']}"
                  f"   （{c['display']}#{c['occ']}）")
        old_ctx, new_ctx = short_diff(info["old_text"], info["new_text"])
        print(f"  diff≈ …{old_ctx}…  ⇒  …{new_ctx}…")

    if failures:
        print(f"\n== 失败清单（{len(failures)} 条，未写盘条目不受影响） ==")
        for f in failures:
            print(f"  CH{f.get('chapter', '?')}[{f.get('pn', '?')}] "
                  f"{f.get('type', '')} {f.get('display', '')} "
                  f"occ={f.get('occ', '')} → {f.get('error')}")
        if apply_mode:
            print("\n[abort] 存在失败条目，本次 --apply 不写盘；先修正定位问题。")
            return 1
    if not apply_mode:
        print("\n(dry-run：未写盘；确认后加 --apply)")
        return 0
    if not file_plans:
        print("\n无改动（全部为 keep），无需写盘。")
        return 0

    # ---- 备份 + 写盘 ----
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = BACKUP_DIR / ts
    manifest = {"book": book, "ts": ts, "source": str(dec_path),
                "files": [], "changes": []}
    for path in file_plans:
        dst = bk / book / path.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(Path(path).read_bytes())
        manifest["files"].append({"path": path.name,
                                  "sha256_before": sha256(path),
                                  "backup": str(dst)})
        manifest["changes"].extend(file_plans[path]["changes"])
    for path in file_plans:
        Path(path).write_text(file_plans[path]["new_text"], encoding="utf-8", newline="")
        print(f"written: {path.name}")
    for entry, path in zip(manifest["files"], file_plans):
        entry["sha256_after"] = sha256(path)
    (bk / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"备份：{bk}")
    print(f"完成：{len(file_plans)} 文件 / "
          f"{sum(len(v['changes']) for v in file_plans.values())} 处 token 改动")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(main())
