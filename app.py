import streamlit as st
import pandas as pd

st.set_page_config(page_title="🏭 سيرفيس تحضيرات Bail Yarn", layout="wide")

@st.cache_data
def load_all_sheets():
    try:
        return pd.read_excel("Machine_Service_Lookup.xlsx", sheet_name=None)
    except FileNotFoundError:
        st.error("❌ لم يتم العثور على ملف Machine_Service_Lookup.xlsx")

def check_machine_status(card_num, current_tons, all_sheets):
    # تأكيد وجود البيانات
    if not all_sheets:
        st.error("⚠ لا توجد بيانات للعرض.")
        return
    
    # دمج كل الشيتات في DataFrame واحد
    df = pd.concat(all_sheets.values(), ignore_index=True)
    
    # تنظيف الأعمدة
    df.columns = [col.strip() for col in df.columns]
    
    # تحويل التاريخ
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
    
    # تصفية برقم الماكينة
    df_filtered = df[df['Card No'] == card_num]
    
    if df_filtered.empty:
        st.warning("⚠ لا توجد بيانات لهذه الماكينة.")
        return
    
    # تحديد النطاق بناءً على عدد الأطنان
    selected_range = st.radio(
        "⚙ اختر نطاق العرض:",
        ["الشريحة الحالية فقط", "كل الشرائح الأقل", "كل الشرائح الأعلى", "نطاق مخصص", "كل الشرائح"],
        horizontal=True
    )
    
    min_tons, max_tons = df_filtered["Tons"].min(), df_filtered["Tons"].max()
    tons_range = (min_tons, max_tons)
    
    if selected_range == "نطاق مخصص":
        tons_range = st.slider("حدد نطاق الأطنان:", min_value=int(min_tons), max_value=int(max_tons), value=(int(min_tons), int(max_tons)))
    elif selected_range == "الشريحة الحالية فقط":
        tons_range = (current_tons, current_tons)
    elif selected_range == "كل الشرائح الأقل":
        tons_range = (min_tons, current_tons)
    elif selected_range == "كل الشرائح الأعلى":
        tons_range = (current_tons, max_tons)

    # تصفية حسب النطاق
    result_df = df_filtered[(df_filtered["Tons"] >= tons_range[0]) & (df_filtered["Tons"] <= tons_range[1])]
    
    if result_df.empty:
        st.info("ℹ لا توجد سجلات في هذا النطاق.")
        return
    
    # عرض الجدول بعرض الشاشة بالكامل
    st.markdown("### 📋 نتائج البحث:")
    st.dataframe(
        result_df.style.set_properties({
            'white-space': 'normal',
            'text-align': 'center',
            'font-size': '16px'
        }),
        use_container_width=True
    )

# ==============================
# 📥 واجهة الإدخال
# ==============================
st.title("🏭 سيرفيس تحضيرات Bail Yarn")

card_num = st.text_input("رقم الماكينة:")
current_tons = st.number_input("عدد الأطنان الحالية:", min_value=0.0)

all_sheets = load_all_sheets()

if st.button("عرض النتائج"):
    check_machine_status(card_num, current_tons, all_sheets)
