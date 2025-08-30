# ===== favicon 強制セット =====
from PIL import Image
import base64, time
import streamlit as st

st.set_page_config(
    page_title="Weight-Trakcer",
    page_icon=Image.open("favicon.png"),
    layout="centered",
)

def force_favicon(png_path: str):
    with open(png_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    ver = int(time.time())
    st.markdown(
        f"""
        <link rel="icon" type="image/png" href="data:image/png;base64,{b64}?v={ver}">
        <link rel="apple-touch-icon" href="data:image/png;base64,{b64}?v={ver}">
        """,
        unsafe_allow_html=True,
    )

force_favicon("favicon.png")

# ===== ライブラリ =====
import pandas as pd
import plotly.express as px
import bcrypt
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

# ===== CSS =====
st.markdown("""
<style>
.metrics-row {
  display: flex;
  justify-content: space-between;
  gap: 4px;
  margin-top: 6px;
}
.metrics-row .mcard {
  flex: 1 1 0;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  box-shadow: 0 4px 12px rgba(2,6,23,.05);
  padding: 6px 4px;
  text-align: center;
  background: #fff;
}
.metrics-row .mlabel { font-size: 0.55rem; color: #6b7280; margin-bottom: 2px; }
.metrics-row .mvalue { font-size: 0.70rem; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ===== Secrets =====
svc_json = st.secrets["GSPREAD_SERVICE_ACCOUNT_JSON"]
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]
ADMIN_CODE = st.secrets.get("ADMIN_CODE", "satomi12345")

# ===== Google Sheets =====
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_dict(svc_json, scope)
gc = gspread.authorize(credentials)
sh = gc.open_by_url(SPREADSHEET_URL)
users_ws = sh.worksheet("users")
weights_ws = sh.worksheet("weights")

# ===== Utils =====
def normalize_uid(s: str) -> str:
    return str(s).strip()

@st.cache_data(ttl=60)
def df_users() -> pd.DataFrame:
    u = pd.DataFrame(users_ws.get_all_records())
    if u.empty:
        return pd.DataFrame(columns=["user_id","password_hash","plain_password","height_cm"])
    u["user_id"] = u["user_id"].map(normalize_uid)
    return u

@st.cache_data(ttl=30)
def df_weights() -> pd.DataFrame:
    df = pd.DataFrame(weights_ws.get_all_records())
    if df.empty: return df
    df["user_id"] = df["user_id"].map(normalize_uid)
    df["date"] = pd.to_datetime(df["year"].astype(str)+"-"+df["month"].astype(str).str.zfill(2)+"-"+df["day"].astype(str).str.zfill(2), errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    return df.dropna(subset=["date","weight"]).sort_values("date")

def verify_user(user_id: str, plain_password: str) -> bool:
    u = df_users()
    row = u[u["user_id"] == user_id]
    if row.empty: return False
    hashed = str(row.iloc[0].get("password_hash", ""))
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed.encode("utf-8"))

def create_user(user_id: str, plain_password: str, height_cm_input: str):
    st.cache_data.clear()
    u = df_users()
    if not user_id or not plain_password: return "user_id と password を入力してください。"
    if not u.empty and any(u["user_id"] == user_id): return "その user_id は既に存在します。"

    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try: h = float(height_cm_input) if height_cm_input not in [None,""] else ""
    except: h = ""

    headers = users_ws.row_values(1)
    row = []
    for hname in headers:
        if hname == "user_id": row.append(user_id)
        elif hname == "password_hash": row.append(hashed)
        elif hname == "plain_password": row.append(plain_password)   # ←追加
        elif hname == "height_cm": row.append(h)
        else: row.append("")
    users_ws.append_row(row)
    return f"ユーザー {user_id} を作成しました。"

def calc_bmi(weight_kg: float, height_cm) -> str:
    try:
        h = float(height_cm)
        return f"{weight_kg / ((h/100)**2):.1f}"
    except: return "未設定"

# ===== 管理者モード =====
st.title("📈 Weight-Trakcer")
st.subheader("Administrator")

if "is_admin" not in st.session_state: st.session_state.is_admin = False
if not st.session_state.is_admin:
    code = st.text_input("ADNIN_CODE", type="password")
    if st.button("管理者モードに入る") and code == ADMIN_CODE:
        st.session_state.is_admin = True
        st.success("管理者モードに入りました。")

if st.session_state.is_admin:
    tabs_admin = st.tabs(["全員の最新情報","ユーザー追加"])
    with tabs_admin[0]:
        u = df_users()
        w = df_weights()
        rows=[]
        for uid in u["user_id"]:
            w_u = w[w["user_id"] == uid].sort_values("date")
            last_w = float(w_u.iloc[-1]["weight"]) if not w_u.empty else None
            last_d = w_u.iloc[-1]["date"].date() if not w_u.empty else None
            h = u.set_index("user_id").get("height_cm").get(uid, None)
            pw_plain = u.set_index("user_id").get("plain_password").get(uid, None)
            bmi = calc_bmi(last_w, h) if last_w else "-"
            rows.append([uid, pw_plain, last_d, last_w, h, bmi])
        df_latest = pd.DataFrame(rows, columns=["user","password","最新日","体重(kg)","身長(cm)","BMI"])
        st.dataframe(df_latest, use_container_width=True)

    with tabs_admin[1]:
        nu = st.text_input("new user_id")
        npw = st.text_input("new password", type="password")
        nh = st.text_input("height_cm（任意）")
        if st.button("ユーザー作成"):
            st.info(create_user(nu, npw, nh))
