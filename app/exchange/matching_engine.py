"""MatchingEngine —— 虚拟撮合引擎（内存）。

负责订单/账户/持仓的虚拟化，撮合时从 MarketSource 取真实最新价。
不订阅任何行情，行情驱动由 HybridExchange 的 watch_* 触发后通过 check_limits 检查限价单。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal

from app.exchange.market_source import MarketSource

logger = logging.getLogger(__name__)


class MatchingEngine:
    """虚拟撮合引擎。市价即时成交、限价挂单等行情触发。"""

    def __init__(
        self,
        market_source: MarketSource,
        initial_balance: float = 10000.0,
        fail_rate: float = 0.0,
    ) -> None:
        self._market = market_source
        self._fail_rate = fail_rate

        # 账户状态
        self._balance: dict[str, dict] = {
            "USDT": {"total": initial_balance, "free": initial_balance, "used": 0.0},
        }
        # symbol → 持仓（合约多空）
        self._positions: dict[str, dict] = {}
        # symbol → 杠杆倍数
        self._leverages: dict[str, int] = {}

        # 订单簿：order_id → raw
        self._orders: dict[str, dict] = {}
        # 挂单（限价未成交）：order_id → raw
        self._pending: dict[str, dict] = {}
        # symbol → 订单回报队列
        self._order_queues: dict[str, asyncio.Queue] = {}

        self._lock = asyncio.Lock()
        self._closed = False

    # ============================================================
    # 订单
    # ============================================================

    async def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: float | None = None,
    ) -> dict:
        """创建订单。市价即时成交，限价挂单。"""
        otype = order_type.lower()
        s = side.lower()
        order_id = str(uuid.uuid4())[:8]

        raw = {
            "id": order_id,
            "clientOrderId": order_id,
            "symbol": symbol,
            "side": s,
            "type": otype,
            "amount": amount,
            "price": price,
            "filled": 0.0,
            "average": None,
            "status": "open",
        }

        async with self._lock:
            self._orders[order_id] = raw

            # 失败场景模拟（可选，默认 0）
            import random
            if self._fail_rate > 0 and random.random() < self._fail_rate:
                raw["status"] = "rejected"
                await self._push_order(symbol, raw)
                logger.info("虚拟拒单: %s %s %s", symbol, s, amount)
                return raw

            if otype == "market":
                fill_price = self._market.last_price(symbol)
                if fill_price is None:
                    raw["status"] = "rejected"
                    await self._push_order(symbol, raw)
                    logger.info("市价单无行情拒单: %s %s", symbol, s)
                    return raw
                await self._fill(raw, fill_price, amount)
            else:
                # 限价单挂单
                self._pending[order_id] = raw
                await self._push_order(symbol, raw)
                logger.info("限价挂单: %s %s %s @%s", symbol, s, amount, price)

        return raw

    async def cancel_order(self, order_id: str, symbol: str) -> dict:
        """撤销挂单。"""
        async with self._lock:
            raw = self._orders.get(order_id, {})
            self._pending.pop(order_id, None)
            raw = {**raw, "status": "canceled"}
            self._orders[order_id] = raw
            await self._push_order(symbol, raw)
        return raw

    async def _fill(self, raw: dict, fill_price: float, fill_qty: float) -> None:
        """成交：更新订单、持仓、余额，推回报。必须持锁调用。"""
        raw["filled"] = fill_qty
        raw["average"] = fill_price
        raw["status"] = "closed"
        self._pending.pop(raw["id"], None)
        self._apply_position(raw["symbol"], raw["side"], fill_qty, fill_price)
        self._apply_balance(raw["symbol"], raw["side"], fill_qty, fill_price)
        await self._push_order(raw["symbol"], raw)
        logger.info(
            "虚拟成交: %s %s %s @%s",
            raw["symbol"], raw["side"], fill_qty, fill_price,
        )

    def _apply_position(self, symbol: str, side: str, qty: float, price: float) -> None:
        """更新持仓（合约多空加权平均）。"""
        pos = self._positions.setdefault(symbol, {
            "symbol": symbol, "side": "", "qty": 0.0,
            "avg_price": 0.0, "unrealizedPnl": 0.0,
        })
        dir_sign = 1.0 if side == "buy" else -1.0
        new_qty_signed = pos["qty"] * (1.0 if pos["side"] == "buy" else (-1.0 if pos["side"] else 0.0)) + dir_sign * qty
        if abs(new_qty_signed) < 1e-12:
            pos["side"] = ""
            pos["qty"] = 0.0
            pos["avg_price"] = 0.0
        else:
            if (new_qty_signed > 0) == (dir_sign > 0):
                # 同向加仓：加权平均
                old_cost = pos["qty"] * pos["avg_price"] if pos["qty"] else 0.0
                new_cost = old_cost + qty * price
                pos["avg_price"] = new_cost / (pos["qty"] + qty)
            # 反向则平仓/反手，avg_price 保持或按剩余方向重置（简化：保持原均价直到归零）
            pos["side"] = "buy" if new_qty_signed > 0 else "sell"
            pos["qty"] = abs(new_qty_signed)

    def _apply_balance(self, symbol: str, side: str, qty: float, price: float) -> None:
        """更新余额（杠杆感知：占用保证金 = notional / leverage）。"""
        usdt = self._balance["USDT"]
        cost = qty * price
        leverage = self._leverages.get(symbol, 1)
        margin = cost / leverage if leverage > 0 else cost
        if side == "buy":
            usdt["free"] -= margin
            usdt["used"] += margin
        else:
            usdt["free"] += margin
        usdt["total"] = usdt["free"] + usdt["used"]

    async def _push_order(self, symbol: str, raw: dict) -> None:
        """推订单回报到 watch_orders 队列。"""
        q = self._order_queues.setdefault(symbol, asyncio.Queue())
        await q.put(raw)

    async def check_limits(self, symbol: str) -> None:
        """行情更新后检查限价单是否触发。由 HybridExchange 在 watch_* 后调用。"""
        price = self._market.last_price(symbol)
        if price is None:
            return
        async with self._lock:
            triggered = []
            for oid, raw in list(self._pending.items()):
                if raw["symbol"] != symbol:
                    continue
                if raw["side"] == "buy" and price <= raw["price"]:
                    triggered.append(raw)
                elif raw["side"] == "sell" and price >= raw["price"]:
                    triggered.append(raw)
            for raw in triggered:
                await self._fill(raw, price, raw["amount"])

    async def watch_orders(self, symbol: str) -> list:
        """等待订单回报。"""
        q = self._order_queues.setdefault(symbol, asyncio.Queue())
        try:
            raw = await asyncio.wait_for(q.get(), timeout=1.0)
            return [raw]
        except asyncio.TimeoutError:
            return []

    # ============================================================
    # 账户
    # ============================================================

    async def fetch_balance(self) -> dict:
        usdt = dict(self._balance["USDT"])
        return {"info": {}, "USDT": usdt}

    async def fetch_positions(self, symbols: list[str]) -> list[dict]:
        """返回 ccxt 风格持仓列表，unrealized_pnl 用最新价实时算（含杠杆）。"""
        result = []
        for sym in symbols:
            pos = self._positions.get(sym)
            if not pos or not pos["qty"]:
                continue
            last = self._market.last_price(sym)
            upnl = 0.0
            if last:
                sign = 1.0 if pos["side"] == "buy" else -1.0
                leverage = self._leverages.get(sym, 1)
                upnl = sign * (last - pos["avg_price"]) * pos["qty"] * leverage
            result.append({
                "symbol": sym,
                "side": pos["side"],
                "contracts": pos["qty"],
                "entryPrice": pos["avg_price"],
                "unrealizedPnl": upnl,
            })
        return result

    def set_leverage(self, symbol: str, leverage: int, margin_mode: str = "cross") -> None:
        """设置逐 symbol 杠杆倍数。"""
        self._leverages[symbol] = leverage

    async def fetch_leverage(self, symbol: str) -> dict:
        lev = self._leverages.get(symbol, 1)
        return {"leverage": lev, "marginMode": "cross"}

    # ============================================================
    # 生命周期
    # ============================================================

    async def close(self) -> None:
        self._closed = True
        for q in self._order_queues.values():
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        logger.info("MatchingEngine 已关闭")
