import { useEffect, useMemo, useState } from 'react';
import {
  dsp,
  dspText,
  fetchDisplayLookup,
  type DisplayLookup,
} from '../lib/display-shared';
import { recordResult } from '../lib/game-stats';

/**
 * G7 每日一谜：日期哈希全网同题（零后端），3 次机会 + 三级提示，emoji 战绩本地分享。
 * 题库：games/daily.json（136 题，答案唯一且带定位符——KB 确定性 = 零幻觉题库）。
 * 选题：djb2(YYYYMMDD) mod N——任何设备当天同题；战绩存 localStorage，分享码纯文本。
 */
type Puzzle = { id: string; type: string; q: string; answer: string; hints: string[]; loc: string; explain: string };

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';
const LS = 'wuxia-daily';

// 与 src/lib/links.ts chapterHref 同式互指（island 内不 import 全量数据版 helper）
const chapHref = (base: string, book: string, loc: string) => {
  const m = loc.match(/\d+/);
  return m ? `${base}books/${encodeURIComponent(book)}/${m[0].padStart(3, '0')}/` : null;
};

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
  const [lookup, setLookup] = useState<DisplayLookup>({ display: {}, canonicalOf: {} });

  const day = todayKey();
  const puzzle = useMemo(() => {
    if (!bank?.length) return null;
    return bank[djb2(day) % bank.length];
  }, [bank, day]);

  useEffect(() => {
    Promise.all([
      fetch(B + 'data/games/daily.json').then((r) => r.json()),
      fetchDisplayLookup(B),
    ]).then(([d, lk]) => {
      setBank(d.puzzles);
      setLookup(lk);
    });
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
    // 答案接受 canonical 与 display 两种写法（展示层与规范层分离，判定口径不变）
    const accepted = new Set(
      [puzzle.answer, dsp(lookup.display, puzzle.answer), ...(puzzle.aliases || [])]
        .filter(Boolean)
        .map((x) => norm(dsp(lookup.display, x))),
    );
    const ok = accepted.has(norm(input));
    const nextTries = [...tries, ok ? 'win' : 'miss'];
    setTries(nextTries);
    setInput('');
    // E1 战绩中心：仅结算（win/lose 落定）时记一局——state==='play' 门卫保证每局只写一次；
    // 旧 wuxia-daily 每日存档不迁移，战绩自战绩中心上线起算
    if (ok) { setState('win'); persist(nextTries, 'win'); recordResult('daily', true, day); return; }
    if (nextTries.length >= 3) { setState('lose'); persist(nextTries, 'lose'); recordResult('daily', false, day); }
  }

  const share = () => {
    const marks = tries.map((t) => (t === 'win' ? '🟩' : '🟥')).join('');
    const text = `江湖每日一谜 ${day.slice(0, 4)}/${day.slice(4, 6)}/${day.slice(6, 8)} ${marks || '⬜'}\n${puzzle ? dspText(lookup.display, puzzle.q) : ''}`;
    navigator.clipboard?.writeText(text).then(() => setCopied(true)).catch(() => setCopied(false));
  };

  // W1-T1：useMemo 必须先于任何条件返回——hooks 调用数在「出题中」态与就绪态之间保持恒定，否则 React #310
  // loc 形如「书名·章:行」（daily.json 均带书名前缀、无独立 book 字段）——split('·') 取书名与章，解析失败降级纯文本
  const locHref = useMemo(() => {
    if (!puzzle) return null;
    const [book, chap] = puzzle.loc.split('·');
    return book && chap ? chapHref(B, book, chap) : null;
  }, [puzzle]);

  if (!puzzle) return <div className="gd-loading">出题中…</div>;
  const hintsShown = Math.min(tries.length, puzzle.hints.length);
  const lost = state === 'lose';

  return (
    <div className="gd">
      <div className="riddle">
        <div className="rh">
          <b className="gd-q">{dspText(lookup.display, puzzle.q)}</b>
          <span className="mono gd-day">{day.slice(0, 4)}/{day.slice(4, 6)}/{day.slice(6, 8)} · 第 {tries.length}/3 次</span>
        </div>

        {puzzle.hints.slice(0, state === 'play' ? hintsShown : puzzle.hints.length).map((h, i) => (
          <div className="hint" key={i}><span className="hn">提示 {i + 1}</span>{dspText(lookup.display, h)}</div>
        ))}

        {state === 'play' ? (
          <div className="gd-row">
            <input className="gd-in" value={input} placeholder="写下答案（人名/门派）"
              onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submit()} aria-label="答案" />
            <button className="gd-btn" onClick={submit}>作答</button>
          </div>
        ) : (
          <div className={'answer ' + (state === 'win' ? 'ok' : 'no')}>
            {state === 'win' ? `恭喜！答案就是「${dsp(lookup.display, puzzle.answer)}」。` : `今日谜底：「${dsp(lookup.display, puzzle.answer)}」。`}
            {locHref
              ? <a className="gd-loc mono" href={locHref}>{puzzle.loc} →</a>
              : <span className="gd-loc">{puzzle.loc}</span>}
            <p className="gd-explain">{dspText(lookup.display, puzzle.explain)}</p>
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
          border-radius: 6px; padding: 26px 32px; box-shadow: 6px 7px 0 rgba(38,36,32,.12); box-sizing: border-box; }
        .rh { display: flex; justify-content: space-between; gap: 12px; align-items: baseline;
          border-bottom: 1px solid #d8cdb4; padding-bottom: 12px; }
        .gd-q { font-size: 18px; line-height: 1.8; }
        .mono { font-family: ui-monospace, monospace; color: #8a8172; font-size: 12px; white-space: nowrap; }
        .hint { display: flex; gap: 12px; align-items: baseline; padding: 8px 0; border-bottom: 1px dashed #e6ddc8; font-size: 14.5px; }
        .hn { color: #8a8172; font-family: ui-monospace, monospace; font-size: 12px; white-space: nowrap; }
        .gd-row { display: flex; gap: 10px; margin-top: 16px; }
        .gd-in { flex: 1; min-width: 0; padding: 10px 16px; border: 2px solid #262420; border-radius: 4px; font-family: inherit; font-size: 15px; background: #fbf8ef; }
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
