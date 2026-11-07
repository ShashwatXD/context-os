from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from contextos.config import Config
from contextos.models import Message
from contextos.storage import Store

NOW = datetime(2026, 11, 7, 15, 0, tzinfo=UTC)


def msg(n: int, **kw) -> Message:
    base = dict(
        id=f"slack:C1:{n}",
        source="slack",
        channel="#eng",
        author="Alice",
        ts=NOW - timedelta(hours=5) + timedelta(minutes=n),
        text=f"message number {n}",
    )
    base.update(kw)
    return Message(**base)


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(home=tmp_path, user_name="Sam")


@pytest.fixture
def store(cfg: Config) -> Store:
    s = Store(cfg.db_path)
    yield s
    s.close()


class FakeLLM:
    """Stands in for contextos.llm.LLM. Records calls; returns canned outputs. No network."""

    def __init__(self, json_out=None, text_out="- notes [m1]", turns=None):
        self.json_out = json_out
        self.text_out = text_out
        self.turns = list(turns or [])
        self.calls: list[dict] = []

    def text(self, **kw):
        self.calls.append({"kind": "text", **kw})
        return self.text_out

    def json(self, **kw):
        self.calls.append({"kind": "json", **kw})
        return self.json_out

    @staticmethod
    def user_message(text):
        return {"role": "user", "text": text}

    @staticmethod
    def tool_results(results):
        return {"role": "user", "results": [(c.name, content, is_error) for c, content, is_error in results]}

    def tool_turn(self, **kw):
        self.calls.append({"kind": "tool_turn", **kw, "history": list(kw["history"])})
        return self.turns.pop(0)

    def usage_summary(self):
        return {"total_tokens": 1234}

    def cost_usd(self):
        return None


def tool_call(name, args):
    from contextos.llm import ToolCall

    return ToolCall(id=None, name=name, args=args)


def turn(text="", *calls):
    from contextos.llm import ToolTurn

    return ToolTurn(text=text, calls=list(calls), message={"role": "model", "text": text})
