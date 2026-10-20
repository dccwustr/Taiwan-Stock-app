#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
資金流向補資料（收盤後 / collector 沒跑到時）
──────────────────────────────────────────
用 yfinance 1 分 K 估算：本分鐘收盤 > 上分鐘 → 流入；< → 流出；相同 → 沿用前一個方向。
精度比盤中內外盤法粗，但足以看出整天的類股輪動。會覆寫當天資料。

python3 flow_backfill.py [--no-push]
"""
import argparse, json, sys, time, warnings
from typing import Dict

import requests

import flow_core as fc
from flow_collector import BATCH, MIS_URL, _f, export, log

warnings.filterwarnings("ignore")


def mis_states(universe) -> Dict[str, Dict]:
    """收盤價 / 昨收 / 總量（證交所 MIS），順便確認今天有沒有開盤"""
    sess = requests.Session(); sess.headers["User-Agent"] = "Mozilla/5.0"
    syms = [f'{s["market"]}_{s["code"]}.tw' for s in universe]
    out = {}
    for i in range(0, len(syms), BATCH):
        r = sess.get(MIS_URL, params={"ex_ch": "|".join(syms[i:i + BATCH]), "json": 1, "delay": 0}, timeout=20)
        for m in json.loads(r.text.strip()).get("msgArray", []):
            out[m["c"]] = m
        time.sleep(0.3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    import yfinance as yf

    universe = fc.load_universe()
    meta = {s["code"]: s for s in universe}
    states = mis_states(universe)
    today = fc.now_tw().strftime("%Y%m%d")
    date = fc.now_tw().strftime("%Y-%m-%d")
    live = {c: m for c, m in states.items() if m.get("d") == today and c in meta}
    if not live:
        log.warning("backfill: no trading data for today")
        return
    # 只抓今天有成交的股票
    traded = [c for c, m in live.items() if int(m.get("v") or 0) > 0]
    tick = {c: f'{c}.{"TW" if meta[c]["market"] == "tse" else "TWO"}' for c in traded}
    log.info("backfill: %d traded stocks, downloading 1m bars", len(traded))

    flows, done = [], set()
    pending = list(tick.values())
    for rnd in range(4):                       # Yahoo 會限流 → 失敗的分批重試
        if not pending:
            break
        if rnd:
            log.info("retry round %d: %d tickers, cooling down 60s", rnd, len(pending))
            time.sleep(60)
        for i in range(0, len(pending), 100):
            chunk = pending[i:i + 100]
            try:
                df = yf.download(chunk, period="1d", interval="1m", group_by="ticker",
                                 threads=4, progress=False, auto_adjust=False)
            except Exception as e:
                log.warning("download failed: %s", e)
                time.sleep(10)
                continue
            for tk in chunk:
                code = tk.split(".")[0]
                try:
                    d = df[tk].dropna(subset=["Close"])
                except KeyError:
                    continue
                if d.empty:
                    continue
                done.add(tk)
                prev, sign = _f(live[code].get("y")), 0
                for ts, row in d.iterrows():
                    c, v = float(row["Close"]), float(row["Volume"] or 0)
                    if prev:
                        sign = ((c > prev) - (c < prev)) or sign
                    prev = c
                    if v <= 0 or not sign:
                        continue
                    amt = v * c
                    flows.append((ts.tz_convert("Asia/Taipei").strftime("%H:%M"), code,
                                  amt if sign > 0 else 0.0, amt if sign < 0 else 0.0))
            time.sleep(3)
        pending = [t for t in pending if t not in done]
        log.info("round %d: %d/%d tickers have bars", rnd, len(done), len(tick))

    con = fc.connect()
    con.execute("DELETE FROM minute_flow WHERE date=?", (date,))
    con.execute("DELETE FROM stock_state WHERE date=?", (date,))
    fc.add_flows(con, date, flows)
    stamp = fc.now_tw().strftime("%H:%M:%S")
    fc.upsert_states(con, date, [
        (c, meta[c]["name"], meta[c]["ind"], meta[c]["market"],
         _f(m.get("z")) or _f(m.get("pz")), _f(m.get("y")), int(m.get("v") or 0), stamp, "yf")
        for c, m in live.items()
    ])
    con.commit()
    log.info("backfill: %d minute-flow rows written for %s", len(flows), date)
    export(con, push=not args.no_push)


if __name__ == "__main__":
    sys.exit(main())
