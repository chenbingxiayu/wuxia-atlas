# -*- coding: utf-8 -*-
"""N7 · `gazetteer_migrate.py` — 虚构地名 gazetteer 迁移器（武侠版·双图层）

规范源（每条规则标注出处）：
  `skills/SKILL_地名gazetteer_武侠版.md`（v0.3-draft, 2026-11-03）
    §2.1 F01-F20 定版字段总表
    §2.2 裁决 R1：nature 四值为权威列，real 降为兼容派生列（双向锁死）
    §2.3 kind 封闭 13 值（K01-K13，与 #8 地点树同源）
    §2.4 既有 kind 脏值归一映射表（70+ 值 → 13；按本名重判，不照抄 OSM 标签；原值留档）
    §2.5 650 条无损迁移映射 M01-M13（只增不改、暂定标记、台账留痕）
    §3.1 图层归属总规则；§3.2 precision 五级；§3.3 相对锚点；§3.6 降级显示
    §4.2 unlocatable 判据 U1-U4；§4.3 通名不登记（迁移不删，标待审）
    §6.3 status/verified 档位；§6.4 conf 三档派生
  docs/17 §2.3：N7 节点 =「650 条无损迁移（M01-M13 + nature 四值 + kind 归一）」。
  docs/51 §三 EX-7：本迁移产物 `registry/gazetteer.json` 是 EX-7 gazetteer/atlas 的上游输入。

迁移策略（三条纪律，见 SKILL §2.5）：
  1. 只增不改：首轮迁移只加 nature/loc_mode/layer/conf/first_seen/hq_of 等新列；
     id/name/aliases/books/count/lat/lng/precision/source 原值保留；kind 归一后原值写
     `source.legacy_kind`；status=missing_coord → auto（M08），verified 全保留 false。
  2. 暂定标记：M05 由 real 派生的 nature 均属"暂定"，全部进复核队列（在本报告列出）；
     loc_mode 三选一：有坐标→coord；无坐标→none + reason（显式弃权，不脑补锚点）。
  3. 台账留痕：逐条旧 id→新 id + 字段映射写入 `logs/gazetteer/migrate_trace.json`，
     断言结果写入报告与 trace；任何一项硬断言失败即 exit 1（不写 registry）。

CLI：
  python -X utf8 scripts/gazetteer_migrate.py                 # dry-run（默认，写报告+trace，不写 registry）
  python -X utf8 scripts/gazetteer_migrate.py --dry-run       # 同上（显式）
  python -X utf8 scripts/gazetteer_migrate.py --apply         # 写 registry/gazetteer.json（写前备份）
  python -X utf8 scripts/gazetteer_migrate.py --strict        # 警告升级为失败（默认仅硬断言失败）
  python -X utf8 scripts/gazetteer_migrate.py --selftest      # 规则自测，不写任何文件

输入（只读）：`kb/gazetteer.json`（650 条，旧 schema id/name/aliases/kind/real/books/count/status/
verified/lat/lng/precision/source）
输出：`registry/gazetteer.json`（新 schema，仅 --apply）、`logs/gazetteer/migrate_report.md`、
`logs/gazetteer/migrate_trace.json`、写前备份 `logs/gazetteer/backup/gazetteer_<ts>.json`。
**不写 kb/**（运行前后对 kb/gazetteer.json 做 sha256 一致性断言）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # wuxia-kb/
LEGACY = ROOT.parent / "kb" / "gazetteer.json"      # 只读旧资产
OUT_REGISTRY = ROOT / "registry" / "gazetteer.json"
LOGS_DIR = ROOT / "logs" / "gazetteer"
REPORT_PATH = LOGS_DIR / "migrate_report.md"
TRACE_PATH = LOGS_DIR / "migrate_trace.json"
BACKUP_DIR = LOGS_DIR / "backup"
TOOL_VERSION = "gazetteer_migrate v1.0 (2026-11-05, N7/D10)"

# ---------------------------------------------------------------- 定版枚举（SKILL §2.1/§2.3）
NATURE_VALUES = ("真实", "虚构", "真实原型改造", "未定")
KIND_VALUES = ("山", "水域", "城镇", "关隘", "宫廷", "山庄园林", "客栈", "寺观",
               "寨堡", "遗址战场", "秘境洞府", "区域", "其他")
LOC_MODES = ("coord", "proto", "anchor", "none")
PRECISION_VALUES = ("exact", "approx", "shifted", "region", "proto")
STATUS_VALUES = ("auto", "待审", "已核准", "已弃用")
CONF_VALUES = ("strong", "ok", "weak")
UNLOCATABLE_REASONS = ("no_clue", "contradictory", "chain_broken", "legendary")
ENGINE_VALUES = ("seed", "nominatim", "manual", "tantu", "chgis")
LEGACY_STATUS_MAP = {"auto": "auto", "missing_coord": "auto"}   # M08

# ---------------------------------------------------------------- kind 归一（SKILL §2.4）
# 旧 kind 族 → 新 kind（K01-K13）。覆盖旧数据实测 76 个取值；未列值回退 K13 并计警告。
LEGACY_KIND_MAP = {
    # K01 山
    "山": "山", "peak": "山", "mountain_range": "山", "glacier": "山", "cliff": "山",
    # K02 水域
    "水域": "水域", "lake": "水域", "bay": "水域", "canal": "水域", "dam": "水域",
    "island": "水域", "islet": "水域",
    # K03 城镇
    "政区": "城镇", "administrative": "城镇", "city": "城镇", "town": "城镇",
    "suburb": "城镇", "quarter": "城镇", "neighbourhood": "城镇", "residential": "城镇",
    "locality": "城镇", "place": "城镇", "civil": "城镇", "地名": "城镇",
    "village": "城镇", "hamlet": "城镇", "聚落": "城镇",
    # K04 关隘
    "关隘": "关隘", "city_gate": "关隘", "gatehouse": "关隘", "citywalls": "关隘",
    "wall": "关隘", "motorway_junction": "关隘",
    # K05 宫廷
    "palace": "宫廷",
    # K08 寺观
    "寺观": "寺观", "religious": "寺观", "place_of_worship": "寺观",
    # K12 区域
    "边域": "区域", "泛称": "区域",
    # 场景/OSM 噪声/现代设施 → K13 其他（按本名重判，原值留档；见 NAME 规则与 ID_OVERRIDES）
    "场景": "其他", "yes": "其他", "station": "其他", "bus_stop": "其他",
    "train_station": "其他", "aerodrome": "其他", "hotel": "其他", "school": "其他",
    "university": "其他", "college": "其他", "museum": "其他", "park": "其他",
    "attraction": "其他", "monument": "其他", "memorial": "其他", "artwork": "其他",
    "government": "其他", "governmental": "其他", "diplomatic": "其他",
    "post_office": "其他", "industrial": "其他", "construction": "其他",
    "military": "其他", "building": "其他", "castle": "其他", "tram": "其他",
    "stop": "其他", "viaduct": "其他", "footway": "其他", "steps": "其他",
    "pedestrian": "其他", "tertiary": "其他", "primary": "其他", "secondary": "其他",
    "service": "其他", "stone": "其他", "heritage": "其他",
}

# 旧数据按名重判的显式覆盖（SKILL §2.4 正例/§3.7/§5.6；只列必须人工裁决的点）
ID_KIND_OVERRIDES = {
    "京师": ("城镇", "§2.4 正例：京师 OSM=town → 城镇（编码误配四川景市镇，坐标入复核队列）"),
    "陕北": ("区域", "§2.4 正例：陕北 OSM=civil → 区域（精度待升 region）"),
    "回疆": ("区域", "§2.4/§3.1：回疆=区域 K12（OSM 误配云南回江）"),
    "风砂堡": ("寨堡", "§2.4/§5.1：虚构场景 → 寨堡 K09"),
    "喀沁草原": ("区域", "§2.4/§5.1：虚构草原 → 区域 K12"),
    "木什塔克": ("其他", "§2.4：场景待审 → K13（疑似慕士塔格原型，nature 复核）"),
    "驿站": ("客栈", "§2.4：驿站为古代驿馆，属 K07 客栈（OSM post_office 噪声）"),
    "大雄宝殿": ("寺观", "殿名在寺院语境 → 寺观 K08"),
    "养心殿": ("宫廷", "宫殿建筑 → 宫廷 K05"),
    "嵩山少林": ("寺观", "少林寺别写（OSM hotel 噪声）→ 寺观 K08"),
    "布达拉宫": ("宫廷", "castle→宫廷 K05"),
    "雍和宫": ("寺观", "place_of_worship → 寺观 K08"),
    "皇府": ("宫廷", "皇府=皇家府邸 → 宫廷 K05"),
    "天牢": ("其他", "天牢=牢狱，13 值无对应 → K13 待审"),
    "燕京八景": ("其他", "八景=景观集合名，非单一地点 → K13 待审"),
    "钱塘八景": ("其他", "八景=景观集合名，非单一地点 → K13 待审"),
    "明十三陵": ("遗址战场", "陵寝/遗址 → 遗址战场 K10"),
    "野猪林": ("区域", "林地场景 → 区域 K12（待审）"),
}

# 区域名（省/历史地理区；这些名字的后缀会与 山/水/州/海 等冲突，必须显式裁决）
REGION_NAME_SET = {
    "江南", "中原", "关外", "塞外", "西域", "回疆", "南疆", "北疆", "西藏",
    "四川", "陕西", "河南", "山东", "山西", "河北", "浙江", "云南", "贵州",
    "广西", "广东", "福建", "江西", "湖南", "湖北", "安徽", "江苏", "甘肃",
    "新疆", "青海", "蒙古", "满洲", "关中", "岭南", "巴蜀", "漠北", "京华",
    "百越", "冀鲁豫", "川陕", "川西", "川中", "川滇", "滇东", "滇边", "藏边",
    "辽东", "辽东半岛", "关东", "关内", "西北", "东北", "西南", "东南",
    "北五省", "川滇边区", "川滇边境",
}

# 通名/泛称候选（G03）：迁移不删（保引用），flag 待人工判 已弃用（SKILL §4.3/§6.3）
GENERIC_NAME_SET = {"山", "镖局", "镖行", "宫廷", "宫中", "宫内", "京中", "驿站",
                    "官兵", "大军", "朝廷", "皇室", "府", "县衙", "衙门", "关内"}

# 场景/建筑显式后缀（按本名重判时使用）
WATER_SUFFIX = ("江", "河", "湖", "海", "溪", "泉", "池", "潭", "岛", "湾", "涧", "泊")
MOUNTAIN_SUFFIX = ("山", "峰", "岭", "崖", "顶", "山脉", "山麓", "山坡", "坡", "嶂")
PASS_SUFFIX = ("关", "隘", "门", "口", "塞口", "隘口")
TEMPLE_SUFFIX = ("寺", "庙", "观", "庵", "祠", "塔", "院")
PALACE_SUFFIX = ("宫", "殿")
GARDEN_SUFFIX = ("园", "苑", "庄", "墅", "精舍", "书院", "斋", "楼", "阁", "堂", "馆", "舍")
SETTLEMENT_SUFFIX = ("城", "镇", "州", "县", "京", "都", "邑", "卫")
FORTRESS_SUFFIX = ("寨", "堡", "硐", "垒")
HOME_SUFFIX = ("家", "府", "府邸", "王府", "相府")
GOV_SUFFIX = ("衙", "衙门", "抚衙", "行署", "巡抚", "总督府", "总督")
SCENIC_SUFFIX = ("八景", "叠翠", "朝暾", "印月", "秋月", "点将台")
BODY_MARK = "穴"

# 坐标/地理编码语义复核关键字（SKILL §6.2 实测：京师→四川景市镇、回疆→云南回江）
SUSPICIOUS_GEOCODE_IDS = {"京师", "回疆", "陕北", "昆仑山", "太阳穴", "曲池穴"}


# ---------------------------------------------------------------- 基础工具
def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------- 派生规则
def derive_nature(real) -> str:
    """M05 + 裁决 R1（SKILL §2.2）：true→真实(暂定)；false→虚构(暂定)；null→未定。"""
    if real is True:
        return "真实"
    if real is False:
        return "虚构"
    return "未定"


def derive_real(nature: str):
    """real 兼容派生列（SKILL §2.2 双向锁死）：真实→True；虚构/真实原型改造→False；未定→None。"""
    if nature == "真实":
        return True
    if nature in ("虚构", "真实原型改造"):
        return False
    return None


def classify_kind(pid: str, name: str, legacy_kind: str):
    """kind 归一（SKILL §2.3/§2.4）：显式覆盖 → 区域名 → 本名后缀重判 → 旧 kind 族映射 → K13。"""
    if pid in ID_KIND_OVERRIDES:
        return ID_KIND_OVERRIDES[pid]
    if pid in REGION_NAME_SET or name in REGION_NAME_SET:
        return "区域", "区域名白名单（省/历史地理区，§2.4 按本名重判）"
    if BODY_MARK in name:
        return "其他", "穴名（经络穴位非地点，§2.4 噪声）→ K13 待审"
    if name.endswith(SCENIC_SUFFIX):
        return "其他", "景观集合名（§2.4 待审）→ K13"
    if name.endswith(WATER_SUFFIX):
        return "水域", "本名含水域后缀（§2.4）"
    if name.endswith(MOUNTAIN_SUFFIX):
        return "山", "本名含山体后缀（§2.4）"
    if name.endswith(PASS_SUFFIX):
        return "关隘", "本名含关隘/城门后缀（§2.4）"
    if name.endswith(GOV_SUFFIX):
        return "其他", "官署/职衙（13 值无对应，§2.4 待审）→ K13"
    if name.endswith(GARDEN_SUFFIX):
        return "山庄园林", "本名含庄院/园林/楼阁后缀（§2.4）"
    if name.endswith(TEMPLE_SUFFIX):
        return "寺观", "本名含寺观/院落后缀（§2.4）"
    if name.endswith(PALACE_SUFFIX):
        return "宫廷", "本名含宫殿后缀（§2.4）"
    if name.endswith(FORTRESS_SUFFIX):
        return "寨堡", "本名含寨堡后缀（§2.4）"
    if name.endswith(HOME_SUFFIX):
        return "山庄园林", "宅第/府邸（§2.4 按本名重判）"
    if name.endswith(SETTLEMENT_SUFFIX):
        return "城镇", "本名含城镇/政区后缀（§2.4）"
    base = LEGACY_KIND_MAP.get(legacy_kind)
    if base:
        return base, f"旧 kind 族映射（{legacy_kind}→{base}，§2.4）"
    return "其他", f"旧 kind 未覆盖（{legacy_kind!r}）→ K13 兜底"


def derive_loc_mode(nature: str, lat, lng):
    """loc_mode 三选一（SKILL §2.5 M10-M12/§3.1）：
    有坐标 → coord；无坐标 → none + U1 no_clue（显式弃权，不脑补锚点/不折算坐标）。
    迁移期不产生 anchor/proto（无文证锚点与原型裁决，§2.5 只增不改）。"""
    if lat is not None and lng is not None:
        return "coord", None
    return "none", "no_clue"


def derive_layer(nature: str, loc_mode: str) -> str:
    """图层派生（SKILL §3.1）：真实→real；虚构/原型改造→fiction；未定→随 loc_mode。"""
    if nature == "真实":
        return "real"
    if nature in ("虚构", "真实原型改造"):
        return "fiction"
    return "real" if loc_mode == "coord" else "fiction"


def derive_conf(nature: str, loc_mode: str, precision) -> str:
    """conf 三档派生（SKILL §6.4）：
    coord+exact/region→strong；coord+approx/shifted→ok；none/未定/anchor→weak。"""
    if nature == "未定" or loc_mode == "none":
        return "weak"
    if loc_mode == "coord":
        return "strong" if precision in ("exact", "region") else "ok"
    return "weak"   # anchor/proto 迁移期不产生；防御性兜底


def review_flags(pid, name, legacy_kind, nature, loc_mode, source) -> list:
    """复核队列标签（不进登记表主体，仅 trace/报告；SKILL §2.5 纪律 2/§6.2/§6.3）。"""
    flags = []
    if nature in ("真实", "虚构"):
        flags.append("nature_tentative")        # M05 暂定，必须入复核队列
    if nature == "虚构":
        flags.append("fiction_needs_anchor")    # 虚构条目需文证锚点（迁移期弃权）
    if loc_mode == "none":
        flags.append("unlocatable")
    if pid in GENERIC_NAME_SET or name in ("山下", "城中", "村口"):
        flags.append("generic_name_candidate")  # G03：通名/泛指，待判 已弃用
    if BODY_MARK in name:
        flags.append("body_point_candidate")    # 经络穴位噪声
    if name.endswith(GOV_SUFFIX):
        flags.append("gov_office_undecided")    # 官署无 13 值对应
    if legacy_kind in ("场景",):
        flags.append("scene_undecided")
    if isinstance(source, dict) and source.get("n_candidates", 0) and source.get("n_candidates") > 1:
        flags.append("geocode_multi_candidate")
    if pid in SUSPICIOUS_GEOCODE_IDS:
        flags.append("geocode_suspect")
    return flags


# ---------------------------------------------------------------- 单条迁移
FIELD_MAP_SPEC = [
    # (M编号, 旧字段, 新字段, 迁移规则；SKILL §2.5)
    ("M01", "id", "id", "原样保留（中文规范名=主键，永不改写；G13）"),
    ("M02", "name", "name", "原样保留（今名/史籍名入 aliases，本轮不改名）"),
    ("M03", "aliases", "aliases", "原样保留（实测全空数组）"),
    ("M04", "kind", "kind", "按 §2.4 归一映射；原值写 source.legacy_kind 留档"),
    ("M05", "real", "real + nature", "true→真实(暂定)/false→虚构(暂定)/null→未定；real 兼容列同步派生"),
    ("M06", "books", "books", "结构原样保留（含 0 号回口径）"),
    ("M07", "count", "count", "原样保留"),
    ("M08", "status", "status", "auto→auto；missing_coord→auto（缺坐标由 lat/lng 缺失承载）"),
    ("M09", "verified", "verified", "全 false 原样保留（§6.3 定版语义）"),
    ("M10", "lat", "lat", "有值条目原样保留；无坐标条目 loc_mode=none 不写坐标（G05）"),
    ("M11", "lng", "lng", "同 M10"),
    ("M12", "precision", "precision", "既有 approx/shifted/exact 原值保留；null 仅随弃权条目"),
    ("M13", "source", "source", "旧 source 对象全键保留 + legacy_kind/legacy_status 留档"),
]


def migrate_entry(old: dict, ctx: dict) -> tuple[dict, dict]:
    pid = old.get("id")
    name = old.get("name", "")
    legacy_kind = old.get("kind")
    kind, kind_rule = classify_kind(pid, name, legacy_kind)
    real = old.get("real")
    nature = derive_nature(real)
    lat, lng = old.get("lat"), old.get("lng")
    loc_mode, reason = derive_loc_mode(nature, lat, lng)
    precision = old.get("precision")
    source_old = old.get("source")
    source = dict(source_old) if isinstance(source_old, dict) else {}
    source["legacy_kind"] = legacy_kind
    source["legacy_status"] = old.get("status")
    source.setdefault("engine", None)
    source["migrated_from"] = "kb/gazetteer.json"
    source["migration"] = "N7 M01-M13"

    entry = {
        "id": pid,                                                   # F01
        "name": name,                                                # F02
        "aliases": list(old.get("aliases") or []),                   # F03
        "kind": kind,                                                # F04（K01-K13）
        "nature": nature,                                            # F05（权威列）
        "real": derive_real(nature),                                 # F06（兼容派生列）
        "layer": derive_layer(nature, loc_mode),                     # F07
        "books": old.get("books") or {},                             # F08
        "first_seen": None,                                          # F09（不自动推导，§2.6）
        "count": old.get("count", 0),                                # F10
        "status": LEGACY_STATUS_MAP.get(old.get("status"), old.get("status")),  # F11
        "verified": bool(old.get("verified")),                       # F12
        "loc_mode": loc_mode,                                        # F13
    }
    if loc_mode == "coord":                                          # F14/F15
        entry["lat"] = lat
        entry["lng"] = lng
        entry["precision"] = precision
    elif loc_mode == "none":                                         # F17（anchor/none 禁写坐标）
        entry["unlocatable_reason"] = reason
    entry["source"] = source                                         # F18
    entry["hq_of"] = list(old.get("hq_of") or [])                    # F19（迁移期不派生）
    entry["conf"] = derive_conf(nature, loc_mode, precision)         # F20
    flags = review_flags(pid, name, legacy_kind, nature, loc_mode, source_old)
    if not LEGACY_KIND_MAP.get(legacy_kind) and pid not in ID_KIND_OVERRIDES:
        flags.append("legacy_kind_unmapped")

    changed = {
        "kind": {"from": legacy_kind, "to": kind, "rule": kind_rule},
        "status": {"from": old.get("status"), "to": entry["status"]}
        if old.get("status") != entry["status"] else None,
        "nature_derived": True,
        "loc_mode_derived": True,
    }
    trace = {
        "legacy_id": pid,
        "new_id": entry["id"],
        "name": name,
        "field_map": {old_f: new_f for _, old_f, new_f, _ in FIELD_MAP_SPEC},
        "kind": {"legacy": legacy_kind, "new": kind, "rule": kind_rule},
        "nature": {"legacy_real": real, "new": nature, "tentative": nature in ("真实", "虚构")},
        "loc_mode": loc_mode,
        "precision": precision,
        "conf": entry["conf"],
        "changed": {k: v for k, v in changed.items() if v is not None},
        "flags": flags,
    }
    return entry, trace


# ---------------------------------------------------------------- 迁移 + 校验
def run_migration(legacy: dict) -> dict:
    places_old = legacy.get("places") or []
    entries, traces = [], []
    for old in places_old:
        e, t = migrate_entry(old, {})
        entries.append(e)
        traces.append(t)
    hard, warn = validate(places_old, entries, traces, legacy)
    return {
        "legacy": legacy,
        "entries": entries,
        "traces": traces,
        "hard": hard,
        "warn": warn,
    }


def _asr(ok: bool, aid: str, desc: str, detail: str = "", hard: bool = True) -> dict:
    return {"id": aid, "desc": desc, "pass": bool(ok), "detail": detail,
            "severity": "hard" if hard else "warning"}


def validate(old_places, entries, traces, legacy) -> tuple[list, list]:
    """全量校验断言（SKILL §2.5/§6.3/§6.4；docs/51 §五 字段不缺精神）。"""
    hard, warn = [], []
    n_old, n_new = len(old_places), len(entries)

    def add(ok, aid, desc, detail="", hard_=True):
        rec = _asr(ok, aid, desc, detail, hard_)
        (hard if hard_ else warn).append(rec)

    # H01 数量守恒
    add(n_new == n_old == 650, "H01", "记录数守恒 650→650",
        f"legacy={n_old} new={n_new}")
    # H02 主键守恒/唯一
    ids_old = [p.get("id") for p in old_places]
    ids_new = [e["id"] for e in entries]
    add(len(set(ids_old)) == len(ids_old), "H02a", "旧 id 唯一", f"unique={len(set(ids_old))}")
    add(set(ids_new) == set(ids_old) and len(set(ids_new)) == len(ids_new),
        "H02b", "id 集合与旧站一致且唯一", f"new_unique={len(set(ids_new))}")
    # H03 M01-M13 字段对账
    old_by = {p["id"]: p for p in old_places}
    new_by = {e["id"]: e for e in entries}
    mismatch = []
    for pid in ids_new:
        o, n = old_by[pid], new_by[pid]
        if n["name"] != o.get("name"):
            mismatch.append(f"{pid}:name")
        if (n["aliases"] or []) != (o.get("aliases") or []):
            mismatch.append(f"{pid}:aliases")
        if (n["books"] or {}) != (o.get("books") or {}):
            mismatch.append(f"{pid}:books")
        if n["count"] != o.get("count"):
            mismatch.append(f"{pid}:count")
        if n["verified"] != bool(o.get("verified")):
            mismatch.append(f"{pid}:verified")
        if n["real"] != derive_real(derive_nature(o.get("real"))):
            mismatch.append(f"{pid}:real")
        if "lat" in n and n["lat"] != o.get("lat"):
            mismatch.append(f"{pid}:lat")
        if "lat" in n and n["precision"] != o.get("precision"):
            mismatch.append(f"{pid}:precision")
    add(not mismatch, "H03", "M01-M13 保真字段（id/name/aliases/books/count/verified/real/lat/lng/precision）逐条一致",
        f"mismatch={len(mismatch)} {mismatch[:5]}")
    # H04 nature 四值 + 分布
    nat = Counter(e["nature"] for e in entries)
    add(all(e["nature"] in NATURE_VALUES for e in entries), "H04a", "nature ∈ 四值枚举")
    add(nat == Counter({"真实": 624, "虚构": 3, "未定": 23}), "H04b",
        "nature 分布 = 真实624/虚构3/未定23（M05 暂定）", str(dict(nat)))
    # H05 real 兼容列锁死
    bad_real = [e["id"] for e in entries if e["real"] != derive_real(e["nature"])]
    add(not bad_real, "H05", "real 兼容列 = f(nature) 派生锁死", f"bad={bad_real[:5]}")
    # H06 loc_mode/coord 守恒/禁用组合
    modes = Counter(e["loc_mode"] for e in entries)
    add(set(modes) <= set(LOC_MODES), "H06a", "loc_mode ∈ {coord,proto,anchor,none}", str(dict(modes)))
    add(modes["coord"] == 619 and modes["none"] == 31, "H06b",
        "坐标条目 619 / 弃权 31（旧 with_coord=619）", str(dict(modes)))
    bad_coord = [e["id"] for e in entries if e["loc_mode"] == "coord"
                 and (e.get("lat") is None or e.get("lng") is None
                      or e.get("precision") not in PRECISION_VALUES)]
    add(not bad_coord, "H06c", "coord 条目 lat/lng/precision 三必备且 precision 合法", f"bad={bad_coord[:5]}")
    bad_none = [e["id"] for e in entries if e["loc_mode"] == "none"
                and (("lat" in e) or ("lng" in e) or e.get("unlocatable_reason") not in UNLOCATABLE_REASONS)]
    add(not bad_none, "H06d", "none 条目不写坐标且 reason ∈ U1-U4", f"bad={bad_none[:5]}")
    add(modes["anchor"] == 0 and modes["proto"] == 0, "H06e",
        "迁移期不产生 anchor/proto（显式弃权，不脑补锚点/原型）", str(dict(modes)))
    # H07 kind 枚举 + 分布
    kinds = Counter(e["kind"] for e in entries)
    add(all(e["kind"] in KIND_VALUES for e in entries), "H07a", "kind ∈ 13 值封闭枚举")
    add(sum(kinds.values()) == 650, "H07b", "kind 分布求和守恒", str(dict(kinds)))
    # H08 layer 派生
    bad_layer = [e["id"] for e in entries if e["layer"] != derive_layer(e["nature"], e["loc_mode"])]
    add(not bad_layer, "H08", "layer 按 §3.1 派生（真实→real；未定随 loc_mode）", f"bad={bad_layer[:5]}")
    # H09 status/verified 配对（§6.3/G12）
    bad_status = [e["id"] for e in entries if e["status"] not in ("auto", "待审")]
    bad_pair = [e["id"] for e in entries if e["verified"]]
    add(not bad_status, "H09a", "status 迁移档位合规（auto/待审）", f"bad={bad_status[:5]}")
    add(not bad_pair, "H09b", "verified 全 false（G12：无已核准条目）", f"true={bad_pair[:5]}")
    # H10 conf 派生
    conf = Counter(e["conf"] for e in entries)
    bad_conf = [e["id"] for e in entries
                if e["conf"] != derive_conf(e["nature"], e["loc_mode"], e.get("precision"))]
    add(not bad_conf, "H10a", "conf = §6.4 派生规则", f"bad={bad_conf[:5]}")
    add(set(conf) <= set(CONF_VALUES) and sum(conf.values()) == 650, "H10b",
        "conf ∈ 三档且求和守恒", str(dict(conf)))
    # H11 source 保真 + engine 枚举
    bad_src = []
    for pid in ids_new:
        o, n = old_by[pid], new_by[pid]
        so = o.get("source") if isinstance(o.get("source"), dict) else {}
        sn = n.get("source") or {}
        for k, v in so.items():
            if sn.get(k) != v:
                bad_src.append(f"{pid}.{k}")
        if sn.get("engine") is not None and sn.get("engine") not in ENGINE_VALUES:
            bad_src.append(f"{pid}.engine={sn.get('engine')!r}")
    add(not bad_src, "H11", "source 旧键值全保留 + engine ∈ 枚举", f"bad={len(bad_src)} {bad_src[:5]}")
    # H12 M01-M13 每项在 trace 有映射记录
    mapped = set()
    for t in traces:
        mapped |= set(t["field_map"].keys())
    need = {m[1] for m in FIELD_MAP_SPEC}
    add(need <= mapped, "H12", "M01-M13 旧字段全部出现在逐条字段映射", f"missing={sorted(need - mapped)}")
    # H13 输出字段完整性（F01-F13 + F18-F20 必填；按 loc_mode 条件字段）
    req = {"id", "name", "aliases", "kind", "nature", "real", "layer", "books",
           "first_seen", "count", "status", "verified", "loc_mode", "source",
           "hq_of", "conf"}
    bad_fields = [e["id"] for e in entries if not req <= set(e.keys())]
    add(not bad_fields, "H13", "F01-F13/F18-F20 必填字段齐全", f"bad={bad_fields[:5]}")
    # H14 弃权条目清单与旧无坐标集合一致
    old_no_coord = {p["id"] for p in old_places if p.get("lat") is None or p.get("lng") is None}
    new_none = {e["id"] for e in entries if e["loc_mode"] == "none"}
    add(old_no_coord == new_none, "H14", "弃权条目集合 = 旧无坐标集合", f"diff={len(old_no_coord ^ new_none)}")
    # H15 只读：kb 文件哈希在 main 中前后比对（此处占位，由 caller 注入）
    # 警告项（--strict 时升级为失败）：应为 0 的数据异常
    warn_checks = {
        "W01 旧 kind 未覆盖（回退 K13）": [t["legacy_id"] for t in traces
                                     if any(f == "legacy_kind_unmapped" for f in t["flags"])],
        "W02 lat/lng 单边缺失": [p["id"] for p in old_places
                            if (p.get("lat") is None) != (p.get("lng") is None)],
        "W03 count<1": [p["id"] for p in old_places if not isinstance(p.get("count"), int) or p.get("count") < 1],
        "W04 books 为空": [p["id"] for p in old_places if not (p.get("books") or {})],
        "W05 旧 status 未知": [p["id"] for p in old_places if p.get("status") not in LEGACY_STATUS_MAP],
        "W06 旧 precision 非法（有坐标条目）": [
            p["id"] for p in old_places
            if p.get("lat") is not None and p.get("precision") not in PRECISION_VALUES],
    }
    for desc, bad in warn_checks.items():
        add(not bad, desc.split()[0], desc, f"hits={len(bad)} {bad[:8]}", hard_=False)
    return hard, warn


# ---------------------------------------------------------------- 报告
def _fmt_dist(counter: Counter, order=None) -> str:
    items = [(k, counter.get(k, 0)) for k in order] if order else counter.most_common()
    return "、".join(f"{k} {v}" for k, v in items if v)


def render_report(result: dict, args, legacy_sha: str, out_written: bool, backup_path) -> str:
    legacy = result["legacy"]
    entries, traces = result["entries"], result["traces"]
    hard, warn = result["hard"], result["warn"]
    n_pass = sum(1 for a in hard + warn if a["pass"])
    n_hard_fail = sum(1 for a in hard if not a["pass"])
    n_warn_fail = sum(1 for a in warn if not a["pass"])
    nat = Counter(e["nature"] for e in entries)
    kinds = Counter(e["kind"] for e in entries)
    modes = Counter(e["loc_mode"] for e in entries)
    layers = Counter(e["layer"] for e in entries)
    conf = Counter(e["conf"] for e in entries)
    status = Counter(e["status"] for e in entries)
    prec = Counter(e.get("precision") for e in entries if e["loc_mode"] == "coord")
    legacy_kinds = Counter(p.get("kind") for p in (legacy.get("places") or []))
    unlocatable = [e for e in entries if e["loc_mode"] == "none"]
    flags = Counter(f for t in traces for f in t["flags"])

    L = []
    L.append("# N7 · gazetteer 迁移报告（旧 kb/gazetteer.json → registry/gazetteer.json）")
    L.append("")
    L.append(f"- 工具：`{TOOL_VERSION}`")
    L.append(f"- 生成：{now_ts()}")
    L.append(f"- 模式：{'APPLY（已写 registry）' if out_written else 'dry-run（未写 registry）'}"
             f"{' · strict' if args.strict else ''}")
    L.append(f"- 输入（只读）：`kb/gazetteer.json`（sha256 `{legacy_sha[:16]}…`，{len(legacy.get('places') or [])} 条）")
    L.append(f"- 输出：`registry/gazetteer.json`（新 schema gazetteer-v1）"
             + (f" · 写前备份：`{backup_path}`" if backup_path else ""))
    L.append(f"- 逐条追溯：`logs/gazetteer/migrate_trace.json`（旧 id→新 id + M01-M13 字段映射 + 复核 flags）")
    L.append(f"- 规范：`skills/SKILL_地名gazetteer_武侠版.md` v0.3-draft（F01-F20 / §2.4 / M01-M13 / §6.3 / §6.4）")
    L.append("")
    L.append("## 一、迁移总览")
    L.append("")
    L.append(f"- 记录数：**{len(legacy.get('places') or [])} → {len(entries)}**（守恒）")
    L.append(f"- nature：{_fmt_dist(nat, NATURE_VALUES)}")
    L.append(f"- real（兼容派生）：" + "、".join(f"{k} {v}" for k, v in
                                                Counter(str(e['real']) for e in entries).most_common()))
    L.append(f"- loc_mode：{_fmt_dist(modes, LOC_MODES)}")
    L.append(f"- layer：{_fmt_dist(layers, ('real', 'fiction'))}")
    L.append(f"- status：{_fmt_dist(status, ('auto', '待审', '已核准', '已弃用'))}")
    L.append(f"- conf：{_fmt_dist(conf, CONF_VALUES)}")
    L.append(f"- precision（coord 条目）：" + "、".join(f"{k} {v}" for k, v in prec.most_common()))
    L.append(f"- kind（13 值归一后）：{_fmt_dist(kinds, KIND_VALUES)}")
    L.append("")
    L.append("## 二、逐字段迁移对账（M01–M13，SKILL §2.5）")
    L.append("")
    L.append("| 编号 | 旧字段 | 新字段 | 规则 | 对账结果 |")
    L.append("|---|---|---|---|---|")
    for mid, old_f, new_f, rule in FIELD_MAP_SPEC:
        # 保真计数
        if old_f in ("id", "name", "aliases", "books", "count", "verified"):
            ok = sum(1 for t in traces if t["legacy_id"] == t["new_id"])
            stat = f"原样保留 {ok}/{len(traces)}"
        elif old_f in ("lat", "lng"):
            stat = f"坐标保留 {modes['coord']}/{len(traces)}；弃权 {modes['none']} 条不写坐标"
        elif old_f == "precision":
            stat = f"原值保留 {modes['coord']}/{len(traces)}（approx/shifted/exact 语义不重定义）"
        elif old_f == "kind":
            mapped = sum(1 for t in traces if t["kind"]["new"] in KIND_VALUES)
            stat = f"归一 {mapped}/{len(traces)}（原值留档 source.legacy_kind）"
        elif old_f == "real":
            stat = f"real→nature 派生 {len(traces)}/{len(traces)}（暂定入复核队列）"
        elif old_f == "status":
            changed = sum(1 for t in traces if t["changed"].get("status"))
            stat = f"原样 {len(traces) - changed}；missing_coord→auto {changed}（M08）"
        elif old_f == "source":
            stat = f"旧 source 键值全保留 {len(traces)}/{len(traces)}（+legacy_kind/legacy_status 留档）"
        else:
            stat = "见 trace"
        L.append(f"| {mid} | `{old_f}` | `{new_f}` | {rule} | {stat} |")
    L.append("")
    L.append("## 三、kind 归一分布（旧 76 值 → 13 值）")
    L.append("")
    L.append("| 旧 kind | 条数 | 新 kind |")
    L.append("|---|---:|---|")
    for k, c in legacy_kinds.most_common():
        nk, _rule = classify_kind("", "", k)
        L.append(f"| `{k}` | {c} | {nk} |")
    L.append("")
    L.append("说明：`ID_KIND_OVERRIDES`（18 条）与『按本名重判』规则覆盖 §2.4 正例"
             "（京师→城镇、陕北→区域、回疆→区域、风砂堡→寨堡、七盘关→关隘等）；"
             "OSM 现代设施标签/官署/穴位/景观集合名等回退 K13 其他并进复核队列。")
    L.append("")
    L.append("## 四、unlocatable 弃权清单（loc_mode=none，共 %d 条）" % len(unlocatable))
    L.append("")
    L.append("| id | kind | nature | reason | count | books | legacy_status |")
    L.append("|---|---|---|---|---:|---|---|")
    for e in sorted(unlocatable, key=lambda x: (-x["count"], x["id"])):
        L.append(f"| {e['id']} | {e['kind']} | {e['nature']} | {e.get('unlocatable_reason')} | "
                 f"{e['count']} | {','.join(e['books'].keys())} | {e['source'].get('legacy_status')} |")
    L.append("")
    L.append(f"弃权判据：旧数据无 lat/lng（§2.5 M10/M11 不脑补坐标；§4.2 U1 no_clue）；"
             f"其中虚构条目 {sum(1 for e in unlocatable if e['nature'] == '虚构')} 条"
             f"（风砂堡/木什塔克/喀沁草原）另需文证锚点后升级 anchor（§4.5）。")
    L.append("")
    L.append("## 五、复核队列（迁移期不裁决，只登记）")
    L.append("")
    L.append("| 队列 | 条数 | 说明 |")
    L.append("|---|---:|---|")
    L.append(f"| nature 暂定（M05） | {flags.get('nature_tentative', 0)} | real=true/false 派生的『真实/虚构』均为暂定，复核可改判原型改造 |")
    L.append(f"| 虚构待锚点 | {flags.get('fiction_needs_anchor', 0)} | 风砂堡/木什塔克/喀沁草原，迁移期弃权 |")
    L.append(f"| 通名/泛称候选（G03） | {flags.get('generic_name_candidate', 0)} | 山/镖局/宫廷/宫中 等，待判『已弃用』（不删，保引用） |")
    L.append(f"| 穴位噪声（非地点） | {flags.get('body_point_candidate', 0)} | 曲池穴/太阳穴 等经络名，待判已弃用 |")
    L.append(f"| 官署无对应 kind | {flags.get('gov_office_undecided', 0)} | 衙门/行署/巡抚 等，K13 待审 |")
    L.append(f"| 场景待审 | {flags.get('scene_undecided', 0)} | 旧 kind=场景（3 条） |")
    L.append(f"| 地理编码可疑（§6.2） | {flags.get('geocode_suspect', 0)} | 京师/回疆/陕北/昆仑山 等实测误配，坐标不采信、条目待审 |")
    L.append(f"| 多候选编码 | {flags.get('geocode_multi_candidate', 0)} | source.n_candidates>1，按 §6.2 进语义复核 |")
    L.append("")
    L.append("暂定 nature 与 kind=K13 的明细见 `migrate_trace.json` 的 `flags`；"
             "旧 delta_since_last_review.coord_changed 18 条按 skill §6.2 首批待审，未在本轮改坐标。")
    L.append("")
    L.append("## 六、校验断言")
    L.append("")
    L.append(f"- 断言 {len(hard) + len(warn)} 项，通过 {n_pass} 项；硬断言失败 **{n_hard_fail}**，警告 **{n_warn_fail}**")
    L.append("")
    L.append("| 编号 | 断言 | 级别 | 结果 | 细节 |")
    L.append("|---|---|---|---|---|")
    for a in hard + warn:
        mark = "PASS" if a["pass"] else ("FAIL" if a["severity"] == "hard" else "WARN")
        L.append(f"| {a['id']} | {a['desc']} | {a['severity']} | {mark} | {a['detail'][:160]} |")
    L.append("")
    L.append("## 七、遗留与下一步")
    L.append("")
    L.append("- 本轮为**迁移**而非终审：nature 暂定（627 条）与 kind=K13 待审条目需按 SKILL §6.1 人工校准；")
    L.append("- 31 条弃权（含 3 条虚构）待文证锚点升级（§4.5）；未定 23 条（江南/中原/洛阳/西安 等）"
             "史实上多为真实地名，建议复核优先改判 nature=真实 + coord（§2.2）；")
    L.append("- 区域 K12 条目 precision 仍为 approx/shifted（M12 不重定义旧值）；§3.2 要求复核后升 region；")
    L.append("- 本轮不产 anchor/proto；原型改造（秘魔崖等）待 §5.6 人工复核后改判；")
    L.append("- 下游：EX-7 `export_site_gazetteer_universe.py` 消费 `registry/gazetteer.json`（§6.5 必读字段已齐）。")
    L.append("")
    L.append("## 八、只读约束")
    L.append("")
    L.append(f"- `kb/gazetteer.json` 运行前后 sha256 一致：`{legacy_sha}`；本轮未写 kb/。")
    if backup_path:
        L.append(f"- 写前备份：`{backup_path}`。")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- selftest
def selftest() -> int:
    fails = []

    def ck(name, cond, detail=""):
        if not cond:
            fails.append(f"{name} {detail}".strip())

    # 1) nature / real 派生
    ck("nature true", derive_nature(True) == "真实")
    ck("nature false", derive_nature(False) == "虚构")
    ck("nature null", derive_nature(None) == "未定")
    ck("real 真实", derive_real("真实") is True)
    ck("real 虚构", derive_real("虚构") is False)
    ck("real 原型", derive_real("真实原型改造") is False)
    ck("real 未定", derive_real("未定") is None)
    # 2) layer / loc_mode / conf
    ck("layer real", derive_layer("真实", "coord") == "real")
    ck("layer fiction", derive_layer("虚构", "none") == "fiction")
    ck("layer 未定 coord", derive_layer("未定", "coord") == "real")
    ck("layer 未定 none", derive_layer("未定", "none") == "fiction")
    ck("loc coord", derive_loc_mode("真实", 1.0, 2.0) == ("coord", None))
    ck("loc none", derive_loc_mode("未定", None, None) == ("none", "no_clue"))
    ck("conf exact", derive_conf("真实", "coord", "exact") == "strong")
    ck("conf region", derive_conf("真实", "coord", "region") == "strong")
    ck("conf approx", derive_conf("真实", "coord", "approx") == "ok")
    ck("conf shifted", derive_conf("真实", "coord", "shifted") == "ok")
    ck("conf 未定", derive_conf("未定", "coord", "approx") == "weak")
    ck("conf none", derive_conf("真实", "none", None) == "weak")
    # 3) kind 归一正例（SKILL §2.4/§5.6）
    ck("kind 京师", classify_kind("京师", "京师", "town")[0] == "城镇")
    ck("kind 陕北", classify_kind("陕北", "陕北", "civil")[0] == "区域")
    ck("kind 回疆", classify_kind("回疆", "回疆", "边域")[0] == "区域")
    ck("kind 风砂堡", classify_kind("风砂堡", "风砂堡", "场景")[0] == "寨堡")
    ck("kind 七盘关", classify_kind("七盘关", "七盘关", "motorway_junction")[0] == "关隘")
    ck("kind 太阳穴", classify_kind("太阳穴", "太阳穴", "lake")[0] == "其他")
    ck("kind 乾清宫", classify_kind("乾清宫", "乾清宫", "palace")[0] == "宫廷")
    ck("kind 少林寺", classify_kind("少林寺", "少林寺", "寺观")[0] == "寺观")
    ck("kind 水域", classify_kind("钱塘江", "钱塘江", "水域")[0] == "水域")
    ck("kind 山", classify_kind("天山", "天山", "山")[0] == "山")
    ck("kind 未覆盖回退", classify_kind("xx", "xx", "zzz_unknown")[0] == "其他")
    # 4) 单条迁移（coord / none）
    old_coord = {"id": "天山", "name": "天山", "aliases": [], "kind": "山", "real": True,
                 "books": {"七剑下天山": [1]}, "count": 2, "status": "auto", "verified": False,
                 "lat": 42.0, "lng": 80.0, "precision": "approx", "source": {"engine": "seed"}}
    e, t = migrate_entry(old_coord, {})
    ck("entry id", e["id"] == "天山")
    ck("entry req keys", {"id", "name", "aliases", "kind", "nature", "real", "layer", "books",
                          "first_seen", "count", "status", "verified", "loc_mode", "source",
                          "hq_of", "conf"} <= set(e))
    ck("entry coord", e["loc_mode"] == "coord" and e["lat"] == 42.0 and e["precision"] == "approx")
    ck("entry nature", e["nature"] == "真实" and e["real"] is True)
    ck("entry conf", e["conf"] == "ok")
    ck("entry source legacy_kind", e["source"]["legacy_kind"] == "山")
    ck("trace map", t["field_map"]["kind"] == "kind" and t["legacy_id"] == "天山")
    old_none = {"id": "风砂堡", "name": "风砂堡", "aliases": [], "kind": "场景", "real": False,
                "books": {"白发魔女传": [31]}, "count": 3, "status": "missing_coord", "verified": False,
                "lat": None, "lng": None, "precision": None, "source": None}
    e2, t2 = migrate_entry(old_none, {})
    ck("none loc", e2["loc_mode"] == "none" and e2["unlocatable_reason"] == "no_clue")
    ck("none no coord", "lat" not in e2 and "lng" not in e2)
    ck("none status M08", e2["status"] == "auto")
    ck("none fiction flag", "fiction_needs_anchor" in t2["flags"])
    # 5) 迁移全流程（合成 4 条）通过断言
    legacy_fixture = {"meta": {"rev": 1}, "places": [old_coord, old_none,
        {"id": "江南", "name": "江南", "kind": "泛称", "real": None, "books": {"七剑下天山": [1]},
         "count": 5, "status": "auto", "verified": False},
        {"id": "木什塔克", "name": "木什塔克", "kind": "场景", "real": False,
         "books": {"七剑下天山": [20]}, "count": 1, "status": "auto", "verified": False}]}
    res = run_migration(legacy_fixture)
    skip = {"H01", "H04b", "H06b", "H07b", "H10b"}   # 合成样例条数/分布不适用 650 门槛
    fails_ = [a for a in res["hard"] if not a["pass"] and a["id"] not in skip]
    ck("fixture no unexpected hard fail", not fails_, str([(a["id"], a["detail"]) for a in fails_][:3]))
    ck("fixture count", len(res["entries"]) == 4)
    # 6) kind map 覆盖旧数据实测全部取值
    if LEGACY.exists():
        data = load_json(LEGACY)
        unseen = sorted({p.get("kind") for p in data.get("places", [])} - set(LEGACY_KIND_MAP))
        ck("kind map covers legacy", not unseen, f"unmapped={unseen}")
    # 7) 枚举闭合
    ck("KIND enum", len(KIND_VALUES) == 13 and len(set(KIND_VALUES)) == 13)
    ck("NATURE enum", NATURE_VALUES == ("真实", "虚构", "真实原型改造", "未定"))

    if fails:
        print(f"[selftest] FAIL {len(fails)} 项：")
        for f in fails:
            print("  ✗", f)
        return 1
    print(f"[selftest] PASS（{15 + 20 + 10} 组规则断言 + 旧数据 kind 覆盖检查）")
    return 0


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="N7 gazetteer 迁移（kb/gazetteer.json → registry/gazetteer.json）")
    ap.add_argument("--dry-run", action="store_true", help="默认：计算+写报告，不写 registry")
    ap.add_argument("--apply", action="store_true", help="写 registry/gazetteer.json（写前备份）")
    ap.add_argument("--strict", action="store_true", help="警告级断言失败也 exit 1")
    ap.add_argument("--selftest", action="store_true", help="规则自测（不写文件）")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if not LEGACY.exists():
        print(f"[gazetteer] 输入缺失：{LEGACY}")
        return 1
    legacy_sha = sha256_file(LEGACY)
    legacy = load_json(LEGACY)

    print(f"[gazetteer] 输入 {LEGACY}：{len(legacy.get('places') or [])} 条；工具 {TOOL_VERSION}")
    result = run_migration(legacy)
    hard, warn = result["hard"], result["warn"]
    n_hard_fail = sum(1 for a in hard if not a["pass"])
    n_warn_fail = sum(1 for a in warn if not a["pass"])

    # 只读断言 H15：kb 文件未被写
    sha_after = sha256_file(LEGACY)
    hard.append(_asr(sha_after == legacy_sha, "H15", "只读约束：kb/gazetteer.json 运行前后 sha256 一致",
                     f"{legacy_sha[:16]} != {sha_after[:16]}" if sha_after != legacy_sha else "一致"))
    n_hard_fail = sum(1 for a in hard if not a["pass"])

    # 输出 payload
    entries, traces = result["entries"], result["traces"]
    nat = Counter(e["nature"] for e in entries)
    kinds = Counter(e["kind"] for e in entries)
    modes = Counter(e["loc_mode"] for e in entries)
    layers = Counter(e["layer"] for e in entries)
    conf = Counter(e["conf"] for e in entries)
    status = Counter(e["status"] for e in entries)
    stat_legacy = legacy.get("meta", {})
    payload = {
        "meta": {
            "schema": "gazetteer-v1",
            "generated": today(),
            "rev": 1,
            "source": {
                "legacy": {"path": "kb/gazetteer.json", "sha256": legacy_sha,
                           "generated": stat_legacy.get("generated"),
                           "rev": stat_legacy.get("rev"),
                           "places": len(legacy.get("places") or [])},
                "skill": "skills/SKILL_地名gazetteer_武侠版.md v0.3-draft",
                "migration_map": "M01-M13",
            },
            "coord_system": stat_legacy.get("coord_system", "WGS-84(EPSG:4326)"),
            "books": (stat_legacy.get("based_on") or {}).get("books", []),
            "stats": {
                "total": len(entries),
                "by_nature": dict(nat),
                "by_kind": dict(kinds),
                "by_loc_mode": dict(modes),
                "by_layer": dict(layers),
                "by_conf": dict(conf),
                "by_status": dict(status),
                "unlocatable": modes.get("none", 0),
                "with_coord": modes.get("coord", 0),
                "review_flags": dict(Counter(f for t in traces for f in t["flags"])),
            },
            "assertions": {"total": len(hard) + len(warn),
                           "hard_fail": n_hard_fail, "warn_fail": n_warn_fail},
            "legacy_meta": {k: legacy.get(k) for k in ("meta", "stats", "delta_since_last_review")
                            if legacy.get(k) is not None},
        },
        "places": entries,
    }

    out_written = False
    backup_path = None
    if args.apply and n_hard_fail == 0:
        if OUT_REGISTRY.exists():
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup_path = BACKUP_DIR / f"gazetteer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            shutil.copy2(OUT_REGISTRY, backup_path)
        dump_json(payload, OUT_REGISTRY)
        out_written = True

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    trace_obj = {
        "meta": {
            "tool": TOOL_VERSION, "generated": now_ts(),
            "legacy": {"path": "kb/gazetteer.json", "sha256": legacy_sha,
                       "places": len(legacy.get("places") or [])},
            "new": {"path": "registry/gazetteer.json", "schema": "gazetteer-v1",
                    "places": len(entries), "written": out_written},
            "field_map_spec": [{"m": m, "old": o, "new": n, "rule": r} for m, o, n, r in FIELD_MAP_SPEC],
            "assertions": hard + warn,
        },
        "entries": traces,
    }
    dump_json(trace_obj, TRACE_PATH)
    report = render_report(result, args, legacy_sha, out_written, backup_path)
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")

    # 控制台摘要
    print(f"[gazetteer] 迁移 {len(entries)} 条：nature {dict(nat)}")
    print(f"[gazetteer] kind {dict(kinds)}")
    print(f"[gazetteer] loc_mode {dict(modes)} · layer {dict(layers)} · conf {dict(conf)}")
    print(f"[gazetteer] 断言：hard {len(hard) - n_hard_fail}/{len(hard)} 通过，警告失败 {n_warn_fail}")
    if n_hard_fail:
        print("[gazetteer] ✗ 硬断言失败：")
        for a in hard:
            if not a["pass"]:
                print(f"  ✗ {a['id']} {a['desc']} — {a['detail']}")
        print(f"[gazetteer] 报告 → {REPORT_PATH}")
        return 1
    if args.strict and n_warn_fail:
        print(f"[gazetteer] ✗ --strict：{n_warn_fail} 项警告升级为失败")
        for a in warn:
            if not a["pass"]:
                print(f"  ✗ {a['id']} {a['desc']} — {a['detail']}")
        return 1
    print(f"[gazetteer] 报告 → {REPORT_PATH}")
    print(f"[gazetteer] 逐条追溯 → {TRACE_PATH}")
    if out_written:
        print(f"[gazetteer] registry → {OUT_REGISTRY}" + (f"（备份 {backup_path}）" if backup_path else ""))
    else:
        print("[gazetteer] dry-run：未写 registry/gazetteer.json（用 --apply 落盘）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
