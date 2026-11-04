"""Unit tests for Hybrid Retrieval, Local Embeddings, and Reciprocal Rank Fusion."""

from app.application.context_retrieval.ranker import reciprocal_rank_fusion
from app.infrastructure.embeddings.local_embedding import LocalEmbeddingClient, cosine_similarity


def test_reciprocal_rank_fusion_scoring():
    # Asset 'ast_01' is rank 1 in list A and rank 2 in list B
    list_a = ["ast_01", "ast_02", "ast_03"]
    list_b = ["ast_02", "ast_01", "ast_04"]

    scores = reciprocal_rank_fusion([list_a, list_b], k=60)

    assert "ast_01" in scores
    assert "ast_02" in scores
    assert "ast_03" in scores
    assert "ast_04" in scores

    # Both ast_01 and ast_02 appear near top in both lists, so they must score highest
    assert scores["ast_01"] > scores["ast_03"]
    assert scores["ast_02"] > scores["ast_04"]


def test_local_embedding_deterministic_similarity():
    embedder = LocalEmbeddingClient(dimension=64)

    vec_revenue1 = embedder.embed_text("monthly recurring revenue subscription")
    vec_revenue2 = embedder.embed_text("mrr monthly revenue recurring")
    vec_unrelated = embedder.embed_text("customer support desk ticket incident")

    sim_related = cosine_similarity(vec_revenue1, vec_revenue2)
    sim_unrelated = cosine_similarity(vec_revenue1, vec_unrelated)

    assert sim_related > sim_unrelated
    assert sim_related > 0.30
    assert sim_unrelated < 0.10
