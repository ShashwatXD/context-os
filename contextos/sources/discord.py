"""Discord via a bot you add to your servers.

Limitation: Discord's API does not let any app read *your* DMs. Automating a user
account ("self-bot") breaks Discord's Terms of Service, so this only covers servers.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Iterator

import httpx

from contextos.config import Config
from contextos.models import Message

API = "https://discord.com/api/v10"
DISCORD_EPOCH_MS = 1420070400000
TEXT_CHANNEL_TYPES = {0, 5}  # text, announcement
# Discord channel/message types that are conversation (default message, reply, thread starter).
CONVERSATION_MESSAGE_TYPES = {0, 19, 21}


def snowflake_at(dt: datetime) -> int:
    """Discord IDs encode their creation time, so 'messages after time T' = 'after this ID'."""
    return (int(dt.timestamp() * 1000) - DISCORD_EPOCH_MS) << 22


class DiscordSource:
    name = "discord"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.warnings: list[str] = []

    def is_configured(self) -> bool:
        return bool(self.cfg.discord_token)

    def setup_hint(self) -> str:
        return "set DISCORD_BOT_TOKEN (see README → Discord setup)"

    def _get(self, client: httpx.Client, path: str, params: dict | None = None):
        for _ in range(6):
            r = client.get(API + path, params=params)
            if r.status_code == 429:
                time.sleep(float(r.json().get("retry_after", 1.0)) + 0.1)
                continue
            if r.status_code in (403, 404):
                return None  # the bot can't see this channel; skip it
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"Discord kept rate-limiting {path}")

    def fetch(self, since: datetime) -> Iterator[Message]:
        after = snowflake_at(since)
        headers = {"Authorization": f"Bot {self.cfg.discord_token}"}
        empty_content = total = 0

        with httpx.Client(headers=headers, timeout=30) as client:
            for guild in self._get(client, "/users/@me/guilds") or []:
                gid = guild["id"]
                channels = [c for c in (self._get(client, f"/guilds/{gid}/channels") or [])
                            if c["type"] in TEXT_CHANNEL_TYPES]
                threads = (self._get(client, f"/guilds/{gid}/threads/active") or {}).get("threads", [])
                parent_names = {c["id"]: c["name"] for c in channels}

                for ch in channels + threads:
                    # Skip channels with nothing new: saves one API call per quiet channel.
                    if not ch.get("last_message_id") or int(ch["last_message_id"]) <= after:
                        continue
                    is_thread = ch in threads
                    label = (f"{guild['name']} #{parent_names.get(ch.get('parent_id'), '?')} › {ch['name']}"
                             if is_thread else f"{guild['name']} #{ch['name']}")

                    cursor = after
                    while True:
                        batch = self._get(client, f"/channels/{ch['id']}/messages",
                                          {"after": str(cursor), "limit": 100}) or []
                        for raw in batch:
                            if raw.get("type", 0) not in CONVERSATION_MESSAGE_TYPES:
                                continue
                            msg = convert(raw, gid, ch["id"], label, is_thread, self.cfg.discord_user_id)
                            total += 1
                            if not raw.get("content") and not raw.get("attachments") and not raw.get("embeds"):
                                empty_content += 1
                            yield msg
                        if len(batch) < 100:
                            break
                        cursor = max(int(m["id"]) for m in batch)

        if total >= 5 and empty_content / total > 0.8:
            self.warnings.append(
                "Most Discord messages arrived empty: enable 'Message Content Intent' for your bot "
                "in the Discord Developer Portal (Bot tab)."
            )


def convert(raw: dict, gid: str, cid: str, channel: str, is_thread: bool, my_id: str) -> Message:
    author = raw.get("author", {})
    is_from_me = bool(my_id) and author.get("id") == my_id
    text = raw.get("content", "")
    for a in raw.get("attachments", []):
        text += f"\n[attached: {a.get('filename', 'file')}]"
    for e in raw.get("embeds", []):
        if e.get("title") or e.get("description"):
            text += f"\n[embed: {e.get('title', '')} {e.get('description', '')[:300]}]"
    if raw.get("message_reference", {}).get("message_id"):
        text = "(reply) " + text

    return Message(
        id=f"discord:{raw['id']}",
        source="discord",
        channel=channel,
        author="me" if is_from_me else (author.get("global_name") or author.get("username", "unknown")),
        ts=datetime.fromisoformat(raw["timestamp"]),
        text=text.strip(),
        thread_id=f"discord:thread:{cid}" if is_thread else None,
        url=f"https://discord.com/channels/{gid}/{cid}/{raw['id']}",
        is_to_me=bool(my_id) and not is_from_me and any(m.get("id") == my_id for m in raw.get("mentions", [])),
        is_from_me=is_from_me,
        is_automated=bool(author.get("bot")),
    )
