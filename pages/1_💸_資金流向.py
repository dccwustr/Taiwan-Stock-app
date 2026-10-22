# -*- coding: utf-8 -*-
"""
💸 台股即時資金流向 — 全上市櫃、各產業流入 / 流出
資料：本機 flow_collector.py（盤中每 ~20 秒，內外盤法）→ data/flow.db
      雲端則讀 GitHub flow-data 分支的快照（約 30–60 秒延遲）
"""
import html, json, sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import flow_core as fc  # noqa: E402
import flow_race  # noqa: E402

st.set_page_config(page_title="即時資金流向", page_icon="💸", layout="wide")

# 台股慣例：紅 = 流入 / 漲，綠 = 流出 / 跌（色盲辨識：方向 + 正負號雙重編碼）
RED, GREEN, MID = "#e8504a", "#4cd07d", "#2a2e39"
BG, PANEL, INK, MUTED, GRID = "#0b0e14", "#121722", "#e6e9ef", "#8a93a6", "#1e2533"

st.markdown(f"""
<style>
.stApp {{ background:{BG}; }}
.flow-tile {{ background:{PANEL}; border:1px solid {GRID}; border-radius:10px; padding:12px 16px; }}
.flow-tile .lbl {{ color:{MUTED}; font-size:12px; }}
.flow-tile .val {{ color:{INK}; font-size:24px; font-weight:700; font-variant-numeric:tabular-nums; }}
.flow-tile .sub {{ font-size:12px; font-variant-numeric:tabular-nums; }}
</style>""", unsafe_allow_html=True)


# ── 資料 ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=5, show_spinner=False)
def load_local():
    if not fc.DB_PATH.exists():
        return None
    try:
        con = fc.connect()
        snap = fc.build_snapshot(con)
        con.close()
        return snap
    except Exception:
        return None


@st.cache_data(ttl=10, show_spinner=False)
def load_remote():
    return fc.fetch_remote_snapshot()


def load():
    loc, rem = load_local(), load_remote()
    if loc and rem:   # 取比較新的
        return loc if (loc["date"], loc.get("updated") or "") >= (rem["date"], rem.get("updated") or "") else rem
    return loc or rem


def yi(million: float) -> str:
    """百萬 → 億，帶正負號"""
    v = million / 100
    return f"{v:+,.2f} 億" if abs(v) < 100 else f"{v:+,.0f} 億"


def market_open() -> bool:
    n = fc.now_tw()
    return n.weekday() < 5 and "08:59" <= n.strftime("%H:%M") <= "13:36"


# ── 圖表 ────────────────────────────────────────────────────────────────────
def base_layout(fig, height):
    fig.update_layout(
        height=height, paper_bgcolor=BG, plot_bgcolor=BG, font=dict(color=INK, size=12),
        margin=dict(l=8, r=8, t=8, b=8), showlegend=False,
        hoverlabel=dict(bgcolor=PANEL, bordercolor=GRID, font=dict(color=INK)),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=MUTED, zerolinewidth=1, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=BG, tickfont=dict(color=INK))
    return fig


def sector_bar(df: pd.DataFrame, height: int):
    """各產業淨流入（水平、正負分流），右紅 = 流入、左綠 = 流出"""
    d = df.sort_values("net")
    fig = go.Figure(go.Bar(
        x=d["net"] / 100, y=d["ind"], orientation="h",
        marker=dict(color=[RED if v >= 0 else GREEN for v in d["net"]], line=dict(width=0),
                    cornerradius=4),
        text=[yi(v) for v in d["net"]], textposition="outside",
        textfont=dict(color=INK, size=11), cliponaxis=False,
        customdata=d[["in", "out"]].to_numpy() / 100,
        hovertemplate="<b>%{y}</b><br>淨額 %{x:+,.2f} 億<br>流入 %{customdata[0]:,.2f} 億"
                      "<br>流出 %{customdata[1]:,.2f} 億<extra></extra>",
    ))
    lo, hi = min(d["net"].min(), 0) / 100, max(d["net"].max(), 0) / 100
    pad = (hi - lo) * 0.28 or 1          # 留空間給數值標籤
    fig.update_xaxes(title=None, ticksuffix=" 億", range=[lo - pad, hi + pad])
    fig.update_layout(bargap=0.25)
    return base_layout(fig, height)


def rotation_heatmap(snap, sel_idx, sectors, bucket, height):
    """產業 × 時段 淨流入熱圖：一眼看出資金何時從哪裡移到哪裡"""
    mins = [snap["minutes"][i] for i in sel_idx]
    labels = []
    for m in mins:
        h, mm = int(m[:2]), int(m[3:])
        mm = (mm // bucket) * bucket
        labels.append(f"{h:02d}:{mm:02d}")
    cols = sorted(set(labels))
    order = sorted(sectors, key=lambda s: sum(snap["sectors"][s]["in"][i] - snap["sectors"][s]["out"][i]
                                              for i in sel_idx))
    z = []
    for s in order:
        v = snap["sectors"][s]
        row = dict.fromkeys(cols, 0.0)
        for i, lb in zip(sel_idx, labels):
            row[lb] += (v["in"][i] - v["out"][i]) / 100
        z.append([row[c] for c in cols])
    lim = max((abs(x) for r in z for x in r), default=1) or 1
    lim = sorted(abs(x) for r in z for x in r)[int(len(cols) * len(order) * 0.97) - 1] or lim  # 去極端值
    fig = go.Figure(go.Heatmap(
        z=z, x=cols, y=order, zmin=-lim, zmax=lim, zmid=0,
        colorscale=[[0, GREEN], [0.5, MID], [1, RED]], xgap=2, ygap=2,
        colorbar=dict(title=dict(text="億", font=dict(color=MUTED)), tickfont=dict(color=MUTED),
                      thickness=10, outlinewidth=0),
        hovertemplate="<b>%{y}</b> %{x}<br>淨額 %{z:+,.2f} 億<extra></extra>",
    ))
    fig = base_layout(fig, height)
    fig.update_xaxes(side="top", gridcolor=BG)
    return fig


def stock_table(rows: pd.DataFrame) -> pd.DataFrame:
    t = rows.copy()
    t["淨額(億)"] = (t["in"] - t["out"]) / 100
    t["流入(億)"] = t["in"] / 100
    t["流出(億)"] = t["out"] / 100
    t["NT$10,000 可買"] = t["price"].apply(lambda p: "—" if not p else (f"{int(10000 // p):,} 股" if p <= 10000 else f"不足 1 股（需 NT${p:,.0f}）"))
    t["股票"] = t["code"] + " " + t["name"]
    return t[["股票", "ind", "price", "chg", "淨額(億)", "流入(億)", "流出(億)", "NT$10,000 可買"]].rename(
        columns={"ind": "產業", "price": "股價", "chg": "漲跌%"})


def stocks_in_window(snap, stocks: pd.DataFrame, win) -> pd.DataFrame:
    """個股在所選時間區間的 in/out/net（百萬）。全日用精確值；其餘用 5 分鐘分桶加總。
    舊快照沒有分桶資料時退回全日累計。"""
    st_ = stocks.copy()
    minutes = snap["minutes"]
    sf, bks = snap.get("stock_flow"), snap.get("buckets")
    if not (win[0] == minutes[0] and win[1] == minutes[-1]) and sf and bks:
        lo, hi = fc.bucket_of(win[0]), win[1]
        idx = [i for i, b in enumerate(bks) if lo <= b <= hi]
        rows = []
        for code, v in sf.items():
            rows.append((code, sum(v["in"][i] for i in idx), sum(v["out"][i] for i in idx)))
        w = pd.DataFrame(rows, columns=["code", "in", "out"])
        st_ = st_.drop(columns=["in", "out"]).merge(w, on="code", how="inner")
    st_["net"] = st_["in"] - st_["out"]
    return st_


TABLE_CFG = {
    "股價": st.column_config.NumberColumn(format="%.2f"),
    "漲跌%": st.column_config.NumberColumn(format="%+.2f%%"),
    "淨額(億)": st.column_config.NumberColumn(format="%+.2f"),
    "流入(億)": st.column_config.NumberColumn(format="%.2f"),
    "流出(億)": st.column_config.NumberColumn(format="%.2f"),
}


def tile(col, label, val, sub="", color=INK):
    col.markdown(f'<div class="flow-tile"><div class="lbl">{label}</div>'
                 f'<div class="val" style="color:{color}">{val}</div>'
                 f'<div class="sub" style="color:{MUTED}">{sub}</div></div>', unsafe_allow_html=True)


# ── 頁面 ────────────────────────────────────────────────────────────────────
st.markdown("## 💸 台股即時資金流向")

snap = load()
if not snap or not snap.get("minutes"):
    st.info("今天還沒有盤中資料。開盤（09:00）後約 1 分鐘開始顯示，盤中約每 30 秒更新。")
    st.stop()

if snap.get("source") == "demo":
    st.warning("⚠️ 示範資料：股價、成交量、產業為今日真實收盤資料，但盤中流入/流出分配是模擬的，只用來預覽版面。")

live = market_open() and snap["date"] == fc.now_tw().strftime("%Y-%m-%d")

# 動畫放在 fragment 外面才不會被重整打斷；新資料由下面 fragment 的隱藏元素提供
flow_race.render(snap, live)


@st.fragment(run_every=15 if live else None)
def details():
    snap = load() or {}
    if not snap.get("minutes"):
        return
    # 每 15 秒把最新快照放進隱藏元素，動畫元件每 2 秒讀一次（元件本身不重載，動畫不中斷）
    lite = {k: snap.get(k) for k in ("date", "updated", "source", "minutes", "sectors")}
    st.html(f'<div id="flow-live-data" style="display:none">'
            f'{html.escape(json.dumps(lite, ensure_ascii=False))}</div>')
    _details(snap)


def _details(snap):
    minutes = snap["minutes"]
    c1, c2, c3 = st.columns([3, 2, 2])
    # 盤中每分鐘 options 都會變長，Streamlit 會把元件當成新的而重設 → 自己記住使用者的選擇
    # （右端選在最新一分鐘 = 跟著最新走）
    a, b, follow = st.session_state.get("flow_win", (minutes[0], minutes[-1], True))
    a = a if a in minutes else minutes[0]
    b = minutes[-1] if follow or b not in minutes else b
    win = c1.select_slider("時間區間", options=minutes, value=(a, b))
    st.session_state["flow_win"] = (win[0], win[1], win[1] == minutes[-1])
    bucket = c2.selectbox("熱圖時段", [5, 10, 15, 30], index=2, format_func=lambda m: f"每 {m} 分鐘")
    scope = c3.selectbox("顯示產業", ["全部產業", "前後各 10 名"], index=0)

    sel_idx = [i for i, m in enumerate(minutes) if win[0] <= m <= win[1]]
    sec_rows = []
    for s, v in snap["sectors"].items():
        i_ = sum(v["in"][i] for i in sel_idx)
        o_ = sum(v["out"][i] for i in sel_idx)
        if i_ or o_:
            sec_rows.append({"ind": s, "in": i_, "out": o_, "net": i_ - o_})
    sec = pd.DataFrame(sec_rows)
    if scope != "全部產業" and len(sec) > 20:
        sec = pd.concat([sec.nlargest(10, "net"), sec.nsmallest(10, "net")]).drop_duplicates("ind")
    sectors = list(sec["ind"])

    src = "盤中即時（內外盤）" if snap.get("source") == "mis" else "1 分 K 估算"
    live = market_open() and snap["date"] == fc.now_tw().strftime("%Y-%m-%d")
    tot_in, tot_out = sec["in"].sum(), sec["out"].sum()
    net = tot_in - tot_out
    k1, k2, k3, k4 = st.columns(4)
    tile(k1, f"{snap['date']}　{win[0]} → {win[1]}", "🔴 盤中" if live else "收盤",
         f"更新 {snap.get('updated') or '—'} · {src}")
    tile(k2, "主動買進（流入）", f"{tot_in / 100:,.0f} 億", "成交在委賣價（外盤）", RED)
    tile(k3, "主動賣出（流出）", f"{tot_out / 100:,.0f} 億", "成交在委買價（內盤）", GREEN)
    tile(k4, "全市場淨額", yi(net), f"流入佔 {tot_in / max(tot_in + tot_out, 1):.1%}", RED if net >= 0 else GREEN)

    st.write("")
    h = max(420, 22 * len(sectors) + 40)
    st.markdown("#### 產業淨流入排行")
    st.plotly_chart(sector_bar(sec, h), config={"displayModeBar": False})

    st.markdown("#### 產業 × 時段 熱圖")
    st.caption("紅 = 該時段資金淨流入，綠 = 淨流出。由上往下依區間淨額排序。")
    st.plotly_chart(rotation_heatmap(snap, sel_idx, sectors, bucket, max(420, 20 * len(sectors) + 60)),
                    config={"displayModeBar": False})

    # ── 個股 ────────────────────────────────────────────────────────────────────
    st.markdown("#### 個股資金流向")
    stocks = pd.DataFrame(snap["stocks"])
    sel = stocks_in_window(snap, stocks, win)
    full_day = win[0] == minutes[0] and win[1] == minutes[-1]
    d1, d2, d3 = st.columns([2, 2, 1])
    direction = d1.selectbox("方向", ["🔴 資金流入最多", "🟢 資金流出最多"], key="flow_dir")
    ind_opts = ["全部產業"] + sorted(sel["ind"].dropna().unique())
    ind_pick = d2.selectbox("產業", ind_opts, key="flow_ind")
    topn = d3.selectbox("前 N 名", [10, 15, 30], index=1, key="flow_topn")
    if ind_pick != "全部產業":
        sel = sel[sel["ind"] == ind_pick]
    sel = sel[(sel["in"] > 0) | (sel["out"] > 0)]
    sel = sel.nlargest(topn, "net") if direction.startswith("🔴") else sel.nsmallest(topn, "net")
    st.caption(f"區間 {win[0]} → {win[1]}" + ("（全日，精確值）" if full_day else
               f"（以 {fc.BUCKET_MIN} 分鐘為單位估算，僅含當日成交最活躍的股票）"))
    if sel.empty:
        st.info("這個區間／產業沒有資料。")
    else:
        st.dataframe(stock_table(sel), hide_index=True, column_config=TABLE_CFG)

    st.caption("說明：成交價在前一刻委賣價以上 = 主動買進（流入），在委買價以下 = 主動賣出（流出）。"
               "每 ~20 秒掃描一次，同一段時間內多筆成交會合併判斷，數字為估算、看方向比看絕對金額準。"
               "這是盤中籌碼溫度計，不是買賣訊號——零股小資請搭配精選頁的綜合評分。")


details()
