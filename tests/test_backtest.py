import unittest

import pandas as pd

from backtest import Backtest


class StepStrategy:
    def __init__(self, signals):
        self._signals = signals

    def generate_signals(self, df):
        out = pd.DataFrame(index=df.index)
        out["signal"] = self._signals
        return out


class BacktestTests(unittest.TestCase):
    def _sample_df(self):
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2025-01-01", periods=4, freq="h"),
                "open": [100, 100, 100, 100],
                "high": [100, 100, 100, 100],
                "low": [100, 100, 100, 100],
                "close": [100, 100, 100, 100],
                "volume": [1, 1, 1, 1],
            }
        )

    def test_sell_signal_logs_non_zero_amount(self):
        df = self._sample_df()
        strategy = StepStrategy([0.0, 1.0, 0.0, -1.0])
        bt = Backtest(initial_balance=1_000_000, taker_fee=0.0, slippage_bps=0.0)
        _, logs = bt.run(df, strategy)
        sell_logs = [x for x in logs if x["type"] == "SELL (SIGNAL)"]
        self.assertTrue(sell_logs)
        self.assertGreater(sell_logs[0]["amount"], 0.0)

    def test_slippage_reduces_pnl(self):
        df = self._sample_df()
        strategy = StepStrategy([0.0, 1.0, 0.0, -1.0])
        bt = Backtest(initial_balance=1_000_000, taker_fee=0.0, slippage_bps=100)
        portfolio, _ = bt.run(df, strategy)
        self.assertLess(portfolio[-1], 1_000_000)

    def test_trade_fraction_keeps_unused_cash(self):
        df = self._sample_df()
        strategy = StepStrategy([0.0, 1.0, 0.0, -1.0])
        bt = Backtest(initial_balance=1_000_000, taker_fee=0.0, slippage_bps=0.0, trade_fraction=0.5)
        portfolio, _ = bt.run(df, strategy)
        self.assertAlmostEqual(portfolio[-1], 1_000_000, places=6)

    def test_spread_reduces_pnl(self):
        df = self._sample_df()
        strategy = StepStrategy([0.0, 1.0, 0.0, -1.0])
        bt = Backtest(initial_balance=1_000_000, taker_fee=0.0, slippage_bps=0.0, spread_bps=100)
        portfolio, _ = bt.run(df, strategy)
        self.assertLess(portfolio[-1], 1_000_000)

    def test_fill_ratio_allows_partial_exit(self):
        df = self._sample_df()
        strategy = StepStrategy([0.0, 1.0, 0.0, -1.0])
        bt = Backtest(initial_balance=1_000_000, taker_fee=0.0, fill_ratio=0.5)
        bt.run(df, strategy)
        self.assertGreater(bt.position_amt, 0.0)


if __name__ == "__main__":
    unittest.main()
