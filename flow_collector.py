#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
即時資金流向收集器（盤中執行）
────────────────────────────
每 ~12 秒掃描全部上市＋上櫃股票（證交所 MIS 即時報價，每批 100 檔），
依內外盤判斷每筆新增成交量是流入還是流出，按「分鐘 × 個股」累加寫入 data/flow.db。
每 3 分鐘輸出 data/flow_snapshot.json 並推送到 GitHub flow-data 分支（給雲端 App 讀）。

launchd: com.stock.flow_collector — 週一至五 08:55 啟動，13:35 自動結束。
手動：python3 flow_collector.py [--once] [--no-push]
"""
import argparse, json, logging, subprocess, sys, time, traceback
from datetime import datetime
from typing import Dict, List, Optional

import requests

import flow_core as fc

MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
BATCH = 100            # MIS 單次上限約 100–150 檔
GAP = 0.3              # 批次間隔（秒），避免被證交所擋
PUBLISH_EVERY = 180    # 秒
END_HHMM = "13:35"
PUB_DIR = fc.BASE / ".flow_pub"   # flow-data 分支的 git worktree

LOG_DIR = fc.BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "flow_collector.log", encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("flow")


def _f(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _first(s: str) -> Optional[float]:
    return _f((s or "").split("_")[0])


class Collector:
    def __init__(self, universe: List[Dict]):
        self.meta = {s["code"]: s for s in universe}
        self.symbols = [f'{s["market"]}_{s["code"]}.tw' for s in universe]
        self.prev: Dict[str, Dict] = {}     # code → {v, z, ask, bid, sign}
        self.sess = requests.Session()
        self.sess.headers["User-Agent"] = "Mozilla/5.0"
        self.today = fc.now_tw().strftime("%Y%m%d")
        self.date = fc.now_tw().strftime("%Y-%m-%d")
        self.con = fc.connect()
        self._restore_state()

    def _restore_state(self):
        """重啟時：從 DB 還原各股最後成交量，避免把已計算過的量重算一次"""
        for code, price, vol in self.con.execute(
                "SELECT code, price, vol FROM stock_state WHERE date=? AND source='mis'", (self.date,)):
            self.prev[code] = {"v": vol or 0, "z": price, "ask": None, "bid": None, "sign": 0}
        if self.prev:
            log.info("restored state for %d stocks", len(self.prev))

    def fetch(self) -> List[Dict]:
        out = []
        for i in range(0, len(self.symbols), BATCH):
            chunk = "|".join(self.symbols[i:i + BATCH])
            for attempt in range(3):
                try:
                    r = self.sess.get(MIS_URL, params={"ex_ch": chunk, "json": 1, "delay": 0}, timeout=15)
                    out.extend(json.loads(r.text.strip()).get("msgArray", []))
                    break
                except Exception as e:
                    log.warning("batch %d attempt %d failed: %s", i, attempt, e)
                    time.sleep(2 + attempt * 3)
            time.sleep(GAP)
        return out

    def sweep(self) -> int:
        msgs = self.fetch()
        flows, states = [], []
        stamp = fc.now_tw().strftime("%H:%M:%S")
        for m in msgs:
            code = m.get("c")
            if not code or code not in self.meta or m.get("d") != self.today:
                continue
            v = int(m.get("v") or 0)
            z = _f(m.get("z")) or _f(m.get("pz"))
            ask, bid, ref = _first(m.get("a")), _first(m.get("b")), _f(m.get("y"))
            t = (m.get("t") or "")[:5]
            p = self.prev.get(code)
            if p is None:
                # 第一次看到：開盤前後 → 開盤集合競價量依開盤價 vs 昨收判方向；盤中才開機 → 只當基準
                if v and z and t <= "09:05":
                    sign = (z > ref) - (z < ref) if ref else 0
                    amt = v * 1000 * z
                    if sign:
                        flows.append((t, code, amt if sign > 0 else 0.0, amt if sign < 0 else 0.0))
                p = {"v": v, "z": z, "ask": ask, "bid": bid, "sign": 0}
            else:
                dv = v - p["v"]
                if dv > 0 and z:
                    if t >= "13:30" and p["z"]:                 # 收盤集合競價
                        sign = (z > p["z"]) - (z < p["z"])
                    elif p["ask"] and z >= p["ask"]:
                        sign = 1                                 # 外盤
                    elif p["bid"] and z <= p["bid"]:
                        sign = -1                                # 內盤
                    elif p["z"] and z != p["z"]:
                        sign = 1 if z > p["z"] else -1           # tick rule
                    else:
                        sign = p["sign"]
                    amt = dv * 1000 * z
                    if sign:
                        flows.append((t, code, amt if sign > 0 else 0.0, amt if sign < 0 else 0.0))
                    p["sign"] = sign or p["sign"]
                p.update(v=max(v, p["v"]), z=z or p["z"], ask=ask or p["ask"], bid=bid or p["bid"])
            self.prev[code] = p
            meta = self.meta[code]
            states.append((code, meta["name"], meta["ind"], meta["market"],
                           p["z"], ref, p["v"], stamp, "mis"))
        if states:
            fc.add_flows(self.con, self.date, flows)
            fc.upsert_states(self.con, self.date, states)
            self.con.commit()
        return len(states)


# ── 發布到 GitHub flow-data 分支 ──────────────────────────────────────────────
def _git(*args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd or fc.BASE), capture_output=True, text=True, timeout=60)


def ensure_pub_worktree() -> bool:
    if (PUB_DIR / ".git").exists():
        return True
    _git("worktree", "prune")
    r = _git("fetch", "origin", "flow-data")
    if r.returncode == 0:
        r = _git("worktree", "add", "-B", "flow-data", str(PUB_DIR), "origin/flow-data")
    else:
        r = _git("worktree", "add", "--orphan", "-b", "flow-data", str(PUB_DIR))
    if r.returncode != 0:
        log.error("worktree setup failed: %s", r.stderr.strip())
        return False
    return True


def publish(snap: Dict) -> None:
    try:
        if not ensure_pub_worktree():
            return
        (PUB_DIR / "flow_snapshot.json").write_text(
            json.dumps(snap, ensure_ascii=False, separators=(",", ":")), "utf-8")
        _git("add", "flow_snapshot.json", cwd=PUB_DIR)
        has_head = _git("rev-parse", "--verify", "HEAD", cwd=PUB_DIR).returncode == 0
        # 只保留一個 commit（amend + force push），分支不會越長越大
        msg = f"flow snapshot {snap['date']} {snap.get('updated')}"
        c = _git("commit", "-q", "--amend", "-m", msg, cwd=PUB_DIR) if has_head else \
            _git("commit", "-q", "-m", msg, cwd=PUB_DIR)
        if c.returncode != 0 and "nothing" not in c.stdout + c.stderr:
            log.error("publish commit failed: %s", c.stderr.strip())
            return
        p = _git("push", "-q", "-f", "origin", "flow-data", cwd=PUB_DIR)
        if p.returncode != 0:
            log.error("publish push failed: %s", p.stderr.strip())
        else:
            log.info("published snapshot (%s)", snap.get("updated"))
    except Exception:
        log.error("publish error\n%s", traceback.format_exc())


def export(con, push: bool) -> None:
    snap = fc.build_snapshot(con)
    if snap:
        fc.write_snapshot(snap)
        if push:
            publish(snap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="只掃一次（測試用）")
    ap.add_argument("--no-push", action="store_true", help="不推送到 GitHub")
    args = ap.parse_args()

    now = fc.now_tw()
    if now.weekday() >= 5 and not args.once:
        log.info("weekend — exit")
        return
    universe = fc.load_universe()
    col = Collector(universe)
    log.info("collector start: %d stocks", len(universe))

    # 等到 08:59 再開始（開盤前的報價沒有成交）
    while not args.once and fc.now_tw().strftime("%H:%M") < "08:59":
        time.sleep(15)

    last_pub, empty_sweeps = 0.0, 0
    while True:
        t0 = time.time()
        try:
            n = col.sweep()
        except Exception:
            log.error("sweep error\n%s", traceback.format_exc())
            n = 0
        empty_sweeps = empty_sweeps + 1 if n == 0 else 0
        if args.once:
            log.info("sweep: %d stocks in %.1fs", n, time.time() - t0)
            export(col.con, push=not args.no_push)
            break
        # 休市日：開盤後 MIS 資料日期不是今天 → 連續空掃 → 結束
        if empty_sweeps >= 20 and fc.now_tw().strftime("%H:%M") > "09:10":
            log.warning("no data for today after 09:10 — market holiday? exit")
            break
        if time.time() - last_pub > PUBLISH_EVERY and n:
            export(col.con, push=not args.no_push)
            last_pub = time.time()
        if fc.now_tw().strftime("%H:%M") >= END_HHMM:
            export(col.con, push=not args.no_push)
            log.info("market closed — final snapshot written, exit")
            break
        time.sleep(max(0.0, 5 - (time.time() - t0)))


if __name__ == "__main__":
    main()
