#!/usr/bin/env python3
"""Assistant (AI) second read of the Story 1 purity sheets, compared with the owner's read.

The assistant read titles/claim text only (not the source pages) against the same rule shown in the review app.
Default for every row is 1 (matches the group); the rows below are the exceptions (0 = does not match, ? = unsure).
Writes deliverables/story1_review/assistant_second_read.csv (all 280 rows, both readers side by side) and prints agreement.
With --apply it ALSO rewrites the two sheets: for disputed rows human_pure takes the AI value and human_note records
"[AI second read: owner said X -> Y; reason]"; the owner's untouched submission stays in deliverables/story1_review/owner_submitted_20261007/.
"""
import argparse, csv, sys
from pathlib import Path

csv.field_size_limit(10**9)
ROOT = Path(__file__).resolve().parent.parent
SHEETS = {"A": ROOT / "runs/20261004_story1_by_publisher_v001/topic0_samples.csv", "B": ROOT / "runs/20261004_purity_v001/named_topic_samples.csv"}
OWNER = ROOT / "deliverables/story1_review/owner_submitted_20261007"
OUT = ROOT / "deliverables/story1_review/assistant_second_read.csv"

EXC = {  # (topic_id, id): (value, reason)
    ("0", "26533"): ("1", "เรื่องอาหารโดยตรง เจ้าของยังไม่ได้ตอบ"),
    ("0", "25780"): ("0", "คลิปปลาร้องไห้ ไม่ใช่สุขภาพ/อาหาร (เห็นตรงกับเจ้าของ)"),
    ("0", "25491"): ("0", "ซ่อมอ่างล้างหน้า ไม่ใช่สุขภาพ/อาหาร (เห็นตรงกับเจ้าของ)"),
    ("0", "25235"): ("0", "ทารกปีศาจ ไม่ใช่สุขภาพ/อาหาร (เห็นตรงกับเจ้าของ)"),
    ("0", "24622"): ("0", "เทคนิคขับรถลงเขา ไม่ใช่สุขภาพ/อาหาร (เห็นตรงกับเจ้าของ)"),
    ("0", "24483"): ("0", "แอลกอฮอล์กุญแจรถ ไม่ใช่สุขภาพ/อาหาร (เห็นตรงกับเจ้าของ)"),
    ("2", "7212"): ("0", "อบรม e-Learning ก.ค.ศ. ไม่ใช่ใบขับขี่ (เห็นตรงกับเจ้าของ)"),
    ("6", "14799"): ("0", "เด็กอาชีวะถูกยิงในม็อบ ไม่ใช่ชายแดน (เห็นตรงกับเจ้าของ)"),
    ("0", "25761"): ("?", "น้ำสบู่กำจัดยุง เป็นเรื่องบ้าน ไม่ใช่สุขภาพ/อาหาร/ร่างกายโดยตรง"),
    ("0", "25310"): ("?", "กระบองเพชรดูดรังสีจอคอม กึ่งสุขภาพกึ่งของใช้"),
    ("2", "28025"): ("0", "มอเตอร์เวย์ M6 ไม่เกี่ยวกับใบขับขี่"),
    ("2", "1641"): ("0", "เพจชำระค่าตั๋ว บขส. ไม่ใช่ทางลัดทำใบขับขี่"),
    ("4", "11954"): ("0", "ผลหลังหายจากโควิด ไม่ใช่ป้องกัน/รักษา/ฆ่าเชื้อ"),
    ("4", "9330"): ("0", "ผลหลังหายจากโควิด ไม่ใช่ป้องกัน/รักษา/ฆ่าเชื้อ"),
    ("4", "9911"): ("0", "เรื่องการแพร่เชื้อ ไม่ใช่ป้องกัน/รักษา"),
    ("4", "15164"): ("0", "เรื่องการตรวจ ไม่ใช่ป้องกัน/รักษา"),
    ("4", "15168"): ("0", "เรื่องการตรวจ ไม่ใช่ป้องกัน/รักษา"),
    ("7", "15614"): ("0", "มาตรการเดินทาง ไม่ใช่ข่าวพบผู้ติดเชื้อ"),
    ("7", "14356"): ("0", "มาตรการตรวจ/ลงทะเบียน ไม่ใช่ข่าวพบผู้ติดเชื้อ"),
    ("7", "8320"): ("0", "ผลทดลองไวรัสในหนู ไม่ใช่การพบผู้ติดเชื้อ"),
    ("7", "16919"): ("?", "ชื่อไม่บอกข้ออ้าง ต้องเปิดต้นทาง"),
    ("7", "26793"): ("?", "ภาพสุสานผู้ป่วยโควิด ไม่ใช่รายงานพบผู้ติดเชื้อโดยตรง"),
    ("6", "916"): ("0", "เรื่องเครื่องบินสหรัฐฯ/ตะวันออกกลาง ไม่ใช่ชายแดนไทย–กัมพูชา"),
    ("6", "3034"): ("?", "เรื่องสัญชาติ ไม่ใช่ทหาร/ชายแดนโดยตรง"),
    ("1", "1488"): ("?", "กองทุนผู้สูงอายุ ไม่ใช่ลงทุนหุ้น/ปันผลโดยตรง"),
    ("1", "1528"): ("?", "กองทุนผู้สูงอายุ ไม่ใช่ลงทุนหุ้น/ปันผลโดยตรง"),
}


def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); a = ap.parse_args()
    rows_out, seen = [], set()
    sheets = {}
    for sh, p in SHEETS.items():
        h, rows = rd(OWNER / p.name)   # always compare against the owner's untouched submission
        sheets[sh] = (h, rows)
        for r in rows:
            k = (r["topic_id"], r["id"])
            ai, why = EXC.get(k, ("1", ""))
            seen.add(k) if k in EXC else None
            rows_out.append({"sheet": sh, "topic_id": r["topic_id"], "id": r["id"], "year": r["year"], "source": r["source"], "title": r["title"],
                             "owner_pure": r["human_pure"], "assistant_pure": ai, "agree": "1" if r["human_pure"] == ai else "0", "assistant_reason": why})
    assert seen == set(EXC), set(EXC) - seen
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0])); w.writeheader(); w.writerows(rows_out)
    n = len(rows_out); ag = sum(r["agree"] == "1" for r in rows_out)
    dis = [r for r in rows_out if r["agree"] == "0"]
    print(f"rows {n}; owner and assistant agree on {ag} ({ag/n:.1%}); disputed {len(dis)} (owner blank: {sum(r['owner_pure']=='' for r in dis)})")
    by = {}
    for r in rows_out:
        d = by.setdefault(r["topic_id"], {"n": 0, "owner1": 0, "owner0": 0, "ai1": 0, "ai0": 0, "aiq": 0})
        d["n"] += 1; d["owner1"] += r["owner_pure"] == "1"; d["owner0"] += r["owner_pure"] == "0"
        d["ai1"] += r["assistant_pure"] == "1"; d["ai0"] += r["assistant_pure"] == "0"; d["aiq"] += r["assistant_pure"] == "?"
    for t, d in sorted(by.items(), key=lambda x: int(x[0])):
        print(f"topic {t:>2}: n={d['n']:>2} owner 1/0 = {d['owner1']}/{d['owner0']} | assistant 1/0/? = {d['ai1']}/{d['ai0']}/{d['aiq']}")
    if a.apply:
        for sh, p in SHEETS.items():
            h, rows = sheets[sh]
            for r in rows:
                k = (r["topic_id"], r["id"])
                if k in EXC and r["human_pure"] != EXC[k][0]:
                    v, why = EXC[k]
                    old = r["human_pure"] or "ว่าง"
                    r["human_note"] = f"[AI อ่านซ้ำ: เจ้าของตอบ {old} -> {v}; {why}] " + r["human_note"]
                    r["human_pure"] = v
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=h); w.writeheader(); w.writerows(rows)
        print("applied to the two sheets (owner's submission preserved in", OWNER, ")")


if __name__ == "__main__":
    sys.exit(main())
