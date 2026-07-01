"""Channel —— 只认 EventBus，从不持有交易所对象。

每个 symbol 一个实例。通过 EventBus 订阅数据、发布指令。
"""
from core.domain.command import Command
from __future__ import annotations

class Channel:
    """Netty 风格 Channel。只认 EventBus，不持有任何交易所连接。"""

    # ---------------- 入站：订阅 EventBus 上的 data topic ----------------
    # ExchangeConnector 已将数据包装为 ChannelEvent，Channel 只转发

    def read(self, timeframe: str) -> Channel:...

    # ---------------- 出站：写指令，通过 Pipeline 后发布到 EventBus ----------------

    async def write(self, command: Command) -> None:...

    # ---------------- 生命周期 ----------------

    async def close(self) -> None:...
