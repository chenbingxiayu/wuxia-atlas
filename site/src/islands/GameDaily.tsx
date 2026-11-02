import { useEffect, useMemo, useState } from 'react';

/**
 * G7 每日一谜：日期哈希全网同题（零后端），3 次机会 + 三级提示，emoji 战绩本地分享。
 * 题库：games/daily.json（136 题，答案唯一且带定位符——KB 确定性 = 零幻觉题库）。
 * 选题：djb2(YYYYMMDD) mod N——任何设备当天同题；战绩存 localStorage，分享码纯文本。
 */
type Puzzle = { id: string; type: string; q: string; answer: string; hints: string[]; loc: string; explain: string };

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';
const LS = 'wuxia-daily';

function todayKey() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
}
function djb2(s: string) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h;
}
function norm(s: string) {
  return s.trim().replace(/\s+/g, '');
}

export default function GameDaily() {
  const [bank, setBank] = useState<Puzzle[] | null>(null);
  const [tries, setTries] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [state, setState] = useState<'play' | 'win' | 'lose'>('play');
  const [copied, setCopied] = useState(false);

  const day = todayKey();
  const puzzle = useMemo(() => {
    if (!bank?.length) return null;
    return bank[djb2(day) % bank.length];
  }, [bank, day]);

  useEffect(() => {
    fetch(B + 'data/games/daily.json').then((r) => r.json()).then((d) => setBank(d.puzzles));
    try {
      const hist = JSON.parse(localStorage.getItem(LS) || '{}');
      if (hist[day]) {
        setTries(hist[day].tries || []);
        setState(hist[day].state || 'play');
      }
    } catch { /* 忽略本地存档错误 */ }
  }, []);

  function persist(nextTries: string[], nextState: string) {
    try {
      const hist = JSON.parse(localStorage.getItem(LS) || '{}');
      hist[day] = { tries: nextTries, state: nextState };
      localStorage.setItem(LS, JSON.stringify(hist));
    } catch { /* 无痕模式等 */ }
  }

  function submit() {
    if (!puzzle || state !== 'play' || !input.trim()) return;
    const ok = norm(input) === norm(puzzle.answer);
    const nextTries = [...tries, ok ? 'win' : 'miss'];
    setTries(nextTries);
    setInput('');
    if (ok) { setState('win'); persist(nextTries, 'win'); return; }
    if (nextTries.length >= 3) { setState('lose'); persist(nextTries, 'lose'); }
  }

  function share() {
    const marks = tries.map((t) => (t === 'win' ? '🟩' : '🟥')).join('');
    const text = `江湖每日一谜 ${day.slice(0, 4)}/${day.slice(4, 6)}/${day.slice(6, 8)} ${marks || '⬜'}\n${puzzle?.q}`;
    navigator.clipboard?.writeText(text).then(() => setCopied(true)).catch(() => setCopied(false));
  }

  if (!puzzle) return <div className="gd-loading">出题中…</div>;
  const hintsShown = Math.min(tries.length, puzzle.hints.length);
  const lost = state === 'lose';

  return (
    <div className="gd">
      <div className="riddle">
        <div className="rh">
          <b className="gd-q">{puzzle.q}</b>
          <span className="mono gd-day">{day.slice(0, 4)}/{day.slice(4, 6)}/{day.slice(6, 8)} · 第 {tries.length}/3 次</span>
        </div>

        {puzzle.hints.slice(0, state === 'play' ? hintsShown : puzzle.hints.length).map((h, i) => (
          <div className="hint" key={i}><span className="hn">提示 {i + 1}</span>{h}</div>
        ))}

        {state === 'play' ? (
          <div className="gd-row">
            <input className="gd-in" value={input} placeholder="写下答案（人名/门派）"
              onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submit()} aria-label="答案" />
            <button className="gd-btn" onClick={submit}>作答</button>
          </div>
        ) : (
          <div className={'answer ' + (state === 'win' ? 'ok' : 'no')}>
            {state === 'win' ? `恭喜！答案就是「${puzzle.answer}」。` : `今日谜底：「${puzzle.answer}」。`}
            <span className="gd-loc">{puzzle.loc}</span>
            <p className="gd-explain">{puzzle.explain}</p>
          </div>
        )}

        {tries.length > 0 && state === 'play' && (
          <p className="dim">已有 {tries.length} 次未中——再错一次将揭晓 {puzzle.hints.length > hintsShown ? '新提示' : '答案'}。</p>
        )}

        <div className="share">
          <button className="gd-btn ghost" onClick={share}>{copied ? '已复制 ✓' : '复制战绩'}</button>
          <span className="emoj">{tries.map((t) => (t === 'win' ? '🟩' : '🟥')).join('')}</span>
          <span className="dim">{state === 'win' ? `用了 ${tries.length} 次` : lost ? '明日再战' : '本地存档 · 分享码纯文本'}</span>
        </div>
      </div>

      <p className="fine">
        选题 = 日期哈希（djb2）对题库取模——<b>全网同题、无需服务器</b>；题库 {bank?.length} 道全部由图谱生成，
        每题答案唯一且带「书·回」定位符。战绩仅存本地（localStorage），分享码为纯文本 emoji。
      </p>

      <style>{`
        .gd { display: flex; flex-direction: column; gap: 14px; }
        .riddle { max-width: 720px; margin: 0 auto; width: 100%; background: #fbf8ef; border: 2px solid #262420;
          border-radius: 6px; padding: 26px 32px; box-shadow: 6px 7px 0 rgba(38,36,32,.12); }
        .rh { display: flex; justify-content: space-between; gap: 12px; align-items: baseline;
          border-bottom: 1px solid #d8cdb4; padding-bottom: 12px; }
        .gd-q { font-size: 18px; line-height: 1.8; }
        .mono { font-family: ui-monospace, monospace; color: #8a8172; font-size: 12px; white-space: nowrap; }
        .hint { display: flex; gap: 12px; align-items: baseline; padding: 8px 0; border-bottom: 1px dashed #e6ddc8; font-size: 14.5px; }
        .hn { color: #8a8172; font-family: ui-monospace, monospace; font-size: 12px; white-space: nowrap; }
        .gd-row { display: flex; gap: 10px; margin-top: 16px; }
        .gd-in { flex: 1; padding: 10px 16px; border: 2px solid #262420; border-radius: 4px; font-family: inherit; font-size: 15px; background: #fbf8ef; }
        .gd-btn { font-family: inherit; border: 2px solid #a23527; background: #a23527; color: #fbf8ef;
          border-radius: 4px; padding: 0 24px; font-size: 15px; cursor: pointer; }
        .gd-btn:hover { background: #7e281d; }
        .gd-btn.ghost { background: none; color: #5f584b; border-color: #b5a687; font-size: 13px; padding: 6px 16px; }
        .answer { margin-top: 16px; border-radius: 4px; padding: 14px 18px; font-size: 15px; border: 1px solid; }
        .answer.ok { background: #eef2e6; border-color: #4f6e4a; }
        .answer.no { background: #f6e8d9; border-color: #a23527; }
        .gd-loc { margin-left: 10px; font-family: ui-monospace, monospace; color: #8a8172; font-size: 12px; }
        .gd-explain { margin: 8px 0 0; font-size: 13px; color: #5f584b; }
        .dim { color: #8a8172; font-size: 13px; }
        .share { display: flex; gap: 12px; align-items: center; margin-top: 18px; }
        .emoj { font-size: 16px; }
        .fine { color: #8a8172; font-size: 12.5px; line-height: 1.9; max-width: 720px; margin: 0 auto; text-align: center; }
        .fine b { color: #5f584b; }
        .gd-loading { padding: 50px; text-align: center; color: #5f584b; }
      `}</style>
    </div>
  );
}
