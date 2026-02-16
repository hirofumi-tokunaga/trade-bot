import sys
import os
import pandas as pd

from data_loader import fetch_data, save_to_csv
from strategy import SmaStrategy, MacdStrategy, DonchianStrategy, GridStrategy
from backtest import Backtest


def _input_int(prompt, default):
    return int(input(prompt) or default)


def _input_float(prompt, default):
    return float(input(prompt) or default)


def _parse_risk_inputs(strat_choice):
    """
    Donchian(3)のみ、空Enter時に最適化済みデフォルト(5/15/5)を適用。
    それ以外は空Enterで無効(None)。
    """
    sl_pct = None
    tp_pct = None
    trailing_pct = None

    sl_default = "5" if strat_choice == "3" else ""
    tp_default = "15" if strat_choice == "3" else ""
    ts_default = "5" if strat_choice == "3" else ""

    sl_label = "損切り(Stop Loss) % "
    tp_label = "利確(Take Profit) % "
    ts_label = "トレーリングストップ % "

    sl_prompt = f"{sl_label}(Enterで無し"
    tp_prompt = f"{tp_label}(Enterで無し"
    ts_prompt = f"{ts_label}(Enterで無し"

    if strat_choice == "3":
        sl_prompt += ", default: 5"
        tp_prompt += ", default: 15"
        ts_prompt += ", default: 5"

    sl_prompt += "): "
    tp_prompt += "): "
    ts_prompt += "): "

    sl_input = input(sl_prompt) or sl_default
    if sl_input:
        sl_pct = float(sl_input) / 100.0

    tp_input = input(tp_prompt) or tp_default
    if tp_input:
        tp_pct = float(tp_input) / 100.0

    ts_input = input(ts_prompt) or ts_default
    if ts_input:
        trailing_pct = float(ts_input) / 100.0

    return sl_pct, tp_pct, trailing_pct


def run_fetch_data():
    print("\n--- データ取得モード ---")
    days = input("取得する日数 (例: 30): ")
    try:
        days = int(days)
        limit = days * 24  # 1h足
        df = fetch_data(limit=limit)
        save_to_csv(df)
    except ValueError:
        print("数値を入力してください。")


def run_backtest_mode():
    print("\n--- バックテストモード ---")
    if not os.path.exists("market_data.csv"):
        print("エラー: market_data.csv が見つかりません。先にデータ取得を実行してください。")
        return

    df = pd.read_csv("market_data.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    print(f"データ行数: {len(df)}")
    print("\n--- 戦略の選択 ---")
    print("1. 単純移動平均クロス (SMA)")
    print("2. MACD + フィルター")
    print("3. ドンチャン・ブレイクアウト")
    print("4. レンジグリッド")

    strat_choice = input("戦略番号を入力 (1-4): ")

    if strat_choice == "1":
        short = _input_int("短期期間 (default: 5): ", 5)
        long = _input_int("長期期間 (default: 20): ", 20)
        strategy = SmaStrategy(short_window=short, long_window=long)
    elif strat_choice == "2":
        strategy = MacdStrategy()
    elif strat_choice == "3":
        # Profit-positive defaults from optimization
        window = _input_int("期間 (default: 240): ", 240)
        use_atr = input("ATRフィルターを使いますか？ (y/n, default: y): ")
        if use_atr.lower() == "n":
            strategy = DonchianStrategy(window=window, use_atr_filter=False)
        else:
            atr_thres = _input_float("ATR閾値% (default: 0.3): ", 0.3)
            strategy = DonchianStrategy(window=window, use_atr_filter=True, atr_threshold=atr_thres / 100.0)
    elif strat_choice == "4":
        default_min = float(df["low"].min())
        default_max = float(df["high"].max())
        print(f"データ範囲: {default_min:,.0f} - {default_max:,.0f} JPY")

        r_min = _input_float(f"レンジ下限 (default: {default_min:.0f}): ", default_min)
        r_max = _input_float(f"レンジ上限 (default: {default_max:.0f}): ", default_max)
        grids = _input_int("グリッド本数 (default: 50): ", 50)
        amount = _input_float("1グリッドあたりの数量(BTC) (default: 0.01): ", 0.01)

        use_ema = input("EMA200フィルターを使いますか？ (y/n, default: y): ")
        use_ema = False if use_ema.lower() == "n" else True

        strategy = GridStrategy(
            range_min=r_min,
            range_max=r_max,
            grid_num=grids,
            amount_per_grid=amount,
            use_ema_filter=use_ema,
        )
    else:
        print("不正な選択です。SMA(5,20)を使用します。")
        strategy = SmaStrategy()
        strat_choice = "1"

    sl_pct = None
    tp_pct = None
    trailing_pct = None
    if strat_choice in ["1", "2", "3"]:
        print("\n--- リスク管理設定 ---")
        sl_pct, tp_pct, trailing_pct = _parse_risk_inputs(strat_choice)

    backtest = Backtest(initial_balance=1_000_000)
    backtest.run(df, strategy, sl_pct=sl_pct, tp_pct=tp_pct, trailing_pct=trailing_pct)


def run_live_mode():
    print("\n--- ライブ運用モード ---")
    print("注意: テストモードでは注文を出さず、内部残高のみ更新します。")

    is_test = input("テストモードで実行しますか？ (y/n, default: y): ")
    test_mode = False if is_test.lower() == "n" else True

    print("\n--- 戦略の選択 ---")
    print("1. 単純移動平均クロス (SMA)")
    print("2. MACD + フィルター")
    print("3. ドンチャン・ブレイクアウト")

    strat_choice = input("戦略番号を入力 (1-3): ")

    strategy = None
    if strat_choice == "1":
        short = _input_int("短期期間 (default: 5): ", 5)
        long = _input_int("長期期間 (default: 20): ", 20)
        strategy = SmaStrategy(short_window=short, long_window=long)
    elif strat_choice == "2":
        strategy = MacdStrategy()
    elif strat_choice == "3":
        # Profit-positive defaults from optimization
        window = _input_int("期間 (default: 240): ", 240)
        use_atr = input("ATRフィルターを使いますか？ (y/n, default: y): ")
        if use_atr.lower() == "n":
            strategy = DonchianStrategy(window=window, use_atr_filter=False)
        else:
            atr_thres = _input_float("ATR閾値% (default: 0.3): ", 0.3)
            strategy = DonchianStrategy(window=window, use_atr_filter=True, atr_threshold=atr_thres / 100.0)
    else:
        print("不正な選択です。終了します。")
        return

    print("\n--- リスク管理設定 ---")
    sl_pct, tp_pct, trailing_pct = _parse_risk_inputs(strat_choice)

    amount = _input_float("1回の注文数量(BTC) (default: 0.001): ", 0.001)

    from live_trader import LiveTrader

    trader = LiveTrader(
        strategy,
        amount=amount,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        trailing_pct=trailing_pct,
        test_mode=test_mode,
    )
    trader.run()


def main():
    print("=== 自動売買ツール (Bitbank) ===")
    print("1. データ取得")
    print("2. バックテスト")
    print("3. ライブ運用")

    choice = input("番号を選択 (1-3): ")

    if choice == "1":
        run_fetch_data()
    elif choice == "2":
        run_backtest_mode()
    elif choice == "3":
        run_live_mode()
    else:
        print("不正な選択です。")


if __name__ == "__main__":
    main()
