import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go

st.set_page_config(page_title="Dual Momentum ETF Dashboard", layout="wide")
st.title("📈 Dual Momentum Rotation System")
st.caption("VUG • VBK • GLD | 3-month Relative + Absolute Momentum with Staggered Rebalancing & Volatility Scaling")

# ========================== CONFIG ==========================
tickers = ['VUG', 'VBK', 'GLD', 'SHV']
blended_weights = {'2m': 0.25, '3m': 0.50, '4m': 0.25}
target_daily_vol = 0.010
days = {'2m': 42, '3m': 63, '4m': 84}

# ========================== DATA FETCH (Robust) ==========================
@st.cache_data(ttl=300)
def fetch_data():
    data = {}
    end = datetime.now()
    start = end - timedelta(days=400)
    
    for t in tickers:
        try:
            df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
            
            # Handle different column formats from yfinance
            if isinstance(df.columns, pd.MultiIndex):
                df = df['Close']
            elif 'Close' in df.columns:
                df = df['Close']
            else:
                df = df.iloc[:, 0]  # fallback to first column
            
            df = df.reset_index()
            df.columns = ['date', 'close']
            df['date'] = pd.to_datetime(df['date']).dt.date
            data[t] = df
        except Exception as e:
            continue  # skip if one ticker fails
    return data

data_dict = fetch_data()

if len(data_dict) == 0:
    st.error("Could not fetch market data. Please refresh again.")
    st.stop()

# ========================== SIGNAL CALCULATION ==========================
def calculate_signals(df):
    def roc(days_back):
        if len(df) < days_back + 10:
            return None
        return (df['close'].iloc[-1] / df['close'].iloc[-days_back-1]) - 1
    
    roc2 = roc(days['2m'])
    roc3 = roc(days['3m'])
    roc4 = roc(days['4m'])
    
    blended = None
    if all(x is not None for x in [roc2, roc3, roc4]):
        blended = blended_weights['2m']*roc2 + blended_weights['3m']*roc3 + blended_weights['4m']*roc4
    
    # 20-day volatility
    vol = None
    if len(df) >= 21:
        returns = df['close'].iloc[-21:].pct_change().dropna()
        vol = returns.std()
    
    return {
        'latest_date': df['date'].iloc[-1],
        'price': round(float(df['close'].iloc[-1]), 2),
        'roc3': round(roc3 * 100, 2) if roc3 is not None else None,
        'blended': round(blended * 100, 2) if blended is not None else None,
        'vol20d': round(vol * 100, 2) if vol is not None else None
    }

signals = {t: calculate_signals(data_dict[t]) for t in data_dict}

# ========================== ALLOCATION LOGIC ==========================
def generate_allocation(signals):
    ranked = sorted(
        [(t, s) for t, s in signals.items() if t != 'SHV'],
        key=lambda x: x[1]['blended'] or -999,
        reverse=True
    )
    
    if not ranked:
        return {'asset': 'SHV', 'alloc': 100.0, 'cash': 0.0, 'reason': 'No data', 'winner': 'SHV'}
    
    winner, win_data = ranked[0]
    roc3 = win_data.get('roc3')
    
    if roc3 is None or roc3 <= 0:
        return {'asset': 'SHV', 'alloc': 100.0, 'cash': 0.0, 'reason': 'No positive momentum → Cash', 'winner': 'SHV'}
    
    vol = win_data.get('vol20d', 2.0) / 100
    scale = min(1.0, target_daily_vol / vol) if vol > 0 else 1.0
    
    return {
        'asset': winner,
        'alloc': round(scale * 100, 1),
        'cash': round((1 - scale) * 100, 1),
        'reason': f'Winner: {winner}',
        'winner': winner,
        'roc3': roc3,
        'blended': win_data.get('blended')
    }

allocation = generate_allocation(signals)

# ========================== UI ==========================
st.subheader("🎯 Live Recommendation")
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    st.metric("Selected Asset", allocation['winner'], f"{allocation.get('roc3', 'N/A')}% 3m ROC")
    st.metric("Blended Momentum", f"{allocation.get('blended', 'N/A')}%")

with col2:
    st.success(f"**{allocation['asset']}**: {allocation['alloc']}%")
    if allocation['cash'] > 0:
        st.info(f"**SHV (Cash)**: {allocation['cash']}%")

with col3:
    week = ((datetime.now().day - 1) // 7) + 1
    st.write(f"**Today is Week {week}**")
    for i in range(1,4):
        st.write(f"Tranche {i}: {'🟢 REBALANCE TODAY' if i == week else '⏳ pending'}")

# Ranking Table
st.subheader("📊 Momentum Ranking")
df_rank = pd.DataFrame.from_dict(signals, orient='index')[['price', 'roc3', 'blended', 'vol20d']]
df_rank.columns = ['Price', '3m ROC (%)', 'Blended ROC (%)', '20d Vol (%)']
df_rank = df_rank.sort_values('Blended ROC (%)', ascending=False)
st.dataframe(df_rank.style.format("{:.2f}"), use_container_width=True)

# Chart
st.subheader("📈 Price History (Last 6 Months)")
fig = go.Figure()
for t in ['VUG', 'VBK', 'GLD']:
    if t in data_dict:
        df_plot = data_dict[t].tail(126)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['close'], name=t))
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

# Sidebar
with st.sidebar:
    st.header("Settings")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

st.success("✅ Dashboard is now running!")
