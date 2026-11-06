#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C24 · 实体对照表（concordance）构建 —— 武侠版

权威依据：docs/17 §2.2 C24（`build_entity_concordance`：砍 wiki 依赖、PREFIX_LABELS 补全 15 类）；
docs/05 §2.8（结构适配，~60 行改动）。移植自只读参考件
`shiji-kb/scripts/build_entity_concordance.py`（2026-11-04），相对原版的改动：

  1. 路径一律走 config（DIR_TAGGED / DIR_REGISTRY / PILOT_BOOK），CLI 增
     `--book/--chapters/--min-count`；
  2. 符号一律走 symbols：`PREFIX_LABELS` 直接取 `symbols.ENTITIES`（15 类），
     原版硬编码 11 类 + SKIP_PREFIXES 会静默丢掉 `◎☆{^%$` 中的多类；
  3. 砍掉 wiki 依赖（pages.json / redirect / has_page），登记对照改用
     `registry/entities.json`（本仓登记层唯一来源）；
  4. 归并键改为 **(type, canonical)**，并补齐：显示串变体、分回次数、章回分布、
     首次出现 PN 锚点（`书#pn-r{回}.{段}`）、管道映射统计、未登记实体清单；
  5. 输出 JSON + Markdown 双件（原版只有 JSON）。

口径（关键，详见 docs/_p2/C24-N3-report.md）：
  - 实体令牌一律 `symbols.TOKEN_RE` 定位 + `symbols.parse_token` 解析；类型码以
    `symbols.ENTITIES` 为唯一来源，脚本内不重写字符类（承 SKILL_01g 符号宪法）。
  - canonical：除 `%` 外，管道右侧即规范名（01g：`〖@显示名|规范名〗`）；
    `%` 的管道右侧是受控子标签（时点/时长/年龄，见 SKILL_02d §3 与
    `qa_annotation_report.py` 的 `%` 标签校验），故 `%` 的 canonical 取显示串，
    子标签另存 `subtype_tags`，避免把 586 个时点实体压成"时点"一个组。
  - 首次出现位置只用行内 PN `[N]`（02ab 两级 PN，本批实测 124 个一级 PN、无 [N.M]）。
    `# [0]` 是回目行、**不算正文段**：回目上的出现照计 total，但不作为 first；
    本批 32 回回目实测 0 个实体令牌（防御性保留该分支）。
  - 围栏（`::: 词/回末/回末对/…`）内正文照常计实体（实体层"限实指"由标注环节负责，
    本脚本只做索引不做语义裁剪）；围栏标记行不计 PN、不计样例位置。
  - "未登记实体"按 registry 自述 scope（人物/组织/家族 = @ ◆ &）判定：
    canonical 精确命中 → registered；命中 aliases/contextual → alias_mapped（单列）；
    其余 → unregistered（未登记清单）；scope 外 12 类单列 out_of_scope——
    地点→gazetteer（docs/14）、技艺/概念→词表（docs/13），不归本表。
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

try:  # Windows 控制台中文输出（scripts/README 约定 6）
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
except AttributeError:
    pass

import config  # noqa: E402
import symbols  # noqa: E402

# 行内 PN：[N]（一级）；[0]=回目（见 symbols.PN_TITLE / PN_MAX_LEVEL=2，本批无 [N.M]）
PN_RE = re.compile(r"^\[(\d+)\]")
TITLE_PREFIX = "# "          # 回目标题行形如 `# [0] 第一回　…`
TYPE_ORDER = "@◎=◆&~;#☆•+{^%$"          # 01g §2.2.1 定版顺序，仅用于报告排序
REGISTRY_FILE = "entities.json"
REGISTRY_SCOPE = {"@", "◆", "&"}          # registry/entities.json 的 scope 自述
TIME_TYPE = "%"                           # 管道右侧为受控子标签的特例（SKILL_02d §3）
PUNCT_RE = re.compile(r"[\s　，。？！、：；\"'“”‘’「」『』【】《》〈〉·…—～()（）\-]")


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def parse_chapters(spec: str | None, available: list[int]) -> list[int]:
    """回号过滤表达式 → 回号列表。

    支持 `all`/`None`（全部）与 `1-5,7,10-12`；越界回号照收（缺文件时在报告里标记）。
    非法输入（空段/非数字/`1-abc`/`a-b`/倒置区间/0 或负数）给友好 SystemExit，
    不抛裸 ValueError（task-12 修复，便于 pipeline 透传错误信息）。
    """
    if not spec or spec.strip().lower() == "all":
        return list(available)
    out: list[int] = []
    for i, part in enumerate(spec.split(","), 1):
        part = part.strip()
        if not part:
            raise SystemExit(
                f"✗ --chapters 第 {i} 段为空；示例：1-5,7,10-12（或 all）")
        if "-" in part:
            a, b = (x.strip() for x in part.split("-", 1))
            if not (a.isdigit() and b.isdigit()):
                raise SystemExit(
                    f"✗ --chapters 非法区间 {part!r}；只接受“正整数-正整数”，如 1-5")
            lo, hi = int(a), int(b)
            if lo <= 0 or hi <= 0:
                raise SystemExit(f"✗ --chapters 回号必须为正整数：{part!r}")
            if lo > hi:
                raise SystemExit(
                    f"✗ --chapters 区间起止倒置 {part!r}；应写 {hi}-{lo}")
            out.extend(range(lo, hi + 1))
        else:
            if not part.isdigit():
                raise SystemExit(
                    f"✗ --chapters 非法回号 {part!r}；只接受正整数，如 1,3,5")
            n = int(part)
            if n <= 0:
                raise SystemExit(f"✗ --chapters 回号必须为正整数：{part!r}")
            out.append(n)
    if not out:
        raise SystemExit("✗ --chapters 未解析出任何回号；示例：1-5,7（或 all）")
    return sorted(set(out))


def is_valid_name(name: str) -> bool:
    """名称有效性：非空且剥去标点/空白后仍有内容（原版 is_valid_name 口径）。"""
    return bool(name) and bool(PUNCT_RE.sub("", name).strip())


def chapter_title_map(book: str, chapters: list[int]) -> dict[int, str]:
    """从 tagged 的回目行 `# [0] 第一回　…` 提取回目（缺失时留空）。"""
    titles: dict[int, str] = {}
    for ch in chapters:
        p = config.tagged_path(book, ch)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith(TITLE_PREFIX) and "[0]" in line[:8]:
                titles[ch] = line.split("]", 1)[-1].strip()
                break
    return titles


# --------------------------------------------------------------------------- #
# 登记层（registry/entities.json）
# --------------------------------------------------------------------------- #
def load_registry() -> dict:
    """载入登记层 → {canonical, alias, meta}。

    canonical: {(type, canonical): entry}
    alias    : {(type, alias|contextual): entry}  （别名/上下文称谓 → 登记条目）
    """
    path = config.DIR_REGISTRY / REGISTRY_FILE
    if not path.exists():
        print(f"⚠ 未找到登记表 {path}，未登记判定将全部按 out_of_scope/unknown 处理")
        return {"path": str(path), "exists": False, "canonical": {}, "alias": {},
                "meta": {}, "total": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # task-12：登记表损坏不应中断对照表构建；按空登记表继续，
        # 输出仍然可用（scope @◆& 全部计 unregistered），并在报告/JSON 注明原因。
        print(f"⚠ 登记表 JSON 解析失败 {path}: {exc}；"
              f"按空登记表继续（@◆& 将全部计为 unregistered）")
        return {"path": str(path), "exists": True, "canonical": {}, "alias": {},
                "meta": {"error": f"JSONDecodeError: {exc}"}, "total": 0}
    # task-12 补充：兼容顶层为 list 的登记表（等价旧 schema 的 entries 列表），
    # 以及顶层 JSON 非 dict/list 的异常结构（降级空表并注明，不中断脚本）。
    if isinstance(data, list):
        entries, meta = data, {}
    elif isinstance(data, dict):
        entries = data.get("entities", [])
        meta = {k: data.get(k) for k in ("version", "generated", "scope",
                                         "status_legend")}
    else:
        print(f"⚠ 登记表顶层结构异常（{type(data).__name__}）{path}；"
              f"按空登记表继续（@◆& 将全部计为 unregistered）")
        return {"path": str(path), "exists": True, "canonical": {}, "alias": {},
                "meta": {"error": f"unexpected top-level {type(data).__name__}"},
                "total": 0}
    if not isinstance(entries, list):
        print(f"⚠ 登记表 entities 字段不是 list（{type(entries).__name__}）{path}；"
              f"按空登记表继续")
        return {"path": str(path), "exists": True, "canonical": {}, "alias": {},
                "meta": {"error": "entities is not a list"}, "total": 0}
    canonical: dict[tuple[str, str], dict] = {}
    alias: dict[tuple[str, str], dict] = {}
    for e in entries:
        key = (e.get("type"), e.get("canonical"))
        canonical[key] = e
        for a in (e.get("aliases") or []) + (e.get("contextual") or []):
            # 2026-11-06 修复（docs/70 §四）：兼容 docs/56 书级作用域 dict 注记条目
            # （{"display": ..., "book"/"books"/"chapters": ...}）——取 display 作别名；
            # concordance 仅做登记状态对照统计，书级限制不参与（同 accept_batch 语义）。
            name = a.get("display") if isinstance(a, dict) else a
            if name and name.strip():
                alias.setdefault((e.get("type"), name.strip()), e)
    return {
        "path": str(path), "exists": True,
        "canonical": canonical, "alias": alias,
        "meta": meta,
        "total": len(entries),
    }


def classify_registration(type_code: str, canonical: str, registry: dict) -> dict:
    """实体 → 登记状态：registered / alias_mapped / unregistered / out_of_scope。"""
    if type_code not in REGISTRY_SCOPE:
        return {"status": "out_of_scope",
                "note": "登记层 scope 仅人物/组织/家族；该类权威登记见 gazetteer/词表"}
    entry = registry["canonical"].get((type_code, canonical))
    if entry:
        return {"status": "registered", "id": entry.get("id"),
                "registry_canonical": entry.get("canonical"),
                "registry_status": entry.get("status")}
    entry = registry["alias"].get((type_code, canonical))
    if entry:
        return {"status": "alias_mapped", "id": entry.get("id"),
                "registry_canonical": entry.get("canonical"),
                "registry_status": entry.get("status")}
    return {"status": "unregistered"}


# --------------------------------------------------------------------------- #
# 扫描与归并
# --------------------------------------------------------------------------- #
def scan_entity_tokens(book: str, chapters: list[int]):
    """逐回扫描实体令牌 → (occurrences, skipped, missing, scanned_files)。

    occurrence = 一次实体出现（保留位置以便推锚点与追溯）。
    """
    occurrences: list[dict] = []
    skipped: Counter = Counter()
    skipped_examples: list[str] = []
    missing: list[int] = []
    scanned_files: list[str] = []
    order = 0

    for ch in chapters:
        path = config.tagged_path(book, ch)
        if not path.exists():
            missing.append(ch)
            continue
        scanned_files.append(str(path))
        cur_pn: int | None = None          # 当前段 PN；None=尚未进入正文
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith(TITLE_PREFIX):
                # 回目行固定 [0]：照扫（防御性），但 [0] 不参与首次出现判定
                cur_pn = 0
            elif symbols.fence_opens(line) or symbols.is_fence_close(line):
                continue                    # 围栏标记行既不是 PN 也不是样例正文
            else:
                m = PN_RE.match(line)
                if m:
                    cur_pn = int(m.group(1))
                # 无 PN 的续行（韵文/回末对多行）沿用上一条 PN——本批实测 0 例，
                # 但 02ab 允许多行围栏，保留继承以免换书后丢位置。
            if cur_pn is None:
                continue
            for tm in symbols.TOKEN_RE.finditer(line):
                layer, code, body, display, note, err = symbols.parse_token(tm.group(0))
                if layer != "entity" or err is not None:
                    continue
                if code not in symbols.ENTITIES:
                    skipped["类型码不在15类"] += 1
                    if len(skipped_examples) < 10:
                        skipped_examples.append(f"{ch:03d}:{line_no} {tm.group(0)}")
                    continue
                display = (display or "").strip()
                if not display or not is_valid_name(display):
                    skipped["显示串为空/非名称"] += 1
                    if len(skipped_examples) < 10:
                        skipped_examples.append(f"{ch:03d}:{line_no} {tm.group(0)}")
                    continue
                if code == TIME_TYPE:
                    # % 管道右值是受控子标签（时点/时长/年龄），不是规范名
                    canonical, subtype = display, (note or "").strip() or None
                else:
                    canonical = (note or "").strip() or display
                    subtype = None
                if not is_valid_name(canonical):
                    skipped["规范名为空/非名称"] += 1
                    if len(skipped_examples) < 10:
                        skipped_examples.append(f"{ch:03d}:{line_no} {tm.group(0)}")
                    continue
                order += 1
                occurrences.append({
                    "order": order,
                    "type": code,
                    "canonical": canonical,
                    "display": display,
                    "subtype": subtype,
                    "chapter": ch,
                    "para": cur_pn,
                    "line": line_no,
                    "pipe": bool(note and note.strip()),
                    "token": tm.group(0),
                })

    return occurrences, skipped, skipped_examples, missing, scanned_files


def aggregate(occurrences: list[dict], registry: dict, book: str) -> list[dict]:
    """按 (type, canonical) 归并 → 实体条目列表（保持首次出现顺序）。"""
    groups: "OrderedDict[tuple[str, str], dict]" = OrderedDict()
    for occ in occurrences:
        key = (occ["type"], occ["canonical"])
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "type": occ["type"],
                "type_label": symbols.ENTITIES[occ["type"]],
                "canonical": occ["canonical"],
                "total": 0,
                "chapter_counts": Counter(),
                "variants": Counter(),
                "subtype_tags": Counter(),
                "pipe_occurrences": 0,
                "first": None,
                "last": None,
                "first_rank": len(groups) + 1,
            }
        g["total"] += 1
        g["chapter_counts"][occ["chapter"]] += 1
        g["variants"][occ["display"]] += 1
        if occ["subtype"]:
            g["subtype_tags"][occ["subtype"]] += 1
        if occ["pipe"]:
            g["pipe_occurrences"] += 1
        # 首次出现：[0] 回目不算正文段（02ab 回目行固定 [0]）
        if occ["para"] and occ["para"] > 0:
            if g["first"] is None or (occ["chapter"], occ["para"], occ["line"]) < (
                    g["first"]["chapter"], g["first"]["para"], g["first"]["line"]):
                g["first"] = {
                    "chapter": occ["chapter"],
                    "para": occ["para"],
                    "line": occ["line"],
                    "loc": f"{occ['chapter']}:{occ['para']}",
                    "anchor": symbols.ANCHOR_FMT.format(
                        book=book, chapter=occ["chapter"], para=occ["para"]),
                }
        g["last"] = {"chapter": occ["chapter"], "para": occ["para"]}

    entities: list[dict] = []
    for (type_code, canonical), g in groups.items():
        registration = classify_registration(type_code, canonical, registry)
        variants = [{"display": d, "count": c, "is_canonical": d == canonical}
                    for d, c in g["variants"].most_common()]
        entities.append({
            "canonical": canonical,
            "type": type_code,
            "type_label": g["type_label"],
            "total": g["total"],
            "first_rank": g["first_rank"],
            "chapter_count": len(g["chapter_counts"]),
            "chapter_counts": [{"chapter": ch, "count": c}
                               for ch, c in sorted(g["chapter_counts"].items())],
            "first": g["first"],
            "last": g["last"],
            "variants": variants,
            "variant_count": len(variants),
            "piped": g["pipe_occurrences"] > 0,
            "pipe_occurrences": g["pipe_occurrences"],
            "subtype_tags": ([{"tag": t, "count": c}
                              for t, c in g["subtype_tags"].most_common()]
                             if g["subtype_tags"] else []),
            "registration": registration,
        })
    return entities


def build_type_counts(entities: list[dict]) -> dict:
    """逐类统计（15 类全列，0 也保留，便于报告稳定列）。"""
    out: dict[str, dict] = {}
    for code in TYPE_ORDER:
        label = symbols.ENTITIES[code]
        subset = [e for e in entities if e["type"] == code]
        reg = Counter(e["registration"]["status"] for e in subset)
        out[code] = {
            "label": label,
            "entities": len(subset),
            "occurrences": sum(e["total"] for e in subset),
            "unique_displays": len({v["display"] for e in subset for v in e["variants"]}),
            "registered": reg.get("registered", 0),
            "alias_mapped": reg.get("alias_mapped", 0),
            "unregistered": reg.get("unregistered", 0),
            "out_of_scope": reg.get("out_of_scope", 0),
        }
    return out


# --------------------------------------------------------------------------- #
# Markdown 报告
# --------------------------------------------------------------------------- #
def render_md(result: dict) -> str:
    book = result["book"]
    lines: list[str] = []
    add = lines.append
    totals = result["summary"]
    type_counts = result["type_counts"]
    entities = result["entities"]
    registry = result["registry"]

    add(f"# 实体对照表（concordance）·《{book}》")
    add("")
    add(f"- 生成时间：{result['generated']}")
    add(f"- 数据来源：`tagged/{book}/NNN.tagged.md` 共 {result['chapter_count']} 回"
        f"（{result['chapters'][0]:03d}–{result['chapters'][-1]:03d}）"
        if result["chapters"] else "- 数据来源：无")
    add(f"- 生成脚本：`scripts/build_entity_concordance.py`（C24，移植自 shiji 同名脚本）")
    add(f"- 符号体系：`symbols.py` v{result['spec_version']}；15 类实体码 "
        f"`{' '.join(TYPE_ORDER)}`")
    add(f"- 归并键：(类型码, 规范名)；合计 **{totals['entity_count']:,}** 个实体、"
        f"**{totals['total_occurrences']:,}** 次出现；解析跳过 {totals['skipped']} 个令牌")
    add("")
    add("> 口径：管道右侧除 `%` 外取为规范名（`〖@显示名|规范名〗`）；`%` 的管道右侧是"
        "受控子标签（时点/时长/年龄），其 canonical 取显示串。首次出现位置用行内 PN "
        "推 `书#pn-r{回}.{段}`；`[0]` 回目不算正文段。")
    add("")

    # 一、逐类统计
    add("## 一、逐类统计")
    add("")
    add("| 类型 | 符号 | 实体数 | 出现数 | 出现占比 | 唯一显示串 | 已登记 | 别名映射 | 未登记 | 范围外 |")
    add("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    total_occ = totals["total_occurrences"] or 1
    for code in TYPE_ORDER:
        v = type_counts[code]
        pct = 100 * v["occurrences"] / total_occ
        add(f"| {v['label']} | 〖{code}〗 | {v['entities']:,} | {v['occurrences']:,} | "
            f"{pct:.2f}% | {v['unique_displays']:,} | {v['registered']:,} | "
            f"{v['alias_mapped']:,} | {v['unregistered']:,} | {v['out_of_scope']:,} |")
    add("")
    add(f"**合计**：{totals['entity_count']:,} 个实体 · {totals['total_occurrences']:,} 次出现 · "
        f"{sum(v['unique_displays'] for v in type_counts.values()):,} 个显示串"
        f"（分类型去重求和，同一写法跨类重复计入）")
    add("")

    # 二、TOP 实体
    add("## 二、TOP 30 实体（按出现次数）")
    add("")
    add("| # | 类型 | 规范名 | 出现 | 回数 | 显示串变体 | 首次出现 |")
    add("|---:|---|---|---:|---:|---:|---|")
    top = sorted(entities, key=lambda e: (-e["total"], e["first_rank"]))[:30]
    for i, e in enumerate(top, 1):
        first = e["first"]
        first_s = f"`{first['anchor']}`" if first else "—（仅回目）"
        add(f"| {i} | {e['type_label']} | {e['canonical']} | {e['total']:,} | "
            f"{e['chapter_count']} | {e['variant_count']} | {first_s} |")
    add("")

    # 三、显示串变体
    add("## 三、显示串变体 TOP 20（规范名 ≠ 显示串）")
    add("")
    add("| 规范名 | 类型 | 总出现 | 变体数 | 变体示例（出现数） |")
    add("|---|---|---:|---:|---|")
    variant_entities = sorted(
        (e for e in entities if any(not v["is_canonical"] for v in e["variants"])),
        key=lambda e: -e["total"])
    for e in variant_entities[:20]:
        variants = [v for v in e["variants"] if not v["is_canonical"]][:4]
        sample = "、".join(f"{v['display']}({v['count']})" for v in variants)
        add(f"| {e['canonical']} | {e['type_label']} | {e['total']:,} | "
            f"{e['variant_count']} | {sample} |")
    add("")
    pipe_entities = sum(1 for e in entities if e["piped"])
    add(f"> 全书含管道映射的实体 {pipe_entities:,} 个、管道出现 "
        f"{sum(e['pipe_occurrences'] for e in entities):,} 次；上表仅列有别名变体者")
    add("")

    # 四、章回分布
    add("## 四、分回分布")
    add("")
    add("| 回 | 回目 | 实体出现 | 唯一实体 | 累计 |")
    add("|---:|---|---:|---:|---:|")
    per_ch: dict[int, list[dict]] = {}
    for e in entities:
        for cc in e["chapter_counts"]:
            per_ch.setdefault(cc["chapter"], []).append((e["canonical"], cc["count"]))
    cum = 0
    titles = result["chapter_titles"]
    for ch in result["chapters"]:
        rows = per_ch.get(ch, [])
        occ = sum(c for _, c in rows)
        cum += occ
        add(f"| {ch:03d} | {titles.get(str(ch), '')} | {occ:,} | {len(rows):,} | {cum:,} |")
    add("")

    # 五、登记对照与未登记清单
    add("## 五、登记对照与未登记实体清单")
    add("")
    add(f"- 登记表：`{registry['path']}`（version={registry['meta'].get('version')}，"
        f"generated={registry['meta'].get('generated')}，共 {registry['total']} 条）")
    add(f"- 登记 scope：{registry['meta'].get('scope')}")
    if registry["meta"].get("error"):
        add(f"- ⚠ **登记表解析失败**：{registry['meta']['error']}；本报告按空登记表输出，"
            f"@◆& 全部计为 unregistered（见 §5.1）。修复 `registry/entities.json` 后复跑。")
    add(f"- 对照结果：登记范围内实体 {totals['in_scope_entities']:,} 个 → "
        f"registered {totals['registered_entities']:,} · "
        f"alias_mapped {totals['alias_mapped_entities']:,} · "
        f"**unregistered {totals['unregistered_entities']:,}**")
    add(f"- registry {registry['total']} 条中被语料命中 "
        f"**{totals['registry_hit']}** 条"
        + (f"；未被使用：{'、'.join(result['registry_unused'])}"
           if result["registry_unused"] else ""))
    add("")
    add("### 5.1 未登记实体（scope=@◆&，canonical 未在 registry）")
    add("")
    if result["unregistered"]:
        add("| # | 类型 | canonical | 出现 | 回数 | 首次出现 | 说明 |")
        add("|---:|---|---|---:|---:|---|---|")
        for i, e in enumerate(sorted(result["unregistered"],
                                      key=lambda x: -x["total"]), 1):
            first = e["first"]["anchor"] if e["first"] else "—"
            add(f"| {i} | {e['type_label']} | {e['canonical']} | {e['total']:,} | "
                f"{e['chapter_count']} | `{first}` | 待登记（或需别名归并） |")
    else:
        add("（无）")
    add("")
    add("### 5.2 别名/上下文称谓可映射（canonical 未直登，但 registry aliases/contextual 命中）")
    add("")
    if result["alias_mapped"]:
        add("| 类型 | canonical（语料） | 映射至 registry canonical | 出现 | 首次出现 |")
        add("|---|---|---|---:|---|")
        for e in sorted(result["alias_mapped"], key=lambda x: -x["total"]):
            first = e["first"]["anchor"] if e["first"] else "—"
            add(f"| {e['type_label']} | {e['canonical']} | "
                f"{e['registration'].get('registry_canonical')} | {e['total']:,} | `{first}` |")
    else:
        add("（无）")
    add("")
    add("### 5.3 登记范围外类型（scope 仅 @◆&）")
    add("")
    add("| 类型 | 符号 | 实体数 | 出现数 | 权威登记去向 |")
    add("|---|---|---:|---:|---|")
    outside_note = {
        "=": "gazetteer（docs/14）", "☆": "词表/招式表（docs/13）",
        "^": "词表（docs/13）", "%": "时间体系（docs/09）",
        "•": "神兵谱/器物表（docs/13）", "{": "文书表（docs/13）",
        "$": "数量词表（wordlists/quantity）", ";": "职衔表（docs/13）",
        "#": "身份分类树（docs/12）", "+": "生物表（docs/13）",
        "◎": "群组（随 @ 登记）", "~": "族群表（docs/13）",
    }
    for code in TYPE_ORDER:
        if code in REGISTRY_SCOPE:
            continue
        v = type_counts[code]
        add(f"| {v['label']} | 〖{code}〗 | {v['entities']:,} | {v['occurrences']:,} | "
            f"{outside_note.get(code, '词表')} |")
    add("")

    # 六、管道与 % 子标签
    add("## 六、管道映射与时间子标签")
    add("")
    add(f"- 管道映射实体：{pipe_entities:,} 个；含别名变体的实体："
        f"{sum(1 for e in entities if any(not v['is_canonical'] for v in e['variants'])):,} 个")
    time_entities = [e for e in entities if e["type"] == TIME_TYPE]
    tag_counter: Counter = Counter()
    for e in time_entities:
        for t in e["subtype_tags"]:
            tag_counter[t["tag"]] += t["count"]
    if tag_counter:
        add(f"- `%` 时间实体 {len(time_entities):,} 个（canonical=显示串，未按子标签归并）；"
            f"子标签分布：" + "、".join(f"{t} {c:,}" for t, c in tag_counter.most_common()))
    add("")

    # 七、已知局限
    add("## 七、已知局限")
    add("")
    add("1. 只做**形式归并**，不做语义归并：显示串不同、管道未连接的两个写法会留在两个条目里"
        "（如 `◆武当` 已由管道归到 `武当派`，但 `◆少林` 未接管道）。")
    add("2. `%` 实体未按时间子标签拆分/归并（子标签是受控标签而非规范名），"
        "时间语义归 N4 时间轴消费。")
    add("3. 未登记判定只覆盖 registry scope（@◆&）；地点/器物等由 gazetteer/词表负责，"
        "本表 5.3 仅给规模。")
    add("4. 首次出现基于行内 PN；若换书后出现多行围栏且续行无 PN，已按上一 PN 继承，"
        "尚无样本验证。")
    add("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="C24 · 实体对照表构建（武侠版）",
        formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--book", default=config.PILOT_BOOK, help="书名（默认试点书）")
    ap.add_argument("--chapters", default="all",
                    help="回号过滤，如 1-5,7（默认 all=该书全部 tagged）")
    ap.add_argument("--out", type=Path, default=None,
                    help="输出目录（默认 config.DIR_REGISTRY/concordance）")
    ap.add_argument("--min-count", type=int, default=1,
                    help="最小出现次数，低于此值的实体不输出（默认 1）")
    args = ap.parse_args()

    book = args.book
    tagged_dir = config.DIR_TAGGED / book
    if not tagged_dir.is_dir():
        print(f"✗ 标注目录不存在：{tagged_dir}")
        return 1
    available = sorted(int(p.stem.split(".")[0]) for p in tagged_dir.glob("*.tagged.md"))
    if not available:
        print(f"✗ {tagged_dir} 下没有 *.tagged.md")
        return 1
    chapters = parse_chapters(args.chapters, available)

    registry = load_registry()
    occurrences, skipped, skipped_examples, missing, scanned_files = scan_entity_tokens(
        book, chapters)
    entities = aggregate(occurrences, registry, book)
    scanned_entity_count = len(entities)
    scanned_occurrences = len(occurrences)
    if args.min_count > 1:
        entities = [e for e in entities if e["total"] >= args.min_count]
        for i, e in enumerate(entities, 1):
            e["first_rank"] = i

    type_counts = build_type_counts(entities)
    in_scope = [e for e in entities if e["type"] in REGISTRY_SCOPE]
    registered = [e for e in in_scope if e["registration"]["status"] == "registered"]
    alias_mapped = [e for e in in_scope if e["registration"]["status"] == "alias_mapped"]
    unregistered = [e for e in in_scope if e["registration"]["status"] == "unregistered"]
    registry_hit = len({e["registration"]["id"] for e in registered})
    registry_unused = sorted(
        f"{e.get('type')} {e.get('canonical')}" for e in registry["canonical"].values()
        if e.get("id") not in {x["registration"]["id"] for x in registered})

    result = {
        "book": book,
        "generated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "spec_version": symbols.SPEC_VERSION,
        "source": "tagged/<book>/NNN.tagged.md",
        "anchor_format": symbols.ANCHOR_FMT,
        "chapters": chapters,
        "chapter_count": len(scanned_files),
        "chapter_titles": {str(k): v for k, v in
                           chapter_title_map(book, chapters).items()},
        "missing_chapters": missing,
        "spec": {
            "group_key": "(type, canonical)",
            "canonical_rule": "管道右侧为规范名；% 例外（管道右值为受控子标签，canonical=显示串）",
            "first_location": "行内 PN [N] → 书#pn-r{回}.{段}；[0] 回目不算正文段",
        },
        "summary": {
            "entity_count": len(entities),
            "total_occurrences": sum(e["total"] for e in entities),
            "scanned_entities": scanned_entity_count,
            "scanned_occurrences": scanned_occurrences,
            "skipped": sum(skipped.values()),
            "in_scope_entities": len(in_scope),
            "registered_entities": len(registered),
            "alias_mapped_entities": len(alias_mapped),
            "unregistered_entities": len(unregistered),
            "registry_hit": registry_hit,
        },
        "registry": {
            "path": registry["path"], "exists": registry["exists"],
            "total": registry["total"], "meta": registry["meta"],
            "scope_types": sorted(REGISTRY_SCOPE),
        },
        "registry_unused": registry_unused,
        "type_counts": type_counts,
        "unregistered": unregistered,
        "alias_mapped": alias_mapped,
        "entities": entities,
        "skipped": dict(skipped),
        "skipped_examples": skipped_examples,
    }

    out_dir = args.out or (config.DIR_REGISTRY / "concordance")
    out_dir.mkdir(parents=True, exist_ok=True)
    # 子集扫描不得覆盖全书产物：章节过滤时文件名加范围后缀（2026-11-04 Lead 修复）
    suffix = "" if chapters == available else \
        (f"_{chapters[0]:03d}-{chapters[-1]:03d}" if chapters else "_empty")
    json_path = out_dir / f"{book}{suffix}.json"
    md_path = out_dir / f"{book}{suffix}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    md_path.write_text(render_md(result), encoding="utf-8")

    s = result["summary"]
    print(f"✓ 扫描 {len(scanned_files)} 回 {scanned_occurrences:,} 次实体出现 → "
          f"{scanned_entity_count:,} 个 (类型, 规范名) 组")
    print(f"✓ 输出实体 {s['entity_count']:,} 个（--min-count≥{args.min_count}）· "
          f"出现 {s['total_occurrences']:,} 次")
    print(f"✓ 登记对照：scope @◆& 实体 {s['in_scope_entities']:,} · registered "
          f"{s['registered_entities']:,} · alias_mapped {s['alias_mapped_entities']:,} · "
          f"unregistered {s['unregistered_entities']:,}")
    print(f"✓ registry {registry['total']} 条命中 {s['registry_hit']} 条"
          + (f"；未使用 {len(registry_unused)} 条" if registry_unused else ""))
    if missing:
        print(f"⚠ 缺失回：{missing}")
    if skipped:
        print(f"⚠ 跳过令牌：{dict(skipped)}")
    print(f"✓ 写入 {json_path}")
    print(f"✓ 写入 {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
