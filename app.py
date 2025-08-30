# --- 管理者（Administrator） ---
st.divider()
st.subheader("Administrator")

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

if not st.session_state.is_admin:
    code = st.text_input("ADNIN_CODE", type="password")
    if st.button("管理者モードに入る"):
        if code == ADMIN_CODE:
            st.session_state.is_admin = True
            st.success("管理者モードに入りました。")
        else:
            st.error("合言葉が違います。")

if st.session_state.is_admin:
    # 🔽 タブの並びを変更
    tabs_admin = st.tabs(["個別データ", "全員のグラフ", "全員の最新情報", "ユーザー追加"])

    # 個別データ
    with tabs_admin[0]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        u = df_users()
        w = df_weights()
        user_list = sorted(u["user_id"].tolist()) if not u.empty else []
        if len(user_list) == 0:
            st.info("users シートにユーザーがいません。")
        else:
            colsel, colper = st.columns([2, 2])
            sel_uid = colsel.selectbox("ユーザーを選択", user_list, key="admin_pick_user")
            period_k = colper.radio("表示期間", ["1か月","3か月","全期間"], horizontal=True, key="admin_pick_period")

            # グラフ
            per_df = filter_period(w[w["user_id"] == sel_uid].sort_values("date"), period_k)
            if per_df.empty:
                st.info(f"{sel_uid} の {period_k} データがありません。")
            else:
                fig_u = px.line(
                    per_df, x="date", y="weight", markers=True,
                    title=f"{sel_uid} の体重推移（{period_k}）",
                    labels={"date":"日付","weight":"体重(kg)"}
                )
                fig_u.update_layout(margin=dict(l=8, r=8, t=48, b=8), font=dict(size=13))
                st.plotly_chart(fig_u, use_container_width=True,
                                config={"staticPlot": True, "displayModeBar": False})

            # 最新情報
            w_u_all = w[w["user_id"] == sel_uid].sort_values("date")
            if w_u_all.empty:
                st.info("最新情報：体重記録がありません。")
            else:
                last = w_u_all.iloc[-1]
                try:
                    h = u.set_index("user_id").get("height_cm").get(sel_uid, None)
                except KeyError:
                    h = None
                bmi_txt = calc_bmi(float(last["weight"]), h) if pd.notna(h) else "未設定"

                st.markdown("**最新情報**", unsafe_allow_html=True)
                # 🔽 metric のフォントサイズを小さくするCSS
                st.markdown("""
                <style>
                [data-testid="stMetricValue"] {
                    font-size: 0.8rem !important;
                }
                [data-testid="stMetricLabel"] {
                    font-size: 0.7rem !important;
                }
                </style>
                """, unsafe_allow_html=True)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("ユーザー", sel_uid)
                c2.metric("最新日", f"{last['date'].date()}")
                c3.metric("体重", f"{float(last['weight']):.1f} kg")
                c4.metric("BMI", bmi_txt)
        st.markdown('</div>', unsafe_allow_html=True)

    # 全員のグラフ
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
            st.plotly_chart(fig_all, use_container_width=True,
                            config={"staticPlot": True, "displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # 全員の最新情報
    with tabs_admin[2]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        u = df_users()
        w = df_weights()
        rows=[]
        for uid in u["user_id"]:
            w_u = w[w["user_id"] == uid].sort_values("date")
            if not w_u.empty:
                last_w = float(w_u.iloc[-1]["weight"])
                last_d = w_u.iloc[-1]["date"].date()
            else:
                last_w, last_d = None, None
            h = u.set_index("user_id").get("height_cm").get(uid, None)
            bmi = calc_bmi(last_w, h) if last_w is not None and pd.notna(h) else "未"
            rows.append([uid, last_d, f"{last_w:.1f}" if last_w is not None else "-", 
                         f"{h:.1f}" if pd.notna(h) else "-", bmi])
        df_latest = pd.DataFrame(rows, columns=["user", "最新日", "体重(kg)", "身長(cm)", "BMI"])
        st.dataframe(df_latest, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ユーザー追加
    with tabs_admin[3]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("新規ユーザーを作成します（身長は任意）")
        nu_col1, nu_col2, nu_col3 = st.columns(3)
        nu = nu_col1.text_input("new user_id（日本語OK）")
        npw = nu_col2.text_input("new password", type="password")
        nh  = nu_col3.text_input("height_cm（任意）")
        if st.button("ユーザー作成"):
            st.info(create_user(nu, npw, nh))
        st.markdown('</div>', unsafe_allow_html=True)
