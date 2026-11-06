# -*- coding: utf-8 -*-
"""Apply adjudication decisions for 《江湖三女侠》 judgment items (task-6 / G3a).

用法：
    python -X utf8 scripts/_oneshot/apply_judgment_a.py --dry-run
    python -X utf8 scripts/_oneshot/apply_judgment_a.py --apply

输入：logs/qa/judgment_decisions_a.json（由 fix-judg-a 产出，schema 见 task-6）
行为：
  - 按 (chapter, pn) 定位 tagged/江湖三女侠/NNN.tagged.md 的 [pn] 段落；
  - 段内按「同显示串第 occ 处」定位令牌（entity/verb 均计入 occ；命中非动词层则报错跳过）；
  - remove：摘除括号与类型码、保留显示串（带管道时保留管道前的显示串）；
  - recode：只改括号内首字符类型码；
  - keep：不动作；
  - 每段改完断言 symbols.strip_markup(new) == symbols.strip_markup(old)；
  - --apply 前把将改写的整文件备份到 logs/backup/judgment_a/；
  - 找不到/数量不符/层不符 → 该条记失败并跳过（不崩溃、不误改）。

本脚本只在 __main__ 中执行；不修改 tagged/ 之外的其他脚本。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, OrderedDict
from pathlib import Path

# scripts/ 目录（提供 symbols.py）；不得依赖 cwd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import symbols  # noqa: E402  (scripts/symbols.py)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DECISIONS = REPO_ROOT / 'logs' / 'qa' / 'judgment_decisions_a.json'
TAGGED_DIR = REPO_ROOT / 'tagged' / '江湖三女侠'
BACKUP_DIR = REPO_ROOT / 'logs' / 'backup' / 'judgment_a'
BOOK = '江湖三女侠'

# 令牌：〖类型码+显示串(+|元数据)〗 或 ⟦类型码+显示串(+|元数据)⟧
TOKEN_RE = re.compile(r'[〖⟦]([^〖〗⟦⟧]+)[〗⟧]')
VERB_OPEN = '⟦'
VERB_CLOSE = '⟧'


def load_decisions(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding='utf-8'))
    decisions = data.get('decisions')
    if not isinstance(decisions, list):
        raise SystemExit(f'decisions 字段缺失或不是数组: {path}')
    return decisions


def load_paragraphs(chapter: int) -> tuple[Path, list[str]]:
    path = TAGGED_DIR / f'{chapter:03d}.tagged.md'
    if not path.exists():
        raise FileNotFoundError(f'找不到 tagged 文件: {path}')
    lines = path.read_text(encoding='utf-8').split('\n')
    return path, lines


def find_paragraph_line(lines: list[str], pn: int) -> int | None:
    prefix = f'[{pn}]'
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            return i
    return None


def locate_tokens(para: str, display: str) -> list[dict]:
    """返回段内所有同显示串令牌（含 entity/verb，按出现顺序）。"""
    out = []
    for m in TOKEN_RE.finditer(para):
        content = m.group(1)
        if not content:
            continue
        code = content[0]
        rest = content[1:]
        disp = rest.split('|')[0]
        if disp == display:
            out.append({
                'start': m.start(),
                'end': m.end(),
                'code': code,
                'inner': content,
                'display': disp,
                'raw': m.group(0),
                'is_verb': m.group(0).startswith(VERB_OPEN) and m.group(0).endswith(VERB_CLOSE),
            })
    return out


def transform(token: dict, action: str, new_code: str | None, display: str) -> tuple[str, str]:
    """返回 (新文本, 说明)。"""
    raw = token['raw']
    inner = token['inner']
    if action == 'remove':
        # 摘除括号与类型码；带管道保留管道前显示串
        body = inner[1:]
        new = body.split('|')[0]
        if not new:
            new = display
        return new, f'{raw} -> {new}'
    if action == 'recode':
        assert new_code and len(new_code) == 1, f'recode 需要单字符 new_code: {new_code!r}'
        new = raw[0] + new_code + inner[1:] + raw[-1]
        return new, f'{raw} -> {new}'
    raise ValueError(f'未知 action: {action}')


def build_jobs(decisions: list[dict]) -> tuple[list[dict], list[dict]]:
    """按 (chapter,pn,display,occ) 去重合并，返回 (jobs, duplicate_notes)。"""
    grouped: "OrderedDict[tuple, list[dict]]" = OrderedDict()
    for d in decisions:
        key = (d['chapter'], d['pn'], d['display'], d['occ'])
        grouped.setdefault(key, []).append(d)

    jobs, notes = [], []
    for key, ds in grouped.items():
        actions = {d['action'] for d in ds}
        if len(actions) > 1:
            notes.append({'key': key, 'status': 'conflict',
                          'detail': f'同一令牌存在冲突裁决 {sorted(actions)}，跳过'})
            continue
        action = ds[0]['action']
        new_codes = {d.get('new_code') for d in ds if d['action'] == 'recode'}
        new_code = next(iter(new_codes)) if new_codes else None
        chapter, pn, display, occ = key
        jobs.append({
            'chapter': chapter, 'pn': pn, 'display': display, 'occ': occ,
            'action': action, 'new_code': new_code,
            'n_entries': len(ds),
            'types': sorted({d['type'] for d in ds}),
        })
        if len(ds) > 1:
            notes.append({'key': key, 'status': 'merged',
                          'detail': f'{len(ds)} 条裁决指向同一令牌，合并处理'})
    return jobs, notes


def run(decisions: list[dict], apply: bool) -> int:
    jobs, notes = build_jobs(decisions)
    keep_count = sum(1 for j in jobs if j['action'] == 'keep')

    # 按文件分组
    by_chapter: "OrderedDict[int, list[dict]]" = OrderedDict()
    for j in jobs:
        by_chapter.setdefault(j['chapter'], []).append(j)

    failures: list[dict] = []
    already: list[dict] = []
    applied = Counter()
    previews: list[dict] = []
    files_changed: list[Path] = []
    backup_paths: list[Path] = []

    for chapter, chapter_jobs in by_chapter.items():
        try:
            path, lines = load_paragraphs(chapter)
        except FileNotFoundError as exc:
            for j in chapter_jobs:
                failures.append({'job': j, 'reason': str(exc)})
            continue

        # 按段落分组
        by_pn: "OrderedDict[int, list[dict]]" = OrderedDict()
        for j in chapter_jobs:
            by_pn.setdefault(j['pn'], []).append(j)

        file_dirty = False
        for pn, pn_jobs in by_pn.items():
            line_idx = find_paragraph_line(lines, pn)
            if line_idx is None:
                for j in pn_jobs:
                    failures.append({'job': j, 'reason': f'第 {chapter} 回找不到段落 [{pn}]'})
                continue
            old_para = lines[line_idx]
            work = old_para
            # 同段内从右向左改，避免偏移变化
            changes = []
            for j in pn_jobs:
                tokens = locate_tokens(work, j['display'])
                if len(tokens) < j['occ']:
                    failures.append({'job': j, 'reason':
                                     f'同显示串令牌数不足：需要第 {j["occ"]} 处，实得 {len(tokens)} 处'})
                    continue
                token = tokens[j['occ'] - 1]
                if not token['is_verb']:
                    failures.append({'job': j, 'reason':
                                     f'第 {j["occ"]} 处同显示串令牌不是动词层令牌（{token["raw"]}），跳过'})
                    continue
                if j['action'] == 'keep':
                    previews.append({'key': f'{chapter}[{pn}]', 'display': j['display'],
                                     'occ': j['occ'], 'action': 'keep', 'old': token['raw'],
                                     'new': token['raw'], 'context': work[max(0, token['start'] - 12):token['end'] + 12]})
                    continue
                try:
                    new_text, _ = transform(token, j['action'], j['new_code'], j['display'])
                except ValueError as exc:
                    failures.append({'job': j, 'reason': str(exc)})
                    continue
                if new_text == token['raw']:
                    # recode 目标域码已等于 new_code：视为已应用，不重复改
                    already.append({'job': j, 'reason': '目标域码已等于 new_code，视为已应用'})
                    continue
                changes.append({
                    'start': token['start'], 'end': token['end'],
                    'old': token['raw'], 'new': new_text, 'action': j['action'],
                    'display': j['display'], 'occ': j['occ'],
                })
            if not changes:
                continue
            # 右→左替换
            new_para = work
            for ch in sorted(changes, key=lambda c: c['start'], reverse=True):
                new_para = new_para[:ch['start']] + ch['new'] + new_para[ch['end']:]
                ctx = work[max(0, ch['start'] - 12):ch['end'] + 12]
                previews.append({'key': f'{chapter}[{pn}]', 'display': ch['display'],
                                 'occ': ch['occ'], 'action': ch['action'],
                                 'old': ch['old'], 'new': ch['new'], 'context': ctx})
            # 剥标断言（保持正文逐字不变）
            if symbols.strip_markup(new_para) != symbols.strip_markup(old_para):
                failures.append({'job': {'chapter': chapter, 'pn': pn},
                                 'reason': '剥标断言失败（新段正文与旧段不一致），该段全部改动回退'})
                continue
            lines[line_idx] = new_para
            file_dirty = True
            for ch in changes:
                applied[ch['action']] += 1

        if file_dirty:
            files_changed.append(path)
            if apply:
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                bak = BACKUP_DIR / f'{BOOK}_{chapter:03d}.tagged.md'
                shutil.copy2(path, bak)
                backup_paths.append(bak)
                path.write_text('\n'.join(lines), encoding='utf-8')

    # ---- 输出 ----
    print(f'[{BOOK}] decisions={len(decisions)} jobs={len(jobs)} '
          f'（token 去重后；keep={keep_count}）')
    for note in notes:
        print(f'  note [{note["status"]}] {note["key"]}: {note["detail"]}')
    mode = 'APPLY' if apply else 'DRY-RUN'
    print(f'== {mode} 逐处 diff ==')
    for p in previews:
        mark = 'KEEP' if p['action'] == 'keep' else p['action'].upper()
        print(f'  {p["key"]} {p["display"]}#{p["occ"]} [{mark}] {p["old"]} -> {p["new"]}')
        print(f'      ctx …{p["context"]}…')
    print('== 统计 ==')
    print(f'  remove={applied.get("remove", 0)} recode={applied.get("recode", 0)} '
          f'keep={keep_count}（keep 不动作）')
    print(f'  修改文件数={len(files_changed)}  失败={len(failures)}  已应用跳过={len(already)}')
    for path in files_changed:
        print(f'    {"[已写盘]" if apply else "[待写盘]"} {path.relative_to(REPO_ROOT)}')
    if apply:
        for bak in backup_paths:
            print(f'    备份 -> {bak.relative_to(REPO_ROOT)}')
    if failures:
        print('== 失败清单 ==')
        for f in failures:
            job = f['job']
            if isinstance(job, dict) and 'display' in job:
                print(f'  {job["chapter"]}[{job["pn"]}] {job["display"]}#{job["occ"]}'
                      f' [{job["action"]}]: {f["reason"]}')
            else:
                print(f'  {job}: {f["reason"]}')
    else:
        print('  失败清单：无（0 定位失败 / 0 断言失败）')
    return 0 if not failures else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='应用《江湖三女侠》judgment 裁决（task-6 / G3a）')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run', action='store_true', help='只打印逐处 diff，不写盘')
    g.add_argument('--apply', action='store_true', help='写盘（写前整文件备份）')
    ap.add_argument('--decisions', type=Path, default=DEFAULT_DECISIONS,
                    help=f'decisions JSON（默认 {DEFAULT_DECISIONS}）')
    args = ap.parse_args(argv)
    decisions = load_decisions(args.decisions)
    return run(decisions, apply=args.apply)


if __name__ == '__main__':
    sys.exit(main())
