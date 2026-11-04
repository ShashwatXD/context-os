# ContextOS Web Console (`contextos-web`)

Minimalist enterprise frontend console for **ContextOS**.

Built with Next.js 14, React 18, TypeScript, and Tailwind CSS. Provides engineering visibility into enterprise context graphs, multi-hop lineage, metadata catalog, AI enrichment approvals, MCP tool registries, and distributed trace observability.

---

## Screen Navigation

1. **Overview (`/`)**: High-level platform KPIs, live interactive traceable hybrid context query inspector with discrepancy alerts.
2. **Sources (`/sources`)**: Enterprise sources of record (PostgreSQL, dbt, Notion/Markdown) with sync health and manual trigger.
3. **Catalog (`/catalog`)**: Searchable metadata catalog with type filters and schema attribute inspection.
4. **Lineage (`/lineage`)**: Interactive multi-hop dependency visualizer tracing upstream and downstream flows.
5. **Context Graph (`/graph`)**: Topology of enterprise entities and inferred semantic links.
6. **Context Agents (`/agents`)**: Registered enrichment agents, roles, permissions, and recent execution summaries.
7. **Governance (`/governance`)**: Human-in-the-loop approval queue for AI suggestions and sensitive metric redefinitions.
8. **Agent Access (`/agent-access`)**: Model Context Protocol (MCP) server endpoints, tool catalog, and Claude Desktop config.
9. **Observability (`/observability`)**: Distributed trace inspection with span waterfall breakdown and payload inspection.
10. **Evaluations (`/evaluations`)**: Empirical golden benchmark metrics (Recall@K, relevance, compliance, latency).

---

## Development Setup

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

Console will be live at `http://localhost:3000`.

### Environment Configuration
Create a `.env.local` file:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

