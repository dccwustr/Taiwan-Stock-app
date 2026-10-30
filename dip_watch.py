#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大盤急跌偵測 + 反彈候補紀錄（只記錄、不推薦）。

  app.py          → market_drop() 決定要不要顯示「大盤急跌日」橫幅
  morning_picks.py→ log_dip_candidates() 把急跌日的反彈候補寫進 data/dip_log.csv
  forward_test.py --dip → 追蹤這些候補事後有沒有真的反彈

候補只進紀錄檔，不進 top_picks、不顯示在 app，等樣本夠了再決定要不要上線。
"""
import os

DIP_ALERT_PCT = -2.0   # 加權指數單日跌幅 ≤ 此值 → app 顯示橫幅
DIP_LOG_PCT   = -1.5   # 單日跌幅 ≤ 此值 → 記錄反彈候補（門檻較寬，樣本累積快一點）
DRAWDOWN_PCT  = -5.0   # 距 20 日高點跌幅 ≤ 此值 → 也算急跌（連續幾天小跌累積）
STOCK_DROP_PCT = -3.0  # 個股單日跌幅 ≤ 此值才算「跌深」
DIP_LOG_PATH  = os.path.join("data", "dip_log.csv")


def market_drop(taiex_close) -> dict:
    """TAIEX 單日漲跌與距 20 日高點跌幅。資料不足時 chg1d/drawdown 為 None。"""
    out = {"chg1d": None, "drawdown": None, "alert": False, "log": False}
    if taiex_close is None or len(taiex_close) < 21:
        return out
    close = taiex_close.dropna()
    last, prev = float(close.iloc[-1]), float(close.iloc[-2])
    high20 = float(close.iloc[-20:].max())
    out["chg1d"] = round((last / prev - 1) * 100, 2)
    out["drawdown"] = round((last / high20 - 1) * 100, 2)
    out["alert"] = out["chg1d"] <= DIP_ALERT_PCT or out["drawdown"] <= DRAWDOWN_PCT
    out["log"] = out["chg1d"] <= DIP_LOG_PCT or out["drawdown"] <= DRAWDOWN_PCT
    return out


def _stock_chg1d(df) -> float:
    close = df["Close"].dropna()
    if len(close) < 2 or float(close.iloc[-2]) <= 0:
        return 0.0
    return (float(close.iloc[-1]) / float(close.iloc[-2]) - 1) * 100


def dip_candidates(scored: list, prices: dict) -> list:
    """
    跌深但基本面沒壞的股票：個股單日跌 ≥3%、月營收年增 > 0、不在第四階段（下跌趨勢）。
    依跌幅排序（跌越多越前面）。
    """
    out = []
    for pk in scored:
        df = prices.get(pk["ticker"])
        if df is None:
            continue
        chg = _stock_chg1d(df)
        if chg > STOCK_DROP_PCT or pk.get("rev_yoy", 0) <= 0 or pk.get("stage") == 4:
            continue
        out.append({**pk, "chg1d": round(chg, 2)})
    out.sort(key=lambda p: p["chg1d"])
    return out


def log_dip_candidates(result: dict, scored: list, prices: dict, taiex_close,
                       path: str = DIP_LOG_PATH) -> int:
    """急跌日才記錄。回傳新增筆數；非急跌日回傳 0。"""
    drop = market_drop(taiex_close)
    if not drop["log"]:
        return 0
    from pick_log import FIELDS, append_picks
    picks = [{**c, "taiex_chg": drop["chg1d"], "taiex_dd": drop["drawdown"]}
             for c in dip_candidates(scored, prices)]
    return append_picks({**result, "top_picks": picks}, path,
                        fields=FIELDS + ["chg1d", "taiex_chg", "taiex_dd"])
