import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import bcrypt
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="体重トラッカー", page_icon="📈", layout="centered")

# ====== Secrets から読み込み ======
svc_json = st.secrets["GSPREAD_SERVICE_ACCOUNT_JSON"]   # ← StreamlitのSecretsに貼る
SPREADSHEET_URL = st.secrets["SPREADSHEET_URL"]
ADMIN_CODE = st.secrets.get("ADMIN_CODE", "admin123")

# ====== Google Sheets 認証 ======
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_dict(svc_json, scope)
gc = gspread.authorize(credentials)
sh = gc.open_by_url(SPREADSHEET_URL)
users_ws = sh.worksheet("users")
weights_ws = sh.worksheet("weights")

def normalize_uid(s: str) -> str:
    return str(s).replace("\u3000"," ").replace("\n"," ").replace("\r"," ").strip()

def df_weights():
    df = pd.DataFrame(weights_ws.get_all_records())
    if df.empty: return df
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
    u = pd.DataFrame(users_ws.get_all_records())
    if u.empty: return False
    user_id = normalize_uid(user_id)
    row = u[u["user_id"].map(normalize_uid) == user_id]
    if row.empty: return False
    hashed = str(row.iloc[0].get("password_hash",""))
    if not hashed: return False
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed.encode("utf-8"))

def create_user(user_id: str, plain_password: str):
    user_id = normalize_uid(user_id)
    if not user_id or not plain_password:
        return "user_id と password を入力してください。"
    u = pd.DataFrame(users_ws.get_all_records())
    if not u.empty and any(u["user_id"].map(normalize_uid) == user_id):
        return "その user_id は既に存在します。"
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    users_ws.append_row([user_id, hashed])
    return f"ユーザー {user_id} を作成しました。"

def add_weight_row(y: int, m: int, d: int, user_id: str, weight):
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

def plot_user(dfx: pd.DataFrame, user_id: str, period_key: str):
    dff = dfx[dfx["user_id"] == normalize_uid(user_id)].copy()
    dff = filter_period(dff, period_key)
    if dff.empty:
        st.info(f"{user_id}: {period_key} の範囲にデータなし")
        return
    fig, ax = plt.subplots(figsize=(6,3))
    ax.plot(dff["date"], dff["weight"], marker="o")
    # 目盛り
    if period_key in ("1か月", "3か月"):
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
        try:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m/%-d"))
        except:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    else:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=8))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m/%d"))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_title(f"{user_id} の体重推移（{period_key}）")
    ax.set_xlabel("日付"); ax.set_ylabel("体重(kg)")
    st.pyplot(fig)

st.title("📈 体重トラッカー")

# ログイン
st.subheader("ログイン")
uid = st.text_input("ユーザーID")
pw  = st.text_input("パスワード", type="password")
if "current_user" not in st.session_state:
    st.session_state.current_user = None

if st.button("ログイン"):
    if verify_user(uid, pw):
        st.session_state.current_user = normalize_uid(uid)
        st.success(f"ログイン成功：{st.session_state.current_user}")
    else:
        st.error("ログイン失敗")

if st.session_state.current_user:
    # 期間選択とグラフ
    st.subheader("グラフ表示")
    period = st.radio("表示期間", ["1か月","3か月","全期間"], horizontal=True)
    dfw = df_weights()
    if not dfw.empty:
        plot_user(dfw, st.session_state.current_user, period)

    # 今日デフォルトで記録追加
    st.subheader("記録を追加")
    today = date.today()
    col1, col2, col3, col4 = st.columns(4)
    y = col1.number_input("年", value=today.year, step=1)
    m = col2.number_input("月", value=today.month, step=1)
    d = col3.number_input("日", value=today.day, step=1)
    w = col4.number_input("体重(kg)", value=65.0, step=0.1)
    if st.button("追加"):
        msg = add_weight_row(int(y), int(m), int(d), st.session_state.current_user, w)
        st.info(msg)

# 管理者：ユーザー追加
st.divider()
st.subheader("（管理者）ユーザー追加")
code = st.text_input("合言葉（ADMIN_CODE）", type="password")
nu = st.text_input("新規 user_id（日本語OK）")
npw = st.text_input("新規 password", type="password")
if st.button("ユーザー作成"):
    if code != ADMIN_CODE:
        st.error("合言葉が違います")
    else:
        st.info(create_user(nu, npw))
