from __future__ import annotations

from core.domain.command import Command
from core.domain.event import Event
from core.ports.context import Context


class Handler:

    handles: frozenset  = frozenset()          # 入站事件类型过滤
    handles_commands: frozenset = frozenset()  # 出站指令类型过滤

    async def channel_active(self, ctx: Context) -> None:...

    async def channel_read(self, ctx: Context, event: Event) -> None:...

    async def write(self, ctx: Context, command: Command) -> None:...

    async def exception_caught(self, ctx: Context, exc: Exception) -> None:...
