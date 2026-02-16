import ccxt
import pandas as pd
import time
from datetime import datetime


def fetch_data(symbol="BTC/JPY", timeframe="1h", limit=100):
    """Fetch OHLCV from Bitbank and return DataFrame."""
    print(f"Fetching {limit} candles for {symbol} ({timeframe})...")

    bitbank = ccxt.bitbank()

    timeframe_duration_ms = 60 * 60 * 1000
    if timeframe == "1d":
        timeframe_duration_ms = 24 * 60 * 60 * 1000

    since = bitbank.milliseconds() - (limit * timeframe_duration_ms)
    all_ohlcv = []

    try:
        while len(all_ohlcv) < limit:
            remaining = limit - len(all_ohlcv)
            ohlcv = bitbank.fetch_ohlcv(symbol, timeframe, since=since, limit=remaining)

            if len(ohlcv) == 0:
                print("No more data returned.")
                break

            all_ohlcv += ohlcv

            last_timestamp = ohlcv[-1][0]
            since = last_timestamp + timeframe_duration_ms

            print(f"Fetched: {len(all_ohlcv)} / {limit}")
            time.sleep(0.1)

        all_ohlcv = all_ohlcv[:limit]

        df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

        print("Fetch completed.")
        return df

    except Exception as e:
        print(f"Fetch failed: {e}")
        return None


def save_to_csv(df, filename="market_data.csv"):
    """Save DataFrame to CSV."""
    if df is not None:
        df.to_csv(filename, index=False)
        print(f"Saved data to {filename}")
    else:
        print("No data to save.")


if __name__ == "__main__":
    data = fetch_data(limit=180)
    save_to_csv(data)
