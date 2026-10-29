#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日精選紀錄 — 把 morning_picks.json 的每一檔存進 data/pick_log.csv，
供 forward_test.py 追蹤事後報酬。同一 (date, ticker) 只記一次。

  python pick_log.py                 # 記錄 data/morning_picks.json
  python pick_log.py --backfill-git  # 從 git 歷史補回過去每天的精選
"""
import argparse, csv, json, os, subprocess

LOG_PATH = os.path.join("data", "pick_log.csv")
FIELDS = [
    "date", "ticker", "name", "sector", "rank", "score", "last_price",
    "stop_loss", "target_price", "target_pct", "rsi", "stage", "rs_composite",
    "mom5d", "mom20d", "rev_yoy", "mkt_label", "mkt_penalty",
]


def _rows(result: dict) -> list:
    mkt = result.get("market_direction", {})
    rows = []
    for rank, pk in enumerate(result.get("top_picks", []), 1):
        row = {k: pk.get(k, "") for k in FIELDS}
        row.update(date=result["date"], rank=rank,
                   mkt_label=mkt.get("label", ""), mkt_penalty=mkt.get("penalty", ""))
        rows.append(row)
    return rows


def append_picks(result: dict, path: str = LOG_PATH) -> int:
    """Append result's picks not already logged. Returns number of rows added."""
    existing = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            existing = {(r["date"], r["ticker"]) for r in csv.DictReader(f)}
    new = [r for r in _rows(result) if (r["date"], r["ticker"]) not in existing]
    if not new:
        return 0
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    write_header = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(new)
    return len(new)


def backfill_git(path: str = LOG_PATH) -> int:
    """Replay every committed version of data/morning_picks.json, oldest first."""
    shas = subprocess.check_output(
        ["git", "log", "--reverse", "--format=%H", "--", "data/morning_picks.json"],
        text=True).split()
    total = 0
    for sha in shas:
        try:
            blob = subprocess.check_output(
                ["git", "show", f"{sha}:data/morning_picks.json"], text=True)
            total += append_picks(json.loads(blob), path)
        except Exception as e:
            print(f"skip {sha[:7]}: {e}")
    return total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-git", action="store_true")
    ap.add_argument("--input", default="data/morning_picks.json")
    args = ap.parse_args()
    if args.backfill_git:
        print(f"backfilled {backfill_git()} rows")
    else:
        with open(args.input, encoding="utf-8") as f:
            print(f"logged {append_picks(json.load(f))} rows")
