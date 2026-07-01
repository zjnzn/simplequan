from typing import Any, Awaitable, Callable
from typing import Protocol, runtime_checkable


BusHandler = Callable[[str, Any], Awaitable[None]]


# ============================================================
# EventBus —— 异步发布/订阅总线
# ============================================================
@runtime_checkable
class EventBus(Protocol):

    def on(self, topic_pattern: str, handler: BusHandler) -> None:...

    def off(self, topic_pattern: str, handler: BusHandler) -> None:...

    async def emit(self, topic: str, payload: Any) -> None:...

    def _is_pattern(topic_pattern: str) -> bool:...




