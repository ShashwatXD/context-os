"""Entity Resolution Matcher: Lexical, Canonical and Fuzzy Comparison."""

import re
from typing import Set, Tuple


ABBREVIATIONS = {
    "mrr": "monthly_recurring_revenue",
    "arr": "annual_recurring_revenue",
    "rev": "revenue",
    "cust": "customer",
    "fct": "fact",
    "dim": "dimension",
    "stg": "staging",
    "sub": "subscription",
}

PREFIXES_TO_STRIP = ("fct_", "dim_", "stg_", "tbl_", "vw_", "raw_")
SUFFIXES_TO_STRIP = ("_view", "_table", "_metric", "_summary", "_report")


def canonicalize_name(name: str) -> str:
    """Normalizes an asset or metric name to a canonical semantic representation."""
    cleaned = name.lower().strip()
    # Replace non-alphanumeric with underscores
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")

    # Strip standard data warehouse prefixes
    for prefix in PREFIXES_TO_STRIP:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    # Strip suffixes
    for suffix in SUFFIXES_TO_STRIP:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break

    # Expand common abbreviations
    tokens = cleaned.split("_")
    expanded_tokens = [ABBREVIATIONS.get(t, t) for t in tokens if t]
    return "_".join(expanded_tokens)


def token_similarity_metrics(str_a: str, str_b: str) -> Tuple[float, float]:
    """Computes Jaccard similarity and token containment ratio."""
    tokens_a: Set[str] = set(canonicalize_name(str_a).split("_"))
    tokens_b: Set[str] = set(canonicalize_name(str_b).split("_"))

    if not tokens_a or not tokens_b:
        return 0.0, 0.0

    intersection = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    jaccard = len(intersection) / len(union)

    # Containment: proportion of smaller token set contained in the larger set
    min_len = min(len(tokens_a), len(tokens_b))
    containment = len(intersection) / min_len if min_len > 0 else 0.0

    return jaccard, containment


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Computes normalized Levenshtein similarity ratio between two strings."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    len1, len2 = len(s1), len(s2)
    matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]

    for i in range(len1 + 1):
        matrix[i][0] = i
    for j in range(len2 + 1):
        matrix[0][j] = j

    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,      # deletion
                matrix[i][j - 1] + 1,      # insertion
                matrix[i - 1][j - 1] + cost # substitution
            )

    dist = matrix[len1][len2]
    max_len = max(len1, len2)
    return 1.0 - (dist / max_len)


def calculate_match_confidence(name_a: str, name_b: str) -> Tuple[float, str]:
    """Calculates match confidence and provides reasoning.

    Returns:
        (confidence_score: float, match_reason: str)
    """
    if name_a.strip().lower() == name_b.strip().lower():
        return (1.0, "Exact lexical match")

    canon_a = canonicalize_name(name_a)
    canon_b = canonicalize_name(name_b)

    if canon_a == canon_b:
        return (0.95, f"Canonical normalized equality ('{canon_a}')")

    jaccard, containment = token_similarity_metrics(name_a, name_b)
    lev = levenshtein_ratio(canon_a, canon_b)

    # Composite score: Jaccard, Token containment (subset overlap), and Levenshtein edit proximity
    combined = (jaccard * 0.35) + (containment * 0.35) + (lev * 0.30)

    if combined >= 0.85:
        return (round(combined, 2), "High token overlap and edit proximity")
    elif combined >= 0.70:
        return (round(combined, 2), "Moderate lexical proximity (suggest review)")
    else:
        return (round(combined, 2), "Low semantic correlation")
