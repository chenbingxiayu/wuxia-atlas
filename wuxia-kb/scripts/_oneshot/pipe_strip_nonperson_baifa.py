# -*- coding: utf-8 -*-
"""一次性：白发魔女传非 @ 实体管道摘除（2026-11-06，docs/76 复核批）。

背景：2026-11-06 02:20 会话给金标准章回填别名时给非 @ 实体挂了 `|规范名` 管道，
违反 SKILL_01g v0.3 宪法「管道 | 只用于 @ 规范名 / % 时点时长年龄 / 动词状态注记」，
accept_batch 报 hard `pipe_on_nonperson` / `pipe_format` 31 处（白发 001×26 / 002×1 /
006 修辞×1 / 007×1 / 009×2），5 回 needs_fix（registry/acceptance/白发魔女传_001-032.json
generated_at 2026-11-06T11:57）。

处置：摘管道保显示串（〖◆武当|武当派〗→〖◆武当〗；〘※…|…〙→〘※…〙）。
规范名信息由 registry 承载（武当派 E0101 / 龙门帮 E0102 等 alias_additions）；
=乾清官 的 原文错字按「剥标=底本」保留显示串。

断言：逐文件 strip-token 前后一致（摘管道不动正文）、替换计数=预期 31、幂等。
用法：python -X utf8 scripts/_oneshot/pipe_strip_nonperson_baifa.py [--apply]
"""
import glob
import io
import re
import shutil
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
BOOK = "白发魔女传"
BACKUP = ROOT / "logs" / "backup" / "pipe_strip_nonperson_20261106"

# 仅 @/% 之外的实体类型挂管道 = 非法；% 时点时长与 @ 规范名保留。
# 令牌形如 〖XY...|ZZ...〗，X 为类型符且 X ∉ {@,%}；正文/围栏内不会出现 〖…|…〗 组合
# （五门 md-lint/integrity 已保证 〖〗 为标注专用）。
ENT_RE = re.compile(r"〖([^@%|〗])((?:[^|〗]{1,38}))\|((?:[^〗]{1,38}))〗")
RHE_RE = re.compile(r"〘((?:[^|〙]{1,58}))\|((?:[^〙]{1,58}))〙")

EXPECT = 31


def main(apply: bool):
    files = sorted(glob.glob(str(ROOT / "tagged" / BOOK / "*.tagged.md")))
    total = 0
    changed = []
    for f in files:
        p = Path(f)
        txt = io.open(f, encoding="utf-8").read()
        # 剥标一致性基线：摘管道只动令牌内部，剥标文本必须不变
        stripped_before = re.sub(r"〖[^〗]*〗|〘[^〙]*〙", "", txt)
        txt2 = ENT_RE.sub(lambda m: f"〖{m.group(1)}{m.group(2)}〗", txt)
        txt2 = RHE_RE.sub(lambda m: f"〘{m.group(1)}〙", txt2)
        n = len(ENT_RE.findall(txt)) + len(RHE_RE.findall(txt))
        if n == 0:
            continue
        stripped_after = re.sub(r"〖[^〗]*〗|〘[^〙]*〙", "", txt2)
        assert stripped_before == stripped_after, f"剥标不一致: {p.name}"
        total += n
        changed.append((p, txt, txt2, n))

    print(f"扫描 {BOOK}: {len(files)} 文件，非法管道 {total} 处（预期 {EXPECT}）")
    assert total == EXPECT, f"计数不符：{total} != {EXPECT}"
    for p, _, _, n in changed:
        print(f"  {p.name}: {n}")

    if not apply:
        print("dry-run 完成（--apply 落盘）")
        return

    BACKUP.mkdir(parents=True, exist_ok=True)
    for p, txt, txt2, n in changed:
        shutil.copy2(p, BACKUP / p.name)
        io.open(p, "w", encoding="utf-8", newline="").write(txt2)
    print(f"apply 完成：{len(changed)} 文件，备份 {BACKUP}")

    # 幂等复扫
    left = 0
    for f in files:
        txt = io.open(f, encoding="utf-8").read()
        left += len(ENT_RE.findall(txt)) + len(RHE_RE.findall(txt))
    print(f"复扫残留：{left}（应 0）")
    assert left == 0


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
