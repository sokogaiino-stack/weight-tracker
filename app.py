import streamlit as st
import pandas as pd
import plotly.express as px
import bcrypt
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="Weight-Trakcer", page_icon="📈", layout="centered")

# -----------------------------
# UIスタイル
# -----------------------------
st.markdown("""
<style>
html, body, [class*="css"] { font-size: 16px; }
h1 { font-size: 1.35rem; margin: .2rem 0 .8rem 0; }
h2 { font-size: 1.1rem; margin-bottom: .6rem; }
h3 { font-size: 1.0rem; margin-bottom: .4rem; }
#MainMenu { visibility: hidden; } footer { visibility: hidden; }
.block-container { padding-top: 1rem; padding-bottom: 2rem; }

.card {
  padding: 0.75rem 0.9rem;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(2,6,23,0.06);
  border: 1px solid rgba(2,6,23,0.06);
  margin-bottom: 0.8rem;
}
.compact-metrics .stMetric { padding: 0.2rem 0.4rem; }

.hr-space { height: 42vh; }
@media (max-width: 480px) {
  .hr-space { height: 36vh; }
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Secrets 読み込み
# -----------------------------
svc_json = st.secrets["GSPREAD_SERVICE_ACCOUNT_JSON"]
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]
ADMIN_CODE = st.secrets.get("ADMIN_CODE", "satomi12345")

# -----------------------------
# Google Sheets
# -----------------------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_dict(svc_json, scope)
gc = gspread.authorize(credentials)
sh = gc.open_by_url(SPREADSHEET_URL)
users_ws = sh.worksheet("users")
weights_ws = sh.worksheet("weights")

# -----------------------------
# Util
# -----------------------------
def normalize_uid(s: str) -> str:
    return str(s).replace("\u3000"," ").replace("\n"," ").replace("\r"," ").strip()

@st.cache_data(ttl=60)
def df_users() -> pd.DataFrame:
    u = pd.DataFrame(users_ws.get_all_records())
    if u.empty:
        return pd.DataFrame(columns=["user_id","password_hash","height_cm"])
    if "height_cm" not in u.columns:
        u["height_cm"] = None
    u["user_id"] = u["user_id"].map(normalize_uid)
    u["height_cm"] = pd.to_numeric(u["height_cm"], errors="coerce")
    return u

@st.cache_data(ttl=30)
def df_weights() -> pd.DataFrame:
    df = pd.DataFrame(weights_ws.get_all_records())
    if df.empty:
        return df
    df["user_id"] = df["user_id"].map(normalize_uid)
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + "-" +
        df["month"].astype(str).str.zfill(2) + "-" +
        df["day"].astype(str).str.zfill(2),
        errors="coerce"
    )
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    return df.dropna(subset=["date","weight"]).sort_values("date")

def filter_period(dfx: pd.DataFrame, key: str) -> pd.DataFrame:
    if dfx.empty: return dfx
    today = pd.Timestamp.today().normalize()
    if key == "1か月":
        since = today - relativedelta(months=1)
    elif key == "3か月":
        since = today - relativedelta(months=3)
    else:
        since = dfx["date"].min()
    return dfx[dfx["date"] >= since].sort_values("date")

def verify_user(user_id: str, plain_password: str) -> bool:
    u = df_users()
    if u.empty: return False
    user_id = normalize_uid(user_id)
    row = u[u["user_id"] == user_id]
    if row.empty: return False
    hashed = str(row.iloc[0].get("password_hash", ""))
    if not hashed: return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def create_user(user_id: str, plain_password: str, height_cm_input: str):
    st.cache_data.clear()
    user_id = normalize_uid(user_id)
    if not user_id or not plain_password:
        return "user_id と password を入力してください。"
    u = df_users()
    if not u.empty and any(u["user_id"] == user_id):
        return "その user_id は既に存在します。"
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        h = float(height_cm_input) if height_cm_input not in [None, "", " "] else ""
    except:
        h = ""
    headers = users_ws.row_values(1)
    row = []
    for hname in headers:
        if hname == "user_id":
            row.append(user_id)
        elif hname == "password_hash":
            row.append(hashed)
        elif hname == "height_cm":
            row.append(h if h != "" else "")
        else:
            row.append("")
    users_ws.append_row(row)
    return f"ユーザー {user_id} を作成しました。"

def update_height(user_id: str, height_cm: float):
    st.cache_data.clear()
    u = df_users()
    if u.empty: return "users シートが空です。"
    idx = u.index[u["user_id"] == user_id]
    if len(idx) == 0: return "ユーザーが見つかりません。"
    r = idx[0] + 2
    headers = users_ws.row_values(1)
    c = headers.index("height_cm") + 1
    users_ws.update_cell(r, c, str(height_cm))
    return "身長を更新しました。"

def add_weight_row(y: int, m: int, d: int, user_id: str, weight):
    st.cache_data.clear()
    weights_ws.append_row([int(y), int(m), int(d), user_id, float(weight)])
    return f"追加: {y}-{m:02d}-{d:02d} / {user_id} / {weight}kg"

def calc_bmi(weight_kg: float, height_cm) -> str:
    try:
        h = float(height_cm)
        if h <= 0: return "未設定"
        bmi = weight_kg / ((h/100)**2)
        return f"{bmi:.1f}"
    except:
        return "未設定"

# -----------------------------
# 桁操作ヘルパ（- / + ボタン）
# -----------------------------
def digit_control(label, value, minv, maxv, step=1, key_prefix=""):
    c1, c2, c3 = st.columns([1,2,1])
    if c1.button("−", key=f"{key_prefix}_minus"):
        value = max(minv, value - step)
    c2.markdown(f"<div style='text-align:center;font-size:1.2rem;'>{label}: {value}</div>", unsafe_allow_html=True)
    if c3.button("+", key=f"{key_prefix}_plus"):
        value = min(maxv, value + step)
    return value

# -----------------------------
# メイン画面
# -----------------------------
st.title("📈 Weight-Trakcer")

if "current_user" not in st.session_state: st.session_state.current_user = None
if "is_admin" not in st.session_state:     st.session_state.is_admin = False
if "user_tab" not in st.session_state:     st.session_state.user_tab = "体重グラフ"
if "period_key" not in st.session_state:   st.session_state.period_key = "1か月"

# --- LOGIN ---
st.subheader("LOGIN")
uid = st.text_input("ID")
pw  = st.text_input("PASSWORD", type="password")
if st.button("ログイン"):
    if verify_user(uid, pw):
        st.session_state.current_user = normalize_uid(uid)
        st.success(f"ログイン成功：{st.session_state.current_user}")
    else:
        st.error("ログイン失敗")

# --- USER AREA ---
if st.session_state.current_user:
    dfw = df_weights()
    du = df_users()
    me = st.session_state.current_user
    my_h = du.set_index("user_id").get("height_cm", pd.Series()).get(me, None)

    # 最新データで初期化
    me_df_sorted = dfw[dfw["user_id"] == me].sort_values("date")
    if not me_df_sorted.empty:
        latest_w = float(me_df_sorted.iloc[-1]["weight"])
    else:
        latest_w = 65.0
    latest_h = float(my_h) if pd.notna(my_h) else 170.0

    # タブ
    user_tab = st.radio("メニュー", ["体重グラフ","最新の記録（BMI）","記録を追加","身長を更新"], horizontal=True)
    st.session_state.user_tab = user_tab

    # === グラフ ===
    if user_tab == "体重グラフ":
        dplot = filter_period(me_df_sorted, st.session_state.period_key)
        if dplot.empty:
            st.info("データがありません")
        else:
            fig = px.line(dplot, x="date", y="weight", markers=True,
                          title=f"{me} の体重推移（{st.session_state.period_key}）")
            st.plotly_chart(fig, use_container_width=True,
                            config={"staticPlot":True,"displayModeBar":False})
        st.session_state.period_key = st.radio("表示期間",["1か月","3か月","全期間"],horizontal=True)

    # === 最新 ===
    elif user_tab == "最新の記録（BMI）":
        if me_df_sorted.empty:
            st.info("記録なし")
        else:
            last = me_df_sorted.iloc[-1]
            bmi = calc_bmi(last["weight"], latest_h)
            c1,c2,c3 = st.columns(3)
            c1.metric("日付", str(last["date"].date()))
            c2.metric("体重", f"{last['weight']:.1f}kg")
            c3.metric("BMI", bmi)

    # === 追加 ===
    elif user_tab == "記録を追加":
        today = date.today()
        y = st.number_input("年", value=today.year, step=1)
        m = st.number_input("月", value=today.month, step=1)
        d = st.number_input("日", value=today.day, step=1)
        weight_val = digit_control("体重", int(latest_w), 30, 200, 1, "w")
        if st.button("追加"):
            st.info(add_weight_row(int(y),int(m),int(d),me,weight_val))

    # === 身長 ===
    elif user_tab == "身長を更新":
        height_val = digit_control("身長", int(latest_h), 100, 299, 1, "h")
        if st.button("身長を保存"):
            st.success(update_height(me,height_val))

# --- ADMIN ---
st.divider()
st.subheader("Administrator")
if not st.session_state.is_admin:
    code = st.text_input("ADNIN_CODE", type="password")
    if st.button("管理者モードに入る"):
        if code == ADMIN_CODE:
            st.session_state.is_admin = True
            st.success("管理者モードに入りました")
        else:
            st.error("合言葉が違います")

if st.session_state.is_admin:
    tabs_admin = st.tabs(["ユーザー追加","全員のグラフ","全員の最新情報"])

    with tabs_admin[0]:
        nu = st.text_input("new user_id")
        npw = st.text_input("new password", type="password")
        nh = st.text_input("height_cm（任意）")
        if st.button("ユーザー作成"):
            st.info(create_user(nu,npw,nh))

    with tabs_admin[1]:
        period_all = st.radio("表示期間（全員）",["1か月","3か月","全期間"],horizontal=True)
        dfw_all = filter_period(df_weights(),period_all)
        if dfw_all.empty:
            st.info("データなし")
        else:
            fig = px.line(dfw_all,x="date",y="weight",color="user_id",markers=True,
                          title=f"全員の体重推移（{period_all}）")
            st.plotly_chart(fig,use_container_width=True,
                            config={"staticPlot":True,"displayModeBar":False})

    with tabs_admin[2]:
        u = df_users()
        w = df_weights()
        rows=[]
        for uid in u["user_id"]:
            w_u = w[w["user_id"]==uid].sort_values("date")
            if not w_u.empty:
                last_w = w_u.iloc[-1]["weight"]
                last_d = w_u.iloc[-1]["date"].date()
            else:
                last_w, last_d = None, None
            h = u.set_index("user_id").at[uid,"height_cm"]
            bmi = calc_bmi(last_w,h) if last_w else "未"
            rows.append([uid,last_d,last_w,h,bmi])
        df_latest = pd.DataFrame(rows,columns=["user","最新日","体重","身長","BMI"])
        st.dataframe(df_latest, use_container_width=True)
