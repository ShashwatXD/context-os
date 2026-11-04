"""Evaluation Benchmark Repository Implementation."""

from typing import List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.evaluation.evaluation import EvalResult, EvalRun
from app.infrastructure.database.models import EvaluationRunModel


class EvaluationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(self, run: EvalRun) -> EvalRun:
        results_data = [r.model_dump() for r in run.results]
        model = EvaluationRunModel(
            id=run.id,
            dataset_id=run.dataset_id,
            dataset_version=run.dataset_version,
            model_version=run.model_version,
            overall_recall_at_k=run.overall_recall_at_k,
            overall_entity_resolution_accuracy=run.overall_entity_resolution_accuracy,
            overall_context_relevance=run.overall_context_relevance,
            policy_compliance_rate=run.policy_compliance_rate,
            average_latency_ms=run.average_latency_ms,
            total_cost_usd=run.total_cost_usd,
            results_payload=results_data,
            executed_at=run.executed_at,
        )
        self.session.add(model)
        await self.session.flush()
        return run

    async def get_by_id(self, run_id: str) -> Optional[EvalRun]:
        stmt = select(EvaluationRunModel).where(EvaluationRunModel.id == run_id)
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return self._to_domain(model)

    async def list_runs(self, limit: int = 50) -> List[EvalRun]:
        stmt = select(EvaluationRunModel).order_by(desc(EvaluationRunModel.executed_at)).limit(limit)
        res = await self.session.execute(stmt)
        return [self._to_domain(m) for m in res.scalars().all()]

    def _to_domain(self, model: EvaluationRunModel) -> EvalRun:
        results = [
            EvalResult(
                test_case_id=r.get("test_case_id", ""),
                recall_at_k=r.get("recall_at_k", 0.0),
                entity_resolution_accuracy=r.get("entity_resolution_accuracy", 0.0),
                context_relevance=r.get("context_relevance", 0.0),
                policy_compliant=r.get("policy_compliant", True),
                latency_ms=r.get("latency_ms", 0.0),
                success=r.get("success", True),
                error_details=r.get("error_details"),
            )
            for r in (model.results_payload or [])
        ]
        return EvalRun(
            id=model.id,
            dataset_id=model.dataset_id,
            dataset_version=model.dataset_version,
            model_version=model.model_version,
            overall_recall_at_k=model.overall_recall_at_k,
            overall_entity_resolution_accuracy=model.overall_entity_resolution_accuracy,
            overall_context_relevance=model.overall_context_relevance,
            policy_compliance_rate=model.policy_compliance_rate,
            average_latency_ms=model.average_latency_ms,
            total_cost_usd=model.total_cost_usd,
            results=results,
            executed_at=model.executed_at,
        )

