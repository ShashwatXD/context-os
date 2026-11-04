"""Traceable Hybrid Context Retrieval and Assembly Service."""

import uuid
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.asset import Asset, CertificationStatus
from app.domain.entities.provenance import ProvenanceRecord
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.provenance_repo import ProvenanceRepository
from app.infrastructure.embeddings.local_embedding import LocalEmbeddingClient, cosine_similarity
from app.application.context_retrieval.ranker import reciprocal_rank_fusion


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
    trace_id: str


class ContextRetrievalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.asset_repo = AssetRepository(session)
        self.relationship_repo = RelationshipRepository(session)
        self.provenance_repo = ProvenanceRepository(session)
        self.embedder = LocalEmbeddingClient(dimension=64)

    async def query_context(
        self,
        query: str,
        top_k: int = 5,
        asset_types: Optional[List[str]] = None,
        minimum_confidence: float = 0.50,
        include_lineage_depth: int = 2,
    ) -> RetrievedContextResponse:
        trace_id = f"trc_{uuid.uuid4().hex[:10]}"
        all_assets: List[Asset] = await self.asset_repo.search_assets(limit=500)

        if not all_assets:
            return RetrievedContextResponse(query=query, trace_id=trace_id)

        # 1. Lexical / Keyword Search Ranking
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

        # 2. Dense Semantic Vector Ranking
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

        # 3. Reciprocal Rank Fusion (RRF)
        fused_scores = reciprocal_rank_fusion([lexical_ids, vector_ids], k=60)

        # 4. Filter by asset_types and minimum confidence
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

        # 5. Build Matched Entities with Provenance
        matched_entities: List[MatchedEntityContext] = []
        discrepancies: List[DiscrepancyReport] = []

        disputed_assets: List[Asset] = []
        for aid in selected_ids:
            asset = asset_map[aid]
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
                )
            )

            if asset.certification_status == CertificationStatus.DISPUTED:
                disputed_assets.append(asset)

        # 6. Traverse Multi-Hop Lineage Subgraph around top matched entities
        subgraph_nodes: Dict[str, Dict[str, Any]] = {}
        subgraph_edges: List[Dict[str, Any]] = []

        for aid in selected_ids[:2]:  # Traverse lineage for top 2 anchors
            lineage = await self.relationship_repo.get_lineage(
                asset_id=aid, depth=include_lineage_depth, direction="both"
            )
            for node in lineage["nodes"]:
                subgraph_nodes[node["id"]] = node
            for edge in lineage["edges"]:
                if edge not in subgraph_edges:
                    subgraph_edges.append(edge)

        # 7. Discrepancy Detection: Check for conflicting metrics or disputed definitions
        if disputed_assets:
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

        return RetrievedContextResponse(
            query=query,
            matched_entities=matched_entities,
            lineage_subgraph={
                "nodes": list(subgraph_nodes.values()),
                "edges": subgraph_edges,
            },
            discrepancies=discrepancies,
            trace_id=trace_id,
        )
