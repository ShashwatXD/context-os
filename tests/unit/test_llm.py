"""The Gemini wrapper, tested against real SDK response objects (no network)."""

from types import SimpleNamespace

import pytest
from google.genai import errors, types

from contextos.llm import LLM, LLMError, ToolCall


def response(parts, finish="STOP", prompt_tokens=100, out_tokens=20, thoughts=5):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts), finish_reason=finish)],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt_tokens, candidates_token_count=out_tokens, thoughts_token_count=thoughts
        ),
    )


class FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def generate_content(self, *, model, contents, config):
        self.requests.append({"model": model, "contents": contents, "config": config})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def make(*responses):
    models = FakeModels(responses)
    return LLM(client=SimpleNamespace(models=models)), models


def test_json_uses_schema_and_counts_tokens():
    llm, models = make(response([types.Part(text='{"headline": "hi"}')]))
    out = llm.json(model="gemini-x", system="sys", prompt="p", schema={"type": "object"})
    assert out == {"headline": "hi"}
    cfg = models.requests[0]["config"]
    assert cfg.response_mime_type == "application/json" and cfg.response_json_schema == {"type": "object"}
    assert cfg.system_instruction == "sys"
    assert llm.usage["gemini-x"] == {"input": 100, "output": 25, "calls": 1}


def test_text_skips_thought_parts():
    llm, _ = make(response([types.Part(text="thinking…", thought=True), types.Part(text="answer")]))
    assert llm.text(model="m", system="s", prompt="p") == "answer"


def test_tool_turn_parses_calls_and_builds_results():
    call = types.Part(function_call=types.FunctionCall(id="c1", name="search_messages", args={"query": "launch"}))
    llm, models = make(response([types.Part(text="Searching."), call]))
    tools = [{"name": "search_messages", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    turn = llm.tool_turn(model="m", system="s", history=[llm.user_message("q")], tools=tools)

    assert turn.calls == [ToolCall("c1", "search_messages", {"query": "launch"})]
    assert turn.text == "Searching." and turn.message.role == "model"
    cfg = models.requests[0]["config"]
    assert cfg.automatic_function_calling.disable is True
    assert cfg.tools[0].function_declarations[0].name == "search_messages"

    msg = llm.tool_results([(turn.calls[0], "found 2", False), (ToolCall(None, "get_thread", {}), "nope", True)])
    fr = [p.function_response for p in msg.parts]
    assert fr[0].id == "c1" and fr[0].response == {"result": "found 2"}
    assert fr[1].response == {"error": "nope"}


@pytest.mark.parametrize("finish,needle", [("MAX_TOKENS", "cut off"), ("SAFETY", "safety")])
def test_bad_finish_reasons_raise(finish, needle):
    llm, _ = make(response([types.Part(text="x")], finish=finish))
    with pytest.raises(LLMError, match=needle):
        llm.text(model="m", system="s", prompt="p")


@pytest.mark.parametrize("code,needle", [(400, "API key"), (404, "wasn't found"), (429, "rate limit")])
def test_api_errors_become_friendly(code, needle):
    body = {"error": {"code": code, "message": "API key not valid" if code == 400 else "x", "status": "X"}}
    llm, _ = make(errors.ClientError(code, body))
    with pytest.raises(LLMError, match=needle):
        llm.text(model="m", system="s", prompt="p")
