"""Source-faithful English HKEX trees, rendering, partitioning, and coverage."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from re import fullmatch
from typing import Protocol, TypeIs
from unicodedata import is_normalized

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from .hk_regulatory_inventory import HKEX_SCOPE_IDS, HKEXBranchState

HKEX_ENGLISH_RECORD_RULE_ID = "HKREG-ENGLISH-RECORD-001"
HKEX_ENGLISH_RECORD_CONTRACT_VERSION = "1.0.0"
_FINGERPRINT_PATTERN = r"sha256:[0-9a-f]{64}"
_FORM_CONTROL_MARKERS = frozenset({"[BLANK FIELD]", "[CHECKBOX]", "[SELECTION]", "[SIGNATURE]"})
_MINIMUM_PARTS = 2


class HKEXEnglishErrorCode(StrEnum):
    """Closed malformed tree, rendering, and coverage failures."""

    CONTRACT = "HKREG_ENGLISH_CONTRACT_INVALID"
    COVERAGE = "HKREG_ENGLISH_COVERAGE_INVALID"
    FINGERPRINT = "HKREG_ENGLISH_FINGERPRINT_INVALID"
    STRUCTURE = "HKREG_ENGLISH_STRUCTURE_INVALID"


class HKEXEnglishError(ValueError):
    """One source-neutral English contract rejection."""

    code: HKEXEnglishErrorCode

    def __init__(self, code: HKEXEnglishErrorCode) -> None:
        """Create one stable fail-closed error."""
        self.code = code
        super().__init__(code.value)


class HKEXComponentClass(StrEnum):
    """Closed component classes with distinct normal-unit rules."""

    ORDINARY_RULE = "ORDINARY_RULE"
    DEFINITION_RULE = "DEFINITION_RULE"
    APPENDIX = "APPENDIX"
    PRACTICE_NOTE = "PRACTICE_NOTE"
    TABLE = "TABLE"
    FEES_RULE = "FEES_RULE"
    REGULATORY_FORM = "REGULATORY_FORM"


class HKEXEnglishUnitKind(StrEnum):
    """Closed source-supported English semantic and presentation units."""

    HEADING = "HEADING"
    LOCATOR = "LOCATOR"
    BODY_TEXT = "BODY_TEXT"
    LEAD_IN = "LEAD_IN"
    DEFINITION_TERM = "DEFINITION_TERM"
    DEFINITION_TEXT = "DEFINITION_TEXT"
    QUALIFICATION = "QUALIFICATION"
    EXCEPTION = "EXCEPTION"
    PROVISO = "PROVISO"
    TRANSITION_TEXT = "TRANSITION_TEXT"
    SCOPE_TEXT = "SCOPE_TEXT"
    INCORPORATED_NOTE = "INCORPORATED_NOTE"
    TABLE_CAPTION = "TABLE_CAPTION"
    TABLE_HEADER = "TABLE_HEADER"
    TABLE_ROW = "TABLE_ROW"
    TABLE_UNIT = "TABLE_UNIT"
    TABLE_NOTE = "TABLE_NOTE"
    FORM_INSTRUCTION = "FORM_INSTRUCTION"
    FORM_LABEL = "FORM_LABEL"
    FORM_CONTROL = "FORM_CONTROL"
    FORM_DECLARATION = "FORM_DECLARATION"
    FEE_CATEGORY = "FEE_CATEGORY"
    FEE_AMOUNT = "FEE_AMOUNT"
    FEE_BASIS = "FEE_BASIS"
    FEE_TIMING = "FEE_TIMING"
    CROSS_REFERENCE = "CROSS_REFERENCE"
    PRESENTATION = "PRESENTATION"


class HKEXSourceUnitRole(StrEnum):
    """One exact global coverage role for a source unit."""

    PRIMARY = "PRIMARY"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    PRESENTATION_ONLY = "PRESENTATION_ONLY"


class HKEXSourceContractState(StrEnum):
    """Whether an official record boundary is supported."""

    SUPPORTED = "SUPPORTED"
    UNKNOWN = "UNKNOWN"


class HKEXEnglishDisposition(StrEnum):
    """Effect-free branch construction result."""

    PASS = "PASS"
    WAITING_ROOM = "WAITING_ROOM"
    HISTORICAL = "HISTORICAL"
    QUARANTINE = "QUARANTINE"


class HKEXEnglishReason(StrEnum):
    """Stable construction and coverage reason codes."""

    PASS_UNSPLIT = "PASS_UNSPLIT"
    PASS_PARTITIONED = "PASS_PARTITIONED"
    FUTURE_BRANCH_ACCOUNTED = "FUTURE_BRANCH_ACCOUNTED"
    HISTORICAL_BRANCH_ACCOUNTED = "HISTORICAL_BRANCH_ACCOUNTED"
    UNKNOWN_BRANCH_QUARANTINED = "UNKNOWN_BRANCH_QUARANTINED"
    SOURCE_BOUNDARY_UNKNOWN = "SOURCE_BOUNDARY_UNKNOWN"
    SMALLEST_COMPLETE_UNIT_OVER_LIMIT = "SMALLEST_COMPLETE_UNIT_OVER_LIMIT"


class HKEXExactTokenCounter(Protocol):
    """One pinned exact tokenizer; estimates and aliases are forbidden."""

    profile_id: str
    profile_fingerprint: str
    tokenizer_id: str

    def count(self, text: str) -> int:
        """Count the exact final metadata text."""
        ...


@dataclass(frozen=True, slots=True)
class _RenderContext:
    """Internal exact inputs shared by rendering and partitioning."""

    tree: HKEXEnglishSourceTree
    profile: HKEXEnglishServingProfile
    counter: HKEXExactTokenCounter
    effective_context: str | None


@dataclass(frozen=True, slots=True)
class HKEXEnglishSourceUnit:
    """One source-supported unit with immutable primary/context classification."""

    source_unit_id: str
    parent_source_unit_id: str | None
    child_source_unit_ids: tuple[str, ...]
    source_order: int
    kind: HKEXEnglishUnitKind
    role: HKEXSourceUnitRole
    text: str
    source_range: str
    required_context_unit_ids: tuple[str, ...]
    meaning_bearing: bool
    content_fingerprint: str

    def __post_init__(self) -> None:
        """Validate canonical text, ordering, role, and fingerprint."""
        _text(self.source_unit_id)
        if self.parent_source_unit_id is not None:
            _text(self.parent_source_unit_id)
            if self.parent_source_unit_id == self.source_unit_id:
                raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
        _unique_strings(self.child_source_unit_ids, empty=True)
        if type(self.source_order) is not int or self.source_order < 0:
            raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
        _enum(self.kind, HKEXEnglishUnitKind)
        _enum(self.role, HKEXSourceUnitRole)
        _canonical_text(self.text)
        _text(self.source_range)
        _unique_strings(self.required_context_unit_ids, empty=True)
        if type(self.meaning_bearing) is not bool:
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
        if self.role is HKEXSourceUnitRole.PRIMARY and not self.meaning_bearing:
            raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
        if self.role is HKEXSourceUnitRole.PRESENTATION_ONLY and self.meaning_bearing:
            raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
        if self.kind is HKEXEnglishUnitKind.PRESENTATION and self.role is not (
            HKEXSourceUnitRole.PRESENTATION_ONLY
        ):
            raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
        if self.kind is HKEXEnglishUnitKind.FORM_CONTROL and self.text not in (
            _FORM_CONTROL_MARKERS
        ):
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
        if self.content_fingerprint != _raw_fingerprint(self.text.encode()):
            raise HKEXEnglishError(HKEXEnglishErrorCode.FINGERPRINT)


@dataclass(frozen=True, slots=True)
class HKEXReferencedLocation:
    """One locator and optional official heading, never copied target text."""

    locator: str
    official_heading: str | None

    def __post_init__(self) -> None:
        """Validate one exact source reference label."""
        _text(self.locator)
        if self.official_heading is not None:
            _canonical_text(self.official_heading)


@dataclass(frozen=True, slots=True)
class HKEXEnglishRecordUnit:
    """One normal unit or official recursive partition alternative."""

    record_unit_id: str
    primary_source_unit_ids: tuple[str, ...]
    dependency_source_unit_ids: tuple[str, ...]
    referenced_locations: tuple[HKEXReferencedLocation, ...]
    child_record_unit_ids: tuple[str, ...]
    source_contract_state: HKEXSourceContractState
    indivisible: bool

    def __post_init__(self) -> None:
        """Validate one declared complete record boundary."""
        _text(self.record_unit_id)
        _unique_strings(self.primary_source_unit_ids)
        _unique_strings(self.dependency_source_unit_ids, empty=True)
        if set(self.primary_source_unit_ids).intersection(self.dependency_source_unit_ids):
            raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
        if type(self.referenced_locations) is not tuple or len(self.referenced_locations) != len(
            set(self.referenced_locations)
        ):
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
        _unique_strings(self.child_record_unit_ids, empty=True)
        _enum(self.source_contract_state, HKEXSourceContractState)
        if type(self.indivisible) is not bool:
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
        if self.indivisible and self.child_record_unit_ids:
            raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)


@dataclass(frozen=True, slots=True)
class HKEXEnglishSourceTree:
    """One complete prevailing-English tree for one exact applicability branch."""

    tree_id: str
    component_id: str
    scope_id: str
    branch_id: str
    branch_state: HKEXBranchState
    component_class: HKEXComponentClass
    component_label: str
    location_label: str
    official_heading: str | None
    root_source_unit_id: str
    source_units: tuple[HKEXEnglishSourceUnit, ...]
    root_record_unit_ids: tuple[str, ...]
    record_units: tuple[HKEXEnglishRecordUnit, ...]
    source_rule_id: str
    source_artifact_fingerprints: tuple[str, ...]

    def __post_init__(self) -> None:
        """Prove graph, primary ownership, dependency closure, and class rules."""
        _validate_tree(self)

    @property
    def fingerprint(self) -> str:
        """Fingerprint all exact result-affecting source-tree facts."""
        return _canonical_fingerprint(_tree_document(self))


@dataclass(frozen=True, slots=True)
class HKEXEnglishServingProfile:
    """Exact injected tokenizer and six-field metadata limits."""

    profile_id: str
    profile_fingerprint: str
    tokenizer_id: str
    max_text_tokens: int
    max_metadata_bytes: int
    country: str
    jurisdiction: str
    material_type: str
    source: str
    authority_note: str

    def __post_init__(self) -> None:
        """Reject placeholder, invalid, or nonpositive profile facts."""
        for value in (
            self.profile_id,
            self.tokenizer_id,
            self.country,
            self.jurisdiction,
            self.material_type,
            self.source,
            self.authority_note,
        ):
            _text(value)
        _fingerprint(self.profile_fingerprint)
        if (
            type(self.max_text_tokens) is not int
            or self.max_text_tokens <= 0
            or type(self.max_metadata_bytes) is not int
            or self.max_metadata_bytes <= 0
        ):
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)


@dataclass(frozen=True, slots=True)
class HKEXEnglishMeasurement:
    """Two independent exact final-payload measurements."""

    text_tokens: int
    metadata_bytes: int
    text_limit: int
    metadata_limit: int

    def __post_init__(self) -> None:
        """Reject impossible measurements even on direct construction."""
        for value in (
            self.text_tokens,
            self.metadata_bytes,
            self.text_limit,
            self.metadata_limit,
        ):
            if type(value) is not int or value < 0:
                raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
        if self.text_limit == 0 or self.metadata_limit == 0:
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)

    @property
    def fits(self) -> bool:
        """Return whether both hard ceilings pass."""
        return self.text_tokens <= self.text_limit and self.metadata_bytes <= (self.metadata_limit)


@dataclass(frozen=True, slots=True)
class HKEXEnglishServingPart:
    """One complete effect-free rendered part without Search Record identity."""

    part_number: int
    total_parts: int
    record_unit_ids: tuple[str, ...]
    primary_source_unit_ids: tuple[str, ...]
    dependency_source_unit_ids: tuple[str, ...]
    text: str
    text_fingerprint: str
    serving_payload_fingerprint: str
    measurement: HKEXEnglishMeasurement


@dataclass(slots=True)
class _PartitionProblem:
    """One bounded minimum-part search with memoized exact renders."""

    context: _RenderContext
    frontier: tuple[HKEXEnglishRecordUnit, ...]
    total: int
    cache: dict[tuple[int, int], tuple[HKEXEnglishServingPart, ...] | None]


@dataclass(frozen=True, slots=True)
class HKEXEnglishRecordResult:
    """One independently processed normal record unit."""

    root_record_unit_id: str
    disposition: HKEXEnglishDisposition
    reason: HKEXEnglishReason
    parts: tuple[HKEXEnglishServingPart, ...]
    accounted_primary_source_unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKEXEnglishCoverageProof:
    """Complete branch source-unit accounting with no serving claim."""

    tree_fingerprint: str
    component_id: str
    scope_id: str
    branch_id: str
    branch_state: HKEXBranchState
    disposition: HKEXEnglishDisposition
    reason: HKEXEnglishReason
    record_results: tuple[HKEXEnglishRecordResult, ...]
    primary_source_unit_ids: tuple[str, ...]
    context_only_source_unit_ids: tuple[str, ...]
    presentation_only_source_unit_ids: tuple[str, ...]
    primary_accounting_complete: bool
    serving_candidate_ready: bool
    search_record_authorized: bool = False
    serving_ready: bool = False

    def document(self, *, case_id: str) -> dict[str, object]:
        """Return the exact conformance result without granting record authority."""
        _text(case_id)
        return {
            "case_id": case_id,
            "contract_version": HKEX_ENGLISH_RECORD_CONTRACT_VERSION,
            "rule_id": HKEX_ENGLISH_RECORD_RULE_ID,
            "tree_fingerprint": self.tree_fingerprint,
            "component_id": self.component_id,
            "scope_id": self.scope_id,
            "branch_id": self.branch_id,
            "branch_state": self.branch_state.value,
            "disposition": self.disposition.value,
            "reason": self.reason.value,
            "record_results": [
                {
                    "root_record_unit_id": result.root_record_unit_id,
                    "disposition": result.disposition.value,
                    "reason": result.reason.value,
                    "parts": [
                        {
                            "part_number": part.part_number,
                            "total_parts": part.total_parts,
                            "record_unit_ids": list(part.record_unit_ids),
                            "primary_source_unit_ids": list(part.primary_source_unit_ids),
                            "dependency_source_unit_ids": list(part.dependency_source_unit_ids),
                            "text": part.text,
                            "text_fingerprint": part.text_fingerprint,
                            "serving_payload_fingerprint": (part.serving_payload_fingerprint),
                            "measurement": {
                                "text_tokens": part.measurement.text_tokens,
                                "metadata_bytes": part.measurement.metadata_bytes,
                                "text_limit": part.measurement.text_limit,
                                "metadata_limit": part.measurement.metadata_limit,
                                "fits": part.measurement.fits,
                            },
                        }
                        for part in result.parts
                    ],
                    "accounted_primary_source_unit_ids": list(
                        result.accounted_primary_source_unit_ids
                    ),
                }
                for result in self.record_results
            ],
            "primary_source_unit_ids": list(self.primary_source_unit_ids),
            "context_only_source_unit_ids": list(self.context_only_source_unit_ids),
            "presentation_only_source_unit_ids": list(self.presentation_only_source_unit_ids),
            "primary_accounting_complete": self.primary_accounting_complete,
            "serving_candidate_ready": self.serving_candidate_ready,
            "search_record_authorized": self.search_record_authorized,
            "serving_ready": self.serving_ready,
        }


@dataclass(frozen=True, slots=True)
class HKEXEnglishConstructionRequest:
    """Strict JSON-compatible construction inputs except the injected tokenizer."""

    tree: HKEXEnglishSourceTree
    profile: HKEXEnglishServingProfile
    effective_context: str | None

    def __post_init__(self) -> None:
        """Bind effective context to the exact retained branch state."""
        if type(self.tree) is not HKEXEnglishSourceTree or type(self.profile) is not (
            HKEXEnglishServingProfile
        ):
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
        _validate_effective_context(self.tree.branch_state, self.effective_context)

    def document(self) -> dict[str, object]:
        """Return the canonical JSON-compatible construction request."""
        return {
            "tree": _tree_document(self.tree),
            "profile": {
                "profile_id": self.profile.profile_id,
                "profile_fingerprint": self.profile.profile_fingerprint,
                "tokenizer_id": self.profile.tokenizer_id,
                "max_text_tokens": self.profile.max_text_tokens,
                "max_metadata_bytes": self.profile.max_metadata_bytes,
                "country": self.profile.country,
                "jurisdiction": self.profile.jurisdiction,
                "material_type": self.profile.material_type,
                "source": self.profile.source,
                "authority_note": self.profile.authority_note,
            },
            "effective_context": self.effective_context,
        }


def hkex_english_request_from_document(
    document: object,
) -> HKEXEnglishConstructionRequest:
    """Strictly decode one source-neutral ADR 0073 construction request."""
    value = _json_object(document)
    _exact_keys(value, {"tree", "profile", "effective_context"})
    return HKEXEnglishConstructionRequest(
        tree=_tree_from_document(_json_object(value["tree"])),
        profile=_profile_from_document(_json_object(value["profile"])),
        effective_context=_json_nullable_text(value["effective_context"]),
    )


def construct_hkex_english_request(
    request: HKEXEnglishConstructionRequest,
    token_counter: HKEXExactTokenCounter,
) -> HKEXEnglishCoverageProof:
    """Execute one strictly decoded request with one exact injected tokenizer."""
    if type(request) is not HKEXEnglishConstructionRequest:
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    return construct_hkex_english_branch(
        request.tree,
        request.profile,
        token_counter,
        effective_context=request.effective_context,
    )


def construct_hkex_english_branch(
    tree: HKEXEnglishSourceTree,
    profile: HKEXEnglishServingProfile,
    token_counter: HKEXExactTokenCounter,
    *,
    effective_context: str | None,
) -> HKEXEnglishCoverageProof:
    """Render, partition, and account one exact branch without issuing records."""
    if type(tree) is not HKEXEnglishSourceTree or type(profile) is not (HKEXEnglishServingProfile):
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    _validate_counter(profile, token_counter)
    _validate_effective_context(tree.branch_state, effective_context)
    primary = tuple(
        item.source_unit_id for item in tree.source_units if item.role is HKEXSourceUnitRole.PRIMARY
    )
    context = tuple(
        item.source_unit_id
        for item in tree.source_units
        if item.role is HKEXSourceUnitRole.CONTEXT_ONLY
    )
    presentation = tuple(
        item.source_unit_id
        for item in tree.source_units
        if item.role is HKEXSourceUnitRole.PRESENTATION_ONLY
    )
    noncurrent = _noncurrent_result(tree.branch_state)
    if noncurrent is not None:
        disposition, reason = noncurrent
        return HKEXEnglishCoverageProof(
            tree_fingerprint=tree.fingerprint,
            component_id=tree.component_id,
            scope_id=tree.scope_id,
            branch_id=tree.branch_id,
            branch_state=tree.branch_state,
            disposition=disposition,
            reason=reason,
            record_results=(),
            primary_source_unit_ids=primary,
            context_only_source_unit_ids=context,
            presentation_only_source_unit_ids=presentation,
            primary_accounting_complete=True,
            serving_candidate_ready=False,
        )
    render_context = _RenderContext(tree, profile, token_counter, effective_context)
    results = tuple(
        _partition_root(render_context, root_id) for root_id in tree.root_record_unit_ids
    )
    accounted = tuple(
        source_unit_id
        for result in results
        for source_unit_id in result.accounted_primary_source_unit_ids
    )
    if accounted != primary:
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
    passed = all(result.disposition is HKEXEnglishDisposition.PASS for result in results)
    disposition = HKEXEnglishDisposition.PASS if passed else HKEXEnglishDisposition.QUARANTINE
    reason = (
        HKEXEnglishReason.PASS_PARTITIONED
        if passed and any(len(result.parts) > 1 for result in results)
        else HKEXEnglishReason.PASS_UNSPLIT
        if passed
        else next(
            result.reason
            for result in results
            if result.disposition is HKEXEnglishDisposition.QUARANTINE
        )
    )
    return HKEXEnglishCoverageProof(
        tree_fingerprint=tree.fingerprint,
        component_id=tree.component_id,
        scope_id=tree.scope_id,
        branch_id=tree.branch_id,
        branch_state=tree.branch_state,
        disposition=disposition,
        reason=reason,
        record_results=results,
        primary_source_unit_ids=primary,
        context_only_source_unit_ids=context,
        presentation_only_source_unit_ids=presentation,
        primary_accounting_complete=True,
        serving_candidate_ready=passed,
    )


def _partition_root(
    context: _RenderContext,
    root_id: str,
) -> HKEXEnglishRecordResult:
    units = _record_index(context.tree)
    root = units[root_id]
    if root.source_contract_state is HKEXSourceContractState.UNKNOWN:
        return HKEXEnglishRecordResult(
            root_id,
            HKEXEnglishDisposition.QUARANTINE,
            HKEXEnglishReason.SOURCE_BOUNDARY_UNKNOWN,
            (),
            root.primary_source_unit_ids,
        )
    unsplit = _render_part(context, (root,), part_number=1, total_parts=1)
    if unsplit.measurement.fits:
        return HKEXEnglishRecordResult(
            root_id,
            HKEXEnglishDisposition.PASS,
            HKEXEnglishReason.PASS_UNSPLIT,
            (unsplit,),
            root.primary_source_unit_ids,
        )
    frontier, failure = _largest_safe_frontier(context, root, units)
    while frontier is not None:
        parts = _canonical_partition(context, frontier)
        if parts is not None:
            return HKEXEnglishRecordResult(
                root_id,
                HKEXEnglishDisposition.PASS,
                HKEXEnglishReason.PASS_PARTITIONED,
                parts,
                root.primary_source_unit_ids,
            )
        refined, failure = _refine_frontier(context, frontier, units)
        if refined == frontier:
            break
        frontier = refined
    return HKEXEnglishRecordResult(
        root_id,
        HKEXEnglishDisposition.QUARANTINE,
        failure or HKEXEnglishReason.SMALLEST_COMPLETE_UNIT_OVER_LIMIT,
        (),
        root.primary_source_unit_ids,
    )


def _largest_safe_frontier(
    context: _RenderContext,
    unit: HKEXEnglishRecordUnit,
    units: dict[str, HKEXEnglishRecordUnit],
) -> tuple[tuple[HKEXEnglishRecordUnit, ...] | None, HKEXEnglishReason | None]:
    if unit.source_contract_state is HKEXSourceContractState.UNKNOWN:
        return None, HKEXEnglishReason.SOURCE_BOUNDARY_UNKNOWN
    candidate = _render_part(context, (unit,), part_number=1, total_parts=1)
    if candidate.measurement.fits:
        return (unit,), None
    if unit.indivisible or not unit.child_record_unit_ids:
        return None, HKEXEnglishReason.SMALLEST_COMPLETE_UNIT_OVER_LIMIT
    result: list[HKEXEnglishRecordUnit] = []
    for child_id in unit.child_record_unit_ids:
        child_result, failure = _largest_safe_frontier(context, units[child_id], units)
        if child_result is None:
            return None, failure
        result.extend(child_result)
    return tuple(result), None


def _refine_frontier(
    context: _RenderContext,
    frontier: tuple[HKEXEnglishRecordUnit, ...],
    units: dict[str, HKEXEnglishRecordUnit],
) -> tuple[tuple[HKEXEnglishRecordUnit, ...] | None, HKEXEnglishReason | None]:
    result: list[HKEXEnglishRecordUnit] = []
    changed = False
    total = len(frontier)
    for index, unit in enumerate(frontier, start=1):
        standalone = _render_part(
            context,
            (unit,),
            part_number=index,
            total_parts=total,
        )
        if standalone.measurement.fits:
            result.append(unit)
            continue
        if unit.source_contract_state is HKEXSourceContractState.UNKNOWN:
            return None, HKEXEnglishReason.SOURCE_BOUNDARY_UNKNOWN
        if unit.indivisible or not unit.child_record_unit_ids:
            return None, HKEXEnglishReason.SMALLEST_COMPLETE_UNIT_OVER_LIMIT
        result.extend(units[item] for item in unit.child_record_unit_ids)
        changed = True
    return (tuple(result) if changed else frontier), None


def _canonical_partition(
    context: _RenderContext,
    frontier: tuple[HKEXEnglishRecordUnit, ...],
) -> tuple[HKEXEnglishServingPart, ...] | None:
    for total in range(_MINIMUM_PARTS, len(frontier) + 1):
        problem = _PartitionProblem(context, frontier, total, {})
        result = _solve_partition(problem, 0, 1)
        if result is not None:
            return result
    return None


def _solve_partition(
    problem: _PartitionProblem,
    start: int,
    part_number: int,
) -> tuple[HKEXEnglishServingPart, ...] | None:
    key = (start, part_number)
    if key in problem.cache:
        return problem.cache[key]
    remaining = problem.total - part_number
    maximum_end = (
        len(problem.frontier) if part_number == problem.total else len(problem.frontier) - remaining
    )
    for end in range(maximum_end, start, -1):
        part = _render_part(
            problem.context,
            problem.frontier[start:end],
            part_number=part_number,
            total_parts=problem.total,
        )
        if not part.measurement.fits:
            continue
        if part_number == problem.total:
            if end == len(problem.frontier):
                problem.cache[key] = (part,)
                return problem.cache[key]
            continue
        tail = _solve_partition(problem, end, part_number + 1)
        if tail is not None:
            problem.cache[key] = (part, *tail)
            return problem.cache[key]
    problem.cache[key] = None
    return None


def _render_part(
    context: _RenderContext,
    record_units: tuple[HKEXEnglishRecordUnit, ...],
    *,
    part_number: int,
    total_parts: int,
) -> HKEXEnglishServingPart:
    tree = context.tree
    profile = context.profile
    source_units = {item.source_unit_id: item for item in tree.source_units}
    primary_ids = _ordered_unique(
        source_units,
        tuple(item for unit in record_units for item in unit.primary_source_unit_ids),
    )
    dependency_ids = _ordered_unique(
        source_units,
        tuple(item for unit in record_units for item in unit.dependency_source_unit_ids),
    )
    references = tuple(
        reference for unit in record_units for reference in unit.referenced_locations
    )
    if len(references) != len(set(references)):
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    market = "Main Board" if tree.scope_id.endswith("MAIN-BOARD") else "GEM"
    context_lines = [
        "Context:",
        "Material: HKEX Listing Rule — non-statutory exchange regulatory rule",
        f"Market: {market}",
        f"Component: {tree.component_label}",
        f"Location: {tree.location_label}",
    ]
    if tree.official_heading is not None:
        context_lines.append(f"Official heading: {tree.official_heading}")
    if context.effective_context is not None:
        context_lines.append(f"Effective context: {context.effective_context}")
    if total_parts > 1:
        context_lines.append(f"Serving part: {part_number} of {total_parts}")
    blocks = ["\n".join(context_lines)]
    if dependency_ids:
        blocks.append(
            "Required governing context:\n"
            + "\n".join(source_units[item].text for item in dependency_ids)
        )
    if references:
        lines = [
            f"- {item.locator}" + (f" — {item.official_heading}" if item.official_heading else "")
            for item in references
        ]
        blocks.append("Referenced locations:\n" + "\n".join(lines))
    blocks.append(
        "English rule text — prevailing language:\n"
        + "\n".join(source_units[item].text for item in primary_ids)
    )
    text = "\n\n".join(blocks)
    _canonical_text(text)
    payload = checked_json_value(
        {
            "authority_note": profile.authority_note,
            "country": profile.country,
            "jurisdiction": profile.jurisdiction,
            "source": profile.source,
            "text": text,
            "type": profile.material_type,
        }
    )
    measurement = HKEXEnglishMeasurement(
        context.counter.count(text),
        len(canonicalize(payload)),
        profile.max_text_tokens,
        profile.max_metadata_bytes,
    )
    return HKEXEnglishServingPart(
        part_number,
        total_parts,
        tuple(item.record_unit_id for item in record_units),
        primary_ids,
        dependency_ids,
        text,
        _raw_fingerprint(text.encode()),
        _canonical_fingerprint(payload),
        measurement,
    )


def _validate_tree(tree: HKEXEnglishSourceTree) -> None:
    for value in (
        tree.tree_id,
        tree.component_id,
        tree.branch_id,
        tree.component_label,
        tree.location_label,
        tree.root_source_unit_id,
        tree.source_rule_id,
    ):
        _text(value)
    if tree.scope_id not in HKEX_SCOPE_IDS:
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    _enum(tree.branch_state, HKEXBranchState)
    _enum(tree.component_class, HKEXComponentClass)
    if tree.official_heading is not None:
        _canonical_text(tree.official_heading)
    sources = _unique_objects(tree.source_units, "source_unit_id")
    records = _unique_objects(tree.record_units, "record_unit_id")
    if tree.root_source_unit_id not in sources:
        raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
    _unique_strings(tree.root_record_unit_ids)
    if not set(tree.root_record_unit_ids).issubset(records):
        raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
    _fingerprints(tree.source_artifact_fingerprints)
    _validate_source_graph(tree, sources)
    _validate_record_graph(tree, sources, records)


def _validate_source_graph(
    tree: HKEXEnglishSourceTree,
    sources: dict[str, HKEXEnglishSourceUnit],
) -> None:
    orders = tuple(item.source_order for item in tree.source_units)
    if orders != tuple(range(len(tree.source_units))):
        raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
    for item in tree.source_units:
        _validate_source_links(tree.root_source_unit_id, item, sources)
        _validate_source_dependencies(item, sources)
        _prove_source_acyclic(item, sources)


def _validate_source_links(
    root_source_unit_id: str,
    item: HKEXEnglishSourceUnit,
    sources: dict[str, HKEXEnglishSourceUnit],
) -> None:
    if not set(item.child_source_unit_ids).issubset(sources):
        raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
    if item.parent_source_unit_id is None:
        if item.source_unit_id != root_source_unit_id:
            raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
    else:
        parent = sources.get(item.parent_source_unit_id)
        if parent is None or item.source_unit_id not in parent.child_source_unit_ids:
            raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
    if any(
        sources[child_id].parent_source_unit_id != item.source_unit_id
        for child_id in item.child_source_unit_ids
    ):
        raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)


def _validate_source_dependencies(
    item: HKEXEnglishSourceUnit,
    sources: dict[str, HKEXEnglishSourceUnit],
) -> None:
    if not set(item.required_context_unit_ids).issubset(sources):
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
    if item.source_unit_id in item.required_context_unit_ids or any(
        sources[dependency].role is HKEXSourceUnitRole.PRESENTATION_ONLY
        for dependency in item.required_context_unit_ids
    ):
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
    _prove_context_acyclic(item.source_unit_id, sources, set(), set())


def _validate_record_graph(
    tree: HKEXEnglishSourceTree,
    sources: dict[str, HKEXEnglishSourceUnit],
    records: dict[str, HKEXEnglishRecordUnit],
) -> None:
    root_primary: list[str] = []
    child_sequence = tuple(
        child_id for item in tree.record_units for child_id in item.child_record_unit_ids
    )
    child_ids = set(child_sequence)
    if len(child_sequence) != len(child_ids):
        raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
    if set(tree.root_record_unit_ids).intersection(child_ids):
        raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
    if set(records) != set(tree.root_record_unit_ids).union(child_ids):
        raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
    for item in tree.record_units:
        _validate_record_ownership(item, sources, records)
        _validate_component_class(tree.component_class, item, sources)
        _prove_record_acyclic(item, records)
        if item.child_record_unit_ids:
            child_primary = tuple(
                source_id
                for child_id in item.child_record_unit_ids
                for source_id in records[child_id].primary_source_unit_ids
            )
            if child_primary != item.primary_source_unit_ids:
                raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
    for root_id in tree.root_record_unit_ids:
        root_primary.extend(records[root_id].primary_source_unit_ids)
    expected = tuple(
        item.source_unit_id for item in tree.source_units if item.role is HKEXSourceUnitRole.PRIMARY
    )
    if tuple(root_primary) != expected:
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)


def _validate_record_ownership(
    item: HKEXEnglishRecordUnit,
    sources: dict[str, HKEXEnglishSourceUnit],
    records: dict[str, HKEXEnglishRecordUnit],
) -> None:
    if not set(item.primary_source_unit_ids).issubset(sources) or not set(
        item.dependency_source_unit_ids
    ).issubset(sources):
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
    if not set(item.child_record_unit_ids).issubset(records):
        raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
    expected_primary = _ordered_unique(sources, item.primary_source_unit_ids)
    expected_dependencies = _context_closure(item.primary_source_unit_ids, sources)
    if item.primary_source_unit_ids != expected_primary or (
        item.dependency_source_unit_ids != expected_dependencies
    ):
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
    if any(
        sources[source_id].role is not HKEXSourceUnitRole.PRIMARY
        for source_id in item.primary_source_unit_ids
    ):
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)


def _context_closure(
    primary_source_unit_ids: tuple[str, ...],
    sources: dict[str, HKEXEnglishSourceUnit],
) -> tuple[str, ...]:
    required: set[str] = set()
    primary = set(primary_source_unit_ids)
    pending = list(primary_source_unit_ids)
    while pending:
        source_id = pending.pop()
        for dependency in sources[source_id].required_context_unit_ids:
            if dependency not in primary and dependency not in required:
                required.add(dependency)
                pending.append(dependency)
    return _ordered_unique(sources, tuple(required))


def _prove_context_acyclic(
    source_id: str,
    sources: dict[str, HKEXEnglishSourceUnit],
    active: set[str],
    complete: set[str],
) -> None:
    if source_id in active:
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
    if source_id in complete:
        return
    active.add(source_id)
    for dependency in sources[source_id].required_context_unit_ids:
        _prove_context_acyclic(dependency, sources, active, complete)
    active.remove(source_id)
    complete.add(source_id)


def _validate_component_class(
    component_class: HKEXComponentClass,
    record: HKEXEnglishRecordUnit,
    sources: dict[str, HKEXEnglishSourceUnit],
) -> None:
    kinds = {
        sources[item].kind
        for item in (*record.primary_source_unit_ids, *record.dependency_source_unit_ids)
    }
    required_all = {
        HKEXComponentClass.DEFINITION_RULE: {
            HKEXEnglishUnitKind.DEFINITION_TERM,
            HKEXEnglishUnitKind.DEFINITION_TEXT,
        },
        HKEXComponentClass.TABLE: {
            HKEXEnglishUnitKind.TABLE_HEADER,
            HKEXEnglishUnitKind.TABLE_ROW,
        },
        HKEXComponentClass.FEES_RULE: {
            HKEXEnglishUnitKind.FEE_CATEGORY,
            HKEXEnglishUnitKind.FEE_AMOUNT,
            HKEXEnglishUnitKind.FEE_BASIS,
            HKEXEnglishUnitKind.FEE_TIMING,
        },
    }
    required = required_all.get(component_class)
    if required is not None and not required.issubset(kinds):
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
    if component_class is HKEXComponentClass.REGULATORY_FORM and not kinds.intersection(
        {
            HKEXEnglishUnitKind.FORM_INSTRUCTION,
            HKEXEnglishUnitKind.FORM_DECLARATION,
            HKEXEnglishUnitKind.FORM_CONTROL,
        }
    ):
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)
    if component_class in {
        HKEXComponentClass.ORDINARY_RULE,
        HKEXComponentClass.APPENDIX,
        HKEXComponentClass.PRACTICE_NOTE,
    } and not kinds.intersection(
        {
            HKEXEnglishUnitKind.BODY_TEXT,
            HKEXEnglishUnitKind.QUALIFICATION,
            HKEXEnglishUnitKind.EXCEPTION,
            HKEXEnglishUnitKind.PROVISO,
        }
    ):
        raise HKEXEnglishError(HKEXEnglishErrorCode.COVERAGE)


def _validate_counter(
    profile: HKEXEnglishServingProfile,
    counter: HKEXExactTokenCounter,
) -> None:
    for field in ("profile_id", "profile_fingerprint", "tokenizer_id"):
        if not hasattr(counter, field):
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    if (
        counter.profile_id != profile.profile_id
        or counter.profile_fingerprint != profile.profile_fingerprint
        or counter.tokenizer_id != profile.tokenizer_id
    ):
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)


def _validate_effective_context(state: HKEXBranchState, value: str | None) -> None:
    if state is HKEXBranchState.TRANSITIONAL_CURRENT:
        if value is None:
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
        _canonical_text(value)
    elif value is not None:
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)


def _noncurrent_result(
    state: HKEXBranchState,
) -> tuple[HKEXEnglishDisposition, HKEXEnglishReason] | None:
    if state in {HKEXBranchState.FUTURE_FIXED_DATE, HKEXBranchState.FUTURE_CONDITIONAL}:
        return (
            HKEXEnglishDisposition.WAITING_ROOM,
            HKEXEnglishReason.FUTURE_BRANCH_ACCOUNTED,
        )
    if state in {HKEXBranchState.SUPERSEDED, HKEXBranchState.WITHDRAWN}:
        return (
            HKEXEnglishDisposition.HISTORICAL,
            HKEXEnglishReason.HISTORICAL_BRANCH_ACCOUNTED,
        )
    if state is HKEXBranchState.UNKNOWN:
        return (
            HKEXEnglishDisposition.QUARANTINE,
            HKEXEnglishReason.UNKNOWN_BRANCH_QUARANTINED,
        )
    return None


def _tree_from_document(value: dict[str, object]) -> HKEXEnglishSourceTree:
    _exact_keys(
        value,
        {
            "tree_id",
            "component_id",
            "scope_id",
            "branch_id",
            "branch_state",
            "component_class",
            "component_label",
            "location_label",
            "official_heading",
            "root_source_unit_id",
            "source_units",
            "root_record_unit_ids",
            "record_units",
            "source_rule_id",
            "source_artifact_fingerprints",
        },
    )
    return HKEXEnglishSourceTree(
        tree_id=_json_text(value["tree_id"]),
        component_id=_json_text(value["component_id"]),
        scope_id=_json_text(value["scope_id"]),
        branch_id=_json_text(value["branch_id"]),
        branch_state=_json_enum(value["branch_state"], HKEXBranchState),
        component_class=_json_enum(value["component_class"], HKEXComponentClass),
        component_label=_json_text(value["component_label"]),
        location_label=_json_text(value["location_label"]),
        official_heading=_json_nullable_text(value["official_heading"]),
        root_source_unit_id=_json_text(value["root_source_unit_id"]),
        source_units=tuple(
            _source_unit_from_document(item) for item in _json_object_array(value["source_units"])
        ),
        root_record_unit_ids=_json_strings(value["root_record_unit_ids"]),
        record_units=tuple(
            _record_unit_from_document(item) for item in _json_object_array(value["record_units"])
        ),
        source_rule_id=_json_text(value["source_rule_id"]),
        source_artifact_fingerprints=_json_strings(value["source_artifact_fingerprints"]),
    )


def _tree_document(tree: HKEXEnglishSourceTree) -> dict[str, object]:
    return {
        "tree_id": tree.tree_id,
        "component_id": tree.component_id,
        "scope_id": tree.scope_id,
        "branch_id": tree.branch_id,
        "branch_state": tree.branch_state.value,
        "component_class": tree.component_class.value,
        "component_label": tree.component_label,
        "location_label": tree.location_label,
        "official_heading": tree.official_heading,
        "root_source_unit_id": tree.root_source_unit_id,
        "source_units": [
            {
                "source_unit_id": item.source_unit_id,
                "parent_source_unit_id": item.parent_source_unit_id,
                "child_source_unit_ids": list(item.child_source_unit_ids),
                "source_order": item.source_order,
                "kind": item.kind.value,
                "role": item.role.value,
                "text": item.text,
                "source_range": item.source_range,
                "required_context_unit_ids": list(item.required_context_unit_ids),
                "meaning_bearing": item.meaning_bearing,
                "content_fingerprint": item.content_fingerprint,
            }
            for item in tree.source_units
        ],
        "root_record_unit_ids": list(tree.root_record_unit_ids),
        "record_units": [
            {
                "record_unit_id": item.record_unit_id,
                "primary_source_unit_ids": list(item.primary_source_unit_ids),
                "dependency_source_unit_ids": list(item.dependency_source_unit_ids),
                "referenced_locations": [
                    {
                        "locator": reference.locator,
                        "official_heading": reference.official_heading,
                    }
                    for reference in item.referenced_locations
                ],
                "child_record_unit_ids": list(item.child_record_unit_ids),
                "source_contract_state": item.source_contract_state.value,
                "indivisible": item.indivisible,
            }
            for item in tree.record_units
        ],
        "source_rule_id": tree.source_rule_id,
        "source_artifact_fingerprints": list(tree.source_artifact_fingerprints),
    }


def _source_unit_from_document(value: dict[str, object]) -> HKEXEnglishSourceUnit:
    _exact_keys(
        value,
        {
            "source_unit_id",
            "parent_source_unit_id",
            "child_source_unit_ids",
            "source_order",
            "kind",
            "role",
            "text",
            "source_range",
            "required_context_unit_ids",
            "meaning_bearing",
            "content_fingerprint",
        },
    )
    return HKEXEnglishSourceUnit(
        source_unit_id=_json_text(value["source_unit_id"]),
        parent_source_unit_id=_json_nullable_text(value["parent_source_unit_id"]),
        child_source_unit_ids=_json_strings(value["child_source_unit_ids"], empty=True),
        source_order=_json_integer(value["source_order"]),
        kind=_json_enum(value["kind"], HKEXEnglishUnitKind),
        role=_json_enum(value["role"], HKEXSourceUnitRole),
        text=_json_text(value["text"]),
        source_range=_json_text(value["source_range"]),
        required_context_unit_ids=_json_strings(value["required_context_unit_ids"], empty=True),
        meaning_bearing=_json_boolean(value["meaning_bearing"]),
        content_fingerprint=_json_text(value["content_fingerprint"]),
    )


def _record_unit_from_document(value: dict[str, object]) -> HKEXEnglishRecordUnit:
    _exact_keys(
        value,
        {
            "record_unit_id",
            "primary_source_unit_ids",
            "dependency_source_unit_ids",
            "referenced_locations",
            "child_record_unit_ids",
            "source_contract_state",
            "indivisible",
        },
    )
    return HKEXEnglishRecordUnit(
        record_unit_id=_json_text(value["record_unit_id"]),
        primary_source_unit_ids=_json_strings(value["primary_source_unit_ids"]),
        dependency_source_unit_ids=_json_strings(value["dependency_source_unit_ids"], empty=True),
        referenced_locations=tuple(
            _reference_from_document(item)
            for item in _json_object_array(value["referenced_locations"])
        ),
        child_record_unit_ids=_json_strings(value["child_record_unit_ids"], empty=True),
        source_contract_state=_json_enum(value["source_contract_state"], HKEXSourceContractState),
        indivisible=_json_boolean(value["indivisible"]),
    )


def _reference_from_document(value: dict[str, object]) -> HKEXReferencedLocation:
    _exact_keys(value, {"locator", "official_heading"})
    return HKEXReferencedLocation(
        locator=_json_text(value["locator"]),
        official_heading=_json_nullable_text(value["official_heading"]),
    )


def _profile_from_document(value: dict[str, object]) -> HKEXEnglishServingProfile:
    _exact_keys(
        value,
        {
            "profile_id",
            "profile_fingerprint",
            "tokenizer_id",
            "max_text_tokens",
            "max_metadata_bytes",
            "country",
            "jurisdiction",
            "material_type",
            "source",
            "authority_note",
        },
    )
    return HKEXEnglishServingProfile(
        profile_id=_json_text(value["profile_id"]),
        profile_fingerprint=_json_text(value["profile_fingerprint"]),
        tokenizer_id=_json_text(value["tokenizer_id"]),
        max_text_tokens=_json_integer(value["max_text_tokens"]),
        max_metadata_bytes=_json_integer(value["max_metadata_bytes"]),
        country=_json_text(value["country"]),
        jurisdiction=_json_text(value["jurisdiction"]),
        material_type=_json_text(value["material_type"]),
        source=_json_text(value["source"]),
        authority_note=_json_text(value["authority_note"]),
    )


def _record_index(tree: HKEXEnglishSourceTree) -> dict[str, HKEXEnglishRecordUnit]:
    return {item.record_unit_id: item for item in tree.record_units}


def _ordered_unique(
    source_units: dict[str, HKEXEnglishSourceUnit], values: tuple[str, ...]
) -> tuple[str, ...]:
    unique = set(values)
    return tuple(
        item.source_unit_id
        for item in sorted(source_units.values(), key=lambda value: value.source_order)
        if item.source_unit_id in unique
    )


def _unique_objects[T: object](values: tuple[T, ...], field: str) -> dict[str, T]:
    if type(values) is not tuple or not values:
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    result: dict[str, T] = {}
    for value in values:
        identity = getattr(value, field, None)
        if type(identity) is not str or identity in result:
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
        result[identity] = value
    return result


def _prove_source_acyclic(
    unit: HKEXEnglishSourceUnit, sources: dict[str, HKEXEnglishSourceUnit]
) -> None:
    seen = {unit.source_unit_id}
    parent_id = unit.parent_source_unit_id
    while parent_id is not None:
        if parent_id in seen or parent_id not in sources:
            raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
        seen.add(parent_id)
        parent_id = sources[parent_id].parent_source_unit_id


def _prove_record_acyclic(
    unit: HKEXEnglishRecordUnit, records: dict[str, HKEXEnglishRecordUnit]
) -> None:
    stack = list(unit.child_record_unit_ids)
    seen = {unit.record_unit_id}
    while stack:
        child_id = stack.pop()
        if child_id in seen:
            raise HKEXEnglishError(HKEXEnglishErrorCode.STRUCTURE)
        seen.add(child_id)
        stack.extend(records[child_id].child_record_unit_ids)


def _canonical_text(value: str) -> str:
    _text(value)
    if (
        not is_normalized("NFC", value)
        or "\r" in value
        or value.startswith("\n")
        or value.endswith("\n")
        or any(line.endswith((" ", "\t")) for line in value.split("\n"))
    ):
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    return value


def _raw_fingerprint(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


def _canonical_fingerprint(value: object) -> str:
    return _raw_fingerprint(canonicalize(checked_json_value(value)))


def _fingerprint(value: str) -> str:
    if fullmatch(_FINGERPRINT_PATTERN, value) is None:
        raise HKEXEnglishError(HKEXEnglishErrorCode.FINGERPRINT)
    return value


def _fingerprints(values: tuple[str, ...]) -> tuple[str, ...]:
    _unique_strings(values)
    for value in values:
        _fingerprint(value)
    return values


def _enum[E: StrEnum](value: object, expected: type[E]) -> E:
    if type(value) is not expected:
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    return value


def _text(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    return value


def _unique_strings(values: tuple[str, ...], *, empty: bool = False) -> tuple[str, ...]:
    if type(values) is not tuple or (not empty and not values) or len(values) != len(set(values)):
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    for value in values:
        _text(value)
    return values


def _json_object(value: object) -> dict[str, object]:
    if not _is_object_dict(value):
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
        result[key] = item
    return result


def _json_object_array(value: object) -> tuple[dict[str, object], ...]:
    if not _is_object_list(value):
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    return tuple(_json_object(item) for item in value)


def _is_object_dict(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeIs[list[object]]:
    return isinstance(value, list)


def _exact_keys(value: dict[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)


def _json_text(value: object) -> str:
    return _text(value)


def _json_nullable_text(value: object) -> str | None:
    if value is None:
        return None
    return _json_text(value)


def _json_strings(value: object, *, empty: bool = False) -> tuple[str, ...]:
    if not _is_object_list(value):
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    return _unique_strings(tuple(_json_text(item) for item in value), empty=empty)


def _json_integer(value: object) -> int:
    if type(value) is not int:
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    return value


def _json_boolean(value: object) -> bool:
    if type(value) is not bool:
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT)
    return value


def _json_enum[E: StrEnum](value: object, expected: type[E]) -> E:
    raw = _json_text(value)
    try:
        return expected(raw)
    except ValueError as error:
        raise HKEXEnglishError(HKEXEnglishErrorCode.CONTRACT) from error
