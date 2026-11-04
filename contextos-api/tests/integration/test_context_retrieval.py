"""Integration test for Hybrid Retrieval and Context Assembly."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.source import Source, SourceType
from app.domain.entities.asset import Asset, AssetType, CertificationStatus
from app.domain.relationships.relationship import Relationship, RelationshipType
from app.domain.entities.provenance import ProvenanceRecord
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.provenance_repo import ProvenanceRepository
from app.application.context_retrieval.retrieval_service import ContextRetrievalService


@pytest.mark.asyncio
async def test_traceable_context_retrieval_and_discrepancy(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)
    rel_repo = RelationshipRepository(test_session)
    prov_repo = ProvenanceRepository(test_session)

    # 1. Setup Source
    src = Source(id="src_dw", name="DW", source_type=SourceType.POSTGRESQL)
    await source_repo.create(src)

    # 2. Setup Provenance
    prov = ProvenanceRecord(
        id="prov_test_01",
        entity_id="ast_fct_mrr",
        entity_type="ASSET",
        source_id=src.id,
        extraction_method="DBT_PARSER",
        source_hash="abcd1234efgh5678",
        raw_evidence={"model": "fct_mrr", "sql_logic": "sum(net_amount)"},
    )
    await prov_repo.create(prov)

    # 3. Setup Assets
    table_asset = Asset(
        id="ast_fct_mrr",
        source_id=src.id,
        external_id="analytics.fct_mrr",
        name="fct_monthly_revenue",
        qualified_name="dbt.analytics.fct_monthly_revenue",
        asset_type=AssetType.TRANSFORMATION_MODEL,
        description="Recognized subscription revenue net of refunds and processor chargebacks.",
        certification_status=CertificationStatus.CERTIFIED,
        owner_name="Finance Core Team",
        provenance_id=prov.id,
    )
    dashboard_asset = Asset(
        id="ast_dash_rev",
        source_id=src.id,
        external_id="tableau.rev_dash",
        name="Revenue Monthly Dashboard",
        qualified_name="tableau.dashboards.rev_dash",
        asset_type=AssetType.DASHBOARD,
        description="Executive sales dashboard querying billed payments without refund churn deduction.",
        certification_status=CertificationStatus.DISPUTED,
        owner_name="Sales Ops",
    )
    await asset_repo.upsert(table_asset)
    await asset_repo.upsert(dashboard_asset)

    # 4. Setup Lineage Relationship
    await rel_repo.create(
        Relationship(
            id="rel_01",
            source_asset_id=table_asset.id,
            target_asset_id=dashboard_asset.id,
            relationship_type=RelationshipType.CONSUMES,
            confidence=1.0,
        )
    )

    # 5. Execute Context Retrieval
    retrieval_service = ContextRetrievalService(test_session)
    response = await retrieval_service.query_context(
        query="monthly revenue dashboard difference",
        top_k=5,
        include_lineage_depth=2,
    )

    assert len(response.matched_entities) >= 1
    # Check that provenance is attached to matched entity
    matched_fct = next((e for e in response.matched_entities if e.asset_id == table_asset.id), None)
    assert matched_fct is not None
    assert matched_fct.provenance is not None
    assert matched_fct.provenance["source_id"] == src.id

    # Check lineage subgraph contains connected nodes & edges
    assert len(response.lineage_subgraph["nodes"]) >= 2
    assert len(response.lineage_subgraph["edges"]) >= 1

    # Check discrepancy detection caught the DISPUTED dashboard
    assert len(response.discrepancies) >= 1
    assert response.discrepancies[0].discrepancy_type == "DISPUTED_DEFINITION"
    assert response.discrepancies[0].evidence_asset_ids == [dashboard_asset.id]

