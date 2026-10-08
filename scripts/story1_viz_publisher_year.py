#!/usr/bin/env python3
"""Story 1 figure: records per year, stacked by publisher ("จำนวนบทตรวจในคลัง แยกตามสำนัก").

Reads runs/20261004_story1_by_publisher_v001/publisher_year_topic_groups.csv (the `records` column),
checks the per-publisher sums against the archive total (14,429) and the `all` rows, and writes one
self-contained HTML file (inline SVG + hover tooltip + table view + light/dark) plus a tidy CSV.

Usage: python scripts/story1_viz_publisher_year.py [--out runs/20261007_story1_viz_v001]
Colors: categorical slots 1-5 of the reference palette (validated with the dataviz validator, light+dark).
"""
import argparse, csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "runs/20261004_story1_by_publisher_v001/publisher_year_topic_groups.csv"
ORDER = [("sure_share", "ชัวร์ก่อนแชร์"), ("afnc", "AFNC"), ("afp", "AFP ประเทศไทย"), ("cofact", "Cofact"), ("thaipbs", "Thai PBS Verify")]
TOTAL = 14429


def build():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    years = sorted({int(r["year"]) for r in rows})
    val = {(r["source"], int(r["year"])): int(r["records"]) for r in rows}
    partial = sorted({int(r["year"]) for r in rows if r["partial_year"] == "True"})
    data = []
    for y in years:
        by = {k: val[(k, y)] for k, _ in ORDER}
        assert sum(by.values()) == val[("all", y)], (y, by, val[("all", y)])
        data.append({"year": y, "be": y + 543, "partial": y in partial, "by": by, "total": val[("all", y)]})
    assert sum(d["total"] for d in data) == TOTAL
    for k, _ in ORDER:
        pass
    return data, [{"key": k, "label": l} for k, l in ORDER]


HTML = r"""<!doctype html>
<html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>จำนวนบทตรวจในคลัง แยกตามสำนัก</title>
<style>
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#6f6d67;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);--band:#efeee9;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#a09e96;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--band:#232321;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;}}
:root[data-theme="dark"]{--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#a09e96;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--band:#232321;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI","Thonburi","Sarabun","Noto Sans Thai",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:24px 16px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:20px 20px 14px}
h1{font-size:20px;line-height:1.3;margin:0 0 4px;font-weight:650}
.sub{margin:0 0 12px;color:var(--ink2);font-size:14px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0 0 6px;padding:0;list-style:none;font-size:13px;color:var(--ink2)}
.legend i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.tools{display:flex;justify-content:flex-end;margin:2px 0 0}
button.t{font:inherit;font-size:13px;color:var(--ink2);background:transparent;border:1px solid var(--ring);border-radius:8px;padding:4px 10px;cursor:pointer}
button.t:hover{background:var(--band)}button.t:focus-visible{outline:2px solid var(--s1);outline-offset:2px}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{font-family:inherit}
.note{margin:10px 0 0;color:var(--muted);font-size:12.5px;line-height:1.55}
.col{outline:none}.col:focus-visible .hit{stroke:var(--ink);stroke-width:1.5}
#tip{position:fixed;z-index:5;pointer-events:none;min-width:190px;background:var(--surface);color:var(--ink);border:1px solid var(--ring);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 18px rgba(0,0,0,.18);opacity:0;transition:opacity .08s}
#tip .h{font-weight:650;margin-bottom:4px}#tip .r{display:flex;align-items:center;gap:8px;line-height:1.7}
#tip .k{width:12px;height:3px;border-radius:2px;flex:none}#tip .v{font-weight:650;min-width:46px;text-align:right}#tip .n{color:var(--ink2);flex:1}
#tip .tot{border-top:1px solid var(--ring);margin-top:4px;padding-top:4px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:10px}th,td{padding:5px 8px;text-align:right;border-bottom:1px solid var(--grid)}th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
.hidden{display:none}
.export .tools{display:none}.export .wrap{padding:16px}
</style></head><body>
<div class="wrap"><div class="card">
<h1>จำนวนบทตรวจในคลัง แยกตามสำนัก</h1>
<p class="sub">บทตรวจที่มีผลเท็จ บิดเบือน หรือสื่อดัดแปลง รายปี (พ.ศ.) รวม 14,429 บันทึกจาก 5 สำนัก</p>
<ul class="legend" id="legend"></ul>
<div id="chart"></div>
<div class="tools"><button class="t" id="tg" type="button" aria-expanded="false">ดูเป็นตาราง</button></div>
<div id="tbl" class="hidden"></div>
<p class="note">พื้นแรเงา = ปีที่ข้อมูลไม่เต็มปี: 2558 เริ่ม 30 พ.ค. และ 2569 ถึง 1 ก.ย. · ตัวเลขนับ <b>บทตรวจสอบ</b> ไม่ใช่จำนวนข่าวลวงในประเทศไทยหรือยอดแชร์ และเรื่องที่ไม่มีสำนักใดเลือกตรวจจะไม่อยู่ในคลัง · วันที่ = วันเผยแพร่บทตรวจ · AFNC มี 48 บันทึกก่อน พ.ย. 2562 ที่เป็นคำเตือนซึ่งนำมาลงย้อนหลัง<br>ที่มา: คลังบันทึกผลตรวจสอบ 5 สำนัก (สแนปช็อต 2 ก.ย. 2569) · publisher_year_topic_groups.csv · วิเคราะห์โดยทีมข้อมูล</p>
</div></div>
<div id="tip" role="status"></div>
<script>
const DATA=__DATA__, PUBS=__PUBS__;
try{const q=new URLSearchParams(location.search).get("theme");if(q==="light"||q==="dark")document.documentElement.dataset.theme=q;if(new URLSearchParams(location.search).has("export"))document.documentElement.classList.add("export")}catch(e){}
const fmt=n=>n.toLocaleString("en-US"), NS="http://www.w3.org/2000/svg";
const col=i=>`var(--s${i+1})`;
const YMAX=3000, GAP=2, R=4;
const el=(n,a={},p)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e};
const leg=document.getElementById("legend");
PUBS.forEach((p,i)=>{const li=document.createElement("li"),s=document.createElement("i");s.style.background=col(i);li.append(s,document.createTextNode(p.label));leg.append(li)});
const chartEl=document.getElementById("chart"),tip=document.getElementById("tip");let lastW=0;
function draw(){
const W=Math.max(320,Math.round(chartEl.clientWidth||900)),narrow=W<600,H=narrow?380:460,M={l:narrow?44:56,r:12,t:18,b:narrow?50:56},iw=W-M.l-M.r,ih=H-M.t-M.b;
const y=v=>M.t+ih-v/YMAX*ih, band=iw/DATA.length, bw=Math.min(24,Math.round(band*.62));lastW=chartEl.clientWidth;
chartEl.replaceChildren();
const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,width:W,height:H,role:"img","aria-label":"แท่งซ้อนจำนวนบทตรวจรายปี แยกตามสำนัก ปี 2558 ถึง 2569"});
chartEl.append(svg);
// partial-year bands
DATA.forEach((d,i)=>{if(d.partial)el("rect",{x:M.l+i*band+2,y:M.t,width:band-4,height:ih,rx:6,fill:"var(--band)"},svg)});
// grid + y ticks
[0,1000,2000,3000].forEach(t=>{el("line",{x1:M.l,x2:W-M.r,y1:y(t),y2:y(t),stroke:t?"var(--grid)":"var(--axis)","stroke-width":1},svg);
 const tx=el("text",{x:M.l-8,y:y(t)+4,"text-anchor":"end","font-size":12,fill:"var(--muted)"},svg);tx.textContent=fmt(t)});
// annotation: archive changes hands (wide layouts only; the note and table carry it otherwise)
const bx=M.l+5*band;
if(!narrow){el("line",{x1:bx,x2:bx,y1:y(2800),y2:y(0),stroke:"var(--axis)","stroke-width":1},svg);
[["ก่อน 2563: ชัวร์ก่อนแชร์ 93.4%","ของ 1,187 บทตรวจ (2558–2562)"],["2563: AFNC เข้ามาเป็น 74.2%","ของบทตรวจปีนั้น (2562: 18.0%)"]].forEach((ls,j)=>{
 ls.forEach((s,k)=>{const t=el("text",{x:j?bx+8:bx-8,y:y(2800)+14+k*15,"text-anchor":j?"start":"end","font-size":12,fill:k?"var(--muted)":"var(--ink2)","font-weight":k?400:600},svg);t.textContent=s})})}
if(narrow){const c=el("text",{x:M.l,y:H-6,"font-size":11,fill:"var(--muted)"},svg);c.textContent="ปี พ.ศ. 25xx · * = ไม่เต็มปี"}
// stacks
function showTip(d,ev,el_){
 tip.replaceChildren();
 const h=document.createElement("div");h.className="h";h.textContent=`ปี ${d.be} (ค.ศ. ${d.year})${d.partial?" · ไม่เต็มปี":""}`;tip.append(h);
 PUBS.forEach((p,i)=>{const r=document.createElement("div");r.className="r";const k=document.createElement("span");k.className="k";k.style.background=col(i);
  const n=document.createElement("span");n.className="n";n.textContent=p.label;const v=document.createElement("span");v.className="v";v.textContent=fmt(d.by[p.key]);r.append(k,n,v);tip.append(r)});
 const t=document.createElement("div");t.className="r tot";const n=document.createElement("span");n.className="n";n.textContent="รวม";const v=document.createElement("span");v.className="v";v.textContent=fmt(d.total);t.append(n,v);tip.append(t);
 const bb=el_.getBoundingClientRect();let x=bb.right+8,yy=Math.max(8,bb.top+20);if(x+210>innerWidth)x=bb.left-218;tip.style.left=Math.max(8,x)+"px";tip.style.top=yy+"px";tip.style.opacity=1}
const hideTip=()=>tip.style.opacity=0;
function topRounded(x,yt,w,h,r){r=Math.min(r,h/2);return `M${x},${yt+h}V${yt+r}Q${x},${yt} ${x+r},${yt}H${x+w-r}Q${x+w},${yt} ${x+w},${yt+r}V${yt+h}Z`}
DATA.forEach((d,i)=>{
 const g=el("g",{class:"col",tabindex:0,role:"img","aria-label":`ปี ${d.be}: รวม ${fmt(d.total)} บทตรวจ — `+PUBS.map(p=>`${p.label} ${fmt(d.by[p.key])}`).join(", ")},svg);
 const cx=M.l+i*band+band/2, x0=cx-bw/2;
 el("rect",{class:"hit",x:M.l+i*band,y:M.t,width:band,height:ih,fill:"transparent"},g);
 const segs=PUBS.map((p,k)=>({k,v:d.by[p.key]})).filter(s=>s.v>0);let acc=0;
 segs.forEach((s,idx)=>{const y1=y(acc+s.v),y0=y(acc),h=y0-y1;acc+=s.v;
  const top=idx===segs.length-1, hh=Math.max(h-(idx?0:0),1);
  const yt=y1, hgt=h-(idx>0?GAP:0)  ; // 2px surface gap sits at the bottom edge of every segment above the first
  const rect=top?el("path",{d:topRounded(x0,yt,bw,Math.max(hgt,1),R),fill:col(s.k)},g):el("rect",{x:x0,y:yt,width:bw,height:Math.max(hgt,1),fill:col(s.k)},g);
 });
 if(d.year===2023||i===DATA.length-1){const t=el("text",{x:(narrow&&i===DATA.length-1)?W-4:cx,y:y(d.total)-7,"text-anchor":(narrow&&i===DATA.length-1)?"end":"middle","font-size":12.5,"font-weight":650,fill:"var(--ink)"},g);t.textContent=fmt(d.total)+(d.partial?"*":"")}
 const lb=el("text",{x:cx,y:H-M.b+20,"text-anchor":"middle","font-size":narrow?11:13,fill:"var(--ink2)"},g);lb.textContent=(narrow?String(d.be).slice(2):d.be)+(d.partial?"*":"");
 if(d.partial&&!narrow){const t=el("text",{x:cx,y:H-M.b+37,"text-anchor":"middle","font-size":11,fill:"var(--muted)"},g);t.textContent="ไม่เต็มปี"}
 g.addEventListener("pointermove",e=>showTip(d,e,g));g.addEventListener("pointerenter",e=>showTip(d,e,g));g.addEventListener("pointerleave",hideTip);
 g.addEventListener("focus",e=>showTip(d,e,g));g.addEventListener("blur",hideTip);
});
}
draw();new ResizeObserver(()=>{if(Math.abs(chartEl.clientWidth-lastW)>2)draw()}).observe(chartEl);
// table view
const tb=document.getElementById("tbl");
(function(){const t=document.createElement("table"),th=document.createElement("thead"),hr=document.createElement("tr");
 ["ปี (พ.ศ.)",...PUBS.map(p=>p.label),"รวม"].forEach(s=>{const c=document.createElement("th");c.textContent=s;hr.append(c)});th.append(hr);t.append(th);
 const b=document.createElement("tbody");DATA.forEach(d=>{const r=document.createElement("tr");[d.be+(d.partial?"*":""),...PUBS.map(p=>fmt(d.by[p.key])),fmt(d.total)].forEach(s=>{const c=document.createElement("td");c.textContent=s;r.append(c)});b.append(r)});
 const r=document.createElement("tr");r.style.fontWeight=650;["รวม",...PUBS.map(p=>fmt(DATA.reduce((a,d)=>a+d.by[p.key],0))),fmt(DATA.reduce((a,d)=>a+d.total,0))].forEach(s=>{const c=document.createElement("td");c.textContent=s;r.append(c)});b.append(r);t.append(b);tb.append(t)})();
const tg=document.getElementById("tg");tg.onclick=()=>{const open=tb.classList.toggle("hidden")===false;tg.setAttribute("aria-expanded",open);tg.textContent=open?"ซ่อนตาราง":"ดูเป็นตาราง"};
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(ROOT / "runs/20261007_story1_viz_v001")); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    data, pubs = build()
    (out / "records_by_publisher_year.csv").write_text(
        "year_ce,year_be,partial_year," + ",".join(k for k, _ in ORDER) + ",total\n" +
        "\n".join(f"{d['year']},{d['be']},{d['partial']}," + ",".join(str(d['by'][k]) for k, _ in ORDER) + f",{d['total']}" for d in data) + "\n", encoding="utf-8")
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__PUBS__", json.dumps(pubs, ensure_ascii=False))
    (out / "chart_records_by_publisher.html").write_text(html, encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
