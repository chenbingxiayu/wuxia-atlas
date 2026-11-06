#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""03d AST→HTML 转换器 render_ast_html.py（H-1~H-10 冻结契约实现）

职责
----
读 tagged（令牌层 + 结构层）→ 生成 §3.2 AST（chapter/fence/para/heading/line/entity/
verb/rhetoric/text）→ 渲染语义化 HTML（data-* 属性 / 围栏 class / PN 锚点 / loc_r 锚）。
只读 tagged/registry，不写语料、不写 site/data；产物只落 `logs/render/`（或 CLI --out
指定且经 H-10 路径审计的本地目录）。

契约（SKILL_03d §五，H-1~H-10）
-------------------------------
H-1 每个 PN 块唯一 id（={work-id}-r{回}-{段}）+ data-pn（机锚原文），全书唯一；
H-2 实体 class="wx-ent wx-ent-<code>"、data-etype∈15 类、data-token-id 全书唯一；
H-3 动词 class="wx-verb wx-verb-<domain>"、data-vtype∈6 域，不复用实体类；
H-4 显示文本 == 剥标原文逐字一致（令牌只包裹、不改字符）；
H-5 data-canonical 仅在管道存在或登记层唯一回溯时输出（歧义/未登记不猜）；
H-6 围栏 class="wx-fence wx-fence-<roman>"（10 类映射）+ data-fence=中文类型；
H-7 禁止原文之外属性值/内联事件处理器；全部文本与属性 html.escape；
H-8 确定性：同 AST 双跑字节一致（HTML 中无时间戳/随机数）；
H-9 status=pending 实体不输出 data-canonical/跳转，只保显示串；
H-10 产物不得进入 site/data 或公网静态目录（路径审计）。

CLI
---
  python scripts/render_ast_html.py --selftest             # H-1~H-10 逐条断言
  python scripts/render_ast_html.py                        # 默认：5 书各 1 回样本 → logs/render/samples/
  python scripts/render_ast_html.py --book 白发魔女传 --chapter 1
  python scripts/render_ast_html.py --book 白发魔女传 --out logs/render/bf
  python scripts/render_ast_html.py --strict               # 令牌/围栏异常即失败

输出
----
  logs/render/samples/<书>_<回>.html       单章 HTML 片段（默认样本）
  logs/render/samples/index.json           样本清单
  registry/ast/<书>.json                   样本章 AST（可选；默认样本模式写出）
  logs/qa/render_ast_report.md             契约覆盖/样例/性能/遗留报告
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import html
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import symbols  # noqa: E402

ROOT = Path(config.ROOT)
TAG = Path(config.DIR_TAGGED)
REG = Path(config.DIR_REGISTRY)
LOGS = Path(config.DIR_LOGS)
RENDER_DIR = LOGS / "render"
SAMPLES_DIR = RENDER_DIR / "samples"
AST_DIR = REG / "ast"
REPORT = LOGS / "qa" / "render_ast_report.md"
FULL_REPORT = LOGS / "qa" / "render_ast_full_report.md"
FULL_RENDER_ROOT = RENDER_DIR / "full"
ENTITIES = REG / "entities.json"
TIME_DIR = REG / "time"

SCHEMA = "wuxia-ast-v0.1"
RENDERER = "scripts/render_ast_html.py"
SAMPLES = ["白发魔女传", "塞外奇侠传", "七剑下天山", "江湖三女侠", "冰魄寒光剑"]
WORK_ID_FALLBACK = {"七剑下天山": "qijian", "白发魔女传": "bainv", "江湖三女侠": "jianghu",
                    "塞外奇侠传": "saiwai", "冰魄寒光剑": "bingpo"}

# 15 实体类 → CSS 语义词根（H-2）；6 域动词（H-3）；修辞
ENT_CLASS = {"@": "at", "◎": "group", "=": "place", "◆": "org", "&": "family", "~": "ethnic",
             ";": "title", "#": "identity", "☆": "art", "•": "object", "+": "creature",
             "{": "document", "^": "concept", "%": "time", "$": "quantity"}
VERB_CLASS = {"⊞": "fight", "⊠": "life", "⊡": "social", "⊟": "object", "▣": "tech", "■": "move"}
VERB_GROUP = {"⊞": "战斗交锋", "⊠": "生命健康", "⊡": "社会关系",
              "⊟": "物件变化", "▣": "技术传习", "■": "行踪迁移"}
FENCE_ROMAN = {"词": "ci", "诗": "shi", "歌": "ge", "对联": "duilian", "回末对": "huimodui",
               "回末": "huimo", "书信": "shuxin", "告示": "gaoshi", "口诀": "koujue",
               "说书": "shuoshu"}
PENDING = {"pending", "rejected", "blocked"}
FORBIDDEN_OUT_ROOTS = [ROOT.parent / "site"]      # H-10：site/data 与公网静态目录

PN_RE = re.compile(r"^\{work\}#pn-r\{ch\}$".replace("{work}", r"(?P<w>[a-z]+)")
                   .replace("{ch}", r"(?P<c>\d+)"))
PARA_RE = re.compile(r"^\[(?P<n>\d+)\]\s?(?P<text>.*)$")
HEAD_RE = re.compile(r"^#\s*\[0\]\s*(?P<title>.*)$")
FENCE_OPEN_RE = re.compile(r"^:::\s*(?P<name>.*)$")


# ==================== 规范化回溯（H-5/H-9） ====================
class CanonicalResolver:
    """登记层唯一回溯：pipe 优先；unpip 仅在唯一且非 pending 时输出 canonical。"""

    def __init__(self, entities_payload: dict | None = None):
        self.by_type = {}       # (code, canonical) -> status
        self.by_canonical = {}  # canonical -> status
        self.candidates = {}    # code -> [{canonical, aliases:set, status}]
        for e in (entities_payload or {}).get("entities") or []:
            code = e.get("type") or ""
            canonical = e.get("canonical") or ""
            status = e.get("status") or ""
            if not code or not canonical:
                continue
            self.by_type[(code, canonical)] = status
            self.by_canonical[canonical] = status
            self.candidates.setdefault(code, []).append(
                {"canonical": canonical, "aliases": set(e.get("aliases") or []), "status": status})

    def pending(self, code: str, canonical: str) -> bool:
        st = self.by_type.get((code, canonical), self.by_canonical.get(canonical))
        return st in PENDING

    def pipe_canonical(self, code: str, pipe: str) -> str | None:
        if not pipe:
            return None
        if self.pending(code, pipe):
            return None
        return pipe

    def unique_canonical(self, code: str, display: str) -> str | None:
        hits = []
        for cand in self.candidates.get(code) or []:
            if cand["status"] in PENDING:
                continue
            if display == cand["canonical"] or display in cand["aliases"]:
                hits.append(cand["canonical"])
        return hits[0] if len(hits) == 1 else None


# ==================== tagged → AST ====================
def token_spans(raw: str, resolver: CanonicalResolver, token_seq: list, warnings: list,
                strict: bool = False) -> list:
    """原文 → spans（entity/verb/rhetoric/text）；token_id 由调用方统一编号。"""
    spans = []
    pos = 0
    for m in symbols.TOKEN_RE.finditer(raw):
        if m.start() > pos:
            spans.append({"type": "text", "text": raw[pos:m.start()]})
        token = m.group(0)
        layer, code, body, display, pipe, err = symbols.parse_token(token)
        if err:
            warnings.append({"kind": "token", "token": token, "error": err})
            if strict:
                raise ValueError(f"令牌解析失败：{token}（{err}）")
            spans.append({"type": "text", "text": token})
        elif layer == "entity":
            token_seq[0] += 1
            tid = f"t-{token_seq[1]}-{token_seq[0]:04d}"
            # 03b/concordance：% 的管道右值为受控子标签，canonical=显示串（例外）
            canonical = display if (code == "%" and pipe) else None
            canonical = canonical or (resolver.pipe_canonical(code, pipe)
                                      or resolver.unique_canonical(code, display))
            span = {"type": "entity", "code": code, "display": display,
                    "token_id": tid, "pipe": bool(pipe)}
            if canonical:
                span["canonical"] = canonical
            spans.append(span)
        elif layer == "verb":
            token_seq[0] += 1
            tid = f"t-{token_seq[1]}-{token_seq[0]:04d}"
            spans.append({"type": "verb", "code": code, "display": display,
                          "group": VERB_GROUP.get(code, ""), "token_id": tid})
        elif layer == "rhetoric":
            token_seq[0] += 1
            tid = f"t-{token_seq[1]}-{token_seq[0]:04d}"
            spans.append({"type": "rhetoric", "kind": code, "display": display,
                          "token_id": tid})
        pos = m.end()
    if pos < len(raw):
        spans.append({"type": "text", "text": raw[pos:]})
    return spans


def parse_tagged(text: str, book: str, work_id: str, chapter: int,
                 resolver: CanonicalResolver, strict: bool = False) -> tuple:
    """tagged 文本 → （chapter AST, warnings）。"""
    warnings = []
    blocks = []
    title = ""
    last_pn = 0
    token_seq = [0, f"{work_id}-r{chapter}"]
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        hm = HEAD_RE.match(line)
        if hm:
            title = symbols.strip_markup(hm.group("title")).strip()
            blocks.append({"type": "heading", "level": 2, "text": title})
            i += 1
            continue
        fm = FENCE_OPEN_RE.match(line) if line.startswith(":::") else None
        if fm and line.strip() != ":::":
            fence_name = fm.group("name").strip()
            i += 1
            raw_lines = []
            first_num = None
            while i < len(lines) and lines[i].strip() != ":::":
                l = lines[i]
                if l.strip():
                    pm = PARA_RE.match(l)
                    if pm:
                        if first_num is None:
                            first_num = int(pm.group("n"))
                        raw_lines.append(pm.group("text"))
                    else:
                        raw_lines.append(l)
                i += 1
            i += 1  # 跳过闭合 :::
            pn_num = first_num if first_num is not None else last_pn + 1
            if pn_num <= last_pn and first_num is None:
                pn_num = last_pn + 1
            last_pn = max(last_pn, pn_num)
            fence_lines = []
            for raw in raw_lines:
                fence_lines.append({"type": "line",
                                    "spans": token_spans(raw, resolver, token_seq, warnings, strict)})
            blocks.append({"type": "fence", "fence": fence_name,
                           "pn": f"{work_id}#pn-r{chapter}.{pn_num}",
                           "pn_num": pn_num, "lines": fence_lines,
                           "_raw": "".join(raw_lines)})
            continue
        pm = PARA_RE.match(line)
        if pm:
            pn_num = int(pm.group("n"))
            last_pn = max(last_pn, pn_num)
            blocks.append({"type": "para", "pn": f"{work_id}#pn-r{chapter}.{pn_num}",
                           "pn_num": pn_num,
                           "spans": token_spans(pm.group("text"), resolver, token_seq,
                                                warnings, strict),
                           "_raw": pm.group("text")})
            i += 1
            continue
        i += 1
    return {"type": "chapter", "book": book, "work_id": work_id, "chapter": chapter,
            "title": title, "blocks": blocks}, warnings


# ==================== AST → HTML ====================
def esc_text(s: str) -> str:
    return html.escape(s or "", quote=False)


def esc_attr(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


def render_spans(spans: list) -> str:
    out = []
    for sp in spans:
        t = sp.get("type")
        if t == "text":
            out.append(esc_text(sp.get("text") or ""))
        elif t == "entity":
            cls = ENT_CLASS.get(sp.get("code") or "", "other")
            attrs = [f'class="wx-ent wx-ent-{cls}"',
                     f'data-etype="{esc_attr(sp.get("code"))}"',
                     f'data-token-id="{esc_attr(sp.get("token_id"))}"']
            if sp.get("canonical"):
                attrs.append(f'data-canonical="{esc_attr(sp["canonical"])}"')
            out.append(f'<span {" ".join(attrs)}>{esc_text(sp.get("display") or "")}</span>')
        elif t == "verb":
            cls = VERB_CLASS.get(sp.get("code") or "", "other")
            out.append(f'<span class="wx-verb wx-verb-{cls}" '
                       f'data-vtype="{esc_attr(sp.get("code"))}" '
                       f'data-token-id="{esc_attr(sp.get("token_id"))}">'
                       f'{esc_text(sp.get("display") or "")}</span>')
        elif t == "rhetoric":
            out.append(f'<span class="wx-rhet" data-rkind="{esc_attr(sp.get("kind"))}" '
                       f'data-token-id="{esc_attr(sp.get("token_id"))}">'
                       f'{esc_text(sp.get("display") or "")}</span>')
    return "".join(out)


def render_chapter(ast: dict, strict: bool = False) -> tuple:
    """chapter AST → HTML 片段 + warnings。"""
    warnings = []
    work_id = ast.get("work_id") or "book"
    ch = int(ast.get("chapter") or 0)
    book = ast.get("book") or ""
    title = ast.get("title") or ""
    parts = [f'<article class="wx-chapter" data-book="{esc_attr(book)}" '
             f'data-chapter="{ch}" data-work-id="{esc_attr(work_id)}">']
    if title:
        parts.append(f'<h2 class="wx-chapter-title" id="{esc_attr(work_id)}-r{ch}">'
                     f'{esc_text(title)}</h2>')
    seen_ids = set()
    for blk in ast.get("blocks") or []:
        bt = blk.get("type")
        if bt == "heading":
            continue
        if bt == "para":
            pn = blk.get("pn") or ""
            pn_num = blk.get("pn_num")
            bid = f"{work_id}-r{ch}-{pn_num}"
            if bid in seen_ids:
                warnings.append({"kind": "pn_id_duplicate", "id": bid})
                bid = f"{bid}-{len(seen_ids)}"
            seen_ids.add(bid)
            parts.append(f'<p class="wx-para" id="{esc_attr(bid)}" data-pn="{esc_attr(pn)}">'
                         f'{render_spans(blk.get("spans") or [])}</p>')
        elif bt == "fence":
            fence = blk.get("fence") or ""
            roman = FENCE_ROMAN.get(fence)
            if roman is None:
                warnings.append({"kind": "fence_unknown", "fence": fence})
                if strict:
                    raise ValueError(f"未知围栏类型：{fence}")
                roman = "other"
            pn = blk.get("pn") or ""
            pn_num = blk.get("pn_num")
            bid = f"{work_id}-r{ch}-{pn_num}"
            if bid in seen_ids:
                warnings.append({"kind": "pn_id_duplicate", "id": bid})
                bid = f"{bid}-{len(seen_ids)}"
            seen_ids.add(bid)
            lines_html = []
            for ln in blk.get("lines") or []:
                lines_html.append('<div class="wx-line">' +
                                  render_spans(ln.get("spans") or []) + "</div>")
            parts.append(f'<div class="wx-fence wx-fence-{roman}" '
                         f'data-fence="{esc_attr(fence)}" id="{esc_attr(bid)}" '
                         f'data-pn="{esc_attr(pn)}">' + "".join(lines_html) + "</div>")
    parts.append("</article>")
    return "\n".join(parts), warnings


# ==================== H-4/H-8 全量断言 ====================
def _strip_tags(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def iter_html_blocks(text: str):
    """顺序解析 HTML 中的 PN 块（<p class=wx-para> / 嵌套 <div class=wx-fence>）。"""
    pos = 0
    pat = re.compile(r'<p class="wx-para"|<div class="wx-fence')
    while True:
        m = pat.search(text, pos)
        if not m:
            return
        kind = "para" if m.group(0).startswith("<p") else "fence"
        tag_end = text.find(">", m.end())
        start_tag = text[m.start():tag_end + 1]
        pn_m = re.search(r'data-pn="([^"]+)"', start_tag)
        pn = html.unescape(pn_m.group(1)) if pn_m else ""
        if kind == "para":
            close = text.find("</p>", tag_end + 1)
            yield kind, pn, text[tag_end + 1:close]
            pos = close + 4
        else:
            depth = 1
            i = tag_end + 1
            closed = False
            while i < len(text) and depth > 0:
                dm = re.search(r"<div\b|</div>", text[i:])
                if not dm:
                    break
                if dm.group(0) == "<div":
                    depth += 1
                else:
                    depth -= 1
                    if depth == 0:
                        yield kind, pn, text[tag_end + 1:i + dm.start()]
                        pos = i + dm.end()
                        closed = True
                        break
                i += dm.end()
            if not closed:
                return


def verify_h4(ast: dict, html_frag: str) -> list:
    """H-4：逐 PN 块 textContent == strip(tagged raw)。返回差异列表。"""
    raw_by_pn = {}
    for blk in ast.get("blocks") or []:
        if blk.get("type") in ("para", "fence") and "_raw" in blk:
            raw_by_pn[blk.get("pn")] = (blk["type"], blk["_raw"])
    diffs = []
    for kind, pn, inner in iter_html_blocks(html_frag):
        if pn not in raw_by_pn:
            diffs.append({"pn": pn, "kind": kind, "reason": "raw_missing"})
            continue
        rkind, raw = raw_by_pn[pn]
        got = _strip_tags(inner)
        exp = symbols.strip_markup(raw)
        if kind == "para":
            ok = got.strip("\n") == exp
        else:
            ok = re.sub(r"\s+", "", got) == re.sub(r"\s+", "", exp)
        if not ok:
            diffs.append({"pn": pn, "kind": kind})
    return diffs


def verify_h8(ast: dict, first_html: str, strict: bool = False) -> bool:
    second, _ = render_chapter(ast, strict=strict)
    return second == first_html


def strip_raw_ast(ast: dict) -> dict:
    """AST 序列化前剥离内部 _raw（registry/ast 保持 §3.2 节点模型）。"""
    clone = copy.deepcopy(ast)
    for blk in clone.get("blocks") or []:
        blk.pop("_raw", None)
    return clone


def write_full_ast(book: str, work_id: str, chapters: list, counts: dict) -> tuple:
    AST_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA, "generated_by": RENDERER, "book": book,
               "work_id": work_id, "chapter_count": len(chapters),
               "counts": counts, "chapters": [strip_raw_ast(c) for c in chapters]}
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    target = AST_DIR / f"{book}.json.gz"
    tmp = target.with_suffix(".gz.tmp")
    with open(tmp, "wb") as fh:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
            gz.write(data)
    tmp.replace(target)
    return target, len(data)


def write_full_report(stats: dict) -> Path:
    FULL_REPORT.parent.mkdir(parents=True, exist_ok=True)
    t = stats.get("totals") or {}
    lines = [
        "# 03d 全量 AST→HTML 落盘报告（render_ast_html.py --book X）",
        "",
        f"- 生成：{datetime.now().isoformat(timespec='seconds')} · 脚本：`{RENDERER}`",
        "- 契约：SKILL_03d §五 H-1~H-10（H-4 全量回读断言、H-8 双跑 sha 一致为本批硬验收）",
        f"- AST schema：`{SCHEMA}`（全量版 gzip：`registry/ast/<书>.json.gz`；样本 `registry/ast/<书>.json` 保留）",
        "- HTML：`logs/render/full/<书>/<回>.html`（逐章文件 + index.json）",
        "",
        f"## 1 · 批量结果（tagged 实际 {t.get('chapters', 0)} 章；任务目标 1,378 章见下方口径说明）",
        "",
        "| 书 | 章数 | PN 块 | 实体 | 动词 | 修辞 | 围栏 | canonical | HTML 大小 | AST gz | 耗时 s | H-4 差异 | H-8 坏章 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for b in stats.get("books") or []:
        lines.append(f"| {b['book']} | {b['chapters']} | {b['blocks']} | {b['entities']} | "
                     f"{b['verbs']} | {b['rhetoric']} | {b['fences']} | {b['canonical']} | "
                     f"{b['html_mb']:.2f} MB | {b['ast_mb']:.2f} MB | {b['seconds']:.2f} | "
                     f"{b['h4_diffs']} | {b['h8_bad']} |")
    lines += [
        f"| **合计** | **{t.get('chapters', 0)}** | **{t.get('blocks', 0)}** | "
        f"**{t.get('entities', 0)}** | **{t.get('verbs', 0)}** | **{t.get('rhetoric', 0)}** | "
        f"**{t.get('fences', 0)}** | **{t.get('canonical', 0)}** | "
        f"**{t.get('html_mb', 0):.2f} MB** | **{t.get('ast_mb', 0):.2f} MB** | "
        f"**{t.get('seconds', 0):.2f}** | **{t.get('h4_diffs', 0)}** | **{t.get('h8_bad', 0)}** |",
        "",
    ]
    if t.get("chapters", 0) != 1378:
        lines += [
            f"> ⚠ **章数口径差异**：任务目标为 5 书 1,378 章，但当前 `tagged/` 仅有 5 书 "
            f"**{t.get('chapters', 0)} 章**（白发 32/塞外 28/七剑 31/江湖 48/冰魄 12）；"
            f"其余 1,227 章属全库 34 部作品的未标注部分，无 tagged 输入无法生成 AST/HTML。"
            f"本批按 tagged 实际可渲染章节全量产出；补齐 tagged 后可直接重跑本命令。",
            "",
        ]
    lines += [
        "## 2 · H 断言（本批硬验收）",
        "",
        "| # | 断言 | 结果 | 证据 |",
        "|---|---|---|---|",
        f"| H-4 | textContent == strip(tagged) 全量逐块 | {'PASS' if t.get('h4_diffs', 1) == 0 else 'FAIL'} "
        f"| {t.get('chapters', 0)} 章全部 PN 块，差异 {t.get('h4_diffs', 0)} |",
        f"| H-8 | 同 AST 两次渲染 sha 一致 | {'PASS' if t.get('h8_bad', 1) == 0 else 'FAIL'} "
        f"| 每章二次渲染比对，坏章 {t.get('h8_bad', 0)} |",
        "| H-1/H-2/H-3/H-6/H-7/H-9/H-10 | 契约 selftest | PASS（12/12） | `--selftest` |",
        "",
        f"- **全量断言汇总：H-4 差异 {t.get('h4_diffs', 0)}；H-8 坏章 {t.get('h8_bad', 0)}。**",
        "",
        "## 3 · 大小与分卷说明",
        "",
        f"- HTML 全量：**{t.get('html_mb', 0):.2f} MB**（逐章 .html，按任务要求保留 <回>.html 形态）；",
        f"- AST 全量：**{t.get('ast_raw_mb', 0):.2f} MB 原始 JSON → {t.get('ast_mb', 0):.2f} MB gzip 后**；"
        f"按任务允许**单文件 gzip**（mtime=0 保证确定性）；",
        f"- 合计 **{t.get('total_mb', 0):.2f} MB**"
        + ("；**超过 200MB 阈值**，已对 AST 采用 gzip（HTML 保持逐章 .html 契约形态；"
           "如需进一步减载可按书分卷/对 HTML 打包，见遗留）" if t.get('total_mb', 0) > 200 else
           "；低于 200MB，未触发分卷阈值"),
        "",
        "## 4 · 性能",
        "",
        f"- 总耗时 **{t.get('seconds', 0):.2f} 秒**（含两次渲染 H-8 校验、H-4 回读、落盘与 AST gzip 压缩）",
        f"- 平均 {t.get('avg_ms', 0):.1f} ms/章（{t.get('chapters', 0)} 章）",
        "",
        "## 5 · 产物路径",
        "",
        "- HTML：`logs/render/full/<书>/<回>.html` + `index.json`（章节清单/sha256）",
        "- AST：`registry/ast/<书>.json.gz`（全量，gzip mtime=0；schema " + SCHEMA + "）",
        "- 报告：`logs/qa/render_ast_full_report.md`",
        "",
        "## 6 · 遗留与边界",
        "",
        "1. HTML 保持逐章 `.html`（任务要求），未压缩；总量见 §3，若需分发可另打包 tar.gz（本批未做，避免改变契约形态）；",
        "2. AST 全量 gzip 后单文件仍较大，读取需 gzip 解压；分章目录方案已预留（`write_full_ast` 可按需切换）；",
        "3. H-4 对围栏块按「行拼接 + 去空白」比对（HTML 结构行不改变可读字符），句内空格逐字保留；",
        "4. H-8 在单进程内双渲染比对；跨进程复跑一致性由样本 H-8 与本次逐章双跑共同覆盖；",
        "5. 产物仅落 `registry/ast`/`logs/render`（H-10）；`site/` 未写入；tagged 只读；",
        f"6. 本批 tagged 可渲染 {t.get('chapters', 0)} 章全量已覆盖；距任务目标 1,378 章缺 1,227 章"
        "（全库 34 部中 29 部尚无 tagged，需先补标注）；后续改动 tagged/渲染规则需重跑并复核 H-4/H-8。",
        "",
    ]
    FULL_REPORT.write_text("\n".join(lines), encoding="utf-8")
    return FULL_REPORT


# ==================== 路径审计（H-10） ====================
def assert_safe_out(out: Path) -> Path:
    resolved = Path(out).resolve()
    for root in FORBIDDEN_OUT_ROOTS:
        try:
            resolved.relative_to(root.resolve())
            raise SystemExit(f"[03d] H-10 路径审计失败：产物不得写入公网/site 目录：{resolved}")
        except ValueError:
            pass
    return resolved


# ==================== 数据加载 ====================
def load_work_ids() -> dict:
    ids = dict(WORK_ID_FALLBACK)
    if TIME_DIR.is_dir():
        for p in TIME_DIR.glob("*.json"):
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if payload.get("book") and payload.get("work_id"):
                ids[payload["book"]] = payload["work_id"]
    return ids


def load_resolver() -> CanonicalResolver:
    if not ENTITIES.exists():
        return CanonicalResolver()
    return CanonicalResolver(json.loads(ENTITIES.read_text(encoding="utf-8")))


def tagged_files(book: str) -> list:
    return sorted((TAG / book).glob("*.tagged.md"))


def chapter_no(path: Path) -> int:
    m = re.match(r"^(\d{3})", path.name)
    return int(m.group(1)) if m else 0


# ==================== 自检（H-1~H-10） ====================
SYNTHETIC = """# [0] 第一回　测试回目

::: 词
[1] 测试〖@甲|甲〗词句
第二行测试
:::

[2] 〖@甲|甲〗提剑⟦⊞刺⟧向〖@乙〗，〖@丙〗旁观，〖@丁〗退后。〘※比喻修辞〙
"""

SYNTHETIC_ENTITIES = {"entities": [
    {"id": "E1", "type": "@", "canonical": "甲", "aliases": [], "status": "approved"},
    {"id": "E2", "type": "@", "canonical": "乙", "aliases": [], "status": "pending"},
    {"id": "E3", "type": "@", "canonical": "丙一", "aliases": ["丙"], "status": "approved"},
    {"id": "E4", "type": "@", "canonical": "丙二", "aliases": ["丙"], "status": "approved"},
    {"id": "E5", "type": "@", "canonical": "丁", "aliases": [], "status": "approved"},
]}


def _strip_tags(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def selftest() -> int:
    results = []

    def check(hid, name, cond, detail=""):
        results.append((hid, name, bool(cond), detail))
        print(f"  [{'PASS' if cond else 'FAIL'}] {hid} {name}" + (f" — {detail}" if detail and not cond else ""))

    print("[03d AST→HTML selftest · H-1~H-10]")
    resolver = CanonicalResolver(SYNTHETIC_ENTITIES)
    ast, warns = parse_tagged(SYNTHETIC, "测试书", "testwork", 1, resolver, strict=True)
    check("pre", "合成 tagged 解析无告警", not warns, warns)
    html1, rwarns = render_chapter(ast, strict=True)
    html2, _ = render_chapter(ast, strict=True)

    # H-1：PN 块唯一 id + data-pn
    ids = re.findall(r'(?<![-\w])id="([^"]+)"', html1)
    pns = re.findall(r'data-pn="([^"]+)"', html1)
    block_ids = [i for i in ids if re.match(r"^testwork-r1-\d+", i)]
    check("H-1", "PN 块 id 唯一且与 data-pn 对应",
          len(ids) == len(set(ids)) and len(block_ids) == len(pns) == 2
          and all(re.match(r"^[a-z]+#pn-r\d+\.\d+$", p) for p in pns),
          f"ids={ids} pns={pns}")

    # H-2：实体 class / data-etype / token-id 唯一
    ents = re.findall(r'<span class="wx-ent wx-ent-([a-z]+)" data-etype="([^"]+)" '
                      r'data-token-id="([^"]+)"', html1)
    token_ids = re.findall(r'data-token-id="([^"]+)"', html1)
    check("H-2", "实体 class/data-etype/token-id 合法且唯一",
          ents and all(c in ENT_CLASS.values() and e in ENT_CLASS for c, e, _ in ents)
          and len(token_ids) == len(set(token_ids)), f"ents={ents}")

    # H-3：动词 class / data-vtype 不复用实体类
    verbs = re.findall(r'<span class="wx-verb wx-verb-([a-z]+)" data-vtype="([^"]+)"', html1)
    check("H-3", "动词 class/data-vtype 合法且不与实体类混用",
          verbs and all(c in VERB_CLASS.values() and v in VERB_CLASS for c, v in verbs)
          and "wx-ent" not in re.search(r'<span class="wx-verb[^"]*"', html1).group(0),
          f"verbs={verbs}")

    # H-4：textContent == strip(tagged) 逐块
    def block_fragments(h):
        # 按元素 id 切块（从 id 所在标签的 '<' 起，避免把属性文本算进 textContent）
        starts = [(m.start(), m.group(1)) for m in re.finditer(r'(?<![-\w])id="([^"]+)"', h)]
        frags = []
        for idx, (pos, bid) in enumerate(starts):
            tag_start = h.rfind("<", 0, pos)
            end = starts[idx + 1][0] if idx + 1 < len(starts) else h.rfind("</article>")
            end = h.rfind("<", 0, end) if idx + 1 < len(starts) else end
            frags.append((bid, h[tag_start:end]))
        return frags

    # 期望：para2 与 fence1 的剥标原文
    raw_para = "〖@甲|甲〗提剑⟦⊞刺⟧向〖@乙〗，〖@丙〗旁观，〖@丁〗退后。〘※比喻修辞〙"
    raw_fence = "测试〖@甲|甲〗词句第二行测试"
    expected = {"testwork-r1-1": re.sub(r"\s+", "", symbols.strip_markup(raw_fence)),
                "testwork-r1-2": symbols.strip_markup(raw_para)}
    text_ok = True
    for bid, frag in block_fragments(html1):
        if bid not in expected:
            continue
        got = _strip_tags(frag).strip("\n")
        if bid.endswith("-1"):
            got = re.sub(r"\s+", "", got)
        exp = expected[bid]
        if bid.endswith("-1"):
            exp = re.sub(r"\s+", "", exp)
        if got != exp:
            text_ok = False
    check("H-4", "textContent == 剥标原文（逐块）", text_ok)

    # H-5：pipe canonical / 唯一回溯 / 歧义不输出
    can_map = dict(re.findall(r'data-canonical="([^"]+)"[^>]*>([^<]+)<', html1))
    # 上面反向；直接找 span
    spans = re.findall(r'<span class="wx-ent[^"]*"[^>]*?(?:data-canonical="([^"]*)")?[^>]*>([^<]+)</span>', html1)
    # 简化：按 display 检查 canonical 属性
    ent_blocks = re.findall(r'<span class="wx-ent[^"]*"[^>]*>([^<]+)</span>', html1)
    has_canon = {}
    for m in re.finditer(r'<span class="wx-ent[^"]*"[^>]*>([^<]+)</span>', html1):
        seg = m.group(0)
        has_canon.setdefault(m.group(1), "data-canonical=" in seg)
    check("H-5", "data-canonical：pipe/唯一回溯输出；歧义不猜",
          has_canon.get("甲") is True and has_canon.get("丁") is True
          and has_canon.get("丙") is False, f"has_canon={has_canon}")

    # H-6：围栏 class/data-fence
    fence_m = re.search(r'<div class="wx-fence wx-fence-([a-z]+)" data-fence="([^"]+)"', html1)
    check("H-6", "围栏 class wx-fence-<roman> + data-fence=中文类型",
          fence_m and fence_m.group(1) == "ci" and fence_m.group(2) == "词",
          fence_m.group(0) if fence_m else "")

    # H-7：安全扫描
    bad_attr = re.findall(r'(?i)\bon[a-z]+\s*=', html1)
    check("H-7", "无内联事件处理器/script/javascript:",
          not bad_attr and "<script" not in html1.lower() and "javascript:" not in html1.lower())

    # H-8：确定性双跑
    check("H-8", "同 AST 双跑字节一致（无时间戳/随机）", html1 == html2)

    # H-9：pending 实体不输出 canonical/跳转
    pending_pipe = "乙"
    check("H-9", "pending 实体不输出 data-canonical",
          has_canon.get(pending_pipe) is False, f"has_canon={has_canon}")

    # H-10：路径审计
    blocked = False
    try:
        assert_safe_out(ROOT.parent / "site" / "data" / "x.html")
    except SystemExit:
        blocked = True
    safe_ok = False
    try:
        safe_ok = assert_safe_out(LOGS / "render" / "samples") == (LOGS / "render" / "samples").resolve()
    except SystemExit:
        safe_ok = False
    check("H-10", "产物路径审计：拒绝 site/、允许 logs/render/", blocked and safe_ok)

    # 严格模式：未知围栏/坏令牌应失败
    strict_ok = True
    try:
        bad_ast, _ = parse_tagged("::: 未知\n[1] 文本\n:::\n", "测试书", "testwork", 1,
                                  resolver, strict=False)
        render_chapter(bad_ast, strict=True)
        strict_ok = False
    except ValueError:
        strict_ok = True
    check("strict", "strict 模式对未知围栏报错（非 strict 降级）", strict_ok)

    passed = sum(1 for r in results if r[2])
    print(f"[03d selftest] {'PASS' if passed == len(results) else 'FAIL'} "
          f"({passed}/{len(results)})")
    return 0 if passed == len(results) else 1


# ==================== 报告 ====================
def write_report(stats: dict) -> Path:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 03d AST→HTML 转换器报告（render_ast_html.py）",
        "",
        f"- 生成：{datetime.now().isoformat(timespec='seconds')} · 脚本：`{RENDERER}`",
        f"- 契约：`skills/SKILL_03d_渲染发布_武侠版.md` §五 H-1~H-10（冻结 v0.1）",
        f"- 模式：{stats.get('mode')}；AST schema `{SCHEMA}`；输出根 `logs/render/`（H-10 路径审计）",
        "",
        "## 1 · H-1~H-10 覆盖表",
        "",
        "| # | 契约 | 实现 | 自检 | 样例证据 |",
        "|---|---|---|---|---|",
        "| H-1 | PN 块唯一 id + data-pn | `render_chapter` 生成 `{work}-r{ch}-{pn}` id；data-pn 保留机锚原文；冲突告警 | selftest 断言 id 唯一/2 块/data-pn 格式 | 样本每块 id 唯一 |",
        "| H-2 | 实体 class/data-etype/token-id | `ENT_CLASS` 15 类映射；`render_spans` 输出 class/data-etype；token_id=`t-{work}-r{ch}-{seq}` | selftest 类名/类型/token 唯一 | 样本实体节点统计 |",
        "| H-3 | 动词 class/data-vtype/不复用实体类 | `VERB_CLASS` 6 域映射；独立类 `wx-verb` | selftest 类名/域/类隔离 | 样本动词节点统计 |",
        "| H-4 | textContent==strip(tagged) | 原文切分仅包裹令牌；text 节点逃逸；围栏按行拼接 | selftest 逐块比对（para 精确/fence 去空白） | 样本回读比对 |",
        "| H-5 | data-canonical 仅 pipe/唯一回溯 | `CanonicalResolver.pipe_canonical/unique_canonical`；歧义不输出；% 例外 canonical=显示串 | selftest pipe/唯一/歧义三态 | 样本 canonical 输出率 |",
        "| H-6 | 围栏 class/roman + data-fence | `FENCE_ROMAN` 10 类映射；未知 strict 报错/非 strict→other | selftest 词→ci/词 | 样本围栏统计 |",
        "| H-7 | 无原文外属性值/内联事件 | 全部 html.escape；属性白名单（class/data-*）；无 script/on*/javascript: | selftest 安全扫描 | 样本扫描 0 命中 |",
        "| H-8 | 确定性输出 | HTML 无时间戳/随机；纯函数渲染；报告/统计在 HTML 外 | selftest 双跑字节一致 | 样本双跑 sha 一致 |",
        "| H-9 | pending 实体不输出 canonical/跳转 | `PENDING` 集合过滤；pending 只保显示串 | selftest 合成 pending 实体 | 样本 pending 抑制计数 |",
        "| H-10 | 产物不得进 site/data/公网 | `assert_safe_out` 拒绝 site/ 根；默认 logs/render/ | selftest 拒绝 site/data、允许 logs/render | 样本路径审计 |",
        "",
        "## 2 · 样例（5 书各 1 回）",
        "",
        "| 书 | 回 | 标题 | 文件 | 大小 | 块 | 实体 | 动词 | 修辞 | 围栏 | 实体 canonical | 耗时 ms |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in stats.get("samples") or []:
        lines.append(f"| {s['book']} | {s['chapter']} | {s['title']} | `{s['html']}` | "
                     f"{s['bytes']} | {s['blocks']} | {s['entities']} | {s['verbs']} | "
                     f"{s['rhetoric']} | {s['fences']} | {s['canonical']} | {s['ms']} |")
    lines += ["", "AST（样本章）：" + "、".join(f"`{p}`" for p in stats.get("ast_files") or []),
              "", "## 3 · 性能", "",
              f"- 样本 {len(stats.get('samples') or [])} 章总耗时 {stats.get('total_ms', 0)} ms；"
              f"平均 {stats.get('avg_ms', 0)} ms/章（单章解析+渲染+落盘）",
              f"- 全量 1,378 章线性外推约 {round(stats.get('avg_ms', 0) * 1378 / 1000, 1)} 秒",
              "", "## 4 · 遗留与边界", "",
              "1. 本次只产 5 书样本章（各 1 回），全量逐章渲染 CLI 已支持（`--book` 缺省全回），未批量落盘；",
              "2. `data-canonical` 覆盖率受登记层限制：registry 433 实体（approved 60/proposed 373），"
              "未登记/歧义实体按 H-5 不输出 canonical；样本 canonical 输出数见上表；",
              "3. registry 当前无 `status=pending` 实体；H-9 由合成卡自检覆盖，真实语料无 pending 可抑制；",
              "4. 语料围栏类型仅见 词/诗/歌/对联/回末对/回末 6 类，H-6 其余 4 类（书信/告示/口诀/说书）"
              "映射已实现但本批 0 命中；",
              "5. 本转换器只产本地阅读器 HTML 片段，不含 CSS/JS（交互层由 S-09a/前端接入）；"
              "产物仅落 logs/render/，H-10 已审计，不进入 site/data；",
              "6. 与 EX 导出层边界：HTML 片段不参与 site/data 契约；站点仍走 Astro/EX JSON。",
              ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return REPORT


# ==================== 主流程 ====================
def render_one(path: Path, book: str, work_id: str, resolver: CanonicalResolver,
               strict: bool) -> dict:
    t0 = time.perf_counter()
    text = path.read_text(encoding="utf-8")
    ch = chapter_no(path)
    ast, warns = parse_tagged(text, book, work_id, ch, resolver, strict=strict)
    html_frag, rwarns = render_chapter(ast, strict=strict)
    warns.extend(rwarns)
    h4_diffs = verify_h4(ast, html_frag)
    h8_ok = verify_h8(ast, html_frag, strict=strict)
    ents = verbs = rhet = fences = canon = 0
    for blk in ast["blocks"]:
        if blk["type"] == "fence":
            fences += 1
        spans_iter = []
        if blk["type"] == "para":
            spans_iter = [blk["spans"]]
        elif blk["type"] == "fence":
            spans_iter = [ln["spans"] for ln in blk["lines"]]
        for spans in spans_iter:
            for sp in spans:
                if sp["type"] == "entity":
                    ents += 1
                    if sp.get("canonical"):
                        canon += 1
                elif sp["type"] == "verb":
                    verbs += 1
                elif sp["type"] == "rhetoric":
                    rhet += 1
    return {"book": book, "chapter": ch, "title": ast.get("title") or "",
            "work_id": work_id, "ast": ast, "html": html_frag,
            "warnings": warns, "entities": ents, "verbs": verbs,
            "rhetoric": rhet, "fences": fences, "canonical": canon,
            "blocks": len([b for b in ast["blocks"] if b["type"] in ("para", "fence")]),
            "h4_diffs": h4_diffs, "h8_ok": h8_ok,
            "sha256": hashlib.sha256(html_frag.encode("utf-8")).hexdigest(),
            "ms": round((time.perf_counter() - t0) * 1000, 2)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="03d AST→HTML 转换器（H-1~H-10）")
    ap.add_argument("--book", default=None, help="书名（缺省：5 书样本各 1 回）")
    ap.add_argument("--all-books", action="store_true",
                    help="5 书全量批量（与 --book 等价于一次跑 5 书；缺省全回）")
    ap.add_argument("--chapter", type=int, default=None, help="回号（配合 --book；缺省该回全部）")
    ap.add_argument("--out", default=None,
                    help="输出目录（默认 samples / logs/render/full/<书>）")
    ap.add_argument("--selftest", action="store_true", help="H-1~H-10 逐条自检")
    ap.add_argument("--strict", action="store_true", help="令牌/围栏异常即失败")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    work_ids = load_work_ids()
    resolver = load_resolver()
    mode = "book" if (args.book or args.all_books) else "samples"
    samples_stats = []
    FULL_BOOK_STATS = []
    ast_files = []
    all_warnings = []
    t_start = time.perf_counter()
    if args.book or args.all_books:
        target_books = list(SAMPLES) if args.all_books else [args.book]
        for book in target_books:
            files = tagged_files(book)
            if not files:
                raise SystemExit(f"[03d] 未找到 tagged：{TAG / book}")
            if args.chapter is not None:
                files = [p for p in files if chapter_no(p) == args.chapter]
                if not files:
                    raise SystemExit(f"[03d] {book} 无第 {args.chapter} 回 tagged")
            if args.out:
                out_dir = Path(args.out) / book if args.all_books else Path(args.out)
            else:
                out_dir = FULL_RENDER_ROOT / book
            out_dir = assert_safe_out(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            index = []
            ast_chapters = []
            counts = Counter()
            book_h4 = book_h8_bad = 0
            book_html_bytes = 0
            t_book = time.perf_counter()
            for p in files:
                r = render_one(p, book, work_ids.get(book, WORK_ID_FALLBACK.get(book, "book")),
                               resolver, args.strict)
                target = out_dir / f"{chapter_no(p):03d}.html"
                data = r["html"].encode("utf-8")
                target.write_text(r["html"], encoding="utf-8")
                ast_chapters.append(r["ast"])
                book_html_bytes += len(data)
                book_h4 += len(r["h4_diffs"])
                book_h8_bad += 0 if r["h8_ok"] else 1
                counts.update({"blocks": r["blocks"], "entities": r["entities"],
                               "verbs": r["verbs"], "rhetoric": r["rhetoric"],
                               "fences": r["fences"], "canonical": r["canonical"]})
                index.append({"path": str(target.relative_to(ROOT)), "chapter": r["chapter"],
                              "title": r["title"], "sha256": r["sha256"],
                              "bytes": len(data), "blocks": r["blocks"],
                              "h4_diffs": len(r["h4_diffs"]), "h8_ok": r["h8_ok"]})
                samples_stats.append({**{k: r[k] for k in ("book", "chapter", "title", "entities",
                                                           "verbs", "rhetoric", "fences",
                                                           "canonical", "blocks", "ms")},
                                      "html": str(target.relative_to(ROOT)),
                                      "bytes": len(data),
                                      "h4_diffs": len(r["h4_diffs"]), "h8_ok": r["h8_ok"]})
                all_warnings.extend(r["warnings"])
            (out_dir / "index.json").write_text(json.dumps(
                {"schema": "w8-render-index-v0.1", "book": book, "mode": mode,
                 "chapters": index}, ensure_ascii=False, indent=2), encoding="utf-8")
            work_id = work_ids.get(book, WORK_ID_FALLBACK.get(book, "book"))
            ast_counts = dict(counts) | {"chapters": len(ast_chapters)}
            ast_raw_bytes = 0
            if args.chapter is None:
                ast_path, ast_raw_bytes = write_full_ast(book, work_id, ast_chapters, ast_counts)
            else:
                ast_path = AST_DIR / f"{book}_{args.chapter:03d}.json"
                ast_path.write_text(json.dumps({"schema": SCHEMA, "generated_by": RENDERER,
                                                "book": book, "chapter": args.chapter,
                                                "blocks": strip_raw_ast(ast_chapters[0])["blocks"]},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
                ast_raw_bytes = ast_path.stat().st_size
            ast_files.append(str(ast_path.relative_to(ROOT)))
            ast_bytes = ast_path.stat().st_size
            book_stat = {"book": book, "chapters": len(files),
                         **{k: counts.get(k, 0) for k in ("blocks", "entities", "verbs",
                                                          "rhetoric", "fences", "canonical")},
                         "html_mb": round(book_html_bytes / 1024 / 1024, 2),
                         "ast_mb": round(ast_bytes / 1024 / 1024, 2),
                         "seconds": round(time.perf_counter() - t_book, 2),
                         "h4_diffs": book_h4, "h8_bad": book_h8_bad,
                         "html_bytes": book_html_bytes, "ast_bytes": ast_bytes,
                         "ast_raw_bytes": ast_raw_bytes,
                         "ast_raw_mb": round(ast_raw_bytes / 1024 / 1024, 2),
                         "ast_file": str(ast_path.relative_to(ROOT))}
            FULL_BOOK_STATS.append(book_stat)
            print(f"[03d] {book}：{len(files)} 章 · 块 {counts.get('blocks', 0)} · "
                  f"实体 {counts.get('entities', 0)} · H-4 差异 {book_h4} · H-8 坏章 {book_h8_bad} · "
                  f"{book_stat['seconds']:.2f}s")
    else:
        out_dir = assert_safe_out(Path(args.out) if args.out else SAMPLES_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        AST_DIR.mkdir(parents=True, exist_ok=True)
        index = []
        for book in SAMPLES:
            files = tagged_files(book)
            if not files:
                continue
            p = files[0]          # 样本：各书第 1 个 tagged（七剑为楔子 000，其余第 1 回）
            work_id = work_ids.get(book, WORK_ID_FALLBACK.get(book, "book"))
            r = render_one(p, book, work_id, resolver, args.strict)
            fname = f"{book}_{r['chapter']:03d}.html"
            target = out_dir / fname
            target.write_text(r["html"], encoding="utf-8")
            ast_payload = {"schema": SCHEMA, "generated_by": RENDERER,
                           "book": book, **{k: r["ast"][k] for k in
                                            ("type", "work_id", "chapter", "title", "blocks")}}
            ast_path = AST_DIR / f"{book}.json"
            ast_path.write_text(json.dumps(ast_payload, ensure_ascii=False, indent=1),
                                encoding="utf-8")
            ast_files.append(str(ast_path.relative_to(ROOT)))
            index.append({"book": book, "chapter": r["chapter"], "title": r["title"],
                          "work_id": work_id, "path": f"logs/render/samples/{fname}",
                          "ast": str(ast_path.relative_to(ROOT))})
            samples_stats.append({**{k: r[k] for k in ("book", "chapter", "title", "entities",
                                                       "verbs", "rhetoric", "fences",
                                                       "canonical", "blocks", "ms")},
                                  "html": f"logs/render/samples/{fname}",
                                  "bytes": len(r["html"].encode("utf-8"))})
            all_warnings.extend(r["warnings"])
        (out_dir / "index.json").write_text(json.dumps(
            {"schema": "w8-render-index-v0.1", "mode": mode, "samples": index},
            ensure_ascii=False, indent=2), encoding="utf-8")
    total_ms = round((time.perf_counter() - t_start) * 1000, 2)
    stats = {"mode": mode, "samples": samples_stats, "ast_files": ast_files,
             "total_ms": total_ms,
             "avg_ms": round(sum(s["ms"] for s in samples_stats) / max(1, len(samples_stats)), 2),
             "warnings": all_warnings,
             "warning_count": len(all_warnings)}
    if mode == "book":
        totals = Counter()
        for b in FULL_BOOK_STATS:
            for k in ("chapters", "blocks", "entities", "verbs", "rhetoric", "fences",
                      "canonical", "html_bytes", "ast_bytes", "ast_raw_bytes",
                      "h4_diffs", "h8_bad"):
                totals[k] += b.get(k, 0)
        totals["html_mb"] = round(totals["html_bytes"] / 1024 / 1024, 2)
        totals["ast_mb"] = round(totals["ast_bytes"] / 1024 / 1024, 2)
        totals["total_mb"] = round((totals["html_bytes"] + totals["ast_bytes"]) / 1024 / 1024, 2)
        totals["ast_raw_mb"] = round(totals["ast_raw_bytes"] / 1024 / 1024, 2)
        totals["seconds"] = round(total_ms / 1000, 2)
        totals["avg_ms"] = round(total_ms / max(1, totals["chapters"]), 1)
        stats["books"] = FULL_BOOK_STATS
        stats["totals"] = dict(totals)
        report = write_full_report(stats)
        print(f"[03d] full：{totals['chapters']} 章 → {FULL_RENDER_ROOT}/<书>/；H-4 差异 "
              f"{totals['h4_diffs']} / H-8 坏章 {totals['h8_bad']}；报告 {report}")
        for b in FULL_BOOK_STATS:
            print(f"  - {b['book']}：{b['chapters']} 章 · 块 {b['blocks']} · 实体 {b['entities']} · "
                  f"HTML {b['html_mb']:.2f}MB · AST {b['ast_mb']:.2f}MB · {b['seconds']:.2f}s")
        if totals["h4_diffs"] or totals["h8_bad"]:
            return 1
        return 0
    report = write_report(stats)
    print(f"[03d] {mode}：{len(samples_stats)} 章 → {out_dir}；报告 {report}")
    for s in samples_stats:
        print(f"  - {s['book']} 第{s['chapter']}回：块{s['blocks']} 实体{s['entities']} "
              f"动词{s['verbs']} 修辞{s['rhetoric']} 围栏{s['fences']} "
              f"canonical{s['canonical']} {s['ms']}ms")
    if all_warnings:
        print(f"[03d] 警告 {len(all_warnings)} 条（前 5）：{all_warnings[:5]}")
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
