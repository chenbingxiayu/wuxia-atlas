import { useEffect, useState } from 'react';

/**
 * GameTest —— 测测你是梁书里的谁（starter 版）。
 * 10 道性格选择题（不考知识）→ 目标画像 → 与 twenty.json chars 属性最近匹配 → 人物卡。
 * 数据在客户端 useEffect 加载（SSR 预渲染时无 fetch）。
 */
type Char = { name: string; books: string[]; sect: string; a: Record<string, boolean>; total: number };
type Question = { q: string; opts: { text: string; want: Record<string, boolean | string> }[] };

const QUESTIONS: Question[] = [
  { q: '江湖初入，你更想加入——', opts: [
    { text: '名门正派，有师承有规矩', want: { _group: '名门正派', master: true } },
    { text: '绿林山寨，快意恩仇', want: { _group: '绿林', master: false, kills: true } },
    { text: '独来独往，自在逍遥', want: { _group: '散', master: false, cross: true } },
  ] },
  { q: '仇家上门，你的第一反应——', opts: [
    { text: '先动手，江湖没有第二次机会', want: { kills: true } },
    { text: '先讲理，理讲不通再动手', want: { master: true, kills: false } },
    { text: '先避其锋芒，日后再算', want: { slain: true } },
  ] },
  { q: '面对朝廷征召——', opts: [
    { text: '坚决不仕，反到底', want: { _group: '绿林', top: true } },
    { text: '可以合作，但保持底线', want: { _group: '名门正派' } },
    { text: '进入体制，护一方平安', want: { _group: '朝廷', top: true } },
  ] },
  { q: '你最看重——', opts: [
    { text: '儿女情长，为一人可弃江湖', want: { cross: true, top: true } },
    { text: '师门恩义，重于生死', want: { master: true, disciple: true } },
    { text: '武道极致，一生只求更强', want: { n: true, top: true } },
  ] },
  { q: '理想的江湖生活方式——', opts: [
    { text: '隐居深山，不问世事', want: { cross: true, n: false } },
    { text: '行走天下，管不平之事', want: { top: true, kills: true } },
    { text: '开宗立派，传承衣钵', want: { disciple: true, top: true } },
  ] },
  { q: '神兵利器当前——', opts: [
    { text: '宝剑赠英雄，收下', want: { top: true } },
    { text: '身外之物，不动心', want: { n: false } },
    { text: '夺来送给心上人', want: { cross: true } },
  ] },
  { q: '你的武功路数偏好——', opts: [
    { text: '剑法，正兵之首', want: { _kw: '剑' } },
    { text: '掌法拳脚，硬桥硬马', want: { _kw: '掌' } },
    { text: '暗器轻功，另辟蹊径', want: { kills: false, slain: false } },
  ] },
  { q: '徒弟问你江湖最重要的东西——', opts: [
    { text: '侠义二字', want: { disciple: true, top: true } },
    { text: '活着比什么都重要', want: { slain: true } },
    { text: '随心而行，莫问对错', want: { _group: '绿林' } },
  ] },
  { q: '一场躲不过的大战前夜——', opts: [
    { text: '独自练剑到天明', want: { top: true, master: true } },
    { text: '与挚友痛饮达旦', want: { cross: true, kills: true } },
    { text: '安睡如常，胜败皆命', want: { n: false } },
  ] },
  { q: '你希望后人如何记得你——', opts: [
    { text: '一代大侠，侠义传千古', want: { top: true, master: true } },
    { text: '亦正亦邪，活得潇洒', want: { _group: '绿林', cross: true } },
    { text: '无名无姓，来去自由', want: { top: false, n: false } },
  ] },
];

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';

export default function GameTest() {
  const [chars, setChars] = useState<Char[] | null>(null);
  const [step, setStep] = useState(0);
  const [want, setWant] = useState<Record<string, unknown>>({});
  const [result, setResult] = useState<Char | null>(null);

  useEffect(() => {
    fetch(`${B}data/games/twenty.json`).then((r) => r.json()).then((d) => setChars(d.chars || []));
  }, []);

  const answer = (wantPart: Record<string, boolean | string>) => {
    const merged = { ...want, ...wantPart };
    const nextStep = step + 1;
    setWant(merged);
    if (nextStep >= QUESTIONS.length) {
      matchBest(merged);
    } else {
      setStep(nextStep);
    }
  };

  function matchBest(target: Record<string, unknown>) {
    if (!chars || !chars.length) { setResult(null); return; }
    const group = String(target._group || '');
    let best: Char | null = null;
    let bestScore = -Infinity;
    for (const c of chars) {
      let score = 0;
      for (const [k, v] of Object.entries(target)) {
        if (k.startsWith('_')) continue;
        if (typeof v === 'boolean' && c.a[k] === v) score += 1;
      }
      const cg = String(c.sect || '');
      if (group === '名门正派' && cg.endsWith('派')) score += 1.5;
      if (group === '绿林' && (cg.includes('帮') || cg.includes('寨') || cg === '散人')) score += 1.5;
      if (group === '朝廷' && (cg.includes('军') || cg.includes('卫') || cg.includes('大内'))) score += 1.5;
      if (group === '散' && !cg) score += 1;
      if (score > bestScore) { bestScore = score; best = c; }
    }
    setResult(best);
  }

  const restart = () => { setStep(0); setWant({}); setResult(null); };

  if (!chars) return <div className="gt-loading">题库加载中…</div>;

  if (result) {
    const displaySect = result.sect || '无门派 · 逍遥散人';
    return (
      <div className="gt-result">
        <p className="gt-label">你像极了——</p>
        <h3 className="gt-name">{result.name}</h3>
        <div className="gt-card">
          <div className="gt-row"><span className="k">门派</span><b>{displaySect}</b></div>
          <div className="gt-row"><span className="k">行经</span><span>{result.books.join(' · ')}</span></div>
          <div className="gt-row"><span className="k">出场</span><span>{result.total.toLocaleString()} 次</span></div>
          <div className="gt-row"><span className="k">武评</span><span>考订中——座次将在武评校订后收录</span></div>
        </div>
        <div className="gt-links">
          <a href={`${B}characters/${encodeURIComponent(result.name)}/`}>人物档案 →</a>
          <button className="gt-re" onClick={restart}>再测一次</button>
        </div>
        <p className="fine">匹配依据：你的性格答案与人物档案属性最近契合（非知识考核 · 结果仅供一乐）。</p>
      </div>
    );
  }

  const q = QUESTIONS[step];
  return (
    <div className="gt">
      <div className="gt-head">
        <b>第 {step + 1} / {QUESTIONS.length} 题</b>
        <div className="gt-bar"><div className="gt-fill" style={{ width: `${(step / QUESTIONS.length) * 100}%` }} /></div>
      </div>
      <p className="gt-q">{q.q}</p>
      <div className="gt-opts">
        {q.opts.map((o) => (
          <button key={o.text} onClick={() => answer(o.want)}>{o.text}</button>
        ))}
      </div>
      <p className="fine">性格测试 · 不考知识——你的答案只用来匹配气质最接近的江湖人。</p>
      <style>{`
        .gt { display: flex; flex-direction: column; gap: 14px; }
        .gt-loading { padding: 40px; text-align: center; color: #5f584b; }
        .gt-head { display: flex; align-items: center; gap: 14px; }
        .gt-head b { color: #a63a2b; }
        .gt-bar { flex: 1; height: 10px; border: 1px solid #b5a687; border-radius: 999px; overflow: hidden; background: #f5efe4; }
        .gt-fill { height: 100%; background: #a63a2b; }
        .gt-q { font-size: 17px; font-weight: 700; font-family: 'Noto Serif SC', serif; margin: 0; }
        .gt-opts { display: flex; flex-direction: column; gap: 8px; }
        .gt-opts button { text-align: left; border: 1.5px solid #b9ab90; background: #fbf8ef; border-radius: 4px; padding: 9px 14px; font-family: inherit; font-size: 14px; cursor: pointer; color: #2b2b2b; }
        .gt-opts button:hover { border-color: #a63a2b; color: #a63a2b; }
        .gt-result { background: #fbf8ef; border: 1px solid #b8860b; border-radius: 4px; padding: 18px 22px; }
        .gt-label { margin: 0; color: #8a8172; font-size: 13px; }
        .gt-name { margin: 4px 0 10px; font-family: 'Noto Serif SC', serif; font-size: 30px; letter-spacing: 4px; color: #a63a2b; }
        .gt-card { border-top: 1px dashed #d8cdb8; padding-top: 10px; display: flex; flex-direction: column; gap: 6px; font-size: 14px; }
        .gt-row .k { display: inline-block; min-width: 3.5em; color: #8a8172; font-size: 12.5px; }
        .gt-links { margin-top: 14px; display: flex; gap: 16px; align-items: center; }
        .gt-links a { color: #31536c; font-weight: 700; }
        .gt-re { font-family: inherit; border: 1px solid #b5a687; background: none; border-radius: 999px; padding: 3px 16px; cursor: pointer; font-size: 13px; color: #5f584b; }
        .fine { font-size: 12px; color: #8a8172; }
      `}</style>
    </div>
  );
}
