"""Phase 1 contract tests for the deterministic rules engine.

These tests intentionally use only synthetic facts and target the planned
public API.  The implementation may represent outcomes and trace entries as
Pydantic models, dataclasses, dictionaries, literals, or enums; the small
access helpers keep the assertions focused on the public behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from app.rules.engine import (
    DecisionOutcome,
    RuleStatus,
    SchemeValidationError,
    evaluate,
    load_scheme,
    load_schemes,
)

SCHEMES = Path(__file__).parents[1] / "app" / "rules" / "schemes"


def _field(value: Any, name: str) -> Any:
    """Read a public field from either a model/dataclass or a mapping."""

    if isinstance(value, Mapping):
        return value[name]
    return getattr(value, name)


def _value(value: Any) -> Any:
    """Normalize a literal or enum member to the value used by the contract."""

    return getattr(value, "value", value)


def _loaded_schemes(value: Any) -> dict[str, Any]:
    """Normalize the supported collection shape returned by ``load_schemes``."""

    schemes = value.values() if isinstance(value, Mapping) else value
    return {_field(scheme, "scheme_id"): scheme for scheme in schemes}


def _facts_for(scheme_id: str, *, include_declaration: bool = True) -> dict[str, Any]:
    """Return passing synthetic facts, using mappings for document provenance."""

    if scheme_id == "pm_kisan_mock":
        facts: dict[str, Any] = {
            "land_owned_hectares": {
                "value": 2.5,
                "source_doc_id": "synthetic-land-record-001",
            },
            "holder_type": {
                "value": "individual",
                "source_doc_id": "synthetic-land-record-001",
            },
        }
        if include_declaration:
            facts["is_income_tax_payer"] = False
        return facts

    if scheme_id == "state_scholarship_mock":
        facts = {
            "family_income_annual": {
                "value": 100000,
                "source_doc_id": "synthetic-income-certificate-001",
            },
            "last_exam_percentage": {
                "value": 82.5,
                "source_doc_id": "synthetic-marksheet-001",
            },
        }
        if include_declaration:
            facts["institution_recognized"] = True
        return facts

    raise AssertionError(f"unknown synthetic scheme: {scheme_id}")


@pytest.mark.parametrize(
    (
        "file_name",
        "scheme_id",
        "required_documents",
        "payload_fields",
        "declaration_key",
        "question",
    ),
    [
        (
            "pm_kisan_mock.yaml",
            "pm_kisan_mock",
            {"aadhaar", "land_record", "bank_passbook"},
            {"applicant_name", "aadhaar_last4", "bank_account_number", "bank_ifsc"},
            "is_income_tax_payer",
            "Does anyone in your family pay income tax?",
        ),
        (
            "state_scholarship_mock.yaml",
            "state_scholarship_mock",
            {"aadhaar", "income_certificate", "marksheet", "bonafide_certificate"},
            {"applicant_name", "aadhaar_last4", "bank_account_number", "bank_ifsc"},
            "institution_recognized",
            "Is your educational institution recognized?",
        ),
    ],
)
def test_mock_scheme_loads_with_declared_inputs_and_mock_labels(
    file_name: str,
    scheme_id: str,
    required_documents: set[str],
    payload_fields: set[str],
    declaration_key: str,
    question: str,
) -> None:
    scheme = load_scheme(SCHEMES / file_name)

    assert _field(scheme, "scheme_id") == scheme_id
    assert "MOCK" in _field(scheme, "name").upper()
    assert "MOCK" in _field(scheme, "benefit").upper()
    assert set(_field(scheme, "required_documents")) == required_documents
    assert {
        _field(field, "key") for field in _field(scheme, "payload_fields")
    } == payload_fields

    declaration_facts = [
        fact
        for fact in _field(scheme, "facts")
        if _field(fact, "source") == "declaration"
    ]
    assert len(declaration_facts) == 1
    declaration = declaration_facts[0]
    assert _field(declaration, "key") == declaration_key
    assert _field(declaration, "question") == question


def test_load_schemes_discovers_both_mock_schemes() -> None:
    schemes = _loaded_schemes(load_schemes(SCHEMES))

    assert set(schemes) == {"pm_kisan_mock", "state_scholarship_mock"}


@pytest.mark.parametrize("scheme_id", ["pm_kisan_mock", "state_scholarship_mock"])
def test_passing_facts_are_eligible(scheme_id: str) -> None:
    scheme = load_scheme(SCHEMES / f"{scheme_id}.yaml")

    decision = evaluate(scheme, _facts_for(scheme_id))

    assert _value(_field(decision, "outcome")) == _value(DecisionOutcome.ELIGIBLE)


@pytest.mark.parametrize(
    ("scheme_id", "overrides"),
    [
        ("pm_kisan_mock", {"land_owned_hectares": 0}),
        ("pm_kisan_mock", {"holder_type": "institutional"}),
        ("pm_kisan_mock", {"is_income_tax_payer": True}),
        ("state_scholarship_mock", {"family_income_annual": 250001}),
        ("state_scholarship_mock", {"last_exam_percentage": 74.9}),
        ("state_scholarship_mock", {"institution_recognized": False}),
    ],
)
def test_definitively_failing_rule_is_not_eligible(
    scheme_id: str, overrides: dict[str, Any]
) -> None:
    facts = _facts_for(scheme_id)
    for key, value in overrides.items():
        if key in {
            "land_owned_hectares",
            "holder_type",
            "family_income_annual",
            "last_exam_percentage",
        }:
            facts[key] = {"value": value, "source_doc_id": f"synthetic-{key}-001"}
        else:
            facts[key] = value

    decision = evaluate(load_scheme(SCHEMES / f"{scheme_id}.yaml"), facts)

    assert _value(_field(decision, "outcome")) == _value(DecisionOutcome.NOT_ELIGIBLE)


@pytest.mark.parametrize("scheme_id", ["pm_kisan_mock", "state_scholarship_mock"])
def test_missing_declaration_fact_is_undetermined(scheme_id: str) -> None:
    decision = evaluate(
        load_scheme(SCHEMES / f"{scheme_id}.yaml"),
        _facts_for(scheme_id, include_declaration=False),
    )

    assert _value(_field(decision, "outcome")) == _value(DecisionOutcome.UNDETERMINED)
    trace = _field(decision, "trace")
    assert any(_value(_field(entry, "status")) == _value(RuleStatus.UNKNOWN) for entry in trace)


@pytest.mark.parametrize(
    ("scheme_id", "missing_fact"),
    [
        ("pm_kisan_mock", "land_owned_hectares"),
        ("state_scholarship_mock", "family_income_annual"),
    ],
)
def test_missing_document_fact_is_undetermined(
    scheme_id: str, missing_fact: str
) -> None:
    facts = _facts_for(scheme_id)
    facts.pop(missing_fact)

    decision = evaluate(load_scheme(SCHEMES / f"{scheme_id}.yaml"), facts)

    assert _value(_field(decision, "outcome")) == _value(DecisionOutcome.UNDETERMINED)
    unknown_entries = [
        entry
        for entry in _field(decision, "trace")
        if _value(_field(entry, "status")) == _value(RuleStatus.UNKNOWN)
    ]
    assert unknown_entries
    assert any(missing_fact in _field(entry, "reason") for entry in unknown_entries)


def test_rule_trace_contains_fields_and_document_provenance() -> None:
    decision = evaluate(
        load_scheme(SCHEMES / "pm_kisan_mock.yaml"),
        {
            "land_owned_hectares": {
                "value": 2.5,
                "source_doc_id": "synthetic-land-record-001",
            },
            "holder_type": {
                "value": "individual",
                "source_doc_id": "synthetic-land-record-001",
            },
            "is_income_tax_payer": False,
        },
    )

    trace = {_field(entry, "rule_id"): entry for entry in _field(decision, "trace")}
    assert set(trace) == {"owns_land", "individual_holder", "not_tax_payer"}
    for entry in trace.values():
        assert _field(entry, "rule_id")
        assert _value(_field(entry, "status")) in {
            _value(RuleStatus.PASSED),
            _value(RuleStatus.FAILED),
            _value(RuleStatus.UNKNOWN),
        }
        assert _field(entry, "facts_used")
        assert isinstance(_field(entry, "source_doc_ids"), list)
        assert _field(entry, "reason")

    assert _field(trace["owns_land"], "facts_used") == ["land_owned_hectares"]
    assert _field(trace["owns_land"], "source_doc_ids") == ["synthetic-land-record-001"]
    assert _field(trace["individual_holder"], "facts_used") == ["holder_type"]
    assert _field(trace["individual_holder"], "source_doc_ids") == ["synthetic-land-record-001"]
    assert _field(trace["not_tax_payer"], "facts_used") == ["is_income_tax_payer"]
    assert _field(trace["not_tax_payer"], "source_doc_ids") == []


def test_invalid_scheme_validation_raises_public_error(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("scheme_id: incomplete_mock\n", encoding="utf-8")

    with pytest.raises(SchemeValidationError):
        load_scheme(path)


def test_malicious_expression_is_rejected_without_execution(tmp_path: Path) -> None:
    marker = tmp_path / "expression-was-executed"
    path = tmp_path / "malicious.yaml"
    payload = {
        "scheme_id": "malicious_mock",
        "name": "Malicious MOCK",
        "version": 1,
        "benefit": "None (MOCK)",
        "required_documents": [],
        "facts": [{"key": "flag", "type": "bool", "source": "declaration", "question": "Flag?"}],
        "payload_fields": [],
        "rules": [
            {
                "id": "injected",
                "expr": f"__import__('pathlib').Path({str(marker)!r}).write_text('owned')",
                "fail_reason": "injected expression should never run",
            }
        ],
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(SchemeValidationError):
        load_scheme(path)

    assert not marker.exists()
