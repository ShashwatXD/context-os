"""Source connectors. Each one turns a provider's API into a stream of `Message`s.

A source only has to implement:
    name: str
    is_configured() -> bool
    fetch(since: datetime) -> Iterator[Message]
"""

from __future__ import annotations

from contextos.config import Config


def all_sources(cfg: Config) -> list:
    from contextos.sources.discord import DiscordSource
    from contextos.sources.gmail import GmailSource
    from contextos.sources.slack import SlackSource

    return [GmailSource(cfg), SlackSource(cfg), DiscordSource(cfg)]
