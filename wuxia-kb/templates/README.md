# templates/ 模板库（武侠版）

> **定位**：可复制的静态模板（SKILL 骨架、页面/档案页型），与 `skills/`（技能规范正文）、`references/`（规律库）互补。
> **纪律**：模板只给结构与槽位，不重复定义规范；规范唯一来源是 `skills/SKILL_*` 正文；模板中引用的字段/判定须标注来源（SKILL 章节 / registry 路径）。占用文件名保持稳定，不重命名。

## 一、索引

| 文件 | 类型 | 用途 | 来源/依据 |
|---|---|---|---|
| `SKILL_template.md` | SKILL 骨架 | 新建项目 SKILL 的通用模板：frontmatter/快速开始（≤150 行）/定位边界/核心方法/工具与脚本/检查清单/成功标准/错误模式/反思挂钩/附录 A 差异/附录 B 待补；文末含复制后 12 项自检清单（对齐 `scripts/lint_skills.py` 10 项检查） | `skills/README.md` 收录标准 + lint_skills 规则 + S-03c/03c1 接口 |
| `忠义殉主者.md` | 页面/档案页型 | W8 精品页五段式（适用判断→必有节→加分项→反面示例→参考页面）+ SKILL_08a 人物卡槽位 + Markdown 模板 + demo 填充 + 8 条反面示例；同族页型（门派覆灭者/武功失传者/师门叛徒）可复用骨架 | `skills/SKILL_08a_SKU字段_武侠版.md`、`skills/SKILL_03d_渲染发布_武侠版.md`、docs/05 §2.5-§2.6、`registry/sku/cards.json`（N10） |

## 二、使用约定

1. **复制不修改原模板**：新建文件从模板复制后按 §三 自检，原模板只在结构性改进时更新（升版本）。
2. **demo 数据边界**：模板示例数据必须标 `demo: true`，不得进入发布库（对齐 SKU 卡 R4 脱敏纪律）。
3. **页面型模板**：输出到 `content/`（建议）或 W 组产物目录，frontmatter 须含 `quotes[]` 独立字段供 W7 `verify_quotes.py` 消费。
4. **与 lint 对齐**：SKILL 型模板复制后跑 `python scripts/lint_skills.py <file>`，目标 PASS ≥90（总长 warning 可接受）。

## 三、复制后自检（SKILL 型）

- [ ] frontmatter 含 `name/title/description/version/last_updated`（无 BOM、LF）
- [ ] 快速开始 ≤150 行且命令可复跑
- [ ] 定位/边界明确（做什么/不做什么/与相邻 SKILL 分工）
- [ ] 引用的脚本与 SKILL 文件均真实存在
- [ ] 检查清单与成功标准可验证（量化优先）
- [ ] 错误模式库有编号且与 03a DEF / 04f 错误库不重复
- [ ] 反思挂钩指向 03c/03c1 与回写 owner
- [ ] 附录 A 差异对照（对照 shiji 同名件）
- [ ] 附录 B 待补清单（待拍板/待补数据逐条）
- [ ] 文内无 CSS/HTML 围栏、无日期偏置硬编码
