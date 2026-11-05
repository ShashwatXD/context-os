"""Domain entities for Enterprise Sources and Synchronization."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    POSTGRESQL = "POSTGRESQL"
    SNOWFLAKE = "SNOWFLAKE"
    DBT = "DBT"
    GITHUB = "GITHUB"
    NOTION = "NOTION"
    TABLEAU = "TABLEAU"
    SLACK = "SLACK"


class SyncStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SyncRecord(BaseModel):
    id: str
    source_id: str
    status: SyncStatus
    entities_extracted: int = 0
    relationships_extracted: int = 0
    error_message: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class SyncCheckpoint(BaseModel):
    id: str
    source_id: str
    cursor_value: str
    checkpoint_metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeadLetterRecord(BaseModel):
    id: str
    source_id: str
    raw_record_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    error_reason: str
    retry_count: int = 1
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceRecord(BaseModel):
    id: str
    source_id: str
    external_id: str
    record_type: str
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    version_hash: str
    is_deleted: bool = False
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Source(BaseModel):
    id: str
    name: str
    source_type: SourceType
    connection_config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    freshness_threshold_seconds: int = 900
    auth_type: str = "API_TOKEN"
    oauth_scopes: list[str] = Field(default_factory=list)
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[SyncStatus] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

