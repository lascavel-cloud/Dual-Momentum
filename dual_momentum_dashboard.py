import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go

st.set_page_config(page_title="Dual Momentum ETF Dashboard", layout="wide")
st.title("📈 Dual Momentum Rotation System")
st.caption("VUG • VBK • GLD | 3-month Relative + Absolute Momentum with Staggered Rebalancing & Volatility Scaling")

# ========================== SETTINGS ==========================
st.sidebar.header("⚙️ Settings")

data_source = st.sidebar.selectbox(
    "Data Source",
    ["Yahoo Finance (Recommended)", "Polygon.io (Optional)"],
    index=0
)

polygon_key = None
if data_source == "Polygon.io (Optional)":
    polygon_key = st.sidebar.text_input("Polygon API Key (free at polygon.io)", type="password")

total_portfolio = st.sidebar.number_input("Total Portfolio Value ($)", 
                                        min_value=1000.0, value=30000.0, step=1000.0, format="%.0f")

# ========================== DATA FETCH (Robust with fallback) ==========================
@st.cache_data(ttl=300)
def fetch_data(source: str, api_key: str = None):
    tickers = ['VUG', 'VBK', 'GLD', 'SHV']
    data = {}
    end = datetime.now().date()
    start = (datetime.now() - timedelta(days=400)).date()
    
    for t in tickers:
        df = None
        try:
            if source.startswith("Yahoo"):
                raw = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
                if isinstance(raw.columns, pd.MultiIndex):
                    close_series = raw['Close']
                else:
                    close_series = raw['Close'] if 'Close' in raw.columns else raw.iloc[:, 0]
                df = close_series.reset_index()
                df.columns = ['date', 'close']
            
            elif source.startswith("Polygon") and api_key:
                try:
                    from polygon import RESTClient
                    client = RESTClient(api_key)
                    aggs = list(client.get_aggs(
                        ticker=t,
                        multiplier=1,
                        timespan="day",
                        from_=start.strftime("%Y-%m-%d"),
                        to=end.strftime("%Y-%m-%d"),
                        adjusted=True,
                        sort="asc",
                        limit=50000
                    ))
                    if aggs:
                        df_list = [{'date': datetime.fromtimestamp(a.timestamp/1000).date(), 'close': a.close} for a in aggs]
                        df = pd.DataFrame(df_list)
                except Exception as e_poly:
                    st.warning(f"Polygon error for {t}: {str(e_poly)[:100]}... Falling back to Yahoo.")
                    # fallback to yfinance for this ticker
                    raw = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
                    close_series = raw['Close'] if not isinstance(raw.columns, pd.MultiIndex) else raw['Close']
                    df = close_series.reset_index()
                    df.columns = ['date', 'close']
            
            if df is not None and not df.empty:
                df['date'] = pd.to_datetime(df['date']).dt.date
                data[t] = df
            else:
                st.warning(f"No data returned for {t}")
        except Exception as e:
            st.warning(f"Error fetching {t} from {source}: {str(e)[:80]}")
            continue
    
    return data

data_dict = fetch_data(data_source, polygon_key)

if len(data_dict) < 3:   # at least 3 tickers needed
    st.error("⚠️ Failed to load sufficient market data. Please try switching the Data Source or refresh.")
    st.info("Tip: Yahoo Finance usually works best without any API key.")
    st.stop()

# ========================== SIGNAL CALCULATION ==========================
blended_weights = {'2m': 0.25, '3m': 0.50, '4m': 0.25}
target_daily_vol = 0.010
days_dict = {'2m': 42, '3m': 63, '4m': 84}

def calculate_signals(df):
    def roc(days_back):
        if len(df) < days_back + 10:
            return None
        return (df['close'].iloc[-1] / df['close'].iloc[-days_back-1]) - 1
    
    r2 = roc(days_dict['2m'])
    r3 = roc(days_dict['3m'])
    r4 = roc(days_dict['4m'])
    blended = (blended_weights['2m']*r2 + blended_weights['3m']*r3 + blended_weights['4m']*r4) if None not in (r2, r3, r4) else r3
    vol = df['close'].iloc[-21:].pct_change().dropna().std() if len(df) >= 21 else None
    
    return {
        'latest_date': df['date'].iloc[-1],
        'price': round(float(df['close'].iloc[-1]), 2),
        'roc3': round(r3 * 100, 2) if r3 is not None else None,
        'blended': round(blended * 100, 2) if blended is not None else None,
        'vol20d': round(vol * 100, 2) if vol is not None else None
    }

signals = {t: calculate_signals(data_dict[t]) for t in data_dict}

# ========================== ALLOCATION & TRANCHE (same as before) ==========================
def generate_allocation(signals):
    ranked = sorted([(t, s) for t, s in signals.items() if t != 'SHV'], 
                    key=lambda x: x[1]['blended'] or -999, reverse=True)
    if not ranked:
        return {'asset': 'SHV', 'alloc': 100.0, 'cash': 0.0, 'winner': 'SHV'}
    winner, win_data = ranked[0]
    roc3 = win_data.get('roc3')
    if roc3 is None or roc3 <= 0:
        return {'asset': 'SHV', 'alloc': 100.0, 'cash': 0.0, 'winner': 'SHV'}
    vol = win_data.get('vol20d', 2.0) / 100
    scale = min(1.0, target_daily_vol / vol) if vol > 0 else 1.0
    return {'asset': winner, 'alloc': round(scale*100, 1), 'cash': round((1-scale)*100, 1), 'winner': winner, 'roc3': roc3, 'blended': win_data.get('blended')}

allocation = generate_allocation(signals)

today = datetime.now()
week_of_month = ((today.day - 1) // 7) + 1
tranche_size = total_portfolio / 3

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
    st.write(f"**Today is Week {week_of_month}**")
    for i in range(1,4):
        if i == week_of_month:
            st.success(f"**Tranche {i}**: 🟢 REBALANCE TODAY")
        else:
            st.write(f"Tranche {i}: ⏳ pending")

st.subheader("✅ What You Should Do Today")
due_pct = allocation['alloc'] / 100
st.success(f"**Rebalance Tranche {week_of_month} (~${tranche_size:,.0f})**")
col_a, col_b = st.columns(2)
with col_a:
    st.metric(f"Buy {allocation['winner']}", f"${tranche_size * due_pct:,.0f}")
with col_b:
    st.metric("Move to SHV", f"${tranche_size * (1-due_pct):,.0f}")

# Ranking Table + Charts + Backtest section (copy from previous working version if needed)

st.success(f"✅ Data loaded successfully from **{data_source}**")

with st.sidebar:
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
