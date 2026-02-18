import unittest
import types
import sys

import pandas as pd

class _DummyExchange:
    def fetch_ticker(self, symbol):
        return {"last": 100.0}

    def fetch_ohlcv(self, symbol, timeframe="1h", limit=500):
        return []

    def create_market_order(self, symbol, side, amount):
        return {"symbol": symbol, "side": side, "amount": amount}


if "ccxt" not in sys.modules:
    sys.modules["ccxt"] = types.SimpleNamespace(bitbank=lambda *_args, **_kwargs: _DummyExchange())

from live_trader import LiveTrader


class DummyStrategy:
    def generate_signals(self, df):
        out = pd.DataFrame(index=df.index)
        out["signal"] = [0.0 for _ in range(len(df))]
        return out


class LiveTraderTests(unittest.TestCase):
    def test_confirmed_signal_uses_second_last_candle(self):
        trader = LiveTrader(DummyStrategy(), test_mode=True)
        signals = pd.DataFrame({"signal": [0.0, 1.0, -1.0]})
        self.assertEqual(trader._get_latest_confirmed_signal(signals), 1.0)

    def test_test_mode_applies_fee_and_slippage(self):
        trader = LiveTrader(
            DummyStrategy(),
            amount=1.0,
            test_mode=True,
            virtual_balance=1_000.0,
            taker_fee_pct=0.1,
            slippage_bps=100.0,
        )

        buy = trader.execute_order("buy", price=100.0)
        self.assertIsNotNone(buy)
        # buy exec = 101, cost=101, fee=0.101
        self.assertAlmostEqual(trader.virtual_balance, 1_000.0 - 101.101, places=6)
        self.assertAlmostEqual(trader.virtual_btc, 1.0, places=6)

        trader.position = {"amount": 1.0, "entry_price": buy["price"], "entry_fee": buy["fee"]}
        sell = trader.execute_order("sell", price=100.0)
        self.assertIsNotNone(sell)
        # sell exec = 99, revenue=99, fee=0.099, net=98.901
        self.assertAlmostEqual(trader.virtual_balance, 1_000.0 - 101.101 + 98.901, places=6)
        self.assertAlmostEqual(trader.virtual_btc, 0.0, places=6)
        self.assertLess(trader.total_profit, 0.0)


if __name__ == "__main__":
    unittest.main()
