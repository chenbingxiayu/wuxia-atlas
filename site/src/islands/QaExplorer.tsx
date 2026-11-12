import { useEffect, useMemo, useRef, useState } from 'react';
import {
  buildDisplayLookup,
  dsp,
  isMainPerson,
  toCanonical,
  type DisplayLookup,
} from '../lib/display-shared';
import { route } from '../lib/qa-router-rules';
import { tierLabel } from '../lib/tiers';

/**
 * QaExplorer —— 江湖问答（KG-QA · 预置模板客户端确定性求解，答案必带定位符）。
 * 数据：entity-index / dossiers / arts / weapons / atlas×4（首次提问时懒加载并缓存）。
 * 深链：?t=<模板id>&x=<主词>&y=<副词> 预填并求解（N17 深链协议）+ 答案卡「复制链接」一键复制。
 * NL 路由（决策 5，规则式）：置顶自然语言框 → lib/qa-router-rules route() 分发模板，
 *   只有路由无生成；未命中回落模板 chips + 「没听懂」提示。页首示例卡点即查（F4）。
 */

/** F4 示例卡：页内预置 3 条真实可查问题（点即走 NL 路由）。 */
const EXAMPLES = ['谁杀了楚昭南', '练霓裳去过哪些地方', '卓一航和练霓裳交过手吗'];
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
  { id: 'places', label: 'X 去过哪些地方', x: 'X（人物）', hintX: '如 练霓裳' },
];

export default function QaExplorer() {
  const [tpl, setTpl] = useState<Tpl>(TPLS[0]);
  const [xv, setX] = useState('');
  const [yv, setY] = useState('');
  const [ans, setAns] = useState<{ text: string; rows: { t: string; href?: string; loc?: string }[]; note: string; warn?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [suggest, setSuggest] = useState<string[]>([]);
  const data = useRef<Record<string, unknown>>({});
  // 展示层（B-1/B-2）：canonical 做数据检索，display 做展示文案；输入两者皆可（toCanonical 归一）。
  const lookupRef = useRef<DisplayLookup>({ display: {}, canonicalOf: {} });
  const [lookup, setLookup] = useState<DisplayLookup>({ display: {}, canonicalOf: {} });
  // NL 路由框（决策 5）+ 复制链接（决策 6）+ miss 提示。
  const [nlv, setNl] = useState('');
  const [miss, setMiss] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyNote, setCopyNote] = useState('');
  const entsRef = useRef<Array<{ c?: string; display?: string }>>([]);
  const namesRef = useRef<string[] | null>(null);

  useEffect(() => {
    getJSON('entity-index.json').then((idx) => {
      const entities = idx?.entities || [];
      entsRef.current = entities;
      const lk = buildDisplayLookup(entities);
      lookupRef.current = lk;
      setLookup(lk);
      const names = entities
        .filter((e: { t: string }) => e.t === '@')
        .map((e: { c: string; display?: string }) => e.display || e.c);
      setSuggest(names.slice(0, 400));
    });
    const q = new URLSearchParams(location.search);
    const t = TPLS.find((x) => x.id === q.get('t'));
    if (t) {
      setTpl(t);
      const x = q.get('x') || '';
      const y = q.get('y') || '';
      const cx = toCanonical(lookupRef.current, x);
      const cy = toCanonical(lookupRef.current, y);
      setX(dsp(lookupRef.current.display, cx));
      setY(dsp(lookupRef.current.display, cy));
      if (cx && (!t.y || cy)) ask(t, cx, cy);
    }
  }, []);

  function getJSON(rel: string) {
    const key = rel;
    if (!data.current[key]) {
      data.current[key] = fetch(B + 'data/' + rel).then((r) => (r.ok ? r.json() : null));
    }
    return data.current[key] as Promise<never>;
  }
  // spec 002/003：预索引契约——轻索引（chaps/places）+ 按书事件文件（qa-events/<书>.json）
  let qaIndex: any = null;
  async function getIndex(): Promise<any> {
    if (!qaIndex) qaIndex = await getJSON('qa-index.json');
    return qaIndex;
  }
  async function allEvents(): Promise<{ title: string; events: Record<string, Ev[]> }[]> {
    const idx = await getIndex();
    const files = (idx.meta?.events_files || []) as { book: string; file: string }[];
    return Promise.all(files.map(async (f) => {
      const d = await getJSON(f.file.replace(/^qa-events\//, 'qa-events/'));
      const out: Record<string, Ev[]> = {};
      for (const r of d.events || []) {
        const ch = String(r.l || '').slice(0, 3);
        (out[ch] ||= []).push({ l: r.l, v: r.v, a: r.a, b: r.b, code: r.code });
      }
      return { title: f.book, events: out };
    }));
  }

  async function ask(t: Tpl = tpl, xvArg = xv, yvArg = yv) {
    // 输入归一：用户可输入展示名（康熙）或规范名（玄烨）——检索一律用 canonical，URL 深链写 canonical。
    const X = toCanonical(lookupRef.current, xvArg);
    const Y = toCanonical(lookupRef.current, yvArg);
    if (!X || (t.y && !Y)) return;
    setBusy(true);
    try {
      setAns(await solve(t, X, Y));
      const q = new URLSearchParams({ t: t.id, x: X });
      if (t.y) q.set('y', Y);
      history.replaceState(null, '', `${location.pathname}?${q.toString()}`);
    } finally {
      setBusy(false);
    }
  }

  /**
   * 路由实体归一（注入 qa-router-rules）：先走 toCanonical（display→canonical），
   * 未命中再在残留串内做多词取最长命中（扫已知实体名，长名优先）；
   * 仍失败返回原串——既有「档案未载」路径兜底，不阻断查询。
   */
  function routeResolve(raw: string): string {
    const s = (raw || '').trim();
    if (!s) return '';
    const direct = toCanonical(lookupRef.current, s);
    if (direct !== s) return direct;
    if (!namesRef.current) {
      namesRef.current = entsRef.current
        .flatMap((e) => [e.c, e.display] as (string | undefined)[])
        .filter((n): n is string => !!n && n.length >= 2)
        .sort((a, b) => b.length - a.length);
    }
    for (const n of namesRef.current) {
      if (s.includes(n)) return toCanonical(lookupRef.current, n);
    }
    return s;
  }

  /** NL 路由提交：命中→直接调对应模板求解；未命中→「没听懂」提示（不影响模板 chips 手动路径）。 */
  async function askNL(text?: string) {
    const q = (text !== undefined ? text : nlv).trim();
    if (!q) return;
    if (text !== undefined) setNl(text);
    const hit = route(q, routeResolve);
    const t = hit ? TPLS.find((z) => z.id === hit.template) : undefined;
    if (!hit || !hit.x || !t) {
      setMiss(true);
      return;
    }
    const X = toCanonical(lookupRef.current, hit.x);
    const Y = hit.y ? toCanonical(lookupRef.current, hit.y) : '';
    if (t.y && !Y) {
      setMiss(true);
      return;
    }
    setMiss(false);
    setTpl(t);
    setX(dsp(lookupRef.current.display, X));
    if (t.y) setY(dsp(lookupRef.current.display, Y));
    await ask(t, X, Y);
  }

  /** 决策 6：一键复制当前答案深链（?t=&x=&y=）——clipboard 优先，失败降级选中提示，均不抛错。 */
  async function copyLink() {
    const X = toCanonical(lookupRef.current, xv);
    const q = new URLSearchParams({ t: tpl.id, x: X });
    if (tpl.y && yv) q.set('y', toCanonical(lookupRef.current, yv));
    const url = `${location.origin}${location.pathname}?${q.toString()}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setCopyNote('');
    } catch {
      try {
        const ta = document.createElement('textarea');
        ta.value = url;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        setCopied(true);
        setCopyNote('');
      } catch {
        setCopied(false);
        setCopyNote(url);
      }
    }
    window.setTimeout(() => setCopied(false), 1600);
  }

  async function solve(t: Tpl, X: string, Y: string) {
    // X/Y 为 canonical（检索用）；dx/dy 为展示名（文案用），二者分离。
    const dx = dsp(lookupRef.current.display, X);
    const dy = dsp(lookupRef.current.display, Y);
    if (t.id === 'killer') {
      const hits: { t: string; href?: string; loc?: string }[] = [];
      for (const s of await allEvents()) {
        for (const evs of Object.values(s.events)) {
          for (const e of evs) {
            if (e.b === X && /杀|诛|毙|刺死/.test(e.v)) {
              hits.push({ t: `${dsp(lookup.display, e.a)} ${e.v} ${dsp(lookup.display, e.b)}`, loc: `${s.title}·${e.l}`, href: `${B}books/${encodeURIComponent(s.title)}/${String(parseInt(e.l, 10)).padStart(3, '0')}/` });
            }
          }
        }
      }
      // spec 005 T3：audit-r1 宽松核验存疑标注（问答展示记录不静默；games 才过滤）
      let warn = '';
      const amb = ((await getJSON('audit-r1.json'))?.ambiguous || []) as any[];
      const hit = amb.find((a: any) => a.name === X);
      if (hit) warn = `死者此后仍在出场（${hit.live_n} 次）——剧情保护或误标`;
      return finish(hits.length ? `击杀 ${dx} 的记录：${hits.length} 起（去重后 ${new Set(hits.map((h) => h.t)).size} 名凶手）` : `档案未载：事件层没有"${dx}"被杀的记录（也可能其死亡为病故/自尽/未直接收录）。`,
        hits.slice(0, 10), `口径：事件表 verb∈{杀,诛,毙} 且宾语=${dx}，L0 定位符。`, warn);
    }
    if (t.id === 'chaps') {
      const idx = await getIndex();
      const rec = idx.persons?.[X];
      if (!rec) return finish(`档案未载：${dx}`, [], '口径：qa-index 人物索引（atlas 切片派生）。');
      const rows: { t: string; href?: string; loc?: string }[] = Object.entries(rec.chaps as Record<string, number[]>).map(([book, chaps]) => ({
        t: `${book}：第 ${chaps.join('、')} 回（${chaps.length} 回）`,
        href: `${B}books/${encodeURIComponent(book)}/${String(chaps[0]).padStart(3, '0')}/`,
        loc: book,
      }));
      return finish(rows.length ? `${dx} 见于 ${rows.length} 部书：` : `档案未载：${dx}`, rows, '口径：qa-index 人物索引（L0）。');
    }
    if (t.id === 'places') {
      const idx = await getIndex();
      const rec = idx.persons?.[X];
      const rows: { t: string; href?: string; loc?: string }[] = (rec?.places || []).map((p: any) => ({
        t: `${p.name} · 首见 ${p.first}${p.real === false ? '（虚构 · 不落图）' : ''}`,
        href: `${B}atlas/?book=${encodeURIComponent(p.first.split('·')[0])}&place=${encodeURIComponent(p.name)}`,
      }));
      return finish(rows.length ? `${dx} 的行经之地（按故事顺序）：` : `档案未载：没有 ${dx} 的地点锚。`, rows.slice(0, 12),
        '口径：atlas 切片 person 索引（L0）。虚构地名不落图——推理偏移管线筹备中。');
    }
    if (t.id === 'lineage') {
      const d = await getJSON('dossiers.json');
      const p = (d?.dossiers || []).find((z: { canonical: string; aliases: unknown[] }) =>
        z.canonical === X || (Array.isArray(z.aliases) ? z.aliases : []).some((a: { alias?: string }) => (typeof a === 'string' ? a : a?.alias) === X));
      if (!p) return finish(`档案未载：${dx}（此人物暂无师承考订）。`, [], '口径：dossiers.json lineage（动词分级：收徒/传授=强证）。');
      const rows: { t: string; href?: string; loc?: string }[] = [];
      // W0-T5 存目守卫：师承/传人对端可能是存目人物（无档案页）→ 不发链接渲染文本（定位符保留）
      for (const m of p.lineage?.masters || []) rows.push({ t: `师承 ${dsp(lookupRef.current.display, m.person)}（${tierLabel(m.tier)}）`, loc: (m.locs || []).join('，'), href: isMainPerson(lookupRef.current, m.person) ? `${B}characters/${encodeURIComponent(m.person)}/` : undefined });
      for (const m of p.lineage?.disciples || []) rows.push({ t: `传人 ${dsp(lookupRef.current.display, m.person)}（${tierLabel(m.tier)}）`, loc: (m.locs || []).join('，'), href: isMainPerson(lookupRef.current, m.person) ? `${B}characters/${encodeURIComponent(m.person)}/` : undefined });
      return finish(rows.length ? `${dsp(lookupRef.current.display, p.canonical)} 的师承谱系（动词分级）：` : `${dsp(lookupRef.current.display, p.canonical)}：暂无明确师承考订；民间相传线索以“相传”标注。`, rows.slice(0, 10), '口径：◇ 传授/拜师事件 + 师承考订；民间相传线索以“相传”标注。');
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
      return finish(rows.length ? `${dx} 名下武功 ${rows.length} 门（镇山置顶）：` : `档案未载：关系表没有 ${dx} 的"拥有/镇山"武功。`, rows.slice(0, 12), '口径：关系表「门派—拥有/镇山—武功」，按证据定位符。');
    }
    if (t.id === 'versus') {
      const hits: { t: string; href?: string; loc?: string }[] = [];
      const seen = new Set<string>();
      for (const s of await allEvents()) {
        for (const evs of Object.values(s.events)) {
          for (const e of evs) {
            if ((e.a === X && e.b === Y) || (e.a === Y && e.b === X)) {
              // 兜底去重：同一（定位符,动词,双方）只记 1 起（导出层已去全同行，此处防镜像聚合回归）
              const k = `${e.l}|${e.v}|${e.a}|${e.b}`;
              if (seen.has(k)) continue;
              seen.add(k);
              hits.push({ t: `${dsp(lookupRef.current.display, e.a)} ${e.v} ${dsp(lookupRef.current.display, e.b)}`, loc: `${s.title}·${e.l}`, href: `${B}books/${encodeURIComponent(s.title)}/${String(parseInt(e.l, 10)).padStart(3, '0')}/` });
            }
          }
        }
      }
      return finish(hits.length ? `${dx} × ${dy}：同场交手/互动 ${hits.length} 起。` : `${dx} × ${dy}：四书事件层无直接交手记录（同场≠同事件，可在时空页查共现）。`,
        hits.slice(0, 10), '口径：事件表主客双向匹配（同定位符同动词双方去重），L0。');
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
      return finish(rows.length ? `${dx} 的持物/关联名物 ${rows.length} 件（明文流转置顶）：` : `档案未载：神兵表中没有 ${dx} 的持物线索。`, rows.slice(0, 10), '口径：神兵表 holders/chain（工具 C）；暂持 ≠ 归属。');
    }
    return finish('未知模板', [], '');
  }

  function finish(text: string, rows: { t: string; href?: string; loc?: string }[], note: string, warn?: string) {
    return { text, rows, note, warn };
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
      <div className="qa-nl">
        <input className="qa-in" value={nlv} placeholder="直接问：谁杀了金独异？练霓裳去过哪里？"
          onChange={(e) => { setNl(e.target.value); setMiss(false); }}
          onKeyDown={(e) => e.key === 'Enter' && askNL()} aria-label="自然语言提问" />
        <button className="qa-btn" onClick={() => askNL()} disabled={busy}>{busy ? '求解中…' : '问'}</button>
      </div>
      {miss && (
        <p className="qa-miss">没听懂这个问题——试着选一个模板，或换个问法（示例：谁杀了 X / X 去过哪里 / X 和 Y 交过手吗）。</p>
      )}
      <div className="qa-tpls">
        <span className="qa-exlabel">示例：</span>
        {EXAMPLES.map((q) => (
          <button key={q} className="qa-chip" onClick={() => askNL(q)}>{q}</button>
        ))}
      </div>
      <div className="qa-tpls">
        {TPLS.map((t) => (
          <button key={t.id} className={'qa-chip' + (t.id === tpl.id ? ' on' : '')}
            onClick={() => { setTpl(t); setAns(null); }}>{t.label}</button>
        ))}
      </div>
      {input}
      {ans && (
        <div className="qa-ans">
          <div className="qa-anshead">
            <button className="qa-chip qa-copy" onClick={copyLink}>{copied ? '已复制' : '复制链接'}</button>
            {copyNote && <code className="qa-copyurl">{copyNote}</code>}
          </div>
          <p className="qa-con">{ans.text}</p>
          {ans.warn && (
            <div className="qa-warn">
              ⚠ 此记录存疑：{ans.warn}——<a href={`${B}audit/`}>详见穿帮雷达</a>。
            </div>
          )}

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
        .qa-nl { display: flex; gap: 8px; }
        .qa-miss { margin: 0; font-size: 13.5px; color: #7f2c21; background: #f6e8d9;
          border: 1px dashed #a63a2b; border-radius: 4px; padding: 8px 12px; line-height: 1.8; }
        .qa-exlabel { font-size: 13px; color: #8a8172; align-self: center; }
        .qa-anshead { display: flex; gap: 10px; align-items: center; justify-content: flex-end; margin: 0 0 6px; }
        .qa-copyurl { font-size: 12px; color: #5f584b; background: rgba(0,0,0,.05);
          border-radius: 3px; padding: 2px 8px; font-family: ui-monospace, monospace;
          max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
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
        .qa-warn { background: #f6e8d9; border: 1px solid #a63a2b; border-radius: 4px; padding: 8px 12px; margin: 0 0 10px; font-size: 13px; color: #7f2c21; line-height: 1.8; }
        .qa-warn a { color: #a63a2b; }
      `}</style>
    </div>
  );
}
