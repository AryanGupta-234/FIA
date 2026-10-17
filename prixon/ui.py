from __future__ import annotations

from fastapi.responses import HTMLResponse


PRIXON_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#10151f">
<title>Prixon · Local Agent</title>
<style>
:root{color-scheme:dark;--bg:#0c111a;--surface:#151d2a;--surface2:#1a2534;--line:rgba(178,202,232,.13);--muted:#94a4b8;--text:#edf4ff;--cyan:#70d9ed;--blue:#7b9cff;--green:#69d7a7;--amber:#f1c77b;--red:#ff8989;--radius:20px}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1000px 600px at 80% -10%,rgba(80,111,176,.22),transparent 60%),radial-gradient(700px 500px at 0% 30%,rgba(50,159,173,.10),transparent 60%),var(--bg);color:var(--text);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh}
button,input,textarea{font:inherit}button{cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}
.shell{display:grid;grid-template-columns:245px minmax(0,1fr);min-height:100vh}.sidebar{border-right:1px solid var(--line);padding:28px 18px;background:rgba(12,17,26,.72);backdrop-filter:blur(24px);display:flex;flex-direction:column;gap:28px}
.brand{display:flex;gap:12px;align-items:center;padding:4px 8px}.brand-mark{width:38px;height:38px;border-radius:13px;background:linear-gradient(145deg,#7be2ed,#7c8ff8);color:#10202d;display:grid;place-items:center;font-weight:900;font-size:18px;box-shadow:0 8px 28px #54b4d755}.brand-name{font-weight:760;letter-spacing:.03em;font-size:17px}.brand-sub{color:var(--muted);font-size:11px;letter-spacing:.12em;text-transform:uppercase}
.nav-label{font-size:10px;color:#73849a;letter-spacing:.16em;text-transform:uppercase;padding:0 10px;margin-bottom:7px}.nav{display:grid;gap:5px}.nav button{display:flex;align-items:center;gap:12px;border:1px solid transparent;background:transparent;color:#a9b7ca;text-align:left;border-radius:12px;padding:11px 12px}.nav button.active,.nav button:hover{background:#1b2a3a;border-color:#31465b;color:#edf8ff}.nav .glyph{width:20px;text-align:center;color:var(--cyan);font-size:16px}
.sidebar-bottom{margin-top:auto;display:grid;gap:10px}.local-card{padding:14px;border:1px solid var(--line);background:rgba(27,39,55,.62);border-radius:16px}.local-card strong{display:block;font-size:12px;margin-bottom:4px}.local-card p{font-size:11px;color:var(--muted);margin:0}
main{padding:28px clamp(18px,3vw,42px) 48px;max-width:1600px;width:100%;margin:0 auto}.topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:28px}.eyebrow{font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:var(--cyan);font-weight:700}.top-status{display:flex;align-items:center;gap:8px;padding:7px 12px;border:1px solid var(--line);border-radius:99px;background:#172231;color:#c5d5e8;font-size:12px}.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 12px #69d7a7aa}.top-actions{display:flex;gap:8px;align-items:center}
.hero{padding:30px 32px;border:1px solid #41566c66;border-radius:26px;background:linear-gradient(115deg,rgba(37,58,80,.9),rgba(24,38,57,.78) 55%,rgba(30,42,63,.72));box-shadow:0 22px 75px #0003;position:relative;overflow:hidden;margin-bottom:20px}.hero:after{content:"";position:absolute;width:340px;height:340px;border-radius:50%;border:1px solid #89d9e71c;right:7%;top:-220px;box-shadow:0 0 0 34px #89d9e70a,0 0 0 74px #89d9e706}.hero h1{font-size:clamp(27px,3vw,40px);line-height:1.1;letter-spacing:-.04em;margin:8px 0 10px;max-width:760px}.hero p{color:#b3c3d6;margin:0;max-width:640px}.hero-row{display:flex;justify-content:space-between;gap:18px;align-items:end;position:relative;z-index:1}.hero-buttons{display:flex;gap:9px;flex-wrap:wrap}
.btn{border:1px solid #41546c;background:#1c2a3b;color:#e7f1fc;padding:9px 13px;border-radius:11px;font-weight:650;font-size:12px;transition:.18s}.btn:hover{transform:translateY(-1px);border-color:#71cbd9}.btn.primary{background:linear-gradient(110deg,#74d8e5,#91a7ff);color:#0d1b28;border:0}.btn.danger{border-color:#754c57;background:#402b37;color:#ffc2c2}.btn.subtle{background:transparent;border-color:var(--line);color:#adbed1}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin-bottom:20px}.metric,.panel{background:linear-gradient(160deg,rgba(25,36,51,.94),rgba(19,28,41,.94));border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 12px 35px #0002}.metric{padding:17px 18px}.metric-label{font-size:11px;color:var(--muted);margin-bottom:10px}.metric-value{font-size:25px;font-weight:750;letter-spacing:-.03em}.metric-foot{font-size:11px;color:#8294aa;margin-top:3px}
.layout{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(300px,.85fr);gap:16px;align-items:start}.stack{display:grid;gap:16px}.panel{padding:20px}.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:15px}.panel-title{font-weight:720;font-size:14px}.panel-sub{color:var(--muted);font-size:11px;margin-top:2px}.command-box{border:1px solid #465d75;background:#0e1722;border-radius:16px;padding:12px}.command-box textarea{display:block;width:100%;min-height:76px;resize:vertical;background:transparent;color:var(--text);border:0;outline:0;padding:4px;font-size:14px}.command-box textarea::placeholder{color:#65788e}.command-actions{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:11px}.helper{font-size:11px;color:#8294aa}.quick{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}.chip{border:1px solid var(--line);border-radius:99px;background:#1a2736;color:#b8c9dc;padding:7px 10px;font-size:11px}.chip:hover{border-color:#6bc9da;color:#ebfbff}
.result{margin-top:12px;border:1px solid var(--line);border-radius:14px;padding:13px;background:#111c29;display:none}.result.show{display:block}.result strong{font-size:12px}.result p{margin:5px 0 0;color:#b7c7d8;font-size:12px;white-space:pre-wrap}.result.confirm{border-color:#a8864d;background:#282316}
.list{display:grid;gap:8px}.list-item{border:1px solid var(--line);background:#131e2b;border-radius:12px;padding:10px 12px;display:flex;justify-content:space-between;gap:12px;align-items:center}.list-main{min-width:0}.list-main strong{font-size:12px;display:block;overflow-wrap:anywhere}.list-main small{color:var(--muted);font-size:10px}.empty{padding:18px;border:1px dashed #33465b;border-radius:13px;color:#8394a8;text-align:center;font-size:12px}
.badge{font-size:10px;padding:4px 7px;border:1px solid var(--line);border-radius:99px;color:#aabbd0;white-space:nowrap}.badge.good{color:var(--green);border-color:#4f957b66}.badge.warn{color:var(--amber);border-color:#9c814866}.badge.bad{color:var(--red);border-color:#9f555566}
.voice-hotkeys{display:grid;grid-template-columns:1fr 1fr;gap:8px}.hotkey{border:1px solid var(--line);border-radius:13px;background:#121e2a;padding:11px}.hotkey kbd{border:1px solid #526981;border-bottom-width:2px;background:#202f40;border-radius:6px;padding:3px 6px;font-size:10px;color:#e6f2ff}.hotkey strong{display:block;font-size:12px;margin:8px 0 2px}.hotkey small{color:var(--muted);font-size:10px}
.window-list{max-height:290px;overflow:auto}.footer-note{color:#72849a;text-align:center;font-size:10px;margin-top:22px}
.view{display:none}.view.active{display:block}.activity{display:grid;gap:8px}.activity-item{border-left:2px solid #5abfce;padding:5px 0 5px 12px}.activity-item strong{font-size:11px}.activity-item small{display:block;color:var(--muted);font-size:10px}
@media(max-width:1100px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.layout{grid-template-columns:1fr}}
@media(max-width:720px){.shell{grid-template-columns:1fr}.sidebar{padding:12px 14px;border-right:0;border-bottom:1px solid var(--line)}.brand{padding:0}.nav{display:flex;overflow:auto}.nav-label,.sidebar-bottom{display:none}.nav button{white-space:nowrap;padding:8px 10px}.nav .glyph{display:none}main{padding:18px 14px 36px}.hero{padding:23px 19px}.hero-row{align-items:start;flex-direction:column}.topbar{align-items:flex-start}.grid{gap:9px}.metric{padding:13px}.metric-value{font-size:21px}}
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand"><div class="brand-mark">P</div><div><div class="brand-name">PRIXON</div><div class="brand-sub">Local Intelligence</div></div></div>
    <div><div class="nav-label">Workspace</div><nav class="nav">
      <button class="active" data-view="overview"><span class="glyph">◈</span>Overview</button>
      <button data-view="command"><span class="glyph">⌘</span>Command Center</button>
      <button data-view="goals"><span class="glyph">◎</span>Goals & Signals</button>
      <button data-view="activity"><span class="glyph">≋</span>Activity</button>
    </nav></div>
    <div class="sidebar-bottom">
      <div class="local-card"><strong><span class="dot" style="display:inline-block;margin-right:7px"></span>Local-first runtime</strong><p>Windows actions stay on this device. No hosted model fallback.</p></div>
      <div class="local-card"><strong>Emergency stop</strong><p>Ctrl + Alt + Pause halts the autonomous loop immediately.</p></div>
    </div>
  </aside>
  <main>
    <header class="topbar">
      <div><div class="eyebrow">Autonomous Intelligence Ecosystem · Prixon</div><div class="panel-sub">Personal Windows agent workspace</div></div>
      <div class="top-actions"><div id="statusPill" class="top-status"><span class="dot"></span><span id="statusText">Connecting…</span></div><button class="btn subtle" id="refreshBtn">↻ Refresh</button></div>
    </header>
    <section id="view-overview" class="view active">
      <div class="hero"><div class="hero-row"><div><div class="eyebrow">Your local intelligence layer</div><h1>Your Windows environment, under intelligent control.</h1><p>Grounded actions, live machine context and bounded autonomy—running locally, with confirmation at the risk boundary.</p></div><div class="hero-buttons"><button class="btn primary" data-jump="command">Open Command Center</button><button class="btn" id="startBtn">Start Agent</button><button class="btn danger" id="killBtn">Stop Agent</button></div></div></div>
      <div class="grid">
        <div class="metric"><div class="metric-label">CPU LOAD</div><div class="metric-value" id="cpuValue">—</div><div class="metric-foot">Current system usage</div></div>
        <div class="metric"><div class="metric-label">MEMORY</div><div class="metric-value" id="memoryValue">—</div><div class="metric-foot">Physical RAM utilization</div></div>
        <div class="metric"><div class="metric-label">BATTERY</div><div class="metric-value" id="batteryValue">—</div><div class="metric-foot" id="batteryFoot">Power state</div></div>
        <div class="metric"><div class="metric-label">OPEN WINDOWS</div><div class="metric-value" id="windowValue">—</div><div class="metric-foot">Visible top-level windows</div></div>
      </div>
      <div class="layout">
        <div class="stack">
          <section class="panel">
            <div class="panel-head"><div><div class="panel-title">Command Center</div><div class="panel-sub">Describe an outcome. Prixon grounds it against registered actions.</div></div><span class="badge good">LOCAL EXECUTION</span></div>
            <div class="command-box"><textarea id="commandInput" placeholder="Try: show system health · open calculator and maximize it · pause music"></textarea><div class="command-actions"><span class="helper">Enter to submit · Shift+Enter for a new line</span><button class="btn primary" id="sendBtn">Run command ↗</button></div></div>
            <div class="quick"><button class="chip" data-command="show system health">System health</button><button class="chip" data-command="check battery">Battery</button><button class="chip" data-command="list running processes">Processes</button><button class="chip" data-command="check Office session status">Office status</button><button class="chip" data-command="show media playback status">Media status</button></div>
            <div id="commandResult" class="result"><strong id="resultTitle"></strong><p id="resultBody"></p><div id="confirmRow" style="display:none;margin-top:11px"><button class="btn primary" id="confirmBtn">Confirm and execute</button><span class="helper" style="margin-left:9px">Required for high-impact actions.</span></div></div>
          </section>
          <section class="panel"><div class="panel-head"><div><div class="panel-title">Open Windows</div><div class="panel-sub">Top-level window metadata; sensitive credential windows are hidden.</div></div><span id="windowCount" class="badge">0 windows</span></div><div id="windowList" class="list window-list"><div class="empty">Waiting for perception snapshot…</div></div></section>
        </div>
        <div class="stack">
          <section class="panel"><div class="panel-head"><div><div class="panel-title">Voice Interface</div><div class="panel-sub">Push-to-talk · local Vosk · local Windows speech</div></div><span id="voiceBadge" class="badge">Disabled</span></div><div class="voice-hotkeys"><div class="hotkey"><kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>V</kbd><strong>Emergency stop</strong><small>Say “Prixon stop”</small></div><div class="hotkey"><kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>M</kbd><strong>Voice command</strong><small>Speak one short request</small></div></div><div id="voiceInfo" class="panel-sub" style="margin-top:12px">Voice status will appear here.</div></section>
          <section class="panel"><div class="panel-head"><div><div class="panel-title">Proactive Signals</div><div class="panel-sub">Suggestions only; never silently execute routines.</div></div><span id="suggestionCount" class="badge">0 pending</span></div><div id="suggestionList" class="list"><div class="empty">No pending suggestions.</div></div></section>
        </div>
      </div>
    </section>
    <section id="view-command" class="view">
      <div class="panel" style="margin-bottom:16px"><div class="eyebrow">Interaction</div><h2 style="margin:5px 0 8px">Command Center</h2><div class="panel-sub">Every request passes through deterministic grounding, confidence gates and the registered action contract.</div><div style="margin-top:18px" class="command-box"><textarea id="commandInput2" placeholder="What should Prixon do?"></textarea><div class="command-actions"><span class="helper">Safe L1/L2 requests may run automatically. L4 requires confirmation.</span><button class="btn primary" id="sendBtn2">Run command ↗</button></div></div><div id="commandResult2" class="result"><strong id="resultTitle2"></strong><p id="resultBody2"></p><div id="confirmRow2" style="display:none;margin-top:11px"><button class="btn primary" id="confirmBtn2">Confirm and execute</button></div></div></div>
      <div class="panel"><div class="panel-head"><div><div class="panel-title">Registered Capabilities</div><div class="panel-sub">Actions currently exposed by the local registry.</div></div><span id="actionCount" class="badge">—</span></div><div id="actionList" class="list"></div></div>
    </section>
    <section id="view-goals" class="view">
      <div class="panel">
        <div class="panel-head"><div><div class="panel-title">Goals & Signals</div><div class="panel-sub">Persistent user goals and bounded proactive events.</div></div><button id="goalRefresh" class="btn subtle">Refresh</button></div>
        <div class="command-box" style="margin:12px 0 16px"><textarea id="goalInput" style="min-height:56px" placeholder="Describe an outcome to keep on Prixon's goal stack…"></textarea><div class="command-actions"><span class="helper">Prixon prepares a typed plan; L4 steps still need confirmation.</span><button class="btn primary" id="createGoalBtn">Create goal</button></div></div>
        <div id="goalResult" class="result"><strong id="goalResultTitle"></strong><p id="goalResultBody"></p></div>
        <div id="goalList" class="list"><div class="empty">No goals available.</div></div>
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="panel-head"><div><div class="panel-title">Scheduled Routines</div><div class="panel-sub">Schedule owner-approved macros. L3 autonomous execution is optional and separately confirmed.</div></div><button id="routineRefresh" class="btn subtle">Refresh</button></div>
        <div class="grid" style="grid-template-columns:repeat(2,minmax(0,1fr));margin:14px 0">
          <label class="list-main">Routine name<input id="routineName" maxlength="100" placeholder="Morning workspace" style="width:100%;margin-top:6px"></label>
          <label class="list-main">Approved macro<select id="routineMacro" style="width:100%;margin-top:6px"><option value="">Loading approved macros…</option></select></label>
          <label class="list-main">Local time<input id="routineTime" type="time" value="09:00" style="width:100%;margin-top:6px"></label>
          <label class="list-main">Days<select id="routineDays" style="width:100%;margin-top:6px"><option value="all">Every day</option><option value="weekdays">Weekdays</option><option value="weekends">Weekends</option></select></label>
        </div>
        <label class="helper" style="display:flex;align-items:center;gap:9px;margin:4px 0 12px"><input id="routineAutoExecute" type="checkbox"> Enable autonomous L3 execution (only eligible reversible/read-only macros; requires confirmation)</label>
        <button class="btn primary" id="createRoutineBtn">Schedule routine</button>
        <div id="routineResult" class="result"><strong id="routineResultTitle"></strong><p id="routineResultBody"></p></div>
        <div id="routineList" class="list" style="margin-top:12px"></div>
        <div class="panel-sub" style="margin-top:14px">Recent routine runs</div><div id="routineRunList" class="list"></div>
      </div>
    </section>
    <section id="view-activity" class="view"><div class="panel"><div class="panel-head"><div><div class="panel-title">Recent Activity</div><div class="panel-sub">Local action and decision audit summaries.</div></div><div style="display:flex;gap:8px"><a class="btn subtle" href="/api/v1/agent/audit/export" download="prixon-audit.jsonl">Export JSONL</a><button id="auditRefresh" class="btn subtle">Refresh</button></div></div><div id="auditList" class="activity"><div class="empty">No activity loaded.</div></div></div></section>
    <div class="footer-note">PRIXON · LOCAL-FIRST · WINDOWS AUTOMATION · RISK-GATED AUTONOMY</div>
  </main>
</div>
<script>
const API="/api/v1/agent";
let pendingText=null;
const $=id=>document.getElementById(id);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function request(path,options={}){
  const response=await fetch(API+path,{headers:{"Content-Type":"application/json"},...options});
  const data=await response.json().catch(()=>({detail:response.statusText}));
  if(!response.ok) throw new Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail||data));
  return data;
}
function setResult(prefix,result){
  const isConfirm=result.status==="confirmation_required";
  $(prefix==="1"?"commandResult":"commandResult2").classList.toggle("show",true);
  $(prefix==="1"?"commandResult":"commandResult2").classList.toggle("confirm",isConfirm);
  $(prefix==="1"?"resultTitle":"resultTitle2").textContent=isConfirm?"Confirmation required":String(result.status||"Result").replaceAll("_"," ");
  const reason=result.clarification||result.reason||result.answer||result.message||result.error||"Request processed by Prixon.";
  $(prefix==="1"?"resultBody":"resultBody2").textContent=reason;
  $(prefix==="1"?"confirmRow":"confirmRow2").style.display=isConfirm?"block":"none";
}
async function sendCommand(text,prefix="1",confirmed=false){
  if(!text.trim())return;
  const button=$(prefix==="1"?"sendBtn":"sendBtn2");
  button.disabled=true;button.textContent="Working…";
  try{
    const result=await request("/run",{method:"POST",body:JSON.stringify({text,args:{},execute:null,confirmed})});
    if(result.status==="confirmation_required"){pendingText=text;}else if(confirmed){pendingText=null;}
    setResult(prefix,result);await refreshAll();
  }catch(error){setResult(prefix,{status:"error",reason:error.message});}
  finally{button.disabled=false;button.textContent="Run command ↗";}
}
function fillList(id,items,render,empty){
  const el=$(id);
  if(!items||!items.length){el.innerHTML='<div class="empty">'+esc(empty)+'</div>';return;}
  el.innerHTML=items.map(render).join("");
}
async function refreshHealth(){
  const h=await request("/health");
  $("statusText").textContent=h.loop_running?"Agent active":"Agent ready";
  $("cpuValue").textContent="—";$("memoryValue").textContent="—";$("batteryValue").textContent="—";
  $("actionCount").textContent=(h.registered_actions||0)+" actions";
  $("actionCount").className="badge good";
  $("statusPill").querySelector(".dot").style.background=h.kill_switch_active?"var(--red)":"var(--green)";
  return h;
}
async function refreshPerception(){
  const p=await request("/perception");
  const snap=p.snapshot||{};
  $("cpuValue").textContent=(snap.cpu_percent??"—")+"%";
  $("memoryValue").textContent=(snap.memory?.percent??"—")+"%";
  const battery=snap.battery;
  $("batteryValue").textContent=battery?battery.percent+"%":"N/A";
  $("batteryFoot").textContent=battery?(battery.plugged_in?"Plugged in":"On battery"):"No battery telemetry";
  const windows=snap.open_windows||[];
  $("windowValue").textContent=windows.length;
  $("windowCount").textContent=windows.length+" windows";
  fillList("windowList",windows.slice(0,30),w=>'<div class="list-item"><div class="list-main"><strong>'+esc(w.title||w.process||"Application window")+'</strong><small>'+esc(w.process||"Unknown process")+' · PID '+esc(w.pid)+'</small></div><span class="badge '+(w.foreground?"good":"")+'">'+(w.foreground?"Foreground":w.minimized?"Minimized":"Open")+'</span></div>',"No visible top-level windows.");
}
async function refreshVoice(){
  const v=await request("/voice/status");
  const ready=!!v.ready;
  $("voiceBadge").textContent=ready?"Ready":v.enabled||v.command_enabled?"Not ready":"Disabled";
  $("voiceBadge").className="badge "+(ready?"good":v.enabled||v.command_enabled?"warn":"");
  const hotkeys=[];
  if(v.kill_hotkey)hotkeys.push("Emergency stop: "+v.kill_hotkey);
  if(v.command_hotkey)hotkeys.push("Voice command: "+v.command_hotkey);
  $("voiceInfo").textContent=hotkeys.join(" · ")||v.error||"Enable voice options and install the local Vosk model to activate push-to-talk.";
}
async function refreshSuggestions(){
  const items=await request("/suggestions?limit=20");
  $("suggestionCount").textContent=items.length+" pending";
  fillList("suggestionList",items,item=>'<div class="list-item"><div class="list-main"><strong>'+esc(item.title||item.trigger)+'</strong><small>'+esc(item.message||"Review this suggestion.")+'</small></div><span class="badge warn">Review</span></div>',"No pending suggestions.");
}
async function refreshGoals(){
  const items=await request("/goals");
  fillList("goalList",items,item=>'<div class="list-item"><div class="list-main"><strong>'+esc(item.description||"Goal")+'</strong><small>Priority '+esc(item.priority)+' · '+esc(item.created_at||"")+'</small></div><div style="display:flex;gap:7px;align-items:center"><span class="badge '+(item.status==="completed"?"good":"")+'">'+esc(item.status)+'</span>'+(["pending","active"].includes(item.status)?'<button class="btn subtle" data-goal-cancel="'+esc(item.id)+'">Cancel</button>':"")+'</div></div>',"No stored goals.");
}

async function refreshRoutines(){
  const [routines,macros,runs]=await Promise.all([
    request("/routines"),request("/macros?approved=true"),request("/routine-runs?limit=12")
  ]);
  const selected=$("routineMacro").value;
  $("routineMacro").innerHTML='<option value="">Choose an approved macro</option>'+macros.map(m=>'<option value="'+esc(m.id)+'">'+esc(m.name)+' · '+esc(m.successes)+' successes</option>').join("");
  if(macros.some(m=>String(m.id)===selected))$("routineMacro").value=selected;
  fillList("routineList",routines,item=>'<div class="list-item"><div class="list-main"><strong>'+esc(item.name)+'</strong><small>'+esc(item.time_local)+' · '+(item.weekdays||[]).map(n=>["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][n]).join(", ")+'</small></div><div style="display:flex;gap:7px;align-items:center"><span class="badge '+(item.auto_execute?"good":"")+'">'+(item.auto_execute?"L3 auto":"Review first")+'</span><span class="badge">'+(item.enabled?"Enabled":"Paused")+'</span><button class="btn subtle" data-routine-toggle="'+esc(item.id)+'" data-enabled="'+(!item.enabled)+'">'+(item.enabled?"Pause":"Enable")+'</button></div></div>',"No scheduled routines.");
  fillList("routineRunList",runs,item=>'<div class="list-item"><div class="list-main"><strong>'+esc(item.routine_name||"Routine")+'</strong><small>'+esc(item.due_date)+' · '+esc(item.status)+'</small></div><span class="badge '+(item.status==="completed"?"good":item.status==="failed"||item.status==="interrupted"?"warn":"")+'">'+esc(item.status)+'</span></div>',"No routine runs recorded.");
}
async function refreshAudit(){
  const items=await request("/audit?limit=30");
  fillList("auditList",items,item=>'<div class="activity-item"><strong>'+esc(item.event_type||"activity")+'</strong><small>'+esc(new Date((item.created_at||0)*1000).toLocaleString())+'</small></div>',"No recent audit activity.");
}
async function refreshActions(){
  const items=await request("/actions");
  $("actionCount").textContent=items.length+" actions";
  fillList("actionList",items,item=>'<div class="list-item"><div class="list-main"><strong>'+esc(item.name)+'</strong><small>'+esc(item.description)+'</small></div><span class="badge">'+esc(item.risk)+'</span></div>',"No registered actions.");
}
async function refreshAll(){
  const jobs=[refreshHealth(),refreshPerception(),refreshVoice(),refreshSuggestions()];
  await Promise.allSettled(jobs);
}
function showView(name){
  document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active",v.id==="view-"+name));
  document.querySelectorAll(".nav button").forEach(b=>b.classList.toggle("active",b.dataset.view===name));
  if(name==="goals"){refreshGoals().catch(e=>console.error(e));refreshRoutines().catch(e=>console.error(e));}
  if(name==="activity")refreshAudit().catch(e=>console.error(e));
  if(name==="command")refreshActions().catch(e=>console.error(e));
}
document.querySelectorAll("[data-view]").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));
document.querySelectorAll("[data-jump]").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.jump)));
document.querySelectorAll("[data-command]").forEach(b=>b.addEventListener("click",()=>{showView("command");$("commandInput2").value=b.dataset.command;}));
$("sendBtn").addEventListener("click",()=>sendCommand($("commandInput").value,"1"));
$("sendBtn2").addEventListener("click",()=>sendCommand($("commandInput2").value,"2"));
["commandInput","commandInput2"].forEach((id,index)=>$(id).addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendCommand($(id).value,index===0?"1":"2");}}));
$("confirmBtn").addEventListener("click",()=>pendingText&&sendCommand(pendingText,"1",true));
$("confirmBtn2").addEventListener("click",()=>pendingText&&sendCommand(pendingText,"2",true));
$("refreshBtn").addEventListener("click",()=>refreshAll());
$("createGoalBtn").addEventListener("click",async()=>{
  const description=$("goalInput").value.trim();
  if(!description)return;
  const button=$("createGoalBtn");button.disabled=true;button.textContent="Planning…";
  try{
    const result=await request("/goals",{method:"POST",body:JSON.stringify({
      description,priority:2,plan:null,confirmed:false
    })});
    $("goalResult").classList.add("show");
    $("goalResultTitle").textContent="Goal added";
    $("goalResultBody").textContent=result.message||"Prixon has stored the goal and prepared its typed plan.";
    $("goalInput").value="";
    await refreshGoals();
  }catch(error){
    $("goalResult").classList.add("show");
    $("goalResultTitle").textContent="Goal not created";
    $("goalResultBody").textContent=error.message;
  }finally{button.disabled=false;button.textContent="Create goal";}
});
$("goalList").addEventListener("click",async event=>{
  const button=event.target.closest("[data-goal-cancel]");
  if(!button)return;
  button.disabled=true;
  try{
    await request("/goals/"+encodeURIComponent(button.dataset.goalCancel)+"/status",{
      method:"POST",body:JSON.stringify({status:"cancelled"})
    });
    await refreshGoals();
  }catch(error){alert(error.message);button.disabled=false;}
});
$("goalRefresh").addEventListener("click",()=>refreshGoals());

$("routineRefresh").addEventListener("click",()=>refreshRoutines().catch(e=>console.error(e)));
$("createRoutineBtn").addEventListener("click",async()=>{
  const name=$("routineName").value.trim();
  const macroId=Number($("routineMacro").value);
  const timeLocal=$("routineTime").value;
  const dayMode=$("routineDays").value;
  const weekdays=dayMode==="weekdays"?[0,1,2,3,4]:dayMode==="weekends"?[5,6]:[0,1,2,3,4,5,6];
  const autoExecute=$("routineAutoExecute").checked;
  if(!name||!macroId||!timeLocal)return;
  const confirmed=autoExecute?window.confirm("Allow this owner-approved routine to run automatically at L3? Only reversible/read-only, non-sensitive actions are eligible."):false;
  if(autoExecute&&!confirmed)return;
  const button=$("createRoutineBtn");button.disabled=true;button.textContent="Scheduling…";
  try{
    const result=await request("/routines",{method:"POST",body:JSON.stringify({
      name,macro_id:macroId,time_local:timeLocal,weekdays,auto_execute:autoExecute,confirmed
    })});
    $("routineResult").classList.add("show");
    $("routineResultTitle").textContent="Routine scheduled";
    $("routineResultBody").textContent=result.execution==="owner_approved_l3"?"Owner-confirmed L3 execution is enabled.":"Prixon will suggest the routine at its scheduled time.";
    $("routineName").value="";$("routineAutoExecute").checked=false;
    await refreshRoutines();
  }catch(error){
    $("routineResult").classList.add("show");
    $("routineResultTitle").textContent="Routine not scheduled";
    $("routineResultBody").textContent=error.message;
  }finally{button.disabled=false;button.textContent="Schedule routine";}
});
$("routineList").addEventListener("click",async event=>{
  const button=event.target.closest("[data-routine-toggle]");
  if(!button)return;
  button.disabled=true;
  try{
    await request("/routines/"+encodeURIComponent(button.dataset.routineToggle)+"/status",{
      method:"POST",body:JSON.stringify({enabled:button.dataset.enabled==="true"})
    });
    await refreshRoutines();
  }catch(error){alert(error.message);button.disabled=false;}
});
$("auditRefresh").addEventListener("click",()=>refreshAudit());
$("killBtn").addEventListener("click",async()=>{try{await request("/kill",{method:"POST",body:"{}"});await refreshAll();}catch(e){alert(e.message);}});
$("startBtn").addEventListener("click",async()=>{try{await request("/runtime/start",{method:"POST",body:"{}"});await refreshAll();}catch(e){alert(e.message);}});
refreshAll().catch(e=>{$("statusText").textContent="API unavailable";console.error(e);});
setInterval(()=>refreshAll().catch(()=>{}),12000);
</script>
</body>
</html>
"""


def render_prixon_ui() -> HTMLResponse:
    return HTMLResponse(PRIXON_HTML)
