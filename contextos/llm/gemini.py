"""Thin wrapper around Google's Gemini SDK: plain text, JSON output, tool-calling turns, usage tracking.

The rest of ContextOS only talks to this class, so swapping model providers means changing this file.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field

from google import genai
from google.genai import errors, types

MISSING_KEY = "No Gemini API key. Add GEMINI_API_KEY=... to your .env file and restart ContextOS."

# Finish reasons that mean "the model stopped on purpose, but not because it was done".
BLOCKED = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}


class LLMError(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str | None
    name: str
    args: dict


@dataclass
class ToolTurn:
    text: str
    calls: list[ToolCall] = field(default_factory=list)
    message: object = None  # the model's turn, to append to history unchanged


def api_key_from_env() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


class LLM:
    def __init__(self, client: genai.Client | None = None):
        if client is None:
            key = api_key_from_env()
            if not key:
                raise LLMError(MISSING_KEY)
            client = genai.Client(api_key=key)
        self.client = client
        self.usage: dict[str, dict[str, int]] = defaultdict(lambda: {"input": 0, "output": 0, "calls": 0})

    # ---- one-shot calls -----------------------------------------------------

    def text(self, *, model: str, system: str, prompt: str, max_tokens: int = 8192) -> str:
        config = types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens)
        return _text_of(self._generate(model, prompt, config))

    def json(self, *, model: str, system: str, prompt: str, schema: dict, max_tokens: int = 16384) -> dict:
        """Structured output: Gemini constrains the response to `schema`, so json.loads is safe."""
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        try:
            return json.loads(_text_of(self._generate(model, prompt, config)))
        except json.JSONDecodeError as e:
            raise LLMError(f"Gemini returned invalid JSON: {e}") from e

    # ---- embeddings (meaning search) ----------------------------------------

    def embed(self, texts: list[str], *, model: str, task: str, dim: int = 768, batch: int = 100) -> list[list[float]]:
        """Turn texts into meaning vectors.

        task = "RETRIEVAL_DOCUMENT" for stored messages, "RETRIEVAL_QUERY" for a search question: the model
        tunes each side of the search differently. dim < 3072 truncates the vector (the model is trained so
        shorter prefixes keep most of the quality), trading a little accuracy for 4x less storage and compute.
        """
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch):
            chunk = texts[i : i + batch]
            try:
                resp = self.client.models.embed_content(
                    model=model,
                    contents=chunk,
                    config=types.EmbedContentConfig(task_type=task, output_dimensionality=dim),
                )
            except errors.APIError as e:
                raise LLMError(_describe(e, model)) from e
            vectors += [list(e.values or []) for e in resp.embeddings or []]
            bucket = self.usage[model]
            bucket["input"] += sum(len(t) for t in chunk) // 4  # estimate; the embed API doesn't report tokens
            bucket["calls"] += 1
        if len(vectors) != len(texts):
            raise LLMError("Gemini returned the wrong number of embeddings.")
        return vectors

    # ---- tool calling (used by Ask) -----------------------------------------

    @staticmethod
    def user_message(text: str) -> types.Content:
        return types.Content(role="user", parts=[types.Part.from_text(text=text)])

    @staticmethod
    def tool_results(results: list[tuple[ToolCall, str, bool]]) -> types.Content:
        """All results of one turn go back in ONE message, matched to their calls by name/id."""
        parts = [
            types.Part(
                function_response=types.FunctionResponse(
                    id=call.id,
                    name=call.name,
                    response={"error": content} if is_error else {"result": content},
                )
            )
            for call, content, is_error in results
        ]
        return types.Content(role="user", parts=parts)

    def tool_turn(self, *, model: str, system: str, history: list, tools: list[dict]) -> ToolTurn:
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=8192,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t["name"], description=t["description"], parameters_json_schema=t["input_schema"]
                        )
                        for t in tools
                    ]
                )
            ],
            # We run the loop ourselves (ask.py) so every tool call is visible and controlled.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        resp = self._generate(model, history, config)
        content = resp.candidates[0].content
        parts = (content.parts if content else None) or []
        calls = [
            ToolCall(p.function_call.id, p.function_call.name, dict(p.function_call.args or {})) for p in parts if p.function_call
        ]
        text = "".join(p.text for p in parts if p.text and not p.thought).strip()
        return ToolTurn(text=text, calls=calls, message=content)

    # ---- accounting ---------------------------------------------------------

    def cost_usd(self) -> float | None:
        return None  # Gemini prices change often; we report tokens instead.

    def total_tokens(self) -> int:
        return sum(u["input"] + u["output"] for u in self.usage.values())

    def usage_summary(self) -> dict:
        return {"by_model": dict(self.usage), "total_tokens": self.total_tokens()}

    # ---- internals ----------------------------------------------------------

    def _generate(self, model: str, contents, config: types.GenerateContentConfig):
        try:
            resp = self.client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as e:
            raise LLMError(_describe(e, model)) from e

        self._record(model, resp)
        if resp.prompt_feedback and resp.prompt_feedback.block_reason:
            raise LLMError(f"Gemini blocked this request ({resp.prompt_feedback.block_reason}).")
        if not resp.candidates:
            raise LLMError("Gemini returned no answer.")
        reason = str(getattr(resp.candidates[0].finish_reason, "name", resp.candidates[0].finish_reason) or "")
        if reason == "MAX_TOKENS":
            raise LLMError("Gemini's answer was cut off (hit the output limit).")
        if reason in BLOCKED:
            raise LLMError(f"Gemini stopped for safety reasons ({reason}).")
        return resp

    def _record(self, model: str, resp) -> None:
        u = resp.usage_metadata
        if not u:
            return
        bucket = self.usage[model]
        bucket["input"] += u.prompt_token_count or 0
        # Thinking tokens are billed as output.
        bucket["output"] += (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
        bucket["calls"] += 1


def _text_of(resp) -> str:
    parts = (resp.candidates[0].content.parts if resp.candidates[0].content else None) or []
    return "".join(p.text for p in parts if p.text and not p.thought).strip()


def _describe(e: errors.APIError, model: str) -> str:
    msg = (getattr(e, "message", None) or str(e)).strip()
    if e.code in (401, 403) or "API key" in msg:
        return "Your Gemini API key was rejected. Check GEMINI_API_KEY in .env."
    if e.code == 404:
        return f"Gemini model '{model}' wasn't found. Set CONTEXTOS_MAIN_MODEL / CONTEXTOS_WORKER_MODEL in .env."
    if e.code == 429:
        return "Gemini rate limit or quota hit. Try again in a minute."
    return f"Gemini error {e.code}: {msg[:300]}"
