import streamlit as st
import pandas as pd
import json
import os
import io
import requests
import shutil
import re
from datetime import datetime, timedelta
from base64 import b64decode

# محاولة استيراد PyGithub (لرفع التعديلات)
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
SESSION_DURATION = timedelta(minutes=10)  # مدة الجلسة 10 دقائق
MAX_ACTIVE_USERS = 2  # أقصى عدد مستخدمين مسموح

# إعدادات GitHub (مسارات الملف والريبو)
REPO_NAME = "mahmedabdallh123/input-data"  # عدل إذا لزم
BRANCH = "main"
FILE_PATH = "Machine_Service_Lookup.xlsx"
LOCAL_FILE = "Machine_Service_Lookup.xlsx"
GITHUB_EXCEL_URL = "https://github.com/mahmedabdallh123/input-data/raw/refs/heads/main/Machine_Service_Lookup.xlsx"

# -------------------------------
# 🧩 دوال مساعدة للملفات والحالة
# -------------------------------
def load_users():
    if not os.path.exists(USERS_FILE):
        # انشئ ملف افتراضي اذا مش موجود (يوجد admin بكلمة مرور افتراضية "admin" — غيرها فورًا)
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
    except:
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
            except:
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
# 🔐 تسجيل الخروج
# -------------------------------
def logout_action():
    state = load_state()
    username = st.session_state.get("username")
    if username and username in state:
        state[username]["active"] = False
        state[username].pop("login_time", None)
        save_state(state)
    # احذف متغيرات الجلسة
    keys = list(st.session_state.keys())
    for k in keys:
        st.session_state.pop(k, None)
    st.rerun()

# -------------------------------
# 🧠 واجهة تسجيل الدخول (مأخوذ وموسع)
# -------------------------------
def login_ui():
    users = load_users()
    state = cleanup_sessions(load_state())
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = None

    st.title("🔐 تسجيل الدخول - Bail Yarn (CMMS)")

    # اختيار المستخدم
    username_input = st.selectbox("👤 اختر المستخدم", list(users.keys()))
    password = st.text_input("🔑 كلمة المرور", type="password")

    active_users = [u for u, v in state.items() if v.get("active")]
    active_count = len(active_users)
    st.caption(f"🔒 المستخدمون النشطون الآن: {active_count} / {MAX_ACTIVE_USERS}")

    if not st.session_state.logged_in:
        if st.button("تسجيل الدخول"):
            if username_input in users and users[username_input]["password"] == password:
                if username_input == "admin":
                    pass
                elif username_input in active_users:
                    st.warning("⚠ هذا المستخدم مسجل دخول بالفعل.")
                    return False
                elif active_count >= MAX_ACTIVE_USERS:
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
# 🔄 طرق جلب الملف من GitHub
# -------------------------------
def fetch_from_github_requests():
    """تحميل بإستخدام رابط RAW (requests)"""
    try:
        response = requests.get(GITHUB_EXCEL_URL, stream=True, timeout=15)
        response.raise_for_status()
        with open(LOCAL_FILE, "wb") as f:
            shutil.copyfileobj(response.raw, f)
        # امسح الكاش
        try:
            st.cache_data.clear()
        except:
            pass
        return True
    except Exception as e:
        st.error(f"⚠ فشل التحديث من GitHub: {e}")
        return False

def fetch_from_github_api():
    """تحميل عبر GitHub API (باستخدام PyGithub token في secrets)"""
    if not GITHUB_AVAILABLE:
        return fetch_from_github_requests()
    
    try:
        token = st.secrets.get("github", {}).get("token", None)
        if not token:
            return fetch_from_github_requests()
        
        g = Github(token)
        repo = g.get_repo(REPO_NAME)
        file_content = repo.get_contents(FILE_PATH, ref=BRANCH)
        content = b64decode(file_content.content)
        with open(LOCAL_FILE, "wb") as f:
            f.write(content)
        try:
            st.cache_data.clear()
        except:
            pass
        return True
    except Exception as e:
        st.error(f"⚠ فشل تحميل الملف من GitHub: {e}")
        return False

# -------------------------------
# 📂 تحميل الشيتات (مخبأ) - معدل لقراءة جميع الشيتات
# -------------------------------
@st.cache_data(show_spinner=False)
def load_all_sheets():
    """تحميل جميع الشيتات من ملف Excel"""
    if not os.path.exists(LOCAL_FILE):
        return None
    
    try:
        # قراءة جميع الشيتات
        sheets = pd.read_excel(LOCAL_FILE, sheet_name=None)
        
        if not sheets:
            return None
        
        # تنظيف أسماء الأعمدة لكل شيت
        for name, df in sheets.items():
            df.columns = df.columns.astype(str).str.strip()
        
        return sheets
    except Exception as e:
        return None

# نسخة مع dtype=object لواجهة التحرير
@st.cache_data(show_spinner=False)
def load_sheets_for_edit():
    """تحميل جميع الشيتات للتحرير"""
    if not os.path.exists(LOCAL_FILE):
        return None
    
    try:
        # قراءة جميع الشيتات مع dtype=object للحفاظ على تنسيق البيانات
        sheets = pd.read_excel(LOCAL_FILE, sheet_name=None, dtype=object)
        
        if not sheets:
            return None
        
        # تنظيف أسماء الأعمدة لكل شيت
        for name, df in sheets.items():
            df.columns = df.columns.astype(str).str.strip()
        
        return sheets
    except Exception as e:
        return None

# -------------------------------
# 🔁 حفظ محلي + رفع على GitHub + مسح الكاش + إعادة تحميل
# -------------------------------
def save_local_excel_and_push(sheets_dict, commit_message="Update from Streamlit"):
    # احفظ محلياً
    try:
        with pd.ExcelWriter(LOCAL_FILE, engine="openpyxl") as writer:
            for name, sh in sheets_dict.items():
                try:
                    sh.to_excel(writer, sheet_name=name, index=False)
                except Exception:
                    sh.astype(object).to_excel(writer, sheet_name=name, index=False)
    except Exception as e:
        st.error(f"⚠ خطأ أثناء الحفظ المحلي: {e}")
        return load_sheets_for_edit()

    # امسح الكاش
    try:
        st.cache_data.clear()
    except:
        pass

    # حاول الرفع عبر PyGithub token في secrets
    token = st.secrets.get("github", {}).get("token", None)
    if not token:
        return load_sheets_for_edit()

    if not GITHUB_AVAILABLE:
        return load_sheets_for_edit()

    try:
        g = Github(token)
        repo = g.get_repo(REPO_NAME)
        with open(LOCAL_FILE, "rb") as f:
            content = f.read()

        try:
            contents = repo.get_contents(FILE_PATH, ref=BRANCH)
            repo.update_file(path=FILE_PATH, message=commit_message, content=content, sha=contents.sha, branch=BRANCH)
        except Exception:
            # حاول رفع كملف جديد أو إنشاء
            try:
                repo.create_file(path=FILE_PATH, message=commit_message, content=content, branch=BRANCH)
            except Exception:
                return load_sheets_for_edit()

        return load_sheets_for_edit()
    except Exception:
        return load_sheets_for_edit()

# -------------------------------
# 🧰 دوال مساعدة للمعالجة والنصوص
# -------------------------------
def normalize_name(s):
    if s is None: return ""
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
        "Service Done": "background-color: #d4edda; color:#155724; font-weight:bold;",
        "Service Didn't Done": "background-color: #f8d7da; color:#721c24; font-weight:bold;",
        "Date": "background-color: #e7f1ff; color:#004085; font-weight:bold;",
        "Tones": "background-color: #e8f8f5; color:#0d5c4a; font-weight:bold;",
        "Min_Tons": "background-color: #ebf5fb; color:#154360; font-weight:bold;",
        "Max_Tons": "background-color: #f9ebea; color:#641e16; font-weight:bold;",
        "Event": "background-color: #e2f0d9; color:#2e6f32; font-weight:bold;",
        "Correction": "background-color: #fdebd0; color:#7d6608; font-weight:bold;",
        "Servised by": "background-color: #f0f0f0; color:#333; font-weight:bold;",
        "Card Number": "background-color: #ebdef0; color:#4a235a; font-weight:bold;"
    }
    return color_map.get(col_name, "")

def style_table(row):
    return [highlight_cell(row[col], col) for col in row.index]

# -------------------------------
# 🖥 دالة فحص الماكينة - معدلة لعرض جميع الأحداث
# -------------------------------
def check_machine_status(card_num, current_tons, all_sheets):
    if not all_sheets:
        st.error("❌ لم يتم تحميل أي شيتات.")
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

    # نطاق العرض
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
        col1, col2 = st.columns(2)
        with col1:
            min_range = st.number_input("من (طن):", min_value=0, step=100, value=min_range, key="min_range")
        with col2:
            max_range = st.number_input("إلى (طن):", min_value=min_range, step=100, value=max_range, key="max_range")

    # اختيار الشرائح
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

        if not matching_rows.empty:
            # نمر على كل صف (حدث) في الصفوف المطابقة
            for _, row in matching_rows.iterrows():
                done_services_set = set()
                
                # تحديد الأعمدة التي تحتوي على خدمات منجزة
                ignore_cols = {"card", "Tones", "Min_Tones", "Max_Tones", "Date", "Other", "Servised by", "Event", "Correction"}
                for col in matching_rows.columns:
                    if col not in ignore_cols:
                        val = str(row.get(col, "")).strip()
                        if val and val.lower() not in ["nan", "none", ""]:
                            done_services_set.add(col)

                # جمع بيانات الحدث
                current_date = str(row.get("Date", "")).strip() if pd.notna(row.get("Date")) else "-"
                current_tones = str(row.get("Tones", "")).strip() if pd.notna(row.get("Tones")) else "-"
                current_other = str(row.get("Other", "")).strip() if pd.notna(row.get("Other")) else "-"
                current_servised_by = str(row.get("Servised by", "")).strip() if pd.notna(row.get("Servised by")) else "-"
                current_event = str(row.get("Event", "")).strip() if pd.notna(row.get("Event")) else "-"
                current_correction = str(row.get("Correction", "")).strip() if pd.notna(row.get("Correction")) else "-"

                done_services = sorted(list(done_services_set))
                done_norm = [normalize_name(c) for c in done_services]
                not_done = [orig for orig, n in zip(needed_parts, needed_norm) if n not in done_norm]

                all_results.append({
                    "Card Number": card_num,
                    "Min_Tons": slice_min,
                    "Max_Tons": slice_max,
                    "Service Needed": " + ".join(needed_parts) if needed_parts else "-",
                    "Service Done": ", ".join(done_services) if done_services else "-",
                    "Service Didn't Done": ", ".join(not_done) if not_done else "-",
                    "Tones": current_tones,
                    "Event": current_event,
                    "Correction": current_correction,
                    "Servised by": current_servised_by,
                    "Date": current_date
                })
        else:
            # إذا لم توجد أحداث، نضيف سجل للشريحة بدون خدمات منجزة
            all_results.append({
                "Card Number": card_num,
                "Min_Tons": slice_min,
                "Max_Tons": slice_max,
                "Service Needed": " + ".join(needed_parts) if needed_parts else "-",
                "Service Done": "-",
                "Service Didn't Done": ", ".join(needed_parts) if needed_parts else "-",
                "Tones": "-",
                "Event": "-",
                "Correction": "-",
                "Servised by": "-",
                "Date": "-"
            })

    result_df = pd.DataFrame(all_results).dropna(how="all").reset_index(drop=True)

    st.markdown("### 📋 نتائج الفحص - جميع الأحداث")
    st.dataframe(result_df.style.apply(style_table, axis=1), use_container_width=True)

    # تنزيل النتائج
    buffer = io.BytesIO()
    result_df.to_excel(buffer, index=False, engine="openpyxl")
    st.download_button(
        label="💾 حفظ النتائج كـ Excel",
        data=buffer.getvalue(),
        file_name=f"Service_Report_Card{card_num}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# -------------------------------
# 🖥 الواجهة الرئيسية المدمجة
# -------------------------------
# إعداد الصفحة
st.set_page_config(page_title="CMMS - Bail Yarn", layout="wide")

# شريط تسجيل الدخول / معلومات الجلسة في الشريط الجانبي
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
    st.write("🔧 أدوات:")
    if st.button("🔄 تحديث الملف من GitHub"):
        if fetch_from_github_requests():
            st.rerun()
    
    # زر مسح الكاش
    if st.button("🗑 مسح الكاش"):
        try:
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"❌ خطأ في مسح الكاش: {e}")
    
    st.markdown("---")
    # زر لإعادة تسجيل الخروج
    if st.button("🚪 تسجيل الخروج"):
        logout_action()

# تحميل الشيتات (عرض وتحليل)
all_sheets = load_all_sheets()

# تحميل الشيتات للتحرير (dtype=object)
sheets_edit = load_sheets_for_edit()

# واجهة التبويبات الرئيسية
st.title("🏭 CMMS - Bail Yarn")

# التحقق من الصلاحيات لعرض التبويبات المناسبة
username = st.session_state.get("username")
is_admin = username == "admin"

# تحديد التبويبات بناءً على نوع المستخدم
if is_admin:
    tabs = st.tabs(["📊 عرض وفحص الماكينات", "🛠 تعديل وإدارة البيانات", "📞 الدعم الفني"])
else:
    tabs = st.tabs(["📊 عرض وفحص الماكينات", "📞 الدعم الفني"])

# -------------------------------
# Tab: عرض وفحص الماكينات
# -------------------------------
with tabs[0]:
    st.header("📊 عرض وفحص الماكينات")
    
    if all_sheets is None:
        st.warning("❗ الملف المحلي غير موجود. استخدم زر التحديث في الشريط الجانبي لتحميل الملف من GitHub.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            card_num = st.number_input("رقم الماكينة:", min_value=1, step=1, key="card_num_main")
        with col2:
            current_tons = st.number_input("عدد الأطنان الحالية:", min_value=0, step=100, key="current_tons_main")

        if st.button("عرض الحالة"):
            st.session_state["show_results"] = True

        if st.session_state.get("show_results", False):
            check_machine_status(card_num, current_tons, all_sheets)

# -------------------------------
# Tab: تعديل وإدارة البيانات - للمسؤول فقط
# -------------------------------
if is_admin and len(tabs) > 1:
    with tabs[1]:
        st.header("🛠 تعديل وإدارة البيانات")

        # تحقق صلاحية الرفع
        token_exists = bool(st.secrets.get("github", {}).get("token", None))
        can_push = token_exists and GITHUB_AVAILABLE

        if sheets_edit is None:
            st.warning("❗ الملف المحلي غير موجود. اضغط تحديث من GitHub في الشريط الجانبي أولًا.")
        else:
            tab1, tab2, tab3, tab4 = st.tabs([
                "عرض وتعديل شيت",
                "إضافة صف جديد",
                "إضافة عمود جديد",
                "🗑 حذف صف"
            ])

            # -------------------------------
            # Tab 1: تعديل بيانات وعرض
            # -------------------------------
            with tab1:
                st.subheader("✏ تعديل البيانات")
                sheet_name = st.selectbox("اختر الشيت:", list(sheets_edit.keys()), key="edit_sheet")
                df = sheets_edit[sheet_name].astype(str)

                edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

                if st.button("💾 حفظ التعديلات", key=f"save_edit_{sheet_name}"):
                    if not can_push:
                        st.warning("🚫 لا تملك صلاحية الرفع إلى GitHub من هذه الجلسة.")
                    else:
                        sheets_edit[sheet_name] = edited_df.astype(object)
                        new_sheets = save_local_excel_and_push(
                            sheets_edit,
                            commit_message=f"Edit sheet {sheet_name} by {st.session_state.get('username')}"
                        )
                        if isinstance(new_sheets, dict):
                            sheets_edit = new_sheets
                        st.dataframe(sheets_edit[sheet_name])

            # -------------------------------
            # Tab 2: إضافة صف جديد (أحداث متعددة بنفس الرينج)
            # -------------------------------
            with tab2:
                st.subheader("➕ إضافة صف جديد")
                sheet_name_add = st.selectbox("اختر الشيت لإضافة صف:", list(sheets_edit.keys()), key="add_sheet")
                df_add = sheets_edit[sheet_name_add].astype(str).reset_index(drop=True)
                
                st.markdown("أدخل بيانات الحدث:")

                new_data = {}
                cols = st.columns(3)
                for i, col in enumerate(df_add.columns):
                    with cols[i % 3]:
                        new_data[col] = st.text_input(f"{col}", key=f"add_{sheet_name_add}_{col}")

                if st.button("💾 إضافة الصف الجديد", key=f"add_row_{sheet_name_add}"):

                    new_row_df = pd.DataFrame([new_data]).astype(str)

                    # البحث عن أعمدة الرينج
                    min_col, max_col, card_col = None, None, None
                    for c in df_add.columns:
                        c_low = c.strip().lower()
                        if c_low in ("min_tones", "min_tone", "min tones", "min"):
                            min_col = c
                        if c_low in ("max_tones", "max_tone", "max tones", "max"):
                            max_col = c
                        if c_low in ("card", "machine", "machine_no", "machine id"):
                            card_col = c

                    if not min_col or not max_col:
                        st.error("⚠ لم يتم العثور على أعمدة Min_Tones و/أو Max_Tones في الشيت.")
                    else:
                        def to_num_or_none(x):
                            try:
                                return float(x)
                            except:
                                return None

                        new_min_raw = str(new_data.get(min_col, "")).strip()
                        new_max_raw = str(new_data.get(max_col, "")).strip()
                        new_min_num = to_num_or_none(new_min_raw)
                        new_max_num = to_num_or_none(new_max_raw)

                        # البحث عن موضع الإدراج
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

                        df_top = df_add.iloc[:insert_pos].reset_index(drop=True)
                        df_bottom = df_add.iloc[insert_pos:].reset_index(drop=True)
                        df_new = pd.concat(
                            [df_top, new_row_df.reset_index(drop=True), df_bottom],
                            ignore_index=True
                        )

                        sheets_edit[sheet_name_add] = df_new.astype(object)

                        if not can_push:
                            st.warning("🚫 لا تملك صلاحية الرفع (التغييرات ستبقى محلياً).")
                            # فقط اكتب الملف محلياً
                            with pd.ExcelWriter(LOCAL_FILE, engine="openpyxl") as writer:
                                for name, sh in sheets_edit.items():
                                    try:
                                        sh.to_excel(writer, sheet_name=name, index=False)
                                    except:
                                        sh.astype(object).to_excel(writer, sheet_name=name, index=False)
                            st.dataframe(sheets_edit[sheet_name_add])
                        else:
                            new_sheets = save_local_excel_and_push(
                                sheets_edit,
                                commit_message=f"Add new row under range {new_min_raw}-{new_max_raw} in {sheet_name_add} by {st.session_state.get('username')}"
                            )
                            if isinstance(new_sheets, dict):
                                sheets_edit = new_sheets
                            st.dataframe(sheets_edit[sheet_name_add])

            # -------------------------------
            # Tab 3: إضافة عمود جديد
            # -------------------------------
            with tab3:
                st.subheader("🆕 إضافة عمود جديد")
                sheet_name_col = st.selectbox("اختر الشيت لإضافة عمود:", list(sheets_edit.keys()), key="add_col_sheet")
                df_col = sheets_edit[sheet_name_col].astype(str)
                
                new_col_name = st.text_input("اسم العمود الجديد:")
                default_value = st.text_input("القيمة الافتراضية لكل الصفوف (اختياري):", "")

                if st.button("💾 إضافة العمود الجديد", key=f"add_col_{sheet_name_col}"):
                    if new_col_name:
                        df_col[new_col_name] = default_value
                        sheets_edit[sheet_name_col] = df_col.astype(object)
                        if not can_push:
                            # حفظ محليًا فقط
                            with pd.ExcelWriter(LOCAL_FILE, engine="openpyxl") as writer:
                                for name, sh in sheets_edit.items():
                                    try:
                                        sh.to_excel(writer, sheet_name=name, index=False)
                                    except:
                                        sh.astype(object).to_excel(writer, sheet_name=name, index=False)
                            st.dataframe(sheets_edit[sheet_name_col])
                        else:
                            new_sheets = save_local_excel_and_push(
                                sheets_edit,
                                commit_message=f"Add new column '{new_col_name}' to {sheet_name_col} by {st.session_state.get('username')}"
                            )
                            if isinstance(new_sheets, dict):
                                sheets_edit = new_sheets
                            st.dataframe(sheets_edit[sheet_name_col])
                    else:
                        st.warning("⚠ الرجاء إدخال اسم العمود الجديد.")

            # -------------------------------
            # Tab 4: حذف صف
            # -------------------------------
            with tab4:
                st.subheader("🗑 حذف صف من الشيت")
                sheet_name_del = st.selectbox("اختر الشيت:", list(sheets_edit.keys()), key="delete_sheet")
                df_del = sheets_edit[sheet_name_del].astype(str).reset_index(drop=True)

                st.markdown("### 📋 بيانات الشيت الحالية")
                st.dataframe(df_del, use_container_width=True)

                st.markdown("### ✏ اختر الصفوف التي تريد حذفها")
                rows_to_delete = st.text_input("أدخل أرقام الصفوف مفصولة بفاصلة (مثلاً: 0,2,5):")
                confirm_delete = st.checkbox("✅ أؤكد أني أريد حذف هذه الصفوف بشكل نهائي")

                if st.button("🗑 تنفيذ الحذف", key=f"delete_rows_{sheet_name_del}"):
                    if not rows_to_delete.strip():
                        st.warning("⚠ الرجاء إدخال رقم الصف أو أكثر.")
                    elif not confirm_delete:
                        st.warning("⚠ برجاء تأكيد الحذف أولاً.")
                    else:
                        try:
                            rows_list = [int(x.strip()) for x in rows_to_delete.split(",") if x.strip().isdigit()]
                            rows_list = [r for r in rows_list if 0 <= r < len(df_del)]

                            if not rows_list:
                                st.warning("⚠ لم يتم العثور على صفوف صحيحة.")
                            else:
                                df_new = df_del.drop(rows_list).reset_index(drop=True)
                                sheets_edit[sheet_name_del] = df_new.astype(object)

                                if not can_push:
                                    # حفظ محليًا فقط
                                    with pd.ExcelWriter(LOCAL_FILE, engine="openpyxl") as writer:
                                        for name, sh in sheets_edit.items():
                                            try:
                                                sh.to_excel(writer, sheet_name=name, index=False)
                                            except:
                                                sh.astype(object).to_excel(writer, sheet_name=name, index=False)
                                    st.dataframe(sheets_edit[sheet_name_del])
                                else:
                                    new_sheets = save_local_excel_and_push(sheets_edit, commit_message=f"Delete rows {rows_list} from {sheet_name_del} by {st.session_state.get('username')}")
                                    if isinstance(new_sheets, dict):
                                        sheets_edit = new_sheets
                                    st.dataframe(sheets_edit[sheet_name_del])
                        except Exception as e:
                            st.error(f"حدث خطأ أثناء الحذف: {e}")
