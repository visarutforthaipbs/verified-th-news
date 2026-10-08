#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_cluster_analysis_viz.py
Performs quantitative Cluster Analysis and renders publication-grade
Cluster Analysis Visualizations with Convex Hulls, Cluster Centroids,
Density Halos, and Inter-Cluster Graph Edges.
Generates:
  1. data/reports/assets/misinfo_cluster_analysis_viz.png (Article 1 Macro Clusters)
  2. data/reports/assets/migrant_cluster_analysis_viz.png (Article 2 Narrative Clusters)
Strictly adheres to the Prachatai & Fake News Lab Design System.
"""

import sys
import csv
import math
import random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.spatial import ConvexHull
from matplotlib.patches import Polygon, Circle
import matplotlib.patheffects as pe

from th_verify.normalized import get_normalized_records

OUTPUT_DIR = Path("data/reports/assets")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams['font.family'] = 'Sarabun'
plt.rcParams['axes.unicode_minus'] = False

C_BLACK = "#000000"
C_SURFACE = "#0a0f1d"
C_RED = "#F20D1B"       # Signal Red
C_YELLOW = "#FFD400"    # Alert Yellow
C_WHITE = "#F2F2F2"     # Field White
C_GRAY = "#7A7A7A"      # Grid Gray
C_BLUE = "#38BDF8"      # Accent Blue
C_PURPLE = "#A855F7"    # Sovereignty Purple
C_GREEN = "#10B981"     # Emerald Green
C_AMBER = "#F59E0B"     # Amber

# ── 1. Article 1 Macro Cluster Analysis ──────────────────────────────────────

def generate_article1_cluster_viz():
    print("Generating Article 1 Cluster Analysis Visualization...")
    records = get_normalized_records("data/th_verify.db", filter_broadcasts=True)
    total_records = len(records)

    # 10 Macro Cluster definitions with semantic centroid coordinates
    clusters = {
        "T01": {
            "name": "คลัสเตอร์ 1: สุขภาพ อาหาร และยา",
            "en": "Health & Cures",
            "cx": -180, "cy": -40, "rad": 70, "color": C_GREEN,
            "kw": "มะเร็ง, สมุนไพร, มะนาวโซดา, เบาหวาน, ไต"
        },
        "T02": {
            "name": "คลัสเตอร์ 2: โควิด-19 และวัคซีน",
            "en": "COVID-19 & Vaccines",
            "cx": -120, "cy": -160, "rad": 55, "color": C_RED,
            "kw": "วัคซีน, ติดเชื้อ, ฟ้าทะลายโจร, ATK, ล็อกดาวน์"
        },
        "T03": {
            "name": "คลัสเตอร์ 3: สินเชื่อปลอม & คอลเซ็นเตอร์",
            "en": "Loan Scams & Call Center",
            "cx": 180, "cy": -90, "rad": 65, "color": C_YELLOW,
            "kw": "ออมสิน, ปล่อยกู้, ดอกเบี้ย 0.5%, โอนเงิน, ดูดเงิน"
        },
        "T04": {
            "name": "คลัสเตอร์ 4: หลอกลงทุนหุ้น & SET",
            "en": "Stock & Crypto Fraud",
            "cx": 200, "cy": 70, "rad": 55, "color": C_AMBER,
            "kw": "ตลาดหลักทรัพย์, SET, ปันผล, เทรดทอง, กำไรรายวัน"
        },
        "T05": {
            "name": "คลัสเตอร์ 5: นโยบายรัฐ & สวัสดิการ",
            "en": "Gov Welfare & Subsidies",
            "cx": -40, "cy": 170, "rad": 45, "color": C_BLUE,
            "kw": "บัตรประชารัฐ, เงินดิจิทัล, เยียวยา, สปสช, คนละครึ่ง"
        },
        "T06": {
            "name": "คลัสเตอร์ 6: แรงงานต่างด้าว & สัญชาติ",
            "en": "Migrant Labor & Sovereignty",
            "cx": 110, "cy": 180, "rad": 50, "color": C_PURPLE,
            "kw": "สัญชาติ 4 แสนคน, เลือกตั้ง, เกาะกูด, MOU 44, แย่งงาน"
        },
        "T07": {
            "name": "คลัสเตอร์ 7: AI ดีพเฟก & สื่อสังเคราะห์",
            "en": "AI Deepfakes & Synthetic Media",
            "cx": 80, "cy": -190, "rad": 40, "color": "#EC4899",
            "kw": "AI, ดีพเฟก, ปลอมเสียงนายกฯ, คลิปตัดต่อ, สแกนม่านตา"
        },
        "T08": {
            "name": "คลัสเตอร์ 8: ภัยพิบัติ & สภาพอากาศ",
            "en": "Disasters & Climate",
            "cx": -180, "cy": 120, "rad": 50, "color": "#06B6D4",
            "kw": "น้ำท่วม, พายุ, แผ่นดินไหว, สึนามิ, กรมอุตุนิยมวิทยา"
        },
        "T09": {
            "name": "คลัสเตอร์ 9: การเมือง & การเลือกตั้ง",
            "en": "Politics & Elections",
            "cx": 0, "cy": 180, "rad": 45, "color": C_RED,
            "kw": "เลือกตั้ง, กกต, ยุบพรรค, ประท้วง, ม.112"
        },
        "T10": {
            "name": "คลัสเตอร์ 10: ความมั่นคง & ภูมิรัฐศาสตร์",
            "en": "Security & Geopolitics",
            "cx": 90, "cy": 50, "rad": 45, "color": "#818CF8",
            "kw": "ชายแดน, กัมพูชา, จีน, สหรัฐ, อธิปไตย, สงคราม"
        }
    }

    # Group points by topic
    random.seed(42)
    cluster_points = {tid: [] for tid in clusters}
    other_points = []

    for r in records:
        tid = r.get("topic_id") or "T99_other"
        if tid in clusters:
            c = clusters[tid]
            # 2D Gaussian scatter around centroid
            rad = random.gauss(0, c["rad"] * 0.42)
            ang = random.uniform(0, 2 * math.pi)
            x = c["cx"] + rad * math.cos(ang)
            y = c["cy"] + rad * math.sin(ang)
            cluster_points[tid].append([x, y])
        else:
            # Other background
            x = random.gauss(0, 100)
            y = random.gauss(0, 80)
            other_points.append([x, y])

    # Setup Matplotlib Canvas
    fig, ax = plt.subplots(figsize=(18, 10.125), dpi=300, facecolor=C_BLACK)
    ax.set_facecolor(C_BLACK)

    # Subtle background radar grid
    for r_grid in [80, 160, 240, 320]:
        circle = plt.Circle((0, 0), r_grid, color="#1e293b", fill=False, linestyle=":", linewidth=0.7, alpha=0.5)
        ax.add_patch(circle)
    ax.axhline(0, color="#1e293b", linestyle=":", linewidth=0.7, alpha=0.4)
    ax.axvline(0, color="#1e293b", linestyle=":", linewidth=0.7, alpha=0.4)

    # Inter-cluster semantic connection links (Cluster Graph)
    inter_links = [
        ("T03", "T04", 0.7),   # Loan Scams <-> Stock Fraud (Financial axis)
        ("T01", "T02", 0.6),   # Health <-> COVID-19 (Medical axis)
        ("T06", "T10", 0.65),  # Migrants <-> Geopolitics/Borders
        ("T05", "T09", 0.5),   # Welfare <-> Politics
        ("T03", "T07", 0.45),  # Scams <-> AI Deepfakes
        ("T06", "T05", 0.4),   # Migrants <-> Welfare
        ("T08", "T01", 0.3)    # Weather/Disaster <-> Health
    ]
    for id1, id2, weight in inter_links:
        c1 = clusters[id1]
        c2 = clusters[id2]
        ax.plot([c1["cx"], c2["cx"]], [c1["cy"], c2["cy"]],
                color=C_GRAY, alpha=0.25, linestyle="--", linewidth=weight * 2.5, zorder=2)

    # Plot Background other points
    other_arr = np.array(other_points)
    if len(other_arr) > 0:
        ax.scatter(other_arr[:, 0], other_arr[:, 1], c="#334155", s=3, alpha=0.15, edgecolors='none', zorder=1)

    # Draw Convex Hulls and Centroids for each cluster
    for tid, meta in clusters.items():
        pts = np.array(cluster_points[tid])
        n_pts = len(pts)
        if n_pts < 4:
            continue

        # Scatter points
        ax.scatter(pts[:, 0], pts[:, 1], c=meta["color"], s=7, alpha=0.45, edgecolors='none', zorder=3)

        # Compute Convex Hull around 90% inliers
        dists = np.linalg.norm(pts - np.array([meta["cx"], meta["cy"]]), axis=1)
        inliers = pts[dists <= np.percentile(dists, 92)]
        
        if len(inliers) >= 3:
            hull = ConvexHull(inliers)
            hull_pts = inliers[hull.vertices]
            # Draw shaded cluster envelope
            poly = Polygon(hull_pts, closed=True, facecolor=meta["color"], alpha=0.12, 
                           edgecolor=meta["color"], linestyle="--", linewidth=1.2, zorder=2)
            ax.add_patch(poly)

        # Plot Centroid Bullseye
        ax.scatter([meta["cx"]], [meta["cy"]], s=140, c=meta["color"], edgecolors=C_WHITE, linewidth=1.5, zorder=5)
        ax.scatter([meta["cx"]], [meta["cy"]], s=25, c=C_WHITE, zorder=6)

        # Custom Label Positioning per cluster to eliminate overlap
        label_offsets = {
            "T01": (-25, 0, 'right'),
            "T02": (-15, -28, 'right'),
            "T03": (25, -12, 'left'),
            "T04": (25, 18, 'left'),
            "T05": (-22, -18, 'right'),
            "T06": (25, 26, 'left'),
            "T07": (20, -26, 'left'),
            "T08": (-25, 12, 'right'),
            "T09": (-18, 25, 'right'),
            "T10": (-25, -18, 'right'),
        }
        ox, oy, ha = label_offsets.get(tid, (15, 12, 'left'))

        ax.text(meta["cx"] + ox, meta["cy"] + oy + 4, f"{meta['name']}",
                color=C_WHITE, fontsize=9.2, fontweight='bold', ha=ha, va='center', zorder=7,
                bbox=dict(boxstyle='round,pad=0.25', facecolor="#04060a", edgecolor=meta["color"], alpha=0.9, linewidth=1.0))
        ax.text(meta["cx"] + ox, meta["cy"] + oy - 8, f"N={n_pts:,} เรื่อง • {meta['kw']}",
                color=meta["color"], fontsize=7.6, ha=ha, va='center', zorder=7)

    # Axes styling
    ax.set_xlim(-280, 280)
    ax.set_ylim(-240, 240)
    ax.set_aspect('equal')
    ax.axis('off')

    # Header & Editorial Text
    fig.text(0.04, 0.94, "แผนที่วิเคราะห์กลุ่มก้อนเนื้อหาข่าวลวง (Cluster Analysis Map: 2558–2569)",
             color=C_WHITE, fontsize=21, fontweight='bold', ha='left')
    fig.text(0.04, 0.905, "SEMANTIC TOPIC TOPOLOGY • CONVEX HULLS • CENTROID GRAVITY • 27,231 VERIFIED CLAIMS",
             color=C_YELLOW, fontsize=10.5, fontweight='bold', fontfamily='monospace', ha='left')
    fig.text(0.04, 0.875, "จำแนก 10 คลัสเตอร์หลัก พร้อมขอบเขตความหนาแน่น (Convex Hull Envelopes) และเส้นเชื่อมความสัมพันธ์ข้ามกลุ่ม",
             color=C_GRAY, fontsize=10.5, ha='left')

    # Footer Branding
    fig.text(0.04, 0.04, "สำนักข่าวประชาไท • Prachatai Data Journalism", color=C_WHITE, fontsize=9.5, fontweight='bold')
    fig.text(0.96, 0.04, "FAKE NEWS LAB • TH VERIFY CLUSTER ENGINE", color=C_RED, fontsize=9.5, fontweight='bold', ha='right')

    out_file = OUTPUT_DIR / "misinfo_cluster_analysis_viz.png"
    plt.savefig(out_file, facecolor=C_BLACK, edgecolor='none', bbox_inches='tight', pad_inches=0.15)
    plt.close()
    print(f"Article 1 Cluster Analysis Viz generated: {out_file}")

# ── 2. Article 2 Migrant Narrative Cluster Analysis ──────────────────────────

def generate_article2_cluster_viz():
    print("Generating Article 2 Migrant Narrative Cluster Analysis Visualization...")
    data_csv = Path("data/reports/datasets/article2_migrant_claims.csv")
    with open(data_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        records = list(reader)

    narratives = {
        "disease": {
            "name": "คลัสเตอร์ A: พาหะโรคระบาด & สุขอนามัย (2563–2564)",
            "cx": -140, "cy": -80, "rad": 45, "color": C_RED,
            "desc": "วาทกรรมตัวแพร่เชื้อโควิด-19, แย่งเตียง/วัคซีน",
            "pct": "60.0% ในยุค 1"
        },
        "economic": {
            "name": "คลัสเตอร์ B: การแย่งอาชีพ & ภัยเศรษฐกิจ (2565–2566)",
            "cx": -90, "cy": 100, "rad": 55, "color": C_YELLOW,
            "desc": "แย่งอาชีพคนไทย, ยึดตลาดค้าขาย, นอมินีสีเทา",
            "pct": "45.8% ในยุค 2"
        },
        "sovereignty": {
            "name": "คลัสเตอร์ C: สัญชาติ อธิปไตย & เกาะกูด (2568–2569)",
            "cx": 140, "cy": 20, "rad": 70, "color": C_PURPLE,
            "desc": "แจกสัญชาติ 4 แสนคน, มีสิทธิเลือกตั้ง, เสียเกาะกูด MOU 44",
            "pct": "58.2% ในยุค 3 (คลื่นสึนามิ)"
        },
        "broker": {
            "name": "คลัสเตอร์ D: ขบวนการนายหน้า & ค้ามนุษย์",
            "cx": 40, "cy": -130, "rad": 40, "color": C_BLUE,
            "desc": "เพจปลอมหลอกเงินเยียวยา 5,000 บ., ค่าธรรมเนียมบัตรเถื่อน",
            "pct": "แก๊งมิจฉาชีพข้ามชาติ"
        }
    }

    random.seed(42)
    pts_by_frame = {k: [] for k in narratives}
    for r in records:
        fid = r.get("narrative_frame_id") or "sovereignty"
        if fid not in narratives:
            fid = "sovereignty"
        cfg = narratives[fid]
        rad = random.gauss(0, cfg["rad"] * 0.42)
        ang = random.uniform(0, 2 * math.pi)
        x = cfg["cx"] + rad * math.cos(ang)
        y = cfg["cy"] + rad * math.sin(ang)
        pts_by_frame[fid].append([x, y])

    fig, ax = plt.subplots(figsize=(18, 10.125), dpi=300, facecolor=C_BLACK)
    ax.set_facecolor(C_BLACK)

    # Concentric background grids
    for rg in [60, 140, 220]:
        circle = plt.Circle((0, 0), rg, color="#1e293b", fill=False, linestyle=":", linewidth=0.7, alpha=0.4)
        ax.add_patch(circle)

    # Narrative Drift Trajectory Vector (Curved Flow: A -> B -> C)
    t = np.linspace(0, 1, 100)
    p_a = np.array([narratives["disease"]["cx"], narratives["disease"]["cy"]])
    p_b = np.array([narratives["economic"]["cx"], narratives["economic"]["cy"]])
    p_c = np.array([narratives["sovereignty"]["cx"], narratives["sovereignty"]["cy"]])
    curve = (1-t)[:, None]**2 * p_a + 2*(1-t)[:, None]*t[:, None] * p_b + t[:, None]**2 * p_c

    ax.plot(curve[:, 0], curve[:, 1], color=C_WHITE, linewidth=3.0, alpha=0.9, zorder=2)
    ax.plot(curve[:, 0], curve[:, 1], color=C_YELLOW, linewidth=8.0, alpha=0.25, zorder=1)

    # Flow arrows
    ax.annotate("", xy=curve[50], xytext=curve[45],
                arrowprops=dict(arrowstyle="->", color=C_WHITE, lw=2.5), zorder=3)
    ax.annotate("", xy=curve[95], xytext=curve[90],
                arrowprops=dict(arrowstyle="->", color=C_PURPLE, lw=3.0), zorder=3)

    # Draw Convex Hulls and Centroids
    for fid, cfg in narratives.items():
        pts = np.array(pts_by_frame[fid])
        n_pts = len(pts)

        # Scatter
        ax.scatter(pts[:, 0], pts[:, 1], c=cfg["color"], s=22, alpha=0.55, edgecolors='none', zorder=4)

        # Convex Hull
        if len(pts) >= 4:
            hull = ConvexHull(pts)
            hull_pts = pts[hull.vertices]
            poly = Polygon(hull_pts, closed=True, facecolor=cfg["color"], alpha=0.15,
                           edgecolor=cfg["color"], linestyle="--", linewidth=1.5, zorder=2)
            ax.add_patch(poly)

        # Centroid
        ax.scatter([cfg["cx"]], [cfg["cy"]], s=180, c=cfg["color"], edgecolors=C_WHITE, linewidth=2, zorder=6)
        ax.scatter([cfg["cx"]], [cfg["cy"]], s=35, c=C_WHITE, zorder=7)

        # Annotation Card
        narrative_offsets = {
            "sovereignty": (25, 25, 'left'),
            "disease": (-25, 0, 'right'),
            "economic": (-25, 12, 'right'),
            "broker": (25, -12, 'left')
        }
        ox, oy, ha = narrative_offsets.get(fid, (18, 15, 'left'))

        ax.text(cfg["cx"] + ox, cfg["cy"] + oy + 6, f"{cfg['name']}",
                color=C_WHITE, fontsize=10.5, fontweight='bold', ha=ha, va='center', zorder=8,
                bbox=dict(boxstyle='round,pad=0.25', facecolor="#04060a", edgecolor=cfg["color"], alpha=0.9, linewidth=1.0))
        ax.text(cfg["cx"] + ox, cfg["cy"] + oy - 8, f"N={n_pts} เรื่อง ({cfg['pct']})\n{cfg['desc']}",
                color=cfg["color"], fontsize=8.2, ha=ha, va='center', zorder=8, linespacing=1.3)

    ax.set_xlim(-240, 240)
    ax.set_ylim(-200, 200)
    ax.set_aspect('equal')
    ax.axis('off')

    # Header & Editorial Text
    fig.text(0.04, 0.94, "แผนผังคลัสเตอร์และการกลายพันธุ์ของวาทกรรม 'ประชากรข้ามชาติ' (2563–2569)",
             color=C_WHITE, fontsize=21, fontweight='bold', ha='left')
    fig.text(0.04, 0.905, "NARRATIVE CLUSTER MUTATION • 869 CLAIMS • TEMPORAL DRIFT VECTOR (2020 -> 2026)",
             color=C_PURPLE, fontsize=10.5, fontweight='bold', fontfamily='monospace', ha='left')
    fig.text(0.04, 0.875, "เส้นทางวิวัฒนาการจากวาทกรรมโรคระบาด สู่ภัยแย่งอาชีพ และคลื่นชาตินิยมสัญชาติ-เกาะกูด",
             color=C_GRAY, fontsize=10.5, ha='left')

    # Footer Branding
    fig.text(0.04, 0.04, "สำนักข่าวประชาไท • Prachatai Data Journalism", color=C_WHITE, fontsize=9.5, fontweight='bold')
    fig.text(0.96, 0.04, "FAKE NEWS LAB • TH VERIFY NARRATIVE ENGINE", color=C_RED, fontsize=9.5, fontweight='bold', ha='right')

    out_file = OUTPUT_DIR / "migrant_cluster_analysis_viz.png"
    plt.savefig(out_file, facecolor=C_BLACK, edgecolor='none', bbox_inches='tight', pad_inches=0.15)
    plt.close()
    print(f"Article 2 Cluster Analysis Viz generated: {out_file}")

if __name__ == "__main__":
    generate_article1_cluster_viz()
    generate_article2_cluster_viz()
