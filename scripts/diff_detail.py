# -*- coding: utf-8 -*-
"""定位标注文件与原文的逐字差异"""
import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ENTITY_CODES = "@=◆;%☆•+[§"
VERB_CODES = "◉◈○▲◇"

def strip_tags(text):
    def repl(m):
        token = m.group(0)
        inner = token[1:-1]
        code, surface = inner[0], inner[1:]
        if code == "@" or code in ENTITY_CODES:
            if "|" in surface:
                surface = surface.split("|")[0]
        return surface
    text = re.sub(r'〖[^〖〗]*〗', repl, text)
    text = re.sub(r'⟦[^⟦⟧]*⟧', repl, text)
    return text

def load_lines(path):
    with open(path, encoding='utf-8') as f:
        lines = f.read().splitlines()
    out = []
    skip = False
    for ln in lines:
        s = ln.strip()
        if s == '---':
            skip = not skip if out == [] or skip else skip
            if not out:
                continue
        if out == [] and s == '---':
            continue
        out.append(ln)
    return out

def body_lines(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    # 去 YAML 头
    if raw.startswith('---'):
        end = raw.index('---', 3)
        raw = raw[end+3:]
    lines = raw.splitlines()
    out = []
    for ln in lines:
        if re.match(r'^:::', ln):
            continue
        out.append(ln)
    # 去掉首尾空行
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out

tagged = body_lines(sys.argv[1])
orig_path = sys.argv[2]
with open(orig_path, encoding='utf-8') as f:
    orig = [ln for ln in f.read().splitlines()]
while orig and not orig[0].strip():
    orig.pop(0)
while orig and not orig[-1].strip():
    orig.pop()

if len(tagged) != len(orig):
    print(f'行数不同: tagged={len(tagged)} orig={len(orig)}')

for i, (t, o) in enumerate(zip(tagged, orig)):
    ts = strip_tags(t)
    if ts != o:
        # 找第一个差异点
        n = min(len(ts), len(o))
        pos = None
        for j in range(n):
            if ts[j] != o[j]:
                pos = j
                break
        if pos is None:
            pos = n
        print(f'第{i+1}行 (orig行号) 差异@{pos}:')
        print(f'  tagged: ...{ts[max(0,pos-15):pos]}【{ts[pos:pos+15] if pos < len(ts) else "<EOF>"}】...')
        print(f'  orig  : ...{o[max(0,pos-15):pos]}【{o[pos:pos+15] if pos < len(o) else "<EOF>"}】...')
        for j in range(n):
            if ts[j] != o[j]:
                print(f'  U+码点: tagged={hex(ord(ts[j]))}({ts[j]}) orig={hex(ord(o[j]))}({o[j]})')
                break
        else:
            print(f'  长度不同: tagged={len(ts)} orig={len(o)}')
