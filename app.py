import streamlit as st
import pandas as pd
import json
import os
import io
import requests
import re
import time
from datetime import datetime, timedelta

# ===============================
# إعدادات أساسية
# ===============================
USERS_FILE = "users.json"
STATE_FILE = "state.json"
LOCAL_FILE = "Machine_Service_Lookup.xlsx"

# -------------------------------
# دوال الملفات والمستخدمين
# -------------------------------
def load_users():
    """تحميل بيانات المستخدمين"""
    if not os.path.exists(USERS_FILE):
        default = {"admin": {"password": "admin", "role": "admin"}}
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4, ensure_ascii=False)
        return default
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"❌ خطأ في ملف users.json: {e}")
        st.stop()

def save_users(users):
    """حفظ بيانات المستخدمين"""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

def load_state():
    """تحميل حالة الجلسات"""
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    """حفظ حالة الجلسات"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

# -------------------------------
# دوال الملفات الأساسية
# -------------------------------
def load_excel_fresh():
    """قراءة الملف مباشرة من القرص"""
    if not os.path.exists(LOCAL_FILE):
        return {}
    
    try:
        sheets = pd.read_excel(LOCAL_FILE, sheet_name=None)
        for name, df in sheets.items():
            df.columns = df.columns.str.strip()
        return sheets
    except Exception as e:
        st.error(f"❌ خطأ في قراءة الملف: {e}")
        return {}

def load_excel_for_edit():
    """تحميل الملف للتحرير"""
    if not os.path.exists(LOCAL_FILE):
        return {}
    try:
        sheets = pd.read_excel(LOCAL_FILE, sheet_name=None, dtype=object)
        for name, df in sheets.items():
            df.columns = df.columns.str.strip()
        return sheets
    except Exception as e:
        st.error(f"❌ خطأ في قراءة الملف للتحرير: {e}")
        return {}

def save_excel_locally(sheets_dict):
    """حفظ الملف محلياً فقط"""
    try:
        with pd.ExcelWriter(LOCAL_FILE, engine='openpyxl') as writer:
            for name, df in sheets_dict.items():
                df.to_excel(writer, sheet_name=name, index=False)
        
        if os.path.exists(LOCAL_FILE):
            file_size = os.path.getsize(LOCAL_FILE)
            st.success(f"✅ تم الحفظ المحلي | الحجم: {file_size} بايت")
            return True
        else:
            st.error("❌ فشل الحفظ المحلي")
            return False
            
    except Exception as e:
        st.error(f"❌ خطأ في الحفظ: {e}")
        return False

# -------------------------------
# واجهة المستخدم البسيطة
# -------------------------------
def login_ui():
    """واجهة تسجيل الدخول"""
    users = load_users()
    
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = None

    st.title("🔐 تسجيل الدخول - نظام الصيانة")

    username_input = st.selectbox("👤 اختر المستخدم", list(users.keys()))
    password = st.text_input("🔑 كلمة المرور", type="password")

    if not st.session_state.logged_in:
        if st.button("تسجيل الدخول", type="primary"):
            if username_input in users and users[username_input]["password"] == password:
                st.session_state.logged_in = True
                st.session_state.username = username_input
                st.success(f"✅ تم تسجيل الدخول: {username_input}")
                st.rerun()
            else:
                st.error("❌ كلمة المرور غير صحيحة.")
        return False
    else:
        username = st.session_state.username
        st.success(f"✅ مسجل الدخول كـ: {username}")
        if st.button("🚪 تسجيل الخروج"):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.rerun()
        return True

# -------------------------------
# أدوات الفحص
# -------------------------------
def normalize_name(s):
    """تطبيع الأسماء"""
    if s is None:
        return ""
    s = str(s).replace("\n", "+")
    s = re.sub(r"[^0-9a-zA-Z\u0600-\u06FF\+\s_/.-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def split_needed_services(needed_service_str):
    """تقسيم الخدمات المطلوبة"""
    if not isinstance(needed_service_str, str) or needed_service_str.strip() == "":
        return []
    parts = re.split(r"\+|,|\n|;", needed_service_str)
    return [p.strip() for p in parts if p.strip() != ""]

def check_machine_status_simple(card_num, current_tons):
    """فحص مبسط للماكينات"""
    
    with st.spinner("🔄 جاري تحميل البيانات..."):
        all_sheets = load_excel_fresh()
    
    if not all_sheets:
        st.error("❌ لا يمكن تحميل الملف")
        return
    
    if "ServicePlan" not in all_sheets:
        st.error("❌ الملف لا يحتوي على شيت ServicePlan.")
        return
    
    service_plan_df = all_sheets["ServicePlan"]
    card_sheet_name = f"Card{card_num}"
    
    if card_sheet_name not in all_sheets:
        st.warning(f"⚠ لا يوجد شيت باسم {card_sheet_name}")
        return
    
    card_df = all_sheets[card_sheet_name]

    # البحث عن الشريحة الحالية فقط
    current_slice = service_plan_df[
        (service_plan_df["Min_Tones"] <= current_tons) & 
        (service_plan_df["Max_Tones"] >= current_tons)
    ]
    
    if current_slice.empty:
        st.warning("⚠ لا توجد شريحة مطابقة للأطنان الحالية.")
        return

    current_slice = current_slice.iloc[0]
    slice_min = current_slice["Min_Tones"]
    slice_max = current_slice["Max_Tones"]
    needed_service_raw = current_slice.get("Service", "")
    needed_parts = split_needed_services(needed_service_raw)

    # البحث في سجل الماكينة
    mask = (card_df.get("Min_Tones", 0).fillna(0) <= slice_max) & (card_df.get("Max_Tones", 0).fillna(0) >= slice_min)
    matching_rows = card_df[mask]

    done_services_set = set()
    last_date = "-"
    last_tons = "-"

    if not matching_rows.empty:
        ignore_cols = {"card", "Tones", "Min_Tones", "Max_Tones", "Date", "Other", "Servised by"}
        for _, r in matching_rows.iterrows():
            for col in matching_rows.columns:
                if col not in ignore_cols:
                    val = str(r.get(col, "")).strip()
                    if val and val.lower() not in ["nan", "none", ""]:
                        done_services_set.add(col)
        
        if "Date" in matching_rows.columns:
            try:
                dates = pd.to_datetime(matching_rows["Date"], errors="coerce")
                if dates.notna().any():
                    last_date = dates.max().strftime("%d/%m/%Y")
            except:
                last_date = "-"
        
        if "Tones" in matching_rows.columns:
            tons_vals = pd.to_numeric(matching_rows["Tones"], errors="coerce")
            if tons_vals.notna().any():
                last_tons = int(tons_vals.max())

    done_services = sorted(list(done_services_set))
    not_done = [service for service in needed_parts if service not in done_services]

    # عرض النتائج
    st.subheader("📋 نتيجة الفحص")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info(f"*الماكينة:* Card{card_num}")
        st.info(f"*الأطنان الحالية:* {current_tons}")
        st.info(f"*الشريحة:* {slice_min} - {slice_max} طن")
    
    with col2:
        st.info(f"*آخر صيانة:* {last_date}")
        st.info(f"*آخر أطنان:* {last_tons}")
    
    st.subheader("🔧 الخدمات")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.success("*الخدمات المنجزة:*")
        if done_services:
            for service in done_services:
                st.write(f"✅ {service}")
        else:
            st.write("لا توجد خدمات منجزة")
    
    with col2:
        st.error("*الخدمات المطلوبة:*")
        if not_done:
            for service in not_done:
                st.write(f"❌ {service}")
        else:
            st.write("جميع الخدمات مكتملة ✓")

# -------------------------------
# الواجهة الرئيسية
# -------------------------------
st.set_page_config(page_title="نظام إدارة الصيانة", layout="wide")

with st.sidebar:
    st.header("👤 الجلسة")
    if not login_ui():
        st.stop()
    
    st.markdown("---")
    st.header("🔄 التحكم في البيانات")
    
    if st.button("🔄 تحديث الصفحة", use_container_width=True):
        st.rerun()
    
    if st.button("📊 تحميل البيانات", use_container_width=True):
        if os.path.exists(LOCAL_FILE):
            st.success("✅ تم تحميل البيانات")
        else:
            st.error("❌ الملف غير موجود")
    
    st.markdown("---")
    st.header("📊 حالة النظام")
    
    if os.path.exists(LOCAL_FILE):
        file_time = datetime.fromtimestamp(os.path.getmtime(LOCAL_FILE))
        file_size = os.path.getsize(LOCAL_FILE)
        st.success(f"📁 الملف: {file_time.strftime('%H:%M:%S')}")
        st.info(f"📊 الحجم: {file_size:,} بايت")
        
        try:
            sheets = load_excel_fresh()
            if sheets:
                st.info(f"📋 عدد الشيتات: {len(sheets)}")
        except:
            pass
    else:
        st.error("❌ الملف غير موجود")

# التبويبات الرئيسية
st.title("🏭 نظام إدارة صيانة الماكينات")
st.markdown("الإصدار المبسط - يعمل بدون اتصال بالإنترنت")

tabs = st.tabs(["📊 فحص الماكينات", "🛠 تعديل البيانات", "⚙ إدارة المستخدمين"])

# -------------------------------
# Tab 1: فحص الماكينات
# -------------------------------
with tabs[0]:
    st.header("📊 فحص حالة الماكينات")
    
    if not os.path.exists(LOCAL_FILE):
        st.error("❌ ملف البيانات غير موجود. تأكد من وجود الملف في نفس المجلد.")
        st.info("""
        *لحل المشكلة:*
        1. تأكد من وجود ملف Machine_Service_Lookup.xlsx في نفس المجلد
        2. إذا لم يكن موجوداً، انسخه إلى هذا المكان
        3. اضغط على زر 'تحديث الصفحة'
        """)
    else:
        col1, col2 = st.columns(2)
        with col1:
            card_num = st.number_input("رقم الماكينة:", min_value=1, step=1, value=1)
        with col2:
            current_tons = st.number_input("عدد الأطنان الحالية:", min_value=0, step=100, value=1000)

        if st.button("🔍 فحص الحالة", type="primary", use_container_width=True):
            check_machine_status_simple(card_num, current_tons)

# -------------------------------
# Tab 2: تعديل البيانات
# -------------------------------
with tabs[1]:
    st.header("🛠 تعديل البيانات")
    
    if not os.path.exists(LOCAL_FILE):
        st.error("❌ ملف البيانات غير موجود")
    else:
        with st.spinner("جاري تحميل البيانات..."):
            sheets_data = load_excel_for_edit()
        
        if not sheets_data:
            st.error("❌ لا يمكن تحميل البيانات")
        else:
            sheet_name = st.selectbox("اختر الشيت للتعديل:", list(sheets_data.keys()))
            
            if sheet_name in sheets_data:
                df = sheets_data[sheet_name].copy()
                st.write(f"*عدد الصفوف:* {len(df)} | *عدد الأعمدة:* {len(df.columns)}")
                
                st.subheader("✏ تعديل البيانات")
                edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

                if st.button("💾 حفظ التعديلات", type="primary", use_container_width=True):
                    sheets_data[sheet_name] = edited_df
                    if save_excel_locally(sheets_data):
                        st.success("✅ تم الحفظ بنجاح! اضغط على زر 'تحديث الصفحة' لرؤية التغييرات.")

# -------------------------------
# Tab 3: إدارة المستخدمين
# -------------------------------
with tabs[2]:
    st.header("⚙ إدارة المستخدمين")
    users = load_users()
    username = st.session_state.get("username")

    if username != "admin":
        st.info("🛑 فقط المستخدم 'admin' يمكنه إدارة المستخدمين.")
        st.write("👥 المستخدمين الحاليين:", ", ".join(users.keys()))
    else:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("👥 المستخدمين الموجودين")
            for user, info in users.items():
                role = info.get("role", "مستخدم")
                st.write(f"- *{user}* ({role})")
            
            st.subheader("🗑 حذف مستخدم")
            del_user = st.selectbox("اختر مستخدم للحذف:", 
                                   [u for u in users.keys() if u != "admin"])
            
            if st.button("حذف المستخدم", type="secondary", use_container_width=True):
                if del_user in users:
                    users.pop(del_user)
                    save_users(users)
                    st.success(f"✅ تم حذف المستخدم '{del_user}'")
                    st.rerun()

        with col2:
            st.subheader("➕ إضافة مستخدم جديد")
            
            new_user = st.text_input("اسم المستخدم الجديد:")
            new_pass = st.text_input("كلمة المرور:", type="password")
            confirm_pass = st.text_input("تأكيد كلمة المرور:", type="password")
            user_role = st.selectbox("دور المستخدم:", ["مستخدم", "مشرف"])
            
            if st.button("إضافة مستخدم", type="primary", use_container_width=True):
                if not new_user or not new_pass:
                    st.warning("⚠ الرجاء إدخال اسم المستخدم وكلمة المرور")
                elif new_pass != confirm_pass:
                    st.error("❌ كلمة المرور غير متطابقة")
                elif new_user in users:
                    st.warning("⚠ هذا المستخدم موجود بالفعل")
                else:
                    users[new_user] = {
                        "password": new_pass,
                        "role": user_role
                    }
                    save_users(users)
                    st.success(f"✅ تم إضافة المستخدم '{new_user}' بنجاح")
                    st.rerun()

# -------------------------------
# تذييل الصفحة
# -------------------------------
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: gray;">
    <p><strong>نظام إدارة صيانة الماكينات</strong></p>
    <p>الإصدار المبسط | © 2024</p>
</div>
""", unsafe_allow_html=True)
