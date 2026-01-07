import ccxt
import pandas as pd
import time
import os
import sys
from datetime import datetime

class LiveTrader:
    def __init__(self, strategy, symbol='BTC/JPY', amount=0.001, sl_pct=None, tp_pct=None, trailing_pct=None, test_mode=True):
        """
        ライブ取引ボット
        strategy: Strategyオブジェクト
        symbol: 取引ペア
        amount: 1回の注文量 (BTC)
        sl_pct, tp_pct, trailing_pct: リスク管理設定
        test_mode: Trueなら実際に注文を出さずにログのみ出力
        """
        self.strategy = strategy
        self.symbol = symbol
        self.amount = amount
        self.sl_pct = sl_pct
        self.tp_pct = tp_pct
        self.trailing_pct = trailing_pct
        self.test_mode = test_mode
        
        # API設定
        api_key = os.environ.get('BITBANK_API_KEY')
        api_secret = os.environ.get('BITBANK_API_SECRET')
        
        if not api_key or not api_secret:
            if not test_mode:
                print("エラー: 環境変数 BITBANK_API_KEY, BITBANK_API_SECRET が設定されていません。")
                sys.exit(1)
            else:
                print("警告: APIキーが見つかりません。テストモード(ReadOnly)で動作します。")
        
        self.exchange = ccxt.bitbank({
            'apiKey': api_key,
            'secret': api_secret,
        })
        
        
        # 状態管理
        self.position = None # None or {'amount': 0.001, 'entry_price': 5000000}
        self.highest_price = 0.0 # トレーリングストップ用

        # 仮想取引（Paper Trading）用の残高
        self.virtual_balance = 1000000.0 # 100万円スタート
        self.virtual_btc = 0.0
        self.total_profit = 0.0
        
    def fetch_recent_data(self, limit=500):
        """
        最新のOHLCVデータを取得
        """
        try:
            # 1h足で判定
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe='1h', limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"データ取得エラー: {e}")
            return None

    def execute_order(self, side, price=None):
        """
        注文実行
        side: 'buy' or 'sell'
        price: Noneなら成行、値があれば指値（今回は成行メイン）
        """
        current_price = price if price else self.get_current_price()

        if self.test_mode:
            # Paper Trading Logic
            if side == 'buy':
                cost = current_price * self.amount
                if self.virtual_balance >= cost:
                    self.virtual_balance -= cost
                    self.virtual_btc += self.amount
                    print(f"[TEST] 仮想買い注文: {self.amount} BTC @ {current_price:,.0f} JPY")
                    print(f"       残高: {self.virtual_balance:,.0f} JPY, 保有BTC: {self.virtual_btc:.4f}")
                else:
                    print(f"[TEST] 資金不足で仮想買い注文スキップ: 必要 {cost:,.0f} > 残高 {self.virtual_balance:,.0f}")
                    return None
            
            elif side == 'sell':
                revenue = current_price * self.amount
                if self.virtual_btc >= self.amount * 0.99: # 誤差許容
                    self.virtual_balance += revenue
                    self.virtual_btc -= self.amount
                    
                    # 利益計算（簡易）
                    if self.position:
                        entry = self.position['entry_price']
                        pnl = (current_price - entry) * self.amount
                        self.total_profit += pnl
                        print(f"[TEST] 仮想売り注文: {self.amount} BTC @ {current_price:,.0f} JPY (損益: {pnl:+,.0f} JPY)")
                    else:
                        print(f"[TEST] 仮想売り注文: {self.amount} BTC @ {current_price:,.0f} JPY")
                        
                    print(f"       残高: {self.virtual_balance:,.0f} JPY, 保有BTC: {self.virtual_btc:.4f}")
                    print(f"       総損益: {self.total_profit:+,.0f} JPY")
                else:
                    print("[TEST] BTC不足で仮想売り注文スキップ")
                    return None

            return {'price': current_price, 'amount': self.amount}
        
        try:
            # 成行注文
            order = self.exchange.create_market_order(self.symbol, side, self.amount)
            print(f"注文成功: {order}")
            # 約定価格を取得したいが、成行は即時約定とは限らないため、簡易的に現在価格等を返す
            # 実運用では fetch_order で確認が必要
            return {'price': self.get_current_price(), 'amount': self.amount}
        except Exception as e:
            print(f"注文エラー: {e}")
            return None

    def get_current_price(self):
        ticker = self.exchange.fetch_ticker(self.symbol)
        return ticker['last']

    def check_risk_management(self, current_price):
        """
        リスク管理判定（SL/TP/Trailing）
        返り値: True if exited, False otherwise
        """
        if self.position is None:
            return False
            
        entry_price = self.position['entry_price']
        
        # トレーリングストップ用の高値更新
        if current_price > self.highest_price:
            self.highest_price = current_price
            
        # 1. Stop Loss
        if self.sl_pct:
            sl_price = entry_price * (1.0 - self.sl_pct)
            if current_price <= sl_price:
                print(f"損切りトリガー: 現在 {current_price} <= SL {sl_price}")
                self.execute_order('sell', current_price) # 価格を渡す
                self.position = None
                return True
                
        # 2. Take Profit
        if self.tp_pct:
            tp_price = entry_price * (1.0 + self.tp_pct)
            if current_price >= tp_price:
                print(f"利確トリガー: 現在 {current_price} >= TP {tp_price}")
                self.execute_order('sell', current_price) 
                self.position = None
                return True
                
        # 3. Trailing Stop
        if self.trailing_pct:
            ts_price = self.highest_price * (1.0 - self.trailing_pct)
            if current_price <= ts_price:
                print(f"トレーリングストップトリガー: 現在 {current_price} <= TS {ts_price} (最高値 {self.highest_price})")
                self.execute_order('sell', current_price)
                self.position = None
                return True
                
        return False

    def run(self, interval_sec=60):
        print(f"ライブ取引開始 ({self.symbol}) - テストモード: {self.test_mode}")
        if self.test_mode:
            print(f"仮想残高スタート: {self.virtual_balance:,.0f} JPY")
            
        print(f"戦略: {self.strategy.__class__.__name__}")
        print("Ctrl+C で停止します...")
        
        while True:
            try:
                # 現在価格取得 & リスク管理チェック（高頻度でやってもいいが、ここではループ毎）
                current_price = self.get_current_price()
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 現在価格: {current_price} JPY")
                
                if self.test_mode:
                    # 含み損益表示
                    if self.position:
                        unrealized_pnl = (current_price - self.position['entry_price']) * self.amount
                        print(f"状態: ポジション保有中 (含み損益: {unrealized_pnl:+,.0f} JPY)")
                    else:
                        print("状態: ノーポジション")

                if self.check_risk_management(current_price):
                    print("決済完了。次のチャンスを待ちます。")
                    time.sleep(interval_sec)
                    continue

                # 戦略判定用のデータ取得
                df = self.fetch_recent_data()
                if df is None:
                    time.sleep(10)
                    continue
                
                # シグナル生成
                signals = self.strategy.generate_signals(df)
                latest_signal = signals.iloc[-1]['signal']
                
                # エントリー判定
                if latest_signal == 1.0 and self.position is None:
                    print("買いシグナル点灯！")
                    res = self.execute_order('buy', current_price)
                    if res:
                        self.position = {'amount': self.amount, 'entry_price': res['price']}
                        self.highest_price = res['price']
                        
                elif latest_signal == -1.0 and self.position is not None:
                    print("売りシグナル点灯！")
                    self.execute_order('sell', current_price)
                    self.position = None
                
                else:
                    if not self.test_mode: # Test mode already prints status above
                        if self.position:
                            print(f"ポジション保有中 (取得: {self.position['entry_price']}) - 異常なし")
                        else:
                            print("シグナルなし - 待機中")

                time.sleep(interval_sec)
                
            except KeyboardInterrupt:
                print("\n停止しました。")
                if self.test_mode:
                    print(f"最終仮想残高: {self.virtual_balance:,.0f} JPY")
                    print(f"総損益: {self.total_profit:+,.0f} JPY")
                break
            except Exception as e:
                print(f"エラー発生: {e}")
                time.sleep(30)
