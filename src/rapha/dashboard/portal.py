"""Render the multi-tab portal from a briefing dict.

Pure: briefing in, one self-contained HTML string out. No I/O. Everything is inline
(CSS, JS, SVG sparklines) because the server enforces a strict same-origin policy
and the page must work with no network (ADR-009). Vanilla JS only — no framework, in
keeping with the project's stdlib-first constraint.

Tabs: Today · Training · Meals · Performance · Progress.
"""

from __future__ import annotations

import html
import json
from typing import Any


def _e(x: Any) -> str:
    return html.escape(str(x))


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  color-scheme:light dark;
  --bg:oklch(0.968 0.008 85);--panel:oklch(0.995 0.004 90);--inset:oklch(0.975 0.008 85);
  --stripe:oklch(0.93 0.008 82);
  --line:oklch(0.88 0.010 80);--line2:oklch(0.90 0.010 80);--row:oklch(0.92 0.008 82);
  --line-strong:oklch(0.85 0.010 80);--axis:oklch(0.82 0.010 80);--scroll:oklch(0.85 0.010 80);
  --ink:oklch(0.24 0.015 60);--ink2:oklch(0.30 0.014 62);--ink3:oklch(0.40 0.014 65);
  --ink4:oklch(0.47 0.014 65);--dim:oklch(0.52 0.012 70);--dim2:oklch(0.61 0.012 70);
  --accent:oklch(0.60 0.13 45);--accent-hover:oklch(0.48 0.13 45);--accent2:oklch(0.60 0.13 215);
  --bad:oklch(0.45 0.15 30);--on-accent:oklch(0.99 0.004 90);--on-ink:oklch(0.975 0.008 85);
  --accent-soft:oklch(0.60 0.13 45 / 0.10);--area:oklch(0.60 0.13 45 / 0.13);
  --band:oklch(0.24 0.015 60 / 0.06);--trend:oklch(0.24 0.015 60 / 0.45);
  --stage-rem:oklch(0.60 0.13 215 / 0.55);--stage-light:oklch(0.60 0.13 215 / 0.22);
  --bar:oklch(0.60 0.13 215 / 0.75);
  --sans:'Archivo',ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,'SF Mono',Menlo,Consolas,monospace;
}
@media(prefers-color-scheme:dark){:root{
  --bg:oklch(0.185 0.006 70);--panel:oklch(0.225 0.007 70);--inset:oklch(0.265 0.008 70);
  --stripe:oklch(0.31 0.008 70);--line:oklch(0.33 0.008 70);--line2:oklch(0.31 0.008 70);
  --row:oklch(0.29 0.008 70);--line-strong:oklch(0.37 0.009 70);--axis:oklch(0.42 0.010 70);
  --scroll:oklch(0.38 0.008 70);
  --ink:oklch(0.95 0.006 85);--ink2:oklch(0.90 0.006 85);--ink3:oklch(0.82 0.006 82);
  --ink4:oklch(0.75 0.006 80);--dim:oklch(0.69 0.006 78);--dim2:oklch(0.62 0.006 78);
  --accent:oklch(0.74 0.13 48);--accent-hover:oklch(0.82 0.11 48);--accent2:oklch(0.74 0.11 215);
  --bad:oklch(0.70 0.15 30);--on-accent:oklch(0.17 0.006 70);--on-ink:oklch(0.17 0.006 70);
  --accent-soft:oklch(0.74 0.13 48 / 0.16);--area:oklch(0.74 0.13 48 / 0.16);
  --band:oklch(0.95 0.006 85 / 0.08);--trend:oklch(0.95 0.006 85 / 0.45);
  --stage-rem:oklch(0.74 0.11 215 / 0.55);--stage-light:oklch(0.74 0.11 215 / 0.28);
  --bar:oklch(0.74 0.11 215 / 0.75);
}}
html{font-feature-settings:'tnum' 1}
body{background:var(--bg);color:var(--ink3);font-family:var(--sans);font-size:15px;line-height:1.55;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
::-webkit-scrollbar{height:8px;width:8px}::-webkit-scrollbar-thumb{background:var(--scroll);border-radius:4px}

/* ── shell ── */
header{max-width:1180px;margin:0 auto;padding:26px clamp(14px,3vw,32px) 0;
  display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:14px}
.eyebrow{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.16em;
  color:var(--dim);display:flex;align-items:center;gap:8px}
.dot{width:9px;height:9px;border-radius:50%;background:var(--dim);flex:0 0 auto}
h1{font-family:var(--sans);font-weight:600;font-size:clamp(28px,3.6vw,44px);letter-spacing:-.025em;
  color:var(--ink);line-height:1.02;margin-top:8px}
h1 .of{color:var(--dim2);font-weight:400}
.sub{color:var(--dim);font-size:12.5px;margin-top:6px}
.hmeta{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.hright{text-align:right;font-family:var(--mono);font-size:11px;text-transform:uppercase;
  letter-spacing:.06em;color:var(--dim);line-height:1.9}
.hright .fresh{color:var(--accent2)}.hright .stale{color:var(--bad)}

nav{position:sticky;top:0;z-index:10;background:var(--bg);max-width:1180px;margin:14px auto 0;
  padding:0 clamp(14px,3vw,32px);display:flex;gap:2px;overflow-x:auto;
  border-bottom:1px solid var(--line)}
nav button{flex:0 0 auto;background:none;border:none;border-bottom:2px solid transparent;
  color:var(--dim);font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.1em;
  padding:14px 14px 12px;cursor:pointer;white-space:nowrap;margin-bottom:-1px;transition:color .12s}
nav button:hover:not(.on){color:var(--ink2)}
nav button.on{color:var(--ink);border-bottom-color:var(--accent)}
nav button.statusok.on{border-bottom-color:var(--accent2)}
nav button.statusok{color:var(--accent2)}
nav button.statusbad{color:var(--bad)}nav button.statusbad.on{border-bottom-color:var(--bad)}

main{max-width:1180px;margin:0 auto;padding:clamp(14px,1.8vw,22px) clamp(14px,3vw,32px) 40px}
.tab{display:none}.tab.on{display:block;animation:f .2s ease}
@keyframes f{from{opacity:0;transform:translateY(4px)}to{opacity:1}}
footer{max-width:1180px;margin:0 auto;padding:8px clamp(14px,3vw,32px) 60px;
  font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.08em;
  color:var(--dim2);line-height:1.9;border-top:1px solid var(--line);margin-top:10px;padding-top:20px}

/* ── primitives ── */
.card{background:var(--panel);border:1px solid var(--line);border-radius:4px;
  padding:clamp(16px,1.8vw,24px);margin-bottom:clamp(12px,1.4vw,18px)}
.card.hero{padding:clamp(18px,2vw,28px)}
.card h2{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.16em;
  color:var(--dim);margin-bottom:14px}
.big{font-family:var(--sans);font-weight:600;font-size:clamp(26px,3.2vw,38px);letter-spacing:-.02em;
  color:var(--ink);line-height:1.08}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.stat{background:var(--inset);border:1px solid var(--line2);border-radius:3px;padding:13px 14px}
.stat .n{font-family:var(--sans);font-size:22px;font-weight:600;letter-spacing:-.02em;color:var(--ink)}
.stat .l{font-family:var(--mono);color:var(--dim);font-size:10px;text-transform:uppercase;
  letter-spacing:.08em;margin-top:5px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:999px;
  font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.06em;
  background:var(--accent-soft);color:var(--accent)}
.pill.green{background:var(--accent-soft);color:var(--accent2)}
.pill.amber{background:var(--accent-soft);color:var(--accent)}
.pill.red{background:oklch(0.45 0.15 30 / .12);color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:14px}
.tablewrap{overflow-x:auto}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--row);vertical-align:top;color:var(--ink3)}
th{font-family:var(--mono);color:var(--dim);font-weight:500;font-size:10px;text-transform:uppercase;letter-spacing:.12em}
td.num{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink2)}
.note{color:var(--dim2);font-size:13px;line-height:1.6;margin-top:8px}
.note code,code{background:var(--inset);border:1px solid var(--line2);border-radius:3px;
  padding:1px 6px;font-family:var(--mono);font-size:12px;color:var(--ink3)}

/* colour semantics: accent2(blue)=good/stable, accent(rust)=attention, bad=bad */
.good{color:var(--accent2)}.warn{color:var(--accent)}.bad{color:var(--bad)}.muted{color:var(--dim2)}
.stat .n.good{color:var(--accent2)}.stat .n.warn{color:var(--accent)}.stat .n.bad{color:var(--bad)}.stat .n.muted{color:var(--dim2)}

/* buttons */
button.copy,.btn{background:var(--accent);color:var(--on-accent);border:none;border-radius:999px;
  padding:10px 18px;font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.06em;
  cursor:pointer;margin-top:12px;transition:background .12s}
button.copy:hover,.btn:hover{background:var(--accent-hover)}
.btn-outline{display:inline-block;background:none;border:1px solid var(--line-strong);color:var(--ink3);
  border-radius:999px;padding:9px 16px;font-family:var(--mono);font-size:11px;text-transform:uppercase;
  letter-spacing:.06em;cursor:pointer;text-decoration:none;transition:border-color .12s,color .12s}
.btn-outline:hover{border-color:var(--accent);color:var(--accent)}

/* time-range segmented control (Trends / hero) */
.tfbar{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.tfbar button{background:none;border:1px solid var(--line-strong);color:var(--dim);
  padding:7px 14px;border-radius:999px;font-family:var(--mono);font-size:11px;text-transform:uppercase;
  letter-spacing:.06em;cursor:pointer}
.tfbar button:hover:not(.on){border-color:var(--accent);color:var(--accent)}
.tfbar button.on{background:var(--ink);border-color:var(--ink);color:var(--on-ink)}
.dirtag{font-family:var(--mono);color:var(--dim2);font-size:10px;text-transform:uppercase;letter-spacing:.06em}

/* recovery signals */
.sig{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;
  padding:12px 0;border-bottom:1px solid var(--row)}
.sig:last-child{border:none}
.sig .v{font-weight:600;font-variant-numeric:tabular-nums;text-align:right}

/* callrow / method / adjust */
.callrow{margin-top:6px;font-size:14px;line-height:1.5}
.callrow strong{font-weight:600}
.callrow.good strong{color:var(--accent2)}.callrow.warn strong{color:var(--accent)}.callrow.muted strong{color:var(--dim2)}
.callrow .why{display:block;color:var(--ink4);font-size:13px;line-height:1.45;margin-top:3px;max-width:62ch}
.method{margin-top:5px;font-family:var(--mono);font-size:11px;line-height:1.5}
.method strong{color:var(--accent2)}.method span{color:var(--dim)}
.adjust{margin:12px 0 16px;padding:12px 14px;border-radius:3px;background:var(--inset);
  border-left:3px solid var(--dim)}
.adjust.good{border-color:var(--accent2)}.adjust.warn{border-color:var(--accent)}.adjust.bad{border-color:var(--bad)}
.adjust strong{font-size:15px;font-weight:600;color:var(--ink)}
.ad-rir{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);margin-top:3px}

/* meals */
.meal{border-left:2px solid var(--accent);padding:2px 0 2px 14px;margin-bottom:16px}
.meal .t{font-family:var(--mono);color:var(--accent);font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.meal .lbl{font-weight:600;font-size:16px;color:var(--ink);margin:3px 0}
.meal ul{list-style:none;display:flex;flex-direction:column;gap:3px;margin-top:6px}
.meal li{color:var(--ink3);padding:1px 0}

/* exercise rows */
.ex{display:flex;justify-content:space-between;gap:14px;padding:14px 0;border-bottom:1px solid var(--row)}
.ex:last-child{border:none}
.ex .nm{font-weight:600;font-size:16px;color:var(--ink)}
.ex .sc{font-family:var(--mono);color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.04em;margin-top:3px}
.ex .rt{font-family:var(--mono);color:var(--dim);font-size:11px;white-space:nowrap}

/* garmin sheet */
.gsheet{background:var(--inset);border:1px dashed var(--line-strong);border-radius:3px;padding:14px;
  font-family:var(--mono);font-size:12px;line-height:1.75;white-space:pre-wrap;overflow-x:auto;color:var(--ink3)}

/* tonnage bars */
.vbars{display:flex;gap:5px;align-items:flex-end;height:64px;margin:14px 0 4px}
.vbar{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%}
.vfill{width:74%;background:var(--bar);border-radius:2px 2px 0 0;min-height:2px}
.vlbl{font-family:var(--mono);font-size:8px;color:var(--dim2);margin-top:4px;white-space:nowrap}

/* sleep-stage proportional bar + legend */
.stagebar{display:flex;height:14px;border-radius:3px;overflow:hidden;margin:12px 0 10px;background:var(--inset)}
.stageseg{height:100%}
.stage-deep{background:var(--accent2)}.stage-rem{background:var(--stage-rem)}
.stage-light{background:var(--stage-light)}.stage-awake{background:var(--line)}
.stagelegend{display:flex;flex-wrap:wrap;gap:12px}
.stagelegend span{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:10px;
  text-transform:uppercase;letter-spacing:.05em;color:var(--dim)}
.stagelegend i{width:10px;height:10px;border-radius:2px;display:inline-block}

/* performance hero */
.metricsel{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px}
.herohead{display:flex;flex-wrap:wrap;align-items:baseline;gap:14px;margin-bottom:4px}
.heronum{font-family:var(--sans);font-weight:600;font-size:clamp(40px,5.2vw,60px);letter-spacing:-.03em;
  line-height:.95;color:var(--ink)}
.herounit{font-family:var(--mono);font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim)}
.herodelta{font-family:var(--sans);font-weight:600;font-size:clamp(22px,2.6vw,30px);letter-spacing:-.02em}
.heroverdict{color:var(--ink4);font-size:13px;line-height:1.5;margin:8px 0 14px;max-width:70ch}
.perfchart{display:flex;gap:8px;height:clamp(200px,24vw,280px)}
.perfyax{width:46px;display:flex;flex-direction:column;justify-content:space-between;
  font-family:var(--mono);font-size:9px;color:var(--dim2);text-align:right;padding:2px 0}
.perfplot{flex:1;position:relative;border-top:1px solid var(--line2);border-bottom:1px solid var(--axis)}
.perfplot svg{position:absolute;inset:0;width:100%;height:100%}
.perfmid{position:absolute;left:0;right:0;top:50%;border-top:1px dotted var(--line-strong)}
.prevchip{position:absolute;font-family:var(--mono);font-size:9px;text-transform:uppercase;letter-spacing:.05em;
  background:var(--panel);color:var(--dim);padding:1px 5px;transform:translateY(-50%);z-index:2;white-space:nowrap}
.perfxax{display:flex;justify-content:space-between;font-family:var(--mono);font-size:9px;
  color:var(--dim2);margin:6px 0 0 54px}

/* measurement form */
.mgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin-top:12px}
.mfield{display:flex;flex-direction:column;gap:4px;font-family:var(--mono);font-size:10px;
  text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
.mfield em{font-style:normal;opacity:.7}
.mfield input{background:var(--inset);border:1px solid var(--line);color:var(--ink);
  border-radius:3px;padding:9px 10px;font-family:var(--mono);font-size:14px;width:100%}
.mfield input:focus{outline:none;border-color:var(--accent)}

/* photos */
.photos{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
.photos img{width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:3px;border:1px solid var(--line);
  display:block;cursor:zoom-in}
.lightbox{position:fixed;inset:0;background:oklch(0.1 0 0 / .92);display:none;z-index:100;
  cursor:zoom-out;align-items:center;justify-content:center}
.lightbox.on{display:flex}
.lightbox img{max-width:96vw;max-height:96vh;object-fit:contain;border-radius:4px}
.lightbox .x{position:fixed;top:14px;right:20px;color:#fff;font-size:34px;cursor:pointer;line-height:1;font-weight:300}

/* tags */
.tag{display:inline-block;background:var(--inset);border:1px solid var(--line2);border-radius:3px;
  padding:3px 9px;font-family:var(--mono);font-size:11px;color:var(--ink3);margin:2px 4px 2px 0}
.spark{display:block}
.disclaimer{color:var(--dim2);font-size:12px;text-align:center;padding:16px;line-height:1.6}
"""

JS = """
function tab(id,btn){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  document.querySelectorAll('nav button').forEach(b=>b.classList.remove('on'));
  document.getElementById(id).classList.add('on');
  btn.classList.add('on');
  window.scrollTo(0,0);
}
function copyGarmin(){
  const el=document.getElementById('gsheet');
  navigator.clipboard.writeText(el.innerText).then(()=>{
    const b=document.getElementById('copybtn');b.innerText='Copied ✓';
    setTimeout(()=>b.innerText='Copy workout for Garmin Connect',1500);
  });
}
function togglePhotos(btn){
  // Photos are hidden by default; this reveals them on demand.
  const w=document.getElementById('photowrap');
  const shown=w.style.display!=='none';
  w.style.display=shown?'none':'block';
  btn.innerText=shown?'Show photos':'Hide photos';
}
async function uploadPhotos(input){
  // POST each file raw with its name in X-Filename. The server converts HEIC->JPG,
  // stores under today's date, and re-renders; we reload to show the new set.
  const status=document.getElementById('upstatus');
  const files=[...input.files];
  if(!files.length) return;
  status.textContent='Uploading '+files.length+' photo'+(files.length>1?'s':'')+'\\u2026';
  let ok=0, err='';
  for(const f of files){
    try{
      const r=await fetch('/upload/photo',{method:'POST',
        headers:{'X-Filename':f.name},body:f});
      const j=await r.json().catch(()=>({}));
      if(r.ok&&j.ok){ok++;} else {err=(j&&j.error)||('HTTP '+r.status);}
    }catch(e){err=''+e;}
  }
  input.value='';
  if(ok){status.textContent=ok+' uploaded \\u2713 reloading\\u2026';
    setTimeout(()=>location.reload(),700);}
  else{status.textContent='Upload failed: '+err+' (is the portal served by rapha serve?)';}
}
function _drawLine(el, series, color){
  const vals=series.map(p=>p[1]).filter(v=>v!=null);
  if(vals.length<2){ el.innerHTML='<span class="note">not enough data in this range</span>'; return null; }
  const lo=Math.min(...vals), hi=Math.max(...vals), rng=(hi-lo)||1, w=320, h=48, n=vals.length;
  const pts=vals.map((v,i)=>((i/(n-1)*w).toFixed(1)+','+(h-(v-lo)/rng*h).toFixed(1))).join(' ');
  el.innerHTML='<svg width="100%" height="'+(h+8)+'" viewBox="0 0 '+w+' '+(h+8)+'" '
    +'preserveAspectRatio="none" style="max-width:340px"><polyline fill="none" stroke="'
    +color+'" stroke-width="2" stroke-linejoin="round" points="'+pts+'"/></svg>';
  return {latest:vals[vals.length-1], avg:vals.reduce((a,b)=>a+b,0)/vals.length};
}
function perfRange(tf, btn){
  document.querySelectorAll('#perfbar button').forEach(b=>b.classList.remove('on'));
  if(btn) btn.classList.add('on');
  const days={'7d':7,'30d':30,'90d':90,'1y':365,'all':100000}[tf]||30;
  const cutoff=Date.now()-days*86400000;
  document.querySelectorAll('[data-metric]').forEach(el=>{
    const key=el.getAttribute('data-metric'), unit=el.getAttribute('data-unit')||'';
    const all=(window.PERF&&window.PERF[key])||[];
    const s=all.filter(p=>Date.parse(p[0])>=cutoff);
    const pc=el.querySelector('.pc'), pv=el.querySelector('.pv'), pa=el.querySelector('.pa');
    const r=_drawLine(pc, s, 'var(--accent)');
    if(r){ pv.textContent=(Math.round(r.latest*10)/10)+unit;
      pa.textContent='avg '+(Math.round(r.avg*10)/10)+unit+' \\u00b7 '+s.length+' readings'; }
    else { pv.textContent='\\u2014'; pa.textContent=''; }
  });
}
function _drawIntraday(){
  const el=document.getElementById('intraday-hr'); if(!el) return;
  const hr=((window.PERF_INTRADAY||{}).hr)||[];
  _drawLine(el, hr, 'var(--red)');
}
function toggleMeasForm(btn){
  const f=document.getElementById('measform');
  const shown=f.style.display!=='none';
  f.style.display=shown?'none':'block';
  btn.textContent=shown?'Add / edit measurement':'Hide form';
  if(!shown){ const d=document.getElementById('m_date');
    if(d&&!d.value) d.value=new Date().toISOString().slice(0,10); }
}
async function saveMeasurement(btn){
  const status=document.getElementById('mstatus');
  const attrs=['weight','waist','neck','chest','shoulders','arm','thigh','hip','calf','wingspan'];
  const body={date:(document.getElementById('m_date')||{}).value||''};
  attrs.forEach(function(a){ const el=document.getElementById('m_'+a);
    if(el&&el.value!=='') body[a]=el.value; });
  const n=document.getElementById('m_notes'); if(n&&n.value) body.notes=n.value;
  status.textContent='Saving\\u2026';
  try{
    const r=await fetch('/measurement',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const j=await r.json().catch(function(){return {};});
    if(r.ok&&j.ok){ status.textContent='Saved \\u2713 reloading\\u2026';
      setTimeout(function(){location.reload();},600); }
    else{ status.textContent='Failed: '+((j&&j.error)||('HTTP '+r.status)); }
  }catch(e){ status.textContent='Error: '+e+' (is the portal served by rapha serve?)'; }
}
function openLightbox(src){
  const lb=document.getElementById('lightbox'); if(!lb) return;
  document.getElementById('lightbox-img').src=src;
  lb.classList.add('on');
}
function closeLightbox(){
  const lb=document.getElementById('lightbox'); if(lb) lb.classList.remove('on');
}
document.addEventListener('keydown',function(e){ if(e.key==='Escape') closeLightbox(); });
function _fmtAge(sec){
  if(sec==null) return 'never';
  if(sec<60) return sec+'s ago';
  if(sec<3600) return Math.floor(sec/60)+' min ago';
  if(sec<86400){ const h=Math.floor(sec/3600), m=Math.floor((sec%3600)/60);
    return h+'h'+(m?' '+m+'m':'')+' ago'; }
  return Math.floor(sec/86400)+'d ago';
}
function _applyStatus(st){
  const freshMin=st.fresh_minutes||60, age=st.age_seconds;
  const fresh=(age!=null)&&(age<freshMin*60);
  const col=fresh?'var(--accent)':'var(--red)';
  ['navdot','statusdot'].forEach(function(id){
    const e=document.getElementById(id); if(e) e.style.background=col; });
  const navbtn=document.getElementById('tab-datastatus');
  if(navbtn){ navbtn.classList.toggle('statusok',fresh);
    navbtn.classList.toggle('statusbad',!fresh); }
  const t=document.getElementById('statustext'), sub=document.getElementById('statussub');
  if(t){ t.textContent=age==null?'No pull recorded yet':(fresh?'Data is current':'Data is stale');
    t.style.color=col; }
  if(sub){ sub.textContent=age==null
    ?'Open the browser session below and the hourly pull will start filling this in.'
    :(fresh?('Last pull was within '+freshMin+' minutes.')
           :('Last pull was over '+freshMin+' minutes ago — a refresh is due.')); }
  window.__lastPullAt=st.last_pull_at||null;
  const lp=document.getElementById('lastpull');
  if(lp) lp.textContent=st.last_pull_at?st.last_pull_at.replace('T',' '):'\\u2014';
  const pa=document.getElementById('pullage'); if(pa) pa.textContent=_fmtAge(age);
  const cs=document.getElementById('chromestate');
  if(cs&&st.chrome_up!=null){ cs.innerHTML=st.chrome_up
    ?'<span style="color:var(--accent)">\\u25cf</span> A Garmin browser session is open \\u2014 a pull can run.'
    :'<span style="color:var(--red)">\\u25cf</span> No browser session detected. Open one below so pulls can run.'; }
}
async function refreshStatus(){
  try{ const r=await fetch('/pull-status',{cache:'no-store'});
    if(r.ok){ _applyStatus(await r.json()); return; } }catch(e){}
  if(window.DATA_STATUS) _applyStatus(window.DATA_STATUS);
}
async function forcePull(btn){
  const st=document.getElementById('pullnowstatus');
  const before=window.__lastPullAt||null;
  btn.disabled=true; st.textContent='Starting pull\\u2026';
  try{
    const r=await fetch('/pull-now',{method:'POST'});
    const j=await r.json().catch(function(){return {};});
    if(!(r.ok&&j.ok)){ st.textContent='Failed: '+((j&&j.error)||('HTTP '+r.status));
      btn.disabled=false; return; }
  }catch(e){ st.textContent='Error: '+e+' (is the portal served by rapha serve?)';
    btn.disabled=false; return; }
  st.textContent='Pull running\\u2026 (about a minute)';
  let tries=0;
  const iv=setInterval(async function(){
    tries++;
    try{ const r=await fetch('/pull-status',{cache:'no-store'});
      if(r.ok){ const s=await r.json(); _applyStatus(s);
        if(s.last_pull_at && s.last_pull_at!==before){ clearInterval(iv);
          btn.disabled=false; st.textContent='Pull complete \\u2713'; return; } } }catch(e){}
    if(tries>=30){ clearInterval(iv); btn.disabled=false;
      st.textContent='Still running, or it failed — if the dot stays red, open the '
        +'Garmin browser session below and try again.'; }
  },4000);
}
async function launchChrome(btn){
  const st=document.getElementById('launchstatus'); st.textContent='Opening Chrome\\u2026';
  try{ const r=await fetch('/launch-chrome',{method:'POST'});
    const j=await r.json().catch(function(){return {};});
    st.textContent=(r.ok&&j.ok)?(j.message||'Chrome opening\\u2026')
      :('Failed: '+((j&&j.error)||('HTTP '+r.status))); }
  catch(e){ st.textContent='Error: '+e+' (is the portal served by rapha serve?)'; }
  setTimeout(refreshStatus,3000);
}
window.addEventListener('DOMContentLoaded',function(){ refreshStatus();
  setInterval(refreshStatus,60000); });
window.addEventListener('DOMContentLoaded',function(){
  _drawIntraday();
  const b=document.querySelector('#perfbar button.def'); if(b) b.click();
});
"""


def _spark(series: list, *, w=260, h=40, color="var(--accent)", lower_better=False) -> str:
    """A tiny inline SVG sparkline. Series is [(label, value), ...]."""
    vals = [v for _, v in series if v is not None]
    if len(vals) < 2:
        return '<span class="note">not enough data yet</span>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = " ".join(
        f"{round(i / (n - 1) * w, 1)},{round(h - (v - lo) / rng * h, 1)}"
        for i, v in enumerate(vals)
    )
    last = vals[-1]
    cx = w
    cy = h - (last - lo) / rng * h
    return (
        f'<svg class="spark" width="{w}" height="{h + 6}" viewBox="0 0 {w} {h + 6}">'
        f'<polyline fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linejoin="round" points="{pts}"/>'
        f'<circle cx="{round(cx, 1)}" cy="{round(cy, 1)}" r="3" fill="{color}"/></svg>'
    )


def _weight_chart(wv: dict, *, w=560, h=130) -> str:
    """Weigh-ins as a solid line with dots, plus the dotted trend estimate.

    Both series share one date-based x-axis and one kg y-axis, so the dotted line
    sits honestly against the real points instead of a separate mini-plot.
    """
    from datetime import date as _date

    actual = [(_date.fromisoformat(d), v) for d, v in wv.get("actual", [])]
    est = [(_date.fromisoformat(d), v) for d, v in wv.get("estimate", [])]
    if not actual:
        return '<span class="note">No weigh-ins yet</span>'

    all_dates = [d for d, _ in actual] + [d for d, _ in est]
    all_vals = [v for _, v in actual] + [v for _, v in est]
    x0, x1 = min(all_dates), max(all_dates)
    span = (x1 - x0).days or 1
    lo, hi = min(all_vals), max(all_vals)
    pad = ((hi - lo) or 1) * 0.18
    lo, hi = lo - pad, hi + pad
    rng = (hi - lo) or 1

    def px(d):
        return round((d - x0).days / span * (w - 8) + 4, 1)

    def py(v):
        return round(h - 16 - (v - lo) / rng * (h - 28), 1)

    apoly = " ".join(f"{px(d)},{py(v)}" for d, v in actual)
    dots = "".join(f'<circle cx="{px(d)}" cy="{py(v)}" r="2.6" fill="var(--accent)"/>'
                   for d, v in actual)
    est_line = ""
    if len(est) >= 2:
        epoly = " ".join(f"{px(d)},{py(v)}" for d, v in est)
        est_line = (f'<polyline points="{epoly}" fill="none" stroke="var(--dim)" '
                    f'stroke-width="1.6" stroke-dasharray="5,4"/>')
    # today guide + first/last value labels
    today = _date.today()
    tx = px(today) if x0 <= today <= x1 else None
    guide = (f'<line x1="{tx}" y1="4" x2="{tx}" y2="{h - 12}" stroke="var(--line)" '
             f'stroke-width="1" stroke-dasharray="2,3"/>') if tx is not None else ""
    y_hi = f'<text x="2" y="12" fill="var(--dim)" font-size="10">{round(hi,1)} kg</text>'
    y_lo = f'<text x="2" y="{h-4}" fill="var(--dim)" font-size="10">{round(lo,1)} kg</text>'
    return (
        f'<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" '
        f'preserveAspectRatio="none" style="max-width:100%">'
        f'{guide}{est_line}'
        f'<polyline points="{apoly}" fill="none" stroke="var(--accent)" '
        f'stroke-width="2" stroke-linejoin="round"/>{dots}{y_hi}{y_lo}</svg>'
        '<div class="note" style="margin-top:4px">'
        '<span style="color:var(--accent)">●</span> weigh-ins &nbsp; '
        '<span style="color:var(--dim)">– – –</span> trend estimate</div>'
    )


def _stat(n: Any, label: str, cls: str = "") -> str:
    ncls = f"n {cls}".strip()
    return f'<div class="stat"><div class="{ncls}">{_e(n)}</div><div class="l">{_e(label)}</div></div>'


# ── tabs ─────────────────────────────────────────────────────────────────────

def _vitals_card(v: dict | None) -> str:
    """Body Battery, sleep score + stages, and HRV status — the overnight detail behind
    the recovery light, from data the pull already had."""
    if not v or not v.get("available"):
        return ""

    def hm(sec):
        return f"{sec // 3600}h{(sec % 3600) // 60:02d}m" if sec else "—"

    bb = v.get("body_battery", {})
    bb_stat = (f'{bb.get("low", "—")}–{bb.get("high", "—")}'
               if bb.get("high") is not None else "—")
    score = v.get("sleep_score")
    score_cls = ("good" if score and score >= 80 else
                 "warn" if score and score >= 60 else "bad" if score else "muted")
    st = v.get("sleep_stages", {})
    stage_txt = (f'Deep {hm(st.get("deep"))} · REM {hm(st.get("rem"))} · '
                 f'Light {hm(st.get("light"))} · Awake {hm(st.get("awake"))}')
    hrv = v.get("hrv_status")
    hrv_cls = {"BALANCED": "good", "UNBALANCED": "warn", "LOW": "bad"}.get(hrv, "muted")
    hrv_txt = hrv.title() if hrv else "—"

    return f"""
  <div class="card">
    <h2>Overnight</h2>
    <div class="row">
      {_stat(score if score is not None else "—", "Sleep score", score_cls)}
      {_stat(bb_stat, "Body Battery")}
      {_stat(hrv_txt, "HRV status", hrv_cls)}
    </div>
    <div class="note">{_e(stage_txt)}</div>
  </div>"""


def _bold(escaped: str) -> str:
    """`**x**` -> bold, on already-escaped text (no regex, no backslash escapes)."""
    parts = escaped.split("**")
    return "".join(seg if i % 2 == 0 else f"<strong>{seg}</strong>"
                   for i, seg in enumerate(parts))


def _md_lite(text: str) -> str:
    """Minimal markdown for a coach note: paragraphs, bold, headings, - bullets. Escaped
    first, so the note is never markup injection even though Claude authored it."""
    out = []
    for block in text.strip().split(chr(10) * 2):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if all(ln.startswith(("-", "*")) for ln in lines):
            items = "".join(f"<li>{_bold(_e(ln[1:].strip()))}</li>" for ln in lines)
            out.append(f'<ul style="margin:0 0 10px;padding-left:18px">{items}</ul>')
        elif lines[0].startswith("#"):
            out.append(f'<h3 style="margin:2px 0 8px">'
                       f'{_bold(_e(lines[0].lstrip("#").strip()))}</h3>')
        else:
            out.append(f'<p style="margin:0 0 10px">{_bold(_e(" ".join(lines)))}</p>')
    return "".join(out)


def _coach_card(coach: dict) -> str:
    """The daily coach read. A fresh Claude-authored note leads; otherwise the always-
    fresh templated paragraphs stand in, so the card is never empty or stale-by-surprise."""
    authored = coach.get("authored")
    if authored and authored.get("fresh"):
        body = _md_lite(authored["text"])
        return f"""
  <div class="card" style="border-left:3px solid var(--accent)">
    <h2>Your day, in plain terms</h2>
    {body}
    <div class="note">Written by Claude from today’s numbers — an observation, not
      a medical opinion. Every call is yours.</div>
  </div>"""

    paras = "".join(f'<p style="margin:0 0 10px">{_e(p)}</p>'
                    for p in coach.get("paragraphs", []))
    if not paras:
        return ""
    stale = ""
    if authored and not authored.get("fresh"):
        stale = (f'<div class="note">A written coach note from {_e(authored["written"])} '
                 "is on file but out of date — showing today’s computed read "
                 "instead.</div>")
    return f"""
  <div class="card" style="border-left:3px solid var(--accent)">
    <h2>Your day, in plain terms</h2>
    {paras}
    {stale}
    <div class="note">Written from today’s numbers — an observation, not a medical
      opinion. Every call is yours.</div>
  </div>"""


def _today_tab(b: dict) -> str:
    ov = b["overview"]
    rec = ov["recovery"]
    tr = b.get("training", {})
    meals = b.get("meals", {})

    sig_rows = ""
    for s in rec["signals"]:
        cls = "good" if s["good"] else ("bad" if s["good"] is False else "warn")
        hib = s.get("higher_is_better", True)
        dir_txt = "↑ higher is better" if hib else "↓ lower is better"
        recent = s.get("recent") or ""
        recent_html = (
            f'<div style="color:var(--dim);font-size:11px;font-weight:400;'
            f'margin-top:2px;text-align:right">{_e(recent)}</div>' if recent else "")
        sig_rows += (
            f'<div class="sig"><span>{_e(s["label"])} '
            f'<span style="color:var(--dim);font-size:11px;font-weight:400">'
            f'{dir_txt}</span></span>'
            f'<span class="v {cls}">{_e(s["note"])}{recent_html}</span></div>'
        )

    first_meal = meals["meals"][0] if meals.get("meals") else None
    train_line = (
        "Rest day" if tr.get("rest")
        else f'Day {tr.get("day","")}: <strong>{_e(tr.get("focus",""))}</strong> '
             f'({len(tr.get("exercises",[]))} exercises)'
    )

    coach = b.get("coach", {})
    coach_card = _coach_card(coach)

    sw = ov.get("sheet_switch")
    switch_banner = ""
    if sw and sw.get("days_until") is not None and sw["days_until"] <= 10:
        d = sw["days_until"]
        when = ("today" if d <= 0 else "tomorrow" if d == 1 else f"in {d} days")
        switch_banner = (
            '<div class="card" style="border-left:3px solid var(--cyan)">'
            '<h2>Programme update</h2>'
            f'<div>Your training sheet advances to <strong>Sheet {_e(sw["sheet"])}</strong> '
            f'{when} — week {_e(sw["starts_week"])}, {_e(sw["starts_on"])}. The portal '
            'switches automatically; the new workouts are being set up in Garmin.</div></div>')

    sheet_line = ""
    if ov.get("sheet_number") and ov.get("week"):
        sheet_line = (f'<div class="note">Sheet {_e(ov["sheet_number"])} · '
                      f'week {_e(ov["week"])} of 8</div>')

    return f"""
<div class="tab on" id="today">
  <div class="card">
    <h2>Today · Day {ov["day_of_60"]} of 60</h2>
    <div class="pill {rec['status']}">{_recovery_emoji(rec['status'])} {_e(rec['headline'])}</div>
    <div style="margin-top:14px">{sig_rows}</div>
  </div>
  {_vitals_card(b.get("vitals"))}
  {switch_banner}
  {coach_card}
  <div class="row">
    <div class="card" style="flex:1;min-width:240px">
      <h2>Train</h2>
      <div>{train_line}</div>
      {sheet_line}
      <div class="note">{_e(tr.get("progression","")[:150])}{'…' if tr.get('progression') else ''}</div>
    </div>
    <div class="card" style="flex:1;min-width:240px">
      <h2>Eat · {meals.get('target_kcal','—')} kcal · {meals.get('protein_g','—')} g protein</h2>
      <div class="pill {'green' if meals.get('is_cut') else 'amber'}">{_e(meals.get('direction','').upper() or '—')}</div>
      {f'<div class="note"><strong>{_e(first_meal["time"])}</strong> — {_e(first_meal["label"])}: {_e("; ".join(str(it["grams"]) + "g " + it["food"] for it in first_meal.get("items", [])))}</div>' if first_meal else ''}
    </div>
  </div>
</div>"""


def _recovery_emoji(status: str) -> str:
    return {"green": "●", "amber": "●", "red": "●"}.get(status, "●")


def _method_line(method: dict | None) -> str:
    """A technique cue (isometria, negative emphasis, …) when the movement names one."""
    if not method:
        return ""
    return (f'<div class="method"><strong>{_e(method["label"])}</strong> '
            f'<span>{_e(method["cue"])}</span></div>')


def _call_line(call: dict | None) -> str:
    """The double-progression call for one exercise: what load to try, and why.

    Green = add a plate, amber = hold and build in, grey = establish the load. The
    load is always framed as a suggestion the lifter confirms by feel (M17).
    """
    if not call:
        return ""
    dec = call.get("decision")
    gated = call.get("gated")
    if dec == "progress" and gated and call.get("last_kg") is not None:
        cls = "warn"
        head = f'→ Hold {call["last_kg"]:g} kg today (recovery)'
    elif dec == "progress" and gated:
        cls, head = "warn", "→ Hold today (recovery)"
    elif dec == "progress" and call.get("suggested_kg") is not None:
        cls, head = "good", f'↗ Try {call["suggested_kg"]:g} kg'
        if call.get("last_kg") is not None:
            head += f' (last {call["last_kg"]:g} kg × {call["target_reps"]})'
    elif dec == "progress":                       # bodyweight
        cls, head = "good", "↗ Add reps / harder variation"
    elif dec == "hold":
        cls = "warn"
        head = (f'→ Hold {call["last_kg"]:g} kg' if call.get("last_kg") is not None
                else "→ Hold")
    else:                                          # establish
        cls, head = "muted", "○ Find your working load"
    return (f'<div class="callrow {cls}"><strong>{_e(head)}</strong>'
            f'<span class="why">{_e(call.get("reasoning",""))}</span></div>')


def _adjustment_banner(adj: dict | None) -> str:
    """The recovery-driven session adjustment, as a coloured banner above the exercises."""
    if not adj:
        return ""
    cls = {"green": "good", "amber": "warn", "red": "bad"}.get(adj.get("readiness"), "muted")
    return (f'<div class="adjust {cls}"><strong>{_e(adj.get("headline",""))}</strong>'
            f'<div class="ad-rir">Leave {_e(adj.get("reps_in_reserve",""))}</div>'
            f'<div class="note">{_e(adj.get("detail",""))}</div></div>')


def _training_tab(b: dict) -> str:
    tr = b.get("training", {})
    if not tr.get("available"):
        return '<div class="tab" id="training"><div class="card">No protocol extracted yet.</div></div>'
    if tr.get("rest"):
        return (f'<div class="tab" id="training"><div class="card"><h2>Training</h2>'
                f'<div class="big">Rest day</div><div class="note">{_e(tr.get("note",""))}</div>'
                '</div></div>')

    ex_rows = ""
    for ex in tr["exercises"]:
        rest = f'{ex["rest_s"]}s rest' if ex.get("rest_s") else ""
        warn = (f'<div class="note bad">⚠ {_e("; ".join(ex["issues"]))}</div>'
                if ex.get("issues") else "")
        ex_rows += (
            f'<div class="ex"><div><div class="nm">{_e(ex["name"].title())}</div>'
            f'<div class="sc">{ex["sets"]} sets · reps {_e(ex["scheme"])}</div>'
            f'{_call_line(ex.get("call"))}{_method_line(ex.get("method"))}{warn}</div>'
            f'<div class="rt">{rest}</div></div>'
        )

    g = tr.get("garmin", {})
    sheet_lines = [f'Workout: {g.get("workout_name","")}', ""]
    for i, s in enumerate(g.get("steps", []), 1):
        sheet_lines.append(f'{i:>2}. {s["exercise"].title()}  →  {s["garmin_name"]}  ({s["scheme"]} reps)')
    if g.get("unmapped"):
        sheet_lines += ["", "Not auto-mapped (enter manually): " + ", ".join(g["unmapped"])]
    sheet = _e("\n".join(sheet_lines))

    return f"""
<div class="tab" id="training">
  <div class="card">
    <h2>{_e(tr["level"])} · Day {tr["day"]} · {_e(tr["focus"])}</h2>
    {_adjustment_banner(tr.get("adjustment"))}
    {ex_rows}
    <div class="note"><strong>Progression:</strong> {_e(tr["progression"])}</div>
    <div class="note"><strong>Cadence:</strong> every rep at a controlled tempo — a rep only counts toward the target if the form held; a set rushed with momentum is a different, lesser stimulus (M15/M17).</div>
  </div>
  <div class="card">
    <h2>Set this in Garmin Connect</h2>
    <div class="note">Open <strong>Garmin Connect → Training → Workouts → Create a Workout</strong>
      (Strength), then add each step below. Or ask Claude in Chrome to enter it for you —
      paste this sheet.</div>
    <div class="gsheet" id="gsheet">{sheet}</div>
    <button class="copy" id="copybtn" onclick="copyGarmin()">Copy workout for Garmin Connect</button>
  </div>
  <div class="card">
    <h2>All workouts — set up Garmin once</h2>
    <div class="note">The full rotation (all training days of this sheet) as one sheet
      you build once in Garmin Connect. Open it, or hand it to Claude in Chrome.</div>
    <div style="margin-top:10px">
      <a class="copy" style="text-decoration:none;display:inline-block"
         href="/workouts.md" target="_blank">Open all workouts (workouts.md)</a>
      &nbsp;<a class="tag" href="/workouts.json" target="_blank"
         style="padding:8px 12px">workouts.json</a>
    </div>
  </div>
</div>"""


def _meals_tab(b: dict) -> str:
    m = b.get("meals", {})
    meal_html = ""
    for meal in m.get("meals", []):
        items = "".join(
            f'<li><strong>{_e(it["grams"])} g</strong> {_e(it["food"])} '
            f'<span style="color:var(--dim)">· {_e(it["kcal"])} kcal</span></li>'
            for it in meal.get("items", [])
        )
        meal_html += (
            f'<div class="meal"><div class="t">{_e(meal["time"])} · '
            f'{_e(meal["kcal"])} kcal · {_e(meal["protein_g"])} g protein</div>'
            f'<div class="lbl">{_e(meal["label"])}</div><ul>{items}'
            f'<li style="color:var(--accent)">+ {_e(meal.get("free",""))}</li></ul></div>'
        )
    principles = "".join(f"<li>{_e(p)}</li>" for p in m.get("principles", []))
    supp_html = "".join(
        f'<div class="meal"><div class="lbl">{_e(s["name"])} — {_e(s["dose"])}</div>'
        f'<div class="note">{_e(s["when"])}</div>'
        f'<div class="note" style="font-size:11px">{_e(s["source"])}</div></div>'
        for s in m.get("supplements", [])
    ) or '<div class="note">—</div>'

    return f"""
<div class="tab" id="meals">
  <div class="card">
    <h2>Today · hits your target exactly</h2>
    <div class="row">
      {_stat(str(m.get("actual_kcal","—")) + " kcal", f"target {m.get('target_kcal','—')}")}
      {_stat(str(m.get("actual_protein_g","—")) + " g", "protein")}
      {_stat(str(m.get("carb_g","—")) + " g", "carbs")}
      {_stat(str(m.get("fat_g","—")) + " g", "fat")}
    </div>
    <div class="note"><strong>Split:</strong> {_e(m.get("split",""))} &nbsp;·&nbsp;
      Measured TDEE {_e(m.get("tdee_kcal","—"))} kcal, {_e(m.get("deficit_pct",""))}% deficit</div>
    <div style="margin-top:8px"><span class="pill {'green' if m.get('is_cut') else 'amber'}">{_e(m.get("direction","").upper())}</span></div>
    <div class="note">{_e(m.get("direction_why",""))}</div>
  </div>
  <div class="card">
    <h2>Meals · weighed portions, timed to your training</h2>
    {meal_html}
  </div>
  <div class="card">
    <h2>Supplements</h2>
    {supp_html}
  </div>
  <div class="card">
    <h2>How to use it</h2>
    <ul class="note" style="padding-left:18px">{principles}</ul>
  </div>
</div>"""


# The daily metrics the timeframe selector windows. Each: (key, label, unit,
# lower_is_better). The JS reads window.PERF[key] and redraws for the active range.
_PERF_METRICS = [
    ("tdee", "Energy burned (TDEE)", " kcal", False),
    ("hrv", "HRV — overnight", " ms", False),
    ("rhr", "Resting heart rate", " bpm", True),
    ("sleep", "Sleep", " h", False),
    ("stress", "Stress", "", True),
    ("steps", "Steps", "", False),
    ("weight", "Weight", " kg", False),
]


def _load_card(lb: dict | None) -> str:
    """Acute:chronic training-load ratio — a ramp gauge, coloured by the ACWR band."""
    if not lb or lb.get("ratio") is None:
        return ""
    band = lb.get("band", "unknown")
    labels = {"detraining": ("Detraining", "warn"), "optimal": ("Optimal ramp", "good"),
              "building": ("Building", "good"), "high": ("Ramping hard", "warn"),
              "spike": ("Load spike", "bad"), "unknown": ("—", "muted")}
    text, cls = labels.get(band, ("—", "muted"))
    ratio = lb["ratio"]
    reliable = lb.get("reliable")
    caveat = ("" if reliable else
              '<div class="note">Still building a 4-week baseline — the ratio reads high '
              'until there is enough history behind it.</div>')
    return f"""
  <div class="card">
    <h2>Load balance</h2>
    <div class="row">
      {_stat(f"{ratio:g}", "Acute : chronic", cls)}
      {_stat(lb.get("acute", 0), "This week (load)")}
      {_stat(lb.get("chronic_weekly", 0), "4-wk weekly avg")}
      {_stat(text, "Reading", cls)}
    </div>
    <div class="note">This week's training load against the four-week average you've built
      a base for. Around 0.8–1.3 is the sweet spot where fitness rises without the injury
      risk that climbs when a week spikes far above your base — an observation, not a rule;
      a hard block breaches it on purpose.</div>
    {caveat}
  </div>"""


def _volume_card(v: dict) -> str:
    """Weekly tonnage bars + hard sets, and the adherence line — the 'more work over
    time' signal and the 'am I showing up' signal, side by side."""
    if not v.get("available"):
        return ""
    weeks = v.get("weeks", [])
    tvals = [w["tonnage_kg"] for w in weeks]
    peak = max(tvals) if tvals else 0
    bars = ""
    for w in weeks:
        h = round((w["tonnage_kg"] / peak) * 46) if peak else 0
        lbl = w["start"][5:]
        bars += (f'<div class="vbar" title="{lbl}: {w["tonnage_kg"]:g} kg · '
                 f'{w["hard_sets"]} hard sets · {w["sessions"]} sessions">'
                 f'<div class="vfill" style="height:{h}px"></div>'
                 f'<div class="vlbl">{_e(lbl)}</div></div>')
    tw = v.get("this_week", {})
    tr = v.get("trend_kg")
    trend_txt = ("—" if tr is None
                 else f'{"+" if tr >= 0 else ""}{round(tr/1000, 1)} t vs 12 wks ago')

    a = v.get("adherence", {})
    adh = ""
    if a.get("available"):
        rate = a.get("rate")
        rate_pct = f'{round(rate * 100)}%' if rate is not None else "—"
        since = a.get("days_since_last")
        since_txt = ("trained today" if since == 0
                     else f'{since} d since last' if since is not None else "—")
        adh = (
            '<div class="row" style="margin-top:12px">'
            f'{_stat(f"{a.get('done',0)}/{a.get('expected',0)}", "Sessions (4wk)")}'
            f'{_stat(rate_pct, "Adherence")}'
            f'{_stat(a.get("streak_weeks", 0), "Week streak")}'
            f'{_stat(since_txt, "Last session")}'
            '</div>')

    return f"""
  <div class="card">
    <h2>Volume &amp; adherence</h2>
    <div class="row">
      {_stat(f'{tw.get("tonnage_kg", 0):g} kg', "Tonnage this week")}
      {_stat(tw.get("hard_sets", 0), "Hard sets")}
      {_stat(tw.get("sessions", 0), "Sessions")}
      {_stat(trend_txt, "Trend")}
    </div>
    <div class="vbars">{bars}</div>
    <div class="note">Weekly tonnage (reps × load). The compounding currency of a
      recomposition block — a rising line is real progress no single session shows.
      Hard sets are working sets taken at a real load.</div>
    {adh}
  </div>"""


def _performance_tab(b: dict) -> str:
    import json as _json

    p = b.get("performance", {})
    pr = b.get("progress", {})

    perf_series = {
        "tdee": p.get("tdee_series", []),
        "hrv": p.get("hrv_series", []),
        "rhr": p.get("rhr_series", []),
        "sleep": p.get("sleep_series", []),
        "stress": p.get("stress_series", []),
        "steps": p.get("steps_series", []),
        "weight": pr.get("weight_view", {}).get("actual", []),
    }
    perf_json = _json.dumps(perf_series)
    intraday_json = _json.dumps(p.get("intraday") or {})

    metric_cards = ""
    for key, label, unit, lower in _PERF_METRICS:
        metric_cards += (
            f'<div class="card" data-metric="{key}" data-unit="{_e(unit)}" '
            f'data-lower="{1 if lower else 0}">'
            f'<h2>{_e(label)} <span class="dirtag">'
            f'{"↓ lower is better" if lower else "↑ higher is better" if key in ("hrv","steps") else ""}'
            f'</span></h2>'
            '<div class="row" style="align-items:center">'
            '<div><div class="big pv">—</div>'
            '<div class="l pa" style="color:var(--dim);font-size:12px"></div></div>'
            '<div class="pc" style="flex:1;text-align:right;min-width:0"></div>'
            '</div></div>'
        )

    act_rows = ""
    for a in p.get("recent_activities", []):
        act_rows += (
            f'<tr><td>{_e(a["date"])}</td><td>{_e(a["kind"].title())}</td>'
            f'<td class="num">{_e(a["duration_min"])} min</td>'
            f'<td class="num">{_e(a["avg_hr"] or "—")}</td>'
            f'<td class="num">{_e(a["kcal"] or "—")}</td></tr>'
        )

    return f"""
<div class="tab" id="performance">
  <script>window.PERF={perf_json};window.PERF_INTRADAY={intraday_json};</script>
  <div class="card">
    <h2>Snapshot</h2>
    <div class="row">
      {_stat(p.get("vo2max","—"), "VO₂ max")}
      {_stat(p.get("strength_sessions","—"), "Strength (12wk)")}
      {_stat(p.get("cardio_sessions","—"), "Cardio (12wk)")}
      {_stat(p.get("typical_train_time","—"), "Usual start")}
    </div>
  </div>
  {_volume_card(b.get("volume", {}))}
  {_load_card((b.get("volume", {}) or {}).get("load"))}
  {_intraday_card(p.get("intraday"))}
  <div class="card" style="position:sticky;top:0;z-index:5">
    <h2>Trends over time</h2>
    <div id="perfbar" class="tfbar">
      <button onclick="perfRange('7d',this)">7D</button>
      <button class="on def" onclick="perfRange('30d',this)">30D</button>
      <button onclick="perfRange('90d',this)">90D</button>
      <button onclick="perfRange('1y',this)">1Y</button>
      <button onclick="perfRange('all',this)">All</button>
    </div>
    <div class="note">A line that starts partway in just means that metric hasn't been
      recorded that far back yet — history fills in as the watch keeps syncing.</div>
  </div>
  {metric_cards}
  <div class="card"><h2>Recent sessions</h2>
    <table><tr><th>Date</th><th>Type</th><th class="num">Time</th><th class="num">Avg HR</th><th class="num">kcal</th></tr>
    {act_rows}</table>
  </div>
  {_progression_card(b.get("progression", {}))}
</div>"""


def _intraday_card(intraday: dict | None) -> str:
    """The Day view: a single day's heart-rate (and stress) at watch resolution."""
    if not intraday or not intraday.get("hr"):
        return (
            '<div class="card"><h2>Day · heart rate</h2>'
            '<div class="note">No intraday data pulled yet. Run <code>rapha pull</code> '
            'to fetch the most recent day at watch resolution.</div></div>'
        )
    d = intraday.get("date", "")
    hr = [v for _, v in intraday["hr"] if v is not None]
    lo, hi = (min(hr), max(hr)) if hr else ("—", "—")
    return f"""
  <div class="card">
    <h2>Day · heart rate <span class="dirtag">{_e(d)}</span></h2>
    <div class="row" style="align-items:center">
      <div><div class="big">{_e(lo)}–{_e(hi)}</div>
        <div class="l" style="color:var(--dim);font-size:12px">bpm range</div></div>
      <div class="pc" id="intraday-hr" style="flex:1;text-align:right;min-width:0"></div>
    </div>
    <div class="note">Resting dips and training spikes across the day — the shape a
      single daily number hides.</div>
  </div>"""


def _progression_card(pg: dict) -> str:
    if not pg.get("available") or not pg.get("exercises"):
        return ('<div class="card"><h2>Load progression</h2>'
                '<div class="note">No strength sets yet — run <code>rapha pull</code> '
                'to read your on-watch exercise loads.</div></div>')

    rows = ""
    for e in pg["exercises"]:
        if e["bodyweight"]:
            load = f'BW × {_e(e["reps"] or "—")}'
        else:
            load = f'{_e(e["top_kg"])} kg × {_e(e["reps"] or "—")}'
        t = e.get("trend_kg")
        if t is None:
            trend = '<span style="color:var(--dim)">—</span>'
        elif t > 0:
            trend = f'<span style="color:var(--accent)">▲ +{_e(t)} kg</span>'
        elif t < 0:
            trend = f'<span style="color:var(--amber)">▼ {_e(t)} kg</span>'
        else:
            trend = '<span style="color:var(--dim)">→ held</span>'
        spark = _spark(e.get("series", []), w=120, h=28) if len(e.get("series", [])) > 1 else ""
        rows += (
            f'<tr><td>{_e(e["name"])}</td>'
            f'<td class="num">{e["sessions"]}</td>'
            f'<td class="num">{load}</td>'
            f'<td class="num">{trend}</td>'
            f'<td style="text-align:right">{spark}</td></tr>'
        )

    total = pg.get("total", 0)
    more = (f'<div class="note">Showing the {len(pg["exercises"])} most-trained of '
            f'{total} movements.</div>') if total > len(pg["exercises"]) else ""
    return f"""
  <div class="card">
    <h2>Load progression</h2>
    <table>
      <tr><th>Exercise</th><th class="num">Sess.</th><th class="num">Top set</th>
          <th class="num">Trend</th><th style="text-align:right">Top-weight</th></tr>
      {rows}
    </table>
    {more}
    <div class="note">{_e(pg.get("note",""))}</div>
  </div>"""


def _photo_analysis_html(analysis: dict | None) -> str:
    """The written physique review for one set, or a 'pending' note if not done yet."""
    if not analysis:
        return ('<div class="note" style="margin:2px 0 8px">📋 Analysis pending — '
                'it appears here once the set has been reviewed.</div>')
    body = f'<p style="margin:0 0 8px"><strong>{_e(analysis.get("headline",""))}</strong></p>'
    body += "".join(f'<p style="margin:0 0 8px">{_e(p)}</p>'
                    for p in analysis.get("paragraphs", []))
    return (f'<div class="card" style="background:var(--card2);border-left:3px solid '
            f'var(--accent);margin:6px 0 12px">{body}</div>')


# (attr, label, human unit) — the fields the measurement form and history show.
_MEASURE_FIELDS = [
    ("weight", "Weight", "kg"), ("waist", "Waist", "cm"), ("neck", "Neck", "cm"),
    ("chest", "Chest", "cm"), ("shoulders", "Shoulders", "cm"), ("arm", "Arm", "cm"),
    ("thigh", "Thigh", "cm"), ("hip", "Hip", "cm"), ("calf", "Calf", "cm"),
    ("wingspan", "Wingspan", "cm"),
]
# For circumferences: is a DROP the good direction? Waist yes (fat); muscles no.
_LOWER_IS_BETTER = {"waist", "hip"}


def _measurements_card(pr: dict) -> str:
    tape = pr.get("tape") or {}
    measure = pr.get("measure") or {}
    latest = measure.get("latest", {})
    changes = measure.get("changes", [])

    # Current values as tags
    tags = ""
    for attr, label, unit in _MEASURE_FIELDS:
        v = latest.get(attr)
        if v is not None:
            tags += f'<span class="tag">{_e(label)}: {_e(v)} {_e(unit)}</span>'
    tags_html = (tags + f'<div class="note">Latest tape: {_e(tape.get("measured_on","—"))}'
                 + (f' · biotype {_e(tape["biotype"])}' if tape.get("biotype") else '')
                 + '</div>') if tags else (
        '<div class="note">No measurements yet — add your waist and neck below and '
        'the Navy body-fat estimate starts tracking.</div>')

    # Recomposition changes (since protocol start)
    change_html = ""
    for c in changes:
        drop_good = c["attr"] in _LOWER_IS_BETTER
        d = c["delta"]
        if d == 0:
            col, arrow = "var(--dim)", "→"
        else:
            good = (d < 0) if drop_good else (d > 0)
            col = "var(--accent)" if good else "var(--amber)"
            arrow = "▼" if d < 0 else "▲"
        change_html += (
            f'<span class="tag" style="color:{col}">{_e(c["label"])} '
            f'{arrow} {_e(abs(d))} {_e(c["unit"])}</span>')
    change_block = (f'<div class="note" style="margin-top:6px">Change since you started '
                    f'measuring:</div><div>{change_html}</div>' if change_html else '')

    # Add / edit form — prefilled with the latest values
    inputs = ""
    for attr, label, unit in _MEASURE_FIELDS:
        val = latest.get(attr, "")
        inputs += (
            f'<label class="mfield"><span>{_e(label)} <em>{_e(unit)}</em></span>'
            f'<input type="number" step="0.1" min="0" id="m_{attr}" '
            f'value="{_e(val)}" placeholder="—"></label>')

    return f"""
  <div class="card">
    <h2>Measurements</h2>
    <div>{tags_html}</div>
    {change_block}
    <button class="copy" style="margin-top:12px" onclick="toggleMeasForm(this)">Add / edit measurement</button>
    <div id="measform" style="display:none;margin-top:12px">
      <div class="note">Enter what you measured today — leave the rest blank; blank
        fields keep their last value. Waist + neck drive the body-fat estimate.</div>
      <label class="mfield"><span>Date</span>
        <input type="date" id="m_date"></label>
      <div class="mgrid">{inputs}</div>
      <label class="mfield" style="grid-column:1/-1"><span>Notes</span>
        <input type="text" id="m_notes" placeholder="optional"></label>
      <button class="copy" style="margin-top:10px" onclick="saveMeasurement(this)">Save measurement</button>
      <span class="note" id="mstatus" style="margin-left:10px"></span>
    </div>
  </div>"""


def _progress_tab(b: dict) -> str:
    pr = b.get("progress", {})
    ath = b.get("athlete", {})

    photo_html = ""
    for pset in pr.get("photo_sets", []):
        imgs = "".join(
            f'<img src="/photos/{_e(pset["date"])}/{_e(img)}" alt="progress photo" '
            f'loading="lazy" onclick="openLightbox(this.src)">'
            for img in pset["images"]
        )
        photo_html += (f'<h2 style="margin-top:18px">{_e(pset["date"])}</h2>'
                       f'{_photo_analysis_html(pset.get("analysis"))}'
                       f'<div class="photos">{imgs}</div>')

    weights = pr.get("weight_series", [])

    return f"""
<div class="tab" id="progress">
  <div class="card">
    <h2>Body composition</h2>
    <div class="row">
      {_stat(f'{ath.get("weight_kg","—")} kg', "Weight")}
      {_stat(f'{pr.get("bodyfat_pct","—")}%', "Body fat")}
      {_stat(pr.get("biotype","—") or "—", "Biotype")}
      {_stat(pr.get("somatotype","—") or "—", "Somatotype")}
    </div>
    <div class="note">{_e(pr.get("bodyfat_source",""))}</div>
  </div>
  <div class="card">
    <h2>Weight trend</h2>
    {_weight_chart(pr.get("weight_view", {}))}
    <div class="note">{('Latest ' + str(weights[-1][1]) + ' kg · ' + str(len(weights))
                        + ' weigh-ins') if weights else 'No weigh-ins yet'}</div>
    <div class="note">{_e(pr.get("weight_view", {}).get("trend_note", ""))}</div>
  </div>
  {_measurements_card(pr)}
  <div class="card">
    <h2>Progress photos</h2>
    <label class="copy" style="cursor:pointer;display:inline-block">Upload photos
      <input type="file" accept=".heic,.heif,.jpg,.jpeg,.png,image/*" multiple
             style="display:none" onchange="uploadPhotos(this)">
    </label>
    {'<button class="copy" id="photobtn" style="margin-left:8px" '
     'onclick="togglePhotos(this)">Show photos</button>' if photo_html else ''}
    <span class="note" id="upstatus" style="margin-left:10px"></span>
    {f'<div id="photowrap" style="display:none;margin-top:12px">{photo_html}</div>'
     if photo_html else
     '<div class="note" style="margin-top:8px">No photos yet — upload straight from '
     'your phone (HEIC is converted automatically), or drop them in '
     '%RAPHA_HOME%\\\\data\\\\photos\\\\&lt;date&gt;\\\\</div>'}
    <div class="note">{_e(pr.get("note",""))}</div>
  </div>
</div>"""


def _data_status_tab(b: dict) -> str:
    import json as _json

    ds = b.get("data_status", {})
    s = ds.get("summary") or {}
    # Initial dot from the build; JS makes it live against the clock + a port probe.
    fresh = ds.get("fresh")
    init_col = "var(--accent)" if fresh else "var(--red)"
    summary_html = ""
    if s:
        bits = [
            (s.get("activities"), "activities"),
            (s.get("days"), "days of metrics"),
            (s.get("weigh_ins"), "weigh-ins"),
            (s.get("exercise_set_rows"), "exercise sets"),
        ]
        summary_html = " · ".join(f"{v} {label}" for v, label in bits if v is not None)

    return f"""
<div class="tab" id="datastatus">
  <script>window.DATA_STATUS={_json.dumps(ds)};</script>
  <div class="card">
    <h2><span class="dot" id="statusdot" style="background:{init_col}"></span>
      Data status</h2>
    <div class="big" id="statustext" style="margin-top:4px">checking…</div>
    <div class="note" id="statussub"></div>
  </div>

  <div class="card">
    <h2>Last Garmin pull</h2>
    <div class="row">
      <div class="stat"><div class="n" id="lastpull">—</div><div class="l">When</div></div>
      <div class="stat"><div class="n" id="pullage">—</div><div class="l">Age</div></div>
    </div>
    {f'<div class="note">Last pull brought in: {_e(summary_html)}</div>' if summary_html else ''}
    <button class="copy" style="margin-top:10px" onclick="forcePull(this)">Pull now</button>
    <span class="note" id="pullnowstatus" style="margin-left:10px"></span>
    <div class="note">The dot turns <span style="color:var(--red)">red</span> once a pull
      is more than {ds.get("fresh_minutes", 60)} minutes old, and
      <span style="color:var(--accent)">green</span> while it's fresh. "Pull now" runs
      the same job immediately — it needs the browser session below to be open.</div>
  </div>

  <div class="card">
    <h2>Browser session</h2>
    <div class="note" id="chromestate">checking whether a Garmin browser session is open…</div>
    <button class="copy" style="margin-top:10px" onclick="launchChrome(this)">
      Open Chrome on the Garmin login page</button>
    <span class="note" id="launchstatus" style="margin-left:10px"></span>
    <div class="note" style="margin-top:10px">The pull can only run while a Chrome you've
      logged into Garmin is open. Click the button, sign in (do the human bits — password,
      any check), then leave that window open. Rapha only ever <em>attaches</em> to it — it
      never sees your password, and stores no credential.</div>
  </div>

  <div class="card">
    <h2>How refresh works</h2>
    <ul class="note" style="padding-left:18px;line-height:1.8">
      <li>An hourly task runs <code>rapha pull</code> and rebuilds this portal.</li>
      <li>A pull succeeds only if the browser session above is open and still logged in
          — otherwise the dot goes red, your cue to click the button and sign in again.</li>
      <li>Garmin sign-ins last a while, so in practice you re-authenticate occasionally,
          not hourly.</li>
      <li>Uploads and measurements you enter here are saved instantly and don't depend
          on the pull.</li>
    </ul>
  </div>
</div>"""


def _freshness(ds: dict) -> str:
    """Header freshness chip: '● data is current · 23 min' coloured by staleness."""
    fresh = ds.get("fresh")
    age = ds.get("age_seconds")
    if age is None:
        return '<span class="stale">○ no pull recorded</span>'
    mins = age // 60
    when = (f"{mins} min" if mins < 90 else f"{mins // 60} h {mins % 60} min"
            if mins < 60 * 36 else f"{mins // (60 * 24)} d")
    cls = "fresh" if fresh else "stale"
    label = "data is current" if fresh else "data is stale"
    return f'<span class="{cls}">● {label} · {_e(when)}</span>'


def render(b: dict) -> str:
    ov = b["overview"]
    status = ov["recovery"]["status"]
    dot = {"green": "var(--accent2)", "amber": "var(--accent)",
           "red": "var(--bad)"}.get(status, "var(--dim)")
    ds = b.get("data_status", {}) or {}
    ds_class = "statusok" if ds.get("fresh") else "statusbad"

    meta_bits = []
    if ov.get("sheet_number"):
        meta_bits.append(f'sheet {_e(ov["sheet_number"])}')
    if ov.get("week"):
        meta_bits.append(f'week {_e(ov["week"])} of 8')
    meta_bits.append(f'built {_e(b["generated"])}')
    meta = " · ".join(meta_bits)

    header = (
        '<header><div>'
        f'<div class="eyebrow"><span class="dot" style="background:{dot}"></span>'
        'Rapha · Projeto 60 Dias</div>'
        f'<h1>Day {ov["day_of_60"]} <span class="of">of 60</span></h1>'
        f'<div class="sub hmeta">{meta}</div>'
        '</div>'
        f'<div class="hright">{_freshness(ds)}<br>macro-first recomposition</div>'
        '</header>'
    )

    nav = (
        '<nav>'
        '<button class="on" onclick="tab(\'today\',this)">Today</button>'
        '<button onclick="tab(\'training\',this)">Training</button>'
        '<button onclick="tab(\'meals\',this)">Meals</button>'
        '<button onclick="tab(\'performance\',this)">Performance</button>'
        '<button onclick="tab(\'progress\',this)">Progress</button>'
        f'<button id="tab-datastatus" class="{ds_class}" onclick="tab(\'datastatus\',this)">'
        '<span class="dot" id="navdot" style="background:currentColor"></span>'
        'Data Status</button>'
        '</nav>'
    )

    footer = (
        '<footer>'
        'Observations against Projeto 60 Dias · not medical advice · every decision is yours'
        '<br>local-first · 127.0.0.1 · no credential in the portal'
        '</footer>'
    )

    return (
        f"<style>{CSS}</style>"
        + header + nav + '<main>'
        + _today_tab(b)
        + _training_tab(b)
        + _meals_tab(b)
        + _performance_tab(b)
        + _progress_tab(b)
        + _data_status_tab(b)
        + '</main>'
        + footer
        + '<div class="lightbox" id="lightbox" onclick="closeLightbox()">'
          '<span class="x" onclick="closeLightbox()">&times;</span>'
          '<img id="lightbox-img" src="" alt="enlarged progress photo"></div>'
        + f"<script>{JS}</script>"
    )


def write(dist, b: dict) -> Any:
    from pathlib import Path
    dist = Path(dist)
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Rapha</title></head><body>" + render(b) + "</body></html>",
        encoding="utf-8",
    )
    (dist / "briefing.json").write_text(
        json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dist / "index.html"
