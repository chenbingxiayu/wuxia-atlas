# -*- coding: utf-8 -*-
"""C1 二阶段 · 泛称收口 + $ 数量层旧口径双侧清洗（2026-11-06 用户拍板）。

拍板（本日 AskUserQuestion 三项）：
  ① 泛称收口：〖^武学〗×3（白发 007/009、冰魄 002）+ 〖☆功夫〗×2（gold）按 P0-1
    「泛称不标」同口径摘除（docs/63 §七 裁决①的延伸；docs/66 §八.2 待裁项就此关闭）。
    全 6 书扫描 〖^武学〗〖☆武学〗〖^功夫〗〖☆功夫〗（〖^功夫〗此前 292 摘标已清零，兜底复核）。
  ② $ 数量层旧口径**双侧清洗**（gold 001-019 + 机器 020-032）：事件量/时间量/程度量/
    泛指/习语/方位/垃圾类摘除，规则全部有 docs/45「裸数词不标」+ W4 负例表背书
    （apply_gold_calibrated_recall.py §W4）；双侧同洗保持 P/R 评测对称。
  ③ 量词白名单外待审档（两个/一把/一口/一丈/三舵…，quantity.json review 档）**不动**，
    留待 docs/47 §五.1 量词扩表工作流单独裁定。

规则分层（逐条可审计）：
  R0 泛称       —— 上表四符号面，6 书全扫。
  R1 skip表面   —— W4 文档负例：一个/一道/一笔/千条/万条/四处（+千万条 同族）。
  R2 前置deny   —— surface 首字 ∈ 第/每/这/哪/另（W4 QTY_PREV_DENY 同源）。
  R3 非数量词   —— 整面不匹配「数+量」结构（一定/方面/星星/了X…），保护 丈许。
  R4 事件量     —— 量词末字 ∈ W4 文档负例 声掌拳眼步句次遍番阵场回合看。
  R5 时间量     —— 量词末字 ∈ 日月年天时（W4 注释「→% 层辖域」）+ 夜晚世。
  R6 程度量     —— 量词末字 ∈ 点片丝（W4 注释 + docs/47 负表 丝「一丝笑意」）。
  R7 裸数词     —— 数词后仅跟量级字（余多几数半廿卅零百千万），docs/45 裸数词不标。
  R9 补遗表     —— 泛指/副词/连词/习语/方位/动量补遗/垃圾的显式 surface 表
                  （逐条附理由；一笑/一惊 等动量与 R4 同理，唯未入 W4 负例字表）。

安全纪律：
  - 默认 dry-run；--apply 才落盘。
  - **摘标 = 令牌变裸文本**（去标记符号与管道注记、保留正文，C1/292-摘标同口径；
    「标注不改正文」铁律 —— 剥标断言用 apply_gold_c1_cleanup.sk 同款：摘标前后剥标文本逐字相等）。
  - 带管道令牌（〖$X|Y〗）一律不自动摘，仅报告（登记管道属 registry 资产）。
  - 备份 logs/backup/strip_qty_legacy_<ts>/<书>/；newline='' 保留原行尾（C1:110 教训）。

用法：
  python -I scripts/_oneshot/strip_qty_legacy_tokens.py            # dry-run 报告
  python -I scripts/_oneshot/strip_qty_legacy_tokens.py --apply    # 备份+落盘+断言
"""
import argparse
import collections
import glob
import io
import os
import re
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import apply_gold_calibrated_recall as _W  # noqa: E402  权威 W4 表同源 import

BOOKS = ["白发魔女传", "江湖三女侠", "七剑下天山", "塞外奇侠传", "冰魄寒光剑", "冰川天女传"]
GOLD_BOOK = "白发魔女传"
GOLD_MAX, MACH_MIN, MACH_MAX = 19, 20, 32

SKIP = set(_W.QTY_SKIP_SURFACE) | {"千万条"}          # R1
DENY_HEAD = set("第每这哪另")                          # R2
EV = set("声掌拳眼步句次遍番阵场回合看")                # R4
TIME = set("日月年天时夜晚世")                          # R5
DEG = set("点片丝")                                     # R6
SCALE = set("余多几数半廿卅零百千万")                    # R7
PROTECT = {"丈许", "一半", "两半", "二分之一", "好几个", "无数", "二十万人"}
# （长度/分数/模糊量保护；二十万人 系 QTY_NUM 无独立「二十」的解析缺口面）
NUM = _W.QTY_NUM

# R9 · 补遗表：surface -> 理由（分组标签）
EXTRA = {
    # —— 泛指/副词/连词（非数量语义；一头秀发/一军主帅/生下一子/武当二老/
    #    一家小旅馆/高逾半身 等合法计数经语境抽查移出，归待审档）——
    **{s: "泛指副词" for s in (
        "一定 一般 一样 一种 一切 一同 一起 一直 一向 一律 一味 一再 一齐 一边 一连 "
        "一并 一来 二来 三来 一方面 一一 一等一 一流 一介 一众 一伙 两伙 一党 一霸 "
        "一系 一职 一身 一腔 一心 一红 一香 一完 一起疑 一二 一无 齐都 天大 大批 "
        "少数几人 方面 星星 多少 双方 双掌 双腿 两肩 两臂 其一 其二 之一 四下 两边 "
        "两旁 一旁 一侧 半路").split()},
    # —— 习语/固定语 ——
    **{s: "习语" for s in (
        "一筹 一臂 三长两短 十有八九 两袖清风 一箭之仇 一面之缘 一物换一物 一至如斯 "
        "一纸空文 三刀六洞 一对一 一雌雄 一举一动 一粒粒 一对对 一缕缕 一堆堆 三三五五 "
        "三宇 二宇 十三各 五金 三大 四大弟子 四肢 四蹄 六根 五指").split()},
    # —— 时间域（% 层辖域延伸面）——
    **{s: "时间域" for s in (
        "一会 一会儿 一忽儿 一周 一晚 一晚上 一夜 一早 一世 一代 一生 一开首").split()},
    # —— 动量补遗（与 R4 同理：事件量/微动作不标）——
    **{s: "动量补遗" for s in (
        "一笑 一惊 一怔 一愕 一楞 一喜 一望 一见 一听 一瞧 一瞥 一张望 一想 一说 一问 "
        "一谈 一叙 一数 一试 一战 一比 一别 一走 一歇 一游 一遭 一探 一抓 一按 一摆 一拉 "
        "一抱 一碰 一绕 一递 一拨 一铲 一翻 一涌 一拥 一跃 一跳 一晃 两晃 几晃 一闪 几闪 "
        "一动 一振 一激 一震 一沉 一扬 一扫 一亮 一停 一仰 一转 几转 三转 两旋 一指 一脚 "
        "一腿 一拜 三拜 一揖 一礼 一言 一句话 两句话").split()},
    # —— W4 文档 surface 负例补录（头/路/带 注释原文；「一头」语境抽查均为
    #    合法计量〔一头秀发/一头猛虎〕，移出本表归待审档）——
    **{s: "W4负表面" for s in ("一路 两路 一带").split()},
}

TOKEN_RE = re.compile("〖\\$([^〖〗|]+)(\\|[^〖〗]*)?〗")
GENERIC_RE = re.compile("〖(\\^|☆)(武学|功夫)(\\|[^〖〗]*)?〗")


def classify_qty(s: str):
    """$ surface → (规则名, 是否摘)。返回 None 表示待审不动。"""
    if s in PROTECT:
        return None
    if s in EXTRA:
        return "R9-" + EXTRA[s]
    if s in SKIP:
        return "R1-skip表面"
    if s[0] in DENY_HEAD:
        return "R2-前置deny"
    verdict = _parse_verdict(s)
    if verdict == "R3-非数量词" and s[0] == "二":
        # QTY_NUM 无独立「二」（只有二三十）：二人/二位/二招 等合法计数
        # 按「两X」重试解析；EXTRA/PROTECT 已先行，故此处只影响解析桶。
        verdict = _parse_verdict("两" + s[1:])
    return verdict


def _parse_verdict(s: str):
    m = re.fullmatch(NUM + r"(.+)", s)
    if not m:
        return "R3-非数量词"
    unit = m.group(2)
    if not unit:
        return "R7-裸数词"
    if unit[-1] in EV:
        return "R4-事件量"
    if unit[-1] in TIME:
        return "R5-时间量"
    if unit[-1] in DEG:
        return "R6-程度量"
    if all(c in SCALE for c in unit):
        return "R7-裸数词"
    return None  # 白名单外/复量词 → 待审档，不动


def chapter_files(book: str):
    return sorted(glob.glob(f"tagged/{book}/0[0-9][0-9].tagged.md"))


def scope(book: str, no: int) -> bool:
    """$ 规则作用域：白发金标准 001-019 + 机器 020-032（拍板②双侧）。"""
    return book == GOLD_BOOK and 1 <= no <= MACH_MAX


def collect():
    """扫描 → [(book, no, span, whole, inner, rule)]；泛称与 $ 分列。inner=保留正文。"""
    qty_hits, gen_hits, piped = [], [], []
    for book in BOOKS:
        for f in chapter_files(book):
            no = int(re.search(r"(\d{3})", f).group(1))
            t = open(f, encoding="utf-8", newline="").read()
            for m in GENERIC_RE.finditer(t):
                gen_hits.append((book, no, m.span(), m.group(0), m.group(2), "R0-泛称"))
            if not scope(book, no):
                continue
            for m in TOKEN_RE.finditer(t):
                s = m.group(1)
                rule = classify_qty(s)
                if rule is None:
                    continue
                if m.group(2):  # 带管道 → 只报告
                    piped.append((book, no, m.start(), m.group(0), s, rule))
                    continue
                qty_hits.append((book, no, m.span(), m.group(0), s, rule))
    return qty_hits, gen_hits, piped


def strip_text(t: str, hits) -> str:
    """令牌→裸文本（去符号留正文，含管道段丢弃）；hits 按 span 起点升序。"""
    out, last = [], 0
    for (a, b), _whole, inner, _rule in hits:
        out.append(t[last:a])
        out.append(inner)
        last = b
    out.append(t[last:])
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="C1 二阶段：泛称收口 + $ 层旧口径双侧清洗")
    ap.add_argument("--apply", action="store_true", help="落盘（默认 dry-run）")
    args = ap.parse_args()

    qty_hits, gen_hits, piped = collect()
    by_rule = collections.Counter(h[5] for h in qty_hits)
    by_rule.update(h[5] for h in gen_hits)
    by_book = collections.Counter(h[0] for h in qty_hits + gen_hits)
    by_file = collections.Counter((h[0], h[1]) for h in qty_hits + gen_hits)
    surf_rule = {}
    for h in qty_hits:
        surf_rule.setdefault(h[4], h[5])

    print(f"== {'APPLY' if args.apply else 'DRY-RUN'} ==  共 {len(qty_hits) + len(gen_hits)} 处"
          f"（$ 层 {len(qty_hits)} + 泛称 {len(gen_hits)}）；带管道报告 {len(piped)} 处")
    print("-- 按规则 --")
    for r, c in sorted(by_rule.items()):
        print(f"  {r}: {c}")
    print("-- 按书 --")
    for b, c in sorted(by_book.items()):
        print(f"  {b}: {c}")
    print("-- 按回（改动文件）--")
    for (b, no), c in sorted(by_file.items()):
        print(f"  {b} {no:03d}: {c}")
    print("-- 泛称命中明细 --")
    for b, no, _, whole, inner, _r in gen_hits:
        print(f"  {b} {no:03d}: {whole} → {inner}")
    if piped:
        print("-- 带管道候选（不自动摘，请人工裁）--")
        for b, no, _, whole, s, r in piped:
            print(f"  {b} {no:03d}: {whole}  [{r}]")
    print("-- $ 层 surface→规则 抽样（每规则前 8）--")
    seen = collections.Counter()
    for s, r in sorted(surf_rule.items()):
        if seen[r] < 8:
            print(f"  {s} → {r}")
            seen[r] += 1

    if not args.apply:
        print("\ndry-run 结束（未写盘）。加 --apply 落盘。")
        return

    import apply_gold_c1_cleanup as _C1  # noqa: E402  规范 sk 同源

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"logs/backup/strip_qty_legacy_{ts}"
    file_hits = collections.defaultdict(list)
    for b, no, span, whole, inner, r in qty_hits + gen_hits:
        file_hits[(b, no)].append((span, whole, inner, r))

    total, files_changed = 0, 0
    for (b, no), hits in sorted(file_hits.items()):
        f = f"tagged/{b}/{no:03d}.tagged.md"
        raw = open(f, encoding="utf-8", newline="").read()
        os.makedirs(os.path.join(bak, b), exist_ok=True)
        open(os.path.join(bak, b, f"{no:03d}.tagged.md"), "w",
             encoding="utf-8", newline="").write(raw)
        hits = sorted(hits, key=lambda h: h[0])
        out = strip_text(raw, hits)
        # 剥标断言（规范 sk 口径）：摘标只去符号，剥标文本逐字不变
        assert _C1.sk(out) == _C1.sk(raw), f"剥标断言失败 {b} {no:03d}"
        assert out != raw, f"无实际改动 {b} {no:03d}"
        open(f, "w", encoding="utf-8", newline="").write(out)
        total += len(hits)
        files_changed += 1
        print(f"  wrote {b} {no:03d}: -{len(hits)} token")
    print(f"\nAPPLY 完成：{total} token / {files_changed} 文件；备份 {bak}")

    if piped:
        print(f"提醒：{len(piped)} 处带管道候选未摘（见上方报告），需人工裁定。")


if __name__ == "__main__":
    main()
