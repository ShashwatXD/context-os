"""Abstract Base Connector Interface for ContextOS Enterprise Ingestion.

Supports the Three Data Access Mechanisms:
- Mechanism A: Historical & Incremental Ingestion via extract() and extract_incremental()
- Mechanism C: Live Source Fallback Retrieval via fetch_live_record()
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.domain.entities.asset import Asset, SearchChunk
from app.domain.relationships.relationship import Relationship
from app.domain.entities.provenance import ProvenanceRecord
from app.domain.entities.source import SourceRecord


class ExtractionResult(BaseModel):
    assets: List[Asset] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    provenance_records: List[ProvenanceRecord] = Field(default_factory=list)
    source_records: List[SourceRecord] = Field(default_factory=list)
    search_chunks: List[SearchChunk] = Field(default_factory=list)
    metadata_summary: Dict[str, Any] = Field(default_factory=dict)
    next_cursor: Optional[str] = None


class BaseConnector(ABC):
    """Abstract base class that all enterprise data source connectors must implement."""

    def __init__(self, source_id: str, connection_config: Dict[str, Any]):
        self.source_id = source_id
        self.config = connection_config

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Verifies connectivity and credentials to the enterprise source."""
        pass

    @abstractmethod
    async def extract(self) -> ExtractionResult:
        """Extracts metadata assets, relationships, and evidence from the source."""
        pass

    async def extract_incremental(self, cursor: Optional[str] = None) -> ExtractionResult:
        """Mechanism A: Incremental synchronization starting from cursor."""
        return await self.extract()

    async def fetch_live_record(self, external_id: str) -> Optional[ExtractionResult]:
        """Mechanism C: Live just-in-time retrieval fallback from provider API."""
        return None
