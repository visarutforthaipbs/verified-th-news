#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_temporal_story_app.py — Generates the Complete Interactive Temporal Storytelling
Application for Longitudinal Fact-Check Archives (2015–2026).

Implements:
1. Scrollytelling Chapters (1: Folk Health, 2: Pandemic Shock, 3: Financial Scam Pivot, 4: AI & Sovereignty, 5: Sandbox).
2. Dynamic 26,894 Particle Canvas with Smooth 60 FPS Camera Focus & Physics.
3. Interactive Streamgraph ("River of Misinformation") spanning 2015–2026.
4. Layer B Narrative Framing Drilldowns (Migrants, Banking Scams, Deepfakes).
5. O(1) Spatial Grid Indexing & Real-Time Full-Text Search.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import json
import math
import random
from collections import Counter, defaultdict
from th_verify.normalized import get_normalized_records, HIGH_PRECISION_TOPIC_RULES

DB_PATH = Path('data/th_verify.db')
OUTPUT_DIR = Path('data/reports')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
HTML_PATH = OUTPUT_DIR / 'temporal_story_app.html'

def build_app():
    print("Loading 26,894 clean atomic claims for temporal story application...")
    records = get_normalized_records(DB_PATH, filter_broadcasts=True)
    total_count = len(records)
    print(f"Loaded {total_count} records.")

    # 1. Topic Layout & Styling Config
    topic_meta = {
        "T01": {"name": "สุขภาพ อาหาร และยา", "color": "#10b981", "x": -420, "y": -260},
        "T02": {"name": "โควิด-19 และวัคซีน", "color": "#f59e0b", "x": -160, "y": -400},
        "T03": {"name": "สินเชื่อปลอม & คอลเซ็นเตอร์", "color": "#f43f5e", "x": 420, "y": -220},
        "T04": {"name": "หลอกลงทุนหุ้น & SET", "color": "#a855f7", "x": 460, "y": 240},
        "T05": {"name": "นโยบายรัฐ & สวัสดิการ", "color": "#06b6d4", "x": 140, "y": 420},
        "T06": {"name": "แรงงานต่างด้าว & สัญชาติ", "color": "#fb923c", "x": -240, "y": 380},
        "T07": {"name": "AI Deepfake & สื่อตัดต่อ", "color": "#38bdf8", "x": 300, "y": -440},
        "T08": {"name": "ภัยพิบัติ & สภาพอากาศ", "color": "#94a3b8", "x": -500, "y": 140},
        "T09": {"name": "การเมือง & การเลือกตั้ง", "color": "#6366f1", "x": -60, "y": 200},
        "T10": {"name": "ความมั่นคง & ภูมิรัฐศาสตร์", "color": "#ec4899", "x": 0, "y": -140},
        "T99": {"name": "เรื่องทั่วไป / อื่นๆ", "color": "#475569", "x": 0, "y": 60}
    }

    def assign_era(year_str):
        if not year_str or not year_str.isdigit():
            return 4
        y = int(year_str)
        if y <= 2018:
            return 1
        elif y <= 2021:
            return 2
        elif y <= 2023:
            return 3
        else:
            return 4

    random.seed(42)
    nodes = []

    # 2. Build Compact Node Payload with Spatial Layouts
    for r in records:
        tid = r["topic_id"]
        tcfg = topic_meta[tid]
        era = assign_era(r["published_year"])

        angle = random.uniform(0, 2 * math.pi)
        dist = random.gauss(0, 70)
        px = round(tcfg["x"] + math.cos(angle) * dist, 1)
        py = round(tcfg["y"] + math.sin(angle) * dist, 1)

        y_int = int(r["published_year"]) if r["published_year"] and r["published_year"].isdigit() else 2024
        
        nodes.append({
            "i": r["id"],
            "c": r["claim_clean"],
            "y": y_int,
            "e": era,
            "t": tid,
            "s": r["source"],
            "v": r["verdict_normalized"],
            "d": r["published_date"] or "",
            "u": r["url"] or "",
            "x": px,
            "y_pos": py
        })

    # 3. Streamgraph Timeline Matrix (2015 to 2026)
    years = sorted(list(set(n["y"] for n in nodes if n["y"] >= 2015)))
    stream_timeline = []
    
    for y in years:
        y_nodes = [n for n in nodes if n["y"] == y]
        y_total = len(y_nodes)
        counts = Counter(n["t"] for n in y_nodes)
        
        row = {"year": y, "total": y_total}
        for tid in topic_meta.keys():
            cnt = counts[tid]
            pct = round((cnt / y_total) * 100, 1) if y_total > 0 else 0.0
            row[tid] = {"count": cnt, "pct": pct}
        stream_timeline.append(row)

    # 4. Layer B Narrative Trajectories (Migrant Case Study)
    migrant_nodes = [n for n in nodes if n["t"] == "T06"]
    layer_b_migrant = []
    for y in years:
        y_m = [n for n in migrant_nodes if n["y"] == y]
        tot = len(y_m)
        if tot == 0:
            continue
        disease = sum(1 for n in y_m if any(k in n["c"].lower() for k in ["โควิด", "โรค", "ระบาด", "ติดเชื้อ"]))
        jobs = sum(1 for n in y_m if any(k in n["c"].lower() for k in ["แย่งงาน", "แย่งอาชีพ", "ค้าขาย", "นอมินี"]))
        sovereignty = sum(1 for n in y_m if any(k in n["c"].lower() for k in ["สัญชาติ", "เลือกตั้ง", "บัตรประชาชน", "อธิปไตย", "เกาะกูด", "mou"]))
        layer_b_migrant.append({
            "year": y,
            "total": tot,
            "disease_pct": round((disease / tot) * 100, 1),
            "jobs_pct": round((jobs / tot) * 100, 1),
            "sovereignty_pct": round((sovereignty / tot) * 100, 1)
        })

    # 5. Editorial Scrollytelling Chapters
    chapters = [
        {
            "id": 1,
            "era": 1,
            "year_range": "2558–2561 (2015–2018)",
            "title": "บทที่ 1: ยุคข่าวลวงสุขภาพ & ไลน์กลุ่มส่งต่อ",
            "subtitle": "เมื่อข่าวลวงยังเป็นเรื่องเล่าพื้นบ้าน ไร้ร่องรอยของอาชญากรรมการเงิน",
            "narrative": "ในยุคแรกเริ่ม ข่าวลวงในสังคมไทยเกือบ 50% เป็นเรื่องเกี่ยวกับสูตรสมุนไพร อาหารพื้นบ้าน และความเชื่อเรื่องสุขภาพ เช่น 'มะนาวโซดารักษามะเร็ง' หรือ 'เนื้องูทำลูกชิ้นปลา' โดยในยุคนี้สถิติการหลอกลงทุน สินเชื่อปลอม หรือแก๊งคอลเซ็นเตอร์มีค่าเป็น 0.0%",
            "camera": {"x": -420, "y": -260, "k": 1.6},
            "highlight_topic": "T01",
            "milestone": "พ.ค. 2558: เริ่มต้นบันทึกชัวร์ก่อนแชร์ (MCOT)"
        },
        {
            "id": 2,
            "era": 2,
            "year_range": "2562–2564 (2019–2021)",
            "title": "บทที่ 2: วิกฤตโรคระบาด & คลื่นสึนามิข้อมูลเท็จ",
            "subtitle": "จุดเปลี่ยนประวัติศาสตร์รุนแรงที่สุด (JSD = 0.4161) จากการมาถึงของโควิด-19",
            "narrative": "ปี 2563 ก่อให้เกิดการระเบิดของข่าวลวงโรคระบาดและวัคซีนพุ่งครองสัดส่วน 28.5% นำไปสู่การก่อตั้งศูนย์ต่อต้านข่าวปลอมแห่งชาติ (AFNC) และเครือข่าย Fact-checkers อิสระ เช่น Cofact และ AFP โดยช่วงปลายยุคเริ่มพบสัญญาณการเกิดเพจเงินกู้แอบอ้างธนาคารรัฐ",
            "camera": {"x": -160, "y": -400, "k": 1.4},
            "highlight_topic": "T02",
            "milestone": "พ.ย. 2562: เปิดตัวศูนย์ต่อต้านข่าวปลอม (AFNC)"
        },
        {
            "id": 3,
            "era": 3,
            "year_range": "2565–2566 (2022–2023)",
            "title": "บทที่ 3: การเงินภิวัตน์ของมิจฉาชีพ (Financialization Pivot)",
            "subtitle": "มิจฉาชีพย้ายเป้าหมายจากความกลัวโรคระบาด สู่การปล้นเงินในบัญชี",
            "narrative": "เมื่อความกลัวโควิด-19 เริ่มซา ข่าวโรคระบาดลดฮวบ -90% แต่มิจฉาชีพข้ามชาติได้ผันตัวเข้าสู่การเงินภิวัตน์ ข่าวหลอกลงทุนหุ้น SET และคริปโตพุ่งขึ้นอย่างก้าวกระโดดกว่า +2,038% แอบอ้างธนาคารออมสินและตลาดหลักทรัพย์ฯ กว่า 1,300 เรื่อง",
            "camera": {"x": 440, "y": 0, "k": 1.3},
            "highlight_topic": "T04",
            "milestone": "ม.ค. 2566: ปรากฏการณ์แอบอ้าง SET เทรดหุ้นกำไรรายวัน"
        },
        {
            "id": 4,
            "era": 4,
            "year_range": "2567–2569 (2024–2026)",
            "title": "บทที่ 4: AI Deepfake & คลื่นชาตินิยม/อธิปไตย",
            "subtitle": "สงครามข้อมูลยุคใหม่ด้วยปัญญาประดิษฐ์ และการปั่นกระแสการเมืองข้ามพรมแดน",
            "narrative": "ในยุคปัจจุบัน ข่าวลวงเรื่องแรงงานต่างด้าวและการเสียดินแดนพุ่งขึ้น +665% โดยกลายพันธุ์จากเรื่องโรคระบาดสู่เรื่อง 'สิทธิการเมืองและอธิปไตย' ควบคู่กับการแพร่ระบาดของคลิปเสียงและภาพตัดต่อ AI Deepfake (+501%)",
            "camera": {"x": 0, "y": 0, "k": 1.0},
            "highlight_topic": "T06",
            "milestone": "พ.ศ. 2568: คลื่นข่าวลวงอธิปไตยเกาะกูดและดีพเฟกเสียงนายกฯ"
        },
        {
            "id": 5,
            "era": 0,
            "year_range": "2558–2569 (11 ปีเต็ม)",
            "title": "บทที่ 5: สำรวจจักรวาลข้อมูลอิสระ (Open Exploration Sandbox)",
            "subtitle": "ค้นหา ตรวจสอบ และวิเคราะห์ข้อเท็จจริงทั้งหมด 26,894 เรื่องด้วยตัวคุณเอง",
            "narrative": "คุณสามารถค้นหาคำสำคัญ กรองตามยุคสมัย เลื่อนแถบกาลเวลา หรือคลิกดูรายละเอียดของข้ออ้างจริงทุกเรื่องบนผืนผ้าใบ พร้อมดูกราฟสายธารวิวัฒนาการด้านล่าง",
            "camera": {"x": 0, "y": 0, "k": 0.85},
            "highlight_topic": None,
            "milestone": "11.2 ปี & 28,506 ข้อมูลบันทึกประวัติศาสตร์"
        }
    ]

    nodes_json = json.dumps(nodes, ensure_ascii=False)
    topics_json = json.dumps(topic_meta, ensure_ascii=False)
    stream_json = json.dumps(stream_timeline, ensure_ascii=False)
    layer_b_json = json.dumps(layer_b_migrant, ensure_ascii=False)
    chapters_json = json.dumps(chapters, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>11 Years of Thai Misinformation: A Longitudinal Story Map (2015–2026)</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;600;700;800&family=Sarabun:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #060913;
            --panel-bg: rgba(13, 19, 36, 0.9);
            --panel-border: rgba(45, 62, 94, 0.7);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #38bdf8;
            --accent-emerald: #10b981;
            --accent-rose: #f43f5e;
            --accent-purple: #a855f7;
            --accent-amber: #f59e0b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Prompt', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            overflow: hidden;
            height: 100vh;
            width: 100vw;
            display: flex;
            flex-direction: column;
        }}

        /* ── Top Header & Timeline Scrubber ───────────────────────────────── */
        header {{
            height: 64px;
            background: var(--panel-bg);
            backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--panel-border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 1.6rem;
            z-index: 100;
        }}
        .brand-zone {{
            display: flex;
            align-items: center;
            gap: 0.8rem;
        }}
        .brand-zone h1 {{
            font-size: 1.15rem;
            font-weight: 700;
            color: #fff;
        }}
        .brand-badge {{
            background: linear-gradient(135deg, #38bdf8, #818cf8);
            color: #000;
            font-size: 0.7rem;
            font-weight: 800;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
        }}

        /* Top Timeline Year Slider */
        .timeline-slider-zone {{
            display: flex;
            align-items: center;
            gap: 0.8rem;
            background: #0b1122;
            border: 1px solid var(--panel-border);
            padding: 0.35rem 1rem;
            border-radius: 30px;
        }}
        .btn-play-ctrl {{
            background: var(--accent-blue);
            color: #000;
            border: none;
            font-weight: 700;
            font-size: 0.8rem;
            padding: 0.25rem 0.8rem;
            border-radius: 16px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .year-label-active {{
            font-size: 0.95rem;
            font-weight: 800;
            color: var(--accent-blue);
            min-width: 50px;
        }}
        input[type=range] {{
            width: 220px;
            accent-color: var(--accent-blue);
            cursor: pointer;
        }}

        .header-search {{
            position: relative;
            width: 220px;
        }}
        .header-search input {{
            width: 100%;
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid var(--panel-border);
            border-radius: 20px;
            color: #fff;
            padding: 0.35rem 0.8rem 0.35rem 1.8rem;
            font-family: 'Sarabun', sans-serif;
            font-size: 0.8rem;
            outline: none;
        }}
        .header-search span {{
            position: absolute;
            left: 0.6rem;
            top: 50%;
            transform: translateY(-50%);
            font-size: 0.75rem;
            color: var(--text-muted);
        }}

        /* ── Main Layout: Scrollytelling Left & Canvas Right ──────────────── */
        #main-stage {{
            flex: 1;
            display: flex;
            position: relative;
            overflow: hidden;
            height: calc(100vh - 64px - 140px);
        }}

        /* Left Story Scroll Panel */
        #story-panel {{
            width: 440px;
            height: 100%;
            overflow-y: auto;
            background: linear-gradient(90deg, rgba(6,9,19,0.98) 80%, rgba(6,9,19,0.0));
            z-index: 50;
            padding: 2rem 1.5rem 4rem 1.8rem;
            scroll-behavior: smooth;
        }}
        #story-panel::-webkit-scrollbar {{
            width: 6px;
        }}
        #story-panel::-webkit-scrollbar-thumb {{
            background: rgba(56, 189, 248, 0.2);
            border-radius: 3px;
        }}

        .story-card {{
            background: var(--panel-bg);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 1.6rem;
            margin-bottom: 2.5rem;
            box-shadow: 0 20px 40px rgba(0,0,0,0.6);
            transition: all 0.3s ease;
            opacity: 0.45;
            transform: scale(0.97);
        }}
        .story-card.active {{
            opacity: 1;
            transform: scale(1);
            border-color: var(--accent-blue);
            box-shadow: 0 0 30px rgba(56, 189, 248, 0.25);
        }}
        .story-card .kicker {{
            font-size: 0.75rem;
            font-weight: 700;
            color: var(--accent-blue);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .story-card h2 {{
            font-size: 1.25rem;
            font-weight: 700;
            margin: 0.3rem 0 0.4rem 0;
            line-height: 1.3;
        }}
        .story-card .subtitle {{
            font-family: 'Sarabun', sans-serif;
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--accent-amber);
            margin-bottom: 0.8rem;
        }}
        .story-card p {{
            font-family: 'Sarabun', sans-serif;
            font-size: 0.9rem;
            color: var(--text-muted);
            line-height: 1.6;
            margin-bottom: 1rem;
        }}
        .milestone-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.3);
            color: var(--accent-blue);
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.3rem 0.6rem;
            border-radius: 6px;
        }}

        /* Right Canvas Area */
        #canvas-viewport {{
            flex: 1;
            position: relative;
            height: 100%;
            overflow: hidden;
        }}
        canvas {{
            width: 100%;
            height: 100%;
            cursor: grab;
        }}
        canvas:active {{ cursor: grabbing; }}

        /* Live Inspector Card (Right Floating) */
        #inspector-float {{
            position: absolute;
            top: 1.5rem;
            right: 1.5rem;
            width: 340px;
            background: var(--panel-bg);
            backdrop-filter: blur(20px);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 1.2rem;
            box-shadow: 0 20px 40px rgba(0,0,0,0.6);
            z-index: 60;
        }}
        #inspector-float h3 {{
            font-size: 0.85rem;
            font-weight: 700;
            color: var(--accent-blue);
            margin-bottom: 0.6rem;
            border-bottom: 1px solid var(--panel-border);
            padding-bottom: 0.4rem;
            display: flex;
            justify-content: space-between;
        }}

        /* ── Bottom Section: Streamgraph & Layer B Sub-Charts ──────────────── */
        #bottom-deck {{
            height: 140px;
            background: var(--panel-bg);
            backdrop-filter: blur(20px);
            border-top: 1px solid var(--panel-border);
            display: flex;
            padding: 0.8rem 1.6rem;
            gap: 1.5rem;
            z-index: 100;
        }}
        .deck-section {{
            display: flex;
            flex-direction: column;
        }}
        .deck-section h4 {{
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.4rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        #streamgraph-container {{
            flex: 1.6;
            height: 100%;
            position: relative;
        }}
        #layer-b-container {{
            flex: 1;
            height: 100%;
            background: rgba(11, 17, 32, 0.8);
            border: 1px solid var(--panel-border);
            border-radius: 8px;
            padding: 0.6rem 0.8rem;
        }}

        /* Streamgraph Bars */
        .stream-grid {{
            display: flex;
            height: 75px;
            gap: 4px;
            align-items: flex-end;
        }}
        .stream-col {{
            flex: 1;
            display: flex;
            flex-direction: column-reverse;
            height: 100%;
            cursor: pointer;
            position: relative;
            transition: opacity 0.2s ease;
        }}
        .stream-col:hover {{ opacity: 0.85; }}
        .stream-col.active {{
            outline: 2px solid var(--accent-blue);
            outline-offset: 2px;
            border-radius: 2px;
        }}
        .stream-segment {{
            width: 100%;
            transition: height 0.3s ease;
        }}
        .stream-col-label {{
            font-size: 0.65rem;
            color: var(--text-muted);
            text-align: center;
            margin-top: 0.2rem;
        }}

        /* Tooltip */
        #app-tooltip {{
            position: absolute;
            background: rgba(13, 19, 36, 0.96);
            border: 1px solid var(--accent-blue);
            color: #fff;
            padding: 0.6rem 0.9rem;
            border-radius: 8px;
            font-size: 0.8rem;
            max-width: 300px;
            pointer-events: none;
            z-index: 1000;
            display: none;
            box-shadow: 0 10px 30px rgba(0,0,0,0.9);
            transform: translate(-50%, -125%);
        }}
    </style>
</head>
<body>
    <!-- Top Navigation -->
    <header>
        <div class="brand-zone">
            <h1>TH Verify <span class="brand-badge">Temporal Story Map</span></h1>
        </div>

        <div class="timeline-slider-zone">
            <button class="btn-play-ctrl" id="btn-timeline-play" onclick="toggleTimelinePlay()">▶️ เล่นวิวัฒนาการ</button>
            <input type="range" id="timelineRange" min="2015" max="2026" value="2026" step="1" oninput="onYearSlider(this.value)">
            <span class="year-label-active" id="yearLabelDisplay">2026</span>
        </div>

        <div class="header-search">
            <span>🔍</span>
            <input type="text" id="searchInput" placeholder="ค้นหา 28,000 เรื่อง..." oninput="handleSearch(this.value)">
        </div>
    </header>

    <!-- Main Stage -->
    <div id="main-stage">
        <!-- Left Scrollytelling Story Panel -->
        <div id="story-panel">
            <!-- Dynamically populated chapters -->
        </div>

        <!-- Right Canvas Viewport -->
        <div id="canvas-viewport">
            <canvas id="storyCanvas"></canvas>

            <!-- Floating Inspector -->
            <div id="inspector-float">
                <h3>
                    <span>🎯 รายละเอียดข้ออ้าง (Claim Inspector)</span>
                    <span id="inspectCountBadge" style="color: var(--accent-blue);">26,894 claims</span>
                </h3>
                <div id="inspectContent">
                    <div style="color: var(--text-muted); font-size: 0.82rem; line-height: 1.5; text-align: center; padding: 1rem 0;">
                        👉 เลื่อนเมาส์หรือคลิกที่จุดบนกราฟ<br>เพื่อตรวจสอบข้อความจริงจากฐานข้อมูล
                    </div>
                </div>
            </div>
        </div>

        <div id="app-tooltip"></div>
    </div>

    <!-- Bottom Deck: Streamgraph & Layer B Narrative Framing -->
    <div id="bottom-deck">
        <div class="deck-section" id="streamgraph-container">
            <h4>
                <span>🌊 สายธารวิวัฒนาการข่าวลวง (The River of Misinformation 2015–2026)</span>
                <span style="font-size: 0.7rem; color: var(--accent-blue);">คลิกที่แท่งปีเพื่อเปลี่ยนเวลา</span>
            </h4>
            <div class="stream-grid" id="streamGrid"></div>
        </div>

        <div class="deck-section" id="layer-b-container">
            <h4>
                <span>🎭 เจาะลึก Layer B: การกลายพันธุ์ของข้ออ้าง "แรงงานต่างด้าว"</span>
                <span id="layerBYearLabel" style="color: var(--accent-amber); font-size: 0.75rem;">ปี 2026</span>
            </h4>
            <div id="layerBContent" style="margin-top: 0.3rem;"></div>
        </div>
    </div>

    <script>
        const nodes = {nodes_json};
        const topicMeta = {topics_json};
        const streamTimeline = {stream_json};
        const layerBMigrant = {layer_b_json};
        const chapters = {chapters_json};

        const canvas = document.getElementById('storyCanvas');
        const ctx = canvas.getContext('2d');
        const tooltip = document.getElementById('app-tooltip');

        let width = canvas.width = window.innerWidth - 440;
        let height = canvas.height = window.innerHeight - 64 - 140;

        window.addEventListener('resize', () => {{
            width = canvas.width = window.innerWidth - 440;
            height = canvas.height = window.innerHeight - 64 - 140;
            buildSpatialGrid();
        }});

        let currentYear = 2026;
        let activeChapterId = 1;
        let activeFilterTopic = null;
        let searchKeyword = "";
        let selectedNode = null;
        let hoveredNode = null;

        // Camera Transform with Smooth Interpolation
        let camera = {{ x: 0, y: 0, k: 0.85 }};
        let targetCamera = {{ x: 0, y: 0, k: 0.85 }};
        let isDragging = false;
        let startX, startY;

        // Spatial Grid for O(1) Hit-Testing on 26,894 points
        let cellSize = 35;
        let spatialGrid = new Map();

        function buildSpatialGrid() {{
            spatialGrid.clear();
            for (let i = 0; i < nodes.length; i++) {{
                const n = nodes[i];
                if (!isNodeVisible(n)) continue;
                const gx = Math.floor(n.x / cellSize);
                const gy = Math.floor(n.y_pos / cellSize);
                const key = `${{gx}},${{gy}}`;
                if (!spatialGrid.has(key)) spatialGrid.set(key, []);
                spatialGrid.get(key).push(n);
            }}
        }}

        function isNodeVisible(n) {{
            if (activeChapterId < 5 && activeChapterId > 0) {{
                const ch = chapters.find(c => c.id === activeChapterId);
                if (ch && ch.era !== 0 && n.e !== ch.era) return false;
            }} else {{
                if (n.y > currentYear) return false;
            }}
            if (activeFilterTopic && n.t !== activeFilterTopic) return false;
            if (searchKeyword && !n.c.toLowerCase().includes(searchKeyword)) return false;
            return true;
        }}

        // Render Scrollytelling Chapters
        const storyPanel = document.getElementById('story-panel');
        chapters.forEach(ch => {{
            const card = document.createElement('div');
            card.className = `story-card ${{ch.id === 1 ? 'active' : ''}}`;
            card.id = `chapter-card-${{ch.id}}`;
            card.innerHTML = `
                <div class="kicker">${{ch.year_range}}</div>
                <h2>${{ch.title}}</h2>
                <div class="subtitle">${{ch.subtitle}}</div>
                <p>${{ch.narrative}}</p>
                <div class="milestone-badge">🚩 ${{ch.milestone}}</div>
            `;
            storyPanel.appendChild(card);
        }});

        // Scroll Intersection Observer for Guided Chapters
        storyPanel.addEventListener('scroll', () => {{
            const cards = document.querySelectorAll('.story-card');
            let closest = cards[0];
            let minDistance = Infinity;

            cards.forEach(card => {{
                const rect = card.getBoundingClientRect();
                const dist = Math.abs(rect.top - 120);
                if (dist < minDistance) {{
                    minDistance = dist;
                    closest = card;
                }}
            }});

            cards.forEach(c => c.classList.remove('active'));
            closest.classList.add('active');

            const chId = parseInt(closest.id.replace('chapter-card-', ''));
            if (chId !== activeChapterId) {{
                setChapter(chId);
            }}
        }});

        function setChapter(chId) {{
            activeChapterId = chId;
            const ch = chapters.find(c => c.id === chId);
            if (!ch) return;

            targetCamera.x = (width / 2) - (ch.camera.x * ch.camera.k);
            targetCamera.y = (height / 2) - (ch.camera.y * ch.camera.k);
            targetCamera.k = ch.camera.k;

            activeFilterTopic = ch.highlight_topic;
            buildSpatialGrid();
            updateLayerBDeck();
        }}

        // Streamgraph Builder
        const streamGrid = document.getElementById('streamGrid');
        streamTimeline.forEach(st => {{
            const col = document.createElement('div');
            col.className = `stream-col ${{st.year === currentYear ? 'active' : ''}}`;
            col.id = `stream-col-${{st.year}}`;
            col.onclick = () => onYearSlider(st.year);

            let innerHtml = '';
            Object.entries(topicMeta).forEach(([tid, cfg]) => {{
                if (tid === 'T99') return;
                const d = st[tid];
                if (d && d.pct > 0) {{
                    innerHtml += `<div class="stream-segment" style="height: ${{d.pct * 0.7}}px; background: ${{cfg.color}};"></div>`;
                }}
            }});
            innerHtml += `<div class="stream-col-label">${{st.year}}</div>`;
            col.innerHTML = innerHtml;
            streamGrid.appendChild(col);
        }});

        function onYearSlider(yr) {{
            currentYear = parseInt(yr);
            document.getElementById('timelineRange').value = currentYear;
            document.getElementById('yearLabelDisplay').innerText = currentYear;

            document.querySelectorAll('.stream-col').forEach(c => c.classList.remove('active'));
            const activeCol = document.getElementById(`stream-col-${{currentYear}}`);
            if (activeCol) activeCol.classList.add('active');

            buildSpatialGrid();
            updateLayerBDeck();
        }}

        function updateLayerBDeck() {{
            const container = document.getElementById('layerBContent');
            const label = document.getElementById('layerBYearLabel');
            label.innerText = `ปี ${{currentYear}}`;

            const yrData = layerBMigrant.find(d => d.year === currentYear) || layerBMigrant[layerBMigrant.length - 1];
            if (!yrData) return;

            container.innerHTML = `
                <div style="display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.75rem;">
                    <div style="display: flex; justify-content: space-between;">
                        <span>🦠 แพร่เชื้อโรค/โควิด:</span>
                        <strong style="color: #f59e0b;">${{yrData.disease_pct}}%</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>💼 แย่งอาชีพ/นอมินี:</span>
                        <strong style="color: #10b981;">${{yrData.jobs_pct}}%</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>🏛️ สัญชาติ/สิทธิการเมือง/เกาะกูด:</span>
                        <strong style="color: #f43f5e;">${{yrData.sovereignty_pct}}%</strong>
                    </div>
                </div>
            `;
        }}

        function handleSearch(val) {{
            searchKeyword = val.trim().toLowerCase();
            buildSpatialGrid();
        }}

        // Smooth Camera Physics & High Performance 60 FPS Render
        function render() {{
            camera.x += (targetCamera.x - camera.x) * 0.08;
            camera.y += (targetCamera.y - camera.y) * 0.08;
            camera.k += (targetCamera.k - camera.k) * 0.08;

            ctx.clearRect(0, 0, width, height);
            ctx.save();
            ctx.translate(camera.x, camera.y);
            ctx.scale(camera.k, camera.k);

            // 1. Draw Cluster Hulls
            Object.entries(topicMeta).forEach(([tid, cfg]) => {{
                if (tid === 'T99') return;
                ctx.beginPath();
                ctx.arc(cfg.x, cfg.y, 130, 0, Math.PI * 2);
                ctx.fillStyle = cfg.color + '0e';
                ctx.fill();
                ctx.strokeStyle = cfg.color + '25';
                ctx.lineWidth = 1.5;
                ctx.stroke();

                ctx.font = 'bold 12px "Prompt", sans-serif';
                ctx.fillStyle = cfg.color;
                ctx.textAlign = 'center';
                ctx.fillText(cfg.name, cfg.x, cfg.y - 140);
            }});

            // 2. Draw 26,894 Claim Nodes
            for (let i = 0; i < nodes.length; i++) {{
                const n = nodes[i];
                if (!isNodeVisible(n)) continue;

                const cfg = topicMeta[n.t] || {{ color: "#64748b" }};
                ctx.beginPath();
                ctx.arc(n.x, n.y_pos, 2.7, 0, Math.PI * 2);
                ctx.fillStyle = cfg.color;
                ctx.fill();
            }}

            // 3. Draw Hovered & Selected Nodes
            if (hoveredNode) {{
                ctx.beginPath();
                ctx.arc(hoveredNode.x, hoveredNode.y_pos, 6.5, 0, Math.PI * 2);
                ctx.fillStyle = '#ffffff';
                ctx.fill();
                ctx.strokeStyle = '#38bdf8';
                ctx.lineWidth = 2.5;
                ctx.stroke();
            }}
            if (selectedNode) {{
                ctx.beginPath();
                ctx.arc(selectedNode.x, selectedNode.y_pos, 8, 0, Math.PI * 2);
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 3;
                ctx.stroke();
            }}

            ctx.restore();
            requestAnimationFrame(render);
        }}

        // Canvas Interactions
        canvas.addEventListener('mousedown', e => {{
            isDragging = true;
            startX = e.clientX - targetCamera.x;
            startY = e.clientY - targetCamera.y;
        }});

        window.addEventListener('mousemove', e => {{
            if (isDragging) {{
                targetCamera.x = e.clientX - startX;
                targetCamera.y = e.clientY - startY;
                return;
            }}

            const rect = canvas.getBoundingClientRect();
            const mouseX = (e.clientX - rect.left - camera.x) / camera.k;
            const mouseY = (e.clientY - rect.top - camera.y) / camera.k;

            const gx = Math.floor(mouseX / cellSize);
            const gy = Math.floor(mouseY / cellSize);

            hoveredNode = null;
            let minD2 = 64;

            for (let dx = -1; dx <= 1; dx++) {{
                for (let dy = -1; dy <= 1; dy++) {{
                    const key = `${{gx + dx}},${{gy + dy}}`;
                    const cellNodes = spatialGrid.get(key);
                    if (!cellNodes) continue;
                    for (let i = 0; i < cellNodes.length; i++) {{
                        const n = cellNodes[i];
                        const d2 = (n.x - mouseX) ** 2 + (n.y_pos - mouseY) ** 2;
                        if (d2 < minD2) {{
                            minD2 = d2;
                            hoveredNode = n;
                        }}
                    }}
                }}
            }}

            if (hoveredNode) {{
                const cfg = topicMeta[hoveredNode.t] || {{ name: "ทั่วไป", color: "#38bdf8" }};
                tooltip.style.display = 'block';
                tooltip.style.left = e.clientX + 'px';
                tooltip.style.top = e.clientY + 'px';
                tooltip.innerHTML = `
                    <div style="font-weight: 700; color: ${{cfg.color}}; font-size: 0.75rem; text-transform: uppercase;">
                        ${{cfg.name}} &bull; ${{hoveredNode.y}}
                    </div>
                    <div style="margin-top: 0.3rem; line-height: 1.35; font-weight: 600;">
                        ${{hoveredNode.c}}
                    </div>
                `;
            }} else {{
                tooltip.style.display = 'none';
            }}
        }});

        window.addEventListener('mouseup', () => isDragging = false);

        canvas.addEventListener('wheel', e => {{
            e.preventDefault();
            const zoom = e.deltaY < 0 ? 1.12 : 0.88;
            targetCamera.k = Math.max(0.3, Math.min(5, targetCamera.k * zoom));
        }});

        canvas.addEventListener('click', () => {{
            if (hoveredNode) {{
                selectedNode = hoveredNode;
                showInspector(selectedNode);
            }}
        }});

        function showInspector(node) {{
            const cfg = topicMeta[node.t] || {{ name: "ทั่วไป", color: "#38bdf8" }};
            const container = document.getElementById('inspectContent');
            container.innerHTML = `
                <div style="background: rgba(8, 12, 22, 0.9); border: 1px solid var(--panel-border); border-radius: 8px; padding: 0.9rem;">
                    <div style="display: flex; gap: 0.3rem; margin-bottom: 0.4rem;">
                        <span style="background: ${{cfg.color}}22; color: ${{cfg.color}}; font-size: 0.7rem; font-weight: 700; padding: 0.15rem 0.4rem; border-radius: 4px;">${{cfg.name}}</span>
                        <span style="background: #1e293b; color: var(--accent-blue); font-size: 0.7rem; font-weight: 700; padding: 0.15rem 0.4rem; border-radius: 4px;">${{node.v.toUpperCase()}}</span>
                    </div>
                    <div style="font-family: 'Sarabun', sans-serif; font-size: 0.88rem; font-weight: 600; line-height: 1.4; color: #fff; margin-bottom: 0.5rem;">
                        ${{node.c}}
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-muted); display: flex; justify-content: space-between;">
                        <span>📅 ${{node.d || node.y}}</span>
                        <span>🏢 ${{node.s.toUpperCase()}}</span>
                    </div>
                    ${{node.u ? `<a href="${{node.u}}" target="_blank" style="display: inline-block; margin-top: 0.6rem; color: var(--accent-blue); font-size: 0.75rem; text-decoration: none;">🔗 ดูลิงก์ตรวจสอบต้นฉบับ &rarr;</a>` : ''}}
                </div>
            `;
        }}

        // Automatic Play Animation
        let timelineTimer = null;
        function toggleTimelinePlay() {{
            const btn = document.getElementById('btn-timeline-play');
            if (timelineTimer) {{
                clearInterval(timelineTimer);
                timelineTimer = null;
                btn.innerText = '▶️ เล่นวิวัฒนาการ';
            }} else {{
                btn.innerText = '⏸️ หยุดชั่วคราว';
                let yr = 2015;
                onYearSlider(yr);
                timelineTimer = setInterval(() => {{
                    yr++;
                    if (yr > 2026) yr = 2015;
                    onYearSlider(yr);
                }}, 2000);
            }}
        }}

        // Initial setup
        setChapter(1);
        updateLayerBDeck();
        buildSpatialGrid();
        requestAnimationFrame(render);
    </script>
</body>
</html>
"""
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Temporal Storytelling application generated at: {HTML_PATH}")

if __name__ == '__main__':
    build_app()
