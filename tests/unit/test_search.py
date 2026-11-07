"""Hybrid search: each test is one real-world scenario."""

from datetime import UTC, datetime, timedelta

import pytest

from contextos.config import Config
from contextos.pipeline.search import Searcher, SearchRequest, parse_date, reciprocal_rank_fusion
from contextos.services.indexing import index_messages
from tests.conftest import NOW, FakeLLM, fake_vector, msg


@pytest.fixture
def searcher(store, cfg: Config):
    store.upsert([
        msg(1, author="Priya Shah", channel="Inbox", source="gmail", id="gmail:1", title="Vendor contract",
            text="Please sign the contract by Friday", ts=NOW - timedelta(days=1)),
        msg(2, author="Priya Shah", channel="DM: Priya Shah", text="pinging again about it", ts=NOW - timedelta(days=10)),
        msg(3, author="Bob", channel="#eng", text="the invoice bounced, card declined", ts=NOW - timedelta(days=2)),
        msg(4, author="me", channel="DM: Priya Shah", text="signed it, sent back", ts=NOW - timedelta(hours=20)),
        msg(5, author="Kai", channel="#design", text="new onboarding mocks are up", ts=NOW - timedelta(days=3)),
        msg(6, author="Bob", channel="#eng", text="PR #142 fixes the refund logic", ts=NOW - timedelta(days=4)),
    ])
    llm = FakeLLM()
    index_messages(store, llm, cfg)
    return Searcher(store, lambda q: fake_vector(q), cfg.embed_model, min_similarity=0.2)


def texts(res):
    return [m.text for m in res.messages]


def test_exact_keyword(searcher):
    assert texts(searcher.search(SearchRequest(query="contract")))[0] == "Please sign the contract by Friday"


def test_name_typo_resolves_person(searcher):
    res = searcher.search(SearchRequest(person="priyta"))
    assert "'priyta' matched: Priya Shah" in res.notes
    # Her messages plus your replies in your DM with her, newest first.
    assert texts(res) == ["signed it, sent back", "Please sign the contract by Friday", "pinging again about it"]


def test_first_name_only(searcher):
    assert searcher.resolve_person("priya") == ["Priya Shah"]


def test_unknown_person_says_so(searcher):
    res = searcher.search(SearchRequest(person="zzyzx"))
    assert res.messages == [] and "No one named 'zzyzx'" in res.notes[0]


def test_word_typo_is_corrected(searcher):
    res = searcher.search(SearchRequest(query="contarct"))
    assert any("also searched 'contract'" in n for n in res.notes)
    assert "Please sign the contract by Friday" in texts(res)


def test_meaning_match_without_shared_words(searcher):
    # "payment" never appears; the (fake) embedding treats invoice ≈ payment.
    res = searcher.search(SearchRequest(query="payment problem"))
    assert texts(res)[0] == "the invoice bounced, card declined"
    assert res.matched_by[res.messages[0].rid] == {"meaning"}


def test_person_plus_time_window(searcher):
    after = NOW - timedelta(days=5)
    res = searcher.search(SearchRequest(person="Priya", after=after))
    assert "pinging again about it" not in texts(res)  # 10 days old: filtered out
    assert len(res.messages) == 2


def test_channel_and_query(searcher):
    res = searcher.search(SearchRequest(query="refund", channel="#eng"))
    assert texts(res) == ["PR #142 fixes the refund logic"]


def test_exact_ids_still_found_by_keywords(searcher):
    assert texts(searcher.search(SearchRequest(query="PR 142")))[0] == "PR #142 fixes the refund logic"


def test_both_methods_agreeing_ranks_first():
    fused = reciprocal_rank_fusion({"keyword": [1, 2, 3], "meaning": [3, 4, 1]})
    assert [rid for rid, _ in fused][:2] == [1, 3]


def test_embedding_failure_falls_back_to_keywords(store, cfg):
    store.upsert([msg(1, text="contract signed")])
    index_messages(store, FakeLLM(), cfg)

    def broken(_):
        raise RuntimeError("quota")

    res = Searcher(store, broken, cfg.embed_model).search(SearchRequest(query="contract"))
    assert texts(res) == ["contract signed"] and "keywords only" in res.notes[0]


def test_indexing_is_incremental_and_reindexes_edits(store, cfg):
    store.upsert([msg(1), msg(2)])
    llm = FakeLLM()
    assert index_messages(store, llm, cfg) == 2
    assert index_messages(store, llm, cfg) == 0            # nothing new: no API calls
    store.upsert([msg(1, text="edited")])
    assert index_messages(store, llm, cfg) == 1            # only the edited one
    assert [c["task"] for c in llm.calls if c["kind"] == "embed"] == ["RETRIEVAL_DOCUMENT"] * 2


def test_parse_date_end_of_day():
    tz = UTC
    assert parse_date("2026-11-03", tz) == datetime(2026, 11, 3, tzinfo=tz)
    assert parse_date("2026-11-03", tz, end_of_day=True) == datetime(2026, 11, 4, tzinfo=tz)
    assert parse_date("not a date", tz) is None
