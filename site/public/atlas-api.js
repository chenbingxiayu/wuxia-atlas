/**
 * atlasAPI —— 浏览器端图谱查询 API（N17）。
 * 挂载于全站页头（Base.astro），站点内游戏（G1/G3/G6/G11）、专栏图表与问答共用同一套查询函数；
 * 亦是深链与外部脚本（控制台/书签）的公开入口。全部数据 = 预构建 L0 静态 JSON，无后端。
 *
 * window.atlasAPI
 *   .resolve(name)            → {type:'人物|武功|地点|名物', name}   别名解析（"白发魔女"→练霓裳）
 *   .inspect('character'|'place'|'artifact', name) → 结构化档案对象（Promise）
 *   .locate(book, chap?)      → 该书时空切片（places/bychap/events）
 *   .search(query)            → search_all 结果（同 MCP search_atlas）
 */
(function () {
  'use strict';
  var me = document.currentScript;
  var RAW = me && me.src ? new URL(me.src).pathname.replace(/atlas-api\.js$/, '') : '/';
  var cache = {};
  function getJSON(url) {
    if (!cache[url]) cache[url] = fetch(url).then(function (r) { return r.ok ? r.json() : null; });
    return cache[url];
  }
  function state() { return getJSON(RAW + 'data/atlas/state.json'); }

  var api = {
    base: RAW,
    resolve: function (name) {
      return state().then(function (m) {
        return Promise.all([
          getJSON(RAW + 'data/entity-index.json'),
          getJSON(RAW + 'data/gazetteer.json'),
          getJSON(RAW + 'data/weapons.json'),
        ]).then(function (r) {
          var idx = r[0], gaz = r[1], wp = r[2], i, x;
          for (i = 0; idx && i < (idx.entities || []).length; i++) {
            x = idx.entities[i];
            if (x.c === name) return { type: x.t === '@' ? '人物' : '武功', name: name };
          }
          if (gaz) for (i = 0; i < gaz.places.length; i++) {
            x = gaz.places[i];
            if (x.name === name || (x.aliases || []).indexOf(name) >= 0) return { type: '地点', name: x.name };
          }
          if (wp) for (i = 0; i < wp.weapons.length; i++) {
            x = wp.weapons[i];
            if (x.canonical === name || (x.aliases || []).indexOf(name) >= 0) return { type: '名物', name: x.canonical };
          }
          return null;  // 人物别名兜底请用 inspect('character', 别名)（dossiers 含别名组）
        });
      });
    },
    inspect: function (kind, name) {
      var url = kind === 'character' ? RAW + 'data/dossiers.json'
        : kind === 'place' ? RAW + 'data/gazetteer.json'
        : kind === 'artifact' ? RAW + 'data/weapons.json' : null;
      if (!url) return Promise.reject(new Error('unknown kind: ' + kind));
      return getJSON(url).then(function (d) {
        if (kind === 'character') {
          return (d.dossiers || []).find(function (x) {
            return x.canonical === name || x.id === '@' + name ||
              (Array.isArray(x.aliases) ? x.aliases.indexOf(name) >= 0 : Object.keys(x.aliases || {}).indexOf(name) >= 0);
          }) || null;
        }
        if (kind === 'place') {
          return (d.places || []).find(function (x) {
            return x.name === name || (x.aliases || []).indexOf(name) >= 0;
          }) || null;
        }
        return (d.weapons || []).find(function (x) {
          return x.canonical === name || (x.aliases || []).indexOf(name) >= 0;
        }) || null;
      });
    },
    locate: function (book, chap) {
      return getJSON(RAW + 'data/atlas/' + encodeURIComponent(book) + '.json').then(function (s) {
        if (s && chap && s.bychap[String(chap)]) {
          return { book: s.title, chap: chap, persons: s.bychap[String(chap)].p, places: s.bychap[String(chap)].l, events: s.events[String(chap)] || [] };
        }
        return s;
      });
    },
    search: function (q) {
      return getJSON(RAW + 'data/entity-index.json').then(function (idx) {
        var out = [];
        (idx && idx.entities || []).forEach(function (e) {
          if (e.c && e.c.indexOf(q) >= 0) out.push({ type: e.t === '@' ? '人物' : '武功', name: e.c });
        });
        return out;
      });
    },
  };
  window.atlasAPI = api;
})();
