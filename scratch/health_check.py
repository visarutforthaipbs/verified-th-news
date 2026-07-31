import sqlite3
import os
import json
from pathlib import Path

db_path = Path("data/th_verify.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== 1. DATABASE METRICS & COVERAGE ===")
cursor.execute("SELECT COUNT(*) FROM fact_checks;")
total_fact_checks = cursor.fetchone()[0]
print(f"Total Fact Checks: {total_fact_checks:,}")

cursor.execute("""
    SELECT source, COUNT(*), 
           SUM(CASE WHEN verdict != 'unknown' THEN 1 ELSE 0 END),
           SUM(CASE WHEN verdict = 'unknown' THEN 1 ELSE 0 END),
           MIN(published_at), MAX(published_at), MAX(first_seen_at)
    FROM fact_checks 
    GROUP BY source;
""")
sources_summary = cursor.fetchall()
print("\nSource Breakdown:")
print(f"{'Source':<18} | {'Total':<7} | {'Labeled':<7} | {'Unknown':<7} | {'Oldest Pub':<10} | {'Newest Pub':<10} | {'Last Seen':<10}")
print("-" * 90)
for row in sources_summary:
    src, tot, lab, unk, min_p, max_p, max_s = row
    min_p_str = (min_p[:10] if min_p else 'N/A')
    max_p_str = (max_p[:10] if max_p else 'N/A')
    max_s_str = (max_s[:10] if max_s else 'N/A')
    print(f"{src:<18} | {tot:<7} | {lab:<7} | {unk:<7} | {min_p_str:<10} | {max_p_str:<10} | {max_s_str:<10}")

print("\n=== 2. VERDICT & QUALITY CHECKS ===")
cursor.execute("""
    SELECT verdict, COUNT(*) 
    FROM fact_checks 
    GROUP BY verdict 
    ORDER BY COUNT(*) DESC;
""")
verdict_dist = cursor.fetchall()
print("Verdict Distribution:")
for v, c in verdict_dist:
    pct = (c / total_fact_checks) * 100 if total_fact_checks else 0
    print(f"  - {v:<15}: {c:>6} ({pct:.1f}%)")

cursor.execute("SELECT COUNT(*) FROM fact_checks WHERE published_at IS NULL OR published_at = '';")
missing_pub = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM fact_checks WHERE title IS NULL OR title = '';")
missing_title = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM fact_checks WHERE claim IS NULL OR claim = '';")
missing_claim = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM fact_checks WHERE explanation IS NULL OR explanation = '';")
missing_exp = cursor.fetchone()[0]

print(f"\nData Quality Anomalies:")
print(f"  - Missing published_at: {missing_pub:,} ({missing_pub/total_fact_checks*100:.1f}%)")
print(f"  - Missing title       : {missing_title:,}")
print(f"  - Empty claim text    : {missing_claim:,} ({missing_claim/total_fact_checks*100:.1f}%)")
print(f"  - Empty explanation  : {missing_exp:,} ({missing_exp/total_fact_checks*100:.1f}%)")

print("\n=== 3. SYNC RUNS & SOURCE STATE ===")
cursor.execute("SELECT source, mode, last_success_at, records_seen, complete FROM source_state;")
states = cursor.fetchall()
print("Source State Table:")
for s in states:
    print(f"  - {s[0]} ({s[1]}): last_success={s[2]}, records_seen={s[3]}, complete={s[4]}")

cursor.execute("""
    SELECT source, mode, finished_at, status, records_seen, error 
    FROM sync_runs 
    ORDER BY id DESC 
    LIMIT 10;
""")
recent_syncs = cursor.fetchall()
print("\nRecent Sync Runs (last 10):")
for r in recent_syncs:
    err_str = f" | Err: {r[5]}" if r[5] else ""
    print(f"  - {r[0]} [{r[1]}] finished={r[2]} status={r[3]} records={r[4]}{err_str}")

print("\n=== 4. CLUSTERING & INDEX HEALTH ===")
cursor.execute("SELECT COUNT(*) FROM claim_clusters;")
num_clusters = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(DISTINCT fact_check_id) FROM claim_cluster_members;")
clustered_fc = cursor.fetchone()[0]
print(f"Total Clusters         : {num_clusters:,}")
print(f"Clustered Fact Checks  : {clustered_fc:,} / {total_fact_checks:,} ({clustered_fc/total_fact_checks*100:.1f}%)")

index_path = Path("data/index")
if index_path.exists():
    idx_files = list(index_path.glob("*"))
    print(f"Index directory contents: {[f.name for f in idx_files]}")
else:
    print("Index directory does NOT exist.")

exports_path = Path("data/exports")
if exports_path.exists():
    exp_files = list(exports_path.glob("*"))
    print(f"Exports directory contents: {[(f.name, f.stat().st_size) for f in exp_files]}")
else:
    print("Exports directory does NOT exist.")

conn.close()
