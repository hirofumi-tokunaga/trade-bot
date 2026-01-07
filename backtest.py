import pandas as pd
import numpy as np

class Backtest:
    def __init__(self, initial_balance=1000000, maker_fee=-0.02, taker_fee=0.12):
        """
        initial_balance: 初期資金 (JPY)
        maker_fee: 指値注文の手数料 (%) - マイナスならリベート
        taker_fee: 成行注文の手数料 (%)
        """
        self.initial_balance = initial_balance
        self.maker_fee = maker_fee / 100.0
        self.taker_fee = taker_fee / 100.0
        
        self.reset()

    def reset(self):
        self.balance = self.initial_balance
        self.position_amt = 0.0 # BTC amount
        self.avg_entry_price = 0.0
        self.trade_log = []
        self.portfolio_values = []
        self.drawdowns = []

    def calculate_drawdown(self, portfolio_values):
        """最大ドローダウンを計算"""
        if not portfolio_values:
            return 0.0
        
        # 累積最大値
        peak = portfolio_values[0]
        max_dd = 0.0
        
        for value in portfolio_values:
            if value > peak:
                peak = value
            
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        
        return max_dd * 100 # %表記

    def run(self, df, strategy, sl_pct=None, tp_pct=None, trailing_pct=None):
        """
        バックテスト実行
        df: OHLCVデータ
        strategy: Strategyオブジェクト
        """
        self.reset()
        print("バックテストを開始します...")

        # グリッド戦略（指値）か、一般戦略（シグナルベース）かで分岐
        # グリッドの場合は一旦SL/TPは未実装（グリッド自体がTPを含むため）
        if hasattr(strategy, 'is_grid') and strategy.is_grid:
            self.run_grid(df, strategy)
        else:
            self.run_signal(df, strategy, sl_pct, tp_pct, trailing_pct)

        # 最終結果計算
        final_value = self.portfolio_values[-1] if self.portfolio_values else self.initial_balance
        profit = final_value - self.initial_balance
        max_dd = self.calculate_drawdown(self.portfolio_values)

        print("-" * 30)
        print(f"初期資金: {self.initial_balance:,.0f} JPY")
        print(f"最終資産: {final_value:,.0f} JPY")
        print(f"損益: {profit:,.0f} JPY ({(profit/self.initial_balance)*100:.2f}%)")
        print(f"最大ドローダウン: {max_dd:.2f}%")
        print(f"総取引回数: {len(self.trade_log)}")
        print("-" * 30)

        return self.portfolio_values, self.trade_log

    def run_signal(self, df, strategy, sl_pct=None, tp_pct=None, trailing_pct=None):
        """
        従来のシグナルベース（成行売買）のバックテスト + リスク管理
        sl_pct: 損切りライン (例: 0.05 = 5%)
        tp_pct: 利確ライン (例: 0.10 = 10%)
        trailing_pct: トレーリングストップ幅 (例: 0.05 = 高値から5%下落で決済)
        """
        signals = strategy.generate_signals(df)
        
        # トレーリングストップ用の最高値記録
        highest_price_since_entry = 0.0
        
        for i in range(len(df)):
            row = df.iloc[i]
            timestamp = row['timestamp']
            open_price = row['open']
            high = row['high']
            low = row['low']
            close = row['close']
            price = close # 基本の売買価格は終値(簡略化)
            
            signal = signals.iloc[i]['signal']
            
            # 成行手数料 (Taker)
            fee_rate = self.taker_fee

            # --- ポジション保有時の決済判定 (SL/TP/Trailing) ---
            if self.position_amt > 0.0:
                is_exit = False
                exit_reason = ""
                exit_price = price
                
                # 最高値更新 (トレーリングストップ用)
                if high > highest_price_since_entry:
                    highest_price_since_entry = high
                
                # 1. Stop Loss (損切り)
                if sl_pct is not None:
                    sl_price = self.avg_entry_price * (1.0 - sl_pct)
                    if low <= sl_price:
                        is_exit = True
                        exit_reason = "STOP_LOSS"
                        # SL価格で約定したとみなす（スリッページ等は無視）
                        exit_price = sl_price
                
                # 2. Take Profit (利確) - SLより後に判定（同足ならSL優先という保守的想定だが、順番は議論あり）
                if not is_exit and tp_pct is not None:
                    tp_price = self.avg_entry_price * (1.0 + tp_pct)
                    if high >= tp_price:
                        is_exit = True
                        exit_reason = "TAKE_PROFIT"
                        exit_price = tp_price

                # 3. Trailing Stop
                if not is_exit and trailing_pct is not None:
                    ts_price = highest_price_since_entry * (1.0 - trailing_pct)
                    # エントリー価格より上であることを条件にするか？ -> 通常はしない（損切りも兼ねる）
                    if low <= ts_price:
                        is_exit = True
                        exit_reason = "TRAILING_STOP"
                        exit_price = ts_price

                # 決済実行
                if is_exit:
                    revenue = self.position_amt * exit_price
                    fee = revenue * fee_rate
                    self.balance = revenue - fee
                    self.position_amt = 0.0
                    self.trade_log.append({
                        'timestamp': timestamp, 'type': f'SELL ({exit_reason})', 
                        'price': exit_price, 'amount': 0.0, 'fee': fee # amountは0にしておく（ロジック簡略化）
                    })
                    # ポジション解消したので次へ
                    current_val = self.balance # ポジション0
                    self.portfolio_values.append(current_val)
                    continue

            # --- 通常の売買シグナル判定 ---
            
            # Buy Signal
            if signal == 1.0 and self.position_amt == 0.0:
                amount = self.balance / price
                cost = amount * price
                fee = cost * fee_rate
                
                actual_amount = (self.balance - fee) / price
                
                self.position_amt = actual_amount
                self.avg_entry_price = price
                self.balance = 0.0
                
                # ポジション初期化
                highest_price_since_entry = price
                
                self.trade_log.append({
                    'timestamp': timestamp, 'type': 'BUY', 'price': price, 
                    'amount': actual_amount, 'fee': fee
                })

            # Sell Signal (戦略からの手仕舞いサイン)
            elif signal == -1.0 and self.position_amt > 0.0:
                revenue = self.position_amt * price
                fee = revenue * fee_rate
                
                self.balance = revenue - fee
                self.position_amt = 0.0
                
                self.trade_log.append({
                    'timestamp': timestamp, 'type': 'SELL (SIGNAL)', 'price': price, 
                    'amount': self.position_amt, 'fee': fee
                })
            
            # 資産記録
            current_val = self.balance + (self.position_amt * price)
            self.portfolio_values.append(current_val)

    def run_grid(self, df, strategy):
        """
        グリッドトレード用のバックテスト（指値注文シミュレーション）
        """
        # グリッドのセットアップ (DataFrameごと渡す)
        strategy.setup(df)
        
        # DataFrameのインデックスをDatetimeIndexにしておく（もしなってなければ）
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.set_index('timestamp', drop=False)
        
        for i in range(len(df)):
            row = df.iloc[i]
            timestamp = row['timestamp']
            high = row['high']
            low = row['low']
            close = row['close']
            
            # 指値注文の手数料 (Maker)
            fee_rate = self.maker_fee

            # 約定判定 (Timestampも渡す)
            executed_orders = strategy.check_execution(high, low, timestamp)
            
            for order in executed_orders:
                # order = {'type': 'BUY'/'SELL', 'price': ..., 'amount': ...}
                price = order['price']
                amount = order['amount']
                
                if order['type'] == 'BUY':
                    cost = price * amount
                    fee = cost * fee_rate
                    
                    if self.balance >= (cost + fee):
                        self.balance -= (cost + fee) # Maker手数料がマイナスなら増える
                        self.position_amt += amount
                        self.trade_log.append({
                            'timestamp': timestamp, 'type': 'GRID_BUY', 
                            'price': price, 'amount': amount, 'fee': fee
                        })
                
                elif order['type'] == 'SELL':
                    if self.position_amt >= amount:
                        revenue = price * amount
                        fee = revenue * fee_rate
                        
                        self.balance += (revenue - fee)
                        self.position_amt -= amount
                        self.trade_log.append({
                            'timestamp': timestamp, 'type': 'GRID_SELL', 
                            'price': price, 'amount': amount, 'fee': fee
                        })

            # 資産記録
            current_val = self.balance + (self.position_amt * close)
            self.portfolio_values.append(current_val)
