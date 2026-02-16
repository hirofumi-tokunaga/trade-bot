import ccxt
import pandas as pd
import time
import os
import sys
from datetime import datetime


class LiveTrader:
    def __init__(self, strategy, symbol="BTC/JPY", amount=0.001, sl_pct=None, tp_pct=None, trailing_pct=None, test_mode=True):
        """
        Live trader / paper trader.

        test_mode=True: no exchange order; updates virtual balances only.
        """
        self.strategy = strategy
        self.symbol = symbol
        self.amount = amount
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.trailing_pct = trailing_pct
        self.test_mode = test_mode

        api_key = os.environ.get("BITBANK_API_KEY")
        api_secret = os.environ.get("BITBANK_API_SECRET")

        if not api_key or not api_secret:
            if not test_mode:
                print("Error: Set BITBANK_API_KEY and BITBANK_API_SECRET env vars.")
                sys.exit(1)
            else:
                print("Info: API keys not found. Running in test mode only.")

        self.exchange = ccxt.bitbank({"apiKey": api_key, "secret": api_secret})

        self.position = None
        self.highest_price = 0.0

        self.virtual_balance = 1_000_000.0
        self.virtual_btc = 0.0
        self.total_profit = 0.0

    def fetch_recent_data(self, limit=500):
        """Fetch recent 1h OHLCV data."""
        try:
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe="1h", limit=limit)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df
        except Exception as e:
            print(f"Data fetch error: {e}")
            return None

    def execute_order(self, side, price=None):
        """Execute buy/sell in test mode or live mode."""
        current_price = price if price else self.get_current_price()

        if self.test_mode:
            if side == "buy":
                cost = current_price * self.amount
                if self.virtual_balance >= cost:
                    self.virtual_balance -= cost
                    self.virtual_btc += self.amount
                    print(f"[TEST] BUY {self.amount} BTC @ {current_price:,.0f} JPY")
                    print(f"       Balance: {self.virtual_balance:,.0f} JPY, BTC: {self.virtual_btc:.4f}")
                else:
                    print(
                        f"[TEST] BUY skipped: required {cost:,.0f} > balance {self.virtual_balance:,.0f}"
                    )
                    return None

            elif side == "sell":
                revenue = current_price * self.amount
                if self.virtual_btc >= self.amount * 0.99:
                    self.virtual_balance += revenue
                    self.virtual_btc -= self.amount

                    if self.position:
                        entry = self.position["entry_price"]
                        pnl = (current_price - entry) * self.amount
                        self.total_profit += pnl
                        print(
                            f"[TEST] SELL {self.amount} BTC @ {current_price:,.0f} JPY "
                            f"(PnL: {pnl:+,.0f} JPY)"
                        )
                    else:
                        print(f"[TEST] SELL {self.amount} BTC @ {current_price:,.0f} JPY")

                    print(f"       Balance: {self.virtual_balance:,.0f} JPY, BTC: {self.virtual_btc:.4f}")
                    print(f"       Total Profit: {self.total_profit:+,.0f} JPY")
                else:
                    print("[TEST] SELL skipped: insufficient BTC.")
                    return None

            return {"price": current_price, "amount": self.amount}

        try:
            order = self.exchange.create_market_order(self.symbol, side, self.amount)
            print(f"Live order sent: {order}")
            return {"price": self.get_current_price(), "amount": self.amount}
        except Exception as e:
            print(f"Order error: {e}")
            return None

    def get_current_price(self):
        ticker = self.exchange.fetch_ticker(self.symbol)
        return ticker["last"]

    def check_risk_management(self, current_price):
        """Apply SL/TP/Trailing. Returns True when position is closed."""
        if self.position is None:
            return False

        entry_price = self.position["entry_price"]

        if current_price > self.highest_price:
            self.highest_price = current_price

        if self.sl_pct:
            sl_price = entry_price * (1.0 - self.sl_pct)
            if current_price <= sl_price:
                print(f"Stop Loss hit: {current_price} <= {sl_price}")
                self.execute_order("sell", current_price)
                self.position = None
                return True

        if self.tp_pct:
            tp_price = entry_price * (1.0 + self.tp_pct)
            if current_price >= tp_price:
                print(f"Take Profit hit: {current_price} >= {tp_price}")
                self.execute_order("sell", current_price)
                self.position = None
                return True

        if self.trailing_pct:
            ts_price = self.highest_price * (1.0 - self.trailing_pct)
            if current_price <= ts_price:
                print(f"Trailing Stop hit: {current_price} <= {ts_price} (high={self.highest_price})")
                self.execute_order("sell", current_price)
                self.position = None
                return True

        return False

    def run(self, interval_sec=60):
        print(f"Live trader started ({self.symbol}) | test_mode={self.test_mode}")
        if self.test_mode:
            print(f"Initial virtual balance: {self.virtual_balance:,.0f} JPY")

        print(f"Strategy: {self.strategy.__class__.__name__}")
        print("Press Ctrl+C to stop.")

        while True:
            try:
                current_price = self.get_current_price()
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Price: {current_price} JPY")

                if self.test_mode:
                    if self.position:
                        unrealized_pnl = (current_price - self.position["entry_price"]) * self.amount
                        print(f"Position: OPEN (unrealized PnL: {unrealized_pnl:+,.0f} JPY)")
                    else:
                        print("Position: FLAT")

                if self.check_risk_management(current_price):
                    print("Exited by risk management.")
                    time.sleep(interval_sec)
                    continue

                df = self.fetch_recent_data()
                if df is None:
                    time.sleep(10)
                    continue

                signals = self.strategy.generate_signals(df)
                latest_signal = signals.iloc[-1]["signal"]

                if latest_signal == 1.0 and self.position is None:
                    print("BUY signal")
                    res = self.execute_order("buy", current_price)
                    if res:
                        self.position = {"amount": self.amount, "entry_price": res["price"]}
                        self.highest_price = res["price"]

                elif latest_signal == -1.0 and self.position is not None:
                    print("SELL signal")
                    self.execute_order("sell", current_price)
                    self.position = None

                else:
                    if not self.test_mode:
                        if self.position:
                            print(f"Position OPEN (entry: {self.position['entry_price']}) - no action")
                        else:
                            print("No signal - waiting")

                time.sleep(interval_sec)

            except KeyboardInterrupt:
                print("\nStopped.")
                if self.test_mode:
                    print(f"Final virtual balance: {self.virtual_balance:,.0f} JPY")
                    print(f"Total Profit: {self.total_profit:+,.0f} JPY")
                break
            except Exception as e:
                print(f"Runtime error: {e}")
                time.sleep(30)
