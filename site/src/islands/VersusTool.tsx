import { useEffect, useState } from 'react';

/**
 * VersusTool —— 对局详情（规格 P3，单页 + URL 参数 ?a=&b=，不生成 N² 静态页）。
 * 评分对比头（分差 + 预期胜率）· 历史交锋列表 · 深链同步。
 */
type Player = { name: string; rating: number; rd: number; tier: string; matches_n: number; per_book: Record<string, number> };
type Match = { id: string; a: string; b: string; outcome: string; weight: number; kind: string; modifiers: string[]; book: string; loc: string };

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';

export default function VersusTool() {
  const [players, setPlayers] = useState<Player[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [a, setA] = useState('');
  const [b, setB] = useState('');

  useEffect(() => {
    Promise.all([
      fetch(B + 'data/ratings.json').then((r) => r.json()),
      fetch(B + 'data/matches.json').then((r) => r.json()),
    ]).then(([rt, mt]) => {
      setPlayers(rt.players.filter((p: Player) => p.matches_n > 0));
      setMatches(mt.matches);
      const q = new URLSearchParams(location.search);
      const qa = q.get('a') || '', qb = q.get('b') || '';
      if (qa && qb) { setA(qa); setB(qb); }
    });
  }, []);

  useEffect(() => {
    if (a && b) history.replaceState(null, '', `${location.pathname}?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  }, [a, b]);

  const pa = players.find((p) => p.name === a);
  const pb = players.find((p) => p.name === b);
  const h2h = (a && b) ? matches.filter((m) => (m.a === a && m.b === b) || (m.a === b && m.b === a)) : [];
  const expected = pa && pb ? 1 / (1 + Math.pow(10, (pb.rating - pa.rating) / 400)) : null;

  return (
    <div className="vt">
      <div className="vt-sel">
        <select value={a} onChange={(e) => setA(e.target.value)} aria-label="人物 A">
          <option value="">选人物 A…</option>
          {players.map((p) => <option key={p.name}>{p.name}</option>)}
        </select>
        <span className="vs">×</span>
        <select value={b} onChange={(e) => setB(e.target.value)} aria-label="人物 B">
          <option value="">选人物 B…</option>
          {players.map((p) => <option key={p.name}>{p.name}</option>)}
        </select>
      </div>

      {pa && pb ? (
        <>
          <div className="vt-head">
            {[pa, pb].map((p, i) => (
              <div className="vt-side" key={p.name}>
                <a className="vt-name" href={`${B}characters/${encodeURIComponent(p.name)}/`}>{p.name}</a>
                <div className="vt-rating mono">{p.rating}±{p.rd}</div>
                <div className="dim">{p.tier} · {p.matches_n} 场</div>
                {i === 0 && expected != null && <div className="vt-exp">预期胜率 <b>{Math.round(expected * 100)}%</b></div>}
              </div>
            ))}
            <div className="vt-mid">
              <div className="vt-delta mono">分差 {Math.abs(pa.rating - pb.rating)}</div>
              {expected != null && <div className="dim">（另一侧 {Math.round((1 - expected) * 100)}%）</div>}
            </div>
          </div>

          <h2>历史交锋（事件层）</h2>
          {h2h.length ? (
            <ul className="vt-list">
              {h2h.map((m) => (
                <li key={m.id}>
                  <b>{m.a}</b> <span className={'mono ' + m.outcome}>{m.outcome === 'draw' ? '平' : m.outcome === 'win' ? `${m.a} 胜` : `${m.b} 胜`}</span>
                  <span className="dim">（{m.kind}{m.modifiers.length ? ' · ' + m.modifiers.join('/') : ''} · w{m.weight}）</span>
                  <a className="mono loc" href={`${B}books/${encodeURIComponent(m.book)}/${parseInt(m.loc, 10)}/`}>{m.book}·{m.loc} →</a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="dim">事件层无直接交手记录——分差来自各自与共同对手的间接比较（可去时空页看两人是否同场）。</p>
          )}
          <p className="fine">分差来源：Glicko-2 合成榜展示分（收缩后）；预期胜率按 Elo 标度近似。区间宽者（RD 大于 150）结论仅供参考。</p>
        </>
      ) : (
        <p className="dim">选择两个人物查看评分对比与历史交锋（支持 <code>?a=练霓裳&amp;b=铁飞龙</code> 深链）。</p>
      )}

      <style>{`
        .vt { display: flex; flex-direction: column; gap: 16px; }
        .vt-sel { display: flex; gap: 12px; align-items: center; }
        .vt-sel select { font-family: inherit; font-size: 15px; padding: 8px 12px; border: 2px solid #262420; border-radius: 4px; background: #fbf8ef; flex: 1; }
        .vs { font-family: 'Ma Shan Zheng', serif; font-size: 22px; color: #a23527; }
        .vt-head { display: flex; gap: 20px; align-items: stretch; background: #fbf8ef; border: 1px solid #d8cdb4; border-radius: 4px; padding: 18px 24px; }
        .vt-side { flex: 1; }
        .vt-name { font-size: 22px; font-weight: 900; color: #31536c; }
        .vt-name:hover { color: #a23527; }
        .vt-rating { font-size: 26px; color: #a23527; margin: 4px 0; }
        .vt-exp { margin-top: 6px; font-size: 13.5px; color: #4f6e4a; }
        .vt-mid { display: flex; flex-direction: column; justify-content: center; align-items: center; }
        .vt-delta { font-size: 18px; color: #262420; }
        h2 { font-size: 1.05rem; border-bottom: 1px solid #d8cdb4; padding-bottom: .2em; }
        .vt-list { list-style: none; padding: 0; }
        .vt-list li { display: flex; gap: 10px; align-items: baseline; padding: 7px 0; border-bottom: 1px dashed #e6ddc8; font-size: 14px; flex-wrap: wrap; }
        .vt-list .win, .vt-list .loss { color: #4f6e4a; }
        .vt-list .draw { color: #8a8172; }
        .loc { margin-left: auto; }
        .dim { color: #8a8172; font-size: 13px; }
        .fine { color: #8a8172; font-size: 12px; }
        .mono { font-family: ui-monospace, monospace; }
        code { background: rgba(0,0,0,.05); border-radius: 3px; padding: 0 .3em; font-family: ui-monospace, monospace; }
      `}</style>
    </div>
  );
}
