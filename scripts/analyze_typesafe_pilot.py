#!/usr/bin/env python3
"""Audit TypeSafe pilot outputs against assistant labels without calling them truth."""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "runs/20260921_typesafe_pilot_v001"
RESULTS = PILOT / "pilot_results.csv"
IN_SCOPE = {"resident_refugee_status", "crossborder_people_services"}
CLASSES = (
    "resident_refugee_status",
    "crossborder_people_services",
    "out_of_scope",
    "unclear",
)


def read_rows() -> list[dict[str, str]]:
    with RESULTS.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = read_rows()
    exact = [row for row in rows if row["assistant_scope"] == row["typesafe_scope"]]
    disagreements = [row for row in rows if row["assistant_scope"] != row["typesafe_scope"]]
    binary_agreement = [
        row for row in rows if (row["assistant_scope"] in IN_SCOPE) == (row["typesafe_scope"] in IN_SCOPE)
    ]

    tp = sum(row["assistant_scope"] in IN_SCOPE and row["typesafe_scope"] in IN_SCOPE for row in rows)
    tn = sum(row["assistant_scope"] not in IN_SCOPE and row["typesafe_scope"] not in IN_SCOPE for row in rows)
    fp = sum(row["assistant_scope"] not in IN_SCOPE and row["typesafe_scope"] in IN_SCOPE for row in rows)
    fn = sum(row["assistant_scope"] in IN_SCOPE and row["typesafe_scope"] not in IN_SCOPE for row in rows)

    confusion = {
        assistant: {predicted: 0 for predicted in CLASSES}
        for assistant in CLASSES
    }
    for row in rows:
        confusion[row["assistant_scope"]][row["typesafe_scope"]] += 1

    duplicated_texts: list[dict[str, object]] = []
    by_text: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_text[row["claim_text"]].append(row)
    for text, group in by_text.items():
        if len(group) > 1:
            duplicated_texts.append(
                {
                    "claim_text": text,
                    "ids": [row["id"] for row in group],
                    "typesafe_scopes": [row["typesafe_scope"] for row in group],
                    "scope_confidences": [float(row["typesafe_scope_confidence"]) for row in group],
                    "in_scope_probabilities": [float(row["typesafe_in_scope_probability"]) for row in group],
                }
            )

    reason_counts = Counter(
        reason
        for row in rows
        for reason in row["typesafe_review_reasons"].split(";")
        if reason
    )
    issue_counts = Counter(row["typesafe_primary_issue"] for row in rows)
    clarity_counts = Counter(row["typesafe_evidence_clarity"] for row in rows)
    priority_counts = Counter(row["typesafe_review_priority"] for row in rows)
    predicted_counts = Counter(row["typesafe_scope"] for row in rows)
    input_tokens = sum(int(row["typesafe_input_tokens"]) for row in rows)
    output_tokens = sum(int(row["typesafe_output_tokens"]) for row in rows)

    metrics = {
        "status": "assistant-reference audit; no human gold labels",
        "records": len(rows),
        "model_versions": sorted({row["typesafe_model"] for row in rows}),
        "question_set_versions": sorted({row["typesafe_question_set_version"] for row in rows}),
        "exact_scope_agreement": len(exact),
        "exact_scope_agreement_pct": pct(len(exact), len(rows)),
        "binary_in_scope_agreement": len(binary_agreement),
        "binary_in_scope_agreement_pct": pct(len(binary_agreement), len(rows)),
        "binary_reference_counts": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "binary_reference_precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "binary_reference_recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "binary_reference_f1": round(2 * tp / (2 * tp + fp + fn), 4) if 2 * tp + fp + fn else None,
        "mean_scope_confidence_on_agreement": round(
            statistics.mean(float(row["typesafe_scope_confidence"]) for row in exact), 4
        ),
        "mean_scope_confidence_on_disagreement": round(
            statistics.mean(float(row["typesafe_scope_confidence"]) for row in disagreements), 4
        ),
        "confusion_assistant_rows_typesafe_columns": confusion,
        "typesafe_scope_counts": dict(predicted_counts),
        "review_priority_counts": dict(priority_counts),
        "review_reasons": dict(reason_counts),
        "evidence_clarity_counts": dict(clarity_counts),
        "primary_issue_counts": dict(issue_counts),
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "duplicate_text_checks": duplicated_texts,
        "limitations": [
            "assistant_scope is a prior machine-assisted screen, not ground truth",
            "n=24 is too small for stable performance estimates",
            "the sample is stratified and is not prevalence-representative",
            "Jev documentation says English is its strongest language; this state is Thai",
            "narrative frames have no human gold labels in this pilot",
        ],
    }
    (PILOT / "pilot_evaluation_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    disagreement_fields = [
        "id", "year", "source", "claim_text", "title", "url", "assistant_scope",
        "typesafe_scope", "typesafe_scope_confidence", "typesafe_scope_probabilities",
        "typesafe_in_scope_probability", "typesafe_primary_issue",
        "typesafe_review_reasons", "human_scope", "human_frame", "human_review_status",
    ]
    write_csv(
        PILOT / "pilot_scope_disagreements.csv",
        [{field: row[field] for field in disagreement_fields} for row in disagreements],
    )

    cost = input_tokens / 1_000_000 * 0.042
    report = f"""# ผลประเมิน TypeSafe pilot สำหรับ Story 2

## ข้อสรุป

ผลรอบ 24 รายการแสดงว่า Jev มีประโยชน์ในฐานะ **ตัวช่วยคัดกรองและชี้คิวตรวจ** แต่ยังไม่ควรใช้แทนนักข่าวหรือใช้คำนวณแนวโน้ม narrative โดยตรง

- ตรงกับ `assistant_scope` แบบ 4 กลุ่ม: **{len(exact)}/24 ({pct(len(exact), 24)}%)**
- ตรงกันเมื่อยุบเหลือ “เข้า/ไม่เข้าเรื่อง”: **{len(binary_agreement)}/24 ({pct(len(binary_agreement), 24)}%)**
- ถ้าใช้ป้ายเดิมเป็นเพียง reference: precision = **{tp/(tp+fp):.1%}**, recall = **{tp/(tp+fn):.1%}**, F1 = **{2*tp/(2*tp+fp+fn):.1%}**
- รายการที่ถูกส่งเข้าคิวตรวจเร่งด่วน: **{priority_counts['high']}/24 ({pct(priority_counts['high'], 24)}%)**
- รายการที่อาจผ่านคิวปกติ: **{priority_counts['normal']}/24 ({pct(priority_counts['normal'], 24)}%)**

ตัวเลขเหล่านี้เป็น **agreement กับการคัดของผู้ช่วยเดิม ไม่ใช่ accuracy** เพราะทั้งสองฝั่งยังไม่ได้ผ่าน human gold labels

## สิ่งที่ทำได้ดี

1. รักษารายการที่เดิมคัดเข้าเรื่องไว้ 11 จาก 12 รายการ (reference recall 91.7%) เหมาะกับงานค้นข่าวที่ยอมรับ false positive ได้มากกว่าการพลาดข่าวสำคัญ
2. ความมั่นใจเฉลี่ยเมื่อสองระบบเห็นตรงกันอยู่ที่ **{metrics['mean_scope_confidence_on_agreement']:.2f}** เทียบกับ **{metrics['mean_scope_confidence_on_disagreement']:.2f}** เมื่อเห็นต่าง จึงมีสัญญาณสำหรับเรียงคิวตรวจ
3. รุ่นจริงที่ตอบคือ `jev-1.13.0` และมีการเก็บ probability, raw response และ fingerprint ของคำถามครบ
4. ใช้ input {input_tokens:,} tokens; ตามราคาเอกสารสาธารณะ $0.042 ต่อหนึ่งล้าน input tokens คิดเป็นประมาณ **${cost:.4f}** สำหรับ pilot นี้ (ไม่รวมเงื่อนไขบัญชีหรือราคาที่อาจเปลี่ยน)

## จุดที่ยังไม่ผ่าน

1. **คลาส `unclear` ไม่ถูกเลือกเลย:** ทั้ง 6 รายการที่ระบบเดิมระบุว่าไม่ชัด ถูก Jev บังคับไปยังคลาสอื่น แปลว่า taxonomy ปัจจุบันยังไม่ทำให้ “หลักฐานไม่พอ” เป็นทางออกที่ใช้งานได้
2. **คำถาม evidence clarity ไม่มีพลังแยก:** Jev ตอบ `explicit` ครบ 24/24 แม้หลายรายการมีความกำกวมด้านตัวตนหรือบริบท
3. **มี self-consistency warning:** ข้ออ้างเดียวกันเรื่อง “ออกบัตรประชาชนให้มุสลิม” ปรากฏสองระเบียนและได้ผู้ชนะคนละคลาส (`out_of_scope` กับ `resident_refugee_status`) แม้ Choice confidence ต่ำทั้งคู่ 0.33/0.30 และ Noul อยู่ในขอบเขตต่ำใกล้กัน 0.17/0.15 กรณีนี้ยืนยันว่าควรใช้ probability และส่งให้คนตัดสิน ไม่ควรใช้ชื่อคลาสผู้ชนะลำพัง
4. **กรอบ narrative ยังไม่มี gold labels:** สัญญาณหลายกรอบต่ำมาก แม้ข้อความบางรายการดูเหมือนมีการวางกรอบชัดในทางภาษา จึงยังห้ามนำจำนวนกรอบไปสร้าง timeline
5. ตัวอย่างนี้แบ่งชั้น 6/6/6/6 เพื่อทดสอบระบบ ไม่ใช่ตัวแทนสัดส่วนจริงของ 332 ระเบียน

## ความเห็นต่างที่ต้องให้นักข่าวตัดสิน

มีทั้งหมด **{len(disagreements)} รายการ** อยู่ใน `pilot_scope_disagreements.csv` โดยจุดสำคัญคือ:

- 1 รายการเดิมเป็น `out_of_scope` แต่ Jev คัดเข้าเรื่อง
- 2 รายการเดิมเป็น `crossborder_people_services` แต่ Jev เปลี่ยนคลาส โดยหนึ่งรายการยังอยู่ในขอบเขตและอีกหนึ่งรายการถูกคัดออก
- 6 รายการเดิมเป็น `unclear`; Jev คัดเข้า 4 และคัดออก 2

กลุ่ม `unclear` จึงควรเป็นชุดแรกที่นักข่าวอ่านต้นทาง เพราะจะบอกได้ว่า Jev ช่วยค้นคืนรายการที่ระบบเดิมลังเล หรือเพียงสร้าง false positives

## แบบจำลอง v2 ที่แนะนำ

ยังไม่ควรรันครบ 332 รายการด้วยคำถามชุดเดิม ให้ลงรหัส pilot นี้แบบ blind ก่อน แล้วเปลี่ยนการตัดสิน scope จาก Choice ใหญ่หนึ่งข้อเป็น Noul แยกองค์ประกอบ:

1. ข้อความระบุชัดหรือไม่ว่าบุคคลเป็นแรงงานข้ามชาติ ผู้ลี้ภัย คนไร้รัฐ หรือผู้พำนักต่างชาติ
2. เหตุการณ์เกี่ยวข้องกับประเทศไทยอย่างมีนัยสำคัญหรือไม่
3. มีการข้ามแดน/เข้าออกประเทศ/บริการชายแดนหรือไม่
4. มีประเด็นสิทธิ สถานะ งาน สุขภาพ การศึกษา หรือสวัสดิการของคนกลุ่มนั้นหรือไม่
5. หลักฐานจาก title/claim เพียงพอหรือจำเป็นต้องเปิดต้นทาง

จากนั้นให้โค้ดประกอบเป็น `resident_refugee_status`, `crossborder_people_services`, `out_of_scope` หรือ `human_review` โดยเก็บ Choice เดิมไว้เป็น diagnostic เท่านั้น วิธีนี้ทำให้เห็นว่าความผิดพลาดเกิดจาก “ไม่รู้ว่าเป็นใคร”, “ไม่มีบริบทไทย” หรือ “แยก resident/cross-border ไม่ได้”

## เกณฑ์ก่อนขยายผล

- นักข่าวสองคนลงรหัส 24 รายการโดยไม่เห็นคำตอบ Jev และแก้ข้อขัดแย้งร่วมกัน
- วัด precision/recall สำหรับ binary scope และราย frame พร้อมช่วงความไม่แน่นอน
- รันซ้ำอย่างน้อย 3 ครั้งกับชุดเดิมเพื่อตรวจความคงที่ของ probability
- เปรียบเทียบ question set v1 กับ v2 บน gold set เดียวกัน
- ขยายเป็น 332 รายการต่อเมื่อ recall ผ่านเกณฑ์ที่กองบรรณาธิการกำหนด และทบทวน model/version ใหม่ทุกครั้ง
"""
    (PILOT / "PILOT_EVALUATION_TH.md").write_text(report, encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
