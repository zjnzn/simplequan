from core.domain.command import Command
from core.domain.event import Event
from core.ports.channel import Channel
from core.ports.context import Context
from core.ports.handler import Handler
from core.ports.pipline import Pipeline


class ChannelHandlerContext(Context):
    """双向链表节点。channel_read 向 next 传播，write 向 prev 传播。"""

    __slots__ = ("name", "handler", "pipeline", "prev", "next")

    def __init__(self,channel:Channel, handler: Handler, pipeline: Pipeline):

        self.channel = channel
        self.pipeline = pipeline
        self.handler = handler
        self.prev:Context = None
        self.next:Context = None

    async def fire_channel_active(self) -> None:
        """向 next 传播 channel_active。"""
        if self.next:
            await self.next.handler.channel_active(self.next)

    async def fire_channel_read(self, event: Event) -> None:
        """入站：传播到 next 的 channel_read（Head → Tail）。
        声明式过滤：handler.handles 非空且事件类型不匹配时，自动跳到下一个 handler。
        """
        nxt = self.next
        while nxt is not None:
            h = nxt.handler
            if h.handles and event.type not in h.handles:
                nxt = nxt.next
            else:
                await h.channel_read(nxt, event)
                return

    async def write(self, command: Command) -> None:
        """出站：向 prev 传播 write（Tail → Head）。
        声明式过滤：handler.handles_commands 非空且指令类型不匹配时，自动跳到前一个 handler。
        Head handler 是显式终端，直接调用 _publish_command。
        """
        prev = self.prev
        while prev is not None:
            h = prev.handler
            if h.handles_commands and command.type not in h.handles_commands:
                prev = prev.prev
            else:
                await h.write(prev, command)
                return
        # 不应到达这里：Head handler 应该是终端
        raise RuntimeError("write() reached a node with no prev — Head handler should be the terminal")

    async def fire_exception_caught(self, exc: Exception) -> None:
        """向 next 传播 exception_caught。"""
        if self.next:
            await self.next.handler.exception_caught(self.next, exc)
