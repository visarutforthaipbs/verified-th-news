#!/usr/bin/env python3
"""Build the single-file review app for the Story 1 purity sheets (human_pure / human_note).

Inputs (read-only): runs/20261004_story1_by_publisher_v001/topic0_samples.csv (sheet A, 70 rows, topic 0)
                    runs/20261004_purity_v001/named_topic_samples.csv      (sheet B, 210 rows, 7 topics)
Output: deliverables/story1_review/purity_review_app.html (offline, localStorage autosave, CSV export in the ORIGINAL columns/order)
Refuses to build if either sheet already has a human_pure/human_note value (the app starts blank by design).
The assistant's own earlier read of the samples (63/70) is NOT in these files and is not shown in the app.
"""
import csv, json, sys
from pathlib import Path

csv.field_size_limit(10**9)
ROOT = Path(__file__).resolve().parent.parent
SHEET_A = ROOT / "runs/20261004_story1_by_publisher_v001/topic0_samples.csv"
SHEET_B = ROOT / "runs/20261004_purity_v001/named_topic_samples.csv"
TOPICS_CSV = ROOT / "runs/20260908_bertopic_v001/topics.csv"
TEMPLATE = ROOT / "assets/story1_review_app/template.html"
OUT = ROOT / "deliverables/story1_review/purity_review_app.html"

TOPIC_A = {"0": {"name": "สุขภาพ อาหาร และเรื่องใกล้ตัว", "short": "สุขภาพ-อาหาร",
                 "rule": "ข้ออ้างเรื่องสุขภาพ อาหาร หรือร่างกาย (รวมโรค ยา อาหารเสริม สมุนไพร) ถ้าเป็นเรื่องอื่น เช่น บ้าน รถ คลิปแปลก ให้ตอบ “ไม่ตรง”"}}
TOPIC_B = {
    "1": {"name": "ชวนลงทุน–ปันผล ในนามตลาดหลักทรัพย์/กองทุน", "short": "ลงทุน-ปันผล", "rule": "ข้ออ้างชวนลงทุนหุ้น กองทุน หรือปันผล โดยอ้างชื่อตลาดหลักทรัพย์ ก.ล.ต. หรือหน่วยงานการเงิน"},
    "2": {"name": "รับทำใบขับขี่ออนไลน์", "short": "ใบขับขี่", "rule": "ข้ออ้างเรื่องการทำหรือต่อใบขับขี่ผ่านเพจหรือช่องทางที่อ้างหน่วยงานขนส่ง ถ้ามีคำว่าใบขับขี่แต่ไม่ใช่ข้ออ้างทางลัดทำใบขับขี่ ให้ตอบ “ไม่ตรง”"},
    "4": {"name": "ป้องกัน/รักษา/ฆ่าเชื้อไวรัสหรือโควิด", "short": "ป้องกัน-รักษา", "rule": "ข้ออ้างว่ากิน ใช้ หรือทำสิ่งใดแล้วป้องกัน รักษา หรือฆ่าเชื้อไวรัส/โควิดได้"},
    "6": {"name": "ทหารและชายแดนไทย–กัมพูชา", "short": "ชายแดน", "rule": "ข้ออ้างเกี่ยวกับทหาร การปะทะ อาวุธ หรือพื้นที่ชายแดนไทย–กัมพูชา"},
    "7": {"name": "พบผู้ติดเชื้อ/การระบาด", "short": "พบผู้ติดเชื้อ", "rule": "ข้ออ้างว่าพบผู้ติดเชื้อหรือโรคระบาดในสถานที่หรือกลุ่มคน (ไวรัสหรือโรคติดต่อ)"},
    "11": {"name": "อ้างคืนเงินให้ผู้เสียหาย", "short": "คืนเงิน", "rule": "ข้ออ้างว่ามีการลงทะเบียนหรือคืนเงินให้ผู้เสียหายจากแก๊งหรือการหลอกลวง (เช่น อ้าง ปปง.) ผ่านเพจหรือลิงก์"},
    "18": {"name": "วัคซีน", "short": "วัคซีน", "rule": "ข้ออ้างเกี่ยวกับวัคซีน (ผลข้างเคียง ส่วนผสม การฉีด ฯลฯ)"},
}


def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def kw():
    d = {}
    for r in rd(TOPICS_CSV)[1]:
        d[r["topic_id"]] = " · ".join(x.strip() for x in r["machine_keywords"].split("|")[:6])
    return d


def sheet(path, topics, name):
    cols, rows = rd(path)
    assert "human_pure" in cols and "human_note" in cols
    if any((r["human_pure"] or r["human_note"]) for r in rows):
        sys.exit(f"{path.name} already has human answers; refusing to build a blank app over it")
    keys = {(r["id"], r["topic_id"]) for r in rows}
    assert len(keys) == len(rows), "duplicate (id, topic_id) keys"
    out = []
    for r in rows:
        assert r["topic_id"] in topics, r["topic_id"]
        out.append({"id": r["id"], "topic_id": r["topic_id"], "year": r["year"], "source": r["source"], "title": r["title"],
                    "claim_text": r.get("claim_text", ""), "url": r["url"], "orig": r})
    return {"filename": name, "columns": cols, "rows": out}


def main():
    k = kw()
    for t in (TOPIC_A, TOPIC_B):
        for i, v in t.items():
            v["keywords"] = k.get(i, "")
    A = sheet(SHEET_A, TOPIC_A, "topic0_samples.csv"); A["topics"] = TOPIC_A
    B = sheet(SHEET_B, TOPIC_B, "named_topic_samples.csv"); B["topics"] = TOPIC_B
    assert len(A["rows"]) == 70 and len(B["rows"]) == 210, (len(A["rows"]), len(B["rows"]))
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", json.dumps({"A": A, "B": B}, ensure_ascii=False).replace("</", "<\\/"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print("wrote", OUT, len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
