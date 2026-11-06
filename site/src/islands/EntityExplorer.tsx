import { useMemo, useState } from 'react';

export interface Ent {
  t: string;                       // '@'人物 | '☆'武功 | '◆'门派组织
  c: string;                       // 规范名（内部 key / URL slug，保持 canonical）
  display?: string;                // 展示名（display-canonical-v1；缺省回落 canonical）
  n: number;                       // 总频次
  b: Record<string, number>;       // 逐书频次
  x: boolean;                      // 跨书
}

const TYPE_LABEL: Record<string, string> = { '@': '人物', '☆': '武功', '◆': '门派组织' };
// 部署在项目子路径下：内部链接统一带 base 前缀
const RAW = import.meta.env.BASE_URL || '/';
const B = RAW.endsWith('/') ? RAW : RAW + '/';
const BASE: Record<string, string> = { '@': B + 'characters/', '☆': B + 'arts/', '◆': B + 'sects/' };
const PAGE_SIZE = 300;

/** 展示名：display 优先，缺省回落 canonical（展示层，B-1/B-2）。 */
const shown = (e: Ent) => e.display || e.c;

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
  const [limit, setLimit] = useState(PAGE_SIZE);

  const list = useMemo(
    () =>
      entities.filter(
        (e) =>
          e.t === type &&
          (!crossOnly || e.x) &&
          // 搜索同时匹配展示名与规范名（输入 canonical 也能搜到；匹配逻辑不改变 URL）
          (!q || shown(e).includes(q) || e.c.includes(q)),
      ),
    [entities, type, q, crossOnly],
  );
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
          placeholder="输入名称筛选…"
          onChange={(e) => { setQ(e.target.value); setLimit(PAGE_SIZE); }}
        />
        <label className="cross">
          <input type="checkbox" checked={crossOnly} onChange={(e) => { setCrossOnly(e.target.checked); setLimit(PAGE_SIZE); }} />
          只看跨书
        </label>
      </div>
      <p className="meta">
        {list.length} 条{list.length > shownList.length ? `，显示前 ${shownList.length}（继续筛选缩小范围）` : ''}
      </p>
      <div className="chips">
        {shownList.map((e) => (
          <a
            key={e.t + e.c}
            className={e.x ? 'chip cross' : 'chip'}
            href={BASE[e.t] + encodeURIComponent(e.c) + '/'}
            title={`规范名：${e.c}`}
            style={{ fontSize: e.n > 800 ? '1rem' : '.88rem' }}
          >
            {shown(e)}
            <small>×{e.n}</small>
            {e.x && <em>换乘</em>}
          </a>
        ))}
        {shownList.length === 0 && <p className="meta">无匹配结果。</p>}
      </div>
    </div>
  );
}
