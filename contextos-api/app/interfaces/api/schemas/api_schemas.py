"""Pydantic Request and Response Schemas for ContextOS REST API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Health
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    database: str = "connected"
    timestamp: datetime


# Sources
class SourceCreateRequest(BaseModel):
    name: str
    source_type: str
    connection_config: Dict[str, Any] = Field(default_factory=dict)


class SourceResponse(BaseModel):
    id: str
    name: str
    source_type: str
    connection_config: Dict[str, Any]
    is_active: bool
    freshness_threshold_seconds: int = 900
    auth_type: str = "API_TOKEN"
    oauth_scopes: List[str] = Field(default_factory=list)
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    created_at: datetime


class CheckpointResponse(BaseModel):
    id: str
    source_id: str
    cursor_value: str
    checkpoint_metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class DeadLetterResponse(BaseModel):
    id: str
    source_id: str
    raw_record_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    error_reason: str
    retry_count: int
    failed_at: datetime


class SyncJobResponse(BaseModel):
    sync_id: str
    source_id: str
    status: str
    entities_extracted: int = 0
    relationships_extracted: int = 0
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


# Assets & Lineage
class ColumnSchema(BaseModel):
    name: str
    data_type: str
    is_primary_key: bool = False
    is_nullable: bool = True
    description: Optional[str] = None


class AssetSummary(BaseModel):
    id: str
    source_id: str
    external_id: str
    name: str
    qualified_name: str
    asset_type: str
    description: Optional[str] = None
    certification_status: str
    owner_name: Optional[str] = None
    created_at: datetime


class AssetDetail(AssetSummary):
    columns: List[ColumnSchema] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    metadata_payload: Dict[str, Any] = Field(default_factory=dict)
    provenance_id: Optional[str] = None


class LineageGraphResponse(BaseModel):
    root_asset_id: str
    depth: int
    direction: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


# Context Query
class ContextQueryRequest(BaseModel):
    query: str
    top_k: int = 5
    asset_types: Optional[List[str]] = None
    minimum_confidence: float = 0.50
    include_lineage_depth: int = 2


# Governance & Approvals
class ApprovalDecisionRequest(BaseModel):
    decision: str  # "APPROVED" | "REJECTED"
    reviewer_id: str
    decision_notes: Optional[str] = None


# Agents & Runs
class AgentRunRequest(BaseModel):
    user_prompt: str
    tool_sequence: Optional[List[Dict[str, Any]]] = None


# Evaluations
class EvalRunRequest(BaseModel):
    model_version: Optional[str] = "contextos-hybrid-v1.0"

