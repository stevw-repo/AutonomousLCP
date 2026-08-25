"""Deterministic HKEX source-entry and rule-component inventory accounting."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .model import SourceDefinition

HKEX_MAIN_SCOPE_ID = "HK-REG-HKEX-MAIN-BOARD"
HKEX_GEM_SCOPE_ID = "HK-REG-HKEX-GEM"
HKEX_SCOPE_IDS = (HKEX_GEM_SCOPE_ID, HKEX_MAIN_SCOPE_ID)

HKEX_RULEBOOK_CATALOGUE_SOURCE_ID = "HK-REG-HKEX-RULEBOOK-CATALOGUE"
HKEX_CONSOLIDATED_RULEBOOKS_SOURCE_ID = "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS"
HKEX_REGULATORY_FORMS_SOURCE_ID = "HK-REG-HKEX-REGULATORY-FORMS"
HKEX_FEES_RULES_SOURCE_ID = "HK-REG-HKEX-FEES-RULES"
HKEX_RULE_UPDATES_SOURCE_ID = "HK-REG-HKEX-RULE-UPDATES"
HKEX_REGULATORY_SOURCE_IDS = (
    HKEX_CONSOLIDATED_RULEBOOKS_SOURCE_ID,
    HKEX_FEES_RULES_SOURCE_ID,
    HKEX_REGULATORY_FORMS_SOURCE_ID,
    HKEX_RULE_UPDATES_SOURCE_ID,
    HKEX_RULEBOOK_CATALOGUE_SOURCE_ID,
)

HKEX_REGULATORY_SOURCE_UNIVERSE = (
    SourceDefinition(
        source_id=HKEX_CONSOLIDATED_RULEBOOKS_SOURCE_ID,
        role="CONTROLLING",
        endpoint_families=("HKEX_MAIN_AND_GEM_CONSOLIDATED_ENGLISH_RULEBOOKS",),
        checking_tier="DAILY_SIGNAL_AND_CHANGE_TRIGGERED_COMPLETE_ARTIFACT",
        permitted_use="PREVAILING_ENGLISH_WORDING_AND_CONTAINED_OFFICIAL_STRUCTURE",
        completeness_rule="ENUMERATE_EVERY_COMPONENT_NOT_ONLY_TABLE_OF_CONTENTS",
        outage_consequence="BOUNDED_BOARD_OR_UNBOUNDED_BOTH_SCOPE_BLOCKING",
    ),
    SourceDefinition(
        source_id=HKEX_FEES_RULES_SOURCE_ID,
        role="CONTROLLING",
        endpoint_families=("HKEX_MAIN_AND_GEM_FEES_RULES",),
        checking_tier="DAILY_INVENTORY_AND_CHANGE_TRIGGERED_ARTIFACT",
        permitted_use="SEPARATE_FEES_RULE_MEMBERSHIP_OWNERSHIP_AND_ENGLISH_CONTENT",
        completeness_rule="ENUMERATE_EVERY_REQUIRED_ENGLISH_FEES_RULE_PER_BOARD",
        outage_consequence="BOUNDED_BOARD_OR_UNBOUNDED_BOTH_SCOPE_BLOCKING",
    ),
    SourceDefinition(
        source_id=HKEX_REGULATORY_FORMS_SOURCE_ID,
        role="CONTROLLING",
        endpoint_families=("HKEX_MAIN_AND_GEM_REGULATORY_FORMS",),
        checking_tier="DAILY_INVENTORY_AND_CHANGE_TRIGGERED_ARTIFACT",
        permitted_use="SEPARATE_FORM_MEMBERSHIP_OWNERSHIP_AND_ENGLISH_CONTENT",
        completeness_rule="ENUMERATE_EVERY_REQUIRED_ENGLISH_REGULATORY_FORM_PER_BOARD",
        outage_consequence="BOUNDED_BOARD_OR_UNBOUNDED_BOTH_SCOPE_BLOCKING",
    ),
    SourceDefinition(
        source_id=HKEX_RULE_UPDATES_SOURCE_ID,
        role="CONTROLLING",
        endpoint_families=("HKEX_MAIN_AND_GEM_FINAL_RULE_UPDATES",),
        checking_tier="DAILY_UPDATE_INVENTORY_AND_CHANGE_TRIGGERED_PACKAGE",
        permitted_use="FINAL_CHANGE_WORDING_TIMING_CONDITION_TRANSITION_AND_MAPPING_FACTS",
        completeness_rule="ENUMERATE_EVERY_DUE_FINAL_UPDATE_AND_LINKED_CLASSIFICATION_ARTIFACT",
        outage_consequence="AFFECTED_BOARD_FRESH_RELEASE_BLOCKING",
    ),
    SourceDefinition(
        source_id=HKEX_RULEBOOK_CATALOGUE_SOURCE_ID,
        role="CONTROLLING",
        endpoint_families=("HKEX_LISTING_RULES_PRODUCT_CATALOGUE",),
        checking_tier="DAILY_SIGNAL_AND_WEEKLY_COMPLETE_OBSERVATION",
        permitted_use="TOP_LEVEL_PRODUCT_FAMILIES_BOARD_ASSOCIATION_AND_CURRENT_LOCATORS",
        completeness_rule="BOUNDS_FAMILIES_BUT_NEVER_PROVES_COMPONENT_WORDING_OR_LIST_ALONE",
        outage_consequence="UNBOUNDED_BOTH_SCOPE_RELEASE_BLOCKING",
    ),
)


class HKEXInventoryErrorCode(StrEnum):
    """Closed deterministic inventory-contract failures."""

    COMPONENT = "HKEX_COMPONENT_INVENTORY_INVALID"
    DUPLICATE = "HKEX_COMPONENT_INVENTORY_DUPLICATE"
    ENTRY = "HKEX_SOURCE_ENTRY_INVALID"
    SOURCE = "HKEX_SOURCE_OBSERVATION_INVALID"
    STRUCTURE = "HKEX_COMPONENT_STRUCTURE_INVALID"


class HKEXInventoryError(ValueError):
    """One fail-closed inventory-accounting rejection."""

    code: HKEXInventoryErrorCode

    def __init__(self, code: HKEXInventoryErrorCode) -> None:
        """Create one stable fail-closed error."""
        self.code = code
        super().__init__(code.value)


class HKEXMembership(StrEnum):
    """Exact ADR 0069 source-entry membership results."""

    RULE_COMPONENT = "RULE_COMPONENT"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    EXCLUDED_NON_RULE = "EXCLUDED_NON_RULE"
    UNRESOLVED_MEMBERSHIP = "UNRESOLVED_MEMBERSHIP"


class HKEXBranchState(StrEnum):
    """Atomic ADR 0071 applicability-branch states."""

    CURRENT = "CURRENT"
    TRANSITIONAL_CURRENT = "TRANSITIONAL_CURRENT"
    FUTURE_FIXED_DATE = "FUTURE_FIXED_DATE"
    FUTURE_CONDITIONAL = "FUTURE_CONDITIONAL"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"
    UNKNOWN = "UNKNOWN"


class HKEXComponentState(StrEnum):
    """Derived component summary without flattening branch facts."""

    CURRENT = "CURRENT"
    TRANSITIONAL_CURRENT = "TRANSITIONAL_CURRENT"
    FUTURE_FIXED_DATE = "FUTURE_FIXED_DATE"
    FUTURE_CONDITIONAL = "FUTURE_CONDITIONAL"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"
    UNKNOWN = "UNKNOWN"


class HKEXMaterialDisposition(StrEnum):
    """Material disposition kept separate from state and processing."""

    SEARCHABLE_CURRENT_RULE_COMPONENT = "SEARCHABLE_CURRENT_RULE_COMPONENT"
    REGULATORY_WAITING_ROOM = "REGULATORY_WAITING_ROOM"
    HISTORICAL = "HISTORICAL"
    QUARANTINE = "QUARANTINE"


class HKEXProcessingOutcome(StrEnum):
    """Exact processing terminal families."""

    PASS = "PASS"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"


@dataclass(frozen=True, slots=True)
class HKEXSourceObservation:
    """One source-role observation bounded to one or both board scopes."""

    observation_id: str
    source_id: str
    scope_ids: tuple[str, ...]
    complete: bool
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject source-role, scope, and completeness drift."""
        _text(self.observation_id)
        if self.source_id not in HKEX_REGULATORY_SOURCE_IDS:
            raise HKEXInventoryError(HKEXInventoryErrorCode.SOURCE)
        _scopes(self.scope_ids)
        if type(self.complete) is not bool:
            raise HKEXInventoryError(HKEXInventoryErrorCode.SOURCE)
        _strings(self.evidence_refs)
        if self.source_id == HKEX_RULEBOOK_CATALOGUE_SOURCE_ID and self.scope_ids != (
            HKEX_GEM_SCOPE_ID,
            HKEX_MAIN_SCOPE_ID,
        ):
            raise HKEXInventoryError(HKEXInventoryErrorCode.SOURCE)


@dataclass(frozen=True, slots=True)
class HKEXObservedSourceEntry:
    """One observed source object with one explicit membership outcome."""

    entry_id: str
    source_id: str
    scope_ids: tuple[str, ...]
    membership: HKEXMembership
    owner_scope_id: str | None
    component_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Keep entry membership and component ownership consistent."""
        _text(self.entry_id)
        if self.source_id not in HKEX_REGULATORY_SOURCE_IDS:
            raise HKEXInventoryError(HKEXInventoryErrorCode.ENTRY)
        _scopes(self.scope_ids)
        if type(self.membership) is not HKEXMembership:
            raise HKEXInventoryError(HKEXInventoryErrorCode.ENTRY)
        _strings(self.evidence_refs)
        if self.membership is HKEXMembership.RULE_COMPONENT:
            if self.owner_scope_id not in self.scope_ids:
                raise HKEXInventoryError(HKEXInventoryErrorCode.ENTRY)
            _strings(self.component_ids)
        elif self.owner_scope_id is not None or self.component_ids:
            raise HKEXInventoryError(HKEXInventoryErrorCode.ENTRY)


@dataclass(frozen=True, slots=True)
class HKEXApplicabilityBranch:
    """One retained atomic state decision for one rule wording branch."""

    branch_id: str
    state: HKEXBranchState
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate one retained branch decision."""
        _text(self.branch_id)
        if type(self.state) is not HKEXBranchState:
            raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)
        _strings(self.evidence_refs)


@dataclass(frozen=True, slots=True)
class HKEXRuleComponent:
    """One board-owned component with complete branch and structure accounting."""

    component_id: str
    scope_id: str
    source_entry_ids: tuple[str, ...]
    parent_component_id: str | None
    structural_order: int
    branches: tuple[HKEXApplicabilityBranch, ...]
    component_state: HKEXComponentState
    disposition: HKEXMaterialDisposition
    processing_outcome: HKEXProcessingOutcome
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate state, disposition, processing, and local structure."""
        _text(self.component_id)
        if self.scope_id not in HKEX_SCOPE_IDS:
            raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)
        _strings(self.source_entry_ids)
        if self.parent_component_id is not None:
            _text(self.parent_component_id)
            if self.parent_component_id == self.component_id:
                raise HKEXInventoryError(HKEXInventoryErrorCode.STRUCTURE)
        if type(self.structural_order) is not int or self.structural_order < 0:
            raise HKEXInventoryError(HKEXInventoryErrorCode.STRUCTURE)
        if type(self.branches) is not tuple or not self.branches:
            raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)
        if len({branch.branch_id for branch in self.branches}) != len(self.branches):
            raise HKEXInventoryError(HKEXInventoryErrorCode.DUPLICATE)
        if self.component_state is not derive_hkex_component_state(self.branches):
            raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)
        _validate_disposition(self)
        _strings(self.evidence_refs)


@dataclass(frozen=True, slots=True)
class HKEXInventoryCycle:
    """One frozen source-neutral inventory accounting request."""

    cutoff: str
    observations: tuple[HKEXSourceObservation, ...]
    entries: tuple[HKEXObservedSourceEntry, ...]
    components: tuple[HKEXRuleComponent, ...]


@dataclass(frozen=True, slots=True)
class HKEXScopeInventoryAccounting:
    """Four separate ADR 0069 results without a serving-readiness claim."""

    scope_id: str
    observed_entry_count: int
    component_count: int
    membership_counts: tuple[tuple[str, int], ...]
    component_state_counts: tuple[tuple[str, int], ...]
    source_observations_complete: bool
    source_entry_accounting_complete: bool
    component_ownership_structure_complete: bool
    current_state_accounting_complete: bool
    blocking_entry_ids: tuple[str, ...]
    blocking_component_ids: tuple[str, ...]
    inventory_candidate_ready: bool
    serving_ready: bool
    serving_blocker: str


def derive_hkex_component_state(
    branches: tuple[HKEXApplicabilityBranch, ...],
) -> HKEXComponentState:
    """Derive the ADR 0071 summary while retaining every atomic branch."""
    if type(branches) is not tuple or not branches:
        raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)
    states = tuple(branch.state for branch in branches)
    state_set = frozenset(states)
    if HKEXBranchState.UNKNOWN in state_set:
        result = HKEXComponentState.UNKNOWN
    else:
        ordinary_current_count = states.count(HKEXBranchState.CURRENT)
        transitional_count = states.count(HKEXBranchState.TRANSITIONAL_CURRENT)
        if ordinary_current_count == 1 and transitional_count == 0:
            result = HKEXComponentState.CURRENT
        elif ordinary_current_count > 1 or transitional_count:
            result = HKEXComponentState.TRANSITIONAL_CURRENT
        elif state_set == frozenset({HKEXBranchState.FUTURE_FIXED_DATE}):
            result = HKEXComponentState.FUTURE_FIXED_DATE
        elif state_set == frozenset({HKEXBranchState.FUTURE_CONDITIONAL}):
            result = HKEXComponentState.FUTURE_CONDITIONAL
        elif state_set == frozenset({HKEXBranchState.SUPERSEDED}):
            result = HKEXComponentState.SUPERSEDED
        elif state_set == frozenset({HKEXBranchState.WITHDRAWN}):
            result = HKEXComponentState.WITHDRAWN
        else:
            result = HKEXComponentState.UNKNOWN
    return result


def account_hkex_component_inventory(
    cycle: HKEXInventoryCycle,
) -> tuple[HKEXScopeInventoryAccounting, ...]:
    """Validate the complete graph and report exact per-board inventory results."""
    if type(cycle) is not HKEXInventoryCycle:
        raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)
    _text(cycle.cutoff)
    observation_pairs = _index_observations(cycle.observations)
    entries, components = _validate_component_graph(cycle.entries, cycle.components)
    return tuple(
        _scope_accounting(scope_id, observation_pairs, entries, components)
        for scope_id in HKEX_SCOPE_IDS
    )


def _index_observations(
    observations: tuple[HKEXSourceObservation, ...],
) -> dict[tuple[str, str], HKEXSourceObservation]:
    observation_pairs: dict[tuple[str, str], HKEXSourceObservation] = {}
    for observation in observations:
        if type(observation) is not HKEXSourceObservation:
            raise HKEXInventoryError(HKEXInventoryErrorCode.SOURCE)
        for scope_id in observation.scope_ids:
            key = (observation.source_id, scope_id)
            if key in observation_pairs:
                raise HKEXInventoryError(HKEXInventoryErrorCode.DUPLICATE)
            observation_pairs[key] = observation
    return observation_pairs


def _validate_component_graph(
    entry_values: tuple[HKEXObservedSourceEntry, ...],
    component_values: tuple[HKEXRuleComponent, ...],
) -> tuple[dict[str, HKEXObservedSourceEntry], dict[str, HKEXRuleComponent]]:
    entries = _unique_by_id(entry_values, "entry_id", HKEXInventoryErrorCode.ENTRY)
    components = _unique_by_id(
        component_values,
        "component_id",
        HKEXInventoryErrorCode.COMPONENT,
    )
    _validate_entry_component_links(entries, components)
    _validate_component_structure(entries, components)
    return entries, components


def _validate_entry_component_links(
    entries: dict[str, HKEXObservedSourceEntry],
    components: dict[str, HKEXRuleComponent],
) -> None:
    referenced_components: set[str] = set()
    for entry in entries.values():
        if type(entry) is not HKEXObservedSourceEntry:
            raise HKEXInventoryError(HKEXInventoryErrorCode.ENTRY)
        for component_id in entry.component_ids:
            component = components.get(component_id)
            if component is None or component.scope_id != entry.owner_scope_id:
                raise HKEXInventoryError(HKEXInventoryErrorCode.ENTRY)
            referenced_components.add(component_id)
    if referenced_components != set(components):
        raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)


def _validate_component_structure(
    entries: dict[str, HKEXObservedSourceEntry],
    components: dict[str, HKEXRuleComponent],
) -> None:
    positions: set[tuple[str, str | None, int]] = set()
    for component in components.values():
        if type(component) is not HKEXRuleComponent:
            raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)
        if not set(component.source_entry_ids).issubset(entries):
            raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)
        for entry_id in component.source_entry_ids:
            entry = entries[entry_id]
            if component.component_id not in entry.component_ids:
                raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)
        if component.parent_component_id is not None:
            parent = components.get(component.parent_component_id)
            if parent is None or parent.scope_id != component.scope_id:
                raise HKEXInventoryError(HKEXInventoryErrorCode.STRUCTURE)
        position = (component.scope_id, component.parent_component_id, component.structural_order)
        if position in positions:
            raise HKEXInventoryError(HKEXInventoryErrorCode.DUPLICATE)
        positions.add(position)
        _prove_acyclic(component, components)


def _scope_accounting(
    scope_id: str,
    observation_pairs: dict[tuple[str, str], HKEXSourceObservation],
    entries: dict[str, HKEXObservedSourceEntry],
    components: dict[str, HKEXRuleComponent],
) -> HKEXScopeInventoryAccounting:
    scope_entries = tuple(entry for entry in entries.values() if scope_id in entry.scope_ids)
    scope_components = tuple(
        component for component in components.values() if component.scope_id == scope_id
    )
    observations_complete = all(
        (observation := observation_pairs.get((source_id, scope_id))) is not None
        and observation.complete
        for source_id in HKEX_REGULATORY_SOURCE_IDS
    )
    blocking_entries = tuple(
        sorted(
            entry.entry_id
            for entry in scope_entries
            if entry.membership is HKEXMembership.UNRESOLVED_MEMBERSHIP
        )
    )
    blocking_components = tuple(
        sorted(
            component.component_id
            for component in scope_components
            if component.processing_outcome is not HKEXProcessingOutcome.PASS
        )
    )
    candidate_ready = observations_complete and not blocking_entries and not blocking_components
    return HKEXScopeInventoryAccounting(
        scope_id=scope_id,
        observed_entry_count=len(scope_entries),
        component_count=len(scope_components),
        membership_counts=_counts(
            HKEXMembership,
            (entry.membership for entry in scope_entries),
        ),
        component_state_counts=_counts(
            HKEXComponentState,
            (component.component_state for component in scope_components),
        ),
        source_observations_complete=observations_complete,
        source_entry_accounting_complete=observations_complete,
        component_ownership_structure_complete=True,
        current_state_accounting_complete=True,
        blocking_entry_ids=blocking_entries,
        blocking_component_ids=blocking_components,
        inventory_candidate_ready=candidate_ready,
        serving_ready=False,
        serving_blocker="ENGLISH_RECORD_TRACEABILITY_AND_RELEASE_LAYER_NOT_EVALUATED",
    )


def _validate_disposition(component: HKEXRuleComponent) -> None:
    state = component.component_state
    disposition = component.disposition
    outcome = component.processing_outcome
    if state in {HKEXComponentState.CURRENT, HKEXComponentState.TRANSITIONAL_CURRENT}:
        if outcome is HKEXProcessingOutcome.PASS:
            valid = disposition is HKEXMaterialDisposition.SEARCHABLE_CURRENT_RULE_COMPONENT
        else:
            valid = disposition is HKEXMaterialDisposition.QUARANTINE
    elif state in {
        HKEXComponentState.FUTURE_FIXED_DATE,
        HKEXComponentState.FUTURE_CONDITIONAL,
    }:
        valid = (
            disposition is HKEXMaterialDisposition.REGULATORY_WAITING_ROOM
            and outcome is HKEXProcessingOutcome.PASS
        )
    elif state in {HKEXComponentState.SUPERSEDED, HKEXComponentState.WITHDRAWN}:
        valid = (
            disposition is HKEXMaterialDisposition.HISTORICAL
            and outcome is HKEXProcessingOutcome.PASS
        )
    else:
        valid = (
            disposition is HKEXMaterialDisposition.QUARANTINE
            and outcome is HKEXProcessingOutcome.QUARANTINE
        )
    if not valid:
        raise HKEXInventoryError(HKEXInventoryErrorCode.COMPONENT)


def _unique_by_id[T: object](
    values: tuple[T, ...], field: str, code: HKEXInventoryErrorCode
) -> dict[str, T]:
    if type(values) is not tuple:
        raise HKEXInventoryError(code)
    result: dict[str, T] = {}
    for value in values:
        identity = getattr(value, field, None)
        if type(identity) is not str or identity in result:
            raise HKEXInventoryError(HKEXInventoryErrorCode.DUPLICATE)
        result[identity] = value
    return result


def _prove_acyclic(
    component: HKEXRuleComponent,
    components: dict[str, HKEXRuleComponent],
) -> None:
    seen = {component.component_id}
    parent_id = component.parent_component_id
    while parent_id is not None:
        if parent_id in seen:
            raise HKEXInventoryError(HKEXInventoryErrorCode.STRUCTURE)
        seen.add(parent_id)
        parent = components.get(parent_id)
        if parent is None:
            raise HKEXInventoryError(HKEXInventoryErrorCode.STRUCTURE)
        parent_id = parent.parent_component_id


def _counts[E: StrEnum](enum_type: type[E], values: Iterable[E]) -> tuple[tuple[str, int], ...]:
    materialized = tuple(values)
    return tuple((item.value, materialized.count(item)) for item in enum_type)


def _text(value: object) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise HKEXInventoryError(HKEXInventoryErrorCode.ENTRY)
    return value


def _strings(values: tuple[str, ...]) -> tuple[str, ...]:
    if (
        type(values) is not tuple
        or not values
        or any(type(item) is not str or not item for item in values)
        or len(values) != len(set(values))
    ):
        raise HKEXInventoryError(HKEXInventoryErrorCode.ENTRY)
    return values


def _scopes(values: tuple[str, ...]) -> tuple[str, ...]:
    _strings(values)
    if values != tuple(sorted(values)) or not set(values).issubset(HKEX_SCOPE_IDS):
        raise HKEXInventoryError(HKEXInventoryErrorCode.ENTRY)
    return values
