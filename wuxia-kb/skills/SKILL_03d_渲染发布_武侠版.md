---
name: skill-03d-wuxia
title: 渲染与发布（武侠版）——从标注语料到阅读器渲染与站点发布契约
description: 武侠章回标注语料的渲染与发布规范：三层输入契约（令牌流/结构 PN/登记层）、15 实体+6 动词域的配色与渲染语义、围栏渲染规则、AST→HTML 转换契约（data 属性/类名/PN 锚点）、站点数据导出（EX-1..EX-8）与本地阅读器发布边界、版本化与回滚。当需要把 tagged/struct 产物渲染成阅读器页面、生成站点 data JSON、或裁定"什么能公开发布/什么只能本地用"时使用。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 03d 武侠版：渲染与发布 — 从标注语料到可发布形态

> **上游声明**：本文从 shiji-kb `SKILL_03d_渲染发布` 移植重造，移植依据见 `docs/05-管线技能与脚本逐项改造分析.md` §2.3（判定 ✅ 90:10：换脚本名/多书目录即可；shiji `render_shiji_html` 渲染器 46KB 深度特化**不移植**，武侠渲染自建）与 `docs/17-技能脚本改造实现图与拓扑排序.md`（S-03d 属 P2 轻档；P5 的 S-09 组消费本文渲染契约）。
> **上游规范（已定版，本文引用不重定义）**：`SKILL_01g_标注符号集合原则.md`（D01）§二 三大符号集合（15 实体+6 动词+1 修辞）、§9.8 网站功能覆盖、§9.9 SKU 最低字段、§9.10 公开发布边界；`SKILL_02a_02b_章回结构与韵文处理.md`（D04）§四 围栏类型与渲染语义、§9.2 正文分母、§3 PN 锚点。
> **现行发布架构（2026-11-05 已决策）**：E 组"冻结旧件 + 薄导出适配层"（方案 C，见 `docs/51-E组合流决策与导出适配层方案.md`）——父仓旧 `build_*` 脚本只读冻结；新管线经 EX-1..EX-8 导出器把数据写入 `site/data/*.json`（14 份契约，见 docs/51 §五），Astro 页面零改动；**新管线不自建第二套站点，也不复活旧渲染器**。
> **核心原则**：**标注层只管语义，渲染层只管呈现；发布层只管边界。** 三层不得互相污染：渲染不得改标注、导出不得伪造字段、发布不得越过 01g §9.10。

---

## 一、定位与边界

### 1.1 工序位置

```text
③a 标注（SKILL_03a）→ ③b 消歧（SKILL_03b）→ 结构（02ab: PN/围栏）
        ↓
⑤ 登记层（registry/entities.json + concordance + SKU）
        ↓
③d 渲染发布（本文）──┬─→ 本地阅读器（AST→HTML，仅本地）
                     └─→ 站点数据导出（EX-1..EX-8）→ Astro 构建 → site/dist
```

- 前置：`pipeline_wuxia.py <书> check` 五门 lint 全 0（结构/符号完成门）；`registry/`、`registry/concordance/` 就绪。
- 后继：S-09 组（09a 语法高亮渲染器、09b/09c/09e/09m 应用形态）消费本文的 AST/HTML 契约；W 组页型模板消费本文的发布边界。

### 1.2 本文做什么

1. **渲染契约**：定义从 tagged/struct 到阅读器 AST 的节点模型（令牌节点/PN 节点/围栏节点/普通文本）；
2. **配色与符号语义**：15 实体 + 6 动词域 + 修辞层的渲染分类（颜色分组/图例/tooltip），引 01g §二 不重定符号；
3. **围栏渲染**：10 类围栏（7 正式 + 3 观察）的渲染语义（居中/灰斜体/信笺/口诀样式等），引 02ab §4.1；
4. **AST→HTML 转换契约**：`data-*` 属性、CSS 类名、PN 锚点 id、可访问性、幂等与消毒规则（§五，本文最硬交付物）；
5. **站点数据导出**：EX-1..EX-8 的字段来源、`meta.field_gaps` 纪律、幂等与备份（引 docs/51 §五/§七）；
6. **发布边界**：01g §9.10 允许/禁止出口的工程化执行（脱敏、版权、本地/公开分层）。

### 1.3 本文不做什么（越界即错）

| 不做 | 归属 |
|---|---|
| 重新定义符号/类型码 | SKILL_01g §二（唯一来源 `scripts/symbols.py`） |
| 生成/修改 PN、围栏标记 | SKILL_02a_02b + `generate_pn_wuxia.py` |
| 重写标注语义、改管道 | SKILL_03a / SKILL_03b |
| 站点页面设计与样式实现 | `../site/`（Astro，冻结期只读+data 驱动） |
| 旧 `build_*.py` 渲染器改造 | 已冻结（docs/51 §四），由 EX 导出层替代 |
| SKU 卡内容生成 | SKILL_SKU卡片_武侠版 + N10（待建） |

### 1.4 现有资产与冻结边界

| 资产 | 状态 | 本文关系 |
|---|---|---|
| `tagged/<书>/NNN.tagged.md`、`NNN.struct.md/json` | 5 书 131 回已 accepted | 渲染输入（只读） |
| `registry/entities.json`、`registry/concordance/` | 454 条 / 5 书 | 发布数据源 |
| `export_site_*.py`（`scripts/`，EX-1..EX-8） | 阶段 1 已完成 | 本文引用其契约 |
| `../site/data/*.json`（14 份） | 冻结基线 2026-11-02，桥接期由 EX 覆盖 | 发布目标契约 |
| `../site/src/pages/**`（38 页） | 冻结期只读 | 页面零改动验收 |
| 父仓 `Wuxiaxiaoshuo/scripts/build_*.py` 44 件 | **只读冻结** | 禁止调用/改 bug（docs/51 §4.1） |

---

## 二、快速开始（五步发布流）

````text
Step 1 完成门   pipeline_wuxia.py <书> check（五门 lint 全 0）
Step 2 渲染测试  从 tagged 抽样生成 AST + HTML（本地阅读器预览；脚手架脚本待建）
Step 3 导出数据  export_site_all.py（默认 dry-run/staging；--apply 前自动备份 site/data）
Step 4 站点构建  ../site npm run build（验 38 页 + 数据契约无报错）
Step 5 验收发布  hard_gap=0、页面数、字段缺口表、抽检可回溯、01g §9.10 发布边界复核
````

```powershell
cd C:\Users\YANG Ruosong\Documents\workspace\Wuxiaxiaoshuo\wuxia-kb
$env:PYTHONIOENCODING='utf-8'

# Step 1 完成门（任一 FAIL 即停）
python -X utf8 scripts/pipeline_wuxia.py 江湖三女侠 check

# Step 3 导出层（默认 dry-run，产物先落 logs/export/staging/；--apply 前先备份 site/data）
python -X utf8 scripts/export_site_all.py
python -X utf8 scripts/export_site_all.py --apply

# Step 4 站点构建（父仓 Astro）
cd ..\site; npm run build; cd ..\wuxia-kb

# 回滚：site/data 备份在 backup/site_data_20261105/，直接恢复 + 重新构建
```

**成功标准**（本工序验收门）：① `export_site_all.py --apply` 产出 8+ 数据文件 `hard_gap=0`；② `site` 构建退出码 0 且页面数与导出记录一致（基线 1480–1508 页随数据收敛浮动）；③ `meta.field_gaps` 覆盖全部缺失字段（无静默丢弃）；④ 抽检 10% 可回溯到 tagged/registry 定位；⑤ 01g §9.10 禁止出口零命中；⑥ 渲染器 AST 对抽样回幂等（同输入两次渲染字节同）。

---

## 三、输入契约：三层语料模型

### 3.1 三层与节点来源

| 层 | 载体 | 渲染用途 |
|---|---|---|
| 令牌层 | `〖@显示串|规范名〗`、`⟦◈动词⟧`、`〘※修辞〙` | 实体高亮/配色/点击跳转/管道 tooltip |
| 结构层 | `# [0] 第N回 回目`、`[n]` PN 段号、`::: 类型` 围栏 | 阅读器目录/段锚/围栏样式 |
| 登记层 | `registry/entities.json`、`registry/concordance/<书>.json`、SKU 卡 | 档案页/搜索/跨书跳转 |

### 3.2 渲染 AST 节点模型（v0.1 约定）

```json
{
  "type": "chapter",
  "book": "江湖三女侠",
  "chapter": 12,
  "title": "第12回 …",
  "blocks": [
    {"type": "fence", "fence": "词", "pn": "jianghu#pn-r12.1",
     "lines": [{"type": "line", "spans": [{"type": "text", "text": "…"}]}]},
    {"type": "para", "pn": "jianghu#pn-r12.2",
     "spans": [
       {"type": "entity", "code": "@", "display": "吕四娘", "canonical": "吕四娘",
        "token_id": "t-0001", "pipe": false},
       {"type": "text", "text": "提剑"},
       {"type": "verb", "code": "⊞", "display": "刺", "group": "战斗交锋"},
       {"type": "rhetoric", "kind": "※", "display": "…"}
     ]}
  ]
}
```

- 节点 `type` 枚举：`chapter/fence/para/heading/line/entity/verb/rhetoric/text`；v0.1 只允许这些，扩展走版本化（§六.3）。
- `pn` 为 02ab 机锚 `{作品ID}#pn-r{N}.{X}`；围栏整体一 PN（02ab §3.3）。
- `entity.canonical` 取登记层规范名（03b 口径），`display` 必须等于原文连续区间（03a 输出契约）。
- AST 生成器**只读** tagged/struct，不改任何语料。

### 3.3 结构侧约束（引 02ab）

- 回目行 `# [0]` 不产生实体/动词高亮（02ab §2.2）；
- 围栏内渲染按 02ab §4.1 的"渲染语义"列：词/诗/歌/对联/回末对居中硬换行；回末弱化灰斜体；书信信笺样式；口诀口诀样式；说书旁白样式；
- 回末围栏内零标注（02ab §4.4），渲染器不得为"空围栏"补造子节点。

---

## 四、渲染规则：配色、图例与交互

### 4.1 15 实体 + 6 动词的渲染分类（引 01g §二，颜色名为建议值）

| 类 | 符号 | 渲染重点 | 建议颜色族 |
|---|---|---|---|
| 人物 | `@` | 主高亮，可点击→档案 | 暖红 |
| 人物群组 | `◎` | 群组样式（虚线下划线） | 深红 |
| 地点 | `=` | 可点击→地图/地点页 | 绿 |
| 组织 | `◆` | 组织徽标色 | 蓝 |
| 家族 | `&` | 谱系淡色 | 紫 |
| 族群 | `~` | 民族色 | 青 |
| 职衔 | `;` | 不加粗，仅下划 | 灰蓝 |
| 身份 | `#` | 处境标签色 | 灰 |
| 武功 | `☆` | 技艺样式（斜体高亮） | 橙 |
| 器物 | `•` | 器物样式 | 棕 |
| 生物 | `+` | 生物样式 | 草绿 |
| 文书 | `{` | 书卷样式 | 墨绿 |
| 专门概念 | `^` | 术语样式（点线） | 青灰 |
| 时间 | `%` | 时间标签（浅底） | 黄褐 |
| 数量 | `$` | 数值强调 | 沙色 |
| 动词 6 域 | `⊞⊠⊡⊟▣■` | 动作词淡底/下点；不参与实体图例 | 按域分色（弱化） |
| 修辞 | `〘※〙` | 波浪下划线（可关闭） | 中性 |

> 色值须同时满足：色盲可区分（明度差≥25%）、与站点主题相容、15 类两两可分（01g §三 Disjoint 原则的视觉延伸；具体色板由 S-09a 专项冻结，本文只定分组与语义）。

### 4.2 交互契约

| 交互 | 行为 | 数据来源 |
|---|---|---|
| 实体点击 | 打开该实体档案/搜索面板（本地阅读器本地跳转；站点跳 `/entities/<id>` 或搜索） | registry id/canonical/aliases |
| 管道 tooltip | 显示"显示串→规范名"+ alias 来源 | token 管道 + registry status |
| PN 悬浮 | 显示机锚 `{作品ID}#pn-r{N}.{X}`，可复制 | struct PN |
| 跨书链接 | 同一系列实体跨书跳转（D07 双层 canonical） | series 成员（v1.0 两表；v0.1 用 registry aliases + active 书） |
| 图例开关 | 15 类实体/6 动词/修辞层可分别开关 | AST 静态配置 |

### 4.3 正文密度与阅读体验

- 配色不得改变字号/行距（避免"标注影响阅读"）；
- 动词层默认弱化（可关）；修辞层默认关（01g 修辞层后置启用）；
- 围栏块整体样式化，围栏标签渲染为 tooltip 而非标题（02ab §4.1 继承设计决策）。

---

## 五、AST→HTML 转换契约（本文最硬交付物）

### 5.1 输出 HTML 骨架

```html
<article class="wx-chapter" data-book="江湖三女侠" data-chapter="12" data-work-id="jianghu">
  <h2 class="wx-chapter-title" id="jianghu-r12">第12回 　…</h2>
  <div class="wx-fence wx-fence-ci" data-fence="词" id="jianghu-r12-1" data-pn="jianghu#pn-r12.1">
    <div class="wx-line">…</div>
  </div>
  <p class="wx-para" id="jianghu-r12-2" data-pn="jianghu#pn-r12.2">
    <span class="wx-ent wx-ent-at" data-etype="@" data-token-id="t-0001"
          data-canonical="吕四娘">吕四娘</span>提剑
    <span class="wx-verb wx-verb-fight" data-vtype="⊞" data-token-id="t-0002">刺</span>出。
  </p>
</article>
```

### 5.2 契约条款（可测试）

| # | 条款 | 验收方式 |
|---|---|---|
| H-1 | 每个 PN 块输出唯一 `id`（=机锚可读形式）与 `data-pn`（机锚原文）；id 全书唯一 | 正则扫描 + 唯一性断言 |
| H-2 | 实体节点 `class="wx-ent wx-ent-<code>"`，`data-etype`=15 类码之一，`data-token-id` 全书唯一 | 类名/属性断言 |
| H-3 | 动词节点 `class="wx-verb wx-verb-<domain>"`，`data-vtype`∈6 域；不得复用实体类 | 断言 |
| H-4 | 显示文本（textContent）与剥标原文逐字一致；令牌只增加包裹元素，不改字符 | 渲染后 `textContent == strip(tagged)` 逐段断言 |
| H-5 | `data-canonical` 仅当管道存在或登记层可唯一回溯时输出；歧义/未登记不输出（03b：不猜） | 与 registry 对照 |
| H-6 | 围栏块 `class="wx-fence wx-fence-<roman>"`（ci/shi/ge/duilian/huimodui/huimo/shuxin/gaoshi/koujue/shuoshu），`data-fence`=中文类型名 | 类名映射表 |
| H-7 | 禁止输出原文之外的属性值；禁止内联事件处理器（`onclick` 等） | 安全扫描 |
| H-8 | 输出确定性：同 AST 两次渲染字节相同（时间戳/随机数禁止进入 HTML） | 双跑 diff |
| H-9 | 页面级不输出未审核实体（registry status=pending 不渲染 `data-canonical`/跳转，只保显示串） | status 过滤断言 |
| H-10 | 本地阅读器产物**不得**进入 `site/data` 或公网静态目录（01g §9.10） | 路径审计 |

### 5.3 转换器接口（骨架，待实现）

```text
输入：AST JSON（§3.2）+ 渲染配置（色板/开关/图例版本）
输出：HTML 片段（单章）+ 资源清单（CSS 类名清单/图例数据）
CLI（建议）：render_wuxia.py --book <书> --chapters <范围> --out <dir> [--theme default] [--no-verb] [--json-ast]
纪律：只读 tagged/struct/registry；渲染器不写 registry；产物写 logs/render/ 或站点静态目录（本地）
```

> ⚠️ 本转换器**尚未实现**（v0.1 只定契约），实现属 S-09a/应用层工程；在实现前本文的 H-1~H-10 作为契约冻结，供前端/阅读器开发对照。

### 5.4 站点侧契约（EX 导出层）

- 站点数据契约见 docs/51 §五（14 份 JSON + atlas）；导出器以"字段不缺、类型不破"为底线，缺失字段置 `null`/空数组并写 `meta.field_gaps`；
- 字段来源：`books/chapters` ← config+作品元数据表+struct；`characters/entity-index/dossiers` ← registry+concordance+tagged；`sects/weapons/arts` ← registry+词表+旧考订表（只读）；`graph/matches/ratings/gazetteer/universe/audit` ← 依赖 N5/N7/N8 与 W 组（阶段 2/3）；
- 幂等：每个导出器复跑产出确定性一致（时间戳字段除外）；默认 dry-run，`--apply` 前自动备份 `site/data/`（docs/51 §七）；
- 零旧写入：导出器不改 `tagged/`、`registry/`；不运行父仓旧脚本（docs/51 §七）。

---

## 六、发布边界、版本化与回滚

### 6.1 发布边界（执行 01g §9.10）

| 允许出口 | 本文执行点 |
|---|---|
| 结构化实体属性/关系/统计/不含正文定位/原创分析/数据与方法版本 | EX 导出字段白名单；`meta.version/rule_version` 必填 |
| **禁止**：原文正文、标注正文、可逐步还原正文的连续片段、逐字证据伪图谱、未核实却表述为确定事实 | 导出器字段级脱敏；dossiers/characters 不携带长原文；evidence.snippet ≤120 字且**不发布**（D07 §7.5） |

- **本地阅读器**：可渲染标注正文，但产物仅本地使用、不得上传/打包进公网站点（01g §9.10 + docs/51 §4.1 冻结纪律）；
- **站点**：只发布结构化数据；页面不内联原文段落；
- **原始 snippet/引语**：走版权审查通道，不在本文自动发布范围。

### 6.2 版本化

- 渲染契约版本 `html_contract: v0.1`、色板版本 `theme: v0.1`、图例版本随 01g 符号表版本；
- AST schema 版本 `ast_schema: v0.1`；节点类型增删走 §六.3 变更治理；
- 站点数据：`meta.generated/version/field_gaps` 必填，构建产物可按日期回溯。

### 6.3 变更治理（引 02ab §9.4 三步）

1. **分级**：甲类=纯文档/样式修订（不影响 AST/HTML 契约字段）→ 直接修订；乙类=节点类型、类名、data 属性变化 → 迁移+回归；
2. **回归**：抽样 ≥3 书 30 回渲染 → diff 报告；HTML 契约变化须给旧→新映射（阅读器/前端据此升级）；
3. **冻结窗口**：发布变更说明 + 7 天下游回归窗口（S-09 组/站点确认），窗口后旧版本存档。

### 6.4 回滚

- 站点数据：恢复 `backup/site_data_20261105/` 快照 → 重新构建；
- 渲染契约：按 `html_contract` 版本回退转换器实现；
- 不修改 tagged/registry 是回滚前提（导出/渲染均为只读消费）。

---

## 七、错误模式库（RND 系列，首批 10 条）

| # | 错误 | 实例（示意） | 检测 | 修正 |
|---|---|---|---|---|
| RND-01 | 渲染吞字/改字 | 令牌包裹时丢空格或标点 | `textContent==strip(tagged)` 断言 | 转换器逐段对账 |
| RND-02 | 令牌跨节点拆分 | 一个实体令牌被拆进两个 HTML 元素 | 结构断言：令牌=单元素 | 修复解析器 |
| RND-03 | 类名与类型码不一致 | `wx-ent-at` 但 `data-etype`=◆ | 类名/属性双向校验 | 统一映射表 |
| RND-04 | PN 锚点重复/缺失 | 围栏整体一 PN 未落到块上 | H-1 唯一性扫描 | 汇编期断言 |
| RND-05 | 管道规范名越权展示 | 歧义/未登记项也显示 `data-canonical` | status/唯一性过滤 | 03b 口径 |
| RND-06 | 页面内联原文片段 | dossiers 直接塞长段原文 | 字段白名单 + 长度上限 | 脱敏/改摘要 |
| RND-07 | 导出伪造字段 | 旧站有、新数据无的字段被编造 | `meta.field_gaps` 审查 | 置 null + 记录 |
| RND-08 | 渲染不确定性 | 时间戳/随机 id 进入 HTML | 双跑 diff | 去除 |
| RND-09 | 本地阅读器产物上公网 | 本地 HTML 被拷入 site/public | 发布路径审计 | 隔离目录 |
| RND-10 | 旧件回流 | 调用父仓 `build_*.py` 生成数据 | mtime/import 审计 | 冻结（docs/51） |

---

## 八、检查清单（发布前逐项）

### 执行前
- [ ] `pipeline_wuxia.py <书> check` 五门 lint 全 0；
- [ ] registry/concordance 为最新（与 tagged 同批）；
- [ ] 导出器/渲染器版本与契约版本匹配（`html_contract/ast_schema/theme`）。

### 执行中
- [ ] 默认 dry-run/staging；`--apply` 前备份 `site/data/`；
- [ ] 渲染 H-1~H-10 断言、导出契约字段校验；
- [ ] `meta.field_gaps` 逐项有说明；
- [ ] 抽检 10% 记录可回溯（tagged 回/段/PN）。

### 执行后
- [ ] `site` 构建 exit 0、页面数与记录一致、控制台无契约报错；
- [ ] 01g §9.10 边界零命中（无原文/标注正文/长片段）；
- [ ] 本地阅读器产物未进入发布目录；
- [ ] 变更记录与版本号落盘。

---

## 九、与下游/反思循环挂钩

1. **→ S-09 组**：09a 语法高亮直接消费本文 AST/HTML 契约与配色分组；09b/09c/09e/09m 消费发布形态与版本号；
2. **→ W 组**：W8-W9 页型模板、W10x 页面维护以本文导出契约与发布边界为输入；W 组新 schema 落地后 EX 层退役（docs/51 §六）；
3. **→ META-10 QC**：渲染/导出的字段完整性检查（L3 数据完整性）纳入 QC 层；契约断言可提升为 CI；
4. **→ 反思循环**：RND 错误模式按月汇总，可规则化者沉淀为导出器/渲染器断言（"QC 验证反思成果"闭环）；
5. **→ 数据版本**：每次发布记录 `data_version + rule_version + contract_version`，供问答/统计引用。

---

## 十、FAQ（首批 8 问）

**Q1 为什么不移植 shiji 的 HTML 渲染器？**
它 46KB 且深度绑定史记体裁（本纪/世家/赞文排版）；武侠有围栏 10 类、多书目录、站点已存在（Astro），按 docs/05 判定自建/走站点数据层更省成本。

**Q2 新管线还要不要生成 HTML？**
分两种：本地阅读器需要 AST→HTML（本文契约，实现属 S-09a）；公网站点由 Astro 从 `site/data` 渲染，新管线只导出数据（EX 层），**不生成站点 HTML**。

**Q3 标注正文能发布吗？**
不能。01g §9.10 禁止原文正文/标注正文/可还原正文的连续片段；本地阅读器仅本地使用。

**Q4 站点页面零改动的前提是什么？**
EX 导出器严格对齐 site/data 14 份契约（docs/51 §五）；缺字段置 null 并记 `meta.field_gaps`，不得静默丢弃。

**Q5 颜色/图例由谁定？**
本文定分组与语义（§4.1），具体色板由 S-09a 专项冻结；两处都不得绕过 01g §二 符号表。

**Q6 围栏渲染要显示标签吗？**
按 02ab §4.1：标签渲染为 tooltip，不作页面标题；回末围栏弱化样式。

**Q7 数据导出失败/字段缺失怎么办？**
dry-run 先看 `hard_gap`；缺失字段写 `meta.field_gaps` 并按 docs/51 §七 判定是否阻断（数组元素缺字段必须 0）。

**Q8 旧站数据还能用吗？**
作为桥接基线只读（docs/51 §4.1 冻结）；W 组新 schema 落地后 EX 层退役。

---

## 十一、工具与脚本

| 用途 | 工具 | 说明 |
|---|---|---|
| 完成门 | `scripts/pipeline_wuxia.py` | 14 机械阶段 + check（五门 lint） |
| 导出入口 | `scripts/export_site_all.py` | 默认 dry-run/staging；--apply 前备份 site/data |
| 导出契约校验 | `scripts/export_site_common.py` | hard_gap/field_gaps/meta 校验 |
| 书/卷导出 | `scripts/export_site_books_chapters.py` | EX-1（books/chapters） |
| 人物/索引导出 | `scripts/export_site_characters.py` | EX-2（characters/entity-index） |
| 档案导出 | `scripts/export_site_dossiers.py` | EX-3（dossiers） |
| 门派/神兵/招式导出 | `scripts/export_site_sects_weapons_arts.py` | EX-6（sects/weapons/arts） |
| 统计数据与渲染校验 | `scripts/build_entity_concordance.py` | 导出前的实体去重基线 |

> 渲染器本体（AST→HTML）尚未实现，见附录 B D-1；上表为现有实现。

---

## 十二、相关文档

| 文档 | 关系 |
|---|---|
| `SKILL_01g_标注符号集合原则.md` | 符号/类型/发布边界（§二/§9.8-9.10） |
| `SKILL_02a_02b_章回结构与韵文处理.md` | PN 锚点/围栏渲染语义/变更治理 |
| `SKILL_03a_实体标注.md` | 令牌输出契约/管道规则 |
| `SKILL_03b_人名消歧_武侠版.md` | 规范名/展示层/发布过滤口径 |
| `SKILL_SKU卡片_武侠版.md` | SKU 卡字段与发布脱敏规则 |
| `docs/51-E组合流决策与导出适配层方案.md` | EX 导出契约与冻结边界（本文发布架构） |
| `docs/52-EX导出层阶段0-1实施记录.md` | 阶段 1 实测（8 数据文件 hard_gap=0、构建页数） |
| `scripts/export_site_all.py` / `scripts/export_site_common.py` | 导出入口/契约校验 |
| `scripts/pipeline_wuxia.py` | 完成门（14 机械阶段 + check） |

---

## 附录 A · 与 shiji 03d 原版差异对照（META-13 纪律）

| 史记 03d | 处置 | 武侠版 |
|---|---|---|
| `render_shiji_html.py` 渲染器 | [不移植] | 自建 AST→HTML 契约（§五）；站点走 Astro |
| 单书目录/章号 | [替换] | 多书目录 + `{作品ID}#pn-r{N}.{X}` 机锚 |
| 18 类配色 | [替换] | 15 实体 + 6 动词 + 修辞（01g 定版） |
| 赞文排版 | [替换] | 10 类围栏渲染语义（02ab §4.1） |
| 发布口径 | [补写] | 01g §9.10 边界执行 + 本地/公开分层 |
| 渲染脚本调用链 | [替换] | pipeline check → EX 导出 → Astro 构建 |

## 附录 B · v0.1 待补清单

| # | 待补 | 归属/前置 |
|---|---|---|
| D-1 | AST 生成器与 AST→HTML 转换器**未实现**（本文只定契约） | S-09a 工程；需色板定稿 |
| D-2 | 具体色板/主题未冻结（15 类色值、动词 6 域弱化方案） | S-09a 设计 |
| D-3 | 本地阅读器前端未建（点击档案/搜索/图例开关） | 应用层 |
| D-4 | EX-4/5/7/8（graph/matches/ratings/audit 等）依赖 N5/N7/N8 | docs/51 §六 阶段 2/3 |
| D-5 | site 13 份 atlas 分书数据契约仅 4 书有来源（gazetteer 待 N7） | N7 |
| D-6 | 站点页面数随数据收敛（1480–1508）需在每次发布记录 | 发布流程 |
| D-7 | 渲染指标（首屏/体积/可访问性）未定义 | S-09a |

---

## 结语

渲染发布不是"把标注染色成网页"，而是**把三层语料翻译成两种交付物**：本地阅读器要能点、能查、能回原文锚点；公网站点只拿结构化数据、守死发布边界。契约先于实现，边界先于美观。
