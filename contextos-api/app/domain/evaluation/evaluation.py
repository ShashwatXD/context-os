"""Domain entities for Golden Evaluation Datasets and Benchmark Runs."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvalTestCase(BaseModel):
    id: str
    query: str
    expected_entity_ids: List[str] = Field(default_factory=list)
    expected_relationship_types: List[str] = Field(default_factory=list)
    expected_discrepancy_types: List[str] = Field(default_factory=list)
    must_require_approval: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvalDataset(BaseModel):
    id: str
    name: str
    version: str
    description: str
    test_cases: List[EvalTestCase] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvalResult(BaseModel):
    test_case_id: str
    recall_at_k: float = 0.0
    entity_resolution_accuracy: float = 0.0
    context_relevance: float = 0.0
    policy_compliant: bool = True
    latency_ms: float = 0.0
    success: bool = True
    error_details: Optional[str] = None


class EvalRun(BaseModel):
    id: str
    dataset_id: str
    dataset_version: str
    model_version: str
    overall_recall_at_k: float = 0.0
    overall_entity_resolution_accuracy: float = 0.0
    overall_context_relevance: float = 0.0
    policy_compliance_rate: float = 1.0
    average_latency_ms: float = 0.0
    total_cost_usd: float = 0.0
    results: List[EvalResult] = Field(default_factory=list)
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

