"""Domain entities for Roles, Permissions, and Access Governance."""

from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    APPROVE = "APPROVE"
    EXECUTE = "EXECUTE"
    ADMIN = "ADMIN"


class ToolPermission(BaseModel):
    tool_name: str
    allowed_actions: List[ActionType] = Field(default_factory=lambda: [ActionType.READ])
    requires_approval: bool = False


class Role(BaseModel):
    name: str
    description: str
    permissions: List[ToolPermission] = Field(default_factory=list)

