import streamlit as st
from google import genai
from google.genai import types
import pandas as pd
import json
import pypdf

# 1. ตั้งค่าหน้าเว็บ
st.set_page_config(page_title="Research Project SROI Evaluator", layout="wide")
st.title("ระบบสกัดข้อมูลโครงการวิจัยและประเมินผลตอบแทนทางสังคม (SROI)")
st.markdown("อัปโหลดไฟล์เอกสารโครงการวิจัยเพื่อวิเคราะห์ข้อมูล SDGs และคำนวณ SROI แบบระมัดระวัง (Conservative Approach)")

if 'df_thai' not in st.session_state:
    st.session_state.df_thai = None

# 2. รับค่า API Key
api_key = st.text_input("กรุณาใส่ Gemini API Key ของคุณ", type="password")

# 3. ส่วนอัปโหลดไฟล์
uploaded_files = st.file_uploader(
    "เลือกไฟล์เอกสารโครงการวิจัย (PDF) - รวมทุกไฟล์ของโครงการเดียวกันได้", 
    type="pdf", 
    accept_multiple_files=True
)

if st.button("เริ่มประมวลผลโครงการ") and uploaded_files and api_key:
    client = genai.Client(api_key=api_key) 
    
    status_text = st.empty()
    progress_bar = st.progress(0)

    # Base Prompt ปรับปรุงเพิ่ม Guardrails และคำนวณมูลค่าปัจจุบัน vs อนาคต
    base_prompt = """
    คุณคือผู้เชี่ยวชาญด้านการประเมินโครงการวิจัยและผู้เชี่ยวชาญด้าน SROI ขั้นสูง
    กรุณาอ่านเอกสารโครงการวิจัยทั้งหมดที่แนบมา ซึ่งทั้งหมดนี้คือเอกสารของ "โครงการวิจัยเดียวกัน" 
    แล้วทำการวิเคราะห์สกัดข้อมูลออกมาเป็นชุดเดียวในรูปแบบ JSON เท่านั้น โครงสร้างตามนี้:
    {
        "project_name": "ชื่อโครงการวิจัย",
        "project_leader": "ชื่อหัวหน้าโครงการ",
        "co_researchers": "รายชื่อผู้ร่วมวิจัย (คั่นด้วยลูกน้ำ)",
        "summary": "รายละเอียดโครงการโดยย่อ",
        "target_area": "พื้นที่ หรือ กลุ่มเป้าหมายของโครงการ",
        "duration": "ระยะเวลาโครงการ (เช่น 8 เดือน)",
        "fiscal_year": "ปีงบประมาณ (เช่น 2568)",
        "output": "ผลผลิต (Output) ที่ได้โดยตรงจากโครงการ",
        "outcome": "ผลลัพธ์ (Outcome) ที่เกิดขึ้นกับกลุ่มเป้าหมาย",
        "impact": "ผลกระทบ (Impact) เชิงนโยบาย เศรษฐกิจ หรือสิ่งแวดล้อมในวงกว้าง",
        "primary_sdg": "SDG หลักที่เกี่ยวข้องโดยตรงที่สุด (เช่น SDG 7)",
        "secondary_sdg": "SDG ย่อยที่สนับสนุน (เช่น SDG 13)",
        "total_investment": 0, 
        "beneficiary_count": 0,
        "present_proxy_per_unit": 0,
        "present_proxy_explanation": "คำอธิบายการประเมินมูลค่าผลกระทบเชิงสังคมที่เกิดขึ้นจริง ณ ปัจจุบัน (ระหว่างดำเนินโครงการ)",
        "projected_proxy_per_unit": 0,
        "projected_proxy_explanation": "คำอธิบายการประเมินมูลค่าผลกระทบคาดการณ์ระยะยาว (3 ปีหลังจบโครงการ)",
        "deadweight_pct": 30,
        "attribution_pct": 30
    }

    กฎเหล็กในการประเมิน (CONSERVATIVE SROI RULES):
    1. **การคิดมูลค่าปัจจุบัน (present_proxy_per_unit):** 
       - ให้คิดเฉพาะผลกระทบที่เกิดขึ้นจริงในระยะเวลาโครงการ เช่น ค่าอบรมพัฒนาบุคลากร (Cost Avoidance ไม่เกิน 2,000-5,000 บาท/คน) หรือผลประหยัดจากการทดลองนำร่องเล็กๆ เท่านั้น 
       - ห้ามนำผลประโยชน์ระดับจังหวัดหรือระดับประเทศมาคิดในส่วนนี้เด็ดขาด
    2. **การคิดมูลค่าคาดการณ์อนาคต (projected_proxy_per_unit):** 
       - ประเมินผลกระทบคาดการณ์สะสม 3 ปี จากการนำผลงานวิจัย/แผนยุทธศาสตร์ไปใช้จริง โดยคิดบนฐานที่สมเหตุสมผลและระมัดระวัง
    3. **การหัก DISCOUNT FACTORS (บังคับหักเสมอ):**
       - deadweight_pct: ตั้งค่าระหว่าง 20 - 40% (ผลลัพธ์บางส่วนเกิดขึ้นเองอยู่แล้ว)
       - attribution_pct: ตั้งค่าระหว่าง 20 - 50% (ผลลัพธ์มีส่วนร่วมจากหน่วยงานอื่น)
    4. **ฟิลด์ตัวเลข:** คืนค่าเป็นตัวเลข純 (Number) ห้ามใส่เครื่องหมายจุลภาคหรือข้อความ
    5. **ภาษา:** ฟิลด์คำอธิบายทั้งหมดต้องเขียนเป็นภาษาไทย
    """

    try:
        combined_text = ""
        file_names = []
        MAX_PAGES_PER_FILE = 50

        for idx, file in enumerate(uploaded_files):
            file_names.append(file.name)
            status_text.text(f"กำลังอ่านเนื้อหาจากไฟล์ ({idx+1}/{len(uploaded_files)}): {file.name}")
            
            pdf_reader = pypdf.PdfReader(file)
            extracted_text = ""
            
            for page_num, page in enumerate(pdf_reader.pages):
                if page_num >= MAX_PAGES_PER_FILE:
                    break 
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
            
            combined_text += f"\n--- เริ่มต้นเนื้อหาจากไฟล์: {file.name} ---\n{extracted_text}\n--- สิ้นสุดเนื้อหาจากไฟล์: {file.name} ---\n"
            progress_bar.progress((idx + 1) / (len(uploaded_files) + 1))

        status_text.text("กำลังประมวลผลวิเคราะห์โครงการและคำนวณ SROI ด้วย Gemini...")
        
        full_prompt = f"{base_prompt}\n\nเนื้อหาเอกสารโครงการวิจัยทั้งหมดที่เกี่ยวข้อง:\n{combined_text}"

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        
        data = json.loads(response.text)
        
        # --- ตัวแปรคำนวณ ---
        investment = float(data.get("total_investment", 0))
        count = float(data.get("beneficiary_count", 0))
        
        deadweight = float(data.get("deadweight_pct", 30)) / 100.0
        attribution = float(data.get("attribution_pct", 30)) / 100.0
        net_factor = (1 - deadweight) * (1 - attribution)
        
        # 1. คำนวณ SROI ถึงปัจจุบัน (Present SROI)
        present_proxy = float(data.get("present_proxy_per_unit", 0))
        present_gross = count * present_proxy
        present_net_impact = present_gross * net_factor
        present_sroi_ratio = present_net_impact / investment if investment > 0 else 0
        
        # 2. คำนวณ SROI คาดการณ์ระยะยาว (Projected SROI - 3 Years)
        projected_proxy = float(data.get("projected_proxy_per_unit", 0))
        projected_gross = count * projected_proxy
        projected_net_impact = projected_gross * net_factor
        projected_sroi_ratio = projected_net_impact / investment if investment > 0 else 0
        
        # บันทึกค่าลง Data Dictionary
        data["file_name"] = ", ".join(file_names)
        data["present_net_impact"] = round(present_net_impact, 2)
        data["present_sroi_ratio"] = round(present_sroi_ratio, 2)
        data["projected_net_impact"] = round(projected_net_impact, 2)
        data["projected_sroi_ratio"] = round(projected_sroi_ratio, 2)

        progress_bar.progress(1.0)
        status_text.text("ประมวลผลและคำนวณ SROI เสร็จสิ้น!")

        # จัดทำ DataFrame พร้อมจัดลำดับคอลัมน์ใหม่
        df = pd.DataFrame([data])
        
        cols = [
            "file_name", "project_name", "project_leader", "co_researchers", "summary", 
            "target_area", "duration", "fiscal_year", "output", "outcome", "impact", 
            "primary_sdg", "secondary_sdg", "total_investment", 
            "present_net_impact", "present_sroi_ratio", "present_proxy_explanation",
            "projected_net_impact", "projected_sroi_ratio", "projected_proxy_explanation"
        ]
        df = df.reindex(columns=cols)
        
        df_thai = df.rename(columns={
            "file_name": "ไฟล์เอกสารที่ใช้",
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
            "present_net_impact": "มูลค่าผลกระทบสุทธิ [ปัจจุบัน] (บาท)",
            "present_sroi_ratio": "อัตราส่วน SROI [ปัจจุบัน] (เท่า)",
            "present_proxy_explanation": "คำอธิบาย SROI [ปัจจุบัน]",
            "projected_net_impact": "มูลค่าผลกระทบสุทธิ [คาดการณ์ระยะยาว] (บาท)",
            "projected_sroi_ratio": "อัตราส่วน SROI [คาดการณ์ระยะยาว] (เท่า)",
            "projected_proxy_explanation": "คำอธิบาย SROI [คาดการณ์ระยะยาว]"
        })
        
        st.session_state.df_thai = df_thai

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการประมวลผล: {e}")

# 4. แสดงผลตารางและปุ่มดาวน์โหลด
if st.session_state.df_thai is not None:
    st.subheader("📊 ตารางสรุปข้อมูลโครงการวิจัยและการประเมิน SROI")
    st.dataframe(st.session_state.df_thai)

    csv = st.session_state.df_thai.to_csv(index=False).encode('utf-8-sig') 
    st.download_button(
        label="📥 ดาวน์โหลดรายงานโครงการวิจัยและ SROI (.CSV)",
        data=csv,
        file_name="สรุปโครงการวิจัยและคำนวณ_SROI_Realistic.csv",
        mime="text/csv",
    )
