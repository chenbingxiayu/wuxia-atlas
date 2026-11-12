import{j as e}from"./jsx-runtime.D_zvdyIk.js";import{r as t}from"./index.DLkBFFtG.js";const d="/wuxia-atlas".endsWith("/")?"/wuxia-atlas":"/wuxia-atlas/",p="wx-tuji-viewed",w=n=>n>=100?["传世名器","#a63a2b"]:n>=30?["知名兵器","#b8860b"]:["杂件","#8c8477"];function v(){const[n,x]=t.useState([]),[o,i]=t.useState(new Set),[h,f]=t.useState(!1);t.useEffect(()=>{fetch(d+"data/weapons.json").then(a=>a.json()).then(a=>{x(a.weapons||[])});try{const a=localStorage.getItem(p);a&&i(new Set(JSON.parse(a)))}catch{}f(!0)},[]);const g=a=>{if(o.has(a))return;const r=new Set(o);r.add(a),i(r);try{localStorage.setItem(p,JSON.stringify([...r]))}catch{}},b=n.length>0&&o.size>=n.length,m=t.useMemo(()=>{const a={};for(const r of n)(a[r.kind]||=[]).push(r);return Object.entries(a).sort((r,s)=>s[1].length-r[1].length)},[n]);if(!h)return e.jsx("div",{style:{padding:40,textAlign:"center",color:"#5f584b"},children:"图鉴加载中…"});const l=n.length?Math.round(o.size/n.length*100):0;return e.jsxs("div",{className:"gc",children:[e.jsxs("div",{className:"gc-progress",children:[e.jsx("b",{children:"图鉴收集度"}),e.jsx("div",{className:"bar",children:e.jsx("div",{className:"fill",style:{width:`${l}%`}})}),e.jsxs("span",{className:"mono",children:[l,"%"]}),e.jsxs("span",{className:"lab",children:[o.size," / ",n.length," 件已阅 · 点击卡片查看并收集 · 集齐点亮完成卡"]})]}),b&&e.jsx("div",{className:"gc-done",children:"✦ 图鉴收集完成——四书神兵，尽在眼底。"}),m.map(([a,r])=>e.jsxs("section",{children:[e.jsxs("h3",{children:[a," ",e.jsxs("small",{children:[r.length," 件"]})]}),e.jsx("div",{className:"grid",children:r.map(s=>{const[u,j]=w(s.ev_total),c=o.has(s.canonical);return e.jsxs("a",{className:"wcard"+(c?" seen":""),href:`${d}weapons/${encodeURIComponent(s.canonical)}/`,onClick:()=>g(s.canonical),children:[e.jsxs("div",{className:"whead",children:[e.jsx("b",{children:s.canonical}),c&&e.jsx("span",{className:"tick",children:"✓"})]}),e.jsxs("div",{className:"wmeta",children:[e.jsx("span",{className:"kind",children:s.kind}),s.grade&&e.jsx("span",{className:"grade",style:s.grade_basis==="明文"?{}:{borderStyle:"dashed",color:"#8a6607"},children:s.grade})]}),e.jsxs("div",{className:"wfoot",children:[e.jsxs("span",{className:"rar",style:{color:j},children:["◆ ",u]}),e.jsxs("span",{className:"ev",children:["考订证据 ",s.ev_total," 处"]})]})]},s.canonical)})})]},a)),e.jsx("style",{children:`
        .gc { display: flex; flex-direction: column; gap: 18px; }
        .gc-progress { background: #fbf8ef; border: 1px solid #d8cdb4; border-radius: 4px; padding: 12px 18px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
        .gc-progress b { font-family: 'Noto Serif SC', serif; }
        .bar { flex: 1; min-width: 160px; height: 14px; border: 1px solid #b5a687; border-radius: 999px; background: #f5efe4; overflow: hidden; }
        .fill { height: 100%; background: #a63a2b; }
        .mono { font-family: ui-monospace, monospace; }
        .lab { font-size: 12px; color: #8a8172; }
        .gc-done { background: #f6e8d9; border: 1px solid #b8860b; border-radius: 4px; padding: 10px 16px; color: #8a6607; font-weight: 700; text-align: center; }
        h3 { font-size: 15px; color: #5f584b; margin: 8px 0 6px; letter-spacing: 2px; }
        h3 small { color: #8a8172; font-weight: 400; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
        .wcard { border: 1px solid #b9ab90; border-radius: 4px; padding: 10px 12px; background: #fbf8ef; color: #2b2b2b; display: block; }
        .wcard:hover { border-color: #a63a2b; }
        .wcard.seen { border-color: #5e7d5a; }
        .whead { display: flex; justify-content: space-between; align-items: center; }
        .whead b { font-size: 14px; }
        .tick { color: #5e7d5a; font-weight: 700; }
        .wmeta { margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; }
        .kind { font-size: 11px; color: #5a544a; border: 1px solid #d8cdb8; border-radius: 999px; padding: 0 8px; }
        .grade { font-size: 11px; border: 1px solid #a63a2b; color: #a63a2b; border-radius: 3px; padding: 0 6px; }
        .wfoot { margin-top: 8px; display: flex; justify-content: space-between; font-size: 11px; color: #8a8172; }
      `})]})}export{v as default};
