import { useEffect, useRef, useState } from 'react';

/**
 * NetworkGraph —— 江湖关系网络图（ECharts graph · 按类型/书目着色 · 邻接高亮 · 点击进档案）。
 * 数据：graph.json（懒加载，每条边聚合证据 ≤3 定位符）。
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

export default function NetworkGraph() {
  const ref = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState('关系图加载中…');

  useEffect(() => {
    let chart: any = null;
    let disposed = false;
    Promise.all([
      import('echarts/core'),
      import('echarts/charts'),
      import('echarts/components'),
      import('echarts/renderers'),
      fetch(B + 'data/graph.json').then((r) => r.json()),
    ]).then(([core, charts, comps, renderers, graph]) => {
      if (disposed || !ref.current) return;
      core.use([charts.GraphChart, comps.TooltipComponent, comps.LegendComponent, renderers.CanvasRenderer]);
      const catIdx: Record<string, number> = {};
      const categories = CATS.map((name) => ({ name }));
      CATS.forEach((c, i) => (catIdx[c] = i));

      const nodes = graph.nodes.map((n: { id: string; type: string; n: number; books: string[] }) => {
        let cat = '人物';
        if (n.type === '☆') cat = '武功';
        else if (n.type === '◆') cat = '门派';
        else {
          const bs = n.books || [];
          cat = bs.length > 1 ? '跨书人物' : `人物·${bs[0]}`.replace('人物·', '人物·');
          if (!CATS.includes(cat)) cat = '人物';
        }
        const size = n.type === '@' ? Math.min(34, 8 + Math.sqrt(n.n || 1) * 1.6) : n.type === '◆' ? 16 : 10;
        return { id: n.id, name: n.id, category: catIdx[cat], symbolSize: size, _type: n.type };
      });
      const nodeSet = new Set(nodes.map((n: { id: string }) => n.id));
      const edges = graph.edges.map((e: { s: string; t: string; kind: string; label: string; n: number; locs: string[] }) => ({
        source: e.s, target: e.t,
        lineStyle: { width: Math.min(3.5, 0.6 + e.n * 0.25), opacity: 0.45, color: '#b5a687', curveness: 0.12 },
        _tip: `[${e.kind}${e.label ? '·' + e.label : ''}] ×${e.n} · ${e.locs.join(' / ')}`,
      })).filter((e: { source: string; target: string }) => nodeSet.has(e.source) && nodeSet.has(e.target));

      chart = core.init(ref.current);
      chart.setOption({
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
      });
      chart.on('click', (p: { dataType: string; data: { name?: string; _type?: string } }) => {
        if (p.dataType !== 'node' || !p.data.name) return;
        const t = p.data._type;
        const route = t === '☆' ? 'arts' : t === '◆' ? 'sects' : 'characters';
        window.open(`${B}${route}/${encodeURIComponent(p.data.name)}/`, '_blank');
      });
      setStatus('');
    });
    return () => { disposed = true; if (chart) chart.dispose(); };
  }, []);

  return (
    <div className="ng">
      <div ref={ref} className="ng-canvas" />
      {status && <div className="ng-status">{status}</div>}
      <p className="fine">
        拖拽/滚轮缩放 · 悬停高亮邻接 · 点击节点进档案页 · 图例点击按类型隐藏 ·
        边宽=证据数 · 悬停边看定位符。节点 646（人物 521/武功 108/门派 17）· 边 626（全部挂证）。
      </p>
      <style>{`
        .ng { display: flex; flex-direction: column; gap: 8px; }
        .ng-canvas { height: 620px; background: #fbf8ef; border: 1px solid #d8cdb4; border-radius: 4px; }
        .ng-status { padding: 60px; text-align: center; color: #5f584b; }
        .fine { font-size: 12px; color: #8a8172; }
      `}</style>
    </div>
  );
}
