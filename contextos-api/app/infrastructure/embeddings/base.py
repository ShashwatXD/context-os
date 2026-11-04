"""Abstract Protocol for Dense Embedding Generation."""

from typing import List, Protocol


class EmbeddingClient(Protocol):
    """Protocol for generating dense semantic vector embeddings."""

    @property
    def dimension(self) -> int:
        """Vector dimension size."""
        ...

    def embed_text(self, text: str) -> List[float]:
        """Embeds a single string into a normalized float vector."""
        ...

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embeds a batch of strings into normalized float vectors."""
        ...

