/**
 * 展示层共享工具（display-canonical-v1，B-1/B-2）——纯函数、零数据依赖，客户端岛可安全引用。
 *
 * 纪律（Lead 任务口径）：
 *   - display 只用于**展示文案**（标题/列表/搜索提示/面包屑/事件流人名）；
 *   - URL slug、内部 key、链接参数、数据匹配一律保持 **canonical**；
 *   - 未登记映射的实体 display == canonical（回落，不报错）。
 */
export type DisplayMap = Record<string, string>;

/** canonical → display；未登记返回原名。 */
export function dsp(map: DisplayMap | null | undefined, name: string | null | undefined): string {
  if (!name) return '';
  return (map && map[name]) || name;
}

/** 文本批量替换：把已知 canonical 名替换为 display（长名优先，防子串误替）。 */
export function dspText(map: DisplayMap | null | undefined, text: string | null | undefined): string {
  if (!text) return text || '';
  if (!map) return text;
  let out = text;
  for (const key of Object.keys(map).sort((a, b) => b.length - a.length)) {
    const val = map[key];
    if (val && val !== key) out = out.split(key).join(val);
  }
  return out;
}

export interface DisplayLookup {
  /** canonical → display（仅非恒等映射） */
  display: DisplayMap;
  /** display → canonical（反向归一；同一 display 多 canonical 时取首个） */
  canonicalOf: Record<string, string>;
  /** W0-T5 存目守卫：有主档页的人物 canonical 集（entity-index page!==false 的 @ 条目）。
   *  与构建期 @lib/scope isMainDossier 同语义；经 isMainPerson() 消费（fail-open）。 */
  mainPersons?: Set<string>;
}

/** 从带 c/canonical + display/display_name 字段的实体列表构建双向查找表。 */
export function buildDisplayLookup(entities: Array<Record<string, unknown>>): DisplayLookup {
  const display: DisplayMap = {};
  const canonicalOf: Record<string, string> = {};
  const mainPersons = new Set<string>();
  for (const e of entities || []) {
    const canonical = (e.c as string) || (e.canonical as string) || '';
    const disp = (e.display as string) || (e.display_name as string) || '';
    if (canonical && disp && disp !== canonical) {
      display[canonical] = disp;
      if (!(disp in canonicalOf)) canonicalOf[disp] = canonical;
    }
    // W0-T5：主档集收集。t 缺省按人物处理（dossiers.json 形态无 t）；page 缺省=有页
    // （全量口径回退兼容，与 @lib/scope 同语义）。
    const type = (e.t as string) || '@';
    if (canonical && type === '@' && e.page !== false) mainPersons.add(canonical);
  }
  return { display, canonicalOf, mainPersons };
}

/** W0-T5：canonical 是否有主档页（islands 运行时版，语义同 @lib/scope isMainDossier）。
 *  空集 fail-open（entity-index 未加载完/全量口径 page 缺省）——宁可暂多链，不误杀。 */
export function isMainPerson(
  lookup: DisplayLookup | null | undefined,
  canonical: string | null | undefined,
): boolean {
  if (!canonical) return false;
  const set = lookup?.mainPersons;
  if (!set || set.size === 0) return true;
  return set.has(canonical);
}

/** 输入归一：显示名/规范名 → 规范名（数据检索用 canonical）。 */
export function toCanonical(lookup: DisplayLookup | null | undefined, name: string): string {
  const n = (name || '').trim();
  if (!n || !lookup) return n;
  return lookup.canonicalOf[n] || n;
}

/**
 * 客户端岛运行时加载展示层映射（与构建期 @lib/display 同源：site/data/entity-index.json）。
 * 失败时回落空表（display==canonical），不影响功能。
 */
export async function fetchDisplayLookup(base: string): Promise<DisplayLookup> {
  const empty: DisplayLookup = { display: {}, canonicalOf: {} };
  try {
    if (typeof fetch !== 'function') return empty;
    const res = await fetch(`${base}data/entity-index.json`);
    if (!res.ok) return empty;
    const payload = await res.json();
    const entities = (payload && (payload.entities || payload.dossiers)) || [];
    return buildDisplayLookup(entities);
  } catch {
    return empty;
  }
}

