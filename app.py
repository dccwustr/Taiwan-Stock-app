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

def _is_market_open() -> bool:
    """True during Taiwan stock market hours: weekdays 09:00–13:30 TWN."""
    tw = _now_tw()
    if tw.weekday() >= 5:
        return False
    h, m = tw.hour, tw.minute
    return (h == 9) or (10 <= h <= 12) or (h == 13 and m <= 30)

def _trading_epoch() -> str:
    """Returns the trading-date + intraday slot string used as the cache key.
    Changes 4× per trading day so load_data() re-fetches fresh news, foreign
    buying and market data at each slot boundary:

      PRE  08:00–08:59  盤前 — overnight news + US data
      MRN  09:00–10:59  早盤 — opening momentum + fresh catalysts
      MID  11:00–13:29  午盤 — mid-session updates
      AFT  13:30+       盤後 — final close prices + foreign buying
    """
    tw = _now_tw()
    h, m = tw.hour, tw.minute

    # Before 8 AM on any day → use previous trading day's AFT slot
    if h < 8:
        tw -= timedelta(days=1)
        while tw.weekday() >= 5:
            tw -= timedelta(days=1)
        return tw.strftime("%Y-%m-%d-AFT")

    # Weekend → use Friday's AFT slot
    if tw.weekday() >= 5:
        while tw.weekday() >= 5:
            tw -= timedelta(days=1)
        return tw.strftime("%Y-%m-%d-AFT")

    # Weekday 08:00+: intraday slots
    date_str = tw.strftime("%Y-%m-%d")
    if h < 9:
        return f"{date_str}-PRE"                        # 08:00–08:59
    elif h < 11:
        return f"{date_str}-MRN"                        # 09:00–10:59
    elif h < 13 or (h == 13 and m < 30):
        return f"{date_str}-MID"                        # 11:00–13:29
    else:
        return f"{date_str}-AFT"                        # 13:30+

def _epoch_slot_info() -> tuple:
    """Returns (slot_label, next_update_str) for the current trading slot."""
    tw = _now_tw()
    h, m = tw.hour, tw.minute
    if tw.weekday() >= 5:
        return "盤後分析", "下週一 08:00"
    if h < 8:
        return "盤後分析", "今日 08:00"
    if h < 9:
        return "盤前分析", "09:00 早盤更新"
    if h < 11:
        return "早盤分析", "11:00 午盤更新"
    if h < 13 or (h == 13 and m < 30):
        return "午盤分析", "13:30 收盤更新"
    return "盤後分析", "明日 08:00"

import streamlit as st
import streamlit.components.v1 as components

# Soft-import: app works without it (localStorage persistence disabled),
# but never crashes the whole app if the package isn't installed.
try:
    from streamlit_javascript import st_javascript
    _HAS_STJS = True
except Exception:
    _HAS_STJS = False
    def st_javascript(js_code, key=None):   # graceful no-op
        return 0
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
    fetch_market_alerts,
    fetch_yf_fundamentals_batch, fetch_twse_shareholder_meetings,
    calc_fundamental_bonus,
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
  .fund-row {
    display: flex; gap: 8px; flex-wrap: wrap; margin: 4px 0 2px;
    font-size: 12px;
  }
  .fund-tag {
    background: #0a1e12; border: 1px solid #1a5c2a;
    border-radius: 12px; padding: 2px 8px; color: #4caf7d;
  }
  .fund-tag-warn {
    background: #1e0a0a; border: 1px solid #5c1a1a;
    border-radius: 12px; padding: 2px 8px; color: #e57373;
  }
  .meeting-tag {
    background: #0a1229; border: 1px solid #1a3a6e;
    border-radius: 12px; padding: 2px 8px; color: #7eb3ff;
  }
  .near-limit-warn {
    font-size: 13px; font-weight: 700; color: #ff5252;
    background: #1a0505; border-left: 3px solid #c0392b;
    border-radius: 0 6px 6px 0; padding: 6px 10px; margin-top: 6px;
  }

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

# ── Category universe ─────────────────────────────────────────────────────────
# Each entry: emoji, name (zh), en, desc (tag line), why (investment thesis),
# tickers (curated universe ~8-14 stocks — scoring engine picks the best 5).
CATEGORY_UNIVERSE = {
    "ai": {
        "emoji": "🤖", "name": "AI人工智能", "en": "AI / Machine Learning",
        "desc": "AI推論晶片・大型語言模型硬體・AI應用",
        "why": "NVIDIA供應鏈爆量、資料中心AI建設週期長，台灣廠商直接受益於每一層",
        "tickers": ["3661.TW","5274.TW","3443.TW","2454.TW","2379.TW",
                    "3034.TW","8299.TW","6669.TW","2382.TW","2356.TW","3231.TW"],
    },
    "ic_design": {
        "emoji": "🔧", "name": "IC設計", "en": "IC Design",
        "desc": "SoC・驅動IC・電源管理・特殊應用晶片",
        "why": "台灣IC設計全球第二，聚焦AI邊緣、車用、伺服器三大成長引擎",
        "tickers": ["2454.TW","3034.TW","2379.TW","6415.TW","3661.TW",
                    "4966.TW","5274.TW","8299.TW","3443.TW","4919.TW","2344.TW"],
    },
    "foundry": {
        "emoji": "🏭", "name": "半導體製造", "en": "Semiconductor Foundry",
        "desc": "晶圓代工・先進製程・成熟/特殊製程",
        "why": "AI晶片全靠台積電N3/N2；CoWoS先進封裝嚴重缺產能，整個代工鏈受惠",
        # 3037 removed (欣興 = PCB/substrate, not a foundry)
        "tickers": ["2330.TW","2303.TW","5347.TW","6770.TW"],
    },
    "osat": {
        "emoji": "📦", "name": "封裝測試", "en": "IC Packaging & Testing",
        "desc": "先進封裝・CoWoS・SoIC・晶片測試・基板",
        "why": "AI GPU需要CoWoS先進封裝，日月光訂單滿載；封測是AI供應鏈現在的瓶頸",
        # 2408=Nanya Tech(DRAM,not OSAT) removed; 2449=KYEC(IC testing) added
        "tickers": ["3711.TW","8150.TW","6271.TW","2449.TW"],
    },
    "ai_server": {
        "emoji": "🖥️", "name": "AI伺服器", "en": "AI Servers / Cloud",
        "desc": "GPU伺服器・液冷機櫃・AI基礎建設ODM",
        "why": "雲巨頭AI資本支出2024年翻倍；台廠ODM廣達、緯穎搶訂AI伺服器直接受惠",
        # 4977=PCL(PCB maker,not server ODM) removed; 2317=Foxconn added
        "tickers": ["2382.TW","6669.TW","2356.TW","3231.TW","2301.TW","2317.TW","2324.TW"],
    },
    "thermal": {
        "emoji": "🌡️", "name": "散熱模組", "en": "Thermal / Cooling",
        "desc": "熱管・均熱板・液冷系統・AI伺服器散熱",
        "why": "AI GPU功耗600W+，散熱需求暴增；液冷滲透率從低位飛速成長，是被忽視的主題",
        # Removed: 6413(delisted), 3529(力旺=memory IP), 2362(藍天=PC ODM), 3003(KS Terminals=connectors)
        # Added: 3324=雙鴻科技(vapor chambers for AI servers)
        "tickers": ["3017.TW","3324.TW","8163.TW","1626.TW","2369.TW"],
    },
    "networking": {
        "emoji": "📡", "name": "網通設備", "en": "Networking Equipment",
        "desc": "資料中心交換器・400G/800G光模組・AI叢集互連",
        "why": "AI叢集需要超高頻寬互連，400G→800G升級週期剛啟動，智邦等台廠接單滿",
        # Added 3062=建漢(networking ODM), kept 2345=智邦, 6277=宏正, 2332=友訊
        "tickers": ["2345.TW","6277.TW","2332.TW","3062.TW","4706.TW","3706.TW"],
    },
    "gaming": {
        "emoji": "🎮", "name": "遊戲", "en": "Gaming",
        "desc": "手遊・PC遊戲・電競・遊戲發行平台",
        "why": "生成式AI大幅降低遊戲製作成本，台灣遊戲股題材活絡；電競市場持續擴張",
        # 3060=Min Aik(motors,not gaming), 6491=Pegavision(contact lenses!) removed
        "tickers": ["5478.TW","6180.TW","6111.TW","4943.TW"],
    },
    "software": {
        "emoji": "💻", "name": "應用軟體", "en": "Software / SaaS",
        "desc": "ERP・IT服務・雲端應用・企業管理系統",
        "why": "AI賦能軟體訂閱轉型，台灣IT服務股基本面改善、本益比修復空間大",
        # 3658 missing, 3686=Danen(PCB not software), 4916=Parpro(plastics) removed
        "tickers": ["6510.TW","6104.TW","2353.TW","2395.TW","2376.TW"],
    },
    "ev": {
        "emoji": "🔋", "name": "電動車", "en": "EV Components",
        "desc": "電控系統・充電模組・BMS・馬達驅動IC",
        "why": "全球EV滲透率加速，台廠在電控、充電樁、連接器取得關鍵供應地位",
        # Removed 2059(中興電=5075元，價格過高for零股), kept core EV plays
        "tickers": ["2308.TW","1504.TW","1590.TW","1537.TW","5536.TW","5483.TW"],
    },
    "green_energy": {
        "emoji": "☀️", "name": "綠能太陽能", "en": "Green Energy",
        "desc": "太陽能模組・離岸風電・儲能系統・電網",
        "why": "RE100採購+政府2050淨零目標；台灣離岸風電裝機量持續上升，政策多頭",
        # 3533=Lotes(AI connectors,not green) removed; 3519(missing) removed
        "tickers": ["3576.TW","6443.TW","6412.TW","1513.TW","1519.TW"],
    },
    "biotech": {
        "emoji": "💊", "name": "生技醫療", "en": "Biotech / Healthcare",
        "desc": "新藥研發・醫療器材・體外診斷・AI醫療",
        "why": "高齡化社會+AI加速新藥研發；台灣生技股授權金題材具備爆發力",
        # 4110=東洋製藥(missing from yfinance data) removed
        "tickers": ["4743.TW","6547.TW","4119.TW","1786.TW","4166.TW","6446.TW"],
    },
    "mobile": {
        "emoji": "📱", "name": "手機零組件", "en": "Mobile Supply Chain",
        "desc": "鏡頭模組・金屬機殼・OLED驅動IC・連接器",
        "why": "iPhone供應鏈補庫存+Android高階機復甦；蘋果新品發布前台廠拉貨明顯",
        "tickers": ["3008.TW","2474.TW","2327.TW","6285.TW","5483.TW","2357.TW","4938.TW"],
    },
}

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)     # 1-hour TTL; epoch param busts cache at each slot boundary
def load_data(epoch: str):                       # epoch = "YYYY-MM-DD-SLOT", changes 4× per trading day
    import io, contextlib
    tickers  = list(TECH_UNIVERSE.keys())
    # Suppress yfinance stdout/stderr chatter inside the cached function
    # (yfinance prints "N Failed downloads:" etc. which can confuse some Streamlit Cloud versions)
    _buf = io.StringIO()
    with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_buf):
        prices   = fetch_prices_batch(tickers, period="3mo")
        us_data  = fetch_us_overnight()
        g_news   = fetch_global_news()
    news     = fetch_cnyes_news(100) + fetch_moneydj_news()
    cat_sc, headlines = analyze_catalysts(news)
    foreign  = fetch_twse_foreign_buying()
    market   = fetch_twse_market_summary()
    ts = _now_tw().strftime("%H:%M")
    return dict(news=news, headlines=headlines, catalyst=cat_sc,
                foreign=foreign, market=market, prices=prices,
                us_data=us_data, global_news=g_news, ts=ts)

@st.cache_data(ttl=3600, show_spinner=False)
def load_category_prices(category_key: str, epoch: str) -> dict:
    """Fetch OHLCV price history for a category's universe. Cached per slot."""
    import io, contextlib
    tickers = CATEGORY_UNIVERSE[category_key]["tickers"]
    _buf = io.StringIO()
    with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_buf):
        return fetch_prices_batch(tickers, period="3mo")

@st.cache_data(ttl=3600*12, show_spinner=False)
def load_fundamentals(epoch_day: str) -> dict:
    """
    yfinance 季報基本面 (營收年增 / 盈利年增 / 毛利率) — 每12小時快取一次。
    Fetches all TECH_UNIVERSE + every category ticker in parallel (~8-15s on cold load).
    epoch_day = YYYY-MM-DD so the cache key changes once per day.
    """
    all_tickers = list(TECH_UNIVERSE.keys())
    for _cinfo in CATEGORY_UNIVERSE.values():
        for _ct in _cinfo.get("tickers", []):
            if _ct not in all_tickers:
                all_tickers.append(_ct)
    fund_map = fetch_yf_fundamentals_batch(all_tickers)
    meetings = fetch_twse_shareholder_meetings()   # returns {} when API unavailable
    return {"fund": fund_map, "meetings": meetings}

# ── Session state init ────────────────────────────────────────────────────────
if "view_mode"        not in st.session_state: st.session_state.view_mode        = "picks"
# valid modes: "picks" | "categories" | "holdings" | "watchlist" | "search" | "monitor"
if "custom_holdings"  not in st.session_state: st.session_state.custom_holdings  = {}
if "hidden_holdings"  not in st.session_state: st.session_state.hidden_holdings  = set()
if "search_ticker"    not in st.session_state: st.session_state.search_ticker    = None
if "watchlist"        not in st.session_state: st.session_state.watchlist        = []
if "recent_searches"  not in st.session_state: st.session_state.recent_searches  = []
if "_close_sidebar"   not in st.session_state: st.session_state._close_sidebar   = False
if "rsi_thresholds"   not in st.session_state: st.session_state.rsi_thresholds   = {}
# rsi_thresholds: {ticker: {"target": float, "direction": "below"|"above"}}
if "seen_alert_ids"   not in st.session_state: st.session_state.seen_alert_ids   = set()
if "alert_snoozed"    not in st.session_state: st.session_state.alert_snoozed    = 0  # epoch sec
if "_last_epoch"        not in st.session_state: st.session_state._last_epoch        = ""
# Two-variable slot-tracking so the "新進榜" badge stays visible the ENTIRE slot:
#   _prev_pick_tickers — previous slot's tickers; STABLE throughout current slot (badge ref)
#   _cur_slot_tickers  — current slot's tickers; updated once per slot change
#   _prev_slot_scores  — previous slot's {ticker: score}; for delta display
#   _cur_slot_scores   — current slot's {ticker: score}
if "_prev_pick_tickers" not in st.session_state: st.session_state._prev_pick_tickers = set()
if "_cur_slot_tickers"  not in st.session_state: st.session_state._cur_slot_tickers  = set()
if "_prev_slot_scores"  not in st.session_state: st.session_state._prev_slot_scores  = {}
if "_cur_slot_scores"   not in st.session_state: st.session_state._cur_slot_scores   = {}
if "selected_category"  not in st.session_state: st.session_state.selected_category  = "ai"

# ── localStorage persistence (watchlist + holdings survive redeployments) ─────
#
# Architecture:
#   SAVE path  – any mutation sets st.session_state._needs_save = True before
#                st.rerun(); on the very next render this block writes to LS.
#   LOAD path  – on the first render of a brand-new browser session (ls_loaded
#                absent) we read LS; st_javascript is async so render-1 returns 0,
#                Streamlit auto-reruns, render-2 returns the real value.
#
# Using a fixed code position (not a helper function) keeps the component key
# stable across renders and avoids duplicate-component collisions.
#
if st.session_state.pop("_needs_save", False):
    # ── SAVE ──────────────────────────────────────────────────────────────────
    _payload = json.dumps({
        "watchlist":      list(st.session_state.get("watchlist",         [])),
        "holdings":       st.session_state.get("custom_holdings",         {}),
        "hidden":         list(st.session_state.get("hidden_holdings", set())),
        "rsi_thresholds": st.session_state.get("rsi_thresholds",         {}),
    })
    # Comma-expression returns 1 so st_javascript gets a clean non-undefined value
    st_javascript(f"(localStorage.setItem('tw_user_data_v1', {json.dumps(_payload)}), 1)")

elif "ls_loaded" not in st.session_state:
    # ── LOAD (once per new browser session) ───────────────────────────────────
    _ls_raw = st_javascript("localStorage.getItem('tw_user_data_v1')")
    if _ls_raw == 0:
        pass   # JS not yet executed; Streamlit auto-reruns → we try again
    else:
        if _ls_raw:   # None means key was never set → keep defaults
            try:
                _ls = json.loads(_ls_raw)
                if isinstance(_ls.get("watchlist"),      list):
                    st.session_state.watchlist       = _ls["watchlist"]
                if isinstance(_ls.get("holdings"),       dict):
                    st.session_state.custom_holdings = _ls["holdings"]
                if isinstance(_ls.get("hidden"),         list):
                    st.session_state.hidden_holdings = set(_ls["hidden"])
                if isinstance(_ls.get("rsi_thresholds"), dict):
                    st.session_state.rsi_thresholds  = _ls["rsi_thresholds"]
            except Exception:
                pass   # corrupt data → keep defaults
        st.session_state.ls_loaded = True

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
            # Strip any existing suffix so "6207.TWO" or "6207.TW" both normalise to "6207.TW"
            if   raw.endswith(".TWO"): raw = raw[:-4]
            elif raw.endswith(".TW"):  raw = raw[:-3]
            # Validate: Taiwan stock codes are 4-5 digits only
            if not raw.isdigit() or not (4 <= len(raw) <= 5):
                st.session_state["_search_err"] = f'「{raw}」不是有效代號，請輸入4-5位數字（如 2330、6207、00878）'
            else:
                st.session_state.pop("_search_err", None)
                ticker = raw + ".TW"
                st.session_state.search_ticker = ticker
                rs = [t for t in st.session_state.recent_searches if t != ticker]
                st.session_state.recent_searches = ([ticker] + rs)[:10]
                st.session_state.view_mode = "search"
                st.session_state._close_sidebar = True
    if st.session_state.get("_search_err"):
        st.caption(f"⚠️ {st.session_state['_search_err']}")

    _vm_search_active = st.session_state.view_mode == "search"
    if st.button("搜尋記錄  ✓" if _vm_search_active else "搜尋記錄",
                 use_container_width=True,
                 type="primary" if _vm_search_active else "secondary",
                 key="nav_search_inline"):
        st.session_state.view_mode = "search"
        st.session_state._close_sidebar = True
        st.rerun()

    st.divider()

    # Nav: 5 buttons (2 top + 3 bottom)
    _n_mon   = len(st.session_state.rsi_thresholds)
    _mon_lbl = f"📡{_n_mon}" if _n_mon else "📡"
    vm       = st.session_state.view_mode
    _nr1, _nr2 = st.columns(2)
    for _col, (_vk, _vl) in zip([_nr1, _nr2], [
        ("picks", "精選推薦"), ("categories", "🏷️ 分類"),
    ]):
        _active = vm == _vk
        if _col.button(_vl + (" ✓" if _active else ""), key=f"nav_{_vk}",
                       type="primary" if _active else "secondary", use_container_width=True):
            st.session_state.view_mode = _vk
            st.session_state._close_sidebar = True
            st.rerun()
    _nr3, _nr4, _nr5 = st.columns(3)
    for _col, (_vk, _vl) in zip([_nr3, _nr4, _nr5], [
        ("holdings", "持股"), ("watchlist", "追蹤"), ("monitor", _mon_lbl),
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

    st.divider()
    st.caption("資料來源：鉅亨網・TWSE・Yahoo Finance")
    st.caption("⚠ 非投資建議，僅供參考")
    st.divider()
    # ── Push notification permission (persists in browser, not session_state) ──
    _np = st_javascript(
        "typeof Notification !== 'undefined' ? Notification.permission : 'unsupported'"
    )
    if _np == "granted":
        st.caption("🔔 重大警報推播：已開啟 ✅")
    elif _np == "denied":
        st.caption("🔕 推播已封鎖，請在瀏覽器網址列 → 網站設定 → 允許通知")
    elif _np in (0, "default", None):
        if st.button("🔔 開啟重大新聞推播", use_container_width=True, help="戰爭・崩盤・聯準會緊急決議 自動通知"):
            st_javascript("await Notification.requestPermission()")
            st.rerun()

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
    try:
        data = load_data(_epoch)
    except Exception as _load_err:
        # If cache fails (rare Streamlit Cloud serialization issue), clear and retry once
        st.cache_data.clear()
        try:
            data = load_data(_epoch)
        except Exception:
            data = dict(news=[], headlines=[], catalyst={},
                        foreign={}, market={}, prices={},
                        us_data={}, global_news=[], ts="--:--")
            st.warning(f"資料載入失敗，請重新整理頁面。（{type(_load_err).__name__}）")

prices      = data.get("prices", {})
all_news    = data.get("news", [])
cat_sc      = data.get("catalyst", {})
foreign     = data.get("foreign", {})
mkt         = data.get("market", {})
us_data     = data.get("us_data", {})
global_news = data.get("global_news", [])

# ── Fundamental data (yfinance quarterly: revenue/earnings growth, margins) ───
_epoch_day   = _now_tw().strftime("%Y-%m-%d")
_fund_cache  = load_fundamentals(_epoch_day)
fund_map     = _fund_cache.get("fund", {})
meeting_map  = _fund_cache.get("meetings", {})

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
        _sf = calc_fundamental_bonus(_sticker, fund_map, meeting_map)
        _sres["score"]        = max(0, min(100, _sres["score"] + _sf["bonus"]))
        _sres["rev_yoy"]      = _sf["rev_yoy"]
        _sres["earn_yoy"]     = _sf["earn_yoy"]
        _sres["fund_labels"]  = _sf["labels"]
        _sres["trailing_eps"] = _sf.get("trailing_eps")
        _sres["forward_eps"]  = _sf.get("forward_eps")
        _sres["forward_pe"]   = _sf.get("forward_pe")
        _sres["catalysts"]    = (_sf["labels"] + get_catalyst_labels(_sticker, all_news))[:4]

# Score watchlist tickers
_watch_results = {}
for _wt in st.session_state.watchlist:
    _wr = score_stock(_wt, prices.get(_wt), cat_sc.get(_wt, 0), foreign.get(_wt, 0),
                      us_macro_stock_bonus(_wt, us_data))
    if _wr:
        _wf = calc_fundamental_bonus(_wt, fund_map, meeting_map)
        _wr["score"]        = max(0, min(100, _wr["score"] + _wf["bonus"]))
        _wr["rev_yoy"]      = _wf["rev_yoy"]
        _wr["earn_yoy"]     = _wf["earn_yoy"]
        _wr["fund_labels"]  = _wf["labels"]
        _wr["trailing_eps"] = _wf.get("trailing_eps")
        _wr["forward_eps"]  = _wf.get("forward_eps")
        _wr["forward_pe"]   = _wf.get("forward_pe")
        _wr["catalysts"]    = (_wf["labels"] + get_catalyst_labels(_wt, all_news))[:4]
        _watch_results[_wt] = _wr

# Score recent search tickers
_recent_results = {}
for _rt in _recent:
    _rr = score_stock(_rt, prices.get(_rt), cat_sc.get(_rt, 0), foreign.get(_rt, 0),
                      us_macro_stock_bonus(_rt, us_data))
    if _rr:
        _rf = calc_fundamental_bonus(_rt, fund_map, meeting_map)
        _rr["score"]        = max(0, min(100, _rr["score"] + _rf["bonus"]))
        _rr["rev_yoy"]      = _rf["rev_yoy"]
        _rr["earn_yoy"]     = _rf["earn_yoy"]
        _rr["fund_labels"]  = _rf["labels"]
        _rr["trailing_eps"] = _rf.get("trailing_eps")
        _rr["forward_eps"]  = _rf.get("forward_eps")
        _rr["forward_pe"]   = _rf.get("forward_pe")
        _rr["catalysts"]    = (_rf["labels"] + get_catalyst_labels(_rt, all_news))[:4]
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
                st.session_state._needs_save = True
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
                st.session_state._needs_save = True
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
            st.session_state._needs_save = True
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
        # 零股小資調整：RSI是否在適合進場區間；高價股零股難累積
        _adj = 0
        _rsi = res.get("rsi", 50)
        if   _rsi > 82:  _adj -= 30  # 嚴重超買：不追
        elif _rsi > 78:  _adj -= 20  # 很熱：等回落
        elif _rsi > 72:  _adj -= 12  # 偏熱：不適合進場
        elif _rsi > 68:  _adj -=  4  # 微熱：謹慎
        elif _rsi >= 45: _adj +=  8  # 甜蜜區間 45-68：最佳進場
        elif _rsi >= 35: _adj +=  3  # 輕微超賣：還不錯
        else:            _adj -= 15  # 極度超賣：可能下跌趨勢
        if res.get("last_price", 0) > 500: _adj -= 8  # expensive per share
        res["score"]    = max(0, min(100, res["score"] + _adj))
        res["_rsi_adj"] = _adj   # stored so live-RSI update can undo and reapply
        # ── 基本面加權 (月營收 / 股東會) ──────────────────────────────────────
        _fund = calc_fundamental_bonus(ticker, fund_map, meeting_map)
        res["score"]        = max(0, min(100, res["score"] + _fund["bonus"]))
        res["rev_yoy"]      = _fund["rev_yoy"]
        res["earn_yoy"]     = _fund["earn_yoy"]
        res["fund_labels"]  = _fund["labels"]
        res["trailing_eps"] = _fund.get("trailing_eps")
        res["forward_eps"]  = _fund.get("forward_eps")
        res["forward_pe"]   = _fund.get("forward_pe")
        if res["score"] >= min_score:
            _tech_labels = get_catalyst_labels(ticker, all_news)
            res["catalysts"] = (_fund["labels"] + _tech_labels)[:4]
            scored.append(res)
scored.sort(key=lambda x: x["score"], reverse=True)

# ── Live intraday scoring update (market hours only) ──────────────────────────
# ONE batch TWSE call fetches live price + yesterday's close for every scored ticker.
# Updates TWO key signals with today's actual intraday data:
#   1. RSI  — appends live price to historical series, re-computes + re-applies adj
#   2. mom1d — live momentum = (live_price / prev_close - 1) × 100
#              replaces the stale "yesterday vs the day before" value from yfinance
# Both run uncached so picks always reflect the current trading session.
if _is_market_open() and scored:
    _score_live_tickers = [r["ticker"] for r in scored]
    _score_live_prices  = fetch_live_prices(_score_live_tickers)
    for _r in scored:
        _ld  = _score_live_prices.get(_r["ticker"], {})
        _lp  = _ld.get("price", 0) if _ld else 0
        if _lp <= 0:
            continue
        _df = prices.get(_r["ticker"])

        # ── 1. Live RSI ────────────────────────────────────────────────────────
        if _df is not None and len(_df) >= 15:
            _new_rsi = round(calc_live_rsi(_df, _lp), 1)
            _old_rsi = _r.get("rsi", 50)
            if abs(_new_rsi - _old_rsi) >= 0.5:
                _old_adj = _r.pop("_rsi_adj", 0)
                _new_adj = 0
                if   _new_rsi > 82:  _new_adj -= 30
                elif _new_rsi > 78:  _new_adj -= 20
                elif _new_rsi > 72:  _new_adj -= 12
                elif _new_rsi > 68:  _new_adj -=  4
                elif _new_rsi >= 45: _new_adj +=  8
                elif _new_rsi >= 35: _new_adj +=  3
                else:                _new_adj -= 15
                _r["score"] = max(0, min(100, _r["score"] - _old_adj + _new_adj))
                _r["rsi"]   = _new_rsi

        # ── 2. Live 1-day momentum ─────────────────────────────────────────────
        # TWSE API "prev" field = yesterday's official close price
        _live_prev = _ld.get("prev", 0)
        if _live_prev > 0:
            _live_mom1d = (_lp / _live_prev - 1) * 100
            _old_mom1d  = _r.get("mom1d", 0)
            if abs(_live_mom1d - _old_mom1d) >= 0.3:
                # score_stock uses: mom1d_s = min(10, max(0, mom1d * 2))
                _old_m1s = min(10, max(0, _old_mom1d * 2))
                _new_m1s = min(10, max(0, _live_mom1d * 2))
                _r["score"] = max(0, min(100, _r["score"] + (_new_m1s - _old_m1s)))
                _r["mom1d"] = round(_live_mom1d, 2)

        # ── 3. Near-limit-up guard ─────────────────────────────────────────────
        # RSI cannot catch this: a stock at RSI 35 (oversold) that jumps +9%
        # today only moves to live RSI ~47 — still in the "sweet spot".
        # But buying near limit-up is one of the most common retail traps:
        # you're the last buyer before profit-taking reversal.
        # Apply a hard penalty so these stocks EXIT today_picks regardless.
        _live_chg_pct = round(_ld.get("chg_pct", 0), 2)
        _r["live_chg_pct"] = _live_chg_pct  # stored for fragment warning display
        if _live_chg_pct >= 9.0:
            # Near/at limit-up (+10%): guaranteed removal from today_picks
            _r["score"]      = max(0, _r["score"] - 45)
            _r["near_limit"] = True
        elif _live_chg_pct >= 7.0:
            # Strong up-day: high reversal risk tomorrow, especially for 零股 investors
            _r["score"]      = max(0, _r["score"] - 22)
            _r["near_limit"] = True

    # Re-sort with live-updated scores
    scored.sort(key=lambda x: x["score"], reverse=True)

# ── Final picks split ──────────────────────────────────────────────────────────
# 今日可進場：RSI合理 + 分數達標 + 今日未大漲 (near-limit guard — belt AND suspenders)
today_picks = [r for r in scored
               if r.get("rsi", 50) < 73
               and r["score"] >= 52
               and r.get("live_chg_pct", 0) < 9.0][:top_n]
# 準備中：RSI偏熱，或今日大漲，等回落後進場（最多3支）
watch_picks = [r for r in scored if r.get("rsi", 50) >= 73 and r["score"] >= 45][:3]
# backward compat
picks = today_picks

# ── Slot-change tracking: badge + score delta ─────────────────────────────────
# _prev_pick_tickers / _prev_slot_scores  = PREVIOUS slot's data — NEVER changes
#   during current slot, so badge and delta display are stable across renders.
# _cur_slot_tickers / _cur_slot_scores    = CURRENT slot's data — recorded once
#   at slot boundary and stays fixed until the next slot change.
#
# Rotation at slot change:
#   prev ← cur  (old current becomes prev for badge comparison)
#   cur  ← new  (today's picks recorded as new current)
_prev_tickers     = st.session_state._prev_pick_tickers   # stable ref, don't mutate
_prev_sc_map      = st.session_state._prev_slot_scores

for _p in today_picks:
    # 新進榜 badge: visible the ENTIRE slot, not just first render
    _p["is_new"]      = bool(_prev_tickers) and _p["ticker"] not in _prev_tickers
    # Score delta vs previous slot (None = no previous data yet)
    _ps = _prev_sc_map.get(_p["ticker"])
    _p["score_delta"] = round(_p["score"] - _ps) if _ps is not None else None

# Rotate slot tracking at slot boundaries (or initialise on first session load)
if st.session_state._last_epoch != _epoch:
    st.session_state._prev_pick_tickers = st.session_state._cur_slot_tickers
    st.session_state._prev_slot_scores  = st.session_state._cur_slot_scores
    st.session_state._cur_slot_tickers  = {_p["ticker"] for _p in today_picks}
    st.session_state._cur_slot_scores   = {_p["ticker"]: _p["score"] for _p in today_picks}
    st.session_state._last_epoch = _epoch
elif not st.session_state._last_epoch:
    # First browser session load: seed cur-slot so next slot change can compare
    st.session_state._cur_slot_tickers = {_p["ticker"] for _p in today_picks}
    st.session_state._cur_slot_scores  = {_p["ticker"]: _p["score"] for _p in today_picks}
    st.session_state._last_epoch = _epoch

# ── Fill sidebar content based on view mode ───────────────────────────────────
with sidebar_content:
    # ── Portfolio summary (always shown, only total — not per stock) ──────────
    if total_cost > 0:
        pnl_col   = "#ef5350" if total_pnl >= 0 else "#00c853"
        pnl_arrow = "▲" if total_pnl >= 0 else "▼"
        # Today's portfolio change (quick calc for sidebar)
        _sb_today = sum(
            h.get("shares", 0) * h.get("price", 0) * h.get("chg", 0) / (100 + h.get("chg", 0))
            for h in holdings_info
            if not h.get("error") and h.get("shares", 0) > 0
            and h.get("cost", 0) > 0 and abs(h.get("chg", 0)) < 99
        )
        _td_col = "#ef5350" if _sb_today >= 0 else "#00c853"
        _td_arr = "▲" if _sb_today >= 0 else "▼"
        st.markdown(
            f'<div style="background:#0d1117;border:1px solid #252d45;border-radius:8px;'
            f'padding:10px 14px;margin-bottom:8px">'
            f'<div style="font-size:11px;color:#555;margin-bottom:4px">'
            f'💼 持股總覽　成本 NT${total_cost:,.0f}</div>'
            f'<div style="font-size:16px;font-weight:700;color:{pnl_col};margin-bottom:2px">'
            f'{pnl_arrow} {abs(total_pct):.2f}%　NT${total_pnl:+,.0f}</div>'
            f'<div style="font-size:12px;color:{_td_col}">'
            f'今日 {_td_arr} NT${abs(_sb_today):,.0f}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    if st.session_state.view_mode != "picks":
        # Sidebar shows compact picks list when NOT on the picks main view
        st.caption("今日可進場（點左上按鈕返回）")
        for i, p in enumerate(today_picks if today_picks else [], 1):
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

def _build_fund_row(p: dict) -> str:
    """Build fundamental tags HTML row for a stock card. Returns '' if no data."""
    tags = []
    rev_yoy      = p.get("rev_yoy",  0.0)   # revenue YoY %
    earn_yoy     = p.get("earn_yoy", 0.0)   # earnings YoY %
    t_eps        = p.get("trailing_eps")     # trailing 12m EPS (NT$)
    f_eps        = p.get("forward_eps")      # forward 12m EPS estimate
    f_pe         = p.get("forward_pe")       # forward P/E ratio

    # Revenue growth chip
    if rev_yoy >= 5:
        tags.append(f'<span class="fund-tag">📊 營收年增 +{rev_yoy:.0f}%</span>')
    elif rev_yoy <= -10:
        tags.append(f'<span class="fund-tag-warn">📊 營收年減 {rev_yoy:.0f}%</span>')

    # Earnings growth chip
    if earn_yoy >= 20:
        tags.append(f'<span class="fund-tag">💰 盈利年增 +{earn_yoy:.0f}%</span>')
    elif earn_yoy <= -20:
        tags.append(f'<span class="fund-tag-warn">💰 盈利年減 {earn_yoy:.0f}%</span>')

    # EPS upgrade/downgrade chip
    if t_eps is not None and f_eps is not None and t_eps > 0:
        eps_chg = (f_eps - t_eps) / abs(t_eps) * 100
        if eps_chg >= 20:
            tags.append(
                f'<span class="fund-tag">📈 EPS NT${t_eps:.1f}→NT${f_eps:.1f}'
                f' (+{eps_chg:.0f}%)</span>'
            )
        elif eps_chg <= -20:
            tags.append(
                f'<span class="fund-tag-warn">📉 EPS NT${t_eps:.1f}→NT${f_eps:.1f}'
                f' ({eps_chg:.0f}%)</span>'
            )
    elif t_eps is not None and t_eps < 0:
        tags.append(f'<span class="fund-tag-warn">⚠️ EPS 虧損 NT${t_eps:.1f}</span>')

    # Forward P/E chip
    if f_pe is not None:
        if f_pe < 12:
            tags.append(f'<span class="fund-tag">💎 預估本益比 {f_pe:.0f}x（低估）</span>')
        elif f_pe > 60:
            tags.append(f'<span class="fund-tag-warn">⚡ 預估本益比 {f_pe:.0f}x（偏高）</span>')

    # Shareholder meeting (from fund_labels list)
    for lbl in p.get("fund_labels", []):
        if "股東會" in lbl:
            tags.append(f'<span class="meeting-tag">🗓 {lbl}</span>')

    if not tags:
        return ""
    inner = "".join(tags)
    return f'<div class="fund-row">{inner}</div>'


def _build_why_buy(p: dict) -> str:
    """
    Generate a '為什麼值得關注' bulleted explanation for the beginner advice box.
    Draws from fundamentals, supply chain, technicals, foreign buying, and catalysts.
    Returns an HTML string (empty string if nothing meaningful to say).
    """
    reasons: list = []

    rev_yoy  = p.get("rev_yoy",  0.0)
    earn_yoy = p.get("earn_yoy", 0.0)
    t_eps    = p.get("trailing_eps")      # trailing 12m EPS (NT$)
    f_eps    = p.get("forward_eps")       # forward 12m EPS estimate
    f_pe     = p.get("forward_pe")        # forward P/E ratio
    rsi      = p.get("rsi", 50.0)
    mom5d    = p.get("mom5d", 0.0)
    fi       = p.get("foreign_net", 0.0)
    vr       = p.get("vol_ratio", 1.0)
    supply   = p.get("supply", [])
    cats     = p.get("catalysts", [])
    fund_lbl = p.get("fund_labels", [])

    # ── 基本面 ─────────────────────────────────────────────────────────────────
    if rev_yoy >= 50:
        reasons.append(f"📈 <b>營收爆發</b>：近期年增 <b>+{rev_yoy:.0f}%</b>，業績大幅超越去年，成長動能極強")
    elif rev_yoy >= 20:
        reasons.append(f"📈 <b>營收成長</b>：近期年增 <b>+{rev_yoy:.0f}%</b>，公司業績持續擴張")
    elif rev_yoy >= 5:
        reasons.append(f"📈 <b>營收溫和成長</b>：年增 +{rev_yoy:.0f}%，業績穩定")
    elif rev_yoy <= -20:
        reasons.append(f"⚠️ <b>注意</b>：近期營收年減 {rev_yoy:.0f}%，需確認是暫時調整還是趨勢反轉")

    if earn_yoy >= 50:
        reasons.append(f"💰 <b>盈利大幅成長</b>：每股獲利（EPS）年增 <b>+{earn_yoy:.0f}%</b>，公司賺錢能力顯著提升")
    elif earn_yoy >= 20:
        reasons.append(f"💰 <b>盈利改善</b>：EPS 年增 +{earn_yoy:.0f}%，獲利逐步提升")

    # ── EPS 估值分析 ───────────────────────────────────────────────────────────
    if t_eps is not None and f_eps is not None and t_eps > 0:
        eps_chg = (f_eps - t_eps) / abs(t_eps) * 100
        if eps_chg >= 50:
            reasons.append(
                f"💎 <b>EPS 大幅升級</b>：今年預估每股盈利 NT${f_eps:.1f}（去年 NT${t_eps:.1f}），"
                f"分析師預測獲利 <b>+{eps_chg:.0f}%</b>，公司進入高速成長期"
            )
        elif eps_chg >= 20:
            reasons.append(
                f"💎 <b>EPS 成長預期</b>：預估今年每股盈利 NT${f_eps:.1f}（去年 NT${t_eps:.1f}），"
                f"獲利成長 +{eps_chg:.0f}%，持續向上"
            )
        elif eps_chg <= -20:
            reasons.append(
                f"⚠️ <b>EPS 預估下修</b>：今年 EPS 預估 NT${f_eps:.1f}（去年 NT${t_eps:.1f}），"
                f"獲利衰退 {eps_chg:.0f}%，需留意業績壓力"
            )
    elif t_eps is not None and t_eps < 0:
        reasons.append(f"⚠️ <b>目前虧損</b>：去年每股虧損 NT${t_eps:.1f}，需觀察轉盈進度")

    # ── 本益比估值 ─────────────────────────────────────────────────────────────
    if f_pe is not None and f_pe > 0:
        if f_pe < 12:
            reasons.append(
                f"💡 <b>股價被低估</b>：預估本益比僅 {f_pe:.0f}x，遠低於科技股均值 25x，"
                f"代表股價相對公司獲利非常便宜，存在補漲空間"
            )
        elif f_pe < 18:
            reasons.append(
                f"💡 <b>合理估值</b>：預估本益比 {f_pe:.0f}x，位於合理區間，"
                f"股價未過度高估，適合長期持有"
            )
        elif f_pe > 60:
            reasons.append(
                f"⚡ <b>高本益比注意</b>：預估本益比 {f_pe:.0f}x，反映市場對高成長的樂觀預期，"
                f"若業績不如預期可能大幅修正，零股買入分批降低風險"
            )

    for lbl in fund_lbl:
        if "高毛利" in lbl:
            reasons.append(f"🏭 <b>高毛利</b>：{lbl.replace('高毛利 ', '')} 毛利率，代表產品競爭力強、定價權高，不易被競爭對手搶走客戶")
            break

    # ── 供應鏈與行業地位 ───────────────────────────────────────────────────────
    if "NVIDIA" in supply:
        reasons.append("🤖 <b>NVIDIA 核心供應鏈</b>：直接供貨給全球最大 AI 晶片公司，AI 資料中心建設持續多年")
    elif "Apple" in supply:
        reasons.append("🍎 <b>蘋果認證供應商</b>：進入蘋果供應鏈門檻極高，一旦進入代表技術與品質達到世界頂尖標準")
    elif "AI" in supply and "NVIDIA" not in supply:
        reasons.append("⚡ <b>AI 供應鏈受益者</b>：直接受惠於全球 AI 基礎建設投資浪潮，需求能見度高")

    # ── 法人動向 ────────────────────────────────────────────────────────────────
    if fi >= 500:
        reasons.append(f"🌐 <b>外資大買超</b>：近期外資淨買入 {fi:.0f}千張，代表國際法人對這支股票高度信心")
    elif fi >= 150:
        reasons.append(f"🌐 <b>外資持續買入</b>：外資淨買入 {fi:.0f}千張，法人籌碼持續累積")

    # ── 技術面甜蜜區 ────────────────────────────────────────────────────────────
    if 45 <= rsi <= 62:
        reasons.append(f"📊 <b>技術面最佳進場位</b>：RSI {rsi:.0f} 在 45–62 甜蜜區間，股價有動能但尚未過熱，是零股分批買入的好時機")
    elif rsi < 40:
        reasons.append(f"📊 <b>超賣反彈機會</b>：RSI {rsi:.0f} 偏低，短期可能已過度下跌，有反彈空間（仍需確認趨勢）")

    if mom5d >= 8 and rsi < 70:
        reasons.append(f"🚀 <b>短線強勢</b>：近5日上漲 {mom5d:+.1f}%，且 RSI 未進入超買，趨勢向上但仍有追漲空間")

    if vr >= 2.0:
        reasons.append(f"📦 <b>量能爆發</b>：今日成交量是20日均量的 {vr:.1f}倍，市場高度關注，大戶可能正在建倉")

    # ── 催化劑 ──────────────────────────────────────────────────────────────────
    # Extract meaningful news-based catalysts (skip generic ones)
    _skip = {"技術面分析", "技術面突破", "AI鏈"}
    _meaningful = [c for c in cats if c not in _skip and "年增" not in c and "盈利" not in c and "月增" not in c and "毛利" not in c]
    if _meaningful:
        reasons.append(f"📰 <b>近期催化劑</b>：{' / '.join(_meaningful[:2])}")

    if not reasons:
        return ""

    bullets = "".join(f'<li style="margin-bottom:6px">{r}</li>' for r in reasons[:5])
    return (
        f'<div style="background:#050d1a;border:1px solid #1a3a6e;border-radius:8px;'
        f'padding:10px 14px;margin-bottom:12px">'
        f'<div style="font-size:12px;color:#7eb3ff;font-weight:700;margin-bottom:8px">'
        f'🔍 為什麼值得關注這支股票？</div>'
        f'<ul style="margin:0;padding-left:16px;color:#c0d4ff;font-size:12.5px;line-height:1.7">'
        f'{bullets}</ul></div>'
    )

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
        _mb = sres.get("macro_bonus", 0)
        _mb_str = f"　美股 {_mb:+d}" if _mb != 0 else ""
        _score_breakdown = (
            f'量能 {sres["vol_score"]}/30　動能 {sres["mom_score"]}/25　'
            f'技術 {sres["tech_score"]}/25　催化劑 {sres["cat_score"]}/30'
            f'{_mb_str}'
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
                st.session_state._needs_save = True
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
                st.session_state._needs_save = True
                st.rerun()

    if _clicked:
        if in_watch:
            st.session_state.watchlist.remove(ticker)
        else:
            if ticker not in st.session_state.watchlist:
                st.session_state.watchlist.append(ticker)
        st.session_state._needs_save = True
        st.rerun()

# ── Helpers & fragments (defined here so they're always available) ───────────

def _analyze_holding_with_live(df, live_price: float):
    """
    Injects today's live price as a synthetic 'today close' row and runs
    analyze_holding_sell() on the modified DataFrame so all signals
    (RSI, MACD, MA, resistance) reflect the CURRENT price, not yesterday's.
    """
    if df is None or len(df) < 22 or live_price <= 0:
        return analyze_holding_sell(df)
    try:
        df_live = df.copy()
        last_idx = df_live.index[-1]
        new_idx  = last_idx + pd.Timedelta(days=1)
        new_row  = pd.DataFrame({
            "Open":   [live_price],
            "High":   [max(float(df_live["High"].iloc[-1]), live_price)],
            "Low":    [min(float(df_live["Low"].iloc[-1]),  live_price)],
            "Close":  [live_price],
            "Volume": [float(df_live["Volume"].iloc[-1])],   # use yesterday vol as proxy
        }, index=[new_idx])
        return analyze_holding_sell(pd.concat([df_live, new_row]))
    except Exception:
        return analyze_holding_sell(df)


@st.fragment(run_every="10s")
def render_holdings_live(holdings_list: list, prices: dict, total_cost_: float):
    """
    Auto-refreshing holdings dashboard — every 10 s during market hours.
    Shows:
      • Portfolio hero card with live-updated total P&L
      • Per-stock row: live price · today's P&L · prominent HOLD / SELL signal
    """
    if not holdings_list:
        return

    _pov = [h for h in holdings_list
            if not h.get("error") and h.get("cost", 0) > 0 and h.get("shares", 0) > 0]
    if not _pov:
        return

    _tickers  = [h["ticker"] for h in _pov]
    _live     = fetch_live_prices(_tickers)
    _is_open  = _is_market_open()
    _badge_s  = "● 盤中即時" if _is_open else "收盤價"
    st.caption(f"💼 即時持股　{_badge_s}　更新：{_now_tw().strftime('%H:%M:%S')}　每10秒自動刷新")

    # ── Recompute totals with live prices ────────────────────────────────────
    def _lp(h):
        ld = _live.get(h["ticker"], {})
        p  = ld.get("price", 0) if ld else 0
        return p if p > 0 else h.get("price", 0)

    _live_val  = sum(h["shares"] * _lp(h) for h in _pov)
    _live_pnl  = _live_val - total_cost_ if total_cost_ > 0 else 0
    _live_pct  = (_live_pnl / total_cost_ * 100) if total_cost_ > 0 else 0
    _live_td   = sum(
        h["shares"] * _lp(h) * _live.get(h["ticker"], {}).get("chg_pct", h.get("chg",0))
        / (100 + _live.get(h["ticker"], {}).get("chg_pct", h.get("chg",0)))
        for h in _pov
        if abs(_live.get(h["ticker"], {}).get("chg_pct", h.get("chg",0))) < 99
    )

    _pc  = "#ef5350" if _live_pnl >= 0 else "#00c853"
    _pa  = "▲" if _live_pnl >= 0 else "▼"
    _tc  = "#ef5350" if _live_td >= 0 else "#00c853"
    _ta  = "▲" if _live_td >= 0 else "▼"
    _bh  = min(50.0, abs(_live_pct) / 20.0 * 50.0)
    _bsi = "left:50%;" if _live_pnl >= 0 else "right:50%;"
    _bra = "0 5px 5px 0" if _live_pnl >= 0 else "5px 0 0 5px"

    # ── Hero portfolio card ───────────────────────────────────────────────────
    st.markdown(
        f'<div class="card">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:14px">'
        f'<div><div style="font-size:11px;color:#555">總投入成本</div>'
        f'<div style="font-size:18px;font-weight:700;color:#e0e0e0">NT${total_cost_:,.0f}</div></div>'
        f'<div style="text-align:right">'
        f'<div style="font-size:11px;color:#555">即時市值</div>'
        f'<div style="font-size:18px;font-weight:700;color:#e0e0e0">NT${_live_val:,.0f}</div>'
        f'</div></div>'
        f'<div style="text-align:center;padding:10px 0 12px;'
        f'border-top:1px solid #252d45;border-bottom:1px solid #252d45">'
        f'<div style="font-size:11px;color:#777;letter-spacing:0.8px;margin-bottom:6px">總損益</div>'
        f'<div style="font-size:44px;font-weight:900;color:{_pc};line-height:1.05">'
        f'{_pa}&nbsp;NT${abs(_live_pnl):,.0f}</div>'
        f'<div style="font-size:22px;font-weight:700;color:{_pc};margin-top:2px">'
        f'{_pa}&nbsp;{abs(_live_pct):.2f}%</div>'
        f'</div>'
        f'<div style="margin:14px 0 4px">'
        f'<div style="position:relative;background:#1a1a2e;border-radius:5px;height:10px">'
        f'<div style="position:absolute;left:50%;top:0;width:2px;height:10px;background:#2a2a4a"></div>'
        f'<div style="position:absolute;{_bsi}width:{_bh:.1f}%;height:10px;'
        f'background:{_pc};border-radius:{_bra}"></div></div>'
        f'<div style="display:flex;justify-content:space-between;font-size:10px;'
        f'color:#3a3a5a;margin-top:4px"><span>← 虧損</span><span>損平點</span><span>獲利 →</span></div>'
        f'</div>'
        f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid #1a1a2e;'
        f'display:flex;justify-content:space-between;align-items:center">'
        f'<span style="font-size:12px;color:#555">今日損益</span>'
        f'<div>'
        f'<span style="font-size:15px;font-weight:700;color:{_tc}">'
        f'{_ta}&nbsp;NT${abs(_live_td):,.0f}</span>'
        f'<span style="font-size:12px;color:{_tc};margin-left:6px">'
        f'（{_ta}{abs(_live_td / (total_cost_ or 1) * 100):.2f}%）</span>'
        f'</div></div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # ── Per-stock rows: live price + hold/sell signal ─────────────────────────
    st.markdown(
        '<div style="font-size:13px;font-weight:600;color:#888;'
        'margin:14px 0 6px;letter-spacing:0.3px">個股損益 ＆ 操作建議</div>',
        unsafe_allow_html=True
    )

    for _h in sorted(_pov, key=lambda x: x.get("pnl_pct", 0), reverse=True):
        _t    = _h["ticker"]
        _code = _t.replace(".TW","")
        _name = _h["name"]
        _ld   = _live.get(_t, {})
        _lp_v = _ld.get("price", 0) if _ld else 0
        _use_lp = _lp_v if _lp_v > 0 else _h.get("price", 0)
        _lchg = _ld.get("chg_pct", _h.get("chg", 0)) if _ld else _h.get("chg", 0)

        _cost_v  = _h.get("cost", 0)
        _shr     = _h.get("shares", 0)
        _pnl_pct = (_use_lp / _cost_v - 1) * 100   if _cost_v > 0 else 0
        _pnl_amt = (_use_lp - _cost_v) * _shr       if _cost_v > 0 and _shr > 0 else 0
        _pc2 = "#ef5350" if _pnl_pct >= 0 else "#00c853"
        _pa2 = "▲" if _pnl_pct >= 0 else "▼"
        _lcc = "#ef5350" if _lchg >= 0 else "#00c853"
        _lca = "▲" if _lchg >= 0 else "▼"

        # ── Hold/sell signal ──────────────────────────────────────────────────
        _df_h = prices.get(_t)
        _sell = _analyze_holding_with_live(_df_h, _use_lp)
        if _sell:
            _urg = _sell.get("urgency", "低")
            _act = _sell.get("action", "繼續持有")
            _tgt = _sell.get("target_sell", 0)
            _stp = _sell.get("stop_loss", 0)
            _reasons = _sell.get("reasons", [])
            if _urg == "高":
                _sbg, _scl, _ico = "#2d0808", "#ef5350", "🔴"
            elif _urg == "中":
                _sbg, _scl, _ico = "#2a1800", "#ffd54f", "🟡"
            else:
                _sbg, _scl, _ico = "#071a07", "#00c853", "🟢"
        else:
            _urg, _act = "—", "資料不足"
            _tgt, _stp = 0, 0
            _reasons = []
            _sbg, _scl, _ico = "#0d1117", "#555", "⚫"

        _live_badge = (
            f'<span style="font-size:10px;background:#1a3a1a;color:#00c853;'
            f'border-radius:3px;padding:1px 5px;margin-left:4px">● LIVE</span>'
            if _is_open and _lp_v > 0 else ""
        )

        # Target & stop line (if data available)
        _ts_line = ""
        if _tgt > 0 and _stp > 0:
            _ts_line = (
                f'<div style="font-size:11px;color:#555;margin-top:4px">'
                f'🎯 目標 NT${_tgt}　　🛡 止損 NT${_stp}</div>'
            )

        # Primary reason (the single most important signal)
        _reason_line = ""
        if _reasons:
            _reason_line = (
                f'<div style="font-size:11px;color:{_scl};opacity:0.85;margin-top:3px">'
                f'{_reasons[0]}</div>'
            )

        st.markdown(
            f'<div style="background:#0e1117;border:1px solid #1e2235;'
            f'border-radius:10px;padding:12px 14px;margin-bottom:8px">'

            # Row 1: name + live price + today change
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'margin-bottom:6px">'
            f'<span style="font-size:15px;font-weight:700;color:#e0e0e0">'
            f'{_code}&nbsp;{_name}</span>'
            f'<div style="text-align:right">'
            f'<span style="font-size:18px;font-weight:800;color:{_lcc}">'
            f'NT${_use_lp:.1f}</span>{_live_badge}'
            f'<span style="font-size:12px;color:{_lcc};margin-left:5px">'
            f'{_lca}{abs(_lchg):.2f}%</span>'
            f'</div></div>'

            # Row 2: P&L vs cost
            f'<div style="display:flex;align-items:center;gap:8px;'
            f'font-size:12px;margin-bottom:8px">'
            f'<span style="color:#555">成本&nbsp;NT${_cost_v:.1f}</span>'
            f'<span style="color:#333">→</span>'
            f'<span style="font-size:15px;font-weight:800;color:{_pc2}">'
            f'{_pa2}&nbsp;{abs(_pnl_pct):.1f}%</span>'
            f'<span style="font-size:12px;color:{_pc2}">'
            f'NT${_pa2}{abs(_pnl_amt):,.0f}</span>'
            f'</div>'

            # Row 3: HOLD/SELL signal badge
            f'<div style="background:{_sbg};border:1px solid {_scl}44;'
            f'border-left:4px solid {_scl};border-radius:0 8px 8px 0;'
            f'padding:8px 12px;margin-bottom:0">'
            f'<div style="font-size:13px;font-weight:700;color:{_scl}">'
            f'{_ico}&nbsp;{_act}</div>'
            f'{_reason_line}'
            f'{_ts_line}'
            f'</div>'

            f'</div>',
            unsafe_allow_html=True
        )


@st.cache_data(ttl=180, show_spinner=False)
def _fetch_alerts_cached():
    """Cache RSS fetch results for 3 min so multiple simultaneous users share one poll."""
    return fetch_market_alerts(hours_back=6)


@st.fragment(run_every="180s")
def render_news_alerts():
    """
    Polls breaking-news RSS every 3 minutes.
    • Shows a red/orange sticky banner for critical/high alerts.
    • Fires a browser push notification for each NEW critical alert
      (if the user granted permission via the sidebar button).
    • 'Snooze 1 hour' button to hide the banner without missing future alerts.
    """
    now_ts = _now_tw().timestamp()
    if now_ts < st.session_state.alert_snoozed:
        return   # user snoozed for 1 h

    alerts = _fetch_alerts_cached()
    if not alerts:
        return

    critical = [a for a in alerts if a["severity"] == "critical"]
    high     = [a for a in alerts if a["severity"] == "high"]
    all_shown = (critical + high)[:5]

    if not all_shown:
        return

    # ── Banner ──────────────────────────────────────────────────────────────
    for a in all_shown:
        sev    = a["severity"]
        bg     = "#2d0808" if sev == "critical" else "#2a1500"
        border = "#ef5350" if sev == "critical" else "#ff9800"
        icon   = "🚨" if sev == "critical" else "⚠️"
        label  = "重大危機" if sev == "critical" else "市場警示"
        am     = a["age_min"]
        age_s  = f"{am}分鐘前" if am > 0 else "剛發布"
        st.markdown(
            f'<div style="background:{bg};border:1px solid {border};'
            f'border-left:5px solid {border};border-radius:8px;'
            f'padding:10px 16px;margin:3px 0">'
            f'<div style="color:{border};font-size:11px;font-weight:700;'
            f'letter-spacing:0.5px">{icon} {label}'
            f'　<span style="color:#666;font-weight:400">'
            f'{a["source"]}　{age_s}</span></div>'
            f'<div style="color:#f0f0f0;font-size:14px;margin-top:4px;'
            f'line-height:1.45">{a["title"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    _snz_col, _ = st.columns([3, 7])
    if _snz_col.button("✓ 已知悉，暫時隱藏 (1小時)", key="snooze_alerts"):
        st.session_state.alert_snoozed = now_ts + 3600
        st.rerun()

    # ── Browser push notification for NEW critical alerts ─────────────────
    new_crit = [a for a in critical
                if a["alert_id"] not in st.session_state.seen_alert_ids]
    for a in new_crit[:3]:
        st.session_state.seen_alert_ids.add(a["alert_id"])
        # Escape for JS string literal
        _t = a["title"].replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        _s = a["source"].replace("'", "\\'")
        _id = a["alert_id"]
        st_javascript(f"""(
            typeof Notification !== 'undefined' && Notification.permission === 'granted'
            ? new Notification('🚨 市場緊急警報', {{
                body: '{_t}',
                tag:  'tw-alert-{_id}',
                requireInteraction: true
              }})
            : null, 1)""")


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
                st.session_state._needs_save = True
                st.rerun()

# ── Breaking-news alert banner (runs every 3 min, shown in all views) ────────
render_news_alerts()

# ── Market index bar + minimalist refresh ────────────────────────────────────
_mi_col, _ref_col = st.columns([11, 1])
with _mi_col:
    if mkt:
        idx_val = mkt.get("index", "—")
        idx_chg = mkt.get("change", "—")
        is_up   = not str(idx_chg).startswith("-")
        mkt_col = "#ef5350" if is_up else "#00c853"
        _slot_label, _next_upd = _epoch_slot_info()
        _epoch_date = _epoch.split("-")[:3]   # ["YYYY", "MM", "DD"]
        _epoch_ymd  = "-".join(_epoch_date)
        st.markdown(
            f'<span style="color:#888;font-size:13px">加權指數　</span>'
            f'<span style="font-size:16px;font-weight:700;color:#f0f0f0">{idx_val}</span>'
            f'　<span style="color:{mkt_col};font-size:14px">{idx_chg}</span>'
            f'　<span style="color:#555;font-size:12px">｜　'
            f'<span style="color:#7eb3ff;font-weight:600">{_slot_label}</span>'
            f'　{_epoch_ymd} {data["ts"]}'
            f'　｜　下次 {_next_upd}'
            f'　｜　漲停 ±10%</span>',
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
                _code = _rt.replace('.TW','').replace('.TWO','')
                # Hint: codes 30xx-39xx / 40xx-49xx are often 興櫃 (emerging),
                # codes starting with 9 are sometimes special-purpose
                _hint = ""
                if _code.isdigit() and len(_code) == 4:
                    _n = int(_code)
                    if 3000 <= _n <= 3999 or 4000 <= _n <= 4999:
                        _hint = "（提示：部分3xxx/4xxx為興櫃股，yfinance不支援興櫃）"
                _hint_html = (f'<br><span style="font-size:11px;color:#777">{_hint}</span>'
                              if _hint else "")
                st.markdown(
                    f'<div style="background:#1a0a0a;border-left:3px solid #c0392b;'
                    f'border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:8px;font-size:13px">'
                    f'❌ <b>{_code}</b> 查無資料——可能是：'
                    f'<span style="color:#aaa">代號錯誤 ／ 興櫃股（yfinance不支援）'
                    f' ／ 已下市 ／ 上市未滿1個月</span>'
                    f'{_hint_html}</div>',
                    unsafe_allow_html=True
                )
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

# ── Category cards fragment (must be defined BEFORE the category view block) ──
# Separate function from render_stock_cards to avoid Streamlit fragment-identity
# conflicts when both picks-view and category-view could call the same fragment.
@st.fragment(run_every="10s")
def render_category_cards(picks, prices, show_chart):
    """Live-refreshing stock cards for the category picks view."""
    tickers  = [p["ticker"] for p in picks]
    live     = fetch_live_prices(tickers)
    is_open  = _is_market_open()
    refresh  = "每10秒更新 ●" if is_open else "非交易時段"
    st.caption(f"📡 即時股價　{refresh}　　更新：{_now_tw().strftime('%H:%M:%S')}　｜　零股盤中 09:00–13:30 ／ 盤後 14:00–14:30")

    for rank, p in enumerate(picks, 1):
        sc         = p["score"]
        bar_color  = conf_color(sc)
        vr         = p["vol_ratio"]
        fi         = p["foreign_net"]
        cats       = p.get("catalysts") or ["技術面分析"]
        cat_str    = "　".join(cats)
        rsi        = p.get("rsi", 50)

        if rsi <= 72 and sc >= 65:
            acq = "✅ 今日可進場：分批零股買入"
        elif rsi <= 72 and sc >= 45:
            acq = "🟡 今日可小量試探：先買三成"
        elif rsi > 72:
            acq = f"⏳ RSI {rsi:.0f} 偏熱，等回落至 68 以下再進場"
        else:
            acq = "👀 觀察中：等量能與趨勢確認"

        if   fi > 100:  fi_str = f"外資買超 {fi:.0f}千張 📥"
        elif fi < -100: fi_str = f"外資賣超 {abs(fi):.0f}千張 📤"
        else:           fi_str = ""

        info_parts = [
            f'量比 <span class="info-val {"up" if vr>=1.5 else ""}">{vr:.1f}x</span>',
            f'RSI <span class="info-val">{rsi:.0f}</span>',
            f'5日 <span class="info-val {"up" if p["mom5d"]>=0 else "down"}">{p["mom5d"]:+.1f}%</span>',
        ]
        if fi_str:
            info_parts.append(f'<span class="{"up" if fi>0 else "down"}">{fi_str}</span>')

        # Live price block
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
            if is_limit:     status_tag = '<span class="limit-up">漲停🔥</span>'
            elif near_limit: status_tag = '<span class="limit-near">近漲停⚡</span>'
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
            lp = p["last_price"]
            chg_pct = 0
            live_block = '<div class="live-in-card"><span style="color:#555">等待開盤資料…</span></div>'

        # Near-limit-up safety override
        _live_chg_now = chg_pct
        if _live_chg_now >= 9.0:
            acq = (f"🚫 今日已漲 {_live_chg_now:.1f}%，接近漲停——"
                   f"現在進場是散戶常見陷阱，等明日 RSI 冷卻後再評估")
        elif _live_chg_now >= 7.0:
            acq = (f"⚠️ 今日已大漲 {_live_chg_now:.1f}%——追高風險極高。"
                   f"建議等股價回落、RSI 冷卻至 65 以下再考慮進場")

        ref_price  = (d["price"] if d and d["price"] > 0 else p["last_price"])
        shares_10k = int(10000 / ref_price) if ref_price > 0 else 0
        bar_w      = int(sc)
        info_html  = '　'.join(f'<span>{x}</span>' for x in info_parts)

        # Watchlist star button
        _in_w = p["ticker"] in st.session_state.watchlist
        _star = "★" if _in_w else "☆"
        _scol = "#ffd54f" if _in_w else "#888"
        _, _sc2 = st.columns([10, 1])
        with _sc2:
            st.markdown('<span class="star-sentinel"></span>', unsafe_allow_html=True)
            _star_clicked = st.button(_star, key=f"star_cat_{p['ticker']}", use_container_width=True, help="追蹤")

        # Score label
        _score_html = f'<div style="font-size:11px;color:#555;margin-top:3px">類別評分 {sc}/100</div>'

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
            + _build_fund_row(p)
            + f'<div class="catalyst">📌 {cat_str}</div>'
            f'<div class="{"near-limit-warn" if _live_chg_now >= 7.0 else "sell-note"}">{acq}</div>'
            f'<div class="conf-wrap"><div class="conf-bar" style="width:{bar_w}%;background:{bar_color}"></div></div>'
            f'{_score_html}'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Watchlist update
        if _star_clicked:
            if _in_w:
                st.session_state.watchlist = [t for t in st.session_state.watchlist if t != p["ticker"]]
            else:
                if p["ticker"] not in st.session_state.watchlist:
                    st.session_state.watchlist.append(p["ticker"])
            st.session_state._needs_save = True
            st.rerun()

        # Beginner advice
        _ref  = d["price"] if d and d["price"] > 0 else p["last_price"]
        _adv  = get_beginner_advice(prices.get(p["ticker"]), _ref)
        if _adv:
            _rsi_pct = min(100, max(0, _adv["rsi"]))
            _rsi_col = _adv["rsi_col"]
            with st.expander(f"💡 {p['ticker'].replace('.TW','')} 新手建議（點擊展開）", expanded=False):
                st.markdown(
                    f'<div class="advice-box">'
                    f'<div class="advice-title">💡 新手操作建議</div>'
                    + _build_why_buy(p)
                    +
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
                    f'<div class="advice-row" style="margin-top:10px">'
                    f'  <span class="advice-label">📈 趨勢</span>'
                    f'  <span style="color:{_adv["trend_col"]};font-weight:700">'
                    f'    {_adv["trend_icon"]} {_adv["trend"]}'
                    f'  </span>'
                    f'</div>'
                    f'<div class="advice-row" style="margin-top:8px">'
                    f'  <span class="advice-label">💡 建議</span>'
                    f'  <span style="font-size:13px;color:#c0d4ff">{_adv["buy_note"]}</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        if show_chart:
            _df_c = prices.get(p["ticker"])
            if _df_c is not None and len(_df_c) >= 10:
                import plotly.graph_objects as go
                from plotly.subplots import make_subplots
                _fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                     row_heights=[0.7, 0.3], vertical_spacing=0.03)
                _fig.add_trace(go.Candlestick(
                    x=_df_c.index, open=_df_c["Open"], high=_df_c["High"],
                    low=_df_c["Low"], close=_df_c["Close"],
                    increasing_line_color="#ef5350", decreasing_line_color="#00c853",
                    name="K線"), row=1, col=1)
                _fig.add_trace(go.Bar(
                    x=_df_c.index, y=_df_c["Volume"],
                    marker_color="#1a56db44", name="成交量"), row=2, col=1)
                _fig.update_layout(
                    height=320, margin=dict(l=0, r=0, t=8, b=0),
                    paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                    xaxis_rangeslider_visible=False, showlegend=False,
                    font=dict(color="#888", size=10),
                )
                _fig.update_xaxes(gridcolor="#1a1a2e", showgrid=True)
                _fig.update_yaxes(gridcolor="#1a1a2e", showgrid=True)
                st.plotly_chart(_fig, use_container_width=True, config={"displayModeBar": False})

# ── Main view: Category Picks ─────────────────────────────────────────────────
if st.session_state.view_mode == "categories":

    # ── Inline category dropdown ───────────────────────────────────────────────
    _cat_keys = list(CATEGORY_UNIVERSE.keys())
    _cur_idx  = _cat_keys.index(st.session_state.selected_category) if st.session_state.selected_category in _cat_keys else 0
    _main_sel = st.selectbox(
        "選擇產業類別",
        options=_cat_keys,
        index=_cur_idx,
        format_func=lambda k: f"{CATEGORY_UNIVERSE[k]['emoji']} {CATEGORY_UNIVERSE[k]['name']}",
        key="main_cat_select",
    )
    if _main_sel != st.session_state.selected_category:
        st.session_state.selected_category = _main_sel
        st.rerun()

    _sel_cat = st.session_state.selected_category
    _cinfo   = CATEGORY_UNIVERSE.get(_sel_cat, next(iter(CATEGORY_UNIVERSE.values())))

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f"## {_cinfo['emoji']} {_cinfo['name']}　"
        f"<span style='font-size:12px;background:#1e2740;color:#7eb3ff;"
        f"border-radius:5px;padding:2px 8px;vertical-align:middle'>"
        f"{_cinfo['en']}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="font-size:13px;color:#777;margin:2px 0 6px">{_cinfo["desc"]}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="background:#0d1f3c;border-left:3px solid #1a56db;border-radius:0 8px 8px 0;'
        f'padding:8px 12px;font-size:13px;color:#c0d4ff;margin-bottom:16px">'
        f'💡 {_cinfo["why"]}</div>',
        unsafe_allow_html=True,
    )

    # ── Load prices for this category (cached per epoch slot) ─────────────────
    with st.spinner(f"載入 {_cinfo['name']} 價格資料…"):
        _cat_prices = load_category_prices(_sel_cat, _epoch)

    # ── Score every ticker in the universe using already-loaded context ────────
    # Same scoring formula as the main picks loop: score_stock → RSI adj → live update
    _cat_scored = []
    for _ct in _cinfo["tickers"]:
        _cdf = _cat_prices.get(_ct)
        if _cdf is None or len(_cdf) < 22:
            continue
        _cres = score_stock(_ct, _cdf, cat_sc.get(_ct, 0), foreign.get(_ct, 0),
                            us_macro_stock_bonus(_ct, us_data))
        if not _cres:
            continue
        # Zero-stock RSI + price adjustments (identical to main picks loop)
        _cadj = 0
        _crsi = _cres.get("rsi", 50)
        if   _crsi > 82:  _cadj -= 30
        elif _crsi > 78:  _cadj -= 20
        elif _crsi > 72:  _cadj -= 12
        elif _crsi > 68:  _cadj -=  4
        elif _crsi >= 45: _cadj +=  8
        elif _crsi >= 35: _cadj +=  3
        else:             _cadj -= 15
        if _cres.get("last_price", 0) > 500: _cadj -= 8
        _cres["score"]       = max(0, min(100, _cres["score"] + _cadj))
        _cres["_rsi_adj"]    = _cadj
        # ── 基本面加權 ────────────────────────────────────────────────────────
        _cfd = calc_fundamental_bonus(_ct, fund_map, meeting_map)
        _cres["score"]        = max(0, min(100, _cres["score"] + _cfd["bonus"]))
        _cres["rev_yoy"]      = _cfd["rev_yoy"]
        _cres["earn_yoy"]     = _cfd["earn_yoy"]
        _cres["fund_labels"]  = _cfd["labels"]
        _cres["trailing_eps"] = _cfd.get("trailing_eps")
        _cres["forward_eps"]  = _cfd.get("forward_eps")
        _cres["forward_pe"]   = _cfd.get("forward_pe")
        _cres["catalysts"]    = (_cfd["labels"] + get_catalyst_labels(_ct, all_news))[:4]
        _cres["is_new"]      = False
        _cres["score_delta"] = None
        _cat_scored.append(_cres)

    # ── Live intraday scoring (market hours) — same 3-layer guard as main picks ─
    if _is_market_open() and _cat_scored:
        _cl_tickers = [r["ticker"] for r in _cat_scored]
        _cl_live    = fetch_live_prices(_cl_tickers)
        for _cr in _cat_scored:
            _cld = _cl_live.get(_cr["ticker"], {})
            _clp = _cld.get("price", 0) if _cld else 0
            if _clp <= 0:
                continue
            _cdf2 = _cat_prices.get(_cr["ticker"])
            # 1. Live RSI
            if _cdf2 is not None and len(_cdf2) >= 15:
                _cn_rsi = round(calc_live_rsi(_cdf2, _clp), 1)
                _co_rsi = _cr.get("rsi", 50)
                if abs(_cn_rsi - _co_rsi) >= 0.5:
                    _co_adj = _cr.pop("_rsi_adj", 0)
                    _cn_adj = 0
                    if   _cn_rsi > 82:  _cn_adj -= 30
                    elif _cn_rsi > 78:  _cn_adj -= 20
                    elif _cn_rsi > 72:  _cn_adj -= 12
                    elif _cn_rsi > 68:  _cn_adj -=  4
                    elif _cn_rsi >= 45: _cn_adj +=  8
                    elif _cn_rsi >= 35: _cn_adj +=  3
                    else:               _cn_adj -= 15
                    _cr["score"] = max(0, min(100, _cr["score"] - _co_adj + _cn_adj))
                    _cr["rsi"]   = _cn_rsi
            # 2. Live mom1d
            _cl_prev = _cld.get("prev", 0)
            if _cl_prev > 0:
                _cl_mom = (_clp / _cl_prev - 1) * 100
                _co_mom = _cr.get("mom1d", 0)
                if abs(_cl_mom - _co_mom) >= 0.3:
                    _co_ms = min(10, max(0, _co_mom * 2))
                    _cn_ms = min(10, max(0, _cl_mom * 2))
                    _cr["score"] = max(0, min(100, _cr["score"] + (_cn_ms - _co_ms)))
                    _cr["mom1d"] = round(_cl_mom, 2)
            # 3. Near-limit-up guard
            _cl_chg = round(_cld.get("chg_pct", 0), 2)
            _cr["live_chg_pct"] = _cl_chg
            if _cl_chg >= 9.0:
                _cr["score"]      = max(0, _cr["score"] - 45)
                _cr["near_limit"] = True
            elif _cl_chg >= 7.0:
                _cr["score"]      = max(0, _cr["score"] - 22)
                _cr["near_limit"] = True

    _cat_scored.sort(key=lambda x: x["score"], reverse=True)
    # Category view: show top 5 by score regardless of absolute threshold —
    # the user chose this category intentionally.  Only hard-filter:
    #   • RSI ≥ 73  (technically overbought — wait for pullback)
    #   • live_chg ≥ 9%  (near limit-up — dangerous to chase)
    # Score threshold dropped to 20 (vs 52 for main picks) so hot sectors
    # (e.g. all foundry stocks overbought) still yield picks + a warning.
    # Show top-5 by score. Only hard-filter near-limit-up (≥9%) — dangerous to chase.
    # RSI overbought is handled via card advice text (⏳ wait for pullback), NOT filtering.
    _cat_picks = [r for r in _cat_scored
                  if r.get("live_chg_pct", 0) < 9.0][:5]

    # ── Sector momentum summary bar ───────────────────────────────────────────
    _avg_rsi, _avg_mom5, _avg_mom1, _n_hot = 50.0, 0.0, 0.0, 0  # safe defaults
    if _cat_scored:
        _n_sample  = min(len(_cat_scored), 8)
        _avg_rsi   = round(sum(p["rsi"]   for p in _cat_scored[:_n_sample]) / _n_sample, 1)
        _avg_mom5  = round(sum(p["mom5d"] for p in _cat_scored[:_n_sample]) / _n_sample, 1)
        _avg_mom1  = round(sum(p["mom1d"] for p in _cat_scored[:_n_sample]) / _n_sample, 2)
        _rsi_emoji = "🔥" if _avg_rsi > 68 else ("✅" if _avg_rsi >= 40 else "📉")
        _rsi_label = "偏熱，需謹慎" if _avg_rsi > 68 else ("適中，可進場" if _avg_rsi >= 40 else "偏冷，觀察中")
        _n_hot     = sum(1 for p in _cat_scored if p.get("near_limit"))
        st.markdown(
            f'<div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;align-items:stretch">'
            # RSI tile
            f'<div style="background:#0a0f1a;border-radius:8px;padding:10px 16px;min-width:120px">'
            f'<div style="font-size:10px;color:#555;margin-bottom:2px">板塊平均 RSI</div>'
            f'<div style="font-size:18px;font-weight:700;color:#e0e0e0">{_avg_rsi}'
            f' <span style="font-size:12px">{_rsi_emoji}</span></div>'
            f'<div style="font-size:11px;color:#666">{_rsi_label}</div>'
            f'</div>'
            # 5d momentum tile
            f'<div style="background:#0a0f1a;border-radius:8px;padding:10px 16px;min-width:120px">'
            f'<div style="font-size:10px;color:#555;margin-bottom:2px">5日板塊動能</div>'
            f'<div style="font-size:18px;font-weight:700;'
            f'color:{"#ef5350" if _avg_mom5>=0 else "#00c853"}">{_avg_mom5:+.1f}%</div>'
            f'<div style="font-size:11px;color:#666">近5個交易日均漲跌</div>'
            f'</div>'
            # Today tile
            f'<div style="background:#0a0f1a;border-radius:8px;padding:10px 16px;min-width:120px">'
            f'<div style="font-size:10px;color:#555;margin-bottom:2px">今日板塊表現</div>'
            f'<div style="font-size:18px;font-weight:700;'
            f'color:{"#ef5350" if _avg_mom1>=0 else "#00c853"}">{_avg_mom1:+.2f}%</div>'
            f'<div style="font-size:11px;color:#666">{"盤中即時" if _is_market_open() else "昨日收盤"}</div>'
            f'</div>'
            # Near-limit warning tile (only if relevant)
            + (f'<div style="background:#1a0505;border:1px solid #c0392b;border-radius:8px;'
               f'padding:10px 16px;min-width:120px">'
               f'<div style="font-size:10px;color:#c0392b;margin-bottom:2px">⚠️ 近漲停已排除</div>'
               f'<div style="font-size:18px;font-weight:700;color:#ff5252">{_n_hot} 檔</div>'
               f'<div style="font-size:11px;color:#666">已自動過濾，不建議追高</div>'
               f'</div>'
               if _n_hot > 0 else "")
            + f'</div>',
            unsafe_allow_html=True,
        )

    # ── Render picks or empty state ───────────────────────────────────────────
    if _cat_picks:
        render_category_cards(_cat_picks, _cat_prices, show_chart)
    else:
        st.warning(
            f"目前 **{_cinfo['name']}** 沒有符合條件的推薦。\n\n"
            f"可能原因：整個板塊 RSI 過熱（>{_avg_rsi:.0f}），或評分不足。\n"
            f"建議：等板塊回落後再看，或在左側調低「最低評分門檻」。"
        )

    st.divider()
    with st.expander("📰 今日早盤新聞", expanded=False):
        for h in data["headlines"][:8]:
            st.markdown(f'<div class="news-line">{h}</div>', unsafe_allow_html=True)
    st.stop()

# ── Main view: Holdings ───────────────────────────────────────────────────────
if st.session_state.view_mode == "holdings":
    st.markdown(
        "## 💼 我的持股　"
        "<span style='font-size:12px;background:#0d2a4a;color:#7eb3ff;"
        "border-radius:5px;padding:2px 8px;vertical-align:middle'>"
        "盤中每10秒自動更新</span>",
        unsafe_allow_html=True
    )

    _has_cost = any(
        h.get("cost", 0) > 0 and h.get("shares", 0) > 0
        for h in holdings_info if not h.get("error")
    )

    if _has_cost and total_cost > 0:
        # ── Live hero card + per-stock rows + hold/sell signals (auto-refresh) ─
        render_holdings_live(holdings_info, prices, total_cost)
    elif holdings_info:
        st.info("💡 點選下方「＋ 新增 / 編輯持股」輸入買進均價和股數，即可看到完整損益總覽")

    st.divider()
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
                    st.session_state._needs_save = True
                    st.rerun()
                except ValueError:
                    st.error("請輸入有效數字")

        for _ht, _hv in list(st.session_state.custom_holdings.items()):
            _hd1, _hd2 = st.columns([4, 1])
            _hd1.caption(f"{_ht.replace('.TW','')}　{_hv['shares']:.0f}股　成本 {_hv['cost']:.1f}")
            if _hd2.button("✕", key=f"hp_del_{_ht}"):
                del st.session_state.custom_holdings[_ht]
                st.session_state._needs_save = True
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
                    st.session_state._needs_save = True
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
_slot_lbl, _next_lbl = _epoch_slot_info()
_is_mkt_open = _is_market_open()
_freshness_col  = "#00c853" if _is_mkt_open else "#555"
_freshness_icon = "🟢" if _is_mkt_open else "⚫"
_live_rsi_note  = "　●　已套用即時RSI" if _is_mkt_open else ""

st.markdown(
    "## ✅ 今日可進場股　"
    "<span style='font-size:12px;background:#1a3a5c;color:#7eb3ff;border-radius:5px;padding:2px 8px;vertical-align:middle'>"
    "RSI 合理區間・零股小資</span>",
    unsafe_allow_html=True
)
st.markdown(
    f'<div style="background:#0a0f1a;border:1px solid #1a2035;border-radius:8px;'
    f'padding:8px 14px;margin:-4px 0 12px;display:flex;align-items:center;gap:10px">'
    f'<span style="font-size:11px;color:{_freshness_col}">{_freshness_icon}</span>'
    f'<span style="font-size:12px;color:#7eb3ff;font-weight:700">{_slot_lbl}</span>'
    f'<span style="font-size:12px;color:#555">'
    f'　分析時間：{data["ts"]}　｜　下次更新：{_next_lbl}{_live_rsi_note}'
    f'</span>'
    f'<span style="margin-left:auto;font-size:11px;color:#333">'
    f'今日精選由系統自動計算，每個時段重新評分排序</span>'
    f'</div>',
    unsafe_allow_html=True
)

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

        rsi = p.get("rsi", 50)
        if rsi <= 72 and sc >= 65:
            acq = "✅ 今日可進場：分批零股買入"
        elif rsi <= 72 and sc >= 52:
            acq = "🟡 今日可小量試探：先買三成"
        elif rsi > 72:
            acq = f"⏳ RSI {rsi:.0f} 偏熱，等回落至 68 以下再進場"
        else:
            acq = "👀 觀察中：等量能與趨勢確認"

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

        # ── Live near-limit-up safety guard (fragment-level, overrides scored acq) ──
        # The main body scoring only runs on user interaction, NOT every 10 seconds.
        # A stock scored fine at 9 AM might be at +8% by 10 AM.
        # Without this override, the card would show +8% live price AND "✅ 今日可進場" —
        # a dangerous contradiction that could cause the user to chase.
        _live_chg_now = d["chg_pct"] if d and d["price"] > 0 else 0
        if _live_chg_now >= 9.0:
            acq = (f"🚫 今日已漲 {_live_chg_now:.1f}%，接近漲停——"
                   f"現在進場是散戶常見陷阱，等明日 RSI 冷卻後再評估")
        elif _live_chg_now >= 7.0:
            acq = (f"⚠️ 今日已大漲 {_live_chg_now:.1f}%——追高風險極高。"
                   f"建議等股價回落、RSI 冷卻至 65 以下再考慮進場")

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

        # Score delta vs previous slot
        _sdelta = p.get("score_delta")
        if _sdelta is not None and abs(_sdelta) >= 1:
            _sd_col = "#ef5350" if _sdelta > 0 else "#00c853"
            _sd_arr = "↑" if _sdelta > 0 else "↓"
            _score_delta_html = (
                f'<div style="font-size:11px;color:#555;margin-top:3px">'
                f'信心指數 {sc}/100'
                f'　<span style="color:{_sd_col};font-weight:700">{_sd_arr}{abs(_sdelta):.0f}</span>'
                f'　<span style="color:#333">vs 上一時段</span>'
                f'</div>'
            )
        else:
            _score_delta_html = (
                f'<div style="font-size:11px;color:#555;margin-top:3px">信心指數 {sc}/100</div>'
            )

        _is_new_pick = p.get("is_new", False)
        _new_badge   = (
            '<span style="background:#1a4a1a;color:#00c853;font-size:10px;'
            'font-weight:700;border:1px solid #00c85366;border-radius:4px;'
            'padding:2px 6px;margin-left:6px">🆕 新進榜</span>'
            if _is_new_pick else ""
        )
        st.markdown(
            f'<div style="margin-top:-3rem;pointer-events:none">'
            f'<div class="card">'
            f'<div class="card-top">'
            f'<div class="rank">{rank}</div>'
            f'<span class="stock-name">{p["ticker"].replace(".TW","")} {p["name"]}</span>'
            f'{_new_badge}'
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
            + _build_fund_row(p)
            + f'<div class="catalyst">📌 {cat_str}</div>'
            f'<div class="{"near-limit-warn" if _live_chg_now >= 7.0 else "sell-note"}">{acq}</div>'
            f'<div class="conf-wrap"><div class="conf-bar" style="width:{bar_w}%;background:{bar_color}"></div></div>'
            f'{_score_delta_html}'
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
                    + _build_why_buy(p)
                    +

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
            st.session_state._needs_save = True
            st.rerun()

if not today_picks:
    st.info(
        "🌡️ **今日市場偏熱，暫無理想進場點。**\n\n"
        "多數科技股 RSI 超過 72，追高風險大。\n"
        "建議等待回調再進場，或查看下方「準備中」名單。",
    )
else:
    render_stock_cards(today_picks, prices, show_chart)

# ── 準備中：RSI偏熱，觀察等回落 ──────────────────────────────────────────────
if watch_picks:
    st.divider()
    with st.expander(f"👀 準備中・等 RSI 回落（{len(watch_picks)} 支）", expanded=False):
        st.caption("這些股票體質不錯但 RSI 偏熱，等回落至 68 以下再考慮進場")
        render_stock_cards(watch_picks, prices, show_chart)

# ── 備選股 toggle ─────────────────────────────────────────────────────────────
backups = [r for r in scored if r not in today_picks and r not in watch_picks and r["score"] >= 45][: 5]
if backups:
    if "show_backups" not in st.session_state:
        st.session_state.show_backups = False

    label = "▲ 收起備選股" if st.session_state.show_backups else "＋ 查看更多備選（觀察用）"
    if st.button(label, use_container_width=True):
        st.session_state.show_backups = not st.session_state.show_backups
        st.rerun()

    if st.session_state.show_backups:
        st.caption("備選股僅供觀察，建議等待更佳進場訊號後再考慮")
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
