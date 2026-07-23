"""获取 1m~1h 各周期近一年 K 线数据，分页拉取导出为 CSV。"""
import asyncio
import csv
import os
import time
from datetime import datetime, timezone

import ccxt.pro as ccxt

SYMBOLS = ["BTC/USDT","ETH/USDT", "SOL/USDT"]
TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h"]
CHUNK = 1000
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "warmup")

TF_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000,
    "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000,
}

YEAR_MS = 365 * 24 * 3600 * 1000


def write_csv(filepath: str, rows: list):
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "datetime", "open", "high", "low", "close", "volume"])
        for row in rows:
            ts = row[0]
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([ts, dt, row[1], row[2], row[3], row[4], row[5]])


async def fetch_one_tf(exchange, symbol: str, tf: str) -> list:
    since_ms = int((time.time() * 1000) - YEAR_MS)
    tf_ms = TF_MS[tf]
    all_rows = []
    page = 0

    while True:
        page += 1
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, tf, since=since_ms, limit=CHUNK)
        except Exception as e:
            print(f"    请求失败 (page={page}): {e}，等 2s 重试...")
            await asyncio.sleep(2)
            try:
                ohlcv = await exchange.fetch_ohlcv(symbol, tf, since=since_ms, limit=CHUNK)
            except Exception as e2:
                print(f"    重试仍失败: {e2}，停止")
                break

        if not ohlcv:
            break

        all_rows.extend(ohlcv)

        first_dt = datetime.fromtimestamp(ohlcv[0][0] / 1000, tz=timezone.utc)
        last_dt = datetime.fromtimestamp(ohlcv[-1][0] / 1000, tz=timezone.utc)
        print(f"    page {page:>4d} | {len(ohlcv):>4d} 条 | {first_dt} ~ {last_dt} | 累计 {len(all_rows):>7d}")

        since_ms = ohlcv[-1][0] + tf_ms

        if len(ohlcv) < CHUNK:
            break

        await asyncio.sleep(0.15)

    return all_rows


async def main():
    exchange = ccxt.binance({"options": {"defaultType": "spot"}})
    exchange.set_sandbox_mode(True)

    os.makedirs(OUT_DIR, exist_ok=True)

    for symbol in SYMBOLS:
        compact = symbol.replace("/", "_")
        for tf in TIMEFRAMES:
            print(f"\n{'='*60}")
            print(f"获取 {symbol} {tf}（近一年，每次 {CHUNK} 条）")
            print(f"{'='*60}")

            rows = await fetch_one_tf(exchange, symbol, tf)

            if not rows:
                print(f"  无数据，跳过")
                continue

            filepath = os.path.join(OUT_DIR, f"{compact}_{tf}.csv")
            write_csv(filepath, rows)

            first_dt = datetime.fromtimestamp(rows[0][0] / 1000, tz=timezone.utc)
            last_dt = datetime.fromtimestamp(rows[-1][0] / 1000, tz=timezone.utc)
            print(f"  已保存 {len(rows)} 条 | {first_dt} ~ {last_dt} → {filepath}")

    await exchange.close()
    print("\n完成。")


if __name__ == "__main__":
    asyncio.run(main())
