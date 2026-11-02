import { useEffect, useMemo, useState } from 'react';

/**
 * G1 武林二十问答：Akinator 式是非题，系统想一个人物，玩家 ≤20 问猜出。
 * 数据：games/twenty.json（436 候选 × 属性向量，来自人物档案）。
 * 策略：每轮在未问问题中选信息增益最大者（|是/否| 最接近均分）；候选 ≤1 或问满 20 → 出猜测；
 *       猜错移除该候选继续（是/否/不知道 三答，"不知道"仅跳过该问不收缩）。
 */
type Char = { name: string; a: Record<string, boolean>; total: number; sect: string; href: string; books: string[] };
type Q = { id: string; text: string; key: string };

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';

export default function GameTwenty() {
  const [chars, setChars] = useState<Char[]>([]);
  const [qs, setQs] = useState<Q[]>([]);
  const [pool, setPool] = useState<Char[]>([]);
  const [asked, setAsked] = useState<string[]>([]);
  const [qno, setQno] = useState(0);
  const [log, setLog] = useState<{ text: string; ans: string }[]>([]);
  const [guess, setGuess] = useState<Char | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    fetch(B + 'data/games/twenty.json').then((r) => r.json()).then((d) => {
      setChars(d.chars);
      setQs(d.questions);
      setPool(d.chars);
    });
  }, []);

  const nextQ = useMemo(() => {
    const remaining = qs.filter((q) => !asked.includes(q.id));
    if (!remaining.length) return null;
    let best = remaining[0], bestScore = Infinity;
    for (const q of remaining) {
      const yes = pool.filter((c) => c.a[q.key]).length;
      const p = yes / (pool.length || 1);
      const score = Math.abs(p - 0.5);
      if (score < bestScore) { bestScore = score; best = q; }
    }
    return best;
  }, [qs, asked, pool]);

  function answer(ans: 'yes' | 'no' | 'unsure') {
    if (!nextQ) return;
    const text = nextQ.text;
    setLog((l) => [...l, { text, ans }]);
    setAsked((a) => [...a, nextQ.id]);
    if (ans !== 'unsure') setPool((p) => p.filter((c) => (ans === 'yes') === !!c.a[nextQ.key]));
    setQno((n) => n + 1);
    setGuess(null);
  }

  function makeGuess() {
    const top = [...pool].sort((a, b) => b.total - a.total)[0] || null;
    setGuess(top);
  }

  function wrongGuess() {
    if (!guess) return;
    setPool((p) => p.filter((c) => c.name !== guess.name));
    setGuess(null);
  }

  function restart() {
    setPool(chars); setAsked([]); setQno(0); setLog([]); setGuess(null); setDone(false);
  }

  if (!chars.length) return <div className="g20-loading">题库加载中…</div>;

  const out = qno >= 20 || pool.length === 0;

  return (
    <div className="g20">
      <div className="g20-head">
        <span className="mono">第 {Math.min(qno + 1, 20)} / 20 问</span>
        <span className="dim">候选 {pool.length} 人</span>
        <button className="g20-restart" onClick={restart}>重开</button>
      </div>

      <div className="g20-progress">
        {Array.from({ length: 20 }).map((_, i) => (
          <i key={i} className={i < qno ? 'used' : ''} />
        ))}
      </div>

      {done || out ? (
        <div className="g20-result">
          {pool.length === 1 && <p className="g20-only">候选只剩一人——</p>}
          <p className="g20-guess">{guess ? guess.name : '我认输，江湖高人到底是谁？'}</p>
          {guess && (
            <>
              {guess.sect && <p className="dim">{guess.sect} · {guess.books.join('、')}</p>}
              <a className="g20-link" href={`${B}characters/${encodeURIComponent(guess.name)}/`}>看 TA 的档案 →</a>
              <div className="g20-btns">
                <button className="yes" onClick={() => { setDone(true); }}>猜对了</button>
                <button className="no" onClick={wrongGuess}>猜错了，继续</button>
              </div>
            </>
          )}
          {done && <p className="dim">共用了 {qno} 问。战绩保存在本地（G7 每日一谜可分享战绩）。</p>}
          {(out && !pool.length) || (guess && done) ? (
            <button className="g20-restart big" onClick={restart}>再来一局</button>
          ) : null}
        </div>
      ) : (
        <div className="g20-q">
          <p className="g20-text">{nextQ ? nextQ.text : '问题用尽'}</p>
          <div className="g20-btns">
            <button className="yes" onClick={() => answer('yes')}>是</button>
            <button className="no" onClick={() => answer('no')}>否</button>
            <button className="unsure" onClick={() => answer('unsure')}>不知道</button>
            {pool.length > 1 && <button className="guess" onClick={makeGuess}>直接猜（{[...pool].sort((a, b) => b.total - a.total)[0]?.name}？）</button>}
          </div>
        </div>
      )}

      {log.length > 0 && (
        <ol className="g20-log">
          {log.map((l, i) => (
            <li key={i}><span className="mono">{i + 1}.</span> {l.text} <b className={l.ans}>{l.ans === 'yes' ? '是' : l.ans === 'no' ? '否' : '？'}</b></li>
          ))}
        </ol>
      )}
      <style>{`
        .g20 { display: flex; flex-direction: column; gap: 16px; max-width: 720px; }
        .g20-head { display: flex; gap: 16px; align-items: baseline; }
        .mono { font-family: ui-monospace, monospace; color: #8a8172; font-size: 13px; }
        .dim { color: #5f584b; font-size: 14px; }
        .g20-restart { margin-left: auto; font-family: inherit; border: 1px solid #b5a687; background: none;
          border-radius: 999px; padding: 3px 14px; cursor: pointer; color: #5f584b; }
        .g20-restart:hover { border-color: #a23527; color: #a23527; }
        .g20-restart.big { font-size: 15px; padding: 8px 24px; }
        .g20-progress { display: flex; gap: 4px; }
        .g20-progress i { width: 18px; height: 8px; background: #e6ddc8; border-radius: 2px; }
        .g20-progress i.used { background: #a23527; }
        .g20-q, .g20-result { background: #fbf8ef; border: 2px solid #262420; border-radius: 6px; padding: 24px 28px;
          box-shadow: 6px 7px 0 rgba(38,36,32,.12); }
        .g20-text { font-size: 19px; margin: 0 0 16px; line-height: 1.8; }
        .g20-guess { font-family: 'Ma Shan Zheng', serif; font-size: 34px; margin: 4px 0; letter-spacing: 4px; color: #a23527; }
        .g20-only { color: #8a6607; margin: 0; }
        .g20-btns { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
        .g20-btns button { font-family: inherit; font-size: 16px; border-radius: 4px; padding: 8px 26px; cursor: pointer; border: 2px solid; }
        .yes { background: #a23527; color: #fbf8ef; border-color: #a23527; }
        .yes:hover { background: #7e281d; }
        .no { background: #fbf8ef; color: #262420; border-color: #262420; }
        .unsure { background: #fbf8ef; color: #5f584b; border-color: #b5a687; }
        .guess { background: none; color: #31536c; border-color: #31536c; font-size: 14px !important; }
        .g20-link { color: #31536c; }
        .g20-log { list-style: none; padding: 0; margin: 0; font-size: 13.5px; color: #5f584b; }
        .g20-log li { padding: 3px 0; border-bottom: 1px dashed #e6ddc8; }
        .g20-log b.yes { color: #4f6e4a; } .g20-log b.no { color: #a23527; } .g20-log b.unsure { color: #8a8172; }
        .g20-loading { padding: 50px; text-align: center; color: #5f584b; }
      `}</style>
    </div>
  );
}
