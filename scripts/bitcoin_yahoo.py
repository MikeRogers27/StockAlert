import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# -----------------------------
# Parameters
# -----------------------------
symbol = "BTC-USD"
start_date = "2015-01-01"  # BTC data before 2015 is less liquid
dip_thresholds = [-0.20, -0.30, -0.40, -0.50]  # -30%, -40%, -50%
forward_windows = [30, 90, 180, 365]   # 1m, 3m, 6m, 12m (calendar days)

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

# -----------------------------
# Indicators
# -----------------------------
close = data["Close"][symbol]
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
        (data["Close"][symbol] < data["200DMA"])
    )

# -----------------------------
# Performance Evaluation
# -----------------------------
results = []
for t in dip_thresholds:
    signal_dates = signals.index[signals[f"Dip_{int(t*100)}"]]
    for date in signal_dates:
        entry_price = data.loc[date, "Close"][symbol]
        row = {"Threshold": f"{int(t*100)}%", "Date": date, "Entry Price": entry_price}
        for fw in forward_windows:
            future_date = date + pd.Timedelta(days=fw)
            if future_date in data.index:
                future_price = data.loc[future_date, "Close"][symbol]
                row[f"Return_{fw}d"] = (future_price / entry_price - 1) * 100
            else:
                row[f"Return_{fw}d"] = np.nan
        results.append(row)

results_df = pd.DataFrame(results)
pd.set_option("display.max_rows", 20)
print("\n=== Bitcoin Buy-the-Dip Signal Performance ===\n")
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
plt.plot(data.index, data["Close"], label="Bitcoin", color="black")

colors = {-0.2: "green", -0.30: "orange", -0.40: "red", -0.50: "purple"}
for t in dip_thresholds:
    signal_dates = signals.index[signals[f"Dip_{int(t*100)}"]]
    plt.scatter(signal_dates, data.loc[signal_dates, "Close"], 
                label=f"{int(t*100)}% Dip Signal", marker="^", s=100, 
                color=colors[t])

plt.plot(data.index, data["200DMA"], label="200DMA", linestyle="--", alpha=0.7)
plt.title("Bitcoin - Buy the Dip Signals")
plt.xlabel("Date")
plt.ylabel("Price (USD)")
plt.legend()
plt.show()
