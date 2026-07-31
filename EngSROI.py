import streamlit as st
from google import genai
from google.genai import types
import pandas as pd
import json
import time
import pypdf  # <--- เพิ่มไลบรารีสำหรับอ่าน PDF

# 1. ตั้งค่าหน้าเว็บ (ต้องอยู่บรรทัดแรกสุดเสมอ)
st.set_page_config(page_title="Research Project SROI Evaluator", layout="wide")
st.title("ระบบสกัดข้อมูลโครงการวิจัยและประเมินผลตอบแทนทางสังคม (SROI)")
st.markdown("อัปโหลดไฟล์เอกสารโครงการวิจัยเพื่อวิเคราะห์ข้อมูลเชิงยุทธศาสตร์ SDGs และคำนวณ SROI เบื้องต้น")

# [ตั้งค่า session_state เพื่อป้องกันข้อมูลหายตอนกดดาวน์โหลด]
if 'df_thai' not in st.session_state:
    st.session_state.df_thai = None

# 2. รับค่า API Key
api_key = st.text_input("กรุณาใส่ Gemini API Key ของคุณ", type="password")

# 3. ส่วนอัปโหลดไฟล์
uploaded_files = st.file_uploader("เลือกไฟล์เอกสารโครงการวิจัย (PDF)", type="pdf", accept_multiple_files=True)

if st.button("เริ่มประมวลผลโครงการ") and uploaded_files and api_key:
    client = genai.Client(api_key=api_key) 
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    # เปลี่ยนตัวเลขตัวอย่างเป็น 0 ทั้งหมดเพื่อไม่ให้ AI สับสน
    base_prompt = """
    คุณคือผู้เชี่ยวชาญด้านการประเมินโครงการวิจัยและผู้เชี่ยวชาญด้าน SROI กรุณาอ่านเอกสารโครงการที่แนบมา และสกัดข้อมูลออกมาในรูปแบบ JSON เท่านั้น โครงสร้างตามนี้:
    {
        "project_name": "ชื่อโครงการวิจัย",
        "project_leader": "ชื่อหัวหน้าโครงการ",
        "co_researchers": "รายชื่อผู้ร่วมวิจัย (คั่นด้วยลูกน้ำ)",
        "summary": "รายละเอียดโครงการโดยย่อ",
        "target_area": "พื้นที่ หรือ กลุ่มเป้าหมายของโครงการ",
        "duration": "ระยะเวลาโครงการ (เช่น 1 ปี, 6 เดือน)",
        "fiscal_year": "ปีงบประมาณ (เช่น 2569)",
        "output": "ผลผลิต (Output) ที่ได้โดยตรงจากโครงการ",
        "outcome": "ผลลัพธ์ (Outcome) ที่เกิดขึ้นกับกลุ่มเป้าหมาย",
        "impact": "ผลกระทบ (Impact) เชิงนโยบาย เศรษฐกิจ หรือสิ่งแวดล้อมในวงกว้าง",
        "primary_sdg": "SDG หลักที่เกี่ยวข้องโดยตรงที่สุด (เช่น SDG 9)",
        "secondary_sdg": "SDG ย่อยที่สนับสนุน (เช่น SDG 13)",
        "total_investment": 0, 
        "beneficiary_count": 0,
        "financial_proxy_value": 0,
        "financial_proxy_explanation": "คำอธิบายที่มาของการแทนค่าทางการเงิน (Financial Proxy) ว่าอ้างอิงจากอะไรหรือคิดอย่างไรสำหรับการตีมูลค่าผลลัพธ์นี้เป็นเงิน",
        "deadweight_pct": 0,
        "attribution_pct": 0
    }
    หมายเหตุ:
    - สำหรับค่า total_investment, beneficiary_count, financial_proxy_value, deadweight_pct, attribution_pct ให้หาข้อมูลจากในเล่ม หากไม่พบจริงๆ ให้คุณทำการประมาณการ (Estimate) ตัวเลขที่เหมาะสมตามหลักการประเมิน SROI และคืนค่ากลับมาเป็นตัวเลข (Number) ห้ามใส่ข้อความหรือเครื่องหมายจุลภาคในฟิลด์ตัวเลขเหล่านี้
    - ฟิลด์อธิบายทั้งหมดต้องเขียนเป็นภาษาไทย
    """

    for i, file in enumerate(uploaded_files):
        status_text.text(f"กำลังประมวลผลโครงการที่ {i+1}/{len(uploaded_files)}: {file.name}")
        
        try:
            # ---------------------------------------------------------
            # ส่วนที่เพิ่มเข้ามาใหม่: อ่านข้อความจาก PDF ด้วย pypdf
            # ---------------------------------------------------------
            pdf_reader = pypdf.PdfReader(file)
            extracted_text = ""
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
            
            # นำข้อความที่สกัดได้ มาต่อท้าย Prompt ของเรา
            full_prompt = f"{base_prompt}\n\nเนื้อหาเอกสารโครงการวิจัย:\n{extracted_text}"

            # ส่งให้ Gemini 2.0 Flash (ส่งเป็น Text ปกติ ไม่ได้ส่งไฟล์)
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )
            
            data = json.loads(response.text)
            # ---------------------------------------------------------
            
            # คำนวณ SROI
            investment = float(data.get("total_investment", 0))
            count = float(data.get("beneficiary_count", 0))
            proxy = float(data.get("financial_proxy_value", 0))
            deadweight = float(data.get("deadweight_pct", 0)) / 100.0
            attribution = float(data.get("attribution_pct", 0)) / 100.0
            
            gross_value = count * proxy
            net_impact_value = gross_value * (1 - deadweight) * (1 - attribution)
            sroi_ratio = net_impact_value / investment if investment > 0 else 0
            
            data["net_impact_value"] = round(net_impact_value, 2)
            data["sroi_ratio"] = round(sroi_ratio, 2)
            data["file_name"] = file.name 
            
            results.append(data)
            
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดกับไฟล์ {file.name}: {e}")
            
        progress_bar.progress((i + 1) / len(uploaded_files))
        
        # หน่วงเวลา 20 วินาทีเพื่อป้องกัน API Limit (เว้นไฟล์สุดท้ายไม่ต้องหน่วง)
        if i < len(uploaded_files) - 1:
            status_text.text(f"พักระบบ 20 วินาทีก่อนประมวลผลไฟล์ถัดไป เพื่อป้องกันข้อจำกัด API...")
            time.sleep(20)

    status_text.text("ประมวลผลและคำนวณ SROI เสร็จสิ้น!")

    if results:
        df = pd.DataFrame(results)
        
        cols = [
            "file_name", "project_name", "project_leader", "co_researchers", "summary", 
            "target_area", "duration", "fiscal_year", "output", "outcome", "impact", 
            "primary_sdg", "secondary_sdg", "total_investment", "net_impact_value", "sroi_ratio", "financial_proxy_explanation"
        ]
        df = df.reindex(columns=cols)
        
        df_thai = df.rename(columns={
            "file_name": "ชื่อไฟล์",
            "project_name": "ชื่อโครงการ",
            "project_leader": "หัวหน้าโครงการ",
            "co_researchers": "ผู้ร่วมวิจัย",
            "summary": "สรุปโครงการ",
            "target_area": "พื้นที่/กลุ่มเป้าหมาย",
            "duration": "ระยะเวลา",
            "fiscal_year": "ปีงบประมาณ",
            "output": "ผลผลิต (Output)",
            "outcome": "ผลลัพธ์ (Outcome)",
            "impact": "ผลกระทบ (Impact)",
            "primary_sdg": "SDG หลัก",
            "secondary_sdg": "SDG ย่อย",
            "total_investment": "เงินลงทุนโครงการ (บาท)",
            "net_impact_value": "มูลค่าผลกระทบทางสังคมสุทธิ (บาท)",
            "sroi_ratio": "อัตราส่วน SROI (เท่า)",
            "financial_proxy_explanation": "ที่มาและคำอธิบาย SROI"
        })
        
        # บันทึกตารางลงตัวแปร state เพื่อไม่ให้ข้อมูลหาย
        st.session_state.df_thai = df_thai

# 4. แสดงผลตารางและปุ่มดาวน์โหลด (นำออกมาไว้นอกเงื่อนไขปุ่มรัน)
if st.session_state.df_thai is not None:
    st.subheader("📊 ตารางสรุปข้อมูลโครงการวิจัยและการประเมิน SROI")
    st.dataframe(st.session_state.df_thai)

    csv = st.session_state.df_thai.to_csv(index=False).encode('utf-8-sig') 
    st.download_button(
        label="📥 ดาวน์โหลดรายงานโครงการวิจัยและ SROI (.CSV)",
        data=csv,
        file_name="สรุปโครงการวิจัยและคำนวณ_SROI.csv",
        mime="text/csv",
    )
