"""Strict M4 source registry, request, and result contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Never

from asklegal_evidence_vault import HostileClassification

_ID = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")


def _fail(message: str) -> Never:
    raise ValueError(message)


def _text(value: object, field: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact string")
    if not value or value.strip() != value:
        _fail(f"{field} must be non-empty and whitespace-exact")
    return value


def _positive(value: object, field: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field} must be an exact integer")
    if value < 1:
        _fail(f"{field} must be positive")
    return value


def _identifier(value: object, field: str, prefix: str) -> str:
    text = _text(value, field)
    if _ID.fullmatch(text) is None or not text.startswith(f"{prefix}_"):
        _fail(f"{field} must be one register-issued {prefix}_ identity")
    return text


def _string_tuple(value: tuple[object, ...], field: str) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise TypeError(f"{field} must be a non-empty exact tuple")
    if any(type(item) is not str or not item for item in value):
        raise TypeError(f"{field} must contain exact non-empty strings")
    result = tuple(item for item in value if isinstance(item, str))
    if len(set(result)) != len(result):
        _fail(f"{field} must be unique")
    return result


class SourcePolicyState(StrEnum):
    """Explicit source authorization state."""

    CONFIGURED = "CONFIGURED"
    DISABLED = "DISABLED"
    EXPIRED = "EXPIRED"
    UNDECIDED = "UNDECIDED"


class AuthenticationClass(StrEnum):
    """Credential classes without credential values."""

    NONE = "NONE"
    MANAGED_SECRET = "MANAGED_SECRET"


class HttpMethod(StrEnum):
    """Closed acquisition methods."""

    GET = "GET"
    HEAD = "HEAD"


class WatcherResultCode(StrEnum):
    """The six and only six M4 Watcher outcomes."""

    SUPPORTED_NO_CHANGE = "SUPPORTED_NO_CHANGE"
    POSSIBLE_CHANGE = "POSSIBLE_CHANGE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    INCOMPLETE_OBSERVATION = "INCOMPLETE_OBSERVATION"
    UNSAFE_RESPONSE = "UNSAFE_RESPONSE"


class ScraperResultCode(StrEnum):
    """The six and only six M4 Scraper outcomes."""

    SNAPSHOT_PRESERVED = "SNAPSHOT_PRESERVED"
    SUPPORTED_NO_CHANGE_AFTER_CAPTURE = "SUPPORTED_NO_CHANGE_AFTER_CAPTURE"
    PARTIAL_CAPTURE = "PARTIAL_CAPTURE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    UNSAFE_RESPONSE = "UNSAFE_RESPONSE"


class ObservationDisposition(StrEnum):
    """One exact register consequence for an admitted observation."""

    COMPLETE_NO_CHANGE = "COMPLETE_NO_CHANGE"
    SNAPSHOT_PRESERVED = "SNAPSHOT_PRESERVED"
    SOURCE_CONTRACT_REVIEW = "SOURCE_CONTRACT_REVIEW"
    COVERAGE_GAP = "COVERAGE_GAP"
    QUARANTINE = "QUARANTINE"


class AcquisitionConsequence(StrEnum):
    """Closed downstream authorization emitted by M4."""

    NONE = "NONE"
    LEGAL_PROCESSING_ELIGIBLE = "LEGAL_PROCESSING_ELIGIBLE"


@dataclass(frozen=True, slots=True)
class RegisteredSource:
    """One immutable source registration with no credential material."""

    source_id: str
    version: str
    jurisdiction: str
    material_family: str
    endpoint_ids: tuple[str, ...]
    policy_state: SourcePolicyState
    permitted_use: str
    authorization_expires_at: str

    def __post_init__(self) -> None:
        _identifier(self.source_id, "source_id", "src")
        for field in (
            "version",
            "jurisdiction",
            "material_family",
            "permitted_use",
            "authorization_expires_at",
        ):
            _text(getattr(self, field), field)
        if type(self.endpoint_ids) is not tuple or not self.endpoint_ids:
            _fail("endpoint_ids must be one non-empty exact tuple")
        if any(type(item) is not str or not item for item in self.endpoint_ids):
            raise TypeError("endpoint_ids must contain exact non-empty strings")
        for endpoint_id in self.endpoint_ids:
            _identifier(endpoint_id, "endpoint_id", "sep")
        if len(set(self.endpoint_ids)) != len(self.endpoint_ids):
            _fail("endpoint_ids must be unique")
        if type(self.policy_state) is not SourcePolicyState:
            raise TypeError("policy_state must be an exact SourcePolicyState")


@dataclass(frozen=True, slots=True)
class EndpointContract:
    """Exact connector envelope and complete-inventory limits."""

    endpoint_id: str
    version: str
    source_id: str
    rulebook_id: str
    rulebook_version: str
    allowed_host: str
    allowed_path_prefix: str
    methods: tuple[HttpMethod, ...]
    redirect_hosts: tuple[str, ...]
    authentication_class: AuthenticationClass
    media_types: tuple[str, ...]
    max_bytes: int
    max_pages: int
    max_items: int
    time_budget_seconds: int
    complete_inventory_required: bool
    http_304_proves_no_change: bool
    equal_signal_proves_no_change: bool
    required_capture_roles: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.endpoint_id, "endpoint_id", "sep")
        _identifier(self.source_id, "source_id", "src")
        _identifier(self.rulebook_id, "rulebook_id", "rbp")
        for field in (
            "version",
            "rulebook_version",
            "allowed_host",
            "allowed_path_prefix",
        ):
            _text(getattr(self, field), field)
        if (
            type(self.methods) is not tuple
            or not self.methods
            or any(type(item) is not HttpMethod for item in self.methods)
        ):
            raise TypeError("methods must be a non-empty exact tuple of HttpMethod values")
        _string_tuple(self.redirect_hosts, "redirect_hosts")
        _string_tuple(self.media_types, "media_types")
        _string_tuple(self.required_capture_roles, "required_capture_roles")
        if type(self.authentication_class) is not AuthenticationClass:
            raise TypeError("authentication_class must be exact")
        for field in ("max_bytes", "max_pages", "max_items", "time_budget_seconds"):
            _positive(getattr(self, field), field)
        for field in (
            "complete_inventory_required",
            "http_304_proves_no_change",
            "equal_signal_proves_no_change",
        ):
            if type(getattr(self, field)) is not bool:
                raise TypeError(f"{field} must be an exact boolean")


class SourceRegistry:
    """Closed in-memory source and endpoint registry with exact versions."""

    def __init__(
        self,
        sources: tuple[RegisteredSource, ...],
        endpoints: tuple[EndpointContract, ...],
    ) -> None:
        """Validate and freeze a complete synthetic registry."""
        if type(sources) is not tuple or type(endpoints) is not tuple:
            raise TypeError("registry collections must be exact tuples")
        self._sources = {item.source_id: item for item in sources}
        self._endpoints = {item.endpoint_id: item for item in endpoints}
        if len(self._sources) != len(sources) or len(self._endpoints) != len(endpoints):
            _fail("source and endpoint identities must be unique")
        for source in sources:
            for endpoint_id in source.endpoint_ids:
                endpoint = self._endpoints.get(endpoint_id)
                if endpoint is None or endpoint.source_id != source.source_id:
                    _fail("every endpoint must resolve to exactly its owning source")

    @property
    def source_ids(self) -> tuple[str, ...]:
        """Return the complete deterministic Registered Source inventory."""
        return tuple(sorted(self._sources))

    def resolve(
        self,
        source_id: str,
        source_version: str,
        endpoint_id: str,
        endpoint_version: str,
    ) -> tuple[RegisteredSource, EndpointContract]:
        """Resolve exact immutable registrations; floating lookup is forbidden."""
        source = self._sources.get(source_id)
        endpoint = self._endpoints.get(endpoint_id)
        if source is None or endpoint is None:
            raise LookupError("registered source or endpoint is missing")
        if source.version != source_version or endpoint.version != endpoint_version:
            raise LookupError("registered source or endpoint version changed")
        if endpoint.source_id != source.source_id:
            raise LookupError("endpoint does not belong to source")
        return source, endpoint


@dataclass(frozen=True, slots=True)
class CoverageAccountingResult:
    """Complete M4 source-observation accounting without release inference."""

    registered_source_ids: tuple[str, ...]
    accounted_source_ids: tuple[str, ...]
    missing_source_ids: tuple[str, ...]
    duplicate_source_ids: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """Return true only when every Registered Source has exactly one outcome."""
        return not self.missing_source_ids and not self.duplicate_source_ids


class CoverageAccounting:
    """Account for every Registered Source without turning failure into no-change."""

    def __init__(self, registry: SourceRegistry) -> None:
        """Bind accounting to one exact immutable registry inventory."""
        if type(registry) is not SourceRegistry:
            raise TypeError("registry must be an exact SourceRegistry")
        self.registry = registry

    def account(
        self,
        outcomes: tuple[tuple[str, ObservationDisposition], ...],
    ) -> CoverageAccountingResult:
        """Report missing and duplicate source outcomes explicitly."""
        if type(outcomes) is not tuple:
            raise TypeError("outcomes must be an exact tuple")
        counts: dict[str, int] = {}
        registered = set(self.registry.source_ids)
        for source_id, disposition in outcomes:
            _text(source_id, "source_id")
            if type(disposition) is not ObservationDisposition:
                raise TypeError("disposition must be exact")
            if source_id not in registered:
                raise LookupError("outcome names an unregistered source")
            counts[source_id] = counts.get(source_id, 0) + 1
        accounted = tuple(sorted(counts))
        return CoverageAccountingResult(
            self.registry.source_ids,
            accounted,
            tuple(sorted(registered.difference(counts))),
            tuple(sorted(source_id for source_id, count in counts.items() if count != 1)),
        )


@dataclass(frozen=True, slots=True)
class RetryProfile:
    """Bounded deterministic retry and throttling facts."""

    attempt_ceiling: int
    max_elapsed_seconds: int
    backoff_seconds: tuple[int, ...]
    jitter_seed: int
    honor_retry_after: bool

    def __post_init__(self) -> None:
        _positive(self.attempt_ceiling, "attempt_ceiling")
        _positive(self.max_elapsed_seconds, "max_elapsed_seconds")
        if type(self.backoff_seconds) is not tuple or not self.backoff_seconds:
            _fail("backoff_seconds must be one non-empty exact tuple")
        if any(type(item) is not int or item < 0 for item in self.backoff_seconds):
            raise TypeError("backoff_seconds must contain non-negative exact integers")
        if type(self.jitter_seed) is not int:
            raise TypeError("jitter_seed must be an exact integer")
        if type(self.honor_retry_after) is not bool:
            raise TypeError("honor_retry_after must be an exact boolean")


@dataclass(frozen=True, slots=True)
class ConnectorRequest:
    """One exact Watcher or Scraper invocation contract."""

    pipeline_run_id: str
    work_item_id: str
    observation_id: str
    observation_cutoff: str
    source_id: str
    source_version: str
    endpoint_id: str
    endpoint_version: str
    rulebook_id: str
    rulebook_version: str
    method: HttpMethod
    previous_observation_id: str
    previous_snapshot_id: str
    prior_signal: str
    retry_profile: RetryProfile

    def __post_init__(self) -> None:
        _identifier(self.pipeline_run_id, "pipeline_run_id", "run")
        _identifier(self.work_item_id, "work_item_id", "wki")
        _identifier(self.observation_id, "observation_id", "obs")
        _identifier(self.source_id, "source_id", "src")
        _identifier(self.endpoint_id, "endpoint_id", "sep")
        _identifier(self.rulebook_id, "rulebook_id", "rbp")
        _identifier(self.previous_observation_id, "previous_observation_id", "obs")
        _identifier(self.previous_snapshot_id, "previous_snapshot_id", "snp")
        for field in (
            "observation_cutoff",
            "source_version",
            "endpoint_version",
            "rulebook_version",
            "prior_signal",
        ):
            _text(getattr(self, field), field)
        if type(self.method) is not HttpMethod:
            raise TypeError("method must be an exact HttpMethod")
        if type(self.retry_profile) is not RetryProfile:
            raise TypeError("retry_profile must be exact")


@dataclass(frozen=True, slots=True)
class SyntheticResponse:
    """Inert deterministic transport response; it performs no network access."""

    status_code: int
    host: str
    path: str
    media_type: str
    body: bytes
    declared_length: int
    content_encoding: str
    character_encoding: str
    signal: str
    redirect_host: str
    transient: bool = False
    authentication_failed: bool = False
    truncated: bool = False

    def __post_init__(self) -> None:
        if type(self.status_code) is not int or not 100 <= self.status_code <= 599:
            _fail("status_code must be an exact HTTP status")
        for field in (
            "host",
            "path",
            "media_type",
            "content_encoding",
            "character_encoding",
            "signal",
            "redirect_host",
        ):
            _text(getattr(self, field), field)
        if type(self.body) is not bytes:
            raise TypeError("body must be exact bytes")
        if type(self.declared_length) is not int or self.declared_length < 0:
            raise TypeError("declared_length must be a non-negative exact integer")
        for field in ("transient", "authentication_failed", "truncated"):
            if type(getattr(self, field)) is not bool:
                raise TypeError(f"{field} must be an exact boolean")


@dataclass(frozen=True, slots=True)
class SyntheticPage:
    """One source-ordered page with explicit cursor and inventory facts."""

    response: SyntheticResponse
    cursor: str
    next_cursor: str
    member_ids: tuple[str, ...]
    declared_total: int
    inventory_generation: str

    def __post_init__(self) -> None:
        if type(self.response) is not SyntheticResponse:
            raise TypeError("response must be an exact SyntheticResponse")
        for field in ("cursor", "next_cursor", "inventory_generation"):
            _text(getattr(self, field), field)
        if type(self.member_ids) is not tuple:
            raise TypeError("member_ids must be an exact tuple")
        if any(type(item) is not str or not item for item in self.member_ids):
            raise TypeError("member_ids must contain exact non-empty strings")
        if type(self.declared_total) is not int or self.declared_total < 0:
            raise TypeError("declared_total must be a non-negative exact integer")


@dataclass(frozen=True, slots=True)
class AcquisitionArtifact:
    """One exact admitted or isolated acquisition byte payload."""

    role: str
    response: SyntheticResponse
    classification: HostileClassification

    def __post_init__(self) -> None:
        _text(self.role, "role")
        if type(self.response) is not SyntheticResponse:
            raise TypeError("response must be exact")
        if type(self.classification) is not HostileClassification:
            raise TypeError("classification must be exact")


@dataclass(frozen=True, slots=True)
class WatcherResult:
    """One complete Watcher result with preserved attempt artifacts."""

    code: WatcherResultCode
    artifacts: tuple[AcquisitionArtifact, ...]
    affected_boundary: str
    attempts: int

    def __post_init__(self) -> None:
        if type(self.code) is not WatcherResultCode:
            raise TypeError("code must be an exact WatcherResultCode")
        if type(self.artifacts) is not tuple or not self.artifacts:
            _fail("watcher results require preserved attempt evidence")
        if any(type(item) is not AcquisitionArtifact for item in self.artifacts):
            raise TypeError("artifacts must be exact AcquisitionArtifact values")
        _text(self.affected_boundary, "affected_boundary")
        _positive(self.attempts, "attempts")


@dataclass(frozen=True, slots=True)
class ScraperResult:
    """One complete Scraper result with exact inventory proof."""

    code: ScraperResultCode
    artifacts: tuple[AcquisitionArtifact, ...]
    member_ids: tuple[str, ...]
    cursors: tuple[str, ...]
    declared_total: int
    restart_count: int
    attempts: int

    def __post_init__(self) -> None:
        if type(self.code) is not ScraperResultCode:
            raise TypeError("code must be an exact ScraperResultCode")
        if type(self.artifacts) is not tuple or not self.artifacts:
            _fail("scraper results require preserved attempt evidence")
        if any(type(item) is not AcquisitionArtifact for item in self.artifacts):
            raise TypeError("artifacts must be exact AcquisitionArtifact values")
        if type(self.member_ids) is not tuple or type(self.cursors) is not tuple:
            raise TypeError("inventory facts must be exact tuples")
        if type(self.declared_total) is not int or self.declared_total < 0:
            raise TypeError("declared_total must be non-negative")
        if type(self.restart_count) is not int or self.restart_count < 0:
            raise TypeError("restart_count must be non-negative")
        _positive(self.attempts, "attempts")


@dataclass(frozen=True, slots=True)
class AcquisitionOutcome:
    """Internal closed result used by the acquisition application."""

    disposition: ObservationDisposition
    consequence: AcquisitionConsequence
    watcher: WatcherResult
    scraper: ScraperResult | None
    evidence_package_id: str

    def __post_init__(self) -> None:
        if type(self.disposition) is not ObservationDisposition:
            raise TypeError("disposition must be exact")
        if type(self.consequence) is not AcquisitionConsequence:
            raise TypeError("consequence must be exact")
        if type(self.watcher) is not WatcherResult:
            raise TypeError("watcher must be exact")
        if self.scraper is not None and type(self.scraper) is not ScraperResult:
            raise TypeError("scraper must be exact or None")
        _text(self.evidence_package_id, "evidence_package_id")
        if (
            self.consequence is AcquisitionConsequence.LEGAL_PROCESSING_ELIGIBLE
            and self.disposition is not ObservationDisposition.SNAPSHOT_PRESERVED
        ):
            _fail("only a preserved snapshot can become legal-processing eligible")
