"""Turn stored briefings, actions and answers into what the templates render."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo

from markupsafe import Markup, escape

from contextos.models import Message
from contextos.pipeline.digest import SECTIONS
from contextos.storage import DigestRecord, ItemAction, Store

SECTION_INFO = {
    "needs_you": ("Needs you", "📌"),
    "important": ("Important", "⚡"),
    "fyi": ("FYI", "📰"),
}
SOURCE_ICON = {"gmail": "✉️", "slack": "💬", "discord": "🎮"}


def item_key(item: dict) -> str:
    refs = sorted(item.get("refs") or [])
    if refs:
        return ",".join(refs)
    return "t:" + hashlib.sha1(item.get("title", "").encode()).hexdigest()[:10]


@dataclass
class Source:
    label: str
    url: str | None
    icon: str
    tooltip: str


@dataclass
class ItemView:
    key: str
    section: str
    digest_id: int
    title: str
    detail: str
    sources: list[Source]
    unverified: bool = False
    state: str = "open"  # open | done | snoozed
    until: datetime | None = None
    vote: int | None = None
    origin: str | None = None  # for reminders: when it was first seen


@dataclass
class SectionView:
    key: str
    title: str
    icon: str
    open: list[ItemView] = field(default_factory=list)
    done: list[ItemView] = field(default_factory=list)
    snoozed: list[ItemView] = field(default_factory=list)


def item_state(key: str, refs: list[str], actions: list[ItemAction], now: datetime) -> tuple[str, datetime | None]:
    """The newest action covering this item decides its state.

    An action covers an item if it was taken on the same item, or on an item whose citations include all
    of this item's citations. So if a new message joins the topic, the item reappears: there's news.
    """
    wanted = set(refs)
    for a in actions:
        if a.item_key == key or (wanted and wanted <= set(a.refs)):
            if a.action == "done":
                return "done", None
            if a.action == "snooze" and a.until and a.until > now:
                return "snoozed", a.until
            return "open", None
    return "open", None


def sources_for(refs: list[str], messages: dict[str, Message], tz: tzinfo) -> list[Source]:
    out = []
    for r in refs:
        m = messages.get(r)
        if not m:
            continue
        when = m.ts.astimezone(tz)
        label = f"{m.channel} · {when:%H:%M}"
        tooltip = f"{m.author}: {(m.title + ' · ') if m.title else ''}{m.text[:160]}"
        out.append(Source(label, m.url, SOURCE_ICON.get(m.source, "•"), tooltip))
    return out


def make_item(
    item: dict,
    section: str,
    digest_id: int,
    messages: dict[str, Message],
    tz: tzinfo,
    actions: list[ItemAction],
    votes: dict[str, int],
    now: datetime,
) -> ItemView:
    key = item_key(item)
    state, until = item_state(key, item.get("refs", []), actions, now)
    return ItemView(
        key=key,
        section=section,
        digest_id=digest_id,
        title=item.get("title", ""),
        detail=item.get("detail", ""),
        sources=sources_for(item.get("refs", []), messages, tz),
        unverified=bool(item.get("unverified")),
        state=state,
        until=until,
        vote=votes.get(key),
    )


def digest_view(store: Store, rec: DigestRecord, tz: tzinfo, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    refs = [r for s in SECTIONS for it in rec.output.get(s, []) for r in it.get("refs", [])]
    actions = store.actions()
    reminders = reminder_items(store, actions, rec, tz, now)
    messages = store.by_refs(refs)
    votes = store.votes(rec.id)

    sections = []
    for s in SECTIONS:
        title, icon = SECTION_INFO[s]
        view = SectionView(s, title, icon)
        for raw in rec.output.get(s, []):
            item = make_item(raw, s, rec.id, messages, tz, actions, votes, now)
            getattr(view, item.state).append(item)
        sections.append(view)

    return {
        "digest": rec,
        "headline": rec.output.get("headline", ""),
        "sections": sections,
        "reminders": reminders,
        "stats": rec.meta.get("stats", {}),
        "cost": (rec.meta.get("llm") or {}).get("cost_usd"),
        "llm_tokens": (rec.meta.get("llm") or {}).get("total_tokens"),
        "new_since": store.count_since(rec.end),
    }


def reminder_items(store: Store, actions: list[ItemAction], current: DigestRecord, tz: tzinfo, now: datetime) -> list[ItemView]:
    """Items snoozed from earlier briefings whose time has come."""
    current_keys = {item_key(it) for s in SECTIONS for it in current.output.get(s, [])}
    seen, out = set(), []
    for a in actions:
        if a.item_key in seen:
            continue
        seen.add(a.item_key)
        if a.action == "snooze" and a.until and a.until <= now and a.item_key not in current_keys:
            messages = store.by_refs(a.refs)
            view = make_item(a.item, "reminder", a.digest_id, messages, tz, [], {}, now)
            view.origin = a.created_at.astimezone(tz).strftime("%a %d %b")
            out.append(view)
    return out


def find_item(store: Store, digest_id: int, section: str, key: str) -> dict | None:
    if section == "reminder":
        return next((a.item for a in store.actions() if a.item_key == key), None)
    rec = store.get_digest(digest_id)
    if not rec:
        return None
    return next((it for it in rec.output.get(section, []) if item_key(it) == key), None)


def snooze_until(tz: tzinfo, morning_hour: int, now: datetime | None = None) -> datetime:
    now = (now or datetime.now(UTC)).astimezone(tz)
    tomorrow = (now + timedelta(days=1)).replace(hour=morning_hour, minute=0, second=0, microsecond=0)
    return tomorrow.astimezone(UTC)


# ---- answers ----------------------------------------------------------------

_REF = re.compile(r"\[(m\d+(?:\s*,\s*m\d+)*)\]|\bm(\d+)\b")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_BULLET = re.compile(r"^\s*[-*•]\s+")


def answer_html(text: str, messages: dict[str, Message], tz: tzinfo) -> Markup:
    """Light markdown (paragraphs, bullets, bold) with [m42] citations turned into source links."""

    def link(ref: str) -> str:
        m = messages.get(ref)
        if not m:
            return f'<span class="ref missing" title="not a message ContextOS showed the model">{ref}</span>'
        title = escape(f"{m.source} · {m.channel} · {m.ts.astimezone(tz):%a %H:%M} · {m.author}")
        href = escape(m.url or "#")
        label = escape(m.channel if len(m.channel) <= 20 else m.channel[:19] + "…")
        return (
            f'<a class="ref" href="{href}" target="_blank" rel="noopener" title="{title}">{SOURCE_ICON.get(m.source, "")} {label}</a>'
        )

    def inline(line: str) -> str:
        s = str(escape(line))
        s = _BOLD.sub(r"<strong>\1</strong>", s)

        def sub(match: re.Match) -> str:
            if match.group(1):
                return "".join(link(r.strip()) for r in match.group(1).split(","))
            return link(f"m{match.group(2)}")

        return _REF.sub(sub, s)

    html = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        if all(_BULLET.match(l) for l in lines if l.strip()):
            items = [inline(_BULLET.sub("", l)) for l in lines if l.strip()]
            html.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
        else:
            html.append("<p>" + "<br>".join(inline(l) for l in lines) + "</p>")
    return Markup("".join(html))


def ago(dt: datetime | None, now: datetime | None = None) -> str:
    if not dt:
        return "never"
    secs = ((now or datetime.now(UTC)) - dt).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"
