"""Domain entities for Graph Relationships and Directed Edges."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, model_validator


class RelationshipType(str, Enum):
    TRANSFORMS_TO = "TRANSFORMS_TO"
    CONSUMES = "CONSUMES"
    BELONGS_TO = "BELONGS_TO"
    OWNS = "OWNS"
    DEFINES = "DEFINES"
    INFERRED_SAME_AS = "INFERRED_SAME_AS"
    DISPUTES = "DISPUTES"


class Relationship(BaseModel):
    id: str
    source_asset_id: str
    target_asset_id: str
    relationship_type: RelationshipType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_id: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_to: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def prevent_self_loop(self) -> "Relationship":
        if self.source_asset_id == self.target_asset_id:
            raise ValueError(
                f"Self-referential loop prohibited: source and target are both '{self.source_asset_id}'"
            )
        return self

