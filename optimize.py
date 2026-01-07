import pandas as pd
import itertools
from backtest import Backtest
from strategy import DonchianStrategy, GridStrategy
import sys

def load_data():
    try:
        df = pd.read_csv('market_data.csv')
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except FileNotFoundError:
        print("market_data.csv not found.")
        sys.exit(1)

def optimize_donchian(df):
    print("\n--- Donchian Strategy Optimization ---")
    
    # Parameter Grid
    # 1h足なので、240(10日), 480(20日), 960(40日), 1440(60日) をテスト
    windows = [120, 240, 480, 960] 
    atr_thresholds = [0.003, 0.005, 0.01] # 0.3%, 0.5%, 1%
    sl_pcts = [0.03, 0.05, 0.08] # 3%, 5%, 8%
    tp_pcts = [0.05, 0.10, 0.15] # 5%, 10%, 15%
    trailing_pcts = [0.03, 0.05] # 3%, 5%
    
    results = []
    
    # Generate all combinations
    combinations = list(itertools.product(windows, atr_thresholds, sl_pcts, tp_pcts, trailing_pcts))
    total_combs = len(combinations)
    print(f"Testing {total_combs} combinations...")
    
    for i, (window, atr_thres, sl, tp, trailing) in enumerate(combinations):
        if i % 50 == 0:
            print(f"Progress: {i}/{total_combs}")
            
        use_atr = True if atr_thres > 0 else False
        strategy = DonchianStrategy(window=window, use_atr_filter=use_atr, atr_threshold=atr_thres)
        
        backtest = Backtest(initial_balance=1000000)
        # Suppress output during optimization
        sys.stdout = open('/dev/null', 'w')
        portfolio, trade_log = backtest.run(df, strategy, sl_pct=sl, tp_pct=tp, trailing_pct=trailing)
        sys.stdout = sys.__stdout__
        
        final_val = portfolio[-1] if portfolio else 1000000
        profit = final_val - 1000000
        max_dd = backtest.calculate_drawdown(portfolio)
        
        results.append({
            'window': window,
            'atr': atr_thres,
            'sl': sl,
            'tp': tp,
            'trailing': trailing,
            'profit': profit,
            'max_dd': max_dd,
            'trades': len(trade_log)
        })
        
    # Sort by profit
    sorted_results = sorted(results, key=lambda x: x['profit'], reverse=True)
    
    print("\nTop 3 Donchian Settings:")
    for rank, res in enumerate(sorted_results[:3], 1):
        print(f"{rank}. Profit: {res['profit']:,.0f} JPY, MaxDD: {res['max_dd']:.2f}%, Trades: {res['trades']}")
        print(f"   Params: Window={res['window']}, ATR={res['atr']*100}%, SL={res['sl']}, TP={res['tp']}, Trailing={res['trailing']}")

def optimize_grid(df):
    print("\n--- Grid Strategy Optimization ---")
    
    r_min = df['low'].min()
    r_max = df['high'].max()
    print(f"Range: {r_min} - {r_max}")
    
    grid_nums = [20, 50, 100]
    use_emas = [True, False]
    
    results = []
    
    combinations = list(itertools.product(grid_nums, use_emas))
    
    for grid_num, use_ema in combinations:
        strategy = GridStrategy(range_min=r_min, range_max=r_max, grid_num=grid_num, amount_per_grid=0.01, use_ema_filter=use_ema)
        
        backtest = Backtest(initial_balance=1000000)
        sys.stdout = open('/dev/null', 'w')
        portfolio, trade_log = backtest.run(df, strategy)
        sys.stdout = sys.__stdout__
        
        final_val = portfolio[-1] if portfolio else 1000000
        profit = final_val - 1000000
        max_dd = backtest.calculate_drawdown(portfolio)
        
        results.append({
            'grids': grid_num,
            'ema': use_ema,
            'profit': profit,
            'max_dd': max_dd,
            'trades': len(trade_log)
        })
        
    sorted_results = sorted(results, key=lambda x: x['profit'], reverse=True)
    
    print("\nTop 3 Grid Settings:")
    for rank, res in enumerate(sorted_results[:3], 1):
        print(f"{rank}. Profit: {res['profit']:,.0f} JPY, MaxDD: {res['max_dd']:.2f}%, Trades: {res['trades']}")
        print(f"   Params: Grids={res['grids']}, EMA Filter={res['ema']}")

if __name__ == "__main__":
    df = load_data()
    optimize_donchian(df)
    optimize_grid(df)
