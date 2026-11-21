"""Open loops: memory across days. A multi-day story, each day one briefing."""

from datetime import UTC, timedelta

from contextos.pipeline import loops as loopmem
from contextos.pipeline.digest import make_digest
from tests.conftest import NOW, FakeLLM, msg

MON = NOW - timedelta(days=2, hours=2)
TUE = NOW - timedelta(days=1)
WED = NOW


def briefing(loops_opened=(), loops_updated=(), needs_you=()):
    return {"headline": "", "needs_you": list(needs_you), "important": [], "fyi": [],
            "loops_opened": list(loops_opened), "loops_updated": list(loops_updated)}


def day(store, cfg, end, out):
    llm = FakeLLM(json_out=out)
    return make_digest(store, llm, cfg, end - timedelta(days=1), end, UTC), llm


def ask_from_priya(n=1, ts=MON, **kw):
    base = dict(id=f"gmail:{n}", source="gmail", channel="Inbox", author="Priya", title="Q3 invoice", thread_id="g1",
                text="Can you approve the Q3 invoice by Friday?", is_to_me=True, ts=ts)
    base.update(kw)
    return msg(n, **base)


def open_invoice_loop(store, cfg, m):
    d, _ = day(store, cfg, MON + timedelta(hours=1), briefing(loops_opened=[
        {"kind": "you_owe", "who": "Priya", "title": "Approve Q3 invoice", "detail": "She needs approval by Friday.",
         "due": "2026-11-13", "refs": [m.ref]}]))
    return d


def test_loop_is_opened_and_carried_into_the_next_day(store, cfg):
    m = ask_from_priya()
    store.upsert([m])
    d = open_invoice_loop(store, cfg, m)
    assert d.loops.opened == 1
    [lp] = store.loops("open")
    assert lp.threads == ["gmail:t:g1"] and lp.due == "2026-11-13"

    # Tuesday: nothing about the invoice, but the loop rides along as one line.
    store.upsert([msg(50, ts=TUE - timedelta(hours=2), text="lunch?")])
    d2, llm = day(store, cfg, TUE, briefing())
    prompt = llm.calls[0]["prompt"]
    assert f"[{lp.ref}] you owe Priya" in prompt and "due 2026-11-13" in prompt and f"(from {m.ref})" in prompt
    assert "Can you approve" not in prompt  # state is carried, not the raw message
    assert d2.loops.carried == 1 and store.loops("open")
    assert m.ref in d2.messages  # Monday's email is still a valid citation for "still waiting" items


def test_your_reply_closes_the_loop_without_the_model(store, cfg):
    m = ask_from_priya()
    store.upsert([m])
    open_invoice_loop(store, cfg, m)

    reply = ask_from_priya(2, ts=TUE - timedelta(hours=3), author="Sam", is_from_me=True, is_to_me=False,
                           text="Approved.")
    store.upsert([reply])
    d, llm = day(store, cfg, TUE, briefing())
    assert d.loops.auto_closed == 1
    assert "<open_loops>\n(none)" in llm.calls[0]["prompt"]  # closed before the model saw anything
    [lp] = store.loops("closed")
    assert lp.closed_reason == "you replied" and lp.closed_ref == reply.ref


def test_model_can_resolve_only_with_todays_evidence(store, cfg):
    m = ask_from_priya()
    store.upsert([m])
    open_invoice_loop(store, cfg, m)
    [lp] = store.loops("open")

    other = msg(60, ts=TUE - timedelta(hours=1), channel="#finance", author="Ravi", text="Q3 invoice paid by Sam's team")
    store.upsert([other])
    # Citing Monday's message (not today's) must not close it.
    d, _ = day(store, cfg, TUE, briefing(loops_updated=[{"loop": lp.ref, "status": "resolved", "note": "done", "refs": [m.ref]}]))
    assert d.loops.resolved == 0 and d.loops.rejected and store.loops("open")
    # With today's evidence it closes.
    resolve = {"loop": lp.ref, "status": "resolved", "note": "Ravi says paid", "refs": [other.ref]}
    d, _ = day(store, cfg, TUE, briefing(loops_updated=[resolve]))
    assert d.loops.resolved == 1
    assert store.get_loop(lp.id).closed_reason.startswith("resolved: Ravi says paid")


def test_news_updates_a_loop_and_duplicates_merge(store, cfg):
    m = ask_from_priya()
    store.upsert([m])
    open_invoice_loop(store, cfg, m)
    [lp] = store.loops("open")

    nudge = ask_from_priya(3, ts=TUE - timedelta(hours=1), text="Friendly reminder on the invoice!")
    store.upsert([nudge])
    d, _ = day(store, cfg, TUE, briefing(
        loops_updated=[{"loop": lp.ref, "status": "still_open", "note": "Priya nudged again.", "refs": [nudge.ref]}],
        # the model also (wrongly) opens it again: same thread → merged, not duplicated
        loops_opened=[{"kind": "you_owe", "who": "Priya", "title": "Invoice", "detail": "x", "due": "", "refs": [nudge.ref]}],
    ))
    assert d.loops.updated == 1 and d.loops.merged == 1 and d.loops.opened == 0
    [lp2] = store.loops("open")
    assert lp2.id == lp.id and nudge.ref in lp2.refs and lp2.updated_at == nudge.ts


def test_loop_opened_and_answered_the_same_day_closes(store, cfg):
    m = ask_from_priya(ts=MON)
    reply = ask_from_priya(2, ts=MON + timedelta(minutes=30), author="Sam", is_from_me=True, is_to_me=False,
                           text="Approved, it's in the system now.")
    store.upsert([m, reply])
    d = open_invoice_loop(store, cfg, m)
    assert d.loops.opened == 1 and d.loops.auto_closed == 1 and not store.loops("open")


def test_rejects_uncited_or_invented_loops(store, cfg):
    m = ask_from_priya()
    store.upsert([m])
    d, _ = day(store, cfg, MON + timedelta(hours=1), briefing(
        loops_opened=[{"kind": "you_owe", "who": "X", "title": "made up", "detail": "", "due": "", "refs": ["m999"]}],
        loops_updated=[{"loop": "L42", "status": "resolved", "note": "", "refs": [m.ref]}],
    ))
    assert d.loops.opened == 0 and len(d.loops.rejected) == 2 and not store.loops(None)


def test_quiet_loops_go_stale_and_budget_prefers_deadlines(store, cfg):
    old = store.add_loop("owed_to_you", "Bob", "old", "", None, ["m1"], [], NOW - timedelta(days=10))
    past_due = store.add_loop("you_owe", "Ann", "past", "", "2026-11-01", ["m2"], [], NOW - timedelta(days=9))
    fresh = store.add_loop("owed_to_you", "Cy", "fresh", "", None, ["m3"], [], NOW - timedelta(hours=1))
    due = store.add_loop("owed_to_you", "Di", "due", "", "2026-11-09", ["m4"], [], NOW - timedelta(days=1))
    owe = store.add_loop("you_owe", "Ed", "owe", "", None, ["m5"], [], NOW - timedelta(days=2))

    gone = loopmem.expire(store, store.loops("open"), NOW)
    assert {lp.id for lp in gone} == {old, past_due}
    carried, over = loopmem.select_carried(store.loops("open"), limit=2)
    assert [lp.id for lp in carried] == [due, owe] and over == 1
    assert fresh  # kept open, just not carried this time


def test_marking_a_briefing_item_done_closes_its_loops(store, cfg):
    from web.views import close_loops_for

    m = ask_from_priya()
    store.upsert([m])
    open_invoice_loop(store, cfg, m)
    assert close_loops_for(store, [m.ref]) == 1
    assert store.loops("closed")[0].closed_reason == "marked done"


def test_public_channel_without_thread_has_no_reply_key():
    assert loopmem.conversation_key(msg(1, channel="#eng")) is None
    assert loopmem.conversation_key(msg(1, channel="DM: Priya")) == "slack:c:DM: Priya"
    assert loopmem.conversation_key(msg(1, thread_id="123")) == "slack:t:123"


def test_a_promise_is_not_an_answer(store, cfg):
    m = ask_from_priya()
    store.upsert([m])
    open_invoice_loop(store, cfg, m)

    promise = ask_from_priya(2, ts=TUE - timedelta(hours=5), author="Sam", is_from_me=True, is_to_me=False,
                             text="I'll look at it tomorrow")
    store.upsert([promise])
    d, llm = day(store, cfg, TUE, briefing())
    [lp] = store.loops("open")  # still open
    assert d.loops.auto_closed == 0
    assert lp.promised_at == promise.ts and lp.due == "2026-11-07"  # "tomorrow", from the reply sent on the 6th
    assert "promised · due 2026-11-07" in llm.calls[0]["prompt"]

    # Next day the actual answer lands in the thread: now it closes.
    done = ask_from_priya(3, ts=WED - timedelta(hours=2), author="Sam", is_from_me=True, is_to_me=False,
                          text="Approved and sent to finance.")
    store.upsert([done])
    d, _ = day(store, cfg, WED, briefing())
    assert d.loops.auto_closed == 1 and store.get_loop(lp.id).closed_ref == done.ref


def test_waiting_on_closes_when_they_deliver_in_the_thread(store, cfg):
    ask = msg(1, ts=MON, author="Sam", is_from_me=True, thread_id="t9", text="Bob, can you send the deck by Friday?")
    store.upsert([ask])
    day(store, cfg, MON + timedelta(hours=1), briefing(loops_opened=[
        {"kind": "owed_to_you", "who": "Bob", "title": "Deck from Bob", "detail": "", "due": "", "refs": [ask.ref]}]))
    [lp] = store.loops("open")
    assert lp.due == "2026-11-06"  # filled from the message's own "by Friday" when the model left it empty

    store.upsert([msg(2, ts=TUE - timedelta(hours=4), author="Bob", thread_id="t9", text="sure, will do")])
    day(store, cfg, TUE, briefing())
    assert store.get_loop(lp.id).status == "open" and store.get_loop(lp.id).promised_at

    store.upsert([msg(3, ts=WED - timedelta(hours=4), author="Bob", thread_id="t9", text="here it is: deck_v3.pdf")])
    d, _ = day(store, cfg, WED, briefing())
    assert store.get_loop(lp.id).closed_reason == "Bob replied"


def test_rule_candidates_are_offered_to_the_model(store, cfg):
    buried = msg(1, ts=MON, channel="#eng", is_to_me=True, text="@sam could you check the staging config?")
    chatter = msg(2, ts=MON + timedelta(minutes=1), channel="#eng", text="lunch was great")
    answered = msg(3, ts=MON, channel="DM: Ann", author="Ann", is_to_me=True, text="can you call me?")
    reply = msg(4, ts=MON + timedelta(minutes=5), channel="DM: Ann", author="Sam", is_from_me=True, text="calling now")
    store.upsert([buried, chatter, answered, reply])
    d, llm = day(store, cfg, MON + timedelta(hours=1), briefing(loops_opened=[
        {"kind": "you_owe", "who": "Alice", "title": "Check staging config", "detail": "", "due": "", "refs": [buried.ref]}]))
    assert f"<loop_candidates>{buried.ref}</loop_candidates>" in llm.calls[0]["prompt"]
    assert d.loops.candidates == 1 and d.loops.candidates_opened == 1
