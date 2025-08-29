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
# 管理者パスはデフォルトを satomi12345（Secretsに ADMIN_CODE があればそれを優先）
ADMIN_CODE = st.secrets.get("ADMIN_CODE", "satomi12345")

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

# -----------------------------
# 画面本体
# -----------------------------
st.title("📈 Weight-Trakcer")

# セッション
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "weight_input" not in st.session_state: st.session_state.weight_input = 65.0
if "height_input" not in st.session_state: st.session_state.height_input = 170.0

# --- LOGIN ---
st.subheader("LOGIN")
with st.container():
    cA, cB = st.columns(2)
    uid = cA.text_input("ID")
    pw  = cB.text_input("PASSWORD", type="password")
    if st.button("ログイン"):
        if verify_user(uid, pw):
            st.session_state.current_user = normalize_uid(uid)
            st.success(f"ログイン成功：{st.session_state.current_user}")
        else:
            st.error("ログイン失敗")

# --- ログイン後の機能（タブ化） ---
if st.session_state.current_user:
    dfw = df_weights()
    du = df_users()
    me = st.session_state.current_user
    my_h = du.set_index("user_id").get("height_cm", pd.Series()).get(me, None)

    tabs = st.tabs(["体重グラフ", "最新の記録（BMI）", "記録を追加"])

    # === タブ1：体重グラフ（グラフ → 期間切替 → 身長登録（スライダー＋微調整）） ===
    with tabs[0]:
        me_df_all = dfw[dfw["user_id"] == me]

        # 現在の期間でグラフ
        period_key = st.session_state.get("period_key", "1か月")
        dplot = filter_period(me_df_all, period_key)
        if dplot.empty:
            st.info(f"{me}: {period_key} の範囲にデータがありません。")
        else:
            fig = px.line(
                dplot, x="date", y="weight", markers=True,
                title=f"{me} の体重推移（{period_key}）",
                labels={"date":"日付","weight":"体重(kg)"}
            )
            fig.update_layout(margin=dict(l=8, r=8, t=48, b=8), font=dict(size=13))
            st.plotly_chart(
                fig, use_container_width=True,
                config={"staticPlot": True, "displayModeBar": False, "responsive": True}
            )

        # 期間切替
        period_key = st.radio("表示期間", ["1か月","3か月","全期間"],
                              horizontal=True,
                              index=["1か月","3か月","全期間"].index(period_key))
        st.session_state.period_key = period_key

        # 身長登録/更新（スライダー＋微調整＋直接入力）
        with st.expander("身長（cm）を登録/更新する（BMI計算用）"):
            st.markdown('<div class="card">', unsafe_allow_html=True)

            # 現在値初期化
            init_h = float(my_h) if pd.notna(my_h) else st.session_state.get("height_input", 170.0)
            h_slider = st.slider("身長（cm）", min_value=130.0, max_value=210.0,
                                 value=float(init_h), step=0.1)

            # 微調整（可変ステップ + ジャンプ）
            step_choice = st.radio("微調整ステップ", [0.1, 0.5, 1.0], horizontal=True, index=0, key="h_step_choice")
            c1, c2, c3, c4, c5 = st.columns([1,1,2,1,1])
            with c1:
                if st.button("−", key="h_minus"):
                    h_slider = round(max(130.0, h_slider - float(step_choice)), 1)
            with c2:
                if st.button("+", key="h_plus"):
                    h_slider = round(min(210.0, h_slider + float(step_choice)), 1)
            with c4:
                if st.button("−10", key="h_minus10"):
                    h_slider = round(max(130.0, h_slider - 10.0), 1)
            with c5:
                if st.button("+10", key="h_plus10"):
                    h_slider = round(min(210.0, h_slider + 10.0), 1)

            # 最終値（直接入力可）
            st.session_state.height_input = st.number_input(
                "最終値（直接入力可）", value=float(h_slider), step=0.1, format="%.1f"
            )

            if st.button("身長を保存"):
                try:
                    hval = float(st.session_state.height_input)
                    msg = update_height(me, hval)
                    st.success(msg)
                except:
                    st.error("数値で入力してください（例: 170.0）")

            st.markdown('</div>', unsafe_allow_html=True)

    # === タブ2：最新の記録（BMI） ===
    with tabs[1]:
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

    # === タブ3：記録を追加（体重スライダー＋微調整＋直接入力） ===
    with tabs[2]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        today = date.today()

        # 日付
        c1, c2, c3 = st.columns([1,1,1])
        y = c1.number_input("年", value=today.year, step=1, format="%d")
        m = c2.number_input("月", value=today.month, step=1, format="%d")
        d = c3.number_input("日", value=today.day, step=1, format="%d")

        # 体重（スライダー）
        w_slider = st.slider("体重(kg)", min_value=30.0, max_value=200.0,
                             value=float(st.session_state.get("weight_input", 65.0)), step=0.1)

        # 微調整（可変ステップ + ジャンプ）
        step_choice_w = st.radio("微調整ステップ", [0.1, 0.5, 1.0], horizontal=True, index=0, key="w_step_choice")
        wcol1, wcol2, wsp, wcol3, wcol4 = st.columns([1,1,2,1,1])
        with wcol1:
            if st.button("−", key="w_minus"):
                w_slider = round(max(30.0, w_slider - float(step_choice_w)), 1)
        with wcol2:
            if st.button("+", key="w_plus"):
                w_slider = round(min(200.0, w_slider + float(step_choice_w)), 1)
        with wcol3:
            if st.button("−5", key="w_minus5"):
                w_slider = round(max(30.0, w_slider - 5.0), 1)
        with wcol4:
            if st.button("+5", key="w_plus5"):
                w_slider = round(min(200.0, w_slider + 5.0), 1)

        # 最終値（直接入力可）
        st.session_state.weight_input = st.number_input(
            "最終値（直接入力可）", value=float(w_slider), step=0.1, format="%.1f"
        )

        if st.button("追加"):
            msg = add_weight_row(int(y), int(m), int(d), me, st.session_state.weight_input)
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
    code = st.text_input("ADNIN_CODE", type="password")  # ご指定どおりの表記
    if st.button("管理者モードに入る"):
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
        nu = nu_col1.text_input("new user_id（日本語OK）")
        npw = nu_col2.text_input("new password", type="password")
        nh  = nu_col3.text_input("height_cm（任意）")
        if st.button("ユーザー作成"):
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
