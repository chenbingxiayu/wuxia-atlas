import { useEffect, useMemo, useRef, useState } from 'react';

/**
 * QaExplorer —— 江湖问答（KG-QA · 预置模板客户端确定性求解，答案必带定位符）。
 * 数据：entity-index / dossiers / arts / weapons / atlas×4（首次提问时懒加载并缓存）。
 * 深链：?t=<模板id>&x=<主词>&y=<副词> 预填并求解（N17 深链协议）。
 */
type Ev = { l: string; v: string; a?: string | null; b?: string | null; code?: string };
type Slice = { title: string; events: Record<string, Ev[]>; persons: Record<string, { n: number; chaps: number[] }> };

const B = (import.meta.env.BASE_URL || '/').endsWith('/')
  ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';

type Tpl = { id: string; label: string; x: string; y?: string; hintX: string; hintY?: string };
const TPLS: Tpl[] = [
  { id: 'killer', label: '谁杀了 X', x: 'X（死者）', hintX: '如 金独异' },
  { id: 'chaps', label: 'X 在哪几回出场', x: 'X（人物）', hintX: '如 练霓裳' },
  { id: 'lineage', label: 'X 的师承 / 传人', x: 'X（人物）', hintX: '如 岳鸣珂' },
  { id: 'sectarts', label: 'Y 派有什么武功', x: 'Y（门派）', hintX: '如 武当派' },
  { id: 'versus', label: 'X 和 Y 交过手吗', x: 'X', y: 'Y', hintX: '如 练霓裳', hintY: '如 铁飞龙' },
  { id: 'artifact', label: 'X 的神兵 / 持物', x: 'X（人物）', hintX: '如 岳鸣珂' },
];

export default function QaExplorer() {
  const [tpl, setTpl] = useState<Tpl>(TPLS[0]);
  const [xv, setX] = useState('');
  const [yv, setY] = useState('');
  const [ans, setAns] = useState<{ text: string; rows: { t: string; href?: string; loc?: string }[]; note: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [suggest, setSuggest] = useState<string[]>([]);
  const data = useRef<Record<string, unknown>>({});

  useEffect(() => {
    getJSON('entity-index.json').then((idx) => {
      const names = (idx?.entities || []).filter((e: { t: string }) => e.t === '@').map((e: { c: string }) => e.c);
      setSuggest(names.slice(0, 400));
    });
    const q = new URLSearchParams(location.search);
    const t = TPLS.find((x) => x.id === q.get('t'));
    if (t) {
      setTpl(t);
      const x = q.get('x') || '';
      const y = q.get('y') || '';
      setX(x);
      setY(y);
      if (x && (!t.y || y)) ask(t, x, y);
    }
  }, []);

  function getJSON(rel: string) {
    const key = rel;
    if (!data.current[key]) {
      data.current[key] = fetch(B + 'data/' + rel).then((r) => (r.ok ? r.json() : null));
    }
    return data.current[key] as Promise<never>;
  }
  async function slices(): Promise<Slice[]> {
    const st = await getJSON('atlas/state.json');
    return Promise.all((st.books || []).map((b: { title: string }) => getJSON(`atlas/${encodeURIComponent(b.title)}.json`)));
  }

  async function ask(t: Tpl = tpl, xvArg = xv, yvArg = yv) {
    if (!xvArg.trim() || (t.y && !yvArg.trim())) return;
    setBusy(true);
    try {
      setAns(await solve(t, xvArg.trim(), yvArg.trim()));
      const q = new URLSearchParams({ t: t.id, x: xvArg.trim() });
      if (t.y) q.set('y', yvArg.trim());
      history.replaceState(null, '', `${location.pathname}?${q.toString()}`);
    } finally {
      setBusy(false);
    }
  }

  async function solve(t: Tpl, X: string, Y: string) {
    if (t.id === 'killer') {
      const hits: { t: string; href?: string; loc?: string }[] = [];
      for (const s of await slices()) {
        for (const evs of Object.values(s.events)) {
          for (const e of evs) {
            if (e.b === X && /杀|诛|毙|刺死/.test(e.v)) {
              hits.push({ t: `${e.a} ${e.v} ${e.b}`, loc: `${s.title}·${e.l}`, href: `${B}books/${encodeURIComponent(s.title)}/${parseInt(e.l, 10)}/` });
            }
          }
        }
      }
      return finish(hits.length ? `击杀 ${X} 的记录：${hits.length} 起（去重后 ${new Set(hits.map((h) => h.t)).size} 名凶手）` : `档案未载：四书事件层没有"${X}"被杀的记录（也可能其死亡为病故/自尽/未直接收录）。`,
        hits.slice(0, 10), '口径：事件表 verb∈{杀,诛,毙} 且宾语=X，L0 定位符。');
    }
    if (t.id === 'chaps') {
      const rows: { t: string; href?: string; loc?: string }[] = [];
      let total = 0;
      for (const s of await slices()) {
        const p = s.persons[X];
        if (p) {
          total += p.n;
          rows.push({ t: `${s.title}：第 ${p.chaps.join('、')} 回（出现 ${p.n} 次）`, href: `${B}books/${encodeURIComponent(s.title)}/${p.chaps[0]}/`, loc: `${s.title}` });
        }
      }
      return finish(rows.length ? `${X} 共出现 ${total} 次，见于 ${rows.length} 部书：` : `档案未载：${X}`, rows, '口径：实体登记表 chapters（@ 实体定位符归并）。');
    }
    if (t.id === 'lineage') {
      const d = await getJSON('dossiers.json');
      const p = (d?.dossiers || []).find((z: { canonical: string; aliases: unknown[] }) =>
        z.canonical === X || (Array.isArray(z.aliases) ? z.aliases : []).some((a: { alias?: string }) => (typeof a === 'string' ? a : a?.alias) === X));
      if (!p) return finish(`档案未载：${X}（人物谱 Top40 之外）`, [], '口径：dossiers.json lineage（动词分级：收徒/传授=strong）。');
      const rows: { t: string; href?: string; loc?: string }[] = [];
      for (const m of p.lineage?.masters || []) rows.push({ t: `师承 ${m.person}（${m.tier}）`, loc: (m.locs || []).join('，'), href: `${B}characters/${encodeURIComponent(m.person)}/` });
      for (const m of p.lineage?.disciples || []) rows.push({ t: `传人 ${m.person}（${m.tier}）`, loc: (m.locs || []).join('，'), href: `${B}characters/${encodeURIComponent(m.person)}/` });
      return finish(rows.length ? `${p.canonical} 的师承谱系（动词分级）：` : `${p.canonical}：无 strong/ok 级师承线索（对话称呼不进事件层，见边界案例库）。`, rows.slice(0, 10), '口径：◇ 传授/拜师事件 + 师承考订；weak=相传级。');
    }
    if (t.id === 'sectarts') {
      const arts = await getJSON('arts.json');
      const rows: { t: string; href?: string; loc?: string }[] = [];
      for (const a of arts?.arts || []) {
        for (const [book, bb] of Object.entries(a.relations || {})) {
          for (const r of (bb as { relations: { st: string; s: string; pred: string; locs: string[] }[] }).relations) {
            if (r.st === '◆' && r.s === X && (r.pred === '拥有' || r.pred === '镇山')) {
              rows.push({ t: `${a.canonical}（${r.pred}）`, loc: `${book}·${(r.locs || [])[0] || ''}`, href: `${B}arts/${encodeURIComponent(a.canonical)}/` });
            }
          }
        }
      }
      rows.sort((p, q2) => (p.t.includes('镇山') ? -1 : 0) - (q2.t.includes('镇山') ? -1 : 0));
      return finish(rows.length ? `${X} 名下武功 ${rows.length} 门（镇山置顶）：` : `档案未载：关系表没有 ${X} 的"拥有/镇山"武功。`, rows.slice(0, 12), '口径：关系表「门派—拥有/镇山—武功」，按证据定位符。');
    }
    if (t.id === 'versus') {
      const hits: { t: string; href?: string; loc?: string }[] = [];
      for (const s of await slices()) {
        for (const evs of Object.values(s.events)) {
          for (const e of evs) {
            if ((e.a === X && e.b === Y) || (e.a === Y && e.b === X)) {
              hits.push({ t: `${e.a} ${e.v} ${e.b}`, loc: `${s.title}·${e.l}`, href: `${B}books/${encodeURIComponent(s.title)}/${parseInt(e.l, 10)}/` });
            }
          }
        }
      }
      return finish(hits.length ? `${X} × ${Y}：同场交手/互动 ${hits.length} 起。` : `${X} × ${Y}：四书事件层无直接交手记录（同场≠同事件，可在时空页查共现）。`,
        hits.slice(0, 10), '口径：事件表主客双向匹配，L0。');
    }
    if (t.id === 'artifact') {
      const w = await getJSON('weapons.json');
      const rows: { t: string; href?: string; loc?: string }[] = [];
      for (const x of w?.weapons || []) {
        const mine = (x.holders || []).some((h: { name: string }) => h.name === X)
          || (x.chain || []).some((e: { persons: string[] }) => e.persons.includes(X));
        if (mine) {
          const strong = (x.chain || []).filter((e: { persons: string[]; conf: string }) => e.conf === 'strong' && e.persons.includes(X))[0];
          rows.push({
            t: `${x.canonical}（${x.kind}${x.grade ? ' · ' + x.grade : ''}）${strong ? ` · [${strong.verb}]` : ''}`,
            loc: strong ? `${strong.book}·${strong.loc}` : `共现×${(x.holders || []).find((h: { name: string }) => h.name === X)?.n ?? ''}`,
            href: `${B}weapons/${encodeURIComponent(x.canonical)}/`,
          });
        }
      }
      rows.sort((p, q2) => (q2.t.includes('[') ? 1 : 0) - (p.t.includes('[') ? 1 : 0));
      return finish(rows.length ? `${X} 的持物/关联名物 ${rows.length} 件（明文流转置顶）：` : `档案未载：神兵表中没有 ${X} 的持物线索。`, rows.slice(0, 10), '口径：神兵表 holders/chain（工具 C）；暂持 ≠ 归属。');
    }
    return finish('未知模板', [], '');
  }

  function finish(text: string, rows: { t: string; href?: string; loc?: string }[], note: string) {
    return { text, rows, note };
  }

  const input = useMemo(() => (
    <div className="qa-row">
      <input className="qa-in" value={xv} list="qa-names" placeholder={tpl.hintX}
        onChange={(e) => setX(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && ask()} aria-label={tpl.x} />
      {tpl.y && (
        <input className="qa-in" value={yv} list="qa-names" placeholder={tpl.hintY}
          onChange={(e) => setY(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && ask()} aria-label={tpl.y} />
      )}
      <button className="qa-btn" onClick={() => ask()} disabled={busy}>{busy ? '求解中…' : '问'}</button>
      <datalist id="qa-names">{suggest.slice(0, 300).map((n) => <option key={n} value={n} />)}</datalist>
    </div>
  ), [tpl, xv, yv, suggest, busy]);

  return (
    <div className="qa-root">
      <div className="qa-tpls">
        {TPLS.map((t) => (
          <button key={t.id} className={'qa-chip' + (t.id === tpl.id ? ' on' : '')}
            onClick={() => { setTpl(t); setAns(null); }}>{t.label}</button>
        ))}
      </div>
      {input}
      {ans && (
        <div className="qa-ans">
          <p className="qa-con">{ans.text}</p>
          <ul>
            {ans.rows.map((r, i) => (
              <li key={i}>
                {r.href ? <a href={r.href}>{r.t}</a> : <b>{r.t}</b>}
                {r.loc && <span className="qa-loc">{r.loc}</span>}
              </li>
            ))}
          </ul>
          <p className="qa-note">{ans.note} · 答案由预构建 JSON 确定性求解，永不幻觉。</p>
        </div>
      )}
      <style>{`
        .qa-root { display: flex; flex-direction: column; gap: 14px; }
        .qa-tpls { display: flex; flex-wrap: wrap; gap: 6px; }
        .qa-chip { font-family: inherit; border: 1px solid #b5a687; background: #fbf8ef; color: #5f584b;
          border-radius: 999px; padding: 4px 14px; font-size: 13.5px; cursor: pointer; }
        .qa-chip.on, .qa-chip:hover { border-color: #a23527; color: #a23527; }
        .qa-row { display: flex; gap: 8px; }
        .qa-in { flex: 1; min-width: 140px; padding: 10px 14px; border: 2px solid #262420; border-radius: 4px;
          font-family: inherit; font-size: 15px; background: #fbf8ef; }
        .qa-btn { font-family: inherit; border: 2px solid #a23527; background: #a23527; color: #fbf8ef;
          border-radius: 4px; padding: 0 26px; font-size: 15px; cursor: pointer; }
        .qa-btn:hover { background: #7e281d; }
        .qa-ans { background: #fbf8ef; border: 1px solid #d8cdb4; border-radius: 4px; padding: 14px 18px; }
        .qa-con { margin: 0 0 8px; font-weight: 700; }
        .qa-ans ul { list-style: none; margin: 0; padding: 0; }
        .qa-ans li { padding: 5px 0; border-bottom: 1px dashed #e6ddc8; font-size: 14px; display: flex; gap: 10px; align-items: baseline; }
        .qa-ans a { color: #31536c; }
        .qa-ans a:hover { color: #a23527; }
        .qa-loc { margin-left: auto; color: #8a8172; font-size: 12px; font-family: ui-monospace, monospace; white-space: nowrap; }
        .qa-note { margin: 10px 0 0; font-size: 12px; color: #8a8172; }
      `}</style>
    </div>
  );
}
