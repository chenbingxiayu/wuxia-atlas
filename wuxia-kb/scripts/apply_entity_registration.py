# -*- coding: utf-8 -*-
"""S-03b · 登记提案合并器（apply_entity_registration.py，2026-11-05 / task-74 修复版）。

把 `propose_entity_registration.py` 产出的登记提案合并进 `registry/entities.json`。

## 提案位置（自动探测，2026-11-05 子目录化口径）

    registry/patches/<书>/<书>_entity_registration.json     ← 现行（propose 输出）
    registry/patches/<书>_entity_registration.json          ← 旧扁平稿（兼容）

## 设计要点

  * **现读现写 + 并发 CAS**：合并前记录 entities.json 的 sha256；`--apply` 写前重读比对，
    若被其它任务改过则中止并提示重跑（不丢更新）；
  * **id 延迟分配**：合并时按现存 max(id 数字后缀)+1 顺延（E%04d），提案不携带 id；
  * **alias_additions**：追加进目标条目 aliases（已有则跳过；目标 id 缺失则告警跳过）；
  * **写前备份**：entities.json → `registry/patches/<书>/_backup_entities_<时间戳>.json`；
  * **写后校验**：id 唯一、(type, canonical) 唯一、条目数 = 旧 + 新增；失败自动回滚；
  * **原子写**：同目录临时文件 + os.replace；
  * **异常化**：关键检查用 `raise ApplyError`（`python -O` 下仍生效），不用 assert。

## 用法

    python scripts/apply_entity_registration.py --book 七剑下天山            # dry-run
    python scripts/apply_entity_registration.py --book 七剑下天山 --apply
    python scripts/apply_entity_registration.py --selftest                  # 合成用例自检

退出码：0 成功；1 自检失败/写后校验失败；2 输入缺失/格式错；3 并发冲突。
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config  # noqa: E402

ID_NUM_RE = re.compile(r"^E(\d+)$")
PROPOSAL_SCHEMA = "entity_registration_proposal/v1"
SCOPE_TYPES = ("@", "◆", "&")
ALLOWED_STATUS = ("proposed", "approved", "pending")
PAREN_RE = re.compile(r"[（(]")


class ApplyError(Exception):
    """输入/校验/并发类错误（由 main 转成退出码）。"""

    def __init__(self, message, exit_code=2):
        super().__init__(message)
        self.exit_code = exit_code


# ---------------------------------------------------------------- 基础 ----
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def proposal_candidates(book: str, patches_root: Path):
    """提案候选路径（现行子目录优先，旧扁平稿兜底）。"""
    return [patches_root / book / f"{book}_entity_registration.json",
            patches_root / f"{book}_entity_registration.json"]


def find_proposal(book: str, patches_root: Path, explicit: Path | None = None) -> Path:
    if explicit is not None:
        if not explicit.exists():
            raise ApplyError(f"提案文件不存在：{explicit}\n"
                             f"  生成方法：python scripts/propose_entity_registration.py --book {book}")
        return explicit
    cands = proposal_candidates(book, patches_root)
    for p in cands:
        if p.exists():
            return p
    lines = "\n".join(f"  - {p}" for p in cands)
    raise ApplyError(
        f"未找到《{book}》的登记提案（已探测：\n{lines}\n）\n"
        f"  生成方法：python scripts/propose_entity_registration.py --book {book}\n"
        f"  （propose 输出 registry/patches/{book}/{book}_entity_registration.json；"
        f"旧扁平稿 registry/patches/{book}_entity_registration.json 亦兼容）")


def load_json_file(path: Path, what: str) -> dict:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise ApplyError(f"{what}不存在：{path}")
    except OSError as e:
        raise ApplyError(f"{what}读取失败：{path}（{type(e).__name__}: {e}）")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ApplyError(f"{what}不是合法 UTF-8 JSON：{path}（{type(e).__name__}: {e}）")
    if not isinstance(data, dict):
        raise ApplyError(f"{what}顶层必须是 JSON 对象：{path}（实际 {type(data).__name__}）")
    return data


# ---------------------------------------------------------------- 校验 ----
def _require(cond, message):
    if not cond:
        raise ApplyError(message)


def validate_proposal(prop: dict, book: str, prop_path: Path | None = None) -> dict:
    """提案 schema/book/字段校验；返回规范化副本（strip 字符串、去重 aliases）。"""
    where = f"（{prop_path}）" if prop_path else ""
    _require(prop.get("schema") == PROPOSAL_SCHEMA,
             f"提案 schema 不符{where}：期望 {PROPOSAL_SCHEMA!r}，"
             f"实际 {prop.get('schema')!r}；请用 propose_entity_registration.py 重新生成")
    _require(prop.get("book") == book,
             f"提案 book 与 --book 不一致{where}：提案 {prop.get('book')!r} / 参数 {book!r}；"
             f"请确认提案归属书后重跑")
    entities = prop.get("entities")
    _require(isinstance(entities, list), f"提案 entities 必须是数组{where}")
    alias_adds = prop.get("alias_additions", [])
    _require(isinstance(alias_adds, list), f"提案 alias_additions 必须是数组{where}")

    norm_entities = []
    for i, p in enumerate(entities):
        tag = f"entities[{i}]"
        _require(isinstance(p, dict), f"提案 {tag} 必须是对象{where}")
        t = str(p.get("type") or "").strip()
        _require(t in SCOPE_TYPES,
                 f"提案 {tag}.type={t!r} 非法{where}：只登记 {'/'.join(SCOPE_TYPES)}（S-03b §九）")
        canon = str(p.get("canonical") or "").strip()
        _require(bool(canon), f"提案 {tag}.canonical 为空{where}")
        _require(not PAREN_RE.search(canon),
                 f"提案 {tag}.canonical 含括注{where}：{canon!r}（括注不入 canonical）")
        aliases = p.get("aliases") or []
        _require(isinstance(aliases, list), f"提案 {tag}.aliases 必须是数组{where}")
        norm_aliases, seen = [], set()
        for a in aliases:
            a = str(a or "").strip()
            if not a or a == canon or a in seen:
                continue
            seen.add(a)
            norm_aliases.append(a)
        sources = p.get("sources") or []
        _require(isinstance(sources, list), f"提案 {tag}.sources 必须是数组{where}")
        status = str(p.get("status") or "proposed").strip()
        _require(status in ALLOWED_STATUS,
                 f"提案 {tag}.status={status!r} 非法{where}：允许 {'/'.join(ALLOWED_STATUS)}")
        note = p.get("note", "")
        _require(isinstance(note, str), f"提案 {tag}.note 必须是字符串{where}")
        norm_entities.append({"type": t, "canonical": canon, "aliases": norm_aliases,
                              "sources": [str(s).strip() for s in sources if str(s).strip()],
                              "status": status, "note": note})

    norm_adds = []
    for i, a in enumerate(alias_adds):
        tag = f"alias_additions[{i}]"
        _require(isinstance(a, dict), f"提案 {tag} 必须是对象{where}")
        tid = str(a.get("target_id") or "").strip()
        _require(bool(ID_NUM_RE.match(tid)),
                 f"提案 {tag}.target_id={tid!r} 非法{where}：应形如 E0123")
        alias = str(a.get("add_alias") or "").strip()
        _require(bool(alias), f"提案 {tag}.add_alias 为空{where}")
        norm_adds.append({"target_id": tid, "add_alias": alias})

    out = dict(prop)
    out["entities"] = norm_entities
    out["alias_additions"] = norm_adds
    return out


def validate_registry(entities) -> None:
    """既有登记表结构校验：数组、id/canonical 必填、id 唯一。"""
    _require(isinstance(entities, list), "entities.json 的 entities 必须是数组")
    ids = set()
    for i, e in enumerate(entities):
        _require(isinstance(e, dict), f"entities[{i}] 不是对象")
        eid = str(e.get("id") or "").strip()
        _require(bool(eid), f"entities[{i}] 缺 id")
        _require(eid not in ids, f"entities.json 存在重复 id：{eid}（请先修复登记表再合并）")
        ids.add(eid)
        _require(bool(str(e.get("canonical") or "").strip()),
                 f"entities[{i}]（{eid}）缺 canonical")
        _require(str(e.get("type") or "").strip() != "",
                 f"entities[{i}]（{eid}）缺 type")


# ---------------------------------------------------------------- 合并 ----
def next_id(existing_ids) -> str:
    """从现存最大 id 顺延 +1（提案不携带 id；合并时分配防并发冲突）。"""
    nums = [int(m.group(1)) for i in existing_ids if (m := ID_NUM_RE.match(str(i)))]
    base = max(nums) if nums else 0
    return f"E{base + 1:04d}"


def merge(entities, prop):
    """→ (new_entries, skipped_dup, alias_done, alias_missing)。不修改 entities。"""
    canon_keys = {(e["type"], e["canonical"]) for e in entities}
    new_entries, skipped_dup = [], []
    for p in prop["entities"]:
        key = (p["type"], p["canonical"])
        if key in canon_keys:
            skipped_dup.append(p["canonical"])
            continue
        canon_keys.add(key)
        new_entries.append(p)
    by_id = {str(e.get("id")): e for e in entities}
    alias_done, alias_missing = [], []
    for a in prop.get("alias_additions") or []:
        tgt = by_id.get(a["target_id"])
        if tgt is None:
            alias_missing.append(a)
            continue
        if a["add_alias"] == tgt.get("canonical"):
            # 同名别名无信息量，且会制造 alias==canonical 瑕疵（task-65 已清理同类）→ 跳过
            alias_done.append((a["add_alias"], tgt.get("canonical"), "同名跳过"))
            continue
        aliases = tgt.setdefault("aliases", [])
        if a["add_alias"] in aliases:
            alias_done.append((a["add_alias"], tgt.get("canonical"), "已存在"))
        else:
            aliases.append(a["add_alias"])
            alias_done.append((a["add_alias"], tgt.get("canonical"), "已追加"))
    return new_entries, skipped_dup, alias_done, alias_missing


def append_entities(entities, new_entries):
    """按 id 顺延追加新实体（返回新增条目列表）。"""
    ids = {str(e.get("id")) for e in entities}
    added = []
    for p in new_entries:
        nid = next_id(ids)
        ids.add(nid)
        rec = {"id": nid, "type": p["type"], "canonical": p["canonical"],
               "aliases": list(p.get("aliases") or []), "contextual": [],
               "sources": list(p.get("sources") or []),
               "status": p.get("status", "proposed"), "note": p.get("note", "")}
        entities.append(rec)
        added.append(rec)
    return added


def check_invariants(entities, old_count, added_count):
    ids = [str(e.get("id")) for e in entities]
    if len(ids) != len(set(ids)):
        dup = sorted({i for i in ids if ids.count(i) > 1})[:5]
        raise ApplyError(f"写后校验失败：id 重复 {dup}", exit_code=1)
    keys = [(e.get("type"), e.get("canonical")) for e in entities]
    if len(keys) != len(set(keys)):
        dup = [k for k in keys if keys.count(k) > 1][:5]
        raise ApplyError(f"写后校验失败：(type, canonical) 重复 {dup}", exit_code=1)
    if len(entities) != old_count + added_count:
        raise ApplyError(f"写后校验失败：条目数 {len(entities)} ≠ 旧 {old_count} + 新增 {added_count}",
                         exit_code=1)


# ---------------------------------------------------------------- 写盘 ----
def serialize_registry(data: dict) -> bytes:
    data["generated"] = datetime.now().isoformat(timespec="seconds")
    return (json.dumps(data, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def write_with_cas(ent_path: Path, new_bytes: bytes, expected_sha: str,
                   backup_dir: Path | None = None) -> Path:
    """CAS 校验 → 备份 → 原子写 → 回读校验；失败回滚。返回备份路径。"""
    try:
        current = ent_path.read_bytes()
    except OSError as e:
        raise ApplyError(f"写前读取 entities.json 失败：{ent_path}（{e}）")
    now_sha = sha256_bytes(current)
    if now_sha != expected_sha:
        raise ApplyError(
            f"并发冲突：entities.json 在本次合并期间被其它任务修改"
            f"（sha256 {expected_sha[:8]}… → {now_sha[:8]}…）。已中止、未写入；请重跑。",
            exit_code=3)
    backup = None
    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"_backup_entities_{datetime.now():%Y%m%d_%H%M%S}.json"
        backup.write_bytes(current)
    tmp = ent_path.with_name(ent_path.name + f".tmp{os.getpid()}")
    try:
        tmp.write_bytes(new_bytes)
        os.replace(tmp, ent_path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    # 回读校验；失败回滚
    try:
        written = json.loads(ent_path.read_bytes().decode("utf-8"))
        _require(isinstance(written, dict) and isinstance(written.get("entities"), list),
                 "写后回读：entities 结构异常")
    except (json.JSONDecodeError, UnicodeDecodeError, ApplyError) as e:
        if backup is not None and backup.exists():
            shutil.copyfile(backup, ent_path)
        raise ApplyError(f"写后回读失败，已回滚到备份：{e}", exit_code=1)
    return backup


# ---------------------------------------------------------------- CLI ----
def run(book, patches_root, registry_path, proposal_path, apply):
    prop_path = find_proposal(book, patches_root, explicit=proposal_path)
    prop = load_json_file(prop_path, "提案文件")
    prop = validate_proposal(prop, book, prop_path)
    reg = load_json_file(registry_path, "登记表")
    entities = reg.get("entities")
    validate_registry(entities)
    reg_bytes = registry_path.read_bytes()
    reg_sha = sha256_bytes(reg_bytes)

    old_count = len(entities)
    new_entries, skipped_dup, alias_done, alias_missing = merge(entities, prop)
    print(f"提案来源：{prop_path}")
    print(f"提案 {len(prop['entities'])} 条 → 新增 {len(new_entries)}，"
          f"已在册跳过 {len(skipped_dup)}；别名并入 {len(alias_done)}（缺目标 {len(alias_missing)}）")
    for c in skipped_dup[:5]:
        print(f"  [dup-skip] {c}")
    for a, tgt, st in alias_done:
        print(f"  [alias-{st}] {a} → {tgt}")
    for a in alias_missing:
        print(f"  [alias-MISSING] {a['add_alias']} → id {a['target_id']} 未找到（跳过）")

    if not new_entries and not any(st == "已追加" for _, _, st in alias_done):
        print("无可合并项（幂等：提案已全部在册）。")
        return 0
    if not apply:
        print(f"\n(dry-run；确认后加 --apply。合并前 CAS 将校验 entities.json sha256={reg_sha[:8]}…)")
        return 0

    added = append_entities(entities, new_entries)
    check_invariants(entities, old_count, len(added))
    new_bytes = serialize_registry(reg)
    backup = write_with_cas(registry_path, new_bytes, reg_sha,
                            backup_dir=patches_root / book)
    print(f"\n[ok] 备份 → {backup}")
    print(f"[ok] 写入 {registry_path}：+{len(added)} 新实体（id {added[0]['id']}…{added[-1]['id']}），"
          f"别名 +{sum(1 for _, _, st in alias_done if st == '已追加')}，总数 {len(entities)}")
    return 0


# ---------------------------------------------------------------- 自检 ----
def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _selftest_case(name, fn):
    try:
        fn()
    except Exception as e:      # noqa: BLE001 - 自检需汇总所有失败
        print(f"[FAIL] {name}: {type(e).__name__}: {e}")
        return False
    print(f"[PASS] {name}")
    return True


def selftest() -> int:
    """合成提案自检：新实体/别名并入/重复 id/id 顺延/幂等/校验/并发 CAS。"""
    results = []

    def case_new_and_alias():
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            reg = {"version": "test", "entities": [
                {"id": "E0001", "type": "@", "canonical": "甲", "aliases": ["甲某"]},
                {"id": "E0005", "type": "@", "canonical": "乙", "aliases": []},
            ]}
            prop = {"schema": PROPOSAL_SCHEMA, "book": "测试书", "entities": [
                {"type": "@", "canonical": "丙", "aliases": ["丙某"], "sources": ["001"],
                 "status": "proposed", "note": "t"},
                {"type": "◆", "canonical": "丁", "aliases": [], "sources": ["002"]},
            ], "alias_additions": [
                {"target_id": "E0001", "add_alias": "甲老"},
                {"target_id": "E0001", "add_alias": "甲某"},   # 已存在 → 跳过
                {"target_id": "E0001", "add_alias": "甲"},     # 同名 → 跳过（防 alias==canonical）
            ]}
            ent_path = td / "entities.json"
            _write_json(ent_path, reg)
            _write_json(td / "patches" / "测试书" / "测试书_entity_registration.json", prop)
            rc = run("测试书", td / "patches", ent_path, None, apply=True)
            _require(rc == 0, f"run rc={rc}")
            out = json.loads(ent_path.read_text(encoding="utf-8"))
            ents = out["entities"]
            _require(len(ents) == 4, f"新增后条目数 {len(ents)} != 4")
            ids = [e["id"] for e in ents]
            _require(ids[-2:] == ["E0006", "E0007"], f"id 顺延异常 {ids}")
            _require("甲老" in ents[0]["aliases"], "别名未并入")
            _require("甲某" in ents[0]["aliases"], "已有别名被破坏")
            _require("甲" not in ents[0]["aliases"], "同名别名未跳过（会制造 alias==canonical）")

    def case_idempotent():
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            ent_path = td / "entities.json"
            _write_json(ent_path, {"version": "t", "entities": [
                {"id": "E0001", "type": "@", "canonical": "甲", "aliases": []}]})
            _write_json(td / "patches" / "测试书" / "测试书_entity_registration.json",
                        {"schema": PROPOSAL_SCHEMA, "book": "测试书",
                         "entities": [{"type": "@", "canonical": "乙"}],
                         "alias_additions": []})
            _require(run("测试书", td / "patches", ent_path, None, apply=True) == 0, "首跑失败")
            before = ent_path.read_bytes()
            _require(run("测试书", td / "patches", ent_path, None, apply=True) == 0, "二跑失败")
            _require(ent_path.read_bytes() == before, "幂等失败：二次 apply 改写了文件")

    def case_dup_id_rejected():
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            ent_path = td / "entities.json"
            _write_json(ent_path, {"version": "t", "entities": [
                {"id": "E0001", "type": "@", "canonical": "甲"},
                {"id": "E0001", "type": "@", "canonical": "乙"}]})
            _write_json(td / "patches" / "测试书" / "测试书_entity_registration.json",
                        {"schema": PROPOSAL_SCHEMA, "book": "测试书",
                         "entities": [{"type": "@", "canonical": "丙"}]})
            try:
                run("测试书", td / "patches", ent_path, None, apply=True)
            except ApplyError as e:
                _require("重复 id" in str(e), f"错误信息不符：{e}")
                return
            raise AssertionError("重复 id 未被拒绝")

    def case_schema_and_book_validation():
        prop = {"schema": "bad", "book": "甲书", "entities": []}
        for p, msg in [(prop, "schema"), (dict(prop, schema=PROPOSAL_SCHEMA, book="乙书"), "book"),
                       ({"schema": PROPOSAL_SCHEMA, "book": "甲书",
                         "entities": [{"type": "@", "canonical": "丙", "aliases": "坏"}]}, "aliases")]:
            try:
                validate_proposal(p, "甲书")
            except ApplyError as e:
                _require(msg in str(e), f"期望 {msg} 错误，实际：{e}")
            else:
                raise AssertionError(f"未拒绝非法提案（{msg}）")
        try:
            validate_proposal({"schema": PROPOSAL_SCHEMA, "book": "甲书",
                               "entities": [{"type": "☆", "canonical": "丙"}]}, "甲书")
        except ApplyError as e:
            _require("type" in str(e), f"type 错误信息不符：{e}")
        else:
            raise AssertionError("非法 type 未拒绝")

    def case_missing_proposal_friendly():
        with tempfile.TemporaryDirectory() as td:
            try:
                find_proposal("无提案书", Path(td))
            except ApplyError as e:
                _require("propose_entity_registration.py" in str(e), "缺 propose 提示")
                _require("无提案书" in str(e), "缺书名")
                _require(e.exit_code == 2, "exit_code 应为 2")
                return
            raise AssertionError("缺失提案未报错")

    def case_cas_conflict():
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            ent_path = td / "entities.json"
            _write_json(ent_path, {"version": "t", "entities": []})
            expected = sha256_bytes(ent_path.read_bytes())
            _write_json(ent_path, {"version": "t", "entities": [{"id": "E9999", "type": "@",
                                                                 "canonical": "并发"}]})
            try:
                write_with_cas(ent_path, b"{}\n", expected)
            except ApplyError as e:
                _require(e.exit_code == 3, f"CAS exit_code={e.exit_code} != 3")
                _require("并发冲突" in str(e), f"CAS 错误信息不符：{e}")
                return
            raise AssertionError("CAS 冲突未中止")

    def case_atomic_and_backup():
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            ent_path = td / "entities.json"
            _write_json(ent_path, {"version": "t", "entities": [{"id": "E0001", "type": "@",
                                                                 "canonical": "甲"}]})
            sha = sha256_bytes(ent_path.read_bytes())
            backup = write_with_cas(ent_path, b'{"version": "t2", "entities": []}\n', sha,
                                    backup_dir=td / "patches" / "书")
            _require(backup is not None and backup.exists(), "备份未生成")
            _require(json.loads(ent_path.read_text(encoding="utf-8"))["version"] == "t2", "写入失败")

    cases = [
        ("新实体 + 别名并入 + id 顺延", case_new_and_alias),
        ("幂等（二次 apply 不改写）", case_idempotent),
        ("重复 id 拒绝", case_dup_id_rejected),
        ("schema/book/type/aliases 校验", case_schema_and_book_validation),
        ("提案缺失友好报错（exit 2）", case_missing_proposal_friendly),
        ("并发 CAS 冲突中止（exit 3）", case_cas_conflict),
        ("原子写 + 备份", case_atomic_and_backup),
    ]
    for name, fn in cases:
        results.append(_selftest_case(name, fn))
    ok = sum(results)
    print(f"\nSELFTEST {ok}/{len(results)} PASS")
    return 0 if ok == len(results) else 1


def main():
    ap = argparse.ArgumentParser(description="合并登记提案 → entities.json（现读现写+CAS+备份）")
    ap.add_argument("--book", help="书名（config.books() 键）")
    ap.add_argument("--apply", action="store_true", help="默认 dry-run；加此参数才写盘")
    ap.add_argument("--selftest", action="store_true", help="合成提案自检（不触碰仓库数据）")
    ap.add_argument("--proposal", default=None, metavar="PATH",
                    help="显式提案路径（缺省自动探测子目录/旧扁平稿）")
    ap.add_argument("--registry", default=None, metavar="PATH",
                    help="登记表路径（缺省 registry/entities.json；沙盒测试用）")
    ap.add_argument("--patches-root", default=None, metavar="PATH",
                    help="提案根目录（缺省 registry/patches；沙盒测试用）")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.book:
        print("[ERROR] 需要 --book（或 --selftest）", file=sys.stderr)
        return 2
    patches_root = Path(args.patches_root) if args.patches_root else (config.DIR_REGISTRY / "patches")
    registry_path = Path(args.registry) if args.registry else (config.DIR_REGISTRY / "entities.json")
    proposal_path = Path(args.proposal) if args.proposal else None
    try:
        return run(args.book, patches_root, registry_path, proposal_path, args.apply)
    except ApplyError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return e.exit_code


if __name__ == "__main__":
    sys.exit(main())
