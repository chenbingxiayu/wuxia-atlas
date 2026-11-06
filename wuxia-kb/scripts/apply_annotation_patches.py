#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/apply_annotation_patches.py（2026-11-03）；改动：
#   1. 路径改经 config：章节文件按 TSV「章节」字段（=文件 stem，如 001）在
#      config.DIR_TAGGED 下解析；多书时章节字段可写「书名/001」消歧（02ab §2.6）；
#      补丁目录缺省 config.DIR_REGISTRY/patches；
#   2. 类型→符号映射按 symbols.ENTITIES 15 类重订（shiji 18 类中未启用码位
#      天文/神话/礼仪/刑法/思想 删除；制度/思想 → 专门概念 ^）；
#   3. 已标注检测改用 symbols.TOKEN_RE（统一符号正则，不再内联字符类）；
#   4. TSV 约定照搬：章节/全名/省称·词/位置/框架类型/匹配模式/上下文[+类型]，
#      上下文优先定位、同词多现全插、已标注不重复、插后自校验；
#   5. 写安全硬化（2026-11-05 review 修复）：默认 dry-run、--apply 才写盘（与
#      C16/C17/C18 家族纪律对齐）；写前备份到 logs/backup/annotation_patches_<时间戳>/；
#      写前剥标断言（strip 前后一致才落盘）；TSV pos 列生效——pos 处精确命中且
#      未标注时只插该处（否则回退同词多现全插并告警）；写盘固定 newline="\n"。

import argparse
import io
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols

PATCH_DIR = config.DIR_REGISTRY / "patches"

# 中文类型名 → symbols 15 类实体码（v0.3-draft）
TYPE_NAME_TO_CODE = {
    '人名': '@', '人物': '@',
    '群组': '◎', '人物群组': '◎',
    '地名': '=', '地点': '=',
    '组织': '◆', '门派': '◆', '邦国': '◆',
    '家族': '&', '家族世系': '&', '世家': '&',
    '族群': '~',
    '职衔': ';', '官职': ';',
    '身份': '#',
    '武功': '☆', '武功技艺': '☆', '技艺': '☆', '招式': '☆',
    '器物': '•', '神兵': '•',
    '生物': '+',
    '作品': '{', '典籍': '{', '作品文书': '{',
    '概念': '^', '专门概念': '^', '制度': '^', '思想': '^',
    '时间': '%',
    '数量': '$',
}
# 省称建议 TSV 中，实体类型固定为人名
ABBREV_TSV_ENTITY_TYPE = '人名'


def type_to_symbol(entity_type: str):
    """类型名 → (开启串, 闭合串)；未知类型返回 None。"""
    code = TYPE_NAME_TO_CODE.get(entity_type)
    if code is None or code not in symbols.ENTITY_CODES:
        return None
    return (symbols.BRACKETS['entity'][0] + code,
            symbols.BRACKETS['entity'][1])


def load_tsv(tsv_path: Path) -> list[dict]:
    """加载建议 TSV，返回 patch 列表。"""
    patches = []
    lines = tsv_path.read_text(encoding='utf-8').splitlines()
    if not lines:
        return patches
    header = lines[0].split('\t')
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) < 7:
            continue
        # 通用字段：章节 全名 省称/词 位置 框架类型 匹配模式 上下文
        patches.append({
            'chapter': parts[0],
            'full_name': parts[1],
            'word': parts[2],       # 省称 或 别名词
            'pos': int(parts[3]) if parts[3].isdigit() else 0,
            'frame_type': parts[4],
            'pattern': parts[5],
            'context': parts[6].replace('↵', '\n') if len(parts) > 6 else '',
            'entity_type': parts[7] if len(parts) > 7 else ABBREV_TSV_ENTITY_TYPE,
        })
    return patches


def resolve_chapter_file(chapter_field: str):
    """章节字段（=文件 stem，如 001；多书时可写「书名/001」）→ 文件路径。

    多书歧义时不猜（补丁必须显式），返回 None 并告警。"""
    field = chapter_field.replace('\\', '/')
    if '/' in field:
        book, stem = field.split('/', 1)
        candidates = [config.DIR_TAGGED / book / f"{stem}.tagged.md"]
    else:
        candidates = sorted(config.DIR_TAGGED.glob(f"*/{field}.tagged.md"))
    candidates = [p for p in candidates if p.exists()]
    if not candidates:
        return None
    if len(candidates) > 1:
        print(f"  [WARN] 章节 {chapter_field} 命中多部书，请把章节字段写为"
              f"「书名/{field}」消歧：")
        for p in candidates:
            print(f"         {p.relative_to(config.ROOT)}")
        return None
    return candidates[0]


def is_already_tagged(text: str, start: int, word: str) -> bool:
    """检查 text[start:start+len(word)] 是否已被任意标注令牌包裹。"""
    for m in symbols.TOKEN_RE.finditer(text):
        if m.start() <= start < m.end():
            return True
    return False


def apply_patch_to_text(text: str, word: str, entity_type: str,
                        context_hint: str = '', dry_run: bool = False,
                        pos: int = 0) -> tuple:
    """
    在 text 中找到所有未标注的 word，插入标注符号。
    优先使用 TSV pos 精确定位（命中且未标注时只插该处），其次 context_hint，
    最后同词多现全插。
    返回 (new_text, count)。
    """
    sym = type_to_symbol(entity_type)
    if sym is None:
        return text, -1  # 未知类型（调用方告警跳过）
    open_sym, close_sym = sym
    tagged_word = open_sym + word + close_sym

    count = 0

    # 构建"已标注位置"集合，避免重复标注（统一走 symbols.TOKEN_RE）
    tagged_ranges = set()
    for m in symbols.TOKEN_RE.finditer(text):
        for i in range(m.start(), m.end()):
            tagged_ranges.add(i)

    # TSV pos 精确定位优先（2026-11-05）：pos 列命中且未标注 → 只插该处
    if pos > 0 and text[pos:pos + len(word)] == word \
            and not any(i in tagged_ranges for i in range(pos, pos + len(word))):
        positions = [pos]
    else:
        if pos > 0:
            print(f'    [WARN] pos={pos} 与「{word}」不匹配或已标注，回退同词多现全插')
        # 查找所有未标注的 word 出现位置
        search_start = 0
        positions = []
        while True:
            idx = text.find(word, search_start)
            if idx == -1:
                break
            # 确认这些位置不在已标注区域内
            if not any(i in tagged_ranges for i in range(idx, idx + len(word))):
                positions.append(idx)
            search_start = idx + 1

    if not positions:
        return text, 0

    # 如果有上下文提示，优先找最接近 context_hint 的位置
    if context_hint and len(positions) > 1:
        # 在文本中找 context_hint 出现的位置，取最近的 word 位置
        ctx_clean = re.sub(r'[\n\r]', '', context_hint)[:20]
        ctx_pos = text.find(ctx_clean)
        if ctx_pos >= 0:
            positions.sort(key=lambda p: abs(p - ctx_pos))

    if dry_run:
        for p in positions:
            ctx_s = max(0, p - 8)
            ctx_e = min(len(text), p + len(word) + 8)
            ctx = text[ctx_s:ctx_e].replace('\n', '↵')
            print(f'    [DRY-RUN] 将在位置 {p} 插入 {tagged_word}  ctx=「{ctx}」')
        return text, len(positions)

    # 从后往前替换，避免位置偏移问题
    positions_rev = sorted(positions, reverse=True)
    text_list = list(text)
    for p in positions_rev:
        text_list[p:p + len(word)] = list(open_sym + word + close_sym)
        count += 1

    return ''.join(text_list), count


def apply_tsv_to_chapter(tsv_path: Path, dry_run: bool = False) -> dict:
    """
    将一个 TSV 文件中的所有建议应用到对应的 .tagged.md 文件。
    返回统计信息。
    """
    patches = load_tsv(tsv_path)
    if not patches:
        return {'tsv': tsv_path.name, 'patches': 0, 'applied': 0}

    # 按章节分组
    by_chapter: dict[str, list] = {}
    for p in patches:
        by_chapter.setdefault(p['chapter'], []).append(p)

    total_applied = 0
    for chapter, chapter_patches in by_chapter.items():
        fpath = resolve_chapter_file(chapter)
        if fpath is None:
            print(f'  [WARN] 章节文件不存在或多书歧义：{chapter}')
            continue

        text = fpath.read_text(encoding='utf-8')
        original_text = text
        chapter_count = 0

        # 按词分组，避免同一词多次处理
        words_seen = set()
        for patch in chapter_patches:
            word = patch['word']
            entity_type = patch.get('entity_type', ABBREV_TSV_ENTITY_TYPE)
            context_hint = patch.get('context', '')

            if word in words_seen:
                continue
            words_seen.add(word)

            new_text, cnt = apply_patch_to_text(
                text, word, entity_type, context_hint, dry_run=dry_run,
                pos=patch.get('pos', 0)
            )
            if cnt < 0:
                print(f'    [WARN] 未知实体类型「{entity_type}」'
                      f'（不在 symbols 15 类），跳过「{word}」')
                continue
            if cnt > 0:
                text = new_text
                chapter_count += cnt
                if not dry_run:
                    print(f'    ✓ {chapter}: {word} 插入 {cnt} 处')

        if not dry_run and text != original_text:
            # 剥标断言：插标只增令牌，剥标后正文必须与原文逐字一致（04f1 V0 红线）
            assert symbols.strip_markup(text) == symbols.strip_markup(original_text), \
                f'{fpath.name} 剥标不一致，拒写'
            backup_dir = config.DIR_LOGS / 'backup' / \
                f'annotation_patches_{datetime.now():%Y%m%d_%H%M%S}'
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fpath, backup_dir / fpath.name)
            io.open(fpath, 'w', encoding='utf-8', newline='\n').write(text)
            total_applied += chapter_count

    return {'tsv': tsv_path.name, 'patches': len(patches), 'applied': total_applied}


def main():
    parser = argparse.ArgumentParser(description='标注补丁应用工具')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', help='应用单个 TSV 文件')
    group.add_argument('--dir', nargs='?', const='book',
                       help='批量应用目录下的 TSV 文件；不带值=registry/patches/<book>/（配 --book）')
    parser.add_argument('--book', default=config.PILOT_BOOK,
                        help=f'书名（--dir 缺省目录解析用，默认 {config.PILOT_BOOK}）')
    parser.add_argument('--pattern', default='',
                        help='与 --dir 配合，只处理文件名含此字符串的 TSV')
    parser.add_argument('--apply', action='store_true',
                        help='实际写入 tagged（默认 dry-run；写前备份+剥标断言）')
    parser.add_argument('--dry-run', action='store_true',
                        help='只显示将要做的修改，不实际写入（缺省即 dry-run，保留兼容）')
    args = parser.parse_args()

    if not args.apply:
        print('[DRY-RUN 模式，不写入任何文件（确认后加 --apply）]')

    if args.file:
        tsv_path = Path(args.file)
        if not tsv_path.exists():
            print(f'[ERROR] 文件不存在：{tsv_path}')
            sys.exit(1)
        result = apply_tsv_to_chapter(tsv_path, dry_run=not args.apply)
        print(f'\n{result["tsv"]}: {result["patches"]} 条建议, '
              f'{"将插入" if not args.apply else "实际插入"} {result["applied"]} 处')

    elif args.dir:
        patch_dir = Path(args.dir) if args.dir != "book" else config.patches_dir(args.book)
        tsv_files = sorted(patch_dir.glob('*.tsv'))
        if args.pattern:
            tsv_files = [f for f in tsv_files if args.pattern in f.name]
        if not tsv_files:
            print(f'[WARN] 未找到匹配的 TSV 文件')
            sys.exit(0)

        print(f'找到 {len(tsv_files)} 个 TSV 文件...')
        total = 0
        for tsv in tsv_files:
            result = apply_tsv_to_chapter(tsv, dry_run=not args.apply)
            if result['applied'] > 0 or not args.apply:
                print(f'  {result["tsv"]}: 插入 {result["applied"]} 处')
            total += result['applied']
        print(f'\n✅ 合计插入 {total} 处标注')


if __name__ == '__main__':
    main()
