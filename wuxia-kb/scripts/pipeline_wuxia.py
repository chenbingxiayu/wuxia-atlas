# -*- coding: utf-8 -*-
"""wuxia-kb 新管线阶段编排器 —— 武侠标注流水线的多书阶段化驱动。

用法：python wuxia-kb/scripts/pipeline_wuxia.py <书名> <阶段> [--chapter N]
      python wuxia-kb/scripts/pipeline_wuxia.py <书名> status    # 该书产物盘点
      python wuxia-kb/scripts/pipeline_wuxia.py                  # 打印阶段清单

书名取 config.books() 键（章回版/ 目录自动发现），如 白发魔女传。
旧编排器 scripts/pipeline.py（kb/tagged 旧体系）保持原样，与本编排器互不影响；
本脚本只编排 wuxia-kb/scripts/ 内已移植/新写的脚本，路径一律经 config.py。

机械阶段（subprocess 调 sys.executable 跑同目录脚本，继承 stdout，失败即停）：
  structure       N1 章回结构标注生成：章回版/<书>/NNN.txt → tagged/<书>/NNN.struct.md
                  （generate_pn_wuxia --all --verify；--chapter 单回限定）
  verse-scan      N2 韵文/词牌/对联候选扫描，报告落 logs/verse_scan/
                  （detect_verse_wuxia --scan；--chapter 单回限定）
  lint-pn         PN 编号与章回结构检查 E1-E17（lint_purple_numbers；--chapter 单回）
  integrity       剥标与锁定底本逐字对账（lint_text_integrity，默认即字符级严格模式，
                  勿开 --norm；--chapter 单回）
  symbol-lint     符号冲突/旧符号残留检查（lint_symbol_conflicts）
  md-lint         Markdown 结构检查（lint_markdown）
  fence-format    韵文围栏格式检查（lint_fence_format；--chapter 单回）
  coverage        分书汉字标注覆盖率统计（compute_annotation_coverage，落 logs/coverage/）
  para-structure  段落结构与围栏块提取（extract_paragraph_structure，落 registry/structure/）
  yunwen          韵文围栏提取（extract_yunwen，落 logs/yunwen/）
  candidates      未标注候选实体发现（find_candidate_entities，缺省 stopwords 词表反查；
                  落 logs/candidates/；--chapter 单回限定）
  concordance     实体对照表构建（build_entity_concordance；落 registry/concordance/；
                  --chapter 单回限定，缺省全书）
  verb-validate   动词标注校验（validate_verb_tagging_wuxia，六域白名单/边界/消歧/密度；
                  落 logs/verb_validation/；--chapter 单回限定；默认 warning 口径，
                  词表补 senses 后可加 --wordlist-strict）
  time-resolve    N4 时间轴解析（time_resolver_wuxia，D05/SKILL_时间体系 §二-§八）：
                  % 时间令牌 → 时点键/四类锚点/书内相对刻度/单调性/分叉隔离；
                  落 registry/time/ + logs/time/；--chapter 单回限定；只读 tagged
  check           标注批次完成门：lint-pn → integrity → symbol-lint → md-lint →
                  fence-format 五项连跑，逐项记录退出码，任一非零即门未过
                  （对应旧管线 annotate 每回 repair→lint→diff 的完成习惯）

LLM 契约阶段（本脚本只打印输入输出契约，不执行——由主对话/子代理完成）：
  annotate        逐回标注：读 tagged/<书>/NNN.struct.md → 按 skills/SKILL_03a_实体标注.md
                  §二 SYSTEM_PROMPT（G1 已收口；few-shot 由 scripts/build_03a_fewshot.py
                  随种子再生成，版本以 SKILL_03a 文内"版本锁定"节为准）
                  + SKILL_04f 动词域补标 〖实体〗⟦动词⟧（文字零增删改）
                  → 写同目录 NNN.tagged.md；API 执行件 scripts/annotate_llm.py
                  （--prompt 单遍主模式 / --prompt-e+--prompt-v 两遍 fallback）；
                  每回完成后必须 check 五项全过才算完成
  review          按章反思（S-03c，待建）：读 NNN.tagged.md + lint/coverage 报告 →
                  反思记录（占位契约，待 SKILL_03c 落地后补全）

推荐顺序（每本书）：
  structure → verse-scan → lint-pn → [G1 种子回 annotate 试点] → annotate 全书 →
  check → coverage → para-structure → yunwen → candidates → concordance → verb-validate →
  time-resolve → review

辅助工具（非阶段，需要时单独调用）：
  generate_entity_stats_report.py   实体统计报告（--book 分书统计 15+6 类密度）
  token_tracker.py                  LLM 会话 token 计量库（annotate/review 批次计费用）
  tag_new_entity_types.py           C16 新实体类型补标建议（TSV→registry/patches/，不写 tagged）
  tag_identity_kinship.py           C17 身份/亲属补标建议（同上）
  scan_untagged_aliases.py          C18 已知实体别名裸文扫描（建议 TSV）
  infer_single_char_names.py        C19 单字人名全名推断（报告；--apply 可选）
  detect_entity_boundary_errors.py  C20 实体边界体检（报告 + 建议 TSV）
  accept_batch.py                   语义验收器（高风险全查+10%抽样；registry/acceptance/）

任一机械阶段失败即终止并提示可从该阶段重跑：
  python pipeline_wuxia.py <书名> <失败阶段> [--chapter N]
"""
import io
import os
import subprocess
import sys
from datetime import datetime

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import config  # noqa: E402  （wuxia-kb/scripts/config.py，路径与书目唯一来源）

# 阶段注册表：机械阶段（subprocess 透传）+ LLM 契约阶段（只打印契约）
MECHANICAL_STAGES = ("structure", "verse-scan", "lint-pn", "integrity", "symbol-lint",
                     "md-lint", "fence-format", "coverage", "para-structure",
                     "yunwen", "candidates", "concordance", "verb-validate",
                     "time-resolve", "check")
LLM_STAGES = ("annotate", "review")
STAGES = ("status",) + MECHANICAL_STAGES + LLM_STAGES

# check 完成门连跑的 lint 阶段（顺序即执行顺序；check 不短路，逐项记录退出码）
CHECK_STAGES = ("lint-pn", "integrity", "symbol-lint", "md-lint", "fence-format")


def build_command(stage, book, chapter):
    """阶段 → 同目录脚本的 argv（不含解释器前缀）。chapter 为 None 或 1-based int。"""
    b = ["--book", book]
    ch3 = f"{chapter:03d}" if chapter else None
    if stage == "structure":
        argv = (["generate_pn_wuxia.py"] + b
                + (["--chapter", str(chapter)] if chapter else ["--all"])
                + ["--verify"])
    elif stage == "verse-scan":
        argv = (["detect_verse_wuxia.py"] + b + ["--scan"]
                + (["--chapter", str(chapter)] if chapter else []))
    elif stage == "lint-pn":
        argv = ["lint_purple_numbers.py"] + b + ([ch3] if ch3 else [])
    elif stage == "integrity":
        argv = ["lint_text_integrity.py"] + b + ([ch3] if ch3 else [])
    elif stage == "symbol-lint":
        argv = ["lint_symbol_conflicts.py"] + b
    elif stage == "md-lint":
        argv = ["lint_markdown.py"] + b
    elif stage == "fence-format":
        argv = ["lint_fence_format.py"] + b + ([ch3] if ch3 else [])
    elif stage == "coverage":
        argv = ["compute_annotation_coverage.py"] + b
    elif stage == "para-structure":
        argv = ["extract_paragraph_structure.py"] + b
    elif stage == "yunwen":
        argv = ["extract_yunwen.py"] + b
    elif stage == "candidates":
        # 脚本要求 --chapter/--all 二选一；--book 已把范围锁定到单书
        argv = (["find_candidate_entities.py"] + b
                + (["--chapter", ch3] if ch3 else ["--all"]))
    elif stage == "concordance":
        argv = (["build_entity_concordance.py"] + b
                + (["--chapters", ch3] if ch3 else []))
    elif stage == "verb-validate":
        argv = (["validate_verb_tagging_wuxia.py"] + b
                + (["--chapters", ch3] if ch3 else []))
    elif stage == "time-resolve":
        # N4 时间轴解析（D05）：只读 tagged/struct，写 registry/time/ + logs/time/
        argv = (["time_resolver_wuxia.py"] + b
                + (["--chapter", str(chapter)] if chapter else []))
    else:
        raise ValueError(f"非机械阶段：{stage}")
    return argv


def run_stage(stage, book, chapter=None):
    """跑单个机械阶段：继承 stdout，打印开始/完成行，返回退出码。

    子进程启动失败（脚本缺失/解释器或 cwd 不可用等 FileNotFoundError/OSError）时
    不抛异常，打印 `[stage] 子进程启动失败: ...` 并返回 -1；check 的各阶段因此仍能
    逐项记录（不短路），由 stage_check 汇总为未通过（task-12 修复）。
    """
    argv = build_command(stage, book, chapter)
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, argv[0])] + argv[1:]
    scope = f"（第 {chapter} 回）" if chapter else ""
    print(f"[{stage}] 开始{scope} → {' '.join(argv)}")
    sys.stdout.flush()                     # 先落"开始"行，再让子进程继承 stdout 直写
    try:
        r = subprocess.run(cmd, cwd=config.ROOT)
    except (FileNotFoundError, OSError) as exc:
        print(f"[{stage}] 子进程启动失败: {exc}")
        return -1
    print(f"[{stage}] 完成（退出码 {r.returncode}）")
    return r.returncode


def fail(stage, code, book, chapter=None):
    ch = f" --chapter {chapter}" if chapter else ""
    print(f"\n[{stage}] 失败（退出码 {code}）。修复后可从该阶段重跑："
          f"python pipeline_wuxia.py {book} {stage}{ch}")
    sys.exit(code)


def stage_check(book, chapter=None):
    """标注批次完成门：五项 lint 连跑（不短路），汇总各项退出码。"""
    print(f"[check] 开始（标注批次完成门：{' → '.join(CHECK_STAGES)}）")
    codes = {}
    for st in CHECK_STAGES:
        codes[st] = run_stage(st, book, chapter)
    print("[check] 各项退出码：" + "  ".join(f"{k}={v}" for k, v in codes.items()))
    bad = [k for k, v in codes.items() if v != 0]
    if bad:
        print(f"[check] 未通过：{'、'.join(bad)}（exit!=0）——"
              f"修复后重跑 python pipeline_wuxia.py {book} check")
        sys.exit(1)
    print(f"[check] 完成：{len(CHECK_STAGES)} 项 lint 全过，本批次达到完成门")


def _compress(nums):
    """[2,3,5,7,8] → '002-003, 005, 007-008'（缺回清单压缩显示）。"""
    if not nums:
        return ""
    runs, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        runs.append((start, prev))
        start = prev = n
    runs.append((start, prev))
    return ", ".join(f"{a:03d}" if a == b else f"{a:03d}-{b:03d}" for a, b in runs)


def _recent_reports(limit=8):
    """收集 logs/ 与 registry/structure/ 下的报告文件，按修改时间倒序。"""
    paths = list(config.DIR_LOGS.glob("lint_text_integrity*.txt")) \
        if config.DIR_LOGS.is_dir() else []
    for sub in (config.DIR_LOGS / "verse_scan", config.DIR_LOGS / "coverage",
                config.DIR_LOGS / "yunwen", config.DIR_LOGS / "candidates",
                config.DIR_LOGS / "verb_validation",
                config.DIR_REGISTRY / "structure", config.DIR_REGISTRY / "concordance",
                config.DIR_REGISTRY / "acceptance"):
        if sub.is_dir():
            paths.extend(p for p in sub.iterdir() if p.is_file())
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[:limit]


def stage_status(book):
    """产物盘点：底本回数 vs struct/tagged 齐备情况 + 最近 lint/统计报告。"""
    meta = config.books()[book]
    total = meta["chapters"]
    d = config.DIR_TAGGED / book
    struct = {}
    tagged = {}
    if d.is_dir():
        struct = {int(p.name[:3]): p for p in d.glob("*.struct.md")}
        tagged = {int(p.name[:3]): p for p in d.glob("*.tagged.md")}
    print(f"《{book}》产物盘点（{datetime.now():%Y-%m-%d %H:%M}）")
    lock = "已锁定" if meta["fingerprint"] else "未锁定（G0 拍板门未过）"
    slug = meta["slug"] or "未定（G0 后回填）"
    print(f"  底本     : 章回版/{book}/ 共 {total} 回（slug={slug}，指纹={lock}）")
    ok = " ".join(f"{n:03d}" for n in sorted(struct)) or "无"
    print(f"  结构文件 : tagged/{book}/NNN.struct.md —— {len(struct)}/{total} 回（{ok}）")
    missing = [n for n in range(1, total + 1) if n not in struct]
    if missing:
        print(f"  缺结构   : {_compress(missing)}")
    ok = " ".join(f"{n:03d}" for n in sorted(tagged)) or "无"
    print(f"  标注文件 : tagged/{book}/NNN.tagged.md —— {len(tagged)}/{total} 回（{ok}）")
    if struct and not tagged:
        print("  → 结构已生成、标注未开始；下一步 annotate（LLM 契约阶段，待 G1 门）")
    elif tagged and struct:
        gap = [n for n in sorted(struct) if n not in tagged]
        if gap:
            print(f"  → 已结构未标注：{_compress(gap)}")
    print("  最近报告 :")
    reports = _recent_reports()
    if reports:
        for p in reports:
            ts = datetime.fromtimestamp(p.stat().st_mtime)
            print(f"    {p.relative_to(config.ROOT)}  （{ts:%Y-%m-%d %H:%M}）")
    else:
        print("    （无——先跑 lint/统计类阶段生成）")


def stage_annotate(book, chapter=None):
    """打印 annotate 的 LLM 输入输出契约（SKILL_03a 已定版，G1 已收口）。"""
    print("[annotate] LLM 契约阶段（本编排器只打印契约，由主对话/子代理执行）")
    print(f"  输入  : tagged/{book}/NNN.struct.md（structure 阶段产物；缺失先跑 structure）")
    if chapter:
        print(f"  范围  : 第 {chapter:03d} 回（{config.struct_path(book, chapter)}）")
    else:
        print("  范围  : 全书逐回（建议先 G1 种子回试点，再子代理分批）")
    print("  规范  : skills/SKILL_03a_实体标注.md §二 SYSTEM_PROMPT")
    print("          （G1 已收口；版本随种子再生成滚动，以文内\"版本锁定\"节为准；")
    print("          few-shot 由 scripts/build_03a_fewshot.py 再生成）")
    print("          + skills/SKILL_04f_动词标注.md（⟦⟧ 动词六类）")
    print("  运行器: scripts/annotate_llm.py（--prompt 单遍主模式 / 两遍 fallback）")
    print("  操作  : 在 struct 的 PN 段序上补标 〖15 类实体〗与 ⟦6 类动词⟧；")
    print("          文字零增删改（剥标须与锁定底本逐字一致，integrity 把关）")
    print(f"  输出  : tagged/{book}/NNN.tagged.md（与 struct 同目录）")
    print(f"  完成门: python pipeline_wuxia.py {book} check 五项 lint 全过（退出码全 0）")
    print("  计量  : 批次经 token_tracker.track_tokens 包装（落 logs/token_usage/）")
    targets = [chapter] if chapter else range(1, meta_chapters(book) + 1)
    missing = [n for n in targets if not config.struct_path(book, n).exists()]
    if missing:
        print(f"  [提示] 输入缺失：{_compress(missing)} —— "
              f"先跑 python pipeline_wuxia.py {book} structure")


def stage_review(book, chapter=None):
    """打印 review 的占位契约（S-03c 待建）。"""
    print("[review] LLM 契约阶段（占位——S-03c 按章反思 SKILL 待建，G1 门后落地）")
    print("  输入（拟定）: tagged/<书>/NNN.tagged.md + check/lint 报告 + coverage 分回统计")
    print("  操作（拟定）: 按章反思标注质量——实体边界、动词归类、韵文围栏、漏标候选")
    print("  输出（拟定）: 按章反思记录（载体与格式待 SKILL_03c 定义）")
    print("  状态    : 契约占位，不可执行；SKILL_03c 落地后由本编排器补全")


def meta_chapters(book):
    return config.books()[book]["chapters"]


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        print("阶段清单：status（盘点）｜机械：" + " ".join(MECHANICAL_STAGES)
              + "｜LLM 契约：" + " ".join(LLM_STAGES))
        return
    if len(argv) < 2 or argv[1] not in STAGES:
        print(__doc__)
        sys.exit(2)
    book, stage = argv[0], argv[1]

    chapter = None
    if "--chapter" in argv:
        i = argv.index("--chapter")
        if i + 1 >= len(argv):
            print("错误：--chapter 需要回号整数")
            sys.exit(2)
        try:
            chapter = int(argv[i + 1])
        except ValueError:
            print(f"错误：--chapter 需整数回号，收到 {argv[i + 1]!r}")
            sys.exit(2)

    meta = config.books().get(book)
    if not meta:
        print(f"错误：书目未发现：{book}（可选：{'、'.join(config.book_names())}）")
        sys.exit(2)
    if chapter is not None and not 1 <= chapter <= meta["chapters"]:
        print(f"错误：回号 {chapter} 超出《{book}》范围 1-{meta['chapters']}")
        sys.exit(2)

    if stage == "status":
        stage_status(book)
    elif stage == "check":
        stage_check(book, chapter)
    elif stage == "annotate":
        stage_annotate(book, chapter)
    elif stage == "review":
        stage_review(book, chapter)
    else:
        code = run_stage(stage, book, chapter)
        if code != 0:
            fail(stage, code, book, chapter)


if __name__ == "__main__":
    main()
