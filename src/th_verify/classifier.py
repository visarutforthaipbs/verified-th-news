import re
import httpx
import asyncio
from pathlib import Path
from .db import Repository

FAKE_KEYWORDS = [
    r"ข่าวปลอม", r"ข้อมูลเท็จ", r"คลิปปลอม", r"ภาพปลอม", r"ไม่จริง", 
    r"ลวงโลก", r"มิจฉาชีพ", r"แอบอ้าง", r"แก๊งคอลเซ็นเตอร์", r"ห้ามแชร์",
    r"อย่าหลงเชื่อ", r"อย่าแชร์"
]

TRUE_KEYWORDS = [
    r"ข่าวจริง", r"เรื่องจริง", r"เป็นความจริง", r"ของจริง", r"แชร์จริง",
    r"ชัวร์\s*:\s*จริง", r"สรุป\s*:\s*จริง"
]

DISTORTED_KEYWORDS = [
    r"บิดเบือน", r"เข้าใจผิด", r"จริงบางส่วน", r"คลาดเคลื่อน"
]

def classify_heuristic(title: str, text: str) -> str:
    combined = (title or "") + " " + (text or "")
    for pattern in FAKE_KEYWORDS:
        if re.search(pattern, combined):
            return "ข่าวปลอม"
    for pattern in DISTORTED_KEYWORDS:
        if re.search(pattern, combined):
            return "ข่าวบิดเบือน"
    for pattern in TRUE_KEYWORDS:
        if re.search(pattern, combined):
            return "ข่าวจริง"
    return "unknown"

async def classify_with_gemini(client: httpx.AsyncClient, title: str, text: str, api_key: str) -> str | None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    prompt = (
        "คุณคือผู้เชี่ยวชาญการวิเคราะห์ข่าวปลอม จงจัดหมวดหมู่ข่าวสารต่อไปนี้เป็นภาษาไทย\n"
        "คำตอบที่เป็นไปได้มีเพียง 4 คำนี้เท่านั้น:\n"
        "1. ข่าวปลอม (หากเนื้อหานั้นเป็นเท็จหรือไม่มีความจริงอยู่เลย)\n"
        "2. ข่าวจริง (หากเนื้อหานั้นถูกต้องและเป็นความจริง)\n"
        "3. ข่าวบิดเบือน (หากเนื้อหานั้นจริงบางส่วนแต่ถูกตัดต่อหรือนำเสนอให้เข้าใจผิด)\n"
        "4. unknown (หากไม่มีข้อมูลข่าวเพียงพอหรือไม่สามารถสรุปได้)\n\n"
        f"หัวข้อข่าว: {title}\n"
        f"คำอธิบายเพิ่มเติม: {text[:400]}\n\n"
        "จงตอบเฉพาะคำตอบที่เป็นคำศัพท์ 1 ใน 4 คำข้างต้นเท่านั้น ห้ามตอบนอกเหนือจากนี้เด็ดขาด:"
    )
    try:
        response = await client.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 10}
        }, timeout=5.0)
        if response.status_code == 200:
            result = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            for verdict in ("ข่าวปลอม", "ข่าวจริง", "ข่าวบิดเบือน"):
                if verdict in result:
                    return verdict
            return "unknown"
    except Exception:
        pass
    return None

async def run_classification(db_path: Path, api_key: str | None = None, concurrency: int = 5) -> dict[str, int]:
    repo = Repository(db_path)
    repo.initialize()
    
    with repo.connect() as conn:
        rows = conn.execute(
            "SELECT id, title, explanation FROM fact_checks "
            "WHERE verdict = 'unknown' AND source IN ('sure_share', 'cofact') "
            "AND verdict_origin NOT LIKE 'human%'"
        ).fetchall()
        
    if not rows:
        return {"updated": 0, "total": 0}
        
    updated = 0
    sem = asyncio.Semaphore(concurrency)
    
    async def process_one(row_id: int, title: str, explanation: str, client: httpx.AsyncClient) -> tuple[int, str]:
        verdict = None
        if api_key:
            async with sem:
                verdict = await classify_with_gemini(client, title, explanation, api_key)
        if not verdict:
            verdict = classify_heuristic(title, explanation)
        return row_id, verdict

    async with httpx.AsyncClient() as client:
        tasks = [process_one(row["id"], row["title"], row["explanation"], client) for row in rows]
        results = await asyncio.gather(*tasks)
        
    with repo.connect() as conn:
        updates = []
        for row_id, verdict in results:
            if verdict != "unknown":
                updates.append((verdict, row_id))
        
        if updates:
            conn.executemany(
                "UPDATE fact_checks SET verdict = ?, verdict_origin = 'heuristic' "
                "WHERE id = ? AND verdict_origin NOT LIKE 'human%'",
                updates,
            )
            updated = len(updates)
            
    return {"updated": updated, "total": len(rows)}
