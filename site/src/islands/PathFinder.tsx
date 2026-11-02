import { useEffect, useState } from 'react';

/**
 * PathFinder —— 江湖 AB 路径（规格 N1/7b）：任意两人最短关联路径，每一步挂一条证据。
 * 数据：graph.json（对局/师承/救助/恩义/传授边，全部带定位符）。深链 ?a=&b=。
 */
type Edge = { s: string; t: string; kind: string; label: string; n: number; locs: string[]; books: string[] };
type Graph = { nodes: { id: string; type: string }[]; edges: Edge[] };

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';
const KIND_LABEL: Record<string, string> = {
  对局: '交手', 师承: '师承', 救助: '救助', 恩义: '恩义',
  传授: '传授', 修习: '修习', 独门: '独门', 拥有: '拥有', 镇山: '镇山',
};

export default function PathFinder() {
  const [graph, setGraph] = useState<Graph | null>(null);
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const [result, setResult] = useState<{ hops: { node: string; edge?: Edge; from: string }[]; n: number } | null>(null);
  const [miss, setMiss] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch(B + 'data/graph.json').then((r) => r.json()).then((g: Graph) => {
      setGraph(g);
      const q = new URLSearchParams(location.search);
      const qa = q.get('a') || '', qb = q.get('b') || '';
      if (qa && qb) { setA(qa); setB(qb); run(g, qa, qb); }
    });
  }, []);

  function run(g: Graph | null = graph, xa: string = a, xb: string = b) {
    if (!g || !xa.trim() || !xb.trim()) return;
    setBusy(true);
    try {
      const adj = new Map<string, { to: string; edge: Edge }[]>();
      for (const e of g.edges) {
        if (!adj.has(e.s)) adj.set(e.s, []);
        if (!adj.has(e.t)) adj.set(e.t, []);
        adj.get(e.s)!.push({ to: e.t, edge: e });
        adj.get(e.t)!.push({ to: e.s, edge: e });
      }
      const prev = new Map<string, { from: string; edge: Edge } | null>();
      prev.set(xa, null);
      const dq: string[] = [xa];
      while (dq.length) {
        const cur = dq.shift()!;
        if (cur === xb) break;
        for (const { to, edge } of adj.get(cur) || []) {
          if (!prev.has(to)) {
            prev.set(to, { from: cur, edge });
            dq.push(to);
          }
        }
      }
      if (!prev.has(xb)) { setMiss(true); setResult(null); return; }
      const hops: { node: string; edge?: Edge; from: string }[] = [];
      let cur = xb;
      while (cur !== xa) {
        const p = prev.get(cur)!;
        hops.unshift({ node: cur, edge: p.edge, from: p.from });
        cur = p.from;
      }
      setResult({ hops, n: hops.length });
      setMiss(false);
      history.replaceState(null, '', `${location.pathname}?a=${encodeURIComponent(xa)}&b=${encodeURIComponent(xb)}`);
    } finally {
      setBusy(false);
    }
  }

  const persons = useMemoPersons(graph);

  return (
    <div className="pf">
      <div className="pf-row">
        <input className="pf-in" list="pf-names" value={a} placeholder="起点（如 卓一航）"
          onChange={(e) => setA(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && run()} aria-label="起点" />
        <span className="pf-arrow">→</span>
        <input className="pf-in" list="pf-names" value={b} placeholder="终点（如 凌未风）"
          onChange={(e) => setB(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && run()} aria-label="终点" />
        <button className="pf-btn" onClick={() => run()} disabled={busy}>{busy ? '寻路中…' : '寻路'}</button>
      </div>
      <datalist id="pf-names">{persons.map((n) => <option key={n} value={n} />)}</datalist>

      {miss && <p className="pf-miss">图谱上不连通——两人没有可考证的关联边（这本身也是一种考据结论）。</p>}
      {result && (
        <div className="pf-result">
          <p className="pf-sum">
            {result.hops[0].from} → {result.hops[result.n - 1].node}：<b>{result.n} 跳</b>，每跳挂证（BFS 最短）。
          </p>
          <ol className="pf-path">
            {result.hops.map((h, i) => (
              <li key={i}>
                <div className="pf-from">
                  <a href={personHref(h.from)}>{h.from}</a>
                </div>
                <div className="pf-edge">
                  <span className="pf-kind">{KIND_LABEL[h.edge!.kind] || h.edge!.kind}{h.edge!.label && h.edge!.kind !== '对局' && h.edge!.kind !== '师承' ? `·${h.edge!.label}` : ''}</span>
                  <span className="pf-n">×{h.edge!.n}</span>
                  {h.edge!.locs.map((loc) => {
                    const bi = loc.indexOf('·');
                    const book = bi > 0 ? loc.slice(0, bi) : '';
                    const chap = bi > 0 ? parseInt(loc.slice(bi + 1), 10) : NaN;
                    return book && !isNaN(chap)
                      ? <a key={loc} className="mono" href={`${B}books/${encodeURIComponent(book)}/${chap}/`}>{loc} →</a>
                      : <span key={loc} className="mono">{loc}</span>;
                  })}
                </div>
              </li>
            ))}
            <li className="pf-end">
              <a href={personHref(result.hops[result.n - 1].node)}>{result.hops[result.n - 1].node}</a>
            </li>
          </ol>
          <p className="fine">这是 BFS 最短路径之一——同一对人可能有多条考据路径（换条边再试）。
            经典案例：<button className="pf-demo" onClick={() => { setA('卓一航'); setB('凌未风'); run(graph, '卓一航', '凌未风'); }}>卓一航 → 凌未风（2 跳）</button></p>
        </div>
      )}
      <style>{`
        .pf { display: flex; flex-direction: column; gap: 14px; }
        .pf-row { display: flex; gap: 10px; align-items: center; }
        .pf-in { flex: 1; padding: 10px 14px; border: 2px solid #262420; border-radius: 4px; font-family: inherit; font-size: 15px; background: #fbf8ef; }
        .pf-arrow { font-size: 20px; color: #a23527; }
        .pf-btn { font-family: inherit; border: 2px solid #a23527; background: #a23527; color: #fbf8ef; border-radius: 4px; padding: 0 26px; font-size: 15px; cursor: pointer; }
        .pf-btn:hover { background: #7e281d; }
        .pf-miss { color: #8a6607; }
        .pf-sum { font-size: 15px; }
        .pf-sum b { color: #a23527; }
        .pf-path { list-style: none; padding: 0; margin: 0; border-left: 2px solid #d8cdb4; }
        .pf-path li { padding: 8px 0 8px 18px; position: relative; }
        .pf-path li::before { content: ''; position: absolute; left: -7px; top: 13px; width: 10px; height: 10px; border-radius: 50%; background: #a23527; border: 2px solid #fbf8ef; box-shadow: 0 0 0 1.5px #a23527; }
        .pf-from a, .pf-end a { font-size: 17px; font-weight: 700; color: #31536c; }
        .pf-from a:hover, .pf-end a:hover { color: #a23527; }
        .pf-edge { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; font-size: 13px; color: #5f584b; margin-top: 2px; }
        .pf-kind { color: #a23527; border: 1px solid #a23527; border-radius: 3px; padding: 0 6px; font-size: 12px; font-weight: 700; }
        .pf-n { color: #8a8172; font-size: 12px; }
        .pf-edge .mono { color: #31536c; font-family: ui-monospace, monospace; font-size: 12px; }
        .pf-end { padding-top: 2px; }
        .pf-demo { font-family: inherit; border: 1px solid #31536c; background: none; color: #31536c; border-radius: 999px; padding: 2px 12px; cursor: pointer; font-size: 13px; }
        .pf-demo:hover { border-color: #a23527; color: #a23527; }
        .fine { font-size: 12px; color: #8a8172; }
      `}</style>
    </div>
  );
}

function personHref(name: string) {
  return `${B}characters/${encodeURIComponent(name)}/`;
}
function useMemoPersons(graph: Graph | null) {
  const [names, setNames] = useState<string[]>([]);
  useEffect(() => {
    if (!graph) return;
    setNames(graph.nodes.filter((n) => n.type === '@').map((n) => n.id).sort().slice(0, 450));
  }, [graph]);
  return names;
}
