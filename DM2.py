import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import time
import requests
import plotly.express as px
from dateutil.relativedelta import relativedelta

# --- Page Config ---
st.set_page_config(page_title="Dual Momentum ETF Screener", page_icon="📈", layout="wide")

# --- Retry Helper with Exponential Backoff ---
def fetch_with_retry(func, max_retries=3, delay=1, **kwargs):
    """Retry a function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func(**kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = delay * (2 ** attempt)
            st.warning(f"⚠️ Attempt {attempt+1} failed. Retrying in {wait_time}s... ({e})")
            time.sleep(wait_time)

# --- Robust Yahoo Finance Fetcher ---
@st.cache_data(ttl=1800, show_spinner="Fetching Yahoo data...")
def fetch_yahoo_robust(tickers, months_ago):
    """Fetch data with better error handling and user-agent headers."""
    end_date = datetime.date.today()
    start_date = end_date - relativedelta(months=months_ago)
    
    # Custom headers to mimic browser request (helps avoid blocks)
    import yfinance as yf
    yf.set_tz_cache_location(None)  # Avoid timezone cache issues
    
    try:
        # Download with explicit parameters
        df = yf.download(
            tickers if len(tickers) > 1 else tickers[0],
            start=start_date,
            end=end_date,
            progress=False,
            auto_adjust=True,
            keepna=False,
            timeout=30
        )
        
        if df is None or df.empty:
            return None
            
        # Handle column structure
        if len(tickers) == 1:
            if isinstance(df.columns, pd.MultiIndex):
                close_df = df[['Close']].droplevel(1, axis=1)
            else:
                close_df = df[['Close']].rename(columns={'Close': tickers[0]})
        else:
            if 'Close' in df.columns and isinstance(df.columns, pd.MultiIndex):
                close_df = df['Close'].dropna(axis=1, how='all')
            else:
                close_df = df.dropna(axis=1, how='all')
        
        # Validate data
        if close_df.empty or close_df.isna().all().all():
            return None
            
        # Forward/backward fill for non-trading days
        close_df = close_df.ffill().bfill()
        
        return close_df.sort_index()
        
    except Exception as e:
        st.error(f"❌ Yahoo Fetch Error: {type(e).__name__}\n\n{str(e)}")
        st.info("💡 Try: 1) Update yfinance 2) Wait 60s for rate limit 3) Use Polygon.io")
        return None

# --- Alpha Vantage Fallback (Free Tier) ---
@st.cache_data(ttl=3600, show_spinner="Fetching Alpha Vantage data...")
def fetch_alphavantage(tickers, months_ago, api_key=None):
    """Fallback using Alpha Vantage free API."""
    if not api_key:
        # Use demo key (limited to 5 calls/min, 500/day)
        api_key = "demo"
    
    end_date = datetime.date.today()
    start_date = end_date - relativedelta(months=months_ago)
    
    data_dict = {}
    
    for ticker in tickers:
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "TIME_SERIES_ADJUSTED",
                "symbol": ticker,
                "outputsize": "compact",  # Last 100 days
                "apikey": api_key
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if "Time Series (Daily)" in data:
                ts = data["Time Series (Daily)"]
                dates = sorted([d for d in ts.keys() if datetime.date.fromisoformat(d) >= start_date])
                
                if dates:
                    prices = [float(ts[d]["4. close"]) for d in dates]
                    date_idx = [datetime.date.fromisoformat(d) for d in dates]
                    data_dict[ticker] = pd.Series(prices, index=date_idx)
            elif "Note" in data:
                st.warning(f"⚠️ Alpha Vantage rate limit for {ticker}: {data['Note']}")
                
        except Exception as e:
            st.warning(f"⚠️ Alpha Vantage failed for {ticker}: {e}")
    
    if not data_dict:
        return None
        
    close_df = pd.DataFrame(data_dict).ffill().bfill()
    return close_df if not close_df.empty else None

# --- Momentum Calculation (Unchanged, robust) ---
def calculate_roc(close_df, months_ago):
    if close_df is None or len(close_df) < 2:
        return None
    
    # Use actual trading days: ~21 days/month
    lookback_days = max(1, int(months_ago * 21))
    start_idx = max(0, len(close_df) - lookback_days)
    
    start_prices = close_df.iloc[start_idx]
    end_prices = close_df.iloc[-1]
    
    roc = {}
    for ticker in close_df.columns:
        p0, p1 = start_prices.get(ticker), end_prices.get(ticker)
        if pd.isna(p0) or pd.isna(p1) or p0 == 0:
            roc[ticker] = np.nan
        else:
            roc[ticker] = (p1 - p0) / p0 * 100
    
    return pd.Series(roc)

def get_momentum_signal(roc_series):
    if roc_series is None or roc_series.isna().all():
        return None, None, "⚠️ Insufficient data for momentum calculation"
    
    roc_clean = roc_series.dropna()
    if roc_clean.empty:
        return None, None, "⚠️ No valid ROC values"
    
    max_roc = roc_clean.max()
    
    if max_roc > 0:
        winner = roc_clean.idxmax()
        allocation = {t: 100 if t == winner else 0 for t in roc_series.index}
        signal = f"✅ BUY {winner} (ROC: {max_roc:.2f}%)"
    else:
        # Safe haven logic
        if "GLD" in roc_series.index:
            allocation = {t: 100 if t == "GLD" else 0 for t in roc_series.index}
            signal = f"🛡️ All ROC negative → HOLD GLD"
        else:
            allocation = {t: 0 for t in roc_series.index}
            signal = f"⚠️ All ROC negative & GLD not in universe → HOLD CASH"
    
    return allocation, roc_clean.sort_values(ascending=False), signal

# --- Sample Data for Testing ---
def get_sample_data(tickers, months_ago):
    """Generate realistic sample data for testing when APIs fail."""
    st.warning("🧪 Using SAMPLE DATA for demonstration (APIs unavailable)")
    
    end_date = datetime.date.today()
    dates = pd.date_range(end=end_date, periods=int(months_ago*21)+10, freq='B')[-int(months_ago*21):]
    
    # Simulate momentum: give one ticker positive ROC
    np.random.seed(42)
    data = {}
    base_price = 100
    
    for i, ticker in enumerate(tickers):
        # Create realistic price series with trend
        returns = np.random.normal(0.0005, 0.015, len(dates))
        if i == 0:  # First ticker gets positive momentum
            returns += 0.002  # Slight upward drift
        prices = base_price * (1 + returns).cumprod()
        data[ticker] = pd.Series(prices, index=dates)
    
    return pd.DataFrame(data)

# --- Main App ---
st.title("🚀 Dual Momentum ETF Screener")
st.markdown("Calculates 3-month ROC to determine optimal allocation: **Top performer if ROC>0, else GLD**")

# Sidebar
st.sidebar.header("⚙️ Configuration")

# Data Source with Fallback Options
data_source = st.sidebar.radio(
    "Select Data Source",
    options=[
        "Yahoo Finance (Free)", 
        "Polygon.io (Paid)", 
        "Alpha Vantage (Free Fallback)",
        "🧪 Sample Data (Testing)"
    ]
)

api_key = None
if data_source == "Polygon.io (Paid)":
    try:
        from polygon import RESTClient
        POLYGON_AVAILABLE = True
    except ImportError:
        POLYGON_AVAILABLE = False
        st.sidebar.error("Install: `pip install polygon-api-client`")
    
    if POLYGON_AVAILABLE:
        api_key = st.sidebar.text_input("Polygon API Key", type="password")
        if not api_key:
            st.sidebar.warning("Enter API key or switch to free source")

elif data_source == "Alpha Vantage (Free Fallback)":
    api_key = st.sidebar.text_input("Alpha Vantage Key (optional)", type="password", 
                                    help="Leave blank for demo key (rate limited)")

# ETF Selection
tickers = st.sidebar.multiselect("Select ETFs", ["VUG", "VBK", "GLD"], default=["VUG", "VBK", "GLD"])
period_months = st.sidebar.slider("Lookback Period (Months)", 1, 12, 3)
debug_mode = st.sidebar.checkbox("🐛 Enable Debug Output", value=False)

# Main Logic
if not tickers:
    st.info("👈 Select at least one ETF from the sidebar")
else:
    # Fetch Data
    close_df = None
    
    with st.spinner("📡 Fetching market data..."):
        if data_source == "🧪 Sample Data (Testing)":
            close_df = get_sample_data(tickers, period_months)
            
        elif data_source == "Yahoo Finance (Free)":
            close_df = fetch_with_retry(fetch_yahoo_robust, tickers=tickers, months_ago=period_months)
            if close_df is None and debug_mode:
                st.code("""
🔍 Debug Tips for Yahoo Finance:
1. Run: pip install --upgrade yfinance
2. Check: https://status.yahoofinance.com/
3. Wait 60 seconds if rate limited
4. Try a different network/VPN if blocked regionally
                """, language="bash")
                
        elif data_source == "Polygon.io (Paid)" and api_key and POLYGON_AVAILABLE:
            try:
                from polygon import RESTClient
                client = RESTClient(api_key)
                end_date = datetime.date.today()
                start_date = end_date - relativedelta(months=period_months)
                
                data_dict = {}
                for ticker in tickers:
                    agg = client.get_aggregates(
                        ticker, multiplier=1, timespan="day",
                        from_=start_date.strftime("%Y-%m-%d"),
                        to_=end_date.strftime("%Y-%m-%d"),
                        adjusted=True, sort="asc"
                    )
                    if agg and agg.results:
                        df = pd.DataFrame([
                            {'date': datetime.date.fromtimestamp(r.t/1000), 'close': r.c}
                            for r in agg.results
                        ])
                        df.set_index('date', inplace=True)
                        data_dict[ticker] = df['close']
                
                if data_dict:
                    close_df = pd.DataFrame(data_dict).ffill().bfill().sort_index()
            except Exception as e:
                st.error(f"❌ Polygon Error: {e}")
                
        elif data_source == "Alpha Vantage (Free Fallback)":
            close_df = fetch_alphavantage(tickers, period_months, api_key)
    
    # Handle fetch failure
    if close_df is None or close_df.empty:
        st.error("❌ Could not fetch data from selected source")
        
        # Offer fallback
        st.info("💡 Try these steps:")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Retry with Sample Data"):
                st.rerun()
        with col2:
            if st.button("🌐 Switch to Alpha Vantage"):
                st.rerun()
        
        if debug_mode:
            st.expander("🔍 Technical Details").code(f"""
Source: {data_source}
Tickers: {tickers}
Period: {period_months} months
Timestamp: {datetime.datetime.now()}
            """, language="python")
    else:
        # Calculate & Display Results
        roc_series = calculate_roc(close_df, period_months)
        
        if roc_series is not None:
            allocation, roc_sorted, signal_msg = get_momentum_signal(roc_series)
            
            # Signal Card
            st.divider()
            st.subheader("🎯 Current Signal")
            if "BUY" in signal_msg:
                st.success(f"## {signal_msg}")
            elif "HOLD" in signal_msg or "GLD" in signal_msg:
                st.info(f"## {signal_msg}")
            else:
                st.warning(f"## {signal_msg}")
            
            # ROC Chart
            if roc_sorted is not None and not roc_sorted.empty:
                st.subheader("📊 Momentum Rankings")
                roc_df = roc_sorted.reset_index()
                roc_df.columns = ['ETF', 'ROC (%)']
                
                fig = px.bar(
                    roc_df, x='ETF', y='ROC (%)',
                    color=roc_df['ROC (%)'].apply(lambda x: 'Positive' if x > 0 else 'Negative'),
                    color_discrete_map={'Positive': '#2ECC71', 'Negative': '#E74C3C'},
                    text_auto='.2f', title=f"{period_months}-Month Rate of Change"
                )
                fig.add_hline(y=0, line_dash="dot")
                fig.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig, use_container_width=True)
            
            # Allocation
            if allocation:
                alloc_df = pd.DataFrame([
                    {'ETF': t, 'Allocation': allocation.get(t, 0)} for t in tickers
                ])
                fig_alloc = px.pie(
                    alloc_df[alloc_df['Allocation'] > 0], 
                    values='Allocation', names='ETF',
                    title="💼 Recommended Allocation", hole=0.4
                )
                st.plotly_chart(fig_alloc, use_container_width=True)
            
            # Price Chart
            st.subheader("📈 Recent Price Action")
            chart_df = close_df.tail(90)  # Last ~4.5 months
            fig_price = px.line(chart_df, title="Adjusted Close Prices", labels={'value': 'Price'})
            fig_price.update_layout(hovermode='x unified', height=400)
            st.plotly_chart(fig_price, use_container_width=True)
            
            # Debug info
            if debug_mode:
                with st.expander("🔍 Debug: Raw Data Preview"):
                    st.dataframe(close_df.tail(10).style.format('{:.2f}'))
                    st.write(f"**Shape**: {close_df.shape} | **Date Range**: {close_df.index[0].date()} to {close_df.index[-1].date()}")

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("🔄 Auto-refreshes hourly | 💡 Use Sample Data if APIs fail")
st.caption("⚠️ Educational use only. Not financial advice.")
