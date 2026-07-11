from th_verify.db import Repository
from th_verify.models import FactCheckRecord


def test_upsert_is_idempotent(tmp_path):
    repo = Repository(tmp_path / "test.db")
    repo.initialize()
    record = FactCheckRecord(source="demo", source_id="1", source_url="https://example.com/1", title="first")
    assert repo.upsert_many([record]) == 1
    record.title = "updated"
    assert repo.upsert_many([record]) == 1
    assert repo.count() == 1
    with repo.connect() as conn:
        assert conn.execute("SELECT title FROM fact_checks").fetchone()[0] == "updated"


def test_clustering_groups_similar_claims(tmp_path):
    from th_verify.clustering import run_clustering
    repo = Repository(tmp_path / "test.db")
    repo.initialize()
    
    r1 = FactCheckRecord(source="s1", source_id="1", source_url="https://x.com/1", title="น้ำสับปะรดร้อน รักษามะเร็งจริงไหม")
    r2 = FactCheckRecord(source="s2", source_id="2", source_url="https://x.com/2", title="น้ำสับปะรดร้อน รักษามะเร็ง จริงหรือ ?")
    r3 = FactCheckRecord(source="s3", source_id="3", source_url="https://x.com/3", title="กินทุเรียนลดความอ้วน")
    
    repo.upsert_many([r1, r2, r3])
    
    result = run_clustering(tmp_path / "test.db")
    assert result["clusters_created"] == 2
    assert result["members_linked"] == 3
    
    with repo.connect() as conn:
        c_ids = conn.execute(
            "SELECT DISTINCT cluster_id FROM claim_cluster_members m JOIN fact_checks f ON m.fact_check_id = f.id WHERE f.title LIKE '%สับปะรด%'"
        ).fetchall()
        assert len(c_ids) == 1


def test_classification_heuristics():
    from th_verify.classifier import classify_heuristic
    assert classify_heuristic("เรื่องเด่นเย็นนี้ ข่าวปลอมเรื่องวัคซีน", "") == "ข่าวปลอม"
    assert classify_heuristic("เรื่องจริงเรื่องลิขสิทธิ์", "") == "ข่าวจริง"
    assert classify_heuristic("พบข้อมูลบิดเบือนกรณีประกันสังคม", "") == "ข่าวบิดเบือน"
    assert classify_heuristic("หัวข้อปกติไม่มีคำสำคัญ", "") == "unknown"


