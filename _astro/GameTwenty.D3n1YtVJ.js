import{j as e}from"./jsx-runtime.D_zvdyIk.js";import{r as a}from"./index.DLkBFFtG.js";import{f as I,a as q,d as R}from"./display-shared.C0w8vhne.js";import{r as E}from"./game-stats.Ca4mq0uj.js";const h="/wuxia-atlas".endsWith("/")?"/wuxia-atlas":"/wuxia-atlas/";function U(){const[b,G]=a.useState([]),[u,M]=a.useState([]),[r,p]=a.useState([]),[j,k]=a.useState([]),[x,N]=a.useState(0),[w,S]=a.useState([]),[t,c]=a.useState(null),[d,v]=a.useState(!1),[f,A]=a.useState({display:{},canonicalOf:{}}),g=a.useRef(!1);a.useEffect(()=>{Promise.all([fetch(h+"data/games/twenty.json").then(s=>s.json()),I(h)]).then(([s,n])=>{G(s.chars),M(s.questions),p(s.chars),A(n)})},[]);const l=a.useMemo(()=>{const s=u.filter(i=>!j.includes(i.id));if(!s.length)return null;let n=s[0],o=1/0;for(const i of s){const $=r.filter(D=>D.a[i.key]).length/(r.length||1),z=Math.abs($-.5);z<o&&(o=z,n=i)}return n},[u,j,r]),m=b.length>0&&(x>=20||r.length===0||u.length>0&&j.length>=u.length);a.useEffect(()=>{m&&!t&&!d&&!g.current&&(g.current=!0,E("twenty",!1))},[m,t,d]);function L(){g.current||(g.current=!0,v(!0),E("twenty",!0))}function y(s){if(!l)return;const n=l.text;if(S(o=>[...o,{text:n,ans:s}]),k(o=>[...o,l.id]),s!=="unsure"){const o=r.filter(i=>s==="yes"==!!i.a[l.key]);p(o),c(o.length===1?o[0]:null)}else c(null);N(o=>o+1)}function Q(){const s=[...r].sort((n,o)=>o.total-n.total)[0]||null;c(s)}function T(){t&&(p(s=>s.filter(n=>n.name!==t.name)),c(null))}function C(){p(b),k([]),N(0),S([]),c(null),v(!1),g.current=!1}return b.length?e.jsxs("div",{className:"g20",children:[e.jsxs("div",{className:"g20-head",children:[e.jsxs("span",{className:"mono",children:["第 ",Math.min(x+1,20)," / 20 问"]}),e.jsxs("span",{className:"dim",children:["候选 ",r.length," 人"]}),e.jsx("button",{className:"g20-restart",onClick:C,children:"重开"})]}),e.jsx("div",{className:"g20-progress",children:Array.from({length:20}).map((s,n)=>e.jsx("i",{className:n<x?"used":""},n))}),d||m||t?e.jsxs("div",{className:"g20-result",children:[r.length===1&&e.jsx("p",{className:"g20-only",children:"候选只剩一人——"}),e.jsx("p",{className:"g20-guess",children:t?q(f.display,t.name):"我认输，江湖高人到底是谁？"}),t&&e.jsxs(e.Fragment,{children:[t.sect&&e.jsxs("p",{className:"dim",children:[t.sect," · ",t.books.join("、")]}),e.jsx("a",{className:"g20-link",href:`${h}characters/${encodeURIComponent(t.href||t.name)}/`,children:"看 TA 的档案 →"}),e.jsxs("div",{className:"g20-btns",children:[e.jsx("button",{className:"yes",onClick:L,children:"猜对了"}),e.jsx("button",{className:"no",onClick:T,children:"猜错了，继续"})]})]}),d&&e.jsxs("p",{className:"dim",children:["共用了 ",x," 问。战绩已计入",e.jsx("a",{href:`${h}games/`,children:"战绩中心"}),"（仅存本机，不上传）。"]}),m||t&&d?e.jsx("button",{className:"g20-restart big",onClick:C,children:"再来一局"}):null]}):e.jsxs("div",{className:"g20-q",children:[e.jsx("p",{className:"g20-text",children:l?R(f.display,l.text):"问题用尽"}),e.jsxs("div",{className:"g20-btns",children:[e.jsx("button",{className:"yes",onClick:()=>y("yes"),children:"是"}),e.jsx("button",{className:"no",onClick:()=>y("no"),children:"否"}),e.jsx("button",{className:"unsure",onClick:()=>y("unsure"),children:"不知道"}),r.length>1&&e.jsxs("button",{className:"guess",onClick:Q,children:["直接猜（",q(f.display,[...r].sort((s,n)=>n.total-s.total)[0]?.name||""),"？）"]})]})]}),w.length>0&&e.jsx("ol",{className:"g20-log",children:w.map((s,n)=>e.jsxs("li",{children:[e.jsxs("span",{className:"mono",children:[n+1,"."]})," ",R(f.display,s.text)," ",e.jsx("b",{className:s.ans,children:s.ans==="yes"?"是":s.ans==="no"?"否":"？"})]},n))}),e.jsx("style",{children:`
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
      `})]}):e.jsx("div",{className:"g20-loading",children:"题库加载中…"})}export{U as default};
