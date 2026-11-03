#!/bin/bash
# 本機產生早安精選並發布（launchd: com.stock.morning_picks，平日 08:45）。
# GitHub 排程常晚 4–6 小時，它留著當備援：這裡沒發布，它就會補上。
#   ./run_morning_picks.sh --dry-run   # 跑完整流程但不 push，也不做時間與休市檢查
set -u
REPO="$HOME/taiwan_stock_widget"
HOME_DIR="$HOME/.stock_picks"
WT="$HOME_DIR/worktree"
PY="$HOME_DIR/venv/bin/python"
LOG="$REPO/logs/morning_picks.log"
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
mkdir -p "$REPO/logs"
exec >>"$LOG" 2>&1
export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin

log() { echo "$(TZ=Asia/Taipei date '+%F %T') $*"; }
notify() { /usr/bin/osascript -e "display notification \"$1\" with title \"台股早安精選\"" >/dev/null 2>&1; }
fail() { log "FAIL: $1"; notify "$1；GitHub 備援稍後會補上"; exit 1; }

log "=== start (dry=$DRY)"
if [ $DRY = 0 ]; then
  HHMM=$(TZ=Asia/Taipei date +%H%M)
  # Mac 睡過頭才醒：收盤後不再產生，交給 GitHub 備援
  if [ "$HHMM" -ge 1330 ]; then log "after close, skip"; exit 0; fi
  if ! "$PY" -I - <<'EOF'
import json, sys, urllib.request
from datetime import datetime, timezone, timedelta
now = datetime.now(timezone(timedelta(hours=8)))
if now.weekday() >= 5:
    sys.exit(1)
roc = f"{now.year - 1911}{now:%m%d}"
try:
    req = urllib.request.Request("https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule",
                                 headers={"User-Agent": "Mozilla/5.0"})
    rows = json.load(urllib.request.urlopen(req, timeout=20))
except Exception as e:   # 抓不到一律當開市（和 flow_guard 同規則）
    print("holiday fetch failed:", e)
    sys.exit(0)
for r in rows:           # 名稱結尾「交易日」= 開始/最後交易日，仍有交易
    if r.get("Date") == roc and not r.get("Name", "").strip().endswith("交易日"):
        sys.exit(1)
EOF
  then log "market holiday, skip"; exit 0; fi
fi

git -C "$REPO" fetch -q origin || fail "git fetch 失敗"
[ -e "$WT/.git" ] || { git -C "$REPO" worktree prune; git -C "$REPO" worktree add -q --detach "$WT" origin/main || fail "worktree 建立失敗"; }
cd "$WT" || fail "找不到 worktree"
git reset -q --hard origin/main || fail "git reset 失敗"

"$PY" morning_picks.py --output data/morning_picks.json || fail "morning_picks.py 執行失敗"

PROBLEMS=$("$PY" -c "import json;print(','.join(json.load(open('data/morning_picks.json')).get('data_health',{}).get('problems',[])))") \
  || fail "輸出檔無法讀取"
if [ -n "$PROBLEMS" ]; then
  git reset -q --hard origin/main
  fail "資料來源異常（$PROBLEMS），不發布"
fi
if [ $DRY = 1 ]; then
  log "dry-run ok: $("$PY" -c "import json;d=json.load(open('data/morning_picks.json'));print(d['generated_at'],[p['ticker'] for p in d['top_picks'][:3]])")"
  git reset -q --hard origin/main
  exit 0
fi

git add data/morning_picks.json data/pick_log.csv
[ -f data/dip_log.csv ] && git add data/dip_log.csv
if ! git diff --staged --quiet; then
  git -c core.hooksPath=/dev/null -c user.name="台股早安精選 Bot" -c user.email="bot@users.noreply.github.com" \
      commit -q -m "chore: morning picks $(TZ=Asia/Taipei date +%F)" || fail "git commit 失敗"
fi
for i in 1 2 3; do
  git -c core.hooksPath=/dev/null pull -q --rebase origin main && git push -q origin HEAD:main && { log "published"; exit 0; }
  sleep 10
done
fail "git push 失敗"
