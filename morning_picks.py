#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股早安精選 — 每日 08:30 台灣時間自動執行
分析全市場籌碼、基本面、技術面，輸出 data/morning_picks.json
供 Streamlit app 顯示「今日精選」，也供 remote CCR agent 產出 Google Drive 報告。
"""
import sys, json, warnings, io, contextlib, os
from datetime import datetime, timezone, timedelta

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from widget import (
    TECH_UNIVERSE,
    fetch_prices_batch,
    fetch_cnyes_news,
    fetch_twse_foreign_buying,
    fetch_twse_foreign_multi_day, calc_foreign_streak,
    fetch_twse_trust_multi_day,   calc_trust_streak,
    fetch_twse_margin_balance,
    fetch_twse_monthly_revenue,
    calc_market_direction,
    fetch_taiex_prices,
    score_stock,
    calc_fundamental_bonus,
    analyze_catalysts,
    fetch_yf_fundamentals_batch,
    calc_relative_strength,
)

TST = timezone(timedelta(hours=8))


def run_morning_analysis(verbose: bool = True) -> dict:
    tw_now = datetime.now(tz=TST)

    def log(msg):
        if verbose:
            print(f"[{tw_now.strftime('%H:%M')} TST] {msg}", flush=True)

    log("=== 台股早安精選分析開始 ===")

    # ── 1. 股價 (1y 供 MA200/SEPA) ────────────────────────────────────────────
    log("下載股價 (1y)...")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        prices = fetch_prices_batch(list(TECH_UNIVERSE.keys()), period="1y")
    log(f"  → {len(prices)} 支股票")

    # ── 2. 籌碼面 ─────────────────────────────────────────────────────────────
    log("抓取三大法人 + 融資融券...")
    foreign       = fetch_twse_foreign_buying()
    foreign_multi = fetch_twse_foreign_multi_day(days=5)
    fi_streak     = calc_foreign_streak(foreign_multi)
    trust_multi   = fetch_twse_trust_multi_day(days=5)
    trust_streak  = calc_trust_streak(trust_multi)
    margin_bal    = fetch_twse_margin_balance()
    log(f"  → 外資 {len(foreign)} 筆 | 投信連買 {sum(1 for v in trust_streak.values() if v>0)} 支 | 融資券 {len(margin_bal)} 筆")

    # ── 3. 大盤方向 (CANSLIM M factor) ────────────────────────────────────────
    log("計算大盤方向...")
    taiex_close  = fetch_taiex_prices()
    mkt_dir      = calc_market_direction(taiex_close)
    _mkt_penalty = mkt_dir.get("penalty", 0)
    log(f"  → {mkt_dir.get('label','未知')} | 懲罰 {_mkt_penalty:+d} 分")

    # ── 4. 新聞催化劑 ─────────────────────────────────────────────────────────
    log("抓取新聞...")
    try:
        news = fetch_cnyes_news(limit=80)
    except Exception:
        news = []
    cat_sc, headlines = analyze_catalysts(news)
    log(f"  → 新聞 {len(news)} 則 | 有催化劑 {len(cat_sc)} 支")

    # ── 5. 基本面 (yfinance + MOPS月營收) ─────────────────────────────────────
    log("抓取基本面 (yfinance + MOPS)...")
    fund_raw    = fetch_yf_fundamentals_batch(list(TECH_UNIVERSE.keys()))
    monthly_rev = fetch_twse_monthly_revenue()
    for tk, yoy in monthly_rev.items():
        fund_raw.setdefault(tk, {})["monthly_rev_yoy"] = yoy
    log(f"  → 季報 {len(fund_raw)} 筆 | 月營收 {len(monthly_rev)} 筆")

    # ── 6. 評分 ────────────────────────────────────────────────────────────────
    log("評分中...")
    scored = []

    for ticker in TECH_UNIVERSE:
        df = prices.get(ticker)
        if df is None or len(df) < 22:
            continue

        res = score_stock(
            ticker, df,
            catalyst_bonus    = cat_sc.get(ticker, 0),
            foreign_net       = foreign.get(ticker, 0),
            fi_streak_val     = fi_streak.get(ticker, 0),
            trust_streak_val  = trust_streak.get(ticker, 0),
            margin_chg_pct    = margin_bal.get(ticker, {}).get("margin_chg_pct",     0.0),
            short_margin_ratio= margin_bal.get(ticker, {}).get("short_margin_ratio", 0.0),
        )
        if not res:
            continue

        # 零股小資 RSI + 高價 adjustments
        rsi = res.get("rsi", 50)
        adj = 0
        if   rsi > 82: adj -= 30
        elif rsi > 78: adj -= 20
        elif rsi > 72: adj -= 12
        elif rsi > 68: adj -=  4
        elif rsi >= 40: adj +=  8
        elif rsi >= 35: adj +=  3
        else:           adj -= 15
        if res.get("last_price", 0) > 500:
            adj -= 8
        adj += _mkt_penalty

        # 基本面加權
        fund = calc_fundamental_bonus(ticker, fund_raw, {})
        final_score = max(0, min(100, res["score"] + adj + fund["bonus"]))

        # 相對強度 (RS)
        rs_bonus = 0
        try:
            _cl = df["Close"] if "Close" in df.columns else None
            rs  = calc_relative_strength(_cl, taiex_close)
            rs_bonus    = rs.get("bonus", 0)
            rs_composite = rs.get("rs_composite", 0.0)
            final_score = max(0, min(100, final_score + rs_bonus))
        except Exception:
            rs_composite = 0.0

        # 建立顯示標籤
        _mc  = res.get("margin_chg_pct",     0.0)
        _smr = res.get("short_margin_ratio",  0.0)
        labels: list = []
        if _mc  >= 25:  labels.append(f"融資暴增+{_mc:.0f}% ⚠️")
        elif _mc <= -15: labels.append(f"融資大減{_mc:.0f}% 清洗")
        if _smr >= 30:  labels.append(f"券資比{_smr:.0f}% 潛在軋空")
        labels = (fund["labels"] + labels)[:5]

        price = res["last_price"]
        scored.append({
            "ticker":             ticker,
            "name":               res.get("name", ticker),
            "sector":             TECH_UNIVERSE.get(ticker, {}).get("sector", ""),
            "score":              final_score,
            "last_price":         price,
            "rsi":                round(res["rsi"], 1),
            "stage":              res.get("stage", 0),
            "stage_label":        res.get("stage_label", ""),
            "bo_type":            res.get("bo_type", ""),
            "bo_label":           res.get("bo_label", ""),
            "trust_bonus":        res.get("trust_bonus", 0),
            "margin_score":       res.get("margin_score", 0),
            "margin_chg_pct":     round(_mc, 1),
            "short_margin_ratio": round(_smr, 1),
            "kd_signal":          res.get("kd_signal", "neutral"),
            "bb_signal":          res.get("bb_signal", "neutral"),
            "mom5d":              round(res.get("mom5d",  0.0), 2),
            "mom20d":             round(res.get("mom20d", 0.0), 2),
            "rev_yoy":            round(fund.get("rev_yoy",  0.0), 1),
            "earn_yoy":           round(fund.get("earn_yoy", 0.0), 1),
            "rs_composite":       round(rs_composite, 1),
            "labels":             labels,
            "stop_loss":          round(res.get("stop_loss", 0.0), 2),
            "target_price":       round(res.get("target_price", 0.0), 2),
            "target_pct":         res.get("target_pct", 5.0),
            "affordability":      int(10000 / price) if price > 0 else 0,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    log(f"  → {len(scored)} 支完成評分 | 前3名: {', '.join(p['ticker'] for p in scored[:3])}")

    output = {
        "generated_at":     tw_now.strftime("%Y-%m-%d %H:%M TST"),
        "date":             tw_now.strftime("%Y-%m-%d"),
        "market_direction": {
            "label":   mkt_dir.get("label",  ""),
            "penalty": mkt_dir.get("penalty", 0),
            "stage":   mkt_dir.get("stage",  ""),
            "taiex_vs_ma50":  mkt_dir.get("taiex_vs_ma50",  0.0),
            "taiex_vs_ma200": mkt_dir.get("taiex_vs_ma200", 0.0),
        },
        "top_picks":       scored[:10],
        "total_scored":    len(scored),
        "top_headlines":   headlines[:5],
    }

    log(f"=== 分析完成 ===")
    return output


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="台股早安精選分析")
    p.add_argument("--output",  default="data/morning_picks.json", help="輸出路徑")
    p.add_argument("--quiet",   action="store_true",               help="靜音模式")
    args = p.parse_args()

    result = run_morning_analysis(verbose=not args.quiet)

    out_path = args.output
    if os.path.dirname(out_path):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 報告已儲存至 {out_path}")
    print(f"   生成時間: {result['generated_at']}")
    print(f"   大盤方向: {result['market_direction']['label']}")
    if result["top_picks"]:
        print(f"   今日精選前3名:")
        for pk in result["top_picks"][:3]:
            print(f"     {pk['name']}({pk['ticker']}) {pk['score']}分 | "
                  f"NT${pk['last_price']} | RSI {pk['rsi']} | {pk['stage_label']}")
