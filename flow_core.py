#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
即時資金流向 — 共用核心
─────────────────────────
資料庫結構、產業代碼對照、快照彙整（collector / backfill / Streamlit 頁面共用）

流向定義（內外盤法）：
  成交價 ≥ 前一刻委賣價（外盤，買方追價）→ 資金流入  +成交金額
  成交價 ≤ 前一刻委買價（內盤，賣方殺價）→ 資金流出  −成交金額
  介於中間 → 與前一筆成交價比較（tick rule）
"""
import json, os, re, sqlite3, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

TW = timezone(timedelta(hours=8))
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DB_PATH = Path(os.environ.get("FLOW_DB") or DATA / "flow.db")   # FLOW_DB：測試用
UNIVERSE_PATH = DATA / "flow_universe.json"
SNAPSHOT_PATH = DATA / "flow_snapshot.json"

# GitHub 上的快照（給 Streamlit Cloud 讀；由本機 collector 推送到 flow-data 分支）
REMOTE_SNAPSHOT_URL = (
    "https://raw.githubusercontent.com/dccwustr/Taiwan-Stock-app/flow-data/flow_snapshot.json"
)
REPO_GIT = "https://github.com/dccwustr/Taiwan-Stock-app.git"


def fetch_remote_snapshot() -> Optional[Dict]:
    """最新快照。raw 分支網址有 5 分鐘 CDN 快取（加 ?t= 也沒用），
    所以先用 git 的 info/refs 查 flow-data 最新 commit，再用 commit 網址抓（每次都是新檔）"""
    url = REMOTE_SNAPSHOT_URL
    try:
        r = requests.get(REPO_GIT + "/info/refs", params={"service": "git-upload-pack"}, timeout=10)
        m = re.search(r"([0-9a-f]{40}) refs/heads/flow-data\b", r.text)
        if m:
            url = f"https://raw.githubusercontent.com/dccwustr/Taiwan-Stock-app/{m.group(1)}/flow_snapshot.json"
    except Exception:
        pass
    try:
        r = requests.get(url, timeout=10)
        return r.json() if r.ok else None
    except Exception:
        return None

# 證交所 / 櫃買 官方產業別代碼
INDUSTRY = {
    "01": "水泥", "02": "食品", "03": "塑膠", "04": "紡織纖維", "05": "電機機械",
    "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙", "10": "鋼鐵", "11": "橡膠",
    "12": "汽車", "14": "建材營造", "15": "航運", "16": "觀光餐旅", "17": "金融保險",
    "18": "貿易百貨", "19": "綜合", "20": "其他", "21": "化學", "22": "生技醫療",
    "23": "油電燃氣", "24": "半導體", "25": "電腦週邊", "26": "光電", "27": "通信網路",
    "28": "電子零組件", "29": "電子通路", "30": "資訊服務", "31": "其他電子",
    "32": "文化創意", "33": "農業科技", "34": "電子商務", "35": "綠能環保",
    "36": "數位雲端", "37": "運動休閒", "38": "居家生活", "80": "管理股票", "91": "存託憑證",
}


def now_tw() -> datetime:
    return datetime.now(TW)


def industry_name(code: str) -> str:
    return INDUSTRY.get(str(code).zfill(2), "其他")


# ── 股票清單（上市 + 上櫃，含產業別）────────────────────────────────────────
def load_universe(refresh: bool = False) -> List[Dict]:
    """[{code, name, market:'tse'|'otc', ind}] — 每日快取一次"""
    today = now_tw().strftime("%Y-%m-%d")
    if UNIVERSE_PATH.exists() and not refresh:
        try:
            cached = json.loads(UNIVERSE_PATH.read_text("utf-8"))
            if cached.get("date") == today and cached.get("stocks"):
                return cached["stocks"]
        except Exception:
            pass
    stocks: List[Dict] = []
    try:
        tse = requests.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", timeout=30).json()
        for x in tse:
            stocks.append({"code": x["公司代號"].strip(), "name": x["公司簡稱"].strip(),
                           "market": "tse", "ind": industry_name(x.get("產業別", ""))})
        otc = requests.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", timeout=30).json()
        for x in otc:
            stocks.append({"code": x["SecuritiesCompanyCode"].strip(),
                           "name": x["CompanyAbbreviation"].strip(),
                           "market": "otc", "ind": industry_name(x.get("SecuritiesIndustryCode", ""))})
    except Exception:
        # 網路失敗 → 用舊快取
        if UNIVERSE_PATH.exists():
            return json.loads(UNIVERSE_PATH.read_text("utf-8")).get("stocks", [])
        raise
    DATA.mkdir(exist_ok=True)
    UNIVERSE_PATH.write_text(json.dumps({"date": today, "stocks": stocks}, ensure_ascii=False), "utf-8")
    return stocks


# ── SQLite ───────────────────────────────────────────────────────────────────
def connect() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS minute_flow (
            date TEXT, minute TEXT, code TEXT,
            inflow REAL DEFAULT 0, outflow REAL DEFAULT 0,
            PRIMARY KEY (date, minute, code)
        );
        CREATE TABLE IF NOT EXISTS stock_state (
            date TEXT, code TEXT, name TEXT, ind TEXT, market TEXT,
            price REAL, ref REAL, vol INTEGER, updated TEXT, source TEXT,
            PRIMARY KEY (date, code)
        );
        CREATE INDEX IF NOT EXISTS ix_flow_code ON minute_flow (date, code);
    """)
    return con


def add_flows(con: sqlite3.Connection, date: str, rows: List[tuple]) -> None:
    """rows: (minute, code, inflow, outflow) — 累加到同分鐘"""
    con.executemany("""
        INSERT INTO minute_flow (date, minute, code, inflow, outflow) VALUES (?,?,?,?,?)
        ON CONFLICT(date, minute, code) DO UPDATE SET
            inflow = inflow + excluded.inflow, outflow = outflow + excluded.outflow
    """, [(date, m, c, i, o) for m, c, i, o in rows])


def upsert_states(con: sqlite3.Connection, date: str, rows: List[tuple]) -> None:
    """rows: (code, name, ind, market, price, ref, vol, updated, source)"""
    con.executemany("""
        INSERT OR REPLACE INTO stock_state
            (date, code, name, ind, market, price, ref, vol, updated, source)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, [(date,) + r for r in rows])


def latest_date(con: sqlite3.Connection) -> Optional[str]:
    r = con.execute("SELECT MAX(date) FROM minute_flow").fetchone()
    return r[0] if r else None


# ── 快照：頁面需要的所有彙整資料（JSON 可序列化）─────────────────────────────
def build_snapshot(con: sqlite3.Connection, date: Optional[str] = None) -> Optional[Dict]:
    date = date or latest_date(con)
    if not date:
        return None
    flows = con.execute("""
        SELECT f.minute, s.ind, SUM(f.inflow), SUM(f.outflow)
        FROM minute_flow f JOIN stock_state s ON s.date = f.date AND s.code = f.code
        WHERE f.date = ? GROUP BY f.minute, s.ind ORDER BY f.minute
    """, (date,)).fetchall()
    if not flows:
        return None
    minutes = sorted({m for m, *_ in flows})
    idx = {m: k for k, m in enumerate(minutes)}
    sectors: Dict[str, Dict[str, List[float]]] = {}
    for m, ind, i, o in flows:
        s = sectors.setdefault(ind, {"in": [0.0] * len(minutes), "out": [0.0] * len(minutes)})
        s["in"][idx[m]] = round(i / 1e6, 2)    # 單位：百萬元
        s["out"][idx[m]] = round(o / 1e6, 2)

    stocks = []
    for code, name, ind, market, price, ref, vol, i, o in con.execute("""
        SELECT s.code, s.name, s.ind, s.market, s.price, s.ref, s.vol,
               COALESCE(SUM(f.inflow),0), COALESCE(SUM(f.outflow),0)
        FROM stock_state s LEFT JOIN minute_flow f ON f.date = s.date AND f.code = s.code
        WHERE s.date = ? GROUP BY s.code
    """, (date,)):
        if not (i or o):
            continue
        stocks.append({
            "code": code, "name": name, "ind": ind, "mkt": market,
            "price": price, "chg": round((price / ref - 1) * 100, 2) if price and ref else None,
            "vol": vol, "in": round(i / 1e6, 2), "out": round(o / 1e6, 2),
        })
    upd = con.execute("SELECT MAX(updated), MIN(source) FROM stock_state WHERE date = ?", (date,)).fetchone()
    buckets, stock_flow = build_stock_buckets(con, date, stocks)
    return {
        "date": date, "updated": upd[0], "source": upd[1],
        "minutes": minutes, "sectors": sectors, "stocks": stocks,
        "buckets": buckets, "stock_flow": stock_flow,
    }


BUCKET_MIN = 5          # 個股時段資料的分桶（分鐘）
BUCKET_TOP_GROSS = 200  # 成交額最大的前 N 檔
BUCKET_TOP_NET = 60     # 全日淨流入 / 淨流出各前 N 檔


def bucket_of(minute: str) -> str:
    """'09:17' → '09:15'"""
    h, m = int(minute[:2]), int(minute[3:5])
    return f"{h:02d}:{(m // BUCKET_MIN) * BUCKET_MIN:02d}"


def build_stock_buckets(con: sqlite3.Connection, date: str, stocks: List[Dict]):
    """個股 × 5 分鐘 的流入/流出（百萬元），讓個股排行能跟著時間區間走。
    只留活躍的少數幾檔，快照才不會爆量：成交額前 200 ∪ 淨流入前 60 ∪ 淨流出前 60。"""
    if not stocks:
        return [], {}
    by_gross = sorted(stocks, key=lambda x: x["in"] + x["out"], reverse=True)[:BUCKET_TOP_GROSS]
    by_net = sorted(stocks, key=lambda x: x["in"] - x["out"])
    keep = {x["code"] for x in by_gross + by_net[:BUCKET_TOP_NET] + by_net[-BUCKET_TOP_NET:]}
    rows = con.execute("SELECT minute, code, inflow, outflow FROM minute_flow WHERE date = ?", (date,)).fetchall()
    acc: Dict[str, Dict[str, List[float]]] = {}
    bset = set()
    tmp: Dict[tuple, List[float]] = {}
    for minute, code, i, o in rows:
        if code not in keep:
            continue
        b = bucket_of(minute)
        bset.add(b)
        v = tmp.setdefault((code, b), [0.0, 0.0])
        v[0] += i or 0.0
        v[1] += o or 0.0
    buckets = sorted(bset)
    bidx = {b: k for k, b in enumerate(buckets)}
    for (code, b), (i, o) in tmp.items():
        s = acc.setdefault(code, {"in": [0.0] * len(buckets), "out": [0.0] * len(buckets)})
        s["in"][bidx[b]] = round(i / 1e6, 2)
        s["out"][bidx[b]] = round(o / 1e6, 2)
    return buckets, acc


def write_snapshot(snap: Dict) -> Path:
    tmp = SNAPSHOT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), "utf-8")
    tmp.replace(SNAPSHOT_PATH)
    return SNAPSHOT_PATH
