"""Agents and Execution API Routes."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from app.domain.agents.agent import Agent, AgentRun
from app.infrastructure.repositories.trace_repo import TraceRepository
from app.application.agent_execution.runner import AgentRunner
from app.interfaces.api.dependencies import get_trace_repo, get_agent_runner
from app.interfaces.api.schemas.api_schemas import AgentRunRequest

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("")
async def list_agents(trace_repo: TraceRepository = Depends(get_trace_repo)) -> List[Dict[str, Any]]:
    agents = await trace_repo.list_agents()
    return [
        {
            "id": a.id,
            "name": a.name,
            "version": a.version,
            "role": a.role,
            "system_prompt": a.system_prompt,
            "allowed_tools": a.allowed_tools,
            "is_active": a.is_active,
            "created_at": a.created_at,
        }
        for a in agents
    ]


@router.post("/{agent_id}/run")
async def run_agent(
    agent_id: str,
    req: AgentRunRequest,
    agent_runner: AgentRunner = Depends(get_agent_runner),
    trace_repo: TraceRepository = Depends(get_trace_repo),
) -> Dict[str, Any]:
    agents = await trace_repo.list_agents()
    agent = next((a for a in agents if a.id == agent_id), None)
    permissions = agent.allowed_tools if agent else ["*"]

    run: AgentRun = await agent_runner.execute_task(
        agent_id=agent_id,
        user_prompt=req.user_prompt,
        agent_permissions=permissions,
        tool_sequence=req.tool_sequence,
    )
    return {
        "run_id": run.id,
        "status": run.status.value,
        "output_response": run.output_response,
        "latency_ms": run.latency_ms,
        "total_tokens": run.total_tokens,
        "retrieved_context_ids": run.retrieved_context_ids,
        "spans_count": len(run.spans),
    }


@router.get("/{agent_id}/runs")
async def list_agent_runs(
    agent_id: str,
    limit: int = 50,
    trace_repo: TraceRepository = Depends(get_trace_repo),
) -> List[Dict[str, Any]]:
    runs = await trace_repo.list_runs(agent_id=agent_id, limit=limit)
    return [
        {
            "id": r.id,
            "agent_id": r.agent_id,
            "trigger_event": r.trigger_event,
            "input_prompt": r.input_prompt,
            "status": r.status.value,
            "latency_ms": r.latency_ms,
            "total_tokens": r.total_tokens,
            "estimated_cost_usd": r.estimated_cost_usd,
            "output_response": r.output_response,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
        }
        for r in runs
    ]

