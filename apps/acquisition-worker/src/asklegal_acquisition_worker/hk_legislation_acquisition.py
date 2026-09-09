"""Resumable legislation-family work graph and complete-input projection.

This module owns acquisition accounting only.  It binds safe retained HKeL
admission facts and ordinary journal outcomes, but never decides legal effect.
"""

from __future__ import annotations

import re
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Literal, Never, Protocol, TypeIs
from urllib.parse import urlsplit

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_management_register_ports import (
    AcquisitionObservationRecord,
    AcquisitionRegisterStore,
)
from asklegal_source_connectors import (
    GldGazetteClass,
    GldGazetteEntry,
    GldGazetteIssueKind,
    GldGazetteWindow,
    HkelArchiveReuseKey,
    assert_gld_gazette_window_issued,
    load_hk_legislation_source_register,
    project_gld_artifact_requests,
    select_hkel_archives_to_reparse,
)

from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionCycleResult,
    AcquisitionFailureCode,
    CheckpointItem,
    ImportedCaptureVerifiedPayload,
    JournalTransition,
    LocalAcquisitionJournal,
    WorkItemIdentity,
)
from asklegal_acquisition_worker.gld_session import (
    GldSessionError,
    GldSessionFailureClass,
    classify_gld_session_failure,
)
from asklegal_acquisition_worker.resumable_acquisition import (
    AcquisitionClock,
    AcquisitionCycleReport,
    CaptureOutcome,
    CaptureTransport,
    CycleBudget,
    ResumableAcquisitionRunner,
    RetainedObjectVerifier,
    ScheduledWorkItem,
    VerifiedCaptureBinding,
    runner_verified_capture_bindings,
)
from asklegal_acquisition_worker.retained_evidence_import import (
    RetainedImportReceipt,
)
from asklegal_acquisition_worker.source_role_evidence import (
    SourceRoleDisposition,
    validate_source_role_dispositions,
)

LEGISLATION_SCOPE_IDS = (
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_SCHEMA_ID = "asklegal.legislation-acquisition-manifest"
_SCHEMA_VERSION = "1.0.0"
_ADMISSION_SCHEMA_ID = "asklegal.hkel-authentic-admission"
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{2,159}$")
_SOURCE_ROLE = re.compile(r"^[A-Z][A-Z0-9_]{2,159}$")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{2,1023}$")
_CYCLE = re.compile(r"^cyc_[A-Za-z0-9_-]{3,123}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")
_MAX_OBJECT_BYTES = 1_073_741_824
_REFERENCE_PARTS = 3
_PRIORITY_PARTS = 3
_SHA256_HEX_LENGTH = 64
_EXPECTED_ENDPOINTS = 56
_EXPECTED_ARCHIVE_MEMBERS = 12_858
_EXPECTED_BILINGUAL_PAIRS = 3_157
_EXPECTED_SPECIFICATIONS = 7
_EXPECTED_ARCHIVES = 12
_KNOWN_HKEL_REPORT_FINGERPRINT = (
    "sha256:5f6b8625fd7c0ff4093d96b7a2f72e4ededc9b8af54b6c1add02b95e81549b50"
)
_KNOWN_HKEL_SEMANTIC_PROOF = (
    "sha256:fd47b7694ecd923242d823969c9b90271e047f44298224a4995988bbce6c4016"
)
_KNOWN_HKEL_REUSED_BYTES = 2_892_060_128
_KNOWN_HKEL_IMPORT_CYCLE = "cyc_20260903_import_hkel"
_KNOWN_HKEL_ATTEMPT = "hkel-live-baseline-basic-law20-20260828b"
_KNOWN_HKEL_SOURCE_OBSERVATION = (
    "sha256:c5c6fd784c7b96f11c77b99e52090bd9b7afd45a27d1df1faacfac98ca822309"
)
_KNOWN_HKEL_STRUCTURE_PROFILE = (
    "sha256:bf44b850d30b0521b1a915f1399915e2aab169dcae5204c8ab5587d6c5a7891f"
)
_KNOWN_HKEL_OBSERVATION_CUTOFF = "2026-08-28T22:20:23+08:00"
_KNOWN_HKEL_PUBLICATION_PROFILE = (
    "sha256:747c168d4bd8a3836f4c95b541a3d203d120d579102bcbfffc254e30a9585737"
)
_KNOWN_HKEL_ARCHIVE_FINGERPRINTS = (
    "sha256:7d12582cd93cba2bee8cf89c18dc56941cc626d3b5a5bf380bf711db13be602c",
    "sha256:2375d1215006a98549942c30581cf7a01749e9018aa44e017891df5ba049601c",
    "sha256:6714d98b5ed219b20706a40c55d71a332eb4757db21e99ca13096f856fdb88eb",
    "sha256:51a4d2f38e2d025df4ae2e96292caf8e6fe7b93b7eba7514bf8b8a9d81271b26",
    "sha256:796e5272b25dcc1f92c40dd3c0a778432f7b173550c1c3dca49050c57f308bb0",
    "sha256:014f9dfa8893a69949f1e4c1493b7fd9cd9904ff27e3b68b92251be6e6009fa9",
    "sha256:c1a9b59d15949c45752cb529d0e0e9215ededc88a049447478cc4db413d1379b",
    "sha256:85ed0a7ec778f2ce89e7b99393b96839a8ca96b1a6ec4f257529059ccab8d85d",
    "sha256:8cf813e8ce7f5039424ec6dc4043635ae0a807d48a9a0bdab6987f640c27e615",
    "sha256:8b87db9f64d39d0928902be3362f072a79e06b586f5b2b1fdef606cea6c6957b",
    "sha256:66a216c5d013c9d3cb0745b3eead87aab2a20f6754f4011f0b9436a33d56c94b",
    "sha256:da12d0791a9a9573b91a86cebe6c9d25a51406ac0a470ed0ec0df1f77a32a603",
)
_KNOWN_HKEL_REVIEW_ISSUES = (
    "hkel-structure/HKEL_ARCHIVE_ROOT_LANGUAGE_CONFLICT/3",
    "hkel-structure/HKEL_BILINGUAL_ROOT_KIND_CONFLICT/1",
)
_ADMISSION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "attempt_id",
        "observation_cutoff",
        "report_fingerprint",
        "source_observation_fingerprint",
        "structure_profile_fingerprint",
        "archive_member_count",
        "bilingual_pair_count",
        "publication_specification_count",
        "archive_reuse_keys",
        "review_issue_refs",
        "fingerprint",
    }
)
_REUSE_FIELDS = frozenset(
    {
        "archive_endpoint_id",
        "archive_fingerprint",
        "publication_profile_fingerprint",
        "fingerprint",
    }
)
_ARCHIVE_REFERENCE_FIELDS = frozenset(
    {
        "authority_manifest_fingerprint",
        "body_length",
        "content_fingerprint",
        "endpoint_id",
        "execution_authorization_fingerprint",
        "final_url",
        "media_type",
        "object_ref",
        "provenance_kind",
        "source_attempt_id",
        "source_cycle_id",
        "source_journal_head_fingerprint",
        "source_report_fingerprint",
        "work_item_id",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "cycle_id",
        "observation_cutoff",
        "scope_dispositions",
        "verified_item_refs",
        "review_issue_refs",
        "journal_head_fingerprint",
        "source_register_fingerprint",
        "source_baseline_fingerprint",
        "work_plan_fingerprint",
        "result",
        "fingerprint",
    }
)
_MANIFEST_FIELDS_WITH_SOURCES = _MANIFEST_FIELDS | {"source_dispositions"}
_SCOPE_FIELDS = frozenset(
    {
        "scope_id",
        "required_item_count",
        "verified_item_count",
        "retryable_item_count",
        "rejected_item_count",
        "result",
    }
)
_SUCCESS = frozenset(
    {
        JournalTransition.CAPTURED_VERIFIED,
        JournalTransition.IMPORTED_CAPTURE_VERIFIED,
    }
)
_RETRYABLE = frozenset(
    {
        JournalTransition.DISCOVERED,
        JournalTransition.STARTED,
        JournalTransition.TRANSPORT_STARTED,
        JournalTransition.RETRYABLE_FAILURE,
        JournalTransition.ADMISSION_FAILED_BEFORE_TRANSPORT,
        JournalTransition.ELAPSED_BUDGET_EXHAUSTED,
    }
)


def _fail(code: str) -> Never:
    raise ValueError(code)


def _object_tuple(value: object) -> TypeIs[tuple[object, ...]]:
    return type(value) is tuple


def _exact_string_tuple(value: object) -> tuple[str, ...]:
    if not _object_tuple(value):
        _fail("LEGISLATION_REFERENCE_SET_INVALID")
    result: list[str] = []
    for item in value:
        if type(item) is not str:
            _fail("LEGISLATION_REFERENCE_SET_INVALID")
        result.append(item)
    return tuple(result)


def _exact_string(value: object, *, code: str) -> str:
    if type(value) is not str:
        _fail(code)
    return value


def _exact_int(value: object, *, code: str) -> int:
    if type(value) is not int:
        _fail(code)
    return value


def _gld_language(value: object) -> Literal["ENGLISH", "TRADITIONAL_CHINESE", "BILINGUAL"]:
    if value == "ENGLISH":
        return "ENGLISH"
    if value == "TRADITIONAL_CHINESE":
        return "TRADITIONAL_CHINESE"
    if value == "BILINGUAL":
        return "BILINGUAL"
    _fail("LEGISLATION_WORK_GRAPH_INVALID")


class LegislationWorkKind(StrEnum):
    """All required V1 legislation acquisition work classes."""

    HKEL_CURRENT_INVENTORY = "HKEL_CURRENT_INVENTORY"
    HKEL_CURRENT_ARCHIVE = "HKEL_CURRENT_ARCHIVE"
    HKEL_PUBLICATION_SPECIFICATION = "HKEL_PUBLICATION_SPECIFICATION"
    GLD_ISSUE_DISCOVERY = "GLD_ISSUE_DISCOVERY"
    GLD_EVENT_ARTIFACT = "GLD_EVENT_ARTIFACT"
    HKEL_EDITORIAL_RECORD = "HKEL_EDITORIAL_RECORD"
    HKEL_VERIFIED_COPY = "HKEL_VERIFIED_COPY"
    HKEL_ASSISTED_COPY = "HKEL_ASSISTED_COPY"
    BASIC_LAW = "BASIC_LAW"
    ANNEX_III = "ANNEX_III"
    INSTRUMENTS_AND_OTHERS = "INSTRUMENTS_AND_OTHERS"


class HkelArchiveProvenanceKind(StrEnum):
    """Closed origin of one reusable HKeL archive object."""

    TASK4_RETAINED_IMPORT = "TASK4_RETAINED_IMPORT"
    CURRENT_CYCLE_CAPTURE = "CURRENT_CYCLE_CAPTURE"


@dataclass(frozen=True, slots=True, weakref_slot=True)
class LegislationWorkSeed:
    """Stable source work facts used to issue one cycle-specific journal item."""

    stable_key: str
    kind: LegislationWorkKind
    source_role: str
    locator: str
    media_type: str
    max_bytes: int
    scope_ids: tuple[str, ...]
    dependency_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate one exact seed without granting URL authority."""
        if (
            type(self.stable_key) is not str
            or _STABLE_KEY.fullmatch(self.stable_key) is None
            or type(self.kind) is not LegislationWorkKind
            or type(self.source_role) is not str
            or _SOURCE_ROLE.fullmatch(self.source_role) is None
            or type(self.locator) is not str
            or type(self.media_type) is not str
            or not self.media_type
            or type(self.max_bytes) is not int
            or not 1 <= self.max_bytes <= _MAX_OBJECT_BYTES
            or type(self.scope_ids) is not tuple
            or not self.scope_ids
            or tuple(sorted(set(self.scope_ids))) != self.scope_ids
            or not set(self.scope_ids).issubset(LEGISLATION_SCOPE_IDS)
            or type(self.dependency_keys) is not tuple
            or tuple(sorted(set(self.dependency_keys))) != self.dependency_keys
            or any(_STABLE_KEY.fullmatch(item) is None for item in self.dependency_keys)
        ):
            _fail("LEGISLATION_WORK_SEED_INVALID")
        parsed = urlsplit(self.locator)
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.port not in {None, 443}
        ):
            _fail("LEGISLATION_WORK_SEED_INVALID")


@dataclass(frozen=True, slots=True)
class LegislationWorkNode:
    """One graph node with its shared-runner schedule and exact dependencies."""

    stable_key: str
    kind: LegislationWorkKind
    scope_ids: tuple[str, ...]
    dependency_keys: tuple[str, ...]
    scheduled: ScheduledWorkItem
    source_id: str
    endpoint_id: str
    source_register_fingerprint: str
    source_input_fingerprint: str


@dataclass(frozen=True, slots=True)
class LegislationWorkGraph:
    """Canonical complete legislation work graph for one source cycle."""

    cycle_id: str
    observation_cutoff: str
    gld_window: GldGazetteWindow
    nodes: tuple[LegislationWorkNode, ...]
    fingerprint: str

    def to_json(self) -> dict[str, JsonValue]:
        """Return the complete canonical durable-activity graph payload."""
        _validate_graph(self)
        return {
            "schema_id": "asklegal.legislation-work-graph",
            "schema_version": _SCHEMA_VERSION,
            **_graph_body(self.cycle_id, self.observation_cutoff, self.gld_window, self.nodes),
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_json(cls, value: object) -> LegislationWorkGraph:
        """Rebuild and fully revalidate one durable-activity graph payload."""
        try:
            document = checked_json_value(value)
        except ValueError:
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
        if type(document) is not dict or set(document) != {
            "schema_id",
            "schema_version",
            "cycle_id",
            "observation_cutoff",
            "gld_window",
            "nodes",
            "fingerprint",
        }:
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
        if (
            document["schema_id"] != "asklegal.legislation-work-graph"
            or document["schema_version"] != _SCHEMA_VERSION
            or type(document["cycle_id"]) is not str
            or type(document["observation_cutoff"]) is not str
            or type(document["fingerprint"]) is not str
            or type(document["nodes"]) is not list
        ):
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
        nodes: list[LegislationWorkNode] = []
        for raw in document["nodes"]:
            if type(raw) is not dict or set(raw) != {
                "stable_key",
                "kind",
                "scope_ids",
                "dependency_keys",
                "work_item",
                "priority",
                "host",
                "source_id",
                "endpoint_id",
                "source_register_fingerprint",
                "source_input_fingerprint",
            }:
                _fail("LEGISLATION_WORK_GRAPH_INVALID")
            if (
                type(raw["stable_key"]) is not str
                or type(raw["kind"]) is not str
                or type(raw["scope_ids"]) is not list
                or any(type(item) is not str for item in raw["scope_ids"])
                or type(raw["dependency_keys"]) is not list
                or any(type(item) is not str for item in raw["dependency_keys"])
                or type(raw["priority"]) is not list
                or len(raw["priority"]) != _PRIORITY_PARTS
                or type(raw["priority"][0]) is not int
                or type(raw["priority"][1]) is not int
                or type(raw["priority"][2]) is not str
                or type(raw["host"]) is not str
                or type(raw["source_id"]) is not str
                or type(raw["endpoint_id"]) is not str
                or type(raw["source_register_fingerprint"]) is not str
                or type(raw["source_input_fingerprint"]) is not str
            ):
                _fail("LEGISLATION_WORK_GRAPH_INVALID")
            try:
                identity = WorkItemIdentity.from_json(raw["work_item"])
                kind = LegislationWorkKind(raw["kind"])
                scheduled = ScheduledWorkItem(
                    identity,
                    (raw["priority"][0], raw["priority"][1], raw["priority"][2]),
                    raw["host"],
                    0,
                )
            except (TypeError, ValueError) as error:
                code = "LEGISLATION_WORK_GRAPH_INVALID"
                raise ValueError(code) from error
            scope_ids = tuple(item for item in raw["scope_ids"] if type(item) is str)
            dependency_keys = tuple(item for item in raw["dependency_keys"] if type(item) is str)
            nodes.append(
                LegislationWorkNode(
                    raw["stable_key"],
                    kind,
                    scope_ids,
                    dependency_keys,
                    scheduled,
                    raw["source_id"],
                    raw["endpoint_id"],
                    raw["source_register_fingerprint"],
                    raw["source_input_fingerprint"],
                )
            )
        graph = cls(
            document["cycle_id"],
            document["observation_cutoff"],
            _gld_window_from_json(document["gld_window"]),
            tuple(nodes),
            document["fingerprint"],
        )
        _validate_graph(graph)
        return graph


@dataclass(frozen=True, slots=True)
class LegislationVerifiedItem:
    """Stable input identity linked to one verified journal object."""

    stable_key: str
    object_ref: str
    content_fingerprint: str
    reference: str

    @classmethod
    def issue(
        cls,
        stable_key: object,
        object_ref: object,
        content_fingerprint: object,
    ) -> LegislationVerifiedItem:
        """Issue one canonical downstream reference from exact verified facts."""
        if (
            type(stable_key) is not str
            or _STABLE_KEY.fullmatch(stable_key) is None
            or type(object_ref) is not str
            or _REFERENCE.fullmatch(object_ref) is None
            or type(content_fingerprint) is not str
            or _FINGERPRINT.fullmatch(content_fingerprint) is None
        ):
            _fail("LEGISLATION_VERIFIED_INPUT_INVALID")
        body = {
            "stable_key": stable_key,
            "object_ref": object_ref,
            "content_fingerprint": content_fingerprint,
        }
        digest = sha256(canonicalize(checked_json_value(body))).hexdigest()
        return cls(
            stable_key,
            object_ref,
            content_fingerprint,
            f"legislation-item/{stable_key}/{digest}",
        )


@dataclass(frozen=True, slots=True)
class LegislationScopeDisposition:
    """Complete accounting for one release scope."""

    scope_id: str
    required_item_count: int
    verified_item_count: int
    retryable_item_count: int
    rejected_item_count: int
    result: AcquisitionCycleResult

    def to_json(self) -> dict[str, JsonValue]:
        """Return the closed scope-accounting projection."""
        return {
            "scope_id": self.scope_id,
            "required_item_count": self.required_item_count,
            "verified_item_count": self.verified_item_count,
            "retryable_item_count": self.retryable_item_count,
            "rejected_item_count": self.rejected_item_count,
            "result": self.result.value,
        }


@dataclass(frozen=True, slots=True)
class _ManifestProjection:
    cycle_id: str
    observation_cutoff: str
    scopes: tuple[LegislationScopeDisposition, ...]
    verified_refs: tuple[str, ...]
    review_refs: tuple[str, ...]
    journal_head: str
    source_register_fingerprint: str
    source_baseline_fingerprint: str
    work_plan_fingerprint: str
    result: AcquisitionCycleResult
    source_dispositions: tuple[SourceRoleDisposition, ...] = ()


@dataclass(frozen=True, slots=True)
class LegislationAcquisitionManifest:
    """Strict family result accepted by legal processing only when complete."""

    cycle_id: str
    observation_cutoff: str
    scope_dispositions: tuple[LegislationScopeDisposition, ...]
    verified_item_refs: tuple[str, ...]
    review_issue_refs: tuple[str, ...]
    journal_head_fingerprint: str
    source_register_fingerprint: str
    source_baseline_fingerprint: str
    work_plan_fingerprint: str
    result: AcquisitionCycleResult
    fingerprint: str
    source_dispositions: tuple[SourceRoleDisposition, ...] = ()

    def to_json(self) -> dict[str, JsonValue]:
        """Return the canonical cross-application JSON document."""
        _validate_manifest(self)
        return {
            **_manifest_body(
                _ManifestProjection(
                    self.cycle_id,
                    self.observation_cutoff,
                    self.scope_dispositions,
                    self.verified_item_refs,
                    self.review_issue_refs,
                    self.journal_head_fingerprint,
                    self.source_register_fingerprint,
                    self.source_baseline_fingerprint,
                    self.work_plan_fingerprint,
                    self.result,
                    self.source_dispositions,
                )
            ),
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_json(cls, value: object) -> LegislationAcquisitionManifest:
        """Restore the exact canonical manifest without importing another app."""
        code = "LEGISLATION_MANIFEST_INVALID"
        try:
            document = checked_json_value(value)
        except ValueError as error:
            raise ValueError(code) from error
        if (
            type(document) is not dict
            or frozenset(document) not in {_MANIFEST_FIELDS, _MANIFEST_FIELDS_WITH_SOURCES}
            or document["schema_id"] != _SCHEMA_ID
            or document["schema_version"] != _SCHEMA_VERSION
            or type(document["scope_dispositions"]) is not list
            or type(document["verified_item_refs"]) is not list
            or type(document["review_issue_refs"]) is not list
        ):
            _fail("LEGISLATION_MANIFEST_INVALID")
        scopes: list[LegislationScopeDisposition] = []
        for raw in document["scope_dispositions"]:
            if type(raw) is not dict or frozenset(raw) != _SCOPE_FIELDS:
                _fail("LEGISLATION_MANIFEST_INVALID")
            if any(
                type(raw[name]) is not int
                for name in (
                    "required_item_count",
                    "verified_item_count",
                    "retryable_item_count",
                    "rejected_item_count",
                )
            ):
                _fail("LEGISLATION_MANIFEST_INVALID")
            try:
                scopes.append(
                    LegislationScopeDisposition(
                        _exact_string(raw["scope_id"], code="LEGISLATION_MANIFEST_INVALID"),
                        _exact_int(raw["required_item_count"], code=code),
                        _exact_int(raw["verified_item_count"], code=code),
                        _exact_int(raw["retryable_item_count"], code=code),
                        _exact_int(raw["rejected_item_count"], code=code),
                        AcquisitionCycleResult(raw["result"]),
                    )
                )
            except (TypeError, ValueError) as error:
                raise ValueError(code) from error
        string_names = (
            "cycle_id",
            "observation_cutoff",
            "journal_head_fingerprint",
            "source_register_fingerprint",
            "source_baseline_fingerprint",
            "work_plan_fingerprint",
            "fingerprint",
        )
        if (
            any(type(document[name]) is not str for name in string_names)
            or any(type(item) is not str for item in document["verified_item_refs"])
            or any(type(item) is not str for item in document["review_issue_refs"])
        ):
            _fail("LEGISLATION_MANIFEST_INVALID")
        try:
            raw_sources = document.get("source_dispositions", [])
            if type(raw_sources) is not list:
                _fail(code)
            source_dispositions = validate_source_role_dispositions(
                tuple(SourceRoleDisposition.from_json(item) for item in raw_sources)
            )
            manifest = cls(
                cycle_id=_exact_string(document["cycle_id"], code=code),
                observation_cutoff=_exact_string(document["observation_cutoff"], code=code),
                scope_dispositions=tuple(scopes),
                verified_item_refs=tuple(
                    item for item in document["verified_item_refs"] if type(item) is str
                ),
                review_issue_refs=tuple(
                    item for item in document["review_issue_refs"] if type(item) is str
                ),
                journal_head_fingerprint=_exact_string(
                    document["journal_head_fingerprint"], code=code
                ),
                source_register_fingerprint=_exact_string(
                    document["source_register_fingerprint"], code=code
                ),
                source_baseline_fingerprint=_exact_string(
                    document["source_baseline_fingerprint"], code=code
                ),
                work_plan_fingerprint=_exact_string(document["work_plan_fingerprint"], code=code),
                result=AcquisitionCycleResult(document["result"]),
                fingerprint=_exact_string(document["fingerprint"], code=code),
                source_dispositions=source_dispositions,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(code) from error
        _validate_manifest(manifest)
        return manifest


@dataclass(frozen=True, slots=True)
class HkelArchiveObjectReference:
    """One reusable archive binding with origin-specific acquisition authority."""

    endpoint_id: str
    work_item_id: str
    media_type: str
    final_url: str
    body_length: int
    content_fingerprint: str
    object_ref: str
    provenance_kind: HkelArchiveProvenanceKind
    source_cycle_id: str
    source_attempt_id: str
    source_report_fingerprint: str
    authority_manifest_fingerprint: str
    execution_authorization_fingerprint: str
    source_journal_head_fingerprint: str


@dataclass(frozen=True, slots=True, weakref_slot=True)
class LegislationAcceptedSourceState:
    """One register-accepted complete predecessor authorized for equality comparison."""

    manifest: LegislationAcquisitionManifest
    observation_id: str
    source_snapshot_id: str
    provenance_fingerprint: str


@dataclass(frozen=True, slots=True, weakref_slot=True)
class HkelImportedBaseline:
    """Task 4 journal items bound to the exact full-body admission receipt."""

    source_report_fingerprint: str
    imported_work_item_ids: tuple[str, ...]
    archive_member_count: int
    bilingual_pair_count: int
    publication_specification_count: int
    archive_reuse_keys: tuple[HkelArchiveReuseKey, ...]
    archive_object_references: tuple[HkelArchiveObjectReference, ...]
    review_issue_refs: tuple[str, ...]
    source_observation_fingerprint: str
    structure_profile_fingerprint: str
    import_cycle_id: str
    source_attempt_id: str
    receipt_fingerprint: str
    work_item_lineage_fingerprint: str
    fingerprint: str


class HkelArchiveBodyAdmissionPort(Protocol):
    """Admit the complete retained ZIP member set and XML for one changed archive."""

    def admit_archive(
        self,
        *,
        source_role: str,
        endpoint_id: str,
        object_ref: str,
        content_fingerprint: str,
    ) -> bool:
        """Return exactly true only after the retained archive body passes admission."""
        ...


@dataclass(frozen=True, slots=True)
class LegislationAcquisitionCycle:
    """One production composition result from runner through manifest projection."""

    report: AcquisitionCycleReport
    verified_items: tuple[LegislationVerifiedItem, ...]
    baseline: HkelImportedBaseline
    manifest: LegislationAcquisitionManifest


@dataclass(frozen=True, slots=True)
class _HkelAdmissionProjection:
    archive_reuse_keys: tuple[HkelArchiveReuseKey, ...]
    review_issue_refs: tuple[str, ...]
    source_observation_fingerprint: str
    structure_profile_fingerprint: str


@dataclass(frozen=True, slots=True)
class _IssuedLegislationSeed:
    reference: weakref.ReferenceType[object]
    snapshot: str
    observation_cutoff: str
    source_id: str
    endpoint_id: str
    register_fingerprint: str
    input_fingerprint: str
    gld_window: GldGazetteWindow


@dataclass(frozen=True, slots=True)
class _IssuedAcceptedSourceState:
    reference: weakref.ReferenceType[object]
    manifest_fingerprint: str
    observation_id: str
    source_snapshot_id: str
    evidence_package_id: str
    primary_manifest_version: str
    recovery_manifest_version: str


_SEED_ISSUANCE: dict[int, _IssuedLegislationSeed] = {}
_BASELINE_ISSUANCE: dict[int, tuple[weakref.ReferenceType[object], str]] = {}
_ACCEPTED_STATE_ISSUANCE: dict[int, _IssuedAcceptedSourceState] = {}
_ENDPOINTS_BY_KIND = {
    LegislationWorkKind.HKEL_CURRENT_INVENTORY: frozenset(
        f"sep_{value:048x}" for value in (1, 2, 3)
    ),
    LegislationWorkKind.HKEL_CURRENT_ARCHIVE: frozenset(
        f"sep_{value:048x}" for value in range(10, 22)
    ),
    LegislationWorkKind.HKEL_PUBLICATION_SPECIFICATION: frozenset(
        f"sep_{value:048x}" for value in (53, 54, 55, 56, 57, 58, 81)
    ),
    LegislationWorkKind.GLD_ISSUE_DISCOVERY: frozenset(
        {"sep_00000000000000000000000000000000000000000000003b"}
    ),
    LegislationWorkKind.GLD_EVENT_ARTIFACT: frozenset(
        {"sep_00000000000000000000000000000000000000000000003d"}
    ),
    LegislationWorkKind.HKEL_EDITORIAL_RECORD: frozenset(
        {
            "sep_000000000000000000000000000000000000000000000033",
            "sep_000000000000000000000000000000000000000000000034",
        }
    ),
    LegislationWorkKind.HKEL_VERIFIED_COPY: frozenset(
        {"sep_00000000000000000000000000000000000000000000004d"}
    ),
    LegislationWorkKind.HKEL_ASSISTED_COPY: frozenset(
        {"sep_000000000000000000000000000000000000000000000019"}
    ),
    LegislationWorkKind.BASIC_LAW: frozenset(
        {"sep_000000000000000000000000000000000000000000000050"}
    ),
    LegislationWorkKind.ANNEX_III: frozenset(
        {"sep_000000000000000000000000000000000000000000000043"}
    ),
    LegislationWorkKind.INSTRUMENTS_AND_OTHERS: frozenset(
        {"sep_000000000000000000000000000000000000000000000044"}
    ),
}
_CONSTITUTIONAL_SCOPE = (LEGISLATION_SCOPE_IDS[0],)
_ALL_SCOPES = LEGISLATION_SCOPE_IDS


def _seed_snapshot(seed: LegislationWorkSeed) -> str:
    body = {
        "dependency_keys": list(seed.dependency_keys),
        "kind": seed.kind.value,
        "locator": seed.locator,
        "max_bytes": seed.max_bytes,
        "media_type": seed.media_type,
        "scope_ids": list(seed.scope_ids),
        "source_role": seed.source_role,
        "stable_key": seed.stable_key,
    }
    return f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"


def _baseline_body(baseline: HkelImportedBaseline) -> dict[str, JsonValue]:
    return {
        "archive_member_count": baseline.archive_member_count,
        "archive_reuse_keys": [
            {
                "archive_endpoint_id": item.archive_endpoint_id,
                "archive_fingerprint": item.archive_fingerprint,
                "publication_profile_fingerprint": item.publication_profile_fingerprint,
                "fingerprint": item.fingerprint,
            }
            for item in baseline.archive_reuse_keys
        ],
        "archive_object_references": [
            {
                "authority_manifest_fingerprint": item.authority_manifest_fingerprint,
                "body_length": item.body_length,
                "content_fingerprint": item.content_fingerprint,
                "endpoint_id": item.endpoint_id,
                "execution_authorization_fingerprint": item.execution_authorization_fingerprint,
                "final_url": item.final_url,
                "media_type": item.media_type,
                "object_ref": item.object_ref,
                "provenance_kind": item.provenance_kind.value,
                "source_attempt_id": item.source_attempt_id,
                "source_cycle_id": item.source_cycle_id,
                "source_journal_head_fingerprint": item.source_journal_head_fingerprint,
                "source_report_fingerprint": item.source_report_fingerprint,
                "work_item_id": item.work_item_id,
            }
            for item in baseline.archive_object_references
        ],
        "bilingual_pair_count": baseline.bilingual_pair_count,
        "import_cycle_id": baseline.import_cycle_id,
        "imported_work_item_ids": list(baseline.imported_work_item_ids),
        "publication_specification_count": baseline.publication_specification_count,
        "receipt_fingerprint": baseline.receipt_fingerprint,
        "review_issue_refs": list(baseline.review_issue_refs),
        "source_attempt_id": baseline.source_attempt_id,
        "source_observation_fingerprint": baseline.source_observation_fingerprint,
        "source_report_fingerprint": baseline.source_report_fingerprint,
        "structure_profile_fingerprint": baseline.structure_profile_fingerprint,
        "work_item_lineage_fingerprint": baseline.work_item_lineage_fingerprint,
    }


def _baseline_fingerprint(baseline: HkelImportedBaseline) -> str:
    return (
        "sha256:" + sha256(canonicalize(checked_json_value(_baseline_body(baseline)))).hexdigest()
    )


def _issue_baseline(baseline: HkelImportedBaseline) -> HkelImportedBaseline:
    identity = id(baseline)
    fingerprint = _baseline_fingerprint(baseline)
    object.__setattr__(baseline, "fingerprint", fingerprint)

    def cleanup(reference: weakref.ReferenceType[object]) -> None:
        issued = _BASELINE_ISSUANCE.get(identity)
        if issued is not None and issued[0] is reference:
            del _BASELINE_ISSUANCE[identity]

    _BASELINE_ISSUANCE[identity] = (weakref.ref(baseline, cleanup), fingerprint)
    return baseline


def _validate_baseline(value: object) -> HkelImportedBaseline:
    if type(value) is not HkelImportedBaseline:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    issued = _BASELINE_ISSUANCE.get(id(value))
    if (
        issued is None
        or issued[0]() is not value
        or issued[1] != _baseline_fingerprint(value)
        or value.fingerprint != issued[1]
        or value.source_report_fingerprint != _KNOWN_HKEL_REPORT_FINGERPRINT
        or value.archive_member_count != _EXPECTED_ARCHIVE_MEMBERS
        or value.bilingual_pair_count != _EXPECTED_BILINGUAL_PAIRS
        or value.publication_specification_count != _EXPECTED_SPECIFICATIONS
        or value.import_cycle_id != _KNOWN_HKEL_IMPORT_CYCLE
        or value.source_attempt_id != _KNOWN_HKEL_ATTEMPT
        or _FINGERPRINT.fullmatch(value.source_observation_fingerprint) is None
        or _FINGERPRINT.fullmatch(value.structure_profile_fingerprint) is None
        or len(value.imported_work_item_ids) != _EXPECTED_ENDPOINTS
        or tuple(sorted(set(value.imported_work_item_ids))) != value.imported_work_item_ids
        or len(value.archive_reuse_keys) != _EXPECTED_ARCHIVES
        or len(value.archive_object_references) != _EXPECTED_ARCHIVES
        or tuple(item.endpoint_id for item in value.archive_object_references)
        != tuple(item.archive_endpoint_id for item in value.archive_reuse_keys)
        or any(
            type(item) is not HkelArchiveObjectReference
            or item.content_fingerprint != key.archive_fingerprint
            or type(item.provenance_kind) is not HkelArchiveProvenanceKind
            or not item.source_cycle_id
            or not item.source_attempt_id
            or _FINGERPRINT.fullmatch(item.source_report_fingerprint) is None
            or _FINGERPRINT.fullmatch(item.authority_manifest_fingerprint) is None
            or _FINGERPRINT.fullmatch(item.execution_authorization_fingerprint) is None
            or _FINGERPRINT.fullmatch(item.source_journal_head_fingerprint) is None
            or (
                item.provenance_kind is HkelArchiveProvenanceKind.TASK4_RETAINED_IMPORT
                and (
                    item.source_cycle_id != value.import_cycle_id
                    or item.source_attempt_id != value.source_attempt_id
                    or item.source_report_fingerprint != value.source_report_fingerprint
                )
            )
            for item, key in zip(
                value.archive_object_references, value.archive_reuse_keys, strict=True
            )
        )
        or tuple(item.archive_endpoint_id for item in value.archive_reuse_keys)
        != tuple(f"sep_{index:048x}" for index in range(10, 22))
        or any(
            _FINGERPRINT.fullmatch(item.publication_profile_fingerprint) is None
            or HkelArchiveReuseKey.issue(
                item.archive_endpoint_id,
                item.archive_fingerprint,
                item.publication_profile_fingerprint,
            )
            != item
            for item in value.archive_reuse_keys
        )
        or value.review_issue_refs != _KNOWN_HKEL_REVIEW_ISSUES
    ):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    return value


def hkel_baseline_to_json(value: object) -> dict[str, JsonValue]:
    """Serialize one issued HKeL baseline for the worker-local durable state file."""
    baseline = _validate_baseline(value)
    return {
        "schema_id": "asklegal.hkel-acquisition-baseline",
        "schema_version": _SCHEMA_VERSION,
        **_baseline_body(baseline),
        "fingerprint": baseline.fingerprint,
    }


def restore_hkel_baseline(  # noqa: C901, PLR0912, PLR0915 - one closed state parser.
    value: object,
    authentic_import: object,
) -> HkelImportedBaseline:
    """Restore advanced state while anchoring every Task 4 claim to a fresh import."""
    code = "HKEL_IMPORTED_BASELINE_INVALID"
    original = _validate_baseline(authentic_import)
    try:
        document = checked_json_value(value)
    except ValueError as error:
        raise ValueError(code) from error
    expected_fields = frozenset(_baseline_body(original)) | {
        "schema_id",
        "schema_version",
        "fingerprint",
    }
    if (
        type(document) is not dict
        or frozenset(document) != expected_fields
        or document["schema_id"] != "asklegal.hkel-acquisition-baseline"
        or document["schema_version"] != _SCHEMA_VERSION
    ):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    raw_reuse_keys = document["archive_reuse_keys"]
    if type(raw_reuse_keys) is not list:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    reuse_key_list: list[HkelArchiveReuseKey] = []
    for raw_key in raw_reuse_keys:
        if type(raw_key) is not dict or frozenset(raw_key) != _REUSE_FIELDS:
            _fail("HKEL_IMPORTED_BASELINE_INVALID")
        try:
            key = HkelArchiveReuseKey.issue(
                raw_key["archive_endpoint_id"],
                raw_key["archive_fingerprint"],
                raw_key["publication_profile_fingerprint"],
            )
        except (TypeError, ValueError) as error:
            code = "HKEL_IMPORTED_BASELINE_INVALID"
            raise ValueError(code) from error
        if raw_key["fingerprint"] != key.fingerprint:
            _fail("HKEL_IMPORTED_BASELINE_INVALID")
        reuse_key_list.append(key)
    reuse_keys = tuple(reuse_key_list)
    raw_references = document["archive_object_references"]
    if type(raw_references) is not list:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    references: list[HkelArchiveObjectReference] = []
    original_by_endpoint = {item.endpoint_id: item for item in original.archive_object_references}
    for raw in raw_references:
        if type(raw) is not dict or frozenset(raw) != _ARCHIVE_REFERENCE_FIELDS:
            _fail("HKEL_IMPORTED_BASELINE_INVALID")
        try:
            reference = HkelArchiveObjectReference(
                endpoint_id=_exact_string(
                    raw["endpoint_id"], code="HKEL_IMPORTED_BASELINE_INVALID"
                ),
                work_item_id=_exact_string(
                    raw["work_item_id"], code="HKEL_IMPORTED_BASELINE_INVALID"
                ),
                media_type=_exact_string(raw["media_type"], code="HKEL_IMPORTED_BASELINE_INVALID"),
                final_url=_exact_string(raw["final_url"], code="HKEL_IMPORTED_BASELINE_INVALID"),
                body_length=_exact_int(raw["body_length"], code=code),
                content_fingerprint=_exact_string(
                    raw["content_fingerprint"], code="HKEL_IMPORTED_BASELINE_INVALID"
                ),
                object_ref=_exact_string(raw["object_ref"], code="HKEL_IMPORTED_BASELINE_INVALID"),
                provenance_kind=HkelArchiveProvenanceKind(raw["provenance_kind"]),
                source_cycle_id=_exact_string(
                    raw["source_cycle_id"], code="HKEL_IMPORTED_BASELINE_INVALID"
                ),
                source_attempt_id=_exact_string(
                    raw["source_attempt_id"], code="HKEL_IMPORTED_BASELINE_INVALID"
                ),
                source_report_fingerprint=_exact_string(
                    raw["source_report_fingerprint"], code="HKEL_IMPORTED_BASELINE_INVALID"
                ),
                authority_manifest_fingerprint=_exact_string(
                    raw["authority_manifest_fingerprint"], code="HKEL_IMPORTED_BASELINE_INVALID"
                ),
                execution_authorization_fingerprint=_exact_string(
                    raw["execution_authorization_fingerprint"],
                    code="HKEL_IMPORTED_BASELINE_INVALID",
                ),
                source_journal_head_fingerprint=_exact_string(
                    raw["source_journal_head_fingerprint"], code="HKEL_IMPORTED_BASELINE_INVALID"
                ),
            )
        except (TypeError, ValueError) as error:
            raise ValueError(code) from error
        if type(reference.body_length) is not int or reference.body_length < 1:
            _fail("HKEL_IMPORTED_BASELINE_INVALID")
        imported = original_by_endpoint.get(reference.endpoint_id)
        if reference.provenance_kind is HkelArchiveProvenanceKind.TASK4_RETAINED_IMPORT:
            if reference != imported:
                _fail("HKEL_IMPORTED_BASELINE_INVALID")
        elif (
            imported is None
            or reference.source_cycle_id == original.import_cycle_id
            or reference.source_attempt_id == original.source_attempt_id
            or reference.source_report_fingerprint == original.source_report_fingerprint
            or reference.authority_manifest_fingerprint == imported.authority_manifest_fingerprint
            or reference.execution_authorization_fingerprint
            == imported.execution_authorization_fingerprint
            or reference.source_attempt_id != f"runner-{reference.source_cycle_id}"
            or reference.source_report_fingerprint != reference.execution_authorization_fingerprint
        ):
            _fail("HKEL_IMPORTED_BASELINE_INVALID")
        references.append(reference)
    scalar_names = (
        "archive_member_count",
        "bilingual_pair_count",
        "publication_specification_count",
    )
    if any(type(document[name]) is not int for name in scalar_names):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    string_names = (
        "source_report_fingerprint",
        "source_observation_fingerprint",
        "structure_profile_fingerprint",
        "import_cycle_id",
        "source_attempt_id",
        "receipt_fingerprint",
        "work_item_lineage_fingerprint",
        "fingerprint",
    )
    if any(type(document[name]) is not str for name in string_names):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    imported_ids_raw = document["imported_work_item_ids"]
    review_refs_raw = document["review_issue_refs"]
    if (
        type(imported_ids_raw) is not list
        or any(type(item) is not str for item in imported_ids_raw)
        or type(review_refs_raw) is not list
        or any(type(item) is not str for item in review_refs_raw)
    ):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    candidate = HkelImportedBaseline(
        source_report_fingerprint=_exact_string(document["source_report_fingerprint"], code=code),
        imported_work_item_ids=tuple(item for item in imported_ids_raw if type(item) is str),
        archive_member_count=_exact_int(document["archive_member_count"], code=code),
        bilingual_pair_count=_exact_int(document["bilingual_pair_count"], code=code),
        publication_specification_count=_exact_int(
            document["publication_specification_count"], code=code
        ),
        archive_reuse_keys=reuse_keys,
        archive_object_references=tuple(references),
        review_issue_refs=tuple(item for item in review_refs_raw if type(item) is str),
        source_observation_fingerprint=_exact_string(
            document["source_observation_fingerprint"], code=code
        ),
        structure_profile_fingerprint=_exact_string(
            document["structure_profile_fingerprint"], code=code
        ),
        import_cycle_id=_exact_string(document["import_cycle_id"], code=code),
        source_attempt_id=_exact_string(document["source_attempt_id"], code=code),
        receipt_fingerprint=_exact_string(document["receipt_fingerprint"], code=code),
        work_item_lineage_fingerprint=_exact_string(
            document["work_item_lineage_fingerprint"], code=code
        ),
        fingerprint="",
    )
    immutable_names = (
        "source_report_fingerprint",
        "imported_work_item_ids",
        "archive_member_count",
        "bilingual_pair_count",
        "publication_specification_count",
        "review_issue_refs",
        "import_cycle_id",
        "source_attempt_id",
        "receipt_fingerprint",
        "work_item_lineage_fingerprint",
    )
    if any(getattr(candidate, name) != getattr(original, name) for name in immutable_names):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    issued = _issue_baseline(candidate)
    if issued.fingerprint != document["fingerprint"]:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    return _validate_baseline(issued)


def _issue_registered_seed(  # noqa: PLR0913 - binds the complete register provenance.
    seed: LegislationWorkSeed,
    *,
    observation_cutoff: str,
    source_id: str,
    endpoint_id: str,
    register_fingerprint: str,
    input_fingerprint: str,
    gld_window: GldGazetteWindow,
) -> LegislationWorkSeed:
    identity = id(seed)

    def cleanup(reference: weakref.ReferenceType[object]) -> None:
        issued = _SEED_ISSUANCE.get(identity)
        if issued is not None and issued.reference is reference:
            del _SEED_ISSUANCE[identity]

    _SEED_ISSUANCE[identity] = _IssuedLegislationSeed(
        weakref.ref(seed, cleanup),
        _seed_snapshot(seed),
        observation_cutoff,
        source_id,
        endpoint_id,
        register_fingerprint,
        input_fingerprint,
        gld_window,
    )
    return seed


def _issued_registered_seed(
    seed: LegislationWorkSeed,
    observation_cutoff: str,
) -> _IssuedLegislationSeed:
    issued = _SEED_ISSUANCE.get(id(seed))
    if (
        issued is None
        or issued.reference() is not seed
        or issued.snapshot != _seed_snapshot(seed)
        or issued.observation_cutoff != observation_cutoff
    ):
        _fail("LEGISLATION_WORK_SEED_NOT_REGISTERED")
    return issued


def registered_legislation_work_seeds(  # noqa: C901 - one closed source-role projection.
    window: object,
) -> tuple[LegislationWorkSeed, ...]:
    """Project one admitted GLD window plus the exact checked-in source register."""
    if type(window) is not GldGazetteWindow:
        _fail("LEGISLATION_GLD_WINDOW_INVALID")
    try:
        assert_gld_gazette_window_issued(window)
        window.__post_init__()
        artifacts = project_gld_artifact_requests(window)
    except (TypeError, ValueError) as error:
        code = (
            "LEGISLATION_GLD_WINDOW_NOT_ISSUED"
            if str(error) == "GLD_WINDOW_NOT_ISSUED"
            else "LEGISLATION_GLD_WINDOW_INVALID"
        )
        raise ValueError(code) from error
    if not artifacts:
        _fail("LEGISLATION_GLD_WINDOW_INVALID")
    register = load_hk_legislation_source_register()
    seeds: list[LegislationWorkSeed] = []
    key_by_kind: dict[LegislationWorkKind, list[str]] = {kind: [] for kind in LegislationWorkKind}

    def add(
        kind: LegislationWorkKind,
        endpoint_id: str,
        *,
        locator: str | None = None,
        stable_suffix: str | None = None,
        input_fingerprint: str | None = None,
    ) -> None:
        source, endpoint = register.resolve_registered_endpoint(endpoint_id)
        suffix = stable_suffix or endpoint_id.removeprefix("sep_")
        stable_key = f"{kind.value.lower().replace('_', '-')}-{suffix}"
        if kind in {
            LegislationWorkKind.HKEL_CURRENT_ARCHIVE,
            LegislationWorkKind.HKEL_EDITORIAL_RECORD,
            LegislationWorkKind.HKEL_VERIFIED_COPY,
            LegislationWorkKind.HKEL_ASSISTED_COPY,
        }:
            dependencies = tuple(key_by_kind[LegislationWorkKind.HKEL_CURRENT_INVENTORY])
        elif kind is LegislationWorkKind.GLD_EVENT_ARTIFACT:
            dependencies = tuple(key_by_kind[LegislationWorkKind.GLD_ISSUE_DISCOVERY])
        elif kind in {LegislationWorkKind.ANNEX_III, LegislationWorkKind.INSTRUMENTS_AND_OTHERS}:
            dependencies = tuple(key_by_kind[LegislationWorkKind.BASIC_LAW])
        else:
            dependencies = ()
        scopes = (
            _CONSTITUTIONAL_SCOPE
            if kind
            in {
                LegislationWorkKind.BASIC_LAW,
                LegislationWorkKind.ANNEX_III,
                LegislationWorkKind.INSTRUMENTS_AND_OTHERS,
            }
            else _ALL_SCOPES
        )
        seed = LegislationWorkSeed(
            stable_key=stable_key,
            kind=kind,
            source_role=source.source_id.replace("-", "_"),
            locator=locator or endpoint.url,
            media_type=endpoint.media_types[0],
            max_bytes=min(endpoint.max_bytes, _MAX_OBJECT_BYTES),
            scope_ids=scopes,
            dependency_keys=tuple(sorted(dependencies)),
        )
        seeds.append(
            _issue_registered_seed(
                seed,
                observation_cutoff=window.observation_cutoff,
                source_id=source.source_id,
                endpoint_id=endpoint.endpoint_id,
                register_fingerprint=register.fingerprint,
                input_fingerprint=input_fingerprint or register.fingerprint,
                gld_window=window,
            )
        )
        key_by_kind[kind].append(stable_key)

    for endpoint_id in sorted(_ENDPOINTS_BY_KIND[LegislationWorkKind.HKEL_CURRENT_INVENTORY]):
        add(LegislationWorkKind.HKEL_CURRENT_INVENTORY, endpoint_id)
    for endpoint_id in sorted(_ENDPOINTS_BY_KIND[LegislationWorkKind.HKEL_CURRENT_ARCHIVE]):
        add(LegislationWorkKind.HKEL_CURRENT_ARCHIVE, endpoint_id)
    for endpoint_id in sorted(
        _ENDPOINTS_BY_KIND[LegislationWorkKind.HKEL_PUBLICATION_SPECIFICATION]
    ):
        add(LegislationWorkKind.HKEL_PUBLICATION_SPECIFICATION, endpoint_id)
    add(
        LegislationWorkKind.GLD_ISSUE_DISCOVERY,
        window.endpoint_id,
        input_fingerprint=window.listing_fingerprint,
    )
    for artifact in artifacts:
        add(
            LegislationWorkKind.GLD_EVENT_ARTIFACT,
            artifact.endpoint_id,
            locator=artifact.locator,
            stable_suffix=artifact.stable_identity,
            input_fingerprint=artifact.listing_fingerprint,
        )
    for kind in (
        LegislationWorkKind.HKEL_EDITORIAL_RECORD,
        LegislationWorkKind.HKEL_VERIFIED_COPY,
        LegislationWorkKind.HKEL_ASSISTED_COPY,
        LegislationWorkKind.BASIC_LAW,
        LegislationWorkKind.ANNEX_III,
        LegislationWorkKind.INSTRUMENTS_AND_OTHERS,
    ):
        for endpoint_id in sorted(_ENDPOINTS_BY_KIND[kind]):
            add(kind, endpoint_id)
    return tuple(sorted(seeds, key=lambda item: item.stable_key))


def _gld_window_json(window: GldGazetteWindow) -> dict[str, JsonValue]:
    """Serialize the complete admitted GLD listing that authorizes artifact nodes."""
    window.__post_init__()
    return {
        "source_id": window.source_id,
        "endpoint_id": window.endpoint_id,
        "endpoint_version": window.endpoint_version,
        "source_profile_version": window.source_profile_version,
        "register_version": window.register_version,
        "register_fingerprint": window.register_fingerprint,
        "start_date": window.start_date,
        "end_date": window.end_date,
        "language": window.language,
        "observation_cutoff": window.observation_cutoff,
        "entries": [
            {
                "stable_identity": entry.stable_identity,
                "gazette_class": entry.gazette_class.value,
                "issue_kind": entry.issue_kind.value,
                "publication_date": entry.publication_date,
                "artifact_endpoint_id": entry.artifact_endpoint_id,
                "artifact_endpoint_version": entry.artifact_endpoint_version,
                "source_profile_version": entry.source_profile_version,
                "register_version": entry.register_version,
                "register_fingerprint": entry.register_fingerprint,
                "artifact_locator": entry.artifact_locator,
            }
            for entry in window.entries
        ],
        "listing_fingerprint": window.listing_fingerprint,
    }


def _gld_window_from_json(value: JsonValue) -> GldGazetteWindow:
    """Rebuild a complete GLD window before it may authorize durable graph nodes."""
    if type(value) is not dict or set(value) != {
        "source_id",
        "endpoint_id",
        "endpoint_version",
        "source_profile_version",
        "register_version",
        "register_fingerprint",
        "start_date",
        "end_date",
        "language",
        "observation_cutoff",
        "entries",
        "listing_fingerprint",
    }:
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    raw_entries = value["entries"]
    if type(raw_entries) is not list:
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    try:
        entries = tuple(
            GldGazetteEntry(
                _exact_string(raw["stable_identity"], code="LEGISLATION_WORK_GRAPH_INVALID"),
                GldGazetteClass(raw["gazette_class"]),
                GldGazetteIssueKind(raw["issue_kind"]),
                _exact_string(raw["publication_date"], code="LEGISLATION_WORK_GRAPH_INVALID"),
                _exact_string(raw["artifact_endpoint_id"], code="LEGISLATION_WORK_GRAPH_INVALID"),
                _exact_string(
                    raw["artifact_endpoint_version"], code="LEGISLATION_WORK_GRAPH_INVALID"
                ),
                _exact_string(raw["source_profile_version"], code="LEGISLATION_WORK_GRAPH_INVALID"),
                _exact_string(raw["register_version"], code="LEGISLATION_WORK_GRAPH_INVALID"),
                _exact_string(raw["register_fingerprint"], code="LEGISLATION_WORK_GRAPH_INVALID"),
                _exact_string(raw["artifact_locator"], code="LEGISLATION_WORK_GRAPH_INVALID"),
            )
            for raw in raw_entries
            if type(raw) is dict
            and set(raw)
            == {
                "stable_identity",
                "gazette_class",
                "issue_kind",
                "publication_date",
                "artifact_endpoint_id",
                "artifact_endpoint_version",
                "source_profile_version",
                "register_version",
                "register_fingerprint",
                "artifact_locator",
            }
        )
        if len(entries) != len(raw_entries):
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
        language = _gld_language(value["language"])
        return GldGazetteWindow(
            _exact_string(value["source_id"], code="LEGISLATION_WORK_GRAPH_INVALID"),
            _exact_string(value["endpoint_id"], code="LEGISLATION_WORK_GRAPH_INVALID"),
            _exact_string(value["endpoint_version"], code="LEGISLATION_WORK_GRAPH_INVALID"),
            _exact_string(value["source_profile_version"], code="LEGISLATION_WORK_GRAPH_INVALID"),
            _exact_string(value["register_version"], code="LEGISLATION_WORK_GRAPH_INVALID"),
            _exact_string(value["register_fingerprint"], code="LEGISLATION_WORK_GRAPH_INVALID"),
            _exact_string(value["start_date"], code="LEGISLATION_WORK_GRAPH_INVALID"),
            _exact_string(value["end_date"], code="LEGISLATION_WORK_GRAPH_INVALID"),
            language,
            _exact_string(value["observation_cutoff"], code="LEGISLATION_WORK_GRAPH_INVALID"),
            entries,
            _exact_string(value["listing_fingerprint"], code="LEGISLATION_WORK_GRAPH_INVALID"),
        )
    except (KeyError, TypeError, ValueError) as error:
        code = "LEGISLATION_WORK_GRAPH_INVALID"
        raise ValueError(code) from error


def parse_gld_gazette_window_snapshot(value: object) -> GldGazetteWindow:
    """Parse one unissued local snapshot for immediate admitted-exchange issuance."""
    try:
        checked = checked_json_value(value)
    except Exception as error:
        code = "LEGISLATION_WORK_GRAPH_INVALID"
        raise ValueError(code) from error
    return _gld_window_from_json(checked)


def _graph_body(
    cycle_id: str,
    observation_cutoff: str,
    gld_window: GldGazetteWindow,
    nodes: tuple[LegislationWorkNode, ...],
) -> dict[str, JsonValue]:
    return {
        "cycle_id": cycle_id,
        "observation_cutoff": observation_cutoff,
        "gld_window": _gld_window_json(gld_window),
        "nodes": [
            {
                "stable_key": node.stable_key,
                "kind": node.kind.value,
                "scope_ids": list(node.scope_ids),
                "dependency_keys": list(node.dependency_keys),
                "work_item": node.scheduled.identity.to_json(),
                "priority": list(node.scheduled.priority),
                "host": node.scheduled.host,
                "source_id": node.source_id,
                "endpoint_id": node.endpoint_id,
                "source_register_fingerprint": node.source_register_fingerprint,
                "source_input_fingerprint": node.source_input_fingerprint,
            }
            for node in nodes
        ],
    }


def build_legislation_work_graph(
    cycle_id: object,
    observation_cutoff: object,
    seeds: object,
) -> LegislationWorkGraph:
    """Issue one deterministic complete graph consumed by the shared runner."""
    if (
        type(cycle_id) is not str
        or _CYCLE.fullmatch(cycle_id) is None
        or type(observation_cutoff) is not str
        or _UTC.fullmatch(observation_cutoff) is None
        or not _object_tuple(seeds)
        or not seeds
    ):
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    typed_seeds: list[LegislationWorkSeed] = []
    for seed in seeds:
        if type(seed) is not LegislationWorkSeed:
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
        typed_seeds.append(seed)
    exact = tuple(sorted(typed_seeds, key=lambda item: item.stable_key))
    if len({item.stable_key for item in exact}) != len(exact):
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    if {item.kind for item in exact} != set(LegislationWorkKind) or {
        scope for item in exact for scope in item.scope_ids
    } != set(LEGISLATION_SCOPE_IDS):
        _fail("LEGISLATION_WORK_GRAPH_INCOMPLETE")
    keys = {item.stable_key for item in exact}
    if any(set(item.dependency_keys) - keys for item in exact):
        _fail("LEGISLATION_WORK_DEPENDENCY_INVALID")
    nodes: list[LegislationWorkNode] = []
    issued_seeds = tuple(_issued_registered_seed(seed, observation_cutoff) for seed in exact)
    gld_window = issued_seeds[0].gld_window
    if any(issued.gld_window != gld_window for issued in issued_seeds):
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    for index, seed in enumerate(exact):
        issued = issued_seeds[index]
        _source, endpoint = load_hk_legislation_source_register().resolve_registered_endpoint(
            issued.endpoint_id
        )
        identity = WorkItemIdentity.issue(
            source_family="LEGISLATION",
            source_role=seed.source_role,
            cycle_id=cycle_id,
            observation_cutoff=observation_cutoff,
            procedure_version=endpoint.version,
            locator=seed.locator,
            stage=seed.kind.value,
            parent_id=seed.stable_key,
            media_type=seed.media_type,
            max_bytes=seed.max_bytes,
        )
        host = urlsplit(seed.locator).hostname
        if host is None:  # pragma: no cover - seed validation owns this invariant.
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
        nodes.append(
            LegislationWorkNode(
                seed.stable_key,
                seed.kind,
                seed.scope_ids,
                seed.dependency_keys,
                ScheduledWorkItem(
                    identity,
                    (tuple(LegislationWorkKind).index(seed.kind), index, seed.stable_key),
                    host,
                    0,
                ),
                issued.source_id,
                issued.endpoint_id,
                issued.register_fingerprint,
                issued.input_fingerprint,
            )
        )
    stable_nodes = tuple(nodes)
    body = _graph_body(cycle_id, observation_cutoff, gld_window, stable_nodes)
    fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"
    return LegislationWorkGraph(cycle_id, observation_cutoff, gld_window, stable_nodes, fingerprint)


def _manifest_body(projection: _ManifestProjection) -> dict[str, JsonValue]:
    body: dict[str, JsonValue] = {
        "schema_id": _SCHEMA_ID,
        "schema_version": _SCHEMA_VERSION,
        "cycle_id": projection.cycle_id,
        "observation_cutoff": projection.observation_cutoff,
        "scope_dispositions": [item.to_json() for item in projection.scopes],
        "verified_item_refs": list(projection.verified_refs),
        "review_issue_refs": list(projection.review_refs),
        "journal_head_fingerprint": projection.journal_head,
        "source_register_fingerprint": projection.source_register_fingerprint,
        "source_baseline_fingerprint": projection.source_baseline_fingerprint,
        "work_plan_fingerprint": projection.work_plan_fingerprint,
        "result": projection.result.value,
    }
    if projection.source_dispositions:
        body["source_dispositions"] = [item.to_json() for item in projection.source_dispositions]
    return body


def _stable_key_from_ref(reference: str) -> str:
    parts = reference.split("/")
    if (
        len(parts) != _REFERENCE_PARTS
        or parts[0] != "legislation-item"
        or _STABLE_KEY.fullmatch(parts[1]) is None
    ):
        _fail("LEGISLATION_VERIFIED_INPUT_INVALID")
    if len(parts[2]) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in parts[2]
    ):
        _fail("LEGISLATION_VERIFIED_INPUT_INVALID")
    return parts[1]


def _validate_graph(  # noqa: C901, PLR0912, PLR0915 - one exact provenance boundary.
    graph: LegislationWorkGraph,
) -> None:
    if (
        type(graph.cycle_id) is not str
        or _CYCLE.fullmatch(graph.cycle_id) is None
        or type(graph.observation_cutoff) is not str
        or _UTC.fullmatch(graph.observation_cutoff) is None
        or type(graph.gld_window) is not GldGazetteWindow
        or type(graph.nodes) is not tuple
        or not graph.nodes
        or _FINGERPRINT.fullmatch(graph.fingerprint) is None
    ):
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    try:
        graph.gld_window.__post_init__()
    except (TypeError, ValueError) as error:
        code = "LEGISLATION_WORK_GRAPH_INVALID"
        raise ValueError(code) from error
    if graph.gld_window.observation_cutoff != graph.observation_cutoff:
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    register = load_hk_legislation_source_register()
    nodes: list[LegislationWorkNode] = []
    for node in graph.nodes:
        if (
            type(node) is not LegislationWorkNode
            or type(node.stable_key) is not str
            or _STABLE_KEY.fullmatch(node.stable_key) is None
            or type(node.kind) is not LegislationWorkKind
            or type(node.scope_ids) is not tuple
            or not node.scope_ids
            or tuple(sorted(set(node.scope_ids))) != node.scope_ids
            or not set(node.scope_ids).issubset(LEGISLATION_SCOPE_IDS)
            or type(node.dependency_keys) is not tuple
            or tuple(sorted(set(node.dependency_keys))) != node.dependency_keys
            or type(node.scheduled) is not ScheduledWorkItem
            or type(node.source_id) is not str
            or type(node.endpoint_id) is not str
            or node.source_register_fingerprint != register.fingerprint
            or _FINGERPRINT.fullmatch(node.source_input_fingerprint) is None
        ):
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
        try:
            ScheduledWorkItem(
                node.scheduled.identity,
                node.scheduled.priority,
                node.scheduled.host,
                node.scheduled.not_before_monotonic_ns,
            )
        except (TypeError, ValueError) as error:
            code = "LEGISLATION_WORK_GRAPH_INVALID"
            raise ValueError(code) from error
        try:
            source, endpoint = register.resolve_registered_endpoint(node.endpoint_id)
        except (LookupError, TypeError, ValueError) as error:
            code = "LEGISLATION_WORK_GRAPH_INVALID"
            raise ValueError(code) from error
        identity = node.scheduled.identity
        endpoint_host = urlsplit(endpoint.url).hostname
        dynamic_gld = node.kind is LegislationWorkKind.GLD_EVENT_ARTIFACT
        locator_matches = (
            urlsplit(identity.locator).hostname == endpoint_host
            and "{" not in identity.locator
            and "}" not in identity.locator
            if dynamic_gld
            else identity.locator == endpoint.url
        )
        expected_scopes = (
            _CONSTITUTIONAL_SCOPE
            if node.kind
            in {
                LegislationWorkKind.BASIC_LAW,
                LegislationWorkKind.ANNEX_III,
                LegislationWorkKind.INSTRUMENTS_AND_OTHERS,
            }
            else _ALL_SCOPES
        )
        if (
            node.endpoint_id not in _ENDPOINTS_BY_KIND[node.kind]
            or node.source_id != source.source_id
            or identity.source_family != "LEGISLATION"
            or identity.source_role != source.source_id.replace("-", "_")
            or identity.cycle_id != graph.cycle_id
            or identity.observation_cutoff != graph.observation_cutoff
            or identity.procedure_version != endpoint.version
            or identity.stage != node.kind.value
            or identity.parent_id != node.stable_key
            or identity.media_type not in endpoint.media_types
            or identity.max_bytes != min(endpoint.max_bytes, _MAX_OBJECT_BYTES)
            or node.scheduled.host != endpoint_host
            or node.scheduled.not_before_monotonic_ns != 0
            or node.scope_ids != expected_scopes
            or not locator_matches
        ):
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
        nodes.append(node)
    stable_nodes = tuple(nodes)
    keys = tuple(item.stable_key for item in stable_nodes)
    if (
        keys != tuple(sorted(set(keys)))
        or {item.kind for item in stable_nodes} != set(LegislationWorkKind)
        or {scope for item in stable_nodes for scope in item.scope_ids}
        != set(LEGISLATION_SCOPE_IDS)
        or any(set(item.dependency_keys) - set(keys) for item in stable_nodes)
        or any(item.stable_key in item.dependency_keys for item in stable_nodes)
    ):
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    by_key = {item.stable_key: item for item in stable_nodes}
    keys_by_kind = {
        kind: tuple(node.stable_key for node in stable_nodes if node.kind is kind)
        for kind in LegislationWorkKind
    }
    for node in stable_nodes:
        expected_dependencies = (
            keys_by_kind[LegislationWorkKind.HKEL_CURRENT_INVENTORY]
            if node.kind
            in {
                LegislationWorkKind.HKEL_CURRENT_ARCHIVE,
                LegislationWorkKind.HKEL_EDITORIAL_RECORD,
                LegislationWorkKind.HKEL_VERIFIED_COPY,
                LegislationWorkKind.HKEL_ASSISTED_COPY,
            }
            else keys_by_kind[LegislationWorkKind.BASIC_LAW]
            if node.kind
            in {LegislationWorkKind.ANNEX_III, LegislationWorkKind.INSTRUMENTS_AND_OTHERS}
            else ()
        )
        if node.kind is not LegislationWorkKind.GLD_EVENT_ARTIFACT and (
            node.dependency_keys != expected_dependencies
        ):
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
    for kind, endpoint_ids in _ENDPOINTS_BY_KIND.items():
        if kind is LegislationWorkKind.GLD_EVENT_ARTIFACT:
            continue
        actual = tuple(sorted(node.endpoint_id for node in stable_nodes if node.kind is kind))
        if actual != tuple(sorted(endpoint_ids)):
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
    discovery_nodes = tuple(
        node for node in stable_nodes if node.kind is LegislationWorkKind.GLD_ISSUE_DISCOVERY
    )
    if len(discovery_nodes) != 1:
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    discovery = discovery_nodes[0]
    if (
        discovery.endpoint_id != graph.gld_window.endpoint_id
        or discovery.source_input_fingerprint != graph.gld_window.listing_fingerprint
        or discovery.dependency_keys
    ):
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    try:
        projected_artifacts = project_gld_artifact_requests(graph.gld_window)
    except (TypeError, ValueError) as error:
        code = "LEGISLATION_WORK_GRAPH_INVALID"
        raise ValueError(code) from error
    expected_artifacts = {
        f"gld-event-artifact-{item.stable_identity}": item for item in projected_artifacts
    }
    actual_artifacts = {
        node.stable_key: node
        for node in stable_nodes
        if node.kind is LegislationWorkKind.GLD_EVENT_ARTIFACT
    }
    if set(actual_artifacts) != set(expected_artifacts):
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    for stable_key, artifact in expected_artifacts.items():
        node = actual_artifacts[stable_key]
        if (
            node.endpoint_id != artifact.endpoint_id
            or node.scheduled.identity.procedure_version != artifact.endpoint_version
            or node.scheduled.identity.locator != artifact.locator
            or node.source_input_fingerprint != artifact.listing_fingerprint
            or node.dependency_keys != (discovery.stable_key,)
        ):
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(stable_key: str) -> None:
        if stable_key in visiting:
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
        if stable_key in visited:
            return
        visiting.add(stable_key)
        for dependency in by_key[stable_key].dependency_keys:
            visit(dependency)
        visiting.remove(stable_key)
        visited.add(stable_key)

    for index, node in enumerate(stable_nodes):
        if node.scheduled.priority != (
            tuple(LegislationWorkKind).index(node.kind),
            index,
            node.stable_key,
        ):
            _fail("LEGISLATION_WORK_GRAPH_INVALID")
        visit(node.stable_key)
    body = _graph_body(
        graph.cycle_id,
        graph.observation_cutoff,
        graph.gld_window,
        stable_nodes,
    )
    expected = f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"
    if graph.fingerprint != expected:
        _fail("LEGISLATION_WORK_GRAPH_INVALID")


def legislation_runner_dependencies(
    graph: object,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Translate stable graph prerequisites to the shared runner's work identities."""
    if type(graph) is not LegislationWorkGraph:
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    _validate_graph(graph)
    work_id_by_key = {node.stable_key: node.scheduled.identity.work_item_id for node in graph.nodes}
    return tuple(
        (
            node.scheduled.identity.work_item_id,
            tuple(sorted(work_id_by_key[key] for key in node.dependency_keys)),
        )
        for node in graph.nodes
    )


class _ClassifiedLegislationTransport:
    """Translate only closed GLD session failures into shared-runner outcomes."""

    def __init__(
        self,
        graph: LegislationWorkGraph,
        transport: CaptureTransport,
        clock: AcquisitionClock,
    ) -> None:
        self._nodes = {node.scheduled.identity.work_item_id: node for node in graph.nodes}
        self._transport = transport
        self._clock = clock

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        node = self._nodes.get(item.work_item_id)
        if node is None:
            _fail("LEGISLATION_REPORT_MEMBERSHIP_MISMATCH")
        try:
            return self._transport.capture(item)
        except GldSessionError as error:
            if node.kind not in {
                LegislationWorkKind.GLD_ISSUE_DISCOVERY,
                LegislationWorkKind.GLD_EVENT_ARTIFACT,
            }:
                raise
            classification = classify_gld_session_failure(error)
            contract = classification is GldSessionFailureClass.CONTRACT
            retry_not_before = None
            if not contract:
                now = self._clock.now()
                if type(now) is not datetime:
                    _fail("LEGISLATION_ACTIVITY_CLOCK_INVALID")
                retry_not_before = now.astimezone(UTC).replace(microsecond=0).isoformat()
            return CaptureOutcome(
                work_item_id=item.work_item_id,
                transition=(
                    JournalTransition.CONTRACT_REJECTED
                    if contract
                    else JournalTransition.RETRYABLE_FAILURE
                ),
                status_code=None,
                media_type=None,
                final_url=None,
                body_length=0,
                body_fingerprint=None,
                object_ref=None,
                failure_code=(
                    AcquisitionFailureCode.SOURCE_CONTRACT_CHANGED.value
                    if contract
                    else AcquisitionFailureCode.SOURCE_UNAVAILABLE.value
                ),
                retry_not_before=retry_not_before,
                read_back_verified=False,
                redirect_chain=(),
            )


def _observed_hkel_archive_keys(
    baseline: HkelImportedBaseline,
    value: tuple[HkelArchiveReuseKey, ...] | None,
) -> tuple[HkelArchiveReuseKey, ...]:
    observed = baseline.archive_reuse_keys if value is None else value
    if (
        type(observed) is not tuple
        or any(type(item) is not HkelArchiveReuseKey for item in observed)
        or tuple(item.archive_endpoint_id for item in observed)
        != tuple(item.archive_endpoint_id for item in baseline.archive_reuse_keys)
    ):
        _fail("HKEL_ARCHIVE_SELECTION_INVALID")
    return observed


def run_legislation_resumable_graph(  # noqa: PLR0913 - exact shared-runner composition.
    *,
    state_root: Path,
    graph: LegislationWorkGraph,
    transport: CaptureTransport,
    retained_verifier: RetainedObjectVerifier,
    clock: AcquisitionClock,
    sleeper: Callable[[float], None],
    budget: CycleBudget,
    baseline: HkelImportedBaseline | None = None,
    observed_archive_reuse_keys: tuple[HkelArchiveReuseKey, ...] | None = None,
) -> AcquisitionCycleReport:
    """Run one registered legislation graph through the sole shared runner."""
    if type(state_root) is not type(Path()) or not state_root.is_absolute():
        _fail("LEGISLATION_ACTIVITY_CONFIGURATION_INVALID")
    _validate_graph(graph)
    preverified_imports: tuple[tuple[str, ImportedCaptureVerifiedPayload], ...] = ()
    if baseline is not None:
        exact_baseline = _validate_baseline(baseline)
        observed = _observed_hkel_archive_keys(exact_baseline, observed_archive_reuse_keys)
        try:
            reparse = {
                item.archive_endpoint_id
                for item in select_hkel_archives_to_reparse(
                    observed, exact_baseline.archive_reuse_keys
                )
            }
        except (TypeError, ValueError) as error:
            code = "HKEL_ARCHIVE_SELECTION_INVALID"
            raise ValueError(code) from error
        reference_by_endpoint = {
            item.endpoint_id: item for item in exact_baseline.archive_object_references
        }
        preverified_imports = tuple(
            (
                node.scheduled.identity.work_item_id,
                ImportedCaptureVerifiedPayload(
                    source_attempt_id=reference.source_attempt_id,
                    source_report_fingerprint=reference.source_report_fingerprint,
                    authority_manifest_fingerprint=reference.authority_manifest_fingerprint,
                    execution_authorization_fingerprint=(
                        reference.execution_authorization_fingerprint
                    ),
                    status=200,
                    media_type=reference.media_type,
                    final_url=reference.final_url,
                    body_length=reference.body_length,
                    content_fingerprint=reference.content_fingerprint,
                    object_ref=reference.object_ref,
                    read_back_verified=True,
                ),
            )
            for node in graph.nodes
            if node.kind is LegislationWorkKind.HKEL_CURRENT_ARCHIVE
            and node.endpoint_id not in reparse
            for reference in (reference_by_endpoint[node.endpoint_id],)
        )
    classified_transport = _ClassifiedLegislationTransport(graph, transport, clock)
    with LocalAcquisitionJournal(state_root, graph.cycle_id) as journal:
        return ResumableAcquisitionRunner(
            journal=journal,
            items=tuple(node.scheduled for node in graph.nodes),
            transport=classified_transport,
            retained_verifier=retained_verifier,
            clock=clock,
            sleeper=sleeper,
            budget=budget,
            maximum_attempts_per_item=2,
            dependencies=legislation_runner_dependencies(graph),
            preverified_imports=preverified_imports,
        ).run()


def _runner_verified_items(
    graph: LegislationWorkGraph,
    report: AcquisitionCycleReport,
) -> tuple[LegislationVerifiedItem, ...]:
    """Project only the runner's journal-derived retained-body identities."""
    by_work_id = {node.scheduled.identity.work_item_id: node for node in graph.nodes}
    try:
        bindings = runner_verified_capture_bindings(report)
    except (TypeError, ValueError, RuntimeError) as error:
        code = "LEGISLATION_REPORT_NOT_RUNNER_ISSUED"
        raise ValueError(code) from error
    if any(binding.work_item_id not in by_work_id for binding in bindings):
        _fail("LEGISLATION_REPORT_MEMBERSHIP_MISMATCH")
    return tuple(
        sorted(
            (
                LegislationVerifiedItem.issue(
                    by_work_id[binding.work_item_id].stable_key,
                    binding.object_ref,
                    binding.content_fingerprint,
                )
                for binding in bindings
            ),
            key=lambda item: item.stable_key,
        )
    )


def advance_hkel_baseline_from_cycle(
    baseline: object,
    graph: object,
    report: object,
    admission: HkelArchiveBodyAdmissionPort,
    observed_archive_reuse_keys: tuple[HkelArchiveReuseKey, ...] | None = None,
) -> HkelImportedBaseline:
    """Advance archive reuse facts only after a trusted full-body admission outcome."""
    exact_baseline = _validate_baseline(baseline)
    if (
        type(graph) is not LegislationWorkGraph
        or type(report) is not AcquisitionCycleReport
        or report.cycle_id != graph.cycle_id
        or not callable(getattr(admission, "admit_archive", None))
    ):
        _fail("HKEL_ARCHIVE_ADMISSION_INVALID")
    _validate_graph(graph)
    _validate_cycle_report(report)
    bindings = runner_verified_capture_bindings(report)
    nodes = {node.scheduled.identity.work_item_id: node for node in graph.nodes}
    prior_by_endpoint = {
        item.archive_endpoint_id: item for item in exact_baseline.archive_reuse_keys
    }
    observed_keys = _observed_hkel_archive_keys(exact_baseline, observed_archive_reuse_keys)
    observed_by_endpoint = {item.archive_endpoint_id: item for item in observed_keys}
    replacements: dict[str, HkelArchiveReuseKey] = {}
    admitted_facts: list[dict[str, JsonValue]] = []
    for binding in bindings:
        node = nodes.get(binding.work_item_id)
        if node is None:
            _fail("LEGISLATION_REPORT_MEMBERSHIP_MISMATCH")
        if node.kind is not LegislationWorkKind.HKEL_CURRENT_ARCHIVE:
            continue
        prior = prior_by_endpoint[node.endpoint_id]
        observed = observed_by_endpoint.get(node.endpoint_id)
        if observed is None:
            _fail("HKEL_ARCHIVE_SELECTION_INVALID")
        if binding.content_fingerprint != observed.archive_fingerprint:
            _fail("HKEL_ARCHIVE_SELECTION_INVALID")
        if binding.content_fingerprint == prior.archive_fingerprint and observed == prior:
            continue
        admitted = admission.admit_archive(
            source_role=node.scheduled.identity.source_role,
            endpoint_id=node.endpoint_id,
            object_ref=binding.object_ref,
            content_fingerprint=binding.content_fingerprint,
        )
        if admitted is not True:
            _fail("HKEL_ARCHIVE_ADMISSION_REJECTED")
        replacements[node.endpoint_id] = HkelArchiveReuseKey.issue(
            node.endpoint_id,
            binding.content_fingerprint,
            observed.publication_profile_fingerprint,
        )
        admitted_facts.append(
            {
                "content_fingerprint": binding.content_fingerprint,
                "endpoint_id": node.endpoint_id,
                "object_ref": binding.object_ref,
            }
        )
    if not replacements:
        return exact_baseline
    archive_reuse_keys = tuple(
        replacements.get(item.archive_endpoint_id, item)
        for item in exact_baseline.archive_reuse_keys
    )
    binding_by_endpoint = {
        nodes[item.work_item_id].endpoint_id: item
        for item in bindings
        if nodes[item.work_item_id].kind is LegislationWorkKind.HKEL_CURRENT_ARCHIVE
    }
    reference_by_endpoint = {
        item.endpoint_id: item for item in exact_baseline.archive_object_references
    }
    archive_object_references = tuple(
        (
            reference_by_endpoint[item.archive_endpoint_id]
            if item.archive_endpoint_id not in replacements
            else HkelArchiveObjectReference(
                endpoint_id=item.archive_endpoint_id,
                work_item_id=nodes[
                    binding_by_endpoint[item.archive_endpoint_id].work_item_id
                ].scheduled.identity.work_item_id,
                media_type=nodes[
                    binding_by_endpoint[item.archive_endpoint_id].work_item_id
                ].scheduled.identity.media_type,
                final_url=nodes[
                    binding_by_endpoint[item.archive_endpoint_id].work_item_id
                ].scheduled.identity.locator,
                body_length=binding_by_endpoint[item.archive_endpoint_id].body_length,
                content_fingerprint=binding_by_endpoint[
                    item.archive_endpoint_id
                ].content_fingerprint,
                object_ref=binding_by_endpoint[item.archive_endpoint_id].object_ref,
                provenance_kind=HkelArchiveProvenanceKind.CURRENT_CYCLE_CAPTURE,
                source_cycle_id=report.cycle_id,
                source_attempt_id=f"runner-{report.cycle_id}",
                source_report_fingerprint=report.fingerprint,
                authority_manifest_fingerprint=graph.fingerprint,
                execution_authorization_fingerprint=report.fingerprint,
                source_journal_head_fingerprint=report.journal_head_fingerprint,
            )
        )
        for item in archive_reuse_keys
    )
    proof_body = {
        "admitted_archives": sorted(admitted_facts, key=lambda item: str(item["endpoint_id"])),
        "prior_source_observation_fingerprint": exact_baseline.source_observation_fingerprint,
        "prior_structure_profile_fingerprint": exact_baseline.structure_profile_fingerprint,
    }
    proof = f"sha256:{sha256(canonicalize(checked_json_value(proof_body))).hexdigest()}"
    return _issue_baseline(
        HkelImportedBaseline(
            exact_baseline.source_report_fingerprint,
            exact_baseline.imported_work_item_ids,
            exact_baseline.archive_member_count,
            exact_baseline.bilingual_pair_count,
            exact_baseline.publication_specification_count,
            archive_reuse_keys,
            archive_object_references,
            exact_baseline.review_issue_refs,
            proof,
            proof,
            exact_baseline.import_cycle_id,
            exact_baseline.source_attempt_id,
            exact_baseline.receipt_fingerprint,
            exact_baseline.work_item_lineage_fingerprint,
            "",
        )
    )


def run_legislation_acquisition_cycle(  # noqa: PLR0913 - complete injected composition.
    *,
    state_root: Path,
    graph: LegislationWorkGraph,
    transport: CaptureTransport,
    retained_verifier: RetainedObjectVerifier,
    clock: AcquisitionClock,
    sleeper: Callable[[float], None],
    budget: CycleBudget,
    baseline: HkelImportedBaseline,
    archive_admission: HkelArchiveBodyAdmissionPort,
    review_issue_refs: object,
    previous: LegislationAcceptedSourceState | None = None,
    observed_archive_reuse_keys: tuple[HkelArchiveReuseKey, ...] | None = None,
) -> LegislationAcquisitionCycle:
    """Compose registered work, shared runner, body admission, and manifest projection."""
    report = run_legislation_resumable_graph(
        state_root=state_root,
        graph=graph,
        transport=transport,
        retained_verifier=retained_verifier,
        clock=clock,
        sleeper=sleeper,
        budget=budget,
        baseline=baseline,
        observed_archive_reuse_keys=observed_archive_reuse_keys,
    )
    verified_items = _runner_verified_items(graph, report)
    next_baseline = advance_hkel_baseline_from_cycle(
        baseline,
        graph,
        report,
        archive_admission,
        observed_archive_reuse_keys,
    )
    manifest = build_legislation_acquisition_manifest(
        graph,
        report,
        verified_items,
        review_issue_refs,
        next_baseline,
        previous=previous,
    )
    return LegislationAcquisitionCycle(report, verified_items, next_baseline, manifest)


def _work_plan_fingerprint(graph: LegislationWorkGraph) -> str:
    """Hash graph facts that must remain equal across source cycles."""
    body = {
        "nodes": [
            {
                "dependency_keys": list(node.dependency_keys),
                "endpoint_id": node.endpoint_id,
                "kind": node.kind.value,
                "locator": node.scheduled.identity.locator,
                "max_bytes": node.scheduled.identity.max_bytes,
                "media_type": node.scheduled.identity.media_type,
                "parent_id": node.scheduled.identity.parent_id,
                "procedure_version": node.scheduled.identity.procedure_version,
                "scope_ids": list(node.scope_ids),
                "source_id": node.source_id,
                "source_register_fingerprint": node.source_register_fingerprint,
                "source_role": node.scheduled.identity.source_role,
                "stable_key": node.stable_key,
                "stage": node.scheduled.identity.stage,
            }
            for node in graph.nodes
        ]
    }
    return f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"


def _validate_cycle_report(report: AcquisitionCycleReport) -> None:
    if (
        type(report.cycle_id) is not str
        or _CYCLE.fullmatch(report.cycle_id) is None
        or type(report.result) is not AcquisitionCycleResult
        or type(report.item_dispositions) is not tuple
        or type(report.request_starts) is not int
        or report.request_starts < 0
        or type(report.retained_bytes) is not int
        or report.retained_bytes < 0
        or type(report.journal_head_fingerprint) is not str
        or _FINGERPRINT.fullmatch(report.journal_head_fingerprint) is None
        or type(report.fingerprint) is not str
        or _FINGERPRINT.fullmatch(report.fingerprint) is None
    ):
        _fail("LEGISLATION_REPORT_INVALID")
    for item in report.item_dispositions:
        if type(item) is not CheckpointItem:
            _fail("LEGISLATION_REPORT_INVALID")
        try:
            CheckpointItem(
                item.work_item_id,
                item.latest_sequence,
                item.transition,
                item.attempt_count,
                item.object_ref,
                item.retry_not_before,
            )
        except (TypeError, ValueError) as error:
            code = "LEGISLATION_REPORT_INVALID"
            raise ValueError(code) from error
    document = report.to_json()
    supplied = document.pop("fingerprint")
    expected = f"sha256:{sha256(canonicalize(document)).hexdigest()}"
    if supplied != expected:
        _fail("LEGISLATION_REPORT_INVALID")


def _validate_manifest(manifest: LegislationAcquisitionManifest) -> None:
    try:
        source_dispositions = validate_source_role_dispositions(manifest.source_dispositions)
    except (AttributeError, TypeError, ValueError) as error:
        code = "LEGISLATION_MANIFEST_INVALID"
        raise ValueError(code) from error
    if (
        type(manifest.cycle_id) is not str
        or _CYCLE.fullmatch(manifest.cycle_id) is None
        or type(manifest.observation_cutoff) is not str
        or _UTC.fullmatch(manifest.observation_cutoff) is None
        or type(manifest.scope_dispositions) is not tuple
        or type(manifest.verified_item_refs) is not tuple
        or type(manifest.review_issue_refs) is not tuple
        or type(manifest.journal_head_fingerprint) is not str
        or _FINGERPRINT.fullmatch(manifest.journal_head_fingerprint) is None
        or _FINGERPRINT.fullmatch(manifest.source_register_fingerprint) is None
        or _FINGERPRINT.fullmatch(manifest.source_baseline_fingerprint) is None
        or _FINGERPRINT.fullmatch(manifest.work_plan_fingerprint) is None
        or type(manifest.result) is not AcquisitionCycleResult
        or type(manifest.fingerprint) is not str
        or _FINGERPRINT.fullmatch(manifest.fingerprint) is None
    ):
        _fail("LEGISLATION_MANIFEST_INVALID")
    scopes: list[LegislationScopeDisposition] = []
    for scope in manifest.scope_dispositions:
        if (
            type(scope) is not LegislationScopeDisposition
            or type(scope.scope_id) is not str
            or type(scope.required_item_count) is not int
            or type(scope.verified_item_count) is not int
            or type(scope.retryable_item_count) is not int
            or type(scope.rejected_item_count) is not int
            or type(scope.result) is not AcquisitionCycleResult
            or scope.required_item_count < 1
            or min(
                scope.verified_item_count,
                scope.retryable_item_count,
                scope.rejected_item_count,
            )
            < 0
            or scope.verified_item_count + scope.retryable_item_count + scope.rejected_item_count
            != scope.required_item_count
        ):
            _fail("LEGISLATION_MANIFEST_INVALID")
        scopes.append(scope)
    stable_scopes = tuple(scopes)
    if tuple(item.scope_id for item in stable_scopes) != LEGISLATION_SCOPE_IDS:
        _fail("LEGISLATION_MANIFEST_INVALID")
    if manifest.result in {
        AcquisitionCycleResult.COMPLETE,
        AcquisitionCycleResult.NO_CHANGE,
    } and (
        any(
            item.result is not manifest.result
            or item.verified_item_count != item.required_item_count
            or item.retryable_item_count != 0
            or item.rejected_item_count != 0
            for item in stable_scopes
        )
        or any(
            item.result not in {AcquisitionCycleResult.COMPLETE, AcquisitionCycleResult.NO_CHANGE}
            for item in source_dispositions
        )
    ):
        _fail("LEGISLATION_MANIFEST_INVALID")
    verified = _exact_string_tuple(manifest.verified_item_refs)
    reviews = _exact_string_tuple(manifest.review_issue_refs)
    if (
        verified != tuple(sorted(set(verified)))
        or reviews != tuple(sorted(set(reviews)))
        or any(_REFERENCE.fullmatch(item) is None for item in reviews)
    ):
        _fail("LEGISLATION_MANIFEST_INVALID")
    for reference in verified:
        _stable_key_from_ref(reference)
    projection = _ManifestProjection(
        manifest.cycle_id,
        manifest.observation_cutoff,
        stable_scopes,
        verified,
        reviews,
        manifest.journal_head_fingerprint,
        manifest.source_register_fingerprint,
        manifest.source_baseline_fingerprint,
        manifest.work_plan_fingerprint,
        manifest.result,
        source_dispositions,
    )
    expected = (
        f"sha256:{sha256(canonicalize(checked_json_value(_manifest_body(projection)))).hexdigest()}"
    )
    if manifest.fingerprint != expected:
        _fail("LEGISLATION_MANIFEST_INVALID")


def load_accepted_legislation_source_state(
    manifest: object,
    store: AcquisitionRegisterStore,
    observation_id: object,
) -> LegislationAcceptedSourceState:
    """Load one exact register-preserved source snapshot bound to a complete manifest."""
    if (
        type(manifest) is not LegislationAcquisitionManifest
        or type(observation_id) is not str
        or not observation_id
        or not callable(getattr(store, "get_observation", None))
    ):
        _fail("LEGISLATION_ACCEPTED_SOURCE_STATE_INVALID")
    _validate_manifest(manifest)
    if manifest.result not in {
        AcquisitionCycleResult.COMPLETE,
        AcquisitionCycleResult.NO_CHANGE,
    }:
        _fail("LEGISLATION_ACCEPTED_SOURCE_STATE_INVALID")
    try:
        record = store.get_observation(observation_id)
    except Exception as error:
        code = "LEGISLATION_ACCEPTED_SOURCE_STATE_INVALID"
        raise ValueError(code) from error
    if (
        type(record) is not AcquisitionObservationRecord
        or record.observation_id != observation_id
        or record.source_id != "HK-LEG-HKEL-CURRENT-INVENTORY"
        or record.endpoint_id not in _ENDPOINTS_BY_KIND[LegislationWorkKind.HKEL_CURRENT_INVENTORY]
        or record.observation_cutoff != manifest.observation_cutoff
        or record.input_fingerprint != manifest.fingerprint
        or record.manifest_fingerprint != manifest.fingerprint
        or record.watcher_result != "POSSIBLE_CHANGE"
        or record.scraper_result != "SNAPSHOT_PRESERVED"
        or record.disposition != "SNAPSHOT_PRESERVED"
        or record.consequence != "LEGAL_PROCESSING_ELIGIBLE"
    ):
        _fail("LEGISLATION_ACCEPTED_SOURCE_STATE_INVALID")
    provenance_body = {
        "evidence_package_id": record.evidence_package_id,
        "manifest_fingerprint": manifest.fingerprint,
        "observation_id": record.observation_id,
        "primary_manifest_version": record.primary_manifest_version,
        "recovery_manifest_version": record.recovery_manifest_version,
        "source_snapshot_id": record.source_snapshot_id,
    }
    fingerprint = "sha256:" + sha256(canonicalize(checked_json_value(provenance_body))).hexdigest()
    state = LegislationAcceptedSourceState(
        manifest,
        record.observation_id,
        record.source_snapshot_id,
        fingerprint,
    )
    identity = id(state)

    def cleanup(reference: weakref.ReferenceType[object]) -> None:
        issued = _ACCEPTED_STATE_ISSUANCE.get(identity)
        if issued is not None and issued.reference is reference:
            del _ACCEPTED_STATE_ISSUANCE[identity]

    _ACCEPTED_STATE_ISSUANCE[identity] = _IssuedAcceptedSourceState(
        weakref.ref(state, cleanup),
        manifest.fingerprint,
        record.observation_id,
        record.source_snapshot_id,
        record.evidence_package_id,
        record.primary_manifest_version,
        record.recovery_manifest_version,
    )
    return state


def _accepted_source_manifest(value: object) -> LegislationAcquisitionManifest:
    if type(value) is not LegislationAcceptedSourceState:
        _fail("LEGISLATION_ACCEPTED_SOURCE_STATE_REQUIRED")
    issued = _ACCEPTED_STATE_ISSUANCE.get(id(value))
    if issued is None or issued.reference() is not value:
        _fail("LEGISLATION_ACCEPTED_SOURCE_STATE_INVALID")
    try:
        _validate_manifest(value.manifest)
    except ValueError as error:
        code = "LEGISLATION_ACCEPTED_SOURCE_STATE_INVALID"
        raise ValueError(code) from error
    provenance_body = {
        "evidence_package_id": issued.evidence_package_id,
        "manifest_fingerprint": value.manifest.fingerprint,
        "observation_id": value.observation_id,
        "primary_manifest_version": issued.primary_manifest_version,
        "recovery_manifest_version": issued.recovery_manifest_version,
        "source_snapshot_id": value.source_snapshot_id,
    }
    expected = "sha256:" + sha256(canonicalize(checked_json_value(provenance_body))).hexdigest()
    if (
        value.manifest.fingerprint != issued.manifest_fingerprint
        or value.observation_id != issued.observation_id
        or value.source_snapshot_id != issued.source_snapshot_id
        or value.provenance_fingerprint != expected
    ):
        _fail("LEGISLATION_ACCEPTED_SOURCE_STATE_INVALID")
    return value.manifest


def changed_legislation_inputs(
    current: object,
    previous: object,
) -> tuple[LegislationVerifiedItem, ...]:
    """Return only stable inputs whose complete verified identity changed."""
    if not _object_tuple(current):
        _fail("LEGISLATION_VERIFIED_INPUT_INVALID")
    rebuilt_items: list[LegislationVerifiedItem] = []
    for item in current:
        if type(item) is not LegislationVerifiedItem:
            _fail("LEGISLATION_VERIFIED_INPUT_INVALID")
        rebuilt_items.append(
            LegislationVerifiedItem.issue(
                item.stable_key, item.object_ref, item.content_fingerprint
            )
        )
    rebuilt = tuple(rebuilt_items)
    if len({item.stable_key for item in rebuilt}) != len(rebuilt):
        _fail("LEGISLATION_VERIFIED_INPUT_INVALID")
    if previous is None:
        return tuple(sorted(rebuilt, key=lambda item: item.stable_key))
    if type(previous) is not LegislationAcquisitionManifest:
        _fail("LEGISLATION_MANIFEST_INVALID")
    _validate_manifest(previous)
    prior = {_stable_key_from_ref(item): item for item in previous.verified_item_refs}
    return tuple(
        item
        for item in sorted(rebuilt, key=lambda value: value.stable_key)
        if prior.get(item.stable_key) != item.reference
    )


def _validated_verified_items(
    graph: LegislationWorkGraph,
    report: AcquisitionCycleReport,
    verified_items: object,
    capture_bindings: tuple[VerifiedCaptureBinding, ...],
) -> tuple[
    dict[str, CheckpointItem],
    tuple[LegislationVerifiedItem, ...],
]:
    dispositions = {item.work_item_id: item for item in report.item_dispositions}
    by_work_id = {node.scheduled.identity.work_item_id: node for node in graph.nodes}
    if set(dispositions) != set(by_work_id) or len(dispositions) != len(report.item_dispositions):
        _fail("LEGISLATION_REPORT_MEMBERSHIP_MISMATCH")
    if not _object_tuple(verified_items):
        _fail("LEGISLATION_VERIFIED_INPUT_INVALID")
    typed_verified: list[LegislationVerifiedItem] = []
    for item in verified_items:
        if type(item) is not LegislationVerifiedItem:
            _fail("LEGISLATION_VERIFIED_INPUT_INVALID")
        typed_verified.append(
            LegislationVerifiedItem.issue(
                item.stable_key, item.object_ref, item.content_fingerprint
            )
        )
    exact_verified = tuple(typed_verified)
    verified_by_key = {item.stable_key: item for item in exact_verified}
    successful_keys = {
        node.stable_key
        for work_id, node in by_work_id.items()
        if dispositions[work_id].transition in _SUCCESS
    }
    captures_by_work_id = {item.work_item_id: item for item in capture_bindings}
    if (
        len(captures_by_work_id) != len(capture_bindings)
        or set(captures_by_work_id)
        != {work_id for work_id, item in dispositions.items() if item.transition in _SUCCESS}
        or len(verified_by_key) != len(exact_verified)
        or set(verified_by_key) != successful_keys
        or any(
            (
                dispositions[node.scheduled.identity.work_item_id].object_ref
                != verified_by_key[node.stable_key].object_ref
                or captures_by_work_id[node.scheduled.identity.work_item_id].object_ref
                != verified_by_key[node.stable_key].object_ref
                or captures_by_work_id[node.scheduled.identity.work_item_id].content_fingerprint
                != verified_by_key[node.stable_key].content_fingerprint
            )
            for node in graph.nodes
            if node.stable_key in successful_keys
        )
    ):
        _fail("LEGISLATION_VERIFIED_INPUT_MISMATCH")
    return dispositions, exact_verified


def build_legislation_acquisition_manifest(  # noqa: PLR0913 - complete manifest evidence.
    graph: object,
    report: object,
    verified_items: object,
    review_issue_refs: object,
    baseline: object,
    *,
    previous: object = None,
) -> LegislationAcquisitionManifest:
    """Project graph and journal accounting into one strict three-scope manifest."""
    if (
        type(graph) is not LegislationWorkGraph
        or type(report) is not AcquisitionCycleReport
        or report.cycle_id != graph.cycle_id
        or _FINGERPRINT.fullmatch(report.journal_head_fingerprint) is None
    ):
        _fail("LEGISLATION_MANIFEST_INVALID")
    _validate_graph(graph)
    exact_baseline = _validate_baseline(baseline)
    _validate_cycle_report(report)
    try:
        capture_bindings = runner_verified_capture_bindings(report)
    except (TypeError, ValueError, RuntimeError) as error:
        code = "LEGISLATION_REPORT_NOT_RUNNER_ISSUED"
        raise ValueError(code) from error
    prior_manifest = None if previous is None else _accepted_source_manifest(previous)
    reviews = tuple(
        sorted(set(_exact_string_tuple(review_issue_refs)) | set(exact_baseline.review_issue_refs))
    )
    if (
        any(_REFERENCE.fullmatch(item) is None for item in reviews)
        or tuple(sorted(set(reviews))) != reviews
    ):
        _fail("LEGISLATION_MANIFEST_INVALID")
    dispositions, exact_verified = _validated_verified_items(
        graph,
        report,
        verified_items,
        capture_bindings,
    )
    archive_endpoint_ids = tuple(
        sorted(
            node.endpoint_id
            for node in graph.nodes
            if node.kind is LegislationWorkKind.HKEL_CURRENT_ARCHIVE
        )
    )
    if archive_endpoint_ids != tuple(
        item.archive_endpoint_id for item in exact_baseline.archive_reuse_keys
    ):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    source_register_fingerprints = {node.source_register_fingerprint for node in graph.nodes}
    if len(source_register_fingerprints) != 1:
        _fail("LEGISLATION_WORK_GRAPH_INVALID")
    source_register_fingerprint = next(iter(source_register_fingerprints))
    work_plan_fingerprint = _work_plan_fingerprint(graph)
    scopes: list[LegislationScopeDisposition] = []
    any_retryable = False
    any_rejected = False
    for scope_id in LEGISLATION_SCOPE_IDS:
        nodes = tuple(node for node in graph.nodes if scope_id in node.scope_ids)
        transitions = tuple(
            dispositions[node.scheduled.identity.work_item_id].transition for node in nodes
        )
        verified = sum(item in _SUCCESS for item in transitions)
        retryable = sum(item in _RETRYABLE for item in transitions)
        rejected = len(transitions) - verified - retryable
        any_retryable = any_retryable or retryable > 0
        any_rejected = any_rejected or rejected > 0
        scope_result = (
            AcquisitionCycleResult.INCOMPLETE_RETRYABLE
            if retryable
            else (
                report.result
                if rejected and report.result is not AcquisitionCycleResult.COMPLETE
                else (
                    AcquisitionCycleResult.INCOMPLETE_TERMINAL
                    if rejected
                    else AcquisitionCycleResult.COMPLETE
                )
            )
        )
        scopes.append(
            LegislationScopeDisposition(
                scope_id, len(nodes), verified, retryable, rejected, scope_result
            )
        )
    result = (
        report.result
        if any_rejected and report.result is not AcquisitionCycleResult.COMPLETE
        else (
            AcquisitionCycleResult.INCOMPLETE_TERMINAL
            if any_rejected
            else (
                AcquisitionCycleResult.INCOMPLETE_RETRYABLE
                if any_retryable
                else AcquisitionCycleResult.COMPLETE
            )
        )
    )
    if (
        not any_retryable
        and not any_rejected
        and report.result is not AcquisitionCycleResult.COMPLETE
    ):
        _fail("LEGISLATION_REPORT_RESULT_MISMATCH")
    verified_refs = tuple(sorted(item.reference for item in exact_verified))
    if (
        result is AcquisitionCycleResult.COMPLETE
        and prior_manifest is not None
        and prior_manifest.result
        in {AcquisitionCycleResult.COMPLETE, AcquisitionCycleResult.NO_CHANGE}
        and prior_manifest.source_register_fingerprint == source_register_fingerprint
        and prior_manifest.source_baseline_fingerprint == exact_baseline.fingerprint
        and prior_manifest.work_plan_fingerprint == work_plan_fingerprint
        and tuple(
            (item.scope_id, item.required_item_count) for item in prior_manifest.scope_dispositions
        )
        == tuple((item.scope_id, item.required_item_count) for item in scopes)
        and not changed_legislation_inputs(exact_verified, prior_manifest)
        and reviews == prior_manifest.review_issue_refs
    ):
        result = AcquisitionCycleResult.NO_CHANGE
        scopes = [
            LegislationScopeDisposition(
                item.scope_id,
                item.required_item_count,
                item.verified_item_count,
                item.retryable_item_count,
                item.rejected_item_count,
                AcquisitionCycleResult.NO_CHANGE,
            )
            for item in scopes
        ]
    stable_scopes = tuple(scopes)
    source_dispositions = _legislation_source_dispositions(graph, dispositions)
    body = _manifest_body(
        _ManifestProjection(
            graph.cycle_id,
            graph.observation_cutoff,
            stable_scopes,
            verified_refs,
            reviews,
            report.journal_head_fingerprint,
            source_register_fingerprint,
            exact_baseline.fingerprint,
            work_plan_fingerprint,
            result,
            source_dispositions,
        )
    )
    fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"
    return LegislationAcquisitionManifest(
        graph.cycle_id,
        graph.observation_cutoff,
        stable_scopes,
        verified_refs,
        reviews,
        report.journal_head_fingerprint,
        source_register_fingerprint,
        exact_baseline.fingerprint,
        work_plan_fingerprint,
        result,
        fingerprint,
        source_dispositions,
    )


def _legislation_source_dispositions(
    graph: LegislationWorkGraph,
    dispositions: dict[str, CheckpointItem],
) -> tuple[SourceRoleDisposition, ...]:
    """Project each source role from only its own scheduled journal items."""
    projected: list[SourceRoleDisposition] = []
    for source_id in sorted({node.source_id for node in graph.nodes}):
        nodes = tuple(node for node in graph.nodes if node.source_id == source_id)
        transitions = tuple(
            dispositions[node.scheduled.identity.work_item_id].transition for node in nodes
        )
        verified = sum(item in _SUCCESS for item in transitions)
        retryable = sum(item in _RETRYABLE for item in transitions)
        rejected = len(nodes) - verified - retryable
        result = (
            AcquisitionCycleResult.INCOMPLETE_RETRYABLE
            if retryable
            else AcquisitionCycleResult.INCOMPLETE_TERMINAL
            if rejected
            else AcquisitionCycleResult.COMPLETE
        )
        projected.append(
            SourceRoleDisposition(source_id, len(nodes), verified, retryable, rejected, result)
        )
    return validate_source_role_dispositions(tuple(projected))


def bind_imported_hkel_baseline(
    receipt: object,
    report: object,
    admission_document: object,
) -> HkelImportedBaseline:
    """Bind Task 4's 56 imported journal items to the full retained admission."""
    if type(receipt) is not RetainedImportReceipt:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    try:
        receipt.assert_factory_issued()
    except (AttributeError, ValueError) as error:
        code = "HKEL_IMPORTED_BASELINE_INVALID"
        raise ValueError(code) from error
    if (
        receipt.source_family != "LEGISLATION"
        or receipt.source_report_fingerprint != _KNOWN_HKEL_REPORT_FINGERPRINT
        or receipt.imported_item_count != _EXPECTED_ENDPOINTS
        or receipt.reused_object_bytes != _KNOWN_HKEL_REUSED_BYTES
        or receipt.archive_members != _EXPECTED_ARCHIVE_MEMBERS
        or receipt.archive_pairs != _EXPECTED_BILINGUAL_PAIRS
        or receipt.publication_specifications != _EXPECTED_SPECIFICATIONS
        or receipt.semantic_proof_fingerprint != _KNOWN_HKEL_SEMANTIC_PROOF
        or receipt.cycle_id != _KNOWN_HKEL_IMPORT_CYCLE
        or receipt.source_attempt_id != _KNOWN_HKEL_ATTEMPT
        or len(receipt.imported_work_item_ids) != _EXPECTED_ENDPOINTS
        or tuple(sorted(set(receipt.imported_work_item_ids))) != receipt.imported_work_item_ids
        or _FINGERPRINT.fullmatch(receipt.work_item_lineage_fingerprint) is None
        or type(report) is not AcquisitionCycleReport
        or report.cycle_id != receipt.cycle_id
        or report.result is not AcquisitionCycleResult.COMPLETE
        or report.journal_head_fingerprint != receipt.journal_head_fingerprint
        or len(report.item_dispositions) != _EXPECTED_ENDPOINTS
        or tuple(sorted(item.work_item_id for item in report.item_dispositions))
        != receipt.imported_work_item_ids
        or any(
            item.transition is not JournalTransition.IMPORTED_CAPTURE_VERIFIED
            for item in report.item_dispositions
        )
    ):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    _validate_cycle_report(report)
    checkpoint_body = {
        "cycle_id": report.cycle_id,
        "items": [item.to_json() for item in report.item_dispositions],
    }
    expected_checkpoint_fingerprint = (
        f"sha256:{sha256(canonicalize(checked_json_value(checkpoint_body))).hexdigest()}"
    )
    if receipt.imported_checkpoint_fingerprint != expected_checkpoint_fingerprint:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    admission = _parse_hkel_admission(admission_document, receipt.source_report_fingerprint)
    if (
        admission.source_observation_fingerprint != _KNOWN_HKEL_SOURCE_OBSERVATION
        or admission.structure_profile_fingerprint != _KNOWN_HKEL_STRUCTURE_PROFILE
    ):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    return _issue_baseline(
        HkelImportedBaseline(
            receipt.source_report_fingerprint,
            tuple(sorted(item.work_item_id for item in report.item_dispositions)),
            _EXPECTED_ARCHIVE_MEMBERS,
            _EXPECTED_BILINGUAL_PAIRS,
            _EXPECTED_SPECIFICATIONS,
            admission.archive_reuse_keys,
            tuple(
                HkelArchiveObjectReference(
                    endpoint_id=item.endpoint_id,
                    work_item_id=item.work_item_id,
                    media_type=item.media_type,
                    final_url=item.final_url,
                    body_length=item.body_length,
                    content_fingerprint=item.content_fingerprint,
                    object_ref=item.object_ref,
                    provenance_kind=HkelArchiveProvenanceKind.TASK4_RETAINED_IMPORT,
                    source_cycle_id=receipt.cycle_id,
                    source_attempt_id=receipt.source_attempt_id,
                    source_report_fingerprint=receipt.source_report_fingerprint,
                    authority_manifest_fingerprint=item.authority_manifest_fingerprint,
                    execution_authorization_fingerprint=(item.execution_authorization_fingerprint),
                    source_journal_head_fingerprint=receipt.journal_head_fingerprint,
                )
                for item in receipt.imported_object_references
                if item.endpoint_id in _ENDPOINTS_BY_KIND[LegislationWorkKind.HKEL_CURRENT_ARCHIVE]
            ),
            admission.review_issue_refs,
            admission.source_observation_fingerprint,
            admission.structure_profile_fingerprint,
            receipt.cycle_id,
            receipt.source_attempt_id,
            receipt.issuance_fingerprint,
            receipt.work_item_lineage_fingerprint,
            "",
        )
    )


def _parse_hkel_reuse_keys(value: JsonValue) -> tuple[HkelArchiveReuseKey, ...]:
    if type(value) is not list:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    keys: list[HkelArchiveReuseKey] = []
    for raw in value:
        if type(raw) is not dict or frozenset(raw) != _REUSE_FIELDS:
            _fail("HKEL_IMPORTED_BASELINE_INVALID")
        key = HkelArchiveReuseKey.issue(
            raw["archive_endpoint_id"],
            raw["archive_fingerprint"],
            raw["publication_profile_fingerprint"],
        )
        if raw["fingerprint"] != key.fingerprint:
            _fail("HKEL_IMPORTED_BASELINE_INVALID")
        keys.append(key)
    result = tuple(keys)
    if len(result) != _EXPECTED_ARCHIVES or tuple(
        item.archive_endpoint_id for item in result
    ) != tuple(sorted(item.archive_endpoint_id for item in result)):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    expected = tuple(
        (
            f"sep_{index:048x}",
            archive_fingerprint,
            _KNOWN_HKEL_PUBLICATION_PROFILE,
        )
        for index, archive_fingerprint in enumerate(_KNOWN_HKEL_ARCHIVE_FINGERPRINTS, start=10)
    )
    if (
        tuple(
            (
                item.archive_endpoint_id,
                item.archive_fingerprint,
                item.publication_profile_fingerprint,
            )
            for item in result
        )
        != expected
    ):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    return result


def _parse_hkel_review_refs(value: JsonValue) -> tuple[str, ...]:
    if type(value) is not list:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    reviews: list[str] = []
    for review in value:
        if type(review) is not str or _REFERENCE.fullmatch(review) is None:
            _fail("HKEL_IMPORTED_BASELINE_INVALID")
        reviews.append(review)
    result = tuple(reviews)
    if result != tuple(sorted(set(result))) or result != _KNOWN_HKEL_REVIEW_ISSUES:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    return result


def _parse_hkel_admission(
    admission_document: object,
    expected_report_fingerprint: str,
) -> _HkelAdmissionProjection:
    if type(admission_document) is not bytes:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    try:
        document = parse_json_bytes(admission_document, max_bytes=1_048_576)
    except ValueError:
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    if (
        type(document) is not dict
        or frozenset(document) != _ADMISSION_FIELDS
        or canonicalize(document) != admission_document
        or document["schema_id"] != _ADMISSION_SCHEMA_ID
        or document["schema_version"] != "1.0.0"
        or document["archive_member_count"] != _EXPECTED_ARCHIVE_MEMBERS
        or document["bilingual_pair_count"] != _EXPECTED_BILINGUAL_PAIRS
        or document["publication_specification_count"] != _EXPECTED_SPECIFICATIONS
        or document["report_fingerprint"] != expected_report_fingerprint
        or document["attempt_id"] != _KNOWN_HKEL_ATTEMPT
        or document["observation_cutoff"] != _KNOWN_HKEL_OBSERVATION_CUTOFF
    ):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    fingerprint = document["fingerprint"]
    body = {key: value for key, value in document.items() if key != "fingerprint"}
    if (
        type(fingerprint) is not str
        or fingerprint != f"sha256:{sha256(canonicalize(checked_json_value(body))).hexdigest()}"
    ):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    source_observation = document["source_observation_fingerprint"]
    structure_profile = document["structure_profile_fingerprint"]
    if (
        type(source_observation) is not str
        or _FINGERPRINT.fullmatch(source_observation) is None
        or type(structure_profile) is not str
        or _FINGERPRINT.fullmatch(structure_profile) is None
    ):
        _fail("HKEL_IMPORTED_BASELINE_INVALID")
    return _HkelAdmissionProjection(
        _parse_hkel_reuse_keys(document["archive_reuse_keys"]),
        _parse_hkel_review_refs(document["review_issue_refs"]),
        source_observation,
        structure_profile,
    )
