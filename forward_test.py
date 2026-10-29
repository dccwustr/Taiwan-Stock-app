#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前向測試 — 把 data/pick_log.csv 的每筆精選對照其後的實際走勢。

進場參考價 = 精選當時的 last_price（前一交易日收盤）。
  ret_5d / ret_20d : 精選日起第 5 / 20 個交易日收盤報酬 (%)
  ex_5d / ex_20d   : 減去同期加權指數報酬 (%)
  outcome          : 20 個交易日內先碰停損 / 先碰目標 / 皆未碰（同日兩者都碰以停損計，較保守）
尚未走滿的天數留空，不計入統計。

  python forward_test.py        # 輸出 data/forward_test.csv 並印出摘要
"""
import csv, os, sys, warnings
from collections import defaultdict

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
LOG_PATH = os.path.join("data", "pick_log.csv")
OUT_PATH = os.path.join("data", "forward_test.csv")


def _download(tickers, start):
    out = {}
    for t in tickers:
        # 上櫃股在 yfinance 是 .TWO；.TW 抓不到時改試 .TWO
        for sym in ([t, t[:-3] + ".TWO"] if t.endswith(".TW") else [t]):
            try:
                df = yf.download(sym, start=start, auto_adjust=True, progress=False,
                                 threads=False, timeout=15)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                if df is not None and not df.empty:
                    out[t] = df
                    break
            except Exception as e:
                print(f"  ! {sym}: {e}", file=sys.stderr)
    return out


def _ret(df, date, n, base):
    """% return from base to the close of the n-th trading day on/after date."""
    fwd = df[df.index >= pd.Timestamp(date)]
    if len(fwd) < n or base <= 0:
        return None
    return (float(fwd["Close"].iloc[n - 1]) / base - 1) * 100


def _outcome(df, date, stop, target):
    fwd = df[df.index >= pd.Timestamp(date)].head(20)
    for _, bar in fwd.iterrows():
        if stop and float(bar["Low"]) <= stop:
            return "stop"
        if target and float(bar["High"]) >= target:
            return "target"
    return "open" if len(fwd) < 20 else "neither"


def run():
    if not os.path.exists(LOG_PATH):
        sys.exit("no data/pick_log.csv — run pick_log.py first")
    with open(LOG_PATH, encoding="utf-8", newline="") as f:
        picks = list(csv.DictReader(f))
    start = min(p["date"] for p in picks)
    px = _download({p["ticker"] for p in picks} | {"^TWII"}, start)
    mkt = px.get("^TWII")

    rows = []
    for p in picks:
        df = px.get(p["ticker"])
        if df is None:
            continue
        base = float(p["last_price"] or 0)
        r = dict(p)
        for n in (5, 20):
            ret = _ret(df, p["date"], n, base)
            mret = _ret(mkt, p["date"], n, _ret_base(mkt, p["date"])) if mkt is not None else None
            r[f"ret_{n}d"] = round(ret, 2) if ret is not None else ""
            r[f"ex_{n}d"] = round(ret - mret, 2) if ret is not None and mret is not None else ""
        r["outcome"] = _outcome(df, p["date"],
                                float(p["stop_loss"] or 0), float(p["target_price"] or 0))
        rows.append(r)

    if not rows:
        sys.exit("no price data downloaded (rate limited?) — keeping existing output")
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summarize(rows)


def _ret_base(mkt, date):
    """TAIEX close the trading day before `date`, matching the picks' reference price."""
    prev = mkt[mkt.index < pd.Timestamp(date)]
    return float(prev["Close"].iloc[-1]) if len(prev) else 0.0


def _stats(label, rows, key):
    v = [float(r[key]) for r in rows if r[key] != ""]
    if not v:
        return f"  {label:<12} n=0"
    win = sum(x > 0 for x in v) / len(v) * 100
    return f"  {label:<12} n={len(v):<4} avg={sum(v)/len(v):+6.2f}%  win={win:4.0f}%"


def summarize(rows):
    print(f"\n=== 前向測試 ({len(rows)} 筆精選, "
          f"{len({r['date'] for r in rows})} 個交易日) ===")
    for n in (5, 20):
        print(f"\n{n} 日報酬")
        print(_stats("全部", rows, f"ret_{n}d"))
        print(_stats("超額(vs大盤)", rows, f"ex_{n}d"))
        buckets = defaultdict(list)
        for r in rows:
            s = float(r["score"] or 0)
            buckets["score>=80" if s >= 80 else "score 60-79" if s >= 60 else "score<60"].append(r)
        for k in sorted(buckets):
            print(_stats(k, buckets[k], f"ret_{n}d"))
        for rk, lab in ((lambda r: int(r["rank"]) <= 3, "排名前3"),):
            print(_stats(lab, [r for r in rows if rk(r)], f"ret_{n}d"))
    oc = defaultdict(int)
    for r in rows:
        oc[r["outcome"]] += 1
    print(f"\n20日內先碰: 目標 {oc['target']} / 停損 {oc['stop']} / "
          f"皆未碰 {oc['neither']} / 未走完 {oc['open']}")
    print(f"明細: {OUT_PATH}\n")


if __name__ == "__main__":
    run()
