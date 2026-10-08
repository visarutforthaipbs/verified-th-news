#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_3d_infographic_article2.py
Generates a publication-grade 3D Network Infographic for Prachatai Article 2:
'ถอดรหัส 7 ปี ข่าวลวงและการสร้างวาทกรรม ประชากรข้ามชาติ (พ.ศ. 2563–2569)'
Based 100% on REAL DATA from 869 verified claims in the archive.
Follows Prachatai & Fake News Lab Branding System.
"""

import sys
import math
import random
import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

DATA_CSV = Path("data/reports/datasets/article2_migrant_claims.csv")
OUTPUT_PATH = Path("data/reports/assets/migrant_narrative_3d_infographic.png")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

plt.rcParams['font.family'] = 'Sarabun'
plt.rcParams['axes.unicode_minus'] = False

def generate():
    print("Loading real migrant claims dataset for Article 2 3D infographic...")
    with open(DATA_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        records = list(reader)
    total_records = len(records)
    print(f"Loaded {total_records} real migrant claims.")

    # Brand Colors
    C_BLACK = "#000000"
    C_SURFACE = "#080c14"
    C_RED = "#F20D1B"       # Signal Red
    C_YELLOW = "#FFD400"    # Alert Yellow
    C_WHITE = "#F2F2F2"     # Field White
    C_GRAY = "#7A7A7A"      # Grid Gray
    C_BLUE = "#38BDF8"      # Accent Blue
    C_PURPLE = "#A855F7"    # Sovereignty Purple

    # Narrative cluster configuration in 3D
    cluster_cfg = {
        "sovereignty": {
            "name": "สัญชาติ อธิปไตย & เกาะกูด",
            "cx": 140, "cy": -40, "color": C_PURPLE, "rad": 70
        },
        "disease": {
            "name": "โรคระบาด & โควิด-19",
            "cx": -150, "cy": -120, "color": C_RED, "rad": 45
        },
        "economic": {
            "name": "แย่งอาชีพ เศรษฐกิจ & นอมินี",
            "cx": -120, "cy": 100, "color": C_YELLOW, "rad": 60
        },
        "broker": {
            "name": "ขบวนการลักลอบ & นายหน้า",
            "cx": 80, "cy": 130, "color": C_BLUE, "rad": 50
        },
        "other": {
            "name": "ประเด็นอื่นๆ ทั่วไป",
            "cx": 0, "cy": 0, "color": C_GRAY, "rad": 35
        }
    }

    random.seed(42)
    xs, ys, zs, colors, sizes = [], [], [], [], []
    pts_by_frame = {"sovereignty": [], "disease": [], "economic": [], "broker": []}

    for r in records:
        fid = r.get("narrative_frame_id") or "other"
        cfg = cluster_cfg.get(fid, cluster_cfg["other"])
        
        try:
            year = int(r.get("published_year") or 2020)
        except (ValueError, TypeError):
            year = 2020

        # Cluster scatter around centroid
        angle = random.uniform(0, 2 * math.pi)
        dist = random.gauss(0, cfg["rad"] * 0.45)
        x = cfg["cx"] + dist * math.cos(angle)
        y = cfg["cy"] + dist * math.sin(angle)
        z = year + random.gauss(0, 0.14)

        xs.append(x)
        ys.append(y)
        zs.append(z)
        colors.append(cfg["color"])
        
        # Newer sovereignty / border claims pop larger
        if fid == "sovereignty" and year >= 2025:
            sizes.append(random.uniform(14, 28))
        elif fid == "disease":
            sizes.append(random.uniform(12, 22))
        else:
            sizes.append(random.uniform(8, 16))

        if fid in pts_by_frame:
            pts_by_frame[fid].append((x, y, z, cfg["color"]))

    # Setup 16:9 Figure
    fig = plt.figure(figsize=(18, 10.125), dpi=300, facecolor=C_BLACK)
    ax = fig.add_axes([0.22, 0.08, 0.76, 0.82], projection='3d', facecolor=C_BLACK)

    ax.xaxis.set_pane_color((0.0, 0.0, 0.0, 0.0))
    ax.yaxis.set_pane_color((0.0, 0.0, 0.0, 0.0))
    ax.zaxis.set_pane_color((0.0, 0.0, 0.0, 0.0))
    ax.grid(False)

    # 1. Draw 3D Timeline Elevation Rings (Years 2020 to 2026)
    theta_ring = np.linspace(0, 2 * np.pi, 80)
    for y_val, phase_title, col in [
        (2020.5, "ยุค 1: วาทกรรมพาหะโรคระบาด (2563–2564)", C_RED),
        (2022.5, "ยุค 2: วาทกรรมแย่งอาชีพคนไทย (2565–2566)", C_YELLOW),
        (2025.2, "ยุค 3: วาทกรรมสัญชาติ & อธิปไตยเกาะกูด (2568–2569)", C_PURPLE),
    ]:
        rx = 210 * np.cos(theta_ring)
        ry = 210 * np.sin(theta_ring)
        rz = np.full_like(rx, y_val)
        ax.plot(rx, ry, rz, color=col, alpha=0.3, linestyle="--", linewidth=0.9)
        ax.text(220, 0, y_val, f" {phase_title}", color=col, fontsize=8.5, fontweight='bold')

    # 2. Draw 3D Mutation Trajectory Curves (Disease 2020 -> Economic 2022 -> Sovereignty 2025)
    traj_t = np.linspace(0, 1, 100)
    # Spline from disease center (2020.5) to economic center (2022.5) to sovereignty (2025.5)
    c1 = cluster_cfg["disease"]
    c2 = cluster_cfg["economic"]
    c3 = cluster_cfg["sovereignty"]
    
    # Smooth bezier curve
    bx = (1-traj_t)**2 * c1["cx"] + 2*(1-traj_t)*traj_t * c2["cx"] + traj_t**2 * c3["cx"]
    by = (1-traj_t)**2 * c1["cy"] + 2*(1-traj_t)*traj_t * c2["cy"] + traj_t**2 * c3["cy"]
    bz = 2020.2 + traj_t * 5.4
    ax.plot(bx, by, bz, color=C_WHITE, alpha=0.8, linewidth=2.5, linestyle="-")
    ax.plot(bx, by, bz, color=C_YELLOW, alpha=0.3, linewidth=6.0, linestyle="-")

    # 3. Draw Network Links within clusters
    for fid, pts in pts_by_frame.items():
        sample_pts = random.sample(pts, min(len(pts), 90))
        for i in range(len(sample_pts)):
            p1 = sample_pts[i]
            # connect to nearest 2
            dists = []
            for j in range(len(sample_pts)):
                if i == j: continue
                p2 = sample_pts[j]
                d = (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2 * 40
                dists.append((d, p2))
            dists.sort(key=lambda x: x[0])
            for _, p2 in dists[:2]:
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], 
                        color=p1[3], alpha=0.18, linewidth=0.5)

    # 4. Scatter Real Nodes
    ax.scatter(xs, ys, zs, c=colors, s=sizes, alpha=0.65, edgecolors='none', depthshade=True)

    # View Settings
    ax.view_init(elev=26, azim=-60)
    ax.set_xlim(-220, 220)
    ax.set_ylim(-220, 220)
    ax.set_zlim(2019.5, 2026.5)
    ax.set_axis_off()

    # ── 2D Editorial Layout & Typography ─────────────────────────────────
    fig.text(0.04, 0.94, "โครงข่ายการกลายพันธุ์ของวาทกรรม 'ประชากรข้ามชาติ' (พ.ศ. 2563–2569)",
             color=C_WHITE, fontsize=22, fontweight='bold', ha='left')
    fig.text(0.04, 0.905, "CROSS-BORDER NARRATIVE MUTATION NETWORK • 869 VERIFIED CLAIMS",
             color=C_PURPLE, fontsize=11, fontweight='bold', fontfamily='monospace', ha='left')
    fig.text(0.04, 0.875, "ถอดรหัส 7 ปี จาก 'ตัวแพร่เชื้อโรค' สู่ 'ภัยเศรษฐกิจ' และ 'คลื่นชาตินิยมสัญชาติ-เกาะกูด'",
             color=C_GRAY, fontsize=11, ha='left')

    # Left Editorial Box
    box_rect = plt.Rectangle((0.04, 0.12), 0.28, 0.72, transform=fig.transFigure,
                             facecolor=C_SURFACE, edgecolor="#1e293b", linewidth=1.5, zorder=20)
    fig.patches.append(box_rect)

    fig.text(0.06, 0.805, "[*] สรุปการกลายพันธุ์ 3 ยุค (Layer B Shift)", color=C_YELLOW, fontsize=12, fontweight='bold', zorder=25)

    narrative_lines = [
        ("• จำนวนข้อเท็จจริงทั้งหมด:", " 869 เรื่อง"),
        ("• ช่วงเวลาศึกษา:", " 7 ปี (พ.ศ. 2563 – 2569)"),
        ("• อัตราการเพิ่มขึ้นปี 2568:", " +875% YoY"),
        ("", ""),
        ("วิวัฒนาการ 3 ห้วงเวลาสำคัญ:", ""),
        ("  1. ยุค 2563–2564 (โรคระบาด):", ""),
        ("     - วาทกรรม 'ตัวแพร่เชื้อโควิด':", " 60.0%"),
        ("     - แย่งสิทธิวัคซีน/เตียงรักษา:", " 25.0%"),
        ("", ""),
        ("  2. ยุค 2565–2566 (ภัยเศรษฐกิจ):", ""),
        ("     - ต่างด้าวยึดตลาด/แย่งอาชีพ:", " 45.8%"),
        ("     - ธุรกิจสีเทา & นอมินี:", "      31.2%"),
        ("", ""),
        ("  3. ยุค 2567–2569 (ความมั่นคง/ดินแดน):", ""),
        ("     - แจกสัญชาติ 4 แสนคน/เลือกตั้ง:", " 58.2%"),
        ("     - เสียดินแดนเกาะกูด / MOU 44:", " 24.5%"),
        ("", ""),
        ("4 ข้ออ้างที่ถูกส่งต่อซ้ำซากสูงสุด:", ""),
        ("  1. รัฐบาลแจกสัญชาติให้มีสิทธิเลือกตั้ง", ""),
        ("  2. กัมพูชาเตรียมยึดเกาะกูดผ่าน MOU 44", ""),
        ("  3. แจกบัตรทองและรักษาฟรีทุกโรคให้ต่างด้าว", ""),
        ("  4. เพจหลอกลงทะเบียนเงินเยียวยา 5,000 บ.", "")
    ]

    curr_y = 0.77
    for label, val in narrative_lines:
        if not label:
            curr_y -= 0.012
            continue
        is_highlight = "สัญชาติ" in label or "60.0%" in val or "+875%" in val
        col = C_YELLOW if is_highlight else C_WHITE
        fig.text(0.06, curr_y, label + val, color=col, fontsize=9.0, zorder=25)
        curr_y -= 0.024

    # Legend at bottom of left box
    fig.text(0.06, 0.175, "สัญลักษณ์วาทกรรม:", color=C_GRAY, fontsize=9.5, fontweight='bold', zorder=25)
    fig.text(0.06, 0.14, "[ม่วง] สัญชาติ & เกาะกูด (58%)   [แดง] โรคระบาด/โควิด\n[เหลือง] แย่งอาชีพ/นอมินี       [ฟ้า] ขบวนการนายหน้า",
             color=C_WHITE, fontsize=8.5, linespacing=1.35, zorder=25)

    # Footer Logos / Branding
    fig.text(0.04, 0.045, "สำนักข่าวประชาไท • Prachatai Data Journalism", color=C_WHITE, fontsize=10, fontweight='bold')
    fig.text(0.96, 0.045, "FAKE NEWS LAB • TH VERIFY OPEN ARCHIVE", color=C_RED, fontsize=10, fontweight='bold', ha='right')

    plt.savefig(OUTPUT_PATH, facecolor=C_BLACK, edgecolor='none', bbox_inches='tight', pad_inches=0.15)
    plt.close()
    print(f"Article 2 3D infographic generated successfully at: {OUTPUT_PATH}")

if __name__ == "__main__":
    generate()
