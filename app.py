import streamlit as st
import akshare as ak
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import json
import os
import time
import sqlite3
import hashlib
from datetime import datetime, timedelta
from openai import OpenAI
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==================== 配置 ====================
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# 数据库路径（Streamlit Cloud 持久化存储）
DB_PATH = "fundos.db"

st.set_page_config(
    page_title="FundOS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== Apple 风格 CSS ====================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
    
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    .glass-card {
        background: rgba(255, 255, 255, 0.85);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-radius: 24px;
        border: 1px solid rgba(255, 255, 255, 0.4);
        padding: 28px;
        margin: 16px 0;
        box-shadow: 0 8px 32px rgba(31, 38, 135, 0.1);
    }
    
    .glass-card-dark {
        background: rgba(30, 30, 30, 0.85);
        backdrop-filter: blur(20px);
        border-radius: 24px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 28px;
        margin: 16px 0;
        color: white;
    }
    
    .metric-large {
        font-size: 36px;
        font-weight: 700;
        color: #1d1d1f;
    }
    
    .metric-label {
        font-size: 13px;
        color: #86868b;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        font-weight: 500;
    }
    
    .up { color: #ff3b30; }
    .down { color: #34c759; }
    
    .stButton > button {
        background: linear-gradient(135deg, #007AFF 0%, #5856D6 100%);
        color: white;
        border: none;
        border-radius: 14px;
        padding: 14px 28px;
        font-size: 15px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0, 122, 255, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0, 122, 255, 0.4);
    }
    
    .stTextArea textarea, .stTextInput input {
        border-radius: 16px;
        border: 1px solid rgba(0,0,0,0.08);
        background: rgba(255,255,255,0.9);
        padding: 16px;
        font-size: 15px;
    }
    
    h1 { font-size: 32px !important; font-weight: 700 !important; }
    h2 { font-size: 22px !important; font-weight: 600 !important; }
    h3 { font-size: 18px !important; font-weight: 600 !important; }
    
    .nav-pill {
        display: inline-block;
        padding: 8px 20px;
        border-radius: 20px;
        background: rgba(0,122,255,0.1);
        color: #007AFF;
        font-size: 13px;
        font-weight: 600;
        margin: 4px;
    }
    
    .tag {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
    }
    .tag-tech { background: rgba(0,122,255,0.15); color: #007AFF; }
    .tag-warning { background: rgba(255,59,48,0.15); color: #ff3b30; }
    .tag-success { background: rgba(52,199,89,0.15); color: #34c759; }
    
    .divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(0,0,0,0.1), transparent);
        margin: 32px 0;
    }
</style>
""", unsafe_allow_html=True)
# ==================== 数据库初始化 ====================
def init_db():
    """初始化 SQLite 数据库"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 持仓表
    c.execute('''
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT,
            cost REAL NOT NULL,
            shares REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code)
        )
    ''')
    
    # 净值历史表
    c.execute('''
        CREATE TABLE IF NOT EXISTS nav_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            nav REAL,
            change_pct REAL,
            date TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 投资日志表
    c.execute('''
        CREATE TABLE IF NOT EXISTS journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            action TEXT,
            code TEXT,
            reason TEXT,
            emotion TEXT,
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 预警设置表
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            alert_type TEXT,
            threshold REAL,
            triggered INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 科技基金关注表
    c.execute('''
        CREATE TABLE IF NOT EXISTS tech_watch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            sector TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# 初始化数据库
init_db()

# ==================== 数据库操作函数 ====================
def db_save_holding(code, name, cost, shares):
    """保存或更新持仓"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO holdings (code, name, cost, shares) 
        VALUES (?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
        name=excluded.name, cost=excluded.cost, shares=excluded.shares,
        updated_at=CURRENT_TIMESTAMP
    ''', (code, name, cost, shares))
    conn.commit()
    conn.close()

def db_get_holdings():
    """获取所有持仓"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM holdings ORDER BY updated_at DESC", conn)
    conn.close()
    return df

def db_delete_holding(code):
    """删除持仓"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM holdings WHERE code=?", (code,))
    conn.commit()
    conn.close()

def db_save_nav(code, nav, change_pct, date, source):
    """保存净值历史"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO nav_history (code, nav, change_pct, date, source)
        VALUES (?, ?, ?, ?, ?)
    ''', (code, nav, change_pct, date, source))
    conn.commit()
    conn.close()

def db_get_nav_history(code, days=30):
    """获取净值历史"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query('''
        SELECT * FROM nav_history 
        WHERE code=? AND date>=date('now', '-{} days')
        ORDER BY date DESC
    '''.format(days), conn)
    conn.close()
    return df

def db_add_journal(date, action, code, reason, emotion, result):
    """添加投资日志"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO journal (date, action, code, reason, emotion, result)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (date, action, code, reason, emotion, result))
    conn.commit()
    conn.close()

def db_get_journals(limit=50):
    """获取投资日志"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query('''
        SELECT * FROM journal ORDER BY created_at DESC LIMIT ?
    ''', conn, params=(limit,))
    conn.close()
    return df

def db_add_alert(code, alert_type, threshold):
    """添加预警"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO alerts (code, alert_type, threshold)
        VALUES (?, ?, ?)
    ''', (code, alert_type, threshold))
    conn.commit()
    conn.close()

def db_get_alerts():
    """获取所有预警"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM alerts WHERE triggered=0", conn)
    conn.close()
    return df

def db_add_tech_watch(code, name, sector):
    """添加科技基金关注"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO tech_watch (code, name, sector)
        VALUES (?, ?, ?)
    ''', (code, name, sector))
    conn.commit()
    conn.close()

def db_get_tech_watch():
    """获取科技基金关注列表"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM tech_watch ORDER BY added_at DESC", conn)
    conn.close()
    return df

# ==================== 基金数据服务 ====================
@st.cache_data(ttl=3600)
def load_all_funds():
    """加载全市场基金列表"""
    try:
        df = ak.fund_name_em()
        if not df.empty and '基金代码' in df.columns:
            return df[['基金代码', '基金简称', '基金类型']]
    except Exception as e:
        st.sidebar.warning(f"基金库加载异常: {e}")
    return pd.DataFrame()

@st.cache_data(ttl=300)
def get_fund_nav(code):
    """多源获取基金净值"""
    clean_code = code.strip().replace('.OF', '').replace('.of', '')
    
    # 源1: 天天基金实时估值
    try:
        df = ak.fund_em_realtime_nav(clean_code)
        if df is not None and not df.empty:
            latest = df.iloc[0]
            nav = latest.get('净值', latest.get('单位净值', None))
            change = latest.get('估算涨幅', latest.get('日增长率', None))
            result = {
                "code": clean_code,
                "nav": float(nav) if nav else None,
                "change": float(change) if change else 0,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source": "实时估值"
            }
            db_save_nav(clean_code, result["nav"], result["change"], result["date"], result["source"])
            return result
    except:
        pass
    
    # 源2: 历史净值
    try:
        df = ak.fund_open_fund_info_em(symbol=clean_code, indicator="单位净值走势")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            result = {
                "code": clean_code,
                "nav": float(latest["单位净值"]) if "单位净值" in latest else None,
                "change": float(latest.get("日增长率", 0)) if latest.get("日增长率") else 0,
                "date": str(latest.get("净值日期", "")),
                "source": "历史净值"
            }
            db_save_nav(clean_code, result["nav"], result["change"], result["date"], result["source"])
            return result
    except:
        pass
    
    # 源3: 从数据库找最新
    history = db_get_nav_history(clean_code, days=7)
    if not history.empty:
        latest = history.iloc[0]
        return {
            "code": clean_code,
            "nav": latest["nav"],
            "change": latest["change_pct"],
            "date": latest["date"],
            "source": "缓存"
        }
    
    return None

def get_fund_name_type(code, fund_df):
    """获取基金名称和类型"""
    if fund_df.empty:
        return code, ""
    clean = code.replace('.OF', '').replace('.of', '')
    match = fund_df[fund_df['基金代码'] == clean]
    if len(match) == 0:
        match = fund_df[fund_df['基金简称'].str.contains(code, na=False)]
    if len(match) > 0:
        info = match.iloc[0]
        return info['基金简称'], info['基金类型']
    return code, ""

# ==================== 新闻聚合 ====================
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

# ==================== 资金流向 ====================
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

# ==================== DeepSeek AI ====================
def ai_analyze(text, context=""):
    """通用 AI 分析"""
    try:
        prompt = context + "\n\n" + text if context else text
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"AI 分析暂不可用：{str(e)[:80]}"

def ai_portfolio_advice(holdings_text, market_context=""):
    """AI 调仓建议"""
    prompt = f"""你是资深基金经理。请分析以下持仓并给出建议：

持仓：{holdings_text}
市场情况：{market_context}

请给出：
1. 整体仓位建议（满仓/重仓/半仓/轻仓）
2. 需要关注的板块
3. 具体调仓建议
4. 风险提示

输出简洁，300字以内。"""
    return ai_analyze(prompt)

def ai_risk_warning(holdings_text):
    """AI 风险预警"""
    prompt = f"""分析以下持仓的潜在风险：

{holdings_text}

请指出：
1. 集中度风险
2. 板块过度暴露
3. 近期需要关注的风险事件
4. 建议的止损/止盈位置

输出简洁，200字以内。"""
    return ai_analyze(prompt)

def ai_news_impact(news, holdings_text=""):
    """AI 新闻影响分析"""
    prompt = f"快讯：{news}\n"
    if holdings_text:
        prompt += f"用户持仓：{holdings_text}\n请分析对持仓的影响，给出操作建议。"
    else:
        prompt += "总结可能影响的市场板块和基金类型。"
    prompt += "输出简洁，200字以内。"
    return ai_analyze(prompt)

# ==================== 科技基金雷达 ====================
TECH_SECTORS = {
    "AI/人工智能": ["人工智能", "AI", "ChatGPT", "大模型", "算力"],
    "半导体/芯片": ["半导体", "芯片", "集成电路", "晶圆", "光刻"],
    "新能源": ["新能源", "光伏", "储能", "锂电池", "电动车"],
    "消费电子": ["消费电子", "苹果", "华为", "手机", "可穿戴"],
    "生物医药": ["生物医药", "创新药", "CXO", "医疗器械", "基因"],
    "云计算": ["云计算", "大数据", "SaaS", "数据中心", "IDC"]
}

def identify_tech_sector(name):
    """识别基金所属科技赛道"""
    name = str(name)
    for sector, keywords in TECH_SECTORS.items():
        for kw in keywords:
            if kw in name:
                return sector
    return "其他科技"

# ==================== 工具函数 ====================
def format_money(value):
    """格式化金额"""
    if value is None:
        return "-"
    if abs(value) >= 10000:
        return f"{value/10000:.2f}万"
    return f"{value:.2f}"

def format_pct(value):
    """格式化百分比"""
    if value is None:
        return "-"
    return f"{value:+.2f}%"

def get_color_class(value):
    """获取涨跌颜色类"""
    if value is None:
        return ""
    return "up" if value >= 0 else "down"

# ==================== Session State 初始化 ====================
if "page" not in st.session_state:
    st.session_state.page = "总览"
if "news_cache" not in st.session_state:
    st.session_state.news_cache = []
if "last_update" not in st.session_state:
    st.session_state.last_update = None
# ==================== 页面路由 ====================
def render_header():
    """渲染顶部导航"""
    cols = st.columns([1, 4, 1])
    with cols[0]:
        st.markdown(f"""
        <div style="padding-top:8px">
            <span style="font-size:28px">📊</span>
            <span style="font-size:20px; font-weight:700; color:white">FundOS</span>
        </div>
        """, unsafe_allow_html=True)
    with cols[1]:
        pages = ["总览", "持仓", "AI投研", "市场", "科技雷达", "日志"]
        page_cols = st.columns(len(pages))
        for i, page in enumerate(pages):
            with page_cols[i]:
                if st.button(page, key=f"nav_{page}", use_container_width=True):
                    st.session_state.page = page
                    st.rerun()
    with cols[2]:
        st.markdown(f"""
        <div style="text-align:right; color:rgba(255,255,255,0.8); font-size:13px; padding-top:12px">
            {datetime.now().strftime("%H:%M")}
        </div>
        """, unsafe_allow_html=True)

# ==================== 总览页面 ====================
def page_overview():
    """总览仪表盘"""
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    
    # 获取数据
    holdings_df = db_get_holdings()
    all_funds = load_all_funds()
    
    if holdings_df.empty:
        st.markdown("""
        <div style="text-align:center; padding:60px 20px">
            <div style="font-size:64px; margin-bottom:20px">💼</div>
            <div style="font-size:24px; font-weight:600; color:#1d1d1f; margin-bottom:12px">开始你的投资之旅</div>
            <div style="font-size:15px; color:#86868b; margin-bottom:24px">点击上方「持仓」添加你的第一只基金</div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        return
    
    # 计算持仓数据
    total_cost = 0
    total_value = 0
    today_change = 0
    holding_details = []
    
    for _, row in holdings_df.iterrows():
        code = row['code']
        cost = row['cost']
        shares = row['shares']
        name = row['name'] or code
        
        nav_data = get_fund_nav(code)
        if nav_data and nav_data['nav']:
            nav = nav_data['nav']
            change = nav_data['change'] or 0
            market_value = nav * shares
            cost_amount = cost * shares
            profit = market_value - cost_amount
            profit_rate = (nav - cost) / cost * 100 if cost > 0 else 0
            
            total_cost += cost_amount
            total_value += market_value
            today_change += market_value * change / 100 if change else 0
            
            holding_details.append({
                'name': name,
                'code': code,
                'nav': nav,
                'change': change,
                'market_value': market_value,
                'profit': profit,
                'profit_rate': profit_rate
            })
        else:
            holding_details.append({
                'name': name,
                'code': code,
                'nav': None,
                'change': None,
                'market_value': cost * shares,
                'profit': 0,
                'profit_rate': 0
            })
    
    total_profit = total_value - total_cost
    total_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0
    
    # 核心指标卡片
    st.markdown("### 📈 资产总览")
    cols = st.columns(4)
    metrics = [
        ("总资产", f"¥{total_value:,.2f}", "💰", None),
        ("累计收益", f"{total_profit:+.2f}", "📊", total_profit),
        ("收益率", f"{total_rate:+.2f}%", "🎯", total_rate),
        ("今日预估", f"{today_change:+.2f}", "📅", today_change)
    ]
    for col, (label, value, emoji, color_val) in zip(cols, metrics):
        with col:
            color = ""
            if color_val is not None:
                color = "up" if color_val >= 0 else "down"
            st.markdown(f"""
            <div style="text-align:center; padding:16px; background:rgba(255,255,255,0.5); border-radius:16px">
                <div class="metric-label">{emoji} {label}</div>
                <div class="metric-large {color}">{value}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 资产配置图
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 🥧 资产配置")
    
    valid_holdings = [h for h in holding_details if h['nav'] is not None]
    if valid_holdings:
        fig = go.Figure(data=[go.Pie(
            labels=[h['name'][:8] for h in valid_holdings],
            values=[h['market_value'] for h in valid_holdings],
            hole=0.5,
            marker=dict(colors=px.colors.sequential.Plasma_r),
            textinfo='label+percent',
            textfont=dict(size=12)
        )])
        fig.update_layout(
            showlegend=False,
            margin=dict(t=0, b=0, l=0, r=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暂无可用数据")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 收益曲线
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 📉 收益走势（近30天）")
    
    # 模拟/真实收益曲线
    dates = [(datetime.now() - timedelta(days=i)).strftime("%m-%d") for i in range(29, -1, -1)]
    
    # 尝试从数据库获取历史
    nav_data_list = []
    for h in valid_holdings[:3]:  # 取前3只
        history = db_get_nav_history(h['code'], days=30)
        if not history.empty:
            nav_data_list.append(history)
    
    if nav_data_list:
        fig = go.Figure()
        for i, hist in enumerate(nav_data_list):
            if not hist.empty:
                fig.add_trace(go.Scatter(
                    x=hist['date'].tolist(),
                    y=hist['nav'].tolist(),
                    mode='lines',
                    name=valid_holdings[i]['name'][:8],
                    line=dict(width=2)
                ))
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=300,
            margin=dict(t=20, b=40, l=40, r=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        # 模拟数据
        np.random.seed(42)
        cumulative = np.cumsum(np.random.randn(30) * 0.5)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates,
            y=cumulative,
            mode='lines',
            fill='tozeroy',
            line=dict(color='#007AFF', width=2),
            fillcolor='rgba(0,122,255,0.1)'
        ))
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=300,
            margin=dict(t=20, b=40, l=40, r=20),
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("注：数据积累后将显示真实收益曲线")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 快捷操作
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### ⚡ 快捷操作")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("🔄 刷新净值", use_container_width=True):
            st.cache_data.clear()
            st.success("已刷新")
            time.sleep(0.5)
            st.rerun()
    with c2:
        if st.button("📝 添加日志", use_container_width=True):
            st.session_state.page = "日志"
            st.rerun()
    with c3:
        if st.button("🤖 AI分析", use_container_width=True):
            st.session_state.page = "AI投研"
            st.rerun()
    with c4:
        if st.button("⚠️ 风险检查", use_container_width=True):
            with st.spinner("AI分析中..."):
                holdings_text = "\n".join([f"{h['name']}: {h['market_value']:.0f}元" for h in valid_holdings])
                warning = ai_risk_warning(holdings_text)
            st.markdown(f"""
            <div style="background:rgba(255,59,48,0.08); border-radius:12px; padding:16px; border-left:4px solid #ff3b30">
                <div style="font-weight:600; color:#ff3b30; margin-bottom:8px">⚠️ 风险预警</div>
                <div style="color:#1d1d1f; font-size:14px; line-height:1.6">{warning}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# ==================== 持仓页面 ====================
def page_holdings():
    """持仓管理"""
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 💼 持仓管理")
    
    all_funds = load_all_funds()
    holdings_df = db_get_holdings()
    
    # 添加新持仓
    with st.expander("➕ 添加/修改持仓", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            new_code = st.text_input("基金代码", placeholder="000001", key="new_code")
        with c2:
            new_cost = st.number_input("成本价", min_value=0.0, value=1.0, step=0.001, format="%.4f", key="new_cost")
        with c3:
            new_shares = st.number_input("份额", min_value=0.0, value=100.0, step=10.0, key="new_shares")
        
        # 自动识别名称
        name_preview = ""
        if new_code and not all_funds.empty:
            name, ftype = get_fund_name_type(new_code, all_funds)
            name_preview = f"**{name}** ({ftype})" if name != new_code else ""
        
        if name_preview:
            st.markdown(f"<div style='color:#007AFF; font-size:14px'>识别到：{name_preview}</div>", unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 保存持仓", use_container_width=True, type="primary"):
                if new_code and new_cost > 0 and new_shares > 0:
                    name, _ = get_fund_name_type(new_code, all_funds)
                    db_save_holding(new_code.replace('.OF', ''), name, new_cost, new_shares)
                    st.success(f"已保存：{name}")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("请填写完整信息")
        with c2:
            if st.button("📋 批量导入", use_container_width=True):
                st.session_state.show_batch = True
    
    # 批量导入
    if st.session_state.get('show_batch'):
        st.markdown("---")
        st.markdown("**批量导入格式**：每行 `代码,成本价,份额`")
        batch_text = st.text_area("粘贴持仓", height=100, placeholder="000001,1.5,1000\n270042,2.8,500", key="batch_input")
        if st.button("确认导入", key="confirm_batch"):
            lines = batch_text.strip().split('\n')
            imported = 0
            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 3:
                    try:
                        code, cost, shares = parts[0], float(parts[1]), float(parts[2])
                        name, _ = get_fund_name_type(code, all_funds)
                        db_save_holding(code.replace('.OF', ''), name, cost, shares)
                        imported += 1
                    except:
                        pass
            st.success(f"成功导入 {imported} 条持仓")
            st.session_state.show_batch = False
            time.sleep(1)
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 持仓列表
    if not holdings_df.empty:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("### 📋 当前持仓")
        
        for _, row in holdings_df.iterrows():
            code = row['code']
            name = row['name'] or code
            cost = row['cost']
            shares = row['shares']
            
            nav_data = get_fund_nav(code)
            
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
                
                with c1:
                    if nav_data and nav_data['nav']:
                        nav = nav_data['nav']
                        change = nav_data['change'] or 0
                        market_value = nav * shares
                        profit = (nav - cost) * shares
                        profit_rate = (nav - cost) / cost * 100 if cost > 0 else 0
                        
                        color = "up" if profit >= 0 else "down"
                        st.markdown(f"""
                        <div>
                            <div style="font-weight:600; font-size:16px">{name}</div>
                            <div style="font-size:12px; color:#86868b">{code} · {row['updated_at'][:10]}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div>
                            <div style="font-weight:600; font-size:16px">{name}</div>
                            <div style="font-size:12px; color:#86868b">{code} · 数据获取失败</div>
                        </div>
                        """, unsafe_allow_html=True)
                
                with c2:
                    if nav_data and nav_data['nav']:
                        st.markdown(f"""
                        <div style="text-align:center">
                            <div style="font-size:12px; color:#86868b">净值</div>
                            <div style="font-weight:600">{nav:.4f}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.write("—")
                
                with c3:
                    if nav_data and nav_data['nav']:
                        st.markdown(f"""
                        <div style="text-align:center">
                            <div style="font-size:12px; color:#86868b">市值</div>
                            <div style="font-weight:600">¥{market_value:,.0f}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.write("—")
                
                with c4:
                    if nav_data and nav_data['nav']:
                        st.markdown(f"""
                        <div style="text-align:center">
                            <div style="font-size:12px; color:#86868b">收益</div>
                            <div class="{color}" style="font-weight:600">{profit_rate:+.2f}%</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.write("—")
                
                with c5:
                    if st.button("🗑️", key=f"del_{code}"):
                        db_delete_holding(code)
                        st.success("已删除")
                        time.sleep(0.5)
                        st.rerun()
                
                st.markdown("<div style='height:1px; background:rgba(0,0,0,0.05); margin:12px 0'></div>", unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("暂无持仓，请添加")
# ==================== AI投研页面 ====================
def page_ai_research():
    """AI投研中心"""
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 🤖 AI 投研中心")
    st.caption("基于 DeepSeek 大模型的智能分析")
    st.markdown('</div>', unsafe_allow_html=True)
    
    holdings_df = db_get_holdings()
    all_funds = load_all_funds()
    
    # 获取持仓文本
    holdings_text = ""
    if not holdings_df.empty:
        holdings_list = []
        for _, row in holdings_df.iterrows():
            nav_data = get_fund_nav(row['code'])
            if nav_data and nav_data['nav']:
                market_value = nav_data['nav'] * row['shares']
                holdings_list.append(f"{row['name'] or row['code']}: ¥{market_value:.0f}")
        holdings_text = "\n".join(holdings_list)
    
    # 新闻分析
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("#### 📰 新闻影响分析")
    
    if not st.session_state.news_cache:
        st.session_state.news_cache = fetch_all_news()
    
    if st.session_state.news_cache and st.session_state.news_cache[0] != "（暂无快讯，请点击刷新）":
        selected_news = st.selectbox("选择快讯", st.session_state.news_cache, key="ai_news")
        
        c1, c2 = st.columns([3, 1])
        with c2:
            if st.button("🔍 分析影响", type="primary", use_container_width=True):
                with st.spinner("DeepSeek 分析中..."):
                    analysis = ai_news_impact(selected_news, holdings_text)
                
                st.markdown(f"""
                <div style="background:rgba(0,122,255,0.08); border-radius:16px; padding:20px; margin-top:16px; border-left:4px solid #007AFF">
                    <div style="font-size:13px; font-weight:600; color:#007AFF; margin-bottom:12px">🤖 DeepSeek 分析结果</div>
                    <div style="color:#1d1d1f; font-size:15px; line-height:1.7">{analysis}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.write("暂无快讯数据")
        if st.button("🔄 刷新快讯"):
            st.session_state.news_cache = fetch_all_news()
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 调仓建议
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("#### 💡 智能调仓建议")
    
    if holdings_text:
        market_context = ""
        flow = get_market_flow()
        if flow['北向资金']:
            market_context += f"北向资金净流入{flow['北向资金']:.2f}亿。"
        
        if st.button("🎯 生成调仓建议", type="primary", use_container_width=True):
            with st.spinner("AI 思考中..."):
                advice = ai_portfolio_advice(holdings_text, market_context)
            
            st.markdown(f"""
            <div style="background:rgba(52,199,89,0.08); border-radius:16px; padding:20px; margin-top:16px; border-left:4px solid #34c759">
                <div style="font-size:13px; font-weight:600; color:#34c759; margin-bottom:12px">📋 调仓方案</div>
                <div style="color:#1d1d1f; font-size:15px; line-height:1.7; white-space:pre-line">{advice}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("请先添加持仓，AI才能给出个性化建议")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 风险预警
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("#### ⚠️ 风险扫描")
    
    if holdings_text:
        if st.button("🔍 扫描风险", type="primary", use_container_width=True):
            with st.spinner("AI 扫描中..."):
                warning = ai_risk_warning(holdings_text)
            
            st.markdown(f"""
            <div style="background:rgba(255,59,48,0.08); border-radius:16px; padding:20px; margin-top:16px; border-left:4px solid #ff3b30">
                <div style="font-size:13px; font-weight:600; color:#ff3b30; margin-bottom:12px">⚠️ 风险报告</div>
                <div style="color:#1d1d1f; font-size:15px; line-height:1.7; white-space:pre-line">{warning}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("请先添加持仓")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 每日复盘
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("#### 📝 每日 AI 复盘")
    
    today = datetime.now().strftime("%Y-%m-%d")
    if st.button("📊 生成今日复盘", type="primary", use_container_width=True):
        with st.spinner("AI 生成中..."):
            prompt = f"""今天是{today}，请作为基金经理生成今日投资复盘：

持仓概况：{holdings_text if holdings_text else '暂无持仓'}

请包含：
1. 今日市场总结（3句话）
2. 持仓表现点评
3. 明日关注要点
4. 情绪评分（1-10分）

输出简洁，200字以内。"""
            review = ai_analyze(prompt)
        
        st.markdown(f"""
        <div style="background:rgba(175,82,222,0.08); border-radius:16px; padding:20px; margin-top:16px; border-left:4px solid #af52de">
            <div style="font-size:13px; font-weight:600; color:#af52de; margin-bottom:12px">📊 {today} 复盘</div>
            <div style="color:#1d1d1f; font-size:15px; line-height:1.7; white-space:pre-line">{review}</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# ==================== 市场页面 ====================
def page_market():
    """市场监控"""
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 💰 市场资金流向")
    
    flow = get_market_flow()
    
    # 北向资金
    c1, c2 = st.columns([1, 2])
    with c1:
        north = flow.get("北向资金")
        if north is not None:
            color = "up" if north >= 0 else "down"
            emoji = "📈" if north >= 0 else "📉"
            st.markdown(f"""
            <div style="text-align:center; padding:24px; background:rgba(255,255,255,0.5); border-radius:20px">
                <div class="metric-label">北向资金净流入</div>
                <div class="metric-large {color}" style="margin-top:8px">{emoji} {north:+.2f}亿</div>
                <div style="font-size:12px; color:#86868b; margin-top:8px">实时数据</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="text-align:center; padding:24px; background:rgba(255,255,255,0.5); border-radius:20px">
                <div class="metric-label">北向资金</div>
                <div style="font-size:14px; color:#86868b; margin-top:12px">非交易时间</div>
                <div style="font-size:12px; color:#86868b">工作日 9:30-15:00</div>
            </div>
            """, unsafe_allow_html=True)
    
    with c2:
        # 板块流向可视化
        if flow['板块流入'] or flow['板块流出']:
            sectors_in = [s['名称'] for s in flow['板块流入']]
            values_in = [float(str(s['流入净额']).replace('亿', '')) for s in flow['板块流入']]
            sectors_out = [s['名称'] for s in flow['板块流出']]
            values_out = [-float(str(s['流入净额']).replace('亿', '')) for s in flow['板块流出']]
            
            fig = go.Figure()
            if sectors_in:
                fig.add_trace(go.Bar(
                    y=sectors_in,
                    x=values_in,
                    orientation='h',
                    name='流入',
                    marker_color='#34c759'
                ))
            if sectors_out:
                fig.add_trace(go.Bar(
                    y=sectors_out,
                    x=values_out,
                    orientation='h',
                    name='流出',
                    marker_color='#ff3b30'
                ))
            
            fig.update_layout(
                barmode='relative',
                height=250,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=20, b=20, l=80, r=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=False)
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("板块资金流向数据暂无")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 新闻聚合
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 📰 实时快讯")
    
    if not st.session_state.news_cache:
        st.session_state.news_cache = fetch_all_news()
    
    if st.session_state.news_cache and st.session_state.news_cache[0] != "（暂无快讯，请点击刷新）":
        for i, news in enumerate(st.session_state.news_cache[:10]):
            st.markdown(f"""
            <div style="padding:12px 0; border-bottom:1px solid rgba(0,0,0,0.05)">
                <div style="font-size:14px; color:#1d1d1f; line-height:1.5">{news}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.write("暂无快讯")
        if st.button("🔄 刷新"):
            st.session_state.news_cache = fetch_all_news()
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)

# ==================== 科技雷达页面 ====================
def page_tech_radar():
    """科技基金雷达"""
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 🚀 科技基金雷达")
    st.caption("跟踪 AI、半导体、新能源等核心赛道")
    
    # 预设科技基金池
    tech_funds_pool = {
        "AI/人工智能": [
            ("001938", "中欧时代先锋"),
            ("005911", "广发科技动力"),
            ("007484", "招商科技创新"),
        ],
        "半导体/芯片": [
            ("320007", "诺安成长混合"),
            ("007300", "银河创新成长"),
            ("002560", "诺安和鑫灵活配置"),
        ],
        "新能源": [
            ("003834", "华夏能源革新"),
            ("005939", "工银新能源汽车"),
            ("009068", "嘉实新能源新材料"),
        ],
        "消费电子": [
            ("001410", "信达澳银新能源产业"),
            ("005911", "广发科技动力"),
            ("007484", "招商科技创新"),
        ],
        "云计算": [
            ("001938", "中欧时代先锋"),
            ("005911", "广发科技动力"),
        ]
    }
    
    # 加载用户关注的科技基金
    watch_df = db_get_tech_watch()
    
    # 添加关注
    with st.expander("➕ 添加科技基金关注"):
        c1, c2 = st.columns(2)
        with c1:
            tech_code = st.text_input("基金代码", placeholder="320007", key="tech_code")
        with c2:
            sector = st.selectbox("所属赛道", list(TECH_SECTORS.keys()), key="tech_sector")
        
        if st.button("🔍 添加关注", type="primary"):
            if tech_code:
                all_funds = load_all_funds()
                name, _ = get_fund_name_type(tech_code, all_funds)
                db_add_tech_watch(tech_code.replace('.OF', ''), name, sector)
                st.success(f"已添加：{name}")
                time.sleep(0.5)
                st.rerun()
    
    # 预设赛道快速添加
    st.markdown("#### 📂 预设赛道基金")
    tabs = st.tabs(list(tech_funds_pool.keys()))
    for i, (sector, funds) in enumerate(tech_funds_pool.items()):
        with tabs[i]:
            for code, name in funds:
                c1, c2, c3 = st.columns([2, 2, 1])
                with c1:
                    st.write(f"**{name}**")
                    st.caption(code)
                with c2:
                    nav_data = get_fund_nav(code)
                    if nav_data and nav_data['nav']:
                        change = nav_data['change'] or 0
                        color = "up" if change >= 0 else "down"
                        st.markdown(f"<span class='{color}'>{change:+.2f}%</span>", unsafe_allow_html=True)
                    else:
                        st.write("—")
                with c3:
                    if st.button("➕", key=f"add_{code}_{sector}"):
                        db_add_tech_watch(code, name, sector)
                        st.success("已添加")
                        time.sleep(0.5)
                        st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 我的科技关注
    if not watch_df.empty:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("#### ⭐ 我的科技关注")
        
        for _, row in watch_df.iterrows():
            code = row['code']
            name = row['name'] or code
            sector = row['sector']
            
            nav_data = get_fund_nav(code)
            
            with st.container():
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                
                with c1:
                    st.markdown(f"""
                    <div>
                        <div style="font-weight:600">{name}</div>
                        <div style="font-size:12px; color:#86868b">{code}</div>
                        <span class="tag tag-tech">{sector}</span>
                    </div>
                    """, unsafe_allow_html=True)
                
                with c2:
                    if nav_data and nav_data['nav']:
                        st.write(f"净值: {nav_data['nav']:.4f}")
                    else:
                        st.write("—")
                
                with c3:
                    if nav_data and nav_data['nav']:
                        change = nav_data['change'] or 0
                        color = "up" if change >= 0 else "down"
                        st.markdown(f"<span class='{color}'>{change:+.2f}%</span>", unsafe_allow_html=True)
                    else:
                        st.write("—")
                
                with c4:
                    if st.button("🗑️", key=f"del_tech_{code}"):
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        c.execute("DELETE FROM tech_watch WHERE code=?", (code,))
                        conn.commit()
                        conn.close()
                        st.rerun()
                
                st.markdown("<div style='height:1px; background:rgba(0,0,0,0.05); margin:12px 0'></div>", unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
# ==================== 日志页面 ====================
def page_journal():
    """投资日志"""
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 📝 投资日志")
    st.caption("记录每一次决策，AI 定期复盘")
    
    # 添加新日志
    with st.expander("➕ 记录新交易", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            j_date = st.date_input("日期", datetime.now(), key="j_date")
        with c2:
            j_action = st.selectbox("操作", ["买入", "卖出", "定投", "调仓", "观望"], key="j_action")
        with c3:
            j_code = st.text_input("基金代码", placeholder="000001", key="j_code")
        
        j_reason = st.text_area("决策原因", placeholder="为什么做出这个决策？", key="j_reason")
        
        c1, c2 = st.columns(2)
        with c1:
            j_emotion = st.select_slider("情绪状态", ["恐慌", "焦虑", "平静", "乐观", "狂热"], value="平静", key="j_emotion")
        with c2:
            j_result = st.text_input("结果预判", placeholder="预计收益或风险", key="j_result")
        
        if st.button("💾 保存日志", type="primary", use_container_width=True):
            db_add_journal(
                j_date.strftime("%Y-%m-%d"),
                j_action,
                j_code,
                j_reason,
                j_emotion,
                j_result
            )
            st.success("日志已保存")
            time.sleep(0.5)
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 日志列表
    journals = db_get_journals(limit=50)
    if not journals.empty:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("#### 📚 历史记录")
        
        for _, row in journals.iterrows():
            emotion_color = {
                "恐慌": "tag-warning",
                "焦虑": "tag-warning",
                "平静": "tag-tech",
                "乐观": "tag-success",
                "狂热": "tag-warning"
            }.get(row['emotion'], "tag-tech")
            
            st.markdown(f"""
            <div style="padding:16px; background:rgba(255,255,255,0.5); border-radius:16px; margin:8px 0">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px">
                    <div style="font-weight:600; font-size:15px">{row['date']} · {row['action']}</div>
                    <span class="tag {emotion_color}">{row['emotion']}</span>
                </div>
                <div style="font-size:14px; color:#1d1d1f; margin-bottom:8px; line-height:1.5">{row['reason']}</div>
                <div style="font-size:12px; color:#86868b">代码: {row['code']} · 预判: {row['result']}</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("暂无日志记录")

# ==================== 利润锁定提醒 ====================
def check_profit_alerts():
    """检查利润锁定条件"""
    holdings_df = db_get_holdings()
    alerts = []
    
    for _, row in holdings_df.iterrows():
        code = row['code']
        cost = row['cost']
        nav_data = get_fund_nav(code)
        
        if nav_data and nav_data['nav']:
            nav = nav_data['nav']
            profit_rate = (nav - cost) / cost * 100 if cost > 0 else 0
            
            # 利润锁定提醒阈值
            if profit_rate >= 20:
                alerts.append({
                    'code': code,
                    'name': row['name'] or code,
                    'profit': profit_rate,
                    'level': 'high',
                    'message': f"收益率达 {profit_rate:.1f}%，建议考虑分批止盈"
                })
            elif profit_rate >= 10:
                alerts.append({
                    'code': code,
                    'name': row['name'] or code,
                    'profit': profit_rate,
                    'level': 'medium',
                    'message': f"收益率达 {profit_rate:.1f}%，可关注止盈机会"
                })
            elif profit_rate <= -15:
                alerts.append({
                    'code': code,
                    'name': row['name'] or code,
                    'profit': profit_rate,
                    'level': 'warning',
                    'message': f"亏损达 {abs(profit_rate):.1f}%，建议评估是否止损"
                })
    
    return alerts

# ==================== 主程序入口 ====================
def main():
    """主程序"""
    # 渲染头部导航
    render_header()
    
    # 检查利润锁定提醒
    alerts = check_profit_alerts()
    if alerts:
        st.markdown('<div style="margin-top:16px">', unsafe_allow_html=True)
        for alert in alerts:
            color_map = {
                'high': ('#ff3b30', 'rgba(255,59,48,0.08)'),
                'medium': ('#ff9500', 'rgba(255,149,0,0.08)'),
                'warning': ('#af52de', 'rgba(175,82,222,0.08)')
            }
            color, bg = color_map.get(alert['level'], ('#007AFF', 'rgba(0,122,255,0.08)'))
            
            st.markdown(f"""
            <div style="background:{bg}; border-radius:16px; padding:16px 20px; margin:8px 0; border-left:4px solid {color}; display:flex; align-items:center; justify-content:space-between">
                <div>
                    <div style="font-weight:600; color:{color}; font-size:14px">💡 {alert['name']}</div>
                    <div style="font-size:13px; color:#1d1d1f; margin-top:4px">{alert['message']}</div>
                </div>
                <div style="font-size:24px; font-weight:700; color:{color}">{alert['profit']:+.1f}%</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    # 页面路由
    page = st.session_state.page
    
    if page == "总览":
        page_overview()
    elif page == "持仓":
        page_holdings()
    elif page == "AI投研":
        page_ai_research()
    elif page == "市场":
        page_market()
    elif page == "科技雷达":
        page_tech_radar()
    elif page == "日志":
        page_journal()
    
    # 底部信息
    st.markdown("---")
    st.caption("""
    <div style="text-align:center; color:rgba(255,255,255,0.6); font-size:12px">
        FundOS v2.0 · 数据来源：东方财富、同花顺、财联社 · 仅供学习研究
    </div>
    """, unsafe_allow_html=True)

# 运行主程序
if __name__ == "__main__":
    main()
