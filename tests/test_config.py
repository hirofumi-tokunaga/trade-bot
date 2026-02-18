import json
import os
import tempfile
import unittest

from config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_default_when_missing(self):
        cfg = load_config("does_not_exist.json")
        self.assertIn("backtest", cfg)
        self.assertIn("live", cfg)
        self.assertIn("strategy_defaults", cfg)

    def test_override_values(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(
                {
                    "backtest": {"initial_balance": 12345},
                    "strategy_defaults": {"donchian_window": 111},
                },
                f,
            )
            path = f.name

        try:
            cfg = load_config(path)
            self.assertEqual(cfg["backtest"]["initial_balance"], 12345)
            self.assertEqual(cfg["strategy_defaults"]["donchian_window"], 111)
            # non-overridden fields remain
            self.assertIn("slippage_bps", cfg["backtest"])
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
