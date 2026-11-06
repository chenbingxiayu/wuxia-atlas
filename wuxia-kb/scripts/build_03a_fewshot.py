# -*- coding: utf-8 -*-
"""SKILL_03a few-shot 构建器 v3（G1 收口件；2026-11-03 外部 Review 回应后升级，
2026-11-04 审计修复：prompt_version 回填 + 修辞层剥离 + --check 干跑）。
注入 + 全部断言 + 版本锁定回填。任一断言失败不落盘。
位置：scripts/（P5 修复 2026-11-03，原 tagged/_xval/_build_03a_fewshot.py——脚本归
scripts/、语料归 tagged/ 的目录约定）；路径接 config，任意 cwd 可跑。
再生成纪律（SKILL_03a §5.3）：种子修订后必须重跑本脚本，规则改动不直接改提示词。
用法：python scripts/build_03a_fewshot.py [--check]   # --check 只断言不写盘
检查项（对应 SKILL_03a §5.2）：
  1 类型码=15 且与 symbols.ENTITIES 一致；2 FS 注入逐字+剥标一致；3 块长≤800；
  4 FS 语法解析（闭合/无嵌套）；5 §5.1 索引 claims↔块内容一致；6 覆盖报告；
  7 对照例引文存在性；8 反向断言（废止标记不得回流）；9 依赖哈希回填版本锁定节；
  10 版本一致性：frontmatter version = §二标题版本 = manifest prompt_version。
种子若含修辞层 〘※…〙（docs/37 之后 001-019 已补标），注入前剥离——03a 只教 E+V，
修辞层由 02j/annotate_rhetoric_llm 单独处理，避免 few-shot 诱导模型输出 ※。"""
import re, io, sys, hashlib, datetime, collections
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config   # noqa: E402
import symbols  # noqa: E402

SKILL = config.DIR_SKILLS / 'SKILL_03a_实体标注.md'
S001, B001 = config.DIR_TAGGED / '_xval/glm_001.EV.v2.md', config.DIR_TAGGED / '_xval/fragment_001_L2-12.txt'
S003, B003 = config.tagged_path('白发魔女传', 3), config.struct_path('白发魔女传', 3)
S015, B015 = config.tagged_path('白发魔女传', 15), config.struct_path('白发魔女传', 15)
S017, B017 = config.tagged_path('白发魔女传', 17), config.struct_path('白发魔女传', 17)
S018, B018 = config.tagged_path('白发魔女传', 18), config.struct_path('白发魔女传', 18)
S019, B019 = config.tagged_path('白发魔女传', 19), config.struct_path('白发魔女传', 19)

# D1/亲属 v1.8 不标形（docs/39 §1.2 D1；SKILL_03a DEF-04）：注入前剥标记、保留显示串。
# 先例=修辞层剥离（03a 只教 v1.8 口径的 E+V）；种子文件不动，剥离仅作用于 few-shot 注入本。
# 依据：金标准含 19.4% D1 旧口径 over-tag（docs/39 §1.2），示例必须教正确口径。
D1_UNTAG = {
    '人', '大家', '自己人', '俺', '小鬼', '小', '老头', '老者', '老妇人', '老儿',
    '少年', '少女', '汉子', '大汉', '人物', '人声', '姑姑', '前夫', '舅舅',
}

def sha12(p):
    return hashlib.sha256(io.open(p, 'rb').read()).hexdigest()[:12]

def parse_seed(path):
    out = {}
    for ln in io.open(path, encoding='utf-8').read().split('\n'):
        m = re.match(r'^\[(\d+)\] (.*)$', ln)
        if m:
            out[int(m.group(1))] = ln
    return out

def strip(s):
    s = re.sub(r'〖.([^|〗]*)(?:\|[^〗]*)?〗', r'\1', s)
    s = re.sub(r'⟦.([^|⟧]*)(?:\|[^⟧]*)?⟧', r'\1', s)
    # 修辞层只去标记、保留显示串（docs/37 后种子含 〘※显示串〙；03a 只教 E+V）
    return re.sub(r'〘.(.*?)〙', r'\1', s)

def parse_tags_ok(s):
    """FS 语法解析（单遍扫描）：闭合/无嵌套/类型码在白名单。"""
    stack = []
    for i, c in enumerate(s):
        if c in '〖⟦':
            stack.append((c, i))
        elif c in '〗⟧':
            if not stack:
                return f'多余闭括号 @{i}'
            op, _ = stack.pop()
            if (op == '〖') != (c == '〗'):
                return f'括号不匹配 @{i}'
    if stack:
        return f'未闭合 {len(stack)} 处'
    if re.search(r'〖[^〗]*〖', s) or re.search(r'⟦[^⟧]*⟦', s):
        return '嵌套'
    bad = [c for c in re.findall(r'[〖⟦](.)', s)
           if c not in symbols.ENTITIES and c not in symbols.VERBS]
    return f'非法类型码 {bad}' if bad else None

text = io.open(SKILL, encoding='utf-8').read()

# ---- 1 类型码数量与白名单 ----
seg = text.split('## 实体类型码', 1)[1].split('## 动词域码', 1)[0]
codes = re.findall(r'^([@◎=◆&~;#☆•+{^%$]) ', seg, re.M)
assert sorted(codes) == sorted(symbols.ENTITIES), f'码表与 symbols.ENTITIES 不一致: {codes}'
assert len(codes) == 15, f'类型码数量 {len(codes)} != 15'
vseg = text.split('## 动词域码', 1)[1].split('## 触发词边界', 1)[0]
vcodes = re.findall(r'^([⊞⊠⊡⊟▣■]) ', vseg, re.M)
assert sorted(vcodes) == sorted(symbols.VERBS), f'动词域码不一致: {vcodes}'
print(f'检查1 PASS: 实体码 {len(codes)}/15 与 symbols 一致；动词域 {len(vcodes)}/6')

# ---- 2/3 FS 注入（幂等：示例区块整体重建）----
seed001, base001 = parse_seed(S001), parse_seed(B001)
seed003, base003 = parse_seed(S003), parse_seed(B003)
seed015, base015 = parse_seed(S015), parse_seed(B015)
seed017, base017 = parse_seed(S017), parse_seed(B017)
seed018, base018 = parse_seed(S018), parse_seed(B018)
seed019, base019 = parse_seed(S019), parse_seed(B019)
LABELS = [
    (2, seed001, base001, '001 回 [2]｜开场叙事：时间/地点/职业身份/器物坐骑全量/行踪'),
    (7, seed001, base001, '001 回 [7]｜D2 集体名号+省称、组织+职衔+数量、技艺、器物'),
    (10, seed001, base001, '001 回 [10]｜战斗动词域、引号边界、绰号|本名管道、组织变体'),
    (1, seed003, base003, '003 回 [1]｜对白 D1 称谓管道、纯意图不标、绑架归 ■、建制职 ;'),
    (9, seed003, base003, '003 回 [9]｜物件变化动词族、&家族、#随从、治疗 ⊠'),
    (11, seed003, base003, '003 回 [11]｜%宽口径、⟦⊠遭横死⟧、{情报、⊡收买、方位地域、蓄意不标'),
    (24, seed003, base003, '003 回 [24]｜⊡政治司法动词族（含囚禁/问刑执行状态注记）、案件名不标'),
    (38, seed003, base003, '003 回 [38]｜命名揭名段、{文书、对白内本名照标、战斗语境闪避 ⊞'),
    (30, seed003, base003, '003 回 [30]｜▣ 传习调教、⊠致残割指、#门中辈分、%相对时点、法号称名管道'),
    (26, seed018, base018, '018 回 [26]｜= 场所指代密集（沈阳/辽阳/河东/堡寨链）、#金兵/大将、;辽东经略、◆政权链'),
    (47, seed017, base017, '017 回 [47]｜#身份通名群（强盗头子/悍盗/官军）、$数量×13、•器物×10、☆专名招式'),
    (41, seed017, base017, '017 回 [41]｜•器物×8（绿玉箫/腰间）、☆判官笔比喻、#狗强盗（骂称指具体）、$一份'),
    (14, seed019, base019, '019 回 [14]｜$信息承载计数（十二人/二十名/每人/一名）、#卫士/伤员、^穴道、•关节'),
    (41, seed018, base018, '018 回 [41]｜◆武当派+☆剑法+^上乘（总称/分项对照）、#大弟子/卫士、=观/观外'),
    (38, seed015, base015, '015 回 [38]｜D1 边界现场（卫士 标 vs 少女/大汉 不标）、■跳上、⊟缚、•岩石/马背'),
]
blocks, assembled = {}, []
d1_stripped = [0]
for i, (n, seed, base, label) in enumerate(LABELS, 1):
    line = seed[n]
    line = re.sub(r'〘.(.*?)〙', r'\1', line)  # 剥离修辞标记、保留显示串（03a 只教 E+V）
    # D1/亲属 v1.8 不标形剥标（保留显示串；docs/39 §1.2 + DEF-04；种子不动）
    def _d1(m):
        d1_stripped[0] += 1
        return m.group(1)
    line = re.sub(r'〖#(' + '|'.join(D1_UNTAG) + r')〗', _d1, line)
    assert strip(line) == strip(base[n]), f'FS{i} 段[{n}] 剥标与底本不一致'
    assert len(line) <= 800, f'FS{i} 段[{n}] 长 {len(line)} > 800'
    err = parse_tags_ok(line)
    assert not err, f'FS{i} 段[{n}] 语法: {err}'
    blocks[f'___FS{i}___'] = line
    assembled.append(f'【示例 {i} · {label}】\n{line}')
start = text.index('【示例 1 ·')
end = text.index('## 正反对照')
text = text[:start] + '\n\n'.join(assembled) + '\n\n' + text[end:]
print(f'检查2/3/4 PASS: {len(LABELS)} 块示例区块重建（逐字+剥标+≤800+语法解析）；'
      f'D1 剥离 {d1_stripped[0]} 处')

# ---- 5 §5.1 索引 claims ↔ 块内容 ----
CLAIMS = [
    ('___FS1___', ['〖%凉秋九月|时点〗', '⟦■西行⟧', '〖•骡车〗', '〖#武师〗', '〖$一辆〗']),
    ('___FS2___', ['〖◎西川双煞〗', '〖◎双煞〗', '〖◆龙门帮〗', '〖;舵主〗', '〖$三位〗', '〖☆铁沙掌〗']),
    ('___FS3___', ['⟦⊟着火⟧', '⟦⊠打中⟧', '〖@火灵猿|朱宝椿〗', '〖☆八方风雨〗', '〖$一堆〗']),
    ('___FS4___', ['〖@魏公公|魏忠贤〗', '⟦■绑架⟧', '〖;值殿武师〗', '〖@孟伯伯|孟灿〗']),
    ('___FS5___', ['⟦⊟揭⟧', '〖&孟家〗', '〖#随从〗', '⟦⊠敷⟧', '〖•封条〗']),
    ('___FS6___', ['⟦⊡收买⟧', '〖{情报〗', '〖%五年前|时点〗', '〖%连年来|时长〗', '〖%年前|时点〗', '〖=关外〗', '〖=大内〗']),
    ('___FS7___', ['⟦⊡囚禁|司法拘押⟧', '⟦⊡问|判处缳首之刑，执行状态未明⟧', '⟦⊡昭雪⟧', '〖;太子少保〗', '〖=冷宫〗']),
    ('___FS8___', ['〖@霓裳|练霓裳〗', '〖@练小姐|练霓裳〗', '〖{霓裳羽衣〗', '身形⟦⊞一闪⟧']),
    ('___FS9___', ['⟦▣调教⟧', '⟦⊠割⟧', '〖#第二代弟子〗', '〖$五个〗', '〖%一月之前|时点〗',
                   '〖@贞乾|贞乾道人〗', '〖@贞乾道人〗', '〖@红云道人〗', '〖@玉罗刹|练霓裳〗', '〖=华山〗']),
    ('___FS10___', ['〖;辽东经略〗', '〖#金兵〗', '〖#大将〗', '〖=沈阳〗', '〖=辽阳〗', '〖=辽河〗',
                    '〖$五十寨〗', '〖◆大清〗', '〖@努尔哈赤〗', '〖•大军〗']),
    ('___FS11___', ['〖=林中〗', '〖$两股〗', '〖#强盗头子〗', '〖#悍盗〗', '〖#官军〗', '〖•铁烟杆〗',
                    '〖•九节鞭〗', '〖☆云麾三舞〗', '〖$一根〗', '〖=陕北〗']),
    # 2026-11-06 C1 二阶段摘标同步：FS12 〖$一掌〗（事件量）、FS13 〖$每人〗（前置
    # deny）、FS14 〖$十二〗（裸数词）已按 docs/45/W4 口径从种子摘除，声明随之移除。
    ('___FS12___', ['〖•绿玉箫〗', '〖•腰间〗', '〖☆判官笔〗', '〖#狗强盗〗', '〖$一份〗']),
    ('___FS13___', ['〖$十二人〗', '〖$二十名〗', '〖$十五六人〗', '〖$一名〗', '〖#卫士〗',
                    '〖#伤员〗', '〖^穴道〗', '〖•关节〗', '〖•剑〗', '〖=清虚观〗', '〖◆东厂〗', '〖◆武当派〗']),
    ('___FS14___', ['〖◆武当派〗', '〖☆剑法〗', '〖^上乘〗', '〖#大弟子〗', '〖#卫士〗', '〖=观〗',
                    '〖=观外〗', '〖$一隅〗']),
    ('___FS15___', ['〖=秘魔崖〗', '〖◆东厂〗', '〖#卫士〗', '〖•岩石〗', '〖•马背〗', '〖$一名〗',
                    '〖$一条〗', '〖$一群〗', '⟦■跳上⟧', '⟦⊟缚|捆绑⟧']),
]
for ph, claims in CLAIMS:
    for c in claims:
        assert c in blocks[ph], f'{ph} 索引声明 {c} 不在块内'
NEG = [('___FS6___', '〖$一批〗'), ('___FS7___', '⟦⊞囚禁'), ('___FS1___', '⟦■纵马过来⟧'),
       ('___FS15___', '〖#少女〗'), ('___FS15___', '〖#大汉〗'), ('___FS11___', '〖#老头〗'),
       ('___FS14___', '〖#人物〗'), ('___FS13___', '〖#人〗')]
for ph, neg in NEG:
    assert neg not in blocks[ph], f'{ph} 出现废止标记 {neg}'
print(f"检查5 PASS: 索引声明 {sum(len(c) for _, c in CLAIMS)} 条全部命中；废止标记 {len(NEG)} 条未回流")

# ---- 6 覆盖报告 ----
allfs = '\n'.join(blocks.values())
ce = collections.Counter(re.findall(r'〖(.)', allfs))
cv = collections.Counter(re.findall(r'⟦(.)', allfs))
miss_e = [c for c in symbols.ENTITIES if c not in ce]
miss_v = [c for c in symbols.VERBS if c not in cv]
print(f'检查6 覆盖报告: 实体缺 {miss_e or "无"}（~族群=0 为已知零覆盖）；动词缺 {miss_v or "无"}')
print(f'   FS 实体分布 {dict(sorted(ce.items()))}')
print(f'   FS 动词分布 {dict(sorted(cv.items()))}')

# ---- 7 对照例引文存在性 ----
CONTRAST = [
    (S003, '蓄意内侵'), (S001, '时时⟦⊞内侵⟧'), (S001, '竟自允了'), (S001, '齐向〖@耿绍南〗下拜'),
    (S001, '⟦⊡请|雇请⟧'), (S001, '纵马⟦■过来⟧'), (S003, '迈步⟦■入内⟧'), (S001, '〖{信〗'),
    (S001, '⟦⊞抢上来|劫夺未遂⟧'), (S003, '身形⟦⊞一闪⟧'), (S003, '⟦⊡囚禁|司法拘押⟧'),
    (S003, '⟦⊡问|判处缳首之刑，执行状态未明⟧'), (S003, '⟦⊠死⟧在狱中'), (S003, '⟦■劫⟧'),
    (S003, '⟦■绑架⟧'),
    # D1 边界（docs/39 S2 对照组；卫士 标 vs 少女 裸文同段；剑/剑法 分项 vs 器物）
    (S015, '另有〖$一名〗少女已被⟦⊟缚|捆绑⟧在〖•马背〗'),
    (S015, '〖$一群〗〖◆东厂〗〖#卫士〗围着'),
    (S019, '用〖•剑〗刺伤〖•关节〗'),
    (S018, '〖☆剑法〗原是〖^上乘〗〖☆剑法〗'),
]
seed_txt = {S001: io.open(S001, encoding='utf-8').read(), S003: io.open(S003, encoding='utf-8').read(),
            S015: io.open(S015, encoding='utf-8').read(), S018: io.open(S018, encoding='utf-8').read(),
            S019: io.open(S019, encoding='utf-8').read()}
for path, frag in CONTRAST:
    assert frag in seed_txt[path], f'对照例引文不在种子中: {frag}'
print(f'检查7 PASS: 对照例引文 {len(CONTRAST)} 条全部存在于种子')
# 传闻对照行的引文（含 〧 误写检测——必须在提示词文本中核对）
q = '⟦⊠杀⟧了我们〖$三个〗〖◆锦衣卫〗'
assert q in seed_txt[S003], 'FS 传闻对照引文与种子不符'
assert q in text, '提示词内传闻对照引文缺失或含误写字符'
print('检查7b PASS: 传闻对照引文（⟦⊠杀⟧…）与种子逐字一致且已写入提示词')

# ---- 8 manifest ----
counts = {}
for name, path in [('s001', S001), ('s003', S003), ('s015', S015), ('s017', S017),
                   ('s018', S018), ('s019', S019)]:
    t = io.open(path, encoding='utf-8').read()
    counts[name] = (len(re.findall(r'〖', t)), len(re.findall(r'⟦', t)))

# 版本一致性（检查 10）：frontmatter version = §二标题版本 = manifest prompt_version
ver_m = re.search(r'^version:\s*(\S+)\s*$', text, re.M)
assert ver_m, 'frontmatter 缺 version 字段（§一 检查 10）'
prompt_version = ver_m.group(1)
sec2_m = re.search(r'^## 二、SYSTEM_PROMPT（([^，]+)，', text, re.M)
assert sec2_m, '未找到 §二 SYSTEM_PROMPT 标题'
assert sec2_m.group(1) == prompt_version, (
    f'§二标题版本 {sec2_m.group(1)} != frontmatter version {prompt_version}（检查 10）')

rows = [
    (r'(\| prompt_version \| )[^\n]*', prompt_version),
    (r'(\| ruleset: SKILL_01g \| )[^\n]*', sha12(config.DIR_SKILLS / 'SKILL_01g_标注符号集合原则.md')),
    (r'(\| ruleset: SKILL_04f \| )[^\n]*', sha12(config.DIR_SKILLS / 'SKILL_04f_动词标注.md')),
    (r'(\| ruling: docs/21 \| )[^\n]*', sha12(config.ROOT / 'docs' / '21-第一回标注修订说明.md')),
    (r'(\| symbols: scripts/symbols\.py \| )[^\n]*', sha12(config.DIR_SCRIPTS / 'symbols.py')),
    (r'(\| seed: 001 v2 \| )[^\n]*', sha12(S001) + f'（{counts["s001"][0]}E+{counts["s001"][1]}V）'),
    (r'(\| seed: 003 \| )[^\n]*', sha12(S003) + f'（{counts["s003"][0]}E+{counts["s003"][1]}V）'),
    (r'(\| seed: 015 \| )[^\n]*', sha12(S015) + f'（{counts["s015"][0]}E+{counts["s015"][1]}V）'),
    (r'(\| seed: 017 \| )[^\n]*', sha12(S017) + f'（{counts["s017"][0]}E+{counts["s017"][1]}V）'),
    (r'(\| seed: 018 \| )[^\n]*', sha12(S018) + f'（{counts["s018"][0]}E+{counts["s018"][1]}V）'),
    (r'(\| seed: 019 \| )[^\n]*', sha12(S019) + f'（{counts["s019"][0]}E+{counts["s019"][1]}V）'),
    (r'(\| generated_at \| )[^\n]*', datetime.date.today().isoformat()),
]
drift = []
for pat, v in rows:
    m = re.search(pat, text)
    assert m, f'版本锁定行未命中: {pat}'
    old = m.group(0)[len(m.group(1)):]
    if old != str(v):
        # 2026-11-05 修复"假绿"：原实现只回填不比对，依赖哈希失配（如种子修订后未重跑）
        # 在 --check 下永远发现不了。现逐行报告漂移，--check 时给出显式重跑指引。
        drift.append((old, str(v)))
    text, n = re.subn(pat, lambda mm: mm.group(1) + v, text, count=1)
    assert n == 1, f'版本锁定行未命中: {pat}'
if drift:
    print(f'检查8 DRIFT: 版本锁定 {len(drift)} 行失配（依赖在构建后被改过，锁表已回填新值）：')
    for old, new in drift:
        print(f'  {old[:40]}  →  {new[:40]}')
    if '--check' in sys.argv or '--dry-run' in sys.argv:
        print('  → 干跑模式未写盘；请重跑本脚本（不带 --check）回填锁表（SKILL_03a §5.3 再生成纪律）')
else:
    print('检查8 PASS: 版本锁定哈希全部一致（prompt_version/01g/04f/docs21/symbols/六种子）')

if '--check' in sys.argv or '--dry-run' in sys.argv:
    print('检查9 PASS: 版本一致性（frontmatter = §二标题 = manifest）；干跑模式未写盘')
    sys.exit(0)

io.open(SKILL, 'w', encoding='utf-8', newline='\n').write(text)
left = re.findall(r'___(?:FS\d|H_\w+|C_\w+|GEN_AT)___', text)
print('占位符残留:', len(left), '（应为 0）')
m = re.search(r'````text\n(.*?)\n````', text, re.S)
print(f'SYSTEM_PROMPT 总长: {len(m.group(1))} 字符（含 few-shot 与对照例）')
print('构建完成：全部断言通过，已落盘。')
