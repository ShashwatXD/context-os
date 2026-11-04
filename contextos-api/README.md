# ContextOS API (`contextos-api`)

Enterprise context infrastructure platform backend for AI agents.

Connects enterprise systems of record (PostgreSQL, Snowflake, dbt, Notion/Markdown), discovers entities, builds a traceable context graph, enriches context using AI, and exposes trusted context to external AI agents through REST APIs and Model Context Protocol (MCP).

---

## Architecture Highlights

- **Clean Domain-Driven Modular Monolith**: Strict segregation between Domain, Application, Infrastructure, and Interface layers.
- **Multi-Stage Entity Resolution**: Canonical normalization, token containment, Levenshtein edit distance, and human review gating.
- **Traceable Hybrid Retrieval**: Full-text search + dense local vector embeddings + Reciprocal Rank Fusion (RRF) + multi-hop lineage traversal.
- **Governed Agent Runtime & MCP**: Tool-level permissions, idempotency key guarantees, and human-in-the-loop approval workflows (`PENDING_REVIEW` -> `APPROVED`).
- **AI Observability & Evaluations**: Distributed traces with spans (`USER_REQUEST`, `CONTEXT_RETRIEVAL`, `TOOL_EXECUTION`, `APPROVAL_GATE`) and golden benchmarks (Recall@K, accuracy, latency, cost).

---

## Quickstart & Local Execution

### 1. Requirements
- Python 3.12+
- Virtual environment (`venv`)

### 2. Setup & Installation
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt greenlet aiosqlite
```

### 3. Run Synthetic Enterprise Demo (Acme Analytics)
```bash
# Seed synthetic enterprise warehouse, dbt models, Notion docs, and dashboards
python -m app.cli demo seed

# Run the end-to-end revenue discrepancy scenario
python -m app.cli demo run
```

### 4. Run Automated Test Suite
```bash
pytest tests -v
```

### 5. Launch API Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive API docs available at: `http://localhost:8000/docs`

---

## API Summary

- `GET /api/v1/health` — Health check
- `GET /api/v1/sources` — List enterprise data sources
- `POST /api/v1/sources/{id}/sync` — Ingest metadata and extract provenance
- `GET /api/v1/assets` — Metadata catalog search & filter
- `GET /api/v1/assets/{id}/lineage` — Multi-hop dependency lineage
- `GET /api/v1/graph` — Global context graph
- `POST /api/v1/context/query` — Traceable hybrid context retrieval
- `GET /api/v1/approvals` — Governance approval queue
- `POST /api/v1/approvals/{id}/decide` — Human approval/rejection decision
- `GET /api/v1/traces/{id}` — Distributed trace span inspector
- `GET /api/v1/evaluations` — Golden evaluation runs & benchmarks

