import streamlit as st
import pandas as pd
import plotly.express as px
import bcrypt
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

# -----------------------------
# 基本設定（タイトル）
# -----------------------------
st.set_page_config(page_title="Weight-Trakcer", page_icon="📈", layout="centered")

# -----------------------------
# シンプルなUIスタイル（カード等）
# -----------------------------
st.markdown("""
<style>
html, body, [class*="css"] { font-size: 16px; }
h1 { font-size: 1.35rem; margin: .2rem 0 .8rem 0; }
h2 { font-size: 1.1rem;  margin-bottom: .6rem; }
h3 { font-size: 1.0rem;  margin-bottom: .4rem; }
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

.small-title {
  font-size: 1.0rem;
  font-weight: 700;
  margin: .2rem 0 .4rem 0;
}

.hr-space { height: 42vh; } /* 管理者をページ下方へ */
@media (max-width: 480px) {
  .stPlotlyChart { margin-left: -8px; margin-right: -8px; }
  h1 { font-size: 1.15rem; }
  .hr-space { height: 36vh; }
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Secrets から読み込み
# -----------------------------
svc_json = st.secrets["GSPREAD_SERVICE_ACCOUNT_JSON"]
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]
ADMIN_CODE = st.secrets.get("ADMIN_CODE", "satomi12345")  # デフォルト

# -----------------------------
# Google Sheets 認証
# -----------------------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_dict(svc_json, scope)
gc = gspread.authorize(credentials)
sh = gc.open_by_url(SPREADSHEET_URL)
users_ws = sh.worksheet("users")
weights_ws = sh.worksheet("weights")

# -----------------------------
# ユーティリティ
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
    if "height_cm" not in headers:
        return "users シートに height_cm ヘッダーがありません。"
    c = headers.index("height_cm") + 1
    users_ws.update_cell(r, c, str(height_cm))
    return "身長を更新しました。"

def add_weight_row(y: int, m: int, d: int, user_id: str, weight):
    st.cache_data.clear()
    try:
        _ = datetime(year=int(y), month=int(m), day=int(d))
    except Exception:
        return "日付が不正です。"
    try:
        w = float(weight)
    except Exception:
        return "体重は数値で入力してください。"
    if not (30 <= w <= 200):
        return "体重は 30〜200 の範囲で入力してください。"
    user_id = normalize_uid(user_id)
    weights_ws.append_row([int(y), int(m), int(d), user_id, w])
    return f"追加: {y}-{int(m):02d}-{int(d):02d} / {user_id} / {w}kg"

def calc_bmi(weight_kg: float, height_cm) -> str:
    try:
        h = float(height_cm)
        if h <= 0: return "未設定"
        bmi = weight_kg / ((h/100)**2)
        return f"{bmi:.1f}"
    except:
        return "未設定"

# ---- 桁UIの共通ヘルパ ----
DIGITS = list(range(0,10))
def init_height_digits(val: float):
    if val is None or pd.isna(val): val = 170.0
    v = round(float(val),1)
    hund = int(v // 100)
    tens = int((v % 100) // 10)
    ones = int(v % 10)
    tenths = int(round((v - int(v)) * 10)) % 10
    return hund, tens, ones, tenths

def init_weight_digits(val: float):
    if val is None or pd.isna(val): val = 65.0
    v = round(float(val),1)
    hund01 = min(1, int(v // 100))  # 0 or 1
    tens = int((v % 100) // 10)
    ones = int(v % 10)
    tenths = int(round((v - int(v)) * 10)) % 10
    return hund01, tens, ones, tenths

def digits_to_float(hund, tens, ones, tenths):
    return float(100*hund + 10*tens + ones + tenths/10.0)

# -----------------------------
# 画面本体
# -----------------------------
st.title("📈 Weight-Trakcer")

# セッション初期化
if "current_user" not in st.session_state: st.session_state.current_user = None
if "is_admin" not in st.session_state:     st.session_state.is_admin = False
if "weight_input" not in st.session_state: st.session_state.weight_input = 65.0
if "height_input" not in st.session_state: st.session_state.height_input = 170.0
if "user_tab" not in st.session_state:     st.session_state.user_tab = "体重グラフ"
if "period_key" not in st.session_state:   st.session_state.period_key = "1か月"

# --- LOGIN ---
st.subheader("LOGIN")
with st.container():
    cA, cB = st.columns(2)
    uid = cA.text_input("ID")
    pw  = cB.text_input("PASSWORD", type="password")
    if st.button("ログイン", key="btn_login"):
        if verify_user(uid, pw):
            st.session_state.current_user = normalize_uid(uid)
            st.success(f"ログイン成功：{st.session_state.current_user}")
        else:
            st.error("ログイン失敗")

# --- ユーザー領域（ラジオでタブ安定化） ---
if st.session_state.current_user:
    dfw = df_weights()
    du = df_users()
    me = st.session_state.current_user
    my_h = du.set_index("user_id").get("height_cm", pd.Series()).get(me, None)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.session_state.user_tab = st.radio(
        "メニュー", ["体重グラフ", "最新の記録（BMI）", "記録を追加"],
        horizontal=True, index=["体重グラフ","最新の記録（BMI）","記録を追加"].index(st.session_state.user_tab),
        key="user_tab_radio"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # === 体重グラフ ===
    if st.session_state.user_tab == "体重グラフ":
        me_df_all = dfw[dfw["user_id"] == me]
        dplot = filter_period(me_df_all, st.session_state.period_key)
        if dplot.empty:
            st.info(f"{me}: {st.session_state.period_key} の範囲にデータがありません。")
        else:
            fig = px.line(
                dplot, x="date", y="weight", markers=True,
                title=f"{me} の体重推移（{st.session_state.period_key}）",
                labels={"date":"日付","weight":"体重(kg)"}
            )
            fig.update_layout(margin=dict(l=8, r=8, t=48, b=8), font=dict(size=13))
            st.plotly_chart(
                fig, use_container_width=True,
                config={"staticPlot": True, "displayModeBar": False, "responsive": True}
            )

        st.session_state.period_key = st.radio(
            "表示期間", ["1か月","3か月","全期間"],
            horizontal=True, index=["1か月","3か月","全期間"].index(st.session_state.period_key),
            key="period_radio"
        )

        # --- 身長：□ □ □ . □ cm（各桁セレクト）
        with st.expander("身長（cm）を登録/更新する（BMI計算用）"):
            st.markdown('<div class="card">', unsafe_allow_html=True)
            init_hund, init_tens, init_ones, init_tenths = init_height_digits(my_h if my_h else st.session_state.height_input)

            colh1, colh2, colh3, colh_dot, colh4 = st.columns([1,1,1,0.3,1])
            hund = colh1.selectbox("100の位", options=DIGITS, index=init_hund, key="h_hund")
            tens = colh2.selectbox("10の位", options=DIGITS, index=init_tens, key="h_tens")
            ones = colh3.selectbox("1の位", options=DIGITS, index=init_ones, key="h_ones")
            colh_dot.markdown("<div style='text-align:center;font-weight:bold;margin-top:1.8rem;'>.</div>", unsafe_allow_html=True)
            tenths = colh4.selectbox("小数第1位", options=DIGITS, index=init_tenths, key="h_tenths")

            height_val = digits_to_float(hund, tens, ones, tenths)
            st.write(f"現在の入力値：**{height_val:.1f} cm**")

            if st.button("身長を保存", key="btn_save_height"):
                msg = update_height(me, height_val)
                st.success(msg)
                st.session_state.height_input = height_val
            st.markdown('</div>', unsafe_allow_html=True)

    # === 最新の記録（BMI） ===
    elif st.session_state.user_tab == "最新の記録（BMI）":
        me_df_sorted = dfw[dfw["user_id"] == me].sort_values("date")
        if me_df_sorted.empty:
            st.info("記録がありません。")
        else:
            last_row = me_df_sorted.iloc[-1]
            last_w = float(last_row["weight"])
            bmi_txt = calc_bmi(last_w, my_h)
            st.markdown('<div class="card compact-metrics">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            c1.metric("最新日", f"{last_row['date'].date()}")
            c2.metric("体重", f"{last_w:.1f} kg")
            c3.metric("BMI", bmi_txt)
            st.markdown('</div>', unsafe_allow_html=True)

    # === 記録を追加（体重：□ □ □ . □ kg） ===
    elif st.session_state.user_tab == "記録を追加":
        st.markdown('<div class="card">', unsafe_allow_html=True)
        today = date.today()

        c1, c2, c3 = st.columns([1,1,1])
        y = c1.number_input("年", value=today.year, step=1, format="%d", key="in_year")
        m = c2.number_input("月", value=today.month, step=1, format="%d", key="in_month")
        d = c3.number_input("日", value=today.day, step=1, format="%d", key="in_day")

        # 直近値で初期化
        init_w = st.session_state.weight_input
        iw_hund01, iw_tens, iw_ones, iw_tenths = init_weight_digits(init_w)

        colw1, colw2, colw3, colw_dot, colw4 = st.columns([1,1,1,0.3,1])
        hund01 = colw1.selectbox("100の位(0/1)", options=[0,1], index=iw_hund01, key="w_hund01")
        tens   = colw2.selectbox("10の位", options=DIGITS, index=iw_tens, key="w_tens")
        ones   = colw3.selectbox("1の位",  options=DIGITS, index=iw_ones, key="w_ones")
        colw_dot.markdown("<div style='text-align:center;font-weight:bold;margin-top:1.8rem;'>.</div>", unsafe_allow_html=True)
        tenths = colw4.selectbox("小数第1位", options=DIGITS, index=iw_tenths, key="w_tenths")

        weight_val = digits_to_float(hund01, tens, ones, tenths)
        st.write(f"現在の入力値：**{weight_val:.1f} kg**")

        if st.button("追加", key="btn_add_record"):
            st.session_state.weight_input = weight_val
            msg = add_weight_row(int(y), int(m), int(d), me, weight_val)
            st.info(msg)

        st.markdown('</div>', unsafe_allow_html=True)

# ===== スペース入れて管理者を下方に配置（半ページ分程度） =====
st.markdown('<div class="hr-space"></div>', unsafe_allow_html=True)

# --- 管理者（Administrator） ---
st.divider()
st.subheader("Administrator")

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

if not st.session_state.is_admin:
    code = st.text_input("ADNIN_CODE", type="password", key="admin_code_input")
    if st.button("管理者モードに入る", key="btn_admin_login"):
        if code == ADMIN_CODE:
            st.session_state.is_admin = True
            st.success("管理者モードに入りました。")
        else:
            st.error("合言葉が違います。")

if st.session_state.is_admin:
    tabs_admin = st.tabs(["ユーザー追加", "全員のグラフ"])

    with tabs_admin[0]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("新規ユーザーを作成します（身長は任意）")
        nu_col1, nu_col2, nu_col3 = st.columns(3)
        nu = nu_col1.text_input("new user_id（日本語OK）", key="new_uid")
        npw = nu_col2.text_input("new password", type="password", key="new_pw")
        nh  = nu_col3.text_input("height_cm（任意）", key="new_h")
        if st.button("ユーザー作成", key="btn_create_user"):
            st.info(create_user(nu, npw, nh))
        st.markdown('</div>', unsafe_allow_html=True)

    with tabs_admin[1]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        period_all = st.radio("表示期間（全員）", ["1か月","3か月","全期間"],
                              horizontal=True, key="period_all")
        dfw_all = filter_period(df_weights(), period_all)
        if dfw_all.empty:
            st.info("データがありません。")
        else:
            fig_all = px.line(
                dfw_all, x="date", y="weight", color="user_id", markers=True,
                title=f"全員の体重推移（{period_all}）",
                labels={"date":"日付","weight":"体重(kg)","user_id":"ユーザー"}
            )
            fig_all.update_layout(margin=dict(l=8, r=8, t=48, b=8), font=dict(size=13))
            st.plotly_chart(
                fig_all, use_container_width=True,
                config={"staticPlot": True, "displayModeBar": False, "responsive": True}
            )
        st.markdown('</div>', unsafe_allow_html=True)
