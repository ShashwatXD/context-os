"""Integration test: Ingest multiple enterprise sources and resolve entities."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.source import Source, SourceType, SyncStatus
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.approval_repo import ApprovalRepository
from app.infrastructure.repositories.provenance_repo import ProvenanceRepository
from app.application.ingestion.ingestion_service import IngestionService
from app.application.entity_resolution.resolver import EntityResolutionService


@pytest.mark.asyncio
async def test_multi_source_ingestion_and_resolution_pipeline(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)
    approval_repo = ApprovalRepository(test_session)
    rel_repo = RelationshipRepository(test_session)

    # 1. Register PostgreSQL warehouse source
    pg_src = Source(
        id="src_pg_01",
        name="Production Warehouse",
        source_type=SourceType.POSTGRESQL,
        connection_config={"tables": [
            {
                "schema": "analytics",
                "table": "fct_monthly_revenue",
                "description": "Warehouse monthly revenue table",
                "owner": "Data Platform",
                "columns": [{"name": "revenue_amount", "data_type": "numeric"}],
            }
        ]},
    )
    await source_repo.create(pg_src)

    # 2. Register Notion documentation source
    notion_src = Source(
        id="src_notion_01",
        name="Company Notion Glossary",
        source_type=SourceType.NOTION,
        connection_config={"documents": [
            {
                "doc_id": "doc_mrr_policy",
                "title": "monthly_revenue",
                "owner": "Finance Team",
                "content": "Official calculation guidelines for recognized monthly recurring revenue.",
            },
            {
                "doc_id": "doc_sales_comp",
                "title": "Monthly Billed Revenue",
                "owner": "Sales Ops",
                "content": "Sales booking commissions based on raw invoice counts.",
            }
        ]},
    )
    await source_repo.create(notion_src)

    # 3. Execute Ingestion for both sources
    ingestion_service = IngestionService(test_session)

    pg_sync = await ingestion_service.sync_source("src_pg_01")
    assert pg_sync.status == SyncStatus.COMPLETED
    assert pg_sync.entities_extracted == 1

    notion_sync = await ingestion_service.sync_source("src_notion_01")
    assert notion_sync.status == SyncStatus.COMPLETED
    assert notion_sync.entities_extracted == 2

    # Verify assets were persisted in catalog
    all_assets = await asset_repo.search_assets(limit=10)
    assert len(all_assets) == 3

    # 4. Run Entity Resolution Pipeline
    resolution_service = EntityResolutionService(test_session)
    res_summary = await resolution_service.resolve_all_sources()

    # 'fct_monthly_revenue' vs 'monthly_revenue' -> Canonical match (confidence 0.95 >= 0.90) -> Auto linked!
    assert res_summary["auto_linked_count"] >= 1

    # 'fct_monthly_revenue' vs 'Monthly Billed Revenue' -> Moderate confidence (0.70-0.89) -> Approval Suggestion!
    assert res_summary["suggestions_pending_review"] >= 1

    # Verify pending approvals exist in governance queue
    pending_approvals = await approval_repo.list_pending_requests()
    assert len(pending_approvals) >= 1
    assert pending_approvals[0]["action_type"] == "MERGE_OR_LINK_ENTITY"

    # Verify auto-linked relationship exists in graph
    rels = await rel_repo.list_all()
    inferred_rels = [r for r in rels if r.relationship_type.value == "INFERRED_SAME_AS"]
    assert len(inferred_rels) >= 1

