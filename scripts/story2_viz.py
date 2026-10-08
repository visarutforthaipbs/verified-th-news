#!/usr/bin/env python3
"""Story 2 figures (AI-coded, not human-validated).

Fig 1  in-scope records per year, stacked by target group (other / Cambodia / Israel), with the share of that year's archive
Fig 2  two claims that were fact-checked again and again: dates of each AFNC fact-check

Reads runs/20261007_story2_aicoded_v001/ai_by_year.csv and runs/20260908_bertopic_v001/assignments.csv.
Writes self-contained HTML (inline SVG, tooltip, table view, light/dark) + tidy CSVs into --out.
"""
import argparse, csv, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from story1_viz_virus_impersonation import CSS, JS_COMMON  # shared chart chrome

csv.field_size_limit(10**9)
ROOT = Path(__file__).resolve().parent.parent
BY_YEAR = ROOT / "runs/20261007_story2_aicoded_v001/ai_by_year.csv"
ASSIGN = ROOT / "runs/20260908_bertopic_v001/assignments.csv"
RECUR = [("“กระทรวงแรงงานปลดล็อก 5 อาชีพให้แรงงานต่างชาติ”", ["15406", "13929", "13177", "7940"]),
         ("“ลักลอบนำชาวมุสลิมต่างด้าวเข้าภูเก็ตตอนกลางคืนด้วยรถตู้”", ["14480", "13918", "12036", "9740"])]

HTML_YEAR = r"""<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>บทตรวจเรื่องคนข้ามชาติ รายปี</title><style>__CSS__</style></head><body>
<div class="wrap"><div class="card">
<h1>บทตรวจเรื่องคนข้ามชาติในชุดที่ AI คัด: เพิ่มในปี 2568–2569 และไม่ได้มาจากกัมพูชาอย่างเดียว</h1>
<p class="sub">จำนวนบทตรวจต่อปี (พ.ศ.) แยกตามกลุ่มคนที่ข้ออ้างพูดถึง · ตัวเลขเหนือแท่ง = จำนวน และร้อยละของบทตรวจทั้งหมดในปีนั้น</p>
<ul class="legend" id="legend"></ul><div id="chart"></div>
<div class="tools"><button class="t" id="tg" type="button" aria-expanded="false">ดูเป็นตาราง</button></div><div id="tbl" class="hidden"></div>
<p class="note"><b>AI เป็นผู้คัดและลงรหัสทั้งหมด ไม่มีมนุษย์ตรวจซ้ำ</b> (เทียบกับ 30 ข้อที่บรรณาธิการลงเอง ตรงกันเรื่องขอบเขต 19 ข้อ) · ปี 2563–2566 มีเพียง 4–6 บทตรวจต่อปี จึงห้ามอ่านเป็น “เพิ่มขึ้นกี่เท่า” · ช่วงหลังมีสำนักใหม่เข้ามาในคลังด้วย · พื้นแรเงา = 2569 ถึง 1 ก.ย. ไม่เต็มปี · “คนข้ามชาติ” = แรงงานข้ามชาติ ผู้ลี้ภัย คนไร้สัญชาติ และผู้พำนักต่างชาติทุกสัญชาติ ไม่รวมนักท่องเที่ยว · นับบทตรวจ ไม่ใช่จำนวนข่าวลวง · ก่อนปี 2563 ไม่มีบทตรวจในชุดนี้<br>ที่มา: คิวตรวจ 513 บันทึกจากคลัง 14,429 บันทึก (สแนปช็อต 2 ก.ย. 2569) · ai_by_year.csv</p>
</div></div><div id="tip" role="status"></div>
<script>__JS__
const DATA=__DATA__, SER=[["other","กลุ่มอื่น (เมียนมา จีน ไม่ระบุสัญชาติ ฯลฯ)",0],["cambodia","กัมพูชา",1],["israel","อิสราเอล/ชาวยิว",2]];
const col=i=>`var(--s${i+1})`, chartEl=document.getElementById("chart");let lastW=0;const YMAX=80,GAP=2,R=4;
const leg=document.getElementById("legend");SER.forEach(s=>{const li=document.createElement("li"),k=document.createElement("i");k.style.background=col(s[2]);li.append(k,document.createTextNode(s[1]));leg.append(li)});
function draw(){const W=Math.max(320,Math.round(chartEl.clientWidth||900)),narrow=W<600,H=narrow?360:430,M={l:narrow?34:46,r:10,t:38,b:narrow?46:54},iw=W-M.l-M.r,ih=H-M.t-M.b;lastW=chartEl.clientWidth;
 const band=iw/DATA.length,bw=Math.min(24,Math.round(band*.5)),Y=v=>M.t+ih-v/YMAX*ih;chartEl.replaceChildren();
 const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,width:W,height:H,role:"img","aria-label":"แท่งซ้อนจำนวนบทตรวจเรื่องคนข้ามชาติรายปี แยกตามกลุ่ม"});chartEl.append(svg);
 DATA.forEach((d,i)=>{if(d.partial)el("rect",{x:M.l+i*band+2,y:M.t-30,width:band-4,height:ih+30,rx:6,fill:"var(--band)"},svg)});
 [0,20,40,60,80].forEach(t=>{el("line",{x1:M.l,x2:W-M.r,y1:Y(t),y2:Y(t),stroke:t?"var(--grid)":"var(--axis)","stroke-width":1},svg);const tx=el("text",{x:M.l-8,y:Y(t)+4,"text-anchor":"end","font-size":12,fill:"var(--muted)"},svg);tx.textContent=t});
 const top=(x,yt,w,h,r)=>{r=Math.min(r,h/2);return `M${x},${yt+h}V${yt+r}Q${x},${yt} ${x+r},${yt}H${x+w-r}Q${x+w},${yt} ${x+w},${yt+r}V${yt+h}Z`};
 DATA.forEach((d,i)=>{const cx=M.l+i*band+band/2,x0=cx-bw/2,g=el("g",{class:"col",tabindex:0,role:"img","aria-label":`ปี ${d.be}: ${d.total} บทตรวจ (${d.share}% ของบทตรวจปีนั้น) — `+SER.map(s=>`${s[1]} ${d[s[0]]}`).join(", ")},svg);
  el("rect",{class:"hit",x:M.l+i*band,y:M.t-30,width:band,height:ih+30,fill:"transparent"},g);
  const segs=SER.map(s=>({k:s[2],v:d[s[0]]})).filter(s=>s.v>0);let acc=0;
  segs.forEach((s,idx)=>{const y1=Y(acc+s.v),h=Y(acc)-y1-(idx>0?GAP:0);acc+=s.v;const last=idx===segs.length-1;
   if(last)el("path",{d:top(x0,y1,bw,Math.max(h,1),R),fill:col(s.k)},g);else el("rect",{x:x0,y:y1,width:bw,height:Math.max(h,1),fill:col(s.k)},g)});
  const a=el("text",{x:cx,y:Y(d.total)-(narrow?8:20),"text-anchor":"middle","font-size":13,"font-weight":650,fill:"var(--ink)"},g);a.textContent=d.total+(d.partial?"*":"");
  if(!narrow){const b=el("text",{x:cx,y:Y(d.total)-6,"text-anchor":"middle","font-size":11.5,fill:"var(--muted)"},g);b.textContent=d.share.toFixed(2)+"%"}
  const lb=el("text",{x:cx,y:H-M.b+20,"text-anchor":"middle","font-size":narrow?11:13,fill:"var(--ink2)"},g);lb.textContent=(narrow?String(d.be).slice(2):d.be)+(d.partial?"*":"");
  if(d.partial&&!narrow){const t=el("text",{x:cx,y:H-M.b+37,"text-anchor":"middle","font-size":11,fill:"var(--muted)"},g);t.textContent="ไม่เต็มปี"}
  const show=()=>{tip.replaceChildren();tip.append(div("h",`ปี ${d.be}${d.partial?" · ไม่เต็มปี":""}`));
   SER.forEach(s=>{const r=div("r"),k=span("k");k.style.background=col(s[2]);r.append(k,span("n",s[1]),span("v",fmt(d[s[0]])));tip.append(r)});
   const r=div("r tot");r.append(span("n","รวม"),span("v",fmt(d.total)));tip.append(r);tip.append(div("s",`${d.share.toFixed(2)}% ของ ${fmt(d.all)} บทตรวจปีนั้น · ไม่นับกัมพูชา ${d.share_excl_kh.toFixed(2)}%`));placeTip(g)};
  g.addEventListener("pointermove",show);g.addEventListener("pointerenter",show);g.addEventListener("focus",show);g.addEventListener("pointerleave",hideTip);g.addEventListener("blur",hideTip)});
 if(narrow){const c=el("text",{x:M.l,y:H-6,"font-size":11,fill:"var(--muted)"},svg);c.textContent="ปี พ.ศ. 25xx · * = ไม่เต็มปี"}}
draw();new ResizeObserver(()=>{if(Math.abs(chartEl.clientWidth-lastW)>2)draw()}).observe(chartEl);
buildTable(document.getElementById("tbl"),["ปี (พ.ศ.)","กลุ่มอื่น","กัมพูชา","อิสราเอล","รวม","บทตรวจทั้งปี","ร้อยละของปี","ร้อยละเมื่อไม่นับกัมพูชา"],DATA.map(d=>[d.be+(d.partial?"*":""),d.other,d.cambodia,d.israel,d.total,fmt(d.all),d.share.toFixed(2)+"%",d.share_excl_kh.toFixed(2)+"%"]));
wireToggle(document.getElementById("tg"),document.getElementById("tbl"));
</script></body></html>"""

HTML_RECUR = r"""<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ข้ออ้างที่ถูกตรวจซ้ำ</title><style>__CSS__ .tl h2{font-size:14.5px;margin:14px 0 2px;font-weight:650}.tl .cap{font-size:12.5px;color:var(--ink2);margin:0}</style></head><body>
<div class="wrap"><div class="card">
<h1>สองข้ออ้างเรื่องคนข้ามชาติที่ถูกตรวจซ้ำ ข้อละ 4 ครั้ง (ปี 2564–2567)</h1>
<p class="sub">แต่ละจุด = บทตรวจ 1 ครั้งของศูนย์ต่อต้านข่าวปลอม (AFNC) ตามวันเผยแพร่บทตรวจ ทุกครั้งมีผลว่าเป็นข่าวปลอม</p>
<div class="tl" id="tl"></div>
<div class="tools"><button class="t" id="tg" type="button" aria-expanded="false">ดูเป็นตาราง</button></div><div id="tbl" class="hidden"></div>
<p class="note">วันที่คือวันเผยแพร่บทตรวจ ไม่ใช่วันที่ข้ออ้างเริ่มแพร่ · ยังไม่ได้เปิดบทตรวจยืนยันว่าแต่ละครั้งอ้างถึงโพสต์ต้นเหตุคนละโพสต์หรือโพสต์เดิม จึงเรียกว่า “ถูกตรวจซ้ำ” ไม่ใช่ “กลับมา” · ถ้อยคำของแต่ละครั้งต่างกันเล็กน้อย (ครั้งแรกของข้ออ้างภูเก็ตระบุว่าผู้ว่าราชการจังหวัดเป็นผู้นำเข้า)<br>ที่มา: คลังบันทึกผลตรวจสอบ 5 สำนัก (สแนปช็อต 2 ก.ย. 2569) · assignments.csv</p>
</div></div><div id="tip" role="status"></div>
<script>__JS__
const DATA=__DATA__, host=document.getElementById("tl");let lastW=0;
const TH=["ม.ค.","ก.พ.","มี.ค.","เม.ย.","พ.ค.","มิ.ย.","ก.ค.","ส.ค.","ก.ย.","ต.ค.","พ.ย.","ธ.ค."];
const dstr=s=>{const [y,m,d]=s.split("-").map(Number);return `${d} ${TH[m-1]} ${(y+543)%100}`};
const T0=Date.UTC(2021,0,1),T1=Date.UTC(2024,11,31),tx=s=>{const [y,m,d]=s.split("-").map(Number);return (Date.UTC(y,m-1,d)-T0)/(T1-T0)};
function draw(){lastW=host.clientWidth;host.replaceChildren();const W=Math.max(300,Math.round(host.clientWidth||900)),narrow=W<600,H=118,M={l:14,r:14},iw=W-M.l-M.r;
 DATA.forEach(row=>{const h=document.createElement("h2");h.textContent=row.label;host.append(h);
  const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,width:W,height:H,role:"img","aria-label":row.label+": วันที่ถูกตรวจ "+row.items.map(i=>dstr(i.date)).join(", ")});host.append(svg);const y=62;
  el("line",{x1:M.l,x2:W-M.r,y1:y,y2:y,stroke:"var(--axis)","stroke-width":1},svg);
  [2021,2022,2023,2024,2025].forEach(yr=>{const x=M.l+iw*((Date.UTC(yr,0,1)-T0)/(T1-T0));if(x>W-M.r+1)return;el("line",{x1:x,x2:x,y1:y-5,y2:y+5,stroke:"var(--axis)","stroke-width":1},svg);
   if(x>W-M.r-34)return;const t=el("text",{x:x+4,y:H-6,"font-size":11.5,fill:"var(--muted)"},svg);t.textContent=yr+543});
  row.items.forEach((it,k)=>{const x=M.l+iw*tx(it.date),up=k%2===0,g=el("g",{class:"col",tabindex:0,role:"img","aria-label":`${dstr(it.date)}: ${it.claim}`},svg);
   el("rect",{class:"hit",x:x-16,y:y-34,width:32,height:68,fill:"transparent"},g);
   el("line",{x1:x,x2:x,y1:up?y-22:y+22,y2:y,stroke:"var(--axis)","stroke-width":1},g);
   el("circle",{cx:x,cy:y,r:6,fill:"var(--s2)",stroke:"var(--surface)","stroke-width":2},g);
   const anchor=x<70?"start":x>W-70?"end":"middle";const t=el("text",{x:anchor==="start"?x-4:anchor==="end"?x+4:x,y:up?y-28:y+36,"text-anchor":anchor,"font-size":12.5,"font-weight":650,fill:"var(--ink)"},g);t.textContent=dstr(it.date);
   const show=()=>{tip.replaceChildren();tip.append(div("h",`${dstr(it.date)} · AFNC · ข่าวปลอม`));tip.append(div("",it.claim));tip.append(div("s",`ID ${it.id}`));placeTip(g)};
   g.addEventListener("pointermove",show);g.addEventListener("pointerenter",show);g.addEventListener("focus",show);g.addEventListener("pointerleave",hideTip);g.addEventListener("blur",hideTip)})})}
draw();new ResizeObserver(()=>{if(Math.abs(host.clientWidth-lastW)>2)draw()}).observe(host);
(function(){const rows=[];DATA.forEach(r=>r.items.forEach(i=>rows.push([r.label,dstr(i.date),i.claim,"ID "+i.id])));buildTable(document.getElementById("tbl"),["ข้ออ้าง","วันที่ตรวจ","ถ้อยคำในคลัง","รหัส"],rows);wireToggle(document.getElementById("tg"),document.getElementById("tbl"))})();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(ROOT / "runs/20261008_story2_viz_v001")); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    years = []
    for r in csv.DictReader(open(BY_YEAR, encoding="utf-8-sig")):
        y = int(r["year"])
        if y < 2020:
            assert int(r["in_scope"]) == 0; continue
        kh, il, tot = int(r["grp_cambodia"]), int(r["grp_israel"]), int(r["in_scope"])
        years.append({"year": y, "be": y + 543, "partial": y == 2026, "other": tot - kh - il, "cambodia": kh, "israel": il, "total": tot,
                      "all": int(r["all_records"]), "share": float(r["share_pct"]), "share_excl_kh": float(r["excl_cambodia_pct"])})
    assert sum(d["total"] for d in years) == 156 and [d["total"] for d in years] == [5, 4, 6, 4, 20, 50, 67]
    assert sum(d["cambodia"] for d in years) == 52 and sum(d["israel"] for d in years) == 17
    asg = {r["id"]: r for r in csv.DictReader(open(ASSIGN, encoding="utf-8-sig"))}
    recur = []
    for label, ids in RECUR:
        items = []
        for i in ids:
            r = asg[i]; assert r["source"] == "afnc" and r["verdict"] == "false", i
            items.append({"id": i, "date": r["date"], "claim": r["claim_text"], "url": r["url"]})
        recur.append({"label": label, "items": sorted(items, key=lambda x: x["date"])})
    assert [x["date"] for x in recur[0]["items"]] == ["2021-02-01", "2022-01-29", "2022-05-15", "2024-03-21"]
    assert [x["date"] for x in recur[1]["items"]] == ["2021-10-24", "2022-01-31", "2022-10-21", "2023-07-27"]
    rep = lambda t, d: t.replace("__CSS__", CSS).replace("__JS__", JS_COMMON).replace("__DATA__", json.dumps(d, ensure_ascii=False))
    (out / "chart_migrant_records_by_year.html").write_text(rep(HTML_YEAR, years), encoding="utf-8")
    (out / "chart_recurring_claims.html").write_text(rep(HTML_RECUR, recur), encoding="utf-8")
    with open(out / "migrant_records_by_year.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["year_be", "other", "cambodia", "israel", "total", "all_records", "share_pct", "share_excl_cambodia_pct", "coded_by"])
        for d in years: w.writerow([d["be"], d["other"], d["cambodia"], d["israel"], d["total"], d["all"], d["share"], d["share_excl_kh"], "assistant"])
    with open(out / "recurring_claims.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["claim_family", "date", "id", "claim_text", "url"])
        for r in recur:
            for i in r["items"]: w.writerow([r["label"], i["date"], i["id"], i["claim"], i["url"]])
    print("wrote", out)


if __name__ == "__main__":
    main()
