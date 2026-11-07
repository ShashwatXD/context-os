import base64
from datetime import datetime, timezone

from contextos.sources import discord, gmail, slack


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def gmail_raw(headers: dict, parts: list, labels=("INBOX",)) -> dict:
    return {
        "id": "abc", "threadId": "th1", "internalDate": "1762527600000", "labelIds": list(labels),
        "snippet": "snippet text",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [{"name": k, "value": v} for k, v in headers.items()],
            "parts": parts,
        },
    }


def test_gmail_prefers_plain_text_and_strips_quotes():
    body = "Can you review the contract?\n\nOn Mon, 3 Nov 2026 at 10:00, Sam <sam@x.com> wrote:\n> old stuff"
    raw = gmail_raw(
        {"From": "Priya Shah <priya@acme.com>", "To": "sam@x.com", "Subject": "Contract"},
        [{"mimeType": "text/plain", "body": {"data": b64(body)}},
         {"mimeType": "text/html", "body": {"data": b64("<p>ignored</p>")}}],
    )
    m = gmail.parse_message(raw, "sam@x.com")
    assert m.text == "Can you review the contract?"
    assert m.author == "Priya Shah" and m.title == "Contract"
    assert m.is_to_me and not m.is_automated and not m.is_from_me
    assert m.thread_id == "gmail:th1" and "th1" in m.url


def test_gmail_html_fallback_and_newsletter_detection():
    raw = gmail_raw(
        {"From": "news@shop.com", "To": "sam@x.com", "Subject": "Sale", "List-Unsubscribe": "<mailto:x>"},
        [{"mimeType": "text/html", "body": {"data": b64("<style>.a{}</style><p>Big</p><p>sale</p>")}}],
        labels=("INBOX", "CATEGORY_PROMOTIONS"),
    )
    m = gmail.parse_message(raw, "sam@x.com")
    assert m.text == "Big\nsale"
    assert m.is_automated and not m.is_to_me


def test_gmail_sent_is_from_me():
    raw = gmail_raw({"From": "Sam <sam@x.com>", "To": "a@b.com", "Subject": "Re: hi"},
                    [{"mimeType": "text/plain", "body": {"data": b64("done")}}], labels=("SENT",))
    m = gmail.parse_message(raw, "sam@x.com")
    assert m.is_from_me and m.author == "me" and m.channel == "Sent"


def test_slack_format_and_convert():
    names = {"U1": "alice", "U2": "sam"}.get
    text = "hey <@U2> see <https://x.com|the doc> in <#C9|eng> &amp; <!here>"
    assert slack.format_text(text, names) == "hey @sam see the doc (https://x.com) in #eng & @here"

    raw = {"ts": "1762527600.000100", "thread_ts": "1762527000.000000", "user": "U1", "text": "ping <@U2>"}
    m = slack.convert(raw, "C9", "#eng", False, "U2", "https://acme.slack.com", names)
    assert m.is_to_me and not m.is_from_me
    assert m.thread_id == "slack:C9:1762527000.000000"
    assert m.url == "https://acme.slack.com/archives/C9/p1762527600000100?thread_ts=1762527000.000000&cid=C9"


def test_slack_dm_and_bot():
    names = {"U1": "alice"}.get
    dm = slack.convert({"ts": "1.0", "user": "U1", "text": "hi"}, "D1", "DM: alice", True, "U2", "https://a", names)
    assert dm.is_to_me
    bot = slack.convert({"ts": "2.0", "bot_id": "B1", "username": "deploybot", "text": "ok"},
                        "C1", "#ops", False, "U2", "https://a", names)
    assert bot.is_automated and bot.author == "deploybot"


def test_discord_snowflake_roundtrip():
    dt = datetime(2026, 11, 7, tzinfo=timezone.utc)
    sf = discord.snowflake_at(dt)
    assert ((sf >> 22) + discord.DISCORD_EPOCH_MS) == int(dt.timestamp() * 1000)


def test_discord_convert():
    raw = {
        "id": "123", "timestamp": "2026-11-07T10:00:00.000000+00:00", "content": "ship it?",
        "author": {"id": "u9", "username": "bob", "global_name": "Bob"},
        "mentions": [{"id": "me1"}], "attachments": [{"filename": "plan.pdf"}],
    }
    m = discord.convert(raw, "g1", "c1", "Server #general", False, "me1")
    assert m.author == "Bob" and m.is_to_me and "[attached: plan.pdf]" in m.text
    assert m.url == "https://discord.com/channels/g1/c1/123"
