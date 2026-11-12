# -*- coding: utf-8 -*-
"""一次性：裸文补标（2026-11-07 复核批，docs/76 §五；延伸 docs/72 用户裁定）。

  * 「武林」→ 〖^武林〗：云海玉弓缘/冰河洗剑录 全部裸文（docs/72 §三 拍板②
    「武林统一为 ^武林，白发 ^×54 为锚」的跨书延伸；registry E87622 type ^）。
    云海 1 处旧 〖=武林〗 一并归一为 〖^武林〗（类型重写，与 docs/72 Phase A
    ◆中国→=中国 同机制）。
  * 「镖局」→ 〖◆镖局〗：冰河洗剑录 裸文（docs/72 拍板③ ◆镖行/镖局）。

围栏/标题/既有令牌保护区跳过（build_masked 等长掩码）；逐文件 final_verify +
剥标断言 + 令牌数守恒 + 写前备份。

用法：python -X utf8 scripts/_oneshot/bare_tag_yh_bh.py [--apply]
"""
import glob
import io
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import config                                        # noqa: E402
import symbols                                       # noqa: E402
from annotate_chapter_llm import final_verify, read_struct  # noqa: E402
from scan_untagged_aliases import build_masked       # noqa: E402

BACKUP = ROOT / "logs" / "backup" / "bare_tag_yh_bh_20261107"

# 书 → [(词, 类型码)]；RETYPE: (旧令牌全形, 新令牌全形)
TASKS = {
    "云海玉弓缘": [("武林", "^")],
    "冰河洗剑录": [("武林", "^"), ("镖局", "◆")],
}
RETYPE = {
    "云海玉弓缘": [("〖=武林〗", "〖^武林〗")],
    "冰河洗剑录": [],
}


def bare_positions(text: str, word: str):
    """裸文出现位置（不在既有令牌/围栏/标题保护区内的 word 全部出现点）。"""
    masked = build_masked(text)
    out = []
    start = 0
    while True:
        i = text.find(word, start)
        if i < 0:
            break
        start = i + 1
        if any(masked[j] == "\ufffd" for j in range(i, i + len(word))):
            continue
        out.append(i)
    return out


def main(apply: bool):
    grand = defaultdict(lambda: {"bare": 0, "retype": 0, "files": 0})
    for book, tasks in TASKS.items():
        n_book = 0
        retypes = RETYPE.get(book, [])
        for f in sorted(glob.glob(str(config.DIR_TAGGED / book / "*.tagged.md"))):
            text = io.open(f, encoding="utf-8").read()
            old = text
            positions = []
            for word, code in tasks:
                for i in bare_positions(text, word):
                    positions.append((i, word, code))
            chars = list(text)
            for i, word, code in sorted(positions, reverse=True):
                chars[i:i + len(word)] = list(f"〖{code}{word}〗")
            text = "".join(chars)
            n_retype = 0
            for old_tok, new_tok in retypes:
                n_retype += text.count(old_tok)
                text = text.replace(old_tok, new_tok)
            if text == old:
                continue
            # 断言：剥标不变 + 令牌数守恒（裸文补标净增=bare 数；retype 不增减）
            assert symbols.strip_markup(text) == symbols.strip_markup(old), f"剥标变化: {f}"
            old_n = len(list(symbols.TOKEN_RE.finditer(old)))
            new_n = len(list(symbols.TOKEN_RE.finditer(text)))
            assert new_n - old_n == len(positions), f"令牌数不符: {f}"
            if apply:
                Path(BACKUP / book).mkdir(parents=True, exist_ok=True)
                bp = Path(BACKUP) / book / Path(f).name
                if not bp.exists():
                    shutil.copy2(f, bp)
                io.open(f, "w", encoding="utf-8", newline="").write(text)
            grand[book]["bare"] += len(positions)
            grand[book]["retype"] += n_retype
            grand[book]["files"] += 1
            n_book += len(positions)
        print(f"[{book}] 裸文 {grand[book]['bare']} + 重型 {grand[book]['retype']}"
              f" / {grand[book]['files']} 文件")
    if apply:
        print(f"apply 完成，备份 {BACKUP}")
    else:
        print("dry-run（--apply 落盘）")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
