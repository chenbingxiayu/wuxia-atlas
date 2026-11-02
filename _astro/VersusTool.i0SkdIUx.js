import{j as s}from"./jsx-runtime.D_zvdyIk.js";import{r as t}from"./index.DLkBFFtG.js";const r="/wuxia-atlas".endsWith("/")?"/wuxia-atlas":"/wuxia-atlas/";function w(){const[l,u]=t.useState([]),[g,j]=t.useState([]),[a,x]=t.useState(""),[n,m]=t.useState("");t.useEffect(()=>{Promise.all([fetch(r+"data/ratings.json").then(e=>e.json()),fetch(r+"data/matches.json").then(e=>e.json())]).then(([e,d])=>{u(e.players.filter(b=>b.matches_n>0)),j(d.matches);const h=new URLSearchParams(location.search),f=h.get("a")||"",v=h.get("b")||"";f&&v&&(x(f),m(v))})},[]),t.useEffect(()=>{a&&n&&history.replaceState(null,"",`${location.pathname}?a=${encodeURIComponent(a)}&b=${encodeURIComponent(n)}`)},[a,n]);const i=l.find(e=>e.name===a),o=l.find(e=>e.name===n),p=a&&n?g.filter(e=>e.a===a&&e.b===n||e.a===n&&e.b===a):[],c=i&&o?1/(1+Math.pow(10,(o.rating-i.rating)/400)):null;return s.jsxs("div",{className:"vt",children:[s.jsxs("div",{className:"vt-sel",children:[s.jsxs("select",{value:a,onChange:e=>x(e.target.value),"aria-label":"人物 A",children:[s.jsx("option",{value:"",children:"选人物 A…"}),l.map(e=>s.jsx("option",{children:e.name},e.name))]}),s.jsx("span",{className:"vs",children:"×"}),s.jsxs("select",{value:n,onChange:e=>m(e.target.value),"aria-label":"人物 B",children:[s.jsx("option",{value:"",children:"选人物 B…"}),l.map(e=>s.jsx("option",{children:e.name},e.name))]})]}),i&&o?s.jsxs(s.Fragment,{children:[s.jsxs("div",{className:"vt-head",children:[[i,o].map((e,d)=>s.jsxs("div",{className:"vt-side",children:[s.jsx("a",{className:"vt-name",href:`${r}characters/${encodeURIComponent(e.name)}/`,children:e.name}),s.jsxs("div",{className:"vt-rating mono",children:[e.rating,"±",e.rd]}),s.jsxs("div",{className:"dim",children:[e.tier," · ",e.matches_n," 场"]}),d===0&&c!=null&&s.jsxs("div",{className:"vt-exp",children:["预期胜率 ",s.jsxs("b",{children:[Math.round(c*100),"%"]})]})]},e.name)),s.jsxs("div",{className:"vt-mid",children:[s.jsxs("div",{className:"vt-delta mono",children:["分差 ",Math.abs(i.rating-o.rating)]}),c!=null&&s.jsxs("div",{className:"dim",children:["（另一侧 ",Math.round((1-c)*100),"%）"]})]})]}),s.jsx("h2",{children:"历史交锋（事件层）"}),p.length?s.jsx("ul",{className:"vt-list",children:p.map(e=>s.jsxs("li",{children:[s.jsx("b",{children:e.a})," ",s.jsx("span",{className:"mono "+e.outcome,children:e.outcome==="draw"?"平":e.outcome==="win"?`${e.a} 胜`:`${e.b} 胜`}),s.jsxs("span",{className:"dim",children:["（",e.kind,e.modifiers.length?" · "+e.modifiers.join("/"):""," · w",e.weight,"）"]}),s.jsxs("a",{className:"mono loc",href:`${r}books/${encodeURIComponent(e.book)}/${parseInt(e.loc,10)}/`,children:[e.book,"·",e.loc," →"]})]},e.id))}):s.jsx("p",{className:"dim",children:"事件层无直接交手记录——分差来自各自与共同对手的间接比较（可去时空页看两人是否同场）。"}),s.jsx("p",{className:"fine",children:"分差来源：Glicko-2 合成榜展示分（收缩后）；预期胜率按 Elo 标度近似。区间宽者（RD 大于 150）结论仅供参考。"})]}):s.jsxs("p",{className:"dim",children:["选择两个人物查看评分对比与历史交锋（支持 ",s.jsx("code",{children:"?a=练霓裳&b=铁飞龙"})," 深链）。"]}),s.jsx("style",{children:`
        .vt { display: flex; flex-direction: column; gap: 16px; }
        .vt-sel { display: flex; gap: 12px; align-items: center; }
        .vt-sel select { font-family: inherit; font-size: 15px; padding: 8px 12px; border: 2px solid #262420; border-radius: 4px; background: #fbf8ef; flex: 1; }
        .vs { font-family: 'Ma Shan Zheng', serif; font-size: 22px; color: #a23527; }
        .vt-head { display: flex; gap: 20px; align-items: stretch; background: #fbf8ef; border: 1px solid #d8cdb4; border-radius: 4px; padding: 18px 24px; }
        .vt-side { flex: 1; }
        .vt-name { font-size: 22px; font-weight: 900; color: #31536c; }
        .vt-name:hover { color: #a23527; }
        .vt-rating { font-size: 26px; color: #a23527; margin: 4px 0; }
        .vt-exp { margin-top: 6px; font-size: 13.5px; color: #4f6e4a; }
        .vt-mid { display: flex; flex-direction: column; justify-content: center; align-items: center; }
        .vt-delta { font-size: 18px; color: #262420; }
        h2 { font-size: 1.05rem; border-bottom: 1px solid #d8cdb4; padding-bottom: .2em; }
        .vt-list { list-style: none; padding: 0; }
        .vt-list li { display: flex; gap: 10px; align-items: baseline; padding: 7px 0; border-bottom: 1px dashed #e6ddc8; font-size: 14px; flex-wrap: wrap; }
        .vt-list .win, .vt-list .loss { color: #4f6e4a; }
        .vt-list .draw { color: #8a8172; }
        .loc { margin-left: auto; }
        .dim { color: #8a8172; font-size: 13px; }
        .fine { color: #8a8172; font-size: 12px; }
        .mono { font-family: ui-monospace, monospace; }
        code { background: rgba(0,0,0,.05); border-radius: 3px; padding: 0 .3em; font-family: ui-monospace, monospace; }
      `})]})}export{w as default};
