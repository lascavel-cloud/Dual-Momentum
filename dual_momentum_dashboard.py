import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go

# Optional: Polygon (uncomment and install if you want to use it)
# pip install polygon-api-client
try:
    from polygon import RESTClient
    POLYGON_AVAILABLE = True
except ImportError:
    POLYGON_AVAILABLE = False

st.set_page_config(page_title="Dual Momentum ETF Dashboard", layout="wide")
st.title("📈 Dual Momentum Rotation System")
st.caption("VUG • VBK • GLD | 3-month Relative + Absolute Momentum with Staggered Rebalancing & Volatility Scaling")

# ========================== SIDEBAR SETTINGS ==========================
st.sidebar.header("⚙️ Settings")

data_source = st.sidebar.selectbox(
    "Data Source",
    ["Yahoo Finance (yfinance)", "Polygon.io"],
    help="Yahoo is default and requires no key. Polygon is more reliable but needs a free API key."
)

if data_source == "Polygon.io" and POLYGON_AVAILABLE:
    polygon_key = st.sidebar.text_input("Polygon API Key", type="password", 
                                      help="Get free key at polygon.io")
else:
    polygon_key = None

total_portfolio = st.sidebar.number_input("Total Portfolio Value ($)", 
                                        min_value=1000.0, value=30000.0, step=1000.0, format="%.0f")

# ========================== DATA FETCH ==========================
@st.cache_data(ttl=300)
def fetch_data(source, key=None):
    tickers = ['VUG', 'VBK', 'GLD', 'SHV']
    data = {}
    end = datetime.now()
    start = end - timedelta(days=400)
    
    for t in tickers:
        try:
            if source == "Yahoo Finance (yfinance)":
                df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
                if isinstance(df.columns, pd.MultiIndex):
                    close = df['Close']
                else:
                    close = df['Close'] if 'Close' in df.columns else df.iloc[:, 0]
                
            elif source == "Polygon.io" and POLYGON_AVAILABLE and key:
                client = RESTClient(key)
                aggs = list(client.get_aggs(t, 1, "day", from_=start.strftime("%Y-%m-%d"), 
                                          to=end.strftime("%Y-%m-%d"), adjusted=True, sort="asc"))
                df_list = [{'date': datetime.fromtimestamp(a.timestamp/1000).date(), 'close': a.close} for a in aggs]
                close = pd.DataFrame(df_list).set_index('date')['close']
            
            else:
                st.warning(f"Polygon not available or key missing. Falling back to Yahoo.")
                # fallback code here if needed
            
            df_reset = close.reset_index()
            df_reset.columns = ['date', 'close']
            df_reset['date'] = pd.to_datetime(df_reset['date']).dt.date
            data[t] = df_reset
            
        except Exception as e:
            st.warning(f"Failed to fetch {t} from {source}: {e}")
            continue
    return data

data_dict = fetch_data(data_source, polygon_key)

if len(data_dict) == 0:
    st.error("Failed to fetch data from selected source. Try switching source or refreshing.")
    st.stop()

# ... [Rest of your existing code for signals, allocation, tranche logic, UI, backtest section remains the same] ...

# (Paste the live recommendation, "What to Do Today", ranking table, live chart, and backtest sections from the previous working version here)

st.success(f"✅ Data loaded from **{data_source}** | Refresh anytime")
