"""ChannelHandler —— 类似 Netty 的 ChannelHandlerAdapter。

默认实现是直接放行（pass-through），子类按需重写 channel_read 和/或 write。
声明式事件过滤：handles / handles_commands 非 empty 时，基类自动跳过不匹配的事件/指令。
"""
from __future__ import annotations

from core.domain.command import Command
from core.domain.event import Event
from core.ports.context import Context


class Handler:
    """Handler 基类。默认所有方法都是 pass-through（直接传播到下一节点）。

    声明式过滤：
      handles: frozenset[EventType]  — 非空时，只处理声明的事件类型，其余自动跳过
      handles_commands: frozenset[CommandType] — 非空时，只处理声明的指令类型，其余自动跳过
      默认 frozenset() = 处理所有（pass-through）
    """

    handles: frozenset  = frozenset()          # 入站事件类型过滤
    handles_commands: frozenset = frozenset()  # 出站指令类型过滤

    async def channel_active(self, ctx: Context) -> None:...

    async def channel_read(self, ctx: Context, event: Event) -> None:...

    async def write(self, ctx: Context, command: Command) -> None:...

    async def exception_caught(self, ctx: Context, exc: Exception) -> None:...
