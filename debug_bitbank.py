import ccxt
import time

def debug_bitbank():
    bitbank = ccxt.bitbank()
    try:
        # Load markets to verify connection and symbol mapping
        markets = bitbank.load_markets()
        print(f"Loaded {len(markets)} markets.")
        if 'BTC/JPY' in markets:
            print("BTC/JPY is available.")
        else:
            print("BTC/JPY NOT found. Available keys sample:", list(markets.keys())[:5])

        # Try fetching ticker
        print("Fetching ticker for BTC/JPY...")
        ticker = bitbank.fetch_ticker('BTC/JPY')
        print("Ticker:", ticker)

        # Try fetching OHLCV again with explicit parameters
        print("Fetching OHLCV...")
        # Bitbank candlestick API is grouped by day/year. ccxt needs to construct the URL.
        # Try fetching from a specific timestamp (e.g. 24 hours ago)
        since = bitbank.milliseconds() - 24 * 60 * 60 * 1000 * 10 # 10 days ago
        ohlcv = bitbank.fetch_ohlcv('BTC/JPY', '1h', since=since, limit=10)
        print(f"Fetched {len(ohlcv)} candles.")

    except Exception as e:
        print("Error:", e)
        # Print exception details if possible
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_bitbank()
