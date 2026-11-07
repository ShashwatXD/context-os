import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from contextos.services import scheduler, tasks
from contextos.storage import ItemAction
from tests.conftest import FakeLLM, msg, tool_call, turn
from web.app import create_app
from web.views import answer_html, item_key, item_state

UTC = UTC


@pytest.fixture
def client(cfg, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    llm = FakeLLM()
    app = create_app(
        config_loader=lambda: cfg, llm_factory=lambda c: llm, start_scheduler=False, allowed_hosts=("testserver", "localhost")
    )
    with TestClient(app) as c:
        c.llm = llm
        yield c


def seed_digest(store):
    now = datetime.now(UTC)
    m1 = msg(1, text="can you review my PR?", is_to_me=True, url="https://slack/1", ts=now - timedelta(minutes=30))
    m2 = msg(2, text="deploy broke", ts=now - timedelta(minutes=20))
    store.upsert([m1, m2])
    output = {
        "headline": "Alice needs a review.",
        "needs_you": [{"title": "Review Alice's PR", "detail": "She asked at 10.", "refs": [m1.ref], "unverified": False}],
        "important": [{"title": "Deploy broke", "detail": "Bob is on it.", "refs": [m2.ref], "unverified": False}],
        "fyi": [],
    }
    start = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    did = store.save_digest(start, now, [m1.rid, m2.rid], output, {"stats": {"read": {"slack": 2}}, "llm": {"cost_usd": 0.01}})
    return did, m1, m2


def wait_job(c, job_id):
    with c.stream("GET", f"/api/jobs/{job_id}/events") as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    return events


def test_pages_render_empty(client):
    for path in ("/today", "/ask", "/history", "/sources", "/settings"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "ContextOS" in r.text
    assert "Let's get you set up" in client.get("/today").text


def test_today_shows_briefing_with_source_links(client, store):
    seed_digest(store)
    html = client.get("/today").text
    assert "Alice needs a review." in html
    assert "Review Alice&#39;s PR" in html
    assert 'href="https://slack/1"' in html
    assert "Nothing here." in html  # empty FYI


def test_done_then_undo_and_votes(client, store):
    did, m1, _ = seed_digest(store)
    key = item_key({"refs": [m1.ref]})
    base = {"digest_id": did, "section": "needs_you", "key": key}

    r = client.post("/items/action", data={**base, "action": "done"})
    assert r.status_code == 200 and "state-done" in r.text and "Undo" in r.text
    assert "1 done" in client.get("/today").text

    r = client.post("/items/action", data={**base, "action": "reopen"})
    assert "state-open" in r.text

    r = client.post("/items/vote", data={**base, "vote": "-1"})
    assert 'class="vote on" data-vote="-1"' in r.text
    assert store.feedback_rows()[-1]["vote"] == -1

    client.post("/feedback/missed", data={"digest_id": did, "note": "missed the offsite email"})
    assert store.feedback_rows()[-1]["note"] == "missed the offsite email"


def test_snoozed_items_come_back_from_older_briefings(store):
    from web.views import digest_view

    did, m1, _ = seed_digest(store)
    item = store.get_digest(did).output["needs_you"][0]
    store.add_action(did, item_key(item), item["refs"], item, "snooze", until=datetime.now(UTC) - timedelta(minutes=1))
    # a newer briefing that no longer contains that item
    now = datetime.now(UTC)
    new_id = store.save_digest(now - timedelta(hours=1), now, [], {"headline": "", "needs_you": [], "important": [], "fyi": []}, {})
    view = digest_view(store, store.get_digest(new_id), UTC)
    assert [r.title for r in view["reminders"]] == ["Review Alice's PR"]


def test_item_state_follows_citations():
    now = datetime.now(UTC)
    a = ItemAction(1, 1, "m1,m2", ["m1", "m2"], {}, "done", None, now)
    assert item_state("m1", ["m1"], [a], now)[0] == "done"  # covered by an older done
    assert item_state("m1,m3", ["m1", "m3"], [a], now)[0] == "open"  # new message joined → resurfaces


def test_settings_saved_and_secrets_masked(client, cfg):
    r = client.post(
        "/settings",
        data={
            "user_name": "Sam",
            "slack_token": "xoxp-secret",
            "mute": "#random, ads",
            "morning_hour": "7",
            "auto_sync_minutes": "30",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    saved = json.loads(cfg.settings_path.read_text())
    assert saved["slack_token"] == "xoxp-secret" and saved["morning_hour"] == 7
    assert oct(cfg.settings_path.stat().st_mode)[-3:] == "600"
    assert r.headers["location"] == "/settings?saved=1"
    page = client.get("/settings?saved=1").text
    assert "xoxp-secret" not in page and "•••••••• saved" in page and "Saved." in page
    assert "Slack user token" not in client.get("/sources").text
    assert "anthropic" not in page.lower() and 'name="gemini' not in page.lower()  # key is .env-only

    client.post("/settings", data={"user_name": "Sam", "slack_token": ""})  # blank keeps the secret
    assert json.loads(cfg.settings_path.read_text())["slack_token"] == "xoxp-secret"


def test_gmail_credentials_upload_validates(client, cfg):
    bad = client.post("/settings/gmail-credentials", files={"file": ("x.json", b'{"web": {}}')})
    assert bad.status_code == 400
    ok = client.post(
        "/settings/gmail-credentials", files={"file": ("x.json", b'{"installed": {"client_id": "a"}}')}, follow_redirects=False
    )
    assert ok.status_code == 303 and cfg.gmail_credentials.exists()


def test_rejects_other_hosts_and_cross_site_posts(client):
    assert client.get("/today", headers={"host": "evil.example"}).status_code == 403
    r = client.post("/settings", data={"user_name": "x"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_refresh_job_writes_briefing(client, store):
    m = msg(1, text="ping", ts=datetime.now(UTC) - timedelta(minutes=5))
    store.upsert([m])
    client.llm.json_out = {
        "headline": "quiet",
        "needs_you": [],
        "important": [],
        "fyi": [{"title": "ping", "detail": "", "refs": [m.ref]}],
    }
    job = client.post("/api/refresh", data={"window": "24h"}).json()["job"]
    events = wait_job(client, job)
    assert events[-1]["type"] == "done" and events[-1]["result"]["digest_id"]
    assert any("Writing your briefing" in e.get("text", "") for e in events)
    assert "quiet" in client.get("/today?window=24h").text


def test_ask_job_and_answer_card(client, store):
    m = msg(1, text="the launch moved to Friday", url="https://slack/launch", ts=datetime.now(UTC))
    store.upsert([m])
    client.llm.turns = [
        turn("", tool_call("search_messages", {"query": "launch"})),
        turn(f"It moved to **Friday** [{m.ref}]."),
    ]
    job = client.post("/api/ask", data={"question": "when is the launch?"}).json()["job"]
    events = wait_job(client, job)
    assert events[0] == {"type": "step", "text": "Searching launch"}
    ask_id = events[-1]["result"]["ask_id"]
    card = client.get(f"/ask/{ask_id}/card").text
    assert "<strong>Friday</strong>" in card and 'href="https://slack/launch"' in card


def test_job_errors_are_friendly(client, store):
    store.upsert([msg(1, ts=datetime.now(UTC))])

    from contextos.llm import LLMError

    def boom(**_):
        raise LLMError("Your Gemini API key was rejected. Check GEMINI_API_KEY in .env.")

    client.llm.json = boom
    job = client.post("/api/refresh", data={"window": "24h"}).json()["job"]
    assert wait_job(client, job)[-1] == {"type": "error", "text": "Your Gemini API key was rejected. Check GEMINI_API_KEY in .env."}


def test_answer_html_escapes_and_flags_unknown_refs():
    html = str(answer_html("<script>x</script> see [m9]", {}, UTC))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert 'class="ref missing"' in html


def test_scheduler_writes_morning_briefing_once(cfg, store, monkeypatch):
    cfg.slack_token = "xoxp"
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    cfg.morning_hour = 0
    calls = []
    monkeypatch.setattr(tasks, "run_refresh", lambda *a, **k: calls.append("refresh"))
    monkeypatch.setattr(tasks, "run_sync", lambda *a, **k: calls.append("sync"))
    s = scheduler.Scheduler(llm_factory=lambda c: None, config_loader=lambda: cfg)
    t0 = time.time()
    assert s.tick(t0) == "briefing"
    assert s.tick(t0 + 60) is None  # just tried; nothing due
    assert s.tick(t0 + 16 * 60) == "sync" or calls.count("refresh") == 2


def test_llm_requires_env_key(monkeypatch):
    from contextos.llm import LLM, LLMError

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        LLM()
