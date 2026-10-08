#!/usr/bin/env python3
"""Story 1 figures 2 and 3.

Fig 2  ข้ออ้างเรื่องไวรัส การระบาด และวัคซีน: share of each publisher's yearly records in the virus group (T4+T7+T18)
Fig 3  AFNC agency-impersonation pages: records per year vs distinct claims (cosine >= 0.95), three groups, 2565-2569

Reads runs/20261004_story1_by_publisher_v001/{publisher_year_topic_groups.csv,named_topics_by_year.csv}
Writes self-contained HTML (inline SVG, hover tooltip, table view, light/dark) + tidy CSVs into --out.
Colors: categorical slots 1-3 (publishers, same entity colors as figure 1), AFNC orange + neutral ink for fig 3.
"""
import argparse, csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "runs/20261004_story1_by_publisher_v001"
PUBS = [("sure_share", "ชัวร์ก่อนแชร์", 0), ("afnc", "AFNC", 1), ("afp", "AFP ประเทศไทย", 2)]
FIRST_YEAR = {"sure_share": 2015, "afnc": 2020, "afp": 2020}  # AFNC/AFP have <=70 records/yr before 2563 (AFP none); start where the series is meaningful
GROUPS = [("driving_licence", "รับทำใบขับขี่ออนไลน์"), ("victim_refund", "อ้างคืนเงินให้ผู้เสียหาย"), ("invest_dividend", "ลงทุน–ปันผล–ตลาดหลักทรัพย์")]

CSS = r"""
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#6f6d67;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);--band:#efeee9;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--neutral:#52514e;}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#a09e96;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--band:#232321;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--neutral:#c3c2b7;}}
:root[data-theme="dark"]{--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#a09e96;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--band:#232321;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--neutral:#c3c2b7;}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI","Thonburi","Sarabun","Noto Sans Thai",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:24px 16px}.export .wrap{padding:16px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:20px 20px 14px}
h1{font-size:20px;line-height:1.3;margin:0 0 4px;font-weight:650}.sub{margin:0 0 12px;color:var(--ink2);font-size:14px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0 0 6px;padding:0;list-style:none;font-size:13px;color:var(--ink2)}
.legend i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.legend i.ln{height:3px;vertical-align:3px;width:16px}
.tools{display:flex;justify-content:flex-end;margin:2px 0 0}.export .tools{display:none}
button.t{font:inherit;font-size:13px;color:var(--ink2);background:transparent;border:1px solid var(--ring);border-radius:8px;padding:4px 10px;cursor:pointer}
button.t:hover{background:var(--band)}button.t:focus-visible{outline:2px solid var(--s1);outline-offset:2px}
svg{display:block;overflow:visible}svg text{font-family:inherit}
.note{margin:10px 0 0;color:var(--muted);font-size:12.5px;line-height:1.55}
.col{outline:none}.col:focus-visible .hit{stroke:var(--ink);stroke-width:1.5}
#tip{position:fixed;z-index:5;pointer-events:none;min-width:200px;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 18px rgba(0,0,0,.18);opacity:0;transition:opacity .08s}
#tip .h{font-weight:650;margin-bottom:4px}#tip .r{display:flex;align-items:center;gap:8px;line-height:1.7}
#tip .k{width:12px;height:3px;border-radius:2px;flex:none}#tip .v{font-weight:650;min-width:56px;text-align:right}#tip .n{color:var(--ink2);flex:1}#tip .s{color:var(--muted);font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:10px}th,td{padding:5px 8px;text-align:right;border-bottom:1px solid var(--grid)}th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
.hidden{display:none}
.panels{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:6px}@media(max-width:700px){.panels{grid-template-columns:1fr}}
.panel h2{font-size:14px;margin:6px 0 0;font-weight:650;color:var(--ink)}
"""
JS_COMMON = r"""
try{const sp=new URLSearchParams(location.search),q=sp.get("theme");if(q==="light"||q==="dark")document.documentElement.dataset.theme=q;if(sp.has("export"))document.documentElement.classList.add("export")}catch(e){}
const fmt=n=>n.toLocaleString("en-US"), NS="http://www.w3.org/2000/svg", tip=document.getElementById("tip");
const el=(n,a={},p)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e};
const div=(c,t)=>{const d=document.createElement("div");if(c)d.className=c;if(t!=null)d.textContent=t;return d};
const span=(c,t)=>{const d=document.createElement("span");if(c)d.className=c;if(t!=null)d.textContent=t;return d};
const hideTip=()=>tip.style.opacity=0;
function placeTip(node){const bb=node.getBoundingClientRect();let x=bb.right+8;if(x+230>innerWidth)x=bb.left-238;tip.style.left=Math.max(8,x)+"px";tip.style.top=Math.max(8,bb.top+20)+"px";tip.style.opacity=1}
function buildTable(host,head,rows){const t=document.createElement("table"),th=document.createElement("thead"),hr=document.createElement("tr");
 head.forEach(s=>{const c=document.createElement("th");c.textContent=s;hr.append(c)});th.append(hr);t.append(th);const b=document.createElement("tbody");
 rows.forEach(r=>{const tr=document.createElement("tr");r.forEach(s=>{const c=document.createElement("td");c.textContent=s;tr.append(c)});b.append(tr)});t.append(b);host.append(t)}
function wireToggle(btn,box){btn.onclick=()=>{const open=box.classList.toggle("hidden")===false;btn.setAttribute("aria-expanded",open);btn.textContent=open?"ซ่อนตาราง":"ดูเป็นตาราง"}}
"""

HTML_VIRUS = r"""<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ข้ออ้างเรื่องไวรัสและการระบาด แยกตามสำนัก</title><style>__CSS__</style></head><body>
<div class="wrap"><div class="card">
<h1>ข้ออ้างเรื่องไวรัส การระบาด และวัคซีน: ขึ้นพร้อมกันในปี 2563 และแทบหมดไปภายในปี 2566</h1>
<p class="sub">สัดส่วนของบทตรวจรายปีของแต่ละสำนักที่โมเดลจัดเข้ากลุ่มไวรัส/การระบาด/วัคซีน (กลุ่ม 4, 7, 18)</p>
<ul class="legend" id="legend"></ul><div id="chart"></div>
<div class="tools"><button class="t" id="tg" type="button" aria-expanded="false">ดูเป็นตาราง</button></div><div id="tbl" class="hidden"></div>
<p class="note">แต่ละเส้นคิดเป็นร้อยละของบทตรวจ <b>ของสำนักนั้นในปีนั้น</b> ไม่ใช่ร้อยละของทั้งคลัง · AFNC และ AFP เริ่มที่ปี 2563 (ก่อนหน้านั้น AFNC มีบทตรวจไม่เกิน 70 รายการต่อปี และ AFP ยังไม่มี) · ไม่แสดง Cofact (ไม่เกิน 20 บทตรวจต่อปีก่อนปี 2568) และ Thai PBS Verify (เริ่มปี 2567) · พื้นแรเงา = ปีไม่เต็มปี (2558 เริ่ม 30 พ.ค.; 2569 ถึง 1 ก.ย.) · ชื่อกลุ่มเป็นการตีความของผู้เขียนจากผลโมเดล กลุ่มปี 2569 มีไวรัสนิปาห์ปนอยู่ ไม่ใช่โควิดทั้งหมด · ปี 2567 ของชัวร์ก่อนแชร์เป็นข้ออ้างวัคซีนในชุดคลิปเดียว (30 จาก 35) ไม่ใช่หลักฐานว่าข่าวลวงวัคซีนกลับมา · วันที่ = วันเผยแพร่บทตรวจ<br>ที่มา: คลังบันทึกผลตรวจสอบ 5 สำนัก (สแนปช็อต 2 ก.ย. 2569) · publisher_year_topic_groups.csv</p>
</div></div><div id="tip" role="status"></div>
<script>__JS__
const DATA=__DATA__, SERIES=DATA.series, YEARS=DATA.years, YMAX=25;
const col=i=>`var(--s${i+1})`, chartEl=document.getElementById("chart");let lastW=0;
const leg=document.getElementById("legend");SERIES.forEach(s=>{const li=document.createElement("li"),k=document.createElement("i");k.className="ln";k.style.background=col(s.slot);li.append(k,document.createTextNode(s.label));leg.append(li)});
function draw(){
 const W=Math.max(320,Math.round(chartEl.clientWidth||900)),narrow=W<600,H=narrow?360:430,M={l:narrow?40:52,r:14,t:20,b:narrow?46:54},iw=W-M.l-M.r,ih=H-M.t-M.b;lastW=chartEl.clientWidth;
 const band=iw/YEARS.length,X=i=>M.l+band*i+band/2,Y=v=>M.t+ih-v/YMAX*ih;chartEl.replaceChildren();
 const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,width:W,height:H,role:"img","aria-label":"เส้นสัดส่วนข้ออ้างเรื่องไวรัสต่อบทตรวจรายปี แยกตามสำนัก"});chartEl.append(svg);
 YEARS.forEach((y,i)=>{if(y.partial)el("rect",{x:M.l+i*band+2,y:M.t,width:band-4,height:ih,rx:6,fill:"var(--band)"},svg)});
 [0,5,10,15,20,25].forEach(t=>{el("line",{x1:M.l,x2:W-M.r,y1:Y(t),y2:Y(t),stroke:t?"var(--grid)":"var(--axis)","stroke-width":1},svg);const tx=el("text",{x:M.l-8,y:Y(t)+4,"text-anchor":"end","font-size":12,fill:"var(--muted)"},svg);tx.textContent=t+"%"});
 const cross=el("line",{y1:M.t,y2:M.t+ih,stroke:"var(--axis)","stroke-width":1,style:"display:none"},svg);
 SERIES.forEach(s=>{const pts=s.pts.map((p,i)=>p&&p.pct!=null?[X(i),Y(p.pct)]:null);let d="",pen=false;
  pts.forEach(q=>{if(!q){pen=false;return}d+=(pen?"L":"M")+q[0].toFixed(1)+","+q[1].toFixed(1);pen=true});
  el("path",{d,fill:"none",stroke:col(s.slot),"stroke-width":2,"stroke-linejoin":"round","stroke-linecap":"round"},svg)});
 SERIES.forEach(s=>s.pts.forEach((p,i)=>{if(p&&p.pct!=null)el("circle",{cx:X(i),cy:Y(p.pct),r:4,fill:col(s.slot),stroke:"var(--surface)","stroke-width":2},svg)}));
 // selective labels: the 2563 peaks (left of the points) and the ชัวร์ก่อนแชร์ 2567 bump
 const i63=YEARS.findIndex(y=>y.year===2020);
 if(!narrow)SERIES.forEach(s=>{const p=s.pts[i63];const t=el("text",{x:X(i63)-10,y:Y(p.pct)+4,"text-anchor":"end","font-size":12.5,"font-weight":650,fill:"var(--ink)"},svg);t.textContent=`${s.short} ${p.pct.toFixed(1)}%`});
 const i67=YEARS.findIndex(y=>y.year===2024),sp=SERIES[0].pts[i67];
 if(!narrow){[["2567: ชัวร์ก่อนแชร์ 9.1% (35 บันทึก)",650],["30 บันทึกมาจากชุดคลิป LIVE Retrovert",400]].forEach((l,k)=>{const t=el("text",{x:X(i67),y:Y(sp.pct)-36+k*15,"text-anchor":"middle","font-size":12,"font-weight":l[1],fill:k?"var(--muted)":"var(--ink2)"},svg);t.textContent=l[0]});
  el("line",{x1:X(i67),x2:X(i67),y1:Y(sp.pct)-12,y2:Y(sp.pct)-7,stroke:"var(--axis)","stroke-width":1},svg)}
 YEARS.forEach((y,i)=>{const lb=el("text",{x:X(i),y:H-M.b+20,"text-anchor":"middle","font-size":narrow?11:13,fill:"var(--ink2)"},svg);lb.textContent=(narrow?String(y.be).slice(2):y.be)+(y.partial?"*":"");
  if(y.partial&&!narrow){const t=el("text",{x:X(i),y:H-M.b+37,"text-anchor":"middle","font-size":11,fill:"var(--muted)"},svg);t.textContent="ไม่เต็มปี"}});
 if(narrow){const c=el("text",{x:M.l,y:H-6,"font-size":11,fill:"var(--muted)"},svg);c.textContent="ปี พ.ศ. 25xx · * = ไม่เต็มปี"}
 YEARS.forEach((y,i)=>{const g=el("g",{class:"col",tabindex:0,role:"img","aria-label":`ปี ${y.be}: `+SERIES.map(s=>{const p=s.pts[i];return p&&p.pct!=null?`${s.label} ${p.pct.toFixed(1)}% (${p.n} จาก ${fmt(p.total)})`:`${s.label} ไม่มีข้อมูลที่ใช้ได้`}).join(", ")},svg);
  const hit=el("rect",{class:"hit",x:M.l+i*band,y:M.t,width:band,height:ih,fill:"transparent"},g);
  const show=()=>{cross.setAttribute("x1",X(i));cross.setAttribute("x2",X(i));cross.style.display="";tip.replaceChildren();tip.append(div("h",`ปี ${y.be} (ค.ศ. ${y.year})${y.partial?" · ไม่เต็มปี":""}`));
   SERIES.forEach(s=>{const p=s.pts[i],r=div("r"),k=span("k");k.style.background=col(s.slot);r.append(k,span("n",s.label));
    if(p&&p.pct!=null){r.append(span("v",p.pct.toFixed(1)+"%"));tip.append(r);tip.append(div("s",`   ${p.n} จาก ${fmt(p.total)} บทตรวจ`))}else{r.append(span("v","–"));tip.append(r)}});placeTip(g)};
  g.addEventListener("pointermove",show);g.addEventListener("pointerenter",show);g.addEventListener("focus",show);
  const off=()=>{hideTip();cross.style.display="none"};g.addEventListener("pointerleave",off);g.addEventListener("blur",off)});
}
draw();new ResizeObserver(()=>{if(Math.abs(chartEl.clientWidth-lastW)>2)draw()}).observe(chartEl);
(function(){const rows=YEARS.map((y,i)=>[y.be+(y.partial?"*":""),...SERIES.map(s=>{const p=s.pts[i];return p&&p.pct!=null?`${p.pct.toFixed(1)}% (${p.n}/${fmt(p.total)})`:"–"})]);
 buildTable(document.getElementById("tbl"),["ปี (พ.ศ.)",...SERIES.map(s=>s.label+" (บทตรวจในกลุ่ม/ทั้งหมด)")],rows);wireToggle(document.getElementById("tg"),document.getElementById("tbl"))})();
</script></body></html>"""

HTML_IMPERS = r"""<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>บทตรวจกับข้ออ้างที่ต่างกัน เพจแอบอ้างหน่วยงาน</title><style>__CSS__</style></head><body>
<div class="wrap"><div class="card">
<h1>เพจแอบอ้างหน่วยงาน: จำนวนบทตรวจไม่เท่ากับจำนวนข้ออ้าง</h1>
<p class="sub">จำนวนบทตรวจต่อปี เทียบกับจำนวนข้ออ้างที่ต่างกัน ในสามกลุ่มที่ใช้ชื่อหน่วยงานจริงคู่กับ “เพจ” (ปี 2565–2569)</p>
<ul class="legend"><li><i style="background:var(--s2)"></i>บทตรวจ</li><li><i style="background:var(--neutral)"></i>ข้ออ้างที่ต่างกัน (ประมาณ)</li></ul>
<div class="panels" id="panels"></div>
<div class="tools"><button class="t" id="tg" type="button" aria-expanded="false">ดูเป็นตาราง</button></div><div id="tbl" class="hidden"></div>
<p class="note">“ข้ออ้างที่ต่างกัน” นับข้อความที่คล้ายกันตั้งแต่ cosine 0.95 ขึ้นไปเป็นหนึ่งข้ออ้าง เป็นค่าประมาณ ไม่ใช่การอ่านยืนยันทีละข้อ ที่เกณฑ์เข้มกว่า (0.97) กลุ่มใบขับขี่มีข้อความต่างกัน 121 แทน 282 · บทตรวจนับทุกสำนักในกลุ่ม แต่เกือบทั้งหมดเป็นของ AFNC (885 จาก 893 บันทึกในสามกลุ่ม) ภาพนี้จึงเป็นเรื่องของวิธีตรวจของ AFNC ไม่ใช่ของข่าวลวงทั้งสังคม · แกนตั้งใช้สเกลเดียวกันทั้งสามกลุ่ม · พื้นแรเงา = 2569 ถึง 1 ก.ย. ไม่เต็มปี · ชื่อกลุ่มเป็นการตีความของผู้เขียน และขอบเขตกลุ่มคืนเงินเปลี่ยนตามค่าสุ่มของโมเดล (2.65–6.08% ของคลังในปี 2567–2568) ใช้จำนวนเป็นค่าประมาณ<br>ที่มา: named_topics_by_year.csv (คอลัมน์ records และ distinct_near_duplicate_claims_cos095)</p>
</div></div><div id="tip" role="status"></div>
<script>__JS__
const DATA=__DATA__, YMAX=240, TICKS=[0,50,100,150,200];
const host=document.getElementById("panels");let lastW=0;
function panel(g,node){
 const W=Math.max(220,Math.round(node.clientWidth)),H=250,M={l:34,r:6,t:22,b:36},iw=W-M.l-M.r,ih=H-M.t-M.b,n=g.rows.length,band=iw/n,bw=Math.min(18,Math.floor(band*.34)),GAP=2;
 const Y=v=>M.t+ih-v/YMAX*ih;const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,width:W,height:H,role:"img","aria-label":g.label+": บทตรวจเทียบข้ออ้างที่ต่างกัน ปี 2565 ถึง 2569"});node.append(svg);
 g.rows.forEach((r,i)=>{if(r.partial)el("rect",{x:M.l+i*band+2,y:M.t,width:band-4,height:ih,rx:6,fill:"var(--band)"},svg)});
 TICKS.forEach(t=>{el("line",{x1:M.l,x2:W-M.r,y1:Y(t),y2:Y(t),stroke:t?"var(--grid)":"var(--axis)","stroke-width":1},svg);const tx=el("text",{x:M.l-6,y:Y(t)+4,"text-anchor":"end","font-size":11.5,fill:"var(--muted)"},svg);tx.textContent=t});
 const top=(x,yt,w,h,r)=>{r=Math.min(r,h/2);return `M${x},${yt+h}V${yt+r}Q${x},${yt} ${x+r},${yt}H${x+w-r}Q${x+w},${yt} ${x+w},${yt+r}V${yt+h}Z`};
 const peak=g.rows.reduce((a,r,i)=>r.records>g.rows[a].records?i:a,0);
 g.rows.forEach((r,i)=>{const cx=M.l+i*band+band/2,grp=el("g",{class:"col",tabindex:0,role:"img","aria-label":`${g.label} ปี ${r.be}: บทตรวจ ${r.records}, ข้ออ้างที่ต่างกัน ${r.distinct}`},svg);
  el("rect",{class:"hit",x:M.l+i*band,y:M.t,width:band,height:ih,fill:"transparent"},grp);
  [[r.records,"var(--s2)",cx-bw-GAP/2],[r.distinct,"var(--neutral)",cx+GAP/2]].forEach(([v,c,x])=>{if(v>0)el("path",{d:top(x,Y(v),bw,Math.max(Y(0)-Y(v),1),4),fill:c},grp)});
  if(i===peak){[[r.records,cx-bw/2-GAP/2],[r.distinct,cx+bw/2+GAP/2]].forEach(([v,x])=>{const t=el("text",{x,y:Y(v)-6,"text-anchor":"middle","font-size":12,"font-weight":650,fill:"var(--ink)"},grp);t.textContent=v})}
  const lb=el("text",{x:cx,y:H-M.b+18,"text-anchor":"middle","font-size":12.5,fill:"var(--ink2)"},grp);lb.textContent=r.be+(r.partial?"*":"");
  const show=()=>{tip.replaceChildren();tip.append(div("h",`${g.label} · ปี ${r.be}${r.partial?" (ไม่เต็มปี)":""}`));
   [["บทตรวจ",r.records,"var(--s2)"],["ข้ออ้างที่ต่างกัน",r.distinct,"var(--neutral)"]].forEach(([nm,v,c])=>{const row=div("r"),k=span("k");k.style.background=c;row.append(k,span("n",nm),span("v",fmt(v)));tip.append(row)});placeTip(grp)};
  grp.addEventListener("pointermove",show);grp.addEventListener("pointerenter",show);grp.addEventListener("focus",show);grp.addEventListener("pointerleave",hideTip);grp.addEventListener("blur",hideTip)});
}
function draw(){lastW=host.clientWidth;host.replaceChildren();DATA.groups.forEach(g=>{const p=document.createElement("div");p.className="panel";const h=document.createElement("h2");h.textContent=g.label;const box=document.createElement("div");p.append(h,box);host.append(p);panel(g,box)})}
draw();new ResizeObserver(()=>{if(Math.abs(host.clientWidth-lastW)>2)draw()}).observe(host);
(function(){const rows=[];DATA.groups.forEach(g=>g.rows.forEach(r=>rows.push([g.label,r.be+(r.partial?"*":""),fmt(r.records),fmt(r.distinct)])));
 buildTable(document.getElementById("tbl"),["กลุ่ม","ปี (พ.ศ.)","บทตรวจ","ข้ออ้างที่ต่างกัน"],rows);wireToggle(document.getElementById("tg"),document.getElementById("tbl"))})();
</script></body></html>"""


def load():
    rows = list(csv.DictReader(open(RUN / "publisher_year_topic_groups.csv", encoding="utf-8-sig")))
    years = sorted({int(r["year"]) for r in rows})
    partial = {int(r["year"]) for r in rows if r["partial_year"] == "True"}
    by = {(r["source"], int(r["year"])): r for r in rows}
    ydat = [{"year": y, "be": y + 543, "partial": y in partial} for y in years]
    series = []
    for key, label, slot in PUBS:
        pts = []
        for y in years:
            r = by[(key, y)]
            if y < FIRST_YEAR[key] or r["virus_T4_T7_T18_pct"] == "":
                pts.append(None)
            else:
                pts.append({"pct": float(r["virus_T4_T7_T18_pct"]), "n": int(r["virus_T4_T7_T18"]), "total": int(r["records"])})
        series.append({"key": key, "label": label, "short": {"sure_share": "ชัวร์ก่อนแชร์", "afnc": "AFNC", "afp": "AFP"}[key], "slot": slot, "pts": pts})
    virus = {"years": ydat, "series": series}

    nt = list(csv.DictReader(open(RUN / "named_topics_by_year.csv", encoding="utf-8-sig")))
    groups = []
    for gk, gl in GROUPS:
        rs = []
        for r in nt:
            if r["label_draft"] == gk and 2022 <= int(r["year"]) <= 2026:
                rs.append({"year": int(r["year"]), "be": int(r["year_be"]), "partial": int(r["year"]) in partial,
                           "records": int(r["records"]), "distinct": int(r["distinct_near_duplicate_claims_cos095"])})
        rs.sort(key=lambda x: x["year"]); groups.append({"key": gk, "label": gl, "rows": rs})
    return virus, {"groups": groups}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(ROOT / "runs/20261007_story1_viz_v001")); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    virus, impers = load()
    # sanity: figures quoted in the article draft
    s = {p["be"]: p for p in [dict(y, **(virus["series"][0]["pts"][i] or {})) for i, y in enumerate(virus["years"])]}
    assert round(s[2563]["pct"], 1) == 14.0 and round(s[2567]["pct"], 1) == 9.1
    a_ = {y["be"]: virus["series"][1]["pts"][i] for i, y in enumerate(virus["years"])}; assert round(a_[2563]["pct"], 1) == 21.6 and a_[2563]["n"] == 187
    p_ = {y["be"]: virus["series"][2]["pts"][i] for i, y in enumerate(virus["years"])}; assert round(p_[2563]["pct"], 1) == 16.0 and p_[2563]["n"] == 17
    g = {x["key"]: {r["be"]: r for r in x["rows"]} for x in impers["groups"]}
    assert [g["driving_licence"][y]["records"] for y in range(2565, 2570)] == [21, 49, 87, 117, 46]
    assert [g["driving_licence"][y]["distinct"] for y in range(2565, 2570)] == [4, 9, 10, 7, 10]
    assert [g["victim_refund"][y]["distinct"] for y in range(2565, 2570)] == [1, 1, 19, 16, 12]
    assert [g["invest_dividend"][y]["records"] for y in range(2565, 2570)] == [41, 208, 99, 30, 4]
    rep = lambda t, d, c: t.replace("__CSS__", CSS).replace("__JS__", JS_COMMON).replace("__DATA__", json.dumps(d, ensure_ascii=False))
    (out / "chart_virus_by_publisher.html").write_text(rep(HTML_VIRUS, virus, 0), encoding="utf-8")
    (out / "chart_agency_impersonation.html").write_text(rep(HTML_IMPERS, impers, 0), encoding="utf-8")
    with open(out / "virus_share_by_publisher_year.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["year_be", "publisher", "virus_records", "records", "virus_pct"])
        for i, y in enumerate(virus["years"]):
            for sr in virus["series"]:
                p = sr["pts"][i]
                if p: w.writerow([y["be"], sr["label"], p["n"], p["total"], p["pct"]])
    with open(out / "agency_impersonation_records_vs_claims.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["group", "year_be", "records", "distinct_claims_cos095"])
        for gr in impers["groups"]:
            for r in gr["rows"]: w.writerow([gr["label"], r["be"], r["records"], r["distinct"]])
    print("wrote", out)


if __name__ == "__main__":
    main()
