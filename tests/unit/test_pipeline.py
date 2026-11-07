from datetime import UTC, timedelta

from contextos.pipeline.ask import ask
from contextos.pipeline.context import Block, build_blocks, pack
from contextos.pipeline.digest import make_digest, verify_refs
from contextos.pipeline.noise import triage
from tests.conftest import NOW, FakeLLM, msg, tool_call, turn

UTC = UTC


def test_triage_buckets():
    msgs = [
        msg(1),
        msg(2, is_automated=True),
        msg(3, is_automated=True, is_to_me=True),  # a bot DM'ing you still counts
        msg(4, labels=["CATEGORY_PROMOTIONS"]),
        msg(5, channel="#random"),
        msg(6, text="  "),
    ]
    t = triage(msgs, mute=["#random"])
    assert [m.id for m in t.keep] == ["slack:C1:1", "slack:C1:3"]
    assert [m.id for m in t.low] == ["slack:C1:2"]
    assert t.dropped == {"promotions": 1, "muted": 1, "empty": 1}


def test_blocks_group_threads_and_cite(store):
    msgs = [
        msg(1, text="deploy failed", thread_id="t1"),
        msg(2, text="looking", author="Bob", thread_id="t1"),
        msg(3, id="gmail:1", source="gmail", channel="Inbox", title="Invoice", text="pay me", thread_id="g1"),
        msg(4, text="newsletter", is_automated=True),
    ]
    store.upsert(msgs)
    blocks = build_blocks(triage(msgs), UTC)
    rendered = "\n\n".join(b.render() for b in blocks)
    assert '### gmail · "Invoice"' in rendered
    assert "### slack · #eng" in rendered
    assert f"  ↳ [{msgs[1].ref}]" in rendered  # reply nested under parent
    assert "headlines only" in blocks[-1].header


def test_pack_respects_budget_and_splits_big_blocks():
    small = Block("### a", ["x" * 40] * 2)
    big = Block("### big", ["y" * 400] * 10)
    chunks = pack([small, big, small], max_tokens=300)
    assert len(chunks) > 3
    assert all(len(c) // 4 <= 330 for c in chunks)
    assert any("(continued)" in c for c in chunks)


def test_verify_refs_drops_hallucinated_citations():
    out = {
        "needs_you": [{"title": "a", "detail": "", "refs": ["m1", "m99"]}, {"title": "b", "detail": "", "refs": ["[m77]"]}],
        "important": [],
        "fyi": [],
    }
    dropped = verify_refs(out, {"m1"})
    assert dropped == ["m99", "m77"]
    assert out["needs_you"][0]["refs"] == ["m1"] and not out["needs_you"][0]["unverified"]
    assert out["needs_you"][1]["unverified"]


def _digest_json(ref):
    return {
        "headline": "busy day",
        "needs_you": [{"title": "Reply to Alice", "detail": "she asked", "refs": [ref, "m999"]}],
        "important": [],
        "fyi": [],
    }


def test_digest_single_call(store, cfg):
    msgs = [msg(1, text="can you review my PR?", is_to_me=True), msg(2)]
    store.upsert(msgs)
    llm = FakeLLM(json_out=_digest_json(msgs[0].ref))
    d = make_digest(store, llm, cfg, NOW - timedelta(days=1), NOW, UTC)

    assert [c["kind"] for c in llm.calls] == ["json"]
    prompt = llm.calls[0]["prompt"]
    assert f"[{msgs[0].ref}]" in prompt and "(to you)" in prompt
    assert "untrusted" in llm.calls[0]["system"]
    assert d.dropped_refs == ["m999"]
    assert d.output["needs_you"][0]["refs"] == [msgs[0].ref]
    assert store.db.execute("SELECT COUNT(*) FROM digests").fetchone()[0] == 1


def test_digest_map_reduce_when_over_budget(store, cfg):
    cfg.token_budget, cfg.chunk_tokens = 200, 150
    msgs = [msg(i, text="word " * 60, channel=f"#c{i}") for i in range(8)]
    store.upsert(msgs)
    llm = FakeLLM(json_out=_digest_json(msgs[0].ref), text_out=f"- something [{msgs[0].ref}]")
    d = make_digest(store, llm, cfg, NOW - timedelta(days=1), NOW, UTC)

    kinds = [c["kind"] for c in llm.calls]
    assert kinds.count("text") == d.chunks > 1 and kinds[-1] == "json"
    assert all(c["model"] == cfg.worker_model for c in llm.calls if c["kind"] == "text")
    assert "Notes, part 1 of" in llm.calls[-1]["prompt"]


def test_digest_empty_window_makes_no_llm_call(store, cfg):
    llm = FakeLLM()
    d = make_digest(store, llm, cfg, NOW - timedelta(days=1), NOW, UTC)
    assert d.empty and llm.calls == []


def test_ask_runs_tool_loop_and_verifies_citations(store, cfg):
    m = msg(1, text="the launch moved to Friday", ts=NOW.replace(year=2099))  # "recent" relative to real now
    store.upsert([m])
    llm = FakeLLM(
        turns=[
            turn("Let me search.", tool_call("search_messages", {"query": "launch"})),
            turn(f"The launch moved to Friday [{m.ref}]. Also see [m424242]."),
        ]
    )
    r = ask("when is the launch?", store, llm, cfg, UTC)

    assert r.steps == 2
    assert list(r.cited) == [m.ref]
    assert r.unknown_refs == ["m424242"]
    history = llm.calls[1]["history"]
    assert history[0] == {"role": "user", "text": "when is the launch?"}
    assert history[1]["role"] == "model"  # model turn kept as-is
    name, content, is_error = history[2]["results"][0]
    assert name == "search_messages" and "launch moved" in content and is_error is False


def test_ask_tool_errors_are_returned_to_model(store, cfg):
    llm = FakeLLM(
        turns=[
            turn("", tool_call("get_thread", {"ref": "m5"})),
            turn("I couldn't find it."),
        ]
    )
    r = ask("?", store, llm, cfg, UTC)
    name, content, is_error = llm.calls[1]["history"][-1]["results"][0]
    assert is_error is True and "No message" in content
    assert r.answer == "I couldn't find it."
