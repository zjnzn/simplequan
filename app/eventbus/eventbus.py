"""EventBus —— Channel 和 ExchangeConnector 之间唯一的连接方式。

topic 支持 * 通配符（fnmatch 风格）。
exact topic 走 O(1) 索引查找，wildcard topic 走 fnmatch 遍历。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

BusHandler = Callable[[str, Any], Awaitable[None]]


# ============================================================
# EventBus —— 异步发布/订阅总线
# ============================================================
class EventBus:
    """异步发布/订阅总线，topic 支持 * 通配符（fnmatch 风格）。"""

    def __init__(self) -> None:
        self._exact: dict[str, list[BusHandler]] = defaultdict(list)
        self._patterns: dict[str, list[BusHandler]] = defaultdict(list)

    def on(self, topic_pattern: str, handler: BusHandler) -> None:
        if self._is_pattern(topic_pattern):
            self._patterns[topic_pattern].append(handler)
        else:
            self._exact[topic_pattern].append(handler)

    def off(self, topic_pattern: str, handler: BusHandler) -> None:
        store = self._patterns if self._is_pattern(topic_pattern) else self._exact
        if handler in store.get(topic_pattern, []):
            store[topic_pattern].remove(handler)

    async def emit(self, topic: str, payload: Any) -> None:
        # exact 匹配 O(1)
        for h in self._exact.get(topic, []):
            try:
                result = h(topic, payload)
                if result is not None and hasattr(result, "__await__"):
                    await result
            except Exception:
                logger.exception(f"handler error on {topic}")
        # wildcard 匹配
        for pattern, handlers in list(self._patterns.items()):
            if fnmatch(topic, pattern):
                for h in handlers:
                    try:
                        result = h(topic, payload)
                        if result is not None and hasattr(result, "__await__"):
                            await result
                    except Exception:
                        logger.exception(f"handler error on {topic}")

    @staticmethod
    def _is_pattern(topic_pattern: str) -> bool:
        return "*" in topic_pattern or "?" in topic_pattern




