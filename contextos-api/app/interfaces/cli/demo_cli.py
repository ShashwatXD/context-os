"""ContextOS Demo CLI: Deterministic Seeding and End-to-End Demonstration Scenario."""

import asyncio
import sys
from datetime import datetime, timezone
from app.infrastructure.database.session import async_session_factory, init_db, reset_db
from app.domain.entities.source import Source, SourceType
from app.domain.entities.asset import Asset, AssetType, CertificationStatus, ColumnMetadata
from app.domain.relationships.relationship import Relationship, RelationshipType
from app.domain.entities.provenance import ProvenanceRecord
from app.domain.agents.agent import Agent, RunStatus
from app.domain.governance.approval import ApprovalStatus
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.provenance_repo import ProvenanceRepository
from app.infrastructure.repositories.trace_repo import TraceRepository
from app.infrastructure.repositories.approval_repo import ApprovalRepository
from app.application.ingestion.ingestion_service import IngestionService
from app.application.entity_resolution.resolver import EntityResolutionService
from app.application.context_retrieval.retrieval_service import ContextRetrievalService
from app.application.agent_execution.runner import AgentRunner
from app.application.approvals.approval_service import ApprovalService


async def seed_demo():
    print("==================================================================")
    print("  ContextOS — Seeding Synthetic Enterprise: Acme Analytics")
    print("==================================================================")
    await reset_db()

    async with async_session_factory() as session:
        source_repo = SourceRepository(session)
        asset_repo = AssetRepository(session)
        rel_repo = RelationshipRepository(session)
        prov_repo = ProvenanceRepository(session)
        trace_repo = TraceRepository(session)

        # 1. Register Data Sources
        print("-> [1/5] Registering enterprise sources...")
        src_dw = Source(
            id="src_acme_postgres",
            name="Acme Analytics PostgreSQL Warehouse",
            source_type=SourceType.POSTGRESQL,
            connection_config={
                "tables": [
                    {
                        "schema": "raw",
                        "table": "stripe_charges",
                        "description": "Raw billing charge events directly from Stripe webhook stream",
                        "owner": "Data Platform Team",
                        "columns": [
                            {"name": "charge_id", "data_type": "varchar", "is_primary_key": True},
                            {"name": "customer_id", "data_type": "varchar"},
                            {"name": "amount_cents", "data_type": "bigint"},
                            {"name": "currency", "data_type": "varchar"},
                            {"name": "status", "data_type": "varchar"},
                        ],
                    },
                    {
                        "schema": "analytics",
                        "table": "dim_customers",
                        "description": "Core dimension table containing verified customer accounts",
                        "owner": "Revenue Ops",
                        "columns": [
                            {"name": "customer_id", "data_type": "varchar", "is_primary_key": True},
                            {"name": "company_name", "data_type": "varchar"},
                            {"name": "plan_tier", "data_type": "varchar"},
                        ],
                    },
                    {
                        "schema": "analytics",
                        "table": "fct_subscriptions",
                        "description": "Subscription contracts and active billing periods",
                        "owner": "Finance Core Team",
                        "columns": [
                            {"name": "subscription_id", "data_type": "varchar", "is_primary_key": True},
                            {"name": "customer_id", "data_type": "varchar"},
                            {"name": "mrr_amount", "data_type": "numeric"},
                        ],
                    },
                ]
            },
        )
        await source_repo.create(src_dw)

        src_dbt = Source(
            id="src_acme_dbt",
            name="Acme dbt Transformation Repo",
            source_type=SourceType.DBT,
            connection_config={
                "models": [
                    {
                        "unique_id": "model.acme.stg_stripe_charges",
                        "name": "stg_stripe_charges",
                        "description": "Staging layer normalizing Stripe charge events and refund statuses",
                        "owner": "Data Platform Team",
                        "upstream_sources": ["raw.stripe_charges"],
                        "columns": [
                            {"name": "charge_id", "data_type": "varchar"},
                            {"name": "amount_usd", "data_type": "numeric"},
                        ],
                    },
                    {
                        "unique_id": "model.acme.fct_monthly_revenue",
                        "name": "fct_monthly_revenue",
                        "description": "Certified company Monthly Recurring Revenue (MRR) transformation model deducting refunds and chargebacks",
                        "owner": "Finance Core Team",
                        "upstream_sources": ["stg_stripe_charges", "analytics.fct_subscriptions"],
                        "columns": [
                            {"name": "revenue_month", "data_type": "date"},
                            {"name": "gross_revenue", "data_type": "numeric"},
                            {"name": "net_revenue", "data_type": "numeric"},
                            {"name": "refunds_amount", "data_type": "numeric"},
                        ],
                    },
                ]
            },
        )
        await source_repo.create(src_dbt)

        src_notion = Source(
            id="src_acme_notion",
            name="Acme Finance Knowledge Base (Notion)",
            source_type=SourceType.NOTION,
            connection_config={
                "documents": [
                    {
                        "doc_id": "notion_finance_policy_mrr",
                        "title": "Monthly Recurring Revenue (MRR) - Official Finance Policy",
                        "owner": "Finance Core Team",
                        "asset_type": AssetType.METRIC,
                        "content": (
                            "Section 4.1: Monthly Recurring Revenue (MRR) is defined strictly as normalized "
                            "subscription revenue recognized within a calendar month. It EXCLUDES one-time setup fees "
                            "and MUST deduct processed churn, mid-month downgrades, and chargebacks."
                        ),
                        "certification_status": CertificationStatus.CERTIFIED,
                    },
                    {
                        "doc_id": "notion_sales_commission_policy",
                        "title": "Monthly Billed Revenue (Sales Definition)",
                        "owner": "Sales Operations",
                        "asset_type": AssetType.DOCUMENTATION,
                        "content": (
                            "Sales compensation evaluates gross billed invoices issued in the month, "
                            "regardless of refund status or multi-month advance collection periods."
                        ),
                        "certification_status": CertificationStatus.DISPUTED,
                    },
                ]
            },
        )
        await source_repo.create(src_notion)

        src_slack = Source(
            id="src_acme_slack",
            name="Acme Slack Workspace",
            source_type=SourceType.SLACK,
            freshness_threshold_seconds=900,
            auth_type="OAUTH2",
            oauth_scopes=["channels:read", "channels:history"],
        )
        await source_repo.create(src_slack)

        src_github = Source(
            id="src_acme_github",
            name="Acme GitHub Repositories",
            source_type=SourceType.GITHUB,
            freshness_threshold_seconds=1800,
            auth_type="OAUTH2",
            oauth_scopes=["repo", "pull_requests:read"],
        )
        await source_repo.create(src_github)

        # 2. Run Ingestion Services
        print("-> [2/5] Ingesting metadata and extracting cryptographic provenance...")
        ingestion = IngestionService(session)
        await ingestion.sync_source(src_dw.id)
        await ingestion.sync_source(src_dbt.id)
        await ingestion.sync_source(src_notion.id)
        await ingestion.sync_source(src_slack.id)
        await ingestion.sync_source(src_github.id)

        # 3. Add Tableau Dashboard consuming raw data (the source of the discrepancy)
        dash_id = "ast_tableau_exec_revenue"
        prov_dash = ProvenanceRecord(
            id="prov_tableau_01",
            entity_id=dash_id,
            entity_type="ASSET",
            source_id="src_tableau",
            extraction_method="TABLEAU_SERVER_METADATA_API",
            source_hash="tableau_workbook_hash_9988",
            raw_evidence={"workbook": "Executive Revenue Summary", "sql": "SELECT SUM(amount_cents) FROM raw.stripe_charges"},
        )
        await prov_repo.create(prov_dash)

        dash_asset = Asset(
            id=dash_id,
            source_id=src_dw.id,
            external_id="tableau.executive_revenue",
            name="Revenue Monthly Dashboard",
            qualified_name="tableau.dashboards.executive_revenue",
            asset_type=AssetType.DASHBOARD,
            description="Executive leadership dashboard querying raw stripe charges directly without refund deduction.",
            certification_status=CertificationStatus.DISPUTED,
            owner_name="Sales Operations",
            provenance_id=prov_dash.id,
        )
        await asset_repo.upsert(dash_asset)

        # Add Lineage edge: Raw Stripe Charges -> Tableau Dashboard
        raw_stripe = await asset_repo.get_by_source_and_external_id(src_dw.id, "raw.stripe_charges")
        if raw_stripe:
            await rel_repo.create(
                Relationship(
                    id="rel_stripe_to_tableau",
                    source_asset_id=raw_stripe.id,
                    target_asset_id=dash_asset.id,
                    relationship_type=RelationshipType.CONSUMES,
                    confidence=1.0,
                    properties={"query_direct": True},
                )
            )

        # 4. Run Entity Resolution Pipeline
        print("-> [3/5] Running Multi-Stage Entity Resolution...")
        res_service = EntityResolutionService(session)
        summary = await res_service.resolve_all_sources()
        print(f"       Auto-linked high-confidence edges: {summary['auto_linked_count']}")
        print(f"       Gated suggestions pending review: {summary['suggestions_pending_review']}")

        # 5. Register AI Agents
        print("-> [4/5] Registering enterprise agents...")
        agent = Agent(
            id="agent_context_investigator",
            name="ContextOS Root Cause Analyst",
            version="1.2.0",
            role="Traces enterprise lineage discrepancies and validates definitions",
            system_prompt=(
                "You are an enterprise ContextOS analyst. Identify metric definitions across systems, "
                "trace dbt and dashboard lineage, report conflicting evidence, and request approval "
                "before proposing metric redefinitions."
            ),
            allowed_tools=[
                "search_assets",
                "get_asset_details",
                "get_lineage",
                "search_context",
                "get_business_definition",
                "get_asset_owner",
                "request_metric_correction",
            ],
        )
        await trace_repo.register_agent(agent)

        await session.commit()
        print("-> [5/5] Seed completed successfully!")
        print("==================================================================")


async def run_scenario():
    print("==================================================================")
    print("  ContextOS — End-to-End Demonstration Scenario")
    print("  User Query: 'Why does our monthly revenue dashboard show a different number from the finance report?'")
    print("==================================================================")

    async with async_session_factory() as session:
        retrieval = ContextRetrievalService(session)
        runner = AgentRunner(session)
        approvals = ApprovalService(session)

        # Step 1: Hybrid Retrieval
        print("\n[Step 1] Hybrid Context Retrieval & Traceable Assembly...")
        query = "Why does our monthly revenue dashboard show a different number from the finance report?"
        ctx_response = await retrieval.query_context(query=query, top_k=5, include_lineage_depth=3)

        print(f"   -> Trace ID: {ctx_response.trace_id}")
        print(f"   -> Discovered {len(ctx_response.matched_entities)} grounded entities:")
        for e in ctx_response.matched_entities:
            print(f"      * [{e.asset_type}] '{e.name}' (Status: {e.certification_status}) — Owner: {e.owner_name}")
            if e.provenance:
                print(f"        Evidence: {e.provenance['extraction_method']} (Hash: {e.provenance['source_hash']})")

        # Step 2: Lineage Traversal
        print("\n[Step 2] Multi-Hop Dependency & Lineage Graph Traversal...")
        print(f"   -> Graph Nodes: {len(ctx_response.lineage_subgraph['nodes'])}")
        print(f"   -> Graph Edges: {len(ctx_response.lineage_subgraph['edges'])}")
        for edge in ctx_response.lineage_subgraph["edges"]:
            print(f"      * Edge: {edge['source']} --[{edge.get('type') or edge.get('relationship_type')}]--> {edge['target']}")

        # Step 3: Discrepancy & Conflict Detection
        print("\n[Step 3] Definition Conflict Detection...")
        if ctx_response.discrepancies:
            for d in ctx_response.discrepancies:
                print(f"   ! [WARNING] Discrepancy Found: {d.discrepancy_type}")
                print(f"     Description: {d.description}")
                print(f"     Confidence: {d.confidence}")
        else:
            print("   No discrepancies detected.")

        # Step 4: Agent Execution with Approval Gate
        print("\n[Step 4] Agent Execution & Governance Approval Gate...")
        run = await runner.execute_task(
            agent_id="agent_context_investigator",
            user_prompt=query,
            agent_permissions=[
                "search_assets",
                "get_asset_details",
                "get_lineage",
                "search_context",
                "get_business_definition",
                "get_asset_owner",
                "request_metric_correction",
            ],
            tool_sequence=[
                {
                    "tool": "request_metric_correction",
                    "arguments": {
                        "asset_id": "ast_tableau_exec_revenue",
                        "proposed_definition": "Redirect dashboard to query dbt fct_monthly_revenue (deducting refunds)",
                        "reason": "Eliminates $42,500 discrepancy between Sales Tableau and Finance official report",
                        "idempotency_key": "acme_correction_run_01",
                    },
                }
            ],
        )

        print(f"   -> Agent Run ID: {run.id}")
        print(f"   -> Status: {run.status.value}")
        print(f"   -> Latency: {run.latency_ms} ms | Tokens: {run.total_tokens} | Cost: ${run.estimated_cost_usd}")
        print(f"   -> Spans Generated: {len(run.spans)}")
        for sp in run.spans:
            print(f"      - Span [{sp.span_type.value}]: {sp.name} ({sp.latency_ms} ms) -> {sp.status}")

        # Step 5: Human Review & Certification
        print("\n[Step 5] Human-in-the-Loop Review & Policy Certification...")
        pending = await approvals.list_pending()
        print(f"   -> Pending Approval Requests in Queue: {len(pending)}")
        if pending:
            item = pending[0]
            print(f"   -> Reviewing Request ID: {item['request_id']} for Asset '{item['asset_name']}'")
            print(f"   -> Proposed Action: {item['action_type']}")
            decision = await approvals.review_request(
                request_id=item["request_id"],
                decision=ApprovalStatus.APPROVED,
                reviewer_id="user:sarah_head_of_finance",
                decision_notes="Approved: confirmed Tableau was querying raw unadjusted billed charges.",
            )
            print(f"   -> Decision: {decision['status']} by {decision['reviewer_id']}")
            print(f"   -> Applied to Asset: {decision['applied_to_asset']}")

        await session.commit()
        print("\n==================================================================")
        print("  ContextOS Demonstration Completed with Verifiable Traceability!")
        print("==================================================================")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.interfaces.cli.demo_cli [seed|run]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "seed":
        asyncio.run(seed_demo())
    elif cmd == "run":
        asyncio.run(run_scenario())
    else:
        print(f"Unknown command: '{cmd}'. Choose 'seed' or 'run'.")


if __name__ == "__main__":
    main()

