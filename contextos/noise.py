"""Cheap, deterministic triage *before* the LLM sees anything.

Three buckets:
  keep    full text goes into the context
  low     one-line headline only (newsletters, bots, notifications). The model still sees
          they exist, so a GitHub review request or a bank alert isn't silently lost.
  dropped never sent (promotions, social notifications, muted channels, empty messages)

Filtering in code first is the cheapest context-engineering lever there is: every token
you don't send is cost, latency and distraction you don't pay for.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from contextos.models import Message

DROP_LABELS = {"CATEGORY_PROMOTIONS": "promotions", "CATEGORY_SOCIAL": "social notifications"}


@dataclass
class Triage:
    keep: list[Message] = field(default_factory=list)
    low: list[Message] = field(default_factory=list)
    dropped: Counter = field(default_factory=Counter)


def is_muted(m: Message, mute: list[str]) -> bool:
    haystack = f"{m.channel} {m.author}".lower()
    return any(pattern in haystack for pattern in mute)


def triage(messages: list[Message], mute: list[str] | None = None) -> Triage:
    t = Triage()
    for m in messages:
        dropped_label = next((DROP_LABELS[l] for l in m.labels if l in DROP_LABELS), None)
        if dropped_label:
            t.dropped[dropped_label] += 1
        elif mute and is_muted(m, mute):
            t.dropped["muted"] += 1
        elif not m.text.strip() and not m.title:
            t.dropped["empty"] += 1
        elif m.is_automated and not m.is_to_me:
            t.low.append(m)
        else:
            t.keep.append(m)
    return t
