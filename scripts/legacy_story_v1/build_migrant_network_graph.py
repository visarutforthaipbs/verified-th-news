#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_migrant_network_graph.py
Builds an interactive 2D Network Graph & Temporal Evolution App for Article 2
(869 Migrant & Cross-Border Verified Claims: 2020–2026).
"""

import sys
import json
import math
import random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from th_verify.normalized import get_normalized_records

OUTPUT_PATH = Path("data/reports/article2_migrant_network_graph.html")

def build_graph():
    print("Loading migrant claims for network graph visualization...")
    import re
    records = get_normalized_records("data/th_verify.db", filter_broadcasts=True)
    migrant_rx = re.compile(
        r'ต่างด้าว|แรงงานต่าง|พม่า|กัมพูชา|เขมร|ลาว|เวียดนาม|โรฮิงญา|สัญชาติ|เกาะกูด|mou\s*44|แย่งอาชีพ|แย่งงาน|ข้ามชาติ|ประชากรข้ามชาติ',
        re.IGNORECASE
    )
    
    # Filter migrant records
    migrant_records = [r for r in records if migrant_rx.search(r['claim_clean'])]
    print(f"Loaded {len(migrant_records)} migrant claims.")

    # Narrative clusters and centroids
    clusters = {
        "sovereignty": {
            "name": "สัญชาติ อธิปไตย และเกาะกูด",
            "cx": 180, "cy": -60, "color": "#a855f7", "radius": 140,
            "desc": "วาทกรรมแจกสัญชาติ 4 แสนคน สิทธิเลือกตั้ง MOU 44 และข้อพิพาทเกาะกูด"
        },
        "disease": {
            "name": "โรคระบาด โควิด-19 และสาธารณสุข",
            "cx": -220, "cy": -150, "color": "#ef4444", "radius": 80,
            "desc": "วาทกรรมแรงงานต่างด้าวนำเข้าเชื้อโควิด-19 และแย่งสิทธิการรักษาพยาบาล"
        },
        "economic": {
            "name": "การแย่งอาชีพ เศรษฐกิจ และนอมินี",
            "cx": -160, "cy": 120, "color": "#f59e0b", "radius": 110,
            "desc": "วาทกรรมต่างด้าวยึดตลาด แย่งอาชีพห้ามคนต่างด้าวทำ และเปิดธุรกิจนอมินี"
        },
        "broker": {
            "name": "ขบวนการลักลอบและนายหน้าต้มตุ๋น",
            "cx": 100, "cy": 180, "color": "#0ea5e9", "radius": 90,
            "desc": "ข่าวลวงหลอกทำบัตรประชาชน หลอกข้ามแดน และขบวนการรีดไถค่าหัว"
        },
        "other": {
            "name": "ประเด็นอื่นๆ และความสัมพันธ์ทั่วไป",
            "cx": 0, "cy": 0, "color": "#64748b", "radius": 60,
            "desc": "ข่าวลวงเหตุการณ์ทั่วไปที่เกี่ยวข้องกับบุคคลสัญชาติต่างๆ"
        }
    }

    def categorize(text):
        t = text.lower()
        if any(k in t for k in ['สัญชาติ', 'เลือกตั้ง', 'บัตรประชาชน', 'อธิปไตย', 'เกาะกูด', 'mou', 'ยึดครอง', 'เสียดินแดน', 'สิทธิการเมือง']):
            return 'sovereignty'
        elif any(k in t for k in ['โควิด', 'โรค', 'ระบาด', 'ติดเชื้อ', 'วัคซีน', 'ไข้ป่า', 'สาธารณสุข', 'โอไมครอน']):
            return 'disease'
        elif any(k in t for k in ['แย่งงาน', 'แย่งอาชีพ', 'ค้าขาย', 'ทำงาน', 'นอมินี', 'สิทธิรักษา', 'ประกันสังคม', 'สวัสดิการ']):
            return 'economic'
        elif any(k in t for k in ['นายหน้า', 'หลอกลวง', 'ลักลอบ', 'ค้ามนุษย์', 'ข้ามแดน', 'ขนแรงงาน', 'หนีเข้าเมือง']):
            return 'broker'
        else:
            return 'other'

    # Build nodes with pre-computed cluster coordinates
    nodes = []
    random.seed(42)
    for idx, r in enumerate(migrant_records):
        cid = categorize(r["claim_clean"])
        cl = clusters[cid]
        
        # Gaussian distribution around cluster center
        angle = random.uniform(0, 2 * math.pi)
        dist = random.gauss(0, cl["radius"] * 0.45)
        x = round(cl["cx"] + dist * math.cos(angle), 1)
        y = round(cl["cy"] + dist * math.sin(angle), 1)
        
        try:
            year = int(r.get("published_year") or 2020)
        except (ValueError, TypeError):
            year = 2020
            
        nodes.append({
            "id": r["id"],
            "claim": r["claim_clean"],
            "title": r["title_raw"],
            "source": r["source"],
            "url": r["url"],
            "verdict": r["verdict_normalized"],
            "raw_verdict": r["verdict_raw"],
            "year": year,
            "date": r.get("published_date") or f"{year}-01-01",
            "cluster": cid,
            "color": cl["color"],
            "x": x,
            "y": y
        })

    # Sort nodes by date
    nodes.sort(key=lambda n: n["date"])

    # Compute yearly breakdown for stream chart
    years = sorted(list(set(n["year"] for n in nodes)))
    yearly_stats = {}
    for y in years:
        y_nodes = [n for n in nodes if n["year"] == y]
        yearly_stats[y] = {
            "total": len(y_nodes),
            "sovereignty": sum(1 for n in y_nodes if n["cluster"] == "sovereignty"),
            "disease": sum(1 for n in y_nodes if n["cluster"] == "disease"),
            "economic": sum(1 for n in y_nodes if n["cluster"] == "economic"),
            "broker": sum(1 for n in y_nodes if n["cluster"] == "broker"),
            "other": sum(1 for n in y_nodes if n["cluster"] == "other")
        }

    html_content = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>เครือข่ายข่าวลวงและวาทกรรม 'ประชากรข้ามชาติ' (2563–2569) | ประชาไท & TH Verify</title>
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@400;500;600;700;800&family=Sarabun:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #07090e;
            --panel-bg: rgba(13, 17, 26, 0.95);
            --border: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-orange: #fb923c;
            --sov-color: #a855f7;
            --dis-color: #ef4444;
            --eco-color: #f59e0b;
            --brk-color: #0ea5e9;
            --oth-color: #64748b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Prompt', -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text-main);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}

        /* TOP NAVIGATION */
        header {{
            background: #0d111a;
            border-bottom: 1px solid var(--border);
            padding: 0.75rem 1.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            z-index: 20;
            flex-shrink: 0;
        }}
        .brand-area {{ display: flex; align-items: center; gap: 1rem; }}
        .badge-kicker {{
            background: rgba(251, 146, 60, 0.15);
            color: var(--accent-orange);
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.25rem 0.6rem;
            border-radius: 4px;
            border: 1px solid rgba(251, 146, 60, 0.3);
            text-transform: uppercase;
        }}
        .header-title {{ font-size: 1.1rem; font-weight: 700; color: #fff; }}
        .header-sub {{ font-size: 0.8rem; color: var(--text-muted); }}
        
        .controls-top {{ display: flex; align-items: center; gap: 1rem; }}
        .search-input {{
            background: #161f30;
            border: 1px solid #2d3f5e;
            color: #fff;
            padding: 0.45rem 1rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-family: 'Prompt';
            width: 260px;
            outline: none;
            transition: all 0.2s;
        }}
        .search-input:focus {{
            border-color: var(--accent-orange);
            box-shadow: 0 0 10px rgba(251, 146, 60, 0.25);
            width: 300px;
        }}
        .btn-action {{
            background: #1e293b;
            color: #fff;
            border: 1px solid #334155;
            padding: 0.45rem 0.9rem;
            border-radius: 8px;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            text-decoration: none;
            transition: all 0.2s;
        }}
        .btn-action:hover {{ background: #2d3f5e; border-color: #475569; }}

        /* MAIN STAGE */
        .stage {{
            position: relative;
            flex: 1;
            display: flex;
            overflow: hidden;
        }}
        canvas {{
            width: 100%;
            height: 100%;
            display: block;
            cursor: grab;
        }}
        canvas:active {{ cursor: grabbing; }}

        /* FLOATING SIDEBAR (CLUSTER DIRECTORY & STATS) */
        .sidebar-left {{
            position: absolute;
            top: 1rem;
            left: 1rem;
            width: 320px;
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.2rem;
            backdrop-filter: blur(12px);
            z-index: 10;
            box-shadow: 0 10px 30px rgba(0,0,0,0.6);
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
        }}
        .sidebar-title {{
            font-size: 0.85rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            border-bottom: 1px solid #243044;
            padding-bottom: 0.4rem;
        }}
        .cluster-item {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.5rem 0.7rem;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s;
            border: 1px solid transparent;
        }}
        .cluster-item:hover, .cluster-item.active {{
            background: rgba(255,255,255,0.05);
            border-color: #334155;
        }}
        .cluster-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 0.6rem;
            flex-shrink: 0;
        }}
        .cluster-label {{ font-size: 0.82rem; font-weight: 500; color: #e2e8f0; flex: 1; }}
        .cluster-count {{ font-size: 0.75rem; color: var(--text-muted); font-weight: 600; }}

        /* TIMELINE CONTROLLER (BOTTOM FLOATING) */
        .timeline-bar {{
            position: absolute;
            bottom: 1.2rem;
            left: 50%;
            transform: translateX(-50%);
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 30px;
            padding: 0.6rem 1.5rem;
            backdrop-filter: blur(12px);
            z-index: 10;
            box-shadow: 0 10px 30px rgba(0,0,0,0.6);
            display: flex;
            align-items: center;
            gap: 1.2rem;
        }}
        .btn-play {{
            background: var(--accent-orange);
            color: #000;
            font-weight: 800;
            border: none;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: transform 0.15s;
        }}
        .btn-play:hover {{ transform: scale(1.08); background: #fdba74; }}
        .year-selector {{
            display: flex;
            gap: 0.4rem;
        }}
        .year-pill {{
            padding: 0.35rem 0.75rem;
            border-radius: 16px;
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--text-muted);
            background: rgba(255,255,255,0.04);
            border: 1px solid transparent;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .year-pill:hover {{ color: #fff; background: rgba(255,255,255,0.1); }}
        .year-pill.active {{
            background: #3b82f6;
            color: #fff;
            border-color: #60a5fa;
            box-shadow: 0 0 12px rgba(59, 130, 246, 0.4);
        }}
        .year-pill.all {{ background: #334155; color: #fff; }}

        /* NODE DETAIL DRAWER */
        .detail-drawer {{
            position: absolute;
            top: 1rem;
            right: 1rem;
            width: 360px;
            max-height: calc(100vh - 7rem);
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.4rem;
            backdrop-filter: blur(16px);
            z-index: 10;
            box-shadow: 0 15px 35px rgba(0,0,0,0.7);
            display: none;
            flex-direction: column;
            gap: 0.8rem;
            overflow-y: auto;
        }}
        .drawer-close {{
            position: absolute;
            top: 1rem;
            right: 1rem;
            background: none;
            border: none;
            color: var(--text-muted);
            font-size: 1.2rem;
            cursor: pointer;
        }}
        .badge-verdict {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 700;
            width: fit-content;
        }}
        .badge-false {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
        .badge-misleading {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }}
        .badge-true {{ background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4); }}

        .claim-headline {{ font-size: 1.05rem; font-weight: 700; color: #fff; line-height: 1.4; }}
        .claim-meta {{ font-size: 0.8rem; color: var(--text-muted); display: flex; flex-direction: column; gap: 0.2rem; }}
        .link-source {{
            display: inline-block;
            margin-top: 0.5rem;
            color: #38bdf8;
            font-size: 0.82rem;
            text-decoration: none;
            word-break: break-all;
        }}
        .link-source:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>

    <header>
        <div class="brand-area">
            <span class="badge-kicker">Prachatai & TH Verify</span>
            <div>
                <div class="header-title">โครงข่ายและวิวัฒนาการข่าวลวง 'ประชากรข้ามชาติ' (2563–2569)</div>
                <div class="header-sub">แผนที่ปฏิสัมพันธ์ {len(migrant_records)} ข้อเท็จจริง จำแนกตาม 4 วาทกรรมหลัก</div>
            </div>
        </div>
        <div class="controls-top">
            <input type="text" id="searchInput" class="search-input" placeholder="🔍 ค้นหาคำสำคัญ (เช่น เกาะกูด, สัญชาติ, โควิด)...">
            <a href="datasets/article2_migrant_claims.csv" download class="btn-action">📥 ดาวน์โหลด Dataset (CSV)</a>
            <a href="migrant_deepdive_feature.html" class="btn-action">📰 อ่านบทความสืบสวน</a>
        </div>
    </header>

    <div class="stage">
        <canvas id="graphCanvas"></canvas>

        <!-- LEFT CLUSTER DIRECTORY -->
        <div class="sidebar-left">
            <div class="sidebar-title">กลุ่มวาทกรรมข่าวลวง ({len(migrant_records)} เรื่อง)</div>
            <div class="cluster-item active" onclick="filterCluster('all')">
                <span class="cluster-dot" style="background: #fff;"></span>
                <span class="cluster-label">ทั้งหมดทุกประเด็น</span>
                <span class="cluster-count">{len(migrant_records)}</span>
            </div>
            <div class="cluster-item" onclick="filterCluster('sovereignty')">
                <span class="cluster-dot" style="background: var(--sov-color);"></span>
                <span class="cluster-label">สัญชาติ อธิปไตย & เกาะกูด</span>
                <span class="cluster-count">{sum(1 for n in nodes if n['cluster'] == 'sovereignty')}</span>
            </div>
            <div class="cluster-item" onclick="filterCluster('economic')">
                <span class="cluster-dot" style="background: var(--eco-color);"></span>
                <span class="cluster-label">แย่งอาชีพ เศรษฐกิจ & นอมินี</span>
                <span class="cluster-count">{sum(1 for n in nodes if n['cluster'] == 'economic')}</span>
            </div>
            <div class="cluster-item" onclick="filterCluster('broker')">
                <span class="cluster-dot" style="background: var(--brk-color);"></span>
                <span class="cluster-label">ขบวนการลักลอบ & นายหน้า</span>
                <span class="cluster-count">{sum(1 for n in nodes if n['cluster'] == 'broker')}</span>
            </div>
            <div class="cluster-item" onclick="filterCluster('disease')">
                <span class="cluster-dot" style="background: var(--dis-color);"></span>
                <span class="cluster-label">โรคระบาด & โควิด-19</span>
                <span class="cluster-count">{sum(1 for n in nodes if n['cluster'] == 'disease')}</span>
            </div>
            <div class="cluster-item" onclick="filterCluster('other')">
                <span class="cluster-dot" style="background: var(--oth-color);"></span>
                <span class="cluster-label">ประเด็นอื่นๆ ทั่วไป</span>
                <span class="cluster-count">{sum(1 for n in nodes if n['cluster'] == 'other')}</span>
            </div>
        </div>

        <!-- DETAIL DRAWER -->
        <div class="detail-drawer" id="detailDrawer">
            <button class="drawer-close" onclick="closeDrawer()">✕</button>
            <div id="drawerBadge"></div>
            <div class="claim-headline" id="drawerClaim"></div>
            <div class="claim-meta">
                <div><strong>ผู้ตรวจสอบ:</strong> <span id="drawerSource"></span></div>
                <div><strong>วันที่เผยแพร่:</strong> <span id="drawerDate"></span> (พ.ศ. <span id="drawerBE"></span>)</div>
                <div><strong>หมวดหมู่วาทกรรม:</strong> <span id="drawerCluster"></span></div>
                <div><strong>ข้อความพาดหัวเดิม:</strong> <span id="drawerTitle"></span></div>
            </div>
            <a href="#" target="_blank" class="link-source" id="drawerLink">🔗 เปิดดูรายงานฉบับเต็มของผู้ตรวจสอบ ↗</a>
        </div>

        <!-- BOTTOM TIMELINE -->
        <div class="timeline-bar">
            <button class="btn-play" id="btnPlay" onclick="togglePlay()">▶</button>
            <div class="year-selector" id="yearSelector">
                <div class="year-pill active" onclick="setYear('all')">ทั้งหมด (2563–2569)</div>
                <div class="year-pill" onclick="setYear(2020)">2563</div>
                <div class="year-pill" onclick="setYear(2021)">2564</div>
                <div class="year-pill" onclick="setYear(2022)">2565</div>
                <div class="year-pill" onclick="setYear(2023)">2566</div>
                <div class="year-pill" onclick="setYear(2024)">2567</div>
                <div class="year-pill" onclick="setYear(2025)">2568</div>
                <div class="year-pill" onclick="setYear(2026)">2569</div>
            </div>
        </div>
    </div>

    <script>
        const nodesData = {json.dumps(nodes, ensure_ascii=False)};
        const clustersMeta = {json.dumps(clusters, ensure_ascii=False)};
        const yearlyStats = {json.dumps(yearly_stats, ensure_ascii=False)};

        const canvas = document.getElementById('graphCanvas');
        const ctx = canvas.getContext('2d');

        let width, height;
        let camera = {{ x: 0, y: 0, zoom: 1.4 }};
        let isDragging = false;
        let dragStart = {{ x: 0, y: 0 }};
        let hoveredNode = null;
        let activeCluster = 'all';
        let activeYear = 'all';
        let isPlaying = false;
        let playInterval = null;
        let searchQuery = '';

        function resize() {{
            width = canvas.parentElement.clientWidth;
            height = canvas.parentElement.clientHeight;
            canvas.width = width * window.devicePixelRatio;
            canvas.height = height * window.devicePixelRatio;
            ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
            draw();
        }}
        window.addEventListener('resize', resize);

        function worldToScreen(wx, wy) {{
            return {{
                x: width / 2 + (wx - camera.x) * camera.zoom,
                y: height / 2 + (wy - camera.y) * camera.zoom
            }};
        }}

        function screenToWorld(sx, sy) {{
            return {{
                x: (sx - width / 2) / camera.zoom + camera.x,
                y: (sy - height / 2) / camera.zoom + camera.y
            }};
        }}

        function isVisible(node) {{
            if (activeCluster !== 'all' && node.cluster !== activeCluster) return false;
            if (activeYear !== 'all' && node.year !== activeYear) return false;
            if (searchQuery) {{
                const q = searchQuery.toLowerCase();
                return node.claim.toLowerCase().includes(q) || node.title.toLowerCase().includes(q);
            }}
            return true;
        }}

        function draw() {{
            ctx.fillStyle = '#07090e';
            ctx.fillRect(0, 0, width, height);

            // Draw cluster halos and boundary names
            for (const [key, cl] of Object.entries(clustersMeta)) {{
                if (activeCluster !== 'all' && activeCluster !== key) continue;
                const p = worldToScreen(cl.cx, cl.cy);
                const r = cl.radius * camera.zoom;

                // Subtle halo
                const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * 1.5);
                grad.addColorStop(0, cl.color + '22');
                grad.addColorStop(0.7, cl.color + '08');
                grad.addColorStop(1, 'transparent');
                ctx.fillStyle = grad;
                ctx.beginPath();
                ctx.arc(p.x, p.y, r * 1.5, 0, Math.PI * 2);
                ctx.fill();

                // Cluster title
                ctx.font = '600 11px Prompt, sans-serif';
                ctx.fillStyle = cl.color + 'aa';
                ctx.textAlign = 'center';
                ctx.fillText(cl.name.toUpperCase(), p.x, p.y - r * 0.9);
            }}

            // Draw links between nearby nodes in same cluster (Subtle web)
            ctx.lineWidth = 0.5;
            for (let i = 0; i < nodesData.length; i += 4) {{
                const n1 = nodesData[i];
                if (!isVisible(n1)) continue;
                for (let j = i + 1; j < Math.min(i + 5, nodesData.length); j++) {{
                    const n2 = nodesData[j];
                    if (!isVisible(n2) || n1.cluster !== n2.cluster) continue;
                    const dx = n1.x - n2.x;
                    const dy = n1.y - n2.y;
                    if (dx*dx + dy*dy < 1200) {{
                        const p1 = worldToScreen(n1.x, n1.y);
                        const p2 = worldToScreen(n2.x, n2.y);
                        ctx.strokeStyle = n1.color + '22';
                        ctx.beginPath();
                        ctx.moveTo(p1.x, p1.y);
                        ctx.lineTo(p2.x, p2.y);
                        ctx.stroke();
                    }}
                }}
            }}

            // Draw nodes
            for (const node of nodesData) {{
                const visible = isVisible(node);
                const p = worldToScreen(node.x, node.y);
                const isHover = (hoveredNode && hoveredNode.id === node.id);

                if (!visible) {{
                    // Render faintly if inactive
                    ctx.fillStyle = '#1e293b22';
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, 2 * camera.zoom, 0, Math.PI * 2);
                    ctx.fill();
                    continue;
                }}

                // Active node
                const radius = isHover ? 7 : 4;
                ctx.fillStyle = isHover ? '#fff' : node.color;
                ctx.shadowColor = node.color;
                ctx.shadowBlur = isHover ? 16 : 6;
                ctx.beginPath();
                ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
                ctx.fill();
                ctx.shadowBlur = 0;

                // Tooltip on hover
                if (isHover) {{
                    ctx.font = '500 12px Prompt, sans-serif';
                    ctx.fillStyle = '#fff';
                    ctx.textAlign = 'left';
                    const text = node.claim.length > 45 ? node.claim.substring(0, 45) + '...' : node.claim;
                    const tw = ctx.measureText(text).width;
                    
                    ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
                    ctx.strokeStyle = node.color;
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.roundRect(p.x + 12, p.y - 18, tw + 16, 28, 6);
                    ctx.fill();
                    ctx.stroke();

                    ctx.fillStyle = '#f8fafc';
                    ctx.fillText(text, p.x + 20, p.y + 1);
                }}
            }}
        }}

        // Canvas interactions
        canvas.addEventListener('mousedown', e => {{
            isDragging = true;
            dragStart = {{ x: e.clientX, y: e.clientY }};
        }});

        window.addEventListener('mousemove', e => {{
            if (isDragging) {{
                const dx = (e.clientX - dragStart.x) / camera.zoom;
                const dy = (e.clientY - dragStart.y) / camera.zoom;
                camera.x -= dx;
                camera.y -= dy;
                dragStart = {{ x: e.clientX, y: e.clientY }};
                draw();
            }} else {{
                // Hit testing
                const rect = canvas.getBoundingClientRect();
                const mx = e.clientX - rect.left;
                const my = e.clientY - rect.top;
                const worldM = screenToWorld(mx, my);

                let found = null;
                for (const node of nodesData) {{
                    if (!isVisible(node)) continue;
                    const dx = node.x - worldM.x;
                    const dy = node.y - worldM.y;
                    if (dx*dx + dy*dy < 40) {{
                        found = node;
                        break;
                    }}
                }}
                if (found !== hoveredNode) {{
                    hoveredNode = found;
                    draw();
                }}
            }}
        }});

        window.addEventListener('mouseup', () => isDragging = false);

        canvas.addEventListener('wheel', e => {{
            e.preventDefault();
            const zoomFactor = e.deltaY < 0 ? 1.12 : 0.89;
            camera.zoom = Math.max(0.6, Math.min(camera.zoom * zoomFactor, 3.5));
            draw();
        }});

        canvas.addEventListener('click', e => {{
            if (hoveredNode) {{
                showDrawer(hoveredNode);
            }}
        }});

        function showDrawer(node) {{
            const drawer = document.getElementById('detailDrawer');
            document.getElementById('drawerClaim').innerText = node.claim;
            document.getElementById('drawerTitle').innerText = node.title;
            document.getElementById('drawerSource').innerText = node.source.toUpperCase();
            document.getElementById('drawerDate').innerText = node.date;
            document.getElementById('drawerBE').innerText = node.year + 543;
            document.getElementById('drawerCluster').innerText = clustersMeta[node.cluster].name;
            document.getElementById('drawerLink').href = node.url;

            const badge = document.getElementById('drawerBadge');
            const v = node.verdict.toLowerCase();
            let vClass = 'badge-false';
            let vText = 'ข้อความเท็จ (False)';
            if (v === 'true') {{ vClass = 'badge-true'; vText = 'ข้อความจริง (True)'; }}
            else if (v === 'misleading') {{ vClass = 'badge-misleading'; vText = 'ข้อมูลบิดเบือน (Misleading)'; }}
            badge.className = 'badge-verdict ' + vClass;
            badge.innerText = vText;

            drawer.style.display = 'flex';
        }}

        function closeDrawer() {{
            document.getElementById('detailDrawer').style.display = 'none';
        }}

        function filterCluster(cid) {{
            activeCluster = cid;
            document.querySelectorAll('.cluster-item').forEach(el => el.classList.remove('active'));
            event.currentTarget.classList.add('active');
            draw();
        }}

        function setYear(yr) {{
            activeYear = yr;
            document.querySelectorAll('.year-pill').forEach(el => el.classList.remove('active'));
            event.currentTarget.classList.add('active');
            draw();
        }}

        function togglePlay() {{
            const btn = document.getElementById('btnPlay');
            if (isPlaying) {{
                clearInterval(playInterval);
                isPlaying = false;
                btn.innerText = '▶';
            }} else {{
                isPlaying = true;
                btn.innerText = '⏸';
                const yrs = [2020, 2021, 2022, 2023, 2024, 2025, 2026];
                let idx = 0;
                playInterval = setInterval(() => {{
                    const curYr = yrs[idx];
                    activeYear = curYr;
                    const pills = document.querySelectorAll('.year-pill');
                    pills.forEach(p => p.classList.remove('active'));
                    if (pills[idx + 1]) pills[idx + 1].classList.add('active');
                    draw();
                    idx++;
                    if (idx >= yrs.length) {{
                        clearInterval(playInterval);
                        isPlaying = false;
                        btn.innerText = '▶';
                    }}
                }}, 1500);
            }}
        }}

        document.getElementById('searchInput').addEventListener('input', e => {{
            searchQuery = e.target.value;
            draw();
        }});

        resize();
    </script>
</body>
</html>
"""
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Migrant network graph successfully created at: {OUTPUT_PATH}")

if __name__ == "__main__":
    build_graph()
