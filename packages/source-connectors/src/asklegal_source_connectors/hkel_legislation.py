"""Plan-before-fetch evidence contracts for one HKeL legal instrument.

The public HKeL inventory is source-wide, while the legal-processing boundary
needs one evidence bundle for one exact instrument.  This module deliberately
does not parse source bytes or fetch a URL.  It turns an already enumerated,
registered set of artifact identities into a frozen plan that an acquisition
activity can execute later through its bounded transport and immutable vault.
"""

from __future__ import annotations

import re
import weakref
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from html.parser import HTMLParser
from typing import TypeIs

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value

from .model import exact_text
from .official import (
    HongKongLegislationSourceRegister,
    OfficialEndpointContract,
    load_hk_legislation_source_register,
)
from .official_binding import bind_official_endpoint_locator
from .official_http import OfficialFetchCode, OfficialFetchResult
from .official_inventory import OfficialInventoryResult

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_INSTRUMENT_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,159}$")
_LANGUAGES = frozenset({"en", "zh-Hant"})
_UTC_CUTOFF = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_PUBLICATION_SPECIFICATION_ENDPOINTS = frozenset(
    {
        "sep_000000000000000000000000000000000000000000000036",
        "sep_000000000000000000000000000000000000000000000037",
        "sep_000000000000000000000000000000000000000000000038",
    }
)
_SYNTHETIC_CURRENT_INVENTORY_PROFILE = "asklegal.synthetic.hkel.current-inventory.v1"
_CURRENT_INVENTORY_LANGUAGE_ENDPOINTS = {
    "en": "sep_000000000000000000000000000000000000000000000002",
    "zh-Hant": "sep_000000000000000000000000000000000000000000000003",
}
_ARCHIVE_MEMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")
_MAX_INVENTORY_ITEMS = 100_000
_MAX_RESOURCES_PER_ITEM = 16
_ENDPOINT_ID = re.compile(r"^sep_[0-9a-f]{48}$")


class HkelInventoryProfile(StrEnum):
    """Known inventory byte profiles, each explicit about source admission."""

    SYNTHETIC_CANDIDATE_V1 = "SYNTHETIC_CANDIDATE_V1"


@dataclass(frozen=True, slots=True)
class HkelArchiveReuseKey:
    """Exact archive/spec tuple that permits reuse of one prior safe parse."""

    archive_endpoint_id: str
    archive_fingerprint: str
    publication_profile_fingerprint: str
    fingerprint: str

    @classmethod
    def issue(
        cls,
        archive_endpoint_id: object,
        archive_fingerprint: object,
        publication_profile_fingerprint: object,
    ) -> HkelArchiveReuseKey:
        """Issue one canonical key from exact source and publication identities."""
        if (
            type(archive_endpoint_id) is not str
            or _ENDPOINT_ID.fullmatch(archive_endpoint_id) is None
            or type(archive_fingerprint) is not str
            or _SHA256.fullmatch(archive_fingerprint) is None
            or type(publication_profile_fingerprint) is not str
            or _SHA256.fullmatch(publication_profile_fingerprint) is None
        ):
            raise ValueError("HKEL_ARCHIVE_REUSE_KEY_INVALID")
        body = {
            "archive_endpoint_id": archive_endpoint_id,
            "archive_fingerprint": archive_fingerprint,
            "publication_profile_fingerprint": publication_profile_fingerprint,
        }
        fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"
        return cls(
            archive_endpoint_id,
            archive_fingerprint,
            publication_profile_fingerprint,
            fingerprint,
        )


def select_hkel_archives_to_reparse(
    current: object,
    previous: object,
) -> tuple[HkelArchiveReuseKey, ...]:
    """Return only archives whose exact archive/spec key has not been proved before."""

    def exact_tuple(value: object) -> TypeIs[tuple[object, ...]]:
        return type(value) is tuple

    def validated(value: object) -> tuple[HkelArchiveReuseKey, ...]:
        if not exact_tuple(value):
            raise ValueError("HKEL_ARCHIVE_REUSE_KEYS_INVALID")
        rebuilt_values: list[HkelArchiveReuseKey] = []
        for item in value:
            if type(item) is not HkelArchiveReuseKey:
                raise ValueError("HKEL_ARCHIVE_REUSE_KEYS_INVALID")
            rebuilt_values.append(
                HkelArchiveReuseKey.issue(
                    item.archive_endpoint_id,
                    item.archive_fingerprint,
                    item.publication_profile_fingerprint,
                )
            )
        rebuilt = tuple(rebuilt_values)
        if len({item.archive_endpoint_id for item in rebuilt}) != len(rebuilt) or len(
            {item.fingerprint for item in rebuilt}
        ) != len(rebuilt):
            raise ValueError("HKEL_ARCHIVE_REUSE_KEYS_INVALID")
        return tuple(sorted(rebuilt, key=lambda item: item.archive_endpoint_id))

    exact_current = validated(current)
    prior_fingerprints = {item.fingerprint for item in validated(previous)}
    return tuple(item for item in exact_current if item.fingerprint not in prior_fingerprints)


@dataclass(slots=True)
class _CandidateInventoryElement:
    """Small inert tree for the closed synthetic inventory grammar only."""

    tag: str
    attrib: dict[str, str]
    children: list[_CandidateInventoryElement]


class _CandidateInventoryParser(HTMLParser):
    """Parse only inert start/end tags after declaration/entity rejection."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root: _CandidateInventoryElement | None = None
        self._stack: list[_CandidateInventoryElement] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if any(value is None for _, value in attrs):
            raise ValueError("candidate HKeL inventory attributes must have exact string values")
        element = _CandidateInventoryElement(
            tag,
            {name: value for name, value in attrs if value is not None},
            [],
        )
        if self.root is None:
            self.root = element
        elif not self._stack:
            raise ValueError("candidate HKeL inventory has multiple roots")
        else:
            self._stack[-1].children.append(element)
        self._stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack or self._stack[-1].tag != tag:
            raise ValueError("candidate HKeL inventory has mismatched tags")
        self._stack.pop()

    def handle_data(self, data: str) -> None:
        if data.strip():
            raise ValueError("candidate HKeL inventory cannot contain text nodes")

    def handle_comment(self, data: str) -> None:
        del data
        raise ValueError("candidate HKeL inventory cannot contain comments")

    def handle_decl(self, decl: str) -> None:
        del decl
        raise ValueError("candidate HKeL inventory cannot contain declarations")

    def complete(self) -> _CandidateInventoryElement:
        """Return exactly one closed root after all source bytes were consumed."""
        if self.root is None or self._stack:
            raise ValueError("candidate HKeL inventory is structurally incomplete")
        return self.root


@dataclass(frozen=True, slots=True)
class HkelInventoryResource:
    """One exact item resource projected from a captured inventory body."""

    item_id: str
    resource_id: str
    language: str
    version_signal: str
    status_signal: str
    locator: str
    declared_sha256: str
    archive_member: str
    endpoint_id: str
    endpoint_version: str
    copy_endpoint_id: str
    copy_endpoint_version: str
    copy_locator: str
    inventory_member_fingerprint: str

    def __post_init__(self) -> None:
        for field in (
            "item_id",
            "resource_id",
            "version_signal",
            "status_signal",
            "locator",
            "endpoint_id",
            "endpoint_version",
            "copy_endpoint_id",
            "copy_endpoint_version",
            "copy_locator",
            "inventory_member_fingerprint",
        ):
            exact_text(getattr(self, field), field)
        if _INSTRUMENT_ID.fullmatch(self.item_id) is None:
            raise ValueError("inventory item_id must be one bounded stable identifier")
        if self.language not in _LANGUAGES:
            raise ValueError("inventory resource language must be en or zh-Hant")
        if _SHA256.fullmatch(self.declared_sha256) is None:
            raise ValueError("inventory resource declared_sha256 must be exact SHA-256")
        if (
            _ARCHIVE_MEMBER.fullmatch(self.archive_member) is None
            or "//" in self.archive_member
            or "/../" in f"/{self.archive_member}/"
            or "\\" in self.archive_member
        ):
            raise ValueError("inventory resource archive_member is unsafe")
        if _SHA256.fullmatch(self.inventory_member_fingerprint) is None:
            raise ValueError("inventory member fingerprint must be exact SHA-256")


@dataclass(frozen=True, slots=True)
class HkelInventoryItem:
    """Paired current-inventory statements for one legal item/version."""

    item_id: str
    version_signal: str
    status_signal: str
    editorial_disposition: str
    resources: tuple[HkelInventoryResource, ...]

    def __post_init__(self) -> None:
        for field in ("item_id", "version_signal", "status_signal", "editorial_disposition"):
            exact_text(getattr(self, field), field)
        if _INSTRUMENT_ID.fullmatch(self.item_id) is None:
            raise ValueError("inventory item_id must be one bounded stable identifier")
        if self.editorial_disposition not in {"NOT_PUBLISHED", "PUBLISHED"}:
            raise ValueError(
                "editorial disposition must be source-proved PUBLISHED or NOT_PUBLISHED"
            )
        if (
            type(self.resources) is not tuple
            or len(self.resources) != 2
            or any(type(resource) is not HkelInventoryResource for resource in self.resources)
        ):
            raise TypeError("inventory item must have exactly two exact language resources")
        if frozenset(resource.language for resource in self.resources) != _LANGUAGES:
            raise ValueError("inventory item must have an English and Traditional Chinese resource")
        if any(resource.item_id != self.item_id for resource in self.resources):
            raise ValueError("inventory resource item identity drifted")
        if any(resource.version_signal != self.version_signal for resource in self.resources):
            raise ValueError("inventory resource version signal drifted")
        if any(resource.status_signal != self.status_signal for resource in self.resources):
            raise ValueError("inventory resource status signal drifted")


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HkelInventoryProjection:
    """Strict source-byte projection, deliberately not authentic format admission."""

    profile: HkelInventoryProfile
    authentic_source_admitted: bool
    source_inventory_fingerprint: str
    items: tuple[HkelInventoryItem, ...]
    projection_fingerprint: str = dataclass_field(init=False, default="", repr=False)

    def __post_init__(self) -> None:
        if self.profile is not HkelInventoryProfile.SYNTHETIC_CANDIDATE_V1:
            raise TypeError("inventory profile must be the exact candidate profile")
        if self.authentic_source_admitted is not False:
            raise ValueError("candidate HKeL profile cannot claim authentic source admission")
        if _SHA256.fullmatch(self.source_inventory_fingerprint) is None:
            raise ValueError("source inventory fingerprint must be exact SHA-256")
        if (
            type(self.items) is not tuple
            or not self.items
            or len(self.items) > _MAX_INVENTORY_ITEMS
            or any(type(item) is not HkelInventoryItem for item in self.items)
        ):
            raise TypeError("inventory projection must contain bounded exact items")
        if tuple(sorted(item.item_id for item in self.items)) != tuple(
            item.item_id for item in self.items
        ):
            raise ValueError("inventory items must be sorted by exact item identity")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("inventory item identities must be unique")
        for item in self.items:
            item.__post_init__()

    def assert_factory_issued(self) -> None:
        """Reject a public construction/replacement lacking captured-byte issuance."""
        try:
            self.__post_init__()
            snapshot = _projection_fingerprint(self)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "HKeL inventory projection is not factory-issued from captured bytes"
            ) from error
        _assert_issued_identity(
            self,
            snapshot=snapshot,
            displayed_fingerprint=self.projection_fingerprint,
            registry=_PROJECTION_ISSUANCE,
            label="HKeL inventory projection",
        )

    def item(self, item_id: str) -> HkelInventoryItem:
        """Return one exact source-derived item or reject an unlisted identity."""
        self.assert_factory_issued()
        exact_text(item_id, "item_id")
        for item in self.items:
            if item.item_id == item_id:
                return item
        raise ValueError("instrument is absent from the captured HKeL inventory")


class HkelEvidenceRole(StrEnum):
    """The six semantic evidence roles for one HKeL instrument."""

    ENGLISH_XML = "ENGLISH_XML"
    TRADITIONAL_CHINESE_XML = "TRADITIONAL_CHINESE_XML"
    XSD = "XSD"
    PUBLICATION_SPECIFICATION = "PUBLICATION_SPECIFICATION"
    OFFICIAL_COPY = "OFFICIAL_COPY"
    EDITORIAL_RECORD = "EDITORIAL_RECORD"


@dataclass(frozen=True, slots=True)
class HkelEvidenceArtifact:
    """One physical registered artifact selected from a complete item inventory."""

    artifact_id: str
    instrument_id: str
    role: HkelEvidenceRole
    source_id: str
    endpoint_id: str
    endpoint_version: str
    language: str | None
    locator: str | None
    resource_id: str | None = None
    version_signal: str | None = None
    status_signal: str | None = None
    declared_sha256: str | None = None
    archive_member: str | None = None
    inventory_member_fingerprint: str | None = None
    source_disposition: str | None = None

    def __post_init__(self) -> None:
        for field in (
            "artifact_id",
            "instrument_id",
            "source_id",
            "endpoint_id",
            "endpoint_version",
        ):
            exact_text(getattr(self, field), field)
        if _INSTRUMENT_ID.fullmatch(self.instrument_id) is None:
            raise ValueError("artifact instrument_id must be one bounded stable identifier")
        if type(self.role) is not HkelEvidenceRole:
            raise TypeError("role must be an exact HkelEvidenceRole")
        if self.language is not None and self.language not in _LANGUAGES:
            raise ValueError("language must be en, zh-Hant, or None")
        if self.locator is not None:
            exact_text(self.locator, "locator")
        for field in ("resource_id", "version_signal", "status_signal"):
            value = getattr(self, field)
            if value is not None:
                exact_text(value, field)
        if self.declared_sha256 is not None and _SHA256.fullmatch(self.declared_sha256) is None:
            raise ValueError("artifact declared_sha256 must be exact SHA-256 or None")
        if self.archive_member is not None and (
            _ARCHIVE_MEMBER.fullmatch(self.archive_member) is None
            or "//" in self.archive_member
            or "/../" in f"/{self.archive_member}/"
            or "\\" in self.archive_member
        ):
            raise ValueError("artifact archive_member is unsafe")
        if (
            self.inventory_member_fingerprint is not None
            and _SHA256.fullmatch(self.inventory_member_fingerprint) is None
        ):
            raise ValueError("artifact inventory member fingerprint must be exact SHA-256 or None")
        if self.role is HkelEvidenceRole.EDITORIAL_RECORD:
            if self.source_disposition not in {
                "NOT_PUBLISHED",
                "PROCEDURE_NOT_ADMITTED",
            }:
                raise ValueError("editorial record requires one exact source disposition")
        elif self.source_disposition is not None:
            raise ValueError("only editorial records may carry a source disposition")


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HkelEvidencePlan:
    """Immutable member set and exact omissions for one HKeL capture attempt."""

    instrument_id: str
    observation_cutoff: str
    source_register_id: str
    source_register_fingerprint: str
    inventory_fingerprint: str
    projection_fingerprint: str
    members: tuple[HkelEvidenceArtifact, ...]
    missing_member_ids: tuple[str, ...]
    release_blocking: bool
    plan_fingerprint: str
    authentic_source_admitted: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.instrument_id) is not str
            or _INSTRUMENT_ID.fullmatch(self.instrument_id) is None
        ):
            raise ValueError("instrument_id must be one bounded stable identifier")
        for field in (
            "observation_cutoff",
            "source_register_id",
            "source_register_fingerprint",
            "inventory_fingerprint",
            "projection_fingerprint",
            "plan_fingerprint",
        ):
            exact_text(getattr(self, field), field)
        _exact_utc_cutoff(self.observation_cutoff)
        if any(
            _SHA256.fullmatch(getattr(self, field)) is None
            for field in (
                "source_register_fingerprint",
                "inventory_fingerprint",
                "projection_fingerprint",
                "plan_fingerprint",
            )
        ):
            raise ValueError("plan fingerprints must be exact SHA-256 values")
        if type(self.members) is not tuple or any(
            type(item) is not HkelEvidenceArtifact for item in self.members
        ):
            raise TypeError("members must be an exact artifact tuple")
        for member in self.members:
            member.__post_init__()
        if any(member.instrument_id != self.instrument_id for member in self.members):
            raise ValueError("every member must bind the plan instrument identity")
        _validate_required_member_shape(self.members)
        if tuple(member.artifact_id for member in self.members) != tuple(
            sorted(member.artifact_id for member in self.members)
        ) or len({member.artifact_id for member in self.members}) != len(self.members):
            raise ValueError("members must be a non-empty sorted exact artifact set")
        if (
            type(self.missing_member_ids) is not tuple
            or self.missing_member_ids != tuple(sorted(self.missing_member_ids))
            or any(type(item) is not str or not item for item in self.missing_member_ids)
        ):
            raise TypeError("missing_member_ids must be sorted exact non-empty strings")
        if type(self.release_blocking) is not bool:
            raise TypeError("release_blocking must be exact bool")
        if self.authentic_source_admitted is not False:
            raise ValueError(
                "candidate HKeL evidence plans cannot claim authentic source admission"
            )
        expected_missing = tuple(
            sorted(
                f"{member.role.value}:PROCEDURE_NOT_ADMITTED"
                for member in self.members
                if member.source_disposition == "PROCEDURE_NOT_ADMITTED"
            )
        )
        if self.missing_member_ids != expected_missing:
            raise ValueError("missing members must derive from exact member dispositions")
        if self.release_blocking != bool(expected_missing):
            raise ValueError("release blocking must exactly reflect missing required members")
        if self.plan_fingerprint != _plan_fingerprint(self):
            raise ValueError("plan fingerprint does not reproduce its exact member snapshot")

    def assert_factory_issued(self) -> None:
        """Reject plans not issued from one verified frozen inventory projection."""
        try:
            self.__post_init__()
            snapshot = _plan_fingerprint(self)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "HKeL evidence plan is not factory-issued from a frozen projection"
            ) from error
        _assert_issued_identity(
            self,
            snapshot=snapshot,
            displayed_fingerprint=self.plan_fingerprint,
            registry=_PLAN_ISSUANCE,
            label="HKeL evidence plan",
        )


@dataclass(frozen=True, slots=True)
class _IssuedIdentity:
    """One private factory record bound to one live Python object identity."""

    reference: weakref.ReferenceType[object]
    snapshot: str


_PROJECTION_ISSUANCE: dict[int, _IssuedIdentity] = {}
_PLAN_ISSUANCE: dict[int, _IssuedIdentity] = {}


def _issue_identity(
    value: object,
    *,
    snapshot: str,
    registry: dict[int, _IssuedIdentity],
) -> None:
    """Record private weak provenance without placing a reusable token on value."""
    identity = id(value)

    def cleanup(reference: weakref.ReferenceType[object]) -> None:
        issued = registry.get(identity)
        if issued is not None and issued.reference is reference:
            del registry[identity]

    registry[identity] = _IssuedIdentity(weakref.ref(value, cleanup), snapshot)


def _assert_issued_identity(
    value: object,
    *,
    snapshot: str,
    displayed_fingerprint: str,
    registry: dict[int, _IssuedIdentity],
    label: str,
) -> None:
    """Require the live object, current snapshot, and displayed fingerprint to agree."""
    issued = registry.get(id(value))
    if (
        issued is None
        or issued.reference() is not value
        or issued.snapshot != snapshot
        or displayed_fingerprint != snapshot
    ):
        raise ValueError(f"{label} is not factory-issued from a frozen projection")


def _projection_fingerprint(projection: HkelInventoryProjection) -> str:
    """Hash only immutable primitive facts projected from captured inventory bytes."""
    body = {
        "authentic_source_admitted": projection.authentic_source_admitted,
        "items": [
            {
                "editorial_disposition": item.editorial_disposition,
                "item_id": item.item_id,
                "resources": [
                    {
                        "archive_member": resource.archive_member,
                        "copy_endpoint_id": resource.copy_endpoint_id,
                        "copy_endpoint_version": resource.copy_endpoint_version,
                        "copy_locator": resource.copy_locator,
                        "declared_sha256": resource.declared_sha256,
                        "endpoint_id": resource.endpoint_id,
                        "endpoint_version": resource.endpoint_version,
                        "inventory_member_fingerprint": resource.inventory_member_fingerprint,
                        "item_id": resource.item_id,
                        "language": resource.language,
                        "locator": resource.locator,
                        "resource_id": resource.resource_id,
                        "status_signal": resource.status_signal,
                        "version_signal": resource.version_signal,
                    }
                    for resource in item.resources
                ],
                "status_signal": item.status_signal,
                "version_signal": item.version_signal,
            }
            for item in projection.items
        ],
        "profile": projection.profile.value,
        "source_inventory_fingerprint": projection.source_inventory_fingerprint,
    }
    return f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"


def _issue_projection(projection: HkelInventoryProjection) -> HkelInventoryProjection:
    """Register private identity provenance after structural validation."""
    snapshot = _projection_fingerprint(projection)
    object.__setattr__(projection, "projection_fingerprint", snapshot)
    _issue_identity(projection, snapshot=snapshot, registry=_PROJECTION_ISSUANCE)
    projection.assert_factory_issued()
    return projection


def _validate_required_member_shape(members: tuple[HkelEvidenceArtifact, ...]) -> None:
    """Require every semantic role and exact language/disposition accounting."""
    by_role: dict[HkelEvidenceRole, list[HkelEvidenceArtifact]] = {
        role: [] for role in HkelEvidenceRole
    }
    for member in members:
        by_role[member.role].append(member)
    if set(by_role) != set(HkelEvidenceRole) or any(not values for values in by_role.values()):
        raise ValueError("members must account for all six semantic roles")
    if len(by_role[HkelEvidenceRole.ENGLISH_XML]) != 1 or {
        member.language for member in by_role[HkelEvidenceRole.ENGLISH_XML]
    } != {"en"}:
        raise ValueError("members must have exactly one English XML role")
    if len(by_role[HkelEvidenceRole.TRADITIONAL_CHINESE_XML]) != 1 or {
        member.language for member in by_role[HkelEvidenceRole.TRADITIONAL_CHINESE_XML]
    } != {"zh-Hant"}:
        raise ValueError("members must have exactly one Traditional Chinese XML role")
    if len(by_role[HkelEvidenceRole.XSD]) != 1:
        raise ValueError("members must have exactly one XSD role")
    if len(by_role[HkelEvidenceRole.PUBLICATION_SPECIFICATION]) != 4:
        raise ValueError("members must have the complete publication specification bundle")
    copy_members = by_role[HkelEvidenceRole.OFFICIAL_COPY]
    if (
        len(copy_members) != 2
        or not any(member.language == "en" for member in copy_members)
        or not any(member.language == "zh-Hant" for member in copy_members)
    ):
        raise ValueError("members must have both official-copy language roles")
    editorial = by_role[HkelEvidenceRole.EDITORIAL_RECORD]
    if len(editorial) != 1 or editorial[0].language is not None:
        raise ValueError("members must have exactly one editorial-record role")


def _plan_fingerprint_components(
    *,
    identity: tuple[str, str, str, str, str, str],
    members: tuple[HkelEvidenceArtifact, ...],
    missing_member_ids: tuple[str, ...],
    authentic_source_admitted: bool,
) -> str:
    """Reproduce the frozen plan fingerprint from its immutable primitive snapshot."""
    (
        instrument_id,
        observation_cutoff,
        source_register_id,
        source_register_fingerprint,
        inventory_fingerprint,
        projection_fingerprint,
    ) = identity
    body = {
        "authentic_source_admitted": authentic_source_admitted,
        "instrument_id": instrument_id,
        "inventory_fingerprint": inventory_fingerprint,
        "members": [_artifact_projection(member) for member in members],
        "missing_member_ids": list(missing_member_ids),
        "observation_cutoff": observation_cutoff,
        "projection_fingerprint": projection_fingerprint,
        "source_register_fingerprint": source_register_fingerprint,
        "source_register_id": source_register_id,
    }
    return f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"


def _plan_fingerprint(plan: HkelEvidencePlan) -> str:
    """Reproduce the fingerprint for one already constructed evidence plan."""
    return _plan_fingerprint_components(
        identity=(
            plan.instrument_id,
            plan.observation_cutoff,
            plan.source_register_id,
            plan.source_register_fingerprint,
            plan.inventory_fingerprint,
            plan.projection_fingerprint,
        ),
        members=plan.members,
        missing_member_ids=plan.missing_member_ids,
        authentic_source_admitted=plan.authentic_source_admitted,
    )


def _issue_plan(plan: HkelEvidencePlan) -> HkelEvidencePlan:
    """Register private identity provenance only after all plan checks pass."""
    _issue_identity(plan, snapshot=_plan_fingerprint(plan), registry=_PLAN_ISSUANCE)
    plan.assert_factory_issued()
    return plan


def _checked_in_hkel_register(
    register: HongKongLegislationSourceRegister | None,
) -> HongKongLegislationSourceRegister:
    """Reject a public register object whose facts drift from the checked-in register."""
    canonical_register = load_hk_legislation_source_register()
    exact_register = register or canonical_register
    if type(exact_register) is not HongKongLegislationSourceRegister:
        raise TypeError("register must be an exact HongKongLegislationSourceRegister")
    if exact_register != canonical_register:
        raise ValueError("HKeL planning requires the exact checked-in source register")
    return exact_register


def project_hkel_current_inventory(
    result: OfficialInventoryResult,
    *,
    register: HongKongLegislationSourceRegister | None = None,
) -> HkelInventoryProjection:
    """Parse a closed synthetic profile from the two retained inventory bodies.

    This is deliberately a *candidate* parser.  It proves only the declared
    synthetic fixture profile and its exact captured-byte provenance; Task 7
    must separately admit an authentic HKeL source profile before real source
    results can acquire any corresponding authority.
    """
    exact_register = _checked_in_hkel_register(register)
    _validate_source_inventory(result, exact_register)
    by_language: dict[str, dict[str, tuple[str, str, str, HkelInventoryResource]]] = {}
    for member in result.member_results:
        language = next(
            (
                name
                for name, endpoint_id in _CURRENT_INVENTORY_LANGUAGE_ENDPOINTS.items()
                if endpoint_id == member.endpoint_id
            ),
            None,
        )
        if language is None:
            raise ValueError("current inventory includes an unrecognised language member")
        if member.fingerprint != f"sha256:{sha256(member.body).hexdigest()}":
            raise ValueError(
                "captured inventory body fingerprint does not match the retained bytes"
            )
        by_language[language] = _parse_synthetic_current_inventory_member(
            member, language, exact_register
        )
    if frozenset(by_language) != _LANGUAGES:
        raise ValueError("current inventory must contain both authentic-language bodies")
    item_ids = set(by_language["en"]) | set(by_language["zh-Hant"])
    if set(by_language["en"]) != item_ids or set(by_language["zh-Hant"]) != item_ids:
        raise ValueError("current inventory language item sets do not match")
    paired: list[HkelInventoryItem] = []
    for item_id in sorted(item_ids):
        english_version, english_status, english_editorial, english_resource = by_language["en"][
            item_id
        ]
        chinese_version, chinese_status, chinese_editorial, chinese_resource = by_language[
            "zh-Hant"
        ][item_id]
        if (
            english_version != chinese_version
            or english_status != chinese_status
            or english_editorial != chinese_editorial
        ):
            raise ValueError("current inventory bilingual item metadata does not match")
        paired.append(
            HkelInventoryItem(
                item_id,
                english_version,
                english_status,
                english_editorial,
                (english_resource, chinese_resource),
            )
        )
    fingerprint = result.inventory_fingerprint
    if fingerprint is None:  # pragma: no cover - _validate_source_inventory guards this.
        raise AssertionError("complete source inventory fingerprint is absent")
    return _issue_projection(
        HkelInventoryProjection(
            profile=HkelInventoryProfile.SYNTHETIC_CANDIDATE_V1,
            authentic_source_admitted=False,
            source_inventory_fingerprint=fingerprint,
            items=tuple(paired),
        )
    )


def _parse_synthetic_current_inventory_member(
    member: OfficialFetchResult,
    language: str,
    register: HongKongLegislationSourceRegister,
) -> dict[str, tuple[str, str, str, HkelInventoryResource]]:
    """Parse one exact candidate language listing without inferring a real format."""
    if b"<!" in member.body or b"&" in member.body:
        raise ValueError("candidate HKeL inventory rejects declarations and entity references")
    try:
        text = member.body.decode("utf-8")
        parser = _CandidateInventoryParser()
        parser.feed(text)
        parser.close()
        root = parser.complete()
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("candidate HKeL inventory body is not well-formed XML") from error
    if root.tag != "hkel-inventory" or root.attrib != {
        "profile": _SYNTHETIC_CURRENT_INVENTORY_PROFILE,
        "language": language,
    }:
        raise ValueError("HKeL inventory body is not the closed synthetic candidate profile")
    items: dict[str, tuple[str, str, str, HkelInventoryResource]] = {}
    children = tuple(root.children)
    if not children or len(children) > _MAX_INVENTORY_ITEMS:
        raise ValueError("candidate HKeL inventory has an invalid item count")
    endpoints = {endpoint.endpoint_id: endpoint for endpoint in register.endpoints}
    for element in children:
        if element.tag != "item" or element.attrib.keys() != {
            "id",
            "version",
            "status",
            "editorial-disposition",
        }:
            raise ValueError("candidate HKeL inventory item has an unknown shape")
        item_id = element.attrib["id"]
        version = element.attrib["version"]
        status = element.attrib["status"]
        editorial = element.attrib["editorial-disposition"]
        if _INSTRUMENT_ID.fullmatch(item_id) is None or not version or not status:
            raise ValueError("candidate HKeL inventory item identity is invalid")
        resource_elements = tuple(element.children)
        if len(resource_elements) != 1 or len(resource_elements) > _MAX_RESOURCES_PER_ITEM:
            raise ValueError(
                "candidate HKeL inventory item must declare exactly one language resource"
            )
        resource = resource_elements[0]
        if resource.tag != "resource" or resource.attrib.keys() != {
            "id",
            "endpoint-id",
            "endpoint-version",
            "locator",
            "archive-member",
            "sha256",
            "copy-endpoint-id",
            "copy-endpoint-version",
            "copy-locator",
        }:
            raise ValueError("candidate HKeL inventory resource has an unknown shape")
        endpoint_id = resource.attrib["endpoint-id"]
        endpoint = endpoints.get(endpoint_id)
        if (
            endpoint is None
            or endpoint.source_id != "HK-LEG-HKEL-CURRENT-DATA"
            or endpoint.version != resource.attrib["endpoint-version"]
            or endpoint.evidence_role != "CURRENT_STRUCTURED_SOURCE"
            or not endpoint.url.endswith(f"_{language}.zip")
        ):
            raise ValueError(
                "candidate HKeL inventory resource lacks registered language authority"
            )
        copy_endpoint_id = resource.attrib["copy-endpoint-id"]
        copy_endpoint = endpoints.get(copy_endpoint_id)
        if (
            copy_endpoint is None
            or copy_endpoint.version != resource.attrib["copy-endpoint-version"]
            or copy_endpoint.source_id
            not in {"HK-LEG-HKEL-VERIFIED-COPIES", "HK-LEG-HKEL-ASSISTED-COPIES"}
            or copy_endpoint.evidence_role not in {"VERIFIED_COPY", "ASSISTED_COPY"}
        ):
            raise ValueError("candidate HKeL inventory copy lacks registered source authority")
        projected = HkelInventoryResource(
            item_id,
            resource.attrib["id"],
            language,
            version,
            status,
            resource.attrib["locator"],
            resource.attrib["sha256"],
            resource.attrib["archive-member"],
            endpoint_id,
            resource.attrib["endpoint-version"],
            copy_endpoint_id,
            resource.attrib["copy-endpoint-version"],
            resource.attrib["copy-locator"],
            member.fingerprint or "",
        )
        if item_id in items:
            raise ValueError("candidate HKeL inventory repeats one item identity")
        items[item_id] = (version, status, editorial, projected)
    return items


def build_hkel_evidence_plan_from_projection(
    projection: HkelInventoryProjection,
    *,
    instrument_id: str,
    cutoff: str,
    register: HongKongLegislationSourceRegister | None = None,
) -> HkelEvidencePlan:
    """Build an item plan solely from a byte-derived inventory projection.

    The candidate profile exposes only the structured bilingual resources.  It
    deliberately does not invent copy or Editorial locators from an item label;
    those absent source facts stay explicit blocking members until their own
    publisher inventory procedure is admitted.
    """
    if type(projection) is not HkelInventoryProjection:
        raise TypeError("projection must be an exact HkelInventoryProjection")
    projection.assert_factory_issued()
    exact_register = _checked_in_hkel_register(register)
    item = projection.item(instrument_id)
    endpoints = {endpoint.endpoint_id: endpoint for endpoint in exact_register.endpoints}
    xml_role = {
        "en": HkelEvidenceRole.ENGLISH_XML,
        "zh-Hant": HkelEvidenceRole.TRADITIONAL_CHINESE_XML,
    }
    members: list[HkelEvidenceArtifact] = [
        HkelEvidenceArtifact(
            artifact_id=f"{item.item_id}:{resource.resource_id}",
            instrument_id=item.item_id,
            role=xml_role[resource.language],
            source_id="HK-LEG-HKEL-CURRENT-DATA",
            endpoint_id=resource.endpoint_id,
            endpoint_version=resource.endpoint_version,
            language=resource.language,
            locator=None,
            resource_id=resource.resource_id,
            version_signal=resource.version_signal,
            status_signal=resource.status_signal,
            declared_sha256=resource.declared_sha256,
            archive_member=resource.archive_member,
            inventory_member_fingerprint=resource.inventory_member_fingerprint,
        )
        for resource in item.resources
    ]
    members.extend(
        HkelEvidenceArtifact(
            artifact_id=f"{item.item_id}:{resource.resource_id}:official-copy",
            instrument_id=item.item_id,
            role=HkelEvidenceRole.OFFICIAL_COPY,
            source_id=endpoints[resource.copy_endpoint_id].source_id,
            endpoint_id=resource.copy_endpoint_id,
            endpoint_version=resource.copy_endpoint_version,
            language=resource.language,
            locator=resource.copy_locator,
            resource_id=resource.resource_id,
            version_signal=resource.version_signal,
            status_signal=resource.status_signal,
            inventory_member_fingerprint=resource.inventory_member_fingerprint,
        )
        for resource in item.resources
    )
    editorial_endpoint = endpoints.get("sep_000000000000000000000000000000000000000000000033")
    if editorial_endpoint is None:
        raise ValueError("registered editorial-record procedure is absent")
    members.append(
        HkelEvidenceArtifact(
            artifact_id=f"{item.item_id}:editorial-record",
            instrument_id=item.item_id,
            role=HkelEvidenceRole.EDITORIAL_RECORD,
            source_id=editorial_endpoint.source_id,
            endpoint_id=editorial_endpoint.endpoint_id,
            endpoint_version=editorial_endpoint.version,
            language=None,
            locator=None,
            source_disposition=(
                "NOT_PUBLISHED"
                if item.editorial_disposition == "NOT_PUBLISHED"
                else "PROCEDURE_NOT_ADMITTED"
            ),
        )
    )
    for endpoint_id in (
        "sep_000000000000000000000000000000000000000000000035",
        *sorted(_PUBLICATION_SPECIFICATION_ENDPOINTS),
        "sep_000000000000000000000000000000000000000000000039",
    ):
        endpoint = endpoints.get(endpoint_id)
        if endpoint is None:
            raise ValueError("registered publication specification bundle is incomplete")
        role = (
            HkelEvidenceRole.XSD
            if endpoint_id.endswith("35")
            else HkelEvidenceRole.PUBLICATION_SPECIFICATION
        )
        members.append(
            HkelEvidenceArtifact(
                artifact_id=f"publication-specification:{endpoint_id}",
                instrument_id=item.item_id,
                role=role,
                source_id=endpoint.source_id,
                endpoint_id=endpoint.endpoint_id,
                endpoint_version=endpoint.version,
                language=None,
                locator=None,
            )
        )
    # Build directly from the source-byte projection rather than recreating a
    # public inventory result that could be populated with caller assertions.
    exact_cutoff = exact_text(cutoff, "cutoff")
    _exact_utc_cutoff(exact_cutoff)
    _validate_artifacts(tuple(members), endpoints)
    stable_members = tuple(sorted(members, key=lambda member: member.artifact_id))
    missing = tuple(
        sorted(
            f"{member.role.value}:PROCEDURE_NOT_ADMITTED"
            for member in stable_members
            if member.source_disposition == "PROCEDURE_NOT_ADMITTED"
        )
    )
    fingerprint = _plan_fingerprint_components(
        identity=(
            item.item_id,
            exact_cutoff,
            exact_register.register_id,
            exact_register.fingerprint,
            projection.source_inventory_fingerprint,
            projection.projection_fingerprint,
        ),
        members=stable_members,
        missing_member_ids=missing,
        authentic_source_admitted=False,
    )
    return _issue_plan(
        HkelEvidencePlan(
            instrument_id=item.item_id,
            observation_cutoff=exact_cutoff,
            source_register_id=exact_register.register_id,
            source_register_fingerprint=exact_register.fingerprint,
            inventory_fingerprint=projection.source_inventory_fingerprint,
            projection_fingerprint=projection.projection_fingerprint,
            members=stable_members,
            missing_member_ids=missing,
            release_blocking=bool(missing),
            plan_fingerprint=fingerprint,
            authentic_source_admitted=False,
        )
    )


def _artifact_projection(item: HkelEvidenceArtifact) -> dict[str, str | None]:
    """Return the self-reproducing provenance fields for one planned member."""
    return {
        "archive_member": item.archive_member,
        "artifact_id": item.artifact_id,
        "declared_sha256": item.declared_sha256,
        "endpoint_id": item.endpoint_id,
        "endpoint_version": item.endpoint_version,
        "inventory_member_fingerprint": item.inventory_member_fingerprint,
        "instrument_id": item.instrument_id,
        "language": item.language,
        "locator": item.locator,
        "resource_id": item.resource_id,
        "role": item.role.value,
        "source_disposition": item.source_disposition,
        "source_id": item.source_id,
        "status_signal": item.status_signal,
        "version_signal": item.version_signal,
    }


def _validate_artifacts(
    artifacts: tuple[HkelEvidenceArtifact, ...],
    endpoint_by_id: dict[str, OfficialEndpointContract],
) -> None:
    """Reject unregistered, cross-source, role-drifted, and duplicate members."""
    seen_member_keys: set[tuple[HkelEvidenceRole, str | None]] = set()
    seen_physical: set[tuple[str, str, str | None]] = set()
    for artifact in artifacts:
        endpoint = endpoint_by_id.get(artifact.endpoint_id)
        if endpoint is None:
            raise ValueError("artifact endpoint is not registered")
        endpoint_source = endpoint.source_id
        endpoint_version = endpoint.version
        if artifact.source_id != endpoint_source:
            raise ValueError("artifact registered source does not match endpoint")
        if artifact.endpoint_version != endpoint_version:
            raise ValueError("artifact endpoint version does not match register")
        placeholders = tuple(_PLACEHOLDER.findall(endpoint.url))
        if placeholders:
            if artifact.locator is None:
                raise ValueError("templated artifact endpoint requires one bounded locator")
            bind_official_endpoint_locator(
                endpoint,
                placeholder=placeholders[0],
                locator=artifact.locator,
            )
        elif artifact.locator is not None:
            raise ValueError("fixed artifact endpoint cannot accept an item locator")
        member_key = (artifact.role, artifact.language)
        if (
            artifact.role is not HkelEvidenceRole.PUBLICATION_SPECIFICATION
            and member_key in seen_member_keys
        ):
            raise ValueError("duplicate semantic artifact member")
        seen_member_keys.add(member_key)
        physical_key = (artifact.endpoint_id, artifact.endpoint_version, artifact.locator)
        if physical_key in seen_physical:
            raise ValueError("one physical artifact cannot satisfy two evidence members")
        seen_physical.add(physical_key)
        _validate_role_contract(artifact, endpoint_source, endpoint.evidence_role, endpoint.url)


def _validate_role_contract(
    artifact: HkelEvidenceArtifact,
    endpoint_source: str,
    endpoint_evidence_role: str,
    endpoint_url: str,
) -> None:
    if artifact.role is HkelEvidenceRole.ENGLISH_XML:
        if artifact.language != "en" or endpoint_source not in {
            "HK-LEG-HKEL-CURRENT-DATA",
            "HK-LEG-HKEL-PAST-DATA",
        }:
            raise ValueError("English XML member has an invalid registered contract")
        if endpoint_evidence_role != "CURRENT_STRUCTURED_SOURCE" or not endpoint_url.endswith(
            "_en.zip"
        ):
            raise ValueError("English XML endpoint has no exact language resource contract")
    elif artifact.role is HkelEvidenceRole.TRADITIONAL_CHINESE_XML:
        if artifact.language != "zh-Hant" or endpoint_source not in {
            "HK-LEG-HKEL-CURRENT-DATA",
            "HK-LEG-HKEL-PAST-DATA",
        }:
            raise ValueError("Traditional Chinese XML member has an invalid registered contract")
        if endpoint_evidence_role != "CURRENT_STRUCTURED_SOURCE" or not endpoint_url.endswith(
            "_zh-Hant.zip"
        ):
            raise ValueError(
                "Traditional Chinese XML endpoint has no exact language resource contract"
            )
    elif artifact.role is HkelEvidenceRole.XSD:
        if artifact.language is not None or endpoint_evidence_role != "PARSER_SPECIFICATION":
            raise ValueError("XSD member has an invalid registered contract")
    elif artifact.role is HkelEvidenceRole.PUBLICATION_SPECIFICATION:
        if (
            artifact.language is not None
            or endpoint_source != "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS"
        ):
            raise ValueError("publication specification member has an invalid registered contract")
    elif artifact.role is HkelEvidenceRole.OFFICIAL_COPY:
        if (
            artifact.language not in _LANGUAGES
            or artifact.locator is None
            or endpoint_source not in {"HK-LEG-HKEL-VERIFIED-COPIES", "HK-LEG-HKEL-ASSISTED-COPIES"}
        ):
            raise ValueError("official copy member has an invalid registered contract")
    elif artifact.role is HkelEvidenceRole.EDITORIAL_RECORD:
        if artifact.language is not None or endpoint_source != "HK-LEG-HKEL-EDITORIAL-RECORDS":
            raise ValueError("editorial record member has an invalid registered contract")
    else:  # pragma: no cover - exact enum validation makes this defensive.
        raise AssertionError("unknown HKeL evidence role")


def _validate_source_inventory(
    result: OfficialInventoryResult,
    register: HongKongLegislationSourceRegister,
) -> None:
    """Recompute the existing inventory proof before trusting its fingerprint."""
    expected = tuple(
        sorted(
            (endpoint.endpoint_id, endpoint.version)
            for endpoint in register.endpoints
            if endpoint.source_id == result.source_id and endpoint.complete_inventory_required
        )
    )
    observed = tuple((item.endpoint_id, item.endpoint_version) for item in result.member_results)
    if observed != expected:
        raise ValueError("source inventory members do not match the registered complete set")
    if any(
        item.code not in {OfficialFetchCode.CAPTURED, OfficialFetchCode.CAPTURED_IDENTICAL}
        or item.fingerprint is None
        for item in result.member_results
    ):
        raise ValueError("source inventory contains an incomplete member result")
    digest = sha256()
    for item in result.member_results:
        if item.fingerprint is None:  # pragma: no cover - guarded above.
            raise AssertionError("captured inventory member lacks fingerprint")
        for value in (item.endpoint_id, item.endpoint_version, item.fingerprint):
            digest.update(value.encode("utf-8"))
            digest.update(b"\x00")
    expected_fingerprint = f"sha256:{digest.hexdigest()}"
    if result.inventory_fingerprint != expected_fingerprint:
        raise ValueError("source inventory fingerprint does not prove its member set")


def _exact_utc_cutoff(value: str) -> None:
    """Require the stable UTC instant used by evidence and manifest identity."""
    if _UTC_CUTOFF.fullmatch(value) is None:
        raise ValueError("cutoff must be one canonical UTC RFC3339 second")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not UTC or parsed.isoformat().replace("+00:00", "Z") != value:
        raise ValueError("cutoff must be one canonical UTC RFC3339 second")
