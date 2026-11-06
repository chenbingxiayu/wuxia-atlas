# -*- coding: utf-8 -*-
"""C0c · 共享掩码/最长匹配模块 —— 词表驱动的候选召回与文本掩码。

统一 docs/05 §1.2-5 的"词表三派"（外置 JSON / 内联 set / 内联 dict）：tag_* 脚本
一律经本模块消费 wordlists/*.json，词表是数据不是代码。

用法：
    from masker import load_wordlist, find_candidates, mask_text
    m = load_wordlist(config.DIR_WORDLISTS / "verbs.json")     # 或 build_matcher([...])
    hits = find_candidates("他一招怪蟒翻身点倒对手", m)          # [(词, 起, 止)]
    masked = mask_text(text, m)                                 # 命中段替换为等长占位

设计：
  - 最长优先、不重叠：同起点取最长命中；命中后跳到命中末端。
  - max_len 剪枝：匹配尝试不超过词表最长词长。
  - 占位符默认 "\\uFFFD"×len（等长，保句长统计与剥标对账的长度不变性）。
"""
from pathlib import Path
import json

_PLACEHOLDER = "\uFFFD"


def build_matcher(words):
    """words: iterable[str] → matcher dict {index: {首字: [词...]按长度降序}, max_len}"""
    index = {}
    max_len = 0
    seen = set()
    for w in words:
        w = w.strip()
        if not w:
            continue
        # 词族模板（含 [备选] 槽位）此处按字面收录，模板展开属词表编译器职责
        if w in seen:
            continue
        seen.add(w)
        max_len = max(max_len, len(w))
        index.setdefault(w[0], []).append(w)
    for first in index:
        index[first].sort(key=len, reverse=True)
    return {"index": index, "max_len": max_len, "count": len(seen)}


def load_wordlist(path: Path, field: str = "surface"):
    """从词表 JSON（D09 schema：{items:[...]}）构建 matcher。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("items", [])
    return build_matcher(it[field] for it in items)


def find_candidates(text: str, matcher, overlap_free: bool = True):
    """返回 [(命中词, 起始, 结束)]（结束为排他索引）。

    overlap_free=True 时同一位置只留最长命中并跳过命中段；
    False 时返回所有起点上的最长命中（位置可重叠，供统计核dup用）。
    """
    index, max_len = matcher["index"], matcher["max_len"]
    out = []
    i, n = 0, len(text)
    while i < n:
        hit = None
        if text[i] in index:
            for w in index[text[i]]:
                if i + len(w) <= n and text[i:i + len(w)] == w:
                    hit = w
                    break  # 已按长度降序，首个即最长
        if hit:
            out.append((hit, i, i + len(hit)))
            i += len(hit) if overlap_free else 1
        else:
            i += 1
    return out


def mask_text(text: str, matcher, placeholder: str = _PLACEHOLDER):
    """命中段替换为等长占位串（长度不变，供句长统计/韵文检测排除专名）。"""
    hits = find_candidates(text, matcher)
    chars = list(text)
    for _, a, b in hits:
        for j in range(a, b):
            chars[j] = placeholder
    return "".join(chars)


def merge_words(*word_lists):
    """多词表合并去重（如 实体词表+泛称黑名单 一起掩码）。"""
    seen, out = set(), []
    for ws in word_lists:
        for w in ws:
            w = w.strip()
            if w and w not in seen:
                seen.add(w)
                out.append(w)
    return out
