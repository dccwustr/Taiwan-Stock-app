# -*- coding: utf-8 -*-
"""
獨立部署版：台股即時資金流向
Streamlit Cloud → Main file path: flow_app.py
（st.navigation 會讓 Streamlit 忽略 pages/ 資料夾，只顯示這一頁）
"""
import streamlit as st

st.navigation([st.Page("pages/1_💸_資金流向.py", title="台股即時資金流向", icon="💸")],
              position="hidden").run()
