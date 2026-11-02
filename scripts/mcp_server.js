#!/usr/bin/env node
/**
 * 江湖图志 MCP Server（零依赖 stdio · 离线 <5ms）。
 *
 * 四个确定性工具，直接读 site/data 预构建 JSON（L0 图谱层——定位符与结构化事实，无原文摘录）：
 *   inspect_character  人物档案（书目/别名/师承/武功/战绩/关键事件，全部带 书·回:行 定位符）
 *   inspect_place      地名沿革（真实经纬度/虚实分层/出场书目回目）
 *   inspect_artifact   名物流转链（品阶/历代持有人/流转动词边）
 *   search_atlas       全图检索（人物/武功/地名/名物，别名解析）
 *
 * 运行：node scripts/mcp_server.js   （标准 MCP stdio 传输：newline-delimited JSON-RPC 2.0）
 * Claude Desktop / 任意 MCP 宿主配置示例：
 *   {"mcpServers": {"wuxia-atlas": {"command": "node", "args": ["scripts/mcp_server.js"]}}}
 */
'use strict';
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'site', 'data');
const cache = new Map();
function load(file) {
  if (!cache.has(file)) {
    try {
      cache.set(file, JSON.parse(fs.readFileSync(path.join(DATA, file), 'utf8')));
    } catch (e) {
      cache.set(file, null);
    }
  }
  return cache.get(file);
}
const atlasBook = (title) => load(path.join('atlas', title + '.json'));

/* ---------- 检索 ---------- */
const aliasNames = (x) => (Array.isArray(x.aliases) ? x.aliases.map((a) => (typeof a === 'string' ? a : a.alias)) : Object.keys(x.aliases || {}));
function findCharacter(name) {
  const d = load('dossiers.json');
  if (!d) return null;
  const hit = (x) => x.canonical === name || x.id === '@' + name || aliasNames(x).includes(name);
  return d.dossiers.find(hit) || null;
}
function findArtifact(name) {
  const w = load('weapons.json');
  if (!w) return null;
  return w.weapons.find((x) => x.canonical === name || (x.aliases || []).includes(name)) || null;
}
function findPlace(name) {
  const g = load('gazetteer.json');
  const place = g && g.places.find((p) => p.name === name || (p.aliases || []).includes(name));
  const books = [];
  for (const b of (load('atlas/state.json') || { books: [] }).books || []) {
    const s = atlasBook(b.title);
    if (s && s.places[name]) books.push({ book: b.title, chaps: s.places[name].chaps.slice(0, 12) });
  }
  if (!place && !books.length) return null;
  return {
    name, real: place ? place.real !== false : null,
    coord: place && place.lat != null ? `${place.lat.toFixed(4)}, ${place.lng.toFixed(4)}（WGS-84 · ${place.precision || 'approx'}）` : '虚构或待锚定（不发布经纬度）',
    aliases: place ? place.aliases : [],
    appearances: books,
  };
}
function searchAll(q) {
  const out = [];
  const d = load('dossiers.json');
  if (d) {
    for (const x of d.dossiers || []) {
      const al = aliasNames(x);
      if (x.canonical === q || al.includes(q)) out.push({ type: '人物', name: x.canonical, note: al.includes(q) && x.canonical !== q ? `别名"${q}"解析` : `出现 ${x.appearance_total} 次` });
      else if (x.canonical.includes(q)) out.push({ type: '人物', name: x.canonical, note: '模糊命中' });
    }
  }
  const idx = load('entity-index.json');
  if (idx) {
    for (const e of idx.entities || []) {
      if (e.c && e.c.includes(q)) out.push({ type: e.t === '@' ? '人物' : '武功', name: e.c, note: `出现 ${e.n} 次` });
    }
  }
  const g = load('gazetteer.json');
  if (g) {
    for (const p of g.places) {
      if (p.name === q || (p.aliases || []).includes(q)) out.push({ type: '地点', name: p.name, note: p.lat != null ? `真实坐标 ${p.lat.toFixed(2)}, ${p.lng.toFixed(2)}` : '虚构/待锚定' });
      else if (p.name.includes(q)) out.push({ type: '地点', name: p.name, note: '模糊命中' });
    }
  }
  const w = load('weapons.json');
  if (w) {
    for (const x of w.weapons) {
      if (x.canonical.includes(q)) out.push({ type: '名物', name: x.canonical, note: `${x.kind}${x.grade ? ' · ' + x.grade : ''}` });
    }
  }
  const seen = new Set();
  return out.filter((x) => (seen.has(x.type + x.name) ? false : (seen.add(x.type + x.name), true))).slice(0, 12);
}

/* ---------- 渲染（文本块，全部挂定位符）---------- */
function renderCharacter(x) {
  const L = [`# ${x.canonical}${x.cross_book ? '（跨书）' : ''}`, `出场 ${x.appearance_total} 次 · 书目：${(x.books || []).join('、')}`];
  const al = aliasNames(x);
  if (al.length) L.push(`别名：${al.join('、')}`);
  if (x.lineage && typeof x.lineage === 'object') {
    const lin = x.lineage;
    if (lin.masters && lin.masters.length) L.push(`师承：${lin.masters.map((m) => `${m.person}（${m.tier} · ${(m.locs || []).join('，')}）`).join('；')}`);
    if (lin.disciples && lin.disciples.length) L.push(`传人：${lin.disciples.map((m) => `${m.person}（${m.tier} · ${(m.locs || []).join('，')}）`).join('；')}`);
  } else if (x.lineage) {
    L.push(`师承线索：${x.lineage}`);
  }
  if (x.arts && x.arts.length) L.push(`武功：${x.arts.map((a) => a.art || a.canonical || a).slice(0, 8).join('、')}`);
  if (x.combat) {
    const c = x.combat;
    const fmt = (list, label) => {
      if (!Array.isArray(list) || !list.length) return;
      const rows = list.slice(0, 4).map((k) => `${k.person}×${(k.records || []).length}（${(k.records || [])[0] ? k.records[0].book + '·' + k.records[0].loc : ''}）`);
      L.push(`${label}：${rows.join('；')}`);
    };
    fmt(c.kills, '杀伤（对象×次数，附首证）');
    fmt(c.slain_by, '被杀/败于');
    if (c.top_opponents && c.top_opponents.length) {
      L.push(`高频对手：${c.top_opponents.slice(0, 5).map((r) => (typeof r === 'string' ? r : `${r.name || r.person || r.c}×${r.n || r.count || ''}`)).join('、')}`);
    }
  }
  if (x.sect_affinity) {
    const sa = Array.isArray(x.sect_affinity) ? x.sect_affinity : [];
    if (sa.length) L.push(`门派线索（derived，非正式归属）：${sa.map((s) => `${s.sect}（${s.tier} · 经${(s.via_arts || []).join('/')}）`).join('；')}`);
  }
  if (x.key_events && x.key_events.length) {
    L.push('关键事件（high 置信 · 定位符）：');
    for (const e of x.key_events.slice(0, 8)) {
      L.push(`  - ${e.book || ''}·${e.loc || ''} ${[e.subject, e.verb, e.object].filter(Boolean).join(' ')}`);
    }
  }
  L.push('（数据口径：L0 图谱层，每条结论可在对应 书·回:行 溯源）');
  return L.join('\n');
}
function renderArtifact(x) {
  const L = [`# ${x.canonical}（${x.kind}${x.grade ? ' · ' + x.grade + (x.grade_basis === '明文' ? '·明文' : '·待考') : ''}）`];
  L.push(`见于：${Object.keys(x.books).join('、')} · 证据 ${x.ev_total} 处 · 置信 ${x.conf}`);
  const strong = x.chain.filter((e) => e.conf === 'strong');
  if (strong.length) {
    L.push('流转链（明文句式，每次易手挂定位符）：');
    for (const e of strong.slice(0, 10)) L.push(`  - [${e.verb}] ${e.persons.join('、')}（${e.book}·${e.loc}）`);
  }
  if (x.holders && x.holders.length) L.push(`共现持有人：${x.holders.map((h) => `${h.name}×${h.n}`).join('、')}（暂持 ≠ 归属）`);
  if (x.end_state) L.push(`终态：${x.end_state.note}`);
  L.push('（L0：仅定位符与结构化事实）');
  return L.join('\n');
}

/* ---------- 工具定义 ---------- */
const TOOLS = [
  { name: 'inspect_character', description: '人物档案：书目/别名/师承/武功/战绩/关键事件（带 书·回:行 定位符）', inputSchema: { type: 'object', properties: { name: { type: 'string', description: '人物规范名或别名，如 练霓裳 / 玉罗刹' } }, required: ['name'] } },
  { name: 'inspect_place', description: '地名沿革：真实经纬度（WGS-84，虚实分层）/出场书目与回目', inputSchema: { type: 'object', properties: { name: { type: 'string', description: '地名，如 武当山 / 秘魔崖' } }, required: ['name'] } },
  { name: 'inspect_artifact', description: '名物流转链：品阶/历代持有人/流转动词边（赠夺还传借毁失）', inputSchema: { type: 'object', properties: { name: { type: 'string', description: '名物名，如 游龙剑 / 金丝手套' } }, required: ['name'] } },
  { name: 'search_atlas', description: '全图检索：人物/武功/地名/名物（含别名解析，如"白发魔女"→练霓裳）', inputSchema: { type: 'object', properties: { query: { type: 'string' } }, required: ['query'] } },
];

function callTool(name, args) {
  try {
    if (name === 'inspect_character') {
      const x = findCharacter(args.name);
      if (!x) return { content: [{ type: 'text', text: `档案未载：${args.name}（四书人物谱无此规范名/别名）` }], isError: true };
      return { content: [{ type: 'text', text: renderCharacter(x) }] };
    }
    if (name === 'inspect_place') {
      const p = findPlace(args.name);
      if (!p) return { content: [{ type: 'text', text: `档案未载：${args.name}` }], isError: true };
      const L = [`# ${p.name}${p.real ? '' : '（虚构 · 按文中方位安放）'}`, `坐标：${p.coord}`];
      if (p.aliases && p.aliases.length) L.push(`别名：${p.aliases.join('、')}`);
      for (const b of p.appearances) L.push(`出场：${b.book}（${b.chaps.join('、')} 回）`);
      return { content: [{ type: 'text', text: L.join('\n') }] };
    }
    if (name === 'inspect_artifact') {
      const x = findArtifact(args.name);
      if (!x) return { content: [{ type: 'text', text: `档案未载：${args.name}` }], isError: true };
      return { content: [{ type: 'text', text: renderArtifact(x) }] };
    }
    if (name === 'search_atlas') {
      const hits = searchAll(args.query);
      if (!hits.length) return { content: [{ type: 'text', text: `无命中：${args.query}` }], isError: true };
      return { content: [{ type: 'text', text: hits.map((h) => `[${h.type}] ${h.name} — ${h.note}`).join('\n') }] };
    }
    return { content: [{ type: 'text', text: `未知工具：${name}` }], isError: true };
  } catch (e) {
    return { content: [{ type: 'text', text: '工具错误：' + e.message }], isError: true };
  }
}

/* ---------- stdio JSON-RPC ---------- */
const SERVER = { name: 'wuxia-atlas', version: '0.1.0' };
let buf = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => {
  buf += chunk;
  let i;
  while ((i = buf.indexOf('\n')) >= 0) {
    const line = buf.slice(0, i).trim();
    buf = buf.slice(i + 1);
    if (!line) continue;
    let msg;
    try { msg = JSON.parse(line); } catch { continue; }
    handle(msg);
  }
});
function send(msg) {
  process.stdout.write(JSON.stringify(msg) + '\n');
}
function handle(msg) {
  const { id, method, params } = msg;
  if (method === 'initialize') {
    return send({ jsonrpc: '2.0', id, result: { protocolVersion: '2024-11-05', capabilities: { tools: {} }, serverInfo: SERVER } });
  }
  if (method && method.startsWith('notifications/')) return;
  if (method === 'ping') return send({ jsonrpc: '2.0', id, result: {} });
  if (method === 'tools/list') return send({ jsonrpc: '2.0', id, result: { tools: TOOLS } });
  if (method === 'tools/call') {
    const { name, arguments: args } = params || {};
    return send({ jsonrpc: '2.0', id, result: callTool(name, args || {}) });
  }
  send({ jsonrpc: '2.0', id, error: { code: -32601, message: 'method not found: ' + method } });
}
process.stderr.write(`[wuxia-atlas MCP] ready · data: ${DATA}\n`);
