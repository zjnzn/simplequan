"""ChannelPipeline —— Netty 风格双向链表。

入站事件（channel_read）从 Head → Tail 传播，
出站指令（write）从 Tail → Head 传播。
"""

from app.context.context import ChannelHandlerContext
from core.domain.command import Command
from core.domain.event import Event
from core.ports.channel import Channel
from core.ports.context import Context
from core.ports.handler import Handler
from core.ports.pipline import Pipeline


class _HeadHandler(Handler):
    """Head 节点：入站入口，出站显式终端（直接发布到 EventBus）。"""

    async def channel_read(self, ctx: Context, event: Event) -> None:
        await ctx.fire_channel_read(event)

    async def write(self, ctx: Context, command: Command) -> None:
        # 显式终端：出站链到此结束，发布到 EventBus
        await ctx.pipeline.channel.write(command)


class _TailHandler(Handler):
    """Tail 节点：入站终点，出站入口。"""

    async def channel_read(self, ctx: Context, event: Event) -> None:
        pass

    async def write(self, ctx: Context, command: Command) -> None:
        await ctx.write(command)


class ChannelPipeline:
    """一条 Pipeline = 一个交易对。双向链表：Head ⇄ Handler ⇄ ... ⇄ Tail"""

    def __init__(self, channel: Channel):
        self.channel = channel
        self._head = ChannelHandlerContext("head", _HeadHandler(), self)
        self._tail = ChannelHandlerContext("tail", _TailHandler(), self)
        self._head.next = self._tail
        self._tail.prev = self._head

    def add_last(self, name: str, handler: Handler) -> Pipeline:
        ctx = ChannelHandlerContext(name, handler, self)
        prev = self._tail.prev
        prev.next = ctx
        ctx.prev = prev
        ctx.next = self._tail
        self._tail.prev = ctx
        return self

    async def fire_channel_active(self) -> None:
        await self._head.fire_channel_active()

    async def fire_channel_read(self, event: Event) -> None:
        await self._head.fire_channel_read(event)

    async def write(self, command: Command) -> None:
        await self._tail.write(command)

    async def fire_exception_caught(self, exc: Exception) -> None:
        await self._head.fire_exception_caught(exc)



