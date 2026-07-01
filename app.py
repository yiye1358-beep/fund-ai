import streamlit as st
import akshare as ak
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime
from openai import OpenAI

# ---------------------------- 配置 ----------------------------
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

st.set_page_config(
    page_title="基金控制台 Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stButton button { padding: 0.8rem 1.5rem; font-size: 1.1rem; border-radius: 12px; }
    .stTextArea textarea, .stTextInput input { font-size: 1.05rem; }
    .positive { color: #e63946; font-weight: bold; }
    .negative { color: #2a9d8f; font-weight: bold; }
    .card {
        background: #f8f9fa; border-radius: 12px; padding: 1rem; margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 基金控制台 Pro")
st.caption("多源快讯 · 持仓盈亏 · 资金流向 · AI 解读")

# ---------------------------- 核心数据加载（带明确状态） ----------------------------
@st.cache_data(ttl=3600)
def load_all_funds():
    """加载全市场基金列表，失败返回空 DataFrame"""
    for i in range(3):
        try:
            df = ak.fund_name_em()
            # 确保列存在
            if not df.empty and '基金代码' in df.columns:
                return df[['基金代码', '基金简称', '基金类型']]
        except Exception as e:
            if i == 2:
                st.error(f"基金数据加载失败，请稍后刷新重试。错误：{e}")
            time.sleep(2)
    return pd.DataFrame()

# ---------------------------- 多源快讯（使用已验证存在的接口） ----------------------------
@st.cache_data(ttl=90)
def fetch_js_news():
    """金十数据实时快讯（稳定）"""
    try:
        df = ak.js_news()
        if df is not None and not df.empty:
            # 通常有 'content' 或 'title' 列
            if 'content' in df.columns:
                return [str(c) for c in df['content'].tolist() if str(c) != 'nan'][:20]
            elif 'title' in df.columns:
                return [str(t) for t in df['title'].tolist() if str(t) != 'nan'][:20]
    except:
        pass
    return []

def fetch_cls_telegraph():
    """财联社电报（备用，抓公开页面）"""
    url = "https://www.cls.cn/telegraph"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(resp.text, "html.parser")
        # 尝试多种可能的 class
        items = soup.find_all("div", class_="telegraph-content-box")
        if not items:
            items = soup.find_all("div", class_="content")
        return [it.get_text(strip=True) for it in items[:15] if it.get_text(strip=True)]
    except:
        return []

def fetch_all_news():
    """聚合金十和财联社，去重"""
    all_news = []
    seen = set()
    for news_list in [fetch_js_news(), fetch_cls_telegraph()]:
        for n in news_list:
            if n and n not in seen:
                seen.add(n)
                all_news.append(n)
    if not all_news:
        return ["（暂无快讯，请点击侧边栏刷新）"]
    return all_news[:30]

# ---------------------------- 基金净值与资金流向（不变） ----------------------------
@st.cache_data(ttl=120)
def get_fund_nav_today(fund_code):
    try:
        df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            return {
                "净值日期": str(latest["净值日期"]),
                "单位净值": latest["单位净值"],
                "日增长率": latest.get("日增长率", None)
            }
    except:
        pass
    try:
        est = ak.fund_em_value_estimation(symbol=fund_code)
        if est is not None and not est.empty:
            e = est.iloc[0]
            return {
                "净值日期": "实时估算",
                "单位净值": e.get("估算值", None),
                "日增长率": e.get("估算增长率", None)
            }
    except:
        pass
    return None

@st.cache_data(ttl=60)
def get_market_flow():
    data = {"北向资金": None, "板块流入": [], "板块流出
