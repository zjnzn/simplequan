"""DataPersistHandler —— 运行时全链路数据自动持久化为 CSV。

K 线 + 指标 + 市场状态 + 信号 → {symbol}_{interval}.csv
订单创建/成交/取消 → {symbol}_orders.csv
出站下单指令 → {symbol}_commands.csv
"""
from __future__ import annotations

import csv
import logging
import os
import threading
import time as _time
from dataclasses import asdict
from datetime import datetime, timezone

from core.domain.command import Command
from core.domain.event import Event, EventType
from core.domain.order import Order
from core.ports.context import Context
from core.ports.handler import Handler

logger = logging.getLogger(__name__)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "runtime")


def _dt(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _flatten_order(order: Order) -> dict:
    d = asdict(order)
    if d.get("updates"):
        d["updates"] = str(d["updates"])
    d["datetime"] = _dt(int(d.get("timestamp", 0))) if d.get("timestamp") else ""
    return d


def _ensure_row(row: dict) -> None:
    if "timestamp" in row and "datetime" not in row:
        try:
            row["datetime"] = _dt(int(row["timestamp"]))
        except (TypeError, ValueError):
            pass


class DataPersistHandler(Handler):
    """全链路持久化：K 线 + 订单 + 出站指令。

    位置：Signal 之后、RiskPre 之前。
    """

    handles: frozenset = frozenset()
    handles_commands: frozenset = frozenset()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._klines_last: dict[str, int] = {}
        self._klines_fields: dict[str, list[str]] = {}
        self._orders_fields: dict[str, list[str]] = {}
        self._commands_fields: dict[str, list[str]] = {}
        os.makedirs(OUT_DIR, exist_ok=True)

    # ============================================================
    # 入站
    # ============================================================

    async def channel_read(self, ctx: Context, event: Event) -> None:
        try:
            if event.type == EventType.KLINE:
                self._write_kline(event)
            elif event.type in (
                EventType.ORDER_CREATED, EventType.ORDER_FILLED,
                EventType.ORDER_CANCELED, EventType.ORDER_REJECTED,
            ):
                self._write_order(event)
        except Exception:
            logger.warning("DataPersist 写入异常", exc_info=True)
        finally:
            await ctx.fire_channel_read(event)

    def _write_kline(self, event: Event) -> None:
        row = event.payload
        if not isinstance(row, dict):
            return
        interval = row.get("interval", "")
        if not interval:
            return

        _ensure_row(row)
        compact = event.symbol.replace("/", "_")
        key = f"{compact}_{interval}"
        filepath = os.path.join(OUT_DIR, f"{key}.csv")

        with self._lock:
            ts = row.get("timestamp", 0)
            last = self._klines_last.get(key, 0)
            if ts and ts <= last:
                return
            if ts:
                self._klines_last[key] = ts

            if key not in self._klines_fields:
                self._klines_fields[key] = list(row.keys())
            fields = self._klines_fields[key]
            for k in row:
                if k not in fields:
                    fields.append(k)

            with open(filepath, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                if f.tell() == 0:
                    writer.writeheader()
                writer.writerow(row)

    def _write_order(self, event: Event) -> None:
        payload = event.payload
        if isinstance(payload, Order):
            row = _flatten_order(payload)
        elif isinstance(payload, dict):
            row = dict(payload)
            _ensure_row(row)
        else:
            row = {"raw": str(payload)}

        row["event_type"] = event.type.value
        row["symbol"] = event.symbol

        compact = event.symbol.replace("/", "_")
        key = f"order_{compact}"
        filepath = os.path.join(OUT_DIR, f"{compact}_orders.csv")

        with self._lock:
            if key not in self._orders_fields:
                self._orders_fields[key] = list(row.keys())
            fields = self._orders_fields[key]
            for k in row:
                if k not in fields:
                    fields.append(k)

            with open(filepath, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                if f.tell() == 0:
                    writer.writeheader()
                writer.writerow(row)

    # ============================================================
    # 出站
    # ============================================================

    async def write(self, ctx: Context, command: Command) -> None:
        try:
            compact = command.symbol.replace("/", "_")
            key = f"cmd_{compact}"
            filepath = os.path.join(OUT_DIR, f"{compact}_commands.csv")

            row = {
                "timestamp": int(_time.time() * 1000),
                "datetime": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "command_type": command.type.value,
                "symbol": command.symbol,
                **command.payload,
            }

            with self._lock:
                if key not in self._commands_fields:
                    self._commands_fields[key] = list(row.keys())
                fields = self._commands_fields[key]
                for k in row:
                    if k not in fields:
                        fields.append(k)

                with open(filepath, "a", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                    if f.tell() == 0:
                        writer.writeheader()
                    writer.writerow(row)
        except Exception:
            logger.warning("DataPersist 指令写入异常", exc_info=True)
        finally:
            await ctx.write(command)
