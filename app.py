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

# ---------------------------- 全量基金列表（备选） ----------------------------
@st.cache_data(ttl=3600)
def load_all_funds():
    try:
        df = ak.fund_name_em()
        if not df.empty:
            return df[['基金代码', '基金简称', '基金类型']]
    except:
        pass
    return pd.DataFrame()  # 失败就返回空

# ---------------------------- 快讯聚合 ----------------------------
@st.cache_data(ttl=90)
def fetch_eastmoney_news():
    """东方财富全球快讯"""
    try:
        df = ak.stock_info_global_news_em()
        if df is not None and not df.empty:
            news = []
            for _, row in df.iterrows():
                title = str(row.get("标题", ""))
                summary = str(row.get("摘要", ""))
                if title:
                    full = title + ("：" + summary if summary and summary != "nan" else "")
                    news.append(full)
            return news[:20]
    except:
        return []

def fetch_cls_telegraph():
    """财联社电报"""
    url = "https://www.cls.cn/telegraph"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.find_all("div", class_="telegraph-content-box")
        return [it.get_text(strip=True) for it in items[:15] if it.get_text(strip=True)]
    except:
        return []

def fetch_all_news():
    all_news = []
    seen = set()
    for source in [fetch_eastmoney_news(), fetch_cls_telegraph()]:
        for n in source:
            if n and n not in seen:
                seen.add(n)
                all_news.append(n)
    return all_news[:30] if all_news else ["（暂无快讯，请点击刷新）"]

# ---------------------------- 基金净值 ----------------------------
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

# ---------------------------- 资金流向 ----------------------------
@st.cache_data(ttl=60)
def get_market_flow():
    data = {"北向资金": None, "板块流入": [], "板块流出": []}
    try:
        north = ak.stock_hsgt_north_net_flow_in_em()
        if north is not None and not north.empty:
            data["北向资金"] = north.iloc[-1]["value"]
    except:
        pass
    try:
        sector = ak.stock_sector_fund_flow_rank(indicator="今日")
        if sector is not None and not sector.empty:
            data["板块流入"] = sector.head(3)[["名称", "流入净额"]].to_dict(orient="records")
            data["板块流出"] = sector.tail(3)[["名称", "流入净额"]].to_dict(orient="records")
    except:
        pass
    return data

# ---------------------------- 持仓解析（不依赖全量库） ----------------------------
def parse_holdings(text, fund_df):
    holdings = []
    for line in text.strip().split("\n"):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        code, cost, shares = parts[0], parts[1], parts[2]
        try:
            cost = float(cost)
            shares = float(shares)
        except:
            continue
        # 尝试从全量库匹配名称
        name = code  # 默认显示代码
        ftype = ""
        if not fund_df.empty:
            match = fund_df[fund_df['基金代码'] == code]
            if len(match) == 0:
                match = fund_df[fund_df['基金简称'].str.contains(code, na=False)]
            if len(match) > 0:
                info = match.iloc[0]
                name = info['基金简称']
                ftype = info['基金类型']
        holdings.append({
            "代码": code,
            "名称": name,
            "类型": ftype,
            "成本": cost,
            "份额": shares,
            "成本金额": cost * shares
        })
    return holdings

def compute_holdings(holdings):
    results = []
    for h in holdings:
        nav_data = get_fund_nav_today(h['代码'])
        if nav_data and nav_data.get("单位净值") is not None:
            nav = nav_data["单位净值"]
            daily_change = nav_data.get("日增长率")
            try:
                daily_change = float(daily_change) if daily_change is not None else None
            except:
                daily_change = None
            market_value = nav * h['份额']
            profit = market_value - h['成本金额']
            profit_rate = (nav - h['成本']) / h['成本'] * 100
            results.append({
                "代码": h['代码'], "名称": h['名称'],
                "成本价": h['成本'], "当前净值": nav,
                "份额": h['份额'], "市值": market_value,
                "盈亏": profit, "收益率%": profit_rate,
                "今日涨幅%": daily_change if daily_change is not None else "无数据",
                "净值日期": nav_data.get("净值日期", "")
            })
        else:
            results.append({
                "代码": h['代码'], "名称": h['名称'],
                "成本价": h['成本'], "当前净值": "获取失败",
                "份额": h['份额'], "市值": None,
                "盈亏": None, "收益率%": None, "今日涨幅%": "N/A"
            })
    return results

# ---------------------------- AI 分析 ----------------------------
def ai_analyze_news(news, holdings_text=""):
    prompt = f"你是专业基金投研助手。快讯：{news}\n"
    if holdings_text:
        prompt += f"用户持仓：{holdings_text}\n请分析对持仓的影响，给出操作建议（持有/加仓/减仓/观望）。"
    else:
        prompt += "总结可能影响的市场板块和基金类型。"
    prompt += "输出简洁，200字以内。"
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300
        )
        return resp.choices[0].message.content
    except:
        return "AI 分析暂不可用。"

# ---------------------------- Session State ----------------------------
if "holdings_text" not in st.session_state:
    st.session_state.holdings_text = ""
if "show_news" not in st.session_state:
    st.session_state.show_news = False
if "news_cache" not in st.session_state:
    st.session_state.news_cache = []

# ---------------------------- 侧边栏 ----------------------------
with st.sidebar:
    st.header("💼 我的持仓")
    st.caption("格式：基金代码,成本价,份额（每行一个）")
    holdings_input = st.text_area(
        "输入持仓",
        value=st.session_state.holdings_text,
        height=150,
        placeholder="000001,1.5,1000\n广发纳斯达克,2.8,500"
    )
    if st.button("💾 更新持仓", use_container_width=True):
        st.session_state.holdings_text = holdings_input
        st.rerun()

    st.divider()
    st.subheader("📰 资讯侧边栏")
    st.session_state.show_news = st.checkbox("开启多源快讯与AI分析", value=st.session_state.show_news)
    if st.session_state.show_news:
        if st.button("刷新多源快讯", use_container_width=True):
            with st.spinner("聚合快讯中..."):
                st.session_state.news_cache = fetch_all_news()
        st.caption("数据源：东方财富全球快讯、财联社电报")

    st.divider()
    if st.button("强制刷新全部缓存", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ---------------------------- 主界面 ----------------------------
all_funds = load_all_funds()  # 可能为空

# 1. 持仓分析
if st.session_state.holdings_text.strip():
    holdings = parse_holdings(st.session_state.holdings_text, all_funds)
    if not holdings:
        st.warning("请按格式输入：基金代码,成本价,份额，每行一个")
    else:
        results = compute_holdings(holdings)
        valid = [r for r in results if isinstance(r["市值"], (int, float))]
        if valid:
            total_cost = sum(r['成本价'] * r['份额'] for r in valid)
            total_value = sum(r['市值'] for r in valid)
            total_profit = total_value - total_cost
            total_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0

            col1, col2, col3, col4 = st.columns(4)
            col1.markdown(f"<div class='card'><small>持仓成本</small><br><b>{total_cost:.2f}</b></div>", unsafe_allow_html=True)
            col2.markdown(f"<div class='card'><small>持仓市值</small><br><b>{total_value:.2f}</b></div>", unsafe_allow_html=True)
            col3.markdown(f"<div class='card'><small>累计盈亏</small><br><b class='{'positive' if total_profit>=0 else 'negative'}'>{total_profit:+.2f}</b></div>", unsafe_allow_html=True)
            col4.markdown(f"<div class='card'><small>总收益率</small><br><b class='{'positive' if total_rate>=0 else 'negative'}'>{total_rate:+.2f}%</b></div>", unsafe_allow_html=True)

            st.subheader("📋 持仓明细")
            res_df = pd.DataFrame(results)
            st.dataframe(res_df, use_container_width=True, height=250)

            st.subheader("📈 今日涨幅估算")
            change_cols = st.columns(len(results))
            for i, r in enumerate(results):
                with change_cols[i]:
                    val = r.get("今日涨幅%")
                    if isinstance(val, (int, float)):
                        color = "positive" if val >= 0 else "negative"
                        st.markdown(f"<div class='card'><small>{r['名称']}</small><br><b class='{color}'>{val:+.2f}%</b></div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='card'><small>{r['名称']}</small><br>--</div>", unsafe_allow_html=True)
        else:
            st.warning("当前持仓净值获取失败，可能是接口波动，请稍后刷新。")
else:
    st.info("👈 在左侧输入你的基金持仓（代码,成本价,份额），每行一个。")

# 2. 资金流向
st.markdown("---")
st.subheader("💰 市场资金流向")
flow = get_market_flow()
col1, col2 = st.columns(2)
with col1:
    north = flow.get("北向资金")
    if north is not None:
        st.metric("北向资金净流入（亿元）", f"{north:.2f}")
    else:
        st.write("北向资金数据获取失败")
with col2:
    st.write("📈 板块流入 TOP3")
    if flow["板块流入"]:
        for item in flow["板块流入"]:
            st.write(f"· {item['名称']} : {item['流入净额']}")
    else:
        st.write("暂无数据")
    st.write("📉 板块流出 TOP3")
    if flow["板块流出"]:
        for item in flow["板块流出"]:
            st.write(f"· {item['名称']} : {item['流入净额']}")
    else:
        st.write("暂无数据")

# 3. 快讯与AI
if st.session_state.show_news:
    st.markdown("---")
    st.subheader("📰 多源实时快讯 & AI 解读")
    if not st.session_state.news_cache:
        st.session_state.news_cache = fetch_all_news()
    if st.session_state.news_cache:
        selected_news = st.selectbox("选择快讯进行AI分析", st.session_state.news_cache)
        if selected_news:
            with st.spinner("AI 分析中..."):
                analysis = ai_analyze_news(selected_news, st.session_state.holdings_text)
            st.markdown(f"**快讯内容：** {selected_news}")
            st.markdown(f"**AI 分析：** {analysis}")
    else:
        st.write("暂无法获取快讯，请点击侧边栏刷新。")

st.markdown("---")
st.caption("⚠️ 数据来源公开接口，仅供个人学习研究，不构成投资建议。")
