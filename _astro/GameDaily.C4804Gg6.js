import{j as n}from"./jsx-runtime.D_zvdyIk.js";import{r as l}from"./index.DLkBFFtG.js";const z="/wuxia-atlas".endsWith("/")?"/wuxia-atlas":"/wuxia-atlas/",g="wuxia-daily";function k(){const a=new Date;return`${a.getFullYear()}${String(a.getMonth()+1).padStart(2,"0")}${String(a.getDate()).padStart(2,"0")}`}function v(a){let d=5381;for(let t=0;t<a.length;t++)d=(d<<5)+d+a.charCodeAt(t)>>>0;return d}function w(a){return a.trim().replace(/\s+/g,"")}function q(){const[a,d]=l.useState(null),[t,h]=l.useState([]),[p,m]=l.useState(""),[r,x]=l.useState("play"),[y,f]=l.useState(!1),i=k(),s=l.useMemo(()=>a?.length?a[v(i)%a.length]:null,[a,i]);l.useEffect(()=>{fetch(z+"data/games/daily.json").then(e=>e.json()).then(e=>d(e.puzzles));try{const e=JSON.parse(localStorage.getItem(g)||"{}");e[i]&&(h(e[i].tries||[]),x(e[i].state||"play"))}catch{}},[]);function u(e,o){try{const c=JSON.parse(localStorage.getItem(g)||"{}");c[i]={tries:e,state:o},localStorage.setItem(g,JSON.stringify(c))}catch{}}function b(){if(!s||r!=="play"||!p.trim())return;const e=w(p)===w(s.answer),o=[...t,e?"win":"miss"];if(h(o),m(""),e){x("win"),u(o,"win");return}o.length>=3&&(x("lose"),u(o,"lose"))}function N(){const e=t.map(c=>c==="win"?"🟩":"🟥").join(""),o=`江湖每日一谜 ${i.slice(0,4)}/${i.slice(4,6)}/${i.slice(6,8)} ${e||"⬜"}
${s?.q}`;navigator.clipboard?.writeText(o).then(()=>f(!0)).catch(()=>f(!1))}if(!s)return n.jsx("div",{className:"gd-loading",children:"出题中…"});const j=Math.min(t.length,s.hints.length),S=r==="lose";return n.jsxs("div",{className:"gd",children:[n.jsxs("div",{className:"riddle",children:[n.jsxs("div",{className:"rh",children:[n.jsx("b",{className:"gd-q",children:s.q}),n.jsxs("span",{className:"mono gd-day",children:[i.slice(0,4),"/",i.slice(4,6),"/",i.slice(6,8)," · 第 ",t.length,"/3 次"]})]}),s.hints.slice(0,r==="play"?j:s.hints.length).map((e,o)=>n.jsxs("div",{className:"hint",children:[n.jsxs("span",{className:"hn",children:["提示 ",o+1]}),e]},o)),r==="play"?n.jsxs("div",{className:"gd-row",children:[n.jsx("input",{className:"gd-in",value:p,placeholder:"写下答案（人名/门派）",onChange:e=>m(e.target.value),onKeyDown:e=>e.key==="Enter"&&b(),"aria-label":"答案"}),n.jsx("button",{className:"gd-btn",onClick:b,children:"作答"})]}):n.jsxs("div",{className:"answer "+(r==="win"?"ok":"no"),children:[r==="win"?`恭喜！答案就是「${s.answer}」。`:`今日谜底：「${s.answer}」。`,n.jsx("span",{className:"gd-loc",children:s.loc}),n.jsx("p",{className:"gd-explain",children:s.explain})]}),t.length>0&&r==="play"&&n.jsxs("p",{className:"dim",children:["已有 ",t.length," 次未中——再错一次将揭晓 ",s.hints.length>j?"新提示":"答案","。"]}),n.jsxs("div",{className:"share",children:[n.jsx("button",{className:"gd-btn ghost",onClick:N,children:y?"已复制 ✓":"复制战绩"}),n.jsx("span",{className:"emoj",children:t.map(e=>e==="win"?"🟩":"🟥").join("")}),n.jsx("span",{className:"dim",children:r==="win"?`用了 ${t.length} 次`:S?"明日再战":"本地存档 · 分享码纯文本"})]})]}),n.jsxs("p",{className:"fine",children:["选题 = 日期哈希（djb2）对题库取模——",n.jsx("b",{children:"全网同题、无需服务器"}),"；题库 ",a?.length," 道全部由图谱生成， 每题答案唯一且带「书·回」定位符。战绩仅存本地（localStorage），分享码为纯文本 emoji。"]}),n.jsx("style",{children:`
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
      `})]})}export{q as default};
