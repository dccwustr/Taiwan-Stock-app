#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣科技股盤前分析系統 v1.0
Taiwan Tech Stock Pre-Market Analysis Widget
晶片・記憶體・AI — NVIDIA / AMD / Apple 上游供應鏈深度追蹤
每日早上 8:00 執行，分析最有可能大漲的5支股票
"""

import sys, re, json, time, warnings, argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False
    print("請安裝 yfinance: pip3 install yfinance")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    from rich.rule import Rule
    from rich.columns import Columns
    from rich.align import Align
    from rich.progress import Progress, SpinnerColumn, TextColumn
except ImportError:
    print("請安裝 rich: pip3 install rich")
    sys.exit(1)

console = Console(width=130)

# ═══════════════════════════════════════════════════════════════════════════════
#  持股設定
# ═══════════════════════════════════════════════════════════════════════════════
MY_HOLDINGS = {}

# ═══════════════════════════════════════════════════════════════════════════════
#  股票池：台灣科技股（晶片・記憶體・AI）
# ═══════════════════════════════════════════════════════════════════════════════
TECH_UNIVERSE: Dict[str, Dict] = {
    # ── 晶圓代工 Foundry ────────────────────────────────────────────────────
    "2330.TW": {"name":"台積電",   "en":"TSMC",           "sector":"晶圓代工",  "supply":["NVIDIA","AMD","Apple","AI","CoWoS"]},
    "2303.TW": {"name":"聯電",     "en":"UMC",            "sector":"晶圓代工",  "supply":[]},
    "5347.TW": {"name":"世界先進", "en":"Vanguard Semi",  "sector":"晶圓代工",  "supply":[]},
    "6770.TW": {"name":"力積電",   "en":"PSMC",           "sector":"晶圓代工",  "supply":[]},
    # ── IC設計 Fabless ──────────────────────────────────────────────────────
    "2454.TW": {"name":"聯發科",   "en":"MediaTek",       "sector":"IC設計",    "supply":["AI","AMD"]},
    "3034.TW": {"name":"聯詠",     "en":"Novatek",        "sector":"IC設計",    "supply":["Apple"]},
    "2379.TW": {"name":"瑞昱",     "en":"Realtek",        "sector":"IC設計",    "supply":[]},
    "6415.TW": {"name":"矽力-KY",  "en":"Silergy",        "sector":"IC設計",    "supply":["AI"]},
    "3529.TW": {"name":"力旺",     "en":"eMemory",        "sector":"記憶體IP",  "supply":["AI"]},
    "2458.TW": {"name":"義隆電",   "en":"Elan Micro",     "sector":"IC設計",    "supply":["Apple"]},
    "2401.TW": {"name":"凌陽",     "en":"Sunplus",        "sector":"IC設計",    "supply":[]},
    # ── 記憶體 Memory ───────────────────────────────────────────────────────
    "2344.TW": {"name":"華邦電",   "en":"Winbond",        "sector":"記憶體",    "supply":[]},
    "2408.TW": {"name":"南亞科",   "en":"Nanya Tech",     "sector":"DRAM",      "supply":[]},
    "8299.TW": {"name":"群聯",     "en":"Phison",         "sector":"NAND控制器","supply":["AI"]},
    # ── 先進封裝 / 封測 Packaging ───────────────────────────────────────────
    "3711.TW": {"name":"日月光投控","en":"ASE Technology", "sector":"封測",     "supply":["NVIDIA","AMD","Apple","CoWoS"]},
    "2449.TW": {"name":"京元電子", "en":"KYEC",           "sector":"IC測試",    "supply":[]},
    # ── IC載板 / PCB ────────────────────────────────────────────────────────
    "3037.TW": {"name":"欣興",     "en":"Unimicron",      "sector":"IC載板",    "supply":["NVIDIA","AMD","CoWoS"]},
    "3044.TW": {"name":"健鼎",     "en":"Tripod Tech",    "sector":"PCB",       "supply":["NVIDIA","AI"]},
    # ── AI伺服器 / ODM ──────────────────────────────────────────────────────
    "6669.TW": {"name":"緯穎",     "en":"Wiwynn",         "sector":"AI伺服器",  "supply":["NVIDIA","AI"]},
    "2382.TW": {"name":"廣達",     "en":"Quanta",         "sector":"伺服器ODM", "supply":["NVIDIA","AI","Apple"]},
    "3231.TW": {"name":"緯創",     "en":"Wistron",        "sector":"ODM",       "supply":["Apple","AI"]},
    "4938.TW": {"name":"和碩",     "en":"Pegatron",       "sector":"ODM",       "supply":["Apple"]},
    "2317.TW": {"name":"鴻海",     "en":"Foxconn",        "sector":"EMS/ODM",   "supply":["Apple","NVIDIA","AI"]},
    # ── 被動元件 Passive Components ─────────────────────────────────────────
    "2327.TW": {"name":"國巨",     "en":"Yageo",          "sector":"被動元件",  "supply":["NVIDIA","Apple"]},
    "2492.TW": {"name":"華新科",   "en":"Walsin Tech",    "sector":"被動元件",  "supply":[]},
    # ── 光學 Optics ─────────────────────────────────────────────────────────
    "3008.TW": {"name":"大立光",   "en":"Largan",         "sector":"光學鏡頭",  "supply":["Apple"]},
    "3406.TW": {"name":"玉晶光",   "en":"Genius Optical", "sector":"光學鏡頭",  "supply":["Apple"]},
    # ── 電源 / 散熱 Power & Thermal ─────────────────────────────────────────
    "2308.TW": {"name":"台達電",   "en":"Delta Electronics","sector":"電源散熱","supply":["NVIDIA","AI"]},
    # ── 面板 Displays ────────────────────────────────────────────────────────
    "2409.TW": {"name":"友達",     "en":"AUO",            "sector":"面板",      "supply":["Apple"]},
    "3481.TW": {"name":"群創",     "en":"Innolux",        "sector":"面板",      "supply":[]},
    # ── 機殼 Enclosures ──────────────────────────────────────────────────────
    "2474.TW": {"name":"可成",     "en":"Catcher Tech",   "sector":"金屬機殼",  "supply":["Apple"]},
    # ── 品牌 / 主機板 ─────────────────────────────────────────────────────
    "2376.TW": {"name":"技嘉",     "en":"Gigabyte",       "sector":"主機板",    "supply":["NVIDIA","AMD","AI"]},
    "2357.TW": {"name":"華碩",     "en":"ASUS",           "sector":"3C品牌",    "supply":["NVIDIA","AMD","AI"]},
    "2395.TW": {"name":"研華",     "en":"Advantech",      "sector":"工業電腦",  "supply":["AI"]},
    # ── ETF ─────────────────────────────────────────────────────────────────
    "0052.TW": {"name":"富邦科技", "en":"Fubon Tech ETF", "sector":"ETF",       "supply":["ETF"]},
}

# ── 新聞催化劑關鍵字 ────────────────────────────────────────────────────────
CATALYST_MAP = {
    "NVIDIA": ["NVIDIA","輝達","Blackwell","GB200","GB300","H100","H200","NVL72","B200","Hopper","HGX","DGX"],
    "AMD":    ["AMD","超微","MI300","MI350","MI400","EPYC","Instinct"],
    "Apple":  ["Apple","蘋果","iPhone","iPad","Vision Pro","M4","A18","供應商","蘋果鏈"],
    "AI":     ["AI","人工智慧","生成式","LLM","大模型","算力","推論","訓練","GPU","NPU"],
    "CoWoS":  ["CoWoS","先進封裝","SoIC","2.5D","3D封裝","晶片堆疊"],
    "記憶體": ["HBM","記憶體","DRAM","NAND","高頻寬"],
    "漲價":   ["漲價","調漲","報價提升","price hike","報價上調"],
    "訂單":   ["接單","新訂單","出貨","交貨","獲利","業績","法說"],
    "外資":   ["外資買超","法人買超","外資大買"],
}

# 催化劑觸發的受益股票
CATALYST_BENEFICIARIES = {
    "NVIDIA":  ["2330.TW","3711.TW","3037.TW","6669.TW","2382.TW","2308.TW","3044.TW","2327.TW"],
    "AMD":     ["2330.TW","3711.TW","3037.TW","2376.TW","2357.TW"],
    "Apple":   ["2330.TW","4938.TW","2317.TW","3008.TW","3406.TW","2474.TW","3034.TW","2382.TW"],
    "AI":      ["2330.TW","2454.TW","6669.TW","2382.TW","3529.TW","2308.TW","8299.TW","3037.TW"],
    "CoWoS":   ["2330.TW","3711.TW","3037.TW"],
    "記憶體":  ["2344.TW","2408.TW","8299.TW","3529.TW"],
    "漲價":    ["2330.TW","2454.TW","3008.TW","2344.TW","2408.TW"],
}

# ═══════════════════════════════════════════════════════════════════════════════
#  技術指標計算
# ═══════════════════════════════════════════════════════════════════════════════

def calc_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    up   = delta.clip(lower=0)
    down = (-delta).clip(lower=0)
    avg_up   = up.ewm(alpha=1/period, min_periods=period).mean()
    avg_down = down.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_up / avg_down
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0

def calc_macd(close: pd.Series) -> Tuple[float, float]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal
    return float(hist.iloc[-1]) if not hist.empty else 0.0, float(hist.iloc[-2]) if len(hist) > 1 else 0.0

def calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return float(atr.iloc[-1]) if not atr.empty else 0.0

def volume_ratio(vol: pd.Series, period: int = 20) -> float:
    avg = vol.iloc[-period-1:-1].mean()
    if avg == 0 or np.isnan(avg):
        return 1.0
    return float(vol.iloc[-1] / avg)

def ma_score(close: pd.Series) -> int:
    """Price above MA5, MA20, MA60 → score 0-3"""
    score = 0
    last  = float(close.iloc[-1])
    for n in [5, 20, 60]:
        if len(close) >= n and last > float(close.rolling(n).mean().iloc[-1]):
            score += 1
    return score

# ═══════════════════════════════════════════════════════════════════════════════
#  新聞抓取
# ═══════════════════════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Accept": "application/json, text/html, */*",
}

def fetch_cnyes_news(limit: int = 60) -> List[Dict]:
    """鉅亨網科技財經新聞"""
    urls = [
        f"https://api.cnyes.com/media/api/v1/newslist/category/tw_stock?limit={limit}",
        f"https://api.cnyes.com/media/api/v1/newslist/category/technology?limit={limit}",
    ]
    news = []
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            items = r.json().get("items", {}).get("data", [])
            for item in items:
                pub_ts = item.get("publishAt", 0)
                pub_dt = datetime.fromtimestamp(pub_ts)
                if datetime.now() - pub_dt > timedelta(hours=18):
                    continue
                news.append({
                    "title":   item.get("title", ""),
                    "summary": (item.get("summary") or "")[:120],
                    "time":    pub_dt.strftime("%H:%M"),
                    "source":  "鉅亨網",
                })
        except Exception:
            pass
    return news

def fetch_moneydj_news() -> List[Dict]:
    """MoneyDJ 財經新聞"""
    url = "https://www.moneydj.com/kline/fundsn/fundsn0003.djhtm"
    news = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href*='djhtm']")[:20]:
            title = a.get_text(strip=True)
            if len(title) > 8:
                news.append({"title": title, "summary": "", "time": "--:--", "source": "MoneyDJ"})
    except Exception:
        pass
    return news

# Exchange mapping: stocks on OTC (櫃買) vs TSE (上市)
_OTC_STOCKS = {"3529.TW","6415.TW","8299.TW","2401.TW","6770.TW","3406.TW"}

def fetch_live_prices(tickers: List[str]) -> Dict[str, Dict]:
    """
    Real-time prices via TWSE MIS API.
    Returns price, change, change_pct, volume, limit_up, limit_down, last_time.
    Falls back to yfinance previous close when market is closed or data unavailable.
    """
    result: Dict[str, Dict] = {}

    # Build exchange-aware query string
    tse_codes = [t.replace(".TW","") for t in tickers if t not in _OTC_STOCKS and not t.endswith(".TWO")]
    otc_codes = [t.replace(".TW","") for t in tickers if t in _OTC_STOCKS]

    def _parse_response(data: dict, exchange: str):
        for item in data.get("msgArray", []):
            code   = item.get("c", "")
            ticker = code + ".TW"
            if ticker not in tickers:
                continue
            z = item.get("z", "-")   # current deal price
            y = item.get("y", "0")   # yesterday close
            u = item.get("u", "-")   # limit up (漲停)
            w = item.get("w", "-")   # limit down (跌停)
            v = item.get("v", "0")   # volume (千股)
            t = item.get("t", "")    # time
            try:
                prev   = float(y) if y and y != "-" else 0
                curr   = float(z) if z and z != "-" else prev
                chg    = curr - prev
                chg_pct = (chg / prev * 100) if prev > 0 else 0
                vol_k  = int(float(v)) if v and v != "-" else 0
                result[ticker] = {
                    "price":     curr,
                    "prev":      prev,
                    "chg":       chg,
                    "chg_pct":   chg_pct,
                    "volume":    vol_k,
                    "limit_up":  float(u) if u and u != "-" else 0,
                    "limit_down":float(w) if w and w != "-" else 0,
                    "time":      t,
                    "live":      z != "-",
                }
            except (ValueError, ZeroDivisionError):
                pass

    headers = {**HEADERS, "Referer": "https://mis.twse.com.tw/"}

    for codes, prefix in [(tse_codes, "tse"), (otc_codes, "otc")]:
        if not codes:
            continue
        ex_ch = "|".join(f"{prefix}_{c}.tw" for c in codes)
        url   = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch}&json=1&delay=0"
        try:
            r = requests.get(url, headers=headers, timeout=6)
            _parse_response(r.json(), prefix)
        except Exception:
            pass

    return result

def analyze_holding_sell(df: pd.DataFrame) -> Dict:
    """
    分析持股最佳賣出時機。
    回傳：action, urgency, target_sell, stop_loss, upside, downside, reasons
    """
    if df is None or len(df) < 22:
        return {}

    close = df["Close"]
    high  = df["High"]
    last  = float(close.iloc[-1])

    rsi          = calc_rsi(close)
    macd_h, macd_prev = calc_macd(close)
    atr          = calc_atr(df)
    ma5          = float(close.rolling(5).mean().iloc[-1])
    ma20         = float(close.rolling(20).mean().iloc[-1])
    ma60         = float(close.rolling(min(60, len(close))).mean().iloc[-1])
    high_20      = float(high.tail(20).max())
    high_60      = float(high.tail(min(60, len(high))).max())
    high_52w     = float(high.tail(min(252, len(high))).max())

    reasons  = []
    urgency  = "低"
    action   = "繼續持有"

    # ── RSI ──────────────────────────────────────────────────────────────────
    if rsi >= 82:
        reasons.append(f"RSI {rsi:.0f}，嚴重超買")
        urgency = "高"; action = "建議減倉或出場"
    elif rsi >= 75:
        reasons.append(f"RSI {rsi:.0f}，進入超買區間")
        urgency = "中"; action = "可考慮部分獲利了結"
    elif rsi >= 68:
        reasons.append(f"RSI {rsi:.0f}，偏高，留意轉折")
    elif rsi < 45:
        reasons.append(f"RSI {rsi:.0f}，動能轉弱")
        if urgency == "低": urgency = "中"
        if action == "繼續持有": action = "留意止損"

    # ── MACD ─────────────────────────────────────────────────────────────────
    if macd_h < 0 and macd_prev >= 0:
        reasons.append("MACD 出現死叉，動能反轉")
        if urgency == "低": urgency = "中"
        if action == "繼續持有": action = "留意賣出時機"
    elif macd_h > 0 and macd_prev > 0 and macd_h < macd_prev * 0.6:
        reasons.append("MACD 柱狀縮短，上漲動能減弱")

    # ── MA position ──────────────────────────────────────────────────────────
    if last < ma20:
        reasons.append("跌破 MA20，短線轉弱")
        if urgency == "低": urgency = "中"
        if action == "繼續持有": action = "留意止損"
    elif last > ma20 > ma60:
        reasons.append("MA 多頭排列，趨勢健康")

    # ── Resistance ───────────────────────────────────────────────────────────
    if last >= high_52w * 0.99:
        reasons.append(f"逼近52週高點 {high_52w:.1f}，歷史壓力區")
        if urgency == "低": urgency = "中"
    elif last >= high_20 * 0.985:
        reasons.append(f"接近近20日高點 {high_20:.1f}，短期壓力")

    if not reasons:
        reasons.append("技術面穩健，暫無明顯賣出信號")

    # ── Target & stop ─────────────────────────────────────────────────────────
    target_sell = round(min(last + 2.0 * atr, high_52w * 1.02), 1)
    stop_loss   = round(max(last - 1.5 * atr, ma20 * 0.97), 1)
    upside      = round((target_sell - last) / last * 100, 1)
    downside    = round((stop_loss   - last) / last * 100, 1)

    return {
        "action":      action,
        "urgency":     urgency,
        "target_sell": target_sell,
        "stop_loss":   stop_loss,
        "upside":      upside,
        "downside":    downside,
        "rsi":         round(rsi, 1),
        "above_ma20":  last > ma20,
        "macd_pos":    macd_h > 0,
        "reasons":     reasons[:3],
    }

def fetch_twse_foreign_buying(date_str: Optional[str] = None) -> Dict[str, float]:
    """抓取外資買超資料（千張）"""
    if not date_str:
        from datetime import timezone, timedelta
        date_str = datetime.now(tz=timezone(timedelta(hours=8))).strftime("%Y%m%d")
    url = f"https://www.twse.com.tw/rwd/zh/fund/TWT53U?response=json&date={date_str}"
    result = {}
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        rows = data.get("data", [])
        for row in rows:
            if len(row) >= 5:
                code = row[0].strip()
                try:
                    net = float(row[4].replace(",", "").replace("+", ""))
                    result[code + ".TW"] = net / 1000
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass
    return result

def fetch_twse_market_summary() -> Dict:
    """抓取大盤概況"""
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?response=json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        data = r.json()
        rows = data.get("data", [])
        if rows:
            row = rows[-1]
            return {
                "date":   row[0] if len(row) > 0 else "--",
                "volume": row[1] if len(row) > 1 else "--",
                "amount": row[2] if len(row) > 2 else "--",
                "index":  row[4] if len(row) > 4 else "--",
                "change": row[5] if len(row) > 5 else "--",
            }
    except Exception:
        pass
    return {}

# ═══════════════════════════════════════════════════════════════════════════════
#  催化劑分析：從新聞中找出觸發因素與受益股
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_catalysts(news_list: List[Dict]) -> Tuple[Dict[str, int], List[str]]:
    """
    回傳:
      catalyst_scores: {ticker: bonus_points}
      headlines:       最重要的5條新聞標題
    """
    catalyst_scores: Dict[str, int] = {}
    key_headlines: List[str] = []
    all_text = " ".join(n["title"] + " " + n["summary"] for n in news_list)

    triggered = set()
    for catalyst, keywords in CATALYST_MAP.items():
        for kw in keywords:
            if kw.lower() in all_text.lower():
                triggered.add(catalyst)
                break

    # 找出最相關的新聞
    for news in news_list:
        combined = news["title"] + " " + news["summary"]
        for catalyst in triggered:
            for kw in CATALYST_MAP[catalyst]:
                if kw.lower() in combined.lower():
                    if news["title"] not in key_headlines:
                        key_headlines.append(f"[{news['time']}][{news['source']}] {news['title'][:60]}")
                    break

    # 計算每支股票的催化劑加分
    for catalyst in triggered:
        beneficiaries = CATALYST_BENEFICIARIES.get(catalyst, [])
        for ticker in beneficiaries:
            catalyst_scores[ticker] = catalyst_scores.get(ticker, 0) + 20

    return catalyst_scores, key_headlines[:8]

def get_catalyst_labels(ticker: str, news_list: List[Dict]) -> List[str]:
    """為特定股票找出新聞催化劑標籤"""
    info  = TECH_UNIVERSE.get(ticker, {})
    name  = info.get("name", "")
    en    = info.get("en", "")
    supply_chains = info.get("supply", [])
    labels = []

    all_text = " ".join(n["title"] + " " + n["summary"] for n in news_list).lower()

    if name.lower() in all_text or en.lower() in all_text:
        labels.append("📰直接受益")

    for sc in supply_chains:
        if sc in CATALYST_MAP:
            for kw in CATALYST_MAP[sc]:
                if kw.lower() in all_text:
                    labels.append(f"🔗{sc}鏈")
                    break

    return list(dict.fromkeys(labels))[:3]

# ═══════════════════════════════════════════════════════════════════════════════
#  股票篩選引擎
# ═══════════════════════════════════════════════════════════════════════════════

def score_stock(ticker: str, df: pd.DataFrame, catalyst_bonus: int, foreign_net: float) -> Dict:
    """
    綜合評分 0-100：
      量能 30 + 動能 25 + 技術 25 + 催化劑 20（+外資調整）
    """
    if df is None or len(df) < 22:
        return {}

    close  = df["Close"]
    volume = df["Volume"]

    # 1. 量能分 (0-30)
    vr = volume_ratio(volume, 20)
    if   vr >= 3.0: vol_score = 30
    elif vr >= 2.0: vol_score = 24
    elif vr >= 1.5: vol_score = 18
    elif vr >= 1.2: vol_score = 12
    else:           vol_score = max(0, int(vr * 6))

    # 2. 價格動能 (0-25)
    mom1d = (float(close.iloc[-1]) / float(close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0
    mom5d = (float(close.iloc[-1]) / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_score = min(25, max(0, int((mom1d * 2 + mom5d) * 1.5)))

    # 3. 技術指標 (0-25)
    rsi  = calc_rsi(close)
    macd_hist, macd_prev = calc_macd(close)
    mas  = ma_score(close)

    tech = 0
    if 45 <= rsi <= 72:   tech += 8
    elif 72 < rsi <= 80:  tech += 4
    if macd_hist > 0 and macd_hist > macd_prev:  tech += 9
    elif macd_hist > 0:   tech += 5
    tech += mas * 2   # max 6

    # 4. 催化劑 (0-20) + 外資調整
    cat_score = min(20, catalyst_bonus)
    fi_bonus  = min(5, int(foreign_net / 500)) if foreign_net > 0 else max(-5, int(foreign_net / 500))
    total = min(100, vol_score + mom_score + tech + cat_score + fi_bonus)

    last_price = float(close.iloc[-1])
    atr        = calc_atr(df)
    target_pct = 5.0 if total < 75 else (7.0 if total < 88 else 10.0)

    # 預估賣出時間
    if total >= 88:
        sell_note = "當日收盤前（衝漲停留意）"
    elif total >= 75:
        sell_note = "開盤後達5-7%即可分批賣出"
    else:
        sell_note = "T+1 早盤高點賣出"

    return {
        "ticker":      ticker,
        "name":        TECH_UNIVERSE[ticker]["name"],
        "en":          TECH_UNIVERSE[ticker]["en"],
        "sector":      TECH_UNIVERSE[ticker]["sector"],
        "supply":      TECH_UNIVERSE[ticker]["supply"],
        "score":       total,
        "vol_score":   vol_score,
        "mom_score":   mom_score,
        "tech_score":  tech,
        "cat_score":   cat_score,
        "vol_ratio":   round(vr, 2),
        "rsi":         round(rsi, 1),
        "mom1d":       round(mom1d, 2),
        "mom5d":       round(mom5d, 2),
        "last_price":  last_price,
        "atr":         round(atr, 2),
        "target_pct":  target_pct,
        "target_price":round(last_price * (1 + target_pct / 100), 2),
        "stop_loss":   round(last_price - 1.5 * atr, 2),
        "stop_pct":    round((-1.5 * atr / last_price) * 100, 2) if last_price > 0 else 0,
        "sell_note":   sell_note,
        "foreign_net": foreign_net,
    }

# ═══════════════════════════════════════════════════════════════════════════════
#  批次抓取股價
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_prices_batch(tickers: List[str], period: str = "3mo") -> Dict[str, pd.DataFrame]:
    data = {}
    chunk = 25
    for i in range(0, len(tickers), chunk):
        batch = tickers[i:i+chunk]
        try:
            raw = yf.download(batch, period=period, auto_adjust=True, progress=False, threads=True)
            if isinstance(raw.columns, pd.MultiIndex):
                for t in batch:
                    try:
                        df = raw.xs(t, axis=1, level=1).dropna()
                        if len(df) >= 22:
                            data[t] = df
                    except Exception:
                        pass
            else:
                if len(batch) == 1 and len(raw) >= 22:
                    data[batch[0]] = raw.dropna()
        except Exception:
            pass
    return data

# ═══════════════════════════════════════════════════════════════════════════════
#  持股分析
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_holdings(price_data: Dict[str, pd.DataFrame]) -> List[Dict]:
    result = []
    for ticker, info in MY_HOLDINGS.items():
        df = price_data.get(ticker)
        if df is None or len(df) < 2:
            result.append({"ticker": ticker, "name": info["name"], "price": 0, "chg": 0, "error": True})
            continue
        p1 = float(df["Close"].iloc[-1])
        p0 = float(df["Close"].iloc[-2])
        chg = (p1 / p0 - 1) * 100
        wk_high = float(df["Close"].iloc[-5:].max()) if len(df) >= 5 else p1
        wk_low  = float(df["Close"].iloc[-5:].min()) if len(df) >= 5 else p1
        result.append({
            "ticker": ticker, "name": info["name"],
            "price": p1, "chg": chg,
            "wk_high": wk_high, "wk_low": wk_low,
            "error": False,
        })
    return result

# ═══════════════════════════════════════════════════════════════════════════════
#  顯示函數
# ═══════════════════════════════════════════════════════════════════════════════

def make_bar(score: int, width: int = 10) -> str:
    filled = round(score / 100 * width)
    color = "green" if score >= 75 else ("yellow" if score >= 55 else "red")
    bar = "█" * filled + "░" * (width - filled)
    return f"[{color}]{bar}[/{color}]"

def chg_color(pct: float) -> str:
    if pct >= 0.5:  return "bold green"
    if pct > 0:     return "green"
    if pct <= -0.5: return "bold red"
    return "red"

def supply_badge(supply: List[str]) -> str:
    badges = {
        "NVIDIA": "[bold cyan]NV[/bold cyan]",
        "AMD":    "[bold magenta]AMD[/bold magenta]",
        "Apple":  "[bold white]APL[/bold white]",
        "AI":     "[bold yellow]AI[/bold yellow]",
        "CoWoS":  "[bold green]CoW[/bold green]",
        "ETF":    "[dim]ETF[/dim]",
    }
    return " ".join(badges[s] for s in supply if s in badges) or "—"

def print_header(now: datetime):
    title = Text(justify="center")
    title.append("  台灣科技股盤前分析系統  ", style="bold white on blue")
    title.append(f"  {now.strftime('%Y-%m-%d  %H:%M')}  ", style="white on dark_blue")
    console.print()
    console.print(Align.center(title))
    console.print(Align.center(Text("晶片・記憶體・AI｜NVIDIA / AMD / Apple 上游供應鏈深度追蹤", style="dim")))
    console.print()

def print_market_summary(summary: Dict):
    if not summary:
        return
    console.print(Rule("[bold]大盤概況[/bold]", style="blue"))
    grid = Table.grid(padding=(0, 3))
    grid.add_row(
        f"[dim]加權指數[/dim]",
        f"[bold]{summary.get('index','--')}[/bold]",
        f"[dim]漲跌[/dim]",
        f"{summary.get('change','--')}",
        f"[dim]成交量[/dim]",
        f"{summary.get('amount','--')}",
    )
    console.print(Align.center(grid))
    console.print()

def print_holdings(holdings: List[Dict]):
    console.print(Rule("[bold yellow]我的持股[/bold yellow]", style="yellow"))
    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    t.add_column("代號", style="bold", width=8)
    t.add_column("名稱", width=14)
    t.add_column("昨收", justify="right", width=10)
    t.add_column("漲跌%", justify="right", width=10)
    t.add_column("5日高", justify="right", width=10)
    t.add_column("5日低", justify="right", width=10)
    t.add_column("狀態", width=16)

    for h in holdings:
        if h.get("error"):
            t.add_row(h["ticker"], h["name"], "—", "—", "—", "—", "[dim]資料不足[/dim]")
            continue
        chg   = h["chg"]
        color = chg_color(chg)
        arrow = "▲" if chg >= 0 else "▼"
        sign  = "+" if chg >= 0 else ""
        p = h["price"]
        status = "🔥 強勢" if chg >= 3 else ("📈 上漲" if chg >= 0.5 else ("⚠ 弱勢" if chg < -1.5 else "➡ 持平"))
        t.add_row(
            h["ticker"].replace(".TW", ""),
            h["name"],
            f"{p:.1f}",
            f"[{color}]{arrow}{sign}{chg:.2f}%[/{color}]",
            f"{h.get('wk_high',0):.1f}",
            f"{h.get('wk_low',0):.1f}",
            status,
        )
    console.print(t)
    console.print()

def print_news(headlines: List[str]):
    console.print(Rule("[bold cyan]今日早盤新聞重點[/bold cyan]", style="cyan"))
    if not headlines:
        console.print("  [dim]新聞抓取中，請稍候…[/dim]\n")
        return
    for h in headlines[:8]:
        console.print(f"  [cyan]●[/cyan] {h}")
    console.print()

def print_recommendations(picks: List[Dict], news_list: List[Dict]):
    console.print(Rule(
        "[bold green]今日精選 5 支潛力股  （預估漲幅 5% ～ 漲停）[/bold green]",
        style="green"
    ))
    console.print()

    for rank, p in enumerate(picks, 1):
        catalyst_labels = get_catalyst_labels(p["ticker"], news_list)
        cat_str = "  ".join(catalyst_labels) if catalyst_labels else "技術面突破"

        supply_str = supply_badge(p.get("supply", []))
        chg_str = (
            f"[green]+{p['mom1d']:.2f}%[/green]" if p["mom1d"] >= 0
            else f"[red]{p['mom1d']:.2f}%[/red]"
        )
        fi_str = (
            f"[green]+{p['foreign_net']:.0f}千張[/green]" if p["foreign_net"] > 0
            else (f"[red]{p['foreign_net']:.0f}千張[/red]" if p["foreign_net"] < 0 else "[dim]N/A[/dim]")
        )

        header = (
            f" #{rank}  "
            f"[bold yellow]{p['ticker'].replace('.TW','')} {p['name']}[/bold yellow]"
            f"  [dim]{p['en']}[/dim]"
            f"  [{p['sector']}]"
            f"  {supply_str}"
        )

        body = Table.grid(padding=(0, 2))
        body.add_row(
            f"[dim]昨收[/dim] [bold]{p['last_price']:.1f}[/bold]",
            f"[dim]昨漲[/dim] {chg_str}",
            f"[dim]5日[/dim] [white]{p['mom5d']:+.1f}%[/white]",
            f"[dim]量比[/dim] [{'green' if p['vol_ratio']>=1.5 else 'white'}]{p['vol_ratio']:.1f}x[/{'green' if p['vol_ratio']>=1.5 else 'white'}]",
            f"[dim]RSI[/dim] {p['rsi']:.0f}",
            f"[dim]外資[/dim] {fi_str}",
        )
        body.add_row()
        body.add_row(
            f"[dim]目標[/dim] [bold green]{p['target_price']:.1f}  (+{p['target_pct']:.0f}%)[/bold green]",
            f"[dim]止損[/dim] [red]{p['stop_loss']:.1f}  ({p['stop_pct']:.1f}%)[/red]",
            f"[dim]建議賣出[/dim] [bold cyan]{p['sell_note']}[/bold cyan]",
            "", "", "",
        )
        body.add_row()
        body.add_row(
            f"[dim]催化劑[/dim] [italic]{cat_str}[/italic]",
            f"[dim]信心[/dim] {make_bar(p['score'])} {p['score']}/100",
            "", "", "", "",
        )

        score_breakdown = (
            f"量能{p['vol_score']} + 動能{p['mom_score']} + 技術{p['tech_score']} + 催化{p['cat_score']}"
        )
        body.add_row(f"[dim]評分細項  {score_breakdown}[/dim]", "", "", "", "", "")

        panel_color = "green" if p["score"] >= 80 else ("yellow" if p["score"] >= 65 else "white")
        console.print(Panel(body, title=header, border_style=panel_color, padding=(0, 1)))
        console.print()

def print_supply_chain_map():
    console.print(Rule("[bold]供應鏈地圖（快速參考）[/bold]", style="dim"))
    t = Table(box=box.MINIMAL, show_header=True, header_style="bold dim")
    t.add_column("客戶", width=10)
    t.add_column("台灣上游供應商", width=90)
    rows = [
        ("NVIDIA", "台積電(晶圓)・日月光(封測)・欣興(載板)・緯穎(AI伺服器)・廣達(伺服器ODM)・台達電(電源)・健鼎(PCB)・國巨(被動元件)"),
        ("AMD",    "台積電(晶圓)・日月光(封測)・欣興(載板)・技嘉・華碩(主機板)"),
        ("Apple",  "台積電(A/M晶片)・和碩/鴻海(組裝)・大立光/玉晶光(鏡頭)・可成(機殼)・聯詠(驅動IC)・義隆電(觸控)・廣達(Mac)"),
        ("AI全鏈", "台積電・聯發科(AI晶片)・力旺(NVM IP)・矽力(PMIC)・群聯(NAND)・緯穎・廣達・台達電"),
    ]
    for client, chain in rows:
        t.add_row(f"[bold]{client}[/bold]", chain)
    console.print(t)
    console.print()

def print_disclaimer():
    console.print()
    console.print(Panel(
        "[dim]⚠  本系統僅供技術分析參考，不構成投資建議。\n"
        "   台股漲停板為前日收盤價 ±10%。零股交易請注意流動性。\n"
        "   建議結合基本面、籌碼面與總經環境綜合判斷。[/dim]",
        style="dim", border_style="dim"
    ))

# ═══════════════════════════════════════════════════════════════════════════════
#  主程式
# ═══════════════════════════════════════════════════════════════════════════════

def main(args):
    now = datetime.now()
    print_header(now)

    all_tickers  = list(TECH_UNIVERSE.keys())
    holding_tickers = list(MY_HOLDINGS.keys())
    screen_tickers  = [t for t in all_tickers if t not in holding_tickers]

    with Progress(SpinnerColumn(), TextColumn("[bold blue]{task.description}"), transient=True) as prog:

        t1 = prog.add_task("抓取早盤新聞…", total=None)
        cnyes_news  = fetch_cnyes_news(60)
        moneydj_news = fetch_moneydj_news()
        all_news = cnyes_news + moneydj_news
        prog.update(t1, description=f"✅ 取得 {len(all_news)} 條新聞")
        time.sleep(0.3)

        t2 = prog.add_task("分析催化劑…", total=None)
        catalyst_scores, key_headlines = analyze_catalysts(all_news)
        prog.update(t2, description="✅ 催化劑分析完成")
        time.sleep(0.3)

        t3 = prog.add_task("抓取外資籌碼…", total=None)
        foreign_data = fetch_twse_foreign_buying()
        prog.update(t3, description=f"✅ 取得 {len(foreign_data)} 筆外資資料")
        time.sleep(0.3)

        t4 = prog.add_task("下載股價資料（約30秒）…", total=None)
        price_data = fetch_prices_batch(all_tickers, period="3mo")
        prog.update(t4, description=f"✅ 取得 {len(price_data)} 支股票")
        time.sleep(0.3)

        t5 = prog.add_task("大盤概況…", total=None)
        market_summary = fetch_twse_market_summary()
        prog.update(t5, description="✅ 大盤資料完成")
        time.sleep(0.2)

    # 評分
    scored = []
    for ticker in screen_tickers:
        df = price_data.get(ticker)
        bonus = catalyst_scores.get(ticker, 0)
        fi    = foreign_data.get(ticker, 0)
        res   = score_stock(ticker, df, bonus, fi)
        if res:
            scored.append(res)

    scored.sort(key=lambda x: x["score"], reverse=True)
    top5 = scored[:5]

    # ── 輸出 ──────────────────────────────────────────────────────────────────
    print_market_summary(market_summary)

    holding_info = analyze_holdings(price_data)
    print_holdings(holding_info)

    print_news(key_headlines)
    print_recommendations(top5, all_news)
    print_supply_chain_map()
    print_disclaimer()

    # 儲存 JSON 報告
    report = {
        "date":        now.strftime("%Y-%m-%d %H:%M"),
        "top5":        [{k: v for k, v in p.items() if k not in ("supply",)} for p in top5],
        "headlines":   key_headlines,
        "market":      market_summary,
    }
    import os
    log_dir = os.path.expanduser("~/taiwan_stock_widget/reports")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{now.strftime('%Y%m%d_%H%M')}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    console.print(f"\n[dim]報告已儲存：{log_path}[/dim]")

# ═══════════════════════════════════════════════════════════════════════════════
#  啟動
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="台灣科技股盤前分析系統")
    parser.add_argument("--quick", action="store_true", help="跳過外資資料（較快）")
    args = parser.parse_args()
    main(args)
