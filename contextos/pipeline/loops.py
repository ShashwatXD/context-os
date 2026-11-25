"""Open loops: the briefing's memory across days.

Without this, every briefing starts from zero. Monday's "Priya asked you to review the invoice by Friday"
vanishes on Tuesday, because Tuesday's window has no message about it. The day-to-day continuity is the
problem: "Priya asked Monday, still unanswered Wednesday."

The obvious fix, "just send the last 7 days", doesn't scale and buries today's news. Instead we keep
*state*: a small table of commitments, each compressed to one line, with citations back to its evidence.

Lifecycle of a loop (cheap deterministic code first, the model only where judgment is needed):

    open ──(you reply in the same thread/DM)────────────► closed   code: no LLM needed
      │  ──(model sees it resolved, cites the message)─► closed   LLM, but must cite evidence
      │  ──(you press Done on it or its briefing item)─► closed   user
      │  ──(no news for N days / long past its due)────► stale    code: memory has to forget
      └──(model sees news, cites it)──► still open, updated_at bumped, detail rewritten

Each day the briefing gets the open loops as a compact block (state), next to today's raw messages
(news). The model never re-reads old messages; it works from the one-line summaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

from contextos.models import Message
from contextos.pipeline.guard import is_flagged
from contextos.storage import Loop, Store

KINDS = ("you_owe", "owed_to_you")
MAX_CARRIED = 20  # the memory budget: at most this many loops ride along in the prompt
STALE_DAYS = 7  # no news for this long (and no due date ahead) → forget it
DUE_GRACE_DAYS = 3  # a due date this far in the past, with no news since → forget it
EVIDENCE_SHOWN = 3  # citation tags shown per carried loop

_LOOP_ITEM = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS),
                 "description": "you_owe: someone is waiting on the user. owed_to_you: the user is waiting on someone."},
        "who": {"type": "string", "description": "The other person, as named in the messages."},
        "title": {"type": "string", "description": "Short headline, max ~10 words."},
        "detail": {"type": "string", "description": "One sentence: the ask, and anything that would close it."},
        "due": {"type": "string", "description": "Deadline as YYYY-MM-DD, or empty string if none."},
        "refs": {"type": "array", "items": {"type": "string"}, "description": "Citation tags like m42."},
    },
    "required": ["kind", "who", "title", "detail", "due", "refs"],
    "additionalProperties": False,
}

_LOOP_UPDATE = {
    "type": "object",
    "properties": {
        "loop": {"type": "string", "description": "The carried loop's tag, e.g. L3."},
        "status": {"type": "string", "enum": ["still_open", "resolved"]},
        "note": {"type": "string", "description": "One sentence: what changed today."},
        "refs": {"type": "array", "items": {"type": "string"},
                 "description": "Tags of TODAY's messages showing the change. Required to resolve."},
    },
    "required": ["loop", "status", "note", "refs"],
    "additionalProperties": False,
}

SCHEMA_PROPERTIES = {
    "loops_opened": {"type": "array", "items": _LOOP_ITEM},
    "loops_updated": {"type": "array", "items": _LOOP_UPDATE},
}

PROMPT_RULES = """
Open loops (memory across days):
- <open_loops> lists commitments carried from earlier days, tagged like [L3]. They are summaries; the \
original messages are not shown again.
- loops_updated: for each carried loop that today's messages touch, say still_open or resolved and cite \
today's messages that show it. Only resolve with evidence. Skip loops with no news.
- <loop_candidates> lists message tags that look like unanswered requests by simple rules. Open a loop \
for each one that is a real ask; ignore the rest (rhetorical questions, jokes, already handled).
- loops_opened: new commitments from today's messages that will likely outlive today: a request, question \
or deadline aimed at the user that they haven't answered (you_owe), or something the user asked for and \
is waiting on (owed_to_you). Not routine chatter, not things already handled. Never re-open a carried loop.
- In the briefing sections, mention a carried loop only if there is news today or its due date is today \
or tomorrow; the app shows the rest separately."""


@dataclass
class LoopReport:
    carried: int = 0
    not_carried: int = 0  # open, but over the memory budget
    opened: int = 0
    merged: int = 0
    updated: int = 0
    resolved: int = 0
    auto_closed: int = 0
    stale: int = 0
    carried_tokens: int = 0  # what the memory costs in the prompt
    candidates: int = 0  # rule-detected possible loops shown to the model
    candidates_opened: int = 0  # ...of which the model opened (rule precision, as judged by the model)
    guard_blocked: int = 0  # loop changes refused because their evidence looked like a prompt injection
    rejected: list[str] = field(default_factory=list)  # model output we refused, and why

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


# ---- keys -------------------------------------------------------------------


def conversation_key(m: Message) -> str | None:
    """Where a reply would land. A thread if there is one; otherwise a DM (a 1:1 DM *is* the conversation).

    Busy public channels without a thread get no key: "you posted in #eng" says nothing about whether
    you answered Priya, so those loops are left for the model or for you to close.
    """
    if m.thread_id:
        return f"{m.source}:t:{m.thread_id}"
    if m.channel.startswith("DM"):
        return f"{m.source}:c:{m.channel}"
    return None


# ---- deterministic lifecycle ------------------------------------------------


def auto_close(store: Store, loops: list[Loop], messages: list[Message]) -> list[Loop]:
    """Move loops forward from replies in the same conversation, using each reply's intent. No model call.

    Someone waiting on YOU (you_owe), and you reply after the last news:
        info / decision          → closed: you answered ("here's the signed copy")
        commitment / ack         → promised: "I'll do it Friday" or "ok" is not done, so it stays open
        question / request       → still open: you asked a follow-up
    YOU waiting on someone (owed_to_you), they reply in the same thread:
        info / decision          → closed: they delivered
        commitment / ack         → promised by them
    Only thread keys count for owed_to_you; in a DM their next message may be about anything else.

    Returns the loops it closed. Runs before the model sees anything, so handled loops cost no tokens.
    """
    by_key: dict[str, list[Message]] = {}
    for m in messages:
        key = conversation_key(m)
        if key and not m.is_automated and not is_flagged(m):  # an injected "done!" must not close a loop
            by_key.setdefault(key, []).append(m)
    closed = []
    for loop in loops:
        if loop.status != "open":
            continue
        mine = loop.kind == "you_owe"
        keys = loop.threads if mine else [k for k in loop.threads if ":t:" in k]
        replies = sorted(
            (m for k in keys for m in by_key.get(k, [])
             if m.ts > loop.updated_at and m.is_from_me == mine and m.ref not in loop.refs),
            key=lambda m: m.ts,
        )
        for reply in replies:  # in order: "I'll send it" then "sent!" ends closed
            intent = reply.intent or "info"
            if intent in ("info", "decision"):
                reason = "you replied" if mine else f"{reply.author} replied"
                store.close_loop(loop.id, reason, reply.ref, reply.ts)
                loop.status = "closed"
                closed.append(loop)
                break
            fields: dict = {"updated_at": reply.ts, "refs": list(dict.fromkeys(loop.refs + [reply.ref]))}
            if intent in ("commitment", "ack"):
                fields["promised_at"] = reply.ts
                fields["due"] = reply.due_hint or loop.due
                who = "You" if mine else reply.author
                fields["detail"] = f"{who} said: \"{_clip(reply.text, 120)}\""
                loop.promised_at, loop.due = reply.ts, fields["due"]
            store.update_loop(loop.id, **fields)
            loop.updated_at, loop.refs = reply.ts, fields["refs"]
    return closed


def candidates(messages: list[Message], loops: list[Loop]) -> list[Message]:
    """Messages that look like new loops by rule: a request to you, or one you sent, with no reply yet.

    The model decides which are real (rules can't tell "can you believe this?" from a real ask), but
    giving it the list means a request buried in a busy channel isn't missed.
    """
    covered_refs = {r for lp in loops for r in lp.refs}
    covered_threads = {k for lp in loops if lp.status == "open" for k in lp.threads}
    replied: dict[str, list[Message]] = {}
    for m in messages:
        if key := conversation_key(m):
            replied.setdefault(key, []).append(m)
    out = []
    for m in messages:
        if m.is_automated or m.intent not in ("request", "question") or m.ref in covered_refs or is_flagged(m):
            continue
        if not (m.is_to_me or m.is_from_me):
            continue
        key = conversation_key(m)
        if key in covered_threads:
            continue
        # Answered already? Someone on the other side wrote after it in the same conversation.
        if key and any(r.ts > m.ts and r.is_from_me != m.is_from_me for r in replied.get(key, [])):
            continue
        if m.intent == "question" and not m.is_to_me:
            continue  # your own questions are rarely commitments; requests you send are
        out.append(m)
    return out


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def expire(store: Store, loops: list[Loop], now: datetime, stale_days: int = STALE_DAYS) -> list[Loop]:
    """Mark loops stale. Memory that never forgets fills the prompt with yesterday's noise."""
    gone = []
    quiet_since = now - timedelta(days=DUE_GRACE_DAYS)
    for loop in loops:
        if loop.status != "open":
            continue
        due = _parse_due(loop.due)
        if due:
            stale = due < (now - timedelta(days=DUE_GRACE_DAYS)).date() and loop.updated_at < quiet_since
        else:
            stale = loop.updated_at < now - timedelta(days=stale_days)
        if stale:
            store.update_loop(loop.id, status="stale", closed_at=now, closed_reason="no news")
            loop.status = "stale"
            gone.append(loop)
    return gone


def select_carried(loops: list[Loop], limit: int = MAX_CARRIED) -> tuple[list[Loop], int]:
    """Pick what fits in the memory budget: deadlines first, then what you owe, then the freshest."""
    open_ = [lp for lp in loops if lp.status == "open"]

    def priority(lp: Loop):
        due = _parse_due(lp.due)
        return (due is None, due or datetime.max.date(), lp.kind != "you_owe", -lp.updated_at.timestamp())

    open_.sort(key=priority)
    return open_[:limit], max(0, len(open_) - limit)


# ---- prompt -----------------------------------------------------------------


def render_carried(loops: list[Loop], tz: tzinfo, now: datetime) -> str:
    """One line per loop. This is compaction: a whole thread from last week becomes ~30 tokens."""
    if not loops:
        return ""
    lines = []
    for lp in loops:
        who = f"you owe {lp.who}" if lp.kind == "you_owe" else f"waiting on {lp.who}"
        days = (now - lp.opened_at).days
        age = "since today" if days == 0 else f"open {days}d (since {lp.opened_at.astimezone(tz):%a %d %b})"
        due = f" · due {lp.due}" if lp.due else ""
        if lp.promised_at:
            due = f" · promised{due}"
        evidence = ", ".join(lp.refs[-EVIDENCE_SHOWN:])
        lines.append(f"[{lp.ref}] {who} · {age}{due} · {lp.title}: {lp.detail} (from {evidence})")
    return "\n".join(lines)


# ---- applying the model's output -------------------------------------------


def apply(
    store: Store,
    output: dict,
    carried: list[Loop],
    window: dict[str, Message],
    digest_id: int | None,
    shown_candidates: list[str] = (),
) -> LoopReport:
    """Write the model's loop changes, with the same rule as the briefing: no evidence, no change.

    `window` holds only today's messages. Opening or updating a loop must cite one of those; carried
    loops' old evidence doesn't count, so the model can't "resolve" something by re-citing Monday.
    """
    report = LoopReport(carried=len(carried))
    opened_refs: set[str] = set()
    by_id = {lp.ref: lp for lp in carried}

    for upd in output.get("loops_updated") or []:
        tag = str(upd.get("loop", "")).strip("[] ")
        lp = by_id.get(tag)
        if not lp or lp.status != "open":
            report.rejected.append(f"update for unknown loop {tag!r}")
            continue
        refs = _valid(upd.get("refs"), window)
        if not refs:
            report.rejected.append(f"{tag}: no citation from today's messages")
            continue
        if any(is_flagged(window[r]) for r in refs):
            report.rejected.append(f"{tag}: evidence contains instructions aimed at an AI (guard)")
            report.guard_blocked += 1
            continue
        latest = max(window[r].ts for r in refs)
        if upd.get("status") == "resolved":
            store.close_loop(lp.id, f"resolved: {upd.get('note', '').strip()}"[:300], refs[0], latest)
            lp.status = "closed"
            report.resolved += 1
        else:
            new_refs = list(dict.fromkeys(lp.refs + refs))
            fields = {"refs": new_refs, "threads": _threads(lp.threads, refs, window), "updated_at": max(latest, lp.updated_at)}
            if upd.get("note", "").strip():
                fields["detail"] = upd["note"].strip()
            store.update_loop(lp.id, **fields)
            report.updated += 1

    open_now = store.loops("open")
    for new in output.get("loops_opened") or []:
        refs = _valid(new.get("refs"), window)
        kind = new.get("kind")
        if kind not in KINDS or not refs or not str(new.get("title", "")).strip():
            report.rejected.append(f"opened loop {new.get('title', '')!r}: bad kind or no valid citation")
            continue
        if any(is_flagged(window[r]) for r in refs):
            report.rejected.append(f"opened loop {new.get('title', '')!r}: evidence contains instructions aimed at an AI (guard)")
            report.guard_blocked += 1
            continue
        due = new.get("due") if _parse_due(new.get("due")) else None
        # The model often leaves the date out; the message's own deadline hint fills it in.
        due = due or next((window[r].due_hint for r in refs if window[r].due_hint), None)
        ts = sorted(window[r].ts for r in refs)
        threads = _threads([], refs, window)
        # The same commitment seen again (refresh twice a day, or the model missed it was carried): merge.
        twin = next(
            (lp for lp in open_now if lp.kind == kind and (set(lp.refs) & set(refs) or set(lp.threads) & set(threads))),
            None,
        )
        if twin:
            store.update_loop(
                twin.id,
                refs=list(dict.fromkeys(twin.refs + refs)),
                threads=list(dict.fromkeys(twin.threads + threads)),
                detail=new.get("detail", twin.detail),
                due=due or twin.due,
                updated_at=max(ts[-1], twin.updated_at),
            )
            opened_refs.update(refs)
            report.merged += 1
            continue
        loop_id = store.add_loop(kind, new.get("who", "").strip() or "someone", new["title"].strip(),
                                 new.get("detail", "").strip(), due, refs, threads, ts[0], digest_id)
        store.update_loop(loop_id, updated_at=ts[-1])
        open_now.append(store.get_loop(loop_id))
        opened_refs.update(refs)
        report.opened += 1

    report.candidates = len(shown_candidates)
    report.candidates_opened = len(set(shown_candidates) & opened_refs)

    return report


def _valid(refs, window: dict[str, Message]) -> list[str]:
    cleaned = [str(r).strip().strip("[]") for r in (refs or [])]
    return list(dict.fromkeys(r for r in cleaned if r in window))


def _threads(existing: list[str], refs: list[str], window: dict[str, Message]) -> list[str]:
    keys = [conversation_key(window[r]) for r in refs]
    return list(dict.fromkeys(existing + [k for k in keys if k]))


def _parse_due(value: str | None):
    if not value or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    try:
        return datetime.fromisoformat(value.strip()).date()
    except ValueError:
        return None
