import sys
from data_loader import fetch_data, save_to_csv
from strategy import SmaStrategy, MacdStrategy, DonchianStrategy, GridStrategy
from backtest import Backtest
import pandas as pd
import os

def main():
    print("=== 仮想通貨取引ボット (Bitbank) ===")
    print("1. 過去データの取得")
    print("2. バックテストの実行")
    print("3. ライブ自動取引 [NEW!]")
    
    choice = input("選択してください (1-3): ")

    if choice == '1':
        print("\n--- データ取得モード ---")
        days = input("取得する日数（例: 30）: ")
        try:
            days = int(days)
            # 1日24時間なので、24 * days 分のデータを取得
            # Bitbankの1時間足
            limit = days * 24
            df = fetch_data(limit=limit)
            save_to_csv(df)
        except ValueError:
            print("数値を入力してください。")

    elif choice == '2':
        print("\n--- バックテストモード ---")
        if not os.path.exists('market_data.csv'):
            print("エラー: market_data.csv が見つかりません。先にオプション1でデータを取得してください。")
            return

        # データの読み込み
        df = pd.read_csv('market_data.csv')
        df['timestamp'] = pd.to_datetime(df['timestamp']) # これがないとエラーになる可能性あり
        
        print(f"データ読み込み完了: {len(df)} 件")

        print("\n--- 戦略の選択 ---")
        print("1. 単純移動平均 (SMA) - 基本的")
        print("2. MACD + フィルター - 実践的")
        print("3. ドンチャン・ブレイクアウト - トレンドフォロー")
        print("4. レンジグリッド (Range Grid) - レンジ相場特化 [NEW!]")
        
        strat_choice = input("戦略番号を選択してください (1-4): ")
        
        if strat_choice == '1':
            print("SMA戦略を選択しました。")
            short = int(input("短期期間 (default: 5): ") or 5)
            long = int(input("長期期間 (default: 20): ") or 20)
            strategy = SmaStrategy(short_window=short, long_window=long)
            signals = strategy.generate_signals(df)
            
        elif strat_choice == '2':
            print("MACD戦略(EMA200+RSIフィルター付)を選択しました。")
            strategy = MacdStrategy()
            signals = strategy.generate_signals(df)
            
        elif strat_choice == '3':
            print("ドンチャン・ブレイクアウト戦略を選択しました。")
            window = int(input("期間 (default: 20): ") or 20)
            
            print("--- ATRフィルター設定 ---")
            use_atr = input("ATRフィルターを使いますか？ (y/n, default: n): ")
            if use_atr.lower() == 'y':
                atr_thres = float(input("ATR閾値% (例: 0.5 = 0.5%以上の変動でエントリー): ") or 0.5)
                strategy = DonchianStrategy(window=window, use_atr_filter=True, atr_threshold=atr_thres/100.0)
            else:
                strategy = DonchianStrategy(window=window, use_atr_filter=False)
                
            signals = strategy.generate_signals(df)
            
        elif strat_choice == '4':
            print("レンジグリッド戦略を選択しました。")
            
            # レンジの自動設定（データの過去30日間の安値・高値を目安にするなどの提案があればいいが、ここは手動入力）
            # デフォルトはデータの最小・最大
            default_min = df['low'].min()
            default_max = df['high'].max()
            print(f"データの範囲: {default_min:,.0f} - {default_max:,.0f} JPY")
            
            r_min = float(input(f"レンジ下限 (default: {default_min:.0f}): ") or default_min)
            r_max = float(input(f"レンジ上限 (default: {default_max:.0f}): ") or default_max)
            grids = int(input("グリッド本数 (default: 50): ") or 50)
            amount = float(input("1グリッドあたりの注文量(BTC) (default: 0.01): ") or 0.01)
            
            use_ema = input("EMA200フィルターを使いますか？ (y/n, default: y): ")
            use_ema = False if use_ema.lower() == 'n' else True
            
            from strategy import GridStrategy # 遅延インポートまたは上部に追加
            strategy = GridStrategy(range_min=r_min, range_max=r_max, grid_num=grids, amount_per_grid=amount, use_ema_filter=use_ema)
            signals = None # Gridはsignalsを使わない
            
        else:
            print("無効な選択です。SMA(5,20)を使用します。")
            strategy = SmaStrategy()
            signals = strategy.generate_signals(df)

        # リスク管理設定（グリッド以外で有効）
        sl_pct = None
        tp_pct = None
        trailing_pct = None
        
        if strat_choice in ['1', '2', '3']:
            print("\n--- リスク管理設定 (オプション) ---")
            sl_input = input("損切り(Stop Loss) % (Enterで無し): ")
            if sl_input:
                sl_pct = float(sl_input) / 100.0
            
            tp_input = input("利確(Take Profit) % (Enterで無し): ")
            if tp_input:
                tp_pct = float(tp_input) / 100.0

            # TPとTrailingは併用可能

            ts_input = input("トレーリングストップ % (Enterで無し): ")
            if ts_input:
                trailing_pct = float(ts_input) / 100.0

        # バックテストの実行
        backtest = Backtest(initial_balance=1000000)
        backtest.run(df, strategy, sl_pct=sl_pct, tp_pct=tp_pct, trailing_pct=trailing_pct)

    elif choice == '3':
        print("\n--- ライブ自動取引モード ---")
        print("注意: 実際にBitbankのAPIを使用して取引を行います。")
        print("APIキーは環境変数 BITBANK_API_KEY, BITBANK_API_SECRET から読み込まれます。")
        
        # モード選択
        is_test = input("テストモード(注文を出さずログのみ)で実行しますか？ (y/n, default: y): ")
        test_mode = True if is_test.lower() != 'n' else False
        
        # 戦略選択（バックテストと同じフロー）
        print("\n--- 戦略の選択 ---")
        print("1. 単純移動平均 (SMA)")
        print("2. MACD + フィルター")
        print("3. ドンチャン・ブレイクアウト [推奨]")
        print("4. レンジグリッド [未対応]")
        
        strat_choice = input("戦略番号を選択してください (1-3): ")
        
        strategy = None
        if strat_choice == '1':
            short = int(input("短期期間 (default: 5): ") or 5)
            long = int(input("長期期間 (default: 20): ") or 20)
            strategy = SmaStrategy(short_window=short, long_window=long)
        elif strat_choice == '2':
            strategy = MacdStrategy()
        elif strat_choice == '3':
            window = int(input("期間 (default: 240): ") or 240)
            use_atr = input("ATRフィルターを使いますか？ (y/n, default: y): ")
            if use_atr.lower() != 'n':
                atr_thres = float(input("ATR閾値% (default: 0.3): ") or 0.3)
                strategy = DonchianStrategy(window=window, use_atr_filter=True, atr_threshold=atr_thres/100.0)
            else:
                strategy = DonchianStrategy(window=window, use_atr_filter=False)
        else:
            print("無効な選択、またはGrid戦略はライブ取引未対応です。")
            return

        # リスク管理
        print("\n--- リスク管理設定 ---")
        sl_pct = None
        tp_pct = None
        trailing_pct = None
        
        sl_input = input("損切り(Stop Loss) % (Enterで無し): ")
        if sl_input: sl_pct = float(sl_input) / 100.0
        
        tp_input = input("利確(Take Profit) % (Enterで無し): ")
        if tp_input: tp_pct = float(tp_input) / 100.0
        
        ts_input = input("トレーリングストップ % (Enterで無し): ")
        if ts_input: trailing_pct = float(ts_input) / 100.0
        
        amount = float(input("1回の注文数量(BTC) (default: 0.001): ") or 0.001)

        # 実行
        from live_trader import LiveTrader
        trader = LiveTrader(strategy, amount=amount, sl_pct=sl_pct, tp_pct=tp_pct, trailing_pct=trailing_pct, test_mode=test_mode)
        trader.run()

    else:
        print("無効な選択です。")

if __name__ == "__main__":
    main()
