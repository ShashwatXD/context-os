"""Reciprocal Rank Fusion (RRF) & Multi-Modal Ranker."""

from typing import Any, Dict, List


def reciprocal_rank_fusion(
    ranked_lists: List[List[str]],
    k: int = 60,
) -> Dict[str, float]:
    """Combines multiple ranked candidate lists using Reciprocal Rank Fusion (RRF).

    Formula:
        RRF_Score(d) = SUM_m [ 1.0 / (k + rank_m(d)) ]

    Args:
        ranked_lists: List of ordered lists of asset IDs.
        k: Smoothing constant (standard default is 60).

    Returns:
        Dict mapping asset_id to normalized RRF score.
    """
    scores: Dict[str, float] = {}

    for ranked_list in ranked_lists:
        for rank, item_id in enumerate(ranked_list, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + (1.0 / (k + rank))

    # Normalize max score to 1.0 if any scores exist
    if scores:
        max_score = max(scores.values())
        if max_score > 0:
            for item_id in scores:
                scores[item_id] = round(scores[item_id] / max_score, 4)

    return scores

