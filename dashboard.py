"""
Smart DCA Dashboard — with Auth + Secrets
==========================================
รัน: streamlit run dashboard.py
"""

import streamlit as st

# ① Auth — ต้องเรียกก่อนทุกอย่าง
from auth import require_auth, logout
require_auth()

# ② imports หลัก (โหลดหลัง login เท่านั้น)
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from score_engine import SmartDCAScorer, DCAConfig
from backtest import SmartDCABacktester, BacktestConfig

# ==================== Page Config ====================

st.set_page_config(
    page_title="Smart DCA — S&P 500",
    page_icon="📈",
    layout="wide",
)

# ==================== Helper: ดึง API key จาก secrets ====================

def get_secret(section: str, key: str, default: str = "") -> str:
    """ดึงค่าจาก secrets.toml อย่างปลอดภัย — ถ้าไม่มีคืน default"""
    try:
        return st.secrets[section][key]
    except Exception:
        return default


# ==================== Sidebar ====================

with st.sidebar:
    st.header("⚙️ ตั้งค่า")

    ticker = st.text_input("Ticker", value="AAPL").upper().strip()

    st.subheader("DCA Config")
    monthly_budget   = st.number_input("เงินลงทุน/เดือน ($)", value=500, step=100)
    rsi_oversold     = st.slider("RSI Oversold threshold", 15, 40, 30)
    rsi_overbought   = st.slider("RSI Overbought threshold", 60, 85, 70)
    trailing_stop    = st.slider("Trailing Stop %", 3, 20, 8)
    buy_heavy_mult   = st.slider("BUY_HEAVY multiplier", 1.0, 3.0, 2.0, 0.5)

    st.subheader("Backtest")
    bt_start = st.selectbox("ช่วงเวลา", ["2020", "2021", "2022", "2023"], index=1)

    run_btn = st.button("🔍 วิเคราะห์", use_container_width=True, type="primary")

    st.divider()

    # แสดง API key status
    av_key   = get_secret("api_keys", "alpha_vantage")
    poly_key = get_secret("api_keys", "polygon_io")
    st.caption("API Keys")
    st.markdown(
        f"Alpha Vantage: {'✅' if av_key else '⬜ ไม่ได้ตั้ง'}  \n"
        f"Polygon.io: {'✅' if poly_key else '⬜ ไม่ได้ตั้ง'}"
    )

    st.divider()
    logout()  # ปุ่ม logout

# ==================== Helper: Colors ====================

ACTION_COLORS = {
    "BUY_HEAVY":     "#1D9E75",
    "BUY_NORMAL":    "#5DCAA5",
    "WAIT":          "#EF9F27",
    "SKIP":          "#888780",
    "SELL_PARTIAL":  "#F09595",
    "SELL_HEAVY":    "#E24B4A",
    "TRAILING_STOP": "#A32D2D",
}
ACTION_TH = {
    "BUY_HEAVY":     "ซื้อเพิ่ม 2x",
    "BUY_NORMAL":    "ซื้อปกติ",
    "WAIT":          "รอก่อน",
    "SKIP":          "ข้ามเดือนนี้",
    "SELL_PARTIAL":  "ขายบางส่วน",
    "SELL_HEAVY":    "ขายมาก",
    "TRAILING_STOP": "Trailing Stop",
}

# ==================== Main ====================

st.title("📈 Smart DCA Analyzer — S&P 500")
st.caption("วิเคราะห์จังหวะซื้อ/ขายด้วย Composite Score | yfinance + pandas-ta")

if run_btn or ticker:

    config = DCAConfig(
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
        trailing_stop=trailing_stop / 100,
    )
    bt_config = BacktestConfig(
        monthly_budget=monthly_budget,
        buy_heavy_mult=buy_heavy_mult,
        trailing_stop=trailing_stop / 100,
    )

    scorer     = SmartDCAScorer(config)
    backtester = SmartDCABacktester(scorer, bt_config)

    with st.spinner(f"กำลังดึงข้อมูล {ticker}..."):
        try:
            analysis  = scorer.analyze(ticker, period="2y")
            bt_result = backtester.run(ticker, start_date=f"{bt_start}-01-01")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")
            st.stop()

    # -------- Current Signal --------
    action    = analysis["action"]
    score     = analysis["score_composite"]
    color     = ACTION_COLORS.get(action, "#888")
    action_th = ACTION_TH.get(action, action)

    st.divider()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("ราคาปัจจุบัน", f"${analysis['price']:,.2f}")
    col2.metric("RSI (14)",      f"{analysis['rsi']:.1f}")
    col3.metric("Score รวม",     f"{score:.2f} / 10")
    col4.metric("MA 200",        f"${analysis['ma200']:,.2f}")

    with col5:
        st.markdown(
            f"""<div style='background:{color}22;border:1.5px solid {color};
                 border-radius:10px;padding:10px 14px;text-align:center;'>
              <div style='font-size:11px;color:{color};font-weight:500;'>คำแนะนำ</div>
              <div style='font-size:18px;font-weight:600;color:{color};'>{action_th}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # -------- Score Breakdown --------
    st.subheader("📊 Score Breakdown")
    score_df = pd.DataFrame({
        "indicator": ["RSI", "MA", "MACD", "Volume", "BB"],
        "score":     [analysis["score_rsi"], analysis["score_ma"],
                      analysis["score_macd"], analysis["score_volume"], analysis["score_bb"]],
    })
    fig_score = px.bar(
        score_df, x="indicator", y="score",
        color="score",
        color_continuous_scale=["#E24B4A", "#EF9F27", "#1D9E75"],
        range_color=[0, 10], height=250,
    )
    fig_score.update_layout(margin=dict(t=10, b=10), coloraxis_showscale=False)
    fig_score.add_hline(y=6, line_dash="dash", line_color="#888",
                        annotation_text="buy threshold")
    st.plotly_chart(fig_score, use_container_width=True)

    # -------- Price Chart --------
    df = analysis["df"].dropna(subset=["RSI"])
    st.subheader("📉 Price Chart + Indicators")
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.25, 0.20], vertical_spacing=0.04,
        subplot_titles=("ราคา + MA", "RSI (14)", "MACD"),
    )
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="Price",
        increasing_line_color="#1D9E75", decreasing_line_color="#E24B4A",
    ), row=1, col=1)
    for col_name, color_val in [("MA50", "#378ADD"), ("MA200", "#EF9F27")]:
        fig.add_trace(go.Scatter(x=df.index, y=df[col_name], name=col_name,
                                 line=dict(color=color_val, width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI",
                             line=dict(color="#7F77DD", width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#E24B4A", line_width=1, row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#1D9E75", line_width=1, row=2, col=1)
    colors_hist = ["#1D9E75" if v >= 0 else "#E24B4A" for v in df["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"], name="Histogram",
                         marker_color=colors_hist, opacity=0.7), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD"],        name="MACD",
                             line=dict(color="#378ADD", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df["MACD_Signal"], name="Signal",
                             line=dict(color="#EF9F27", width=1.5)), row=3, col=1)
    fig.update_layout(height=600, xaxis_rangeslider_visible=False,
                      showlegend=True, margin=dict(t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # -------- Backtest --------
    st.subheader(f"🔄 Backtest: {bt_start}–ปัจจุบัน")
    bcol1, bcol2, bcol3 = st.columns(3)
    for col, key, label in [
        (bcol1, "smart_dca",    "Smart DCA"),
        (bcol2, "naive_dca",    "Naive DCA"),
        (bcol3, "buy_and_hold", "Buy & Hold"),
    ]:
        r = bt_result[key]
        col.metric(label, f"${r['final_value']:,.0f}",
                   f"{r['total_return_pct']:+.1f}%",
                   help=f"ลงทุนรวม ${r['cash_invested']:,.0f}")

    if not bt_result["trades_df"].empty:
        tdf = bt_result["trades_df"].copy()
        tdf["date"]      = pd.to_datetime(tdf["date"]).dt.strftime("%Y-%m-%d")
        tdf["action_th"] = tdf["action"].map(ACTION_TH)
        tdf["price"]     = tdf["price"].round(2)
        tdf["score"]     = tdf["score"].round(2)
        with st.expander(f"📋 Trade Log ({len(tdf)} รายการ)"):
            cols = ["date", "action_th", "price", "score"]
            if "amount_invested" in tdf.columns:
                cols.append("amount_invested")
            st.dataframe(
                tdf[cols].rename(columns={
                    "date": "วันที่", "action_th": "Action",
                    "price": "ราคา ($)", "score": "Score",
                    "amount_invested": "ลงทุน ($)",
                }),
                use_container_width=True, hide_index=True,
            )

    st.caption("⚠️ ผลการทดสอบย้อนหลังไม่ได้รับประกันผลในอนาคต "
               "ใช้เป็นข้อมูลประกอบการตัดสินใจเท่านั้น")
