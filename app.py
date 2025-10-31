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
SESSION_DURATION = timedelta(minutes=30)
MAX_ACTIVE_USERS = 5

# إعدادات GitHub
REPO_NAME = "mahmedabdallh123/input-data"
BRANCH = "main"
FILE_PATH = "Machine_Service_Lookup.xlsx"
LOCAL_FILE = "Machine_Service_Lookup.xlsx"
GITHUB_EXCEL_RAW_BASE = f"https://raw.githubusercontent.com/{REPO_NAME}/{BRANCH}/{FILE_PATH}"

# -------------------------------
# دوال مسح الذاكرة المؤقتة
# -------------------------------
def clear_cache_and_reload():
    """مسح الذاكرة المؤقتة وإعادة تحميل البيانات"""
    try:
        # مسح ذاكرة التخزين المؤقت لـ pandas
        if hasattr(pd, 'read_excel') and hasattr(pd.read_excel, 'cache_clear'):
            pd.read_excel.cache_clear()
        
        # إعادة تعيين حالة الجلسة
        keys_to_clear = ['sheets_data', 'excel_data', 'last_loaded']
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        # إضافة تأخير بسيط لضمان مسح الذاكرة المؤقتة
        time.sleep(1)
        
        st.success("✅ تم تحديث البيانات بنجاح")
        st.rerun()
        return True
    except Exception as e:
        st.error(f"❌ خطأ في مسح الذاكرة المؤقتة: {e}")
        return False

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

def cleanup_sessions(state):
    """تنظيف الجلسات المنتهية"""
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
    """حساب الوقت المتبقي للجلسة"""
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
# دوال GitHub والملفات
# -------------------------------
def load_excel_fresh():
    """قراءة الملف مباشرة من القرص - محدث دائماً"""
    if not os.path.exists(LOCAL_FILE):
        return {}
    
    try:
        # إضافة طابع زمني لمنع التخزين المؤقت
        timestamp = int(time.time())
        sheets = pd.read_excel(LOCAL_FILE, sheet_name=None)
        for name, df in sheets.items():
            df.columns = df.columns.str.strip()
        
        # تخزين وقت التحميل الأخير
        st.session_state.last_loaded = timestamp
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

def download_from_github():
    """تحميل من GitHub"""
    try:
        timestamp = int(time.time())
        url = f"{GITHUB_EXCEL_RAW_BASE}?t={timestamp}"
        
        st.info("🔄 جاري تحميل أحدث نسخة من GitHub...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(LOCAL_FILE, "wb") as f:
            f.write(response.content)
            
        if os.path.exists(LOCAL_FILE):
            file_size = os.path.getsize(LOCAL_FILE)
            st.success(f"✅ تم التحديث من GitHub | الحجم: {file_size} بايت")
            
            # مسح الذاكرة المؤقتة بعد التحديث
            clear_cache_and_reload()
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
        
        # 3. تحديث الذاكرة المؤقتة مباشرة بعد الحفظ
        clear_cache_and_reload()
        
        # 4. رفع إلى GitHub
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
    """تسجيل الخروج"""
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
    """واجهة تسجيل الدخول"""
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
        if st.button("تسجيل الدخول", type="primary"):
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

def highlight_cell(val, col_name):
    """تلوين الخلايا"""
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
    """تنسيق الجدول"""
    return [highlight_cell(row[col], col) for col in row.index]

def check_machine_status_realtime(card_num, current_tons):
    """فحص مباشر - يقرأ الملف في اللحظة نفسها"""
    
    with st.spinner("🔄 جاري تحميل أحدث البيانات..."):
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
    
    st.markdown("📋 *نتائج الفحص*")
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
# دوال مساعدة للتعديل
# -------------------------------
def find_range_columns(df):
    """البحث عن أعمدة المدى"""
    min_col, max_col, card_col = None, None, None
    for c in df.columns:
        c_low = c.strip().lower()
        if c_low in ("min_tones", "min_tone", "min tones", "min"):
            min_col = c
        if c_low in ("max_tones", "max_tone", "max tones", "max"):
            max_col = c
        if c_low in ("card", "machine", "machine_no", "machine id"):
            card_col = c
    return min_col, max_col, card_col

def calculate_insert_position(df_add, new_data, min_col, max_col, card_col):
    """حساب موضع الإدراج"""
    def to_num_or_none(x):
        try:
            return float(x)
        except:
            return None

    new_min_raw = str(new_data.get(min_col, "")).strip()
    new_max_raw = str(new_data.get(max_col, "")).strip()
    new_min_num = to_num_or_none(new_min_raw)
    new_max_num = to_num_or_none(new_max_raw)

    insert_pos = len(df_add)
    mask = pd.Series([False] * len(df_add))

    if card_col:
        new_card = str(new_data.get(card_col, "")).strip()
        if new_card != "":
            if new_min_num is not None and new_max_num is not None:
                mask = (
                    (df_add[card_col].astype(str).str.strip() == new_card) &
                    (pd.to_numeric(df_add[min_col], errors='coerce') == new_min_num) &
                    (pd.to_numeric(df_add[max_col], errors='coerce') == new_max_num)
                )
            else:
                mask = (
                    (df_add[card_col].astype(str).str.strip() == new_card) &
                    (df_add[min_col].astype(str).str.strip() == new_min_raw) &
                    (df_add[max_col].astype(str).str.strip() == new_max_raw)
                )
    else:
        if new_min_num is not None and new_max_num is not None:
            mask = (
                (pd.to_numeric(df_add[min_col], errors='coerce') == new_min_num) &
                (pd.to_numeric(df_add[max_col], errors='coerce') == new_max_num)
            )
        else:
            mask = (
                (df_add[min_col].astype(str).str.strip() == new_min_raw) &
                (df_add[max_col].astype(str).str.strip() == new_max_raw)
            )

    if mask.any():
        insert_pos = mask[mask].index[-1] + 1
    else:
        try:
            df_add["_min_num"] = pd.to_numeric(df_add[min_col], errors='coerce').fillna(-1)
            if new_min_num is not None:
                insert_pos = int((df_add["_min_num"] < new_min_num).sum())
            else:
                insert_pos = len(df_add)
            df_add = df_add.drop(columns=["_min_num"])
        except Exception:
            insert_pos = len(df_add)

    return insert_pos

def safe_date_analysis(df, date_column='Date'):
    """تحليل آمن للتواريخ"""
    if date_column not in df.columns:
        return "-", "-"
    
    try:
        # تحويل التواريخ بشكل آمن
        dates = pd.to_datetime(df[date_column], errors='coerce')
        valid_dates = dates.dropna()
        
        if len(valid_dates) == 0:
            return "-", "-"
        
        min_date = valid_dates.min().strftime("%Y-%m-%d")
        max_date = valid_dates.max().strftime("%Y-%m-%d")
        return min_date, max_date
    except Exception:
        return "-", "-"

# -------------------------------
# الواجهة الرئيسية
# -------------------------------
st.set_page_config(page_title="CMMS - Bail Yarn", layout="wide", page_icon="🏭")

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
    st.subheader("🔄 تحديث البيانات")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📥 تحميل حديث", help="تحميل أحدث نسخة من GitHub", use_container_width=True):
            if download_from_github():
                st.success("✅ تم تحميل أحدث نسخة")

    with col2:
        if st.button("🔄 تحديث البيانات", help="تحديث البيانات من الملف المحلي", use_container_width=True):
            if clear_cache_and_reload():
                st.success("✅ تم تحديث البيانات")

    with col3:
        if st.button("🔄 إعادة تحميل", help="إعادة تحميل الصفحة", use_container_width=True):
            st.rerun()
    
    st.markdown("---")
    st.subheader("📊 حالة النظام")
    
    if os.path.exists(LOCAL_FILE):
        file_time = datetime.fromtimestamp(os.path.getmtime(LOCAL_FILE))
        file_size = os.path.getsize(LOCAL_FILE)
        st.success(f"📁 الملف: {file_time.strftime('%H:%M:%S')}")
        st.info(f"📊 الحجم: {file_size:,} بايت")
        
        # معلومات الملف
        try:
            sheets = load_excel_fresh()
            if sheets:
                st.info(f"📋 عدد الشيتات: {len(sheets)}")
                total_rows = sum(len(df) for df in sheets.values())
                st.info(f"📈 إجمالي الصفوف: {total_rows:,}")
        except:
            pass
    else:
        st.error("❌ الملف غير موجود")
    
    # حالة GitHub
    try:
        token = st.secrets.get("github", {}).get("token")
        if token and GITHUB_AVAILABLE:
            st.success("🔗 GitHub: متصل")
        else:
            st.info("🔗 GitHub: بدون توكن")
    except:
        st.error("🔗 GitHub: خطأ في التكوين")
    
    st.markdown("---")
    
    # إحصائيات الجلسة
    active_sessions = [u for u, info in state.items() if info.get("active")]
    st.metric("المستخدمين النشطين", f"{len(active_sessions)} / {MAX_ACTIVE_USERS}")
    
    if st.button("🚪 تسجيل الخروج", use_container_width=True):
        logout_action()

# التبويبات الرئيسية
st.title("🏭 CMMS - Bail Yarn")
st.markdown("نظام إدارة صيانة الماكينات - الإصدار 2.0")

tabs = st.tabs(["📊 عرض وفحص الماكينات", "🛠 تعديل وإدارة البيانات", "⚙ إدارة المستخدمين", "📈 التقارير والإحصائيات"])

# -------------------------------
# Tab 1: عرض وفحص الماكينات
# -------------------------------
with tabs[0]:
    st.header("📊 عرض وفحص الماكينات")
    
    # زر تحديث البيانات
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 تحديث البيانات", key="refresh_tab1", use_container_width=True):
            clear_cache_and_reload()
    
    if not os.path.exists(LOCAL_FILE):
        st.error("❌ الملف غير موجود. اضغط 'تحميل من GitHub' في الشريط الجانبي.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            card_num = st.number_input("رقم الماكينة:", min_value=1, step=1, key="card_num_main")
        with col2:
            current_tons = st.number_input("عدد الأطنان الحالية:", min_value=0, step=100, key="current_tons_main")

        if st.button("🔍 فحص الحالة الآن", type="primary", use_container_width=True):
            check_machine_status_realtime(card_num, current_tons)

# -------------------------------
# Tab 2: تعديل وإدارة البيانات
# -------------------------------
with tabs[1]:
    st.header("🛠 تعديل وإدارة البيانات")
    
    # زر تحديث البيانات
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 تحديث البيانات", key="refresh_tab2", use_container_width=True):
            clear_cache_and_reload()
    
    username = st.session_state.get("username")
    token_exists = bool(st.secrets.get("github", {}).get("token", None))
    can_push = (username == "admin") or (token_exists and GITHUB_AVAILABLE)

    with st.spinner("🔄 جاري تحميل البيانات..."):
        sheets_data = load_excel_for_edit()
    
    if not sheets_data:
        st.error("❌ لا يمكن تحميل البيانات")
    else:
        tab1, tab2, tab3, tab4 = st.tabs(["✏ تعديل البيانات", "➕ إضافة صف جديد", "🆕 إضافة عمود", "🗑 حذف صف"])

        # Tab1 - تعديل وعرض
        with tab1:
            st.subheader("✏ تعديل البيانات")
            sheet_name = st.selectbox("اختر الشيت:", list(sheets_data.keys()), key="edit_sheet")
            
            if sheet_name in sheets_data:
                df = sheets_data[sheet_name].copy()
                st.write(f"عدد الصفوف: {len(df)} | عدد الأعمدة: {len(df.columns)}")
                
                edited_df = st.data_editor(df, num_rows="dynamic", key=f"editor_{sheet_name}",
                                         use_container_width=True)

                if st.button("💾 حفظ التعديلات", key=f"save_{sheet_name}", type="primary", use_container_width=True):
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
                cols = st.columns(3)
                for i, col in enumerate(df_add.columns):
                    with cols[i % 3]:
                        new_data[col] = st.text_input(f"{col}", key=f"new_{sheet_name_add}_{col}")

                if st.button("💾 إضافة الصف", key=f"add_{sheet_name_add}", type="primary", use_container_width=True):
                    min_col, max_col, card_col = find_range_columns(df_add)
                    
                    if not min_col or not max_col:
                        st.error("⚠ لم يتم العثور على أعمدة Min_Tones و/أو Max_Tones في الشيت.")
                    else:
                        insert_pos = calculate_insert_position(df_add, new_data, min_col, max_col, card_col)
                        
                        new_row_df = pd.DataFrame([new_data])
                        df_top = df_add.iloc[:insert_pos].reset_index(drop=True)
                        df_bottom = df_add.iloc[insert_pos:].reset_index(drop=True)
                        df_new = pd.concat([df_top, new_row_df, df_bottom], ignore_index=True)
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
                st.write(f"الأعمدة الحالية: {', '.join(df_col.columns.tolist())}")
                
                new_col_name = st.text_input("اسم العمود الجديد:")
                default_value = st.text_input("القيمة الافتراضية (اختياري):", "")
                
                col1, col2 = st.columns(2)
                with col1:
                    data_type = st.selectbox("نوع البيانات:", ["نص", "رقم", "تاريخ"])
                with col2:
                    required = st.checkbox("حقل مطلوب")

                if st.button("💾 إضافة العمود", key=f"add_col_{sheet_name_col}", type="primary", use_container_width=True):
                    if new_col_name:
                        if new_col_name in df_col.columns:
                            st.warning("⚠ هذا العمود موجود بالفعل!")
                        else:
                            # تعيين القيمة الافتراضية بناءً على نوع البيانات
                            if data_type == "رقم":
                                try:
                                    default_value = float(default_value) if default_value else 0
                                except:
                                    default_value = 0
                            elif data_type == "تاريخ":
                                default_value = default_value if default_value else datetime.now().strftime("%Y-%m-%d")
                            
                            df_col[new_col_name] = default_value
                            sheets_data[sheet_name_col] = df_col
                            
                            if save_to_github(sheets_data, f"إضافة عمود '{new_col_name}' في {sheet_name_col} بواسطة {username}"):
                                st.balloons()
                                st.success("✅ تم إضافة العمود بنجاح! انتقل إلى تبويب الفحص لرؤية التغييرات.")
                    else:
                        st.warning("⚠ الرجاء إدخال اسم العمود")

        # Tab4 - حذف صف
        with tab4:
            st.subheader("🗑 حذف صف من الشيت")
            sheet_name_del = st.selectbox("اختر الشيت:", list(sheets_data.keys()), key="delete_sheet")
            
            if sheet_name_del in sheets_data:
                df_del = sheets_data[sheet_name_del].copy()

                st.markdown("### 📋 بيانات الشيت الحالية")
                st.dataframe(df_del, use_container_width=True)

                st.markdown("### ✏ اختر الصفوف للحذف")
                st.write("💡 ملاحظة: رقم الصف يبدأ من 0 (أول صف = 0)")
                
                rows_to_delete = st.text_input("أدخل أرقام الصفوف مفصولة بفاصلة (مثلاً: 0,2,5):")
                show_preview = st.checkbox("عرض معاينة قبل الحذف")
                
                if rows_to_delete:
                    try:
                        rows_list = [int(x.strip()) for x in rows_to_delete.split(",") if x.strip().isdigit()]
                        rows_list = [r for r in rows_list if 0 <= r < len(df_del)]
                        
                        if rows_list:
                            if show_preview:
                                st.warning(f"⚠ سيتم حذف {len(rows_list)} صفوف:")
                                preview_df = df_del.iloc[rows_list]
                                st.dataframe(preview_df, use_container_width=True)
                            
                            confirm_delete = st.checkbox("✅ أؤكد أني أريد حذف هذه الصفوف بشكل نهائي")
                            
                            if st.button("🗑 تنفيذ الحذف", key=f"delete_rows_{sheet_name_del}", type="primary", use_container_width=True):
                                if not confirm_delete:
                                    st.warning("⚠ برجاء تأكيد الحذف أولاً")
                                else:
                                    df_new = df_del.drop(rows_list).reset_index(drop=True)
                                    sheets_data[sheet_name_del] = df_new
                                    
                                    if save_to_github(sheets_data, f"حذف {len(rows_list)} صفوف من {sheet_name_del} بواسطة {username}"):
                                        st.balloons()
                                        st.success(f"✅ تم حذف {len(rows_list)} صفوف بنجاح!")
                        else:
                            st.warning("⚠ لم يتم العثور على صفوف صحيحة.")
                    except Exception as e:
                        st.error(f"❌ حدث خطأ أثناء معالجة البيانات: {e}")

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
            
            # تحضير بيانات المستخدمين للعرض
            users_data = []
            for user, info in users.items():
                users_data.append({
                    "المستخدم": user,
                    "الدور": info.get("role", "مستخدم"),
                    "الحالة": "نشط" if load_state().get(user, {}).get("active") else "غير نشط"
                })
            
            users_df = pd.DataFrame(users_data)
            st.dataframe(users_df, use_container_width=True)
            
            st.metric("إجمالي المستخدمين", len(users))
            
            st.subheader("🗑 حذف مستخدم")
            del_user = st.selectbox("اختر مستخدم للحذف:", 
                                   [u for u in users.keys() if u != "admin"],
                                   key="del_user_select")
            
            if st.button("حذف المستخدم", type="secondary", use_container_width=True):
                if del_user in users:
                    users.pop(del_user)
                    save_users(users)
                    st.success(f"✅ تم حذف المستخدم '{del_user}'")
                    st.rerun()

        with col2:
            st.subheader("➕ إضافة مستخدم جديد")
            
            new_user = st.text_input("اسم المستخدم الجديد:", placeholder="أدخل اسم المستخدم")
            new_pass = st.text_input("كلمة المرور:", type="password", placeholder="أدخل كلمة المرور")
            confirm_pass = st.text_input("تأكيد كلمة المرور:", type="password", placeholder="أكد كلمة المرور")
            user_role = st.selectbox("دور المستخدم:", ["مستخدم", "مشرف", "فني"])
            
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
                        "role": user_role,
                        "created_at": datetime.now().isoformat()
                    }
                    save_users(users)
                    st.success(f"✅ تم إضافة المستخدم '{new_user}' بنجاح")
                    st.rerun()

        # قسم الإحصائيات
        st.markdown("---")
        st.subheader("📊 إحصائيات المستخدمين")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            active_count = len([u for u, info in load_state().items() if info.get("active")])
            st.metric("المستخدمين النشطين", active_count)
        with col2:
            admin_count = len([u for u, info in users.items() if info.get("role") == "مشرف"])
            st.metric("المشرفين", admin_count)
        with col3:
            st.metric("السعة المتاحة", f"{MAX_ACTIVE_USERS} مستخدم")

# -------------------------------
# Tab 4: التقارير والإحصائيات - الإصدار المصحح
# -------------------------------
with tabs[3]:
    st.header("📈 التقارير والإحصائيات")
    
    # زر تحديث البيانات
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 تحديث البيانات", key="refresh_tab4", use_container_width=True):
            clear_cache_and_reload()
    
    if not os.path.exists(LOCAL_FILE):
        st.warning("⚠ لا توجد بيانات لعرض التقارير")
    else:
        with st.spinner("🔄 جاري تحميل البيانات..."):
            sheets_data = load_excel_fresh()
        
        if not sheets_data:
            st.error("❌ لا يمكن تحميل البيانات من الملف")
        else:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                total_sheets = len(sheets_data)
                st.metric("عدد الشيتات", total_sheets)
            
            with col2:
                total_rows = sum(len(df) for df in sheets_data.values())
                st.metric("إجمالي الصفوف", f"{total_rows:,}")
            
            with col3:
                card_sheets = [name for name in sheets_data.keys() if name.startswith('Card')]
                st.metric("شيتات الماكينات", len(card_sheets))
            
            st.markdown("---")
            
            # تحليل شيتات الماكينات - الإصدار المصحح
            st.subheader("📋 تحليل شيتات الماكينات")
            
            if card_sheets:
                machine_data = []
                
                for sheet_name in card_sheets:
                    df = sheets_data[sheet_name]
                    
                    # استخدام الدالة المحسنة لتحليل التواريخ
                    first_date, last_date = safe_date_analysis(df, 'Date')
                    
                    machine_data.append({
                        "الشيت": sheet_name,
                        "عدد الصفوف": len(df),
                        "عدد الأعمدة": len(df.columns),
                        "أول تاريخ": first_date,
                        "آخر تاريخ": last_date
                    })
                
                if machine_data:
                    machine_df = pd.DataFrame(machine_data)
                    st.dataframe(machine_df, use_container_width=True)
                else:
                    st.info("📭 لا توجد بيانات لشيتات الماكينات")
            else:
                st.info("📭 لا توجد شيتات ماكينات (Card) للتحليل")
            
            # ServicePlan analysis - الإصدار المصحح
            st.subheader("📊 تحليل خطط الصيانة")
            if "ServicePlan" in sheets_data:
                service_df = sheets_data["ServicePlan"]
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("*ملخص خطط الصيانة:*")
                    st.write(f"- عدد الشرائح: {len(service_df)}")
                    
                    # حساب نطاق الأطنان بشكل آمن
                    try:
                        if 'Min_Tones' in service_df.columns and 'Max_Tones' in service_df.columns:
                            min_tones = service_df['Min_Tones'].min()
                            max_tones = service_df['Max_Tones'].max()
                            st.write(f"- نطاق الأطنان: {min_tones} إلى {max_tones}")
                        else:
                            st.write("- نطاق الأطنان: غير متوفر")
                    except Exception as e:
                        st.write(f"- نطاق الأطنان: خطأ في الحساب - {e}")
                
                with col2:
                    if 'Service' in service_df.columns:
                        try:
                            # تحويل القيم إلى نص قبل التقسيم
                            services = service_df['Service'].fillna('').astype(str)
                            services_split = services.str.split('[+,]').explode().str.strip()
                            services_split = services_split[services_split != '']
                            
                            if not services_split.empty:
                                service_counts = services_split.value_counts()
                                st.write("*الخدمات الأكثر تكراراً:*")
                                for service, count in service_counts.head(5).items():
                                    st.write(f"- {service}: {count} مرة")
                            else:
                                st.write("- لا توجد خدمات للتحليل")
                        except Exception as e:
                            st.write(f"- تحليل الخدمات: خطأ - {e}")
                    else:
                        st.write("- تحليل الخدمات: عمود الخدمات غير موجود")
            else:
                st.info("📭 لا يوجد شيت ServicePlan للتحليل")
            
            # إحصائيات إضافية
            st.markdown("---")
            st.subheader("📈 إحصائيات إضافية")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("*معلومات الشيتات:*")
                for sheet_name, df in list(sheets_data.items())[:5]:  # عرض أول 5 شيتات فقط
                    st.write(f"- {sheet_name}: {len(df)} صف، {len(df.columns)} عمود")
                
                if len(sheets_data) > 5:
                    st.write(f"- ... و{len(sheets_data) - 5} شيتات أخرى")
            
            with col2:
                st.write("*حالة النظام:*")
                st.write(f"- وقت التحميل: {datetime.now().strftime('%H:%M:%S')}")
                if os.path.exists(LOCAL_FILE):
                    st.write(f"- حجم الملف: {os.path.getsize(LOCAL_FILE):,} بايت")
                active_users = len([u for u, info in load_state().items() if info.get('active')])
                st.write(f"- عدد المستخدمين النشطين: {active_users}")
            
            # تنزيل التقارير - الإصدار المصحح
            st.markdown("---")
            st.subheader("📥 تنزيل التقارير")
            
            report_type = st.selectbox("اختر نوع التقرير:", 
                                     ["ملخص عام", "تحليل الماكينات", "خطط الصيانة", "جميع البيانات"])
            
            if st.button("🔄 إنشاء التقرير", type="primary", key="generate_report"):
                with st.spinner("جاري إنشاء التقرير..."):
                    try:
                        buffer = io.BytesIO()
                        
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            if report_type == "ملخص عام":
                                summary_data = {
                                    "الإحصائية": [
                                        "إجمالي الشيتات", 
                                        "إجمالي الصفوف", 
                                        "شيتات الماكينات",
                                        "وقت الإنشاء"
                                    ],
                                    "القيمة": [
                                        total_sheets,
                                        total_rows,
                                        len(card_sheets),
                                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    ]
                                }
                                pd.DataFrame(summary_data).to_excel(writer, sheet_name="ملخص عام", index=False)
                                
                            elif report_type == "تحليل الماكينات" and card_sheets:
                                if 'machine_df' in locals():
                                    machine_df.to_excel(writer, sheet_name="تحليل الماكينات", index=False)
                                else:
                                    st.warning("⚠ لا توجد بيانات لتحليل الماكينات")
                                    
                                
                            elif report_type == "خطط الصيانة" and "ServicePlan" in sheets_data:
                                service_df.to_excel(writer, sheet_name="خطط الصيانة", index=False)
                                
                            elif report_type == "جميع البيانات":
                                for sheet_name, df in sheets_data.items():
                                    # تقليل طول اسم الشيت إذا كان طويلاً جداً
                                    safe_sheet_name = sheet_name[:31]  # Excel limit
                                    df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
                        
                        # تقديم زر التحميل فقط إذا كان التقرير يحتوي على بيانات
                        st.download_button(
                            label="💾 تحميل التقرير",
                            data=buffer.getvalue(),
                            file_name=f"report_{report_type}{datetime.now().strftime('%Y%m%d%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_report"
                        )
                        
                    except Exception as e:
                        st.error(f"❌ خطأ في إنشاء التقرير: {str(e)}")

# -------------------------------
# تذييل الصفحة والمساعدة
# -------------------------------
st.sidebar.markdown("---")
with st.sidebar.expander("ℹ المساعدة والدعم"):
    st.markdown("""
    *📖 دليل الاستخدام السريع:*
    
    🔍 *فحص الماكينات:*
    - أدخل رقم الماكينة والأطنان
    - اضغط "فحص الحالة الآن"
    - اختر نطاق العرض المناسب
    
    ✏ *تعديل البيانات:*
    - اختر الشيت المطلوب
    - عدل مباشرة في الجدول
    - احفظ التغييرات
    
    👥 *إدارة المستخدمين:*
    - للمسؤولين فقط
    - إضافة/حذف المستخدمين
    - تحديد الصلاحيات
    
    🔄 *المزامنة:*
    - استخدم "تحميل" لأحدث نسخة
    - البيانات تحفظ تلقائياً في GitHub
    - يمكن العمل من أي مكان
    
    *📞 الدعم الفني:*
    - في حالة وجود مشاكل او محتاج دعم فني مقترح يرجي تواصل عبر واتساب (01274424062)
    """)

st.markdown("---")
footer = """
<div style="text-align: center; color: gray; padding: 20px;">
    <p><strong>نظام إدارة صيانة الماكينات (CMMS) - Bail Yarn</strong></p>
    <p>الإصدار 2.0 | تم التطوير باستخدام Streamlit | © 2024</p>
</div>
"""
st.markdown(footer, unsafe_allow_html=True)

# -------------------------------
# التهيئة الأولية
# -------------------------------
if not os.path.exists(LOCAL_FILE):
    st.sidebar.info("🔄 جاري التحميل الأولي...")
    if download_from_github():
        st.sidebar.success("✅ تم التهيئة بنجاح")
        st.rerun()
    else:
        st.sidebar.error("❌ فشل التحميل الأولي")

