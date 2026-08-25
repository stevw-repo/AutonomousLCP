"""ADR 0074/0075 complete HKEX conformance-universe contract tests."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Protocol

import pytest
from asklegal_contracts import parse_json_bytes
from asklegal_contracts.json_types import JsonValue
from asklegal_legal_desks import (
    HKEX_CONFORMANCE_CASE_COUNT,
    HKEX_CONFORMANCE_COVERAGE_CELL_COUNT,
    HKEX_CONFORMANCE_DESIGN_SOURCE_FINGERPRINT,
    HKEX_CONFORMANCE_PAIR_COUNT,
    HKEXConformanceError,
    HKEXConformanceErrorCode,
    HKEXConformanceLayer,
    validate_hkex_conformance_universe,
)
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1] / "src/asklegal_legal_desks/_hk_regulatory_package"
)
CATALOGUE_PATH = PACKAGE_ROOT / "catalogues/conformance-universe.json"
SCHEMA_PATH = PACKAGE_ROOT / "contracts/schemas/hkex-conformance-universe.schema.json"
DESIGN_PATH = ROOT / "docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md"


class _ObjectValidator(Protocol):
    def validate(self, instance: object) -> None:
        """Validate one JSON-compatible instance or raise."""


def test_frozen_universe_has_all_284_cases_cells_and_57_complete_pairs() -> None:
    document = _document()
    schema = _json_object(parse_json_bytes(SCHEMA_PATH.read_bytes(), max_bytes=2_000_000))
    Draft202012Validator.check_schema(schema)
    _validator(schema).validate(document)

    proof = validate_hkex_conformance_universe(document)

    assert proof.case_count == HKEX_CONFORMANCE_CASE_COUNT == 284
    assert proof.coverage_cell_count == HKEX_CONFORMANCE_COVERAGE_CELL_COUNT == 284
    assert proof.pair_count == HKEX_CONFORMANCE_PAIR_COUNT == 57
    assert (
        sum(case.layer is HKEXConformanceLayer.EVIDENCE_TO_DECISION for case in proof.cases) == 143
    )
    assert (
        sum(case.layer is HKEXConformanceLayer.DECISION_TO_ARTIFACT for case in proof.cases) == 141
    )
    assert proof.cases[0].case_id == "HKREG-DEC-SRC-001"
    assert proof.cases[-1].case_id == "HKREG-DET-PKG-038"
    assert proof.pair_index[0].pair_id == "HKREG-PAIR-001"
    assert proof.pair_index[-1].pair_id == "HKREG-PAIR-057"
    assert proof.all_case_identities_contiguous
    assert proof.every_case_has_one_primary_cell
    assert proof.every_pair_complete
    assert proof.case_packages_complete
    assert not proof.conformance_ready
    assert not proof.activation_authorized
    assert proof.external_effects == "NONE"


def test_universe_binds_the_exact_accepted_design_bytes() -> None:
    actual = f"sha256:{sha256(DESIGN_PATH.read_bytes()).hexdigest()}"
    proof = validate_hkex_conformance_universe(_document())

    assert actual == HKEX_CONFORMANCE_DESIGN_SOURCE_FINGERPRINT
    assert proof.design_source_fingerprint == actual
    assert proof.catalogue_fingerprint.startswith("sha256:")


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("REMOVE_CASE", HKEXConformanceErrorCode.ARITHMETIC),
        ("CHANGE_CASE_ID", HKEXConformanceErrorCode.CONTRACT),
        ("CHANGE_LAYER", HKEXConformanceErrorCode.CONTRACT),
        ("REMOVE_PAIR", HKEXConformanceErrorCode.PAIR),
        ("CHANGE_PAIR_MEMBER", HKEXConformanceErrorCode.CONTRACT),
        ("CHANGE_DESIGN_FINGERPRINT", HKEXConformanceErrorCode.SOURCE),
        ("CLAIM_CASE_PACKAGES_INCOMPLETE", HKEXConformanceErrorCode.CONTRACT),
        ("ADD_FIELD", HKEXConformanceErrorCode.CONTRACT),
    ],
)
def test_universe_rejects_incomplete_misbound_or_authority_broadening_mutations(
    mutation: str,
    code: HKEXConformanceErrorCode,
) -> None:
    document = _document()
    cases = _json_array(document["cases"])
    pairs = _json_array(document["pair_index"])
    if mutation == "REMOVE_CASE":
        cases.pop()
    elif mutation == "CHANGE_CASE_ID":
        _json_object(cases[0])["case_id"] = "HKREG-DEC-SRC-999"
    elif mutation == "CHANGE_LAYER":
        _json_object(cases[0])["layer"] = "DECISION_TO_ARTIFACT"
    elif mutation == "REMOVE_PAIR":
        pairs.pop()
    elif mutation == "CHANGE_PAIR_MEMBER":
        _json_object(pairs[0])["positive_case_id"] = "HKREG-DEC-SRC-002"
    elif mutation == "CHANGE_DESIGN_FINGERPRINT":
        document["design_source_fingerprint"] = f"sha256:{'0' * 64}"
    elif mutation == "CLAIM_CASE_PACKAGES_INCOMPLETE":
        document["case_packages_complete"] = False
    elif mutation == "ADD_FIELD":
        document["undeclared"] = False

    with pytest.raises(HKEXConformanceError) as failure:
        validate_hkex_conformance_universe(document)
    assert failure.value.code is code


def test_pair_roles_are_derived_from_cases_and_cannot_duplicate() -> None:
    document = _document()
    cases = _json_array(document["cases"])
    first = _json_object(cases[0])
    memberships = _json_array(first["pair_memberships"])
    memberships.append(_json_object(memberships[0]).copy())

    with pytest.raises(HKEXConformanceError) as duplicate:
        validate_hkex_conformance_universe(document)
    assert duplicate.value.code is HKEXConformanceErrorCode.PAIR


def _document() -> dict[str, JsonValue]:
    return _json_object(parse_json_bytes(CATALOGUE_PATH.read_bytes(), max_bytes=2_000_000))


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _json_array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _validator(schema: dict[str, JsonValue]) -> _ObjectValidator:
    return Draft202012Validator(schema)
