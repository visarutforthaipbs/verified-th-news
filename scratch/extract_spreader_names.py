import sqlite3
import re
from collections import defaultdict, Counter

DB_PATH = "data/th_verify.db"

def extract_names():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT source, title, explanation FROM fact_checks WHERE explanation IS NOT NULL AND explanation != ''")
    rows = cursor.fetchall()
    conn.close()
    
    # Matching quotes: เพจ "ชื่อเพจ" or เพจ [ชื่อเพจ] without quotes
    patterns = [
        r"(?:เพจเฟซบุ๊ก|เพจ|บัญชีเฟซบุ๊ก|บัญชีผู้ใช้|บัญชี\s*tiktok|บัญชี\s*ไลน์|ทวิตเตอร์|ช่องยูทูบ)\s*(?:ชื่อ)?\s*[\"“'‘]([^\"“”'‘]{3,50})[\"”'’]",
        r"(?:เพจเฟซบุ๊ก|เพจ|บัญชีเฟซบุ๊ก|บัญชีผู้ใช้|บัญชี\s*tiktok|บัญชี\s*ไลน์|ทวิตเตอร์|ช่องยูทูบ)\s*(?:ชื่อ)?\s*([ก-๙a-zA-Z0-9_\-\.]{3,40})"
    ]
    
    names = Counter()
    source_names = defaultdict(Counter)
    
    for source, title, text in rows:
        combined = (title or "") + " " + (text or "")
        
        for pat in patterns:
            matches = re.findall(pat, combined)
            for name in matches:
                name = name.strip(":- \t\"'“”)‘’\n\r.()")
                if not name or len(name) < 3:
                    continue
                # Filter out generic terms
                if name in ("ดังกล่าว", "ปลอม", "ของ", "การ", "ทางการ", "ผู้ใช้", "ไลน์", "ติ๊กต๊อก", "ทวิตเตอร์", "ยูทูบ"):
                    continue
                if any(x in name.lower() for x in ("ดังกล่าว", "แอบอ้าง", "ไม่จริง", "เชิญชวน", "เผยแพร่", "โฆษณา")):
                    continue
                
                names[name] += 1
                source_names[source][name] += 1
                
    print("Top 30 Page/Account Names mentioned in the database:")
    for name, count in names.most_common(30):
        sources = [src for src, c in source_names.items() if name in c]
        print(f"  - {name} ({count} times) [sources: {', '.join(sources)}]")

if __name__ == "__main__":
    extract_names()
