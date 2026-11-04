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


class Source(BaseModel):
    id: str
    name: str
    source_type: SourceType
    connection_config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[SyncStatus] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

