"""Human Approval Governance Service: Enforces review state transitions and applies mutations."""

from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import EntityNotFoundError
from app.domain.entities.asset import Asset, CertificationStatus
from app.domain.governance.approval import ApprovalRequest, ApprovalStatus, Suggestion
from app.infrastructure.repositories.approval_repo import ApprovalRepository
from app.infrastructure.repositories.asset_repo import AssetRepository
from app.infrastructure.repositories.relationship_repo import RelationshipRepository
from app.infrastructure.database.models import SuggestionModel
from sqlalchemy import select


class ApprovalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.approval_repo = ApprovalRepository(session)
        self.asset_repo = AssetRepository(session)
        self.relationship_repo = RelationshipRepository(session)

    async def list_pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.approval_repo.list_pending_requests(limit=limit)

    async def review_request(
        self,
        request_id: str,
        decision: ApprovalStatus,
        reviewer_id: str,
        decision_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Applies the reviewer decision and executes mutations if approved."""
        decided_req = await self.approval_repo.decide_request(
            request_id=request_id,
            decision=decision,
            reviewer_id=reviewer_id,
            decision_notes=decision_notes,
        )
        if not decided_req:
            raise EntityNotFoundError("ApprovalRequest", request_id)

        # Retrieve the underlying suggestion to execute mutations
        stmt = select(SuggestionModel).where(SuggestionModel.id == decided_req.suggestion_id)
        res = await self.session.execute(stmt)
        sug_model = res.scalar_one_or_none()

        applied = False
        if decision == ApprovalStatus.APPROVED and sug_model:
            asset = await self.asset_repo.get_by_id(sug_model.asset_id)
            if asset:
                proposed = sug_model.proposed_value_payload or {}

                # Apply description update
                if "description" in proposed and proposed["description"]:
                    asset.description = proposed["description"]

                # Apply owner update
                if "suggested_owner" in proposed and proposed["suggested_owner"]:
                    asset.owner_name = proposed["suggested_owner"]

                # Upgrade certification status to CERTIFIED upon approved human review
                asset.certification_status = CertificationStatus.CERTIFIED
                await self.asset_repo.upsert(asset)
                applied = True

        return {
            "request_id": decided_req.id,
            "status": decided_req.status.value,
            "reviewer_id": decided_req.reviewer_id,
            "applied_to_asset": applied,
            "decision_notes": decision_notes,
        }

