"""Hong Kong V1 Coverage Matrix contract tests."""

from __future__ import annotations

import gc
import weakref
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

import asklegal_reporting
import asklegal_reporting.hk_v1_coverage as coverage_module
import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_reporting.hk_v1_coverage import (
    CoverageMatrixRow,
    HongKongV1CoverageError,
    HongKongV1CoverageMatrix,
    HongKongV1ScopeGateResult,
    evaluate_hk_v1_scope_gate,
    is_hk_v1_coverage_matrix_policy_approved,
    load_hk_v1_coverage_matrix,
)
from asklegal_reporting.hk_v1_proposal_evidence import (
    VerifiedSemanticCapability,
    build_provider_disabled_profile_receipt,
    verify_provider_disabled_semantic_capability,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue


_REQUIRED_SCOPE_IDS = (
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-CASE-BINDING-POST-1997",
)
_REQUIRED_EXCLUSIONS = (
    "ASKLEGAL_ADMIN",
    "ASKLEGAL_ROUTING",
    "AZURE_APP_HOSTING",
    "FULL_JUDGMENTS_AS_RECORDS",
    "HK-CASE-PRE-1997",
    "HK-LEG-NPC-SOURCES",
    "HK-PRINCIPLES",
    "HKEX_NON_LISTING_RULE_GUIDANCE",
    "HKEX_REGULATORY_POST_V1",
)
_LEGISLATION_SHARED_SOURCE_IDS = frozenset(
    {
        "HK-LEG-GLD-EGAZETTE",
        "HK-LEG-HKEL-ASSISTED-COPIES",
        "HK-LEG-HKEL-CURRENT-DATA",
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        "HK-LEG-HKEL-EDITORIAL-RECORDS",
        "HK-LEG-HKEL-GAZETTE-BACKCAPTURE",
        "HK-LEG-HKEL-PAST-DATA",
        "HK-LEG-HKEL-PAST-INVENTORY",
        "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        "HK-LEG-HKEL-VERIFIED-COPIES",
        "HK-LEG-OFFICIAL-GAZETTE-ARCHIVE",
    }
)
_LEGISLATION_CONSTITUTIONAL_SOURCE_IDS = frozenset(
    {
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
        "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS",
    }
)
_CASES_SOURCE_IDS = frozenset(
    {
        "HK-CASE-COURT-REGISTRY",
        "HK-CASE-HKLII-DISCOVERY",
        "HK-CASE-JUDICIARY-JUDGMENT",
        "HK-CASE-JUDICIARY-LIBRARY",
        "HK-CASE-JUDICIARY-LRS-INVENTORY",
        "HK-CASE-JUDICIARY-TRANSLATION",
        "HK-CASE-PRIVY-COUNCIL",
    }
)
_SOURCE_IDS_BY_SCOPE = {
    "HK-LEG-ORDINANCES": _LEGISLATION_SHARED_SOURCE_IDS,
    "HK-LEG-SUBSIDIARY": _LEGISLATION_SHARED_SOURCE_IDS,
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS": (
        _LEGISLATION_SHARED_SOURCE_IDS | _LEGISLATION_CONSTITUTIONAL_SOURCE_IDS
    ),
    "HK-CASE-BINDING-POST-1997": _CASES_SOURCE_IDS,
}
_REQUIRED_SCOPE_SOURCE_PAIRS = tuple(
    sorted(
        (scope_id, source_id)
        for scope_id, source_ids in _SOURCE_IDS_BY_SCOPE.items()
        for source_id in source_ids
    )
)
_PRIVY_COUNCIL_PAIR = ("HK-CASE-BINDING-POST-1997", "HK-CASE-PRIVY-COUNCIL")
_PRIVY_COUNCIL_CUTOFF_RULE = "DECISION_DATE_ON_OR_AFTER_1997-07-01_AND_PUBLISHED_BY_CYCLE_CUTOFF"
_PRIVY_COUNCIL_LIMITATION = (
    "Excluded because V1 begins on 1997-07-01; no Privy Council material is included."
)
_NPC_SOURCE_IDS = frozenset(
    {
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
        "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS",
    }
)
_NPC_SCOPE_ID = "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS"
_NPC_EXCLUSION_CODE = "HK-LEG-NPC-SOURCES"
_NPC_LIMITATION = "Outside V1; retained only as dormant legal/evidence vocabulary."
_EXCLUDED_PAIRS = frozenset(
    {
        _PRIVY_COUNCIL_PAIR,
        *((_NPC_SCOPE_ID, source_id) for source_id in _NPC_SOURCE_IDS),
    }
)
_DEFAULT_MATRIX_PATH = Path(coverage_module.__file__).with_name("hk_v1_coverage_matrix.json")


def _issued_capability(
    kind: str, profile_fingerprint: str, cutoff: str
) -> VerifiedSemanticCapability:
    application, role = {
        "MODEL": ("LEGAL_PROCESSING_WORKER", "generative_llm_provider"),
        "EMBEDDING": ("PROMOTION_WORKER", "embedding_provider"),
    }[kind]
    profile_body = {
        "schema_id": "asklegal.hk-v1-provider-disabled-profile-receipt/v1",
        "capability": kind,
        "issuer_application": application,
        "profile_fingerprint": profile_fingerprint,
        "status": "PROVIDER_DISABLED_PREPARATION_ONLY",
    }
    profile_fingerprint_value = (
        "sha256:" + sha256(canonicalize(checked_json_value(profile_body))).hexdigest()
    )
    profile_content = canonicalize(
        checked_json_value({**profile_body, "fingerprint": profile_fingerprint_value})
    )
    profile_ref = (
        f"proposal-readiness/profile-receipts/{kind.lower()}/"
        f"{profile_fingerprint.removeprefix('sha256:')}.json"
    )
    evidence_body = {
        "schema_id": "asklegal.hk-v1-provider-disabled-capability-evidence/v1",
        "capability": kind,
        "application": application,
        "role": role,
        "observation_cutoff": cutoff,
        "profile_receipt_ref": profile_ref,
        "profile_receipt_fingerprint": profile_fingerprint_value,
        "profile_fingerprint": profile_fingerprint,
        "status": "PROVIDER_DISABLED_PREPARATION_ONLY",
    }
    evidence_fingerprint = (
        "sha256:" + sha256(canonicalize(checked_json_value(evidence_body))).hexdigest()
    )
    evidence_content = canonicalize(
        checked_json_value({**evidence_body, "fingerprint": evidence_fingerprint})
    )
    evidence_ref = (
        f"proposal-readiness/capability-evidence/{kind.lower()}/"
        f"{evidence_fingerprint.removeprefix('sha256:')}.json"
    )
    return verify_provider_disabled_semantic_capability(
        kind,
        profile_ref,
        profile_content,
        evidence_ref,
        evidence_content,
        cutoff,
    )


def _unissued_capability(
    kind: str, profile_fingerprint: str, evidence_ref: str
) -> VerifiedSemanticCapability:
    value = object.__new__(VerifiedSemanticCapability)
    for name, item in (
        ("capability", kind),
        ("profile_fingerprint", profile_fingerprint),
        ("profile_receipt_ref", "proposal-readiness/profile-receipts/unissued.json"),
        ("profile_receipt_fingerprint", "sha256:" + "7" * 64),
        ("evidence_ref", evidence_ref),
        ("evidence_fingerprint", "sha256:" + "8" * 64),
        ("status", "PROVIDER_DISABLED_PREPARATION_ONLY"),
    ):
        object.__setattr__(value, name, item)
    return value


@pytest.mark.parametrize("kind", ["MODEL", "EMBEDDING"])
def test_shared_reporting_package_cannot_mint_capability_receipts_from_arbitrary_hashes(
    kind: str,
) -> None:
    """Mutation caught: a hash-shaped caller value cannot claim application issuance."""
    with pytest.raises(coverage_module.ProposalEvidenceError):
        build_provider_disabled_profile_receipt(kind, "sha256:" + "9" * 64)


def valid_matrix_document() -> dict[str, JsonValue]:
    """Return one hand-authored valid matrix document."""
    document: dict[str, JsonValue] = {
        "effective_date": "2026-08-25",
        "explicit_exclusions": ["HK-PRINCIPLES"],
        "included_material_families": ["CASES", "LEGISLATION"],
        "revision": "HK-V1-001",
        "rows": [
            {
                "cadence": "DAILY",
                "cutoff_rule": "CURRENT_AT_CYCLE_CUTOFF",
                "earliest_boundary": "1997-07-01",
                "exclusion_code": "",
                "fact_authority": "Hong Kong Judiciary",
                "limitation_text": "Binding case propositions only.",
                "material_family": "CASES",
                "outage_consequence": "RELEASE_BLOCKING",
                "owner": "ACQUISITION",
                "rights_state": "NOT_ADMITTED",
                "scope_id": "HK-CASE-BINDING-POST-1997",
                "source_id": "HK-CASE-JUDICIARY-LISTING",
                "technical_state": "NOT_ADMITTED",
            }
        ],
    }
    document["fingerprint"] = "sha256:" + sha256(canonicalize(document)).hexdigest()
    return document


def write_matrix(tmp_path: Path, document: dict[str, JsonValue]) -> Path:
    """Write one canonical matrix fixture to a temporary path."""
    path = tmp_path / "coverage-matrix.json"
    path.write_bytes(canonicalize(document))
    return path


def seal_matrix_document(document: dict[str, JsonValue]) -> None:
    """Replace the declared fingerprint after an intentional fixture change."""
    document.pop("fingerprint", None)
    document["fingerprint"] = "sha256:" + sha256(canonicalize(document)).hexdigest()


def load_default_matrix_document() -> dict[str, JsonValue]:
    """Read the checked-in JSON without using the production matrix loader."""
    document = parse_json_bytes(_DEFAULT_MATRIX_PATH.read_bytes(), max_bytes=1_000_000)
    assert isinstance(document, dict)
    return document


def admitted_placeholder_matrix_document() -> dict[str, JsonValue]:
    """Return the former six-row placeholder as a negative Gate A fixture."""
    document = valid_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    first_row = rows[0]
    assert isinstance(first_row, dict)
    first_row["technical_state"] = "ADMITTED"
    first_row["rights_state"] = "ADMITTED"
    for scope_id, material_family, source_id in (
        ("HK-LEG-ORDINANCES", "LEGISLATION", "HK-LEG-ORDINANCES-SOURCE"),
        ("HK-LEG-SUBSIDIARY", "LEGISLATION", "HK-LEG-SUBSIDIARY-SOURCE"),
        (
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
            "LEGISLATION",
            "HK-LEG-CONSTITUTIONAL-SOURCE",
        ),
    ):
        row = dict(first_row)
        row["scope_id"] = scope_id
        row["material_family"] = material_family
        row["source_id"] = source_id
        rows.append(row)
    document["explicit_exclusions"] = list(_REQUIRED_EXCLUSIONS)
    seal_matrix_document(document)
    return document


def complete_admitted_matrix_document() -> dict[str, JsonValue]:
    """Return an alternate same-revision document with all active rows admitted."""
    document = load_default_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        pair = (row["scope_id"], row["source_id"])
        if pair not in _EXCLUDED_PAIRS:
            row["technical_state"] = "ADMITTED"
            row["rights_state"] = "ADMITTED"
    seal_matrix_document(document)
    return document


def approved_new_revision_admitted_matrix_document() -> dict[str, JsonValue]:
    """Return an explicitly approved temporary default for the positive gate path."""
    document = complete_admitted_matrix_document()
    document["revision"] = "HK-V1-004"
    document["effective_date"] = "2026-09-03"
    seal_matrix_document(document)
    return document


def load_complete_admitted_matrix(tmp_path: Path) -> HongKongV1CoverageMatrix:
    """Load one integrity-checked but repository-unapproved matrix fixture."""
    return load_hk_v1_coverage_matrix(write_matrix(tmp_path, complete_admitted_matrix_document()))


def load_approved_temporary_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, JsonValue] | None = None,
) -> HongKongV1CoverageMatrix:
    """Install and load one explicit new-revision default for this test only."""
    approved_document = (
        approved_new_revision_admitted_matrix_document() if document is None else document
    )
    path = write_matrix(tmp_path, approved_document)
    monkeypatch.setattr(coverage_module, "_DEFAULT_MATRIX_PATH", path)
    return load_hk_v1_coverage_matrix()


def test_v1_matrix_includes_only_legislation_and_cases() -> None:
    """The repository default must freeze only the approved V1 scope."""
    matrix = load_hk_v1_coverage_matrix()

    assert matrix.included_material_families == ("CASES", "LEGISLATION")
    assert {row.material_family for row in matrix.rows} == {"LEGISLATION", "CASES"}
    assert {row.scope_id for row in matrix.rows} == {
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-CASE-BINDING-POST-1997",
    }
    assert "HKEX_REGULATORY_POST_V1" in matrix.explicit_exclusions
    assert all(
        row.earliest_boundary == "1997-07-01"
        for row in matrix.rows
        if row.material_family == "CASES"
    )


def test_default_matrix_freezes_the_complete_source_role_inventory() -> None:
    """Every approved source role must be bound to each scope it serves."""
    matrix = load_hk_v1_coverage_matrix()
    source_ids_by_scope = {
        scope_id: frozenset(row.source_id for row in matrix.rows if row.scope_id == scope_id)
        for scope_id in _REQUIRED_SCOPE_IDS
    }

    assert source_ids_by_scope["HK-LEG-ORDINANCES"] == _LEGISLATION_SHARED_SOURCE_IDS
    assert source_ids_by_scope["HK-LEG-SUBSIDIARY"] == _LEGISLATION_SHARED_SOURCE_IDS
    assert source_ids_by_scope["HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS"] == (
        _LEGISLATION_SHARED_SOURCE_IDS | _LEGISLATION_CONSTITUTIONAL_SOURCE_IDS
    )
    assert source_ids_by_scope["HK-CASE-BINDING-POST-1997"] == _CASES_SOURCE_IDS


def test_default_matrix_freezes_all_three_exact_excluded_rows() -> None:
    """Privy Council and both dormant NPC roles stay exact and visibly excluded."""
    matrix = load_hk_v1_coverage_matrix()
    privy_council_rows = [row for row in matrix.rows if row.source_id == "HK-CASE-PRIVY-COUNCIL"]
    npc_rows = [row for row in matrix.rows if row.source_id in _NPC_SOURCE_IDS]

    assert matrix.explicit_exclusions == _REQUIRED_EXCLUSIONS
    assert matrix.revision == "HK-V1-003"
    assert matrix.effective_date == "2026-09-02"
    assert len(matrix.rows) == 43
    assert len([row for row in matrix.rows if row.exclusion_code]) == 3
    assert len([row for row in matrix.rows if not row.exclusion_code]) == 40
    assert len(privy_council_rows) == 1
    privy_council_row = privy_council_rows[0]
    assert privy_council_row.scope_id == _PRIVY_COUNCIL_PAIR[0]
    assert privy_council_row.exclusion_code == "HK-CASE-PRE-1997"
    assert privy_council_row.cadence == "EXCLUDED_FROM_V1"
    assert privy_council_row.earliest_boundary == "1997-07-01"
    assert privy_council_row.cutoff_rule == _PRIVY_COUNCIL_CUTOFF_RULE
    assert privy_council_row.limitation_text == _PRIVY_COUNCIL_LIMITATION
    assert len(npc_rows) == 2
    assert {row.scope_id for row in npc_rows} == {_NPC_SCOPE_ID}
    assert {row.cadence for row in npc_rows} == {"EXCLUDED_FROM_V1"}
    assert {row.exclusion_code for row in npc_rows} == {_NPC_EXCLUSION_CODE}
    assert {row.limitation_text for row in npc_rows} == {_NPC_LIMITATION}
    assert {row.technical_state for row in npc_rows} == {"NOT_ADMITTED"}
    assert {row.rights_state for row in npc_rows} == {"NOT_ADMITTED"}


def test_default_matrix_declares_the_actual_unsigned_document_fingerprint() -> None:
    """The checked-in digest must attest the actual unsigned JSON document."""
    document = load_default_matrix_document()
    declared_fingerprint = document.pop("fingerprint")

    assert isinstance(declared_fingerprint, str)
    assert declared_fingerprint == "sha256:" + sha256(canonicalize(document)).hexdigest()


def test_default_matrix_is_stable_across_two_independent_reads() -> None:
    """Repeated default loads must return the same frozen revision and fingerprint."""
    first = load_hk_v1_coverage_matrix()
    second = load_hk_v1_coverage_matrix()

    assert first == second
    assert first is not second
    assert first.revision == "HK-V1-003"
    assert first.fingerprint == second.fingerprint


def test_default_matrix_gate_fails_closed_on_unadmitted_sources() -> None:
    """Freezing scope must not imply technical or rights source admission."""
    matrix = load_hk_v1_coverage_matrix()

    assert {row.technical_state for row in matrix.rows} == {"NOT_ADMITTED"}
    assert {row.rights_state for row in matrix.rows} == {"NOT_ADMITTED"}
    gate = evaluate_hk_v1_scope_gate(matrix)
    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == (
        "SOURCE_TECHNICAL_ADMISSION_MISSING",
        "SOURCE_RIGHTS_ADMISSION_MISSING",
    )


def test_reporting_package_exports_the_hk_v1_matrix_api() -> None:
    """Consumers must receive the matrix contract from the reporting boundary."""
    assert asklegal_reporting.CoverageMatrixRow is CoverageMatrixRow
    assert asklegal_reporting.HongKongV1CoverageError is HongKongV1CoverageError
    assert asklegal_reporting.HongKongV1CoverageMatrix is HongKongV1CoverageMatrix
    assert asklegal_reporting.HongKongV1ScopeGateResult is HongKongV1ScopeGateResult
    assert asklegal_reporting.evaluate_hk_v1_scope_gate is evaluate_hk_v1_scope_gate
    assert (
        asklegal_reporting.is_hk_v1_coverage_matrix_policy_approved
        is is_hk_v1_coverage_matrix_policy_approved
    )
    assert asklegal_reporting.load_hk_v1_coverage_matrix is load_hk_v1_coverage_matrix


def test_scope_gate_rejects_the_former_six_row_placeholder_matrix(tmp_path: Path) -> None:
    """Invented rows cannot stand in for the exact 43-row source inventory."""
    matrix = load_hk_v1_coverage_matrix(
        write_matrix(tmp_path, admitted_placeholder_matrix_document())
    )

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("SOURCE_ROLE_INVENTORY_INVALID",)


@pytest.mark.parametrize("required_pair", _REQUIRED_SCOPE_SOURCE_PAIRS)
def test_scope_gate_rejects_each_omitted_required_scope_source_pair(
    tmp_path: Path,
    required_pair: tuple[str, str],
) -> None:
    """No required scope/source role may disappear from an otherwise admitted matrix."""
    document = complete_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    document["rows"] = [
        row
        for row in rows
        if isinstance(row, dict) and (row["scope_id"], row["source_id"]) != required_pair
    ]
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("SOURCE_ROLE_INVENTORY_INVALID",)


@pytest.mark.parametrize("required_pair", _REQUIRED_SCOPE_SOURCE_PAIRS)
def test_scope_gate_rejects_each_replaced_required_scope_source_pair(
    tmp_path: Path,
    required_pair: tuple[str, str],
) -> None:
    """An invented source role cannot replace any exact required pair."""
    document = complete_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if (row["scope_id"], row["source_id"]) == required_pair:
            row["source_id"] = f"{required_pair[1]}-REPLACEMENT"
            break
    else:
        pytest.fail(f"required pair missing from fixture: {required_pair}")
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("SOURCE_ROLE_INVENTORY_INVALID",)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("exclusion_code", ""),
        ("cadence", "ON_DEMAND"),
        ("earliest_boundary", "1997-07-02"),
        ("cutoff_rule", "CURRENT_AT_CYCLE_CUTOFF"),
        ("limitation_text", "Privy Council is included."),
    ],
)
def test_scope_gate_rejects_privy_council_exclusion_semantic_drift(
    tmp_path: Path,
    field: str,
    invalid_value: str,
) -> None:
    """The mandatory excluded accounting row must retain its exact contract."""
    document = complete_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if (row["scope_id"], row["source_id"]) == _PRIVY_COUNCIL_PAIR:
            row[field] = invalid_value
            break
    else:
        pytest.fail("Privy Council row missing from fixture")
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("SOURCE_ROLE_EXCLUSION_INVALID",)


@pytest.mark.parametrize("source_id", sorted(_NPC_SOURCE_IDS))
@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("source_id", "HK-LEG-NPC-REPLACEMENT"),
        ("exclusion_code", ""),
        ("cadence", "MONTHLY_EVENT_TRIGGERED_AND_ON_DEMAND"),
        ("limitation_text", "Included constitutional material."),
        ("technical_state", "ADMITTED"),
        ("rights_state", "ADMITTED"),
    ],
)
def test_scope_gate_rejects_each_npc_exclusion_policy_mutation(
    tmp_path: Path,
    source_id: str,
    field: str,
    invalid_value: str,
) -> None:
    """Neither dormant NPC pair nor any field that keeps it excluded may drift."""
    document = complete_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if row["source_id"] == source_id:
            assert row["cadence"] == "EXCLUDED_FROM_V1"
            assert row["exclusion_code"] == _NPC_EXCLUSION_CODE
            assert row["limitation_text"] == _NPC_LIMITATION
            assert row["technical_state"] == "NOT_ADMITTED"
            assert row["rights_state"] == "NOT_ADMITTED"
            row[field] = invalid_value
            break
    else:
        pytest.fail(f"NPC row missing from fixture: {source_id}")
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes in {
        ("SOURCE_ROLE_INVENTORY_INVALID",),
        ("SOURCE_ROLE_EXCLUSION_INVALID",),
        ("SOURCE_ROLE_POLICY_INVALID",),
    }


def test_scope_gate_rejects_an_exclusion_code_on_an_active_row(tmp_path: Path) -> None:
    """An arbitrary exclusion code cannot let an active source evade admission."""
    document = complete_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if (row["scope_id"], row["source_id"]) != _PRIVY_COUNCIL_PAIR:
            row["exclusion_code"] = "HK-PRINCIPLES"
            break
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("SOURCE_ROLE_EXCLUSION_INVALID",)


def test_scope_gate_exempts_only_the_three_exact_excluded_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All 40 active rows may admit while the three exact excluded rows stay unadmitted."""
    matrix = load_approved_temporary_default(tmp_path, monkeypatch)
    excluded_rows = [row for row in matrix.rows if row.exclusion_code]
    active_rows = [row for row in matrix.rows if not row.exclusion_code]

    assert len(active_rows) == 40
    assert len(excluded_rows) == 3
    assert {(row.scope_id, row.source_id) for row in excluded_rows} == _EXCLUDED_PAIRS
    assert all(row.technical_state == "NOT_ADMITTED" for row in excluded_rows)
    assert all(row.rights_state == "NOT_ADMITTED" for row in excluded_rows)
    assert evaluate_hk_v1_scope_gate(matrix) == HongKongV1ScopeGateResult("ADMITTED", ())


def test_scope_gate_still_blocks_one_unadmitted_active_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the three exact excluded rows omit technical and rights prerequisites."""
    document = approved_new_revision_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if (row["scope_id"], row["source_id"]) not in _EXCLUDED_PAIRS:
            row["technical_state"] = "NOT_ADMITTED"
            row["rights_state"] = "NOT_ADMITTED"
            break
    seal_matrix_document(document)
    matrix = load_approved_temporary_default(tmp_path, monkeypatch, document)

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == (
        "SOURCE_TECHNICAL_ADMISSION_MISSING",
        "SOURCE_RIGHTS_ADMISSION_MISSING",
    )


@pytest.mark.parametrize(
    ("field", "drifted_value"),
    [
        ("fact_authority", "DRIFTED_FACT_AUTHORITY"),
        ("owner", "CONTROL"),
        ("earliest_boundary", "1997-07-02"),
        ("cutoff_rule", "DRIFTED_CUTOFF_RULE"),
        ("cadence", "DRIFTED_CADENCE"),
        ("outage_consequence", "NONBLOCKING"),
        ("limitation_text", "Drifted limitation."),
    ],
)
def test_scope_gate_rejects_resealed_active_row_policy_drift(
    tmp_path: Path,
    field: str,
    drifted_value: str,
) -> None:
    """A new digest cannot authorize drift from an approved source-role policy."""
    document = complete_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if (row["scope_id"], row["source_id"]) != _PRIVY_COUNCIL_PAIR:
            row[field] = drifted_value
            break
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("SOURCE_ROLE_POLICY_INVALID",)


@pytest.mark.parametrize(
    ("field", "drifted_value"),
    [
        ("revision", "HK-V1-002"),
        ("effective_date", "2026-08-27"),
    ],
)
def test_scope_gate_rejects_resealed_top_level_policy_drift(
    tmp_path: Path,
    field: str,
    drifted_value: str,
) -> None:
    """A resealed candidate must retain the approved top-level policy identity."""
    document = complete_admitted_matrix_document()
    document[field] = drifted_value
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("MATRIX_POLICY_INVALID",)


def test_matrix_rejects_unknown_row_field(tmp_path: Path) -> None:
    """An added source-row field must not silently alter the scope contract."""
    document = valid_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    first_row = rows[0]
    assert isinstance(first_row, dict)
    first_row["invented"] = True
    path = write_matrix(tmp_path, document)

    with pytest.raises(HongKongV1CoverageError, match="MATRIX_ROW_FIELDS_INVALID"):
        load_hk_v1_coverage_matrix(path)


def test_matrix_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    """An added document field must not silently broaden the frozen contract."""
    document = valid_matrix_document()
    document["invented"] = True
    path = write_matrix(tmp_path, document)

    with pytest.raises(HongKongV1CoverageError, match="MATRIX_FIELDS_INVALID"):
        load_hk_v1_coverage_matrix(path)


def test_matrix_rejects_noncanonical_bytes(tmp_path: Path) -> None:
    """Whitespace changes must not be accepted as an immutable matrix artifact."""
    document = valid_matrix_document()
    path = tmp_path / "coverage-matrix.json"
    path.write_bytes(canonicalize(document) + b"\n")

    with pytest.raises(HongKongV1CoverageError, match="MATRIX_CANONICAL_BYTES_INVALID"):
        load_hk_v1_coverage_matrix(path)


def test_matrix_rejects_malformed_fingerprint(tmp_path: Path) -> None:
    """A declared fingerprint needs the repository's exact SHA-256 encoding."""
    document = valid_matrix_document()
    document["fingerprint"] = "not-a-fingerprint"
    path = write_matrix(tmp_path, document)

    with pytest.raises(HongKongV1CoverageError, match="MATRIX_FINGERPRINT_INVALID"):
        load_hk_v1_coverage_matrix(path)


def test_matrix_rejects_fingerprint_drift(tmp_path: Path) -> None:
    """A valid-looking digest cannot attest a different matrix body."""
    document = valid_matrix_document()
    document["fingerprint"] = "sha256:" + ("0" * 64)
    path = write_matrix(tmp_path, document)

    with pytest.raises(HongKongV1CoverageError, match="MATRIX_FINGERPRINT_MISMATCH"):
        load_hk_v1_coverage_matrix(path)


def test_matrix_rejects_duplicate_scope_source_pair(tmp_path: Path) -> None:
    """One scope/source pair must not have competing policy declarations."""
    document = valid_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    first_row = rows[0]
    assert isinstance(first_row, dict)
    rows.append(first_row.copy())
    seal_matrix_document(document)
    path = write_matrix(tmp_path, document)

    with pytest.raises(HongKongV1CoverageError, match="MATRIX_ROW_DUPLICATE"):
        load_hk_v1_coverage_matrix(path)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("material_family", "PRINCIPLES"),
        ("owner", "PROMOTION"),
        ("technical_state", "UNKNOWN"),
        ("rights_state", "UNKNOWN"),
        ("outage_consequence", "UNKNOWN"),
    ],
)
def test_matrix_rejects_unknown_closed_row_values(
    tmp_path: Path,
    field: str,
    invalid_value: str,
) -> None:
    """Closed policy enumerations must not gain unreviewed values."""
    document = valid_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    first_row = rows[0]
    assert isinstance(first_row, dict)
    first_row[field] = invalid_value
    seal_matrix_document(document)
    path = write_matrix(tmp_path, document)

    with pytest.raises(HongKongV1CoverageError, match="MATRIX_ROW_VALUE_INVALID"):
        load_hk_v1_coverage_matrix(path)


def test_matrix_sorts_rows_and_scope_gate_reports_missing_admissions(tmp_path: Path) -> None:
    """Gate A must retain deterministic ordering and fail visibly on missing admission."""
    document = valid_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    first_row = rows[0]
    assert isinstance(first_row, dict)
    second_row = dict(first_row)
    second_row["scope_id"] = "HK-CASE-BINDING-POST-1998"
    second_row["source_id"] = "HK-CASE-JUDICIARY-OPINIONS"
    rows.insert(0, second_row)
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    assert [(row.scope_id, row.source_id) for row in matrix.rows] == [
        ("HK-CASE-BINDING-POST-1997", "HK-CASE-JUDICIARY-LISTING"),
        ("HK-CASE-BINDING-POST-1998", "HK-CASE-JUDICIARY-OPINIONS"),
    ]
    assert matrix.fingerprint == document["fingerprint"]
    assert evaluate_hk_v1_scope_gate(matrix).result == "NOT_ADMITTED"
    assert evaluate_hk_v1_scope_gate(matrix).blocker_codes == ("SCOPE_INVENTORY_INVALID",)


def test_matrix_accepts_unsorted_rows_when_its_fingerprint_covers_actual_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fingerprint verification must precede the loader's deterministic row sorting."""
    document = approved_new_revision_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    document["rows"] = list(reversed(rows))
    seal_matrix_document(document)

    matrix = load_approved_temporary_default(tmp_path, monkeypatch, document)

    assert matrix.fingerprint == document["fingerprint"]
    assert [(row.scope_id, row.source_id) for row in matrix.rows] == sorted(
        (row["scope_id"], row["source_id"]) for row in rows if isinstance(row, dict)
    )
    assert evaluate_hk_v1_scope_gate(matrix).result == "ADMITTED"


@pytest.mark.parametrize("omitted_scope_id", _REQUIRED_SCOPE_IDS)
def test_scope_gate_rejects_each_omitted_required_scope(
    tmp_path: Path,
    omitted_scope_id: str,
) -> None:
    """Gate A must not treat an all-admitted partial V1 scope as complete."""
    document = complete_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    document["rows"] = [
        row for row in rows if isinstance(row, dict) and row["scope_id"] != omitted_scope_id
    ]
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("SCOPE_INVENTORY_INVALID",)


@pytest.mark.parametrize(
    ("scope_id", "wrong_material_family"),
    [
        ("HK-LEG-ORDINANCES", "CASES"),
        ("HK-LEG-SUBSIDIARY", "REGULATORY"),
        ("HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS", "CASES"),
        ("HK-CASE-BINDING-POST-1997", "LEGISLATION"),
    ],
)
def test_scope_gate_rejects_each_wrong_required_scope_material_family_pair(
    tmp_path: Path,
    scope_id: str,
    wrong_material_family: str,
) -> None:
    """Every source row must retain its settled scope-to-family binding."""
    document = complete_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if row["scope_id"] == scope_id:
            row["material_family"] = wrong_material_family
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("SCOPE_MATERIAL_FAMILY_INVALID",)


@pytest.mark.parametrize("omitted_exclusion", _REQUIRED_EXCLUSIONS)
def test_scope_gate_rejects_each_omitted_required_exclusion(
    tmp_path: Path,
    omitted_exclusion: str,
) -> None:
    """Gate A must not admit a matrix missing any settled V1 exclusion."""
    document = complete_admitted_matrix_document()
    exclusions = document["explicit_exclusions"]
    assert isinstance(exclusions, list)
    document["explicit_exclusions"] = [
        exclusion for exclusion in exclusions if exclusion != omitted_exclusion
    ]
    seal_matrix_document(document)
    matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("EXCLUSION_INVENTORY_INVALID",)


def test_scope_gate_rejects_resealed_state_only_alternate_under_approved_revision(
    tmp_path: Path,
) -> None:
    """A new digest cannot attach admission evidence to the approved revision."""
    matrix = load_complete_admitted_matrix(tmp_path)

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert matrix.revision == "HK-V1-003"
    assert matrix.fingerprint != (
        "sha256:551a3cc2dfbaa6d4082076b19b6a74784e93225014654c7af958231c594ac512"
    )
    assert gate == HongKongV1ScopeGateResult(
        result="NOT_ADMITTED",
        blocker_codes=("MATRIX_POLICY_INVALID",),
    )


def test_scope_gate_rejects_a_direct_incomplete_matrix_with_valid_fingerprint(
    tmp_path: Path,
) -> None:
    """A caller cannot bypass the complete-scope check by reconstructing the dataclass."""
    document = complete_admitted_matrix_document()
    rows = document["rows"]
    assert isinstance(rows, list)
    document["rows"] = [
        row
        for row in rows
        if isinstance(row, dict) and row["scope_id"] != "HK-CASE-BINDING-POST-1997"
    ]
    seal_matrix_document(document)
    decoded_matrix = load_hk_v1_coverage_matrix(write_matrix(tmp_path, document))
    direct_matrix = HongKongV1CoverageMatrix(
        revision=decoded_matrix.revision,
        effective_date=decoded_matrix.effective_date,
        rows=decoded_matrix.rows,
        explicit_exclusions=decoded_matrix.explicit_exclusions,
        included_material_families=decoded_matrix.included_material_families,
        fingerprint=decoded_matrix.fingerprint,
    )

    gate = evaluate_hk_v1_scope_gate(direct_matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("MATRIX_PROVENANCE_INVALID",)


def test_scope_gate_rejects_a_direct_complete_matrix_with_loader_fingerprint(
    tmp_path: Path,
) -> None:
    """A matching public dataclass copy cannot impersonate a loader-issued matrix."""
    loaded_matrix = load_complete_admitted_matrix(tmp_path)
    direct_matrix = HongKongV1CoverageMatrix(
        revision=loaded_matrix.revision,
        effective_date=loaded_matrix.effective_date,
        rows=loaded_matrix.rows,
        explicit_exclusions=loaded_matrix.explicit_exclusions,
        included_material_families=loaded_matrix.included_material_families,
        fingerprint=loaded_matrix.fingerprint,
    )

    gate = evaluate_hk_v1_scope_gate(direct_matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == ("MATRIX_PROVENANCE_INVALID",)


def test_discarded_loader_matrix_is_collectible_without_admitting_direct_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Weak provenance must release discarded loads without weakening identity checks."""
    loaded_matrix = load_approved_temporary_default(tmp_path, monkeypatch)
    direct_matrix = HongKongV1CoverageMatrix(
        revision=loaded_matrix.revision,
        effective_date=loaded_matrix.effective_date,
        rows=loaded_matrix.rows,
        explicit_exclusions=loaded_matrix.explicit_exclusions,
        included_material_families=loaded_matrix.included_material_families,
        fingerprint=loaded_matrix.fingerprint,
    )
    loaded_reference = weakref.ref(loaded_matrix)

    assert evaluate_hk_v1_scope_gate(loaded_matrix).result == "ADMITTED"
    del loaded_matrix
    gc.collect()

    assert loaded_reference() is None
    assert evaluate_hk_v1_scope_gate(direct_matrix).blocker_codes == ("MATRIX_PROVENANCE_INVALID",)


def test_loader_registry_cleans_dead_entry_and_preserves_colliding_replacement(
    tmp_path: Path,
) -> None:
    """Cleanup must remove only the exact dead identity registration."""
    template = load_complete_admitted_matrix(tmp_path)
    registry = coverage_module.LoaderIssuedMatrixRegistry(identity_key=lambda _matrix: 1)

    discarded = replace(template)
    discarded_registration = registry.register(discarded)
    del discarded
    gc.collect()

    assert discarded_registration() is None
    assert len(registry) == 0

    stale = replace(template)
    replacement = replace(template)
    stale_registration = registry.register(stale)
    registry.register(replacement)
    del stale
    gc.collect()

    assert stale_registration() is None
    assert registry.is_issued(replacement)


@pytest.mark.parametrize("field", ["technical_state", "rights_state"])
def test_scope_gate_rejects_same_loader_object_after_active_admission_state_mutation(
    field: str,
) -> None:
    """Changing either active admission state must invalidate loader provenance."""
    matrix = load_hk_v1_coverage_matrix()
    original_fingerprint = matrix.fingerprint

    for row in matrix.rows:
        if (row.scope_id, row.source_id) != _PRIVY_COUNCIL_PAIR:
            object.__setattr__(row, field, "ADMITTED")

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert matrix.fingerprint == original_fingerprint
    assert gate == HongKongV1ScopeGateResult(
        result="NOT_ADMITTED",
        blocker_codes=("MATRIX_PROVENANCE_INVALID",),
    )


@pytest.mark.parametrize(
    ("field", "mutated_value"),
    [
        ("revision", "HK-V1-999"),
        ("effective_date", "2099-01-01"),
        ("explicit_exclusions", (*_REQUIRED_EXCLUSIONS, "MUTATED-EXCLUSION")),
        ("fingerprint", "sha256:" + ("0" * 64)),
    ],
)
def test_scope_gate_rejects_same_loader_object_after_top_level_mutation(
    field: str,
    mutated_value: str | tuple[str, ...],
) -> None:
    """Every decoded top-level field must remain equal to its loader snapshot."""
    matrix = load_hk_v1_coverage_matrix()
    object.__setattr__(matrix, field, mutated_value)

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.blocker_codes == ("MATRIX_PROVENANCE_INVALID",)


@pytest.mark.parametrize(
    ("field", "mutated_value"),
    [
        ("scope_id", "HK-LEG-ORDINANCES"),
        ("material_family", "LEGISLATION"),
        ("source_id", "HK-CASE-ALTERED"),
        ("fact_authority", "ALTERED_AUTHORITY"),
        ("owner", "CONTROL"),
        ("earliest_boundary", "1998-01-01"),
        ("cutoff_rule", "ALTERED_CUTOFF"),
        ("cadence", "ALTERED_CADENCE"),
        ("outage_consequence", "NONBLOCKING"),
        ("exclusion_code", "HK-CASE-PRE-1997"),
        ("limitation_text", "Altered limitation."),
    ],
)
def test_scope_gate_rejects_same_loader_object_after_row_policy_mutation(
    field: str,
    mutated_value: str,
) -> None:
    """Every decoded row policy field must remain equal to its loader snapshot."""
    matrix = load_hk_v1_coverage_matrix()
    object.__setattr__(matrix.rows[0], field, mutated_value)

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.blocker_codes == ("MATRIX_PROVENANCE_INVALID",)


def test_scope_gate_rejects_same_loader_object_after_row_inventory_mutation() -> None:
    """The complete row tuple must remain equal to the loader-issued inventory."""
    matrix = load_hk_v1_coverage_matrix()
    object.__setattr__(matrix, "rows", matrix.rows[1:])

    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.blocker_codes == ("MATRIX_PROVENANCE_INVALID",)


def test_scope_gate_rejects_direct_non_tuple_members(tmp_path: Path) -> None:
    """The evaluator must enforce exact tuple runtime types, not annotations alone."""
    matrix = load_complete_admitted_matrix(tmp_path)
    list_rows = replace(matrix)
    object.__setattr__(list_rows, "rows", list(matrix.rows))
    list_exclusions = replace(matrix)
    object.__setattr__(list_exclusions, "explicit_exclusions", list(matrix.explicit_exclusions))
    cases = (
        (list_rows, "MATRIX_PROVENANCE_INVALID"),
        (list_exclusions, "MATRIX_PROVENANCE_INVALID"),
    )

    for direct_matrix, expected_blocker in cases:
        gate = evaluate_hk_v1_scope_gate(direct_matrix)

        assert gate.result == "NOT_ADMITTED"
        assert gate.blocker_codes == (expected_blocker,)


def test_two_family_coverage_report_lists_four_scopes_exclusions_heads_and_capabilities() -> None:
    """Mutation caught: omitted family facts can otherwise make a partial report look complete."""
    acquisition_type = coverage_module.FamilyAcquisitionCoverage
    build = coverage_module.build_hk_v1_two_family_coverage_report
    parse = coverage_module.parse_hk_v1_two_family_coverage_report
    acquisitions = (
        acquisition_type(
            "CASES",
            "cyc_cases_1997",
            "1997-12-31T00:00:00Z",
            ("HK-CASE-BINDING-POST-1997",),
            "sha256:" + "1" * 64,
            "sha256:" + "2" * 64,
            0,
            ("review/cases/name-discrepancy",),
            ("cases/judgment-bundles/sha256/" + "a" * 64 + ".json",),
        ),
        acquisition_type(
            "LEGISLATION",
            "cyc_legislation_1997",
            "1997-12-31T00:00:00Z",
            tuple(sorted(_REQUIRED_SCOPE_IDS[:3])),
            "sha256:" + "3" * 64,
            "sha256:" + "4" * 64,
            0,
            ("review/legislation/structural-issue",),
            ("legislation-item/cap1/" + "b" * 64,),
        ),
    )
    capabilities = tuple(
        _issued_capability(kind, profile, "1997-12-31T00:00:00Z")
        for kind, profile in (
            ("EMBEDDING", "sha256:" + "5" * 64),
            ("MODEL", "sha256:" + "6" * 64),
        )
    )

    report = build(load_hk_v1_coverage_matrix(), acquisitions, capabilities)
    restored = parse(report.content)
    document = parse_json_bytes(report.content, max_bytes=1_000_000)
    assert type(document) is dict
    acquisition_documents = document["acquisitions"]
    assert type(acquisition_documents) is list
    assert all(type(item) is dict for item in acquisition_documents)
    typed_acquisitions = tuple(item for item in acquisition_documents if type(item) is dict)
    capability_documents = document["capabilities"]
    assert type(capability_documents) is list
    assert all(type(item) is dict for item in capability_documents)
    typed_capabilities = tuple(item for item in capability_documents if type(item) is dict)
    exclusions = document["explicit_exclusions"]
    assert type(exclusions) is list

    assert restored == report
    assert document["scope_ids"] == sorted(_REQUIRED_SCOPE_IDS)
    assert document["included_material_families"] == ["CASES", "LEGISLATION"]
    assert exclusions == list(_REQUIRED_EXCLUSIONS)
    assert "HKEX_REGULATORY_POST_V1" in exclusions
    assert "HK-PRINCIPLES" in exclusions
    assert [item["journal_head_fingerprint"] for item in typed_acquisitions] == [
        "sha256:" + "2" * 64,
        "sha256:" + "4" * 64,
    ]
    assert [item["retryable_count"] for item in typed_acquisitions] == [0, 0]
    assert [item["review_issue_refs"] for item in typed_acquisitions] == [
        ["review/cases/name-discrepancy"],
        ["review/legislation/structural-issue"],
    ]
    assert [item["capability"] for item in typed_capabilities] == [
        "EMBEDDING",
        "MODEL",
    ]


def test_two_family_coverage_builder_rejects_unissued_capability_shells() -> None:
    """Mutation caught: syntax-only capability metadata can otherwise enter reports."""
    acquisition_type = coverage_module.FamilyAcquisitionCoverage
    acquisitions = (
        acquisition_type(
            "CASES",
            "cyc_cases_1997",
            "1997-12-31T00:00:00Z",
            ("HK-CASE-BINDING-POST-1997",),
            "sha256:" + "1" * 64,
            "sha256:" + "2" * 64,
            0,
            (),
            ("cases/judgment-bundles/sha256/" + "a" * 64 + ".json",),
        ),
        acquisition_type(
            "LEGISLATION",
            "cyc_legislation_1997",
            "1997-12-31T00:00:00Z",
            tuple(sorted(_REQUIRED_SCOPE_IDS[:3])),
            "sha256:" + "3" * 64,
            "sha256:" + "4" * 64,
            0,
            (),
            ("legislation-item/cap1/" + "b" * 64,),
        ),
    )
    unissued = (
        _unissued_capability(
            "EMBEDDING",
            "sha256:" + "5" * 64,
            "capability/embedding/unissued",
        ),
        _unissued_capability(
            "MODEL",
            "sha256:" + "6" * 64,
            "capability/model/unissued",
        ),
    )

    with pytest.raises(
        coverage_module.HongKongV1CoverageError,
        match="TWO_FAMILY_COVERAGE_CAPABILITY_INVALID",
    ):
        coverage_module.build_hk_v1_two_family_coverage_report(
            load_hk_v1_coverage_matrix(), acquisitions, unissued
        )


@pytest.mark.parametrize(
    ("matrix", "expected_blocker"),
    [
        (
            HongKongV1CoverageMatrix(
                revision="HK-V1-003",
                effective_date="2026-09-02",
                rows=(),
                explicit_exclusions=_REQUIRED_EXCLUSIONS,
                included_material_families=("CASES", "LEGISLATION"),
                fingerprint="sha256:" + ("0" * 64),
            ),
            "MATRIX_PROVENANCE_INVALID",
        ),
        (
            object.__new__(HongKongV1CoverageMatrix),
            "MATRIX_PROVENANCE_INVALID",
        ),
    ],
)
def test_scope_gate_rejects_invalid_direct_matrix_types_or_empty_rows(
    matrix: HongKongV1CoverageMatrix,
    expected_blocker: str,
) -> None:
    """Gate A must not vacuously admit a direct or empty matrix object."""
    gate = evaluate_hk_v1_scope_gate(matrix)

    assert gate.result == "NOT_ADMITTED"
    assert gate.blocker_codes == (expected_blocker,)


def test_scope_gate_rejects_direct_row_type_state_duplicate_and_fingerprint_drift(
    tmp_path: Path,
) -> None:
    """Direct objects must receive the same admission-critical checks as JSON input."""
    matrix = load_complete_admitted_matrix(tmp_path)
    invalid_state_row = replace(matrix.rows[0])
    object.__setattr__(invalid_state_row, "technical_state", "UNKNOWN")
    invalid_row_type = object.__new__(CoverageMatrixRow)
    cases = (
        (
            replace(
                matrix,
                rows=(invalid_row_type, *matrix.rows[1:]),
            ),
            "MATRIX_PROVENANCE_INVALID",
        ),
        (
            replace(matrix, rows=(*matrix.rows, matrix.rows[0])),
            "MATRIX_PROVENANCE_INVALID",
        ),
        (
            replace(matrix, rows=(invalid_state_row, *matrix.rows[1:])),
            "MATRIX_PROVENANCE_INVALID",
        ),
        (
            replace(matrix, fingerprint="sha256:" + ("0" * 64)),
            "MATRIX_PROVENANCE_INVALID",
        ),
    )

    for direct_matrix, expected_blocker in cases:
        gate = evaluate_hk_v1_scope_gate(direct_matrix)

        assert gate.result == "NOT_ADMITTED"
        assert gate.blocker_codes == (expected_blocker,)
