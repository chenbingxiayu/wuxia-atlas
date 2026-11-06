# -*- coding: utf-8 -*-
"""C18 · 已知实体别名补标扫描（武侠版，默认只出建议 TSV / 报告，不写 tagged）。

移植自 shiji-kb/scripts/scan_untagged_aliases.py（只读参考，2026-11-04），改动：
  1. 实体索引来源改 `registry/entities.json`（顶层 {version, generated, scope,
     status_legend, entities:[...]}；实体字段 id/type/canonical/aliases/contextual/
     sources/status/note），不再依赖 shiji 的 kg/entities/data/entity_index.json；
     aliases 里带「（旧称）/（称谓前缀）」注释者剥括号参与匹配；
     contextual（"卓兄/卓公子"等关系称谓）**不入索引**——01g 负规则二：纯礼貌/
     关系称呼不标人物，避免制造噪声。
  2. 符号解析统一走 `symbols.TOKEN_RE`（禁本地实体字符类），围栏/回目行整体掩码
     （按 symbols.FENCE_* 与 02ab 政策，默认不扫围栏与回末套语）。
  3. 泛称黑名单改 `wordlists/stopwords.json`（D09 词表），单字别名默认跳过；
     同一 alias 指向多 canonical 时告警并整体跳过（不猜）。
  4. 建议 TSV 与 `scripts/apply_annotation_patches.py`（C7）load_tsv 契约兼容：
     列 = 章节 / 全名 / 省称·词 / 位置 / 框架类型 / 匹配模式 / 上下文 / 实体类型
     （前 7 列必需；「省称·词」是单列，别名词放第 3 列，C7 的 parts[2]）。
  5. 默认只写 `registry/patches/<章节>_aliases.tsv` + `logs/aliases/` 报告；
     `--apply` 为可选上标动作（2026-11-05 P1 修复）：先备份，再按 TSV 的原文
     `位置` 精确插入（保护既有令牌/围栏块/标题行/回目），最后剥标逐回自检；
     缺 pos 的外部 TSV 退回"同词全插"但仍跳过保护区间。`--selftest` 为回归自检。
  6. 2026-11-05 P2-B 修复：无 pos 回退的"同词全插"额外做**长词保护**——`do_apply`
     把 `set(word_map)`（known_words）传入 `_apply_word`，若某位置存在更长的已知词
     以该词为前缀（如 known 含「武当派」时的「武当」），跳过该位置，避免产出
     `〖◆武当〗派` 这类切碎长词的令牌。pos 精确模式不变。

用法：
    python scripts/scan_untagged_aliases.py --book 白发魔女传 --all
    python scripts/scan_untagged_aliases.py --book 白发魔女传 --chapter 001
    python scripts/scan_untagged_aliases.py --book 白发魔女传 --all --types 人物 组织
    python scripts/scan_untagged_aliases.py --book 白发魔女传 --all --dry-run
    python scripts/scan_untagged_aliases.py --book 白发魔女传 --all --apply   # 本轮不执行

设计边界：只建议「已知实体（registry）的别名/正名」在未标注正文中的裸文出现，
不做新实体发现（那是 C16/词表与 C24 的职责），不改原文，不调 LLM。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config      # noqa: E402
import symbols     # noqa: E402
import masker      # noqa: E402

REGISTRY_PATH = config.DIR_REGISTRY / "entities.json"
STOPWORDS_PATH = config.DIR_WORDLISTS / "stopwords.json"
DEFAULT_OUT = None  # 运行时按书解析：config.patches_dir(args.book)（2026-11-05 子目录化）
LOG_DIR = config.DIR_LOGS / "aliases"

TSV_HEADER = ["章节", "全名", "省称/词", "位置", "框架类型", "匹配模式", "上下文", "实体类型"]
FRAME_TYPE = "词表匹配"
CONTEXT_RADIUS = 10
BACKUP_ROOT = config.ROOT / "backup" / "tagged"

# 括号注释：全名/别名里「（旧称）」「(称谓前缀)」等是说明而非字面词
_PAREN_NOTE_RE = re.compile(r"[（(][^（）()]*[）)]\s*$")
# 纯汉字数词（"二十""八十一"）：在武侠叙事里几乎都是数量/序数，误报率极高
_NUMERAL_RE = re.compile(r"^[零一二三四五六七八九十百千万亿两]+$")
# 回目/标题行（Markdown 标题，非正文；回目里的名称由结构层处理）
_HEADING_RE = re.compile(r"^\s{0,3}#")

# 类型过滤：code / symbols 中文名 / 常用同义词均可（同义词只做输入便利，输出仍用 15 类定版名）
TYPE_ALIASES = {"人名": "@", "官职": ";", "门派": "◆", "武功": "☆", "招式": "☆",
                "神兵": "•", "典籍": "{", "世家": "&"}


def clean_name(name: str) -> str:
    """剥掉名称尾部的括号说明；只留字面词。"""
    return _PAREN_NOTE_RE.sub("", (name or "").strip()).strip()


def load_stopwords(path: Path = STOPWORDS_PATH) -> set:
    """D09 泛称黑名单（wordlists/stopwords.json 的 surface 集）。"""
    if not path.exists():
        return set()
    data = json.loads(io.open(path, encoding="utf-8").read())
    items = data if isinstance(data, list) else data.get("items", [])
    words = set()
    for it in items:
        val = it.get("surface", "") if isinstance(it, dict) else str(it)
        clean = clean_name(val)
        if clean:
            words.add(clean)
    return words


def load_registry(path: Path = REGISTRY_PATH) -> tuple[list, dict]:
    """读 registry/entities.json，做结构校验与统计；返回 (entities, diagnostics)。

    结构契约（本层先读后信）：顶层 entities 列表；实体含 type/canonical/aliases/status。
    """
    if not path.exists():
        raise FileNotFoundError(f"实体登记表缺失：{path}")
    data = json.loads(io.open(path, encoding="utf-8").read())
    entities = data.get("entities")
    if not isinstance(entities, list):
        raise ValueError(f"{path} 顶层 entities 不是列表（实际 {type(entities).__name__}）")
    diag = {
        "version": data.get("version", ""),
        "generated": data.get("generated", ""),
        "scope": data.get("scope", ""),
        "status_legend": data.get("status_legend", ""),
        "total": len(entities),
        "type_dist": Counter(),
        "status_dist": Counter(),
        "missing_fields": [],
        "bad_type": [],
        "note_names": [],       # 带括号说明、已剥注释的条目
    }
    for ent in entities:
        eid = ent.get("id", "?")
        miss = [f for f in ("type", "canonical", "aliases", "status") if f not in ent]
        if miss:
            diag["missing_fields"].append({"id": eid, "missing": miss})
        code = ent.get("type", "")
        if code not in symbols.ENTITY_CODES:
            diag["bad_type"].append({"id": eid, "type": code})
        else:
            diag["type_dist"][code] += 1
        diag["status_dist"][ent.get("status", "")] += 1
        for field in ("canonical", "aliases"):
            vals = [ent.get(field)] if field == "canonical" else list(ent.get(field) or [])
            for val in vals:
                if isinstance(val, str) and _PAREN_NOTE_RE.search(val):
                    diag["note_names"].append({"id": eid, "field": field, "raw": val,
                                               "clean": clean_name(val)})
    return entities, diag


def build_word_map(entities: list, stopwords: set, min_len: int,
                   allow_single: bool, types: set | None) -> tuple[dict, dict]:
    """registry → {词: (canonical, type_code)}。

    返回 (word_map, report)，report 记录：词条数、被拦截项、跨实体歧义（同词多 canonical）。
    """
    word_map: dict[str, tuple[str, str]] = {}
    owner: dict[str, set] = defaultdict(set)
    ambiguous_words: set[str] = set()
    report = {"words": 0, "by_type": Counter(), "ambiguous": {}, "skipped_stop": [],
              "skipped_short": [], "skipped_type": 0, "contextual_ignored": 0}
    for ent in entities:
        code = ent.get("type", "")
        if types and code not in types:
            report["skipped_type"] += 1
            continue
        if code not in symbols.ENTITY_CODES:
            continue
        canonical = clean_name(ent.get("canonical", ""))
        report["contextual_ignored"] += len(ent.get("contextual") or [])
        names = [canonical] + [clean_name(a) for a in (ent.get("aliases") or [])]
        for word in names:
            if not word:
                continue
            if _NUMERAL_RE.match(word):
                report["skipped_stop"].append({"word": word, "reason": "纯数词"})
                continue
            if word in stopwords:
                report["skipped_stop"].append({"word": word, "reason": "stopwords 泛称"})
                continue
            if len(word) < min_len or (len(word) == 1 and not allow_single):
                report["skipped_short"].append({"word": word, "len": len(word)})
                continue
            if word in ambiguous_words:
                owner[word].add(canonical)
                continue
            if word in word_map and word_map[word][0] != canonical:
                owner[word].update({word_map[word][0], canonical})
                ambiguous_words.add(word)
                word_map.pop(word, None)          # 歧义词从索引移除，绝不猜
                continue
            word_map[word] = (canonical, code)
    for word, canonicals in sorted(owner.items()):
        report["ambiguous"][word] = sorted(canonicals)
    report["words"] = len(word_map)
    report["by_type"] = Counter(code for _, code in word_map.values())
    return word_map, report


def build_masked(text: str) -> str:
    """未标注正文掩码（等长，保偏移）：标注令牌 + 围栏块 + 标题行全部掩掉。

    围栏策略（symbols.FENCE_ENTITY_POLICY / 02ab §4.4）：本扫描默认整块跳过围栏
    （词/诗/歌/对联/回末对/回末/书信/告示/口诀/说书）与回末套语，保证建议只落在
    正文叙事区。
    2026-11-05 P3 修复（docs/47 §二轮）：补「回末套语段」负区域（欲知/下回分解/
    且听下回，与 accept_batch.TAO_RE 同口径）——套语段按负规则不标任何令牌；此前
    未加围栏的套语尾段不在此掩码内，--apply 曾据此把建议插进套语段（024/025 实例，
    accept 报 tao_token hard）。
    """
    masked = list(text)

    def blank(a: int, b: int) -> None:
        for i in range(a, b):
            masked[i] = "\ufffd"

    for m in symbols.TOKEN_RE.finditer(text):
        blank(m.start(), m.end())
    offset = 0
    in_fence = False
    for line in text.split("\n"):
        start, end = offset, offset + len(line)
        if symbols.FENCE_OPEN_RE.match(line):
            in_fence = True
            blank(start, end)
        elif symbols.is_fence_close(line):
            blank(start, end)
            in_fence = False
        elif in_fence or _HEADING_RE.match(line):
            blank(start, end)
        offset = end + 1
    # 回末套语段负区域（与 accept_batch TAO_RE 同口径）：定位命中并向两侧扩展到
    # 段落边界（兼容 \n\n 与 \r\n\r\n 行尾），整段掩码
    tao_re = getattr(symbols, "TAO_RE", None) or re.compile(r"欲知|下回分解|且听下回")
    for m in tao_re.finditer(text):
        a = text.rfind("\n\n", 0, m.start())
        a = 0 if a < 0 else a + 2
        b = text.find("\n\n", m.end())
        b = len(text) if b < 0 else b
        blank(a, b)
    return "".join(masked)


def scan_chapter(tagged_path: Path, matcher: dict, word_map: dict,
                 min_freq: int) -> list[dict]:
    """单回扫描：未标注正文中已知词的最长优先、不重叠命中 → 建议列表。"""
    text = io.open(tagged_path, encoding="utf-8").read()
    masked = build_masked(text)
    hits = masker.find_candidates(masked, matcher)
    per_word: dict[str, list[int]] = defaultdict(list)
    for word, start, _end in hits:
        per_word[word].append(start)
    suggestions = []
    for word, positions in per_word.items():
        if len(positions) < min_freq:
            continue
        canonical, code = word_map[word]
        for pos in positions:
            c0 = max(0, pos - CONTEXT_RADIUS)
            c1 = min(len(text), pos + len(word) + CONTEXT_RADIUS)
            suggestions.append({
                "chapter": tagged_path.name.split(".")[0],
                "canonical": canonical,
                "word": word,
                "pos": pos,
                "frame_type": FRAME_TYPE,
                "pattern": word,
                "context": text[c0:c1].replace("\n", "↵"),
                "entity_type": symbols.ENTITIES[code],
                "type_code": code,
            })
    suggestions.sort(key=lambda s: s["pos"])
    return suggestions


def write_tsv(path: Path, suggestions: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(TSV_HEADER)]
    for s in suggestions:
        lines.append("\t".join([
            s["chapter"], s["canonical"], s["word"], str(s["pos"]),
            s["frame_type"], s["pattern"], s["context"], s["entity_type"],
        ]))
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")


def chapter_numbers(book: str) -> list[int]:
    """按 config 的 tagged 文件枚举回号。"""
    nums = []
    for p in sorted(config.DIR_TAGGED.joinpath(book).glob("*.tagged.md")):
        stem = p.name.split(".")[0]
        if stem.isdigit():
            nums.append(int(stem))
    return nums


def write_report(out_dir: Path, book: str, params: dict, diag: dict, reg_report: dict,
                 all_suggestions: list[dict], chapters: list[int],
                 per_chapter: dict, skipped_stop_hits: Counter,
                 note_alias_words: set) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 子集扫描不覆盖全书报告（2026-11-04 Lead 修复）
    suffix = "" if params.get("chapters") in (None, "all") else \
        "_" + str(params["chapters"]).replace(",", "-").replace(" ", "")
    label = f"{book}{suffix}"
    total = len(all_suggestions)
    hit_chapters = sorted({s["chapter"] for s in all_suggestions})
    word_counter = Counter((s["word"], s["canonical"], s["entity_type"]) for s in all_suggestions)
    chapter_counter = Counter(s["chapter"] for s in all_suggestions)
    lines = [
        f"# C18 已知实体别名补标扫描报告 — {book}",
        "",
        f"- 生成时间：{stamp}",
        f"- 语料：`tagged/{book}/` 共 {len(chapters)} 回；扫描回数 {len(chapters)}",
        f"- 命令参数：{json.dumps(params, ensure_ascii=False)}",
        "- 写入范围：仅建议 TSV（`registry/patches/<回>_aliases.tsv`）与本报告；tagged 未改动"
        + ("；`--apply` 已开启（见文末）" if params.get("apply") else ""),
        "",
        "## 一、总览",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| registry 实体条数 | {diag['total']} |",
        f"| registry 版本 | {diag.get('version', '')}（{diag.get('generated', '')}） |",
        f"| 可匹配词条（正名+别名去重） | {reg_report['words']} |",
        f"| 有命中回数 | {len(hit_chapters)} / {len(chapters)} |",
        f"| 建议总数 | {total} |",
        f"| 命中词种 | {len(word_counter)} |",
        f"| 跨实体歧义词（跳过） | {len(reg_report['ambiguous'])} |",
        f"| registry 词条被 stopwords/数词拦截 | {len(reg_report['skipped_stop'])} |",
        f"| 短词拦截条目（<{params['min_len']} 字，单字默认跳过） | {len(reg_report['skipped_short'])} |",
        "",
        "## 二、分回命中",
        "",
        "| 回 | 建议数 | 词种（top5） |",
        "|---|---|---|",
    ]
    for ch in chapters:
        chs = f"{ch:03d}"
        n = chapter_counter.get(chs, 0)
        if not n:
            lines.append(f"| {chs} | 0 | —（无裸文别名/正名命中） |")
            continue
        words = Counter(s["word"] for s in per_chapter.get(chs, []))
        top = "、".join(f"{w}×{c}" for w, c in words.most_common(5))
        lines.append(f"| {chs} | {n} | {top} |")
    lines += [
        "",
        "## 三、命中词排行（前 30）",
        "",
        "| 词 | 全名 | 实体类型 | 次数 |",
        "|---|---|---|---|",
    ]
    for (word, canonical, etype), n in word_counter.most_common(30):
        lines.append(f"| {word} | {canonical} | {etype} | {n} |")
    lines += [
        "",
        "## 四、registry 校验与歧义告警",
        "",
        f"- 类型分布：" + "、".join(
            f"{symbols.ENTITIES.get(c, c)}×{n}" for c, n in sorted(diag["type_dist"].items())
        ),
        f"- status 分布：" + "、".join(f"{k}×{v}" for k, v in sorted(diag["status_dist"].items())),
        f"- 缺字段实体：{diag['missing_fields'] or '无'}",
        f"- 非法类型码实体：{diag['bad_type'] or '无'}",
        f"- 带括号说明的名称（已剥注释参与匹配）：{len(diag['note_names'])} 条",
    ]
    for item in diag["note_names"][:10]:
        lines.append(f"  - {item['id']}.{item['field']}：`{item['raw']}` → `{item['clean']}`")
    if reg_report["ambiguous"]:
        lines.append("- **跨实体歧义词（已整体跳过，需人工裁定 canonical）**：")
        for word, cans in reg_report["ambiguous"].items():
            lines.append(f"  - `{word}` → {cans}")
    else:
        lines.append("- 跨实体歧义词：无（全部 alias 唯一归属）")
    note_alias_hits = [s for s in all_suggestions if s["word"] in note_alias_words]
    if note_alias_hits:
        agg = Counter((s["word"], s["canonical"]) for s in note_alias_hits)
        lines += [
            "",
            "### 描述性旧称别名候选（01g 负规则一，需人工裁定）",
            "",
            "registry 中带「（旧称）/（称谓前缀）」注释的别名默认参与了匹配；"
            "这些词是描述性代称，按 01g 负规则一通常不标，**建议逐条人工裁定后再应用**：",
            "",
        ]
        for (word, canonical), n in agg.most_common():
            lines.append(f"- `{word}` → {canonical} ×{n}")
    lines += [
        "",
        "## 五、负规则与跳过说明",
        "",
        "- `contextual` 字段（如「卓兄/卓公子/练小姐」）按 01g 负规则二不入索引：",
        f"  本轮忽略 {reg_report['contextual_ignored']} 条关系/礼貌称谓，避免把称谓当实体补标。",
        "- 围栏块（词/诗/歌/对联/回末对/回末/书信/告示/口诀/说书）与 `#` 回目行整体跳过；",
        "  回末套语（「欲知后事如何…」）在围栏内，随之跳过。",
        "- 纯数词与 stopwords 泛称黑名单拦截条目见上表；单字词默认不扫（`--allow-single` 可放开）。",
        "",
        "### 被 stopwords 拦截的裸文出现（top10，仅说明未采纳量）",
        "",
    ]
    if skipped_stop_hits:
        for word, n in skipped_stop_hits.most_common(10):
            lines.append(f"- `{word}` ×{n}")
    else:
        lines.append("- 无")
    lines += [
        "",
        "## 六、输出文件与 C7 契约",
        "",
        f"- 建议 TSV：`registry/patches/<回>_aliases.tsv`（有命中回；表头 {len(TSV_HEADER)} 列，C7 契约）",
        "  - 列序：章节 / 全名 / 省称·词 / 位置 / 框架类型 / 匹配模式 / 上下文 / 实体类型；",
        "    与 `apply_annotation_patches.load_tsv` 对齐（word=第 3 列、entity_type=第 8 列）。",
        "  - 落标首选本脚本 `--apply`（精确插入+保护区+v1.8 管道纪律）；",
        "    C7 `apply_annotation_patches.py` 亦可消费（2026-11-05 起默认 dry-run、",
        "    --apply 才写盘、pos 精确定位优先），但其纯插入不带管道与保护区语义。",
        "  - 本脚本 `--apply` 另行遵守 v1.8 管道纪律：@ 类型写 `〖@别称|规范名〗`，",
        "    非 @ 类型只落显示串（`〖◆武当〗`），规范名归并交给 registry；",
        "    插入按 TSV `位置`（原文偏移）精确定位，并跳过令牌/围栏/标题保护区（P1 修复）。",
        f"- 本报告：`{Path(LOG_DIR.name) / f'{label}_alias_scan.md'}`",
        f"- 机读汇总：`{Path(LOG_DIR.name) / f'{label}_alias_scan.json'}`",
        "",
    ]
    report_path = LOG_DIR / f"{label}_alias_scan.md"
    io.open(report_path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    payload = {
        "book": book,
        "generated": stamp,
        "params": params,
        "registry": {"total": diag["total"], "version": diag["version"],
                     "words": reg_report["words"],
                     "type_dist": dict(diag["type_dist"]),
                     "status_dist": dict(diag["status_dist"]),
                     "ambiguous": reg_report["ambiguous"]},
        "summary": {"chapters": len(chapters), "hit_chapters": len(hit_chapters),
                    "suggestions": total, "word_kinds": len(word_counter)},
        "chapters": [{"chapter": f"{ch:03d}", "suggestions": chapter_counter.get(f"{ch:03d}", 0),
                      "words": dict(Counter(s["word"] for s in per_chapter.get(f"{ch:03d}", [])))}
                     for ch in chapters],
        "top_words": [{"word": w, "canonical": c, "type": t, "count": n}
                      for (w, c, t), n in word_counter.most_common(50)],
    }
    io.open(LOG_DIR / f"{label}_alias_scan.json", "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    return report_path


def load_suggestion_rows(path: Path) -> list[dict]:
    """读回本脚本生成的建议 TSV（C7 兼容列序），供 --apply 使用。"""
    rows = []
    type_to_code = {name: code for code, name in symbols.ENTITIES.items()}
    lines = io.open(path, encoding="utf-8").read().splitlines()
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        entity_type = parts[7]
        code = type_to_code.get(entity_type) or TYPE_ALIASES.get(entity_type)
        if code not in symbols.ENTITY_CODES:
            continue
        rows.append({"chapter": parts[0], "canonical": parts[1], "word": parts[2],
                     "pos": int(parts[3]) if parts[3].isdigit() else None,
                     "entity_type": entity_type, "type_code": code})
    return rows


def _tagged_ranges(text: str) -> set:
    covered = set()
    for m in symbols.TOKEN_RE.finditer(text):
        covered.update(range(m.start(), m.end()))
    return covered


def _token_text(word: str, code: str, canonical: str) -> str:
    """按 v1.8 管道纪律生成实体令牌（仅 @/% 可挂规范名管道）。"""
    body = f"{word}|{canonical}" if (code in ("@", "%") and canonical != word) else word
    return symbols.BRACKETS["entity"][0] + code + body + symbols.BRACKETS["entity"][1]


def _apply_word(text: str, word: str, code: str, canonical: str,
                pos: int | None = None,
                known_words: set | None = None) -> tuple[str, int]:
    """把未标注的 word 包成实体令牌（保护：既有令牌 / 围栏块 / 标题行 / 回目）。

    2026-11-05 P1 修复：
      - 指定 pos（C18 建议 TSV 的**原文偏移**）时只在该位置插入，先校验原文一致；
      - pos 缺失（外部 TSV）时退回"同词全插"，但仍跳过 `build_masked` 保护区间
        （令牌 + 围栏块 + 标题行；等长掩码，偏移与原文一致）。
    2026-11-05 P2-B 长词保护（仅无 pos 回退模式）：
      - known_words 中存在更长的词以 word 为前缀时（如 known 含「武当派」而 word
        为「武当」），该位置 `text.startswith(longer, i)` 则跳过，避免把长词切碎成
        `〖◆武当〗派`；pos 精确模式不变。
    """
    masked = build_masked(text)          # 令牌 + 围栏 + 标题 → \ufffd（等长）
    covered = _tagged_ranges(text)
    if pos is not None:
        if not (0 <= pos and text[pos:pos + len(word)] == word):
            return text, 0
        if any(j in covered for j in range(pos, pos + len(word))):
            return text, 0
        if any(masked[j] == "\ufffd" for j in range(pos, pos + len(word))):
            return text, 0
        token = _token_text(word, code, canonical)
        return text[:pos] + token + text[pos + len(word):], 1
    # 无 pos 回退：先算"以 word 为前缀的更长已知词"，命中处跳过
    longer_known = []
    if known_words:
        longer_known = sorted(
            (w for w in known_words
             if len(w) > len(word) and w.startswith(word)),
            key=len, reverse=True)
    positions = []
    start = 0
    while True:
        i = text.find(word, start)
        if i < 0:
            break
        start = i + 1
        if any(j in covered for j in range(i, i + len(word))):
            continue
        if any(masked[j] == "\ufffd" for j in range(i, i + len(word))):
            continue
        if longer_known and any(text.startswith(w2, i) for w2 in longer_known):
            continue
        positions.append(i)
    if not positions:
        return text, 0
    token = _token_text(word, code, canonical)
    chars = list(text)
    for i in sorted(positions, reverse=True):
        chars[i:i + len(word)] = list(token)
    return "".join(chars), len(positions)


def do_apply(book: str, tsv_paths: list[Path], known_words: set | None = None) -> dict:
    """可选上标：备份 → 按建议位置插入令牌 → 剥标/令牌数/逐行断言；失败回滚该回。

    2026-11-05 P1 修复：
      - 只按建议 TSV 的原文偏移 pos 插入（不再全词重插）→ 不会把词插进围栏/标题；
      - 外部 TSV 缺 pos 时退回"同词全插"，但仍跳过 build_masked 保护区间；
      - 备份名含 TSV 名（避免同章多 TSV 覆盖）；tsv 计数按文件。
    2026-11-05 P2-B 修复：known_words（= set(word_map)）传入 `_apply_word`，
      无 pos 回退模式下跳过"更长已知词前缀"位置（武当不切进武当派）。

    逐回校验：①剥标后正文一致；②新增令牌数 == 插入数；③所有行均已插入。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / book
    backup_dir.mkdir(parents=True, exist_ok=True)
    stats = {"tsv": 0, "chapters": 0, "inserted": 0, "rolled_back": []}
    for tsv in tsv_paths:
        rows = load_suggestion_rows(tsv)
        by_chapter: dict[str, list] = defaultdict(list)
        for row in rows:
            by_chapter[row["chapter"]].append(row)
        if not by_chapter:
            continue
        stats["tsv"] += 1
        for chapter, chapter_rows in sorted(by_chapter.items()):
            fpath = config.tagged_path(book, int(chapter))
            if not fpath.exists():
                stats["rolled_back"].append(f"{chapter}: tagged 缺失")
                continue
            old = io.open(fpath, encoding="utf-8").read()
            backup = backup_dir / f"{fpath.name}.{tsv.stem}.{stamp}.bak"
            io.open(backup, "w", encoding="utf-8", newline="\n").write(old)
            text = old
            inserted = 0
            failed = 0
            for row in sorted(chapter_rows, key=lambda r: -(r.get("pos") or 0)):
                text, n = _apply_word(text, row["word"], row["type_code"],
                                      row["canonical"], pos=row.get("pos"),
                                      known_words=known_words)
                inserted += n
                failed += 1 if n == 0 else 0
            old_tokens = len(list(symbols.TOKEN_RE.finditer(old)))
            new_tokens = len(list(symbols.TOKEN_RE.finditer(text)))
            problems = []
            if symbols.strip_markup(text) != symbols.strip_markup(old):
                problems.append("剥标后正文不一致")
            if new_tokens - old_tokens != inserted:
                problems.append(f"新增令牌 {new_tokens - old_tokens} ≠ 插入 {inserted}")
            if failed:
                problems.append(f"{failed} 行未插入（pos 失效/已标注/保护区）")
            if problems:
                io.open(fpath, "w", encoding="utf-8", newline="\n").write(old)
                stats["rolled_back"].append(f"{chapter}: {'；'.join(problems)}")
                continue
            io.open(fpath, "w", encoding="utf-8", newline="\n").write(text)
            stats["chapters"] += 1
            stats["inserted"] += inserted
    return stats


def selftest() -> int:
    """回归自检：①pos 模式保护围栏/标题/既有令牌；②全插模式长词保护（P2-B）。"""
    text = ("# [0] 标题行武当\n"
            "[1] 正文里武当派与掌门武当。\n"
            "::: 词\n武当在围栏内\n:::\n"
            "# 武当标题\n"
            "[2] 又见〖◆武当〗。\n")
    pos = text.index("掌门武当") + 2
    new, n = _apply_word(text, "武当", "◆", "武当派", pos=pos)
    ok1 = (n == 1 and symbols.strip_markup(new) == symbols.strip_markup(text)
           and "武当在围栏内" in new and "# 武当标题" in new
           and new.count("〖◆武当〗") == 2)
    # 无 known_words：保护区间内不插，正文两处（武当派 / 掌门武当）都插
    new2, n2 = _apply_word(text, "武当", "◆", "武当派")
    ok2 = (n2 == 2 and "武当在围栏内" in new2 and "# 武当标题" in new2
           and symbols.strip_markup(new2) == symbols.strip_markup(text))
    # P2-B 长词保护：known_words 含「武当派」时，全插模式不得产出「〖◆武当〗派」
    new3, n3 = _apply_word(text, "武当", "◆", "武当派",
                           known_words={"武当派", "武当"})
    ok3 = (n3 == 1 and "〖◆武当〗派" not in new3 and "武当派" in new3
           and new3.count("〖◆武当〗") == 2
           and symbols.strip_markup(new3) == symbols.strip_markup(text))
    # pos 精确模式不受长词保护影响（pos 指向独立「武当」时仍可插）
    new4, n4 = _apply_word(text, "武当", "◆", "武当派", pos=pos,
                           known_words={"武当派", "武当"})
    ok4 = (n4 == 1 and symbols.strip_markup(new4) == symbols.strip_markup(text))
    ok = ok1 and ok2 and ok3 and ok4
    print(f"SELFTEST: {'PASS' if ok else 'FAIL'}"
          f"（pos 模式 {n} 处；全插 {n2} 处；长词保护后全插 {n3} 处、"
          f"无「〖◆武当〗派」={'是' if '〖◆武当〗派' not in new3 else '否'}；"
          f"pos+known {n4} 处；围栏/标题均未插入）")
    return 0 if ok else 1


def normalize_types(values: list[str] | None) -> set | None:
    if not values:
        return None
    out = set()
    for v in values:
        if v in symbols.ENTITY_CODES:
            out.add(v)
        elif v in symbols.ENTITIES.values():
            out.update(c for c, n in symbols.ENTITIES.items() if n == v)
        elif v in TYPE_ALIASES:
            out.add(TYPE_ALIASES[v])
        else:
            raise SystemExit(f"[ERROR] 未知类型过滤值：{v}（可用码 {sorted(symbols.ENTITY_CODES)}"
                             f" 或名称 {sorted(set(symbols.ENTITIES.values()))}）")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="C18 已知实体别名补标扫描（默认只出建议 TSV/报告）")
    ap.add_argument("--book", default=config.PILOT_BOOK)
    group = ap.add_mutually_exclusive_group(required=False)
    group.add_argument("--chapter", help="单回（如 001 或 1）")
    group.add_argument("--all", action="store_true", help="全书")
    ap.add_argument("--selftest", action="store_true",
                    help="运行 apply 保护区间回归自检（不读 tagged）后退出")
    ap.add_argument("--min-len", type=int, default=2, help="参与匹配的最短词长（默认 2）")
    ap.add_argument("--min-freq", type=int, default=1, help="单回内最少出现次数（默认 1）")
    ap.add_argument("--types", nargs="+", help="只扫指定实体类型（码或中文名）")
    ap.add_argument("--out", default=None,
                    help="建议 TSV 输出目录（默认 registry/patches/<book>/）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写 TSV（tagged 永远不写）")
    ap.add_argument("--allow-single", action="store_true", help="允许单字别名参与匹配")
    ap.add_argument("--apply", action="store_true",
                    help="可选上标：备份后调用 C7 应用建议并剥标自检（默认不执行）")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.chapter and not args.all:
        ap.error("必须指定 --chapter 或 --all（或 --selftest）")

    if args.apply and args.dry_run:
        raise SystemExit("[ERROR] --apply 与 --dry-run 互斥")
    if args.min_freq < 1:
        raise SystemExit("[ERROR] --min-freq 必须 >= 1")

    entities, diag = load_registry()
    stopwords = load_stopwords()
    types = normalize_types(args.types)
    note_alias_words = {x["clean"] for x in diag["note_names"]
                        if x["field"] == "aliases" and x["clean"]}
    word_map, reg_report = build_word_map(entities, stopwords, args.min_len,
                                          args.allow_single, types)
    if not word_map:
        raise SystemExit("[ERROR] registry 未产出任何可匹配词条")
    matcher = masker.build_matcher(word_map)      # 最长优先、不重叠

    if args.chapter:
        chapters = [int(args.chapter)]
    else:
        chapters = chapter_numbers(args.book)
    if not chapters:
        raise SystemExit(f"[ERROR] 未找到 {args.book} 的 tagged 回目")

    params = {"book": args.book, "chapters": args.chapter or "all",
              "min_len": args.min_len, "min_freq": args.min_freq,
              "types": args.types, "dry_run": args.dry_run, "apply": args.apply,
              "allow_single": args.allow_single}
    print(f"registry：{diag['total']} 实体 / {reg_report['words']} 可匹配词条"
          f"（歧义 {len(reg_report['ambiguous'])}，拦截 {len(reg_report['skipped_stop'])}）")
    out_dir = Path(args.out) if args.out else config.patches_dir(args.book)
    out_dir.mkdir(parents=True, exist_ok=True)
    per_chapter: dict[str, list] = {}
    all_suggestions: list = []
    tsv_paths: list[Path] = []
    missing = []
    skipped_stop_hits = Counter()
    stop_matcher = masker.build_matcher(stopwords)

    for ch in chapters:
        fpath = config.tagged_path(args.book, ch)
        if not fpath.exists():
            missing.append(f"{ch:03d}")
            continue
        suggestions = scan_chapter(fpath, matcher, word_map, args.min_freq)
        text = io.open(fpath, encoding="utf-8").read()
        for word, _s, _e in masker.find_candidates(build_masked(text), stop_matcher):
            skipped_stop_hits[word] += 1
        if suggestions:
            per_chapter[f"{ch:03d}"] = suggestions
            all_suggestions.extend(suggestions)
            if not args.dry_run:
                tsv_path = out_dir / f"{ch:03d}_aliases.tsv"
                write_tsv(tsv_path, suggestions)
                tsv_paths.append(tsv_path)
            print(f"  {ch:03d}: {len(suggestions):4d} 条（词种 "
                  f"{len({s['word'] for s in suggestions})}）")
        else:
            print(f"  {ch:03d}: 0")

    if missing:
        print(f"  [WARN] 缺 tagged 的回：{missing}")
    report_path = write_report(out_dir, args.book, params, diag, reg_report,
                               all_suggestions, chapters, per_chapter, skipped_stop_hits,
                               note_alias_words)
    print(f"\n合计 {len(all_suggestions)} 条建议 / {len(chapters)} 回；报告：{report_path}")
    if args.dry_run:
        print("（dry-run：未写任何 TSV，tagged 未改动）")
    elif args.apply:
        stats = do_apply(args.book, tsv_paths, known_words=set(word_map))
        print(f"--apply：应用 {stats['tsv']} 个 TSV / {stats['chapters']} 回 / "
              f"插入 {stats['inserted']} 处；回滚 {stats['rolled_back'] or '无'}")
    else:
        print(f"（默认模式：已写建议 TSV 到 {out_dir}，tagged 未改动）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
