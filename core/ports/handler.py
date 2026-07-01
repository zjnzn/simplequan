from __future__ import annotations

from typing import TYPE_CHECKING

from core.domain.command import Command
from core.domain.event import Event

if TYPE_CHECKING:
    from core.ports.context import Context


class Handler:

    handles: frozenset  = frozenset()          # 入站事件类型过滤
    handles_commands: frozenset = frozenset()  # 出站指令类型过滤

    async def channel_active(self, ctx: Context) -> None:...

    async def channel_read(self, ctx: Context, event: Event) -> None:
        """入站默认透传：未实现 channel_read 的 handler 把事件继续向 next 传播。"""
        await ctx.fire_channel_read(event)

    async def write(self, ctx: Context, command: Command) -> None:
        """出站默认透传：未实现 write 的 handler 把指令继续向 prev 传播。

        入站类 handler（如 OrderResult/OrderAccepted）不处理出站指令，
        透传让出站链能到达真正实现的 handler（OrderEncode）和 Head 终端。
        Head handler 覆盖此方法作为显式终端。
        """
        await ctx.write(command)

    async def exception_caught(self, ctx: Context, exc: Exception) -> None:...
