"""AI Context Enrichment Service: Proposes metadata improvements with human review gates."""

import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import EntityNotFoundError
from app.domain.entities.asset import Asset
from app.domain.governance.approval import (
    ApprovalRequest,
    ApprovalStatus,
    Suggestion,
    SuggestionType,
)
from app.infrastructure.llm.grounded_llm import GroundedLLMProvider
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.approval_repo import ApprovalRepository


class EnrichmentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.asset_repo = AssetRepository(session)
        self.relationship_repo = RelationshipRepository(session)
        self.approval_repo = ApprovalRepository(session)
        self.llm = GroundedLLMProvider()

    async def enrich_asset(
        self, asset_id: str, agent_id: str = "agent_enricher_v1"
    ) -> Dict[str, Any]:
        asset = await self.asset_repo.get_by_id(asset_id)
        if not asset:
            raise EntityNotFoundError("Asset", asset_id)

        # Retrieve upstream lineage context as grounding evidence
        lineage = await self.relationship_repo.get_lineage(
            asset_id=asset_id, depth=2, direction="upstream"
        )
        upstream_names = [n["name"] for n in lineage["nodes"] if n["id"] != asset_id]

        cols_data = [c.model_dump() for c in asset.columns]

        proposal = await self.llm.generate_enrichment(
            asset_name=asset.name,
            asset_type=asset.asset_type.value,
            columns=cols_data,
            upstream_context=upstream_names,
        )

        sug_id = f"sug_{uuid.uuid4().hex[:12]}"
        suggestion = Suggestion(
            id=sug_id,
            asset_id=asset.id,
            suggestion_type=SuggestionType.DESCRIPTION,
            proposed_value={
                "description": proposal.proposed_description,
                "business_terms": proposal.suggested_business_terms,
                "suggested_owner": proposal.suggested_owner,
                "classification": proposal.suggested_classification,
            },
            reasoning=proposal.reasoning,
            confidence=proposal.confidence,
            status=ApprovalStatus.PENDING_REVIEW,
            evidence_provenance_id=asset.provenance_id,
            created_by_agent_id=agent_id,
        )
        await self.approval_repo.create_suggestion(suggestion)

        req_id = f"appr_{uuid.uuid4().hex[:12]}"
        req = ApprovalRequest(
            id=req_id,
            suggestion_id=suggestion.id,
            action_type="APPLY_AI_ENRICHMENT",
            requested_by=agent_id,
            status=ApprovalStatus.PENDING_REVIEW,
        )
        await self.approval_repo.create_approval_request(req)

        return {
            "suggestion_id": suggestion.id,
            "approval_request_id": req.id,
            "asset_id": asset.id,
            "proposed_description": proposal.proposed_description,
            "confidence": proposal.confidence,
            "status": ApprovalStatus.PENDING_REVIEW.value,
        }

