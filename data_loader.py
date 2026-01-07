import ccxt
import pandas as pd
import time
from datetime import datetime

def fetch_data(symbol='BTC/JPY', timeframe='1h', limit=100):
    """
    Bitbankからローソク足データを取得してDataFrameとして返す関数
    """
    print(f"{symbol} のデータを {timeframe} 足で {limit} 件取得中...")
    
    # Bitbankのクライアントを作成
    bitbank = ccxt.bitbank()
    
    # 期間計算 (ミリ秒)
    # 1h = 60 * 60 * 1000 ms
    timeframe_duration_ms = 60 * 60 * 1000
    if timeframe == '1d':
        timeframe_duration_ms = 24 * 60 * 60 * 1000
    
    # 開始時刻の計算
    since = bitbank.milliseconds() - (limit * timeframe_duration_ms)
    
    all_ohlcv = []
    
    try:
        while len(all_ohlcv) < limit:
            remaining = limit - len(all_ohlcv)
            # 一度のリクエストで多すぎるとエラーになる可能性があるため、適度な数（例えば100）にするか、
            # ccxtのデフォルトに任せる。ここではsinceを指定して取得する。
            
            ohlcv = bitbank.fetch_ohlcv(symbol, timeframe, since=since, limit=remaining)
            
            if len(ohlcv) == 0:
                print("これ以上のデータがありません。")
                break
                
            all_ohlcv += ohlcv
            
            # 次の取得開始時刻を更新 (最後のデータの時間 + 1期間)
            last_timestamp = ohlcv[-1][0]
            since = last_timestamp + timeframe_duration_ms
            
            print(f"取得済み: {len(all_ohlcv)} / {limit} 件")
            
            # API制限考慮
            time.sleep(0.1)
        
        # 必要な数だけ切り出す
        all_ohlcv = all_ohlcv[:limit]
        
        # DataFrameに変換
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # タイムスタンプを読みやすい形式に変換
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        print("データ取得完了。")
        return df
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        return None

def save_to_csv(df, filename='market_data.csv'):
    """
    DataFrameをCSVファイルに保存する関数
    """
    if df is not None:
        df.to_csv(filename, index=False)
        print(f"データを {filename} に保存しました。")
    else:
        print("保存するデータがありません。")

if __name__ == "__main__":
    # テスト実行用
    # 半年分くらいの日足データを取得してみる (30日 * 6 = 180)
    data = fetch_data(limit=180)
    save_to_csv(data)
