# -*- coding: utf-8 -*-
"""@ 人物管道规范名回填 —— 以实体登记表（人工登记层）为权威，
把 tagged 里管道后的规范名归一到登记表 canonical；归一后若显示串==规范名则摘管道。

换书标准工具（原 scripts/_oneshot/normalize_pipe_canonicals.py 正式化，docs/50 S12）。
只动管道元数据（| 之后），显示串与正文零改动 → 剥标逐字不变（脚本内断言）。
歧义 surface（同一 surface 对应多个 canonical，如"李公子"）不归一，留给语境界定。

登记表来源（--registry）：
  * 缺省 kb/<书>/实体登记表.json（旧人工登记层）；
  * 也可传统一登记表 registry/entities.json（兼容 entities 为 dict 或 list 两种形态）。

用法：
    python -X utf8 scripts/normalize_pipe_canonicals.py <书名>            # dry-run
    python -X utf8 scripts/normalize_pipe_canonicals.py <书名> --apply
产物：
    logs/qa/pipe_normalize_<书>.md（逐处变更清单与统计；--apply 前先备份到 logs/backup/）
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402
import symbols  # noqa: E402

TOKEN_RE = symbols.TOKEN_RE
PERSON_TYPES = {"@", "person", "人物"}          # 兼容旧登记表与统一 registry 的类型命名
ENTITY_KEYS = ("entities", "registry", "items")  # 兼容几种顶层容器命名


def load_surface_map(registry_path: Path):
    """surface → set(canonical)（取 @/person 实体；含 canonical 自身）。"""
    data = json.loads(io.open(registry_path, encoding="utf-8").read())
    raw = None
    for key in ENTITY_KEYS:
        if isinstance(data, dict) and key in data:
            raw = data[key]
            break
    if raw is None:
        raw = data
    items = raw.values() if isinstance(raw, dict) else raw
    surface = collections.defaultdict(set)
    for ent in items:
        if not isinstance(ent, dict):
            continue
        if ent.get("type") not in PERSON_TYPES:
            continue
        canon = (ent.get("canonical") or "").strip()
        if not canon:
            continue
        surface[canon].add(canon)
        for s in list(ent.get("surfaces") or {}) + list(ent.get("aliases") or {}):
            s = (s or "").strip()
            if s:
                surface[s].add(canon)
    return {s: next(iter(cs)) if len(cs) == 1 else None for s, cs in surface.items()}, len(surface)


def rewrite(text: str, surface_map: dict):
    """返回 (新文本, 变更清单[(old_token, new_token)])。"""
    changes = []

    def repl(m):
        if m.group("ent") is None or not m.group("ent").startswith("@"):
            return m.group(0)
        body = m.group("ent")[1:]
        if "|" not in body:
            return m.group(0)
        disp, canon = body.split("|", 1)
        target = surface_map.get(canon)
        if target is None:      # 歧义或登记表无此名：不动
            return m.group(0)
        if target == disp:
            new = "〖@" + disp + "〗"
            changes.append((m.group(0), new))
            return new
        if target == canon:
            return m.group(0)
        new = "〖@" + disp + "|" + target + "〗"
        changes.append((m.group(0), new))
        return new

    return TOKEN_RE.sub(repl, text), changes


def main() -> int:
    ap = argparse.ArgumentParser(description="@ 管道规范名回填（换书工具）")
    ap.add_argument("book", help="书名（tagged/<书> 同名）")
    ap.add_argument("--registry", default=None,
                    help="登记表路径（缺省 <仓库根>/kb/<书>/实体登记表.json；"
                         "也可传统一登记表 registry/entities.json）")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    book = args.book
    reg_path = Path(args.registry) if args.registry else \
        config.REPO_ROOT / "kb" / book / "实体登记表.json"
    if not reg_path.exists():
        raise SystemExit(f"登记表不存在：{reg_path}（可用 --registry 指定，"
                         f"如 registry/entities.json）")
    surface_map, n_surface = load_surface_map(reg_path)
    d = config.DIR_TAGGED / book
    files = sorted(d.glob("*.tagged.md"))
    if not files:
        raise SystemExit(f"无 tagged：{d}")
    all_changes = []
    total_tokens = 0
    backup_dir = config.DIR_LOGS / "backup" / f"pipe_normalize_{book}"
    for p in files:
        text = io.open(p, encoding="utf-8").read()
        total_tokens += len(re.findall(r"〖@[^〗]*〗", text))
        new, changes = rewrite(text, surface_map)
        if not changes:
            continue
        # 剥标断言：只允许管道元数据变化
        if symbols.strip_markup(new) != symbols.strip_markup(text):
            raise SystemExit(f"{p.name} 剥标不一致，中止")
        all_changes.append((p.name, changes))
        if args.apply:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, backup_dir / p.name)
            io.open(p, "w", encoding="utf-8", newline="\n").write(new)
    # 报告
    L = [f"# @ 管道规范名回填报告 ——《{book}》", "",
         f"- 登记表：`{reg_path}`；surface 数：{n_surface}；"
         f"扫描 tagged {len(files)} 回 / @ 令牌 {total_tokens}",
         f"- 归一规则：规范名 → 登记表 canonical（歧义 surface 不动）；显示串==规范名则摘管道",
         f"- 模式：{'APPLY' if args.apply else 'DRY-RUN'}；变更文件 {len(all_changes)} 回 / "
         f"变更令牌 {sum(len(c) for _, c in all_changes)} 处", ""]
    for name, changes in all_changes:
        L += [f"## {name}", ""]
        L += [f"- {old} → {new}" for old, new in changes]
        L.append("")
    out = config.DIR_LOGS / "qa" / f"pipe_normalize_{book}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print(f"[{'apply' if args.apply else 'dry-run'}] 登记表 {reg_path.name}（surface {n_surface}）；"
          f"回 {len(all_changes)} / 变更 {sum(len(c) for _, c in all_changes)} 处 → {out}")
    if not args.apply:
        for name, changes in all_changes[:5]:
            print(f"  {name}: " + "；".join(f"{a}→{b}" for a, b in changes[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
