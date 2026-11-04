"""Deterministic Local Embedding Generator.

Produces unit-normalized dense float vectors using n-gram feature hashing
and token frequency weighting. Cosine similarity is computed via dot product.
Requires zero external API keys or heavy GPU runtimes.
"""

import hashlib
import math
import re
from typing import List
from app.application.entity_resolution.matcher import ABBREVIATIONS


class LocalEmbeddingClient:
    def __init__(self, dimension: int = 64):
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self._dimension

        vector = [0.0] * self._dimension
        raw_tokens = re.findall(r"\w+", text.lower())
        # Expand known domain abbreviations for semantic parity
        tokens = [ABBREVIATIONS.get(t, t) for t in raw_tokens]

        # Generate unigram and bigram features
        features = list(tokens)
        for i in range(len(tokens) - 1):
            features.append(f"{tokens[i]}_{tokens[i+1]}")

        for feat in features:
            # Deterministic hash bucket
            hash_val = int(hashlib.md5(feat.encode("utf-8")).hexdigest(), 16)
            bucket = hash_val % self._dimension
            sign = 1.0 if (hash_val // self._dimension) % 2 == 0 else -1.0
            vector[bucket] += sign

        # L2 Normalization
        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude > 0.0:
            vector = [v / magnitude for v in vector]

        return vector

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Computes cosine similarity between two unit vectors (dot product)."""
    if len(vec_a) != len(vec_b):
        return 0.0
    return sum(a * b for a, b in zip(vec_a, vec_b))
