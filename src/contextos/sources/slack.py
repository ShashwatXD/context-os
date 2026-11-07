"""Slack via a user token (xoxp-...): reads what *you* can see, including DMs."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

from contextos.config import Config
from contextos.models import Message

# Membership and housekeeping events, not conversation.
SKIP_SUBTYPES = {
    "channel_join",
    "channel_leave",
    "channel_topic",
    "channel_purpose",
    "channel_name",
    "channel_archive",
    "channel_unarchive",
    "group_join",
    "group_leave",
    "bot_add",
    "bot_remove",
    "pinned_item",
    "unpinned_item",
    "reminder_add",
}


class SlackSource:
    name = "slack"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def is_configured(self) -> bool:
        return bool(self.cfg.slack_token)

    def setup_hint(self) -> str:
        return "set SLACK_USER_TOKEN (see README → Slack setup)"

    def fetch(self, since: datetime) -> Iterator[Message]:
        from slack_sdk import WebClient
        from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

        client = WebClient(token=self.cfg.slack_token)
        client.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=5))

        auth = client.auth_test()
        my_id = auth["user_id"]
        base_url = auth["url"].rstrip("/")
        oldest = f"{since.timestamp():.6f}"

        names: dict[str, str] = {}

        def user_name(uid: str) -> str:
            if uid not in names:
                try:
                    u = client.users_info(user=uid)["user"]
                    p = u.get("profile", {})
                    names[uid] = p.get("display_name") or p.get("real_name") or u.get("name") or uid
                except Exception:
                    names[uid] = uid
            return names[uid]

        conversations = []
        for page in client.users_conversations(types="public_channel,private_channel,mpim,im", exclude_archived=True, limit=200):
            conversations += page["channels"]

        for conv in conversations:
            cid = conv["id"]
            channel = channel_label(conv, user_name)
            is_dm = bool(conv.get("is_im"))

            for page in client.conversations_history(channel=cid, oldest=oldest, limit=200):
                for raw in page["messages"]:
                    if raw.get("subtype") in SKIP_SUBTYPES:
                        continue
                    yield convert(raw, cid, channel, is_dm, my_id, base_url, user_name)

                    # Thread replies don't appear in channel history; fetch them separately.
                    if raw.get("reply_count") and float(raw.get("latest_reply", 0)) > since.timestamp():
                        for rpage in client.conversations_replies(channel=cid, ts=raw["ts"], oldest=oldest, limit=200):
                            for reply in rpage["messages"]:
                                if reply["ts"] == raw["ts"] or reply.get("subtype") in SKIP_SUBTYPES:
                                    continue
                                yield convert(reply, cid, channel, is_dm, my_id, base_url, user_name)


def channel_label(conv: dict, user_name: Callable[[str], str]) -> str:
    if conv.get("is_im"):
        return f"DM: {user_name(conv['user'])}"
    if conv.get("is_mpim"):
        return "Group DM"
    return f"#{conv.get('name', conv['id'])}"


def convert(
    raw: dict,
    cid: str,
    channel: str,
    is_dm: bool,
    my_id: str,
    base_url: str,
    user_name: Callable[[str], str],
) -> Message:
    ts = raw["ts"]
    thread_ts = raw.get("thread_ts", ts)
    uid = raw.get("user")
    is_from_me = uid == my_id
    author = "me" if is_from_me else (user_name(uid) if uid else raw.get("username") or raw.get("bot_profile", {}).get("name", "bot"))
    text = format_text(raw.get("text", ""), user_name)
    for f in raw.get("files", []) or []:
        text += f"\n[attached: {f.get('name') or f.get('title') or 'file'}]"

    url = f"{base_url}/archives/{cid}/p{ts.replace('.', '')}"
    if thread_ts != ts:
        url += f"?thread_ts={thread_ts}&cid={cid}"

    return Message(
        id=f"slack:{cid}:{ts}",
        source="slack",
        channel=channel,
        author=author,
        ts=datetime.fromtimestamp(float(ts), UTC),
        text=text.strip(),
        thread_id=f"slack:{cid}:{thread_ts}",
        url=url,
        is_to_me=not is_from_me and (is_dm or f"<@{my_id}>" in raw.get("text", "")),
        is_from_me=is_from_me,
        is_automated=bool(raw.get("bot_id")) or raw.get("subtype") == "bot_message",
    )


def format_text(text: str, user_name: Callable[[str], str]) -> str:
    """Slack's markup → plain text: <@U1> → @name, <#C1|eng> → #eng, <url|label> → label (url)."""
    text = re.sub(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>", lambda m: "@" + user_name(m.group(1)), text)
    text = re.sub(r"<#[A-Z0-9]+\|([^>]*)>", r"#\1", text)
    text = re.sub(r"<!(here|channel|everyone)[^>]*>", r"@\1", text)
    text = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2 (\1)", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
