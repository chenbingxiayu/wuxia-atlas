# 停用泛称表 · 人工源（泛称/描写性代称黑名单）
# 用途：tag 脚本召回过滤 + lint 误标告警（01g 负规则一/二、04f 不标清单、qwen 实验实测集体泛称问题）
# 列：surface | type | tier | status | conf | evidence | note
# tier=review：只作告警与召回过滤，无批量语义；新增条目按"3+ 案例"门槛增补
| surface | type | tier | status | conf | evidence | note |
| - | - | - | - | - | - | - |
| 那汉子 | 泛称 | review | 已核准 | ok |  | 01g 负规则一示例 |
| 老者 | 泛称 | review | 已核准 | ok |  | 01g 负规则一示例 |
| 那姑娘 | 泛称 | review | 已核准 | ok |  | 01g 负规则一示例 |
| 蒙面人 | 泛称 | review | 已核准 | ok |  | 01g 负规则一示例 |
| 众人 | 泛称 | review | 已核准 | ok |  | 04f 不标清单 |
| 群盗 | 泛称 | review | 已核准 | ok |  | 04f 不标清单 |
| 众镖师 | 泛称 | review | 已核准 | ok |  | 01g 负规则一/实验实测误标 |
| 白马少年 | 泛称 | review | 已核准 | ok |  | qwen 实验 v1 不标清单 |
| 虬髯汉子 | 泛称 | review | 已核准 | ok |  | qwen 实验 v1 不标清单 |
| 矮胖老头 | 泛称 | review | 已核准 | ok |  | qwen 实验 v1 不标清单 |
| 老镖头 | 泛称 | review | 已核准 | ok |  | qwen 实验 v1 不标清单 |
| 女魔头 | 泛称 | review | 已核准 | ok |  | 评价代称（01g：贬称须别名证据才标） |
| 红面老人 | 泛称 | review | 已核准 | ok |  | qwen 实验 v1 不标清单 |
| 手下 | 泛称 | review | 已核准 | ok |  | 04f 通名与泛量词 |
| 弟子们 | 泛称 | review | 已核准 | ok |  | 泛量复数 |
| 群豪 | 泛称 | review | 待审 | weak |  | doc05 模式词表（群豪/众弟子族），试点复核 |
| 众弟子 | 泛称 | review | 待审 | weak |  | doc05 模式词表 |
| 各派掌门 | 泛称 | review | 待审 | weak |  | doc05 模式词表（复数集合，单数掌门归职衔） |
