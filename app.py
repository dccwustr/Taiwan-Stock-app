#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣科技股盤前分析 — Streamlit App (Minimalist)
"""

import sys, os, json, warnings
from datetime import datetime
from typing import Dict, List

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(__file__))
from widget import (
    TECH_UNIVERSE, MY_HOLDINGS,
    fetch_cnyes_news, fetch_moneydj_news, fetch_twse_foreign_buying,
    fetch_twse_market_summary, fetch_prices_batch, analyze_catalysts,
    get_catalyst_labels, score_stock, analyze_holdings, fetch_live_prices,
    analyze_holding_sell,
)

warnings.filterwarnings("ignore")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="台股分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Global */
  .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
  h1 { font-size: 1.4rem !important; font-weight: 700; color: #f0f0f0; }
  h2 { font-size: 1.1rem !important; font-weight: 600; color: #d0d0d0; }
  hr { border-color: #2a2a2a; margin: 0.6rem 0; }

  /* Stock card */
  .card {
    background: #161b2e;
    border: 1px solid #252d45;
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 14px;
  }
  .card-top {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 10px;
  }
  .rank {
    background: #1a56db; color: white;
    border-radius: 8px; width: 30px; height: 30px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 15px; flex-shrink: 0;
  }
  .stock-name { font-size: 18px; font-weight: 700; color: #f0f0f0; }
  .stock-sub  { font-size: 13px; color: #888; margin-left: 2px; }
  .sector-tag {
    background: #1e2740; color: #7eb3ff;
    border-radius: 6px; padding: 2px 8px; font-size: 12px;
  }
  .chip { border-radius: 5px; padding: 2px 7px; font-size: 11px; font-weight: 700; }
  .nv  { background:#76b900; color:#000; }
  .amd { background:#c0392b; color:#fff; }
  .apl { background:#555; color:#fff; }
  .ai  { background:#e67e22; color:#000; }
  .cow { background:#0097a7; color:#fff; }

  /* Prices row */
  .price-row { display: flex; gap: 16px; align-items: baseline; margin: 10px 0; flex-wrap: wrap; }
  .price-now { font-size: 20px; font-weight: 700; color: #e0e0e0; }
  .arrow { font-size: 18px; color: #555; }
  .price-target { font-size: 20px; font-weight: 700; color: #ef5350; }
  .pct-badge {
    background: #ef535022; color: #ef5350;
    border-radius: 6px; padding: 3px 10px; font-size: 14px; font-weight: 700;
  }
  .stop-row { font-size: 13px; color: #00c853; margin: 2px 0 6px 0; }

  /* Info row */
  .info-row { display: flex; flex-wrap: wrap; gap: 18px; margin: 8px 0; font-size: 13px; color: #aaa; }
  .info-val { color: #e0e0e0; font-weight: 600; }
  .up   { color: #ef5350 !important; }
  .down { color: #00c853 !important; }

  /* Catalyst */
  .catalyst {
    background: #0d1f3c; border-left: 3px solid #1a56db;
    border-radius: 0 8px 8px 0; padding: 8px 12px;
    font-size: 13px; color: #c0d4ff; margin: 8px 0;
  }
  .sell-note { font-size: 13px; color: #ffd54f; margin-top: 4px; }

  /* Confidence bar */
  .conf-wrap { background: #2a2a2a; border-radius: 4px; height: 6px; width: 100%; margin-top: 10px; }
  .conf-bar  { border-radius: 4px; height: 6px; }

  /* Sidebar holdings */
  .holding-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 4px; border-bottom: 1px solid #222;
  }
  .h-name { font-size: 14px; color: #ccc; }
  .h-val  { font-size: 14px; font-weight: 600; }

  /* Live price inside card */
  .live-in-card {
    display: flex; align-items: baseline; gap: 12px;
    flex-wrap: wrap; margin: 6px 0 10px 0;
    padding: 10px 14px; background: #0d1117;
    border-radius: 8px; border: 1px solid #1e2740;
  }
  .live-big      { font-size: 28px; font-weight: 800; }
  .live-chg-in   { font-size: 16px; font-weight: 700; }
  .live-vol      { font-size: 12px; color: #555; margin-left: auto; }
  .live-badge {
    font-size: 10px; font-weight: 700; padding: 2px 7px;
    border-radius: 4px; background: #ef535022; color: #ef5350;
    animation: pulse 2s infinite;
  }
  .closed-badge {
    font-size: 10px; padding: 2px 7px;
    border-radius: 4px; background: #22222255; color: #555;
  }
  .limit-up   { background:#ef5350; color:#fff; border-radius:4px; padding:2px 8px; font-size:12px; font-weight:700; }
  .limit-near { background:#e65100; color:#fff; border-radius:4px; padding:2px 8px; font-size:12px; font-weight:700; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

  /* News */
  .news-line {
    padding: 5px 0 5px 10px; border-left: 2px solid #1a56db;
    font-size: 13px; color: #bbb; margin-bottom: 6px; line-height: 1.4;
  }
  .news-time { color: #555; font-size: 11px; margin-right: 6px; }
</style>
""", unsafe_allow_html=True)

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def load_data():
    tickers  = list(TECH_UNIVERSE.keys())
    news     = fetch_cnyes_news(60) + fetch_moneydj_news()
    cat_sc, headlines = analyze_catalysts(news)
    foreign  = fetch_twse_foreign_buying()
    market   = fetch_twse_market_summary()
    prices   = fetch_prices_batch(tickers, period="3mo")
    return dict(news=news, headlines=headlines, catalyst=cat_sc,
                foreign=foreign, market=market, prices=prices,
                ts=datetime.now().strftime("%H:%M"))

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### 📈 台股分析")
    st.caption(f"{datetime.now().strftime('%Y-%m-%d  %H:%M')}")

    if st.button("🔄 重新整理", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # Settings
    top_n     = st.slider("推薦數量", 3, 8, 5)
    min_score = st.slider("最低評分門檻", 30, 75, 40)
    show_chart = st.checkbox("顯示K線圖", value=False)

    st.divider()

    # Holdings — load after data
    st.markdown("**💼 我的持股**")
    holdings_placeholder = st.empty()

    st.divider()
    st.caption("資料來源：鉅亨網・TWSE・Yahoo Finance")
    st.caption("⚠ 非投資建議，僅供參考")

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("載入中…"):
    data = load_data()

prices   = data["prices"]
all_news = data["news"]
cat_sc   = data["catalyst"]
foreign  = data["foreign"]
mkt      = data["market"]

# ── Fill holdings in sidebar ──────────────────────────────────────────────────
holdings_info = analyze_holdings(prices)
with holdings_placeholder:
    for h in holdings_info:
        ticker = h["ticker"]
        name   = h["name"]

        if h.get("error"):
            with st.expander(f"{ticker.replace('.TW','')} {name}"):
                st.caption("資料不足")
            continue

        chg   = h["chg"]
        color = "#ef5350" if chg >= 0 else "#00c853"
        arrow = "▲" if chg >= 0 else "▼"
        label = f"{ticker.replace('.TW','')} {name}　{arrow}{abs(chg):.2f}%"

        with st.expander(label):
            st.metric("現價", f"NT${h['price']:.1f}", f"{chg:+.2f}%")
            st.caption(f"5日高 {h.get('wk_high',0):.1f}　／　低 {h.get('wk_low',0):.1f}")
            st.divider()

            sell = analyze_holding_sell(prices.get(ticker))
            if sell:
                urgency_icon = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(sell["urgency"], "⚪")
                st.markdown(f"**{urgency_icon} {sell['action']}**")
                st.markdown(
                    f'<div style="margin:8px 0">'
                    f'<div style="color:#ef5350;font-size:13px">🎯 目標賣出　NT${sell["target_sell"]}　(+{sell["upside"]}%)</div>'
                    f'<div style="color:#00c853;font-size:13px;margin-top:4px">🛡 止損參考　NT${sell["stop_loss"]}　({sell["downside"]}%)</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                st.caption(f"RSI {sell['rsi']}　｜　MA20 {'✅' if sell['above_ma20'] else '⚠️'}　｜　MACD {'↑' if sell['macd_pos'] else '↓'}")
                st.divider()
                st.caption("分析依據：")
                for r in sell["reasons"]:
                    st.caption(f"• {r}")
            else:
                st.caption("資料不足，無法分析")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## 🎯 今日精選潛力股")
if mkt:
    idx_val = mkt.get("index", "—")
    idx_chg = mkt.get("change", "—")
    is_up   = not str(idx_chg).startswith("-")
    mkt_col = "#ef5350" if is_up else "#00c853"
    st.markdown(
        f'<span style="color:#888;font-size:13px">加權指數　</span>'
        f'<span style="font-size:16px;font-weight:700;color:#f0f0f0">{idx_val}</span>'
        f'　<span style="color:{mkt_col};font-size:14px">{idx_chg}</span>'
        f'　<span style="color:#555;font-size:12px">｜　更新 {data["ts"]}　｜　漲停 ±10%</span>',
        unsafe_allow_html=True
    )
else:
    st.caption(f"資料更新：{data['ts']}　｜　台股漲停 ±10%")

st.divider()

# ── Score stocks ──────────────────────────────────────────────────────────────
skip = set(MY_HOLDINGS.keys())
scored = []
for ticker in TECH_UNIVERSE:
    if ticker in skip:
        continue
    res = score_stock(ticker, prices.get(ticker), cat_sc.get(ticker, 0), foreign.get(ticker, 0))
    if res and res["score"] >= min_score:
        res["catalysts"] = get_catalyst_labels(ticker, all_news)
        scored.append(res)
scored.sort(key=lambda x: x["score"], reverse=True)
picks = scored[:top_n]

# ── Chip helper ───────────────────────────────────────────────────────────────
CHIP_CSS = {"NVIDIA":"nv","AMD":"amd","Apple":"apl","AI":"ai","CoWoS":"cow"}
def supply_chips(supply):
    return " ".join(
        f'<span class="chip {CHIP_CSS[s]}">{s}</span>'
        for s in supply if s in CHIP_CSS
    )

def conf_color(s):
    return "#00c853" if s >= 80 else ("#ffd54f" if s >= 60 else "#ef5350")

# ── Stock cards with embedded live prices (30s auto-refresh) ─────────────────
from datetime import timezone, timedelta as _td

def _is_market_open() -> bool:
    tw = datetime.now(tz=timezone(_td(hours=8)))
    return tw.weekday() < 5 and (
        (tw.hour == 9) or (10 <= tw.hour <= 12) or
        (tw.hour == 13 and tw.minute <= 30)
    )

@st.fragment(run_every="30s" if _is_market_open() else None)
def render_stock_cards(picks, prices, show_chart):
    tickers  = [p["ticker"] for p in picks]
    live     = fetch_live_prices(tickers)
    is_open  = _is_market_open()
    refresh  = "每30秒自動更新 ●" if is_open else "非交易時段"
    st.caption(f"📡 即時股價　{refresh}　　更新：{datetime.now().strftime('%H:%M:%S')}")

    for rank, p in enumerate(picks, 1):
        sc      = p["score"]
        bar_color = conf_color(sc)
        vr      = p["vol_ratio"]
        fi      = p["foreign_net"]
        cats    = p.get("catalysts") or ["技術面突破"]
        cat_str = "　".join(cats)

        if sc >= 88:  sell = "⏰ 當日收盤前（留意漲停）"
        elif sc >= 72: sell = "⏰ 達 5–7% 即可分批出場"
        else:          sell = "⏰ T+1 早盤高點賣出"

        if fi > 100:    fi_str = f"外資買超 {fi:.0f}千張 📥"
        elif fi < -100: fi_str = f"外資賣超 {abs(fi):.0f}千張 📤"
        else:           fi_str = ""

        info_parts = [
            f'量比 <span class="info-val {"up" if vr>=1.5 else ""}">{vr:.1f}x</span>',
            f'RSI <span class="info-val">{p["rsi"]:.0f}</span>',
            f'5日 <span class="info-val {"up" if p["mom5d"]>=0 else "down"}">{p["mom5d"]:+.1f}%</span>',
        ]
        if fi_str:
            info_parts.append(f'<span class="{"up" if fi>0 else "down"}">{fi_str}</span>')

        # ── Live price block ──────────────────────────────────────────────────
        d = live.get(p["ticker"])
        if d and d["price"] > 0:
            lp      = d["price"]
            chg     = d["chg"]
            chg_pct = d["chg_pct"]
            lu      = d["limit_up"]
            vol     = d["volume"]
            upd     = d["time"] or "--:--"
            up      = chg >= 0
            lc      = "#ef5350" if up else "#00c853"
            arrow   = "▲" if up else "▼"

            is_limit   = lu > 0 and abs(lp - lu) < 0.02
            near_limit = lu > 0 and chg_pct >= 8 and not is_limit
            status_tag = ""
            if is_limit:    status_tag = '<span class="limit-up">漲停🔥</span>'
            elif near_limit:status_tag = '<span class="limit-near">近漲停⚡</span>'

            live_badge = ('<span class="live-badge">● LIVE</span>' if is_open and d["live"]
                         else '<span class="closed-badge">收盤價</span>')

            live_block = f"""
  <div class="live-in-card">
    <span class="live-big" style="color:{lc}">{lp:.1f}</span>
    <span class="live-chg-in" style="color:{lc}">{arrow} {abs(chg):.1f} ({abs(chg_pct):.2f}%)</span>
    {status_tag}
    {live_badge}
    <span class="live-vol">{vol:,}千股　{upd}</span>
  </div>"""
        else:
            live_block = '<div class="live-in-card"><span style="color:#555">等待開盤資料…</span></div>'

        bar_w = int(sc)
        st.markdown(f"""
<div class="card">
  <div class="card-top">
    <div class="rank">{rank}</div>
    <span class="stock-name">{p['ticker'].replace('.TW','')} {p['name']}</span>
    <span class="stock-sub">{p['en']}</span>
  </div>

  {live_block}

  <div class="price-row">
    <span class="arrow">目標</span>
    <span class="price-target">NT${p['target_price']:.1f}</span>
    <span class="pct-badge">+{p['target_pct']:.0f}%</span>
  </div>
  <div class="stop-row">💰 建議買入 NT${p['last_price']:.1f}　　🛡 止損 NT${p['stop_loss']:.1f}　({p['stop_pct']:.1f}%)</div>

  <div class="info-row">{'　'.join(f'<span>{x}</span>' for x in info_parts)}</div>

  <div class="catalyst">📌 {cat_str}</div>
  <div class="sell-note">{sell}</div>

  <div class="conf-wrap">
    <div class="conf-bar" style="width:{bar_w}%;background:{bar_color}"></div>
  </div>
  <div style="font-size:11px;color:#555;margin-top:3px">信心指數 {sc}/100</div>
</div>
""", unsafe_allow_html=True)

        if show_chart:
            df = prices.get(p["ticker"])
            if df is not None and len(df) >= 20:
                recent = df.tail(60).copy()
                recent["MA5"]  = recent["Close"].rolling(5).mean()
                recent["MA20"] = recent["Close"].rolling(20).mean()
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                    row_heights=[0.72, 0.28], vertical_spacing=0.03)
                fig.add_trace(go.Candlestick(
                    x=recent.index, open=recent["Open"], high=recent["High"],
                    low=recent["Low"], close=recent["Close"],
                    increasing_line_color="#ef5350", decreasing_line_color="#00c853",
                    name="K線"), row=1, col=1)
                fig.add_trace(go.Scatter(x=recent.index, y=recent["MA5"],
                    line=dict(color="#ffd54f", width=1.2), name="MA5"), row=1, col=1)
                fig.add_trace(go.Scatter(x=recent.index, y=recent["MA20"],
                    line=dict(color="#4fc3f7", width=1.2), name="MA20"), row=1, col=1)
                vol_colors = ["#ef5350" if c >= o else "#00c853"
                              for c, o in zip(recent["Close"], recent["Open"])]
                fig.add_trace(go.Bar(x=recent.index, y=recent["Volume"],
                    marker_color=vol_colors, opacity=0.6, name="量"), row=2, col=1)
                fig.update_layout(
                    height=280, margin=dict(l=0, r=0, t=0, b=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0e1117",
                    xaxis_rangeslider_visible=False, showlegend=False,
                    font=dict(color="#666", size=11),
                    xaxis2=dict(gridcolor="#1a1a2e"),
                    yaxis=dict(gridcolor="#1a1a2e"),
                    yaxis2=dict(gridcolor="#1a1a2e"),
                )
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

if not picks:
    st.warning("目前無符合條件的股票，請降低評分門檻後重試。")
else:
    render_stock_cards(picks, prices, show_chart)

# ── 備選股 toggle ─────────────────────────────────────────────────────────────
backups = scored[top_n:top_n + 5]
if backups:
    if "show_backups" not in st.session_state:
        st.session_state.show_backups = False

    label = "▲ 收起備選股" if st.session_state.show_backups else "＋ 查看備選股（第 6–10 名）"
    if st.button(label, use_container_width=True):
        st.session_state.show_backups = not st.session_state.show_backups
        st.rerun()

    if st.session_state.show_backups:
        st.caption("備選股為今日評分第 6–10 名，信心指數相對較低，建議謹慎操作")
        render_stock_cards(backups, prices, show_chart)

# ── News (collapsed by default) ───────────────────────────────────────────────
st.divider()
with st.expander("📰 今日早盤新聞", expanded=False):
    headlines = data["headlines"]
    if headlines:
        for h in headlines[:10]:
            st.markdown(f'<div class="news-line">{h}</div>', unsafe_allow_html=True)
    else:
        st.caption("暫無最新新聞")
    if len(all_news) > 10:
        st.caption(f"共 {len(all_news)} 條新聞已掃描")

# ── Supply chain (collapsed) ──────────────────────────────────────────────────
with st.expander("🗺 供應鏈參考", expanded=False):
    data_sc = {
        "NVIDIA":  "台積電(CoWoS)・日月光(封裝)・欣興(載板)・緯穎(AI伺服器)・廣達(ODM)・台達電(電源)・健鼎(PCB)・國巨(被動元件)",
        "AMD":     "台積電(晶圓)・日月光(封裝)・欣興(載板)・技嘉・華碩(主機板)",
        "Apple":   "台積電(A/M晶片)・和碩/鴻海(組裝)・大立光/玉晶光(鏡頭)・可成(機殼)・聯詠(驅動IC)・廣達(Mac)",
        "AI 全鏈": "台積電・聯發科・力旺(IP)・矽力(PMIC)・群聯(NAND)・緯穎・廣達・台達電",
    }
    for k, v in data_sc.items():
        st.markdown(f"**{k}**")
        st.caption(v)
