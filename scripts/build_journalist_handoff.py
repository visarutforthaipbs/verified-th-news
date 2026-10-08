#!/usr/bin/env python3
"""Read-only, reproducible datasets for the two Thai journalistic outlines.

No database writes, verdict inference, discovered clustering or significance
claims. Outputs are derived snapshots; existing deliverables stay untouched.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from th_verify.normalized import (
    HIGH_PRECISION_TOPIC_RULES, clean_claim_text, dedup_key, is_factcheck, normalize_verdict,
)

OUT = ROOT / "data/reports/journalist_handoff_2026-09-08"
DB = ROOT / "data/th_verify.db"
BAD = {"false", "misleading", "altered_media"}
TRUST = {"human", "source"}
MIGRANT = re.compile(
    r"ต่างด้าว|แรงงานข้ามชาติ|ประชากรข้ามชาติ|แรงงานต่างชาติ|แรงงาน(?:พม่า|เมียนมา|กัมพูชา|ลาว|เวียดนาม)|"
    r"ผู้ลี้ภัย|โรฮิงญา|ไร้สัญชาติ|ไร้รัฐ|ชนกลุ่มน้อย|แจกสัญชาติ|สัญชาติไทย|"
    r"บุคคลไม่มีสถานะ|บุคคลที่ไม่มีสถานะ|แย่งอาชีพ|แย่งงาน|คนเข้าเมือง|หลบหนีเข้าเมือง", re.I
)
BORDER = re.compile(r"เกาะกูด|mou\s*44|ชายแดน|ทหารกัมพูชา|กองทัพกัมพูชา|ปะทะ.*กัมพูชา", re.I)
EXPANDED = re.compile(r"ชาว(?:เมียนมา|พม่า|กัมพูชา|ลาว|เวียดนาม)|คน(?:เมียนมา|พม่า|กัมพูชา|ลาว)|แรงงานเขมร|กลุ่มชาติพันธุ์", re.I)
FRAMES = {
    "health": ("โรคและสุขภาพ", r"โควิด|โรค|ติดเชื้อ|วัคซีน|โรงพยาบาล|รพ\.|สาธารณสุข"),
    "jobs": ("งานและอาชีพ", r"แย่งงาน|แย่งอาชีพ|ทำงาน|อาชีพ|ค้าขาย|ขายของ|นอมินี|ใบอนุญาต|จ้างงาน|ทำธุรกิจ|ประกอบธุรกิจ"),
    "rights": ("สถานะ สิทธิ และสวัสดิการ", r"สัญชาติ|บัตรประชาชน|เลือกตั้ง|สิทธิ|สวัสดิการ|รักษาฟรี|ประกันสังคม|เงินช่วยเหลือ|เงินเยียวยา"),
    "security": ("การเข้าเมือง อาชญากรรม และความมั่นคง", r"ลักลอบ|หลบหนี|หนีเข้าเมือง|ยาเสพติด|ก่อเหตุ|อาชญากรรม|ทำร้าย|ฆ่า|โจร|ปล้น|ค้ามนุษย์|นายหน้า|ส่งกลับ|ผลักดัน|ขับไล่|ก่อการร้าย"),
}
DIGEST = re.compile(r"ข่าวเด่นประจำสัปดาห์|สรุปข่าวปลอมประจำ|รวมข่าวปลอมประจำ")


def write_csv(name, rows, fields=None):
    path = OUT / name
    if fields is None:
        fields = list(rows[0]) if rows else ["empty"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def hash_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    # Do not erase a journalist's subsequent coding on rebuild.
    for name in ('07_migrant_candidates_review.csv','10_expanded_migrant_review.csv'):
        existing = OUT/name
        if existing.exists():
            with existing.open(encoding='utf-8-sig',newline='') as stream:
                if any(any(r.get(k,'') for k in ('reviewed_scope','reviewed_frames','journalist_note'))
                       or r.get('review_status') != 'pending_editorial_review' for r in csv.DictReader(stream)):
                    raise RuntimeError(f'Preserving editorial review: {existing}. Archive the reviewed copy before rebuilding.')
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    source_rows = conn.execute("SELECT * FROM fact_checks ORDER BY published_at, id").fetchall()
    conn.close()
    excluded = []
    accepted = []
    for r in source_rows:
        reason = None
        if not is_factcheck(r['source'], r['title'], r['verdict'], r['explanation'], r['verdict_origin']) or DIGEST.search(r['title']):
            reason = "nonclaim_or_digest"
        elif r['verdict_origin'] not in TRUST:
            reason = "verdict_not_source_or_human"
        label = normalize_verdict(r['source'], r['verdict'])
        if not reason and label not in BAD | {"true"}:
            reason = "verdict_outside_comparison"
        date = (r['published_at'] or '')[:10]
        if not reason and (not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", date) or not '2015-01-01' <= date <= '2026-09-02'):
            reason = "outside_snapshot_window_or_missing_date"
        if r['claim_origin'] in ('source', 'human', 'llm') and r['claim'].strip():
            text, basis = r['claim'].strip(), r['claim_origin']
        else:
            text, basis = clean_claim_text(r['title'], r['source']), 'cleaned_title'
        if not reason and len(text) < 10:
            reason = "short_text"
        if reason:
            excluded.append({'id':r['id'], 'source':r['source'], 'reason':reason})
            continue
        topics = [tid for tid, _, _, rx in HIGH_PRECISION_TOPIC_RULES if rx.search(text)]
        frames = [key for key, (_, pattern) in FRAMES.items() if re.search(pattern, text, re.I)]
        accepted.append({
            'id':r['id'], 'source':r['source'], 'date':date, 'year':int(date[:4]),
            'verdict':label, 'verdict_origin':r['verdict_origin'], 'claim_text':text,
            'claim_text_basis':basis, 'title':r['title'], 'url':r['source_url'],
            'topic_flags':';'.join(topics) or 'other',
            'migrant_match':bool(MIGRANT.search(text)),
            'border_match':bool(BORDER.search(text)),
            'frame_flags':';'.join(frames) or 'other',
            'text_family':hashlib.sha256(dedup_key(text).encode()).hexdigest()[:20],
        })
    main = [r for r in accepted if r['verdict'] in BAD]
    write_csv('01_checked_records.csv', accepted)
    write_csv('02_false_misleading_altered_records.csv', main)
    write_csv('03_exclusions.csv', excluded)
    year_rows = []
    for year in range(2015, 2027):
        group = [r for r in accepted if r['year'] == year]
        counts = Counter(r['verdict'] for r in group)
        year_rows.append({'year':year, 'year_be':year+543, 'checked_records':len(group),
            'false':counts['false'], 'misleading':counts['misleading'],
            'altered_media':counts['altered_media'], 'true':counts['true'],
            'main_records':sum(counts[v] for v in BAD), 'partial_year':year==2026})
    write_csv('04_year_counts.csv', year_rows)
    source_year = []
    for source in sorted({r['source'] for r in accepted}):
        for year in range(2015, 2027):
            group = [r for r in main if r['year']==year and r['source']==source]
            source_year.append({'source':source, 'year':year, 'main_records':len(group),
                'source_verdicts':sum(r['verdict_origin']=='source' for r in group),
                'human_verdicts':sum(r['verdict_origin']=='human' for r in group)})
    write_csv('05_publisher_year_counts.csv', source_year)
    topic_year = []
    for year in range(2015, 2027):
        for source in ['all', *sorted({r['source'] for r in main})]:
            group = [r for r in main if r['year']==year and (source=='all' or r['source']==source)]
            for key, name, _, _ in HIGH_PRECISION_TOPIC_RULES:
                count = sum(key in r['topic_flags'].split(';') for r in group)
                topic_year.append({'year':year, 'source':source, 'topic':key, 'topic_label':name,
                    'matches':count, 'denominator':len(group),
                    'share_pct':round(count/len(group)*100,3) if group else '',
                    'multi_label':True})
            count = sum(r['topic_flags']=='other' for r in group)
            topic_year.append({'year':year, 'source':source, 'topic':'other', 'topic_label':'ไม่มีคำตรงกฎหัวข้อ',
                'matches':count,'denominator':len(group),'share_pct':round(count/len(group)*100,3) if group else '', 'multi_label':True})
    write_csv('06_topic_year_by_publisher.csv', topic_year)
    migrant = [dict(r, review_status='pending_editorial_review', reviewed_scope='', reviewed_frames='', journalist_note='')
               for r in main if r['migrant_match']]
    border = [r for r in main if r['border_match'] and not r['migrant_match']]
    write_csv('07_migrant_candidates_review.csv', migrant)
    write_csv('08_border_only_excluded_from_migrant.csv', border, fields=list(main[0]))
    frame_year = []
    for year in range(2015, 2027):
        group = [r for r in migrant if r['year']==year]
        for key in [*FRAMES, 'other']:
            count = sum(key in r['frame_flags'].split(';') for r in group)
            frame_year.append({'year':year,'frame':key,'candidate_matches':count,
                'candidate_denominator':len(group), 'share_pct':round(count/len(group)*100,3) if group else '',
                'status':'keyword_candidate_not_validated_narrative','multi_label':True})
    write_csv('09_candidate_frame_year.csv', frame_year)
    expanded = [dict(r, match_route='explicit_migrant' if r['migrant_match'] else 'demonym_expansion',
                     review_status='pending_editorial_review', reviewed_scope='', reviewed_frames='',
                     journalist_note='') for r in main if r['migrant_match'] or EXPANDED.search(r['claim_text'])]
    write_csv('10_expanded_migrant_review.csv', expanded)
    period_rows = []
    for label, start, end in [('2020-2021',2020,2021),('2024-2025',2024,2025)]:
        for source in ['all', *sorted({r['source'] for r in main})]:
            group = [r for r in main if start <= r['year'] <= end and (source=='all' or r['source']==source)]
            collapsed = list({(r['source'],r['year'],r['text_family']):r for r in group}.values())
            for method, sample in [('publisher_records',group),('same_source_year_text_dedup',collapsed),
                                   ('false_only',[r for r in group if r['verdict']=='false'])]:
                for key,name,_,_ in HIGH_PRECISION_TOPIC_RULES:
                    count = sum(key in r['topic_flags'].split(';') for r in sample)
                    period_rows.append({'period':label,'source':source,'method':method,'topic':key,
                        'topic_label':name,'matches':count,'denominator':len(sample),
                        'share_pct':round(count/len(sample)*100,3) if sample else ''})
    write_csv('11_period_sensitivity.csv', period_rows)
    cases = {
        26643: ('story1','สูตรสุขภาพยุคต้น','snapshot_only'),
        5292: ('story1','แอบอ้างการลงทุน','snapshot_text_checked_live_recheck_needed'),
        15735: ('both','คำกล่าวอ้างโรคติดเชื้อ; ต้องอ่านชื่อข่าวเต็มเพราะข้อความสกัดถูกตัด','snapshot_text_checked_live_recheck_needed'),
        15731: ('both','ภาพย้ายถิ่นเชื่อมโยงโควิด','snapshot_text_checked_live_recheck_needed'),
        15406: ('story2','ปลดล็อก 5 อาชีพ รุ่นปี 2021','snapshot_text_checked_live_recheck_needed'),
        13929: ('story2','ข้ออ้าง 5 อาชีพกลับมาปี 2022','snapshot_only'),
        13177: ('story2','ข้ออ้าง 5 อาชีพอีกครั้งปี 2022','snapshot_only'),
        7940: ('story2','ข้ออ้าง 5 อาชีพกลับมาปี 2024','snapshot_only'),
        27645: ('story2','บัตรสีชมพูถูกโยงเป็นสิทธิสัญชาติ','live_source_read_2026-09-08'),
        6278: ('story2','ตัวเลขแรงงานถูกโยงกับการว่างงาน','snapshot_only'),
        5366: ('story2','ข้ออ้างประกันสังคมเอื้อแรงงานข้ามชาติ','snapshot_text_checked_live_recheck_needed'),
        16862: ('both','ภาพเก่าถูกอ้างว่าชุมนุมขอค่าแรง 700','live_source_read_2026-09-08'),
        17289: ('story2','อีกบันทึกในข้ออ้างค่าแรง 700; ไม่ใช่เหตุการณ์ใหม่โดยอัตโนมัติ','snapshot_only'),
        27076: ('story2','สำนักที่สองตรวจภาพเก่าในข้ออ้างค่าแรง 700','live_page_checked_2026-09-08'),
        27584: ('story2','สิทธิการศึกษาและบริบทคลิปชายแดนเก่า','live_page_checked_2026-09-08'),
        28118: ('story2','ข้ออ้างเรื่องสัญชาติในปี 2026','snapshot_only'),
        28176: ('both','ภาพห้องคลอดสังเคราะห์กับข้ออ้างเรื่องประชากร','live_source_read_2026-09-08'),
    }
    case_rows = []
    lookup = {r['id']:r for r in main}
    for record_id,(story,use,status) in cases.items():
        assert record_id in lookup, record_id
        case_rows.append(dict(lookup[record_id], intended_story=story, reporting_use=use,
                              source_check_status=status, final_editorial_verification='pending'))
    write_csv('12_selected_cases.csv',case_rows)
    assert len(accepted)+len(excluded)==len(source_rows)
    assert sum(r['main_records'] for r in year_rows)==len(main)
    assert len({r['id'] for r in accepted})==len(accepted)
    assert all(r['verdict_origin'] in TRUST and r['verdict'] in BAD for r in main)
    assert {r['id'] for r in migrant} <= {r['id'] for r in expanded}
    manifest = {
        'snapshot_cutoff':'2026-09-02', 'raw_records':len(source_rows),
        'accepted_comparison_records':len(accepted), 'main_records':len(main),
        'main_verdicts':dict(Counter(r['verdict'] for r in main)),
        'main_origins':dict(Counter(r['verdict_origin'] for r in main)),
        'main_sources':dict(Counter(r['source'] for r in main)),
        'claim_text_basis':dict(Counter(r['claim_text_basis'] for r in main)),
        'exclusions':dict(Counter(r['reason'] for r in excluded)),
        'main_exact_text_families':len({r['text_family'] for r in main}),
        'migrant_candidates':len(migrant), 'migrant_years':dict(Counter(r['year'] for r in migrant)),
        'expanded_migrant_candidates':len(expanded),
        'expanded_migrant_regex':EXPANDED.pattern,
        'migrant_frames':dict(Counter(k for r in migrant for k in r['frame_flags'].split(';'))),
        'border_only_records':len(border),
        'topic_method':'multi_label_regex_on_provenance_aware_claim_text; not discovered clustering',
        'migrant_regex':MIGRANT.pattern, 'frame_rules':FRAMES,
        'topic_rules':{key:rx.pattern for key,_,_,rx in HIGH_PRECISION_TOPIC_RULES},
        'unit':'publisher fact-check record, not unique hoax or social-media reach',
        'script_sha256':hash_file(Path(__file__)),
        'normalization_sha256':hash_file(ROOT/'src/th_verify/normalized.py'),
        'input_rows_sha256':hashlib.sha256(json.dumps([dict(r) for r in source_rows],ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest(),
        'csv_sha256':{p.name:hash_file(p) for p in sorted(OUT.glob('*.csv'))},
    }
    (OUT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    prepare()
