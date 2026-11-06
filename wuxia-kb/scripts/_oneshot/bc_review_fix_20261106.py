# -*- coding: utf-8 -*-
"""冰川天女传 复核修复（2026-11-06，docs/55 批次）。

三部分（每步独立断言 + 备份，失败即停）：
  A. C18 过滤补标：逐词裁决白名单 + 行级守卫 → scan_untagged_aliases.do_apply
     （pos 精确插入 + 保护区 + 剥标断言 + 回滚）。
  B. 管道修正：pipe_unsourced 摘管保标 / 错管改管 / 错认喜剧按实际指称改管。
  C. judgment 人工项摘标：D1 描述性代称（藏族少女）+ 计划语境动词（准备+X）。

用法：python -X utf8 scripts/_oneshot/bc_review_fix_20261106.py [--skip-c18]
"""
import io
import re
import shutil
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import scan_untagged_aliases as c18  # noqa: E402

BOOK = "冰川天女传"
STAMP = "20261106"
BACKUP = ROOT / "backup" / "tagged" / f"bc-review-{STAMP}"
DRY = "--skip-c18" not in sys.argv and "--dry" in sys.argv

# ---- A. C18 过滤 -------------------------------------------------------------
APPROVE = {
    ("武当", "武当派"): {},
    ("中国", "中国"): {"type": "组织"},
    ("班禅", "班禅"): {},
    ("朝廷", "朝廷"): {},
    ("唐家", "唐家"): {},
    ("桂家", "桂家"): {},
    ("清兵", "清兵"): {},
    ("满洲", "满洲"): {},
    ("御林军", "御林军"): {},
    ("天山", "天山"): {},
    ("天山派", "天山派"): {},
    ("清宫", "清宫"): {},
    ("铁掌神弹", "杨仲英"): {},
    ("浣莲", "冒浣莲"): {},
    ("莲儿", "冒浣莲"): {},
}
SKIP_WORDS = {
    "活佛", "武林", "公子", "哥哥", "大哥", "老婆婆", "中年美妇", "红衣喇嘛",
    "大军", "龙树", "于中", "贝勒", "镖行", "桂老前辈", "胤禛", "官兵", "悟性",
    "通明", "霓裳", "武当门", "白石", "释迦牟尼", "杨仲英", "未风", "玄通",
}
# 行级守卫：(chapter, pos, word)
SKIP_ROWS = {
    ("015", None, "唐家"),      # 唐家哥哥（人物称谓，非家族）
    ("018", None, "铁掌神弹"),  # 铁掌神弹〖@杨仲英〗 同位前缀
}
CTX_ALLOW = {
    "天山": ("天山的灵药",),          # 其余为 剑法/掌法 分裂形、弟子/门下 复合、诗句
    "唐家": ("唐家暗器", "唐家世传"),
    "铁掌神弹": ("铁掌神弹的女儿",),
}


def apply_c18():
    tsv_paths, kept_n, dropped_n = [], 0, 0
    out_dir = ROOT / "logs" / "qa" / f"c18_filtered_bc_{STAMP}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for tsv in sorted((ROOT / "registry" / "patches" / BOOK).glob("*_aliases.tsv")):
        lines = io.open(tsv, encoding="utf-8").read().splitlines()
        out = [lines[0]]
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 8:
                continue
            canonical, word, pos, etype = parts[1], parts[2], parts[3], parts[7]
            if (word, canonical) not in APPROVE or word in SKIP_WORDS:
                dropped_n += 1
                continue
            if (parts[0], None, word) in SKIP_ROWS:
                dropped_n += 1
                continue
            allow = CTX_ALLOW.get(word)
            if allow and not any(a in parts[6] for a in allow):
                dropped_n += 1
                continue
            ov = APPROVE[(word, canonical)]
            if "type" in ov:
                parts[7] = ov["type"]
            out.append("\t".join(parts))
            kept_n += 1
        if len(out) > 1:
            p = out_dir / tsv.name
            io.open(p, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            tsv_paths.append(p)
    print(f"[A] C18 过滤：保留 {kept_n} / 剔除 {dropped_n}，TSV {len(tsv_paths)} 个")
    stats = c18.do_apply(BOOK, tsv_paths, known_words=None)
    print(f"[A] 落盘：{stats['chapters']} 回 / 插入 {stats['inserted']}；回滚 {stats['rolled_back'] or '无'}")


# ---- B. 管道修正 -------------------------------------------------------------
# (chapter, old_token, new_token, expected_count)
PIPE_FIXES = [
    ("010", "〖@陈兄|陈定基〗", "〖@陈兄|陈天宇〗", 2),
    ("028", "〖@天宇|唐天宇〗", "〖@天宇|陈天宇〗", 2),
    ("028", "〖@冒大侠|冒川生〗", "〖@冒大侠〗", 1),
    ("028", "〖@冰川天女|桂冰娥〗", "〖@冰川天女〗", 2),
    ("031", "〖@唐伯母|冯瑛〗", "〖@唐伯母|冯琳〗", 1),
    ("032", "〖@唐伯母|唐经天夫人〗", "〖@唐伯母|冯琳〗", 1),
    # 032[22] 同段两处〖@唐伯母|冯瑛〗：冯琳自述"真冯瑛在天山"保留第一处；绛霞"呼她做唐伯母"指实际在场的冯琳，改第二处
    ("032", "〖@冯琳〗追了出来，笑嘻嘻道：“你〖@唐伯母|冯瑛〗在〖=天山〗，将来你总能看到。”〖@邹绛霞〗一愕，转过头去埋怨母亲道：“妈，你怎么要我呼她做〖@唐伯母|冯瑛〗？”",
           "〖@冯琳〗追了出来，笑嘻嘻道：“你〖@唐伯母|冯瑛〗在〖=天山〗，将来你总能看到。”〖@邹绛霞〗一愕，转过头去埋怨母亲道：“妈，你怎么要我呼她做〖@唐伯母|冯琳〗？”", 1),
    ("031", "〖@八臂神魔|萨天剌〗", "〖@八臂神魔|萨天刺〗", 1),
    ("035", "〖@冰娥|桂冰娥〗", "〖@冰娥〗", 1),
    ("035", "〖@冰娥姐姐|桂冰娥〗", "〖@冰娥姐姐〗", 1),
    ("038", "〖@乾隆|弘历〗", "〖@乾隆〗", 3),
]


def _surgical(fixes, label):
    done = 0
    for ch, old, new, n in fixes:
        p = ROOT / "tagged" / BOOK / f"{ch}.tagged.md"
        BACKUP.mkdir(parents=True, exist_ok=True)
        bak = BACKUP / f"{ch}.tagged.md.bak"
        if not bak.exists():
            shutil.copyfile(p, bak)
        raw = io.open(p, encoding="utf-8").read()
        cnt = raw.count(old)
        if cnt == 0 and raw.count(new) >= n:
            done += 1  # 已应用（幂等重跑）
            continue
        assert cnt == n, f"{ch}: 「{old[:34]}…」出现 {cnt} 次，预期 {n}"
        raw = raw.replace(old, new)
        assert c18.symbols.strip_markup(raw) == c18.symbols.strip_markup(
            io.open(bak, encoding="utf-8").read()), f"{ch}: 剥标不一致"
        io.open(p, "w", encoding="utf-8", newline="\n").write(raw)
        done += 1
    print(f"[{label}] {done}/{len(fixes)} 组完成（备份 {BACKUP.name}）")


# ---- C. judgment 人工项摘标 --------------------------------------------------
# 藏族少女 全书 16 处（ch001×1/004×3/016×7/017×7/026×1）均为 D1 描述性代称，全部摘标
TIBETAN_FIXES = [("001", 1), ("004", 3), ("016", 7), ("017", 7), ("026", 1)]
JUDGE_FIXES = [
    *[("004", "〖#藏族少女〗", "藏族少女", 3)],
    ("017", "〖#藏族少女〗", "藏族少女", 7),
    ("013", "仍然准备⟦⊞合攻⟧", "仍然准备合攻", 1),  # 仅 pn41 计划处（pn34 已实际合攻，保留）
    ("014", "准备⟦■穿过⟧", "准备穿过", 1),  # 仅"准备穿过西藏"（另一处"穿过了沙漠"既成，保留）
    ("033", "准备⟦■劫狱⟧", "准备劫狱", 1),  # 仅 pn29 计划处（其余 8 处为叙述提及/既成，保留）
    ("035", "准备⟦■回到⟧", "准备回到", 1),  # 仅计划处（另一处"回到席间"既成，保留）
    *[("016", "〖#藏族少女〗", "藏族少女", 7)],
    ("001", "〖#藏族少女〗", "藏族少女", 1),
    ("026", "〖#藏族少女〗", "藏族少女", 1),
    # 036[8] 射死：前句"一箭射向咽喉…利箭插入口中"既成，保留（docs/45 #70）
]


def apply_pipe_fixes():
    _surgical(PIPE_FIXES, "B 管道修正")


def apply_judge_fixes():
    _surgical(JUDGE_FIXES, "C judgment 摘标")


if __name__ == "__main__":
    if "--only" in sys.argv:
        step = sys.argv[sys.argv.index("--only") + 1]
        {"c18": apply_c18, "pipe": apply_pipe_fixes, "judge": apply_judge_fixes}[step]()
    else:
        if "--skip-c18" not in sys.argv:
            apply_c18()
        apply_pipe_fixes()
        apply_judge_fixes()
