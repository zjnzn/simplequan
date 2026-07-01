from typing import Protocol, runtime_checkable

from core.domain.command import Command
from core.domain.event import Event
from core.ports.channel import Channel
from core.ports.handler import Handler
from core.ports.pipline import Pipeline

@runtime_checkable
class Context(Protocol):

    pipeline:Pipeline
    channel:Channel
    handler:Handler
    prev:Context
    next:Context


    async def fire_channel_active(self) -> None:...

    async def fire_channel_read(self, event: Event) -> None:...

    async def write(self, command: Command) -> None:...

    async def fire_exception_caught(self, exc: Exception) -> None:...
