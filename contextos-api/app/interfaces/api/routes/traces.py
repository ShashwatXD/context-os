"""Observability & Trace Inspection API Routes."""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from app.infrastructure.repositories.trace_repo import TraceRepository
from app.interfaces.api.dependencies import get_trace_repo

router = APIRouter(prefix="/traces", tags=["Observability"])


@router.get("/{run_id}")
async def get_trace_by_run_id(
    run_id: str,
    trace_repo: TraceRepository = Depends(get_trace_repo),
) -> Dict[str, Any]:
    run = await trace_repo.get_run_with_spans(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace with run ID '{run_id}' not found",
        )
    return {
        "run_id": run.id,
        "agent_id": run.agent_id,
        "trigger_event": run.trigger_event,
        "input_prompt": run.input_prompt,
        "status": run.status.value,
        "latency_ms": run.latency_ms,
        "total_tokens": run.total_tokens,
        "prompt_tokens": run.prompt_tokens,
        "completion_tokens": run.completion_tokens,
        "estimated_cost_usd": run.estimated_cost_usd,
        "output_response": run.output_response,
        "retrieved_context_ids": run.retrieved_context_ids,
        "error_message": run.error_message,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "spans": [
            {
                "id": s.id,
                "parent_span_id": s.parent_span_id,
                "span_type": s.span_type.value,
                "name": s.name,
                "input_payload": s.input_payload,
                "output_payload": s.output_payload,
                "latency_ms": s.latency_ms,
                "status": s.status,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
            }
            for s in run.spans
        ],
    }

