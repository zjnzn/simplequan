
from typing import Protocol, runtime_checkable

from core.domain.command import Command
from core.domain.event import Event
from core.ports.channel import Channel
from core.ports.context import Context
from core.ports.handler import Handler
from __future__ import annotations
"""Pipeline —— Netty 风格双向链表。

入站事件（channel_read）从 Head → Tail 传播，
出站指令（write）从 Tail → Head 传播。
"""
@runtime_checkable
class Pipeline(Protocol):

    channel:Channel
    _head:Context
    _tail:Context

    def add_last(self, name: str, handler: Handler) -> Pipeline:...

    async def fire_channel_active(self) -> None:...

    async def fire_channel_read(self, event: Event) -> None:...

    async def write(self, command: Command) -> None:...

    async def fire_exception_caught(self, exc: Exception) -> None:...
