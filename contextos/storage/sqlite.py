"""SQLite storage: messages + full-text index, sync state, briefings, and what you did with them."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from contextos.models import Message

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    rid          INTEGER PRIMARY KEY,
    id           TEXT UNIQUE NOT NULL,
    source       TEXT NOT NULL,
    channel      TEXT NOT NULL,
    author       TEXT NOT NULL,
    ts           REAL NOT NULL,
    text         TEXT NOT NULL,
    title        TEXT,
    thread_id    TEXT,
    url          TEXT,
    is_to_me     INTEGER NOT NULL DEFAULT 0,
    is_from_me   INTEGER NOT NULL DEFAULT 0,
    is_automated INTEGER NOT NULL DEFAULT 0,
    labels       TEXT NOT NULL DEFAULT '[]',
    intent       TEXT,
    due_hint     TEXT,
    author_id    TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    rid UNINDEXED, title, text, author, channel, tokenize = 'porter unicode61'
);
-- Every distinct word in the index: used to correct typos ("contarct" -> "contract").
CREATE VIRTUAL TABLE IF NOT EXISTS messages_vocab USING fts5vocab(messages_fts, 'row');

-- Meaning vectors (one per message), stored as float32 bytes. No separate vector database needed.
CREATE TABLE IF NOT EXISTS embeddings (
    rid   INTEGER PRIMARY KEY,
    model TEXT NOT NULL,
    vec   BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    source         TEXT PRIMARY KEY,
    last_synced_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id      INTEGER PRIMARY KEY,
    source  TEXT NOT NULL,
    at      REAL NOT NULL,
    fetched INTEGER NOT NULL,
    new     INTEGER NOT NULL,
    error   TEXT
);

CREATE TABLE IF NOT EXISTS digests (
    id           INTEGER PRIMARY KEY,
    created_at   REAL NOT NULL,
    window_start REAL NOT NULL,
    window_end   REAL NOT NULL,
    message_rids TEXT NOT NULL,
    output       TEXT NOT NULL,
    meta         TEXT NOT NULL
);

-- Done / snooze / reopen on a briefing item. Keyed by the item's citations, so the state
-- carries over when the briefing is regenerated with the same messages.
CREATE TABLE IF NOT EXISTS item_actions (
    id         INTEGER PRIMARY KEY,
    digest_id  INTEGER NOT NULL,
    item_key   TEXT NOT NULL,
    refs       TEXT NOT NULL,
    item       TEXT NOT NULL,
    action     TEXT NOT NULL,
    until      REAL,
    created_at REAL NOT NULL
);

-- 👍 / 👎 on items and "you missed something" notes: the raw material for evals.
CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY,
    digest_id  INTEGER NOT NULL,
    item_key   TEXT,
    item       TEXT,
    vote       INTEGER,
    note       TEXT,
    created_at REAL NOT NULL
);

-- Open loops: commitments that outlive a single day ("Priya asked you to review the invoice by Friday").
-- This is the briefing's memory. Each day reads the open ones, and they close when the conversation
-- shows they're resolved: your reply in the thread, the model seeing it settled, you pressing Done,
-- or going stale.
CREATE TABLE IF NOT EXISTS loops (
    id            INTEGER PRIMARY KEY,
    kind          TEXT NOT NULL,              -- "you_owe" | "owed_to_you"
    who           TEXT NOT NULL,
    title         TEXT NOT NULL,
    detail        TEXT NOT NULL,
    due           TEXT,                       -- YYYY-MM-DD or NULL
    status        TEXT NOT NULL DEFAULT 'open',  -- open | closed | stale
    refs          TEXT NOT NULL,              -- evidence: citation tags, oldest first
    threads       TEXT NOT NULL,              -- conversation keys where a reply would close it
    opened_at     REAL NOT NULL,              -- time of the message that opened it
    updated_at    REAL NOT NULL,              -- last time there was news about it
    closed_at     REAL,
    closed_reason TEXT,
    closed_ref    TEXT,
    digest_id     INTEGER,
    promised_at   REAL                        -- someone said "I'll do it": still open, but in motion
);
CREATE INDEX IF NOT EXISTS idx_loops_status ON loops(status);

-- Identity resolution (pipeline/identity.py): every (source, author) alias belongs to one person.
-- Rebuilt from the messages after each sync; overrides are what the user said by hand and always win.
CREATE TABLE IF NOT EXISTS identities (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS identity_aliases (
    source      TEXT NOT NULL,
    author      TEXT NOT NULL,
    author_id   TEXT,
    identity_id INTEGER NOT NULL,
    messages    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source, author)
);
CREATE INDEX IF NOT EXISTS idx_alias_identity ON identity_aliases(identity_id);
CREATE TABLE IF NOT EXISTS identity_overrides (
    id     INTEGER PRIMARY KEY,
    a      TEXT NOT NULL,
    b      TEXT NOT NULL,
    action TEXT NOT NULL              -- merge | split
);

CREATE TABLE IF NOT EXISTS asks (
    id         INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    refs       TEXT NOT NULL,
    meta       TEXT NOT NULL
);
"""

_COLUMNS = (
    "id, source, channel, author, ts, text, title, thread_id, url, is_to_me, is_from_me, is_automated, labels, intent, "
    "due_hint, author_id"
)
_NCOLS = _COLUMNS.count(",") + 1
# Columns added after the first release: (table, column, type). Older databases get them on open.
_MIGRATIONS = [
    ("messages", "intent", "TEXT"),
    ("messages", "due_hint", "TEXT"),
    ("loops", "promised_at", "REAL"),
    ("messages", "author_id", "TEXT"),
]


def _now() -> float:
    return datetime.now(UTC).timestamp()


def _dt(ts: float | None) -> datetime | None:
    return datetime.fromtimestamp(ts, UTC) if ts is not None else None


def fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 query: every word quoted, OR-ed together, ranked by bm25."""
    words = [w for w in re.findall(r"\w+", text.lower()) if len(w) > 1]
    return " OR ".join(f'"{w}"' for w in words)


@dataclass
class DigestRecord:
    id: int
    created_at: datetime
    start: datetime
    end: datetime
    rids: list[int]
    output: dict
    meta: dict


@dataclass
class ItemAction:
    id: int
    digest_id: int
    item_key: str
    refs: list[str]
    item: dict
    action: str  # "done" | "snooze" | "reopen"
    until: datetime | None
    created_at: datetime


@dataclass
class Loop:
    id: int
    kind: str
    who: str
    title: str
    detail: str
    due: str | None
    status: str
    refs: list[str]
    threads: list[str]
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    closed_reason: str | None = None
    closed_ref: str | None = None
    digest_id: int | None = None
    promised_at: datetime | None = None

    @property
    def ref(self) -> str:
        return f"L{self.id}"


class Store:
    def __init__(self, path: Path | str):
        self.db = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        # WAL lets the website read while a background sync writes.
        self.db.execute("PRAGMA journal_mode=WAL")
        self._migrate()
        self.db.executescript(SCHEMA)
        self._backfill_intents()
        if not self.db.execute("SELECT 1 FROM identity_aliases LIMIT 1").fetchone() and \
                self.db.execute("SELECT 1 FROM messages LIMIT 1").fetchone():
            self.rebuild_identities()  # databases from before identities existed

    def _migrate(self) -> None:
        for table, column, kind in _MIGRATIONS:
            cols = {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
            if cols and column not in cols:  # table exists, column doesn't
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        self.db.commit()

    def _backfill_intents(self) -> None:
        """Tag messages stored before intents existed. Rules only, so it's fast even for a big inbox."""
        from contextos.pipeline.intent import tag

        rows = self.db.execute("SELECT * FROM messages WHERE intent IS NULL").fetchall()
        if not rows:
            return
        with self.db:
            for r in rows:
                m = tag(self._to_message(r))
                self.db.execute("UPDATE messages SET intent = ?, due_hint = ? WHERE rid = ?", (m.intent, m.due_hint, m.rid))
            # Acks are never embedded; drop any vectors made before we knew.
            self.db.execute("DELETE FROM embeddings WHERE rid IN (SELECT rid FROM messages WHERE intent = 'ack')")

    def close(self) -> None:
        self.db.close()

    # ---- messages -----------------------------------------------------------

    def upsert(self, messages: list[Message]) -> int:
        """Insert or update messages. Returns how many were new. Sets .rid, .intent and .due_hint on each message."""
        from contextos.pipeline.intent import tag

        new = 0
        with self.db:
            for m in messages:
                tag(m)
                row = self.db.execute("SELECT rid, text, title FROM messages WHERE id = ?", (m.id,)).fetchone()
                values = (
                    m.id,
                    m.source,
                    m.channel,
                    m.author,
                    m.ts.timestamp(),
                    m.text,
                    m.title,
                    m.thread_id,
                    m.url,
                    int(m.is_to_me),
                    int(m.is_from_me),
                    int(m.is_automated),
                    json.dumps(m.labels),
                    m.intent,
                    m.due_hint,
                    m.author_id,
                )
                if row is None:
                    cur = self.db.execute(f"INSERT INTO messages ({_COLUMNS}) VALUES ({','.join('?' * _NCOLS)})", values)
                    m.rid = cur.lastrowid
                    new += 1
                else:
                    m.rid = row["rid"]
                    if (row["text"], row["title"]) != (m.text, m.title):
                        self.db.execute("DELETE FROM embeddings WHERE rid = ?", (m.rid,))  # re-embed edited text
                    self.db.execute(
                        f"UPDATE messages SET ({_COLUMNS}) = ({','.join('?' * _NCOLS)}) WHERE rid = ?",
                        (*values, m.rid),
                    )
                    self.db.execute("DELETE FROM messages_fts WHERE rid = ?", (m.rid,))
                self.db.execute(
                    "INSERT INTO messages_fts (rid, title, text, author, channel) VALUES (?, ?, ?, ?, ?)",
                    (m.rid, m.title or "", m.text, m.author, m.channel),
                )
        return new

    def between(self, start: datetime, end: datetime) -> list[Message]:
        rows = self.db.execute(
            "SELECT * FROM messages WHERE ts >= ? AND ts < ? ORDER BY ts",
            (start.timestamp(), end.timestamp()),
        ).fetchall()
        return [self._to_message(r) for r in rows]

    def count_since(self, since: datetime) -> int:
        return self.db.execute("SELECT COUNT(*) FROM messages WHERE ts >= ?", (since.timestamp(),)).fetchone()[0]

    @staticmethod
    def _where(
        authors: list[str] | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        source: str | None = None,
        channel: str | None = None,
    ) -> tuple[str, list]:
        """SQL filter clauses shared by keyword search, listing and vector search."""
        clauses, params = [], []
        if authors:
            marks = ",".join("?" * len(authors))
            # A person's messages, plus your side of your DMs with them.
            clauses.append(f"(m.author IN ({marks}) OR m.channel IN ({marks}))")
            params += list(authors) + [f"DM: {a}" for a in authors]
        if after:
            clauses.append("m.ts >= ?")
            params.append(after.timestamp())
        if before:
            clauses.append("m.ts < ?")
            params.append(before.timestamp())
        if source:
            clauses.append("m.source = ?")
            params.append(source)
        if channel:
            clauses.append("LOWER(m.channel) LIKE ?")
            params.append(f"%{channel.lower().lstrip('#')}%")
        return "".join(f" AND {c}" for c in clauses), params

    def search(
        self,
        query: str,
        since: datetime | None = None,
        source: str | None = None,
        limit: int = 25,
        *,
        authors: list[str] | None = None,
        before: datetime | None = None,
        channel: str | None = None,
    ) -> list[Message]:
        """Keyword search (FTS5, bm25-ranked) with optional filters."""
        q = fts_query(query)
        if not q:
            return []
        where, params = self._where(authors, since, before, source, channel)
        sql = (
            "SELECT m.* FROM messages_fts f JOIN messages m ON m.rid = f.rid "
            f"WHERE messages_fts MATCH ?{where} ORDER BY bm25(messages_fts) LIMIT ?"
        )
        return [self._to_message(r) for r in self.db.execute(sql, [q, *params, limit]).fetchall()]

    def filtered(self, *, limit: int = 50, **filters) -> list[Message]:
        """Newest messages matching filters only (no text query): 'what did Priya send last week?'."""
        where, params = self._where(**filters)
        sql = f"SELECT m.* FROM messages m WHERE 1=1{where} ORDER BY m.ts DESC LIMIT ?"
        return [self._to_message(r) for r in self.db.execute(sql, [*params, limit]).fetchall()]

    def people(self) -> dict[str, int]:
        """Everyone who appears as an author or DM partner, with message counts."""
        out: dict[str, int] = {}
        for r in self.db.execute("SELECT author, COUNT(*) FROM messages WHERE author != 'me' GROUP BY author"):
            out[r[0]] = out.get(r[0], 0) + r[1]
        for r in self.db.execute("SELECT substr(channel, 5), COUNT(*) FROM messages WHERE channel LIKE 'DM: %' GROUP BY channel"):
            out[r[0]] = out.get(r[0], 0) + r[1]
        return out

    def term_hits(self, word: str) -> int:
        """How many messages contain this word (after stemming)."""
        q = fts_query(word)
        return self.db.execute("SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH ?", (q,)).fetchone()[0] if q else 0

    def vocabulary(self, min_docs: int = 1) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT term FROM messages_vocab WHERE doc >= ?", (min_docs,))]

    # ---- meaning vectors ----------------------------------------------------

    def missing_embeddings(self, model: str, limit: int = 100) -> list[Message]:
        rows = self.db.execute(
            "SELECT m.* FROM messages m LEFT JOIN embeddings e ON e.rid = m.rid AND e.model = ? "
            "WHERE e.rid IS NULL AND COALESCE(m.intent, '') != 'ack' "
            "ORDER BY m.ts DESC LIMIT ?",
            (model, limit),
        ).fetchall()
        return [self._to_message(r) for r in rows]

    def save_embeddings(self, model: str, items: list[tuple[int, bytes]]) -> None:
        with self.db:
            self.db.executemany(
                "INSERT OR REPLACE INTO embeddings (rid, model, vec) VALUES (?, ?, ?)",
                [(rid, model, vec) for rid, vec in items],
            )

    def embedding_count(self, model: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM embeddings WHERE model = ?", (model,)).fetchone()[0]

    def vectors(self, model: str, **filters) -> list[tuple[int, bytes]]:
        """(rid, vector bytes) for every embedded message matching the filters."""
        where, params = self._where(**filters)
        sql = f"SELECT e.rid, e.vec FROM embeddings e JOIN messages m ON m.rid = e.rid WHERE e.model = ?{where}"
        return [(r[0], r[1]) for r in self.db.execute(sql, [model, *params])]

    def by_rids(self, rids: list[int]) -> dict[int, Message]:
        out: dict[int, Message] = {}
        for i in range(0, len(rids), 500):
            chunk = rids[i : i + 500]
            rows = self.db.execute(f"SELECT * FROM messages WHERE rid IN ({','.join('?' * len(chunk))})", chunk)
            out.update({r["rid"]: self._to_message(r) for r in rows})
        return out

    def by_rid(self, rid: int) -> Message | None:
        row = self.db.execute("SELECT * FROM messages WHERE rid = ?", (rid,)).fetchone()
        return self._to_message(row) if row else None

    def by_refs(self, refs: list[str]) -> dict[str, Message]:
        rids = [int(r[1:]) for r in refs if re.fullmatch(r"m\d+", r)]
        if not rids:
            return {}
        rows = self.db.execute(f"SELECT * FROM messages WHERE rid IN ({','.join('?' * len(rids))})", rids).fetchall()
        return {f"m{r['rid']}": self._to_message(r) for r in rows}

    def thread(self, thread_id: str, limit: int = 60) -> list[Message]:
        rows = self.db.execute(
            "SELECT * FROM (SELECT * FROM messages WHERE thread_id = ? ORDER BY ts DESC LIMIT ?) ORDER BY ts",
            (thread_id, limit),
        ).fetchall()
        return [self._to_message(r) for r in rows]

    def activity(self, since: datetime) -> list[tuple[str, str, int, datetime]]:
        """(source, channel, message count, latest timestamp) for everything since `since`."""
        rows = self.db.execute(
            "SELECT source, channel, COUNT(*) AS n, MAX(ts) AS latest FROM messages "
            "WHERE ts >= ? GROUP BY source, channel ORDER BY n DESC",
            (since.timestamp(),),
        ).fetchall()
        return [(r["source"], r["channel"], r["n"], _dt(r["latest"])) for r in rows]

    def counts(self) -> dict[str, int]:
        rows = self.db.execute("SELECT source, COUNT(*) FROM messages GROUP BY source").fetchall()
        return {r[0]: r[1] for r in rows}

    # ---- sync ---------------------------------------------------------------

    def last_synced(self, source: str) -> datetime | None:
        row = self.db.execute("SELECT last_synced_at FROM sync_state WHERE source = ?", (source,)).fetchone()
        return _dt(row[0]) if row else None

    def set_last_synced(self, source: str, when: datetime) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO sync_state (source, last_synced_at) VALUES (?, ?) "
                "ON CONFLICT(source) DO UPDATE SET last_synced_at = excluded.last_synced_at",
                (source, when.timestamp()),
            )

    def log_sync(self, source: str, fetched: int, new: int, error: str | None) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO sync_log (source, at, fetched, new, error) VALUES (?, ?, ?, ?, ?)",
                (source, _now(), fetched, new, error),
            )

    def last_sync_logs(self) -> dict[str, dict]:
        rows = self.db.execute("SELECT * FROM sync_log WHERE id IN (SELECT MAX(id) FROM sync_log GROUP BY source)").fetchall()
        return {r["source"]: {"at": _dt(r["at"]), "fetched": r["fetched"], "new": r["new"], "error": r["error"]} for r in rows}

    # ---- briefings ----------------------------------------------------------

    def save_digest(self, start: datetime, end: datetime, rids: list[int], output: dict, meta: dict) -> int:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO digests (created_at, window_start, window_end, message_rids, output, meta) VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), start.timestamp(), end.timestamp(), json.dumps(rids), json.dumps(output), json.dumps(meta)),
            )
            return cur.lastrowid

    def update_digest_meta(self, digest_id: int, updates: dict) -> None:
        rec = self.get_digest(digest_id)
        if rec is None:
            return
        meta = {**rec.meta, **updates}
        with self.db:
            self.db.execute("UPDATE digests SET meta = ? WHERE id = ?", (json.dumps(meta), digest_id))

    def get_digest(self, digest_id: int) -> DigestRecord | None:
        row = self.db.execute("SELECT * FROM digests WHERE id = ?", (digest_id,)).fetchone()
        return self._to_digest(row) if row else None

    def latest_digest(self, created_since: datetime | None = None) -> DigestRecord | None:
        row = self.db.execute(
            "SELECT * FROM digests WHERE created_at >= ? ORDER BY id DESC LIMIT 1",
            ((created_since.timestamp() if created_since else 0),),
        ).fetchone()
        return self._to_digest(row) if row else None

    def list_digests(self, limit: int = 60) -> list[DigestRecord]:
        rows = self.db.execute("SELECT * FROM digests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._to_digest(r) for r in rows]

    # ---- what you did with them ---------------------------------------------

    def add_action(
        self, digest_id: int, item_key: str, refs: list[str], item: dict, action: str, until: datetime | None = None
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO item_actions (digest_id, item_key, refs, item, action, until, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (digest_id, item_key, json.dumps(refs), json.dumps(item), action, until.timestamp() if until else None, _now()),
            )

    def actions(self, limit: int = 500) -> list[ItemAction]:
        """Most recent first."""
        rows = self.db.execute("SELECT * FROM item_actions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [
            ItemAction(
                r["id"],
                r["digest_id"],
                r["item_key"],
                json.loads(r["refs"]),
                json.loads(r["item"]),
                r["action"],
                _dt(r["until"]),
                _dt(r["created_at"]),
            )
            for r in rows
        ]

    def add_feedback(
        self, digest_id: int, item_key: str | None = None, item: dict | None = None, vote: int | None = None, note: str | None = None
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO feedback (digest_id, item_key, item, vote, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (digest_id, item_key, json.dumps(item) if item else None, vote, note, _now()),
            )

    def votes(self, digest_id: int) -> dict[str, int]:
        """Latest vote per item in a briefing."""
        rows = self.db.execute(
            "SELECT item_key, vote FROM feedback WHERE id IN ("
            "  SELECT MAX(id) FROM feedback WHERE digest_id = ? AND vote IS NOT NULL GROUP BY item_key)",
            (digest_id,),
        ).fetchall()
        return {r["item_key"]: r["vote"] for r in rows}

    def feedback_rows(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM feedback ORDER BY id").fetchall()]

    # ---- open loops ---------------------------------------------------------

    def add_loop(
        self, kind: str, who: str, title: str, detail: str, due: str | None, refs: list[str], threads: list[str],
        opened_at: datetime, digest_id: int | None = None,
    ) -> int:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO loops (kind, who, title, detail, due, refs, threads, opened_at, updated_at, digest_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (kind, who, title, detail, due, json.dumps(refs), json.dumps(threads), opened_at.timestamp(),
                 opened_at.timestamp(), digest_id),
            )
            return cur.lastrowid

    def update_loop(self, loop_id: int, **fields) -> None:
        """Change some fields of a loop. Lists are stored as JSON, datetimes as timestamps."""
        if not fields:
            return
        values = []
        for v in fields.values():
            if isinstance(v, list):
                v = json.dumps(v)
            elif isinstance(v, datetime):
                v = v.timestamp()
            values.append(v)
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.db:
            self.db.execute(f"UPDATE loops SET {cols} WHERE id = ?", (*values, loop_id))

    def close_loop(self, loop_id: int, reason: str, ref: str | None = None, when: datetime | None = None) -> None:
        self.update_loop(loop_id, status="closed", closed_reason=reason, closed_ref=ref,
                         closed_at=when or datetime.now(UTC))

    def get_loop(self, loop_id: int) -> Loop | None:
        row = self.db.execute("SELECT * FROM loops WHERE id = ?", (loop_id,)).fetchone()
        return self._to_loop(row) if row else None

    def loops(self, status: str | None = "open", limit: int = 200) -> list[Loop]:
        """Newest news first."""
        if status:
            rows = self.db.execute(
                "SELECT * FROM loops WHERE status = ? ORDER BY updated_at DESC LIMIT ?", (status, limit)
            ).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM loops ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._to_loop(r) for r in rows]

    # ---- identities ---------------------------------------------------------

    def aliases(self) -> tuple[list, dict[str, int]]:
        """Every person alias seen in messages, plus message counts keyed by alias key."""
        from contextos.pipeline.identity import Alias

        found: dict[str, Alias] = {}
        counts: dict[str, int] = {}
        rows = self.db.execute(
            "SELECT source, author, MAX(author_id) AS aid, COUNT(*) AS n FROM messages "
            "WHERE is_from_me = 0 AND is_automated = 0 AND author NOT IN ('me', 'unknown', 'bot') GROUP BY source, author"
        )
        for r in rows:
            a = Alias(r["source"], r["author"], r["aid"])
            found[a.key], counts[a.key] = a, r["n"]
        # DM partners: in "DM: Alice" the other person is Alice even when only you wrote.
        for r in self.db.execute("SELECT source, substr(channel, 5) AS who, COUNT(*) AS n FROM messages "
                                 "WHERE channel LIKE 'DM: %' GROUP BY source, channel"):
            a = Alias(r["source"], r["who"])
            found.setdefault(a.key, a)
            counts[a.key] = max(counts.get(a.key, 0), r["n"])
        return list(found.values()), counts

    def rebuild_identities(self) -> int:
        """Re-run identity resolution over all stored messages. Returns the number of identities."""
        from contextos.pipeline.identity import resolve

        aliases, counts = self.aliases()
        overrides = self.db.execute("SELECT a, b, action FROM identity_overrides ORDER BY id").fetchall()
        merges = [(r["a"], r["b"]) for r in overrides if r["action"] == "merge"]
        splits = [(r["a"], r["b"]) for r in overrides if r["action"] == "split"]
        people = resolve(aliases, counts, merges, splits)
        with self.db:
            self.db.execute("DELETE FROM identity_aliases")
            self.db.execute("DELETE FROM identities")
            for p in people:
                iid = self.db.execute("INSERT INTO identities (name) VALUES (?)", (p.name,)).lastrowid
                self.db.executemany(
                    "INSERT INTO identity_aliases (source, author, author_id, identity_id, messages) VALUES (?, ?, ?, ?, ?)",
                    [(a.source, a.author, a.author_id, iid, counts.get(a.key, 0)) for a in p.aliases],
                )
        return len(people)

    def add_identity_override(self, a: str, b: str, action: str) -> None:
        if action not in ("merge", "split"):
            raise ValueError("action must be merge or split")
        with self.db:
            self.db.execute("INSERT INTO identity_overrides (a, b, action) VALUES (?, ?, ?)", (a, b, action))
        self.rebuild_identities()

    def identities(self, min_sources: int = 1) -> list[dict]:
        """[{id, name, aliases: [{source, author, author_id, messages}]}], busiest first."""
        out: dict[int, dict] = {}
        rows = self.db.execute(
            "SELECT i.id, i.name, a.source, a.author, a.author_id, a.messages FROM identities i "
            "JOIN identity_aliases a ON a.identity_id = i.id ORDER BY a.source, a.author"
        )
        for r in rows:
            p = out.setdefault(r["id"], {"id": r["id"], "name": r["name"], "aliases": []})
            p["aliases"].append({"source": r["source"], "author": r["author"], "author_id": r["author_id"],
                                 "messages": r["messages"]})
        people = [p for p in out.values() if len({a["source"] for a in p["aliases"]}) >= min_sources]
        return sorted(people, key=lambda p: -sum(a["messages"] for a in p["aliases"]))

    def same_person(self, authors: list[str]) -> list[str]:
        """Every name the people behind `authors` use, in any app. Unknown names come back unchanged."""
        if not authors:
            return []
        marks = ",".join("?" * len(authors))
        rows = self.db.execute(
            f"SELECT DISTINCT b.author FROM identity_aliases a JOIN identity_aliases b ON a.identity_id = b.identity_id "
            f"WHERE a.author IN ({marks})",
            authors,
        ).fetchall()
        return list(dict.fromkeys([*authors, *(r[0] for r in rows)]))

    # ---- ask history --------------------------------------------------------

    def save_ask(self, question: str, answer: str, refs: list[str], meta: dict) -> int:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO asks (created_at, question, answer, refs, meta) VALUES (?, ?, ?, ?, ?)",
                (_now(), question, answer, json.dumps(refs), json.dumps(meta)),
            )
            return cur.lastrowid

    def list_asks(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute("SELECT * FROM asks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [
            {
                "id": r["id"],
                "created_at": _dt(r["created_at"]),
                "question": r["question"],
                "answer": r["answer"],
                "refs": json.loads(r["refs"]),
                "meta": json.loads(r["meta"]),
            }
            for r in rows
        ]

    # ---- mapping ------------------------------------------------------------

    @staticmethod
    def _to_digest(r: sqlite3.Row) -> DigestRecord:
        return DigestRecord(
            r["id"],
            _dt(r["created_at"]),
            _dt(r["window_start"]),
            _dt(r["window_end"]),
            json.loads(r["message_rids"]),
            json.loads(r["output"]),
            json.loads(r["meta"]),
        )

    @staticmethod
    def _to_loop(r: sqlite3.Row) -> Loop:
        return Loop(
            r["id"], r["kind"], r["who"], r["title"], r["detail"], r["due"], r["status"],
            json.loads(r["refs"]), json.loads(r["threads"]), _dt(r["opened_at"]), _dt(r["updated_at"]),
            _dt(r["closed_at"]), r["closed_reason"], r["closed_ref"], r["digest_id"], _dt(r["promised_at"]),
        )

    @staticmethod
    def _to_message(r: sqlite3.Row) -> Message:
        return Message(
            id=r["id"],
            source=r["source"],
            channel=r["channel"],
            author=r["author"],
            ts=_dt(r["ts"]),
            text=r["text"],
            title=r["title"],
            thread_id=r["thread_id"],
            url=r["url"],
            is_to_me=bool(r["is_to_me"]),
            is_from_me=bool(r["is_from_me"]),
            is_automated=bool(r["is_automated"]),
            labels=json.loads(r["labels"]),
            intent=r["intent"],
            due_hint=r["due_hint"],
            author_id=r["author_id"],
            rid=r["rid"],
        )
