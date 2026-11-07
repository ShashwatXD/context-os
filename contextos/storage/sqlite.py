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
    labels       TEXT NOT NULL DEFAULT '[]'
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

CREATE TABLE IF NOT EXISTS asks (
    id         INTEGER PRIMARY KEY,
    created_at REAL NOT NULL,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    refs       TEXT NOT NULL,
    meta       TEXT NOT NULL
);
"""

_COLUMNS = "id, source, channel, author, ts, text, title, thread_id, url, is_to_me, is_from_me, is_automated, labels"


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


class Store:
    def __init__(self, path: Path | str):
        self.db = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        # WAL lets the website read while a background sync writes.
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    # ---- messages -----------------------------------------------------------

    def upsert(self, messages: list[Message]) -> int:
        """Insert or update messages. Returns how many were new. Sets .rid on each message."""
        new = 0
        with self.db:
            for m in messages:
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
                )
                if row is None:
                    cur = self.db.execute(f"INSERT INTO messages ({_COLUMNS}) VALUES ({','.join('?' * 13)})", values)
                    m.rid = cur.lastrowid
                    new += 1
                else:
                    m.rid = row["rid"]
                    if (row["text"], row["title"]) != (m.text, m.title):
                        self.db.execute("DELETE FROM embeddings WHERE rid = ?", (m.rid,))  # re-embed edited text
                    self.db.execute(
                        f"UPDATE messages SET ({_COLUMNS}) = ({','.join('?' * 13)}) WHERE rid = ?",
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
            "WHERE e.rid IS NULL ORDER BY m.ts DESC LIMIT ?",
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
            rid=r["rid"],
        )
