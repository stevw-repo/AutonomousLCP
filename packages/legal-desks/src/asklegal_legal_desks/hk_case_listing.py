"""Deterministic Hong Kong official-judgment listing accounting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from .model import SourceDefinition

_MIN_CASE_YEAR = 1800
_MAX_YEAR = 9999
_HANDOVER_YEAR = 1997

HK_CASE_LRS_INVENTORY_SOURCE_ID = "HK-CASE-JUDICIARY-LRS-INVENTORY"
HK_CASE_JUDICIARY_JUDGMENT_SOURCE_ID = "HK-CASE-JUDICIARY-JUDGMENT"
HK_CASE_COURT_REGISTRY_SOURCE_ID = "HK-CASE-COURT-REGISTRY"
HK_CASE_JUDICIARY_LIBRARY_SOURCE_ID = "HK-CASE-JUDICIARY-LIBRARY"
HK_CASE_PRIVY_COUNCIL_SOURCE_ID = "HK-CASE-PRIVY-COUNCIL"
HK_CASE_JUDICIARY_TRANSLATION_SOURCE_ID = "HK-CASE-JUDICIARY-TRANSLATION"
HK_CASE_HKLII_DISCOVERY_SOURCE_ID = "HK-CASE-HKLII-DISCOVERY"

OFFICIAL_INVENTORY_SOURCE_IDS = frozenset(
    {
        HK_CASE_JUDICIARY_LIBRARY_SOURCE_ID,
        HK_CASE_LRS_INVENTORY_SOURCE_ID,
        HK_CASE_PRIVY_COUNCIL_SOURCE_ID,
    }
)

HK_CASE_SOURCE_UNIVERSE = (
    SourceDefinition(
        source_id=HK_CASE_COURT_REGISTRY_SOURCE_ID,
        role="CORROBORATING",
        endpoint_families=("ITEM_SPECIFIC_COURT_REGISTRY_REQUEST",),
        checking_tier="ITEM_SPECIFIC",
        permitted_use="KNOWN_ITEM_AUTHENTICITY_VERSION_OR_AVAILABILITY_FALLBACK",
        completeness_rule="CANNOT_PROVE_COMPLETE_ONLINE_INVENTORY",
        outage_consequence="AFFECTED_ITEM_BLOCKING",
    ),
    SourceDefinition(
        source_id=HK_CASE_HKLII_DISCOVERY_SOURCE_ID,
        role="DISCOVERY",
        endpoint_families=("HKLII_CASE_DISCOVERY",),
        checking_tier="NONBLOCKING_DISCOVERY",
        permitted_use="DISCOVERY_ALIAS_CITATION_AND_TREATMENT_LEADS_ONLY",
        completeness_rule="NEVER_PROVES_OFFICIAL_COMPLETENESS_OR_NO_CHANGE",
        outage_consequence="NONBLOCKING",
    ),
    SourceDefinition(
        source_id=HK_CASE_JUDICIARY_JUDGMENT_SOURCE_ID,
        role="CONTROLLING",
        endpoint_families=("JUDICIARY_ORIGINAL_JUDGMENT_ARTIFACT",),
        checking_tier="ITEM_ACQUISITION",
        permitted_use="ORIGINAL_WORDING_VERSION_LANGUAGE_AND_OPINION_EVIDENCE",
        completeness_rule="EVERY_ACQUIRED_IN_SCOPE_DECISION_REQUIRES_ACCEPTED_ORIGINAL",
        outage_consequence="AFFECTED_ITEM_RELEASE_BLOCKING",
    ),
    SourceDefinition(
        source_id=HK_CASE_JUDICIARY_LIBRARY_SOURCE_ID,
        role="CONTROLLING",
        endpoint_families=("JUDICIARY_LIBRARY_HISTORICAL_INVENTORY",),
        checking_tier="HISTORICAL_BASELINE",
        permitted_use="HISTORICAL_SUPERIOR_COURT_INVENTORY_AND_ORIGINATING_EVIDENCE",
        completeness_rule="EVERY_PROMISED_HISTORICAL_SCOPE_REQUIRES_COMPLETE_ENUMERATION",
        outage_consequence="AFFECTED_HISTORICAL_SCOPE_BLOCKING",
    ),
    SourceDefinition(
        source_id=HK_CASE_LRS_INVENTORY_SOURCE_ID,
        role="CONTROLLING",
        endpoint_families=("JUDICIARY_LRS_COMPLETE_LISTING",),
        checking_tier="WORKING_DAY_AND_PARTITION_RECONCILIATION",
        permitted_use="CURRENT_OFFICIAL_LISTING_INVENTORY",
        completeness_rule="EVERY_DUE_COURT_YEAR_PARTITION_MUST_COMPLETE",
        outage_consequence="CURRENT_SCOPE_RELEASE_BLOCKING",
    ),
    SourceDefinition(
        source_id=HK_CASE_JUDICIARY_TRANSLATION_SOURCE_ID,
        role="CORROBORATING",
        endpoint_families=("JUDICIARY_TRANSLATION_ARTIFACT",),
        checking_tier="OPTIONAL_ITEM_EVIDENCE",
        permitted_use="LINKED_TRANSLATION_EVIDENCE_NOT_A_SECOND_AUTHORITY",
        completeness_rule="TRANSLATION_ABSENCE_NEVER_CREATES_A_COVERAGE_GAP",
        outage_consequence="NONBLOCKING_IF_ORIGINAL_IS_PROVED",
    ),
    SourceDefinition(
        source_id=HK_CASE_PRIVY_COUNCIL_SOURCE_ID,
        role="CONTROLLING",
        endpoint_families=("PRIVY_COUNCIL_HONG_KONG_APPEAL_INVENTORY",),
        checking_tier="HISTORICAL_BASELINE",
        permitted_use="HONG_KONG_PRIVY_COUNCIL_INVENTORY_AND_ORIGINATING_EVIDENCE",
        completeness_rule="EVERY_PROMISED_HKPC_SCOPE_REQUIRES_COMPLETE_ENUMERATION",
        outage_consequence="AFFECTED_HISTORICAL_SCOPE_BLOCKING",
    ),
)


class HKCaseListingErrorCode(StrEnum):
    """Closed listing-accounting contract failures."""

    CONTRACT = "HK_CASE_LISTING_CONTRACT_INVALID"
    DUPLICATE = "HK_CASE_LISTING_DUPLICATE"
    EVIDENCE = "HK_CASE_LISTING_EVIDENCE_INVALID"
    OUTCOME = "HK_CASE_LISTING_OUTCOME_INVALID"
    POST_CUTOFF = "HK_CASE_LISTING_POST_CUTOFF"
    SCOPE = "HK_CASE_LISTING_SCOPE_INVALID"
    SOURCE = "HK_CASE_LISTING_SOURCE_INVALID"


class HKCaseListingError(ValueError):
    """One fail-closed listing-accounting rejection."""

    code: HKCaseListingErrorCode

    def __init__(self, code: HKCaseListingErrorCode) -> None:
        """Create one stable fail-closed error."""
        self.code = code
        super().__init__(code.value)


class HKCaseCourtFamily(StrEnum):
    """Accepted ordinary and separately accountable historical families."""

    CFA = "CFA"
    CA = "CA"
    CFI = "CFI"
    COMPETITION_TRIBUNAL = "CT"
    HISTORICAL_SUPERIOR = "HKSUPERIOR"
    PRIVY_COUNCIL_HK = "HKPC"
    EXCLUDED_BODY = "EXCLUDED"


IN_SCOPE_COURT_FAMILIES = frozenset(
    {
        HKCaseCourtFamily.CFA,
        HKCaseCourtFamily.CA,
        HKCaseCourtFamily.CFI,
        HKCaseCourtFamily.COMPETITION_TRIBUNAL,
        HKCaseCourtFamily.HISTORICAL_SUPERIOR,
        HKCaseCourtFamily.PRIVY_COUNCIL_HK,
    }
)


@dataclass(frozen=True, slots=True)
class HKCaseScopeFamily:
    """One accepted court family before concrete year boundaries are frozen."""

    court_family: HKCaseCourtFamily
    ordinary_current_scope: bool
    required_inventory_source_ids: tuple[str, ...]
    historical_boundary_required: bool


@dataclass(frozen=True, slots=True)
class HKCaseScopeBoundary:
    """One evidence-bound inclusive year range for an accepted court family."""

    court_family: HKCaseCourtFamily
    first_year: int
    last_year: int
    boundary_evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseConcreteReleaseScope:
    """One generated court-family/year ownership scope before readiness."""

    scope_id: str
    court_family: HKCaseCourtFamily
    decision_year: int
    required_inventory_source_ids: tuple[str, ...]
    boundary_evidence_refs: tuple[str, ...]


HK_CASE_SCOPE_FAMILIES = (
    HKCaseScopeFamily(
        court_family=HKCaseCourtFamily.CA,
        ordinary_current_scope=True,
        required_inventory_source_ids=(HK_CASE_LRS_INVENTORY_SOURCE_ID,),
        historical_boundary_required=False,
    ),
    HKCaseScopeFamily(
        court_family=HKCaseCourtFamily.CFA,
        ordinary_current_scope=True,
        required_inventory_source_ids=(HK_CASE_LRS_INVENTORY_SOURCE_ID,),
        historical_boundary_required=False,
    ),
    HKCaseScopeFamily(
        court_family=HKCaseCourtFamily.CFI,
        ordinary_current_scope=True,
        required_inventory_source_ids=(HK_CASE_LRS_INVENTORY_SOURCE_ID,),
        historical_boundary_required=False,
    ),
    HKCaseScopeFamily(
        court_family=HKCaseCourtFamily.COMPETITION_TRIBUNAL,
        ordinary_current_scope=True,
        required_inventory_source_ids=(HK_CASE_LRS_INVENTORY_SOURCE_ID,),
        historical_boundary_required=False,
    ),
    HKCaseScopeFamily(
        court_family=HKCaseCourtFamily.PRIVY_COUNCIL_HK,
        ordinary_current_scope=False,
        required_inventory_source_ids=(HK_CASE_PRIVY_COUNCIL_SOURCE_ID,),
        historical_boundary_required=True,
    ),
    HKCaseScopeFamily(
        court_family=HKCaseCourtFamily.HISTORICAL_SUPERIOR,
        ordinary_current_scope=False,
        required_inventory_source_ids=(HK_CASE_JUDICIARY_LIBRARY_SOURCE_ID,),
        historical_boundary_required=True,
    ),
)


class HKCaseArtifactClass(StrEnum):
    """Accepted and explicitly excluded listing artifact classes."""

    JUDGMENT = "JUDGMENT"
    REASONS_FOR_JUDGMENT = "REASONS_FOR_JUDGMENT"
    REASONS_FOR_VERDICT = "REASONS_FOR_VERDICT"
    REASONS_FOR_SENTENCE = "REASONS_FOR_SENTENCE"
    MISCELLANEOUS_ACCEPTED = "MISCELLANEOUS_ACCEPTED"
    ORDER_WITHOUT_REASONS = "ORDER_WITHOUT_REASONS"
    NON_DECISION_MATERIAL = "NON_DECISION_MATERIAL"


IN_SCOPE_ARTIFACT_CLASSES = frozenset(
    {
        HKCaseArtifactClass.JUDGMENT,
        HKCaseArtifactClass.REASONS_FOR_JUDGMENT,
        HKCaseArtifactClass.REASONS_FOR_SENTENCE,
        HKCaseArtifactClass.REASONS_FOR_VERDICT,
        HKCaseArtifactClass.MISCELLANEOUS_ACCEPTED,
    }
)


class HKCaseArtifactRole(StrEnum):
    """Original decisions and optional official translations stay distinct."""

    ORIGINAL = "ORIGINAL"
    JUDICIARY_TRANSLATION = "JUDICIARY_TRANSLATION"


class HKCaseListingOutcome(StrEnum):
    """Exact ADR 0048 acquisition outcomes."""

    ACQUIRED = "ACQUIRED"
    DUPLICATE_OR_ALIAS = "DUPLICATE_OR_ALIAS"
    TRANSLATION_ARTIFACT = "TRANSLATION_ARTIFACT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    BLOCKED_UNAVAILABLE = "BLOCKED_UNAVAILABLE"
    QUARANTINED = "QUARANTINED"


class HKCaseDecisionOutcome(StrEnum):
    """Separate processing outcomes for an acquired decision."""

    PROPOSITIONS = "PROPOSITIONS"
    VALID_NO_MATERIAL_PROPOSITION = "VALID_NO_MATERIAL_PROPOSITION"
    PROCESSING_QUARANTINE = "PROCESSING_QUARANTINE"
    UNAVAILABLE_SCOPE = "UNAVAILABLE_SCOPE"


@dataclass(frozen=True, slots=True)
class OfficialJudgmentListingEntry:
    """One preserved official listing observation at one frozen cutoff."""

    listing_entry_id: str
    source_id: str
    observed_at: str
    cutoff: str
    court_family: HKCaseCourtFamily
    artifact_class: HKCaseArtifactClass
    decision_date: str
    release_scope_id: str | None
    artifact_role: HKCaseArtifactRole
    outcome: HKCaseListingOutcome
    decision_id: str | None
    artifact_id: str | None
    duplicate_of_listing_entry_id: str | None
    reason_code: str | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseDecisionDisposition:
    """One processing/search result for one acquired original decision."""

    decision_id: str
    outcome: HKCaseDecisionOutcome
    search_record_count: int
    reason_code: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HKCaseListingCycle:
    """One complete official-inventory accounting request."""

    observation_id: str
    cutoff: str
    due_source_ids: tuple[str, ...]
    completed_source_ids: tuple[str, ...]
    entries: tuple[OfficialJudgmentListingEntry, ...]
    decision_dispositions: tuple[HKCaseDecisionDisposition, ...]


@dataclass(frozen=True, slots=True)
class HKCaseListingAccounting:
    """Three separate completeness results plus exact search-output counts."""

    observation_id: str
    cutoff: str
    listing_entry_count: int
    acquired_decision_count: int
    acquisition_outcome_counts: tuple[tuple[str, int], ...]
    inventory_accounting_complete: bool
    evidence_coverage_complete: bool
    processing_accounting_complete: bool
    zero_record_decision_count: int
    one_record_decision_count: int
    many_record_decision_count: int
    search_record_count: int
    coverage_gap_codes: tuple[str, ...]
    release_eligible: bool


def hk_case_release_scope_id(court_family: HKCaseCourtFamily, decision_date: str) -> str:
    """Derive the accepted court-family/year ownership boundary."""
    if court_family not in IN_SCOPE_COURT_FAMILIES:
        raise HKCaseListingError(HKCaseListingErrorCode.SCOPE)
    parsed = _date(decision_date)
    return f"HK-CASE-{court_family.value}-{parsed.year:04d}"


def freeze_hk_case_release_scope_registry(
    boundaries: tuple[HKCaseScopeBoundary, ...], *, cutoff_year: int
) -> tuple[HKCaseConcreteReleaseScope, ...]:
    """Generate every concrete scope from one complete evidenced family boundary set."""
    if type(cutoff_year) is not int or not _MIN_CASE_YEAR <= cutoff_year <= _MAX_YEAR:
        raise HKCaseListingError(HKCaseListingErrorCode.SCOPE)
    families = {item.court_family: item for item in HK_CASE_SCOPE_FAMILIES}
    if (
        type(boundaries) is not tuple
        or tuple(item.court_family.value for item in boundaries)
        != tuple(sorted(item.court_family.value for item in boundaries))
        or len(boundaries) != len(families)
        or {item.court_family for item in boundaries} != set(families)
    ):
        raise HKCaseListingError(HKCaseListingErrorCode.SCOPE)
    result: list[HKCaseConcreteReleaseScope] = []
    for boundary in boundaries:
        family = families[boundary.court_family]
        _validate_scope_boundary(boundary, family, cutoff_year)
        result.extend(
            HKCaseConcreteReleaseScope(
                scope_id=f"HK-CASE-{boundary.court_family.value}-{year:04d}",
                court_family=boundary.court_family,
                decision_year=year,
                required_inventory_source_ids=family.required_inventory_source_ids,
                boundary_evidence_refs=boundary.boundary_evidence_refs,
            )
            for year in range(boundary.first_year, boundary.last_year + 1)
        )
    return tuple(result)


def _validate_scope_boundary(
    boundary: HKCaseScopeBoundary, family: HKCaseScopeFamily, cutoff_year: int
) -> None:
    if (
        type(boundary.first_year) is not int
        or type(boundary.last_year) is not int
        or not _MIN_CASE_YEAR <= boundary.first_year <= boundary.last_year <= cutoff_year
    ):
        raise HKCaseListingError(HKCaseListingErrorCode.SCOPE)
    _evidence(boundary.boundary_evidence_refs)
    if family.ordinary_current_scope and boundary.last_year != cutoff_year:
        raise HKCaseListingError(HKCaseListingErrorCode.SCOPE)
    if family.historical_boundary_required and boundary.last_year > _HANDOVER_YEAR:
        raise HKCaseListingError(HKCaseListingErrorCode.SCOPE)


def account_hk_case_listing_cycle(cycle: HKCaseListingCycle) -> HKCaseListingAccounting:
    """Validate and completely account one frozen official listing cycle."""
    cutoff, due, completed = _validate_cycle_header(cycle)
    by_id, outcome_counts, acquired_decisions, gap_codes = _account_entries(cycle, cutoff, due)
    _validate_relationships(by_id, acquired_decisions)
    dispositions, output_counts, disposition_gaps = _account_dispositions(
        cycle.decision_dispositions, acquired_decisions
    )
    gap_codes.update(disposition_gaps)
    missing_dispositions = acquired_decisions.difference(dispositions)
    for decision_id in missing_dispositions:
        gap_codes.add(f"HK_CASE_DECISION_PROCESSING_MISSING:{decision_id}")
    inventory_complete = set(completed) == set(due)
    if not inventory_complete:
        for source_id in set(due).difference(completed):
            gap_codes.add(f"HK_CASE_DUE_SOURCE_INCOMPLETE:{source_id}")
    evidence_complete = not any(
        entry.outcome
        in {HKCaseListingOutcome.BLOCKED_UNAVAILABLE, HKCaseListingOutcome.QUARANTINED}
        for entry in cycle.entries
    )
    processing_complete = not missing_dispositions and all(
        item.outcome
        in {
            HKCaseDecisionOutcome.PROPOSITIONS,
            HKCaseDecisionOutcome.VALID_NO_MATERIAL_PROPOSITION,
        }
        for item in dispositions.values()
    )
    release_eligible = inventory_complete and evidence_complete and processing_complete
    return HKCaseListingAccounting(
        observation_id=cycle.observation_id,
        cutoff=cycle.cutoff,
        listing_entry_count=len(cycle.entries),
        acquired_decision_count=len(acquired_decisions),
        acquisition_outcome_counts=tuple(sorted(outcome_counts.items())),
        inventory_accounting_complete=inventory_complete,
        evidence_coverage_complete=evidence_complete,
        processing_accounting_complete=processing_complete,
        zero_record_decision_count=output_counts[0],
        one_record_decision_count=output_counts[1],
        many_record_decision_count=output_counts[2],
        search_record_count=output_counts[3],
        coverage_gap_codes=tuple(sorted(gap_codes)),
        release_eligible=release_eligible,
    )


def _validate_cycle_header(
    cycle: HKCaseListingCycle,
) -> tuple[datetime, tuple[str, ...], tuple[str, ...]]:
    _nonempty(cycle.observation_id)
    cutoff = _timestamp(cycle.cutoff)
    due = _unique_sorted(cycle.due_source_ids)
    completed = _unique_sorted(cycle.completed_source_ids)
    if not due or not set(due).issubset(OFFICIAL_INVENTORY_SOURCE_IDS):
        raise HKCaseListingError(HKCaseListingErrorCode.SOURCE)
    if not set(completed).issubset(due):
        raise HKCaseListingError(HKCaseListingErrorCode.SOURCE)
    return cutoff, due, completed


def _account_entries(
    cycle: HKCaseListingCycle, cutoff: datetime, due: tuple[str, ...]
) -> tuple[
    dict[str, OfficialJudgmentListingEntry],
    dict[str, int],
    set[str],
    set[str],
]:
    by_id: dict[str, OfficialJudgmentListingEntry] = {}
    outcome_counts = {outcome.value: 0 for outcome in HKCaseListingOutcome}
    acquired_decisions: set[str] = set()
    gap_codes: set[str] = set()
    for entry in cycle.entries:
        _validate_entry(entry, cutoff, cycle.cutoff, due)
        if entry.listing_entry_id in by_id:
            raise HKCaseListingError(HKCaseListingErrorCode.DUPLICATE)
        by_id[entry.listing_entry_id] = entry
        outcome_counts[entry.outcome.value] += 1
        if entry.outcome is HKCaseListingOutcome.ACQUIRED:
            acquired_decisions.add(_required(entry.decision_id))
        elif entry.outcome in {
            HKCaseListingOutcome.BLOCKED_UNAVAILABLE,
            HKCaseListingOutcome.QUARANTINED,
        }:
            gap_codes.add(_required(entry.reason_code))
    return by_id, outcome_counts, acquired_decisions, gap_codes


def _account_dispositions(
    items: tuple[HKCaseDecisionDisposition, ...], acquired_decisions: set[str]
) -> tuple[dict[str, HKCaseDecisionDisposition], tuple[int, int, int, int], set[str]]:
    dispositions: dict[str, HKCaseDecisionDisposition] = {}
    zero_count = one_count = many_count = record_count = 0
    gap_codes: set[str] = set()
    for item in items:
        _validate_disposition(item, acquired_decisions)
        if item.decision_id in dispositions:
            raise HKCaseListingError(HKCaseListingErrorCode.DUPLICATE)
        dispositions[item.decision_id] = item
        if item.outcome is HKCaseDecisionOutcome.VALID_NO_MATERIAL_PROPOSITION:
            zero_count += 1
        elif item.outcome is HKCaseDecisionOutcome.PROPOSITIONS:
            record_count += item.search_record_count
            if item.search_record_count == 1:
                one_count += 1
            else:
                many_count += 1
        else:
            gap_codes.add(item.reason_code)
    return dispositions, (zero_count, one_count, many_count, record_count), gap_codes


def _validate_entry(
    entry: OfficialJudgmentListingEntry,
    cutoff: datetime,
    cutoff_text: str,
    due_sources: tuple[str, ...],
) -> None:
    _nonempty(entry.listing_entry_id)
    if entry.source_id not in due_sources or entry.source_id == HK_CASE_HKLII_DISCOVERY_SOURCE_ID:
        raise HKCaseListingError(HKCaseListingErrorCode.SOURCE)
    if entry.cutoff != cutoff_text or _timestamp(entry.observed_at) > cutoff:
        raise HKCaseListingError(HKCaseListingErrorCode.POST_CUTOFF)
    _date(entry.decision_date)
    _evidence(entry.evidence_refs)
    in_scope = (
        entry.court_family in IN_SCOPE_COURT_FAMILIES
        and entry.artifact_class in IN_SCOPE_ARTIFACT_CLASSES
    )
    expected_scope = (
        hk_case_release_scope_id(entry.court_family, entry.decision_date) if in_scope else None
    )
    if entry.release_scope_id != expected_scope:
        raise HKCaseListingError(HKCaseListingErrorCode.SCOPE)
    validator = _OUTCOME_VALIDATORS.get(entry.outcome)
    if validator is None:
        raise HKCaseListingError(HKCaseListingErrorCode.OUTCOME)
    validator(entry, in_scope=in_scope)


def _validate_acquired(entry: OfficialJudgmentListingEntry, *, in_scope: bool) -> None:
    if (
        not in_scope
        or entry.artifact_role is not HKCaseArtifactRole.ORIGINAL
        or not entry.decision_id
        or not entry.artifact_id
        or entry.duplicate_of_listing_entry_id is not None
        or entry.reason_code is not None
    ):
        raise HKCaseListingError(HKCaseListingErrorCode.OUTCOME)


def _validate_duplicate(entry: OfficialJudgmentListingEntry, *, in_scope: bool) -> None:
    if (
        not in_scope
        or entry.artifact_role is not HKCaseArtifactRole.ORIGINAL
        or not entry.decision_id
        or entry.artifact_id is not None
        or not entry.duplicate_of_listing_entry_id
        or entry.reason_code is not None
    ):
        raise HKCaseListingError(HKCaseListingErrorCode.OUTCOME)


def _validate_translation(entry: OfficialJudgmentListingEntry, *, in_scope: bool) -> None:
    if (
        not in_scope
        or entry.artifact_role is not HKCaseArtifactRole.JUDICIARY_TRANSLATION
        or not entry.decision_id
        or not entry.artifact_id
        or entry.duplicate_of_listing_entry_id is not None
        or entry.reason_code is not None
    ):
        raise HKCaseListingError(HKCaseListingErrorCode.OUTCOME)


def _validate_out_of_scope(entry: OfficialJudgmentListingEntry, *, in_scope: bool) -> None:
    if (
        in_scope
        or entry.release_scope_id is not None
        or not entry.reason_code
        or entry.decision_id is not None
        or entry.artifact_id is not None
        or entry.duplicate_of_listing_entry_id is not None
    ):
        raise HKCaseListingError(HKCaseListingErrorCode.OUTCOME)


def _validate_unresolved(entry: OfficialJudgmentListingEntry, *, in_scope: bool) -> None:
    if (
        not in_scope
        or entry.artifact_role is not HKCaseArtifactRole.ORIGINAL
        or not entry.reason_code
        or entry.artifact_id is not None
        or entry.duplicate_of_listing_entry_id is not None
    ):
        raise HKCaseListingError(HKCaseListingErrorCode.OUTCOME)


_OUTCOME_VALIDATORS = {
    HKCaseListingOutcome.ACQUIRED: _validate_acquired,
    HKCaseListingOutcome.DUPLICATE_OR_ALIAS: _validate_duplicate,
    HKCaseListingOutcome.TRANSLATION_ARTIFACT: _validate_translation,
    HKCaseListingOutcome.OUT_OF_SCOPE: _validate_out_of_scope,
    HKCaseListingOutcome.BLOCKED_UNAVAILABLE: _validate_unresolved,
    HKCaseListingOutcome.QUARANTINED: _validate_unresolved,
}


def _validate_relationships(
    entries: dict[str, OfficialJudgmentListingEntry], acquired_decisions: set[str]
) -> None:
    for entry in entries.values():
        if entry.outcome is HKCaseListingOutcome.DUPLICATE_OR_ALIAS:
            target = entries.get(entry.duplicate_of_listing_entry_id or "")
            if (
                target is None
                or target.outcome is not HKCaseListingOutcome.ACQUIRED
                or target.decision_id != entry.decision_id
            ):
                raise HKCaseListingError(HKCaseListingErrorCode.OUTCOME)
        if entry.outcome is HKCaseListingOutcome.TRANSLATION_ARTIFACT and (
            entry.decision_id not in acquired_decisions
        ):
            raise HKCaseListingError(HKCaseListingErrorCode.EVIDENCE)


def _validate_disposition(
    disposition: HKCaseDecisionDisposition, acquired_decisions: set[str]
) -> None:
    if disposition.decision_id not in acquired_decisions:
        raise HKCaseListingError(HKCaseListingErrorCode.EVIDENCE)
    _nonempty(disposition.reason_code)
    _evidence(disposition.evidence_refs)
    if type(disposition.search_record_count) is not int:
        raise HKCaseListingError(HKCaseListingErrorCode.CONTRACT)
    if disposition.outcome is HKCaseDecisionOutcome.PROPOSITIONS:
        if disposition.search_record_count < 1:
            raise HKCaseListingError(HKCaseListingErrorCode.OUTCOME)
    elif disposition.search_record_count != 0:
        raise HKCaseListingError(HKCaseListingErrorCode.OUTCOME)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except TypeError, ValueError:
        raise HKCaseListingError(HKCaseListingErrorCode.CONTRACT) from None
    if parsed.tzinfo is None:
        raise HKCaseListingError(HKCaseListingErrorCode.CONTRACT)
    return parsed.astimezone(UTC)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except TypeError, ValueError:
        raise HKCaseListingError(HKCaseListingErrorCode.CONTRACT) from None


def _nonempty(value: str) -> None:
    if type(value) is not str or not value:
        raise HKCaseListingError(HKCaseListingErrorCode.CONTRACT)


def _required(value: str | None) -> str:
    if value is None:
        raise HKCaseListingError(HKCaseListingErrorCode.CONTRACT)
    _nonempty(value)
    return value


def _evidence(values: tuple[str, ...]) -> None:
    if not values or values != tuple(sorted(set(values))):
        raise HKCaseListingError(HKCaseListingErrorCode.EVIDENCE)
    for value in values:
        _nonempty(value)


def _unique_sorted(values: tuple[str, ...]) -> tuple[str, ...]:
    if values != tuple(sorted(set(values))):
        raise HKCaseListingError(HKCaseListingErrorCode.CONTRACT)
    for value in values:
        _nonempty(value)
    return values
