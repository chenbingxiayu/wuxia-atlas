import { useEffect, useMemo, useRef, useState } from 'react';
import {
  dsp,
  fetchDisplayLookup,
  isMainPerson,
  toCanonical,
  type DisplayLookup,
} from '../lib/display-shared';

/**
 * PathFinder —— 江湖 AB 路径（规格 N1/7b；T10 多路径枚举 / T11 非人节点类型路由）：
 * 分层 BFS 求 dist + 前驱集合，沿前驱 DAG 回溯枚举全部最短路（上限 20 条），每一步挂一条证据。
 * 数据：graph.json（对局/师承/救助/恩义/传授/修习/独门/拥有/镇山边，全部带定位符）。深链 ?a=&b=&p=。
 */
type Edge = { s: string; t: string; kind: string; label: string; n: number; locs: string[]; books: string[] };
type Graph = { nodes: { id: string; type: string }[]; edges: Edge[] };
type Hop = { node: string; edge?: Edge; from: string };
type PfPath = { hops: Hop[]; n: number };
type PfResult = { paths: PfPath[]; total: number; ca: string; cb: string };

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';
const KIND_LABEL: Record<string, string> = {
  对局: '交手', 师承: '师承', 救助: '救助', 恩义: '恩义',
  传授: '传授', 修习: '修习', 独门: '独门', 拥有: '拥有', 镇山: '镇山',
};
// T11：graph.json 节点 type → 用户词（数据里是 ASCII 等号 '='=武功；未知类型一律「实体」）
// 节点类型用户词（对齐 characters.json type_legend：'=地点 ☆武功 ◆组织；&家族 ;职衔 ◎群体）
const TYPE_LABEL: Record<string, string> = { '@': '人物', '=': '地点', '☆': '武功', '◆': '门派', '&': '家族', ';': '职衔', '◎': '群体', '•': '神兵' };
const MAX_PATHS = 20; // T10：单次枚举上限，超过截断（总数仍由前驱 DAG 上的 DP 精确统计并提示）

export default function PathFinder() {
  const [graph, setGraph] = useState<Graph | null>(null);
  const [a, setA] = useState('');
  const [b, setB] = useState('');
  const [result, setResult] = useState<PfResult | null>(null);
  const [pathIdx, setPathIdx] = useState(0);
  const [miss, setMiss] = useState(false);
  const [sameNode, setSameNode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lookup, setLookup] = useState<DisplayLookup>({ display: {}, canonicalOf: {} });
  const lookupRef = useRef<DisplayLookup>({ display: {}, canonicalOf: {} });
  // T11：id→type 映射（graph.nodes 一次性建表，供 nodeHref 与非人物判定）
  const nodeType = useMemo(() => new Map((graph?.nodes || []).map((n) => [n.id, n.type])), [graph]);

  useEffect(() => {
    Promise.all([
      fetch(B + 'data/graph.json').then((r) => r.json()),
      fetchDisplayLookup(B),
    ]).then(([g, lk]: [Graph, DisplayLookup]) => {
      setGraph(g);
      setLookup(lk);
      lookupRef.current = lk;
      const q = new URLSearchParams(location.search);
      const qa = toCanonical(lk, q.get('a') || '');
      const qb = toCanonical(lk, q.get('b') || '');
      if (qa && qb) {
        setA(dsp(lk.display, qa));
        setB(dsp(lk.display, qb));
        // T10 深链：p 为 1-based 路径序号；越界/缺失由 run 内夹取回落第 1 条
        const p = parseInt(q.get('p') || '', 10);
        run(g, qa, qb, Number.isFinite(p) && p >= 1 ? p - 1 : 0);
      }
    });
  }, []);

  function run(g: Graph | null = graph, xa: string = a, xb: string = b, reqIdx = 0) {
    if (!g || !xa.trim() || !xb.trim()) return;
    // 输入可以是展示名（康熙）或规范名（玄烨）：内部寻路/URL 一律 canonical
    const ca = toCanonical(lookupRef.current, xa);
    const cb = toCanonical(lookupRef.current, xb);
    setBusy(true);
    try {
      const adj = new Map<string, { to: string; edge: Edge }[]>();
      for (const e of g.edges) {
        if (!adj.has(e.s)) adj.set(e.s, []);
        if (!adj.has(e.t)) adj.set(e.t, []);
        adj.get(e.s)!.push({ to: e.t, edge: e });
        adj.get(e.t)!.push({ to: e.s, edge: e });
      }
      if (ca === cb) { setSameNode(true); setMiss(true); setResult(null); setPathIdx(0); return; }
      setSameNode(false);
      // T10 分层 BFS：dist（起点=0）+ 每节点前驱集合（所有 dist=前驱dist-1 的边，同层边天然不入集）
      const dist = new Map<string, number>([[ca, 0]]);
      const prevs = new Map<string, { from: string; edge: Edge }[]>();
      const dq: string[] = [ca];
      while (dq.length) {
        const cur = dq.shift()!;
        if (cur === cb) break; // FIFO 保证此时所有 dist(cb)-1 层节点已出队，cb 的前驱集已完备
        const d = dist.get(cur)!;
        for (const { to, edge } of adj.get(cur) || []) {
          if (!dist.has(to)) {
            dist.set(to, d + 1);
            prevs.set(to, [{ from: cur, edge }]);
            dq.push(to);
          } else if (dist.get(to) === d + 1) {
            prevs.get(to)!.push({ from: cur, edge });
          }
        }
      }
      if (!dist.has(cb)) { setMiss(true); setResult(null); setPathIdx(0); return; }
      // T10 精确总数：前驱集合构成分层 DAG（每步 dist 严格 -1），DP 计数 count(v)=Σcount(pred)
      const cnt = new Map<string, number>([[ca, 1]]);
      const order = [...dist.keys()].sort((x, y) => dist.get(x)! - dist.get(y)!);
      for (const v of order) {
        if (v === ca) continue;
        let s = 0;
        for (const p of prevs.get(v) || []) s += cnt.get(p.from) || 0;
        cnt.set(v, s);
      }
      const total = cnt.get(cb) || 0;
      // T10 回溯枚举 ≤MAX_PATHS 条：前驱链每步 dist 递减必达起点，故每条分支都产出完整路径，
      // 取满 20 条即停（百万级总数也不会拖慢）；收集后再按跳点 id 字典序稳定排序。
      const paths: PfPath[] = [];
      const stackNodes: string[] = [];
      const stackEdges: Edge[] = [];
      (function walk(node: string) {
        if (paths.length >= MAX_PATHS) return;
        if (node === ca) {
          const hops: Hop[] = [];
          let from = ca;
          for (let i = stackEdges.length - 1; i >= 0; i--) {
            hops.push({ node: stackNodes[i], edge: stackEdges[i], from });
            from = stackNodes[i];
          }
          paths.push({ hops, n: hops.length });
          return;
        }
        stackNodes.push(node);
        for (const p of prevs.get(node) || []) {
          if (paths.length >= MAX_PATHS) break;
          stackEdges.push(p.edge);
          walk(p.from);
          stackEdges.pop();
        }
        stackNodes.pop();
      })(cb);
      paths.sort((x, y) => {
        for (let i = 0; i < Math.max(x.hops.length, y.hops.length); i++) {
          const xn = x.hops[i] ? x.hops[i].node : '';
          const yn = y.hops[i] ? y.hops[i].node : '';
          if (xn !== yn) return xn < yn ? -1 : 1;
        }
        // 同跳点序列时按边 kind·label 兜底，保证切换顺序稳定确定
        for (let i = 0; i < x.hops.length; i++) {
          const xe = x.hops[i].edge!, ye = y.hops[i].edge!;
          const xk = `${xe.kind}·${xe.label}`, yk = `${ye.kind}·${ye.label}`;
          if (xk !== yk) return xk < yk ? -1 : 1;
        }
        return 0;
      });
      const idx = Number.isInteger(reqIdx) && reqIdx >= 0 && reqIdx < paths.length ? reqIdx : 0;
      setResult({ paths, total, ca, cb });
      setPathIdx(idx);
      setMiss(false);
      // T10 深链：URL 同步 p（1-based）
      history.replaceState(null, '', `${location.pathname}?a=${encodeURIComponent(ca)}&b=${encodeURIComponent(cb)}&p=${idx + 1}`);
    } finally {
      setBusy(false);
    }
  }

  // T10：路径环形切换（‹ › 越界回绕），同步 URL 的 p
  function gotoPath(i: number) {
    if (!result || result.paths.length < 2) return;
    const len = result.paths.length;
    const idx = ((i % len) + len) % len;
    setPathIdx(idx);
    history.replaceState(null, '', `${location.pathname}?a=${encodeURIComponent(result.ca)}&b=${encodeURIComponent(result.cb)}&p=${idx + 1}`);
  }

  const persons = useMemoPersons(graph, lookup);
  const curPath = result ? result.paths[Math.min(pathIdx, result.paths.length - 1)] : null;
  // T11 文案：路径途经武功节点（☆）才显示"武功也能连通"——地点/家族等只出徽章不出此句
  const hasArts = !!curPath && curPath.hops.some(
    (h) => (nodeType.get(h.from) || '') === '☆' || (nodeType.get(h.node) || '') === '☆',
  );

  // T11 渲染：可链类型给 <a>，否则纯文本 + 类型徽章（起点/终点同式处理）
  function NodeTag({ id, type, className }: { id: string; type: string; className?: string }) {
    const href = nodeHref(id, type, lookup);
    if (href) return <a className={className} href={href}>{dsp(lookup.display, id)}</a>;
    return (
      <span className={className}>
        {dsp(lookup.display, id)}
        <span className="pf-type">{TYPE_LABEL[type] || '实体'}</span>
      </span>
    );
  }

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

      {miss && <p className="pf-miss">{sameNode ? '起点与终点是同一人——换一个终点再试。' : '图谱上不连通——两人没有可考证的关联边（这本身也是一种考据结论）。'}</p>}
      {result && curPath && (
        <div className="pf-result">
          <p className="pf-sum">
            {dsp(lookup.display, curPath.hops[0].from)} → {dsp(lookup.display, curPath.hops[curPath.n - 1].node)}：<b>{curPath.n} 跳</b>，每跳挂证（最短路）。
          </p>
          {hasArts && <p className="pf-dim">这一跳经由共同修习的武功——武功也能连通两位侠客。</p>}
          {result.paths.length > 1 && (
            <div className="pf-switch">
              <button className="pf-nav" onClick={() => gotoPath(pathIdx - 1)} aria-label="上一条路径">‹</button>
              <span className="pf-page">第 <b>{pathIdx + 1}</b>/{result.paths.length} 条</span>
              <button className="pf-nav" onClick={() => gotoPath(pathIdx + 1)} aria-label="下一条路径">›</button>
              <span className="pf-total">共 {result.total} 条最短路{result.total > MAX_PATHS ? `（显示前 ${MAX_PATHS}）` : ''}</span>
            </div>
          )}
          <ol className="pf-path">
            {curPath.hops.map((h, i) => (
              <li key={i}>
                <div className="pf-from">
                  <NodeTag id={h.from} type={nodeType.get(h.from) || ''} className="pf-node" />
                </div>
                <div className="pf-edge">
                  <span className="pf-kind">{KIND_LABEL[h.edge!.kind] || h.edge!.kind}{h.edge!.label && h.edge!.kind !== '对局' && h.edge!.kind !== '师承' ? `·${h.edge!.label}` : ''}</span>
                  <span className="pf-n">×{h.edge!.n}</span>
                  {/* 回目链接：章号补零（padStart 3 位）与 site/src/lib/links.ts 的 chapterHref 同式内联，注释互指（宪法：island 不 import links，避免全量 JSON 进 bundle） */}
                  {h.edge!.locs.map((loc) => {
                    const bi = loc.indexOf('·');
                    const book = bi > 0 ? loc.slice(0, bi) : '';
                    const chap = bi > 0 ? parseInt(loc.slice(bi + 1), 10) : NaN;
                    return book && !isNaN(chap)
                      ? <a key={loc} className="mono" href={`${B}books/${encodeURIComponent(book)}/${String(chap).padStart(3, '0')}/`}>{loc} →</a>
                      : <span key={loc} className="mono">{loc}</span>;
                  })}
                </div>
              </li>
            ))}
            <li className="pf-end">
              <NodeTag id={curPath.hops[curPath.n - 1].node} type={nodeType.get(curPath.hops[curPath.n - 1].node) || ''} className="pf-node" />
            </li>
          </ol>
          <p className="fine">
            {result.total > 1 ? '同一对侠客可有多条考据最短路——用上方 ‹ › 切换。' : '图谱上两人之间只有这一条最短路。'}
            经典案例：<button className="pf-demo" onClick={() => { setA('卓一航'); setB('凌未风'); run(graph, '卓一航', '凌未风'); }}>卓一航 → 凌未风（2 跳）</button>
          </p>
        </div>
      )}
      <style>{`
        .pf { display: flex; flex-direction: column; gap: 14px; }
        .pf-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .pf-in { flex: 1 1 150px; min-width: 0; padding: 10px 14px; border: 2px solid #262420; border-radius: 4px; font-family: inherit; font-size: 15px; background: #fbf8ef; }
        .pf-arrow { font-size: 20px; color: #a23527; }
        .pf-btn { font-family: inherit; border: 2px solid #a23527; background: #a23527; color: #fbf8ef; border-radius: 4px; padding: 0 26px; font-size: 15px; cursor: pointer; }
        .pf-btn:hover { background: #7e281d; }
        @media (max-width: 560px) {
          .pf-in { flex-basis: 100%; }
          .pf-btn { margin-left: auto; padding: 10px 26px; }
        }
        .pf-miss { color: #8a6607; }
        .pf-sum { font-size: 15px; }
        .pf-sum b { color: #a23527; }
        .pf-dim { font-size: 12px; color: #8a8172; margin: 0 0 4px; }
        .pf-switch { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 0 0 4px; font-size: 13px; color: #5f584b; }
        .pf-nav { font-family: inherit; border: 1px solid #31536c; background: none; color: #31536c; border-radius: 4px; width: 26px; height: 26px; font-size: 15px; line-height: 1; cursor: pointer; }
        .pf-nav:hover { border-color: #a23527; color: #a23527; }
        .pf-page b { color: #a23527; }
        .pf-total { color: #8a8172; font-size: 12px; }
        .pf-path { list-style: none; padding: 0; margin: 0; border-left: 2px solid #d8cdb4; }
        .pf-path li { padding: 8px 0 8px 18px; position: relative; }
        .pf-path li::before { content: ''; position: absolute; left: -7px; top: 13px; width: 10px; height: 10px; border-radius: 50%; background: #a23527; border: 2px solid #fbf8ef; box-shadow: 0 0 0 1.5px #a23527; }
        .pf-from .pf-node, .pf-end .pf-node { font-size: 17px; font-weight: 700; color: #31536c; }
        .pf-from a.pf-node:hover, .pf-end a.pf-node:hover { color: #a23527; }
        .pf-type { display: inline-block; margin-left: 6px; border: 1px solid #b5a687; color: #8a8172; border-radius: 3px; padding: 0 5px; font-size: 11px; font-weight: 400; vertical-align: 2px; }
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

/**
 * T11：graph.json 节点 type → 档案路由。与 site/src/lib/links.ts 的
 * personTarget/artTarget/weaponTarget/sectTarget「是否可链」判断同式内联，注释互指
 * （宪法：island 内不得 import src/lib/links——会把全量 JSON 打进 bundle）。
 * graph.json 的 id 已是 canonical id，无需再走别名解析；其余类型（&/◎/;/• 等实体）无档案页，返回 null。
 * W0-T5 存目守卫（方案 §2.3）：'@' 节点须有主档页（display-shared isMainPerson，与
 * 构建期 @lib/scope isMainDossier 同语义）——存目人物渲染纯文本节点（仍可作路径中间点）。
 */
function nodeHref(id: string, type: string, lookup: DisplayLookup): string | null {
  if (type === '@') return isMainPerson(lookup, id) ? `${B}characters/${encodeURIComponent(id)}/` : null;
  if (type === '☆') return `${B}arts/${encodeURIComponent(id)}/`;
  if (type === '◆') return `${B}sects/${encodeURIComponent(id)}/`;
  return null;
}

function useMemoPersons(graph: Graph | null, lookup: DisplayLookup) {
  const [names, setNames] = useState<string[]>([]);
  useEffect(() => {
    if (!graph) return;
    // 候选展示名（datalist 值）：用户可输入展示名，run() 内以 toCanonical 归一回内部 key
    setNames(
      graph.nodes.filter((n) => n.type === '@').map((n) => dsp(lookup.display, n.id)).sort().slice(0, 450),
    );
  }, [graph, lookup]);
  return names;
}
