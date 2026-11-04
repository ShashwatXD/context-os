"""Abstract LLM Provider Interface for ContextOS."""

from typing import Any, Dict, List, Optional, Protocol
from pydantic import BaseModel


class LLMEnrichmentProposal(BaseModel):
    proposed_description: Optional[str] = None
    suggested_business_terms: List[str] = []
    suggested_owner: Optional[str] = None
    suggested_classification: Optional[str] = None
    reasoning: str
    confidence: float
    evidence_references: List[str] = []


class LLMProvider(Protocol):
    """Protocol for AI LLM providers."""

    async def generate_enrichment(
        self,
        asset_name: str,
        asset_type: str,
        columns: List[Dict[str, Any]],
        upstream_context: List[str],
    ) -> LLMEnrichmentProposal:
        """Generates grounded metadata proposals based on asset schema and lineage evidence."""
        ...

