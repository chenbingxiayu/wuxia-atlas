# N6 跨书归并 · 双人复核队列

- 生成：2026-11-05T17:50:54；规格：n6-v1.0
- 候选：140 条（E1 0 / E2 0 / E3 13 / E4 127）
- 规则：`skills/SKILL_跨书治理_武侠版.md` §2（E1-E4）/§3（L1-L4）/§4（双层 canonical）/§7.2（bare B0-B8）/§8.2（双人门槛）

## 一、状态机

```
pending ──A通过──▶ reviewer_a ──B通过──▶ approved ──回写──▶ merged
   │                  │
   └──A拒绝───────────┴──B拒绝──▶ rejected（保留候选与证据，可撤销重判）
E1（免双人）：pending_sample ──5% 抽验通过──▶ approved
```
状态取值：pending / pending_sample / reviewer_a / reviewer_b / approved / rejected / deferred；每次流转在 `history` 追加 {by,date,from,to,note}。

## 二、复核门槛（D07 §8.2）

| 证据级 | 门槛 | 抽验 |
|---|---|---|
| E1 正文明示 | 免双人 | 5% |
| E2 序跋 / E3 情节暗示 | 全量双人 | — |
| E4 读者推断 | 不进归并（仅候选池） | — |
| display_canonical 变更 / unmerge / 底本切换 | 全量双人 | — |

## 三、复核队列（proposal / merge；双人复核门槛见 §二）

| # | candidate_id | 级 | conf | 建议动作 | 书/成员 | 系列建议 | 状态 | reviewer_a | reviewer_b |
|---|---|---|---|---|---|---|---|---|---|
| 1 | N6-0007 | E3 | ok | proposal | 冰魄寒光剑、江湖三女侠：桂华生 | 桂华生 | pending | （待填） | （待填） |
| 2 | N6-0009 | E3 | ok | proposal | 塞外奇侠传、白发魔女传：焦化 | 焦化 | pending | （待填） | （待填） |
| 3 | N6-0010 | E3 | ok | proposal | 塞外奇侠传、白发魔女传：甘天立 | 甘天立 | pending | （待填） | （待填） |
| 4 | N6-0013 | E3 | ok | proposal | 塞外奇侠传、白发魔女传：青蓑道人 | 青蓑道人 | pending | （待填） | （待填） |
| 5 | N6-0029 | E4 | todo | proposal | 冰魄寒光剑、江湖三女侠：吕四娘 | 吕四娘 | pending | （待填） | （待填） |
| 6 | N6-0035 | E4 | todo | proposal | 冰魄寒光剑、白发魔女传：唐三藏 | 唐三藏 | pending | （待填） | （待填） |
| 7 | N6-0038 | E4 | todo | proposal | 冰魄寒光剑、江湖三女侠：唐晓澜 | 唐晓澜 | pending | （待填） | （待填） |
| 8 | N6-0039 | E4 | todo | proposal | 冰魄寒光剑、江湖三女侠：唐赛花 | 唐赛花 | pending | （待填） | （待填） |
| 9 | N6-0060 | E4 | todo | proposal | 江湖三女侠、白发魔女传：岳家 | 岳家 | pending | （待填） | （待填） |
| 10 | N6-0065 | E4 | todo | proposal | 冰魄寒光剑、江湖三女侠：年羹尧 | 年羹尧 | pending | （待填） | （待填） |
| 11 | N6-0070 | E4 | todo | proposal | 冰魄寒光剑、江湖三女侠：方今明 | 方今明 | pending | （待填） | （待填） |
| 12 | N6-0077 | E4 | todo | proposal | 江湖三女侠、白发魔女传：李家 | 李家 | pending | （待填） | （待填） |
| 13 | N6-0083 | E4 | todo | proposal | 江湖三女侠、白发魔女传：杨家 | 杨家 | pending | （待填） | （待填） |
| 14 | N6-0094 | E4 | todo | proposal | 江湖三女侠、白发魔女传：汉武帝 | 汉武帝 | pending | （待填） | （待填） |
| 15 | N6-0102 | E4 | todo | proposal | 冰魄寒光剑、江湖三女侠：王敖 | 王敖 | pending | （待填） | （待填） |
| 16 | N6-0116 | E4 | todo | proposal | 冰魄寒光剑、江湖三女侠：苏东坡 | 苏东坡 | pending | （待填） | （待填） |
| 17 | N6-0122 | E4 | todo | proposal | 冰魄寒光剑、江湖三女侠、白发魔女传：达摩祖师 | 达摩祖师 | pending | （待填） | （待填） |

> 待复核 17 条（E2/E3/E4 全量双人；E1 免双人抽验 5%）。另有 123 条已判定不归并（审计记录见 §四）。

## 四、已判定不归并（审计记录）

| candidate_id | 处置 | 成员 | 理由 |
|---|---|---|---|
| N6-0001 | already_merged | 七剑下天山→凌未风、江湖三女侠→凌未风 | 种子已归并（registry 同一实体覆盖全部成员） |
| N6-0002 | already_merged | 七剑下天山→卓一航、塞外奇侠传→卓一航、白发魔女传→卓一航 | 种子已归并（registry 同一实体覆盖全部成员） |
| N6-0003 | already_merged | 七剑下天山→飞红巾、塞外奇侠传→哈玛雅、江湖三女侠→飞红巾 | 种子已归并（registry 同一实体覆盖全部成员） |
| N6-0004 | already_merged | 七剑下天山→晦明禅师、塞外奇侠传→晦明禅师、白发魔女传→岳鸣珂 | 种子已归并（registry 同一实体覆盖全部成员） |
| N6-0005 | already_merged | 七剑下天山→杨云骢、塞外奇侠传→杨云骢 | 种子已归并（registry 同一实体覆盖全部成员） |
| N6-0006 | already_merged | 七剑下天山→桂仲明、江湖三女侠→桂仲明 | 种子已归并（registry 同一实体覆盖全部成员） |
| N6-0008 | already_merged | 七剑下天山→楚昭南、塞外奇侠传→楚昭南 | 种子已归并（registry 同一实体覆盖全部成员） |
| N6-0011 | already_merged | 七剑下天山→练霓裳、塞外奇侠传→练霓裳、白发魔女传→练霓裳 | 种子已归并（registry 同一实体覆盖全部成员） |
| N6-0012 | already_merged | 七剑下天山→辛龙子、白发魔女传→辛龙子 | 种子已归并（registry 同一实体覆盖全部成员） |
| N6-0014 | registry_multi_entity | 七剑下天山→杨一维、塞外奇侠传→杨云骢、江湖三女侠→杨仲英 | 同 surface「杨大哥」跨书异名（杨一维、杨云骢、杨仲英）→ 候选池（E4），不自动归并 |
| N6-0015 | registry_multi_entity | 七剑下天山→王刚、白发魔女传→王嘉胤 | 同 surface「王大哥」跨书异名（王刚、王嘉胤）→ 候选池（E4），不自动归并 |
| N6-0016 | registry_multi_entity | 七剑下天山→石大哥、白发魔女传→石浩 | 同 surface「石大哥」跨书异名（石大哥、石浩）→ 候选池（E4），不自动归并 |
| N6-0017 | registry_multi_entity | 七剑下天山→纳兰小姐、塞外奇侠传→纳兰明慧 | 同 surface「纳兰小姐」跨书异名（纳兰小姐、纳兰明慧）→ 候选池（E4），不自动归并 |
| N6-0018 | already_merged | 七剑下天山→伊土达、塞外奇侠传→伊土达 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0019 | already_merged | 七剑下天山→伊士达、塞外奇侠传→伊士达 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0020 | already_merged | 七剑下天山→何绿华、塞外奇侠传→何绿华、白发魔女传→何绿华 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0021 | already_merged | 七剑下天山→傅青主、冰魄寒光剑→傅青主、江湖三女侠→傅青主 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0022 | already_merged | 七剑下天山→兵部、白发魔女传→兵部 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0023 | already_merged | 七剑下天山→冒浣莲、冰魄寒光剑→冒浣莲、江湖三女侠→冒浣莲 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0024 | already_merged | 七剑下天山→冒辟疆、江湖三女侠→冒辟疆 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0025 | already_merged | 七剑下天山→凌未风、冰魄寒光剑→凌未风、江湖三女侠→凌未风 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0026 | already_merged | 七剑下天山→刘郁芳、江湖三女侠→刘郁芳 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0027 | already_merged | 七剑下天山→卓一航、塞外奇侠传→卓一航 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0028 | org_association_only | 江湖三女侠→吏部、白发魔女传→吏部 | 组织跨书=关联（D07 §4.6）：surface 恒定无归并操作，档案按时代切面 |
| N6-0030 | already_merged | 七剑下天山→吴三桂、江湖三女侠→吴三桂 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0031 | already_merged | 七剑下天山→吴梅村、江湖三女侠→吴梅村 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0032 | already_merged | 七剑下天山→周青、江湖三女侠→周青 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0033 | already_merged | 七剑下天山→哈玛雅、塞外奇侠传→哈玛雅、白发魔女传→哈玛雅 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0034 | already_merged | 七剑下天山→哈玛雅、江湖三女侠→飞红巾 | registry 同一实体已覆盖各书 canonical（映射分歧仅为书内层投影） |
| N6-0036 | already_merged | 七剑下天山→唐努、塞外奇侠传→唐努、白发魔女传→唐努 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0037 | already_merged | 七剑下天山→唐家、冰魄寒光剑→唐家、江湖三女侠→唐家、白发魔女传→唐家 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0040 | already_merged | 七剑下天山→喀达尔族、白发魔女传→喀达尔族 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0041 | already_merged | 七剑下天山→塔山族、塞外奇侠传→塔山族 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0042 | already_merged | 七剑下天山→多尔衮、塞外奇侠传→多尔衮 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0043 | already_merged | 七剑下天山→多铎、塞外奇侠传→多铎 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0044 | already_merged | 七剑下天山→大军、江湖三女侠→大军 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0045 | already_merged | 七剑下天山→天山、江湖三女侠→天山 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0046 | org_association_only | 冰魄寒光剑→天山七剑、江湖三女侠→天山七剑 | 组织跨书=关联（D07 §4.6）：surface 恒定无归并操作，档案按时代切面 |
| N6-0047 | already_merged | 七剑下天山→天山剑法、塞外奇侠传→天山剑法、江湖三女侠→天山剑法 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0048 | already_merged | 七剑下天山→天山剑派、江湖三女侠→天山剑派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0049 | already_merged | 七剑下天山→天山派、冰魄寒光剑→天山派、江湖三女侠→天山派、白发魔女传→天山派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0050 | already_merged | 塞外奇侠传→天龙上人、白发魔女传→天龙上人 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0051 | already_merged | 七剑下天山→天龙派、塞外奇侠传→天龙派、白发魔女传→天龙派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0052 | already_merged | 七剑下天山→天龙禅师、塞外奇侠传→天龙禅师 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0053 | org_association_only | 江湖三女侠→太极派、白发魔女传→太极派 | 组织跨书=关联（D07 §4.6）：surface 恒定无归并操作，档案按时代切面 |
| N6-0054 | already_merged | 七剑下天山→孟家、白发魔女传→孟家 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0055 | already_merged | 七剑下天山→孟禄、塞外奇侠传→孟禄 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0056 | org_association_only | 冰魄寒光剑→密宗、白发魔女传→密宗 | 组织跨书=关联（D07 §4.6）：surface 恒定无归并操作，档案按时代切面 |
| N6-0057 | already_merged | 七剑下天山→少林、冰魄寒光剑→少林、江湖三女侠→少林、白发魔女传→少林 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0058 | already_merged | 七剑下天山→少林派、冰魄寒光剑→少林派、江湖三女侠→少林派、白发魔女传→少林派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0059 | already_merged | 七剑下天山→尚云亭、江湖三女侠→尚云亭 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0061 | already_merged | 七剑下天山→岳武穆、江湖三女侠→岳武穆 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0062 | already_merged | 七剑下天山→峨嵋派、江湖三女侠→峨嵋派、白发魔女传→峨嵋派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0063 | already_merged | 江湖三女侠→嵩阳派、白发魔女传→嵩阳派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0064 | org_association_only | 江湖三女侠→帮会、白发魔女传→帮会 | 组织跨书=关联（D07 §4.6）：surface 恒定无归并操作，档案按时代切面 |
| N6-0066 | already_merged | 七剑下天山→张华昭、江湖三女侠→张华昭 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0067 | already_merged | 七剑下天山→张献忠、白发魔女传→张献忠 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0068 | already_merged | 七剑下天山→御林军、冰魄寒光剑→御林军、江湖三女侠→御林军 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0069 | already_merged | 七剑下天山→文殊菩萨、冰魄寒光剑→文殊菩萨 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0071 | already_merged | 七剑下天山→无住禅师、江湖三女侠→无住禅师 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0072 | already_merged | 七剑下天山→无极派、江湖三女侠→无极派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0073 | already_merged | 七剑下天山→易兰珠、冰魄寒光剑→易兰珠、江湖三女侠→易兰珠 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0074 | already_merged | 七剑下天山→曼铃娜、塞外奇侠传→曼铃娜 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0075 | already_merged | 七剑下天山→朱由检、江湖三女侠→朱由检、白发魔女传→朱由检 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0076 | already_merged | 七剑下天山→朱翊钧、白发魔女传→朱翊钧 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0078 | already_merged | 七剑下天山→李思永、江湖三女侠→李思永 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0079 | already_merged | 七剑下天山→李自成、江湖三女侠→李自成、白发魔女传→李自成 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0080 | already_merged | 七剑下天山→李锦、塞外奇侠传→李锦 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0081 | already_merged | 七剑下天山→杨云骢、塞外奇侠传→杨云骢、白发魔女传→杨云骢 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0082 | already_merged | 七剑下天山→杨云骢、塞外奇侠传→杨云骢、江湖三女侠→杨仲英 | registry 同一实体已覆盖各书 canonical（映射分歧仅为书内层投影） |
| N6-0084 | already_merged | 七剑下天山→柳西岩、塞外奇侠传→柳西岩 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0085 | already_merged | 七剑下天山→桂仲明、冰魄寒光剑→桂仲明、江湖三女侠→桂仲明 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0086 | already_merged | 七剑下天山→桑乾、白发魔女传→桑乾 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0087 | already_merged | 七剑下天山→桑仁、白发魔女传→桑仁 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0088 | already_merged | 七剑下天山→桑弧、白发魔女传→桑弧 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0089 | already_merged | 七剑下天山→楚昭南、塞外奇侠传→楚昭南、江湖三女侠→楚昭南、白发魔女传→楚昭南 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0090 | already_merged | 七剑下天山→武元英、江湖三女侠→武元英 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0091 | already_merged | 七剑下天山→武当派、冰魄寒光剑→武当派、塞外奇侠传→武当派、江湖三女侠→武当派、白发魔女传→武当派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0092 | already_merged | 七剑下天山→武成化、江湖三女侠→武成化 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0093 | already_merged | 七剑下天山→武琼瑶、冰魄寒光剑→武琼瑶、江湖三女侠→武琼瑶 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0095 | already_merged | 七剑下天山→洪承畴、江湖三女侠→洪承畴、白发魔女传→洪承畴 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0096 | already_merged | 七剑下天山→清军、塞外奇侠传→清军、江湖三女侠→清军 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0097 | already_merged | 七剑下天山→清宫、江湖三女侠→清宫 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0098 | already_merged | 七剑下天山→满清、冰魄寒光剑→满清、塞外奇侠传→满清、江湖三女侠→满清、白发魔女传→满清 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0099 | already_merged | 七剑下天山→熊廷弼、白发魔女传→熊廷弼 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0100 | already_merged | 七剑下天山→爱新觉罗氏、冰魄寒光剑→爱新觉罗氏、江湖三女侠→爱新觉罗氏 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0101 | already_merged | 七剑下天山→玄通、白发魔女传→玄通 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0103 | already_merged | 七剑下天山→班禅、冰魄寒光剑→班禅 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0104 | already_merged | 七剑下天山→石振飞、江湖三女侠→石振飞 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0105 | already_merged | 七剑下天山→禁卫军、江湖三女侠→禁卫军 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0106 | already_merged | 七剑下天山→福临、江湖三女侠→福临 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0107 | already_merged | 塞外奇侠传→红云道人、白发魔女传→红云道人 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0108 | org_association_only | 冰魄寒光剑→红教、江湖三女侠→红教 | 组织跨书=关联（D07 §4.6）：surface 恒定无归并操作，档案按时代切面 |
| N6-0109 | already_merged | 七剑下天山→纳兰容若、江湖三女侠→纳兰容若 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0110 | already_merged | 七剑下天山→纳兰明慧、塞外奇侠传→纳兰明慧 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0111 | already_merged | 七剑下天山→纳兰明珠、江湖三女侠→李明珠 | registry 同一实体已覆盖各书 canonical（映射分歧仅为书内层投影） |
| N6-0112 | already_merged | 七剑下天山→纳兰秀吉、塞外奇侠传→纳兰秀吉 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0113 | already_merged | 七剑下天山→练霓裳、塞外奇侠传→练霓裳、江湖三女侠→练霓裳、白发魔女传→练霓裳 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0114 | already_merged | 七剑下天山→终南派、江湖三女侠→终南派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0115 | already_merged | 塞外奇侠传→罗铁臂、白发魔女传→罗铁臂 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0117 | already_merged | 七剑下天山→董小宛、江湖三女侠→董小宛 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0118 | already_merged | 七剑下天山→西藏天龙派、白发魔女传→西藏天龙派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0119 | already_merged | 七剑下天山→辛弃疾、江湖三女侠→辛弃疾 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0120 | already_merged | 七剑下天山→辛龙子、塞外奇侠传→辛龙子 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0121 | already_merged | 七剑下天山→辛龙子、塞外奇侠传→辛龙子、白发魔女传→辛龙子 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0123 | already_merged | 七剑下天山→达摩禅师、冰魄寒光剑→达摩禅师、江湖三女侠→达摩禅师 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0124 | already_merged | 七剑下天山→达赖活佛、冰魄寒光剑→达赖活佛 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0125 | already_merged | 七剑下天山→邱东洛、塞外奇侠传→邱东洛 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0126 | already_merged | 七剑下天山→郝飞凤、江湖三女侠→郝飞凤 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0127 | already_merged | 七剑下天山→释迦牟尼、冰魄寒光剑→释迦牟尼 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0128 | already_merged | 七剑下天山→铁扇帮、江湖三女侠→铁扇帮 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0129 | already_merged | 七剑下天山→镖局、江湖三女侠→镖局、白发魔女传→镖局 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0130 | already_merged | 七剑下天山→长白山派、塞外奇侠传→长白山派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0131 | already_merged | 七剑下天山→阿盖、塞外奇侠传→阿盖 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0132 | already_merged | 七剑下天山→陆家、江湖三女侠→陆家 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0133 | already_merged | 江湖三女侠→雪山派、白发魔女传→雪山派 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0134 | already_merged | 七剑下天山→韩志邦、江湖三女侠→韩重山 | registry 同一实体已覆盖各书 canonical（映射分歧仅为书内层投影） |
| N6-0135 | already_merged | 七剑下天山→马帮、塞外奇侠传→马帮 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0136 | already_merged | 七剑下天山→马方、江湖三女侠→马昆 | registry 同一实体已覆盖各书 canonical（映射分歧仅为书内层投影） |
| N6-0137 | already_merged | 七剑下天山→魏忠贤、塞外奇侠传→魏忠贤、白发魔女传→魏忠贤 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0138 | already_merged | 七剑下天山→鲁王、塞外奇侠传→鲁王 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0139 | already_merged | 七剑下天山→麦盖提、塞外奇侠传→麦盖提 | registry 同一实体已覆盖该 canonical（无需归并） |
| N6-0140 | already_merged | 七剑下天山→齐真君、塞外奇侠传→齐真君 | registry 同一实体已覆盖该 canonical（无需归并） |

## 五、逐候选证据卡（actionable，前 80 条；全量见 merge_candidates.json）

### N6-0007 · E3 · ok · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：冰魄寒光剑→桂华生（@，1193 次）；江湖三女侠→桂华生（@，51 次）
- 系列层建议：{"display_canonical": "桂华生", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：同名「桂华生」跨书 + 同系列接力/种子（冰魄寒光剑、江湖三女侠）→ 提案，全量双人复核
- 证据 [E3/series_relay] 同系列（天山系列（清代主脉））+ 接力边/种子；同名「桂华生」跨书 loc=—
- 复核状态：pending（全量双人）

### N6-0009 · E3 · ok · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：塞外奇侠传→焦化（@，15 次）；白发魔女传→焦化（@，6 次）
- 系列层建议：{"display_canonical": "焦化", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：同名「焦化」跨书 + 同系列接力/种子（塞外奇侠传、白发魔女传）→ 提案，全量双人复核
- 证据 [E3/series_relay] 同系列（天山系列（清代主脉））+ 接力边/种子；同名「焦化」跨书 loc=—
- 复核状态：pending（全量双人）

### N6-0010 · E3 · ok · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：塞外奇侠传→甘天立（@，11 次）；白发魔女传→甘天立（@，8 次）
- 系列层建议：{"display_canonical": "甘天立", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：同名「甘天立」跨书 + 同系列接力/种子（塞外奇侠传、白发魔女传）→ 提案，全量双人复核
- 证据 [E3/series_relay] 同系列（天山系列（清代主脉））+ 接力边/种子；同名「甘天立」跨书 loc=—
- 复核状态：pending（全量双人）

### N6-0013 · E3 · ok · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：塞外奇侠传→青蓑道人（@，2 次）；白发魔女传→青蓑道人（@，20 次）
- 系列层建议：{"display_canonical": "青蓑道人", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：同名「青蓑道人」跨书 + 同系列接力/种子（塞外奇侠传、白发魔女传）→ 提案，全量双人复核
- 证据 [E3/series_relay] 同系列（天山系列（清代主脉））+ 接力边/种子；同名「青蓑道人」跨书 loc=—
- 复核状态：pending（全量双人）

### N6-0029 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：冰魄寒光剑→吕四娘（@，3 次）；江湖三女侠→吕四娘（@，1840 次）
- 系列层建议：{"display_canonical": "吕四娘", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「吕四娘」（冰魄寒光剑、江湖三女侠）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「吕四娘」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0035 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：冰魄寒光剑→唐三藏（@，1 次）；白发魔女传→唐三藏（@，3 次）
- 系列层建议：{"display_canonical": "唐三藏", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「唐三藏」（冰魄寒光剑、白发魔女传）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「唐三藏」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0038 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：冰魄寒光剑→唐晓澜（@，2 次）；江湖三女侠→唐晓澜（@，2184 次）
- 系列层建议：{"display_canonical": "唐晓澜", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「唐晓澜」（冰魄寒光剑、江湖三女侠）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「唐晓澜」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0039 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：冰魄寒光剑→唐赛花（@，8 次）；江湖三女侠→唐赛花（@，56 次）
- 系列层建议：{"display_canonical": "唐赛花", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「唐赛花」（冰魄寒光剑、江湖三女侠）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「唐赛花」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0060 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：家族（&）；系列：天山系列（清代主脉）
- 成员（书内层）：江湖三女侠→岳家（&，1 次）；白发魔女传→岳家（&，2 次）
- 系列层建议：{"display_canonical": "岳家", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「岳家」（江湖三女侠、白发魔女传）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「岳家」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0065 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：冰魄寒光剑→年羹尧（@，29 次）；江湖三女侠→年羹尧（@，1056 次）
- 系列层建议：{"display_canonical": "年羹尧", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「年羹尧」（冰魄寒光剑、江湖三女侠）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「年羹尧」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0070 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：冰魄寒光剑→方今明（@，52 次）；江湖三女侠→方今明（@，135 次）
- 系列层建议：{"display_canonical": "方今明", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「方今明」（冰魄寒光剑、江湖三女侠）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「方今明」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0077 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：家族（&）；系列：天山系列（清代主脉）
- 成员（书内层）：江湖三女侠→李家（&，1 次）；白发魔女传→李家（&，3 次）
- 系列层建议：{"display_canonical": "李家", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「李家」（江湖三女侠、白发魔女传）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「李家」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0083 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：家族（&）；系列：天山系列（清代主脉）
- 成员（书内层）：江湖三女侠→杨家（&，44 次）；白发魔女传→杨家（&，18 次）
- 系列层建议：{"display_canonical": "杨家", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「杨家」（江湖三女侠、白发魔女传）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「杨家」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0094 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：江湖三女侠→汉武帝（@，1 次）；白发魔女传→汉武帝（@，1 次）
- 系列层建议：{"display_canonical": "汉武帝", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「汉武帝」（江湖三女侠、白发魔女传）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「汉武帝」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0102 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：冰魄寒光剑→王敖（@，1 次）；江湖三女侠→王敖（@，50 次）
- 系列层建议：{"display_canonical": "王敖", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「王敖」（冰魄寒光剑、江湖三女侠）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「王敖」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0116 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：冰魄寒光剑→苏东坡（@，1 次）；江湖三女侠→苏东坡（@，1 次）
- 系列层建议：{"display_canonical": "苏东坡", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「苏东坡」（冰魄寒光剑、江湖三女侠）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「苏东坡」跨 2 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

### N6-0122 · E4 · todo · proposal

- 来源：cross_book_same_canonical；类型：人物（@）；系列：天山系列（清代主脉）
- 成员（书内层）：冰魄寒光剑→达摩祖师（@，4 次）；江湖三女侠→达摩祖师（@，4 次）；白发魔女传→达摩祖师（@，4 次）
- 系列层建议：{"display_canonical": "达摩祖师", "entity_id": null, "rule": "跨书总频最高名（D07 §4.3；实体 ID 待双人复核后由登记层颁发）"}
- 理由：仅同名「达摩祖师」（冰魄寒光剑、江湖三女侠、白发魔女传）→ 候选池，无证据不归并（E4）
- 证据 [E4/same_surface] 仅同名 canonical「达摩祖师」跨 3 书，无正文/种子锚点 loc=—
- 复核状态：pending（不进归并（仅候选池））

## 六、bare B0-B8 转投与人工复核（D07 §7.2）

| probe | 转投池 | 条数 | 说明 |
|---|---|---|---|
| 武林天骄 | q4_alias_pool | 1575 | 人物绰号撞书名（檀羽冲） |
| 冰魄寒光剑 | artifact_layer | 171 | 兵器撞书名 |
| 散花女侠 | q4_alias_pool | 15 | 人物绰号撞书名（于承珠） |
| 江湖三女侠 | group_layer | 3 | 群体称号撞书名 |
| 幻剑灵旗 | artifact_layer | 2 | 信物撞书名 |
| 武林三绝 | phrase_layer | 2 | 短语称名（三法并称） |

B8 转人工复核 0 条（明细见 merge_candidates.json `bare_dispatch.review_items`）；其余 bare 边按 B0-B8 自动归因。

## 七、回写与撤销（D07 §8.1/§8.3）

1. 顺序：book_aliases → series_identities → 派生视图重建（先书内后系列）；
2. 归并/撤销均须留 review 记录；entity_id 封存不删不复用；
3. 本工作台**不自动回写 registry**：approved 后的回写由登记层工具执行并留痕。

