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
    ts = _now_tw().strftime("%H:%M")
    return dict(news=news, headlines=headlines, catalyst=cat_sc,
                foreign=foreign, market=market, prices=prices, ts=ts)

# ── Session state init ────────────────────────────────────────────────────────
if "view_mode"        not in st.session_state: st.session_state.view_mode        = "picks"
# valid modes: "picks" | "holdings" | "watchlist" | "search"
if "custom_holdings"  not in st.session_state: st.session_state.custom_holdings  = {}
if "hidden_holdings"  not in st.session_state: st.session_state.hidden_holdings  = set()
if "search_ticker"    not in st.session_state: st.session_state.search_ticker    = None
if "watchlist"        not in st.session_state: st.session_state.watchlist        = []
if "recent_searches"  not in st.session_state: st.session_state.recent_searches  = []

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # Compact header: title/date left, refresh right
    _hc1, _hc2 = st.columns([3, 1])
    with _hc1:
        st.markdown("#### 📈 台股分析")
        st.caption(_now_tw().strftime('%Y-%m-%d  %H:%M'))
    with _hc2:
        st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
        if st.button("🔄", use_container_width=True, help="重新整理"):
            st.cache_data.clear()
            st.rerun()

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

    _vm_search_active = st.session_state.view_mode == "search"
    if st.button("🔍 搜尋記錄  ✓" if _vm_search_active else "🔍 搜尋記錄",
                 use_container_width=True,
                 type="primary" if _vm_search_active else "secondary",
                 key="nav_search_inline"):
        st.session_state.view_mode = "search"; st.rerun()

    st.divider()

    # Nav: 3 buttons in one row
    vm = st.session_state.view_mode
    _nc1, _nc2, _nc3 = st.columns(3)
    for _col, (_vk, _vl) in zip([_nc1, _nc2, _nc3], [
        ("picks", "🎯 精選"), ("holdings", "💼 持股"), ("watchlist", "⭐ 追蹤"),
    ]):
        _active = vm == _vk
        if _col.button(_vl + (" ✓" if _active else ""), key=f"nav_{_vk}",
                       type="primary" if _active else "secondary", use_container_width=True):
            st.session_state.view_mode = _vk; st.rerun()

    with st.expander("＋ 新增 / 編輯持股"):
        st.caption("輸入股票代號（如 2454）、股數、買進均價")
        col1, col2, col3 = st.columns([2, 2, 2])
        new_code  = col1.text_input("代號", placeholder="2454",  label_visibility="collapsed")
        new_shares= col2.text_input("股數", placeholder="100",   label_visibility="collapsed")
        new_cost  = col3.text_input("買進價", placeholder="850", label_visibility="collapsed")
        if st.button("新增", use_container_width=True):
            code = new_code.strip().upper()
            if code:
                ticker = code + ".TW" if not code.endswith(".TW") else code
                try:
                    st.session_state.custom_holdings[ticker] = {
                        "shares": float(new_shares) if new_shares else 0,
                        "cost":   float(new_cost)   if new_cost   else 0,
                    }
                    st.rerun()
                except ValueError:
                    st.error("請輸入有效數字")

        # Show existing custom holdings with delete buttons
        for t, v in list(st.session_state.custom_holdings.items()):
            c1, c2 = st.columns([4, 1])
            c1.caption(f"{t.replace('.TW','')}　{v['shares']:.0f}股　成本 {v['cost']:.1f}")
            if c2.button("✕", key=f"quickdel_{t}"):
                del st.session_state.custom_holdings[t]
                st.rerun()

        # Restore hidden holdings
        hidden_set = st.session_state.get("hidden_holdings", set())
        if hidden_set:
            st.caption("已移除的持股：")
            for t in list(hidden_set):
                name = MY_HOLDINGS.get(t, {}).get("name", t.replace(".TW",""))
                c1, c2 = st.columns([4, 1])
                c1.caption(f"{t.replace('.TW','')} {name}")
                if c2.button("↩", key=f"restore_{t}"):
                    st.session_state.hidden_holdings.discard(t)
                    st.rerun()

    sidebar_content = st.container()

    st.divider()
    top_n     = st.slider("推薦數量", 3, 8, 5)
    min_score = st.slider("最低評分門檻", 30, 75, 40)
    show_chart = st.checkbox("顯示K線圖", value=False)
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

# Score search ticker
_sres = None
if _sticker:
    _sres = score_stock(_sticker, prices.get(_sticker), cat_sc.get(_sticker, 0), foreign.get(_sticker, 0))
    if _sres:
        _sres["catalysts"] = get_catalyst_labels(_sticker, all_news)

# Score watchlist tickers
_watch_results = {}
for _wt in st.session_state.watchlist:
    _wr = score_stock(_wt, prices.get(_wt), cat_sc.get(_wt, 0), foreign.get(_wt, 0))
    if _wr:
        _wr["catalysts"] = get_catalyst_labels(_wt, all_news)
        _watch_results[_wt] = _wr

# Score recent search tickers
_recent_results = {}
for _rt in _recent:
    _rr = score_stock(_rt, prices.get(_rt), cat_sc.get(_rt, 0), foreign.get(_rt, 0))
    if _rr:
        _rr["catalysts"] = get_catalyst_labels(_rt, all_news)
        _recent_results[_rt] = _rr

# Batch live prices for all extra tickers in one call
_live_tickers = [t for t in _all_extra if t]
_query_live = fetch_live_prices(_live_tickers) if _live_tickers else {}

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
    res = score_stock(ticker, prices.get(ticker), cat_sc.get(ticker, 0), foreign.get(ticker, 0))
    if res and res["score"] >= min_score:
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
        f'<span class="stock-name">{ticker.replace(".TW","")} {sres["name"]}</span>'
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

    if _clicked:
        if in_watch:
            st.session_state.watchlist.remove(ticker)
        else:
            if ticker not in st.session_state.watchlist:
                st.session_state.watchlist.append(ticker)
        st.rerun()

# ── Market index bar (always shown) ──────────────────────────────────────────
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
st.divider()


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
    for h in holdings_info:
        render_holding_card(h)
    st.divider()
    with st.expander("📰 今日早盤新聞", expanded=False):
        for h in data["headlines"][:8]:
            st.markdown(f'<div class="news-line">{h}</div>', unsafe_allow_html=True)
    st.stop()

# ── Picks view header ────────────────────────────────────────────────────────
st.markdown("## 🎯 今日精選潛力股")
st.divider()

# ── Chip helper ───────────────────────────────────────────────────────────────
CHIP_CSS = {"NVIDIA":"nv","AMD":"amd","Apple":"apl","AI":"ai","CoWoS":"cow"}
def supply_chips(supply):
    return " ".join(
        f'<span class="chip {CHIP_CSS[s]}">{s}</span>'
        for s in supply if s in CHIP_CSS
    )

# ── Stock cards with embedded live prices (30s auto-refresh) ─────────────────
def _is_market_open() -> bool:
    tw = _now_tw()
    return tw.weekday() < 5 and (
        (tw.hour == 9) or (10 <= tw.hour <= 12) or
        (tw.hour == 13 and tw.minute <= 30)
    )

# Always run every 10s — decorator is evaluated once at import so the
# conditional would be frozen to whatever time the server started.
@st.fragment(run_every="10s")
def render_stock_cards(picks, prices, show_chart):
    tickers  = [p["ticker"] for p in picks]
    live     = fetch_live_prices(tickers)
    is_open  = _is_market_open()
    refresh  = "每10秒更新 ●" if is_open else "非交易時段"
    st.caption(f"📡 即時股價　{refresh}　　更新：{_now_tw().strftime('%H:%M:%S')}")

    for rank, p in enumerate(picks, 1):
        sc      = p["score"]
        bar_color = conf_color(sc)
        vr      = p["vol_ratio"]
        fi      = p["foreign_net"]
        cats    = p.get("catalysts") or ["技術面突破"]
        cat_str = "　".join(cats)

        if sc >= 88:  sell = "⏰ 今天收盤前賣，有機會漲停"
        elif sc >= 72: sell = "⏰ 漲 5–7% 就賣，不要貪"
        else:          sell = "⏰ 明天早上9–10點趁高點賣掉"

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
            f'<div class="stop-row">💰 建議買入 NT${p["last_price"]:.1f}　　🛡 止損 NT${p["stop_loss"]:.1f}　({p["stop_pct"]:.1f}%)</div>'
            f'<div class="info-row">{info_html}</div>'
            f'<div class="catalyst">📌 {cat_str}</div>'
            f'<div class="sell-note">{sell}</div>'
            f'<div class="conf-wrap"><div class="conf-bar" style="width:{bar_w}%;background:{bar_color}"></div></div>'
            f'<div style="font-size:11px;color:#555;margin-top:3px">信心指數 {sc}/100</div>'
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
