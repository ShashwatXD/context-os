"""ContextOS Domain & Application Exceptions Hierarchy."""

from typing import Any, Dict, Optional


class ContextOSError(Exception):
    """Base exception for all ContextOS errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EntityNotFoundError(ContextOSError):
    """Raised when an asset, source, or record is not found."""

    def __init__(self, entity_type: str, entity_id: str):
        super().__init__(
            f"{entity_type} with ID '{entity_id}' not found.",
            {"entity_type": entity_type, "entity_id": entity_id},
        )


class DuplicateAssetError(ContextOSError):
    """Raised when an asset with identical source and external_id already exists."""

    def __init__(self, source_id: str, external_id: str):
        super().__init__(
            f"Asset with external ID '{external_id}' in source '{source_id}' already exists.",
            {"source_id": source_id, "external_id": external_id},
        )


class InvalidRelationshipError(ContextOSError):
    """Raised when an invalid relationship is proposed (e.g. self-cycle)."""

    def __init__(self, message: str, source_id: str, target_id: str):
        super().__init__(
            message,
            {"source_id": source_id, "target_id": target_id},
        )


class ApprovalRequiredError(ContextOSError):
    """Raised when an agent attempts a sensitive action that requires human approval."""

    def __init__(self, action: str, suggestion_id: str):
        super().__init__(
            f"Action '{action}' requires human approval before execution.",
            {"action": action, "suggestion_id": suggestion_id},
        )


class PermissionDeniedError(ContextOSError):
    """Raised when an agent or user lacks required tool or resource permissions."""

    def __init__(self, actor: str, required_permission: str):
        super().__init__(
            f"Actor '{actor}' lacks required permission: {required_permission}.",
            {"actor": actor, "required_permission": required_permission},
        )


class ConnectorError(ContextOSError):
    """Raised when an ingestion connector fails during extraction or synchronization."""

    def __init__(self, source_id: str, reason: str):
        super().__init__(
            f"Connector error for source '{source_id}': {reason}",
            {"source_id": source_id, "reason": reason},
        )


class IngestionError(ContextOSError):
    """Raised when data transformation or normalization fails during ingestion."""
    pass

