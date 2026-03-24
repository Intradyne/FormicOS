import { useState, useEffect, useRef, useCallback, useMemo } from "react";

/*
 * ═══════════════════════════════════════════════════════════
 * FORMICOS v2.0.0-α — UI PROTOTYPE / VISUAL SPEC
 * Phase 1 deliverable. Lit implementation uses this as spec.
 * ═══════════════════════════════════════════════════════════
 * Void Protocol · Luminous Void · Pheromone Substrate
 *
 * CHANGELOG from draft:
 *  - Added merge/prune/broadcast controls (S2 critical)
 *  - Added workspace config editing panel
 *  - Thread view shows colonies with merge edge arrows
 *  - Protocol status consolidated into header
 *  - Data shapes aligned with docs/contracts/types.ts
 *  - Colony detail: round timeline visualization
 *  - Defense signals factored into dedicated section
 * ═══════════════════════════════════════════════════════════
 */

// ── VOID PROTOCOL DESIGN TOKENS ─────────────────────────
const V = {
  void: "#06060C", surface: "#0D0E16", elevated: "#161721", recessed: "#030308",
  border: "rgba(255,255,255,0.05)", borderHover: "rgba(255,255,255,0.12)",
  borderAccent: "rgba(232,88,26,0.22)",
  fg: "#EDEDF0", fgMuted: "#6B6B76", fgDim: "#3A3A44", fgOnAccent: "#08080D",
  accent: "#E8581A", accentBright: "#F4763A", accentDeep: "#B8440F",
  accentMuted: "rgba(232,88,26,0.08)", accentGlow: "rgba(232,88,26,0.16)",
  secondary: "#3DD6F5", secondaryMuted: "rgba(61,214,245,0.07)",
  secondaryGlow: "rgba(61,214,245,0.12)",
  success: "#2DD4A8", warn: "#F5B731", danger: "#F06464",
  purple: "#A78BFA", blue: "#5B9CF5",
  glass: "rgba(13,14,22,0.60)", glassHover: "rgba(22,23,33,0.78)",
  pheromoneWeak: "rgba(232,88,26,0.04)", pheromoneMid: "rgba(232,88,26,0.12)",
  pheromoneStrong: "rgba(232,88,26,0.25)",
};
const F = {
  display: "'Satoshi','General Sans','DM Sans',system-ui,sans-serif",
  body: "'Geist','DM Sans','Plus Jakarta Sans',system-ui,sans-serif",
  mono: "'IBM Plex Mono','JetBrains Mono',monospace",
};

// ── MOCK DATA (aligned with contracts/types.ts) ──────────
const TREE = [
  { id:"ws-auth", name:"refactor-auth", type:"workspace",
    config:{ coder_model:"anthropic/claude-sonnet-4.6", reviewer_model:null, researcher_model:null, archivist_model:null, budget:5.0, strategy:"stigmergic" },
    children:[
      { id:"th-main", name:"main", type:"thread", children:[
        { id:"col-a1b2", name:"colony-a1b2", type:"colony", status:"running", round:3, maxRounds:8,
          task:"Refactor JWT refresh handler — proper token rotation, session invalidation, PKCE flow",
          strategy:"stigmergic",
          agents:[
            { name:"Coder", caste:"coder", model:"anthropic/claude-sonnet-4.6", tokens:14620, status:"active", pheromone:0.82 },
            { name:"Reviewer", caste:"reviewer", model:"ollama/qwen3-30b", tokens:5020, status:"pending", pheromone:0.61 },
            { name:"Archivist", caste:"archivist", model:"ollama/qwen3-30b", tokens:4420, status:"done", pheromone:0.44 },
          ],
          convergence:0.72, cost:0.38,
          pheromones:[
            {from:"coder",to:"reviewer",w:1.8,trend:"up"},{from:"reviewer",to:"archivist",w:0.9,trend:"stable"},
            {from:"coder",to:"archivist",w:0.6,trend:"down"},{from:"queen",to:"coder",w:1.4,trend:"up"},
          ],
          topology:{
            nodes:[
              {id:"queen",label:"QUEEN",x:200,y:30,c:V.accent,caste:"queen"},
              {id:"coder",label:"CODER",x:80,y:140,c:V.success,caste:"coder"},
              {id:"reviewer",label:"REVIEWER",x:320,y:140,c:V.purple,caste:"reviewer"},
              {id:"archivist",label:"ARCHVST",x:200,y:230,c:V.warn,caste:"archivist"},
            ],
            edges:[
              {from:"queen",to:"coder",w:1.4},{from:"queen",to:"reviewer",w:0.8},
              {from:"coder",to:"reviewer",w:1.8},{from:"reviewer",to:"archivist",w:0.9},
              {from:"coder",to:"archivist",w:0.6},
            ],
          },
          defense:{ composite:0.12, signals:[
            {name:"entropy",value:0.08,threshold:1.0},{name:"drift",value:0.15,threshold:0.7},
            {name:"mi",value:0.11,threshold:0.3},{name:"spectral",value:0.14,threshold:0.3},
          ]},
          rounds:[
            {r:1,phase:"Goal",agents:[{n:"Coder",m:"ollama/qwen3-30b",t:2840,s:"done"},{n:"Reviewer",m:"ollama/qwen3-30b",t:1920,s:"done"}]},
            {r:2,phase:"Execute",agents:[{n:"Coder",m:"anthropic/sonnet",t:8420,s:"done"},{n:"Reviewer",m:"ollama/qwen3-30b",t:3100,s:"done"}]},
            {r:3,phase:"Route",agents:[{n:"Coder",m:"anthropic/sonnet",t:6200,s:"active"},{n:"Reviewer",m:"ollama/qwen3-30b",t:0,s:"pending"}]},
          ],
        },
        { id:"col-c3d4", name:"colony-c3d4", type:"colony", status:"completed", round:5, maxRounds:5,
          task:"Initial auth module analysis — dependency mapping, vulnerability scan",
          strategy:"stigmergic",
          agents:[{name:"Coder",caste:"coder",model:"ollama/qwen3-30b",tokens:28400,status:"done",pheromone:0.95},
                  {name:"Reviewer",caste:"reviewer",model:"ollama/qwen3-30b",tokens:12800,status:"done",pheromone:0.88}],
          convergence:0.95, cost:0.62, pheromones:[], topology:null, defense:null, rounds:[] },
      ]},
      { id:"th-exp", name:"experiment", type:"thread", children:[
        { id:"col-e5f6", name:"colony-e5f6", type:"colony", status:"queued", round:0, maxRounds:6,
          task:"Test alternative OAuth2 PKCE flow with DPoP binding",
          strategy:"sequential",
          agents:[{name:"Researcher",caste:"researcher",model:"anthropic/claude-sonnet-4.6",tokens:0,status:"pending",pheromone:0}],
          convergence:0, cost:0, pheromones:[], topology:null, defense:null, rounds:[] },
      ]},
    ]},
  { id:"ws-research", name:"research-ttt", type:"workspace",
    config:{ coder_model:null, reviewer_model:null, researcher_model:"anthropic/claude-sonnet-4.6", archivist_model:null, budget:2.0, strategy:"stigmergic" },
    children:[
      { id:"th-main2", name:"main", type:"thread", children:[
        { id:"col-g7h8", name:"colony-g7h8", type:"colony", status:"running", round:2, maxRounds:10,
          task:"Research test-time training for agent memory — TTT-E2E, ZipMap, and hybrid retrieval",
          strategy:"stigmergic",
          agents:[
            {name:"Researcher",caste:"researcher",model:"anthropic/claude-sonnet-4.6",tokens:4200,status:"active",pheromone:0.67},
            {name:"Coder",caste:"coder",model:"ollama/qwen3-30b",tokens:2100,status:"done",pheromone:0.38},
          ],
          convergence:0.41, cost:0.21, pheromones:[{from:"researcher",to:"coder",w:1.2,trend:"up"}],
          topology:null, defense:{ composite:0.09, signals:[{name:"entropy",value:0.05,threshold:1.0},{name:"drift",value:0.12,threshold:0.7}] },
          rounds:[] },
      ]},
    ]},
];

const SYS_DEFAULTS = { coder:"ollama/qwen3-30b", reviewer:"ollama/qwen3-30b", researcher:"ollama/qwen3-30b", archivist:"ollama/qwen3-30b", queen:"anthropic/claude-sonnet-4.6" };
const CASTES = [
  { id:"queen", name:"Queen", icon:"♛", color:V.accent, desc:"Strategic coordinator — fleet evaluation, directive emission, colony lifecycle" },
  { id:"coder", name:"Coder", icon:"⟨/⟩", color:V.success, desc:"Implementation — writes, modifies, and debugs code via tools" },
  { id:"reviewer", name:"Reviewer", icon:"⊘", color:V.purple, desc:"Quality gate — reviews outputs, runs verification, flags issues" },
  { id:"researcher", name:"Researcher", icon:"◎", color:V.blue, desc:"Information specialist — retrieves, synthesizes, cites findings" },
  { id:"archivist", name:"Archivist", icon:"⧫", color:V.warn, desc:"Memory curator — compresses rounds, extracts TKG triples, distills skills" },
];
const LOCAL_MODELS = [
  { id:"qwen3-30b", name:"Qwen 3 30B-A3B", quant:"Q4_K_M", status:"loaded", vram:17.3, ctx:8192, maxCtx:32768, backend:"llama.cpp", gpu:"RTX 5090", slots:2, provider:"ollama" },
  { id:"arctic-embed-s", name:"Arctic Embed S", quant:"F32", status:"loaded", vram:0.09, ctx:512, maxCtx:512, backend:"sentence-transformers (CPU)", gpu:"CPU", slots:0, provider:"local" },
];
const CLOUD_EPS = [
  { id:"anthropic", provider:"Anthropic", models:["claude-sonnet-4.6","claude-opus-4.6","claude-haiku-4.5"], status:"connected", spend:0.62, limit:10.0 },
  { id:"openai", provider:"OpenAI", models:["gpt-5","gpt-5-nano"], status:"no key", spend:0, limit:0 },
];
const INIT_MERGES = [{from:"col-c3d4",to:"col-a1b2",id:"merge-1",active:true}];
const QUEEN_THREADS = [
  { id:"qt-1", name:"auth refactor", wsId:"ws-auth", messages:[
    {role:"operator",text:"Start with the auth module. Prioritize JWT refresh flow.",ts:"14:30:22"},
    {role:"queen",text:"Spawning colony targeting JWT refresh handler. 3 known issues from colony-c3d4 — merging compressed output as context.",ts:"14:30:25"},
    {role:"event",text:"ColonySpawned · col-a1b2 · 3 agents · stigmergic strategy",ts:"14:31:05",kind:"spawn"},
    {role:"event",text:"MergeCreated · col-c3d4 → col-a1b2 · compressed output injected",ts:"14:31:06",kind:"merge"},
    {role:"event",text:"RoundCompleted · R2 · convergence 0.72 · 3 skills extracted",ts:"14:33:45",kind:"metric"},
    {role:"event",text:"Pheromone update · coder→reviewer strengthened to 1.8 (was 1.2)",ts:"14:34:01",kind:"pheromone"},
    {role:"event",text:"ModelRouted · Coder R3 → anthropic/claude-sonnet-4.6 (budget=62%)",ts:"14:36:44",kind:"route"},
  ]},
  { id:"qt-2", name:"TTT research", wsId:"ws-research", messages:[
    {role:"operator",text:"Find recent papers on test-time training for agent memory.",ts:"15:10:00"},
    {role:"queen",text:"Spawning research colony. Researcher routes to cloud for synthesis, local for queries.",ts:"15:10:03"},
    {role:"event",text:"ColonySpawned · col-g7h8 · 2 agents · stigmergic strategy",ts:"15:10:05",kind:"spawn"},
  ]},
];
const APPROVALS_INIT = [{ id:1, type:"Cloud Escalation", agent:"Coder", detail:"anthropic/claude-opus-4.6 · est. $0.42", colony:"col-a1b2" }];
const PROTOCOLS = { mcp:{status:"active",tools:5}, agui:{status:"adapter",events:12}, a2a:{status:"discovery",card:true} };

// ── HELPERS ──────────────────────────────────────────────
function findNode(n,id){for(const x of n){if(x.id===id)return x;if(x.children){const f=findNode(x.children,id);if(f)return f;}}return null;}
function allColonies(n){let o=[];for(const x of n){if(x.type==="colony")o.push(x);if(x.children)o=o.concat(allColonies(x.children));}return o;}
function bc(n,id,p=[]){for(const x of n){const c=[...p,x];if(x.id===id)return c;if(x.children){const f=bc(x.children,id,c);if(f)return f;}}return null;}

// ── ATOMS (design-system primitives) ─────────────────────
const Pill = ({children,color=V.fgMuted,glow,sm,onClick})=>(
  <span onClick={onClick} style={{display:"inline-flex",alignItems:"center",gap:3,
    padding:sm?"1px 7px":"2px 10px",borderRadius:999,
    fontSize:sm?8.5:9.5,fontFamily:F.mono,letterSpacing:"0.05em",fontWeight:500,color,
    background:`${color}12`,border:`1px solid ${color}18`,
    boxShadow:glow?`0 0 14px ${color}18`:"none",cursor:onClick?"pointer":"default"}}>{children}</span>
);
const Dot = ({status,size=6})=>{
  const c={running:V.success,completed:V.secondary,queued:V.warn,loaded:V.success,connected:V.success,
    "no key":V.danger,active:V.success,pending:V.warn,done:V.secondary,failed:V.danger}[status]||V.fgDim;
  const p=status==="running"||status==="active"||status==="loaded";
  return <span style={{display:"inline-block",width:size,height:size,borderRadius:"50%",background:c,flexShrink:0,
    boxShadow:p?`0 0 ${size+4}px ${c}50`:"none",animation:p?"pulse 2.8s ease-in-out infinite":"none"}}/>;
};
const Meter = ({label,value,max,unit="",color=V.accent,compact})=>{
  const v=typeof value==="string"?parseFloat(value):value;
  const p=max>0?Math.min(v/max*100,100):0;
  return (
    <div style={{marginBottom:compact?5:9}}>
      <div style={{display:"flex",justifyContent:"space-between",marginBottom:2}}>
        <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:600}}>{label}</span>
        <span style={{fontSize:10,fontFamily:F.mono,color:V.fgMuted,fontFeatureSettings:'"tnum"'}}>
          {unit==="$"?`$${v.toFixed(2)}`:`${typeof value==="number"?v.toFixed(1):value}${unit}`}
          <span style={{color:V.fgDim}}> / {unit==="$"?`$${max.toFixed(2)}`:`${max}${unit}`}</span>
        </span>
      </div>
      <div style={{height:2,background:"rgba(255,255,255,0.03)",borderRadius:1,overflow:"hidden"}}>
        <div style={{height:"100%",width:`${p}%`,borderRadius:1,
          background:p>85?V.danger:p>65?V.warn:color,transition:"width 0.6s cubic-bezier(0.22,1,0.36,1)",
          boxShadow:p>10?`0 0 8px ${p>85?V.danger:p>65?V.warn:color}30`:"none"}}/>
      </div>
    </div>
  );
};
const Btn=({children,onClick,v="primary",sm,sx,disabled:d})=>{
  const [h,sH]=useState(false);
  const base={fontFamily:F.body,fontSize:sm?10.5:12,fontWeight:500,cursor:d?"default":"pointer",
    borderRadius:999,border:"none",transition:"all 0.2s cubic-bezier(0.22,1,0.36,1)",
    padding:sm?"3px 10px":"7px 16px",opacity:d?0.3:1,display:"inline-flex",alignItems:"center",
    gap:4,whiteSpace:"nowrap",letterSpacing:"0.01em",...sx};
  const vs={
    primary:{background:h&&!d?V.accentBright:V.accent,color:"#fff",boxShadow:h?`0 0 24px ${V.accentGlow}`:"none"},
    secondary:{background:h?"rgba(255,255,255,0.04)":"transparent",color:V.fg,border:`1px solid ${h?V.borderHover:V.border}`},
    ghost:{background:h?"rgba(255,255,255,0.03)":"transparent",color:h?V.fg:V.fgMuted},
    danger:{background:h?"rgba(240,100,100,0.12)":"transparent",color:V.danger,border:`1px solid ${V.danger}25`},
    success:{background:h?"rgba(45,212,168,0.12)":"transparent",color:V.success,border:`1px solid ${V.success}25`},
    merge:{background:h?V.secondary:"transparent",color:h?V.fgOnAccent:V.secondary,border:`1px solid ${V.secondary}35`},
  };
  return <button onClick={d?undefined:onClick} onMouseEnter={()=>sH(true)} onMouseLeave={()=>sH(false)} style={{...base,...vs[v]}}>{children}</button>;
};
const Glass=({children,style:sx,hover,featured,onClick})=>{
  const [h,sH]=useState(false);
  return <div onClick={onClick} onMouseEnter={()=>sH(true)} onMouseLeave={()=>sH(false)}
    style={{background:h&&hover?V.glassHover:V.glass,backdropFilter:"blur(14px)",WebkitBackdropFilter:"blur(14px)",
      border:`1px solid ${featured?V.borderAccent:h&&hover?V.borderHover:V.border}`,
      borderRadius:10,padding:14,transition:"all 0.25s cubic-bezier(0.22,1,0.36,1)",
      cursor:onClick?"pointer":"default",transform:h&&hover?"translateY(-1px)":"none",
      boxShadow:featured?`0 0 28px ${V.accentGlow}`
        :h&&hover?"0 8px 32px rgba(3,3,8,0.6)":"0 1px 2px rgba(3,3,8,0.3)",...sx}}>{children}</div>;
};
const SLabel=({children,sx})=>(
  <div style={{fontSize:8,fontFamily:F.mono,fontWeight:600,color:V.fgDim,letterSpacing:"0.14em",
    textTransform:"uppercase",marginBottom:7,...sx}}>{children}</div>
);
const GradientText=({children,style:sx})=>(
  <span style={{background:`linear-gradient(135deg,${V.accentBright},${V.accent},${V.secondary})`,
    WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent",backgroundClip:"text",...sx}}>{children}</span>
);

// Pheromone intensity bar
const PheromoneBar=({value,max=2,label,trend})=>{
  const p=Math.min(value/max*100,100);
  const trendIcon = trend==="up"?"↑":trend==="down"?"↓":"·";
  const trendColor = trend==="up"?V.success:trend==="down"?V.danger:V.fgDim;
  return(
    <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:4}}>
      <span style={{fontSize:8.5,fontFamily:F.mono,color:V.fgDim,width:80,overflow:"hidden",textOverflow:"ellipsis"}}>{label}</span>
      <div style={{flex:1,height:3,background:"rgba(255,255,255,0.03)",borderRadius:2,overflow:"hidden"}}>
        <div style={{height:"100%",width:`${p}%`,borderRadius:2,
          background:`linear-gradient(90deg,${V.accentMuted},${p>60?V.accent:V.accentMuted})`,
          boxShadow:p>60?`0 0 6px ${V.accentGlow}`:"none",transition:"width 0.5s ease-out"}}/>
      </div>
      <span style={{fontSize:9,fontFamily:F.mono,color:V.fgMuted,fontFeatureSettings:'"tnum"',width:28,textAlign:"right"}}>{value.toFixed(1)}</span>
      <span style={{fontSize:9,color:trendColor,width:10,textAlign:"center"}}>{trendIcon}</span>
    </div>
  );
};

// Defense anomaly gauge
const DefenseGauge=({score,compact})=>{
  const c = score>0.8?V.danger:score>0.6?V.warn:score>0.3?V.accentBright:V.success;
  const label = score>0.8?"HALT":score>0.6?"ESCALATE":score>0.3?"WARN":"NOMINAL";
  const r=compact?16:22;const circ=2*Math.PI*r;const filled=circ*Math.min(score,1);
  return(
    <div style={{display:"flex",alignItems:"center",gap:compact?6:10}}>
      <svg width={r*2+8} height={r*2+8} style={{transform:"rotate(-90deg)"}}>
        <circle cx={r+4} cy={r+4} r={r} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth={compact?2:3}/>
        <circle cx={r+4} cy={r+4} r={r} fill="none" stroke={c} strokeWidth={compact?2:3}
          strokeDasharray={`${filled} ${circ-filled}`} strokeLinecap="round"
          style={{transition:"stroke-dasharray 0.6s ease-out",filter:`drop-shadow(0 0 4px ${c}40)`}}/>
      </svg>
      <div>
        <div style={{fontFamily:F.mono,fontSize:compact?11:14,fontWeight:600,color:c,fontFeatureSettings:'"tnum"'}}>{(score*100).toFixed(0)}%</div>
        <div style={{fontFamily:F.mono,fontSize:compact?7:8,color:V.fgDim,letterSpacing:"0.1em"}}>{label}</div>
      </div>
    </div>
  );
};

// ── TREE NAVIGATOR ──────────────────────────────────────
const TreeNav=({selected,onSelect,expanded,onToggle})=>{
  const icons={workspace:"▣",thread:"▷",colony:"⬡"};
  const colors={workspace:V.accent,thread:V.blue,colony:V.fgMuted};
  const renderNode=(node,depth=0)=>{
    const sel=selected===node.id;const exp=expanded[node.id]!==false;const has=node.children?.length>0;
    return(
      <div key={node.id}>
        <div onClick={()=>onSelect(node.id)}
          style={{padding:`4px 8px 4px ${6+depth*12}px`,cursor:"pointer",display:"flex",alignItems:"center",gap:4,
            background:sel?`${V.accent}0C`:"transparent",borderLeft:sel?`2px solid ${V.accent}`:"2px solid transparent",
            transition:"all 0.12s",fontSize:11,fontFamily:F.mono,borderRadius:sel?"0 3px 3px 0":"0"}}>
          {has?<span onClick={e=>{e.stopPropagation();onToggle(node.id);}}
            style={{color:V.fgDim,fontSize:6,width:8,textAlign:"center",cursor:"pointer"}}>
            {exp?"▼":"▶"}</span>:<span style={{width:8}}/>}
          <span style={{color:colors[node.type],fontSize:9}}>{icons[node.type]}</span>
          <span style={{color:sel?V.fg:V.fgMuted,overflow:"hidden",textOverflow:"ellipsis",flex:1,fontSize:10.5}}>{node.name}</span>
          {node.status&&<Dot status={node.status} size={4}/>}
        </div>
        {has&&exp&&node.children.map(c=>renderNode(c,depth+1))}
      </div>
    );
  };
  return <div style={{paddingTop:1}}>{TREE.map(n=>renderNode(n))}</div>;
};

// ── TOPOLOGY GRAPH ──────────────────────────────────────
const TopoGraph=({topo})=>{
  const [hov,setHov]=useState(null);
  if(!topo) return <div style={{padding:20,color:V.fgDim,fontSize:9.5,fontFamily:F.mono,textAlign:"center",letterSpacing:"0.08em"}}>NO TOPOLOGY DATA</div>;
  return(
    <svg viewBox="0 0 400 270" style={{width:"100%",height:"100%"}}>
      <defs>
        <marker id="arr" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="5" markerHeight="3.5" orient="auto"><path d="M0,0 L10,3 L0,6" fill={V.fgDim}/></marker>
        <filter id="edgeGlow"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      </defs>
      {topo.edges.map((e,i)=>{
        const a=topo.nodes.find(n=>n.id===e.from),b=topo.nodes.find(n=>n.id===e.to);
        if(!a||!b) return null;
        const strong = e.w > 1.2;
        const isHov = hov===e.from||hov===e.to;
        return <g key={`trail-${i}`}>
          {strong&&<line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke={V.accent} strokeWidth={e.w*2} opacity={0.06} filter="url(#edgeGlow)"/>}
          <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke={isHov?`rgba(255,255,255,0.22)`:strong?V.accent:`rgba(255,255,255,${Math.min(e.w/4,0.1)})`}
            strokeWidth={isHov?e.w+0.5:e.w} markerEnd="url(#arr)" opacity={strong?0.6:0.4}
            strokeDasharray={e.w<0.8?"4 3":"none"} style={{transition:"all 0.3s"}}/>
        </g>;
      })}
      {topo.nodes.map(n=>{
        const isH = hov===n.id;
        return(
          <g key={n.id} onMouseEnter={()=>setHov(n.id)} onMouseLeave={()=>setHov(null)} style={{cursor:"pointer"}}>
            {isH&&<circle cx={n.x} cy={n.y} r={24} fill="none" stroke={n.c} strokeWidth={0.5} opacity={0.3}/>}
            <rect x={n.x-32} y={n.y-13} width={64} height={26} rx={6}
              fill={isH?`${n.c}15`:V.surface} stroke={isH?`${n.c}50`:`${n.c}20`} strokeWidth={0.8}
              style={{transition:"all 0.2s"}}/>
            <text x={n.x} y={n.y+3} textAnchor="middle" fill={isH?n.c:V.fgMuted}
              style={{fontFamily:F.mono,fontSize:7.5,letterSpacing:"0.12em",fontWeight:600,transition:"fill 0.2s"}}>{n.label}</text>
          </g>
        );
      })}
    </svg>
  );
};

// ── QUEEN CHAT ──────────────────────────────────────────
const QueenChat=({style:sx,threads,activeThreadId,onSwitchThread,onNewThread})=>{
  const [input,setInput]=useState("");
  const [localThreads,setLocalThreads]=useState(threads);
  const ref=useRef(null);
  const active=localThreads.find(t=>t.id===activeThreadId)||localThreads[0];
  useEffect(()=>{ref.current?.scrollTo({top:ref.current.scrollHeight,behavior:"smooth"});},[active?.messages?.length]);
  const send=()=>{
    if(!input.trim()||!active) return;
    const ts=new Date().toLocaleTimeString("en-US",{hour12:false});
    setLocalThreads(p=>p.map(t=>t.id===active.id?{...t,messages:[...t.messages,{role:"operator",text:input,ts}]}:t));
    setInput("");
    setTimeout(()=>{setLocalThreads(p=>p.map(t=>t.id===active.id?{...t,messages:[...t.messages,
      {role:"queen",text:"Directive queued. Colony will reflect changes next round.",ts:new Date().toLocaleTimeString("en-US",{hour12:false})}]}:t));},500);
  };
  const kindColor={spawn:V.success,merge:V.secondary,metric:V.purple,route:V.warn,pheromone:V.accent};
  return(
    <div style={{display:"flex",flexDirection:"column",background:V.surface,borderRadius:10,border:`1px solid ${V.border}`,overflow:"hidden",...sx}}>
      <div style={{display:"flex",alignItems:"center",borderBottom:`1px solid ${V.border}`,padding:"0 4px",minHeight:36,overflow:"auto",gap:0}}>
        <span style={{fontSize:11,color:V.accent,padding:"0 8px",flexShrink:0,filter:`drop-shadow(0 0 3px ${V.accentGlow})`}}>♛</span>
        {localThreads.map(t=>(
          <div key={t.id} onClick={()=>onSwitchThread(t.id)}
            style={{padding:"7px 10px",cursor:"pointer",fontSize:10.5,fontFamily:F.body,fontWeight:500,whiteSpace:"nowrap",
              color:t.id===active?.id?V.fg:V.fgDim,borderBottom:t.id===active?.id?`2px solid ${V.accent}`:"2px solid transparent",
              transition:"all 0.15s"}}>{t.name}</div>
        ))}
        <div onClick={onNewThread} style={{padding:"7px 8px",cursor:"pointer",fontSize:12,color:V.fgDim,marginLeft:"auto",flexShrink:0}}>+</div>
      </div>
      <div ref={ref} style={{flex:1,overflow:"auto",padding:"8px 0"}}>
        {active?.messages.map((m,i)=>(
          <div key={i} style={{padding:m.role==="event"?"2px 12px":"6px 12px"}}>
            {m.role==="event"?(
              <div style={{display:"flex",alignItems:"center",gap:5,fontSize:10}}>
                <span style={{width:3,height:3,borderRadius:"50%",background:kindColor[m.kind]||V.fgDim,flexShrink:0,
                  boxShadow:`0 0 5px ${kindColor[m.kind]||V.fgDim}35`}}/>
                <span style={{fontFamily:F.mono,fontSize:8.5,color:V.fgDim,fontFeatureSettings:'"tnum"'}}>{m.ts}</span>
                <span style={{color:V.fgDim,fontSize:10}}>{m.text}</span>
              </div>
            ):(
              <div>
                <div style={{display:"flex",alignItems:"center",gap:5,marginBottom:2}}>
                  {m.role==="queen"&&<span style={{fontSize:8,color:V.accent}}>♛</span>}
                  <span style={{fontFamily:F.mono,fontSize:8,color:m.role==="queen"?V.accent:V.fgDim,fontWeight:600,
                    letterSpacing:"0.08em",textTransform:"uppercase"}}>{m.role==="queen"?"Queen":"Operator"}</span>
                  <span style={{fontFamily:F.mono,fontSize:7.5,color:V.fgDim,fontFeatureSettings:'"tnum"'}}>{m.ts}</span>
                </div>
                <div style={{fontSize:12,lineHeight:1.55,color:m.role==="queen"?V.fg:"rgba(237,237,240,0.8)",
                  paddingLeft:m.role==="queen"?14:0}}>{m.text}</div>
              </div>
            )}
          </div>
        ))}
      </div>
      <div style={{padding:"6px 8px",borderTop:`1px solid ${V.border}`,display:"flex",gap:5}}>
        <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&send()}
          placeholder="Direct the Queen..."
          style={{flex:1,background:V.void,border:`1px solid ${V.border}`,borderRadius:999,color:V.fg,
            fontFamily:F.body,fontSize:12,padding:"7px 14px",outline:"none",transition:"border-color 0.2s"}}
          onFocus={e=>e.target.style.borderColor=`${V.accent}40`}
          onBlur={e=>e.target.style.borderColor=V.border}/>
        <Btn sm onClick={send}>Send</Btn>
      </div>
    </div>
  );
};

// ── PROTOCOL STATUS (header bar) ────────────────────────
const ProtocolBar=()=>(
  <div style={{display:"flex",gap:10,alignItems:"center"}}>
    {[
      {label:"MCP",status:PROTOCOLS.mcp.status,detail:`${PROTOCOLS.mcp.tools} tools`},
      {label:"AG-UI",status:PROTOCOLS.agui.status,detail:`${PROTOCOLS.agui.events} events`},
      {label:"A2A",status:PROTOCOLS.a2a.status,detail:"card only"},
    ].map(p=>(
      <div key={p.label} style={{display:"flex",alignItems:"center",gap:4,padding:"2px 8px",
        borderRadius:999,border:`1px solid ${V.border}`,background:V.recessed}}>
        <Dot status={p.status==="active"?"loaded":p.status==="adapter"?"pending":"done"} size={4}/>
        <span style={{fontFamily:F.mono,fontSize:8,fontWeight:600,letterSpacing:"0.08em",color:V.fgDim}}>{p.label}</span>
        <span style={{fontFamily:F.mono,fontSize:8,color:V.fgDim}}>{p.detail}</span>
      </div>
    ))}
  </div>
);

// ═══════════════════════════════════════════════════════════
// VIEWS
// ═══════════════════════════════════════════════════════════

// ── QUEEN OVERVIEW ──────────────────────────────────────
const ViewQueen=({approvals,onApprove,onReject,onNav,queenThreads,activeQT,onSwitchQT,onNewQT})=>{
  const cols=allColonies(TREE);
  const running=cols.filter(c=>c.status==="running");
  const totalCost=cols.reduce((a,c)=>a+(c.cost||0),0);
  const totalTok=cols.reduce((a,c)=>a+(c.agents||[]).reduce((b,ag)=>b+ag.tokens,0),0);
  const totalVram=LOCAL_MODELS.filter(m=>m.status==="loaded").reduce((a,m)=>a+m.vram,0);
  const avgPheromone = running.length>0?running.reduce((a,c)=>{
    const agents=c.agents||[];return a+(agents.reduce((b,ag)=>b+(ag.pheromone||0),0)/Math.max(agents.length,1));
  },0)/running.length:0;

  return(
    <div style={{display:"flex",gap:16,height:"100%",overflow:"hidden"}}>
      <div style={{flex:1,overflow:"auto",paddingRight:4}}>
        <div style={{marginBottom:22}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:5}}>
            <span style={{fontSize:22,filter:`drop-shadow(0 0 8px ${V.accentGlow})`}}>♛</span>
            <h1 style={{fontFamily:F.display,fontSize:22,fontWeight:700,color:V.fg,letterSpacing:"-0.04em",margin:0}}>
              <GradientText>Supercolony</GradientText>
            </h1>
            <Pill color={V.success} glow><Dot status="running" size={4}/> {running.length} active</Pill>
            <div style={{marginLeft:"auto"}}><ProtocolBar/></div>
          </div>
          <p style={{fontSize:11,color:V.fgMuted,margin:0}}>
            {cols.length} colonies · <span style={{fontFamily:F.mono,fontFeatureSettings:'"tnum"'}}>{(totalTok/1000).toFixed(0)}k</span> tokens · <span style={{fontFamily:F.mono,color:V.accent}}>${totalCost.toFixed(2)}</span>
          </p>
        </div>

        {/* Resource strip */}
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:8,marginBottom:20}}>
          <Glass style={{padding:12}}><Meter label="Budget" value={totalCost} max={5} unit="$" compact/></Glass>
          <Glass style={{padding:12}}><Meter label="VRAM" value={totalVram} max={32} unit=" GB" color={V.purple} compact/></Glass>
          <Glass style={{padding:12}}><Meter label="Tokens" value={(totalTok/1000).toFixed(0)} max={200} unit="k" color={V.blue} compact/></Glass>
          <Glass style={{padding:12}}><Meter label="Avg Pheromone" value={avgPheromone.toFixed(2)} max={1} color={V.accent} compact/></Glass>
        </div>

        {/* Approvals */}
        {approvals.length>0&&(
          <div style={{marginBottom:20}}>
            <SLabel>Pending Approvals</SLabel>
            {approvals.map(a=>(
              <Glass key={a.id} featured style={{padding:12,marginBottom:6,display:"flex",alignItems:"center",gap:10}}>
                <div style={{width:3,height:28,borderRadius:2,background:V.accent,flexShrink:0}}/>
                <div style={{flex:1}}>
                  <div style={{fontSize:9,fontFamily:F.mono,color:V.accent,fontWeight:600,letterSpacing:"0.08em",textTransform:"uppercase",marginBottom:1}}>{a.type}</div>
                  <div style={{fontSize:11.5,color:V.fg}}>{a.agent} → {a.detail}</div>
                </div>
                <Btn v="success" sm onClick={()=>onApprove(a.id)}>Approve</Btn>
                <Btn v="danger" sm onClick={()=>onReject(a.id)}>Deny</Btn>
              </Glass>
            ))}
          </div>
        )}

        {/* Colonies by workspace */}
        {TREE.map(ws=>(
          <div key={ws.id} style={{marginBottom:20}}>
            <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:8}}>
              <SLabel sx={{marginBottom:0}}><span style={{color:V.accent}}>▣</span> {ws.name}</SLabel>
              <Pill color={V.fgDim} sm>{ws.config.strategy}</Pill>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
              {allColonies([ws]).map(c=>(
                <Glass key={c.id} hover onClick={()=>onNav(c.id)} style={{padding:12}}>
                  <div style={{display:"flex",alignItems:"center",gap:5,marginBottom:3}}>
                    <Dot status={c.status} size={5}/>
                    <span style={{fontFamily:F.display,fontSize:12,fontWeight:600,color:V.fg}}>{c.name}</span>
                    <Pill color={V.fgDim} sm>{c.strategy||"stigmergic"}</Pill>
                  </div>
                  {c.task&&<div style={{fontSize:10,color:V.fgMuted,marginBottom:5,lineHeight:1.35,
                    overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{c.task}</div>}
                  <div style={{display:"flex",gap:8,fontSize:9.5,fontFamily:F.mono,color:V.fgMuted,fontFeatureSettings:'"tnum"',alignItems:"center"}}>
                    <span>R{c.round}/{c.maxRounds}</span>
                    <span>{(c.agents||[]).length} agents</span>
                    {c.convergence>0&&<span style={{color:c.convergence>0.8?V.success:V.fgMuted}}>conv {(c.convergence*100).toFixed(0)}%</span>}
                    {c.defense&&<DefenseGauge score={c.defense.composite} compact/>}
                  </div>
                  {c.maxRounds>0&&c.round>0&&(
                    <div style={{height:2,background:"rgba(255,255,255,0.03)",borderRadius:1,marginTop:7}}>
                      <div style={{height:"100%",borderRadius:1,width:`${(c.round/c.maxRounds)*100}%`,
                        background:c.status==="completed"?V.success:V.accent,transition:"width 0.4s"}}/>
                    </div>
                  )}
                </Glass>
              ))}
            </div>
          </div>
        ))}
      </div>
      <QueenChat style={{width:320,flexShrink:0}} threads={queenThreads} activeThreadId={activeQT} onSwitchThread={onSwitchQT} onNewThread={onNewQT}/>
    </div>
  );
};

// ── THREAD VIEW (NEW — with merge edge visualization) ───
const ViewThread=({thread,parentWs,merges,onNav,onMerge,onPrune,onBroadcast})=>{
  if(!thread) return null;
  const cols = thread.children||[];
  const [mergeMode,setMergeMode]=useState(null); // null | colonyId (source)
  const activeMerges = merges.filter(m=>m.active);

  return(
    <div style={{overflow:"auto",height:"100%"}}>
      <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:4}}>
        <span style={{fontSize:12,color:V.blue}}>▷</span>
        <h2 style={{fontFamily:F.display,fontSize:18,fontWeight:700,color:V.fg,margin:0}}>{thread.name}</h2>
        <Pill color={V.fgMuted} sm>{cols.length} colonies</Pill>
        {parentWs&&<Pill color={V.accent} sm>▣ {parentWs.name}</Pill>}
        <div style={{marginLeft:"auto",display:"flex",gap:5}}>
          <Btn v="secondary" sm>+ Spawn Colony</Btn>
          <Btn v="merge" sm onClick={()=>setMergeMode(mergeMode?null:"picking")}>{mergeMode?"Cancel Merge":"⊕ Merge"}</Btn>
          <Btn v="secondary" sm onClick={onBroadcast}>⊗ Broadcast</Btn>
        </div>
      </div>
      {mergeMode&&<div style={{padding:"6px 12px",background:V.accentMuted,borderRadius:7,border:`1px solid ${V.accent}20`,marginBottom:12,
        fontSize:11,color:V.accent,fontFamily:F.body}}>
        {mergeMode==="picking"?"Click a SOURCE colony to begin merge":"Now click the TARGET colony to complete merge from "+mergeMode}
      </div>}

      {/* Colony cards with merge edges */}
      <div style={{position:"relative",paddingTop:8}}>
        {/* Draw merge edge arrows between colonies */}
        {activeMerges.length>0&&(
          <svg style={{position:"absolute",top:0,left:0,width:"100%",height:"100%",pointerEvents:"none",zIndex:1}}>
            <defs>
              <marker id="mergeArr" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="6" markerHeight="4" orient="auto">
                <path d="M0,0 L10,3 L0,6" fill={V.secondary}/>
              </marker>
            </defs>
            {activeMerges.map((m,i)=>{
              const fromIdx=cols.findIndex(c=>c.id===m.from);
              const toIdx=cols.findIndex(c=>c.id===m.to);
              if(fromIdx<0||toIdx<0) return null;
              const y1=fromIdx*90+45; const y2=toIdx*90+45;
              return <g key={m.id}>
                <path d={`M 20 ${y1} C -20 ${y1}, -20 ${y2}, 20 ${y2}`}
                  stroke={V.secondary} strokeWidth={1.5} fill="none" opacity={0.5} markerEnd="url(#mergeArr)"
                  strokeDasharray="4 2"/>
                <text x={-8} y={(y1+y2)/2+3} fill={V.secondary} fontSize={7} fontFamily={F.mono} textAnchor="middle" opacity={0.6}>MERGE</text>
              </g>;
            })}
          </svg>
        )}
        <div style={{display:"flex",flexDirection:"column",gap:8,paddingLeft:30}}>
          {cols.map((c,ci)=>{
            const hasMergeFrom = activeMerges.some(m=>m.from===c.id);
            const hasMergeTo = activeMerges.some(m=>m.to===c.id);
            return(
              <Glass key={c.id} hover
                onClick={()=>{
                  if(mergeMode==="picking"){setMergeMode(c.id);}
                  else if(mergeMode&&mergeMode!=="picking"){onMerge(mergeMode,c.id);setMergeMode(null);}
                  else{onNav(c.id);}
                }}
                style={{padding:14,borderLeft:hasMergeTo?`3px solid ${V.secondary}`:hasMergeFrom?`3px solid ${V.secondary}40`:"3px solid transparent",
                  cursor:mergeMode?"crosshair":"pointer"}}>
                <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:4}}>
                  <Dot status={c.status} size={6}/>
                  <span style={{fontFamily:F.display,fontSize:13,fontWeight:600,color:V.fg}}>{c.name}</span>
                  <Pill color={V.fgDim} sm>{c.strategy||"stigmergic"}</Pill>
                  <span style={{fontSize:9.5,fontFamily:F.mono,color:V.fgMuted,fontFeatureSettings:'"tnum"',marginLeft:"auto"}}>
                    R{c.round}/{c.maxRounds} · {(c.agents||[]).length} agents
                  </span>
                  {hasMergeTo&&<Pill color={V.secondary} sm>← receiving merge</Pill>}
                  {hasMergeFrom&&<Pill color={V.secondary} sm>→ merged out</Pill>}
                </div>
                {c.task&&<div style={{fontSize:11,color:V.fgMuted,lineHeight:1.4,marginBottom:6}}>{c.task}</div>}
                <div style={{display:"flex",gap:8,alignItems:"center"}}>
                  {c.convergence>0&&(
                    <div style={{flex:1}}>
                      <Meter label="Convergence" value={c.convergence} max={1} color={c.convergence>0.8?V.success:V.accent} compact/>
                    </div>
                  )}
                  {c.defense&&<DefenseGauge score={c.defense.composite} compact/>}
                  <div style={{display:"flex",gap:3,marginLeft:"auto"}}>
                    {activeMerges.filter(m=>m.to===c.id).map(m=>(
                      <Btn key={m.id} v="danger" sm onClick={(e)=>{e.stopPropagation();onPrune(m.id);}}>✕ Prune</Btn>
                    ))}
                  </div>
                </div>
              </Glass>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// ── COLONY DETAIL ──────────────────────────────────────
const ViewColony=({colony,queenThreads,activeQT,onSwitchQT,onNewQT})=>{
  if(!colony) return null;
  const totalTokens=(colony.agents||[]).reduce((a,ag)=>a+ag.tokens,0);
  return(
    <div style={{display:"flex",gap:16,height:"100%",overflow:"hidden"}}>
      <div style={{flex:1,overflow:"auto",paddingRight:4}}>
        <div style={{marginBottom:5}}>
          <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:3}}>
            <span style={{fontFamily:F.display,fontSize:18,fontWeight:700,color:V.fg,letterSpacing:"-0.03em"}}>⬡ {colony.name}</span>
            <Pill color={colony.status==="running"?V.success:colony.status==="completed"?V.secondary:V.warn} glow>
              <Dot status={colony.status} size={4}/> {colony.status}
            </Pill>
            <Pill color={V.fgDim} sm>{colony.strategy||"stigmergic"}</Pill>
          </div>
          {colony.task&&<p style={{fontSize:11,color:V.fgMuted,margin:0,marginBottom:12,lineHeight:1.4}}>{colony.task}</p>}
        </div>

        <div style={{display:"grid",gridTemplateColumns:"3fr 2fr",gap:10,marginBottom:16}}>
          <Glass style={{padding:0,overflow:"hidden"}}>
            <div style={{padding:"6px 12px",borderBottom:`1px solid ${V.border}`,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
              <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:600}}>
                Topology · Pheromone Trails
              </span>
              <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,fontFeatureSettings:'"tnum"'}}>R{colony.round}/{colony.maxRounds}</span>
            </div>
            <div style={{height:190}}><TopoGraph topo={colony.topology}/></div>
          </Glass>
          <div style={{display:"flex",flexDirection:"column",gap:10}}>
            <Glass style={{padding:12,flex:1}}>
              <Meter label="Convergence" value={colony.convergence} max={1} color={colony.convergence>0.8?V.success:V.accent} compact/>
              <Meter label="Cost" value={colony.cost} max={5} unit="$" compact/>
              <Meter label="Tokens" value={(totalTokens/1000).toFixed(1)} max={80} unit="k" color={V.blue} compact/>
            </Glass>
            {colony.defense&&(
              <Glass style={{padding:12}}>
                <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:6}}>
                  <SLabel sx={{marginBottom:0}}>Defense</SLabel>
                  <DefenseGauge score={colony.defense.composite} compact/>
                </div>
                {colony.defense.signals.map(s=>(
                  <PheromoneBar key={s.name} value={s.value} max={s.threshold} label={s.name} trend="stable"/>
                ))}
              </Glass>
            )}
          </div>
        </div>

        {colony.pheromones?.length>0&&(
          <div style={{marginBottom:16}}>
            <SLabel>Pheromone Trails</SLabel>
            <Glass style={{padding:12}}>
              {colony.pheromones.map((p,i)=>(
                <PheromoneBar key={i} value={p.w} max={2} label={`${p.from}→${p.to}`} trend={p.trend}/>
              ))}
            </Glass>
          </div>
        )}

        <SLabel>Agents</SLabel>
        <Glass style={{padding:0,marginBottom:16,overflow:"hidden"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontFamily:F.mono,fontSize:10.5}}>
            <thead><tr style={{borderBottom:`1px solid ${V.border}`}}>
              {["","Agent","Caste","Model","Tokens","Pheromone","Status"].map(h=>
                <th key={h} style={{padding:"6px 8px",textAlign:"left",color:V.fgDim,fontWeight:600,fontSize:7.5,
                  letterSpacing:"0.12em",textTransform:"uppercase"}}>{h}</th>)}
            </tr></thead>
            <tbody>{(colony.agents||[]).map((a,i)=>(
              <tr key={i} style={{borderBottom:i<colony.agents.length-1?`1px solid ${V.border}`:"none"}}>
                <td style={{padding:"6px 8px"}}><Dot status={a.status} size={5}/></td>
                <td style={{padding:"6px 8px",color:V.fg,fontWeight:500}}>{a.name}</td>
                <td style={{padding:"6px 8px",color:V.fgMuted,fontSize:9.5}}>{a.caste}</td>
                <td style={{padding:"6px 8px",color:V.fgMuted,fontSize:9.5}}>{a.model}</td>
                <td style={{padding:"6px 8px",color:V.fgMuted,fontFeatureSettings:'"tnum"'}}>{a.tokens>0?`${(a.tokens/1000).toFixed(1)}k`:"—"}</td>
                <td style={{padding:"6px 8px"}}>
                  <div style={{width:40,height:3,background:"rgba(255,255,255,0.03)",borderRadius:2,overflow:"hidden"}}>
                    <div style={{height:"100%",width:`${(a.pheromone||0)*100}%`,borderRadius:2,
                      background:V.accent,boxShadow:a.pheromone>0.6?`0 0 4px ${V.accentGlow}`:"none"}}/>
                  </div>
                </td>
                <td style={{padding:"6px 8px"}}><Pill color={a.status==="active"?V.success:a.status==="done"?V.secondary:V.warn} sm>{a.status}</Pill></td>
              </tr>
            ))}</tbody>
          </table>
        </Glass>

        <div style={{display:"flex",gap:6,marginBottom:16}}>
          <Btn v="secondary" sm>Intervene</Btn>
          <Btn v="secondary" sm>Extend Rounds</Btn>
          <Btn v="secondary" sm>Switch Strategy</Btn>
          <Btn v="danger" sm>Kill Colony</Btn>
        </div>

        {colony.rounds?.length>0&&(<>
          <SLabel>Round History</SLabel>
          <Glass style={{padding:12}}>
            {colony.rounds.map((r,ri)=>{
              const pc=r.phase==="Goal"?V.accent:r.phase==="Route"?V.warn:V.blue;
              return(
                <div key={ri} style={{paddingLeft:10,borderLeft:`2px solid ${pc}`,marginBottom:ri<colony.rounds.length-1?10:0}}>
                  <div style={{display:"flex",alignItems:"center",gap:5,marginBottom:3}}>
                    <span style={{fontFamily:F.display,fontSize:11,fontWeight:700,color:pc}}>R{r.r}</span>
                    <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.08em"}}>{r.phase}</span>
                  </div>
                  {r.agents.map((a,ai)=>(
                    <div key={ai} style={{display:"flex",alignItems:"center",gap:5,padding:"1px 0 1px 4px",fontSize:9.5}}>
                      <Dot status={a.s} size={4}/>
                      <span style={{color:V.fgMuted,width:55}}>{a.n}</span>
                      <span style={{color:V.fgDim,fontSize:9}}>{a.m}</span>
                      {a.t>0&&<span style={{color:V.fgDim,fontSize:9,marginLeft:"auto",fontFeatureSettings:'"tnum"'}}>{(a.t/1000).toFixed(1)}k</span>}
                    </div>
                  ))}
                </div>
              );
            })}
          </Glass>
        </>)}
      </div>
      <QueenChat style={{width:280,flexShrink:0}} threads={queenThreads} activeThreadId={activeQT} onSwitchThread={onSwitchQT} onNewThread={onNewQT}/>
    </div>
  );
};

// ── WORKSPACE CONFIG (NEW) ──────────────────────────────
const ViewWorkspace=({ws,onNav})=>{
  if(!ws) return null;
  const cols=allColonies([ws]);
  const totalCost=cols.reduce((a,c)=>a+(c.cost||0),0);
  return(
    <div style={{overflow:"auto",height:"100%",maxWidth:860}}>
      <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:16}}>
        <span style={{fontSize:14,color:V.accent}}>▣</span>
        <h2 style={{fontFamily:F.display,fontSize:18,fontWeight:700,color:V.fg,margin:0}}>{ws.name}</h2>
        <Pill color={V.fgDim} sm>{ws.config?.strategy||"stigmergic"}</Pill>
        <span style={{fontSize:10,fontFamily:F.mono,color:V.fgMuted,marginLeft:"auto"}}>{cols.length} colonies · ${totalCost.toFixed(2)}</span>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:20}}>
        {/* Model Overrides */}
        <Glass style={{padding:14}}>
          <SLabel>Model Cascade Overrides</SLabel>
          <div style={{fontSize:9.5,color:V.fgDim,marginBottom:10,lineHeight:1.4}}>
            Set to override system defaults. <span style={{fontFamily:F.mono,color:V.fg}}>null</span> inherits from system.
          </div>
          {CASTES.filter(c=>c.id!=="queen").map(c=>{
            const val=ws.config?.[`${c.id}_model`];
            return(
              <div key={c.id} style={{display:"flex",alignItems:"center",gap:6,padding:"5px 0",borderBottom:`1px solid ${V.border}`}}>
                <span style={{fontSize:10,filter:`drop-shadow(0 0 2px ${c.color}25)`}}>{c.icon}</span>
                <span style={{fontSize:10.5,color:V.fg,width:70}}>{c.name}</span>
                <span style={{fontFamily:F.mono,fontSize:10,color:val?V.fg:V.fgDim,flex:1}}>{val||"null (inherit)"}</span>
                {val&&<Pill color={c.color} sm>override</Pill>}
                <Btn v="ghost" sm>{val?"Edit":"Set"}</Btn>
              </div>
            );
          })}
        </Glass>

        {/* Governance */}
        <Glass style={{padding:14}}>
          <SLabel>Governance & Budget</SLabel>
          <Meter label="Budget Used" value={totalCost} max={ws.config?.budget||5} unit="$" color={V.accent}/>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginTop:10}}>
            {[
              {l:"Strategy",v:ws.config?.strategy||"stigmergic"},
              {l:"Budget Limit",v:`$${(ws.config?.budget||5).toFixed(2)}`},
              {l:"Max Rounds",v:"25 (system)"},
              {l:"Convergence θ",v:"0.95"},
            ].map(({l,v})=>(
              <div key={l}>
                <div style={{fontSize:7.5,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.12em",textTransform:"uppercase",marginBottom:2,fontWeight:600}}>{l}</div>
                <div style={{fontSize:11,fontFamily:F.mono,color:V.fg}}>{v}</div>
              </div>
            ))}
          </div>
          <div style={{marginTop:10,display:"flex",gap:5}}>
            <Btn v="secondary" sm>Edit Config</Btn>
            <Btn v="danger" sm>Reset Budget</Btn>
          </div>
        </Glass>
      </div>

      <SLabel>Threads</SLabel>
      {(ws.children||[]).map(th=>(
        <Glass key={th.id} hover onClick={()=>onNav(th.id)} style={{padding:12,marginBottom:6}}>
          <div style={{display:"flex",alignItems:"center",gap:5}}>
            <span style={{color:V.blue,fontSize:10}}>▷</span>
            <span style={{fontFamily:F.display,fontSize:12.5,fontWeight:600,color:V.fg}}>{th.name}</span>
            <span style={{fontSize:9.5,fontFamily:F.mono,color:V.fgMuted,marginLeft:"auto"}}>{(th.children||[]).length} colonies</span>
          </div>
        </Glass>
      ))}
    </div>
  );
};

// ── MODEL REGISTRY ──────────────────────────────────────
const ViewModels=()=>{
  const [expanded,setExpanded]=useState(null);
  const totalVram=LOCAL_MODELS.reduce((a,m)=>a+m.vram,0);
  const cloudSpend=CLOUD_EPS.reduce((a,c)=>a+c.spend,0);
  return(
    <div style={{overflow:"auto",height:"100%",maxWidth:860}}>
      <div style={{marginBottom:20}}>
        <h2 style={{fontFamily:F.display,fontSize:20,fontWeight:700,color:V.fg,letterSpacing:"-0.03em",margin:0,marginBottom:3}}>
          <GradientText>Model Registry</GradientText>
        </h2>
        <p style={{fontSize:10.5,color:V.fgMuted,margin:0}}>
          <span style={{fontFamily:F.mono,color:V.fg}}>provider/model-name</span> · nullable cascade: thread → workspace → system
        </p>
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:8,marginBottom:20}}>
        <Glass style={{padding:12}}><Meter label="GPU VRAM" value={totalVram} max={32} unit=" GB" color={V.purple} compact/>
          <div style={{fontSize:8.5,fontFamily:F.mono,color:V.fgDim}}>RTX 5090 · 32 GB</div></Glass>
        <Glass style={{padding:12}}><Meter label="Cloud Spend" value={cloudSpend} max={10} unit="$" color={V.secondary} compact/>
          <div style={{fontSize:8.5,fontFamily:F.mono,color:V.fgDim}}>daily cap $10.00</div></Glass>
        <Glass style={{padding:12}}>
          <div style={{display:"flex",alignItems:"baseline",gap:5}}>
            <span style={{fontFamily:F.mono,fontSize:20,fontWeight:600,color:V.fg,fontFeatureSettings:'"tnum"'}}>{LOCAL_MODELS.length}</span>
            <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.1em",textTransform:"uppercase"}}>local</span>
          </div>
          <div style={{display:"flex",alignItems:"baseline",gap:5}}>
            <span style={{fontFamily:F.mono,fontSize:20,fontWeight:600,color:V.fg,fontFeatureSettings:'"tnum"'}}>{CLOUD_EPS.filter(c=>c.status==="connected").length}</span>
            <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.1em",textTransform:"uppercase"}}>cloud</span>
          </div>
        </Glass>
      </div>

      <SLabel>Local Models</SLabel>
      <div style={{display:"flex",flexDirection:"column",gap:6,marginBottom:20}}>
        {LOCAL_MODELS.map(m=>{
          const exp=expanded===m.id;
          return(
            <Glass key={m.id} hover={!exp} onClick={()=>setExpanded(exp?null:m.id)} style={{padding:0,overflow:"hidden"}}>
              <div style={{padding:12,display:"flex",alignItems:"center",gap:10}}>
                <Dot status={m.status} size={7}/>
                <div style={{flex:1}}>
                  <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:1}}>
                    <span style={{fontFamily:F.display,fontSize:13,fontWeight:600,color:V.fg}}>{m.name}</span>
                    <Pill color={V.success} sm>{m.status}</Pill>
                    <Pill color={V.fgDim} sm>{m.quant}</Pill>
                  </div>
                  <div style={{fontSize:9.5,fontFamily:F.mono,color:V.fgDim,display:"flex",gap:10,fontFeatureSettings:'"tnum"'}}>
                    <span>{m.provider}/{m.id}</span>
                    <span>{m.backend}</span>
                    <span>ctx {m.ctx.toLocaleString()}</span>
                    {m.vram>0&&<span style={{color:V.purple}}>{m.vram} GB</span>}
                  </div>
                </div>
                <Btn v="ghost" sm onClick={e=>{e.stopPropagation();setExpanded(exp?null:m.id);}}>{exp?"▲":"▼"}</Btn>
              </div>
              {exp&&(
                <div style={{borderTop:`1px solid ${V.border}`,padding:12,background:V.recessed}}>
                  <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10}}>
                    {[{l:"GPU",v:m.gpu},{l:"Slots",v:m.slots},{l:"Max Ctx",v:m.maxCtx.toLocaleString()},
                      {l:"VRAM",v:m.vram>0?`${m.vram} GB`:"CPU"},{l:"Quant",v:m.quant},{l:"Backend",v:m.backend}].map(({l,v})=>(
                      <div key={l}>
                        <div style={{fontSize:7.5,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.12em",textTransform:"uppercase",marginBottom:2,fontWeight:600}}>{l}</div>
                        <div style={{fontSize:11,fontFamily:F.mono,color:V.fg,fontFeatureSettings:'"tnum"'}}>{v}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Glass>
          );
        })}
        <Btn v="secondary" sm sx={{alignSelf:"flex-start"}}>+ Load Model</Btn>
      </div>

      <SLabel>Cloud Endpoints</SLabel>
      <div style={{display:"flex",flexDirection:"column",gap:6,marginBottom:20}}>
        {CLOUD_EPS.map(c=>(
          <Glass key={c.id} style={{padding:12}}>
            <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:6}}>
              <Dot status={c.status} size={6}/>
              <span style={{fontFamily:F.display,fontSize:13,fontWeight:600,color:V.fg}}>{c.provider}</span>
              <Pill color={c.status==="connected"?V.success:V.danger} sm>{c.status}</Pill>
              {c.status==="no key"&&<Btn v="ghost" sm>Add Key</Btn>}
              {c.status==="connected"&&<span style={{marginLeft:"auto",fontFamily:F.mono,fontSize:9.5,color:V.fgMuted,fontFeatureSettings:'"tnum"'}}>
                ${c.spend.toFixed(2)} / ${c.limit.toFixed(2)}</span>}
            </div>
            <div style={{display:"flex",gap:3,flexWrap:"wrap"}}>
              {c.models.map(m=><Pill key={m} color={c.status==="connected"?V.fg:V.fgDim} sm>{m}</Pill>)}
            </div>
            {c.status==="connected"&&<div style={{marginTop:8}}><Meter label="Daily" value={c.spend} max={c.limit} unit="$" color={V.secondary} compact/></div>}
          </Glass>
        ))}
        <Btn v="secondary" sm sx={{alignSelf:"flex-start"}}>+ Add Endpoint</Btn>
      </div>

      <SLabel>Default Resolution Cascade</SLabel>
      <Glass style={{padding:12}}>
        <div style={{fontSize:9.5,color:V.fgDim,marginBottom:8,lineHeight:1.45}}>
          Nullable cascade: <span style={{color:V.fg,fontFamily:F.mono}}>thread → workspace → system</span>. Null inherits from parent.
        </div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:6}}>
          {CASTES.map(c=>(
            <div key={c.id} style={{textAlign:"center",padding:7,background:V.void,borderRadius:7,border:`1px solid ${c.color}12`}}>
              <div style={{fontSize:13,marginBottom:3,filter:`drop-shadow(0 0 3px ${c.color}25)`}}>{c.icon}</div>
              <div style={{fontSize:9,fontFamily:F.display,fontWeight:600,color:V.fg,marginBottom:1}}>{c.name}</div>
              <div style={{fontSize:7.5,fontFamily:F.mono,color:V.fgDim,wordBreak:"break-all"}}>{SYS_DEFAULTS[c.id]}</div>
            </div>
          ))}
        </div>
      </Glass>
    </div>
  );
};

// ── CASTES ──────────────────────────────────────────────
const ViewCastes=()=>{
  const [sel,setSel]=useState("queen");
  const c=CASTES.find(x=>x.id===sel);
  return(
    <div style={{display:"flex",gap:14,height:"100%",overflow:"hidden"}}>
      <div style={{width:150,flexShrink:0,background:V.surface,borderRadius:10,border:`1px solid ${V.border}`,overflow:"hidden"}}>
        <div style={{padding:"8px 12px",borderBottom:`1px solid ${V.border}`,fontFamily:F.display,fontSize:11,fontWeight:600,color:V.fg}}>Castes</div>
        {CASTES.map(x=>(
          <div key={x.id} onClick={()=>setSel(x.id)}
            style={{padding:"7px 12px",cursor:"pointer",display:"flex",alignItems:"center",gap:6,
              background:sel===x.id?`${x.color}0C`:"transparent",borderLeft:sel===x.id?`2px solid ${x.color}`:"2px solid transparent"}}>
            <span style={{fontSize:11,filter:sel===x.id?`drop-shadow(0 0 2px ${x.color}35)`:"none"}}>{x.icon}</span>
            <span style={{fontSize:10.5,color:sel===x.id?V.fg:V.fgMuted,fontWeight:sel===x.id?500:400}}>{x.name}</span>
          </div>
        ))}
      </div>
      {c&&(
        <div style={{flex:1,overflow:"auto"}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
            <span style={{fontSize:24,filter:`drop-shadow(0 0 5px ${c.color}35)`}}>{c.icon}</span>
            <h2 style={{fontFamily:F.display,fontSize:20,fontWeight:700,color:V.fg,margin:0}}>{c.name}</h2>
          </div>
          <p style={{fontSize:11,color:V.fgMuted,marginBottom:16}}>{c.desc}</p>
          <SLabel>System Default</SLabel>
          <Glass style={{padding:12,marginBottom:14,display:"flex",alignItems:"center",gap:8}}>
            <span style={{fontFamily:F.mono,fontSize:11.5,color:V.fg}}>{SYS_DEFAULTS[c.id]}</span>
            <span style={{fontSize:9,fontFamily:F.mono,color:V.fgDim}}>— overridable per workspace, per thread</span>
            <Btn v="secondary" sm sx={{marginLeft:"auto"}}>Change</Btn>
          </Glass>
          <SLabel>Workspace Overrides</SLabel>
          <Glass style={{padding:12}}>
            {TREE.map(ws=>{
              const val=ws.config?.[`${c.id}_model`];
              return(
                <div key={ws.id} style={{display:"flex",alignItems:"center",gap:7,padding:"4px 0",borderBottom:`1px solid ${V.border}`}}>
                  <span style={{fontSize:9,color:V.accent}}>▣</span>
                  <span style={{fontSize:10.5,color:V.fgMuted,width:120}}>{ws.name}</span>
                  <span style={{fontFamily:F.mono,fontSize:10,color:val?V.fg:V.fgDim}}>{val||"null (inherit)"}</span>
                  {val&&<Pill color={c.color} sm>override</Pill>}
                </div>
              );
            })}
          </Glass>
        </div>
      )}
    </div>
  );
};

// ── SETTINGS ────────────────────────────────────────────
const ViewSettings=()=>(
  <div style={{maxWidth:580,overflow:"auto",height:"100%"}}>
    <h2 style={{fontFamily:F.display,fontSize:20,fontWeight:700,color:V.fg,marginBottom:18}}>Settings</h2>
    <SLabel>Event Store</SLabel>
    <Glass style={{padding:12,marginBottom:16}}>
      <div style={{fontSize:10.5,fontFamily:F.mono,color:V.fgMuted,marginBottom:8}}>Single SQLite · WAL mode · append-only</div>
      <div style={{display:"flex",gap:5}}>
        <Btn v="secondary" sm>Export Events</Btn>
        <Btn v="secondary" sm>Rebuild Projections</Btn>
        <Btn v="danger" sm>Reset State</Btn>
      </div>
    </Glass>
    <SLabel>Coordination Strategy</SLabel>
    <Glass style={{padding:12,marginBottom:16}}>
      <div style={{fontSize:10.5,color:V.fgMuted,marginBottom:8,lineHeight:1.4}}>
        System default strategy. Overridable per workspace.
      </div>
      <div style={{display:"flex",gap:6}}>
        <Pill color={V.accent} glow>stigmergic (active)</Pill>
        <Pill color={V.fgDim}>sequential</Pill>
      </div>
    </Glass>
    <SLabel>Protocols</SLabel>
    <Glass style={{padding:12}}>
      {[["MCP","Streamable HTTP · 5 tools exposed","active"],["AG-UI","SSE adapter · 12 event types mapped","adapter"],["A2A","Static Agent Card · discovery only","discovery"]].map(([n,d,s])=>(
        <div key={n} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:`1px solid ${V.border}`}}>
          <Dot status={s==="active"?"loaded":"pending"} size={4}/>
          <span style={{fontFamily:F.mono,fontSize:10.5,fontWeight:600,color:V.fg,width:50}}>{n}</span>
          <span style={{fontSize:10,color:V.fgMuted}}>{d}</span>
          <Pill color={V.fgDim} sm sx={{marginLeft:"auto"}}>{s}</Pill>
        </div>
      ))}
    </Glass>
  </div>
);

// ═══════════════════════════════════════════════════════════
// MAIN SHELL
// ═══════════════════════════════════════════════════════════
export default function FormicOS() {
  const [view,setView]=useState("queen");
  const [treeSel,setTreeSel]=useState(null);
  const [treeExp,setTreeExp]=useState({});
  const [approvals,setApprovals]=useState(APPROVALS_INIT);
  const [merges,setMerges]=useState(INIT_MERGES);
  const [activeQT,setActiveQT]=useState("qt-1");
  const [sideOpen,setSideOpen]=useState(false);

  const navTree=id=>{setTreeSel(id);setView("tree");};
  const navTab=v=>{setView(v);if(v!=="tree")setTreeSel(null);};
  const newQT=()=>{const id=`qt-${Date.now()}`;QUEEN_THREADS.push({id,name:`thread ${QUEEN_THREADS.length+1}`,wsId:null,messages:[]});setActiveQT(id);};
  const handleMerge=(fromId,toId)=>{
    const id=`merge-${Date.now()}`;
    setMerges(p=>[...p,{from:fromId,to:toId,id,active:true}]);
  };
  const handlePrune=(mergeId)=>{
    setMerges(p=>p.map(m=>m.id===mergeId?{...m,active:false}:m));
  };
  const handleBroadcast=()=>{/* TODO: merge active colony to all siblings */};

  const selNode=treeSel?findNode(TREE,treeSel):null;
  const crumbs=treeSel?bc(TREE,treeSel):null;
  const showTree=view==="tree"||view==="queen";
  const showFull=showTree||sideOpen;
  const totalVram=LOCAL_MODELS.filter(m=>m.status==="loaded").reduce((a,m)=>a+m.vram,0);
  const totalCost=allColonies(TREE).reduce((a,c)=>a+(c.cost||0),0);

  // Find parent workspace for thread views
  const parentWs = selNode?.type==="thread"
    ? TREE.find(ws=>(ws.children||[]).some(th=>th.id===selNode.id))
    : null;

  const NAV=[{id:"queen",label:"Queen",icon:"♛"},{id:"models",label:"Models",icon:"◈"},{id:"castes",label:"Castes",icon:"⬡"},{id:"settings",label:"Settings",icon:"⚙"}];

  return(
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=IBM+Plex+Mono:wght@400;500;600&family=Outfit:wght@400;500;600;700;800&display=swap');
        @import url('https://api.fontshare.com/v2/css?f[]=satoshi@500,600,700,800&f[]=geist@400,500,600&display=swap');
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.25}}
        *{box-sizing:border-box;margin:0;padding:0;}
        ::-webkit-scrollbar{width:3px;}::-webkit-scrollbar-track{background:transparent;}
        ::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.03);border-radius:2px;}
        ::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,0.06);}
        ::selection{background:${V.accent}25;}
        @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:0.01ms!important;transition-duration:0.01ms!important;}}
      `}</style>

      {/* Atmosphere layers */}
      <div style={{position:"fixed",inset:0,pointerEvents:"none",zIndex:0}}>
        <div style={{position:"absolute",top:"-30%",left:"25%",width:800,height:800,borderRadius:"50%",filter:"blur(200px)",opacity:0.02,
          background:`radial-gradient(circle,${V.accent},transparent 70%)`}}/>
        <div style={{position:"absolute",bottom:"-35%",right:"15%",width:600,height:600,borderRadius:"50%",filter:"blur(170px)",opacity:0.012,
          background:`radial-gradient(circle,${V.secondary},transparent 70%)`}}/>
      </div>
      <div style={{position:"fixed",inset:0,pointerEvents:"none",zIndex:1,opacity:0.012,
        backgroundImage:"linear-gradient(rgba(255,255,255,0.012) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.012) 1px,transparent 1px)",
        backgroundSize:"64px 64px"}}/>

      <div style={{position:"fixed",inset:0,background:V.void,color:V.fg,fontFamily:F.body,display:"flex",flexDirection:"column",zIndex:3}}>

        {/* TOP BAR */}
        <div style={{height:40,borderBottom:`1px solid ${V.border}`,display:"flex",alignItems:"center",padding:"0 14px",gap:14,flexShrink:0,
          background:"rgba(6,6,12,0.85)",backdropFilter:"blur(14px)",WebkitBackdropFilter:"blur(14px)"}}>
          <div style={{display:"flex",alignItems:"center",gap:6,cursor:"pointer"}} onClick={()=>navTab("queen")}>
            <span style={{fontFamily:F.display,fontWeight:800,fontSize:15,color:V.fg,letterSpacing:"-0.04em"}}>
              formic<span style={{color:V.accent}}>OS</span>
            </span>
            <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.05em"}}>2.0.0-α</span>
          </div>
          {view==="tree"&&crumbs&&(
            <div style={{display:"flex",alignItems:"center",gap:2,fontSize:10.5,fontFamily:F.mono}}>
              {crumbs.map((n,i)=>(
                <span key={n.id} style={{display:"flex",alignItems:"center",gap:2}}>
                  {i>0&&<span style={{color:V.fgDim,fontSize:7}}>⟩</span>}
                  <span onClick={()=>navTree(n.id)} style={{color:i===crumbs.length-1?V.fg:V.fgMuted,cursor:"pointer"}}>{n.name}</span>
                </span>
              ))}
            </div>
          )}
          <div style={{flex:1}}/>
          <div style={{display:"flex",alignItems:"center",gap:14,fontSize:9.5,fontFamily:F.mono,fontFeatureSettings:'"tnum"'}}>
            <ProtocolBar/>
            <span style={{color:V.fgDim}}><span style={{color:V.accent}}>${totalCost.toFixed(2)}</span>/$5</span>
            <span style={{color:V.fgDim}}>VRAM <span style={{color:V.purple}}>{totalVram.toFixed(1)}</span>/32</span>
          </div>
          {approvals.length>0&&(
            <div onClick={()=>navTab("queen")} style={{padding:"2px 8px",borderRadius:999,cursor:"pointer",
              background:V.accentMuted,fontSize:9.5,fontFamily:F.mono,color:V.accent,display:"flex",alignItems:"center",gap:4,
              border:`1px solid ${V.accent}18`,boxShadow:`0 0 14px ${V.accentGlow}`}}>
              <span style={{width:4,height:4,borderRadius:"50%",background:V.accent,animation:"pulse 1.5s infinite"}}/>
              {approvals.length}
            </div>
          )}
        </div>

        {/* BODY */}
        <div style={{flex:1,display:"flex",overflow:"hidden"}}>
          {/* SIDEBAR */}
          <div onMouseEnter={()=>setSideOpen(true)} onMouseLeave={()=>setSideOpen(false)}
            style={{width:showFull?195:46,borderRight:`1px solid ${V.border}`,display:"flex",flexDirection:"column",
              flexShrink:0,background:`${V.surface}88`,backdropFilter:"blur(10px)",WebkitBackdropFilter:"blur(10px)",
              transition:"width 0.22s cubic-bezier(0.22,1,0.36,1)",overflow:"hidden"}}>
            <div style={{display:"flex",flexDirection:showFull?"row":"column",borderBottom:`1px solid ${V.border}`,padding:showFull?"3px 4px":"4px 3px",gap:1}}>
              {NAV.map(n=>{
                const act=view===n.id||(view==="tree"&&n.id==="queen");
                return(
                  <div key={n.id} onClick={()=>navTab(n.id)} title={n.label}
                    style={{flex:showFull?1:"none",height:showFull?30:32,display:"flex",alignItems:"center",
                      justifyContent:"center",gap:4,borderRadius:6,cursor:"pointer",fontSize:12,
                      background:act?`${V.accent}0C`:"transparent",color:act?V.accent:V.fgDim,transition:"all 0.15s"}}>
                    <span style={{filter:act?`drop-shadow(0 0 3px ${V.accent}40)`:"none",fontSize:12}}>{n.icon}</span>
                    {showFull&&<span style={{fontSize:10,fontWeight:500}}>{n.label}</span>}
                  </div>
                );
              })}
            </div>
            <div style={{opacity:showFull?1:0,transition:"opacity 0.18s",pointerEvents:showFull?"auto":"none",flex:1,overflow:"hidden",display:"flex",flexDirection:"column"}}>
              <div style={{padding:"5px 10px",borderBottom:`1px solid ${V.border}`,fontSize:7.5,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.14em",textTransform:"uppercase",fontWeight:600}}>Navigator</div>
              <div style={{flex:1,overflow:"auto",paddingTop:1}}>
                <TreeNav selected={treeSel} onSelect={navTree} expanded={treeExp} onToggle={id=>setTreeExp(p=>({...p,[id]:p[id]===false}))}/>
              </div>
            </div>
            {!showFull&&(
              <div style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center",paddingTop:10,gap:5}}>
                {allColonies(TREE).filter(c=>c.status==="running").map(c=>(
                  <div key={c.id} onClick={()=>navTree(c.id)} title={c.name}
                    style={{width:26,height:26,borderRadius:6,display:"flex",alignItems:"center",justifyContent:"center",
                      background:treeSel===c.id?`${V.accent}0C`:"transparent",cursor:"pointer",
                      border:`1px solid ${treeSel===c.id?V.accent+"25":V.border}`,fontSize:9,color:V.fgMuted}}>⬡</div>
                ))}
              </div>
            )}
          </div>

          {/* CONTENT */}
          <div style={{flex:1,padding:16,overflow:"hidden",display:"flex",flexDirection:"column"}}>
            <div style={{flex:1,overflow:"hidden"}}>
              {view==="queen"&&<ViewQueen approvals={approvals} onApprove={id=>setApprovals(a=>a.filter(x=>x.id!==id))}
                onReject={id=>setApprovals(a=>a.filter(x=>x.id!==id))} onNav={navTree}
                queenThreads={QUEEN_THREADS} activeQT={activeQT} onSwitchQT={setActiveQT} onNewQT={newQT}/>}
              {view==="tree"&&selNode?.type==="colony"&&<ViewColony colony={selNode}
                queenThreads={QUEEN_THREADS} activeQT={activeQT} onSwitchQT={setActiveQT} onNewQT={newQT}/>}
              {view==="tree"&&selNode?.type==="workspace"&&<ViewWorkspace ws={selNode} onNav={navTree}/>}
              {view==="tree"&&selNode?.type==="thread"&&<ViewThread thread={selNode} parentWs={parentWs}
                merges={merges} onNav={navTree} onMerge={handleMerge} onPrune={handlePrune} onBroadcast={handleBroadcast}/>}
              {view==="models"&&<ViewModels/>}
              {view==="castes"&&<ViewCastes/>}
              {view==="settings"&&<ViewSettings/>}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
