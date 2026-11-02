import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

/**
 * MapTrail —— 时空页交互岛（M6 · jiangshan 形态）。
 * 数据：/data/atlas/state.json（书目清单+年代） + /data/atlas/{书}.json（人-回-地共现+事件，懒加载）
 *       + /public/geo/china-provinces.json（真实省界底图，DataV GeoAtlas，GCJ-02；站点内
 *         WGS-84 坐标直接叠加——全国视野下 ~500m 系统差 < 0.1px，无须纠偏，见实现设计 §2.3）。
 * 交互：回目滑块（已至/未至/当前三态轨迹）· 编年播放 · 人物多选 · 虚实透镜 · 幽灵对比 ·
 *       地名谱系卡（Trace Place）· 内联江湖状态 · URL 深链（?book&chap&person&place&mode&lens）。
 * 版权：全部 L0 图谱层（定位符/结构化事实），不含摘录。
 */

type Chaps = number[];
interface Person { n: number; chaps: Chaps }
interface Place {
  real?: boolean | null; lat?: number; lng?: number; precision?: string;
  chaps: Chaps; aliases?: string[];
}
interface Ev { l: string; v: string; a?: string | null; b?: string | null; code?: string; conf?: string }
interface BookSlice {
  title: string; era?: string; era_conf?: string; chapters: number;
  persons: Record<string, Person>;
  places: Record<string, Place>;
  bychap: Record<string, { p: string[]; l: string[] }>;
  events: Record<string, Ev[]>;
}
interface Manifest {
  meta: { note: string };
  books: { slug: string; title: string; chapters: number; era?: string; leads: string[] }[];
}
interface GeoFeat { geometry: { type: string; coordinates: unknown } }

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';
const PALETTE = ['#a23527', '#31536c', '#4f6e4a', '#8a6607'];
const W = 1000, H = 760, PAD = 30;

/* Mercator（自实现，免依赖）：x = λ，y = ln tan(π/4 + φ/2)，再线性拟合到画布 */
const mx = (lng: number) => (lng * Math.PI) / 180;
const my = (lat: number) => Math.log(Math.tan(Math.PI / 4 + ((lat * Math.PI) / 180) / 2));
type Proj = (lng: number, lat: number) => [number, number];
function fitProjection(pts: [number, number][]): Proj {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const [lng, lat] of pts) {
    const x = mx(lng), y = my(lat);
    if (x < x0) x0 = x; if (x > x1) x1 = x;
    if (y < y0) y0 = y; if (y > y1) y1 = y;
  }
  const s = Math.min((W - PAD * 2) / (x1 - x0), (H - PAD * 2) / (y1 - y0));
  const ox = (W - s * (x1 - x0)) / 2 - s * x0;
  const oy = (H - s * (y1 - y0)) / 2 + s * y1;
  return (lng, lat) => [s * mx(lng) + ox, oy - s * my(lat)];
}
function ringsToPath(geom: { type: string; coordinates: unknown }, proj: Proj): string {
  const polys: number[][][][] =
    geom.type === 'Polygon' ? [geom.coordinates as number[][][]] : (geom.coordinates as number[][][][]);
  let d = '';
  for (const poly of polys) {
    for (const ring of poly) {
      ring.forEach(([lng, lat], i) => {
        const [x, y] = proj(lng, lat);
        d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
      });
      d += 'Z';
    }
  }
  return d;
}

export default function MapTrail() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [bookTitle, setBookTitle] = useState<string>('');
  const [slice, setSlice] = useState<BookSlice | null>(null);
  const [chap, setChap] = useState(1);
  const [ghostChap, setGhostChap] = useState(1);
  const [ghostOn, setGhostOn] = useState(false);
  const [dotMode, setDotMode] = useState<'cur' | 'all'>('cur');
  const [evCat, setEvCat] = useState('all');
  const [lens, setLens] = useState<'real' | 'fiction'>('real');
  const [persons, setPersons] = useState<string[]>([]);
  const [playing, setPlaying] = useState(false);
  const [selPlace, setSelPlace] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  /* 深链初始化 */
  useEffect(() => {
    const d: Record<string, string> = {};
    new URLSearchParams(location.search).forEach((v, k) => (d[k] = v));
    fetch(B + 'data/atlas/state.json')
      .then((r) => r.json())
      .then((m: Manifest) => {
        setManifest(m);
        const pick = d.book && m.books.find((b) => b.title === d.book);
        setBookTitle(pick ? pick.title : m.books.find((b) => b.title === '白发魔女传')?.title || m.books[0].title);
      });
  }, []);

  /* 换书加载切片 */
  useEffect(() => {
    if (!bookTitle) return;
    setSlice(null);
    fetch(B + 'data/atlas/' + encodeURIComponent(bookTitle) + '.json')
      .then((r) => r.json())
      .then((s: BookSlice) => {
        setSlice(s);
        const q = new URLSearchParams(location.search);
        const initChap = q.get('chap') ? +q.get('chap')! : bookTitle === '白发魔女传' ? 26 : Math.ceil(s.chapters / 2);
        setChap(Math.min(Math.max(1, initChap), s.chapters));
        const ps = (q.get('person') || '').split(',').filter((p) => s.persons[p]);
        setPersons(ps.length ? ps : [suggestedPerson(s, manifest)]);
        setLens(q.get('lens') === 'fiction' ? 'fiction' : 'real');
        setGhostOn(q.get('mode') === 'ghost');
        setGhostChap(Math.max(1, Math.ceil(s.chapters / 4)));
        setSelPlace(q.get('place') && s.places[q.get('place')!] ? q.get('place') : null);
      });
  }, [bookTitle, manifest]);

  /* 深链回写（replaceState：不污染历史栈） */
  useEffect(() => {
    if (!slice || !manifest) return;
    const q = new URLSearchParams();
    q.set('book', bookTitle);
    q.set('chap', String(chap));
    if (persons.length) q.set('person', persons.join(','));
    if (selPlace) q.set('place', selPlace);
    if (lens !== 'real') q.set('lens', lens);
    if (ghostOn) q.set('mode', 'ghost');
    history.replaceState(null, '', `${location.pathname}?${q.toString()}`);
  }, [slice, manifest, bookTitle, chap, persons, selPlace, lens, ghostOn]);

  /* 播放 */
  useEffect(() => {
    if (playing && slice) {
      timer.current = window.setInterval(() => {
        setChap((c) => {
          if (c >= slice.chapters) { setPlaying(false); return c; }
          return c + 1;
        });
      }, 800);
    }
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [playing, slice]);

  const [baseMap, setBaseMap] = useState<{ path: string }[]>([]);
  useEffect(() => {
    fetch(B + 'geo/china-provinces.json')
      .then((r) => r.json())
      .then((gj: { features: GeoFeat[] }) => {
        // 用底图外框定投影（真实经纬范围）
        const pts = collectPoints(gj.features);
        const p = fitProjection(pts);
        setBaseMap(gj.features.map((f) => ({ path: ringsToPath(f.geometry, p) })));
        projRef.current = p;
      });
  }, []);
  const projRef = useRef<Proj | null>(null);

  if (!manifest || !slice || !projRef.current) {
    return <div className="mt-loading">时空数据加载中……（底图 / 人-回-地切片）</div>;
  }
  const proj = projRef.current;
  const chapStr = String(chap);
  const cur = slice.bychap[chapStr] || { p: [], l: [] };

  /* 轨迹计算：人物 P 已至节点 = Σ{ c ≤ chap : P∈bychap[c].p } 的地点；未至 = 其余同现点 */
  const trails = persons.map((pid, i) => {
    const person = slice.persons[pid];
    if (!person) return null;
    const visited = new Map<string, number[]>();
    const future = new Set<string>();
    const order: string[] = [];
    for (const c of person.chaps) {
      const placesHere = (slice.bychap[String(c)] || { l: [] }).l;
      for (const pl of placesHere) {
        if (c <= chap) {
          if (!visited.has(pl)) { visited.set(pl, []); order.push(pl); }
          visited.get(pl)!.push(c);
        } else future.add(pl);
      }
    }
    return { pid, color: PALETTE[i % PALETTE.length], visited, future, order };
  }).filter(Boolean) as Trail[];

  /* 幽灵对比：选中人物在 A、B 两回的人-地在场集合差 */
  const ghost = ghostOn ? (() => {
    const pairsAt = (c: number) => {
      const s = new Set<string>();
      const slot = slice.bychap[String(c)];
      if (!slot) return s;
      for (const pid of persons) if (slot.p.includes(pid)) slot.l.forEach((l) => s.add(pid + '|' + l));
      return s;
    };
    const A = pairsAt(chap), Bset = pairsAt(ghostChap);
    const added = [...Bset].filter((x) => !A.has(x)).map((x) => x.split('|')[1]);
    const removed = [...A].filter((x) => !Bset.has(x)).map((x) => x.split('|')[1]);
    return { added: [...new Set(added)], removed: [...new Set(removed)] };
  })() : null;

  const evList = slice.events[chapStr] || [];
  const evShown = evCat === 'all' ? evList : evCat === 'other'
    ? evList.filter((e) => !['◈', '◉', '▲', '◇', '○'].includes(e.code || ''))
    : evList.filter((e) => e.code === evCat);
  const trailSummary = (slice.bychap[chapStr] || { p: [], l: [] }).l.length
    ? (slice.events[chapStr] || []).map((e) => (e as { place?: string }).place).filter(Boolean)
        .filter((v, i, arr) => arr.indexOf(v) === i).join(' → ') || '本章无定位事件地点'
    : '—';
  const placeEntry = selPlace ? slice.places[selPlace] : null;
  const gazPlace = placeEntry ? { real: placeEntry.real, lat: placeEntry.lat, lng: placeEntry.lng, precision: placeEntry.precision } : null;

  return (
    <div className="mt-root">
      {/* 控制台 */}
      <div className="mt-panel">
        <div className="mt-row">
          <span className="mt-lab">书目</span>
          {manifest.books.map((b) => (
            <button key={b.slug} className={'mt-chip' + (b.title === bookTitle ? ' on' : '')}
              onClick={() => { setBookTitle(b.title); setSelPlace(null); }}>{b.title}</button>
          ))}
          <span className="mt-lab" style={{ marginLeft: 14 }}>视角</span>
          <button className={'mt-chip' + (lens === 'real' ? ' on' : '')} onClick={() => setLens('real')}>真实地理</button>
          <button className={'mt-chip' + (lens === 'fiction' ? ' on' : '')} onClick={() => setLens('fiction')}>虚构安放</button>
        </div>
        <div className="mt-row">
          <span className="mt-lab">回目</span>
          <input type="range" min={1} max={slice.chapters} value={chap}
            onChange={(e) => setChap(+e.target.value)} className="mt-slider" aria-label="回目滑块" />
          <b className="mt-chapno">第 {chap} 回</b>
          <button className="mt-play" onClick={() => setPlaying(!playing)}>{playing ? '⏸ 暂停' : '▶ 编年播放'}</button>
          {ghostOn && (
            <>
              <span className="mt-lab">对比回</span>
              <input type="range" min={1} max={slice.chapters} value={ghostChap}
                onChange={(e) => setGhostChap(+e.target.value)} className="mt-slider" aria-label="幽灵对比回目" />
              <b className="mt-chapno">第 {ghostChap} 回</b>
            </>
          )}
          <button className={'mt-chip' + (ghostOn ? ' on' : '')} style={{ marginLeft: 'auto' }}
            onClick={() => setGhostOn(!ghostOn)} title="比较两回之间谁到访、谁离开">幽灵对比</button>
        </div>
        <div className="mt-row">
          <span className="mt-lab">侠客</span>
          {Object.entries(slice.persons).slice(0, 14).map(([pid]) => (
            <button key={pid}
              className={'mt-chip' + (persons.includes(pid) ? ' on' : '')}
              style={persons.includes(pid) ? { borderColor: PALETTE[persons.indexOf(pid) % 4], color: PALETTE[persons.indexOf(pid) % 4] } : {}}
              onClick={() => setPersons((ps) => ps.includes(pid) ? ps.filter((x) => x !== pid) : [...ps, pid])}>
              {pid}
            </button>
          ))}
        </div>
      </div>

      {/* 地图 */}
      <div className="mt-mapcard">
        <svg viewBox={`0 0 ${W} ${H}`} className="mt-svg" role="img" aria-label={`${bookTitle} 行踪地图（第 ${chap} 回）`}>
          {baseMap.map((f, i) => (
            <path key={i} d={f.path} fill="#efe7d4" stroke="#d8cdb4" strokeWidth="0.7" />
          ))}
          {/* 轨迹连线 + 节点 */}
          {trails.map((t) => {
            let d = '';
            let prev: [number, number] | null = null;
            for (const pl of t.order) {
              const p = slice.places[pl];
              if (!p?.lat || lens !== 'real') continue;
              const xy = proj(p.lng!, p.lat!);
              if (prev) d += `M${prev[0]} ${prev[1]}L${xy[0]} ${xy[1]}`;
              prev = xy;
            }
            return <path key={t.pid} d={d} fill="none" stroke={t.color} strokeWidth="1.6" strokeDasharray="5 4" opacity="0.75" />;
          })}
          {placeDots(slice, trails, lens, proj, chap, ghost, selPlace, setSelPlace, dotMode)}
        </svg>

        {/* 内联江湖状态 */}
        <div className="mt-state">
          <b>{bookTitle} · 第 {chap} 回</b>
          <span>时期：{slice.era || '元数据待考'}{slice.era_conf === 'todo' ? '（待考）' : ''}</span>
          <span>在场人物 {cur.p.length} · 地点 {cur.l.length} · 事件 {evList.length} 起</span>
          <span className="mt-faint">掌门世系 · 待工具 B 世系表接入</span>
        </div>

        {/* 地名谱系卡 */}
        {placeEntry && selPlace && (
          <div className="mt-trace">
            <div className="mt-trace-h">
              <b>{selPlace}</b>
              {gazPlace?.real === true && <span className="mt-badge mt-ok">真实地理</span>}
              {gazPlace?.real === false && <span className="mt-badge mt-fic">虚构 · 待锚定</span>}
              {placeEntry.aliases && placeEntry.aliases.length > 0 && (
                <span className="mt-faint">别名 {placeEntry.aliases.slice(0, 3).join(' / ')}</span>
              )}
              <button className="mt-x" onClick={() => setSelPlace(null)} aria-label="关闭">×</button>
            </div>
            {gazPlace?.real === true && gazPlace.lat != null && (
              <div className="mt-coord mono">{gazPlace.lat.toFixed(4)}°N, {gazPlace.lng!.toFixed(4)}°E
                <span className="mt-faint"> · {gazPlace.precision === 'exact' ? '精确落点' : '近似/待核验'} · OSM/人工核验</span>
              </div>
            )}
            <div className="mt-trace-rows">
              {placeEntry.chaps.slice(0, 8).map((c) => {
                const ppl = (slice.bychap[String(c)] || { p: [] }).p.slice(0, 6);
                return (
                  <div className="mt-trow" key={c}>
                    <a className="mt-link mono" href={`${B}books/${encodeURIComponent(bookTitle)}/${c}`}>
                      第 {c} 回 →
                    </a>
                    <span className="mt-faint">{ppl.length ? '在场 ' + ppl.join(' · ') : ''}</span>
                  </div>
                );
              })}
              {placeEntry.chaps.length > 8 && (
                <div className="mt-faint">…共 {placeEntry.chaps.length} 回（跨书沿革待多书联查）</div>
              )}
            </div>
          </div>
        )}

        {/* 图例 */}
        <div className="mt-legend">
          <span><i className="dot" style={{ background: '#a23527' }} />已至（≤ 当前回）</span>
          <span><i className="dot hollow" />未至节点</span>
          {ghostOn && <span><i className="dot" style={{ background: '#4f6e4a' }} />B 回新到</span>}
          {ghostOn && <span><i className="dot" style={{ background: '#8a8172' }} />A 回后离开</span>}
          <span className="mt-faint" style={{ marginLeft: 'auto' }}>
            底图：DataV GeoAtlas（真实省界）· 坐标：OSM/人工核验（WGS-84）· 虚构地名按考订锚点安放
          </span>
        </div>
      </div>

      <style>{`
        .mt-trail { font-size: 13.5px; color: #31536c; }
        .mt-place-tag { color: #8a6607; font-size: 12px; }
      `}</style>
      {/* 本回事件流 */}
      <div className="mt-panel">
        <div className="mt-row" style={{ alignItems: 'baseline' }}>
          <b>第 {chap} 回事件流</b>
          <span className="mt-faint">{evList.length} 起 · L0 定位符</span>
          <a className="mt-link" style={{ marginLeft: 'auto' }}
            href={`${B}books/${encodeURIComponent(bookTitle)}/${chap}`}>回目页 →</a>
        </div>
        <div className="mt-row">
          <span className="mt-lab">本章行踪：</span>
          <span className="mt-trail">{trailSummary || '—'}</span>
        </div>
        <div className="mt-row">
          <span className="mt-lab">类型</span>
          {[['all', '全部'], ['◈', '交战'], ['◉', '杀伐'], ['▲', '擒控'], ['◇', '传艺'], ['○', '结盟拜认'], ['other', '其他']].map(([k, lab]) => (
            <button key={k} className={'mt-chip' + (evCat === k ? ' on' : '')} onClick={() => setEvCat(k)}>
              {lab}<small>{k === 'all' ? evList.length : catCount(evList, k)}</small>
            </button>
          ))}
        </div>
        <div className="mt-evgrid">
          {evShown.slice(0, 12).map((e, i) => (
            <div className="mt-ev" key={i}>
              <span className="mt-verb">{e.v || e.code}</span>
              <span className="mt-who">{e.a || '？'}</span>
              {e.b && <>→ <span className="mt-who">{e.b}</span></>}
              {e.place && <span className="mt-place-tag">@{e.place}</span>}
              <span className="mt-loc mono">{e.l}</span>
            </div>
          ))}
          {evShown.length > 12 && <div className="mt-faint">…其余 {evShown.length - 12} 起见回目页</div>}
        </div>
      </div>
    </div>
  );
}

/* ---- 辅助 ---- */
interface Trail { pid: string; color: string; visited: Map<string, number[]>; future: Set<string>; order: string[] }

function suggestedPerson(s: BookSlice, manifest: Manifest | null): string {
  const book = manifest?.books.find((b) => b.title === s.title);
  if (book) for (const lead of book.leads) if (s.persons[canonLead(lead)]) return canonLead(lead);
  return Object.keys(s.persons)[0];
}
function canonLead(name: string) { return name; }

function collectPoints(feats: GeoFeat[]): [number, number][] {
  const out: [number, number][] = [];
  const push = (c: unknown) => {
    if (typeof c?.[0] === 'number') out.push(c as [number, number]);
    else if (Array.isArray(c)) c.forEach(push);
  };
  feats.forEach((f) => push(f.geometry.coordinates));
  return out;
}

function placeDots(
  slice: BookSlice, trails: Trail[], lens: 'real' | 'fiction', proj: Proj,
  chap: number, ghost: { added: string[]; removed: string[] } | null,
  selPlace: string | null, onSelect: (p: string) => void,
  dotMode: 'cur' | 'all',
) {
  const nodes: ReactNode[] = [];
  const visitedOf = (pl: string) => trails.filter((t) => t.visited.has(pl));
  const futureOf = (pl: string) => trails.some((t) => t.future.has(pl));
  const evsAt = (pl: string) => {
    const evs = slice.events[String(chap)] || [];
    return evs.filter((e) => (e as { place?: string }).place === pl).slice(0, 5);
  };
  const show = (pl: string) => {
    const p = slice.places[pl];
    if (!p) return false;
    if (lens === 'real') return p.real !== false && p.lat != null;
    return p.real === false; // 虚构层
  };
  const curPlaces = new Set((slice.bychap[String(chap)] || { l: [] }).l);
  for (const [pl, p] of Object.entries(slice.places)) {
    if (!show(pl) || p.lat == null) continue;
    const [x, y] = proj(p.lng!, p.lat!);
    const vis = visitedOf(pl);
    const isFuture = !vis.length && futureOf(pl);
    const isGhostAdd = ghost?.added.includes(pl);
    const isGhostRem = ghost?.removed.includes(pl);
    const curHere = curPlaces.has(pl);
    // 点位模式：cur = 只显当前回地点；all = 已至/未至全景
    const visible = dotMode === 'cur' ? curHere || pl === selPlace : vis.length > 0 || isFuture || curHere;
    if (!visible) continue;
    const evs = evsAt(pl);
    const tip = [
      pl + (p.lat != null ? `（${p.lat.toFixed(2)}, ${p.lng!.toFixed(2)}）` : ' · 虚构 · 待锚定'),
      ...evs.map((e) => `第${chap}回 ${e.v}：${e.a || '？'}${e.b ? ' → ' + e.b : ''}`),
      evs.length === 0 && curHere ? '第' + chap + '回：在场（无定位事件）' : '',
    ].filter(Boolean).join(' ｜ ');
    nodes.push(
      <g key={pl} onClick={() => onSelect(pl)} className="mt-place">
        <title>{tip}</title>
        {dotMode === 'cur' || curHere
          ? <circle cx={x} cy={y} r={curHere ? 7.5 : 5.5} fill={vis[0]?.color || '#a23527'}
              stroke="#fbf8ef" strokeWidth={curHere ? 2.5 : 1.5} />
          : isFuture
            ? <circle cx={x} cy={y} r={4.5} fill="#f4eee0" stroke={trails[0]?.color || '#a23527'} strokeWidth="2" />
            : <circle cx={x} cy={y} r={3} fill="#c9c0ac" opacity="0.55" />}
        {isGhostAdd && <circle cx={x} cy={y} r={9} fill="none" stroke="#4f6e4a" strokeWidth="2.5" />}
        {isGhostRem && <line x1={x - 6} y1={y - 6} x2={x + 6} y2={y + 6} stroke="#8a8172" strokeWidth="2" />}
        {(dotMode === 'cur' || curHere || pl === selPlace || (p.chaps.length >= 12 && lens === 'real')) && (
          <text x={x} y={y - 10} textAnchor="middle" fontSize="12"
            fill={pl === selPlace ? '#a23527' : '#5f584b'} style={{ pointerEvents: 'none' }}>{pl}</text>
        )}
      </g>,
    );
  }
  return nodes;
}
