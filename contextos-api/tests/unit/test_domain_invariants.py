"""Unit tests for ContextOS Domain Invariants and Integrity Rules."""

import pytest
from app.domain.entities.asset import Asset, AssetType, CertificationStatus, ColumnMetadata
from app.domain.entities.provenance import ProvenanceRecord
from app.domain.relationships.relationship import Relationship, RelationshipType
from app.domain.governance.approval import ApprovalRequest, ApprovalStatus, Suggestion, SuggestionType
from app.domain.agents.agent import AgentRun, RunStatus, SpanType, TraceSpan


def test_asset_creation_and_defaults():
    asset = Asset(
        id="ast_test_01",
        source_id="src_pg_01",
        external_id="public.users",
        name="users",
        qualified_name="warehouse.public.users",
        asset_type=AssetType.TABLE,
        columns=[
            ColumnMetadata(name="id", data_type="uuid", is_primary_key=True),
            ColumnMetadata(name="email", data_type="varchar", is_nullable=False),
        ],
    )
    assert asset.id == "ast_test_01"
    assert asset.certification_status == CertificationStatus.UNVERIFIED
    assert len(asset.columns) == 2
    assert asset.columns[0].is_primary_key is True


def test_relationship_self_loop_prohibited():
    """Invariant: An asset cannot have a relationship directed to itself."""
    with pytest.raises(ValueError, match="Self-referential loop prohibited"):
        Relationship(
            id="rel_invalid",
            source_asset_id="ast_01",
            target_asset_id="ast_01",
            relationship_type=RelationshipType.TRANSFORMS_TO,
        )


def test_relationship_valid_creation():
    rel = Relationship(
        id="rel_valid",
        source_asset_id="ast_tbl_charges",
        target_asset_id="ast_model_mrr",
        relationship_type=RelationshipType.TRANSFORMS_TO,
        confidence=0.98,
    )
    assert rel.source_asset_id != rel.target_asset_id
    assert rel.confidence == 0.98


def test_provenance_deterministic_hash():
    """Invariant: Provenance hashes must be deterministic and identical for equivalent payloads."""
    payload1 = {"query": "SELECT * FROM billing", "timestamp": "2026-11-04", "author": "etl"}
    payload2 = {"author": "etl", "query": "SELECT * FROM billing", "timestamp": "2026-11-04"}

    hash1 = ProvenanceRecord.compute_hash(payload1)
    hash2 = ProvenanceRecord.compute_hash(payload2)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256


def test_suggestion_and_approval_workflow_entities():
    sug = Suggestion(
        id="sug_01",
        asset_id="ast_tbl_charges",
        suggestion_type=SuggestionType.DESCRIPTION,
        proposed_value={"description": "Stripe transactions synced hourly."},
        reasoning="Extracted from stripe dbt doc block.",
        confidence=0.88,
    )
    assert sug.status == ApprovalStatus.PENDING_REVIEW

    req = ApprovalRequest(
        id="appr_01",
        suggestion_id=sug.id,
        action_type="UPDATE_DESCRIPTION",
        requested_by="agent:enricher_v1",
    )
    assert req.status == ApprovalStatus.PENDING_REVIEW
    assert req.reviewed_at is None


def test_trace_span_accounting():
    span = TraceSpan(
        id="sp_01",
        run_id="run_01",
        span_type=SpanType.CONTEXT_RETRIEVAL,
        name="HybridSearch",
        latency_ms=14.2,
        status="SUCCESS",
    )
    assert span.latency_ms == 14.2
    assert span.status == "SUCCESS"

