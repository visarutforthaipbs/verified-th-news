import sqlite3
from pathlib import Path
from .db import Repository
from .models import utc_now

def get_trigrams(text: str) -> set[str]:
    if not text:
        return set()
    text = "".join(text.split()).lower()
    return {text[i:i+3] for i in range(len(text) - 2)}

def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    if not set1 or not set2:
        return 0.0
    return len(set1.intersection(set2)) / len(set1.union(set2))

def run_clustering(db_path: Path, similarity_threshold: float = 0.70, window_size: int = 12) -> dict[str, int]:
    repo = Repository(db_path)
    repo.initialize()
    
    with repo.connect() as conn:
        rows = conn.execute("SELECT id, title FROM fact_checks").fetchall()
        
    if not rows:
        return {"clusters_created": 0, "members_linked": 0}
        
    records = []
    for r in rows:
        records.append({
            "id": r["id"],
            "title": r["title"],
            "trigrams": get_trigrams(r["title"])
        })
        
    # Sort alphabetically by title
    records.sort(key=lambda x: x["title"])
    
    n = len(records)
    parent = list(range(n))
    
    def find(i):
        path = []
        while parent[i] != i:
            path.append(i)
            i = parent[i]
        for node in path:
            parent[node] = i
        return i
        
    def union_nodes(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    # Comparison loop (Sorted Neighborhood Method)
    for i in range(n):
        for w in range(1, window_size + 1):
            j = i + w
            if j >= n:
                break
            len_i = len(records[i]["title"])
            len_j = len(records[j]["title"])
            if min(len_i, len_j) / max(len_i, len_j) < 0.60:
                continue
            sim = jaccard_similarity(records[i]["trigrams"], records[j]["trigrams"])
            if sim >= similarity_threshold:
                union_nodes(i, j)
                
    # Group by clusters
    clusters = {}
    for idx in range(n):
        root = find(idx)
        if root not in clusters:
            clusters[root] = []
        clusters[root].append(records[idx]["id"])
        
    now = utc_now()
    clusters_created = 0
    members_linked = 0
    
    with repo.connect() as conn:
        # Clear existing clusters for a fresh rebuild
        conn.execute("DELETE FROM claim_cluster_members")
        conn.execute("DELETE FROM claim_clusters")
        
        for root_idx, member_ids in clusters.items():
            rep_title = records[root_idx]["title"]
            # Insert cluster
            cur = conn.execute(
                "INSERT INTO claim_clusters (representative_title, created_at) VALUES (?, ?)",
                (rep_title, now)
            )
            cluster_id = cur.lastrowid
            
            # Insert members
            member_rows = [(cluster_id, m_id) for m_id in member_ids]
            conn.executemany(
                "INSERT INTO claim_cluster_members (cluster_id, fact_check_id) VALUES (?, ?)",
                member_rows
            )
            clusters_created += 1
            members_linked += len(member_ids)
            
    return {"clusters_created": clusters_created, "members_linked": members_linked}
