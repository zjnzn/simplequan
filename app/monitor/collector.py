"""Monitor 采集器 —— 订阅 eventbus 被动采集历史数据。

handler 内部事件（信号/指标）走 pipeline fire_channel_read 不上 bus，
故通过订阅 kline topic 触发快照：每根 bar 到达后读 channel.market 最新值。
订单回报走 bus topic，直接订阅。
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

import pandas as pd

from app.monitor.store import ChannelRecord

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume", "interval"}


class Collector:
    """订阅 bus 采集历史数据，写入 ChannelRecord。"""

    def __init__(self, bootstrap, bus) -> None:
        self._bootstrap = bootstrap
        self._bus = bus
        self._records: dict[str, ChannelRecord] = {}
        self._synced_ts: dict[str, int] = {}
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
        payload: Event(KLINE, symbol, row_dict)
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

        df = ch.market.bars.get(interval)
        if df is not None and len(df) > 0:
            last_synced = self._synced_ts.get(channel_id, 0)
            new_rows = df[df["timestamp"] > last_synced]
            for _, row in new_rows.iterrows():
                rec.klines.append(self._row_to_bar_dict(row))
                last_synced = int(row["timestamp"])
            self._synced_ts[channel_id] = last_synced

            last_row = df.iloc[-1]
            bar_ts = int(last_row["timestamp"])
        else:
            bar_ts = 0

        # 快照当前指标（从最后一行的非 OHLCV 列提取）
        if df is not None and len(df) > 0:
            last_row = df.iloc[-1]
            inds = {}
            for col in df.columns:
                if col not in OHLCV_COLUMNS and col not in ("signal_value", "signal_strength", "signal_reason"):
                    val = last_row[col]
                    if pd.notna(val):
                        inds[col] = str(val)
            rec.indicators.append({"timestamp": bar_ts, "indicators": inds})

        # 快照当前信号
        sig = ch.market.current_signal
        if sig is not None:
            rec.signals.append({
                "timestamp": bar_ts,
                "direction": sig.direction,
                "strength": sig.strength,
                "value": sig.value,
                "reason": sig.reason,
            })

    async def _on_order(self, topic: str, payload: Any) -> None:
        """订单回报 → 存历史订单。"""
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

        if oid:
            for i, old in enumerate(rec.orders):
                if str(old.get("order_id", "")) == str(oid):
                    rec.orders[i] = snap
                    return
        rec.orders.append(snap)

    def _row_to_bar_dict(self, row: pd.Series) -> dict:
        """DataFrame 行 → Bar dict（兼容监控前端）。"""
        return {
            "symbol": row.get("symbol", ""),
            "interval": row.get("interval", ""),
            "open": str(row.get("open", "")),
            "high": str(row.get("high", "")),
            "low": str(row.get("low", "")),
            "close": str(row.get("close", "")),
            "volume": str(row.get("volume", "")),
            "timestamp": int(row.get("timestamp", 0)),
        }

    def _find_channel_by_uuid(self, uuid: str):
        for ch in self._bootstrap._channels.values():
            if ch.id == uuid or ch.id.startswith(uuid):
                return ch
        return None

    def _parse_kline_topic(self, topic: str) -> str | None:
        marker = "/kline/"
        idx = topic.find(marker)
        if idx < 0:
            return None
        return topic[idx + len(marker):]

    def _find_channel(self, channel_id: str):
        for ch in self._bootstrap._channels.values():
            if ch.config.channel_id == channel_id:
                return ch
        return None

    def _order_to_dict(self, order: Any, event: str = "") -> dict:
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
