import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  dsp,
  fetchDisplayLookup,
  toCanonical,
  type DisplayLookup,
  type DisplayMap,
} from '../lib/display-shared';

/**
 * MapTrail —— 时空页交互岛（M6 · jiangshan 形态）。
 * 数据：/data/atlas/state.json（书目清单+年代） + /data/atlas/{书}.json（人-回-地共现+事件，懒加载）
 *       + /public/geo/china-provinces.json（真实省界底图，DataV GeoAtlas，GCJ-02；站点内
 *         WGS-84 坐标直接叠加——全国视野下 ~500m 系统差 < 0.1px，无须纠偏，见实现设计 §2.3）。
 * 交互：回目滑块（已至/未至/当前三态轨迹）· 编年播放 · 人物多选 · 虚实透镜 · 幽灵对比 ·
 *       图层三档（共现轨迹[默认开]/门派驻地/剧情锚点，W3-T5）· 地名搜索（全书目，W3-T5）·
 *       地名谱系卡（Trace Place）· 剧情锚点卡（W3-T5）· 内联江湖状态 · URL 深链（?book&chap&person&place&mode&lens）。
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

/* W3-T5 图层/搜索支撑数据：
   SectSeat = sect_seats.json 门派驻地（●实锚/◌推理，color=类型四色，同门派志全景图）；
   Plot = char_plots.json 剧情锚点（place.coords 为空者不落图，待考不上图——纪律同 §五）；
   PlaceHit = 构建期从全部 atlas 切片提取的带坐标地名索引（atlas/index.astro props 注入，
   免运行时拉 7 书切片；b=书名标注）。 */
interface SectSeat {
  sect: string; type: string; seat: string; status: string; color: string;
  coords: [number, number]; basis?: string;
}
interface Plot {
  id: string; seq: number; name: string; tags?: string[]; tag_colors?: string[];
  book: string; loc: string; line?: string;
  place: {
    name: string | null; status: string; anchor: string | null;
    coords: [number, number] | null; candidates?: string;
  };
}
interface PlaceHit { n: string; b: string; la: number; ln: number; p?: string }
/* 剧情锚点渲染态：跨人物按 剧情名+定位 去重合并（同一剧情多人同锚只画一点），
   no=故事先后编号，offset=同坐标避让偏移。 */
interface PlotAnchor {
  key: string; no: number; name: string; book: string; loc: string; line?: string;
  status: string; anchorName: string | null; color: string;
  coords: [number, number]; chars: string[]; candidates?: string;
  offset: [number, number];
}

/* 事件类型计数（「类型」筛选 chips 用；other = 五种动词码之外） */
const EVENT_CODES = ['◈', '◉', '▲', '◇', '○'];
function catCount(list: Ev[], cat: string): number {
  return cat === 'other'
    ? list.filter((e) => !EVENT_CODES.includes(e.code || '')).length
    : list.filter((e) => e.code === cat).length;
}

/* 置信三档（gazetteer.json 的 precision）：exact=●实锚（明文可考）· shifted=◌偏移落图（虚构/模糊
   地名按考订锚点偏移安放）· approx=○待核验（近似）。谱系卡 / 图例 / 标记 tooltip 三处共用此名目；
   未标注或缺档一律按「待核验」诚实呈现（verified 均为 false，逐点核验进行中）。 */
const TIERS: Record<string, { glyph: string; label: string; note?: string }> = {
  exact: { glyph: '●', label: '实锚' },
  shifted: { glyph: '◌', label: '偏移落图', note: '虚构/模糊地名按考订锚点偏移安放' },
  approx: { glyph: '○', label: '待核验' },
};
function tierOf(precision?: string): { glyph: string; label: string; note?: string } {
  return (precision && TIERS[precision]) || TIERS.approx;
}

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

export default function MapTrail({ sectPages = [], placeIndex = [] }: {
  sectPages?: string[]; placeIndex?: PlaceHit[];
}) {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [bookTitle, setBookTitle] = useState<string>('');
  const [slice, setSlice] = useState<BookSlice | null>(null);
  const [lookup, setLookup] = useState<DisplayLookup>({ display: {}, canonicalOf: {} });
  const lookupRef = useRef<DisplayLookup>({ display: {}, canonicalOf: {} });
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
  /* W3-T5 图层三档：共现轨迹（默认开·核心）/ 门派驻地 / 剧情锚点（默认关，可叠加） */
  const [layers, setLayers] = useState({ trail: true, sects: false, plots: false });
  const [seats, setSeats] = useState<SectSeat[] | null>(null);
  const [plotData, setPlotData] = useState<Record<string, Plot[]> | null>(null);
  const plotsLoaded = useRef(false);
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [selPlot, setSelPlot] = useState<PlotAnchor | null>(null);
  /* 跨书搜索命中：换书后由切片加载效果定位并开谱系卡（ref 避免触发重拉切片） */
  const pendingPlace = useRef<string | null>(null);

  /* 深链初始化 */
  useEffect(() => {
    const d: Record<string, string> = {};
    new URLSearchParams(location.search).forEach((v, k) => (d[k] = v));
    Promise.all([
      fetch(B + 'data/atlas/state.json').then((r) => r.json()),
      fetchDisplayLookup(B),
    ]).then(([m, lk]: [Manifest, DisplayLookup]) => {
      setManifest(m);
      setLookup(lk);
      lookupRef.current = lk;
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
        const ps = (q.get('person') || '').split(',').filter(Boolean)
          .map((p) => toCanonical(lookupRef.current, p))
          .filter((p) => s.persons[p]);
        setPersons(ps.length ? ps : [suggestedPerson(s, manifest, lookupRef.current)]);
        setLens(q.get('lens') === 'fiction' ? 'fiction' : 'real');
        setGhostOn(q.get('mode') === 'ghost');
        setGhostChap(Math.max(1, Math.ceil(s.chapters / 4)));
        /* W3-T5 跨书搜索命中优先：换书加载完成后定位命中地名并开谱系卡 */
        const linked = pendingPlace.current && s.places[pendingPlace.current] ? pendingPlace.current : null;
        setSelPlace(linked || (q.get('place') && s.places[q.get('place')!] ? q.get('place') : null));
        if (linked) pendingPlace.current = null;
      });
  }, [bookTitle, manifest]);

  /* W3-T5 门派驻地层：sect_seats.json（3KB）进页一次加载 */
  useEffect(() => {
    fetch(B + 'data/sect_seats.json')
      .then((r) => r.json())
      .then((s: { seats?: SectSeat[] }) => setSeats(s.seats || []))
      .catch(() => setSeats([]));
  }, []);

  /* W3-T5 剧情锚点层：char_plots.json（55KB）首次开启该层时懒加载一次。
     characters 值形如 { plots: [...] }（部分人物另带 book_states），取整为 Plot[] 表。 */
  useEffect(() => {
    if (!layers.plots || plotsLoaded.current) return;
    plotsLoaded.current = true;
    fetch(B + 'data/char_plots.json')
      .then((r) => r.json())
      .then((d: { characters?: Record<string, { plots?: Plot[] }> }) => {
        const out: Record<string, Plot[]> = {};
        for (const [ch, v] of Object.entries(d.characters || {})) out[ch] = v?.plots || [];
        setPlotData(out);
      })
      .catch(() => { plotsLoaded.current = false; });
  }, [layers.plots]);

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
  const gazTier = tierOf(gazPlace?.precision); // 置信三档（缺档按「待核验」诚实呈现）

  /* W3-T5 地名搜索（F6）：全书目切片地名索引（构建期 props 注入，条目标注书名），
     ≥2 字即过滤；命中当前书直接定位开卡，他书命中先切书再由切片加载效果定位。 */
  const q = query.trim();
  const searchHits: PlaceHit[] = q.length >= 2
    ? placeIndex
        .filter((h) => h.n.includes(q))
        .sort((a, b) => (a.b === bookTitle ? 0 : 1) - (b.b === bookTitle ? 0 : 1))
        .slice(0, 12)
    : [];
  const pickHit = (h: PlaceHit) => {
    setSearchOpen(false);
    setQuery('');
    setSelPlot(null);
    if (h.b === bookTitle) setSelPlace(h.n);
    else { pendingPlace.current = h.n; setBookTitle(h.b); }
  };

  /* W3-T5 剧情锚点（F3 事件层）：当前书、有坐标的锚点；跨人物按 剧情名+定位 去重
     （同一剧情多人同锚只画一点，卡内并列人物）；按回目+故事先后编号。
     避让策略：① z 序——锚点层整体绘制在轨迹点之上；② 同坐标多锚点环形散开（r=11px），
     不改坐标语义（tooltip 仍报真实锚点）。 */
  const plotAnchors: PlotAnchor[] = (() => {
    if (!layers.plots || !plotData) return [];
    const merged = new Map<string, Omit<PlotAnchor, 'no' | 'offset'>>();
    for (const [ch, plots] of Object.entries(plotData)) {
      for (const p of plots || []) {
        if (p.book !== bookTitle || !p.place?.coords) continue;
        const key = p.name + '|' + p.loc;
        const ex = merged.get(key);
        if (ex) { if (!ex.chars.includes(ch)) ex.chars.push(ch); continue; }
        merged.set(key, {
          key, name: p.name, book: p.book, loc: p.loc, line: p.line,
          status: p.place.status, anchorName: p.place.anchor || p.place.name || null,
          color: p.tag_colors?.[0] || '#8c8477', coords: p.place.coords,
          chars: [ch], candidates: p.place.candidates,
        });
      }
    }
    const list = [...merged.values()].sort((a, b) =>
      (parseInt(a.loc.slice(0, 3), 10) || 0) - (parseInt(b.loc.slice(0, 3), 10) || 0)
      || a.key.localeCompare(b.key, 'zh-Hans-CN'));
    const groups = new Map<string, string[]>();
    for (const a of list) {
      const gk = a.coords[0].toFixed(3) + ',' + a.coords[1].toFixed(3);
      const arr = groups.get(gk);
      if (arr) arr.push(a.key); else groups.set(gk, [a.key]);
    }
    const offsetOf = (key: string): [number, number] => {
      for (const keys of groups.values()) {
        const i = keys.indexOf(key);
        if (i < 0) continue;
        const k = keys.length;
        if (k === 1) return [0, 0];
        const ang = (2 * Math.PI * i) / k - Math.PI / 2;
        return [Math.round(Math.cos(ang) * 110) / 10, Math.round(Math.sin(ang) * 110) / 10];
      }
      return [0, 0];
    };
    return list.map((a, i) => ({ ...a, no: i + 1, offset: offsetOf(a.key) }));
  })();

  return (
    <div className="mt-root">
      {/* 控制台 */}
      <div className="mt-panel">
        <div className="mt-row">
          <span className="mt-lab">书目</span>
          {manifest.books.map((b) => (
            <button key={b.slug} className={'mt-chip' + (b.title === bookTitle ? ' on' : '')}
              onClick={() => { setBookTitle(b.title); setSelPlace(null); setSelPlot(null); }}>{b.title}</button>
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
          <span className="mt-lab">图层</span>
          {([['trail', '共现轨迹'], ['sects', '门派驻地'], ['plots', '剧情锚点']] as const).map(([k, lab]) => (
            <button key={k} className={'mt-chip' + (layers[k] ? ' on' : '')} aria-pressed={layers[k]}
              title={k === 'trail' ? '人物-回-地共现轨迹（默认开 · 核心层）'
                : k === 'sects' ? '门派驻地标记（●实锚/◌推理 · 类型四色 · 点击进门派页）'
                  : '剧情锚点（编号示故事先后 · 类型着色 · 点击看剧情卡）'}
              onClick={() => {
                setLayers((l) => ({ ...l, [k]: !l[k] }));
                if (k === 'plots') setSelPlot(null);
              }}>{lab}</button>
          ))}
          <div className="mt-search" style={{ marginLeft: 'auto' }}>
            <input className="mt-search-input" value={query} aria-label="地名搜索"
              placeholder="搜索地名（如 武当山、布达拉宫）……"
              onChange={(e) => { setQuery(e.target.value); setSearchOpen(true); }}
              onFocus={() => setSearchOpen(true)}
              onBlur={() => window.setTimeout(() => setSearchOpen(false), 150)} />
            {searchOpen && q.length >= 2 && (
              <ul className="mt-search-list">
                {searchHits.map((h) => (
                  <li key={h.b + '|' + h.n}>
                    <button type="button" onMouseDown={() => pickHit(h)}>
                      <b>{h.n}</b>
                      <span className="mt-faint">{h.b} · {tierOf(h.p).glyph} {tierOf(h.p).label}</span>
                    </button>
                  </li>
                ))}
                {searchHits.length === 0 && <li className="mt-faint" style={{ padding: '4px 8px' }}>无命中地名（全书目检索）</li>}
              </ul>
            )}
          </div>
        </div>
        <div className="mt-row">
          <span className="mt-lab">侠客</span>
          {Object.entries(slice.persons).slice(0, 14).map(([pid]) => (
            <button key={pid}
              className={'mt-chip' + (persons.includes(pid) ? ' on' : '')}
              style={persons.includes(pid) ? { borderColor: PALETTE[persons.indexOf(pid) % 4], color: PALETTE[persons.indexOf(pid) % 4] } : {}}
              onClick={() => setPersons((ps) => ps.includes(pid) ? ps.filter((x) => x !== pid) : [...ps, pid])}>
              {dsp(lookup.display, pid)}
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
          {/* W3-T5 门派驻地层：●实锚/◌推理 · 类型色沿用全景势力地图四色（sect_seats.color）。
              有门派页者整组包 <a> 点击进门派页；无页者 title 提示待建（不虚挂 404）。
              画在轨迹线之下——核心轨迹永远不被叠加层遮挡。 */}
          {layers.sects && seats && seats.map((s) => {
            const [x, y] = proj(s.coords[0], s.coords[1]);
            const reasoned = s.status === '推理';
            const hasPage = sectPages.includes(s.sect);
            const tip = `${s.sect} · 驻地 ${s.seat} · ${s.status}${s.basis ? ' · ' + s.basis : ''} · ${hasPage ? '点击进门派页' : '门派页待建'}`;
            const dot = (
              <circle cx={x} cy={y} r={reasoned ? 9 : 7.5} fill={reasoned ? 'none' : s.color}
                stroke={s.color} strokeWidth="2" strokeDasharray={reasoned ? '3 3' : undefined}
                className="mt-sectdot" />
            );
            const label = (
              <text x={x} y={y - 13} textAnchor="middle" fontSize="11.5" fontWeight="700"
                fill={s.color} stroke="#fbf8ef" strokeWidth="2.5" paintOrder="stroke">{s.sect}</text>
            );
            return (
              <g className="mt-sect" key={s.sect}>
                <title>{tip}</title>
                {hasPage
                  ? <a href={`${B}sects/${encodeURIComponent(s.sect)}/`} aria-label={`${s.sect} 门派页`}>{dot}{label}</a>
                  : <>{dot}{label}</>}
              </g>
            );
          })}
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
          {placeDots(slice, trails, lens, proj, chap, ghost, selPlace, setSelPlace, dotMode, lookup.display)}
          {/* W3-T5 剧情锚点层：编号=故事先后 · 类型色点（●实锚/◌推理）· 点击开剧情卡。
              画在轨迹点之上（z 序避让），同坐标锚点已环形散开（不改坐标语义）。 */}
          {layers.plots && plotAnchors.map((a) => {
            const [px, py] = proj(a.coords[0], a.coords[1]);
            const cx = px + a.offset[0], cy = py + a.offset[1];
            return (
              <g className="mt-plot" key={a.key} onClick={() => setSelPlot(a)}>
                <title>{`${a.no} ${a.name} · ${a.book} ${a.loc.slice(0, 3)} 回 · ${a.status}锚${a.anchorName ? ' · ' + a.anchorName : ''} · 点击看剧情`}</title>
                {/* 扩大热区（透明垫层）：锚点小（r6.5）且编号文字在上方，垫层保证整组易点中 */}
                <circle cx={cx} cy={cy} r={10} fill="transparent" stroke="none" />
                {a.status === '实锚' ? (
                  <circle cx={cx} cy={cy} r={6.5} fill={a.color} stroke="#fbf8ef" strokeWidth="1.6" />
                ) : (
                  <circle cx={cx} cy={cy} r={6.5} fill="#fbf8ef" fillOpacity="0.55" stroke={a.color}
                    strokeWidth="2" strokeDasharray="3 2.4" />
                )}
                <text x={cx} y={cy - 9.5} textAnchor="middle" fontSize="11.5" fontWeight="700"
                  fill={a.color} stroke="#fbf8ef" strokeWidth="2.5" paintOrder="stroke"
                  style={{ pointerEvents: 'none' }}>{a.no}</text>
              </g>
            );
          })}
          {/* W3-T5 搜索/选中定位环：地图为全国固定视野，以高亮环示意「居中该点」（脉冲动画见样式） */}
          {(() => {
            if (!selPlace) return null;
            const p = slice.places[selPlace];
            if (!p || p.lat == null || lens !== 'real') return null;
            const [x, y] = proj(p.lng!, p.lat!);
            return <circle className="mt-focus" cx={x} cy={y} r={15} fill="none" stroke="#a23527"
              strokeWidth="1.6" strokeDasharray="4 3" style={{ pointerEvents: 'none' }} />;
          })()}
        </svg>

        {/* 内联江湖状态 */}
        <div className="mt-state">
          <b>{bookTitle} · 第 {chap} 回</b>
          <span>时期：{slice.era || '元数据待考'}{slice.era_conf === 'todo' ? '（待考）' : ''}</span>
          <span>在场人物 {cur.p.length} · 地点 {cur.l.length} · 事件 {evList.length} 起</span>
          <span className="mt-faint">掌门世系 · 考订中</span>
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
            {gazPlace?.lat != null && (
              <div className="mt-coord mono">{gazPlace.lat.toFixed(4)}°N, {gazPlace.lng!.toFixed(4)}°E
                <span className="mt-faint" title={gazTier.note}> · {gazTier.glyph} {gazTier.label} · OSM 检索 · 逐点核验进行中</span>
              </div>
            )}
            <div className="mt-trace-rows">
              {placeEntry.chaps.slice(0, 8).map((c) => {
                const ppl = (slice.bychap[String(c)] || { p: [] }).p.slice(0, 6);
                return (
                  <div className="mt-trow" key={c}>
                    <a className="mt-link mono" href={`${B}books/${encodeURIComponent(bookTitle)}/${String(c).padStart(3, '0')}`}>
                      第 {c} 回 →
                    </a>
                    <span className="mt-faint">{ppl.length ? '在场 ' + ppl.map((p) => dsp(lookup.display, p)).join(' · ') : ''}</span>
                  </div>
                );
              })}
              {placeEntry.chaps.length > 8 && (
                <div className="mt-faint">…共 {placeEntry.chaps.length} 回（跨书沿革待多书联查）</div>
              )}
            </div>
          </div>
        )}

        {/* W3-T5 剧情锚点卡：剧情名 + 一句话 + 回目链接 + 人物档案（设计 §八「点击看人物档案」） */}
        {selPlot && (
          <div className="mt-plotcard">
            <div className="mt-trace-h">
              <b>{selPlot.name}</b>
              {selPlot.status === '实锚'
                ? <span className="mt-badge mt-ok">实锚</span>
                : <span className="mt-badge mt-fic">推理锚</span>}
              <button className="mt-x" onClick={() => setSelPlot(null)} aria-label="关闭剧情卡">×</button>
            </div>
            <div className="mt-coord mono">
              <a className="mt-link" href={`${B}books/${encodeURIComponent(selPlot.book)}/${selPlot.loc.slice(0, 3)}`}>
                {selPlot.book} {selPlot.loc} →
              </a>
              <span className="mt-faint"> 剧情锚点 {selPlot.no}</span>
            </div>
            {selPlot.line && <div className="mt-plotline">{selPlot.line}</div>}
            <div className="mt-faint">
              锚点 {selPlot.anchorName || '—'} · {selPlot.status === '实锚' ? '原文明文落图' : '推理落图'}
            </div>
            {selPlot.status !== '实锚' && selPlot.candidates && (
              <div className="mt-faint">依据：{selPlot.candidates}</div>
            )}
            <div className="mt-trace-rows">
              {selPlot.chars.map((c) => (
                <div className="mt-trow" key={c}>
                  <a className="mt-link" href={`${B}characters/${encodeURIComponent(c)}/`}>{dsp(lookup.display, c)} 档案 →</a>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 图例 */}
        <div className="mt-legend">
          <span><i className="dot" style={{ background: '#a23527' }} />已至（≤ 当前回）</span>
          <span><i className="dot hollow" />未至节点</span>
          <span title="precision = exact">● 实锚（明文可考）</span>
          <span title="虚构/模糊地名按考订锚点偏移安放">◌ 偏移落图（虚构/模糊）</span>
          <span title="precision = approx">○ 待核验（近似）</span>
          {/* W3-T5 口径明示（F8 · 设计 §八）：连线语义必须在图例内逐字可见 */}
          <span className="mt-semic" title="共现口径：同回出现在同一地点即连边，不推断途中行进">
            连线 = 同回出现，不表示行进路线
          </span>
          {ghostOn && <span><i className="dot" style={{ background: '#4f6e4a' }} />B 回新到</span>}
          {ghostOn && <span><i className="dot" style={{ background: '#8a8172' }} />A 回后离开</span>}
          {layers.sects && (
            <span title="类型四色同门派志全景图：名门正派/世家/绿林帮会/朝廷势力">
              ◉ 门派驻地（●实锚 ◌推理 · 点击进门派页）
            </span>
          )}
          {layers.plots && (
            <span title="编号示故事先后 · 颜色示剧情类型">
              ⓘ 剧情锚点（编号 · 点击看剧情卡）
            </span>
          )}
          <span className="mt-faint" style={{ marginLeft: 'auto' }}>
            底图：DataV GeoAtlas（真实省界）· 坐标：OSM 检索 · 逐点核验进行中（WGS-84）· ◌ 虚构/模糊地名按考订锚点偏移安放
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
            href={`${B}books/${encodeURIComponent(bookTitle)}/${String(chap).padStart(3, '0')}`}>回目页 →</a>
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
              <span className="mt-who">{e.a ? dsp(lookup.display, e.a) : '？'}</span>
              {e.b && <>→ <span className="mt-who">{dsp(lookup.display, e.b)}</span></>}
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

function suggestedPerson(s: BookSlice, manifest: Manifest | null, lookup: DisplayLookup): string {
  const book = manifest?.books.find((b) => b.title === s.title);
  if (book) {
    for (const lead of book.leads) {
      const c = toCanonical(lookup, lead);
      if (s.persons[c]) return c;
      if (s.persons[lead]) return lead;
    }
  }
  return Object.keys(s.persons)[0];
}

function collectPoints(feats: GeoFeat[]): [number, number][] {
  const out: [number, number][] = [];
  const push = (c: unknown) => {
    if (typeof c?.[0] === 'number') out.push(c as [number, number]);
    else if (Array.isArray(c)) c.forEach(push);
  };
  feats.forEach((f) => push(f.geometry.coordinates));
  return out;
}

/* 置信三档圆点：exact=●实锚（实心+白晕环）· shifted=◌偏移落图（虚线环+半透明填充）·
   approx=○待核验（空心环，纸色内芯）。fill/ring 分离以便灰点复用；haloW>0 垫白底晕圈
   （主点位），=0 无晕（次级灰点）。时态语义（已至/未至/幽灵）由外层另行叠加。 */
function precDot(
  x: number, y: number, r: number, fill: string, ring: string,
  prec: 'exact' | 'shifted' | 'approx', haloW: number,
): ReactNode {
  if (prec === 'shifted') {
    return (
      <>
        {haloW > 0 && <circle cx={x} cy={y} r={r + haloW / 2 + 0.4} fill="#fbf8ef" />}
        <circle cx={x} cy={y} r={r} fill={fill} fillOpacity="0.38" stroke={ring}
          strokeWidth={haloW > 0 ? 1.8 : 1.2} strokeDasharray="3 2.4" />
      </>
    );
  }
  if (prec === 'approx') {
    return (
      <>
        {haloW > 0 && <circle cx={x} cy={y} r={r + haloW / 2 + 0.4} fill="#fbf8ef" />}
        <circle cx={x} cy={y} r={r} fill="#f4eee0" stroke={ring} strokeWidth={haloW > 0 ? 1.6 : 1.1} />
      </>
    );
  }
  return <circle cx={x} cy={y} r={r} fill={fill} stroke={haloW > 0 ? '#fbf8ef' : 'none'} strokeWidth={haloW > 0 ? haloW : 0} />;
}

function placeDots(
  slice: BookSlice, trails: Trail[], lens: 'real' | 'fiction', proj: Proj,
  chap: number, ghost: { added: string[]; removed: string[] } | null,
  selPlace: string | null, onSelect: (p: string) => void,
  dotMode: 'cur' | 'all', displayMap: DisplayMap,
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
    /* 置信三档（缺档按「待核验」）：圆点实心/虚线/空心由 prec 决定；已至/未至等时态样式不变 */
    const prec: 'exact' | 'shifted' | 'approx' =
      p.precision === 'exact' ? 'exact' : p.precision === 'shifted' ? 'shifted' : 'approx';
    const base = vis[0]?.color || '#a23527';
    const tier = tierOf(p.precision);
    // 点位模式：cur = 只显当前回地点；all = 已至/未至全景
    const visible = dotMode === 'cur' ? curHere || pl === selPlace : vis.length > 0 || isFuture || curHere;
    if (!visible) continue;
    const evs = evsAt(pl);
    const tip = [
      pl + (p.lat != null ? `（${p.lat.toFixed(2)}, ${p.lng!.toFixed(2)}）· ${tier.glyph} ${tier.label}` : ' · 虚构 · 待锚定'),
      ...evs.map((e) => `第${chap}回 ${e.v}：${e.a ? dsp(displayMap, e.a) : '？'}${e.b ? ' → ' + dsp(displayMap, e.b) : ''}`),
      evs.length === 0 && curHere ? '第' + chap + '回：在场（无定位事件）' : '',
    ].filter(Boolean).join(' ｜ ');
    nodes.push(
      <g key={pl} onClick={() => onSelect(pl)} className="mt-place">
        <title>{tip}</title>
        {dotMode === 'cur' || curHere
          ? precDot(x, y, curHere ? 7.5 : 5.5, base, base, prec, curHere ? 2.5 : 1.5)
          : isFuture
            ? <circle cx={x} cy={y} r={4.5} fill="#f4eee0" stroke={trails[0]?.color || '#a23527'} strokeWidth="2" />
            : precDot(x, y, 3, '#c9c0ac', '#8a8172', prec, 0)}
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
