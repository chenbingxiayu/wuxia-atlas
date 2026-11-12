# -*- coding: utf-8 -*-
"""ratings_calibration.py —— 工具 E·E3 武评校准回填（W2-D4-B · 天山演示版总体方案 §4.3 C1，2026-11-11）。

比对人工抽检表（kb/校订/武评抽检.tsv，100 场：id/layer/book/loc/a/b/outcome/s/manual_ok/
manual_note）与自动裁决（site/data/matches.json，同 id 对局 outcome 一致性）：

  precision = outcome 一致场数 / 抽检场数（缺行——抽检表有 id 而 matches 无——不入分母，单独计数）

产物（只回填统计，**不改对局裁决**）：
  - site/data/ratings.json meta.calibration =
      {"sampled", "precision"(4 位小数/None), "agree", "disagree", "missing",
       "tsv"(抽检表), "disagree_tsv"(分歧清单), "note"}
  - kb/校订/武评抽检-分歧.tsv：不一致清单（列 manual_outcome/auto_outcome 对举），
    0 分歧 = 仅表头（显式记录零分歧）；供人工复核，**不自动改裁决**。

实现位置选型（任务书二选一）：**独立脚本在 ratings_whr 之后跑**——ratings_whr 每次重跑都以
占位骨架覆盖 meta.calibration（build_payload 硬编码 sampled:0 待办骨架），回填做进 E2 输出组装
仍会被下次 E2 重算覆盖；独立脚本 + run_pipeline 步骤列表（紧跟 ratings_whr）才闭环，
顺序由 wuxia-kb/tests/test_ratings_calibration.py::TestPipelineOrder 固化（测试即规范）。

--scope：接受但语义中性（比对按对局 id 全等，matches.json 已由 clean_matches 按 scope 裁定；
抽检 100 场 id 恒为其子集——W2-D4-B 测试固化）。全量口径跑法一致（R6）。

G1（2026-11-12）新增 --refresh-sample：抽检表 100 行系 F1 方向修正前自动裁决的机械副本
（manual_ok 全空=从未人工标注），方向修正后与 matches 出现 29 分歧——刷新口径（用户裁定：
表系机械副本非人工判断，随方向修正 v2 刷新）：按当前（已修正）matches.json 以「场景身份」
（book/loc/scene/双方——双方经 alias_overrides @ 映射归一）唯一命中重写 id/outcome/s/layer
（抽样结构 book/loc/a/b 与 manual_ok/manual_note 保留空；无后继行原样保留、计 missing），
刷新前备份 武评抽检.tsv.bak-<时间戳>-G1；随后照常比对回填 → 分歧归零。人工抽检待后续批次。

用法：python -X utf8 scripts/ratings_calibration.py [--refresh-sample] [--scope tianshan-demo]
覆盖写 site/data/ratings.json 前自动备份到 site/data/backup/cal_<时间戳>/ratings.json。
"""
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kb_discovery import SITE_DATA  # noqa: E402

# G1：人名归并映射来源（export_site_characters.load_alias_overrides，D9 单一校验源）
_WXKB_SCRIPTS = Path(__file__).resolve().parents[1] / "wuxia-kb" / "scripts"
if str(_WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WXKB_SCRIPTS))
import export_site_characters as exc  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TSV_PATH = ROOT / "kb" / "校订" / "武评抽检.tsv"
DISAGREE_TSV = ROOT / "kb" / "校订" / "武评抽检-分歧.tsv"
TSV_REL = "kb/校订/武评抽检.tsv"
DISAGREE_REL = "kb/校订/武评抽检-分歧.tsv"
PRECISION_BAR = 0.90  # 发布口径（ratings/method.astro「精度 ≥90% 方可发布」）

# 分歧清单列：抽检表原列 + manual/auto outcome 对举（原 outcome 列改名 manual_outcome 消歧）
DISAGREE_COLS = ["id", "layer", "book", "loc", "a", "b",
                 "manual_outcome", "auto_outcome", "s", "manual_ok", "manual_note"]

# 抽检表列（G1 --refresh-sample 回写口径：与既有表头逐列一致）
SAMPLE_COLS = ["id", "layer", "book", "loc", "a", "b", "outcome", "s", "manual_ok", "manual_note"]


def load_tsv(path) -> list:
    """抽检表 → 行字典列表（utf-8，制表符分隔；空文件/缺文件 → 空列表由调用方报错）。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def compare_rows(tsv_rows, matches) -> dict:
    """抽检行 × 自动裁决（同 id 对局 outcome 一致性）→ 统计（纯函数，不改输入）。

    sampled = id 命中 matches 的抽检行数（precision 分母）；missing = 缺行（单独报告，
    不入分母——无法比对的场次既不能证明一致也不能证明分歧）。
    """
    by_id = {m.get("id"): m for m in matches}
    sampled = agree = disagree = missing = 0
    disagree_rows, missing_ids = [], []
    for r in tsv_rows:
        m = by_id.get(r.get("id"))
        if m is None:
            missing += 1
            missing_ids.append(r.get("id"))
            continue
        sampled += 1
        manual_outcome = (r.get("outcome") or "").strip()
        auto_outcome = (m.get("outcome") or "").strip()
        if manual_outcome == auto_outcome:
            agree += 1
        else:
            disagree += 1
            row = dict(r)
            row["manual_outcome"] = manual_outcome
            row["auto_outcome"] = auto_outcome
            disagree_rows.append(row)
    precision = round(agree / sampled, 4) if sampled else None
    return {"sampled": sampled, "agree": agree, "disagree": disagree,
            "missing": missing, "missing_ids": missing_ids,
            "precision": precision, "disagree_rows": disagree_rows}


def build_calibration(res: dict) -> dict:
    """比对统计 → meta.calibration 载荷（回填字段结构：tsv 路径 + note 固化口径）。"""
    precision = round(res["precision"], 4) if res.get("precision") is not None else None
    return {
        "sampled": res["sampled"],
        "precision": precision,
        "agree": res["agree"],
        "disagree": res["disagree"],
        "missing": res["missing"],
        "tsv": TSV_REL,
        "disagree_tsv": DISAGREE_REL,
        "note": ("人工抽检 vs 自动裁决（matches 同 id 对局 outcome 一致性）；"
                 "precision=一致数/抽检数，缺行不入分母；分歧清单见 disagree_tsv 供人工复核；"
                 "只回填统计，不改对局裁决；抽检覆盖旧事件层 4 书场次"
                 "（registry 新源 3 书未经抽检）；"
                 "抽检表系自动裁决机械副本（manual_ok 全空，非人工判断），"
                 "已随方向修正 v2 刷新（2026-11-12，--refresh-sample 按当前 matches "
                 "重写 outcome/s/layer；id 按场景身份重指向——人名归并会平移 matches id 序列，"
                 "缺行=抽检对局无后继（随归并退场，不入分母）；人工抽检待后续批次）；"
                 "方向修正依据见 matches meta.note"),
    }


def write_disagree_tsv(path, disagree_rows) -> int:
    """分歧清单 → TSV（0 分歧 = 仅表头，显式记录零分歧）；返回行数。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=DISAGREE_COLS, delimiter="\t",
                           extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in disagree_rows:
            w.writerow(row)
    return len(disagree_rows)


def _fmt_s(v) -> str:
    """matches 软分数 → 抽检表 s 列字符串（旧表风格：1.0→"1.0"、0.85→"0.85"，非 "1"/"0.850000"）。"""
    try:
        return str(round(float(v), 4))
    except (TypeError, ValueError):
        return str(v if v is not None else "")


def refresh_rows(tsv_rows: list, matches: list, rename: dict | None = None) -> tuple[list, dict]:
    """抽检行按当前 matches 刷新 id/outcome/s/layer（纯函数，不改输入）→ (rows, stats)。

    G1 刷新口径：抽检表系机械副本非人工判断 → outcome/s/layer 直接取自动裁决；
    抽样结构（book/loc/a/b 原值）与 manual_ok/manual_note（保留空）原样。

    行解析以「场景身份」为主键：抽检行的抽样单元是对局场景（book/loc/双方），不是代理
    id——人名归并（alias_overrides）会增删/去重对局并平移 matches 的 id 序列，按 id 直查
    会把行指到另一场对局。故双方名经 rename（registry alias_overrides @ 映射）归一后，
    与当前 matches 同 (book, loc/scene) 且 {a,b} 恰等、唯一命中才刷新并重指 id（歧义不猜）；
    无后继的行原样保留（compare_rows 计 missing——如 008:093 李大人×白石道人 词表兜底
    低信任对局随归并退场）；若其旧 id 已被新空间占用（指向另一场对局，会与重指行撞车
    造成 compare 双计）→ id 清空以防误比（对局身份仍在 book/loc/a/b 结构里）。
    """
    rename = rename or {}
    # 索引两级场景身份：(book, loc, scene, {a,b}) 精确（同 loc 双战的场景码消歧）
    # → (book, loc, {a,b}) 兜底（场景码漂移时按 loc 唯一命中）
    by_full: dict = {}
    by_loc: dict = {}
    for m in matches:
        pair = frozenset((m.get("a"), m.get("b")))
        by_full.setdefault((m.get("book"), m.get("loc"), m.get("scene"), pair), []).append(m)
        by_loc.setdefault((m.get("book"), m.get("loc"), pair), []).append(m)
    live_ids = {m.get("id") for m in matches}
    rows, refreshed, remapped, emptied, missing_ids = [], 0, 0, 0, []

    def _resolve(r):
        """行 → 当前对局（场景身份唯一命中；两级索引；歧义不猜）。"""
        pair = frozenset((rename.get(r.get("a"), r.get("a")),
                          rename.get(r.get("b"), r.get("b"))))
        cands = by_full.get((r.get("book"), r.get("loc"), r.get("scene"), pair)) or []
        if len(cands) == 1:
            return cands[0]
        cands = by_loc.get((r.get("book"), r.get("loc"), pair)) or []
        return cands[0] if len(cands) == 1 else None

    for r in tsv_rows:
        m = _resolve(r)
        if m is None:
            nr = dict(r)
            if r.get("id") in live_ids:
                nr["id"] = ""          # 旧 id 已被新空间占用（另一场对局）——清空防 compare 双计
                emptied += 1
            rows.append(nr)
            missing_ids.append(r.get("id") or "(id 空·无后继)")
            continue
        if m.get("id") != r.get("id"):
            remapped += 1
        nr = dict(r)
        nr["id"] = m.get("id")
        nr["outcome"] = (m.get("outcome") or "").strip()
        nr["s"] = _fmt_s(m.get("s"))
        nr["layer"] = (m.get("layer") or r.get("layer") or "").strip()
        rows.append(nr)
        refreshed += 1
    return rows, {"refreshed": refreshed, "remapped": remapped, "emptied": emptied,
                  "kept_missing": len(missing_ids), "missing_ids": missing_ids}


def write_sample_tsv(path, rows: list) -> int:
    """抽检表回写（列序 SAMPLE_COLS、行序不变）；返回数据行数。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SAMPLE_COLS, delimiter="\t",
                           extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    return len(rows)


def backfill(payload: dict, calibration: dict) -> None:
    """回填 payload["meta"]["calibration"]（仅替换该键，meta 其余键/players/conflicts 原样）。"""
    payload.setdefault("meta", {})["calibration"] = calibration


def main() -> int:
    # --scope 接受但语义中性（见模块 docstring）：保持与管线其余步骤一致的参数面
    for args in (sys.argv[1:],):
        if "--scope" in args and (args.index("--scope") + 1 >= len(args)
                                  or args[args.index("--scope") + 1].startswith("--")):
            print("[calibration] --scope 缺少取值（用法：--scope <profile 名> 或 --scope all）")
            return 2
    if not TSV_PATH.exists():
        print(f"[calibration] ✗ 抽检表不存在：{TSV_PATH}")
        return 2
    matches_path = SITE_DATA / "matches.json"
    ratings_path = SITE_DATA / "ratings.json"
    if not matches_path.exists() or not ratings_path.exists():
        print(f"[calibration] ✗ 缺 {matches_path} 或 {ratings_path}（先跑 clean_matches/ratings_whr）")
        return 2

    tsv_rows = load_tsv(TSV_PATH)
    matches = json.loads(matches_path.read_text(encoding="utf-8")).get("matches", [])
    ratings = json.loads(ratings_path.read_text(encoding="utf-8"))

    # G1 --refresh-sample：抽检表系机械副本 → 按当前 matches 刷新 outcome/s/layer（备份先行）
    if "--refresh-sample" in sys.argv[1:]:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = TSV_PATH.with_name(f"{TSV_PATH.name}.bak-{stamp}-G1")
        shutil.copy2(TSV_PATH, bak)
        print(f"[calibration] 备份抽检表 -> {bak}")
        # 人名归并映射（registry alias_overrides @ 条目）——id 重指向时归一双方名
        _overrides, _meta = exc.load_alias_overrides()
        rename = {form: to_canon for (ftype, form), (to_type, to_canon) in _overrides.items()
                  if ftype == "@" and to_canon}
        tsv_rows, rstat = refresh_rows(tsv_rows, matches, rename=rename)
        write_sample_tsv(TSV_PATH, tsv_rows)
        print(f"[calibration] --refresh-sample：刷新 {rstat['refreshed']} 行"
              f"（outcome/s/layer 随当前 matches；id 按场景身份重指向 {rstat['remapped']} 行；"
              f"manual_ok 保留空；无后继 {rstat['kept_missing']} 行原样保留"
              f"{'：' + '、'.join(map(str, rstat['missing_ids'][:5])) if rstat['kept_missing'] else ''}）"
              f"-> {TSV_PATH}")

    res = compare_rows(tsv_rows, matches)

    # 覆盖写前备份 ratings.json（同 run_pipeline 备份纪律）
    if ratings_path.exists():
        dest = SITE_DATA / "backup" / f"cal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ratings_path, dest / ratings_path.name)
        print(f"[calibration] 备份 ratings.json → {dest}")

    write_disagree_tsv(DISAGREE_TSV, res["disagree_rows"])
    cal = build_calibration(res)
    backfill(ratings, cal)
    ratings_path.write_text(json.dumps(ratings, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[calibration] 抽检 {res['sampled']} 场 · 一致 {res['agree']} · 分歧 {res['disagree']} · "
          f"缺行 {res['missing']}（{('、'.join(map(str, res['missing_ids'][:5])) + ('…' if res['missing'] > 5 else '')) if res['missing'] else '无'}）"
          f" · precision={cal['precision']}")
    print(f"-> {ratings_path} meta.calibration 已回填；分歧清单 -> {DISAGREE_TSV}"
          f"（{len(res['disagree_rows'])} 行，0 行=零分歧）")
    if res["precision"] is not None and res["precision"] < PRECISION_BAR:
        print(f"⚠ precision {res['precision']:.2%} < {PRECISION_BAR:.0%} 发布线"
              f"（ratings/method.astro 校准口径）——请先人工复核分歧清单再发布")
    return 0


if __name__ == "__main__":
    sys.exit(main())
