import { useState, useEffect, useRef, useCallback, useMemo } from "react";

/*
 * ═══════════════════════════════════════════════════════════
 * FORMICOS v2.1.0 — FULL UI PROTOTYPE / VISUAL SPEC
 * All 16+ components. Luminous Void design system.
 * Single JSX — self-contained with mock data.
 * ═══════════════════════════════════════════════════════════
 *
 * NEW IN v2.1:
 *  - Skill Browser with confidence bars, sort, filter, merge badges
 *  - Template Browser with use counts, tags, quick-launch
 *  - Colony Creator multi-step modal (Describe → Configure → Launch)
 *  - Gemini as third cloud provider
 *  - Colony display names + Queen naming
 *  - Quality scoring on completed colonies
 *  - Convergence sparklines
 *  - Richer round data with tool calls + output summaries
 *  - Approval queue as dedicated surface
 * ═══════════════════════════════════════════════════════════
 */

// ── LUMINOUS VOID DESIGN TOKENS ───────────────────────────
const V = {
  void: "#08080F", surface: "#10111A", elevated: "#1A1B26", recessed: "#050508",
  border: "rgba(255,255,255,0.06)", borderHover: "rgba(255,255,255,0.14)",
  borderAccent: "rgba(232,88,26,0.22)",
  fg: "#EDEDF0", fgMuted: "#6B6B76", fgDim: "#45454F", fgOnAccent: "#0A0A0F",
  accent: "#E8581A", accentBright: "#F4763A", accentDeep: "#B8440F",
  accentMuted: "rgba(232,88,26,0.08)", accentGlow: "rgba(232,88,26,0.16)",
  secondary: "#3DD6F5", secondaryMuted: "rgba(61,214,245,0.07)",
  secondaryGlow: "rgba(61,214,245,0.12)",
  success: "#2DD4A8", warn: "#F5B731", danger: "#F06464",
  purple: "#A78BFA", blue: "#5B9CF5",
  glass: "rgba(16,17,26,0.60)", glassHover: "rgba(26,27,38,0.78)",
  pheromoneWeak: "rgba(232,88,26,0.04)", pheromoneMid: "rgba(232,88,26,0.12)",
  pheromoneStrong: "rgba(232,88,26,0.25)",
};
const F = {
  display: "'Satoshi','General Sans','DM Sans',system-ui,sans-serif",
  body: "'Geist','DM Sans','Plus Jakarta Sans',system-ui,sans-serif",
  mono: "'IBM Plex Mono','JetBrains Mono',monospace",
};

// Provider colors: green=local, amber=anthropic, blue=gemini
const PROVIDER_COLOR = { "llama-cpp": V.success, "anthropic": V.accent, "gemini": V.blue, "local": V.fgDim };
const providerOf = (model) => {
  if (!model) return "local";
  if (model.startsWith("anthropic/")) return "anthropic";
  if (model.startsWith("gemini/")) return "gemini";
  return "llama-cpp";
};

// ── MOCK DATA (aligned with contracts/types.ts) ──────────
const TREE = [
  { id:"ws-auth", name:"refactor-auth", type:"workspace",
    config:{ coder_model:"anthropic/claude-sonnet-4.6", reviewer_model:null, researcher_model:null, archivist_model:null, budget:5.0, strategy:"stigmergic" },
    children:[
      { id:"th-main", name:"main", type:"thread", children:[
        { id:"col-a1b2", displayName:"Auth Refactor Sprint", type:"colony", status:"running", round:4, maxRounds:10,
          task:"Refactor JWT refresh handler — proper token rotation, session invalidation, PKCE flow",
          strategy:"stigmergic", templateId: null,
          agents:[
            { name:"Coder-α", caste:"coder", model:"anthropic/claude-sonnet-4.6", tokens:18420, status:"active", pheromone:0.82 },
            { name:"Reviewer-β", caste:"reviewer", model:"llama-cpp/qwen3-30b", tokens:6820, status:"pending", pheromone:0.61 },
            { name:"Archivist-γ", caste:"archivist", model:"gemini/gemini-2.5-flash", tokens:4420, status:"done", pheromone:0.44 },
          ],
          convergence:0.72, convergenceHistory:[0.21, 0.48, 0.65, 0.72], cost:0.38, budget: 2.0,
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
            {r:1,phase:"Goal",convergence:0.21,cost:0.04,duration:3200,agents:[
              {n:"Coder-α",m:"llama-cpp/qwen3-30b",t:2840,s:"done",output:"Analyzed JWT refresh flow. Identified 3 token rotation bugs in auth_handler.rs.",tools:["memory_search"]},
              {n:"Reviewer-β",m:"llama-cpp/qwen3-30b",t:1920,s:"done",output:"Confirmed vulnerabilities match CVE-2024-3891. Priority: high.",tools:["memory_search"]},
              {n:"Archivist-γ",m:"gemini/gemini-2.5-flash",t:1200,s:"done",output:"Compressed R1 findings. 2 candidate skills identified.",tools:["memory_write"]},
            ]},
            {r:2,phase:"Execute",convergence:0.48,cost:0.12,duration:8400,agents:[
              {n:"Coder-α",m:"anthropic/claude-sonnet-4.6",t:8420,s:"done",output:"Implemented token rotation with PKCE binding. 4 files modified, 2 new tests.",tools:["code_write","test_run"]},
              {n:"Reviewer-β",m:"llama-cpp/qwen3-30b",t:3100,s:"done",output:"Review passed with 2 minor suggestions. No blocking issues.",tools:["code_read"]},
              {n:"Archivist-γ",m:"gemini/gemini-2.5-flash",t:1800,s:"done",output:"Extracted skill: JWT rotation pattern with DPoP binding.",tools:["memory_write","skill_extract"]},
            ]},
            {r:3,phase:"Execute",convergence:0.65,cost:0.14,duration:7200,agents:[
              {n:"Coder-α",m:"anthropic/claude-sonnet-4.6",t:6200,s:"done",output:"Session invalidation logic complete. Added Redis TTL integration.",tools:["code_write","memory_search"]},
              {n:"Reviewer-β",m:"llama-cpp/qwen3-30b",t:2800,s:"done",output:"Approved session invalidation. Flagged edge case in concurrent refresh.",tools:["code_read"]},
              {n:"Archivist-γ",m:"gemini/gemini-2.5-flash",t:1400,s:"done",output:"Updated skill confidence for JWT patterns. Compressed R3.",tools:["memory_write"]},
            ]},
            {r:4,phase:"Route",convergence:0.72,cost:0.08,duration:null,agents:[
              {n:"Coder-α",m:"anthropic/claude-sonnet-4.6",t:3200,s:"active",output:"Working on concurrent refresh edge case...",tools:[]},
              {n:"Reviewer-β",m:"llama-cpp/qwen3-30b",t:0,s:"pending",output:null,tools:[]},
              {n:"Archivist-γ",m:"gemini/gemini-2.5-flash",t:0,s:"pending",output:null,tools:[]},
            ]},
          ],
        },
        { id:"col-c3d4", displayName:"Dependency Analysis", type:"colony", status:"completed", round:5, maxRounds:5,
          task:"Initial auth module analysis — dependency mapping, vulnerability scan",
          strategy:"stigmergic", templateId:null,
          agents:[{name:"Coder-α",caste:"coder",model:"llama-cpp/qwen3-30b",tokens:28400,status:"done",pheromone:0.95},
                  {name:"Reviewer-β",caste:"reviewer",model:"llama-cpp/qwen3-30b",tokens:12800,status:"done",pheromone:0.88}],
          convergence:0.95, convergenceHistory:[0.30,0.52,0.71,0.88,0.95], cost:0.62, budget:1.0,
          quality:0.81, skillsExtracted:3,
          pheromones:[], topology:null, defense:null, rounds:[] },
      ]},
      { id:"th-exp", name:"experiment", type:"thread", children:[
        { id:"col-e5f6", displayName:"OAuth2 PKCE Spike", type:"colony", status:"queued", round:0, maxRounds:6,
          task:"Test alternative OAuth2 PKCE flow with DPoP binding",
          strategy:"sequential", templateId:null,
          agents:[{name:"Researcher-α",caste:"researcher",model:"gemini/gemini-2.5-flash",tokens:0,status:"pending",pheromone:0}],
          convergence:0, convergenceHistory:[], cost:0, budget:1.0, pheromones:[], topology:null, defense:null, rounds:[] },
      ]},
    ]},
  { id:"ws-research", name:"research-ttt", type:"workspace",
    config:{ coder_model:null, reviewer_model:null, researcher_model:"anthropic/claude-sonnet-4.6", archivist_model:null, budget:2.0, strategy:"stigmergic" },
    children:[
      { id:"th-main2", name:"main", type:"thread", children:[
        { id:"col-g7h8", displayName:"TTT Memory Survey", type:"colony", status:"running", round:2, maxRounds:10,
          task:"Research test-time training for agent memory — TTT-E2E, ZipMap, and hybrid retrieval",
          strategy:"stigmergic", templateId:null,
          agents:[
            {name:"Researcher-α",caste:"researcher",model:"anthropic/claude-sonnet-4.6",tokens:4200,status:"active",pheromone:0.67},
            {name:"Coder-β",caste:"coder",model:"llama-cpp/qwen3-30b",tokens:2100,status:"done",pheromone:0.38},
          ],
          convergence:0.41, convergenceHistory:[0.18,0.41], cost:0.21, budget:2.0,
          pheromones:[{from:"researcher",to:"coder",w:1.2,trend:"up"}],
          topology:null, defense:{ composite:0.09, signals:[{name:"entropy",value:0.05,threshold:1.0},{name:"drift",value:0.12,threshold:0.7}] },
          rounds:[] },
      ]},
    ]},
];

const SYS_DEFAULTS = { coder:"llama-cpp/qwen3-30b", reviewer:"llama-cpp/qwen3-30b", researcher:"gemini/gemini-2.5-flash", archivist:"gemini/gemini-2.5-flash", queen:"anthropic/claude-sonnet-4.6" };
const CASTES = [
  { id:"queen", name:"Queen", icon:"♛", color:V.accent, desc:"Strategic coordinator — spawns colonies, manages fleet" },
  { id:"coder", name:"Coder", icon:"⟨/⟩", color:V.success, desc:"Implementation — writes and debugs code via tools" },
  { id:"reviewer", name:"Reviewer", icon:"⊘", color:V.purple, desc:"Quality gate — reviews outputs, runs verification, flags issues" },
  { id:"researcher", name:"Researcher", icon:"◎", color:V.blue, desc:"Information specialist — retrieves, synthesizes, cites findings" },
  { id:"archivist", name:"Archivist", icon:"⧫", color:V.warn, desc:"Memory curator — compresses rounds, extracts skills, distills" },
];
const LOCAL_MODELS = [
  { id:"qwen3-30b", name:"Qwen 3 30B-A3B", quant:"Q4_K_M", status:"loaded", vram:21.1, ctx:8192, maxCtx:32768, backend:"llama.cpp", gpu:"RTX 5090", slots:2, provider:"llama-cpp" },
  { id:"arctic-embed-s", name:"Arctic Embed S", quant:"F32", status:"loaded", vram:0.09, ctx:512, maxCtx:512, backend:"sentence-transformers (CPU)", gpu:"CPU", slots:0, provider:"local" },
];
const CLOUD_EPS = [
  { id:"anthropic", provider:"Anthropic", models:["claude-sonnet-4.6","claude-opus-4.6","claude-haiku-4.5"], status:"connected", spend:0.62, limit:10.0, color:V.accent },
  { id:"gemini", provider:"Gemini", models:["gemini-2.5-flash","gemini-2.5-flash-lite"], status:"connected", spend:0.04, limit:5.0, color:V.blue },
];
const INIT_MERGES = [{from:"col-c3d4",to:"col-a1b2",id:"merge-1",active:true}];
const QUEEN_THREADS = [
  { id:"qt-1", name:"auth refactor", wsId:"ws-auth", messages:[
    {role:"operator",text:"Start with the auth module. Prioritize JWT refresh flow.",ts:"14:30:22"},
    {role:"queen",text:"Spawning colony targeting JWT refresh handler. 3 known issues from colony-c3d4 — merging compressed output as context.",ts:"14:30:25"},
    {role:"event",text:"ColonySpawned · Auth Refactor Sprint · 3 agents · stigmergic",ts:"14:31:05",kind:"spawn"},
    {role:"event",text:"MergeCreated · Dependency Analysis → Auth Refactor Sprint",ts:"14:31:06",kind:"merge"},
    {role:"event",text:"RoundCompleted · R2 · convergence 0.48 · 1 skill extracted",ts:"14:33:45",kind:"metric"},
    {role:"event",text:"Pheromone update · coder→reviewer strengthened to 1.8 (was 1.2)",ts:"14:34:01",kind:"pheromone"},
    {role:"event",text:"ModelRouted · Coder R3 → anthropic/claude-sonnet-4.6 (budget=62%)",ts:"14:36:44",kind:"route"},
    {role:"queen",text:"R4 in progress. Coder working on concurrent refresh edge case flagged by Reviewer in R3. Convergence trending well at 0.72.",ts:"14:38:10"},
  ]},
  { id:"qt-2", name:"TTT research", wsId:"ws-research", messages:[
    {role:"operator",text:"Find recent papers on test-time training for agent memory.",ts:"15:10:00"},
    {role:"queen",text:"Spawning research colony. Researcher routes to Anthropic for synthesis, local for structured queries.",ts:"15:10:03"},
    {role:"event",text:"ColonySpawned · TTT Memory Survey · 2 agents · stigmergic",ts:"15:10:05",kind:"spawn"},
    {role:"event",text:"RoundCompleted · R1 · convergence 0.18",ts:"15:14:30",kind:"metric"},
  ]},
];
const APPROVALS_INIT = [
  { id:1, type:"Cloud Escalation", agent:"Coder-α", detail:"anthropic/claude-opus-4.6 · est. $0.42", colony:"col-a1b2", colonyName:"Auth Refactor Sprint" },
];
const PROTOCOLS = { mcp:{status:"active",tools:5}, agui:{status:"adapter",events:12}, a2a:{status:"discovery",card:true} };

// ── SKILLS MOCK DATA ──────────────────────────────────────
const SKILLS = [
  { id:"sk-001", text_preview:"JWT token rotation with PKCE binding requires DPoP proof generation before refresh, ensuring session continuity across rotations", confidence:0.83, conf_alpha:15, conf_beta:3, uncertainty:0.08, algorithm_version:"bayesian-beta-v2", extracted_at:"2025-03-12T14:35:00Z", source_colony:"Dependency Analysis", merged:false },
  { id:"sk-002", text_preview:"Redis TTL-based session invalidation: set key expiry to match refresh token lifetime, use MULTI/EXEC for atomic rotation", confidence:0.79, conf_alpha:12, conf_beta:4, uncertainty:0.10, algorithm_version:"bayesian-beta-v2", extracted_at:"2025-03-12T14:40:00Z", source_colony:"Auth Refactor Sprint", merged:false },
  { id:"sk-003", text_preview:"Concurrent refresh race condition mitigated by optimistic locking with CAS (compare-and-swap) on token version field", confidence:0.88, conf_alpha:18, conf_beta:2, uncertainty:0.06, algorithm_version:"bayesian-beta-v2", extracted_at:"2025-03-11T10:20:00Z", source_colony:"Dependency Analysis", merged:true },
  { id:"sk-004", text_preview:"Stigmergic coordination outperforms sequential for code review tasks when reviewer has access to coder's pheromone trail", confidence:0.56, conf_alpha:5, conf_beta:4, uncertainty:0.18, algorithm_version:"bayesian-beta-v2", extracted_at:"2025-03-10T09:15:00Z", source_colony:"Auth Refactor Sprint", merged:false },
  { id:"sk-005", text_preview:"Test-time training with ZipMap compression achieves 94% retention at 8x compression ratio for factual knowledge", confidence:0.52, conf_alpha:4, conf_beta:3, uncertainty:0.21, algorithm_version:"bayesian-beta-v2", extracted_at:"2025-03-12T15:20:00Z", source_colony:"TTT Memory Survey", merged:false },
  { id:"sk-006", text_preview:"Hybrid retrieval combining vector similarity with BFS graph traversal on TKG triples improves recall by 23% vs vector-only", confidence:0.61, conf_alpha:7, conf_beta:5, uncertainty:0.15, algorithm_version:"bayesian-beta-v2", extracted_at:"2025-03-12T15:25:00Z", source_colony:"TTT Memory Survey", merged:false },
  { id:"sk-007", text_preview:"PKCE code_verifier should use S256 challenge method; plain method deprecated and rejected by most providers since 2024", confidence:0.91, conf_alpha:20, conf_beta:2, uncertainty:0.05, algorithm_version:"bayesian-beta-v2", extracted_at:"2025-03-09T11:00:00Z", source_colony:"Dependency Analysis", merged:true },
  { id:"sk-008", text_preview:"Auth middleware should validate token signature before checking expiry to prevent timing attacks on expired tokens", confidence:0.50, conf_alpha:2, conf_beta:2, uncertainty:0.25, algorithm_version:"bayesian-beta-v2", extracted_at:"2025-03-12T14:50:00Z", source_colony:"Auth Refactor Sprint", merged:false },
  { id:"sk-009", text_preview:"Agent pheromone decay rate of 0.85 per round balances exploration vs exploitation for 3-5 agent colonies", confidence:0.48, conf_alpha:3, conf_beta:3, uncertainty:0.22, algorithm_version:"bayesian-beta-v1", extracted_at:"2025-03-08T16:00:00Z", source_colony:"TTT Memory Survey", merged:false },
  { id:"sk-010", text_preview:"Local model routing for Goal/Compress phases saves 60-80% cost with <5% quality loss vs cloud for structured tasks", confidence:0.74, conf_alpha:10, conf_beta:3, uncertainty:0.11, algorithm_version:"bayesian-beta-v2", extracted_at:"2025-03-11T13:30:00Z", source_colony:"Dependency Analysis", merged:false },
];

// ── TEMPLATES MOCK DATA ───────────────────────────────────
const TEMPLATES = [
  { template_id:"tpl-001", name:"Code Review", description:"Fast code review with coder+reviewer pair", caste_names:["coder","reviewer"], strategy:"stigmergic", budget_limit:1.0, max_rounds:8, tags:["code","review"], use_count:12, source_colony_id:"col-c3d4", version:2 },
  { template_id:"tpl-002", name:"Research Sprint", description:"Deep research with synthesis and archival", caste_names:["researcher","archivist"], strategy:"stigmergic", budget_limit:2.0, max_rounds:15, tags:["research"], use_count:5, source_colony_id:"col-g7h8", version:1 },
  { template_id:"tpl-003", name:"Full Stack", description:"Complete team for complex implementation tasks", caste_names:["coder","reviewer","researcher","archivist"], strategy:"stigmergic", budget_limit:3.0, max_rounds:25, tags:["code","research","full"], use_count:3, source_colony_id:null, version:1 },
];

// ── HELPERS ──────────────────────────────────────────────
function findNode(n,id){for(const x of n){if(x.id===id)return x;if(x.children){const f=findNode(x.children,id);if(f)return f;}}return null;}
function allColonies(n){let o=[];for(const x of n){if(x.type==="colony")o.push(x);if(x.children)o=o.concat(allColonies(x.children));}return null? []:o;}
function bc(n,id,p=[]){for(const x of n){const c=[...p,x];if(x.id===id)return c;if(x.children){const f=bc(x.children,id,c);if(f)return f;}}return null;}
function timeAgo(iso){const d=Date.now()-new Date(iso).getTime();const h=Math.floor(d/3600000);if(h<1)return"just now";if(h<24)return`${h}h ago`;return`${Math.floor(h/24)}d ago`;}
function colonyName(c){return c.displayName||c.id;}

// ── ATOMS ────────────────────────────────────────────────
const Pill = ({children,color=V.fgMuted,glow,sm,onClick})=>(
  <span onClick={onClick} style={{display:"inline-flex",alignItems:"center",gap:3,
    padding:sm?"1px 7px":"2px 10px",borderRadius:999,
    fontSize:sm?8.5:9.5,fontFamily:F.mono,letterSpacing:"0.05em",fontWeight:500,color,
    background:`${color}12`,border:`1px solid ${color}18`,
    boxShadow:glow?`0 0 14px ${color}18`:"none",cursor:onClick?"pointer":"default"}}>{children}</span>
);
const Dot = ({status,size=6})=>{
  const c={running:V.success,completed:V.secondary,queued:V.warn,loaded:V.success,connected:V.success,
    "no key":V.danger,active:V.success,pending:V.warn,done:V.secondary,failed:V.danger,killed:V.danger}[status]||V.fgDim;
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
        :h&&hover?"0 8px 32px rgba(5,5,8,0.6)":"0 1px 2px rgba(5,5,8,0.3)",...sx}}>{children}</div>;
};
const SLabel=({children,sx})=>(
  <div style={{fontSize:8,fontFamily:F.mono,fontWeight:600,color:V.fgDim,letterSpacing:"0.14em",
    textTransform:"uppercase",marginBottom:7,...sx}}>{children}</div>
);
const GradientText=({children,style:sx})=>(
  <span style={{background:`linear-gradient(135deg,${V.accentBright},${V.accent},${V.secondary})`,
    WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent",backgroundClip:"text",...sx}}>{children}</span>
);

// Convergence sparkline
const Sparkline = ({data,w=60,h=16,color=V.accent}) => {
  if(!data||data.length<2) return null;
  const max=Math.max(...data,1);const min=Math.min(...data,0);
  const range=max-min||1;
  const pts=data.map((v,i)=>`${(i/(data.length-1))*w},${h-(((v-min)/range)*h)}`).join(" ");
  return <svg width={w} height={h} style={{display:"inline-block",verticalAlign:"middle"}}><polyline points={pts} fill="none" stroke={color} strokeWidth={1.2} strokeLinejoin="round" opacity={0.7}/></svg>;
};

// Pheromone bar
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

// Defense gauge
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

// Quality dot for completed colonies
const QualityDot = ({quality,size=6}) => {
  if(quality==null) return null;
  const c = quality>=0.8?V.success:quality>=0.5?V.warn:V.danger;
  return <span title={`Quality: ${(quality*100).toFixed(0)}%`} style={{display:"inline-block",width:size,height:size,borderRadius:"50%",background:c,flexShrink:0,opacity:0.8}}/>;
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
          <span style={{color:sel?V.fg:V.fgMuted,overflow:"hidden",textOverflow:"ellipsis",flex:1,fontSize:10.5}}>{colonyName(node)}</span>
          {node.status&&<Dot status={node.status} size={4}/>}
          {node.quality!=null&&<QualityDot quality={node.quality} size={4}/>}
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
        const strong = e.w > 1.2;const isHov = hov===e.from||hov===e.to;
        return <g key={`trail-${i}`}>
          {strong&&<line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={V.accent} strokeWidth={e.w*2} opacity={0.06} filter="url(#edgeGlow)"/>}
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
const QueenChat=({style:sx,threads,activeThreadId,onSwitchThread})=>{
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

// ── PROTOCOL BAR ────────────────────────────────────────
const ProtocolBar=()=>(
  <div style={{display:"flex",gap:8,alignItems:"center"}}>
    {[
      {label:"MCP",status:PROTOCOLS.mcp.status,detail:`${PROTOCOLS.mcp.tools} tools`},
      {label:"AG-UI",status:PROTOCOLS.agui.status,detail:`${PROTOCOLS.agui.events} events`},
      {label:"A2A",status:PROTOCOLS.a2a.status,detail:"card"},
    ].map(p=>(
      <div key={p.label} style={{display:"flex",alignItems:"center",gap:3,padding:"2px 6px",
        borderRadius:999,border:`1px solid ${V.border}`,background:V.recessed}}>
        <Dot status={p.status==="active"?"loaded":p.status==="adapter"?"pending":"done"} size={3}/>
        <span style={{fontFamily:F.mono,fontSize:7.5,fontWeight:600,letterSpacing:"0.06em",color:V.fgDim}}>{p.label}</span>
      </div>
    ))}
  </div>
);

// ═══════════════════════════════════════════════════════════
// VIEWS
// ═══════════════════════════════════════════════════════════

// ── QUEEN OVERVIEW ──────────────────────────────────────
const ViewQueen=({approvals,onApprove,onReject,onNav,queenThreads,activeQT,onSwitchQT,onCreateColony})=>{
  const cols=allColonies(TREE);
  const running=cols.filter(c=>c.status==="running");
  const totalCost=cols.reduce((a,c)=>a+(c.cost||0),0);
  const totalTok=cols.reduce((a,c)=>a+(c.agents||[]).reduce((b,ag)=>b+ag.tokens,0),0);
  const totalVram=LOCAL_MODELS.filter(m=>m.status==="loaded").reduce((a,m)=>a+m.vram,0);
  const avgConf=SKILLS.length>0?SKILLS.reduce((a,s)=>a+s.confidence,0)/SKILLS.length:0;

  return(
    <div style={{display:"flex",gap:16,height:"100%",overflow:"hidden"}}>
      <div style={{flex:1,overflow:"auto",paddingRight:4}}>
        {/* Header */}
        <div style={{marginBottom:20}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:5}}>
            <span style={{fontSize:22,filter:`drop-shadow(0 0 8px ${V.accentGlow})`}}>♛</span>
            <h1 style={{fontFamily:F.display,fontSize:22,fontWeight:700,color:V.fg,letterSpacing:"-0.04em",margin:0}}>
              <GradientText>Supercolony</GradientText>
            </h1>
            <Pill color={V.success} glow><Dot status="running" size={4}/> {running.length} active</Pill>
            <div style={{marginLeft:"auto"}}><ProtocolBar/></div>
          </div>
          <p style={{fontSize:11,color:V.fgMuted,margin:0}}>
            {cols.length} colonies · <span style={{fontFamily:F.mono,fontFeatureSettings:'"tnum"'}}>{(totalTok/1000).toFixed(0)}k</span> tokens · <span style={{fontFamily:F.mono,color:V.accent}}>${totalCost.toFixed(2)}</span> · <span style={{fontFamily:F.mono,color:V.secondary}}>{SKILLS.length} skills</span> (avg conf {(avgConf*100).toFixed(0)}%)
          </p>
        </div>

        {/* Resource strip */}
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:8,marginBottom:18}}>
          <Glass style={{padding:10}}><Meter label="Budget" value={totalCost} max={7} unit="$" compact/></Glass>
          <Glass style={{padding:10}}><Meter label="VRAM" value={totalVram} max={32} unit=" GB" color={V.purple} compact/></Glass>
          <Glass style={{padding:10}}><Meter label="Anthropic" value={0.62} max={10} unit="$" color={V.accent} compact/></Glass>
          <Glass style={{padding:10}}><Meter label="Gemini" value={0.04} max={5} unit="$" color={V.blue} compact/></Glass>
        </div>

        {/* Approvals */}
        {approvals.length>0&&(
          <div style={{marginBottom:18}}>
            <SLabel>Pending Approvals</SLabel>
            {approvals.map(a=>(
              <Glass key={a.id} featured style={{padding:12,marginBottom:6,display:"flex",alignItems:"center",gap:10}}>
                <div style={{width:3,height:28,borderRadius:2,background:V.accent,flexShrink:0}}/>
                <div style={{flex:1}}>
                  <div style={{fontSize:9,fontFamily:F.mono,color:V.accent,fontWeight:600,letterSpacing:"0.08em",textTransform:"uppercase",marginBottom:1}}>{a.type}</div>
                  <div style={{fontSize:11.5,color:V.fg}}>{a.agent} → {a.detail}</div>
                  <div style={{fontSize:9,color:V.fgDim}}>{a.colonyName}</div>
                </div>
                <Btn v="success" sm onClick={()=>onApprove(a.id)}>Approve</Btn>
                <Btn v="danger" sm onClick={()=>onReject(a.id)}>Deny</Btn>
              </Glass>
            ))}
          </div>
        )}

        {/* Template Quick-Launch */}
        <div style={{marginBottom:18}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
            <SLabel sx={{marginBottom:0}}>Quick Launch</SLabel>
            <Btn v="primary" sm onClick={onCreateColony}>+ New Colony</Btn>
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:8}}>
            {TEMPLATES.map(t=>(
              <Glass key={t.template_id} hover onClick={onCreateColony} style={{padding:10}}>
                <div style={{display:"flex",alignItems:"center",gap:4,marginBottom:4}}>
                  <span style={{fontFamily:F.display,fontSize:11.5,fontWeight:600,color:V.fg}}>{t.name}</span>
                  <span style={{fontFamily:F.mono,fontSize:8,color:V.fgDim,marginLeft:"auto"}}>{t.use_count}×</span>
                </div>
                <div style={{display:"flex",gap:3,marginBottom:4}}>
                  {t.caste_names.map(cn=>{const c=CASTES.find(x=>x.id===cn);return c?<span key={cn} style={{fontSize:10,filter:`drop-shadow(0 0 2px ${c.color}30)`}} title={c.name}>{c.icon}</span>:null;})}
                </div>
                <div style={{display:"flex",gap:3}}>
                  {t.tags.map(tag=><Pill key={tag} color={V.fgDim} sm>{tag}</Pill>)}
                </div>
              </Glass>
            ))}
          </div>
        </div>

        {/* Colonies by workspace */}
        {TREE.map(ws=>(
          <div key={ws.id} style={{marginBottom:18}}>
            <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:8}}>
              <SLabel sx={{marginBottom:0}}><span style={{color:V.accent}}>▣</span> {ws.name}</SLabel>
              <Pill color={V.fgDim} sm>{ws.config.strategy}</Pill>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
              {allColonies([ws]).map(c=>(
                <Glass key={c.id} hover onClick={()=>onNav(c.id)} style={{padding:12}}>
                  <div style={{display:"flex",alignItems:"center",gap:5,marginBottom:3}}>
                    <Dot status={c.status} size={5}/>
                    <span style={{fontFamily:F.display,fontSize:12,fontWeight:600,color:V.fg}}>{colonyName(c)}</span>
                    {c.quality!=null&&<QualityDot quality={c.quality}/>}
                  </div>
                  <div style={{fontSize:9,fontFamily:F.mono,color:V.fgDim,marginBottom:2}}>{c.id}</div>
                  {c.task&&<div style={{fontSize:10,color:V.fgMuted,marginBottom:5,lineHeight:1.35,
                    overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{c.task}</div>}
                  <div style={{display:"flex",gap:6,fontSize:9.5,fontFamily:F.mono,color:V.fgMuted,fontFeatureSettings:'"tnum"',alignItems:"center",flexWrap:"wrap"}}>
                    <span>R{c.round}/{c.maxRounds}</span>
                    <span>{(c.agents||[]).length} agents</span>
                    {c.convergence>0&&<><span style={{color:c.convergence>0.8?V.success:V.fgMuted}}>conv {(c.convergence*100).toFixed(0)}%</span><Sparkline data={c.convergenceHistory} color={c.convergence>0.8?V.success:V.accent}/></>}
                    <span style={{color:V.accent}}>${(c.cost||0).toFixed(2)}</span>
                    {c.skillsExtracted>0&&<Pill color={V.secondary} sm>{c.skillsExtracted} skills</Pill>}
                    {/* Provider mix dots */}
                    <span style={{display:"flex",gap:2,marginLeft:"auto"}}>
                      {[...new Set((c.agents||[]).map(a=>providerOf(a.model)))].map(p=>(
                        <span key={p} style={{width:5,height:5,borderRadius:"50%",background:PROVIDER_COLOR[p]||V.fgDim}}/>
                      ))}
                    </span>
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
      <QueenChat style={{width:310,flexShrink:0}} threads={queenThreads} activeThreadId={activeQT} onSwitchThread={onSwitchQT}/>
    </div>
  );
};

// ── COLONY DETAIL ──────────────────────────────────────
const ViewColony=({colony,queenThreads,activeQT,onSwitchQT})=>{
  if(!colony) return null;
  const [expandedRound,setExpandedRound]=useState(null);
  const totalTokens=(colony.agents||[]).reduce((a,ag)=>a+ag.tokens,0);
  return(
    <div style={{display:"flex",gap:16,height:"100%",overflow:"hidden"}}>
      <div style={{flex:1,overflow:"auto",paddingRight:4}}>
        {/* Header */}
        <div style={{marginBottom:5}}>
          <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:3}}>
            <span style={{fontFamily:F.display,fontSize:18,fontWeight:700,color:V.fg,letterSpacing:"-0.03em"}}>⬡ {colonyName(colony)}</span>
            <Pill color={colony.status==="running"?V.success:colony.status==="completed"?V.secondary:V.warn} glow>
              <Dot status={colony.status} size={4}/> {colony.status}
            </Pill>
            <Pill color={V.fgDim} sm>{colony.strategy||"stigmergic"}</Pill>
            {colony.templateId&&<Pill color={V.secondary} sm>from template</Pill>}
            {colony.quality!=null&&<Pill color={colony.quality>=0.8?V.success:colony.quality>=0.5?V.warn:V.danger} sm>quality {(colony.quality*100).toFixed(0)}%</Pill>}
          </div>
          <div style={{fontSize:9,fontFamily:F.mono,color:V.fgDim,marginBottom:4}}>{colony.id}</div>
          {colony.task&&<p style={{fontSize:11,color:V.fgMuted,margin:0,marginBottom:12,lineHeight:1.4}}>{colony.task}</p>}
        </div>

        {/* Metrics + Topology */}
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
              <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:6}}>
                <Meter label="Convergence" value={colony.convergence} max={1} color={colony.convergence>0.8?V.success:V.accent} compact/>
              </div>
              {colony.convergenceHistory?.length>1&&(
                <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:6}}>
                  <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>trend</span>
                  <Sparkline data={colony.convergenceHistory} w={80} h={20} color={colony.convergence>0.8?V.success:V.accent}/>
                </div>
              )}
              <Meter label="Cost" value={colony.cost} max={colony.budget||5} unit="$" compact/>
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

        {/* Agents Table */}
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
                <td style={{padding:"6px 8px"}}><span style={{fontSize:10,filter:`drop-shadow(0 0 2px ${CASTES.find(c=>c.id===a.caste)?.color}30)`}}>{CASTES.find(c=>c.id===a.caste)?.icon}</span></td>
                <td style={{padding:"6px 8px",color:V.fgMuted,fontSize:9.5}}>
                  <span style={{display:"inline-flex",alignItems:"center",gap:3}}>
                    <span style={{width:5,height:5,borderRadius:"50%",background:PROVIDER_COLOR[providerOf(a.model)]||V.fgDim}}/>
                    {a.model}
                  </span>
                </td>
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

        {/* Action buttons */}
        <div style={{display:"flex",gap:6,marginBottom:16}}>
          <Btn v="secondary" sm>Intervene</Btn>
          <Btn v="secondary" sm>Extend Rounds</Btn>
          <Btn v="secondary" sm>Save as Template</Btn>
          <Btn v="danger" sm>Kill Colony</Btn>
        </div>

        {/* Round History */}
        {colony.rounds?.length>0&&(<>
          <SLabel>Round History</SLabel>
          <Glass style={{padding:12}}>
            {colony.rounds.map((r,ri)=>{
              const pc=r.phase==="Goal"?V.accent:r.phase==="Route"?V.warn:V.blue;
              const isExpanded=expandedRound===ri;
              return(
                <div key={ri} style={{paddingLeft:10,borderLeft:`2px solid ${pc}`,marginBottom:ri<colony.rounds.length-1?10:0}}>
                  <div onClick={()=>setExpandedRound(isExpanded?null:ri)} style={{display:"flex",alignItems:"center",gap:5,marginBottom:3,cursor:"pointer"}}>
                    <span style={{fontFamily:F.display,fontSize:11,fontWeight:700,color:pc}}>R{r.r}</span>
                    <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.08em"}}>{r.phase}</span>
                    {r.convergence!=null&&<span style={{fontSize:8,fontFamily:F.mono,color:V.fgMuted}}>conv {(r.convergence*100).toFixed(0)}%</span>}
                    {r.cost!=null&&<span style={{fontSize:8,fontFamily:F.mono,color:V.accent}}>${r.cost.toFixed(2)}</span>}
                    {r.duration&&<span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>{(r.duration/1000).toFixed(1)}s</span>}
                    <span style={{fontSize:8,color:V.fgDim,marginLeft:"auto"}}>{isExpanded?"▲":"▼"}</span>
                  </div>
                  {isExpanded&&r.agents.map((a,ai)=>(
                    <div key={ai} style={{padding:"4px 0 4px 6px",marginBottom:2,borderBottom:ai<r.agents.length-1?`1px solid ${V.border}`:"none"}}>
                      <div style={{display:"flex",alignItems:"center",gap:5,fontSize:9.5}}>
                        <Dot status={a.s} size={4}/>
                        <span style={{color:V.fg,width:70,fontWeight:500}}>{a.n}</span>
                        <span style={{display:"inline-flex",alignItems:"center",gap:2,color:V.fgDim,fontSize:9}}>
                          <span style={{width:4,height:4,borderRadius:"50%",background:PROVIDER_COLOR[providerOf(a.m)]||V.fgDim}}/>
                          {a.m}
                        </span>
                        {a.t>0&&<span style={{color:V.fgDim,fontSize:9,marginLeft:"auto",fontFeatureSettings:'"tnum"'}}>{(a.t/1000).toFixed(1)}k</span>}
                      </div>
                      {a.output&&<div style={{fontSize:9.5,color:V.fgMuted,lineHeight:1.4,marginTop:3,paddingLeft:16}}>{a.output}</div>}
                      {a.tools?.length>0&&<div style={{display:"flex",gap:3,marginTop:3,paddingLeft:16}}>
                        {a.tools.map(t=><Pill key={t} color={V.purple} sm>{t}</Pill>)}
                      </div>}
                    </div>
                  ))}
                  {!isExpanded&&r.agents.map((a,ai)=>(
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
      <QueenChat style={{width:280,flexShrink:0}} threads={queenThreads} activeThreadId={activeQT} onSwitchThread={onSwitchQT}/>
    </div>
  );
};

// ── THREAD VIEW ─────────────────────────────────────────
const ViewThread=({thread,parentWs,merges,onNav,onMerge,onPrune,onBroadcast,onCreateColony})=>{
  if(!thread) return null;
  const cols = thread.children||[];
  const [mergeMode,setMergeMode]=useState(null);
  const activeMerges = merges.filter(m=>m.active);
  return(
    <div style={{overflow:"auto",height:"100%"}}>
      <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:8}}>
        <span style={{fontSize:12,color:V.blue}}>▷</span>
        <h2 style={{fontFamily:F.display,fontSize:18,fontWeight:700,color:V.fg,margin:0}}>{thread.name}</h2>
        <Pill color={V.fgMuted} sm>{cols.length} colonies</Pill>
        {parentWs&&<Pill color={V.accent} sm>▣ {parentWs.name}</Pill>}
        <div style={{marginLeft:"auto",display:"flex",gap:5}}>
          <Btn v="primary" sm onClick={onCreateColony}>+ Spawn Colony</Btn>
          <Btn v="merge" sm onClick={()=>setMergeMode(mergeMode?null:"picking")}>{mergeMode?"Cancel":"⊕ Merge"}</Btn>
          <Btn v="secondary" sm onClick={onBroadcast}>⊗ Broadcast</Btn>
        </div>
      </div>
      {mergeMode&&<div style={{padding:"6px 12px",background:V.accentMuted,borderRadius:7,border:`1px solid ${V.accent}20`,marginBottom:10,
        fontSize:11,color:V.accent,fontFamily:F.body}}>
        {mergeMode==="picking"?"Click a SOURCE colony":"Click TARGET to merge from "+colonyName(findNode(TREE,mergeMode)||{id:mergeMode})}
      </div>}
      <div style={{position:"relative",paddingTop:8}}>
        {activeMerges.length>0&&(
          <svg style={{position:"absolute",top:0,left:0,width:"100%",height:"100%",pointerEvents:"none",zIndex:1}}>
            <defs><marker id="mergeArr" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="6" markerHeight="4" orient="auto"><path d="M0,0 L10,3 L0,6" fill={V.secondary}/></marker></defs>
            {activeMerges.map((m,i)=>{
              const fromIdx=cols.findIndex(c=>c.id===m.from);const toIdx=cols.findIndex(c=>c.id===m.to);
              if(fromIdx<0||toIdx<0) return null;
              const y1=fromIdx*90+45; const y2=toIdx*90+45;
              return <g key={m.id}>
                <path d={`M 20 ${y1} C -20 ${y1}, -20 ${y2}, 20 ${y2}`} stroke={V.secondary} strokeWidth={1.5} fill="none" opacity={0.5} markerEnd="url(#mergeArr)" strokeDasharray="4 2"/>
              </g>;
            })}
          </svg>
        )}
        <div style={{display:"flex",flexDirection:"column",gap:8,paddingLeft:30}}>
          {cols.map(c=>{
            const hasMergeTo = activeMerges.some(m=>m.to===c.id);
            const hasMergeFrom = activeMerges.some(m=>m.from===c.id);
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
                  <span style={{fontFamily:F.display,fontSize:13,fontWeight:600,color:V.fg}}>{colonyName(c)}</span>
                  {c.quality!=null&&<QualityDot quality={c.quality}/>}
                  <span style={{fontSize:9.5,fontFamily:F.mono,color:V.fgMuted,fontFeatureSettings:'"tnum"',marginLeft:"auto"}}>
                    R{c.round}/{c.maxRounds} · {(c.agents||[]).length} agents · ${(c.cost||0).toFixed(2)}
                  </span>
                  {hasMergeTo&&<Pill color={V.secondary} sm>← merge in</Pill>}
                  {hasMergeFrom&&<Pill color={V.secondary} sm>→ merge out</Pill>}
                </div>
                {c.task&&<div style={{fontSize:11,color:V.fgMuted,lineHeight:1.4,marginBottom:6}}>{c.task}</div>}
                <div style={{display:"flex",gap:8,alignItems:"center"}}>
                  {c.convergence>0&&<div style={{flex:1}}><Meter label="Convergence" value={c.convergence} max={1} color={c.convergence>0.8?V.success:V.accent} compact/></div>}
                  {c.defense&&<DefenseGauge score={c.defense.composite} compact/>}
                  <div style={{display:"flex",gap:3,marginLeft:"auto"}}>
                    {activeMerges.filter(m=>m.to===c.id).map(m=>(<Btn key={m.id} v="danger" sm onClick={e=>{e.stopPropagation();onPrune(m.id);}}>✕ Prune</Btn>))}
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

// ── SKILL BROWSER ───────────────────────────────────────
const ViewSkills=()=>{
  const [sort,setSort]=useState("confidence");
  const [minConf,setMinConf]=useState(0);
  const sorted=[...SKILLS].filter(s=>s.confidence>=minConf).sort((a,b)=>{
    if(sort==="confidence") return b.confidence-a.confidence;
    if(sort==="freshness") return new Date(b.extracted_at)-new Date(a.extracted_at);
    if(sort==="uncertainty") return b.uncertainty-a.uncertainty;
    return 0;
  });
  return(
    <div style={{overflow:"auto",height:"100%",maxWidth:900}}>
      <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:16}}>
        <h2 style={{fontFamily:F.display,fontSize:20,fontWeight:700,color:V.fg,margin:0}}>
          <GradientText>Skill Bank</GradientText>
        </h2>
        <Pill color={V.secondary} glow>{SKILLS.length} skills</Pill>
        <span style={{fontSize:10,fontFamily:F.mono,color:V.fgMuted}}>avg conf {(SKILLS.reduce((a,s)=>a+s.confidence,0)/SKILLS.length*100).toFixed(0)}%</span>
      </div>
      {/* Controls */}
      <div style={{display:"flex",gap:8,marginBottom:14,alignItems:"center"}}>
        <SLabel sx={{marginBottom:0}}>Sort</SLabel>
        {["confidence","freshness","uncertainty"].map(s=>(
          <Pill key={s} color={sort===s?V.accent:V.fgDim} onClick={()=>setSort(s)} sm>{s}</Pill>
        ))}
        <span style={{width:1,height:16,background:V.border,margin:"0 4px"}}/>
        <SLabel sx={{marginBottom:0}}>Min conf</SLabel>
        <input type="range" min={0} max={0.9} step={0.05} value={minConf} onChange={e=>setMinConf(parseFloat(e.target.value))}
          style={{width:80,accentColor:V.accent}}/>
        <span style={{fontFamily:F.mono,fontSize:9,color:V.fgMuted}}>{(minConf*100).toFixed(0)}%</span>
      </div>
      {/* Skills */}
      <div style={{display:"flex",flexDirection:"column",gap:6}}>
        {sorted.length===0&&(
          <Glass style={{padding:24,textAlign:"center"}}>
            <div style={{fontSize:12,color:V.fgMuted}}>No skills match the current filter.</div>
          </Glass>
        )}
        {sorted.map(s=>{
          const confColor=s.confidence>=0.8?V.success:s.confidence>=0.6?V.accent:V.warn;
          return(
            <Glass key={s.id} hover style={{padding:12}}>
              <div style={{display:"flex",gap:10,alignItems:"flex-start"}}>
                <div style={{flex:1}}>
                  <div style={{fontSize:11.5,color:V.fg,lineHeight:1.45,marginBottom:6}}>{s.text_preview}</div>
                  <div style={{display:"flex",gap:6,alignItems:"center",flexWrap:"wrap"}}>
                    <Pill color={V.fgDim} sm>{s.source_colony}</Pill>
                    <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>{timeAgo(s.extracted_at)}</span>
                    <Pill color={V.fgDim} sm>{s.algorithm_version}</Pill>
                    {s.merged&&<Pill color={V.secondary} sm>merged</Pill>}
                  </div>
                </div>
                <div style={{width:100,flexShrink:0,textAlign:"right"}}>
                  <div style={{fontFamily:F.mono,fontSize:16,fontWeight:600,color:confColor,fontFeatureSettings:'"tnum"',marginBottom:2}}>{(s.confidence*100).toFixed(0)}%</div>
                  <div style={{height:4,background:"rgba(255,255,255,0.04)",borderRadius:2,overflow:"hidden",marginBottom:4}}>
                    <div style={{height:"100%",width:`${s.confidence*100}%`,borderRadius:2,background:confColor,transition:"width 0.3s"}}/>
                  </div>
                  {/* Uncertainty bar - width indicates uncertainty */}
                  <div style={{display:"flex",alignItems:"center",gap:4,justifyContent:"flex-end"}}>
                    <span style={{fontSize:7,fontFamily:F.mono,color:V.fgDim}}>±{(s.uncertainty*100).toFixed(0)}%</span>
                    <div style={{width:30,height:3,background:"rgba(255,255,255,0.04)",borderRadius:2,overflow:"hidden"}}>
                      <div style={{height:"100%",width:`${s.uncertainty*100*2}%`,borderRadius:2,background:V.warn,opacity:0.5}}/>
                    </div>
                  </div>
                  <div style={{fontSize:7,fontFamily:F.mono,color:V.fgDim,marginTop:2}} title={`α=${s.conf_alpha} β=${s.conf_beta}`}>
                    α{s.conf_alpha} β{s.conf_beta}
                  </div>
                </div>
              </div>
            </Glass>
          );
        })}
      </div>
    </div>
  );
};

// ── TEMPLATE BROWSER ────────────────────────────────────
const ViewTemplates=({onCreateColony})=>(
  <div style={{overflow:"auto",height:"100%",maxWidth:860}}>
    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:16}}>
      <h2 style={{fontFamily:F.display,fontSize:20,fontWeight:700,color:V.fg,margin:0}}>
        <GradientText>Colony Templates</GradientText>
      </h2>
      <Pill color={V.fgDim}>{TEMPLATES.length}</Pill>
      <Btn v="primary" sm sx={{marginLeft:"auto"}} onClick={onCreateColony}>+ New Colony</Btn>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
      {TEMPLATES.map(t=>(
        <Glass key={t.template_id} hover onClick={onCreateColony} style={{padding:14}}>
          <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:6}}>
            <span style={{fontFamily:F.display,fontSize:14,fontWeight:600,color:V.fg}}>{t.name}</span>
            <Pill color={V.fgDim} sm>v{t.version}</Pill>
            <span style={{fontFamily:F.mono,fontSize:9,color:V.fgMuted,marginLeft:"auto"}}>{t.use_count} uses</span>
          </div>
          <div style={{fontSize:10.5,color:V.fgMuted,lineHeight:1.4,marginBottom:8}}>{t.description}</div>
          <div style={{display:"flex",gap:6,alignItems:"center",marginBottom:6}}>
            {t.caste_names.map(cn=>{const c=CASTES.find(x=>x.id===cn);return c?<div key={cn} style={{display:"flex",alignItems:"center",gap:3}}>
              <span style={{fontSize:11,filter:`drop-shadow(0 0 2px ${c.color}30)`}}>{c.icon}</span>
              <span style={{fontSize:9,color:V.fgMuted}}>{c.name}</span>
            </div>:null;})}
          </div>
          <div style={{display:"flex",gap:4,alignItems:"center"}}>
            {t.tags.map(tag=><Pill key={tag} color={V.fgDim} sm>{tag}</Pill>)}
            <span style={{marginLeft:"auto",fontFamily:F.mono,fontSize:9,color:V.fgMuted,fontFeatureSettings:'"tnum"'}}>
              ${t.budget_limit.toFixed(2)} · {t.max_rounds}R · {t.strategy}
            </span>
          </div>
        </Glass>
      ))}
    </div>
  </div>
);

// ── COLONY CREATOR MODAL ────────────────────────────────
const ColonyCreator=({onClose,onNav})=>{
  const [step,setStep]=useState(1);
  const [objective,setObjective]=useState("");
  const [suggestedTeam,setSuggestedTeam]=useState(null);
  const [selectedCastes,setSelectedCastes]=useState(["coder","reviewer"]);
  const [budget,setBudget]=useState(2.0);
  const [maxRounds,setMaxRounds]=useState(10);
  const [strategy,setStrategy]=useState("stigmergic");
  const [launching,setLaunching]=useState(false);

  const submitObjective=()=>{
    if(!objective.trim()) return;
    // Simulate suggest-team response
    setTimeout(()=>setSuggestedTeam([
      {caste:"coder",count:1,reasoning:"Implementation needed for the described task"},
      {caste:"reviewer",count:1,reasoning:"Quality verification of code changes"},
      {caste:"researcher",count:1,reasoning:"May need to look up API docs or patterns"},
    ]),400);
    setStep(2);
  };
  const launch=()=>{
    setLaunching(true);
    setTimeout(()=>{onClose();},800);
  };
  const toggleCaste=(id)=>setSelectedCastes(p=>p.includes(id)?p.filter(x=>x!==id):[...p,id]);

  return(
    <div style={{position:"fixed",inset:0,zIndex:100,display:"flex",alignItems:"center",justifyContent:"center",
      background:"rgba(5,5,8,0.85)",backdropFilter:"blur(20px)"}}>
      <div style={{width:580,maxHeight:"80vh",background:V.surface,border:`1px solid ${V.border}`,borderRadius:14,
        overflow:"hidden",display:"flex",flexDirection:"column"}}>
        {/* Header */}
        <div style={{padding:"14px 18px",borderBottom:`1px solid ${V.border}`,display:"flex",alignItems:"center",gap:8}}>
          <span style={{fontSize:14,color:V.accent}}>⬡</span>
          <span style={{fontFamily:F.display,fontSize:15,fontWeight:600,color:V.fg}}>New Colony</span>
          <div style={{display:"flex",gap:4,marginLeft:"auto"}}>
            {[1,2,3].map(s=>(
              <span key={s} style={{width:20,height:3,borderRadius:2,background:step>=s?V.accent:"rgba(255,255,255,0.06)",transition:"background 0.2s"}}/>
            ))}
          </div>
          <span onClick={onClose} style={{cursor:"pointer",color:V.fgDim,fontSize:14,marginLeft:8}}>✕</span>
        </div>
        {/* Body */}
        <div style={{flex:1,overflow:"auto",padding:18}}>
          {step===1&&(<>
            <SLabel>Describe your objective</SLabel>
            <textarea value={objective} onChange={e=>setObjective(e.target.value)} placeholder="What should the colony accomplish?"
              style={{width:"100%",height:100,background:V.void,border:`1px solid ${V.border}`,borderRadius:8,color:V.fg,
                fontFamily:F.body,fontSize:13,padding:12,outline:"none",resize:"vertical",lineHeight:1.5}}/>
            <div style={{marginTop:14}}>
              <SLabel>Or start from template</SLabel>
              <div style={{display:"flex",gap:6}}>
                {TEMPLATES.map(t=>(
                  <Glass key={t.template_id} hover onClick={()=>{setObjective(t.description);setSelectedCastes(t.caste_names);setBudget(t.budget_limit);setMaxRounds(t.max_rounds);setStep(2);}} style={{padding:10,flex:1}}>
                    <div style={{fontSize:11,fontWeight:600,color:V.fg,marginBottom:3}}>{t.name}</div>
                    <div style={{display:"flex",gap:2}}>{t.caste_names.map(cn=>{const c=CASTES.find(x=>x.id===cn);return c?<span key={cn} style={{fontSize:10}}>{c.icon}</span>:null;})}</div>
                  </Glass>
                ))}
              </div>
            </div>
          </>)}
          {step===2&&(<>
            {suggestedTeam&&(
              <div style={{marginBottom:16}}>
                <SLabel>Suggested Team</SLabel>
                <Glass style={{padding:12}}>
                  {suggestedTeam.map(s=>{const c=CASTES.find(x=>x.id===s.caste);return c?(
                    <div key={s.caste} style={{display:"flex",alignItems:"center",gap:6,padding:"4px 0",borderBottom:`1px solid ${V.border}`}}>
                      <span style={{fontSize:12,filter:`drop-shadow(0 0 2px ${c.color}30)`}}>{c.icon}</span>
                      <span style={{fontSize:11,color:V.fg,fontWeight:500}}>{c.name}</span>
                      <span style={{fontSize:9.5,color:V.fgMuted,flex:1}}>{s.reasoning}</span>
                      <Pill color={selectedCastes.includes(s.caste)?V.success:V.fgDim} onClick={()=>toggleCaste(s.caste)} sm>
                        {selectedCastes.includes(s.caste)?"✓":"add"}
                      </Pill>
                    </div>
                  ):null;})}
                </Glass>
              </div>
            )}
            <SLabel>Team Composition</SLabel>
            <div style={{display:"flex",gap:6,flexWrap:"wrap",marginBottom:14}}>
              {CASTES.filter(c=>c.id!=="queen").map(c=>(
                <Glass key={c.id} hover onClick={()=>toggleCaste(c.id)}
                  style={{padding:"8px 12px",display:"flex",alignItems:"center",gap:6,
                    border:selectedCastes.includes(c.id)?`1px solid ${c.color}40`:`1px solid ${V.border}`}}>
                  <span style={{fontSize:13,filter:selectedCastes.includes(c.id)?`drop-shadow(0 0 3px ${c.color}40)`:"none"}}>{c.icon}</span>
                  <span style={{fontSize:11,color:selectedCastes.includes(c.id)?V.fg:V.fgMuted,fontWeight:selectedCastes.includes(c.id)?500:400}}>{c.name}</span>
                  <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>{SYS_DEFAULTS[c.id]}</span>
                </Glass>
              ))}
            </div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10}}>
              <div>
                <SLabel>Budget</SLabel>
                <div style={{display:"flex",alignItems:"center",gap:4}}>
                  <span style={{fontFamily:F.mono,fontSize:12,color:V.fg}}>$</span>
                  <input type="number" value={budget} onChange={e=>setBudget(parseFloat(e.target.value)||0)} step={0.5} min={0.5}
                    style={{width:"100%",background:V.void,border:`1px solid ${V.border}`,borderRadius:6,color:V.fg,fontFamily:F.mono,fontSize:12,padding:"6px 10px",outline:"none"}}/>
                </div>
              </div>
              <div>
                <SLabel>Max Rounds</SLabel>
                <input type="number" value={maxRounds} onChange={e=>setMaxRounds(parseInt(e.target.value)||1)} min={1} max={50}
                  style={{width:"100%",background:V.void,border:`1px solid ${V.border}`,borderRadius:6,color:V.fg,fontFamily:F.mono,fontSize:12,padding:"6px 10px",outline:"none"}}/>
              </div>
              <div>
                <SLabel>Strategy</SLabel>
                <div style={{display:"flex",gap:4}}>
                  {["stigmergic","sequential"].map(s=>(
                    <Pill key={s} color={strategy===s?V.accent:V.fgDim} onClick={()=>setStrategy(s)} sm>{s}</Pill>
                  ))}
                </div>
              </div>
            </div>
          </>)}
          {step===3&&(<>
            <SLabel>Launch Summary</SLabel>
            <Glass style={{padding:14}}>
              <div style={{fontSize:11.5,color:V.fg,lineHeight:1.5,marginBottom:10}}>{objective}</div>
              <div style={{display:"flex",gap:6,marginBottom:8}}>
                {selectedCastes.map(cn=>{const c=CASTES.find(x=>x.id===cn);return c?<div key={cn} style={{display:"flex",alignItems:"center",gap:3}}>
                  <span style={{fontSize:11}}>{c.icon}</span><span style={{fontSize:10,color:V.fg}}>{c.name}</span>
                  <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>→ {SYS_DEFAULTS[c.id]}</span>
                </div>:null;})}
              </div>
              <div style={{display:"flex",gap:12,fontFamily:F.mono,fontSize:10,color:V.fgMuted}}>
                <span>${budget.toFixed(2)} budget</span>
                <span>{maxRounds} rounds</span>
                <span>{strategy}</span>
              </div>
            </Glass>
            {launching&&<div style={{marginTop:14,textAlign:"center"}}>
              <div style={{display:"inline-block",width:24,height:24,border:`2px solid ${V.accent}`,borderTopColor:"transparent",borderRadius:"50%",animation:"spin 0.8s linear infinite"}}/>
              <div style={{fontSize:10,color:V.accent,marginTop:6,fontFamily:F.mono}}>Spawning colony...</div>
            </div>}
          </>)}
        </div>
        {/* Footer */}
        <div style={{padding:"12px 18px",borderTop:`1px solid ${V.border}`,display:"flex",gap:8,justifyContent:"flex-end"}}>
          {step>1&&<Btn v="secondary" sm onClick={()=>setStep(step-1)}>Back</Btn>}
          {step===1&&<Btn sm onClick={submitObjective} disabled={!objective.trim()}>Continue</Btn>}
          {step===2&&<Btn sm onClick={()=>setStep(3)} disabled={selectedCastes.length===0}>Review</Btn>}
          {step===3&&!launching&&<Btn sm onClick={launch}>Launch Colony</Btn>}
        </div>
      </div>
    </div>
  );
};

// ── WORKSPACE CONFIG ────────────────────────────────────
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
        <Glass style={{padding:14}}>
          <SLabel>Model Cascade Overrides</SLabel>
          {CASTES.filter(c=>c.id!=="queen").map(c=>{
            const val=ws.config?.[`${c.id}_model`];
            return(
              <div key={c.id} style={{display:"flex",alignItems:"center",gap:6,padding:"5px 0",borderBottom:`1px solid ${V.border}`}}>
                <span style={{fontSize:10,filter:`drop-shadow(0 0 2px ${c.color}25)`}}>{c.icon}</span>
                <span style={{fontSize:10.5,color:V.fg,width:70}}>{c.name}</span>
                <span style={{fontFamily:F.mono,fontSize:10,color:val?V.fg:V.fgDim,flex:1}}>{val||"null (inherit)"}</span>
                {val&&<Pill color={c.color} sm>override</Pill>}
              </div>
            );
          })}
        </Glass>
        <Glass style={{padding:14}}>
          <SLabel>Governance & Budget</SLabel>
          <Meter label="Budget Used" value={totalCost} max={ws.config?.budget||5} unit="$" color={V.accent}/>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginTop:10}}>
            {[{l:"Strategy",v:ws.config?.strategy||"stigmergic"},{l:"Budget",v:`$${(ws.config?.budget||5).toFixed(2)}`},{l:"Max Rounds",v:"25"},{l:"Conv θ",v:"0.95"}].map(({l,v})=>(
              <div key={l}>
                <div style={{fontSize:7.5,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.12em",textTransform:"uppercase",marginBottom:2,fontWeight:600}}>{l}</div>
                <div style={{fontSize:11,fontFamily:F.mono,color:V.fg}}>{v}</div>
              </div>
            ))}
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
  return(
    <div style={{overflow:"auto",height:"100%",maxWidth:860}}>
      <div style={{marginBottom:16}}>
        <h2 style={{fontFamily:F.display,fontSize:20,fontWeight:700,color:V.fg,margin:0,marginBottom:3}}><GradientText>Model Registry</GradientText></h2>
        <p style={{fontSize:10.5,color:V.fgMuted,margin:0}}>
          <span style={{fontFamily:F.mono,color:V.fg}}>provider/model-name</span> · nullable cascade: thread → workspace → system
        </p>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:8,marginBottom:18}}>
        <Glass style={{padding:10}}><Meter label="GPU VRAM" value={totalVram} max={32} unit=" GB" color={V.purple} compact/><div style={{fontSize:8.5,fontFamily:F.mono,color:V.fgDim}}>RTX 5090 · 32 GB</div></Glass>
        {CLOUD_EPS.filter(c=>c.status==="connected").map(c=>(
          <Glass key={c.id} style={{padding:10}}><Meter label={c.provider} value={c.spend} max={c.limit} unit="$" color={c.color} compact/><div style={{fontSize:8.5,fontFamily:F.mono,color:V.fgDim}}>daily cap ${c.limit.toFixed(2)}</div></Glass>
        ))}
      </div>
      <SLabel>Local Models</SLabel>
      <div style={{display:"flex",flexDirection:"column",gap:6,marginBottom:18}}>
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
                    <span>{m.provider}/{m.id}</span><span>{m.backend}</span><span>ctx {m.ctx.toLocaleString()}</span>
                    {m.vram>0&&<span style={{color:V.purple}}>{m.vram} GB</span>}
                  </div>
                </div>
              </div>
              {exp&&(
                <div style={{borderTop:`1px solid ${V.border}`,padding:12,background:V.recessed}}>
                  <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10}}>
                    {[{l:"GPU",v:m.gpu},{l:"Slots",v:m.slots},{l:"Max Ctx",v:m.maxCtx.toLocaleString()},{l:"VRAM",v:m.vram>0?`${m.vram} GB`:"CPU"},{l:"Quant",v:m.quant},{l:"Backend",v:m.backend}].map(({l,v})=>(
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
      </div>
      <SLabel>Cloud Endpoints</SLabel>
      <div style={{display:"flex",flexDirection:"column",gap:6,marginBottom:18}}>
        {CLOUD_EPS.map(c=>(
          <Glass key={c.id} style={{padding:12}}>
            <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:6}}>
              <Dot status={c.status} size={6}/>
              <span style={{fontFamily:F.display,fontSize:13,fontWeight:600,color:V.fg}}>{c.provider}</span>
              <Pill color={c.status==="connected"?V.success:V.danger} sm>{c.status}</Pill>
              {c.status==="connected"&&<span style={{marginLeft:"auto",fontFamily:F.mono,fontSize:9.5,color:V.fgMuted,fontFeatureSettings:'"tnum"'}}>
                ${c.spend.toFixed(2)} / ${c.limit.toFixed(2)}</span>}
            </div>
            <div style={{display:"flex",gap:3,flexWrap:"wrap"}}>{c.models.map(m=><Pill key={m} color={V.fg} sm>{m}</Pill>)}</div>
            {c.status==="connected"&&<div style={{marginTop:8}}><Meter label="Daily" value={c.spend} max={c.limit} unit="$" color={c.color} compact/></div>}
          </Glass>
        ))}
      </div>
      <SLabel>Default Routing Cascade</SLabel>
      <Glass style={{padding:12}}>
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

// ── CASTES VIEW ─────────────────────────────────────────
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
            <span style={{display:"inline-flex",alignItems:"center",gap:3}}>
              <span style={{width:5,height:5,borderRadius:"50%",background:PROVIDER_COLOR[providerOf(SYS_DEFAULTS[c.id])]||V.fgDim}}/>
              <span style={{fontFamily:F.mono,fontSize:11.5,color:V.fg}}>{SYS_DEFAULTS[c.id]}</span>
            </span>
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
  const [showCreator,setShowCreator]=useState(false);

  const navTree=id=>{setTreeSel(id);setView("tree");};
  const navTab=v=>{setView(v);if(v!=="tree")setTreeSel(null);};
  const handleMerge=(fromId,toId)=>setMerges(p=>[...p,{from:fromId,to:toId,id:`merge-${Date.now()}`,active:true}]);
  const handlePrune=(mergeId)=>setMerges(p=>p.map(m=>m.id===mergeId?{...m,active:false}:m));
  const handleBroadcast=()=>{};

  const selNode=treeSel?findNode(TREE,treeSel):null;
  const crumbs=treeSel?bc(TREE,treeSel):null;
  const showTree=view==="tree"||view==="queen";
  const showFull=showTree||sideOpen;
  const totalVram=LOCAL_MODELS.filter(m=>m.status==="loaded").reduce((a,m)=>a+m.vram,0);
  const totalCost=allColonies(TREE).reduce((a,c)=>a+(c.cost||0),0);
  const parentWs = selNode?.type==="thread"?TREE.find(ws=>(ws.children||[]).some(th=>th.id===selNode.id)):null;

  const NAV=[
    {id:"queen",label:"Queen",icon:"♛"},
    {id:"skills",label:"Skills",icon:"◈"},
    {id:"templates",label:"Templates",icon:"⧉"},
    {id:"models",label:"Models",icon:"⬢"},
    {id:"castes",label:"Castes",icon:"⬡"},
    {id:"settings",label:"Settings",icon:"⚙"},
  ];

  return(
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
        @import url('https://api.fontshare.com/v2/css?f[]=satoshi@500,600,700,800&f[]=geist@400,500,600&display=swap');
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.25}}
        @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
        *{box-sizing:border-box;margin:0;padding:0;}
        ::-webkit-scrollbar{width:3px;}::-webkit-scrollbar-track{background:transparent;}
        ::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.03);border-radius:2px;}
        ::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,0.06);}
        ::selection{background:${V.accent}25;}
        @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:0.01ms!important;transition-duration:0.01ms!important;}}
      `}</style>

      {/* Atmosphere */}
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
          background:"rgba(8,8,15,0.85)",backdropFilter:"blur(14px)",WebkitBackdropFilter:"blur(14px)"}}>
          <div style={{display:"flex",alignItems:"center",gap:6,cursor:"pointer"}} onClick={()=>navTab("queen")}>
            <span style={{fontFamily:F.display,fontWeight:800,fontSize:15,color:V.fg,letterSpacing:"-0.04em"}}>
              formic<span style={{color:V.accent}}>OS</span>
            </span>
            <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.05em"}}>2.1.0</span>
          </div>
          {view==="tree"&&crumbs&&(
            <div style={{display:"flex",alignItems:"center",gap:2,fontSize:10.5,fontFamily:F.mono}}>
              {crumbs.map((n,i)=>(
                <span key={n.id} style={{display:"flex",alignItems:"center",gap:2}}>
                  {i>0&&<span style={{color:V.fgDim,fontSize:7}}>⟩</span>}
                  <span onClick={()=>navTree(n.id)} style={{color:i===crumbs.length-1?V.fg:V.fgMuted,cursor:"pointer"}}>{colonyName(n)}</span>
                </span>
              ))}
            </div>
          )}
          <div style={{flex:1}}/>
          <div style={{display:"flex",alignItems:"center",gap:12,fontSize:9.5,fontFamily:F.mono,fontFeatureSettings:'"tnum"'}}>
            <ProtocolBar/>
            <span style={{color:V.fgDim}}><span style={{color:V.accent}}>${totalCost.toFixed(2)}</span></span>
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
            <div style={{display:"flex",flexDirection:showFull?"row":"column",borderBottom:`1px solid ${V.border}`,padding:showFull?"3px 4px":"4px 3px",gap:1,flexWrap:"wrap"}}>
              {NAV.map(n=>{
                const act=view===n.id||(view==="tree"&&n.id==="queen");
                return(
                  <div key={n.id} onClick={()=>navTab(n.id)} title={n.label}
                    style={{flex:showFull?"1 0 auto":"none",height:showFull?28:30,display:"flex",alignItems:"center",
                      justifyContent:"center",gap:3,borderRadius:6,cursor:"pointer",fontSize:11,
                      background:act?`${V.accent}0C`:"transparent",color:act?V.accent:V.fgDim,transition:"all 0.15s",
                      padding:showFull?"0 6px":"0"}}>
                    <span style={{filter:act?`drop-shadow(0 0 3px ${V.accent}40)`:"none",fontSize:11}}>{n.icon}</span>
                    {showFull&&<span style={{fontSize:9.5,fontWeight:500}}>{n.label}</span>}
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
                  <div key={c.id} onClick={()=>navTree(c.id)} title={colonyName(c)}
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
                queenThreads={QUEEN_THREADS} activeQT={activeQT} onSwitchQT={setActiveQT}
                onCreateColony={()=>setShowCreator(true)}/>}
              {view==="tree"&&selNode?.type==="colony"&&<ViewColony colony={selNode}
                queenThreads={QUEEN_THREADS} activeQT={activeQT} onSwitchQT={setActiveQT}/>}
              {view==="tree"&&selNode?.type==="workspace"&&<ViewWorkspace ws={selNode} onNav={navTree}/>}
              {view==="tree"&&selNode?.type==="thread"&&<ViewThread thread={selNode} parentWs={parentWs}
                merges={merges} onNav={navTree} onMerge={handleMerge} onPrune={handlePrune} onBroadcast={handleBroadcast}
                onCreateColony={()=>setShowCreator(true)}/>}
              {view==="skills"&&<ViewSkills/>}
              {view==="templates"&&<ViewTemplates onCreateColony={()=>setShowCreator(true)}/>}
              {view==="models"&&<ViewModels/>}
              {view==="castes"&&<ViewCastes/>}
              {view==="settings"&&<ViewSettings/>}
            </div>
          </div>
        </div>
      </div>

      {showCreator&&<ColonyCreator onClose={()=>setShowCreator(false)} onNav={navTree}/>}
    </>
  );
}
