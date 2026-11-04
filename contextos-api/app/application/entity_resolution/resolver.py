"""Entity Resolution Service: Multi-source entity matching and review gating."""

import uuid
from typing import Dict, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.domain.entities.asset import Asset
from app.domain.relationships.relationship import Relationship, RelationshipType
from app.domain.governance.approval import Suggestion, SuggestionType, ApprovalRequest, ApprovalStatus
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.repositories.approval_repo import ApprovalRepository
from app.application.entity_resolution.matcher import calculate_match_confidence


class EntityResolutionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.asset_repo = AssetRepository(session)
        self.relationship_repo = RelationshipRepository(session)
        self.approval_repo = ApprovalRepository(session)

    async def resolve_all_sources(self) -> Dict[str, int]:
        """Resolves entities across all registered sources and applies confidence gating."""
        assets: List[Asset] = await self.asset_repo.search_assets(limit=1000)
        auto_linked = 0
        suggestions_created = 0

        # Pairwise comparison across distinct sources or different asset types
        for i in range(len(assets)):
            for j in range(i + 1, len(assets)):
                ast_a = assets[i]
                ast_b = assets[j]

                # Only resolve assets from different sources or distinct systems
                if ast_a.source_id == ast_b.source_id and ast_a.asset_type == ast_b.asset_type:
                    continue

                confidence, reason = calculate_match_confidence(ast_a.name, ast_b.name)

                if confidence >= settings.AUTO_LINK_THRESHOLD:
                    # High confidence -> Automatically link with INFERRED_SAME_AS
                    rel_id = f"rel_same_{uuid.uuid4().hex[:12]}"
                    rel = Relationship(
                        id=rel_id,
                        source_asset_id=ast_a.id,
                        target_asset_id=ast_b.id,
                        relationship_type=RelationshipType.INFERRED_SAME_AS,
                        confidence=confidence,
                        properties={"match_reason": reason, "resolved_by": "entity_resolution_pipeline"},
                    )
                    try:
                        await self.relationship_repo.create(rel)
                        auto_linked += 1
                    except Exception:
                        pass

                elif confidence >= settings.REVIEW_THRESHOLD:
                    # Moderate confidence -> Create Suggestion & Human Approval Request
                    sug_id = f"sug_res_{uuid.uuid4().hex[:12]}"
                    sug = Suggestion(
                        id=sug_id,
                        asset_id=ast_a.id,
                        suggestion_type=SuggestionType.RELATIONSHIP,
                        proposed_value={
                            "target_asset_id": ast_b.id,
                            "target_asset_name": ast_b.name,
                            "relationship_type": RelationshipType.INFERRED_SAME_AS.value,
                        },
                        reasoning=f"Potential match between '{ast_a.name}' and '{ast_b.name}': {reason}",
                        confidence=confidence,
                        status=ApprovalStatus.PENDING_REVIEW,
                    )
                    await self.approval_repo.create_suggestion(sug)

                    req_id = f"appr_res_{uuid.uuid4().hex[:12]}"
                    req = ApprovalRequest(
                        id=req_id,
                        suggestion_id=sug.id,
                        action_type="MERGE_OR_LINK_ENTITY",
                        requested_by="pipeline:entity_resolution",
                    )
                    await self.approval_repo.create_approval_request(req)
                    suggestions_created += 1

        return {
            "auto_linked_count": auto_linked,
            "suggestions_pending_review": suggestions_created,
        }

