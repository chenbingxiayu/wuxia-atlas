import { useEffect, useMemo, useState } from 'react';
import { lastNDays, readStats, type GameStats, type JianghuStats } from '../lib/game-stats';

/**
 * GameStatsHub —— 战绩中心卡（游戏页设计 §六 F3，任务 E1）。
 * /games hub 客户端渲染：读 localStorage jianghu-stats-v1，跨游戏汇总——
 * 每日一谜 / 二十问答 各自连胜（最佳）+ 累计正确率，近 14 天答题日历（有战绩日亮起，hover 当日结果）。
 * 空态：江湖风平浪静（EmptyState 口吻）。数据层契约见 lib/game-stats.ts；仅存本机，不上传。
 */
const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';

const pct = (g: GameStats) => (g.plays ? Math.round((g.wins * 100) / g.plays) : 0);
const dayLabel = (d: string) => `${Number(d.slice(4, 6))}月${Number(d.slice(6, 8))}日`;
const resWord = (r?: 'w' | 'l') => (r === 'w' ? '胜' : r === 'l' ? '负' : null);

function GameLine({ name, href, g }: { name: string; href: string; g: GameStats }) {
  return (
    <div className="gsc-game">
      <a className="gsc-name" href={href}>{name}</a>
      <div className="gsc-line">连胜 <b>{g.curStreak}</b><span className="gsc-sub">（最佳 {g.bestStreak}）</span></div>
      <div className="gsc-line">正确率 <b>{pct(g)}</b>%<span className="gsc-sub">· 共 {g.plays} 局</span></div>
    </div>
  );
}

export default function GameStatsHub() {
  const [stats, setStats] = useState<JianghuStats | null>(null);

  useEffect(() => {
    setStats(readStats());
  }, []);

  // 近 14 天日历格：hooks 先于任何条件返回（islands 纪律）
  const cells = useMemo(() => {
    const s = stats;
    if (!s) return [];
    return lastNDays(14).map((d) => {
      const inDaily = s.daily.days.includes(d);
      const inTwenty = s.twenty.days.includes(d);
      const e = s.cal?.[d] || {};
      const parts: string[] = [];
      const dw = resWord(e.d);
      const tw = resWord(e.t);
      if (inDaily) parts.push(`每日一谜${dw ? ' ' + dw : ''}`);
      if (inTwenty) parts.push(`二十问答${tw ? ' ' + tw : ''}`);
      const win = e.d === 'w' || e.t === 'w';
      return { day: d, lit: inDaily || inTwenty, win, title: parts.length ? `${dayLabel(d)} · ${parts.join(' · ')}` : dayLabel(d) };
    });
  }, [stats]);

  if (!stats) return null; // 水合前不渲染，避免空态闪现

  const totalPlays = stats.daily.plays + stats.twenty.plays;

  if (totalPlays === 0) {
    return (
      <div className="gsc empty">
        <p className="gsc-empty-line">江湖风平浪静——先去玩一局<a href={`${B}games/daily/`}>每日一谜</a>或<a href={`${B}games/twenty/`}>二十问答</a>，再来晾战绩。</p>
        <span className="gsc-note">战绩仅存本机（localStorage），不上传 · 统计自战绩中心上线起算</span>
        <style>{GSC_CSS}</style>
      </div>
    );
  }

  return (
    <div className="gsc">
      <div className="gsc-card">
        <div className="gsc-head">
          <b>本机战绩</b>
          <span className="gsc-note">仅存本机（localStorage），不上传 · 统计自战绩中心上线起算</span>
        </div>
        <div className="gsc-grid">
          <GameLine name="每日一谜" href={`${B}games/daily/`} g={stats.daily} />
          <GameLine name="二十问答" href={`${B}games/twenty/`} g={stats.twenty} />
          <div className="gsc-cal">
            <span className="gsc-cal-label">答题日历 · 近 14 天</span>
            <div className="gsc-cells">
              {cells.map((c) => (
                <i
                  key={c.day}
                  className={'gsc-cell' + (c.lit ? ' lit' : '') + (c.lit && c.win ? ' win' : '') + (c.day === cells[cells.length - 1].day ? ' today' : '')}
                  title={c.title}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
      <style>{GSC_CSS}</style>
    </div>
  );
}

const GSC_CSS = `
  .gsc { min-height: 20px; }
  .gsc-card { border: 1px solid var(--line-strong); border-radius: 4px; background: rgba(255,255,255,.45); padding: 16px 20px; }
  .gsc-head { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; border-bottom: 1px dashed var(--line); padding-bottom: 10px; }
  .gsc-head b { font-size: 1.05rem; }
  .gsc-note { color: var(--ink-faint); font-size: .75rem; }
  .gsc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-top: 12px; }
  .gsc-game { display: flex; flex-direction: column; gap: 2px; }
  .gsc-name { font-weight: 700; color: var(--ink); }
  .gsc-name:hover { color: var(--seal); }
  .gsc-line { font-size: .9rem; color: var(--ink-light); }
  .gsc-line b { color: var(--seal); font-size: 1.1rem; }
  .gsc-sub { color: var(--ink-faint); font-size: .78rem; }
  .gsc-cal { display: flex; flex-direction: column; gap: 6px; }
  .gsc-cal-label { font-size: .8rem; color: var(--ink-light); }
  .gsc-cells { display: flex; gap: 4px; flex-wrap: wrap; }
  .gsc-cell { width: 18px; height: 18px; border-radius: 3px; background: var(--paper-deep); border: 1px solid var(--line); }
  .gsc-cell.lit { background: var(--ghost); border-color: var(--line-strong); }
  .gsc-cell.lit.win { background: var(--jade); border-color: var(--jade); }
  .gsc-cell.today { outline: 1px dashed var(--seal); outline-offset: 1px; }
  .gsc.empty { display: flex; flex-direction: column; gap: 6px; border: 1px dashed var(--line-strong); border-radius: 4px;
    padding: 18px 20px; color: var(--ink-faint); background: rgba(255,255,255,.3); }
  .gsc-empty-line { margin: 0; color: var(--ink-light); font-size: .95rem; }
  @media (max-width: 480px) { .gsc-grid { grid-template-columns: 1fr; } }
`;
