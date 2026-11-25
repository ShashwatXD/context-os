"""The CI quality gate: every code-only layer must stay above its threshold on the hand-labeled cases."""

import pytest

from contextos.evals.run import THRESHOLDS, gate, run


@pytest.fixture(scope="module")
def report():
    return run()


def test_quality_gate(report):
    assert gate(report) == []


@pytest.mark.parametrize(("layer", "metric"), list(THRESHOLDS))
def test_each_threshold(report, layer, metric):
    assert report[layer][metric] >= THRESHOLDS[(layer, metric)]


def test_identity_never_merges_two_people(report):
    assert report["identity"]["fp"] == 0
