#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前向測試 — 把 data/pick_log.csv 的每筆精選對照其後的實際走勢。

進場 = 盤前（09:00 前）產生的精選用當日開盤價；其餘用下一個交易日開盤價
       （GitHub 排程曾晚到 12:46–14:56 才發布，last_price 已是當日價，用當日 K 棒會偷看未來）。
  ret_5d / ret_20d : 進場後第 5 / 20 個交易日收盤報酬 (%)，已扣來回成本 0.585%
  ex_5d / ex_20d   : 減去同期加權指數（同樣開盤到收盤、不扣成本）
  outcome          : 進場後 20 個交易日內先碰停損 / 先碰目標 / 皆未碰（同日兩者都碰以停損計，較保守）
尚未走滿的天數留空，不計入統計。

  python forward_test.py        # 輸出 data/forward_test.csv 並印出摘要
  python forward_test.py --dip  # 大盤急跌日的反彈候補 → data/dip_forward_test.csv
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


COST_PCT = 0.585   # 手續費 0.1425%×2 + 證交稅 0.3%


def _is_premarket(generated_at):
    """generated_at = 'YYYY-MM-DD HH:MM TST'；舊紀錄沒有這欄 → 視為非盤前。"""
    return bool(generated_at) and generated_at[11:16] < "09:00"


def _forward(df, date, premarket=False):
    """可實際進場之後的 K 棒。"""
    ts = pd.Timestamp(date)
    return df[df.index >= ts] if premarket else df[df.index > ts]


def _ret(df, date, n, cost=0.0, premarket=False):
    """% return from the entry session's open to the close of the n-th session."""
    fwd = _forward(df, date, premarket)
    if len(fwd) < n or float(fwd["Open"].iloc[0]) <= 0:
        return None
    return (float(fwd["Close"].iloc[n - 1]) / float(fwd["Open"].iloc[0]) - 1) * 100 - cost


def _outcome(df, date, stop, target, premarket=False):
    fwd = _forward(df, date, premarket).head(20)
    for _, bar in fwd.iterrows():
        if stop and float(bar["Low"]) <= stop:
            return "stop"
        if target and float(bar["High"]) >= target:
            return "target"
    return "open" if len(fwd) < 20 else "neither"


def run(log_path=LOG_PATH, out_path=OUT_PATH):
    if not os.path.exists(log_path):
        sys.exit(f"no {log_path} — nothing logged yet")
    with open(log_path, encoding="utf-8", newline="") as f:
        picks = list(csv.DictReader(f))
    start = min(p["date"] for p in picks)
    px = _download({p["ticker"] for p in picks} | {"^TWII"}, start)
    mkt = px.get("^TWII")

    rows = []
    for p in picks:
        df = px.get(p["ticker"])
        if df is None:
            continue
        r = dict(p)
        pre = _is_premarket(p.get("generated_at"))
        for n in (5, 20):
            ret = _ret(df, p["date"], n, COST_PCT, pre)
            mret = _ret(mkt, p["date"], n, 0.0, pre) if mkt is not None else None
            r[f"ret_{n}d"] = round(ret, 2) if ret is not None else ""
            r[f"ex_{n}d"] = round(ret - mret, 2) if ret is not None and mret is not None else ""
        r["outcome"] = _outcome(df, p["date"], float(p["stop_loss"] or 0),
                                float(p["target_price"] or 0), pre)
        rows.append(r)

    if not rows:
        sys.exit("no price data downloaded (rate limited?) — keeping existing output")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summarize(rows, out_path)


def _stats(label, rows, key):
    v = [float(r[key]) for r in rows if r[key] != ""]
    if not v:
        return f"  {label:<12} n=0"
    win = sum(x > 0 for x in v) / len(v) * 100
    return f"  {label:<12} n={len(v):<4} avg={sum(v)/len(v):+6.2f}%  win={win:4.0f}%"


def summarize(rows, out_path=OUT_PATH):
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
    print(f"明細: {out_path}\n")


if __name__ == "__main__":
    if "--dip" in sys.argv:
        run(os.path.join("data", "dip_log.csv"), os.path.join("data", "dip_forward_test.csv"))
    else:
        run()
