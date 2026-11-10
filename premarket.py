#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盤前情境（08:20 跑）：前一晚美股收盤 + 台指期夜盤 + 日韓 08:00 開盤後走勢 → 預估加權與個股開盤漲跌。

來源（皆免金鑰）：
  美股      Yahoo chart API（比 yfinance 日K 早更新）：費半、那指、S&P、台積電 ADR、輝達
  台指夜盤  mis.taifex.com.tw 即時報價（MarketType 1），05:00 收盤價
  日韓      Yahoo chart API：日經、KOSPI、三星、SK 海力士、東京威力科創（08:00 開盤）
個股預估 = beta(60 日, 對加權) × 預估加權 + 產業連動（記憶體看韓股相對強弱、半導體看費半相對 S&P）。
權重是事前設定、未經擬合；本機實驗室（~/.stock_picks/lab）每天評分這類預估。
"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import numpy as np
import pandas as pd

TW = timezone(timedelta(hours=8))
UA = {"User-Agent": "Mozilla/5.0"}
US = {"sox": "^SOX", "ndx": "^IXIC", "spx": "^GSPC", "tsm": "TSM", "nvda": "NVDA"}
ASIA = {"nikkei": "^N225", "kospi": "^KS11", "samsung": "005930.KS", "hynix": "000660.KS", "tel": "8035.T"}
MEMORY_KW = ("記憶體", "DRAM", "NAND", "快閃")
SEMI_KW = ("半導體", "晶圓", "IC", "封測", "設備", "矽", "ASIC", "記憶體")


def _get(url: str, data: Optional[bytes] = None, timeout: int = 12):
    hdr = dict(UA, **({"Content-Type": "application/json"} if data else {}))
    return json.load(urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr), timeout=timeout))


def _yahoo(symbol: str) -> Optional[dict]:
    """{'ret': 最新價對前一收盤, 'date': 最新報價的當地日期}"""
    try:
        r = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(symbol)}?range=5d&interval=1d")
        r = r["chart"]["result"][0]
        m = r["meta"]
        px = float(m["regularMarketPrice"])
        closes = [c for c in r["indicators"]["quote"][0]["close"] if c is not None]
        ts = datetime.fromtimestamp(m["regularMarketTime"], timezone(timedelta(seconds=m.get("gmtoffset", 0))))
        # 盤中（日韓剛開盤）最後一根是今天 → 前收是倒數第二根；收盤後同理
        prev = closes[-2] if len(closes) >= 2 and abs(closes[-1] - px) / px < 1e-3 else closes[-1]
        return {"ret": px / prev - 1, "date": ts.strftime("%Y-%m-%d"), "time": ts.strftime("%H:%M")}
    except Exception:
        return None


def _night_futures(spot: Optional[float]) -> Optional[dict]:
    try:
        body = json.dumps({"MarketType": "1", "SymbolType": "F", "KindID": "1", "CID": "TXF", "ExpireMonth": "",
                           "RowSize": "全部", "PageNo": "", "SortColumn": "", "AscDesc": "A"}).encode()
        q = _get("https://mis.taifex.com.tw/futures/api/getQuoteList", data=body)["RtData"]["QuoteList"]
        f = next(x for x in q if x["SymbolID"].startswith("TXF") and x["SymbolID"].endswith("-M"))
        idx = next((x for x in q if x["SymbolID"] == "TXF-P"), None)        # 臺指現貨：CRefPrice = 官方前一日收盤
        spot = float(idx["CRefPrice"]) if idx and idx.get("CRefPrice") else spot
        last, ref = float(f["CLastPrice"]), float(f["CRefPrice"])
        return {"last": last, "settle": ref, "taiex_prev": spot,
                "implied_pct": round(((last + (spot - ref)) / spot - 1) * 100, 2), "time": f["CTime"]}
    except Exception:
        return None


def premarket_context(prices: Dict[str, pd.DataFrame], taiex_close: Optional[pd.Series],
                      sectors: Dict[str, str]) -> dict:
    now = datetime.now(TW)
    today = now.strftime("%Y-%m-%d")
    us = {k: _yahoo(s) for k, s in US.items()}
    asia = {k: _yahoo(s) for k, s in ASIA.items()}
    asia_open = {k: v for k, v in asia.items() if v and v["date"] == today}      # 今天已開盤才算
    spot = float(taiex_close.iloc[-1]) if taiex_close is not None and len(taiex_close) else None
    fut = _night_futures(spot)

    r = lambda d, k: (d.get(k) or {}).get("ret")
    m_us = None
    if r(us, "sox") is not None and r(us, "spx") is not None:
        m_us = 0.35 * r(us, "sox") + 0.25 * r(us, "spx")          # 美股隔夜對加權的粗略敏感度
    a = [r(asia_open, k) for k in ("nikkei", "kospi") if r(asia_open, k) is not None]
    m_asia = 0.8 * float(np.mean(a)) if a else None
    parts = [(0.7, fut["implied_pct"] / 100) if fut else None, (0.3, m_asia) if m_asia is not None else None]
    parts = [p for p in parts if p]
    if not parts and m_us is not None:
        parts = [(1.0, m_us)]
    M = sum(w * x for w, x in parts) / sum(w for w, _ in parts) if parts else 0.0
    source = " + ".join(n for n, ok in (("台指夜盤", fut), ("日韓開盤", m_asia is not None)) if ok) or ("美股迴歸" if m_us is not None else "無資料")

    mem_rel = None
    if r(asia_open, "samsung") is not None and r(asia_open, "hynix") is not None and r(asia_open, "kospi") is not None:
        mem_rel = (r(asia_open, "samsung") + r(asia_open, "hynix")) / 2 - r(asia_open, "kospi")
    semi_rel = (r(us, "sox") - r(us, "spx")) if r(us, "sox") is not None and r(us, "spx") is not None else None

    tx = taiex_close.pct_change().dropna() if taiex_close is not None else None
    est = {}
    for t, df in prices.items():
        try:
            s = df["Close"].pct_change().dropna()
            j = pd.concat([s, tx], axis=1, join="inner").tail(60)
            beta = float(j.cov().iloc[0, 1] / j.iloc[:, 1].var()) if len(j) >= 30 else 1.0
            e = float(np.clip(beta, 0.2, 2.5)) * M
            sec = sectors.get(t, "")
            if mem_rel is not None and any(k in sec for k in MEMORY_KW):
                e += 0.5 * mem_rel
            elif semi_rel is not None and any(k in sec for k in SEMI_KW):
                e += 0.3 * semi_rel
            est[t] = round(float(np.clip(e, -0.1, 0.1)) * 100, 2)
        except Exception:
            continue

    pct = lambda d: {k: (round(v["ret"] * 100, 2) if v else None) for k, v in d.items()}
    return {
        "asof": now.strftime("%Y-%m-%d %H:%M"),
        "us": pct(us), "us_date": (us.get("sox") or {}).get("date"),
        "asia": pct(asia), "asia_open": sorted(asia_open), "asia_time_local": (asia.get("kospi") or {}).get("time"),
        "night_futures": fut,
        "taiex_est_pct": round(M * 100, 2), "source": source, "est": est,
    }


def adjust(pick: dict, est_pct: Optional[float]) -> float:
    """排名用加減分：預估開盤漲跌 ×3，限 ±8 分；並加上追高/開低標籤。"""
    if est_pct is None:
        return 0.0
    pick["premarket_est_pct"] = est_pct
    if est_pct >= 5:          # 跳空太大：買在開盤等於追高 → 不加分
        pick.setdefault("labels", []).insert(0, f"預估開高 +{est_pct:.1f}%，勿追高")
        return 0.0
    elif est_pct <= -3:
        pick.setdefault("labels", []).insert(0, f"預估開低 {est_pct:.1f}%")
    return float(np.clip(est_pct * 3, -8, 8))
