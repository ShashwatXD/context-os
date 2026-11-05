"""Domain entities for Enterprise Assets and Metadata."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AssetType(str, Enum):
    DATABASE = "DATABASE"
    SCHEMA = "SCHEMA"
    TABLE = "TABLE"
    COLUMN = "COLUMN"
    DASHBOARD = "DASHBOARD"
    METRIC = "METRIC"
    TRANSFORMATION_MODEL = "TRANSFORMATION_MODEL"
    DOCUMENTATION = "DOCUMENTATION"
    TEAM = "TEAM"
    USER = "USER"
    CHANNEL = "CHANNEL"
    PULL_REQUEST = "PULL_REQUEST"
    COMMIT = "COMMIT"


class CertificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    PENDING_REVIEW = "PENDING_REVIEW"
    CERTIFIED = "CERTIFIED"
    DEPRECATED = "DEPRECATED"
    DISPUTED = "DISPUTED"


class ColumnMetadata(BaseModel):
    name: str
    data_type: str
    is_primary_key: bool = False
    is_nullable: bool = True
    description: Optional[str] = None


class SearchChunk(BaseModel):
    id: str
    asset_id: str
    chunk_type: str
    chunk_text: str
    metadata_filters: Dict[str, Any] = Field(default_factory=dict)
    acl_tags: List[str] = Field(default_factory=list)
    embedding: Optional[List[float]] = None
    version_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Asset(BaseModel):
    id: str
    source_id: str
    external_id: str
    name: str
    qualified_name: str
    asset_type: AssetType
    description: Optional[str] = None
    certification_status: CertificationStatus = CertificationStatus.UNVERIFIED
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    columns: List[ColumnMetadata] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    acl_tags: List[str] = Field(default_factory=list)
    metadata_payload: Dict[str, Any] = Field(default_factory=dict)
    provenance_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

