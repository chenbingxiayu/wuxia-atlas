import { useEffect, useRef, useState } from 'react';
import {
  fetchDisplayLookup,
  dsp,
  type DisplayLookup,
} from '../lib/display-shared';

/**
 * NetworkGraph —— 江湖关系网络图（ECharts graph · 按类型/书目着色 · 邻接高亮 · 点击进档案）。
 * 数据：graph.json（懒加载，每条边聚合证据 ≤3 定位符）。T12：可选「只看主要人物」过滤。
 */
const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';
const BOOK_COLOR: Record<string, string> = {
  '白发魔女传': '#c0392b', '塞外奇侠传': '#8a6607', '七剑下天山': '#31536c',
  '江湖三女侠': '#4f6e4a',
};
const CATS = ['跨书人物', '人物·白发', '人物·塞外', '人物·七剑', '人物·三女侠', '人物', '武功', '门派'];
const CAT_COLOR: Record<string, string> = {
  跨书人物: '#a23527', '人物·白发': '#c0392b', '人物·塞外': '#8a6607',
  '人物·七剑': '#31536c', '人物·三女侠': '#4f6e4a', 人物: '#5f584b', 武功: '#7d5ba6', 门派: '#b8860b',
};

// T12：「主要人物」阈值——人物节点证据数 n≥此值才保留（阈值可调）
const MAJOR_N = 100;

type RawNode = { id: string; type: string; n: number; books: string[] };
type RawEdge = { s: string; t: string; kind: string; label: string; n: number; locs: string[] };
type RawGraph = { nodes: RawNode[]; edges: RawEdge[] };

/** T12 过滤：majorOnly=false 时原样返回（全量图，视觉冲击保留）。 */
function filterGraph(graph: RawGraph, majorOnly: boolean): { nodes: RawNode[]; edges: RawEdge[] } {
  if (!majorOnly) return { nodes: graph.nodes, edges: graph.edges };
  // 规则：人物(type='@')保留 n≥MAJOR_N；非人物仅当至少一条边直连保留人物；边仅保留两端都在保留集的
  const typeOf = new Map(graph.nodes.map((n) => [n.id, n.type]));
  const major = new Set<string>();
  for (const n of graph.nodes) if (n.type === '@' && (n.n || 0) >= MAJOR_N) major.add(n.id);
  const kept = new Set(major);
  for (const e of graph.edges) {
    if (major.has(e.s) && typeOf.get(e.t) !== '@') kept.add(e.t);
    if (major.has(e.t) && typeOf.get(e.s) !== '@') kept.add(e.s);
  }
  return {
    nodes: graph.nodes.filter((n) => kept.has(n.id)),
    edges: graph.edges.filter((e) => kept.has(e.s) && kept.has(e.t)),
  };
}

/** 由原始节点/边构建 echarts series 数据（分类/着色/尺寸规则与全量图一致）。 */
function buildSeries(nodesRaw: RawNode[], edgesRaw: RawEdge[], lk: DisplayLookup) {
  const catIdx: Record<string, number> = {};
  const categories = CATS.map((name) => ({ name }));
  CATS.forEach((c, i) => (catIdx[c] = i));
  const nodes = nodesRaw.map((n) => {
    let cat = '人物';
    if (n.type === '☆') cat = '武功';
    else if (n.type === '◆') cat = '门派';
    else {
      const bs = n.books || [];
      cat = bs.length > 1 ? '跨书人物' : `人物·${bs[0]}`;
      if (!CATS.includes(cat)) cat = '人物';
    }
    const size = n.type === '@' ? Math.min(34, 8 + Math.sqrt(n.n || 1) * 1.6) : n.type === '◆' ? 16 : 10;
    return { id: n.id, name: dsp(lk.display, n.id), _canonical: n.id, category: catIdx[cat], symbolSize: size, _type: n.type };
  });
  const nodeSet = new Set(nodes.map((n) => n.id));
  const edges = edgesRaw.map((e) => ({
    source: e.s, target: e.t,
    lineStyle: { width: Math.min(3.5, 0.6 + e.n * 0.25), opacity: 0.45, color: '#b5a687', curveness: 0.12 },
    _tip: `[${e.kind}${e.label ? '·' + e.label : ''}] ×${e.n} · ${e.locs.join(' / ')}`,
  })).filter((e) => nodeSet.has(e.source) && nodeSet.has(e.target));
  return { categories, nodes, edges };
}

function buildOption(nodes: any[], edges: any[], categories: { name: string }[]) {
  return {
    backgroundColor: 'transparent',
    tooltip: { formatter: (p: { dataType: string; data: { _tip?: string; name?: string; _type?: string } }) =>
      p.dataType === 'edge' ? (p.data._tip || '') : `${p.data.name}（${p.data._type === '@' ? '人物' : p.data._type === '☆' ? '武功' : '门派'}）` },
    legend: { data: CATS, textStyle: { color: '#5f584b', fontSize: 11 }, top: 4, type: 'scroll' },
    series: [{
      type: 'graph', layout: 'force', roam: true, draggable: true,
      force: { repulsion: 90, edgeLength: [30, 90], gravity: 0.08, layoutAnimation: true },
      categories, data: nodes, links: edges,
      emphasis: { focus: 'adjacency', lineStyle: { opacity: 0.9 } },
      label: { show: false },
      scaleLimit: { min: 0.4, max: 6 },
    }],
  };
}

export default function NetworkGraph() {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const graphRef = useRef<{ graph: RawGraph; lk: DisplayLookup } | null>(null);
  const [status, setStatus] = useState('关系图加载中…');
  const [lookup, setLookup] = useState<DisplayLookup>({ display: {}, canonicalOf: {} });
  // 规模文案：从 fetch 到的 graph.json 运行时计算（宪法：数字从数据计算，不写死）；加载中留空（见页面 lead「规模加载后显示」）
  const [scale, setScale] = useState('');
  // T12：过滤开关（默认不勾选=全量图）；切换只重算 series，不重建/不重置已加载图
  const [majorOnly, setMajorOnly] = useState(false);
  const [filterScale, setFilterScale] = useState('');

  // T12：按当前开关重算 series 并 setOption（merge 模式替换 data/links，force 自动重排）
  function applySeries(mo: boolean) {
    const ctx = graphRef.current;
    const chart = chartRef.current;
    if (!ctx || !chart) return;
    const fg = filterGraph(ctx.graph, mo);
    const { categories, nodes, edges } = buildSeries(fg.nodes, fg.edges, ctx.lk);
    chart.setOption(buildOption(nodes, edges, categories));
    // 计数联动：过滤开启时在规模行后追加过滤后计数
    setFilterScale(mo ? `过滤后：节点 ${nodes.length} · 边 ${edges.length}。` : '');
  }

  useEffect(() => {
    let disposed = false;
    Promise.all([
      import('echarts/core'),
      import('echarts/charts'),
      import('echarts/components'),
      import('echarts/renderers'),
      fetch(B + 'data/graph.json').then((r) => r.json()),
      fetchDisplayLookup(B),
    ]).then(([core, charts, comps, renderers, graph, lk]) => {
      if (disposed || !ref.current) return;
      setLookup(lk);
      graphRef.current = { graph, lk };
      // 规模统计（011-T17）：始终统计全量 graph.json；过滤后计数由 applySeries 写入 filterScale
      // 类型用户词对齐 characters.json type_legend（'=地点 ☆武功 ◆组织；&家族 ;职衔 ◎群体）
      const TYPE_LABEL: Record<string, string> = { '@': '人物', '=': '地点', '☆': '武功', '◆': '门派', '&': '家族', ';': '职衔', '◎': '群体', '•': '神兵' };
      const typeCount: Record<string, number> = {};
      for (const n of graph.nodes as { type: string }[]) typeCount[n.type] = (typeCount[n.type] || 0) + 1;
      const parts = Object.keys(TYPE_LABEL).map((t) => `${TYPE_LABEL[t]} ${typeCount[t] || 0}`);
      const otherCount = Object.entries(typeCount).reduce((s, [t, c]) => (t in TYPE_LABEL ? s : s + c), 0);
      if (otherCount > 0) parts.push(`其他 ${otherCount}`);
      setScale(`节点 ${graph.nodes.length}（${parts.join('/')}）· 边 ${graph.edges.length}。`);
      core.use([charts.GraphChart, comps.TooltipComponent, comps.LegendComponent, renderers.CanvasRenderer]);
      const chart = core.init(ref.current);
      chartRef.current = chart;
      chart.on('click', (p: { dataType: string; data: { name?: string; _canonical?: string; _type?: string } }) => {
        if (p.dataType !== 'node' || !p.data.name) return;
        const t = p.data._type;
        const route = t === '☆' ? 'arts' : t === '◆' ? 'sects' : 'characters';
        // URL/内部 key 保持 canonical（_canonical），展示名仅用于 label/tooltip
        window.open(`${B}${route}/${encodeURIComponent(p.data._canonical || p.data.name)}/`, '_blank');
      });
      applySeries(false); // 初始渲染全量图
      setStatus('');
    });
    return () => { disposed = true; if (chartRef.current) { chartRef.current.dispose(); chartRef.current = null; } };
  }, []);

  return (
    <div className="ng">
      <label className="ng-filter">
        <input type="checkbox" checked={majorOnly}
          onChange={(e) => { const v = e.target.checked; setMajorOnly(v); applySeries(v); }} />
        只看主要人物（证据数 ≥ {MAJOR_N}）
      </label>
      <div ref={ref} className="ng-canvas" />
      {status && <div className="ng-status">{status}</div>}
      <p className="fine">
        拖拽/滚轮缩放 · 悬停高亮邻接 · 点击节点进档案页 · 图例点击按类型隐藏 ·
        边宽=证据数 · 悬停边看定位符。{scale}{filterScale}
      </p>
      <style>{`
        .ng { display: flex; flex-direction: column; gap: 8px; }
        .ng-filter { display: flex; gap: 6px; align-items: center; width: fit-content; font-size: 13px; color: #5f584b; cursor: pointer; user-select: none; }
        .ng-canvas { height: 620px; background: #fbf8ef; border: 1px solid #d8cdb4; border-radius: 4px; }
        .ng-status { padding: 60px; text-align: center; color: #5f584b; }
        .fine { font-size: 12px; color: #8a8172; }
      `}</style>
    </div>
  );
}
