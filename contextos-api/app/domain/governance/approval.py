"""Domain entities for Governance, Suggestions and Human Approval Workflows."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class SuggestionType(str, Enum):
    DESCRIPTION = "DESCRIPTION"
    BUSINESS_TERM = "BUSINESS_TERM"
    OWNERSHIP = "OWNERSHIP"
    RELATIONSHIP = "RELATIONSHIP"
    CLASSIFICATION = "CLASSIFICATION"
    DEPRECATION = "DEPRECATION"


class ApprovalStatus(str, Enum):
    SUGGESTED = "SUGGESTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Suggestion(BaseModel):
    id: str
    asset_id: str
    suggestion_type: SuggestionType
    proposed_value: Dict[str, Any]
    reasoning: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    status: ApprovalStatus = ApprovalStatus.PENDING_REVIEW
    evidence_provenance_id: Optional[str] = None
    created_by_agent_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalRequest(BaseModel):
    id: str
    suggestion_id: str
    action_type: str  # e.g., "APPLY_METRIC_DEFINITION", "MERGE_ENTITY", "CERTIFY_ASSET"
    requested_by: str
    reviewer_id: Optional[str] = None
    status: ApprovalStatus = ApprovalStatus.PENDING_REVIEW
    decision_notes: Optional[str] = None
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None

