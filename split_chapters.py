# -*- coding: utf-8 -*-
"""
把《梁羽生武侠全集.txt》按"章回"拆分。

输出结构：
    章回版/<书名>/<序号3位>　<章回标题>.txt

- 文件名以 3 位序号开头（楔子=000，第一回=001 ……），保证资源管理器
  按名称排序即按章回顺序排列。
- 章回边界一律以"第X回"标题行为准（含"○"写法）。《绝塞传烽录》
  《幻剑灵旗》《弹指惊雷》《剑网尘丝》四部正文中另嵌有大量报纸连载
  的栏目小标题（常插在对话中间，如"冷若冰霜的少女"），并非章节边界，
  保留在所在回的正文里。
- 源文件有两处排版重复块（同一连载段被排了两遍），拆分时删除后一份：
    * 弹指惊雷：第 130207–130524 行（318 行，"小妖女拦途截劫"栏目块）
    * 鸣镝风云录：第 328485–328880 行（396 行，整个第四十九回）
"""

import os
import re
import shutil

SRC = "梁羽生武侠全集.txt"
OUT_DIR = "章回版"

# (书名, 起始行, 结束行)  1-based 闭区间，与按部拆分时核定的一致
NOVELS = [
    ("萍踪侠影录",   1,      4388),
    ("联剑风云录",   4389,   10602),
    ("龙虎斗京华",   10603,  13940),
    ("飞凤潜龙",     13941,  15578),
    ("散花女侠",     15579,  20650),
    ("还剑奇情录",   20651,  22732),
    ("冰魄寒光剑",   22733,  24286),
    ("草莽龙蛇传",   24287,  27722),
    ("塞外奇侠传",   27723,  29146),
    ("七剑下天山",   29147,  34126),
    ("白发魔女传",   34127,  38848),
    ("女帝奇英传",   38849,  44022),
    ("大唐游侠传",   44023,  53400),
    ("绝塞传烽录",   53401,  66596),
    ("幻剑灵旗",     66597,  80648),
    ("武林天骄",     80649,  92294),
    ("冰川天女传",   92295,  98106),
    ("云海玉弓缘",   98107,  107694),
    ("冰河洗剑录",   107695, 121596),
    ("弹指惊雷",     121597, 137682),
    ("广陵剑",       137683, 162352),
    ("剑网尘丝",     162353, 185116),
    ("侠骨丹心",     185117, 199446),
    ("风雷震九州",   199447, 214188),
    ("风云雷电",     214189, 238642),
    ("瀚海雄风",     238643, 257374),
    ("慧剑心魔",     257375, 271148),
    ("江湖三女侠",   271149, 278134),
    ("狂侠天骄魔女", 278135, 303798),
    ("龙凤宝钗缘",   303799, 313400),
    ("鸣镝风云录",   313401, 350332),
    ("牧野流星",     350333, 374554),
    ("武当一剑",     374555, 397054),
    ("游剑江湖",     397055, 422493),
]

# 源文件重复块（1-based 闭区间），删除后一份
DEDUP = [
    (130207, 130524),   # 弹指惊雷：连载栏目"小妖女拦途截劫"整段重排
    (328485, 328880),   # 鸣镝风云录：第四十九回整章重排
]

HUI_RE = re.compile(r"^第[一二三四五六七八九十百零○]+回")
CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
      "七": 7, "八": 8, "九": 9, "零": 0, "○": 0}


def cn2int(s: str) -> int:
    if "十" not in s and "百" not in s:
        v = 0
        for c in s:
            v = v * 10 + CN[c]
        return v
    m = re.match(r"^([一二三四五六七八九])?十([一二三四五六七八九])?$", s)
    if m:
        return (CN[m.group(1)] if m.group(1) else 1) * 10 + (CN[m.group(2)] if m.group(2) else 0)
    m = re.match(r"^([一二三四五六七八九])百(零([一二三四五六七八九])|([一二三四五六七八九])?十([一二三四五六七八九])?)?$", s)
    if m:
        h = CN[m.group(1)] * 100
        if m.group(3):
            return h + CN[m.group(3)]
        if m.group(4) or m.group(5):
            return h + (CN[m.group(4)] if m.group(4) else 1) * 10 + (CN[m.group(5)] if m.group(5) else 0)
        return h
    return -1


def sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "", name)
    return name.rstrip(" .")


def write_file(path: str, body, prefix=()):
    body = list(prefix) + list(body)
    while body and body[-1].strip() == "":
        body.pop()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(body) + "\n")


def main():
    with open(SRC, encoding="utf-8") as f:
        lines = f.read().split("\n")

    deleted = set()
    for a, b in DEDUP:
        deleted.update(range(a - 1, b))          # 0-based
    print(f"删除重复行 {len(deleted)} 行")

    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)

    report = []
    total_files = 0
    for title, s, e in NOVELS:
        idxs = [i for i in range(s - 1, e) if i not in deleted]
        seg = [lines[i] for i in idxs]
        # 回目行在 idxs 中的位置
        hui = [k for k, i in enumerate(idxs) if HUI_RE.match(seg[k].strip())]
        assert hui, f"{title}: 未找到回目行"

        # 每章行区间（idxs 下标）
        bounds = hui + [len(idxs)]
        chapters = []                            # (序号, 标题, 行下标区间, 前置行)
        pre = seg[: hui[0]]
        chapters = []
        if any(x.strip() for x in pre) and any(x.strip().startswith("楔子") for x in pre):
            # 楔子（可能连同书名行）单独成第 000 个文件
            heading = next(x.strip() for x in pre if x.strip().startswith("楔子"))
            chapters.append((0, heading, 0, hui[0], ()))
            prefix = ()
        else:
            # 无楔子：保留书名行并入第一章；其余非空行是堆叠目录残片，丢弃
            prefix = (title, "", "") if pre and pre[0].strip() == title else ()
        for j in range(len(hui)):
            pfx = prefix if j == 0 else ()
            chapters.append((j + 1, seg[hui[j]].strip(), hui[j], bounds[j + 1], pfx))

        ndir = os.path.join(OUT_DIR, title)
        os.makedirs(ndir, exist_ok=True)
        for seq, heading, a, b, pfx in chapters:
            body = [lines[i] for i in idxs[a:b]]
            fname = f"{seq:03d}　{sanitize(heading)}.txt"
            write_file(os.path.join(ndir, fname), body, pfx)
        total_files += len(chapters)

        # 回号连续性校验
        nums = [cn2int(HUI_RE.match(h).group(0)[1:-1]) for _, h, *_ in chapters if HUI_RE.match(h)]
        missing = [i for i in range(1, max(nums) + 1) if i not in set(nums)] if nums else []
        status = "OK" if not missing and len(nums) == len(set(nums)) else f"异常 缺{missing}"
        report.append((title, len(chapters), max(nums) if nums else 0, status))
        print(f"{title}: {len(chapters)}个文件（回目{len(nums)}，至第{max(nums)}回） {status}")

    print(f"\n共 {len(NOVELS)} 部小说，{total_files} 个章回文件")

    rows = "\n".join(f"| {t} | {n} | {mx} | {st} |" for t, n, mx, st in report)
    md = f"""# 章回版说明

每部小说一个文件夹，每个章回一个文本文件。文件名以 3 位序号开头
（楔子=000、第一回=001……），按名称排序即为阅读顺序。

- 章回边界以"第X回"标题行为准；《绝塞传烽录》《幻剑灵旗》《弹指惊雷》
  《剑网尘丝》正文中嵌有报纸连载的栏目小标题，非章节边界，未作拆分。
- 已剔除源文件两处排版重复块：弹指惊雷"小妖女拦途截劫"段（318 行）、
  鸣镝风云录第四十九回整章（396 行）。
- 全部文件为 UTF-8 编码。

| 书名 | 章回文件数 | 回目至 | 校验 |
|------|-----------|--------|------|
{rows}
"""
    with open(os.path.join(OUT_DIR, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(md)


if __name__ == "__main__":
    main()
