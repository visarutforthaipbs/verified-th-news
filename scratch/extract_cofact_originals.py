import sqlite3
import re
from collections import Counter

DB_PATH = "data/th_verify.db"

def extract_cofact_originals():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Fetch all cofact explanations
    cursor.execute("SELECT title, explanation FROM fact_checks WHERE source='cofact'")
    rows = cursor.fetchall()
    conn.close()
    
    # We want to extract links like web.facebook.com/share or facebook.com/share or other facebook post links
    fb_share_pattern = r"https?://(?:web\.)?facebook\.com/share/[^\s\"'“”‘’<>(),;]+"
    
    extracted = []
    
    for title, text in rows:
        if not text:
            continue
        # Find all share links
        links = re.findall(fb_share_pattern, text)
        for link in links:
            link = link.rstrip(".:,;!?()[]{}<>\"'“”)‘’")
            extracted.append((title, link))
            
    print(f"Extracted {len(extracted)} original Facebook rumor share links from Cofact articles.\n")
    print("Sample extracted original rumor links:")
    for idx, (title, link) in enumerate(extracted[:25]):
        print(f"{idx+1}. Article: {title}")
        print(f"   Original Source URL: {link}\n")

if __name__ == "__main__":
    extract_cofact_originals()
