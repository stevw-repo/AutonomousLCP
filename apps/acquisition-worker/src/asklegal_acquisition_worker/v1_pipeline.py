"""Real scheduler-driven acquisition work for the V1 ACQUISITION_WORKER.

The activities capture a configured official endpoint, one exact complete source
inventory, or a bounded HKeL Gazette window through this application's own egress
proxy. A separate ADR 0100 activity may run one exact-host ephemeral browser
handshake, but it retains only a sanitized discovery map with explicit zero
evidence, completeness, no-change, coverage, and processing authority. Endpoint contracts
enforce byte ceilings and hostile-content classification. Admitted source bytes
are written into the Primary evidence vault under Object Lock and verified by
read-back; reports and response-bearing failures remain separately classified,
and every enumerated attempt receives manifest-last accounting.

The orchestrator holds no fetch and no clock, because the scheduler replays it on
every work item; both effects live in activities, which are checkpointed once.

Only endpoints the register already marks enabled can be fetched. The payload
names an endpoint id, never a URL, so a scheduled message cannot direct this
worker at a host the register has not admitted.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Never
from urllib.parse import urlsplit

from asklegal_contracts import ContractViolation, canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import SourceCoverageOutcomeCode
from asklegal_durable_task import TaskFailedError
from asklegal_evidence_vault import ExactObjectReference, RetentionProfile, VaultName
from asklegal_reporting import (
    SourceCoverageObservation,
    SourceCoverageReport,
    SourceCoverageRequirement,
    build_source_coverage_cycle_report,
    build_source_coverage_report,
    parse_source_coverage_report,
)
from asklegal_source_connectors import (
    EndpointAccessMode,
    GazetteEntry,
    GazetteRegisterError,
    GazetteRegisterFailureCode,
    GazetteRequestTiming,
    HkelGazetteRegisterClient,
    HttpMethod,
    OfficialCoverageCycle,
    OfficialEndpointContract,
    OfficialFetchCode,
    OfficialFetchRequest,
    OfficialFetchResult,
    OfficialHttpConnector,
    OfficialInventoryCode,
    OfficialInventoryConnector,
    OfficialInventoryRequest,
    OfficialInventoryResult,
    OfficialObservationGate,
    OfficialRenderedFetchRequest,
    OfficialRenderedSessionConnector,
    OfficialRenderedSessionTransport,
    OfficialSourceState,
    PolicyBoundOfficialHttpTransport,
    ProxiedOfficialHttpTransport,
    SignalUse,
    due_official_source_profiles,
    load_hk_legislation_source_register,
    official_observation_profile,
)

from asklegal_acquisition_worker.patchright_discovery import (
    PatchrightDiscoveryTransport,
    patchright_policy_for_endpoint,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task

    from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure

_LOGGER = logging.getLogger("asklegal_acquisition_worker.v1_pipeline")
_RETENTION_PROFILE = "poc-source-evidence"
# A fixed instant, not a clock reading. The object key is the content
# fingerprint, so re-capturing identical bytes must adopt the existing object,
# and adoption compares the whole retention profile. Any clock-derived value
# makes the same bytes collide with themselves on a later run. This is a POC
# retention horizon and nothing more.
_RETENTION_UNTIL = "2027-01-01T00:00:00Z"
_GAZETTE_SOURCE_ID = "HK-LEG-HKEL-GAZETTE-BACKCAPTURE"
_GAZETTE_ARTIFACT_ENDPOINT = "sep_00000000000000000000000000000000000000000000004f"
_GAZETTE_LOCATOR_PLACEHOLDER = "gazette_artifact_locator"
_GAZETTE_LOCATOR_PREFIX = "hk/"
_GAZETTE_MAX_PAGES = 50
_GAZETTE_LANGUAGES = ("en", "zh-Hant-HK")
_GAZETTE_DATE_PATTERN = re.compile(r"(?P<day>[0-9]{2})/(?P<month>[0-9]{2})/(?P<year>[0-9]{4})")
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_OBSERVATION_CUTOFF_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_PAIR_LENGTH = 2
_DISCOVERY_SUMMARY_PREFIX = "poc/report/source-discovery-summary"
_DISCOVERY_ISOLATION_PREFIX = "poc/isolation/source-discovery"
_DISCOVERY_ATTEMPT_PREFIX = "poc/report/source-discovery-attempt"
_COVERAGE_CYCLE_PREFIX = "poc/report/source-coverage-cycle"
_CURRENT_INVENTORY_SOURCE_ID = "HK-LEG-HKEL-CURRENT-INVENTORY"


class AcquisitionPipelineError(RuntimeError):
    """One exact acquisition-pipeline failure, safe to log."""


def _fail_pipeline(message: str, cause: BaseException | None = None) -> Never:
    """Raise one lint-safe pipeline boundary failure with an optional exact cause."""
    error = AcquisitionPipelineError(message)
    if cause is None:
        raise error
    raise error from cause


class GazetteWindowOutcomeCode(StrEnum):
    """Closed durable outcomes for one date-bounded Gazette activity."""

    COMPLETE = "COMPLETE"
    PARTIAL_CAPTURE = "PARTIAL_CAPTURE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    INCOMPLETE_OBSERVATION = "INCOMPLETE_OBSERVATION"


class GazetteArtifactOutcomeCode(StrEnum):
    """Closed durable outcomes for one listed Gazette artifact."""

    RETAINED = "RETAINED"
    NOT_PUBLISHED = "NOT_PUBLISHED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_CONTRACT_CHANGED = "SOURCE_CONTRACT_CHANGED"
    UNSAFE_RESPONSE = "UNSAFE_RESPONSE"


_REGISTER_TO_WINDOW_CODE = {
    GazetteRegisterFailureCode.SOURCE_UNAVAILABLE: GazetteWindowOutcomeCode.SOURCE_UNAVAILABLE,
    GazetteRegisterFailureCode.SOURCE_CONTRACT_CHANGED: (
        GazetteWindowOutcomeCode.SOURCE_CONTRACT_CHANGED
    ),
    GazetteRegisterFailureCode.INCOMPLETE_OBSERVATION: (
        GazetteWindowOutcomeCode.INCOMPLETE_OBSERVATION
    ),
}

_FETCH_TO_ARTIFACT_CODE = {
    OfficialFetchCode.SOURCE_UNAVAILABLE: GazetteArtifactOutcomeCode.SOURCE_UNAVAILABLE,
    OfficialFetchCode.SOURCE_CONTRACT_CHANGED: (GazetteArtifactOutcomeCode.SOURCE_CONTRACT_CHANGED),
    OfficialFetchCode.UNSAFE_RESPONSE: GazetteArtifactOutcomeCode.UNSAFE_RESPONSE,
}

_ARTIFACT_TO_COVERAGE_OUTCOME = (
    (
        GazetteArtifactOutcomeCode.UNSAFE_RESPONSE,
        SourceCoverageOutcomeCode.UNSAFE_RESPONSE,
    ),
    (
        GazetteArtifactOutcomeCode.SOURCE_CONTRACT_CHANGED,
        SourceCoverageOutcomeCode.SOURCE_CONTRACT_CHANGED,
    ),
    (
        GazetteArtifactOutcomeCode.SOURCE_UNAVAILABLE,
        SourceCoverageOutcomeCode.SOURCE_UNAVAILABLE,
    ),
)

_COMPLETE_INVENTORY_CODES = {
    OfficialInventoryCode.COMPLETE_CAPTURED,
    OfficialInventoryCode.COMPLETE_CAPTURED_IDENTICAL,
}
_CAPTURED_FETCH_CODES = {
    OfficialFetchCode.CAPTURED,
    OfficialFetchCode.CAPTURED_IDENTICAL,
}
_INVENTORY_TO_COVERAGE_OUTCOME = {
    OfficialInventoryCode.COMPLETE_CAPTURED: SourceCoverageOutcomeCode.COMPLETE,
    OfficialInventoryCode.COMPLETE_CAPTURED_IDENTICAL: SourceCoverageOutcomeCode.COMPLETE,
    OfficialInventoryCode.SOURCE_UNAVAILABLE: SourceCoverageOutcomeCode.SOURCE_UNAVAILABLE,
    OfficialInventoryCode.SOURCE_CONTRACT_CHANGED: (
        SourceCoverageOutcomeCode.SOURCE_CONTRACT_CHANGED
    ),
    OfficialInventoryCode.UNSAFE_RESPONSE: SourceCoverageOutcomeCode.UNSAFE_RESPONSE,
}


def _result_text(result: dict[str, object], field: str) -> str:
    value = result.get(field)
    if type(value) is not str or not value:
        message = f"gazette result {field} must be an exact non-empty string"
        raise AcquisitionPipelineError(message)
    return value


def _result_count(result: dict[str, object], field: str) -> int:
    value = result.get(field)
    if type(value) is not int or value < 0:
        message = f"gazette result {field} must be an exact non-negative integer"
        raise AcquisitionPipelineError(message)
    return value


def _observation_cutoff(value: object) -> str:
    if type(value) is not str:
        message = "observation_cutoff must be an exact canonical UTC string"
        raise AcquisitionPipelineError(message)
    try:
        parsed = datetime.strptime(value, _OBSERVATION_CUTOFF_FORMAT).replace(tzinfo=UTC)
    except ValueError as error:
        message = "observation_cutoff must be a real YYYY-MM-DDTHH:MM:SSZ instant"
        raise AcquisitionPipelineError(message) from error
    if parsed.strftime(_OBSERVATION_CUTOFF_FORMAT) != value:
        message = "observation_cutoff must be canonical YYYY-MM-DDTHH:MM:SSZ"
        raise AcquisitionPipelineError(message)
    return value


def _coverage_outcome(
    window_code: GazetteWindowOutcomeCode,
    artifact_outcomes: list[dict[str, object]],
) -> SourceCoverageOutcomeCode:
    """Preserve the strongest deterministic consequence in a partial window."""
    if window_code is not GazetteWindowOutcomeCode.PARTIAL_CAPTURE:
        return SourceCoverageOutcomeCode(window_code.value)
    artifact_codes = {item.get("code") for item in artifact_outcomes}
    for artifact_code, coverage_code in _ARTIFACT_TO_COVERAGE_OUTCOME:
        if artifact_code.value in artifact_codes:
            return coverage_code
    return SourceCoverageOutcomeCode.PARTIAL_CAPTURE


def _coverage_failure_codes(
    artifact_outcomes: list[dict[str, object]],
) -> tuple[str, ...]:
    """Name every non-retained artifact result without hiding publisher absence."""
    failures: set[str] = set()
    for item in artifact_outcomes:
        code = item.get("code")
        if code == GazetteArtifactOutcomeCode.RETAINED.value:
            continue
        failure_code = item.get("failure_code")
        if type(failure_code) is str and failure_code:
            failures.add(failure_code)
        elif type(code) is str and code:
            failures.add(code)
        else:
            message = "non-retained gazette artifact needs one exact failure code"
            raise AcquisitionPipelineError(message)
    return tuple(sorted(failures))


def _inventory_failure_codes(result: OfficialInventoryResult) -> tuple[str, ...]:
    if result.code in _COMPLETE_INVENTORY_CODES:
        return ()
    failures = {
        item.failure_code or item.code.value
        for item in result.member_results
        if item.code not in _CAPTURED_FETCH_CODES
    }
    if result.failure_code is not None:
        failures.add(result.failure_code)
    if not failures:
        message = "failed inventory result needs at least one exact failure code"
        raise AcquisitionPipelineError(message)
    return tuple(sorted(failures))


def _response_fingerprint(result: OfficialFetchResult) -> str:
    if result.fingerprint is not None:
        return result.fingerprint
    if not result.body:
        return ""
    return f"sha256:{sha256(result.body).hexdigest()}"


def _stable_inventory_member_outcomes(
    member_outcomes: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Remove replay-local creation facts from immutable source accounting."""
    stable: list[dict[str, object]] = []
    for member in member_outcomes:
        normalized = dict(member)
        for field in ("evidence", "isolated_response"):
            reference = normalized.get(field)
            if reference is None:
                continue
            try:
                exact_reference = checked_json_value(reference)
            except ContractViolation as error:
                _fail_pipeline("inventory member storage reference must be exact JSON", error)
            if not isinstance(exact_reference, dict):
                _fail_pipeline("inventory member storage reference must be an exact object")
            normalized[field] = {
                key: value for key, value in exact_reference.items() if key != "created"
            }
        stable.append(normalized)
    return stable


def _gazette_artifact_plan(
    entry: GazetteEntry,
    language: str,
) -> str | dict[str, object]:
    """Return one bounded locator or a durable no-fetch publisher outcome."""
    if entry.pdf_url(language) is None:
        return {
            "gazette_id": entry.gazette_id,
            "locator": entry.locator,
            "code": GazetteArtifactOutcomeCode.NOT_PUBLISHED.value,
            "failure_code": None,
        }
    if not entry.locator.startswith(_GAZETTE_LOCATOR_PREFIX):
        return {
            "gazette_id": entry.gazette_id,
            "locator": entry.locator,
            "code": GazetteArtifactOutcomeCode.SOURCE_CONTRACT_CHANGED.value,
            "failure_code": "INVALID_ARTIFACT_LOCATOR",
        }
    return f"{entry.locator.removeprefix(_GAZETTE_LOCATOR_PREFIX)}!{language}"


def _gazette_date(value: str, label: str) -> date:
    """Parse one exact DD/MM/YYYY date before any publisher call."""
    matched = _GAZETTE_DATE_PATTERN.fullmatch(value)
    if matched is None:
        message = f"capture_gazette_window {label} must be DD/MM/YYYY"
        raise AcquisitionPipelineError(message)
    try:
        return date(
            int(matched.group("year")),
            int(matched.group("month")),
            int(matched.group("day")),
        )
    except ValueError as error:
        message = f"capture_gazette_window {label} is not a calendar date"
        raise AcquisitionPipelineError(message) from error


@dataclass(frozen=True, slots=True)
class _GazetteWindowRequest:
    """One exact, bounded Gazette register request."""

    date_from: str
    date_to: str
    first_date: date
    last_date: date
    language: str

    @classmethod
    def from_json(cls, payload: object) -> _GazetteWindowRequest:
        """Reject an incomplete, unbounded, or non-canonical activity payload."""
        try:
            document = checked_json_value(payload)
        except ContractViolation as error:
            message = "capture_gazette_window needs exact JSON values"
            raise AcquisitionPipelineError(message) from error
        if (
            not isinstance(document, dict)
            or not {"date_from", "date_to"}.issubset(document)
            or not set(document).issubset({"date_from", "date_to", "language"})
        ):
            message = "capture_gazette_window needs a date window"
            raise AcquisitionPipelineError(message)
        date_from = document.get("date_from")
        date_to = document.get("date_to")
        if type(date_from) is not str or not date_from or type(date_to) is not str or not date_to:
            message = "capture_gazette_window needs both date_from and date_to as DD/MM/YYYY"
            raise AcquisitionPipelineError(message)
        first_date = _gazette_date(date_from, "date_from")
        last_date = _gazette_date(date_to, "date_to")
        if first_date > last_date:
            message = "capture_gazette_window date_from must not be after date_to"
            raise AcquisitionPipelineError(message)
        language = document.get("language", "en")
        if type(language) is not str:
            message = "capture_gazette_window language must be an exact string"
            raise AcquisitionPipelineError(message)
        if language not in _GAZETTE_LANGUAGES:
            message = "capture_gazette_window language must be en or zh-Hant-HK"
            raise AcquisitionPipelineError(message)
        return cls(date_from, date_to, first_date, last_date, language)


@dataclass(frozen=True, slots=True)
class FetchInstruction:
    """One endpoint the orchestration is asked to capture."""

    endpoint_id: str

    @classmethod
    def from_json(cls, value: object) -> FetchInstruction:
        """Parse one instruction from the scheduler payload."""
        if isinstance(value, str):
            return cls(value)
        try:
            document = checked_json_value(value)
        except ContractViolation:
            document = None
        if isinstance(document, dict) and set(document) == {"endpoint_id"}:
            endpoint_id = document.get("endpoint_id")
            if isinstance(endpoint_id, str) and endpoint_id:
                return cls(endpoint_id)
        message = "acquisition instruction needs an endpoint_id"
        raise AcquisitionPipelineError(message)


@dataclass(frozen=True, slots=True)
class InventoryInstruction:
    """One complete source inventory at an exact scheduler-provided cutoff."""

    source_id: str
    observation_cutoff: str
    prior_fingerprints: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        """Keep the scheduler boundary exact even when constructed directly."""
        if type(self.source_id) is not str or not self.source_id:
            message = "inventory instruction source_id must be an exact non-empty string"
            raise AcquisitionPipelineError(message)
        _observation_cutoff(self.observation_cutoff)
        if (
            type(self.prior_fingerprints) is not tuple
            or any(
                type(item) is not tuple or len(item) != _PAIR_LENGTH
                for item in self.prior_fingerprints
            )
            or self.prior_fingerprints != tuple(sorted(self.prior_fingerprints))
            or len({item[0] for item in self.prior_fingerprints}) != len(self.prior_fingerprints)
            or any(
                type(endpoint_id) is not str
                or not endpoint_id
                or type(fingerprint) is not str
                or _SHA256_PATTERN.fullmatch(fingerprint) is None
                for endpoint_id, fingerprint in self.prior_fingerprints
            )
        ):
            message = "prior_fingerprints must be unique sorted endpoint SHA-256 pairs"
            raise AcquisitionPipelineError(message)

    @classmethod
    def from_json(cls, value: object) -> InventoryInstruction:
        """Parse a closed instruction without accepting caller-selected members."""
        try:
            document = checked_json_value(value)
        except ContractViolation as error:
            message = "inventory instruction must contain exact JSON values"
            raise AcquisitionPipelineError(message) from error
        if not isinstance(document, dict):
            message = "inventory instruction must be an exact object"
            raise AcquisitionPipelineError(message)
        keys = set(document)
        if not {"source_id", "observation_cutoff"}.issubset(keys) or not keys.issubset(
            {"source_id", "observation_cutoff", "prior_fingerprints"}
        ):
            message = "inventory instruction has missing or unknown fields"
            raise AcquisitionPipelineError(message)
        source_id = document["source_id"]
        if type(source_id) is not str or not source_id:
            message = "inventory instruction source_id must be an exact non-empty string"
            raise AcquisitionPipelineError(message)
        cutoff = _observation_cutoff(document["observation_cutoff"])
        raw_priors = document.get("prior_fingerprints", {})
        if not isinstance(raw_priors, dict):
            message = "prior_fingerprints must be an exact endpoint-to-fingerprint object"
            raise AcquisitionPipelineError(message)
        priors: list[tuple[str, str]] = []
        for endpoint_id, fingerprint in raw_priors.items():
            if (
                not endpoint_id
                or type(fingerprint) is not str
                or _SHA256_PATTERN.fullmatch(fingerprint) is None
            ):
                message = "prior_fingerprints must contain exact endpoint SHA-256 values"
                raise AcquisitionPipelineError(message)
            priors.append((endpoint_id, fingerprint))
        return cls(source_id, cutoff, tuple(sorted(priors)))


@dataclass(frozen=True, slots=True)
class RenderedDiscoveryInstruction:
    """One exact reviewed browser-discovery endpoint at a frozen cutoff."""

    endpoint_id: str
    endpoint_version: str
    observation_cutoff: str

    def __post_init__(self) -> None:
        """Keep direct construction as strict as the scheduler JSON boundary."""
        for field in ("endpoint_id", "endpoint_version"):
            value = getattr(self, field)
            if type(value) is not str or not value or value.strip() != value:
                message = f"rendered discovery {field} must be an exact non-empty string"
                raise AcquisitionPipelineError(message)
        _observation_cutoff(self.observation_cutoff)

    @classmethod
    def from_json(cls, value: object) -> RenderedDiscoveryInstruction:
        """Parse one closed instruction with no URL or browser-policy override."""
        try:
            document = checked_json_value(value)
        except ContractViolation as error:
            message = "rendered discovery instruction must contain exact JSON values"
            raise AcquisitionPipelineError(message) from error
        if not isinstance(document, dict) or set(document) != {
            "endpoint_id",
            "endpoint_version",
            "observation_cutoff",
        }:
            message = "rendered discovery instruction has missing or unknown fields"
            raise AcquisitionPipelineError(message)
        endpoint_id = document["endpoint_id"]
        endpoint_version = document["endpoint_version"]
        cutoff = _observation_cutoff(document["observation_cutoff"])
        if (
            type(endpoint_id) is not str
            or not endpoint_id
            or type(endpoint_version) is not str
            or not endpoint_version
        ):
            message = "rendered discovery endpoint identity and version must be exact strings"
            raise AcquisitionPipelineError(message)
        return cls(endpoint_id, endpoint_version, cutoff)


@dataclass(frozen=True, slots=True)
class SourceCycleInstruction:
    """One accepted periodic cycle plus exact prior endpoint fingerprints."""

    cycle: OfficialCoverageCycle
    observation_cutoff: str
    prior_fingerprints_by_source: tuple[
        tuple[str, tuple[tuple[str, str], ...]],
        ...,
    ]

    def __post_init__(self) -> None:
        """Keep direct cycle construction as strict as the scheduler boundary."""
        if type(self.cycle) is not OfficialCoverageCycle:
            _fail_pipeline("source cycle must be an exact accepted cycle")
        _observation_cutoff(self.observation_cutoff)
        if type(self.prior_fingerprints_by_source) is not tuple:
            _fail_pipeline("source cycle priors must be an exact tuple")
        source_ids: list[str] = []
        for item in self.prior_fingerprints_by_source:
            if type(item) is not tuple or len(item) != _PAIR_LENGTH:
                _fail_pipeline("source cycle priors must contain exact pairs")
            source_id, priors = item
            if type(source_id) is not str or not source_id:
                _fail_pipeline("source cycle prior source_id must be exact")
            InventoryInstruction(source_id, self.observation_cutoff, priors)
            source_ids.append(source_id)
        if source_ids != sorted(set(source_ids)):
            _fail_pipeline("source cycle prior sources must be unique and sorted")

    @classmethod
    def from_json(cls, value: object) -> SourceCycleInstruction:
        """Parse a cycle without accepting a caller-selected due-source set."""
        try:
            document = checked_json_value(value)
        except ContractViolation as error:
            _fail_pipeline("source cycle instruction must contain exact JSON values", error)
        if not isinstance(document, dict):
            _fail_pipeline("source cycle instruction must be an exact object")
        keys = set(document)
        if not {"cycle", "observation_cutoff"}.issubset(keys) or not keys.issubset(
            {"cycle", "observation_cutoff", "prior_fingerprints"}
        ):
            _fail_pipeline("source cycle instruction has missing or unknown fields")
        cycle_value = document["cycle"]
        if type(cycle_value) is not str:
            _fail_pipeline("source cycle must be an exact string")
        try:
            cycle = OfficialCoverageCycle(cycle_value)
        except ValueError as error:
            _fail_pipeline("source cycle is unavailable", error)
        cutoff = _observation_cutoff(document["observation_cutoff"])
        raw_by_source = document.get("prior_fingerprints", {})
        if not isinstance(raw_by_source, dict):
            _fail_pipeline("source cycle priors must be an exact object")
        by_source: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        for source_id, raw_priors in raw_by_source.items():
            instruction = InventoryInstruction.from_json(
                {
                    "observation_cutoff": cutoff,
                    "prior_fingerprints": raw_priors,
                    "source_id": source_id,
                }
            )
            by_source.append((source_id, instruction.prior_fingerprints))
        return cls(cycle, cutoff, tuple(sorted(by_source)))

    def priors_for(self, source_id: str) -> tuple[tuple[str, str], ...]:
        """Return exact priors for one due source without inventing an empty member."""
        return next(
            (
                priors
                for prior_source_id, priors in self.prior_fingerprints_by_source
                if prior_source_id == source_id
            ),
            (),
        )


@dataclass(frozen=True, slots=True)
class CoverageReportReference:
    """Exact immutable report reference permitted into cycle assembly."""

    vault: VaultName
    logical_key: str
    version_id: str
    fingerprint: str
    byte_length: int

    @classmethod
    def from_json(cls, value: object) -> CoverageReportReference:
        """Reject summaries that omit an exact vault version or content identity."""
        try:
            document = checked_json_value(value)
        except ContractViolation as error:
            _fail_pipeline("coverage report reference must be exact JSON", error)
        if not isinstance(document, dict) or set(document) != {
            "byte_length",
            "fingerprint",
            "logical_key",
            "vault",
            "version_id",
        }:
            _fail_pipeline("coverage report reference has missing or unknown fields")
        try:
            vault = VaultName(document["vault"])
        except (TypeError, ValueError) as error:
            _fail_pipeline("coverage report vault is unavailable", error)
        logical_key = document["logical_key"]
        version_id = document["version_id"]
        fingerprint = document["fingerprint"]
        byte_length = document["byte_length"]
        if (
            type(logical_key) is not str
            or type(version_id) is not str
            or type(fingerprint) is not str
            or type(byte_length) is not int
        ):
            _fail_pipeline("coverage report reference fields must be exact")
        reference = ExactObjectReference(
            vault,
            logical_key,
            version_id,
            fingerprint,
            byte_length,
        )
        return cls(
            reference.vault,
            reference.logical_key,
            reference.version_id,
            reference.fingerprint,
            reference.byte_length,
        )

    def exact_reference(self) -> ExactObjectReference:
        """Convert the scheduler-safe value into the vault boundary type."""
        return ExactObjectReference(
            self.vault,
            self.logical_key,
            self.version_id,
            self.fingerprint,
            self.byte_length,
        )


def _patchright_transport_for_endpoint(
    endpoint: OfficialEndpointContract,
) -> OfficialRenderedSessionTransport:
    """Build only the exact reviewed ADR 0100 policy for this endpoint."""
    return PatchrightDiscoveryTransport(patchright_policy_for_endpoint(endpoint))


def _stable_discovery_reference(
    reference: dict[str, object] | None,
) -> dict[str, object] | None:
    """Remove write-attempt facts from one fingerprint-stable report reference."""
    if reference is None:
        return None
    return {
        "byte_length": reference["byte_length"],
        "fingerprint": reference["fingerprint"],
        "logical_key": reference["logical_key"],
    }


def _exact_coverage_report_reference(result: object) -> dict[str, object]:
    """Project one activity result to the exact immutable report reference."""
    try:
        document = checked_json_value(result)
    except ContractViolation as error:
        _fail_pipeline("due source result must contain exact JSON", error)
    if not isinstance(document, dict):
        _fail_pipeline("due source result must be an exact object")
    coverage = document.get("coverage_report")
    if not isinstance(coverage, dict):
        _fail_pipeline("due source result lacks a coverage report")
    projected = {
        field: coverage.get(field)
        for field in ("byte_length", "fingerprint", "logical_key", "vault", "version_id")
    }
    reference = CoverageReportReference.from_json(projected)
    return {
        "byte_length": reference.byte_length,
        "fingerprint": reference.fingerprint,
        "logical_key": reference.logical_key,
        "vault": reference.vault.value,
        "version_id": reference.version_id,
    }


def _proxy(infrastructure: V1AcquisitionInfrastructure) -> tuple[str, int]:
    raw = infrastructure.source_egress_proxy_credential.reveal().decode().strip()
    parsed = urlsplit(raw)
    if not parsed.hostname or not parsed.port:
        message = "source egress proxy credential is not host:port"
        raise AcquisitionPipelineError(message)
    return (parsed.hostname, parsed.port)


class AcquisitionActivities:
    """The bounded source and vault effects bound to one infrastructure."""

    def __init__(self, infrastructure: V1AcquisitionInfrastructure) -> None:
        """Compose the bounded connector and the vault this worker writes to."""
        host, port = _proxy(infrastructure)
        self._register = load_hk_legislation_source_register()
        self._transport = ProxiedOfficialHttpTransport(host, port)
        self._observation_gate = OfficialObservationGate()
        self._connector = OfficialHttpConnector(
            self._register,
            PolicyBoundOfficialHttpTransport(
                self._register,
                self._transport,
                self._observation_gate,
            ),
        )
        self._endpoints = {item.endpoint_id: item for item in self._register.endpoints}
        self._sources = {item.source_id: item for item in self._register.sources}
        self._vault = infrastructure.primary_vault
        self._discovery_transport_for_endpoint = _patchright_transport_for_endpoint

    def capture_rendered_discovery(
        self,
        _context: ActivityContext,
        payload: object,
    ) -> object:
        """Run one reviewed browser handshake and retain only its sanitized map."""
        instruction = RenderedDiscoveryInstruction.from_json(payload)
        endpoint = self._endpoints.get(instruction.endpoint_id)
        if endpoint is None or endpoint.version != instruction.endpoint_version:
            message = "rendered discovery endpoint or exact version is absent"
            raise AcquisitionPipelineError(message)
        source = self._sources[endpoint.source_id]
        if not endpoint.enabled or source.operational_state not in {
            OfficialSourceState.CONFIGURED,
            OfficialSourceState.PARTIALLY_CONFIGURED,
        }:
            message = "rendered discovery endpoint is not operationally enabled"
            raise AcquisitionPipelineError(message)
        if (
            endpoint.access_mode is not EndpointAccessMode.BROWSER_SESSION
            or endpoint.signal_use is not SignalUse.DISCOVERY_ONLY
            or "{" in endpoint.url
            or "}" in endpoint.url
        ):
            message = "endpoint is not a fixed non-controlling rendered discovery"
            raise AcquisitionPipelineError(message)
        try:
            patchright_policy_for_endpoint(endpoint)
        except (LookupError, TypeError, ValueError) as error:
            message = "rendered discovery endpoint has no exact reviewed browser policy"
            raise AcquisitionPipelineError(message) from error
        transport = self._discovery_transport_for_endpoint(endpoint)
        result = OfficialRenderedSessionConnector(self._register, transport).fetch(
            OfficialRenderedFetchRequest(
                OfficialFetchRequest(
                    endpoint.endpoint_id,
                    endpoint.version,
                    HttpMethod.GET,
                    None,
                    official_observation_profile(
                        self._register,
                        source.source_id,
                    ).timeout_seconds,
                ),
                None,
            )
        )
        return self._retain_rendered_discovery(instruction, result)

    def _retain_rendered_discovery(
        self,
        instruction: RenderedDiscoveryInstruction,
        result: OfficialFetchResult,
    ) -> dict[str, object]:
        """Retain a sanitized map or isolated diagnostic, then attempt accounting."""
        summary: dict[str, object] | None = None
        isolated: dict[str, object] | None = None
        if result.body:
            if result.code is OfficialFetchCode.DISCOVERY_SIGNAL_CAPTURED:
                summary = self._retain_discovery_bytes(
                    result,
                    _DISCOVERY_SUMMARY_PREFIX,
                )
            else:
                isolated = self._retain_discovery_bytes(
                    result,
                    _DISCOVERY_ISOLATION_PREFIX,
                )
        attempt = self._retain_discovery_attempt(
            instruction,
            result,
            summary,
            isolated,
        )
        source = self._sources[result.source_id]
        return {
            "code": result.code.value,
            "completeness_supported": False,
            "controlling_evidence": False,
            "coverage_satisfied": False,
            "discovery_summary": summary,
            "endpoint_id": result.endpoint_id,
            "endpoint_version": result.endpoint_version,
            "failure_code": result.failure_code,
            "isolated_response": isolated,
            "no_change_supported": False,
            "observation_cutoff": instruction.observation_cutoff,
            "processing_authorized": False,
            "source_id": source.source_id,
            "source_version": source.version,
            "attempt_report": attempt,
        }

    def _retain_discovery_bytes(
        self,
        result: OfficialFetchResult,
        prefix: str,
    ) -> dict[str, object]:
        """Retain only the connector's sanitized summary, never rendered HTML."""
        fingerprint = _response_fingerprint(result)
        if not fingerprint:
            message = "response-bearing rendered discovery needs one exact fingerprint"
            raise AcquisitionPipelineError(message)
        logical_key = f"{prefix}/{result.endpoint_id}/{fingerprint.removeprefix('sha256:')}"
        receipt = self._vault.conditional_create(
            logical_key,
            result.body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        return {
            "byte_length": len(result.body),
            "created": receipt.created,
            "fingerprint": fingerprint,
            "logical_key": logical_key,
            "read_back_verified": receipt.read_back_verified,
            "version_id": receipt.reference.version_id,
        }

    def _retain_discovery_attempt(
        self,
        instruction: RenderedDiscoveryInstruction,
        result: OfficialFetchResult,
        summary: dict[str, object] | None,
        isolated: dict[str, object] | None,
    ) -> dict[str, object]:
        """Write terminal non-authoritative attempt accounting after response storage."""
        source = self._sources[result.source_id]
        body = canonicalize(
            checked_json_value(
                {
                    "code": result.code.value,
                    "completeness_supported": False,
                    "controlling_evidence": False,
                    "coverage_satisfied": False,
                    "discovery_summary": _stable_discovery_reference(summary),
                    "endpoint_id": result.endpoint_id,
                    "endpoint_version": result.endpoint_version,
                    "failure_code": result.failure_code,
                    "isolated_response": _stable_discovery_reference(isolated),
                    "no_change_supported": False,
                    "observation_cutoff": instruction.observation_cutoff,
                    "processing_authorized": False,
                    "schema_id": "asklegal.rendered-discovery-attempt",
                    "schema_version": "1.0.0",
                    "source_id": source.source_id,
                    "source_register_fingerprint": self._register.fingerprint,
                    "source_version": source.version,
                }
            )
        )
        fingerprint = f"sha256:{sha256(body).hexdigest()}"
        logical_key = (
            f"{_DISCOVERY_ATTEMPT_PREFIX}/{result.endpoint_id}/"
            f"{fingerprint.removeprefix('sha256:')}"
        )
        receipt = self._vault.conditional_create(
            logical_key,
            body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        return {
            "byte_length": len(body),
            "created": receipt.created,
            "fingerprint": fingerprint,
            "logical_key": logical_key,
            "read_back_verified": receipt.read_back_verified,
            "version_id": receipt.reference.version_id,
        }

    def capture_inventory(self, _context: ActivityContext, payload: object) -> object:
        """Capture all required members of one registered complete inventory."""
        instruction = InventoryInstruction.from_json(payload)
        source = self._sources.get(instruction.source_id)
        if source is None:
            message = "inventory source is absent from the official register"
            raise AcquisitionPipelineError(message)
        if source.operational_state is not OfficialSourceState.CONFIGURED:
            message = "inventory source is not operationally configured"
            raise AcquisitionPipelineError(message)
        endpoint_versions = tuple(
            sorted(
                (item.endpoint_id, item.version)
                for item in self._register.endpoints
                if item.source_id == source.source_id and item.complete_inventory_required
            )
        )
        if not endpoint_versions:
            message = "inventory source declares no complete member set"
            raise AcquisitionPipelineError(message)
        endpoint_ids = {item[0] for item in endpoint_versions}
        if not {item[0] for item in instruction.prior_fingerprints}.issubset(endpoint_ids):
            message = "prior fingerprint names an endpoint outside the complete member set"
            raise AcquisitionPipelineError(message)
        inventory = OfficialInventoryConnector(self._connector).capture(
            OfficialInventoryRequest(
                source.source_id,
                endpoint_versions,
                instruction.prior_fingerprints,
                official_observation_profile(
                    self._register,
                    source.source_id,
                ).timeout_seconds,
            )
        )
        return self._retain_inventory_result(instruction, inventory)

    def plan_source_cycle(self, _context: ActivityContext, payload: object) -> object:
        """Freeze the register-derived due set before any cycle source attempt."""
        instruction = SourceCycleInstruction.from_json(payload)
        due_sources = due_official_source_profiles(self._register, instruction.cycle)
        due_source_ids = {source.source_id for source in due_sources}
        prior_source_ids = {
            source_id for source_id, _priors in instruction.prior_fingerprints_by_source
        }
        if not prior_source_ids.issubset(due_source_ids):
            _fail_pipeline("source cycle prior names a source outside its due set")
        return {
            "cycle": instruction.cycle.value,
            "observation_cutoff": instruction.observation_cutoff,
            "requirements": [
                {
                    "outage_impact": source.outage_impact.value,
                    "source_id": source.source_id,
                    "source_version": source.version,
                }
                for source in due_sources
            ],
            "schema_id": "asklegal.source-cycle-plan",
            "schema_version": "1.0.0",
            "source_register_fingerprint": self._register.fingerprint,
        }

    def capture_due_source(self, context: ActivityContext, payload: object) -> object:
        """Attempt one plan-derived due source or retain an explicit procedure gap."""
        try:
            document = checked_json_value(payload)
        except ContractViolation as error:
            _fail_pipeline("due source instruction must be exact JSON", error)
        if not isinstance(document, dict) or set(document) != {
            "cycle",
            "observation_cutoff",
            "prior_fingerprints",
            "source_id",
        }:
            _fail_pipeline("due source instruction has missing or unknown fields")
        source_id = document["source_id"]
        if type(source_id) is not str or not source_id:
            _fail_pipeline("due source_id must be an exact non-empty string")
        instruction = SourceCycleInstruction.from_json(
            {
                "cycle": document["cycle"],
                "observation_cutoff": document["observation_cutoff"],
                "prior_fingerprints": {source_id: document["prior_fingerprints"]},
            }
        )
        due_sources = {
            source.source_id: source
            for source in due_official_source_profiles(self._register, instruction.cycle)
        }
        source = due_sources.get(source_id)
        if source is None:
            _fail_pipeline("source is not due in the accepted cycle")
        priors = instruction.priors_for(source_id)
        if source_id == _CURRENT_INVENTORY_SOURCE_ID:
            return self.capture_inventory(
                context,
                {
                    "observation_cutoff": instruction.observation_cutoff,
                    "prior_fingerprints": dict(priors),
                    "source_id": source_id,
                },
            )
        if priors:
            _fail_pipeline("prior fingerprints are unavailable for this source procedure")
        failure_codes = tuple(
            sorted({"PERIODIC_SOURCE_PROCEDURE_NOT_IMPLEMENTED", *source.blockers})
        )
        coverage = self._retain_source_coverage_report(
            SourceCoverageObservation(
                source_id=source.source_id,
                source_version=source.version,
                endpoint_ids=source.endpoint_ids,
                observation_key=(
                    f"{instruction.cycle.value}:{source.source_id}:{instruction.observation_cutoff}"
                ),
                observation_cutoff=instruction.observation_cutoff,
                outcome=SourceCoverageOutcomeCode.INCOMPLETE_OBSERVATION,
                outage_impact=source.outage_impact,
                failure_codes=failure_codes,
                listed=0,
                retained=0,
                not_published=0,
                failed=0,
                observation_manifest_ref="",
            )
        )
        return {
            "code": SourceCoverageOutcomeCode.INCOMPLETE_OBSERVATION.value,
            "coverage_report": coverage,
            "failure_codes": list(failure_codes),
            "observation_cutoff": instruction.observation_cutoff,
            "source_id": source.source_id,
            "source_version": source.version,
        }

    def assemble_source_cycle(self, _context: ActivityContext, payload: object) -> object:
        """Read back exact source reports and retain manifest-last cycle accounting."""
        try:
            document = checked_json_value(payload)
        except ContractViolation as error:
            _fail_pipeline("source cycle assembly must be exact JSON", error)
        if not isinstance(document, dict) or set(document) != {
            "cycle",
            "observation_cutoff",
            "report_references",
            "requirements",
            "source_register_fingerprint",
        }:
            _fail_pipeline("source cycle assembly has missing or unknown fields")
        instruction = SourceCycleInstruction.from_json(
            {
                "cycle": document["cycle"],
                "observation_cutoff": document["observation_cutoff"],
            }
        )
        if document["source_register_fingerprint"] != self._register.fingerprint:
            _fail_pipeline("source register changed after cycle planning")
        due_sources = due_official_source_profiles(self._register, instruction.cycle)
        expected_requirements = [
            {
                "outage_impact": source.outage_impact.value,
                "source_id": source.source_id,
                "source_version": source.version,
            }
            for source in due_sources
        ]
        if document["requirements"] != expected_requirements:
            _fail_pipeline("source cycle requirements drifted from the register")
        raw_references = document["report_references"]
        if not isinstance(raw_references, list):
            _fail_pipeline("source cycle report references must be an exact array")
        reports: list[SourceCoverageReport] = []
        stable_references: list[dict[str, object]] = []
        for raw_reference in raw_references:
            reference = CoverageReportReference.from_json(raw_reference)
            if reference.vault is not self._vault.vault_name:
                _fail_pipeline("coverage report is outside the primary vault")
            report = parse_source_coverage_report(
                self._vault.read_exact(reference.exact_reference())
            )
            if (
                report.fingerprint != reference.fingerprint
                or report.observation.observation_cutoff != instruction.observation_cutoff
            ):
                _fail_pipeline("coverage report identity or cutoff drifted")
            reports.append(report)
            stable_references.append(
                {
                    "byte_length": reference.byte_length,
                    "fingerprint": reference.fingerprint,
                    "logical_key": reference.logical_key,
                    "vault": reference.vault.value,
                    "version_id": reference.version_id,
                }
            )
        requirements = tuple(
            SourceCoverageRequirement(
                source.source_id,
                source.version,
                source.outage_impact,
            )
            for source in due_sources
        )
        cycle = build_source_coverage_cycle_report(
            instruction.observation_cutoff,
            requirements,
            tuple(reports),
        )
        logical_key = (
            f"{_COVERAGE_CYCLE_PREFIX}/{instruction.cycle.value.lower()}/"
            f"{cycle.fingerprint.removeprefix('sha256:')}"
        )
        receipt = self._vault.conditional_create(
            logical_key,
            cycle.canonical_bytes,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        coverage_status_binding = {
            "accounting_complete": cycle.accounting_complete,
            "byte_length": receipt.reference.byte_length,
            "duplicate_source_ids": list(cycle.duplicate_source_ids),
            "fingerprint": cycle.fingerprint,
            "gap_source_ids": list(cycle.gap_source_ids),
            "logical_key": logical_key,
            "missing_source_ids": list(cycle.missing_source_ids),
            "observation_cutoff": instruction.observation_cutoff,
            "release_blocking": cycle.release_blocking,
            "vault": receipt.reference.vault.value,
            "version_id": receipt.reference.version_id,
        }
        return {
            "accounting_complete": cycle.accounting_complete,
            "byte_length": receipt.reference.byte_length,
            "created": receipt.created,
            "coverage_status_binding": coverage_status_binding,
            "cycle": instruction.cycle.value,
            "duplicate_source_ids": list(cycle.duplicate_source_ids),
            "fingerprint": cycle.fingerprint,
            "gap_source_ids": list(cycle.gap_source_ids),
            "logical_key": logical_key,
            "missing_source_ids": list(cycle.missing_source_ids),
            "observation_cutoff": instruction.observation_cutoff,
            "read_back_verified": receipt.read_back_verified,
            "release_blocking": cycle.release_blocking,
            "source_report_references": stable_references,
            "source_register_fingerprint": self._register.fingerprint,
            "vault": receipt.reference.vault.value,
            "version_id": receipt.reference.version_id,
        }

    def _retain_inventory_result(
        self,
        instruction: InventoryInstruction,
        inventory: OfficialInventoryResult,
    ) -> dict[str, object]:
        """Retain admitted members, isolate failed responses, then write accounting."""
        member_outcomes: list[dict[str, object]] = []
        retained = 0
        bytes_retained = 0
        for member in inventory.member_results:
            evidence, isolated = self._retain_inventory_member(member)
            if evidence is not None:
                retained += 1
                bytes_retained += len(member.body)
            member_outcomes.append(
                {
                    "code": member.code.value,
                    "endpoint_id": member.endpoint_id,
                    "endpoint_version": member.endpoint_version,
                    "evidence": evidence,
                    "failure_code": member.failure_code,
                    "isolated_response": isolated,
                    "media_type": member.media_type,
                    "response_fingerprint": _response_fingerprint(member),
                }
            )
        observation_manifest = self._retain_inventory_observation_manifest(
            instruction,
            inventory,
            member_outcomes,
        )
        source = self._sources[inventory.source_id]
        endpoint_ids = tuple(item.endpoint_id for item in inventory.member_results)
        failed = len(inventory.member_results) - retained
        coverage = self._retain_source_coverage_report(
            SourceCoverageObservation(
                source_id=source.source_id,
                source_version=source.version,
                endpoint_ids=endpoint_ids,
                observation_key=f"{source.source_id}:{instruction.observation_cutoff}",
                observation_cutoff=instruction.observation_cutoff,
                outcome=_INVENTORY_TO_COVERAGE_OUTCOME[inventory.code],
                outage_impact=source.outage_impact,
                failure_codes=_inventory_failure_codes(inventory),
                listed=len(inventory.member_results),
                retained=retained,
                not_published=0,
                failed=failed,
                observation_manifest_ref=_result_text(
                    observation_manifest,
                    "logical_key",
                ),
            )
        )
        return {
            "bytes_retained": bytes_retained,
            "code": inventory.code.value,
            "coverage_report": coverage,
            "failed": failed,
            "inventory_fingerprint": inventory.inventory_fingerprint,
            "members": member_outcomes,
            "observation_cutoff": instruction.observation_cutoff,
            "observation_manifest": observation_manifest,
            "retained": retained,
            "source_id": source.source_id,
            "source_version": source.version,
        }

    def _retain_inventory_member(
        self,
        member: OfficialFetchResult,
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        """Retain admitted evidence or isolate one bounded response-bearing failure."""
        if member.code in _CAPTURED_FETCH_CODES:
            if (
                member.fingerprint is None
                or member.classification is None
                or not member.classification.admitted
                or member.media_type is None
            ):
                message = "captured inventory member lacks admitted exact evidence"
                raise AcquisitionPipelineError(message)
            logical_key = (
                f"poc/source/inventory/{member.endpoint_id}/"
                f"{member.fingerprint.removeprefix('sha256:')}"
            )
            receipt = self._vault.conditional_create(
                logical_key,
                member.body,
                RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
            )
            return (
                {
                    "byte_length": len(member.body),
                    "created": receipt.created,
                    "fingerprint": member.fingerprint,
                    "logical_key": logical_key,
                    "read_back_verified": receipt.read_back_verified,
                    "version_id": receipt.reference.version_id,
                },
                None,
            )
        if not member.body:
            return None, None
        fingerprint = _response_fingerprint(member)
        logical_key = (
            f"poc/isolation/source-response/{member.endpoint_id}/"
            f"{fingerprint.removeprefix('sha256:')}"
        )
        receipt = self._vault.conditional_create(
            logical_key,
            member.body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        return None, {
            "byte_length": len(member.body),
            "created": receipt.created,
            "fingerprint": fingerprint,
            "logical_key": logical_key,
            "read_back_verified": receipt.read_back_verified,
            "version_id": receipt.reference.version_id,
        }

    def _retain_inventory_observation_manifest(
        self,
        instruction: InventoryInstruction,
        inventory: OfficialInventoryResult,
        member_outcomes: list[dict[str, object]],
    ) -> dict[str, object]:
        """Write complete attempt accounting only after every member is resolved."""
        source = self._sources[inventory.source_id]
        body = canonicalize(
            checked_json_value(
                {
                    "complete": inventory.code in _COMPLETE_INVENTORY_CODES,
                    "inventory_code": inventory.code.value,
                    "inventory_fingerprint": inventory.inventory_fingerprint,
                    "members": _stable_inventory_member_outcomes(member_outcomes),
                    "observation_cutoff": instruction.observation_cutoff,
                    "schema_id": "asklegal.official-inventory-observation-manifest",
                    "schema_version": "1.0.0",
                    "source_id": source.source_id,
                    "source_register_fingerprint": self._register.fingerprint,
                    "source_version": source.version,
                }
            )
        )
        fingerprint = f"sha256:{sha256(body).hexdigest()}"
        logical_key = (
            f"poc/report/source-observation/{source.source_id.lower()}/"
            f"{fingerprint.removeprefix('sha256:')}"
        )
        receipt = self._vault.conditional_create(
            logical_key,
            body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        return {
            "byte_length": len(body),
            "complete": inventory.code in _COMPLETE_INVENTORY_CODES,
            "created": receipt.created,
            "fingerprint": fingerprint,
            "logical_key": logical_key,
            "read_back_verified": receipt.read_back_verified,
            "version_id": receipt.reference.version_id,
        }

    def capture_gazette_window(self, _context: ActivityContext, payload: object) -> object:
        """Enumerate the gazette register for a date window and retain its PDFs.

        Two boundaries meet here and stay separate. The register grid is a
        publisher API reached through the proxied transport, and it produces only
        locators — discovery, never evidence. Each addressed PDF is then fetched
        through the inert connector and retained the ordinary way, so the bytes
        that become evidence arrive on the evidence path.

        The window is required. An unbounded walk is not reproducible: the
        register grows at the front, so page one shifts between runs and two
        captures of the same query disagree. A closed window over past dates
        returns the same rows every time.
        """
        request = _GazetteWindowRequest.from_json(payload)
        date_from = request.date_from
        date_to = request.date_to
        last_date = request.last_date
        language = request.language

        profile = official_observation_profile(self._register, _GAZETTE_SOURCE_ID)
        client = HkelGazetteRegisterClient(
            self._transport,
            attempts=profile.attempt_ceiling,
            backoff_seconds=float(profile.backoff_seconds[0]),
            timing=GazetteRequestTiming(float(profile.minimum_interval_seconds)),
        )
        try:
            client.open_session()
            # Finish the bounded listing before retaining any addressed artifact.
            # A page-limit or paging-contract failure must not leave a partial
            # evidence set that a caller could mistake for a complete window.
            entries = tuple(
                client.iter_entries(
                    date_from=date_from,
                    date_to=date_to,
                    max_pages=_GAZETTE_MAX_PAGES,
                )
            )
        except GazetteRegisterError as error:
            if error.code is GazetteRegisterFailureCode.INVALID_REQUEST:
                message = "capture_gazette_window contains an invalid register request"
                raise AcquisitionPipelineError(message) from error
            code = _REGISTER_TO_WINDOW_CODE[error.code]
            result: dict[str, object] = {
                "code": code.value,
                "failure_code": error.code.value,
                "listing_manifest": None,
                "date_from": date_from,
                "date_to": date_to,
                "language": language,
                "listed": 0,
                "retained": 0,
                "not_published": 0,
                "failed": 0,
                "skipped": 0,
                "artifacts": [],
                "artifact_outcomes": [],
                "skips": [],
            }
            return self._retain_gazette_coverage_report(
                result=result,
                observation_cutoff=f"{last_date.isoformat()}T23:59:59Z",
                outcome=SourceCoverageOutcomeCode(code.value),
                failure_codes=(error.code.value,),
                observation_manifest_ref="",
            )
        # The PDFs sit behind the same capability gate as the register page, so
        # the inert fetch has to carry the session the grid client established or
        # it is redirected to the gate and the media type never matches.
        # Bind this after enumeration because a grid retry may refresh the
        # publisher session.
        session_connector = OfficialHttpConnector(
            self._register,
            PolicyBoundOfficialHttpTransport(
                self._register,
                self._transport.with_session(client.session_cookies),
                self._observation_gate,
            ),
        )
        listed = 0
        retained: list[dict[str, object]] = []
        artifact_outcomes: list[dict[str, object]] = []
        listing: list[dict[str, object]] = []
        for entry in entries:
            listed += 1
            # Every row is recorded, including those the publisher offers no file
            # for. Their metadata is the only record that the document exists.
            listing.append(
                {
                    "gazette_id": entry.gazette_id,
                    "year": entry.year,
                    "supplement": entry.supplement,
                    "gazette_number": entry.gazette_number,
                    "gazette_date": entry.gazette_date,
                    "title_english": entry.title_english,
                    "title_chinese": entry.title_chinese,
                    "locator": entry.locator,
                    "item_url": entry.item_url,
                    "has_english_pdf": entry.has_english_pdf,
                    "has_chinese_pdf": entry.has_chinese_pdf,
                    "has_bilingual_pdf": entry.has_bilingual_pdf,
                }
            )
            plan = _gazette_artifact_plan(entry, language)
            if isinstance(plan, dict):
                artifact_outcomes.append(plan)
                continue
            outcome = self._retain_gazette_artifact(entry, plan, session_connector)
            artifact_outcomes.append(outcome)
            if outcome["code"] == GazetteArtifactOutcomeCode.RETAINED.value:
                retained.append(outcome)
        manifest = self._retain_gazette_listing(date_from, date_to, listing)
        not_published = sum(
            outcome["code"] == GazetteArtifactOutcomeCode.NOT_PUBLISHED.value
            for outcome in artifact_outcomes
        )
        failed_outcomes = [
            outcome
            for outcome in artifact_outcomes
            if outcome["code"]
            not in {
                GazetteArtifactOutcomeCode.RETAINED.value,
                GazetteArtifactOutcomeCode.NOT_PUBLISHED.value,
            }
        ]
        window_code = (
            GazetteWindowOutcomeCode.PARTIAL_CAPTURE
            if failed_outcomes or not_published
            else GazetteWindowOutcomeCode.COMPLETE
        )
        _LOGGER.info(
            "ACQUISITION_WORKER gazette window %s-%s: %s, listed %s, retained %s, "
            "not-published %s, failed %s",
            date_from,
            date_to,
            window_code.value,
            listed,
            len(retained),
            not_published,
            len(failed_outcomes),
        )
        result = {
            "code": window_code.value,
            "failure_code": None,
            "listing_manifest": manifest,
            "date_from": date_from,
            "date_to": date_to,
            "language": language,
            "listed": listed,
            "retained": len(retained),
            "not_published": not_published,
            "failed": len(failed_outcomes),
            "skipped": not_published + len(failed_outcomes),
            "artifacts": retained,
            "artifact_outcomes": artifact_outcomes,
            "skips": [
                outcome
                for outcome in artifact_outcomes
                if outcome["code"] != GazetteArtifactOutcomeCode.RETAINED.value
            ],
        }
        return self._retain_gazette_coverage_report(
            result=result,
            observation_cutoff=f"{last_date.isoformat()}T23:59:59Z",
            outcome=_coverage_outcome(window_code, artifact_outcomes),
            failure_codes=_coverage_failure_codes(artifact_outcomes),
            observation_manifest_ref=_result_text(manifest, "logical_key"),
        )

    def _retain_gazette_coverage_report(
        self,
        *,
        result: dict[str, object],
        observation_cutoff: str,
        outcome: SourceCoverageOutcomeCode,
        failure_codes: tuple[str, ...],
        observation_manifest_ref: str,
    ) -> dict[str, object]:
        """Retain one policy-bound report for every terminal Gazette result."""
        source = self._sources.get(_GAZETTE_SOURCE_ID)
        if source is None:
            message = "HKeL Gazette source profile is absent from the official register"
            raise AcquisitionPipelineError(message)
        observation = SourceCoverageObservation(
            source_id=source.source_id,
            source_version=source.version,
            endpoint_ids=source.endpoint_ids,
            observation_key=(
                f"{_result_text(result, 'date_from')}.."
                f"{_result_text(result, 'date_to')}:"
                f"{_result_text(result, 'language')}"
            ),
            observation_cutoff=observation_cutoff,
            outcome=outcome,
            outage_impact=source.outage_impact,
            failure_codes=failure_codes,
            listed=_result_count(result, "listed"),
            retained=_result_count(result, "retained"),
            not_published=_result_count(result, "not_published"),
            failed=_result_count(result, "failed"),
            observation_manifest_ref=observation_manifest_ref,
        )
        coverage = self._retain_source_coverage_report(observation)
        return {
            **result,
            "source_id": source.source_id,
            "source_version": source.version,
            "coverage_report": coverage,
        }

    def _retain_source_coverage_report(
        self,
        observation: SourceCoverageObservation,
    ) -> dict[str, object]:
        """Retain one canonical report using its source-owned outage policy."""
        report = build_source_coverage_report(observation)
        fingerprint = report.fingerprint.removeprefix("sha256:")
        logical_key = f"poc/report/source-coverage/{observation.source_id.lower()}/{fingerprint}"
        receipt = self._vault.conditional_create(
            logical_key,
            report.canonical_bytes,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        return {
            "affected_work_blocking": report.affected_work_blocking,
            "byte_length": receipt.reference.byte_length,
            "created": receipt.created,
            "disposition": report.disposition.value,
            "fingerprint": report.fingerprint,
            "logical_key": logical_key,
            "outage_impact": report.observation.outage_impact.value,
            "outcome": report.observation.outcome.value,
            "read_back_verified": receipt.read_back_verified,
            "release_blocking": report.release_blocking,
            "vault": receipt.reference.vault.value,
            "version_id": receipt.reference.version_id,
        }

    def _retain_gazette_listing(
        self,
        date_from: str,
        date_to: str,
        listing: list[dict[str, object]],
    ) -> dict[str, object]:
        """Retain the register listing for one window as its own manifest.

        This is not a source artifact and must not be filed as one. The rows come
        from the publisher's grid API, which ADR 0100 treats as discovery rather
        than controlling evidence, so the manifest lives under its own key prefix
        and records where it came from. What it is good for is the question the
        PDFs cannot answer: which documents were gazetted in this window,
        including the ones the publisher hosts no file for.

        The bytes are canonical — rows sorted by gazette id, separators fixed, no
        capture timestamp inside — so re-running a window produces the identical
        object and the vault adopts it instead of writing a second copy.
        """
        document = {
            "kind": "HKEL_GAZETTE_REGISTER_LISTING",
            "provenance": "publisher grid API, not an inert source fetch",
            "source_id": "HK-LEG-HKEL-GAZETTE-BACKCAPTURE",
            "supplements": ["1", "2", "3"],
            "date_from": date_from,
            "date_to": date_to,
            "row_count": len(listing),
            "rows": sorted(listing, key=lambda row: str(row["gazette_id"])),
        }
        body = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        window = f"{date_from.replace('/', '')}-{date_to.replace('/', '')}"
        fingerprint = sha256(body).hexdigest()
        logical_key = f"poc/source/gazette-listing/{window}/{fingerprint}"
        receipt = self._vault.conditional_create(
            logical_key,
            body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        _LOGGER.info(
            "ACQUISITION_WORKER retained a %s-row listing for %s..%s (created=%s)",
            len(listing),
            date_from,
            date_to,
            receipt.created,
        )
        return {
            "logical_key": logical_key,
            "fingerprint": f"sha256:{fingerprint}",
            "row_count": len(listing),
            "byte_length": len(body),
            "created": receipt.created,
            "read_back_verified": receipt.read_back_verified,
            "version_id": receipt.reference.version_id,
        }

    def _retain_gazette_artifact(
        self,
        entry: GazetteEntry,
        locator: str,
        connector: OfficialHttpConnector,
    ) -> dict[str, object]:
        """Fetch one addressed PDF and return one closed durable outcome."""
        base: dict[str, object] = {
            "gazette_id": entry.gazette_id,
            "locator": locator,
        }
        endpoint = self._endpoints.get(_GAZETTE_ARTIFACT_ENDPOINT)
        if endpoint is None or not endpoint.enabled:
            return {
                **base,
                "code": GazetteArtifactOutcomeCode.SOURCE_CONTRACT_CHANGED.value,
                "failure_code": "GAZETTE_ARTIFACT_ENDPOINT_NOT_ENABLED",
            }
        try:
            result = connector.fetch(
                OfficialFetchRequest(
                    endpoint_id=endpoint.endpoint_id,
                    endpoint_version=endpoint.version,
                    method=HttpMethod.GET,
                    prior_fingerprint=None,
                    timeout_seconds=official_observation_profile(
                        self._register,
                        endpoint.source_id,
                    ).timeout_seconds,
                    substitutions=((_GAZETTE_LOCATOR_PLACEHOLDER, locator),),
                )
            )
        except PermissionError:
            return {
                **base,
                "code": GazetteArtifactOutcomeCode.SOURCE_CONTRACT_CHANGED.value,
                "failure_code": "INVALID_ARTIFACT_LOCATOR",
            }
        failure_code = _FETCH_TO_ARTIFACT_CODE.get(result.code)
        if failure_code is not None:
            return {
                **base,
                "code": failure_code.value,
                "failure_code": result.failure_code,
            }
        if (
            result.code not in {OfficialFetchCode.CAPTURED, OfficialFetchCode.CAPTURED_IDENTICAL}
            or result.fingerprint is None
            or result.classification is None
            or not result.classification.admitted
        ):
            return {
                **base,
                "code": GazetteArtifactOutcomeCode.SOURCE_CONTRACT_CHANGED.value,
                "failure_code": "UNEXPECTED_ARTIFACT_FETCH_RESULT",
            }
        logical_key = f"poc/source/gazette/{result.fingerprint.removeprefix('sha256:')}"
        receipt = self._vault.conditional_create(
            logical_key,
            result.body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        return {
            **base,
            "code": GazetteArtifactOutcomeCode.RETAINED.value,
            "failure_code": None,
            "logical_key": logical_key,
            "fingerprint": result.fingerprint,
            "byte_length": len(result.body),
            "created": receipt.created,
            "read_back_verified": receipt.read_back_verified,
            "version_id": receipt.reference.version_id,
        }

    def capture_endpoint(self, _context: ActivityContext, payload: object) -> object:
        """Capture one enabled endpoint and retain it, returning only its reference.

        Fetch and store are one activity on purpose. Splitting them would put the
        whole document body into the orchestration history, because that is where
        an activity result is persisted and replayed from. Only the reference
        travels through the scheduler.
        """
        instruction = FetchInstruction.from_json(payload)
        endpoint = self._endpoints.get(instruction.endpoint_id)
        if endpoint is None:
            message = f"unknown endpoint {instruction.endpoint_id}"
            raise AcquisitionPipelineError(message)
        if not endpoint.enabled:
            message = f"endpoint {instruction.endpoint_id} is not enabled in the register"
            raise AcquisitionPipelineError(message)
        result = self._connector.fetch(
            OfficialFetchRequest(
                endpoint_id=endpoint.endpoint_id,
                endpoint_version=endpoint.version,
                method=HttpMethod.GET,
                prior_fingerprint=None,
                timeout_seconds=official_observation_profile(
                    self._register,
                    endpoint.source_id,
                ).timeout_seconds,
            )
        )
        if result.failure_code is not None:
            message = f"fetch failed for {endpoint.endpoint_id}: {result.failure_code}"
            raise AcquisitionPipelineError(message)
        classification = result.classification
        if classification is None or not classification.admitted:
            message = (
                f"content from {endpoint.endpoint_id} was not admitted: "
                f"{() if classification is None else classification.reasons}"
            )
            raise AcquisitionPipelineError(message)
        if result.fingerprint is None or result.media_type is None:
            message = f"capture from {endpoint.endpoint_id} lacks exact admitted identity"
            raise AcquisitionPipelineError(message)
        _LOGGER.info(
            "ACQUISITION_WORKER captured %s from %s: %s bytes, %s",
            endpoint.endpoint_id,
            endpoint.source_id,
            len(result.body),
            result.code.value,
        )
        # The fingerprint is the key, so re-capturing identical bytes adopts the
        # existing object rather than writing a second conflicting version.
        logical_key = (
            f"poc/source/{endpoint.endpoint_id}/{result.fingerprint.removeprefix('sha256:')}"
        )
        receipt = self._vault.conditional_create(
            logical_key,
            result.body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        _LOGGER.info(
            "ACQUISITION_WORKER retained %s bytes at %s (created=%s verified=%s)",
            len(result.body),
            logical_key,
            receipt.created,
            receipt.read_back_verified,
        )
        return {
            "endpoint_id": endpoint.endpoint_id,
            "source_id": endpoint.source_id,
            "logical_key": logical_key,
            "fingerprint": result.fingerprint,
            "byte_length": len(result.body),
            "media_type": result.media_type,
            "created": receipt.created,
            "read_back_verified": receipt.read_back_verified,
            "version_id": receipt.reference.version_id,
        }


def acquire_endpoint(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Orchestrate one capture, keeping the document body out of the history."""
    captured = yield context.call_activity("capture_endpoint", input=payload)
    return captured


def acquire_endpoints(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Capture many endpoints in sequence, surviving individual failures.

    Sequential rather than fanned out on purpose. Several of these endpoints carry
    ceilings in the hundreds of megabytes, and the connector holds a response in
    memory while it classifies it; running them in parallel would multiply peak
    memory by the width of the fan-out for no useful gain.

    One endpoint failing must not lose the rest of the run, so each capture is
    caught and recorded. The failures are part of the result, not an exception:
    a source that refuses admission is a finding worth reporting, not an error.
    """
    try:
        document = checked_json_value(payload)
    except ContractViolation as error:
        _fail_pipeline("endpoint batch must contain exact JSON values", error)
    if not isinstance(document, list) or any(
        type(endpoint_id) is not str or not endpoint_id for endpoint_id in document
    ):
        _fail_pipeline("endpoint batch must be an exact non-empty string array")
    endpoint_ids = [endpoint_id for endpoint_id in document if type(endpoint_id) is str]
    captured: list[dict[str, JsonValue]] = []
    failed: list[dict[str, str]] = []
    bytes_retained = 0
    for endpoint_id in endpoint_ids:
        try:
            result = yield context.call_activity(
                "capture_endpoint", input={"endpoint_id": endpoint_id}
            )
        except TaskFailedError as error:
            failed.append({"endpoint_id": endpoint_id, "reason": str(error)[:300]})
            continue
        try:
            captured_result = checked_json_value(result)
        except ContractViolation as error:
            _fail_pipeline("captured endpoint result must contain exact JSON", error)
        if not isinstance(captured_result, dict):
            _fail_pipeline("captured endpoint result must be an exact object")
        byte_length = captured_result.get("byte_length")
        if type(byte_length) is not int or byte_length < 0:
            _fail_pipeline("captured endpoint result lacks exact byte_length")
        bytes_retained += byte_length
        captured.append(captured_result)
    return {
        "requested": len(endpoint_ids),
        "captured": len(captured),
        "failed": len(failed),
        "bytes_retained": bytes_retained,
        "results": captured,
        "failures": failed,
    }


def build_activities(
    infrastructure: V1AcquisitionInfrastructure,
    _environment: Mapping[str, str],
) -> AcquisitionActivities:
    """Compose this worker's activities from its own infrastructure."""
    return AcquisitionActivities(infrastructure)


def acquire_gazette_window(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Capture one date-bounded slice of the gazette register."""
    captured = yield context.call_activity("capture_gazette_window", input=payload)
    return captured


def acquire_rendered_discovery(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Run one reviewed non-controlling rendered discovery attempt."""
    captured = yield context.call_activity("capture_rendered_discovery", input=payload)
    return captured


def acquire_inventory(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Capture one exact complete-inventory source at a frozen cutoff."""
    captured = yield context.call_activity("capture_inventory", input=payload)
    return captured


def acquire_source_cycle(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Plan, attempt, and manifest-last account every source due in one cycle."""
    instruction = SourceCycleInstruction.from_json(payload)
    normalized = {
        "cycle": instruction.cycle.value,
        "observation_cutoff": instruction.observation_cutoff,
        "prior_fingerprints": {
            source_id: dict(priors)
            for source_id, priors in instruction.prior_fingerprints_by_source
        },
    }
    planned_result = yield context.call_activity("plan_source_cycle", input=normalized)
    try:
        planned = checked_json_value(planned_result)
    except ContractViolation as error:
        _fail_pipeline("source cycle plan must contain exact JSON", error)
    if not isinstance(planned, dict):
        _fail_pipeline("source cycle plan must be an exact object")
    requirements = planned.get("requirements")
    if not isinstance(requirements, list):
        _fail_pipeline("source cycle plan lacks exact requirements")
    report_references: list[dict[str, object]] = []
    failed_attempts: list[dict[str, str]] = []
    source_results: list[object] = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            _fail_pipeline("source cycle requirement must be an exact object")
        source_id = requirement.get("source_id")
        if type(source_id) is not str or not source_id:
            _fail_pipeline("source cycle requirement lacks source_id")
        try:
            result = yield context.call_activity(
                "capture_due_source",
                input={
                    "cycle": instruction.cycle.value,
                    "observation_cutoff": instruction.observation_cutoff,
                    "prior_fingerprints": dict(instruction.priors_for(source_id)),
                    "source_id": source_id,
                },
            )
        except TaskFailedError as error:
            failed_attempts.append({"reason": str(error)[:300], "source_id": source_id})
            continue
        source_results.append(result)
        report_references.append(_exact_coverage_report_reference(result))
    cycle_report = yield context.call_activity(
        "assemble_source_cycle",
        input={
            "cycle": instruction.cycle.value,
            "observation_cutoff": instruction.observation_cutoff,
            "report_references": report_references,
            "requirements": requirements,
            "source_register_fingerprint": planned.get("source_register_fingerprint"),
        },
    )
    return {
        "attempted": len(requirements),
        "cycle_report": cycle_report,
        "failed_attempts": failed_attempts,
        "reported": len(report_references),
        "source_results": source_results,
    }
