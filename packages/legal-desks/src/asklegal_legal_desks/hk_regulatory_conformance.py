"""Closed ADR 0074/0075 HKEX Regulatory conformance universe."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch

from asklegal_contracts import ContractViolation, fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value

HKEX_CONFORMANCE_UNIVERSE_RULE_ID = "HKREG-CONFORMANCE-UNIVERSE-001"
HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION = "1.0.0"
HKEX_CONFORMANCE_CASE_COUNT = 284
HKEX_CONFORMANCE_COVERAGE_CELL_COUNT = 284
HKEX_CONFORMANCE_PAIR_COUNT = 57
HKEX_CONFORMANCE_DESIGN_SOURCE_FINGERPRINT = (
    "sha256:fd5b7d1da524e260411a36a8aa8817e83769130a0209941936c3866d52316ce5"
)


class HKEXConformanceErrorCode(StrEnum):
    """Closed malformed or incomplete universe failures."""

    CONTRACT = "HKREG_CONFORMANCE_CONTRACT_INVALID"
    IDENTITY = "HKREG_CONFORMANCE_IDENTITY_INVALID"
    ARITHMETIC = "HKREG_CONFORMANCE_ARITHMETIC_INVALID"
    PAIR = "HKREG_CONFORMANCE_PAIR_INVALID"
    SOURCE = "HKREG_CONFORMANCE_DESIGN_SOURCE_INVALID"


class HKEXConformanceError(ValueError):
    """One fail-closed conformance-universe rejection."""

    code: HKEXConformanceErrorCode

    def __init__(self, code: HKEXConformanceErrorCode) -> None:
        """Create one stable contract failure."""
        self.code = code
        super().__init__(code.value)


class HKEXConformanceLayer(StrEnum):
    """The two linked and non-substitutable ADR 0074 layers."""

    EVIDENCE_TO_DECISION = "EVIDENCE_TO_DECISION"
    DECISION_TO_ARTIFACT = "DECISION_TO_ARTIFACT"


class HKEXConformanceCheckpoint(StrEnum):
    """The eight permanent ADR 0075 primary checkpoints."""

    SOURCE_FACT_AUTHORITY = "SOURCE_FACT_AUTHORITY"
    EFFECTIVE_STATE = "EFFECTIVE_STATE"
    RECORD_BOUNDARY = "RECORD_BOUNDARY"
    CANONICAL_RENDERING = "CANONICAL_RENDERING"
    PARTITIONING = "PARTITIONING"
    SOURCE_UNIT_COVERAGE = "SOURCE_UNIT_COVERAGE"
    RECORD_IDENTITY = "RECORD_IDENTITY"
    PACKAGE_INTEGRITY = "PACKAGE_INTEGRITY"


class HKEXConformancePairRole(StrEnum):
    """Exact controlled distinction membership."""

    POSITIVE = "POSITIVE"
    NEAR_MISS = "NEAR_MISS"


@dataclass(frozen=True, slots=True)
class HKEXConformancePairMembership:
    """One case's role in one permanent high-risk pair."""

    pair_id: str
    role: HKEXConformancePairRole


@dataclass(frozen=True, slots=True)
class HKEXConformanceCase:
    """One permanent direct case and matching primary coverage cell."""

    case_id: str
    coverage_cell_id: str
    layer: HKEXConformanceLayer
    primary_checkpoint: HKEXConformanceCheckpoint
    synthetic_scenario: str
    exact_required_result: str
    pair_memberships: tuple[HKEXConformancePairMembership, ...]


@dataclass(frozen=True, slots=True)
class HKEXConformancePair:
    """One complete positive/near-miss pair index entry."""

    pair_id: str
    positive_case_id: str
    near_miss_case_id: str


@dataclass(frozen=True, slots=True)
class HKEXConformanceCheckpointCount:
    """One exact namespace and count from ADR 0075."""

    checkpoint: HKEXConformanceCheckpoint
    layer: HKEXConformanceLayer
    case_namespace: str
    coverage_namespace: str
    direct_case_count: int


@dataclass(frozen=True, slots=True)
class HKEXConformanceUniverseProof:
    """Complete catalogue arithmetic without executable-case readiness."""

    catalogue_fingerprint: str
    design_source_fingerprint: str
    cases: tuple[HKEXConformanceCase, ...]
    pair_index: tuple[HKEXConformancePair, ...]
    checkpoint_counts: tuple[HKEXConformanceCheckpointCount, ...]
    case_count: int
    coverage_cell_count: int
    pair_count: int
    all_case_identities_contiguous: bool
    every_case_has_one_primary_cell: bool
    every_pair_complete: bool
    case_packages_complete: bool
    conformance_ready: bool
    activation_authorized: bool
    external_effects: str


_EXPECTED_CHECKPOINTS = (
    (
        HKEXConformanceCheckpoint.SOURCE_FACT_AUTHORITY,
        HKEXConformanceLayer.EVIDENCE_TO_DECISION,
        "HKREG-DEC-SRC",
        "HKREG-COV-DSRC",
        62,
    ),
    (
        HKEXConformanceCheckpoint.EFFECTIVE_STATE,
        HKEXConformanceLayer.EVIDENCE_TO_DECISION,
        "HKREG-DEC-STA",
        "HKREG-COV-DSTA",
        51,
    ),
    (
        HKEXConformanceCheckpoint.RECORD_BOUNDARY,
        HKEXConformanceLayer.EVIDENCE_TO_DECISION,
        "HKREG-DEC-BND",
        "HKREG-COV-DBND",
        30,
    ),
    (
        HKEXConformanceCheckpoint.CANONICAL_RENDERING,
        HKEXConformanceLayer.DECISION_TO_ARTIFACT,
        "HKREG-DET-RND",
        "HKREG-COV-DRND",
        35,
    ),
    (
        HKEXConformanceCheckpoint.PARTITIONING,
        HKEXConformanceLayer.DECISION_TO_ARTIFACT,
        "HKREG-DET-PAR",
        "HKREG-COV-DPAR",
        24,
    ),
    (
        HKEXConformanceCheckpoint.SOURCE_UNIT_COVERAGE,
        HKEXConformanceLayer.DECISION_TO_ARTIFACT,
        "HKREG-DET-COV",
        "HKREG-COV-DCOV",
        20,
    ),
    (
        HKEXConformanceCheckpoint.RECORD_IDENTITY,
        HKEXConformanceLayer.DECISION_TO_ARTIFACT,
        "HKREG-DET-IDN",
        "HKREG-COV-DIDN",
        24,
    ),
    (
        HKEXConformanceCheckpoint.PACKAGE_INTEGRITY,
        HKEXConformanceLayer.DECISION_TO_ARTIFACT,
        "HKREG-DET-PKG",
        "HKREG-COV-DPKG",
        38,
    ),
)


def validate_hkex_conformance_universe(document: object) -> HKEXConformanceUniverseProof:
    """Validate the complete frozen 284-case identity and pair universe."""
    root, canonical = _root(document)
    _exact_keys(
        root,
        {
            "schema_id",
            "schema_version",
            "catalogue_id",
            "catalogue_version",
            "status",
            "design_source_path",
            "design_source_fingerprint",
            "required_case_count",
            "required_coverage_cell_count",
            "required_pair_count",
            "checkpoint_counts",
            "cases",
            "pair_index",
            "case_packages_complete",
            "conformance_ready",
            "activation_authorized",
            "external_effects",
        },
    )
    _constant(root["schema_id"], "asklegal.hk-regulatory.conformance-universe")
    _constant(root["schema_version"], HKEX_CONFORMANCE_UNIVERSE_CONTRACT_VERSION)
    _constant(root["catalogue_id"], "hk-regulatory-initial")
    _constant(root["catalogue_version"], "1.0.0")
    _constant(root["status"], "FROZEN_EXECUTABLE_CASE_UNIVERSE")
    _constant(
        root["design_source_path"],
        "docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md",
    )
    design_source_fingerprint = _fingerprint(root["design_source_fingerprint"])
    if design_source_fingerprint != HKEX_CONFORMANCE_DESIGN_SOURCE_FINGERPRINT:
        raise HKEXConformanceError(HKEXConformanceErrorCode.SOURCE)
    _exact_integer(root["required_case_count"], HKEX_CONFORMANCE_CASE_COUNT)
    _exact_integer(
        root["required_coverage_cell_count"],
        HKEX_CONFORMANCE_COVERAGE_CELL_COUNT,
    )
    _exact_integer(root["required_pair_count"], HKEX_CONFORMANCE_PAIR_COUNT)
    checkpoint_counts = _checkpoint_counts(root["checkpoint_counts"])
    cases = _cases(root["cases"], checkpoint_counts)
    pair_index = _pairs(root["pair_index"], cases)
    _true(root["case_packages_complete"])
    _false(root["conformance_ready"])
    _false(root["activation_authorized"])
    _constant(root["external_effects"], "NONE")
    return HKEXConformanceUniverseProof(
        catalogue_fingerprint=fingerprint(canonical),
        design_source_fingerprint=design_source_fingerprint,
        cases=cases,
        pair_index=pair_index,
        checkpoint_counts=checkpoint_counts,
        case_count=len(cases),
        coverage_cell_count=len({case.coverage_cell_id for case in cases}),
        pair_count=len(pair_index),
        all_case_identities_contiguous=True,
        every_case_has_one_primary_cell=True,
        every_pair_complete=True,
        case_packages_complete=True,
        conformance_ready=False,
        activation_authorized=False,
        external_effects="NONE",
    )


def _root(document: object) -> tuple[dict[str, JsonValue], JsonValue]:
    try:
        canonical = checked_json_value(document)
    except ContractViolation as error:
        raise HKEXConformanceError(HKEXConformanceErrorCode.CONTRACT) from error
    return _object(canonical), canonical


def _checkpoint_counts(value: JsonValue) -> tuple[HKEXConformanceCheckpointCount, ...]:
    entries = _object_array(value)
    if len(entries) != len(_EXPECTED_CHECKPOINTS):
        raise HKEXConformanceError(HKEXConformanceErrorCode.ARITHMETIC)
    results: list[HKEXConformanceCheckpointCount] = []
    for entry, expected in zip(entries, _EXPECTED_CHECKPOINTS, strict=True):
        _exact_keys(
            entry,
            {
                "checkpoint",
                "layer",
                "case_namespace",
                "coverage_namespace",
                "direct_case_count",
            },
        )
        checkpoint, layer, case_namespace, coverage_namespace, count = expected
        _constant(entry["checkpoint"], checkpoint.value)
        _constant(entry["layer"], layer.value)
        _constant(entry["case_namespace"], case_namespace)
        _constant(entry["coverage_namespace"], coverage_namespace)
        _exact_integer(entry["direct_case_count"], count)
        results.append(
            HKEXConformanceCheckpointCount(
                checkpoint,
                layer,
                case_namespace,
                coverage_namespace,
                count,
            )
        )
    return tuple(results)


def _cases(
    value: JsonValue,
    checkpoints: tuple[HKEXConformanceCheckpointCount, ...],
) -> tuple[HKEXConformanceCase, ...]:
    entries = _object_array(value)
    if len(entries) != HKEX_CONFORMANCE_CASE_COUNT:
        raise HKEXConformanceError(HKEXConformanceErrorCode.ARITHMETIC)
    results: list[HKEXConformanceCase] = []
    offset = 0
    for checkpoint in checkpoints:
        group = entries[offset : offset + checkpoint.direct_case_count]
        for suffix, entry in enumerate(group, start=1):
            results.append(_case(entry, checkpoint, suffix))
        offset += checkpoint.direct_case_count
    if offset != len(entries):
        raise HKEXConformanceError(HKEXConformanceErrorCode.ARITHMETIC)
    case_ids = tuple(case.case_id for case in results)
    coverage_ids = tuple(case.coverage_cell_id for case in results)
    if len(set(case_ids)) != len(case_ids) or len(set(coverage_ids)) != len(coverage_ids):
        raise HKEXConformanceError(HKEXConformanceErrorCode.IDENTITY)
    return tuple(results)


def _case(
    value: dict[str, JsonValue],
    checkpoint: HKEXConformanceCheckpointCount,
    suffix: int,
) -> HKEXConformanceCase:
    _exact_keys(
        value,
        {
            "case_id",
            "coverage_cell_id",
            "layer",
            "primary_checkpoint",
            "synthetic_scenario",
            "exact_required_result",
            "pair_memberships",
        },
    )
    expected_suffix = f"{suffix:03d}"
    case_id = _constant(value["case_id"], f"{checkpoint.case_namespace}-{expected_suffix}")
    coverage_id = _constant(
        value["coverage_cell_id"],
        f"{checkpoint.coverage_namespace}-{expected_suffix}",
    )
    _constant(value["layer"], checkpoint.layer.value)
    _constant(value["primary_checkpoint"], checkpoint.checkpoint.value)
    memberships = _memberships(value["pair_memberships"])
    return HKEXConformanceCase(
        case_id=case_id,
        coverage_cell_id=coverage_id,
        layer=checkpoint.layer,
        primary_checkpoint=checkpoint.checkpoint,
        synthetic_scenario=_text(value["synthetic_scenario"]),
        exact_required_result=_text(value["exact_required_result"]),
        pair_memberships=memberships,
    )


def _memberships(value: JsonValue) -> tuple[HKEXConformancePairMembership, ...]:
    entries = _object_array(value)
    results: list[HKEXConformancePairMembership] = []
    for entry in entries:
        _exact_keys(entry, {"pair_id", "role"})
        pair_id = _pair_id(entry["pair_id"])
        role = _enum(entry["role"], HKEXConformancePairRole)
        results.append(HKEXConformancePairMembership(pair_id, role))
    keys = tuple((item.pair_id, item.role.value) for item in results)
    if keys != tuple(sorted(set(keys))):
        raise HKEXConformanceError(HKEXConformanceErrorCode.PAIR)
    return tuple(results)


def _pairs(
    value: JsonValue,
    cases: tuple[HKEXConformanceCase, ...],
) -> tuple[HKEXConformancePair, ...]:
    entries = _object_array(value)
    if len(entries) != HKEX_CONFORMANCE_PAIR_COUNT:
        raise HKEXConformanceError(HKEXConformanceErrorCode.PAIR)
    memberships: dict[str, dict[HKEXConformancePairRole, str]] = {}
    for case in cases:
        for membership in case.pair_memberships:
            roles = memberships.setdefault(membership.pair_id, {})
            if membership.role in roles:
                raise HKEXConformanceError(HKEXConformanceErrorCode.PAIR)
            roles[membership.role] = case.case_id
    results: list[HKEXConformancePair] = []
    for ordinal, entry in enumerate(entries, start=1):
        _exact_keys(entry, {"pair_id", "positive_case_id", "near_miss_case_id"})
        pair_id = _constant(entry["pair_id"], f"HKREG-PAIR-{ordinal:03d}")
        roles = memberships.get(pair_id)
        if roles is None or set(roles) != set(HKEXConformancePairRole):
            raise HKEXConformanceError(HKEXConformanceErrorCode.PAIR)
        positive = _constant(entry["positive_case_id"], roles[HKEXConformancePairRole.POSITIVE])
        near_miss = _constant(entry["near_miss_case_id"], roles[HKEXConformancePairRole.NEAR_MISS])
        results.append(HKEXConformancePair(pair_id, positive, near_miss))
    if set(memberships) != {item.pair_id for item in results}:
        raise HKEXConformanceError(HKEXConformanceErrorCode.PAIR)
    return tuple(results)


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise HKEXConformanceError(HKEXConformanceErrorCode.CONTRACT)
    return value


def _object_array(value: JsonValue) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise HKEXConformanceError(HKEXConformanceErrorCode.CONTRACT)
    return tuple(_object(item) for item in value)


def _exact_keys(value: dict[str, JsonValue], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKEXConformanceError(HKEXConformanceErrorCode.CONTRACT)


def _constant(value: JsonValue, expected: str) -> str:
    if value != expected or type(value) is not str:
        raise HKEXConformanceError(HKEXConformanceErrorCode.CONTRACT)
    return value


def _false(value: JsonValue) -> None:
    if value is not False:
        raise HKEXConformanceError(HKEXConformanceErrorCode.CONTRACT)


def _true(value: JsonValue) -> None:
    if value is not True:
        raise HKEXConformanceError(HKEXConformanceErrorCode.CONTRACT)


def _exact_integer(value: JsonValue, expected: int) -> None:
    if type(value) is not int or value != expected:
        raise HKEXConformanceError(HKEXConformanceErrorCode.ARITHMETIC)


def _text(value: JsonValue) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise HKEXConformanceError(HKEXConformanceErrorCode.CONTRACT)
    return value


def _fingerprint(value: JsonValue) -> str:
    text = _text(value)
    if fullmatch(r"sha256:[0-9a-f]{64}", text) is None:
        raise HKEXConformanceError(HKEXConformanceErrorCode.SOURCE)
    return text


def _pair_id(value: JsonValue) -> str:
    text = _text(value)
    match = fullmatch(r"HKREG-PAIR-(\d{3})", text)
    if match is None or not 1 <= int(match.group(1)) <= HKEX_CONFORMANCE_PAIR_COUNT:
        raise HKEXConformanceError(HKEXConformanceErrorCode.PAIR)
    return text


def _enum[E: StrEnum](value: JsonValue, enum_type: type[E]) -> E:
    text = _text(value)
    try:
        return enum_type(text)
    except ValueError as error:
        raise HKEXConformanceError(HKEXConformanceErrorCode.CONTRACT) from error
