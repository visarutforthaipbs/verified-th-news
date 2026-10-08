#!/usr/bin/env python3
"""Story 2 review queue v2: close the recall gap found by the 2026-10-04 audit (finding F5).

The canonical queue (332 rows: 128 keyword seeds + 204 semantic neighbours) never
retrieved several whole storylines (Israelis "settling" in Thailand, Chinese
residents, schooling for Cambodian children, Myanmar entitlement claims). This adds
every unscreened corpus record that matches a documented keyword rule; nothing is
removed and round-1 decisions are untouched. A second semantic pass was tested and
rejected: neighbours of the in-scope set are dominated by the driving-licence template.

New rows get a provisional scope from the assistant reading title + claim only
(same basis as round 1). It is NOT a human judgement; coders stay blind to it.

Reads runs/20260908_bertopic_v001 (read-only). Writes runs/20261004_story2_queue_v002/.
"""
import collections, csv, hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'runs/20260908_bertopic_v001'
OUT = ROOT / 'runs/20261004_story2_queue_v002'
csv.field_size_limit(10 ** 9)
C = collections.Counter

# Rule A: a term that names people by status, origin or group.
PEOPLE = ('ต่างด้าว|แรงงานข้ามชาติ|คนข้ามชาติ|ชาวต่างชาติ|คนต่างชาติ|แรงงานต่างชาติ|เด็กต่างชาติ|ผู้ลี้ภัย|ลี้ภัย|ผู้อพยพ|ผู้หนีภัย|ผู้พลัดถิ่น|'
          'ไร้สัญชาติ|ไร้รัฐ|ไม่มีสัญชาติ|สัญชาติ|หลบหนีเข้าเมือง|ลักลอบเข้าเมือง|เข้าเมืองผิดกฎหมาย|แรงงานเถื่อน|แรงงานผิดกฎหมาย|ใบอนุญาตทำงาน|work permit|'
          'บัตรสีชมพู|บัตรชมพู|บัตรหัวศูนย์|ส่งกลับประเทศ|ผลักดันกลับ|โรฮิง|โรฮีน|กะเหรี่ยง|ไทใหญ่|ชาวเขา|ชนกลุ่มน้อย|ชาติพันธุ์|คนจีน|ชาวจีน|จีนเทา|ทุนจีน|นอมินี|'
          'ชาวกัมพูชา|คนกัมพูชา|ชาวเขมร|คนเขมร|แรงงานกัมพูชา|แรงงานเขมร|ชาวลาว|คนลาว|แรงงานลาว|ชาวเวียดนาม|คนเวียดนาม|ชาวเมียนมา|คนเมียนมา|ชาวพม่า|คนพม่า|'
          'แรงงานเมียนมา|แรงงานพม่า|ชาวอินเดีย|ชาวรัสเซีย|คนรัสเซีย|ชาวอิสราเอล|คนอิสราเอล|ชาวยิว')
# Rule B: a bare neighbouring-country name (how Thai posts usually refer to migrants) together with a people/service word.
BARE = 'พม่า|เมียนมา|เขมร|กัมพูชา|ลาว|เวียดนาม'
CO = ('คน|ชาว|แรงงาน|เด็ก|นักเรียน|ผู้ป่วย|รักษา|โรงพยาบาล|สิทธิ|บัตร|งาน|อาชีพ|ค่าแรง|เข้ามา|ทะลัก|ลักลอบ|ขอทาน|โรงเรียน|เรียน|คลอด|ประชากร|ภาษี|'
      'สวัสดิการ|บัตรทอง|เลือด|เงินช่วย|เยียวยา|หมู่บ้าน|ชุมชน|เช่า|ซื้อที่ดิน|ซื้อบ้าน')
NOT_LAO = 'ผักชีลาว|ศิลาว|เวลาว'   # dill, "ศิลาวิเศษ", "เวลาว่าง": the letters ล-า-ว inside other words

# Assistant's provisional scope for the new rows (title + claim only; codebook v1.1 definitions).
RESIDENTS = set('''16449 6609 6389 6337 27145 5180 4904 4851 17181 4811 4789 16856 4706 4571 4127 3690 3614 3537 3445
2382 2379 1266 1108 1099 629 513 505 480 391 315 27293 98 17 14'''.split())
CROSSBORDER = set('''17106 15147 3633 3327 2802 26807 27505 1117 1022 16722 544 27503 392 26687 292'''.split())
UNCLEAR = set('''16541 16531 16517 16444 16382 16353 16351 14485 13656 27475 10599 5026 4314 27495 1595 27414 1126
940 783 26721 27541'''.split())
IN = ('resident_refugee_status', 'crossborder_people_services')


def rd(p):
    with open(p, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def group_of(text):
    """String marker only (not coding): which group a claim names."""
    for name, pat in (('israel_jewish', 'อิสราเอล|ยิว'), ('china', 'จีน'), ('myanmar', 'พม่า|เมียนมา|โรฮิง|โรฮีน'),
                      ('cambodia', 'กัมพูชา|เขมร'), ('laos_vietnam', 'ลาว|เวียดนาม')):
        if re.search(pat, re.sub(NOT_LAO, '', text)):
            return name
    return 'generic_or_other'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    A = rd(RUN / 'assignments.csv'); old = rd(RUN / 'migrant_scope_decisions.csv'); q = {r['id'] for r in old}
    cols = list(old[0].keys()) + ['queue_round', 'v2_match_term']
    rows = [dict(r, queue_round='1', v2_match_term='') for r in old]
    new_ids = set()
    for r in A:
        if r['id'] in q:
            continue
        t = re.sub(NOT_LAO, '', (r['title'] or '') + ' ' + (r['claim_text'] or ''))
        m = re.search(PEOPLE, t, re.I)
        if m:
            route, term = 'keyword_v2_people', m.group(0)
        elif re.search(BARE, t) and re.search(CO, t):
            route, term = 'keyword_v2_nationality', re.search(BARE, t).group(0)
        else:
            continue
        scope = ('resident_refugee_status' if r['id'] in RESIDENTS else 'crossborder_people_services' if r['id'] in CROSSBORDER
                 else 'unclear' if r['id'] in UNCLEAR else 'out_of_scope')
        row = {c: r.get(c, '') for c in cols}
        row.update(retrieval_route=route, assistant_scope=scope, scope_basis='assistant read claim/title, not full-source verification (round 2, 2026-10-04)',
                   scope_evidence=r['title'], human_scope='', human_frame='', human_review_status='pending', queue_round='2', v2_match_term=term)
        rows.append(row); new_ids.add(r['id'])
    assert RESIDENTS | CROSSBORDER | UNCLEAR <= new_ids, sorted((RESIDENTS | CROSSBORDER | UNCLEAR) - new_ids)
    assert len({r['id'] for r in rows}) == len(rows)
    with open(OUT / 'review_queue_v2.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

    den = C(r['year'] for r in A)
    ins = [r for r in rows if r['assistant_scope'] in IN]
    txt = lambda r: (r['title'] or '') + ' ' + (r['claim_text'] or '')
    by_year = []
    for y in sorted(den):
        g = [r for r in ins if r['year'] == y]; g1 = [r for r in g if r['queue_round'] == '1']
        if not den[y]:
            continue
        by_year.append({'year': y, 'year_be': int(y) + 543, 'all_records': den[y], 'in_scope_round1': len(g1), 'in_scope_v2': len(g),
                        'share_round1_pct': round(len(g1) / den[y] * 100, 2), 'share_v2_pct': round(len(g) / den[y] * 100, 2),
                        **{f'group_{k}': v for k, v in sorted(C(group_of(txt(r)) for r in g).items())}})
    keys = sorted({k for r in by_year for k in r})
    lead = ['year', 'year_be', 'all_records', 'in_scope_round1', 'in_scope_v2', 'share_round1_pct', 'share_v2_pct']
    with open(OUT / 'assistant_in_scope_by_year.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=lead + [k for k in keys if k not in lead], restval=0); w.writeheader(); w.writerows(by_year)
    metrics = {
        'queue_rows': len(rows), 'round1_rows': len(old), 'round2_new_rows': len(new_ids),
        'round2_by_route': dict(C(r['retrieval_route'] for r in rows if r['queue_round'] == '2')),
        'assistant_scope_all': dict(C(r['assistant_scope'] for r in rows)),
        'assistant_scope_round2': dict(C(r['assistant_scope'] for r in rows if r['queue_round'] == '2')),
        'assistant_in_scope_v2': len(ins), 'assistant_in_scope_round1': sum(r['queue_round'] == '1' for r in ins),
        'in_scope_by_source': dict(C(r['source'] for r in ins)),
        'in_scope_by_group_marker': dict(C(group_of(txt(r)) for r in ins)),
        'in_scope_round2_by_group_marker': dict(C(group_of(txt(r)) for r in ins if r['queue_round'] == '2')),
        'status': 'assistant-screened from title + claim; no human review; group marker is string matching, not coding',
    }
    manifest = {'run': OUT.name, 'script': 'scripts/story2_extend_queue.py', 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'inputs_sha256': {n: hashlib.sha256((RUN / n).read_bytes()).hexdigest() for n in ('assignments.csv', 'migrant_scope_decisions.csv')},
                'rules': {'A_people_terms': PEOPLE, 'B_bare_nationality': BARE, 'B_requires_one_of': CO, 'excluded_substrings': NOT_LAO,
                          'searched_fields': 'title + claim_text', 'rejected': 'second semantic expansion (dominated by driving-licence template)'},
                'metrics': metrics}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
