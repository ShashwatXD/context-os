"""Hybrid search over your messages: keyword + meaning, with typo-tolerant names and time filters.

    "priyta contract last week"  ─┬─ person:  "priyta" → Priya Shah        (fuzzy name match)
                                   ├─ dates:   "last week" → after/before    (the model converts it)
                                   ├─ keyword: FTS5 / bm25, typos corrected  ("contarct" → "contract")
                                   ├─ meaning: embeddings, cosine similarity ("payment" ≈ "invoice")
                                   └─ merge:   Reciprocal Rank Fusion of the two ranked lists

No vector database: vectors live in SQLite as float32 bytes and are compared with one numpy matrix
multiply. For a personal inbox (tens of thousands of messages) that takes milliseconds.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, tzinfo

import numpy as np

from contextos.models import Message
from contextos.storage import Store

RRF_K = 60            # standard Reciprocal Rank Fusion constant: dampens the gap between rank 1 and rank 2
CANDIDATES = 50       # how many results each method contributes before fusion
NAME_CUTOFF = 0.6     # how similar a typed name must be to a real one (0..1)
WORD_CUTOFF = 0.8     # stricter for ordinary words, so we don't "correct" real words
# Vector search always has a "nearest" result, even when nothing is related. Two guards:
MIN_SIMILARITY = 0.55  # absolute floor (cosine). Tune it on your own data with the benchmark.
RELATIVE_CUT = 0.85    # also drop results far below the best match

Embedder = Callable[[str], list[float]]


@dataclass
class SearchRequest:
    query: str = ""
    person: str | None = None
    after: datetime | None = None
    before: datetime | None = None
    source: str | None = None
    channel: str | None = None
    limit: int = 20


@dataclass
class SearchResult:
    messages: list[Message] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)          # what we corrected or couldn't do, shown to the model
    matched_by: dict[int, set[str]] = field(default_factory=dict)  # rid → {"keyword", "meaning"}


# ---- vectors ----------------------------------------------------------------


def to_blob(vector: list[float]) -> bytes:
    """Normalize to length 1 (so cosine similarity = dot product) and store as compact float32."""
    v = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(v)
    return (v / norm if norm else v).astype(np.float32).tobytes()


def embed_text(m: Message) -> str:
    """What gets embedded for a message: who, where and what, so 'Priya's email about the contract' matches."""
    head = f"{m.source} {m.channel} from {m.author}"
    body = f"{m.title}\n{m.text}" if m.title else m.text
    return f"{head}: {body}"[:2000]


# ---- dates ------------------------------------------------------------------


def parse_date(value: str | None, tz: tzinfo, end_of_day: bool = False) -> datetime | None:
    """Accepts '2026-11-03' or a full ISO timestamp. A bare date used as an upper bound means 'through that day'."""
    if not value:
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            day = datetime.fromisoformat(value).date()
            if end_of_day:
                day += timedelta(days=1)
            return datetime.combine(day, time.min, tzinfo=tz)
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=tz)
    except ValueError:
        return None


# ---- the searcher -----------------------------------------------------------


class Searcher:
    def __init__(
        self, store: Store, embedder: Embedder | None = None, embed_model: str = "", min_similarity: float = MIN_SIMILARITY
    ):
        self.store = store
        self.embedder = embedder
        self.embed_model = embed_model
        self.min_similarity = min_similarity

    # People: "priyta" → ["Priya Shah"]
    def resolve_person(self, typed: str) -> list[str]:
        people = self.store.people()
        if not people:
            return []
        t = typed.strip().lower().lstrip("@")
        exact = [p for p in people if p.lower() == t]
        if exact:
            return exact
        # First names and partial names: "priya" matches "Priya Shah".
        partial = [p for p in people if t in p.lower() or any(part == t for part in p.lower().split())]
        if partial:
            return sorted(partial, key=lambda p: -people[p])
        # Typos: compare against full names and first names.
        candidates: dict[str, str] = {}
        for p in people:
            candidates[p.lower()] = p
            for part in p.lower().split():
                candidates.setdefault(part, p)
        close = difflib.get_close_matches(t, list(candidates), n=3, cutoff=NAME_CUTOFF)
        return list(dict.fromkeys(candidates[c] for c in close))

    # Words: "contarct" → "contract" (only for words that match nothing)
    def correct_query(self, query: str) -> tuple[str, list[str]]:
        words = re.findall(r"\w+", query)
        fixed, notes = [], []
        vocab: list[str] | None = None
        for w in words:
            if len(w) < 4 or w.isdigit() or self.store.term_hits(w):
                fixed.append(w)
                continue
            vocab = vocab if vocab is not None else self.store.vocabulary()
            match = difflib.get_close_matches(w.lower(), vocab, n=1, cutoff=WORD_CUTOFF)
            if match:
                fixed.append(match[0])
                notes.append(f"'{w}' matched nothing; also searched '{match[0]}'")
            else:
                fixed.append(w)
        # Keep the original words too, so a correction never removes a real match.
        combined = " ".join(dict.fromkeys(words + fixed))
        return combined, notes

    def search(self, req: SearchRequest) -> SearchResult:
        result = SearchResult()
        filters: dict = {"after": req.after, "before": req.before, "source": req.source, "channel": req.channel}

        if req.person:
            names = self.resolve_person(req.person)
            if not names:
                result.notes.append(f"No one named '{req.person}' in your messages.")
                return result
            if [n.lower() for n in names] != [req.person.lower()]:
                result.notes.append(f"'{req.person}' matched: {', '.join(names)}")
            filters["authors"] = names

        query = req.query.strip()
        if not query:
            # Filters only, e.g. "what did Priya send last week?": newest first.
            result.messages = self.store.filtered(limit=req.limit, **filters)
            return result

        corrected, notes = self.correct_query(query)
        result.notes += notes
        keyword = [m.rid for m in self.store.search(corrected, filters["after"], filters["source"], CANDIDATES,
                                                    authors=filters.get("authors"), before=filters["before"],
                                                    channel=filters["channel"])]
        meaning = self._vector_search(query, filters, result)

        fused = reciprocal_rank_fusion({"keyword": keyword, "meaning": meaning})
        top = [rid for rid, _ in fused[: req.limit]]
        found = self.store.by_rids(top)
        result.messages = [found[rid] for rid in top if rid in found]
        for name, ranked in (("keyword", keyword), ("meaning", meaning)):
            for rid in ranked:
                result.matched_by.setdefault(rid, set()).add(name)
        return result

    def _vector_search(self, query: str, filters: dict, result: SearchResult) -> list[int]:
        if not self.embedder or not self.embed_model:
            return []
        rows = self.store.vectors(self.embed_model, **filters)
        if not rows:
            return []
        try:
            q = np.frombuffer(to_blob(self.embedder(query)), dtype=np.float32)
        except Exception as e:  # meaning search is a bonus; keyword search still works without it
            result.notes.append(f"Meaning search unavailable ({e}); used keywords only.")
            return []
        rids = np.fromiter((r for r, _ in rows), dtype=np.int64, count=len(rows))
        matrix = np.frombuffer(b"".join(v for _, v in rows), dtype=np.float32).reshape(len(rows), -1)
        if matrix.shape[1] != q.shape[0]:
            result.notes.append("Stored vectors have a different size; re-index needed. Used keywords only.")
            return []
        scores = matrix @ q  # cosine similarity, since every vector is unit length
        order = np.argsort(-scores)[:CANDIDATES]
        floor = max(self.min_similarity, float(scores[order[0]]) * RELATIVE_CUT)
        return [int(rids[i]) for i in order if scores[i] >= floor]


def reciprocal_rank_fusion(lists: dict[str, list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Merge ranked lists: score = Σ 1 / (k + rank). Items found by both methods rise to the top.

    RRF only uses ranks, not raw scores, which matters here: bm25 scores and cosine similarities live on
    completely different scales and can't be added directly.
    """
    scores: dict[int, float] = {}
    for ranked in lists.values():
        for rank, rid in enumerate(ranked, start=1):
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])
