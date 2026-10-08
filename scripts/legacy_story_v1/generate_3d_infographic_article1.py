#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_3d_infographic_article1.py
Generates a publication-grade 3D Network Infographic for Prachatai Article 1:
'วิวัฒนาการ 11 ปี ข่าวลวงในสังคมไทย (พ.ศ. 2558–2569)'
Based 100% on REAL DATA from 27,231 verified atomic claims in the archive.
Follows Prachatai & Fake News Lab Branding System:
  - Infra Black (#000000)
  - Signal Red (#F20D1B)
  - Alert Yellow (#FFD400)
  - Field White (#F2F2F2)
  - Grid Gray (#7A7A7A)
  - Font: Sarabun / Kanit
"""

import sys
import math
import random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.patches import Rectangle, Circle
import matplotlib.patheffects as pe

from th_verify.normalized import get_normalized_records

OUTPUT_PATH = Path("data/reports/assets/misinfo_11years_3d_infographic.png")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Set font
plt.rcParams['font.family'] = 'Sarabun'
plt.rcParams['axes.unicode_minus'] = False

def generate():
    print("Loading real dataset for Article 1 3D infographic...")
    records = get_normalized_records("data/th_verify.db", filter_broadcasts=True)
    total_records = len(records)
    print(f"Loaded {total_records} real atomic claims.")

    # Brand Colors
    C_BLACK = "#000000"
    C_SURFACE = "#080c14"
    C_RED = "#F20D1B"       # Signal Red
    C_YELLOW = "#FFD400"    # Alert Yellow
    C_WHITE = "#F2F2F2"     # Field White
    C_GRAY = "#7A7A7A"      # Grid Gray
    C_BLUE = "#38BDF8"      # Accent Blue
    C_PURPLE = "#A855F7"    # Sovereignty Purple

    # Topic layout angles in cylindrical space (Theta in radians)
    topic_meta = {
        "T01": {"angle": 0.0, "rad": 160, "color": C_YELLOW, "name": "สุขภาพ อาหาร และยา"},
        "T02": {"angle": 0.6, "rad": 140, "color": C_RED, "name": "โควิด-19 และวัคซีน"},
        "T03": {"angle": 1.3, "rad": 150, "color": C_YELLOW, "name": "สินเชื่อปลอม & คอลเซ็นเตอร์"},
        "T04": {"angle": 1.9, "rad": 170, "color": C_YELLOW, "name": "หลอกลงทุนหุ้น & SET"},
        "T05": {"angle": 2.5, "rad": 130, "color": C_BLUE, "name": "นโยบายรัฐ & สวัสดิการ"},
        "T06": {"angle": 3.1, "rad": 160, "color": C_PURPLE, "name": "แรงงานต่างด้าว & สัญชาติ"},
        "T07": {"angle": 3.7, "rad": 140, "color": C_RED, "name": "AI Deepfake & สื่อตัดต่อ"},
        "T08": {"angle": 4.4, "rad": 130, "color": C_BLUE, "name": "ภัยพิบัติ & สภาพอากาศ"},
        "T09": {"angle": 5.0, "rad": 140, "color": C_RED, "name": "การเมือง & การเลือกตั้ง"},
        "T10": {"angle": 5.6, "rad": 150, "color": C_WHITE, "name": "ความมั่นคง & ภูมิรัฐศาสตร์"},
        "T99_other": {"angle": 0.0, "rad": 40, "color": C_GRAY, "name": "อื่นๆ"}
    }

    # Extract real data coordinates
    random.seed(42)
    xs, ys, zs, colors, sizes = [], [], [], [], []
    
    # Track nodes for network edges
    sample_nodes_by_era = {1: [], 2: [], 3: [], 4: []}

    for r in records:
        tid = r.get("topic_id") or "T99_other"
        tm = topic_meta.get(tid, topic_meta["T99_other"])
        
        try:
            year = int(r.get("published_year") or 2020)
        except (ValueError, TypeError):
            year = 2020

        # Assign Era
        if year <= 2018: era = 1
        elif year <= 2021: era = 2
        elif year <= 2023: era = 3
        else: era = 4

        # Cylindrical coordinates: X = r*cos(theta) + jitter, Y = r*sin(theta) + jitter, Z = Year
        angle = tm["angle"] + random.gauss(0, 0.22)
        radius = tm["rad"] + random.gauss(0, 25)
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        z = year + random.gauss(0, 0.12)  # subtle year jitter for cloud thickness

        xs.append(x)
        ys.append(y)
        zs.append(z)
        colors.append(tm["color"])
        
        # Sizing: newer scam/AI/COVID claims pop slightly larger
        if tid in ["T02", "T03", "T04", "T06", "T07"] and era >= 2:
            sizes.append(random.uniform(5, 12))
        else:
            sizes.append(random.uniform(3, 7))

        if random.random() < 0.04:  # Sample 4% for drawing network edges
            sample_nodes_by_era[era].append((x, y, z, tm["color"]))

    # Setup High-Resolution Matplotlib Canvas
    fig = plt.figure(figsize=(18, 10.125), dpi=300, facecolor=C_BLACK)
    
    # 3D Main Axes (Positioned carefully leaving room for editorial side cards)
    ax = fig.add_axes([0.18, 0.08, 0.80, 0.82], projection='3d', facecolor=C_BLACK)
    
    # Darken 3D pane backgrounds
    ax.xaxis.set_pane_color((0.0, 0.0, 0.0, 0.0))
    ax.yaxis.set_pane_color((0.0, 0.0, 0.0, 0.0))
    ax.zaxis.set_pane_color((0.0, 0.0, 0.0, 0.0))
    ax.grid(False)

    # 1. Draw 4 3D Era Reference Disks & Elevation Rings (Wireframes)
    era_rings = [
        (2016.5, "ยุคที่ 1: สุขภาพ & ไลน์ส่งต่อ (2558–2561)", C_GRAY),
        (2020.0, "ยุคที่ 2: วิกฤตโรคระบาดโควิด-19 (2562–2564)", C_RED),
        (2022.5, "ยุคที่ 3: การเงินภิวัตน์ & สินเชื่อปลอม (2565–2566)", C_YELLOW),
        (2025.2, "ยุคที่ 4: AI Deepfake & ชาตินิยม (2567–2569)", C_PURPLE),
    ]

    theta_ring = np.linspace(0, 2 * np.pi, 100)
    for z_level, label, ring_col in era_rings:
        # Concentric rings
        for r_ring in [120, 210]:
            rx = r_ring * np.cos(theta_ring)
            ry = r_ring * np.sin(theta_ring)
            rz = np.full_like(rx, z_level)
            ax.plot(rx, ry, rz, color=ring_col, alpha=0.25, linestyle="--", linewidth=0.8)
        
        # Label on the ring
        ax.text(220, 0, z_level, f" {label}", color=ring_col, fontsize=8, fontweight='bold',
                ha='left', va='center')

    # 2. Draw Central Vertical Time Axis (Spine)
    ax.plot([0, 0], [0, 0], [2014.8, 2026.5], color=C_WHITE, alpha=0.5, linewidth=1.5, linestyle="-")
    for y_mark in range(2015, 2027):
        ax.plot([-15, 15], [0, 0], [y_mark, y_mark], color=C_GRAY, alpha=0.4, linewidth=0.8)
        ax.text(0, -30, y_mark, f"{y_mark+543}", color=C_GRAY, fontsize=7, ha='right', va='center')

    # 3. Draw Network Edges between real sampled claims in the same era
    for era, pts in sample_nodes_by_era.items():
        for i in range(min(len(pts), 140)):
            p1 = pts[i]
            # connect to 2 nearest neighbors
            dists = []
            for j in range(len(pts)):
                if i == j: continue
                p2 = pts[j]
                d = (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2 * 100
                dists.append((d, p2))
            dists.sort(key=lambda x: x[0])
            for _, p2 in dists[:2]:
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], 
                        color=p1[3], alpha=0.12, linewidth=0.4)

    # 4. Scatter Plot Real Claim Nodes (27,231 points)
    # Downsample slightly for rendering performance if needed, but 27k renders in seconds in matplotlib
    ax.scatter(xs, ys, zs, c=colors, s=sizes, alpha=0.55, edgecolors='none', depthshade=True)

    # Set camera perspective
    ax.view_init(elev=22, azim=-55)
    ax.set_xlim(-240, 240)
    ax.set_ylim(-240, 240)
    ax.set_zlim(2014.5, 2026.8)
    ax.set_axis_off()

    # ── 2D Infographic Overlay & Editorial Layout ────────────────────────
    # Top Header Title
    fig.text(0.04, 0.94, "โครงข่ายสามมิติและวิวัฒนาการ 11 ปี ข่าวลวงในสังคมไทย (พ.ศ. 2558–2569)",
             color=C_WHITE, fontsize=22, fontweight='bold', ha='left')
    fig.text(0.04, 0.905, "11-YEAR TEMPORAL MISINFORMATION UNIVERSE • 27,231 VERIFIED CLAIMS",
             color=C_YELLOW, fontsize=11, fontweight='bold', fontfamily='monospace', ha='left')
    fig.text(0.04, 0.875, "ถอดรหัสการกลายพันธุ์จากเรื่องเล่าสุขภาพ สู่อาชญากรรมการเงินและภัยความมั่นคง ผ่าน 4 ยุคประวัติศาสตร์",
             color=C_GRAY, fontsize=11, ha='left')

    # Left Editorial Summary Box (Positioned properly without clipping)
    box_rect = plt.Rectangle((0.04, 0.12), 0.28, 0.72, transform=fig.transFigure,
                             facecolor=C_SURFACE, edgecolor="#1e293b", linewidth=1.5, zorder=20)
    fig.patches.append(box_rect)

    # Box Content
    fig.text(0.06, 0.805, "[*] สถิติสำคัญจากการขุดค้น 11 ปี", color=C_YELLOW, fontsize=13, fontweight='bold', zorder=25)
    
    stats_lines = [
        ("• จำนวนข้อเท็จจริงทั้งหมด:", " 27,231 เรื่อง"),
        ("• แหล่งข้อมูลตรวจสอบ:", " 5 สถาบันหลัก"),
        ("  (ศูนย์ต่อต้านข่าวปลอม, ชัวร์ก่อนแชร์, Cofact, AFP, Thai PBS)", ""),
        ("• ผลตรวจยืนยันโดยมนุษย์ (Gold):", " 5,185 เรื่อง"),
        ("", ""),
        ("3 จุดเปลี่ยนประวัติศาสตร์ (JSD Score):", ""),
        ("  1. ปี 2563: JSD = 0.4076", " (โควิดช็อก)"),
        ("  2. ปี 2568: JSD = 0.1828", " (ชาตินิยม & AI)"),
        ("  3. ปี 2566: JSD = 0.1794", " (การเงินภิวัตน์)"),
        ("", ""),
        ("การเปลี่ยนแปลงสำคัญ (เทียบยุค 2 -> ยุค 4):", ""),
        ("  [+] หลอกลงทุนหุ้น & SET:", "  +2,030.6% (p<0.001)"),
        ("  [+] แรงงานต่างด้าว & สัญชาติ:", " +624.3% (p<0.001)"),
        ("  [+] AI Deepfake สื่อตัดต่อ:", "  +430.5% (p<0.001)"),
        ("  [-] ข่าวโควิด-19 และวัคซีน:", "   -93.7% (p<0.001)"),
        ("  [-] สุขภาพและยาสมุนไพร:", "     -37.6% (p<0.001)"),
        ("", ""),
        ("สถาบันที่ถูกแอบอ้างสูงสุด:", ""),
        ("  - ธนาคารออมสิน (GSB):", " 659 เรื่อง (ปล่อยกู้)"),
        ("  - ตลาดหลักทรัพย์ฯ (SET):", " 511 เรื่อง (หลอกเทรด)"),
        ("  - ธนาคารกรุงไทย (KTB):", " 354 เรื่อง (เงินกู้ฉุกเฉิน)")
    ]

    curr_y = 0.77
    for label, val in stats_lines:
        if not label:
            curr_y -= 0.012
            continue
        fig.text(0.06, curr_y, label + val, color=C_WHITE if not label.startswith("  [+]") else C_YELLOW,
                 fontsize=9.2, zorder=25)
        curr_y -= 0.024

    # Legend at bottom of left box
    fig.text(0.06, 0.18, "สัญลักษณ์สีกลุ่มหัวข้อ:", color=C_GRAY, fontsize=9.5, fontweight='bold', zorder=25)
    fig.text(0.06, 0.145, "[เหลือง] สุขภาพ / การเงิน     [แดง] โควิด / การเมือง\n[ม่วง] สัญชาติ & เกาะกูด      [ฟ้า] นโยบายรัฐ / สภาพอากาศ",
             color=C_WHITE, fontsize=8.5, linespacing=1.4, zorder=25)

    # Footer Logos / Branding
    fig.text(0.04, 0.045, "สำนักข่าวประชาไท • Prachatai Data Journalism", color=C_WHITE, fontsize=10, fontweight='bold')
    fig.text(0.96, 0.045, "FAKE NEWS LAB • TH VERIFY OPEN ARCHIVE", color=C_RED, fontsize=10, fontweight='bold', ha='right')

    plt.savefig(OUTPUT_PATH, facecolor=C_BLACK, edgecolor='none', bbox_inches='tight', pad_inches=0.15)
    plt.close()
    print(f"Article 1 3D infographic updated successfully at: {OUTPUT_PATH}")

if __name__ == "__main__":
    generate()
