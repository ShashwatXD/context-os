"""Integration tests for Agent Runtime, Tool Permissions, Idempotency, and MCP Server."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import PermissionDeniedError
from app.domain.entities.source import Source, SourceType
from app.domain.entities.asset import Asset, AssetType, CertificationStatus
from app.domain.agents.agent import Agent, RunStatus, SpanType
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.trace_repo import TraceRepository
from app.application.agent_execution.tool_registry import ToolRegistry
from app.application.agent_execution.runner import AgentRunner
from app.infrastructure.mcp.server import ContextOSMCPServer


@pytest.mark.asyncio
async def test_tool_permissions_and_idempotency(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)

    src = Source(id="src_dw", name="DW", source_type=SourceType.POSTGRESQL)
    await source_repo.create(src)

    asset = Asset(
        id="ast_rev_table",
        source_id=src.id,
        external_id="analytics.revenue",
        name="monthly_revenue",
        qualified_name="dw.analytics.monthly_revenue",
        asset_type=AssetType.TABLE,
        description="Core revenue metric table",
        certification_status=CertificationStatus.CERTIFIED,
        owner_name="Finance Core Team",
    )
    await asset_repo.upsert(asset)

    tool_reg = ToolRegistry(test_session)

    # 1. Permission check: agent with only 'search_assets' cannot call 'get_asset_details'
    with pytest.raises(PermissionDeniedError, match="lacks required permission: tool:get_asset_details"):
        await tool_reg.execute_tool(
            tool_name="get_asset_details",
            arguments={"asset_id": asset.id},
            caller_permissions=["search_assets"],
        )

    # 2. Execution with proper permission
    res1 = await tool_reg.execute_tool(
        tool_name="get_asset_details",
        arguments={"asset_id": asset.id},
        caller_permissions=["get_asset_details"],
    )
    assert res1["result"]["name"] == "monthly_revenue"
    assert res1["idempotent_replay"] is False

    # 3. Idempotency test: sensitive action called with identical idempotency key
    key = "idem_key_998877"
    action_args = {
        "asset_id": asset.id,
        "proposed_definition": "Updated MRR definition",
        "reason": "Align with audit standards",
        "idempotency_key": key,
    }
    # Execute first time with approval bypass for unit test
    first_run = await tool_reg.execute_tool(
        tool_name="request_metric_correction",
        arguments=action_args,
        caller_permissions=["*"],
        bypass_approval_check=True,
    )
    assert first_run["idempotent_replay"] is False

    # Second execution with exact same key must return replay
    second_run = await tool_reg.execute_tool(
        tool_name="request_metric_correction",
        arguments=action_args,
        caller_permissions=["*"],
        bypass_approval_check=True,
    )
    assert second_run["idempotent_replay"] is True
    assert second_run["result"] == first_run["result"]


@pytest.mark.asyncio
async def test_agent_runner_spans_and_approval_gate(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)
    trace_repo = TraceRepository(test_session)

    src = Source(id="src_dw", name="DW", source_type=SourceType.POSTGRESQL)
    await source_repo.create(src)
    asset = Asset(
        id="ast_rev_tbl",
        source_id=src.id,
        external_id="fct_rev",
        name="monthly_revenue",
        qualified_name="dw.fct_rev",
        asset_type=AssetType.TABLE,
    )
    await asset_repo.upsert(asset)

    agent = Agent(
        id="agent_analyst_01",
        name="Revenue Analyst Agent",
        role="Investigates discrepancies and suggests corrections",
        system_prompt="Analyze metrics and propose certified fixes.",
        allowed_tools=["search_context", "request_metric_correction"],
    )
    await trace_repo.register_agent(agent)

    runner = AgentRunner(test_session)

    # Execute task with a tool sequence containing an approval-gated tool
    run = await runner.execute_task(
        agent_id=agent.id,
        user_prompt="Why does revenue differ between dashboard and warehouse?",
        agent_permissions=agent.allowed_tools,
        tool_sequence=[
            {
                "tool": "request_metric_correction",
                "arguments": {
                    "asset_id": asset.id,
                    "proposed_definition": "Strict subscription revenue",
                    "reason": "Conflict detected",
                    "idempotency_key": "idem_123",
                },
            }
        ],
    )

    # Invariant: Run status must pause in WAITING_APPROVAL
    assert run.status == RunStatus.WAITING_APPROVAL
    assert len(run.spans) >= 3  # USER_REQUEST, CONTEXT_RETRIEVAL, APPROVAL_REQUEST

    span_types = [s.span_type for s in run.spans]
    assert SpanType.USER_REQUEST in span_types
    assert SpanType.CONTEXT_RETRIEVAL in span_types
    assert SpanType.APPROVAL_REQUEST in span_types


@pytest.mark.asyncio
async def test_mcp_server_tools_and_execution(test_session: AsyncSession):
    source_repo = SourceRepository(test_session)
    asset_repo = AssetRepository(test_session)

    src = Source(id="src_dw", name="DW", source_type=SourceType.POSTGRESQL)
    await source_repo.create(src)
    asset = Asset(
        id="ast_glossary_mrr",
        source_id=src.id,
        external_id="glossary.mrr",
        name="monthly_revenue",
        qualified_name="notion.glossary.mrr",
        asset_type=AssetType.METRIC,
        description="Official finance definition of MRR",
        certification_status=CertificationStatus.CERTIFIED,
        owner_name="Finance Core Team",
    )
    await asset_repo.upsert(asset)

    mcp_server = ContextOSMCPServer(test_session)

    # 1. Verify capability and tools list
    caps = mcp_server.get_server_capabilities()
    assert caps["protocol_version"] == "2024-11-05"

    tools = mcp_server.list_tools()
    tool_names = [t["name"] for t in tools]
    assert "search_assets" in tool_names
    assert "get_asset_details" in tool_names
    assert "get_lineage" in tool_names
    assert "get_business_definition" in tool_names
    assert "get_asset_owner" in tool_names

    # 2. Invoke 'get_business_definition' via MCP
    mcp_response = await mcp_server.handle_call_tool(
        tool_name="get_business_definition",
        arguments={"term": "monthly_revenue"},
    )
    assert mcp_response["isError"] is False
    assert "Official finance definition of MRR" in mcp_response["content"][0]["text"]

