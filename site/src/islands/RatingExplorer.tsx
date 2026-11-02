import { useEffect, useMemo, useState } from 'react';

/**
 * RatingExplorer —— 侠谱总榜交互岛（规格 P1）。
 * 榜域切换（合成榜/书内榜）· 分档/门派过滤 · 搜索 · 行内展开证据链（matches 定位符）。
 * 榜头横幅：v0 未过人工抽检（规格 §六 异常规则已触发，见方法论页）。
 */
type Player = { name: string; rating: number; rd: number; tier: string; matches_n: number; 'w/d/l': number[]; per_book: Record<string, number>; top_evidence: string[] };
type Match = { id: string; a: string; b: string; outcome: string; weight: number; confidence: string; modifiers: string[]; kind: string; book: string; loc: string };

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';
const BOOKS = ['白发魔女传', '塞外奇侠传', '七剑下天山', '江湖三女侠'];
const TIERS = ['绝顶', '超一流', '一流', '二流', '三流'];
const TIER_COLOR: Record<string, string> = { 绝顶: '#b8860b', 超一流: '#a23527', 一流: '#31536c', 二流: '#5f584b', 三流: '#9a9280' };

export default function RatingExplorer() {
  const [players, setPlayers] = useState<Player[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [sectOf, setSectOf] = useState<Record<string, string>>({});
  const [domain, setDomain] = useState<string>('合成榜');
  const [tier, setTier] = useState<string>('全部');
  const [sect, setSect] = useState<string>('全部');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch(B + 'data/ratings.json').then((r) => r.json()),
      fetch(B + 'data/matches.json').then((r) => r.json()),
      fetch(B + 'data/dossiers.json').then((r) => r.json()),
    ]).then(([rt, mt, ds]) => {
      setPlayers(rt.players);
      setMatches(mt.matches);
      const sects: Record<string, string> = {};
      for (const d of ds.dossiers || []) {
        const sa = (d.sect_affinity || []).find((x: { tier: string }) => x.tier !== 'weak');
        if (sa) sects[d.canonical] = sa.sect;
      }
      setSectOf(sects);
    });
  }, []);

  const view = useMemo(() => {
    let rows = players.map((p) => {
      const book = domain === '合成榜' ? null : domain;
      const rating = book ? p.per_book[book] : p.rating;
      return book && !rating ? null : { ...p, viewRating: rating as number };
    }).filter(Boolean) as (Player & { viewRating: number })[];
    if (tier !== '全部') rows = rows.filter((p) => p.tier === tier);
    if (sect !== '全部') rows = rows.filter((p) => sectOf[p.name] === sect);
    if (q.trim()) rows = rows.filter((p) => p.name.includes(q.trim()));
    rows.sort((a, b) => b.viewRating - a.viewRating);
    return rows;
  }, [players, domain, tier, sect, q, sectOf]);

  const sects = useMemo(() => Object.values(sectOf).filter(Boolean).sort(), [sectOf]);
  const matchesOf = (name: string) =>
    matches.filter((m) => m.a === name || m.b === name)
      .sort((a, b) => b.weight - a.weight).slice(0, 5);

  if (!players.length) return <div className="re-loading">评分表加载中…</div>;

  return (
    <div className="re">
      <div className="re-banner">
        ⚠ v0 预览：抽取规则未过人工抽检（100 场精度≥90% 方可发布），分档仅供演示；
        规格验收的异常规则已触发（如玉罗刹白发榜未进前五）——回查进行中，见 <a href={`${B}ratings/method/`}>方法论页</a>。
      </div>
      <div className="re-ctrl">
        <div className="re-row">
          <span className="lab">榜域</span>
          {['合成榜', ...BOOKS].map((d) => (
            <button key={d} className={'chip' + (domain === d ? ' on' : '')} onClick={() => setDomain(d)}>{d}</button>
          ))}
        </div>
        <div className="re-row">
          <span className="lab">分档</span>
          {['全部', ...TIERS].map((t) => (
            <button key={t} className={'chip' + (tier === t ? ' on' : '')} onClick={() => setTier(t)}>{t}</button>
          ))}
          <input className="re-q" value={q} placeholder="搜人物…" onChange={(e) => setQ(e.target.value)} aria-label="搜索人物" />
        </div>
        <div className="re-row">
          <span className="lab">门派线索</span>
          <select className="re-sel" value={sect} onChange={(e) => setSect(e.target.value)}>
            <option>全部</option>
            {sects.map((s) => <option key={s}>{s}</option>)}
          </select>
          <span className="fine">展示 {view.length} 人 · 免责：本榜为基于原著交手记录的娱乐性指数</span>
        </div>
      </div>

      <table className="re-table">
        <thead><tr><th>#</th><th>人物</th><th>评分±区间</th><th>档位</th><th>门派线索</th><th>对局</th><th>战绩</th><th></th></tr></thead>
        <tbody>
          {view.map((p, i) => (
            <>
              <tr key={p.name}>
                <td className="mono rk">{i + 1}</td>
                <td><a className="nm" href={`${B}characters/${encodeURIComponent(p.name)}/`}>{p.name}</a></td>
                <td className="mono">{p.viewRating}±{p.rd}{p.rd > 150 && <span className="few" title="区间宽=对局少">数据不足</span>}</td>
                <td><span className="tier" style={{ color: TIER_COLOR[p.tier], borderColor: TIER_COLOR[p.tier] }}>{p.tier}</span></td>
                <td className="dim">{sectOf[p.name] || '—'}</td>
                <td className="mono">{p.matches_n}</td>
                <td className="mono dim">{p['w/d/l'].join('/')}</td>
                <td><button className="exp" onClick={() => setOpen(open === p.name ? null : p.name)}>{open === p.name ? '收起' : '证据链'}</button></td>
              </tr>
              {open === p.name && (
                <tr key={p.name + '-x'} className="evrow">
                  <td colSpan={8}>
                    <b>关键对局（按权重）：</b>
                    <ul>
                      {matchesOf(p.name).map((m) => {
                        const win = (m.a === p.name && m.outcome === 'win') || (m.b === p.name && m.outcome === 'loss');
                        return (
                          <li key={m.id}>
                            <span className={'mono ' + (m.outcome === 'draw' ? '' : win ? 'w' : 'l')}>{win ? '胜' : m.outcome === 'draw' ? '平' : '负'}</span>
                            {m.a} vs {m.b}（{m.kind}{m.modifiers.length ? ' · ' + m.modifiers.join('/') : ''} · w{m.weight}）
                            <a className="mono" href={`${B}books/${encodeURIComponent(m.book)}/${parseInt(m.loc, 10)}/`}>{m.book}·{m.loc} →</a>
                          </li>
                        );
                      })}
                      {!matchesOf(p.name).length && <li>无对局记录（评分=先验 1500）</li>}
                    </ul>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
      <style>{`
        .re { display: flex; flex-direction: column; gap: 14px; }
        .re-banner { background: #f6e8d9; border: 1px solid #a23527; border-radius: 4px; padding: 10px 16px; font-size: 13px; color: #7e281d; line-height: 1.8; }
        .re-banner a { color: #31536c; text-decoration: underline; }
        .re-ctrl { background: #fbf8ef; border: 1px solid #d8cdb4; border-radius: 4px; padding: 10px 16px; display: flex; flex-direction: column; gap: 8px; }
        .re-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .lab { font-size: 12px; color: #8a8172; letter-spacing: 1px; }
        .chip { font-family: inherit; border: 1px solid #b5a687; background: #fbf8ef; color: #5f584b; border-radius: 999px; padding: 2px 12px; font-size: 13px; cursor: pointer; }
        .chip.on, .chip:hover { border-color: #a23527; color: #a23527; }
        .re-q { margin-left: auto; padding: 5px 12px; border: 1px solid #b5a687; border-radius: 4px; font-family: inherit; font-size: 13.5px; background: #fbf8ef; }
        .re-sel { font-family: inherit; padding: 4px 10px; border: 1px solid #b5a687; border-radius: 4px; background: #fbf8ef; font-size: 13.5px; }
        .fine { margin-left: auto; font-size: 11.5px; color: #8a8172; }
        .re-table { width: 100%; border-collapse: collapse; font-size: 13.5px; background: #fbf8ef; border: 1px solid #d8cdb4; }
        .re-table th { text-align: left; color: #5f584b; font-size: 12px; padding: 8px 10px; border-bottom: 2px solid #b5a687; }
        .re-table td { padding: 6px 10px; border-bottom: 1px solid #e6ddc8; }
        .rk { color: #8a8172; } .nm { color: #31536c; font-weight: 700; } .nm:hover { color: #a23527; }
        .dim { color: #8a8172; } .mono { font-family: ui-monospace, monospace; }
        .few { margin-left: 6px; font-size: 10px; color: #8a6607; border: 1px dashed #8a6607; border-radius: 3px; padding: 0 4px; }
        .tier { display: inline-block; border: 1.5px solid; border-radius: 3px; padding: 0 6px; font-size: 12px; transform: rotate(-1.5deg); }
        .exp { font-family: inherit; border: 1px solid #b5a687; background: none; border-radius: 3px; padding: 1px 8px; font-size: 12px; cursor: pointer; color: #5f584b; }
        .exp:hover { border-color: #a23527; color: #a23527; }
        .evrow td { background: #f3ecda; }
        .evrow ul { list-style: none; margin: 4px 0; padding: 0; font-size: 13px; }
        .evrow li { padding: 3px 0; }
        .evrow .w { color: #4f6e4a; } .evrow .l { color: #a23527; }
        .evrow .mono { margin-left: 8px; font-size: 12px; color: #8a8172; }
        .re-loading { padding: 50px; text-align: center; color: #5f584b; }
      `}</style>
    </div>
  );
}
