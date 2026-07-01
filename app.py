import streamlit as st
import akshare as ak
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import os
import time
from openai import OpenAI

# 从环境变量读取 DeepSeek API Key（在 Streamlit Cloud 后台设置）
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

st.set_page_config(
    page_title="AI基金匹配",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stButton button { padding: 0.8rem 1.5rem; font-size: 1.1rem; border-radius: 12px; }
    .stRadio label { font-size: 1.1rem; padding: 0.5rem 0; }
    .stTextArea textarea { font-size: 1.05rem; }
    .stDataFrame { font-size: 0.95rem; }
    h1 { font-size: 2rem !important; }
    h2 { font-size: 1.5rem !important; }
</style>
""", unsafe_allow_html=True)

st.title("📈 AI 基金资讯匹配")
st.caption("基于快讯与基金数据，AI 精准匹配相关基金 · 仅供参考")

@st.cache_data(ttl=3600)
def load_fund_list():
    for _ in range(3):
        try:
            df = ak.fund_name_em()
            df = df[['基金代码', '基金简称', '基金类型']]
            return df
        except Exception:
            time.sleep(2)
    st.error("基金数据加载失败")
    return pd.DataFrame()

@st.cache_data(ttl=120)
def fetch_cls_telegraph():
    url = "https://www.cls.cn/telegraph"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.find_all("div", class_="telegraph-content-box")
        news_list = [item.get_text(strip=True) for item in items[:20] if item.get_text(strip=True)]
        return news_list if news_list else ["（暂无快讯）"]
    except Exception as e:
        st.error(f"获取快讯失败: {e}")
        return ["（快讯获取失败）"]

def ai_match_funds(news_text, fund_df):
    fund_brief = fund_df[['基金简称', '基金类型']].to_string(index=False)
    fund_brief = '\n'.join(fund_brief.split('\n')[:200])

    system_prompt = """你是一个金融数据匹配引擎。根据快讯和基金列表，找出最相关的基金。
输出严格JSON数组，每个元素：fund_name, fund_type, reason, strength(高/中/低)。
只输出JSON，没有匹配则输出[]。"""

    user_prompt = f"快讯内容：\n{news_text}\n\n基金列表：\n{fund_brief}"

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        content = response.choices[0].message.content
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as e:
        st.error(f"AI分析出错: {e}")
        return []

news_mode = st.radio("📰 快讯来源", ["自动抓取财联社电报", "手动输入内容"], horizontal=True)

if "news_list" not in st.session_state:
    st.session_state.news_list = []

if news_mode == "自动抓取财联社电报":
    col_btn, col_status = st.columns([1, 3])
    with col_btn:
        if st.button("🔄 获取最新快讯", use_container_width=True):
            with st.spinner("抓取中..."):
                st.session_state.news_list = fetch_cls_telegraph()
    with col_status:
        if st.session_state.news_list:
            st.success(f"已获取 {len(st.session_state.news_list)} 条快讯")
    if st.session_state.news_list:
        selected_news = st.radio("选择要分析的快讯：", st.session_state.news_list)
    else:
        selected_news = None
else:
    selected_news = st.text_area("✏️ 在此粘贴快讯内容", height=150, placeholder="例：工信部发布关于加快人工智能产业发展的指导意见...")

with st.spinner("加载基金数据..."):
    fund_df = load_fund_list()
if not fund_df.empty:
    st.sidebar.write(f"基金库已加载：{len(fund_df)} 只")
else:
    st.sidebar.warning("基金数据暂不可用")

st.markdown("---")
if selected_news and not fund_df.empty:
    if st.button("🔍 开始 AI 匹配基金", type="primary", use_container_width=True):
        with st.spinner("AI 正在分析..."):
            results = ai_match_funds(selected_news, fund_df)
        if results:
            st.subheader(f"✅ 匹配到 {len(results)} 只相关基金")
            res_df = pd.DataFrame(results)
            res_df.columns = ["基金简称", "基金类型", "匹配理由", "匹配强度"]
            st.dataframe(res_df, use_container_width=True, height=300)
        else:
            st.info("未找到高度匹配的基金。")
elif not selected_news:
    st.info("👆 请先获取或输入快讯内容")
else:
    st.warning("基金数据尚未准备就绪")

with st.sidebar:
    st.header("⚙️ 设置")
    if st.button("强制刷新基金列表"):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")
st.caption("⚠️ 本工具仅供个人学习研究，AI 分析结果不构成投资建议。")
