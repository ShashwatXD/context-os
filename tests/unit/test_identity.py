from contextos.pipeline.ask import Tools
from contextos.pipeline.identity import Alias, resolve, tokens
from contextos.pipeline.search import Searcher, SearchRequest
from tests.conftest import msg


def groups(people):
    return sorted(sorted(a.key for a in p.aliases) for p in people)


def test_tokens_strip_accents_and_separators():
    assert tokens("Priyá  Shah (Acme)") == ["priya", "shah", "acme"]
    assert tokens("priya.shah_99") == ["priya", "shah", "99"]


def test_full_name_email_and_handle_merge_across_apps():
    people = resolve([
        Alias("gmail", "Priya Shah", "gmail:priya.shah@acme.com"),
        Alias("slack", "priya shah", "slack:U1"),
        Alias("discord", "priya_shah", "discord:9"),
        Alias("gmail", "Rahul Verma", "gmail:rahul@acme.com"),
    ])
    assert groups(people) == [
        ["discord|priya_shah", "gmail|Priya Shah", "slack|priya shah"],
        ["gmail|Rahul Verma"],
    ]
    assert next(p for p in people if len(p.aliases) == 3).name == "Priya Shah"


def test_email_local_part_links_a_handle():
    people = resolve([Alias("gmail", "P. Shah", "gmail:priyashah@acme.com"), Alias("discord", "priyashah", "discord:9")])
    assert len(people) == 1


def test_first_name_joins_only_when_unique():
    unique = resolve([Alias("gmail", "Priya Shah"), Alias("slack", "Priya")])
    assert len(unique) == 1
    ambiguous = resolve([Alias("gmail", "Sam Lee"), Alias("gmail", "Sam Patel"), Alias("slack", "Sam")])
    assert len(ambiguous) == 3


def test_generic_mailbox_does_not_merge_people():
    people = resolve([Alias("gmail", "Acme Team", "gmail:team@acme.com"), Alias("discord", "team")])
    assert len(people) == 2


def test_manual_overrides_win():
    merged = resolve([Alias("gmail", "Priya Shah"), Alias("discord", "pshah_dev")], merges=[("Priya Shah", "pshah_dev")])
    assert len(merged) == 1
    split = resolve([Alias("gmail", "Priya Shah"), Alias("slack", "Priya Shah")], splits=[("Priya Shah", "Priya Shah")])
    assert len(split) == 2


def test_store_rebuild_and_same_person(store):
    store.upsert([
        msg(1, source="gmail", channel="Inbox", author="Priya Shah", author_id="gmail:priya.shah@acme.com", text="contract ready"),
        msg(2, author="priyashah", source="discord", channel="Side #general", author_id="discord:9", text="pushed the fix"),
        msg(3, author="Bob", text="lunch?"),
        msg(4, author="me", is_from_me=True, text="hi"),
    ])
    assert store.rebuild_identities() == 2
    assert set(store.same_person(["Priya Shah"])) == {"Priya Shah", "priyashah"}
    assert store.same_person(["Nobody"]) == ["Nobody"]
    linked = store.identities(min_sources=2)
    assert [p["name"] for p in linked] == ["Priya Shah"]


def test_search_by_person_finds_every_app(store):
    store.upsert([
        msg(1, source="gmail", channel="Inbox", author="Priya Shah", author_id="gmail:priya.shah@acme.com", text="contract ready"),
        msg(2, author="priyashah", source="discord", channel="Side #general", text="contract has a typo"),
    ])
    store.rebuild_identities()
    res = Searcher(store).search(SearchRequest(person="Priya Shah"))
    assert {m.source for m in res.messages} == {"gmail", "discord"}
    assert any("same person elsewhere" in n for n in res.notes)


def test_who_is_tool(store):
    store.upsert([
        msg(1, source="gmail", channel="Inbox", author="Priya Shah", author_id="gmail:priya.shah@acme.com"),
        msg(2, author="priya_shah", source="slack"),
    ])
    store.rebuild_identities()
    out, err = Tools(store, tz=None).run("who_is", {"person": "priya"})
    assert not err
    assert "gmail: Priya Shah <priya.shah@acme.com>" in out and "slack: priya_shah" in out


def test_override_persists_through_rebuild(store):
    store.upsert([msg(1, author="Priya Shah"), msg(2, author="pshah_dev", source="discord")])
    store.add_identity_override("Priya Shah", "pshah_dev", "merge")
    store.rebuild_identities()
    assert set(store.same_person(["pshah_dev"])) == {"Priya Shah", "pshah_dev"}
