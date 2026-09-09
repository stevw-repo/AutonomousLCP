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
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Never, Protocol, TypeIs
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import SourceCoverageOutcomeCode
from asklegal_durable_task import TaskFailedError
from asklegal_evidence_vault import (
    ExactObjectReference,
    ImmutableVault,
    RetentionProfile,
    VaultName,
)
from asklegal_management_register_ports import (
    AcquisitionObservationRecord,
    InMemoryAcquisitionRegister,
)
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
    GldGazetteWindow,
    GldSessionGrant,
    GldSessionRequest,
    HkelArchiveAdmissionError,
    HkelArchiveReuseKey,
    HkelEvidenceArtifact,
    HkelEvidencePlan,
    HkelGazetteRegisterClient,
    HkelInventoryProjection,
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
    OfficialTransportFailure,
    PolicyBoundOfficialHttpTransport,
    ProxiedOfficialHttpTransport,
    SignalUse,
    admit_hkel_current_archive,
    assert_gld_gazette_window_issued,
    build_hkel_evidence_plan_from_projection,
    due_official_source_profiles,
    enumerate_gld_gazette_window,
    load_hk_cases_source_register,
    load_hk_legislation_source_register,
    official_observation_profile,
    project_hkel_current_inventory,
)
from asklegal_source_connectors.hk_judiciary import (
    JudiciaryObservationKind,
    registered_judiciary_current_list_route,
    registered_judiciary_observation_contract,
)
from asklegal_source_connectors.hk_judiciary_authentic import build_judiciary_year_result_url

from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionCycleResult,
    AcquisitionFailureCode,
    CapturedVerifiedPayload,
    JournalTransition,
    LocalAcquisitionJournal,
    WorkItemIdentity,
)
from asklegal_acquisition_worker.gld_operator import build_gld_window_provider
from asklegal_acquisition_worker.gld_session import GldSessionError
from asklegal_acquisition_worker.hk_cases_acquisition import (
    CasesAcceptedPredecessorState,
    CasesBaselinePlan,
    CasesCycleMode,
    CasesJudgmentBundleStore,
    CasesWorkGraph,
    CasesWorkKind,
    RetainedJudiciaryEvidenceReader,
    RetainedJudiciaryPrefix,
    VerifiedCaptureEvidenceReader,
    build_cases_baseline_plan,
    build_cases_observation_graph,
    build_cases_work_graph,
    expand_cases_graph_from_verified_listings,
    expand_cases_graph_from_verified_observations,
    persist_verified_cases_judgment_bundles,
    project_cases_manifest_from_runner,
    retained_judiciary_prefix_from_receipt,
    run_cases_resumable_graph,
)
from asklegal_acquisition_worker.hk_legislation_acquisition import (
    HkelArchiveBodyAdmissionPort,
    HkelArchiveProvenanceKind,
    HkelImportedBaseline,
    LegislationAcceptedSourceState,
    LegislationAcquisitionCycle,
    LegislationAcquisitionManifest,
    LegislationWorkGraph,
    LegislationWorkKind,
    LegislationWorkNode,
    bind_imported_hkel_baseline,
    build_legislation_work_graph,
    hkel_baseline_to_json,
    load_accepted_legislation_source_state,
    parse_gld_gazette_window_snapshot,
    registered_legislation_work_seeds,
    restore_hkel_baseline,
    run_legislation_acquisition_cycle,
)
from asklegal_acquisition_worker.patchright_discovery import (
    PatchrightDiscoveryTransport,
    patchright_policy_for_endpoint,
)
from asklegal_acquisition_worker.resumable_acquisition import (
    AcquisitionClock,
    AcquisitionCycleReport,
    CaptureOutcome,
    CaptureTransport,
    CycleBudget,
    RetainedObjectVerifier,
)
from asklegal_acquisition_worker.retained_evidence_import import (
    KnownV1RetainedImportReceipts,
    RetainedImportedObjectReference,
    RetainedImportReceipt,
    RetainedReportReference,
    import_known_v1_retained_evidence,
    import_retained_report,
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
_CASES_CYCLE = re.compile(r"^cyc_[0-9]{8}(?:_[a-z0-9]+)*_cases$")
_CASES_INSTRUCTION_SCHEMA = "asklegal.cases-resumable-acquisition-instruction"
_CASES_INSTRUCTION_VERSION = "1.0.0"
_PAIR_LENGTH = 2
_DISCOVERY_SUMMARY_PREFIX = "poc/report/source-discovery-summary"
_DISCOVERY_ISOLATION_PREFIX = "poc/isolation/source-discovery"
_DISCOVERY_ATTEMPT_PREFIX = "poc/report/source-discovery-attempt"
_COVERAGE_CYCLE_PREFIX = "poc/report/source-coverage-cycle"
_CURRENT_INVENTORY_SOURCE_ID = "HK-LEG-HKEL-CURRENT-INVENTORY"
_HKEL_EVIDENCE_MANIFEST_PREFIX = "poc/report/hkel-evidence-attempt"
_LEGISLATION_SOURCE_ROOT = "ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT"
_LEGISLATION_ADMISSION_RECEIPT = "ASKLEGAL_HK_V1_HKEL_ADMISSION_RECEIPT"
_LEGISLATION_GLD_WINDOW = "ASKLEGAL_HK_V1_GLD_WINDOW_SNAPSHOT"
_LEGISLATION_ARCHIVE_OBSERVATION = "ASKLEGAL_HK_V1_HKEL_ARCHIVE_OBSERVATION"
_LEGISLATION_STATE_ROOT = "ASKLEGAL_HK_V1_LEGISLATION_STATE_ROOT"
_CASES_SOURCE_ROOT = "ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT"
_CASES_ADVANCED_FORM = "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM"
_CASES_ADVANCED_FORM_FINGERPRINT = "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM_FINGERPRINT"
_CASES_FORM_CONTRACT_VERSION = "1.0.13"
_CASES_ADVANCED_SEARCH_ENTRY_URL = (
    "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
    "?isadvsearch=1&stem=1&selall2=1&selallct=1"
)
_KNOWN_JUDICIARY_REPORT_RELATIVE = Path(
    "judiciary-attempt-p/attempts/judiciary-live-baseline-20260831w/report.json"
)
_KNOWN_JUDICIARY_REPORT_SHA256 = "83c98ee3b139d61b8c790772b7b4408fa5aac63dc891fc1bda3572085c84b92a"
_CASES_WORK_GRAPH = re.compile(
    r"^hk-v1-schedule/(?P<cycle_id>cyc_[0-9]{8}(?:_[a-z0-9]+)*_cases)/"
    r"(?P<kind>daily_current_law|full_reconciliation)/cases/"
    r"(?P<cutoff>[0-9]{8}T[0-9]{6}Z)$"
)
_RETAINED_OBJECT_REF = re.compile(r"^objects/[0-9a-f]{64}\.bin$")
_HTTP_OK = 200
_HTTP_SERVER_ERROR = 500
_KNOWN_HKEL_REPORT_RELATIVE = Path(
    "hkel-attempt-b/attempts/hkel-live-baseline-basic-law20-20260828b/report.json"
)
_KNOWN_HKEL_REPORT_SHA256 = "5f6b8625fd7c0ff4093d96b7a2f72e4ededc9b8af54b6c1add02b95e81549b50"
_KNOWN_HKEL_AUTHORITY = "sha256:ef67b8dd0a6f00d23ca4ec1e8ac157d3fdd6423bf88dbd4f6b4346c0df296c66"
_KNOWN_HKEL_EXECUTION = "sha256:4d43ac6c66e938777942d4d09e22de05542d065a39b34f6c2c2a4c48ced9ad88"
_KNOWN_HKEL_IMPORT_CYCLE = "cyc_20260903_import_hkel"
_MAX_LEGISLATION_CONFIG_BYTES = 1 << 20
_EXPECTED_HKEL_ARCHIVES = 12
_LEGISLATION_OBSERVATION_FIELDS = frozenset(
    {
        "observation_id",
        "input_fingerprint",
        "source_id",
        "endpoint_id",
        "observation_cutoff",
        "watcher_result",
        "scraper_result",
        "disposition",
        "consequence",
        "evidence_package_id",
        "primary_manifest_version",
        "recovery_manifest_version",
        "manifest_fingerprint",
        "source_snapshot_id",
        "issue_id",
    }
)


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
_HKEL_FAILURE_CODES_BY_RESULT = {
    OfficialFetchCode.SOURCE_UNAVAILABLE.value: frozenset(
        {
            "BOUNDED_TRANSPORT_FAILURE",
            "TRANSIENT_HTTP_STATUS_EXHAUSTED",
            "REGISTERED_PROCEDURE_NOT_ENABLED",
        }
    ),
    OfficialFetchCode.SOURCE_CONTRACT_CHANGED.value: frozenset(
        {
            "STATUS_OR_REDIRECT_DRIFT",
            "MEDIA_TYPE_DRIFT",
            "HKEL_ARCHIVE_MEMBER_DECLARATION_MISMATCH",
        }
    ),
    OfficialFetchCode.UNSAFE_RESPONSE.value: frozenset({"HOSTILE_OR_INCOMPLETE_CONTENT"}),
}
_HKEL_TERMINAL_MEMBER_FIELDS = frozenset(
    {
        "archive_member",
        "artifact_id",
        "code",
        "declared_sha256",
        "endpoint_id",
        "endpoint_version",
        "evidence",
        "failure_code",
        "instrument_id",
        "inventory_member_fingerprint",
        "isolated_response",
        "language",
        "locator",
        "resource_id",
        "role",
        "source_disposition",
        "source_id",
        "status_signal",
        "version_signal",
    }
)
_ORDINARY_INVENTORY_MEMBER_FIELDS = frozenset(
    {
        "code",
        "endpoint_id",
        "endpoint_version",
        "evidence",
        "failure_code",
        "isolated_response",
        "media_type",
        "response_fingerprint",
    }
)
_ORDINARY_INVENTORY_FETCH_CODES = frozenset(
    {
        OfficialFetchCode.CAPTURED.value,
        OfficialFetchCode.CAPTURED_IDENTICAL.value,
        OfficialFetchCode.SOURCE_UNAVAILABLE.value,
        OfficialFetchCode.SOURCE_CONTRACT_CHANGED.value,
        OfficialFetchCode.UNSAFE_RESPONSE.value,
    }
)
_ORDINARY_INVENTORY_CAPTURED_CODES = frozenset(
    {
        OfficialFetchCode.CAPTURED.value,
        OfficialFetchCode.CAPTURED_IDENTICAL.value,
    }
)
_ORDINARY_INVENTORY_ENDPOINT_ID = re.compile(r"^sep_[0-9a-f]{48}$")
_INVENTORY_TO_COVERAGE_OUTCOME = {
    OfficialInventoryCode.COMPLETE_CAPTURED: SourceCoverageOutcomeCode.COMPLETE,
    OfficialInventoryCode.COMPLETE_CAPTURED_IDENTICAL: SourceCoverageOutcomeCode.COMPLETE,
    OfficialInventoryCode.SOURCE_UNAVAILABLE: SourceCoverageOutcomeCode.SOURCE_UNAVAILABLE,
    OfficialInventoryCode.SOURCE_CONTRACT_CHANGED: (
        SourceCoverageOutcomeCode.SOURCE_CONTRACT_CHANGED
    ),
    OfficialInventoryCode.UNSAFE_RESPONSE: SourceCoverageOutcomeCode.UNSAFE_RESPONSE,
}


@dataclass(frozen=True, slots=True)
class _OrdinaryInventoryMemberValues:
    """Exact primitive and receipt values from one ordinary inventory member."""

    code: str
    endpoint_id: str
    endpoint_version: str
    response_fingerprint: str
    failure_code: str | None
    evidence: object
    isolated_response: object
    media_type: str | None


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


def _hkel_terminal_member_projection(
    member: HkelEvidenceArtifact,
    *,
    code: object,
    evidence: object,
    failure_code: object,
    isolated_response: object,
) -> dict[str, object]:
    """Construct the one complete self-describing terminal-member contract."""
    return {
        "archive_member": member.archive_member,
        "artifact_id": member.artifact_id,
        "code": code,
        "declared_sha256": member.declared_sha256,
        "endpoint_id": member.endpoint_id,
        "endpoint_version": member.endpoint_version,
        "evidence": evidence,
        "failure_code": failure_code,
        "instrument_id": member.instrument_id,
        "inventory_member_fingerprint": member.inventory_member_fingerprint,
        "isolated_response": isolated_response,
        "language": member.language,
        "locator": member.locator,
        "resource_id": member.resource_id,
        "role": member.role.value,
        "source_disposition": member.source_disposition,
        "source_id": member.source_id,
        "status_signal": member.status_signal,
        "version_signal": member.version_signal,
    }


def _stable_hkel_terminal_member_projection(outcome: dict[str, object]) -> dict[str, object]:
    """Serialize only the closed terminal projection, omitting replay-local creation."""
    if frozenset(outcome) != _HKEL_TERMINAL_MEMBER_FIELDS:
        _fail_pipeline("HKeL terminal outcome has missing or unknown fields")
    stable = {field: outcome[field] for field in _HKEL_TERMINAL_MEMBER_FIELDS}
    for field in ("evidence", "isolated_response"):
        reference = stable[field]
        if reference is None:
            continue
        try:
            _hkel_storage_reference_from_json(reference)
            exact_reference = checked_json_value(reference)
        except (ContractViolation, ValueError) as error:
            _fail_pipeline("HKeL terminal storage reference must be exact JSON", error)
        if not isinstance(exact_reference, dict):  # pragma: no cover - parser proves this.
            _fail_pipeline("HKeL terminal storage reference must be an exact object")
        stable[field] = {key: value for key, value in exact_reference.items() if key != "created"}
    return stable


def _ordinary_inventory_manifest_error() -> Never:
    """Reject every malformed ordinary member through its one closed boundary."""
    _fail_pipeline("ordinary inventory outcome has missing or unknown fields")


def _ordinary_inventory_exact_text(value: object) -> str | None:
    """Return one exact ordinary source text value, or reject its raw subtype."""
    if type(value) is not str or not value or value.strip() != value:
        return None
    return value


def _is_exact_object(value: object) -> TypeIs[dict[str, JsonValue]]:
    """Recognize one exact built-in object with string field names."""
    try:
        document = checked_json_value(value)
    except ContractViolation:
        return False
    return type(value) is dict and type(document) is dict


def _ordinary_inventory_reference(
    value: object,
    *,
    endpoint_id: str,
    response_fingerprint: str,
    storage_prefix: str,
) -> dict[str, object]:
    """Parse and bind one worker-owned ordinary evidence or isolation receipt."""
    if not _is_exact_object(value):
        _ordinary_inventory_manifest_error()
    try:
        reference = _hkel_storage_reference_from_json(value)
    except ValueError:
        _ordinary_inventory_manifest_error()
    expected_key = f"{storage_prefix}/{endpoint_id}/{response_fingerprint.removeprefix('sha256:')}"
    if (
        reference.vault is not VaultName.PRIMARY
        or reference.fingerprint != response_fingerprint
        or reference.logical_key != expected_key
    ):
        _ordinary_inventory_manifest_error()
    return {
        "byte_length": reference.byte_length,
        "fingerprint": reference.fingerprint,
        "logical_key": reference.logical_key,
        "read_back_verified": True,
        "vault": reference.vault.value,
        "version_id": reference.version_id,
    }


def _ordinary_inventory_member_fields(
    outcome: object,
) -> _OrdinaryInventoryMemberValues:
    """Read only exact primitive ordinary-result fields before serializing a member."""
    if not _is_exact_object(outcome) or frozenset(outcome) != _ORDINARY_INVENTORY_MEMBER_FIELDS:
        _ordinary_inventory_manifest_error()
    code = outcome["code"]
    endpoint_id = outcome["endpoint_id"]
    endpoint_version = outcome["endpoint_version"]
    response_fingerprint = outcome["response_fingerprint"]
    media_type = outcome["media_type"]
    failure_code = outcome["failure_code"]
    evidence = outcome["evidence"]
    isolated_response = outcome["isolated_response"]
    if type(code) is not str or code not in _ORDINARY_INVENTORY_FETCH_CODES:
        _ordinary_inventory_manifest_error()
    if (
        type(endpoint_id) is not str
        or _ORDINARY_INVENTORY_ENDPOINT_ID.fullmatch(endpoint_id) is None
    ):
        _ordinary_inventory_manifest_error()
    if (
        type(endpoint_version) is not str
        or _ordinary_inventory_exact_text(endpoint_version) is None
    ):
        _ordinary_inventory_manifest_error()
    if type(response_fingerprint) is not str or (
        response_fingerprint != "" and _SHA256_PATTERN.fullmatch(response_fingerprint) is None
    ):
        _ordinary_inventory_manifest_error()
    if media_type is not None and (
        type(media_type) is not str or _ordinary_inventory_exact_text(media_type) is None
    ):
        _ordinary_inventory_manifest_error()
    if failure_code is not None and (
        type(failure_code) is not str or _ordinary_inventory_exact_text(failure_code) is None
    ):
        _ordinary_inventory_manifest_error()
    return _OrdinaryInventoryMemberValues(
        code=code,
        endpoint_id=endpoint_id,
        endpoint_version=endpoint_version,
        response_fingerprint=response_fingerprint,
        failure_code=failure_code,
        evidence=evidence,
        isolated_response=isolated_response,
        media_type=media_type,
    )


def _stable_captured_inventory_member(
    values: _OrdinaryInventoryMemberValues,
) -> dict[str, object]:
    """Serialize a captured ordinary member only with matching primary evidence."""
    if (
        _SHA256_PATTERN.fullmatch(values.response_fingerprint) is None
        or type(values.media_type) is not str
        or values.failure_code is not None
        or values.isolated_response is not None
        or values.evidence is None
    ):
        _ordinary_inventory_manifest_error()
    stable_evidence = _ordinary_inventory_reference(
        values.evidence,
        endpoint_id=values.endpoint_id,
        response_fingerprint=values.response_fingerprint,
        storage_prefix="poc/source/inventory",
    )
    return {
        "code": values.code,
        "endpoint_id": values.endpoint_id,
        "endpoint_version": values.endpoint_version,
        "evidence": stable_evidence,
        "failure_code": None,
        "isolated_response": None,
        "media_type": values.media_type,
        "response_fingerprint": values.response_fingerprint,
    }


def _stable_unavailable_inventory_member(
    values: _OrdinaryInventoryMemberValues,
) -> dict[str, object]:
    """Serialize an unavailable member, which cannot contain response evidence."""
    if (
        values.response_fingerprint != ""
        or values.media_type is not None
        or type(values.failure_code) is not str
        or values.evidence is not None
        or values.isolated_response is not None
    ):
        _ordinary_inventory_manifest_error()
    return {
        "code": values.code,
        "endpoint_id": values.endpoint_id,
        "endpoint_version": values.endpoint_version,
        "evidence": None,
        "failure_code": values.failure_code,
        "isolated_response": None,
        "media_type": None,
        "response_fingerprint": "",
    }


def _stable_response_failure_inventory_member(
    values: _OrdinaryInventoryMemberValues,
) -> dict[str, object]:
    """Serialize one response-bearing failure without promoting it to evidence."""
    if (
        type(values.media_type) is not str
        or type(values.failure_code) is not str
        or values.evidence is not None
    ):
        _ordinary_inventory_manifest_error()
    stable_isolation: dict[str, object] | None = None
    if values.isolated_response is not None:
        if _SHA256_PATTERN.fullmatch(values.response_fingerprint) is None:
            _ordinary_inventory_manifest_error()
        stable_isolation = _ordinary_inventory_reference(
            values.isolated_response,
            endpoint_id=values.endpoint_id,
            response_fingerprint=values.response_fingerprint,
            storage_prefix="poc/isolation/source-response",
        )
    elif (
        values.code == OfficialFetchCode.SOURCE_CONTRACT_CHANGED.value
        and values.response_fingerprint != ""
    ):
        _ordinary_inventory_manifest_error()
    return {
        "code": values.code,
        "endpoint_id": values.endpoint_id,
        "endpoint_version": values.endpoint_version,
        "evidence": None,
        "failure_code": values.failure_code,
        "isolated_response": stable_isolation,
        "media_type": values.media_type,
        "response_fingerprint": values.response_fingerprint,
    }


def _stable_official_inventory_member_projection(outcome: object) -> dict[str, object]:
    """Serialize one ordinary endpoint result under its exact source-result contract."""
    values = _ordinary_inventory_member_fields(outcome)
    if values.code in _ORDINARY_INVENTORY_CAPTURED_CODES:
        return _stable_captured_inventory_member(values)
    if values.code == OfficialFetchCode.SOURCE_UNAVAILABLE.value:
        return _stable_unavailable_inventory_member(values)
    return _stable_response_failure_inventory_member(values)


def _stable_inventory_member_outcomes(
    member_outcomes: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Serialize ordinary inventory members without borrowing the HKeL schema.

    An ordinary official-inventory member is an endpoint response, whereas an
    HKeL terminal member is an evidence-plan artifact.  They intentionally
    have incompatible provenance fields.  Keeping their projections separate
    prevents a future manifest path from accidentally treating one as the
    other.
    """
    if type(member_outcomes) is not list:
        _ordinary_inventory_manifest_error()
    return [_stable_official_inventory_member_projection(outcome) for outcome in member_outcomes]


def _hkel_storage_reference_from_json(value: object) -> ExactObjectReference:
    """Parse one exact immutable reference, never a receipt-shaped assertion."""
    try:
        document = checked_json_value(value)
    except ContractViolation as error:
        message = "HKeL storage reference must be exact JSON"
        raise ValueError(message) from error
    if not isinstance(document, dict) or set(document) != {
        "byte_length",
        "created",
        "fingerprint",
        "logical_key",
        "read_back_verified",
        "vault",
        "version_id",
    }:
        message = "HKeL storage reference has missing or unknown fields"
        raise ValueError(message)
    byte_length = document.get("byte_length")
    created = document.get("created")
    fingerprint = document.get("fingerprint")
    logical_key = document.get("logical_key")
    read_back_verified = document.get("read_back_verified")
    vault = document.get("vault")
    version_id = document.get("version_id")
    if (
        type(byte_length) is not int
        or type(created) is not bool
        or type(fingerprint) is not str
        or type(logical_key) is not str
        or type(vault) is not str
        or type(version_id) is not str
    ):
        message = "HKeL storage reference fields must have exact types"
        raise ValueError(message)
    if byte_length <= 0 or read_back_verified is not True:
        message = "HKeL storage reference lacks a positive verified receipt"
        raise ValueError(message)
    try:
        return ExactObjectReference(
            VaultName(vault),
            logical_key,
            version_id,
            fingerprint,
            byte_length,
        )
    except (TypeError, ValueError) as error:
        message = "HKeL storage reference is not an exact immutable object"
        raise ValueError(message) from error


def _validate_hkel_terminal_outcome(
    planned: dict[str, HkelEvidenceArtifact],
    outcome: dict[str, object],
    observed: set[str],
    seen_references: set[ExactObjectReference],
    validate_reference: Callable[[object, HkelEvidenceArtifact, str], ExactObjectReference],
) -> None:
    """Validate one outcome against its exact frozen member identity and disposition."""
    artifact_id = outcome.get("artifact_id")
    if type(artifact_id) is not str or artifact_id in observed:
        _fail_pipeline("HKeL terminal outcomes have duplicate or invalid artifact identities")
    member = planned.get(artifact_id)
    if member is None:
        _fail_pipeline("HKeL terminal outcomes do not match the frozen plan role identity")
    expected = _hkel_terminal_member_projection(
        member,
        code=outcome.get("code"),
        evidence=outcome.get("evidence"),
        failure_code=outcome.get("failure_code"),
        isolated_response=outcome.get("isolated_response"),
    )
    if frozenset(outcome) != _HKEL_TERMINAL_MEMBER_FIELDS or outcome != expected:
        _fail_pipeline("HKeL terminal outcomes drifted from the frozen canonical member")
    observed.add(artifact_id)
    code = outcome.get("code")
    if type(code) is not str:
        _fail_pipeline("HKeL terminal outcomes require one exact result code")
    evidence = outcome.get("evidence")
    failure = outcome.get("failure_code")
    isolated = outcome.get("isolated_response")
    if code in {item.value for item in _CAPTURED_FETCH_CODES}:
        if evidence is None or failure is not None or isolated is not None:
            _fail_pipeline("captured HKeL outcome lacks verified retained evidence")
        _record_hkel_terminal_reference(
            evidence,
            member,
            "evidence",
            seen_references,
            validate_reference,
        )
        return
    _validate_hkel_non_captured_outcome(
        member,
        outcome,
        seen_references,
        validate_reference,
    )


def _validate_hkel_non_captured_outcome(
    member: HkelEvidenceArtifact,
    outcome: dict[str, object],
    seen_references: set[ExactObjectReference],
    validate_reference: Callable[[object, HkelEvidenceArtifact, str], ExactObjectReference],
) -> None:
    """Validate no-publication and failure accounting without evidence substitution."""
    code = outcome["code"]
    if type(code) is not str:
        _fail_pipeline("HKeL terminal outcomes require one exact result code")
    evidence = outcome.get("evidence")
    failure = outcome.get("failure_code")
    isolated = outcome.get("isolated_response")
    if code == "NOT_PUBLISHED":
        if (
            code != member.source_disposition
            or evidence is not None
            or failure is not None
            or isolated is not None
        ):
            _fail_pipeline("HKeL no-publication outcome does not match its source fact")
        return
    allowed_failure_codes = _HKEL_FAILURE_CODES_BY_RESULT.get(code)
    if allowed_failure_codes is None:
        _fail_pipeline("HKeL terminal outcome has an unproducible terminal code")
    if evidence is not None:
        _fail_pipeline("failed HKeL outcome cannot carry admitted evidence")
    if type(failure) is not str or failure not in allowed_failure_codes:
        _fail_pipeline("failed HKeL outcome has an unproducible failure code")
    if code == OfficialFetchCode.SOURCE_UNAVAILABLE.value and isolated is not None:
        _fail_pipeline("source-unavailable HKeL outcome cannot carry an isolation reference")
    if isolated is not None:
        _record_hkel_terminal_reference(
            isolated,
            member,
            "isolation",
            seen_references,
            validate_reference,
        )


def _record_hkel_terminal_reference(
    value: object,
    member: HkelEvidenceArtifact,
    storage_kind: str,
    seen_references: set[ExactObjectReference],
    validate_reference: Callable[[object, HkelEvidenceArtifact, str], ExactObjectReference],
) -> None:
    """Validate and reserve one immutable reference for exactly one member disposition."""
    reference = validate_reference(value, member, storage_kind)
    if reference in seen_references:
        _fail_pipeline("HKeL terminal outcomes reuse one retained object")
    seen_references.add(reference)


def _validate_hkel_archive_member(
    member: HkelEvidenceArtifact,
    result: OfficialFetchResult,
) -> None:
    """Prove the planned current-data archive member before it becomes evidence."""
    if (
        member.archive_member is None
        or member.declared_sha256 is None
        or member.resource_id is None
        or member.inventory_member_fingerprint is None
    ):
        message = "planned HKeL archive member lacks source-derived provenance"
        raise ValueError(message)
    try:
        with ZipFile(BytesIO(result.body)) as archive:
            matching = tuple(
                info for info in archive.infolist() if info.filename == member.archive_member
            )
            if len(matching) != 1 or matching[0].is_dir():
                message = "planned HKeL archive member is absent or ambiguous"
                raise ValueError(message)
            content = archive.read(matching[0])
    except (BadZipFile, OSError, RuntimeError) as error:
        message = "planned HKeL archive is unreadable"
        raise ValueError(message) from error
    if f"sha256:{sha256(content).hexdigest()}" != member.declared_sha256:
        message = "planned HKeL archive member hash does not match its declaration"
        raise ValueError(message)


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
class HkelEvidenceInstruction:
    """Closed scheduler input for one plan-before-fetch HKeL evidence bundle.

    The activity later binds this projection to the newly captured complete
    current-inventory result.  The payload contains no URL, source bytes, or
    caller-selected transport policy.
    """

    instrument_id: str
    observation_cutoff: str
    expected_plan_fingerprint: str
    expected_inventory_fingerprint: str

    @classmethod
    def from_json(cls, value: object) -> HkelEvidenceInstruction:
        """Parse one source-byte-free HKeL evidence instruction."""
        try:
            document = checked_json_value(value)
        except ContractViolation as error:
            _fail_pipeline("HKeL evidence instruction must contain exact JSON", error)
        if not isinstance(document, dict) or set(document) != {
            "instrument_id",
            "observation_cutoff",
            "expected_plan_fingerprint",
            "expected_inventory_fingerprint",
        }:
            if isinstance(document, dict) and "artifacts" in document:
                _fail_pipeline("HKeL evidence instruction cannot contain caller artifact authority")
            _fail_pipeline("HKeL evidence instruction has missing or unknown fields")
        instrument_id = document["instrument_id"]
        if type(instrument_id) is not str or not instrument_id:
            _fail_pipeline("HKeL evidence instrument_id must be an exact non-empty string")
        cutoff = _observation_cutoff(document["observation_cutoff"])
        expected_plan = document["expected_plan_fingerprint"]
        expected_inventory = document["expected_inventory_fingerprint"]
        if (
            type(expected_plan) is not str
            or _SHA256_PATTERN.fullmatch(expected_plan) is None
            or type(expected_inventory) is not str
            or _SHA256_PATTERN.fullmatch(expected_inventory) is None
        ):
            _fail_pipeline(
                "HKeL evidence instruction requires frozen exact plan and inventory fingerprints"
            )
        return cls(instrument_id, cutoff, expected_plan, expected_inventory)


@dataclass(frozen=True, slots=True)
class HkelEvidencePlanningInstruction:
    """Closed source-byte-free input for HKeL plan construction."""

    instrument_id: str
    observation_cutoff: str

    @classmethod
    def from_json(cls, value: object) -> HkelEvidencePlanningInstruction:
        """Parse the source-byte-free identity/cutoff planning request."""
        try:
            document = checked_json_value(value)
        except ContractViolation as error:
            _fail_pipeline("HKeL evidence planning instruction must contain exact JSON", error)
        if not isinstance(document, dict) or set(document) != {
            "instrument_id",
            "observation_cutoff",
        }:
            _fail_pipeline("HKeL evidence planning instruction has missing or unknown fields")
        instrument_id = document["instrument_id"]
        if type(instrument_id) is not str or not instrument_id:
            _fail_pipeline("HKeL evidence instrument_id must be an exact non-empty string")
        return cls(instrument_id, _observation_cutoff(document["observation_cutoff"]))


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


@dataclass(frozen=True, slots=True)
class _HkelAttemptIssuance:
    """Short-lived reference authority for one exact frozen HKeL plan attempt."""

    plan_fingerprint: str
    member_snapshots: tuple[tuple[str, str], ...]
    issued_references: set[tuple[str, str, str, ExactObjectReference]]
    issued_outcomes: set[tuple[str, str]]


class _SystemAcquisitionClock:
    """Process clock used only inside the registered resumable activity."""

    @staticmethod
    def monotonic_ns() -> int:
        return time.monotonic_ns()

    @staticmethod
    def now() -> datetime:
        return datetime.now(tz=UTC)


class _PrimaryVaultRetainedVerifier:
    """Re-prove a journaled object against this worker's exact primary vault."""

    def __init__(self, vault: object) -> None:
        self._vault = vault

    def verify(
        self,
        item: WorkItemIdentity,
        object_ref: str,
        content_fingerprint: str,
        body_length: int,
    ) -> bool:
        del item
        resolve = getattr(self._vault, "resolve_current", None)
        read = getattr(self._vault, "read_exact", None)
        if not callable(resolve) or not callable(read):
            return False
        try:
            reference = resolve(object_ref)
            if reference is None:
                return False
            body = read(reference)
        except Exception:  # noqa: BLE001 - hostile vault adapters fail verification closed.
            return False
        return (
            type(body) is bytes
            and len(body) == body_length
            and f"sha256:{sha256(body).hexdigest()}" == content_fingerprint
        )


class V1LegislationTransport:
    """Bind shared-runner identities back to one validated graph node."""

    def __init__(self, activities: AcquisitionActivities, graph: LegislationWorkGraph) -> None:
        """Index one already validated graph for the registered activity adapter."""
        self._activities = activities
        self._nodes = {node.scheduled.identity.work_item_id: node for node in graph.nodes}

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        """Resolve one runner identity and delegate its exact registered node."""
        node = self._nodes.get(item.work_item_id)
        if node is None or node.scheduled.identity != item:
            message = "legislation work identity is absent from graph"
            raise AcquisitionPipelineError(message)
        return self._activities.capture_legislation_work(node)


class LegislationAdmittedOutcomePort(Protocol):
    """Supply locally admitted outcomes for roles whose external session is unavailable."""

    def capture(self, node: LegislationWorkNode) -> CaptureOutcome:
        """Return one exact retained outcome for the registered graph node."""
        ...


@dataclass(frozen=True, slots=True)
class LegislationProductionCycleInputs:
    """Live local authorities required to emit one canonical family manifest."""

    gld_window: GldGazetteWindow
    retained_receipt: RetainedImportReceipt
    retained_report: AcquisitionCycleReport
    admission_document: bytes
    observed_archive_reuse_keys: tuple[HkelArchiveReuseKey, ...] | None
    archive_admission: HkelArchiveBodyAdmissionPort
    review_issue_refs: tuple[str, ...]
    previous: LegislationAcceptedSourceState | None = None
    baseline: HkelImportedBaseline | None = None


class LegislationProductionInputPort(Protocol):
    """Load worker-local admitted inputs while preserving their live issuance."""

    def load(self, cycle_id: str, observation_cutoff: str) -> LegislationProductionCycleInputs:
        """Return exact live authorities for one cycle."""
        ...


class GldWindowProvider(Protocol):
    """Issue one current-cycle GLD listing window through its owned session/exchange."""

    def load_window(self, cycle_id: str, observation_cutoff: str) -> GldGazetteWindow:
        """Return a live-issued window exactly bound to this cycle cutoff."""
        ...


@dataclass(frozen=True, slots=True)
class CasesProductionCycleInputs:
    """Worker-local admitted source facts required to construct one Cases graph."""

    retained_receipt: RetainedImportReceipt
    retained_evidence_reader: RetainedJudiciaryEvidenceReader
    verified_capture_reader: VerifiedCaptureEvidenceReader
    advanced_search_form_body: bytes
    advanced_search_entry_url: str
    form_contract_version: str
    observation_cutoff: str
    cycle_mode: CasesCycleMode
    discrepancy_refs: tuple[str, ...]
    judgment_bundle_store: CasesJudgmentBundleStore
    transport: CaptureTransport
    retained_verifier: RetainedObjectVerifier
    clock: AcquisitionClock
    sleeper: Callable[[float], None]
    budget: CycleBudget
    accepted_predecessor: CasesAcceptedPredecessorState | None = None


class CasesProductionInputPort(Protocol):
    """Load typed current/retained Cases facts without accepting serialized source data."""

    def load(self, cycle_id: str, work_graph_ref: str) -> CasesProductionCycleInputs:
        """Return one exact worker-local source input set for the requested cycle mode."""
        ...


def _cases_configuration_invalid(cause: BaseException | None = None) -> Never:
    error = AcquisitionPipelineError("Cases production configuration invalid")
    if cause is None:
        raise error
    raise error from cause


class _RetainedJudiciaryReader:
    """Read only object bytes already verified by the pinned retained import."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def read(self, reference: RetainedImportedObjectReference) -> bytes:
        """Read the exact content-addressed object and recheck its complete binding."""
        if (
            type(reference) is not RetainedImportedObjectReference
            or _RETAINED_OBJECT_REF.fullmatch(reference.object_ref) is None
        ):
            _cases_configuration_invalid()
        path = self._root.joinpath(*reference.object_ref.split("/"))
        current = self._root
        try:
            for part in reference.object_ref.split("/"):
                current /= part
                if current.is_symlink():
                    _cases_configuration_invalid()
            body = path.read_bytes()
        except OSError as error:
            _cases_configuration_invalid(error)
        if (
            len(body) != reference.body_length
            or f"sha256:{sha256(body).hexdigest()}" != reference.content_fingerprint
        ):
            _cases_configuration_invalid()
        return body


class _PrimaryVaultCasesObjects:
    """Exact Cases capture reader, verifier, and immutable bundle writer."""

    def __init__(self, vault: ImmutableVault) -> None:
        self._vault = vault

    def read_exact(self, object_ref: str, content_fingerprint: str, body_length: int) -> bytes:
        resolve = getattr(self._vault, "resolve_current", None)
        read = getattr(self._vault, "read_exact", None)
        if not callable(resolve) or not callable(read):
            _cases_configuration_invalid()
        try:
            reference = resolve(object_ref)
            body = read(reference) if reference is not None else None
        except Exception as error:  # noqa: BLE001 - a vault adapter is a hostile boundary.
            _cases_configuration_invalid(error)
        if (
            type(body) is not bytes
            or len(body) != body_length
            or f"sha256:{sha256(body).hexdigest()}" != content_fingerprint
        ):
            _cases_configuration_invalid()
        return body

    def verify(
        self,
        item: WorkItemIdentity,
        object_ref: str,
        content_fingerprint: str,
        body_length: int,
    ) -> bool:
        del item
        try:
            self.read_exact(object_ref, content_fingerprint, body_length)
        except AcquisitionPipelineError:
            return False
        return True

    def conditional_create(self, object_ref: str, body: bytes) -> None:
        try:
            receipt = self._vault.conditional_create(
                object_ref,
                body,
                RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
            )
            retained = self._vault.read_exact(receipt.reference)
        except Exception as error:  # noqa: BLE001 - a vault adapter is a hostile boundary.
            _cases_configuration_invalid(error)
        if retained != body or receipt.read_back_verified is not True:
            _cases_configuration_invalid()

    def read(self, object_ref: str) -> bytes:
        resolve = getattr(self._vault, "resolve_current", None)
        read = getattr(self._vault, "read_exact", None)
        if not callable(resolve) or not callable(read):
            _cases_configuration_invalid()
        try:
            reference = resolve(object_ref)
            body = read(reference) if reference is not None else None
        except Exception as error:  # noqa: BLE001 - a vault adapter is a hostile boundary.
            _cases_configuration_invalid(error)
        if type(body) is not bytes:
            _cases_configuration_invalid()
        return body


class V1CasesTransport:
    """Fetch one graph-issued Judiciary item through the worker's explicit proxy."""

    def __init__(self, raw_transport: ProxiedOfficialHttpTransport, vault: ImmutableVault) -> None:
        """Bind the already configured proxy and primary evidence vault."""
        self._transport = raw_transport
        self._vault = vault

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:  # noqa: PLR0911
        """Validate the graph identity, capture bounded bytes, and verify vault readback."""
        kinds = {
            CasesWorkKind.CURRENT_LIST_OBSERVATION.value: JudiciaryObservationKind.CURRENT_LIST,
            CasesWorkKind.RSS_OBSERVATION.value: JudiciaryObservationKind.RSS,
            CasesWorkKind.LISTING_PAGE.value: JudiciaryObservationKind.YEAR_RECONCILIATION,
            CasesWorkKind.JUDGMENT_ARTIFACT.value: JudiciaryObservationKind.JUDGMENT_ARTIFACT,
        }
        kind = kinds.get(item.stage)
        if kind is None:
            return _cases_capture_failure(item, retryable=False)
        try:
            registered = registered_judiciary_observation_contract(kind)
            source_endpoint = load_hk_cases_source_register().resolve_registered_endpoint(
                registered.endpoint_id
            )
            parsed = urlsplit(item.locator)
            registered_url = urlsplit(registered.locator)
            if (
                item.source_role != registered.source_id
                or item.procedure_version != registered.endpoint_version
                or item.media_type != registered.media_type
                or item.max_bytes != registered.max_bytes
                or parsed.scheme != "https"
                or parsed.hostname != registered_url.hostname
                or parsed.port not in {None, 443}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
            ):
                return _cases_capture_failure(item, retryable=False)
            endpoint = replace(source_endpoint, url=item.locator, max_bytes=item.max_bytes)
            response = self._transport.request(
                endpoint=endpoint,
                method=HttpMethod.GET,
                timeout_seconds=30,
            )
        except OfficialTransportFailure:
            return _cases_capture_failure(item, retryable=True)
        except Exception:  # noqa: BLE001 - a malformed registered graph fails closed.
            return _cases_capture_failure(item, retryable=False)
        expected_final = item.locator
        redirect_chain: tuple[str, ...] = ()
        if kind is JudiciaryObservationKind.CURRENT_LIST:
            _entry, expected_final = registered_judiciary_current_list_route()
            redirect_chain = (expected_final,)
        media_type = response.media_type.partition(";")[0].strip().casefold()
        if (
            response.status_code != _HTTP_OK
            or response.truncated
            or not response.body
            or media_type != item.media_type.casefold()
            or response.final_url != expected_final
        ):
            return _cases_capture_failure(
                item,
                retryable=(
                    response.status_code in {408, 425, 429}
                    or response.status_code >= _HTTP_SERVER_ERROR
                ),
            )
        fingerprint = f"sha256:{sha256(response.body).hexdigest()}"
        object_ref = f"poc/source/cases/{fingerprint.removeprefix('sha256:')}"
        try:
            receipt = self._vault.conditional_create(
                object_ref,
                response.body,
                RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
            )
            retained = self._vault.read_exact(receipt.reference)
        except Exception:  # noqa: BLE001 - vault failure is terminal and fail visible.
            return _cases_capture_failure(item, retryable=False)
        if retained != response.body or receipt.read_back_verified is not True:
            return _cases_capture_failure(item, retryable=False)
        return CaptureOutcome(
            work_item_id=item.work_item_id,
            transition=JournalTransition.CAPTURED_VERIFIED,
            status_code=response.status_code,
            media_type=item.media_type,
            final_url=response.final_url,
            body_length=len(response.body),
            body_fingerprint=fingerprint,
            object_ref=object_ref,
            failure_code=None,
            retry_not_before=None,
            read_back_verified=True,
            redirect_chain=redirect_chain,
        )


def _cases_capture_failure(item: WorkItemIdentity, *, retryable: bool) -> CaptureOutcome:
    return CaptureOutcome(
        work_item_id=item.work_item_id,
        transition=(
            JournalTransition.RETRYABLE_FAILURE
            if retryable
            else JournalTransition.CONTRACT_REJECTED
        ),
        status_code=None,
        media_type=None,
        final_url=None,
        body_length=0,
        body_fingerprint=None,
        object_ref=None,
        failure_code=(
            AcquisitionFailureCode.SOURCE_UNAVAILABLE.value
            if retryable
            else AcquisitionFailureCode.SOURCE_CONTRACT_CHANGED.value
        ),
        retry_not_before=(
            datetime.now(tz=UTC).replace(microsecond=0).isoformat() if retryable else None
        ),
        read_back_verified=False,
        redirect_chain=(),
    )


class LocalCasesProductionInputs:
    """Compose scheduled Cases from explicit retained files and worker-owned ports."""

    def __init__(
        self,
        infrastructure: V1AcquisitionInfrastructure,
        environment: Mapping[str, str],
    ) -> None:
        """Validate explicit authorities without creating state or touching a source."""
        self._cycle_state_root = infrastructure.due_cycle_state_root
        self._source_root = _configured_cases_path(environment, _CASES_SOURCE_ROOT, directory=True)
        self._report_path = self._source_root / _KNOWN_JUDICIARY_REPORT_RELATIVE
        report = _read_cases_config(self._report_path, maximum=16_777_216)
        if sha256(report).hexdigest() != _KNOWN_JUDICIARY_REPORT_SHA256:
            _cases_configuration_invalid()
        form_path = _configured_cases_path(environment, _CASES_ADVANCED_FORM, directory=False)
        form_fingerprint_path = _configured_cases_path(
            environment, _CASES_ADVANCED_FORM_FINGERPRINT, directory=False
        )
        self._advanced_form = _read_cases_config(form_path, maximum=8_388_608)
        claimed = _read_cases_config(form_fingerprint_path, maximum=72)
        expected = f"sha256:{sha256(self._advanced_form).hexdigest()}\n".encode()
        if claimed != expected:
            _cases_configuration_invalid()
        host, port = _proxy(infrastructure)
        self._objects = _PrimaryVaultCasesObjects(infrastructure.primary_vault)
        self._transport = V1CasesTransport(
            ProxiedOfficialHttpTransport(host, port), infrastructure.primary_vault
        )

    def load(self, cycle_id: str, work_graph_ref: str) -> CasesProductionCycleInputs:
        """Fully verify retained inputs, then issue exact ports for one scheduled cycle."""
        if type(cycle_id) is not str or _CASES_CYCLE.fullmatch(cycle_id) is None:
            _cases_configuration_invalid()
        match = _CASES_WORK_GRAPH.fullmatch(work_graph_ref)
        if match is None or match.group("cycle_id") != cycle_id:
            _cases_configuration_invalid()
        try:
            cutoff = datetime.strptime(match.group("cutoff"), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError as error:
            _cases_configuration_invalid(error)
        receipts = import_known_v1_retained_evidence(
            self._cycle_state_root, source_admission_root=self._source_root
        )
        mode = (
            CasesCycleMode.FULL_RECONCILIATION
            if match.group("kind") == "full_reconciliation"
            else CasesCycleMode.INCREMENTAL_DISCOVERY
        )
        return CasesProductionCycleInputs(
            retained_receipt=receipts.judiciary,
            retained_evidence_reader=_RetainedJudiciaryReader(self._report_path.parents[2]),
            verified_capture_reader=self._objects,
            advanced_search_form_body=self._advanced_form,
            advanced_search_entry_url=_CASES_ADVANCED_SEARCH_ENTRY_URL,
            form_contract_version=_CASES_FORM_CONTRACT_VERSION,
            observation_cutoff=cutoff.strftime(_OBSERVATION_CUTOFF_FORMAT),
            cycle_mode=mode,
            discrepancy_refs=(),
            judgment_bundle_store=self._objects,
            transport=self._transport,
            retained_verifier=self._objects,
            clock=_SystemAcquisitionClock(),
            sleeper=time.sleep,
            budget=CycleBudget(100, 100_000_000_000, 3_600, 1_000),
        )


def _configured_cases_path(environment: Mapping[str, str], key: str, *, directory: bool) -> Path:
    value = environment.get(key)
    if type(value) is not str or not value or value != value.strip():
        _cases_configuration_invalid()
    path = Path(value)
    if (
        not path.is_absolute()
        or path.is_symlink()
        or (directory and not path.is_dir())
        or (not directory and not path.is_file())
    ):
        _cases_configuration_invalid()
    return path


def _read_cases_config(path: Path, *, maximum: int) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            _cases_configuration_invalid()
        body = path.read_bytes()
    except OSError as error:
        _cases_configuration_invalid(error)
    if not body or len(body) > maximum:
        _cases_configuration_invalid()
    return body


class _ConfiguredGldExchange:
    """Return one startup-validated local snapshot through the issuance boundary."""

    def __init__(self, window: GldGazetteWindow) -> None:
        self._window = window

    def enumerate_window(
        self, grant: GldSessionGrant, request: GldSessionRequest
    ) -> GldGazetteWindow:
        del grant, request
        return self._window

    @staticmethod
    def fetch_artifact(_grant: GldSessionGrant, _entry: object) -> object:
        message = "configured GLD exchange cannot bypass runner artifact capture"
        raise AcquisitionPipelineError(message)


class PrimaryVaultHkelArchiveAdmission:
    """Read back and safely parse one changed HKeL archive from the primary vault."""

    def __init__(self, vault: object) -> None:
        """Bind the application-owned primary-vault reader."""
        self._vault = vault

    def admit_archive(
        self,
        *,
        source_role: str,
        endpoint_id: str,
        object_ref: str,
        content_fingerprint: str,
    ) -> bool:
        """Read and admit every member of one exact registered HKeL archive."""
        if (
            type(endpoint_id) is not str
            or not endpoint_id
            or type(object_ref) is not str
            or not object_ref
            or type(content_fingerprint) is not str
            or _SHA256_PATTERN.fullmatch(content_fingerprint) is None
        ):
            return False
        resolve = getattr(self._vault, "resolve_current", None)
        read = getattr(self._vault, "read_exact", None)
        if not callable(resolve) or not callable(read):
            return False
        try:
            reference = resolve(object_ref)
            body = read(reference) if reference is not None else None
        except Exception:  # noqa: BLE001 - hostile vault adapters fail admission closed.
            return False
        if type(body) is not bytes or f"sha256:{sha256(body).hexdigest()}" != content_fingerprint:
            return False
        try:
            admit_hkel_current_archive(
                endpoint_id=endpoint_id,
                source_role=source_role,
                content_fingerprint=content_fingerprint,
                body=body,
            )
        except HkelArchiveAdmissionError:
            return False
        return True


def _legislation_configuration_invalid(cause: BaseException | None = None) -> Never:
    error = AcquisitionPipelineError("legislation production configuration invalid")
    if cause is None:
        raise error
    raise error from cause


class LocalLegislationProductionInputs:
    """Load exact retained/admission snapshots through read-only local boundaries."""

    def __init__(
        self,
        infrastructure: V1AcquisitionInfrastructure,
        environment: Mapping[str, str],
        *,
        gld_window_provider: GldWindowProvider | None = None,
    ) -> None:
        """Validate every configured local input and durable state location."""
        self._cycle_state_root = infrastructure.due_cycle_state_root
        self._source_root = _configured_legislation_path(
            environment, _LEGISLATION_SOURCE_ROOT, directory=True
        )
        report_path = self._source_root / _KNOWN_HKEL_REPORT_RELATIVE
        if not _regular_config_file(report_path):
            _legislation_configuration_invalid()
        try:
            report_bytes = report_path.read_bytes()
        except OSError as error:
            _legislation_configuration_invalid(error)
        if sha256(report_bytes).hexdigest() != _KNOWN_HKEL_REPORT_SHA256:
            _legislation_configuration_invalid()
        admission_path = _configured_legislation_path(
            environment, _LEGISLATION_ADMISSION_RECEIPT, directory=False
        )
        self._gld_window_provider = gld_window_provider
        self._archive_observation_path = _configured_legislation_path(
            environment, _LEGISLATION_ARCHIVE_OBSERVATION, directory=False
        )
        self._state_root = _configured_legislation_state_root(environment)
        self._state_path = self._state_root / "accepted-legislation-cycle.json"
        self._admission_document = _read_legislation_config(admission_path)
        self._window: GldGazetteWindow | None = None
        if gld_window_provider is None:
            window_path = _configured_legislation_path(
                environment, _LEGISLATION_GLD_WINDOW, directory=False
            )
            window_document = parse_json_bytes(
                _read_legislation_config(window_path),
                max_bytes=_MAX_LEGISLATION_CONFIG_BYTES,
            )
            self._window = parse_gld_gazette_window_snapshot(window_document)
        self._archive_admission = PrimaryVaultHkelArchiveAdmission(infrastructure.primary_vault)

    def load(self, cycle_id: str, observation_cutoff: str) -> LegislationProductionCycleInputs:
        """Reload authentic retained evidence and any accepted advanced predecessor."""
        if type(cycle_id) is not str or not cycle_id or type(observation_cutoff) is not str:
            message = "legislation production inputs invalid"
            raise AcquisitionPipelineError(message)
        receipt, report, baseline = self._load_authentic_baseline()
        issued_window = self._load_gld_window(cycle_id, observation_cutoff)
        previous: LegislationAcceptedSourceState | None = None
        if self._state_path.exists():
            baseline, previous = _load_legislation_cycle_state(
                self._state_path, baseline, self._cycle_state_root
            )
        observed = _load_hkel_archive_observation(self._archive_observation_path)
        return LegislationProductionCycleInputs(
            issued_window,
            receipt,
            report,
            self._admission_document,
            observed,
            self._archive_admission,
            (),
            previous,
            baseline,
        )

    def _load_gld_window(self, cycle_id: str, observation_cutoff: str) -> GldGazetteWindow:
        provider = self._gld_window_provider
        if provider is not None:
            try:
                window = provider.load_window(cycle_id, observation_cutoff)
                assert_gld_gazette_window_issued(window)
            except (AttributeError, TypeError, ValueError) as error:
                _legislation_configuration_invalid(error)
            if window.observation_cutoff != observation_cutoff:
                _legislation_configuration_invalid()
            return window
        window = self._window
        if window is None or observation_cutoff != window.observation_cutoff:
            _legislation_configuration_invalid()
        request = GldSessionRequest(
            window.source_id,
            window.endpoint_id,
            window.endpoint_version,
            window.source_profile_version,
            window.register_version,
            window.register_fingerprint,
            window.start_date,
            window.end_date,
            window.language,
            window.observation_cutoff,
        )
        cutoff = datetime.fromisoformat(observation_cutoff)
        grant = GldSessionGrant(
            "gld-configured-local",
            cutoff.replace(microsecond=0).isoformat(),
            (cutoff.replace(microsecond=0) + timedelta(minutes=1)).isoformat(),
            "egazette.gld.gov.hk",
            f"sha256:{sha256(window.listing_fingerprint.encode()).hexdigest()}",
        )
        return enumerate_gld_gazette_window(_ConfiguredGldExchange(window), grant, request)

    def _load_authentic_baseline(
        self,
    ) -> tuple[RetainedImportReceipt, AcquisitionCycleReport, HkelImportedBaseline]:
        receipt = import_retained_report(
            self._cycle_state_root,
            RetainedReportReference(
                self._source_root / _KNOWN_HKEL_REPORT_RELATIVE,
                f"sha256:{_KNOWN_HKEL_REPORT_SHA256}",
                _KNOWN_HKEL_AUTHORITY,
                _KNOWN_HKEL_EXECUTION,
                "LEGISLATION",
                _KNOWN_HKEL_IMPORT_CYCLE,
                "COMPLETE",
                56,
            ),
        )
        report = _imported_hkel_cycle_report(self._cycle_state_root, receipt)
        baseline = bind_imported_hkel_baseline(
            receipt,
            report,
            self._admission_document,
        )
        return receipt, report, baseline

    def record_completed_cycle(self, cycle: LegislationAcquisitionCycle) -> None:
        """Atomically persist and reread one complete accepted local source state."""
        if type(cycle) is not LegislationAcquisitionCycle or cycle.manifest.result not in {
            AcquisitionCycleResult.COMPLETE,
            AcquisitionCycleResult.NO_CHANGE,
        }:
            return
        manifest = cycle.manifest
        record = AcquisitionObservationRecord(
            observation_id=f"legislation-{manifest.fingerprint.removeprefix('sha256:')}",
            input_fingerprint=manifest.fingerprint,
            source_id="HK-LEG-HKEL-CURRENT-INVENTORY",
            endpoint_id="sep_000000000000000000000000000000000000000000000001",
            observation_cutoff=manifest.observation_cutoff,
            watcher_result="POSSIBLE_CHANGE",
            scraper_result="SNAPSHOT_PRESERVED",
            disposition="SNAPSHOT_PRESERVED",
            consequence="LEGAL_PROCESSING_ELIGIBLE",
            evidence_package_id=f"local-legislation/{manifest.fingerprint}",
            primary_manifest_version=f"local-primary/{manifest.fingerprint}",
            recovery_manifest_version=f"local-recovery/{manifest.fingerprint}",
            manifest_fingerprint=manifest.fingerprint,
            source_snapshot_id=f"local-snapshot/{manifest.fingerprint}",
            issue_id="",
        )
        body: dict[str, JsonValue] = {
            "baseline": hkel_baseline_to_json(cycle.baseline),
            "manifest": manifest.to_json(),
            "observation": _observation_to_json(record),
        }
        document: dict[str, JsonValue] = {
            "schema_id": "asklegal.local-legislation-cycle-state",
            "schema_version": "1.0.0",
            **body,
            "fingerprint": f"sha256:{sha256(canonicalize(body)).hexdigest()}",
        }
        encoded = canonicalize(document)
        temporary = self._state_path.with_suffix(".tmp")
        try:
            _, _, authentic_baseline = self._load_authentic_baseline()
            with temporary.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            _load_legislation_cycle_state(temporary, authentic_baseline, self._cycle_state_root)
            temporary.replace(self._state_path)
            if self._state_path.read_bytes() != encoded:
                _legislation_configuration_invalid()
            _load_legislation_cycle_state(
                self._state_path, authentic_baseline, self._cycle_state_root
            )
        except OSError as error:
            _legislation_configuration_invalid(error)


def _configured_legislation_state_root(environment: Mapping[str, str]) -> Path:
    value = environment.get(_LEGISLATION_STATE_ROOT)
    if type(value) is not str or not value or value != value.strip():
        _legislation_configuration_invalid()
    root = Path(value)
    if not root.is_absolute() or root.is_symlink():
        _legislation_configuration_invalid()
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        _legislation_configuration_invalid(error)
    if not root.is_dir() or root.is_symlink():
        _legislation_configuration_invalid()
    return root


def _load_hkel_archive_observation(path: Path) -> tuple[HkelArchiveReuseKey, ...]:
    try:
        document = parse_json_bytes(
            _read_legislation_config(path), max_bytes=_MAX_LEGISLATION_CONFIG_BYTES
        )
    except (ContractViolation, ValueError) as error:
        _legislation_configuration_invalid(error)
    if type(document) is not dict or set(document) != {
        "schema_id",
        "schema_version",
        "archive_reuse_keys",
        "fingerprint",
    }:
        _legislation_configuration_invalid()
    body = {
        "schema_id": document["schema_id"],
        "schema_version": document["schema_version"],
        "archive_reuse_keys": document["archive_reuse_keys"],
    }
    if (
        document["schema_id"] != "asklegal.hkel-archive-observation"
        or document["schema_version"] != "1.0.0"
        or type(document["archive_reuse_keys"]) is not list
        or document["fingerprint"] != f"sha256:{sha256(canonicalize(body)).hexdigest()}"
    ):
        _legislation_configuration_invalid()
    keys: list[HkelArchiveReuseKey] = []
    for raw in document["archive_reuse_keys"]:
        if type(raw) is not dict or set(raw) != {
            "archive_endpoint_id",
            "archive_fingerprint",
            "publication_profile_fingerprint",
            "fingerprint",
        }:
            _legislation_configuration_invalid()
        try:
            key = HkelArchiveReuseKey.issue(
                raw["archive_endpoint_id"],
                raw["archive_fingerprint"],
                raw["publication_profile_fingerprint"],
            )
        except (TypeError, ValueError) as error:
            _legislation_configuration_invalid(error)
        if key.fingerprint != raw["fingerprint"]:
            _legislation_configuration_invalid()
        keys.append(key)
    if len(keys) != _EXPECTED_HKEL_ARCHIVES:
        _legislation_configuration_invalid()
    return tuple(keys)


def _observation_to_json(record: AcquisitionObservationRecord) -> dict[str, JsonValue]:
    return {
        "observation_id": record.observation_id,
        "input_fingerprint": record.input_fingerprint,
        "source_id": record.source_id,
        "endpoint_id": record.endpoint_id,
        "observation_cutoff": record.observation_cutoff,
        "watcher_result": record.watcher_result,
        "scraper_result": record.scraper_result,
        "disposition": record.disposition,
        "consequence": record.consequence,
        "evidence_package_id": record.evidence_package_id,
        "primary_manifest_version": record.primary_manifest_version,
        "recovery_manifest_version": record.recovery_manifest_version,
        "manifest_fingerprint": record.manifest_fingerprint,
        "source_snapshot_id": record.source_snapshot_id,
        "issue_id": record.issue_id,
    }


def _legislation_state_text(document: dict[str, JsonValue], field: str) -> str:
    value = document[field]
    if type(value) is not str:
        _legislation_configuration_invalid()
    return value


def _load_legislation_cycle_state(
    path: Path,
    authentic_baseline: HkelImportedBaseline,
    cycle_state_root: Path,
) -> tuple[HkelImportedBaseline, LegislationAcceptedSourceState]:
    try:
        document = parse_json_bytes(
            _read_legislation_config(path), max_bytes=_MAX_LEGISLATION_CONFIG_BYTES
        )
    except (ContractViolation, ValueError) as error:
        _legislation_configuration_invalid(error)
    if type(document) is not dict or set(document) != {
        "schema_id",
        "schema_version",
        "baseline",
        "manifest",
        "observation",
        "fingerprint",
    }:
        _legislation_configuration_invalid()
    body = {
        "baseline": document["baseline"],
        "manifest": document["manifest"],
        "observation": document["observation"],
    }
    if (
        document["schema_id"] != "asklegal.local-legislation-cycle-state"
        or document["schema_version"] != "1.0.0"
        or document["fingerprint"] != f"sha256:{sha256(canonicalize(body)).hexdigest()}"
        or type(document["observation"]) is not dict
    ):
        _legislation_configuration_invalid()
    try:
        baseline = restore_hkel_baseline(document["baseline"], authentic_baseline)
        _verify_current_archive_provenance(baseline, cycle_state_root)
        manifest = LegislationAcquisitionManifest.from_json(document["manifest"])
        raw = document["observation"]
        if frozenset(raw) != _LEGISLATION_OBSERVATION_FIELDS:
            _legislation_configuration_invalid()
        if (
            raw["watcher_result"] != "POSSIBLE_CHANGE"
            or raw["scraper_result"] != "SNAPSHOT_PRESERVED"
            or raw["disposition"] != "SNAPSHOT_PRESERVED"
            or raw["consequence"] != "LEGAL_PROCESSING_ELIGIBLE"
        ):
            _legislation_configuration_invalid()
        record = AcquisitionObservationRecord(
            observation_id=_legislation_state_text(raw, "observation_id"),
            input_fingerprint=_legislation_state_text(raw, "input_fingerprint"),
            source_id=_legislation_state_text(raw, "source_id"),
            endpoint_id=_legislation_state_text(raw, "endpoint_id"),
            observation_cutoff=_legislation_state_text(raw, "observation_cutoff"),
            watcher_result="POSSIBLE_CHANGE",
            scraper_result="SNAPSHOT_PRESERVED",
            disposition="SNAPSHOT_PRESERVED",
            consequence="LEGAL_PROCESSING_ELIGIBLE",
            evidence_package_id=_legislation_state_text(raw, "evidence_package_id"),
            primary_manifest_version=_legislation_state_text(raw, "primary_manifest_version"),
            recovery_manifest_version=_legislation_state_text(raw, "recovery_manifest_version"),
            manifest_fingerprint=_legislation_state_text(raw, "manifest_fingerprint"),
            source_snapshot_id=_legislation_state_text(raw, "source_snapshot_id"),
            issue_id=_legislation_state_text(raw, "issue_id"),
        )
        store = InMemoryAcquisitionRegister()
        store.record_observation(record)
        previous = load_accepted_legislation_source_state(manifest, store, record.observation_id)
    except (TypeError, ValueError) as error:
        _legislation_configuration_invalid(error)
    if manifest.source_baseline_fingerprint != baseline.fingerprint:
        _legislation_configuration_invalid()
    return baseline, previous


def _verify_current_archive_provenance(
    baseline: HkelImportedBaseline,
    cycle_state_root: Path,
) -> None:
    """Replay each current archive's originating capture before permitting reuse."""
    entries_by_cycle: dict[str, tuple[object, ...]] = {}
    for reference in baseline.archive_object_references:
        if reference.provenance_kind is HkelArchiveProvenanceKind.TASK4_RETAINED_IMPORT:
            continue
        try:
            entries = entries_by_cycle.get(reference.source_cycle_id)
            if entries is None:
                with LocalAcquisitionJournal(
                    cycle_state_root, reference.source_cycle_id
                ) as journal:
                    entries = journal.replay()
                entries_by_cycle[reference.source_cycle_id] = entries
            matches = tuple(
                entry
                for entry in entries
                if getattr(entry, "transition", None) is JournalTransition.CAPTURED_VERIFIED
                and getattr(getattr(entry, "work_item", None), "work_item_id", None)
                == reference.work_item_id
            )
            if len(matches) != 1:
                _legislation_configuration_invalid()
            entry = matches[0]
            payload = getattr(entry, "payload", None)
            item = getattr(entry, "work_item", None)
            if (
                type(payload) is not CapturedVerifiedPayload
                or type(item) is not WorkItemIdentity
                or item.cycle_id != reference.source_cycle_id
                or item.source_family != "LEGISLATION"
                or item.source_role != "HK_LEG_HKEL_CURRENT_DATA"
                or item.media_type != reference.media_type
                or item.locator != reference.final_url
                or payload.media_type != reference.media_type
                or payload.final_url != reference.final_url
                or payload.body_length != reference.body_length
                or payload.content_fingerprint != reference.content_fingerprint
                or payload.object_ref != reference.object_ref
                or payload.read_back_verified is not True
            ):
                _legislation_configuration_invalid()
        except (KeyError, OSError, TypeError, ValueError) as error:
            _legislation_configuration_invalid(error)


def _configured_legislation_path(
    environment: Mapping[str, str], key: str, *, directory: bool
) -> Path:
    value = environment.get(key)
    if type(value) is not str or not value or value != value.strip():
        _legislation_configuration_invalid()
    path = Path(value)
    if (
        not path.is_absolute()
        or path.is_symlink()
        or (directory and not path.is_dir())
        or (not directory and not _regular_config_file(path))
    ):
        _legislation_configuration_invalid()
    return path


def _regular_config_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def _read_legislation_config(path: Path) -> bytes:
    try:
        body = path.read_bytes()
    except OSError as error:
        _legislation_configuration_invalid(error)
    if not body or len(body) > _MAX_LEGISLATION_CONFIG_BYTES:
        _legislation_configuration_invalid()
    return body


def _imported_hkel_cycle_report(
    state_root: Path, receipt: RetainedImportReceipt
) -> AcquisitionCycleReport:
    with LocalAcquisitionJournal(state_root, receipt.cycle_id) as journal:
        checkpoint = journal.load_checkpoint()
    provisional = AcquisitionCycleReport(
        receipt.cycle_id,
        AcquisitionCycleResult.COMPLETE,
        checkpoint.items,
        0,
        0,
        receipt.journal_head_fingerprint,
        "",
    )
    body = provisional.to_json()
    del body["fingerprint"]
    return replace(
        provisional,
        fingerprint=f"sha256:{sha256(canonicalize(body)).hexdigest()}",
    )


def _validate_cases_current_form(
    inputs: CasesProductionCycleInputs,
    retained_prefix: RetainedJudiciaryPrefix,
    plan: CasesBaselinePlan,
) -> None:
    """Prove the worker-local current form generates the planned successor locator."""
    _validate_cases_shared_inputs(inputs)
    if (
        type(inputs.advanced_search_form_body) is not bytes
        or not inputs.advanced_search_form_body
        or type(inputs.advanced_search_entry_url) is not str
        or not inputs.advanced_search_entry_url
        or type(inputs.form_contract_version) is not str
    ):
        raise ValueError
    year, page = retained_prefix.last_listing
    expected = build_judiciary_year_result_url(
        inputs.advanced_search_form_body,
        entry_url=inputs.advanced_search_entry_url,
        year=year,
        page=page + 1,
        contract_version=inputs.form_contract_version,
    )
    if expected != plan.first_network_item.identity.locator:
        raise ValueError


def _validate_cases_shared_inputs(inputs: CasesProductionCycleInputs) -> None:
    """Validate cycle-mode-independent Cases inputs before constructing any graph."""
    if (
        type(inputs.observation_cutoff) is not str
        or not inputs.observation_cutoff
        or type(inputs.cycle_mode) is not CasesCycleMode
        or type(inputs.discrepancy_refs) is not tuple
        or any(type(ref) is not str or not ref for ref in inputs.discrepancy_refs)
        or not callable(getattr(inputs.judgment_bundle_store, "conditional_create", None))
        or not callable(getattr(inputs.judgment_bundle_store, "read", None))
        or (
            inputs.accepted_predecessor is not None
            and type(inputs.accepted_predecessor) is not CasesAcceptedPredecessorState
        )
    ):
        raise ValueError
    try:
        _observation_cutoff(inputs.observation_cutoff)
    except AcquisitionPipelineError as error:
        raise ValueError from error


def _cases_inputs_invalid() -> Never:
    """Keep malformed worker-local Case input handling uniformly fail-closed."""
    raise ValueError


class AcquisitionActivities:
    """The bounded source and vault effects bound to one infrastructure."""

    def __init__(
        self,
        infrastructure: V1AcquisitionInfrastructure,
        *,
        legislation_admitted_outcomes: LegislationAdmittedOutcomePort | None = None,
        legislation_production_inputs: LegislationProductionInputPort | None = None,
        cases_production_inputs: CasesProductionInputPort | None = None,
    ) -> None:
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
        self._cycle_state_root = infrastructure.due_cycle_state_root
        self._hkel_terminal_reference_issuance: dict[int, _HkelAttemptIssuance] = {}
        self._discovery_transport_for_endpoint = _patchright_transport_for_endpoint
        self._legislation_admitted_outcomes = legislation_admitted_outcomes
        self._legislation_production_inputs = legislation_production_inputs
        self._cases_production_inputs = cases_production_inputs

    @property
    def production_legislation_configured(self) -> bool:
        """Confirm the required local production-input port was concretely composed."""
        return self._legislation_production_inputs is not None and callable(
            getattr(self._legislation_production_inputs, "load", None)
        )

    @property
    def production_cases_configured(self) -> bool:
        """Confirm scheduled Cases work has one concrete worker-local input authority."""
        return self._cases_production_inputs is not None and callable(
            getattr(self._cases_production_inputs, "load", None)
        )

    def _hkel_member_snapshot(self, member: HkelEvidenceArtifact) -> str:
        """Fingerprint the complete primitive member/disposition facts for one attempt."""
        body = {
            "archive_member": member.archive_member,
            "artifact_id": member.artifact_id,
            "declared_sha256": member.declared_sha256,
            "endpoint_id": member.endpoint_id,
            "endpoint_version": member.endpoint_version,
            "instrument_id": member.instrument_id,
            "inventory_member_fingerprint": member.inventory_member_fingerprint,
            "language": member.language,
            "locator": member.locator,
            "resource_id": member.resource_id,
            "role": member.role.value,
            "source_disposition": member.source_disposition,
            "source_id": member.source_id,
            "status_signal": member.status_signal,
            "version_signal": member.version_signal,
        }
        return f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"

    def _begin_hkel_terminal_attempt(self, plan: HkelEvidencePlan) -> _HkelAttemptIssuance:
        """Create one unshareable worker-local authorization for this exact frozen plan."""
        try:
            plan.assert_factory_issued()
        except ValueError as error:
            _fail_pipeline("HKeL terminal attempt lost factory provenance", error)
        attempt = _HkelAttemptIssuance(
            plan.plan_fingerprint,
            tuple(
                (member.artifact_id, self._hkel_member_snapshot(member)) for member in plan.members
            ),
            set(),
            set(),
        )
        self._hkel_terminal_reference_issuance[id(attempt)] = attempt
        return attempt

    def _assert_hkel_terminal_attempt_fingerprint(self, attempt: _HkelAttemptIssuance) -> None:
        """Reject stale, swapped, or already-consumed short-lived attempt contexts."""
        if self._hkel_terminal_reference_issuance.get(id(attempt)) is not attempt:
            _fail_pipeline("HKeL terminal attempt issuance is absent or already consumed")

    def _assert_hkel_terminal_attempt(
        self,
        plan: HkelEvidencePlan,
        attempt: _HkelAttemptIssuance,
    ) -> None:
        """Require the exact frozen plan and all issued member snapshots to agree."""
        self._assert_hkel_terminal_attempt_fingerprint(attempt)
        if attempt.plan_fingerprint != plan.plan_fingerprint:
            _fail_pipeline("HKeL terminal attempt does not match the frozen plan")
        expected = tuple(
            (member.artifact_id, self._hkel_member_snapshot(member)) for member in plan.members
        )
        if attempt.member_snapshots != expected:
            _fail_pipeline("HKeL terminal attempt member snapshot drifted from the frozen plan")

    def _consume_hkel_terminal_attempt(self, attempt: _HkelAttemptIssuance) -> None:
        """Forget all per-attempt reference authority on every terminal or abort path."""
        if self._hkel_terminal_reference_issuance.get(id(attempt)) is attempt:
            del self._hkel_terminal_reference_issuance[id(attempt)]

    def _hkel_terminal_outcome_snapshot(self, outcome: dict[str, object]) -> str:
        """Fingerprint the same closed stable projection retained in the manifest."""
        stable = _stable_hkel_terminal_member_projection(outcome)
        return f"sha256:{sha256(canonicalize(checked_json_value(stable))).hexdigest()}"

    def _issue_hkel_terminal_outcome(
        self,
        member: HkelEvidenceArtifact,
        outcome: dict[str, object],
        attempt: _HkelAttemptIssuance,
    ) -> None:
        """Bind the exact worker-emitted terminal shape to this attempt once."""
        self._assert_hkel_terminal_attempt_fingerprint(attempt)
        if dict(attempt.member_snapshots).get(member.artifact_id) != self._hkel_member_snapshot(
            member
        ):
            _fail_pipeline("HKeL terminal attempt member snapshot drifted before outcome issuance")
        attempt.issued_outcomes.add(
            (member.artifact_id, self._hkel_terminal_outcome_snapshot(outcome))
        )

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

    def plan_hkel_evidence(self, _context: ActivityContext, payload: object) -> object:
        """Capture/parse the complete inventory and freeze one item plan before fetch."""
        instruction = HkelEvidencePlanningInstruction.from_json(payload)
        inventory = self._capture_current_hkel_inventory()
        try:
            projection = project_hkel_current_inventory(inventory, register=self._register)
            projection.assert_factory_issued()
            plan = build_hkel_evidence_plan_from_projection(
                projection,
                instrument_id=instruction.instrument_id,
                cutoff=instruction.observation_cutoff,
                register=self._register,
            )
        except (TypeError, ValueError) as error:
            _fail_pipeline("HKeL evidence plan is invalid before artifact transport", error)
        frozen_plan = self._retain_hkel_evidence_plan(plan, projection)
        return {
            "authentic_source_admitted": False,
            "expected_inventory_fingerprint": plan.inventory_fingerprint,
            "expected_plan_fingerprint": plan.plan_fingerprint,
            "instrument_id": plan.instrument_id,
            "observation_cutoff": plan.observation_cutoff,
            "plan_manifest": frozen_plan,
        }

    def capture_hkel_evidence(self, _context: ActivityContext, payload: object) -> object:
        """Capture only the exact members of a prior source-byte-derived plan."""
        instruction = HkelEvidenceInstruction.from_json(payload)
        inventory = self._capture_current_hkel_inventory()
        try:
            projection = project_hkel_current_inventory(inventory, register=self._register)
            projection.assert_factory_issued()
            plan = build_hkel_evidence_plan_from_projection(
                projection,
                instrument_id=instruction.instrument_id,
                cutoff=instruction.observation_cutoff,
                register=self._register,
            )
        except (TypeError, ValueError) as error:
            _fail_pipeline("HKeL evidence plan is invalid before artifact transport", error)
        if (
            plan.plan_fingerprint != instruction.expected_plan_fingerprint
            or plan.inventory_fingerprint != instruction.expected_inventory_fingerprint
        ):
            _fail_pipeline(
                "HKeL evidence inventory or frozen plan drifted before artifact transport"
            )
        try:
            plan.assert_factory_issued()
        except ValueError as error:
            _fail_pipeline("HKeL evidence plan lost factory provenance", error)
        attempt = self._begin_hkel_terminal_attempt(plan)
        try:
            outcomes = [
                self._capture_hkel_evidence_member(member, attempt) for member in plan.members
            ]
            complete = self._hkel_evidence_is_complete(plan, outcomes, attempt)
            manifest = self._retain_hkel_evidence_manifest(plan, outcomes, attempt)
        finally:
            self._consume_hkel_terminal_attempt(attempt)
        return {
            "code": "COMPLETE_CAPTURE" if complete else "PARTIAL_CAPTURE",
            "instrument_id": plan.instrument_id,
            "members": outcomes,
            "observation_cutoff": plan.observation_cutoff,
            "plan_fingerprint": plan.plan_fingerprint,
            "release_blocking": not complete,
            "source_inventory_fingerprint": plan.inventory_fingerprint,
            "terminal_manifest": manifest,
        }

    def _retain_hkel_evidence_plan(
        self,
        plan: HkelEvidencePlan,
        projection: HkelInventoryProjection,
    ) -> dict[str, object]:
        """Persist a self-reproducing frozen plan after its complete inventory parse."""
        try:
            projection.assert_factory_issued()
            plan.assert_factory_issued()
        except ValueError as error:
            _fail_pipeline("HKeL evidence plan lost factory provenance", error)
        body = canonicalize(
            checked_json_value(
                {
                    "authentic_source_admitted": projection.authentic_source_admitted,
                    "instrument_id": plan.instrument_id,
                    "inventory_fingerprint": plan.inventory_fingerprint,
                    "members": [
                        {
                            "archive_member": member.archive_member,
                            "artifact_id": member.artifact_id,
                            "declared_sha256": member.declared_sha256,
                            "endpoint_id": member.endpoint_id,
                            "endpoint_version": member.endpoint_version,
                            "inventory_member_fingerprint": member.inventory_member_fingerprint,
                            "instrument_id": member.instrument_id,
                            "language": member.language,
                            "locator": member.locator,
                            "resource_id": member.resource_id,
                            "role": member.role.value,
                            "source_id": member.source_id,
                            "source_disposition": member.source_disposition,
                            "status_signal": member.status_signal,
                            "version_signal": member.version_signal,
                        }
                        for member in plan.members
                    ],
                    "missing_member_ids": list(plan.missing_member_ids),
                    "observation_cutoff": plan.observation_cutoff,
                    "parser_profile": projection.profile.value,
                    "projection_fingerprint": plan.projection_fingerprint,
                    "plan_fingerprint": plan.plan_fingerprint,
                    "schema_id": "asklegal.hkel-evidence-plan",
                    "schema_version": "1.0.0",
                    "source_register_fingerprint": plan.source_register_fingerprint,
                    "source_register_id": plan.source_register_id,
                }
            )
        )
        logical_key = (
            f"poc/report/hkel-evidence-plan/{plan.instrument_id}/"
            f"{plan.plan_fingerprint.removeprefix('sha256:')}"
        )
        receipt = self._vault.conditional_create(
            logical_key,
            body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        if receipt.read_back_verified is not True:
            _fail_pipeline("HKeL frozen plan did not verify immutable read-back")
        return {
            "byte_length": len(body),
            "created": receipt.created,
            "fingerprint": f"sha256:{sha256(body).hexdigest()}",
            "logical_key": logical_key,
            "read_back_verified": receipt.read_back_verified,
            "version_id": receipt.reference.version_id,
        }

    def _capture_current_hkel_inventory(self) -> OfficialInventoryResult:
        """Obtain the complete current inventory before touching an item artifact."""
        endpoint_versions = tuple(
            sorted(
                (endpoint.endpoint_id, endpoint.version)
                for endpoint in self._register.endpoints
                if endpoint.source_id == _CURRENT_INVENTORY_SOURCE_ID
                and endpoint.complete_inventory_required
            )
        )
        if not endpoint_versions:
            _fail_pipeline("current HKeL inventory declares no complete endpoint set")
        return OfficialInventoryConnector(self._connector).capture(
            OfficialInventoryRequest(
                _CURRENT_INVENTORY_SOURCE_ID,
                endpoint_versions,
                (),
                official_observation_profile(
                    self._register,
                    _CURRENT_INVENTORY_SOURCE_ID,
                ).timeout_seconds,
            )
        )

    def _capture_hkel_evidence_member(
        self,
        member: HkelEvidenceArtifact,
        attempt: _HkelAttemptIssuance,
    ) -> dict[str, object]:
        """Fetch one already validated direct member or account for its unavailable procedure."""
        if member.source_disposition == "NOT_PUBLISHED":
            outcome = _hkel_terminal_member_projection(
                member,
                code=member.source_disposition,
                evidence=None,
                failure_code=None,
                isolated_response=None,
            )
            self._issue_hkel_terminal_outcome(member, outcome, attempt)
            return outcome
        if member.source_disposition == "PROCEDURE_NOT_ADMITTED":
            outcome = _hkel_terminal_member_projection(
                member,
                code="SOURCE_UNAVAILABLE",
                evidence=None,
                failure_code="REGISTERED_PROCEDURE_NOT_ENABLED",
                isolated_response=None,
            )
            self._issue_hkel_terminal_outcome(member, outcome, attempt)
            return outcome
        endpoint = self._endpoints[member.endpoint_id]
        if endpoint.access_mode is not EndpointAccessMode.DIRECT_HTTP or not endpoint.enabled:
            outcome = _hkel_terminal_member_projection(
                member,
                code="SOURCE_UNAVAILABLE",
                evidence=None,
                failure_code="REGISTERED_PROCEDURE_NOT_ENABLED",
                isolated_response=None,
            )
            self._issue_hkel_terminal_outcome(member, outcome, attempt)
            return outcome
        substitutions: tuple[tuple[str, str], ...] = ()
        if member.locator is not None:
            placeholders = re.findall(r"\{([a-z][a-z0-9_]*)\}", endpoint.url)
            if len(placeholders) != 1:
                _fail_pipeline("validated HKeL artifact endpoint lost its locator contract")
            substitutions = ((placeholders[0], member.locator),)
        result = self._connector.fetch(
            OfficialFetchRequest(
                member.endpoint_id,
                member.endpoint_version,
                HttpMethod.GET,
                None,
                official_observation_profile(self._register, member.source_id).timeout_seconds,
                substitutions,
            )
        )
        if result.code in _CAPTURED_FETCH_CODES and member.archive_member is not None:
            try:
                _validate_hkel_archive_member(member, result)
            except ValueError:
                result = replace(
                    result,
                    code=OfficialFetchCode.SOURCE_CONTRACT_CHANGED,
                    fingerprint=None,
                    classification=None,
                    failure_code="HKEL_ARCHIVE_MEMBER_DECLARATION_MISMATCH",
                )
        retained = self._retain_inventory_member(result)
        return self._hkel_terminal_capture_outcome(member, result, retained, attempt)

    def _hkel_terminal_capture_outcome(
        self,
        member: HkelEvidenceArtifact,
        result: OfficialFetchResult,
        retained: tuple[dict[str, object] | None, dict[str, object] | None],
        attempt: _HkelAttemptIssuance,
    ) -> dict[str, object]:
        """Issue worker-owned storage provenance before emitting one capture disposition."""
        evidence, isolated = retained
        if result.code is OfficialFetchCode.SOURCE_UNAVAILABLE and isolated is not None:
            _fail_pipeline("source-unavailable HKeL fetch cannot retain an isolation response")
        if result.code in {
            OfficialFetchCode.SOURCE_CONTRACT_CHANGED,
            OfficialFetchCode.UNSAFE_RESPONSE,
        } and bool(result.body) != (isolated is not None):
            _fail_pipeline(
                "response-bearing HKeL failure must retain one issued isolation response"
            )
        if evidence is not None and evidence["read_back_verified"] is not True:
            _fail_pipeline("HKeL artifact retention did not verify immutable read-back")
        if evidence is not None:
            self._issue_hkel_terminal_reference(member, evidence, "evidence", attempt)
        if isolated is not None:
            self._issue_hkel_terminal_reference(member, isolated, "isolation", attempt)
        outcome = _hkel_terminal_member_projection(
            member,
            code=result.code.value,
            evidence=evidence,
            failure_code=result.failure_code,
            isolated_response=isolated,
        )
        self._issue_hkel_terminal_outcome(member, outcome, attempt)
        return outcome

    def _validated_hkel_evidence_outcomes(
        self,
        plan: HkelEvidencePlan,
        outcomes: list[dict[str, object]],
        attempt: _HkelAttemptIssuance,
    ) -> None:
        """Require one exact terminal disposition for every frozen planned member."""
        try:
            plan.assert_factory_issued()
        except ValueError as error:
            _fail_pipeline("HKeL terminal outcomes lost factory provenance", error)
        if type(outcomes) is not list:
            _fail_pipeline("HKeL terminal outcomes must be one exact list")
        planned = {member.artifact_id: member for member in plan.members}
        if len(outcomes) != len(planned):
            _fail_pipeline("HKeL terminal outcomes do not account for every planned member")
        observed: set[str] = set()
        seen_references: set[ExactObjectReference] = set()
        for outcome in outcomes:
            if type(outcome) is not dict:
                _fail_pipeline("HKeL terminal outcomes must contain exact objects")
            _validate_hkel_terminal_outcome(
                planned,
                outcome,
                observed,
                seen_references,
                lambda value, member, storage_kind: self._validated_hkel_storage_reference(
                    value, member, storage_kind, plan, attempt
                ),
            )
            self._assert_hkel_terminal_attempt(plan, attempt)
            if (
                outcome["artifact_id"],
                self._hkel_terminal_outcome_snapshot(outcome),
            ) not in attempt.issued_outcomes:
                _fail_pipeline("HKeL terminal outcome was not issued for this attempt")
        if observed != set(planned):
            _fail_pipeline("HKeL terminal outcomes do not account for every planned member")

    def _validated_hkel_storage_reference(
        self,
        value: object,
        member: HkelEvidenceArtifact,
        storage_kind: str,
        plan: HkelEvidencePlan,
        attempt: _HkelAttemptIssuance,
    ) -> ExactObjectReference:
        """Prove one outcome reference names the exact readable retained bytes."""
        reference = self._read_verified_hkel_storage_reference(value, member, storage_kind)
        self._assert_hkel_terminal_attempt(plan, attempt)
        member_snapshot = self._hkel_member_snapshot(member)
        if (
            member.artifact_id,
            member_snapshot,
            storage_kind,
            reference,
        ) not in attempt.issued_references:
            _fail_pipeline("HKeL retained storage reference was not issued for this member")
        return reference

    def _issue_hkel_terminal_reference(
        self,
        member: HkelEvidenceArtifact,
        value: object,
        storage_kind: str,
        attempt: _HkelAttemptIssuance,
    ) -> None:
        """Bind one worker-produced receipt to its exact planned terminal member."""
        reference = self._read_verified_hkel_storage_reference(value, member, storage_kind)
        self._assert_hkel_terminal_attempt_fingerprint(attempt)
        member_snapshot = self._hkel_member_snapshot(member)
        if dict(attempt.member_snapshots).get(member.artifact_id) != member_snapshot:
            _fail_pipeline("HKeL terminal attempt member snapshot drifted before issuance")
        attempt.issued_references.add(
            (member.artifact_id, member_snapshot, storage_kind, reference)
        )

    def _read_verified_hkel_storage_reference(
        self,
        value: object,
        member: HkelEvidenceArtifact,
        storage_kind: str,
    ) -> ExactObjectReference:
        """Read a primary-vault object and reproduce its exact content identity."""
        if storage_kind not in {"evidence", "isolation"}:
            _fail_pipeline("HKeL storage reference has an unknown terminal kind")
        try:
            reference = _hkel_storage_reference_from_json(value)
        except ValueError as error:
            _fail_pipeline("HKeL retained storage reference is invalid", error)
        if reference.vault is not self._vault.vault_name:
            _fail_pipeline("HKeL retained storage reference is outside the primary vault")
        prefix = (
            f"poc/isolation/source-response/{member.endpoint_id}/"
            if storage_kind == "isolation"
            else f"poc/source/inventory/{member.endpoint_id}/"
        )
        expected_key = f"{prefix}{reference.fingerprint.removeprefix('sha256:')}"
        if reference.logical_key != expected_key:
            _fail_pipeline("HKeL retained storage reference is not bound to its planned member")
        try:
            content = self._vault.read_exact(reference)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            _fail_pipeline("HKeL retained storage object is unavailable", error)
        if type(content) is not bytes or not content:
            _fail_pipeline("HKeL retained storage object has invalid exact bytes")
        if len(content) != reference.byte_length or (
            f"sha256:{sha256(content).hexdigest()}" != reference.fingerprint
        ):
            _fail_pipeline("HKeL retained storage object does not match its exact reference")
        return reference

    def _hkel_evidence_is_complete(
        self,
        plan: HkelEvidencePlan,
        outcomes: list[dict[str, object]],
        attempt: _HkelAttemptIssuance,
    ) -> bool:
        """Derive completion from validated terminal dispositions, never a caller flag."""
        self._validated_hkel_evidence_outcomes(plan, outcomes, attempt)
        if plan.release_blocking:
            return False
        return all(
            outcome["code"] in {item.value for item in _CAPTURED_FETCH_CODES}
            or outcome["code"] == "NOT_PUBLISHED"
            for outcome in outcomes
        )

    def _retain_hkel_evidence_manifest(
        self,
        plan: HkelEvidencePlan,
        outcomes: list[dict[str, object]],
        attempt: _HkelAttemptIssuance,
    ) -> dict[str, object]:
        """Write terminal HKeL accounting only after every planned member resolves."""
        try:
            complete = self._hkel_evidence_is_complete(plan, outcomes, attempt)
            body = canonicalize(
                checked_json_value(
                    {
                        "complete": complete,
                        "instrument_id": plan.instrument_id,
                        "members": [
                            _stable_hkel_terminal_member_projection(outcome) for outcome in outcomes
                        ],
                        "observation_cutoff": plan.observation_cutoff,
                        "plan_fingerprint": plan.plan_fingerprint,
                        "release_blocking": not complete,
                        "schema_id": "asklegal.hkel-evidence-attempt",
                        "schema_version": "1.0.0",
                        "source_inventory_fingerprint": plan.inventory_fingerprint,
                        "source_register_fingerprint": plan.source_register_fingerprint,
                    }
                )
            )
            fingerprint = f"sha256:{sha256(body).hexdigest()}"
            logical_key = (
                f"{_HKEL_EVIDENCE_MANIFEST_PREFIX}/{plan.instrument_id}/"
                f"{fingerprint.removeprefix('sha256:')}"
            )
            receipt = self._vault.conditional_create(
                logical_key,
                body,
                RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
            )
            if receipt.read_back_verified is not True:
                _fail_pipeline("HKeL terminal manifest did not verify immutable read-back")
            return {
                "byte_length": len(body),
                "created": receipt.created,
                "fingerprint": fingerprint,
                "logical_key": logical_key,
                "read_back_verified": receipt.read_back_verified,
                "version_id": receipt.reference.version_id,
            }
        finally:
            self._consume_hkel_terminal_attempt(attempt)

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
                    "vault": receipt.reference.vault.value,
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
            "vault": receipt.reference.vault.value,
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

    def capture_legislation_work(self, node: LegislationWorkNode) -> CaptureOutcome:
        """Capture one already revalidated graph node or return a closed no-call result."""
        item = node.scheduled.identity
        admitted_outcomes = getattr(self, "_legislation_admitted_outcomes", None)
        if admitted_outcomes is not None:
            outcome = admitted_outcomes.capture(node)
            if type(outcome) is not CaptureOutcome or outcome.work_item_id != item.work_item_id:
                message = "admitted legislation outcome does not match graph node"
                raise AcquisitionPipelineError(message)
            return outcome
        if node.kind in {
            LegislationWorkKind.GLD_ISSUE_DISCOVERY,
            LegislationWorkKind.GLD_EVENT_ARTIFACT,
        }:
            # The GLD browser compartment remains the sole owner of those two roles.
            # Its current V1 service composition has no admitted exchange parser, so the
            # shared runner journals a retryable session result rather than bypassing it.
            code = "GLD_CHALLENGE_UNRESOLVED"
            raise GldSessionError(code)
        endpoint = self._endpoints.get(node.endpoint_id)
        if (
            endpoint is None
            or endpoint.source_id != node.source_id
            or endpoint.version != item.procedure_version
            or not endpoint.enabled
            or endpoint.access_mode is not EndpointAccessMode.DIRECT_HTTP
            or "{" in endpoint.url
            or endpoint.url != item.locator
        ):
            return CaptureOutcome(
                work_item_id=item.work_item_id,
                transition=JournalTransition.CONTRACT_REJECTED,
                status_code=None,
                media_type=None,
                final_url=None,
                body_length=0,
                body_fingerprint=None,
                object_ref=None,
                failure_code=AcquisitionFailureCode.SOURCE_CONTRACT_CHANGED.value,
                retry_not_before=None,
                read_back_verified=False,
                redirect_chain=(),
            )
        result = self._connector.fetch(
            OfficialFetchRequest(
                endpoint.endpoint_id,
                endpoint.version,
                HttpMethod.GET,
                None,
                official_observation_profile(self._register, endpoint.source_id).timeout_seconds,
            )
        )
        if result.failure_code is not None:
            retryable = result.code is OfficialFetchCode.SOURCE_UNAVAILABLE
            return CaptureOutcome(
                work_item_id=item.work_item_id,
                transition=(
                    JournalTransition.RETRYABLE_FAILURE
                    if retryable
                    else JournalTransition.CONTRACT_REJECTED
                ),
                status_code=None,
                media_type=None,
                final_url=None,
                body_length=0,
                body_fingerprint=None,
                object_ref=None,
                failure_code=(
                    AcquisitionFailureCode.SOURCE_UNAVAILABLE.value
                    if retryable
                    else AcquisitionFailureCode.SOURCE_CONTRACT_CHANGED.value
                ),
                retry_not_before=(
                    datetime.now(tz=UTC).replace(microsecond=0).isoformat() if retryable else None
                ),
                read_back_verified=False,
                redirect_chain=(),
            )
        response = result.transport_response
        if (
            response is None
            or result.fingerprint is None
            or result.media_type is None
            or result.classification is None
            or not result.classification.admitted
        ):
            return CaptureOutcome(
                work_item_id=item.work_item_id,
                transition=JournalTransition.CONTRACT_REJECTED,
                status_code=None,
                media_type=None,
                final_url=None,
                body_length=0,
                body_fingerprint=None,
                object_ref=None,
                failure_code=AcquisitionFailureCode.SOURCE_CONTRACT_CHANGED.value,
                retry_not_before=None,
                read_back_verified=False,
                redirect_chain=(),
            )
        logical_key = (
            f"poc/source/{endpoint.endpoint_id}/{result.fingerprint.removeprefix('sha256:')}"
        )
        receipt = self._vault.conditional_create(
            logical_key,
            result.body,
            RetentionProfile(_RETENTION_PROFILE, _RETENTION_UNTIL),
        )
        return CaptureOutcome(
            work_item_id=item.work_item_id,
            transition=JournalTransition.CAPTURED_VERIFIED,
            status_code=response.status_code,
            media_type=result.media_type,
            final_url=response.final_url,
            body_length=len(result.body),
            body_fingerprint=result.fingerprint,
            object_ref=logical_key,
            failure_code=None,
            retry_not_before=None,
            read_back_verified=receipt.read_back_verified,
            redirect_chain=(),
        )

    def run_resumable_acquisition(  # noqa: C901 - one fail-closed production composition.
        self,
        _context: ActivityContext,
        payload: object,
    ) -> object:
        """Retain the generic Cases entry without accepting serialized Legislation."""
        try:
            document = checked_json_value(payload)
        except ContractViolation as error:
            message = "resumable acquisition payload is invalid"
            raise AcquisitionPipelineError(message) from error
        if type(document) is not dict or not _is_cases_resumable_instruction(document):
            message = "resumable acquisition payload is invalid"
            raise AcquisitionPipelineError(message)
        cycle_id = document["cycle_id"]
        work_graph_ref = document["work_graph_ref"]
        if type(cycle_id) is not str or type(work_graph_ref) is not str:
            message = "resumable acquisition payload is invalid"
            raise AcquisitionPipelineError(message)
        if self._cases_production_inputs is None:
            message = "Cases production inputs are not configured"
            raise AcquisitionPipelineError(message)
        try:
            inputs = self._cases_production_inputs.load(cycle_id, work_graph_ref)
            if type(inputs) is not CasesProductionCycleInputs:
                _cases_inputs_invalid()
            _validate_cases_shared_inputs(inputs)
            inputs.retained_receipt.assert_factory_issued()
            retained_prefix = retained_judiciary_prefix_from_receipt(
                inputs.retained_receipt, inputs.retained_evidence_reader
            )
            if inputs.cycle_mode is CasesCycleMode.FULL_RECONCILIATION:
                year, page = retained_prefix.last_listing
                successor_locator = build_judiciary_year_result_url(
                    inputs.advanced_search_form_body,
                    entry_url=inputs.advanced_search_entry_url,
                    year=year,
                    page=page + 1,
                    contract_version=inputs.form_contract_version,
                )
                plan = build_cases_baseline_plan(
                    retained_prefix=retained_prefix,
                    cycle_id=cycle_id,
                    successor_locator=successor_locator,
                    observation_cutoff=inputs.observation_cutoff,
                )
                _validate_cases_current_form(inputs, retained_prefix, plan)
                graph = build_cases_work_graph(
                    cycle_id=cycle_id,
                    observation_cutoff=inputs.observation_cutoff,
                    retained_prefix=retained_prefix,
                    locator_for_year_page=lambda year, page: build_judiciary_year_result_url(
                        inputs.advanced_search_form_body,
                        entry_url=inputs.advanced_search_entry_url,
                        year=year,
                        page=page,
                        contract_version=inputs.form_contract_version,
                    ),
                )
                observations = build_cases_observation_graph(
                    cycle_id=cycle_id,
                    observation_cutoff=inputs.observation_cutoff,
                )
                graph = CasesWorkGraph(
                    graph.cycle_id,
                    graph.observation_cutoff,
                    (*graph.nodes, *observations.nodes),
                    graph.occurrences,
                    graph.mode,
                    graph.reconciled_partitions,
                    graph.reconciliation_failures,
                )
            else:
                if inputs.cycle_mode is not CasesCycleMode.INCREMENTAL_DISCOVERY:
                    _cases_inputs_invalid()
                _validate_cases_shared_inputs(inputs)
                graph = build_cases_observation_graph(
                    cycle_id=cycle_id, observation_cutoff=inputs.observation_cutoff
                )
            while True:
                report = run_cases_resumable_graph(
                    state_root=self._cycle_state_root,
                    graph=graph,
                    retained_prefix=retained_prefix,
                    transport=inputs.transport,
                    retained_verifier=inputs.retained_verifier,
                    clock=inputs.clock,
                    sleeper=inputs.sleeper,
                    budget=inputs.budget,
                )
                expanded = (
                    expand_cases_graph_from_verified_listings(
                        graph=graph,
                        report=report,
                        reader=inputs.verified_capture_reader,
                        contract_version=inputs.form_contract_version,
                    )
                    if graph.mode is CasesCycleMode.FULL_RECONCILIATION
                    else expand_cases_graph_from_verified_observations(
                        graph=graph,
                        report=report,
                        reader=inputs.verified_capture_reader,
                    )
                )
                if expanded == graph:
                    break
                graph = expanded
            bundle_refs = persist_verified_cases_judgment_bundles(
                state_root=self._cycle_state_root,
                graph=graph,
                report=report,
                store=inputs.judgment_bundle_store,
            )
            manifest = project_cases_manifest_from_runner(
                graph=graph,
                report=report,
                discrepancy_refs=inputs.discrepancy_refs,
                judgment_bundle_refs=bundle_refs,
                accepted_predecessor=inputs.accepted_predecessor,
            )
        except (AttributeError, TypeError, ValueError) as error:
            message = "Cases production inputs are invalid"
            raise AcquisitionPipelineError(message) from error
        return canonicalize(checked_json_value(manifest.to_json()))

    def run_legislation_acquisition(
        self,
        _context: ActivityContext,
        payload: object,
    ) -> bytes:
        """Bind live Task 4 evidence and emit one canonical legislation manifest."""
        invalid = "legislation acquisition payload is invalid"
        try:
            document = checked_json_value(payload)
        except ContractViolation as error:
            raise AcquisitionPipelineError(invalid) from error
        if (
            type(document) is not dict
            or set(document)
            != {
                "source_family",
                "cycle_id",
                "observation_cutoff",
                "budget",
            }
            or document["source_family"] != "LEGISLATION"
        ):
            raise AcquisitionPipelineError(invalid)
        cycle_id = document["cycle_id"]
        cutoff = document["observation_cutoff"]
        budget_payload = document["budget"]
        if (
            type(cycle_id) is not str
            or type(cutoff) is not str
            or type(budget_payload) is not dict
            or set(budget_payload)
            != {
                "maximum_starts",
                "maximum_retained_bytes",
                "maximum_elapsed_seconds",
                "maximum_redirects",
            }
            or self._legislation_production_inputs is None
        ):
            raise AcquisitionPipelineError(invalid)
        maximum_starts = budget_payload["maximum_starts"]
        maximum_retained_bytes = budget_payload["maximum_retained_bytes"]
        maximum_elapsed_seconds = budget_payload["maximum_elapsed_seconds"]
        maximum_redirects = budget_payload["maximum_redirects"]
        if (
            type(maximum_starts) is not int
            or type(maximum_retained_bytes) is not int
            or type(maximum_elapsed_seconds) is not int
            or type(maximum_redirects) is not int
        ):
            raise AcquisitionPipelineError(invalid)
        try:
            inputs = self._legislation_production_inputs.load(cycle_id, cutoff)
            if type(inputs) is not LegislationProductionCycleInputs:
                raise AcquisitionPipelineError(invalid)
            baseline = inputs.baseline or bind_imported_hkel_baseline(
                inputs.retained_receipt,
                inputs.retained_report,
                inputs.admission_document,
            )
            graph = build_legislation_work_graph(
                cycle_id,
                cutoff,
                registered_legislation_work_seeds(inputs.gld_window),
            )
            budget = CycleBudget(
                maximum_starts,
                maximum_retained_bytes,
                maximum_elapsed_seconds,
                maximum_redirects,
            )
            clock = _SystemAcquisitionClock()
            cycle = run_legislation_acquisition_cycle(
                state_root=self._cycle_state_root,
                graph=graph,
                transport=V1LegislationTransport(self, graph),
                retained_verifier=_PrimaryVaultRetainedVerifier(self._vault),
                clock=clock,
                sleeper=time.sleep,
                budget=budget,
                baseline=baseline,
                archive_admission=inputs.archive_admission,
                review_issue_refs=inputs.review_issue_refs,
                previous=inputs.previous,
                observed_archive_reuse_keys=inputs.observed_archive_reuse_keys,
            )
            recorder = getattr(
                self._legislation_production_inputs,
                "record_completed_cycle",
                None,
            )
            if callable(recorder):
                recorder(cycle)
        except (KeyError, TypeError, ValueError) as error:
            raise AcquisitionPipelineError(invalid) from error
        return canonicalize(cycle.manifest.to_json())


def acquire_endpoint(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Orchestrate one capture, keeping the document body out of the history."""
    captured = yield context.call_activity("capture_endpoint", input=payload)
    return captured


def acquire_resumable_source_cycle(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Dispatch only exact Cases-generic or Legislation-production instructions."""
    invalid = "RESUMABLE_SOURCE_CYCLE_INSTRUCTION_INVALID"
    try:
        document = checked_json_value(payload)
    except ContractViolation as error:
        raise AcquisitionPipelineError(invalid) from error
    if type(document) is not dict:
        raise AcquisitionPipelineError(invalid)
    if _is_cases_resumable_instruction(document):
        activity = "run_resumable_acquisition"
    elif _is_legislation_production_instruction(document):
        activity = "run_legislation_acquisition"
    else:
        raise AcquisitionPipelineError(invalid)
    captured = yield context.call_activity(activity, input=payload)
    return captured


def _is_cases_resumable_instruction(document: dict[str, JsonValue]) -> bool:
    """Recognize the exact current Cases shared-runner instruction schema."""
    return (
        set(document)
        == {"schema_id", "schema_version", "source_family", "cycle_id", "work_graph_ref"}
        and document["schema_id"] == _CASES_INSTRUCTION_SCHEMA
        and document["schema_version"] == _CASES_INSTRUCTION_VERSION
        and document["source_family"] == "CASES"
        and type(document["cycle_id"]) is str
        and _CASES_CYCLE.fullmatch(document["cycle_id"]) is not None
        and type(document["work_graph_ref"]) is str
        and bool(document["work_graph_ref"])
    )


def _is_legislation_production_instruction(document: dict[str, JsonValue]) -> bool:
    """Recognize the exact replay-safe Legislation instruction before dispatch."""
    if (
        set(document) != {"source_family", "cycle_id", "observation_cutoff", "budget"}
        or document["source_family"] != "LEGISLATION"
        or type(document["cycle_id"]) is not str
        or not document["cycle_id"]
        or type(document["observation_cutoff"]) is not str
        or not document["observation_cutoff"]
    ):
        return False
    budget = document["budget"]
    return (
        type(budget) is dict
        and set(budget)
        == {
            "maximum_starts",
            "maximum_retained_bytes",
            "maximum_elapsed_seconds",
            "maximum_redirects",
        }
        and all(type(value) is int and value >= 0 for value in budget.values())
    )


def prepare_legislation_resumable_cycle(
    cycle_id: str,
    observation_cutoff: str,
    gld_window: object,
) -> LegislationWorkGraph:
    """Project GLD discoveries and registered sources into the shared-runner graph."""
    return build_legislation_work_graph(
        cycle_id,
        observation_cutoff,
        registered_legislation_work_seeds(gld_window),
    )


def import_frozen_two_family_evidence(
    cycle_state_root: Path,
    *,
    source_admission_root: Path | None = None,
) -> KnownV1RetainedImportReceipts:
    """Compose the zero-transport import of the selected V1 retained baselines."""
    return import_known_v1_retained_evidence(
        cycle_state_root,
        source_admission_root=source_admission_root,
    )


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


def build_activities(  # noqa: PLR0913
    infrastructure: V1AcquisitionInfrastructure,
    environment: Mapping[str, str],
    *,
    legislation_admitted_outcomes: LegislationAdmittedOutcomePort | None = None,
    legislation_production_inputs: LegislationProductionInputPort | None = None,
    cases_production_inputs: CasesProductionInputPort | None = None,
    gld_window_provider: GldWindowProvider | None = None,
) -> AcquisitionActivities:
    """Compose this worker's activities from its own infrastructure."""
    explicit_family_port = (
        legislation_production_inputs is not None or cases_production_inputs is not None
    )
    production_inputs = legislation_production_inputs
    if production_inputs is None and (not explicit_family_port or gld_window_provider is not None):
        effective_gld_provider = gld_window_provider
        if effective_gld_provider is None:
            host, port = _proxy(infrastructure)
            effective_gld_provider = build_gld_window_provider(
                environment, host, port, infrastructure.primary_vault
            )
        production_inputs = LocalLegislationProductionInputs(
            infrastructure, environment, gld_window_provider=effective_gld_provider
        )
    production_cases_inputs = cases_production_inputs
    if production_cases_inputs is None and not explicit_family_port:
        production_cases_inputs = LocalCasesProductionInputs(infrastructure, environment)
    return AcquisitionActivities(
        infrastructure,
        legislation_admitted_outcomes=legislation_admitted_outcomes,
        legislation_production_inputs=production_inputs,
        cases_production_inputs=production_cases_inputs,
    )


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


def acquire_hkel_evidence(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, object]:
    """Freeze a source-byte-derived plan, then capture exactly that frozen plan."""
    planning = HkelEvidencePlanningInstruction.from_json(payload)
    plan_payload = {
        "instrument_id": planning.instrument_id,
        "observation_cutoff": planning.observation_cutoff,
    }
    planned = yield context.call_activity("plan_hkel_evidence", input=plan_payload)
    try:
        document = checked_json_value(planned)
    except ContractViolation as error:
        _fail_pipeline("HKeL evidence plan result must contain exact JSON", error)
    if not isinstance(document, dict) or set(document) != {
        "authentic_source_admitted",
        "expected_inventory_fingerprint",
        "expected_plan_fingerprint",
        "instrument_id",
        "observation_cutoff",
        "plan_manifest",
    }:
        _fail_pipeline("HKeL evidence plan result has missing or unknown fields")
    if document["authentic_source_admitted"] is not False:
        _fail_pipeline("candidate HKeL plan cannot claim authentic source admission")
    capture_payload = {
        "instrument_id": document["instrument_id"],
        "observation_cutoff": document["observation_cutoff"],
        "expected_plan_fingerprint": document["expected_plan_fingerprint"],
        "expected_inventory_fingerprint": document["expected_inventory_fingerprint"],
    }
    HkelEvidenceInstruction.from_json(capture_payload)
    captured = yield context.call_activity("capture_hkel_evidence", input=capture_payload)
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
