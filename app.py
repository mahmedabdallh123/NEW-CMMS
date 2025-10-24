import streamlit as st
import pandas as pd
import re
import requests
import shutil

# ===============================
# ⚙ إعدادات أساسية
# ===============================
GITHUB_EXCEL_URL = "https://github.com/mahmedabdallh123/NEW-CMMS/raw/refs/heads/main/Machine_Service_Lookup.xlsx"
PASSWORD = "1234"

# ===============================
# 📂 تحميل البيانات من GitHub
# ===============================
@st.cache_data(show_spinner=False)
def load_all_sheets():
    local_file = "Machine_Service_Lookup.xlsx"
    r = requests.get(GITHUB_EXCEL_URL, stream=True)
    with open(local_file, 'wb') as f:
        shutil.copyfileobj(r.raw, f)
    sheets = pd.read_excel(local_file, sheet_name=None)
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
    if "ServicePlan" not in all_sheets:
        st.error("❌ الملف لازم يحتوي على شيت 'ServicePlan'")
        return

    service_plan_df = all_sheets["ServicePlan"]
    card_sheet_name = f"Card{card_num}"
    if card_sheet_name not in all_sheets:
        st.warning(f"⚠ لا يوجد شيت باسم {card_sheet_name}")
        return
    card_df = all_sheets[card_sheet_name]

    if "view_option" not in st.session_state:
        st.session_state.view_option = "الشريحة الحالية فقط"

    st.subheader("⚙ نطاق العرض")
    view_option = st.radio(
        "اختر نطاق العرض:",
        ("الشريحة الحالية فقط", "كل الشرائح الأقل", "كل الشرائح الأعلى", "نطاق مخصص", "كل الشرائح"),
        horizontal=True,
        key="view_option"
    )

    min_range = st.session_state.get("min_range", max(0, current_tons - 500))
    max_range = st.session_state.get("max_range", current_tons + 500)

    if view_option == "نطاق مخصص":
        st.markdown("#### 🔢 أدخل النطاق المخصص")
        col1, col2 = st.columns(2)
        with col1:
            min_range = st.number_input("من (طن):", min_value=0, step=100, value=min_range, key="min_range")
        with col2:
            max_range = st.number_input("إلى (طن):", min_value=min_range, step=100, value=max_range, key="max_range")

    # تحديد الشرائح المطلوبة
    if view_option == "الشريحة الحالية فقط":
        selected_slices = service_plan_df[
            (service_plan_df["Min_Tones"] <= current_tons) &
            (service_plan_df["Max_Tones"] >= current_tons)
        ]
    elif view_option == "كل الشرائح الأقل":
        selected_slices = service_plan_df[service_plan_df["Max_Tones"] <= current_tons]
    elif view_option == "كل الشرائح الأعلى":
        selected_slices = service_plan_df[service_plan_df["Min_Tones"] >= current_tons]
    elif view_option == "نطاق مخصص":
        selected_slices = service_plan_df[
            (service_plan_df["Min_Tones"] >= min_range) &
            (service_plan_df["Max_Tones"] <= max_range)
        ]
    else:
        selected_slices = service_plan_df.copy()

    if selected_slices.empty:
        st.warning("⚠ لا توجد شرائح مطابقة حسب النطاق المحدد.")
        return

    all_results = []
    for _, current_slice in selected_slices.iterrows():
        slice_min = current_slice["Min_Tones"]
        slice_max = current_slice["Max_Tones"]

        needed_service_raw = current_slice.get("Service", "")
        needed_parts = split_needed_services(needed_service_raw)
        needed_norm = [normalize_name(p) for p in needed_parts]

        mask = (
            (card_df.get("Min_Tones", 0).fillna(0) <= slice_max) &
            (card_df.get("Max_Tones", 0).fillna(0) >= slice_min)
        )
        matching_rows = card_df[mask]

        done_services_set = set()
        last_date = "-"
        last_tons = "-"

        if not matching_rows.empty:
            ignore_cols = {"card", "Tones", "Min_Tones", "Max_Tones", "Date"}
            for _, r in matching_rows.iterrows():
                for col in matching_rows.columns:
                    if col not in ignore_cols:
                        val = str(r.get(col, "")).strip()
                        if val and val.lower() not in ["nan", "none", ""]:
                            done_services_set.add(col)

            # ✅ قراءة التاريخ
            if "Date" in matching_rows.columns:
                cleaned_dates = matching_rows["Date"].astype(str).str.replace("\\", "/", regex=False)
                dates = pd.to_datetime(cleaned_dates, errors="coerce", dayfirst=True)
                if dates.notna().any():
                    parsed_date = dates.max()
                    last_date = parsed_date.strftime("%d/%m/%Y") if pd.notna(parsed_date) else "-"

            if "Tones" in matching_rows.columns:
                tons_vals = pd.to_numeric(matching_rows["Tones"], errors="coerce")
                if tons_vals.notna().any():
                    last_tons = int(tons_vals.max())

        done_services = sorted(list(done_services_set))
        done_norm = [normalize_name(c) for c in done_services]
        not_done = [orig for orig, n in zip(needed_parts, needed_norm) if n not in done_norm]

        all_results.append({
            "Min_Tons": slice_min,
            "Max_Tons": slice_max,
            "Service Needed": " + ".join(needed_parts) if needed_parts else "-",
            "Done Services": ", ".join(done_services) if done_services else "-",
            "Not Done Services": ", ".join(not_done) if not_done else "-",
            "Last Date": last_date,
            "Last Tones": last_tons,
        })

    result_df = pd.DataFrame(all_results)

    # 🎨 HTML تنسيق
    styled_html = result_df.style.set_table_styles([
        {'selector': 'th', 'props': [('background-color', '#007bff'), ('color', 'white'), ('text-align', 'center')]},
        {'selector': 'td', 'props': [('text-align', 'center'), ('white-space', 'normal'), ('word-wrap', 'break-word')]}
    ]).set_properties({
        'border': '1px solid #ccc',
        'padding': '8px',
        'font-size': '15px'
    }).to_html()

    st.markdown(
        f"""
        <div style="overflow-x:auto; width:100%;">
            {styled_html}
        </div>
        """,
        unsafe_allow_html=True
    )


# ===============================
# 🖥 الواجهة الرئيسية
# ===============================
st.title("🏭 سيرفيس تحضيرات Bail Yarn")

all_sheets = load_all_sheets()

col1, col2 = st.columns(2)
with col1:
    card_num = st.number_input("رقم الماكينة:", min_value=1, step=1, key="card_num")
with col2:
    current_tons = st.number_input("عدد الأطنان الحالية:", min_value=0, step=100, key="current_tons")

if st.button("عرض الحالة"):
    st.session_state["show_results"] = True

if st.session_state.get("show_results", False):
    check_machine_status(st.session_state.card_num, st.session_state.current_tons, all_sheets)
