"""Unit tests for Entity Resolution Matcher and Canonicalization."""

from app.application.entity_resolution.matcher import (
    canonicalize_name,
    calculate_match_confidence,
    levenshtein_ratio,
    token_similarity_metrics,
)


def test_canonicalize_name_prefix_and_abbreviations():
    assert canonicalize_name("fct_monthly_revenue") == "monthly_revenue"
    assert canonicalize_name("dim_customers") == "customers"
    assert canonicalize_name("stg_stripe_charges") == "stripe_charges"
    assert canonicalize_name("fct_mrr") == "monthly_recurring_revenue"
    assert canonicalize_name("Revenue Monthly") == "revenue_monthly"


def test_exact_match_confidence():
    score, reason = calculate_match_confidence("monthly_revenue", "monthly_revenue")
    assert score == 1.0
    assert "Exact" in reason


def test_canonical_match_confidence():
    # 'fct_monthly_revenue' and 'monthly_revenue' normalize to 'monthly_revenue'
    score, reason = calculate_match_confidence("fct_monthly_revenue", "monthly_revenue")
    assert score == 0.95
    assert "Canonical normalized" in reason


def test_acronym_canonical_match():
    # 'fct_mrr' normalizes to 'monthly_recurring_revenue'
    score, reason = calculate_match_confidence("fct_mrr", "monthly_recurring_revenue")
    assert score >= 0.90


def test_moderate_confidence_triggers_review():
    # 'Monthly Billed Revenue' vs 'Monthly Revenue'
    score, reason = calculate_match_confidence("Monthly Billed Revenue", "monthly_revenue")
    assert 0.70 <= score < 0.90
    assert "suggest review" in reason or "proximity" in reason


def test_low_confidence_discarded():
    score, reason = calculate_match_confidence("customer_churn", "stripe_charges")
    assert score < 0.50
