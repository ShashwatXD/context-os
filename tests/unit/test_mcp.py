"""The MCP server, exercised through the real MCP SDK (list_tools / call_tool), no network."""

import asyncio
from datetime import UTC, datetime, timedelta

from contextos.mcp_server import create_server
from contextos.services.indexing import index_messages
from tests.conftest import FakeLLM, msg


def call(server, name, args):
    result = asyncio.run(server.call_tool(name, args))
    return result.content[0].text


def make(cfg, monkeypatch, store):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    now = datetime.now(UTC)
    store.upsert([
        msg(1, author="Priya Shah", channel="DM: Priya Shah", text="please sign the contract by 5pm",
            url="https://slack/1", ts=now - timedelta(hours=2)),
        msg(2, author="Bob", channel="#eng", text="the invoice bounced, card declined", url="https://slack/2",
            ts=now - timedelta(hours=1)),
    ])
    index_messages(store, FakeLLM(), cfg)
    return create_server(config_loader=lambda: cfg, llm_factory=lambda c: FakeLLM())


def test_tools_are_listed_read_only(cfg, monkeypatch, store):
    server = make(cfg, monkeypatch, store)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == {"search_messages", "get_thread", "recent_activity", "latest_briefing"}
    assert all(t.annotations.read_only_hint for t in tools.values())
    assert "person" in tools["search_messages"].input_schema["properties"]


def test_search_with_typo_returns_cited_links(cfg, monkeypatch, store):
    out = call(make(cfg, monkeypatch, store), "search_messages", {"query": "contract", "person": "priyta"})
    assert "'priyta' matched: Priya Shah" in out
    assert "sign the contract" in out and "https://slack/1" in out


def test_keyword_search_and_activity(cfg, monkeypatch, store):
    server = make(cfg, monkeypatch, store)
    assert "invoice bounced" in call(server, "search_messages", {"query": "invoice"})
    assert "#eng: 1 messages" in call(server, "recent_activity", {"days": 1})


def test_briefing_when_missing_and_present(cfg, monkeypatch, store):
    server = make(cfg, monkeypatch, store)
    assert "No briefing written yet" in call(server, "latest_briefing", {})
    now = datetime.now(UTC)
    store.save_digest(now - timedelta(hours=1), now, [1], {
        "headline": "Priya needs a signature.",
        "needs_you": [{"title": "Sign the contract", "detail": "By 5pm.", "refs": ["m1"]}],
        "important": [], "fyi": [],
    }, {})
    out = call(server, "latest_briefing", {"window": "24h"})
    assert "NEEDS YOU (1)" in out and "Sign the contract" in out and "(https://slack/1)" in out


def test_bad_input_is_reported_not_crashing(cfg, monkeypatch, store):
    out = call(make(cfg, monkeypatch, store), "search_messages", {})
    assert out.startswith("Error:")
