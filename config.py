import json
import os
from copy import deepcopy


DEFAULT_CONFIG = {
    "backtest": {
        "initial_balance": 1_000_000,
        "maker_fee_pct": -0.02,
        "taker_fee_pct": 0.12,
        "slippage_bps": 5.0,
        "spread_bps": 0.0,
        "fill_ratio": 1.0,
        "trade_fraction": 1.0,
    },
    "live": {
        "virtual_balance": 1_000_000.0,
        "taker_fee_pct": 0.12,
        "slippage_bps": 5.0,
        "interval_sec": 60,
    },
    "strategy_defaults": {
        "donchian_window": 240,
        "donchian_atr_threshold_pct": 0.3,
        "donchian_sl_pct": 5.0,
        "donchian_tp_pct": 15.0,
        "donchian_trailing_pct": 5.0,
    },
}


def _deep_merge(base, override):
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path="config.json"):
    config = deepcopy(DEFAULT_CONFIG)
    if not os.path.exists(path):
        return config

    with open(path, "r", encoding="utf-8") as f:
        user_config = json.load(f)
    return _deep_merge(config, user_config)
