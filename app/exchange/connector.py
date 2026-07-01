"""ExchangeConnector —— EventBus 桥接层，持有 ExchangePort。

监听 EventBus 上的 request/* 和 command/* topic：
  - request/{market}/{symbol}/{feed}       有人要订阅这路数据，开始对应的 watch_* 循环
  - command/{market}/{symbol}/{cmd}/{channel_id}  有人要下单/撤单，执行真正的交易所调用

ExchangeConnector 是唯一知道 topic 格式和 EventType 映射的地方。
所有 emit 均包装为 ChannelEvent，Channel 只消费不解析。

Topic 协议：
  数据入站:  {market}/{feed}/{symbol}[@{param}]              spot/kline/BTC/USDT@1m
  订单回报:  {market}/order/{symbol}/{channel_id}/{event}    spot/order/BTC/USDT/{uuid}/filled
  错误通知:  {market}/error/{sym_compact}/{source}           spot/error/BTCUSDT/kline
"""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

from app.eventbus.eventbus import ChannelEventBus
from core.domain.account import (
    Balance,
    LeverageConfig,
    MasterAccount,
    Position,
)
from core.domain.event import Event, EventType
from core.domain.symbol import Symbol
from core.ports.exchange import ExchangePort


def _parse_request_topic(topic: str) -> tuple[str, str, str]:
    """解析 request topic: request/{market}/{symbol}/{feed}"""
    rest = topic[len("request/"):]
    first_slash = rest.index("/")
    market = rest[:first_slash]
    remainder = rest[first_slash + 1:]
    last_slash = remainder.rindex("/")
    symbol = remainder[:last_slash]
    feed = remainder[last_slash + 1:]
    return market, symbol, feed


def _parse_command_topic(topic: str) -> tuple[str, str, str, str]:
    """解析 command topic: command/{market}/{symbol}/{cmd}/{channel_id}"""
    rest = topic[len("command/"):]
    first_slash = rest.index("/")
    market = rest[:first_slash]
    remainder = rest[first_slash + 1:]
    last_slash = remainder.rindex("/")
    channel_id = remainder[last_slash + 1:]
    remainder = remainder[:last_slash]
    cmd_slash = remainder.rindex("/")
    symbol = remainder[:cmd_slash]
    cmd = remainder[cmd_slash + 1:]
    return market, symbol, cmd, channel_id


# ccxt status → EventType 映射（集中在这里，Channel 不再持有）
_ORDER_STATUS_MAP: dict[str, EventType] = {
    "open": EventType.ORDER_CREATED,
    "closed": EventType.ORDER_FILLED,
    "canceled": EventType.ORDER_CANCELED,
    "rejected": EventType.ORDER_REJECTED,
}


class ExchangeConnector:
    """EventBus 桥接层，持有 ExchangePort。

    ExchangeConnector 是唯一知道 topic 格式和 EventType 映射的地方。
    所有数据 emit 均包装为 ChannelEvent，Channel 只转发不解析。
    """

    def __init__(self, exchange: ExchangePort, bus: ChannelEventBus) -> None:
        self._exchange = exchange
        self._bus = bus
        self._readers: dict[str, asyncio.Task] = {}
        # order_id → channel_id 映射，确保订单回报路由到正确的 Channel
        self._order_channel: dict[str, str] = {}

        self._bus.on("request/*", self._on_request)
        self._bus.on("command/*", self._on_command)
        self._bus.on("unsubscribe/*", self._on_unsubscribe)
        # 全局查询命令（无 symbol/channel_id，不套 4 段格式）
        self._bus.on("command/fetch_account", self._on_fetch_account)
        self._bus.on("command/fetch_symbol", self._on_fetch_symbol)

    # ============================================================
    # request 处理
    # ============================================================

    async def _on_request(self, topic: str, payload: dict) -> None:
        market, symbol, feed = _parse_request_topic(topic)
        key = f"{market}:{symbol}:{feed}"
        existing = self._readers.get(key)
        if existing and not existing.done():
            return
        coro = self._build_reader(market, symbol, feed)
        self._readers[key] = asyncio.create_task(coro, name=key)

    def _build_reader(self, market: str, symbol: str, feed: str):
        sym_compact = symbol.replace("/", "")
        if feed.startswith("kline-"):
            timeframe = feed.split("-", 1)[1]
            return self._kline_loop(market, symbol, sym_compact, timeframe)
        if feed == "orderbook":
            return self._watch_loop(
                market, symbol, sym_compact, EventType.ORDERBOOK,
                self._exchange.watch_order_book, (symbol,)
            )
        if feed == "trade":
            return self._watch_loop(
                market, symbol, sym_compact, EventType.TRADE,
                self._exchange.watch_trades, (symbol,)
            )
        if feed == "order":
            return self._order_loop(market, symbol, sym_compact)
        raise ValueError(f"unknown feed: {feed}")

    async def _kline_loop(self, market: str, symbol: str, sym_compact: str, timeframe: str) -> None:
        topic = f"{market}/kline/{symbol}@{timeframe}"
        error_topic = f"{market}/error/{sym_compact}/kline"
        while True:
            try:
                ohlcv = await self._exchange.watch_ohlcv(symbol, timeframe)
                event = Event(EventType.KLINE, symbol, {"timeframe": timeframe, "ohlcv": ohlcv})
                await self._bus.emit(topic, event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._bus.emit(error_topic, str(exc))
                await asyncio.sleep(1)

    async def _watch_loop(
        self, market: str, symbol: str, sym_compact: str,
        event_type: EventType, watch_fn, args: tuple,
    ) -> None:
        feed_name = event_type.value
        topic = f"{market}/{feed_name}/{symbol}"
        error_topic = f"{market}/error/{sym_compact}/{feed_name}"
        while True:
            try:
                data = await watch_fn(*args)
                event = Event(event_type, symbol, data)
                await self._bus.emit(topic, event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._bus.emit(error_topic, str(exc))
                await asyncio.sleep(1)

    async def _order_loop(self, market: str, symbol: str, sym_compact: str) -> None:
        """监听交易所订单状态更新，构建 ChannelEvent 后 emit。"""
        error_topic = f"{market}/error/{sym_compact}/order"
        while True:
            try:
                updates = await self._exchange.watch_orders(symbol)
                has_fill = False
                for raw in updates:
                    order_id = str(raw.get("id", ""))
                    event_name = self._order_event_name(raw.get("status", "open"))
                    event_type = _ORDER_STATUS_MAP.get(raw.get("status", "open"), EventType.ORDER_CREATED)
                    channel_id = self._order_channel.get(order_id, "")
                    event = Event(event_type, symbol, raw)
                    if channel_id:
                        topic = f"{market}/order/{symbol}/{channel_id}/{event_name}"
                    else:
                        topic = f"{market}/order/{symbol}/_unknown/{event_name}"
                    await self._bus.emit(topic, event)
                    if raw.get("status") in ("closed", "filled"):
                        has_fill = True
                # 订单成交后刷新余额
                if has_fill:
                    try:
                        bal = await self._exchange.fetch_balance()
                        usdt = bal.get("USDT", {})
                        await self._bus.emit("account/balance", {
                            "total": usdt.get("total", 0.0),
                            "free": usdt.get("free", 0.0),
                            "used": usdt.get("used", 0.0),
                            "currency": "USDT",
                        })
                    except Exception:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._bus.emit(error_topic, str(exc))
                await asyncio.sleep(1)

    @staticmethod
    def _order_event_name(status: str) -> str:
        return {"closed": "filled", "canceled": "canceled", "rejected": "rejected"}.get(
            status, "created"
        )

    # ============================================================
    # command 处理：下单 / 撤单
    # ============================================================

    async def _on_command(self, topic: str, payload: dict) -> None:
        # 跳过全局查询命令（由专门的 handler 处理，避免 _parse_command_topic 解析失败）
        if topic in ("command/fetch_account", "command/fetch_symbol"):
            return
        market, symbol, cmd_type, channel_id = _parse_command_topic(topic)
        sym_compact = symbol.replace("/", "")
        error_topic = f"{market}/error/{sym_compact}/order"
        try:
            if cmd_type == "create_order":
                raw = await self._exchange.create_order(
                    symbol, payload["type"], payload["side"],
                    payload["amount"], payload.get("price"),
                )
                # 记录 order_id → channel_id 映射
                order_id = str(raw.get("id", ""))
                if order_id:
                    self._order_channel[order_id] = channel_id
                # 立即回报 created 事件（带 channel_id），包装为 ChannelEvent
                event = Event(EventType.ORDER_CREATED, symbol, raw)
                await self._bus.emit(f"{market}/order/{symbol}/{channel_id}/created", event)
            elif cmd_type == "cancel_order":
                raw = await self._exchange.cancel_order(payload["order_id"], symbol)
                event = Event(EventType.ORDER_CANCELED, symbol, raw)
                await self._bus.emit(f"{market}/order/{symbol}/{channel_id}/canceled", event)
        except Exception as exc:
            await self._bus.emit(error_topic, str(exc))

    # ============================================================
    # 全局查询命令：拉取 Symbol / MasterAccount 领域对象
    # ============================================================

    async def _on_fetch_symbol(self, topic: str, payload: dict) -> None:
        """拉取单个 symbol 的市场信息，构建 Symbol 对象后回报。

        payload: {"symbol": "BTC/USDT", "market": "futures", "interval": "1m"}
        回报 topic: market/symbol/{symbol}@{interval}
        """
        symbol = payload["symbol"]
        market = payload.get("market", "spot")
        interval = payload.get("interval", "")
        try:
            markets = await self._exchange.load_markets()
            md = markets.get(symbol)
            if not md:
                await self._bus.emit(f"market/symbol/{symbol}@{interval}", None)
                return
            sym = Symbol.from_ccxt(md, market=market)
            await self._bus.emit(f"market/symbol/{symbol}@{interval}", sym)
        except Exception as exc:
            await self._bus.emit(
                f"market/error/{symbol.replace('/', '')}/fetch_symbol", str(exc)
            )

    async def _on_fetch_account(self, topic: str, payload: dict) -> None:
        """拉取主账号整体（balance + 全部 positions + 全部 leverage），组装 MasterAccount 后回报。

        payload: {"symbols": ["BTC/USDT", ...], "account_id": "master"}
        回报 topic: account/master
        symbols 仅用于过滤关心的持仓和逐 symbol 拉杠杆，不切分 SubAccount。
        """
        symbols = payload.get("symbols", [])
        account_id = payload.get("account_id", "master")
        try:
            # 1. balance → Balance
            bal = await self._exchange.fetch_balance()
            usdt = bal.get("USDT", {})
            balance = Balance(
                total=Decimal(str(usdt.get("total", 0))),
                free=Decimal(str(usdt.get("free", 0))),
                used=Decimal(str(usdt.get("used", 0))),
                currency="USDT",
            )
            # 2. 一次拉全部持仓（账号整体，不按 symbol 循环）
            raw_positions = await self._exchange.fetch_positions(symbols)
            positions: dict[str, Position] = {}
            for p in raw_positions:
                sym = p.get("symbol", "")
                if not sym:
                    continue
                qty = p.get("contracts", p.get("qty", 0))
                avg = p.get("entryPrice", p.get("avg_price", 0))
                upnl = p.get("unrealizedPnl", p.get("unrealized_pnl", 0))
                positions[sym] = Position(
                    side=p.get("side", "").upper(),
                    qty=Decimal(str(qty or 0)),
                    avg_price=Decimal(str(avg or 0)),
                    unrealized_pnl=Decimal(str(upnl or 0)),
                )
            # 3. 逐 symbol 拉杠杆（leverage 是 per-symbol 设置）
            leverages: dict[str, LeverageConfig] = {}
            for s in symbols:
                lev = await self._exchange.fetch_leverage(s)
                leverages[s] = LeverageConfig(
                    leverage=int(lev.get("leverage", 1) or 1),
                    margin_mode=lev.get("marginMode", lev.get("margin_mode", "cross")),
                )
            # 4. 组装 MasterAccount（不在此建 SubAccount，由 Channel 创建时分配）
            master = MasterAccount(
                account_id=account_id,
                balance=balance,
                positions=positions,
                leverages=leverages,
            )
            await self._bus.emit("account/master", master)
        except Exception as exc:
            await self._bus.emit("account/error", str(exc))

    async def _on_unsubscribe(self, topic: str, payload: dict) -> None:
        rest = topic[len("unsubscribe/"):]
        first_slash = rest.index("/")
        market = rest[:first_slash]
        symbol = rest[first_slash + 1:]
        prefix = f"{market}:{symbol}:"
        to_cancel = [k for k in self._readers if k.startswith(prefix)]
        for key in to_cancel:
            task = self._readers.pop(key)
            if not task.done():
                task.cancel()
        if to_cancel:
            logger.debug(f"unsubscribed {len(to_cancel)} reader(s) for {symbol}")

    async def close(self) -> None:
        for task in self._readers.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._readers.values(), return_exceptions=True)
        self._readers.clear()
        self._order_channel.clear()
