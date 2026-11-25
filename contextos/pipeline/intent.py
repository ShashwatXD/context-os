"""What a message is *for*: tagged once, at storage time, with plain rules (no model call).

    request     "can you approve the invoice?"      someone wants something done
    question    "are we still on for Thursday?"     someone wants an answer
    commitment  "I'll send it by Friday"             someone promised something
    decision    "we're going with vendor B"          something got settled
    ack         "thanks" / "ok" / "👍" / "lgtm"      no content, only acknowledgement
    info        everything else

Why bother, when the model can read the message anyway?
  * Loops get a lifecycle code can trust. "I'll look tomorrow" is a reply but not an answer, so it must
    not close the loop; "here's the file" in the same thread is, so it can.
  * Context gets shorter. Acks in channels you're not part of carry nothing, so they're dropped before
    the model sees them, and they aren't embedded (an "ok thanks" vector only pollutes meaning search).
  * The model gets a hint next to each message (`request`, `due 2026-11-13`), which is cheaper and
    more consistent than asking it to rediscover the same thing every day.

The rules are deliberately conservative: when unsure, a message is `info`, which changes nothing.
Includes common Hinglish phrasings, since real chats mix languages.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from contextos.models import Message

INTENTS = ("request", "question", "commitment", "decision", "ack", "info")

_ACK_WORDS = (
    r"thanks?( a lot| so much)?|thank you( so much)?|thx|ty|tysm|ok(ay)?|okk+|k|kk|cool|great|nice|awesome|perfect|"
    r"got it|noted|sure|sounds good|makes sense|lgtm|done|will check|np|no worries|yes|yep|yup|ack|"
    r"haan|ha+n|ji|theek hai|thik hai?|thik h|acha|accha|achha|ok bhai|done bhai|shukriya|dhanyavaad"
)
_ACK = re.compile(rf"^\s*(@\w+\s*)?({_ACK_WORDS})(\s+({_ACK_WORDS}))*[\s!.,:)\-]*$", re.I)

_REQUEST = re.compile(
    r"\b(can|could|would|will) (you|u)\b|\bplease\b|\bpls\b|\bplz\b|\bkindly\b|\bneed you to\b|"
    r"\bwould you mind\b|\bmind (sending|checking|reviewing|taking)\b|\bwaiting (for|on) your\b|\blet me know\b|"
    r"\b(review|approve|sign|send|share|check|confirm|fill|update) (this|the|it|my|our)\b.*\b(by|before|asap|eod|today|tomorrow)\b|"
    r"\b(kar do|kar dena|kardo|kardena|bhej do|bhej dena|dekh lo|dekh lena|bata do|batao|bhejo)\b",
    re.I,
)
_COMMITMENT = re.compile(
    r"\b(i'?ll|i will|i'?m going to|i am going to|gonna|will do|on it|i'?m on it|let me (check|look|get|see|find)|"
    r"i can (do|send|take|have)|will (send|share|check|review|update|get back|look)|i'?ll get back|"
    r"kar dunga|kar dungi|kar deta|kar deti|bhej dunga|bhej dungi|dekh leta|dekh leti|dekhta hu|dekhti hu)\b",
    re.I,
)
_DECISION = re.compile(
    r"\b(we('ve| have)? decided|decided to|we'?re going with|going ahead with|let'?s go with|final(i[sz]ed)? (call|decision)|"
    r"approved|agreed|ship it|confirmed for|is confirmed|has been approved|tay hua|final hai)\b",
    re.I,
)
# Question words that make a question even without "?" ("kab tak hoga", "any update on X").
# Auxiliaries (is, will, can...) don't count on their own: "Will share the recording later" is a promise.
_QUESTION_START = re.compile(
    r"^\s*(who|what|when|where|why|how|which|any update|kya|kab|kaise|kaun|kahan|kyu|kyun|kitna)\b",
    re.I,
)
_URL = re.compile(r"https?://\S+")


def classify(m: Message) -> str:
    text = _URL.sub("", f"{m.text}").strip()
    if m.is_automated:
        return "info"
    if len(text) <= 40 and "?" not in text:
        core = re.sub(r":[a-z0-9_+\-]+:|[^\w\s']", " ", text).strip()  # drop emoji and :shortcodes:
        if (text and not core) or _ACK.match(core):
            return "ack"
    # Look mostly at the start: long emails quote, sign off and wander.
    head = text[:600]
    order = (
        ("commitment", "request", "decision", "question")
        if m.is_from_me
        else ("request", "decision", "question", "commitment")
    )
    for intent in order:
        if intent == "request" and _REQUEST.search(head):
            return "request"
        if intent == "commitment" and _COMMITMENT.search(head):
            return "commitment"
        if intent == "decision" and _DECISION.search(head):
            return "decision"
        if intent == "question" and ("?" in head or _QUESTION_START.match(head)):
            return "question"
    return "info"


# ---- deadlines --------------------------------------------------------------

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_DAY_WORDS = {
    "today": 0, "tonight": 0, "eod": 0, "end of day": 0, "aaj": 0,
    "tomorrow": 1, "tmrw": 1, "tmr": 1, "kal": 1,  # "kal" is ambiguous (yesterday/tomorrow); in a deadline it's tomorrow
}
_DUE_CONTEXT = re.compile(r"\b(by|before|until|till|due|deadline|on|for|eod|tak|se pehle)\b", re.I)


def due_hint(m: Message) -> str | None:
    """A deadline mentioned in the message, as YYYY-MM-DD, resolved against when it was sent."""
    text = m.text[:600].lower()
    if not _DUE_CONTEXT.search(text) and not re.search(r"\b(today|tomorrow|tonight|eod|aaj|kal|next week)\b", text):
        return None
    sent: date = m.ts.date()

    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso:
        try:
            return date(int(iso[1]), int(iso[2]), int(iso[3])).isoformat()
        except ValueError:
            pass

    month = "|".join(_MONTHS)
    md = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month})[a-z]*\b|\b({month})[a-z]*\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", text)
    if md:
        day, mon = (md[1], md[2]) if md[1] else (md[4], md[3])
        try:
            d = date(sent.year, _MONTHS.index(mon[:3]) + 1, int(day))
            return (d if d >= sent else d.replace(year=d.year + 1)).isoformat()
        except ValueError:
            pass

    for word, offset in _DAY_WORDS.items():
        hit = re.search(rf"\b{word}\b", text)
        # "the logs from today" is not a deadline
        if hit and not re.search(r"\b(from|since|of|in|yesterday's)\s*$", text[: hit.start()]):
            return (sent + timedelta(days=offset)).isoformat()

    wd = re.search(rf"\b(next\s+)?({'|'.join(_WEEKDAYS)}|mon|tue|wed|thu|fri)\b", text)
    if wd and (_DUE_CONTEXT.search(text)):
        target = next(i for i, w in enumerate(_WEEKDAYS) if w.startswith(wd[2][:3]))
        ahead = (target - sent.weekday()) % 7  # "by Friday" sent on a Friday means today
        if wd[1]:
            ahead += 7
        return (sent + timedelta(days=ahead)).isoformat()

    if re.search(r"\bnext week\b", text):
        return (sent + timedelta(days=7 - sent.weekday())).isoformat()  # next Monday
    return None


def tag(m: Message) -> Message:
    """Fill in intent and due_hint if they aren't set yet."""
    if m.intent is None:
        m.intent = classify(m)
    if m.due_hint is None and m.intent in ("request", "question", "commitment"):
        m.due_hint = due_hint(m)
    return m


def tag_all(messages: list[Message]) -> list[Message]:
    return [tag(m) for m in messages]


__all__ = ["INTENTS", "classify", "due_hint", "tag", "tag_all"]
