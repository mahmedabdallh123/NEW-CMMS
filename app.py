import streamlit as st
import pandas as pd
import json
import os
import io
import requests
import re
import time
from datetime import datetime, timedelta
from base64 import b64decode

# محاولة استيراد PyGithub
try:
    from github import Github
    GITHUB_AVAILABLE = True
except Exception:
    GITHUB_AVAILABLE = False

# ===============================
# إعدادات عامة
# ===============================
USERS_FILE = "users.json"
STATE_FILE = "state.json"
SESSION_DURATION = timedelta(minutes=10)
MAX_ACTIVE_USERS = 2

# إعدادات GitHub
REPO_NAME = "mahmedabdallh123/input-data"
BRANCH = "main"
FILE_PATH = "Machine_Service_Lookup.xlsx"
LOCAL_FILE = "Machine_Service_Lookup.xlsx"
GITHUB_EXCEL_RAW_BASE = f"https://raw.githubusercontent.com/{REPO_NAME}/{BRANCH}/{FILE_PATH}"

# -------------------------------
# دوال الملفات والمستخدمين
# -------------------------------
def load_users():
    if not os.path.exists(USERS_FILE):
        default = {"admin": {"password": "admin"}}
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
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

def load_state():
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
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

def cleanup_sessions(state):
    now = datetime.now()
    changed = False
    for user, info in list(state.items()):
        if info.get("active") and "login_time" in info:
            try:
                login_time = datetime.fromisoformat(info["login_time"])
                if now - login_time > SESSION_DURATION:
                    info["active"] = False
                    info.pop("login_time", None)
                    changed = True
            except Exception:
                info["active"] = False
                changed = True
    if changed:
        save_state(state)
    return state

def remaining_time(state, username):
    if not username or username not in state:
        return None
    info = state.get(username)
    if not info or not info.get("active"):
        return None
    try:
        lt = datetime.fromisoformat(info["login_time"])
        remaining = SESSION_DURATION - (datetime.now() - lt)
        if remaining.total_seconds() <= 0:
            return None
        return remaining
    except:
        return None

# -------------------------------
# الدوال الأساسية - قراءة مباشرة مع GitHub
# -------------------------------
def load_excel_fresh():
    """قراءة الملف مباشرة من القرص - محدث دائماً"""
    if not os.path.exists(LOCAL_FILE):
        st.error("❌ الملف غير موجود. جاري التحميل من GitHub...")
        download_from_github()
        return {}
    
    try:
        # قراءة مباشرة مع التحقق من timestamp
        current_time = datetime.now().strftime("%H:%M:%S")
        sheets = pd.read_excel(LOCAL_FILE, sheet_name=None)
        for name, df in sheets.items():
            df.columns = df.columns.str.strip()
        
        return sheets
    except Exception as e:
        st.error(f"❌ خطأ في قراءة الملف: {e}")
        return {}

def download_from_github():
    """تحميل من GitHub مع التحقق من النجاح"""
    try:
        timestamp = int(time.time())
        url = f"{GITHUB_EXCEL_RAW_BASE}?t={timestamp}"
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(LOCAL_FILE, "wb") as f:
            f.write(response.content)
            
        # التحقق من أن المفع حُفظ
        if os.path.exists(LOCAL_FILE):
            file_size = os.path.getsize(LOCAL_FILE)
            st.success(f"✅ تم التحديث من GitHub | الحجم: {file_size} بايت")
            return True
        else:
            st.error("❌ فشل في حفظ الملف المحلي")
            return False
            
    except Exception as e:
        st.error(f"❌ فشل التحديث: {e}")
        return False

def save_to_github(sheets_dict, commit_message="تحديث من التطبيق"):
    """حفظ محلي ثم رفع إلى GitHub"""
    try:
        # 1. حفظ محلي أولاً
        with pd.ExcelWriter(LOCAL_FILE, engine='openpyxl') as writer:
            for name, df in sheets_dict.items():
                df.to_excel(writer, sheet_name=name, index=False)
        
        # 2. التحقق من الحفظ المحلي
        if not os.path.exists(LOCAL_FILE):
            st.error("❌ فشل الحفظ المحلي")
            return False
            
        file_size = os.path.getsize(LOCAL_FILE)
        st.success(f"✅ تم الحفظ المحلي | الحجم: {file_size} بايت")
        
        # 3. رفع إلى GitHub
        token = None
        try:
            token = st.secrets["github"]["token"]
        except Exception:
            token = None

        if token and GITHUB_AVAILABLE:
            try:
                g = Github(token)
                repo = g.get_repo(REPO_NAME)
                with open(LOCAL_FILE, "rb") as f:
                    content = f.read()
                
                try:
                    contents = repo.get_contents(FILE_PATH, ref=BRANCH)
                    repo.update_file(
                        path=FILE_PATH, 
                        message=commit_message, 
                        content=content, 
                        sha=contents.sha, 
                        branch=BRANCH
                    )
                    st.success("✅ تم الرفع إلى GitHub بنجاح")
                except Exception as e:
                    st.error(f"❌ خطأ في الرفع: {e}")
                    return False
            except Exception as e:
                st.error(f"❌ خطأ في الاتصال بـ GitHub: {e}")
                return False
        else:
            st.info("🔒 تم الحفظ محلياً فقط (لا يوجد توكن GitHub)")
        
        return True
        
    except Exception as e:
        st.error(f"❌ خطأ في الحفظ: {e}")
        return False

# -------------------------------
# واجهة المستخدم
# -------------------------------
def logout_action():
    state = load_state()
    username = st.session_state.get("username")
    if username and username in state:
        state[username]["active"] = False
        state[username].pop("login_time", None)
        save_state(state)
    
    st.session_state.logged_in = False
    st.session_state.username = None
    st.rerun()

def login_ui():
    users = load_users()
    state = cleanup_sessions(load_state())
    
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = None

    st.title("🔐 تسجيل الدخول - Bail Yarn (CMMS)")

    username_input = st.selectbox("👤 اختر المستخدم", list(users.keys()))
    password = st.text_input("🔑 كلمة المرور", type="password")

    active_users = [u for u, v in state.items() if v.get("active")]
    active_count = len(active_users)
    st.caption(f"🔒 المستخدمون النشطون الآن: {active_count} / {MAX_ACTIVE_USERS}")

    if not st.session_state.logged_in:
        if st.button("تسجيل الدخول"):
            if username_input in users and users[username_input]["password"] == password:
                if username_input != "admin" and username_input in active_users:
                    st.warning("⚠ هذا المستخدم مسجل دخول بالفعل.")
                    return False
                if active_count >= MAX_ACTIVE_USERS and username_input != "admin":
                    st.error("🚫 الحد الأقصى للمستخدمين المتصلين حالياً.")
                    return False
                state[username_input] = {"active": True, "login_time": datetime.now().isoformat()}
                save_state(state)
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
        rem = remaining_time(state, username)
        if rem:
            mins, secs = divmod(int(rem.total_seconds()), 60)
            st.info(f"⏳ الوقت المتبقي: {mins:02d}:{secs:02d}")
        else:
            st.warning("⏰ انتهت الجلسة، سيتم تسجيل الخروج.")
            logout_action()
        if st.button("🚪 تسجيل الخروج"):
            logout_action()
        return True

# -------------------------------
# أدوات الفحص والتنسيق
# -------------------------------
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

def highlight_cell(val, col_name):
    color_map = {
        "Service Needed": "background-color: #fff3cd; color:#856404; font-weight:bold;",
        "Done Services": "background-color: #d4edda; color:#155724; font-weight:bold;",
        "Not Done Services": "background-color: #f8d7da; color:#721c24; font-weight:bold;",
        "Last Date": "background-color: #e7f1ff; color:#004085; font-weight:bold;",
        "Last Tones": "background-color: #f0f0f0; color:#333; font-weight:bold;",
        "Other": "background-color: #e2f0d9; color:#2e6f32; font-weight:bold;",
        "Servised by": "background-color: #fdebd0; color:#7d6608; font-weight:bold;",
        "Min_Tons": "background-color: #ebf5fb; color:#154360; font-weight:bold;",
        "Max_Tons": "background-color: #f9ebea; color:#641e16; font-weight:bold;",
    }
    return color_map.get(col_name, "")

def style_table(row):
    return [highlight_cell(row[col], col) for col in row.index]

def check_machine_status_realtime(card_num, current_tons):
    """فحص مباشر - يقرأ الملف في اللحظة نفسها"""
    
    # إظهار مؤشر التحميل
    with st.spinner("🔄 جاري تحميل أحدث البيانات..."):
        # تحميل الملف مباشرة قبل الفحص
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

    # إظهار وقت التحميل
    load_time = datetime.now().strftime("%H:%M:%S")
    st.info(f"🕒 وقت تحميل البيانات: {load_time}")

    st.subheader("⚙ نطاق العرض")
    view_option = st.radio(
        "اختر نطاق العرض:",
        ("الشريحة الحالية فقط", "كل الشرائح الأقل", "كل الشرائح الأعلى", "نطاق مخصص", "كل الشرائح"),
        horizontal=True,
        key=f"view_{card_num}_{current_tons}"
    )

    min_range = max(0, current_tons - 500)
    max_range = current_tons + 500
    if view_option == "نطاق مخصص":
        col1, col2 = st.columns(2)
        with col1:
            min_range = st.number_input("من (طن):", min_value=0, step=100, value=min_range, key=f"min_{card_num}")
        with col2:
            max_range = st.number_input("إلى (طن):", min_value=min_range, step=100, value=max_range, key=f"max_{card_num}")

    if view_option == "الشريحة الحالية فقط":
        selected_slices = service_plan_df[(service_plan_df["Min_Tones"] <= current_tons) & (service_plan_df["Max_Tones"] >= current_tons)]
    elif view_option == "كل الشرائح الأقل":
        selected_slices = service_plan_df[service_plan_df["Max_Tones"] <= current_tons]
    elif view_option == "كل الشرائح الأعلى":
        selected_slices = service_plan_df[service_plan_df["Min_Tones"] >= current_tons]
    elif view_option == "نطاق مخصص":
        selected_slices = service_plan_df[(service_plan_df["Min_Tones"] >= min_range) & (service_plan_df["Max_Tones"] <= max_range)]
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

        mask = (card_df.get("Min_Tones", 0).fillna(0) <= slice_max) & (card_df.get("Max_Tones", 0).fillna(0) >= slice_min)
        matching_rows = card_df[mask]

        done_services_set = set()
        last_date = "-"
        last_tons = "-"
        last_other = "-"
        last_servised_by = "-"

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
                    cleaned_dates = matching_rows["Date"].astype(str).str.replace("\\", "/", regex=False)
                    dates = pd.to_datetime(cleaned_dates, errors="coerce", dayfirst=True)
                    if dates.notna().any():
                        idx = dates.idxmax()
                        last_date = dates.loc[idx].strftime("%d/%m/%Y")
                except:
                    last_date = "-"
            if "Tones" in matching_rows.columns:
                tons_vals = pd.to_numeric(matching_rows["Tones"], errors="coerce")
                if tons_vals.notna().any():
                    last_tons = int(tons_vals.max())
            if "Other" in matching_rows.columns:
                last_other = str(matching_rows["Other"].dropna().iloc[-1]) if matching_rows["Other"].notna().any() else "-"
            if "Servised by" in matching_rows.columns:
                last_servised_by = str(matching_rows["Servised by"].dropna().iloc[-1]) if matching_rows["Servised by"].notna().any() else "-"

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
            "Other": last_other,
            "Servised by": last_servised_by
        })

    result_df = pd.DataFrame(all_results).dropna(how="all").reset_index(drop=True)
    
    st.markdown("### 📋 نتائج الفحص")
    st.dataframe(result_df.style.apply(style_table, axis=1), use_container_width=True)

    buffer = io.BytesIO()
    result_df.to_excel(buffer, index=False, engine="openpyxl")
    st.download_button(
        label="💾 حفظ النتائج كـ Excel",
        data=buffer.getvalue(),
        file_name=f"Service_Report_Card{card_num}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# -------------------------------
# الواجهة الرئيسية
# -------------------------------
st.set_page_config(page_title="CMMS - Bail Yarn", layout="wide")

with st.sidebar:
    st.header("👤 الجلسة")
    if not st.session_state.get("logged_in"):
        if not login_ui():
            st.stop()
    else:
        state = cleanup_sessions(load_state())
        username = st.session_state.username
        rem = remaining_time(state, username)
        if rem:
            mins, secs = divmod(int(rem.total_seconds()), 60)
            st.success(f"👋 {username} | ⏳ {mins:02d}:{secs:02d}")
        else:
            logout_action()

    st.markdown("---")
    st.subheader("🔄 مزامنة GitHub")
    
    if st.button("📥 تحميل من GitHub"):
        if download_from_github():
            st.rerun()
    
    st.markdown("---")
    st.subheader("📊 حالة النظام")
    
    if os.path.exists(LOCAL_FILE):
        file_time = datetime.fromtimestamp(os.path.getmtime(LOCAL_FILE))
        file_size = os.path.getsize(LOCAL_FILE)
        st.success(f"📁 الملف: {file_time.strftime('%H:%M:%S')}")
        st.info(f"📊 الحجم: {file_size} بايت")
    else:
        st.error("❌ الملف غير موجود")
    
    # حالة GitHub
    try:
        token = st.secrets.get("github", {}).get("token")
        if token and GITHUB_AVAILABLE:
            st.success("🔗 GitHub: متصل")
        else:
            st.info("🔗 GitHub: بدون توكين")
    except:
        st.error("🔗 GitHub: خطأ في التكوين")
    
    st.markdown("---")
    if st.button("🚪 تسجيل الخروج"):
        logout_action()

# التبويبات الرئيسية
st.title("🏭 CMMS - Bail Yarn")
tabs = st.tabs(["📊 عرض وفحص الماكينات", "🛠 تعديل وإدارة البيانات", "⚙ إدارة المستخدمين"])

# -------------------------------
# Tab 1: عرض وفحص الماكينات
# -------------------------------
with tabs[0]:
    st.header("📊 عرض وفحص الماكينات")
    
    if not os.path.exists(LOCAL_FILE):
        st.error("❌ الملف غير موجود. اضغط 'تحميل من GitHub' في الشريط الجانبي.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            card_num = st.number_input("رقم الماكينة:", min_value=1, step=1, key="card_num_main")
        with col2:
            current_tons = st.number_input("عدد الأطنان الحالية:", min_value=0, step=100, key="current_tons_main")

        if st.button("🔍 فحص الحالة الآن", type="primary"):
            check_machine_status_realtime(card_num, current_tons)

# -------------------------------
# Tab 2: تعديل وإدارة البيانات
# -------------------------------
with tabs[1]:
    st.header("🛠 تعديل وإدارة البيانات")
    username = st.session_state.get("username")
    token_exists = bool(st.secrets.get("github", {}).get("token", None))
    can_push = (username == "admin") or (token_exists and GITHUB_AVAILABLE)

    # تحميل البيانات مباشرة للتحرير
    with st.spinner("🔄 جاري تحميل البيانات..."):
        sheets_data = load_excel_fresh()
    
    if not sheets_data:
        st.error("❌ لا يمكن تحميل البيانات")
    else:
        tab1, tab2, tab3 = st.tabs(["✏ تعديل البيانات", "➕ إضافة صف جديد", "🆕 إضافة عمود"])

        # Tab1 - تعديل وعرض
        with tab1:
            st.subheader("✏ تعديل البيانات")
            sheet_name = st.selectbox("اختر الشيت:", list(sheets_data.keys()), key="edit_sheet")
            
            if sheet_name in sheets_data:
                df = sheets_data[sheet_name].copy()
                st.write(f"عدد الصفوف: {len(df)}")
                
                edited_df = st.data_editor(df, num_rows="dynamic", key=f"editor_{sheet_name}")

                if st.button("💾 حفظ التعديلات", key=f"save_{sheet_name}", type="primary"):
                    sheets_data[sheet_name] = edited_df
                    if save_to_github(sheets_data, f"تعديل {sheet_name} بواسطة {username}"):
                        st.balloons()
                        st.success("✅ تم الحفظ بنجاح! انتقل إلى تبويب الفحص لرؤية التغييرات.")

        # Tab2 - إضافة صف
        with tab2:
            st.subheader("➕ إضافة صف جديد")
            sheet_name_add = st.selectbox("اختر الشيت:", list(sheets_data.keys()), key="add_sheet")
            
            if sheet_name_add in sheets_data:
                df_add = sheets_data[sheet_name_add].copy()
                
                st.markdown("أدخل بيانات الصف الجديد:")
                new_data = {}
                for col in df_add.columns:
                    new_data[col] = st.text_input(f"{col}", key=f"new_{sheet_name_add}_{col}")

                if st.button("💾 إضافة الصف", key=f"add_{sheet_name_add}", type="primary"):
                    new_row = pd.DataFrame([new_data])
                    df_new = pd.concat([df_add, new_row], ignore_index=True)
                    sheets_data[sheet_name_add] = df_new
                    
                    if save_to_github(sheets_data, f"إضافة صف في {sheet_name_add} بواسطة {username}"):
                        st.balloons()
                        st.success("✅ تم الإضافة بنجاح! انتقل إلى تبويب الفحص لرؤية التغييرات.")

        # Tab3 - إضافة عمود
        with tab3:
            st.subheader("🆕 إضافة عمود جديد")
            sheet_name_col = st.selectbox("اختر الشيت:", list(sheets_data.keys()), key="add_col_sheet")
            
            if sheet_name_col in sheets_data:
                df_col = sheets_data[sheet_name_col].copy()
                new_col_name = st.text_input("اسم العمود الجديد:")
                default_value = st.text_input("القيمة الافتراضية (اختياري):", "")

                if st.button("💾 إضافة العمود", key=f"add_col_{sheet_name_col}", type="primary"):
                    if new_col_name:
                        df_col[new_col_name] = default_value
                        sheets_data[sheet_name_col] = df_col
                        
                        if save_to_github(sheets_data, f"إضافة عمود '{new_col_name}' في {sheet_name_col} بواسطة {username}"):
                            st.balloons()
                            st.success("✅ تم إضافة العمود بنجاح! انتقل إلى تبويب الفحص لرؤية التغييرات.")
                    else:
                        st.warning("⚠ الرجاء إدخال اسم العمود")

# -------------------------------
# Tab 3: إدارة المستخدمين
# -------------------------------
with tabs[2]:
    st.header("⚙ إدارة المستخدمين")
    users = load_users()
    username = st.session_state.get("username")

    if username != "admin":
        st.info("🛑 فقط المستخدم 'admin' يمكنه إدارة المستخدمين.")
        st.write("المستخدمين الحاليين:", list(users.keys()))
    else:
        st.subheader("🔐 المستخدمين الموجودين")
        st.dataframe(pd.DataFrame([{"username": k, "password": "*"} for k in users.keys()]))
        
        st.markdown("### ➕ إضافة مستخدم جديد")
        new_user = st.text_input("اسم المستخدم الجديد:")
        new_pass = st.text_input("كلمة المرور:", type="password")
        if st.button("إضافة مستخدم", type="primary"):
            if new_user and new_pass:
                if new_user in users:
                    st.warning("⚠ المستخدم موجود بالفعل")
                else:
                    users[new_user] = {"password": new_pass}
                    save_users(users)
                    st.success("✅ تم الإضافة")
                    st.rerun()
            else:
                st.warning("⚠ أدخل اسم المستخدم وكلمة المرور")

        st.markdown("### 🗑 حذف مستخدم")
        del_user = st.selectbox("اختر مستخدم للحذف:", [u for u in users.keys() if u != "admin"])
        if st.button("حذف المستخدم"):
            users.pop(del_user, None)
            save_users(users)
            st.success("✅ تم الحذف")
            st.rerun()
```
