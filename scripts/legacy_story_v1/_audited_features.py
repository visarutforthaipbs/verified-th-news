"""Build the corrected features from the delivered CSV snapshots.

Tables and prose share one content model across HTML and Markdown. This module
does not alter/reclassify records, open SQLite, run clustering, or load old run
metrics. The input CSVs remain historical artifacts with explicit limitations.
"""
from __future__ import annotations

import csv
import hashlib
from collections import Counter
from dataclasses import dataclass
from html import escape
from pathlib import Path

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[1]))  # shared libs live in scripts/
from _brand import document

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "data" / "reports"
REVISION = "8 กันยายน 2569 (2026-09-08)"
STEMS = {1: "investigative_11years_feature", 2: "migrant_deepdive_feature"}
DATASETS = {1: "article1_11years_claims.csv", 2: "article2_migrant_claims.csv"}
VERDICTS = {
    "false": "เท็จ", "true": "จริง", "misleading": "บิดเบือน",
    "unknown": "ยังไม่ทราบผล", "scam_alert": "เตือนภัยหลอกลวง",
    "altered_media": "สื่อดัดแปลง", "satire": "เสียดสี",
}
FRAMES = {
    "disease": "โรคระบาดและสุขอนามัย",
    "economic": "เศรษฐกิจ อาชีพ และสวัสดิการ",
    "sovereignty": "สัญชาติ อธิปไตย และสิทธิการเมือง",
    "broker": "การลักลอบและนายหน้า",
    "other": "อื่น ๆ / ไม่เข้าเกณฑ์สี่กลุ่มข้างต้น",
}


def load_rows(number: int, directory: Path = REPORTS / "datasets") -> list[dict]:
    with (directory / DATASETS[number]).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or len({r["claim_id"] for r in rows}) != len(rows):
        raise ValueError("Dataset must be nonempty with unique claim IDs")
    for row in rows:
        if row["verdict"] not in VERDICTS:
            raise ValueError(f"Unmapped verdict: {row['verdict']}")
        if not row["published_year"].isdigit() or len(row["published_date"]) != 10:
            raise ValueError("Missing or invalid publication date; review dataset first")
        if number == 2 and row["narrative_frame_id"] not in FRAMES:
            raise ValueError(f"Unmapped narrative frame: {row['narrative_frame_id']}")
    return rows


def pct(count: int, total: int) -> str:
    return f"{count / total * 100:.2f}%" if total else "ไม่มีข้อมูล"


def period(rows: list[dict], first: int, last: int) -> list[dict]:
    return [r for r in rows if first <= int(r["published_year"]) <= last]


@dataclass(frozen=True)
class Block:
    kind: str
    title: str
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()


def table(title: str, headers: list[str], rows: list[list[str]]) -> Block:
    return Block("table", title, tuple(headers), tuple(tuple(row) for row in rows))


def sources(number: int, rows: list[dict]) -> list[Block]:
    dataset = DATASETS[number]
    return [
        Block("heading", "ข้อมูลประกอบและวิธีอ่าน"),
        Block("paragraph", "ทุกจำนวนในตารางนับหนึ่งแถวต่อหนึ่งบันทึกการตรวจสอบ ไม่ใช่หนึ่งเหตุการณ์ที่ไม่ซ้ำ "
              "ไม่ใช่ยอดแชร์ และไม่ใช่จำนวนประชาชนที่เชื่อข้อความนั้น สัดส่วนใช้จำนวนบันทึกทั้งหมดในช่วงที่ระบุเป็นตัวหาร "
              "ไม่ตัดกลุ่มอื่น ๆ ออกจากฐานคำนวณ ผลรวมเปอร์เซ็นต์อาจคลาดเล็กน้อยจากการปัดเศษ"),
        Block("paragraph", f"วันที่เผยแพร่รายการล่าสุดในชุดข้อมูล: {max(r['published_date'] for r in rows)} "
              "ข้อมูลปี 2569 ยังไม่ครบปี จำนวนและสัดส่วนยังขึ้นกับความครอบคลุมและการเลือกเรื่องของแต่ละสำนักตรวจสอบ "
              "จึงไม่ใช่ตัวแทนความชุกของข่าวลวงทั้งสังคมไทย"),
        Block("links", "เอกสารประกอบ", rows=(
            ("ดาวน์โหลด CSV ที่ใช้คำนวณ — ชุดเดิมที่ยังมีข้อจำกัดตามบทความ", f"datasets/{dataset}"),
            ("ผล audit ของฉบับก่อนแก้ไข (8 กันยายน 2569)", "prachatai_deliverables_audit_2026-09-08.md"),
        )),
    ]


def overview(rows: list[dict]) -> tuple[str, str, list[Block]]:
    total = len(rows)
    topics = Counter(r["topic_code"] for r in rows)
    names = {r["topic_code"]: r["topic_name"] for r in rows}
    origins = Counter(r["verdict_origin"] for r in rows)
    verdicts = Counter(r["verdict"] for r in rows)
    periods = [(2015, 2018), (2019, 2021), (2022, 2023), (2024, 2025), (2026, 2026)]
    timeline = []
    for first, last in periods:
        group = period(rows, first, last)
        counts = Counter(r["topic_code"] for r in group)
        label = f"{first + 543}–{last + 543}" if first != last else f"{first + 543} (บางปี)"
        timeline.append([label, f"{len(group):,}", pct(counts['T01'], len(group)),
                         pct(counts['T02'], len(group)), pct(counts['T03'] + counts['T04'], len(group))])
    early = period(rows, 2015, 2018)
    late = period(rows, 2024, 2025)
    finance_early = sum(r['topic_code'] in ('T03', 'T04') for r in early)
    finance_late = sum(r['topic_code'] in ('T03', 'T04') for r in late)
    blocks = [
        Block("paragraph", f"คลังงานตรวจสอบข้อเท็จจริงจาก AFNC, ชัวร์ก่อนแชร์, Cofact, AFP Thailand และ Thai PBS Verify "
              f"ช่วยให้ย้อนดูเรื่องที่ผู้ตรวจสอบหยิบมาทำงานได้ตั้งแต่ พ.ศ. 2558 ถึง 2569 "
              f"ชุดที่ใช้ในบทความนี้มี {total:,} บันทึกหลังตัวกรองเบื้องต้นของโครงการ "
              "ผล audit เมื่อ 8 กันยายน 2569 ตรวจพบว่าฐานต้นทางของ snapshot นี้มี 29,001 บันทึก"),
        Block("paragraph", f"ตัวเลขที่ควรอ่านคู่กับขนาดคลังคือ {origins['human_not_claim']:,} บันทึกที่ผู้ตรวจระบุว่าไม่ใช่ข้ออ้าง "
              f"และ {verdicts['unknown']:,} บันทึกที่ยังไม่ทราบผล ทั้งสองกลุ่มอาจซ้อนกัน "
              "บทความฉบับนี้จึงใช้คำว่าบันทึกในคลัง และแสดงผลจริง/เท็จแยกกัน "
              "ชุดข้อมูลยังไม่ได้ผ่านการคัดให้เป็นข้ออ้างเดี่ยวที่ไม่ซ้ำและมีผลตรวจสอบครบทุกแถว"),
        Block("heading", "เรื่องการเงินปรากฏมากขึ้นในชุดที่ระบบจัดหมวดได้"),
        Block("paragraph", f"เมื่อใช้หมวดจาก CSV ชุดเดียวกันตลอดช่วง หมวดสินเชื่อ/คอลเซ็นเตอร์และหลอกลงทุนรวมกัน "
              f"มี {finance_early:,} จาก {len(early):,} บันทึกในปี 2558–2561 ({pct(finance_early, len(early))}) "
              f"เทียบกับ {finance_late:,} จาก {len(late):,} บันทึกในปี 2567–2568 ({pct(finance_late, len(late))}) "
              "ความต่างนี้เป็นข้อสังเกตจากงานที่ถูกเก็บและจัดหมวด ยังแยกไม่ได้ว่าเกิดจากการเปลี่ยนแปลงของข่าวลวง "
              "การเลือกเรื่องของผู้ตรวจสอบ หรือความครอบคลุมของแหล่งข้อมูลมากน้อยเพียงใด"),
        table("ตารางที่ 1: สัดส่วนหมวดในช่วงเวลาต่าง ๆ", ["ช่วงปี พ.ศ.", "บันทึกทั้งหมด", "สุขภาพ T01", "โควิด-19 T02", "การเงิน T03+T04"], timeline),
        Block("paragraph", "ช่วงเวลาในตารางกำหนดเพื่อให้อ่านเปรียบเทียบได้ และแยกปีล่าสุดที่ยังไม่ครบปีไว้ต่างหาก "
              "ยังไม่ได้ยืนยันว่าเป็นยุคหรือจุดเปลี่ยนที่ตรวจพบทางสถิติ ชื่อหมวดมาจากกฎคำค้น จึงอาจรวมเรื่องที่ถูกตรวจแล้วว่าเป็นจริงด้วย"),
        Block("heading", "ข้อมูลส่วนใหญ่ยังอยู่ในหมวดอื่น ๆ"),
        Block("paragraph", f"ระบบจัด {topics['T99']:,} จาก {total:,} บันทึกไว้ในหมวดอื่น ๆ ({pct(topics['T99'], total)}) "
              "ความไม่ครอบคลุมนี้ทำให้ต้องระวังการอธิบายทั้งคลังผ่านเพียงสิบหมวดที่ตั้งชื่อไว้ "
              "หมวดหนึ่งมีจำนวนน้อยอาจหมายถึงกฎคำค้นยังจับเนื้อหาไม่ได้ ไม่ได้ยืนยันว่าประเด็นนั้นพบได้น้อยในสังคม"),
        table("ตารางที่ 2: จำนวนบันทึกตามหมวดคำค้น — รวมหมวดอื่น ๆ", ["รหัสและหมวด", "บันทึก", "สัดส่วนทั้งชุด"],
              [[f"{key} — {names[key]}", f"{topics[key]:,}", pct(topics[key], total)] for key in sorted(topics)]),
        Block("paragraph", "ตารางนี้แทนภาพ Cluster เดิม ภาพเดิมกำหนดตำแหน่งและสุ่มจุดรอบศูนย์กลาง "
              "จึงไม่มีหลักฐานให้ตีความระยะห่าง พื้นที่กลุ่ม หรือเส้นเชื่อมเป็นความสัมพันธ์ทางความหมาย "
              "ฉบับแก้ไขถอดทั้งภาพสามมิติและภาพ Cluster ที่มีข้อความและตัวเลขไม่สอดคล้องออกจากบทความ"),
        Block("heading", "ผลตรวจสอบไม่ได้มีแต่ข่าวเท็จ"),
        table("ตารางที่ 3: ผลตรวจสอบที่บันทึกไว้", ["ผลตรวจสอบ", "บันทึก", "สัดส่วนทั้งชุด"],
              [[f"{label} ({key})", f"{verdicts[key]:,}", pct(verdicts[key], total)] for key, label in VERDICTS.items()]),
        Block("paragraph", "ป้ายเหล่านี้มีที่มาทั้งจากสำนักตรวจสอบ มนุษย์ และระบบอัตโนมัติ "
              "ตารางแสดงค่าที่เก็บไว้โดยไม่ได้ยกระดับป้ายจากระบบอัตโนมัติให้เป็นคำยืนยันของผู้ตรวจสอบ "
              "คำว่าเตือนภัยหลอกลวง สื่อดัดแปลง และยังไม่ทราบผล ถูกเก็บแยกจากบิดเบือน"),
        Block("heading", "ข้อสรุปที่ยังต้องใช้หลักฐานเพิ่ม"),
        Block("paragraph", "บทความนี้ยังไม่รับรองข้ออ้างเรื่องสามจุดเปลี่ยนทางสถิติ หรือการกลายพันธุ์ของวาทกรรม "
              "การวิเคราะห์เดิมใช้ตัวจัดหมวดต่างจาก CSV และวิธีทดสอบสถิติต้องทวนใหม่ "
              "จำนวนในคลังเพียงอย่างเดียวยังไม่พิสูจน์การจัดตั้งเครือข่ายอาชญากรรม เจตนาของผู้เผยแพร่ "
              "หรือผลกระทบที่เกิดกับผู้รับสาร"),
        Block("paragraph", "สิ่งที่คลังช่วยได้ในตอนนี้คือชี้รายการให้ผู้สื่อข่าวกลับไปอ่านผลตรวจสอบต้นฉบับ "
              "เพื่อแยกข้ออ้าง ผลตัดสิน และบริบท ก่อนสรุปแนวโน้มควรคัดรายการที่ไม่ใช่ข้ออ้าง ทวนข้อความซ้ำ "
              "และใช้ข้อความที่ผู้ตรวจแก้ไขไว้ให้ตรงกันทั้งระบบ"),
        *sources(1, rows),
    ]
    return "อ่านคลังตรวจสอบ 11 ปี: เรื่องที่ถูกตรวจเปลี่ยนไปอย่างไร", "ข้อสังเกตจากบันทึกปี 2558–2569 พร้อมข้อจำกัดของการจัดหมวด", blocks


def migrant(rows: list[dict]) -> tuple[str, str, list[Block]]:
    total = len(rows)
    frames = Counter(r["narrative_frame_id"] for r in rows)
    scoped = period(rows, 2020, 2026)
    verdicts = Counter(r["verdict"] for r in rows)
    origins = Counter(r["verdict_origin"] for r in rows)
    years = Counter(r["published_year"] for r in rows)
    frame_table = [[name, f"{frames[key]:,}", pct(frames[key], total)] for key, name in FRAMES.items()]
    temporal = []
    for first, last, key in [(2020, 2021, 'disease'), (2022, 2023, 'economic'), (2024, 2026, 'sovereignty')]:
        group = period(rows, first, last)
        count = sum(r['narrative_frame_id'] == key for r in group)
        label = f"{first + 543}–{last + 543}" + (" (ปี 2569 บางปี)" if last == 2026 else "")
        temporal.append([label, FRAMES[key], f"{count:,}/{len(group):,}", pct(count, len(group))])
    growth = ((years['2025'] / years['2024']) - 1) * 100 if years['2024'] else None
    growth_text = f"เพิ่ม {growth:.0f}%" if growth is not None else "ไม่มีฐานปีก่อนสำหรับคำนวณอัตราเพิ่ม"
    blocks = [
        Block("paragraph", "การศึกษาข่าวเกี่ยวกับประชากรข้ามชาติเริ่มจากคำถามว่า เรากำลังนับเรื่องของคนข้ามชาติ "
              "หรือเรื่องที่มีชื่อประเทศอยู่ในข้อความ คำถามนี้สำคัญต่อการตีความคลังที่มีทั้งข่าวแรงงาน "
              "เรื่องชายแดน เกาะกูด และเรื่องอื่นที่ใช้คำใกล้กัน"),
        Block("paragraph", f"ตัวกรองเดิมค้นได้ {total:,} บันทึก โดยใช้คำอย่างต่างด้าว พม่า กัมพูชา ลาว เวียดนาม "
              f"สัญชาติ และเกาะกูด ในจำนวนนี้อยู่ระหว่างปี 2563–2569 จำนวน {len(scoped):,} บันทึก "
              f"และอยู่นอกช่วงอีก {total - len(scoped):,} บันทึก "
              "ทุกตารางระบุฐานนับไว้ เพราะชุดที่ค้นได้ยังไม่ใช่ชุดข่าวลวงต่อต้านประชากรข้ามชาติที่ผ่านการทวนรายเรื่อง"),
        Block("heading", "ชื่อหมวดอธิปไตยไม่ควรรับรายการที่จัดกลุ่มไม่ได้"),
        Block("paragraph", f"ใน CSV กลุ่มสัญชาติ อธิปไตย และสิทธิการเมืองมี {frames['sovereignty']:,} บันทึก "
              f"ส่วนกลุ่มอื่น ๆ มี {frames['other']:,} บันทึก ({pct(frames['other'], total)}) "
              "ฉบับนี้คงกลุ่มอื่น ๆ แยกไว้ ภาพ Cluster เดิมถูกรวมรายการกลุ่มนี้เข้ากับอธิปไตย "
              "ทำให้สัดส่วนและภาพรวมผิดไป จึงถอดภาพดังกล่าวออกและใช้ตารางที่ตรวจย้อนกลับได้แทน"),
        table("ตารางที่ 1: ผลจัดกลุ่มด้วยคำค้นในชุดที่ค้นได้ทั้งหมด", ["กลุ่มคำค้น", "บันทึก", "สัดส่วนทั้งชุด"], frame_table),
        Block("paragraph", "กลุ่มคำค้นเป็นกฎที่ผู้พัฒนากำหนดไว้ ไม่ใช่กลุ่มที่ค้นพบโดยอัตโนมัติจาก semantic embeddings "
              "เรื่องที่ตรงหลายกลุ่มได้รับป้ายตามลำดับกฎ จึงต้องทวนความหมายก่อนใช้เป็นหลักฐานเกี่ยวกับวาทกรรม"),
        Block("heading", "ข้อมูลที่มีอยู่ยังไม่ยืนยันเส้นทางวาทกรรมสามยุค"),
        Block("paragraph", "เมื่อนับจากป้ายใน CSV เดียวกันและใช้บันทึกทั้งหมดในแต่ละช่วงเป็นตัวหาร "
              "สัดส่วนโรคระบาด เศรษฐกิจ และอธิปไตยแตกต่างจากที่ฉบับก่อนกล่าวไว้ "
              "ตารางต่อไปเลือกช่วงตามข้ออ้างเดิมเพื่อให้ตรวจสอบได้ ไม่ได้ยืนยันว่าช่วงเหล่านี้เป็นยุคที่ข้อมูลค้นพบ"),
        table("ตารางที่ 2: สัดส่วนกลุ่มคำค้นในช่วงที่ฉบับเดิมนำมาเปรียบเทียบ", ["ช่วงปี พ.ศ.", "กลุ่มคำค้น", "จำนวน/บันทึกทั้งช่วง", "สัดส่วน"], temporal),
        Block("paragraph", "การมีเนื้อหาเกี่ยวกับโควิด-19 อาชีพ หรือสัญชาติในต่างช่วงเวลา "
              "ยังไม่พิสูจน์ว่าข้อความเปลี่ยนจากกรอบหนึ่งไปสู่อีกกรอบหนึ่ง หรือมีผู้กำกับทิศทางร่วมกัน "
              "ฉบับแก้ไขจึงถอดภาพ 3D Trajectory ที่กำหนดเส้นทางไว้ล่วงหน้าออกด้วย"),
        Block("heading", "จำนวนเพิ่มขึ้น แต่ยังต้องแยกข่าวชายแดนออกจากข่าวแรงงาน"),
        Block("paragraph", f"ตัวกรองเดียวกันพบ {years['2024']:,} บันทึกในปี 2567 และ {years['2025']:,} ในปี 2568 "
              f"({growth_text}) ตัวเลขนี้นับบันทึกที่ผ่านคำค้นทุกผลตรวจสอบ ยังใช้ยืนยันว่าข่าวลวง "
              "ต่อต้านแรงงานเพิ่มในอัตราเดียวกันไม่ได้ และไม่ใช่การวัดยอดเผยแพร่หรือยอดแชร์"),
        table("ตารางที่ 3: บันทึกที่ผ่านตัวกรอง แยกปีเผยแพร่", ["ปี พ.ศ.", "บันทึก", "ขอบเขต"],
              [[str(int(year) + 543), f"{count:,}", "นอกช่วงศึกษา" if int(year) < 2020 else
                ("ข้อมูลยังไม่ครบปี" if year == '2026' else "ในช่วงศึกษา")]
               for year, count in sorted(years.items())]),
        Block("paragraph", "ตัวอย่างที่ต้องคัดออกจากการศึกษาแรงงานคือข้อความเรื่องผักชีลาวบรรเทากรดไหลย้อน "
              "และภาพถ่ายจานบินที่ลาว คำว่า ‘ลาว’ เพียงอย่างเดียวทำให้ผ่านตัวกรองได้ "
              "การพบสองตัวอย่างนี้ไม่ใช่ค่าประมาณความผิดพลาดของทั้งชุด แต่แสดงว่าต้องทวนรายการก่อนตีความ"),
        Block("links", "ตัวอย่างรายการที่ไม่ตรงขอบเขตแรงงาน", rows=(
            ("บันทึก 26174: เรื่องผักชีลาว", "https://www.youtube.com/watch?v=Va9Rg0K259A"),
            ("บันทึก 26615: เรื่องภาพถ่ายจานบินที่ลาว", "https://www.youtube.com/watch?v=aC89GaJ1z4U"),
        )),
        Block("heading", "แยกผลตรวจสอบ ก่อนเรียกรวมว่าข่าวลวง"),
        table("ตารางที่ 4: ผลตรวจสอบในชุดที่ค้นได้ทั้งหมด", ["ผลตรวจสอบ", "บันทึก", "สัดส่วนทั้งชุด"],
              [[f"{label} ({key})", f"{verdicts[key]:,}", pct(verdicts[key], total)] for key, label in VERDICTS.items()]),
        Block("paragraph", f"ชุดนี้รวม {verdicts['true']:,} บันทึกที่ป้ายผลเป็นจริง และ {verdicts['unknown']:,} บันทึกที่ยังไม่ทราบผล "
              f"นอกจากนี้มี {origins['human_not_claim']:,} บันทึกที่มนุษย์ระบุว่าไม่ใช่ข้ออ้าง "
              "ซึ่งซ้อนอยู่ในยอดผลตรวจสอบข้างต้น ไม่ใช่จำนวนที่ต้องบวกเพิ่ม "
              "ป้ายมีทั้งที่มาจากแหล่งข่าว มนุษย์ และระบบอัตโนมัติ จึงต้องอ่านที่มาของป้ายประกอบ"),
        Block("heading", "คำถามสำหรับการสืบค้นต่อ"),
        Block("paragraph", "การอธิบายผลกระทบต่อประชากรข้ามชาติต้องอ่านข้ออ้างและผลตรวจสอบต้นฉบับ "
              "แยกประเด็นสิทธิแรงงานออกจากความขัดแย้งระหว่างประเทศ และมีหลักฐานจากผู้ได้รับผลกระทบ "
              "บทความฉบับนี้ยังไม่อ้างว่ามีผลสำรวจภาคสนาม จำนวนเงินเสียหาย หรือหลักฐานการประสานงานของผู้เผยแพร่ "
              "ข้อสรุปเรื่องการสร้างความเกลียดชังและเจตนาทางการเมืองจึงยังต้องตรวจสอบเพิ่มเติม"),
        *sources(2, rows),
    ]
    return "ก่อนสรุปวาทกรรมประชากรข้ามชาติ: คลังตรวจสอบบอกอะไรได้บ้าง", "ทบทวนชุดคำค้นเกี่ยวกับแรงงานและข้ามแดน โดยแยกข้อมูลที่ยังจัดกลุ่มไม่ได้", blocks


def md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(title: str, subtitle: str, blocks: list[Block]) -> str:
    parts = [f"# {title}", subtitle, f"ชุดชิ้นงานสำหรับประชาไท • TH Verify\n\nปรับปรุง: {REVISION}",
             "> ฉบับแก้ไขหลัง audit — ข้อสังเกตจากข้อมูลที่มีข้อจำกัด ยังไม่รับรองผล discovered clustering หรือข้อสรุปเชิงเหตุและผล"]
    for block in blocks:
        if block.kind == "heading":
            parts.append("## " + block.title)
        elif block.kind == "paragraph":
            parts.append(block.title)
        elif block.kind == "table":
            parts.append("### " + block.title)
            lines = ["| " + " | ".join(map(md_cell, block.headers)) + " |",
                     "| " + " | ".join("---" for _ in block.headers) + " |"]
            lines.extend("| " + " | ".join(map(md_cell, row)) + " |" for row in block.rows)
            parts.append("\n".join(lines))
        elif block.kind == "links":
            parts.append("\n".join(f"- [{label}]({url})" for label, url in block.rows))
    return "\n\n".join(parts) + "\n"


EXTRA_CSS = """
.audited-feature { max-width: 980px; margin: auto; padding: 2rem 1.25rem; }
.audited-feature p { line-height: 1.85; overflow-wrap: anywhere; }
.audit-status { border-left: 4px solid var(--fnl-yellow); padding: 1rem; color: var(--fnl-white); }
.table-scroll { overflow-x: auto; margin: 1.5rem 0; }
.table-scroll table { min-width: 560px; }
caption { text-align: left; font-weight: 700; color: var(--fnl-white); margin-bottom: .8rem; }
.table-scroll:focus { outline: 2px solid var(--fnl-yellow); }
.source-list { overflow-wrap: anywhere; }
@media (max-width: 600px) {
  .audited-feature { padding: 1rem; }
  .audited-feature h1 { font-size: 1.75rem; }
}
@media print {
  .print-button { display: none; }
  .audited-feature { max-width: none; padding: 0; }
  .table-scroll { overflow: visible; }
  .table-scroll table { min-width: 0; table-layout: fixed; font-size: 9pt; }
  th, td { overflow-wrap: anywhere; padding: .35rem; }
  tr { break-inside: avoid; }
  h2, caption { break-after: avoid; }
}
"""


def render_html(title: str, subtitle: str, blocks: list[Block]) -> str:
    parts = ['<main class="audited-feature">', '<header>',
             '<p>ชุดชิ้นงานสำหรับประชาไท • TH Verify</p>',
             f'<h1>{escape(title)}</h1><p>{escape(subtitle)}</p>',
             f'<p>ปรับปรุง: {REVISION}</p>',
             '<p class="audit-status">ฉบับแก้ไขหลัง audit — ข้อสังเกตจากข้อมูลที่มีข้อจำกัด '
             'ยังไม่รับรองผล discovered clustering หรือข้อสรุปเชิงเหตุและผล</p>',
             '<button class="print-button" type="button" onclick="window.print()">พิมพ์ / บันทึก PDF</button>', '</header>']
    for block in blocks:
        if block.kind == "heading":
            parts.append(f"<h2>{escape(block.title)}</h2>")
        elif block.kind == "paragraph":
            parts.append(f"<p>{escape(block.title)}</p>")
        elif block.kind == "table":
            parts.append(f'<div class="table-scroll" role="region" aria-label="{escape(block.title, quote=True)}" tabindex="0"><table>')
            parts.append(f"<caption>{escape(block.title)}</caption><thead><tr>" +
                         ''.join(f'<th scope="col">{escape(cell)}</th>' for cell in block.headers) + '</tr></thead><tbody>')
            for row in block.rows:
                parts.append('<tr>' + ''.join(f'<td>{escape(cell)}</td>' for cell in row) + '</tr>')
            parts.append('</tbody></table></div>')
        elif block.kind == "links":
            parts.append('<ul class="source-list">' + ''.join(
                f'<li><a href="{escape(url, quote=True)}">{escape(label)}</a></li>' for label, url in block.rows) + '</ul>')
    parts.append('</main>')
    return document(escape(title), '\n'.join(parts), extra_css=EXTRA_CSS)


def build_feature(number: int, output: Path = REPORTS, datasets: Path = REPORTS / "datasets") -> tuple[Path, Path]:
    rows = load_rows(number, datasets)
    title, subtitle, blocks = (overview if number == 1 else migrant)(rows)
    digest = hashlib.sha256((datasets / DATASETS[number]).read_bytes()).hexdigest()
    blocks.append(Block("paragraph", f"รหัสตรวจสอบไฟล์ CSV (SHA-256): {digest}"))
    output.mkdir(parents=True, exist_ok=True)
    md_path, html_path = (output / f"{STEMS[number]}.{ext}" for ext in ("md", "html"))
    md_path.write_text(render_markdown(title, subtitle, blocks), encoding="utf-8")
    html_path.write_text(render_html(title, subtitle, blocks), encoding="utf-8")
    return md_path, html_path
