#!/bin/bash
# 啟動台灣科技股盤前分析 App
cd "$(dirname "$0")"
echo "🚀 啟動台灣科技股分析 App..."
echo "   瀏覽器會自動開啟 http://localhost:8501"
/Library/Developer/CommandLineTools/usr/bin/python3 -m streamlit run app.py \
  --server.port 8501 \
  --server.headless false \
  --theme.base dark \
  --theme.primaryColor "#1565c0" \
  --theme.backgroundColor "#0e1117" \
  --theme.secondaryBackgroundColor "#1c2030" \
  --theme.textColor "#e0e0e0"
