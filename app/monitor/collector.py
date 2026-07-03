"""Monitor 采集器 —— 订阅 eventbus 被动采集历史数据。

handler 内部事件（信号/指标）走 pipeline fire_channel_read 不上 bus，
故通过订阅 kline topic 触发快照：每根 bar 到达后读 channel.market 最新值。
订单回报走 bus topic，直接订阅。
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any

from app.monitor.store import ChannelRecord

logger = logging.getLogger(__name__)


class Collector:
    """订阅 bus 采集历史数据，写入 ChannelRecord。"""

    def __init__(self, bootstrap, bus) -> None:
        self._bootstrap = bootstrap
        self._bus = bus
        self._records: dict[str, ChannelRecord] = {}
        # 跟踪每个 channel 已同步到前端的最新 bar timestamp，避免重复
        self._synced_ts: dict[str, int] = {}
        # master 账户历史快照（有界 200）
        self.master_history: deque[dict[str, Any]] = deque(maxlen=200)

    def bind(self) -> None:
        """订阅 bus topic。"""
        self._bus.on("*/kline/*", self._on_kline)
        self._bus.on("*/order/*", self._on_order)
        self._bus.on("account/master", self._on_master)

    @property
    def records(self) -> dict[str, ChannelRecord]:
        return self._records

    def get_or_create(self, channel_id: str, symbol: str, interval: str) -> ChannelRecord:
        rec = self._records.get(channel_id)
        if rec is None:
            rec = ChannelRecord(channel_id=channel_id, symbol=symbol, interval=interval)
            self._records[channel_id] = rec
        return rec

    async def _on_master(self, topic: str, master: Any) -> None:
        """记录 master 历史快照，用于监控面板回溯。"""
        import time
        snap = {
            "ts": int(time.time()),
            "account_id": getattr(master, "account_id", ""),
            "balance_total": float(master.balance.total) if hasattr(master, "balance") else 0.0,
            "balance_free": float(master.balance.free) if hasattr(master, "balance") else 0.0,
            "balance_used": float(master.balance.used) if hasattr(master, "balance") else 0.0,
            "subs_count": len(getattr(master, "sub_accounts", ())),
        }
        self.master_history.append(snap)

    async def _on_kline(self, topic: str, payload: Any) -> None:
        """kline 到达 → 全量同步 market.bars + 快照 indicators/signal 存历史。

        topic: {market}/kline/{symbol}@{interval}
        payload: Event(KLINE, symbol, Bar) 或 Event(KLINE, symbol, {timeframe, ohlcv})
        """
        channel_id = self._parse_kline_topic(topic)
        if channel_id is None:
            return
        ch = self._find_channel(channel_id)
        if ch is None:
            return

        symbol = ch.symbol.symbol
        interval = ch.config.interval
        rec = self.get_or_create(channel_id, symbol, interval)

        # 全量同步 market.bars 中尚未同步到前端的新 bar
        bars = ch.market.bars.get(interval)
        if bars:
            last_synced = self._synced_ts.get(channel_id, 0)
            for bar in bars:
                if bar.timestamp > last_synced:
                    rec.klines.append(bar)
                    last_synced = bar.timestamp
            self._synced_ts[channel_id] = last_synced

            # 取最新 bar 用于指标/信号时间戳
            bar = list(bars)[-1]
        else:
            bar = None

        # 快照当前指标
        inds = ch.market.indicators.get(interval, {})
        rec.indicators.append({
            "timestamp": getattr(bar, "timestamp", 0) if bar else 0,
            "indicators": {k: str(v) for k, v in inds.items()},
        })

        # 快照当前信号
        sig = ch.market.current_signal
        if sig is not None:
            rec.signals.append({
                "timestamp": getattr(bar, "timestamp", 0) if bar else 0,
                "direction": sig.direction,
                "strength": sig.strength,
                "value": sig.value,
                "reason": sig.reason,
            })

    async def _on_order(self, topic: str, payload: Any) -> None:
        """订单回报 → 存历史订单。

        topic: {market}/order/{symbol}/{channel_uuid}/{event}
        其中 channel_uuid 是 SymbolChannel.id（非 channel_id=symbol@interval），
        需用 uuid 反查 channel 再映射到 record。
        """
        parts = topic.split("/")
        if len(parts) < 5:
            return
        channel_uuid = parts[-2]
        ch = self._find_channel_by_uuid(channel_uuid)
        if ch is None:
            return
        channel_id = ch.config.channel_id
        rec = self.get_or_create(channel_id, ch.symbol.symbol, ch.config.interval)

        order = getattr(payload, "payload", payload)
        ev_type = getattr(payload, "type", None)
        ev_name = ev_type.value if hasattr(ev_type, "value") else str(ev_type)
        oid = order.get("id") if isinstance(order, dict) else getattr(order, "order_id", "")
        snap = self._order_to_dict(order, ev_name)

        # 按 order_id 去重：同订单多次回报（created→filled）只保留最新
        if oid:
            for i, old in enumerate(rec.orders):
                if str(old.get("order_id", "")) == str(oid):
                    rec.orders[i] = snap
                    return
        rec.orders.append(snap)

    def _find_channel_by_uuid(self, uuid: str):
        """按 SymbolChannel.id（uuid 或前缀）找 channel。"""
        for ch in self._bootstrap._channels.values():
            if ch.id == uuid or ch.id.startswith(uuid):
                return ch
        return None

    def _parse_kline_topic(self, topic: str) -> str | None:
        """{market}/kline/{symbol}@{interval} → channel_id (symbol@interval)。"""
        marker = "/kline/"
        idx = topic.find(marker)
        if idx < 0:
            return None
        return topic[idx + len(marker):]

    def _find_channel(self, channel_id: str):
        """按 channel_id（symbol@interval）找 channel。"""
        for ch in self._bootstrap._channels.values():
            if ch.config.channel_id == channel_id:
                return ch
        return None

    def _order_to_dict(self, order: Any, event: str = "") -> dict:
        """Order 对象或 ccxt raw dict → dict 快照。"""
        if isinstance(order, dict):
            state = order.get("status", "")
            return {
                "order_id": str(order.get("id", "")),
                "event": event,
                "symbol": order.get("symbol", ""),
                "side": str(order.get("side", "")).upper(),
                "state": state,
                "qty": order.get("amount", ""),
                "filled_qty": order.get("filled", ""),
                "avg_price": order.get("average"),
                "cost": order.get("cost"),
            }
        if hasattr(order, "order_id"):
            return {
                "order_id": order.order_id,
                "event": event,
                "symbol": getattr(order, "symbol", ""),
                "side": getattr(order, "side", ""),
                "state": getattr(order, "state", "").value if hasattr(getattr(order, "state", None), "value") else str(getattr(order, "state", "")),
                "qty": str(getattr(order, "qty", "")),
                "filled_qty": str(getattr(order, "filled_qty", "")),
                "avg_price": str(getattr(order, "avg_price", "")),
            }
        return {"raw": str(order)}
