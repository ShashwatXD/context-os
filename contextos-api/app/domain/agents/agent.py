"""Domain entities for Agents, Runtime Execution, Traces, and Spans."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


class SpanType(str, Enum):
    USER_REQUEST = "USER_REQUEST"
    CONTEXT_RETRIEVAL = "CONTEXT_RETRIEVAL"
    LLM_INVOCATION = "LLM_INVOCATION"
    TOOL_SELECTION = "TOOL_SELECTION"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    FINAL_RESPONSE = "FINAL_RESPONSE"


class TraceSpan(BaseModel):
    id: str
    run_id: str
    parent_span_id: Optional[str] = None
    span_type: SpanType
    name: str
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    output_payload: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    status: str = "SUCCESS"  # SUCCESS | ERROR | BLOCKED
    error_message: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None


class Agent(BaseModel):
    id: str
    name: str
    version: str = "1.0.0"
    role: str
    system_prompt: str
    allowed_tools: List[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentRun(BaseModel):
    id: str
    agent_id: str
    trigger_event: str
    input_prompt: str
    status: RunStatus = RunStatus.PENDING
    latency_ms: float = 0.0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    output_response: Optional[str] = None
    retrieved_context_ids: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    spans: List[TraceSpan] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

