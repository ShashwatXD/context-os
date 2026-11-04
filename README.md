# ContextOS — Enterprise Context Infrastructure Platform for AI Agents

ContextOS connects information from disparate enterprise systems (PostgreSQL data warehouses, Snowflake DDL, dbt transformation pipelines, Tableau dashboards, and Notion documentation), discovers entities and relationships, builds a structured and traceable context graph, enriches that context using AI, and exposes trusted, verifiable context to external AI agents through REST APIs and the **Model Context Protocol (MCP)**.

---

## Repository Architecture

ContextOS is partitioned into two completely independent, decoupled repositories:

```
context-os/
│
├── contextos-api/           # Repository 1: Complete Backend, Context Engine & MCP
│   ├── app/
│   │   ├── domain/          # Pure Domain models (zero external framework imports)
│   │   ├── application/     # Ingestion, Entity Resolution, Retrieval, Approvals, Eval
│   │   ├── infrastructure/  # SQLAlchemy 2.0, Connectors, Embeddings, LLM, MCP, Tracer
│   │   └── interfaces/      # FastAPI REST routes and CLI commands
│   ├── tests/               # 27 unit & integration tests
│   ├── demo/                # Synthetic enterprise dataset (Acme Analytics)
│   ├── Dockerfile
│   └── docker-compose.yml
│
└── contextos-web/           # Repository 2: Frontend Engineering Console
    ├── src/
    │   ├── app/             # Next.js 14 App Router (10 screens)
    │   ├── components/      # Atlan-inspired minimalist design system
    │   └── lib/             # Typed API client & data models
    └── package.json
```

---

## Core Engineering Capabilities

1. **Enterprise Metadata & Lineage Modeling**: Models datasets, databases, schemas, tables, columns, metrics, and dashboards with cryptographic SHA-256 evidence provenance.
2. **Multi-Stage Entity Resolution**: Identifies when different sources refer to the same business entity (e.g., Snowflake `monthly_revenue` vs Tableau `Revenue Monthly` vs Notion `monthly recurring revenue metric`). Ambiguous matches ($0.70 \le \text{confidence} < 0.90$) become reviewable suggestions in human governance queues.
3. **Traceable Hybrid Retrieval**: Combines full-text search, dense local vector embeddings, Reciprocal Rank Fusion (RRF), and recursive graph lineage traversal to return source-attributed context.
4. **Governed Agent Runtime & MCP Protocol**: Implements Model Context Protocol (MCP 2024-11-05) standard tools (`search_assets`, `get_asset_details`, `get_lineage`, `search_context`, `get_business_definition`, `get_asset_owner`) with tool permissions, idempotency keys, and human-in-the-loop review barriers for mutative actions.
5. **AI Observability & Evaluations**: Emits distributed trace spans (`USER_REQUEST`, `CONTEXT_RETRIEVAL`, `TOOL_EXECUTION`, `APPROVAL_GATE`) with token/cost tracking and reproducible golden benchmarks measuring Recall@K, relevance, and policy compliance.

---

## Quickstart & Local Execution

### 1. Backend (`contextos-api`)
```bash
cd contextos-api

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt greenlet aiosqlite

# Run the complete test suite (27 passing tests)
pytest tests -v

# Seed the Acme Analytics synthetic enterprise dataset
python -m app.cli demo seed

# Run the end-to-end Revenue Discrepancy scenario
python -m app.cli demo run

# Launch the FastAPI REST and MCP server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API Docs available at: `http://localhost:8000/docs`

### 2. Frontend (`contextos-web`)
```bash
cd contextos-web

# Install dependencies
npm install

# Start the engineering console
npm run dev
```
Console available at: `http://localhost:3000`

---

## Primary End-to-End Scenario: The Revenue Discrepancy

A user asks:
> *"Why does our monthly revenue dashboard show a different number from the finance report?"*

ContextOS executes the following traceable sequence:
1. **Discovers Relevant Entities**: Locates dbt transformation model `fct_monthly_revenue` and Tableau dashboard `Executive Revenue Summary`.
2. **Traces Multi-Hop Lineage**: Traces upstream sources from raw Stripe billing charges through staging into dbt models and downstream dashboards.
3. **Identifies Conflicting Definitions**: Detects that the Tableau dashboard queries raw unadjusted billed charges, whereas official finance policy requires deducting refunds and chargebacks (`DISPUTED_DEFINITION` detected with 0.91 confidence).
4. **Governed Correction**: Agent queues a `request_metric_correction` action with an idempotency key.
5. **Human Approval Gate**: Execution pauses in `WAITING_APPROVAL` status until a human steward reviews and approves the correction in the Governance Console.

