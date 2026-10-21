from __future__ import annotations

import pytest
from app.demo import SCENARIOS, run_all, run_scenario, seed_manifest


def test_seed_manifest_is_synthetic_and_complete() -> None:
    manifest = seed_manifest()

    assert manifest["synthetic_only"] is True
    assert set(manifest["scenarios"]) == set(SCENARIOS)
    assert manifest["thresholds"] == {"auto_submit": 0.85, "review": 0.60}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_phase10_scenario_has_expected_acceptance_evidence(scenario: str) -> None:
    evidence = run_scenario(scenario)

    assert evidence["scenario"] == scenario
    assert evidence["synthetic_only"] is True
    assert evidence["audit_events"] >= 1
    if scenario != "D2":
        assert evidence["message_count"] >= 1

    if scenario == "A":
        assert evidence["status"] == "COMPLETED"
        assert evidence["confidence"] >= 0.85
        assert evidence["portal_reference"]
    elif scenario == "B":
        assert evidence["status"] == "COMPLETED"
        assert evidence["portal_reference"]
    elif scenario == "C":
        assert evidence["status"] == "COMPLETED"
        assert 0.60 <= evidence["confidence"] < 0.85
    elif scenario == "D1":
        assert evidence["status"] == "COMPLETED"
        assert evidence["portal_attempts"] == 2
    elif scenario == "D2":
        assert evidence["status"] == "NEEDS_REVIEW"
        assert evidence["portal_attempts"] == 1
    elif scenario == "E":
        assert evidence["status"] == "COMPLETED"
        assert evidence["question_count"] == 1


def test_run_all_preserves_demo_order() -> None:
    assert [item["scenario"] for item in run_all()] == list(SCENARIOS)
