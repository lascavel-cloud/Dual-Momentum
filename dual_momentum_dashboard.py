import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go

st.set_page_config(page_title="Dual Momentum Dashboard", layout="wide")
st.title("📈 Dual Momentum Rotation System")
st.caption("VUG • VBK • GLD | 3-month Momentum with Staggered Tranches")

# Sidebar
st.sidebar.header("Settings")
total_portfolio = st.sidebar.number_input("Total Portfolio Value ($)", value=30000.0, step=1000.0)
refresh = st.sidebar.button("🔄 Refresh Data Now")

# ========================== FETCH DATA ==========================
@st.cache_data(ttl=180)  # shorter cache
def fetch_prices():
    tickers = ['VUG', 'VBK', 'GLD', 'SHV']
    data = {}
    end = datetime.now()
    start = end - timedelta(days=500)   # extra buffer
    
    for ticker in tickers:
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True, timeout=10)
            
            if df.empty:
                st.warning(f"No data returned for {ticker}")
                continue
                
            # Handle different column formats
            if isinstance(df.columns, pd.MultiIndex):
                close = df['Close']
            else:
                close = df.get('Close', df.iloc[:, -1])
            
            df_clean = close.reset_index()
            df_clean.columns = ['date', 'close']
            df_clean['date'] = pd.to_datetime(df_clean['date']).dt.date
            data[ticker] = df_clean
            st.success(f"✅ Loaded {ticker} ({len(df_clean)} days)")
        except Exception as e:
            st.error(f"Failed to load {ticker}: {str(e)[:100]}")
    
    return data

data_dict = fetch_prices()

if len(data_dict) < 3:
    st.error("❌ Could not load enough data. Try clicking 'Refresh Data Now' a few times.")
    st.info("Common fixes: Wait 30 seconds and refresh, or try running locally first.")
    st.stop()

# Simple signals (using only 3m ROC for now to reduce complexity)
def get_3m_roc(df):
    if len(df) < 70:
        return None
    try:
        roc = (df['close'].iloc[-1] / df['close'].iloc[-64]) - 1   # ~3 months
        return round(roc * 100, 2)
    except:
        return None

signals = {}
for t, df in data_dict.items():
    roc3 = get_3m_roc(df)
    price = round(float(df['close'].iloc[-1]), 2) if not df.empty else None
    signals[t] = {'price': price, 'roc3': roc3}

# Display
st.subheader("📊 Current Prices & 3-Month ROC")
df_show = pd.DataFrame.from_dict(signals, orient='index')
st.dataframe(df_show, use_container_width=True)

# Basic recommendation (placeholder)
winner = max(signals, key=lambda x: signals[x]['roc3'] or -100)
st.success(f"**Current Leader**: {winner} with {signals[winner]['roc3']}% 3m ROC")

st.info("Note: Full blended momentum + tranche logic coming in next update once data loads reliably.")

with st.sidebar:
    st.caption("If still no data → Try refreshing 2-3 times or run the app locally.")

st.caption("Last updated: " + datetime.now().strftime("%Y-%m-%d %H:%M"))
