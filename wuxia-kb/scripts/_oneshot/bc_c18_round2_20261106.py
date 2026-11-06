# -*- coding: utf-8 -*-
"""冰川天女传 C18 第二轮过滤补标（2026-11-06，registry 登记后重扫 1513 建议）。

裁决基准：docs/55 §四 同口径 + 桂冰娥家族 display-only 约定（全书 ~1780 处无管道）。
用法：python -X utf8 scripts/_oneshot/bc_c18_round2_20261106.py [--dry]
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import scan_untagged_aliases as c18  # noqa: E402

BOOK = "冰川天女传"
OUT_DIR = ROOT / "logs" / "qa" / "c18_filtered_bc_r2_20261106"
DRY = "--dry" in sys.argv

# (word, canonical) → override；canonical 覆写为 word 时落 display-only（桂冰娥家族约定）
APPROVE = {}
for w in ["唐经天", "陈天宇", "芝娜", "俄马登", "龙灵矫", "幽萍", "洞冥子", "金世遗",
          "白教法王", "云灵子", "黄石道人", "泰吉提", "桑青娘", "萧青峰", "陈定基",
          "谢云真", "德鲁奇", "唐晓澜", "萨天刺", "董太清", "雷震子", "方今明",
          "麦永明", "王流子", "唐赛花", "焦春雷", "胤禵", "诸葛武候", "武氏兄弟",
          "游一鄂", "洛珠", "提摩达多"]:
    APPROVE[(w, w)] = {}
# 别名（带管道，registry-backed；与书内 霞儿|邹绛霞 等既有管道先例一致）
for w, can in [("霞儿", "邹绛霞"), ("灵矫", "龙灵矫"), ("龙师叔", "龙灵矫"),
               ("龙先生", "龙灵矫"), ("夺命仙子", "谢云真"), ("峨嵋女侠", "谢云真"),
               ("谢女侠", "谢云真"), ("洞冥道友", "洞冥子"), ("雪儿", "方雪君"),
               ("焦大人", "焦春雷"), ("方大哥", "方今明"), ("雷大哥", "雷震子"),
               ("雷师兄", "雷震子"), ("大师兄", "雷震子"), ("郝师兄", "郝中浩"),
               ("青峰", "萧青峰"), ("世遗哥哥", "金世遗"), ("沁儿", "李沁梅"),
               ("唐相公", "唐经天"), ("唐家哥哥", "唐经天"), ("十四皇子", "胤禵"),
               ("吕大侠", "吕四娘"), ("怪叫化", "金世遗"), ("大麻疯", "金世遗")]:
    APPROVE[(w, can)] = {}
# 桂冰娥家族：display-only（保持全书 ~1780 处无管道约定；身份归并已入 registry）
for w in ["冰川天女", "冰娥", "天女姐姐", "冰娥小公主"]:
    APPROVE[(w, "桂冰娥")] = {"canonical": w}
# 组织/地点/家族
for w in ["崆峒", "红教", "喇嘛教", "黄教", "白教", "噶拳派", "峨嵋", "大清", "尼泊尔军"]:
    APPROVE[(w, w)] = {}
APPROVE[("武当门", "武当派")] = {}
APPROVE[("天山七剑", "天山七剑")] = {}
for w in ["西藏", "尼泊尔", "珠穆朗玛", "萨迦宗"]:
    APPROVE[(w, w)] = {}
for w in ["杨家", "邹家", "武家"]:
    APPROVE[(w, w)] = {}
# 江南：仅人名行（ch001/036），地名/诗句/习语行行级剔除
APPROVE[("江南", "江南")] = {}
JN_SKIP_POS = {(("003"), 4480), (("005"), 6972), (("006"), 1165), (("033"), 14516)}


def main():
    tsv_paths, kept, dropped = [], 0, 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for tsv in sorted((ROOT / "registry" / "patches" / BOOK).glob("*_aliases.tsv")):
        lines = io.open(tsv, encoding="utf-8").read().splitlines()
        out = [lines[0]]
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 8:
                continue
            canonical, word, pos = parts[1], parts[2], parts[3]
            ov = APPROVE.get((word, canonical))
            if ov is None:
                dropped += 1
                continue
            if word == "江南" and (parts[0], int(pos) if pos.isdigit() else -1) in JN_SKIP_POS:
                dropped += 1
                continue
            if "canonical" in ov:
                parts[1] = ov["canonical"]
            out.append("\t".join(parts))
            kept += 1
        if len(out) > 1:
            pth = OUT_DIR / tsv.name
            io.open(pth, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
            tsv_paths.append(pth)
    print(f"[r2] 过滤：保留 {kept} / 剔除 {dropped}，TSV {len(tsv_paths)} 个")
    if DRY:
        print("[r2] dry-run：未写 tagged")
        return
    stats = c18.do_apply(BOOK, tsv_paths, known_words=None)
    print(f"[r2] 落盘：{stats['chapters']} 回 / 插入 {stats['inserted']}；回滚 {stats['rolled_back'] or '无'}")


if __name__ == "__main__":
    main()
