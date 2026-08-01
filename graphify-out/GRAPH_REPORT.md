# Graph Report - .  (2026-08-01)

## Corpus Check
- Corpus is ~28,593 words - fits in a single context window. You may not need a graph.

## Summary
- 188 nodes · 363 edges · 15 communities (11 shown, 4 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 9 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Data Loading & Analysis
- RSI Monitor Dashboard
- Fund Flow Panel
- Infrastructure & Dependencies
- Cache & Price Loading
- App Entry & Layout
- Live Price Fetching
- Market Hours & Holdings
- Future Giants & News Banner
- News Feed (RSS)
- Intraday Order Flow
- Console Stub
- Autostart Script
- Launch Script
- Run Script

## God Nodes (most connected - your core abstractions)
1. `load_data()` - 20 edges
2. `score_stock()` - 16 edges
3. `main()` - 16 edges
4. `render_category_cards()` - 13 edges
5. `render_stock_cards()` - 13 edges
6. `_now_tw()` - 10 edges
7. `fetch_live_prices()` - 9 edges
8. `analyze_holding_sell()` - 9 edges
9. `Python Package Requirements` - 9 edges
10. `_is_market_open()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Python Package Requirements` --conceptually_related_to--> `Python 3.9 Runtime`  [INFERRED]
  requirements.txt → runtime.txt
- `load_data()` --calls--> `fetch_google_news_tw_orders()`  [EXTRACTED]
  app.py → widget.py
- `load_data()` --calls--> `fetch_technews_rss()`  [EXTRACTED]
  app.py → widget.py
- `load_data()` --calls--> `fetch_yahoo_tw_news()`  [EXTRACTED]
  app.py → widget.py
- `load_category_prices()` --calls--> `fetch_prices_batch()`  [EXTRACTED]
  app.py → widget.py

## Import Cycles
- None detected.

## Communities (15 total, 4 thin omitted)

### Community 0 - "Data Loading & Analysis"
Cohesion: 0.08
Nodes (43): load_data(), datetime, analyze_catalysts(), analyze_holdings(), calc_foreign_streak(), chg_color(), detect_order_signals(), fetch_cnyes_news() (+35 more)

### Community 1 - "RSI Monitor Dashboard"
Cohesion: 0.09
Nodes (33): Auto-refreshing RSI monitoring dashboard. Every 10s: fetches live prices →…, render_holding_card(), render_rsi_monitor(), DataFrame, Series, analyze_holding_sell(), calc_52w_position(), calc_atr() (+25 more)

### Community 2 - "Fund Flow Panel"
Cohesion: 0.16
Nodes (17): _build_flow_panel(), _build_fund_row(), _build_kbar_fi_row(), _build_why_buy(), conf_color(), _get_score_reasons(), Build fundamental tags HTML row for a stock card. Returns '' if no data., Generate a '為什麼值得關注' bulleted explanation for the beginner advice box. Draws… (+9 more)

### Community 3 - "Infrastructure & Dependencies"
Cohesion: 0.15
Nodes (17): BeautifulSoup4 HTML Parser, Daily Market Refresh Schedule, GitHub Actions CI/CD, Google Generative AI SDK, libxml2 System Library, libxslt System Library, lxml XML/HTML Parser, Pandas Data Library (+9 more)

### Community 4 - "Cache & Price Loading"
Cohesion: 0.15
Nodes (13): _fetch_alerts_cached(), load_category_prices(), load_fundamentals(), Cache RSS fetch results for 3 min so multiple simultaneous users share one poll., Fetch OHLCV price history for a category's universe. Cached per slot., yfinance 季報基本面 (營收年增 / 盈利年增 / 毛利率) — 每12小時快取一次。 Fetches all TECH_UNIVERSE +…, cache_data, fetch_market_alerts() (+5 more)

### Community 5 - "App Entry & Layout"
Cohesion: 0.17
Nodes (8): _c(), Taiwan convention: UP = red, DOWN = green., calc_fundamental_bonus(), calc_three_investors_bonus(), 三大法人買賣超共識評分 (-6 ~ +8) • 三大同買：機構合力建倉，勝率最高 → +8 • 外資 + 投信同買：主要機構共識 → +6 •…, 根據美股隔夜表現，計算個股的盤前加/減分（-10 ~ +10）。 半導體/IC設計股與費半相關最高；金融/航運相關最低。, 基本面加權評分 (-15 ~ +30 分)。來源：yfinance 季報數據。 ① 營收年增率 (revenueGrowth): >=80% +15 ...…, us_macro_stock_bonus()

### Community 6 - "Live Price Fetching"
Cohesion: 0.18
Nodes (12): Session, fetch_live_prices(), _fetch_live_twse(), _fetch_live_yf(), _get_twse_session(), _parse_ts(), Taiwan ±10% limit, rounded to correct tick size., Convert a pandas Timestamp to Taipei HH:MM string. (+4 more)

### Community 7 - "Market Hours & Holdings"
Cohesion: 0.20
Nodes (11): _analyze_holding_with_live(), _epoch_slot_info(), _is_market_open(), _now_tw(), True during Taiwan stock market hours (weekdays): 盤中 09:00–13:29 + 盤後零股…, Injects today's live price as a synthetic 'today close' row and runs…, Auto-refreshing holdings dashboard — every 10 s during market hours. Shows: •…, Returns the trading-date + intraday slot string used as the cache key. Changes… (+3 more)

### Community 8 - "Future Giants & News Banner"
Cohesion: 0.25
Nodes (8): _build_future_card(), Build a long-horizon research card for the 🚀 潛力十年 section., Polls breaking-news RSS every 3 minutes. • Shows a red/orange sticky banner for…, Auto-refreshes every 5 min to update live prices on the Future Giants view., render_future_giants(), render_news_alerts(), st_javascript(), fragment

### Community 9 - "News Feed (RSS)"
Cohesion: 0.25
Nodes (8): fetch_google_news_tw_orders(), fetch_technews_rss(), fetch_yahoo_tw_news(), Return how many minutes ago an RFC-2822 pubDate string was. -1 if unparseable., 科技新報 RSS — 台灣科技財經最快速更新, Google News RSS — 掃描台灣股票訂單/合作/認證最新消息, Yahoo奇摩股市 RSS — 台灣股市即時財經新聞 URL: https://tw.stock.yahoo.com/rss…, _rss_age_minutes()

### Community 10 - "Intraday Order Flow"
Cohesion: 0.50
Nodes (4): _fetch_flow_batch(), Batch-fetch intraday order flow for up to 5 tickers in parallel. Cached 60 s so…, fetch_intraday_flow(), Wall-Street-style intraday order flow analysis for a single Taiwan stock.…

## Knowledge Gaps
- **6 isolated node(s):** `autostart.sh script`, `launch.sh script`, `run.sh script`, `Python Runtime Specification`, `Google Generative AI SDK` (+1 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `score_stock()` connect `RSI Monitor Dashboard` to `Data Loading & Analysis`, `App Entry & Layout`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Why does `fetch_live_prices()` connect `Live Price Fetching` to `Data Loading & Analysis`, `RSI Monitor Dashboard`, `Fund Flow Panel`, `App Entry & Layout`, `Market Hours & Holdings`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `_FakeConsole` connect `Console Stub` to `Data Loading & Analysis`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **What connects `autostart.sh script`, `launch.sh script`, `run.sh script` to the rest of the system?**
  _6 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Data Loading & Analysis` be split into smaller, more focused modules?**
  _Cohesion score 0.07928118393234672 - nodes in this community are weakly interconnected._
- **Should `RSI Monitor Dashboard` be split into smaller, more focused modules?**
  _Cohesion score 0.0946969696969697 - nodes in this community are weakly interconnected._