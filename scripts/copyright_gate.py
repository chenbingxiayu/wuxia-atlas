# -*- coding: utf-8 -*-
"""版权闸门：发布产物（dist/）L0/L1 合规校验。

规则（版权分层见 kb/README 与《网站完整设计方案》§六）：
  1) 任何语料整行（章回版正文行，长度 ≥20 字）不得出现在 dist 文本中；
     白名单：回目行（"第N回…"，短句元数据，随回目页发布）。
  2) dist 中不得出现语料目录引用（章回版/、tagged/、reader/）。
  3) 只扫描文本类扩展名（.html/.css/.js/.svg/.txt/.xml/.json/.webmanifest）。

实现：语料行前 12 字建索引 → dist 文本滑窗查命中 → 命中后全文复核。
用法：python scripts/copyright_gate.py site/dist
"""
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
ZH = ROOT / '章回版'
TEXT_EXT = {'.html', '.css', '.js', '.svg', '.txt', '.xml', '.json', '.webmanifest'}
K = 12                     # 索引 n-gram 长度
MIN_LINE = 20              # 语料行纳入检测的最小长度
TITLE_RE = re.compile(r'^(?:第[〇○零一二三四五六七八九十百千两0-9]+回|楔子)')


def corpus_lines() -> 'tuple[dict[str, str], set[str]]':
    """(前12字 -> 整行) 索引；白名单行集合"""
    index: dict[str, str] = {}
    whitelist: set[str] = set()
    n = 0
    for fp in ZH.rglob('*.txt'):
        with open(fp, encoding='utf-8-sig') as f:
            for raw in f:
                line = raw.strip()
                if len(line) < MIN_LINE:
                    continue
                n += 1
                if TITLE_RE.match(line):
                    whitelist.add(line)
                    continue
                index.setdefault(line[:K], line)
    return index, whitelist, n


def dist_text(dist: Path) -> 'tuple[str, list[str]]':
    texts = []
    names = []
    for fp in sorted(dist.rglob('*')):
        if not fp.is_file() or fp.suffix.lower() not in TEXT_EXT:
            continue
        try:
            texts.append(fp.read_text(encoding='utf-8', errors='ignore'))
            names.append(str(fp.relative_to(dist)))
        except OSError:
            pass
    return '\n'.join(texts), names


def main() -> int:
    if len(sys.argv) < 2:
        print('usage: python scripts/copyright_gate.py <dist_dir>')
        return 2
    arg = Path(sys.argv[1])
    dist = arg if arg.is_absolute() else Path.cwd() / arg
    index, whitelist, n_corpus = corpus_lines()
    text, names = dist_text(dist)
    print(f'语料行扫描 {n_corpus} 行（≥{MIN_LINE} 字，回目行白名单 {len(whitelist)}），'
          f'产物文本 {len(text) // 1024} KB / {len(names)} 文件')

    violations = []
    hits_whitelisted = 0
    for i in range(len(text) - K + 1):
        window = text[i:i + K]
        line = index.get(window)
        if line is None:
            continue
        if line in whitelist:
            hits_whitelisted += 1
            continue
        if line in text:                    # 语料整行出现在产物中 → 违规
            violations.append((line[:38], text[max(0, i - 20):i + 30]))
            if len(violations) >= 10:
                break

    # 规则 2：语料目录引用
    for bad in ('章回版/', 'tagged/', 'reader/'):
        if bad in text:
            violations.append((f'路径引用: {bad}', '（dist 文本）'))

    # 规则 3：内部链接必须带 base 前缀（项目子路径部署，href="/x" 会 404）
    import re as _re
    base_seg = (sys.argv[2].strip('/') if len(sys.argv) > 2 else '')
    skip = f'href="/{base_seg}' if base_seg else None
    for m in _re.finditer(r'href="/(?!/)([^"]{0,40})"', text):
        if skip and m.group(0).startswith(skip):
            continue
        violations.append((f'内部链接缺 base 前缀: href="/{m.group(1)}"', '（dist HTML）'))
        if len(violations) >= 10:
            break

    if violations:
        print(f'\n✗ 版权闸门未通过：{len(violations)} 处违规（最多显示 10 条）')
        for v, ctx in violations:
            print(f'  - 语料行「{v}…」 上下文:「…{ctx}…」')
        return 1
    print(f'✓ 版权闸门通过：白名单（回目）命中 {hits_whitelisted} 处，无语料整行泄漏')
    return 0


if __name__ == '__main__':
    sys.exit(main())
