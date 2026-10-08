#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_3d_network_graph.py
Generates an interactive 3D WebGL Misinformation Galaxy for Article 1
(27,231 verified claim nodes across 11 years: 2015–2026).
Supports 3D Temporal Tower, 3D Spherical Galaxy, and 3D Temporal Helix layouts,
with OrbitControls, Raycasting, Real-time search, and 11-Year timeline playback.
"""

import sys
import json
import math
import random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from th_verify.normalized import get_normalized_records

OUTPUT_PATH = Path("data/reports/article1_11years_network_graph.html")

def build_3d_graph():
    print("Loading clean atomic claims for 3D network visualization...")
    records = get_normalized_records("data/th_verify.db", filter_broadcasts=True)
    total_records = len(records)
    print(f"Loaded {total_records} atomic records.")

    # 10 Macro Topics configuration with 3D centroids & colors
    topics = {
        "T01": {"name": "สุขภาพ อาหาร และยา", "color": "#10b981", "cx": -220, "cy": -60, "cz": 80, "rad": 110},
        "T02": {"name": "โควิด-19 และวัคซีน", "color": "#f43f5e", "cx": -180, "cy": -180, "cz": -40, "rad": 75},
        "T03": {"name": "สินเชื่อปลอม & คอลเซ็นเตอร์", "color": "#f59e0b", "cx": 200, "cy": -100, "cz": 100, "rad": 90},
        "T04": {"name": "หลอกลงทุนหุ้น & SET", "color": "#eab308", "cx": 220, "cy": 80, "cz": -80, "rad": 80},
        "T05": {"name": "นโยบายรัฐ & สวัสดิการ", "color": "#38bdf8", "cx": -60, "cy": 180, "cz": 50, "rad": 65},
        "T06": {"name": "แรงงานต่างด้าว & สัญชาติ", "color": "#a855f7", "cx": 120, "cy": 180, "cz": 120, "rad": 70},
        "T07": {"name": "AI Deepfake & สื่อตัดต่อ", "color": "#ec4899", "cx": 80, "cy": -200, "cz": -100, "rad": 60},
        "T08": {"name": "ภัยพิบัติ & สภาพอากาศ", "color": "#06b6d4", "cx": -180, "cy": 120, "cz": -120, "rad": 65},
        "T09": {"name": "การเมือง & การเลือกตั้ง", "color": "#ef4444", "cx": 0, "cy": 220, "cz": -50, "rad": 65},
        "T10": {"name": "ความมั่นคง & ภูมิรัฐศาสตร์", "color": "#6366f1", "cx": 100, "cy": 60, "cz": -180, "rad": 60},
        "T99_other": {"name": "ประเด็นอื่นๆ ทั่วไป", "color": "#64748b", "cx": 0, "cy": 0, "cz": 0, "rad": 130}
    }

    # Precompute compact node objects
    nodes = []
    random.seed(42)

    for r in records:
        tid = r.get("topic_id") or "T99_other"
        if tid not in topics:
            tid = "T99_other"
        tc = topics[tid]

        try:
            year = int(r.get("published_year") or 2020)
        except (ValueError, TypeError):
            year = 2020

        # Mode 1: Volumetric Galaxy dispersion (Gaussian in 3D)
        # Random spherical coords
        u = random.random()
        v = random.random()
        theta = u * 2.0 * math.pi
        phi = math.acos(2.0 * v - 1.0)
        dist = random.gauss(0, tc["rad"] * 0.45)
        
        gx = round(tc["cx"] + dist * math.sin(phi) * math.cos(theta), 1)
        gy = round(tc["cy"] + dist * math.sin(phi) * math.sin(theta), 1)
        gz = round(tc["cz"] + dist * math.cos(phi), 1)

        # Mode 2: Temporal Tower (Z = time, X,Y = semantic cluster)
        # Year maps from 2015 (-250) to 2026 (+250)
        year_frac = (year - 2015) / 11.0
        tz = round(-260 + year_frac * 520 + random.gauss(0, 10), 1)
        # Small planar jitter in X, Y
        jitter_r = random.gauss(0, tc["rad"] * 0.35)
        jitter_a = random.uniform(0, 2 * math.pi)
        tx = round(tc["cx"] + jitter_r * math.cos(jitter_a), 1)
        ty = round(tc["cy"] + jitter_r * math.sin(jitter_a), 1)

        # Mode 3: Temporal Helix (DNA Spiral: X, Y rotate with time, Z climbs)
        helix_angle = year_frac * 4.0 * math.pi + random.uniform(-0.3, 0.3)
        helix_r = 180 + random.gauss(0, 30)
        hx = round(helix_r * math.cos(helix_angle), 1)
        hy = round(helix_r * math.sin(helix_angle), 1)
        hz = round(-260 + year_frac * 520 + random.gauss(0, 8), 1)

        nodes.append({
            "i": r["id"],
            "c": r["claim_clean"][:140],
            "t": r["title_raw"][:120],
            "s": r["source"],
            "y": year,
            "d": r.get("published_date") or f"{year}-01-01",
            "v": r["verdict_normalized"],
            "k": tid,
            "u": r["url"],
            "gx": gx, "gy": gy, "gz": gz,
            "tx": tx, "ty": ty, "tz": tz,
            "hx": hx, "hy": hy, "hz": hz
        })

    # Sort nodes by year and date
    nodes.sort(key=lambda n: n["d"])

    # Topic summary counts
    topic_stats = {}
    for tid, meta in topics.items():
        count = sum(1 for n in nodes if n["k"] == tid)
        topic_stats[tid] = {
            "name": meta["name"],
            "color": meta["color"],
            "count": count,
            "pct": round(count / total_records * 100, 1)
        }

    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3D Misinformation Universe: 11 Years of Thai Fact-Checking (2015–2026)</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700;800&family=Sarabun:wght@300;400;500;600&display=swap" rel="stylesheet">
    <!-- Three.js + OrbitControls -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <style>
        :root {{
            --bg-color: #04060a;
            --panel-bg: rgba(10, 15, 26, 0.88);
            --border: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #38bdf8;
            --accent-orange: #fb923c;
            --accent-purple: #a855f7;
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

        /* ── Top Header Bar ──────────────────────────────────────────────── */
        header {{
            height: 60px;
            background: #080d1a;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 1.5rem;
            z-index: 50;
            flex-shrink: 0;
        }}
        .brand-zone {{
            display: flex;
            align-items: center;
            gap: 0.9rem;
        }}
        .brand-pill {{
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent-blue);
            border: 1px solid rgba(56, 189, 248, 0.3);
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            text-transform: uppercase;
        }}
        .header-title {{ font-size: 1.05rem; font-weight: 700; color: #fff; }}
        .header-sub {{ font-size: 0.78rem; color: var(--text-muted); }}

        .header-controls {{
            display: flex;
            align-items: center;
            gap: 0.8rem;
        }}
        .search-box {{
            background: #111827;
            border: 1px solid #374151;
            color: #fff;
            padding: 0.4rem 1rem;
            border-radius: 20px;
            font-size: 0.82rem;
            font-family: 'Prompt';
            width: 240px;
            outline: none;
            transition: all 0.2s;
        }}
        .search-box:focus {{
            border-color: var(--accent-blue);
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.3);
            width: 280px;
        }}
        .btn-top {{
            background: #1e293b;
            color: #e2e8f0;
            border: 1px solid #334155;
            padding: 0.4rem 0.8rem;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            transition: all 0.15s;
        }}
        .btn-top:hover {{ background: #334155; color: #fff; }}

        /* ── Main Stage Area ─────────────────────────────────────────────── */
        .stage-container {{
            position: relative;
            flex: 1;
            width: 100%;
            height: 100%;
            overflow: hidden;
        }}
        #webglCanvas {{
            width: 100%;
            height: 100%;
            display: block;
        }}

        /* ── Floating Left Sidebar: 3D Layout Switcher & Topic Directory ─── */
        .sidebar-panel {{
            position: absolute;
            top: 1rem;
            left: 1rem;
            width: 310px;
            max-height: calc(100vh - 140px);
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.1rem;
            backdrop-filter: blur(16px);
            z-index: 20;
            box-shadow: 0 15px 35px rgba(0,0,0,0.6);
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
            overflow-y: auto;
        }}
        .panel-heading {{
            font-size: 0.8rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            border-bottom: 1px solid #1e293b;
            padding-bottom: 0.4rem;
        }}
        .layout-switch-group {{
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
        }}
        .layout-btn {{
            background: rgba(255,255,255,0.04);
            border: 1px solid transparent;
            color: #cbd5e1;
            padding: 0.45rem 0.75rem;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            text-align: left;
            cursor: pointer;
            transition: all 0.15s;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .layout-btn:hover {{ background: rgba(255,255,255,0.08); color: #fff; }}
        .layout-btn.active {{
            background: rgba(56, 189, 248, 0.15);
            border-color: rgba(56, 189, 248, 0.4);
            color: var(--accent-blue);
        }}

        .topic-list {{
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }}
        .topic-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.35rem 0.6rem;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.78rem;
            transition: all 0.15s;
        }}
        .topic-row:hover, .topic-row.active {{
            background: rgba(255,255,255,0.07);
        }}
        .topic-left {{ display: flex; align-items: center; gap: 0.5rem; overflow: hidden; }}
        .topic-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
        .topic-name {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #e2e8f0; }}
        .topic-num {{ font-size: 0.72rem; color: var(--text-muted); }}

        /* ── Camera View Presets (Top Right) ─────────────────────────────── */
        .camera-presets {{
            position: absolute;
            top: 1rem;
            right: 1rem;
            display: flex;
            gap: 0.4rem;
            z-index: 20;
            background: var(--panel-bg);
            border: 1px solid var(--border);
            padding: 0.35rem;
            border-radius: 8px;
            backdrop-filter: blur(12px);
        }}
        .cam-btn {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 0.78rem;
            font-weight: 600;
            padding: 0.35rem 0.65rem;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .cam-btn:hover {{ color: #fff; background: rgba(255,255,255,0.06); }}
        .cam-btn.active {{ background: #1e293b; color: #fff; }}

        /* ── 3D Timeline Scrubber (Bottom Center) ────────────────────────── */
        .bottom-timeline {{
            position: absolute;
            bottom: 1.2rem;
            left: 50%;
            transform: translateX(-50%);
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 30px;
            padding: 0.55rem 1.4rem;
            backdrop-filter: blur(16px);
            z-index: 20;
            box-shadow: 0 10px 30px rgba(0,0,0,0.7);
            display: flex;
            align-items: center;
            gap: 1.1rem;
        }}
        .btn-playback {{
            background: var(--accent-blue);
            color: #04060a;
            border: none;
            width: 34px;
            height: 34px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 0.9rem;
            cursor: pointer;
            transition: transform 0.15s;
        }}
        .btn-playback:hover {{ transform: scale(1.08); background: #7dd3fc; }}
        .year-chips {{ display: flex; gap: 0.25rem; }}
        .year-chip {{
            padding: 0.25rem 0.55rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-muted);
            background: rgba(255,255,255,0.03);
            cursor: pointer;
            transition: all 0.15s;
        }}
        .year-chip:hover {{ color: #fff; background: rgba(255,255,255,0.1); }}
        .year-chip.active {{
            background: #2563eb;
            color: #fff;
            box-shadow: 0 0 10px rgba(37, 99, 235, 0.5);
        }}

        /* ── 3D Node Tooltip (Floating HUD) ──────────────────────────────── */
        .node-tooltip {{
            position: absolute;
            pointer-events: none;
            background: rgba(15, 23, 42, 0.94);
            border: 1px solid var(--accent-blue);
            border-radius: 8px;
            padding: 0.7rem 1rem;
            max-width: 320px;
            font-size: 0.8rem;
            color: #fff;
            box-shadow: 0 8px 25px rgba(0,0,0,0.8);
            display: none;
            z-index: 40;
            backdrop-filter: blur(8px);
        }}
        .tooltip-badge {{
            font-size: 0.68rem;
            font-weight: 700;
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
            display: inline-block;
            margin-bottom: 0.35rem;
        }}

        /* ── Side Inspector Drawer ───────────────────────────────────────── */
        .side-drawer {{
            position: absolute;
            top: 4.5rem;
            right: 1rem;
            width: 360px;
            max-height: calc(100vh - 7.5rem);
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.4rem;
            backdrop-filter: blur(20px);
            z-index: 30;
            box-shadow: 0 20px 40px rgba(0,0,0,0.8);
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
        .claim-text {{ font-size: 1.05rem; font-weight: 700; color: #fff; line-height: 1.4; }}
        .claim-meta {{ font-size: 0.8rem; color: var(--text-muted); display: flex; flex-direction: column; gap: 0.3rem; }}
        .source-link {{
            color: var(--accent-blue);
            font-size: 0.82rem;
            text-decoration: none;
            word-break: break-all;
        }}
        .source-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>

    <header>
        <div class="brand-zone">
            <span class="brand-pill">3D WebGL Engine</span>
            <div>
                <div class="header-title">จักรวาลข่าวลวง 11 ปี สังคมไทย (3D Misinformation Universe)</div>
                <div class="header-sub">{total_records:,} โหนดข้อเท็จจริง &bull; 10 กลุ่มหัวข้อ &bull; พ.ศ. 2558 – 2569</div>
            </div>
        </div>
        <div class="header-controls">
            <input type="text" id="searchBox" class="search-box" placeholder="🔍 ค้นหาข้ออ้าง (เช่น มะนาว, ออมสิน, AI)...">
            <a href="temporal_story_app.html" class="btn-top">🗺️ สลับไปมุมมอง 2D Storytelling</a>
            <a href="datasets/article1_11years_claims.csv" download class="btn-top">📥 ดาวน์โหลด Dataset (CSV)</a>
            <a href="investigative_11years_feature.html" class="btn-top">📰 อ่านบทความสืบสวน</a>
        </div>
    </header>

    <div class="stage-container">
        <div id="webglContainer" style="width: 100%; height: 100%;"></div>

        <!-- CAMERA PRESETS -->
        <div class="camera-presets">
            <button class="cam-btn active" onclick="setCameraView('iso')">👁️ 3D ไอโซเมตริก</button>
            <button class="cam-btn" onclick="setCameraView('side')">⏱️ วิวัฒนาการ 11 ปี (ด้านข้าง)</button>
            <button class="cam-btn" onclick="setCameraView('top')">🌌 ด้านบน (กาแล็กซี)</button>
            <button class="cam-btn" id="btnAutoRotate" onclick="toggleAutoRotate()">🔄 หมุนอัตโนมัติ: เปิด</button>
        </div>

        <!-- LEFT SIDEBAR: 3D LAYOUT SWITCH & TOPICS -->
        <div class="sidebar-panel">
            <div class="panel-heading">มิติการจัดวาง 3D (Spatial Layout)</div>
            <div class="layout-switch-group">
                <button class="layout-btn active" id="btnLayoutTower" onclick="setLayout('tower')">
                    <span>🏛️</span> หอคอยกาลเวลา 3D (Z = กาลเวลา 11 ปี)
                </button>
                <button class="layout-btn" id="btnLayoutGalaxy" onclick="setLayout('galaxy')">
                    <span>🌌</span> เนบิวลาดาราจักร 3D (3D Cluster Nebula)
                </button>
                <button class="layout-btn" id="btnLayoutHelix" onclick="setLayout('helix')">
                    <span>🧬</span> เกลียวคลื่นวิวัฒนาการ 3D (Temporal Helix)
                </button>
            </div>

            <div class="panel-heading" style="margin-top: 0.5rem;">กลุ่มหัวข้อข่าวลวง ({total_records:,} เรื่อง)</div>
            <div class="topic-list">
                <div class="topic-row active" onclick="filterTopic('all')">
                    <div class="topic-left">
                        <span class="topic-dot" style="background: #fff;"></span>
                        <span class="topic-name">ทั้งหมดทุกหัวข้อ</span>
                    </div>
                    <span class="topic-num">{total_records:,}</span>
                </div>
                {"".join([f'''
                <div class="topic-row" onclick="filterTopic('{tid}')">
                    <div class="topic-left">
                        <span class="topic-dot" style="background: {m['color']};"></span>
                        <span class="topic-name">{m['name']}</span>
                    </div>
                    <span class="topic-num">{m['count']:,} ({m['pct']}%)</span>
                </div>
                ''' for tid, m in topic_stats.items()])}
            </div>
        </div>

        <!-- 3D FLOATING TOOLTIP -->
        <div class="node-tooltip" id="nodeTooltip">
            <div class="tooltip-badge" id="ttBadge"></div>
            <div style="font-weight: 700; margin-bottom: 0.2rem;" id="ttClaim"></div>
            <div style="font-size: 0.72rem; color: #94a3b8;" id="ttMeta"></div>
        </div>

        <!-- SIDE INSPECTOR DRAWER -->
        <div class="side-drawer" id="sideDrawer">
            <button class="drawer-close" onclick="closeDrawer()">✕</button>
            <div id="drawerBadge" style="width: fit-content;"></div>
            <div class="claim-text" id="drawerClaim"></div>
            <div class="claim-meta">
                <div><strong>ผู้ตรวจสอบ:</strong> <span id="drawerSource"></span></div>
                <div><strong>วันที่เผยแพร่:</strong> <span id="drawerDate"></span> (พ.ศ. <span id="drawerBE"></span>)</div>
                <div><strong>หมวดหมู่หัวข้อ:</strong> <span id="drawerTopic"></span></div>
                <div><strong>พาดหัวข่าวเดิม:</strong> <span id="drawerTitle"></span></div>
            </div>
            <a href="#" target="_blank" class="source-link" id="drawerUrl">🔗 เปิดดูรายงานฉบับเต็มของผู้ตรวจสอบ ↗</a>
        </div>

        <!-- BOTTOM TIMELINE -->
        <div class="bottom-timeline">
            <button class="btn-playback" id="btnPlay" onclick="togglePlay()">▶</button>
            <div class="year-chips" id="yearChips">
                <div class="year-chip active" onclick="setYear('all')">ทั้งหมด (2558–2569)</div>
                {"".join([f'''<div class="year-chip" onclick="setYear({y})">{y+543}</div>''' for y in range(2015, 2027)])}
            </div>
        </div>
    </div>

    <script>
        const rawNodes = {json.dumps(nodes, ensure_ascii=False)};
        const topicsMeta = {json.dumps(topics, ensure_ascii=False)};
        const totalNodes = rawNodes.length;

        const container = document.getElementById('webglContainer');
        let width = container.clientWidth;
        let height = container.clientHeight;

        // Scene, Camera, Renderer
        const scene = new THREE.Scene();
        scene.fog = new THREE.FogExp2(0x04060a, 0.0012);

        const camera = new THREE.PerspectiveCamera(45, width / height, 1, 3000);
        camera.position.set(0, -320, 500);

        const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: false }});
        renderer.setSize(width, height);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setClearColor(0x04060a, 1);
        container.appendChild(renderer.domElement);

        // OrbitControls
        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.autoRotate = true;
        controls.autoRotateSpeed = 0.6;
        controls.maxDistance = 1400;
        controls.minDistance = 50;

        // Circular particle sprite via 2D Canvas
        function createParticleTexture() {{
            const canvas = document.createElement('canvas');
            canvas.width = 64;
            canvas.height = 64;
            const ctx = canvas.getContext('2d');
            const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
            grad.addColorStop(0, 'rgba(255, 255, 255, 1)');
            grad.addColorStop(0.3, 'rgba(255, 255, 255, 0.85)');
            grad.addColorStop(0.7, 'rgba(255, 255, 255, 0.2)');
            grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, 64, 64);
            const tex = new THREE.Texture(canvas);
            tex.needsUpdate = true;
            return tex;
        }}

        // Buffer Geometry setup
        const geometry = new THREE.BufferGeometry();
        const positions = new Float32Array(totalNodes * 3);
        const targetPositions = new Float32Array(totalNodes * 3);
        const currentPositions = new Float32Array(totalNodes * 3);
        const colors = new Float32Array(totalNodes * 3);
        const baseColors = new Float32Array(totalNodes * 3);

        // Hex to RGB
        function hexToRgb(hex) {{
            const bigint = parseInt(hex.replace('#', ''), 16);
            return [((bigint >> 16) & 255) / 255, ((bigint >> 8) & 255) / 255, (bigint & 255) / 255];
        }}

        // Initialize positions in Tower mode
        for (let i = 0; i < totalNodes; i++) {{
            const n = rawNodes[i];
            const rgb = hexToRgb(topicsMeta[n.k].color);

            // Start at Tower coords
            positions[i * 3] = n.tx;
            positions[i * 3 + 1] = n.ty;
            positions[i * 3 + 2] = n.tz;

            currentPositions[i * 3] = n.tx;
            currentPositions[i * 3 + 1] = n.ty;
            currentPositions[i * 3 + 2] = n.tz;

            targetPositions[i * 3] = n.tx;
            targetPositions[i * 3 + 1] = n.ty;
            targetPositions[i * 3 + 2] = n.tz;

            colors[i * 3] = rgb[0];
            colors[i * 3 + 1] = rgb[1];
            colors[i * 3 + 2] = rgb[2];

            baseColors[i * 3] = rgb[0];
            baseColors[i * 3 + 1] = rgb[1];
            baseColors[i * 3 + 2] = rgb[2];
        }}

        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const material = new THREE.PointsMaterial({{
            size: 6.5,
            vertexColors: true,
            map: createParticleTexture(),
            transparent: true,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        }});

        const particleSystem = new THREE.Points(geometry, material);
        scene.add(particleSystem);

        // Background Starfield Grid
        const gridHelper = new THREE.GridHelper(700, 20, 0x1e293b, 0x0f172a);
        gridHelper.rotation.x = Math.PI / 2;
        gridHelper.position.z = -280;
        scene.add(gridHelper);

        // State
        let activeLayout = 'tower';
        let activeTopic = 'all';
        let activeYear = 'all';
        let searchQuery = '';
        let isTransitioning = false;
        let transitionProgress = 1.0;
        let isPlaying = false;
        let playTimer = null;

        function setLayout(mode) {{
            activeLayout = mode;
            document.querySelectorAll('.layout-btn').forEach(b => b.classList.remove('active'));
            if (mode === 'tower') document.getElementById('btnLayoutTower').classList.add('active');
            else if (mode === 'galaxy') document.getElementById('btnLayoutGalaxy').classList.add('active');
            else if (mode === 'helix') document.getElementById('btnLayoutHelix').classList.add('active');

            // Set targets
            for (let i = 0; i < totalNodes; i++) {{
                const n = rawNodes[i];
                if (mode === 'tower') {{
                    targetPositions[i * 3] = n.tx;
                    targetPositions[i * 3 + 1] = n.ty;
                    targetPositions[i * 3 + 2] = n.tz;
                }} else if (mode === 'galaxy') {{
                    targetPositions[i * 3] = n.gx;
                    targetPositions[i * 3 + 1] = n.gy;
                    targetPositions[i * 3 + 2] = n.gz;
                }} else if (mode === 'helix') {{
                    targetPositions[i * 3] = n.hx;
                    targetPositions[i * 3 + 1] = n.hy;
                    targetPositions[i * 3 + 2] = n.hz;
                }}
            }}
            transitionProgress = 0;
            isTransitioning = true;
        }}

        function setCameraView(view) {{
            document.querySelectorAll('.cam-btn').forEach(b => b.classList.remove('active'));
            event.currentTarget.classList.add('active');
            controls.autoRotate = false;
            document.getElementById('btnAutoRotate').innerText = '🔄 หมุนอัตโนมัติ: ปิด';

            if (view === 'iso') {{
                camera.position.set(240, -320, 420);
                controls.target.set(0, 0, 0);
            }} else if (view === 'side') {{
                camera.position.set(550, 0, 0);
                controls.target.set(0, 0, 0);
            }} else if (view === 'top') {{
                camera.position.set(0, 0, 600);
                controls.target.set(0, 0, 0);
            }}
        }}

        function toggleAutoRotate() {{
            controls.autoRotate = !controls.autoRotate;
            const btn = document.getElementById('btnAutoRotate');
            btn.innerText = controls.autoRotate ? '🔄 หมุนอัตโนมัติ: เปิด' : '🔄 หมุนอัตโนมัติ: ปิด';
            if (controls.autoRotate) btn.classList.add('active');
            else btn.classList.remove('active');
        }}

        function updateNodeVisibility() {{
            const colAttr = geometry.attributes.color;
            const q = searchQuery.toLowerCase();

            for (let i = 0; i < totalNodes; i++) {{
                const n = rawNodes[i];
                let visible = true;

                if (activeTopic !== 'all' && n.k !== activeTopic) visible = false;
                if (activeYear !== 'all' && n.y !== activeYear) visible = false;
                if (q && !n.c.toLowerCase().includes(q) && !n.t.toLowerCase().includes(q)) visible = false;

                if (visible) {{
                    if (q) {{
                        // Bright highlight on search
                        colAttr.array[i * 3] = 1.0;
                        colAttr.array[i * 3 + 1] = 1.0;
                        colAttr.array[i * 3 + 2] = 1.0;
                    }} else {{
                        colAttr.array[i * 3] = baseColors[i * 3];
                        colAttr.array[i * 3 + 1] = baseColors[i * 3 + 1];
                        colAttr.array[i * 3 + 2] = baseColors[i * 3 + 2];
                    }}
                }} else {{
                    // Dim inactive nodes
                    colAttr.array[i * 3] = 0.05;
                    colAttr.array[i * 3 + 1] = 0.08;
                    colAttr.array[i * 3 + 2] = 0.12;
                }}
            }}
            colAttr.needsUpdate = true;
        }}

        function filterTopic(tid) {{
            activeTopic = tid;
            document.querySelectorAll('.topic-row').forEach(r => r.classList.remove('active'));
            event.currentTarget.classList.add('active');
            updateNodeVisibility();
        }}

        function setYear(yr) {{
            activeYear = yr;
            document.querySelectorAll('.year-chip').forEach(c => c.classList.remove('active'));
            event.currentTarget.classList.add('active');
            updateNodeVisibility();
        }}

        function togglePlay() {{
            const btn = document.getElementById('btnPlay');
            if (isPlaying) {{
                clearInterval(playTimer);
                isPlaying = false;
                btn.innerText = '▶';
            }} else {{
                isPlaying = true;
                btn.innerText = '⏸';
                const yrs = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026];
                let idx = 0;
                playTimer = setInterval(() => {{
                    activeYear = yrs[idx];
                    const chips = document.querySelectorAll('.year-chip');
                    chips.forEach(c => c.classList.remove('active'));
                    if (chips[idx + 1]) chips[idx + 1].classList.add('active');
                    updateNodeVisibility();
                    idx++;
                    if (idx >= yrs.length) {{
                        clearInterval(playTimer);
                        isPlaying = false;
                        btn.innerText = '▶';
                    }}
                }}, 1300);
            }}
        }}

        // Raycasting for Hover & Click
        const raycaster = new THREE.Raycaster();
        raycaster.params.Points.threshold = 4.5;
        const mouse = new THREE.Vector2();
        let hoveredIdx = null;

        const tooltip = document.getElementById('nodeTooltip');

        window.addEventListener('mousemove', e => {{
            const rect = renderer.domElement.getBoundingClientRect();
            mouse.x = ((e.clientX - rect.left) / width) * 2 - 1;
            mouse.y = -((e.clientY - rect.top) / height) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObject(particleSystem);

            if (intersects.length > 0) {{
                hoveredIdx = intersects[0].index;
                const n = rawNodes[hoveredIdx];

                tooltip.style.display = 'block';
                tooltip.style.left = (e.clientX + 14) + 'px';
                tooltip.style.top = (e.clientY + 14) + 'px';

                document.getElementById('ttClaim').innerText = n.c;
                document.getElementById('ttMeta').innerText = `พ.ศ. ${{n.y + 543}} • ${{n.s.toUpperCase()}} • ${{topicsMeta[n.k].name}}`;

                const badge = document.getElementById('ttBadge');
                badge.innerText = n.v === 'false' ? 'ข้อความเท็จ' : (n.v === 'true' ? 'ข้อความจริง' : 'ข้อมูลบิดเบือน');
                badge.style.background = n.v === 'false' ? 'rgba(239, 68, 68, 0.25)' : (n.v === 'true' ? 'rgba(34, 197, 94, 0.25)' : 'rgba(245, 158, 11, 0.25)');
                badge.style.color = n.v === 'false' ? '#f87171' : (n.v === 'true' ? '#4ade80' : '#fbbf24');
            }} else {{
                hoveredIdx = null;
                tooltip.style.display = 'none';
            }}
        }});

        window.addEventListener('click', e => {{
            if (hoveredIdx !== null) {{
                const n = rawNodes[hoveredIdx];
                showDrawer(n);
            }}
        }});

        function showDrawer(n) {{
            const drawer = document.getElementById('sideDrawer');
            document.getElementById('drawerClaim').innerText = n.c;
            document.getElementById('drawerTitle').innerText = n.t;
            document.getElementById('drawerSource').innerText = n.s.toUpperCase();
            document.getElementById('drawerDate').innerText = n.d;
            document.getElementById('drawerBE').innerText = n.y + 543;
            document.getElementById('drawerTopic').innerText = topicsMeta[n.k].name;
            document.getElementById('drawerUrl').href = n.u;

            const badge = document.getElementById('drawerBadge');
            badge.innerText = n.v === 'false' ? 'ข้อความเท็จ (False)' : (n.v === 'true' ? 'ข้อความจริง (True)' : 'ข้อมูลบิดเบือน (Misleading)');
            badge.style.background = n.v === 'false' ? 'rgba(239, 68, 68, 0.2)' : (n.v === 'true' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(245, 158, 11, 0.2)');
            badge.style.color = n.v === 'false' ? '#f87171' : (n.v === 'true' ? '#4ade80' : '#fbbf24');
            badge.style.padding = '0.2rem 0.6rem';
            badge.style.borderRadius = '4px';
            badge.style.fontWeight = '700';

            drawer.style.display = 'flex';
        }}

        function closeDrawer() {{
            document.getElementById('sideDrawer').style.display = 'none';
        }}

        document.getElementById('searchBox').addEventListener('input', e => {{
            searchQuery = e.target.value;
            updateNodeVisibility();
        }});

        window.addEventListener('resize', () => {{
            width = container.clientWidth;
            height = container.clientHeight;
            camera.aspect = width / height;
            camera.updateProjectionMatrix();
            renderer.setSize(width, height);
        }});

        // Animation Loop with Smooth Interpolation
        function animate() {{
            requestAnimationFrame(animate);

            if (isTransitioning) {{
                transitionProgress += 0.035;
                const posAttr = geometry.attributes.position;

                for (let i = 0; i < totalNodes * 3; i++) {{
                    posAttr.array[i] += (targetPositions[i] - posAttr.array[i]) * 0.12;
                }}
                posAttr.needsUpdate = true;

                if (transitionProgress >= 1.0) {{
                    isTransitioning = false;
                }}
            }}

            controls.update();
            renderer.render(scene, camera);
        }}
        animate();
    </script>
</body>
</html>
"""
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"3D Misinformation Universe built successfully: {OUTPUT_PATH}")

if __name__ == "__main__":
    build_3d_graph()
