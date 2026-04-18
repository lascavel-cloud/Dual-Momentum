import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import plotly.express as px
from dateutil.relativedelta import relativedelta

# Import Polygon.io Client
try:
    from polygon import RESTClient
    POLYGON_AVAILABLE = True
except ImportError:
    POLYGON_AVAILABLE = False

# --- Page Configuration ---
st.set_page_config(
    page_title="Dual Momentum ETF Screener",
    page_icon="📈",
    layout="wide"
)

st.title("🚀 Dual Momentum Strategy: VUG, VBK, GLD")
st.markdown("""
This app implements a **dual momentum strategy**:
1. Calculate 3-month Rate of Change (ROC) for each ETF
2. **If highest ROC > 0**: Allocate 100% to the top performer
3. **If all ROC < 0**: Allocate 100% to GLD (safe haven)
""")

# --- Sidebar: Configuration ---
st.sidebar.header("⚙️ Configuration")

# Data Source Selection
data_source = st.sidebar.radio(
    "Select Data Source",
    options=["Yahoo Finance (Free)", "Polygon.io (Paid)"]
)

# API Key Input
api_key = None
if data_source == "Polygon.io (Paid)":
    if not POLYGON_AVAILABLE:
        st.error("🔧 Please install: `pip install polygon-api-client`")
        st.stop()
    
    api_key = st.sidebar.text_input(
        "Polygon.io API Key",
        type="password",
        help="Get your key at https://polygon.io"
    )
    
    if not api_key:
        st.warning("⚠️ Enter your API key to use Polygon.io")
        st.stop()

# ETF Selection & Parameters
tickers = st.sidebar.multiselect(
    "Select ETFs",
    ["VUG", "VBK", "GLD"],
    default=["VUG", "VBK", "GLD"]
)
period_months = st.sidebar.slider("📅 Lookback Period (Months)", 1, 12, 3)
show_backtest = st.sidebar.checkbox("📊 Show Backtest Summary", value=True)

# --- Helper Functions (Cached for Performance) ---

@st.cache_data(ttl=3600, show_spinner="Fetching Yahoo data...")
def fetch_yahoo_data(tickers, months_ago):
    """Fetch adjusted close prices from Yahoo Finance."""
    end_date = datetime.date.today()
    start_date = end_date - relativedelta(months=months_ago)
    
    try:
        df = yf.download(tickers, start=start_date, end=end_date, progress=False, auto_adjust=True)
        if df.empty or 'Close' not in df.columns:
            return None
            
        # Handle single ticker case
        if len(tickers) == 1:
            close_df = df[['Close']].rename(columns={'Close': tickers[0]})
        else:
            close_df = df['Close'].dropna(axis=1, how='all')
        
        # Ensure all requested tickers are present
        missing = [t for t in tickers if t not in close_df.columns]
        if missing:
            st.warning(f"⚠️ Data missing for: {', '.join(missing)}")
            return None
            
        return close_df.sort_index()
    except Exception as e:
        st.error(f"❌ Yahoo Finance Error: {e}")
        return None

@st.cache_data(ttl=3600, show_spinner="Fetching Polygon data...")
def fetch_polygon_data(tickers, months_ago, api_key):
    """Fetch adjusted close prices from Polygon.io."""
    if not POLYGON_AVAILABLE or not api_key:
        return None
        
    client = RESTClient(api_key)
    end_date = datetime.date.today()
    start_date = end_date - relativedelta(months=months_ago)
    
    data_dict = {}
    
    for ticker in tickers:
        try:
            agg = client.get_aggregates(
                ticker, multiplier=1, timespan="day",
                from_=start_date.strftime("%Y-%m-%d"),
                to_=end_date.strftime("%Y-%m-%d"),
                adjusted=True, sort="asc"
            )
            if agg and agg.results:
                # Create DataFrame from results
                df = pd.DataFrame([
                    {'date': datetime.date.fromtimestamp(r.t/1000), 'close': r.c}
                    for r in agg.results
                ])
                df.set_index('date', inplace=True)
                data_dict[ticker] = df['close']
        except Exception as e:
            st.error(f"❌ Polygon error for {ticker}: {e}")
    
    if not data_dict:
        return None
        
    # Combine into single DataFrame
    close_df = pd.DataFrame(data_dict).dropna(how='all')
    
    # Forward fill then backward fill to handle non-trading days
    close_df = close_df.ffill().bfill()
    
    return close_df.sort_index()

def calculate_roc(close_df, months_ago):
    """Calculate Rate of Change for each ticker."""
    if close_df is None or len(close_df) < 2:
        return None
    
    # Get start and end prices
    start_idx = max(0, len(close_df) - int(months_ago * 21))  # ~21 trading days/month
    start_prices = close_df.iloc[start_idx]
    end_prices = close_df.iloc[-1]
    
    roc = {}
    for ticker in close_df.columns:
        p0 = start_prices[ticker]
        p1 = end_prices[ticker]
        if pd.isna(p0) or pd.isna(p1) or p0 == 0:
            roc[ticker] = np.nan
        else:
            roc[ticker] = (p1 - p0) / p0 * 100  # Return as percentage
    
    return pd.Series(roc)

def get_momentum_signal(roc_series):
    """
    Dual Momentum Allocation Logic:
    - If max ROC > 0: 100% to top performer
    - If all ROC < 0: 100% to GLD (safe haven)
    """
    if roc_series.isna().all():
        return None, None, "⚠️ Insufficient data"
    
    # Clean NaN values
    roc_clean = roc_series.dropna()
    if roc_clean.empty:
        return None, None, "⚠️ No valid ROC values"
    
    max_roc = roc_clean.max()
    
    if max_roc > 0:
        winner = roc_clean.idxmax()
        allocation = {t: 100 if t == winner else 0 for t in roc_series.index}
        signal = f"✅ BUY {winner} (ROC: {max_roc:.2f}%)"
    else:
        # All negative → safe haven
        allocation = {t: 100 if t == "GLD" else 0 for t in roc_series.index}
        signal = f"🛡️ ALL NEGATIVE → HOLD GLD"
        if "GLD" not in allocation:
            allocation = {t: 0 for t in allocation}  # No position if GLD not in universe
    
    return allocation, roc_clean.sort_values(ascending=False), signal

# --- Backtesting Function (Simple Monthly Rebalance) ---

@st.cache_data(ttl=7200)
def run_backtest(tickers, months_lookback, start_year=2020):
    """Simple backtest: monthly rebalance based on momentum signal."""
    end_date = datetime.date.today()
    start_date = datetime.date(start_year, 1, 1)
    
    # Fetch full historical data
    df = yf.download(tickers, start=start_date, end=end_date, progress=False, auto_adjust=True)
    if df.empty or 'Close' not in df.columns:
        return None
    
    close_df = df['Close'].dropna(axis=1, how='all')
    if len(tickers) > 1 and close_df.columns.nlevels > 1:
        close_df = close_df.droplevel(1, axis=1)
    
    # Monthly signals
    signals = []
    portfolio_returns = []
    benchmark_returns = {t: [] for t in tickers}
    
    # Generate monthly rebalance dates
    current = start_date + relativedelta(months=months_lookback)
    while current <= end_date:
        # Get lookback window
        lookback_start = current - relativedelta(months=months_lookback)
        window = close_df.loc[lookback_start:current]
        
        if len(window) < 10:  # Need minimum data
            current += relativedelta(months=1)
            continue
        
        # Calculate ROC
        start_prices = window.iloc[0]
        end_prices = window.iloc[-1]
        roc = {}
        for t in tickers:
            if t in start_prices and t in end_prices and start_prices[t] > 0:
                roc[t] = (end_prices[t] - start_prices[t]) / start_prices[t]
            else:
                roc[t] = np.nan
        roc_series = pd.Series(roc)
        
        # Get signal
        allocation, _, _ = get_momentum_signal(roc_series)
        if allocation is None:
            current += relativedelta(months=1)
            continue
        
        # Calculate next month return
        next_month = current + relativedelta(months=1)
        if next_month not in close_df.index:
            break
            
        month_ret = 0
        for t in tickers:
            weight = allocation.get(t, 0) / 100
            if t in close_df.columns and current in close_df.index and next_month in close_df.index:
                ret = (close_df.loc[next_month, t] - close_df.loc[current, t]) / close_df.loc[current, t]
                month_ret += weight * ret
                benchmark_returns[t].append(ret)
        
        signals.append({
            'date': current,
            'allocation': allocation,
            'roc': {t: roc_series.get(t, np.nan) for t in tickers}
        })
        portfolio_returns.append(month_ret)
        current = next_month
    
    if not portfolio_returns:
        return None
    
    # Calculate cumulative returns
    cum_portfolio = (1 + pd.Series(portfolio_returns)).cumprod() - 1
    cum_benchmarks = {}
    for t in tickers:
        if benchmark_returns[t]:
            cum_benchmarks[t] = (1 + pd.Series(benchmark_returns[t])).cumprod() - 1
    
    return {
        'signals': signals,
        'portfolio_returns': cum_portfolio,
        'benchmark_returns': cum_benchmarks,
        'total_return': cum_portfolio.iloc[-1] if len(cum_portfolio) > 0 else 0
    }

# --- Main Execution ---

if not tickers:
    st.info("👈 Please select at least one ETF from the sidebar.")
else:
    # Fetch Data
    with st.spinner("📡 Fetching market data..."):
        if data_source == "Yahoo Finance (Free)":
            close_df = fetch_yahoo_data(tickers, period_months)
        else:
            close_df = fetch_polygon_data(tickers, period_months, api_key)
    
    if close_df is None or close_df.empty:
        st.error("❌ Could not fetch data. Please check your settings and try again.")
    else:
        # Calculate Momentum
        roc_series = calculate_roc(close_df, period_months)
        
        if roc_series is None:
            st.error("❌ Could not calculate momentum. Insufficient data.")
        else:
            # Get Signal & Allocation
            allocation, roc_sorted, signal_msg = get_momentum_signal(roc_series)
            
            # === DISPLAY RESULTS ===
            st.divider()
            
            # Current Signal Card
            st.subheader("🎯 Current Signal")
            if signal_msg:
                st.success(signal_msg) if "BUY" in signal_msg or "HOLD" in signal_msg else st.warning(signal_msg)
            
            if allocation:
                # Allocation Bar Chart
                alloc_df = pd.DataFrame([
                    {'ETF': t, 'Allocation (%)': allocation.get(t, 0)} 
                    for t in tickers
                ])
                fig_alloc = px.bar(
                    alloc_df, x='ETF', y='Allocation (%)', 
                    color='Allocation (%)', color_continuous_scale='RdYlGn',
                    title="💼 Recommended Allocation", text_auto='.0f'
                )
                fig_alloc.update_layout(showlegend=False, height=300)
                st.plotly_chart(fig_alloc, use_container_width=True)
            
            # ROC Comparison Chart
            st.subheader("📊 Momentum Rankings (ROC %)")
            if roc_sorted is not None and not roc_sorted.empty:
                roc_df = roc_sorted.reset_index()
                roc_df.columns = ['ETF', 'ROC (%)']
                roc_df['Color'] = roc_df['ROC (%)'].apply(lambda x: 'positive' if x > 0 else 'negative')
                
                fig_roc = px.bar(
                    roc_df, x='ETF', y='ROC (%)', color='Color',
                    color_discrete_map={'positive': '#2ECC71', 'negative': '#E74C3C'},
                    title=f"{period_months}-Month Rate of Change", text_auto='.2f'
                )
                fig_roc.add_hline(y=0, line_dash="dot", line_color="gray")
                fig_roc.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig_roc, use_container_width=True)
                
                # Data Table
                with st.expander("📋 View Raw ROC Data"):
                    st.dataframe(roc_df.style.format({'ROC (%)': '{:.2f}%'}), hide_index=True)
            
            # Price Chart
            st.subheader("📈 Price History")
            price_chart = px.line(
                close_df.tail(120),  # Last ~6 months
                title="Adjusted Close Prices",
                labels={'value': 'Price', 'variable': 'ETF'}
            )
            price_chart.update_layout(hovermode='x unified', height=400)
            st.plotly_chart(price_chart, use_container_width=True)
            
            # === BACKTESTING SECTION ===
            if show_backtest and len(tickers) >= 2:
                st.divider()
                st.subheader("🔙 Strategy Backtest (Monthly Rebalance)")
                st.caption(f"Period: {period_months}-month ROC | Universe: {', '.join(tickers)}")
                
                with st.spinner("Running backtest..."):
                    bt_results = run_backtest(tickers, period_months)
                
                if bt_results and bt_results['portfolio_returns'] is not None:
                    # Performance Metrics
                    col1, col2, col3 = st.columns(3)
                    strat_ret = bt_results['total_return'] * 100
                    col1.metric("Strategy Return", f"{strat_ret:.1f}%")
                    
                    # Simple benchmark comparison (equal weight)
                    bench_ret = np.mean([bt_results['benchmark_returns'][t].iloc[-1] * 100 
                                       for t in tickers if t in bt_results['benchmark_returns'] 
                                       and len(bt_results['benchmark_returns'][t]) > 0])
                    col2.metric("Avg Benchmark Return", f"{bench_ret:.1f}%")
                    col3.metric("Excess Return", f"{strat_ret - bench_ret:.1f}%")
                    
                    # Cumulative Returns Chart
                    bt_df = pd.DataFrame({'Strategy': bt_results['portfolio_returns']})
                    for t in tickers:
                        if t in bt_results['benchmark_returns']:
                            bt_df[t] = bt_results['benchmark_returns'][t]
                    
                    fig_bt = px.line(
                        bt_df * 100, 
                        title="Cumulative Returns (%)",
                        labels={'value': 'Return (%)', 'variable': 'Asset'}
                    )
                    fig_bt.update_layout(hovermode='x unified', height=400)
                    st.plotly_chart(fig_bt, use_container_width=True)
                    
                    # Recent Signals Table
                    with st.expander("📅 Recent Allocation History"):
                        recent_signals = bt_results['signals'][-10:]
                        sig_df = pd.DataFrame([
                            {
                                'Date': s['date'],
                                'Signal': 'BUY ' + max(s['allocation'], key=s['allocation'].get) if max(s['allocation'].values()) > 0 else 'HOLD CASH/GLD',
                                **{f"{t} %": s['allocation'].get(t, 0) for t in tickers}
                            }
                            for s in recent_signals
                        ])
                        st.dataframe(sig_df, hide_index=True, use_container_width=True)
                else:
                    st.info("ℹ️ Backtest requires sufficient historical data. Try extending the date range.")
            
            # Footer
            st.divider()
            st.caption("""
            ⚠️ **Disclaimer**: This tool is for educational purposes only. 
            Past performance ≠ future results. Always do your own research before investing.
            """)

# --- Sidebar Footer ---
st.sidebar.markdown("---")
st.sidebar.caption("🔄 Data refreshes hourly | Built with Streamlit + yfinance")
