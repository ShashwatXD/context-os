"""A realistic, labeled benchmark inbox for one busy day (plus two weeks of history for search questions).

Persona: a software engineer at "Northwind". Everything is fictional. Generation is deterministic (fixed seed),
so every run measures the same data and results are comparable across changes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from contextos.models import Message

ME = "me@northwind.dev"


@dataclass
class Question:
    text: str                    # what the user would type
    args: dict                   # the search call a model would make for it (query/person/after/before/channel)
    expected: list[str]          # message ids that answer it
    kind: str                    # keyword | typo | meaning | time | exact | hinglish


@dataclass
class Benchmark:
    now: datetime
    messages: list[Message]
    needs_you: dict[str, list[str]]         # label → message ids; an item counts as caught if any id is cited
    already_handled: list[str]              # asks you already answered: should NOT be in Needs you
    questions: list[Question] = field(default_factory=list)


def build(now: datetime, seed: int = 7) -> Benchmark:
    rng = random.Random(seed)
    msgs: list[Message] = []
    counter = iter(range(1, 10_000))

    def at(hours_ago: float) -> datetime:
        return now - timedelta(hours=hours_ago)

    def add(source, channel, author, hours_ago, text, *, title=None, to_me=False, from_me=False, automated=False,
            labels=None, thread=None, mid=None) -> str:
        mid = mid or f"{source}:b{next(counter):03d}"
        msgs.append(Message(
            id=mid, source=source, channel=channel, author=author, ts=at(hours_ago), text=text, title=title,
            thread_id=thread, url=f"https://example.com/{mid}", is_to_me=to_me, is_from_me=from_me,
            is_automated=automated, labels=labels or [],
        ))
        return mid

    gmail = lambda *a, **k: add("gmail", "Sent" if k.get("from_me") else "Inbox", *a, **k)  # noqa: E731
    slack = lambda ch, *a, **k: add("slack", ch, *a, **k)  # noqa: E731
    discord = lambda *a, **k: add("discord", "Side Project #general", *a, **k)  # noqa: E731

    # ---- the 10 things that genuinely need you today -------------------------------------------
    n = {}
    n["contract"] = [
        gmail("Priya Shah", 9, "Hi, can you review and sign the Acme vendor contract by 5pm today? Legal approved clause 4.",
              title="Acme vendor contract: signature needed", to_me=True, thread="t-contract"),
        slack("DM: Priya Shah", "Priya Shah", 4, "pinging again on the Acme contract, need it before 5", to_me=True),
    ]
    n["design_review"] = [gmail("Arjun Mehta", 8, "Shared the payments v2 design doc. Could you review it before Monday's planning?",
                                title="Design doc: payments v2", to_me=True)]
    n["q3_numbers"] = [slack("DM: Meera Iyer", "Meera Iyer", 3, "can you send me the Q3 latency numbers before standup tomorrow?", to_me=True)]
    n["interview"] = [gmail("Rohan Kapoor", 7, "Could you confirm the Thursday 3pm interview slot with the platform team?",
                            title="Interview confirmation", to_me=True)]
    n["pr_approve"] = [slack("#eng", "Bob Lee", 5, "@you can you approve PR #318? it unblocks the release", to_me=True)]
    n["landing_copy"] = [discord("Kai", 6, "@you can you look at the landing page copy tonight?", to_me=True)]
    n["expenses"] = [gmail("Northwind HR", 10, "Reminder: please submit your October expense report by Friday.",
                           title="Expense report due Friday", to_me=True)]
    n["client_call"] = [gmail("Dana Cruz", 2, "We need to move tomorrow's call. Does 11am or 4pm work better for you?",
                              title="Rescheduling tomorrow's call", to_me=True)]
    n["review_request"] = [gmail("GitHub", 6, "Arjun Mehta requested your review on PR #321: retry logic for webhooks",
                                 title="[northwind/api] Review requested: PR #321", automated=True,
                                 labels=["CATEGORY_UPDATES"])]
    n["oncall_swap"] = [slack("DM: Bob Lee", "Bob Lee", 1.5, "could you swap on-call with me next Wednesday? family thing", to_me=True)]

    # ---- a request you already handled (should NOT land in Needs you) -------------------------
    neha_ask = slack("DM: Neha Rao", "Neha Rao", 11, "can you send me the onboarding deck?", to_me=True)
    slack("DM: Neha Rao", "me", 10.5, "sent it, check your inbox", from_me=True)

    # ---- important, but not an ask -------------------------------------------------------------
    slack("#eng", "Bob Lee", 7, "staging deploy is failing since 11, looking into it")
    slack("#eng", "Bob Lee", 5.5, "if it's not fixed by EOD we roll back the release")
    gmail("Stripe", 4, "A payment of $2,400 for invoice #2291 failed: card declined.", title="Payment failed",
          automated=True, labels=["CATEGORY_UPDATES"])
    gmail("HDFC Bank", 3, "A new device signed in to your account. If this wasn't you, call us immediately.",
          title="Security alert: new sign-in", automated=True)
    slack("#announcements", "Meera Iyer", 6, "The offsite moves to the 21st. Same venue.")

    # ---- noise: promotions (dropped), social (dropped), newsletters & notifications (headlines) -
    promos = ["50% off running shoes this weekend", "Your cart is waiting", "Flash sale: noise-cancelling headphones",
              "New arrivals you'll love", "Last chance: annual plan 40% off", "Free shipping on your next order",
              "Members-only early access", "Your weekly deals are here"]
    for _ in range(35):
        gmail(rng.choice(["ShopKart", "Nike", "Myntra", "Zomato", "Audible"]), rng.uniform(0, 23),
              f"{rng.choice(promos)}. Shop now and save before midnight. Unsubscribe anytime.",
              title=rng.choice(promos), automated=True, labels=["CATEGORY_PROMOTIONS"])
    for _ in range(10):
        gmail(rng.choice(["LinkedIn", "Instagram", "X"]), rng.uniform(0, 23),
              rng.choice(["You appeared in 9 searches this week", "Someone viewed your profile", "New follower"]),
              title="Notification", automated=True, labels=["CATEGORY_SOCIAL"])
    letters = ["TLDR: 5 stories on AI chips", "The Pragmatic Engineer: on-call culture", "Morning Brew: markets rally",
               "Python Weekly #712", "Lenny's Newsletter: pricing pages", "Hacker Newsletter #701"]
    for _ in range(25):
        t = rng.choice(letters)
        gmail(t.split(":")[0], rng.uniform(0, 23), f"{t}. " + "Long-form newsletter content. " * 40,
              title=t, automated=True, labels=["CATEGORY_UPDATES"])
    for _ in range(18):
        pr = rng.randint(290, 330)
        gmail("GitHub", rng.uniform(0, 23), f"CI passed for PR #{pr}. 214 checks succeeded.",
              title=f"[northwind/api] Run succeeded: PR #{pr}", automated=True, labels=["CATEGORY_UPDATES"])
    for _ in range(10):
        slack("#deploys", "deploybot", rng.uniform(0, 23), f"Deployed api@{rng.randint(1000, 9999)} to staging",
              automated=True)

    # ---- everyday chatter ----------------------------------------------------------------------
    eng = ["anyone seen flaky tests in the billing suite?", "bumped the node version on CI", "lunch at 1?",
           "merged the logging cleanup", "the dashboard is slow again", "who owns the cron for invoices?",
           "pairing on the migration after lunch", "added alerts for the queue depth", "rebasing now",
           "reviewed, left two nits", "the docs build is green again", "thanks!"]
    for _ in range(30):
        slack("#eng", rng.choice(["Bob Lee", "Arjun Mehta", "Sara Kim", "Tom Park"]), rng.uniform(0, 23), rng.choice(eng))
    rand = ["coffee machine is fixed", "who's up for cricket saturday?", "new memes channel when", "happy birthday Tom!",
            "the AC on floor 3 is broken again"]
    for _ in range(15):
        slack("#random", rng.choice(["Sara Kim", "Tom Park", "Neha Rao"]), rng.uniform(0, 23), rng.choice(rand))
    disc = ["pushed the new onboarding mocks", "anyone tried the new font?", "deployed the preview build", "gm",
            "fixed the mobile nav"]
    for _ in range(12):
        discord(rng.choice(["Kai", "Lena", "Omar"]), rng.uniform(0, 23), rng.choice(disc))

    # ---- history (older than today) for search questions ---------------------------------------
    h = {}
    h["laptop"] = gmail("IT Helpdesk", 24 * 6, "Your MacBook screen replacement is approved. Drop it at desk 4B.",
                        title="Hardware request approved", to_me=True)
    h["pto"] = slack("DM: Meera Iyer", "Meera Iyer", 24 * 9, "approved your leave for the 24th to 28th", to_me=True)
    h["salary"] = gmail("Northwind Payroll", 24 * 12, "Your payslip for October is ready. Net pay credited on the 30th.",
                        title="Payslip ready", automated=True)
    h["reimb"] = gmail("Northwind Finance", 24 * 5, "Your travel reimbursement of ₹18,500 has been processed.",
                       title="Reimbursement processed", to_me=True)
    h["flight"] = gmail("IndiGo", 24 * 3, "Booking confirmed: BLR to DEL, 6E 2134, departing 07:10 on the 14th.",
                        title="Your booking is confirmed", automated=True)
    h["bob_old1"] = slack("#eng", "Bob Lee", 24 * 4, "the redis upgrade is done, keep an eye on memory")
    h["bob_old2"] = slack("#eng", "Bob Lee", 24 * 11, "postmortem doc for the outage is up")
    h["priya_old"] = gmail("Priya Shah", 24 * 8, "Sharing the first draft of the Acme contract for your comments.",
                           title="Acme contract: first draft", to_me=True)
    h["upset"] = slack("DM: Dana Cruz", "Dana Cruz", 24 * 2, "honestly I'm really frustrated with how long the fix is taking",
                       to_me=True)
    h["pr142"] = slack("#eng", "Sara Kim", 24 * 7, "PR #142 fixes the refund rounding bug")
    for _ in range(20):
        slack("#eng", rng.choice(["Sara Kim", "Tom Park", "Arjun Mehta"]), rng.uniform(30, 24 * 13), rng.choice(eng))

    day = lambda d: (now - timedelta(days=d)).strftime("%Y-%m-%d")  # noqa: E731
    qs = [
        Question("what did Priya say about the contract?", {"query": "contract", "person": "Priya"}, n["contract"] + [h["priya_old"]], "keyword"),
        Question("priyta ne contract ke baare me kya bola?", {"query": "contract", "person": "priyta"}, n["contract"] + [h["priya_old"]], "typo"),
        Question("what did meeera ask me?", {"person": "meeera"}, n["q3_numbers"] + [h["pto"]], "typo"),
        Question("anything from bobb lee about on-call?", {"query": "on-call swap", "person": "bobb"}, n["oncall_swap"], "typo"),
        Question("any payment problems?", {"query": "payment problem"}, [_id(msgs, "invoice #2291")], "meaning"),
        Question("is my laptop repair sorted?", {"query": "laptop repair"}, [h["laptop"]], "meaning"),
        Question("when is my vacation approved for?", {"query": "vacation approved"}, [h["pto"]], "meaning"),
        Question("did my salary come?", {"query": "salary"}, [h["salary"]], "meaning"),
        Question("is anyone unhappy with us?", {"query": "unhappy customer"}, [h["upset"]], "meaning"),
        Question("when is my trip to Delhi?", {"query": "trip to Delhi"}, [h["flight"]], "meaning"),
        Question("any security warning on my bank?", {"query": "bank security warning"}, [_id(msgs, "new device signed in")], "meaning"),
        Question("paise wapas aaye travel ke?", {"query": "travel paise wapas"}, [h["reimb"]], "hinglish"),
        Question("kisi ne interview ke baare me pucha?", {"query": "interview pucha"}, n["interview"], "hinglish"),
        Question("what did Bob say last week?", {"person": "Bob", "after": day(6), "before": day(2)}, [h["bob_old1"]], "time"),
        Question("what did Bob post around the outage?", {"query": "outage", "person": "Bob"}, [h["bob_old2"]], "time"),
        Question("Priya's emails 8 days ago", {"person": "Priya", "after": day(9), "before": day(7)}, [h["priya_old"]], "time"),
        Question("what is PR #142?", {"query": "PR #142"}, [h["pr142"]], "exact"),
        Question("who asked about PR #318?", {"query": "PR #318"}, n["pr_approve"], "exact"),
        Question("invoice 2291?", {"query": "invoice 2291"}, [_id(msgs, "invoice #2291")], "exact"),
        Question("who wants me to review a design doc?", {"query": "design doc review"}, n["design_review"], "keyword"),
        Question("expense report deadline?", {"query": "expense report"}, n["expenses"], "keyword"),
        Question("did the client want to move our meeting?", {"query": "client move meeting"}, n["client_call"], "meaning"),
        Question("what happened with staging?", {"query": "staging deploy failing"}, [_id(msgs, "staging deploy is failing")], "keyword"),
        Question("when is the offsite?", {"query": "offsite"}, [_id(msgs, "offsite moves")], "keyword"),
        Question("who needs the onboarding deck?", {"query": "onboarding deck"}, [neha_ask], "keyword"),
    ]
    return Benchmark(now, msgs, n, [neha_ask], qs)


def _id(msgs: list[Message], needle: str) -> str:
    return next(m.id for m in msgs if needle in m.text)

