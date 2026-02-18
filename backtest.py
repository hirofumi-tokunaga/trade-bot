import pandas as pd
import numpy as np


class Backtest:
    def __init__(
        self,
        initial_balance=1000000,
        maker_fee=-0.02,
        taker_fee=0.12,
        slippage_bps=0.0,
        spread_bps=0.0,
        fill_ratio=1.0,
        trade_fraction=1.0,
    ):
        """
        initial_balance: initial JPY balance
        maker_fee: maker fee rate in % (negative means rebate)
        taker_fee: taker fee rate in %
        slippage_bps: per-trade slippage in bps (1 bps = 0.01%)
        spread_bps: simulated spread in bps (applied half each side)
        fill_ratio: fill ratio per execution (0-1)
        trade_fraction: fraction of available cash to use on each entry (0-1)
        """
        self.initial_balance = initial_balance
        self.maker_fee = maker_fee / 100.0
        self.taker_fee = taker_fee / 100.0
        self.slippage_rate = slippage_bps / 10000.0
        self.spread_rate = spread_bps / 10000.0
        self.fill_ratio = max(0.0, min(float(fill_ratio), 1.0))
        self.trade_fraction = max(0.0, min(float(trade_fraction), 1.0))

        self.reset()

    def _apply_slippage(self, price, side):
        if side == "buy":
            return price * (1.0 + (self.spread_rate / 2.0)) * (1.0 + self.slippage_rate)
        if side == "sell":
            return price * (1.0 - (self.spread_rate / 2.0)) * (1.0 - self.slippage_rate)
        return price

    def reset(self):
        self.balance = self.initial_balance
        self.position_amt = 0.0
        self.avg_entry_price = 0.0
        self.trade_log = []
        self.portfolio_values = []
        self.drawdowns = []

    def calculate_drawdown(self, portfolio_values):
        """Calculate max drawdown in %."""
        if not portfolio_values:
            return 0.0

        peak = portfolio_values[0]
        max_dd = 0.0

        for value in portfolio_values:
            if value > peak:
                peak = value

            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd

        return max_dd * 100

    def run(self, df, strategy, sl_pct=None, tp_pct=None, trailing_pct=None):
        """Run backtest against OHLCV dataframe and strategy."""
        self.reset()
        print("Running backtest...")

        if hasattr(strategy, "is_grid") and strategy.is_grid:
            self.run_grid(df, strategy)
        else:
            self.run_signal(df, strategy, sl_pct, tp_pct, trailing_pct)

        final_value = self.portfolio_values[-1] if self.portfolio_values else self.initial_balance
        profit = final_value - self.initial_balance
        max_dd = self.calculate_drawdown(self.portfolio_values)

        print("-" * 30)
        print(f"Initial balance: {self.initial_balance:,.0f} JPY")
        print(f"Final value: {final_value:,.0f} JPY")
        print(f"Profit: {profit:,.0f} JPY ({(profit / self.initial_balance) * 100:.2f}%)")
        print(f"Max drawdown: {max_dd:.2f}%")
        print(f"Total trades: {len(self.trade_log)}")
        print("-" * 30)

        return self.portfolio_values, self.trade_log

    def run_signal(self, df, strategy, sl_pct=None, tp_pct=None, trailing_pct=None):
        """
        Backtest for signal-based strategies with optional SL/TP/Trailing.
        sl_pct/tp_pct/trailing_pct are decimal ratios (e.g., 0.05 = 5%).
        """
        signals = strategy.generate_signals(df)

        highest_price_since_entry = 0.0

        for i in range(len(df)):
            row = df.iloc[i]
            timestamp = row["timestamp"]
            high = row["high"]
            low = row["low"]
            close = row["close"]
            price = close

            signal = signals.iloc[i]["signal"]
            fee_rate = self.taker_fee

            if self.position_amt > 0.0:
                is_exit = False
                exit_reason = ""
                exit_price = price

                if high > highest_price_since_entry:
                    highest_price_since_entry = high

                if sl_pct is not None:
                    sl_price = self.avg_entry_price * (1.0 - sl_pct)
                    if low <= sl_price:
                        is_exit = True
                        exit_reason = "STOP_LOSS"
                        exit_price = sl_price

                if not is_exit and tp_pct is not None:
                    tp_price = self.avg_entry_price * (1.0 + tp_pct)
                    if high >= tp_price:
                        is_exit = True
                        exit_reason = "TAKE_PROFIT"
                        exit_price = tp_price

                if not is_exit and trailing_pct is not None:
                    ts_price = highest_price_since_entry * (1.0 - trailing_pct)
                    if low <= ts_price:
                        is_exit = True
                        exit_reason = "TRAILING_STOP"
                        exit_price = ts_price

                if is_exit:
                    sold_amount = self.position_amt * self.fill_ratio
                    if sold_amount <= 0:
                        current_val = self.balance + (self.position_amt * price)
                        self.portfolio_values.append(current_val)
                        continue
                    exec_exit_price = self._apply_slippage(exit_price, "sell")
                    revenue = sold_amount * exec_exit_price
                    fee = revenue * fee_rate
                    self.balance += revenue - fee
                    self.position_amt -= sold_amount
                    self.trade_log.append(
                        {
                            "timestamp": timestamp,
                            "type": f"SELL ({exit_reason})",
                            "price": exec_exit_price,
                            "amount": sold_amount,
                            "fee": fee,
                        }
                    )
                    self.portfolio_values.append(self.balance)
                    continue

            if signal == 1.0 and self.position_amt == 0.0:
                budget = self.balance * self.trade_fraction
                if budget <= 0:
                    current_val = self.balance + (self.position_amt * price)
                    self.portfolio_values.append(current_val)
                    continue
                exec_buy_price = self._apply_slippage(price, "buy")
                intended_amount = budget / (exec_buy_price * (1.0 + fee_rate))
                actual_amount = intended_amount * self.fill_ratio
                cost = actual_amount * exec_buy_price
                fee = cost * fee_rate

                self.position_amt += actual_amount
                self.avg_entry_price = exec_buy_price
                self.balance -= cost + fee
                highest_price_since_entry = exec_buy_price

                self.trade_log.append(
                    {
                        "timestamp": timestamp,
                        "type": "BUY",
                        "price": exec_buy_price,
                        "amount": actual_amount,
                        "fee": fee,
                    }
                )

            elif signal == -1.0 and self.position_amt > 0.0:
                sold_amount = self.position_amt * self.fill_ratio
                if sold_amount <= 0:
                    current_val = self.balance + (self.position_amt * price)
                    self.portfolio_values.append(current_val)
                    continue
                exec_sell_price = self._apply_slippage(price, "sell")
                revenue = sold_amount * exec_sell_price
                fee = revenue * fee_rate

                self.balance += revenue - fee
                self.position_amt -= sold_amount

                self.trade_log.append(
                    {
                        "timestamp": timestamp,
                        "type": "SELL (SIGNAL)",
                        "price": exec_sell_price,
                        "amount": sold_amount,
                        "fee": fee,
                    }
                )

            current_val = self.balance + (self.position_amt * price)
            self.portfolio_values.append(current_val)

    def run_grid(self, df, strategy):
        """Backtest for grid strategy. Grid orders use maker fee."""
        strategy.setup(df)

        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.set_index("timestamp", drop=False)

        for i in range(len(df)):
            row = df.iloc[i]
            timestamp = row["timestamp"]
            high = row["high"]
            low = row["low"]
            close = row["close"]

            fee_rate = self.maker_fee
            executed_orders = strategy.check_execution(high, low, timestamp)

            for order in executed_orders:
                price = order["price"]
                amount = order["amount"]

                if order["type"] == "BUY":
                    cost = price * amount
                    fee = cost * fee_rate

                    if self.balance >= (cost + fee):
                        self.balance -= (cost + fee)
                        self.position_amt += amount
                        self.trade_log.append(
                            {
                                "timestamp": timestamp,
                                "type": "GRID_BUY",
                                "price": price,
                                "amount": amount,
                                "fee": fee,
                            }
                        )

                elif order["type"] == "SELL":
                    if self.position_amt >= amount:
                        revenue = price * amount
                        fee = revenue * fee_rate

                        self.balance += (revenue - fee)
                        self.position_amt -= amount
                        self.trade_log.append(
                            {
                                "timestamp": timestamp,
                                "type": "GRID_SELL",
                                "price": price,
                                "amount": amount,
                                "fee": fee,
                            }
                        )

            current_val = self.balance + (self.position_amt * close)
            self.portfolio_values.append(current_val)
