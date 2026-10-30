#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大師鏡頭 — 用 yfinance 年報（約 4 年）替每檔股票做三套長期基本面檢查：

  巴菲特 (0-8)   : 高 ROE、低負債、毛利率高且穩、自由現金流、盈餘成長、資本支出輕、業主盈餘殖利率
  Piotroski (0-9): 財報是否「比去年更好」— 獲利、現金流、槓桿、流動性、稀釋、毛利率、資產週轉
  Lynch 分類     : 慢速 / 穩健 / 快速成長 / 景氣循環 / 轉機；成長股算 PEG，景氣循環股改看 P/B

每週由 GitHub Action 執行一次（年報一季才變一次，且逐檔抓會被 Yahoo 限流），
app 只讀 data/master_lenses.json。抓不到的股票保留上一次的結果，不會被清空。
每次執行也把分數附加到 data/lens_log.csv，之後供前向測試驗證哪個鏡頭在台股真的有效。

  python master_lenses.py                 # 全部股票池
  python master_lenses.py 2330.TW 2454.TW # 只跑指定股票（測試用）
"""
import csv, json, math, os, sys, time, warnings
from datetime import datetime, timedelta, timezone

warnings.filterwarnings("ignore")
OUT_PATH = os.path.join("data", "master_lenses.json")
LOG_PATH = os.path.join("data", "lens_log.csv")
TST = timezone(timedelta(hours=8))

# 不適用：銀行/金控沒有毛利率、槓桿本來就高；ETF 不是公司
NOT_APPLICABLE = {"金融", "ETF"}
# Lynch：景氣循環股本益比最低時往往是獲利高峰，不能用低 P/E 當便宜
CYCLICAL_SECTORS = {
    "記憶體", "DRAM", "NAND控制器", "記憶體封測", "面板", "航運", "航空", "鋼鐵", "石化",
    "被動元件", "矽晶圓", "IC載板", "玻纖布", "PCB", "高階PCB", "PCB材料",
    "水泥", "水泥/綠能", "太陽能", "太陽能電池", "建設",
}

ROWS = {
    "ni":     ("Net Income", "Net Income Common Stockholders"),
    "rev":    ("Total Revenue", "Operating Revenue"),
    "gp":     ("Gross Profit",),
    "eq":     ("Stockholders Equity", "Common Stock Equity"),
    "ta":     ("Total Assets",),
    "ltd":    ("Long Term Debt",),
    "ca":     ("Current Assets",),
    "cl":     ("Current Liabilities",),
    "shares": ("Ordinary Shares Number", "Share Issued"),
    "ocf":    ("Operating Cash Flow",),
    "capex":  ("Capital Expenditure",),
    "fcf":    ("Free Cash Flow",),
}


def _num(v):
    try:
        v = float(v)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def years_from_statements(income, balance, cashflow) -> list:
    """
    合併三張年報成 [{year, ni, rev, ...}, ...]，由舊到新。
    只保留有淨利與營收的年度（yfinance 最舊一欄常是空的）。
    """
    by_year = {}
    for df in (income, balance, cashflow):
        if df is None or df.empty:
            continue
        for col in df.columns:
            y = by_year.setdefault(col.year, {"year": col.year})
            for key, names in ROWS.items():
                if y.get(key) is not None:
                    continue
                for n in names:
                    if n in df.index and _num(df.at[n, col]) is not None:
                        y[key] = _num(df.at[n, col])
                        break
    years = [y for y in by_year.values() if y.get("ni") is not None and y.get("rev")]
    return sorted(years, key=lambda y: y["year"])


def _ratio(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def buffett(years: list, market_cap) -> dict:
    """8 項檢查，資料缺的項目算未通過。"""
    if len(years) < 2:
        return {"score": None, "checks": {}}
    last = years[-1]
    roe = [_ratio(y["ni"], y.get("eq")) for y in years]
    gm = [_ratio(y.get("gp"), y["rev"]) for y in years]
    fcf = [y.get("fcf") if y.get("fcf") is not None else
           (y["ocf"] + y["capex"] if y.get("ocf") is not None and y.get("capex") is not None else None)
           for y in years]
    ocf_sum = sum(y.get("ocf") or 0 for y in years)
    capex_sum = sum(abs(y.get("capex") or 0) for y in years)
    checks = {
        "ROE 每年 ≥15%":       all(r is not None and r >= 0.15 for r in roe),
        "長期負債 ≤ 3 年淨利":  last["ni"] > 0 and (last.get("ltd") or 0) <= 3 * last["ni"],
        "毛利率 ≥30%":          gm[-1] is not None and gm[-1] >= 0.30,
        "毛利率穩定 (±5%)":     all(g is not None for g in gm) and max(gm) - min(gm) <= 0.10,
        "自由現金流每年 >0":    all(f is not None and f > 0 for f in fcf),
        "淨利每年 >0 且成長":   all(y["ni"] > 0 for y in years) and years[-1]["ni"] > years[0]["ni"],
        "資本支出 ≤ 營業現金流一半": ocf_sum > 0 and capex_sum <= 0.5 * ocf_sum,
        "業主盈餘殖利率 ≥5%":   fcf[-1] is not None and bool(market_cap) and fcf[-1] / market_cap >= 0.05,
    }
    return {"score": sum(checks.values()), "checks": checks}


def piotroski(years: list) -> dict:
    """標準 9 項 F-Score，比較最近兩個年度。"""
    if len(years) < 2:
        return {"score": None, "checks": {}}
    p, c = years[-2], years[-1]
    roa_c, roa_p = _ratio(c["ni"], c.get("ta")), _ratio(p["ni"], p.get("ta"))
    lev_c, lev_p = _ratio(c.get("ltd") or 0, c.get("ta")), _ratio(p.get("ltd") or 0, p.get("ta"))
    cr_c, cr_p = _ratio(c.get("ca"), c.get("cl")), _ratio(p.get("ca"), p.get("cl"))
    gm_c, gm_p = _ratio(c.get("gp"), c["rev"]), _ratio(p.get("gp"), p["rev"])
    at_c, at_p = _ratio(c["rev"], c.get("ta")), _ratio(p["rev"], p.get("ta"))
    gt = lambda a, b: a is not None and b is not None and a > b
    checks = {
        "ROA >0":           roa_c is not None and roa_c > 0,
        "營業現金流 >0":     (c.get("ocf") or 0) > 0,
        "ROA 提升":          gt(roa_c, roa_p),
        "現金流 > 淨利":     c.get("ocf") is not None and c["ocf"] > c["ni"],
        "長期負債比下降":    lev_c is not None and lev_p is not None and lev_c <= lev_p,
        "流動比率提升":      gt(cr_c, cr_p),
        "沒有增發股票":      c.get("shares") is not None and p.get("shares") is not None
                             and c["shares"] <= p["shares"] * 1.001,
        "毛利率提升":        gt(gm_c, gm_p),
        "資產週轉率提升":    gt(at_c, at_p),
    }
    return {"score": sum(checks.values()), "checks": checks}


def lynch(years: list, sector: str, trailing_pe, price_to_book) -> dict:
    """Lynch 六分類（不含資產股）+ PEG。"""
    if len(years) < 2:
        return {"category": None}
    ni = [y["ni"] for y in years]
    span = years[-1]["year"] - years[0]["year"]
    growth = None
    if ni[0] > 0 and ni[-1] > 0 and span > 0:
        growth = ((ni[-1] / ni[0]) ** (1 / span) - 1) * 100
    big_drop = any(b < a * 0.7 for a, b in zip(ni, ni[1:]) if a > 0)

    # 循環產業虧轉盈仍是景氣循環（Lynch：別把循環谷底反彈當轉機）
    if sector in CYCLICAL_SECTORS:
        cat = "景氣循環股"
    elif ni[-1] > 0 and ni[-2] < 0:
        cat = "轉機股"
    elif big_drop:
        cat = "景氣循環股"
    elif growth is None:
        cat = "虧損中"
    elif growth >= 20:
        cat = "快速成長股"
    elif growth >= 10:
        cat = "穩健成長股"
    else:
        cat = "慢速成長股"

    peg = None
    if cat in ("快速成長股", "穩健成長股", "慢速成長股") and trailing_pe and growth and growth > 0:
        peg = round(trailing_pe / growth, 2)
    return {
        "category": cat,
        "growth_pct": round(growth, 1) if growth is not None else None,
        "peg": peg,
        "pb": round(price_to_book, 2) if price_to_book else None,
        "pass": peg is not None and peg < 1,
    }


def analyze(ticker: str, sector: str, stmts: dict) -> dict:
    if sector in NOT_APPLICABLE:
        return {"na": True, "sector": sector}
    years = years_from_statements(stmts.get("income"), stmts.get("balance"), stmts.get("cashflow"))
    info = stmts.get("info") or {}
    return {
        "sector": sector,
        "years": [y["year"] for y in years],
        "buffett": buffett(years, info.get("marketCap")),
        "piotroski": piotroski(years),
        "lynch": lynch(years, sector, info.get("trailingPE"), info.get("priceToBook")),
    }


def _fetch(ticker: str) -> dict:
    import yfinance as yf
    syms = [ticker, ticker[:-3] + ".TWO"] if ticker.endswith(".TW") else [ticker]
    for sym in syms:
        t = yf.Ticker(sym)
        income = t.income_stmt
        if income is None or income.empty:
            continue
        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass
        return {"income": income, "balance": t.balance_sheet, "cashflow": t.cashflow, "info": info}
    return {}


def run(tickers: dict, pause: float = 1.0) -> dict:
    old = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, encoding="utf-8") as f:
            old = json.load(f).get("tickers", {})
    out, failed = dict(old), []
    for i, (tk, meta) in enumerate(tickers.items(), 1):
        sector = meta.get("sector", "")
        try:
            stmts = {} if sector in NOT_APPLICABLE else _fetch(tk)
            if sector not in NOT_APPLICABLE and not stmts:
                raise ValueError("no statements")
            out[tk] = {"name": meta.get("name", tk), **analyze(tk, sector, stmts)}
        except Exception as e:
            failed.append(tk)  # keep last good result in `out`
            print(f"  ! {tk}: {e}", file=sys.stderr)
        if i % 20 == 0:
            print(f"  {i}/{len(tickers)}", flush=True)
        time.sleep(pause)

    now = datetime.now(tz=TST)
    fresh = len(tickers) - len(failed)
    if fresh == 0:
        sys.exit("no statements downloaded (rate limited?) — keeping existing output")
    result = {"generated_at": now.strftime("%Y-%m-%d %H:%M TST"), "tickers": out,
              "failed": failed}
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    _append_log(now.strftime("%Y-%m-%d"), {t: out[t] for t in tickers if t in out and t not in failed})
    print(f"大師鏡頭: {fresh} 檔更新, {len(failed)} 檔失敗(保留舊值) → {OUT_PATH}")
    return result


def _append_log(date: str, rows: dict, path: str = None):
    path = path or LOG_PATH
    fields = ["date", "ticker", "buffett", "piotroski", "lynch_cat", "lynch_growth", "peg", "pb"]
    write_header = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            w.writeheader()
        for tk, r in rows.items():
            if r.get("na"):
                continue
            ly = r.get("lynch", {})
            w.writerow({"date": date, "ticker": tk,
                        "buffett": r["buffett"].get("score"), "piotroski": r["piotroski"].get("score"),
                        "lynch_cat": ly.get("category"), "lynch_growth": ly.get("growth_pct"),
                        "peg": ly.get("peg"), "pb": ly.get("pb")})


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from widget import TECH_UNIVERSE
    pick = sys.argv[1:]
    universe = {t: TECH_UNIVERSE.get(t, {"name": t, "sector": ""}) for t in pick} if pick else TECH_UNIVERSE
    run(universe)
