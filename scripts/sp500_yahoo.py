import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# -----------------------------
# Parameters
# -----------------------------
symbol = "^GSPC"        # S&P 500 index
vix_symbol = "^VIX"     # Volatility Index
start_date = "2000-01-01"
dip_thresholds = [-0.10, -0.15, -0.20]  # -10%, -15%, -20%
forward_windows = [21, 63, 126, 252]   # ~1m, 3m, 6m, 12m (trading days)

# -----------------------------
# Helper Functions
# -----------------------------
def compute_rsi(series, window=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_drawdowns(prices):
    rolling_max = prices.cummax()
    drawdown = (prices - rolling_max) / rolling_max
    return drawdown

# -----------------------------
# Get Data
# -----------------------------
data = yf.download(symbol, start=start_date, auto_adjust=False)
data["Close"] = data["Adj Close"]

# Pull VIX data
vix = yf.download(vix_symbol, start=start_date, auto_adjust=False)
vix["VIX"] = vix["Adj Close"]

# Merge with S&P
data = data.join(vix, how="left")

# -----------------------------
# Indicators
# -----------------------------
# Ensure we only use the Close column as a Series
close = data["Close"]['^GSPC']

data["Drawdown"] = compute_drawdowns(close)
data["200DMA"] = close.rolling(200).mean()
data["200DMA_deviation"] = (close - data["200DMA"]) / data["200DMA"]
data["RSI"] = compute_rsi(close)

# -----------------------------
# Buy Signals
# -----------------------------
signals = pd.DataFrame(index=data.index)
for t in dip_thresholds:
    signals[f"Dip_{int(t*100)}"] = (
        (data["Drawdown"] <= t) & 
            (data["RSI"] < 30) & 
            (data["VIX"] > 25)   # Add VIX filter
    )

# -----------------------------
# Performance Evaluation
# -----------------------------
results = []
for t in dip_thresholds:
    signal_dates = signals.index[signals[f"Dip_{int(t*100)}"]]
    for date in signal_dates:
        entry_price = data.loc[date, "Close"]['^GSPC']
        row = {"Threshold": f"{int(t*100)}%", "Date": date, "Entry Price": entry_price}
        for fw in forward_windows:
            if data.index.get_loc(date) + fw < len(data):
                future_date = data.index[data.index.get_loc(date) + fw]
                future_price = data.loc[future_date, "Close"]['^GSPC']
                row[f"Return_{fw}d"] = (future_price / entry_price - 1) * 100
            else:
                row[f"Return_{fw}d"] = np.nan
        results.append(row)

results_df = pd.DataFrame(results)
pd.set_option("display.max_rows", 20)
print("\n=== Buy-the-Dip Signal Performance ===\n")
print(results_df)

# -----------------------------
# Average Returns Summary
# -----------------------------
summary = results_df.groupby("Threshold")[[c for c in results_df.columns if "Return" in c]].mean()
print("\n=== Average Returns by Threshold ===\n")
print(summary.round(2))

# -----------------------------
# Plot
# -----------------------------
plt.figure(figsize=(14, 8))
plt.plot(data.index, data["Close"][symbol], label="S&P 500", color="black")

colors = {-0.10: "orange", -0.15: "red", -0.20: "purple"}
for t in dip_thresholds:
    signal_dates = signals.index[signals[f"Dip_{int(t*100)}"]]
    plt.scatter(signal_dates, data.loc[signal_dates, "Close"][symbol], 
                label=f"{int(t*100)}% Dip Signal", marker="^", s=100, 
                color=colors[t])

plt.plot(data.index, data["200DMA"], label="200DMA", linestyle="--", alpha=0.7)
plt.title("S&P 500 - Buy the Dip Signals (With VIX filter)")
plt.xlabel("Date")
plt.ylabel("Price")
plt.legend()
plt.show()
