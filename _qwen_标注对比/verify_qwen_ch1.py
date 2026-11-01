# -*- coding: utf-8 -*-
"""用项目自带的 lint_annotation.py 校验 _qwen_标注对比/ 下的新标注文件。"""
import io
import os
import shutil
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import lint_annotation  # noqa: E402

OUT_DIR = os.path.join(ROOT, "_qwen_标注对比")
VERIFY_DIR = os.path.join(OUT_DIR, "_verify")


def main():
    src = os.path.join(OUT_DIR, "001_第一回.tagged.md")
    book = "白发魔女传"
    vbook = os.path.join(VERIFY_DIR, book)
    vorig = os.path.join(VERIFY_DIR, "章回版", book)
    os.makedirs(vbook, exist_ok=True)
    os.makedirs(vorig, exist_ok=True)
    dst = os.path.join(vbook, "001_第一回.tagged.md")
    shutil.copy(src, dst)
    for fn in os.listdir(os.path.join(ROOT, "章回版", book)):
        if fn.startswith("001") and fn.endswith(".txt"):
            shutil.copy(os.path.join(ROOT, "章回版", book, fn), os.path.join(vorig, fn))

    lint_annotation.ORIG_ROOT = os.path.join(VERIFY_DIR, "章回版")
    errs, stats = lint_annotation.lint(dst)
    stat_s = " ".join(f"{k}:{v}" for k, v in sorted(stats.items()))
    if errs:
        print(f"FAIL [{stat_s}]")
        for e in errs:
            print("   ", e)
        sys.exit(1)
    print(f"PASS [{stat_s}]")

    # pipeline diff 同语义复核：逐行剥标 vs 原文
    perrs = []
    tlines, _ = lint_annotation.load_tagged(dst, perrs)
    orig = os.path.join(vorig, os.listdir(vorig)[0])
    with open(orig, encoding="utf-8") as f:
        olines = f.read().split("\n")
    bad = sum(1 for t, o in zip(tlines, olines) if t != o)
    print(f"剥标逐行对账：tagged={len(tlines)} 行 orig={len(olines)} 行，差异 {bad} 处")
    sys.exit(1 if (bad or len(tlines) != len(olines)) else 0)


if __name__ == "__main__":
    main()
