"""AI Evaluations & Benchmark API Routes."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends
from app.application.evaluation.eval_service import EvaluationService
from app.interfaces.api.dependencies import get_evaluation_service
from app.interfaces.api.schemas.api_schemas import EvalRunRequest

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])


@router.get("")
async def list_evaluations(
    limit: int = 50,
    eval_service: EvaluationService = Depends(get_evaluation_service),
) -> List[Dict[str, Any]]:
    runs = await eval_service.list_evaluation_runs(limit=limit)
    return [
        {
            "id": r.id,
            "dataset_id": r.dataset_id,
            "dataset_version": r.dataset_version,
            "model_version": r.model_version,
            "overall_recall_at_k": r.overall_recall_at_k,
            "overall_entity_resolution_accuracy": r.overall_entity_resolution_accuracy,
            "overall_context_relevance": r.overall_context_relevance,
            "policy_compliance_rate": r.policy_compliance_rate,
            "average_latency_ms": r.average_latency_ms,
            "total_cost_usd": r.total_cost_usd,
            "results_count": len(r.results),
            "executed_at": r.executed_at,
        }
        for r in runs
    ]


@router.post("/run")
async def trigger_evaluation_run(
    req: EvalRunRequest,
    eval_service: EvaluationService = Depends(get_evaluation_service),
) -> Dict[str, Any]:
    run = await eval_service.run_evaluation(model_version=req.model_version or "contextos-hybrid-v1.0")
    return {
        "run_id": run.id,
        "dataset_name": run.dataset_id,
        "model_version": run.model_version,
        "overall_recall_at_k": run.overall_recall_at_k,
        "overall_context_relevance": run.overall_context_relevance,
        "policy_compliance_rate": run.policy_compliance_rate,
        "average_latency_ms": run.average_latency_ms,
        "executed_at": run.executed_at,
        "results": [r.model_dump() for r in run.results],
    }

