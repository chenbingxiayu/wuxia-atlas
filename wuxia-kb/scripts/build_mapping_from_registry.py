# -*- coding: utf-8 -*-
"""registry + 已过审 gold 管道 → 每回《已核准映射表》快照（换书工具 · 扩书前置）

背景（docs/71 §七.1）：
    换新书时，旧标注映射只有 4 部书有（kb/tagged/<书>），其余书 build_legacy_mapping
    无输入 → mapping 只能空表，@ 管道率会掉到 2-4%。本工具改用两路来源，为新书生成
    逐回累积快照：

      来源 A（主）：`registry/entities.json` 的 @ 人物
        A1 全局别名（aliases，字符串）
        A2 书级语境注记（contextual dict）：仅收 `book == 本书` 的条目；跨书注记不搬运
      来源 B（辅，`--gold-transfer`，默认开）：已过审 tagged 的 @ 管道
        只搬运"规范名已登记 且 该规范名在本书正文出现"的跨书别名，并过滤：
        · 出现 <2 次、含注记括号、长度 <2 的显示串不收；
        · 通用称谓/头衔（相公/皇子/前辈/大侠…）不收；
        · 显示串是其他实体 canonical 的不收（防同形冲突）；
        · 显示串是 canonical 的真子串且长度 <3 的不收（短称交给模型按最小完整单位判断）；
        · 同显示串多规范名 → 跳过（宁缺勿错）；人工复核记录见 review.tsv。

口径（与 build_legacy_mapping.py 对齐）：
    1. 只取 @ 类；显示串须在本书正文出现；单字显示串不收；
    2. 第 N 回快照 = 在 1..N-1 回正文中出现过的映射（模拟顺序标注，不引入未来知识）；
    3. 按 (-len(显示串), 显示串) 排序；
    4. 只读 registry/tagged/../章回版，不改任何既有产物。

产物：
    logs/mapping_<书>/ch_NNN.json     逐回累积快照 [[显示串, 规范名], ...]
    logs/mapping_<书>/mapping.json    合并映射（= 末回快照，供 --mapping-file 单文件）
    logs/mapping_<书>/review.tsv      来源 B 的逐条候选（显示串/规范名/来源/计数/首现回/上下文）
    logs/mapping_<书>/summary.md      统计与来源说明

用法：
    python -X utf8 scripts/build_mapping_from_registry.py <书名> [--dry-run] [--check]
    python -X utf8 scripts/build_mapping_from_registry.py <书名> --no-gold-transfer
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402

REGISTRY = config.DIR_REGISTRY / "entities.json"
BAD_ALIAS_RE = re.compile(r"[（(]")
# 通用称谓 / 头衔 / 时代名：不进入人物别名映射
GENERIC = {
    "相公", "皇子", "王子", "神医", "少主", "公子", "大人", "前辈", "大侠", "女侠", "夫人",
    "姑娘", "老师", "师父", "师兄", "师姐", "师弟", "师妹", "掌柜", "老汉", "老者", "婆婆",
    "大娘", "大嫂", "丫头", "贤弟", "仁兄", "老兄", "老弟", "世兄", "世侄", "小兄弟",
    "老前辈", "掌门", "帮主", "长老", "方丈", "道长", "真人", "居士", "皇上", "皇帝",
    "太后", "王爷", "贝勒", "将军", "元帅", "成化", "万历", "嘉靖", "康熙", "雍正", "乾隆",
    "嘉庆", "道光", "顺治", "崇祯", "太子", "天子", "活佛", "兄台", "老爷", "宗主", "国王",
    "公公", "人妖", "武家兄弟", "尼泊尔国王",
}
TITLE_RE = re.compile(
    r"(前辈|大侠|女侠|夫人|公子|少主|叔叔|哥哥|姐姐|师兄|师弟|师姐|师妹|师叔|师伯|师父|"
    r"姑姑|婶婶|兄|姐|哥|先生|姑娘|老汉|老者|老头|婆婆|大娘|大嫂|大婶|大人|阁下|丫头|"
    r"公公|国王|活佛|太子|天子|相公|老爷|宗主|某|们|儿|老|少)$")
# 器物/技艺名形（防止"游龙剑→楚昭南""金刚手（武功）→董岳"这类错误搬运）
OBJECT_RE = re.compile(r"(剑|刀|鞭|棍|拳|掌|手|神芒|剑法|刀法|掌法|神功|心法|秘籍|丹|丸|散|膏|药)$")
# 已知跨书管道噪声（人工复核排除：2026-11-06 云海/冰河 + 联剑/广陵 逐条上下文核验）
TRANSFER_DENY = {
    "天山神芒",   # 暗器名，被误记为凌未风别名
    "游龙剑",     # 兵器名（楚昭南佩剑）
    "自发魔女",   # "白发魔女"讹字形
    "华妹",       # 云海·之华妹妹 → 谷之华，非何绿华
    "霞妹",       # 冰河·霞妹 → 邹绛霞（江南之妻），非孟秋霞
    # P2（联剑/广陵，2026-11-06 上下文核验）
    "火神弹",     # 联剑·"火神弹朱大雄" → 朱大雄绰号，非郝宝椿
    "张兄弟",     # 联剑·毕擎天对不同张姓人物的当面称呼（张丹枫/张玉虎歧义）
    "曹太监",     # 联剑·于谦故事中的太监，考订未定（曹吉祥？）非曹安
    "王妃",       # 广陵·"做段剑平的王妃"为身份/职位，非纳兰明慧
    "八妹",       # 广陵·排行称呼（云瑚等），非吕四娘
    "周伯伯",     # 联剑/广陵·当面尊称，所指待考（周青/周山民歧义）
    "总舵主",     # 联剑·江湖职衔泛称，不作人物别名
    # P3（风雷/侠骨，2026-11-06 上下文核验）
    "三娘",       # 侠骨·实为"董十三娘"子串，非巫三娘子
    "叶朋友",     # 侠骨·对叶慕华的当面称呼，非叶冲霄
    "官伯伯",     # 侠骨·原文为"上官伯伯"子串，非官宗耀
}

# 每书 deny（P3 风雷/侠骨，2026-11-07 逐条上下文核验；证据见
# logs/qa/_expand_books/p3_corpus_struct_audit.md §B1）：
#   registry 全局别名 / 无 book 键 contextual / gold 跨书搬运三路都可能把
#   跨书同形、子串、词义误配带入本书，且已实锤写进已标章节的 @ 管道。
#   清洗后本书映射只保留正文中确有别名关系的条目，宁缺勿错。
BOOK_DENY = {
    "风雷震九州": {
        # 跨书同形 / 子串 / 词义误配（18 条）
        "叶兄弟", "叶英雄", "姓岳的", "冰川天女", "小石子", "少寨主", "张伯伯",
        "楚统领", "王伯伯", "程伯伯", "黑煞神", "杨老爷子", "太师", "广元",
        "玲珑", "英杰", "西门", "秀妹",
        # 冗余短别名 / 子串风险（S3）
        "仲和", "季和", "胜男", "伯和", "冲霄", "廷壁", "闯王",
        # gold 跨书搬运：本书无该 canonical（2026-11-07 二次核验）
        "张伯", "钟秀", "大力神", "玉罗刹",
    },
    "侠骨丹心": {
        "小石子", "小孟", "燕妹", "玲珑", "英杰", "黄叶",
        "仲和", "伯和", "胜男", "廷壁", "冲霄",
    },
    # P4（剑网尘丝/幻剑灵旗，2026-11-07 逐条上下文核验；证据见
    # logs/qa/_expand_books/p4_mapping_audit.md）：
    #   跨书同形（楚少爷→楚青云/王大叔→王老头）、子串（伯和⊂卫伯伯和/冲霄⊂黄鹄冲霄/
    #   虹妹⊂天虹妹子）、词义误配（玲珑=七窍玲珑/围棋残局、西门=城西门/西门霸）、
    #   泛称（世伯）、本书无该 canonical（昆仑剑客实为孟仲强/小石子=石子/韩寨主→韩霸待考）。
    "剑网尘丝": {
        "楚少爷", "王大叔", "伯和", "冲霄", "虹妹", "玲珑", "西门",
        "世伯", "昆仑剑客", "小石子", "韩寨主", "玉妹", "雪妹",
    },
    "幻剑灵旗": {
        "上官山主", "蒙面少女", "宫香主", "世伯", "西门", "玲珑", "玉妹", "雪妹",
    },
    # P5（龙凤宝钗缘/慧剑心魔，2026-11-07 逐条上下文核验）：两书为唐/安史系列（承大唐游侠传），
    # 旧探针映射全部来自其他朝代书的 gold 转运（陈石星/周志侠/年羹尧/铁珊瑚/吕四娘/西门牧野 等），
    # 本书无该 canonical → 一律 deny；换书映射只留人工核验正向表（本批暂空）。
    "龙凤宝钗缘": {
        "小石子", "少寨主", "年将军", "林兄弟", "石香主", "路兄弟", "铁寨主", "铁都尉",
        "黑煞神", "小王", "玲珑", "英杰", "莹妹", "西门",
        # 关系/称谓型 gold 噪声（2026-11-07 二次核验：跨书 gold 转运自 剑网/幻剑 tagged）
        "令叔", "令媛", "妹妹", "师侄", "爷爷", "英妹", "贤侄", "武林怪杰", "楚老弟",
    },
    "慧剑心魔": {
        "铁扇书生", "少寨主", "日月轮", "林兄弟", "沙帮主", "英妹子", "铁寨主", "世伯",
        "太师", "玲珑", "英杰", "莹妹", "虹妹", "西门", "陛下",
        "令叔", "令媛", "妹妹", "师侄", "爷爷", "英妹", "贤侄", "武林怪杰", "楚老弟",
    },
    # P6（飞凤潜龙/草莽龙蛇传/龙虎斗京华/绝塞传烽录，2026-11-09）：初建快照全部为跨书 gold
    # 噪声（郭子仪/穆娟娟/厉南星/杜百英/齐漱玉/宇文雷/江海天… 均非本作角色），一律 deny；
    # 本批无人工核验正向映射，@ 管道只凭回内证据。
    "飞凤潜龙": {"令公", "妹妹", "小王"},
    "草莽龙蛇传": {
        "姓姜的少年", "杜舵主", "林兄弟", "陈兄弟", "三弟", "孔明", "孙女", "小段",
        "师侄", "朝廷", "爷爷", "英杰", "贤侄", "青云",
    },
    "龙虎斗京华": {
        "六合枪", "叫化子", "三弟", "令叔", "伯和", "冲霄", "妹妹", "孙女", "师侄",
        "英杰", "贤侄", "闯王",
    },
    "绝塞传烽录": {
        "冰川天女", "宇文山主", "康熙皇帝", "江湖浪子", "韩总镖头", "叫化子", "小石子",
        "武将军", "韩大爷", "世伯", "令媛", "伯和", "先师", "妖女", "妹妹", "姓展",
        "孙女", "小段", "小王", "师侄", "师嫂", "曼娜", "朝廷", "江家", "爷爷",
        "玲珑", "舍弟", "英扬", "西门", "贤侄",
    },
}

# 每书追加正向映射（人工核验过的本书文内证据；2026-11-07 剑网/幻剑）：
#   楚少爷=扬州楚劲松之子楚天舒（剑网[001] 姜雪君问"扬州楚劲松…是你何人"/"正是家父"）；
#   天虹妹子=楚天虹（"楚天虹七窍玲珑"）；玉妹=齐漱玉（卫天元呼"玉妹"，楚天舒点明所指）；
#   雪妹=姜雪君（卫天元呼"雪妹"，姜雪君应声）。
BOOK_EXTRA = {
    # 注：楚少爷 在剑网同时指 楚天舒（常规）与 楚劲松（追述语境），全局映射会引起
    # 管道冲突 → 不入 BOOK_EXTRA，由回内共现证据判定（2026-11-07 P4 复核决定）。
    "剑网尘丝": [["天虹妹子", "楚天虹"],
                 ["玉妹", "齐漱玉"], ["雪妹", "姜雪君"]],
    "幻剑灵旗": [["玉妹", "齐漱玉"], ["雪妹", "姜雪君"]],
}


def cjk_len(s: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def bad_display(disp: str, canon: str, canon_set: set, book: str | None = None) -> bool:
    """映射显示串通用噪声过滤（registry/gold 两路共用；book 非空时叠加 per-book deny）。"""
    if not disp or cjk_len(disp) < 2 or disp == canon:
        return True
    if book and disp in BOOK_DENY.get(book, ()):
        return True
    if BAD_ALIAS_RE.search(disp) or disp in GENERIC or disp in TRANSFER_DENY:
        return True
    if TITLE_RE.search(disp) or OBJECT_RE.search(disp):
        return True
    if disp in canon_set:              # 是别的实体 canonical → 同形冲突
        return True
    return False


def read_text(path: Path) -> str:
    try:
        return io.open(path, encoding="utf-8").read()
    except UnicodeDecodeError:
        return io.open(path, encoding="gb18030").read()


def load_registry(book: str):
    """registry → ({display: canonical}, 统计, 冲突, 全部 @ canonical 集合)。"""
    data = json.loads(io.open(REGISTRY, encoding="utf-8").read())
    entities = data.get("entities", []) if isinstance(data, dict) else []
    canon_set = {
        (e.get("canonical") or "").strip()
        for e in entities
        if e.get("type") == "@" and e.get("canonical") and e.get("status") != "pending"
    }
    canon_set.discard("")
    disp2canon: dict[str, Counter] = defaultdict(Counter)
    stat = Counter()
    for e in entities:
        if e.get("type") != "@":
            continue
        canon = (e.get("canonical") or "").strip()
        if not canon or e.get("status") == "pending":
            continue
        stat["entities"] += 1
        # A1 全局别名（过滤上下文标题/器物形；叠加本书 deny）
        for a in e.get("aliases") or []:
            if isinstance(a, dict):
                continue
            a = (a or "").strip()
            if bad_display(a, canon, canon_set, book=book):
                continue
            disp2canon[a][canon] += 1
            stat["alias_pairs"] += 1
        # A2 书级语境注记：只收本书
        for a in e.get("contextual") or []:
            if not isinstance(a, dict):
                a = {"display": a}
            disp = (a.get("display") or "").strip()
            bk = a.get("book")
            if not disp:
                continue
            if not bk:
                # 无 book 键的旧式注记不参与任何书（2026-11-07 P3 修复：
                # 岳鸣珂"姓岳的"等从旧书无键注记泄漏进风雷，造成错误 @ 管道）
                stat["ctx_skipped_no_book"] += 1
                continue
            if bk != book:
                stat["ctx_skipped_other_book"] += 1
                continue
            if bad_display(disp, canon, canon_set, book=book):
                continue
            disp2canon[disp][canon] += 1
            stat["ctx_pairs"] += 1
    pairs, conflicts = {}, {}
    for disp, cnt in disp2canon.items():
        if len(cnt) > 1:
            conflicts[disp] = dict(cnt)
            stat["conflicts"] += 1
            continue
        pairs[disp] = next(iter(cnt))
    return pairs, dict(stat), conflicts, canon_set


def load_gold_transfer(book: str, canon_set: set):
    """已过审 tagged 的 @ 管道 → 可搬运到本书的（显示串→规范名）与复核记录。"""
    tagged_root = config.DIR_TAGGED
    cnt: Counter = Counter()
    first_book = {}
    for d in sorted(tagged_root.iterdir() if tagged_root.is_dir() else []):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        for f in sorted(d.glob("*.tagged.md")):
            t = read_text(f)
            for m in re.finditer(r"〖@([^|〗]+)\|([^〗]+)〗", t):
                disp, canon = m.group(1).strip(), m.group(2).strip()
                if cjk_len(disp) >= 2 and disp != canon and not BAD_ALIAS_RE.search(disp):
                    cnt[(disp, canon)] += 1
                    first_book.setdefault((disp, canon), d.name)
    cand = {}
    for (disp, canon), n in cnt.items():
        if n < 2 or canon not in canon_set:
            continue
        if bad_display(disp, canon, canon_set, book=book):
            continue
        if disp in canon and cjk_len(disp) < 3:   # 短称（四娘/凤池）交给模型按最小完整单位判断
            continue
        cand.setdefault(disp, Counter())[canon] += n
    out, review = {}, []
    for disp, c in cand.items():
        if len(c) > 1:
            review.append({"display": disp, "canonical": ",".join(c), "source": "gold",
                           "count": sum(c.values()), "status": "conflict_skip"})
            continue
        canon = next(iter(c))
        out[disp] = (canon, sum(c.values()), first_book.get((disp, canon), ""))
        review.append({"display": disp, "canonical": canon, "source": "gold",
                       "count": sum(c.values()), "status": "candidate"})
    return out, review


def main() -> int:
    ap = argparse.ArgumentParser(description="registry+gold → 逐回《已核准映射表》快照（换书工具）")
    ap.add_argument("book", help="书名（../章回版/<书>、logs/mapping_<书> 同名）")
    ap.add_argument("--out-dir", default=None, help="输出目录（缺省 logs/mapping_<书>）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    ap.add_argument("--check", action="store_true",
                    help="与既有 logs/mapping_<书>/ch_NNN.json 对账后退出")
    ap.add_argument("--no-gold-transfer", action="store_true", help="不搬运 gold 管道别名")
    args = ap.parse_args()
    book = args.book

    reg_pairs, reg_stat, conflicts, canon_set = load_registry(book)
    gold_pairs, review = ({}, []) if args.no_gold_transfer else load_gold_transfer(book, canon_set)

    cdir = config.corpus_dir(book)
    if not cdir.is_dir():
        raise SystemExit(f"[ERROR] 底本目录不存在：{cdir}")
    chapter_files = {}
    for p in sorted(cdir.glob("*.txt")):
        m = re.match(r"^(\d{1,3})", p.name)
        if m:
            chapter_files[int(m.group(1))] = p
    if not chapter_files:
        raise SystemExit(f"[ERROR] 底本文件名无回号前缀：{cdir}")
    total = max(chapter_files)
    texts = {ch: read_text(p) for ch, p in chapter_files.items()}

    # 合并两路来源：gold 只补 registry 没有的显示串；registry 优先
    merged = {}
    for disp, canon in reg_pairs.items():
        merged[disp] = ("registry", canon, 0)
    for disp, (canon, n, first) in gold_pairs.items():
        if disp in merged and merged[disp][1] != canon:
            review.append({"display": disp, "canonical": canon, "source": "gold",
                           "count": n, "status": "registry_conflict_skip"})
            continue
        if disp not in merged:
            merged[disp] = ("gold", canon, n)
    used = {d: v for d, v in merged.items() if any(d in texts.get(ch, "") for ch in texts)}
    # 人工核验的正向映射（BOOK_EXTRA）：只补显示串在本书正文确有出现、且不覆盖已有条目的项
    n_curated = 0
    for disp, canon in BOOK_EXTRA.get(book, []):
        if disp in used:
            continue
        if not any(disp in texts.get(ch, "") for ch in texts):
            continue
        used[disp] = ("curated", canon, 0)
        n_curated += 1
    for r in review:
        r["appears"] = bool(any(r["display"] in texts.get(ch, "") for ch in texts))
    print(f"[registry] @实体 {reg_stat.get('entities', 0)}；候选 {len(reg_pairs)} 条；"
          f"冲突跳过 {len(conflicts)}；跨书注记跳过 {reg_stat.get('ctx_skipped_other_book', 0)}；"
          f"无 book 注记跳过 {reg_stat.get('ctx_skipped_no_book', 0)}；本书 deny {len(BOOK_DENY.get(book, ()))} 条")
    print(f"[gold] 可搬运候选 {len(gold_pairs)} 条（复核表 review.tsv，含冲突/未命中）")
    print(f"[merge] 合并候选 {len(merged)} 条；本书正文命中 {len(used)} 条")

    # 首次出现回
    first_seen = {}
    per_ch_new = {}
    for ch in range(1, total + 1):
        t = texts.get(ch, "")
        n_hit = 0
        for disp in used:
            if disp in first_seen:
                continue
            if disp in t:
                first_seen[disp] = ch
                n_hit += 1
        per_ch_new[ch] = n_hit

    snapshots, sizes, acc = {}, [], {}
    for ch in range(1, total + 1):
        snap = sorted(acc.items(), key=lambda kv: (-len(kv[0]), kv[0]))
        snapshots[ch] = [[d, c] for d, c in snap]
        sizes.append((ch, len(snap)))
        for disp in used:
            if first_seen.get(disp) == ch:
                acc[disp] = used[disp][1]
    final = sorted(acc.items(), key=lambda kv: (-len(kv[0]), kv[0]))

    if args.check:
        old_dir = config.DIR_LOGS / f"mapping_{book}"
        old_final = {}
        old_file = old_dir / f"ch_{total:03d}.json"
        if old_file.exists():
            try:
                old_final = {d: c for d, c in json.loads(io.open(old_file, encoding="utf-8").read())}
            except (ValueError, TypeError):
                old_final = {}
        covered = sum(1 for d in old_final if d in acc)
        print(f"[check] legacy 末回 {len(old_final)} 条；新工具 {len(final)} 条；"
              f"legacy 显示串被覆盖 {covered}/{len(old_final)}")
        return 0

    if args.dry_run:
        print(f"[dry-run] 末回映射 {len(final)} 条（来源："
              f"registry {sum(1 for d, c in final if merged.get(d, ('',))[0] == 'registry')} / "
              f"gold {sum(1 for d, c in final if merged.get(d, ('',))[0] == 'gold')}）；不写文件")
        print("前 10 条：", final[:10])
        return 0

    out_dir = Path(args.out_dir) if args.out_dir else (config.DIR_LOGS / f"mapping_{book}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for ch in range(1, total + 1):
        io.open(out_dir / f"ch_{ch:03d}.json", "w", encoding="utf-8", newline="\n").write(
            json.dumps(snapshots[ch], ensure_ascii=False, indent=0))
    io.open(out_dir / "mapping.json", "w", encoding="utf-8", newline="\n").write(
        json.dumps(final, ensure_ascii=False, indent=0))
    # review.tsv：gold 逐条（含未采用原因）
    lines = ["display\tcanonical\tsource\tcount\tfirst_seen_ch\tappears\tapplied"]
    for r in review:
        d = r["display"]
        applied = (d in acc) and merged.get(d, ("",))[0] == "gold"
        lines.append(f"{d}\t{r['canonical']}\t{r['source']}\t{r['count']}\t"
                     f"{first_seen.get(d, '')}\t{r['appears']}\t{applied}\t{r['status']}")
    io.open(out_dir / "review.tsv", "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    n_reg = sum(1 for d in acc if merged.get(d, ("",))[0] == "registry")
    n_gold = sum(1 for d in acc if merged.get(d, ("",))[0] == "gold")
    n_cur = len(acc) - n_reg - n_gold
    summary = [
        f"# 映射快照（{book}）", "",
        f"- 来源：`registry/entities.json`（A：@实体别名/本书语境注记）"
        f" + 已过审 `tagged/` 的 @管道（B：仅跨书共享规范名，严格过滤）"
        f" + 人工核验正向映射（C：BOOK_EXTRA，本书文内证据）",
        f"- 回数：{total}；`ch_NNN.json` = 第 N 回快照（仅含首次出现在 <N 回的映射）；"
        f"`mapping.json` = 末回合并映射",
        f"- 末回映射 **{len(final)}** 条（A registry {n_reg} / B gold {n_gold} / C curated {n_cur}）；"
        f"本书正文命中 {len(used)} / 合并候选 {len(merged)}",
        f"- registry：@实体 {reg_stat.get('entities', 0)}；候选 {len(reg_pairs)}；"
        f"同显示串冲突跳过 {len(conflicts)}；跨书语境注记跳过 {reg_stat.get('ctx_skipped_other_book', 0)}；"
        f"无 book 注记跳过 {reg_stat.get('ctx_skipped_no_book', 0)}；本书 deny {len(BOOK_DENY.get(book, ()))}",
        f"- gold 搬运：候选 {len(gold_pairs)}；复核明细 `review.tsv`（含冲突跳过/未命中）",
        "", "| 回 | 快照条数 | 本回首次出现 |", "|---|---:|---:|",
    ]
    summary += [f"| {ch:03d} | {n} | {per_ch_new.get(ch, 0)} |" for ch, n in sizes]
    io.open(out_dir / "summary.md", "w", encoding="utf-8", newline="\n").write(
        "\n".join(summary) + "\n")
    print(f"[ok] {book}: {total} 回快照 + mapping.json（{len(final)} 条：registry {n_reg} / gold {n_gold} / curated {n_cur}）→ {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
