#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_era_visualization.py — Generates an interactive Node-Based Visual Graph
illustrating 'วิวัฒนาการ 4 ยุคข่าวลวงในสังคมไทย (2558–2569)' with high-precision topic classification.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import json
import random
from collections import Counter
from th_verify.normalized import get_normalized_records, HIGH_PRECISION_TOPIC_RULES

DB_PATH = Path('data/th_verify.db')
OUTPUT_DIR = Path('data/reports')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
HTML_PATH = OUTPUT_DIR / 'era_evolution_graph.html'

def generate_visualization():
    print("Loading clean atomic claims with high-precision classifier...")
    records = get_normalized_records(DB_PATH, filter_broadcasts=True)
    
    topic_configs = {}
    for tid, name, color, _ in HIGH_PRECISION_TOPIC_RULES:
        topic_configs[tid] = {"name": name, "color": color}
    topic_configs["T99"] = {"name": "เรื่องทั่วไป / อื่นๆ", "color": "#475569"}

    def assign_era(year_str):
        if not year_str or not year_str.isdigit():
            return 4, "ยุคที่ 4 (2567–2569)"
        y = int(year_str)
        if y <= 2018:
            return 1, "ยุคที่ 1 (2558–2561): ข่าวลวงสุขภาพ & ไลน์ส่งต่อ"
        elif y <= 2021:
            return 2, "ยุคที่ 2 (2562–2564): วิกฤตโรคระบาด & นโยบายรัฐ"
        elif y <= 2023:
            return 3, "ยุคที่ 3 (2565–2566): การเงินภิวัตน์ & ล่าเหยื่อออนไลน์"
        else:
            return 4, "ยุคที่ 4 (2567–2569): AI Deepfake & กระแสชาตินิยม"

    random.seed(42)
    by_era = {1: [], 2: [], 3: [], 4: []}
    for r in records:
        era_id, era_name = assign_era(r['published_year'])
        node = {
            "id": r['id'],
            "title": r['title_raw'],
            "claim": r['claim_clean'],
            "source": r['source'],
            "url": r['url'],
            "verdict": r['verdict_normalized'],
            "date": r['published_date'],
            "year": r['published_year'],
            "era_id": era_id,
            "era_name": era_name,
            "topic_id": r['topic_id'],
            "topic_name": r['topic_name'],
            "color": r['topic_color']
        }
        by_era[era_id].append(node)

    sampled_nodes = []
    sampled_nodes.extend(by_era[1]) # take all from Era 1 (~850)
    sampled_nodes.extend(random.sample(by_era[2], min(len(by_era[2]), 400)))
    sampled_nodes.extend(random.sample(by_era[3], min(len(by_era[3]), 400)))
    sampled_nodes.extend(random.sample(by_era[4], min(len(by_era[4]), 400)))

    print(f"Compiled {len(sampled_nodes)} interactive data point nodes across 4 eras.")

    nodes_json = json.dumps(sampled_nodes, ensure_ascii=False)
    topics_json = json.dumps(topic_configs, ensure_ascii=False)

    # Read base html and replace
    with open(OUTPUT_DIR / 'full_universe_map.html', 'r', encoding='utf-8') as f:
        full_content = f.read()

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(full_content)
    print(f"Interactive visual node graph updated at: {HTML_PATH}")

if __name__ == '__main__':
    generate_visualization()
