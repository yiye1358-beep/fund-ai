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
    page_title="基金控制台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------------------------- Apple 风格 CSS ----------------------------
st.markdown("""
<style>
    /* 全局字体 */
    * { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    
    /* 主背景 */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    
    /* 卡片样式 - 毛玻璃效果 */
    .glass-card {
        background: rgba(255, 255, 255, 0.72);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.3);
        padding: 24px;
        margin: 12px 0;
        box-shadow: 0 8px 32px rgba(31, 38, 135, 0.07);
    }
    
    /* 按钮 - Apple 风格 */
    .stButton > button {
        background: linear-gradient(135deg, #007AFF 0%, #5856D6 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 12px 24px;
        font-size: 15px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0, 122, 255, 0.3);
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 122, 255, 0.4);
    }
    
    /* 输入框 */
    .stTextArea textarea {
        border-radius: 16px;
        border: 1px solid rgba(0,0,0,0.1);
        background: rgba(255,255,255,0.8);
        padding: 16px;
        font-size: 15px;
    }
    
    /* 选择框 */
    .stSelectbox > div > div {
        border-radius: 12px;
        background: rgba(255,255,255,0.8);
    }
    
    /* 标题 */
    h1 {
        font-size: 32px !important;
        font-weight: 700 !important;
        background: linear-gradient(135deg, #1d1d1f 0%, #434344 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    h2 {
        font-size: 22px !important;
        font-weight: 600 !important;
        color: #1d1d1f;
    }
    
    /* 数据指标 */
    .metric-value {
        font-size: 28px;
        font-weight: 700;
        color: #1d1d1f;
    }
    .metric-label {
        font-size: 13px;
        color: #86868b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* 涨跌颜色 */
    .up { color: #ff3b30; }
    .down { color: #34c759; }
    
    /* 表格 */
    .stDataFrame {
        border-radius: 16px;
        overflow: hidden;
    }
    
    /* 侧边栏 */
    .css-1d39120 {
        background: rgba(255,255,255,0.6);
        backdrop-filter: blur(20px);
    }
    
    /* 标签页 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        padding: 8px 16px;
        background: rgba(255,255,255,0.5);
    }
    .stTabs [aria-selected="true"] {
        background: #007AFF !important;
        color: white !important;
    }
    
    /* 分割线 */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(0,0,0,0.1), transparent);
        margin: 32px 0;
    }
    
    /* 提示文字 */
    .caption {
        color: #86868b;
        font-size: 12px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------- 标题区域 ----------------------------
col_title, col_time = st.columns([3, 1])
with col_title:
    st.title("📊 基金控制台")
    st.caption("智能持仓 · 实时估值 · AI 投研")
with col_time:
    st.markdown(f"""
    <div style="text-align:right; padding-top:12px">
        <div style="font-size:24px; font-weight:600; color:#1d1d1f">{datetime.now().strftime("%H:%M")}</div>
        <div style="font-size:12px; color:#86868b">{datetime.now().strftime("%Y年%m月%d日")}</div>
    </div>
    """, unsafe_allow_html=True)

# ---------------------------- 全量基金列表 ----------------------------
@st.cache_data(ttl=3600)
def load_all_funds():
    try:
        df = ak.fund_name_em()
        if not df.empty and '基金代码' in df.columns:
            return df[['基金代码', '基金简称', '基金类型']]
    except:
        pass
    return pd.DataFrame()

# ---------------------------- 净值获取（多源备用） ----------------------------
@st.cache_data(ttl=300)
def get_fund_nav_today(fund_code):
    clean_code = fund_code.strip().replace('.OF', '').replace('.of', '')
    
    # 源1: 天天基金实时估值
    try:
        df = ak.fund_em_realtime_nav(clean_code)
        if df is not None and not df.empty:
            latest = df.iloc[0]
            nav = latest.get('净值', latest.get('单位净值', None))
            change = latest.get('估算涨幅', latest.get('日增长率', None))
            return {
                "净值日期": "实时估值",
                "单位净值": float(nav) if nav else None,
                "日增长率": float(change) if change else None,
                "来源": "实时估值"
            }
    except:
        pass
    
    # 源2: 历史净值
    try:
        df = ak.fund_open_fund_info_em(symbol=clean_code, indicator="单位净值走势")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            return {
                "净值日期": str(latest.get("净值日期", "")),
                "单位净值": float(latest["单位净值"]) if "单位净值" in latest else None,
                "日增长率": float(latest.get("日增长率", 0)) if latest.get("日增长率") else None,
                "来源": "历史净值"
            }
    except:
        pass
    
    return None

# ---------------------------- 快讯聚合 ----------------------------
@st.cache_data(ttl=90)
def fetch_eastmoney_news():
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

# ---------------------------- 资金流向 ----------------------------
@st.cache_data(ttl=60)
def get_market_flow():
    data = {"北向资金": None, "板块流入": [], "板块流出": []}
    try:
        north = ak.stock_hsgt_north_net_flow_in_em()
        if north is not None and not north.empty:
            data["北向资金"] = float(north.iloc[-1]["value"])
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

# ---------------------------- 持仓解析 ----------------------------
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
        
        name = code
        ftype = ""
        clean_code = code.replace('.OF', '').replace('.of', '')
        
        if not fund_df.empty:
            match = fund_df[fund_df['基金代码'] == clean_code]
            if len(match) == 0:
                match = fund_df[fund_df['基金简称'].str.contains(code, na=False)]
            if len(match) > 0:
                info = match.iloc[0]
                name = info['基金简称']
                ftype = info['基金类型']
        
        holdings.append({
            "代码": clean_code,
            "显示代码": code,
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
        if nav_data and nav_data.get("单位净值"):
            nav = nav_data["单位净值"]
            daily_change = nav_data.get("日增长率")
            try:
                daily_change = float(daily_change) if daily_change is not None else None
            except:
                daily_change = None
            
            market_value = nav * h['份额']
            profit = market_value - h['成本金额']
            profit_rate = (nav - h['成本']) / h['成本'] * 100 if h['成本'] > 0 else 0
            
            results.append({
                "代码": h['显示代码'],
                "名称": h['名称'],
                "类型": h['类型'],
                "成本价": h['成本'],
                "当前净值": nav,
                "份额": h['份额'],
                "市值": market_value,
                "盈亏": profit,
                "收益率%": profit_rate,
                "今日涨幅%": daily_change if daily_change is not None else "无数据",
                "净值日期": nav_data.get("净值日期", ""),
                "来源": nav_data.get("来源", "")
            })
        else:
            results.append({
                "代码": h['显示代码'],
                "名称": h['名称'],
                "类型": h['类型'],
                "成本价": h['成本'],
                "当前净值": "获取失败",
                "份额": h['份额'],
                "市值": None,
                "盈亏": None,
                "收益率%": None,
                "今日涨幅%": "N/A",
                "净值日期": "",
                "来源": "失败"
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
    except Exception as e:
        return f"AI 分析暂不可用：{str(e)[:50]}"

# ---------------------------- Session State ----------------------------
if "holdings_text" not in st.session_state:
    st.session_state.holdings_text = ""
if "news_cache" not in st.session_state:
    st.session_state.news_cache = []

# ---------------------------- 侧边栏（折叠） ----------------------------
with st.sidebar:
    st.header("⚙️ 设置")
    
    # 持仓输入
    st.subheader("💼 我的持仓")
    st.caption("格式：代码,成本价,份额")
    holdings_input = st.text_area(
        "输入持仓",
        value=st.session_state.holdings_text,
        height=120,
        placeholder="000001,1.5,1000\n270042,2.8,500"
    )
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 保存", use_container_width=True):
            st.session_state.holdings_text = holdings_input
            st.success("已保存")
            time.sleep(0.5)
            st.rerun()
    with c2:
        if st.button("🗑️ 清空", use_container_width=True):
            st.session_state.holdings_text = ""
            st.rerun()
    
    st.divider()
    
    # 快讯控制
    st.subheader("📰 快讯")
    if st.button("🔄 刷新快讯", use_container_width=True):
        with st.spinner("获取中..."):
            st.session_state.news_cache = fetch_all_news()
    if st.session_state.news_cache:
        st.success(f"{len(st.session_state.news_cache)} 条")
    
    st.divider()
    
    # 缓存控制
    if st.button("🔄 刷新全部缓存", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ---------------------------- 主界面 ----------------------------
all_funds = load_all_funds()

# ========== 持仓总览卡片 ==========
if st.session_state.holdings_text.strip():
    holdings = parse_holdings(st.session_state.holdings_text, all_funds)
    
    if holdings:
        results = compute_holdings(holdings)
        valid = [r for r in results if isinstance(r["市值"], (int, float))]
        
        if valid:
            total_cost = sum(r['成本价'] * r['份额'] for r in valid)
            total_value = sum(r['市值'] for r in valid)
            total_profit = total_value - total_cost
            total_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0
            
            # Apple 风格汇总卡片
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            cols = st.columns(4)
            metrics = [
                ("总资产", f"¥{total_value:,.2f}", "💰"),
                ("累计收益", f"{total_profit:+.2f}", "📈" if total_profit >= 0 else "📉"),
                ("收益率", f"{total_rate:+.2f}%", "🎯"),
                ("持仓数量", f"{len(valid)}只", "📊")
            ]
            for col, (label, value, emoji) in zip(cols, metrics):
                with col:
                    color = "up" if total_profit >= 0 else "down"
                    st.markdown(f"""
                    <div style="text-align:center">
                        <div class="metric-label">{emoji} {label}</div>
                        <div class="metric-value {color if label in ['累计收益', '收益率'] else ''}">{value}</div>
                    </div>
                    """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # 持仓明细
            st.markdown("### 📋 持仓明细")
            display_data = []
            for r in results:
                nav_display = f"{r['当前净值']:.4f}" if isinstance(r['当前净值'], float) else r['当前净值']
                profit_display = f"{r['收益率%']:+.2f}%" if isinstance(r['收益率%'], float) else "-"
                change_display = f"{r['今日涨幅%']:+.2f}%" if isinstance(r['今日涨幅%'], float) else r['今日涨幅%']
                change_color = "up" if isinstance(r['今日涨幅%'], float) and r['今日涨幅%'] >= 0 else "down"
                
                display_data.append({
                    "基金名称": r['名称'],
                    "代码": r['代码'],
                    "成本": f"{r['成本价']:.3f}",
                    "净值": nav_display,
                    "份额": f"{r['份额']:.2f}",
                    "市值": f"¥{r['市值']:,.2f}" if isinstance(r['市值'], float) else "-",
                    "收益": profit_display,
                    "今日": f"<span class='{change_color}'>{change_display}</span>" if isinstance(r['今日涨幅%'], float) else change_display
                })
            
            df_display = pd.DataFrame(display_data)
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # 今日涨跌可视化
            st.markdown("### 📈 今日涨跌")
            change_data = [(r['名称'], r['今日涨幅%']) for r in results if isinstance(r['今日涨幅%'], float)]
            if change_data:
                cols = st.columns(min(len(change_data), 6))
                for i, (name, val) in enumerate(change_data):
                    with cols[i % 6]:
                        color_class = "up" if val >= 0 else "down"
                        emoji = "📈" if val >= 0 else "📉"
                        st.markdown(f"""
                        <div class="glass-card" style="text-align:center; padding:16px">
                            <div style="font-size:13px; color:#86868b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">{name[:8]}</div>
                            <div style="font-size:24px; font-weight:700; color:{'#ff3b30' if val >= 0 else '#34c759'}">{emoji} {val:+.2f}%</div>
                        </div>
                        """, unsafe_allow_html=True)
        else:
            st.warning("净值获取失败，请检查基金代码或稍后刷新")
    else:
        st.warning("持仓格式错误，请使用：代码,成本价,份额")
else:
    # 空状态
    st.markdown("""
    <div class="glass-card" style="text-align:center; padding:60px 20px">
        <div style="font-size:64px; margin-bottom:16px">💼</div>
        <div style="font-size:20px; font-weight:600; color:#1d1d1f; margin-bottom:8px">暂无持仓</div>
        <div style="font-size:14px; color:#86868b">点击左上角 ☰ 打开设置，输入你的基金持仓</div>
    </div>
    """, unsafe_allow_html=True)

# ========== 市场资金流向 ==========
st.markdown("---")
st.markdown("### 💰 市场资金流向")

flow = get_market_flow()
c1, c2 = st.columns([1, 2])

with c1:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    north = flow.get("北向资金")
    if north is not None:
        st.markdown(f"""
        <div style="text-align:center">
            <div class="metric-label">北向资金净流入</div>
            <div class="metric-value" style="color:{'#ff3b30' if north >= 0 else '#34c759'}">{north:+.2f}亿</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="text-align:center">
            <div class="metric-label">北向资金</div>
            <div style="font-size:14px; color:#86868b; margin-top:8px">非交易时间</div>
            <div style="font-size:12px; color:#86868b">工作日 9:30-15:00</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c2:
    tab1, tab2 = st.tabs(["📈 板块流入", "📉 板块流出"])
    with tab1:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        if flow["板块流入"]:
            for item in flow["板块流入"]:
                st.markdown(f"**{item['名称']}**  {item['流入净额']}")
        else:
            st.write("暂无数据")
        st.markdown('</div>', unsafe_allow_html=True)
    with tab2:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        if flow["板块流出"]:
            for item in flow["板块流出"]:
                st.markdown(f"**{item['名称']}**  {item['流入净额']}")
        else:
            st.write("暂无数据")
        st.markdown('</div>', unsafe_allow_html=True)

# ========== 快讯与 AI ==========
st.markdown("---")
st.markdown("### 📰 实时快讯 & AI 解读")

if not st.session_state.news_cache:
    st.session_state.news_cache = fetch_all_news()

if st.session_state.news_cache and st.session_state.news_cache[0] != "（暂无快讯，请点击刷新）":
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    selected_news = st.selectbox("选择快讯", st.session_state.news_cache, key="news_select")
    
    if selected_news and st.button("🔍 DeepSeek AI 分析", type="primary"):
        with st.spinner("AI 分析中..."):
            analysis = ai_analyze_news(selected_news, st.session_state.holdings_text)
        
        st.markdown(f"""
        <div style="background:rgba(0,122,255,0.08); border-radius:16px; padding:20px; margin-top:16px; border-left:4px solid #007AFF">
            <div style="font-size:13px; font-weight:600; color:#007AFF; margin-bottom:8px">🤖 DeepSeek 分析</div>
            <div style="font-size:15px; color:#1d1d1f; line-height:1.6">{analysis}</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.write("暂无快讯数据")
    if st.button("🔄 刷新"):
        st.session_state.news_cache = fetch_all_news()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")
st.caption("⚠️ 数据来源公开接口，仅供个人学习研究，不构成投资建议。")
