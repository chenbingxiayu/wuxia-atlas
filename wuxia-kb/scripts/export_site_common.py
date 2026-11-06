# -*- coding: utf-8 -*-
"""EX 导出层公共设施（docs/51 §四/§六，2026-11-05 阶段 0）。

职责：
  1. 路径唯一来源（站点数据 / staging / 契约快照 / 报告 / 备份）
  2. 契约快照：把 site/data 现有 JSON 的类型+字段签名落盘，供各导出器比对
  3. 收尾：默认 dry-run 写 staging；--apply 才写 site/data（先自动备份）
  4. 差异报告：字段缺失/新增/类型不符/数量对比 → logs/export/reports/<name>.md

约定（docs/51 §五/§七）：
  - 导出器只读新管线产物（tagged/registry/concordance/wordlists）与旧 kb/ 只读资产；
    不写 tagged/registry/kb，不运行父仓旧脚本。
  - 输出 JSON 与旧站同风格：ensure_ascii=False, indent=1。
  - 旧站字段"字段不缺、类型不破"是底线；无法产出的字段置 null/空并写入 meta.field_gaps。

CLI：
  python scripts/export_site_common.py --snapshot-contracts   # 阶段 0：契约快照
  python scripts/export_site_common.py --backup              # 阶段 0：site/data 全量备份
  python scripts/export_site_common.py --status              # 查看 staging/报告/备份状态
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import config  # scripts/config.py：路径唯一来源

# ---------------------------------------------------------------- 路径
SITE_DATA = config.REPO_ROOT / "site" / "data"
EXPORT_ROOT = config.DIR_LOGS / "export"
STAGING = EXPORT_ROOT / "staging"
CONTRACTS_DIR = EXPORT_ROOT / "contracts"
REPORTS_DIR = EXPORT_ROOT / "reports"
BACKUP_ROOT = config.ROOT / "backup" / "site_data"

ATLAS_DIR = SITE_DATA / "atlas"
STAMP = datetime.now().strftime("%Y%m%d")

# 契约基线：2026-11-02 旧站构建产物（只读，diff 用）
BASELINE_STAMP = "20261102"
# 阶段 0 冻结快照（首次 --apply 后 site/data 已是新数据，legacy 对比必须读快照而非 live）
BASELINE_BACKUP = BACKUP_ROOT / "phase0_20261105"


# ---------------------------------------------------------------- 基础 IO
# 版权闸门规则 2 配套（2026-11-05 部署阻断③）：meta.provenance 中的 "tagged/" 属"出处说明"，
# 但发布产物不应出现语料目录字样；写盘前统一中性化为 "KB 标注层/"。
# 只改 **顶层 meta 的 provenance 字段**（source/notes/field_gaps/copyright 等），
# 正文、事件、摘录、数组内容一律不动（口径与 scripts/copyright_gate.py 的 provenance 白名单一致）。
PROVENANCE_NEUTRAL_KEYS = {
    "source", "source_detail", "sources", "provenance", "generated", "generated_at",
    "generated_by", "notes", "note", "field_gaps", "copyright", "policy", "schema",
    "build", "build_order", "snapshot", "tool", "skill", "spec",
}
TAGGED_TOKEN = "tagged/"
NEUTRAL_TOKEN = "KB 标注层/"


def neutralize_provenance_meta(payload):
    """meta.provenance 文本中性化（就地修改）：tagged/ → KB 标注层/；其余字段不动。"""
    meta = payload.get("meta") if isinstance(payload, dict) else None
    if not isinstance(meta, dict):
        return payload

    def fix(node, under_prov: bool):
        if isinstance(node, dict):
            return {k: fix(v, under_prov or k in PROVENANCE_NEUTRAL_KEYS) for k, v in node.items()}
        if isinstance(node, list):
            return [fix(v, under_prov) for v in node]
        if isinstance(node, str) and under_prov and TAGGED_TOKEN in node:
            return node.replace(TAGGED_TOKEN, NEUTRAL_TOKEN)
        return node

    for k in list(meta.keys()):
        meta[k] = fix(meta[k], k in PROVENANCE_NEUTRAL_KEYS)
    return payload


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_site(name: str):
    """读旧站数据（diff 基线）；文件不存在返回 None。"""
    p = SITE_DATA / name
    return load_json(p) if p.exists() else None


def load_baseline(name: str):
    """读阶段 0 冻结快照（2026-11-02 旧站基线）；快照缺失时回退 live site/data。

    用于"新旧对比/legacy 记录"语义：首次 --apply 后 live site/data 已是新导出，
    若继续用 load_site 会把旧数据当新数据自我对比（EX-6 source 全 legacy、EX-1 差异归零）。
    """
    p = BASELINE_BACKUP / name
    if p.exists():
        return load_json(p)
    return load_site(name)


def atomic_write_json(payload, path: Path, indent: int = 1) -> Path:
    """原子写：先写 .tmp 再替换，避免半截文件。

    写前对 meta.provenance 做中性化（tagged/ → KB 标注层/），避免版权闸门规则 2 误报；
    正文/引文不受影响（版权边界：provenance 是出处说明，非 Corpus 内容）。
    """
    neutralize_provenance_meta(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=indent)
        f.write("\n")
    tmp.replace(path)
    return path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_apply() -> bool:
    return "--apply" in sys.argv


# ---------------------------------------------------------------- 契约签名
def _type_of(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    return type(v).__name__


def _merge_types(a: set, b: set) -> set:
    return set(a) | set(b)


def signature(obj, depth: int = 0, max_depth: int = 5):
    """递归类型+字段签名（不含具体值，允许多类型）：用于跨版本契约对比。"""
    if isinstance(obj, dict):
        sig = {"type": "dict", "keys": {}}
        for k in sorted(obj.keys()):
            sig["keys"][k] = signature(obj[k], depth + 1, max_depth) if depth < max_depth else {"type": "any"}
        return sig
    if isinstance(obj, list):
        item_types: set = set()
        item_keys: dict = {}
        item_elem = None
        for v in obj:
            item_types.add(_type_of(v))
            if isinstance(v, dict):
                merged = {}
                for k, vv in v.items():
                    merged[k] = _merge_types(item_keys.get(k, set()), {_type_of(vv)})
                item_keys = merged
            elif item_elem is None:
                item_elem = signature(v, depth + 1, max_depth)
        sig = {"type": "array", "len": len(obj), "item_types": sorted(item_types)}
        if item_keys:
            sig["item_keys"] = {k: sorted(v) for k, v in item_keys.items()}
        elif item_elem is not None:
            sig["item"] = item_elem
        return sig
    return {"type": _type_of(obj)}


# ---------------------------------------------------------------- 契约快照
def contract_path(name: str) -> Path:
    return CONTRACTS_DIR / (name.replace("/", "_").replace("\\", "_") + ".schema.json")


def snapshot_contracts() -> Path:
    """阶段 0：把 site/data 全部 JSON 的契约签名 + 文件指纹落盘。"""
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(SITE_DATA.glob("*.json")) + sorted(ATLAS_DIR.glob("*.json"))
    manifest = {
        "generated": now_iso(),
        "baseline_stamp": BASELINE_STAMP,
        "site_data_dir": str(SITE_DATA),
        "files": {},
    }
    for p in files:
        rel = p.relative_to(SITE_DATA).as_posix()
        payload = load_json(p)
        sig = signature(payload)
        atomic_write_json(
            {"name": rel, "generated": now_iso(), "schema": sig},
            contract_path(rel),
        )
        manifest["files"][rel] = {
            "sha256": sha256_file(p),
            "bytes": p.stat().st_size,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "top_type": sig.get("type"),
            "record_count": _record_count(payload),
        }
    atomic_write_json(manifest, CONTRACTS_DIR / "_manifest.json")
    print(f"[contracts] 快照 {len(files)} 个文件 → {CONTRACTS_DIR}")
    return CONTRACTS_DIR


def _record_count(payload) -> int | None:
    """统计主数组长度（契约比对用）。"""
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for k in ("books", "entities", "dossiers", "sects", "weapons", "arts",
                  "places", "nodes", "matches", "players", "lines", "works"):
            if isinstance(payload.get(k), list):
                return len(payload[k])
        # chapters.json：meta + 每书对象
        n = 0
        for k, v in payload.items():
            if k == "meta" or not isinstance(v, dict):
                continue
            if isinstance(v.get("chapters"), list):
                n += len(v["chapters"])
        if n:
            return n
    return None


# ---------------------------------------------------------------- 差异比对
_TYPE_ALIASES = {"int": {"int", "float"}, "float": {"float", "int"}}


def _types_compatible(expected: set, actual: set) -> bool:
    if not expected:
        return True
    for e in expected:
        if e in actual:
            return True
        if e in _TYPE_ALIASES and (_TYPE_ALIASES[e] & actual):
            return True
    return False


def diff_against_contract(name: str, payload, contract: dict | None = None) -> dict:
    """新 payload vs 旧站契约签名：缺失字段/新增字段/类型不符/数量。"""
    contract = contract or load_json(contract_path(name))
    sig = contract["schema"]

    result = {
        "name": name,
        "old_record_count": _record_count_of_sig(sig),
        "new_record_count": _record_count(payload),
        "missing_keys": [],       # 旧契约有、新产出无（硬伤，必须补/说明）
        "extra_keys": [],         # 新产出有、旧契约无（允许）
        "type_mismatch": [],      # 字段类型不符（硬伤）
        "item_missing_keys": [],  # 数组元素缺旧契约字段
    }

    def walk(old_sig, new_val, path: str):
        if old_sig.get("type") == "dict":
            if not isinstance(new_val, dict):
                result["type_mismatch"].append({"path": path or "$", "expected": "dict", "actual": _type_of(new_val)})
                return
            old_keys = old_sig.get("keys", {})
            new_keys = set(new_val.keys())
            for k in sorted(set(old_keys) - new_keys):
                result["missing_keys"].append(f"{path}.{k}" if path else k)
            for k in sorted(new_keys - set(old_keys)):
                result["extra_keys"].append(f"{path}.{k}" if path else k)
            for k in sorted(set(old_keys) & new_keys):
                walk(old_keys[k], new_val[k], f"{path}.{k}" if path else k)
        elif old_sig.get("type") == "array":
            if not isinstance(new_val, list):
                result["type_mismatch"].append({"path": path or "$", "expected": "array", "actual": _type_of(new_val)})
                return
            old_item_keys = old_sig.get("item_keys") or {}
            for i, item in enumerate(new_val):
                if isinstance(item, dict) and old_item_keys:
                    miss = sorted(set(old_item_keys) - set(item.keys()))
                    if miss:
                        result["item_missing_keys"].append({"path": f"{path}[{i}]", "missing": miss})
                        if len(result["item_missing_keys"]) >= 20:
                            break
                elif old_sig.get("item") and isinstance(old_sig["item"], dict):
                    walk(old_sig["item"], item, f"{path}[{i}]")
        else:
            exp = {old_sig.get("type")} - {"null"}
            act = {_type_of(new_val)} - {"null"}
            if exp and act and not _types_compatible(exp, act):
                result["type_mismatch"].append({"path": path or "$", "expected": sorted(exp), "actual": sorted(act)})

    walk(sig, payload, "")
    total_missing = len(result["missing_keys"]) + len(result["item_missing_keys"]) + len(result["type_mismatch"])
    result["hard_gap_count"] = total_missing
    return result


def _record_count_of_sig(sig) -> int | None:
    """从契约签名反推旧记录数（与 _record_count 同口径）。"""
    if sig.get("type") == "array":
        return sig.get("len")
    if sig.get("type") == "dict":
        keys = sig.get("keys", {})
        for k in ("books", "entities", "dossiers", "sects", "weapons", "arts",
                  "places", "nodes", "matches", "players", "lines", "works"):
            if k in keys and keys[k].get("type") == "array":
                return keys[k].get("len")
        # chapters.json：meta + 每书对象 {chapters, lit?, kb?}
        n = 0
        for k, v in keys.items():
            if k == "meta" or v.get("type") != "dict":
                continue
            ch = v.get("keys", {}).get("chapters")
            if ch and ch.get("type") == "array":
                n += ch.get("len", 0)
        if n:
            return n
    return None


# ---------------------------------------------------------------- 收尾（导出器调用）
def field_gaps(payload) -> list:
    meta = payload.get("meta") if isinstance(payload, dict) else None
    if isinstance(meta, dict):
        return list(meta.get("field_gaps") or [])
    return []


def finish(name: str, payload, exporter: str = "", notes: str = "") -> dict:
    """导出器统一收尾：diff + staging 写盘 + 报告；--apply 才写 site/data（先备份）。

    返回 diff dict（供导出器 / 集成脚本汇总）。
    """
    diff = diff_against_contract(name, payload)
    STAGING.mkdir(parents=True, exist_ok=True)
    REPORT_DIR = REPORTS_DIR
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    staged = atomic_write_json(payload, STAGING / name)

    apply = is_apply()
    applied = None
    if apply:
        target = SITE_DATA / name
        if target.exists():
            backup_run = BACKUP_ROOT / f"apply_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_run.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_run / name.replace("/", "_"))
        applied = atomic_write_json(payload, target)

    report = _render_report(name, exporter, diff, payload, staged, applied, notes)
    report_path = REPORT_DIR / (name.replace("/", "_").replace(".json", "") + "_report.md")
    report_path.write_text(report, encoding="utf-8")
    print(
        f"[export] {name}: records={diff['new_record_count']} "
        f"hard_gaps={diff['hard_gap_count']} "
        f"staging={staged} {'APPLIED→' + str(applied) if applied else '(dry-run)'}"
    )
    return diff


def _render_report(name, exporter, diff, payload, staged, applied, notes) -> str:
    meta = payload.get("meta") if isinstance(payload, dict) else {}
    gaps = field_gaps(payload) if isinstance(payload, dict) else []
    lines = [
        f"# 导出报告 · {name}",
        "",
        f"- 导出器：{exporter}",
        f"- 时间：{now_iso()}",
        f"- 模式：{'APPLY（已写 site/data）' if applied else 'dry-run（仅 staging）'}",
        f"- staging：`{staged}`",
        f"- 旧契约记录数：{diff['old_record_count']} · 新产出记录数：{diff['new_record_count']}",
        f"- meta：{json.dumps(meta, ensure_ascii=False)[:500]}",
        "",
        "## 契约硬缺口（必须为 0 或逐项说明）",
        f"- hard_gap_count = **{diff['hard_gap_count']}**",
        "",
    ]
    if diff["missing_keys"]:
        lines.append("### 缺失字段（旧契约有、新产出无）")
        lines += [f"- `{k}`" for k in diff["missing_keys"][:60]]
        if len(diff["missing_keys"]) > 60:
            lines.append(f"- … 另 {len(diff['missing_keys']) - 60} 项")
        lines.append("")
    if diff["type_mismatch"]:
        lines.append("### 类型不符")
        lines += [f"- `{x['path']}`：{x['expected']} → {x['actual']}" for x in diff["type_mismatch"][:40]]
        lines.append("")
    if diff["item_missing_keys"]:
        lines.append("### 数组元素缺字段（前 20 条）")
        lines += [f"- `{x['path']}` 缺 {x['missing']}" for x in diff["item_missing_keys"]]
        lines.append("")
    if diff["extra_keys"]:
        lines.append(f"### 新增字段（允许，{len(diff['extra_keys'])} 项，前 30）")
        lines += [f"- `{k}`" for k in diff["extra_keys"][:30]]
        lines.append("")
    if gaps:
        lines.append("### field_gaps（新数据暂缺、按 docs/51 §五 显式声明）")
        lines += [f"- {g}" for g in gaps[:60]]
        lines.append("")
    if notes:
        lines += ["## 说明", notes, ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- 备份 / 状态
def backup_site_data(tag: str = f"phase0_{STAMP}") -> Path:
    """阶段 0：site/data 全量快照（保留目录结构）。"""
    dest = BACKUP_ROOT / tag
    if dest.exists():
        print(f"[backup] 已存在，跳过：{dest}")
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(SITE_DATA.rglob("*")):
        if p.is_file():
            rel = p.relative_to(SITE_DATA)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            n += 1
    manifest = {
        "generated": now_iso(),
        "source": str(SITE_DATA),
        "files": n,
        "sha256": {p.relative_to(SITE_DATA).as_posix(): sha256_file(p)
                   for p in sorted(SITE_DATA.rglob("*.json"))},
    }
    atomic_write_json(manifest, dest / "_manifest.json")
    print(f"[backup] {n} 个文件 → {dest}")
    return dest


def status() -> None:
    print(f"SITE_DATA   = {SITE_DATA} ({len(list(SITE_DATA.glob('*.json')))} json)")
    print(f"STAGING     = {STAGING} ({len(list(STAGING.glob('*.json'))) if STAGING.exists() else 0} json)")
    print(f"CONTRACTS   = {CONTRACTS_DIR} ({len(list(CONTRACTS_DIR.glob('*.schema.json'))) if CONTRACTS_DIR.exists() else 0})")
    print(f"REPORTS     = {REPORTS_DIR}")
    if BACKUP_ROOT.exists():
        print(f"BACKUPS     = {[p.name for p in sorted(BACKUP_ROOT.iterdir()) if p.is_dir()]}")


def main():
    if "--snapshot-contracts" in sys.argv:
        snapshot_contracts()
    elif "--backup" in sys.argv:
        backup_site_data()
    elif "--status" in sys.argv:
        status()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
