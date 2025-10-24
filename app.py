import streamlit as st
import pandas as pd
import re
import requests
import shutil
import os

# ===============================
# ⚙ إعدادات أساسية
# ===============================
GITHUB_EXCEL_URL = "https://github.com/mahmedabdallh123/cmms/raw/refs/heads/main/Machine_Service_Lookup.xlsx"
PASSWORD = "1224"
LOCAL_FILE = "Machine_Service_Lookup.xlsx"

# ===============================
# 🔄 تحديث الملف من GitHub
# ===============================
def fetch_from_github():
    """تحميل الملف من GitHub وتحديث النسخة المحلية"""
    try:
        response = requests.get(GITHUB_EXCEL_URL, stream=True, timeout=10)
        response.raise_for_status()
        with open(LOCAL_FILE, "wb") as f:
            shutil.copyfileobj(response.raw, f)

        # ✅ تنظيف الكاش بعد التحديث
        st.cache_data.clear()
        st.session_state["last_update"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

        st.success("✅ تم تحديث البيانات من GitHub بنجاح وتم مسح الكاش.")
    except Exception as e:
        st.error(f"⚠ فشل التحديث من GitHub: {e}")

# ===============================
# 📂 تحميل البيانات (من الملف المحلي فقط)
# ===============================
@st.cache_data(show_spinner=False)
def load_all_sheets():
    """تحميل كل الشيتات من الملف المحلي"""
    if not os.path.exists(LOCAL_FILE):
        st.error("❌ الملف المحلي غير موجود. برجاء الضغط على زر التحديث أولًا.")
        return None

    sheets = pd.read_excel(LOCAL_FILE, sheet_name=None)
    for name, df in sheets.items():
        df.columns = df.columns.str.strip()
    return sheets

# ===============================
# 🧰 دوال مساعدة
# ===============================
def normalize_name(s):
    if s is None:
        return ""
    s = str(s).replace("\n", "+")
    s = re.sub(r"[^0-9a-zA-Z\u0600-\u06FF\+\s_/.-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def split_needed_services(needed_service_str):
    if not isinstance(needed_service_str, str) or needed_service_str.strip() == "":
        return []
    parts = re.split(r"\+|,|\n|;", needed_service_str)
    return [p.strip() for p in parts if p.strip() != ""]

# ===============================
# 🔍 تحليل حالة الماكينة
# ===============================
def check_machine_status(card_num, current_tons, all_sheets):
    results = []

    for sheet_name, df in all_sheets.items():
        df = df.copy()
        df.columns = df.columns.str.strip()

        if "Machine No" not in df.columns or "Tons" not in df.columns:
            continue

        df_filtered = df[df["Machine No"].astype(str).str.contains(str(card_num), case=False, na=False)]
        if df_filtered.empty:
            continue

        df_filtered = df_filtered.sort_values("Tons")
        df_filtered["Service Needed"] = df_filtered["Service Needed"].fillna("")
        df_filtered["Service Done"] = df_filtered["Service Done"].fillna("")
        df_filtered["Date"] = df_filtered["Date"].astype(str)

        # استخراج نطاق الخدمات بناءً على التون
        mask = df_filtered["Tons"] <= current_tons
        relevant_rows = df_filtered[mask].copy()

        if relevant_rows.empty:
            continue

        results.append(relevant_rows)

    if not results:
        st.warning("⚠ لا توجد بيانات مطابقة.")
        return

    combined = pd.concat(results, ignore_index=True)

    # ✅ تطبيق تنسيق ألوان على الأعمدة
    def color_cells(val):
        val = str(val).lower()
        if "needed" in val:
            return "background-color: #FFF3CD; color: #856404;"  # أصفر
        elif "done" in val:
            return "background-color: #D4EDDA; color: #155724;"  # أخضر
        elif "delay" in val:
            return "background-color: #F8D7DA; color: #721C24;"  # أحمر
        return ""

    styled = combined.style.applymap(color_cells, subset=["Service Needed", "Service Done"])

    # ✅ عرض الجدول بعرض الشاشة
    st.markdown("### 📊 نتائج الفحص")
    st.dataframe(
        styled,
        use_container_width=True,
        height=450,
    )

    # ✅ زر حفظ الجدول المعدل كملف Excel
    buffer = io.BytesIO()
    combined.to_excel(buffer, index=False, engine="openpyxl")
    st.download_button(
        label="💾 حفظ النتائج كملف Excel",
        data=buffer.getvalue(),
        file_name="Service_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
