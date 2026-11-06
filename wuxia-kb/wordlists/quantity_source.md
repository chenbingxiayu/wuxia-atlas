# 数量词表 · 人工源初版（量词 + 数量模式词；tag_quantity_entities 外置词表样板）
# 用途：〖$〗数量实体候选召回——单字 surface = 量词（进脚本"数字+量词"正则的量词集合），
#       多字 surface = 数量模式词（经 masker.find_candidates 整串最长匹配）
# 列：surface | type | tier | status | conf | evidence | note
# 全表 review 档：量词歧义严重（"名"计人/"成"计比例/"骑"计人马），逐条语境判定，禁批量
| surface | type | tier | status | conf | evidence | note |
| - | - | - | - | - | - | - |
| 招 | 量词 | review | 待审 | weak |  | 武功计次（一招/这招）；进数字+量词正则 |
| 式 | 量词 | review | 待审 | weak |  | 招式计次（这一式）；与 ☆ 武功名易混，语境审 |
| 两 | 量词 | review | 待审 | weak |  | 银两计价（三两银子）；兼作数词，语境审 |
| 里 | 量词 | review | 待审 | weak |  | 路程（三百里）；进数字+量词正则 |
| 年 | 量词 | review | 待审 | weak |  | 年岁/时长（二十年功力）；与 % 时间分工：数量侧重"数值+单位" |
| 斤 | 量词 | review | 待审 | weak |  | 重量（五十斤铁） |
| 丈 | 量词 | review | 待审 | weak |  | 长度/高度（一丈开外） |
| 尺 | 量词 | review | 待审 | weak |  | 长度（三尺青锋） |
| 寸 | 量词 | review | 待审 | weak |  | 长度（七寸） |
| 石 | 量词 | review | 待审 | weak |  | 容量/粮食（一石米） |
| 斛 | 量词 | review | 待审 | weak |  | 容量（十斛） |
| 柄 | 量词 | review | 待审 | weak |  | 兵器计件（两柄短剑）；与 • 器物分工见 01g |
| 骑 | 量词 | review | 待审 | weak |  | 人马计数（五百骑） |
| 名 | 量词 | review | 待审 | weak |  | 计人（三名高手）；高频歧义，语境审 |
| 成 | 量词 | review | 待审 | weak |  | 比例（十成把握/三成内力） |
| 折 | 量词 | review | 待审 | weak |  | 比例/折扣（七折） |
| 匹 | 量词 | review | 待审 | weak |  | 马匹计件（八匹马） |
| 张 | 量词 | review | 待审 | weak |  | 平面物（一张告示/三张弓） |
| 把 | 量词 | review | 待审 | weak |  | 有柄物（一把戒刀） |
| 枚 | 量词 | review | 待审 | weak |  | 小件（三枚暗器） |
| 锭 | 量词 | review | 待审 | weak |  | 银锭计件（十锭银子） |
| 担 | 量词 | review | 待审 | weak |  | 挑载计量（百担粮草） |
| 斗 | 量词 | review | 待审 | weak |  | 容量（一斗酒） |
| 贯 | 量词 | review | 待审 | weak |  | 钱串（一千贯） |
| 层 | 量词 | review | 待审 | weak |  | 功力层级（第七层）；与 ^ 内功层级易混，语境审 |
| 重 | 量词 | review | 待审 | weak |  | 功法层级（第一重） |
| 名高手 | 模式 | review | 待审 | weak |  | "N名高手"整串召回；勿拆"高手"入实体层 |
| 十成 | 模式 | review | 待审 | weak |  | 比例惯用语（十成把握） |
| 数十 | 模式 | review | 待审 | weak |  | 模糊数量（数十名） |
| 数百 | 模式 | review | 待审 | weak |  | 模糊数量（数百骑） |
| 数千 | 模式 | review | 待审 | weak |  | 模糊数量（数千教众） |
| 数万 | 模式 | review | 待审 | weak |  | 模糊数量（数万斤） |
| 上百 | 模式 | review | 待审 | weak |  | 模糊数量（上百弟子） |
| 上千 | 模式 | review | 待审 | weak |  | 模糊数量（上千斤） |
| 好几 | 模式 | review | 待审 | weak |  | 模糊数量（好几招） |
| 半数 | 模式 | review | 待审 | weak |  | 比例（折损半数） |
