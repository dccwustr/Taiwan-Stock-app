#!/bin/bash
# 台灣科技股分析 — 每日自動啟動腳本（供 cron 使用）
# 每天 8:00 AM CST (Taiwan time) 由 cron 執行
# 功能：啟動 Streamlit app（若未運行），並預熱今日資料

APP_DIR="$(dirname "$0")"
LOG="$APP_DIR/logs/auto.log"
PYTHON="/Library/Developer/CommandLineTools/usr/bin/python3"
PORT=8501

echo "======================================" >> "$LOG"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 自動啟動觸發" >> "$LOG"

# ── 1. 直接檢查 port 是否已有 app 在跑 ───────────────────────────────────────
IS_RUNNING=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT 2>/dev/null)

if [ "$IS_RUNNING" = "200" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] App 已在運行，跳過啟動" >> "$LOG"
else
    # ── 2. 啟動 App ───────────────────────────────────────────────────────────
    cd "$APP_DIR"
    # STREAMLIT_EMAIL="" 跳過互動式 email 提示（解決昨日 cron 卡住問題）
    STREAMLIT_EMAIL="" $PYTHON -m streamlit run app.py \
        --server.port $PORT \
        --server.headless true \
        --theme.base dark \
        --theme.primaryColor "#1565c0" \
        --theme.backgroundColor "#0e1117" \
        --theme.secondaryBackgroundColor "#1c2030" \
        --theme.textColor "#e0e0e0" \
        >> "$LOG" 2>&1 &

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] App 已啟動 (PID $!)" >> "$LOG"

    # ── 3. 等待就緒（最多60秒）────────────────────────────────────────────────
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 等待 Streamlit 就緒..." >> "$LOG"
    for i in $(seq 1 12); do
        sleep 5
        HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT 2>/dev/null)
        if [ "$HTTP" = "200" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ App 就緒（等了 $((i*5)) 秒）" >> "$LOG"
            break
        fi
    done
fi

# ── 4. 預熱快取：打一次首頁讓今日資料載入 ─────────────────────────────────────
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 預熱今日資料..." >> "$LOG"
FINAL=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT 2>/dev/null)
if [ "$FINAL" = "200" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ 預熱完成，今日推薦已就緒 🎯" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  App 無回應 (HTTP $FINAL)，請手動檢查" >> "$LOG"
fi

# ── 5. 推送今日時間戳到 GitHub → 觸發 Streamlit Cloud 重新部署 ─────────────────
# 原理：Streamlit Cloud 偵測到 GitHub 有新 commit 就自動重新部署，
#       重新部署會清除 in-memory cache，讓手機端也能拿到今日新資料。
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 推送 GitHub 觸發雲端刷新..." >> "$LOG"
cd "$APP_DIR"
echo "refreshed: $(date '+%Y-%m-%d %H:%M CST')" > data/last_refreshed.txt
git add data/last_refreshed.txt >> "$LOG" 2>&1
git commit -m "chore: daily refresh $(date '+%Y-%m-%d')" >> "$LOG" 2>&1
if git push origin main >> "$LOG" 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ GitHub 推送成功，Streamlit Cloud 即將重新部署 🚀" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️  GitHub 推送失敗，請檢查網路或 token" >> "$LOG"
fi
