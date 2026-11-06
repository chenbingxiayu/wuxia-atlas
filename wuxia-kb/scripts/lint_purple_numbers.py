#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/lint_purple_numbers.py（2026-11-03）；改动：
#   1. 路径改经 config：默认扫 config.DIR_TAGGED（<书>/NNN.tagged.md），
#      新增 --book 单书；保留原位置参数习惯（位置参数=单回编号，如 001）；
#   2. 措辞"篇名"→"回目"（E6，对应 02ab §2.2 回目行定版）；
#   3. 新增武侠检查项 E7-E17（skills/SKILL_02a_02b_章回结构与韵文处理.md §9.1），
#      error/warning 分级照规格；全部阈值以常量置文件头，标"待试点校准"；
#   4. 符号/围栏/标注字符类一律 import symbols（shiji 15 处内联字符类债不重演）；
#   5. PN 提取兼容对话拆分列表项 `- [N.M]`（02ab §3.2/§3.4）；
#   6. 原第 7 项"缺失段落编号"保留为辅助项 AUX（不计入 E 系列，warning 级），
#      并加围栏内容跳过（围栏内仅首 PN，不按正文段落规则要求逐段编号）；
#   7. 退出码：存在 error → 1；仅 warning → 0（02ab §8.1 验收门：
#      "error 清零，warning 有处置记录"）。

import argparse
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols

# --------------------------------------------------------------- 阈值常量 ----
# 02ab §9.1/§5.6：所有阈值默认值均标"待试点校准"——调参只动这里。
VERSE_BLOCK_MAX = 5          # E14 单回韵文块数上限（>5 → warning）
VERSE_RATIO_MAX = 0.20       # E14 韵文块占顶级块比例上限（>0.20 → warning）
PROSE_RATIO_MIN = 0.50       # E17 正文段占顶级块比例下限（<0.50 → warning）
FENCE_PSEUDO_OPENERS = ("但见", "只见", "却见")  # E15 伪信号哨兵（02ab §6.2 实测）
# E16 围栏内禁半角标点（02ab §4.2 铁律 4）；保守集，待试点校准
HALFWIDTH_PUNCT = set(',.;:!?()"\'<>')
# E13 章首 [1] 允许的围栏类型（2026-11-05 设计补正：02ab §2.3 章首约定原文只列 词/诗，
# 但塞外 001 旧稿先例为 `::: 歌`（5 行短句哈萨克迎客歌）——旧稿先例 + 窄规则守卫
# （逐行短句组 + 后段歌/唱叙述信号）下允许"歌"落章首；"允许"≠"强制"，不放松其他检查）
E13_HEAD_FENCES = {"词", "诗", "歌"}
VERSE_FENCES = {"词", "诗", "歌", "对联", "回末对"}  # E14 韵文块（02ab §9.2 口径）
# E9 观察类围栏启用登记簿（02ab §4.1：观察类逐例登记，禁止批量预围栏）
OBSERVE_REGISTRY = config.DIR_REGISTRY / "observe_fences.json"
# E12 回末套语词族：改为 symbols.is_taoyu（02ab §6.3 单一来源，2026-11-05 与生成器对齐）

TAGGED_FILE_RE = re.compile(r"^(\d{1,3})\.(?:struct|tagged)\.md$")
PN_LINE_RE = re.compile(r"^(-\s*)?\[(\d+(?:\.\d+)*)\]\s*")   # 兼容 `- [N.M]` 列表项
HEADING_PN_RE = re.compile(r"^(#{2,6})\s+\[(\d+(?:\.\d+)*)\]\s+(.+)$")
H1_PN_RE = re.compile(r"^#\s+\[(\d+(?:\.\d+)*)\]\s*(.*)$")

# E 系列元数据：分级照 02ab §9.1 定版
E_META = {
    "E1":  ("error",   "E1 PN 格式（[N]/[N.M]，无字母中文；三级禁用）"),
    "E2":  ("error",   "E2 同层编号连续不跳号"),
    "E3":  ("error",   "E3 父子关系（子必有父）"),
    "E4":  ("error",   "E4 标题不含编号（# [0] 回目例外）"),
    "E5":  ("error",   "E5 无重复编号"),
    "E6":  ("error",   "E6 回目 [0] 恰一个且在文件首"),
    "E7":  ("error",   "E7 回号连续（每书无缺号、无重复）"),
    "E8":  ("error",   "E8 围栏成对闭合、不跨回、不嵌套"),
    "E9":  ("error",   "E9 围栏类型在枚举内；观察类启用须有登记"),
    "E10": ("error",   "E10 围栏内 PN 恰一且位于内容首行"),
    "E11": ("warning", "E11 回末顺序（回末对在前；回末为最后内容块）"),
    "E12": ("warning", "E12 回末套语缺失（词族匹配不到；容缺）"),
    "E13": ("error",   "E13 章首结构（[1] 围栏 ∈ {词, 诗, 歌} 或无围栏）"),
    "E14": ("warning", "E14 韵文密度异常（阈值待试点校准）"),
    "E15": ("warning", "E15 伪信号误围栏（但见/只见/却见）"),
    "E16": ("error",   "E16 围栏内半角标点"),
    "E17": ("warning", "E17 正文分母完整性（阈值待试点校准）"),
    "AUX": ("warning", "AUX 缺失段落编号（shiji 继承辅助项，不计入 E 系列）"),
}
E_ORDER = list(E_META)


class PurpleNumberLinter:
    """Purple Numbers + 章回结构检查器（武侠版 E1-E17）"""

    def __init__(self, verbose=False):
        self.verbose = verbose
        self.issues = defaultdict(list)

    def _add(self, code, line=0, content='', reason=''):
        self.issues[code].append({'line': line, 'content': content, 'reason': reason})

    # ------------------------------------------------------------- 主入口 ----
    def check_file(self, file_path, book=None, chapter=None):
        """检查单个回文件的所有编号与结构问题"""
        self.issues = defaultdict(list)
        lines = file_path.read_text(encoding='utf-8').splitlines()

        fences, fence_errors = self._scan_fences(lines)
        pn_items = self._extract_paragraph_numbers(lines)

        # 行号(0-based) → 围栏下标
        line2fence = {}
        for idx, f in enumerate(fences):
            end = f['close_line'] if f['close_line'] is not None else len(lines) - 1
            for ln in range(f['open_line'], end + 1):
                line2fence[ln] = idx

        self._check_format(lines)                                  # E1
        self._check_continuity(pn_items)                           # E2
        self._check_parent_child(pn_items)                         # E3
        self._check_heading_numbers(lines)                         # E4
        self._check_duplicates(pn_items)                           # E5
        self._check_title_number(lines)                            # E6
        self._check_fences(fences, fence_errors, lines,            # E8/E9/E10/E11/
                           line2fence, pn_items,                   #     E12/E13/E14/
                           book=book, chapter=chapter)             #     E15/E16/E17
        self._check_missing_pn(lines, line2fence)                  # AUX
        return self.issues

    # ------------------------------------------------------------- 基础件 ----
    @staticmethod
    def _extract_paragraph_numbers(lines):
        """提取文件中的所有段落编号（含 `- [N.M]` 列表项）"""
        numbers = []
        for i, line in enumerate(lines):
            m = PN_LINE_RE.match(line.strip())
            if m:
                numbers.append({'pn': m.group(2), 'line': i + 1,
                                'content': line.strip()})
        return numbers

    @staticmethod
    def _scan_fences(lines):
        """扫描围栏 → (围栏列表, 围栏结构错误列表)。

        围栏元素：{type, open_line, close_line(None=未闭合), content, pns}。
        """
        fences, errors, cur = [], [], None
        for i, raw in enumerate(lines):
            s = raw.strip()
            if symbols.is_fence_close(s):
                if cur is None:
                    errors.append((i + 1, "围栏闭合行「:::」无对应开启行——02ab §4.2 铁律 1"))
                else:
                    cur['close_line'] = i
                    fences.append(cur)
                    cur = None
                continue
            ftype = symbols.fence_opens(s)
            if ftype is not None:
                if cur is not None:
                    errors.append((i + 1,
                                   f"围栏嵌套：「{ftype}」开于「{cur['type']}」"
                                   f"（行 {cur['open_line'] + 1}）内——02ab §4.2 铁律 2"))
                else:
                    cur = {'type': ftype, 'open_line': i, 'close_line': None,
                           'content': [], 'pns': []}
                continue
            if cur is not None:
                cur['content'].append((i, s))
                m = PN_LINE_RE.match(s)
                if m:
                    cur['pns'].append((m.group(2), i))
        if cur is not None:
            fences.append(cur)  # 未闭合围栏（E8 判定）
        return fences, errors

    @staticmethod
    def _load_observe_registry():
        """E9 观察类围栏登记簿 → {"书/回:类型"} 集合；登记簿缺失 = 全部未登记。"""
        if not OBSERVE_REGISTRY.exists():
            return set()
        try:
            data = json.loads(OBSERVE_REGISTRY.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return set()
        items = data.get('items', data if isinstance(data, list) else [])
        out = set()
        for it in items:
            if isinstance(it, dict):
                out.add(f"{it.get('book', '*')}/{it.get('chapter', '*')}"
                        f":{it.get('fence', it.get('type', ''))}")
            elif isinstance(it, str):
                out.add(it)
        return out

    # ------------------------------------------------- E1 格式（继承①） ----
    def _check_format(self, lines):
        for i, line in enumerate(lines):
            s = line.strip()
            m = re.match(r'^\[([^\]]+)\]', s)
            if not m:
                continue
            pn = m.group(1)
            if not re.match(r'^\d+(?:\.\d+)*$', pn):
                self._add('E1', i + 1, s, '编号格式错误（只允许数字和点，如 [1] 或 [1.2]）')
                continue
            if pn.count('.') + 1 > symbols.PN_MAX_LEVEL:
                self._add('E1', i + 1, s,
                          f"三级及以上编号禁用（02ab §3.1：只用两级，"
                          f"PN_MAX_LEVEL={symbols.PN_MAX_LEVEL}）")

    # --------------------------------------------- E2 连续性（继承②） ----
    def _check_continuity(self, pn_items):
        levels = defaultdict(list)
        for item in pn_items:
            parts = item['pn'].split('.')
            key = '1' if len(parts) == 1 else '.'.join(parts[:-1])
            levels[key].append(item)

        for _level_key, items in levels.items():
            numbers = sorted(
                ((int(it['pn'].split('.')[-1]), it) for it in items),
                key=lambda x: x[0])
            for i in range(len(numbers) - 1):
                cur_num, cur_item = numbers[i]
                next_num, next_item = numbers[i + 1]
                if next_num != cur_num + 1:
                    expected = self._increment_pn(cur_item['pn'])
                    self._add('E2', next_item['line'], f"[{next_item['pn']}]",
                              f"编号跳跃：{cur_item['pn']} → {next_item['pn']}"
                              f"（缺少 {expected}）")

    @staticmethod
    def _increment_pn(pn):
        parts = pn.split('.')
        parts[-1] = str(int(parts[-1]) + 1)
        return '.'.join(parts)

    # ------------------------------------------- E3 父子关系（继承③） ----
    def _check_parent_child(self, pn_items):
        level1 = set()
        children = defaultdict(list)
        for item in pn_items:
            pn = item['pn']
            if '.' in pn:
                children[pn.split('.')[0]].append(item)
            else:
                level1.add(pn)
        for parent, kids in children.items():
            if parent not in level1:
                self._add('E3', kids[0]['line'],
                          '、'.join(f"[{c['pn']}]" for c in kids),
                          f"子编号 [{kids[0]['pn']}] 缺少父编号 [{parent}]"
                          f"（02ab §3.2：有子必有父）")

    # ------------------------------------------- E4 标题编号（继承④） ----
    def _check_heading_numbers(self, lines):
        for i, line in enumerate(lines):
            s = line.strip()
            m = HEADING_PN_RE.match(s)
            if m:
                self._add('E4', i + 1, s,
                          f"{m.group(1)} 级标题不应包含编号（# [0] 回目行例外；"
                          f"## 可选层若启用同规则，02ab §9.1 E4）")

    # --------------------------------------------- E5 重复（继承⑤） ----
    def _check_duplicates(self, pn_items):
        seen = defaultdict(list)
        for item in pn_items:
            seen[item['pn']].append(item['line'])
        for pn, linenos in seen.items():
            if len(linenos) > 1:
                self._add('E5', linenos[0], f"[{pn}]",
                          f"编号 [{pn}] 重复出现 {len(linenos)} 次（行 "
                          f"{', '.join(map(str, linenos))}）")

    # --------------------------------- E6 回目 [0]（继承⑥，篇名→回目） ----
    def _check_title_number(self, lines):
        h1s = []
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith('# '):  # '# ' 不匹配 '## '（第二字符为 '#'）
                h1s.append((i, s))
        first_content = next((i for i, l in enumerate(lines) if l.strip()), None)

        zeros = []
        for i, s in h1s:
            m = H1_PN_RE.match(s)
            if not m:
                self._add('E6', i + 1, s, "一级标题缺少编号 [0]（回目行，02ab §2.2）")
            elif m.group(1) != '0':
                self._add('E6', i + 1, s,
                          f"一级标题编号应为 [0]（回目行），当前为 [{m.group(1)}]")
            else:
                zeros.append((i, s))

        if len(zeros) != 1:
            self._add('E6', 1, h1s[0][1] if h1s else '',
                      f"回目 [0] 应恰一个（当前 {len(zeros)} 个，02ab §2.2）")
        elif first_content is None or zeros[0][0] != first_content:
            self._add('E6', zeros[0][0] + 1, zeros[0][1],
                      "回目行必须在文件首（02ab §2.1 回内标准结构模板）")

    # ------------------------------------- E8-E17 围栏与章回结构（新增） ----
    def _check_fences(self, fences, fence_errors, lines, line2fence, pn_items,
                      book=None, chapter=None):
        # ---- E8 成对闭合、不跨文件、不嵌套 ----
        for ln, reason in fence_errors:
            self._add('E8', ln, f"行 {ln}", reason)
        for f in fences:
            if f['close_line'] is None:
                self._add('E8', f['open_line'] + 1, f"::: {f['type']}",
                          f"围栏「{f['type']}」未闭合（到文件尾）——02ab §4.2 铁律 1"
                          f"（一回一文件，围栏不跨文件）")

        # ---- E9 围栏类型枚举 + 观察类登记 ----
        registry = self._load_observe_registry()
        for f in fences:
            t = f['type']
            if t not in symbols.FENCE_ALL:
                self._add('E9', f['open_line'] + 1, f"::: {t}",
                          f"围栏类型「{t}」不在枚举内（02ab §4.1：正式 7 种+观察 3 种）")
            elif t in symbols.FENCE_OBSERVE:
                key = f"{book or '*'}/{chapter or '*'}:{t}"
                if key not in registry:
                    self._add('E9', f['open_line'] + 1, f"::: {t}",
                              f"观察类围栏「{t}」未登记（02ab §4.1：观察类启用须"
                              f"逐例登记于 {OBSERVE_REGISTRY.name}）")

        # ---- E10 围栏内 PN 恰一且在内容首行 ----
        for f in fences:
            pns = f['pns']
            if len(pns) != 1:
                detail = f"（{[p for p, _ in pns]}）" if pns else "（无 PN）"
                self._add('E10', f['open_line'] + 1, f"::: {f['type']}",
                          f"围栏内 PN 计数={len(pns)}{detail}，应恰为 1（02ab §3.3）")
                continue
            pn, ln = pns[0]
            first_content = next((no for no, s in f['content'] if s), None)
            if first_content is None or ln != first_content:
                self._add('E10', ln + 1, f"[{pn}]",
                          "围栏内 PN 不在内容首行（02ab §3.3）")

        # ---- E11/E12 回末顺序与套语 ----
        by_type = defaultdict(list)
        for f in fences:
            by_type[f['type']].append(f)
        hui_end = by_type.get('回末', [])
        hui_dui = by_type.get('回末对', [])
        if hui_end and hui_dui and hui_dui[0]['open_line'] > hui_end[0]['open_line']:
            self._add('E11', hui_dui[0]['open_line'] + 1, "::: 回末对",
                      "回末对应在回末套语之前（02ab §2.4）")
        if hui_end:
            end = hui_end[0]['close_line']
            end = len(lines) - 1 if end is None else end
            trailing = [i + 1 for i in range(end + 1, len(lines)) if lines[i].strip()]
            if trailing:
                self._add('E11', trailing[0], lines[trailing[0] - 1].strip()[:40],
                          "回末套语应为最后内容块（02ab §2.4）")
            text = symbols.strip_markup(' '.join(s for _, s in hui_end[0]['content']))
            if not symbols.is_taoyu(text):
                self._add('E12', hui_end[0]['open_line'] + 1,
                          f"::: 回末（行 {hui_end[0]['open_line'] + 1}）",
                          "回末围栏内容与回末套语词族不匹配（02ab §6.3："
                          "欲[知/如/看] + [请听/且听/且看/要知]?下回[分解/再/见]?；"
                          "与生成器共用 symbols.TAOYU_*（2026-11-05 对齐）；"
                          "原文变体一律保留原样，绝不改字）")
        else:
            self._add('E12', len(lines), '',
                      "本回无回末套语围栏（容缺，02ab §2.4：实测 27/32 回有套语）")

        # ---- E13 章首结构 ----
        pn1 = next((it for it in pn_items if it['pn'] == '1'), None)
        if pn1 is None:
            self._add('E13', 1, '',
                      "本回缺少 [1] 首块（02ab §2.3：[1] 恒为回目后第一个文本块）")
        else:
            fi = line2fence.get(pn1['line'] - 1)
            if fi is not None:
                t = fences[fi]['type']
                if t not in E13_HEAD_FENCES:
                    self._add('E13', pn1['line'], "[1]",
                              f"章首 [1] 所在围栏类型「{t}」不在 {{词, 诗, 歌}}"
                              f"（02ab §2.3/§9.1 E13；歌为 2026-11-05 设计补正）")

        # ---- E14 韵文密度（阈值待试点校准） ----
        top_blocks = [it for it in pn_items
                      if '.' not in it['pn'] and it['pn'] != symbols.PN_TITLE.strip('[]')]
        verse = [f for f in fences if f['type'] in VERSE_FENCES]
        if len(verse) > VERSE_BLOCK_MAX:
            self._add('E14', verse[0]['open_line'] + 1,
                      f"韵文块 {len(verse)} 个",
                      f"单回韵文块 {len(verse)} > {VERSE_BLOCK_MAX}"
                      f"（阈值待试点校准）")
        if top_blocks:
            ratio = len(verse) / len(top_blocks)
            if ratio > VERSE_RATIO_MAX:
                self._add('E14', verse[0]['open_line'] + 1,
                          f"韵文占比 {ratio:.0%}",
                          f"韵文块占顶级块 {ratio:.0%} > "
                          f"{VERSE_RATIO_MAX:.0%}（阈值待试点校准）")

        # ---- E15 伪信号误围栏（02ab §6.2 落点） ----
        for f in fences:
            first = next((s for _, s in f['content'] if s), '')
            bare = re.sub(r'^[\W_]+', '',
                          symbols.strip_markup(PN_LINE_RE.sub('', first)).strip())
            for opener in FENCE_PSEUDO_OPENERS:
                if bare.startswith(opener):
                    self._add('E15', f['open_line'] + 1, first[:40],
                              f"围栏「{f['type']}」内容首句以伪信号「{opener}」开头"
                              f"（02ab §6.2：叙事动词，疑误围栏；只见/但见永不单独"
                              f"触发围栏）")
                    break

        # ---- E16 围栏内半角标点（02ab §4.2 铁律 4） ----
        for f in fences:
            for ln, s in f['content']:
                bare = symbols.strip_markup(PN_LINE_RE.sub('', s))
                hits = sorted({ch for ch in bare if ch in HALFWIDTH_PUNCT})
                if hits:
                    self._add('E16', ln + 1, s[:50],
                              f"围栏内半角标点：{' '.join(hits)}（02ab §4.2 铁律 4）")

        # ---- E17 正文分母完整性（阈值待试点校准；口径 02ab §9.2） ----
        if top_blocks:
            prose = [it for it in top_blocks if (it['line'] - 1) not in line2fence]
            ratio = len(prose) / len(top_blocks)
            if ratio < PROSE_RATIO_MIN:
                self._add('E17', 0,
                          f"正文 {len(prose)}/顶级块 {len(top_blocks)}",
                          f"正文段占比 {ratio:.0%} < {PROSE_RATIO_MIN:.0%}"
                          f"（分母=回内正文段 PN，排除回目与全部围栏块；"
                          f"阈值待试点校准）")

    # -------------------------- AUX 缺失段落编号（shiji 原第 7 项，非 E 系列） ----
    def _check_missing_pn(self, lines, line2fence):
        in_table = False
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if not line:
                i += 1
                continue

            # 围栏内容行与围栏标记行跳过（围栏整体一 PN，见 02ab §3.3）
            if i in line2fence:
                in_table = False
                i += 1
                continue

            # Markdown 表格检测（排除标注消歧管道 symbols.PIPE）
            is_table_line = False
            if '|' in line:
                if line.startswith('|'):
                    is_table_line = True
                else:
                    bare = symbols.TOKEN_RE.sub('', line)
                    if bare.count('|') >= 2:
                        is_table_line = True
            if is_table_line:
                in_table = True
                i += 1
                continue
            elif in_table:
                in_table = False

            if in_table or line.startswith('#') or line.startswith('>'):
                i += 1
                continue
            if line in ('---', '***', '___', ':::'):
                i += 1
                continue

            has_prev_empty = (i == 0 or not lines[i - 1].strip())
            has_next_empty = (i >= len(lines) - 1 or not lines[i + 1].strip())

            if has_prev_empty and has_next_empty:
                is_after_header_or_list = False
                j = i - 1
                while j >= 0:
                    prev_line = lines[j].strip()
                    if prev_line:
                        if prev_line.startswith('#'):
                            is_after_header_or_list = True
                        elif (prev_line.startswith(('- ', '* ', '+ ')) or
                              re.match(r'^\d+\.\s', prev_line)):
                            is_after_header_or_list = True
                        break
                    j -= 1

                if not is_after_header_or_list and not PN_LINE_RE.match(line):
                    preview = line[:50] + ('...' if len(line) > 50 else '')
                    self._add('AUX', i + 1, preview,
                              "前后有空行的独立段落缺少 PN 编号（shiji 继承辅助项）")
            i += 1


# --------------------------------------------------------------- 报告输出 ----
def print_report(file_name, issues):
    """按 E 系列顺序打印单文件检查报告，返回问题数"""
    total = sum(len(v) for v in issues.values())
    if total == 0:
        return 0

    print(f"\n{'=' * 80}")
    print(f"【{file_name}】发现 {total} 个问题")
    print('=' * 80)

    for code in E_ORDER:
        items = issues.get(code)
        if not items:
            continue
        level, title = E_META[code]
        print(f"\n▸ {title} ({len(items)}处, {level})")
        print('-' * 80)
        for err in items:
            where = f"行 {err['line']}" if err.get('line') else err.get('book', '')
            if err.get('content'):
                print(f"  {where}: {err['content']}")
            else:
                print(f"  {where}:")
            print(f"    → {err['reason']}")
        print()
    return total


def check_book_numbering(book, files):
    """E7：每书回号连续（r001…rNNN 无缺号；文件系统唯一性天然保证无重号）"""
    issues = []
    nums = set()
    odd = []
    for f in files:
        m = TAGGED_FILE_RE.match(f.name)
        if m:
            nums.add(int(m.group(1)))
        else:
            odd.append(f.name)
    if odd:
        issues.append({'book': book, 'content': ', '.join(odd),
                       'reason': "文件名不符合 NNN.tagged.md 约定（回号 1-3 位数字）"})
    if nums:
        lo, hi = min(nums), max(nums)
        missing = [n for n in range(lo, hi + 1) if n not in nums]
        if missing:
            issues.append({'book': book,
                           'content': f"缺号：{[f'{n:03d}' for n in missing]}",
                           'reason': f"回号应连续 {book} r{lo:03d}…r{hi:03d}"
                                     f"（02ab §2.6 每书独立回号）"})
    return issues


def main():
    ap = argparse.ArgumentParser(
        description="Purple Numbers + 章回结构完整性检查（E1-E17，02ab §9.1）")
    ap.add_argument('chapter', nargs='?', default=None,
                    help="单回编号（如 001；配合 --book 消歧，缺省扫全部）")
    ap.add_argument('--book', default=None,
                    help="只查指定书（config.DIR_TAGGED/<书名>/）")
    ap.add_argument('--verbose', '-v', action='store_true',
                    help="显示通过文件")
    args = ap.parse_args()

    if not config.DIR_TAGGED.exists():
        print(f"标注目录不存在：{config.DIR_TAGGED}")
        return 1

    if args.book:
        book_dirs = [config.DIR_TAGGED / args.book]
        if not book_dirs[0].is_dir():
            print(f"未找到书目录：{book_dirs[0]}")
            return 1
    else:
        book_dirs = sorted(p for p in config.DIR_TAGGED.iterdir() if p.is_dir())

    books = {}
    for d in book_dirs:
        files = sorted(list(d.glob('*.struct.md')) + list(d.glob('*.tagged.md')))  # 结构层+标注层双层兼容
        if args.chapter:
            files = [f for f in files
                     if f.name == f"{args.chapter.zfill(3)}.tagged.md"]
        if files:
            books[d.name] = files

    if not books:
        print("未找到匹配的 .tagged.md 文件。")
        return 1

    print("=" * 80)
    print("Purple Numbers + 章回结构检查（02ab §9.1 E1-E17）")
    print("=" * 80)
    print(f"检查书数: {len(books)} · 回文件数: {sum(len(v) for v in books.values())}")
    print()

    linter = PurpleNumberLinter(args.verbose)
    total_issues = 0
    total_errors = 0
    files_with_issues = []
    counts = defaultdict(int)   # E 系列触发数（通过项计 0，输出中编号可见）

    for book, files in books.items():
        # E7 书级检查（增量语境自动降级：已结构化 < 全书回数 → 缺号属预期）
        expected = config.books().get(book, {}).get('chapters')
        partial = bool(expected) and len(files) < expected
        e7_warnings = 0
        for issue in check_book_numbering(book, files):
            counts['E7'] += 1
            total_issues += 1
            if partial and '缺号' in issue.get('content', ''):
                e7_warnings += 1
                print("\n▸ [E7 回号连续] （书级 · warning：增量生成中）")
                print('-' * 80)
                print(f"  {issue['book']}: {issue['content']}")
                print(f"    → 已结构化 {len(files)}/{expected} 回，缺号属增量预期；全书完成后复跑恢复 error 级")
                print()
            else:
                total_errors += 1
                print(f"\n▸ [{E_META['E7'][1]}] （书级）")
                print('-' * 80)
                print(f"  {issue['book']}: {issue['content']}")
                print(f"    → {issue['reason']}")
                print()
            print()

        for file_path in files:
            issues = linter.check_file(file_path, book=book,
                                       chapter=file_path.stem)
            issue_count = sum(len(v) for v in issues.values())
            for code, items in issues.items():
                counts[code] += len(items)
            if issue_count == 0:
                if args.verbose:
                    print(f"✓ {book}/{file_path.name}: 检查通过")
                continue
            file_errors = sum(len(issues.get(c, [])) for c in E_ORDER
                              if E_META[c][0] == 'error')
            total_issues += issue_count
            total_errors += file_errors
            files_with_issues.append((f"{book}/{file_path.name}", issue_count))
            print_report(f"{book}/{file_path.name}", issues)

    # E 系列小结（触发数可见，通过项计 0）
    print("\n" + "=" * 80)
    print("检查项小结（E1-E17 + AUX，冒号后为触发数）")
    print("=" * 80)
    print(' · '.join(f"{E_META[c][1].split()[0]}:{counts.get(c, 0)}"
                     for c in E_ORDER))
    print()

    print("汇总")
    print("=" * 80)
    print(f"问题总数: {total_issues}（其中 error 级 {total_errors}，"
          f"warning 级 {total_issues - total_errors}）")
    print()

    if total_errors:
        print("有 error 的文件:")
        for name, count in files_with_issues:
            print(f"  - {name}: {count} 个问题")
        print()
        print("修复建议：")
        print("  1. E1/E2/E3/E5: 手动改为 [N]/[N.M] 两级连续编号（02ab §3）")
        print("  2. E4: 移除 ##/### 标题中的编号（fix_heading_numbers.py）")
        print("  3. E6: 回目行统一为 `# [0] 第N回　对句`（02ab §2.2）")
        print("  4. E7: 回文件缺号/命名不规范，回号三位零补（02ab §2.6）")
        print("  5. E8-E10/E13/E16: 围栏成对、一栏一 PN、章首 词/诗、栏内全角标点")
        print("  6. E9 观察类: 登记 registry/observe_fences.json 后复检")
        print()
        return 1
    if total_issues:
        print("（仅 warning：按 02ab §8.1 容缺处置并记录即可，不阻断）")
        return 0
    print("✓ 所有文件的检查通过！")
    return 0


if __name__ == '__main__':
    sys.exit(main())
