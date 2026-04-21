import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# Page config
st.set_page_config(page_title="Options Strategy Payoffs", layout="wide")

# Custom UI CSS
st.markdown("""
<style>
[data-testid="stMetric"] {
    background-color: var(--secondary-background-color);
    border: 1px solid rgba(128, 128, 128, 0.2);
    padding: 15px;
    border-radius: 10px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
/* Fix for number input buttons getting stuck on red */
div[data-baseweb="input"] button:focus:not(:active),
button[data-testid="stNumberInputStepUp"]:focus:not(:active),
button[data-testid="stNumberInputStepDown"]:focus:not(:active) {
    background-color: transparent !important;
    color: inherit !important;
}
</style>
""", unsafe_allow_html=True)

# Title
st.title("Financial Derivatives: Option Spread Strategies")
st.markdown("Visualize **Bull Call** and **Bear Put** Spreads using real market data.")

# Sidebar inputs
st.sidebar.header("Strategy Settings")
ticker_symbol = st.sidebar.text_input(
    "Stock Ticker", 
    value="AAPL",
    help="Enter any Yahoo Finance ticker symbol. Examples: AAPL, TSLA, MSFT, SPY, NVDA, GOOGL. It supports almost every publicly traded stock globally!"
)

@st.cache_data(ttl=300)
def fetch_ticker_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="6mo")
        if history.empty:
            return None, None, None
        current_price = history['Close'].iloc[-1]
        expirations = ticker.options
        return history, current_price, expirations
    except Exception as e:
        return None, None, None

history, current_price, expirations = fetch_ticker_data(ticker_symbol)

if current_price is None or not expirations:
    st.error(f"Could not fetch data for ticker: {ticker_symbol}. Please check the symbol and ensure it has options available.")
    st.stop()

# Base Candlestick Chart
fig_candle = go.Figure(data=[go.Candlestick(x=history.index,
                open=history['Open'],
                high=history['High'],
                low=history['Low'],
                close=history['Close'],
                increasing_line_color='#2ecc71', decreasing_line_color='#e74c3c')])
fig_candle.update_layout(xaxis_rangeslider_visible=False, height=350, margin=dict(l=0, r=0, t=30, b=0))

st.sidebar.markdown(f"**Current Price:** ${current_price:.2f}")

selected_expiry = st.sidebar.selectbox("Expiration Date", expirations)

@st.cache_data(ttl=300)
def fetch_options_chain(symbol, expiry):
    ticker = yf.Ticker(symbol)
    opt = ticker.option_chain(expiry)
    return opt.calls, opt.puts

calls, puts = fetch_options_chain(ticker_symbol, selected_expiry)

# Strategy Selection
strategy = st.sidebar.radio("Select Strategy", ["Bull Call Spread", "Bear Put Spread"])

st.sidebar.markdown("---")
st.sidebar.subheader("Trade Parameters")
contracts = st.sidebar.number_input("Number of Contracts (100 shares each)", min_value=1, value=1, step=1, help="Size of your position. 1 contract controls 100 shares.")
commission = st.sidebar.number_input("Broker Commission/Fee ($ per leg)", min_value=0.00, value=0.65, step=0.05, format="%.2f", help="Standard options commission is ~$0.65")
risk_free_rate = st.sidebar.number_input("Risk-Free Interest Rate (%)", min_value=0.0, value=5.0, step=0.1, help="Treasury yield used in Black-Scholes calculations") / 100.0
st.sidebar.markdown("---")

def get_premium(df, strike):
    row = df[df['strike'] == strike].iloc[0]
    # Use mid-price if Bid/Ask are available, otherwise use last price
    if row['bid'] == 0 and row['ask'] == 0:
        return row['lastPrice']
    return (row['bid'] + row['ask']) / 2

if strategy == "Bull Call Spread":
    st.sidebar.subheader("Select Call Options")
    # Get available strikes and set default selection indices
    available_strikes = calls['strike'].tolist()
    
    default_k1_idx = len(available_strikes) // 2
    if current_price:
        # Find ATM strike
        closest_strike = min(available_strikes, key=lambda x: abs(x - current_price))
        default_k1_idx = available_strikes.index(closest_strike)
        
    K1 = st.sidebar.selectbox("Long Call Strike (K1)", available_strikes, index=default_k1_idx)
    
    k2_options = [k for k in available_strikes if k > K1]
    if not k2_options:
        st.error("No valid K2 strikes available for the selected K1.")
        st.stop()
        
    K2 = st.sidebar.selectbox("Short Call Strike (K2)", k2_options, index=min(2, len(k2_options)-1))
    
    try:
        C1 = get_premium(calls, K1)
        C2 = get_premium(calls, K2)
    except IndexError:
        st.error("Premium data missing for selected strikes.")
        st.stop()
        
    net_debit_per_share = C1 - C2
    total_commission = contracts * 2 * commission # 2 legs per contract
    net_debit = (net_debit_per_share * 100 * contracts) + total_commission
    
    st.markdown("---")
    st.markdown(f"### 📈 {ticker_symbol} - 6 Month Price Action vs Selected Strikes")
    fig_candle.add_hline(y=K1, line_dash="dash", line_color="#3498db", annotation_text=f"K1 Long Call (${K1})", annotation_position="top left")
    fig_candle.add_hline(y=K2, line_dash="dash", line_color="#e67e22", annotation_text=f"K2 Short Call (${K2})", annotation_position="bottom left")
    st.plotly_chart(fig_candle, use_container_width=True)
    st.markdown("---")
    
    st.markdown(f"### Bull Call Spread (Buy Call @ {K1}, Sell Call @ {K2})")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Long Call Premium", f"${C1:.2f}")
    col2.metric("Short Call Premium", f"${C2:.2f}")
    col3.metric("Net Debit (Per Share)", f"${net_debit_per_share:.2f}")
    col4.metric("Capital Required (Cost)", f"${net_debit:.2f}")
    
    # Analytics
    max_profit = ((K2 - K1) * 100 * contracts) - net_debit
    max_loss = -net_debit
    breakeven = K1 + (net_debit / (100 * contracts))
    
    st.markdown("#### Strategy Analytics")
    col1, col2, col3 = st.columns(3)
    col1.metric(f"Total Max Profit", f"${max_profit:.2f}")
    col2.metric(f"Total Max Loss", f"-${abs(max_loss):.2f}")
    col3.metric("Underlying Breakeven", f"${breakeven:.2f}")
    
    # Plotting
    ST = np.linspace(current_price * 0.7, current_price * 1.3, 500)
    payoff_long = np.maximum(ST - K1, 0) * 100 * contracts
    payoff_short = -np.maximum(ST - K2, 0) * 100 * contracts
    payoff = payoff_long + payoff_short
    profit = payoff - net_debit
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ST, y=profit, mode='lines', name='Profit/Loss', line=dict(color='#2ecc71', width=3)))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.add_vline(x=current_price, line_dash="dot", line_color="#3498db", annotation_text="Current Price", annotation_position="top left")
    fig.add_vline(x=breakeven, line_dash="dash", line_color="#e67e22", annotation_text="Breakeven", annotation_position="bottom right")
    
    # Fill colors
    fig.add_trace(go.Scatter(x=ST, y=np.where(profit >= 0, profit, 0), fill='tozeroy', mode='none', fillcolor='rgba(46, 204, 113, 0.3)', showlegend=False))
    fig.add_trace(go.Scatter(x=ST, y=np.where(profit < 0, profit, 0), fill='tozeroy', mode='none', fillcolor='rgba(231, 76, 60, 0.3)', showlegend=False))
    
    fig.update_layout(title=f"Payoff Diagram for {ticker_symbol} Bull Call Spread", xaxis_title="Stock Price at Expiration ($)", yaxis_title="Profit / Loss ($)")
    st.plotly_chart(fig, use_container_width=True)

elif strategy == "Bear Put Spread":
    st.sidebar.subheader("Select Put Options")
    available_strikes = puts['strike'].tolist()
    
    default_k2_idx = len(available_strikes) // 2
    if current_price:
        closest_strike = min(available_strikes, key=lambda x: abs(x - current_price))
        default_k2_idx = available_strikes.index(closest_strike)
        
    K2 = st.sidebar.selectbox("Long Put Strike (K2)", available_strikes, index=default_k2_idx)
    
    k1_options = [k for k in available_strikes if k < K2]
    if not k1_options:
        st.error("No valid K1 strikes available for the selected K2.")
        st.stop()
        
    K1 = st.sidebar.selectbox("Short Put Strike (K1)", list(reversed(k1_options)), index=min(2, len(k1_options)-1))
    
    try:
        P2 = get_premium(puts, K2)
        P1 = get_premium(puts, K1)
    except IndexError:
        st.error("Premium data missing for selected strikes.")
        st.stop()
        
    net_debit_per_share = P2 - P1
    total_commission = contracts * 2 * commission
    net_debit = (net_debit_per_share * 100 * contracts) + total_commission
    
    st.markdown("---")
    st.markdown(f"### 📈 {ticker_symbol} - 6 Month Price Action vs Selected Strikes")
    fig_candle.add_hline(y=K2, line_dash="dash", line_color="#3498db", annotation_text=f"K2 Long Put (${K2})", annotation_position="bottom left")
    fig_candle.add_hline(y=K1, line_dash="dash", line_color="#e67e22", annotation_text=f"K1 Short Put (${K1})", annotation_position="top left")
    st.plotly_chart(fig_candle, use_container_width=True)
    st.markdown("---")
    
    st.markdown(f"### Bear Put Spread (Buy Put @ {K2}, Sell Put @ {K1})")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Long Put Premium", f"${P2:.2f}")
    col2.metric("Short Put Premium", f"${P1:.2f}")
    col3.metric("Net Debit (Per Share)", f"${net_debit_per_share:.2f}")
    col4.metric("Capital Required (Cost)", f"${net_debit:.2f}")
    
    # Analytics
    max_profit = ((K2 - K1) * 100 * contracts) - net_debit
    max_loss = -net_debit
    breakeven = K2 - (net_debit / (100 * contracts))
    
    st.markdown("#### Strategy Analytics")
    col1, col2, col3 = st.columns(3)
    col1.metric(f"Total Max Profit", f"${max_profit:.2f}")
    col2.metric(f"Total Max Loss", f"-${abs(max_loss):.2f}")
    col3.metric("Underlying Breakeven", f"${breakeven:.2f}")
    
    # Plotting
    ST = np.linspace(current_price * 0.7, current_price * 1.3, 500)
    payoff_long = np.maximum(K2 - ST, 0) * 100 * contracts
    payoff_short = -np.maximum(K1 - ST, 0) * 100 * contracts
    payoff = payoff_long + payoff_short
    profit = payoff - net_debit
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ST, y=profit, mode='lines', name='Profit/Loss', line=dict(color='#3498db', width=3)))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.add_vline(x=current_price, line_dash="dot", line_color="#2ecc71", annotation_text="Current Price", annotation_position="top left")
    fig.add_vline(x=breakeven, line_dash="dash", line_color="#e67e22", annotation_text="Breakeven", annotation_position="bottom right")
    
    # Fill colors
    fig.add_trace(go.Scatter(x=ST, y=np.where(profit >= 0, profit, 0), fill='tozeroy', mode='none', fillcolor='rgba(52, 152, 219, 0.3)', showlegend=False))
    fig.add_trace(go.Scatter(x=ST, y=np.where(profit < 0, profit, 0), fill='tozeroy', mode='none', fillcolor='rgba(230, 126, 34, 0.3)', showlegend=False))
    
    fig.update_layout(title=f"Payoff Diagram for {ticker_symbol} Bear Put Spread", xaxis_title="Stock Price at Expiration ($)", yaxis_title="Profit / Loss ($)")
    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# Monte Carlo & Investment Verdict
# ==========================================

st.markdown("---")
with st.expander("🤖 REVEAL: Advanced Monte Carlo Simulation & Model Verdict"):
    st.markdown("### 🎲 Monte Carlo Simulation & Algorithmic Verdict")
    st.write("Simulate 10,000 geometric brownian motion paths to find the mathematical probability of success.")

    # 1. Fetch Implied Volatility
    df_options = calls if strategy == "Bull Call Spread" else puts
    try:
        iv1 = df_options[df_options['strike'] == K1].iloc[0]['impliedVolatility']
        iv2 = df_options[df_options['strike'] == K2].iloc[0]['impliedVolatility']
        sigma = (iv1 + iv2) / 2
    except:
        sigma = 0.20 # Fallback

    if sigma < 0.01: sigma = 0.20

    # 2. Calculate T (Time to Expiry in Years)
    expiry_date = datetime.strptime(selected_expiry, "%Y-%m-%d")
    T = (expiry_date - datetime.today()).days / 365.0
    if T <= 0: T = 0.002 # 1 day fallback

    if st.button("Run 10,000 Monte Carlo Simulations"):
        with st.spinner("Running complex stochastic simulations..."):
            # Geometric Brownian Motion
            r = risk_free_rate
            S_T_sim = current_price * np.exp((r - 0.5 * sigma**2) * T + sigma * np.sqrt(T) * np.random.standard_normal(10000))
            
            # Calculate simulated profit
            if strategy == "Bull Call Spread":
                payoff_sim = (np.maximum(S_T_sim - K1, 0) - np.maximum(S_T_sim - K2, 0)) * 100 * contracts
            else:
                payoff_sim = (np.maximum(K2 - S_T_sim, 0) - np.maximum(K1 - S_T_sim, 0)) * 100 * contracts
                
            profit_sim = payoff_sim - net_debit
            
            # Analytics
            pop = np.mean(profit_sim > 0) * 100
            exp_value = np.mean(profit_sim)
            
            col1, col2 = st.columns(2)
            col1.metric("Probability of Profit (POP)", f"{pop:.1f}%")
            col2.metric("Expected Total Payout (Mean Result)", f"${exp_value:.2f}")
            
            # Histogram Plotly
            profit_pos = profit_sim[profit_sim >= 0]
            profit_neg = profit_sim[profit_sim < 0]
            
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Histogram(x=profit_pos, name="Profit Zone", marker_color='#2ecc71', opacity=0.75))
            fig_hist.add_trace(go.Histogram(x=profit_neg, name="Loss Zone", marker_color='#e74c3c', opacity=0.75))
            
            fig_hist.update_layout(
                title="Simulated 10,000 Path Profit/Loss Distribution", 
                xaxis_title="Simulation Profit / Loss ($)", 
                yaxis_title="Frequency (Out of 10k paths)",
                barmode='overlay'
            )
            fig_hist.add_vline(x=0, line_dash="dash", line_color="white")
            st.plotly_chart(fig_hist, use_container_width=True)
            
            # Investment Verdict
            st.markdown("#### 🤖 Algorithmic Recommendation")
            rr_ratio = max_profit / abs(max_loss) if max_loss != 0 else 0
            
            if pop > 50 and rr_ratio > 1.0:
                st.success(f"🔥 **Favorable Trade!** A highly attractive {pop:.1f}% mathematical probability of profit paired with a solid {rr_ratio:.2f}:1 Reward-to-Risk ratio.")
            elif pop > 40 and rr_ratio >= 1.5:
                st.info(f"👍 **Acceptable Trade.** A reasonable {pop:.1f}% win rate compensated beautifully by an excellent {rr_ratio:.2f}:1 Reward-to-Risk payload.")
            elif pop > 60 and rr_ratio >= 0.5:
                st.info(f"👍 **High-Probability Scrape.** A massive {pop:.1f}% win rate, though the smaller {rr_ratio:.2f}:1 payout reflects that extreme safety.")
            else:
                st.warning(f"⚠️ **High Risk.** The {pop:.1f}% win rate and {rr_ratio:.2f}:1 R:R ratio do not indicate a distinct mathematical edge right now. Wait for better alignment.")

st.markdown("---")
st.markdown("*Note: Premiums are estimated using the mid-point between the Bid and Ask prices, or the Last Price if bid/ask are unavailable.*")
