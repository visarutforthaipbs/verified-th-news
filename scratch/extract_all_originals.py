import sqlite3
import re
from collections import defaultdict, Counter

DB_PATH = "data/th_verify.db"

# Official domains/handles of the agencies to exclude
EXCLUDE_PATTERNS = [
    r"facebook\.com/sureandshare",
    r"twitter\.com/sureandshare",
    r"tiktok\.com/@sureandshare",
    r"youtube\.com/@sureandshare",
    r"facebook\.com/tnamcot",
    r"twitter\.com/tnamcot",
    r"youtube\.com/tnamcot",
    r"tnamcot\.com",
    r"facebook\.com/antifakenewscenter",
    r"twitter\.com/afncthailand",
    r"tiktok\.com/@antifakenewscenter",
    r"antifakenewscenter\.com",
    r"cofact\.org",
    r"facebook\.com/cofactthailand",
    r"thaipbs\.or\.th",
    r"files\.wp\.thaipbs\.or\.th"
]

def extract_original_sources():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT source, title, explanation FROM fact_checks WHERE explanation IS NOT NULL AND explanation != ''")
    rows = cursor.fetchall()
    conn.close()
    
    url_pattern = r"https?://(?:web\.)?(?:facebook\.com|tiktok\.com|youtube\.com|youtu\.be|twitter\.com|x\.com)/[^\s\"'“”‘’<>(),;]+"
    
    source_links = defaultdict(list)
    
    for source, title, text in rows:
        urls = re.findall(url_pattern, text)
        for url in urls:
            url = url.rstrip(".:,;!?()[]{}<>\"'“”)‘’")
            
            # Check if this URL is an official channel of the fact check agency
            is_official = False
            for pat in EXCLUDE_PATTERNS:
                if re.search(pat, url.lower()):
                    is_official = True
                    break
            
            if not is_official:
                source_links[source].append((title, url))
                
    for source, items in source_links.items():
        print(f"\n==========================================")
        print(f"Agency: {source.upper()} - Found {len(items)} referenced external social media links.")
        print(f"==========================================")
        
        # Count frequencies
        counter = Counter([url for title, url in items])
        
        # Display top 10 unique links
        printed = 0
        for url, count in counter.most_common(10):
            # Find a title associated with this link
            sample_title = next(title for title, u in items if u == url)
            print(f"{printed+1}. Link: {url} ({count} times)")
            print(f"   Sample Claim: {sample_title}\n")
            printed += 1

if __name__ == "__main__":
    extract_original_sources()
