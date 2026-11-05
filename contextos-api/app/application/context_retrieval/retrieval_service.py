"""Traceable Hybrid Context Retrieval and Assembly Service.

Supports:
- Mechanism B (On-Demand Context Retrieval): Lexical FTS + dense vector search + recursive lineage traversal + RRF
- Mechanism C (Live Source Retrieval Fallback): Freshness evaluation with live connector fetch & graceful degradation
- ACL-Aware Resource Filtering: Ensures callers only receive context they have permissions to view
"""

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.asset import Asset, CertificationStatus
from app.domain.entities.provenance import ProvenanceRecord
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.source_repo import SourceRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.provenance_repo import ProvenanceRepository
from app.infrastructure.embeddings.local_embedding import LocalEmbeddingClient, cosine_similarity
from app.application.context_retrieval.ranker import reciprocal_rank_fusion
from app.infrastructure.llm.grounded_llm import GroundedLLMProvider


class MatchedEntityContext(BaseModel):
    asset_id: str
    name: str
    qualified_name: str
    asset_type: str
    relevance_score: float
    certification_status: str
    owner_name: Optional[str] = None
    description: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None
    freshness_status: str = "CACHED"


class DiscrepancyReport(BaseModel):
    discrepancy_type: str
    description: str
    confidence: float
    evidence_asset_ids: List[str]


class RetrievedContextResponse(BaseModel):
    query: str
    matched_entities: List[MatchedEntityContext] = Field(default_factory=list)
    lineage_subgraph: Dict[str, Any] = Field(default_factory=dict)
    discrepancies: List[DiscrepancyReport] = Field(default_factory=list)
    freshness_warning: Optional[str] = None
    ai_summary: Optional[Dict[str, Any]] = None
    trace_id: str


class ContextRetrievalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.asset_repo = AssetRepository(session)
        self.source_repo = SourceRepository(session)
        self.relationship_repo = RelationshipRepository(session)
        self.provenance_repo = ProvenanceRepository(session)
        self.embedder = LocalEmbeddingClient(dimension=64)
        self.llm = GroundedLLMProvider()

    async def query_context(
        self,
        query: str,
        top_k: int = 5,
        asset_types: Optional[List[str]] = None,
        minimum_confidence: float = 0.50,
        include_lineage_depth: int = 2,
        caller_acl_tags: Optional[List[str]] = None,
        force_fresh: bool = False,
    ) -> RetrievedContextResponse:
        trace_id = f"trc_{uuid.uuid4().hex[:10]}"
        all_assets: List[Asset] = await self.asset_repo.search_assets(limit=500)

        # 1. ACL-Aware Resource Filtering
        if caller_acl_tags is not None and "*" not in caller_acl_tags:
            allowed_set = set(caller_acl_tags)
            all_assets = [
                a for a in all_assets
                if not a.acl_tags or allowed_set.intersection(set(a.acl_tags))
            ]

        if not all_assets:
            return RetrievedContextResponse(query=query, trace_id=trace_id)

        # 2. Lexical / Keyword Search Ranking
        query_tokens = set(query.lower().split())
        lexical_ranked: List[Tuple[str, float]] = []
        for ast in all_assets:
            score = 0.0
            name_tokens = set(ast.name.lower().split("_"))
            desc_tokens = set((ast.description or "").lower().split())
            combined_tokens = name_tokens.union(desc_tokens)

            overlap = len(query_tokens.intersection(combined_tokens))
            if overlap > 0:
                score = overlap / len(query_tokens)
                lexical_ranked.append((ast.id, score))

        lexical_ranked.sort(key=lambda x: x[1], reverse=True)
        lexical_ids = [item[0] for item in lexical_ranked]

        # 3. Dense Semantic Vector Ranking
        query_vector = self.embedder.embed_text(query)
        vector_ranked: List[Tuple[str, float]] = []
        for ast in all_assets:
            content_to_embed = f"{ast.name} {ast.description or ''} {ast.qualified_name}"
            ast_vector = self.embedder.embed_text(content_to_embed)
            sim = cosine_similarity(query_vector, ast_vector)
            if sim > 0.05:
                vector_ranked.append((ast.id, sim))

        vector_ranked.sort(key=lambda x: x[1], reverse=True)
        vector_ids = [item[0] for item in vector_ranked]

        # 4. Reciprocal Rank Fusion (RRF)
        fused_scores = reciprocal_rank_fusion([lexical_ids, vector_ids], k=60)

        # 5. Filter by asset_types and minimum confidence
        asset_map = {a.id: a for a in all_assets}
        candidate_ids = [
            aid for aid, score in sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
            if score >= minimum_confidence
        ]

        if asset_types:
            candidate_ids = [
                aid for aid in candidate_ids
                if asset_map[aid].asset_type.value in asset_types
            ]

        selected_ids = candidate_ids[:top_k]

        # 6. Mechanism C: Freshness Evaluation & Live Source Fallback
        freshness_warning: Optional[str] = None
        matched_entities: List[MatchedEntityContext] = []
        discrepancies: List[DiscrepancyReport] = []
        disputed_assets: List[Asset] = []

        now = datetime.now(timezone.utc)
        for aid in selected_ids:
            asset = asset_map[aid]
            freshness_status = "CACHED"

            # Check source freshness threshold
            source = await self.source_repo.get_by_id(asset.source_id)
            if source and source.last_sync_at:
                last_sync = source.last_sync_at
                if last_sync.tzinfo is None:
                    last_sync = last_sync.replace(tzinfo=timezone.utc)
                age_seconds = (now - last_sync).total_seconds()
                is_stale = age_seconds > source.freshness_threshold_seconds

                if force_fresh or is_stale:
                    # Attempt Live Fetch Fallback (Mechanism C)
                    live_result = await self._attempt_live_fallback(source, asset.external_id)
                    if live_result and live_result.assets:
                        fresh_asset = live_result.assets[0]
                        await self.asset_repo.upsert(fresh_asset)
                        asset = fresh_asset
                        freshness_status = "LIVE_VERIFIED"
                    else:
                        freshness_warning = f"Live source '{source.name}' was unreachable or timed out. Serving cached context."

            prov_summary = None
            if asset.provenance_id:
                prov = await self.provenance_repo.get_by_id(asset.provenance_id)
                if prov:
                    prov_summary = {
                        "source_id": prov.source_id,
                        "extraction_method": prov.extraction_method,
                        "source_hash": prov.source_hash[:16],
                        "evidence_snippet": prov.raw_evidence,
                    }

            matched_entities.append(
                MatchedEntityContext(
                    asset_id=asset.id,
                    name=asset.name,
                    qualified_name=asset.qualified_name,
                    asset_type=asset.asset_type.value,
                    relevance_score=fused_scores.get(asset.id, 0.5),
                    certification_status=asset.certification_status.value,
                    owner_name=asset.owner_name,
                    description=asset.description,
                    provenance=prov_summary,
                    freshness_status=freshness_status,
                )
            )

            if asset.certification_status == CertificationStatus.DISPUTED:
                disputed_assets.append(asset)

        # 7. Multi-Hop Lineage Subgraph Traversal
        subgraph_nodes: Dict[str, Dict[str, Any]] = {}
        subgraph_edges: List[Dict[str, Any]] = []

        for aid in selected_ids[:2]:
            lineage = await self.relationship_repo.get_lineage(
                asset_id=aid, depth=include_lineage_depth, direction="both"
            )
            for node in lineage["nodes"]:
                subgraph_nodes[node["id"]] = node
            for edge in lineage["edges"]:
                if edge not in subgraph_edges:
                    subgraph_edges.append(edge)

        # 8. Discrepancy Detection
        for da in disputed_assets:
            discrepancies.append(
                DiscrepancyReport(
                    discrepancy_type="DISPUTED_DEFINITION",
                    description=(
                        f"Asset '{da.name}' ({da.qualified_name}) is marked DISPUTED. "
                        f"Definition: '{da.description}' conflicts with certified enterprise standards."
                    ),
                    confidence=0.91,
                    evidence_asset_ids=[da.id],
                )
            )

        # 9. AI Root-Cause and Semantic Context Synthesis
        ai_summary = await self.llm.synthesize_root_cause_summary(
            query=query,
            matched_entities=matched_entities,
            discrepancies=discrepancies,
            subgraph_nodes=list(subgraph_nodes.values()),
        )

        return RetrievedContextResponse(
            query=query,
            matched_entities=matched_entities,
            lineage_subgraph={
                "nodes": list(subgraph_nodes.values()),
                "edges": subgraph_edges,
            },
            discrepancies=discrepancies,
            freshness_warning=freshness_warning,
            ai_summary=ai_summary,
            trace_id=trace_id,
        )

    async def _attempt_live_fallback(self, source: Any, external_id: str) -> Optional[Any]:
        """Mechanism C helper: invokes connector's fetch_live_record."""
        from app.application.ingestion.ingestion_service import CONNECTOR_REGISTRY
        connector_cls = CONNECTOR_REGISTRY.get(source.source_type)
        if not connector_cls:
            return None
        try:
            connector = connector_cls(source_id=source.id, connection_config=source.connection_config)
            return await connector.fetch_live_record(external_id)
        except Exception:
            return None

    async def retrieve_source_evidence(self, provenance_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves raw cryptographic provenance evidence for a specific verification ID."""
        prov = await self.provenance_repo.get_by_id(provenance_id)
        if not prov:
            return None
        return {
            "provenance_id": prov.id,
            "entity_id": prov.entity_id,
            "source_id": prov.source_id,
            "extraction_method": prov.extraction_method,
            "source_hash": prov.source_hash,
            "raw_evidence": prov.raw_evidence,
            "captured_at": prov.captured_at.isoformat(),
        }
