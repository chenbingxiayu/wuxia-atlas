# -*- coding: utf-8 -*-
"""版权闸门：发布产物（dist/）L0/L1 合规校验。

规则（版权分层见 kb/README 与《网站完整设计方案》§六）：
  1) 任何语料整行（章回版正文行，长度 ≥20 字）不得出现在 dist 文本中；
     白名单：回目行（"第N回…"，短句元数据，随回目页发布）。
  2) dist 中不得出现语料目录引用（章回版/、tagged/、reader/）。
     **provenance 白名单**（2026-11-05 部署阻断③）：仅豁免 JSON 中 `meta.*` 且键名属
     provenance 集合（source/source_detail/notes/field_gaps/copyright/policy/generated…）
     的**出处说明字符串**——这些是"数据从哪来"的元信息，不是语料正文/引文；
     正文、事件、摘录、数组内容等非 meta.provenance 字段**不豁免**。
     可用 `--no-provenance-whitelist` 复现旧口径（审计/回归用）。
  3) 只扫描文本类扩展名（.html/.css/.js/.svg/.txt/.xml/.json/.webmanifest）。
  3b) 内部链接必须带 base 前缀（项目子路径部署，href="/x" 会 404）；第二参数为 base 段。

实现：语料行前 12 字建索引 → dist 文本滑窗查命中 → 命中后全文复核；
     rule2 对 JSON 做路径感知扫描（provenance 豁免），非 JSON 按原文扫描。

脚本位置：`Wuxiaxiaoshuo/scripts/copyright_gate.py`（仓库根 scripts/，非 wuxia-kb/scripts/）。
用法（二选一，第二参数必须是 base 段 `wuxia-atlas`）：
  cd Wuxiaxiaoshuo && python scripts/copyright_gate.py site/dist wuxia-atlas
  cd Wuxiaxiaoshuo/site && python ..\\scripts\\copyright_gate.py dist wuxia-atlas
"""
import io
import json
import re
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
ZH = ROOT / "章回版"
TEXT_EXT = {".html", ".css", ".js", ".svg", ".txt", ".xml", ".json", ".webmanifest"}
CORPUS_TOKENS = ("章回版/", "tagged/", "reader/")
K = 12                     # 索引 n-gram 长度
MIN_LINE = 20              # 语料行纳入检测的最小长度
TITLE_RE = re.compile(r"^(?:第[〇○零一二三四五六七八九十百千两0-9]+回|楔子)")

# provenance 白名单：仅当 JSON 路径位于顶层 meta 下、且路径中出现这些键名时豁免 rule2。
# 覆盖现网 6 个 data JSON 的 meta.source / meta.notes / meta.field_gaps 等出处说明；
# 不覆盖正文/引文/数组内容（如 dossiers/e vents 的文本字段）。
PROVENANCE_KEYS = {
    "source", "source_detail", "sources", "provenance", "generated", "generated_at",
    "generated_by", "notes", "note", "field_gaps", "copyright", "policy", "schema",
    "build", "build_order", "snapshot", "tool", "skill", "spec",
}


def corpus_lines(corpus_root: Path | None = None):
    """(前12字 -> 整行) 索引；白名单行集合；扫描行数。"""
    root = Path(corpus_root) if corpus_root else ZH
    index: dict = {}
    whitelist: set = set()
    n = 0
    for fp in root.rglob("*.txt"):
        with open(fp, encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if len(line) < MIN_LINE:
                    continue
                n += 1
                if TITLE_RE.match(line):
                    whitelist.add(line)
                    continue
                index.setdefault(line[:K], line)
    return index, whitelist, n


def split_json_strings(obj):
    """JSON → (provenance_exempt: list[str], content: list[str])。路径感知，只豁免 meta.provenance。"""

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, path + (str(k),))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + (str(i),))
        elif isinstance(node, str):
            under_meta = any(seg == "meta" for seg in path)
            is_prov = any(seg in PROVENANCE_KEYS for seg in path)
            if under_meta and is_prov:
                exempt.append(node)
            else:
                content.append(node)

    exempt, content = [], []
    walk(obj, ())
    return exempt, content


def scan(dist: Path, base_seg: str = "", provenance_whitelist: bool = True,
         corpus_root: Path | None = None) -> dict:
    """执行三道规则；返回结构化结果（供 CLI 与 --selftest 复用）。"""
    index, whitelist, n_corpus = corpus_lines(corpus_root)
    full_parts, content2_parts, names = [], [], []
    exempt_counts = {tok: 0 for tok in CORPUS_TOKENS}
    json_files = json_parsed = 0
    for fp in sorted(dist.rglob("*")):
        if not fp.is_file() or fp.suffix.lower() not in TEXT_EXT:
            continue
        try:
            raw = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        names.append(str(fp.relative_to(dist)))
        full_parts.append(raw)
        if fp.suffix.lower() == ".json":
            json_files += 1
            try:
                payload = json.loads(raw)
                json_parsed += 1
                exempt, content = split_json_strings(payload)
                for s in exempt:
                    for tok in CORPUS_TOKENS:
                        exempt_counts[tok] += s.count(tok)
                content2_parts.append("\n".join(content))
            except Exception:
                content2_parts.append(raw)      # JSON 解析失败 → 退回原文扫描（保守）
        else:
            content2_parts.append(raw)

    text = "\n".join(full_parts)
    rule2_text = text if not provenance_whitelist else "\n".join(content2_parts)

    violations = []
    hits_whitelisted = 0
    rule1_hits = 0
    for i in range(len(text) - K + 1):
        window = text[i:i + K]
        line = index.get(window)
        if line is None:
            continue
        if line in whitelist:
            hits_whitelisted += 1
            continue
        if line in text:                    # 语料整行出现在产物中 → 违规
            rule1_hits += 1
            if len(violations) < 10:
                violations.append(("rule1", f"语料行「{line[:38]}…」",
                                   f"上下文:「…{text[max(0, i - 20):i + 30]}…」"))
            if rule1_hits >= 10:
                break

    # 规则 2：语料目录引用（provenance 白名单只作用于 JSON meta.* provenance 字符串）
    rule2_hits = 0
    for tok in CORPUS_TOKENS:
        cnt = rule2_text.count(tok)
        if cnt:
            rule2_hits += cnt
            violations.append(("rule2", f"路径引用: {tok} × {cnt}", "（dist 文本）"))

    # 规则 3：内部链接必须带 base 前缀
    base_seg = base_seg.strip("/")
    rule3_hits = 0
    for m in re.finditer(r'href="/(?!/)([^"]{0,60})"', text):
        if base_seg and m.group(0).startswith(f'href="/{base_seg}'):
            continue
        rule3_hits += 1
        if len(violations) < 10:
            violations.append(("rule3", f'内部链接缺 base 前缀: href="/{m.group(1)}"', "（dist HTML）"))

    return {
        "dist": str(dist),
        "base_seg": base_seg,
        "provenance_whitelist": provenance_whitelist,
        "corpus_lines": n_corpus,
        "corpus_whitelist": len(whitelist),
        "files": len(names),
        "text_kb": len(text) // 1024,
        "json_files": json_files,
        "json_parsed": json_parsed,
        "rule1_corpus_leaks": rule1_hits,
        "rule1_whitelisted_hits": hits_whitelisted,
        "rule2_hits": rule2_hits,
        "provenance_exempt": exempt_counts,
        "rule3_hits": rule3_hits,
        "violations": violations,
        "ok": not violations,
    }


def print_result(res: dict) -> None:
    print(f"语料行扫描 {res['corpus_lines']} 行（≥{MIN_LINE} 字，回目行白名单 {res['corpus_whitelist']}），"
          f"产物文本 {res['text_kb']} KB / {res['files']} 文件"
          + (f"（JSON {res['json_files']}，解析 {res['json_parsed']}）" if res["json_files"] else ""))
    if res["provenance_whitelist"]:
        ex = res["provenance_exempt"]
        ex_s = "、".join(f"{k}×{v}" for k, v in ex.items() if v)
        print(f"provenance 白名单：豁免 JSON meta.provenance 出处说明 {ex_s or '0 处'}"
              f"（source/notes/field_gaps 等，不豁免正文/引文）")
    else:
        print("provenance 白名单：已禁用（--no-provenance-whitelist，旧口径）")
    print(f"规则 1 语料整行泄漏：{res['rule1_corpus_leaks']}（回目白名单命中 {res['rule1_whitelisted_hits']}）；"
          f"规则 2 路径引用：{res['rule2_hits']}；规则 3 链接缺 base：{res['rule3_hits']}")
    if res["violations"]:
        print(f"\n✗ 版权闸门未通过：{len(res['violations'])} 类/处违规（最多显示 10 条）")
        for kind, v, ctx in res["violations"]:
            print(f"  - [{kind}] {v} {ctx}")
        return
    print(f"✓ 版权闸门通过：规则 1 语料整行泄漏 0（回目白名单 {res['rule1_whitelisted_hits']} 处）、"
          f"规则 2/3 PASS")


def selftest() -> int:
    """合成语料 + 合成 dist：覆盖 rule1/rule2 白名单/rule3，不写真实站点。"""
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        ok = ok and bool(cond)

    print("[copyright_gate selftest]")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        corpus = td / "章回版" / "测试书"
        corpus.mkdir(parents=True)
        long_line = "这是一句用于版权闸门自检的完整语料正文行，长度超过二十个字以便被规则一捕获。"
        (corpus / "001.txt").write_text("第一回 测试回\n" + long_line + "\n", encoding="utf-8")
        dist = td / "dist"
        (dist / "data").mkdir(parents=True)
        payload = {
            "meta": {"source": "tagged/struct + registry/concordance", "notes": ["见 tagged/<书>/*.tagged.md"],
                     "field_gaps": ["口径：tagged/ 标注"]},
            "items": [{"body": "正文里出现 tagged/ 应被规则 2 捕获", "excerpt": "引文 tagged/ 不豁免"},
                      {"meta": {"source": "子对象 tagged/x 也应豁免（meta.provenance）"}},
                      {"body": "这是正文行：" + long_line}],
        }
        (dist / "data" / "d.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (dist / "page.html").write_text(
            '<html><body><a href="/no-base/x">x</a><a href="/wuxia-atlas/ok">ok</a>'
            '<a href="/other/y">y</a><p>tagged/ 出现在 HTML 应被捕获</p></body></html>',
            encoding="utf-8")
        # 1) 白名单开启：meta.provenance 豁免；正文/引文/HTML 仍捕获；rule3 只抓缺 base
        r = scan(dist, "wuxia-atlas", provenance_whitelist=True, corpus_root=td / "章回版")
        check("whitelist: meta.provenance tagged/ 被豁免", r["provenance_exempt"]["tagged/"] >= 3,
              str(r["provenance_exempt"]))
        check("whitelist: 正文 tagged/ 仍被规则2捕获", r["rule2_hits"] >= 3, f"rule2_hits={r['rule2_hits']}")
        check("whitelist: rule1 语料整行泄漏被捕获", r["rule1_corpus_leaks"] >= 1,
              f"leaks={r['rule1_corpus_leaks']}")
        check("whitelist: rule3 只抓缺 base 链接", r["rule3_hits"] == 2, f"rule3={r['rule3_hits']}")
        check("whitelist: 整体未通过", r["ok"] is False)
        # 2) 白名单关闭（旧口径）：meta.provenance 也计入 rule2
        r_old = scan(dist, "wuxia-atlas", provenance_whitelist=False, corpus_root=td / "章回版")
        check("no-whitelist: rule2 命中更多（旧口径）", r_old["rule2_hits"] > r["rule2_hits"],
              f"{r_old['rule2_hits']} > {r['rule2_hits']}")
        # 3) 干净 dist：三规则全 PASS
        clean = td / "clean"
        clean.mkdir()
        (clean / "i.html").write_text('<html><a href="/wuxia-atlas/x">x</a><p>无违规正文</p></html>',
                                      encoding="utf-8")
        rc = scan(clean, "wuxia-atlas", provenance_whitelist=True, corpus_root=td / "章回版")
        check("clean dist: 闸门 PASS", rc["ok"] is True and not rc["violations"], str(rc["violations"]))
    print(f"[copyright_gate selftest] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    args = [a for a in sys.argv[1:]]
    if "--selftest" in args:
        return selftest()
    whitelist = "--no-provenance-whitelist" not in args
    positions = [a for a in args if not a.startswith("--")]
    if not positions:
        print("usage: python scripts/copyright_gate.py <dist_dir> [base_seg] [--no-provenance-whitelist] [--selftest]")
        return 2
    arg = Path(positions[0])
    dist = arg if arg.is_absolute() else Path.cwd() / arg
    # 部署子路径默认与 site/astro.config.mjs 的 base 一致；缺省时 rule3 会全量误报
    base_seg = positions[1] if len(positions) > 1 else "wuxia-atlas"
    res = scan(dist, base_seg, provenance_whitelist=whitelist)
    print_result(res)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
