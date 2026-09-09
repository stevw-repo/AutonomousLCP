"""Fail-closed, source-shaped HKEX observation inventory contracts only."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote_to_bytes, urlsplit

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value

from .model import HttpMethod, exact_identifier
from .official import (
    EndpointAccessMode,
    OfficialEndpointContract,
    OfficialSourceState,
    PublisherRightsState,
    SignalUse,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

HKEX_REGULATORY_SOURCE_IDS = (
    "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
    "HK-REG-HKEX-FEES-RULES",
    "HK-REG-HKEX-REGULATORY-FORMS",
    "HK-REG-HKEX-RULE-UPDATES",
    "HK-REG-HKEX-RULEBOOK-CATALOGUE",
)
_MAX_REGISTER_BYTES = 250_000
_MAX_ENTRIES = 1_000_000
_MAX_TEXT = 1_024
_MAX_DEPTH = 32
_IDENTITY = re.compile(r"^[a-z][a-z0-9-]{2,159}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_NUMERIC_IP_LABEL = re.compile(r"^(?:0[xX][0-9a-fA-F]+|0[0-7]*|[0-9]+)$")
_HEX = frozenset("0123456789abcdefABCDEF")
_PERCENT_AMBIGUOUS_BYTES = frozenset(b":/?#[]@\\%")
_TERMINAL_FIELD_NAMES = (
    "source_id",
    "source_profile_version",
    "board",
    "observed_at",
    "terminal_code",
    "declared_member_count",
)
_ENTRY_FIELD_NAMES = (
    "observation_id",
    "source_id",
    "board",
    "product_identity",
    "source_object_kind",
    "official_locator",
    "artifact_fingerprint",
    "source_order",
    "parent_observation_id",
    "declared_child_count",
)


class HKEXPublisherBoard(StrEnum):
    """Publisher tokens, deliberately not HKEX release-scope identifiers."""

    MAIN = "MAIN"
    GEM = "GEM"


class HKEXSourceObjectKind(StrEnum):
    """Closed publisher-shaped objects; none has legal membership here."""

    CHAPTER = "CHAPTER"
    RULE = "RULE"
    NOTE = "NOTE"
    APPENDIX = "APPENDIX"
    PRACTICE_NOTE = "PRACTICE_NOTE"
    REGULATORY_FORM = "REGULATORY_FORM"
    FEES_RULE = "FEES_RULE"
    PRODUCT_FAMILY = "PRODUCT_FAMILY"
    UPDATE_EVIDENCE_OBJECT = "UPDATE_EVIDENCE_OBJECT"
    EXCLUSION_CANDIDATE = "EXCLUSION_CANDIDATE"
    UNKNOWN_SOURCE_OBJECT = "UNKNOWN_SOURCE_OBJECT"


class HKEXTerminalCode(StrEnum):
    """Technical acquisition terminal codes, never legal dispositions."""

    COMPLETE = "COMPLETE"
    OUTAGE = "OUTAGE"
    CONTRACT_DRIFT = "CONTRACT_DRIFT"
    UNSAFE_RESPONSE = "UNSAFE_RESPONSE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class HKEXSourceAccessBoundary:
    """Exact local-only capability boundary for source-observation work."""

    state: str
    forbidden_effects: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.state, "state")
        _canonical_text_tuple(
            self.forbidden_effects,
            "forbidden_effects",
            minimum=len(_FORBIDDEN_EFFECTS),
        )
        if self.state != "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING":
            raise ValueError("HKEX access authority provenance drift")
        if self.forbidden_effects != _FORBIDDEN_EFFECTS:
            raise ValueError("HKEX forbidden effects must remain exact")


@dataclass(frozen=True, slots=True)
class HKEXSourceProfile:
    """One endpoint-free source role and its duplicated policy facts."""

    source_id: str
    registered_source_id: str
    version: str
    source_policy_owner: str
    endpoint_ids: tuple[str, ...]
    rights_state: PublisherRightsState
    operational_state: OfficialSourceState
    outage_consequence: str
    fact_authority: str
    completeness_authority: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_source_profile(self)


@dataclass(frozen=True, slots=True)
class HKEXSourceRegister:
    """Checked-in five-role source register with no admitted endpoint."""

    schema_id: str
    schema_version: str
    register_id: str
    register_version: str
    effective_date: str
    status: str
    fingerprint: str
    access_boundary: HKEXSourceAccessBoundary
    sources: tuple[HKEXSourceProfile, ...]
    endpoints: tuple[OfficialEndpointContract, ...]

    def __post_init__(self) -> None:
        for name in ("schema_id", "schema_version", "register_version", "effective_date", "status"):
            _text(getattr(self, name), name)
        exact_identifier(self.register_id, "register_id", "hrr")
        _fingerprint(self.fingerprint, "fingerprint")
        if (
            self.schema_id,
            self.schema_version,
            self.register_id,
            self.register_version,
            self.effective_date,
            self.status,
        ) != _EXPECTED_REGISTER_FACTS:
            raise ValueError("HKEX register identity provenance drift")
        if self.status != "AUTHORIZED_PARTIAL_FAIL_VISIBLE":
            raise ValueError("HKEX register authority status drift")
        if type(self.access_boundary) is not HKEXSourceAccessBoundary:
            raise TypeError("access_boundary must be exact")
        if type(self.sources) is not tuple or type(self.endpoints) is not tuple:
            raise TypeError("register collections must be exact tuples")
        self.access_boundary.__post_init__()
        if any(type(source) is not HKEXSourceProfile for source in self.sources):
            raise TypeError("source profiles must be exact")
        for source in self.sources:
            _validate_source_profile(source)
        if tuple(source.source_id for source in self.sources) != HKEX_REGULATORY_SOURCE_IDS:
            raise ValueError("register must contain the canonical five-role universe")
        if any(type(endpoint) is not OfficialEndpointContract for endpoint in self.endpoints):
            raise TypeError("HKEX endpoints must be exact")
        endpoint_map = {endpoint.endpoint_id: endpoint for endpoint in self.endpoints}
        if len(endpoint_map) != len(self.endpoints):
            raise ValueError("HKEX endpoint identities must be unique")
        referenced = {item for source in self.sources for item in source.endpoint_ids}
        if referenced != set(endpoint_map):
            raise ValueError("every HKEX endpoint must have exactly one owning source")
        for source in self.sources:
            for endpoint_id in source.endpoint_ids:
                endpoint = endpoint_map[endpoint_id]
                if endpoint.source_id != source.source_id or not endpoint.enabled:
                    raise ValueError("HKEX endpoint ownership or admission drift")
                if (endpoint.source_id, endpoint.url) != _EXPECTED_ENDPOINTS.get(endpoint_id):
                    raise ValueError("HKEX endpoint contract drift")
        if len({source.registered_source_id for source in self.sources}) != len(self.sources):
            raise ValueError("registered source identities must be unique")
        if self.fingerprint != _register_fingerprint_from_register(self):
            raise ValueError("HKEX source register fingerprint drift")

    @property
    def operationally_admitted(self) -> bool:
        """Report the deliberately false local-only operational state."""
        return False

    def resolve_endpoint(
        self, endpoint_id: str, endpoint_version: str
    ) -> tuple[HKEXSourceProfile, OfficialEndpointContract]:
        """Resolve one exact authorized endpoint without implying role completeness."""
        exact_identifier(endpoint_id, "endpoint_id", "sep")
        _text(endpoint_version, "endpoint_version")
        endpoint = next(
            (
                item
                for item in self.endpoints
                if item.endpoint_id == endpoint_id and item.version == endpoint_version
            ),
            None,
        )
        if endpoint is None:
            raise LookupError("HKEX endpoint or exact version is unavailable")
        source = next(item for item in self.sources if item.source_id == endpoint.source_id)
        if source.operational_state is OfficialSourceState.BLOCKED or not endpoint.enabled:
            raise PermissionError("HKEX source is not operationally configured")
        return source, endpoint


@dataclass(frozen=True, slots=True)
class HKEXSourceTerminal:
    """One source-role/publisher-board terminal accounting result."""

    source_id: str
    source_profile_version: str
    board: HKEXPublisherBoard
    observed_at: str
    terminal_code: HKEXTerminalCode
    declared_member_count: int
    terminal_fingerprint: str

    def __post_init__(self) -> None:
        _text(self.source_id, "source_id")
        if self.source_id not in HKEX_REGULATORY_SOURCE_IDS:
            raise ValueError("HKEX source terminal has unknown source")
        _text(self.source_profile_version, "source_profile_version")
        if (
            type(self.board) is not HKEXPublisherBoard
            or type(self.terminal_code) is not HKEXTerminalCode
        ):
            raise TypeError("terminal board and code must be exact")
        _utc(self.observed_at, "observed_at")
        _count(self.declared_member_count, "declared_member_count")
        _fingerprint(self.terminal_fingerprint, "terminal_fingerprint")
        fingerprint = _digest(_terminal_projection(self))
        if self.terminal_fingerprint != fingerprint:
            raise ValueError("HKEX source terminal fingerprint drift")

    @classmethod
    def complete(
        cls,
        *,
        source_id: str,
        board: HKEXPublisherBoard,
        observed_at: str,
        declared_member_count: int,
    ) -> HKEXSourceTerminal:
        """Create a complete terminal bound to the checked-in role version."""
        if source_id not in HKEX_REGULATORY_SOURCE_IDS:
            raise ValueError("HKEX source terminal has unknown source")
        return cls.create(
            source_id=source_id,
            source_profile_version=_profile(source_id).version,
            board=board,
            observed_at=observed_at,
            terminal_code=HKEXTerminalCode.COMPLETE,
            declared_member_count=declared_member_count,
        )

    @classmethod
    def create(cls, *values: object, **fields: object) -> HKEXSourceTerminal:
        """Issue one displayed terminal fingerprint from exact source facts."""
        fields = _factory_fields(values, fields, _TERMINAL_FIELD_NAMES, "terminal")
        source_id = _text_value(fields["source_id"], "source_id")
        source_profile_version = _text_value(
            fields["source_profile_version"], "source_profile_version"
        )
        observed_at = _text_value(fields["observed_at"], "observed_at")
        declared_member_count = fields["declared_member_count"]
        board = fields["board"]
        terminal_code = fields["terminal_code"]
        if type(board) is not HKEXPublisherBoard or type(terminal_code) is not HKEXTerminalCode:
            raise TypeError("terminal board and code must be exact")
        _count(declared_member_count, "declared_member_count")
        if type(declared_member_count) is not int:
            raise TypeError("declared_member_count must be exact")
        fingerprint = _digest(
            {
                "source_id": source_id,
                "source_profile_version": source_profile_version,
                "board": board.value,
                "observed_at": observed_at,
                "terminal_code": terminal_code.value,
                "declared_member_count": declared_member_count,
            }
        )
        return cls(
            source_id,
            source_profile_version,
            board,
            observed_at,
            terminal_code,
            declared_member_count,
            fingerprint,
        )


@dataclass(frozen=True, slots=True)
class HKEXObservedSourceEntry:
    """One preserved publisher observation without a legal identity claim."""

    observation_id: str
    source_id: str
    board: HKEXPublisherBoard
    product_identity: str
    source_object_kind: HKEXSourceObjectKind
    official_locator: str
    artifact_fingerprint: str
    source_order: int
    parent_observation_id: str | None
    declared_child_count: int
    entry_fingerprint: str

    def __post_init__(self) -> None:
        _identity(self.observation_id, "observation_id")
        _text(self.source_id, "source_id")
        if self.source_id not in HKEX_REGULATORY_SOURCE_IDS:
            raise ValueError("source entry has unknown source")
        if (
            type(self.board) is not HKEXPublisherBoard
            or type(self.source_object_kind) is not HKEXSourceObjectKind
        ):
            raise TypeError("source entry board and kind must be exact")
        _identity(self.product_identity, "product_identity")
        _locator(self.official_locator)
        _fingerprint(self.artifact_fingerprint, "artifact_fingerprint")
        if type(self.source_order) is not int or not 1 <= self.source_order <= _MAX_ENTRIES:
            raise ValueError("source_order is out of bounds")
        if self.parent_observation_id is not None:
            _identity(self.parent_observation_id, "parent_observation_id")
            if self.parent_observation_id == self.observation_id:
                raise ValueError("source-entry self-parent is forbidden")
        _count(self.declared_child_count, "declared_child_count")
        _fingerprint(self.entry_fingerprint, "entry_fingerprint")
        fingerprint = _digest(_entry_projection(self))
        if self.entry_fingerprint != fingerprint:
            raise ValueError("HKEX source entry fingerprint drift")

    @classmethod
    def create(cls, *values: object, **fields: object) -> HKEXObservedSourceEntry:
        """Issue one displayed entry fingerprint from exact source facts."""
        fields = _factory_fields(values, fields, _ENTRY_FIELD_NAMES, "entry")
        observation_id = _text_value(fields["observation_id"], "observation_id")
        source_id = _text_value(fields["source_id"], "source_id")
        product_identity = _text_value(fields["product_identity"], "product_identity")
        official_locator = _text_value(fields["official_locator"], "official_locator")
        artifact_fingerprint = _text_value(fields["artifact_fingerprint"], "artifact_fingerprint")
        source_order = fields["source_order"]
        parent_observation_id = fields["parent_observation_id"]
        declared_child_count = fields["declared_child_count"]
        board = fields["board"]
        source_object_kind = fields["source_object_kind"]
        if (
            type(board) is not HKEXPublisherBoard
            or type(source_object_kind) is not HKEXSourceObjectKind
        ):
            raise TypeError("source entry board and kind must be exact")
        if parent_observation_id is not None and type(parent_observation_id) is not str:
            raise TypeError("parent_observation_id must be exact")
        _count(source_order, "source_order")
        _count(declared_child_count, "declared_child_count")
        if type(source_order) is not int or type(declared_child_count) is not int:
            raise TypeError("source entry counts must be exact integers")
        fingerprint = _digest(
            {
                "observation_id": observation_id,
                "source_id": source_id,
                "board": board.value,
                "product_identity": product_identity,
                "source_object_kind": source_object_kind.value,
                "official_locator": official_locator,
                "artifact_fingerprint": artifact_fingerprint,
                "source_order": source_order,
                "parent_observation_id": parent_observation_id,
                "declared_child_count": declared_child_count,
            }
        )
        return cls(
            observation_id,
            source_id,
            board,
            product_identity,
            source_object_kind,
            official_locator,
            artifact_fingerprint,
            source_order,
            parent_observation_id,
            declared_child_count,
            fingerprint,
        )


@dataclass(frozen=True, slots=True)
class HKEXRoleBoardAccounting:
    """Exact terminal and observed-member accounting for one board pair."""

    source_id: str
    board: HKEXPublisherBoard
    terminal_fingerprint: str
    declared_member_count: int
    observation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.source_id, "source_id")
        if (
            self.source_id not in HKEX_REGULATORY_SOURCE_IDS
            or type(self.board) is not HKEXPublisherBoard
        ):
            raise ValueError("invalid role-board accounting")
        _fingerprint(self.terminal_fingerprint, "terminal_fingerprint")
        _count(self.declared_member_count, "declared_member_count")
        _canonical_identity_tuple(self.observation_ids, "observation_ids")
        if len(self.observation_ids) != self.declared_member_count:
            raise ValueError("accounting count does not match member identities")


@dataclass(frozen=True, slots=True)
class HKEXSourceInventory:
    """Self-reproducing all-role/all-board publisher observation inventory."""

    observation_cutoff: str
    register_version: str
    register_fingerprint: str
    terminals: tuple[HKEXSourceTerminal, ...]
    entries: tuple[HKEXObservedSourceEntry, ...]
    role_board_accounting: tuple[HKEXRoleBoardAccounting, ...]
    inventory_fingerprint: str

    def __post_init__(self) -> None:
        _utc(self.observation_cutoff, "observation_cutoff")
        _text(self.register_version, "register_version")
        _fingerprint(self.register_fingerprint, "register_fingerprint")
        _fingerprint(self.inventory_fingerprint, "inventory_fingerprint")
        _validate_inventory(self)
        if self.inventory_fingerprint != _digest(_inventory_projection(self)):
            raise ValueError("HKEX source inventory fingerprint drift")

    @property
    def complete(self) -> bool:
        """True only when every exact source-role/board terminal completed."""
        validate_hkex_source_inventory(self)
        return all(item.terminal_code is HKEXTerminalCode.COMPLETE for item in self.terminals)


@dataclass(frozen=True, slots=True)
class _InventoryPayload:
    """Private projection inputs used before a public inventory is issued."""

    observation_cutoff: str
    register_version: str
    register_fingerprint: str
    terminals: tuple[HKEXSourceTerminal, ...]
    entries: tuple[HKEXObservedSourceEntry, ...]
    accounting: tuple[HKEXRoleBoardAccounting, ...]


def load_hk_regulatory_source_register(path: Path | None = None) -> HKEXSourceRegister:
    """Load the strict local-only five-role source register."""
    raw = (path or Path(__file__).with_name("hk_regulatory_source_register.json")).read_bytes()
    document = _object(parse_json_bytes(raw, max_bytes=_MAX_REGISTER_BYTES), "source register")
    if _text(document.get("fingerprint"), "fingerprint") != _register_fingerprint(document):
        raise ValueError("HKEX source register fingerprint does not match canonical content")
    _exact_keys(
        document,
        frozenset(
            {
                "schema_id",
                "schema_version",
                "register_id",
                "register_version",
                "effective_date",
                "status",
                "fingerprint",
                "access_boundary",
                "sources",
                "endpoints",
            }
        ),
        "source register",
    )
    boundary = _object(document["access_boundary"], "access boundary")
    _exact_keys(boundary, frozenset({"state", "forbidden_effects"}), "access boundary")
    return HKEXSourceRegister(
        _text(document["schema_id"], "schema_id"),
        _text(document["schema_version"], "schema_version"),
        _text(document["register_id"], "register_id"),
        _text(document["register_version"], "register_version"),
        _text(document["effective_date"], "effective_date"),
        _text(document["status"], "status"),
        _text(document["fingerprint"], "fingerprint"),
        HKEXSourceAccessBoundary(
            _text(boundary["state"], "state"),
            _strings(boundary["forbidden_effects"], "forbidden_effects", 1),
        ),
        tuple(
            _parse_source(_object(item, "source"))
            for item in _array(document["sources"], "sources")
        ),
        tuple(
            _parse_endpoint(_object(item, "endpoint"))
            for item in _array(document["endpoints"], "endpoints")
        ),
    )


def build_hkex_source_inventory(
    *,
    observation_cutoff: str,
    terminals: tuple[HKEXSourceTerminal, ...],
    entries: tuple[HKEXObservedSourceEntry, ...],
) -> HKEXSourceInventory:
    """Reconcile source facts, all five roles and both boards, without legal analysis."""
    register = load_hk_regulatory_source_register()
    accounting = _build_accounting(register, observation_cutoff, terminals, entries)
    payload = _InventoryPayload(
        observation_cutoff,
        register.register_version,
        register.fingerprint,
        terminals,
        entries,
        accounting,
    )
    fingerprint = _inventory_fingerprint(payload)
    return HKEXSourceInventory(
        observation_cutoff,
        register.register_version,
        register.fingerprint,
        terminals,
        entries,
        accounting,
        fingerprint,
    )


def validate_hkex_source_inventory(inventory: HKEXSourceInventory) -> None:
    """Replay the complete aggregate before any caller consumes a success claim."""
    if type(inventory) is not HKEXSourceInventory:
        raise TypeError("HKEX source inventory must be exact")
    _utc(inventory.observation_cutoff, "observation_cutoff")
    _text(inventory.register_version, "register_version")
    _fingerprint(inventory.register_fingerprint, "register_fingerprint")
    _fingerprint(inventory.inventory_fingerprint, "inventory_fingerprint")
    _validate_inventory(inventory)
    if inventory.inventory_fingerprint != _digest(_inventory_projection(inventory)):
        raise ValueError("HKEX source inventory fingerprint drift")


def _build_accounting(
    register: HKEXSourceRegister,
    observation_cutoff: str,
    terminals: tuple[HKEXSourceTerminal, ...],
    entries: tuple[HKEXObservedSourceEntry, ...],
) -> tuple[HKEXRoleBoardAccounting, ...]:
    if type(terminals) is not tuple or type(entries) is not tuple:
        raise TypeError("terminals and entries must be exact tuples")
    if any(type(item) is not HKEXSourceTerminal for item in terminals):
        raise TypeError("terminal must be exact")
    if any(type(item) is not HKEXObservedSourceEntry for item in entries):
        raise TypeError("entry must be exact")
    for terminal in terminals:
        terminal.__post_init__()
    for entry in entries:
        entry.__post_init__()
    cutoff = _utc(observation_cutoff, "observation_cutoff")
    expected = tuple(
        (source_id, board)
        for source_id in HKEX_REGULATORY_SOURCE_IDS
        for board in HKEXPublisherBoard
    )
    if tuple((item.source_id, item.board) for item in terminals) != expected:
        raise ValueError("HKEX_SOURCE_INVENTORY_INCOMPLETE")
    profiles = {item.source_id: item for item in register.sources}
    result: list[HKEXRoleBoardAccounting] = []
    for terminal in terminals:
        if terminal.observed_at > cutoff:
            raise ValueError("HKEX source terminal is after inventory cutoff")
        if terminal.source_profile_version != profiles[terminal.source_id].version:
            raise ValueError("HKEX source terminal profile drift")
        members = tuple(
            item
            for item in entries
            if (item.source_id, item.board) == (terminal.source_id, terminal.board)
        )
        if terminal.terminal_code is not HKEXTerminalCode.COMPLETE and members:
            raise ValueError("incomplete terminal cannot claim member accounting")
        result.append(
            HKEXRoleBoardAccounting(
                terminal.source_id,
                terminal.board,
                terminal.terminal_fingerprint,
                terminal.declared_member_count,
                tuple(sorted(item.observation_id for item in members)),
            )
        )
    return tuple(result)


def _validate_inventory(inventory: HKEXSourceInventory) -> None:
    if (
        type(inventory.terminals) is not tuple
        or type(inventory.entries) is not tuple
        or type(inventory.role_board_accounting) is not tuple
    ):
        raise TypeError("HKEX source inventory collections must be exact tuples")
    if any(type(item) is not HKEXRoleBoardAccounting for item in inventory.role_board_accounting):
        raise TypeError("HKEX source accounting must be exact")
    for accounting in inventory.role_board_accounting:
        accounting.__post_init__()
    register = load_hk_regulatory_source_register()
    if (inventory.register_version, inventory.register_fingerprint) != (
        register.register_version,
        register.fingerprint,
    ):
        raise ValueError("HKEX source inventory register provenance drift")
    expected = _build_accounting(
        register,
        inventory.observation_cutoff,
        inventory.terminals,
        inventory.entries,
    )
    if inventory.role_board_accounting != expected:
        raise ValueError("HKEX source inventory accounting drift")
    _validate_entries(inventory.entries)


def _validate_entries(entries: tuple[HKEXObservedSourceEntry, ...]) -> None:
    if (
        type(entries) is not tuple
        or len(entries) > _MAX_ENTRIES
        or any(type(item) is not HKEXObservedSourceEntry for item in entries)
    ):
        raise TypeError("entries must be bounded exact source observations")
    for entry in entries:
        entry.__post_init__()
    keys = tuple(
        (item.source_id, item.board.value, item.source_order, item.observation_id)
        for item in entries
    )
    orders = tuple((item.source_id, item.board, item.source_order) for item in entries)
    if (
        keys != tuple(sorted(keys))
        or len({item.observation_id for item in entries}) != len(entries)
        or len(orders) != len(set(orders))
    ):
        raise ValueError("source entries must be canonical unique observations")
    by_id = {item.observation_id: item for item in entries}
    child_counts = {item.observation_id: 0 for item in entries}
    for item in entries:
        if item.parent_observation_id is not None:
            parent = by_id.get(item.parent_observation_id)
            if parent is None or (parent.source_id, parent.board) != (item.source_id, item.board):
                raise ValueError("source-entry parent provenance is invalid")
            child_counts[parent.observation_id] += 1
            _acyclic(item, by_id)
    if any(item.declared_child_count != child_counts[item.observation_id] for item in entries):
        raise ValueError("source-entry declared child totals drifted")


def _acyclic(entry: HKEXObservedSourceEntry, by_id: Mapping[str, HKEXObservedSourceEntry]) -> None:
    current = entry
    seen: set[str] = set()
    for _ in range(_MAX_DEPTH):
        parent_id = current.parent_observation_id
        if parent_id is None:
            return
        if parent_id in seen:
            raise ValueError("source-entry parent cycle is forbidden")
        seen.add(parent_id)
        current = by_id[parent_id]
    raise ValueError("source-entry relationship depth is out of bounds")


def _parse_source(document: dict[str, JsonValue]) -> HKEXSourceProfile:
    _exact_keys(
        document,
        frozenset(
            {
                "source_id",
                "registered_source_id",
                "version",
                "source_policy_owner",
                "endpoint_ids",
                "rights_state",
                "operational_state",
                "outage_consequence",
                "fact_authority",
                "completeness_authority",
                "blockers",
            }
        ),
        "source",
    )
    return HKEXSourceProfile(
        _text(document["source_id"], "source_id"),
        _text(document["registered_source_id"], "registered_source_id"),
        _text(document["version"], "version"),
        _text(document["source_policy_owner"], "source_policy_owner"),
        _strings(document["endpoint_ids"], "endpoint_ids", 0),
        PublisherRightsState(_text(document["rights_state"], "rights_state")),
        OfficialSourceState(_text(document["operational_state"], "operational_state")),
        _text(document["outage_consequence"], "outage_consequence"),
        _text(document["fact_authority"], "fact_authority"),
        _text(document["completeness_authority"], "completeness_authority"),
        _strings(document["blockers"], "blockers", 1),
    )


def _parse_endpoint(document: dict[str, JsonValue]) -> OfficialEndpointContract:
    _exact_keys(
        document,
        frozenset(
            {
                "endpoint_id",
                "source_id",
                "version",
                "name",
                "url",
                "access_mode",
                "methods",
                "media_types",
                "max_bytes",
                "complete_inventory_required",
                "signal_use",
                "proves_no_change",
                "evidence_role",
                "enabled",
            }
        ),
        "endpoint",
    )
    return OfficialEndpointContract(
        _text(document["endpoint_id"], "endpoint_id"),
        _text(document["source_id"], "source_id"),
        _text(document["version"], "version"),
        _text(document["name"], "name"),
        _text(document["url"], "url"),
        EndpointAccessMode(_text(document["access_mode"], "access_mode")),
        tuple(HttpMethod(_text(item, "method")) for item in _array(document["methods"], "methods")),
        _strings(document["media_types"], "media_types", 1),
        _positive_integer(document["max_bytes"], "max_bytes"),
        _boolean(document["complete_inventory_required"], "complete_inventory_required"),
        SignalUse(_text(document["signal_use"], "signal_use")),
        _boolean(document["proves_no_change"], "proves_no_change"),
        _text(document["evidence_role"], "evidence_role"),
        _boolean(document["enabled"], "enabled"),
    )


def _profile(source_id: str) -> HKEXSourceProfile:
    return next(
        item for item in load_hk_regulatory_source_register().sources if item.source_id == source_id
    )


def _validate_source_profile(profile: HKEXSourceProfile) -> None:
    """Validate every public role-policy fact without relying on an enclosing register."""
    _text(profile.source_id, "source_id")
    if profile.source_id not in HKEX_REGULATORY_SOURCE_IDS:
        raise ValueError("unknown HKEX source role")
    exact_identifier(profile.registered_source_id, "registered_source_id", "src")
    _text(profile.version, "version")
    _text(profile.source_policy_owner, "source_policy_owner")
    if type(profile.endpoint_ids) is not tuple or not profile.endpoint_ids:
        raise ValueError("HKEX source profiles require exact endpoint bindings")
    if type(profile.rights_state) is not PublisherRightsState:
        raise TypeError("rights_state must be exact")
    if type(profile.operational_state) is not OfficialSourceState:
        raise TypeError("operational_state must be exact")
    _text(profile.outage_consequence, "outage_consequence")
    _text(profile.fact_authority, "fact_authority")
    _text(profile.completeness_authority, "completeness_authority")
    _canonical_text_tuple(profile.blockers, "blockers", minimum=1)
    if profile.rights_state is not PublisherRightsState.USER_ATTESTED_PERMISSION_DOCUMENT_PENDING:
        raise ValueError("HKEX publisher authority provenance drift")
    if profile.operational_state is not OfficialSourceState.PARTIALLY_CONFIGURED:
        raise ValueError("HKEX sources must remain visibly partial")
    if (
        profile.registered_source_id,
        profile.version,
        profile.source_policy_owner,
    ) != _EXPECTED_SOURCE_PROFILES[profile.source_id][:3]:
        raise ValueError("HKEX source profile provenance drift")
    if profile.endpoint_ids != _EXPECTED_ENDPOINT_IDS[profile.source_id]:
        raise ValueError("HKEX source endpoint binding drift")
    if profile.blockers != (
        "COMPLETE_COMPONENT_ENUMERATOR_REQUIRED",
        "PERMISSION_DOCUMENT_PENDING",
    ):
        raise ValueError("HKEX source profile provenance drift")
    if (
        profile.fact_authority,
        profile.completeness_authority,
        profile.outage_consequence,
    ) != _EXPECTED_SOURCE_FACTS[profile.source_id]:
        raise ValueError("HKEX source authority drift is forbidden")


def _terminal_projection(item: HKEXSourceTerminal) -> dict[str, object]:
    return {
        "source_id": item.source_id,
        "source_profile_version": item.source_profile_version,
        "board": item.board.value,
        "observed_at": item.observed_at,
        "terminal_code": item.terminal_code.value,
        "declared_member_count": item.declared_member_count,
    }


def _entry_projection(item: HKEXObservedSourceEntry) -> dict[str, object]:
    return {
        "observation_id": item.observation_id,
        "source_id": item.source_id,
        "board": item.board.value,
        "product_identity": item.product_identity,
        "source_object_kind": item.source_object_kind.value,
        "official_locator": item.official_locator,
        "artifact_fingerprint": item.artifact_fingerprint,
        "source_order": item.source_order,
        "parent_observation_id": item.parent_observation_id,
        "declared_child_count": item.declared_child_count,
    }


def _inventory_projection(item: HKEXSourceInventory) -> dict[str, object]:
    return _inventory_projection_from_payload(
        _InventoryPayload(
            item.observation_cutoff,
            item.register_version,
            item.register_fingerprint,
            item.terminals,
            item.entries,
            item.role_board_accounting,
        )
    )


def _inventory_fingerprint(payload: _InventoryPayload) -> str:
    return _digest(_inventory_projection_from_payload(payload))


def _inventory_projection_from_payload(payload: _InventoryPayload) -> dict[str, object]:
    return {
        "observation_cutoff": payload.observation_cutoff,
        "register_version": payload.register_version,
        "register_fingerprint": payload.register_fingerprint,
        "terminals": [
            _terminal_projection(value) | {"terminal_fingerprint": value.terminal_fingerprint}
            for value in payload.terminals
        ],
        "entries": [
            _entry_projection(value) | {"entry_fingerprint": value.entry_fingerprint}
            for value in payload.entries
        ],
        "role_board_accounting": [
            {
                "source_id": value.source_id,
                "board": value.board.value,
                "terminal_fingerprint": value.terminal_fingerprint,
                "declared_member_count": value.declared_member_count,
                "observation_ids": list(value.observation_ids),
            }
            for value in payload.accounting
        ],
    }


def _register_fingerprint(document: dict[str, JsonValue]) -> str:
    projection = dict(document)
    projection.pop("fingerprint", None)
    return _digest(projection)


def _register_fingerprint_from_register(register: HKEXSourceRegister) -> str:
    return _digest(
        {
            "schema_id": register.schema_id,
            "schema_version": register.schema_version,
            "register_id": register.register_id,
            "register_version": register.register_version,
            "effective_date": register.effective_date,
            "status": register.status,
            "access_boundary": {
                "state": register.access_boundary.state,
                "forbidden_effects": list(register.access_boundary.forbidden_effects),
            },
            "sources": [
                {
                    "source_id": source.source_id,
                    "registered_source_id": source.registered_source_id,
                    "version": source.version,
                    "source_policy_owner": source.source_policy_owner,
                    "endpoint_ids": list(source.endpoint_ids),
                    "rights_state": source.rights_state.value,
                    "operational_state": source.operational_state.value,
                    "outage_consequence": source.outage_consequence,
                    "fact_authority": source.fact_authority,
                    "completeness_authority": source.completeness_authority,
                    "blockers": list(source.blockers),
                }
                for source in register.sources
            ],
            "endpoints": [
                {
                    "endpoint_id": endpoint.endpoint_id,
                    "source_id": endpoint.source_id,
                    "version": endpoint.version,
                    "name": endpoint.name,
                    "url": endpoint.url,
                    "access_mode": endpoint.access_mode.value,
                    "methods": [method.value for method in endpoint.methods],
                    "media_types": list(endpoint.media_types),
                    "max_bytes": endpoint.max_bytes,
                    "complete_inventory_required": endpoint.complete_inventory_required,
                    "signal_use": endpoint.signal_use.value,
                    "proves_no_change": endpoint.proves_no_change,
                    "evidence_role": endpoint.evidence_role,
                    "enabled": endpoint.enabled,
                }
                for endpoint in register.endpoints
            ],
        }
    )


def _digest(value: object) -> str:
    return f"sha256:{sha256(canonicalize(checked_json_value(value))).hexdigest()}"


def _object(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact object")
    return value


def _factory_fields(
    values: tuple[object, ...], fields: dict[str, object], names: tuple[str, ...], label: str
) -> dict[str, object]:
    if values:
        if fields or len(values) != len(names):
            raise TypeError(f"{label} factory has invalid arguments")
        return dict(zip(names, values, strict=True))
    _exact_field_names(fields, frozenset(names), label)
    return fields


def _exact_field_names(fields: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    if frozenset(fields) != expected:
        raise TypeError(f"{label} has unknown or missing fields")


def _text_value(value: object, label: str) -> str:
    if type(value) is not str or not value or value.strip() != value or len(value) > _MAX_TEXT:
        raise TypeError(f"{label} must be a bounded exact string")
    return value


def _array(value: JsonValue, label: str) -> list[JsonValue]:
    if type(value) is not list:
        raise TypeError(f"{label} must be an exact array")
    return value


def _text(value: JsonValue, label: str) -> str:
    if type(value) is not str or not value or value.strip() != value or len(value) > _MAX_TEXT:
        raise TypeError(f"{label} must be a bounded exact string")
    return value


def _strings(value: JsonValue, label: str, minimum: int) -> tuple[str, ...]:
    values = tuple(_text(item, label) for item in _array(value, label))
    if len(values) < minimum or len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    return values


def _canonical_text_tuple(value: tuple[str, ...], label: str, *, minimum: int) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{label} must be exact tuple")
    values = tuple(_text(item, label) for item in value)
    if len(values) < minimum or values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be canonical")


def _canonical_identity_tuple(value: tuple[str, ...], label: str) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{label} must be exact tuple")
    values = tuple(_identity(item, label) for item in value)
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be canonical unique identities")


def _identity(value: JsonValue, label: str) -> str:
    result = _text(value, label)
    if _IDENTITY.fullmatch(result) is None:
        raise ValueError(f"{label} must be a stable identity")
    return result


def _fingerprint(value: JsonValue, label: str) -> str:
    result = _text(value, label)
    if _FINGERPRINT.fullmatch(result) is None:
        raise ValueError(f"{label} must be SHA-256")
    return result


def _count(value: object, label: str) -> None:
    if type(value) is not int or not 0 <= value <= _MAX_ENTRIES:
        raise ValueError(f"{label} is out of bounds")


def _positive_integer(value: JsonValue, label: str) -> int:
    if type(value) is not int or value < 1:
        raise TypeError(f"{label} must be a positive exact integer")
    return value


def _boolean(value: JsonValue, label: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{label} must be an exact boolean")
    return value


def _utc(value: JsonValue, label: str) -> str:
    result = _text(value, label)
    if _UTC.fullmatch(result) is None:
        raise ValueError(f"{label} must be canonical UTC")
    try:
        datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError(f"{label} must be real UTC") from error
    return result


def _locator(value: JsonValue) -> str:
    result = _text(value, "official_locator")
    _validate_locator_text(result)
    try:
        parsed = urlsplit(result)
        host = parsed.hostname
        port = parsed.port
    except UnicodeError, ValueError:
        raise ValueError("official_locator must be bounded HTTPS") from None
    if (
        len(result) > 4096
        or not result.startswith("https://")
        or parsed.scheme != "https"
        or not parsed.netloc
        or host is None
        or (port is not None and not 1 <= port <= 65_535)
        or port == 443
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not _is_canonical_locator_authority(parsed.netloc, host, port)
    ):
        raise ValueError("official_locator must be bounded HTTPS")
    return result


def _validate_locator_text(locator: str) -> None:
    """Reject ambiguous raw or percent-encoded text before URL parser normalisation."""
    if "#" in locator:
        raise ValueError("official_locator must be bounded HTTPS")
    for character in locator:
        category = unicodedata.category(character)
        if character == "\\" or character.isspace() or category.startswith(("C", "Z")):
            raise ValueError("official_locator must be bounded HTTPS")
    position = 0
    while position < len(locator):
        if locator[position] != "%":
            position += 1
            continue
        if position + 2 >= len(locator) or (
            locator[position + 1] not in _HEX or locator[position + 2] not in _HEX
        ):
            raise ValueError("official_locator must be bounded HTTPS")
        encoded_byte = int(locator[position + 1 : position + 3], 16)
        if encoded_byte <= 0x1F or encoded_byte == 0x7F or encoded_byte in _PERCENT_AMBIGUOUS_BYTES:
            raise ValueError("official_locator must be bounded HTTPS")
        position += 3
    try:
        decoded = unquote_to_bytes(locator).decode("utf-8")
    except UnicodeError:
        raise ValueError("official_locator must be bounded HTTPS") from None
    for character in decoded:
        category = unicodedata.category(character)
        if character == "\\" or character.isspace() or category.startswith(("C", "Z")):
            raise ValueError("official_locator must be bounded HTTPS")


def _is_canonical_locator_authority(authority: str, host: str, port: int | None) -> bool:
    """Accept one exact ASCII DNS, IPv4, or bracketed canonical IPv6 authority."""
    try:
        if ":" in host:
            canonical_host = str(IPv6Address(host))
            canonical_authority = f"[{canonical_host}]"
        elif _could_be_numeric_ipv4(host):
            canonical_host = str(IPv4Address(host))
            canonical_authority = canonical_host
        else:
            canonical_host = host.encode("idna").decode("ascii")
            if canonical_host != host or not _is_canonical_dns_host(canonical_host):
                return False
            canonical_authority = canonical_host
    except UnicodeError, ValueError:
        return False
    if port is not None:
        canonical_authority = f"{canonical_authority}:{port}"
    return authority == canonical_authority


def _is_canonical_dns_host(host: str) -> bool:
    """Validate lower-case ASCII DNS labels without aliases or empty labels."""
    labels = host.split(".")
    return (
        len(host) <= 253
        and host == host.lower()
        and len(labels) >= 2
        and all(labels)
        and labels[-1][0] in "abcdefghijklmnopqrstuvwxyz"
        and all(_is_canonical_dns_label(label) for label in labels)
    )


def _could_be_numeric_ipv4(host: str) -> bool:
    """Prevent browser-style alternate numeric authorities from falling into DNS."""
    return all(_NUMERIC_IP_LABEL.fullmatch(label) is not None for label in host.split("."))


def _is_canonical_dns_label(label: str) -> bool:
    """Validate only local ASCII LDH labels; Task 7 may admit pinned modern IDNA."""
    return _DNS_LABEL.fullmatch(label) is not None and not label.startswith("xn--")


def _exact_keys(document: Mapping[str, JsonValue], expected: frozenset[str], label: str) -> None:
    if frozenset(document) != expected:
        raise ValueError(f"{label} has unknown or missing fields")


_FORBIDDEN_EFFECTS = (
    "CORPUS_PUBLICATION",
    "DEPLOYMENT",
    "MODEL_OR_EMBEDDING_CALL",
    "PINECONE_MUTATION",
    "PRODUCTION_ROUTING",
)
_EXPECTED_REGISTER_FACTS = (
    "https://contracts.asklegal.local/v1/hk-regulatory-source-register.schema.json",
    "1.0.0",
    "hrr_000000000000000000000000000000000000000000000001",
    "2026-09-01.2",
    "2026-09-01",
    "AUTHORIZED_PARTIAL_FAIL_VISIBLE",
)
_EXPECTED_SOURCE_PROFILES = {
    "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS": (
        "src_000000000000000000000000000000000000000000000301",
        "1.0.0",
        "HK_REGULATORY_MATERIALS_LEGAL_DESK",
        (
            "EXACT_ENDPOINT_CONTRACT_REQUIRED",
            "PUBLISHER_RIGHTS_EVIDENCE_UNADMITTED",
            "SOURCE_ACCESS_AUTHORIZATION_UNADMITTED",
        ),
    ),
    "HK-REG-HKEX-FEES-RULES": (
        "src_000000000000000000000000000000000000000000000302",
        "2.0.0",
        "HK_REGULATORY_MATERIALS_LEGAL_DESK",
        (
            "EXACT_ENDPOINT_CONTRACT_REQUIRED",
            "PUBLISHER_RIGHTS_EVIDENCE_UNADMITTED",
            "SOURCE_ACCESS_AUTHORIZATION_UNADMITTED",
        ),
    ),
    "HK-REG-HKEX-REGULATORY-FORMS": (
        "src_000000000000000000000000000000000000000000000303",
        "2.0.0",
        "HK_REGULATORY_MATERIALS_LEGAL_DESK",
        (
            "EXACT_ENDPOINT_CONTRACT_REQUIRED",
            "PUBLISHER_RIGHTS_EVIDENCE_UNADMITTED",
            "SOURCE_ACCESS_AUTHORIZATION_UNADMITTED",
        ),
    ),
    "HK-REG-HKEX-RULE-UPDATES": (
        "src_000000000000000000000000000000000000000000000304",
        "2.0.0",
        "HK_REGULATORY_MATERIALS_LEGAL_DESK",
        (
            "EXACT_ENDPOINT_CONTRACT_REQUIRED",
            "PUBLISHER_RIGHTS_EVIDENCE_UNADMITTED",
            "SOURCE_ACCESS_AUTHORIZATION_UNADMITTED",
        ),
    ),
    "HK-REG-HKEX-RULEBOOK-CATALOGUE": (
        "src_000000000000000000000000000000000000000000000305",
        "1.0.0",
        "HK_REGULATORY_MATERIALS_LEGAL_DESK",
        (
            "EXACT_ENDPOINT_CONTRACT_REQUIRED",
            "PUBLISHER_RIGHTS_EVIDENCE_UNADMITTED",
            "SOURCE_ACCESS_AUTHORIZATION_UNADMITTED",
        ),
    ),
}
_EXPECTED_ENDPOINT_IDS = {
    "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS": (
        "sep_000000000000000000000000000000000000000000000301",
        "sep_000000000000000000000000000000000000000000000302",
        "sep_000000000000000000000000000000000000000000000310",
        "sep_000000000000000000000000000000000000000000000311",
        "sep_000000000000000000000000000000000000000000000312",
    ),
    "HK-REG-HKEX-FEES-RULES": (
        "sep_000000000000000000000000000000000000000000000303",
        "sep_000000000000000000000000000000000000000000000304",
        "sep_000000000000000000000000000000000000000000000314",
        "sep_000000000000000000000000000000000000000000000320",
    ),
    "HK-REG-HKEX-REGULATORY-FORMS": (
        "sep_000000000000000000000000000000000000000000000305",
        "sep_000000000000000000000000000000000000000000000306",
        "sep_000000000000000000000000000000000000000000000313",
        "sep_000000000000000000000000000000000000000000000319",
    ),
    "HK-REG-HKEX-RULE-UPDATES": (
        "sep_000000000000000000000000000000000000000000000307",
        "sep_000000000000000000000000000000000000000000000308",
        "sep_000000000000000000000000000000000000000000000315",
        "sep_000000000000000000000000000000000000000000000316",
        "sep_000000000000000000000000000000000000000000000317",
        "sep_000000000000000000000000000000000000000000000318",
    ),
    "HK-REG-HKEX-RULEBOOK-CATALOGUE": ("sep_000000000000000000000000000000000000000000000309",),
}
_EXPECTED_ENDPOINTS = {
    "sep_000000000000000000000000000000000000000000000301": (
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "https://en-rules.hkex.com.hk/rulebook/main-board-listing-rules",
    ),
    "sep_000000000000000000000000000000000000000000000302": (
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "https://en-rules.hkex.com.hk/rulebook/gem-listing-rules",
    ),
    "sep_000000000000000000000000000000000000000000000303": (
        "HK-REG-HKEX-FEES-RULES",
        "https://en-rules.hkex.com.hk/rulebook/main-board-fees-rules",
    ),
    "sep_000000000000000000000000000000000000000000000304": (
        "HK-REG-HKEX-FEES-RULES",
        "https://en-rules.hkex.com.hk/rulebook/gem-fees-rules",
    ),
    "sep_000000000000000000000000000000000000000000000305": (
        "HK-REG-HKEX-REGULATORY-FORMS",
        "https://en-rules.hkex.com.hk/rulebook/main-board-regulatory-forms",
    ),
    "sep_000000000000000000000000000000000000000000000306": (
        "HK-REG-HKEX-REGULATORY-FORMS",
        "https://en-rules.hkex.com.hk/rulebook/gem-regulatory-forms",
    ),
    "sep_000000000000000000000000000000000000000000000307": (
        "HK-REG-HKEX-RULE-UPDATES",
        "https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules",
    ),
    "sep_000000000000000000000000000000000000000000000308": (
        "HK-REG-HKEX-RULE-UPDATES",
        "https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules",
    ),
    "sep_000000000000000000000000000000000000000000000309": (
        "HK-REG-HKEX-RULEBOOK-CATALOGUE",
        "https://www.hkex.com.hk/Listing/Rules-and-Resources/Listing-Rules?sc_lang=en",
    ),
    "sep_000000000000000000000000000000000000000000000310": (
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "https://en-rules.hkex.com.hk/entiresection/1932",
    ),
    "sep_000000000000000000000000000000000000000000000311": (
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/consol_mb.pdf",
    ),
    "sep_000000000000000000000000000000000000000000000312": (
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/consol_gem.pdf",
    ),
    "sep_000000000000000000000000000000000000000000000313": (
        "HK-REG-HKEX-REGULATORY-FORMS",
        "https://en-rules.hkex.com.hk/entiresection/6190",
    ),
    "sep_000000000000000000000000000000000000000000000314": (
        "HK-REG-HKEX-FEES-RULES",
        "https://en-rules.hkex.com.hk/entiresection/3783",
    ),
    "sep_000000000000000000000000000000000000000000000315": (
        "HK-REG-HKEX-RULE-UPDATES",
        "https://en-rules.hkex.com.hk/entiresection/2",
    ),
    "sep_000000000000000000000000000000000000000000000316": (
        "HK-REG-HKEX-RULE-UPDATES",
        "https://en-rules.hkex.com.hk/entiresection/49",
    ),
    "sep_000000000000000000000000000000000000000000000317": (
        "HK-REG-HKEX-RULE-UPDATES",
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_154_Attachment.pdf",
    ),
    "sep_000000000000000000000000000000000000000000000318": (
        "HK-REG-HKEX-RULE-UPDATES",
        "https://en-rules.hkex.com.hk/sites/default/files/net_file_store/Update_87_Attachment.pdf",
    ),
    "sep_000000000000000000000000000000000000000000000319": (
        "HK-REG-HKEX-REGULATORY-FORMS",
        "https://en-rules.hkex.com.hk/entiresection/6191",
    ),
    "sep_000000000000000000000000000000000000000000000320": (
        "HK-REG-HKEX-FEES-RULES",
        "https://en-rules.hkex.com.hk/entiresection/1836",
    ),
}
_EXPECTED_SOURCE_FACTS = {
    "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS": (
        "PREVAILING_ENGLISH_WORDING_AND_CONTAINED_OFFICIAL_STRUCTURE",
        "ENUMERATE_EVERY_COMPONENT_NOT_ONLY_TABLE_OF_CONTENTS",
        "BOUNDED_BOARD_OR_UNBOUNDED_BOTH_SCOPE_BLOCKING",
    ),
    "HK-REG-HKEX-FEES-RULES": (
        "SEPARATE_FEES_RULE_MEMBERSHIP_OWNERSHIP_AND_ENGLISH_CONTENT",
        "ENUMERATE_EVERY_REQUIRED_ENGLISH_FEES_RULE_PER_BOARD",
        "BOUNDED_BOARD_OR_UNBOUNDED_BOTH_SCOPE_BLOCKING",
    ),
    "HK-REG-HKEX-REGULATORY-FORMS": (
        "SEPARATE_FORM_MEMBERSHIP_OWNERSHIP_AND_ENGLISH_CONTENT",
        "ENUMERATE_EVERY_REQUIRED_ENGLISH_REGULATORY_FORM_PER_BOARD",
        "BOUNDED_BOARD_OR_UNBOUNDED_BOTH_SCOPE_BLOCKING",
    ),
    "HK-REG-HKEX-RULE-UPDATES": (
        "FINAL_CHANGE_WORDING_TIMING_CONDITION_TRANSITION_AND_MAPPING_FACTS",
        "ENUMERATE_EVERY_DUE_FINAL_UPDATE_AND_LINKED_CLASSIFICATION_ARTIFACT",
        "AFFECTED_BOARD_FRESH_RELEASE_BLOCKING",
    ),
    "HK-REG-HKEX-RULEBOOK-CATALOGUE": (
        "TOP_LEVEL_PRODUCT_FAMILIES_BOARD_ASSOCIATION_AND_CURRENT_LOCATORS",
        "BOUNDS_FAMILIES_BUT_NEVER_PROVES_COMPONENT_WORDING_OR_LIST_ALONE",
        "UNBOUNDED_BOTH_SCOPE_RELEASE_BLOCKING",
    ),
}
