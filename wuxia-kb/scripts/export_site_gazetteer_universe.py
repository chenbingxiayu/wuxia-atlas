# -*- coding: utf-8 -*-
"""EX-7 · `export_site_gazetteer_universe.py` — gazetteer / universe / atlas 薄导出器

定位（docs/51 §三 EX-7，阶段 2）：
  消费 N7 迁移后的 `registry/gazetteer.json`（650 条，nature/kind/layer/precision/lat/lng/
  unlocatable/books）+ 只读 `kb/系列谱系考订表.json`（lines/chronology_spine/interchange_seeds/
  open_questions）+ 旧站 `site/data/atlas/*.json`（经纬度/章节键只读参考），按 site/data
  2026-11-02 契约导出三件：
    1) `gazetteer.json`  —— meta + places（id/name/aliases/kind/real/lat/lng/precision/verified/books）
    2) `universe.json`   —— meta + lines/chronology_spine/interchange_seeds/open_questions
    3) `atlas/<书>.json` —— meta/title/era/era_conf/chapters/persons/places/bychap/events（5 书）
  桥接期 Astro 38 页零改动；新增字段允许，旧字段不缺（docs/51 §五）。

数据口径：
  - gazetteer：N7 的 `loc_mode=coord` 619 条（旧站契约 places 仅含可落点条目）→ 站点坐标层；
    另 31 条 unlocatable（loc_mode=none）不入坐标层，清单写 meta.field_gaps 与本报告；
    kind 用 N7 §2.3 十三值新口径；real 沿用 N7 兼容派生列（nature=未定 → null）。
  - universe：四节数据来自 `kb/系列谱系考订表.json` 只读快照（人工考订权威数据）。
  - atlas：新数据来自 tagged 实体令牌（bychap 逐回 p/l）、registry/concordance（persons）、
    N7 gazetteer（places 坐标层）、kb/作品元数据表（era/era_conf）；旧站 atlas 只读参考用于
    「章节键/人物键/地点键」兜底（契约要求旧键不缺，docs/51 §五"不得静默丢弃"）；
    **事件层 events 无新管线产物（D03/EX-5 未上线），4 书沿用旧站冻结事件表并显式声明**，
    冰魄寒光剑 events={} 并写 meta.field_gaps（不伪造）。
  - tagged/struct/concordance/registry/kb 全部只读；只写 logs/export（staging+报告）。

CLI：默认 dry-run（只写 staging+reports）；`--apply` 由 export_site_common 统一处理（本任务
     明确不执行 --apply site/data，由 Lead 收口）。
用法：python scripts/export_site_gazetteer_universe.py [--apply]
      python scripts/export_site_gazetteer_universe.py --scope tianshan-demo   # 天山 7 书裁剪口径

W0-T3a（天山演示版总体方案 §1.2，2026-11-08）scope 口径：
  - gazetteer：places 按 scope 书目出现过滤（books ∩ scope 为空者不入表），books 键裁到 scope；
  - atlas/<书>.json：仅产 scope 书切片；
  - universe.json：lines 成员裁剪（book ∈ scope）与编年谱裁剪（books ∩ scope）；
  - 全量口径（不带 --scope）行为与现状完全一致（方案 R6）。

W0-T4（天山演示版总体方案 §〇/§1.2，2026-11-08；用户裁定）scope 口径增量：
  - universe.lines：tianshan-demo 重建为**单线**「天山系列」（色沿用 #c0392b），成员 = 7 部
    用户裁定顺序（散花女侠→联剑风云录→白发魔女传→塞外奇侠传→七剑下天山→冰魄寒光剑→
    江湖三女侠；散花/联剑自原「明代系列」并入），成员字段自原 lines join（照搬），
    order 按演示顺序重排、order_conf=「用户裁定 2026-11-08」（order/evidence 缺失 → user_ruling）；
    其他 profile 保持通用成员裁剪（W0-T3a 口径）。
  - interchange_seeds：行经书 ∩ scope 非空者保留 + **canonical 映射**（对照 EX-2 产物
    characters.json 的 canonical/display/别名；命中 → seed.canonical，失败 → 保持纯文本，
    universe 页已支持降级）；tianshan-demo 另新增 4 条演示种子（霍天都/凌云凤=天山派创派、
    易兰珠/吕四娘=演示覆盖；note 为原创编辑内容 L0，不含原文引文）。
  - open_questions：关涉书 ⊆ scope 的悬案保留（关涉书由悬案文本与全书目字符串匹配）。
  - chronology_spine：books ∩ scope（缺佚星标 `*` 按裸名归书，星标保留——W0-T4 修正）。
  - **atlas/state.json 接管**：EX-7 产出（scope=7 书演示顺序；全量=BOOKS 契约顺序等价全量版），
    消费键兼容 MapTrail.tsx Manifest（meta.note + books[].slug/title/chapters/era/era_conf/leads）
    与 build_qa_index.select_titles（books[].title）；父仓 scripts/build_atlas_slices.py 加废弃
    标注（不删文件）。

D2（线路导读接线，宇宙页重构设计 §4.2，2026-11-10）：
  - 消费人工编辑轨 `kb/校订/线路导读.tsv`（仅 status=校定 行；draft 静默跳过；文件缺失 →
    {} 不阻塞——线路导读是可选增强），挂载为 universe lines[].reading_guide =
    {start, peak, skip, note?}（前端 site/src/pages/universe/index.astro guideRows 消费键：
    入坑起点/巅峰之作/可跳过三槽位 + note；无内容不渲染行，全空隐藏区块）。
  - 线名按基名匹配（guide_line_key：去尾部「（…）」括注）——全量口径线「天山系列（清代主脉）」
    与演示口径线「天山系列」消费同一行：reading_guide 是"线"属性，两口径都生效
    （方案 R6 由 D2 增补：全量口径 lines 也带 reading_guide，测试固化）。
  - 槽位书名必须 ∈ 该线成员书，否则**降级丢弃该槽位**（选降级不选报错：站外书不得渲染死链，
    前端对缺槽有降级；演示口径下旧稿 peak=云海玉弓缘即由此降级）。
  - 同线重复校定行 → ReadingGuideError（唯一真源导出闸门，同 load_intro_tsv 口径）。
  - 挂载只发生在导出产物层（全量口径 lines 先浅拷贝再挂），不改写只读源数据。
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from datetime import datetime
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import export_site_common as esc  # noqa: E402

ROOT = config.ROOT
KB = config.LEGACY_KB
SITE_DATA = esc.SITE_DATA
REG_GAZETTEER = ROOT / "registry" / "gazetteer.json"
CONC_DIR = ROOT / "registry" / "concordance"
TAGGED_DIR = ROOT / "tagged"
EXPORTER = "EX-7 export_site_gazetteer_universe"

# 新管线书单（旧站 atlas 契约只有前 4 书；2026-11-07 扩书 P1-P3 批次补齐 15 书）
# 注意：前 4 书顺序是旧站契约基线，不要重排；其余 11 书一律追加在末尾。
BOOKS = ["七剑下天山", "塞外奇侠传", "江湖三女侠", "白发魔女传", "冰魄寒光剑",
         "冰川天女传", "还剑奇情录", "萍踪侠影录", "散花女侠", "云海玉弓缘",
         "冰河洗剑录", "联剑风云录", "广陵剑", "风雷震九州", "侠骨丹心",
         "剑网尘丝", "幻剑灵旗", "大唐游侠传", "龙凤宝钗缘", "慧剑心魔",
         "飞凤潜龙", "草莽龙蛇传", "龙虎斗京华", "绝塞传烽录"]
CONTRACT_BOOKS = BOOKS[:4]

# ---------------------------------------------------------------- W0-T4 演示口径常量
# 用户裁定 2026-11-08：天山演示版宇宙 = 单条线路，线名沿用「天山系列」（方案 §〇）。
# 成员顺序 = config/site_scope.json tianshan-demo.books 顺序（散花女侠→…→江湖三女侠）。
DEMO_PROFILE = "tianshan-demo"
DEMO_LINE_NAME = "天山系列"
DEMO_LINE_COLOR = "#c0392b"          # 原天山线色（kb/系列谱系考订表.json lines[0].color）
ORDER_RULING = "用户裁定 2026-11-08"
ORDER_RULING_SHORT = "user_ruling"

# 演示新增种子（W0-T4；note 为原创编辑内容 L0，不含原文引文）：
#   霍天都/凌云凤 = 天山派创派（行经书按用户裁定 = 散花女侠/联剑风云录/白发魔女传）；
#   易兰珠/吕四娘 = 演示种子必覆盖人物（源考订表无此二人的种子；行经书取 scope 内主战场书）。
DEMO_NEW_SEEDS_START = [
    {"name": "霍天都", "books": ["散花女侠", "联剑风云录", "白发魔女传"],
     "note": "天山派创派开山祖师：创派之志始于散花女侠，天山剑法大成开宗于联剑风云录，"
             "白发魔女传中以天都居士身份收岳鸣珂为徒"},
    {"name": "凌云凤", "books": ["散花女侠", "联剑风云录", "白发魔女传"],
     "note": "天山派创派同侪、霍天都之道侣：自散花女侠并肩创派，联剑风云录共成天山剑法"},
]
DEMO_NEW_SEEDS_END = [
    {"name": "易兰珠", "books": ["塞外奇侠传", "七剑下天山", "江湖三女侠"],
     "note": "天山派第四代传人：杨云骢遗孤，七剑下天山主角之一，至江湖三女侠犹为天山派尊长"
             "（霍天都→岳鸣珂→凌未风→易兰珠四代传承）"},
    {"name": "吕四娘", "books": ["江湖三女侠"],
     "note": "江湖三女侠主角：雍正朝侠女，天山演示线的终点人物"},
]

# 换乘站种子名可能是「展示名（规范名）」复合串（如 晦明禅师（岳鸣珂））——括注两侧都参与解析。
PAREN_NAME_RE = re.compile(r"^(.+?)（(.+?)）$")

# D2 线路导读（宇宙页重构设计 §4.2）：人工编辑轨唯一真源；仅校定行入站（draft 不入站，
# 同 作品简介/武功评语 编辑流程口径）；note ≤40 字为编辑闸门口径（前端一句导读）。
GUIDE_TSV = KB / "校订" / "线路导读.tsv"
GUIDE_STATUS = "校定"
GUIDE_SLOTS = ("start", "peak", "skip")     # 入坑起点 / 巅峰之作 / 可跳过（前端三槽位）
GUIDE_SOURCE = ("kb/校订/线路导读.tsv（仅 status=校定 行，线名基名匹配挂载 lines[].reading_guide；"
                "槽位书名须 ∈ 线成员书，站外降级；D2 2026-11-10）")

TOKEN_RE = re.compile(r"〖([^〖〗]+)〗")
PN_PARA_RE = re.compile(r"^\[(\d+)\] ")

# 冰魄寒光剑无旧站 atlas 契约：用同构 signature 做 diff（顶层字段 + 4 张 dict 的键集合不预置）
ATLAS_SYNTH_SCHEMA = {
    "type": "dict",
    "keys": {
        "meta": {"type": "dict", "keys": {"generated": {"type": "str"},
                                          "schema": {"type": "str"},
                                          "book": {"type": "str"},
                                          "copyright": {"type": "str"}}},
        "title": {"type": "str"},
        "era": {"type": "str"},
        "era_conf": {"type": "str"},
        "chapters": {"type": "int"},
        "persons": {"type": "dict", "keys": {}},
        "places": {"type": "dict", "keys": {}},
        "bychap": {"type": "dict", "keys": {}},
        "events": {"type": "dict", "keys": {}},
    },
}


# ---------------------------------------------------------------- 基础工具
def load_json(p: Path):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def sort_chaps(nums) -> list:
    return sorted({int(n) for n in nums if n is not None})


# ---------------------------------------------------------------- 数据源装载
def load_sources() -> dict:
    src = {}
    src["gazetteer"] = load_json(REG_GAZETTEER) if REG_GAZETTEER.exists() else {"places": []}
    src["series"] = load_json(KB / "系列谱系考订表.json")
    src["works"] = load_json(KB / "作品元数据表.json")
    src["works_by_book"] = {w.get("book"): w for w in src["works"].get("works", [])
                            if w.get("book")}
    src["conc"] = {}
    for b in BOOKS:
        p = CONC_DIR / f"{b}.json"
        src["conc"][b] = load_json(p) if p.exists() else {"entities": []}
    src["old_gazetteer"] = esc.load_site("gazetteer.json")
    src["old_universe"] = esc.load_site("universe.json")
    src["old_atlas"] = {}
    for b in CONTRACT_BOOKS:
        src["old_atlas"][b] = esc.load_site(f"atlas/{b}.json")
    # tagged 实体令牌（逐书逐回）：{book: {chapter: {"p": [@canonical], "l": [non-@ canonical]}}}
    tagged = {}
    for b in BOOKS:
        d = TAGGED_DIR / b
        per_ch = {}
        if d.is_dir():
            for fp in sorted(d.glob("*.tagged.md")):
                try:
                    ch = int(fp.name[:3])
                except ValueError:
                    continue
                persons, others = [], []
                seen_p, seen_o = set(), set()
                for line in open(fp, encoding="utf-8"):
                    for m in TOKEN_RE.finditer(line):
                        body = m.group(1)
                        if not body:
                            continue
                        code, rest = body[0], body[1:]
                        # 管道右侧为规范名；% 例外（右侧是受控子标签，canonical=显示串，
                        # 见 registry/concordance spec.canonical_rule 与 symbols.parse_token）
                        canon = (rest.split("|")[0] if code == "%"
                                 else rest.split("|")[-1]).strip()
                        if not canon:
                            continue
                        if code == "@":
                            if canon not in seen_p:
                                seen_p.add(canon)
                                persons.append(canon)
                        else:
                            if canon not in seen_o:
                                seen_o.add(canon)
                                others.append(canon)
                per_ch[ch] = {"p": persons, "l": others}
        tagged[b] = per_ch
    src["tagged"] = tagged
    return src


# ---------------------------------------------------------------- gazetteer.json
def build_gazetteer(src: dict, scope=None) -> tuple[dict, dict]:
    """gazetteer.json payload（W0-T3a：scope 口径下 places 按出现书目过滤——books ∩ scope
    为空者不入表，books 键裁到 scope；全量口径不变）。"""
    reg = src["gazetteer"]
    all_places = reg.get("places") or []
    coord = [p for p in all_places if p.get("loc_mode") == "coord"]
    unlocatable = [p for p in all_places if p.get("loc_mode") == "none"]
    books = (reg.get("meta", {}).get("books") or [])[:4]
    old_meta = (src["old_gazetteer"] or {}).get("meta", {})
    old_places = {p["id"]: p for p in (src["old_gazetteer"] or {}).get("places", [])}

    places, n_old_fallback, n_new = [], 0, 0
    for p in sorted(coord, key=lambda x: x["id"]):
        rec_books = p.get("books") or {}
        if scope is not None:
            rec_books = {b: v for b, v in rec_books.items() if esc.in_scope(b, scope)}
            if not rec_books:
                continue          # scope 内无出现的地名不入表（方案 §1.2：按 scope 书目出现过滤）
        rec = {
            "id": p["id"],
            "name": p.get("name") or p["id"],
            "aliases": list(p.get("aliases") or []),
            "kind": p.get("kind"),
            "real": p.get("real"),
            "lat": p.get("lat"),
            "lng": p.get("lng"),
            "precision": p.get("precision"),
            "verified": bool(p.get("verified")),
            "books": rec_books,
        }
        old = old_places.get(p["id"])
        if old:
            # 旧站字段兜底（aliases/precision 值等），新值优先
            if not rec["aliases"] and old.get("aliases"):
                rec["aliases"] = list(old["aliases"])
        else:
            n_new += 1
        places.append(rec)
    n_old_fallback = len(places) - n_new
    field_gaps = [
        f"unlocatable {len(unlocatable)} 条（loc_mode=none，含风砂堡/木什塔克/喀沁草原等）"
        f"不进入站点坐标层 places（旧契约 places 619 条=有坐标条目）；清单见 "
        f"registry/gazetteer.json meta.stats 与 EX-7 报告。渲染端 D3 降级由下游决定（SKILL §3.6）。",
        "kind 采用 N7 §2.3 十三值归一（旧站为 OSM/中文脏值混用）；旧 kind 原值见 "
        "registry/gazetteer.json 各条 source.legacy_kind。",
        "real 为 N7 nature 兼容派生列：真实→true / 虚构·原型改造→false / 未定→null（迁移暂定，待复核）。",
    ]
    payload = {
        "meta": {
            "generated": esc.today(),
            "rev": reg.get("meta", {}).get("rev", 1),
            "coord_system": reg.get("meta", {}).get("coord_system",
                                                   old_meta.get("coord_system", "WGS-84(EPSG:4326)")),
            "based_on": {
                "books": list(books or old_meta.get("based_on", {}).get("books", [])),
                "retrieval": old_meta.get("based_on", {}).get(
                    "retrieval", "Nominatim(OSM) + 人工坐标拾取器核验"),
            },
            "tsv_rulings": old_meta.get("tsv_rulings", "kb\\校订\\gazetteer-考订.tsv"),
            "tsv_seeds": old_meta.get("tsv_seeds", "kb\\校订\\gazetteer-seeds.tsv"),
            "strict": False,
            "source": "registry/gazetteer.json（N7 迁移，nature/kind/layer 新口径）",
            "field_gaps": field_gaps,
        },
        "places": places,
    }
    if scope is not None:
        payload["meta"]["scope"] = scope["profile"]
        payload["meta"]["field_gaps"].append(
            f"scope 口径（{scope['profile']}）：places 按 scope 书目出现过滤（books ∩ scope 为空者"
            "不入表），books 键裁到 scope。")
    stats = {"old": len(old_places), "new": len(places), "coord": len(coord),
             "unlocatable": len(unlocatable), "new_places": n_new,
             "legacy_matched": n_old_fallback}
    return payload, stats


# ---------------------------------------------------------------- universe.json
def load_canonical_index() -> dict | None:
    """canonical/别名对照索引（W0-T4 · 方案 A2）：读 EX-2 产物 characters.json，构建
    「表层名 → canonical」与「canonical → 出现书目」两张表（type=@ 人物实体）。

    读取顺序：staging/characters.json（EX-7 在 export_site_all 序列中后于 EX-2 运行，取同批
    staging 产物）→ site/data/characters.json（单跑 EX-7 且 staging 缺失时的兜底）。两处皆缺或
    结构不符 → None（种子保持纯文本，universe 页已支持降级）。同名首见优先：entities 按频次
    降序，高频实体（= 更可能的主档）先入表。只读，不写任何源目录。
    """
    for label, path in (("staging", esc.STAGING / "characters.json"),
                        ("site/data", SITE_DATA / "characters.json")):
        if not path.exists():
            continue
        try:
            data = esc.load_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        ents = data.get("entities") if isinstance(data, dict) else None
        if not isinstance(ents, list):
            continue
        by_name, books_of = {}, {}
        for e in ents:
            if e.get("type") != "@":
                continue
            canon = e.get("canonical")
            if not canon:
                continue
            names = {canon}
            disp = e.get("display")
            if isinstance(disp, str) and disp:
                names.add(disp)
            books = e.get("books") if isinstance(e.get("books"), dict) else {}
            for bv in books.values():
                aliases = bv.get("aliases") if isinstance(bv, dict) else None
                if isinstance(aliases, dict):
                    names.update(a for a in aliases if isinstance(a, str) and a)
                elif isinstance(aliases, list):
                    names.update(a for a in aliases if isinstance(a, str) and a)
            for n in names:
                by_name.setdefault(n, canon)
            books_of.setdefault(canon, list(books.keys()))
        return {"by_name": by_name, "books_of": books_of, "source": label}
    return None


def resolve_seed_canonical(name, index: dict | None, scope=None) -> str | None:
    """种子名 → canonical（W0-T4 · 方案 A2）。

    解析顺序：种子名全串 → 括注外名 → 括注内名（「晦明禅师（岳鸣珂）」两截都可能命中
    canonical/展示名/别名）。命中后再做 scope 出现门：canonical 在 scope 书目内无出现则不产
    canonical（避免指向演示站不存在的页）。任一步失败 → None（种子保持纯文本，页面已降级）。
    """
    if not index or not isinstance(name, str):
        return None
    name = name.strip()
    if not name:
        return None
    cands = [name]
    m = PAREN_NAME_RE.match(name)
    if m:
        cands += [m.group(1).strip(), m.group(2).strip()]
    by_name, books_of = index.get("by_name") or {}, index.get("books_of") or {}
    for cand in cands:
        canon = by_name.get(cand)
        if not canon:
            continue
        books = books_of.get(canon) or []
        if scope is not None and not any(esc.in_scope(b, scope) for b in books):
            continue
        return canon
    return None


# ---------------------------------------------------------------- 线路导读（D2）
class ReadingGuideError(ValueError):
    """线路导读.tsv 非法（同线重复校定行），消息中文，导出即报错（唯一真源闸门）。"""


def guide_line_key(name) -> str:
    """线名匹配键（D2）：去尾部「（…）」括注——全量口径线「天山系列（清代主脉）」与
    演示口径线「天山系列」归一同键，同一导读行两口径通用。非字符串/空 → ""。"""
    s = str(name).strip() if isinstance(name, str) else ""
    return re.sub(r"（[^（）]*）$", "", s).strip()


def load_reading_guide(path: Path | None = None) -> dict:
    """D2：读 kb/校订/线路导读.tsv → {线名基名: {line, start?, peak?, skip?, note?}}。

    - 仅 status=校定 行入站；draft/待校 行静默跳过（编辑流程分批校定，未校定行不进站点）；
    - 文件不存在 → {}（线路导读是可选增强，不阻塞导出；前端全空隐藏区块）；
    - 同线（基名）重复校定行 → ReadingGuideError（唯一真源，同 load_intro_tsv 口径）；
    - 值字段去首尾空白，空值字段不产键。
    """
    path = path or GUIDE_TSV
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    guide: dict = {}
    for i, row in enumerate(rows, start=2):      # 行号从表头下一行起（报错定位友好）
        line = (row.get("line") or "").strip()
        if not line or (row.get("status") or "").strip() != GUIDE_STATUS:
            continue
        key = guide_line_key(line)
        if key in guide:
            raise ReadingGuideError(
                f"线路导读.tsv 第 {i} 行：{line} 重复校定行（唯一真源，只允许一行）")
        rec = {"line": line}
        for k in GUIDE_SLOTS + ("note",):
            v = (row.get(k) or "").strip()
            if v:
                rec[k] = v
        guide[key] = rec
    return guide


def attach_reading_guide(lines: list, guide: dict) -> dict:
    """D2：按线名基名匹配挂载 reading_guide 到 lines（就地修改；返回统计）。

    - 匹配键 = guide_line_key（去「（…）」括注）：reading_guide 是"线"属性，全量口径
      「天山系列（清代主脉）」与演示口径「天山系列」消费同一行（方案 R6 由 D2 增补）；
    - 槽位书名 ∈ 该线成员书才挂载，否则**降级丢弃该槽位**（选降级不选报错：站外书不得渲染
      死链，前端对缺槽有降级渲染；演示口径旧稿 peak=云海玉弓缘即由此降级）；
    - 三槽位全空且 note 空 → 整行不挂载（宇宙页"无内容不渲染行"，全空隐藏区块）。
    统计：reading_guide_attached（挂载线数）/ reading_guide_dropped_slots（降级槽位数）。
    """
    stats = {"reading_guide_attached": 0, "reading_guide_dropped_slots": 0}
    for ln in lines:
        row = guide.get(guide_line_key(ln.get("line")))
        if not row:
            continue
        members = {m.get("book") for m in (ln.get("members") or [])}
        rec, dropped = {}, []
        for k in GUIDE_SLOTS:
            v = row.get(k)
            if not v:
                continue
            if v in members:
                rec[k] = v
            else:
                dropped.append(v)
        if row.get("note"):
            rec["note"] = row["note"]
        if not rec:                                   # 无内容不渲染行（前端全空隐藏）
            continue
        ln["reading_guide"] = rec
        stats["reading_guide_attached"] += 1
        stats["reading_guide_dropped_slots"] += len(dropped)
    return stats


def _demo_line(series: dict, scope: dict) -> dict:
    """演示单线（W0-T4 用户裁定）：单线「天山系列」，成员按 scope 书目顺序 join 原 lines 数据。

    成员字段照搬原线数据（散花/联剑自「明代系列」join）；order 按演示顺序重排 1..7；
    order_conf = 「用户裁定 2026-11-08」，order/evidence 缺失时置 user_ruling；书目完全不在
    任何线（合成数据兜底）→ 最小成员占位（missing=True）。
    """
    src_member = {}
    for ln in series.get("lines") or []:
        for m in ln.get("members") or []:
            b = m.get("book")
            if b and b not in src_member:
                src_member[b] = m
    members = []
    for i, book in enumerate(scope.get("books") or [], start=1):
        m = src_member.get(book)
        if not m:
            members.append({"book": book, "order": i, "conf": ORDER_RULING_SHORT,
                            "order_conf": ORDER_RULING_SHORT, "missing": True})
            continue
        rec = dict(m)
        joined = rec.get("order") is not None and bool(rec.get("evidence"))
        rec["order"] = i
        rec["order_conf"] = ORDER_RULING if joined else ORDER_RULING_SHORT
        members.append(rec)
    return {"line": DEMO_LINE_NAME, "color": DEMO_LINE_COLOR,
            "order_basis": ORDER_RULING, "members": members}


def _trim_spine(sp: dict, scope: dict) -> dict:
    """编年谱单段 books ∩ scope（W0-T3a + W0-T4 修正）：缺佚星标 `*` 按裸名归书，星标保留。"""
    books = []
    for b in (sp.get("books") or []):
        clean = b[:-1] if isinstance(b, str) and b.endswith("*") else b
        if esc.in_scope(clean, scope):
            books.append(b)
    return dict(sp, books=books)


def _question_book_candidates(src: dict, series: dict) -> list:
    """悬案文本归书的候选书名（全集 = 谱系表 lines 成员书 ∪ 作品元数据表书目；长名优先）。"""
    names = set()
    for ln in series.get("lines") or []:
        for m in ln.get("members") or []:
            if m.get("book"):
                names.add(m["book"])
    names.update(str(b) for b in (src.get("works_by_book") or {}))
    return sorted(names, key=lambda x: (-len(x), x))


def _question_in_scope(text, candidates: list, scope: dict) -> bool:
    """悬案是否保留（W0-T4）：关涉书 ⊆ scope 才保留；无法归书（无命中）保守保留。"""
    if not isinstance(text, str):
        return True
    related = [b for b in candidates if b in text]
    return all(esc.in_scope(b, scope) for b in related)


def build_universe(src: dict, scope=None, canon_index=None,
                   guide: dict | None = None) -> tuple[dict, dict]:
    """universe.json payload（kb/系列谱系考订表.json 只读快照）。

    全量口径（scope=None）：四节与源数据逐字段一致（方案 R6；**D2 增补**：lines 挂载
    reading_guide——"线"属性人工编辑轨，两口径都消费同一行，其余字段仍逐字段一致）。

    W0-T4（天山演示版总体方案 §〇/§1.2，2026-11-08）scope 口径：
      1) lines：tianshan-demo 重建单线「天山系列」（用户裁定 2026-11-08 顺序；散花/联剑自
         明代系列并入，成员字段 join 照搬，order 重排 + order_conf=用户裁定）；其他 profile
         保持通用成员裁剪（W0-T3a：book ∈ scope，裁空的趋势线整条不产出）。
      2) chronology_spine：每段 books ∩ scope（缺佚星标按裸名归书），裁空的时段不产出。
      3) interchange_seeds：行经书 ∩ scope 非空者保留 + canonical 映射（canon_index 命中 →
         seed.canonical，失败 → 保持纯文本）；tianshan-demo 另新增 4 条演示种子
         （霍天都/凌云凤 置首 = 系列起点，易兰珠/吕四娘 收尾 = 演示覆盖；note 原创 L0）。
      4) open_questions：关涉书 ⊆ scope 的条目保留（无法归书者保守保留）。

    D2（2026-11-10）：lines[].reading_guide 挂载（线名基名匹配；槽位书名 ∈ 线成员书，
    站外降级；guide=None → 读 kb/校订/线路导读.tsv 校定行，测试可注入合成 guide）。
    """
    series = src["series"]
    lines = series.get("lines", [])
    spine = series.get("chronology_spine", [])
    n_lines_src, n_spine_src = len(lines), len(spine)
    seeds_src = series.get("interchange_seeds", [])
    oq_src = series.get("open_questions", [])

    if scope is not None:
        is_demo = scope.get("profile") == DEMO_PROFILE
        # 1) lines
        if is_demo:
            lines = [_demo_line(series, scope)]
        else:
            lines = [dict(ln, members=[m for m in (ln.get("members") or [])
                                       if esc.in_scope(m.get("book"), scope)])
                     for ln in lines]
            lines = [ln for ln in lines if ln["members"]]
        # 2) chronology_spine
        spine = [_trim_spine(sp, scope) for sp in spine]
        spine = [sp for sp in spine if sp["books"]]
        # 3) interchange_seeds：行经书 ∩ scope 过滤 + canonical 映射 + 演示新增
        kept = []
        for s in seeds_src:
            if not any(esc.in_scope(b, scope) for b in (s.get("books") or [])):
                continue
            s = dict(s)
            canon = resolve_seed_canonical(s.get("name"), canon_index, scope)
            if canon:
                s["canonical"] = canon
            kept.append(s)
        seeds_out = kept
        n_new_seeds = 0
        if is_demo:
            new_seeds = []
            for tpl in DEMO_NEW_SEEDS_START + DEMO_NEW_SEEDS_END:
                s = dict(tpl)
                canon = resolve_seed_canonical(s["name"], canon_index, scope)
                if canon:
                    s["canonical"] = canon
                new_seeds.append(s)
            n_new_seeds = len(new_seeds)
            seeds_out = new_seeds[:len(DEMO_NEW_SEEDS_START)] + kept + \
                new_seeds[len(DEMO_NEW_SEEDS_START):]
        n_canonical = sum(1 for s in seeds_out if s.get("canonical"))
        # 4) open_questions：关涉书 ⊆ scope
        cands = _question_book_candidates(src, series)
        oq_out = [q for q in oq_src if _question_in_scope(q, cands, scope)]
    else:
        lines = [dict(ln) for ln in lines]      # D2：浅拷贝再挂 reading_guide（源数据只读）
        spine, seeds_out, oq_out = spine, seeds_src, oq_src
        n_new_seeds, n_canonical = 0, 0

    # D2：线路导读挂载（线名基名匹配，两口径通用；guide=None → 读人工编辑轨 TSV 校定行）
    if guide is None:
        guide = load_reading_guide()
    rg_stats = attach_reading_guide(lines, guide)

    payload = {
        "meta": {
            "generated": esc.today(),
            "schema": "site-universe-v1",
            "source": "kb/系列谱系考订表.json（只读；人工考订）",
            "field_gaps": [],
        },
        "lines": lines,
        "chronology_spine": spine,
        "interchange_seeds": seeds_out,
        "open_questions": oq_out,
    }
    if scope is not None:
        gaps = payload["meta"]["field_gaps"]
        gaps.append(f"scope 口径（{scope['profile']}，W0-T4）：chronology_spine books ∩ scope "
                    f"（{n_spine_src}→{len(spine)} 段；缺佚星标 * 按裸名归书、星标保留）。")
        if scope.get("profile") == DEMO_PROFILE:
            gaps.append(
                f"lines 重建为单线「{DEMO_LINE_NAME}」（{n_lines_src} 线→1 线；"
                f"{ORDER_RULING}）：成员 = {'→'.join(scope.get('books') or [])}（散花/联剑自"
                "原「明代系列」并入），成员字段自原 lines join（照搬），order 按演示顺序重排、"
                f"order_conf={ORDER_RULING}（order/evidence 缺失 → {ORDER_RULING_SHORT}）。")
        else:
            gaps.append(f"lines 成员裁剪（book ∈ scope，{n_lines_src}→{len(lines)} 条，"
                        "裁空的趋势线不产出；通用口径）。")
        seeds_gap = (f"interchange_seeds：行经书 ∩ scope 过滤（{len(seeds_src)}→"
                     f"{len(seeds_out) - n_new_seeds} 条）")
        if n_new_seeds:
            seeds_gap += f" + 演示新增 {n_new_seeds} 条（霍天都/凌云凤=天山派创派、" \
                         "易兰珠/吕四娘=演示覆盖；note 为原创编辑内容 L0）"
        seeds_gap += f"；canonical 映射命中 {n_canonical}/{len(seeds_out)}"
        seeds_gap += (f"（对照源：EX-2 characters.json {canon_index['source']}）"
                      if canon_index else "（对照索引缺失，保持纯文本降级）")
        gaps.append(seeds_gap + "。")
        gaps.append(f"open_questions：关涉书 ⊆ scope 过滤（{len(oq_src)}→{len(oq_out)} 条；"
                    "关涉书由悬案文本与全书目字符串匹配，无法归书者保守保留）。")
        payload["meta"]["scope"] = scope["profile"]
    if guide:
        payload["meta"]["reading_guide_source"] = GUIDE_SOURCE
    stats = {"lines": len(payload["lines"]), "chronology_spine": len(payload["chronology_spine"]),
             "interchange_seeds": len(payload["interchange_seeds"]),
             "open_questions": len(payload["open_questions"]),
             "lines_trimmed": n_lines_src - len(payload["lines"]),
             "spine_trimmed": n_spine_src - len(payload["chronology_spine"]),
             "seeds_src": len(seeds_src), "seeds_kept": len(payload["interchange_seeds"]) - n_new_seeds,
             "seeds_new": n_new_seeds, "seeds_total": len(payload["interchange_seeds"]),
             "seeds_canonical": n_canonical,
             "open_questions_kept": len(oq_out),
             "open_questions_dropped": len(oq_src) - len(oq_out),
             "reading_guide_rows": len(guide), **rg_stats}
    return payload, stats


# ---------------------------------------------------------------- atlas/<书>.json
def atlas_books(books: list, scope=None) -> list:
    """atlas 切片书单（W0-T3a）：scope 口径仅留 in_scope 书目（顺序保持）；全量口径原样。"""
    return [b for b in books if esc.in_scope(b, scope)]


def _works_meta(src: dict, book: str) -> dict:
    return src["works_by_book"].get(book) or {}


def _conc_persons(src: dict, book: str) -> dict:
    out = {}
    for e in src["conc"].get(book, {}).get("entities", []):
        if e.get("type") != "@":
            continue
        out[e["canonical"]] = {
            "n": e.get("total", 0),
            "chaps": sort_chaps(c.get("chapter", 0) for c in e.get("chapter_counts", [])),
        }
    return out


def _conc_places(src: dict, book: str) -> dict:
    """concordance 的 = 实体（无坐标）→ atlas places 兜底（仅 5th book 需要）。"""
    out = {}
    for e in src["conc"].get(book, {}).get("entities", []):
        if e.get("type") != "=":
            continue
        out[e["canonical"]] = {
            "real": None, "lat": None, "lng": None, "precision": None,
            "aliases": [],
            "chaps": sort_chaps(c.get("chapter", 0) for c in e.get("chapter_counts", [])),
        }
    return out


def build_atlas(src: dict, book: str, scope=None) -> tuple[dict, dict]:
    """单书 atlas 切片（内容本就按书圈定；W0-T3a 仅在 meta 标记 scope 口径）。"""
    wm = _works_meta(src, book)
    old = src["old_atlas"].get(book)
    tagged = src["tagged"].get(book, {})
    reg_places = [p for p in (src["gazetteer"].get("places") or [])
                  if p.get("loc_mode") == "coord" and book in (p.get("books") or {})]

    # persons：新 concordance @ 实体；旧站 key 兜底（契约要求旧键不缺）
    persons = _conc_persons(src, book)
    if old:
        for name, val in (old.get("persons") or {}).items():
            persons.setdefault(name, {"n": val.get("n", 0),
                                      "chaps": sort_chaps(val.get("chaps") or [])})
    # leads 兜底（works 元数据）
    for lead in (wm.get("leads") or []):
        persons.setdefault(lead, {"n": (wm.get("lead_hits") or {}).get(lead, 0),
                                  "chaps": []})

    # places：N7 坐标层（按书过滤）；旧站 key 兜底；5th book 用 concordance = 实体（无坐标）
    places = {}
    for p in reg_places:
        places[p["id"]] = {
            "real": p.get("real"),
            "lat": p.get("lat"),
            "lng": p.get("lng"),
            "precision": p.get("precision"),
            "aliases": list(p.get("aliases") or []),
            "chaps": sort_chaps((p.get("books") or {}).get(book) or []),
        }
    if old:
        for name, val in (old.get("places") or {}).items():
            places.setdefault(name, {
                "real": val.get("real"), "lat": val.get("lat"), "lng": val.get("lng"),
                "precision": val.get("precision"), "aliases": list(val.get("aliases") or []),
                "chaps": sort_chaps(val.get("chaps") or []),
            })
    n_conc_places = 0
    if not old:
        cp = _conc_places(src, book)
        for name, val in cp.items():
            if name not in places:
                places[name] = val
                n_conc_places += 1

    # bychap：新 tagged 逐回 p/l；旧站章节键兜底（契约要求旧章节键不缺）
    bychap = {}
    for ch, slot in sorted(tagged.items()):
        bychap[str(ch)] = {"p": slot["p"], "l": slot["l"]}
    if old:
        for ch, val in (old.get("bychap") or {}).items():
            if ch not in bychap:
                bychap[ch] = {"p": list(val.get("p") or []), "l": list(val.get("l") or [])}
        for ch, val in (old.get("bychap") or {}).items():
            if ch in bychap and (not bychap[ch]["p"] and not bychap[ch]["l"]):
                bychap[ch] = {"p": list(val.get("p") or []), "l": list(val.get("l") or [])}

    # events：新管线无事件层（D03/EX-5 未上线）。4 书沿用旧站冻结事件表；5th book 空 + field_gaps
    if old:
        events = json.loads(json.dumps(old.get("events") or {}, ensure_ascii=False))
        events_src = "legacy-frozen"
    else:
        events = {}
        events_src = "empty"

    # chapters：旧契约=正文章回数（不含 000 楔子）；无旧站时用 works/chapters 或 tagged 最大回号
    if old:
        chapters = old.get("chapters") or len([c for c in bychap if int(c) > 0])
    else:
        chapters = wm.get("chapters") or len([c for c in bychap if int(c) > 0])

    era = wm.get("era") or (old or {}).get("era") or ""
    era_conf = wm.get("era_conf") or (old or {}).get("era_conf") or "todo"

    field_gaps = [
        "events：新管线事件层（D03/EX-5）未上线，"
        + ("沿用旧站 2026-11-02 冻结事件表（不伪造；EX-5 上线后替换）。"
           if old else "本表 events={}（冰魄寒光剑无历史事件表与事件产物；D03 未上线，不伪造）。"),
        "era/era_conf 来自 kb/作品元数据表（只读）；kb_status=待建/标注中的书其年代置信见 era_conf。",
        "persons：registry/concordance @ 实体（新口径，n=出现次数、chaps=出现回号）；"
        "旧站人物键保留兜底（契约不丢键）。",
        "places：registry/gazetteer N7 坐标层（loc_mode=coord）；"
        + ("冰魄寒光剑无历史坐标层，places 取自 concordance = 实体（无经纬度，lat/lng=null）。"
           if not old else "unlocatable 31 条不入图（见 gazetteer.json field_gaps）。"),
        "bychap：tagged 实体令牌逐回生成（p=@人物、l=其余实体规范名）；旧站章节键保留兜底。",
    ]
    payload = {
        "meta": {
            "generated": esc.today(),
            "schema": "atlas-slice-v1",
            "book": book,
            "copyright": "L0 图谱层：仅定位符与结构化事实，不含摘录",
            "source": "tagged/struct + registry/concordance + registry/gazetteer + kb/作品元数据表"
                      "（旧 site/data/atlas 只读兜底）",
            "events_source": events_src,
            "field_gaps": field_gaps,
        },
        "title": book,
        "era": era,
        "era_conf": era_conf,
        "chapters": chapters,
        "persons": persons,
        "places": places,
        "bychap": bychap,
        "events": events,
    }
    if scope is not None:
        payload["meta"]["scope"] = scope["profile"]
        payload["meta"]["field_gaps"].append(
            f"scope 口径（{scope['profile']}）：本切片属 scope 书目（atlas 仅产 scope 书）；"
            "切片内容按本书圈定，无需再裁。")
    stats = {
        "book": book,
        "chapters": chapters,
        "persons": len(persons),
        "places": len(places),
        "bychap_chapters": len(bychap),
        "events_chapters": len(events),
        "events_edges": sum(len(v) for v in events.values() if isinstance(v, list)),
        "new_conc_places": n_conc_places,
        "contract": bool(old),
    }
    return payload, stats


# ---------------------------------------------------------------- atlas/state.json（W0-T4 接管）
def build_state(slices: dict, works_by_book: dict | None = None, scope=None) -> tuple[dict, dict]:
    """atlas/state.json payload（W0-T4 接管；原由废弃的 scripts/build_atlas_slices.py 独产）。

    消费键兼容（本函数的存在依据）：
      - site/src/islands/MapTrail.tsx `Manifest`：meta.note + books[].slug/title/chapters/
        era/era_conf/leads（books[].title 做深链选书与默认书、books[].leads 做 suggestedPerson）；
      - scripts/build_qa_index.py `select_titles`：books[].title（qa-index 书目上限随 state.json）。

    scope 口径：books = scope 书目（tianshan-demo = 演示顺序，books[0] = 散花女侠）；
    全量口径：books = BOOKS 契约顺序（与旧脚本 state.json 同构同序，逐字兼容——方案 R6）。
    persons/places/chaps 不在 state.json（旧契约即无），随 atlas/<书>.json 切片。
    """
    works_by_book = works_by_book or {}
    if scope is not None:
        ordered = [b for b in (scope.get("books") or []) if b in slices]
    else:
        ordered = [b for b in BOOKS if b in slices]
    books = []
    for b in ordered:
        sl = slices.get(b) or {}
        books.append({
            "slug": b,
            "title": sl.get("title") or b,
            "chapters": int(sl.get("chapters") or 0),
            "era": sl.get("era") or "",
            "era_conf": sl.get("era_conf") or "todo",
            "leads": list((works_by_book.get(b) or {}).get("leads") or []),
        })
    note = "leaders（各派当前掌门）待工具 B 门派世系表接入后填充；era 来自作品元数据表"
    meta = {"generated": esc.today(), "schema": "atlas-state-v1", "note": note}
    if scope is not None:
        meta.update(esc.scope_meta(scope) or {})
        meta["note"] = note + f"（W0-T4 起由 {EXPORTER} 接管产出）"
        meta["field_gaps"] = [
            f"scope 口径（{scope['profile']}）：books = scope 书目"
            + ("（演示顺序，books[0]=散花女侠）" if scope.get("profile") == DEMO_PROFILE else "")
            + "；persons/places/chaps 随 atlas/<书>.json 切片（EX-7 仅产 scope 书）。"]
    payload = {"meta": meta, "books": books}
    stats = {"books": len(books), "chapters_total": sum(b["chapters"] for b in books),
             "order": "scope-books" if scope is not None else "BOOKS-contract"}
    return payload, stats


# ---------------------------------------------------------------- finish（4 书有契约；冰魄合成校验）
def finish_with_contract(name: str, payload: dict, notes: str) -> dict:
    return esc.finish(name, payload, exporter=EXPORTER, notes=notes)


def finish_synth_contract(name: str, payload: dict, notes: str) -> dict:
    """无历史契约的落点（冰魄寒光剑）：合成 signature 做 diff，并手动落 staging/report；
    --apply 时与 esc.finish 同口径写 site/data（先备份）。2026-11-05 修复：原恒 dry-run，
    第 5 书 atlas 只进 staging、永不落盘，与集成器 "atlas 5 书" 声称不符。"""
    contract = {"name": name, "generated": esc.now_iso(), "schema": ATLAS_SYNTH_SCHEMA}
    diff = esc.diff_against_contract(name, payload, contract)
    esc.STAGING.mkdir(parents=True, exist_ok=True)
    staged = esc.atomic_write_json(payload, esc.STAGING / name)

    applied = None
    if esc.is_apply():
        target = esc.SITE_DATA / name
        if target.exists():
            backup_run = esc.BACKUP_ROOT / f"apply_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_run.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_run / name.replace("/", "_"))
        applied = esc.atomic_write_json(payload, target)

    report = esc._render_report(name, EXPORTER, diff, payload, staged, applied,
                                notes + "\n（本文件无 2026-11-02 历史契约，差异基线=4 书共同结构合成 signature）")
    report_path = esc.REPORTS_DIR / (name.replace("/", "_").replace(".json", "") + "_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8", newline="\n")
    print(f"[export] {name}: records={diff['new_record_count']} hard_gaps={diff['hard_gap_count']} "
          f"staging={staged} {'APPLIED→' + str(applied) if applied else '(dry-run / synth-contract)'}")
    return diff


def main() -> int:
    # W0-T3a：--scope <profile> 裁剪口径（W0-T1 基础设施；不带 --scope = 全量口径，向后兼容）
    profile = esc.scope_from_args()
    scope = esc.load_scope(profile) if profile is not None else None
    src = load_sources()
    results = {}

    # W0-T4：canonical/别名对照索引（EX-2 产物 characters.json：staging 优先，site/data 兜底；
    # EX-7 在 export_site_all 序列中后于 EX-2 运行 → staging 为同批产物；缺失则种子降级纯文本）
    canon_index = load_canonical_index() if scope is not None else None
    if scope is not None:
        if canon_index:
            print(f"[EX-7] canonical 对照索引：characters.json ({canon_index['source']})，"
                  f"names={len(canon_index['by_name'])}，canonicals={len(canon_index['books_of'])}")
        else:
            print("[EX-7] canonical 对照索引缺失（staging/site/data 均无 characters.json）——"
                  "seeds 保持纯文本降级")

    # 1) gazetteer.json
    payload, stats = build_gazetteer(src, scope=scope)
    notes = (f"places {stats['new']} 条（N7 coord={stats['coord']}；unlocatable={stats['unlocatable']} "
             f"不入坐标层）；旧站 619 条键匹配 {stats['legacy_matched']}，新增 {stats['new_places']}；"
             f"kind=N7 十三值口径、real=N7 兼容派生列。")
    results["gazetteer.json"] = finish_with_contract("gazetteer.json", payload, notes)

    # 2) universe.json（W0-T4：tianshan-demo 单线重建 + seeds canonical + open_questions 过滤）
    upayload, ustats = build_universe(src, scope=scope, canon_index=canon_index)
    unotes = (f"lines {ustats['lines']} / chronology_spine {ustats['chronology_spine']} / "
              f"interchange_seeds {ustats['interchange_seeds']} / open_questions {ustats['open_questions']}；"
              f"四节基源 kb/系列谱系考订表.json 只读。"
              f" D2 线路导读：TSV 校定行 {ustats['reading_guide_rows']} 条，挂载 "
              f"{ustats['reading_guide_attached']} 线（站外槽位降级 "
              f"{ustats['reading_guide_dropped_slots']}）。"
              + (f" scope 口径（W0-T4）：seeds {ustats['seeds_src']}→{ustats['seeds_kept']}"
                 f"（+{ustats['seeds_new']} 演示新增），canonical 命中 {ustats['seeds_canonical']}"
                 f"/{ustats['seeds_total']}，open_questions 裁 {ustats['open_questions_dropped']} 条，"
                 f"编年谱裁 {ustats['spine_trimmed']} 段。"
                 if scope is not None else ""))
    results["universe.json"] = finish_with_contract("universe.json", upayload, unotes)

    # 3) atlas/<书>.json ×5（W0-T3a：仅 scope 书）
    astats = {}
    slice_payloads = {}    # W0-T4：供 atlas/state.json 汇总（chapters/era 随切片）
    for book in atlas_books(BOOKS, scope):
        payload, st = build_atlas(src, book, scope=scope)
        astats[book] = st
        slice_payloads[book] = payload
        notes = (f"{book}：chapters={st['chapters']} persons={st['persons']} places={st['places']} "
                 f"bychap={st['bychap_chapters']} events_chapters={st['events_chapters']} "
                 f"events_edges={st['events_edges']}；"
                 f"persons=concordance @ + 旧键兜底；places=gazetteer 坐标层"
                 + ("（冰魄用 concordance = 实体无坐标）" if not st["contract"] else "")
                 + f"；events={payload['meta']['events_source']}。")
        name = f"atlas/{book}.json"
        if st["contract"]:
            results[name] = finish_with_contract(name, payload, notes)
        else:
            results[name] = finish_synth_contract(name, payload, notes)

    # 4) atlas/state.json（W0-T4 接管：原由废弃的 scripts/build_atlas_slices.py 独产，
    #    2026-11-02 陈旧 4 书口径；现随本次导出口径重建，MapTrail/build_qa_index 消费键兼容）
    spayload, sstats = build_state(slice_payloads, src["works_by_book"], scope=scope)
    snotes = (f"books={sstats['books']}（{'scope 书目' if scope is not None else 'BOOKS 契约顺序'}，"
              f"chapters 合计 {sstats['chapters_total']}，leads=kb/作品元数据表）；"
              "消费键兼容：MapTrail.tsx Manifest（meta.note + books[].slug/title/chapters/era/"
              "era_conf/leads）与 build_qa_index.select_titles（books[].title）。"
              + (" persons/places/chaps 随 atlas/<书>.json 切片。"
                 if scope is not None else " 全量口径与旧脚本 state.json 同构。"))
    results["atlas/state.json"] = finish_with_contract("atlas/state.json", spayload, snotes)

    # W0-T3a：scope 口径下移除 staging 里 scope 外的陈旧 atlas 切片（staging 为可再生产物，
    # 保持与本次导出口径一致；site/data 的陈旧切片清理属 --apply 收口步骤，本任务不做）
    if scope is not None:
        for book in BOOKS:
            if esc.in_scope(book, scope):
                continue
            stale = esc.STAGING / "atlas" / f"{book}.json"
            if stale.exists():
                stale.unlink()
                print(f"[EX-7] scope 口径：移除 staging 陈旧切片 atlas/{book}.json")

    # 4) 汇总报告（跨文件）
    esc.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# EX-7 汇总报告（gazetteer / universe / atlas）",
        "",
        f"- 导出器：{EXPORTER}",
        f"- 时间：{esc.now_iso()}",
        f"- 模式：{'APPLY' if esc.is_apply() else 'dry-run（仅 staging）'}",
        "",
        "| 输出 | 旧契约记录 | 新产出 | hard_gap | staging |",
        "|---|---:|---:|---:|---|",
    ]
    for name, d in results.items():
        lines.append(f"| `{name}` | {d['old_record_count']} | {d['new_record_count']} | "
                     f"{d['hard_gap_count']} | `logs/export/staging/{name.replace('/', '_')}` |")
    lines += ["", "## atlas 逐书统计", "",
              "| 书 | chapters | persons | places | bychap 回 | events 回 | events 边 | 契约 |",
              "|---|---:|---:|---:|---:|---:|---:|---|"]
    for book in atlas_books(BOOKS, scope):
        s = astats[book]
        lines.append(f"| {book} | {s['chapters']} | {s['persons']} | {s['places']} | "
                     f"{s['bychap_chapters']} | {s['events_chapters']} | {s['events_edges']} | "
                     f"{'历史契约' if s['contract'] else '合成 signature（无历史契约）'} |")
    lines += ["", "## 数据源与缺口", "",
              "- gazetteer：N7 `registry/gazetteer.json` coord 619 条入坐标层；unlocatable 31 条不入图（见文件 field_gaps）。",
              "- universe：`kb/系列谱系考订表.json` 四节只读快照（人工考订权威）。"
              f"D2 线路导读：kb/校订/线路导读.tsv 校定行挂载 lines[].reading_guide"
              f"（{ustats['reading_guide_attached']} 线，线名基名匹配，两口径通用）。"
              + (f"W0-T4 scope 口径：lines 单线「{DEMO_LINE_NAME}」重建（{ORDER_RULING}）、"
                 f"seeds canonical 命中 {ustats['seeds_canonical']}/{ustats['seeds_total']}"
                 f"（对照源：EX-2 characters.json {(canon_index or {}).get('source', '缺失→纯文本降级')}）、"
                 f"open_questions 保留 {ustats['open_questions_kept']}/{ustats['open_questions_kept'] + ustats['open_questions_dropped']}。"
                 if scope is not None else ""),
              "- atlas/state.json：W0-T4 起由 EX-7 接管（原 scripts/build_atlas_slices.py 已废弃标注，"
              f"其 2026-11-02 陈旧 4 书口径由本次 {sstats['books']} 书产出取代）；消费键兼容 "
              "MapTrail.tsx Manifest 与 build_qa_index.select_titles。",
              "- atlas：persons=registry/concordance @；places=N7 坐标层；bychap=tagged 逐回实体令牌；"
              "era/era_conf=kb/作品元数据表；events 4 书沿用旧站冻结事件表（D03/EX-5 未上线），冰魄 events={}；"
              "旧站 atlas 章节/人物/地点键保留兜底（契约不丢键）。",
              "- 硬缺口合计：**%d**（目标 0；旧站 4 书契约逐项校验）。" % sum(
                  d["hard_gap_count"] for d in results.values()),
              ""]
    summary_path = esc.REPORTS_DIR / "ex7_summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    total = sum(d["hard_gap_count"] for d in results.values())
    print(f"\n[EX-7] 汇总：{len(results)} 个输出，契约硬缺口合计 = {total}")
    for name, d in results.items():
        print(f"  {name}: old={d['old_record_count']} new={d['new_record_count']} "
              f"hard_gap={d['hard_gap_count']} "
              f"(missing={len(d['missing_keys'])} type={len(d['type_mismatch'])} "
              f"item_missing={len(d['item_missing_keys'])})")
    print(f"[EX-7] 汇总报告 → {summary_path}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
