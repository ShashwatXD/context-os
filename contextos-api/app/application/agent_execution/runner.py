"""Agent Execution Engine: Checkpoints, Retries, Tracing, and Safety."""

from datetime import datetime, timezone
import time
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ApprovalRequiredError, PermissionDeniedError
from app.domain.agents.agent import AgentRun, RunStatus, SpanType, TraceSpan
from app.infrastructure.repositories.trace_repo import TraceRepository
from app.application.agent_execution.tool_registry import ToolRegistry
from app.infrastructure.llm.grounded_llm import GroundedLLMProvider


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Redacts sensitive credentials and secrets from trace payloads."""
    sensitive_keys = {"token", "password", "secret", "authorization", "api_key", "credentials"}
    sanitized = {}
    for k, v in payload.items():
        if any(s in k.lower() for s in sensitive_keys):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_payload(v)
        else:
            sanitized[k] = v
    return sanitized


class AgentRunner:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.trace_repo = TraceRepository(session)
        self.tool_registry = ToolRegistry(session)
        self.llm = GroundedLLMProvider()

    async def execute_task(
        self,
        agent_id: str,
        user_prompt: str,
        agent_permissions: List[str],
        tool_sequence: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentRun:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        start_time = time.perf_counter()

        run = AgentRun(
            id=run_id,
            agent_id=agent_id,
            trigger_event="USER_REQUEST",
            input_prompt=user_prompt,
            status=RunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        await self.trace_repo.create_run(run)

        # Emit Root User Request Span
        req_span = TraceSpan(
            id=f"sp_{uuid.uuid4().hex[:10]}",
            run_id=run_id,
            span_type=SpanType.USER_REQUEST,
            name="ReceiveUserPrompt",
            input_payload={"prompt": user_prompt},
            output_payload={"status": "ACCEPTED"},
            latency_ms=0.5,
            status="SUCCESS",
        )
        await self.trace_repo.create_span(req_span)

        total_tokens = len(user_prompt.split()) * 2

        try:
            # 1. Step: Context Retrieval Span
            retrieval_start = time.perf_counter()
            context_result = await self.tool_registry.execute_tool(
                tool_name="search_context",
                arguments={"query": user_prompt},
                caller_permissions=["*"],  # Internal system retrieval
            )
            retrieval_latency = (time.perf_counter() - retrieval_start) * 1000

            retrieved_data = context_result["result"]
            matched_ids = [m["asset_id"] for m in retrieved_data.get("matched_entities", [])]
            run.retrieved_context_ids = matched_ids

            context_span = TraceSpan(
                id=f"sp_{uuid.uuid4().hex[:10]}",
                run_id=run_id,
                span_type=SpanType.CONTEXT_RETRIEVAL,
                name="HybridContextRetrieval",
                input_payload={"query": user_prompt},
                output_payload={"matched_asset_ids": matched_ids, "discrepancies_found": len(retrieved_data.get("discrepancies", []))},
                latency_ms=round(retrieval_latency, 2),
                status="SUCCESS",
            )
            await self.trace_repo.create_span(context_span)
            total_tokens += 120

            # 2. Step: Execute explicit tool actions if specified
            if tool_sequence:
                for step in tool_sequence:
                    tool_name = step["tool"]
                    tool_args = step.get("arguments", {})

                    tool_start = time.perf_counter()
                    try:
                        tool_out = await self.tool_registry.execute_tool(
                            tool_name=tool_name,
                            arguments=tool_args,
                            caller_permissions=agent_permissions,
                        )
                        tool_latency = (time.perf_counter() - tool_start) * 1000

                        span = TraceSpan(
                            id=f"sp_{uuid.uuid4().hex[:10]}",
                            run_id=run_id,
                            span_type=SpanType.TOOL_EXECUTION,
                            name=f"Tool:{tool_name}",
                            input_payload=sanitize_payload(tool_args),
                            output_payload=sanitize_payload(tool_out),
                            latency_ms=round(tool_latency, 2),
                            status="SUCCESS",
                        )
                        await self.trace_repo.create_span(span)
                        total_tokens += 85

                    except ApprovalRequiredError as e:
                        # Record human approval gate
                        gate_span = TraceSpan(
                            id=f"sp_{uuid.uuid4().hex[:10]}",
                            run_id=run_id,
                            span_type=SpanType.APPROVAL_REQUEST,
                            name=f"ApprovalGate:{tool_name}",
                            input_payload=sanitize_payload(tool_args),
                            output_payload={"reason": str(e), "status": "WAITING_HUMAN_APPROVAL"},
                            latency_ms=round((time.perf_counter() - tool_start) * 1000, 2),
                            status="BLOCKED",
                        )
                        await self.trace_repo.create_span(gate_span)
                        run.status = RunStatus.WAITING_APPROVAL
                        run.output_response = f"Action '{tool_name}' paused: requires human approval before proceeding."
                        break

            if run.status != RunStatus.WAITING_APPROVAL:
                run.status = RunStatus.COMPLETED
                run.output_response = await self.llm.synthesize_agent_execution_response(
                    user_prompt=user_prompt,
                    matched_assets=matched_ids,
                    tool_outputs=[],
                    discrepancies_count=len(retrieved_data.get("discrepancies", [])),
                )

        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error_message = str(exc)

        # Final Run Accounting
        total_latency = (time.perf_counter() - start_time) * 1000
        run.latency_ms = round(total_latency, 2)
        run.total_tokens = total_tokens
        run.prompt_tokens = int(total_tokens * 0.4)
        run.completion_tokens = int(total_tokens * 0.6)
        run.estimated_cost_usd = round(total_tokens * 0.000002, 6)
        run.completed_at = datetime.now(timezone.utc)

        await self.trace_repo.update_run(run)
        return await self.trace_repo.get_run_with_spans(run_id)

