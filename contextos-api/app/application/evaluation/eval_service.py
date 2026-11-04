"""AI Evaluation Framework: Golden Benchmarks, Metric Calculations, and Regression Detection."""

from datetime import datetime, timezone
import time
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.evaluation.evaluation import (
    EvalDataset,
    EvalResult,
    EvalRun,
    EvalTestCase,
)
from app.infrastructure.repositories.eval_repo import EvaluationRepository
from app.application.context_retrieval.retrieval_service import ContextRetrievalService


def calculate_recall_at_k(retrieved_ids: List[str], expected_ids: List[str], k: int = 5) -> float:
    """Computes Recall@K: proportion of expected entities present in the top-K retrieved list."""
    if not expected_ids:
        return 1.0
    top_k_retrieved = set(retrieved_ids[:k])
    matches = len(top_k_retrieved.intersection(set(expected_ids)))
    return round(matches / len(expected_ids), 4)


def calculate_context_relevance(retrieved_scores: List[float]) -> float:
    """Computes mean relevance score across retrieved items."""
    if not retrieved_scores:
        return 0.0
    return round(sum(retrieved_scores) / len(retrieved_scores), 4)


class EvaluationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.eval_repo = EvaluationRepository(session)
        self.retrieval_service = ContextRetrievalService(session)

    def get_golden_dataset(self) -> EvalDataset:
        """Returns the canonical golden evaluation dataset for Acme Analytics."""
        return EvalDataset(
            id="ds_acme_golden_v1",
            name="Acme Analytics Enterprise Benchmark",
            version="1.0.0",
            description="Golden benchmark for financial metrics, lineage tracing, and definition conflicts.",
            test_cases=[
                EvalTestCase(
                    id="tc_001_revenue_discrepancy",
                    query="Why does our monthly revenue dashboard show a different number from the finance report?",
                    expected_entity_ids=["ast_fct_mrr", "ast_dash_rev"],
                    expected_relationship_types=["CONSUMES", "TRANSFORMS_TO"],
                    expected_discrepancy_types=["DISPUTED_DEFINITION"],
                    must_require_approval=True,
                ),
                EvalTestCase(
                    id="tc_002_customer_lineage",
                    query="Show upstream source tables for active customer dimension",
                    expected_entity_ids=["ast_pg_src_01_analytics_dim_customers"],
                    expected_relationship_types=["BELONGS_TO", "TRANSFORMS_TO"],
                    expected_discrepancy_types=[],
                    must_require_approval=False,
                ),
            ],
        )

    async def run_evaluation(
        self,
        dataset: Optional[EvalDataset] = None,
        model_version: str = "contextos-hybrid-v1.0",
    ) -> EvalRun:
        """Executes the golden evaluation suite and computes grounded benchmark metrics."""
        ds = dataset or self.get_golden_dataset()
        run_id = f"eval_run_{uuid.uuid4().hex[:10]}"
        results: List[EvalResult] = []

        total_latency = 0.0
        recalls: List[float] = []
        relevances: List[float] = []
        compliance_scores: List[bool] = []

        for tc in ds.test_cases:
            start_t = time.perf_counter()
            try:
                # Execute actual hybrid retrieval
                retrieval_out = await self.retrieval_service.query_context(
                    query=tc.query,
                    top_k=5,
                    include_lineage_depth=2,
                )
                latency_ms = (time.perf_counter() - start_t) * 1000
                total_latency += latency_ms

                retrieved_ids = [e.asset_id for e in retrieval_out.matched_entities]
                scores = [e.relevance_score for e in retrieval_out.matched_entities]

                recall = calculate_recall_at_k(retrieved_ids, tc.expected_entity_ids, k=5)
                relevance = calculate_context_relevance(scores)

                # Check policy compliance: if discrepancy was expected, verify it was caught
                policy_ok = True
                if tc.expected_discrepancy_types:
                    found_discrepancy_types = [d.discrepancy_type for d in retrieval_out.discrepancies]
                    if not any(t in found_discrepancy_types for t in tc.expected_discrepancy_types):
                        policy_ok = False

                recalls.append(recall)
                relevances.append(relevance)
                compliance_scores.append(policy_ok)

                results.append(
                    EvalResult(
                        test_case_id=tc.id,
                        recall_at_k=recall,
                        entity_resolution_accuracy=1.0 if recall > 0.0 else 0.0,
                        context_relevance=relevance,
                        policy_compliant=policy_ok,
                        latency_ms=round(latency_ms, 2),
                        success=True,
                    )
                )

            except Exception as exc:
                latency_ms = (time.perf_counter() - start_t) * 1000
                results.append(
                    EvalResult(
                        test_case_id=tc.id,
                        latency_ms=round(latency_ms, 2),
                        success=False,
                        error_details=str(exc),
                    )
                )

        # Aggregate metrics
        avg_recall = round(sum(recalls) / len(recalls), 4) if recalls else 0.0
        avg_relevance = round(sum(relevances) / len(relevances), 4) if relevances else 0.0
        compliance_rate = round(sum(1.0 for c in compliance_scores if c) / len(compliance_scores), 4) if compliance_scores else 1.0
        avg_latency = round(total_latency / len(ds.test_cases), 2) if ds.test_cases else 0.0

        eval_run = EvalRun(
            id=run_id,
            dataset_id=ds.id,
            dataset_version=ds.version,
            model_version=model_version,
            overall_recall_at_k=avg_recall,
            overall_entity_resolution_accuracy=avg_recall,
            overall_context_relevance=avg_relevance,
            policy_compliance_rate=compliance_rate,
            average_latency_ms=avg_latency,
            total_cost_usd=round(len(ds.test_cases) * 0.0001, 4),
            results=results,
            executed_at=datetime.now(timezone.utc),
        )

        return await self.eval_repo.create_run(eval_run)

    async def list_evaluation_runs(self, limit: int = 50) -> List[EvalRun]:
        return await self.eval_repo.list_runs(limit=limit)

