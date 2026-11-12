/**
 * 证据档位显示映射（总体方案 §3.3 术语收口 · §5.4 ConfBadge 文案来源）。
 *
 * 红线：数据层 conf/tier 字段值（strong/ok/weak）与比较逻辑一律不改；
 * 本模块只约束「用户可见文案」与「配色类名」，供各页与 W3 ConfBadge 组件复用。
 * 数据域（实测）：weapons.conf/chain.conf、sects tenures/members.tier、arts children.conf
 * 取值均为 strong | ok | weak；ratings 档位（绝顶/超一流…）是另一套中文体系，不经此表。
 */

/** 数据层档位值（schema 保留，不改动） */
export type Tier = 'strong' | 'ok' | 'weak';

/** 用户词表（设计文档 §3.3 定稿）：strong→强证 · ok→确证 · weak→线索 */
export const TIER_LABEL: Record<Tier, string> = {
  strong: '强证',
  ok: '确证',
  weak: '线索',
};

/** 档位 → 显示文案；未知值原样透出（数据域扩展时兜底，不静默吞值） */
export function tierLabel(tier?: string | null): string {
  return (tier && TIER_LABEL[tier as Tier]) || tier || '';
}

/**
 * 档位 → 配色类名。类名不携带 raw 值（避免 strong/ok/weak 经 class 属性进入 HTML 文本层）：
 * t-hi=强证 · t-mid=确证 · t-lo=线索；未知值不染色（返回 undefined）。
 */
export const TIER_CLASS: Record<Tier, string> = {
  strong: 't-hi',
  ok: 't-mid',
  weak: 't-lo',
};

/** 档位 → 配色类名（未知值返回 undefined，不产出 raw 词） */
export function tierClass(tier?: string | null): string | undefined {
  return tier ? TIER_CLASS[tier as Tier] : undefined;
}

/**
 * 数据 note 文本清洗：数据层考订注记（如 arts.json relations[].note「招式表子式（conf=ok）」）
 * 内嵌 raw 档位词，red line 不改数据 → 渲染层把 `conf=<raw>` 整体替换为用户词表文案
 * （「招式表子式（conf=ok）」→「招式表子式（确证）」）。其余文本原样透出。
 */
export function scrubTierNote(text?: string | null): string {
  return (text ?? '').replace(/\bconf\s*=\s*(strong|ok|weak)\b/gi, (_, t: string) => tierLabel(t.toLowerCase()));
}
