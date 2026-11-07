from datetime import timedelta

from contextos.store import fts_query
from tests.conftest import NOW, msg


def test_upsert_is_idempotent_and_assigns_rids(store):
    a, b = msg(1), msg(2)
    assert store.upsert([a, b]) == 2
    assert a.rid and b.rid and a.rid != b.rid

    edited = msg(1, text="edited text")
    assert store.upsert([edited]) == 0
    assert edited.rid == a.rid
    assert store.by_rid(a.rid).text == "edited text"
    assert store.counts() == {"slack": 2}


def test_between_is_time_ordered(store):
    store.upsert([msg(3), msg(1), msg(2)])
    got = store.between(NOW - timedelta(days=1), NOW)
    assert [m.id for m in got] == ["slack:C1:1", "slack:C1:2", "slack:C1:3"]


def test_search_ranks_and_updates_index(store):
    store.upsert([
        msg(1, text="the Q3 invoice from Priya is overdue"),
        msg(2, text="lunch?"),
        msg(3, text="invoice approved", source="gmail", id="gmail:x", title="Invoice"),
    ])
    assert {m.id for m in store.search("invoice")} == {"slack:C1:1", "gmail:x"}
    assert [m.id for m in store.search("invoice", source="gmail")] == ["gmail:x"]

    store.upsert([msg(2, text="the invoice again")])  # edits must be re-indexed
    assert "slack:C1:2" in {m.id for m in store.search("invoice")}
    assert store.search("lunch") == []


def test_fts_query_neutralizes_syntax():
    assert fts_query('invoice AND "drop table" (x) *') == '"invoice" OR "and" OR "drop" OR "table"'
    assert fts_query("!!") == ""


def test_thread_and_activity(store):
    store.upsert([msg(1, thread_id="t1"), msg(2, thread_id="t1"), msg(3, channel="#random")])
    assert len(store.thread("t1")) == 2
    activity = {(s, c): n for s, c, n, _ in store.activity(NOW - timedelta(days=1))}
    assert activity == {("slack", "#eng"): 2, ("slack", "#random"): 1}
