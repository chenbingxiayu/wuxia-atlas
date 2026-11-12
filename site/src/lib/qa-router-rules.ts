/**
 * qa-router-rules —— 问答页规则式自然语言路由（决策 5：只有路由、无生成，零幻觉纪律不破）。
 *
 * 设计：《问答页重构设计.md》§五（模板路由器）·§九（文案稿）+ 总体方案 §3.2 问答行。
 * 形态：ROUTES 有序规则表（越靠前优先级越高——多实体规则 > 单实体模板规则）；
 *       route(text, resolve?) 依次尝试，命中即返回 { template, x, y?, ruleId }，全 miss 返回 null。
 * 实体抽取：
 *   - 多实体规则用捕获组（「X 和 Y 交过手吗 / X 和 Y 什么关系」）；
 *   - 单实体规则剥掉命中关键词 → 清洗疑问词/语助词（NOISE）→ 交注入的 resolve() 归一；
 *   - resolve() 由 QaExplorer 注入（toCanonical 归一 + 残留串内"多词取最长命中"）；
 *     归一失败返回原串——既有"档案未载"路径兜底，不阻断查询。
 * 纪律：路由只分发模板 id 与实体参数，不生成任何答案文本。
 */

export interface RouteHit {
  /** 模板 id（与 QaExplorer TPLS 一致：killer/chaps/lineage/sectarts/versus/artifact/places） */
  template: string;
  /** 主实体（原始串，经 resolve 归一后回填） */
  x: string;
  /** 副实体（仅多实体规则；lineage 的 y 保留但当前求解只消费 x） */
  y?: string;
  /** 命中的规则 id（调试/自检用） */
  ruleId: string;
}

type Resolve = (raw: string) => string;
type Extract = (m: RegExpMatchArray, text: string, resolve: Resolve) => RouteHit | null;

interface RouteRule {
  id: string;
  template: string;
  pattern: RegExp;
  extract: Extract;
}

/**
 * 疑问词/语助词清洗（残留串用）。刻意保守——语料人名含「了因/了缘」「红衣喇嘛」
 * 「八臂哪吒」，故 了/嘛/哪/查/看 等字不进清洗集；「的」只剥首尾（人名「周掌柜的老婆」含内部"的"）。
 */
const NOISE =
  /(哪些地方|什么地方|哪些|哪里|什么|怎么|怎样|如何|请问|告诉|知道|想问|多少|几回|出场|登场|[谁吗呢吧啊呀]|[？?！!。，、·\s"“”‘’「」『』])+/g;

/** 清洗疑问词残留 + 首尾"的"。 */
export function cleanResidual(s: string): string {
  return s.replace(NOISE, '').replace(/^的+/, '').replace(/的+$/, '').trim();
}

/** 单实体规则：剥掉命中关键词 → 清洗 → resolve 归一；抽不出实体返回 null（回落"没听懂"）。 */
function mono(id: string, template: string, pattern: RegExp): RouteRule {
  return {
    id,
    template,
    pattern,
    extract: (m, text, resolve) => {
      const residual = cleanResidual(text.replace(m[0], ''));
      if (!residual) return null;
      const x = resolve(residual);
      return x ? { template, x, ruleId: id } : null;
    },
  };
}

/** 双实体规则：捕获组 1/2 即 X/Y（清洗 + 归一）；任一为空返回 null。 */
function pair(id: string, template: string, pattern: RegExp): RouteRule {
  return {
    id,
    template,
    pattern,
    extract: (m, _text, resolve) => {
      const xr = cleanResidual(m[1] || '');
      const yr = cleanResidual(m[2] || '');
      if (!xr || !yr) return null;
      const x = resolve(xr);
      const y = resolve(yr);
      if (!x || !y) return null;
      return { template, x, y, ruleId: id };
    },
  };
}

/**
 * versus 单实体兜底：「交手/打过/对战」无「和」连接时，从残留串按连接词拆对；
 * 拆不出双方返回 null（versus 必须双方，缺方回落提示而非硬查）。
 */
function pairMono(id: string, template: string, pattern: RegExp): RouteRule {
  return {
    id,
    template,
    pattern,
    extract: (m, text, resolve) => {
      const residual = cleanResidual(text.replace(m[0], ''));
      if (!residual) return null;
      const parts = residual.split(/(?:和|与|跟)/).map((p) => p.trim()).filter(Boolean);
      if (parts.length !== 2) return null;
      const x = resolve(parts[0]);
      const y = resolve(parts[1]);
      if (!x || !y) return null;
      return { template, x, y, ruleId: id };
    },
  };
}

/**
 * 路由规则表（有序，先匹配先赢）。关键词域照设计 §6.2 规则表：
 * 谁(杀了|刺了|害了|击杀)→killer · (去过|行踪|到过|走过)→places · (什么关系|关系|恋人|师徒|仇敌)→lineage
 * (交手|打过|对战)→versus · (师承|传人|徒弟|师父)→lineage · 什么武功|有哪些武功→sectarts · (神兵|持物|兵器)→artifact
 * 附加：多实体 versus/lineage（置顶，优先于单实体）；chaps（哪几回出场，模板已有）。
 */
export const ROUTES: RouteRule[] = [
  pair('vs-pair', 'versus', /(.+?)(?:和|与|跟)(.+?)(?:交过手|交手|打过|对战|动过手|过招)/),
  pair('kin-pair', 'lineage', /(.+?)(?:和|与|跟)(.+?)(?:什么关系|什么交情|交情|关系)/),
  mono('killer', 'killer', /谁(?:杀了|刺死了|杀死|刺了|害了|击杀了|击杀)|凶手(?:是谁)?/),
  mono('places', 'places', /(?:去过|行踪|到过|走过|行经)/),
  mono('kinship', 'lineage', /(?:师承|传人|徒弟|师父|师傅|师祖|师门|拜师|什么关系|恋人|师徒|仇敌|关系)/),
  pairMono('vs-solo', 'versus', /(?:交手|打过|对战|动过手|过招)/),
  mono('sectarts', 'sectarts', /(?:有|的)?(?:什么|哪些)武功/),
  mono('artifact', 'artifact', /(?:神兵|持物|兵器|武器)/),
  mono('chaps', 'chaps', /(?:在哪几回|哪几回|哪些回|出场)/),
];

/**
 * 自然语言路由：命中返回 { template, x, y? , ruleId }，未命中返回 null（QaExplorer 回落
 * 模板选择器 + 「没听懂」提示）。resolve 缺省为恒等（纯文本测试用）。
 */
export function route(text: string, resolve?: Resolve): RouteHit | null {
  const q = (text || '').trim();
  if (!q) return null;
  const rs: Resolve = resolve || ((s: string) => s);
  for (const r of ROUTES) {
    const m = q.match(r.pattern);
    if (!m) continue;
    const hit = r.extract(m, q, rs);
    if (hit && hit.x) return hit;
  }
  return null;
}
