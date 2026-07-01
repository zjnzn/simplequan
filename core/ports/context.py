"""Context —— Pipeline 中的处理节点。

每个 Context 持有 handler、前后节点引用，形成双向链表。
入站事件从 Head → Tail 传播，出站指令从 Tail → Head 传播。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from core.domain.command import Command
from core.domain.event import Event

if TYPE_CHECKING:
    from core.ports.channel import Channel
    from core.ports.handler import Handler
    from core.ports.pipline import Pipeline


@runtime_checkable
class Context(Protocol):
    """Pipeline 处理节点端口。"""

    name: str
    handler: Handler
    pipeline: Pipeline
    channel: Channel
    prev: Context | None
    next: Context | None

    async def fire_channel_active(self) -> None: ...

    async def fire_channel_read(self, event: Event) -> None: ...

    async def write(self, command: Command) -> None: ...

    async def fire_exception_caught(self, exc: Exception) -> None: ...
