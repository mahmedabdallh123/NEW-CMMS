import streamlit as st
import pandas as pd
import requests
from io import BytesIO

st.set_page_config(page_title="🏭 سيرفيس تحضيرات Bail Yarn", layout="wide")

# ===============================
# ⚙ إعدادات
# ===============================
GITHUB_EXCEL_URL = "https://github.com/mahmedabdallh123/cmms/raw/refs/heads/main/Machine_Service_Lookup.xlsx"
# 👆 عدّل الرابط ده برابطك الخام من GitHub

# ===============================
# 📂 تحميل البيانات
# ===============================
@st.cache_data
def load_all_sheets():
    try:
        df_dict = pd.read_excel("Machine_Service_Lookup.xlsx", sheet_name=None)
        return df_dict
    except FileNotFoundError:
        st.error("❌ لم يتم العثور على ملف Machine_Service_Lookup.xlsx")
        return None

def fetch_from_github():
    """تحميل الملف من GitHub وتحديث النسخة المحلية"""
    try:
        response = requests.get(GITHUB_EXCEL_URL)
        response.raise_for_status()
        with open("Machine_Service_Lookup.xlsx", "wb") as f:
            f.write(response.content)
        st.success("✅ تم تحديث البيانات من GitHub بنجاح.")
        st.cache_data.clear()  # مسح الكاش عشان يقرأ النسخة الجديدة
    except Exception as e:
        st.error(f"⚠ فشل التحديث من GitHub: {e}")

# ===============================
# 🔍 تحليل بيانات الماكينة
# ===============================
def check_machine_status(card_num, current_tons, all_sheets):
    if not all_sheets:
        st.error("⚠ لا توجد بيانات للعرض.")
        return
    
    df = pd.concat(all_sheets.values(), ignore_index=True)
    df.columns = [col.strip() for col in df.columns]
    
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
    
    df_filtered = df[df['Card No'] == card_num]
    if df_filtered.empty:
        st.warning("⚠ لا توجد بيانات لهذه الماكينة.")
        return
    
    selected_range = st.radio(
        "⚙ اختر نطاق العرض:",
        ["الشريحة الحالية فقط", "كل الشرائح الأقل", "كل الشرائح الأعلى", "نطاق مخصص", "كل الشرائح"],
        horizontal=True
    )
    
    min_tons, max_tons = df_filtered["Tons"].min(), df_filtered["Tons"].max()
    tons_range = (min_tons, max_tons)
    
    if selected_range == "نطاق مخصص":
        tons_range = st.slider("حدد نطاق الأطنان:", int(min_tons), int(max_tons), (int(min_tons), int(max_tons)))
    elif selected_range == "الشريحة الحالية فقط":
        tons_range = (current_tons, current_tons)
    elif selected_range == "كل الشرائح الأقل":
        tons_range = (min_tons, current_tons)
    elif selected_range == "كل الشرائح الأعلى":
        tons_range = (current_tons, max_tons)
    
    result_df = df_filtered[(df_filtered["Tons"] >= tons_range[0]) & (df_filtered["Tons"] <= tons_range[1])]
    if result_df.empty:
        st.info("ℹ لا توجد سجلات في هذا النطاق.")
        return
    
    # عرض النتائج بعرض الشاشة بالكامل
    st.markdown("### 📋 نتائج البحث:")
    st.dataframe(
        result_df.style.set_properties({
            'white-space': 'normal',
            'text-align': 'center',
            'font-size': '16px'
        }),
        use_container_width=True
    )

# ===============================
# 🖥 واجهة التطبيق
# ===============================
st.title("🏭 سيرفيس تحضيرات Bail Yarn")

# 🔄 زر التحديث من GitHub
if st.button("🔄 تحديث البيانات من GitHub"):
    fetch_from_github()

card_num = st.text_input("رقم الماكينة:")
current_tons = st.number_input("عدد الأطنان الحالية:", min_value=0.0)

all_sheets = load_all_sheets()

if st.button("عرض النتائج"):
    check_machine_status(card_num, current_tons, all_sheets)
