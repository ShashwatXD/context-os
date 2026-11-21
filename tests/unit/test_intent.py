from datetime import UTC, datetime

import pytest

from contextos.pipeline.intent import classify, due_hint
from tests.conftest import msg

THU = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)  # a Thursday


@pytest.mark.parametrize("text,intent", [
    ("thanks!", "ack"), ("ok 👍", "ack"), ("👍", "ack"), ("lgtm", "ack"), ("theek hai", "ack"), (":+1:", "ack"),
    ("Can you approve the Q3 invoice by Friday?", "request"),
    ("please review my PR", "request"),
    ("bhai ye doc dekh lena", "request"),
    ("are we still on for Thursday?", "question"),
    ("kab tak hoga?", "question"),
    ("We've decided to go with vendor B.", "decision"),
    ("deploy finished, all green", "info"),
    ("ok?", "question"),  # a question mark is never an ack
])
def test_classify(text, intent):
    assert classify(msg(1, text=text)) == intent


def test_from_me_promises_win_over_requests():
    assert classify(msg(1, text="I'll send it tonight, can you remind me?", is_from_me=True)) == "commitment"
    assert classify(msg(1, text="I'll send it tonight, can you remind me?")) == "request"


def test_automated_is_never_an_ask():
    assert classify(msg(1, text="Please confirm your email", is_automated=True)) == "info"


@pytest.mark.parametrize("text,due", [
    ("can you send it by Friday?", "2026-11-06"),
    ("need this by next Monday", "2026-11-16"),
    ("please review by EOD", "2026-11-05"),
    ("I'll do it tomorrow", "2026-11-06"),
    ("deadline is 2026-11-20", "2026-11-20"),
    ("due Nov 13", "2026-11-13"),
    ("kal tak bhej dena", "2026-11-06"),
    ("check the logs from today", None),
    ("can you look at this?", None),
])
def test_due_hint(text, due):
    assert due_hint(msg(1, text=text, ts=THU)) == due


def test_store_tags_on_insert_and_skips_ack_embeddings(store):
    a, b = msg(1, text="thanks!"), msg(2, text="can you review by Friday?", ts=THU)
    store.upsert([a, b])
    got = store.by_rids([a.rid, b.rid])
    assert got[a.rid].intent == "ack" and got[b.rid].intent == "request" and got[b.rid].due_hint == "2026-11-06"
    assert [m.rid for m in store.missing_embeddings("e")] == [b.rid]


def test_old_databases_are_migrated_and_backfilled(tmp_path):
    import sqlite3

    from contextos.storage import Store

    path = tmp_path / "old.db"
    db = sqlite3.connect(path)  # the schema before intents existed
    db.executescript("""CREATE TABLE messages (rid INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, source TEXT NOT NULL,
        channel TEXT NOT NULL, author TEXT NOT NULL, ts REAL NOT NULL, text TEXT NOT NULL, title TEXT, thread_id TEXT,
        url TEXT, is_to_me INTEGER NOT NULL DEFAULT 0, is_from_me INTEGER NOT NULL DEFAULT 0,
        is_automated INTEGER NOT NULL DEFAULT 0, labels TEXT NOT NULL DEFAULT '[]');
        INSERT INTO messages (id, source, channel, author, ts, text) VALUES ('s:1', 'slack', '#a', 'Bo', 0, 'ty');""")
    db.commit()
    db.close()
    s = Store(path)
    assert s.by_rid(1).intent == "ack"
    s.close()
