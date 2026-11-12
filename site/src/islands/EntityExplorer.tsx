import { useMemo, useState } from 'react';

export interface Ent {
  t: string;                       // '@'人物 | '☆'武功 | '◆'门派组织
  c: string;                       // 规范名（内部 key / URL slug，保持 canonical）
  display?: string;                // 展示名（display-canonical-v1；缺省回落 canonical）
  n: number;                       // 总频次
  b: Record<string, number>;       // 逐书频次
  x: boolean;                      // 跨书
  aliases?: { alias: string; count: number }[]; // W2-A1 别名频次表（entity-index aliases；-count 排序）
  page?: boolean;                  // W0-T5 主档/存目标志（entity-index page；缺省=有页，全量口径兼容）
}

const TYPE_LABEL: Record<string, string> = { '@': '人物', '☆': '武功', '◆': '门派组织' };
// 部署在项目子路径下：内部链接统一带 base 前缀
const RAW = import.meta.env.BASE_URL || '/';
const B = RAW.endsWith('/') ? RAW : RAW + '/';
const BASE: Record<string, string> = { '@': B + 'characters/', '☆': B + 'arts/', '◆': B + 'sects/' };
const PAGE_SIZE = 300;
const MAJOR_N = 100; // 阈值可调：提及频次 ≥100 的人物记为「主要人物」

/** 展示名：display 优先，缺省回落 canonical（展示层，B-1/B-2）。 */
const shown = (e: Ent) => e.display || e.c;
/** 别名表：entity-index aliases（W2-A1；缺省空表，全量口径旧数据兼容）。 */
const aliasNames = (e: Ent) => (e.aliases || []).map((a) => a.alias);

/**
 * W2-A1：q 经「别名」命中（规范名/展示名未命中时）返回该别名——
 * 用于 chip 小字展示匹配到的别名（搜「玉罗刹」→ 练霓裳 chip 标注 别名·玉罗刹）。
 */
function aliasHit(e: Ent, q: string): string | undefined {
  if (!q) return undefined;
  if (shown(e).includes(q) || e.c.includes(q)) return undefined;
  return (e.aliases || []).find((a) => a.alias.includes(q))?.alias;
}

export default function EntityExplorer({
  entities,
  initialType = '@',
}: {
  entities: Ent[];
  initialType?: string;
}) {
  const [q, setQ] = useState('');
  const [type, setType] = useState(initialType);
  const [crossOnly, setCrossOnly] = useState(false);
  const [showAll, setShowAll] = useState(false); // T14/A9：默认主要人物视图；勾选后全量平铺
  const [limit, setLimit] = useState(PAGE_SIZE);

  // 分层计数（T14/A9）：按当前类目结构统计，不随搜索/跨书开关收窄
  const counts = useMemo(
    () => ({
      total: entities.filter((e) => e.t === type).length,
      major: entities.filter((e) => e.t === type && e.n >= MAJOR_N).length,
    }),
    [entities, type],
  );

  const list = useMemo(() => {
    const rows = entities.filter(
      (e) =>
        e.t === type &&
        (!crossOnly || e.x) &&
        // 搜索匹配展示名、规范名与别名（W2-A1：entity-index aliases，输入"玉罗刹/白发魔女/
        // 晦明禅师"能命中练霓裳/岳鸣珂等规范档案；武功/门派 tab 同样吃 aliases）
        (!q || shown(e).includes(q) || e.c.includes(q) ||
          (e.aliases !== undefined && e.aliases.some((al) => al.alias.includes(q)))) &&
        // 分层（T14/A9）：默认只列主要人物（n≥MAJOR_N）；搜索时覆盖全部，不因分层收窄
        (type !== '@' || q !== '' || showAll || e.n >= MAJOR_N),
    );
    // 主要人物视图按提及频次降序；「显示全部」平铺保持数据原序
    return type !== '@' || showAll ? rows : rows.slice().sort((a, b) => b.n - a.n);
  }, [entities, type, q, crossOnly, showAll]);
  const shownList = list.slice(0, limit);

  return (
    <div className="explorer">
      <div className="bar">
        <div className="tabs">
          {['@', '☆', '◆'].map((t) => (
            <button
              key={t}
              className={t === type ? 'tab on' : 'tab'}
              onClick={() => { setType(t); setLimit(PAGE_SIZE); }}
            >
              {TYPE_LABEL[t]}（{entities.filter((e) => e.t === t).length}）
            </button>
          ))}
        </div>
        <input
          value={q}
          placeholder="输入名称或别名筛选…"
          onChange={(e) => { setQ(e.target.value); setLimit(PAGE_SIZE); }}
        />
        <label className="cross">
          <input type="checkbox" checked={crossOnly} onChange={(e) => { setCrossOnly(e.target.checked); setLimit(PAGE_SIZE); }} />
          只看跨书
        </label>
        {type === '@' && (
          <label className="cross">
            <input type="checkbox" checked={showAll} onChange={(e) => { setShowAll(e.target.checked); setLimit(PAGE_SIZE); }} />
            显示全部（{counts.total} 位）
          </label>
        )}
      </div>
      <p className="meta">
        {type === '@' && <>主要人物 {counts.major} · 其余 {counts.total - counts.major} — </>}
        {list.length} 条{list.length > shownList.length ? `，显示前 ${shownList.length}（继续筛选缩小范围）` : ''}
      </p>
      <div className="chips">
        {shownList.map((e) => {
          // W0-T5 存目守卫（方案 §2.3）：人物 page=false → 不可点灰 chip（无页，防 404），
          // tooltip 承担"存目 · 出场 N 次"对质信息；武功/门派全有页不受影响。
          const toc = e.t === '@' && e.page === false;
          const names = aliasNames(e);
          const aliasNote = names.length ? ` · 又名 ${names.slice(0, 4).join('、')}` : '';
          // W2-A1：经别名命中的 chip → 高亮 + 小字标注匹配到的别名
          const hit = aliasHit(e, q);
          const cls = 'chip' + (e.x ? ' cross' : '') + (hit ? ' ahit' : '');
          if (toc) {
            return (
              <span
                key={e.t + e.c}
                className={cls + ' toc'}
                title={`存目 · 出场 ${e.n} 次${aliasNote}`}
                style={{ fontSize: e.n > 800 ? '1rem' : '.88rem' }}
              >
                {shown(e)}
                <small>×{e.n}</small>
                {hit && <small className="ahit-note">别名·{hit}</small>}
                <em>存目</em>
              </span>
            );
          }
          return (
            <a
              key={e.t + e.c}
              className={cls}
              href={BASE[e.t] + encodeURIComponent(e.c) + '/'}
              title={names.length ? `规范名：${e.c} · 又名 ${names.slice(0, 4).join('、')}` : `规范名：${e.c}`}
              style={{ fontSize: e.n > 800 ? '1rem' : '.88rem' }}
            >
              {shown(e)}
              <small>×{e.n}</small>
              {hit && <small className="ahit-note">别名·{hit}</small>}
              {e.x && <em>换乘</em>}
            </a>
          );
        })}
        {shownList.length === 0 && <p className="meta">无匹配结果。</p>}
      </div>
    </div>
  );
}
