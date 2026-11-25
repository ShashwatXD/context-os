"""Identity resolution: one person, one identity, across Gmail, Slack and Discord.

The same human shows up under different names in every app:

    gmail    "Priya Shah" <priya.shah@acme.com>
    slack    "Priya Shah"
    discord  "priyashah"            (or "priya_s", or a display name)

Without this, "what did Priya say?" only finds one of the three, and a loop opened in email can't be
linked to her Slack reply. With it, every alias points to one identity, and search, loops and the MCP
`who_is` tool all see the person, not the account.

Rules, strongest first (all deterministic, no model call):

    1. same email address                         (gmail aliases of one sender)
    2. same full name, 2+ words                   "Priya Shah" == "priya  shah" == "Priyá Shah"
    3. handle == full name with spaces removed     "priyashah" / "priya_shah" / "priya.shah" == "Priya Shah"
       or == an email's local part                 "priyashah" == priyashah@acme.com
    4. a single first name joins a full name only if exactly ONE identity has that first name
       "Priya" → "Priya Shah", but "Sam" stays alone when there are two Sams

When unsure, keep them apart: a wrong merge mixes two people's messages, a missed merge only means one
extra search. Manual `merge` / `split` overrides always win over the rules.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

_SEPARATORS = re.compile(r"[._\-+]+")
_NON_WORD = re.compile(r"[^a-z0-9 ]+")
_GENERIC_LOCAL = {"info", "hello", "team", "support", "admin", "contact", "hi", "mail", "office", "jobs", "careers"}


@dataclass(frozen=True)
class Alias:
    source: str
    author: str
    author_id: str | None = None  # "gmail:priya@acme.com", "slack:U123", "discord:9876"

    @property
    def key(self) -> str:
        return f"{self.source}|{self.author}"


@dataclass
class Identity:
    name: str
    aliases: list[Alias] = field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        return sorted({a.source for a in self.aliases})


def tokens(text: str) -> list[str]:
    """'Priyá  Shah (Acme)' → ['priya', 'shah', 'acme']."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = _SEPARATORS.sub(" ", text)
    return _NON_WORD.sub(" ", text).split()


def _email(author_id: str | None) -> str | None:
    if author_id and author_id.startswith("gmail:") and "@" in author_id:
        return author_id[6:].lower()
    return None


def keys(alias: Alias) -> tuple[set[str], set[str], str | None]:
    """(strong keys, handle keys, first name if the alias is a single word).

    Strong keys merge on their own. Handle keys merge with a strong full-name key that squashes to them.
    """
    strong: set[str] = set()
    handles: set[str] = set()
    email = _email(alias.author_id)
    if email:
        strong.add(f"email:{email}")
        local = email.split("@")[0]
        local_tokens = tokens(local)
        if local not in _GENERIC_LOCAL and local_tokens:
            if len(local_tokens) >= 2:
                strong.add("name:" + " ".join(local_tokens))
            handles.add("".join(local_tokens))

    t = tokens(alias.author)
    first = None
    if len(t) >= 2:
        strong.add("name:" + " ".join(t))
        handles.add("".join(t))
    elif len(t) == 1:
        # One word: could be a handle ("priyashah") or just a first name ("Priya"). Try both.
        handles.add(t[0])
        first = t[0]
    return strong, handles, first


class _Union:
    def __init__(self, items: list[str]):
        self.parent = {i: i for i in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def resolve(
    aliases: list[Alias],
    counts: dict[str, int] | None = None,
    merges: list[tuple[str, str]] = (),
    splits: list[tuple[str, str]] = (),
) -> list[Identity]:
    """Group aliases into identities. `merges` / `splits` are pairs of author names (any source)."""
    counts = counts or {}
    by_key = {a.key: a for a in aliases}
    uf = _Union(list(by_key))
    split_pairs = {frozenset((x.lower(), y.lower())) for x, y in splits}

    def blocked(a: Alias, b: Alias) -> bool:
        return frozenset((a.author.lower(), b.author.lower())) in split_pairs

    def join(a: Alias, b: Alias) -> None:
        if not blocked(a, b):
            uf.union(a.key, b.key)

    info = {a.key: keys(a) for a in aliases}

    # Rules 1 + 2: shared strong key.
    owner: dict[str, Alias] = {}
    for a in aliases:
        for k in info[a.key][0]:
            if k in owner:
                join(owner[k], a)
            else:
                owner[k] = a

    # Rule 3: a handle equal to a squashed full name.
    squashed: dict[str, Alias] = {}
    for a in aliases:
        for k in info[a.key][0]:
            if k.startswith("name:"):
                squashed.setdefault(k[5:].replace(" ", ""), a)
    for a in aliases:
        for h in info[a.key][1]:
            if h in squashed and squashed[h].key != a.key:
                join(squashed[h], a)

    # Rule 3b: a one-word handle equal to an email's local part ("priyashah" ~ priyashah@acme.com).
    locals_: dict[str, Alias] = {}
    for a in aliases:
        email = _email(a.author_id)
        local = "".join(tokens(email.split("@")[0])) if email else ""
        if len(local) >= 5 and email.split("@")[0] not in _GENERIC_LOCAL:
            locals_.setdefault(local, a)
    for a in aliases:
        first = info[a.key][2]
        if first and first in locals_ and locals_[first].key != a.key:
            join(locals_[first], a)

    # Rule 4: a lone first name joins the only multi-word identity with that first name.
    groups = _groups(uf, by_key)
    first_names: dict[str, set[str]] = defaultdict(set)
    for root, members in groups.items():
        for m in members:
            t = tokens(m.author)
            if len(t) >= 2:
                first_names[t[0]].add(root)
    for a in aliases:
        first = info[a.key][2]
        if not first or len(first) < 3:
            continue
        roots = first_names.get(first, set()) - {uf.find(a.key)}
        if len(roots) == 1:
            join(groups[next(iter(roots))][0], a)

    # Manual merges win over everything.
    by_author: dict[str, list[Alias]] = defaultdict(list)
    for a in aliases:
        by_author[a.author.lower()].append(a)
    for x, y in merges:
        for a in by_author.get(x.lower(), []):
            for b in by_author.get(y.lower(), []):
                uf.union(a.key, b.key)

    out = []
    for members in _groups(uf, by_key).values():
        out.append(Identity(name=_display_name(members, counts), aliases=sorted(members, key=lambda m: (m.source, m.author))))
    return sorted(out, key=lambda i: i.name.lower())


def _groups(uf: _Union, by_key: dict[str, Alias]) -> dict[str, list[Alias]]:
    groups: dict[str, list[Alias]] = defaultdict(list)
    for k, a in by_key.items():
        groups[uf.find(k)].append(a)
    return groups


def _display_name(members: list[Alias], counts: dict[str, int]) -> str:
    """The most human-looking name: multi-word first, then the one with the most messages."""

    def score(a: Alias):
        t = tokens(a.author)
        return (len(t) >= 2, "@" not in a.author, counts.get(a.key, 0), -len(a.author))

    return max(members, key=score).author


__all__ = ["Alias", "Identity", "keys", "resolve", "tokens"]
