#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣科技股盤前分析 — Streamlit Web App
每日早上 8:00 自動執行：python3 -m streamlit run app.py
"""

import sys, os, json, time, warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# 把 widget.py 所在目錄加到 path
sys.path.insert(0, os.path.dirname(__file__))
from widget import (
    TECH_UNIVERSE, MY_HOLDINGS, CATALYST_MAP, CATALYST_BENEFICIARIES,
    fetch_cnyes_news, fetch_moneydj_news, fetch_twse_foreign_buying,
    fetch_twse_market_summary, fetch_prices_batch, analyze_catalysts,
    get_catalyst_labels, score_stock, analyze_holdings,
    calc_rsi, calc_macd, calc_atr, volume_ratio,
)

warnings.filterwarnings("ignore")

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="台灣科技股盤前分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main { background-color: #0e1117; }
  .metric-card {
    background: #1c2030; border: 1px solid #2d3250;
    border-radius: 10px; padding: 14px 18px; margin-bottom: 10px;
  }
  .up   { color: #00e676; font-weight: bold; }
  .down { color: #ff4444; font-weight: bold; }
  .flat { color: #aaaaaa; }
  .rank-badge {
    background: #1565c0; color: white;
    border-radius: 50%; width: 28px; height: 28px;
    display:inline-flex; align-items:center; justify-content:center;
    font-weight: bold; font-size: 13px; margin-right: 8px;
  }
  .news-item {
    border-left: 3px solid #1565c0; padding: 4px 10px;
    margin: 4px 0; background: #161b2e; border-radius: 0 6px 6px 0;
  }
  .supply-chip {
    display:inline-block; padding:2px 8px; border-radius:12px;
    font-size:11px; font-weight:bold; margin:2px;
  }
  .chip-nv  { background:#76b900; color:#000; }
  .chip-amd { background:#ed1c24; color:#fff; }
  .chip-apl { background:#555555; color:#fff; }
  .chip-ai  { background:#ff9800; color:#000; }
  .chip-cow { background:#00bcd4; color:#000; }
  .score-bar-wrap { background:#2a2a2a; border-radius:6px; height:10px; width:100%; }
  .score-bar { border-radius:6px; height:10px; }
  h1, h2, h3, h4 { color: #e0e0e0; }
  .stSelectbox label, .stSlider label { color: #b0b0b0; }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/stock-market.png", width=60)
    st.title("台灣科技股\n盤前分析系統")
    st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d  %H:%M')}")
    st.divider()

    top_n = st.slider("推薦股票數量", 3, 10, 5)
    min_score = st.slider("最低信心門檻", 30, 80, 45)
    show_charts = st.checkbox("顯示K線圖", value=True)
    show_all_stocks = st.checkbox("顯示全部股票評分", value=False)

    st.divider()
    if st.button("🔄  重新分析", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

    st.caption("資料來源：鉅亨網、MoneyDJ、TWSE、Yahoo Finance")
    st.caption("⚠ 僅供技術分析參考，非投資建議")

# ─── Cache Data Loading ──────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def load_all_data():
    all_tickers = list(TECH_UNIVERSE.keys())
    cnyes   = fetch_cnyes_news(60)
    moneydj = fetch_moneydj_news()
    all_news = cnyes + moneydj

    catalyst_scores, key_headlines = analyze_catalysts(all_news)
    foreign = fetch_twse_foreign_buying()
    market  = fetch_twse_market_summary()
    prices  = fetch_prices_batch(all_tickers, period="3mo")
    return {
        "news":       all_news,
        "headlines":  key_headlines,
        "catalyst":   catalyst_scores,
        "foreign":    foreign,
        "market":     market,
        "prices":     prices,
        "loaded_at":  datetime.now().strftime("%H:%M:%S"),
    }

# ─── Header ──────────────────────────────────────────────────────────────────
col_title, col_time = st.columns([4, 1])
with col_title:
    st.markdown("## 📊 台灣科技股盤前分析")
    st.caption("晶片・記憶體・AI　｜　NVIDIA / AMD / Apple 上游供應鏈深度追蹤")
with col_time:
    st.markdown(f"<br><p style='text-align:right;color:#888'>{datetime.now().strftime('%Y年%m月%d日  %H:%M')}</p>", unsafe_allow_html=True)

st.divider()

# ─── Load Data ───────────────────────────────────────────────────────────────
with st.spinner("📡 抓取新聞、外資籌碼與股價資料（首次載入約30秒）…"):
    data = load_all_data()

prices        = data["prices"]
all_news      = data["news"]
catalyst_scores = data["catalyst"]
foreign       = data["foreign"]

st.caption(f"✅ 資料更新時間：{data['loaded_at']}　｜　取得 {len(prices)} 支股票・{len(all_news)} 條新聞")

# ─── Market Summary ──────────────────────────────────────────────────────────
mkt = data["market"]
if mkt:
    st.subheader("📌 大盤概況")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("加權指數", mkt.get("index", "—"))
    mc2.metric("漲跌", mkt.get("change", "—"))
    mc3.metric("成交金額(億)", mkt.get("amount", "—"))
    mc4.metric("成交量(張)", mkt.get("volume", "—"))
    st.divider()

# ─── My Holdings ─────────────────────────────────────────────────────────────
st.subheader("💼 我的持股（零股）")
holdings_data = analyze_holdings(prices)

h_cols = st.columns(len(holdings_data))
for i, h in enumerate(holdings_data):
    with h_cols[i]:
        if h.get("error"):
            st.metric(label=f"{h['ticker'].replace('.TW','')} {h['name']}", value="—", delta="資料不足")
        else:
            delta = f"{h['chg']:+.2f}%"
            delta_color = "normal" if h["chg"] >= 0 else "inverse"
            # Streamlit's delta_color: "normal"=green for positive, "inverse"=green for negative
            st.metric(
                label=f"{h['ticker'].replace('.TW','')}  {h['name']}",
                value=f"NT${h['price']:.1f}",
                delta=delta,
            )
            st.caption(f"5日高 {h.get('wk_high',0):.1f}　低 {h.get('wk_low',0):.1f}")

# Holdings mini-charts
if show_charts:
    hc = st.columns(len(holdings_data))
    for i, h in enumerate(holdings_data):
        ticker = h["ticker"]
        df = prices.get(ticker)
        if df is not None and len(df) >= 10 and not h.get("error"):
            with hc[i]:
                recent = df.tail(30)
                color     = "#00e676" if h["chg"] >= 0 else "#ff4444"
                fill_rgba = "rgba(0,230,118,0.13)" if h["chg"] >= 0 else "rgba(255,68,68,0.13)"
                fig = go.Figure(go.Scatter(
                    x=recent.index, y=recent["Close"],
                    mode="lines", line=dict(color=color, width=2),
                    fill="tozeroy", fillcolor=fill_rgba,
                    hovertemplate="%{x|%m/%d}  %{y:.1f}<extra></extra>",
                ))
                fig.update_layout(
                    height=110, margin=dict(l=0,r=0,t=4,b=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(visible=False), yaxis=dict(visible=False),
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

st.divider()

# ─── News Headlines ──────────────────────────────────────────────────────────
st.subheader("📰 今日早盤新聞重點")
if data["headlines"]:
    for h in data["headlines"][:8]:
        # Color keywords in the headline
        display = h
        for cat, keywords in CATALYST_MAP.items():
            for kw in keywords:
                if kw in display:
                    display = display.replace(kw, f"**{kw}**")
                    break
        st.markdown(f'<div class="news-item">{display}</div>', unsafe_allow_html=True)
else:
    st.info("暫無最新新聞，請稍後重新整理")

# Show more news in expander
if len(all_news) > 8:
    with st.expander(f"查看更多新聞 ({len(all_news)} 條)"):
        df_news = pd.DataFrame(all_news)
        if not df_news.empty:
            for _, row in df_news.head(30).iterrows():
                st.caption(f"[{row.get('time','--')}] [{row.get('source','')}]  {row.get('title','')}")

st.divider()

# ─── Score All Stocks ─────────────────────────────────────────────────────────
holding_keys = set(MY_HOLDINGS.keys())
all_scored = []
for ticker in TECH_UNIVERSE:
    if ticker in holding_keys:
        continue
    df = prices.get(ticker)
    bonus = catalyst_scores.get(ticker, 0)
    fi    = foreign.get(ticker, 0)
    res   = score_stock(ticker, df, bonus, fi)
    if res and res.get("score", 0) >= min_score:
        res["catalysts"] = get_catalyst_labels(ticker, all_news)
        all_scored.append(res)

all_scored.sort(key=lambda x: x["score"], reverse=True)
top_picks = all_scored[:top_n]

# ─── Top Picks ───────────────────────────────────────────────────────────────
score_color = lambda s: "#00e676" if s >= 80 else ("#ff9800" if s >= 65 else "#ef5350")

st.subheader(f"🎯 今日精選 {top_n} 支潛力股（預估漲幅 5%～漲停）")

if not top_picks:
    st.warning("目前符合條件的股票不足，可降低最低信心門檻後重試")
else:
    for rank, p in enumerate(top_picks, 1):
        sc    = p["score"]
        color = score_color(sc)
        chg_c = "#00e676" if p["mom1d"] >= 0 else "#ff4444"

        with st.container():
            # ── Title row ────────────────────────────────────────────────────
            t_col, s_col = st.columns([7, 2])
            with t_col:
                supply_html = ""
                chip_map = {"NVIDIA":"chip-nv","AMD":"chip-amd","Apple":"chip-apl","AI":"chip-ai","CoWoS":"chip-cow"}
                for s in p.get("supply", []):
                    if s in chip_map:
                        supply_html += f'<span class="supply-chip {chip_map[s]}">{s}</span>'

                st.markdown(
                    f'<span class="rank-badge">{rank}</span>'
                    f'<b style="font-size:18px;color:#e0e0e0">'
                    f'{p["ticker"].replace(".TW","")}  {p["name"]}</b>'
                    f'  <span style="color:#888;font-size:14px">{p["en"]}</span>'
                    f'  <span style="color:#888;font-size:13px">[{p["sector"]}]</span>'
                    f'  {supply_html}',
                    unsafe_allow_html=True
                )
            with s_col:
                bar_w = int(sc)
                bar_color = color.lstrip("#")
                st.markdown(
                    f'<div style="text-align:right;color:{color};font-size:20px;font-weight:bold">'
                    f'{sc}/100</div>'
                    f'<div class="score-bar-wrap">'
                    f'<div class="score-bar" style="width:{bar_w}%;background:{color}"></div></div>',
                    unsafe_allow_html=True
                )

            # ── Metrics row ──────────────────────────────────────────────────
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("昨收", f"NT${p['last_price']:.1f}")
            m2.metric("昨漲跌", f"{p['mom1d']:+.2f}%")
            m3.metric("5日動能", f"{p['mom5d']:+.1f}%")
            m4.metric("量比", f"{p['vol_ratio']:.1f}x", delta="放量" if p["vol_ratio"] >= 1.5 else None)
            m5.metric("RSI(14)", f"{p['rsi']:.0f}")
            fi_v = p["foreign_net"]
            m6.metric("外資(千張)", f"{fi_v:+.0f}" if fi_v != 0 else "N/A")

            # ── Target row ───────────────────────────────────────────────────
            tg1, tg2, tg3 = st.columns(3)
            tg1.success(f"🎯 目標價　NT${p['target_price']:.1f}　(+{p['target_pct']:.0f}%)")
            tg2.error(  f"🛡 止損價　NT${p['stop_loss']:.1f}　({p['stop_pct']:.1f}%)")
            tg3.info(   f"⏰ 建議賣出　{p['sell_note']}")

            # ── Catalyst + score breakdown ────────────────────────────────────
            cat_labels = p.get("catalysts", [])
            cat_str = "、".join(cat_labels) if cat_labels else "技術面突破"
            breakdown = f"量能 {p['vol_score']} + 動能 {p['mom_score']} + 技術 {p['tech_score']} + 催化劑 {p['cat_score']}"

            st.markdown(
                f'<div style="color:#aaa;font-size:13px;padding:4px 0">'
                f'📌 <b>催化劑</b>：{cat_str}&nbsp;&nbsp;&nbsp;'
                f'📊 <b>評分細項</b>：{breakdown}</div>',
                unsafe_allow_html=True
            )

            # ── K-line chart ──────────────────────────────────────────────────
            if show_charts:
                df = prices.get(p["ticker"])
                if df is not None and len(df) >= 20:
                    recent = df.tail(60).copy()
                    recent["MA5"]  = recent["Close"].rolling(5).mean()
                    recent["MA20"] = recent["Close"].rolling(20).mean()

                    fig = make_subplots(
                        rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.7, 0.3], vertical_spacing=0.04
                    )
                    # Candlestick
                    fig.add_trace(go.Candlestick(
                        x=recent.index, open=recent["Open"], high=recent["High"],
                        low=recent["Low"], close=recent["Close"],
                        increasing_line_color="#00e676", decreasing_line_color="#ff4444",
                        name="K線",
                    ), row=1, col=1)
                    fig.add_trace(go.Scatter(x=recent.index, y=recent["MA5"],
                        line=dict(color="#ffd54f", width=1), name="MA5"), row=1, col=1)
                    fig.add_trace(go.Scatter(x=recent.index, y=recent["MA20"],
                        line=dict(color="#64b5f6", width=1), name="MA20"), row=1, col=1)
                    # Volume
                    vol_colors = [
                        "#00e676" if c >= o else "#ff4444"
                        for c, o in zip(recent["Close"], recent["Open"])
                    ]
                    fig.add_trace(go.Bar(
                        x=recent.index, y=recent["Volume"],
                        marker_color=vol_colors, opacity=0.7, name="量",
                    ), row=2, col=1)

                    fig.update_layout(
                        height=320, margin=dict(l=0,r=0,t=4,b=0),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0e1117",
                        xaxis_rangeslider_visible=False, showlegend=False,
                        font=dict(color="#888"),
                        xaxis2=dict(gridcolor="#1e2030"),
                        yaxis=dict(gridcolor="#1e2030"),
                        yaxis2=dict(gridcolor="#1e2030"),
                    )
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            st.divider()

# ─── Full Scores Table (optional) ────────────────────────────────────────────
if show_all_stocks and all_scored:
    st.subheader("📋 全部科技股評分一覽")
    df_scores = pd.DataFrame([{
        "代號":   r["ticker"].replace(".TW",""),
        "名稱":   r["name"],
        "類別":   r["sector"],
        "總分":   r["score"],
        "量比":   r["vol_ratio"],
        "昨漲%":  r["mom1d"],
        "5日%":   r["mom5d"],
        "RSI":    r["rsi"],
        "目標%":  r["target_pct"],
        "外資(千)":r["foreign_net"],
    } for r in all_scored])

    st.dataframe(
        df_scores.style.background_gradient(subset=["總分"], cmap="RdYlGn"),
        use_container_width=True, hide_index=True,
    )
    st.divider()

# ─── Supply Chain Reference ───────────────────────────────────────────────────
with st.expander("🗺  供應鏈地圖（NVIDIA / AMD / Apple）"):
    chains = {
        "🟢 NVIDIA": "台積電(CoWoS晶圓)・日月光(先進封裝)・欣興(IC載板)・緯穎(AI伺服器)・廣達(伺服器ODM)・台達電(電源散熱)・健鼎(PCB)・國巨(被動元件)",
        "🔴 AMD":    "台積電(晶圓)・日月光(封裝)・欣興(載板)・技嘉・華碩(主機板/顯卡)",
        "⬜ Apple":  "台積電(A/M系列晶片)・和碩/鴻海(組裝代工)・大立光/玉晶光(鏡頭)・可成(金屬機殼)・聯詠(顯示驅動IC)・義隆電(觸控)・廣達(MacBook)",
        "🟡 AI全鏈": "台積電・聯發科(AI晶片)・力旺(記憶體IP)・矽力(PMIC)・群聯(NAND控制器)・緯穎・廣達・台達電・研華(工業AI)",
    }
    for client, chain in chains.items():
        st.markdown(f"**{client}**")
        st.caption(chain)

# ─── Save JSON Report (use /tmp so it works on cloud too) ────────────────────
report_dir = "/tmp/taiwan_stock_reports"
os.makedirs(report_dir, exist_ok=True)
report_path = os.path.join(report_dir, f"{datetime.now().strftime('%Y%m%d_%H%M')}.json")
if not os.path.exists(report_path):
    report = {
        "date":     datetime.now().strftime("%Y-%m-%d %H:%M"),
        "top_picks": [{k: v for k, v in p.items() if k not in ("supply","catalysts")} for p in top_picks],
        "headlines": data["headlines"],
        "market":    mkt,
    }
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass
