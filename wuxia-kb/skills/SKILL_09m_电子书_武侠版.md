---
name: skill-09m-wuxia
title: 电子书（武侠版）——EPUB 章节结构、围栏样式、PN 映射与三版矩阵
description: 武侠知识库电子书产物规范：从 tagged/struct 经 03d AST 契约转 XHTML/EPUB3（mimetype/container/opf/nav/spine），按 books.json（34 部）与 chapters.json（1,378 回）组织章节，10 类围栏（词/诗/歌/对联/回目对/回末/书信/告示/口诀/说书）的 XHTML+CSS 映射与 PN 锚点（{作品ID}#pn-r{N}.{X}）双向映射，三版矩阵（lite/std/full，原六版裁为三版）、确定性/幂等/消毒断言，以及本地阅读器产物不得进入 site/data 的发布边界；v0.1 明确裁掉古籍竖排。当需要制作 EPUB、单文件 HTML 阅读器或核对电子书结构时使用。
version: v0.1-draft
last_updated: 2026-11-05
---

# SKILL 09m 武侠版：电子书 — 让标注语料"装订成书"而不出界

> **上游声明**：本件属 S 组 P5 应用层，对应 docs/03 §3.10 原 09m 电子书（**中度 60-65%**：形式学与工具链通用，换选题即用）。**无专属设计稿**：由 `02ab` 围栏类型与 PN 锚点、`03d` AST→HTML 契约 H-1~H-10、EX-1 `books/chapters`、`01g §9.10` 发布边界综合而成（v0.1 框架）。**设计裁剪**：按 docs/05 裁定——**裁掉古籍竖排**；版本矩阵由原六版**减为三版**（lite/std/full）。
> **接口**：`tagged/<书>/*.tagged.md` + `struct/`（只读）、`../site/data/books.json`、`../site/data/chapters.json`、03d AST 节点模型（chapter/fence/para/entity/verb/text）、`registry/`（canonical 与 status）、`content/person/`（可选卡页链接）。
> **核心原则**：**电子书是标注产物的"只读装订"，不是第二次编辑。** 文字必须与剥标原文逐字一致（H-4），锚点必须唯一（H-1），产物只能本地（H-10）。

---

## 一、定位与边界

### 1.1 工序位置

```text
tagged / struct（只读）
        ↓
03d AST（契约冻结，转换器 v0.1 未实现）
        ↓
XHTML 分章（ch004.xhtml）→ EPUB3 打包（opf/nav/spine）
        ↓
本地阅读器产物（EPUB / 单文件 HTML）   ← 不入 site/data（H-10）
```

### 1.2 本文做什么

1. **章节结构**：34 部/1,378 回 → EPUB `nav`/`spine` 与文件命名规则，卷/系列可选分组；
2. **围栏样式**：10 类围栏 → `wx-fence wx-fence-<roman>` + `data-fence`，CSS 样式表映射；
3. **PN 映射**：`{作品ID}#pn-r{N}.{X}` ↔ XHTML `id`/`data-pn` ↔ EPUB CFI，双向可回锚；
4. **三版矩阵**：lite/std/full 三版能力边界与体积/依赖取舍；
5. **质量断言**：H-1/H-4/H-6/H-7/H-8/H-9/H-10 在打包流程中的落点；
6. **发布边界**：本地阅读器产物、原文版权、禁入站点数据目录。

### 1.3 本文不做什么

| 不做 | 归属 |
|---|---|
| 改 tagged/struct/PN | 只读（`generate_pn_wuxia.py` 产物） |
| 实现 AST→HTML 转换器 | 03d 契约（未实现，附录 B） |
| 竖排/古籍版式 | **裁掉**（docs/05 裁定） |
| 公开分发原文 EPUB | 禁（`01g §9.10` + 版权） |
| 站点数据导出 | EX 层（`export_site_*`） |
| DRM/加密/商店上架 | 超范围 |

### 1.4 关键约束

- **文字零改动**：XHTML `textContent` 必须等于 `strip(tagged)` 逐段一致（H-4），只允许加包裹元素；
- **锚点唯一**：每 PN 块唯一 `id` + `data-pn`（H-1）；围栏整体一 PN（02ab §3.3）；
- **类名合法**：围栏只用 `wx-fence-<roman>` 十字段集合（H-6），实体/动词类名不混用（H-2/H-3）；
- **无脚本**：禁内联事件处理器与远程资源（H-7）；CSS 本地、字体可选嵌入；
- **确定性**：同 AST 两次打包字节一致（H-8），时间戳/随机数不进 XHTML；
- **未审核不渲染**：`status=pending` 实体不加 `data-canonical`/跳转（H-9）；
- **本地隔离**：EPUB/阅读器产物不得进入 `site/data`、`content/`、`public/`（H-10）。

---

## 二、快速开始（五步）

````text
Step 1 取数   读 books.json / chapters.json，确认书目、回目、lit 状态
Step 2 分章   按"一书一目录、一回一 XHTML"切分，命名 ch{NNN}.xhtml
Step 3 转换   struct → AST → XHTML（03d 契约；v0.1 转换器未实现，按契约手工/脚本试制）
Step 4 映射   围栏类名 + PN 锚点 + CFI 双向映射表（§四/§五）
Step 5 打包   按 §六 三版矩阵选版；跑 §七 断言；产物只落本地目录
````

只读取数示例：

```python
import json
from pathlib import Path

D = Path('../site/data')
books = json.load(open(D / 'books.json', encoding='utf-8'))
chaps = json.load(open(D / 'chapters.json', encoding='utf-8'))

print(books['meta']['totals'])                 # 34 部 / 1,378 回 / 17,004,474 字
lit = set(chaps['meta']['lit_books'])          # 5 书有章级特征
for b in books['books'][:3]:
    print(b['no'], b['book'], b['chapters'], b['kb_status'], 'lit' if b['book'] in lit else 'toc-only')

# 回目：每书 chapters[] 的 title（取自章回版文件名，不另行改写）
toc = chaps['七剑下天山']['chapters']
print(len(toc), toc[0]['title'])
```

> `chapters.json` 的每书 `{chapters, lit, kb}`；未点亮书只有回目元数据（`toc-only`），电子书仍可出 lite 版，但不得伪造章级特征。

---

## 三、章节结构与 EPUB3 骨架

### 3.1 文件布局

```text
ebook/
  mimetype                     # 首文件、无压缩、内容 application/epub+zip
  META-INF/container.xml
  OEBPS/
    content.opf                # metadata / manifest / spine
    nav.xhtml                  # EPUB3 导航（目录）
    toc.ncx                    # 兼容 EPUB2 可选
    css/book.css               # 围栏/段落/实体样式（本地）
    text/
      {book_slug}/
        ch001.xhtml ... chNNN.xhtml
    pn_cfi_map.json            # PN ↔ CFI ↔ id 映射（v0.1 约定，附录 B 未实现）
```

### 3.2 分章规则

| 层级 | 依据 | 规则 |
|---|---|---|
| 部 | `books[].book`（34） | 一书一目录 `text/{slug}/`；`slug` 用拼音或序号，禁中文路径 |
| 回 | `chapters[].no/title`（1,378） | 一回一 `chNNN.xhtml`；`no=0` 为楔子/序，保留原编号 |
| 卷/系列 | `books[].series` | 可选 `nav` 二级分组；`series_conf≠ok` 不自动分组 |
| 导航 | `nav.xhtml` | 三级：系列（可选）→ 书 → 回；标题取 `title` 原文，不改写 |

`content.opf` 的 `spine` 顺序 = `books[].no` → `chapters[].no`，与 `books.json` 顺序一致；`manifest` 每文件一条，`media-type` 用 `application/xhtml+xml`。

### 3.3 XHTML 单章骨架

```html
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh">
<head><meta charset="utf-8"/><title>第四回 回目原文</title>
<link rel="stylesheet" href="../../css/book.css"/></head>
<body>
<section class="wx-chapter" data-book="七剑下天山" data-chapter="4">
  <h1 class="wx-chapter-title">第四回 回目原文</h1>
  <div class="wx-fence wx-fence-ci" data-fence="词" id="qijian-r4-1" data-pn="七剑下天山#pn-r4.1">…</div>
  <p class="wx-para" id="qijian-r4-2" data-pn="七剑下天山#pn-r4.2">
    <span class="wx-ent wx-ent-at" data-etype="@" data-token-id="t-0001">练霓裳</span>…</p>
</section>
</body></html>
```

> 上述结构照 `03d` 契约示例；**实体/动词节点只加包裹、不改字符**（H-4），`data-canonical` 仅在可唯一回溯时输出（H-5）。

---

## 四、围栏样式映射（10 类）

### 4.1 类名表（H-6，固定不可增删）

| `data-fence` | 类名 | 典型样式 | 备注 |
|---|---|---|---|
| 词 | `wx-fence-ci` | 居中、字号略小、段前段后留白 | 吟诵体 |
| 诗 | `wx-fence-shi` | 居中、逐行 | 五七言 |
| 歌 | `wx-fence-ge` | 居中、行距放宽 | 歌行/民歌 |
| 对联 | `wx-fence-duilian` | 居中、两行对齐 | 一般对 |
| 回目对 | `wx-fence-huimodui` | 居中、加粗 | 回目联语 |
| 回末 | `wx-fence-huimo` | 右对齐/缩进、与正文分隔 | 回末套语 |
| 书信 | `wx-fence-shuxin` | 缩进、引文块 | 书信体 |
| 告示 | `wx-fence-gaoshi` | 边框/居中 | 榜文告示 |
| 口诀 | `wx-fence-koujue` | 等宽感、逐条 | 武功口诀 |
| 说书 | `wx-fence-shuoshu` | 缩进、叙述腔 | 说书人套语 |

### 4.2 CSS 纪律

- 只写 `.wx-fence-*`、`.wx-para`、`.wx-ent-*`、`.wx-verb-*` 四组选择器，不写全局 `p`/`div` 样式（避免污染阅读器主题）；
- **不实现竖排**（`writing-mode: vertical-rl` 禁用）：裁古籍竖排是本版裁定，样式表加注释说明；
- 字体：默认系统字体；如需嵌入，仅嵌入授权字体，且体积计入版本矩阵（full 版才允许）；
- 禁远程 `@import`/`url(http…)`（离线可读 + H-7）。

---

## 五、PN ↔ CFI 映射

### 5.1 三层锚点

| 层 | 形式 | 生成者 | 用途 |
|---|---|---|---|
| 机锚 PN | `{作品ID}#pn-r{N}.{X}` | `generate_pn_wuxia.py`（struct） | 跨层唯一标识 |
| XHTML id | `{slug}-r{N}-{X}`（可读形式） | 转换器 | 阅读器内跳转 |
| EPUB CFI | `epubcfi(/6/{spine}/{offset}…)` | 打包器/阅读器 | EPUB 内定位 |

**规则**：`id` 与 `data-pn` 必须同时输出且全书唯一（H-1）；CFI 允许由阅读器现算，但一旦写入 `pn_cfi_map.json` 必须可逆（同版 EPUB 内 PN→CFI→PN 往返一致）。

### 5.2 `pn_cfi_map.json`（v0.1 约定）

```json
{
  "schema": "pn-cfi-map-v0.1",
  "book": "七剑下天山",
  "epub_version": "lite",
  "generated_from": {"ast_schema": "v0.1", "html_contract": "v0.1", "data_version": "2026-11-05.01"},
  "items": [
    {"pn": "七剑下天山#pn-r4.1", "xhtml": "text/qijian/ch004.xhtml", "id": "qijian-r4-1", "cfi": null}
  ]
}
```

`cfi:null` 表示待阅读器回填；**不得**手工编 CFI（CFI 与 DOM 结构强耦合，手填必错）。

### 5.3 回锚校验

```text
每个 pn 在 XHTML 中恰好 1 个 data-pn（H-1）
每个 data-pn 能在 struct 找到同值 PN（反查）
strip(textContent) == strip(tagged) 逐段（H-4）
```

三条全过才算"可回锚"；缺一即阻断打包。

---

## 六、三版矩阵（原六版裁为三版）

| 版本 | 内容 | 围栏样式 | PN 锚点 | 实体/动词着色 | 体积 | 适用 |
|---|---|---|---|---|---|---|
| `lite` | 纯文本 + 标题 + 目录 | 无（仅段落） | 无 | 无 | 最小 | 通用阅读器/低配设备/未点亮 29 部 |
| `std` | + 围栏样式 + PN 锚点 | 10 类 | 有 | 无 | 中 | 主力版；5 书点亮集 |
| `full` | + 实体/动词着色 + 卡页链接 | 10 类 | 有 | 有（H-2/H-3/H-5/H-9） | 最大 | 研究型本地阅读器 |

**裁剪说明**：原六版（含竖排版、注释版、双语版等）按 docs/05 裁定减为三版；竖排版整体删除，不设开关。三版共用同一 AST 与同一 `strip(tagged)` 断言，差异只在渲染层。

---

## 七、打包与断言

### 7.1 打包顺序

```text
1. 生成 XHTML（AST→HTML，确定性：无时间戳/随机数）
2. 写 nav.xhtml / content.opf（spine 顺序 = books[].no → chapters[].no）
3. 写 pn_cfi_map.json（cfi 可空）
4. 打包（mimetype 首文件、无压缩）
5. 断言（§7.2）→ 失败即不产出
```

### 7.2 断言清单（对应 03d H 系列）

| 断言 | 内容 | 对应 |
|---|---|---|
| A-1 | 每 PN 块唯一 `id` + `data-pn`，全书无重复 | H-1 |
| A-2 | `wx-ent`/`wx-verb` 类名与 `data-etype`/`data-vtype` 一致 | H-2/H-3 |
| A-3 | `strip(textContent) == strip(tagged)` 逐段一致 | H-4 |
| A-4 | `data-canonical` 仅在可唯一回溯时出现 | H-5 |
| A-5 | 围栏类名 ∈ 十字段集合，`data-fence` 为中文类型 | H-6 |
| A-6 | 无 `on*=`、无远程 `http(s)://` 资源 | H-7 |
| A-7 | 双跑打包字节一致（mimetype 除外时间戳） | H-8 |
| A-8 | `status=pending` 实体无 `data-canonical`/跳转 | H-9 |
| A-9 | 产物路径不在 `site/data`/`content/`/`public/` | H-10 |

### 7.3 外部校验（可选）

`epubcheck` 属外部工具（未内置）：v0.1 以 A-1~A-9 + XML 良构（`xml.etree` 解析）为准；接入 epubcheck 列入附录 B。

---

## 八、工具与脚本

| 脚本/文件 | 用途 | 备注 |
|---|---|---|
| `scripts/generate_pn_wuxia.py` | 生成 PN/struct（上游，只读） | PN 格式 `{作品ID}#pn-r{N}.{X}` |
| `scripts/extract_paragraph_structure.py` | 段落结构抽取（AST 输入） | 只读 |
| `scripts/lint_fence_format.py` | 围栏格式检查 | 打包前预检 |
| `scripts/lint_text_integrity.py` | 文本完整性（对照剥标原文） | H-4 辅助 |
| `scripts/lint_markdown.py` | Markdown 结构检查 | 文档侧 |
| `scripts/export_site_books_chapters.py` | EX-1 书/章元数据 | 分章与目录依据 |
| `scripts/lint_skills.py` | 本件自检 | `python -X utf8 scripts/lint_skills.py "skills/SKILL_09m_电子书_武侠版.md"` |

> **v0.1 无打包器**：scripts/build_ebook.py（AST→XHTML→EPUB + A-1~A-9 断言）未实现；当前按本文契约手工/脚本试制，见附录 B。

---

## 九、错误模式库（EB 系列）

| ID | 错误 | 表现 | 检测 | 修正 |
|---|---|---|---|---|
| EB-01 | 竖排混入 | CSS 出现 `vertical-rl` 或竖排版产物 | 样式扫描 | 删除（本版裁竖排） |
| EB-02 | 围栏类名非法 | `wx-fence-词`/自造类名 | A-5 对照十字段表 | 改 `wx-fence-<roman>` |
| EB-03 | PN 重复/丢失 | 同章两个 `data-pn` 相同或缺失 | A-1 唯一性扫描 | 回 struct 重生成 |
| EB-04 | 文字被改 | `textContent` 与剥标原文不一致 | A-3 逐段断言 | 回退到只加包裹 |
| EB-05 | 产物入站 | EPUB/阅读器文件出现在 `site/data` | A-9 路径审计 | 移出并加防护 |
| EB-06 | 版本膨胀 | 出现第四版/自定义版 | 版本枚举校验 | 归入三版之一 |
| EB-07 | 目录错序 | `spine` 与 `books[].no`/`chapters[].no` 不一致 | 顺序断言 | 重排 |
| EB-08 | pending 实体渲染 | 未审核实体带 `data-canonical` | A-8 status 过滤 | 只留显示串 |
| EB-09 | 非确定性 | 两次打包字节不同 | A-7 双跑 diff | 去时间戳/随机数 |
| EB-10 | 远程资源 | `@import`/`url(http…)`/字体 CDN | A-6 扫描 | 改本地 |

---

## 十、检查清单

### 制作前

- [ ] 书目/回目与 `books.json`/`chapters.json` 对齐（34/1,378）；
- [ ] 该书 `kb_status` 已知：未点亮书只出 lite；
- [ ] 版本（lite/std/full）已选且不越界；
- [ ] 输入 struct/tagged 版本与 `data_version` 已记录。

### 制作中

- [ ] XHTML 良构（`xml.etree` 可解析）；
- [ ] 围栏只用十字段类名，`data-fence` 中文类型；
- [ ] PN `id`/`data-pn` 唯一，`pn_cfi_map.json` 无手填 CFI；
- [ ] `strip(textContent) == strip(tagged)` 逐段通过；
- [ ] 无脚本、无远程资源、无竖排样式。

### 交付前

- [ ] A-1~A-9 断言全过；
- [ ] 目录 `spine` 顺序正确；
- [ ] 产物路径不在 `site/data`/`content/`/`public/`；
- [ ] 版权声明与"仅本地"说明随产物；
- [ ] `epubcheck`（若已接入）0 error。

## 十一、成功标准（v0.1）

1. **文字一致率 100%**：A-3 逐段断言 0 差异；
2. **锚点唯一率 100%**：A-1 重复 0、缺失 0；
3. **围栏合法率 100%**：A-5 越界类名 0；
4. **确定性**：A-7 双跑字节一致（mimetype 时间戳除外）；
5. **隔离 0 越界**：A-9 产物 0 个进入发布目录；
6. **三版收敛**：产物版本 ∈ {lite,std,full}，无第四版、无竖排。

---

## 十二、FAQ（首批 5 问）

**Q1：为什么裁掉竖排？**
docs/05 裁定：竖排涉及字体/标点/行内注的连锁改造，收益低、成本高，v0.1 直接裁掉并写进契约，避免"半竖排"的坏产物。

**Q2：三版和原六版差在哪？**
原六版含竖排、注释、双语等；本版只保留 lite/std/full，差异集中在渲染层（围栏/锚点/着色），共用同一 AST 与文字断言。

**Q3：未点亮的 29 部能出电子书吗？**
能出 lite（纯文本 + 回目 + 目录），因为回目元数据齐全；但不能出版本 std/full 的围栏/着色，因为缺章级标注。

**Q4：PN 和 CFI 都要维护吗？**
PN 是知识库机锚，必须全量；CFI 由阅读器按版式现算，只在需要跨阅读器定位时写入映射表，且不得手填。

**Q5：电子书能放到站点上吗？**
不能。EPUB/阅读器产物属本地阅读层（H-10），站点只放 EX 导出的结构化数据与卡页；原文版权不在本库处置范围。

---

## 十三、相关文档

- `SKILL_03d_渲染发布_武侠版.md`（AST/HTML 契约 H-1~H-10，本件上游）
- `SKILL_02a_02b_章回结构与韵文处理.md`（围栏类型与 PN 锚点）
- `SKILL_09e_有声书_武侠版.md`（同类"只读产物"契约，可对照）
- `SKILL_09_应用总览_武侠版.md`（应用层命名与 P5 状态）
- `SKILL_01g_标注符号集合原则.md`（§9.10 发布边界）
- `docs/59`、`docs/60`（EX 导出与 S 组 P5 记录）

---

## 附录 A · 与 shiji 原版差异对照（本件为骨架+综合，中度 60-65%）

| 维度 | shiji 09m 电子书 | 本件（武侠版） | 性质 |
|---|---|---|---|
| 产物形态 | EPUB/HTML/PDF | 照搬 EPUB3 + 单文件 HTML；PDF 不做 | 照搬（裁剪） |
| 章节结构 | 通用书章模型 | 照搬，映射为 34 部/1,378 回与 `nav/spine` | 照搬（换对象） |
| 围栏样式 | 通用文体块 | 照搬机制，类名换为 10 类武侠围栏（H-6） | 照搬（换映射） |
| PN 映射 | 原设计未细化 | 本件自拟三层锚点（PN/id/CFI）+ `pn_cfi_map.json` | 骨架+综合 |
| 版本矩阵 | 六版 | **裁为三版**（lite/std/full） | 设计裁剪 |
| 竖排 | 有竖排方案 | **裁掉**，禁 `vertical-rl` | 设计裁剪 |
| 发布边界 | 通用 | 接 `01g §9.10` + H-10 本地隔离 | 武侠增补 |

## 附录 B · v0.1 待补清单

1. **打包器**：scripts/build_ebook.py（AST→XHTML→EPUB + A-1~A-9 断言）未实现，是本件最大缺口；
2. **AST→HTML 转换器**：03d 契约已冻结但转换器未实现（与 03d 同一缺口）；
3. **CFI 回填**：`pn_cfi_map.json` 的 CFI 需阅读器联调回填，当前只能留 `null`；
4. **epubcheck 集成**：外部校验未接入，仅 XML 良构 + 自研断言；
5. **字体嵌入**：授权字体未定，full 版暂用系统字体；
6. **封面/元数据**：`content.opf` 的 `dc:title/dc:creator/dc:language` 取值规则待定（书名/作者元数据在 `books.json` 外）；
7. **竖排**：按裁定不做；若未来恢复，需单独立项（字体/标点/行内注连锁改造）。

---

## 结语

电子书是本项目里**最像"成品"、也最容易越界**的一层：它把标注语料装订成可读文件，但只要文字被改一个字、锚点重复一次、产物进了站点目录，前面的考订就全白费。守住"零改动、唯一锚、本地隔离"三条，装订才是安全的。
