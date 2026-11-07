"""The one data shape every source is normalized into."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    id: str  # globally unique: "<source>:<native id>"
    source: str  # "gmail" | "slack" | "discord"
    channel: str  # "Inbox", "#eng", "DM: Alice", "My Server #general"
    author: str
    ts: datetime  # timezone-aware
    text: str
    title: str | None = None  # email subject
    thread_id: str | None = None  # messages sharing this are one conversation
    url: str | None = None  # deep link back to the original
    is_to_me: bool = False  # DM, @mention, or I'm a direct email recipient
    is_from_me: bool = False
    is_automated: bool = False  # bot, newsletter, no-reply, notification
    labels: list[str] = field(default_factory=list)
    rid: int | None = None  # short numeric id assigned by the store; used as citation [m<rid>]

    @property
    def ref(self) -> str:
        if self.rid is None:
            raise ValueError(f"message {self.id} has not been stored yet")
        return f"m{self.rid}"
