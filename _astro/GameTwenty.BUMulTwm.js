import{j as s}from"./jsx-runtime.D_zvdyIk.js";import{r}from"./index.DLkBFFtG.js";const C="/wuxia-atlas".endsWith("/")?"/wuxia-atlas":"/wuxia-atlas/";function R(){const[u,S]=r.useState([]),[m,z]=r.useState([]),[t,c]=r.useState([]),[f,h]=r.useState([]),[d,b]=r.useState(0),[j,y]=r.useState([]),[a,g]=r.useState(null),[x,N]=r.useState(!1);r.useEffect(()=>{fetch(C+"data/games/twenty.json").then(e=>e.json()).then(e=>{S(e.chars),z(e.questions),c(e.chars)})},[]);const l=r.useMemo(()=>{const e=m.filter(i=>!f.includes(i.id));if(!e.length)return null;let n=e[0],o=1/0;for(const i of e){const M=t.filter(A=>A.a[i.key]).length/(t.length||1),v=Math.abs(M-.5);v<o&&(o=v,n=i)}return n},[m,f,t]);function p(e){if(!l)return;const n=l.text;y(o=>[...o,{text:n,ans:e}]),h(o=>[...o,l.id]),e!=="unsure"&&c(o=>o.filter(i=>e==="yes"==!!i.a[l.key])),b(o=>o+1),g(null)}function q(){const e=[...t].sort((n,o)=>o.total-n.total)[0]||null;g(e)}function G(){a&&(c(e=>e.filter(n=>n.name!==a.name)),g(null))}function k(){c(u),h([]),b(0),y([]),g(null),N(!1)}if(!u.length)return s.jsx("div",{className:"g20-loading",children:"题库加载中…"});const w=d>=20||t.length===0;return s.jsxs("div",{className:"g20",children:[s.jsxs("div",{className:"g20-head",children:[s.jsxs("span",{className:"mono",children:["第 ",Math.min(d+1,20)," / 20 问"]}),s.jsxs("span",{className:"dim",children:["候选 ",t.length," 人"]}),s.jsx("button",{className:"g20-restart",onClick:k,children:"重开"})]}),s.jsx("div",{className:"g20-progress",children:Array.from({length:20}).map((e,n)=>s.jsx("i",{className:n<d?"used":""},n))}),x||w?s.jsxs("div",{className:"g20-result",children:[t.length===1&&s.jsx("p",{className:"g20-only",children:"候选只剩一人——"}),s.jsx("p",{className:"g20-guess",children:a?a.name:"我认输，江湖高人到底是谁？"}),a&&s.jsxs(s.Fragment,{children:[a.sect&&s.jsxs("p",{className:"dim",children:[a.sect," · ",a.books.join("、")]}),s.jsx("a",{className:"g20-link",href:`${C}characters/${encodeURIComponent(a.name)}/`,children:"看 TA 的档案 →"}),s.jsxs("div",{className:"g20-btns",children:[s.jsx("button",{className:"yes",onClick:()=>{N(!0)},children:"猜对了"}),s.jsx("button",{className:"no",onClick:G,children:"猜错了，继续"})]})]}),x&&s.jsxs("p",{className:"dim",children:["共用了 ",d," 问。战绩保存在本地（G7 每日一谜可分享战绩）。"]}),w&&!t.length||a&&x?s.jsx("button",{className:"g20-restart big",onClick:k,children:"再来一局"}):null]}):s.jsxs("div",{className:"g20-q",children:[s.jsx("p",{className:"g20-text",children:l?l.text:"问题用尽"}),s.jsxs("div",{className:"g20-btns",children:[s.jsx("button",{className:"yes",onClick:()=>p("yes"),children:"是"}),s.jsx("button",{className:"no",onClick:()=>p("no"),children:"否"}),s.jsx("button",{className:"unsure",onClick:()=>p("unsure"),children:"不知道"}),t.length>1&&s.jsxs("button",{className:"guess",onClick:q,children:["直接猜（",[...t].sort((e,n)=>n.total-e.total)[0]?.name,"？）"]})]})]}),j.length>0&&s.jsx("ol",{className:"g20-log",children:j.map((e,n)=>s.jsxs("li",{children:[s.jsxs("span",{className:"mono",children:[n+1,"."]})," ",e.text," ",s.jsx("b",{className:e.ans,children:e.ans==="yes"?"是":e.ans==="no"?"否":"？"})]},n))}),s.jsx("style",{children:`
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
      `})]})}export{R as default};
