"""Domain entity for Provenance and Lineage Evidence."""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class EvidenceSnippet(BaseModel):
    title: str
    content: str
    location_ref: Optional[str] = None  # e.g., file path, line number, SQL statement, query


class ProvenanceRecord(BaseModel):
    id: str
    entity_id: str
    entity_type: str  # e.g., "ASSET", "RELATIONSHIP", "SUGGESTION"
    source_id: str
    extraction_method: str  # e.g., "DBT_MANIFEST_PARSER", "INFORMATION_SCHEMA", "SEMANTIC_INFERENCE"
    source_hash: str
    raw_evidence: Dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def compute_hash(cls, payload: Dict[str, Any]) -> str:
        """Computes a deterministic SHA-256 hash of the evidence payload."""
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

