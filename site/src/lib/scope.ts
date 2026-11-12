/**
 * 站点口径唯一来源（天山演示版总体方案 §5.4 / §二，W0-T5 2026-11-08）。
 *
 * 构建期只读 site/data 两处口径事实：
 *   - books.json meta.scope —— 当前书目范围（scope profile 名 + books 数组）；
 *   - entity-index.json meta.major_rule + entities[].page —— 主档规则与主档/存目标志。
 *
 * 纪律：
 *   - 构建期代码（@lib/links、页面 getStaticPaths、统计文案）判"是否主档/在 scope"
 *     一律经本模块，不得各自直读 entity-index；
 *   - islands（运行时）不得 import 本模块（会把全量 JSON 打进 bundle，宪法同 @lib/links）——
 *     运行时等价实现在 @lib/display-shared 的 mainPersons / isMainPerson，语义与本处一致。
 *
 * 全量口径兼容（方案 R6）：page 字段缺省 = 有页；scope 键缺省 = 全量书目——
 * 回退全量导出后本模块自动退化为"全部可链"，无需改代码。
 */
import booksJson from '@data/books.json';
import entityIndex from '@data/entity-index.json';

const BOOKS_META = ((booksJson as any).meta || {}) as {
  scope?: string | { scope?: string; books?: string[] };
};
const SCOPE_META = BOOKS_META.scope;

/** scope 书目（books.json meta.scope.books；缺省回落 = books.json 现载全部书目）。 */
export const SCOPE_BOOKS: string[] =
  Array.isArray((SCOPE_META as any)?.books) && (SCOPE_META as any).books.length > 0
    ? ((SCOPE_META as any).books as string[])
    : (((booksJson as any).books || [])
        .map((b: any) => b?.book)
        .filter((x: unknown): x is string => typeof x === 'string' && !!x));

/** scope profile 名（如 "tianshan-demo"；null = 全量口径）。 */
export const SCOPE_PROFILE: string | null =
  typeof SCOPE_META === 'string'
    ? SCOPE_META
    : ((SCOPE_META as any)?.scope as string | undefined) ?? null;

/** scope profile → 用户可见名（演示口径括注用；未登记的 profile 原样展示）。 */
const SCOPE_PROFILE_LABELS: Record<string, string> = {
  'tianshan-demo': '天山系列',
};

/** 演示口径括注（如 "天山系列 7 部"；null = 全量口径，页面不显示括注）。
 *  用户可见 scope 文案的唯一来源——页面不得自行判 profile 或拼书目数（P0-3）。 */
export const SCOPE_NOTE: string | null = SCOPE_PROFILE
  ? `${SCOPE_PROFILE_LABELS[SCOPE_PROFILE] ?? SCOPE_PROFILE} ${SCOPE_BOOKS.length} 部`
  : null;

/** 主档规则（entity-index meta.major_rule；全量口径下为 null）。 */
export const MAIN_RULE: {
  min_total?: number;
  content_bearing?: boolean;
  scope?: string;
} | null = ((entityIndex as any).meta?.major_rule ?? null) as typeof MAIN_RULE;

/** 主档 canonical 集：entity-index entities 中 t==='@' 且 page !== false 者（存目被排除）。 */
const MAIN_PERSONS: Set<string> = new Set(
  (((entityIndex as any).entities || []) as Array<Record<string, unknown>>)
    .filter((e) => e?.t === '@' && e.page !== false && typeof e.c === 'string' && e.c)
    .map((e) => e.c as string),
);

/** 该 canonical 是否有主档页（entity-index page 字段口径）。
 *  空集 fail-open（数据缺失/全量口径回退时不误伤，宁可多链不误杀）。 */
export function isMainDossier(canonical: unknown): boolean {
  if (typeof canonical !== 'string' || !canonical) return false;
  if (MAIN_PERSONS.size === 0) return true;
  return MAIN_PERSONS.has(canonical);
}
