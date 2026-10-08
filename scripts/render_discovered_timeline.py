"""Static Thai figures and source-backed newsroom readout for the fitted run."""
import os
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/thverify-mpl')
import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from discovered_timeline import OUT,read,write,sha
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
FONT='/System/Library/Fonts/Supplemental/Thonburi.ttc'
font_manager.fontManager.addfont(FONT)
plt.rcParams.update({'font.family':font_manager.FontProperties(fname=FONT).get_name(),'font.size':11,
    'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#242424','text.color':'#242424','svg.fonttype':'path'})
LABELS={0:'สุขภาพ/อาหาร/การรักษา (กลุ่มใหญ่)',1:'ลงทุน–ปันผล–ตลาดหลักทรัพย์',2:'รับทำใบขับขี่ออนไลน์',
    4:'ป้องกัน/รักษาไวรัส (รวมโควิด)',6:'ทหารและชายแดนไทย–กัมพูชา',7:'ข่าวเชื้อโรค/การระบาด (กลุ่มผสม)',
    11:'อ้างคืนเงินให้ผู้เสียหาย',18:'วัคซีนโควิด',28:'แรงงาน/การส่งกลับ',49:'สัญชาติ/เอกสารบุคคล'}
MLABELS={-1:'จัดกลุ่มไม่ได้ (noise)',0:'แรงงาน/การเคลื่อนย้าย/ส่งกลับ',1:'สัญชาติ/เอกสาร/การขึ้นทะเบียน',
    2:'ด่าน/พื้นที่ชายแดน/บริการ',3:'เมียนมา/ค่าแรง/นายหน้า (ผสม)',4:'ลักลอบ/มุสลิม/ภูเก็ต/ขอทาน',5:'เด็ก/โรงเรียน/สิทธิการศึกษา'}

def main():
    timeline=read(OUT/'topic_timeline.csv'); mt=read(OUT/'migrant_screened_timeline.csv')
    metrics=json.loads((OUT/'metrics.json').read_text()); mm=json.loads((OUT/'migrant_screened_metrics.json').read_text())
    contract={'surface':'local newsroom Markdown + standalone PNG/SVG exports',
        'overview':{'family':'line small multiples','question':'Which discovered topics rise or fall in archive share?',
            'points':12,'selected_topics':[4,7,1,2,11,6],'denominator':'all eligible records per year including noise',
            'palette':'single blue root','partial_years':[2015,2026],'not_full_inventory':True},
        'migrant':{'family':'heatmap','question':'When do the six discovered subthemes occur in the assistant-screened pool?',
            'years':7,'cells':'counts, not validated frame prevalence','palette':'single blue root',
            'low_n':'annual n printed; no zero extrapolation before 2020'}}
    (OUT/'chart_contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2))
    years=list(range(2015,2027)); selected=[4,7,1,2,11,6]
    fig,axes=plt.subplots(3,2,figsize=(14,10),sharex=True,sharey=True)
    for ax,t in zip(axes.flat,selected):
        group=[next(r for r in timeline if r['source']=='all' and int(r['year'])==y and int(r['topic_id'])==t) for y in years]
        values=[float(r['share_pct']) for r in group]
        ax.plot(years,values,color='#245D91',marker='o',ms=4,lw=2)
        ax.axvspan(2025.6,2026.4,color='#eeeeee'); ax.axvspan(2014.6,2015.4,color='#eeeeee')
        ax.set_title(f'Topic {t} · {LABELS[t]}',loc='left',fontsize=12,pad=12)
        ax.set_ylim(0,12); ax.set_yticks([0,3,6,9,12]); ax.grid(axis='y',alpha=.18)
        ticks=years[::2]+[2026]
        ax.set_xticks(ticks); ax.set_xticklabels([str(y+543) for y in ticks],fontsize=9)
        ax.tick_params(labelleft=True)
        ax.set_ylabel('สัดส่วนในคลัง (%)')
    fig.suptitle('หัวข้อที่ BERTopic ค้นพบ: สัดส่วนรายปี 2558–2569',fontsize=19,x=.07,ha='left')
    fig.text(.07,.93,'6 หัวข้อคัดแสดงจาก 64 หัวข้อ · ชื่อย่อเป็นคำอธิบายเบื้องต้น ไม่ใช่ชื่อที่มนุษย์รับรอง',fontsize=11)
    fig.text(.07,.035,'ตัวหาร = บันทึกที่ผ่านเกณฑ์ทั้งหมดในแต่ละปี รวม noise · พื้นเทา = ปีไม่เต็ม · ไม่ใช่ความชุกข่าวลวงในประชากรไทย',fontsize=10)
    fig.subplots_adjust(top=.87,bottom=.10,hspace=.46,wspace=.22)
    fig.savefig(OUT/'overview_timelines.png',dpi=150); fig.savefig(OUT/'overview_timelines.svg'); plt.close(fig)
    # Whole inventory: within-row peak normalization makes small-topic trajectories visible.
    topic_info=read(OUT/'topics.csv')
    ordered=[r for r in topic_info if r['topic_id']!='-1']+[r for r in topic_info if r['topic_id']=='-1']
    for page, subset in enumerate([ordered[:33],ordered[33:]],1):
        matrix=[]; labels=[]
        for info in subset:
            values=np.array([float(next(r for r in timeline if r['source']=='all' and int(r['year'])==y and r['topic_id']==info['topic_id'])['share_pct']) for y in years])
            peak=values.max(); matrix.append(values/peak if peak else values)
            label=' / '.join(info['machine_keywords'].split(' | ')[:3])
            labels.append(f'{info["topic_id"]}: {label[:35]}  (สูงสุด {peak:.1f}%)')
        fig,ax=plt.subplots(figsize=(15,15))
        im=ax.imshow(matrix,cmap='Blues',vmin=0,vmax=1,aspect='auto')
        ax.set_yticks(range(len(subset)),labels,fontsize=9)
        ax.set_xticks(range(12),[str(y+543)+('*' if y in [2015,2026] else '') for y in years],fontsize=9)
        fig.colorbar(im,ax=ax,label='สัดส่วนรายปี ÷ สัดส่วนสูงสุดของหัวข้อเดียวกัน',fraction=.022,pad=.02)
        fig.suptitle(f'เส้นเวลาทุกหัวข้อที่ค้นพบ — หน้า {page}/2',x=.04,ha='left',fontsize=20)
        fig.text(.04,.94,'ความเข้มเปรียบเทียบภายในแถวเท่านั้น · สีเท่ากันคนละแถวไม่ได้แปลว่ามีสัดส่วนเท่ากัน',fontsize=11)
        fig.text(.04,.027,'ชื่อเป็นคำสำคัญอัตโนมัติ · ตัวเลขในวงเล็บคือสัดส่วนสูงสุดจริงในคลัง · *ปีไม่เต็ม · รวม noise เป็นแถว -1',fontsize=10)
        fig.subplots_adjust(left=.40,right=.94,top=.90,bottom=.065)
        fig.savefig(OUT/f'all_topics_heatmap_{page}.png',dpi=140); fig.savefig(OUT/f'all_topics_heatmap_{page}.svg'); plt.close(fig)
    myears=list(range(2020,2027)); mids=[0,1,2,3,4,5,-1]
    data=np.array([[int(next(r for r in mt if r['scope']=='all_screened' and int(r['year'])==y and int(r['subtopic_id'])==t)['count']) for y in myears] for t in mids])
    ns=[int(next(r for r in mt if r['scope']=='all_screened' and int(r['year'])==y)['denominator']) for y in myears]
    fig,ax=plt.subplots(figsize=(14,7))
    from matplotlib.colors import LinearSegmentedColormap
    im=ax.imshow(data,cmap=LinearSegmentedColormap.from_list('archive_blue',['#f5f8fb','#245D91']),vmin=0,vmax=max(1,data.max()),aspect='auto')
    ax.set_xticks(range(7),[f'{y+543}{"*" if y==2026 else ""}\nn={n}' for y,n in zip(myears,ns)])
    ax.set_yticks(range(7),[f'{t}: {MLABELS[t]}' for t in mids])
    for i in range(7):
        for j in range(7): ax.text(j,i,str(data[i,j]),ha='center',va='center',color='white' if data[i,j]>data.max()*.6 else '#242424')
    fig.colorbar(im,ax=ax,label='จำนวนบันทึก',fraction=.025,pad=.025)
    fig.suptitle('เรื่องคนข้ามชาติ: หัวข้อย่อยที่ค้นพบตามเวลา',fontsize=19,x=.05,ha='left')
    fig.text(.05,.89,f'คัดขอบเขตโดยผู้ช่วยจากชื่อข่าว/ข้ออ้าง {mm["assistant_in_scope"]} บันทึก · ยังไม่ใช่กรอบวาทกรรมที่มนุษย์ตรวจรับรอง',fontsize=11)
    fig.text(.05,.035,'ช่วงต้นมีเพียง 4–6 บันทึก/ปี · *2569 ไม่เต็มปี · n เปลี่ยนตามขนาดคิว · สีแสดงจำนวน ไม่ใช่สัดส่วนความเกลียดชัง',fontsize=10)
    fig.subplots_adjust(left=.32,right=.93,top=.82,bottom=.15)
    fig.savefig(OUT/'migrant_subtopic_timeline.png',dpi=150); fig.savefig(OUT/'migrant_subtopic_timeline.svg'); plt.close(fig)
    # Exact period comparisons, including publisher-specific and dedup sensitivity.
    assignments=read(OUT/'assignments.csv'); period=[]
    leak_rx=re.compile(r'ข่าวปลอม|อย่าแชร์|สร้างความเข้าใจผิด|สร้างความปั่นป่วน')
    leak_rows=[dict(r,diagnostic='possible editorial leakage; keyword flag requires reading, not automatic exclusion')
               for r in assignments if leak_rx.search(r['claim_text'])]
    write('residual_editorial_review.csv',leak_rows)
    for t in [0,1,2,4,6,7,11,18,28,49]:
        for source in ['all','afnc','afp','sure_share']:
            for start,end in [(2020,2021),(2024,2025)]:
                group=[r for r in assignments if start<=int(r['year'])<=end and (source=='all' or r['source']==source)]
                for method in ['records','source_year_text_dedup','false_only']:
                    sample=group
                    if method=='source_year_text_dedup': sample=list({(r['source'],r['year'],r['text_family']):r for r in group}.values())
                    if method=='false_only': sample=[r for r in group if r['verdict']=='false']
                    count=sum(int(r['topic_id'])==t for r in sample)
                    period.append(dict(topic_id=t,period=f'{start}-{end}',source=source,method=method,count=count,
                        denominator=len(sample),share_pct=100*count/len(sample) if sample else ''))
    write('editorial_period_comparisons.csv',period)
    md=['# ผล BERTopic และเส้นเวลาหัวข้อ — ชุดวิเคราะห์สำหรับนักข่าว',
        '\nรันจริง 8 กันยายน 2569 บน snapshot เดิม (วันตัด 2 กันยายน 2569) ไม่ใช่ข้อมูลสดและไม่ใช่บทความพร้อมตีพิมพ์',
        f'\nฐาน 14,429 บันทึก → ข้อความตรงกันทุกตัวอักษรไม่ซ้ำ 13,377 → BERTopic ค้นพบ {metrics["discovered_topics"]} หัวข้อ; noise {metrics["noise_records"]:,} บันทึก ({metrics["noise_share_pct"]:.2f}%) โดยไม่บังคับเข้า 10 หมวดเดิม',
        '\n## อ่านกราฟเวลา',
        '\n![สัดส่วนหัวข้อที่ค้นพบรายปี](overview_timelines.png)',
        '\nชื่อไทยสั้น ๆ ในกราฟเป็นการตีความเบื้องต้นจากคำสำคัญและตัวอย่าง ไม่ใช่ชื่อที่ผู้เชี่ยวชาญตรวจครบ ทั้ง 64 หัวข้อพร้อมตัวแทนอยู่ใน [topics.csv](topics.csv); ทุกแถวเชื่อมรหัสข่าวและ URL ใน [assignments.csv](assignments.csv)',
        '\nดูครบทุกหัวข้อ: [Heatmap หน้า 1](all_topics_heatmap_1.png) และ [หน้า 2](all_topics_heatmap_2.png) ความเข้มในภาพนี้เทียบกับจุดสูงสุดของหัวข้อเดียวกัน ไม่ใช้เปรียบเทียบขนาดระหว่างหัวข้อ; สัดส่วนจริงรายปีอยู่ใน CSV',
        '\n## ข้อค้นพบเรื่องแรก: ไม่ใช่แค่สุขภาพลด–การเงินเพิ่ม',
        '\n| หัวข้อค้นพบ (คำอธิบายเบื้องต้น) | 2563–2564 | 2567–2568 |',
        '|---|---:|---:|']
    for t in [4,7,1,2,11,6]:
        cells=[]
        for per in ['2020-2021','2024-2025']:
            r=next(r for r in period if r['topic_id']==t and r['source']=='all' and r['method']=='records' and r['period']==per)
            cells.append(f'{r["count"]:,}/{r["denominator"]:,} ({r["share_pct"]:.2f}%)')
        md.append(f'| {t}: {LABELS[t]} | '+ ' | '.join(cells)+' |')
    md += ['\nที่มา [ตารางเปรียบเทียบและความไว](editorial_period_comparisons.csv) หัวข้อค้นพบไม่เท่ากับกฎ T01–T10 เดิม ห้ามใช้รหัสสลับกัน',
        '\nสิ่งที่เพิ่มจากการนับคำค้นคือกลุ่มรับทำใบขับขี่ออนไลน์และกลุ่มอ้างคืนเงินผู้เสียหายที่ปรากฏเป็นหัวข้อแยก รวมถึงการแยกข่าวโควิดออกเป็นข้ออ้างรักษา/ป้องกัน ข่าวพบผู้ติดเชื้อ และวัคซีน ไม่ควรเหมารวมว่ามีเส้นทางเดียวกันทั้งหมด',
        '\nการตรวจตัวอย่างพบ Topic 4 มีข้ออ้างขับไวรัสด้วยน้ำร้อนปี 2561 (ID 25714) และ Topic 7 มีไข้เลือดออกปี 2560 รวมถึงข่าวอาหารที่ใช้คำระบาดปี 2559 จึงใช้ชื่อกลุ่มกว้าง ไม่เรียกทุกแถวว่าโควิด และต้องตรวจความบริสุทธิ์ของหัวข้อก่อนตีพิมพ์',
        '\nกลุ่มลงทุน Topic 1 เพิ่มเมื่อเทียบสองช่วง แต่รายปีลดจาก 99 บันทึก (4.11%) ใน 2567 เป็น 30 (1.24%) ใน 2568 จึงไม่ควรเขียนว่าเติบโตต่อเนื่องทุกปี หรือเหมารวมเป็นการลงทุนทุกชนิด',
        '\nTopic 0 ใหญ่มาก (5,292 บันทึก) และยังผสมสุขภาพ/อาหาร/การรักษาหลายเรื่อง เป็นข้อจำกัดของความละเอียดโมเดล ส่วนอันดับการเปลี่ยน 2567→2568 มี noise เพิ่มเป็นตัวขับสำคัญ ไม่ควรตีความว่าเกิดวาทกรรมใหม่เพียงอย่างเดียว',
        f'\nข้อจำกัดที่ตรวจพบหลัง fit: {len(leak_rows)} บันทึกยังตรงคำที่อาจเป็นคำเฉลย/คำเตือนตกค้าง ดู [คิวตรวจข้อความ](residual_editorial_review.csv) โดย Topic 54 มีตัวอย่างจัดกลุ่มตามสำนวนแก้ข่าวมากกว่าหัวข้อข่าว จึงห้ามเขียนว่าได้ 64 หัวข้อบริสุทธิ์ที่ยืนยันแล้ว ผลนี้เป็น exploratory run ไม่ใช่ taxonomy พร้อมตีพิมพ์',
        '\nทดสอบตัด 82 บันทึกที่ตรงคำเตือนแล้ว fit UMAP/HDBSCAN ใหม่จริง: เหลือ 14,347 บันทึก ได้ 56 กลุ่ม (ARI เทียบรอบหลัก 0.848) กลุ่มที่จับคู่กับหัวข้อคัดแสดงทั้งหกยังมีทิศทางต้นช่วง→ปลายช่วงเหมือนเดิม แต่ขอบเขตและขนาดเปลี่ยน เช่นกลุ่มชายแดนมี Jaccard เพียง 0.370 จึงไม่ควรยืนยันจำนวนกลุ่มหรือขนาดผลว่าเสถียร ดู [ตารางทดสอบคำเฉลยตกค้าง](leakage_exclusion_sensitivity.csv) และ [รายละเอียด](leakage_sensitivity_metrics.json) การตัดคำเตือนเป็น sensitivity ไม่ใช่การรับรองว่าทุกแถวที่ตัดผิดหรือทุกแถวที่เหลือสะอาด',
        '\n## เรื่องที่สอง: หัวข้อย่อยซ้อนกัน ไม่ได้ยืนยันสามยุค',
        f'\nค้นขยายด้วยความหมายได้คิว 332 บันทึก จากนั้นผู้ช่วยอ่านชื่อข่าว/ข้ออ้างและเสนอคัดเข้า {mm["assistant_in_scope"]} บันทึก (บริบทผู้อยู่อาศัย/แรงงาน/สถานะ 99; คนและบริการข้ามแดน 19), กำกวม 7, เสนอคัดออก 207 ทุกการตัดสินอยู่ใน [แฟ้มตรวจขอบเขต](migrant_scope_decisions.csv) และรอนักข่าวตรวจต้นทาง',
        '\n![หัวข้อย่อยคนข้ามชาติตามเวลา](migrant_subtopic_timeline.png)',
        '\nโมเดลย่อยค้นพบ 6 หัวข้อและ noise 11 บันทึก ชื่อกลุ่มเป็นหัวข้อผสม ไม่ใช่การรับรองกรอบโจมตี/ความเกลียดชัง โดยเฉพาะกลุ่มเอกสารรวมใบขับขี่ด้วย และกลุ่มเมียนมาผสมค่าแรงกับนายหน้า',
        '\nเบาะแสสำคัญ: กลุ่มการศึกษา (subtopic 5) มี 1 บันทึกใน 2568 และ 8 ใน 2569; กลุ่มลักลอบ/มุสลิม/ภูเก็ต (subtopic 4) พบตั้งแต่ 2564 และยังพบใน 2569 ขณะที่กลุ่มสัญชาติ/เอกสารมีตัวอย่างตั้งแต่ 2563 ดังนั้นอย่าเขียนว่าสิทธิเพิ่งปรากฏหลังปี 2568',
        '\nข้ออ้างปลดล็อก 5 อาชีพที่กลับมาหลายปีถูกจัดเป็น noise ในโมเดลย่อย แสดงว่าข่าวที่นักข่าวเห็นคุณค่าอาจไม่กลายเป็นคลัสเตอร์ โมเดลไม่พบคลัสเตอร์โรคแยกก็ไม่ได้พิสูจน์ว่ากรอบโรคไม่เคยมีอยู่',
        '\nข้อควรระวังเพิ่มเติมจากโมเดลใหญ่: Topic 28 เพิ่มในสัดส่วนรวมสองช่วง แต่เมื่อให้น้ำหนักสามสำนักที่เทียบได้เท่ากัน ผลต่างเหลือประมาณ +0.033 จุดเปอร์เซ็นต์ (p เชิงสำรวจ 0.960) จึงไม่มีหลักฐานจากการทดสอบนี้ให้กล่าวว่ากลุ่มแรงงาน/ส่งกลับเพิ่มโดยไม่เกี่ยวกับส่วนผสมสำนัก',
        '\n[หัวข้อย่อยและตัวแทน](migrant_screened_topics.csv) · [ทุกข่าวพร้อมหัวข้อย่อย](migrant_screened_assignments.csv) · [เส้นเวลาสองขอบเขต](migrant_screened_timeline.csv) · [คำสำคัญรายปี](migrant_screened_words_over_time.csv)',
        '\n## วิธีวิจัยและข้อจำกัด',
        '\n1. ใช้เวกเตอร์ E5 เดิมเฉพาะข้อความตรงกันทุกตัวอักษร 13,154 ข้อความ และเข้ารหัสเพิ่ม 223 ผ่าน `th_verify.search.build_index` นำหน้าด้วย passage และทำ L2 normalization; ไม่แก้ SQLite',
        '\n2. UMAP 10 มิติ (cosine, neighbors=15, seed=42) แล้ว HDBSCAN min_cluster_size=30/min_samples=5; ทดลองขนาด 15/30/50/80 ได้ 161/64/43/33 กลุ่มตามลำดับ จำนวน 64 จึงเป็นผลของพารามิเตอร์ ไม่ใช่จำนวนหัวข้อจริงในสังคม',
        '\n3. BERTopic 0.17.4 ใช้ภาษา multilingual และตัดคำไทย newmm ก่อน c-TF-IDF คำนวณหัวข้อร่วมครั้งเดียวและคำสำคัญรายปีด้วย topics_over_time โดยปิด smoothing ทั้งสองแบบ เพื่อไม่ทำให้เส้นเวลาเนื้อหาดูเรียบเกินหลักฐาน [เอกสารวิธี](https://maartengr.github.io/BERTopic/getting_started/topicsovertime/topicsovertime.html)',
        '\n4. นับคืนทุกบันทึกตามวันเผยแพร่บทตรวจสอบ ไม่ใช่วันที่โพสต์ลวงครั้งแรก เก็บ noise ในตัวหาร แยกสำนักและทดสอบตัดข้อความซ้ำสำนัก–ปี/ผล false ไว้ในตาราง ช่วงต้นและปี 2569 ไม่เต็มปี',
        '\n5. [Jensen–Shannon distance](adjacent_year_shifts.csv) คือระยะห่างองค์ประกอบระหว่างปี รวม noise ไม่ใช่การยืนยัน change point หรือสาเหตุ อันดับแรกคือ 2562→2563 (0.4903); อันดับสอง 2567→2568 (0.3702)',
        '\n6. [Permutation](source_balanced_tests.csv) 2,000 รอบ ใช้จำนวนต้น/ปลายจริงภายในแต่ละสำนักที่มีอย่างน้อย 20 บันทึกทั้งสองช่วง (AFNC, AFP, ชัวร์ก่อนแชร์) เฉลี่ยส่วนต่างโดยให้น้ำหนักสำนักเท่ากัน p=(exceed+1)/2001 แล้ว BH-FDR ทุกหัวข้อรวม noise ผลเป็น exploratory: ยังไม่แก้การพึ่งพากันของข้ออ้างซ้ำ/เวลาและความไม่แน่นอนของการเลือกโมเดล จึงไม่เรียกว่าเป็นหลักฐานยืนยันระดับประเทศ',
        '\n7. โมเดลย่อยใช้ขอบเขตที่ผู้ช่วยคัดจากข้อความ ไม่ใช่ผู้เชี่ยวชาญตรวจเต็มบท ใช้ UMAP 5 มิติ + HDBSCAN leaf (8/3) เพื่อหากลุ่มละเอียด พร้อม [การทดลองพารามิเตอร์](migrant_screened_sensitivity.csv) การเพิ่มคิวเป็น top-200 เพื่อนบ้านของ seed ไม่ใช่ threshold ความเกี่ยวข้องที่ผ่าน validation',
        '\n8. แยกหัวข้อออกจากกรอบเรื่องเล่า/เจตนา: ช่อง human_frame ยังคงว่าง ต้องตรวจหลักฐานเรื่องผู้ร้าย ผู้เสียหาย และการเรียกร้องสิทธิในข้อความจริง การนับ [ข้อความกลับมาข้ามปี](recurring_text_families.csv) ไม่ใช่การอ้างว่าค้นพบแม่แบบโน้มน้าวใจที่ตรวจแล้ว',
        '\n9. ยังมีความเสี่ยงข้อความสกัดขาด/คำเฉลยตกค้างในฐาน เช่น ID 15735 และบางข้อความจาก LLM; ตัวแทนคือข่าวใกล้ centroid ใน E5 เดิม ไม่ใช้ตำแหน่งภาพ 2D/3D เป็นหลักฐาน ไม่มีการตรวจ benchmark ความแม่นหัวข้อกับผู้เชี่ยวชาญในรอบนี้',
        '\n## ใช้งานต่อ',
        '\n[โครงเรื่อง 1 ฉบับใช้ผลโมเดล](story_1_model_outline_th.md) · [โครงเรื่อง 2 ฉบับใช้ผลโมเดล](story_2_model_outline_th.md)',
        '\nรันจากรากโครงการ: `.venv/bin/python scripts/discovered_timeline.py` แล้ว `.venv/bin/python scripts/migrant_discovered_review.py` และ `.venv/bin/python scripts/render_discovered_timeline.py` เก็บรุ่นแพ็กเกจและพารามิเตอร์ใน [config.json](config.json) และ [metrics.json](metrics.json); อย่าใช้โฟลเดอร์รันเดิมกับ snapshot ใหม่',
        '\nรันทดสอบคำเฉลยตกค้างเพิ่มด้วย `.venv/bin/python scripts/check_discovery_leakage.py` ก่อนสร้างรายงาน แพ็กเกจที่ใช้จริงตรึงไว้ใน [requirements-topic-analysis.txt](../../requirements-topic-analysis.txt) กรอกงานตรวจของนักข่าวในสำเนาแยก; สคริปต์สร้างไฟล์อนุพันธ์ใหม่และไม่ควรรันเขียนทับงานตรวจที่กรอกแล้ว',
        '\n[ผลตรวจข้อมูลและกราฟ](VERIFICATION.md): ผ่าน 23 ข้อรวมชุดก่อนหน้า; รอบโมเดลนี้โดยเฉพาะ 8 ข้อ',
        '\nสถานะ: ผลสำรวจจากโมเดลพร้อมตรวจต่อ ไม่ใช่ผลวาทกรรมที่มนุษย์รับรองหรือบทความพร้อมตีพิมพ์']
    (OUT/'README_TH.md').write_text('\n'.join(md)+'\n')
    manifest={'run':'20260908_bertopic_v001','status':'exploratory; human narrative validation pending',
        'artifacts_sha256':{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='artifact_manifest.json'},
        'scripts_sha256':{name:sha(Path(__file__).parent/name) for name in ['discovered_timeline.py','migrant_discovered_review.py','check_discovery_leakage.py','render_discovered_timeline.py']}}
    (OUT/'artifact_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
