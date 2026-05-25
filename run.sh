#!/bin/bash
# 台灣科技股分析 — 每日早上 8:00 執行
cd "$(dirname "$0")"
/Library/Developer/CommandLineTools/usr/bin/python3 widget.py "$@"
