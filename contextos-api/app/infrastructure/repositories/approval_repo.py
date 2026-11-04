"""Governance & Approval Repository Implementation."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.governance.approval import (
    ApprovalRequest,
    ApprovalStatus,
    Suggestion,
    SuggestionType,
)
from app.infrastructure.database.models import (
    ApprovalRequestModel,
    SuggestionModel,
    AssetModel,
)


class ApprovalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_suggestion(self, suggestion: Suggestion) -> Suggestion:
        model = SuggestionModel(
            id=suggestion.id,
            asset_id=suggestion.asset_id,
            suggestion_type=suggestion.suggestion_type.value,
            proposed_value_payload=suggestion.proposed_value,
            reasoning=suggestion.reasoning,
            confidence=suggestion.confidence,
            status=suggestion.status.value,
            evidence_provenance_id=suggestion.evidence_provenance_id,
            created_by_agent_id=suggestion.created_by_agent_id,
            created_at=suggestion.created_at,
            updated_at=suggestion.updated_at,
        )
        self.session.add(model)
        await self.session.flush()
        return suggestion

    async def create_approval_request(self, req: ApprovalRequest) -> ApprovalRequest:
        model = ApprovalRequestModel(
            id=req.id,
            suggestion_id=req.suggestion_id,
            action_type=req.action_type,
            requested_by=req.requested_by,
            reviewer_id=req.reviewer_id,
            status=req.status.value,
            decision_notes=req.decision_notes,
            requested_at=req.requested_at,
            reviewed_at=req.reviewed_at,
        )
        self.session.add(model)
        await self.session.flush()
        return req

    async def list_pending_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
        stmt = (
            select(ApprovalRequestModel, SuggestionModel, AssetModel)
            .join(SuggestionModel, ApprovalRequestModel.suggestion_id == SuggestionModel.id)
            .join(AssetModel, SuggestionModel.asset_id == AssetModel.id)
            .where(ApprovalRequestModel.status == ApprovalStatus.PENDING_REVIEW.value)
            .order_by(desc(ApprovalRequestModel.requested_at))
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        items = []
        for req, sug, ast in res.all():
            items.append({
                "request_id": req.id,
                "suggestion_id": sug.id,
                "asset_id": ast.id,
                "asset_name": ast.name,
                "asset_type": ast.asset_type,
                "action_type": req.action_type,
                "suggestion_type": sug.suggestion_type,
                "proposed_value": sug.proposed_value_payload,
                "reasoning": sug.reasoning,
                "confidence": sug.confidence,
                "requested_by": req.requested_by,
                "status": req.status,
                "requested_at": req.requested_at,
            })
        return items

    async def decide_request(
        self,
        request_id: str,
        decision: ApprovalStatus,
        reviewer_id: str,
        decision_notes: Optional[str] = None,
    ) -> Optional[ApprovalRequest]:
        stmt = select(ApprovalRequestModel).where(ApprovalRequestModel.id == request_id)
        res = await self.session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            return None

        now = datetime.now(timezone.utc)
        model.status = decision.value
        model.reviewer_id = reviewer_id
        model.decision_notes = decision_notes
        model.reviewed_at = now

        # Also update parent suggestion
        sug_stmt = select(SuggestionModel).where(SuggestionModel.id == model.suggestion_id)
        sug_res = await self.session.execute(sug_stmt)
        sug_model = sug_res.scalar_one_or_none()
        if sug_model:
            sug_model.status = decision.value
            sug_model.updated_at = now

        await self.session.flush()
        return ApprovalRequest(
            id=model.id,
            suggestion_id=model.suggestion_id,
            action_type=model.action_type,
            requested_by=model.requested_by,
            reviewer_id=model.reviewer_id,
            status=ApprovalStatus(model.status),
            decision_notes=model.decision_notes,
            requested_at=model.requested_at,
            reviewed_at=model.reviewed_at,
        )

