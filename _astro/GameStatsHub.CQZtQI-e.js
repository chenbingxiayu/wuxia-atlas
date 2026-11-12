import{j as s}from"./jsx-runtime.D_zvdyIk.js";import{r as o}from"./index.DLkBFFtG.js";import{a as b,l as j}from"./game-stats.Ca4mq0uj.js";const c="/wuxia-atlas".endsWith("/")?"/wuxia-atlas":"/wuxia-atlas/",v=e=>e.plays?Math.round(e.wins*100/e.plays):0,m=e=>`${Number(e.slice(4,6))}月${Number(e.slice(6,8))}日`,h=e=>e==="w"?"胜":e==="l"?"负":null;function u({name:e,href:t,g:l}){return s.jsxs("div",{className:"gsc-game",children:[s.jsx("a",{className:"gsc-name",href:t,children:e}),s.jsxs("div",{className:"gsc-line",children:["连胜 ",s.jsx("b",{children:l.curStreak}),s.jsxs("span",{className:"gsc-sub",children:["（最佳 ",l.bestStreak,"）"]})]}),s.jsxs("div",{className:"gsc-line",children:["正确率 ",s.jsx("b",{children:v(l)}),"%",s.jsxs("span",{className:"gsc-sub",children:["· 共 ",l.plays," 局"]})]})]})}function $(){const[e,t]=o.useState(null);o.useEffect(()=>{t(b())},[]);const l=o.useMemo(()=>{const a=e;return a?j(14).map(r=>{const d=a.daily.days.includes(r),g=a.twenty.days.includes(r),i=a.cal?.[r]||{},n=[],p=h(i.d),x=h(i.t);d&&n.push(`每日一谜${p?" "+p:""}`),g&&n.push(`二十问答${x?" "+x:""}`);const y=i.d==="w"||i.t==="w";return{day:r,lit:d||g,win:y,title:n.length?`${m(r)} · ${n.join(" · ")}`:m(r)}}):[]},[e]);return e?e.daily.plays+e.twenty.plays===0?s.jsxs("div",{className:"gsc empty",children:[s.jsxs("p",{className:"gsc-empty-line",children:["江湖风平浪静——先去玩一局",s.jsx("a",{href:`${c}games/daily/`,children:"每日一谜"}),"或",s.jsx("a",{href:`${c}games/twenty/`,children:"二十问答"}),"，再来晾战绩。"]}),s.jsx("span",{className:"gsc-note",children:"战绩仅存本机（localStorage），不上传 · 统计自战绩中心上线起算"}),s.jsx("style",{children:f})]}):s.jsxs("div",{className:"gsc",children:[s.jsxs("div",{className:"gsc-card",children:[s.jsxs("div",{className:"gsc-head",children:[s.jsx("b",{children:"本机战绩"}),s.jsx("span",{className:"gsc-note",children:"仅存本机（localStorage），不上传 · 统计自战绩中心上线起算"})]}),s.jsxs("div",{className:"gsc-grid",children:[s.jsx(u,{name:"每日一谜",href:`${c}games/daily/`,g:e.daily}),s.jsx(u,{name:"二十问答",href:`${c}games/twenty/`,g:e.twenty}),s.jsxs("div",{className:"gsc-cal",children:[s.jsx("span",{className:"gsc-cal-label",children:"答题日历 · 近 14 天"}),s.jsx("div",{className:"gsc-cells",children:l.map(a=>s.jsx("i",{className:"gsc-cell"+(a.lit?" lit":"")+(a.lit&&a.win?" win":"")+(a.day===l[l.length-1].day?" today":""),title:a.title},a.day))})]})]})]}),s.jsx("style",{children:f})]}):null}const f=`
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
`;export{$ as default};
