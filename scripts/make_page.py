import json, pathlib
import pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
B=json.load(open(ROOT/'data'/'bundle.json'))
HTML = r'''<title>Wilayah 8 Rail Board</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
/* Layout: dispatcher board - fixed header, map canvas fills, roster docked right (below on phones) */
:root{
  --bg:#0a0f12; --panel:#121a1e; --panel2:#0e1518; --edge:#1f2b31;
  --fg:#dde7ea; --muted:#7b8f97; --dim:#4d5f67;
  --rail:#2a383f; --accent:#e9c46a;
  --dhoho:#e4572e; --penataran:#2e9bd6; --supas:#27a567; --arjonegoro:#9b6bc9;
  --ok:#27a567; --warn:#e9c46a;
  --display:"Barlow Condensed",'Arial Narrow',sans-serif;
  --body:"IBM Plex Sans",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,monospace;
  color-scheme:dark;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--body);overflow:hidden}
#app{height:100%;display:flex;flex-direction:column;
  padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:0}
header{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  padding-block:10px 8px;border-bottom:1px solid var(--edge);flex:0 0 auto}
.brand{display:flex;flex-direction:column;gap:1px;min-width:0}
h1{font-family:var(--display);font-weight:700;font-size:1.32rem;letter-spacing:.04em;
  text-transform:uppercase;margin:0;line-height:1;text-wrap:balance}
.sub{font-size:.665rem;color:var(--muted);letter-spacing:.09em;text-transform:uppercase}
.clockwrap{display:flex;align-items:baseline;gap:8px;margin-left:auto}
#clock{font-family:var(--mono);font-weight:600;font-size:1.64rem;line-height:1;
  font-variant-numeric:tabular-nums;color:var(--fg)}
#clock .s{font-size:.9rem;color:var(--muted)}
.ctl{display:flex;align-items:center;gap:6px}
button{font-family:var(--body);font-size:.72rem;font-weight:500;color:var(--fg);
  background:var(--panel);border:1px solid var(--edge);border-radius:4px;
  padding:5px 10px;cursor:pointer;letter-spacing:.02em}
button:hover{border-color:var(--dim)}
button[aria-pressed=true]{background:#1d2b31;border-color:var(--accent);color:var(--accent)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
#main{flex:1 1 auto;display:flex;gap:0;min-height:0}
#mapwrap{flex:1 1 auto;position:relative;min-width:0}
canvas{display:block;width:100%;height:100%;cursor:grab;touch-action:none}
canvas.drag{cursor:grabbing}
#side{flex:0 0 266px;border-left:1px solid var(--edge);display:flex;flex-direction:column;min-height:0}
.sec{padding:9px 12px;border-bottom:1px solid var(--edge)}
.sec h2{font-family:var(--display);font-size:.8rem;font-weight:600;letter-spacing:.09em;
  text-transform:uppercase;color:var(--muted);margin:0 0 7px}
.lines{display:flex;flex-direction:column;gap:4px}
.lrow{display:flex;align-items:center;gap:8px;background:none;border:0;padding:3px 2px;
  width:100%;text-align:left;border-radius:3px}
.lrow:hover{background:var(--panel2)}
.swatch{width:11px;height:11px;border-radius:2px;flex:0 0 auto}
.lname{font-size:.76rem;flex:1 1 auto;min-width:0}
.lcount{font-family:var(--mono);font-size:.7rem;color:var(--muted);font-variant-numeric:tabular-nums}
.lrow[aria-pressed=false]{opacity:.34}
#roster{flex:1 1 auto;overflow-y:auto;padding:4px 0}
.tr{display:grid;grid-template-columns:auto 1fr auto;gap:3px 8px;align-items:center;
  padding:6px 12px;border-left:3px solid transparent;cursor:pointer}
.tr:hover{background:var(--panel2)}
.tr.sel{background:#162127;border-left-color:var(--accent)}
.tno{font-family:var(--mono);font-size:.76rem;font-weight:600;font-variant-numeric:tabular-nums}
.tdest{font-size:.72rem;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.tstat{font-family:var(--mono);font-size:.655rem;color:var(--dim);grid-column:1/-1}
.empty{padding:14px 12px;font-size:.74rem;color:var(--dim);line-height:1.5}
#detail{border-top:1px solid var(--edge);max-height:40%;overflow-y:auto;display:none;flex:0 0 auto}
#detail.on{display:block}
.dh{padding:9px 12px 5px;position:sticky;top:0;background:var(--bg)}
.dh .n{font-family:var(--mono);font-weight:600;font-size:.9rem}
.dh .r{font-size:.69rem;color:var(--muted);margin-top:1px}
.stoplist{padding:0 12px 10px}
.st{display:grid;grid-template-columns:46px 1fr;gap:9px;font-size:.71rem;padding:2px 0;color:var(--muted)}
.st .t{font-family:var(--mono);font-variant-numeric:tabular-nums}
.st.now{color:var(--accent)}
.st.past{color:var(--dim)}
#scrub{flex:0 0 auto;display:flex;align-items:center;gap:10px;padding-block:7px 9px;
  border-top:1px solid var(--edge)}
input[type=range]{flex:1 1 auto;min-width:0;accent-color:var(--accent);height:18px}
.rng{font-family:var(--mono);font-size:.655rem;color:var(--dim);font-variant-numeric:tabular-nums}
.legend{position:absolute;left:10px;bottom:10px;font-family:var(--mono);font-size:.62rem;
  color:var(--dim);background:rgba(10,15,18,.76);border:1px solid var(--edge);
  border-radius:3px;padding:5px 7px;line-height:1.45;pointer-events:none}
.hint{position:absolute;right:10px;top:10px;font-size:.645rem;color:var(--dim);
  background:rgba(10,15,18,.76);border:1px solid var(--edge);border-radius:3px;padding:4px 7px;pointer-events:none}
@media (max-width:860px){
  #main{flex-direction:column}
  #side{flex:0 0 42%;border-left:0;border-top:1px solid var(--edge)}
  #mapwrap{flex:1 1 56%}
  .clockwrap{margin-left:0}
  header{gap:9px}
  h1{font-size:1.12rem}
  #detail{max-height:50%}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

<div id="app">
  <header>
    <div class="brand">
      <h1>Wilayah 8 Rail Board</h1>
      <div class="sub">KAI Commuter &middot; Daop 8 Surabaya &middot; from GAPEKA</div>
    </div>
    <div class="clockwrap"><div id="clock">--:--<span class="s">:--</span></div></div>
    <div class="ctl">
      <button id="play" aria-pressed="true">Pause</button>
      <button class="spd" data-s="30" aria-pressed="false">30&times;</button>
      <button class="spd" data-s="120" aria-pressed="true">120&times;</button>
      <button class="spd" data-s="600" aria-pressed="false">600&times;</button>
      <button id="now">Now</button>
      <button id="fit">Fit</button>
    </div>
  </header>
  <div id="main">
    <div id="mapwrap">
      <canvas id="cv"></canvas>
      <div class="hint">drag to pan &middot; scroll to zoom &middot; click a train</div>
      <div class="legend" id="legend"></div>
    </div>
    <div id="side">
      <div class="sec">
        <h2>Lines</h2>
        <div class="lines" id="lines"></div>
      </div>
      <div class="sec" style="border-bottom:0;padding-bottom:4px">
        <h2>Running now &middot; <span id="nrun" class="lcount">0</span></h2>
      </div>
      <div id="roster"></div>
      <div id="detail"></div>
    </div>
  </div>
  <div id="scrub">
    <span class="rng" id="t0"></span>
    <input type="range" id="slider" min="0" max="100" step="1" value="0" aria-label="Time of day">
    <span class="rng" id="t1"></span>
  </div>
</div>

<script>
const D = __BUNDLE__;
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
const ROUTES=Object.keys(D.routes);
const active=new Set(ROUTES);
let sel=null;

/* ---------- time domain ---------- */
let T0=1e9,T1=-1e9;
for(const t of D.trips){ T0=Math.min(T0,t.k[0][0]); T1=Math.max(T1,t.k[t.k.length-1][1]); }
T0=Math.floor(T0/300)*300; T1=Math.ceil(T1/300)*300;
let T=T0, speed=120, playing=true;
const fmt=s=>{s=((s%86400)+86400)%86400;const h=Math.floor(s/3600),m=Math.floor(s%3600/60);
  return String(h).padStart(2,'0')+':'+String(m).padStart(2,'0');};
const fmtS=s=>String(Math.floor(((s%86400)+86400)%86400%60)).padStart(2,'0');
document.getElementById('t0').textContent=fmt(T0);
document.getElementById('t1').textContent=fmt(T1);

/* ---------- projection ---------- */
const merc=(lon,lat)=>[ (lon+180)/360, (1-Math.log(Math.tan(Math.PI/4+lat*Math.PI/360))/Math.PI)/2 ];
let view={cx:0,cy:0,k:1};
function fit(){
  let xs=[],ys=[];
  for(const id in D.stops){const s=D.stops[id];const[p,q]=merc(s.x,s.y);xs.push(p);ys.push(q);}
  const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
  const w=cv.clientWidth||800,h=cv.clientHeight||600,pad=46;
  view.k=Math.min((w-2*pad)/(x1-x0),(h-2*pad)/(y1-y0));
  view.cx=(x0+x1)/2; view.cy=(y0+y1)/2;
}
const toScreen=(p,q)=>[ (p-view.cx)*view.k + cv.clientWidth/2, (q-view.cy)*view.k + cv.clientHeight/2 ];

/* ---------- geometry helpers ---------- */
function pointAtDist(sid,d){
  const S=D.shapes[sid], ds=S.d, c=S.c;
  let lo=0,hi=ds.length-1;
  if(d<=ds[0])return [c[0][0],c[0][1],bear(sid,0)];
  if(d>=ds[hi])return [c[hi][0],c[hi][1],bear(sid,hi-1)];
  while(hi-lo>1){const m=(lo+hi)>>1; if(ds[m]<=d)lo=m;else hi=m;}
  const span=ds[hi]-ds[lo], f=span>1e-9?(d-ds[lo])/span:0;
  return [ c[lo][0]+(c[hi][0]-c[lo][0])*f, c[lo][1]+(c[hi][1]-c[lo][1])*f, bear(sid,lo) ];
}
function bear(sid,i){
  const c=D.shapes[sid].c, a=c[Math.max(0,i)], b=c[Math.min(c.length-1,i+1)];
  return Math.atan2(b[1]-a[1], b[0]-a[0]);
}
/* position of a trip at time t, or null if not running */
function posAt(tr,t){
  const k=tr.k, n=k.length;
  if(t<k[0][0]||t>k[n-1][1]) return null;
  for(let i=0;i<n;i++){
    if(t<=k[i][1]){
      if(t>=k[i][0]) return {d:k[i][2],at:i,dwell:true};
      const pv=k[i-1]; if(!pv) return {d:k[i][2],at:i,dwell:true};
      const span=k[i][0]-pv[1], f=span>0?(t-pv[1])/span:1;
      return {d:pv[2]+(k[i][2]-pv[2])*f, at:i, dwell:false};
    }
  }
  return {d:k[n-1][2],at:n-1,dwell:true};
}

/* ---------- render ---------- */
function resize(){
  const r=Math.min(window.devicePixelRatio||1,2);
  cv.width=Math.max(1,Math.round(cv.clientWidth*r));
  cv.height=Math.max(1,Math.round(cv.clientHeight*r));
  ctx.setTransform(r,0,0,r,0,0);
}
/* off = perpendicular screen-space offset in px, so routes sharing one track stay distinct */
function drawShape(sid,color,width,alpha,off){
  const c=D.shapes[sid].c, pts=[];
  for(let i=0;i<c.length;i++){
    const[p,q]=merc(c[i][0],c[i][1]); pts.push(toScreen(p,q));
  }
  if(off){
    const sh=[];
    for(let i=0;i<pts.length;i++){
      const a=pts[Math.max(0,i-1)], b=pts[Math.min(pts.length-1,i+1)];
      let dx=b[0]-a[0], dy=b[1]-a[1]; const L=Math.hypot(dx,dy)||1;
      sh.push([pts[i][0] - dy/L*off, pts[i][1] + dx/L*off]);
    }
    pts.length=0; pts.push(...sh);
  }
  ctx.beginPath();
  for(let i=0;i<pts.length;i++) i?ctx.lineTo(pts[i][0],pts[i][1]):ctx.moveTo(pts[i][0],pts[i][1]);
  ctx.globalAlpha=alpha; ctx.strokeStyle=color; ctx.lineWidth=width;
  ctx.lineJoin='round'; ctx.lineCap='round'; ctx.stroke(); ctx.globalAlpha=1;
}
const MAJOR=new Set(['SB','SGU','WO','SDA','MR','KTS','KD','TA','BL','ML','PS','BJ','SBI','LMG','BBT','CU','WR','BG','MLK','JG']);
let running=[];
function draw(){
  const W=cv.clientWidth,H=cv.clientHeight;
  ctx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()||'#0a0f12';
  ctx.fillRect(0,0,W,H);
  /* full network underlay */
  for(const sid in D.shapes) drawShape(sid,'#2a383f',1.1,.5,0);
  /* per-route representative line, fanned out so shared track shows every route on it */
  ROUTES.forEach((r,i)=>{
    const rep=D.routes[r].rep; if(!rep) return;
    const off=(i-(ROUTES.length-1)/2)*2.6;
    drawShape(rep, D.routes[r].color, active.has(r)?2.4:1.1, active.has(r)?.95:.16, off);
  });
  /* stations */
  for(const id in D.stops){
    const s=D.stops[id]; const[p,q]=merc(s.x,s.y); const[x,y]=toScreen(p,q);
    if(x<-40||x>W+40||y<-40||y>H+40) continue;
    const big=MAJOR.has(id);
    ctx.beginPath(); ctx.arc(x,y,big?3.3:2,0,6.283);
    ctx.fillStyle=big?'#dde7ea':'#5d7078'; ctx.fill();
    if(big&&view.k>900){
      ctx.font='600 10px "IBM Plex Mono",monospace'; ctx.fillStyle='#8da0a8';
      ctx.fillText(id,x+6,y+3.5);
    }
  }
  /* trains */
  running=[];
  for(const tr of D.trips){
    if(!active.has(tr.r)) continue;
    const pa=posAt(tr,T); if(!pa) continue;
    running.push({tr,pa});
    const[lon,lat,b]=pointAtDist(tr.s,pa.d);
    const[p,q]=merc(lon,lat); const[x,y]=toScreen(p,q);
    const col=D.routes[tr.r].color, isSel=sel===tr.id;
    ctx.save(); ctx.translate(x,y);
    if(isSel){ ctx.beginPath(); ctx.arc(0,0,11,0,6.283);
      ctx.strokeStyle='#e9c46a'; ctx.lineWidth=1.4; ctx.globalAlpha=.9; ctx.stroke(); ctx.globalAlpha=1; }
    ctx.rotate(b);
    ctx.beginPath(); ctx.roundRect?ctx.roundRect(-6.5,-3.2,13,6.4,1.6):ctx.rect(-6.5,-3.2,13,6.4);
    ctx.fillStyle=col; ctx.fill();
    ctx.strokeStyle=pa.dwell?'#0a0f12':'rgba(255,255,255,.72)'; ctx.lineWidth=1; ctx.stroke();
    ctx.restore();
    if(view.k>700||isSel){
      ctx.font='600 9.5px "IBM Plex Mono",monospace';
      ctx.fillStyle=isSel?'#e9c46a':'#9fb2ba';
      ctx.fillText(tr.n,x+9,y-6);
    }
  }
  document.getElementById('nrun').textContent=running.length;
}

/* ---------- roster + detail ---------- */
let lastSig='';
function roster(){
  const sig=running.map(r=>r.tr.id+':'+r.pa.at+':'+(r.pa.dwell?1:0)).join('|')+'/'+sel;
  if(sig===lastSig) return; lastSig=sig;
  const el=document.getElementById('roster');
  if(!running.length){ el.innerHTML='<div class="empty">No trains in service at this hour. Drag the time slider or press Now.</div>'; return; }
  const order=[...running].sort((a,b)=>a.tr.n.localeCompare(b.tr.n,undefined,{numeric:true}));
  el.innerHTML=order.map(({tr,pa})=>{
    const k=tr.k, cur=k[pa.at], col=D.routes[tr.r].color;
    const stat=pa.dwell
      ? 'at '+(D.stops[cur[3]]?D.stops[cur[3]].n:cur[3])+' &middot; dep '+fmt(cur[1])
      : 'next '+(D.stops[cur[3]]?D.stops[cur[3]].n:cur[3])+' &middot; '+fmt(cur[0]);
    return '<div class="tr'+(sel===tr.id?' sel':'')+'" data-id="'+tr.id+'" style="border-left-color:'+(sel===tr.id?'#e9c46a':col)+'">'
      +'<span class="tno" style="color:'+col+'">'+tr.n+'</span>'
      +'<span class="tdest">&rarr; '+tr.h+'</span>'
      +'<span class="lcount">'+D.routes[tr.r].name+'</span>'
      +'<span class="tstat">'+stat+'</span></div>';
  }).join('');
}
function detail(){
  const el=document.getElementById('detail');
  const tr=D.trips.find(t=>t.id===sel);
  if(!tr){ el.className=''; el.innerHTML=''; return; }
  el.className='on';
  const col=D.routes[tr.r].color;
  const rows=tr.k.map((c,i)=>{
    const nm=D.stops[c[3]]?D.stops[c[3]].n:c[3];
    const cls=T>c[1]?'past':(T>=c[0]&&T<=c[1]?'now':'');
    return '<div class="st '+cls+'"><span class="t">'+fmt(c[0])+'</span><span>'+nm+' <span style="color:var(--dim)">'+c[3]+'</span></span></div>';
  }).join('');
  el.innerHTML='<div class="dh"><div class="n" style="color:'+col+'">KA '+tr.n+'</div>'
    +'<div class="r">'+D.routes[tr.r].name+' &rarr; '+tr.h+' &middot; '+tr.k.length+' stops</div></div>'
    +'<div class="stoplist">'+rows+'</div>';
}

/* ---------- lines panel ---------- */
function linesPanel(){
  document.getElementById('lines').innerHTML=ROUTES.map(r=>{
    const n=D.trips.filter(t=>t.r===r).length;
    return '<button class="lrow" data-r="'+r+'" aria-pressed="'+active.has(r)+'">'
      +'<span class="swatch" style="background:'+D.routes[r].color+'"></span>'
      +'<span class="lname">'+D.routes[r].name+'</span>'
      +'<span class="lcount">'+n+'</span></button>';
  }).join('');
  document.getElementById('legend').innerHTML=
    Object.keys(D.stops).length+' stations &middot; '+D.trips.length+' trips &middot; '
    +Object.keys(D.shapes).length+' shapes<br>track geometry: OpenStreetMap';
}

/* ---------- events ---------- */
document.getElementById('lines').addEventListener('click',e=>{
  const b=e.target.closest('.lrow'); if(!b) return;
  const r=b.dataset.r; active.has(r)?active.delete(r):active.add(r);
  b.setAttribute('aria-pressed',active.has(r)); lastSig='';
});
document.getElementById('roster').addEventListener('click',e=>{
  const d=e.target.closest('.tr'); if(!d) return;
  sel = sel===d.dataset.id ? null : d.dataset.id; lastSig=''; detail();
});
document.getElementById('play').addEventListener('click',e=>{
  playing=!playing; e.target.textContent=playing?'Pause':'Play'; e.target.setAttribute('aria-pressed',playing);
});
document.querySelectorAll('.spd').forEach(b=>b.addEventListener('click',()=>{
  speed=+b.dataset.s;
  document.querySelectorAll('.spd').forEach(o=>o.setAttribute('aria-pressed',o===b));
}));
document.getElementById('now').addEventListener('click',()=>{
  const d=new Date(); let s=d.getHours()*3600+d.getMinutes()*60+d.getSeconds();
  T=Math.min(Math.max(s,T0),T1);
});
document.getElementById('fit').addEventListener('click',()=>fit());
const slider=document.getElementById('slider');
slider.addEventListener('input',()=>{ T=T0+(T1-T0)*(+slider.value/1000); });
slider.max=1000;

let drag=null;
cv.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,moved:0};cv.classList.add('drag');cv.setPointerCapture(e.pointerId);});
cv.addEventListener('pointermove',e=>{
  if(!drag)return;
  const dx=e.clientX-drag.x, dy=e.clientY-drag.y;
  drag.moved+=Math.abs(dx)+Math.abs(dy);
  view.cx-=dx/view.k; view.cy-=dy/view.k; drag.x=e.clientX; drag.y=e.clientY;
});
cv.addEventListener('pointerup',e=>{
  const wasClick = drag && drag.moved<5;
  cv.classList.remove('drag');
  if(wasClick){
    const r=cv.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top;
    let best=null,bd=18;
    for(const {tr,pa} of running){
      const[lon,lat]=pointAtDist(tr.s,pa.d); const[p,q]=merc(lon,lat); const[x,y]=toScreen(p,q);
      const d=Math.hypot(x-mx,y-my); if(d<bd){bd=d;best=tr.id;}
    }
    sel = (best && best!==sel) ? best : null;
    lastSig=''; detail();
  }
  drag=null;
});
cv.addEventListener('wheel',e=>{
  e.preventDefault();
  const r=cv.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top;
  const wx=view.cx+(mx-cv.clientWidth/2)/view.k, wy=view.cy+(my-cv.clientHeight/2)/view.k;
  const f=Math.exp(-e.deltaY*0.0014);
  view.k=Math.min(Math.max(view.k*f,120),120000);
  view.cx=wx-(mx-cv.clientWidth/2)/view.k; view.cy=wy-(my-cv.clientHeight/2)/view.k;
},{passive:false});
window.addEventListener('resize',()=>{resize();});

/* ---------- loop ---------- */
let prev=performance.now();
function frame(now){
  const dt=(now-prev)/1000; prev=now;
  if(playing){ T+=dt*speed; if(T>T1) T=T0; }
  slider.value=Math.round((T-T0)/(T1-T0)*1000);
  document.getElementById('clock').innerHTML=fmt(T)+'<span class="s">:'+fmtS(T)+'</span>';
  draw(); roster();
  if(sel) detail();
  requestAnimationFrame(frame);
}
resize(); fit(); linesPanel();
const d0=new Date(); T=Math.min(Math.max(d0.getHours()*3600+d0.getMinutes()*60,T0),T1);
requestAnimationFrame(frame);
</script>
'''
out=ROOT/'viz'/'index.html'
out.write_text(HTML.replace('__BUNDLE__', json.dumps(B,separators=(',',':'))))
print("wrote",out,out.stat().st_size,"bytes")
