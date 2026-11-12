#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N1 · 章回结构标注生成器 —— generate_pn_wuxia.py（消费 N2）

规范源（唯一）：skills/SKILL_02a_02b_章回结构与韵文处理.md（v0.3-draft）
按 §8.1 阶段流水实现：
  阶段 1 回目识别   行首"第N回" → `# [0] 第N回　回目对句`（原文全角空格与用字不改一字）；
                    分句拆分（全角空格界）入 JSON sidecar（§2.2，分句 2/4 常态，3/5 存疑）
  阶段 2 章首探测   [0] 后第一候选组过 N2 决策树（context=章首）→ 词/诗围栏（整体 [1]，
                    署名行入围栏末行）或正文首段 [1]；无章首词不补写不占位（§2.3）
  阶段 3 段落编号   按空行分段分配 [N]（两级；对话不拆，§3.4 默认裁决，--split-dialogue
                    仅预留开关）；围栏块恰一 PN 在内容首行；正文编号跨围栏连续递增（§3.3）
  阶段 4 围栏标注   回末对（行首正是+支路 C+回末位置）与回末套语（词族正则 §6.3，
                    "欲如"等变体原字保留）分块两 PN 两围栏（§2.4）；回中即兴诗/对联
                    过 N2 检测 + 三判据（§4.3）——行内引语永不围栏
  阶段 5 自检       可逆性内置：产物剥除全部 PN 标记与围栏行后与底本逐字符比对，
                    不一致报错退出 1；--verify 显式报告

纯标准库。输出：config.struct_path(书, 回) 结构文件（PN+围栏，无实体/动词标注）
+ 同名 .struct.json sidecar（回目元数据/围栏清单/存疑清单）。
CLI：python generate_pn_wuxia.py --book <名> --chapter <n> | --all   [--verify] [--split-dialogue]
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import symbols
import detect_verse_wuxia as dv

# 回目行（行首"第N回"，中文数字容忍，承 config.CHAPTER_FILE_RE 风格）
TITLE_RE = re.compile(r"^\s*第([一二三四五六七八九十百零〇\d]+)回")
# 回末套语词族（§6.3 按词族不按字面：欲知/欲如/欲看 + [请/且/要][听/看]下回分解）
TAOYU_HEAD_RE = dv.TAOYU_HEAD_RE
TAOYU_TAIL_RE = dv.TAOYU_TAIL_RE
TAOYU_MAX_CHARS = 60     # 套语公式块长度上限（超长视为正文含套语，存疑）——待试点校准
MID_VERSE_TH = 0.75      # 回中即兴韵文（支路 A/B）围栏保守阈值：宁漏围栏勿错围栏（§1.4/§5.2），
                         # 0.6-0.75 区间保持正文并入存疑清单——待试点校准
# 三判据之"自称文体"（§4.3）：宿主引出句/引号与韵文共段 → 行内引语，永不围栏
NARR_FUSED_RE = re.compile(r"(说道|笑道|喝道|叫道|问道|答道|骂道|喊道|写道|吟道|唱道|赞道"
                           r"|叹道|朗声道|低声道|冷冷道|沉声道|念道|：“|”)")
# 回末对弱信号：叙述段末"正是："引出下一段对句（2026-11-05 新增，G-24 延伸；
# 《江湖三女侠》全书为"段末正是：+ 独立对句段"格式，原实现只认"行首正是"故 48 回 0 围栏）
ZHENGSHI_RE = re.compile(r"正是[：:]\s*$")
VERSE_GROUP_MAX = 4       # 署名行结尾韵文组回溯上限（段数），防误并长段


# ==================== 阶段 1：回目识别 ====================
def read_chapter(raw):
    """底本原文 → (回目行原文, blocks=[(起始行号 1-based, [原始行...])])。不改一字。"""
    lines = raw.splitlines()
    ti = None
    for i, ln in enumerate(lines):
        if TITLE_RE.match(ln):
            ti = i
            break
    if ti is None:
        # 楔子：回目行为首行「楔子　…」（no=0 场景，七剑/萍踪/龙虎/武当一剑同式）
        for i, ln in enumerate(lines):
            if ln.strip().startswith("楔子"):
                ti = i
                break
    if ti is None:
        raise ValueError("回目行未找到（行首'第N回'）")
    title_raw = lines[ti].rstrip()
    blocks = dv._split_blocks(lines[ti + 1:])
    return title_raw, blocks


def title_meta(title_raw):
    """回目元数据：全角空格拆分句，前半归上联、后半归下联（§2.2）。"""
    parts = [p for p in title_raw.split("\u3000") if p]
    number = parts[0] if parts else ""
    clauses = parts[1:]
    ok = len(clauses) in (2, 4)
    half = len(clauses) // 2 if ok else len(clauses)
    return {
        "raw": title_raw,
        "number": number,
        "clauses": clauses,
        "clause_count": len(clauses),
        "upper": clauses[:half] if ok else [],
        "lower": clauses[half:] if ok else [],
        "clause_count_ok": ok,
    }


# ==================== 阶段 2：章首探测 ====================
def detect_head(blocks):
    """[0] 后第一候选组（N2 group_chapter_head 贪心合并）过决策树（context=章首）。

    02ab 围栏修复（2026-11-05 批次）：旧稿逐句成段（诗/歌每句一段），N2 章首组只合并
    “似韵文段”（≥2 句），单句成段的歌词/七言首段即中断导致整首漏检。故常规判定未成立
    时用 N2.chapter_head_verse 兜底（窄规则：歌组需后段歌/唱叙述信号；诗组需两段四句
    整齐五七言 + 偶句同韵），见 scripts/detect_verse_wuxia.py 常量区注释。

    返回 (N2 结果 dict | None, 消耗段数, 组内 blocks)。
    """
    if not blocks:
        return None, 0, []
    paras = [ls for _, ls in blocks]
    group, consumed = dv.group_chapter_head(paras)
    lines = [ln for g in group for ln in g]
    res = dv.detect_block(lines, {"position": "章首"})
    if res["type"] not in ("词", "诗", "歌"):
        rescue = dv.chapter_head_verse(paras)
        if rescue:
            return rescue, rescue["consumed"], blocks[:rescue["consumed"]]
    return res, consumed, blocks[:consumed]


# ==================== 阶段 4 辅助：行内引语三判据（§4.3） ====================
def standalone_verse(ls, res):
    """三判据（成段/完整/自称文体），全部满足才围栏——行内引语永不围栏。

    判据 1 成段：候选为独立段落块，由分段构造保证；
    判据 2 完整：韵文 ≥4 句（绝句起步）；支路 C 对句 ≥2 分句；
    判据 3 自称文体：无引号包裹、无宿主引出句共段（剥除引文后叙述自足）。
    """
    text = "".join(ls)
    if "“" in text or "”" in text:
        return False
    if NARR_FUSED_RE.search(text):
        return False
    st = dv.sentences_of(dv.clean_lines(ls))
    min_sents = 2 if res.get("branch") == "C" else 4
    return len(st) >= min_sents


# ==================== 可逆性自检（§4.2 铁律 5） ====================
PN_LINE_RE = re.compile(r"^(?:#\s*)?\[\d+(?:\.\d+)?\]")


def strip_struct(text):
    """剥除围栏行（::: 开/闭）与行首 PN 标记 → 内容行序列。"""
    kept = []
    for ln in text.splitlines():
        if symbols.is_fence_close(ln) or symbols.fence_opens(ln):
            continue
        m = PN_LINE_RE.match(ln)
        if m:
            t = ln[m.end():]
            if t.startswith(" "):
                t = t[1:]
        else:
            t = ln
        kept.append(t.rstrip())
    return [k for k in kept if k.strip()]


def corpus_lines(raw):
    """底本内容行序列（去空行、去行尾空白）。"""
    return [ln.rstrip() for ln in raw.splitlines() if ln.strip()]


def verify_text(struct_text, corpus_raw):
    """逐字符比对。返回 (ok, diffs)。"""
    a = strip_struct(struct_text)
    b = corpus_lines(corpus_raw)
    if a == b:
        return True, []
    diffs = []
    if len(a) != len(b):
        diffs.append(f"行数不同：底本 {len(b)} 行 vs 产物剥标后 {len(a)} 行")
    shown = 0
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            diffs.append(f"第 {i + 1} 内容行不一致：\n  底本：{b[i][:60]}\n  产物：{a[i][:60]}")
            shown += 1
            if shown >= 5:
                break
    if not diffs:
        diffs.append("前缀一致但长度不符（见行数差异）")
    return False, diffs


# ==================== 主流程（§8.1 阶段流水） ====================
def process_chapter(book, no, verify_flag=False):
    path = config.chapter_path(book, no)
    raw = path.read_text(encoding="utf-8-sig")
    title_raw, blocks = read_chapter(raw)
    meta = title_meta(title_raw)
    n = len(blocks)
    if not meta["clause_count_ok"]:
        pass  # 存疑在下方统一登记
    out = [f"# {symbols.PN_TITLE} {title_raw}", ""]
    pn = 1
    fences = []
    doubts = []
    warnings = []
    if not meta["clause_count_ok"]:
        doubts.append({
            "where": "回目行",
            "what": f"分句数 {meta['clause_count']}（{'　'.join(meta['clauses'])}）",
            "leaning": "回目变格不判错（02ab §2.2），上/下联拆分人工复核",
            "reason": "分句数 2/4 视为常态；3/5 进存疑清单",
        })

    def emit_fence(ftype, block, res_extra=None):
        nonlocal pn
        _, ls = block
        out.append(f"::: {ftype}")
        out.append(f"[{pn}] {ls[0]}")
        for extra in ls[1:]:
            out.append(extra)
        out.append(":::")
        out.append("")
        fences.append({"pn": pn, "type": ftype, "line": block[0], **(res_extra or {})})
        pn += 1

    def emit_plain(block):
        nonlocal pn
        _, ls = block
        out.append(f"[{pn}] {ls[0]}")
        for extra in ls[1:]:
            out.append(extra)
        out.append("")
        pn += 1

    # ---- 阶段 2：章首探测（无词不占位，§2.3） ----
    head_res, consumed, head_group = detect_head(blocks)
    head_fenced = False
    if head_res and head_res["type"] in ("词", "诗", "歌"):
        sig = ""
        out.append(f"::: {head_res['type']}")
        for bi, block in enumerate(head_group):
            _, ls = block
            for li, l in enumerate(ls):
                if bi == 0 and li == 0:
                    out.append(f"[{pn}] {l}")
                elif dv.SIG_RE.match(l.strip()):
                    sig = l.strip()          # 署名行入围栏末行，不单独编号（S14）
                    out.append(l)
                else:
                    out.append(l)
            if bi < len(head_group) - 1:
                out.append("")               # 阕间空行保留在围栏内（§2.3/S12）
        out.append(":::")
        out.append("")
        fences.append({"pn": pn, "type": head_res["type"], "branch": head_res["branch"],
                       "score": round(head_res["score"], 2),
                       "lines": sum(len(ls) for _, ls in head_group),
                       "signature": sig, "position": "章首"})
        pn += 1
        head_fenced = True
    elif head_res and head_res["type"] == "存疑":
        doubts.append({
            "where": f"章首候选组（底本行 {blocks[0][0]} 起 {consumed} 段）",
            "what": head_res.get("metrics"),
            "score": round(head_res["score"], 2),
            "leaning": "章首韵文候选，灰区保守不围栏，待人工裁决",
            "reason": "；".join(head_res["doubts"]),
        })

    # ---- 阶段 3 预处理：以"调寄/右调"署名行为锚的韵文组（回末词/回中词，如 048 回《踏莎行》） ----
    # 阕间断段在底本中以空行分段，逐块检测会把一整首词拆碎；故先以署名行为锚向前回溯
    # 似韵文段（≤VERSE_GROUP_MAX 段），整组一 PN 一围栏（§2.3/S12）。章首组由阶段 2 处理。
    def emit_verse_group(ftype, grp, res_extra=None):
        nonlocal pn
        out.append(f"::: {ftype}")
        for bi, (_, gls) in enumerate(grp):
            for li, l in enumerate(gls):
                if bi == 0 and li == 0:
                    out.append(f"[{pn}] {l}")
                else:
                    out.append(l)
            if bi < len(grp) - 1:
                out.append("")               # 阕间空行保留在围栏内（§2.3/S12）
        out.append(":::")
        out.append("")
        fences.append({"pn": pn, "type": ftype, "line": grp[0][1][0], **(res_extra or {})})
        pn += 1

    head_start = consumed if head_fenced else 0
    sig_groups = {}
    gi = head_start
    while gi < n:
        one_line_sig = (len(blocks[gi][1]) == 1
                        and bool(dv.SIG_RE.match(blocks[gi][1][0].strip())))
        if one_line_sig and gi > head_start:
            start = gi
            while (start - 1 >= head_start and gi - start < VERSE_GROUP_MAX
                   and dv.plausible_verse(blocks[start - 1][1])):
                start -= 1
            if start < gi:
                sig_groups[start] = gi
                gi += 1
                continue
        gi += 1

    # ---- 阶段 3+4：逐块编号与围栏标注 ----
    # 02ab 围栏修复（2026-11-05 批次）：续书预告回末边界（末段不标围栏，§2.4/§6.3 扩展）。
    # 塞外 028/冰魄 012 旧稿以"欲知…请续看拙著…"收束全书，属回末边界段，整段不标。
    paras = [ls for _, ls in blocks]
    tail = dv.tail_prediction(paras)
    skip_until = -1
    for k, block in enumerate(blocks):
        if k < skip_until:
            continue
        if head_fenced and k < consumed:
            continue                          # 已随章首围栏整体一 PN
        line_no, ls = block
        text = ls[0].strip()
        position = "回末" if k >= n - 2 else "回中"
        prev_last = blocks[k - 1][1][-1].strip() if k > 0 else ""

        if not head_fenced and k < consumed:
            emit_plain(block)                 # 章首候选组未围栏 → 逐段正文编号
            continue

        # 续书预告回末边界（02ab 修复）：整段一围栏，回末最后内容块（含"（全书完）"）
        if tail and k == tail["start"]:
            grp = blocks[k:k + tail["consumed"]]
            emit_verse_group("回末", grp,
                             {"branch": "续书预告", "position": "回末",
                              "reason": tail["reason"]})
            skip_until = k + tail["consumed"]
            continue

        # 署名行收尾韵文组（回末词/回中词）：整体一 PN 一围栏
        if k in sig_groups:
            last = sig_groups[k]
            grp = blocks[k:last + 1]
            grp_pos = "回末" if last >= n - 2 else "回中"
            emit_verse_group("词", grp,
                             {"branch": "SIG", "position": grp_pos,
                              "signature": grp[-1][1][-1].strip()})
            skip_until = last + 1
            continue

        # 02ab 修复：词道/词曰 引出上下两阕（旧稿两段排版，回中填词）——宿主引出句留正文
        ci = dv.ci_intro_group(paras, k) if k + 1 + dv.CI_INTRO_MAX_BLOCKS <= n else None
        if ci:
            emit_plain(block)
            grp = blocks[k + 1:k + 1 + ci["consumed"]]
            emit_verse_group("词", grp,
                             {"branch": ci["branch"], "score": round(ci["score"], 2),
                              "position": "回中"})
            skip_until = k + 1 + ci["consumed"]
            continue

        # 02ab 修复：唱道/歌曰/吟道 引出逐行成段歌组（旧稿每句一段，回中即兴歌）
        song = dv.song_intro_group(paras, k)
        if song:
            emit_plain(block)
            grp = blocks[k + 1:k + 1 + song["consumed"]]
            emit_verse_group("歌", grp,
                             {"branch": "逐行歌组", "position": "回中",
                              "lines": song["consumed"]})
            skip_until = k + 1 + song["consumed"]
            continue

        # 强信号：回末套语词族（§6.2/§6.3，按词族不按字面；变体原字保留）
        if (TAOYU_HEAD_RE.search(text) and TAOYU_TAIL_RE.search(text)
                and len(ls) <= 2 and len(text) <= TAOYU_MAX_CHARS):
            emit_fence("回末", block, {"branch": "词族", "position": position})
            if position != "回末":
                warnings.append(f"回末套语出现在非回末位置（底本行 {line_no}），已围栏，请人工复核")
            continue

        # G-24 延伸（2026-11-05）：叙述段末"正是："+ 下一段对句 → 回末对。
        # 原实现只认"行首正是"；《江湖三女侠》全书为"段末正是：+ 独立对句段"格式
        # （48 回同构），支路 C 结构门槛（≤2 行/无叙事框架/分句 2·4/字数相等）全过即
        # 围栏，不依赖对仗词频分（简化词性词典对宽对/借对易误判，见 docs/36 G-24）。
        if position == "回末" and ZHENGSHI_RE.search(prev_last):
            r = dv.detect_block(ls, {"position": position})
            c_ok = r.get("metrics", {}).get("支路", {}).get("C", {}).get("有效")
            joined = "".join(ls)
            if (c_ok and len(ls) <= dv.C_MAX_LINES
                    and "“" not in joined and "”" not in joined):
                emit_fence("回末对", block,
                           {"branch": "回末正是惯例(G-24延伸)", "score": round(r["score"], 2),
                            "position": position})
                continue

        # 弱信号：行首"正是："（§6.2）→ 支路 C；回末→回末对，回中→对联（S06 先核位置）
        if text.startswith("正是"):
            r = dv.detect_block(ls, {"position": position})
            if r["type"] in ("回末对", "对联") and r["score"] >= dv.TH_VERSE:
                emit_fence(r["type"], block,
                           {"branch": r["branch"], "score": round(r["score"], 2),
                            "position": position})
            elif position == "回末" and r.get("metrics", {}).get("支路", {}).get("C", {}).get("有效"):
                # G-24 终裁（2026-11-04，docs/36）：回末位置 + 行首正是 + 支路 C 门槛全过
                # （≤2 行 / 无叙事框架 / 分句 2·4 / 字数相等）→ 章回体回末对结构惯例，
                # 直接围栏，不依赖对仗抽查分数（简化词性词典对宽对/借对易误判 0/4，
                # 见 005/015/017 三例得分 0.40 落灰区）。
                emit_fence("回末对", block,
                           {"branch": "回末正是惯例(G-24终裁)", "score": round(r["score"], 2),
                            "position": position})
            else:
                if r["type"] == "存疑":
                    doubts.append({
                        "where": f"底本行 {line_no}",
                        "what": text[:40],
                        "score": round(r["score"], 2),
                        "leaning": "正是引出对句候选，灰区不围栏",
                        "reason": "；".join(r["doubts"]),
                    })
                emit_plain(block)
            continue

        # 孤立词牌署名行（§6.4：前无韵文块 → 存疑清单）
        if dv.SIG_RE.match(text):
            doubts.append({
                "where": f"底本行 {line_no}",
                "what": text[:40],
                "leaning": "孤立署名行，无韵文块可附",
                "reason": "02ab §6.4：孤立'调寄/右调 X'行进存疑清单",
            })
            emit_plain(block)
            continue

        # 回中即兴诗/对联：N2 检测 + 三判据（行内引语永不围栏）
        r = dv.detect_block(ls, {"position": position})
        # 支路 C 门槛已严（≤2 行/无叙事框架/字数相等）持 0.6；韵文（A/B）用保守阈值
        need = dv.TH_VERSE if r["branch"] == "C" else MID_VERSE_TH
        if (r["type"] in ("词", "诗", "歌", "对联")
                and r["score"] >= need and standalone_verse(ls, r)):
            ftype = r["type"]
            if ftype == "对联" and position == "回末":
                ftype = "回末对"          # 回末位置的对句按 02ab 归回末对（2026-11-05）
            emit_fence(ftype, block,
                       {"branch": r["branch"], "score": round(r["score"], 2),
                        "position": position})
        else:
            if r["type"] in ("存疑", "词", "诗", "歌", "对联"):
                if r["type"] == "存疑":
                    leaning = "韵文候选落灰区，保守保持正文段"
                    reason = "；".join(r["doubts"])
                elif r["score"] < need:
                    leaning = "回中韵文候选低于保守围栏阈值，保持正文段"
                    reason = f"得分 {r['score']:.2f} < 回中保守阈值 {MID_VERSE_TH}（宁漏勿错）"
                else:
                    leaning = "韵文候选不满足行内引语三判据（§4.3），保持正文段"
                    reason = "引号包裹或宿主引出句共段 → 行内引语，永不围栏"
                doubts.append({
                    "where": f"底本行 {line_no}",
                    "what": text[:40],
                    "score": round(r["score"], 2),
                    "leaning": leaning,
                    "reason": reason,
                })
            emit_plain(block)

    # 回末容缺检查（§2.4：无回末对/无套语为合法变体；lint E12 warning）
    tail_texts = [ls[0].strip() for _, ls in blocks[-2:]] if blocks else []
    if not any(TAOYU_HEAD_RE.search(t) and TAOYU_TAIL_RE.search(t) for t in tail_texts):
        warnings.append("回末套语词族未命中（末两块）——容缺合法（E12 warning，实测 27/32 回有套语）")

    struct_text = "\n".join(out).rstrip() + "\n"

    # ---- 阶段 5：可逆性自检（内置，不一致即报错退出 1） ----
    ok, diffs = verify_text(struct_text, raw)
    if not ok:
        raise SystemExit("可逆性自检失败（剥 PN+围栏行后与底本不一致）：\n" + "\n".join(diffs))
    verify_status = "pass"

    # ---- 输出：结构文件 + JSON sidecar ----
    sp = config.struct_path(book, no)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(struct_text, encoding="utf-8")
    if verify_flag:
        ok2, diffs2 = verify_text(sp.read_text(encoding="utf-8"), raw)
        verify_status = "pass" if ok2 else "fail"
        if not ok2:
            print("可逆性复核失败：\n" + "\n".join(diffs2))
            sys.exit(1)

    sidecar = {
        "book": book,
        "chapter": no,
        "source": path.name,
        "spec": f"SKILL_02a/02b v{config.SPEC_VERSION}",
        "generator": "generate_pn_wuxia.py",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "title": meta,
        "pn_total": pn - 1,
        "fences": fences,
        "doubts": doubts,
        "warnings": warnings,
        "reversibility": verify_status,
    }
    jp = sp.parent / f"{no:03d}.struct.json"
    jp.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": sp, "sidecar": jp, "pn_total": pn - 1, "fences": fences,
            "doubts": doubts, "warnings": warnings, "reversibility": verify_status}


def main():
    ap = argparse.ArgumentParser(description="N1 章回结构标注生成器（PN+围栏，SKILL_02a/02b §8.1）")
    ap.add_argument("--book", required=True, help="书名（config.books() 键）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--chapter", type=int, help="单回回号（1-based）")
    g.add_argument("--all", action="store_true", help="全书全部回")
    ap.add_argument("--verify", action="store_true",
                    help="生成后重读产物做可逆性复核并显式报告（不一致退出 1）")
    ap.add_argument("--split-dialogue", action="store_true",
                    help="预留开关：对话拆分逻辑未实现（02ab §3.4 默认不拆裁决；试点后按判据启用）")
    args = ap.parse_args()
    if args.split_dialogue:
        print("[提示] --split-dialogue 仅预留：拆分逻辑未实现，默认不拆（02ab §3.4 裁决，"
              "试点后按'纯对话段 ∧ ≥3 轮 ∧ ≥500 字'判据启用）。")
    meta = config.books().get(args.book)
    if not meta:
        print(f"错误：书目未发现：{args.book}（可选：{config.book_names()}）")
        sys.exit(2)
    chapters = [args.chapter] if args.chapter else range(1, meta["chapters"] + 1)
    for no in chapters:
        s = process_chapter(args.book, no, verify_flag=args.verify)
        msg = (f"{args.book} 第 {no:03d} 回 → {s['path']}\n"
               f"  PN 总数 {s['pn_total']}；围栏 {len(s['fences'])} 处："
               + ("；".join(f"[{f['pn']}]{f['type']}({f.get('branch')},"
                           f"{f.get('score', '-')})" for f in s["fences"]) or "无")
               + f"；存疑 {len(s['doubts'])} 条；可逆性 {s['reversibility']}")
        print(msg)
        for w in s["warnings"]:
            print(f"  [warning] {w}")


if __name__ == "__main__":
    main()
