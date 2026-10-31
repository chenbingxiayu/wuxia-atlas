#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标注完整性校验器（对应 shiji-kb SKILL_01a 标注完整性维护）

规则（标注规范-v0 §一）：
  1. 去掉全部标注/结构围栏/YAML 头后，必须与 章回版/<书>/ 原文逐行逐字一致；
  2. 标记必须配对闭合、不得嵌套；
  3. 类型码必须在白名单内（实体 @=◆;%☆•+[§ ，动词 ◉◈○ ，成语 ※）。

用法：
  python scripts/lint_annotation.py                # 批量校验 kb/tagged/ 下全部文件
  python scripts/lint_annotation.py <tagged.md>    # 校验单个文件
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAGGED_ROOT = os.path.join(ROOT, "kb", "tagged")
ORIG_ROOT = os.path.join(ROOT, "章回版")

ENTITY_CODES = set("@=◆;%☆•+[§")         # v0.1 新增 [ = 秘籍/文书；v0.2 新增 § = 丹药/药物成品
VERB_CODES = set("◉◈○▲◇")                # v0.1 新增 ▲ = 擒控，◇ = 传艺
IDIO_CODE = "※"

PAIRS = [("〖", "〗"), ("〘", "〙"), ("⟦", "⟧")]
MARK_RE = re.compile(r"(〖[^〖〗]*〗|〘[^〘〙]*〙|⟦[^⟦⟧]*⟧)")


def strip_line(line, errs, where):
    """去掉一行中的全部标注，返回纯文本。"""
    def repl(m):
        token = m.group(0)
        open_c, close_c = token[0], token[-1]
        inner = token[1:-1]
        if any(o in inner for o, _ in PAIRS) or any(c in inner for _, c in PAIRS):
            errs.append(f"{where}: 嵌套标注 {token!r}")
            return inner
        if open_c == "〖":
            code, surface = inner[0], inner[1:]
            if code not in ENTITY_CODES:
                errs.append(f"{where}: 非法实体类型码 {code!r} in {token!r}")
            if "|" in surface:
                parts = surface.split("|")
                if len(parts) != 2 or not parts[1]:
                    errs.append(f"{where}: 规范名格式错误 {token!r}")
                surface = parts[0]
            return surface
        if open_c == "⟦":
            code, surface = inner[0], inner[1:]
            if code not in VERB_CODES:
                errs.append(f"{where}: 非法动词类码 {code!r} in {token!r}")
            return surface
        # 〘…〙
        if inner and inner[0] != IDIO_CODE:
            errs.append(f"{where}: 非法成语码 {inner[:1]!r} in {token!r}")
        return inner[1:] if inner else ""

    return MARK_RE.sub(repl, line)


def check_balance(line, errs, where):
    for o, c in PAIRS:
        if line.count(o) != line.count(c):
            errs.append(f"{where}: {o}{c} 不配对（{line.count(o)}/{line.count(c)}）")


def load_tagged(path, errs):
    """返回 (正文行列表, 元数据dict)。"""
    with open(path, encoding="utf-8") as f:
        raw = f.read().split("\n")
    meta, body = {}, []
    if raw and raw[0].strip() == "---":
        try:
            end = raw.index("---", 1)
        except ValueError:
            errs.append(f"{path}: YAML 头未闭合")
            return [], meta
        for ln in raw[1:end]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                meta[k.strip()] = v.strip()
        body = raw[end + 1:]
    else:
        errs.append(f"{path}: 缺 YAML 头（应以 --- 开头）")
        body = raw
    # 去围栏行，去标记
    out = []
    for i, ln in enumerate(body, 1):
        if re.match(r"^:::(\s+\S+)?\s*$", ln):
            continue
        check_balance(ln, errs, f"{path}:{i}")
        out.append(strip_line(ln, errs, f"{path}:{i}"))
    return out, meta


def find_original(tagged_path):
    name = os.path.basename(tagged_path)
    book = os.path.basename(os.path.dirname(tagged_path))
    prefix = name[:3]
    odir = os.path.join(ORIG_ROOT, book)
    if not os.path.isdir(odir):
        return None
    for fn in os.listdir(odir):
        if fn.startswith(prefix) and fn.endswith(".txt"):
            return os.path.join(odir, fn)
    return None


def lint(tagged_path):
    errs = []
    tagged_lines, meta = load_tagged(tagged_path, errs)
    orig_path = find_original(tagged_path)
    if not orig_path:
        errs.append(f"{tagged_path}: 找不到对应原文（章回版/{meta.get('book', '?')}/）")
        return errs, {}
    with open(orig_path, encoding="utf-8") as f:
        orig_lines = f.read().split("\n")
    # 原文行首尾原样比较；tagged 保留空行结构
    if len(tagged_lines) != len(orig_lines):
        errs.append(f"{tagged_path}: 行数不符 tagged={len(tagged_lines)} orig={len(orig_lines)}")
    for i, (t, o) in enumerate(zip(tagged_lines, orig_lines), 1):
        if t != o:
            errs.append(
                f"{tagged_path}:{i} 内容不一致\n  tagged: {t[:60]!r}\n  orig  : {o[:60]!r}"
            )
            break
    # 统计（供反思用）
    with open(tagged_path, encoding="utf-8") as f:
        text = f.read()
    stats = {}
    for m in MARK_RE.finditer(text):
        token = m.group(0)
        code = token[1]
        stats[code] = stats.get(code, 0) + 1
    return errs, stats


def main():
    targets = sys.argv[1:]
    if not targets:
        for book in sorted(os.listdir(TAGGED_ROOT)):
            bdir = os.path.join(TAGGED_ROOT, book)
            if os.path.isdir(bdir):
                targets += [os.path.join(bdir, f) for f in sorted(os.listdir(bdir))
                            if f.endswith(".tagged.md")]
    total_err = 0
    for t in targets:
        errs, stats = lint(t)
        stat_s = " ".join(f"{k}:{v}" for k, v in sorted(stats.items()))
        if errs:
            total_err += len(errs)
            print(f"FAIL {os.path.relpath(t, ROOT)}  [{stat_s}]")
            for e in errs[:6]:
                print("   ", e)
            if len(errs) > 6:
                print(f"    ...共 {len(errs)} 处")
        else:
            print(f"PASS {os.path.relpath(t, ROOT)}  [{stat_s}]")
    print(f"\n{'存在 ' + str(total_err) + ' 处错误' if total_err else '全部通过'}")
    sys.exit(1 if total_err else 0)


if __name__ == "__main__":
    main()
