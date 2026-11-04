"""Governance and Human Approval API Routes."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from app.domain.governance.approval import ApprovalStatus
from app.application.approvals.approval_service import ApprovalService
from app.interfaces.api.dependencies import get_approval_service
from app.interfaces.api.schemas.api_schemas import ApprovalDecisionRequest

router = APIRouter(prefix="/approvals", tags=["Governance"])


@router.get("")
async def list_pending_approvals(
    limit: int = 50,
    approval_service: ApprovalService = Depends(get_approval_service),
) -> List[Dict[str, Any]]:
    return await approval_service.list_pending(limit=limit)


@router.post("/{request_id}/decide")
async def decide_approval_request(
    request_id: str,
    req: ApprovalDecisionRequest,
    approval_service: ApprovalService = Depends(get_approval_service),
) -> Dict[str, Any]:
    try:
        decision = ApprovalStatus(req.decision.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Decision must be 'APPROVED' or 'REJECTED'",
        )

    return await approval_service.review_request(
        request_id=request_id,
        decision=decision,
        reviewer_id=req.reviewer_id,
        decision_notes=req.decision_notes,
    )

