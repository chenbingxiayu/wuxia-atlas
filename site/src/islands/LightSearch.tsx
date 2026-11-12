import { useMemo, useState } from 'react';

/**
 * LightSearch · 武功/名物总览轻量搜索岛（W2-A1，方案 §5.3 EntitySearch 轻量模式·武功/名物复用）。
 *
 * 模式：构建期静态索引（.astro frontmatter 由 arts.json/weapons.json 组装 items）+ 客户端过滤，
 * 不引第三方库；空查询=全部分组原样渲染（SSR 首帧即全量，hydration 无跳变）。
 * 搜索域：规范名 + 别名（名物/武功）+ children 招式名（仅武功）；
 * 经别名/招式命中的 chip/卡片以小字标注匹配词（搜「大漠流沙」→ 天山剑法 标注 招式·大漠流沙）。
 * hooks 纪律（islands README 第 1 条）：全部 hooks 声明在前，无条件早退。
 */
export interface LightItem {
  c: string;                            // 规范名（chip/卡片标题，链接文案）
  href: string;                         // 详情链接（构建期生成，含 base）
  g: string;                            // 分组（武功品类 / 名物类别）
  n?: number;                           // 频次小字（武功 ev_total）
  x?: boolean;                          // 跨书描边
  a?: string[];                         // 别名（搜索域）
  m?: string[];                         // 招式名（搜索域，仅武功 children）
  // —— 名物卡片附加（mode='cards' 时渲染，与原 SSR 卡片逐字段同形）——
  grade?: string;                       // 品阶
  gradeBasis?: string;                  // 品阶依据（明文→实徽章，否则虚徽章）
  kind?: string;                        // 类别
  edges?: { v: string; p: string[] }[]; // 流转边（强证前 4；p 已过展示层）
  noneNote?: string;                    // 无强证边占位（共现证据 N 处）
  foot?: string[];                      // 卡脚注 [书目, 证据, 档位文案]（第 3 位上档位色）
  conf?: string;                        // 档位配色类名（页面经 lib/tiers tierClass 映射：t-hi/t-mid/t-lo）
}

const low = (s: string) => (s || '').toLowerCase();

/** 命中的搜索域外名（别名/招式），用于 chip/卡片小字说明"为何命中"；规范名命中时不标注。 */
function hitExtra(e: LightItem, q: string): string | undefined {
  const query = low(q);
  if (!query) return undefined;
  if (low(e.c).includes(query)) return undefined;
  const al = (e.a || []).find((x) => low(x).includes(query));
  if (al) return al;
  return (e.m || []).find((x) => low(x).includes(query));
}

export default function LightSearch({
  items,
  groups,
  mode = 'chips',
  placeholder = '输入名称筛选…',
  anchorIds = false,
  axis2,
}: {
  items: LightItem[];
  groups: string[];                     // 分组顺序（构建期定序）
  mode?: 'chips' | 'cards';             // chips=武功总览；cards=名物总览
  placeholder?: string;
  anchorIds?: boolean;                  // 分组标题挂 id（名物页顶部类目锚点导航用）
  // D3 双轴（可选）：第二套分组域——平行 items 数组（各自以 g 为第二轴分组键）+ 组序 + 轴注记。
  // 存在时两轴各包一层容器（.lsearch-axis / .lsearch-axis-alt），由页面 radio+CSS 切换显示
  // （零 JS，先例 books/index.astro；武功页重构设计 §四「轴切换：按品类 | 按门派」）；
  // 搜索过滤（visible 集）对两轴同生效——一次查询，两视图同步。
  // 不传时渲染路径与先前逐节点一致（名物页等单轴用法零影响）。
  axis2?: { items: LightItem[]; groups: string[]; note?: string };
}) {
  const [q, setQ] = useState('');

  // 命中集合（空查询=null → 全部渲染；Set<canonical> 判可见）
  const visible = useMemo(() => {
    const query = low(q.trim());
    if (!query) return null;
    return new Set(
      items
        .filter(
          (e) =>
            low(e.c).includes(query) ||
            (e.a || []).some((x) => low(x).includes(query)) ||
            (e.m || []).some((x) => low(x).includes(query)),
        )
        .map((e) => e.c),
    );
  }, [items, q]);

  // 分组（保持构建期给定的组序与组内序）
  const byGroup = useMemo(() => {
    const map = new Map<string, LightItem[]>();
    for (const g of groups) map.set(g, []);
    for (const e of items) {
      if (!map.has(e.g)) map.set(e.g, []);
      map.get(e.g)!.push(e);
    }
    return map;
  }, [items, groups]);

  // D3 第二轴分组（保持构建期给定的组序与组内序；仅 axis2 传入时构建）
  const byGroup2 = useMemo(() => {
    if (!axis2) return null;
    const map = new Map<string, LightItem[]>();
    for (const g of axis2.groups) map.set(g, []);
    for (const e of axis2.items) {
      if (!map.has(e.g)) map.set(e.g, []);
      map.get(e.g)!.push(e);
    }
    return map;
  }, [axis2]);

  const total = visible === null ? items.length : visible.size;

  // 分组渲染（两轴共用同一段 section JSX；list=查询过滤后的组内条目，空组整段不渲染）
  const renderAxis = (groupOrder: string[], grouped: Map<string, LightItem[]>) =>
    groupOrder.map((g) => {
      const list = (grouped.get(g) || []).filter((e) => !visible || visible.has(e.c));
      if (list.length === 0) return null;    // JSX 回调内返回，非组件早退
      return (
        <section key={g}>
          <h2 id={anchorIds ? g : undefined}>
            {g}
            {/* 名物页原 h2 形制 <small>N 件</small>；武功页原形制 （N） */}
            {mode === 'cards'
              ? <small>{list.length} 件</small>
              : <span className="dim">（{list.length}）</span>}
          </h2>
          {mode === 'cards' ? (
            <div className="grid">
              {list.map((e) => {
                const hit = hitExtra(e, q);
                return (
                  <a key={e.c} className={'card' + (hit ? ' ahit' : '')} href={e.href}>
                    <div className="head">
                      <b>{e.c}</b>
                      {e.grade && (
                        <span className={e.gradeBasis === '明文' ? 'badge solid' : 'badge dashed'}>
                          {e.grade}
                        </span>
                      )}
                      {e.kind && <span className="kind">{e.kind}</span>}
                    </div>
                    <div className="chain">
                      {(e.edges || []).map((ed, i) => (
                        <span key={i} className="edge"><i>{ed.v}</i>{ed.p.join('+')}</span>
                      ))}
                      {(e.edges || []).length === 0 && e.noneNote && (
                        <span className="none">{e.noneNote}</span>
                      )}
                    </div>
                    <div className="foot">
                      {(e.foot || []).map((f, i) => (
                        <span key={i} className={i === 2 ? e.conf : undefined}>{f}</span>
                      ))}
                    </div>
                    {hit && <div className="hit-note">命中：{hit}</div>}
                  </a>
                );
              })}
            </div>
          ) : (
            <p className="chips">
              {list.map((e) => {
                const hit = hitExtra(e, q);
                return (
                  <a key={e.c} className={'chip' + (e.x ? ' cross' : '') + (hit ? ' ahit' : '')}
                     href={e.href}>
                    {e.c}
                    {typeof e.n === 'number' && <small>·{e.n}</small>}
                    {hit && <small className="hit-note">{hit}</small>}
                  </a>
                );
              })}
            </p>
          )}
        </section>
      );
    });

  return (
    <div className="lsearch">
      <div className="lsearch-bar">
        <input
          value={q}
          placeholder={placeholder}
          onChange={(e) => setQ(e.target.value)}
        />
        <span className="lsearch-meta">
          {q.trim() ? `${total} 条命中` : `共 ${items.length} 条`}
        </span>
      </div>
      {axis2 && byGroup2 ? (
        <>
          {/* D3 双轴：两容器由页面 radio+CSS 切换（.lsearch-axis-main=默认轴 / .lsearch-axis-alt=门派轴；
              两类名互不为对方 class token 的子集——避免 .lsearch-axis 选择器连坐隐藏两轴） */}
          <div className="lsearch-axis-main">{renderAxis(groups, byGroup)}</div>
          <div className="lsearch-axis lsearch-axis-alt">
            {axis2.note && <p className="lsearch-axis-note">{axis2.note}</p>}
            {renderAxis(axis2.groups, byGroup2)}
          </div>
        </>
      ) : (
        renderAxis(groups, byGroup)
      )}
      {total === 0 && <p className="lsearch-empty">无匹配结果——试试别名或招式名。</p>}
    </div>
  );
}
