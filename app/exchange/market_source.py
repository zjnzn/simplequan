"""MarketSource —— 真实行情数据源（ccxt REST 轮询）。

走 REST 轮询而非 ccxt.pro WS：HTTP 代理对 WS CONNECT 转发不稳，REST 通路稳定。
watch_* 方法保持 ExchangePort 语义（阻塞直到有新数据），由 connector 的 while 循环驱动。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import ccxt  # 用同步 ccxt 走 REST，避免 ccxt.pro 的 WS 代理问题

from core.domain.config import AppConfig, ExchangeConfig

logger = logging.getLogger(__name__)


class MarketSource:
    """真实行情数据源，REST 轮询实现。"""

    def __init__(
        self,
        cfg: ExchangeConfig,
        app_config: AppConfig,
        exchange_name: str = "binance",
    ) -> None:
        self._cfg = cfg
        self._app_config = app_config

        exchange_cls = getattr(ccxt, exchange_name, None)
        if exchange_cls is None:
            raise ValueError(f"ccxt 不支持交易所: {exchange_name}")
        options: dict[str, Any] = {}
        markets = {ch.market for ch in app_config.channels}
        if markets == {"futures"}:
            options["defaultType"] = "futures"
        exchange_kwargs: dict[str, Any] = {
            "options": options,
            "enableRateLimit": True,
            "timeout": 20000,
        }
        # 行情侧只读公开数据，不带 apiKey：binance 配 key 时 load_markets 会顺带
        # 拉 sapi 提现接口并校验 key，公开行情不需要也不应触发。
        if cfg.proxy:
            proxy = cfg.proxy
            exchange_kwargs["proxies"] = {"http": proxy, "https": proxy}
            logger.info("MarketSource 使用代理: %s", proxy)
        self._exchange = exchange_cls(exchange_kwargs)
        self._exchange.load_markets()

        # symbol → 最新价缓存
        self._last_price: dict[str, float] = {}
        # symbol@timeframe → 上次已推送的 K 线时间戳，用于增量
        self._last_ohlcv_ts: dict[str, int] = {}
        self._closed = False

    async def watch_ohlcv(self, symbol: str, timeframe: str) -> list:
        """轮询 K 线，仅在出现新 K 线时返回。

        首次拉取使用大 limit 做历史数据预热，后续用小 limit 增量拉取。
        """
        key = f"{symbol}@{timeframe}"
        while not self._closed:
            # 首次拉取：预热历史数据（limit=500）；后续：增量轮询（limit=2）
            is_first = key not in self._last_ohlcv_ts
            limit = 500 if is_first else 2
            try:
                ohlcv = await asyncio.to_thread(
                    self._exchange.fetch_ohlcv, symbol, timeframe, limit=limit
                )
            except Exception as exc:
                logger.warning("fetch_ohlcv 失败 %s: %s", key, exc)
                await asyncio.sleep(2)
                continue
            if ohlcv:
                last = ohlcv[-1]
                ts = last[0]
                close = float(last[4])
                self._last_price[symbol] = close
                prev_ts = self._last_ohlcv_ts.get(key, 0)
                if ts != prev_ts:
                    self._last_ohlcv_ts[key] = ts
                    logger.info("K线数据 %s: 首次=%s 获取 %d 根", key, is_first, len(ohlcv))
                    return ohlcv
            # 无新 K 线，等待 timeframe 周期的一部分再轮询
            await asyncio.sleep(self._poll_interval(timeframe))

    async def watch_order_book(self, symbol: str) -> dict:
        """轮询盘口，每次都返回最新。"""
        ob = await asyncio.to_thread(self._exchange.fetch_order_book, symbol)
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        if bids and asks:
            mid = (bids[0][0] + asks[0][0]) / 2
            self._last_price[symbol] = float(mid)
        return ob

    async def watch_trades(self, symbol: str) -> list:
        """轮询最近成交。"""
        trades = await asyncio.to_thread(self._exchange.fetch_trades, symbol, limit=5)
        if trades:
            self._last_price[symbol] = float(trades[-1]["price"])
        return trades

    async def load_markets(self) -> dict:
        return self._exchange.markets

    def last_price(self, symbol: str) -> float | None:
        """撮合引擎取价入口。"""
        return self._last_price.get(symbol)

    @staticmethod
    def _poll_interval(timeframe: str) -> float:
        """根据 timeframe 估算轮询间隔（秒）。"""
        unit = timeframe[-1]
        n = int(timeframe[:-1]) if timeframe[:-1] else 1
        total = {"m": 60, "h": 3600, "d": 86400}.get(unit, 60) * n
        # 每个 K 线周期轮询 ~4 次，但不快于 2 秒（限流友好）
        return max(2.0, total / 4)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        logger.info("MarketSource 已关闭")
