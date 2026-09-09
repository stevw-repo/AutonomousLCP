"""Strict immutable Hong Kong V1 Coverage Matrix contract."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Never
from weakref import ReferenceType, ref

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value

from asklegal_reporting.hk_v1_proposal_evidence import (
    ProposalEvidenceError,
    VerifiedSemanticCapability,
    validate_verified_semantic_capability,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_MAX_MATRIX_BYTES = 1_000_000
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_MATRIX_FIELDS = frozenset(
    {
        "effective_date",
        "explicit_exclusions",
        "fingerprint",
        "included_material_families",
        "revision",
        "rows",
    }
)
_ROW_FIELDS = frozenset(
    {
        "cadence",
        "cutoff_rule",
        "earliest_boundary",
        "exclusion_code",
        "fact_authority",
        "limitation_text",
        "material_family",
        "outage_consequence",
        "owner",
        "rights_state",
        "scope_id",
        "source_id",
        "technical_state",
    }
)
_MATERIAL_FAMILIES = frozenset({"LEGISLATION", "CASES", "REGULATORY"})
_OWNERS = frozenset({"ACQUISITION", "LEGAL_PROCESSING", "CONTROL"})
_ADMISSION_STATES = frozenset({"ADMITTED", "NOT_ADMITTED"})
_OUTAGE_CONSEQUENCES = frozenset({"RELEASE_BLOCKING", "AFFECTED_WORK_BLOCKING", "NONBLOCKING"})
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
_REQUIRED_SOURCE_IDS_BY_SCOPE = {
    "HK-LEG-ORDINANCES": _LEGISLATION_SHARED_SOURCE_IDS,
    "HK-LEG-SUBSIDIARY": _LEGISLATION_SHARED_SOURCE_IDS,
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS": (
        _LEGISLATION_SHARED_SOURCE_IDS | _LEGISLATION_CONSTITUTIONAL_SOURCE_IDS
    ),
    "HK-CASE-BINDING-POST-1997": _CASES_SOURCE_IDS,
}
_REQUIRED_SCOPE_SOURCE_PAIRS = frozenset(
    (scope_id, source_id)
    for scope_id, source_ids in _REQUIRED_SOURCE_IDS_BY_SCOPE.items()
    for source_id in source_ids
)
_V1_INCLUDED_MATERIAL_FAMILIES = frozenset({"LEGISLATION", "CASES"})
_V1_REQUIRED_SCOPE_MATERIAL_FAMILIES = {
    "HK-LEG-ORDINANCES": "LEGISLATION",
    "HK-LEG-SUBSIDIARY": "LEGISLATION",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS": "LEGISLATION",
    "HK-CASE-BINDING-POST-1997": "CASES",
}
_V1_REQUIRED_SCOPE_IDS = frozenset(
    {
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-CASE-BINDING-POST-1997",
    }
)
_V1_POSTPONED_EXCLUSIONS = frozenset({"HKEX_REGULATORY_POST_V1"})
_EXCLUDED_PRIVY_COUNCIL_PAIR = (
    "HK-CASE-BINDING-POST-1997",
    "HK-CASE-PRIVY-COUNCIL",
)
_EXCLUDED_PRIVY_COUNCIL_CUTOFF_RULE = (
    "DECISION_DATE_ON_OR_AFTER_1997-07-01_AND_PUBLISHED_BY_CYCLE_CUTOFF"
)
_EXCLUDED_PRIVY_COUNCIL_LIMITATION = (
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
_EXCLUDED_SOURCE_PAIRS = frozenset(
    {
        _EXCLUDED_PRIVY_COUNCIL_PAIR,
        *((_NPC_SCOPE_ID, source_id) for source_id in _NPC_SOURCE_IDS),
    }
)
_REQUIRED_EXCLUSIONS = (
    frozenset(
        {
            "HK-PRINCIPLES",
            "HK-CASE-PRE-1997",
            "FULL_JUDGMENTS_AS_RECORDS",
            "HKEX_NON_LISTING_RULE_GUIDANCE",
            _NPC_EXCLUSION_CODE,
            "ASKLEGAL_ROUTING",
            "ASKLEGAL_ADMIN",
            "AZURE_APP_HOSTING",
        }
    )
    | _V1_POSTPONED_EXCLUSIONS
)
_DEFAULT_MATRIX_PATH = Path(__file__).with_name("hk_v1_coverage_matrix.json")


class HongKongV1CoverageError(ValueError):
    """One closed Coverage Matrix validation failure."""

    def __init__(self, code: str) -> None:
        """Expose the stable machine-readable validation code."""
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CoverageMatrixRow:
    """One source role's declared scope and admission state."""

    scope_id: str
    material_family: Literal["LEGISLATION", "CASES", "REGULATORY"]
    source_id: str
    fact_authority: str
    owner: Literal["ACQUISITION", "LEGAL_PROCESSING", "CONTROL"]
    earliest_boundary: str
    cutoff_rule: str
    cadence: str
    technical_state: Literal["ADMITTED", "NOT_ADMITTED"]
    rights_state: Literal["ADMITTED", "NOT_ADMITTED"]
    outage_consequence: Literal["RELEASE_BLOCKING", "AFFECTED_WORK_BLOCKING", "NONBLOCKING"]
    exclusion_code: str
    limitation_text: str


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HongKongV1CoverageMatrix:
    """One exact fingerprinted definition of the Hong Kong V1 source scope."""

    revision: str
    effective_date: str
    rows: tuple[CoverageMatrixRow, ...]
    explicit_exclusions: tuple[str, ...]
    included_material_families: tuple[str, ...]
    fingerprint: str


_CoverageMatrixRowSnapshot = tuple[str, ...]
_CoverageMatrixSnapshot = tuple[
    str,
    str,
    tuple[_CoverageMatrixRowSnapshot, ...],
    tuple[str, ...],
    tuple[str, ...],
    str,
]


@dataclass(frozen=True, slots=True)
class HongKongV1ScopeGateResult:
    """The fail-visible Gate A result for one checked matrix."""

    result: Literal["ADMITTED", "NOT_ADMITTED"]
    blocker_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FamilyAcquisitionCoverage:
    """One complete acquisition family's proposal-facing immutable facts."""

    material_family: Literal["LEGISLATION", "CASES"]
    cycle_id: str
    observation_cutoff: str
    scope_ids: tuple[str, ...]
    manifest_fingerprint: str
    journal_head_fingerprint: str
    retryable_count: int
    review_issue_refs: tuple[str, ...]
    verified_evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticCapabilityCoverage:
    """Exact provider-disabled capability evidence bound into the coverage report."""

    capability: Literal["MODEL", "EMBEDDING"]
    profile_fingerprint: str
    evidence_ref: str
    status: Literal["PROVIDER_DISABLED_PREPARATION_ONLY"]


@dataclass(frozen=True, slots=True)
class HongKongV1TwoFamilyCoverageReport:
    """Canonical four-scope coverage evidence for one proposal candidate."""

    observation_cutoff: str
    included_material_families: tuple[str, ...]
    scope_ids: tuple[str, ...]
    explicit_exclusions: tuple[str, ...]
    acquisitions: tuple[FamilyAcquisitionCoverage, ...]
    capabilities: tuple[SemanticCapabilityCoverage, ...]
    content: bytes
    fingerprint: str


@dataclass(frozen=True, slots=True)
class _IssuedMatrixRegistration:
    """One weak identity binding plus its immutable loader-time value snapshot."""

    reference: ReferenceType[HongKongV1CoverageMatrix]
    snapshot: _CoverageMatrixSnapshot


class LoaderIssuedMatrixRegistry:
    """Weak identity-and-value registrations for matrices issued by the loader."""

    def __init__(
        self,
        identity_key: Callable[[HongKongV1CoverageMatrix], int] = id,
    ) -> None:
        self._identity_key = identity_key
        self._registrations: dict[int, _IssuedMatrixRegistration] = {}

    def __len__(self) -> int:
        """Return the number of live registry entries."""
        return len(self._registrations)

    def is_issued(self, matrix: HongKongV1CoverageMatrix) -> bool:
        """Require exact identity and exact equality with every loader-time field."""
        registration = self._registrations.get(self._identity_key(matrix))
        if registration is None or registration.reference() is not matrix:
            return False
        current_snapshot = _coverage_matrix_snapshot(matrix)
        return current_snapshot is not None and current_snapshot == registration.snapshot

    def register(
        self,
        matrix: HongKongV1CoverageMatrix,
    ) -> ReferenceType[HongKongV1CoverageMatrix]:
        """Register immutable primitive values weakly and return the identity token."""
        snapshot = _coverage_matrix_snapshot(matrix)
        if snapshot is None:
            _raise("MATRIX_PROVENANCE_INVALID")
        matrix_id = self._identity_key(matrix)

        def remove_issued_matrix(
            issued_reference: ReferenceType[HongKongV1CoverageMatrix],
        ) -> None:
            registration = self._registrations.get(matrix_id)
            if registration is not None and registration.reference is issued_reference:
                del self._registrations[matrix_id]

        issued_reference = ref(matrix, remove_issued_matrix)
        self._registrations[matrix_id] = _IssuedMatrixRegistration(
            reference=issued_reference,
            snapshot=snapshot,
        )
        return issued_reference


def _coverage_matrix_snapshot(matrix: object) -> _CoverageMatrixSnapshot | None:
    """Copy all decoded matrix values into immutable primitive tuples."""
    if type(matrix) is not HongKongV1CoverageMatrix:
        return None
    if any(
        type(value) is not str
        for value in (matrix.revision, matrix.effective_date, matrix.fingerprint)
    ):
        return None
    if (
        type(matrix.rows) is not tuple
        or type(matrix.explicit_exclusions) is not tuple
        or type(matrix.included_material_families) is not tuple
    ):
        return None
    if any(
        type(value) is not str
        for values in (matrix.explicit_exclusions, matrix.included_material_families)
        for value in values
    ):
        return None
    row_snapshots: list[_CoverageMatrixRowSnapshot] = []
    for row in matrix.rows:
        snapshot = _coverage_matrix_row_snapshot(row)
        if snapshot is None:
            return None
        row_snapshots.append(snapshot)
    return (
        matrix.revision,
        matrix.effective_date,
        tuple(row_snapshots),
        matrix.explicit_exclusions,
        matrix.included_material_families,
        matrix.fingerprint,
    )


def _coverage_matrix_row_snapshot(row: object) -> _CoverageMatrixRowSnapshot | None:
    """Copy every decoded row value without retaining a mutable object reference."""
    if type(row) is not CoverageMatrixRow:
        return None
    values = (
        row.scope_id,
        row.material_family,
        row.source_id,
        row.fact_authority,
        row.owner,
        row.earliest_boundary,
        row.cutoff_rule,
        row.cadence,
        row.technical_state,
        row.rights_state,
        row.outage_consequence,
        row.exclusion_code,
        row.limitation_text,
    )
    if any(type(value) is not str for value in values):
        return None
    return values


_LoaderIssuedMatrixRegistry = LoaderIssuedMatrixRegistry
_ISSUED_MATRIX_REGISTRY = LoaderIssuedMatrixRegistry()


def load_hk_v1_coverage_matrix(path: Path | None = None) -> HongKongV1CoverageMatrix:
    """Load, canonical-byte-check, and freeze one exact Coverage Matrix."""
    matrix_path = _DEFAULT_MATRIX_PATH if path is None else path
    return _decode_matrix(matrix_path.read_bytes())


def is_hk_v1_coverage_matrix_issued(matrix: object) -> bool:
    """Expose exact loader provenance for consumers that freeze dependent policy."""
    return _is_loader_issued(matrix)


def is_hk_v1_coverage_matrix_policy_approved(matrix: HongKongV1CoverageMatrix) -> bool:
    """Require one loader-issued Matrix to equal the repository-approved policy exactly."""
    return _scope_gate_validation_error(matrix) is None


def evaluate_hk_v1_scope_gate(
    matrix: HongKongV1CoverageMatrix,
) -> HongKongV1ScopeGateResult:
    """Fail closed until the exact V1 inventory and every source admission exist."""
    validation_error = _scope_gate_validation_error(matrix)
    if validation_error is not None:
        return HongKongV1ScopeGateResult("NOT_ADMITTED", (validation_error,))
    active_rows = tuple(
        row for row in matrix.rows if (row.scope_id, row.source_id) not in _EXCLUDED_SOURCE_PAIRS
    )
    blockers: list[str] = []
    if any(row.technical_state != "ADMITTED" for row in active_rows):
        blockers.append("SOURCE_TECHNICAL_ADMISSION_MISSING")
    if any(row.rights_state != "ADMITTED" for row in active_rows):
        blockers.append("SOURCE_RIGHTS_ADMISSION_MISSING")
    return HongKongV1ScopeGateResult(
        "ADMITTED" if not blockers else "NOT_ADMITTED",
        tuple(blockers),
    )


def build_hk_v1_two_family_coverage_report(
    matrix: HongKongV1CoverageMatrix,
    acquisitions: tuple[FamilyAcquisitionCoverage, ...],
    capabilities: tuple[VerifiedSemanticCapability, ...],
) -> HongKongV1TwoFamilyCoverageReport:
    """Freeze a report from exact reader-verified disabled capabilities."""
    try:
        verified = tuple(validate_verified_semantic_capability(item) for item in capabilities)
    except (ProposalEvidenceError, TypeError) as error:
        code = "TWO_FAMILY_COVERAGE_CAPABILITY_INVALID"
        raise HongKongV1CoverageError(code) from error
    projected = tuple(
        SemanticCapabilityCoverage(
            item.capability,
            item.profile_fingerprint,
            item.evidence_ref,
            item.status,
        )
        for item in verified
    )
    return _build_hk_v1_two_family_coverage_report(matrix, acquisitions, projected)


def _build_hk_v1_two_family_coverage_report(
    matrix: HongKongV1CoverageMatrix,
    acquisitions: tuple[FamilyAcquisitionCoverage, ...],
    capabilities: tuple[SemanticCapabilityCoverage, ...],
) -> HongKongV1TwoFamilyCoverageReport:
    """Build after issuer provenance or canonical report parsing was established."""
    if _scope_gate_validation_error(matrix) is not None:
        _raise("TWO_FAMILY_COVERAGE_MATRIX_INVALID")
    if type(acquisitions) is not tuple or tuple(
        item.material_family for item in acquisitions if type(item) is FamilyAcquisitionCoverage
    ) != ("CASES", "LEGISLATION"):
        _raise("TWO_FAMILY_COVERAGE_ACQUISITION_INVALID")
    if any(type(item) is not FamilyAcquisitionCoverage for item in acquisitions):
        _raise("TWO_FAMILY_COVERAGE_ACQUISITION_INVALID")
    cases = acquisitions[0]
    expected_scopes = {
        "CASES": ("HK-CASE-BINDING-POST-1997",),
        "LEGISLATION": tuple(
            sorted(scope for scope in _V1_REQUIRED_SCOPE_IDS if scope.startswith("HK-LEG-"))
        ),
    }
    cutoff = cases.observation_cutoff
    for item in acquisitions:
        if (
            not _is_text(item.cycle_id)
            or item.observation_cutoff != cutoff
            or item.scope_ids != expected_scopes[item.material_family]
            or _FINGERPRINT_PATTERN.fullmatch(item.manifest_fingerprint) is None
            or _FINGERPRINT_PATTERN.fullmatch(item.journal_head_fingerprint) is None
            or type(item.retryable_count) is not int
            or item.retryable_count != 0
            or not _valid_acquisition_reference_sequences(item)
        ):
            _raise("TWO_FAMILY_COVERAGE_ACQUISITION_INVALID")
    if (
        type(capabilities) is not tuple
        or tuple(
            item.capability for item in capabilities if type(item) is SemanticCapabilityCoverage
        )
        != ("EMBEDDING", "MODEL")
        or any(type(item) is not SemanticCapabilityCoverage for item in capabilities)
    ):
        _raise("TWO_FAMILY_COVERAGE_CAPABILITY_INVALID")
    for capability in capabilities:
        if (
            _FINGERPRINT_PATTERN.fullmatch(capability.profile_fingerprint) is None
            or not _is_text(capability.evidence_ref)
            or capability.status != "PROVIDER_DISABLED_PREPARATION_ONLY"
        ):
            _raise("TWO_FAMILY_COVERAGE_CAPABILITY_INVALID")
    scope_ids = tuple(sorted(_V1_REQUIRED_SCOPE_IDS))
    body = checked_json_value(
        {
            "schema_id": "asklegal.hk-v1-two-family-coverage-report/v1",
            "observation_cutoff": cutoff,
            "included_material_families": list(matrix.included_material_families),
            "scope_ids": list(scope_ids),
            "explicit_exclusions": list(matrix.explicit_exclusions),
            "acquisitions": [
                {
                    "material_family": item.material_family,
                    "cycle_id": item.cycle_id,
                    "manifest_fingerprint": item.manifest_fingerprint,
                    "journal_head_fingerprint": item.journal_head_fingerprint,
                    "retryable_count": item.retryable_count,
                    "review_issue_refs": list(item.review_issue_refs),
                    "verified_evidence_refs": list(item.verified_evidence_refs),
                    "scope_ids": list(item.scope_ids),
                }
                for item in acquisitions
            ],
            "capabilities": [
                {
                    "capability": item.capability,
                    "profile_fingerprint": item.profile_fingerprint,
                    "evidence_ref": item.evidence_ref,
                    "status": item.status,
                }
                for item in capabilities
            ],
        }
    )
    fingerprint = _fingerprint(canonicalize(body))
    if type(body) is not dict:  # pragma: no cover - checked literal is an object.
        _raise("TWO_FAMILY_COVERAGE_REPORT_INVALID")
    content = canonicalize({**body, "fingerprint": fingerprint})
    return HongKongV1TwoFamilyCoverageReport(
        observation_cutoff=cutoff,
        included_material_families=matrix.included_material_families,
        scope_ids=scope_ids,
        explicit_exclusions=matrix.explicit_exclusions,
        acquisitions=acquisitions,
        capabilities=capabilities,
        content=content,
        fingerprint=fingerprint,
    )


def _valid_acquisition_reference_sequences(item: FamilyAcquisitionCoverage) -> bool:
    if (
        type(item.review_issue_refs) is not tuple
        or type(item.verified_evidence_refs) is not tuple
        or any(
            not _is_text(value)
            for values in (item.review_issue_refs, item.verified_evidence_refs)
            for value in values
        )
    ):
        return False
    if item.material_family == "CASES":
        return len(set(item.verified_evidence_refs)) == len(item.verified_evidence_refs)
    return (
        bool(item.verified_evidence_refs)
        and item.verified_evidence_refs == tuple(sorted(set(item.verified_evidence_refs)))
        and item.review_issue_refs == tuple(sorted(set(item.review_issue_refs)))
    )


def parse_hk_v1_two_family_coverage_report(
    content: bytes,
) -> HongKongV1TwoFamilyCoverageReport:
    """Strictly reread one canonical report against the repository-issued Matrix."""
    code = "TWO_FAMILY_COVERAGE_REPORT_INVALID"
    try:
        document = parse_json_bytes(content, max_bytes=_MAX_MATRIX_BYTES)
        expected_fields = {
            "schema_id",
            "observation_cutoff",
            "included_material_families",
            "scope_ids",
            "explicit_exclusions",
            "acquisitions",
            "capabilities",
            "fingerprint",
        }
        if (
            type(document) is not dict
            or set(document) != expected_fields
            or canonicalize(document) != content
            or document["schema_id"] != "asklegal.hk-v1-two-family-coverage-report/v1"
        ):
            _raise(code)
        fingerprint = _text(document["fingerprint"], code)
        unsigned = {key: value for key, value in document.items() if key != "fingerprint"}
        if fingerprint != _fingerprint(canonicalize(unsigned)):
            _raise(code)
        acquisitions = tuple(
            _report_acquisition(item, _text(document["observation_cutoff"], code))
            for item in _report_objects(document["acquisitions"], 2)
        )
        capabilities = tuple(
            SemanticCapabilityCoverage(
                capability=_report_capability(item["capability"]),
                profile_fingerprint=_text(item["profile_fingerprint"], code),
                evidence_ref=_text(item["evidence_ref"], code),
                status=_report_capability_status(item["status"]),
            )
            for item in _report_objects(document["capabilities"], 2)
        )
        rebuilt = _build_hk_v1_two_family_coverage_report(
            load_hk_v1_coverage_matrix(), acquisitions, capabilities
        )
    except (KeyError, TypeError, ValueError, ContractViolation) as error:
        raise HongKongV1CoverageError(code) from error
    if rebuilt.content != content:
        _raise(code)
    return rebuilt


def _report_objects(value: JsonValue, count: int) -> tuple[dict[str, JsonValue], ...]:
    if (
        type(value) is not list
        or len(value) != count
        or any(type(item) is not dict for item in value)
    ):
        _raise("TWO_FAMILY_COVERAGE_REPORT_INVALID")
    return tuple(item for item in value if type(item) is dict)


def _report_acquisition(
    item: dict[str, JsonValue], observation_cutoff: str
) -> FamilyAcquisitionCoverage:
    code = "TWO_FAMILY_COVERAGE_REPORT_INVALID"
    expected = {
        "material_family",
        "cycle_id",
        "manifest_fingerprint",
        "journal_head_fingerprint",
        "retryable_count",
        "review_issue_refs",
        "verified_evidence_refs",
        "scope_ids",
    }
    if set(item) != expected:
        _raise(code)
    family = _report_family(item["material_family"])
    reviews = (
        _report_text_sequence(item["review_issue_refs"])
        if family == "CASES"
        else _report_text_tuple(item["review_issue_refs"])
    )
    evidence_refs = (
        _report_unique_text_sequence(item["verified_evidence_refs"])
        if family == "CASES"
        else _report_text_tuple(item["verified_evidence_refs"])
    )
    return FamilyAcquisitionCoverage(
        material_family=family,
        cycle_id=_text(item["cycle_id"], code),
        observation_cutoff=observation_cutoff,
        scope_ids=_report_text_tuple(item["scope_ids"]),
        manifest_fingerprint=_text(item["manifest_fingerprint"], code),
        journal_head_fingerprint=_text(item["journal_head_fingerprint"], code),
        retryable_count=_report_count(item["retryable_count"]),
        review_issue_refs=reviews,
        verified_evidence_refs=evidence_refs,
    )


def _report_text_tuple(value: JsonValue) -> tuple[str, ...]:
    if type(value) is not list:
        _raise("TWO_FAMILY_COVERAGE_REPORT_INVALID")
    result = tuple(_text(item, "TWO_FAMILY_COVERAGE_REPORT_INVALID") for item in value)
    if result != tuple(sorted(set(result))):
        _raise("TWO_FAMILY_COVERAGE_REPORT_INVALID")
    return result


def _report_text_sequence(value: JsonValue) -> tuple[str, ...]:
    if type(value) is not list:
        _raise("TWO_FAMILY_COVERAGE_REPORT_INVALID")
    return tuple(_text(item, "TWO_FAMILY_COVERAGE_REPORT_INVALID") for item in value)


def _report_unique_text_sequence(value: JsonValue) -> tuple[str, ...]:
    result = _report_text_sequence(value)
    if len(set(result)) != len(result):
        _raise("TWO_FAMILY_COVERAGE_REPORT_INVALID")
    return result


def _report_count(value: JsonValue) -> int:
    if type(value) is not int or value < 0:
        _raise("TWO_FAMILY_COVERAGE_REPORT_INVALID")
    return value


def _report_family(value: JsonValue) -> Literal["LEGISLATION", "CASES"]:
    family = _text(value, "TWO_FAMILY_COVERAGE_REPORT_INVALID")
    if family == "LEGISLATION":
        return "LEGISLATION"
    if family == "CASES":
        return "CASES"
    return _raise("TWO_FAMILY_COVERAGE_REPORT_INVALID")


def _report_capability(value: JsonValue) -> Literal["MODEL", "EMBEDDING"]:
    capability = _text(value, "TWO_FAMILY_COVERAGE_REPORT_INVALID")
    if capability == "MODEL":
        return "MODEL"
    if capability == "EMBEDDING":
        return "EMBEDDING"
    return _raise("TWO_FAMILY_COVERAGE_REPORT_INVALID")


def _report_capability_status(
    value: JsonValue,
) -> Literal["PROVIDER_DISABLED_PREPARATION_ONLY"]:
    if _text(value, "TWO_FAMILY_COVERAGE_REPORT_INVALID") != ("PROVIDER_DISABLED_PREPARATION_ONLY"):
        _raise("TWO_FAMILY_COVERAGE_REPORT_INVALID")
    return "PROVIDER_DISABLED_PREPARATION_ONLY"


def _scope_gate_validation_error(matrix: HongKongV1CoverageMatrix) -> str | None:
    error: str | None = None
    if not _is_loader_issued(matrix):
        error = "MATRIX_PROVENANCE_INVALID"
    elif (runtime_error := _matrix_runtime_error(matrix)) is not None:
        error = runtime_error
    else:
        scope_ids = frozenset(row.scope_id for row in matrix.rows)
        scope_source_pairs = frozenset((row.scope_id, row.source_id) for row in matrix.rows)
        if frozenset(matrix.included_material_families) != _V1_INCLUDED_MATERIAL_FAMILIES:
            error = "INCLUDED_MATERIAL_FAMILY_INVALID"
        elif scope_ids != _V1_REQUIRED_SCOPE_IDS:
            error = "SCOPE_INVENTORY_INVALID"
        elif any(
            _V1_REQUIRED_SCOPE_MATERIAL_FAMILIES[row.scope_id] != row.material_family
            for row in matrix.rows
        ):
            error = "SCOPE_MATERIAL_FAMILY_INVALID"
        elif frozenset(matrix.explicit_exclusions) != _REQUIRED_EXCLUSIONS:
            error = "EXCLUSION_INVENTORY_INVALID"
        elif scope_source_pairs != _REQUIRED_SCOPE_SOURCE_PAIRS:
            error = "SOURCE_ROLE_INVENTORY_INVALID"
        elif not _source_role_exclusions_are_exact(matrix.rows):
            error = "SOURCE_ROLE_EXCLUSION_INVALID"
        else:
            error = _approved_policy_error(matrix)
    return error


def _approved_policy_error(matrix: HongKongV1CoverageMatrix) -> str | None:
    approved = load_hk_v1_coverage_matrix()
    if (
        matrix.revision != approved.revision
        or matrix.effective_date != approved.effective_date
        or matrix.explicit_exclusions != approved.explicit_exclusions
        or matrix.included_material_families != approved.included_material_families
    ):
        return "MATRIX_POLICY_INVALID"
    if tuple(_row_policy_projection(row) for row in matrix.rows) != tuple(
        _row_policy_projection(row) for row in approved.rows
    ):
        return "SOURCE_ROLE_POLICY_INVALID"
    if _coverage_matrix_snapshot(matrix) != _coverage_matrix_snapshot(approved):
        return "MATRIX_POLICY_INVALID"
    return None


def _row_policy_projection(row: CoverageMatrixRow) -> tuple[str, ...]:
    return (
        row.scope_id,
        row.source_id,
        row.material_family,
        row.fact_authority,
        row.owner,
        row.earliest_boundary,
        row.cutoff_rule,
        row.cadence,
        row.outage_consequence,
        row.exclusion_code,
        row.limitation_text,
    )


def _decode_matrix(content: bytes) -> HongKongV1CoverageMatrix:
    if type(content) is not bytes:
        _raise("MATRIX_CONTENT_INVALID")
    try:
        document = parse_json_bytes(content, max_bytes=_MAX_MATRIX_BYTES)
    except ContractViolation as error:
        code = "MATRIX_JSON_INVALID"
        raise HongKongV1CoverageError(code) from error
    if not isinstance(document, dict) or frozenset(document) != _MATRIX_FIELDS:
        _raise("MATRIX_FIELDS_INVALID")
    if canonicalize(document) != content:
        _raise("MATRIX_CANONICAL_BYTES_INVALID")

    revision = _text(document["revision"], "MATRIX_VALUE_INVALID")
    effective_date = _text(document["effective_date"], "MATRIX_VALUE_INVALID")
    decoded_rows = _decode_rows(document["rows"])
    explicit_exclusions = _decode_exclusions(document["explicit_exclusions"])
    included_material_families = _decode_included_material_families(
        document["included_material_families"]
    )
    fingerprint = _text(document["fingerprint"], "MATRIX_FINGERPRINT_INVALID")
    if _FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
        _raise("MATRIX_FINGERPRINT_INVALID")
    unsigned_document = dict(document)
    del unsigned_document["fingerprint"]
    expected_fingerprint = _fingerprint(canonicalize(unsigned_document))
    if fingerprint != expected_fingerprint:
        _raise("MATRIX_FINGERPRINT_MISMATCH")

    rows = tuple(sorted(decoded_rows, key=lambda row: (row.scope_id, row.source_id)))
    matrix = HongKongV1CoverageMatrix(
        revision=revision,
        effective_date=effective_date,
        rows=rows,
        explicit_exclusions=explicit_exclusions,
        included_material_families=included_material_families,
        fingerprint=fingerprint,
    )
    _register_loader_issued(matrix)
    return matrix


def _decode_rows(value: JsonValue) -> tuple[CoverageMatrixRow, ...]:
    if not isinstance(value, list) or not value:
        _raise("MATRIX_ROWS_INVALID")
    rows = tuple(_decode_row(item) for item in value)
    if len({(row.scope_id, row.source_id) for row in rows}) != len(rows):
        _raise("MATRIX_ROW_DUPLICATE")
    return rows


def _decode_row(value: JsonValue) -> CoverageMatrixRow:
    if not isinstance(value, dict) or frozenset(value) != _ROW_FIELDS:
        _raise("MATRIX_ROW_FIELDS_INVALID")
    return CoverageMatrixRow(
        scope_id=_text(value["scope_id"], "MATRIX_ROW_VALUE_INVALID"),
        material_family=_material_family(value["material_family"]),
        source_id=_text(value["source_id"], "MATRIX_ROW_VALUE_INVALID"),
        fact_authority=_text(value["fact_authority"], "MATRIX_ROW_VALUE_INVALID"),
        owner=_owner(value["owner"]),
        earliest_boundary=_text(value["earliest_boundary"], "MATRIX_ROW_VALUE_INVALID"),
        cutoff_rule=_text(value["cutoff_rule"], "MATRIX_ROW_VALUE_INVALID"),
        cadence=_text(value["cadence"], "MATRIX_ROW_VALUE_INVALID"),
        technical_state=_admission_state(value["technical_state"]),
        rights_state=_admission_state(value["rights_state"]),
        outage_consequence=_outage_consequence(value["outage_consequence"]),
        exclusion_code=_text(value["exclusion_code"], "MATRIX_ROW_VALUE_INVALID", allow_empty=True),
        limitation_text=_text(value["limitation_text"], "MATRIX_ROW_VALUE_INVALID"),
    )


def _decode_exclusions(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, list):
        _raise("MATRIX_EXCLUSIONS_INVALID")
    exclusions = tuple(_text(item, "MATRIX_EXCLUSIONS_INVALID") for item in value)
    if exclusions != tuple(sorted(set(exclusions))):
        _raise("MATRIX_EXCLUSIONS_INVALID")
    return exclusions


def _decode_included_material_families(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, list):
        _raise("MATRIX_INCLUDED_MATERIAL_FAMILIES_INVALID")
    families = tuple(_text(item, "MATRIX_INCLUDED_MATERIAL_FAMILIES_INVALID") for item in value)
    if (
        families != tuple(sorted(set(families)))
        or not families
        or not frozenset(families) <= _MATERIAL_FAMILIES
    ):
        _raise("MATRIX_INCLUDED_MATERIAL_FAMILIES_INVALID")
    return families


def _matrix_runtime_error(matrix: object) -> str | None:
    if type(matrix) is not HongKongV1CoverageMatrix:
        return "MATRIX_INVALID"
    fields_error = _matrix_fields_runtime_error(matrix)
    if fields_error is not None:
        return fields_error
    rows_error = _matrix_rows_runtime_error(matrix.rows)
    if rows_error is not None:
        return rows_error
    return None


def _matrix_fields_runtime_error(matrix: HongKongV1CoverageMatrix) -> str | None:
    if not _is_text(matrix.revision) or not _is_text(matrix.effective_date):
        return "MATRIX_VALUE_INVALID"
    if type(matrix.explicit_exclusions) is not tuple:
        return "MATRIX_EXCLUSIONS_INVALID"
    exclusions = matrix.explicit_exclusions
    if any(not _is_text(exclusion) for exclusion in exclusions) or exclusions != tuple(
        sorted(set(exclusions))
    ):
        return "MATRIX_EXCLUSIONS_INVALID"
    if type(matrix.included_material_families) is not tuple:
        return "MATRIX_INCLUDED_MATERIAL_FAMILIES_INVALID"
    families = matrix.included_material_families
    if (
        any(not _is_text(family) for family in families)
        or families != tuple(sorted(set(families)))
        or not frozenset(families) <= _MATERIAL_FAMILIES
    ):
        return "MATRIX_INCLUDED_MATERIAL_FAMILIES_INVALID"
    return None


def _matrix_rows_runtime_error(rows: tuple[CoverageMatrixRow, ...]) -> str | None:
    if type(rows) is not tuple or not rows:
        return "MATRIX_ROWS_INVALID"
    if any(type(row) is not CoverageMatrixRow for row in rows):
        return "MATRIX_ROW_INVALID"
    if any(_row_runtime_error(row) is not None for row in rows):
        return "MATRIX_ROW_VALUE_INVALID"
    if len({(row.scope_id, row.source_id) for row in rows}) != len(rows):
        return "MATRIX_ROW_DUPLICATE"
    if rows != tuple(sorted(rows, key=lambda row: (row.scope_id, row.source_id))):
        return "MATRIX_ROWS_INVALID"
    return None


def _source_role_exclusions_are_exact(rows: tuple[CoverageMatrixRow, ...]) -> bool:
    for row in rows:
        pair = (row.scope_id, row.source_id)
        if pair == _EXCLUDED_PRIVY_COUNCIL_PAIR:
            if (
                row.exclusion_code != "HK-CASE-PRE-1997"
                or row.cadence != "EXCLUDED_FROM_V1"
                or row.earliest_boundary != "1997-07-01"
                or row.cutoff_rule != _EXCLUDED_PRIVY_COUNCIL_CUTOFF_RULE
                or row.limitation_text != _EXCLUDED_PRIVY_COUNCIL_LIMITATION
            ):
                return False
        elif pair[0] == _NPC_SCOPE_ID and pair[1] in _NPC_SOURCE_IDS:
            if (
                row.exclusion_code != _NPC_EXCLUSION_CODE
                or row.cadence != "EXCLUDED_FROM_V1"
                or row.limitation_text != _NPC_LIMITATION
                or row.technical_state != "NOT_ADMITTED"
                or row.rights_state != "NOT_ADMITTED"
            ):
                return False
        elif row.exclusion_code:
            return False
    return True


def _row_runtime_error(row: CoverageMatrixRow) -> str | None:
    if not all(
        _is_text(value, allow_empty=field == "exclusion_code")
        for field, value in (
            ("scope_id", row.scope_id),
            ("source_id", row.source_id),
            ("fact_authority", row.fact_authority),
            ("earliest_boundary", row.earliest_boundary),
            ("cutoff_rule", row.cutoff_rule),
            ("cadence", row.cadence),
            ("exclusion_code", row.exclusion_code),
            ("limitation_text", row.limitation_text),
        )
    ):
        return "MATRIX_ROW_VALUE_INVALID"
    if (
        row.material_family not in _MATERIAL_FAMILIES
        or row.owner not in _OWNERS
        or row.technical_state not in _ADMISSION_STATES
        or row.rights_state not in _ADMISSION_STATES
        or row.outage_consequence not in _OUTAGE_CONSEQUENCES
    ):
        return "MATRIX_ROW_VALUE_INVALID"
    return None


def _material_family(value: JsonValue) -> Literal["LEGISLATION", "CASES", "REGULATORY"]:
    result = _text(value, "MATRIX_ROW_VALUE_INVALID")
    if result == "LEGISLATION":
        return "LEGISLATION"
    if result == "CASES":
        return "CASES"
    if result == "REGULATORY":
        return "REGULATORY"
    return _raise("MATRIX_ROW_VALUE_INVALID")


def _owner(value: JsonValue) -> Literal["ACQUISITION", "LEGAL_PROCESSING", "CONTROL"]:
    result = _text(value, "MATRIX_ROW_VALUE_INVALID")
    if result == "ACQUISITION":
        return "ACQUISITION"
    if result == "LEGAL_PROCESSING":
        return "LEGAL_PROCESSING"
    if result == "CONTROL":
        return "CONTROL"
    return _raise("MATRIX_ROW_VALUE_INVALID")


def _admission_state(value: JsonValue) -> Literal["ADMITTED", "NOT_ADMITTED"]:
    result = _text(value, "MATRIX_ROW_VALUE_INVALID")
    if result == "ADMITTED":
        return "ADMITTED"
    if result == "NOT_ADMITTED":
        return "NOT_ADMITTED"
    return _raise("MATRIX_ROW_VALUE_INVALID")


def _outage_consequence(
    value: JsonValue,
) -> Literal["RELEASE_BLOCKING", "AFFECTED_WORK_BLOCKING", "NONBLOCKING"]:
    result = _text(value, "MATRIX_ROW_VALUE_INVALID")
    if result == "RELEASE_BLOCKING":
        return "RELEASE_BLOCKING"
    if result == "AFFECTED_WORK_BLOCKING":
        return "AFFECTED_WORK_BLOCKING"
    if result == "NONBLOCKING":
        return "NONBLOCKING"
    return _raise("MATRIX_ROW_VALUE_INVALID")


def _text(value: JsonValue, code: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or value.strip() != value or (not value and not allow_empty):
        _raise(code)
    return value


def _is_text(value: object, *, allow_empty: bool = False) -> bool:
    return type(value) is str and value.strip() == value and (bool(value) or allow_empty)


def _is_loader_issued(matrix: object) -> bool:
    if type(matrix) is not HongKongV1CoverageMatrix:
        return False
    return _ISSUED_MATRIX_REGISTRY.is_issued(matrix)


def _register_loader_issued(matrix: HongKongV1CoverageMatrix) -> None:
    _ISSUED_MATRIX_REGISTRY.register(matrix)


def _fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _raise(code: str) -> Never:
    raise HongKongV1CoverageError(code)


__all__ = [
    "CoverageMatrixRow",
    "FamilyAcquisitionCoverage",
    "HongKongV1CoverageError",
    "HongKongV1CoverageMatrix",
    "HongKongV1ScopeGateResult",
    "HongKongV1TwoFamilyCoverageReport",
    "SemanticCapabilityCoverage",
    "build_hk_v1_two_family_coverage_report",
    "evaluate_hk_v1_scope_gate",
    "is_hk_v1_coverage_matrix_policy_approved",
    "load_hk_v1_coverage_matrix",
    "parse_hk_v1_two_family_coverage_report",
]
