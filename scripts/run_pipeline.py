# -*- coding: utf-8 -*-
"""run_pipeline.py —— 站点数据管线一键编排（天山演示版总体方案 §5.5 管线唯一顺序，W2-C1）。

根因背景（§3.1 P0-2）：EX-5 v1 产物（matches-v1/glicko2）在部署序列中后跑，覆盖了工具 E
产物（clean_matches → matches-v2 / ratings_whr → whr）——页面宣称 WHR、数据却是 glicko2，
method 页"133 场"与 live 对局数两张皮。本脚本把 §5.5 唯一顺序固化为有序命令列表：

  export_site_all → manuals_elixirs（D11 EX-6b）→ clean_matches → ratings_whr → audit_r1
    → 切片（plots/relations/annals/wordcloud/qa_index/games_data/stories）
    → build 提示（不代跑 astro）

选型说明（W2-C1 报告）：新增独立 scripts/run_pipeline.py 而非扩展 export_site_all.py 加
--with-tools —— export_site_all 只负责 wuxia-kb EX 导出层（自有契约复核/hard_gap 退出码
语义），而管线顺序横跨 wuxia-kb/scripts 与父仓 scripts 两层脚本，编排器应位于两者之上，
保持 export_site_all 单一职责。

--apply 真跑前自动备份本管线覆盖写的 site/data 四文件（matches.json / ratings.json /
ratings-cleanlog.json / audit-r1.json）到 site/data/backup/c1_<时间戳>/；中途任一步
exit≠0 即中止（后续步骤不执行）。

用法：
  python -X utf8 scripts/run_pipeline.py                          # dry-run：打印命令列表
  python -X utf8 scripts/run_pipeline.py --scope tianshan-demo    # 打印 scope 口径命令
  python -X utf8 scripts/run_pipeline.py --scope tianshan-demo --apply   # 真跑（先备份）
"""
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WXKB_SCRIPTS = ROOT / "wuxia-kb" / "scripts"
SITE_DATA = ROOT / "site" / "data"
# 本管线直接覆盖写的 site/data 文件（--apply 前备份清单）
# D11：manuals/elixirs 为 EX-6b 新增产物（存在才备份，缺失跳过）。
BACKUP_FILES = ["matches.json", "ratings.json", "ratings-cleanlog.json", "audit-r1.json",
                "manuals.json", "elixirs.json"]

if str(WXKB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WXKB_SCRIPTS))
import export_site_common as esc  # noqa: E402

# (label, 脚本相对 ROOT 路径, note)；script=None = build 提示（不代跑 astro）
STEPS = [
    ("export_site_all", "wuxia-kb/scripts/export_site_all.py",
     "EX 导出层 8 导出器（EX-5 matches-v1/glicko2 产物为 legacy 中间层，随后被工具 E 覆盖）"),
    ("manuals_elixirs", "wuxia-kb/scripts/export_site_manuals_elixirs.py",
     "EX-6b 秘籍谱/丹药谱导出器（D11：底表×concordance×KB 标注层扫描 → manuals/elixirs.json，"
     "名物页重构设计 §七；需在 export_site_all 之后跑——related_arts 校验读其 arts.json）"),
    ("clean_matches", "scripts/clean_matches.py",
     "工具 E·E1 对局清洗（读 kb 事件层）→ matches-v2 + ratings-cleanlog"),
    ("ratings_whr", "scripts/ratings_whr.py",
     "工具 E·E2 WHR 评分（读 clean_matches 产物）→ ratings.json engine=whr"),
    ("ratings_calibration", "scripts/ratings_calibration.py",
     "工具 E·E3 校准回填（W2-D4-B）：抽检表 × matches outcome 一致率 → meta.calibration"
     "（E2 重跑会以骨架覆盖 calibration，故必须紧跟其后；分歧清单 → kb/校订/武评抽检-分歧.tsv）"),
    ("audit_r1", "scripts/audit_r1.py",
     "死亡一致性宽松核验（读 kb 事件层）→ audit-r1.json（games killer 上游）"),
    ("plots", "scripts/build_plots.py", "剧情锚点切片 char_plots.json"),
    ("relations", "scripts/build_relations.py", "人物关系切片 char_relations.json"),
    ("annals", "scripts/build_annals.py", "编年切片 annals.json + annals-daily.json"),
    ("wordcloud", "scripts/build_wordcloud.py", "人物词云切片 char_wordcloud.json"),
    ("qa_index", "scripts/build_qa_index.py", "QA 索引 qa-index.json + qa-events/"),
    ("games_data", "scripts/build_games_data.py", "游戏题库 games/twenty.json + daily.json"),
    ("stories", "scripts/build_stories.py", "专栏切片 stories/*.json"),
    ("build（不代跑）", None,
     "cd site && npm run build:preview（或 build:gh）→ build_search_index → pagefind → copyright_gate"
     "（astro 构建与搜索索引不代跑，按 site/README.md 部署节执行）"),
]

_BUILD_HINT = STEPS[-1][0]


def pipeline_commands(scope=None, apply=False):
    """§5.5 有序命令列表（纯函数；天山演示版总体方案 §4.3 C1 测试即规范）。

    scope：profile 名（None=全量口径；"all" 等价 None，同 --scope all 语义）。
    返回 [{"label", "argv", "note"}]：argv=None 表示提示步骤（不代跑）；argv=[python, 脚本, …]。
    scope 口径向每条命令透传 --scope <profile>；全量口径不透传（方案 R6）。
    apply=True 仅给 export_site_all 附加 --apply——工具 E/切片脚本恒直写 site/data，无 dry-run。
    """
    if scope == "all":
        scope = None
    cmds = []
    for label, script, note in STEPS:
        if script is None:
            cmds.append({"label": label, "argv": None, "note": note})
            continue
        argv = [sys.executable, str(ROOT / script)]
        if apply and label in ("export_site_all", "manuals_elixirs"):
            argv.append("--apply")
        if scope is not None:
            argv += ["--scope", scope]
        cmds.append({"label": label, "argv": argv, "note": note})
    return cmds


def backup_site_data_files(tag_prefix="c1"):
    """--apply 前备份覆盖写目标 → site/data/backup/<tag>_<时间戳>/；返回 (目录, 已备份文件名)。

    缺失的文件跳过（不报错）；目录与清单随实际备份文件动态创建。
    """
    dest = SITE_DATA / "backup" / f"{tag_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    copied = []
    for name in BACKUP_FILES:
        p = SITE_DATA / name
        if p.exists():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest / name)
            copied.append(name)
    return dest, copied


def main() -> int:
    apply = "--apply" in sys.argv
    # --scope all / 不传 = 全量口径（None）；提前校验 profile 存在（报错即停，不跑一半）
    profile = esc.scope_from_args()
    if profile is not None:
        esc.load_scope(profile)
    cmds = pipeline_commands(scope=profile, apply=apply)
    caliber = "全量口径" if profile is None else f"scope={profile}"
    print(f"[pipeline] {'APPLY（真跑，先备份）' if apply else 'dry-run（只打印命令列表）'} · "
          f"{caliber} · 共 {len(cmds)} 步（§5.5 唯一顺序）")
    for i, c in enumerate(cmds, 1):
        if c["argv"] is None:
            print(f"[pipeline] [{i}/{len(cmds)}] {c['label']} → {c['note']}")
        else:
            print(f"[pipeline] [{i}/{len(cmds)}] {c['label']}: {' '.join(c['argv'])}")
    if not apply:
        print("[pipeline] dry-run 结束（--apply 真跑；真跑前自动备份 " + "、".join(BACKUP_FILES) + "）")
        return 0

    dest, copied = backup_site_data_files()
    print(f"[pipeline] 备份 {copied or '（无既有文件）'} → {dest}")

    # 子进程统一 UTF-8（仓库惯例 python -X utf8；子进程经环境变量继承）
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    for i, c in enumerate(cmds, 1):
        if c["argv"] is None:
            print(f"[pipeline] ➜ 构建提示：{c['note']}")
            continue
        print(f"[pipeline] ▶ [{i}/{len(cmds)}] {c['label']}")
        t0 = time.perf_counter()
        proc = subprocess.run(c["argv"], cwd=str(ROOT), env=env)
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            print(f"[pipeline] ✗ {c['label']} exit={proc.returncode}"
                  f"（{elapsed:.1f}s）——管线中止，后续步骤未执行")
            return proc.returncode
        print(f"[pipeline] ✓ {c['label']}（{elapsed:.1f}s）")
    print(f"[pipeline] 全部 {len(cmds) - 1} 个数据步完成 → 执行「{_BUILD_HINT}」收尾。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
