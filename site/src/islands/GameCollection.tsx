import { useEffect, useMemo, useState } from 'react';

/**
 * GameCollection —— 神兵图鉴（spec 005/游戏页设计 4.2）。
 * weapons.json 183 件卡片墙 · localStorage wx-tuji-viewed 已阅标记 · 进度条 · 集齐提示。
 * 插画位：留接口（后续 public/illustrations 就位后按 slug 点亮）。
 */
type W = { canonical: string; kind: string; grade?: string; grade_basis?: string; ev_total: number; books: Record<string, unknown> };

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';
const KEY = 'wx-tuji-viewed';
const RARITY = (ev: number) => (ev >= 100 ? ['传世名器', '#a63a2b'] : ev >= 30 ? ['知名兵器', '#b8860b'] : ['杂件', '#8c8477']);

export default function GameCollection() {
  const [weapons, setWeapons] = useState<W[]>([]);
  const [viewed, setViewed] = useState<Set<string>>(new Set());
  const [ready, setReady] = useState(false);

  useEffect(() => {
    fetch(B + 'data/weapons.json').then((r) => r.json()).then((d) => {
      setWeapons(d.weapons || []);
    });
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) setViewed(new Set(JSON.parse(raw)));
    } catch { /* 隐私模式忽略 */ }
    setReady(true);
  }, []);

  const mark = (slug: string) => {
    if (viewed.has(slug)) return;
    const next = new Set(viewed);
    next.add(slug);
    setViewed(next);
    try { localStorage.setItem(KEY, JSON.stringify([...next])); } catch { /* 忽略 */ }
  };
  const allDone = weapons.length > 0 && viewed.size >= weapons.length;

  const byKind = useMemo(() => {
    const g: Record<string, W[]> = {};
    for (const w of weapons) (g[w.kind] ||= []).push(w);
    return Object.entries(g).sort((a, b) => b[1].length - a[1].length);
  }, [weapons]);

  if (!ready) return <div style={{ padding: 40, textAlign: 'center', color: '#5f584b' }}>图鉴加载中…</div>;

  const pct = weapons.length ? Math.round((viewed.size / weapons.length) * 100) : 0;

  return (
    <div className="gc">
      <div className="gc-progress">
        <b>图鉴收集度</b>
        <div className="bar"><div className="fill" style={{ width: `${pct}%` }} /></div>
        <span className="mono">{pct}%</span>
        <span className="lab">{viewed.size} / {weapons.length} 件已阅 · 点击卡片查看并收集 · 集齐点亮完成卡</span>
      </div>
      {allDone && (
        <div className="gc-done">✦ 图鉴收集完成——四书神兵，尽在眼底。</div>
      )}
      {byKind.map(([kind, list]) => (
        <section key={kind}>
          <h3>{kind} <small>{list.length} 件</small></h3>
          <div className="grid">
            {list.map((w) => {
              const [rar, color] = RARITY(w.ev_total);
              const seen = viewed.has(w.canonical);
              return (
                <a
                  key={w.canonical}
                  className={'wcard' + (seen ? ' seen' : '')}
                  href={`${B}weapons/${encodeURIComponent(w.canonical)}/`}
                  onClick={() => mark(w.canonical)}
                >
                  <div className="whead"><b>{w.canonical}</b>{seen && <span className="tick">✓</span>}</div>
                  <div className="wmeta">
                    <span className="kind">{w.kind}</span>
                    {w.grade && <span className="grade" style={w.grade_basis === '明文' ? {} : { borderStyle: 'dashed', color: '#8a6607' }}>{w.grade}</span>}
                  </div>
                  <div className="wfoot">
                    <span className="rar" style={{ color }}>◆ {rar}</span>
                    <span className="ev">考订证据 {w.ev_total} 处</span>
                  </div>
                </a>
              );
            })}
          </div>
        </section>
      ))}
      <style>{`
        .gc { display: flex; flex-direction: column; gap: 18px; }
        .gc-progress { background: #fbf8ef; border: 1px solid #d8cdb4; border-radius: 4px; padding: 12px 18px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
        .gc-progress b { font-family: 'Noto Serif SC', serif; }
        .bar { flex: 1; min-width: 160px; height: 14px; border: 1px solid #b5a687; border-radius: 999px; background: #f5efe4; overflow: hidden; }
        .fill { height: 100%; background: #a63a2b; }
        .mono { font-family: ui-monospace, monospace; }
        .lab { font-size: 12px; color: #8a8172; }
        .gc-done { background: #f6e8d9; border: 1px solid #b8860b; border-radius: 4px; padding: 10px 16px; color: #8a6607; font-weight: 700; text-align: center; }
        h3 { font-size: 15px; color: #5f584b; margin: 8px 0 6px; letter-spacing: 2px; }
        h3 small { color: #8a8172; font-weight: 400; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
        .wcard { border: 1px solid #b9ab90; border-radius: 4px; padding: 10px 12px; background: #fbf8ef; color: #2b2b2b; display: block; }
        .wcard:hover { border-color: #a63a2b; }
        .wcard.seen { border-color: #5e7d5a; }
        .whead { display: flex; justify-content: space-between; align-items: center; }
        .whead b { font-size: 14px; }
        .tick { color: #5e7d5a; font-weight: 700; }
        .wmeta { margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; }
        .kind { font-size: 11px; color: #5a544a; border: 1px solid #d8cdb8; border-radius: 999px; padding: 0 8px; }
        .grade { font-size: 11px; border: 1px solid #a63a2b; color: #a63a2b; border-radius: 3px; padding: 0 6px; }
        .wfoot { margin-top: 8px; display: flex; justify-content: space-between; font-size: 11px; color: #8a8172; }
      `}</style>
    </div>
  );
}
