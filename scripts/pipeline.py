# -*- coding: utf-8 -*-
"""武侠知识库管线编排器 —— 《白发魔女传》全流程的脚本化，供续作复用。

用法：python scripts/pipeline.py <书名> <阶段>

机械阶段（本脚本直接执行）：
  status          盘点：章回版/ tagged/ 各层产物齐备情况与标注统计
  diff            逐行对账：tagged 剥标 vs 章回版原文，报告全部差异（含字符级定位）
  repair          机械损坏自动修复（repair_tags.py 四规则）
  lint            完整性校验（lint_annotation.py：剥标一致+配对+类型码白名单）
  registry        实体归一层：实体登记表.json + 实体归并清单.md（读 pipeline配置.json）
  events          事件层初解：事件表.json/md（启发式主宾消解）
  contexts        校订上下文：校订/核心-◉▲○◇.txt + 校订/◈-N.txt（按 batch_size 分批）
  apply-curation  应用校订 TSV → 事件表 v2 + 校订报告.md
  drop-review     生成 drop 复核材料（可指定批次号）
  rel-candidates  关系候选报告.md
  rel-table       关系表.json + 武功归属表.md（需先有 关系考订.tsv）

LLM 阶段（代理/主对话执行，本脚本给出输入输出契约）：
  annotate        逐回标注：读 章回版/<书>/NNN*.txt → 写 kb/tagged/<书>/NNN_*.tagged.md
                  规范=kb/<书>/标注规范-v0.md（继承白发魔女传 v0.2 冻结版）；
                  每回完成后必须 repair→lint→diff 全通过才算完成
  curation        事件校订：读 校订/核心-◉▲○◇.txt 与 校订/◈-N.txt，
                  按 校订/校订规则.md 逐条裁定 → 写 校订/校订-核心.tsv 与 校订/校订-◈-N.tsv
                  TSV 列：E<id>⇥verdict(correct/fix/drop/unsure)⇥主⇥宾⇥理由（无则 -）
  rel- adjudicate 关系考订：读 关系候选报告.md → 写 关系考订.tsv
                  列：subject⇥stype(◆/@)⇥predicate(镇山/拥有/独门/创制/修习/传授/别名)⇥object⇥otype(☆/•)⇥note
  drop-复核       逐条复核 drop 材料 → 填 drop复核-*.tsv 复核结论列（维持/误删）

推荐顺序（每本书）：
  annotate(种子回,主对话) → annotate(其余回,子代理分批) → repair → lint → diff →
  registry(先补 pipeline配置.json 的 manual_merges) → events → contexts →
  curation(LLM) → apply-curation → drop-review → drop-复核(LLM,可选) → apply-curation →
  rel-candidates → rel-adjudicate(LLM) → rel-table → status
"""
import io
import os
import re
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

STAGES = ["status", "diff", "repair", "lint", "registry", "events", "contexts",
          "apply-curation", "drop-review", "rel-candidates", "rel-table"]


def run(script, book, extra=None):
    cmd = [sys.executable, os.path.join(ROOT, "scripts", script), book] + (extra or [])
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        sys.exit(r.returncode)


def book_paths(book):
    return {
        "orig": os.path.join(ROOT, "章回版", book),
        "tagged": os.path.join(ROOT, "kb", "tagged", book),
        "kb": os.path.join(ROOT, "kb", book),
    }


def chapter_pairs(book):
    """(章节号, 原文路径, tagged路径或None)。tagged 命名约定 NNN_*.tagged.md。"""
    p = book_paths(book)
    pairs = []
    for fn in sorted(os.listdir(p["orig"])):
        m = re.match(r"^(\d{3})", fn)
        if not m or not fn.endswith(".txt"):
            continue
        num = m.group(1)
        tagged = None
        if os.path.isdir(p["tagged"]):
            for tf in os.listdir(p["tagged"]):
                if tf.startswith(num) and tf.endswith(".tagged.md"):
                    tagged = os.path.join(p["tagged"], tf)
                    break
        pairs.append((num, os.path.join(p["orig"], fn), tagged))
    return pairs


def stage_status(book):
    p = book_paths(book)
    pairs = chapter_pairs(book)
    done = [x for x in pairs if x[2]]
    print(f"《{book}》：章回 {len(pairs)} 回，已标注 {len(done)} 回")
    missing = [num for num, _, t in pairs if not t]
    if missing:
        print("  缺 tagged：", " ".join(missing))
    # lint 统计
    if done:
        n = 0
        for _, _, tf in done:
            with open(tf, encoding="utf-8") as f:
                n += len(re.findall(r"〖[^〖〗]*〗|⟦[^⟦⟧]*⟧", f.read()))
        print(f"  标记总数 {n}")
    for name in ["实体登记表.json", "事件表.json", "关系表.json", "关系考订.tsv"]:
        fp = os.path.join(p["kb"], name)
        print(f"  {name}: {'✓' if os.path.exists(fp) else '—'}")
    cur = os.path.join(p["kb"], "校订")
    if os.path.isdir(cur):
        tsvs = [f for f in os.listdir(cur) if f.startswith("校订-") and f.endswith(".tsv")]
        print(f"  校订 TSV: {len(tsvs)} 个")


def stage_diff(book):
    """lint 同语义剥标，报告全部差异行（lint 只报首错，修复循环用本阶段）。"""
    import lint_annotation as lint
    bad = 0
    for num, orig, tagged in chapter_pairs(book):
        if not tagged:
            continue
        errs = []
        tlines, _ = lint.load_tagged(tagged, errs)
        with open(orig, encoding="utf-8") as f:
            olines = f.read().split("\n")
        struct_errs = [e for e in errs if "内容不一致" not in e]
        for e in struct_errs:
            print(f"[{num}] {e}")
            bad += 1
        for i, (t, o) in enumerate(zip(tlines, olines), 1):
            if t != o:
                bad += 1
                n = min(len(t), len(o))
                pos = next((j for j in range(n) if t[j] != o[j]), n)
                print(f"[{num}] 行{i} 差异@{pos}")
                print(f"    tagged: …{t[max(0, pos-12):pos]}【{t[pos:pos+12] if pos < len(t) else '<EOF>'}】…")
                print(f"    orig  : …{o[max(0, pos-12):pos]}【{o[pos:pos+12] if pos < len(o) else '<EOF>'}】…")
                if len(tlines) != len(olines):
                    print(f"    行数不同 tagged={len(tlines)} orig={len(olines)}")
    print(f"{'全部一致' if not bad else f'共 {bad} 处差异/结构错误'}")


def main():
    if len(sys.argv) < 3 or sys.argv[2] not in STAGES:
        print(__doc__)
        sys.exit(2)
    book, stage = sys.argv[1], sys.argv[2]
    if stage == "status":
        stage_status(book)
    elif stage == "diff":
        stage_diff(book)
    elif stage == "repair":
        files = [t for _, _, t in chapter_pairs(book) if t]
        if files:
            run("repair_tags.py", book, files)
    elif stage == "lint":
        files = [t for _, _, t in chapter_pairs(book) if t]
        if files:
            run("lint_annotation.py", book, files)
    elif stage == "registry":
        run("build_entity_registry.py", book)
    elif stage == "events":
        run("build_event_table.py", book)
    elif stage == "contexts":
        run("extract_curation_contexts.py", book)
    elif stage == "apply-curation":
        run("apply_curation.py", book)
    elif stage == "drop-review":
        run("extract_drop_review.py", book, sys.argv[3:])
    elif stage == "rel-candidates":
        run("build_relation_candidates.py", book)
    elif stage == "rel-table":
        run("build_relation_table.py", book)


if __name__ == "__main__":
    main()
