import pandas as pd


class Strategy:
    """Base strategy interface."""

    def generate_signals(self, df):
        raise NotImplementedError("Subclasses should implement this!")


class SmaStrategy(Strategy):
    def __init__(self, short_window=5, long_window=20):
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, df):
        signals = pd.DataFrame(index=df.index)
        signals["signal"] = 0.0
        signals["short_mavg"] = df["close"].rolling(window=self.short_window, min_periods=1).mean()
        signals["long_mavg"] = df["close"].rolling(window=self.long_window, min_periods=1).mean()

        current_bullish = signals["short_mavg"] > signals["long_mavg"]
        prev_bullish = signals["short_mavg"].shift(1) <= signals["long_mavg"].shift(1)
        signals.loc[current_bullish & prev_bullish, "signal"] = 1.0

        current_bearish = signals["short_mavg"] < signals["long_mavg"]
        prev_bearish = signals["short_mavg"].shift(1) >= signals["long_mavg"].shift(1)
        signals.loc[current_bearish & prev_bearish, "signal"] = -1.0
        return signals


class MacdStrategy(Strategy):
    def __init__(self, fast_period=12, slow_period=26, signal_period=9):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def generate_signals(self, df):
        signals = pd.DataFrame(index=df.index)
        signals["signal"] = 0.0

        ema_fast = df["close"].ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.slow_period, adjust=False).mean()
        signals["macd"] = ema_fast - ema_slow
        signals["signal_line"] = signals["macd"].ewm(span=self.signal_period, adjust=False).mean()

        # Trend filter
        signals["ema200"] = df["close"].ewm(span=200, adjust=False, min_periods=200).mean()

        # RSI filter
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        signals["rsi"] = 100 - (100 / (1 + rs))

        macd_cross_up = (signals["macd"] > signals["signal_line"]) & (
            signals["macd"].shift(1) <= signals["signal_line"].shift(1)
        )

        buy_condition = macd_cross_up & (df["close"] > signals["ema200"]) & (signals["rsi"] < 70)
        signals.loc[buy_condition, "signal"] = 1.0

        macd_cross_down = (signals["macd"] < signals["signal_line"]) & (
            signals["macd"].shift(1) >= signals["signal_line"].shift(1)
        )
        signals.loc[macd_cross_down, "signal"] = -1.0

        return signals


class DonchianStrategy(Strategy):
    def __init__(self, window=20, use_atr_filter=True, atr_period=14, atr_threshold=0.0):
        """
        Donchian breakout strategy.

        window: lookback period for channels
        use_atr_filter: whether to require ATR ratio threshold
        atr_period: ATR period
        atr_threshold: minimum ATR/Close ratio (e.g., 0.01 for 1%)
        """
        self.window = window
        self.use_atr_filter = use_atr_filter
        self.atr_period = atr_period
        self.atr_threshold = atr_threshold

    def generate_signals(self, df):
        signals = pd.DataFrame(index=df.index)
        signals["signal"] = 0.0

        signals["high_channel"] = df["high"].rolling(window=self.window).max().shift(1)
        signals["low_channel"] = df["low"].rolling(window=self.window).min().shift(1)

        buy_signal = df["high"] > signals["high_channel"]
        sell_signal = df["low"] < signals["low_channel"]

        if self.use_atr_filter:
            prev_close = df["close"].shift(1)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - prev_close).abs()
            tr3 = (df["low"] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=self.atr_period).mean()
            atr_ratio = atr / df["close"]

            volatility_ok = atr_ratio > self.atr_threshold
            buy_signal = buy_signal & volatility_ok
            sell_signal = sell_signal & volatility_ok

        signals.loc[buy_signal, "signal"] = 1.0
        signals.loc[sell_signal, "signal"] = -1.0
        return signals


class GridStrategy(Strategy):
    def __init__(self, range_min, range_max, grid_num=10, amount_per_grid=0.001, use_ema_filter=True):
        """
        Range grid strategy.

        range_min/range_max: grid price range
        grid_num: number of grid intervals
        amount_per_grid: BTC amount per grid order
        use_ema_filter: buy only when grid price >= EMA200
        """
        self.is_grid = True
        self.range_min = range_min
        self.range_max = range_max
        self.grid_num = grid_num
        self.amount_per_grid = amount_per_grid
        self.use_ema_filter = use_ema_filter

        step = (range_max - range_min) / grid_num
        self.grids = [range_min + i * step for i in range(grid_num + 1)]

        # False: no position at this grid, True: long acquired at this grid
        self.grid_status = [False] * len(self.grids)
        self.ema200 = None

    def setup(self, df):
        if self.use_ema_filter:
            self.ema200 = df["close"].ewm(span=200, adjust=False, min_periods=200).mean()
        else:
            self.ema200 = None
        self.current_idx = 0

    def check_execution(self, high, low, timestamp):
        executions = []

        current_ema = 0
        if self.use_ema_filter and self.ema200 is not None:
            try:
                current_ema = self.ema200.loc[timestamp]
            except Exception:
                pass

        for i, price in enumerate(self.grids):
            if not self.grid_status[i]:
                if low <= price:
                    if self.use_ema_filter and price < current_ema:
                        continue

                    executions.append({"type": "BUY", "price": price, "amount": self.amount_per_grid})
                    self.grid_status[i] = True
            else:
                if i + 1 < len(self.grids):
                    sell_price = self.grids[i + 1]
                    if high >= sell_price:
                        executions.append({"type": "SELL", "price": sell_price, "amount": self.amount_per_grid})
                        self.grid_status[i] = False

        return executions
