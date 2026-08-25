"""ADR 0061/0063/0064/0067/0068 deterministic Cases admission tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks import (
    HKCaseAdmissionError,
    evaluate_hk_case_admission,
    hk_case_admission_request_document,
    hk_case_admission_request_from_document,
    hk_case_admission_result_document,
    hk_case_frozen_case_ids,
    hk_case_frozen_catalogue_fingerprint,
    hk_case_frozen_coverage_cell_ids,
    hk_case_frozen_pair_memberships,
)
from jsonschema import Draft202012Validator

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_cases_package"


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def _json(path: Path) -> dict[str, JsonValue]:
    value = checked_json_value(json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(value, dict)
    return value


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _objects(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [_object(item) for item in value]


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _texts(value: JsonValue) -> list[str]:
    assert isinstance(value, list)
    return [_text(item) for item in value]


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)


def _case(number: int) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    name = f"HKCASE-PROP-DET-ADM-{number:03d}.json"
    return (
        _json(PACKAGE_ROOT / f"fixtures/deterministic/admission/{name}"),
        _json(PACKAGE_ROOT / f"expected/admission/{name}"),
    )


def _execute(number: int) -> list[dict[str, JsonValue]]:
    fixture, expected = _case(number)
    fixture_variants = _objects(fixture["variants"])
    expected_variants = _objects(expected["variants"])
    assert [item["variant_id"] for item in fixture_variants] == [
        item["variant_id"] for item in expected_variants
    ]
    results: list[dict[str, JsonValue]] = []
    for fixture_variant, expected_variant in zip(
        fixture_variants,
        expected_variants,
        strict=True,
    ):
        request = hk_case_admission_request_from_document(fixture_variant["request"])
        result = hk_case_admission_result_document(evaluate_hk_case_admission(request))
        assert result == expected_variant["result"]
        assert result["workflow_admission_created"] is False
        assert result["provider_calls_authorized"] is False
        assert result["deployment_authorized"] is False
        assert result["search_records_created"] == 0
        assert result["release_eligible"] is False
        assert result["external_effects"] == "NONE"
        results.append(result)
    return results


def test_all_eighteen_frozen_admission_cases_validate_and_execute() -> None:
    schema_root = PACKAGE_ROOT / "contracts/schemas"
    case_schema = _json(schema_root / "hk-case-admission-case.schema.json")
    result_schema = _json(schema_root / "hk-case-admission-case-result.schema.json")
    Draft202012Validator.check_schema(case_schema)
    Draft202012Validator.check_schema(result_schema)
    case_validator = _validator(case_schema)
    result_validator = _validator(result_schema)
    observed: set[str] = set()
    for number in range(1, 19):
        fixture, expected = _case(number)
        case_validator.validate(fixture)
        result_validator.validate(expected)
        observed.update(_text(item["outcome"]) for item in _execute(number))
    assert observed == {
        "ELIGIBLE_FOR_WORKFLOW_ADMISSION",
        "FORBIDDEN_SIDE_EFFECT",
        "INVALID",
        "NOT_ADMITTED",
        "VALIDATED",
    }


def test_request_round_trip_is_strict_and_shape_fails_closed() -> None:
    fixture, _ = _case(1)
    request_document = _object(_objects(fixture["variants"])[0]["request"])
    request = hk_case_admission_request_from_document(request_document)
    assert hk_case_admission_request_document(request) == request_document
    request_document["unknown"] = True
    with pytest.raises(HKCaseAdmissionError):
        hk_case_admission_request_from_document(request_document)

    fixture, _ = _case(8)
    request_document = _object(_objects(fixture["variants"])[0]["request"])
    request_document["assertion"] = "WORKFLOW_IDENTITY"
    malformed_shape = hk_case_admission_request_from_document(request_document)
    result = hk_case_admission_result_document(evaluate_hk_case_admission(malformed_shape))
    assert result["outcome"] == "INVALID"
    assert result["reasons"] == ["PACKAGE_SHAPE_INVALID"]


def test_unchanged_reprocessing_reuses_record_and_embedding_with_new_history() -> None:
    result = _execute(1)[0]
    assert result["outcome"] == "VALIDATED"
    assert result["reused_record_ids"] == ["record_1"]
    assert result["reused_embedding_fingerprints"] == [f"sha256:{'b' * 64}"]
    assert result["new_official_version_required"] is False
    assert result["new_ledger_required"] is True
    assert result["processing_history_appended"] is True
    assert result["ledger_history_appended"] is True


def test_official_correction_creates_forward_successor_consequence() -> None:
    result = _execute(2)[0]
    assert result["new_official_version_required"] is True
    assert result["deselected_prior_record_ids"] == ["record_1"]
    lineage = _objects(result["lineages"])[0]
    assert lineage == {
        "relation": "FORWARD_SUCCESSOR",
        "predecessor_record_ids": ["record_1"],
        "successor_record_ids": ["record_2"],
    }


def test_split_merge_and_new_discovery_preserve_exact_lineage_boundary() -> None:
    split = _execute(3)[0]
    merge = _execute(4)[0]
    new = _execute(5)[0]
    assert _objects(split["lineages"])[0]["relation"] == "SPLIT_FROM"
    assert split["deselected_prior_record_ids"] == ["record_combined"]
    assert _objects(merge["lineages"])[0]["relation"] == "MERGED_FROM"
    assert merge["deselected_prior_record_ids"] == ["record_a", "record_b"]
    assert new["lineages"] == []
    assert "record_new" in _texts(new["selected_current_record_ids"])


def test_partial_correction_reuses_only_the_exact_unaffected_record() -> None:
    result = _execute(6)[0]
    assert result["new_official_version_required"] is True
    assert result["reused_record_ids"] == ["record_unchanged"]
    assert result["selected_current_record_ids"] == [
        "record_unchanged",
        "record_successor",
    ]
    assert result["deselected_prior_record_ids"] == ["record_affected"]


def test_component_change_requires_complete_evaluation_without_mutating_history() -> None:
    result = _execute(7)[0]
    assert result["outcome"] == "VALIDATED"
    assert result["complete_evaluation_required"] is True
    assert result["new_official_version_required"] is False
    assert result["new_ledger_required"] is False
    assert result["workflow_admission_created"] is False


def test_complete_catalogue_is_exact_132_cells_and_31_two_role_pairs() -> None:
    assert len(hk_case_frozen_case_ids()) == 132
    assert len(hk_case_frozen_coverage_cell_ids()) == 132
    memberships = hk_case_frozen_pair_memberships()
    assert len(memberships) == 62
    assert {item.pair_id for item in memberships} == {
        f"HKCASE-PROP-PAIR-{number:03d}" for number in range(1, 32)
    }
    valid = _execute(8)[0]
    assert valid["catalogue_fingerprint"] == hk_case_frozen_catalogue_fingerprint()
    assert all(item["outcome"] == "INVALID" for item in _execute(9))


def test_packet_non_leakage_accepts_runtime_facts_and_rejects_every_hidden_field() -> None:
    assert _execute(10)[0]["outcome"] == "VALIDATED"
    leaked = _execute(11)
    assert [item["leakage_fields"] for item in leaked] == [
        ["case_title"],
        ["expected_answer"],
        ["coverage_cell_id"],
        ["pair_role"],
        ["score"],
        ["critical_error_tag"],
    ]
    assert all(item["outcome"] == "INVALID" for item in leaked)


def test_sealed_package_requires_exact_registered_artifacts_and_manifest() -> None:
    valid = _execute(12)[0]
    assert valid["outcome"] == "VALIDATED"
    assert valid["sealed_package_fingerprint"] is not None
    invalid = _execute(13)
    assert len(invalid) == 3
    assert all(item["outcome"] == "INVALID" for item in invalid)
    assert all(item["sealed_package_fingerprint"] is None for item in invalid)


def test_two_runs_must_preserve_bytes_inventory_order_and_fingerprint() -> None:
    valid = _execute(14)[0]
    assert valid["outcome"] == "VALIDATED"
    assert valid["deterministic_artifact_fingerprint"] is not None
    invalid = _execute(15)
    assert len(invalid) == 4
    assert all(item["outcome"] == "INVALID" for item in invalid)
    assert all("DETERMINISTIC_ARTIFACT_DRIFT" in _texts(item["reasons"]) for item in invalid)


def test_every_forbidden_capability_attempt_fails_before_mutation() -> None:
    result = _execute(16)[0]
    assert result["outcome"] == "FORBIDDEN_SIDE_EFFECT"
    assert set(_texts(result["attempted_capabilities"])) == {
        "AZURE",
        "CREDENTIAL",
        "EMBEDDING",
        "MODEL",
        "NETWORK",
        "PINECONE",
        "PRODUCTION_STORE",
        "ROUTING",
        "SOURCE",
        "UNDECLARED_FILE",
    }
    assert result["mutations_performed"] == 0


def test_exact_workflow_is_only_eligible_and_drift_requires_full_evaluation() -> None:
    valid = _execute(17)[0]
    assert valid["outcome"] == "ELIGIBLE_FOR_WORKFLOW_ADMISSION"
    assert valid["workflow_admission_eligible"] is True
    assert valid["workflow_admission_created"] is False
    invalid = _execute(18)[0]
    assert invalid["outcome"] == "NOT_ADMITTED"
    assert invalid["changed_workflow_component_roles"] == ["PARSER_PROFILE"]
    assert invalid["complete_evaluation_required"] is True
    assert invalid["impact_declaration_required"] is True


def test_admission_catalogue_has_exact_ids_cells_pairs_and_checkpoint_boundary() -> None:
    catalogue = _json(PACKAGE_ROOT / "catalogues/admission-cases.json")
    entries = _objects(catalogue["entries"])
    assert catalogue["case_count"] == catalogue["coverage_cell_count"] == len(entries) == 18
    assert [item["case_id"] for item in entries] == [
        f"HKCASE-PROP-DET-ADM-{number:03d}" for number in range(1, 19)
    ]
    assert catalogue["deterministic_case_count"] == 54
    assert catalogue["deterministic_checkpoint_complete"] is True
    assert catalogue["full_proposition_suite_complete"] is False
    assert catalogue["real_source_evidence"] is False
    assert catalogue["workflow_admission_created"] is False
    assert catalogue["activation_authorized"] is False
