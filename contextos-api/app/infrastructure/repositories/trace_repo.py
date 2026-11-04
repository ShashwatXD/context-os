"""Agent & Distributed Trace Repository Implementation."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.domain.agents.agent import Agent, AgentRun, RunStatus, SpanType, TraceSpan
from app.infrastructure.database.models import AgentModel, AgentRunModel, TraceSpanModel


class TraceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def register_agent(self, agent: Agent) -> Agent:
        model = AgentModel(
            id=agent.id,
            name=agent.name,
            version=agent.version,
            role=agent.role,
            system_prompt=agent.system_prompt,
            allowed_tools_payload=agent.allowed_tools,
            is_active=agent.is_active,
            created_at=agent.created_at,
        )
        self.session.add(model)
        await self.session.flush()
        return agent

    async def list_agents(self) -> List[Agent]:
        stmt = select(AgentModel).order_by(AgentModel.name)
        res = await self.session.execute(stmt)
        return [
            Agent(
                id=m.id,
                name=m.name,
                version=m.version,
                role=m.role,
                system_prompt=m.system_prompt,
                allowed_tools=m.allowed_tools_payload or [],
                is_active=m.is_active,
                created_at=m.created_at,
            )
            for m in res.scalars().all()
        ]

    async def create_run(self, run: AgentRun) -> AgentRun:
        model = AgentRunModel(
            id=run.id,
            agent_id=run.agent_id,
            trigger_event=run.trigger_event,
            input_prompt=run.input_prompt,
            status=run.status.value,
            latency_ms=run.latency_ms,
            total_tokens=run.total_tokens,
            prompt_tokens=run.prompt_tokens,
            completion_tokens=run.completion_tokens,
            estimated_cost_usd=run.estimated_cost_usd,
            output_response=run.output_response,
            retrieved_context_payload=run.retrieved_context_ids,
            error_message=run.error_message,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )
        self.session.add(model)
        await self.session.flush()
        return run

    async def update_run(self, run: AgentRun) -> AgentRun:
        stmt = select(AgentRunModel).where(AgentRunModel.id == run.id)
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if model:
            model.status = run.status.value
            model.latency_ms = run.latency_ms
            model.total_tokens = run.total_tokens
            model.prompt_tokens = run.prompt_tokens
            model.completion_tokens = run.completion_tokens
            model.estimated_cost_usd = run.estimated_cost_usd
            model.output_response = run.output_response
            model.retrieved_context_payload = run.retrieved_context_ids
            model.error_message = run.error_message
            model.completed_at = run.completed_at or datetime.now(timezone.utc)
            await self.session.flush()
        return run

    async def create_span(self, span: TraceSpan) -> TraceSpan:
        model = TraceSpanModel(
            id=span.id,
            run_id=span.run_id,
            parent_span_id=span.parent_span_id,
            span_type=span.span_type.value,
            name=span.name,
            input_payload=span.input_payload,
            output_payload=span.output_payload,
            latency_ms=span.latency_ms,
            status=span.status,
            error_message=span.error_message,
            started_at=span.started_at,
            ended_at=span.ended_at,
        )
        self.session.add(model)
        await self.session.flush()
        return span

    async def get_run_with_spans(self, run_id: str) -> Optional[AgentRun]:
        stmt = (
            select(AgentRunModel)
            .where(AgentRunModel.id == run_id)
            .options(selectinload(AgentRunModel.spans))
        )
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None

        spans = [
            TraceSpan(
                id=s.id,
                run_id=s.run_id,
                parent_span_id=s.parent_span_id,
                span_type=SpanType(s.span_type),
                name=s.name,
                input_payload=s.input_payload or {},
                output_payload=s.output_payload or {},
                latency_ms=s.latency_ms,
                status=s.status,
                error_message=s.error_message,
                started_at=s.started_at,
                ended_at=s.ended_at,
            )
            for s in sorted(model.spans, key=lambda x: x.started_at)
        ]

        return AgentRun(
            id=model.id,
            agent_id=model.agent_id,
            trigger_event=model.trigger_event,
            input_prompt=model.input_prompt,
            status=RunStatus(model.status),
            latency_ms=model.latency_ms,
            total_tokens=model.total_tokens,
            prompt_tokens=model.prompt_tokens,
            completion_tokens=model.completion_tokens,
            estimated_cost_usd=model.estimated_cost_usd,
            output_response=model.output_response,
            retrieved_context_ids=model.retrieved_context_payload or [],
            error_message=model.error_message,
            spans=spans,
            started_at=model.started_at,
            completed_at=model.completed_at,
        )

    async def list_runs(
        self, agent_id: Optional[str] = None, limit: int = 50
    ) -> List[AgentRun]:
        stmt = select(AgentRunModel)
        if agent_id:
            stmt = stmt.where(AgentRunModel.agent_id == agent_id)
        stmt = stmt.order_by(desc(AgentRunModel.started_at)).limit(limit)
        res = await self.session.execute(stmt)
        return [
            AgentRun(
                id=m.id,
                agent_id=m.agent_id,
                trigger_event=m.trigger_event,
                input_prompt=m.input_prompt,
                status=RunStatus(m.status),
                latency_ms=m.latency_ms,
                total_tokens=m.total_tokens,
                prompt_tokens=m.prompt_tokens,
                completion_tokens=m.completion_tokens,
                estimated_cost_usd=m.estimated_cost_usd,
                output_response=m.output_response,
                retrieved_context_ids=m.retrieved_context_payload or [],
                error_message=m.error_message,
                started_at=m.started_at,
                completed_at=m.completed_at,
            )
            for m in res.scalars().all()
        ]

