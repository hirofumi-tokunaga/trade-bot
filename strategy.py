import pandas as pd

class Strategy:
    """
    戦略の基底クラス（インターフェース）
    """
    def generate_signals(self, df):
        raise NotImplementedError("Subclasses should implement this!")

class SmaStrategy(Strategy):
    def __init__(self, short_window=5, long_window=20):
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, df):
        signals = pd.DataFrame(index=df.index)
        signals['signal'] = 0.0
        signals['short_mavg'] = df['close'].rolling(window=self.short_window, min_periods=1).mean()
        signals['long_mavg'] = df['close'].rolling(window=self.long_window, min_periods=1).mean()

        current_bullish = signals['short_mavg'] > signals['long_mavg']
        prev_bullish = signals['short_mavg'].shift(1) <= signals['long_mavg'].shift(1)
        signals.loc[current_bullish & prev_bullish, 'signal'] = 1.0

        current_bearish = signals['short_mavg'] < signals['long_mavg']
        prev_bearish = signals['short_mavg'].shift(1) >= signals['long_mavg'].shift(1)
        signals.loc[current_bearish & prev_bearish, 'signal'] = -1.0
        return signals

class MacdStrategy(Strategy):
    def __init__(self, fast_period=12, slow_period=26, signal_period=9):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def generate_signals(self, df):
        signals = pd.DataFrame(index=df.index)
        signals['signal'] = 0.0

        ema_fast = df['close'].ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.slow_period, adjust=False).mean()
        signals['macd'] = ema_fast - ema_slow
        signals['signal_line'] = signals['macd'].ewm(span=self.signal_period, adjust=False).mean()
        
        # トレンドフィルター (EMA200)
        signals['ema200'] = df['close'].ewm(span=200, adjust=False, min_periods=200).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        signals['rsi'] = 100 - (100 / (1 + rs))

        # ゴールデンクロス + フィルター
        macd_cross_up = (signals['macd'] > signals['signal_line']) & \
                        (signals['macd'].shift(1) <= signals['signal_line'].shift(1))
        
        # フィルター: 上昇トレンド中(価格>EMA200) かつ 加熱していない(RSI<70)
        buy_condition = macd_cross_up & \
                        (df['close'] > signals['ema200']) & \
                        (signals['rsi'] < 70)
        
        signals.loc[buy_condition, 'signal'] = 1.0

        # デッドクロス（手仕舞い）
        macd_cross_down = (signals['macd'] < signals['signal_line']) & \
                          (signals['macd'].shift(1) >= signals['signal_line'].shift(1))
        
        signals.loc[macd_cross_down, 'signal'] = -1.0
        return signals

class DonchianStrategy(Strategy):
    def __init__(self, window=20, use_atr_filter=True, atr_period=14, atr_threshold=0.0):
        """
        ドンチャン・ブレイクアウト戦略
        window: チャネル期間
        use_atr_filter: ATRによるボラティリティフィルターを使うか
        atr_period: ATRの計算期間
        atr_threshold: ATRがこの値(価格に対する比率%)以下なら取引しない（低ボラティリティ回避）
                        例: 0.01 なら ATR/Close < 1% の時はエントリーしない
        """
        self.window = window
        self.use_atr_filter = use_atr_filter
        self.atr_period = atr_period
        self.atr_threshold = atr_threshold

    def generate_signals(self, df):
        signals = pd.DataFrame(index=df.index)
        signals['signal'] = 0.0
        
        # ドンチャンチャネル
        signals['high_channel'] = df['high'].rolling(window=self.window).max().shift(1)
        signals['low_channel'] = df['low'].rolling(window=self.window).min().shift(1)

        buy_signal = df['high'] > signals['high_channel']
        sell_signal = df['low'] < signals['low_channel']
        
        # ATRフィルター
        if self.use_atr_filter:
            # ATR計算: TR = Max(H-L, |H-Cp|, |L-Cp|)
            prev_close = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_close).abs()
            tr3 = (df['low'] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=self.atr_period).mean()
            
            # ATR比率 (ATR / Close)
            atr_ratio = atr / df['close']
            
            # フィルター条件: ATR比率が閾値以上であること（動きがある時のみ）
            volatility_ok = atr_ratio > self.atr_threshold
            
            buy_signal = buy_signal & volatility_ok
            sell_signal = sell_signal & volatility_ok

        signals.loc[buy_signal, 'signal'] = 1.0
        signals.loc[sell_signal, 'signal'] = -1.0
        return signals

class GridStrategy(Strategy):
    def __init__(self, range_min, range_max, grid_num=10, amount_per_grid=0.001, use_ema_filter=True):
        """
        グリッド戦略 (Range Grid)
        range_min: レンジ下限
        range_max: レンジ上限
        grid_num: グリッド数
        amount_per_grid: 1グリッドあたりの注文量(BTC)
        use_ema_filter: EMA200より上の時のみ買い注文を出すか
        """
        self.is_grid = True # Backtest側で識別するためのフラグ
        self.range_min = range_min
        self.range_max = range_max
        self.grid_num = grid_num
        self.amount_per_grid = amount_per_grid
        self.use_ema_filter = use_ema_filter
        
        # グリッドの作成
        # 等間隔に価格を設定
        step = (range_max - range_min) / grid_num
        self.grids = [range_min + i * step for i in range(grid_num + 1)]
        
        # 各グリッドの状態管理 (True: ポジション保有中=売り注文待機, False: ポジションなし=買い注文待機)
        # 初期状態は現在価格より上はFalse(買い待ち)、下はTrue(売り待ち)... ではなく、
        # バックテスト開始時はノーポジなので、現在価格より下のグリッドにBuyer指値を置く
        self.grid_status = [False] * len(self.grids)
        
        self.ema200 = None

    def setup(self, df):
        """
        バックテスト開始時の初期化
        """
        # EMA200の計算
        if self.use_ema_filter:
            self.ema200 = df['close'].ewm(span=200, adjust=False, min_periods=200).mean()
        else:
            self.ema200 = None
        
        # 時刻索引参照用
        self.current_idx = 0

    def check_execution(self, high, low, timestamp):
        """
        高値・安値を受け取り、約定した注文を返す
        """
        executions = []
        
        # EMA値の取得
        current_ema = 0
        if self.use_ema_filter and self.ema200 is not None:
             # timestampで検索するか、indexでやるか。簡単のためindexマッチングと仮定したいが
             # Backtest側で row を渡してもらうのが確実。
             try:
                 current_ema = self.ema200.loc[timestamp]
             except:
                 pass # データがない場合など
        
        # グリッドの走査
        for i, price in enumerate(self.grids):
            
            # 1. 買い注文の判定
            if not self.grid_status[i]:
                if low <= price: # ヒット
                    # フィルターチェック: 価格(指値) > EMA200 の場合のみ買う (上昇トレンド中の押し目買い)
                    # または 現在価格 > EMA200
                    if self.use_ema_filter:
                        # 指値価格がEMAより下なら買わない＝「トレンドに逆らわない」
                        # 「価格がEMA200より上のときだけロング」
                        if price < current_ema:
                            continue 
                            
                    executions.append({'type': 'BUY', 'price': price, 'amount': self.amount_per_grid})
                    self.grid_status[i] = True 
            
            # 2. 売り注文の判定
            else:
                if i + 1 < len(self.grids):
                    sell_price = self.grids[i+1]
                    if high >= sell_price:
                        executions.append({'type': 'SELL', 'price': sell_price, 'amount': self.amount_per_grid})
                        self.grid_status[i] = False

        return executions
