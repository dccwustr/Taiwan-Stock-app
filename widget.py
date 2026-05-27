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
#  股票池：全產業（科技 + 金融 + 航運 + 生技 + 消費 + 綠能 + 傳產…）
#  原則：只要有潛力，不限產業
# ═══════════════════════════════════════════════════════════════════════════════
TECH_UNIVERSE: Dict[str, Dict] = {

    # ════════════════════════════════════════════════════════════════════════
    #  科技業 Technology
    # ════════════════════════════════════════════════════════════════════════

    # ── 晶圓代工 Foundry ────────────────────────────────────────────────────
    "2330.TW": {"name":"台積電",    "en":"TSMC",              "sector":"晶圓代工",  "supply":["NVIDIA","AMD","Apple","AI","CoWoS"]},
    "2303.TW": {"name":"聯電",      "en":"UMC",               "sector":"晶圓代工",  "supply":[]},
    "6770.TW": {"name":"力積電",    "en":"PSMC",              "sector":"晶圓代工",  "supply":[]},
    # ── IC設計 Fabless ──────────────────────────────────────────────────────
    "2454.TW": {"name":"聯發科",    "en":"MediaTek",          "sector":"IC設計",    "supply":["AI","AMD"]},
    "3034.TW": {"name":"聯詠",      "en":"Novatek",           "sector":"IC設計",    "supply":["Apple"]},
    "2379.TW": {"name":"瑞昱",      "en":"Realtek",           "sector":"IC設計",    "supply":[]},
    "6415.TW": {"name":"矽力-KY",   "en":"Silergy",           "sector":"IC設計",    "supply":["AI"]},
    "2458.TW": {"name":"義隆電",    "en":"Elan Micro",        "sector":"IC設計",    "supply":["Apple"]},
    "2401.TW": {"name":"凌陽",      "en":"Sunplus",           "sector":"IC設計",    "supply":[]},
    # ── 記憶體 Memory ───────────────────────────────────────────────────────
    "2344.TW": {"name":"華邦電",    "en":"Winbond",           "sector":"記憶體",    "supply":[]},
    "2408.TW": {"name":"南亞科",    "en":"Nanya Tech",        "sector":"DRAM",      "supply":[]},
    "8299.TW": {"name":"群聯",      "en":"Phison",            "sector":"NAND控制器","supply":["AI"]},
    # ── 矽晶圓 Silicon Wafer ─────────────────────────────────────────────────
    "6488.TW": {"name":"環球晶",    "en":"GlobalWafers",      "sector":"矽晶圓",    "supply":["AI","NVIDIA"]},
    "5483.TW": {"name":"中美晶",    "en":"Sino-American Si",  "sector":"矽晶圓",    "supply":["AI"]},
    # ── 先進封裝 / 封測 Packaging ───────────────────────────────────────────
    "3711.TW": {"name":"日月光投控","en":"ASE Technology",    "sector":"封測",      "supply":["NVIDIA","AMD","Apple","CoWoS"]},
    "2449.TW": {"name":"京元電子",  "en":"KYEC",              "sector":"IC測試",    "supply":[]},
    # ── IC載板 / PCB ────────────────────────────────────────────────────────
    "3037.TW": {"name":"欣興",      "en":"Unimicron",         "sector":"IC載板",    "supply":["NVIDIA","AMD","CoWoS"]},
    "3044.TW": {"name":"健鼎",      "en":"Tripod Tech",       "sector":"PCB",       "supply":["NVIDIA","AI"]},
    # ── AI伺服器 / ODM ──────────────────────────────────────────────────────
    "6669.TW": {"name":"緯穎",      "en":"Wiwynn",            "sector":"AI伺服器",  "supply":["NVIDIA","AI"]},
    "2382.TW": {"name":"廣達",      "en":"Quanta",            "sector":"伺服器ODM", "supply":["NVIDIA","AI","Apple"]},
    "3231.TW": {"name":"緯創",      "en":"Wistron",           "sector":"ODM",       "supply":["Apple","AI"]},
    "4938.TW": {"name":"和碩",      "en":"Pegatron",          "sector":"ODM",       "supply":["Apple"]},
    "2317.TW": {"name":"鴻海",      "en":"Foxconn",           "sector":"EMS/ODM",   "supply":["Apple","NVIDIA","AI"]},
    "2324.TW": {"name":"仁寶",      "en":"Compal",            "sector":"ODM",       "supply":["Apple","AI"]},
    # ── 被動元件 Passive Components ─────────────────────────────────────────
    "2327.TW": {"name":"國巨",      "en":"Yageo",             "sector":"被動元件",  "supply":["NVIDIA","Apple"]},
    "2492.TW": {"name":"華新科",    "en":"Walsin Tech",       "sector":"被動元件",  "supply":[]},
    # ── 連接器 Connectors ────────────────────────────────────────────────────
    "3533.TW": {"name":"嘉澤",      "en":"Lotes",             "sector":"連接器",    "supply":["AI","NVIDIA"]},
    # ── 光學 Optics ─────────────────────────────────────────────────────────
    "3008.TW": {"name":"大立光",    "en":"Largan",            "sector":"光學鏡頭",  "supply":["Apple"]},
    "3406.TW": {"name":"玉晶光",    "en":"Genius Optical",    "sector":"光學鏡頭",  "supply":["Apple"]},
    # ── 電源 / 散熱 Power & Thermal ─────────────────────────────────────────
    "2308.TW": {"name":"台達電",    "en":"Delta Electronics", "sector":"電源散熱",  "supply":["NVIDIA","AI","綠能"]},
    # ── 面板 Displays ────────────────────────────────────────────────────────
    "2409.TW": {"name":"友達",      "en":"AUO",               "sector":"面板",      "supply":["Apple"]},
    "3481.TW": {"name":"群創",      "en":"Innolux",           "sector":"面板",      "supply":[]},
    # ── 機殼 Enclosures ──────────────────────────────────────────────────────
    "2474.TW": {"name":"可成",      "en":"Catcher Tech",      "sector":"金屬機殼",  "supply":["Apple"]},
    # ── 品牌 / 主機板 ────────────────────────────────────────────────────────
    "2376.TW": {"name":"技嘉",      "en":"Gigabyte",          "sector":"主機板",    "supply":["NVIDIA","AMD","AI"]},
    "2357.TW": {"name":"華碩",      "en":"ASUS",              "sector":"3C品牌",    "supply":["NVIDIA","AMD","AI"]},
    "2395.TW": {"name":"研華",      "en":"Advantech",         "sector":"工業電腦",  "supply":["AI"]},
    # ── ETF ─────────────────────────────────────────────────────────────────
    "0052.TW": {"name":"富邦科技",  "en":"Fubon Tech ETF",    "sector":"ETF",       "supply":["ETF"]},

    # ════════════════════════════════════════════════════════════════════════
    #  金融 Financial
    # ════════════════════════════════════════════════════════════════════════
    "2881.TW": {"name":"富邦金",    "en":"Fubon Financial",   "sector":"金融",      "supply":["金融"]},
    "2882.TW": {"name":"國泰金",    "en":"Cathay Financial",  "sector":"金融",      "supply":["金融"]},
    "2884.TW": {"name":"玉山金",    "en":"E.Sun Financial",   "sector":"金融",      "supply":["金融"]},
    "2891.TW": {"name":"中信金",    "en":"CTBC Financial",    "sector":"金融",      "supply":["金融"]},
    "2886.TW": {"name":"兆豐金",    "en":"Mega Financial",    "sector":"金融",      "supply":["金融"]},
    "2892.TW": {"name":"第一金",    "en":"First Financial",   "sector":"金融",      "supply":["金融"]},
    "2880.TW": {"name":"華南金",    "en":"Hua Nan Financial", "sector":"金融",      "supply":["金融"]},
    "2883.TW": {"name":"開發金",    "en":"CDIB Financial",    "sector":"金融",      "supply":["金融"]},

    # ════════════════════════════════════════════════════════════════════════
    #  航運 Shipping
    # ════════════════════════════════════════════════════════════════════════
    "2603.TW": {"name":"長榮",      "en":"Evergreen Marine",  "sector":"航運",      "supply":["航運"]},
    "2609.TW": {"name":"陽明",      "en":"Yang Ming Marine",  "sector":"航運",      "supply":["航運"]},
    "2615.TW": {"name":"萬海",      "en":"Wan Hai Lines",     "sector":"航運",      "supply":["航運"]},
    "2610.TW": {"name":"華航",      "en":"China Airlines",    "sector":"航空",      "supply":["航空"]},
    "2618.TW": {"name":"長榮航",    "en":"EVA Air",           "sector":"航空",      "supply":["航空"]},

    # ════════════════════════════════════════════════════════════════════════
    #  鋼鐵 / 石化 / 原材料 Steel / Petrochem / Materials
    # ════════════════════════════════════════════════════════════════════════
    "2002.TW": {"name":"中鋼",      "en":"China Steel",       "sector":"鋼鐵",      "supply":["原物料"]},
    "2015.TW": {"name":"豐興",      "en":"Feng Hsin Steel",   "sector":"鋼鐵",      "supply":["原物料"]},
    "2023.TW": {"name":"燁聯",      "en":"Yieh United Steel", "sector":"鋼鐵",      "supply":["原物料"]},
    "1301.TW": {"name":"台塑",      "en":"Formosa Plastics",  "sector":"石化",      "supply":["原物料"]},
    "1303.TW": {"name":"南亞",      "en":"Nan Ya Plastics",   "sector":"石化",      "supply":["原物料"]},
    "1326.TW": {"name":"台化",      "en":"Formosa Chemicals", "sector":"石化",      "supply":["原物料"]},

    # ════════════════════════════════════════════════════════════════════════
    #  電信 Telecom
    # ════════════════════════════════════════════════════════════════════════
    "2412.TW": {"name":"中華電",    "en":"Chunghwa Telecom",  "sector":"電信",      "supply":[]},
    "3045.TW": {"name":"台灣大",    "en":"Taiwan Mobile",     "sector":"電信",      "supply":[]},
    "4904.TW": {"name":"遠傳",      "en":"Far EasTone",       "sector":"電信",      "supply":[]},

    # ════════════════════════════════════════════════════════════════════════
    #  消費 / 零售 Consumer / Retail
    # ════════════════════════════════════════════════════════════════════════
    "2912.TW": {"name":"統一超",    "en":"President Chain",   "sector":"零售",      "supply":[]},
    "5903.TW": {"name":"全家",      "en":"FamilyMart TW",     "sector":"零售",      "supply":[]},
    "5904.TW": {"name":"寶雅",      "en":"Poya",              "sector":"零售",      "supply":[]},
    "2207.TW": {"name":"和泰車",    "en":"Hotai Motor",       "sector":"汽車",      "supply":[]},

    # ════════════════════════════════════════════════════════════════════════
    #  建設 / 不動產 Construction / Real Estate
    # ════════════════════════════════════════════════════════════════════════
    "5522.TW": {"name":"遠雄",      "en":"Farglory",          "sector":"建設",      "supply":["建設"]},
    "2542.TW": {"name":"興富發",    "en":"Highwealth Const",  "sector":"建設",      "supply":["建設"]},
    "2504.TW": {"name":"國產",      "en":"Kuo Chan Const",    "sector":"建設",      "supply":["建設"]},

    # ════════════════════════════════════════════════════════════════════════
    #  生技醫療 Biotech / Medical
    # ════════════════════════════════════════════════════════════════════════
    "6446.TW": {"name":"藥華藥",    "en":"PharmaEngine",      "sector":"生技",      "supply":["生技"]},
    "6472.TW": {"name":"保瑞",      "en":"Bora Pharma",       "sector":"生技",      "supply":["生技"]},
    "1789.TW": {"name":"神隆",      "en":"ScinoPharm",        "sector":"生技",      "supply":["生技"]},
    "1707.TW": {"name":"葡萄王",    "en":"Grape King Bio",    "sector":"保健",      "supply":[]},
    "4171.TW": {"name":"瑞基",      "en":"Reber Genetics",    "sector":"生技",      "supply":["生技"]},

    # ════════════════════════════════════════════════════════════════════════
    #  綠能 / 電力 Green Energy / Power
    # ════════════════════════════════════════════════════════════════════════
    "1513.TW": {"name":"中興電",    "en":"CENS",              "sector":"電機",      "supply":["綠能"]},
    "1504.TW": {"name":"東元",      "en":"Teco Electric",     "sector":"電機",      "supply":["綠能"]},
    "1101.TW": {"name":"台泥",      "en":"Taiwan Cement",     "sector":"水泥/綠能", "supply":["綠能"]},

    # ════════════════════════════════════════════════════════════════════════
    #  食品 Food
    # ════════════════════════════════════════════════════════════════════════
    "1216.TW": {"name":"統一",      "en":"Uni-President",     "sector":"食品",      "supply":[]},
    "1210.TW": {"name":"大成",      "en":"Great Wall Ent",    "sector":"食品",      "supply":[]},

    # ════════════════════════════════════════════════════════════════════════
    #  觀光 / 餐飲 Tourism / Hospitality
    # ════════════════════════════════════════════════════════════════════════
    "2707.TW": {"name":"晶華",      "en":"Regent Hotel",      "sector":"觀光",      "supply":[]},
    "2727.TW": {"name":"王品",      "en":"Wowprime",          "sector":"餐飲",      "supply":[]},
    "2731.TW": {"name":"雄獅",      "en":"Lion Travel",       "sector":"觀光",      "supply":[]},

    # ════════════════════════════════════════════════════════════════════════
    #  水泥 / 基建 Cement / Infrastructure
    # ════════════════════════════════════════════════════════════════════════
    "1102.TW": {"name":"亞泥",      "en":"Asia Cement",       "sector":"水泥",      "supply":[]},
}

# ── 新聞催化劑關鍵字（科技 + 多元產業）──────────────────────────────────────
CATALYST_MAP = {
    # 科技主題
    "NVIDIA": ["NVIDIA","輝達","Blackwell","GB200","GB300","H100","H200","NVL72","B200","Hopper","HGX","DGX"],
    "AMD":    ["AMD","超微","MI300","MI350","MI400","EPYC","Instinct"],
    "Apple":  ["Apple","蘋果","iPhone","iPad","Vision Pro","M4","A18","蘋果鏈"],
    "AI":     ["AI","人工智慧","生成式","LLM","大模型","算力","推論","訓練","GPU","NPU","機器人"],
    "CoWoS":  ["CoWoS","先進封裝","SoIC","2.5D","3D封裝","晶片堆疊"],
    "記憶體": ["HBM","記憶體","DRAM","NAND","高頻寬"],
    "漲價":   ["漲價","調漲","報價提升","price hike","報價上調"],
    "訂單":   ["接單","新訂單","出貨","交貨","獲利","業績","法說"],
    "外資":   ["外資買超","法人買超","外資大買"],
    # 非科技主題（新增）
    "降息":   ["Fed降息","降息","利率下降","rate cut","FOMC寬鬆","貨幣寬鬆","央行降息"],
    "升息":   ["升息","利率上升","rate hike","緊縮","FOMC升息"],
    "航運":   ["運費","貨櫃","航運景氣","SCFI","FBX","BDI","集運","缺艙","運力"],
    "生技":   ["FDA","新藥","藥證","臨床試驗","解盲","NDA","IND","藥品核准","解禁"],
    "綠能":   ["離岸風電","太陽能","儲能","綠能","再生能源","風電","淨零","碳中和","電動車","EV"],
    "原物料": ["鋼價","銅價","鐵礦石","原油","油價","鋼鐵漲","煤炭","原物料"],
    "建設":   ["房地產","房市","捷運","新青安","都更","危老重建","土地"],
}

# 催化劑觸發的受益股票（科技 + 多元產業）
CATALYST_BENEFICIARIES = {
    # 科技
    "NVIDIA":  ["2330.TW","3711.TW","3037.TW","6669.TW","2382.TW","2308.TW","3044.TW","2327.TW","3533.TW","6488.TW"],
    "AMD":     ["2330.TW","3711.TW","3037.TW","2376.TW","2357.TW"],
    "Apple":   ["2330.TW","4938.TW","2317.TW","3008.TW","3406.TW","2474.TW","3034.TW","2382.TW","2324.TW"],
    "AI":      ["2330.TW","2454.TW","6669.TW","2382.TW","2308.TW","8299.TW","3037.TW","3533.TW","6488.TW","5483.TW"],
    "CoWoS":   ["2330.TW","3711.TW","3037.TW"],
    "記憶體":  ["2344.TW","2408.TW","8299.TW","6488.TW"],
    "漲價":    ["2330.TW","2454.TW","3008.TW","2344.TW","2408.TW","2002.TW","1301.TW"],
    "訂單":    ["2330.TW","2454.TW","6669.TW","2382.TW","2317.TW","2603.TW","2609.TW"],
    # 非科技（新增）
    "降息":    ["2881.TW","2882.TW","2884.TW","2891.TW","2886.TW","2892.TW","2880.TW","2883.TW",
                "5522.TW","2542.TW","2504.TW"],   # 降息利多：金融、建設
    "升息":    ["2412.TW","3045.TW","4904.TW","2881.TW","2882.TW"],  # 升息：電信（高股息防禦）
    "航運":    ["2603.TW","2609.TW","2615.TW","2610.TW","2618.TW"],
    "生技":    ["6446.TW","6472.TW","1789.TW","4171.TW"],
    "綠能":    ["1513.TW","1504.TW","1101.TW","2308.TW","3533.TW"],
    "原物料":  ["2002.TW","2015.TW","2023.TW","1301.TW","1303.TW","1326.TW"],
    "建設":    ["5522.TW","2542.TW","2504.TW","1102.TW","1101.TW"],
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
                if datetime.now() - pub_dt > timedelta(hours=24):
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
def _tw_limit_up(prev: float) -> float:
    """Taiwan ±10% limit, rounded to correct tick size."""
    price = prev * 1.10
    if price < 10:     tick = 0.01
    elif price < 50:   tick = 0.05
    elif price < 100:  tick = 0.10
    elif price < 500:  tick = 0.50
    elif price < 1000: tick = 1.00
    else:              tick = 5.00
    return round(price / tick) * tick

def _parse_ts(ts) -> str:
    """Convert a pandas Timestamp to Taipei HH:MM string."""
    try:
        from datetime import timezone as _tz, timedelta as _td
        if getattr(ts, "tzinfo", None):
            tw = ts.astimezone(_tz(_td(hours=8)))
        else:
            tw = pd.Timestamp(ts).tz_localize("UTC").tz_convert("Asia/Taipei")
        return tw.strftime("%H:%M")
    except Exception:
        return "--:--"

def fetch_live_prices(tickers: List[str]) -> Dict[str, Dict]:
    """
    Real-time-ish prices via yfinance batch download (single HTTP request).
    Uses yf.download() so all tickers are fetched in one call — avoids
    Yahoo Finance rate-limiting that hits per-ticker parallel requests.
    """
    import yfinance as yf
    result: Dict[str, Dict] = {}
    if not tickers:
        return result

    try:
        raw = yf.download(
            tickers=" ".join(tickers),
            period="2d",
            interval="1m",
            progress=False,
            auto_adjust=True,
        )
    except Exception:
        return result

    if raw is None or raw.empty:
        return result

    is_multi = isinstance(raw.columns, pd.MultiIndex)

    for t in tickers:
        try:
            if is_multi:
                close_s = raw["Close"][t].dropna()
                vol_s   = raw["Volume"][t].dropna()
            else:
                # yf.download with a single ticker returns flat columns
                close_s = raw["Close"].dropna()
                vol_s   = raw["Volume"].dropna()

            if close_s.empty:
                continue

            last_price = float(close_s.iloc[-1])
            last_ts    = close_s.index[-1]

            # Previous trading day's last close
            if hasattr(last_ts, "date"):
                today_d    = last_ts.date()
                prev_bars  = close_s[[x.date() < today_d for x in close_s.index]]
                prev_close = float(prev_bars.iloc[-1]) if not prev_bars.empty else last_price
            else:
                prev_close = last_price

            chg     = last_price - prev_close
            chg_pct = (chg / prev_close * 100) if prev_close > 0 else 0
            vol_sum = int(vol_s.iloc[-30:].sum() / 1000) if not vol_s.empty else 0

            result[t] = {
                "price":      last_price,
                "prev":       prev_close,
                "chg":        chg,
                "chg_pct":    chg_pct,
                "volume":     vol_sum,
                "limit_up":   _tw_limit_up(prev_close),
                "limit_down": round(prev_close * 0.90, 0),
                "time":       _parse_ts(last_ts),
                "live":       True,
            }
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
    action   = "目前可以繼續持有"

    # ── RSI ──────────────────────────────────────────────────────────────────
    if rsi >= 82:
        reasons.append(f"漲太多了（RSI {rsi:.0f}），很多人開始獲利了結")
        urgency = "高"; action = "建議賣掉或減少持股"
    elif rsi >= 75:
        reasons.append(f"漲勢偏強（RSI {rsi:.0f}），可以考慮先賣一部分")
        urgency = "中"; action = "可以先賣一半獲利"
    elif rsi >= 68:
        reasons.append(f"漲幅不小（RSI {rsi:.0f}），留意有沒有反轉跡象")
    elif rsi < 45:
        reasons.append(f"漲勢在減弱（RSI {rsi:.0f}），小心繼續跌")
        if urgency == "低": urgency = "中"
        if action == "目前可以繼續持有": action = "注意停損點，別讓虧損擴大"

    # ── MACD ─────────────────────────────────────────────────────────────────
    if macd_h < 0 and macd_prev >= 0:
        reasons.append("動能轉向向下，短線可能開始走弱")
        if urgency == "低": urgency = "中"
        if action == "目前可以繼續持有": action = "考慮找高點賣出"
    elif macd_h > 0 and macd_prev > 0 and macd_h < macd_prev * 0.6:
        reasons.append("上漲力道在縮減，後續漲幅可能有限")

    # ── MA position ──────────────────────────────────────────────────────────
    if last < ma20:
        reasons.append("股價跌破20日均線，短線轉弱")
        if urgency == "低": urgency = "中"
        if action == "目前可以繼續持有": action = "注意停損點，別讓虧損擴大"
    elif last > ma20 > ma60:
        reasons.append("均線向上排列，趨勢健康，可以繼續持有")

    # ── Resistance ───────────────────────────────────────────────────────────
    if last >= high_52w * 0.99:
        reasons.append(f"快到一年最高點 {high_52w:.1f} 了，這附近通常會有賣壓")
        if urgency == "低": urgency = "中"
    elif last >= high_20 * 0.985:
        reasons.append(f"接近近20天高點 {high_20:.1f}，短期可能遇到阻力")

    if not reasons:
        reasons.append("目前沒有明顯賣出訊號，可以繼續觀察")

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
      catalyst_scores: {ticker: bonus_points}  ← 每日依新聞量動態計算，不再固定+20
      headlines:       最重要的5條新聞標題

    修正說明（2026-05）：
      原版給每個觸發催化劑固定+20，導致台積電等大股每天永遠吃滿分，
      推薦名單永遠不變。現改為：
        1. 依當日新聞篇數比例縮放（少=小分，多=大分）
        2. 用 max 累積（避免大股靠多主題堆疊）
        3. 個股直接被點名才能再疊加直接加分
    """
    catalyst_scores: Dict[str, int] = {}
    key_headlines: List[str] = []

    # ── 1. 計算每個催化劑今日新聞篇數 ─────────────────────────────────────────
    catalyst_counts: Dict[str, int] = {}
    for catalyst, keywords in CATALYST_MAP.items():
        count = sum(
            1 for n in news_list
            if any(kw.lower() in (n["title"] + " " + n["summary"]).lower() for kw in keywords)
        )
        if count > 0:
            catalyst_counts[catalyst] = count

    triggered = set(catalyst_counts.keys())

    # 找出最相關的新聞
    for news in news_list:
        combined = news["title"] + " " + news["summary"]
        for catalyst in triggered:
            for kw in CATALYST_MAP[catalyst]:
                if kw.lower() in combined.lower():
                    if news["title"] not in key_headlines:
                        key_headlines.append(f"[{news['time']}][{news['source']}] {news['title'][:60]}")
                    break

    # ── 2. 主題加分：依新聞篇數縮放，單催化劑上限15分 ─────────────────────────
    # 原本固定+20 → 現在依篇數動態給分，讓今日熱度決定分數
    def _theme_bonus(count: int) -> int:
        if count >= 12: return 15
        if count >= 6:  return 11
        if count >= 3:  return 7
        if count >= 1:  return 4
        return 0

    # 用 max（不用+）：每股只取最強的那個催化劑主題，避免台積電靠5個主題疊到滿
    for catalyst in triggered:
        bonus = _theme_bonus(catalyst_counts[catalyst])
        for ticker in CATALYST_BENEFICIARIES.get(catalyst, []):
            prev = catalyst_scores.get(ticker, 0)
            catalyst_scores[ticker] = max(prev, bonus)

    # ── 3. 個股直接被新聞標題點名 → 疊加直接加分（每篇+4分，上限15分）──────────
    # 這讓今日真正熱門個股能浮出水面，而非永遠是固定受益股
    for ticker, info in TECH_UNIVERSE.items():
        name = info.get("name", "")
        en   = info.get("en", "")
        direct = sum(
            1 for n in news_list
            if (name and name in n["title"])
            or (en and len(en) > 3 and en.lower() in n["title"].lower())
        )
        if direct > 0:
            direct_bonus = min(15, direct * 4)
            catalyst_scores[ticker] = catalyst_scores.get(ticker, 0) + direct_bonus

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

    # 4. 催化劑 (0-30) + 外資調整
    # 上限從20提高到30，讓直接被點名的個股能獲得更高加分
    cat_score = min(30, catalyst_bonus)
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

    _tinfo = TECH_UNIVERSE.get(ticker, {})
    return {
        "ticker":      ticker,
        "name":        _tinfo.get("name", ticker.replace(".TW", "")),
        "en":          _tinfo.get("en", ""),
        "sector":      _tinfo.get("sector", ""),
        "supply":      _tinfo.get("supply", []),
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
