"""Integration tests for Database Persistence and Repository Layer."""

import pytest
from app.domain.entities.source import Source, SourceType, SyncRecord, SyncStatus
from app.domain.entities.asset import Asset, AssetType, CertificationStatus, ColumnMetadata
from app.domain.entities.provenance import ProvenanceRecord
from app.domain.relationships.relationship import Relationship, RelationshipType
from app.domain.governance.approval import Suggestion, SuggestionType, ApprovalRequest, ApprovalStatus
from app.domain.agents.agent import Agent, AgentRun, RunStatus, SpanType, TraceSpan
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.provenance_repo import ProvenanceRepository
from app.infrastructure.repositories.approval_repo import ApprovalRepository
from app.infrastructure.repositories.trace_repo import TraceRepository


@pytest.mark.asyncio
async def test_source_lifecycle(source_repo: SourceRepository):
    src = Source(
        id="src_pg_dw",
        name="Postgres Warehouse",
        source_type=SourceType.POSTGRESQL,
        connection_config={"host": "localhost", "database": "analytics"},
    )
    saved = await source_repo.create(src)
    assert saved.id == "src_pg_dw"

    fetched = await source_repo.get_by_id("src_pg_dw")
    assert fetched is not None
    assert fetched.name == "Postgres Warehouse"

    # Sync Record
    sync = SyncRecord(
        id="sync_001",
        source_id="src_pg_dw",
        status=SyncStatus.RUNNING,
    )
    await source_repo.create_sync_record(sync)

    sync.status = SyncStatus.COMPLETED
    sync.entities_extracted = 42
    sync.relationships_extracted = 18
    await source_repo.update_sync_record(sync)

    history = await source_repo.get_sync_history("src_pg_dw")
    assert len(history) == 1
    assert history[0].status == SyncStatus.COMPLETED
    assert history[0].entities_extracted == 42


@pytest.mark.asyncio
async def test_asset_upsert_and_search(source_repo: SourceRepository, asset_repo: AssetRepository):
    # Setup source first
    await source_repo.create(
        Source(id="src_01", name="Test Source", source_type=SourceType.POSTGRESQL)
    )

    asset = Asset(
        id="ast_fct_orders",
        source_id="src_01",
        external_id="analytics.fct_orders",
        name="fct_orders",
        qualified_name="prod.analytics.fct_orders",
        asset_type=AssetType.TABLE,
        description="Daily fact table of placed orders",
        columns=[
            ColumnMetadata(name="order_id", data_type="varchar", is_primary_key=True),
            ColumnMetadata(name="amount", data_type="numeric"),
        ],
    )
    await asset_repo.upsert(asset)

    # Search by keyword
    results = await asset_repo.search_assets(query="orders")
    assert len(results) == 1
    assert results[0].name == "fct_orders"

    # Upsert with new description
    asset.description = "Updated description with churn metrics"
    await asset_repo.upsert(asset)

    updated = await asset_repo.get_by_id("ast_fct_orders")
    assert updated.description == "Updated description with churn metrics"


@pytest.mark.asyncio
async def test_lineage_graph_traversal(
    source_repo: SourceRepository,
    asset_repo: AssetRepository,
    relationship_repo: RelationshipRepository,
):
    await source_repo.create(Source(id="src_01", name="Warehouse", source_type=SourceType.POSTGRESQL))

    # Create 3 assets in a chain: Raw Table -> dbt Model -> Dashboard
    raw_tbl = Asset(
        id="ast_raw_charges",
        source_id="src_01",
        external_id="raw.charges",
        name="charges",
        qualified_name="raw.stripe.charges",
        asset_type=AssetType.TABLE,
    )
    dbt_model = Asset(
        id="ast_fct_mrr",
        source_id="src_01",
        external_id="analytics.fct_mrr",
        name="fct_mrr",
        qualified_name="analytics.dbt.fct_mrr",
        asset_type=AssetType.TRANSFORMATION_MODEL,
    )
    tableau_dash = Asset(
        id="ast_dash_rev",
        source_id="src_01",
        external_id="tableau.exec_revenue",
        name="Executive Revenue",
        qualified_name="tableau.dashboards.exec_revenue",
        asset_type=AssetType.DASHBOARD,
    )

    await asset_repo.upsert(raw_tbl)
    await asset_repo.upsert(dbt_model)
    await asset_repo.upsert(tableau_dash)

    # Create relationships
    await relationship_repo.create(
        Relationship(
            id="rel_01",
            source_asset_id=raw_tbl.id,
            target_asset_id=dbt_model.id,
            relationship_type=RelationshipType.TRANSFORMS_TO,
            confidence=1.0,
        )
    )
    await relationship_repo.create(
        Relationship(
            id="rel_02",
            source_asset_id=dbt_model.id,
            target_asset_id=tableau_dash.id,
            relationship_type=RelationshipType.CONSUMES,
            confidence=1.0,
        )
    )

    # Traverse downstream from raw charges
    downstream = await relationship_repo.get_lineage(raw_tbl.id, depth=3, direction="downstream")
    assert len(downstream["nodes"]) == 3
    assert len(downstream["edges"]) == 2

    # Traverse upstream from dashboard
    upstream = await relationship_repo.get_lineage(tableau_dash.id, depth=3, direction="upstream")
    assert len(upstream["nodes"]) == 3
    node_ids = {n["id"] for n in upstream["nodes"]}
    assert raw_tbl.id in node_ids
    assert dbt_model.id in node_ids


@pytest.mark.asyncio
async def test_approval_decision_workflow(
    source_repo: SourceRepository,
    asset_repo: AssetRepository,
    approval_repo: ApprovalRepository,
):
    await source_repo.create(Source(id="src_01", name="Warehouse", source_type=SourceType.POSTGRESQL))
    asset = Asset(
        id="ast_tbl_01",
        source_id="src_01",
        external_id="tbl_01",
        name="revenue_summary",
        qualified_name="dw.revenue_summary",
        asset_type=AssetType.TABLE,
    )
    await asset_repo.upsert(asset)

    sug = Suggestion(
        id="sug_rev_desc",
        asset_id=asset.id,
        suggestion_type=SuggestionType.DESCRIPTION,
        proposed_value={"description": "Official company monthly recurring revenue."},
        reasoning="Inferred from linked Notion finance policy document.",
        confidence=0.89,
    )
    await approval_repo.create_suggestion(sug)

    req = ApprovalRequest(
        id="appr_req_01",
        suggestion_id=sug.id,
        action_type="UPDATE_METADATA",
        requested_by="agent:enricher",
    )
    await approval_repo.create_approval_request(req)

    pending = await approval_repo.list_pending_requests()
    assert len(pending) == 1
    assert pending[0]["request_id"] == "appr_req_01"

    # Decide approval
    decided = await approval_repo.decide_request(
        request_id="appr_req_01",
        decision=ApprovalStatus.APPROVED,
        reviewer_id="user:lead_data_architect",
        decision_notes="Verified against Q3 finance handbook.",
    )
    assert decided.status == ApprovalStatus.APPROVED
    assert decided.reviewer_id == "user:lead_data_architect"


@pytest.mark.asyncio
async def test_trace_and_span_recording(trace_repo: TraceRepository):
    agent = Agent(
        id="agt_enricher_01",
        name="Metadata Enrichment Agent",
        role="Enriches documentation and ownership",
        system_prompt="Analyze unverified tables and propose descriptions.",
        allowed_tools=["search_assets", "get_lineage"],
    )
    await trace_repo.register_agent(agent)

    run = AgentRun(
        id="run_1001",
        agent_id=agent.id,
        trigger_event="ON_INGESTION_COMPLETE",
        input_prompt="Enrich fct_orders table.",
        status=RunStatus.RUNNING,
    )
    await trace_repo.create_run(run)

    span1 = TraceSpan(
        id="sp_101",
        run_id=run.id,
        span_type=SpanType.CONTEXT_RETRIEVAL,
        name="FetchLineage",
        latency_ms=12.5,
    )
    span2 = TraceSpan(
        id="sp_102",
        run_id=run.id,
        span_type=SpanType.LLM_INVOCATION,
        name="GenerateDescription",
        latency_ms=350.2,
    )
    await trace_repo.create_span(span1)
    await trace_repo.create_span(span2)

    run.status = RunStatus.COMPLETED
    run.latency_ms = 362.7
    run.total_tokens = 412
    await trace_repo.update_run(run)

    retrieved = await trace_repo.get_run_with_spans(run.id)
    assert retrieved is not None
    assert retrieved.status == RunStatus.COMPLETED
    assert len(retrieved.spans) == 2
    assert retrieved.spans[0].name == "FetchLineage"

