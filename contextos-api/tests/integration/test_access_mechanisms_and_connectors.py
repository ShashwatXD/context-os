"""Integration tests for Three Data Access Mechanisms, Slack/GitHub Connectors, Checkpoints, DLQ, and ACLs."""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.source import Source, SourceType, SyncStatus
from app.domain.entities.asset import Asset, AssetType, CertificationStatus, SearchChunk
from app.domain.entities.provenance import ProvenanceRecord
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.provenance_repo import ProvenanceRepository
from app.application.ingestion.ingestion_service import IngestionService
from app.application.context_retrieval.retrieval_service import ContextRetrievalService
from app.infrastructure.connectors.slack_connector import SlackConnector
from app.infrastructure.connectors.github_connector import GithubConnector
from app.infrastructure.mcp.server import ContextOSMCPServer


@pytest.mark.asyncio
async def test_slack_connector_thread_chunking_and_storage_segregation(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)

    src = Source(
        id="src_slack_acme",
        name="Acme Slack Workspace",
        source_type=SourceType.SLACK,
        freshness_threshold_seconds=600,
        auth_type="OAUTH2",
        oauth_scopes=["channels:read", "channels:history"],
    )
    await source_repo.create(src)

    ingestion_service = IngestionService(test_session)
    sync = await ingestion_service.sync_source(src.id)
    assert sync.status == SyncStatus.COMPLETED

    # 1. Verify Storage Layer 2: Asset (Slack Channel)
    channels = await asset_repo.search_assets(asset_type="CHANNEL")
    assert len(channels) >= 1
    finance_channel = next((c for c in channels if "finance-ops" in c.name), None)
    assert finance_channel is not None
    assert "channel:finance-ops" in finance_channel.acl_tags

    # 2. Verify Storage Layer 3: Search Chunks (Thread-Level Aggregation)
    chunks = await asset_repo.get_search_chunks_by_asset(finance_channel.id)
    assert len(chunks) >= 1
    thread_chunk = chunks[0]
    assert thread_chunk.chunk_type == "THREAD_SUMMARY"
    assert "Channel: #finance-ops" in thread_chunk.chunk_text
    assert "Tableau queries raw.stripe_charges directly" in thread_chunk.chunk_text
    assert "https://acme.slack.com/archives/" in thread_chunk.chunk_text
    assert thread_chunk.embedding is not None
    assert len(thread_chunk.embedding) == 64


@pytest.mark.asyncio
async def test_github_connector_pr_and_diff_chunking(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)

    src = Source(
        id="src_gh_acme",
        name="Acme GitHub Org",
        source_type=SourceType.GITHUB,
        auth_type="OAUTH2",
        oauth_scopes=["repo", "pull_requests:read"],
    )
    await source_repo.create(src)

    ingestion_service = IngestionService(test_session)
    sync = await ingestion_service.sync_source(src.id)
    assert sync.status == SyncStatus.COMPLETED

    # 1. Verify PR Asset
    prs = await asset_repo.search_assets(asset_type="PULL_REQUEST")
    assert len(prs) >= 1
    pr = prs[0]
    assert "deduct stripe chargebacks" in pr.name.lower()

    # 2. Verify Content-Aware Search Chunks (PR Summary + Selected Diff)
    chunks = await asset_repo.get_search_chunks_by_asset(pr.id)
    chunk_types = [c.chunk_type for c in chunks]
    assert "PR_SUMMARY" in chunk_types
    assert "PR_DIFF" in chunk_types

    diff_chunk = next(c for c in chunks if c.chunk_type == "PR_DIFF")
    assert "Unified Code Diff" in diff_chunk.chunk_text
    assert "+    sum(case when is_refund then refund_amount else 0 end)" in diff_chunk.chunk_text


@pytest.mark.asyncio
async def test_checkpoint_cursor_and_dlq_handling(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)

    src = Source(
        id="src_slack_chk",
        name="Slack Checkpoint Test",
        source_type=SourceType.SLACK,
    )
    await source_repo.create(src)

    ingestion = IngestionService(test_session)

    # Initial sync commits checkpoint
    await ingestion.sync_source(src.id)
    chk = await source_repo.get_checkpoint(src.id)
    assert chk is not None
    assert chk.cursor_value == "cursor_slack_page_2"

    # Dead-Letter Queue (DLQ) verification
    dlqs = await source_repo.list_dead_letters(src.id)
    # Healthy run has 0 DLQ entries
    assert len(dlqs) == 0


@pytest.mark.asyncio
async def test_deletion_propagation_pruning(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)

    src = Source(id="src_temp", name="Temp", source_type=SourceType.SLACK)
    await source_repo.create(src)

    asset = Asset(
        id="ast_to_delete",
        source_id=src.id,
        external_id="temp.chan",
        name="temp_channel",
        qualified_name="slack.temp",
        asset_type=AssetType.CHANNEL,
    )
    await asset_repo.upsert(asset)

    # Add search chunk
    chunk = SearchChunk(
        id="chk_temp",
        asset_id=asset.id,
        chunk_type="THREAD_SUMMARY",
        chunk_text="Conversation to be deleted",
        version_hash="hash123",
    )
    await asset_repo.save_search_chunks([chunk])

    # Verify chunk exists
    initial_chunks = await asset_repo.get_search_chunks_by_asset(asset.id)
    assert len(initial_chunks) == 1

    # Deletion Propagation: Expunges all search chunks & embeddings
    pruned_count = await asset_repo.delete_search_chunks_by_asset(asset.id)
    assert pruned_count == 1

    remaining_chunks = await asset_repo.get_search_chunks_by_asset(asset.id)
    assert len(remaining_chunks) == 0


@pytest.mark.asyncio
async def test_mechanism_c_live_source_fallback(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)

    # Source synced 2 hours ago with 10-minute freshness threshold -> STALE!
    stale_timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
    src = Source(
        id="src_slack_stale",
        name="Stale Slack",
        source_type=SourceType.SLACK,
        freshness_threshold_seconds=600,  # 10 mins
        last_sync_at=stale_timestamp,
    )
    await source_repo.create(src)

    asset = Asset(
        id="ast_slack_stale_chan",
        source_id=src.id,
        external_id="C01_FINANCE",
        name="#finance-ops",
        qualified_name="slack.src_slack_stale.finance-ops",
        asset_type=AssetType.CHANNEL,
        description="Cached channel description from 2 hours ago",
    )
    await asset_repo.upsert(asset)

    retrieval = ContextRetrievalService(test_session)

    # Mechanism C triggers live fetch because age > 600 seconds
    response = await retrieval.query_context(query="finance revenue discrepancy", force_fresh=True)
    assert len(response.matched_entities) >= 1
    matched = next((e for e in response.matched_entities if e.asset_id == asset.id), None)
    assert matched is not None
    # Live fetch succeeded and verified freshness
    assert matched.freshness_status == "LIVE_VERIFIED"


@pytest.mark.asyncio
async def test_acl_aware_retrieval_filtering(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)

    src = Source(id="src_dw", name="DW", source_type=SourceType.POSTGRESQL)
    await source_repo.create(src)

    # Private finance table
    secret_asset = Asset(
        id="ast_exec_payroll",
        source_id=src.id,
        external_id="hr.payroll",
        name="executive_payroll_compensation",
        qualified_name="dw.hr.payroll",
        asset_type=AssetType.TABLE,
        description="Restricted executive compensation records",
        acl_tags=["role:c-suite", "team:hr-exec"],
    )
    # Public general table
    public_asset = Asset(
        id="ast_general_catalog",
        source_id=src.id,
        external_id="public.products",
        name="product_catalog",
        qualified_name="dw.public.products",
        asset_type=AssetType.TABLE,
        description="Public product pricing catalog",
        acl_tags=[],  # Public
    )
    await asset_repo.upsert(secret_asset)
    await asset_repo.upsert(public_asset)

    retrieval = ContextRetrievalService(test_session)

    # Caller A: lacks C-suite permission -> Can only see public product catalog
    res_restricted = await retrieval.query_context(
        query="compensation product",
        caller_acl_tags=["team:engineering"],
        minimum_confidence=0.30,
    )
    retrieved_ids_a = [e.asset_id for e in res_restricted.matched_entities]
    assert secret_asset.id not in retrieved_ids_a
    assert public_asset.id in retrieved_ids_a

    # Caller B: has C-suite permission -> Can see both
    res_authorized = await retrieval.query_context(
        query="compensation product",
        caller_acl_tags=["role:c-suite"],
        minimum_confidence=0.30,
    )
    retrieved_ids_b = [e.asset_id for e in res_authorized.matched_entities]
    assert secret_asset.id in retrieved_ids_b


@pytest.mark.asyncio
async def test_mcp_retrieve_source_evidence(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    prov_repo = ProvenanceRepository(test_session)

    src = Source(id="src_test", name="Test", source_type=SourceType.POSTGRESQL)
    await source_repo.create(src)

    prov = ProvenanceRecord(
        id="prov_audit_999",
        entity_id="ast_test",
        entity_type="ASSET",
        source_id=src.id,
        extraction_method="DBT_MANIFEST_PARSER",
        source_hash="sha256_audit_hash_value_12345",
        raw_evidence={"file": "models/marts/fct_revenue.sql", "commit": "git_sha_abc"},
    )
    await prov_repo.create(prov)

    mcp_server = ContextOSMCPServer(test_session)

    # Call new MCP tool: retrieve_source_evidence
    res = await mcp_server.handle_call_tool(
        tool_name="retrieve_source_evidence",
        arguments={"provenance_id": prov.id},
    )
    assert res["isError"] is False
    assert "sha256_audit_hash_value_12345" in res["content"][0]["text"]
    assert "models/marts/fct_revenue.sql" in res["content"][0]["text"]
