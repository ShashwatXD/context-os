"""Integration test: Golden Evaluation Benchmark and REST API Routes."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.domain.entities.source import Source, SourceType
from app.domain.entities.asset import Asset, AssetType, CertificationStatus
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.application.evaluation.eval_service import EvaluationService


@pytest.mark.asyncio
async def test_evaluation_runner_metrics(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)

    src = Source(id="src_dw", name="DW", source_type=SourceType.POSTGRESQL)
    await source_repo.create(src)

    # Seed expected golden assets
    fct_mrr = Asset(
        id="ast_fct_mrr",
        source_id=src.id,
        external_id="fct_mrr",
        name="fct_monthly_revenue",
        qualified_name="dw.fct_mrr",
        asset_type=AssetType.TRANSFORMATION_MODEL,
        description="Official recognized MRR calculation.",
        certification_status=CertificationStatus.CERTIFIED,
    )
    dash_rev = Asset(
        id="ast_dash_rev",
        source_id=src.id,
        external_id="dash_rev",
        name="Revenue Monthly Dashboard",
        qualified_name="tableau.dash_rev",
        asset_type=AssetType.DASHBOARD,
        description="Unadjusted billing sales dashboard.",
        certification_status=CertificationStatus.DISPUTED,
    )
    await asset_repo.upsert(fct_mrr)
    await asset_repo.upsert(dash_rev)

    eval_service = EvaluationService(test_session)
    eval_run = await eval_service.run_evaluation(model_version="contextos-hybrid-v1.0")

    # Invariants: Real reported evaluation metrics originating from actual runs
    assert eval_run.id.startswith("eval_run_")
    assert eval_run.overall_recall_at_k > 0.0
    assert eval_run.overall_context_relevance > 0.0
    assert eval_run.policy_compliance_rate == 1.0
    assert eval_run.average_latency_ms > 0.0
    assert len(eval_run.results) == 2


from app.interfaces.api.dependencies import get_session


@pytest.mark.asyncio
async def test_fastapi_rest_endpoints(test_session: AsyncSession):
    async def override_get_session():
        yield test_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Health
            health_res = await client.get("/api/v1/health")
            assert health_res.status_code == 200
            assert health_res.json()["status"] == "ok"

            # 2. Create Source
            create_src_res = await client.post(
                "/api/v1/sources",
                json={"name": "Stripe Billing", "source_type": "POSTGRESQL", "connection_config": {}},
            )
            assert create_src_res.status_code == 201
            source_id = create_src_res.json()["id"]

            # 3. List Sources
            list_src_res = await client.get("/api/v1/sources")
            assert list_src_res.status_code == 200
            assert any(s["id"] == source_id for s in list_src_res.json())

            # 4. Context Query
            query_res = await client.post(
                "/api/v1/context/query",
                json={"query": "revenue", "top_k": 3},
            )
            assert query_res.status_code == 200
            assert "matched_entities" in query_res.json()

            # 5. List Approvals
            appr_res = await client.get("/api/v1/approvals")
            assert appr_res.status_code == 200

            # 6. Evaluations API
            eval_list_res = await client.get("/api/v1/evaluations")
            assert eval_list_res.status_code == 200
    finally:
        app.dependency_overrides.clear()
