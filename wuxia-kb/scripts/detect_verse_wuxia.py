#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N2 · 韵文/词牌/对联三支路检测器 —— detect_verse_wuxia.py

规范源（唯一）：skills/SKILL_02a_02b_章回结构与韵文处理.md（v0.3-draft）
  §5.0  前置清洗（剥 PN/剥标注/剥围栏行；句界标点集 ，。；！？：…；"？"计入切分不扣分）
  §5.1  三支路合成决策树（署名→直入 B；行首正是→直入 C；否则 A→B→C；0.4-0.6 存疑灰区）
  §5.2  支路 A 四言整齐（评分表 + 整组投票 ≥2 行且 ≥6 句 + 但见/只见/却见 引出词降权）
  §5.3  支路 B 长短句词牌（成分分+加分制：形态 0.30 / 押韵 0.30 / 阕对称 0.20 / 署名 +0.20 / 章首 +0.10）
  §5.4  支路 C 对联（门槛三条 + 字数相等必备 + 对仗抽查 + 引出/位置加分）
  §5.5  类型归派 · §5.6 阈值汇总 · §6.2 伪信号（但见/只见/却见 永不单独触发围栏）

纯标准库。
API：detect_block(lines: list[str], context: dict) -> {"type", "score", "branch", "doubts", "metrics"}
     context 含 position（"章首"/"回末"/"回中"，缺省"回中"）。
CLI：python detect_verse_wuxia.py --book <名> --scan [--chapter N | --from A --to B]

韵组表为简化版（尾字相同或"韵腹+韵尾"近似归组，ing→eng、in/un/ün→en、ian/uan→an、
iong→ong、o/e/uo 合并等宽松合并），仅覆盖章回韵文常见尾字——待试点校准。
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import symbols

# ==================== 阈值集中区（全部"待试点校准"，02ab §5.6） ====================
TH_VERSE = 0.60           # 三支路判韵文/对句阈值
TH_GRAY_LOW = 0.40        # 存疑灰区下限（0.4-0.6 → 存疑清单，人工裁决）
TH_GRAY_HIGH = 0.60       # 存疑灰区上限
A_DOWNGRADE_TH = 0.80     # 支路 A 引出词降权阈值（但见/只见/却见 → 须 ≥此分）
A_DOWNGRADE_MIN_LINES = 3  # 降权时并须 ≥3 行
A_VOTE_MIN_LINES = 2      # 整组投票：候选组须 ≥2 行
A_VOTE_MIN_SENTS = 6      # 整组投票：且 ≥6 句
B_STACK_SIM_TH = 0.70     # 阕对称：两段句长序列相似度阈值
B_REPEAT_TH = 0.70        # 单段长词：分句节奏重复性阈值
B_RHYME_SHARE = 0.50      # 押韵：偶数句尾字同韵组占比阈值
B_RHYME_MIN_EVEN = 6      # 押韵最少偶数句证据数（i/u/en 等高频韵组在散文中易凑同组，
                          # 证据不足不记押韵分）——待试点校准
C_MAX_LINES = 2           # 支路 C 门槛 1：独立短段 ≤2 行
C_CLAUSE_COUNTS = (2, 4)  # 支路 C 门槛 3：分句数 2（单联）或 4（两联式）

# 句界标点集（§5.0）；"？"计入句切分且不扣分（§5.3 词中夹问防御）
SENT_DELIMS = set("，。；！？：…")

# 词牌署名行（§5.3 加分信号；§6.2 弱信号，只作加分不可依赖）
# 2026-11-05 扩展：容忍"——自题《某书》，调寄词牌"式署名（《江湖三女侠》001 回实态），
# 即"调寄/右调"前可有"——"与一段题序；原"——调寄沁园春"行为不变。
SIG_RE = re.compile(
    r"^\s*(?:——?\s*)?(?:[^，。！？]{1,16}[，,]\s*)?(?:调寄|右调)\s*\S+\s*$")
# 支路 A 引出词降权触发词（§6.2 伪信号：永不单独触发围栏，仅降权 + E15 哨兵）
DOWN_RE = re.compile(r"^\s*(?:但见|只见|却见)")

# ==================== 逐行成段韵文组（02ab 围栏修复 2026-11-05 批次：塞外/冰魄） ====================
# 起因（docs/49 §五.1）：旧稿（塞外/冰魄底本）把诗/歌逐句排成独立自然段（每句之间空行），
# 单块过 §5.1 决策树时行数/句数不足（支路 A 整组投票要求 ≥2 行且 ≥6 句；短句行仅 1 句），
# 整首漏检。下列常量 + 组检测函数专补该排版缺口，均为**窄规则**（宁漏勿错，见 §1.4）：
#   - 章首歌/诗组：只在 N1 常规章首判定未成立时兜底；
#   - 回中歌组：必须有"唱道/歌曰/吟道"引出段 + 口语化长句 + 短叹句；
#   - 词道组：必须有"词道/词曰："引出 + 恰上下两阕两段 + 四字句占比 >50%；
#   - 续书预告回末：只认"请续看/请看续集/续看拙著"词族（非"下回分解"，避免与套语规则重叠）。
SHORT_LINE_MAX_HAN = 20        # 短句行：单行汉字数上限（只数汉字，标点不计）
SHORT_LINE_MAX_SENTS = 2       # 短句行：最多两句（旧稿歌行常一句/半句成段）
CHAPTER_SONG_MIN_LINES = 3     # 章首短句歌组最少行数（塞外 001《哈萨克迎客歌》5 行）
CHAPTER_SONG_MAX_LINES = 12    # 章首短句组上界（防长叙事段被并入）
MID_SONG_MIN_LINES = 8         # 回中歌组最少行数（塞外 004=12 行、007=8 行）
CI_INTRO_MAX_BLOCKS = 2        # 词道引出：上下两阕恰两段（旧稿排版）——多于两段不适用
CI_MIN_SENTS_PER_BLOCK = 6     # 每阕最少句数（完整上下阕各 10+ 句）
CI_MIN_BRANCH_A = 0.90         # 合并后支路 A 下限（§5.2"四字句占比>50%"0.95 档留余量）
# 续书预告词族（§6.3 词族收录思路）：仅"请续看/请看续集/续看拙著"写法，不含"下回分解"
TAIL_PRED_RE = re.compile(r"请[看敬]续看|续看拙[著作]|请看续集")
# 回中歌引出段收尾（§6.4 引出词同级）：唱道/歌曰/吟道/唱起来道/唱了道：
SONG_INTRO_RE = re.compile(r"(?:唱|歌|吟|诵)(?:起来|了)?道[：:]\s*$")
# 回中填词引出段收尾：词道/词曰（旧稿如"…在念一首词。词道："）
CI_INTRO_RE = re.compile(r"(?:词道|词曰)[：:]\s*$")
# 章首歌组宿主段叙述信号：歌/唱/吟/哦（塞外 001 后段"歌声杂着驼铃…引吭高歌"）
SONG_CUE_RE = re.compile(r"(?:歌|唱|吟|哦)")
# 回末对引出（复用 G-24 的口径）：对句段前一段末为"正是："
ZHENGSHI_TAIL_RE = re.compile(r"正是[：:]\s*$")
# 围栏内禁半角标点（02ab §4.2 铁律 4 / E16 同口径，保守集，与 lint_fence_format 一致）
HALFWIDTH_PUNCT = set(',.;:!?()"\'<>')

# ==================== 简化韵组表（待试点校准） ====================
# 组名 = 韵腹+韵尾近似；括注为宽松合并规则。表外字记伪组 "#字"（同字相押视为同组）。
_RH_RAW = {
    # a（a/ia/ua）
    "a": "花华化话画划家加佳嘉价驾架嫁下夏侠狭霞峡辖吓掐恰洽瓦娃蛙袜沙纱杀傻厦大达答打他她它塔踏塌拿那麻码马骂妈发法罚伐阀拉把爸罢霸怕爬挂瓜夸跨",
    # eo（o/e/uo 合并，词韵歌部）
    "eo": "波播拨伯泊勃婆破坡迫魄莫漠寞魔磨摩膜末沫多歌割哥格隔阁各客课科棵颗壳咳可渴刻河荷合盒贺和乐说硕烁若弱罗锣萝逻螺裸落洛络骆火伙货祸惑获豁活或峨鹅娥俄讹饿额遏扼厄鄂",
    # ie（ie/üe）
    "ie": "列烈裂猎劣姐借街接阶皆结节洁捷界解些斜邪协携鞋写谢泄泻屑血别憋蝶跌爹叠铁贴帖捏聂孽雪月学觉绝决诀掘爵穴靴薛悦阅越约跃",
    # ai（ai/uai）
    "ai": "来赖莱台抬太态汰泰该改盖概丐开凯慨白百摆拜败拍牌排派埋买卖迈麦脉塞赛猜才材财裁栽载灾宰再在摘斋窄债寨待怠殆带戴袋代贷黛外快块",
    # ei（ei/uei）
    "ei": "美妹媚梅媒煤培陪赔佩配飞非菲肥匪肺废沸费微薇巍危为维唯伟委尾味未位卫谓喂慰雷蕾磊累垒泪类内黑悲北备背被辈倍碑卑杯",
    # ao（ao/iao）
    "ao": "高膏糕稿搞告脑恼好号毫豪壕浩耗毛矛茅锚貌冒帽猫道到倒岛盗稻老牢劳早枣灶遭糟凿躁燥造皂藻曹槽草操挑条跳调掉鸟聊辽疗僚寥缭料少绍哨烧韶潮嘲朝吵炒超巢抄钞桃陶淘逃涛滔掏讨套报抱暴爆豹保宝饱堡袍跑炮泡傲奥熬袄",
    # ou（ou/iou）
    "ou": "口后候吼猴走奏邹周州舟粥轴肘咒宙骤皱抽愁仇绸稠丑臭收手首守受授售瘦兽寿头投透偷楼搂漏陋沟钩狗够构购斗豆逗否剖谋某眸牟侯喉厚九酒久旧救就袖秀绣秋丘囚求球邮由游友有又右幼优忧悠幽幽",
    # an（an/ian/uan）
    "an": "山删衫闪善扇煽天田填甜添年念前钱千签迁牵谦乾虔遣欠歼纤坚肩间监兼煎艰检减简拣件见建健剑箭荐鉴践键连莲帘怜廉联敛脸恋炼练链面眠绵棉免勉缅边编鞭贬扁变遍辩辨便先仙鲜掀闲弦嫌贤咸衔现线限县献羡宪陷馅烟淹焉嫣燕宴艳验厌雁焰砚延严沿盐言颜岩炎研阎檐掩眼衍演缘元原圆园源员袁冤渊远院怨愿轩宣喧悬旋玄选眩绚眷卷倦绢鹃捐涓娟单担丹胆弹淡蛋旦但潭谈坛檀毯叹炭探贪摊滩瘫蓝篮岚拦栏懒烂览揽缆兰澜难南楠男燃然冉染三伞散般搬斑班颁板版半伴拌绊磐盘盼判叛潘攀帆番翻凡烦繁藩反返犯范贩泛饭惭残蚕灿参惨餐赞暂沾瞻粘毡盏斩展崭湛站战颤占颠典点电店惦垫滇恬欢环桓换唤焕患幻宦还湾弯玩完丸顽晚碗惋婉蛮馒慢漫蔓官观管馆罐灌贯惯拳权全泉圈劝券鸳渊",
    # en（en/in/uen/ün）
    "en": "门们闷恩奔本笨喷盆分芬纷坟焚粉奋份愤粪魂昏婚荤混棍滚昆坤困捆春唇纯醇淳蠢顺瞬舜润闰真诊珍甄斟贞针枕阵镇震振陈尘晨臣辰沈审婶肾甚深身神申伸绅人仁忍刃认韧任根跟恳垦肯啃痕很狠恨心新薪辛欣芯信音阴姻荫银吟印隐瘾引尹金今津筋禁仅紧谨锦尽进近晋浸劲林琳淋邻鳞麟民敏悯品拼贫频聘亲秦琴芹勤寝侵沁温文纹蚊闻稳问紊吻敦墩蹲顿盾钝遁轮论仑伦纶沦村存寸吞屯豚臀尊遵损笋孙荀询寻巡旬训讯迅熏勋云匀允运韵晕均军君菌郡俊峻竣骏群裙恨恨",
    # ang（ang/iang/uang）
    "ang": "江姜疆缰僵讲奖桨匠酱降将光广逛荒慌黄皇煌蝗凰晃谎方坊芳防妨房肪仿访纺放香乡相箱厢湘襄镶详祥翔想响享向象像橡项巷央秧殃鸯阳杨扬洋羊氧养样漾恙昂肮航杭郎廊琅榔狼朗浪良凉梁粮粱两亮谅辆量晾娘酿忙芒茫盲氓莽蟒桑嗓丧藏脏葬汤唐堂塘膛棠糖倘躺烫趟刚冈岗纲钢缸肛康慷糠抗炕长场肠常偿尝裳厂敞畅唱昌猖商伤殇赏上尚让王忘亡网往旺望妄强墙蔷抢枪腔呛床创窗闯疮装庄妆桩壮状撞幢双霜孀张章彰樟掌涨账丈杖仗",
    # eng（eng/ing 宽松合并；庚青蒸部）
    "eng": "生声升笙甥胜圣剩城成承丞惩程峥筝争征蒸正政郑证名明鸣铭冥溟茗命情晴请顷清轻青倾卿庆兢精睛晶鲸旌经静敬镜境竟竞净径劲迎营蝇赢盈颖影映应硬英樱婴鹰兵冰柄饼并病平萍凭瓶评坪亭停庭廷蜓挺听厅汀灵玲凌陵菱零龄铃岭领令星猩醒幸性姓杏兴行形型刑腥丁叮钉顶鼎定订宁凝灯登凳邓澄橙能棱冷楞恒横衡更耕羹坑朋棚硼鹏蓬篷风枫疯峰烽丰封蜂逢缝讽凤奉蒙盟萌檬朦梦孟猛藤疼腾滕层曾增憎赠崩绷蹦绳仍扔",
    # ong（ong/iong）
    "ong": "东冬董动洞冻栋中忠钟终种众重冲充涌通同童铜桐筒痛统空孔恐控红洪虹鸿哄烘工功攻公宫恭龚供共咏泳勇拥庸雍踊用龙聋笼珑咙隆垄陇拢松嵩耸宋送颂诵讼从丛匆聪葱纵总宗踪综棕粽容荣融蓉溶绒嵘熊雄穷琼穹浓农侬弄彤瞳拱贡洪",
    # i
    "i": "诗时十石识实食蚀师狮失施湿尸世事势视试式市士之只指纸志挚致治智置秩掷址侄直值职植殖执支枝知蜘芝肢脂织汁峙稚奇骑棋旗期欺漆七妻凄齐其启起器气弃汽泣契砌西希稀息熄惜昔析悉夕吸席袭媳锡溪熙嬉禧喜洗系细隙戏离璃梨犁黎篱理里礼李例荔栗力立粒历厉励利痢己记纪技忌济挤脊几机肌饥畸稽吉即极及级急疾集籍嫉意义议易益亿忆役译疫翼谊亦异衣依医一宜仪姨遗移疑颐夷沂怡贻比彼笔鄙币必毕碧蔽庇痹弊逼鼻皮疲脾匹屁僻辟譬米蜜密觅泌谧地弟第低滴抵底敌笛涤递帝蒂缔谛你逆匿腻溺题提蹄啼体替剃涕惕批披琵劈霹",
    # u
    "u": "图途涂徒屠土吐兔突书舒殊疏输蔬暑黍鼠属数树术述束出初除厨锄雏处础储楚触畜主住注驻柱祝筑竹诸猪珠株蛛逐烛如儒汝乳辱入无吴武五午舞乌污诬屋巫呜雾务物误悟木目母亩姆拇幕墓暮路露鹭鹿炉芦庐卢颅卤虏掳陆录辘碌赂古谷股骨姑孤辜鼓故固顾苦库裤酷枯哭窟胡湖葫蝴糊壶狐弧乎呼忽户护互沪夫肤孵敷服福幅蝠辐符伏俘浮扶芙腐腑府俯斧釜辅付妇负附咐富副复覆赋傅腹普谱铺扑仆朴瀑蒲菩葡部布步簿补捕不读独堵赌杜肚渡度族租祖组足卒俗宿素速塑诉肃粟缩屋乌吾梧伍侮雾鹜骛",
    # ü
    "v": "女吕侣履律虑滤绿旅屡缕驴去区曲躯趋趣取娶雨语羽玉育狱欲遇御裕豫誉愈喻宇禹郁于余鱼渔娱愉逾渝舆与予屿序叙绪续蓄絮需虚须徐许",
}
_RHYME_TABLE = {}
for _g, _chars in _RH_RAW.items():
    for _c in _chars:
        if "\u4e00" <= _c <= "\u9fff":
            _RHYME_TABLE.setdefault(_c, _g)


def rhyme_group(ch: str) -> str:
    """尾字韵组（简化版，待试点校准）。表外字返回伪组 "#字"——同字相押视为同组。"""
    return _RHYME_TABLE.get(ch, "#" + ch)


# ==================== 前置清洗（§5.0） ====================
def clean_lines(lines):
    """§5.0 清洗序：剥围栏行 → 剥 PN 标记 → 剥实体/动词/修辞标注（保留显示串）。"""
    out = []
    for ln in lines:
        if symbols.is_fence_close(ln) or symbols.fence_opens(ln):
            continue
        t = re.sub(r"\[\d+(?:\.\d+)?\]", "", ln)   # 剥 PN（[N]/[N.M]）
        t = symbols.strip_markup(t)                 # 剥标注令牌 → 显示串
        out.append(t)
    return out


def _flush(buf, res):
    han = [c for c in buf if "\u4e00" <= c <= "\u9fff"]
    if han:
        res.append((len(han), han[-1]))


def sentences_of(cleaned, drop_sig=True):
    """按句界标点集切句 → [(句长, 尾字), ...]。

    句长只数汉字（引号/书名号/破折/顿号等非句界标点不计长，§5.0"只保留汉字与中文标点"
    的长度口径）；署名行不入统计（drop_sig）。
    """
    res = []
    for ln in cleaned:
        s = ln.strip()
        if drop_sig and s and SIG_RE.match(s):
            continue
        buf = []
        for ch in s:
            if ch in SENT_DELIMS:
                _flush(buf, res)
                buf = []
            else:
                buf.append(ch)
        _flush(buf, res)
    return res


# ==================== 支路 A：四言整齐（§5.2） ====================
def branch_a(nonempty, cleaned, sents, position):
    """返回 (score, eligible, details)。eligible=False 时支路 A 不得判韵文。"""
    details = {}
    n_lines = len(nonempty)
    lengths = [x[0] for x in sents]
    n = len(lengths)
    vote_ok = n_lines >= A_VOTE_MIN_LINES and n >= A_VOTE_MIN_SENTS
    score = 0.0
    if n:
        mean = sum(lengths) / n
        var = sum((x - mean) ** 2 for x in lengths) / n
        p4 = sum(1 for x in lengths if x == 4) / n
        p35 = sum(1 for x in lengths if 3 <= x <= 5) / n
        p47 = sum(1 for x in lengths if 4 <= x <= 7) / n
        if p4 > 0.5:
            score = 0.95
        elif p35 > 0.7:
            score = 0.80
        elif p47 > 0.7:
            score = 0.70
        elif 6 <= mean <= 8 and var < 2.0:
            score = 0.75
        elif mean > 10:
            score = 0.10
        else:
            score = 0.30
        details = {"句数": n, "均长": round(mean, 2), "方差": round(var, 2),
                   "四字占比": round(p4, 2)}
    downgraded = bool(nonempty and DOWN_RE.match(nonempty[0].lstrip()))
    # 整组投票：候选组须 ≥2 行且 ≥6 句，单行四字串不得直接判韵文
    eligible = vote_ok
    # 引出词降权：但见/只见/却见 → 阈值上调至 0.8 且须 ≥3 行
    if downgraded:
        eligible = eligible and score >= A_DOWNGRADE_TH and n_lines >= A_DOWNGRADE_MIN_LINES
    details["整组投票通过"] = vote_ok
    details["引出词降权"] = downgraded
    return score, eligible, details


# ==================== 支路 B：长短句词牌（§5.3） ====================
def _seq_sim(a, b):
    """两句长序列相似度：Dice 式 2*Σmin/(Σa+Σb)（对齐前缀，长度差计入分母）。"""
    if not a or not b:
        return 0.0
    m = min(len(a), len(b))
    smin = sum(min(a[i], b[i]) for i in range(m))
    stot = sum(a) + sum(b)
    return (2.0 * smin / stot) if stot else 0.0


def _stack_symmetry(ducks):
    """阕对称相似度：≥2 段取相邻段相似度均值；单段长词按分句节奏重复性（|Δ|≤1 占比）。"""
    if len(ducks) >= 2:
        sims = [_seq_sim([x[0] for x in ducks[i]], [x[0] for x in ducks[i + 1]])
                for i in range(len(ducks) - 1)]
        return sum(sims) / len(sims)
    if len(ducks) == 1:
        lens = [x[0] for x in ducks[0]]
        if len(lens) < 2:
            return 0.0
        close = sum(1 for p, q in zip(lens, lens[1:]) if abs(p - q) <= 1)
        return close / (len(lens) - 1)
    return 0.0


def _rhyme_score(ducks, form_ok=True):
    """押韵：同阕内偶数句尾字落同一韵组（宽松判定，容忍邻韵），占比 ≥1/2 → 0.30。

    简化版韵组表；仅当长短句形态成立（form_ok）且该阕偶数句证据 ≥3 才计——
    防散文短块凑偶数句噪声，待试点校准。
    """
    if not form_ok:
        return 0.0
    for st in ducks:
        ev = [t for i, (_, t) in enumerate(st) if (i + 1) % 2 == 0]
        if len(ev) < B_RHYME_MIN_EVEN:
            continue
        groups = [rhyme_group(t) for t in ev]
        g, c = Counter(groups).most_common(1)[0]
        if c / len(ev) >= B_RHYME_SHARE:
            return 0.30
    return 0.0


def branch_b(nonempty, cleaned, sents, position, sig_present):
    """成分分+加分制：形态 0.30 + 押韵 0.30 + 阕对称 0.20 + 署名 +0.20 + 章首 +0.10。"""
    parts = {}
    verse_lines = [l.strip() for l in cleaned if l.strip() and not SIG_RE.match(l.strip())]
    ducks = []
    for ln in verse_lines:
        st = sentences_of([ln], drop_sig=True)
        if st:
            ducks.append(st)
    lengths = [x[0] for st_ in ducks for x in st_]
    # 长短句形态 0.30：句长 ∈[2,9] / 极差 ≥3 / 均长 ≤7（全部满足）
    form_ok = False
    if lengths:
        span = max(lengths) - min(lengths)
        mean = sum(lengths) / len(lengths)
        if all(2 <= x <= 9 for x in lengths) and span >= 3 and mean <= 7:
            parts["长短句形态"] = 0.30
            form_ok = True
    # 押韵 0.30（偶数句尾字同韵组；问句号计入切分不扣分；以形态成立为前置）
    r = _rhyme_score(ducks, form_ok=form_ok)
    if r:
        parts["押韵"] = r
    # 阕对称 0.20
    sim = _stack_symmetry(ducks)
    if sim >= B_STACK_SIM_TH:
        parts["阕对称"] = 0.20
    # 词牌署名 +0.20（弱信号，只作加分）
    if sig_present:
        parts["词牌署名"] = 0.20
    # 章首位置 +0.10
    if position == "章首":
        parts["章首位置"] = 0.10
    score = sum(parts.values())
    details = {**parts, "阕对称相似度": round(sim, 2), "韵组表": "简化版，待试点校准"}
    return score, True, details


# ==================== 支路 C：对联（§5.4） ====================
# 门槛 2：无第三人称叙事框架成分（代词主语 / 引语框架 / 引号）
PRON_RE = re.compile(r"[他她它]")
FRAME_RE = re.compile(r"(说道|笑道|喝道|叫道|问道|答道|骂道|喊道|写道|吟道|唱道|赞道|叹道"
                      r"|低声道|朗声道|冷冷道|沉声道|念道|：\"|“|”)")
# 楹联语境词（+0.20）
ALCOVE_RE = re.compile(r"(楹联|门联|对联|联曰|对曰|(?:壁上|柱上|门旁|门上|殿前|堂前|厅前|两侧|龛前|龛旁).{0,6}(?:联|楹|对))")

_NOM_TAILS = set(
    "手侯城旁台楼阁殿宫门窗户壁柱梁舟车马鞭剑刀枪弓箭旗鼓琴棋书诗酒花草叶枝根果"
    "布珠玉金银铜铁钗环裳衣帽鞋袍衫带囊匣壶瓶杯盘灯烛光影片影云霞烟雨雪风霜露雷"
    "山泉溪江河海洋岛滩岸峰峦岭崖谷坡径途路桥街巷市镇村邦国州郡县关塞津渡"
    "人心肠头面目脸眉眼口齿牙语险纸道魂梦世运命功名利禄爵位职军民吏卒兵将帅"
    "王侯伯子男公卿相客宾客友朋侣伴侣俦仇敌党徒僧道尼仙妖魔鬼怪神佛圣贤愚智"
)
_VERB_CHARS = set("施煞吓断来去杀斩惊震笑说打飞落起开守攻破灭沉浮摇夺避让追奔逃"
                  "顾盼看听闻唱吟叹念拜跪立坐行止舞吼啸呼喊哭泣骂问答读写诵读走")


def _pos_class(unit):
    """两字单元词性简化判定：末字名词性优先 → 名词性；含动词字 → 动词性；其余 other。"""
    if unit and unit[-1] in _NOM_TAILS:
        return "n"
    if any(c in _VERB_CHARS for c in unit):
        return "v"
    return "x"


def branch_c(nonempty, cleaned, position):
    """门槛（≤2 行 / 无叙事框架 / 分句数 2 或 4）→ 字数相等必备 → 对仗抽查 + 位置加分。"""
    text = "".join(nonempty)
    # 门槛 1：独立短段 ≤2 行
    if len(nonempty) > C_MAX_LINES:
        return 0.0, False, {"门槛": f"行数 {len(nonempty)} > {C_MAX_LINES}"}
    # 门槛 2：无第三人称叙事框架成分（白话对仗描写第一道闸，S13）
    if PRON_RE.search(text) or FRAME_RE.search(text):
        return 0.0, False, {"门槛": "含叙事框架成分（代词主语/引语框架/引号）"}
    # 门槛 3：分句数 = 2（单联）或 4（两联式）；行首引出词"正是："剥除后计
    body = re.sub(r"^\s*正是[：:]?\s*", "", text)
    bodies = []   # 分句的纯汉字串（首/尾二字抽查与字数比较共用）
    buf = []
    for ch in body:
        if ch in SENT_DELIMS:
            han = "".join(c for c in buf if "\u4e00" <= c <= "\u9fff")
            if han:
                bodies.append(han)
            buf = []
        else:
            buf.append(ch)
    han = "".join(c for c in buf if "\u4e00" <= c <= "\u9fff")
    if han:
        bodies.append(han)
    if len(bodies) not in C_CLAUSE_COUNTS:
        return 0.0, False, {"门槛": f"分句数 {len(bodies)} ∉ {C_CLAUSE_COUNTS}"}
    # 字数相等（必备，不满足直接出局）
    if len(bodies) == 2:
        hpairs = [(bodies[0], bodies[1])]
    else:
        hpairs = [(bodies[0], bodies[2]), (bodies[1], bodies[3])]
    if any(len(a) != len(b) for a, b in hpairs):
        return 0.0, False, {"门槛": "上下句字数不相等（必备条件）"}
    # 对仗抽查：首二字 + 尾二字词性简化判定（宽对即可）
    hits = total = 0
    for a, b in hpairs:
        for u, v in ((a[:2], b[:2]), (a[-2:], b[-2:])):
            total += 1
            if _pos_class(u) == _pos_class(v):
                hits += 1
    dui = 0.6 if hits == total else (0.4 if hits >= 1 else 0.1)
    details = {"对仗": dui, "对仗命中": f"{hits}/{total}",
               "字数": "=".join(str(len(x)) for x in bodies)}
    # 引出/位置加分（最高 +0.40）
    score = dui
    if nonempty[0].lstrip().startswith("正是"):
        score += 0.20
        details["行首正是"] = 0.20
    if position == "回末":
        score += 0.10
        details["回末位置"] = 0.10
    if ALCOVE_RE.search(text):
        score += 0.20
        details["楹联语境"] = 0.20
    return score, True, details


# ==================== 类型归派（§5.5） ====================
GE_YIN_RE = re.compile(r"(歌曰|唱道|吟道|歌罢|吟罢|唱罢|作歌|口号)")


def classify(branch, position, lengths, nonempty, sig=False):
    """韵文判定成立后的围栏类型归派（§5.5 决策树，诗/歌两可→诗 保守归派）。

    sig=True（有"调寄/右调 X"署名行）→ 词牌硬信号，直接归"词"（2026-11-05 补：
    菩萨蛮等长短句词牌，句长不齐时易被误归"诗"）。
    """
    if sig:
        return "词"
    uniform = bool(lengths) and (max(lengths) - min(lengths) <= 1)
    if branch == "C":
        zs = bool(nonempty) and nonempty[0].lstrip().startswith("正是")
        return "回末对" if (position == "回末" and zs) else "对联"
    if position == "章首":
        # 章首块：支路 B 强 → 词；五七言/四言整齐 → 诗
        return "诗" if (branch == "A" or uniform) else "词"
    if GE_YIN_RE.search("".join(nonempty)):
        return "歌"
    if branch == "A" or uniform:
        # 句长整齐（极差≤1）按五七言/四言归诗（即使评分走支路 B）
        return "诗"
    return "词"


# ==================== 合成决策树（§5.1） ====================
def detect_block(lines, context=None):
    """三支路检测入口。context：{"position": "章首"|"回末"|"回中"}（缺省"回中"）。

    返回 {"type", "score", "branch", "doubts", "metrics"}：
      type ∈ 词/诗/歌/对联/回末对（判定成立）｜"存疑"（0.4-0.6 灰区）｜"正文"（散文）。
    """
    context = context or {}
    position = context.get("position", "回中")
    doubts = []
    cleaned = clean_lines(lines)
    nonempty = [l.strip() for l in cleaned if l.strip()]
    sig_present = any(SIG_RE.match(l) for l in nonempty)
    sents = sentences_of(cleaned, drop_sig=True)
    metrics = {"非空行": len(nonempty), "句数": len(sents), "词牌署名": sig_present,
               "位置": position}

    checks = []  # (branch, score, eligible, details)
    if sig_present:
        # §5.1 第 1a 步：有词牌署名行 → 直入支路 B
        checks.append(("B", *branch_b(nonempty, cleaned, sents, position, True)))
    elif nonempty and nonempty[0].startswith("正是"):
        # §5.1 第 1b 步：行首"正是：" → 直入支路 C
        checks.append(("C", *branch_c(nonempty, cleaned, position)))
    else:
        # §5.1 第 1d 步：按支路 A → B → C 顺序评分
        checks.append(("A", *branch_a(nonempty, cleaned, sents, position)))
        checks.append(("B", *branch_b(nonempty, cleaned, sents, position, False)))
        checks.append(("C", *branch_c(nonempty, cleaned, position)))

    metrics["支路"] = {br: {"得分": round(s, 2), "有效": ok, "细节": d}
                      for br, s, ok, d in checks}
    eligible = [(br, s, d) for br, s, ok, d in checks if ok]
    if not eligible:
        return {"type": "正文", "score": 0.0, "branch": None,
                "doubts": doubts, "metrics": metrics}
    br, best, detail = max(eligible, key=lambda x: x[1])
    # 词牌署名直判（2026-11-05 补，02ab §5.3/§6.4）：署名行是词牌硬信息，且 34 部书
    # 全量普查已把"调寄"从弱信号上调为真实信号；前置条件全部满足即归"词"，不因
    # 菩萨蛮式 5/7 交替（句长极差 2）卡在支路 B 的"极差≥3"形态分上。
    if sig_present and len(nonempty) >= 3:
        verse_lines = [l for l in nonempty if not SIG_RE.match(l)]
        joined = "".join(verse_lines)
        if (len(sents) >= 4 and all(x[0] <= 12 for x in sents)
                and "“" not in joined and "”" not in joined):
            metrics["署名直判"] = True
            return {"type": "词", "score": max(best, TH_GRAY_HIGH), "branch": br,
                    "doubts": doubts, "metrics": metrics}
    if best >= TH_GRAY_HIGH:
        lengths = [x[0] for x in sents]
        ftype = classify(br, position, lengths, nonempty, sig_present)
        return {"type": ftype, "score": min(best, 1.0), "branch": br,
                "doubts": doubts, "metrics": metrics}
    if best >= TH_GRAY_LOW:
        doubts.append(
            f"得分 {best:.2f} 落在存疑灰区 [{TH_GRAY_LOW},{TH_GRAY_HIGH}) → 存疑清单"
            f"（人工裁决，02ab §5.1/§8.2）；入选支路 {br}")
        return {"type": "存疑", "score": best, "branch": br,
                "doubts": doubts, "metrics": metrics}
    return {"type": "正文", "score": best, "branch": br,
            "doubts": doubts, "metrics": metrics}


# ==================== 章首候选组（§8.1 阶段 2；N1 复用） ====================
def plausible_verse(ls):
    """章首/署名组贪心合并的"似韵文"廉价预筛：无引号、≥2 句、最长句 ≤12 字。

    2026-11-05 由 ≥3 句放宽为 ≥2 句：《江湖三女侠》001 回章首《菩萨蛮》上下阕
    按五七言短句逐段分段（"弹指数华年，华年梦似烟。"仅 2 句），>3 句门槛使
    章首候选组在首段即停、整首词未被围栏；散文段因单句超 12 字仍被排除。
    """
    text = "".join(ls)
    if "“" in text or "”" in text:
        return False
    st = sentences_of(clean_lines(ls))
    if len(st) < 2:
        return False
    return max(x[0] for x in st) <= 12


def group_chapter_head(paras):
    """回目后第一候选组贪心合并：首段 + 后续似韵文段 + 结尾署名行段。

    paras: list[list[str]]（每段=若干原始行）。返回 (组内段列表, 消耗段数)。
    阕间空行在底本中分隔各段；合并后整体一 PN 一围栏（§2.3，S12 防阕间断栏）。
    """
    if not paras:
        return [], 0
    group = [paras[0]]
    j = 1
    while j < len(paras):
        first = paras[j][0].strip()
        if SIG_RE.match(first):
            group.append(paras[j])
            j += 1
            break
        if plausible_verse(paras[j]):
            group.append(paras[j])
            j += 1
        else:
            break
    return group, j


# ==================== 逐行成段韵文组补检（02ab 围栏修复 2026-11-05 批次） ====================
def is_short_line_block(ls):
    """旧稿"逐行成段"韵文行：单行、≤2 句、无引号、汉字数 ≤SHORT_LINE_MAX_HAN。

    旧稿底本每句诗/歌独立成段（空行分隔），一轮检测把每段当独立候选块；本函数只做
    形态预筛，判定仍由组级规则（章首歌/诗、回中歌、词道）承担。
    """
    if len(ls) != 1:
        return False
    s = ls[0].strip()
    if not s or "“" in s or "”" in s or '"' in s:
        return False
    han = [c for c in s if "\u4e00" <= c <= "\u9fff"]
    if not 1 <= len(han) <= SHORT_LINE_MAX_HAN:
        return False
    st = sentences_of([s], drop_sig=False)
    return 1 <= len(st) <= SHORT_LINE_MAX_SENTS


def _short_line_run(paras, start, max_lines=None):
    """从 start 段起连续短句行段数（受 max_lines 限制）。"""
    j = start
    while j < len(paras) and is_short_line_block(paras[j]):
        if max_lines is not None and j - start >= max_lines:
            break
        j += 1
    return j - start


def _group_sents(paras):
    """组内句序列（清洗后按句界切分，署名行不入统计）。"""
    return sentences_of(clean_lines([ln for p in paras for ln in p]), drop_sig=True)


def _group_form_ok(sents):
    """§5.3 长短句形态：全部句长 ∈[2,9] / 极差 ≥3 / 均长 ≤7（全部满足）。"""
    lengths = [x[0] for x in sents]
    if not lengths:
        return False
    span = max(lengths) - min(lengths)
    mean = sum(lengths) / len(lengths)
    return all(2 <= x <= 9 for x in lengths) and span >= 3 and mean <= 7


def chapter_head_verse(paras):
    """章首逐行成段歌/诗组补检（02ab §2.3 章首探测、§5.5 类型归派；仅 N1 常规判定未成立时兜底）。

    旧稿每句独立成段，N1 章首组只贪心合并"似韵文段"（≥2 句），单句成段的歌词首段即
    中断 → 整首漏检（塞外 001 五段短句、冰魄 001 两段七言）。返回 dict 或 None：

    歌组（塞外 001 先例：5 行短句 + 后段"歌声杂着驼铃…引吭高歌"叙述信号）：
      1) 首段起连续 3-12 个短句行段（组内无引号）；
      2) 句长口语化不齐：句长极差 ≥4 或含 ≤3 字短叹句（整齐五七言不在此列，归诗组）；
      3) 组后第一段（正文宿主段）前 80 字含 歌/唱/吟/哦 叙述信号（§6.4 引出词同级强确认）。
    诗组（冰魄 001 先例：两段七言、四句）：
      1) 首段起恰 2 个短句行段（组内无引号）；
      2) 共 4 句且全为 5 言或全为 7 言（旧稿引五绝/七绝常态）；
      3) 偶数句尾字同韵组（2/2；韵组表简化版——宁可少判，待试点校准）。
    """
    n = len(paras)
    if n < 2:
        return None
    run = _short_line_run(paras, 0, CHAPTER_SONG_MAX_LINES)
    if run < 2:
        return None
    group = paras[:run]
    joined = "".join("".join(p) for p in group)
    if "“" in joined or "”" in joined:
        return None
    sents = _group_sents(group)
    if not sents:
        return None
    lengths = [x[0] for x in sents]
    if run >= CHAPTER_SONG_MIN_LINES:
        span = max(lengths) - min(lengths)
        has_cry = min(lengths) <= 3
        cue_para = "".join(paras[run])[:80] if run < n else ""
        m = SONG_CUE_RE.search(cue_para)
        if (span >= 4 or has_cry) and m:
            return {"type": "歌", "score": 0.60, "branch": "章首-逐行歌组",
                    "consumed": run, "doubts": [],
                    "metrics": {"行数": run, "句长": lengths, "句长极差": span,
                                "宿主段歌信号": m.group(0)}}
    if run == 2 and len(sents) == 4:
        for yan in (5, 7):
            if all(x == yan for x in lengths):
                even = [t for i, (_, t) in enumerate(sents) if (i + 1) % 2 == 0]
                groups = {rhyme_group(t) for t in even}
                if len(groups) == 1:
                    return {"type": "诗", "score": 0.60, "branch": "章首-七言/五言组",
                            "consumed": 2, "doubts": [],
                            "metrics": {"行数": 2, "句长": lengths,
                                        "偶句韵组": sorted(groups)}}
    return None


def song_intro_group(paras, k):
    """回中歌组补检（02ab §2.5 回中即兴歌）：引出段末"唱道/歌曰/吟道/唱起来道："。

    条件（窄规则，宁漏勿错）：
      1) 引出段（k）末为唱/歌/吟/诵 + 道：；
      2) k+1 起连续 ≥8 个短句行段（塞外 004=12 行、007=8 行），组内无引号；
      3) 句长口语化不齐（§5.5 歌判据）：§5.3"长短句形态"不成立且存在 >9 字长句；
      4) 含 ≤3 字短叹句（"依啦/姑娘呀"式口语标记）。
    返回 {"consumed", "metrics"} 或 None（宿主引出句由调用方留正文，§4.4 正误对照）。
    """
    if not SONG_INTRO_RE.search("".join(paras[k])):
        return None
    run = _short_line_run(paras, k + 1)
    if run < MID_SONG_MIN_LINES:
        return None
    group = paras[k + 1:k + 1 + run]
    joined = "".join("".join(p) for p in group)
    if "“" in joined or "”" in joined:
        return None
    sents = _group_sents(group)
    if not sents:
        return None
    lengths = [x[0] for x in sents]
    if _group_form_ok(sents):
        return None                     # 整齐短句 → 交常规支路 A/B，不按歌处理
    if min(lengths) > 3 or max(lengths) <= 9:
        return None                     # 无口语短叹句 / 无口语化长句 → 证据不足，宁漏
    return {"consumed": run, "doubts": [],
            "metrics": {"行数": run, "句长": lengths,
                        "句长极差": max(lengths) - min(lengths)}}


def ci_intro_group(paras, k):
    """回中填词补检（02ab §2.5）：引出段末"词道/词曰："+ 上下两阕两段（旧稿两段排版）。

    条件（窄规则，宁漏勿错）：
      1) 引出段（k）末为词道/词曰：；
      2) k+1、k+2 两段均为单行长段（每段 ≥6 句、无引号）；k+3 段不是短句行
         （防把逐句排版的词误当两阕）；
      3) 两段单看均未达 N2 围栏阈值（<TH_VERSE；否则既有单块判定已覆盖，不重复围栏）；
      4) 合并后支路 A ≥0.90（§5.2 "四字句占比>50%"0.95 档留余量；《解连环》式词牌句式）。
    返回 {"type": "词", "score", "branch", "consumed", "metrics"} 或 None。
    """
    if not CI_INTRO_RE.search("".join(paras[k])):
        return None
    cand = paras[k + 1:k + 1 + CI_INTRO_MAX_BLOCKS]
    if len(cand) < CI_INTRO_MAX_BLOCKS:
        return None
    for p in cand:
        if len(p) != 1 or "“" in p[0] or "”" in p[0]:
            return None
        if len(sentences_of(clean_lines(p), drop_sig=True)) < CI_MIN_SENTS_PER_BLOCK:
            return None
        if detect_block(p, {"position": "回中"})["score"] >= TH_VERSE:
            return None
    nxt = paras[k + 1 + CI_INTRO_MAX_BLOCKS] if k + 1 + CI_INTRO_MAX_BLOCKS < len(paras) else None
    if nxt is not None and is_short_line_block(nxt):
        return None
    sents = _group_sents(cand)
    cleaned = clean_lines([ln for p in cand for ln in p])
    nonempty = [l.strip() for l in cleaned if l.strip()]
    score, eligible, details = branch_a(nonempty, cleaned, sents, "回中")
    if not eligible or score < CI_MIN_BRANCH_A:
        return None
    return {"type": "词", "score": score, "branch": "词道-上下阕",
            "consumed": CI_INTRO_MAX_BLOCKS, "doubts": [],
            "metrics": {**details, "句数": len(sents)}}


def is_couplet_block(ls):
    """独立对句段：单行、2 分句、去标点后字数相等、无引号。"""
    if len(ls) != 1:
        return False
    text = ls[0].strip()
    if not text or "“" in text or "”" in text or '"' in text:
        return False
    body = re.sub(r"^\s*正是[：:]\s*", "", text)
    clauses = [c for c in re.split(r"[，。；！？：…]", body) if c.strip()]
    if len(clauses) != 2:
        return False
    counts = [len([ch for ch in c if "\u4e00" <= ch <= "\u9fff"]) for c in clauses]
    return counts[0] == counts[1] > 0


def tail_prediction(paras):
    """回末边界补检（02ab §2.4 回末约定、§6.3 词族扩展）：续书预告段 → 回末围栏。

    末 3 段内出现"续书预告"词族（请续看/请看续集/续看拙著）即整段不标围栏：
      - 若预告段前一段是"正是："引出的对句（再前一段末为"正是："），对句段一并纳入
        （塞外 028 旧稿 `::: 回末` 先例：对句 + 预告 +（全书完）整体一栏）；
      - 覆盖到回末最后一个内容块；收束段若含半角标点（如冰魄 012 底本作 "(全书完)"，
        ASCII 括号）则不纳入围栏——围栏内禁半角标点（§4.2 铁律 4/E16），该段按正文
        保留，可逆性不受影响。
    只认续书预告词族、不认"下回分解"，与既有回末套语强信号规则不重叠。
    返回 {"start", "consumed", "reason"} 或 None。
    """
    n = len(paras)
    if n < 1:
        return None
    idx = None
    for i in range(max(0, n - 3), n):
        if TAIL_PRED_RE.search("".join(paras[i])):
            idx = i
            break
    if idx is None:
        return None
    end = n
    while end - 1 > idx and any(ch in HALFWIDTH_PUNCT
                                for ch in "".join(paras[end - 1])):
        end -= 1                        # 含半角标点的收束段不入围栏（E16）
    start = idx
    if (idx >= 2 and is_couplet_block(paras[idx - 1])
            and ZHENGSHI_TAIL_RE.search(paras[idx - 2][-1].strip())):
        start = idx - 1
    return {"start": start, "consumed": end - start,
            "reason": "续书预告词族（请续看/请看续集）+ 回末收束"}



# ==================== CLI：--scan 全书候选报告 ====================
_TITLE_LINE_RE = re.compile(r"^\s*第[一二三四五六七八九十百零〇\d]+回")
# 回末套语词族：单一来源 symbols（2026-11-05 对齐；生成器与 lint E12 共用）
TAOYU_HEAD_RE = symbols.TAOYU_HEAD_RE
TAOYU_TAIL_RE = symbols.TAOYU_TAIL_RE


def _split_blocks(lines):
    """底本行 → [(起始行号 1-based, [原始行...])]，按空行分段。"""
    blocks = []
    cur, start = [], None
    for i, ln in enumerate(lines):
        if ln.strip():
            if not cur:
                start = i + 1
            cur.append(ln)
        else:
            if cur:
                blocks.append((start, cur))
                cur = []
    if cur:
        blocks.append((start, cur))
    return blocks


def scan_book(book, lo=None, hi=None):
    """扫描该书回范围，候选报告（行号/类型/得分/摘句）落 config.DIR_LOGS/verse_scan/。"""
    meta = config.books().get(book)
    if not meta:
        print(f"错误：书目未发现：{book}（config.books() 键：{config.book_names()}）")
        sys.exit(2)
    chapters = meta["chapters"]
    lo = lo or 1
    hi = hi or chapters
    out_dir = config.DIR_LOGS / "verse_scan"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    gray_rows = []
    type_count = Counter()
    for no in range(lo, hi + 1):
        path = config.chapter_path(book, no)
        raw = path.read_text(encoding="utf-8-sig")
        lines = raw.splitlines()
        ti = 0
        for i, ln in enumerate(lines):
            if _TITLE_LINE_RE.match(ln):
                ti = i
                break
        blocks = _split_blocks(lines[ti + 1:])
        n = len(blocks)
        paras = [ls for _, ls in blocks]
        k = 0
        while k < n:
            start, ls = blocks[k]
            position = "章首" if k == 0 else ("回末" if k >= n - 2 else "回中")
            text = ls[0].strip()
            remark = ""
            if k == 0:
                group, consumed = group_chapter_head(paras[k:])
                ls = [ln for g in group for ln in g]
                if consumed > 1:
                    remark = f"章首组合并 {consumed} 段"
                k += consumed
            else:
                k += 1
            if SIG_RE.match(text):
                remark = (remark + "；" if remark else "") + "词牌署名行（随前块，不单独判）"
                rows.append((no, start, position, "-", "-", "-", text[:24], remark))
                continue
            taoyu = bool(TAOYU_HEAD_RE.search(text) and TAOYU_TAIL_RE.search(text))
            if taoyu:
                remark = (remark + "；" if remark else "") + "回末套语词族命中（N1 强信号围栏）"
                type_count["回末(套语)"] += 1
                rows.append((no, start, position, "词族", "回末", "-", text[:24], remark))
                continue
            res = detect_block(ls, {"position": position})
            score = round(res["score"], 2)
            excerpt = re.sub(r"\s+", "", text)[:24]
            if res["type"] == "存疑":
                gray_rows.append((no, start, position, res["branch"], score, excerpt))
                rows.append((no, start, position, res["branch"], "存疑", score, excerpt, remark))
            elif res["score"] >= TH_GRAY_LOW:
                type_count[res["type"]] += 1
                rows.append((no, start, position, res["branch"], res["type"], score, excerpt, remark))
            # <0.4 散文不列
    # 汇报
    rep = []
    rep.append(f"# 韵文检测扫描报告 · {book}（{lo:03d}-{hi:03d} / 共 {chapters} 回）")
    rep.append("")
    rep.append(f"- 生成：detect_verse_wuxia.py（SKILL_02a/02b v{config.SPEC_VERSION} 三支路决策树）")
    rep.append(f"- 阈值：判韵文 ≥{TH_VERSE}；存疑灰区 [{TH_GRAY_LOW},{TH_GRAY_HIGH})；"
               f"<{TH_GRAY_LOW} 散文不列。全部待试点校准。")
    rep.append(f"- 韵组表：简化版（尾字同组或韵腹+韵尾近似归并），待试点校准。")
    rep.append("")
    rep.append("| 回 | 行 | 位置 | 支路 | 类型 | 得分 | 摘句 | 备注 |")
    rep.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        rep.append("| " + " | ".join(str(x) for x in r) + " |")
    rep.append("")
    rep.append(f"统计：判定成立 {sum(type_count.values())} 处（"
               + "，".join(f"{t} {c}" for t, c in sorted(type_count.items()))
               + f"）；存疑 {len(gray_rows)} 处。")
    if gray_rows:
        rep.append("")
        rep.append("## 存疑清单（0.4-0.6 灰区，人工裁决）")
        rep.append("")
        rep.append("| 回 | 行 | 位置 | 支路 | 得分 | 摘句 |")
        rep.append("|---|---|---|---|---|---|")
        for r in gray_rows:
            rep.append("| " + " | ".join(str(x) for x in r) + " |")
    rep.append("")
    out_path = out_dir / f"{book}_scan_{lo:03d}-{hi:03d}.md"
    out_path.write_text("\n".join(rep), encoding="utf-8")
    print(f"扫描 {book} 第 {lo:03d}-{hi:03d} 回：候选 {len(rows)} 行"
          f"（判定成立 {sum(type_count.values())}，存疑 {len(gray_rows)}）")
    print(f"报告 → {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="N2 韵文/词牌/对联三支路检测器（SKILL_02a/02b §5）")
    ap.add_argument("--book", help="书名（config.books() 键）")
    ap.add_argument("--scan", action="store_true", help="扫描候选报告模式")
    ap.add_argument("--chapter", type=int, help="只扫单回")
    ap.add_argument("--from", dest="lo", type=int, help="起始回号")
    ap.add_argument("--to", dest="hi", type=int, help="结束回号")
    args = ap.parse_args()
    if not args.book or not args.scan:
        ap.print_help()
        sys.exit(2)
    lo = args.chapter if args.chapter else args.lo
    hi = args.chapter if args.chapter else args.hi
    scan_book(args.book, lo, hi)


if __name__ == "__main__":
    main()
