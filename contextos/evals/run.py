"""Score every code-only layer against the hand labels in data.py. No model, no network, under a second.

    intent      per-class precision / recall / F1, macro F1, accuracy
    due         exact-date accuracy, plus false deadlines (a date where there is none)
    loops       precision / recall of "this message should become an open loop"
    identity    pairwise precision / recall: of all alias pairs, which are the same person
    guard       precision / recall of prompt-injection detection

The same function backs `contextos eval` and the CI gate (tests/evals), so the numbers in the README are
the numbers CI enforces. Failures are listed case by case: that list is the to-do list.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, time, timedelta
from itertools import combinations
from pathlib import Path

from contextos.evals import data
from contextos.models import Message
from contextos.pipeline import guard, intent, loops
from contextos.pipeline.identity import Alias, resolve

INTENTS = ("request", "question", "commitment", "decision", "ack", "info")


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "tp": tp, "fp": fp, "fn": fn}


def _message(i: int, text: str, from_me: bool, ts: datetime | None = None, **kw) -> Message:
    return Message(id=f"eval:{i}", source="slack", channel=kw.pop("channel", "#eng"), author="me" if from_me else "Alex",
                   ts=ts or datetime(2026, 11, 4, 10, tzinfo=UTC), text=text, is_from_me=from_me, **kw)


def eval_intent() -> dict:
    gold, pred, misses = [], [], []
    for i, (text, from_me, label) in enumerate(data.INTENT):
        got = intent.classify(_message(i, text, from_me))
        gold.append(label)
        pred.append(got)
        if got != label:
            misses.append(f"{text!r}: expected {label}, got {got}")
    per_class = {}
    for c in INTENTS:
        tp = sum(g == c and p == c for g, p in zip(gold, pred, strict=True))
        fp = sum(g != c and p == c for g, p in zip(gold, pred, strict=True))
        fn = sum(g == c and p != c for g, p in zip(gold, pred, strict=True))
        per_class[c] = _prf(tp, fp, fn)
    return {
        "cases": len(gold),
        "accuracy": round(sum(g == p for g, p in zip(gold, pred, strict=True)) / len(gold), 3),
        "macro_f1": round(sum(v["f1"] for v in per_class.values()) / len(per_class), 3),
        "per_class": per_class,
        "failures": misses,
    }


def eval_due() -> dict:
    right, false_deadline, misses = 0, 0, []
    for i, (text, sent, gold) in enumerate(data.DUE):
        ts = datetime.combine(datetime.fromisoformat(sent).date(), time(10), tzinfo=UTC)
        got = intent.due_hint(_message(i, text, False, ts))
        if got == gold:
            right += 1
        else:
            misses.append(f"{text!r} sent {sent}: expected {gold}, got {got}")
            false_deadline += gold is None and got is not None
    return {"cases": len(data.DUE), "accuracy": round(right / len(data.DUE), 3), "false_deadlines": false_deadline,
            "false_deadlines_ok": int(false_deadline == 0), "failures": misses}


def eval_loops() -> dict:
    """Store each conversation for real (so intent and guard tagging run), then ask which messages are open loops."""
    from contextos.storage import Store

    tp = fp = fn = 0
    misses = []
    start = datetime(2026, 11, 4, 9, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "eval.db")
        for case in data.LOOPS:
            msgs = [
                Message(id=f"loop:{mid}", source="slack", channel=f"DM: {case['dm']}", author=author,
                        ts=start + timedelta(minutes=minute), text=text, is_from_me=from_me, is_to_me=to_me,
                        is_automated=bool(case.get("automated")) and not from_me)
                for mid, author, from_me, to_me, text, minute in case["messages"]
            ]
            store.upsert(msgs)
            got = {m.id.split(":", 1)[1] for m in loops.candidates(msgs, [])}
            gold = set(case["gold"])
            tp, fp, fn = tp + len(got & gold), fp + len(got - gold), fn + len(gold - got)
            if got != gold:
                misses.append(f"{case['name']}: expected {sorted(gold)}, got {sorted(got)}")
        store.close()
    return {"cases": len(data.LOOPS), **_prf(tp, fp, fn), "failures": misses}


def eval_identity() -> dict:
    aliases = [Alias(s, a, aid) for s, a, aid, _ in data.IDENTITY]
    gold = {Alias(s, a, aid).key: person for s, a, aid, person in data.IDENTITY}
    found = {a.key: i for i, p in enumerate(resolve(aliases)) for a in p.aliases}
    tp = fp = fn = 0
    misses = []
    for x, y in combinations(gold, 2):
        same_gold, same_found = gold[x] == gold[y], found[x] == found[y]
        tp += same_gold and same_found
        fp += same_found and not same_gold
        fn += same_gold and not same_found
        if same_gold != same_found:
            misses.append(f"{x} ~ {y}: {'missed merge' if same_gold else 'wrong merge'}")
    return {"aliases": len(aliases), "people": len(set(gold.values())), **_prf(tp, fp, fn), "failures": misses}


def eval_guard() -> dict:
    tp = fp = fn = 0
    misses = []
    for text, gold in data.GUARD:
        got = bool(guard.check(text))
        tp, fp, fn = tp + (got and gold), fp + (got and not gold), fn + (gold and not got)
        if got != gold:
            misses.append(f"{text!r}: {'false alarm' if got else 'missed injection'}")
    return {"cases": len(data.GUARD), **_prf(tp, fp, fn), "failures": misses}


def run() -> dict:
    return {
        "intent": eval_intent(),
        "due": eval_due(),
        "loops": eval_loops(),
        "identity": eval_identity(),
        "guard": eval_guard(),
    }


# What CI enforces. Set a little under the current scores, so a regression fails the build but noise doesn't.
# Raise them when a change improves a layer; never lower them to make a failing change pass.
THRESHOLDS = {
    ("intent", "macro_f1"): 0.95,
    ("due", "accuracy"): 0.90,
    ("due", "false_deadlines_ok"): 1,  # inventing a deadline is worse than missing one
    ("loops", "f1"): 0.85,
    ("identity", "precision"): 1.0,  # a wrong merge mixes two people's messages: no tolerance
    ("identity", "recall"): 0.85,
    ("guard", "precision"): 0.85,
    ("guard", "recall"): 0.95,
}


def gate(report: dict) -> list[str]:
    """Threshold failures, as readable lines. Empty means the gate passes."""
    return [
        f"{layer}.{metric} = {report[layer][metric]} (minimum {floor})"
        for (layer, metric), floor in THRESHOLDS.items()
        if report[layer][metric] < floor
    ]
