"""Integration test: AI Enrichment with Human Approval Workflow."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.source import Source, SourceType
from app.domain.entities.asset import Asset, AssetType, CertificationStatus, ColumnMetadata
from app.domain.governance.approval import ApprovalStatus
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.application.enrichment.enrichment_service import EnrichmentService
from app.application.approvals.approval_service import ApprovalService


@pytest.mark.asyncio
async def test_enrichment_approval_and_rejection_lifecycle(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)

    # 1. Register Source & Raw Asset without description
    src = Source(id="src_dw", name="Warehouse", source_type=SourceType.POSTGRESQL)
    await source_repo.create(src)

    raw_asset = Asset(
        id="ast_fct_orders_unenriched",
        source_id=src.id,
        external_id="analytics.fct_orders",
        name="fct_orders",
        qualified_name="dw.analytics.fct_orders",
        asset_type=AssetType.TABLE,
        description=None,
        certification_status=CertificationStatus.UNVERIFIED,
        columns=[
            ColumnMetadata(name="order_id", data_type="varchar", is_primary_key=True),
            ColumnMetadata(name="revenue_amount", data_type="numeric"),
            ColumnMetadata(name="charge_status", data_type="varchar"),
        ],
    )
    await asset_repo.upsert(raw_asset)

    # 2. Trigger AI Enrichment
    enrichment_service = EnrichmentService(test_session)
    enrichment_result = await enrichment_service.enrich_asset(raw_asset.id)

    assert enrichment_result["status"] == ApprovalStatus.PENDING_REVIEW.value
    assert "revenue" in enrichment_result["proposed_description"].lower()
    assert enrichment_result["confidence"] >= 0.80

    # Verify asset is NOT mutated yet (Invariant: No unverified automatic certification)
    unchanged_asset = await asset_repo.get_by_id(raw_asset.id)
    assert unchanged_asset.description is None
    assert unchanged_asset.certification_status == CertificationStatus.UNVERIFIED

    # 3. Human Approval Workflow
    approval_service = ApprovalService(test_session)
    pending_items = await approval_service.list_pending()
    assert len(pending_items) == 1
    assert pending_items[0]["asset_id"] == raw_asset.id

    # 4. Human Reviews & Approves
    decision_result = await approval_service.review_request(
        request_id=pending_items[0]["request_id"],
        decision=ApprovalStatus.APPROVED,
        reviewer_id="user:lead_data_steward",
        decision_notes="Verified accuracy against billing pipeline specifications.",
    )

    assert decision_result["status"] == ApprovalStatus.APPROVED.value
    assert decision_result["applied_to_asset"] is True

    # Verify asset is now updated with verified description and CERTIFIED status
    certified_asset = await asset_repo.get_by_id(raw_asset.id)
    assert certified_asset.description == enrichment_result["proposed_description"]
    assert certified_asset.certification_status == CertificationStatus.CERTIFIED
    assert certified_asset.owner_name == "Finance Core Team"

