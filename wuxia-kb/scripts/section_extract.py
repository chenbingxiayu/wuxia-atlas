#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 移植自 shiji-kb/scripts/section_extract.py（2026-11-03）；改动：
#   1. 文件头注明：## 场景小节为可选层（02ab §7.1 裁决，默认不生成），
#      本工具服务可选层回补（§7.2 预留规范：标题不含编号、不含实体符号，
#      anchor 取该节第一个 PN；回补不占 PN 号、不移动既有锚点）；
#   2. 路径改经 config：扫 config.DIR_TAGGED/<书>/NNN.tagged.md，
#      输出 config.DIR_REGISTRY/sections_data.json；
#   3. 标注剥离统一改用 symbols.TOKEN_RE（保留管道后规范名的原语义由
#      _token_to_canonical 承接，删除内联符号正则）；
#   4. 提取逻辑不变：`## 标题` → sections 清单 + 站点锚点/链接生成函数保留
#      （站点层未建，链接函数仅供回补时参考）。

import io
import json
import re
import sys
import urllib.parse
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except AttributeError:
    pass

import config
import symbols

OUTPUT_FILE = config.DIR_REGISTRY / "sections_data.json"


def _token_to_canonical(m) -> str:
    """TOKEN_RE 替换：有管道取规范名（原标题锚点语义），无管道取显示名。"""
    body = m.group("ent") if m.group("ent") is not None else (
        m.group("verb") if m.group("verb") is not None else m.group("rhet"))
    rest = body[1:]
    if symbols.PIPE in rest:
        display, note = rest.split(symbols.PIPE, 1)
        return note or display
    return rest


def extract_sections_from_chapter(md_file):
    """从markdown文件中提取主要段落（二级标题）"""
    sections = []

    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 匹配二级标题：## 标题
        pattern = r'^## (.+)$'

        for line in content.split('\n'):
            match = re.match(pattern, line.strip())
            if match:
                title = match.group(1).strip()
                sections.append({
                    'title': title
                })

    except Exception as e:
        print(f"Error processing {md_file}: {e}")

    return sections


def process_all_chapters():
    """处理全部书的全部已标注回（config.DIR_TAGGED 递归扫描）"""

    result = {}

    # 获取所有tagged.md文件
    md_files = sorted(config.DIR_TAGGED.rglob('*.tagged.md'))

    print(f"Found {len(md_files)} tagged markdown files")

    for md_file in md_files:
        chapter_name = md_file.stem.replace('.tagged', '')
        sections = extract_sections_from_chapter(md_file)

        if sections:
            result[chapter_name] = sections
            print(f"{chapter_name}: {len(sections)} sections")

    return result


def generate_heading_id(text):
    """从标题文本生成URL安全的锚点ID（与站点渲染层保持一致）"""
    # 移除〖T 内容|规范名〗/⟦…⟧/〘…〙标注，保留规范名（消歧格式）
    clean_text = symbols.TOKEN_RE.sub(_token_to_canonical, text)
    # 移除HTML标签
    clean_text = re.sub(r'<[^>]+>', '', clean_text)
    # URL编码（中文会被编码）
    return urllib.parse.quote(clean_text.strip())


def clean_entity_markers(text):
    """移除文本中的实体标注符号，用于显示（保留管道前显示名）"""
    return symbols.strip_markup(text).strip()


def generate_section_links_html(chapter_name, sections, max_display=10):
    """为一个章节生成小节链接的HTML"""

    if not sections:
        return ""

    # 限制显示的小节数量
    display_sections = sections[:max_display]
    has_more = len(sections) > max_display

    links = []
    for i, section in enumerate(display_sections):
        title = section["title"]
        # 生成与HTML文件中相同的锚点ID
        heading_id = generate_heading_id(title)
        # 清理显示文本中的实体标注
        display_title = clean_entity_markers(title)
        link = f'<a href="chapters/{chapter_name}.html#{heading_id}">{display_title}</a>'
        links.append(link)

    if has_more:
        links.append(f'<span class="more-sections">... 共{len(sections)}节</span>')

    html = '<div class="section-links">' + ' · '.join(links) + '</div>'
    return html


def save_sections_data(data, output_file=OUTPUT_FILE):
    """保存提取的段落数据"""
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved sections data to {output_file}")


if __name__ == '__main__':
    print("Extracting sections from all chapters...")
    print("=" * 60)

    # 提取所有章节的段落信息
    sections_data = process_all_chapters()

    print("=" * 60)
    print(f"\nTotal chapters processed: {len(sections_data)}")

    # 保存数据
    save_sections_data(sections_data)

    # 显示示例（取回目第一册有输出者）
    print("\n" + "=" * 60)
    if sections_data:
        sample_name = sorted(sections_data)[0]
        print(f"Sample HTML output for {sample_name}:")
        print("=" * 60)
        print(generate_section_links_html(
            sample_name, sections_data[sample_name]))

    print("\nDone!")
