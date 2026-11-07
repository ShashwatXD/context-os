"""SQLite storage: messages + full-text index, sync state, briefings, and what you did with them."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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

_COLUMNS = (
    "id, source, channel, author, ts, text, title, thread_id, url, "
    "is_to_me, is_from_me, is_automated, labels"
)


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _dt(ts: float | None) -> datetime | None:
    return datetime.fromtimestamp(ts, timezone.utc) if ts is not None else None


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
                row = self.db.execute("SELECT rid FROM messages WHERE id = ?", (m.id,)).fetchone()
                values = (
                    m.id, m.source, m.channel, m.author, m.ts.timestamp(), m.text, m.title,
                    m.thread_id, m.url, int(m.is_to_me), int(m.is_from_me), int(m.is_automated),
                    json.dumps(m.labels),
                )
                if row is None:
                    cur = self.db.execute(
                        f"INSERT INTO messages ({_COLUMNS}) VALUES ({','.join('?' * 13)})", values
                    )
                    m.rid = cur.lastrowid
                    new += 1
                else:
                    m.rid = row["rid"]
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

    def search(
        self, query: str, since: datetime | None = None, source: str | None = None, limit: int = 25
    ) -> list[Message]:
        q = fts_query(query)
        if not q:
            return []
        sql = (
            "SELECT m.* FROM messages_fts f JOIN messages m ON m.rid = f.rid "
            "WHERE messages_fts MATCH ?"
        )
        params: list = [q]
        if since:
            sql += " AND m.ts >= ?"
            params.append(since.timestamp())
        if source:
            sql += " AND m.source = ?"
            params.append(source)
        sql += " ORDER BY bm25(messages_fts) LIMIT ?"
        params.append(limit)
        return [self._to_message(r) for r in self.db.execute(sql, params).fetchall()]

    def by_rid(self, rid: int) -> Message | None:
        row = self.db.execute("SELECT * FROM messages WHERE rid = ?", (rid,)).fetchone()
        return self._to_message(row) if row else None

    def by_refs(self, refs: list[str]) -> dict[str, Message]:
        rids = [int(r[1:]) for r in refs if re.fullmatch(r"m\d+", r)]
        if not rids:
            return {}
        rows = self.db.execute(
            f"SELECT * FROM messages WHERE rid IN ({','.join('?' * len(rids))})", rids
        ).fetchall()
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
        rows = self.db.execute(
            "SELECT * FROM sync_log WHERE id IN (SELECT MAX(id) FROM sync_log GROUP BY source)"
        ).fetchall()
        return {r["source"]: {"at": _dt(r["at"]), "fetched": r["fetched"], "new": r["new"], "error": r["error"]}
                for r in rows}

    # ---- briefings ----------------------------------------------------------

    def save_digest(self, start: datetime, end: datetime, rids: list[int], output: dict, meta: dict) -> int:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO digests (created_at, window_start, window_end, message_rids, output, meta) "
                "VALUES (?, ?, ?, ?, ?, ?)",
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

    def add_action(self, digest_id: int, item_key: str, refs: list[str], item: dict,
                   action: str, until: datetime | None = None) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO item_actions (digest_id, item_key, refs, item, action, until, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (digest_id, item_key, json.dumps(refs), json.dumps(item), action,
                 until.timestamp() if until else None, _now()),
            )

    def actions(self, limit: int = 500) -> list[ItemAction]:
        """Most recent first."""
        rows = self.db.execute("SELECT * FROM item_actions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [
            ItemAction(r["id"], r["digest_id"], r["item_key"], json.loads(r["refs"]), json.loads(r["item"]),
                       r["action"], _dt(r["until"]), _dt(r["created_at"]))
            for r in rows
        ]

    def add_feedback(self, digest_id: int, item_key: str | None = None, item: dict | None = None,
                     vote: int | None = None, note: str | None = None) -> None:
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
            {"id": r["id"], "created_at": _dt(r["created_at"]), "question": r["question"], "answer": r["answer"],
             "refs": json.loads(r["refs"]), "meta": json.loads(r["meta"])}
            for r in rows
        ]

    # ---- mapping ------------------------------------------------------------

    @staticmethod
    def _to_digest(r: sqlite3.Row) -> DigestRecord:
        return DigestRecord(
            r["id"], _dt(r["created_at"]), _dt(r["window_start"]), _dt(r["window_end"]),
            json.loads(r["message_rids"]), json.loads(r["output"]), json.loads(r["meta"]),
        )

    @staticmethod
    def _to_message(r: sqlite3.Row) -> Message:
        return Message(
            id=r["id"], source=r["source"], channel=r["channel"], author=r["author"],
            ts=_dt(r["ts"]), text=r["text"], title=r["title"],
            thread_id=r["thread_id"], url=r["url"], is_to_me=bool(r["is_to_me"]),
            is_from_me=bool(r["is_from_me"]), is_automated=bool(r["is_automated"]),
            labels=json.loads(r["labels"]), rid=r["rid"],
        )
