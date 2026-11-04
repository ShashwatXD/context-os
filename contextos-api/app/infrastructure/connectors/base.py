"""Abstract Base Connector Interface for ContextOS Enterprise Ingestion."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple
from pydantic import BaseModel, Field
from app.domain.entities.asset import Asset
from app.domain.relationships.relationship import Relationship
from app.domain.entities.provenance import ProvenanceRecord


class ExtractionResult(BaseModel):
    assets: List[Asset] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    provenance_records: List[ProvenanceRecord] = Field(default_factory=list)
    metadata_summary: Dict[str, Any] = Field(default_factory=dict)


class BaseConnector(ABC):
    """Abstract base class that all data source connectors must implement."""

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

