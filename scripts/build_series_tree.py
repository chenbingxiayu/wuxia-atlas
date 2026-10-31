# -*- coding: utf-8 -*-
"""P0 收尾：系列谱系考订表。

输入：kb/作品元数据表.json（年代/系列归属）＋ kb/互文引用表.json（边证据）。
考订内容（人工判定，脚本自动挂接证据定位符）：
  ① 六条线路的成员与故事内排序（置信分级 strong=接力边直证 / ok=回指+编年 / todo=待考）；
  ② 宇宙编年主线（故事时间轴跨线排布）；
  ③ 换乘站种子（跨书人物，互文片段实证）；
  ④ 考订问题清单。
输出：kb/系列谱系考订表.json / .md。

用法：python scripts/build_series_tree.py
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / 'kb'

# ---------------------------------------------------------------------------
# 考订判定。why=人工理由；pairs=[(来源书, 被指书)] 由脚本自动从互文表挂定位符。
# conf: strong=作者接力边直证 / ok=回指＋编年互证 / todo=待考
# ---------------------------------------------------------------------------
LINES = [
    dict(line='天山系列（清代主脉）', color='#c0392b', members=[
        dict(book='白发魔女传', order=1, conf='ok',
             why=['编年实证：001 回梃击案＝万历四十三年（1615），全书终于清朝定鼎'],
             pairs=[('塞外奇侠传', '白发魔女传'), ('七剑下天山', '白发魔女传')]),
        dict(book='塞外奇侠传', order=2, conf='strong',
             why=['回指塞外·027:5 参见《白发魔女传》⇒ 白发在前', '正文年代自述：顺治入关后第七年'],
             pairs=[('塞外奇侠传', '七剑下天山')]),
        dict(book='七剑下天山', order=3, conf='strong',
             why=['接力边直证：塞外·028:39 请续看《七剑下天山》'],
             pairs=[('七剑下天山', '塞外奇侠传'), ('江湖三女侠', '七剑下天山')]),
        dict(book='冰魄寒光剑', order=4, conf='todo',
             why=['接力边：冰魄·012:147 请续看《冰川天女传》⇒ 界于七剑与冰川之间无疑',
                  '与《江湖三女侠》先后待考（传主桂华生为桂仲明之子，见弹指惊雷·001 回指）'],
             pairs=[('冰魄寒光剑', '七剑下天山'), ('弹指惊雷', '冰魄寒光剑')]),
        dict(book='江湖三女侠', order=5, conf='ok',
             why=['回指：三女侠→七剑×8（康熙间事为史前）', '冰川·003:43 回指三女侠（雍正朝事为前史）'],
             pairs=[('江湖三女侠', '七剑下天山'), ('冰川天女传', '江湖三女侠')]),
        dict(book='冰川天女传', order=6, conf='ok',
             why=['接力边：冰魄→冰川；回指：冰川→三女侠×2 等', '云海·002 回指冰川（事见）'],
             pairs=[('冰川天女传', '江湖三女侠'), ('云海玉弓缘', '冰川天女传')]),
        dict(book='云海玉弓缘', order=7, conf='ok',
             why=['回指：云海→冰川×2', '冰河→云海×5（金世遗前史）'],
             pairs=[('云海玉弓缘', '冰川天女传'), ('冰河洗剑录', '云海玉弓缘')]),
        dict(book='冰河洗剑录', order=8, conf='ok',
             why=['回指：冰河→云海×5/冰川×4', '侠骨→冰河×4；风雷→冰河×2'],
             pairs=[('冰河洗剑录', '云海玉弓缘'), ('侠骨丹心', '冰河洗剑录'), ('风雷震九州', '冰河洗剑录')]),
        dict(book='风雷震九州', order=9, conf='ok',
             why=['回指：风雷→冰河×2/冰川×1（前史）', '侠骨→风雷×3（尉迟炯/林清事为前史）⇒ 夹在冰河与侠骨之间'],
             pairs=[('风雷震九州', '冰河洗剑录'), ('侠骨丹心', '风雷震九州')]),
        dict(book='侠骨丹心', order=10, conf='ok',
             why=['回指：侠骨→冰河×4/风雷×3/大唐×1', '游剑→侠骨×1；弹指→侠骨×1'],
             pairs=[('侠骨丹心', '冰河洗剑录'), ('游剑江湖', '侠骨丹心')]),
        dict(book='游剑江湖', order=11, conf='ok',
             why=['回指：游剑→侠骨×1', '牧野→游剑×1（云紫萝之死为前史）'],
             pairs=[('游剑江湖', '侠骨丹心'), ('牧野流星', '游剑江湖')]),
        dict(book='牧野流星', order=12, conf='ok',
             why=['接力边：牧野·064:487 请续看《弹指惊雷》', '弹指→牧野×1'],
             pairs=[('牧野流星', '弹指惊雷'), ('弹指惊雷', '牧野流星')]),
        dict(book='弹指惊雷', order=13, conf='strong',
             why=['接力边双证：牧野→弹指、弹指·020:1115 请续看《绝塞传烽录》'],
             pairs=[('弹指惊雷', '绝塞传烽录')]),
        dict(book='绝塞传烽录', order=14, conf='strong',
             why=['接力边：弹指→绝塞、绝塞·012:1121 请续看《剑网尘丝》'],
             pairs=[('绝塞传烽录', '剑网尘丝')]),
        dict(book='剑网尘丝', order=15, conf='strong',
             why=['接力边：绝塞→剑网（⇒ 剑网尘丝属天山系列尾部，非独立）'],
             pairs=[('剑网尘丝', '幻剑灵旗')]),
        dict(book='幻剑灵旗', order=16, conf='strong',
             why=['作者自述：剑网尘丝·018:1277 "《剑网尘丝》的姐妹作《幻剑灵旗》"'],
             pairs=[('幻剑灵旗', '剑网尘丝')]),
    ]),
    dict(line='明代系列', color='#2980b9', members=[
        dict(book='还剑奇情录', order=1, conf='ok',
             why=['编年：元末明初（武当开创期）；武当一剑·003 回指其牟独逸'],
             pairs=[('武当一剑', '还剑奇情录')]),
        dict(book='萍踪侠影录', order=2, conf='ok',
             why=['编年：土木堡之变前后', '散花→萍踪×9、广陵→萍踪×4（张丹枫为前史）'],
             pairs=[('散花女侠', '萍踪侠影录'), ('广陵剑', '萍踪侠影录')]),
        dict(book='散花女侠', order=3, conf='ok',
             why=['回指：散花→萍踪×9', '联剑→散花×1'],
             pairs=[('散花女侠', '萍踪侠影录'), ('联剑风云录', '散花女侠')]),
        dict(book='联剑风云录', order=4, conf='ok',
             why=['回指：联剑→散花×1（张丹枫晚年）', '广陵承其后（张丹枫已故）'],
             pairs=[('联剑风云录', '散花女侠')]),
        dict(book='广陵剑', order=5, conf='ok',
             why=['回指：广陵→萍踪×4', '编年：成化末（承联剑）'],
             pairs=[('广陵剑', '萍踪侠影录')]),
    ]),
    dict(line='大唐三部曲', color='#8e44ad', members=[
        dict(book='大唐游侠传', order=1, conf='ok',
             why=['编年：安史之乱', '接力边：大唐·040:291 请看续集《龙凤宝钗缘》'],
             pairs=[('大唐游侠传', '龙凤宝钗缘')]),
        dict(book='龙凤宝钗缘', order=2, conf='strong',
             why=['接力边直证：大唐结尾请看续集', '慧剑→龙凤×4'],
             pairs=[('慧剑心魔', '龙凤宝钗缘')]),
        dict(book='慧剑心魔', order=3, conf='ok',
             why=['回指：慧剑→龙凤×4/大唐×1', '编年：代宗—德宗间'],
             pairs=[('慧剑心魔', '龙凤宝钗缘'), ('慧剑心魔', '大唐游侠传')]),
    ]),
    dict(line='宋代系列', color='#27ae60', members=[
        dict(book='挑灯看剑录', order=0, conf='ok', missing=True,
             why=['缺佚；被鸣镝×13、风云雷电×7 回指为前作（檀羽冲/耿照）'],
             pairs=[('鸣镝风云录', '挑灯看剑录')]),
        dict(book='飞凤潜龙', order=1, conf='todo',
             why=['武林天骄·007:333 回指其为"穴道铜人来历"⇒ 疑为宋代线最早，待考'],
             pairs=[('武林天骄', '飞凤潜龙')]),
        dict(book='武林天骄', order=2, conf='todo',
             why=['传主檀羽冲（称号"武林天骄"来历在《挑灯看剑录》，见鸣镝·030:319）',
                  '与《狂侠天骄魔女》先后待考（檀羽冲同为狂侠三主角之一）'],
             pairs=[('武林天骄', '飞凤潜龙'), ('鸣镝风云录', '挑灯看剑录')]),
        dict(book='狂侠天骄魔女', order=3, conf='ok',
             why=['编年：孝宗—光宗间（辛弃疾时代）', '鸣镝/风云雷电承其后'],
             pairs=[]),
        dict(book='鸣镝风云录', order=4, conf='ok',
             why=['编年：开禧前后（韩侂胄北伐）', '鸣镝·114:169 "风天扬的故事，另见拙著《风云雷电》"⇒ 承前启后'],
             pairs=[('鸣镝风云录', '瀚海雄风'), ('鸣镝风云录', '风云雷电')]),
        dict(book='瀚海雄风', order=5, conf='todo',
             why=['编年：嘉定（成吉思汗崛起）与鸣镝（开禧）交叠；鸣镝→瀚海×1 回指 ⇒ 并行或稍后，待考',
                  '被鸣镝/风云雷电回指（李思南为前史）'],
             pairs=[('鸣镝风云录', '瀚海雄风'), ('风云雷电', '瀚海雄风')]),
        dict(book='风云雷电', order=6, conf='ok',
             why=['回指：风云雷电→挑灯×7/瀚海×7/鸣镝×1；鸣镝另见其风天扬故事 ⇒ 宋代线末'],
             pairs=[('风云雷电', '鸣镝风云录')]),
    ]),
    dict(line='晚清民国线', color='#7f8c8d', members=[
        dict(book='龙虎斗京华', order=1, conf='ok',
             why=['编年：庚子事变（义和团）', '被草莽回指×10'],
             pairs=[('草莽龙蛇传', '龙虎斗京华')]),
        dict(book='草莽龙蛇传', order=2, conf='todo',
             why=['与龙虎的故事先后待考：草莽·010:223 "后来在《龙虎斗京华》一书中被打死"'
                  '之"后来"既可读作故事时间亦可读作出版次序'],
             pairs=[('草莽龙蛇传', '龙虎斗京华')]),
    ]),
    dict(line='独立作品', color='#f39c12', members=[
        dict(book='女帝奇英传', order=1, conf='ok',
             why=['唐·武周；与各线无互文（出/入边均为 0），独立成篇'],
             pairs=[]),
        dict(book='武当一剑', order=2, conf='ok',
             why=['明末（待考）；互文连《还剑奇情录》（武当开创·牟独逸）'],
             pairs=[('武当一剑', '还剑奇情录')]),
    ]),
]

# 换乘站种子（互文片段实证的跨书人物）
INTERCHANGE = [
    dict(name='晦明禅师（岳鸣珂）', books=['白发魔女传', '塞外奇侠传', '七剑下天山'], note='三部曲 KB 已归并（跨书统一规范名）'),
    dict(name='练霓裳（白发魔女）', books=['白发魔女传', '塞外奇侠传', '七剑下天山'], note='塞外·027:5 回指；七剑·021 回述'),
    dict(name='卓一航', books=['白发魔女传', '塞外奇侠传', '七剑下天山'], note='同上'),
    dict(name='辛龙子', books=['白发魔女传', '七剑下天山', '冰川天女传'], note='冰川·004:79 回指其复得达摩剑法（事在七剑）'),
    dict(name='桂仲明', books=['七剑下天山', '江湖三女侠', '冰川天女传'], note='三女侠·025 回指其怪病；冰川天女为其孙女'),
    dict(name='杨云骢', books=['塞外奇侠传', '七剑下天山'], note='七剑·016-023 多处回述'),
    dict(name='楚昭南', books=['塞外奇侠传', '七剑下天山'], note='跨书统一规范名（kb/README）'),
    dict(name='飞红巾（哈玛雅）', books=['塞外奇侠传', '七剑下天山', '江湖三女侠'], note='三女侠·009 回述'),
    dict(name='凌未风', books=['七剑下天山', '江湖三女侠'], note='三女侠·003/009 回述'),
    dict(name='桂华生', books=['冰魄寒光剑', '冰川天女传', '弹指惊雷'], note='弹指·001/002 回指'),
    dict(name='张丹枫', books=['萍踪侠影录', '散花女侠', '联剑风云录', '广陵剑'], note='明代线主脉人物（散花×9 回指）'),
    dict(name='金世遗', books=['云海玉弓缘', '冰河洗剑录', '侠骨丹心'], note='侠骨·002:9 回指其与文廷壁结怨（事在冰河）'),
    dict(name='江南', books=['冰川天女传', '冰河洗剑录'], note='风雷·001:31 "江海天之父江南"（第一个师父事在冰川）'),
    dict(name='江海天', books=['冰河洗剑录', '风雷震九州', '侠骨丹心'], note='风雷·001 回指'),
    dict(name='金逐流', books=['侠骨丹心', '游剑江湖', '弹指惊雷'], note='弹指·012:539 回指（天下第一剑客）'),
    dict(name='孟华', books=['牧野流星', '弹指惊雷'], note='牧野→弹指接力'),
    dict(name='杨炎', books=['弹指惊雷', '绝塞传烽录', '幻剑灵旗'], note='弹指→绝塞接力；幻剑·011 回指'),
    dict(name='檀羽冲', books=['挑灯看剑录', '武林天骄', '狂侠天骄魔女', '鸣镝风云录', '风云雷电'], note='"武林天骄"称号横贯宋代线（鸣镝·030/风云雷电·043）'),
    dict(name='耿照', books=['挑灯看剑录', '鸣镝风云录', '风云雷电'], note='风云雷电·008/023 回指'),
    dict(name='李思南', books=['瀚海雄风', '鸣镝风云录', '风云雷电'], note='风云雷电·048/052 回指'),
    dict(name='风天扬', books=['鸣镝风云录', '风云雷电'], note='鸣镝·114:169 "风天扬的故事，另见拙著《风云雷电》"'),
    dict(name='卫天元', books=['剑网尘丝', '幻剑灵旗'], note='姐妹作互指'),
]

OPEN_QUESTIONS = [
    '《武林天骄》与缺佚《挑灯看剑录》关系：同故事异版？檀羽冲前传？（人物重合实证，关系待考）',
    '《飞凤潜龙》在宋代线的位置：穴道铜人来历被《武林天骄》回指，疑最早，待考',
    '《冰魄寒光剑》与《江湖三女侠》的故事先后（均界于七剑与冰川之间）',
    '《草莽龙蛇传》与《龙虎斗京华》的故事先后（草莽·010"后来"线索两义）',
    '《鸣镝风云录》与《瀚海雄风》故事先后（编年开禧 vs 嘉定，而鸣镝回指瀚海）',
    '《武当一剑》精确背景年代（明末待考；与还剑奇情录牟家互文）',
    '宋代诸书精确背景年代（狂侠/鸣镝/瀚海/风云雷电 仅到朝代分段）',
]


def load_evidence() -> dict:
    """(source, target) -> [(loc, kind, snippet), ...]（authorial/quoted 优先）"""
    with open(KB / '互文引用表.json', encoding='utf-8') as f:
        edges = json.load(f)['edges']
    idx = defaultdict(list)
    for e in edges:
        if e['kind'] in ('authorial', 'quoted'):
            idx[(e['source'], e['target'])].append((e['loc'], e['kind'], e['snippet']))
    return idx


def main() -> None:
    with open(KB / '作品元数据表.json', encoding='utf-8') as f:
        wmeta = json.load(f)
    winfo = {w['book']: w for w in wmeta['works']}
    winfo.update({m['book']: dict(book=m['book'], missing=True) for m in wmeta['missing_works']})
    ev = load_evidence()

    lines_out = []
    for ln in LINES:
        members = []
        for m in ln['members']:
            w = winfo.get(m['book'], {})
            evs = []
            for src, tgt in m['pairs']:
                for loc, kind, snip in ev.get((src, tgt), [])[:2]:
                    evs.append({'edge': f'{src} → 《{tgt}》', 'loc': f'{src}·{loc}',
                                'kind': kind, 'snippet': snip[:46]})
            members.append({
                'book': m['book'], 'order': m['order'], 'conf': m['conf'],
                'missing': m.get('missing', False),
                'year': w.get('year'), 'era': w.get('era'), 'leads': w.get('leads'),
                'kb_status': w.get('kb_status', '缺佚' if m.get('missing') else '待建'),
                'why': m['why'], 'evidence': evs,
            })
        members.sort(key=lambda x: x['order'])
        lines_out.append({'line': ln['line'], 'color': ln['color'], 'members': members})

    spine = []
    for era, books in [
        ('唐·武周', ['女帝奇英传']),
        ('唐·天宝—大历', ['大唐游侠传', '龙凤宝钗缘', '慧剑心魔']),
        ('南宋', ['挑灯看剑录*', '飞凤潜龙*', '武林天骄*', '狂侠天骄魔女', '鸣镝风云录', '瀚海雄风', '风云雷电']),
        ('元末明初', ['还剑奇情录']),
        ('明·正统—景泰', ['萍踪侠影录']),
        ('明·景泰后—成化', ['散花女侠', '联剑风云录', '广陵剑']),
        ('明末·万历—崇祯', ['白发魔女传']),
        ('清·顺治', ['塞外奇侠传']),
        ('清·康熙', ['七剑下天山']),
        ('清·康熙—雍正', ['冰魄寒光剑*', '江湖三女侠']),
        ('清·乾隆', ['冰川天女传', '云海玉弓缘']),
        ('清·乾隆末—嘉庆', ['冰河洗剑录', '风雷震九州', '侠骨丹心', '游剑江湖', '牧野流星']),
        ('清·嘉庆—道光', ['弹指惊雷', '绝塞传烽录', '剑网尘丝', '幻剑灵旗']),
        ('清末·庚子前后', ['龙虎斗京华', '草莽龙蛇传']),
    ]:
        spine.append({'era': era, 'books': books, 'todo': '*' in era or any(b.endswith('*') for b in books)})

    payload = {
        'meta': {
            'generated': str(date.today()),
            'method': '人工考订（接力边＋回指＋编年三证），证据定位符由 build_series_tree.py 自动挂接自互文引用表',
            'conf_legend': 'strong=作者"请续看/续集/姐妹作"接力边直证；ok=回指＋编年互证；todo=待考',
            'sources': ['kb/作品元数据表.json', 'kb/互文引用表.json'],
        },
        'lines': lines_out,
        'chronology_spine': spine,
        'interchange_seeds': INTERCHANGE,
        'open_questions': OPEN_QUESTIONS,
    }
    with open(KB / '系列谱系考订表.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # ---------------- MD ----------------
    L = []
    L.append('# 系列谱系考订表（P0 收尾 · 地铁图/编年史数据源）\n')
    L.append(f'> 生成：`scripts/build_series_tree.py`（{payload["meta"]["generated"]}）。'
             '排序三证：接力边（作者亲证）＞互文回指＞编年；证据定位符自动挂接自互文引用表。\n')
    L.append('> 置信：**strong**＝接力边直证；**ok**＝回指＋编年互证；**todo**＝待考。'
             '带 \\* 书名为缺佚或年代待考。\n')

    L.append('## 一、线路总览\n')
    L.append('| 线路 | 成员 | 故事时间跨度 | strong/ok/todo |')
    L.append('|---|---|---|---|')
    for ln in lines_out:
        n = len(ln['members'])
        s = sum(1 for m in ln['members'] if m['conf'] == 'strong')
        o = sum(1 for m in ln['members'] if m['conf'] == 'ok')
        t = sum(1 for m in ln['members'] if m['conf'] == 'todo')
        span = f"{ln['members'][0]['era'] or ''} → {ln['members'][-1]['era'] or ''}"
        L.append(f"| {ln['line']} | {n} 部 | {span} | {s}/{o}/{t} |")
    L.append('')

    for ln in lines_out:
        L.append(f"## {ln['line']}\n")
        L.append('| 序 | 书名 | 初刊年 | 排序置信 | 排序依据（证据自动挂接） |')
        L.append('|---|---|---|---|---|')
        for m in ln['members']:
            year = (m['year'] or '—') if not m['missing'] else '缺佚'
            marks = '，'.join(m['why'])
            evs = '；'.join(f"{e['loc']}（{e['kind']}）" for e in m['evidence'][:3])
            conf = {'strong': '**strong**', 'ok': 'ok', 'todo': '**todo**'}[m['conf']]
            L.append(f"| {m['order']} | {m['book']}{'（缺佚）' if m['missing'] else ''} | {year} | {conf} | {marks}" +
                     (f"。证据：{evs}" if evs else '') + ' |')
        L.append('')

    L.append('## 宇宙编年主线（跨线故事时间轴）\n')
    L.append('| 故事年代 | 作品（\\*=待考/缺佚） |')
    L.append('|---|---|')
    for sp in spine:
        L.append(f"| {sp['era'].replace('*', '')} | {' → '.join(sp['books'])} |")
    L.append('')

    L.append(f'## 换乘站种子（{len(INTERCHANGE)} 人，互文实证）\n')
    L.append('| 人物 | 行经书目 | 依据 |')
    L.append('|---|---|---|')
    for ic in INTERCHANGE:
        L.append(f"| {ic['name']} | {'、'.join('《%s》' % b for b in ic['books'])} | {ic['note']} |")
    L.append('')

    L.append(f'## 考订问题清单（{len(OPEN_QUESTIONS)} 项）\n')
    for q in OPEN_QUESTIONS:
        L.append(f'- [ ] {q}')
    L.append('')

    with open(KB / '系列谱系考订表.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')

    n_books = sum(len(ln['members']) for ln in lines_out)
    print(f"lines={len(lines_out)} members={n_books} interchange={len(INTERCHANGE)} questions={len(OPEN_QUESTIONS)}")
    print(f"-> {KB / '系列谱系考订表.json'}")
    print(f"-> {KB / '系列谱系考订表.md'}")


if __name__ == '__main__':
    sys.exit(main())
