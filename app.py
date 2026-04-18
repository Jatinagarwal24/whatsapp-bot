import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# Page config
st.set_page_config(page_title="Options Strategy Payoffs", layout="wide")

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
        history = ticker.history(period="1d")
        if history.empty:
            return None, None
        current_price = history['Close'].iloc[-1]
        expirations = ticker.options
        return current_price, expirations
    except Exception as e:
        return None, None

current_price, expirations = fetch_ticker_data(ticker_symbol)

if current_price is None or not expirations:
    st.error(f"Could not fetch data for ticker: {ticker_symbol}. Please check the symbol and ensure it has options available.")
    st.stop()

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
        
    net_debit = C1 - C2
    
    st.markdown(f"### Bull Call Spread (Buy Call @ {K1}, Sell Call @ {K2})")
    col1, col2, col3 = st.columns(3)
    col1.metric("Long Call (K1) Premium", f"${C1:.2f}")
    col2.metric("Short Call (K2) Premium", f"${C2:.2f}")
    col3.metric("Net Debit (Cost)", f"${net_debit:.2f}")
    
    # Analytics
    max_profit = K2 - K1 - net_debit
    max_loss = -net_debit
    breakeven = K1 + net_debit
    
    st.markdown("#### Strategy Analytics")
    col1, col2, col3 = st.columns(3)
    col1.metric("Max Profit", f"${max_profit:.2f}")
    col2.metric("Max Loss", f"${max_loss:.2f}")
    col3.metric("Breakeven", f"${breakeven:.2f}")
    
    # Plotting
    ST = np.linspace(current_price * 0.7, current_price * 1.3, 500)
    payoff_long = np.maximum(ST - K1, 0)
    payoff_short = -np.maximum(ST - K2, 0)
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
        
    net_debit = P2 - P1
    
    st.markdown(f"### Bear Put Spread (Buy Put @ {K2}, Sell Put @ {K1})")
    col1, col2, col3 = st.columns(3)
    col1.metric("Long Put (K2) Premium", f"${P2:.2f}")
    col2.metric("Short Put (K1) Premium", f"${P1:.2f}")
    col3.metric("Net Debit (Cost)", f"${net_debit:.2f}")
    
    # Analytics
    max_profit = K2 - K1 - net_debit
    max_loss = -net_debit
    breakeven = K2 - net_debit
    
    st.markdown("#### Strategy Analytics")
    col1, col2, col3 = st.columns(3)
    col1.metric("Max Profit", f"${max_profit:.2f}")
    col2.metric("Max Loss", f"${max_loss:.2f}")
    col3.metric("Breakeven", f"${breakeven:.2f}")
    
    # Plotting
    ST = np.linspace(current_price * 0.7, current_price * 1.3, 500)
    payoff_long = np.maximum(K2 - ST, 0)
    payoff_short = -np.maximum(K1 - ST, 0)
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

st.markdown("---")
st.markdown("*Note: Premiums are estimated using the mid-point between the Bid and Ask prices, or the Last Price if bid/ask are unavailable.*")
