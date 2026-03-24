import { useState, useEffect, useRef, useMemo } from "react";

/*
 * ═══════════════════════════════════════════════════════════
 * FORMICOS v3.1.0 — WAVE 14 UI PROTOTYPE / VISUAL SPEC
 * ═══════════════════════════════════════════════════════════
 *
 * CONCEPTUAL SHIFTS from v3.0:
 *
 *  SERVICE COLONIES — A completed colony can become a dormant-
 *  but-callable service. It retains its tools, skills, and
 *  knowledge. Other colonies (or external agents via A2A/MCP)
 *  send it messages through its per-colony chat. It responds
 *  using its full accumulated context. A research colony that
 *  learned web scraping doesn't die — it becomes a callable
 *  research service.
 *
 *  SUBCASTE TIERS — Each agent slot has a tier: Light (local-
 *  only, free), Balanced (default routing), Heavy (cloud-only,
 *  max capability). The operator controls cost/quality tradeoff
 *  per agent, not just per caste.
 *
 *  COLONY-AS-RESOURCE — In the Creator, you don't add a service
 *  colony as a team member. You attach it as a resource the team
 *  can call. Like giving the colony a tool.
 *
 *  SUGGEST-TEAM — The Creator's first step asks the AI to
 *  recommend team composition + tiers + services based on the
 *  objective. The operator adjusts from there.
 *
 *  PER-COLONY CHAT — Three caller types with source badges:
 *    Operator (you), Queen (directives), Colonies/External
 *    (delegation requests from siblings or A2A/MCP agents).
 *
 *  CONSOLIDATED NAV — 5 tabs: Queen, Knowledge (skills+graph),
 *  Templates, Fleet (models+services+castes), Settings.
 * ═══════════════════════════════════════════════════════════
 */

// ── DESIGN TOKENS ────────────────────────────────────────
const V = {
  void:"#08080F",surface:"#10111A",elevated:"#1A1B26",recessed:"#050508",
  border:"rgba(255,255,255,0.06)",borderHover:"rgba(255,255,255,0.14)",borderAccent:"rgba(232,88,26,0.22)",
  fg:"#EDEDF0",fgMuted:"#6B6B76",fgDim:"#45454F",fgOnAccent:"#0A0A0F",
  accent:"#E8581A",accentBright:"#F4763A",accentDeep:"#B8440F",accentMuted:"rgba(232,88,26,0.08)",accentGlow:"rgba(232,88,26,0.16)",
  secondary:"#3DD6F5",secondaryMuted:"rgba(61,214,245,0.07)",secondaryGlow:"rgba(61,214,245,0.12)",
  success:"#2DD4A8",warn:"#F5B731",danger:"#F06464",purple:"#A78BFA",blue:"#5B9CF5",
  glass:"rgba(16,17,26,0.60)",glassHover:"rgba(26,27,38,0.78)",
  service:"#22D3EE",
};
const F = {display:"'Satoshi','General Sans','DM Sans',system-ui,sans-serif",body:"'Geist','DM Sans','Plus Jakarta Sans',system-ui,sans-serif",mono:"'IBM Plex Mono','JetBrains Mono',monospace"};
const PROV_COLOR={"llama-cpp":V.success,"anthropic":V.accent,"gemini":V.blue,"local":V.fgDim};
const providerOf=m=>!m?"local":m.startsWith("anthropic/")?"anthropic":m.startsWith("gemini/")?"gemini":"llama-cpp";

// ── DATA MODEL ───────────────────────────────────────────
const CASTES=[
  {id:"coder",name:"Coder",icon:"⟨/⟩",color:V.success,desc:"Writes and debugs code via tools"},
  {id:"reviewer",name:"Reviewer",icon:"⊘",color:V.purple,desc:"Reviews outputs, runs verification"},
  {id:"researcher",name:"Researcher",icon:"◎",color:V.blue,desc:"Retrieves, synthesizes, cites findings"},
  {id:"archivist",name:"Archivist",icon:"⧫",color:V.warn,desc:"Compresses, extracts skills, distills"},
];
const TIERS={
  light:  {label:"Light",  icon:"○",color:V.success,tag:"local-only",costHint:"free"},
  balanced:{label:"Balanced",icon:"◐",color:V.fgMuted,tag:"smart routing",costHint:"~$0.02/turn"},
  heavy:  {label:"Heavy",  icon:"●",color:V.accent, tag:"cloud-only", costHint:"~$0.08/turn"},
};
const TIER_MODELS={
  coder:     {light:"llama-cpp/qwen3-30b",balanced:"llama-cpp/qwen3-30b",heavy:"anthropic/claude-sonnet-4.6"},
  reviewer:  {light:"llama-cpp/qwen3-30b",balanced:"llama-cpp/qwen3-30b",heavy:"anthropic/claude-sonnet-4.6"},
  researcher:{light:"llama-cpp/qwen3-30b",balanced:"gemini/gemini-2.5-flash",heavy:"anthropic/claude-sonnet-4.6"},
  archivist: {light:"llama-cpp/qwen3-30b",balanced:"gemini/gemini-2.5-flash",heavy:"anthropic/claude-sonnet-4.6"},
};

const EXEC_OK=[
  {code:"import math\nprint(math.sqrt(144))",tier:"STANDARD",exit_code:0,stdout:"12.0",stderr:"",duration_ms:340,cpu_ms:28,mem_mb:45},
  {code:"import numpy as np\nprint(np.random.rand(1000).mean())",tier:"STANDARD",exit_code:0,stdout:"0.4987",stderr:"",duration_ms:520,cpu_ms:41,mem_mb:62},
];
const EXEC_FAIL={code:"import subprocess\nsubprocess.run(['ls'])",tier:"STANDARD",exit_code:1,stdout:"",stderr:"Blocked import 'subprocess'",duration_ms:2,cpu_ms:0,mem_mb:0,error:"AST safety"};

// Colony tree — note "service" status on Dependency Analysis
const TREE=[
  {id:"ws-auth",name:"refactor-auth",type:"workspace",
    config:{budget:5.0,strategy:"stigmergic"},
    children:[
      {id:"th-main",name:"main",type:"thread",children:[
        {id:"col-a1b2",displayName:"Auth Refactor Sprint",type:"colony",status:"running",round:4,maxRounds:10,
          task:"Refactor JWT refresh handler — token rotation, session invalidation, PKCE flow",
          strategy:"stigmergic",
          agents:[
            {name:"Coder-α",caste:"coder",tier:"heavy",model:"anthropic/claude-sonnet-4.6",tokens:18420,status:"active",pheromone:0.82},
            {name:"Reviewer-β",caste:"reviewer",tier:"light",model:"llama-cpp/qwen3-30b",tokens:6820,status:"pending",pheromone:0.61},
            {name:"Archivist-γ",caste:"archivist",tier:"balanced",model:"gemini/gemini-2.5-flash",tokens:4420,status:"done",pheromone:0.44},
          ],
          services:["col-c3d4"], // attached service colonies
          convergence:0.72,convergenceHistory:[0.21,0.48,0.65,0.72],cost:0.38,budget:2.0,
          topology:{nodes:[{id:"queen",label:"QUEEN",x:200,y:30,c:V.accent},{id:"coder",label:"CODER",x:80,y:140,c:V.success},{id:"reviewer",label:"REVIEWER",x:320,y:140,c:V.purple},{id:"archivist",label:"ARCHVST",x:200,y:230,c:V.warn}],edges:[{from:"queen",to:"coder",w:1.4},{from:"queen",to:"reviewer",w:0.8},{from:"coder",to:"reviewer",w:1.8},{from:"reviewer",to:"archivist",w:0.9},{from:"coder",to:"archivist",w:0.6}]},
          defense:{composite:0.12,signals:[{name:"entropy",value:0.08,threshold:1.0},{name:"drift",value:0.15,threshold:0.7}]},
          rounds:[
            {r:1,phase:"Goal",convergence:0.21,cost:0.04,agents:[{n:"Coder-α",m:"llama-cpp/qwen3-30b",t:2840,s:"done",output:"Analyzed JWT refresh flow. 3 rotation bugs found.",tools:["memory_search"],execs:[]},{n:"Reviewer-β",m:"llama-cpp/qwen3-30b",t:1920,s:"done",output:"Confirmed CVE-2024-3891 match.",tools:["memory_search"],execs:[]},{n:"Archivist-γ",m:"gemini/gemini-2.5-flash",t:1200,s:"done",output:"Compressed R1. 2 candidate skills.",tools:["memory_write"],execs:[]}]},
            {r:2,phase:"Execute",convergence:0.48,cost:0.12,agents:[{n:"Coder-α",m:"anthropic/claude-sonnet-4.6",t:8420,s:"done",output:"Token rotation + PKCE binding implemented. 4 files changed.",tools:["code_write","code_execute"],execs:[EXEC_OK[0]]},{n:"Reviewer-β",m:"llama-cpp/qwen3-30b",t:3100,s:"done",output:"Review passed, 2 minor suggestions.",tools:["code_read"],execs:[]},{n:"Archivist-γ",m:"gemini/gemini-2.5-flash",t:1800,s:"done",output:"Skill extracted: JWT rotation with DPoP.",tools:["skill_extract"],execs:[]}]},
            {r:3,phase:"Execute",convergence:0.65,cost:0.14,agents:[{n:"Coder-α",m:"anthropic/claude-sonnet-4.6",t:6200,s:"done",output:"Session invalidation + Redis TTL complete.",tools:["code_write","code_execute"],execs:[EXEC_OK[1],EXEC_FAIL]},{n:"Reviewer-β",m:"llama-cpp/qwen3-30b",t:2800,s:"done",output:"Flagged concurrent refresh edge case.",tools:["code_read"],execs:[]},{n:"Archivist-γ",m:"gemini/gemini-2.5-flash",t:1400,s:"done",output:"Updated JWT skill confidence.",tools:["memory_write"],execs:[]}]},
            {r:4,phase:"Route",convergence:0.72,cost:0.08,agents:[{n:"Coder-α",m:"anthropic/claude-sonnet-4.6",t:3200,s:"active",output:"Working on race condition...",tools:[],execs:[]},{n:"Reviewer-β",m:"llama-cpp/qwen3-30b",t:0,s:"pending",output:null,tools:[],execs:[]},{n:"Archivist-γ",m:"gemini/gemini-2.5-flash",t:0,s:"pending",output:null,tools:[],execs:[]}]},
          ],
        },
        {id:"col-c3d4",displayName:"Dependency Analysis",type:"colony",status:"service",round:5,maxRounds:5,
          task:"Auth module dependency mapping + vulnerability scan — now serving as a callable knowledge service",
          strategy:"stigmergic",
          agents:[{name:"Coder-α",caste:"coder",tier:"light",model:"llama-cpp/qwen3-30b",tokens:28400,status:"idle",pheromone:0.95},{name:"Reviewer-β",caste:"reviewer",tier:"light",model:"llama-cpp/qwen3-30b",tokens:12800,status:"idle",pheromone:0.88}],
          services:[],convergence:0.95,convergenceHistory:[0.30,0.52,0.71,0.88,0.95],cost:0.62,budget:1.0,quality:0.81,skillsExtracted:3,
          topology:null,defense:null,rounds:[]},
      ]},
      {id:"th-exp",name:"experiment",type:"thread",children:[
        {id:"col-e5f6",displayName:"OAuth2 PKCE Spike",type:"colony",status:"queued",round:0,maxRounds:6,
          task:"Test alternative OAuth2 PKCE flow with DPoP binding",strategy:"sequential",
          agents:[{name:"Researcher-α",caste:"researcher",tier:"balanced",model:"gemini/gemini-2.5-flash",tokens:0,status:"pending",pheromone:0}],
          services:[],convergence:0,convergenceHistory:[],cost:0,budget:1.0,topology:null,defense:null,rounds:[]},
      ]},
    ]},
  {id:"ws-research",name:"research-ttt",type:"workspace",
    config:{budget:2.0,strategy:"stigmergic"},
    children:[
      {id:"th-main2",name:"main",type:"thread",children:[
        {id:"col-g7h8",displayName:"TTT Memory Survey",type:"colony",status:"running",round:2,maxRounds:10,
          task:"Research test-time training for agent memory — TTT-E2E, ZipMap, hybrid retrieval",strategy:"stigmergic",
          agents:[{name:"Researcher-α",caste:"researcher",tier:"heavy",model:"anthropic/claude-sonnet-4.6",tokens:4200,status:"active",pheromone:0.67},{name:"Coder-β",caste:"coder",tier:"light",model:"llama-cpp/qwen3-30b",tokens:2100,status:"done",pheromone:0.38}],
          services:["col-c3d4"],convergence:0.41,convergenceHistory:[0.18,0.41],cost:0.21,budget:2.0,
          topology:null,defense:{composite:0.09,signals:[{name:"entropy",value:0.05,threshold:1.0}]},rounds:[]},
      ]},
    ]},
];

const LOCAL_MODELS=[
  {id:"qwen3-30b",name:"Qwen 3 30B-A3B",quant:"Q4_K_M",status:"loaded",vram:21.1,backend:"llama.cpp",gpu:"RTX 5090",provider:"llama-cpp"},
  {id:"qwen3-embed",name:"Qwen3-Embedding-0.6B",quant:"Q8_0",status:"loaded",vram:0.7,backend:"llama.cpp (sidecar)",gpu:"RTX 5090",provider:"local"},
];
const CLOUD_EPS=[
  {id:"anthropic",provider:"Anthropic",models:["claude-sonnet-4.6","claude-opus-4.6","claude-haiku-4.5"],status:"connected",spend:0.62,limit:10.0,color:V.accent},
  {id:"gemini",provider:"Gemini",models:["gemini-2.5-flash","gemini-2.5-flash-lite"],status:"connected",spend:0.04,limit:5.0,color:V.blue},
];

const QUEEN_THREADS=[
  {id:"qt-main",name:"main",permanent:true,messages:[
    {role:"queen",text:"FormicOS online. 2 workspaces, 4 colonies (2 running, 1 service, 1 queued). Skill bank: 7 entries. Knowledge graph: 9 entities. All systems nominal.",ts:"14:00"},
    {role:"operator",text:"Start with auth. JWT refresh is the priority.",ts:"14:30"},
    {role:"queen",text:"Spawning Auth Refactor Sprint in ws-auth/main. Attaching Dependency Analysis as a service — it has 3 relevant skills and 8 KG entities covering the auth module.",ts:"14:30"},
    {role:"event",text:"ColonySpawned · Auth Refactor Sprint · 3 agents (Coder heavy, Reviewer light, Archivist balanced)",ts:"14:31",kind:"spawn"},
    {role:"event",text:"MergeCreated · Dependency Analysis → Auth Refactor Sprint",ts:"14:31",kind:"merge"},
    {role:"operator",text:"Also find papers on test-time training for agent memory.",ts:"15:10"},
    {role:"queen",text:"Spawning TTT Memory Survey in ws-research/main. Researcher heavy, Coder light. Also attaching Dependency Analysis service for cross-referencing.",ts:"15:10"},
    {role:"event",text:"ColonySpawned · TTT Memory Survey · 2 agents",ts:"15:10",kind:"spawn"},
    {role:"queen",text:"Fleet status: Auth Refactor at R4 (conv 0.72, on track), TTT Survey at R2 (conv 0.41, early). Dependency Analysis serving both as knowledge service. 1 pending approval: Coder cloud escalation to opus-4.6.",ts:"15:20"},
  ]},
  {id:"qt-1",name:"auth strategy",permanent:false,messages:[
    {role:"operator",text:"Let's focus just on the auth approach. What's the Coder's plan for the race condition?",ts:"14:40"},
    {role:"queen",text:"Coder-α identified the race in concurrent refresh: two requests can both pass the version check before either writes. Plan is CAS (compare-and-swap) on the token version field with a Redis WATCH/MULTI block. The Dependency Analysis service confirmed this pattern works — skill sk-003 (confidence 88%).",ts:"14:40"},
  ]},
  {id:"qt-2",name:"research plan",permanent:false,messages:[
    {role:"operator",text:"What's the TTT colony finding so far?",ts:"15:18"},
    {role:"queen",text:"R2 complete. Researcher found 3 relevant papers: TTT-E2E (meta-learning), ZipMap (94% retention at 8x compression), and a hybrid retrieval approach combining vector + graph traversal. Convergence still low at 0.41 — early synthesis phase.",ts:"15:18"},
  ]},
];

// Per-colony chats with multi-caller messages
const COLONY_CHATS={
  "col-a1b2":[
    {role:"queen",text:"Colony spawned. 3 agents (Coder heavy, Reviewer light, Archivist balanced). Dependency Analysis attached as service.",ts:"14:31",source:"queen"},
    {role:"event",text:"R1 · Goal · conv 0.21",ts:"14:32",kind:"metric"},
    {role:"event",text:"R2 · Execute · conv 0.48 · 1 skill extracted",ts:"14:34",kind:"metric"},
    {role:"event",text:"Coder queried Dependency Analysis service: 'known CVEs for jsonwebtoken@8.x'",ts:"14:34",kind:"service"},
    {role:"colony",text:"3 known CVEs. CVE-2024-3891 (refresh bypass), CVE-2024-2107 (timing), CVE-2023-8921 (rotation). Recommend addressing 3891 first.",ts:"14:34",source:"Dependency Analysis",sourceId:"col-c3d4"},
    {role:"queen",text:"Escalating Coder to cloud for Execute phase. Budget at 62%.",ts:"14:36",source:"queen",parsed:false},
    {role:"event",text:"R3 · Execute · conv 0.65 · sandbox blocked subprocess",ts:"14:37",kind:"metric"},
    {role:"queen",text:"AST pre-parser caught the subprocess import. Agent will retry with allowed imports.",ts:"14:37",source:"queen",parsed:true},
    {role:"operator",text:"Focus on the concurrent refresh race condition — that's the blocker.",ts:"14:39"},
    {role:"queen",text:"Directive queued. Coder will prioritize race condition next round.",ts:"14:39",source:"queen"},
  ],
  "col-c3d4":[
    {role:"queen",text:"Colony completed R5/5. Quality: 0.81. 3 skills extracted.",ts:"14:25",source:"queen"},
    {role:"queen",text:"Status changed to SERVICE. Retaining tools and knowledge. Now callable by other colonies.",ts:"14:26",source:"queen"},
    {role:"event",text:"Service activated · 2 agents idle · 3 skills · 8 KG entities",ts:"14:26",kind:"service"},
    {role:"colony",text:"Query: 'known CVEs for jsonwebtoken@8.x'",ts:"14:34",source:"Auth Refactor Sprint",sourceId:"col-a1b2"},
    {role:"queen",text:"Responding with CVE data from accumulated analysis...",ts:"14:34",source:"queen"},
    {role:"colony",text:"Query: 'dependency tree for auth_handler.rs'",ts:"15:12",source:"TTT Memory Survey",sourceId:"col-g7h8"},
    {role:"queen",text:"Responding with module dependency graph...",ts:"15:12",source:"queen"},
    {role:"operator",text:"Good to see you're being useful. Keep serving.",ts:"15:15"},
  ],
  "col-g7h8":[
    {role:"queen",text:"Colony spawned. Researcher heavy, Coder light. Dependency Analysis attached as service.",ts:"15:10",source:"queen"},
    {role:"event",text:"R1 · conv 0.18 · web_search: 'test-time training agent memory 2025'",ts:"15:14",kind:"metric"},
    {role:"event",text:"R2 · Researcher active · queried Dependency Analysis for cross-refs",ts:"15:16",kind:"route"},
  ],
  "col-e5f6":[{role:"queen",text:"Colony queued. Waiting for execution slot.",ts:"14:45",source:"queen"}],
};

const APPROVALS=[{id:1,type:"Cloud Escalation",agent:"Coder-α",detail:"claude-opus-4.6 · est. $0.42",colony:"col-a1b2",colonyName:"Auth Refactor Sprint"}];

const TEMPLATES=[
  {template_id:"tpl-001",name:"Code Review",desc:"Coder+Reviewer pair",castes:[{id:"coder",tier:"balanced"},{id:"reviewer",tier:"balanced"}],strategy:"stigmergic",budget:1.0,maxRounds:8,tags:["code","review"],uses:12,successRate:0.83,avgCost:0.45},
  {template_id:"tpl-002",name:"Research Sprint",desc:"Deep research with archival",castes:[{id:"researcher",tier:"heavy"},{id:"archivist",tier:"balanced"}],strategy:"stigmergic",budget:2.0,maxRounds:15,tags:["research"],uses:5,successRate:0.80,avgCost:0.92},
  {template_id:"tpl-003",name:"Full Stack",desc:"Complete team, max capability",castes:[{id:"coder",tier:"heavy"},{id:"reviewer",tier:"balanced"},{id:"researcher",tier:"balanced"},{id:"archivist",tier:"light"}],strategy:"stigmergic",budget:3.0,maxRounds:25,tags:["code","full"],uses:3,successRate:0.67,avgCost:1.85},
  {template_id:"tpl-004",name:"Bug Triage",desc:"Diagnose and fix a specific bug",castes:[{id:"coder",tier:"balanced"},{id:"reviewer",tier:"light"}],strategy:"stigmergic",budget:1.5,maxRounds:10,tags:["debug"],uses:8,successRate:0.88,avgCost:0.55},
  {template_id:"tpl-005",name:"Research Lite",desc:"Quick web lookup, single agent",castes:[{id:"researcher",tier:"balanced"}],strategy:"sequential",budget:0.5,maxRounds:5,tags:["research","quick"],uses:15,successRate:0.90,avgCost:0.12},
  {template_id:"tpl-006",name:"Minimal",desc:"One coder, cheapest option",castes:[{id:"coder",tier:"light"}],strategy:"sequential",budget:0.5,maxRounds:5,tags:["quick"],uses:20,successRate:0.72,avgCost:0.08},
];

const SKILLS=[
  {id:"sk-001",text:"JWT token rotation with PKCE requires DPoP proof before refresh",confidence:0.83,alpha:15,beta:3,uncertainty:0.08,source:"Dependency Analysis",merged:false,at:"2025-03-12T14:35:00Z"},
  {id:"sk-002",text:"Redis TTL session invalidation: key expiry matches refresh token lifetime",confidence:0.79,alpha:12,beta:4,uncertainty:0.10,source:"Auth Refactor Sprint",merged:false,at:"2025-03-12T14:40:00Z"},
  {id:"sk-003",text:"Concurrent refresh mitigated by CAS on token version field",confidence:0.88,alpha:18,beta:2,uncertainty:0.06,source:"Dependency Analysis",merged:true,at:"2025-03-11T10:20:00Z"},
  {id:"sk-004",text:"Hybrid retrieval (vector+BFS graph) improves recall 23% vs vector-only",confidence:0.61,alpha:7,beta:5,uncertainty:0.15,source:"TTT Memory Survey",merged:false,at:"2025-03-12T15:25:00Z"},
  {id:"sk-005",text:"PKCE code_verifier must use S256; plain method deprecated since 2024",confidence:0.91,alpha:20,beta:2,uncertainty:0.05,source:"Dependency Analysis",merged:true,at:"2025-03-09T11:00:00Z"},
  {id:"sk-006",text:"Local routing for Goal/Compress saves 60-80% cost, <5% quality loss",confidence:0.74,alpha:10,beta:3,uncertainty:0.11,source:"Dependency Analysis",merged:false,at:"2025-03-11T13:30:00Z"},
  {id:"sk-007",text:"Test-time training with ZipMap: 94% retention at 8x compression",confidence:0.52,alpha:4,beta:3,uncertainty:0.21,source:"TTT Memory Survey",merged:false,at:"2025-03-12T15:20:00Z"},
];

const KG_NODES=[
  {id:"kg-1",name:"FastAPI_router",type:"MODULE",source:"Dependency Analysis"},
  {id:"kg-2",name:"Pydantic_models",type:"MODULE",source:"Dependency Analysis"},
  {id:"kg-3",name:"JWT_rotation",type:"CONCEPT",source:"Auth Refactor Sprint"},
  {id:"kg-4",name:"session_invalidation",type:"CONCEPT",source:"Auth Refactor Sprint"},
  {id:"kg-5",name:"PKCE_flow",type:"CONCEPT",source:"Dependency Analysis"},
  {id:"kg-6",name:"Redis_TTL",type:"TOOL",source:"Auth Refactor Sprint"},
  {id:"kg-7",name:"DPoP_binding",type:"CONCEPT",source:"Auth Refactor Sprint"},
  {id:"kg-8",name:"ZipMap",type:"CONCEPT",source:"TTT Memory Survey"},
  {id:"kg-9",name:"hybrid_retrieval",type:"CONCEPT",source:"TTT Memory Survey"},
];
const KG_EDGES=[
  {from:"kg-1",to:"kg-2",pred:"DEPENDS_ON"},{from:"kg-3",to:"kg-1",pred:"IMPLEMENTS"},
  {from:"kg-3",to:"kg-5",pred:"ENABLES"},{from:"kg-4",to:"kg-6",pred:"DEPENDS_ON"},
  {from:"kg-7",to:"kg-3",pred:"VALIDATES"},{from:"kg-5",to:"kg-7",pred:"ENABLES"},
  {from:"kg-9",to:"kg-8",pred:"DEPENDS_ON"},
];

// ── HELPERS ──────────────────────────────────────────────
function findNode(n,id){for(const x of n){if(x.id===id)return x;if(x.children){const f=findNode(x.children,id);if(f)return f;}}return null;}
function allColonies(n){let o=[];for(const x of n){if(x.type==="colony")o.push(x);if(x.children)o=o.concat(allColonies(x.children));}return o;}
function bc(n,id,p=[]){for(const x of n){const c=[...p,x];if(x.id===id)return c;if(x.children){const f=bc(x.children,id,c);if(f)return f;}}return null;}
function cn(c){return c.displayName||c.id;}
function timeAgo(iso){const h=Math.floor((Date.now()-new Date(iso).getTime())/3600000);return h<1?"now":h<24?`${h}h`:`${Math.floor(h/24)}d`;}

// ── ATOMS ────────────────────────────────────────────────
const Pill=({children,color=V.fgMuted,glow,sm,onClick})=><span onClick={onClick} style={{display:"inline-flex",alignItems:"center",gap:3,padding:sm?"1px 7px":"2px 10px",borderRadius:999,fontSize:sm?8.5:9.5,fontFamily:F.mono,letterSpacing:"0.05em",fontWeight:500,color,background:`${color}12`,border:`1px solid ${color}18`,boxShadow:glow?`0 0 14px ${color}18`:"none",cursor:onClick?"pointer":"default"}}>{children}</span>;
const Dot=({status,size=6})=>{const c={running:V.success,completed:V.secondary,queued:V.warn,service:V.service,loaded:V.success,connected:V.success,active:V.success,pending:V.warn,done:V.secondary,idle:V.service,failed:V.danger}[status]||V.fgDim;const p=["running","active","loaded","service"].includes(status);return <span style={{display:"inline-block",width:size,height:size,borderRadius:status==="service"?2:"50%",background:c,flexShrink:0,boxShadow:p?`0 0 ${size+4}px ${c}50`:"none",animation:p&&status!=="service"?"pulse 2.8s ease-in-out infinite":"none"}}/>;};
const Meter=({label,value,max,unit="",color=V.accent,compact})=>{const v=typeof value==="string"?parseFloat(value):value;const p=max>0?Math.min(v/max*100,100):0;return <div style={{marginBottom:compact?5:9}}><div style={{display:"flex",justifyContent:"space-between",marginBottom:2}}><span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:600}}>{label}</span><span style={{fontSize:10,fontFamily:F.mono,color:V.fgMuted,fontFeatureSettings:'"tnum"'}}>{unit==="$"?`$${v.toFixed(2)}`:`${typeof value==="number"?v.toFixed(1):value}${unit}`}<span style={{color:V.fgDim}}> / {unit==="$"?`$${max.toFixed(2)}`:`${max}${unit}`}</span></span></div><div style={{height:2,background:"rgba(255,255,255,0.03)",borderRadius:1,overflow:"hidden"}}><div style={{height:"100%",width:`${p}%`,borderRadius:1,background:p>85?V.danger:p>65?V.warn:color,transition:"width 0.6s"}}/></div></div>;};
const Btn=({children,onClick,v="primary",sm,sx,disabled:d})=>{const[h,sH]=useState(false);const base={fontFamily:F.body,fontSize:sm?10.5:12,fontWeight:500,cursor:d?"default":"pointer",borderRadius:999,border:"none",transition:"all 0.2s",padding:sm?"3px 10px":"7px 16px",opacity:d?0.3:1,display:"inline-flex",alignItems:"center",gap:4,whiteSpace:"nowrap",...sx};const vs={primary:{background:h&&!d?V.accentBright:V.accent,color:"#fff",boxShadow:h?`0 0 24px ${V.accentGlow}`:"none"},secondary:{background:h?"rgba(255,255,255,0.04)":"transparent",color:V.fg,border:`1px solid ${h?V.borderHover:V.border}`},ghost:{background:h?"rgba(255,255,255,0.03)":"transparent",color:h?V.fg:V.fgMuted},danger:{background:h?"rgba(240,100,100,0.12)":"transparent",color:V.danger,border:`1px solid ${V.danger}25`},success:{background:h?"rgba(45,212,168,0.12)":"transparent",color:V.success,border:`1px solid ${V.success}25`}};return <button onClick={d?undefined:onClick} onMouseEnter={()=>sH(true)} onMouseLeave={()=>sH(false)} style={{...base,...vs[v]}}>{children}</button>;};
const Glass=({children,style:sx,hover,featured,onClick})=>{const[h,sH]=useState(false);return <div onClick={onClick} onMouseEnter={()=>sH(true)} onMouseLeave={()=>sH(false)} style={{background:h&&hover?V.glassHover:V.glass,backdropFilter:"blur(14px)",border:`1px solid ${featured?V.borderAccent:h&&hover?V.borderHover:V.border}`,borderRadius:10,padding:14,transition:"all 0.25s",cursor:onClick?"pointer":"default",transform:h&&hover?"translateY(-1px)":"none",boxShadow:featured?`0 0 28px ${V.accentGlow}`:h&&hover?"0 8px 32px rgba(5,5,8,0.6)":"0 1px 2px rgba(5,5,8,0.3)",...sx}}>{children}</div>;};
const SLabel=({children,sx})=><div style={{fontSize:8,fontFamily:F.mono,fontWeight:600,color:V.fgDim,letterSpacing:"0.14em",textTransform:"uppercase",marginBottom:7,...sx}}>{children}</div>;
const GradientText=({children})=><span style={{background:`linear-gradient(135deg,${V.accentBright},${V.accent},${V.secondary})`,WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent",backgroundClip:"text"}}>{children}</span>;
const Sparkline=({data,w=60,h=16,color=V.accent})=>{if(!data||data.length<2)return null;const mx=Math.max(...data,1),mn=Math.min(...data,0),r=mx-mn||1;return <svg width={w} height={h} style={{display:"inline-block",verticalAlign:"middle"}}><polyline points={data.map((v,i)=>`${(i/(data.length-1))*w},${h-(((v-mn)/r)*h)}`).join(" ")} fill="none" stroke={color} strokeWidth={1.2} strokeLinejoin="round" opacity={0.7}/></svg>;};
const QualityDot=({q,s=6})=>{if(q==null)return null;const c=q>=0.8?V.success:q>=0.5?V.warn:V.danger;return <span title={`${(q*100).toFixed(0)}%`} style={{display:"inline-block",width:s,height:s,borderRadius:"50%",background:c,opacity:0.8}}/>;};
// Tier badge
const TierBadge=({tier,sm})=>{const t=TIERS[tier]||TIERS.balanced;return <Pill color={t.color} sm={sm}>{t.icon} {t.label}</Pill>;};

// ── TOPOLOGY GRAPH ──────────────────────────────────────
const TopoGraph=({topo})=>{const[hov,setHov]=useState(null);if(!topo)return <div style={{padding:20,color:V.fgDim,fontSize:9.5,fontFamily:F.mono,textAlign:"center"}}>NO TOPOLOGY</div>;return <svg viewBox="0 0 400 270" style={{width:"100%",height:"100%"}}><defs><marker id="arr" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="5" markerHeight="3.5" orient="auto"><path d="M0,0 L10,3 L0,6" fill={V.fgDim}/></marker></defs>{topo.edges.map((e,i)=>{const a=topo.nodes.find(n=>n.id===e.from),b=topo.nodes.find(n=>n.id===e.to);if(!a||!b)return null;const s=e.w>1.2,isH=hov===e.from||hov===e.to;return <g key={i}>{s&&<line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={V.accent} strokeWidth={e.w*2} opacity={0.06}/>}<line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={isH?"rgba(255,255,255,0.22)":s?V.accent:`rgba(255,255,255,0.08)`} strokeWidth={isH?e.w+0.5:e.w} markerEnd="url(#arr)" opacity={s?0.6:0.4} strokeDasharray={e.w<0.8?"4 3":"none"}/></g>})}{topo.nodes.map(n=>{const isH=hov===n.id;return <g key={n.id} onMouseEnter={()=>setHov(n.id)} onMouseLeave={()=>setHov(null)} style={{cursor:"pointer"}}><rect x={n.x-32} y={n.y-13} width={64} height={26} rx={6} fill={isH?`${n.c}15`:V.surface} stroke={`${n.c}${isH?"50":"20"}`} strokeWidth={0.8}/><text x={n.x} y={n.y+3} textAnchor="middle" fill={isH?n.c:V.fgMuted} style={{fontFamily:F.mono,fontSize:7.5,letterSpacing:"0.12em",fontWeight:600}}>{n.label}</text></g>})}</svg>;};

// ── COLONY CHAT (per-colony, multi-caller) ──────────────
const ColonyChat=({colonyId,colonyName:cName,status,style:sx})=>{
  const[input,setInput]=useState("");const[msgs,setMsgs]=useState(COLONY_CHATS[colonyId]||[]);const ref=useRef(null);
  useEffect(()=>{ref.current?.scrollTo({top:ref.current.scrollHeight,behavior:"smooth"});},[msgs.length]);
  const send=()=>{if(!input.trim())return;const ts=new Date().toLocaleTimeString("en-US",{hour12:false,hour:"2-digit",minute:"2-digit"});
    setMsgs(p=>[...p,{role:"operator",text:input,ts}]);setInput("");
    setTimeout(()=>setMsgs(p=>[...p,{role:"queen",text:"Directive queued.",ts:new Date().toLocaleTimeString("en-US",{hour12:false,hour:"2-digit",minute:"2-digit"}),source:"queen"}]),400);};
  const kindColor={metric:V.purple,route:V.warn,pheromone:V.accent,merge:V.secondary,service:V.service,spawn:V.success};
  return(
    <div style={{display:"flex",flexDirection:"column",background:V.surface,borderRadius:10,border:`1px solid ${status==="service"?V.service+"25":V.border}`,overflow:"hidden",...sx}}>
      <div style={{display:"flex",alignItems:"center",borderBottom:`1px solid ${V.border}`,padding:"7px 10px",gap:6}}>
        <span style={{fontSize:10,color:status==="service"?V.service:V.accent}}>{status==="service"?"◆":"⬡"}</span>
        <span style={{fontSize:10.5,fontFamily:F.display,fontWeight:600,color:V.fg,flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{cName}</span>
        {status==="service"?<Pill color={V.service} sm>service</Pill>:<Pill color={V.fgDim} sm>colony</Pill>}
      </div>
      <div ref={ref} style={{flex:1,overflow:"auto",padding:"4px 0"}}>
        {msgs.map((m,i)=>(
          <div key={i} style={{padding:m.role==="event"?"2px 10px":"4px 10px"}}>
            {m.role==="event"?(
              <div style={{display:"flex",alignItems:"center",gap:4,fontSize:9.5}}>
                <span style={{width:3,height:3,borderRadius:m.kind==="service"?1:"50%",background:kindColor[m.kind]||V.fgDim,flexShrink:0}}/>
                <span style={{fontFamily:F.mono,fontSize:7.5,color:V.fgDim}}>{m.ts}</span>
                <span style={{color:V.fgDim,fontSize:9.5}}>{m.text}</span>
              </div>
            ):m.role==="colony"?(
              // Inbound from another colony
              <div style={{background:`${V.service}08`,borderRadius:6,padding:"5px 8px",border:`1px solid ${V.service}15`}}>
                <div style={{display:"flex",alignItems:"center",gap:4,marginBottom:2}}>
                  <span style={{fontSize:7,color:V.service}}>⬡</span>
                  <span style={{fontFamily:F.mono,fontSize:7.5,color:V.service,fontWeight:600,letterSpacing:"0.06em"}}>{m.source}</span>
                  <span style={{fontFamily:F.mono,fontSize:7,color:V.fgDim}}>{m.ts}</span>
                </div>
                <div style={{fontSize:11,lineHeight:1.5,color:V.fg,paddingLeft:12}}>{m.text}</div>
              </div>
            ):(
              <div>
                <div style={{display:"flex",alignItems:"center",gap:4,marginBottom:2}}>
                  {m.role==="queen"&&<span style={{fontSize:7,color:V.accent}}>♛</span>}
                  <span style={{fontFamily:F.mono,fontSize:7.5,color:m.role==="queen"?V.accent:V.fgDim,fontWeight:600,letterSpacing:"0.06em",textTransform:"uppercase"}}>{m.role==="queen"?"Queen":"Operator"}</span>
                  <span style={{fontFamily:F.mono,fontSize:7,color:V.fgDim}}>{m.ts}</span>
                  {m.parsed&&<Pill color={V.warn} sm>parsed from intent</Pill>}
                </div>
                <div style={{fontSize:11.5,lineHeight:1.5,color:m.role==="queen"?V.fg:"rgba(237,237,240,0.8)",paddingLeft:m.role==="queen"?12:0}}>{m.text}</div>
              </div>
            )}
          </div>
        ))}
      </div>
      <div style={{padding:"5px 8px",borderTop:`1px solid ${V.border}`,display:"flex",gap:5}}>
        <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&send()}
          placeholder={status==="service"?"Message this service...":"Intervene in this colony..."}
          style={{flex:1,background:V.void,border:`1px solid ${V.border}`,borderRadius:999,color:V.fg,fontFamily:F.body,fontSize:11,padding:"6px 12px",outline:"none"}}
          onFocus={e=>e.target.style.borderColor=`${V.accent}40`} onBlur={e=>e.target.style.borderColor=V.border}/>
        <Btn sm onClick={send}>Send</Btn>
      </div>
    </div>
  );
};

// ── GLOBAL QUEEN CHAT ───────────────────────────────────
const QueenChat=({style:sx,threads,activeId,onSwitch,chatFull,onToggleFull})=>{
  const[input,setInput]=useState("");const[lt,setLt]=useState(threads);const ref=useRef(null);const active=lt.find(t=>t.id===activeId)||lt[0];
  useEffect(()=>{ref.current?.scrollTo({top:ref.current.scrollHeight,behavior:"smooth"});},[active?.messages?.length]);
  const send=()=>{if(!input.trim()||!active)return;const ts=new Date().toLocaleTimeString("en-US",{hour12:false,hour:"2-digit",minute:"2-digit"});
    setLt(p=>p.map(t=>t.id===active.id?{...t,messages:[...t.messages,{role:"operator",text:input,ts}]}:t));setInput("");
    setTimeout(()=>setLt(p=>p.map(t=>t.id===active.id?{...t,messages:[...t.messages,{role:"queen",text:"Acknowledged. Adjusting fleet strategy.",ts:new Date().toLocaleTimeString("en-US",{hour12:false,hour:"2-digit",minute:"2-digit"})}]}:t)),500);};
  return(
    <div style={{display:"flex",flexDirection:"column",background:V.surface,borderRadius:10,border:`1px solid ${V.border}`,overflow:"hidden",...sx}}>
      <div style={{display:"flex",alignItems:"center",borderBottom:`1px solid ${V.border}`,padding:"0 4px",minHeight:36,overflow:"auto",gap:0}}>
        {lt.map(t=><div key={t.id} onClick={()=>onSwitch(t.id)} style={{padding:"7px 10px",cursor:"pointer",fontSize:10.5,fontFamily:F.body,fontWeight:500,whiteSpace:"nowrap",color:t.id===active?.id?V.fg:V.fgDim,borderBottom:t.id===active?.id?`2px solid ${V.accent}`:"2px solid transparent",display:"flex",alignItems:"center",gap:4}}>
          {t.permanent&&<span style={{fontSize:9,color:V.accent,filter:`drop-shadow(0 0 3px ${V.accentGlow})`}}>♛</span>}
          {t.name}
        </div>)}
        <div onClick={()=>{const id=`qt-${Date.now()}`;setLt(p=>[...p,{id,name:`thread ${p.length}`,permanent:false,messages:[]}]);onSwitch(id);}} style={{padding:"7px 6px",cursor:"pointer",fontSize:13,color:V.fgDim,flexShrink:0}} title="New thread">+</div>
        {onToggleFull&&<div onClick={onToggleFull} style={{padding:"7px 6px",cursor:"pointer",fontSize:11,color:V.fgDim,flexShrink:0,marginLeft:"auto"}} title={chatFull?"Minimize":"Maximize"}>{chatFull?"▫":"▣"}</div>}
      </div>
      <div ref={ref} style={{flex:1,overflow:"auto",padding:"6px 0"}}>{active?.messages.map((m,i)=>(<div key={i} style={{padding:m.role==="event"?"2px 12px":"5px 12px"}}>
        {m.role==="event"?(<div style={{display:"flex",alignItems:"center",gap:4,fontSize:9.5}}>
          <span style={{width:3,height:3,borderRadius:"50%",background:({spawn:V.success,merge:V.secondary,metric:V.purple})[m.kind]||V.fgDim,flexShrink:0}}/>
          <span style={{fontFamily:F.mono,fontSize:7.5,color:V.fgDim}}>{m.ts}</span>
          <span style={{color:V.fgDim,fontSize:9.5}}>{m.text}</span>
        </div>):(<div>
          <div style={{display:"flex",alignItems:"center",gap:4,marginBottom:2}}>{m.role==="queen"&&<span style={{fontSize:7,color:V.accent}}>♛</span>}<span style={{fontFamily:F.mono,fontSize:7.5,color:m.role==="queen"?V.accent:V.fgDim,fontWeight:600,letterSpacing:"0.06em",textTransform:"uppercase"}}>{m.role==="queen"?"Queen":"Operator"}</span><span style={{fontFamily:F.mono,fontSize:7,color:V.fgDim}}>{m.ts}</span></div>
          <div style={{fontSize:12,lineHeight:1.55,color:m.role==="queen"?V.fg:"rgba(237,237,240,0.8)",paddingLeft:m.role==="queen"?12:0}}>{m.text}</div>
        </div>)}
      </div>))}</div>
      <div style={{padding:"6px 8px",borderTop:`1px solid ${V.border}`,display:"flex",gap:5}}>
        <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&send()} placeholder={active?.permanent?"Talk to the Queen (full system context)...":"Thread-scoped direction..."}
          style={{flex:1,background:V.void,border:`1px solid ${V.border}`,borderRadius:999,color:V.fg,fontFamily:F.body,fontSize:12,padding:"7px 14px",outline:"none"}} onFocus={e=>e.target.style.borderColor=`${V.accent}40`} onBlur={e=>e.target.style.borderColor=V.border}/>
        <Btn sm onClick={send}>Send</Btn>
      </div>
    </div>
  );
};

// ── TREE NAV ────────────────────────────────────────────
const TreeNav=({selected,onSelect,expanded,onToggle})=>{
  const icons={workspace:"▣",thread:"▷",colony:"⬡"};
  const renderNode=(node,d=0)=>{const sel=selected===node.id;const exp=expanded[node.id]!==false;const has=node.children?.length>0;
    const isService=node.status==="service";
    return <div key={node.id}><div onClick={()=>onSelect(node.id)} style={{padding:`4px 8px 4px ${6+d*12}px`,cursor:"pointer",display:"flex",alignItems:"center",gap:4,background:sel?`${V.accent}0C`:"transparent",borderLeft:sel?`2px solid ${isService?V.service:V.accent}`:"2px solid transparent",fontSize:11,fontFamily:F.mono}}>
      {has?<span onClick={e=>{e.stopPropagation();onToggle(node.id);}} style={{color:V.fgDim,fontSize:6,width:8,textAlign:"center",cursor:"pointer"}}>{exp?"▼":"▶"}</span>:<span style={{width:8}}/>}
      <span style={{color:isService?V.service:({workspace:V.accent,thread:V.blue}[node.type]||V.fgMuted),fontSize:9}}>{isService?"◆":icons[node.type]}</span>
      <span style={{color:sel?V.fg:V.fgMuted,overflow:"hidden",textOverflow:"ellipsis",flex:1,fontSize:10.5}}>{cn(node)}</span>
      {node.status&&<Dot status={node.status} size={4}/>}{node.quality!=null&&<QualityDot q={node.quality} s={4}/>}
    </div>{has&&exp&&node.children.map(c=>renderNode(c,d+1))}</div>;};
  return <div style={{paddingTop:1}}>{TREE.map(n=>renderNode(n))}</div>;
};

// ═══════════════════════════════════════════════════════════
// VIEWS
// ═══════════════════════════════════════════════════════════

// ── QUEEN OVERVIEW ──────────────────────────────────────
const ViewQueen=({approvals,onApprove,onReject,onNav,queenThreads,activeQT,onSwitchQT,onCreateColony})=>{
  const cols=allColonies(TREE);const running=cols.filter(c=>c.status==="running");const services=cols.filter(c=>c.status==="service");
  const totalCost=cols.reduce((a,c)=>a+(c.cost||0),0);
  const[chatFull,setChatFull]=useState(false);
  return(
    <div style={{display:"flex",gap:chatFull?0:16,height:"100%",overflow:"hidden"}}>
      {!chatFull&&<div style={{flex:1,overflow:"auto",paddingRight:4}}>
        <div style={{marginBottom:16}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:5}}>
            <span style={{fontSize:22,filter:`drop-shadow(0 0 8px ${V.accentGlow})`}}>♛</span>
            <h1 style={{fontFamily:F.display,fontSize:22,fontWeight:700,color:V.fg,letterSpacing:"-0.04em",margin:0}}><GradientText>Supercolony</GradientText></h1>
            <Pill color={V.success} glow><Dot status="running" size={4}/> {running.length} active</Pill>
            {services.length>0&&<Pill color={V.service} glow><Dot status="service" size={4}/> {services.length} service{services.length>1?"s":""}</Pill>}
          </div>
          <p style={{fontSize:11,color:V.fgMuted,margin:0}}>{cols.length} colonies · <span style={{fontFamily:F.mono,color:V.accent}}>${totalCost.toFixed(2)}</span> · <span style={{fontFamily:F.mono,color:V.secondary}}>{SKILLS.length} skills</span> · <span style={{fontFamily:F.mono}}>{KG_NODES.length} entities</span></p>
        </div>
        {/* Resources */}
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr 1fr",gap:8,marginBottom:14}}>
          <Glass style={{padding:10}}><Meter label="Budget" value={totalCost} max={7} unit="$" compact/></Glass>
          <Glass style={{padding:10}}><Meter label="VRAM" value={21.8} max={32} unit=" GB" color={V.purple} compact/></Glass>
          <Glass style={{padding:10}}><Meter label="Anthropic" value={0.62} max={10} unit="$" color={V.accent} compact/></Glass>
          <Glass style={{padding:10}}><Meter label="Gemini" value={0.04} max={5} unit="$" color={V.blue} compact/></Glass>
        </div>
        {/* Approvals */}
        {approvals.length>0&&<div style={{marginBottom:14}}><SLabel>Pending Approvals</SLabel>
          {approvals.map(a=><Glass key={a.id} featured style={{padding:12,marginBottom:6,display:"flex",alignItems:"center",gap:10}}>
            <div style={{width:3,height:28,borderRadius:2,background:V.accent,flexShrink:0}}/>
            <div style={{flex:1}}><div style={{fontSize:9,fontFamily:F.mono,color:V.accent,fontWeight:600,letterSpacing:"0.08em",textTransform:"uppercase"}}>{a.type}</div><div style={{fontSize:11.5,color:V.fg}}>{a.agent} → {a.detail}</div></div>
            <Btn v="success" sm onClick={()=>onApprove(a.id)}>Approve</Btn><Btn v="danger" sm onClick={()=>onReject(a.id)}>Deny</Btn>
          </Glass>)}
        </div>}
        {/* Services */}
        {services.length>0&&<div style={{marginBottom:14}}><SLabel>Active Services</SLabel>
          <div style={{display:"flex",gap:8}}>{services.map(s=><Glass key={s.id} hover onClick={()=>onNav(s.id)} style={{padding:10,flex:1,borderLeft:`3px solid ${V.service}`}}>
            <div style={{display:"flex",alignItems:"center",gap:5,marginBottom:3}}><Dot status="service" size={5}/><span style={{fontFamily:F.display,fontSize:11.5,fontWeight:600,color:V.fg}}>{cn(s)}</span><QualityDot q={s.quality} s={5}/></div>
            <div style={{fontSize:9,fontFamily:F.mono,color:V.fgDim}}>{(s.agents||[]).length} agents idle · {s.skillsExtracted||0} skills · callable</div>
          </Glass>)}</div>
        </div>}
        {/* Quick Launch */}
        <div style={{marginBottom:14}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}><SLabel sx={{marginBottom:0}}>Quick Launch</SLabel><Btn v="primary" sm onClick={onCreateColony}>+ New Colony</Btn></div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:8}}>
            {TEMPLATES.slice(0,3).map(t=><Glass key={t.template_id} hover onClick={onCreateColony} style={{padding:10}}>
              <div style={{display:"flex",alignItems:"center",gap:4,marginBottom:3}}><span style={{fontFamily:F.display,fontSize:11,fontWeight:600,color:V.fg}}>{t.name}</span><span style={{fontFamily:F.mono,fontSize:8,color:V.fgDim,marginLeft:"auto"}}>{t.uses}×</span></div>
              <div style={{display:"flex",gap:3,marginBottom:3}}>{t.castes.map(({id:cid,tier})=>{const c=CASTES.find(x=>x.id===cid);const ti=TIERS[tier];return c?<span key={cid} style={{display:"inline-flex",alignItems:"center",gap:2}}><span style={{fontSize:10}}>{c.icon}</span><span style={{fontSize:7,color:ti.color}}>{ti.icon}</span></span>:null;})}</div>
              <div style={{display:"flex",gap:6,fontSize:8,fontFamily:F.mono}}><span style={{color:V.success}}>{(t.successRate*100).toFixed(0)}%</span><span style={{color:V.fgDim}}>~${t.avgCost.toFixed(2)}</span></div>
            </Glass>)}
          </div>
        </div>
        {/* Colonies */}
        {TREE.map(ws=><div key={ws.id} style={{marginBottom:14}}>
          <SLabel><span style={{color:V.accent}}>▣</span> {ws.name}</SLabel>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
            {allColonies([ws]).map(c=><Glass key={c.id} hover onClick={()=>onNav(c.id)} style={{padding:12,borderLeft:c.status==="service"?`3px solid ${V.service}`:"3px solid transparent"}}>
              <div style={{display:"flex",alignItems:"center",gap:5,marginBottom:3}}><Dot status={c.status} size={5}/><span style={{fontFamily:F.display,fontSize:12,fontWeight:600,color:V.fg}}>{cn(c)}</span>{c.quality!=null&&<QualityDot q={c.quality}/>}</div>
              {c.task&&<div style={{fontSize:10,color:V.fgMuted,marginBottom:4,lineHeight:1.35,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{c.task}</div>}
              <div style={{display:"flex",gap:5,fontSize:9.5,fontFamily:F.mono,color:V.fgMuted,fontFeatureSettings:'"tnum"',alignItems:"center",flexWrap:"wrap"}}>
                {c.status!=="service"&&<span>R{c.round}/{c.maxRounds}</span>}
                <span>{(c.agents||[]).length} agents{c.status==="service"?" (idle)":""}</span>
                {c.convergence>0&&<><span style={{color:c.convergence>0.8?V.success:V.fgMuted}}>conv {(c.convergence*100).toFixed(0)}%</span><Sparkline data={c.convergenceHistory}/></>}
                <span style={{color:V.accent}}>${(c.cost||0).toFixed(2)}</span>
                {(c.services||[]).length>0&&<Pill color={V.service} sm>{c.services.length} svc</Pill>}
                {/* Agent tier dots */}
                <span style={{display:"flex",gap:1,marginLeft:"auto"}}>{(c.agents||[]).map((a,i)=>{const ti=TIERS[a.tier]||TIERS.balanced;return <span key={i} style={{width:5,height:5,borderRadius:"50%",background:ti.color}} title={`${a.name}: ${ti.label}`}/>;})}</span>
              </div>
            </Glass>)}
          </div>
        </div>)}
      </div>}
      <QueenChat style={{width:chatFull?"100%":300,flexShrink:chatFull?undefined:0}} threads={queenThreads} activeId={activeQT} onSwitch={onSwitchQT} chatFull={chatFull} onToggleFull={()=>setChatFull(!chatFull)}/>
    </div>
  );
};

// ── COLONY DETAIL ───────────────────────────────────────
const ViewColony=({colony})=>{
  if(!colony)return null;const[expR,setExpR]=useState(null);const[showCode,setShowCode]=useState(null);
  const isService=colony.status==="service";const svcColonies=(colony.services||[]).map(id=>findNode(TREE,id)).filter(Boolean);
  return(
    <div style={{display:"flex",gap:16,height:"100%",overflow:"hidden"}}>
      <div style={{flex:1,overflow:"auto",paddingRight:4}}>
        {/* Header */}
        <div style={{marginBottom:8}}>
          <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:3}}>
            <span style={{fontSize:14,color:isService?V.service:V.fg}}>{isService?"◆":"⬡"}</span>
            <span style={{fontFamily:F.display,fontSize:18,fontWeight:700,color:V.fg,letterSpacing:"-0.03em"}}>{cn(colony)}</span>
            <Pill color={isService?V.service:colony.status==="running"?V.success:colony.status==="completed"?V.secondary:V.warn} glow><Dot status={colony.status} size={4}/> {colony.status}</Pill>
            {colony.quality!=null&&<Pill color={colony.quality>=0.8?V.success:V.warn} sm>quality {(colony.quality*100).toFixed(0)}%</Pill>}
          </div>
          <div style={{fontSize:9,fontFamily:F.mono,color:V.fgDim,marginBottom:4}}>{colony.id}</div>
          {colony.task&&<p style={{fontSize:11,color:V.fgMuted,margin:0,marginBottom:8,lineHeight:1.4}}>{colony.task}</p>}
        </div>
        {/* Service banner */}
        {isService&&<Glass featured style={{padding:12,marginBottom:12,borderLeft:`3px solid ${V.service}`}}>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            <span style={{fontSize:16,color:V.service}}>◆</span>
            <div><div style={{fontSize:11.5,color:V.fg,fontWeight:500}}>This colony is a callable service</div>
              <div style={{fontSize:10,color:V.fgMuted}}>Other colonies and external agents can query it through the chat interface. Tools, skills, and knowledge graph are retained.</div></div>
            <Btn v="danger" sm sx={{marginLeft:"auto"}}>Deactivate</Btn>
          </div>
        </Glass>}
        {/* Attached services */}
        {svcColonies.length>0&&<div style={{marginBottom:12}}><SLabel>Attached Services</SLabel>
          <div style={{display:"flex",gap:6}}>{svcColonies.map(s=><Glass key={s.id} hover style={{padding:8,display:"flex",alignItems:"center",gap:6,borderLeft:`2px solid ${V.service}`}}>
            <span style={{fontSize:10,color:V.service}}>◆</span><span style={{fontSize:10.5,fontWeight:500,color:V.fg}}>{cn(s)}</span>
            <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>{s.skillsExtracted||0} skills</span>
          </Glass>)}</div>
        </div>}
        {/* Metrics + Topology */}
        {!isService&&<div style={{display:"grid",gridTemplateColumns:"3fr 2fr",gap:10,marginBottom:12}}>
          <Glass style={{padding:0,overflow:"hidden"}}>
            <div style={{padding:"6px 12px",borderBottom:`1px solid ${V.border}`,fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.12em",textTransform:"uppercase",fontWeight:600}}>Topology · R{colony.round}/{colony.maxRounds}</div>
            <div style={{height:180}}><TopoGraph topo={colony.topology}/></div>
          </Glass>
          <Glass style={{padding:12}}>
            <Meter label="Convergence" value={colony.convergence} max={1} color={colony.convergence>0.8?V.success:V.accent} compact/>
            {colony.convergenceHistory?.length>1&&<div style={{display:"flex",alignItems:"center",gap:6,marginBottom:6}}><span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>trend</span><Sparkline data={colony.convergenceHistory} w={80} h={20}/></div>}
            <Meter label="Cost" value={colony.cost} max={colony.budget||5} unit="$" compact/>
          </Glass>
        </div>}
        {/* Agents with tier badges */}
        <SLabel>Agents</SLabel>
        <Glass style={{padding:0,marginBottom:12,overflow:"hidden"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontFamily:F.mono,fontSize:10.5}}>
            <thead><tr style={{borderBottom:`1px solid ${V.border}`}}>{["","Agent","Caste","Tier","Model","Tokens","Status"].map(h=><th key={h} style={{padding:"5px 8px",textAlign:"left",color:V.fgDim,fontWeight:600,fontSize:7.5,letterSpacing:"0.1em",textTransform:"uppercase"}}>{h}</th>)}</tr></thead>
            <tbody>{(colony.agents||[]).map((a,i)=>{const caste=CASTES.find(c=>c.id===a.caste);const ti=TIERS[a.tier]||TIERS.balanced;
              return <tr key={i} style={{borderBottom:i<colony.agents.length-1?`1px solid ${V.border}`:"none"}}>
                <td style={{padding:"5px 8px"}}><Dot status={a.status} size={5}/></td>
                <td style={{padding:"5px 8px",color:V.fg,fontWeight:500}}>{a.name}</td>
                <td style={{padding:"5px 8px"}}><span style={{fontSize:10}}>{caste?.icon}</span></td>
                <td style={{padding:"5px 8px"}}><span style={{fontSize:9,color:ti.color}}>{ti.icon} {ti.label}</span></td>
                <td style={{padding:"5px 8px",color:V.fgMuted,fontSize:9.5}}><span style={{display:"inline-flex",alignItems:"center",gap:3}}><span style={{width:4,height:4,borderRadius:"50%",background:PROV_COLOR[providerOf(a.model)]||V.fgDim}}/>{a.model}</span></td>
                <td style={{padding:"5px 8px",color:V.fgMuted,fontFeatureSettings:'"tnum"'}}>{a.tokens>0?`${(a.tokens/1000).toFixed(1)}k`:"—"}</td>
                <td style={{padding:"5px 8px"}}><Pill color={a.status==="active"?V.success:a.status==="done"||a.status==="idle"?V.secondary:V.warn} sm>{a.status}</Pill></td>
              </tr>})}</tbody>
          </table>
        </Glass>
        {/* Actions */}
        <div style={{display:"flex",gap:6,marginBottom:12}}>
          {!isService&&<><Btn v="secondary" sm>Extend Rounds</Btn><Btn v="secondary" sm>Save Template</Btn><Btn v="danger" sm>Kill</Btn></>}
          {colony.status==="completed"&&<Btn v="success" sm onClick={()=>{}}>Activate as Service</Btn>}
          {isService&&<Btn v="secondary" sm>View Skills ({colony.skillsExtracted||0})</Btn>}
        </div>
        {/* Round History with sandbox */}
        {colony.rounds?.length>0&&<><SLabel>Round History</SLabel><Glass style={{padding:12}}>
          {colony.rounds.map((r,ri)=>{const pc=r.phase==="Goal"?V.accent:r.phase==="Route"?V.warn:V.blue;const isExp=expR===ri;
            return <div key={ri} style={{paddingLeft:10,borderLeft:`2px solid ${pc}`,marginBottom:ri<colony.rounds.length-1?10:0}}>
              <div onClick={()=>setExpR(isExp?null:ri)} style={{display:"flex",alignItems:"center",gap:5,marginBottom:3,cursor:"pointer"}}>
                <span style={{fontFamily:F.display,fontSize:11,fontWeight:700,color:pc}}>R{r.r}</span>
                <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>{r.phase}</span>
                {r.convergence!=null&&<span style={{fontSize:8,fontFamily:F.mono,color:V.fgMuted}}>conv {(r.convergence*100).toFixed(0)}%</span>}
                <span style={{fontSize:8,fontFamily:F.mono,color:V.accent}}>${(r.cost||0).toFixed(2)}</span>
                {r.agents.some(a=>(a.execs||[]).length>0)&&<Pill color={V.purple} sm>⟨/⟩ {r.agents.reduce((a,ag)=>a+(ag.execs||[]).length,0)}</Pill>}
                <span style={{fontSize:8,color:V.fgDim,marginLeft:"auto"}}>{isExp?"▲":"▼"}</span>
              </div>
              {isExp?r.agents.map((a,ai)=><div key={ai} style={{padding:"4px 0 4px 6px",marginBottom:3}}>
                <div style={{display:"flex",alignItems:"center",gap:5,fontSize:9.5}}><Dot status={a.s} size={4}/><span style={{color:V.fg,fontWeight:500}}>{a.n}</span><span style={{fontSize:9,color:V.fgDim}}>{a.m}</span>{a.t>0&&<span style={{fontSize:9,color:V.fgDim,marginLeft:"auto",fontFeatureSettings:'"tnum"'}}>{(a.t/1000).toFixed(1)}k</span>}</div>
                {a.output&&<div style={{fontSize:9.5,color:V.fgMuted,lineHeight:1.4,marginTop:2,paddingLeft:14}}>{a.output}</div>}
                {a.tools?.length>0&&<div style={{display:"flex",gap:3,marginTop:2,paddingLeft:14}}>{a.tools.map(t=><Pill key={t} color={t==="code_execute"?V.purple:V.fgDim} sm>{t}</Pill>)}</div>}
                {(a.execs||[]).map((ex,ei)=>{const ok=ex.exit_code===0;return <div key={ei} style={{margin:"4px 0 0 14px",padding:6,background:V.recessed,borderRadius:5,border:`1px solid ${ok?V.border:V.danger+"25"}`}}>
                  <div style={{display:"flex",alignItems:"center",gap:5,marginBottom:3}}><Pill color={ok?V.success:V.danger} sm>{ok?"exit 0":`exit ${ex.exit_code}`}</Pill><Pill color={V.purple} sm>{ex.tier}</Pill><span style={{fontFamily:F.mono,fontSize:8,color:V.fgDim}}>{ex.duration_ms}ms · {ex.mem_mb}MB</span>{ex.error&&<Pill color={V.danger} sm>{ex.error}</Pill>}</div>
                  <div onClick={()=>setShowCode(showCode===`${ri}-${ai}-${ei}`?null:`${ri}-${ai}-${ei}`)} style={{cursor:"pointer",fontSize:8,fontFamily:F.mono,color:V.fgDim}}>{showCode===`${ri}-${ai}-${ei}`?"▼ code":"▶ code"}</div>
                  {showCode===`${ri}-${ai}-${ei}`&&<pre style={{fontFamily:F.mono,fontSize:9,color:V.fgMuted,background:V.void,padding:4,borderRadius:3,margin:"3px 0",whiteSpace:"pre-wrap"}}>{ex.code}</pre>}
                  {ex.stdout&&<pre style={{fontFamily:F.mono,fontSize:9,color:V.success,margin:0,whiteSpace:"pre-wrap"}}>{ex.stdout}</pre>}
                  {ex.stderr&&<pre style={{fontFamily:F.mono,fontSize:9,color:V.danger,margin:0,whiteSpace:"pre-wrap"}}>{ex.stderr}</pre>}
                </div>})}
              </div>):r.agents.map((a,ai)=><div key={ai} style={{display:"flex",alignItems:"center",gap:5,padding:"1px 0 1px 4px",fontSize:9.5}}><Dot status={a.s} size={4}/><span style={{color:V.fgMuted,width:55}}>{a.n}</span><span style={{color:V.fgDim,fontSize:9}}>{a.m}</span>{(a.execs||[]).length>0&&<Pill color={V.purple} sm>{a.execs.length}⟨/⟩</Pill>}{a.t>0&&<span style={{color:V.fgDim,fontSize:9,marginLeft:"auto"}}>{(a.t/1000).toFixed(1)}k</span>}</div>)}
            </div>;
          })}
        </Glass></>}
      </div>
      <ColonyChat colonyId={colony.id} colonyName={cn(colony)} status={colony.status} style={{width:280,flexShrink:0}}/>
    </div>
  );
};

// ── COLONY CREATOR (Describe → Suggest → Configure → Launch) ─
const ColonyCreator=({onClose})=>{
  const[step,setStep]=useState(1);const[obj,setObj]=useState("");
  const[team,setTeam]=useState([{caste:"coder",tier:"balanced"},{caste:"reviewer",tier:"balanced"}]);
  const[suggestion,setSuggestion]=useState(null);const[budget,setBudget]=useState(2.0);const[maxR,setMaxR]=useState(10);const[strategy,setStrategy]=useState("stigmergic");
  const[attachedServices,setAttachedServices]=useState([]);
  const availableServices=allColonies(TREE).filter(c=>c.status==="service");

  const suggestTeam=()=>{if(!obj.trim())return;
    // Simulate POST /api/v1/suggest-team
    setTimeout(()=>setSuggestion({
      castes:[{caste:"coder",tier:"heavy",reason:"Implementation task — cloud routing for Execute phase"},{caste:"reviewer",tier:"light",reason:"Code review — local model sufficient"},{caste:"researcher",tier:"balanced",reason:"May need API documentation lookup"}],
      services:availableServices.length>0?[{id:availableServices[0].id,name:cn(availableServices[0]),reason:"Has relevant dependency analysis and vulnerability data"}]:[],
      templates:[TEMPLATES[0],TEMPLATES[3]],
    }),600);
    setStep(2);
  };
  const applyTeam=(castes,services)=>{setTeam(castes.map(c=>({caste:c.caste,tier:c.tier})));setAttachedServices(services.map(s=>s.id));setStep(3);};
  const toggleCaste=(id)=>{const exists=team.find(t=>t.caste===id);if(exists)setTeam(team.filter(t=>t.caste!==id));else setTeam([...team,{caste:id,tier:"balanced"}]);};
  const setTier=(caste,tier)=>setTeam(team.map(t=>t.caste===caste?{...t,tier}:t));
  const toggleService=(id)=>setAttachedServices(p=>p.includes(id)?p.filter(x=>x!==id):[...p,id]);
  const estCost=team.reduce((a,t)=>{const ti=TIERS[t.tier];return a+(ti.costHint==="free"?0:t.tier==="heavy"?0.08:0.02)*maxR;},0);

  return(<div style={{position:"fixed",inset:0,zIndex:100,display:"flex",alignItems:"center",justifyContent:"center",background:"rgba(5,5,8,0.85)",backdropFilter:"blur(20px)"}}>
    <div style={{width:640,maxHeight:"85vh",background:V.surface,border:`1px solid ${V.border}`,borderRadius:14,overflow:"hidden",display:"flex",flexDirection:"column"}}>
      <div style={{padding:"12px 18px",borderBottom:`1px solid ${V.border}`,display:"flex",alignItems:"center",gap:8}}>
        <span style={{fontSize:14,color:V.accent}}>⬡</span><span style={{fontFamily:F.display,fontSize:15,fontWeight:600,color:V.fg}}>New Colony</span>
        <div style={{display:"flex",gap:3,marginLeft:"auto"}}>{["Describe","Suggest","Configure","Launch"].map((s,i)=><span key={i} style={{padding:"2px 8px",borderRadius:999,fontSize:8,fontFamily:F.mono,fontWeight:600,color:step===i+1?V.fg:V.fgDim,background:step===i+1?V.accentMuted:"transparent",border:step>i+1?`1px solid ${V.success}30`:step===i+1?`1px solid ${V.accent}30`:`1px solid ${V.border}`}}>{s}</span>)}</div>
        <span onClick={onClose} style={{cursor:"pointer",color:V.fgDim,fontSize:14,marginLeft:8}}>✕</span>
      </div>
      <div style={{flex:1,overflow:"auto",padding:18}}>
        {/* STEP 1: DESCRIBE */}
        {step===1&&<>
          <SLabel>What should the colony accomplish?</SLabel>
          <textarea value={obj} onChange={e=>setObj(e.target.value)} placeholder="Describe the objective — the Queen will recommend a team..." style={{width:"100%",height:90,background:V.void,border:`1px solid ${V.border}`,borderRadius:8,color:V.fg,fontFamily:F.body,fontSize:13,padding:12,outline:"none",resize:"vertical",lineHeight:1.5}}/>
          <div style={{marginTop:12}}><SLabel>Or start from template</SLabel>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:6}}>{TEMPLATES.slice(0,6).map(t=><Glass key={t.template_id} hover onClick={()=>{setObj(t.desc);setTeam(t.castes);setBudget(t.budget);setMaxR(t.maxRounds);setStrategy(t.strategy);setStep(3);}} style={{padding:8}}>
              <div style={{fontSize:10,fontWeight:600,color:V.fg,marginBottom:2}}>{t.name}</div>
              <div style={{display:"flex",gap:2,marginBottom:2}}>{t.castes.map(({id:cid,tier})=>{const c=CASTES.find(x=>x.id===cid);const ti=TIERS[tier];return c?<span key={cid} style={{display:"flex",alignItems:"center",gap:1}}><span style={{fontSize:9}}>{c.icon}</span><span style={{fontSize:7,color:ti.color}}>{ti.icon}</span></span>:null;})}</div>
              <div style={{fontSize:8,fontFamily:F.mono,color:V.success}}>{(t.successRate*100).toFixed(0)}%</div>
            </Glass>)}</div>
          </div>
        </>}
        {/* STEP 2: SUGGEST */}
        {step===2&&<>
          {!suggestion?<div style={{textAlign:"center",padding:20}}><div style={{display:"inline-block",width:20,height:20,border:`2px solid ${V.accent}`,borderTopColor:"transparent",borderRadius:"50%",animation:"spin 0.8s linear infinite"}}/><div style={{fontSize:10,color:V.fgMuted,marginTop:8}}>Queen is analyzing the objective...</div></div>
          :<>
            <SLabel>Suggested Team</SLabel>
            <Glass style={{padding:12,marginBottom:12}}>
              {suggestion.castes.map(s=>{const c=CASTES.find(x=>x.id===s.caste);const ti=TIERS[s.tier];return c?<div key={s.caste} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:`1px solid ${V.border}`}}>
                <span style={{fontSize:13}}>{c.icon}</span>
                <span style={{fontSize:11,color:V.fg,fontWeight:500,width:80}}>{c.name}</span>
                <TierBadge tier={s.tier} sm/>
                <span style={{fontSize:9,color:V.fgMuted,flex:1}}>{s.reason}</span>
              </div>:null;})}
            </Glass>
            {suggestion.services.length>0&&<><SLabel>Suggested Services</SLabel>
              <Glass style={{padding:12,marginBottom:12,borderLeft:`3px solid ${V.service}`}}>
                {suggestion.services.map(s=><div key={s.id} style={{display:"flex",alignItems:"center",gap:6}}><span style={{fontSize:10,color:V.service}}>◆</span><span style={{fontSize:11,color:V.fg,fontWeight:500}}>{s.name}</span><span style={{fontSize:9,color:V.fgMuted,flex:1}}>{s.reason}</span></div>)}
              </Glass>
            </>}
            {suggestion.templates.length>0&&<><SLabel>Matching Templates</SLabel>
              <div style={{display:"flex",gap:6,marginBottom:12}}>{suggestion.templates.map(t=><Glass key={t.template_id} hover onClick={()=>{setTeam(t.castes);setBudget(t.budget);setMaxR(t.maxRounds);setStep(3);}} style={{padding:8,flex:1}}>
                <span style={{fontSize:10,fontWeight:600,color:V.fg}}>{t.name}</span><span style={{fontSize:8,fontFamily:F.mono,color:V.success,marginLeft:6}}>{(t.successRate*100).toFixed(0)}%</span>
              </Glass>)}</div>
            </>}
            <div style={{display:"flex",gap:6}}>
              <Btn sm onClick={()=>applyTeam(suggestion.castes,suggestion.services)}>Accept Suggestion</Btn>
              <Btn v="secondary" sm onClick={()=>setStep(3)}>Configure Manually</Btn>
            </div>
          </>}
        </>}
        {/* STEP 3: CONFIGURE */}
        {step===3&&<>
          <SLabel>Team — click caste to add/remove, click tier to change</SLabel>
          <div style={{display:"flex",flexDirection:"column",gap:6,marginBottom:14}}>
            {CASTES.map(c=>{const member=team.find(t=>t.caste===c.id);return <div key={c.id} onClick={()=>!member&&toggleCaste(c.id)} style={{display:"flex",alignItems:"center",gap:8,padding:"6px 10px",background:member?`${c.color}08`:"transparent",border:`1px solid ${member?c.color+"25":V.border}`,borderRadius:8,cursor:"pointer"}}>
              <span style={{fontSize:14,filter:member?`drop-shadow(0 0 3px ${c.color}40)`:"none"}}>{c.icon}</span>
              <span style={{fontSize:11.5,color:member?V.fg:V.fgDim,fontWeight:member?500:400,width:80}}>{c.name}</span>
              {member?<div style={{display:"flex",gap:3}}>{Object.entries(TIERS).map(([k,ti])=><Pill key={k} color={member.tier===k?ti.color:V.fgDim} onClick={e=>{e.stopPropagation();setTier(c.id,k);}} sm>{ti.icon} {ti.label}</Pill>)}</div>
              :<span style={{fontSize:9,color:V.fgDim}}>click to add</span>}
              {member&&<div style={{marginLeft:"auto",display:"flex",alignItems:"center",gap:6}}>
                <span style={{fontSize:8.5,fontFamily:F.mono,color:V.fgDim}}>{TIER_MODELS[c.id]?.[member.tier]}</span>
                <span onClick={e=>{e.stopPropagation();toggleCaste(c.id);}} style={{cursor:"pointer",color:V.danger,fontSize:12}}>✕</span>
              </div>}
            </div>;})}
          </div>
          {/* Attach services */}
          {availableServices.length>0&&<><SLabel>Attach Services (callable resources)</SLabel>
            <div style={{display:"flex",gap:6,marginBottom:14}}>
              {availableServices.map(s=>{const attached=attachedServices.includes(s.id);return <Glass key={s.id} hover onClick={()=>toggleService(s.id)} style={{padding:8,flex:1,borderLeft:attached?`3px solid ${V.service}`:"3px solid transparent"}}>
                <div style={{display:"flex",alignItems:"center",gap:4}}><span style={{fontSize:10,color:V.service}}>◆</span><span style={{fontSize:10.5,fontWeight:500,color:attached?V.fg:V.fgMuted}}>{cn(s)}</span>{attached&&<span style={{fontSize:8,color:V.service,marginLeft:"auto"}}>✓</span>}</div>
                <div style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>{s.skillsExtracted||0} skills · {(s.agents||[]).length} agents</div>
              </Glass>;})}
            </div>
          </>}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10}}>
            <div><SLabel>Budget ($)</SLabel><input type="number" value={budget} onChange={e=>setBudget(parseFloat(e.target.value)||0)} step={0.5} style={{width:"100%",background:V.void,border:`1px solid ${V.border}`,borderRadius:6,color:V.fg,fontFamily:F.mono,fontSize:12,padding:"6px 10px",outline:"none"}}/></div>
            <div><SLabel>Max Rounds</SLabel><input type="number" value={maxR} onChange={e=>setMaxR(parseInt(e.target.value)||1)} style={{width:"100%",background:V.void,border:`1px solid ${V.border}`,borderRadius:6,color:V.fg,fontFamily:F.mono,fontSize:12,padding:"6px 10px",outline:"none"}}/></div>
            <div><SLabel>Strategy</SLabel><div style={{display:"flex",gap:4}}>{["stigmergic","sequential"].map(s=><Pill key={s} color={strategy===s?V.accent:V.fgDim} onClick={()=>setStrategy(s)} sm>{s}</Pill>)}</div></div>
          </div>
        </>}
        {/* STEP 4: LAUNCH */}
        {step===4&&<>
          <SLabel>Launch Summary</SLabel>
          <Glass style={{padding:14}}>
            <div style={{fontSize:12,color:V.fg,lineHeight:1.5,marginBottom:10}}>{obj}</div>
            <div style={{display:"flex",flexDirection:"column",gap:4,marginBottom:10}}>
              {team.map(({caste,tier})=>{const c=CASTES.find(x=>x.id===caste);const ti=TIERS[tier];return c?<div key={caste} style={{display:"flex",alignItems:"center",gap:6}}>
                <span style={{fontSize:11}}>{c.icon}</span><span style={{fontSize:10.5,color:V.fg}}>{c.name}</span><TierBadge tier={tier} sm/>
                <span style={{fontSize:8.5,fontFamily:F.mono,color:V.fgDim,marginLeft:"auto"}}>{TIER_MODELS[caste]?.[tier]}</span>
              </div>:null;})}
            </div>
            {attachedServices.length>0&&<div style={{marginBottom:10}}>
              <div style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.1em",textTransform:"uppercase",marginBottom:4}}>Attached Services</div>
              {attachedServices.map(id=>{const s=findNode(TREE,id);return s?<div key={id} style={{display:"flex",alignItems:"center",gap:4}}><span style={{fontSize:9,color:V.service}}>◆</span><span style={{fontSize:10,color:V.fg}}>{cn(s)}</span></div>:null;})}
            </div>}
            <div style={{display:"flex",gap:12,fontFamily:F.mono,fontSize:10,color:V.fgMuted,borderTop:`1px solid ${V.border}`,paddingTop:8}}>
              <span>${budget.toFixed(2)} budget</span><span>{maxR} rounds</span><span>{strategy}</span>
              <span style={{color:V.accent}}>est. ~${estCost.toFixed(2)}</span>
            </div>
          </Glass>
        </>}
      </div>
      <div style={{padding:"12px 18px",borderTop:`1px solid ${V.border}`,display:"flex",gap:8,justifyContent:"flex-end"}}>
        {step>1&&<Btn v="secondary" sm onClick={()=>setStep(Math.max(1,step-1))}>Back</Btn>}
        {step===1&&<Btn sm onClick={suggestTeam} disabled={!obj.trim()}>Suggest Team</Btn>}
        {step===2&&!suggestion&&<Btn sm disabled>Analyzing...</Btn>}
        {step===3&&<Btn sm onClick={()=>setStep(4)} disabled={team.length===0}>Review</Btn>}
        {step===4&&<Btn sm onClick={onClose}>Launch Colony</Btn>}
      </div>
    </div>
  </div>);
};

// ── TEMPLATE GALLERY ────────────────────────────────────
const ViewTemplates=({onCreateColony})=>{
  const sorted=[...TEMPLATES].sort((a,b)=>b.uses-a.uses);
  return <div style={{overflow:"auto",height:"100%",maxWidth:920}}>
    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:14}}><h2 style={{fontFamily:F.display,fontSize:20,fontWeight:700,color:V.fg,margin:0}}><GradientText>Templates</GradientText></h2><Pill color={V.fgDim}>{TEMPLATES.length}</Pill><Btn v="primary" sm sx={{marginLeft:"auto"}} onClick={onCreateColony}>+ Custom Colony</Btn></div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(240px,1fr))",gap:10}}>
      {sorted.map(t=>{const sc=t.successRate>=0.85?V.success:t.successRate>=0.7?V.warn:V.danger;
        return <Glass key={t.template_id} hover onClick={onCreateColony} style={{padding:14,display:"flex",flexDirection:"column"}}>
          <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:6}}><span style={{fontFamily:F.display,fontSize:14,fontWeight:600,color:V.fg}}>{t.name}</span><span style={{fontFamily:F.mono,fontSize:8,color:V.fgDim,marginLeft:"auto"}}>{t.uses}×</span></div>
          <div style={{fontSize:10.5,color:V.fgMuted,lineHeight:1.4,marginBottom:8,flex:1}}>{t.desc}</div>
          <div style={{display:"flex",gap:4,alignItems:"center",marginBottom:6}}>
            {t.castes.map(({id:cid,tier})=>{const c=CASTES.find(x=>x.id===cid);const ti=TIERS[tier];return c?<span key={cid} style={{display:"inline-flex",alignItems:"center",gap:2,padding:"1px 5px",borderRadius:4,border:`1px solid ${c.color}15`,background:`${c.color}08`}}>
              <span style={{fontSize:10}}>{c.icon}</span><span style={{fontSize:7,color:ti.color}}>{ti.icon}</span><span style={{fontSize:8,color:V.fgDim}}>{ti.label}</span>
            </span>:null;})}
          </div>
          <div style={{display:"flex",gap:8,alignItems:"center",borderTop:`1px solid ${V.border}`,paddingTop:6}}>
            <div style={{display:"flex",alignItems:"center",gap:3}}><div style={{width:24,height:4,background:"rgba(255,255,255,0.04)",borderRadius:2,overflow:"hidden"}}><div style={{height:"100%",width:`${t.successRate*100}%`,borderRadius:2,background:sc}}/></div><span style={{fontFamily:F.mono,fontSize:9,color:sc}}>{(t.successRate*100).toFixed(0)}%</span></div>
            <span style={{fontFamily:F.mono,fontSize:9,color:V.fgDim}}>~${t.avgCost.toFixed(2)}</span>
            <span style={{fontFamily:F.mono,fontSize:9,color:V.fgDim}}>{t.maxRounds}R</span>
          </div>
        </Glass>;})}
    </div>
  </div>;
};

// ── KNOWLEDGE (skills + graph unified) ──────────────────
const ViewKnowledge=()=>{
  const[tab,setTab]=useState("skills");const[sort,setSort]=useState("confidence");const[minConf,setMinConf]=useState(0);
  const[selKG,setSelKG]=useState(null);const[filterType,setFilterType]=useState(null);
  const typeColor={MODULE:V.purple,CONCEPT:V.secondary,SKILL:V.success,TOOL:V.warn};
  const sorted=[...SKILLS].filter(s=>s.confidence>=minConf).sort((a,b)=>sort==="confidence"?b.confidence-a.confidence:sort==="freshness"?new Date(b.at)-new Date(a.at):b.uncertainty-a.uncertainty);
  const types=[...new Set(KG_NODES.map(n=>n.type))];
  const fNodes=filterType?KG_NODES.filter(n=>n.type===filterType):KG_NODES;
  const fIds=new Set(fNodes.map(n=>n.id));
  const fEdges=KG_EDGES.filter(e=>fIds.has(e.from)&&fIds.has(e.to));
  const pos=useMemo(()=>{const p={};fNodes.forEach((n,i)=>{const a=(i/fNodes.length)*2*Math.PI;const r=110+Math.random()*30;p[n.id]={x:200+Math.cos(a)*r,y:170+Math.sin(a)*r};});return p;},[fNodes.length,filterType]);

  return <div style={{overflow:"auto",height:"100%"}}>
    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:12}}>
      <h2 style={{fontFamily:F.display,fontSize:20,fontWeight:700,color:V.fg,margin:0}}><GradientText>Knowledge</GradientText></h2>
      <Pill color={V.secondary}>{SKILLS.length} skills</Pill><Pill color={V.fgDim}>{KG_NODES.length} entities</Pill>
      <div style={{marginLeft:"auto",display:"flex",gap:4}}>{["skills","graph"].map(t=><Pill key={t} color={tab===t?V.accent:V.fgDim} onClick={()=>setTab(t)}>{t}</Pill>)}</div>
    </div>
    {tab==="skills"?<>
      <div style={{display:"flex",gap:6,marginBottom:10,alignItems:"center",fontSize:9}}>
        <SLabel sx={{marginBottom:0}}>Sort</SLabel>{["confidence","freshness","uncertainty"].map(s=><Pill key={s} color={sort===s?V.accent:V.fgDim} onClick={()=>setSort(s)} sm>{s}</Pill>)}
        <span style={{width:1,height:14,background:V.border,margin:"0 2px"}}/>
        <SLabel sx={{marginBottom:0}}>Min</SLabel><input type="range" min={0} max={0.9} step={0.05} value={minConf} onChange={e=>setMinConf(parseFloat(e.target.value))} style={{width:60,accentColor:V.accent}}/><span style={{fontFamily:F.mono,color:V.fgMuted}}>{(minConf*100).toFixed(0)}%</span>
        <span style={{marginLeft:"auto",fontSize:8,fontFamily:F.mono,color:V.fgDim}}>embed: qwen3-embedding-0.6b · search: dense+BM25+graph</span>
      </div>
      <div style={{display:"flex",flexDirection:"column",gap:6}}>{sorted.map(s=>{const cc=s.confidence>=0.8?V.success:s.confidence>=0.6?V.accent:V.warn;
        return <Glass key={s.id} hover style={{padding:12}}><div style={{display:"flex",gap:10,alignItems:"flex-start"}}>
          <div style={{flex:1}}><div style={{fontSize:11.5,color:V.fg,lineHeight:1.45,marginBottom:5}}>{s.text}</div><div style={{display:"flex",gap:5,alignItems:"center"}}><Pill color={V.fgDim} sm>{s.source}</Pill><span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>{timeAgo(s.at)}</span>{s.merged&&<Pill color={V.secondary} sm>merged</Pill>}</div></div>
          <div style={{width:80,flexShrink:0,textAlign:"right"}}><div style={{fontFamily:F.mono,fontSize:16,fontWeight:600,color:cc}}>{(s.confidence*100).toFixed(0)}%</div><div style={{height:4,background:"rgba(255,255,255,0.04)",borderRadius:2,overflow:"hidden",marginBottom:2}}><div style={{height:"100%",width:`${s.confidence*100}%`,borderRadius:2,background:cc}}/></div><div style={{fontSize:7,fontFamily:F.mono,color:V.fgDim}}>±{(s.uncertainty*100).toFixed(0)}% · α{s.alpha} β{s.beta}</div></div>
        </div></Glass>})}</div>
    </>:<>
      <div style={{display:"flex",gap:5,marginBottom:10}}><Pill color={!filterType?V.accent:V.fgDim} onClick={()=>setFilterType(null)} sm>All</Pill>{types.map(t=><Pill key={t} color={filterType===t?typeColor[t]:V.fgDim} onClick={()=>setFilterType(t)} sm>{t}</Pill>)}</div>
      <div style={{display:"flex",gap:14}}>
        <Glass style={{flex:1,padding:0,overflow:"hidden",minHeight:350}}>
          <svg viewBox="0 0 400 340" style={{width:"100%",height:350}}>
            <defs><marker id="kgA" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="5" markerHeight="3.5" orient="auto"><path d="M0,0 L10,3 L0,6" fill={V.fgDim}/></marker></defs>
            {fEdges.map((e,i)=>{const a=pos[e.from],b=pos[e.to];if(!a||!b)return null;const hl=selKG===e.from||selKG===e.to;return <g key={i}><line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={hl?"rgba(255,255,255,0.18)":"rgba(255,255,255,0.06)"} strokeWidth={hl?1.5:0.8} markerEnd="url(#kgA)"/><text x={(a.x+b.x)/2} y={(a.y+b.y)/2-4} textAnchor="middle" fill={hl?V.fgMuted:V.fgDim} style={{fontFamily:F.mono,fontSize:6}}>{e.pred}</text></g>;})}
            {fNodes.map(n=>{const p=pos[n.id];if(!p)return null;const isSel=selKG===n.id;const c=typeColor[n.type]||V.fgMuted;return <g key={n.id} onClick={()=>setSelKG(isSel?null:n.id)} style={{cursor:"pointer"}}>
              {isSel&&<circle cx={p.x} cy={p.y} r={26} fill="none" stroke={c} strokeWidth={0.5} opacity={0.4}/>}
              <circle cx={p.x} cy={p.y} r={isSel?16:12} fill={isSel?`${c}20`:V.surface} stroke={`${c}${isSel?"60":"30"}`} strokeWidth={1}/>
              <text x={p.x} y={p.y+3} textAnchor="middle" fill={isSel?c:V.fgMuted} style={{fontFamily:F.mono,fontSize:6,fontWeight:600}}>{n.name.length>14?n.name.slice(0,14)+"…":n.name}</text>
            </g>;})}
          </svg>
        </Glass>
        <div style={{width:200,flexShrink:0}}>
          {selKG?<Glass style={{padding:12}}>{(()=>{const n=KG_NODES.find(x=>x.id===selKG);const edges=KG_EDGES.filter(e=>e.from===selKG||e.to===selKG);return n?<><div style={{fontFamily:F.display,fontSize:14,fontWeight:600,color:V.fg,marginBottom:2}}>{n.name}</div><Pill color={typeColor[n.type]} sm>{n.type}</Pill><div style={{fontSize:9,color:V.fgDim,marginTop:6}}>Source: {n.source}</div>{edges.length>0&&<div style={{marginTop:8}}><SLabel>Connections</SLabel>{edges.map((e,i)=>{const other=e.from===selKG?e.to:e.from;const on=KG_NODES.find(x=>x.id===other);return <div key={i} style={{display:"flex",alignItems:"center",gap:3,padding:"2px 0",fontSize:9}}><span style={{color:V.fgDim,fontFamily:F.mono}}>{e.pred}</span><span style={{color:V.fg}}>{e.from===selKG?"→":"←"}</span><span style={{color:typeColor[on?.type]||V.fg}}>{on?.name}</span></div>;})}</div>}</>:null;})()}</Glass>
          :<div style={{padding:16,textAlign:"center",fontSize:10,color:V.fgDim}}>Click a node</div>}
        </div>
      </div>
    </>}
  </div>;
};

// ── FLEET (models + services + castes) ──────────────────
const ViewFleet=()=>{
  const services=allColonies(TREE).filter(c=>c.status==="service");
  const[selCaste,setSelCaste]=useState(null);
  const[editTier,setEditTier]=useState(null); // {caste,tier} being edited
  return <div style={{overflow:"auto",height:"100%",maxWidth:900}}>
    <h2 style={{fontFamily:F.display,fontSize:20,fontWeight:700,color:V.fg,margin:0,marginBottom:14}}><GradientText>Fleet</GradientText></h2>
    {/* Service colonies */}
    {services.length>0&&<><SLabel>Service Colonies</SLabel>
      <div style={{display:"flex",flexDirection:"column",gap:6,marginBottom:16}}>{services.map(s=><Glass key={s.id} style={{padding:12,borderLeft:`3px solid ${V.service}`}}>
        <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:4}}><span style={{fontSize:12,color:V.service}}>◆</span><span style={{fontFamily:F.display,fontSize:13,fontWeight:600,color:V.fg}}>{cn(s)}</span><Pill color={V.service} sm>service</Pill><QualityDot q={s.quality}/><span style={{marginLeft:"auto",fontFamily:F.mono,fontSize:9,color:V.fgDim}}>{(s.agents||[]).length} agents idle · {s.skillsExtracted||0} skills</span></div>
        <div style={{fontSize:10,color:V.fgMuted}}>{s.task}</div>
      </Glass>)}</div>
    </>}
    {/* Caste / Subcaste Configurator */}
    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
      <SLabel sx={{marginBottom:0}}>Caste Configurator</SLabel>
      <Btn v="secondary" sm>+ Custom Caste</Btn>
    </div>
    <div style={{display:"flex",flexDirection:"column",gap:6,marginBottom:16}}>
      {CASTES.map(c=>{const isSel=selCaste===c.id;return <Glass key={c.id} style={{padding:0,overflow:"hidden"}}>
        <div onClick={()=>setSelCaste(isSel?null:c.id)} style={{padding:"10px 14px",display:"flex",alignItems:"center",gap:8,cursor:"pointer"}}>
          <span style={{fontSize:16,filter:`drop-shadow(0 0 3px ${c.color}30)`}}>{c.icon}</span>
          <div style={{flex:1}}>
            <div style={{display:"flex",alignItems:"center",gap:6}}><span style={{fontFamily:F.display,fontSize:13,fontWeight:600,color:V.fg}}>{c.name}</span></div>
            <div style={{fontSize:9.5,color:V.fgMuted}}>{c.desc}</div>
          </div>
          <span style={{fontSize:8,color:V.fgDim}}>{isSel?"▲":"▼"}</span>
        </div>
        {isSel&&<div style={{borderTop:`1px solid ${V.border}`,padding:12,background:V.recessed}}>
          <div style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.1em",textTransform:"uppercase",fontWeight:600,marginBottom:8}}>Tier → Model Routing</div>
          {Object.entries(TIERS).map(([k,ti])=>{const model=TIER_MODELS[c.id]?.[k];const isEditing=editTier?.caste===c.id&&editTier?.tier===k;
            return <div key={k} style={{display:"flex",alignItems:"center",gap:8,padding:"6px 0",borderBottom:`1px solid ${V.border}`}}>
              <span style={{fontSize:11,color:ti.color,width:18,textAlign:"center"}}>{ti.icon}</span>
              <span style={{fontSize:10.5,color:V.fg,fontWeight:500,width:65}}>{ti.label}</span>
              <span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,flex:1}}>{ti.tag}</span>
              <div style={{display:"flex",alignItems:"center",gap:4}}>
                <span style={{width:5,height:5,borderRadius:"50%",background:PROV_COLOR[providerOf(model)]||V.fgDim}}/>
                <span style={{fontSize:9,fontFamily:F.mono,color:V.fg}}>{model||"—"}</span>
              </div>
              <Btn v="ghost" sm onClick={(e)=>{e.stopPropagation();setEditTier(isEditing?null:{caste:c.id,tier:k});}}>{isEditing?"done":"edit"}</Btn>
            </div>;
          })}
          {editTier?.caste===c.id&&<div style={{marginTop:8,padding:8,background:V.void,borderRadius:6,border:`1px solid ${V.border}`}}>
            <div style={{fontSize:8,fontFamily:F.mono,color:V.fgDim,marginBottom:6}}>Select model for {TIERS[editTier.tier]?.label} tier:</div>
            <div style={{display:"flex",gap:4,flexWrap:"wrap"}}>
              {["llama-cpp/qwen3-30b","gemini/gemini-2.5-flash","anthropic/claude-sonnet-4.6","anthropic/claude-opus-4.6"].map(m=>{
                const active=TIER_MODELS[c.id]?.[editTier.tier]===m;
                return <Pill key={m} color={active?PROV_COLOR[providerOf(m)]:V.fgDim} onClick={()=>{}} sm>{m}{active?" ✓":""}</Pill>;
              })}
            </div>
          </div>}
          <div style={{marginTop:8,display:"flex",gap:6}}>
            <Btn v="ghost" sm>Edit System Prompt</Btn>
            <Btn v="ghost" sm>View Tools ({c.id==="coder"?4:c.id==="researcher"?3:2})</Btn>
            <Btn v="danger" sm sx={{marginLeft:"auto"}}>Remove Caste</Btn>
          </div>
        </div>}
      </Glass>;})}
    </div>
    {/* Models */}
    <SLabel>Local Models</SLabel>
    <div style={{display:"flex",flexDirection:"column",gap:6,marginBottom:16}}>{LOCAL_MODELS.map(m=><Glass key={m.id} style={{padding:12}}>
      <div style={{display:"flex",alignItems:"center",gap:8}}><Dot status={m.status} size={6}/><span style={{fontFamily:F.display,fontSize:13,fontWeight:600,color:V.fg}}>{m.name}</span><Pill color={V.success} sm>{m.status}</Pill><Pill color={V.fgDim} sm>{m.quant}</Pill><span style={{marginLeft:"auto",fontFamily:F.mono,fontSize:9.5,color:V.purple}}>{m.vram} GB</span></div>
      <div style={{fontSize:9,fontFamily:F.mono,color:V.fgDim,marginTop:3}}>{m.provider}/{m.id} · {m.backend} · {m.gpu}</div>
    </Glass>)}</div>
    <SLabel>Cloud Endpoints</SLabel>
    <div style={{display:"flex",flexDirection:"column",gap:6}}>{CLOUD_EPS.map(c=><Glass key={c.id} style={{padding:12}}>
      <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:6}}><Dot status={c.status} size={6}/><span style={{fontFamily:F.display,fontSize:13,fontWeight:600,color:V.fg}}>{c.provider}</span><Pill color={V.success} sm>{c.status}</Pill><span style={{marginLeft:"auto",fontFamily:F.mono,fontSize:9.5,color:V.fgMuted}}>${c.spend.toFixed(2)} / ${c.limit.toFixed(2)}</span></div>
      <div style={{display:"flex",gap:3,flexWrap:"wrap"}}>{c.models.map(m=><Pill key={m} color={V.fg} sm>{m}</Pill>)}</div>
      <div style={{marginTop:6}}><Meter label="Daily" value={c.spend} max={c.limit} unit="$" color={c.color} compact/></div>
    </Glass>)}</div>
  </div>;
};

// ── SETTINGS ────────────────────────────────────────────
const ViewSettings=()=><div style={{maxWidth:640,overflow:"auto",height:"100%"}}>
  <h2 style={{fontFamily:F.display,fontSize:20,fontWeight:700,color:V.fg,marginBottom:14}}>Settings</h2>
  <SLabel>Retrieval Pipeline</SLabel>
  <Glass style={{padding:14,marginBottom:14}}>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:8,marginBottom:8}}>
      <Meter label="Embed" value={12} max={100} unit="ms" color={V.blue} compact/>
      <Meter label="Dense" value={3} max={50} unit="ms" color={V.purple} compact/>
      <Meter label="BM25" value={2} max={50} unit="ms" color={V.secondary} compact/>
      <Meter label="Graph" value={1} max={50} unit="ms" color={V.warn} compact/>
      <Meter label="RRF Fusion" value={0.5} max={10} unit="ms" color={V.accent} compact/>
      <Meter label="Total" value={18.5} max={200} unit="ms" color={V.success} compact/>
    </div>
    <div style={{fontSize:8.5,fontFamily:F.mono,color:V.fgDim}}>qwen3-embedding-0.6b Q8_0 · 1024-dim · hybrid dense+BM25+graph</div>
  </Glass>
  <SLabel>Sandbox Pool</SLabel>
  <Glass style={{padding:14,marginBottom:14}}>
    <div style={{display:"flex",gap:8,alignItems:"center",marginBottom:4}}>
      <span style={{fontSize:9,fontFamily:F.mono,color:V.fgMuted}}>gVisor (runsc) · 3 warm · ~100 MiB</span>
      <div style={{display:"flex",gap:3}}>{[1,2,3].map(i=><div key={i} style={{width:7,height:7,borderRadius:"50%",background:V.success,boxShadow:`0 0 5px ${V.success}40`}}/>)}</div>
    </div>
    <div style={{fontSize:8.5,fontFamily:F.mono,color:V.fgDim}}>STANDARD: gVisor + net:none + 512MB + 1CPU · AST pre-parser enabled</div>
  </Glass>
  <SLabel>Event Store</SLabel>
  <Glass style={{padding:12,marginBottom:14}}>
    <div style={{fontSize:10,fontFamily:F.mono,color:V.fgMuted,marginBottom:6}}>SQLite WAL · append-only · 31 events</div>
    <div style={{display:"flex",gap:5}}><Btn v="secondary" sm>Export</Btn><Btn v="danger" sm>Reset</Btn></div>
  </Glass>
  <SLabel>Protocols</SLabel>
  <Glass style={{padding:12}}>
    {[["MCP","7 tools (code_execute, web_search, web_fetch)","active"],["AG-UI","SSE · 12 event types","adapter"],["A2A","Agent Card · service colonies discoverable","discovery"]].map(([n,d,s])=><div key={n} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:`1px solid ${V.border}`}}><Dot status={s==="active"?"loaded":"pending"} size={4}/><span style={{fontFamily:F.mono,fontSize:10.5,fontWeight:600,color:V.fg,width:50}}>{n}</span><span style={{fontSize:10,color:V.fgMuted}}>{d}</span></div>)}
  </Glass>
</div>;

// ── WORKSPACE / THREAD VIEWS (compact) ──────────────────
const ViewWorkspace=({ws,onNav})=>{if(!ws)return null;const cols=allColonies([ws]);return <div style={{overflow:"auto",height:"100%",maxWidth:860}}>
  <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:14}}><span style={{fontSize:14,color:V.accent}}>▣</span><h2 style={{fontFamily:F.display,fontSize:18,fontWeight:700,color:V.fg,margin:0}}>{ws.name}</h2></div>
  <SLabel>Threads</SLabel>{(ws.children||[]).map(th=><Glass key={th.id} hover onClick={()=>onNav(th.id)} style={{padding:12,marginBottom:6}}><div style={{display:"flex",alignItems:"center",gap:5}}><span style={{color:V.blue,fontSize:10}}>▷</span><span style={{fontFamily:F.display,fontSize:12.5,fontWeight:600,color:V.fg}}>{th.name}</span><span style={{fontSize:9.5,fontFamily:F.mono,color:V.fgMuted,marginLeft:"auto"}}>{(th.children||[]).length} colonies</span></div></Glass>)}
</div>;};
const ViewThread=({thread,onNav,onCreateColony})=>{if(!thread)return null;return <div style={{overflow:"auto",height:"100%"}}>
  <div style={{display:"flex",alignItems:"center",gap:7,marginBottom:8}}><span style={{fontSize:12,color:V.blue}}>▷</span><h2 style={{fontFamily:F.display,fontSize:18,fontWeight:700,color:V.fg,margin:0}}>{thread.name}</h2><Btn v="primary" sm sx={{marginLeft:"auto"}} onClick={onCreateColony}>+ Spawn Colony</Btn></div>
  <div style={{display:"flex",flexDirection:"column",gap:8}}>{(thread.children||[]).map(c=><Glass key={c.id} hover onClick={()=>onNav(c.id)} style={{padding:14,borderLeft:c.status==="service"?`3px solid ${V.service}`:"3px solid transparent"}}>
    <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:3}}><Dot status={c.status} size={6}/><span style={{fontFamily:F.display,fontSize:13,fontWeight:600,color:V.fg}}>{cn(c)}</span>{c.quality!=null&&<QualityDot q={c.quality}/>}<span style={{fontSize:9.5,fontFamily:F.mono,color:V.fgMuted,marginLeft:"auto"}}>{c.status==="service"?"service":(`R${c.round}/${c.maxRounds}`)} · ${(c.cost||0).toFixed(2)}</span></div>
    {c.task&&<div style={{fontSize:11,color:V.fgMuted,lineHeight:1.4}}>{c.task}</div>}
  </Glass>)}</div>
</div>;};

// ═══════════════════════════════════════════════════════════
// MAIN SHELL
// ═══════════════════════════════════════════════════════════
export default function FormicOS(){
  const[view,setView]=useState("queen");const[treeSel,setTreeSel]=useState(null);const[treeExp,setTreeExp]=useState({});
  const[approvals,setApprovals]=useState(APPROVALS);const[activeQT,setActiveQT]=useState("qt-main");
  const[sideOpen,setSideOpen]=useState(true);const[showCreator,setShowCreator]=useState(false);

  const navTree=id=>{setTreeSel(id);setView("tree");};const navTab=v=>{setView(v);if(v!=="tree")setTreeSel(null);};
  const selNode=treeSel?findNode(TREE,treeSel):null;const crumbs=treeSel?bc(TREE,treeSel):null;
  const showFull=sideOpen;const totalCost=allColonies(TREE).reduce((a,c)=>a+(c.cost||0),0);
  const parentWs=selNode?.type==="thread"?TREE.find(ws=>(ws.children||[]).some(th=>th.id===selNode.id)):null;

  const NAV=[{id:"queen",label:"Queen",icon:"♛"},{id:"knowledge",label:"Knowledge",icon:"◈"},{id:"templates",label:"Templates",icon:"⧉"},{id:"fleet",label:"Fleet",icon:"⬢"},{id:"settings",label:"Settings",icon:"⚙"}];

  return <>
    <style>{`@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');@import url('https://api.fontshare.com/v2/css?f[]=satoshi@500,600,700,800&f[]=geist@400,500,600&display=swap');@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.25}}@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}*{box-sizing:border-box;margin:0;padding:0;}::-webkit-scrollbar{width:3px;}::-webkit-scrollbar-track{background:transparent;}::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.03);border-radius:2px;}::selection{background:${V.accent}25;}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:0.01ms!important;transition-duration:0.01ms!important;}}`}</style>
    <div style={{position:"fixed",inset:0,pointerEvents:"none",zIndex:0}}><div style={{position:"absolute",top:"-30%",left:"25%",width:800,height:800,borderRadius:"50%",filter:"blur(200px)",opacity:0.02,background:`radial-gradient(circle,${V.accent},transparent 70%)`}}/><div style={{position:"absolute",bottom:"-35%",right:"15%",width:600,height:600,borderRadius:"50%",filter:"blur(170px)",opacity:0.012,background:`radial-gradient(circle,${V.secondary},transparent 70%)`}}/></div>
    <div style={{position:"fixed",inset:0,pointerEvents:"none",zIndex:1,opacity:0.012,backgroundImage:"linear-gradient(rgba(255,255,255,0.012) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.012) 1px,transparent 1px)",backgroundSize:"64px 64px"}}/>
    <div style={{position:"fixed",inset:0,background:V.void,color:V.fg,fontFamily:F.body,display:"flex",flexDirection:"column",zIndex:3}}>
      {/* TOP BAR */}
      <div style={{height:40,borderBottom:`1px solid ${V.border}`,display:"flex",alignItems:"center",padding:"0 14px",gap:14,flexShrink:0,background:"rgba(8,8,15,0.85)",backdropFilter:"blur(14px)"}}>
        <div style={{display:"flex",alignItems:"center",gap:6,cursor:"pointer"}} onClick={()=>navTab("queen")}><span style={{fontFamily:F.display,fontWeight:800,fontSize:15,color:V.fg,letterSpacing:"-0.04em"}}>formic<span style={{color:V.accent}}>OS</span></span><span style={{fontSize:8,fontFamily:F.mono,color:V.fgDim}}>3.1</span></div>
        {view==="tree"&&crumbs&&<div style={{display:"flex",alignItems:"center",gap:2,fontSize:10.5,fontFamily:F.mono}}>{crumbs.map((n,i)=><span key={n.id} style={{display:"flex",alignItems:"center",gap:2}}>{i>0&&<span style={{color:V.fgDim,fontSize:7}}>⟩</span>}<span onClick={()=>navTree(n.id)} style={{color:i===crumbs.length-1?V.fg:V.fgMuted,cursor:"pointer"}}>{cn(n)}</span></span>)}</div>}
        <div style={{flex:1}}/>
        <div style={{display:"flex",alignItems:"center",gap:12,fontSize:9.5,fontFamily:F.mono,fontFeatureSettings:'"tnum"'}}>
          <span style={{color:V.fgDim}}><span style={{color:V.accent}}>${totalCost.toFixed(2)}</span></span>
          <span style={{color:V.fgDim}}>VRAM <span style={{color:V.purple}}>21.8</span>/32</span>
        </div>
        {approvals.length>0&&<div onClick={()=>navTab("queen")} style={{padding:"2px 8px",borderRadius:999,cursor:"pointer",background:V.accentMuted,fontSize:9.5,fontFamily:F.mono,color:V.accent,display:"flex",alignItems:"center",gap:4,border:`1px solid ${V.accent}18`,boxShadow:`0 0 14px ${V.accentGlow}`}}><span style={{width:4,height:4,borderRadius:"50%",background:V.accent,animation:"pulse 1.5s infinite"}}/>{approvals.length}</div>}
      </div>
      {/* BODY */}
      <div style={{flex:1,display:"flex",overflow:"hidden"}}>
        {/* SIDEBAR — click ◂/▸ to toggle */}
        <div style={{width:showFull?195:46,borderRight:`1px solid ${V.border}`,display:"flex",flexDirection:"column",flexShrink:0,background:`${V.surface}88`,backdropFilter:"blur(10px)",transition:"width 0.22s cubic-bezier(0.22,1,0.36,1)",overflow:"hidden"}}>
          <div style={{display:"flex",flexDirection:showFull?"row":"column",borderBottom:`1px solid ${V.border}`,padding:showFull?"3px 4px":"4px 3px",gap:1,flexWrap:showFull?"wrap":"nowrap"}}>
            <div onClick={()=>setSideOpen(!sideOpen)} style={{minWidth:showFull?24:40,height:showFull?26:32,display:"flex",alignItems:"center",justifyContent:"center",borderRadius:6,cursor:"pointer",color:V.fgDim,fontSize:10,flexShrink:0}} title={showFull?"Collapse":"Expand"}>{showFull?"◂":"▸"}</div>
            {NAV.map(n=>{const act=view===n.id||(view==="tree"&&n.id==="queen");return <div key={n.id} onClick={()=>navTab(n.id)} title={n.label} style={{minWidth:showFull?0:40,height:showFull?26:32,display:"flex",alignItems:"center",justifyContent:"center",gap:3,borderRadius:6,cursor:"pointer",fontSize:11,background:act?`${V.accent}0C`:"transparent",color:act?V.accent:V.fgDim,padding:showFull?"0 5px":"0",flexShrink:0}}><span style={{filter:act?`drop-shadow(0 0 3px ${V.accent}40)`:"none",fontSize:11,flexShrink:0}}>{n.icon}</span>{showFull&&<span style={{fontSize:9,fontWeight:500,whiteSpace:"nowrap"}}>{n.label}</span>}</div>;})}
          </div>
          {showFull&&<div style={{flex:1,overflow:"hidden",display:"flex",flexDirection:"column"}}>
            <div style={{padding:"5px 10px",borderBottom:`1px solid ${V.border}`,fontSize:7.5,fontFamily:F.mono,color:V.fgDim,letterSpacing:"0.14em",textTransform:"uppercase",fontWeight:600}}>Navigator</div>
            <div style={{flex:1,overflow:"auto",paddingTop:1}}><TreeNav selected={treeSel} onSelect={navTree} expanded={treeExp} onToggle={id=>setTreeExp(p=>({...p,[id]:p[id]===false}))}/></div>
          </div>}
        </div>
        {/* CONTENT */}
        <div style={{flex:1,padding:16,overflow:"hidden",display:"flex",flexDirection:"column"}}><div style={{flex:1,overflow:"hidden"}}>
          {view==="queen"&&<ViewQueen approvals={approvals} onApprove={id=>setApprovals(a=>a.filter(x=>x.id!==id))} onReject={id=>setApprovals(a=>a.filter(x=>x.id!==id))} onNav={navTree} queenThreads={QUEEN_THREADS} activeQT={activeQT} onSwitchQT={setActiveQT} onCreateColony={()=>setShowCreator(true)}/>}
          {view==="tree"&&selNode?.type==="colony"&&<ViewColony colony={selNode}/>}
          {view==="tree"&&selNode?.type==="workspace"&&<ViewWorkspace ws={selNode} onNav={navTree}/>}
          {view==="tree"&&selNode?.type==="thread"&&<ViewThread thread={selNode} onNav={navTree} onCreateColony={()=>setShowCreator(true)}/>}
          {view==="knowledge"&&<ViewKnowledge/>}
          {view==="templates"&&<ViewTemplates onCreateColony={()=>setShowCreator(true)}/>}
          {view==="fleet"&&<ViewFleet/>}
          {view==="settings"&&<ViewSettings/>}
        </div></div>
      </div>
    </div>
    {showCreator&&<ColonyCreator onClose={()=>setShowCreator(false)}/>}
  </>;
}
