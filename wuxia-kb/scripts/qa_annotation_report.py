# -*- coding: utf-8 -*-
"""标注质量自检报告（结构 + 语义高风险项抽检，供 Lead 终验/文档引用）。

检查项：
  A 结构：逐段剥标 == struct 底本；令牌合法（类型码/闭合/无嵌套）；管道纪律；
  B 管道审计：所有人物管道的 (显示串→规范名) 是否落在《已核准映射表》内，身份管道、
    % 受控标签、其他实体类型的管道残留。映射表缺省 = `registry/entities.json`（试点书
    白发登记表）+ 已过审 tagged 实际管道；**换书批次请传本书映射快照与登记表**：
    `--mapping-file`（本书映射快照，单回文件或快照目录）/`--registry`（本书登记表）；
  C 密度与分布：分回 E/V/R 计数与 E/100 字、V/100 字，15 类实体 + 6 域动词分布；
  D 空标段/异常段：无任何标记的正文字段、动词域占比异常（>60% 单域）。

book-aware（task-64）：回级注记（registry `context_notes` / 快照条目 chapter/scope 字段）
与 accept_batch 同口径——传 `--book` 时**只生效本书作用域的注记**（带 book/books 的条目
仅书匹配时装载），避免多书共用 registry 时 (回,显示串) 跨书串味；无书级注记的书输出不变。
用法：
    python scripts/qa_annotation_report.py --book 白发魔女传 --chapters 20-32
    python scripts/qa_annotation_report.py --book 白发魔女传 --chapters 1-19   # 金标准对照
    # 换书批次（本书快照；缺省参数下行为与旧版一致）
    python scripts/qa_annotation_report.py --book 江湖三女侠 --chapters 1-48 \\
        --mapping-file logs/mapping_江湖三女侠/ch_048.json \\
        --registry ../kb/江湖三女侠/实体登记表.json
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config      # noqa: E402
import symbols     # noqa: E402
from annotate_chapter_llm import (PARA_RE, load_mapping_table, read_struct,  # noqa: E402
                                  strip_all)

ENT_ORDER = "@◎=◆&~;#☆•+{^%$"
VERB_ORDER = "⊞⊠⊡⊟▣■"


def parse_chapters(spec: str):
    out = []
    try:
        for part in spec.split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                out.extend(range(int(a), int(b) + 1))
            else:
                out.append(int(part))
    except ValueError:
        raise SystemExit(f"[ERROR] --chapters 格式非法：{spec!r}（示例：20-32 或 12,13）")
    return out


# ---------------------------------------------------------------- 映射来源 ----
def _resolve_path(value: str) -> Path:
    """命令行路径：绝对路径原样；相对路径优先按项目根解析。"""
    p = Path(value).expanduser()
    if p.is_absolute():
        return p
    cand = config.ROOT / p
    if cand.exists():
        return cand
    return Path.cwd() / p


def _display_path(p: Path) -> str:
    rp = Path(p).resolve()
    try:
        return str(rp.relative_to(config.ROOT)).replace("\\", "/")
    except ValueError:
        return str(rp)


def _iter_entity_records(data):
    """登记表 JSON → 实体记录 list（兼容 entities-list / entities-dict / 裸 list）。"""
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    if not isinstance(data, dict):
        return []
    entities = data.get("entities", [])
    if isinstance(entities, list):
        return [e for e in entities if isinstance(e, dict)]
    if isinstance(entities, dict):
        out = []
        for key, rec in entities.items():
            if not isinstance(rec, dict):
                continue
            rec = dict(rec)
            rec.setdefault("canonical", str(key).lstrip("@"))
            out.append(rec)
        return out
    return []


def _registry_mapping(data) -> dict:
    """登记表 → {显示串(别名): 规范名}（口径与 load_mapping_table 的 registry 段一致）。"""
    mapping = {}
    for e in _iter_entity_records(data):
        canon = (e.get("canonical") or "").strip()
        if not canon:
            continue
        for a in list(e.get("aliases") or []) + list(e.get("contextual") or []):
            a = (a or "").strip()
            if not a or "（" in a or "(" in a or a == canon:
                continue
            mapping.setdefault(a, canon)
    return mapping


def _registry_mapping_scoped(data, book: str | None = None) -> tuple:
    """登记表 → ({显示串: 规范名}, {(回, 显示串): 规范名}, {(回, 段, 显示串): 规范名})。

    回级/段级注记载体与 accept_batch 同源（`_add_scope_notes`：记录级 context_notes 或
    aliases/contextual 中的 dict 条目）；全局段与 `_registry_mapping` 逐条一致。
    book 传入时只装载该书作用域注记（与 accept_batch `load_registry_snapshot(book=...)`
    同口径；book=None 时跳过带 book/books 的条目，行为与旧版逐字节一致）。
    task-65：带 `pn`/`pns`/`pn_range` 的条目进 scoped_pn（段级优先于回级）。
    """
    from accept_batch import _add_scope_notes      # 单一来源：回级注记解析只在 accept 实现
    mapping, scoped, scoped_pn = {}, {}, {}
    for e in _iter_entity_records(data):
        canon = (e.get("canonical") or "").strip()
        if not canon:
            continue
        for a in list(e.get("aliases") or []) + list(e.get("contextual") or []):
            if isinstance(a, dict):
                continue
            a = (a or "").strip()
            if not a or "（" in a or "(" in a or a == canon:
                continue
            mapping.setdefault(a, canon)
        _add_scope_notes(e, canon, scoped, book=book, scoped_pn=scoped_pn)
    return mapping, scoped, scoped_pn


_MAPPING_LIST_KEYS = ("items", "pairs", "mapping_pairs", "entries")
_MAPPING_DICT_KEYS = ("mapping", "map", "pairs_map")


def _mapping_items_from_obj(data):
    """映射快照 JSON → 原始“对”序列（不识别返回 None）。

    兼容 list-of-pairs [[显示串,规范名],...]（logs/mapping_<书>/ch_NNN.json 即此格式）、
    {"items"/"pairs": [...]} 包壳、{"mapping": {显示串: 规范名}} 或顶层纯映射 dict。
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in _MAPPING_LIST_KEYS:
            val = data.get(key)
            if isinstance(val, list):
                return val
        for key in _MAPPING_DICT_KEYS:
            val = data.get(key)
            if isinstance(val, dict):
                return [[k, v] for k, v in val.items()]
        if "entities" in data or "version" in data:
            return None
        return [[k, v] for k, v in data.items() if isinstance(v, str)]
    return None


def _snapshot_mapping(path: Path) -> dict:
    """映射快照（单文件或目录）→ {显示串: 规范名}；schema 不识别抛 ValueError。"""
    mapping, _scoped, _pn = _snapshot_mapping_scoped(path)
    return mapping


def _snapshot_mapping_scoped(path: Path, book: str | None = None) -> tuple:
    """映射快照 → ({显示串: 规范名}, {(回, 显示串): 规范名}, {(回, 段, 显示串): 规范名})。

    全局段保持旧 `setdefault` 首见优先语义（A/B 逐字节不变）；回级条目复用
    accept_batch `_pairs_from_items` 的 scope 解析（单一来源；task-64 增加 book-aware，
    带 book/books 的条目只在 book 匹配时生效）。task-65：带 pn 的 dict 条目只进
    scoped_pn，不重复进回级 scoped。
    """
    from accept_batch import _pairs_from_items, _item_pn_scope
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    if not files:
        raise ValueError("目录下没有 *.json 快照文件")
    mapping, scoped, scoped_pn = {}, {}, {}
    for f in files:
        try:
            data = json.loads(io.open(f, encoding="utf-8").read())
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"{f.name}: {type(e).__name__}: {e}")
        items = _mapping_items_from_obj(data)
        if items is None:
            raise ValueError(f"{f.name}: 无法识别的映射快照 schema"
                             "（应为 list-of-pairs 或 {显示串: 规范名}）")
        pn_items = [it for it in items
                    if isinstance(it, dict) and _item_pn_scope(it)]
        plain_items = [it for it in items if it not in pn_items]
        _pairs_from_items(plain_items, set(), set(), scoped=scoped, book=book)
        for item in plain_items:
            disp = canon = ""
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                disp, canon = str(item[0]).strip(), str(item[1]).strip()
            elif isinstance(item, dict):
                disp = str(item.get("display") or item.get("disp")
                           or item.get("surface") or "").strip()
                canon = str(item.get("canonical") or item.get("canon")
                            or item.get("note") or "").strip()
            if disp and canon:
                mapping.setdefault(disp, canon)
        for item in pn_items:
            from accept_batch import _item_scope
            disp = str(item.get("display") or item.get("disp")
                       or item.get("surface") or "").strip()
            canon = str(item.get("canonical") or item.get("canon")
                        or item.get("note") or "").strip()
            chapters, books = _item_scope(item)
            if books and (book is None or book not in books):
                continue
            if disp and canon:
                for c in chapters:
                    for pn in _item_pn_scope(item):
                        scoped_pn[(c, pn, disp)] = canon
    return mapping, scoped, scoped_pn


def _effective_mapping(mapping: dict, scoped: dict, ch: int) -> dict:
    """回级视图：本回 scoped 覆盖同显示串全局映射；无 scoped 时返回原 dict（零拷贝）。

    task-16 快路径：该回无任何回级条目时也直接返回原 dict，避免逐回复制大字典。
    """
    if not scoped:
        return mapping
    hits = {disp: target for (c, disp), target in scoped.items() if c == ch}
    if not hits:
        return mapping
    eff = dict(mapping)
    eff.update(hits)
    return eff


def _tagged_pipe_pairs(book: str) -> dict:
    """已过审 tagged 中实际使用过的 @ 管道（显示串→规范名），仅作登记表口径补充。"""
    pairs = {}
    d = config.DIR_TAGGED / book
    if not d.is_dir():
        return pairs
    pipe_re = re.compile(r"〖@([^|〗]+)\|([^〗]+)〗")
    for p in sorted(d.glob("*.tagged.md")):
        t = io.open(p, encoding="utf-8").read()
        for m in pipe_re.finditer(t):
            disp, canon = m.group(1).strip(), m.group(2).strip()
            if disp and canon and disp != canon:
                pairs.setdefault(disp, canon)
    return pairs


def _load_display_canonical() -> dict:
    """registry/display_canonical.json → {canonical: display}（B-1/B-2 展示层白名单）。

    2026-11-05 P4：管道冲突判定时，若管道规范名恰为登记表规范名的 display
    （如 康熙 vs 玄烨、飞红巾 vs 哈玛雅），属展示/规范分层而非标注错，不报冲突。
    表缺失/坏文件 → 空映射（行为与旧版逐字节一致）。
    """
    p = config.DIR_REGISTRY / "display_canonical.json"
    out = {}
    try:
        data = json.loads(io.open(p, encoding="utf-8").read())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return out
    entries = data.get("entries") if isinstance(data, dict) else None
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        c = (e.get("canonical") or "").strip()
        d = (e.get("display") or "").strip()
        if c and d and c != d:
            out[c] = d
    return out


def load_audit_mapping(args):
    """管道审计映射来源 → ({显示串: 规范名}, 来源说明 or None, {(回,显示串): 规范名})。

    缺省（不传新参数）严格保持旧口径：load_mapping_table(book)（registry/entities.json
    + 已过审 tagged 实际管道）。传 --mapping-file 时以本书快照为审计口径（不再混入
    缺省 registry，除非另传 --registry）；仅传 --registry 时替换 registry 段、保留
    tagged 管道补充。第三段为回级注记（registry context_notes / 快照条目 chapter 字段），
    按回覆盖同显示串映射，其余回不受影响（缺省无回级注记时为空，输出与旧版逐字节一致）。

    task-64：回级注记 book-aware —— 与 accept_batch `load_registry_snapshot(book=...)` /
    `_pairs_from_items(book=...)` 对齐，只装载 `--book` 本书作用域的 context_notes
    （七剑 38 / 江湖 51 条带 book 字段；其它书无 → 行为不变）。
    """
    if args.mapping_file is None and args.registry is None:
        mapping = dict(load_mapping_table(args.book))
        scoped, scoped_pn = {}, {}
        try:
            from accept_batch import load_registry_snapshot
            reg = load_registry_snapshot(None, book=args.book)
            scoped = dict(reg.scoped)
            scoped_pn = dict(reg.scoped_pn)
        except (FileNotFoundError, json.JSONDecodeError, OSError, ImportError):
            scoped, scoped_pn = {}, {}
        return mapping, None, scoped, scoped_pn
    mapping, notes, scoped, scoped_pn = {}, [], {}, {}
    snap = reg = None
    if args.mapping_file is not None:
        p = _resolve_path(args.mapping_file)
        if not p.exists():
            print(f"[qa][ERROR] --mapping-file 不存在：{_display_path(p)}", file=sys.stderr)
            raise SystemExit(2)
        try:
            snap, snap_scoped, snap_pn = _snapshot_mapping_scoped(p, book=args.book)
        except ValueError as e:
            print(f"[qa][ERROR] --mapping-file 无法解析：{_display_path(p)}：{e}",
                  file=sys.stderr)
            raise SystemExit(2)
        if not snap:
            print(f"[qa][WARN] --mapping-file 未解析出任何映射对：{_display_path(p)}"
                  "（空快照或 schema 不识别）")
        notes.append(f"映射快照 `{_display_path(p)}`（{len(snap)} 对）")
        for disp, canon in snap.items():
            mapping.setdefault(disp, canon)
        scoped.update(snap_scoped)
        scoped_pn.update(snap_pn)
    if args.registry is not None:
        p = _resolve_path(args.registry)
        if not p.exists():
            print(f"[qa][ERROR] --registry 不存在：{_display_path(p)}", file=sys.stderr)
            raise SystemExit(2)
        try:
            data = json.loads(io.open(p, encoding="utf-8").read())
        except (json.JSONDecodeError, OSError) as e:
            print(f"[qa][ERROR] --registry 无法解析：{_display_path(p)}："
                  f"{type(e).__name__}: {e}", file=sys.stderr)
            raise SystemExit(2)
        reg, reg_scoped, reg_pn = _registry_mapping_scoped(data, book=args.book)
        notes.append(f"登记表 `{_display_path(p)}`（{len(reg)} 条映射）")
        for disp, canon in reg.items():
            mapping.setdefault(disp, canon)
        scoped.update(reg_scoped)
        scoped_pn.update(reg_pn)
    if args.mapping_file is None and args.registry is not None:
        # 仅替换 registry 段：保留旧口径的“已过审 tagged 实际管道”补充
        for disp, canon in _tagged_pipe_pairs(args.book).items():
            mapping.setdefault(disp, canon)
    if scoped:
        notes.append(f"回级注记 {len(scoped)} 条（按 (书,回,显示串) 生效）")
    if scoped_pn:
        notes.append(f"段级注记 {len(scoped_pn)} 条（按 (书,回,段,显示串) 生效）")
    return mapping, "；".join(notes), scoped, scoped_pn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default=config.PILOT_BOOK)
    ap.add_argument("--chapters", required=True)
    ap.add_argument("--out", default=None, help="报告落盘路径（缺省 logs/qa/NN.md）")
    ap.add_argument("--mapping-file", default=None, metavar="PATH",
                    help="管道审计映射快照（缺省 = registry/entities.json + 已过审 tagged "
                         "实际管道，即试点书白发口径）；**换书批次请传本书映射快照**："
                         "单回快照文件（如 logs/mapping_江湖三女侠/ch_003.json）或快照目录，"
                         "兼容 list-of-pairs [[显示串,规范名],...] 与 {显示串:规范名} 两种格式")
    ap.add_argument("--registry", default=None, metavar="PATH",
                    help="管道审计实体登记表路径（缺省 registry/entities.json，即白发试点"
                         "登记表）；**换书批次请传本书登记表**（支持 registry/entities.json "
                         "与 kb/<书>/实体登记表.json 两种 schema）")
    args = ap.parse_args()
    chapters = parse_chapters(args.chapters)
    mapping, mapping_note, scoped_mapping, scoped_pn = load_audit_mapping(args)
    display_map = _load_display_canonical()   # B-1/B-2 展示层白名单（2026-11-05 P4）
    try:
        from accept_batch import names_equivalent   # 与 accept 同口径：别名归一 + 展示层归一
    except ImportError:
        names_equivalent = None
    pipe_display_ok = 0
    if mapping_note:
        print(f"[qa] 管道审计映射来源：{mapping_note}")
    no_pipe_codes = set("◎=◆&~;#☆•+{^$")

    struct_errs, pipe_issues, empty_paras = [], [], []
    fence_tokens_all, tao_tokens_all = [], []
    title_tokens_total = 0
    rows = []
    global_ent, global_verb = {}, {}
    for ch in chapters:
        mapping_ch = _effective_mapping(mapping, scoped_mapping, ch)
        # 段级覆盖（task-65）：(回, 段, 显示串) 优先于回级/全局
        pn_map = {(pn, disp): target for (c, pn, disp), target in scoped_pn.items()
                  if c == ch}
        sp, tp = config.struct_path(args.book, ch), config.tagged_path(args.book, ch)
        if not tp.exists():
            rows.append({"ch": ch, "missing": True})
            continue
        _, paras = read_struct(sp)
        tagged = io.open(tp, encoding="utf-8").read()
        ce, cv = {}, {}
        chars = 0
        in_fence = False
        fence_kind = ""
        # 回末套语段位置约束（2026-11-06 与 accept_batch 同步）：只在章末最后两段判负规则，
        # 避免正文中段"若欲知详情"等叙述语误报（冰川天女传 009[33]）。
        last_pns = set(sorted(paras)[-2:]) if paras else set()
        for ln in tagged.split("\n"):
            fm = re.match(r"^::: ?(\S+)", ln)
            if fm:
                in_fence, fence_kind = True, fm.group(1)
                continue
            if re.match(r"^:::\s*$", ln):
                in_fence, fence_kind = False, ""
                continue
            if ln.startswith("# "):
                title_tokens_total += ln.count("〖") + ln.count("⟦")
                continue
            if in_fence:
                # 2026-11-05 P4：围栏内令牌全扫（含无 PN 的开篇词/自题词行，
                # 原实现只统计带 [pn] 的段落，漏检 001 开篇『自题《…》』类）。
                fnt = ln.count("〖") + ln.count("⟦")
                if fnt:
                    fence_tokens_all.append(f"{ch:03d}[{fence_kind or '围栏'}]×{fnt}")
            m = PARA_RE.match(ln)
            if not m:
                continue
            pn, text = int(m.group(1)), m.group(2)
            src = paras.get(pn)
            chars += len(src or "")
            if src is None:
                struct_errs.append(f"{ch:03d}[{pn}] struct 无此段")
                continue
            if strip_all(text) != src:
                struct_errs.append(f"{ch:03d}[{pn}] 剥标 != 底本")
            if not re.search(r"[〖⟦〘]", text) and src.strip():
                empty_paras.append(f"{ch:03d}[{pn}]")
            ntok = text.count("〖") + text.count("⟦")
            # 2026-11-05 与 accept_batch.TAO_RE 同步收窄：原 `欲知` 字面会误命中
            # "多欲知道"类正文（塞外奇侠传 004[5] 实测误报），只认完整引导公式词形。
            if (pn in last_pns and
                    re.search(r"欲知(?:后事|详情|究竟|端的|如何)|下回分解|且听下回|且看下回|"
                              r"请看下回|请听下回|请续看|请看续集", text) and ntok):
                tao_tokens_all.append(f"{ch:03d}[{pn}]×{ntok}")
            for mm in re.finditer(r"([〖⟦])([^\s〖〗⟦⟧]{1,80}?)([〗⟧])", text):
                ob, inner = mm.group(1), mm.group(2)
                code, rest = inner[0], inner[1:]
                disp, sep, note = rest.partition("|")
                if ob == "〖":
                    ce[code] = ce.get(code, 0) + 1
                else:
                    cv[code] = cv.get(code, 0) + 1
                if sep and code in no_pipe_codes:
                    pipe_issues.append(f"{ch:03d}[{pn}] 非 @/%/动词却挂管道：{mm.group(0)[:24]}")
                if ob == "〖" and code == "@" and sep:
                    canon = note
                    mapped_pn = pn_map.get((pn, disp))
                    if disp == canon:
                        pipe_issues.append(f"{ch:03d}[{pn}] 同名管道：{mm.group(0)[:24]}")
                    elif (mapped_pn or mapping_ch.get(disp)) and (mapped_pn or mapping_ch[disp]) != canon:
                        mapped = mapped_pn or mapping_ch[disp]
                        ok = (names_equivalent(canon, mapped, mapping_ch, display_map)
                              if names_equivalent is not None else
                              (canon == display_map.get(mapped) or display_map.get(canon) == mapped))
                        if ok:
                            # 展示层/规范层分层或别名归一（B-1/B-2）：展示名≠标注错，不计冲突
                            pipe_display_ok += 1
                        else:
                            pipe_issues.append(f"{ch:03d}[{pn}] 管道与映射表冲突："
                                               f"{disp}→{canon}（表内 {mapped}）")
                if ob == "〖" and code == "%" and sep and note not in ("时点", "时长", "年龄"):
                    pipe_issues.append(f"{ch:03d}[{pn}] % 标签越界：{mm.group(0)[:24]}")
        for k, v in ce.items():
            global_ent[k] = global_ent.get(k, 0) + v
        for k, v in cv.items():
            global_verb[k] = global_verb.get(k, 0) + v
        rows.append({"ch": ch, "chars": chars, "E": sum(ce.values()), "V": sum(cv.values()),
                     "R": tagged.count("〘"), "E100": round(sum(ce.values()) * 100 / chars, 2)
                     if chars else 0,
                     "V100": round(sum(cv.values()) * 100 / chars, 2) if chars else 0,
                     "ce": ce, "cv": cv})

    lines = [f"# 标注质量自检报告 ·《{args.book}》第 {args.chapters} 回", ""]
    lines.append("## 一、分回密度")
    lines.append("| 回 | 字数 | E | V | R | E/100字 | V/100字 | 实体分布 | 动词分布 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r.get("missing"):
            lines.append(f"| {r['ch']:03d} | — | — | — | — | — | — | 缺失 | 缺失 |")
            continue
        ed = " ".join(f"{k}{r['ce'].get(k, 0)}" for k in ENT_ORDER if r["ce"].get(k))
        vd = " ".join(f"{k}{r['cv'].get(k, 0)}" for k in VERB_ORDER if r["cv"].get(k))
        lines.append(f"| {r['ch']:03d} | {r['chars']} | {r['E']} | {r['V']} | {r['R']} | "
                     f"{r['E100']} | {r['V100']} | {ed} | {vd} |")
    ok = [r for r in rows if not r.get("missing")]
    if ok:
        tot_chars = sum(r["chars"] for r in ok)
        tot_e = sum(r["E"] for r in ok)
        tot_v = sum(r["V"] for r in ok)
        lines.append(f"| **合计** | {tot_chars} | {tot_e} | {tot_v} | "
                     f"{sum(r['R'] for r in ok)} | {round(tot_e*100/tot_chars, 2)} | "
                     f"{round(tot_v*100/tot_chars, 2)} | | |")
    lines += ["", "## 二、结构复验", "",
              f"- 剥标 != 底本：{len(struct_errs)} 段" + ("" if not struct_errs else
                                                          "：" + "；".join(struct_errs[:8])),
              f"- 全段无标注：{len(empty_paras)} 段" + ("" if not empty_paras else
                                                       "：" + "、".join(empty_paras[:12])),
              "", "## 三、边界规则（02ab §4.4 / 负规则十三）", "",
              f"- 回目行令牌：{title_tokens_total}（应为 0）",
              f"- 围栏内令牌：{len(fence_tokens_all)} 段（回末应 0；回末对/对联限实指）"
              + ("" if not fence_tokens_all else "：" + "、".join(fence_tokens_all[:10])),
              f"- 回末套语段令牌：{len(tao_tokens_all)} 段（应为 0）"
              + ("" if not tao_tokens_all else "：" + "、".join(tao_tokens_all[:10])),
              "", "## 四、管道审计", ""]
    if mapping_note:
        lines.append(f"- 映射来源（本次参数）：{mapping_note}")
    lines += [f"- 管道问题：{len(pipe_issues)} 处" + ("" if not pipe_issues else
                                                      "（前 20 条）"),
              f"- 展示层/规范层差异（display_canonical 白名单放行）：{pipe_display_ok} 处",
              ]
    for x in pipe_issues[:20]:
        lines.append(f"  - {x}")
    lines += ["", "## 五、类型分布（合计）", "",
              "| 实体类 | 计数 | 占比 |", "|---|---|---|"]
    te = sum(global_ent.values()) or 1
    for k in ENT_ORDER:
        lines.append(f"| {k} | {global_ent.get(k, 0)} | {round(global_ent.get(k,0)*100/te,1)}% |")
    lines.append("")
    tv = sum(global_verb.values()) or 1
    lines.append("| 动词域 | 计数 | 占比 |")
    lines.append("|---|---|---|")
    for k in VERB_ORDER:
        lines.append(f"| {k} | {global_verb.get(k, 0)} | {round(global_verb.get(k,0)*100/tv,1)}% |")
    text = "\n".join(lines) + "\n"
    out = Path(args.out) if args.out else (config.DIR_LOGS / "qa" /
                                           f"qa_{args.chapters.replace(',', '_')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(text)
    print(text[:2000])
    print(f"\n…报告全文：{out}")


if __name__ == "__main__":
    main()
