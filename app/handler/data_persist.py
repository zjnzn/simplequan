"""DataPersistHandler —— 运行时全链路数据自动持久化为 CSV。

K 线 + 指标 + 市场状态 + 信号 → {symbol}_{interval}.csv
订单创建/成交/取消 → {symbol}_orders.csv
出站下单指令 → {symbol}_commands.csv
"""
from __future__ import annotations

import csv
import json
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
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, OSError, ValueError):
        return ""


def _safe_value(v) -> str | int | float | None:
    """嵌套结构 JSON 序列化，避免 CSV 列内逗号炸开。"""
    if v is None:
        return ""
    if isinstance(v, (int, float, str, bool)):
        return v
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, default=str)
    if isinstance(v, (list, tuple)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def _flatten_row(row: dict) -> dict:
    """将 dict 中所有嵌套值转安全字符串，datetime 补充。"""
    flat = {}
    for k, v in row.items():
        flat[k] = _safe_value(v)
    if "timestamp" in flat and "datetime" not in flat:
        flat["datetime"] = _dt(int(flat["timestamp"])) if isinstance(flat["timestamp"], (int, float)) else ""
    return flat


def _flatten_order(order: Order) -> dict:
    d = asdict(order)
    if d.get("updates"):
        d["updates"] = json.dumps(d["updates"], default=str)
    d["datetime"] = _dt(int(d.get("timestamp", 0))) if d.get("timestamp") else ""
    return d


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
        self._orders_dedup: set[str] = set()
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

        row = _flatten_row(row)
        compact = event.symbol.replace("/", "_")
        key = f"{compact}_{interval}"
        filepath = os.path.join(OUT_DIR, f"{key}.csv")

        with self._lock:
            ts = row.get("timestamp", 0)
            if ts and ts <= self._klines_last.get(key, 0):
                return
            if ts:
                self._klines_last[key] = ts

            if key not in self._klines_fields:
                self._klines_fields[key] = list(row.keys())
            fields = self._klines_fields[key]
            for k in row:
                if k not in fields:
                    fields.append(k)

            self._write_csv_row(filepath, fields, row)

    def _write_order(self, event: Event) -> None:
        payload = event.payload

        # 统一转为扁平 dict
        if isinstance(payload, Order):
            row = _flatten_order(payload)
        elif isinstance(payload, dict):
            row = dict(payload)
        else:
            row = {"raw": _safe_value(payload)}

        row["event_type"] = event.type.value
        row["symbol"] = event.symbol

        # 扁平化嵌套字段
        row = _flatten_row(row)

        # 去重：同 order_id + event_type 只记一次
        oid = row.get("id") or row.get("order_id") or row.get("orderId") or ""
        dedup_key = f"{oid}_{event.type.value}"
        if oid and dedup_key in self._orders_dedup:
            return
        if oid:
            self._orders_dedup.add(dedup_key)

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

            self._write_csv_row(filepath, fields, row)

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
            }
            for k, v in command.payload.items():
                row[k] = _safe_value(v)

            with self._lock:
                if key not in self._commands_fields:
                    self._commands_fields[key] = list(row.keys())
                fields = self._commands_fields[key]
                for k in row:
                    if k not in fields:
                        fields.append(k)

                self._write_csv_row(filepath, fields, row)
        except Exception:
            logger.warning("DataPersist 指令写入异常", exc_info=True)
        finally:
            await ctx.write(command)

    @staticmethod
    def _write_csv_row(filepath: str, fields: list[str], row: dict) -> None:
        with open(filepath, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(row)
