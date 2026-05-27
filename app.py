#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣科技股盤前分析 — Streamlit App (Minimalist)
"""

import sys, os, json, warnings
from datetime import datetime, timezone, timedelta
from typing import Dict, List

_TW = timezone(timedelta(hours=8))
def _now_tw(): return datetime.now(tz=_TW)

def _trading_epoch() -> str:
    """Returns the trading-date string this session belongs to.
    Changes at 08:00 TWN each weekday — Streamlit uses this as a cache key,
    so load_data() re-runs exactly once per trading morning on first visit.
    Before 08:00 TWN, or on weekends, rolls back to the last valid trading day.
    """
    tw = _now_tw()
    if tw.hour < 8:
        tw -= timedelta(days=1)
    while tw.weekday() >= 5:   # Sat=5, Sun=6
        tw -= timedelta(days=1)
    return tw.strftime("%Y-%m-%d")

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(__file__))
from widget import (
    TECH_UNIVERSE, MY_HOLDINGS,
    fetch_cnyes_news, fetch_moneydj_news, fetch_twse_foreign_buying,
    fetch_twse_market_summary, fetch_prices_batch, analyze_catalysts,
    get_catalyst_labels, score_stock, analyze_holdings, fetch_live_prices,
    analyze_holding_sell, get_beginner_advice,
    calc_rsi, calc_live_rsi, _TW_STOCK_NAMES,
    fetch_us_overnight, us_macro_stock_bonus, fetch_global_news,
)

warnings.filterwarnings("ignore")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="台股全產業分析",
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

  /* ── Compact sidebar ──────────────────────────────────────────────────────── */
  section[data-testid="stSidebar"] > div:first-child { padding-top: 0.5rem !important; }
  section[data-testid="stSidebar"] button {
    padding-top: 0.2rem !important; padding-bottom: 0.2rem !important;
    min-height: 1.6rem !important; font-size: 0.78rem !important; line-height: 1.2 !important;
  }
  section[data-testid="stSidebar"] .stElementContainer,
  section[data-testid="stSidebar"] [class*="element-container"] {
    margin-bottom: 0.15rem !important; margin-top: 0 !important;
  }
  section[data-testid="stSidebar"] hr { margin-top: 0.35rem !important; margin-bottom: 0.35rem !important; }
  section[data-testid="stSidebar"] [data-testid="stSlider"] { padding-top: 0.1rem !important; padding-bottom: 0.1rem !important; }
  section[data-testid="stSidebar"] label { font-size: 0.78rem !important; }
  section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
  section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { font-size: 0.75rem !important; margin-bottom: 0 !important; }
  section[data-testid="stSidebar"] h4 { font-size: 1rem !important; margin-bottom: 0 !important; }
  section[data-testid="stSidebar"] input { padding: 0.2rem 0.4rem !important; font-size: 0.78rem !important; }

  /* Star overlay buttons: invisible — card's ★/☆ symbol is the only visual */
  div[data-testid="stHorizontalBlock"]:has(.star-sentinel) button,
  div[data-testid="stHorizontalBlock"]:has(.star-sentinel) button:hover,
  div[data-testid="stHorizontalBlock"]:has(.star-sentinel) button:focus,
  div[data-testid="stHorizontalBlock"]:has(.star-sentinel) button:active {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
  }

  /* Minimalist top refresh button */
  div[data-testid="stHorizontalBlock"]:has(.refresh-sentinel) button {
    background: transparent !important;
    border: 1px solid #2a2a2a !important;
    color: #555 !important;
    font-size: 1rem !important;
    padding: 0.1rem 0.3rem !important;
    min-height: 1.8rem !important;
    box-shadow: none !important;
  }
  div[data-testid="stHorizontalBlock"]:has(.refresh-sentinel) button:hover {
    color: #bbb !important;
    border-color: #555 !important;
  }

  /* Beginner advice panel */
  .advice-box {
    background: #0a1628;
    border: 1px solid #1e3a5c;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 10px 0 4px 0;
  }
  .advice-title {
    font-size: 13px; font-weight: 700; color: #7eb3ff;
    letter-spacing: 0.5px; margin-bottom: 10px;
  }
  .advice-row {
    display: flex; align-items: flex-start; gap: 8px;
    margin-bottom: 8px; font-size: 13px;
  }
  .advice-label {
    color: #666; white-space: nowrap; min-width: 56px;
  }
  .advice-val { color: #e0e0e0; font-weight: 600; }
  .advice-note { color: #aaa; font-size: 12px; margin-top: 2px; }
  .rsi-big {
    font-size: 22px; font-weight: 800; line-height: 1;
  }
  .rsi-bar-wrap {
    background: #1a1a2e; border-radius: 4px; height: 8px;
    width: 100%; margin: 6px 0 2px;
    position: relative;
  }
  .rsi-bar-fill { border-radius: 4px; height: 8px; }
  .rsi-zones {
    display: flex; justify-content: space-between;
    font-size: 10px; color: #444; margin-top: 2px;
  }
  .entry-signal {
    font-size: 13px; font-weight: 700; padding: 6px 10px;
    border-radius: 8px; margin-top: 6px; text-align: center;
  }

  /* News */
  .news-line {
    padding: 5px 0 5px 10px; border-left: 2px solid #1a56db;
    font-size: 13px; color: #bbb; margin-bottom: 6px; line-height: 1.4;
  }
  .news-time { color: #555; font-size: 11px; margin-right: 6px; }
</style>
""", unsafe_allow_html=True)

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=28800, show_spinner=False)   # 8-hour TTL; epoch param busts cache each trading morning
def load_data(epoch: str):                       # epoch = "YYYY-MM-DD", changes at 08:00 TWN each weekday
    tickers  = list(TECH_UNIVERSE.keys())
    news     = fetch_cnyes_news(100) + fetch_moneydj_news()   # 100 items per category, 24h window
    cat_sc, headlines = analyze_catalysts(news)
    foreign  = fetch_twse_foreign_buying()
    market   = fetch_twse_market_summary()
    prices   = fetch_prices_batch(tickers, period="3mo")
    us_data  = fetch_us_overnight()              # US overnight macro (SOX, Nasdaq, VIX…)
    g_news   = fetch_global_news()               # international headlines filtered for TW tech
    ts = _now_tw().strftime("%H:%M")
    return dict(news=news, headlines=headlines, catalyst=cat_sc,
                foreign=foreign, market=market, prices=prices,
                us_data=us_data, global_news=g_news, ts=ts)

# ── Session state init ────────────────────────────────────────────────────────
if "view_mode"        not in st.session_state: st.session_state.view_mode        = "picks"
# valid modes: "picks" | "holdings" | "watchlist" | "search" | "monitor"
if "custom_holdings"  not in st.session_state: st.session_state.custom_holdings  = {}
if "hidden_holdings"  not in st.session_state: st.session_state.hidden_holdings  = set()
if "search_ticker"    not in st.session_state: st.session_state.search_ticker    = None
if "watchlist"        not in st.session_state: st.session_state.watchlist        = []
if "recent_searches"  not in st.session_state: st.session_state.recent_searches  = []
if "_close_sidebar"   not in st.session_state: st.session_state._close_sidebar   = False
if "rsi_thresholds"   not in st.session_state: st.session_state.rsi_thresholds   = {}
# rsi_thresholds: {ticker: {"target": float, "direction": "below"|"above"}}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### 📈 台股分析")
    st.caption(_now_tw().strftime('%Y-%m-%d  %H:%M'))

    st.divider()

    # Search input + Go
    qc1, qc2 = st.columns([3, 1])
    query_input = qc1.text_input("q", placeholder="查詢代號，如 2454",
                                  label_visibility="collapsed", key="query_input")
    if qc2.button("Go", use_container_width=True):
        raw = query_input.strip().upper()
        if raw:
            ticker = raw + ".TW" if not raw.endswith(".TW") else raw
            st.session_state.search_ticker = ticker
            rs = [t for t in st.session_state.recent_searches if t != ticker]
            st.session_state.recent_searches = ([ticker] + rs)[:10]
            st.session_state.view_mode = "search"
            st.session_state._close_sidebar = True

    _vm_search_active = st.session_state.view_mode == "search"
    if st.button("搜尋記錄  ✓" if _vm_search_active else "搜尋記錄",
                 use_container_width=True,
                 type="primary" if _vm_search_active else "secondary",
                 key="nav_search_inline"):
        st.session_state.view_mode = "search"
        st.session_state._close_sidebar = True
        st.rerun()

    st.divider()

    # Nav: 4 buttons in one row
    _n_mon = len(st.session_state.rsi_thresholds)
    _mon_lbl = f"📡{_n_mon}" if _n_mon else "📡"
    vm = st.session_state.view_mode
    _nc1, _nc2, _nc3, _nc4 = st.columns(4)
    for _col, (_vk, _vl) in zip([_nc1, _nc2, _nc3, _nc4], [
        ("picks", "精選"), ("holdings", "持股"), ("watchlist", "追蹤"), ("monitor", _mon_lbl),
    ]):
        _active = vm == _vk
        if _col.button(_vl + (" ✓" if _active else ""), key=f"nav_{_vk}",
                       type="primary" if _active else "secondary", use_container_width=True):
            st.session_state.view_mode = _vk
            st.session_state._close_sidebar = True
            st.rerun()

    sidebar_content = st.container()

    st.divider()
    top_n     = st.slider("推薦數量", 3, 8, 5)
    min_score = st.slider("最低評分門檻", 30, 75, 40)
    show_chart = st.checkbox("顯示K線圖", value=False)
    st.divider()
    st.caption("資料來源：鉅亨網・TWSE・Yahoo Finance")
    st.caption("⚠ 非投資建議，僅供參考")

# ── Auto-close sidebar on mobile ──────────────────────────────────────────────
if st.session_state.get("_close_sidebar"):
    st.session_state._close_sidebar = False
    # components.v1.html iframe uses srcdoc with allow-same-origin, so
    # window.parent.document is accessible — no CSP restriction.
    components.html("""
<script>
(function(){
  var d = window.parent.document;

  function isSidebarOpen(){
    var sb = d.querySelector('section[data-testid="stSidebar"]');
    if(!sb) return false;
    return sb.getBoundingClientRect().width > 50;
  }

  function tryClose(){
    if(!isSidebarOpen()) return;
    // 1. Mobile backdrop overlay
    var backdrop = d.querySelector('[data-testid="stSidebarBackdrop"]');
    if(backdrop){ backdrop.click(); return; }
    // 2. Any button in sidebar NOT inside user content area
    var sb = d.querySelector('section[data-testid="stSidebar"]');
    var uc = d.querySelector('[data-testid="stSidebarUserContent"]');
    if(sb && uc){
      var btns = sb.querySelectorAll('button');
      for(var i=0;i<btns.length;i++){
        if(!uc.contains(btns[i])){ btns[i].click(); return; }
      }
    }
    // 3. Named collapse selectors
    var sels = [
      '[data-testid="stSidebarCollapseButton"] button',
      '[data-testid="stSidebarCollapseButton"]',
      '[data-testid="stSidebarHeader"] button',
      'button[aria-label="Close sidebar"]'
    ];
    for(var j=0;j<sels.length;j++){
      var b = d.querySelector(sels[j]);
      if(b){ b.click(); return; }
    }
    // 4. Last resort: mousedown on main content
    var main = d.querySelector('[data-testid="stAppViewContainer"] > section:not([data-testid="stSidebar"])');
    if(main){ main.dispatchEvent(new MouseEvent('mousedown',{bubbles:true})); }
  }

  tryClose();
  setTimeout(tryClose, 300);
  setTimeout(tryClose, 700);
  setTimeout(tryClose, 1500);
})();
</script>
""", height=0)

# ── Load data ─────────────────────────────────────────────────────────────────
_epoch = _trading_epoch()
with st.spinner("載入中…"):
    data = load_data(_epoch)

prices      = data["prices"]
all_news    = data["news"]
cat_sc      = data["catalyst"]
foreign     = data["foreign"]
mkt         = data["market"]
us_data     = data.get("us_data", {})
global_news = data.get("global_news", [])

# ── Prepare search + watchlist + recent-search data ──────────────────────────
_sticker       = st.session_state.get("search_ticker")
_recent        = st.session_state.recent_searches        # list[ticker], max 10
_all_extra     = list(dict.fromkeys(                     # deduplicated, order preserved
    ([_sticker] if _sticker else []) + _recent + st.session_state.watchlist
))

# Pre-fetch prices for anything not already loaded
_need = [t for t in _all_extra if t and t not in prices]
if _need:
    prices.update(fetch_prices_batch(_need, period="3mo"))

# Fetch live prices FIRST — this populates _TW_STOCK_NAMES cache via the TWSE API
# (the API response carries the Chinese name in the "n" field for every ticker).
# Scoring functions can then use the cached name for non-universe stocks.
_live_tickers = [t for t in _all_extra if t]
_query_live = fetch_live_prices(_live_tickers) if _live_tickers else {}

# Score search ticker
_sres = None
if _sticker:
    _sres = score_stock(_sticker, prices.get(_sticker), cat_sc.get(_sticker, 0), foreign.get(_sticker, 0),
                        us_macro_stock_bonus(_sticker, us_data))
    if _sres:
        _sres["catalysts"] = get_catalyst_labels(_sticker, all_news)

# Score watchlist tickers
_watch_results = {}
for _wt in st.session_state.watchlist:
    _wr = score_stock(_wt, prices.get(_wt), cat_sc.get(_wt, 0), foreign.get(_wt, 0),
                      us_macro_stock_bonus(_wt, us_data))
    if _wr:
        _wr["catalysts"] = get_catalyst_labels(_wt, all_news)
        _watch_results[_wt] = _wr

# Score recent search tickers
_recent_results = {}
for _rt in _recent:
    _rr = score_stock(_rt, prices.get(_rt), cat_sc.get(_rt, 0), foreign.get(_rt, 0),
                      us_macro_stock_bonus(_rt, us_data))
    if _rr:
        _rr["catalysts"] = get_catalyst_labels(_rt, all_news)
        _recent_results[_rt] = _rr

# ── Fill holdings in sidebar ──────────────────────────────────────────────────
custom = st.session_state.get("custom_holdings", {})

# Fetch prices for any custom tickers not yet loaded
new_tickers = [t for t in custom if t not in prices]
if new_tickers:
    prices.update(fetch_prices_batch(new_tickers, period="3mo"))

# Build unified holdings list: fixed defaults + custom additions
def _holding_row(ticker, name, df, cost=0, shares=0):
    if df is None or len(df) < 2:
        return {"ticker": ticker, "name": name, "error": True}
    p1  = float(df["Close"].iloc[-1])
    p0  = float(df["Close"].iloc[-2])
    chg = (p1 / p0 - 1) * 100
    row = {
        "ticker": ticker, "name": name, "price": p1, "chg": chg,
        "wk_high": float(df["Close"].tail(5).max()),
        "wk_low":  float(df["Close"].tail(5).min()),
        "cost": cost, "shares": shares, "error": False,
    }
    if cost > 0:
        row["pnl_pct"] = (p1 - cost) / cost * 100
        row["pnl_amt"] = (p1 - cost) * shares if shares > 0 else None
    return row

hidden = st.session_state.get("hidden_holdings", set())
holdings_info = []
for t, v in MY_HOLDINGS.items():
    if t not in hidden:
        saved = st.session_state.get("custom_holdings", {}).get(t, {})
        holdings_info.append(_holding_row(t, v["name"], prices.get(t),
                                          saved.get("cost", 0), saved.get("shares", 0)))
for t, v in custom.items():
    if t not in MY_HOLDINGS and t not in hidden:
        name = TECH_UNIVERSE.get(t, {}).get("name", t.replace(".TW",""))
        holdings_info.append(_holding_row(t, name, prices.get(t), v.get("cost",0), v.get("shares",0)))
# ── Holdings card renderer (used in main or sidebar) ─────────────────────────
def render_holding_card(h, container=None):
    ctx = container or st
    ticker = h["ticker"]
    name   = h["name"]

    if h.get("error"):
        with ctx.expander(f"{ticker.replace('.TW','')} {name}"):
            st.caption("資料不足，請確認代號是否正確")
            if st.button("🗑 移除", key=f"del_err_{ticker}"):
                st.session_state.custom_holdings.pop(ticker, None)
                st.session_state.hidden_holdings.add(ticker)
                st.rerun()
        return

    chg   = h["chg"]
    arrow = "▲" if chg >= 0 else "▼"
    label = f"{ticker.replace('.TW','')} {name}　{arrow}{abs(chg):.2f}%"

    with ctx.expander(label):
        edit_key = f"edit_open_{ticker}"
        if edit_key not in st.session_state:
            st.session_state[edit_key] = False
        if st.button("✏️ 編輯持倉", key=f"editbtn_{ticker}"):
            st.session_state[edit_key] = not st.session_state[edit_key]
            st.rerun()
        if st.session_state[edit_key]:
            saved = st.session_state.custom_holdings.get(ticker, {})
            e1, e2 = st.columns(2)
            new_shares = e1.number_input("持股數", min_value=0.0,
                                         value=float(saved.get("shares", 0)),
                                         step=1.0, key=f"sh_{ticker}")
            new_cost   = e2.number_input("買進均價", min_value=0.0,
                                         value=float(saved.get("cost", 0)),
                                         step=0.1, key=f"co_{ticker}")
            if st.button("💾 儲存", key=f"save_{ticker}", use_container_width=True):
                st.session_state.custom_holdings[ticker] = {"shares": new_shares, "cost": new_cost}
                st.session_state[edit_key] = False
                st.rerun()
        st.divider()

        st.metric("現價", f"NT${h['price']:.1f}", f"{chg:+.2f}%", delta_color="inverse")
        st.caption(f"5日高 {h.get('wk_high',0):.1f}　／　低 {h.get('wk_low',0):.1f}")

        if "pnl_pct" in h:
            pnl_color = "#ef5350" if h["pnl_pct"] >= 0 else "#00c853"
            pnl_arrow = "▲" if h["pnl_pct"] >= 0 else "▼"
            pnl_amt_str = f"　NT${h['pnl_amt']:+.0f}" if h.get("pnl_amt") else ""
            st.markdown(
                f'<div style="color:{pnl_color};font-size:13px;margin:4px 0">'
                f'損益　{pnl_arrow}{abs(h["pnl_pct"]):.2f}%{pnl_amt_str}'
                f'　｜　成本 NT${h["cost"]:.1f}</div>',
                unsafe_allow_html=True
            )
        st.divider()

        sell = analyze_holding_sell(prices.get(ticker))
        if sell:
            urgency_icon = {"高":"🔴","中":"🟡","低":"🟢"}.get(sell["urgency"],"⚪")
            st.markdown(f"**{urgency_icon} {sell['action']}**")
            st.markdown(
                f'<div style="margin:8px 0">'
                f'<div style="color:#ef5350;font-size:13px">🎯 目標賣出　NT${sell["target_sell"]}　(+{sell["upside"]}%)</div>'
                f'<div style="color:#00c853;font-size:13px;margin-top:4px">🛡 止損參考　NT${sell["stop_loss"]}　({sell["downside"]}%)</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.caption(f"RSI {sell['rsi']}　MA20 {'✅' if sell['above_ma20'] else '⚠️'}　MACD {'↑' if sell['macd_pos'] else '↓'}")
            st.divider()
            for r in sell["reasons"]:
                st.caption(f"• {r}")
        else:
            st.caption("資料不足，無法分析")

        st.divider()
        if st.button("🗑 已賣出，移除此股", key=f"del_{ticker}", use_container_width=True):
            st.session_state.custom_holdings.pop(ticker, None)
            st.session_state.hidden_holdings.add(ticker)
            st.rerun()

# ── Total portfolio summary ───────────────────────────────────────────────────
total_cost = sum(h.get("cost", 0) * h.get("shares", 0) for h in holdings_info if h.get("cost", 0) > 0)
total_val  = sum(h.get("price", 0) * h.get("shares", 0) for h in holdings_info if h.get("cost", 0) > 0 and not h.get("error"))
total_pnl  = total_val - total_cost if total_cost > 0 else 0
total_pct  = (total_pnl / total_cost * 100) if total_cost > 0 else 0

# ── Score stocks (needed by sidebar compact list AND picks view) ──────────────
skip = set(MY_HOLDINGS.keys())
scored = []
for ticker in TECH_UNIVERSE:
    if ticker in skip:
        continue
    res = score_stock(ticker, prices.get(ticker), cat_sc.get(ticker, 0), foreign.get(ticker, 0),
                      us_macro_stock_bonus(ticker, us_data))
    if res:
        # 零股小資調整：RSI過熱難買到低點；高價股零股難累積
        _adj = 0
        if res.get("rsi", 50) > 75: _adj -= 10  # overbought = bad accumulation entry
        if res.get("rsi", 50) < 40: _adj +=  5  # oversold = good accumulation entry
        if res.get("last_price", 0) > 500: _adj -= 8  # expensive per share
        res["score"] = max(0, min(100, res["score"] + _adj))
        if res["score"] >= min_score:
            res["catalysts"] = get_catalyst_labels(ticker, all_news)
            scored.append(res)
scored.sort(key=lambda x: x["score"], reverse=True)
picks = scored[:top_n]

# ── Fill sidebar content based on view mode ───────────────────────────────────
with sidebar_content:
    # Portfolio summary (always shown at top)
    if total_cost > 0:
        pnl_col = "#ef5350" if total_pnl >= 0 else "#00c853"
        pnl_arrow = "▲" if total_pnl >= 0 else "▼"
        st.markdown(
            f'<div style="background:#0d1117;border:1px solid #252d45;border-radius:8px;padding:10px 14px;margin-bottom:8px">'
            f'<div style="font-size:11px;color:#555;margin-bottom:4px">總成本　NT${total_cost:,.0f}</div>'
            f'<div style="font-size:15px;font-weight:700;color:{pnl_col}">'
            f'{pnl_arrow} {abs(total_pct):.2f}%　NT${total_pnl:+,.0f}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    if st.session_state.view_mode == "picks":
        # Sidebar shows holdings (compact)
        for h in holdings_info:
            render_holding_card(h)
    else:
        # Sidebar shows compact picks list
        st.caption("今日精選（點左上按鈕返回）")
        for i, p in enumerate(scored[:top_n] if scored else [], 1):
            chg_col = "#ef5350" if p["mom1d"] >= 0 else "#00c853"
            st.markdown(
                f'<div style="padding:6px 0;border-bottom:1px solid #1a1a2e">'
                f'<span style="color:#aaa;font-size:13px">#{i}　'
                f'<b style="color:#e0e0e0">{p["ticker"].replace(".TW","")} {p["name"]}</b>'
                f'　<span style="color:{chg_col}">{p["mom1d"]:+.1f}%</span>'
                f'　<span style="color:#555;font-size:11px">信心 {p["score"]}</span></span></div>',
                unsafe_allow_html=True
            )

# ── Query card renderer (search result + watchlist) ──────────────────────────
def conf_color(s):
    return "#00c853" if s >= 80 else ("#ffd54f" if s >= 60 else "#ef5350")

def _get_score_reasons(sres: dict) -> str:
    """
    回傳最誠實的一句話解釋為什麼不建議買進。
    只選最關鍵的那一個原因，不列清單。
    """
    rsi   = sres.get("rsi", 50)
    vr    = sres.get("vol_ratio", 1.0)
    mom5d = sres.get("mom5d", 0)
    cat   = sres.get("cat_score", 0)
    tech  = sres.get("tech_score", 0)
    sc    = sres.get("score", 0)
    price = sres.get("last_price", 0)

    # 優先順序：最嚴重的問題先說
    if rsi >= 82:
        return (
            f"RSI {rsi:.0f}，嚴重超買。你現在買進，是在替已經賺錢的人出貨。"
            f" 歷史上 RSI 超過 80 進場的散戶，大多數在接下來兩週內虧損。"
            f" 不是「可能回調」，而是「大概率會拉回」。等 RSI 回到 55 以下再說。"
        )
    if rsi >= 72:
        return (
            f"RSI {rsi:.0f}，短期漲幅過高。前面的人已經賺了，隨時可能獲利了結壓著你。"
            f" 追在這裡是最常見的散戶進場時機錯誤。等 RSI 回到 55 左右，籌碼穩定後再考慮。"
        )
    if mom5d <= -6:
        return (
            f"近5日大跌 {abs(mom5d):.1f}%，股價正在主動下跌。"
            f" 「跌了就買覺得便宜」是散戶最常見的虧損陷阱——往往買在中途，繼續跌。"
            f" 等出現連續兩天紅K且量能放大，才代表跌勢真的結束。"
        )
    if rsi <= 28:
        return (
            f"RSI {rsi:.0f}，超賣但仍在下跌。「很便宜」不等於「不會再跌」。"
            f" 超賣只代表跌得快，不代表會馬上反彈，現在進場是接一把還在往下掉的刀。"
            f" 等 RSI 連續兩天向上才是止跌訊號。"
        )
    if vr < 0.6:
        return (
            f"成交量只剩均量的 {vr:.0%}，市場幾乎沒有人在買這支股票。"
            f" 沒有資金流入，股價不會上漲。買了之後只能等，"
            f" 而零股投資最怕的就是把資金鎖在一支沒人關注的股票上。"
        )
    if tech <= 3:
        return (
            "均線完全空頭排列，短中長期趨勢都往下，不是暫時震盪是結構性下跌。"
            " 在這種排列進場，方向跟市場完全相反。"
            " 等股價重新站回 MA20 且 MA20 轉為向上，才是趨勢改變的最基本確認。"
        )
    if cat == 0 and vr < 1.0:
        return (
            "無題材也無量能，是最容易被套牢的組合。"
            " 沒有新聞催化，沒有資金流入，買進後只能等，而等待本身也是成本。"
            " 台股的資金很容易追題材（AI、航運、生技），沒有故事的股票很難獲得關注。"
        )
    if rsi <= 40 and mom5d <= -2:
        return (
            f"RSI {rsi:.0f} 且近5日跌 {abs(mom5d):.1f}%，動能持續走弱。"
            f" 兩個指標同時偏空，代表市場對這支股票缺乏信心。等趨勢反轉確認再進場。"
        )
    # 兜底：整體分數不足
    return (
        f"綜合評分 {sc}/100，各項指標沒有一個特別突出的優勢。"
        f" 在勝率本就不高的情況下，把資金留著等更明確的機會，比勉強進場更合理。"
    )

def render_query_card(ticker, sres, live_d, key_sfx):
    sc        = sres["score"]
    bar_color = conf_color(sc)
    mom_cls   = "up" if sres["mom5d"] >= 0 else "down"
    cats      = sres.get("catalysts") or ["技術面分析"]
    cat_str   = "　".join(cats[:2])

    if sc >= 60:   verdict, vcolor = "✅ 建議買入",       "#ef5350"
    elif sc >= 45: verdict, vcolor = "🟡 條件不足，觀望",  "#ffd54f"
    else:          verdict, vcolor = "❌ 不建議買進",      "#00c853"

    if live_d and live_d["price"] > 0:
        lp, chg, chg_pct = live_d["price"], live_d["chg"], live_d["chg_pct"]
        lc  = "#ef5350" if chg >= 0 else "#00c853"
        arr = "▲" if chg >= 0 else "▼"
        live_html = (
            f'<div class="live-in-card">'
            f'<span class="live-big" style="color:{lc}">{lp:.1f}</span>'
            f'<span class="live-chg-in" style="color:{lc}">{arr} {abs(chg):.1f} ({abs(chg_pct):.2f}%)</span>'
            f'<span class="closed-badge">{live_d["time"]}</span>'
            f'</div>'
        )
    else:
        live_html = f'<div class="live-in-card"><span style="color:#555">收盤 NT${sres["last_price"]:.1f}</span></div>'

    in_watch = ticker in st.session_state.watchlist
    _star = "★" if in_watch else "☆"
    _scol = "#ffd54f" if in_watch else "#888"

    # Button rendered first; card overlays it via negative margin + pointer-events:none
    _, _sc = st.columns([10, 1])
    with _sc:
        st.markdown('<span class="star-sentinel"></span>', unsafe_allow_html=True)
        _clicked = st.button(_star, key=f"star_{key_sfx}", use_container_width=True, help="追蹤")

    st.markdown(
        f'<div style="margin-top:-3rem;pointer-events:none">'
        f'<div class="card">'
        f'<div class="card-top">'
        f'<span class="stock-name">{ticker.replace(".TW","").replace(".TWO","")} {sres["name"]}</span>'
        f'<span class="stock-sub">{sres["en"]}</span>'
        f'<span style="font-size:13px;color:{vcolor};font-weight:700;margin-left:auto">{verdict}</span>'
        f'<span style="font-size:20px;color:{_scol};line-height:1;margin-left:10px">{_star}</span>'
        f'</div>'
        f'{live_html}'
        f'<div class="price-row">'
        f'<span class="arrow">目標</span>'
        f'<span class="price-target">NT${sres["target_price"]:.1f}</span>'
        f'<span class="pct-badge">+{sres["target_pct"]:.0f}%</span>'
        f'</div>'
        f'<div class="stop-row">🛡 止損 NT${sres["stop_loss"]:.1f}　({sres["stop_pct"]:.1f}%)</div>'
        f'<div class="info-row">'
        f'<span>RSI <span class="info-val">{sres["rsi"]:.0f}</span></span>'
        f'<span>量比 <span class="info-val">{sres["vol_ratio"]:.1f}x</span></span>'
        f'<span>5日 <span class="info-val {mom_cls}">{sres["mom5d"]:+.1f}%</span></span>'
        f'</div>'
        f'<div class="catalyst">📌 {cat_str}</div>'
        f'<div class="conf-wrap"><div class="conf-bar" style="width:{int(sc)}%;background:{bar_color}"></div></div>'
        f'<div style="font-size:11px;color:#555;margin-top:3px">信心指數 {sc}/100</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── 不建議買進時：一句話誠實說明原因 + RSI 即時監控設定 ──────────────────────
    if sc < 60:
        _reason      = _get_score_reasons(sres)
        _border_col  = "#ffd54f" if sc >= 45 else "#c0392b"
        _reason_col  = "#ffd54f" if sc >= 45 else "#ff8a80"
        _label       = "⚠️ 為什麼現在不適合買？" if sc >= 45 else "❌ 為什麼強烈不建議現在買？"
        _score_breakdown = (
            f'量能 {sres["vol_score"]}/30　動能 {sres["mom_score"]}/25　'
            f'技術 {sres["tech_score"]}/25　催化劑 {sres["cat_score"]}/30'
        )
        st.markdown(
            f'<div style="background:#0c1018;border-left:3px solid {_border_col};'
            f'border-radius:0 8px 8px 0;padding:14px 16px;margin:-4px 0 10px 0">'
            f'<div style="font-size:11px;color:#555;margin-bottom:8px">{_label}</div>'
            f'<div style="font-size:13px;font-weight:600;color:{_reason_col};line-height:1.7">'
            f'{_reason}</div>'
            f'<div style="margin-top:10px;font-size:11px;color:#333;'
            f'border-top:1px solid #1a1a2a;padding-top:6px">'
            f'評分細項：{_score_breakdown}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

        # ── RSI 即時監控設定 ────────────────────────────────────────────────────
        _tkey     = key_sfx                          # already unique per ticker
        _existing = st.session_state.rsi_thresholds.get(ticker, {})
        _rsi_now  = sres.get("rsi", 50)

        if _existing:
            # Already monitoring → show status badge + cancel
            _et  = _existing.get("target", 50)
            _ed  = _existing.get("direction", "below")
            _edl = "跌破" if _ed == "below" else "突破"
            st.markdown(
                f'<div style="font-size:12px;color:#7eb3ff;padding:4px 0 6px">'
                f'📡 RSI 監控中：等待 RSI {_edl} {_et:.0f}　'
                f'→ 側邊欄「📡」查看即時動態</div>',
                unsafe_allow_html=True
            )
            if st.button("取消 RSI 監控", key=f"rsi_cancel_{_tkey}", use_container_width=True):
                st.session_state.rsi_thresholds.pop(ticker, None)
                st.rerun()
        else:
            # Smart defaults based on current RSI
            if _rsi_now >= 70:
                _def_tgt, _def_dir = 55.0, "below"   # overbought → wait for RSI < 55
            elif _rsi_now >= 50:
                _def_tgt, _def_dir = 50.0, "below"   # elevated → wait for RSI < 50
            elif _rsi_now < 30:
                _def_tgt, _def_dir = 35.0, "above"   # oversold falling → wait for RSI > 35 (recovery)
            else:
                _def_tgt, _def_dir = 45.0, "below"

            st.markdown(
                '<div style="font-size:12px;color:#666;margin:8px 0 4px">'
                '📡 設定 RSI 到達目標值時提醒我</div>',
                unsafe_allow_html=True
            )
            _sc1, _sc2, _sc3 = st.columns([3, 3, 3])
            _rsi_tgt = _sc1.number_input(
                "目標 RSI", 5.0, 95.0,
                value=_def_tgt, step=1.0,
                key=f"rsi_tgt_{_tkey}", label_visibility="collapsed",
                help="RSI 到達此數值時在「📡 監控」頁顯示進場提醒"
            )
            _rsi_dir = _sc2.selectbox(
                "方向", ["below", "above"],
                format_func=lambda x: "↓ 跌破（買入）" if x == "below" else "↑ 突破（留意）",
                index=0 if _def_dir == "below" else 1,
                key=f"rsi_dir_{_tkey}", label_visibility="collapsed"
            )
            if _sc3.button("📡 開始監控", key=f"rsi_set_{_tkey}", use_container_width=True):
                st.session_state.rsi_thresholds[ticker] = {
                    "target":    float(_rsi_tgt),
                    "direction": _rsi_dir,
                }
                # Auto-add to watchlist so it's reachable
                if ticker not in st.session_state.watchlist:
                    st.session_state.watchlist.append(ticker)
                st.session_state.view_mode = "monitor"
                st.session_state._close_sidebar = True
                st.rerun()

    if _clicked:
        if in_watch:
            st.session_state.watchlist.remove(ticker)
        else:
            if ticker not in st.session_state.watchlist:
                st.session_state.watchlist.append(ticker)
        st.rerun()

# ── Helpers & fragments (defined here so they're always available) ───────────
def _is_market_open() -> bool:
    tw = _now_tw()
    return tw.weekday() < 5 and (
        (tw.hour == 9) or (10 <= tw.hour <= 12) or
        (tw.hour == 13 and tw.minute <= 30)
    )

@st.fragment(run_every="10s")
def render_rsi_monitor(monitored_tickers: list, prices: dict):
    """
    Auto-refreshing RSI monitoring dashboard.
    Every 10s: fetches live prices → computes calc_live_rsi → shows gauge + threshold alert.
    """
    if not monitored_tickers:
        st.caption("尚無監控中的股票。搜尋任何股票 → 若系統建議觀望 → 點「📡 開始監控」加入。")
        return

    now_str = _now_tw().strftime("%H:%M:%S")
    is_open = _is_market_open()
    live    = fetch_live_prices(monitored_tickers)
    badge   = "● 盤中即時" if is_open else "收盤價（非交易時段）"
    st.caption(f"📡 RSI 即時監控　{badge}　最後更新：{now_str}　每10秒自動刷新")

    for ticker in monitored_tickers:
        cfg = st.session_state.rsi_thresholds.get(ticker, {})
        if not cfg:
            continue

        target_rsi = float(cfg.get("target", 50))
        direction  = cfg.get("direction", "below")    # "below" | "above"

        live_d     = live.get(ticker) or {}
        live_price = live_d.get("price", 0)
        df         = prices.get(ticker)
        if df is None or len(df) < 15:
            st.caption(f"{ticker.replace('.TW','').replace('.TWO','')} — 資料不足，請確認代號")
            continue

        # Current live RSI (appends live price to history for intraday accuracy)
        current_rsi = round(calc_live_rsi(df, live_price) if live_price > 0
                            else calc_rsi(df["Close"]), 1)

        # RSI velocity: compare to yesterday's close RSI
        prev_rsi = round(calc_rsi(df["Close"].iloc[:-1]) if len(df) > 15
                         else current_rsi, 1)
        rsi_vel  = round(current_rsi - prev_rsi, 1)

        # Threshold check
        triggered = (
            (direction == "below" and current_rsi <= target_rsi) or
            (direction == "above" and current_rsi >= target_rsi)
        )

        # ETA estimate (assumes RSI continues at current daily velocity)
        gap = current_rsi - target_rsi           # + means RSI above target
        eta_str = ""
        if not triggered and abs(rsi_vel) > 0.1:
            moving_right = (direction == "below" and rsi_vel < 0) or \
                           (direction == "above" and rsi_vel > 0)
            if moving_right:
                days = abs(gap / rsi_vel)
                if days <= 45:
                    eta_str = f"照此趨勢約 {days:.0f} 個交易日"

        # RSI color zone
        if current_rsi >= 70:   rsi_col = "#ef5350"
        elif current_rsi >= 60: rsi_col = "#ff9800"
        elif current_rsi >= 40: rsi_col = "#ffd54f"
        elif current_rsi >= 30: rsi_col = "#7eb3ff"
        else:                   rsi_col = "#00c853"

        # Stock name
        _info = TECH_UNIVERSE.get(ticker, {})
        _name = _info.get("name") or _TW_STOCK_NAMES.get(ticker) \
                or ticker.replace(".TW","").replace(".TWO","")
        _code = ticker.replace(".TW","").replace(".TWO","")

        # Price HTML
        if live_price > 0:
            _chg     = live_d.get("chg", 0)
            _chg_pct = live_d.get("chg_pct", 0)
            _lc      = "#ef5350" if _chg >= 0 else "#00c853"
            _arr     = "▲" if _chg >= 0 else "▼"
            price_html = (f'<span style="font-size:14px;font-weight:700;color:{_lc}">'
                          f'NT${live_price:.1f} {_arr}{abs(_chg_pct):.1f}%</span>')
        else:
            price_html = '<span style="font-size:13px;color:#555">—</span>'

        # Velocity display
        _vc  = "#ef5350" if rsi_vel > 0.3 else ("#00c853" if rsi_vel < -0.3 else "#555")
        _vi  = "↑" if rsi_vel > 0.3 else ("↓" if rsi_vel < -0.3 else "→")
        _vel_html = f'<span style="font-size:13px;font-weight:700;color:{_vc}">{_vi} {abs(rsi_vel):.1f}/日</span>'

        dir_label = "跌破" if direction == "below" else "突破"

        # Card style: green glow when triggered
        if triggered:
            _bg  = "#071a07"; _bdr = "#00c853"
            _diff_str = ""
            _status = (
                f'<div style="background:#00c85322;border:1px solid #00c85366;'
                f'border-radius:7px;padding:9px 14px;margin-top:10px;text-align:center;'
                f'font-size:14px;font-weight:700;color:#00c853">'
                f'🔔 RSI {current_rsi} 已達進場條件！現在可以考慮買入！</div>'
            )
        else:
            _bg  = "#0d1424"; _bdr = "#1e2d45"
            _diff_abs = abs(current_rsi - target_rsi)
            _eta_part = f"　｜　{eta_str}" if eta_str else (
                "　｜　目前趨勢反向，需耐心等待" if not eta_str and abs(rsi_vel) > 0.1 else "")
            _status = (
                f'<div style="font-size:12px;color:#777;margin-top:8px">'
                f'⏳ 等 RSI {dir_label} {target_rsi:.0f}　'
                f'｜　目前差距 {_diff_abs:.1f}{_eta_part}</div>'
            )

        # Bar positions (0-100%)
        _bp = int(min(100, max(0, current_rsi)))  # current RSI pointer
        _tp = int(min(100, max(0, target_rsi)))   # threshold marker

        st.markdown(
            f'<div style="background:{_bg};border:1px solid {_bdr};'
            f'border-radius:10px;padding:14px 18px;margin-bottom:14px">'

            # ── Header ──
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">'
            f'<span style="font-size:15px;font-weight:700;color:#f0f0f0">{_code} {_name}</span>'
            f'{price_html}'
            f'<span style="font-size:11px;color:#444;margin-left:auto">{now_str}</span>'
            f'</div>'

            # ── RSI big + velocity + target ──
            f'<div style="display:flex;align-items:baseline;gap:14px;margin-bottom:10px">'
            f'<span style="font-size:32px;font-weight:800;color:{rsi_col};line-height:1">'
            f'RSI {current_rsi}</span>'
            f'{_vel_html}'
            f'<span style="font-size:12px;color:#555;margin-left:auto">'
            f'目標：{dir_label} {target_rsi:.0f}</span>'
            f'</div>'

            # ── RSI bar: color zones + animated pointer + threshold mark ──
            # Outer wrapper has overflow:visible so the needle tip can stick out
            f'<div style="position:relative;height:14px;margin:0 0 6px">'
            # Zone gradient background
            f'<div style="position:absolute;inset:0;border-radius:7px;overflow:hidden;'
            f'background:linear-gradient(90deg,'
            f'#00c85355 0%,#00c85355 30%,'
            f'#7eb3ff55 30%,#7eb3ff55 50%,'
            f'#ffd54f55 50%,#ffd54f55 70%,'
            f'#ef535055 70%,#ef535055 100%)"></div>'
            # Current RSI needle (colored glow)
            f'<div style="position:absolute;top:-3px;bottom:-3px;'
            f'left:calc({_bp}% - 2px);width:4px;'
            f'background:{rsi_col};border-radius:3px;'
            f'box-shadow:0 0 8px {rsi_col}88"></div>'
            # Threshold marker (blue line + label above)
            f'<div style="position:absolute;top:0;bottom:0;'
            f'left:calc({_tp}% - 1px);width:2px;background:#7eb3ff;border-radius:1px"></div>'
            f'<div style="position:absolute;bottom:18px;'
            f'left:calc({_tp}% - 12px);font-size:10px;color:#7eb3ff;white-space:nowrap">'
            f'目標 {target_rsi:.0f}</div>'
            f'</div>'

            # Zone labels
            f'<div style="display:flex;justify-content:space-between;'
            f'font-size:10px;color:#333;margin-top:10px">'
            f'<span>0</span><span>30 超賣</span>'
            f'<span>50 中性</span><span>70 超買</span><span>100</span>'
            f'</div>'

            f'{_status}'
            f'</div>',
            unsafe_allow_html=True
        )

    # ── Manage monitors ──────────────────────────────────────────────────────
    if monitored_tickers:
        st.caption("管理監控清單：")
        for _mt in list(monitored_tickers):
            _mc  = st.session_state.rsi_thresholds.get(_mt, {})
            if not _mc:
                continue
            _mcode = _mt.replace(".TW","").replace(".TWO","")
            _minfo = TECH_UNIVERSE.get(_mt, {})
            _mname = _minfo.get("name") or _TW_STOCK_NAMES.get(_mt, _mcode)
            _mdl   = "跌破" if _mc.get("direction") == "below" else "突破"
            _mtgt  = _mc.get("target", 50)
            _mr1, _mr2 = st.columns([6, 1])
            _mr1.caption(f"{_mcode} {_mname}　目標 RSI {_mdl} {_mtgt:.0f}")
            if _mr2.button("✕", key=f"rsi_rm_{_mt.replace('.','_')}", help="移除監控"):
                st.session_state.rsi_thresholds.pop(_mt, None)
                st.rerun()

# ── Market index bar + minimalist refresh ────────────────────────────────────
_mi_col, _ref_col = st.columns([11, 1])
with _mi_col:
    if mkt:
        idx_val = mkt.get("index", "—")
        idx_chg = mkt.get("change", "—")
        is_up   = not str(idx_chg).startswith("-")
        mkt_col = "#ef5350" if is_up else "#00c853"
        st.markdown(
            f'<span style="color:#888;font-size:13px">加權指數　</span>'
            f'<span style="font-size:16px;font-weight:700;color:#f0f0f0">{idx_val}</span>'
            f'　<span style="color:{mkt_col};font-size:14px">{idx_chg}</span>'
            f'　<span style="color:#555;font-size:12px">｜　盤前資料 {_epoch}　載入 {data["ts"]}　｜　漲停 ±10%</span>',
            unsafe_allow_html=True
        )
with _ref_col:
    st.markdown('<span class="refresh-sentinel"></span>', unsafe_allow_html=True)
    if st.button("↻", key="top_refresh", help="重新整理", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── Main view: Search history ────────────────────────────────────────────────
if st.session_state.view_mode == "search":
    st.markdown("## 🔍 搜尋記錄")
    if not _recent:
        st.caption("還沒有搜尋記錄。在左側輸入股票代號查詢。")
    else:
        for _rt in _recent:
            if _rt in _recent_results:
                render_query_card(_rt, _recent_results[_rt], _query_live.get(_rt), f"r_{_rt}")
            else:
                st.warning(f"{_rt.replace('.TW','')} — 找不到資料")
    if _recent and st.button("🗑 清除搜尋記錄", use_container_width=True):
        st.session_state.recent_searches = []
        st.session_state.search_ticker   = None
        st.rerun()
    st.divider()
    with st.expander("📰 今日早盤新聞", expanded=False):
        for h in data["headlines"][:8]:
            st.markdown(f'<div class="news-line">{h}</div>', unsafe_allow_html=True)
    st.stop()

# ── Main view: Watchlist ─────────────────────────────────────────────────────
if st.session_state.view_mode == "watchlist":
    st.markdown("## ⭐ 追蹤清單")
    if not st.session_state.watchlist:
        st.caption("還沒有追蹤的股票。在精選推薦或搜尋結果中點 ☆ 加入。")
    else:
        for _wt in st.session_state.watchlist:
            if _wt in _watch_results:
                render_query_card(_wt, _watch_results[_wt], _query_live.get(_wt), f"wv_{_wt}")
    st.divider()
    with st.expander("📰 今日早盤新聞", expanded=False):
        for h in data["headlines"][:8]:
            st.markdown(f'<div class="news-line">{h}</div>', unsafe_allow_html=True)
    st.stop()

# ── Main view: Holdings ───────────────────────────────────────────────────────
if st.session_state.view_mode == "holdings":
    st.markdown("## 💼 我的持股")

    with st.expander("＋ 新增 / 編輯持股", expanded=False):
        st.caption("輸入股票代號（如 2454）、股數、買進均價")
        _hc1, _hc2, _hc3 = st.columns([2, 2, 2])
        _h_code   = _hc1.text_input("代號",   placeholder="2454",  label_visibility="collapsed", key="hp_code")
        _h_shares = _hc2.text_input("股數",   placeholder="100",   label_visibility="collapsed", key="hp_shares")
        _h_cost   = _hc3.text_input("買進價", placeholder="850",   label_visibility="collapsed", key="hp_cost")
        if st.button("新增", use_container_width=True, key="hp_add"):
            _code = _h_code.strip().upper()
            if _code:
                _hticker = _code + ".TW" if not _code.endswith(".TW") else _code
                try:
                    st.session_state.custom_holdings[_hticker] = {
                        "shares": float(_h_shares) if _h_shares else 0,
                        "cost":   float(_h_cost)   if _h_cost   else 0,
                    }
                    st.rerun()
                except ValueError:
                    st.error("請輸入有效數字")

        for _ht, _hv in list(st.session_state.custom_holdings.items()):
            _hd1, _hd2 = st.columns([4, 1])
            _hd1.caption(f"{_ht.replace('.TW','')}　{_hv['shares']:.0f}股　成本 {_hv['cost']:.1f}")
            if _hd2.button("✕", key=f"hp_del_{_ht}"):
                del st.session_state.custom_holdings[_ht]
                st.rerun()

        _h_hidden = st.session_state.get("hidden_holdings", set())
        if _h_hidden:
            st.caption("已移除的持股：")
            for _ht in list(_h_hidden):
                _hname = MY_HOLDINGS.get(_ht, {}).get("name", _ht.replace(".TW",""))
                _hr1, _hr2 = st.columns([4, 1])
                _hr1.caption(f"{_ht.replace('.TW','')} {_hname}")
                if _hr2.button("↩", key=f"hp_restore_{_ht}"):
                    st.session_state.hidden_holdings.discard(_ht)
                    st.rerun()

    for h in holdings_info:
        render_holding_card(h)
    st.divider()
    with st.expander("📰 今日早盤新聞", expanded=False):
        for h in data["headlines"][:8]:
            st.markdown(f'<div class="news-line">{h}</div>', unsafe_allow_html=True)
    st.stop()

# ── Main view: RSI Monitor ────────────────────────────────────────────────────
if st.session_state.view_mode == "monitor":
    st.markdown(
        "## 📡 RSI 即時監控　"
        "<span style='font-size:12px;background:#0d2a4a;color:#7eb3ff;"
        "border-radius:5px;padding:2px 8px;vertical-align:middle'>"
        "盤中每10秒自動更新</span>",
        unsafe_allow_html=True
    )
    _mon_keys = list(st.session_state.rsi_thresholds.keys())

    # Fetch prices for monitored tickers that aren't in the main cache yet
    _mon_need = [t for t in _mon_keys if t and t not in prices]
    if _mon_need:
        from widget import fetch_prices_batch as _fpb
        prices.update(_fpb(_mon_need, period="3mo"))

    if not _mon_keys:
        st.info(
            "**尚無監控中的股票。**\n\n"
            "**使用方式：**\n"
            "1. 在左側搜尋欄輸入任何台股代號（如 2454、0050、6207）\n"
            "2. 若系統顯示「觀望」或「不建議買進」，會出現原因分析\n"
            "3. 設定目標 RSI（例如等 RSI 跌破 50）→ 點「📡 開始監控」\n"
            "4. 回到此頁，即可看到即時 RSI 動態與進場提醒"
        )
    else:
        render_rsi_monitor(_mon_keys, prices)

    st.divider()
    with st.expander("📰 今日早盤新聞", expanded=False):
        for h in data["headlines"][:8]:
            st.markdown(f'<div class="news-line">{h}</div>', unsafe_allow_html=True)
    st.stop()

# ── US Overnight Macro Panel ────────────────────────────────────────────────
def _c(pct):
    """Taiwan convention: UP = red, DOWN = green."""
    return "#ef5350" if pct >= 0 else "#00c853"
def _a(pct):
    return "▲" if pct >= 0 else "▼"

if us_data and (us_data.get("macro_score", 0) != 0 or us_data.get("sox", {}).get("val", 0) > 0):
    _ms   = us_data.get("macro_score", 0)
    _sent = us_data.get("sentiment", "neutral")
    _sent_html = (
        '<span style="color:#ef5350;font-weight:700">🟢 偏多</span>' if _sent == "bullish" else
        '<span style="color:#00c853;font-weight:700">🔴 偏空</span>' if _sent == "bearish" else
        '<span style="color:#ffd54f;font-weight:700">🟡 中性</span>'
    )
    _sox   = us_data["sox"];   _nq = us_data["nasdaq"]; _sp = us_data["sp500"]
    _nvda  = us_data["nvda"];  _tsm = us_data["tsm_adr"]; _vix = us_data["vix"]
    _usd   = us_data["usd_twd"]
    _ms_col = "#ef5350" if _ms >= 3 else ("#00c853" if _ms <= -3 else "#ffd54f")

    st.markdown(
        f'<div style="background:#0a1628;border:1px solid #1e3a5c;border-radius:10px;'
        f'padding:14px 18px;margin-bottom:12px">'
        # Title row
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
        f'<span style="font-size:14px;font-weight:700;color:#7eb3ff">🌍 美股隔夜概況</span>'
        f'<span style="font-size:11px;color:#555">（{_epoch}）</span>'
        f'<span style="margin-left:auto;font-size:12px">{_sent_html}　'
        f'<span style="color:{_ms_col};font-weight:700">台股影響 {_ms:+.0f}</span></span>'
        f'</div>'
        # Indices row
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:8px">'
        f'<div style="text-align:center">'
        f'<div style="font-size:10px;color:#555">費半 SOX</div>'
        f'<div style="font-size:16px;font-weight:700;color:{_c(_sox["pct"])}">'
        f'{_a(_sox["pct"])}{abs(_sox["pct"]):.1f}%</div>'
        f'<div style="font-size:10px;color:#444">{_sox["val"]:.0f}</div></div>'

        f'<div style="text-align:center">'
        f'<div style="font-size:10px;color:#555">那斯達克</div>'
        f'<div style="font-size:16px;font-weight:700;color:{_c(_nq["pct"])}">'
        f'{_a(_nq["pct"])}{abs(_nq["pct"]):.1f}%</div>'
        f'<div style="font-size:10px;color:#444">{_nq["val"]:.0f}</div></div>'

        f'<div style="text-align:center">'
        f'<div style="font-size:10px;color:#555">標普500</div>'
        f'<div style="font-size:16px;font-weight:700;color:{_c(_sp["pct"])}">'
        f'{_a(_sp["pct"])}{abs(_sp["pct"]):.1f}%</div>'
        f'<div style="font-size:10px;color:#444">{_sp["val"]:.0f}</div></div>'

        f'<div style="text-align:center">'
        f'<div style="font-size:10px;color:#555">VIX 恐慌</div>'
        f'<div style="font-size:16px;font-weight:700;color:{"#ef5350" if _vix["val"] > 25 else "#00c853" if _vix["val"] < 15 else "#ffd54f"}">'
        f'{_vix["val"]:.1f}</div>'
        f'<div style="font-size:10px;color:#444">{"偏高⚠️" if _vix["val"] > 25 else "正常"}</div></div>'
        f'</div>'
        # ADR + USD row
        f'<div style="display:flex;gap:16px;font-size:12px;color:#888;border-top:1px solid #1a1a2e;padding-top:8px">'
        f'<span>台積電ADR <b style="color:{_c(_tsm["pct"])}">{_a(_tsm["pct"])}{abs(_tsm["pct"]):.1f}%</b></span>'
        f'<span>NVDA <b style="color:{_c(_nvda["pct"])}">{_a(_nvda["pct"])}{abs(_nvda["pct"]):.1f}%</b></span>'
        f'<span>美元/台幣 <b style="color:#e0e0e0">{_usd["val"]:.2f}</b>'
        f' <span style="color:{_c(_usd["pct"])};font-size:10px">{_a(_usd["pct"])}{abs(_usd["pct"]):.2f}%</span></span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # Global news headlines
    if global_news:
        with st.expander(f"🌐 國際財經新聞 ({len(global_news)}則)", expanded=False):
            for _gh in global_news:
                st.markdown(f'<div class="news-line">🌐 {_gh}</div>', unsafe_allow_html=True)

# ── Picks view header ────────────────────────────────────────────────────────
st.markdown("## 🎯 今日精選潛力股　<span style='font-size:12px;background:#1a3a5c;color:#7eb3ff;border-radius:5px;padding:2px 8px;vertical-align:middle'>全產業・零股小資</span>", unsafe_allow_html=True)

# ── Chip helper ───────────────────────────────────────────────────────────────
CHIP_CSS = {"NVIDIA":"nv","AMD":"amd","Apple":"apl","AI":"ai","CoWoS":"cow"}
def supply_chips(supply):
    return " ".join(
        f'<span class="chip {CHIP_CSS[s]}">{s}</span>'
        for s in supply if s in CHIP_CSS
    )


# ── Stock cards with embedded live prices (10s auto-refresh) ─────────────────
# Always run every 10s — decorator is evaluated once at import so the
# conditional would be frozen to whatever time the server started.
@st.fragment(run_every="10s")
def render_stock_cards(picks, prices, show_chart):
    tickers  = [p["ticker"] for p in picks]
    live     = fetch_live_prices(tickers)
    is_open  = _is_market_open()
    refresh  = "每10秒更新 ●" if is_open else "非交易時段"
    st.caption(f"📡 即時股價　{refresh}　　更新：{_now_tw().strftime('%H:%M:%S')}　｜　零股盤中 09:00–13:30 ／ 盤後 14:00–14:30")

    for rank, p in enumerate(picks, 1):
        sc      = p["score"]
        bar_color = conf_color(sc)
        vr      = p["vol_ratio"]
        fi      = p["foreign_net"]
        cats    = p.get("catalysts") or ["技術面突破"]
        cat_str = "　".join(cats)

        if sc >= 88:  acq = "📈 強勢股，可逢低分批零股累積"
        elif sc >= 72: acq = "💡 趨勢向上，適合定期定額布局"
        else:          acq = "⏳ 等 RSI 回落至 50 以下再考慮進場"

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

            live_block = (
                f'<div class="live-in-card">'
                f'<span class="live-big" style="color:{lc}">{lp:.1f}</span>'
                f'<span class="live-chg-in" style="color:{lc}">{arrow} {abs(chg):.1f} ({abs(chg_pct):.2f}%)</span>'
                f'{status_tag}{live_badge}'
                f'<span class="live-vol">{vol:,}千股　{upd}</span>'
                f'</div>'
            )
        else:
            live_block = '<div class="live-in-card"><span style="color:#555">等待開盤資料…</span></div>'

        ref_price  = (d["price"] if d and d["price"] > 0 else p["last_price"])
        shares_10k = int(10000 / ref_price) if ref_price > 0 else 0

        bar_w  = int(sc)
        info_html = '　'.join(f'<span>{x}</span>' for x in info_parts)
        _in_w  = p["ticker"] in st.session_state.watchlist
        _star  = "★" if _in_w else "☆"
        _scol  = "#ffd54f" if _in_w else "#888"

        # Button rendered first; card overlays it via negative margin + pointer-events:none
        _, _sc = st.columns([10, 1])
        with _sc:
            st.markdown('<span class="star-sentinel"></span>', unsafe_allow_html=True)
            _star_clicked = st.button(_star, key=f"star_pick_{p['ticker']}", use_container_width=True, help="追蹤")

        st.markdown(
            f'<div style="margin-top:-3rem;pointer-events:none">'
            f'<div class="card">'
            f'<div class="card-top">'
            f'<div class="rank">{rank}</div>'
            f'<span class="stock-name">{p["ticker"].replace(".TW","")} {p["name"]}</span>'
            f'<span class="stock-sub">{p["en"]}</span>'
            f'<span style="margin-left:auto;font-size:20px;color:{_scol};line-height:1">{_star}</span>'
            f'</div>'
            f'{live_block}'
            f'<div class="price-row">'
            f'<span class="arrow">目標</span>'
            f'<span class="price-target">NT${p["target_price"]:.1f}</span>'
            f'<span class="pct-badge">+{p["target_pct"]:.0f}%</span>'
            f'</div>'
            f'<div class="stop-row">💰 參考買點 NT${p["last_price"]:.1f}　　🛡 止損 NT${p["stop_loss"]:.1f}　({p["stop_pct"]:.1f}%)</div>'
            f'<div style="font-size:12px;color:#7eb3ff;margin:2px 0 6px">🪙 NT$10,000 約可零股買入 {shares_10k} 股</div>'
            f'<div class="info-row">{info_html}</div>'
            f'<div class="catalyst">📌 {cat_str}</div>'
            f'<div class="sell-note">{acq}</div>'
            f'<div class="conf-wrap"><div class="conf-bar" style="width:{bar_w}%;background:{bar_color}"></div></div>'
            f'<div style="font-size:11px;color:#555;margin-top:3px">信心指數 {sc}/100</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True
        )

        # ── 新手操作建議（即時更新，每10秒隨股價重算）────────────────────────
        _ref = d["price"] if d and d["price"] > 0 else p["last_price"]
        _adv = get_beginner_advice(prices.get(p["ticker"]), _ref)
        if _adv:
            _rsi_pct  = min(100, max(0, _adv["rsi"]))
            _rsi_col  = _adv["rsi_col"]
            _stop_pct = _adv["stop_pct"]
            with st.expander(f"💡 {p['ticker'].replace('.TW','')} 新手建議（點擊展開）", expanded=False):
                st.markdown(
                    f'<div class="advice-box">'
                    f'<div class="advice-title">💡 新手操作建議（即時更新）</div>'

                    # RSI 即時
                    f'<div class="advice-row">'
                    f'  <span class="advice-label">📊 RSI</span>'
                    f'  <div style="flex:1">'
                    f'    <span class="rsi-big" style="color:{_rsi_col}">{_adv["rsi"]}</span>'
                    f'    <span style="font-size:13px;color:{_rsi_col};margin-left:8px;font-weight:700">{_adv["rsi_signal"]}</span>'
                    f'    <div class="rsi-bar-wrap">'
                    f'      <div class="rsi-bar-fill" style="width:{_rsi_pct}%;background:linear-gradient(90deg,#00c853 30%,#ffd54f 60%,#ef5350 85%)"></div>'
                    f'    </div>'
                    f'    <div class="rsi-zones"><span>0</span><span>30 超賣</span><span>50</span><span>70 超買</span><span>100</span></div>'
                    f'    <div class="advice-note" style="color:{_rsi_col};margin-top:5px">{_adv["rsi_action"]}</div>'
                    f'  </div>'
                    f'</div>'

                    # 趨勢
                    f'<div class="advice-row" style="margin-top:10px">'
                    f'  <span class="advice-label">📈 趨勢</span>'
                    f'  <span style="color:{_adv["trend_col"]};font-weight:700">'
                    f'    {_adv["trend_icon"]} {_adv["trend"]}'
                    f'  </span>'
                    f'</div>'

                    # 建議買點
                    f'<div class="advice-row">'
                    f'  <span class="advice-label">🎯 買點</span>'
                    f'  <div>'
                    f'    <span class="advice-val">NT${_adv["buy_low"]} ~ {_adv["buy_high"]}</span>'
                    f'    <div class="advice-note">{_adv["buy_note"]}</div>'
                    f'  </div>'
                    f'</div>'

                    # 止損 & 目標
                    f'<div class="advice-row">'
                    f'  <span class="advice-label">🛡 止損</span>'
                    f'  <span class="advice-val" style="color:#00c853">NT${_adv["stop_loss"]}'
                    f'  <span style="font-size:12px;color:#666"> ({_stop_pct}%)</span></span>'
                    f'</div>'
                    f'<div class="advice-row">'
                    f'  <span class="advice-label">🏆 目標</span>'
                    f'  <span class="advice-val" style="color:#ef5350">NT${_adv["target"]}'
                    f'  <span style="font-size:12px;color:#666"> (+{_adv["target_pct"]}%)</span></span>'
                    f'</div>'

                    # MA參考
                    f'<div style="font-size:11px;color:#444;margin-top:6px">'
                    f'  均線參考：MA5 {_adv["ma5"]}　MA20 {_adv["ma20"]}'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

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

        if _star_clicked:
            if _in_w:
                st.session_state.watchlist.remove(p["ticker"])
            else:
                if p["ticker"] not in st.session_state.watchlist:
                    st.session_state.watchlist.append(p["ticker"])
            st.rerun()

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
