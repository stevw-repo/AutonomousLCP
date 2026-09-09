"""Bounded authentic source capture for the Task 7 admission checkpoint.

This module captures registered bytes and proves immutable local read-back.  It
deliberately does not call a partially implemented parser a complete inventory.
"""

from __future__ import annotations

import base64
import binascii
import errno
import fcntl
import hashlib
import http.cookiejar
import json
import math
import os
import re
import secrets
import ssl
import stat
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from datetime import datetime
from http.client import HTTPMessage
from itertools import pairwise
from pathlib import Path
from typing import IO, Never, Protocol, cast
from urllib.parse import urldefrag, urlencode, urlsplit

from asklegal_contracts import parse_json_bytes
from asklegal_source_connectors import (
    CAPABILITY_CLAIM,
    OfficialEndpointContract,
    load_hk_cases_source_register,
    load_hk_legislation_source_register,
    load_hk_regulatory_source_register,
)
from asklegal_source_connectors.basic_law_authentic import (
    BASIC_LAW_ROOT_URL,
    CONSTITUTION_ROOT_URL,
    CURRENT_BASIC_LAW_MEMBER_URLS,
    parse_basic_law_membership,
    parse_historical_basic_law_root_membership,
    require_basic_law_member_url,
    require_historical_basic_law_category_url,
    validate_basic_law_content_page,
)
from asklegal_source_connectors.hk_judiciary_authentic import (
    JudiciaryYearPartition,
    JudiciaryYearResultPage,
    build_judiciary_next_result_url,
    build_judiciary_year_result_url,
    parse_judiciary_year_result_page,
    reconcile_judiciary_year_partition,
    require_judiciary_detail_url,
    require_judiciary_result_detail_frame_url,
    require_judiciary_result_frame_url,
    require_judiciary_year_result_url,
)
from asklegal_source_connectors.hkel_authentic import (
    parse_hkel_client_configuration_form,
    parse_hkel_current_inventory_xml,
    parse_hkel_dataset_catalogue,
    reconcile_hkel_current_inventories,
    validate_hkel_policy_pages,
)
from asklegal_source_connectors.hkex_authentic import (
    parse_hkex_catalogue,
    parse_hkex_role_membership,
    reconcile_hkex_role_capture,
    require_hkex_amendment_pdf_membership,
    require_hkex_member_url,
    require_hkex_pdf,
)
from asklegal_source_connectors.hkex_dom import (
    HKEXAttachmentOccurrence,
    HKEXAuthorityClass,
    HKEXFetchDisposition,
    HKEXLocatorKind,
    HKEXMembershipAssociation,
    HKEXMembershipRelation,
    HKEXPublisherBoard,
    HKEXRoleMembershipPlan,
    require_hkex_raw_locator,
)
from asklegal_source_connectors.hkex_fees import parse_hkex_fees_membership
from asklegal_source_connectors.hkex_forms import (
    parse_hkex_form_member,
    parse_hkex_forms_membership,
)
from asklegal_source_connectors.hkex_updates import parse_hkex_updates_membership

from tools.hk_v1_hkex_history import historical_hkex_attempt_ids, historical_hkex_replay_pin
from tools.hk_v1_hkex_policy import (
    execution_policy as hkex_execution_policy,
)
from tools.hk_v1_hkex_policy import (
    execution_policy_fingerprint as hkex_execution_policy_fingerprint,
)
from tools.hk_v1_judiciary_policy import (
    execution_policy,
    execution_policy_fingerprint,
    maintenance_outage,
    maintenance_outage_facts,
    publisher_server_error_facts,
    recognized_execution_policy,
    retry_eligible,
)
from tools.hk_v1_source_admission import (
    ExecutionAuthorization,
    authorize_execution,
    authorize_retained_replay,
)

_AUTHORITY = "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING"
_ATTEMPT_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,79}\Z")
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OBJECT_KEY = re.compile(r"objects/[0-9a-f]{64}\.bin\Z")
_MAX_AUTHORITY_BYTES = 64_000
_MAX_HKEL_COMPARISON_BYTES = 64_000
_HTTP_SUCCESS_MIN = 200
_HTTP_SUCCESS_MAX = 300
_HTTP_STATUS_MAX = 599
_JUDICIARY_FIRST_YEAR = 1997
_JUDICIARY_REQUEST_START_LIMIT = 50_000
_JUDICIARY_RETAINED_BYTE_LIMIT = 68_719_476_736
_JUDICIARY_ELAPSED_SECONDS_LIMIT = 259_200.0
_JUDICIARY_MINIMUM_START_INTERVAL_SECONDS = 2.0
_JUDICIARY_MAX_TRANSPORT_ATTEMPTS = 2
_JUDICIARY_DYNAMIC_MAX_BYTES = 16_777_216
_OBSERVATION_CUTOFF_MALFORMED = "OBSERVATION_CUTOFF_MALFORMED"
_PREDECESSOR_REPORT_MALFORMED = "PREDECESSOR_REPORT_MALFORMED"
_PREDECESSOR_EVIDENCE_READBACK_INVALID = "PREDECESSOR_EVIDENCE_READBACK_INVALID"
_SOURCE_EVIDENCE_INTEGRITY_FAILURE = "SOURCE_EVIDENCE_INTEGRITY_FAILURE"
_SOURCE_ATTEMPT_IN_PROGRESS = "SOURCE_ATTEMPT_IN_PROGRESS"
_SOURCE_ATTEMPT_LOCK_UNSAFE = "SOURCE_ATTEMPT_LOCK_UNSAFE"
_ATTEMPT_LOCK_ROOT_ENV = "ASKLEGAL_SOURCE_ATTEMPT_LOCK_ROOT"
_TRUSTED_RUNTIME_BASE = Path("/tmp")  # noqa: S108 - pinned/walked Linux runtime base.
_PRIVATE_RUNTIME_MODE = 0o700
_PRIVATE_LOCK_MODE = 0o600
_HK_CUTOFF = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
_HKEL_CONFIGURATION_ACTION = "https://www.elegislation.gov.hk/checkconfig/submitClientConfig.do"
_HKEL_CONFIGURATION_GET = (
    "https://www.elegislation.gov.hk/checkconfig/checkClientConfig.jsp?applicationId=RA001"
)
_HKEL_TERMS_URL = "https://www.elegislation.gov.hk/terms"
_HKEL_CLIENT_CHECK_ENDPOINT_ID = "sep_000000000000000000000000000000000000000000000056"
_HKEL_CAPABILITY_CLAIM_SNAPSHOT = tuple(CAPABILITY_CLAIM.items())
_HKEL_CLIENT_CHECK_URL = "https://www.elegislation.gov.hk/client-check?" + urlencode(
    _HKEL_CAPABILITY_CLAIM_SNAPSHOT
)
_HKEL_CLIENT_CHECK_COORDINATE = "https://www.elegislation.gov.hk/client-check"
_HKEL_CLIENT_CHECK_CONTRACT_FINGERPRINT = (
    "sha256:" + hashlib.sha256(_HKEL_CLIENT_CHECK_URL.encode()).hexdigest()
)
_RedirectTransition = tuple[str, str, str, str]
_JUDICIARY_CURRENT_LISTING_ENTRY_ID = "sep_000000000000000000000000000000000000000000000202"
_JUDICIARY_CURRENT_LISTING_TARGET_ID = "sep_000000000000000000000000000000000000000000000205"
_JUDICIARY_CURRENT_LISTING_ENTRY_URL = (
    "https://legalref.judiciary.hk/lrs/common/index.jsp?target=newjudgments&lan=en"
)
_JUDICIARY_CURRENT_LISTING_TARGET_URL = (
    "https://legalref.judiciary.hk/lrs/common/ju/newjudgments.jsp"
)
_HKEL_ARCHIVE_ENDPOINT_IDS = frozenset(f"sep_{value:048x}" for value in range(0xA, 0x16))
_PROCEDURE_ONLY_ENDPOINT_IDS = frozenset(
    {
        "sep_000000000000000000000000000000000000000000000052",
        "sep_000000000000000000000000000000000000000000000053",
        _HKEL_CLIENT_CHECK_ENDPOINT_ID,
        _JUDICIARY_CURRENT_LISTING_TARGET_ID,
        *(f"sep_{value:048x}" for value in range(0x57, 0x69)),
    }
)
_BASIC_LAW_CONSTITUTION_ROOT_ID = "sep_000000000000000000000000000000000000000000000054"
_BASIC_LAW_TEXT_ROOT_ID = "sep_000000000000000000000000000000000000000000000055"
_BASIC_LAW_REUSED_ENDPOINTS = {
    "https://www.basiclaw.gov.hk/en/basiclaw/annex3.html": (
        "sep_000000000000000000000000000000000000000000000043"
    ),
    "https://www.basiclaw.gov.hk/en/basiclaw/annex-instrument.html": (
        "sep_000000000000000000000000000000000000000000000044"
    ),
}
_LEGACY_REPORT_KEYS = frozenset(
    {
        "attempt_id",
        "authority_manifest_fingerprint",
        "authority_provenance",
        "change_state",
        "endpoint_counts",
        "endpoints",
        "observation_cutoff",
        "predecessor_attempt_id",
        "readback_verified",
        "result",
        "source_family",
        "source_procedures",
    }
)
_REPORT_KEYS = _LEGACY_REPORT_KEYS | {"execution_authorization_fingerprint"}
_JUDICIARY_OBSERVATION_REPORT_KEYS = _REPORT_KEYS | {"observation_stop"}
_JUDICIARY_RETRY_REPORT_KEYS = _REPORT_KEYS | {
    "execution_policy",
    "execution_policy_fingerprint",
    "observation_accounting",
    "report_schema_version",
    "transport_attempts",
}
_JUDICIARY_CONTINUATION_REPORT_KEYS = _JUDICIARY_RETRY_REPORT_KEYS | {
    "continuation_binding",
    "cumulative_observation_accounting",
}
_HKEX_ROLE_AWARE_REPORT_KEYS = _REPORT_KEYS | {
    "execution_policy",
    "execution_policy_fingerprint",
    "hkex_attachment_occurrences",
    "hkex_dynamic_html_attempts",
    "hkex_membership_associations",
    "hkex_membership_fingerprint",
    "hkex_plan_state",
    "hkex_page_identities",
    "hkex_physical_starts",
    "hkex_request_plan",
    "hkex_root_bindings",
    "hkex_traversal_accounting",
    "report_schema_version",
}
_TRANSPORT_ATTEMPT_KEYS = frozenset(
    {
        "attempt_number",
        "body_fingerprint",
        "byte_length",
        "endpoint_id",
        "endpoint_version",
        "final_url",
        "max_bytes",
        "media_type",
        "method",
        "object_key",
        "redirect_rejected",
        "requested_url",
        "sequence",
        "start_elapsed_seconds",
        "status",
        "terminal_code",
    }
)
_ENDPOINT_KEYS = frozenset(
    {
        "body_fingerprint",
        "byte_length",
        "endpoint_id",
        "endpoint_version",
        "media_type",
        "method",
        "object_key",
        "requested_url",
        "status",
        "terminal_code",
    }
)
_ENDPOINT_TERMINALS = frozenset(
    {
        "CAPTURED",
        "CHALLENGE_AUTHORITY_REQUIRED",
        "EMPTY_RESPONSE",
        "NOT_ATTEMPTED",
        "OUTAGE",
        "SESSION_PROCEDURE_NOT_IMPLEMENTED",
        "SOURCE_CONTRACT_CHANGED",
        "TRUNCATED",
    }
)
_REPORT_RESULTS = frozenset(
    {
        "CHALLENGE_AUTHORITY_REQUIRED",
        "COMPLETE",
        "EVIDENCE_CAPTURED_INCOMPLETE",
        "SESSION_PROCEDURE_NOT_IMPLEMENTED",
        "SOURCE_CONTRACT_CHANGED",
        "SOURCE_OUTAGE",
        "TRUNCATED_RESPONSE",
        "OBSERVATION_BUDGET_EXHAUSTED",
        "OBSERVATION_EXECUTION_FAILURE",
    }
)
_PROCEDURE_TERMINALS = frozenset(
    {
        "CHALLENGE_AUTHORITY_REQUIRED",
        "COMPLETE",
        "INCOMPLETE",
        "EXTERNAL_REFERENCE_AUTHORITY_REQUIRED",
        "MEMBERSHIP_PARSER_PENDING",
        "SOURCE_CONTRACT_CHANGED",
        "YEAR_PARTITION_TRAVERSAL_PENDING",
        "BUDGET_EXHAUSTED",
        "OBSERVATION_EXECUTION_FAILURE",
    }
)
_PROCEDURE_SOURCE_IDS = {
    "GLD": frozenset({"HK-LEG-GLD-EGAZETTE"}),
    "HKEL": frozenset(
        {
            "HK-LEG-BASIC-LAW-PORTAL",
            "HK-LEG-HKEL-CURRENT-DATA",
            "HK-LEG-HKEL-CURRENT-INVENTORY",
            "HK-LEG-HKEL-EDITORIAL-RECORDS",
            "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        }
    ),
    "JUDICIARY": frozenset({"HK-CASE-HKLII-DISCOVERY", "HK-CASE-JUDICIARY-LRS-INVENTORY"}),
    "HKEX": frozenset(
        {
            "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
            "HK-REG-HKEX-FEES-RULES",
            "HK-REG-HKEX-REGULATORY-FORMS",
            "HK-REG-HKEX-RULE-UPDATES",
            "HK-REG-HKEX-RULEBOOK-CATALOGUE",
        }
    ),
}


def _judiciary_observation_profile() -> dict[str, float | int]:
    """Return the complete current source-specific pacing and budget policy."""
    return {
        "elapsed_seconds_limit": _JUDICIARY_ELAPSED_SECONDS_LIMIT,
        "minimum_start_interval_seconds": _JUDICIARY_MINIMUM_START_INTERVAL_SECONDS,
        "request_start_limit": _JUDICIARY_REQUEST_START_LIMIT,
        "retained_response_byte_limit": _JUDICIARY_RETAINED_BYTE_LIMIT,
    }


def _fail(code: str) -> Never:
    raise ValueError(code)


class PredecessorValidationError(ValueError):
    """Closed pre-effect failure raised only by retained lineage validation."""


def _predecessor_fail(code: str) -> Never:
    raise PredecessorValidationError(code)


class SourceEvidenceIntegrityError(ValueError):
    """Closed failure for writer evidence that cannot be retained and read back exactly."""


def _evidence_integrity_fail() -> Never:
    raise SourceEvidenceIntegrityError(_SOURCE_EVIDENCE_INTEGRITY_FAILURE)


class SourceAttemptClaimError(ValueError):
    """Closed pre-effect failure for one local execution-attempt claim."""


def _attempt_claim_fail(code: str) -> Never:
    raise SourceAttemptClaimError(code)


@dataclass(frozen=True, slots=True)
class HKEXDynamicRequest:
    """One immutable current-role request planned before dynamic I/O."""

    sequence: int
    capture_endpoint_id: str
    endpoint_version: str
    relation: HKEXMembershipRelation
    requested_url: str
    media_type: str
    max_bytes: int


@dataclass(frozen=True, slots=True)
class HKEXRootBinding:
    """One exact registered role-root/structural-section pair."""

    source_id: str
    board: HKEXPublisherBoard
    root_endpoint_id: str
    section_endpoint_id: str
    canonical_url: str
    shortlink_url: str
    node_id: str
    entire_section_url: str


@dataclass(frozen=True, slots=True)
class HKEXTraversalAccounting:
    """Counts derivable from one complete immutable role-aware plan."""

    static_registered_requests: int
    unique_dynamic_html_requests: int
    unique_dynamic_pdf_requests: int
    logical_request_starts: int
    semantic_only_associations: int
    planned_or_reused_associations: int
    unfetched_external_associations: int
    declared_associations: int


@dataclass(frozen=True, slots=True)
class HKEXTraversalPlan:
    """One pure staged HKEX traversal plan with no transport facts."""

    root_bindings: tuple[HKEXRootBinding, ...]
    associations: tuple[HKEXMembershipAssociation, ...]
    attachment_occurrences: tuple[HKEXAttachmentOccurrence, ...]
    form_html_requests: tuple[HKEXDynamicRequest, ...]
    pdf_requests: tuple[HKEXDynamicRequest, ...]
    accounting: HKEXTraversalAccounting


@dataclass(frozen=True, slots=True)
class HKEXRawLocationProbe:
    """One bounded raw Location representation safe for report and replay."""

    location_present: bool
    location_octets_base64_prefix: str | None
    prefix_octet_count: int
    representation_complete: bool
    total_octet_count: int | None
    over_limit: bool


@dataclass(frozen=True, slots=True)
class HKEXRedirectEvent:
    """One raw, bounded redirect response and its exact follow decision."""

    event_sequence: int
    response_hop_number: int
    response_status: int
    source_url: str
    location_present: bool
    location_octets_base64_prefix: str | None
    prefix_octet_count: int
    representation_complete: bool
    total_octet_count: int | None
    over_limit: bool
    validated_target_url: str | None
    followed: bool
    rejection_code: str | None
    target_physical_start_sequence: int | None
    target_start_elapsed_seconds: float | None


@dataclass(frozen=True, slots=True)
class HKEXPhysicalStart:
    """One controller-permitted initial or followed network start."""

    sequence: int
    logical_request_sequence: int
    capture_endpoint_id: str
    stage: str
    hop_number: int
    requested_url: str
    start_elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class HKEXDynamicHTMLAttempt:
    """All transport facts for one Forms node, even when identity parsing fails."""

    sequence: int
    capture_endpoint_id: str
    endpoint_version: str
    relation: HKEXMembershipRelation
    requested_url: str
    initial_physical_start_sequence: int
    initial_start_elapsed_seconds: float
    redirect_events: tuple[HKEXRedirectEvent, ...]
    final_url: str | None
    status: int
    media_type: str
    redirect_rejected: bool
    physical_terminal_code: str
    semantic_terminal_code: str


@dataclass(frozen=True, slots=True)
class HKEXPageIdentity:
    """One successfully parsed canonical Forms member identity."""

    capture_endpoint_id: str
    requested_url: str
    final_url: str
    canonical_url: str
    shortlink_url: str
    node_id: str
    entire_section_url: str


@dataclass(frozen=True, slots=True)
class HKEXCapturedEndpoint:
    """One logical static or dynamic response retained by the role-aware executor."""

    sequence: int
    capture_endpoint_id: str
    endpoint_version: str
    stage: str
    requested_url: str
    max_bytes: int
    response: CapturedResponse
    terminal_code: str


@dataclass(frozen=True, slots=True)
class HKEXRoleAwareCapture:
    """One bounded phased capture result ready for schema-2 projection."""

    plan_state: str
    plan: HKEXTraversalPlan | None
    captures: tuple[HKEXCapturedEndpoint, ...]
    dynamic_html_attempts: tuple[HKEXDynamicHTMLAttempt, ...]
    physical_starts: tuple[HKEXPhysicalStart, ...]
    page_identities: tuple[HKEXPageIdentity, ...]
    followed_redirect_starts: int
    redirect_event_count: int
    retained_response_bytes: int
    pacing_sleep_count: int
    pacing_sleep_seconds: float
    elapsed_seconds: float
    stop_code: str | None


_HKEX_PHYSICAL_START_LIMIT = 3_680
_HKEX_ELAPSED_SECONDS_LIMIT = 3_600.0
_HKEX_MINIMUM_START_INTERVAL_SECONDS = 0.25
_HKEX_RETAINED_RESPONSE_BYTES_LIMIT = 68_719_476_736
_HKEX_HTML_RESPONSE_BYTES_LIMIT = 16_777_216
_HKEX_PDF_RESPONSE_BYTES_LIMIT = 67_108_864
_HKEX_REDIRECT_EVENT_LIMIT = 1_024
_HKEX_FOLLOWED_REDIRECT_START_LIMIT = 512


@dataclass(slots=True)
class HKEXObservationController:
    """One source-local permit boundary for every HKEX physical start and body."""

    clock: Callable[[], float]
    sleeper: Callable[[float], None]
    physical_starts: int = 0
    followed_redirect_starts: int = 0
    redirect_events: int = 0
    retained_response_bytes: int = 0
    pacing_sleep_count: int = 0
    pacing_sleep_seconds: float = 0.0
    started_at: float | None = None
    last_start: float | None = None
    elapsed_seconds: float = 0.0
    stop_code: str | None = None

    def _now(self) -> float:
        value = self.clock()
        if type(value) not in {int, float} or not math.isfinite(value):
            _fail("HKEX_OBSERVATION_CONTROLLER_INVALID")
        return float(value)

    def before_physical_start(self, *, followed_redirect: bool = False) -> bool:
        """Grant one permit only after exact physical, elapsed, and pacing checks."""
        if self.physical_starts >= _HKEX_PHYSICAL_START_LIMIT or (
            followed_redirect
            and self.followed_redirect_starts >= _HKEX_FOLLOWED_REDIRECT_START_LIMIT
        ):
            self.stop_code = "BUDGET_EXHAUSTED"
            return False
        now = self._now()
        if self.started_at is None:
            self.started_at = now
        if now < self.started_at:
            _fail("HKEX_OBSERVATION_CONTROLLER_INVALID")
        self.elapsed_seconds = now - self.started_at
        if self.elapsed_seconds >= _HKEX_ELAPSED_SECONDS_LIMIT:
            self.stop_code = "OBSERVATION_BUDGET_EXHAUSTED"
            return False
        if self.last_start is not None:
            remaining = _HKEX_MINIMUM_START_INTERVAL_SECONDS - (now - self.last_start)
            if remaining > 0:
                self.sleeper(remaining)
                self.pacing_sleep_count += 1
                self.pacing_sleep_seconds += remaining
                now = self._now()
                if now < self.last_start + _HKEX_MINIMUM_START_INTERVAL_SECONDS:
                    _fail("HKEX_OBSERVATION_CONTROLLER_INVALID")
                self.elapsed_seconds = now - self.started_at
                if self.elapsed_seconds >= _HKEX_ELAPSED_SECONDS_LIMIT:
                    self.stop_code = "OBSERVATION_BUDGET_EXHAUSTED"
                    return False
        self.physical_starts += 1
        if followed_redirect:
            self.followed_redirect_starts += 1
        self.last_start = now
        return True

    def reserve_redirect_event(self) -> bool:
        """Reserve one globally bounded redirect event before retaining it."""
        if self.redirect_events >= _HKEX_REDIRECT_EVENT_LIMIT:
            self.stop_code = "BUDGET_EXHAUSTED"
            return False
        self.redirect_events += 1
        return True

    def reserve_response(self, *, byte_length: int, media_type: str) -> bool:
        """Reserve a bounded retained response before any writer action."""
        maximum = {
            "application/pdf": _HKEX_PDF_RESPONSE_BYTES_LIMIT,
            "text/html": _HKEX_HTML_RESPONSE_BYTES_LIMIT,
        }.get(media_type)
        if (
            type(byte_length) is not int
            or maximum is None
            or byte_length < 0
            or byte_length > maximum
            or self.retained_response_bytes + byte_length > _HKEX_RETAINED_RESPONSE_BYTES_LIMIT
        ):
            self.stop_code = "TRUNCATED"
            return False
        self.retained_response_bytes += byte_length
        return True


_HKEX_ID_PREFIX = "sep_000000000000000000000000000000000000000000000"
_HKEX_ROLE_AWARE_PLAN_INVALID = "HKEX_ROLE_AWARE_PLAN_INVALID"
_HKEX_ROLE_AWARE_TRANSPORT_INVALID = "HKEX_ROLE_AWARE_TRANSPORT_INVALID"
_HKEX_FORM_MEMBER_CAPTURE_INVALID = "HKEX_FORM_MEMBER_CAPTURE_INVALID"
_HKEX_ROLE_AWARE_REPORT_INVALID = "HKEX_ROLE_AWARE_REPORT_INVALID"
_HKEX_PLAN_STATES = frozenset(
    {
        "STATIC_CAPTURE_INCOMPLETE",
        "ROOT_CONTRACT_CHANGED",
        "ROOT_POLICY_LIMIT_EXCEEDED",
        "FORM_HTML_TIER_INCOMPLETE",
        "FORM_MEMBER_CONTRACT_CHANGED",
        "COMPLETE_PLAN",
    }
)
_HKEX_STATIC_ENDPOINT_COUNT = 20
_HKEX_LOCATION_ADMISSION_OCTETS = 8_192
_HKEX_LOCATION_PREFIX_OCTETS = 8_193
_HKEX_LOCATION_CONSUMPTION_OCTETS = 8_194
_HKEX_LOCATION_BASE64_CHARS = 10_924
_HKEX_REDIRECT_EVENTS_PER_ATTEMPT = 2
_HKEX_RAW_READER_RESULT_FIELDS = 2
_HKEX_ROLE_BINDINGS = (
    ("HK-REG-HKEX-FEES-RULES", HKEXPublisherBoard.MAIN, 303, 314),
    ("HK-REG-HKEX-FEES-RULES", HKEXPublisherBoard.GEM, 304, 320),
    ("HK-REG-HKEX-REGULATORY-FORMS", HKEXPublisherBoard.MAIN, 305, 313),
    ("HK-REG-HKEX-REGULATORY-FORMS", HKEXPublisherBoard.GEM, 306, 319),
    ("HK-REG-HKEX-RULE-UPDATES", HKEXPublisherBoard.MAIN, 307, 315),
    ("HK-REG-HKEX-RULE-UPDATES", HKEXPublisherBoard.GEM, 308, 316),
)


def _hkex_endpoint_id(suffix: int) -> str:
    return f"{_HKEX_ID_PREFIX}{suffix}"


def _hkex_plan_require(*, condition: bool) -> None:
    if not condition:
        raise ValueError


class _HKEXPlanPolicyLimitError(ValueError):
    """A structurally valid root plan exceeds one policy-bound cardinality."""


class _HKEXRoleAwareEvidenceReadbackError(ValueError):
    """A schema-valid retained object is absent or differs from its immutable record."""


def _hkex_require_plan_policy_limits(
    *,
    static_count: int,
    associations: tuple[HKEXMembershipAssociation, ...],
    form_requests: tuple[HKEXDynamicRequest, ...],
    pdf_requests: tuple[HKEXDynamicRequest, ...],
) -> None:
    policy = hkex_execution_policy()

    def limit(name: str) -> int:
        value = policy[name]
        if type(value) is not int:
            _fail("HKEX_EXECUTION_POLICY_INVALID")
        return value

    def unique_targets(relation: HKEXMembershipRelation, board: HKEXPublisherBoard) -> int:
        return len(
            {
                item.target_url
                for item in associations
                if item.relation is relation and item.board is board
            }
        )

    exceeded = (
        static_count > limit("static_registered_requests")
        or len(form_requests) > limit("unique_dynamic_html_requests")
        or len(pdf_requests) > limit("unique_dynamic_pdf_requests")
        or static_count + len(form_requests) + len(pdf_requests) > limit("logical_request_starts")
    )
    for board in HKEXPublisherBoard:
        exceeded = exceeded or (
            unique_targets(HKEXMembershipRelation.FORM_NODE, board) > limit("form_nodes_per_board")
            or unique_targets(HKEXMembershipRelation.FEES_PDF, board) > limit("fees_pdfs_per_board")
            or unique_targets(HKEXMembershipRelation.FORM_PDF, board) > limit("form_pdfs_per_board")
            or unique_targets(HKEXMembershipRelation.UPDATE_CONTAINER, board)
            > limit("update_containers_per_board")
            or unique_targets(HKEXMembershipRelation.UPDATE_PAGE, board)
            > limit("update_pages_per_board")
            or unique_targets(HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF, board)
            > limit("update_pdfs_per_board")
        )
    if exceeded:
        raise _HKEXPlanPolicyLimitError


def probe_hkex_raw_location(
    reader: Callable[[int], tuple[bytes, bool]] | None,
) -> HKEXRawLocationProbe:
    """Read only the policy-bounded prefix and one immediately discarded lookahead."""
    if reader is None:
        return HKEXRawLocationProbe(
            location_present=False,
            location_octets_base64_prefix=None,
            prefix_octet_count=0,
            representation_complete=True,
            total_octet_count=None,
            over_limit=False,
        )
    result = reader(_HKEX_LOCATION_CONSUMPTION_OCTETS)
    if type(result) is not tuple or len(result) != _HKEX_RAW_READER_RESULT_FIELDS:
        _fail("HKEX_RAW_LOCATION_REPRESENTATION_INVALID")
    raw, field_complete = result
    if type(raw) is not bytes or type(field_complete) is not bool:
        _fail("HKEX_RAW_LOCATION_REPRESENTATION_INVALID")
    if len(raw) > _HKEX_LOCATION_CONSUMPTION_OCTETS:
        _fail("HKEX_RAW_LOCATION_REPRESENTATION_INVALID")
    if len(raw) < _HKEX_LOCATION_CONSUMPTION_OCTETS and not field_complete:
        _fail("HKEX_RAW_LOCATION_REPRESENTATION_INVALID")
    lookahead_observed = len(raw) == _HKEX_LOCATION_CONSUMPTION_OCTETS
    prefix = raw[:_HKEX_LOCATION_PREFIX_OCTETS]
    complete = field_complete and not lookahead_observed
    total = len(prefix) if complete else None
    return HKEXRawLocationProbe(
        location_present=True,
        location_octets_base64_prefix=base64.b64encode(prefix).decode("ascii"),
        prefix_octet_count=len(prefix),
        representation_complete=complete,
        total_octet_count=total,
        over_limit=len(prefix) > _HKEX_LOCATION_ADMISSION_OCTETS or lookahead_observed,
    )


def _hkex_accounting(
    *,
    static_count: int,
    associations: tuple[HKEXMembershipAssociation, ...],
    form_requests: tuple[HKEXDynamicRequest, ...],
    pdf_requests: tuple[HKEXDynamicRequest, ...],
) -> HKEXTraversalAccounting:
    subtotals = {
        disposition: sum(item.fetch_disposition is disposition for item in associations)
        for disposition in HKEXFetchDisposition
    }
    return HKEXTraversalAccounting(
        static_registered_requests=static_count,
        unique_dynamic_html_requests=len(form_requests),
        unique_dynamic_pdf_requests=len(pdf_requests),
        logical_request_starts=static_count + len(form_requests) + len(pdf_requests),
        semantic_only_associations=subtotals[HKEXFetchDisposition.SEMANTIC_ONLY],
        planned_or_reused_associations=subtotals[HKEXFetchDisposition.PLANNED_OR_REUSED],
        unfetched_external_associations=subtotals[
            HKEXFetchDisposition.UNFETCHED_EXTERNAL_REFERENCE
        ],
        declared_associations=len(associations),
    )


def _hkex_dynamic_requests(
    associations: tuple[HKEXMembershipAssociation, ...],
    *,
    relation: HKEXMembershipRelation,
    static_urls: frozenset[str],
    start_sequence: int,
) -> tuple[HKEXDynamicRequest, ...]:
    media_type = "text/html" if relation is HKEXMembershipRelation.FORM_NODE else "application/pdf"
    max_bytes = 16_777_216 if media_type == "text/html" else 67_108_864
    unique: dict[str, HKEXMembershipAssociation] = {}
    for association in associations:
        if (
            association.relation is relation
            and association.authority_class is HKEXAuthorityClass.SAME_HOST_ADMITTED
            and association.fetch_disposition is HKEXFetchDisposition.PLANNED_OR_REUSED
            and association.target_url not in static_urls
        ):
            unique.setdefault(association.target_url, association)
    return tuple(
        HKEXDynamicRequest(
            sequence=start_sequence + offset,
            capture_endpoint_id=association.capture_endpoint_id or "",
            endpoint_version="2.0.0",
            relation=relation,
            requested_url=url,
            media_type=media_type,
            max_bytes=max_bytes,
        )
        for offset, (url, association) in enumerate(unique.items())
    )


def _hkex_role_plan(  # noqa: PLR0913 - one closed parser-dispatch interface
    *,
    source_id: str,
    board: HKEXPublisherBoard,
    root: OfficialEndpointContract,
    section: OfficialEndpointContract,
    bodies: Mapping[str, bytes],
    capture_id_by_url: Mapping[str, str],
) -> HKEXRoleMembershipPlan:
    if source_id == "HK-REG-HKEX-FEES-RULES":
        return parse_hkex_fees_membership(
            bodies[root.endpoint_id],
            bodies[section.endpoint_id],
            root_url=root.url,
            complete_section_url=section.url,
            board=board,
            capture_id_by_url=capture_id_by_url,
        )
    if source_id == "HK-REG-HKEX-REGULATORY-FORMS":
        return parse_hkex_forms_membership(
            bodies[root.endpoint_id],
            bodies[section.endpoint_id],
            root_url=root.url,
            complete_section_url=section.url,
            board=board,
            capture_id_by_url=capture_id_by_url,
        )
    if source_id == "HK-REG-HKEX-RULE-UPDATES":
        return parse_hkex_updates_membership(
            bodies[root.endpoint_id],
            bodies[section.endpoint_id],
            root_url=root.url,
            complete_section_url=section.url,
            board=board,
            capture_id_by_url=capture_id_by_url,
        )
    _fail("HKEX_ROLE_AWARE_PLAN_INVALID")


def build_hkex_traversal_plan(
    bodies: Mapping[str, bytes], endpoints: tuple[OfficialEndpointContract, ...]
) -> HKEXTraversalPlan:
    """Build the complete static-derived plan before one dynamic request starts."""
    try:
        endpoint_by_id = {endpoint.endpoint_id: endpoint for endpoint in endpoints}
        _hkex_plan_require(
            condition=len(endpoints) == _HKEX_STATIC_ENDPOINT_COUNT
            and len(endpoint_by_id) == _HKEX_STATIC_ENDPOINT_COUNT
        )
        capture_id_by_url = {endpoint.url: endpoint.endpoint_id for endpoint in endpoints}
        _hkex_plan_require(condition=len(capture_id_by_url) == len(endpoints))
        bindings: list[HKEXRootBinding] = []
        role_plans: list[HKEXRoleMembershipPlan] = []
        for source_id, board, root_suffix, section_suffix in _HKEX_ROLE_BINDINGS:
            root = endpoint_by_id[_hkex_endpoint_id(root_suffix)]
            section = endpoint_by_id[_hkex_endpoint_id(section_suffix)]
            _hkex_plan_require(
                condition=root.source_id == source_id and section.source_id == source_id
            )
            role_plan = _hkex_role_plan(
                source_id=source_id,
                board=board,
                root=root,
                section=section,
                bodies=bodies,
                capture_id_by_url=capture_id_by_url,
            )
            bindings.append(
                HKEXRootBinding(
                    source_id=source_id,
                    board=board,
                    root_endpoint_id=root.endpoint_id,
                    section_endpoint_id=section.endpoint_id,
                    canonical_url=role_plan.identity.canonical_url,
                    shortlink_url=role_plan.identity.shortlink_url,
                    node_id=role_plan.identity.node_id,
                    entire_section_url=role_plan.identity.entire_section_url,
                )
            )
            role_plans.append(role_plan)
        associations = tuple(
            association for plan in role_plans for association in plan.associations
        )
        occurrences = tuple(
            occurrence for plan in role_plans for occurrence in plan.attachment_occurrences
        )
        static_urls = frozenset(capture_id_by_url)
        form_requests = _hkex_dynamic_requests(
            associations,
            relation=HKEXMembershipRelation.FORM_NODE,
            static_urls=static_urls,
            start_sequence=len(endpoints) + 1,
        )
        unsequenced_pdf_requests = _hkex_dynamic_requests(
            associations,
            relation=HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF,
            static_urls=static_urls,
            start_sequence=len(endpoints) + len(form_requests) + 1,
        ) + _hkex_dynamic_requests(
            associations,
            relation=HKEXMembershipRelation.FEES_PDF,
            static_urls=static_urls,
            start_sequence=len(endpoints) + len(form_requests) + 1,
        )
        pdf_requests = tuple(
            replace(request, sequence=len(endpoints) + len(form_requests) + offset + 1)
            for offset, request in enumerate(unsequenced_pdf_requests)
        )
        _hkex_plan_require(
            condition=len({request.requested_url for request in (*form_requests, *pdf_requests)})
            == len(form_requests) + len(pdf_requests)
        )
        _hkex_require_plan_policy_limits(
            static_count=len(endpoints),
            associations=associations,
            form_requests=form_requests,
            pdf_requests=pdf_requests,
        )
    except _HKEXPlanPolicyLimitError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(_HKEX_ROLE_AWARE_PLAN_INVALID) from error
    accounting = _hkex_accounting(
        static_count=len(endpoints),
        associations=associations,
        form_requests=form_requests,
        pdf_requests=pdf_requests,
    )
    return HKEXTraversalPlan(
        tuple(bindings), associations, occurrences, form_requests, pdf_requests, accounting
    )


def finalize_hkex_traversal_plan(
    plan: HKEXTraversalPlan,
    *,
    form_bodies: Mapping[str, bytes],
    form_final_urls: Mapping[str, str],
    endpoints: tuple[OfficialEndpointContract, ...],
) -> HKEXTraversalPlan:
    """Freeze every Forms PDF before adding the first PDF request to the plan."""
    try:
        _hkex_plan_require(condition=type(plan) is HKEXTraversalPlan)
        static_map = {endpoint.url: endpoint.endpoint_id for endpoint in endpoints}
        _hkex_plan_require(
            condition=set(form_bodies) == {item.requested_url for item in plan.form_html_requests}
            and set(form_final_urls) == set(form_bodies)
        )
        board_by_capture = {
            association.capture_endpoint_id: association.board
            for association in plan.associations
            if association.relation is HKEXMembershipRelation.FORM_NODE
        }
        form_associations: list[HKEXMembershipAssociation] = []
        for request in plan.form_html_requests:
            board = board_by_capture[request.capture_endpoint_id]
            capture = parse_hkex_form_member(
                form_bodies[request.requested_url],
                requested_node_url=request.requested_url,
                final_url=form_final_urls[request.requested_url],
                board=board,
                capture_id_by_url=static_map,
            )
            form_associations.extend(capture.associations)
        associations = (*plan.associations, *form_associations)
        static_urls = frozenset(static_map)
        pdf_requests = (
            _hkex_dynamic_requests(
                associations,
                relation=HKEXMembershipRelation.FEES_PDF,
                static_urls=static_urls,
                start_sequence=len(endpoints) + len(plan.form_html_requests) + 1,
            )
            + _hkex_dynamic_requests(
                associations,
                relation=HKEXMembershipRelation.FORM_PDF,
                static_urls=static_urls,
                start_sequence=len(endpoints) + len(plan.form_html_requests) + 1,
            )
            + _hkex_dynamic_requests(
                associations,
                relation=HKEXMembershipRelation.UPDATE_ATTACHMENT_PDF,
                static_urls=static_urls,
                start_sequence=len(endpoints) + len(plan.form_html_requests) + 1,
            )
        )
        unique_requests = {request.requested_url: request for request in pdf_requests}
        _hkex_plan_require(condition=len(unique_requests) == len(pdf_requests))
        _hkex_require_plan_policy_limits(
            static_count=len(endpoints),
            associations=associations,
            form_requests=plan.form_html_requests,
            pdf_requests=pdf_requests,
        )
    except _HKEXPlanPolicyLimitError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(_HKEX_ROLE_AWARE_PLAN_INVALID) from error
    final_pdf_requests = tuple(
        replace(
            request,
            sequence=len(endpoints) + len(plan.form_html_requests) + offset + 1,
        )
        for offset, request in enumerate(unique_requests.values())
    )
    return HKEXTraversalPlan(
        plan.root_bindings,
        associations,
        plan.attachment_occurrences,
        plan.form_html_requests,
        final_pdf_requests,
        _hkex_accounting(
            static_count=len(endpoints),
            associations=associations,
            form_requests=plan.form_html_requests,
            pdf_requests=final_pdf_requests,
        ),
    )


def _hkex_association_projection(item: HKEXMembershipAssociation) -> dict[str, object]:
    return {
        "association_id": item.association_id,
        "authority_class": item.authority_class.value,
        "board": item.board.value,
        "capture_endpoint_id": item.capture_endpoint_id,
        "fetch_disposition": item.fetch_disposition.value,
        "occurrence_ids": list(item.occurrence_ids),
        "parent_url": item.parent_url,
        "relation": item.relation.value,
        "source_id": item.source_id,
        "source_order": item.source_order,
        "target_url": item.target_url,
    }


def _hkex_occurrence_projection(item: HKEXAttachmentOccurrence) -> dict[str, object]:
    return {
        "authority_class": item.authority_class.value,
        "board": item.board.value,
        "fetch_disposition": item.fetch_disposition.value,
        "normalization_code": item.normalization_code.value,
        "occurrence_id": item.occurrence_id,
        "occurrence_order": item.occurrence_order,
        "parent_position": {
            "child_order": item.parent_position.child_order,
            "container_order": item.parent_position.container_order,
            "relation": item.parent_position.relation.value,
        },
        "parent_relation": item.parent_relation.value,
        "parent_url": item.parent_url,
        "raw_locator": item.raw_locator,
        "source_id": item.source_id,
        "target_url": item.target_url,
    }


def _hkex_request_projection(item: HKEXDynamicRequest) -> dict[str, object]:
    return {
        "capture_endpoint_id": item.capture_endpoint_id,
        "endpoint_version": item.endpoint_version,
        "max_bytes": item.max_bytes,
        "media_type": item.media_type,
        "relation": item.relation.value,
        "requested_url": item.requested_url,
        "sequence": item.sequence,
        "stage": (
            "FORM_HTML_TIER" if item.relation is HKEXMembershipRelation.FORM_NODE else "PDF_TIER"
        ),
    }


def hkex_traversal_plan_projection(plan: HKEXTraversalPlan) -> dict[str, object]:
    """Project one complete traversal plan into the exact schema-2 report shape."""
    if type(plan) is not HKEXTraversalPlan:
        _fail(_HKEX_ROLE_AWARE_PLAN_INVALID)
    return {
        "accounting": {
            "declared_associations": plan.accounting.declared_associations,
            "logical_request_starts": plan.accounting.logical_request_starts,
            "planned_or_reused_associations": (plan.accounting.planned_or_reused_associations),
            "semantic_only_associations": plan.accounting.semantic_only_associations,
            "static_registered_requests": plan.accounting.static_registered_requests,
            "unfetched_external_associations": (plan.accounting.unfetched_external_associations),
            "unique_dynamic_html_requests": plan.accounting.unique_dynamic_html_requests,
            "unique_dynamic_pdf_requests": plan.accounting.unique_dynamic_pdf_requests,
        },
        "attachment_occurrences": [
            _hkex_occurrence_projection(item) for item in plan.attachment_occurrences
        ],
        "membership_associations": [
            _hkex_association_projection(item) for item in plan.associations
        ],
        "root_bindings": [
            {
                "board": item.board.value,
                "canonical_url": item.canonical_url,
                "entire_section_url": item.entire_section_url,
                "node_id": item.node_id,
                "root_endpoint_id": item.root_endpoint_id,
                "section_endpoint_id": item.section_endpoint_id,
                "shortlink_url": item.shortlink_url,
                "source_id": item.source_id,
            }
            for item in plan.root_bindings
        ],
        "staged_requests": [
            _hkex_request_projection(item)
            for item in (*plan.form_html_requests, *plan.pdf_requests)
        ],
    }


def require_hkex_traversal_plan_projection(projection: object, plan: HKEXTraversalPlan) -> None:
    """Accept only the byte-canonical projection rederived from the pure plan."""
    try:
        if _canonical(projection) != _canonical(hkex_traversal_plan_projection(plan)):
            _hkex_plan_require(condition=False)
    except (TypeError, ValueError) as error:
        raise ValueError(_HKEX_ROLE_AWARE_PLAN_INVALID) from error


def _hkex_redirect_event_projection(item: HKEXRedirectEvent) -> dict[str, object]:
    return {
        "event_sequence": item.event_sequence,
        "followed": item.followed,
        "location_octets_base64_prefix": item.location_octets_base64_prefix,
        "location_present": item.location_present,
        "over_limit": item.over_limit,
        "prefix_octet_count": item.prefix_octet_count,
        "rejection_code": item.rejection_code,
        "representation_complete": item.representation_complete,
        "response_hop_number": item.response_hop_number,
        "response_status": item.response_status,
        "source_url": item.source_url,
        "target_physical_start_sequence": item.target_physical_start_sequence,
        "target_start_elapsed_seconds": item.target_start_elapsed_seconds,
        "total_octet_count": item.total_octet_count,
        "validated_target_url": item.validated_target_url,
    }


def _hkex_dynamic_attempt_projection(item: HKEXDynamicHTMLAttempt) -> dict[str, object]:
    return {
        "capture_endpoint_id": item.capture_endpoint_id,
        "endpoint_version": item.endpoint_version,
        "final_url": item.final_url,
        "initial_physical_start_sequence": item.initial_physical_start_sequence,
        "initial_start_elapsed_seconds": item.initial_start_elapsed_seconds,
        "media_type": item.media_type,
        "physical_terminal_code": item.physical_terminal_code,
        "redirect_events": [
            _hkex_redirect_event_projection(event) for event in item.redirect_events
        ],
        "redirect_rejected": item.redirect_rejected,
        "relation": item.relation.value,
        "requested_url": item.requested_url,
        "semantic_terminal_code": item.semantic_terminal_code,
        "sequence": item.sequence,
        "status": item.status,
    }


def _hkex_physical_start_projection(item: HKEXPhysicalStart) -> dict[str, object]:
    return {
        "capture_endpoint_id": item.capture_endpoint_id,
        "hop_number": item.hop_number,
        "logical_request_sequence": item.logical_request_sequence,
        "requested_url": item.requested_url,
        "sequence": item.sequence,
        "stage": item.stage,
        "start_elapsed_seconds": item.start_elapsed_seconds,
    }


def _hkex_page_identity_projection(item: HKEXPageIdentity) -> dict[str, object]:
    return {
        "canonical_url": item.canonical_url,
        "capture_endpoint_id": item.capture_endpoint_id,
        "entire_section_url": item.entire_section_url,
        "final_url": item.final_url,
        "node_id": item.node_id,
        "requested_url": item.requested_url,
        "shortlink_url": item.shortlink_url,
    }


def hkex_transport_projection(
    dynamic_html_attempts: tuple[HKEXDynamicHTMLAttempt, ...],
    physical_starts: tuple[HKEXPhysicalStart, ...],
    page_identities: tuple[HKEXPageIdentity, ...],
) -> dict[str, object]:
    """Project the exact schema-2 transport and Forms identity ledgers."""
    if (
        type(dynamic_html_attempts) is not tuple
        or type(physical_starts) is not tuple
        or type(page_identities) is not tuple
        or any(type(item) is not HKEXDynamicHTMLAttempt for item in dynamic_html_attempts)
        or any(type(item) is not HKEXPhysicalStart for item in physical_starts)
        or any(type(item) is not HKEXPageIdentity for item in page_identities)
    ):
        _fail(_HKEX_ROLE_AWARE_TRANSPORT_INVALID)
    return {
        "dynamic_html_attempts": [
            _hkex_dynamic_attempt_projection(item) for item in dynamic_html_attempts
        ],
        "page_identities": [_hkex_page_identity_projection(item) for item in page_identities],
        "physical_starts": [_hkex_physical_start_projection(item) for item in physical_starts],
    }


def require_hkex_transport_projection(
    projection: object,
    dynamic_html_attempts: tuple[HKEXDynamicHTMLAttempt, ...],
    physical_starts: tuple[HKEXPhysicalStart, ...],
    page_identities: tuple[HKEXPageIdentity, ...],
) -> None:
    """Accept only the canonical transport projection rederived from typed facts."""
    try:
        expected = hkex_transport_projection(
            dynamic_html_attempts, physical_starts, page_identities
        )
        if _canonical(projection) != _canonical(expected):
            _hkex_plan_require(condition=False)
    except (TypeError, ValueError) as error:
        raise ValueError(_HKEX_ROLE_AWARE_TRANSPORT_INVALID) from error


@dataclass(slots=True)
class _HeldSourceAttemptClaim:
    """One active, exact claim token shared only across the local CLI boundary."""

    output_root: Path
    attempt_id: str
    active: bool = True


@dataclass(frozen=True, slots=True)
class CapturedResponse:
    """One bounded HTTP result without headers that may contain session data."""

    status: int
    media_type: str
    body: bytes
    final_url: str | None
    redirect_rejected: bool = False
    raw_location_reader: Callable[[int], tuple[bytes, bool]] | None = None


@dataclass(frozen=True, slots=True)
class RedirectCapability:
    """Immutable public declaration of the redirect boundary a transport enforces."""

    allowed_urls: frozenset[str]
    allowed_transitions: frozenset[_RedirectTransition]
    same_origin_only: bool = True


@dataclass(frozen=True, slots=True)
class HkelSessionStage:
    """One sanitized session stage; response content and session values are excluded."""

    stage_id: str
    terminal_code: str
    status: int
    media_type: str
    final_url: str | None
    byte_length: int
    redirect_rejected: bool = False
    configuration_action: str | None = None
    configuration_field_count: int | None = None
    anti_forgery_control_present: bool | None = None
    attempted: bool = True


@dataclass(frozen=True, slots=True)
class HkelSessionCapture:
    """Closed sanitized facts for every configuration session stage."""

    initial: HkelSessionStage
    parser: HkelSessionStage
    submission: HkelSessionStage
    capability: HkelSessionStage | None = None


class ReadOnlySourceTransport(Protocol):
    """The only external capability available to this capture boundary."""

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        """Return at most ``max_bytes + 1`` bytes so truncation stays visible."""
        ...


_HKEX_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _hkex_redirect_target(probe: HKEXRawLocationProbe) -> tuple[str | None, str | None]:
    if not probe.location_present:
        return None, "LOCATION_MISSING"
    if probe.over_limit:
        return None, "LOCATION_OVER_LIMIT"
    encoded = probe.location_octets_base64_prefix
    if type(encoded) is not str:
        return None, "LOCATION_REPRESENTATION_INVALID"
    try:
        raw = base64.b64decode(encoded, validate=True)
        text = raw.decode("ascii")
        target = require_hkex_raw_locator(text, kind=HKEXLocatorKind.ROLE_MEMBER)
    except UnicodeDecodeError, ValueError:
        return None, "LOCATION_INVALID"
    return target, None


def _hkex_physical_start(
    *,
    controller: HKEXObservationController,
    starts: list[HKEXPhysicalStart],
    request: HKEXDynamicRequest,
    hop_number: int,
    requested_url: str,
) -> HKEXPhysicalStart | None:
    if not controller.before_physical_start(followed_redirect=hop_number == 1):
        return None
    start = HKEXPhysicalStart(
        sequence=len(starts) + 1,
        logical_request_sequence=request.sequence,
        capture_endpoint_id=request.capture_endpoint_id,
        stage="FORM_HTML_TIER",
        hop_number=hop_number,
        requested_url=requested_url,
        start_elapsed_seconds=controller.elapsed_seconds,
    )
    starts.append(start)
    return start


def capture_hkex_form_attempt(  # noqa: C901 - exact redirect evidence is one atomic capture.
    *,
    request: HKEXDynamicRequest,
    transport: ReadOnlySourceTransport,
    controller: HKEXObservationController,
    physical_starts: list[HKEXPhysicalStart],
    first_event_sequence: int,
) -> tuple[HKEXDynamicHTMLAttempt, CapturedResponse] | None:
    """Capture one Forms node with at most one followed redirect and two events."""
    initial = _hkex_physical_start(
        controller=controller,
        starts=physical_starts,
        request=request,
        hop_number=0,
        requested_url=request.requested_url,
    )
    if initial is None:
        return None
    try:
        response = transport.get(url=request.requested_url, max_bytes=request.max_bytes)
    except OSError, TimeoutError, urllib.error.URLError:
        response = CapturedResponse(0, "application/octet-stream", b"", None)
    response_reserved = controller.reserve_response(
        byte_length=len(response.body), media_type=request.media_type
    )
    events: list[HKEXRedirectEvent] = []
    effective_url = request.requested_url
    if response_reserved and response.status in _HKEX_REDIRECT_STATUSES:
        if not controller.reserve_redirect_event():
            _fail("HKEX_OBSERVATION_BUDGET_EXHAUSTED")
        probe = probe_hkex_raw_location(response.raw_location_reader)
        target, rejection = _hkex_redirect_target(probe)
        followed_start = (
            _hkex_physical_start(
                controller=controller,
                starts=physical_starts,
                request=request,
                hop_number=1,
                requested_url=target,
            )
            if rejection is None and target is not None
            else None
        )
        if rejection is None and followed_start is None:
            rejection = controller.stop_code or "BUDGET_EXHAUSTED"
        followed = rejection is None and followed_start is not None
        events.append(
            HKEXRedirectEvent(
                event_sequence=first_event_sequence,
                response_hop_number=0,
                response_status=response.status,
                source_url=request.requested_url,
                location_present=probe.location_present,
                location_octets_base64_prefix=probe.location_octets_base64_prefix,
                prefix_octet_count=probe.prefix_octet_count,
                representation_complete=probe.representation_complete,
                total_octet_count=probe.total_octet_count,
                over_limit=probe.over_limit,
                validated_target_url=target,
                followed=followed,
                rejection_code=rejection,
                target_physical_start_sequence=(
                    followed_start.sequence if followed_start is not None else None
                ),
                target_start_elapsed_seconds=(
                    followed_start.start_elapsed_seconds if followed_start is not None else None
                ),
            )
        )
        if followed and target is not None:
            effective_url = target
            try:
                response = transport.get(url=target, max_bytes=request.max_bytes)
            except OSError, TimeoutError, urllib.error.URLError:
                response = CapturedResponse(0, "application/octet-stream", b"", None)
            response_reserved = controller.reserve_response(
                byte_length=len(response.body), media_type=request.media_type
            )
            if response_reserved and response.status in _HKEX_REDIRECT_STATUSES:
                if not controller.reserve_redirect_event():
                    _fail("HKEX_OBSERVATION_BUDGET_EXHAUSTED")
                second_probe = probe_hkex_raw_location(response.raw_location_reader)
                events.append(
                    HKEXRedirectEvent(
                        event_sequence=first_event_sequence + 1,
                        response_hop_number=1,
                        response_status=response.status,
                        source_url=target,
                        location_present=second_probe.location_present,
                        location_octets_base64_prefix=(second_probe.location_octets_base64_prefix),
                        prefix_octet_count=second_probe.prefix_octet_count,
                        representation_complete=second_probe.representation_complete,
                        total_octet_count=second_probe.total_octet_count,
                        over_limit=second_probe.over_limit,
                        validated_target_url=None,
                        followed=False,
                        rejection_code="SECOND_REDIRECT_REJECTED",
                        target_physical_start_sequence=None,
                        target_start_elapsed_seconds=None,
                    )
                )
    physical_terminal = (
        _physical_response_terminal(
            response,
            requested_url=effective_url,
            max_bytes=request.max_bytes,
        )
        if response_reserved
        else "TRUNCATED"
    )
    if physical_terminal == "CAPTURED" and response.media_type != request.media_type:
        physical_terminal = "SOURCE_CONTRACT_CHANGED"
    rejected = any(item.rejection_code is not None for item in events)
    semantic_terminal = "SOURCE_CONTRACT_CHANGED" if rejected else physical_terminal
    return (
        HKEXDynamicHTMLAttempt(
            sequence=request.sequence,
            capture_endpoint_id=request.capture_endpoint_id,
            endpoint_version=request.endpoint_version,
            relation=request.relation,
            requested_url=request.requested_url,
            initial_physical_start_sequence=initial.sequence,
            initial_start_elapsed_seconds=initial.start_elapsed_seconds,
            redirect_events=tuple(events),
            final_url=response.final_url,
            status=response.status,
            media_type=response.media_type,
            redirect_rejected=rejected,
            physical_terminal_code=physical_terminal,
            semantic_terminal_code=semantic_terminal,
        ),
        response,
    )


def derive_hkex_form_member(
    *,
    request: HKEXDynamicRequest,
    attempt: HKEXDynamicHTMLAttempt,
    response: CapturedResponse,
    board: HKEXPublisherBoard,
    capture_id_by_url: Mapping[str, str],
) -> tuple[HKEXPageIdentity, tuple[HKEXMembershipAssociation, ...]]:
    """Parse one fully captured Forms member into identity and PDF association facts."""
    try:
        if (
            type(request) is not HKEXDynamicRequest
            or type(attempt) is not HKEXDynamicHTMLAttempt
            or type(response) is not CapturedResponse
            or type(board) is not HKEXPublisherBoard
            or attempt.sequence != request.sequence
            or attempt.capture_endpoint_id != request.capture_endpoint_id
            or attempt.endpoint_version != request.endpoint_version
            or attempt.relation is not HKEXMembershipRelation.FORM_NODE
            or attempt.requested_url != request.requested_url
            or attempt.physical_terminal_code != "CAPTURED"
            or attempt.semantic_terminal_code != "CAPTURED"
            or attempt.redirect_rejected
            or type(response.final_url) is not str
            or attempt.final_url != response.final_url
            or attempt.status != response.status
            or attempt.media_type != response.media_type
        ):
            _hkex_plan_require(condition=False)
        capture = parse_hkex_form_member(
            response.body,
            requested_node_url=request.requested_url,
            final_url=cast("str", response.final_url),
            board=board,
            capture_id_by_url=capture_id_by_url,
        )
        identity = capture.identity
        return (
            HKEXPageIdentity(
                capture_endpoint_id=request.capture_endpoint_id,
                requested_url=request.requested_url,
                final_url=cast("str", response.final_url),
                canonical_url=identity.canonical_url,
                shortlink_url=identity.shortlink_url,
                node_id=identity.node_id,
                entire_section_url=identity.entire_section_url,
            ),
            capture.associations,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(_HKEX_FORM_MEMBER_CAPTURE_INVALID) from error


def _capture_hkex_direct_request(  # noqa: PLR0913 - one exact physical request boundary
    *,
    sequence: int,
    capture_endpoint_id: str,
    endpoint_version: str,
    stage: str,
    requested_url: str,
    media_type: str,
    max_bytes: int,
    transport: ReadOnlySourceTransport,
    controller: HKEXObservationController,
    physical_starts: list[HKEXPhysicalStart],
) -> HKEXCapturedEndpoint | None:
    if not controller.before_physical_start():
        return None
    start = HKEXPhysicalStart(
        sequence=len(physical_starts) + 1,
        logical_request_sequence=sequence,
        capture_endpoint_id=capture_endpoint_id,
        stage=stage,
        hop_number=0,
        requested_url=requested_url,
        start_elapsed_seconds=controller.elapsed_seconds,
    )
    physical_starts.append(start)
    try:
        response = transport.get(url=requested_url, max_bytes=max_bytes)
    except OSError, TimeoutError, urllib.error.URLError:
        response = CapturedResponse(0, "application/octet-stream", b"", None)
    if not controller.reserve_response(byte_length=len(response.body), media_type=media_type):
        terminal = "TRUNCATED"
    else:
        terminal = _physical_response_terminal(
            response, requested_url=requested_url, max_bytes=max_bytes
        )
        if response.media_type != media_type or response.final_url != requested_url:
            terminal = "SOURCE_CONTRACT_CHANGED"
    return HKEXCapturedEndpoint(
        sequence=sequence,
        capture_endpoint_id=capture_endpoint_id,
        endpoint_version=endpoint_version,
        stage=stage,
        requested_url=requested_url,
        max_bytes=max_bytes,
        response=response,
        terminal_code=terminal,
    )


def _hkex_capture_result(  # noqa: PLR0913 - immutable phased result projection
    *,
    plan_state: str,
    plan: HKEXTraversalPlan | None,
    captures: list[HKEXCapturedEndpoint],
    dynamic_html_attempts: list[HKEXDynamicHTMLAttempt],
    physical_starts: list[HKEXPhysicalStart],
    page_identities: list[HKEXPageIdentity],
    controller: HKEXObservationController,
) -> HKEXRoleAwareCapture:
    return HKEXRoleAwareCapture(
        plan_state=plan_state,
        plan=plan,
        captures=tuple(captures),
        dynamic_html_attempts=tuple(dynamic_html_attempts),
        physical_starts=tuple(physical_starts),
        page_identities=tuple(page_identities),
        followed_redirect_starts=controller.followed_redirect_starts,
        redirect_event_count=controller.redirect_events,
        retained_response_bytes=controller.retained_response_bytes,
        pacing_sleep_count=controller.pacing_sleep_count,
        pacing_sleep_seconds=controller.pacing_sleep_seconds,
        elapsed_seconds=controller.elapsed_seconds,
        stop_code=controller.stop_code,
    )


def capture_hkex_role_aware(  # noqa: C901, PLR0911, PLR0912
    *,
    endpoints: tuple[OfficialEndpointContract, ...],
    transport: ReadOnlySourceTransport,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> HKEXRoleAwareCapture:
    """Capture the exact static, complete Forms, and frozen PDF tiers in order."""
    controller = HKEXObservationController(clock=clock, sleeper=sleeper)
    captures: list[HKEXCapturedEndpoint] = []
    attempts: list[HKEXDynamicHTMLAttempt] = []
    physical_starts: list[HKEXPhysicalStart] = []
    identities: list[HKEXPageIdentity] = []
    static_bodies: dict[str, bytes] = {}
    for sequence, endpoint in enumerate(endpoints, start=1):
        media_type = endpoint.media_types[0]
        captured = _capture_hkex_direct_request(
            sequence=sequence,
            capture_endpoint_id=endpoint.endpoint_id,
            endpoint_version=endpoint.version,
            stage="STATIC",
            requested_url=endpoint.url,
            media_type=media_type,
            max_bytes=endpoint.max_bytes,
            transport=transport,
            controller=controller,
            physical_starts=physical_starts,
        )
        if captured is None:
            return _hkex_capture_result(
                plan_state="STATIC_CAPTURE_INCOMPLETE",
                plan=None,
                captures=captures,
                dynamic_html_attempts=attempts,
                physical_starts=physical_starts,
                page_identities=identities,
                controller=controller,
            )
        captures.append(captured)
        if captured.terminal_code != "CAPTURED":
            return _hkex_capture_result(
                plan_state="STATIC_CAPTURE_INCOMPLETE",
                plan=None,
                captures=captures,
                dynamic_html_attempts=attempts,
                physical_starts=physical_starts,
                page_identities=identities,
                controller=controller,
            )
        static_bodies[endpoint.endpoint_id] = captured.response.body
    try:
        initial_plan = build_hkex_traversal_plan(static_bodies, endpoints)
    except _HKEXPlanPolicyLimitError:
        return _hkex_capture_result(
            plan_state="ROOT_POLICY_LIMIT_EXCEEDED",
            plan=None,
            captures=captures,
            dynamic_html_attempts=attempts,
            physical_starts=physical_starts,
            page_identities=identities,
            controller=controller,
        )
    except ValueError:
        return _hkex_capture_result(
            plan_state="ROOT_CONTRACT_CHANGED",
            plan=None,
            captures=captures,
            dynamic_html_attempts=attempts,
            physical_starts=physical_starts,
            page_identities=identities,
            controller=controller,
        )
    board_by_capture = {
        association.capture_endpoint_id: association.board
        for association in initial_plan.associations
        if association.relation is HKEXMembershipRelation.FORM_NODE
    }
    form_bodies: dict[str, bytes] = {}
    form_final_urls: dict[str, str] = {}
    capture_id_by_url = {endpoint.url: endpoint.endpoint_id for endpoint in endpoints}
    for request in initial_plan.form_html_requests:
        captured_attempt = capture_hkex_form_attempt(
            request=request,
            transport=transport,
            controller=controller,
            physical_starts=physical_starts,
            first_event_sequence=controller.redirect_events + 1,
        )
        if captured_attempt is None:
            return _hkex_capture_result(
                plan_state="FORM_HTML_TIER_INCOMPLETE",
                plan=initial_plan,
                captures=captures,
                dynamic_html_attempts=attempts,
                physical_starts=physical_starts,
                page_identities=identities,
                controller=controller,
            )
        attempt, response = captured_attempt
        attempts.append(attempt)
        terminal = attempt.semantic_terminal_code
        captures.append(
            HKEXCapturedEndpoint(
                sequence=request.sequence,
                capture_endpoint_id=request.capture_endpoint_id,
                endpoint_version=request.endpoint_version,
                stage="FORM_HTML_TIER",
                requested_url=request.requested_url,
                max_bytes=request.max_bytes,
                response=response,
                terminal_code=terminal,
            )
        )
        if terminal != "CAPTURED":
            return _hkex_capture_result(
                plan_state="FORM_HTML_TIER_INCOMPLETE",
                plan=initial_plan,
                captures=captures,
                dynamic_html_attempts=attempts,
                physical_starts=physical_starts,
                page_identities=identities,
                controller=controller,
            )
        try:
            identity, _form_associations = derive_hkex_form_member(
                request=request,
                attempt=attempt,
                response=response,
                board=board_by_capture[request.capture_endpoint_id],
                capture_id_by_url=capture_id_by_url,
            )
        except KeyError, ValueError:
            captures[-1] = replace(captures[-1], terminal_code="SOURCE_CONTRACT_CHANGED")
            return _hkex_capture_result(
                plan_state="FORM_MEMBER_CONTRACT_CHANGED",
                plan=initial_plan,
                captures=captures,
                dynamic_html_attempts=attempts,
                physical_starts=physical_starts,
                page_identities=identities,
                controller=controller,
            )
        identities.append(identity)
        form_bodies[request.requested_url] = response.body
        form_final_urls[request.requested_url] = identity.final_url
    try:
        plan = finalize_hkex_traversal_plan(
            initial_plan,
            form_bodies=form_bodies,
            form_final_urls=form_final_urls,
            endpoints=endpoints,
        )
    except ValueError:
        return _hkex_capture_result(
            plan_state="FORM_MEMBER_CONTRACT_CHANGED",
            plan=initial_plan,
            captures=captures,
            dynamic_html_attempts=attempts,
            physical_starts=physical_starts,
            page_identities=identities,
            controller=controller,
        )
    for request in plan.pdf_requests:
        captured = _capture_hkex_direct_request(
            sequence=request.sequence,
            capture_endpoint_id=request.capture_endpoint_id,
            endpoint_version=request.endpoint_version,
            stage="PDF_TIER",
            requested_url=request.requested_url,
            media_type=request.media_type,
            max_bytes=request.max_bytes,
            transport=transport,
            controller=controller,
            physical_starts=physical_starts,
        )
        if captured is None:
            return _hkex_capture_result(
                plan_state="COMPLETE_PLAN",
                plan=plan,
                captures=captures,
                dynamic_html_attempts=attempts,
                physical_starts=physical_starts,
                page_identities=identities,
                controller=controller,
            )
        if captured.terminal_code == "CAPTURED":
            try:
                require_hkex_pdf(captured.response.body)
            except ValueError:
                captured = replace(captured, terminal_code="SOURCE_CONTRACT_CHANGED")
        captures.append(captured)
        if captured.terminal_code != "CAPTURED":
            break
    return _hkex_capture_result(
        plan_state="COMPLETE_PLAN",
        plan=plan,
        captures=captures,
        dynamic_html_attempts=attempts,
        physical_starts=physical_starts,
        page_identities=identities,
        controller=controller,
    )


def _hkex_role_aware_accounting(capture: HKEXRoleAwareCapture) -> dict[str, object]:
    plan = capture.plan
    plan_absent_state = capture.plan_state in {
        "STATIC_CAPTURE_INCOMPLETE",
        "ROOT_CONTRACT_CHANGED",
        "ROOT_POLICY_LIMIT_EXCEEDED",
    }
    if capture.plan_state not in _HKEX_PLAN_STATES or plan_absent_state != (plan is None):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    typed_plan = plan if type(plan) is HKEXTraversalPlan else None
    associations = typed_plan.associations if typed_plan is not None else ()
    static_ids = {item.capture_endpoint_id for item in capture.captures if item.stage == "STATIC"}
    reused_static_targets = {
        item.capture_endpoint_id
        for item in associations
        if item.fetch_disposition is HKEXFetchDisposition.PLANNED_OR_REUSED
        and item.capture_endpoint_id in static_ids
    }
    return {
        "declared_associations": (
            typed_plan.accounting.declared_associations if typed_plan is not None else 0
        ),
        "dynamic_html_attempted": sum(item.stage == "FORM_HTML_TIER" for item in capture.captures),
        "dynamic_html_planned": (
            typed_plan.accounting.unique_dynamic_html_requests if typed_plan is not None else 0
        ),
        "dynamic_pdf_attempted": sum(item.stage == "PDF_TIER" for item in capture.captures),
        "dynamic_pdf_planned": (
            typed_plan.accounting.unique_dynamic_pdf_requests
            if typed_plan is not None and capture.plan_state == "COMPLETE_PLAN"
            else 0
        ),
        "elapsed_seconds": capture.elapsed_seconds,
        "followed_redirect_starts": capture.followed_redirect_starts,
        "logical_request_starts": len(capture.captures),
        "pacing_sleep_count": capture.pacing_sleep_count,
        "pacing_sleep_seconds": capture.pacing_sleep_seconds,
        "physical_request_starts": len(capture.physical_starts),
        "planned_or_reused_associations": (
            typed_plan.accounting.planned_or_reused_associations if typed_plan is not None else 0
        ),
        "raw_attachment_occurrences": (
            len(typed_plan.attachment_occurrences) if typed_plan is not None else 0
        ),
        "redirect_event_count": capture.redirect_event_count,
        "retained_raw_location_octets": sum(
            event.prefix_octet_count
            for attempt in capture.dynamic_html_attempts
            for event in attempt.redirect_events
        ),
        "retained_response_bytes": capture.retained_response_bytes,
        "reused_static_targets": len(reused_static_targets),
        "semantic_only_associations": (
            typed_plan.accounting.semantic_only_associations if typed_plan is not None else 0
        ),
        "static_attempted": sum(item.stage == "STATIC" for item in capture.captures),
        "static_planned": (
            typed_plan.accounting.static_registered_requests
            if typed_plan is not None
            else _HKEX_STATIC_ENDPOINT_COUNT
        ),
        "stop_code": capture.stop_code,
        "unfetched_external_associations": (
            typed_plan.accounting.unfetched_external_associations if typed_plan is not None else 0
        ),
        "unique_dynamic_html_urls": (
            typed_plan.accounting.unique_dynamic_html_requests if typed_plan is not None else 0
        ),
        "unique_dynamic_pdf_urls": (
            typed_plan.accounting.unique_dynamic_pdf_requests
            if typed_plan is not None and capture.plan_state == "COMPLETE_PLAN"
            else 0
        ),
    }


def hkex_role_aware_report_fields(capture: HKEXRoleAwareCapture) -> dict[str, object]:
    """Project one closed phased capture into the strict schema-2 HKEX fields."""
    if type(capture) is not HKEXRoleAwareCapture or capture.plan_state not in _HKEX_PLAN_STATES:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    plan_projection: dict[str, object] = (
        hkex_traversal_plan_projection(capture.plan)
        if type(capture.plan) is HKEXTraversalPlan
        else {
            "attachment_occurrences": cast("list[object]", []),
            "membership_associations": cast("list[object]", []),
            "root_bindings": cast("list[object]", []),
            "staged_requests": cast("list[object]", []),
        }
    )
    if capture.plan_state != "COMPLETE_PLAN":
        plan_projection["staged_requests"] = [
            item
            for item in cast("list[dict[str, object]]", plan_projection["staged_requests"])
            if item["stage"] == "FORM_HTML_TIER"
        ]
    transport_projection = hkex_transport_projection(
        capture.dynamic_html_attempts,
        capture.physical_starts,
        capture.page_identities,
    )
    membership_projection: dict[str, object] = {
        "attachment_occurrences": plan_projection["attachment_occurrences"],
        "membership_associations": plan_projection["membership_associations"],
        "root_bindings": plan_projection["root_bindings"],
    }
    return {
        "execution_policy": hkex_execution_policy(),
        "execution_policy_fingerprint": hkex_execution_policy_fingerprint(),
        "hkex_attachment_occurrences": plan_projection["attachment_occurrences"],
        "hkex_dynamic_html_attempts": transport_projection["dynamic_html_attempts"],
        "hkex_membership_associations": plan_projection["membership_associations"],
        "hkex_membership_fingerprint": _digest(_canonical(membership_projection)),
        "hkex_plan_state": capture.plan_state,
        "hkex_page_identities": transport_projection["page_identities"],
        "hkex_physical_starts": transport_projection["physical_starts"],
        "hkex_request_plan": plan_projection["staged_requests"],
        "hkex_root_bindings": plan_projection["root_bindings"],
        "hkex_traversal_accounting": _hkex_role_aware_accounting(capture),
        "report_schema_version": "2.0.0",
    }


def _require_hkex_measured_accounting(capture: HKEXRoleAwareCapture) -> None:
    """Check measured pacing/event facts against the retained physical ledger."""
    starts = capture.physical_starts
    maximum_sleep_count = max(0, len(starts) - 1)
    expected_elapsed = starts[-1].start_elapsed_seconds if starts else 0.0
    if (
        type(capture.pacing_sleep_count) is not int
        or not 0 <= capture.pacing_sleep_count <= maximum_sleep_count
        or type(capture.pacing_sleep_seconds) is not float
        or not math.isfinite(capture.pacing_sleep_seconds)
        or capture.pacing_sleep_seconds < 0.0
        or capture.pacing_sleep_seconds
        > capture.pacing_sleep_count * _HKEX_MINIMUM_START_INTERVAL_SECONDS + 1e-12
        or (capture.pacing_sleep_count == 0) != (capture.pacing_sleep_seconds == 0.0)
        or capture.elapsed_seconds != expected_elapsed
        or capture.redirect_event_count
        != sum(len(item.redirect_events) for item in capture.dynamic_html_attempts)
        or capture.redirect_event_count > _HKEX_REDIRECT_EVENT_LIMIT
        or capture.followed_redirect_starts != sum(item.hop_number == 1 for item in starts)
        or capture.followed_redirect_starts > _HKEX_FOLLOWED_REDIRECT_START_LIMIT
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)


def require_hkex_role_aware_report_fields(
    projection: object, capture: HKEXRoleAwareCapture
) -> None:
    """Accept only fields byte-canonically rederived from one typed complete capture."""
    try:
        _require_hkex_measured_accounting(capture)
        if _canonical(projection) != _canonical(hkex_role_aware_report_fields(capture)):
            _hkex_plan_require(condition=False)
    except (TypeError, ValueError) as error:
        raise ValueError(_HKEX_ROLE_AWARE_REPORT_INVALID) from error


def _hkex_role_capture_complete(
    capture_by_id: Mapping[str, HKEXCapturedEndpoint],
    associations: tuple[HKEXMembershipAssociation, ...],
    *,
    source_id: str,
) -> bool:
    required_ids = {
        item.capture_endpoint_id
        for item in associations
        if item.source_id == source_id
        and item.fetch_disposition is HKEXFetchDisposition.PLANNED_OR_REUSED
    }
    return None not in required_ids and all(
        capture_id in capture_by_id and capture_by_id[capture_id].terminal_code == "CAPTURED"
        for capture_id in required_ids
        if capture_id is not None
    )


def hkex_role_aware_procedures(
    capture: HKEXRoleAwareCapture,
) -> list[dict[str, object]]:
    """Derive the five current HKEX procedures from one closed role-aware capture."""
    plan = capture.plan
    if capture.plan_state not in _HKEX_PLAN_STATES:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    if capture.plan_state != "COMPLETE_PLAN":
        association_counts = {
            source_id: (
                sum(item.source_id == source_id for item in plan.associations)
                if type(plan) is HKEXTraversalPlan
                else 0
            )
            for source_id in _PROCEDURE_SOURCE_IDS["HKEX"]
        }
        return [
            {
                "declared_member_count": association_counts[source_id],
                "source_id": source_id,
                "terminal_code": (
                    "SOURCE_CONTRACT_CHANGED"
                    if capture.plan_state == "FORM_MEMBER_CONTRACT_CHANGED"
                    and source_id == "HK-REG-HKEX-REGULATORY-FORMS"
                    else "BUDGET_EXHAUSTED"
                    if capture.stop_code is not None
                    else "INCOMPLETE"
                ),
            }
            for source_id in sorted(_PROCEDURE_SOURCE_IDS["HKEX"])
        ]
    if type(plan) is not HKEXTraversalPlan:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    capture_by_id = {item.capture_endpoint_id: item for item in capture.captures}
    catalogue_id = _hkex_endpoint_id(309)
    catalogue_count = 0
    catalogue_terminal = "INCOMPLETE"
    try:
        catalogue_capture = capture_by_id[catalogue_id]
        if catalogue_capture.terminal_code != "CAPTURED":
            _fail("HKEX_CATALOGUE_CAPTURE_INCOMPLETE")
        catalogue_count = len(parse_hkex_catalogue(catalogue_capture.response.body).role_roots)
        catalogue_terminal = "COMPLETE"
    except KeyError, TypeError, ValueError:
        if capture_by_id.get(catalogue_id) is not None:
            catalogue_terminal = "SOURCE_CONTRACT_CHANGED"
    consolidated_ids = tuple(_hkex_endpoint_id(item) for item in (301, 302, 310, 311, 312))
    consolidated_terminal = "COMPLETE"
    try:
        if any(capture_by_id[item].terminal_code != "CAPTURED" for item in consolidated_ids):
            _fail("HKEX_CONSOLIDATED_CAPTURE_INCOMPLETE")
        require_hkex_pdf(capture_by_id[_hkex_endpoint_id(311)].response.body)
        require_hkex_pdf(capture_by_id[_hkex_endpoint_id(312)].response.body)
    except KeyError, ValueError:
        consolidated_terminal = "SOURCE_CONTRACT_CHANGED"
    counts = {
        source_id: sum(item.source_id == source_id for item in plan.associations)
        for source_id in (
            "HK-REG-HKEX-FEES-RULES",
            "HK-REG-HKEX-REGULATORY-FORMS",
            "HK-REG-HKEX-RULE-UPDATES",
        )
    }
    procedures: list[dict[str, object]] = [
        {
            "declared_member_count": 5 if consolidated_terminal == "COMPLETE" else 0,
            "source_id": "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
            "terminal_code": consolidated_terminal,
        }
    ]
    for source_id in (
        "HK-REG-HKEX-FEES-RULES",
        "HK-REG-HKEX-REGULATORY-FORMS",
        "HK-REG-HKEX-RULE-UPDATES",
    ):
        complete = _hkex_role_capture_complete(
            capture_by_id, plan.associations, source_id=source_id
        )
        has_external = any(
            item.source_id == source_id
            and item.fetch_disposition is HKEXFetchDisposition.UNFETCHED_EXTERNAL_REFERENCE
            for item in plan.associations
        )
        terminal = (
            "EXTERNAL_REFERENCE_AUTHORITY_REQUIRED"
            if complete and has_external
            else "COMPLETE"
            if complete
            else "INCOMPLETE"
        )
        procedures.append(
            {
                "declared_member_count": counts[source_id],
                "source_id": source_id,
                "terminal_code": terminal,
            }
        )
    procedures.append(
        {
            "declared_member_count": catalogue_count,
            "source_id": "HK-REG-HKEX-RULEBOOK-CATALOGUE",
            "terminal_code": catalogue_terminal,
        }
    )
    return sorted(procedures, key=lambda item: cast("str", item["source_id"]))


def hkex_role_aware_result(
    capture: HKEXRoleAwareCapture, procedures: list[dict[str, object]]
) -> str:
    """Derive the family result with ordinary terminal precedence."""
    counts: dict[str, int] = {}
    for item in capture.captures:
        counts[item.terminal_code] = counts.get(item.terminal_code, 0) + 1
    if capture.plan_state in {"ROOT_CONTRACT_CHANGED", "FORM_MEMBER_CONTRACT_CHANGED"}:
        return "SOURCE_CONTRACT_CHANGED"
    return _derived_report_result(counts, procedures)


def publish_hkex_role_aware_report(  # noqa: PLR0913 - exact report binding is explicit
    *,
    output_root: Path,
    attempt_id: str,
    observation_cutoff: str,
    authority_manifest_fingerprint: str,
    authority_provenance: str,
    execution_authorization_fingerprint: str,
    predecessor_attempt_id: str | None,
    capture: HKEXRoleAwareCapture,
) -> dict[str, object]:
    """Retain every complete candidate object and publish its schema-2 report last."""
    if (
        _ATTEMPT_ID.fullmatch(attempt_id) is None
        or authority_provenance != _AUTHORITY
        or _FINGERPRINT.fullmatch(authority_manifest_fingerprint) is None
        or _FINGERPRINT.fullmatch(execution_authorization_fingerprint) is None
        or capture.plan_state not in _HKEX_PLAN_STATES
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    _parse_hong_kong_cutoff(observation_cutoff)
    if predecessor_attempt_id is not None and _ATTEMPT_ID.fullmatch(predecessor_attempt_id) is None:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    records: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for item in capture.captures:
        body = item.response.body
        fingerprint = _digest(body)
        object_key = f"objects/{fingerprint.removeprefix('sha256:')}.bin"
        _write_immutable(output_root / object_key, body)
        records.append(
            {
                "body_fingerprint": fingerprint,
                "byte_length": len(body),
                "endpoint_id": item.capture_endpoint_id,
                "endpoint_version": item.endpoint_version,
                "media_type": item.response.media_type,
                "method": "GET",
                "object_key": object_key,
                "requested_url": item.requested_url,
                "status": item.response.status,
                "terminal_code": item.terminal_code,
            }
        )
        counts[item.terminal_code] = counts.get(item.terminal_code, 0) + 1
    procedures = hkex_role_aware_procedures(capture)
    report: dict[str, object] = {
        "attempt_id": attempt_id,
        "authority_manifest_fingerprint": authority_manifest_fingerprint,
        "authority_provenance": authority_provenance,
        "change_state": "FIRST_OBSERVATION",
        "endpoint_counts": dict(sorted(counts.items())),
        "endpoints": records,
        "execution_authorization_fingerprint": execution_authorization_fingerprint,
        "observation_cutoff": observation_cutoff,
        "predecessor_attempt_id": predecessor_attempt_id,
        "readback_verified": True,
        "result": hkex_role_aware_result(capture, procedures),
        "source_family": "HKEX",
        "source_procedures": procedures,
        **hkex_role_aware_report_fields(capture),
    }
    if frozenset(report) != _HKEX_ROLE_AWARE_REPORT_KEYS:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    report_path = output_root / "attempts" / attempt_id / "report.json"
    _publish_attempt_report(report_path, _canonical(report))
    return report


_HKEX_REDIRECT_EVENT_KEYS = frozenset(
    {
        "event_sequence",
        "followed",
        "location_octets_base64_prefix",
        "location_present",
        "over_limit",
        "prefix_octet_count",
        "rejection_code",
        "representation_complete",
        "response_hop_number",
        "response_status",
        "source_url",
        "target_physical_start_sequence",
        "target_start_elapsed_seconds",
        "total_octet_count",
        "validated_target_url",
    }
)
_HKEX_DYNAMIC_ATTEMPT_KEYS = frozenset(
    {
        "capture_endpoint_id",
        "endpoint_version",
        "final_url",
        "initial_physical_start_sequence",
        "initial_start_elapsed_seconds",
        "media_type",
        "physical_terminal_code",
        "redirect_events",
        "redirect_rejected",
        "relation",
        "requested_url",
        "semantic_terminal_code",
        "sequence",
        "status",
    }
)
_HKEX_PHYSICAL_START_KEYS = frozenset(
    {
        "capture_endpoint_id",
        "hop_number",
        "logical_request_sequence",
        "requested_url",
        "sequence",
        "stage",
        "start_elapsed_seconds",
    }
)


def _hkex_exact_dict(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    item = cast("dict[str, object]", value)
    if frozenset(item) != keys:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    return item


def _hkex_exact_int(value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    return value


def _hkex_exact_float(value: object) -> float:
    if type(value) not in {int, float}:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    exact = cast("int | float", value)
    if not math.isfinite(exact) or exact < 0:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    return float(exact)


def _hkex_optional_str(value: object) -> str | None:
    if value is not None and type(value) is not str:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    return value


def _hkex_parse_redirect_event(  # noqa: C901, PLR0912, PLR0915 - one closed event gate.
    value: object,
) -> HKEXRedirectEvent:
    item = _hkex_exact_dict(value, _HKEX_REDIRECT_EVENT_KEYS)
    location_present = item["location_present"]
    complete = item["representation_complete"]
    over_limit = item["over_limit"]
    followed = item["followed"]
    if any(type(flag) is not bool for flag in (location_present, complete, over_limit, followed)):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    encoded = item["location_octets_base64_prefix"]
    raw: bytes | None = None
    prefix_count = _hkex_exact_int(item["prefix_octet_count"])
    total = item["total_octet_count"]
    if total is not None:
        total = _hkex_exact_int(total)
    if location_present:
        if type(encoded) is not str or len(encoded) > _HKEX_LOCATION_BASE64_CHARS:
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError(_HKEX_ROLE_AWARE_REPORT_INVALID) from error
        if (
            len(raw) != prefix_count
            or base64.b64encode(raw).decode("ascii") != encoded
            or prefix_count > _HKEX_LOCATION_PREFIX_OCTETS
            or (complete and total != prefix_count)
            or (
                not complete and (prefix_count != _HKEX_LOCATION_PREFIX_OCTETS or total is not None)
            )
            or over_limit != (prefix_count > _HKEX_LOCATION_ADMISSION_OCTETS or not complete)
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    elif (
        encoded is not None
        or prefix_count != 0
        or complete is not True
        or total is not None
        or over_limit is not False
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    target_sequence = item["target_physical_start_sequence"]
    if target_sequence is not None:
        target_sequence = _hkex_exact_int(target_sequence, minimum=1)
    target_elapsed = item["target_start_elapsed_seconds"]
    if target_elapsed is not None:
        target_elapsed = _hkex_exact_float(target_elapsed)
    event = HKEXRedirectEvent(
        event_sequence=_hkex_exact_int(item["event_sequence"], minimum=1),
        response_hop_number=_hkex_exact_int(item["response_hop_number"]),
        response_status=_hkex_exact_int(item["response_status"]),
        source_url=cast("str", item["source_url"]),
        location_present=cast("bool", location_present),
        location_octets_base64_prefix=encoded,
        prefix_octet_count=prefix_count,
        representation_complete=cast("bool", complete),
        total_octet_count=total,
        over_limit=cast("bool", over_limit),
        validated_target_url=_hkex_optional_str(item["validated_target_url"]),
        followed=cast("bool", followed),
        rejection_code=_hkex_optional_str(item["rejection_code"]),
        target_physical_start_sequence=target_sequence,
        target_start_elapsed_seconds=target_elapsed,
    )
    if (
        type(event.source_url) is not str
        or event.response_hop_number not in {0, 1}
        or event.response_status not in _HKEX_REDIRECT_STATUSES
        or event.followed
        != (
            event.rejection_code is None
            and event.validated_target_url is not None
            and event.target_physical_start_sequence is not None
            and event.target_start_elapsed_seconds is not None
        )
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    if event.response_hop_number == 1:
        if (
            event.followed
            or event.validated_target_url is not None
            or event.rejection_code != "SECOND_REDIRECT_REJECTED"
            or event.target_physical_start_sequence is not None
            or event.target_start_elapsed_seconds is not None
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        return event
    if not event.location_present:
        if event.validated_target_url is not None or event.rejection_code != "LOCATION_MISSING":
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        return event
    if event.over_limit:
        if (
            event.validated_target_url is not None
            or event.rejection_code != "LOCATION_OVER_LIMIT"
            or event.followed
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        return event
    if raw is None:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    try:
        derived_target = require_hkex_raw_locator(
            raw.decode("ascii"), kind=HKEXLocatorKind.ROLE_MEMBER
        )
    except UnicodeDecodeError, ValueError:
        if event.validated_target_url is not None or event.rejection_code != "LOCATION_INVALID":
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        return event
    if event.validated_target_url != derived_target or (
        not event.followed
        and (
            event.rejection_code not in {"BUDGET_EXHAUSTED", "OBSERVATION_BUDGET_EXHAUSTED"}
            or event.target_physical_start_sequence is not None
            or event.target_start_elapsed_seconds is not None
        )
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    return event


def _hkex_parse_dynamic_attempt(value: object) -> HKEXDynamicHTMLAttempt:
    item = _hkex_exact_dict(value, _HKEX_DYNAMIC_ATTEMPT_KEYS)
    raw_events = item["redirect_events"]
    if type(raw_events) is not list:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    typed_events = cast("list[object]", raw_events)
    if len(typed_events) > _HKEX_REDIRECT_EVENTS_PER_ATTEMPT:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    events = tuple(_hkex_parse_redirect_event(event) for event in typed_events)
    redirect_rejected = item["redirect_rejected"]
    if type(redirect_rejected) is not bool:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    attempt = HKEXDynamicHTMLAttempt(
        sequence=_hkex_exact_int(item["sequence"], minimum=1),
        capture_endpoint_id=cast("str", item["capture_endpoint_id"]),
        endpoint_version=cast("str", item["endpoint_version"]),
        relation=HKEXMembershipRelation(cast("str", item["relation"])),
        requested_url=cast("str", item["requested_url"]),
        initial_physical_start_sequence=_hkex_exact_int(
            item["initial_physical_start_sequence"], minimum=1
        ),
        initial_start_elapsed_seconds=_hkex_exact_float(item["initial_start_elapsed_seconds"]),
        redirect_events=events,
        final_url=_hkex_optional_str(item["final_url"]),
        status=_hkex_exact_int(item["status"]),
        media_type=cast("str", item["media_type"]),
        redirect_rejected=redirect_rejected,
        physical_terminal_code=cast("str", item["physical_terminal_code"]),
        semantic_terminal_code=cast("str", item["semantic_terminal_code"]),
    )
    if (
        any(
            type(value) is not str or not value
            for value in (
                attempt.capture_endpoint_id,
                attempt.endpoint_version,
                attempt.requested_url,
                attempt.media_type,
                attempt.physical_terminal_code,
                attempt.semantic_terminal_code,
            )
        )
        or attempt.relation is not HKEXMembershipRelation.FORM_NODE
        or attempt.redirect_rejected
        != any(event.rejection_code is not None for event in attempt.redirect_events)
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    return attempt


def _hkex_parse_physical_start(value: object) -> HKEXPhysicalStart:
    item = _hkex_exact_dict(value, _HKEX_PHYSICAL_START_KEYS)
    start = HKEXPhysicalStart(
        sequence=_hkex_exact_int(item["sequence"], minimum=1),
        logical_request_sequence=_hkex_exact_int(item["logical_request_sequence"], minimum=1),
        capture_endpoint_id=cast("str", item["capture_endpoint_id"]),
        stage=cast("str", item["stage"]),
        hop_number=_hkex_exact_int(item["hop_number"]),
        requested_url=cast("str", item["requested_url"]),
        start_elapsed_seconds=_hkex_exact_float(item["start_elapsed_seconds"]),
    )
    if (
        any(
            type(value) is not str or not value
            for value in (start.capture_endpoint_id, start.requested_url)
        )
        or start.stage not in {"STATIC", "FORM_HTML_TIER", "PDF_TIER"}
        or start.hop_number not in {0, 1}
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    return start


def _hkex_read_role_aware_records(
    report: dict[str, object], *, output_root: Path
) -> tuple[list[dict[str, object]], list[bytes]]:
    raw_records = report.get("endpoints")
    if type(raw_records) is not list:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    records: list[dict[str, object]] = []
    bodies: list[bytes] = []
    resolved_root = output_root.resolve(strict=True)
    for raw_record in cast("list[object]", raw_records):
        record = _hkex_exact_dict(raw_record, _ENDPOINT_KEYS)
        if (
            type(record["endpoint_id"]) is not str
            or type(record["endpoint_version"]) is not str
            or record["method"] != "GET"
            or type(record["requested_url"]) is not str
            or type(record["media_type"]) is not str
            or type(record["status"]) is not int
            or type(record["terminal_code"]) is not str
            or type(record["byte_length"]) is not int
            or record["byte_length"] < 0
            or type(record["body_fingerprint"]) is not str
            or type(record["object_key"]) is not str
            or _OBJECT_KEY.fullmatch(record["object_key"]) is None
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        lexical_path = output_root / record["object_key"]
        try:
            metadata = lexical_path.lstat()
        except OSError as error:
            raise _HKEXRoleAwareEvidenceReadbackError from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise _HKEXRoleAwareEvidenceReadbackError
        try:
            object_path = lexical_path.resolve(strict=True)
        except OSError as error:
            raise _HKEXRoleAwareEvidenceReadbackError from error
        try:
            object_path.relative_to(resolved_root)
        except ValueError as error:
            raise ValueError(_HKEX_ROLE_AWARE_REPORT_INVALID) from error
        try:
            body = object_path.read_bytes()
        except OSError as error:
            raise _HKEXRoleAwareEvidenceReadbackError from error
        if len(body) != record["byte_length"] or _digest(body) != record["body_fingerprint"]:
            raise _HKEXRoleAwareEvidenceReadbackError
        records.append(record)
        bodies.append(body)
    return records, bodies


def _hkex_replayed_response_terminal(  # noqa: PLR0913 - exact response contract is explicit.
    record: dict[str, object],
    body: bytes,
    *,
    requested_url: str,
    final_url: str | None,
    max_bytes: int,
    expected_media_type: str,
) -> str:
    """Reclassify one retained response without trusting its claimed terminal."""
    response = CapturedResponse(
        cast("int", record["status"]),
        cast("str", record["media_type"]),
        body,
        final_url,
    )
    terminal = _physical_response_terminal(
        response,
        requested_url=requested_url,
        max_bytes=max_bytes,
    )
    if terminal == "CAPTURED" and response.media_type != expected_media_type:
        terminal = "SOURCE_CONTRACT_CHANGED"
    return terminal


def _hkex_validate_start_topology(  # noqa: C901, PLR0912 - full topology is one invariant.
    *,
    starts: tuple[HKEXPhysicalStart, ...],
    attempts: tuple[HKEXDynamicHTMLAttempt, ...],
    endpoints: tuple[OfficialEndpointContract, ...],
    plan: HKEXTraversalPlan,
) -> None:
    if tuple(item.sequence for item in starts) != tuple(range(1, len(starts) + 1)):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    if len(starts) > _HKEX_PHYSICAL_START_LIMIT:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    if any(
        later.start_elapsed_seconds - earlier.start_elapsed_seconds
        < _HKEX_MINIMUM_START_INTERVAL_SECONDS
        for earlier, later in pairwise(starts)
    ) or (starts and starts[-1].start_elapsed_seconds >= _HKEX_ELAPSED_SECONDS_LIMIT):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    by_sequence = {item.sequence: item for item in starts}
    referenced: set[int] = set()
    for sequence, endpoint in enumerate(endpoints, start=1):
        start = by_sequence.get(sequence)
        if (
            start is None
            or start.logical_request_sequence != sequence
            or start.capture_endpoint_id != endpoint.endpoint_id
            or start.stage != "STATIC"
            or start.hop_number != 0
            or start.requested_url != endpoint.url
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        referenced.add(sequence)
    attempt_by_sequence = {item.sequence: item for item in attempts}
    if set(attempt_by_sequence) != {item.sequence for item in plan.form_html_requests}:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    expected_event_sequence = 1
    for request in plan.form_html_requests:
        attempt = attempt_by_sequence[request.sequence]
        initial = by_sequence.get(attempt.initial_physical_start_sequence)
        if (
            initial is None
            or initial.logical_request_sequence != request.sequence
            or initial.capture_endpoint_id != request.capture_endpoint_id
            or initial.stage != "FORM_HTML_TIER"
            or initial.hop_number != 0
            or initial.requested_url != request.requested_url
            or initial.start_elapsed_seconds != attempt.initial_start_elapsed_seconds
            or attempt.capture_endpoint_id != request.capture_endpoint_id
            or attempt.endpoint_version != request.endpoint_version
            or attempt.requested_url != request.requested_url
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        referenced.add(initial.sequence)
        for event in attempt.redirect_events:
            if event.event_sequence != expected_event_sequence:
                _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
            expected_event_sequence += 1
            if event.followed:
                target_start = by_sequence.get(cast("int", event.target_physical_start_sequence))
                if (
                    target_start is None
                    or target_start.logical_request_sequence != request.sequence
                    or target_start.capture_endpoint_id != request.capture_endpoint_id
                    or target_start.stage != "FORM_HTML_TIER"
                    or target_start.hop_number != 1
                    or target_start.requested_url != event.validated_target_url
                    or target_start.start_elapsed_seconds != event.target_start_elapsed_seconds
                ):
                    _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
                referenced.add(target_start.sequence)
    pdf_gap_seen = False
    for request in plan.pdf_requests:
        matching = [
            item
            for item in starts
            if item.logical_request_sequence == request.sequence
            and item.capture_endpoint_id == request.capture_endpoint_id
        ]
        if not matching:
            pdf_gap_seen = True
            continue
        if len(matching) != 1 or pdf_gap_seen:
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        start = matching[0]
        if (
            start.stage != "PDF_TIER"
            or start.hop_number != 0
            or start.requested_url != request.requested_url
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        referenced.add(start.sequence)
    if referenced != set(by_sequence):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)


def _hkex_validate_partial_start_topology(  # noqa: C901 - closed prefix topology.
    *,
    starts: tuple[HKEXPhysicalStart, ...],
    captures: tuple[HKEXCapturedEndpoint, ...],
    attempts: tuple[HKEXDynamicHTMLAttempt, ...],
) -> None:
    """Validate one exact static/Forms physical prefix without inventing later work."""
    if (
        tuple(item.sequence for item in starts) != tuple(range(1, len(starts) + 1))
        or len(starts) > _HKEX_PHYSICAL_START_LIMIT
        or any(item.stage == "PDF_TIER" for item in starts)
        or any(
            later.start_elapsed_seconds - earlier.start_elapsed_seconds
            < _HKEX_MINIMUM_START_INTERVAL_SECONDS
            for earlier, later in pairwise(starts)
        )
        or (starts and starts[-1].start_elapsed_seconds >= _HKEX_ELAPSED_SECONDS_LIMIT)
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    by_sequence = {item.sequence: item for item in starts}
    referenced: set[int] = set()
    for capture in captures:
        if capture.stage != "STATIC":
            continue
        matching = [
            item
            for item in starts
            if item.logical_request_sequence == capture.sequence
            and item.capture_endpoint_id == capture.capture_endpoint_id
        ]
        if (
            len(matching) != 1
            or matching[0].stage != "STATIC"
            or matching[0].hop_number != 0
            or matching[0].requested_url != capture.requested_url
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        referenced.add(matching[0].sequence)
    expected_event_sequence = 1
    capture_by_sequence = {item.sequence: item for item in captures}
    for attempt in attempts:
        capture = capture_by_sequence.get(attempt.sequence)
        initial = by_sequence.get(attempt.initial_physical_start_sequence)
        if (
            capture is None
            or capture.stage != "FORM_HTML_TIER"
            or capture.capture_endpoint_id != attempt.capture_endpoint_id
            or initial is None
            or initial.logical_request_sequence != attempt.sequence
            or initial.capture_endpoint_id != attempt.capture_endpoint_id
            or initial.stage != "FORM_HTML_TIER"
            or initial.hop_number != 0
            or initial.requested_url != attempt.requested_url
            or initial.start_elapsed_seconds != attempt.initial_start_elapsed_seconds
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        referenced.add(initial.sequence)
        for event in attempt.redirect_events:
            if event.event_sequence != expected_event_sequence:
                _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
            expected_event_sequence += 1
            if event.followed:
                target = by_sequence.get(cast("int", event.target_physical_start_sequence))
                if (
                    target is None
                    or target.logical_request_sequence != attempt.sequence
                    or target.capture_endpoint_id != attempt.capture_endpoint_id
                    or target.stage != "FORM_HTML_TIER"
                    or target.hop_number != 1
                    or target.requested_url != event.validated_target_url
                    or target.start_elapsed_seconds != event.target_start_elapsed_seconds
                ):
                    _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
                referenced.add(target.sequence)
    if referenced != set(by_sequence):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)


def _replay_hkex_role_aware_partial_report(  # noqa: C901, PLR0912, PLR0915
    document: dict[str, object],
    *,
    records: list[dict[str, object]],
    bodies: list[bytes],
    endpoints: tuple[OfficialEndpointContract, ...],
    historical_root_contract_changed: bool = False,
) -> dict[str, object]:
    """Rederive one non-complete closed plan state from its exact retained prefix."""
    plan_state = cast("str", document["hkex_plan_state"])
    if plan_state not in _HKEX_PLAN_STATES or plan_state == "COMPLETE_PLAN":
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    raw_attempts = document["hkex_dynamic_html_attempts"]
    raw_starts = document["hkex_physical_starts"]
    if type(raw_attempts) is not list or type(raw_starts) is not list:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    attempts = tuple(
        _hkex_parse_dynamic_attempt(item) for item in cast("list[object]", raw_attempts)
    )
    starts = tuple(_hkex_parse_physical_start(item) for item in cast("list[object]", raw_starts))
    if len(records) > len(endpoints) + len(attempts):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    captures: list[HKEXCapturedEndpoint] = []
    static_bodies: dict[str, bytes] = {}
    static_count = min(len(records), len(endpoints))
    for sequence, (endpoint, record, body) in enumerate(
        zip(endpoints[:static_count], records[:static_count], bodies[:static_count], strict=True),
        start=1,
    ):
        if (
            record["endpoint_id"] != endpoint.endpoint_id
            or record["endpoint_version"] != endpoint.version
            or record["requested_url"] != endpoint.url
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        replayed_terminal = _hkex_replayed_response_terminal(
            record,
            body,
            requested_url=endpoint.url,
            final_url=endpoint.url,
            max_bytes=endpoint.max_bytes,
            expected_media_type=endpoint.media_types[0],
        )
        if record["terminal_code"] not in {replayed_terminal, "SOURCE_CONTRACT_CHANGED"}:
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        captures.append(
            HKEXCapturedEndpoint(
                sequence=sequence,
                capture_endpoint_id=endpoint.endpoint_id,
                endpoint_version=endpoint.version,
                stage="STATIC",
                requested_url=endpoint.url,
                max_bytes=endpoint.max_bytes,
                response=CapturedResponse(
                    cast("int", record["status"]),
                    cast("str", record["media_type"]),
                    body,
                    endpoint.url,
                ),
                terminal_code=cast("str", record["terminal_code"]),
            )
        )
        if record["terminal_code"] == "CAPTURED":
            static_bodies[endpoint.endpoint_id] = body
    if plan_state == "STATIC_CAPTURE_INCOMPLETE":
        if len(records) > len(endpoints) or attempts:
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        plan: HKEXTraversalPlan | None = None
    else:
        if static_count != len(endpoints) or any(
            item.terminal_code != "CAPTURED" for item in captures
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        try:
            initial_plan = build_hkex_traversal_plan(static_bodies, endpoints)
        except _HKEXPlanPolicyLimitError:
            if plan_state != "ROOT_POLICY_LIMIT_EXCEEDED":
                _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
            plan = None
        except ValueError:
            if plan_state != "ROOT_CONTRACT_CHANGED":
                _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
            plan = None
        else:
            if plan_state == "ROOT_CONTRACT_CHANGED" and historical_root_contract_changed:
                plan = None
            elif plan_state in {"ROOT_CONTRACT_CHANGED", "ROOT_POLICY_LIMIT_EXCEEDED"}:
                _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
            else:
                plan = initial_plan
    if plan is not None:
        form_records = records[len(endpoints) :]
        expected_requests = plan.form_html_requests[: len(form_records)]
        if len(form_records) != len(attempts):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        attempt_by_sequence = {item.sequence: item for item in attempts}
        board_by_capture = {
            association.capture_endpoint_id: association.board
            for association in plan.associations
            if association.relation is HKEXMembershipRelation.FORM_NODE
        }
        capture_id_by_url = {endpoint.url: endpoint.endpoint_id for endpoint in endpoints}
        identities: list[HKEXPageIdentity] = []
        parse_failed = False
        for record, body, request in zip(
            form_records,
            bodies[len(endpoints) :],
            expected_requests,
            strict=True,
        ):
            attempt = attempt_by_sequence.get(request.sequence)
            if (
                attempt is None
                or record["endpoint_id"] != request.capture_endpoint_id
                or record["endpoint_version"] != request.endpoint_version
                or record["requested_url"] != request.requested_url
                or record["media_type"] != request.media_type
            ):
                _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
            capture = HKEXCapturedEndpoint(
                sequence=request.sequence,
                capture_endpoint_id=request.capture_endpoint_id,
                endpoint_version=request.endpoint_version,
                stage="FORM_HTML_TIER",
                requested_url=request.requested_url,
                max_bytes=request.max_bytes,
                response=CapturedResponse(
                    cast("int", record["status"]),
                    cast("str", record["media_type"]),
                    body,
                    attempt.final_url,
                ),
                terminal_code=cast("str", record["terminal_code"]),
            )
            captures.append(capture)
            if attempt.semantic_terminal_code != "CAPTURED":
                if capture.terminal_code != attempt.semantic_terminal_code:
                    _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
                continue
            try:
                identity, _associations = derive_hkex_form_member(
                    request=request,
                    attempt=attempt,
                    response=capture.response,
                    board=board_by_capture[request.capture_endpoint_id],
                    capture_id_by_url=capture_id_by_url,
                )
            except KeyError, ValueError:
                if capture.terminal_code != "SOURCE_CONTRACT_CHANGED":
                    _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
                parse_failed = True
            else:
                if capture.terminal_code != "CAPTURED":
                    _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
                identities.append(identity)
        if plan_state == "FORM_MEMBER_CONTRACT_CHANGED" and not parse_failed:
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        if plan_state == "FORM_HTML_TIER_INCOMPLETE" and parse_failed:
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    else:
        identities = []
        if (
            attempts
            or (plan_state == "STATIC_CAPTURE_INCOMPLETE" and len(records) > len(endpoints))
            or (plan_state != "STATIC_CAPTURE_INCOMPLETE" and len(records) != len(endpoints))
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    _hkex_validate_partial_start_topology(
        starts=starts,
        captures=tuple(captures),
        attempts=attempts,
    )
    accounting = _hkex_exact_dict(
        document["hkex_traversal_accounting"],
        frozenset(
            _hkex_role_aware_accounting(
                HKEXRoleAwareCapture(
                    plan_state,
                    plan,
                    (),
                    (),
                    (),
                    (),
                    0,
                    0,
                    0,
                    0,
                    0.0,
                    0.0,
                    None,
                )
            )
        ),
    )
    replay_capture = HKEXRoleAwareCapture(
        plan_state=plan_state,
        plan=plan,
        captures=tuple(captures),
        dynamic_html_attempts=attempts,
        physical_starts=starts,
        page_identities=tuple(identities),
        followed_redirect_starts=sum(item.hop_number == 1 for item in starts),
        redirect_event_count=sum(len(item.redirect_events) for item in attempts),
        retained_response_bytes=sum(len(item.response.body) for item in captures),
        pacing_sleep_count=_hkex_exact_int(accounting["pacing_sleep_count"]),
        pacing_sleep_seconds=_hkex_exact_float(accounting["pacing_sleep_seconds"]),
        elapsed_seconds=starts[-1].start_elapsed_seconds if starts else 0.0,
        stop_code=_hkex_optional_str(accounting["stop_code"]),
    )
    require_hkex_role_aware_report_fields(
        {key: document[key] for key in hkex_role_aware_report_fields(replay_capture)},
        replay_capture,
    )
    procedures = hkex_role_aware_procedures(replay_capture)
    counts: dict[str, int] = {}
    for item in captures:
        counts[item.terminal_code] = counts.get(item.terminal_code, 0) + 1
    if (
        document["endpoint_counts"] != dict(sorted(counts.items()))
        or document["source_procedures"] != procedures
        or document["result"] != hkex_role_aware_result(replay_capture, procedures)
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    return dict(document)


def _exact_historical_hkex_root_contract_changed(
    document: dict[str, object],
    *,
    endpoints: tuple[OfficialEndpointContract, ...],
) -> bool:
    """Derive the one legacy parser exception only from its complete replay pin."""
    attempt_id = document.get("attempt_id")
    if type(attempt_id) is not str:
        return False
    try:
        pin = historical_hkex_replay_pin(attempt_id)
    except KeyError:
        return False
    return bool(
        pin.legacy_root_contract_changed
        and endpoints == pin.endpoints
        and hashlib.sha256(_canonical(document)).hexdigest() == pin.report_sha256
        and document.get("observation_cutoff") == pin.observation_cutoff
        and document.get("authority_manifest_fingerprint") == pin.authority_fingerprint
        and document.get("execution_authorization_fingerprint")
        == pin.execution_authorization_fingerprint
        and document.get("execution_policy_fingerprint") == pin.execution_policy_fingerprint
        and document.get("result") == pin.expected_result
    )


def replay_hkex_role_aware_report(  # noqa: C901, PLR0912, PLR0915
    report: object,
    *,
    output_root: Path,
    endpoints: tuple[OfficialEndpointContract, ...],
) -> dict[str, object]:
    """Reread and semantically rederive one current schema-2 HKEX report."""
    document = _hkex_exact_dict(report, _HKEX_ROLE_AWARE_REPORT_KEYS)
    if (
        document.get("report_schema_version") != "2.0.0"
        or document.get("source_family") != "HKEX"
        or document.get("hkex_plan_state") not in _HKEX_PLAN_STATES
        or document.get("authority_provenance") != _AUTHORITY
        or document.get("readback_verified") is not True
        or _FINGERPRINT.fullmatch(cast("str", document.get("authority_manifest_fingerprint")))
        is None
        or _FINGERPRINT.fullmatch(cast("str", document.get("execution_authorization_fingerprint")))
        is None
        or document.get("execution_policy") != hkex_execution_policy()
        or document.get("execution_policy_fingerprint") != hkex_execution_policy_fingerprint()
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    records, bodies = _hkex_read_role_aware_records(document, output_root=output_root)
    if document["hkex_plan_state"] != "COMPLETE_PLAN":
        return _replay_hkex_role_aware_partial_report(
            document,
            records=records,
            bodies=bodies,
            endpoints=endpoints,
            historical_root_contract_changed=_exact_historical_hkex_root_contract_changed(
                document,
                endpoints=endpoints,
            ),
        )
    if len(records) < len(endpoints):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    static_bodies: dict[str, bytes] = {}
    for index, endpoint in enumerate(endpoints):
        record = records[index]
        if (
            record["endpoint_id"] != endpoint.endpoint_id
            or record["endpoint_version"] != endpoint.version
            or record["requested_url"] != endpoint.url
            or record["media_type"] not in endpoint.media_types
            or record["terminal_code"] != "CAPTURED"
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        if (
            _hkex_replayed_response_terminal(
                record,
                bodies[index],
                requested_url=endpoint.url,
                final_url=endpoint.url,
                max_bytes=endpoint.max_bytes,
                expected_media_type=endpoint.media_types[0],
            )
            != "CAPTURED"
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        static_bodies[endpoint.endpoint_id] = bodies[index]
    try:
        initial_plan = build_hkex_traversal_plan(static_bodies, endpoints)
    except ValueError as error:
        raise ValueError(_HKEX_ROLE_AWARE_REPORT_INVALID) from error
    raw_attempts = document["hkex_dynamic_html_attempts"]
    raw_starts = document["hkex_physical_starts"]
    if type(raw_attempts) is not list or type(raw_starts) is not list:
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    attempts = tuple(
        _hkex_parse_dynamic_attempt(item) for item in cast("list[object]", raw_attempts)
    )
    starts = tuple(_hkex_parse_physical_start(item) for item in cast("list[object]", raw_starts))
    attempt_by_sequence = {item.sequence: item for item in attempts}
    form_bodies: dict[str, bytes] = {}
    form_final_urls: dict[str, str] = {}
    for offset, request in enumerate(initial_plan.form_html_requests, start=len(endpoints)):
        record = records[offset]
        attempt = attempt_by_sequence.get(request.sequence)
        if (
            attempt is None
            or record["endpoint_id"] != request.capture_endpoint_id
            or record["endpoint_version"] != request.endpoint_version
            or record["requested_url"] != request.requested_url
            or record["media_type"] != request.media_type
            or record["terminal_code"] != attempt.semantic_terminal_code
            or attempt.final_url is None
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        physical_terminal = _hkex_replayed_response_terminal(
            record,
            bodies[offset],
            requested_url=attempt.final_url,
            final_url=attempt.final_url,
            max_bytes=request.max_bytes,
            expected_media_type=request.media_type,
        )
        semantic_terminal = (
            "SOURCE_CONTRACT_CHANGED" if attempt.redirect_rejected else physical_terminal
        )
        if (
            attempt.physical_terminal_code != physical_terminal
            or attempt.semantic_terminal_code != semantic_terminal
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        form_bodies[request.requested_url] = bodies[offset]
        form_final_urls[request.requested_url] = attempt.final_url
    try:
        plan = finalize_hkex_traversal_plan(
            initial_plan,
            form_bodies=form_bodies,
            form_final_urls=form_final_urls,
            endpoints=endpoints,
        )
    except ValueError as error:
        raise ValueError(_HKEX_ROLE_AWARE_REPORT_INVALID) from error
    expected_requests = (*plan.form_html_requests, *plan.pdf_requests)
    attempted_dynamic_count = len(records) - len(endpoints)
    if not len(plan.form_html_requests) <= attempted_dynamic_count <= len(expected_requests):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    attempted_requests = expected_requests[:attempted_dynamic_count]
    captures: list[HKEXCapturedEndpoint] = []
    for sequence, (endpoint, record, body) in enumerate(
        zip(endpoints, records[: len(endpoints)], bodies[: len(endpoints)], strict=True), start=1
    ):
        captures.append(
            HKEXCapturedEndpoint(
                sequence=sequence,
                capture_endpoint_id=endpoint.endpoint_id,
                endpoint_version=endpoint.version,
                stage="STATIC",
                requested_url=endpoint.url,
                max_bytes=endpoint.max_bytes,
                response=CapturedResponse(
                    cast("int", record["status"]),
                    cast("str", record["media_type"]),
                    body,
                    endpoint.url,
                ),
                terminal_code=cast("str", record["terminal_code"]),
            )
        )
    for offset, request in enumerate(attempted_requests, start=len(endpoints)):
        record = records[offset]
        body = bodies[offset]
        if (
            record["endpoint_id"] != request.capture_endpoint_id
            or record["endpoint_version"] != request.endpoint_version
            or record["requested_url"] != request.requested_url
            or record["media_type"] != request.media_type
        ):
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        attempt = attempt_by_sequence.get(request.sequence)
        final_url = attempt.final_url if attempt is not None else request.requested_url
        expected_terminal = (
            attempt.semantic_terminal_code
            if attempt is not None
            else _hkex_replayed_response_terminal(
                record,
                body,
                requested_url=request.requested_url,
                final_url=request.requested_url,
                max_bytes=request.max_bytes,
                expected_media_type=request.media_type,
            )
        )
        if record["terminal_code"] != expected_terminal:
            _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
        captures.append(
            HKEXCapturedEndpoint(
                sequence=request.sequence,
                capture_endpoint_id=request.capture_endpoint_id,
                endpoint_version=request.endpoint_version,
                stage=(
                    "FORM_HTML_TIER"
                    if request.relation is HKEXMembershipRelation.FORM_NODE
                    else "PDF_TIER"
                ),
                requested_url=request.requested_url,
                max_bytes=request.max_bytes,
                response=CapturedResponse(
                    cast("int", record["status"]),
                    cast("str", record["media_type"]),
                    body,
                    final_url,
                ),
                terminal_code=cast("str", record["terminal_code"]),
            )
        )
    _hkex_validate_start_topology(starts=starts, attempts=attempts, endpoints=endpoints, plan=plan)
    board_by_capture = {
        association.capture_endpoint_id: association.board
        for association in initial_plan.associations
        if association.relation is HKEXMembershipRelation.FORM_NODE
    }
    capture_id_by_url = {endpoint.url: endpoint.endpoint_id for endpoint in endpoints}
    identities: list[HKEXPageIdentity] = []
    for request in plan.form_html_requests:
        item = captures[request.sequence - 1]
        identity, _associations = derive_hkex_form_member(
            request=request,
            attempt=attempt_by_sequence[request.sequence],
            response=item.response,
            board=board_by_capture[request.capture_endpoint_id],
            capture_id_by_url=capture_id_by_url,
        )
        identities.append(identity)
    accounting = _hkex_exact_dict(
        document["hkex_traversal_accounting"],
        frozenset(
            _hkex_role_aware_accounting(
                HKEXRoleAwareCapture(
                    "COMPLETE_PLAN", plan, (), (), (), (), 0, 0, 0, 0, 0.0, 0.0, None
                )
            )
        ),
    )
    replay_capture = HKEXRoleAwareCapture(
        plan_state="COMPLETE_PLAN",
        plan=plan,
        captures=tuple(captures),
        dynamic_html_attempts=attempts,
        physical_starts=starts,
        page_identities=tuple(identities),
        followed_redirect_starts=sum(item.hop_number == 1 for item in starts),
        redirect_event_count=sum(len(item.redirect_events) for item in attempts),
        retained_response_bytes=sum(len(item.response.body) for item in captures),
        pacing_sleep_count=_hkex_exact_int(accounting["pacing_sleep_count"]),
        pacing_sleep_seconds=_hkex_exact_float(accounting["pacing_sleep_seconds"]),
        elapsed_seconds=starts[-1].start_elapsed_seconds if starts else 0.0,
        stop_code=_hkex_optional_str(accounting["stop_code"]),
    )
    require_hkex_role_aware_report_fields(
        {key: document[key] for key in hkex_role_aware_report_fields(replay_capture)},
        replay_capture,
    )
    procedures = hkex_role_aware_procedures(replay_capture)
    counts: dict[str, int] = {}
    for item in captures:
        counts[item.terminal_code] = counts.get(item.terminal_code, 0) + 1
    if (
        document["endpoint_counts"] != dict(sorted(counts.items()))
        or document["source_procedures"] != procedures
        or document["result"] != hkex_role_aware_result(replay_capture, procedures)
    ):
        _fail(_HKEX_ROLE_AWARE_REPORT_INVALID)
    return dict(document)


class _JudiciaryObservationError(Exception):
    """Internal signal for a non-finite or non-monotonic injected clock."""


@dataclass(slots=True)
class _JudiciaryObservationController:
    """One fail-visible, source-local controller for all Judiciary request starts."""

    clock: Callable[[], float]
    sleeper: Callable[[float], None]
    started_at: float | None = None
    last_start: float | None = None
    request_starts: int = 0
    retained_response_bytes: int = 0
    rejected_response_bytes: int = 0
    elapsed_seconds: float = 0.0
    stop_code: str | None = None
    cumulative_request_starts_before_segment: int = 0
    cumulative_retained_bytes_before_segment: int = 0
    cumulative_elapsed_seconds_before_segment: float = 0.0

    def _clock_now(self) -> float:
        """Read one finite monotonic instant or fail the local controller closed."""
        now = self.clock()
        if type(now) not in {int, float} or not math.isfinite(now):
            raise _JudiciaryObservationError
        return now

    def before_request(self) -> bool:  # noqa: C901
        """Wait and check every ceiling before a new external request starts."""
        try:
            now = self._clock_now()
            if self.started_at is None:
                self.started_at = now
            elif now < self.started_at:
                raise _JudiciaryObservationError  # noqa: TRY301
            self.elapsed_seconds = now - self.started_at
            if (
                self.cumulative_elapsed_seconds_before_segment + self.elapsed_seconds
                >= _JUDICIARY_ELAPSED_SECONDS_LIMIT
            ):
                self.stop_code = "ELAPSED_TIME_BUDGET_EXHAUSTED"
                return False
            if (
                self.cumulative_request_starts_before_segment + self.request_starts
                >= _JUDICIARY_REQUEST_START_LIMIT
            ):
                self.stop_code = "REQUEST_BUDGET_EXHAUSTED"
                return False
            if self.last_start is not None:
                remaining = _JUDICIARY_MINIMUM_START_INTERVAL_SECONDS - (now - self.last_start)
                if remaining > 0:
                    self.sleeper(remaining)
                    now = self._clock_now()
                    if (
                        type(now) not in {int, float}
                        or not math.isfinite(now)
                        or now < self.last_start
                        or now - self.last_start < _JUDICIARY_MINIMUM_START_INTERVAL_SECONDS
                    ):
                        raise _JudiciaryObservationError  # noqa: TRY301
                    self.elapsed_seconds = now - self.started_at
                    if (
                        self.cumulative_elapsed_seconds_before_segment + self.elapsed_seconds
                        >= _JUDICIARY_ELAPSED_SECONDS_LIMIT
                    ):
                        self.stop_code = "ELAPSED_TIME_BUDGET_EXHAUSTED"
                        return False
        except Exception:  # noqa: BLE001 - BaseException is deliberately visible to the operator.
            self.stop_code = "OBSERVATION_EXECUTION_FAILURE"
            return False
        else:
            self.request_starts += 1
            self.last_start = now
            return True

    def accept_response(self, body: bytes) -> bool:
        """Refuse the crossing body before the immutable writer can retain it."""
        if (
            self.cumulative_retained_bytes_before_segment + self.retained_response_bytes + len(body)
            > _JUDICIARY_RETAINED_BYTE_LIMIT
        ):
            self.rejected_response_bytes = len(body)
            self.stop_code = "BYTE_BUDGET_EXHAUSTED"
            return False
        self.retained_response_bytes += len(body)
        return True

    def report_stop(self) -> dict[str, object]:
        """Return only sanitized accounting facts for a terminal bounded attempt."""
        if self.stop_code is None:
            _fail("CAPTURE_ACCOUNTING_INVALID")
        profile = _judiciary_observation_profile()
        return {
            "code": self.stop_code,
            "profile": profile,
            "profile_fingerprint": _digest(_canonical(profile)),
            "request_starts": self.request_starts,
            "rejected_response_bytes": self.rejected_response_bytes,
            "retained_response_bytes": self.retained_response_bytes,
            "elapsed_seconds": self.elapsed_seconds,
        }

    def report_accounting(self) -> dict[str, object]:
        """Return complete accounting even when a bounded observation did not stop."""
        profile = _judiciary_observation_profile()
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "profile": profile,
            "profile_fingerprint": _digest(_canonical(profile)),
            "rejected_response_bytes": self.rejected_response_bytes,
            "request_starts": self.request_starts,
            "retained_response_bytes": self.retained_response_bytes,
            "stop_code": self.stop_code,
        }

    def report_cumulative_accounting(self) -> dict[str, object]:
        """Return budget accounting across the predecessor and this network segment."""
        accounting = self.report_accounting()
        accounting["elapsed_seconds"] = (
            self.cumulative_elapsed_seconds_before_segment + self.elapsed_seconds
        )
        accounting["request_starts"] = (
            self.cumulative_request_starts_before_segment + self.request_starts
        )
        accounting["retained_response_bytes"] = (
            self.cumulative_retained_bytes_before_segment + self.retained_response_bytes
        )
        return accounting


class _ConfiningRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse an unregistered redirect before urllib can issue its follow-up request."""

    def __init__(self, allowed_urls: frozenset[str]) -> None:
        super().__init__()
        self._allowed_urls = allowed_urls
        self._allowed_transitions = _redirect_transitions(allowed_urls)

    def redirect_request(  # noqa: PLR0913, PLR0917 - stdlib override signature.
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        target, _fragment = urldefrag(newurl)
        parsed = urlsplit(target)
        source = urlsplit(req.full_url)
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or target not in self._allowed_urls
            or (source.scheme.lower(), source.hostname, source.port or 443)
            != (parsed.scheme.lower(), parsed.hostname, parsed.port or 443)
        ):
            raise urllib.error.HTTPError(req.full_url, code, "REDIRECT_NOT_ADMITTED", headers, fp)
        redirected = super().redirect_request(req, fp, code, msg, headers, target)
        transition = (
            req.get_method(),
            urldefrag(req.full_url)[0],
            redirected.get_method() if redirected is not None else "",
            target,
        )
        if transition not in self._allowed_transitions:
            raise urllib.error.HTTPError(req.full_url, code, "REDIRECT_NOT_ADMITTED", headers, fp)
        return redirected


def _hkel_redirect_transitions(allowed_urls: frozenset[str]) -> frozenset[_RedirectTransition]:
    """Admit only the observed GET terms-to-config hop; the POST is always explicit."""
    transition = ("GET", _HKEL_TERMS_URL, "GET", _HKEL_CONFIGURATION_GET)
    if _HKEL_CLIENT_CHECK_URL not in allowed_urls and {
        _HKEL_TERMS_URL,
        _HKEL_CONFIGURATION_GET,
    }.issubset(allowed_urls):
        return frozenset({transition})
    return frozenset()


def _redirect_transitions(allowed_urls: frozenset[str]) -> frozenset[_RedirectTransition]:
    """Return the only two registered session transitions for all source families."""
    transitions = set(_hkel_redirect_transitions(allowed_urls))
    if {
        _JUDICIARY_CURRENT_LISTING_ENTRY_URL,
        _JUDICIARY_CURRENT_LISTING_TARGET_URL,
    }.issubset(allowed_urls):
        transitions.add(
            (
                "GET",
                _JUDICIARY_CURRENT_LISTING_ENTRY_URL,
                "GET",
                _JUDICIARY_CURRENT_LISTING_TARGET_URL,
            )
        )
    return frozenset(transitions)


def _validated_hkel_client_check_url() -> str:
    """Return the registered direct gate only while the shared claim matches its snapshot."""
    if (
        type(CAPABILITY_CLAIM) is not dict
        or tuple(CAPABILITY_CLAIM.items()) != _HKEL_CAPABILITY_CLAIM_SNAPSHOT
        or not _HKEL_CAPABILITY_CLAIM_SNAPSHOT
        or any(
            type(key) is not str or not key or type(value) is not str or not value
            for key, value in _HKEL_CAPABILITY_CLAIM_SNAPSHOT
        )
    ):
        _fail("HKEL_CAPABILITY_CLAIM_INVALID")
    return _HKEL_CLIENT_CHECK_URL


_HKEX_TLS_HOST = "en-rules.hkex.com.hk"
_HKEX_TLS_INTERMEDIATE_PATH = Path(__file__).with_name("hkex-sectigo-r36.pem")
_HKEX_TLS_INTERMEDIATE_LENGTH = 2244
_HKEX_TLS_INTERMEDIATE_SHA256 = "505ca50c3930cedca888c4e1ebb0747cb485498547b60ea6bcd23cf78766aeeb"
_HKEX_TLS_INTERMEDIATE_INVALID = "HKEX_TLS_INTERMEDIATE_INVALID"


def _uses_hkex_tls_intermediate(allowed_urls: frozenset[str]) -> bool:
    """Return whether an exact registered locator uses HKEX HTTPS on port 443."""
    for url in allowed_urls:
        if any(character.isspace() or not character.isprintable() for character in url):
            continue
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if (
            parsed.scheme == "https"
            and parsed.hostname == _HKEX_TLS_HOST
            and parsed.netloc in {_HKEX_TLS_HOST, f"{_HKEX_TLS_HOST}:443"}
        ):
            return True
    return False


def _read_hkex_tls_intermediate() -> str:
    """Read only the exact regular, non-symlinked repository trust resource."""
    descriptor: int | None = None
    try:
        descriptor = os.open(
            _HKEX_TLS_INTERMEDIATE_PATH,
            os.O_RDONLY | os.O_NOFOLLOW,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            _fail(_HKEX_TLS_INTERMEDIATE_INVALID)
        stream = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = None
        with stream:
            data = stream.read(_HKEX_TLS_INTERMEDIATE_LENGTH + 1)
    except OSError:
        _fail(_HKEX_TLS_INTERMEDIATE_INVALID)
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
    if (
        len(data) != _HKEX_TLS_INTERMEDIATE_LENGTH
        or hashlib.sha256(data).hexdigest() != _HKEX_TLS_INTERMEDIATE_SHA256
    ):
        _fail(_HKEX_TLS_INTERMEDIATE_INVALID)
    try:
        return data.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        _fail(_HKEX_TLS_INTERMEDIATE_INVALID)


class UrllibReadOnlyTransport:
    """Credential-free GET transport for exact registered public URLs."""

    def __init__(self, *, allowed_redirect_urls: frozenset[str] = frozenset()) -> None:
        """Create one bounded in-memory cookie jar for approved publisher sessions."""
        self._redirect_capability = RedirectCapability(
            allowed_redirect_urls,
            _redirect_transitions(allowed_redirect_urls),
        )
        self._cookie_jar = http.cookiejar.CookieJar()
        handlers: list[urllib.request.BaseHandler] = [
            _ConfiningRedirectHandler(allowed_redirect_urls),
            urllib.request.HTTPCookieProcessor(self._cookie_jar),
        ]
        if _uses_hkex_tls_intermediate(allowed_redirect_urls):
            cadata = _read_hkex_tls_intermediate()
            context = ssl.create_default_context()
            context.load_verify_locations(cadata=cadata)
            handlers.append(urllib.request.HTTPSHandler(context=context))
        self._opener: urllib.request.OpenerDirector | None = urllib.request.build_opener(
            *handlers,
        )

    @property
    def redirect_capability(self) -> RedirectCapability:
        """Return the immutable redirect policy bound when this transport was composed."""
        return self._redirect_capability

    def get(self, *, url: str, max_bytes: int) -> CapturedResponse:
        """Perform one credential-free bounded GET against an HTTPS locator."""
        opener = self._opener
        if opener is None:
            _fail("SOURCE_TRANSPORT_CLOSED")
        if urlsplit(url).scheme != "https":
            _fail("SOURCE_URL_SCHEME_FORBIDDEN")
        request = urllib.request.Request(  # noqa: S310 - scheme validated immediately above.
            url,
            method="GET",
            headers={"User-Agent": "AskLegal-V1-Source-Admission/1.0"},
        )
        try:
            with opener.open(request, timeout=30) as response:
                media_type = response.headers.get_content_type()
                return CapturedResponse(
                    status=int(response.status),
                    media_type=media_type,
                    body=response.read(max_bytes + 1),
                    final_url=cast("str", response.url),
                )
        except urllib.error.HTTPError as error:
            locations = error.headers.get_all("Location")
            location = (
                locations[0]
                if type(locations) is list and len(locations) == 1 and type(locations[0]) is str
                else None
            )
            raw_location = (
                location.encode("latin-1", errors="strict") if type(location) is str else None
            )

            def raw_location_reader(limit: int) -> tuple[bytes, bool]:
                if type(limit) is not int or limit < 0 or raw_location is None:
                    _fail("HKEX_RAW_LOCATION_REPRESENTATION_INVALID")
                return raw_location[:limit], len(raw_location) <= limit

            return CapturedResponse(
                status=error.code,
                media_type=error.headers.get_content_type(),
                body=error.read(max_bytes + 1),
                final_url=error.url,
                redirect_rejected=error.msg == "REDIRECT_NOT_ADMITTED",
                raw_location_reader=(raw_location_reader if raw_location is not None else None),
            )

    def _configure_hkel_direct_session(self, *, url: str, max_bytes: int) -> HkelSessionCapture:
        """Call the exact direct capability gate and return only sanitized stage facts."""
        client_check_url = _validated_hkel_client_check_url()
        if url != client_check_url:
            _fail("HKEL_CAPABILITY_CHECK_URL_INVALID")
        try:
            response = self.get(url=url, max_bytes=max_bytes)
        except OSError, TimeoutError, urllib.error.URLError:
            response = CapturedResponse(0, "application/octet-stream", b"", None)
        capability_stage = _hkel_response_stage(
            "CAPABILITY_GET", response=response, max_bytes=max_bytes
        )
        if capability_stage.terminal_code == "CAPTURED" and response.final_url != client_check_url:
            capability_stage = HkelSessionStage(
                "CAPABILITY_GET",
                "SOURCE_CONTRACT_CHANGED",
                response.status,
                response.media_type,
                response.final_url,
                len(response.body),
                response.redirect_rejected,
            )
        return HkelSessionCapture(
            _hkel_not_attempted_stage("CONFIG_GET"),
            _hkel_not_attempted_stage("CONFIG_PARSE"),
            _hkel_not_attempted_stage("CONFIG_POST"),
            capability_stage,
        )

    def configure_hkel_session(self, *, url: str, max_bytes: int) -> HkelSessionCapture:
        """Establish the HKeL browser session through its exact registered procedure."""
        if url != _HKEL_TERMS_URL:
            return self._configure_hkel_direct_session(url=url, max_bytes=max_bytes)

        # Kept solely for replay-compatible execution under a previously bound
        # authority manifest. New authority manifests select the direct client check.
        try:
            initial = self.get(url=url, max_bytes=max_bytes)
        except OSError, TimeoutError, urllib.error.URLError:
            initial = CapturedResponse(0, "application/octet-stream", b"", None)
        initial_stage = _hkel_response_stage("CONFIG_GET", response=initial, max_bytes=max_bytes)
        if (
            initial_stage.terminal_code == "CAPTURED"
            and initial.final_url != _HKEL_CONFIGURATION_GET
        ):
            initial_stage = HkelSessionStage(
                "CONFIG_GET",
                "SOURCE_CONTRACT_CHANGED",
                initial.status,
                initial.media_type,
                initial.final_url,
                len(initial.body),
            )
        if initial_stage.terminal_code != "CAPTURED":
            return HkelSessionCapture(
                initial_stage,
                _hkel_not_attempted_stage("CONFIG_PARSE"),
                _hkel_not_attempted_stage("CONFIG_POST"),
            )
        try:
            form = parse_hkel_client_configuration_form(
                initial.body, page_url=_HKEL_CONFIGURATION_GET
            )
        except TypeError, ValueError:
            return HkelSessionCapture(
                initial_stage,
                HkelSessionStage(
                    "CONFIG_PARSE",
                    "SOURCE_CONTRACT_CHANGED",
                    initial.status,
                    initial.media_type,
                    initial.final_url,
                    len(initial.body),
                ),
                _hkel_not_attempted_stage("CONFIG_POST"),
            )
        if form.action_url != _HKEL_CONFIGURATION_ACTION:
            return HkelSessionCapture(
                initial_stage,
                HkelSessionStage(
                    "CONFIG_PARSE",
                    "SOURCE_CONTRACT_CHANGED",
                    initial.status,
                    initial.media_type,
                    initial.final_url,
                    len(initial.body),
                    configuration_field_count=len(form.field_names),
                    anti_forgery_control_present=True,
                ),
                _hkel_not_attempted_stage("CONFIG_POST"),
            )
        parser_stage = HkelSessionStage(
            "CONFIG_PARSE",
            "CAPTURED",
            initial.status,
            initial.media_type,
            initial.final_url,
            len(initial.body),
            configuration_action=form.action_url,
            configuration_field_count=len(form.field_names),
            anti_forgery_control_present=True,
        )
        fields = dict(form.post_fields())
        fields.update(
            {
                "javascriptEnabled": "true",
                "cookieEnabled": "true",
                "appletLoadFailed": "false",
            }
        )
        request = urllib.request.Request(  # noqa: S310 - exact HTTPS publisher host above.
            form.action_url,
            data=urlencode(fields).encode("ascii"),
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "AskLegal-V1-Source-Admission/1.0",
            },
        )
        opener = self._opener
        if opener is None:
            _fail("SOURCE_TRANSPORT_CLOSED")
        try:
            with opener.open(request, timeout=30) as response:
                submission = CapturedResponse(
                    int(response.status),
                    response.headers.get_content_type(),
                    response.read(max_bytes + 1),
                    cast("str", response.url),
                )
        except urllib.error.HTTPError as error:
            submission = CapturedResponse(
                error.code,
                error.headers.get_content_type(),
                error.read(max_bytes + 1),
                error.url,
                error.msg == "REDIRECT_NOT_ADMITTED",
            )
        except OSError, TimeoutError, urllib.error.URLError:
            submission = CapturedResponse(0, "application/octet-stream", b"", None)
        return HkelSessionCapture(
            initial_stage,
            parser_stage,
            _hkel_response_stage("CONFIG_POST", response=submission, max_bytes=max_bytes),
        )

    def close(self) -> None:
        """Release the opener and all session cookies after one terminal invocation."""
        opener = self._opener
        self._opener = None
        if opener is not None:
            close = getattr(opener, "close", None)
            if callable(close):
                close()
        self._cookie_jar.clear()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest_file(path: Path) -> tuple[str, int]:
    """Hash one retained object incrementally so readback never duplicates a large body."""
    digest = hashlib.sha256()
    byte_length = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            digest.update(chunk)
            byte_length += len(chunk)
    return "sha256:" + digest.hexdigest(), byte_length


def _response_terminal(response: CapturedResponse, *, max_bytes: int) -> str:
    """Classify a bounded response without inspecting or retaining its content."""
    if response.redirect_rejected:
        return "SOURCE_CONTRACT_CHANGED"
    if len(response.body) > max_bytes:
        return "TRUNCATED"
    if not _HTTP_SUCCESS_MIN <= response.status < _HTTP_SUCCESS_MAX:
        return "OUTAGE"
    if not response.body:
        return "EMPTY_RESPONSE"
    return "CAPTURED"


def _physical_response_terminal(
    response: CapturedResponse, *, requested_url: str, max_bytes: int
) -> str:
    """Derive one physical terminal before retry eligibility is considered."""
    if response.redirect_rejected:
        return "SOURCE_CONTRACT_CHANGED"
    if len(response.body) > max_bytes:
        return "TRUNCATED"
    if maintenance_outage(
        status=response.status,
        body=response.body,
        media_type=response.media_type,
        final_url=response.final_url,
        redirect_rejected=response.redirect_rejected,
        requested_url=requested_url,
    ):
        return "OUTAGE"
    terminal = _response_terminal(response, max_bytes=max_bytes)
    if response.final_url is not None and (
        urlsplit(response.final_url).hostname != urlsplit(requested_url).hostname
    ):
        return "SOURCE_CONTRACT_CHANGED"
    return terminal


def _hkel_response_stage(
    stage_id: str, *, response: CapturedResponse, max_bytes: int
) -> HkelSessionStage:
    """Discard session-bearing content while preserving its closed terminal facts."""
    return HkelSessionStage(
        stage_id,
        _response_terminal(response, max_bytes=max_bytes),
        response.status,
        response.media_type,
        response.final_url,
        len(response.body),
        response.redirect_rejected,
    )


def _hkel_not_attempted_stage(stage_id: str) -> HkelSessionStage:
    """Return an explicit safe fact for a stage blocked by its predecessor."""
    return HkelSessionStage(
        stage_id, "NOT_ATTEMPTED", 0, "application/octet-stream", None, 0, attempted=False
    )


def _hkel_transport_outage_capture(*, direct: bool) -> HkelSessionCapture:
    """Return the exact sanitized mandatory terminal for a bounded transport failure."""
    if direct:
        return HkelSessionCapture(
            _hkel_not_attempted_stage("CONFIG_GET"),
            _hkel_not_attempted_stage("CONFIG_PARSE"),
            _hkel_not_attempted_stage("CONFIG_POST"),
            HkelSessionStage(
                "CAPABILITY_GET",
                "OUTAGE",
                0,
                "application/octet-stream",
                None,
                0,
            ),
        )
    return HkelSessionCapture(
        HkelSessionStage(
            "CONFIG_GET",
            "OUTAGE",
            0,
            "application/octet-stream",
            None,
            0,
        ),
        _hkel_not_attempted_stage("CONFIG_PARSE"),
        _hkel_not_attempted_stage("CONFIG_POST"),
    )


def _hkel_stage_documents(
    stage: HkelSessionStage,
    *,
    derived_terminal: str,
    effective_terminal: str,
    assertion_consistent: bool,
) -> tuple[bytes, bytes]:
    """Return retained evidence and the secret-insensitive comparison projection."""
    stable: dict[str, object] = {
        "anti_forgery_control_present": stage.anti_forgery_control_present,
        "attempted": stage.attempted,
        "configuration_action": stage.configuration_action,
        "configuration_field_count": stage.configuration_field_count,
        "derived_terminal_code": derived_terminal,
        "final_url": (
            _HKEL_CLIENT_CHECK_COORDINATE if stage.stage_id == "CAPABILITY_GET" else stage.final_url
        ),
        "media_type": stage.media_type,
        "redirect_rejected": stage.redirect_rejected,
        "stage_id": stage.stage_id,
        "status": stage.status,
        "terminal_assertion_consistent": assertion_consistent,
        "terminal_code": effective_terminal,
    }
    if stage.stage_id == "CAPABILITY_GET":
        stable["endpoint_contract_fingerprint"] = _HKEL_CLIENT_CHECK_CONTRACT_FINGERPRINT
    comparison = _canonical(stable)
    return _canonical({"observed_byte_length": stage.byte_length, "stable": stable}), comparison


def _validate_hkel_stage(  # noqa: C901 - closed stage fact/terminal derivation matrix.
    stage: object,
    *,
    expected_stage_id: str,
    expected_final_url: str,
    max_bytes: int,
) -> tuple[HkelSessionStage, str, str, bool]:
    """Derive one stage terminal and fail closed on an incompatible assertion."""
    if type(stage) is not HkelSessionStage:
        _evidence_integrity_fail()
    typed = stage
    if (
        typed.stage_id != expected_stage_id
        or type(typed.terminal_code) is not str
        or type(typed.status) is not int
        or typed.status < 0
        or type(typed.media_type) is not str
        or not typed.media_type
        or (typed.final_url is not None and type(typed.final_url) is not str)
        or type(typed.byte_length) is not int
        or typed.byte_length < 0
        or type(typed.redirect_rejected) is not bool
        or type(typed.attempted) is not bool
        or typed.configuration_action not in {None, _HKEL_CONFIGURATION_ACTION}
        or (
            typed.configuration_field_count is not None
            and (
                type(typed.configuration_field_count) is not int
                or typed.configuration_field_count < 0
            )
        )
        or (
            typed.anti_forgery_control_present is not None
            and type(typed.anti_forgery_control_present) is not bool
        )
    ):
        _evidence_integrity_fail()
    parser_facts = (
        typed.configuration_action,
        typed.configuration_field_count,
        typed.anti_forgery_control_present,
    )
    if expected_stage_id != "CONFIG_PARSE" and parser_facts != (None, None, None):
        _evidence_integrity_fail()
    if not typed.attempted:
        if (
            typed.status != 0
            or typed.media_type != "application/octet-stream"
            or typed.final_url is not None
            or typed.byte_length != 0
            or typed.redirect_rejected
            or parser_facts != (None, None, None)
        ):
            _evidence_integrity_fail()
        derived_terminal = "NOT_ATTEMPTED"
    elif typed.redirect_rejected:
        derived_terminal = "SOURCE_CONTRACT_CHANGED"
    elif not _HTTP_SUCCESS_MIN <= typed.status < _HTTP_SUCCESS_MAX:
        derived_terminal = "OUTAGE"
    elif typed.final_url != expected_final_url:
        derived_terminal = "SOURCE_CONTRACT_CHANGED"
    elif typed.byte_length > max_bytes:
        derived_terminal = "TRUNCATED"
    elif typed.byte_length == 0:
        derived_terminal = "EMPTY_RESPONSE"
    elif expected_stage_id == "CONFIG_PARSE" and (
        typed.configuration_action != _HKEL_CONFIGURATION_ACTION
        or typed.configuration_field_count is None
        or typed.configuration_field_count == 0
        or typed.anti_forgery_control_present is not True
    ):
        derived_terminal = "SOURCE_CONTRACT_CHANGED"
    else:
        derived_terminal = "CAPTURED"
    assertion_consistent = typed.terminal_code == derived_terminal
    effective_terminal = derived_terminal if assertion_consistent else "SOURCE_CONTRACT_CHANGED"
    return typed, derived_terminal, effective_terminal, assertion_consistent


def _read_hkel_comparison(body: bytes) -> bytes:
    """Recover the stable session projection from retained sanitized evidence."""
    document = parse_json_bytes(body, max_bytes=64_000)
    if type(document) is not dict or type(document.get("stable")) is not dict:
        _fail("PREDECESSOR_REPORT_MALFORMED")
    return _canonical(document["stable"])


def _authority_identity(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if len(raw) > _MAX_AUTHORITY_BYTES:
        _fail("AUTHORITY_MANIFEST_MALFORMED")
    document = parse_json_bytes(raw, max_bytes=_MAX_AUTHORITY_BYTES)
    if type(document) is not dict:
        _fail("AUTHORITY_MANIFEST_MALFORMED")
    candidate = cast("dict[str, object]", document)
    fingerprint = candidate.get("fingerprint")
    unsigned = dict(candidate)
    unsigned.pop("fingerprint", None)
    if (
        candidate.get("schema_version") != "1.0.0"
        or candidate.get("scope") != "HK_V1_SOURCE_ADMISSION_PREFLIGHT"
        or candidate.get("provenance") != _AUTHORITY
        or fingerprint != _digest(_canonical(unsigned))
    ):
        _fail("AUTHORITY_MANIFEST_MALFORMED")
    return _AUTHORITY, cast("str", fingerprint)


def _parse_hong_kong_cutoff(value: str) -> datetime:
    """Require one exact second-resolution Asia/Hong_Kong baseline cutoff."""
    if type(value) is not str or _HK_CUTOFF.fullmatch(value) is None:
        _fail(_OBSERVATION_CUTOFF_MALFORMED)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(_OBSERVATION_CUTOFF_MALFORMED) from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 8 * 60 * 60:
        _fail(_OBSERVATION_CUTOFF_MALFORMED)
    return parsed


def _safe_output_root(output_root: Path, repository_root: Path) -> Path:
    root = repository_root.resolve(strict=True)
    var_root = (root / "var").resolve(strict=False)
    candidate = output_root if output_root.is_absolute() else root / output_root
    candidate = candidate.resolve(strict=False)
    candidate.relative_to(var_root)
    if candidate == var_root:
        _fail("OUTPUT_ROOT_UNSAFE")
    current = root
    for part in candidate.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            _fail("OUTPUT_ROOT_UNSAFE")
    return candidate


def _reject_runtime_evidence_overlap(path: Path, output_root: Path) -> None:
    """Reject a runtime coordinate inside the canonical retained-evidence root."""
    try:
        path.relative_to(output_root)
    except ValueError:
        return
    _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)


def _trusted_runtime_component(details: os.stat_result, *, role: str) -> bool:
    """Validate one pinned directory according to its trusted-base role."""
    mode = stat.S_IMODE(details.st_mode)
    sticky_shared = bool(mode & stat.S_ISVTX) and bool(mode & 0o002)
    if not stat.S_ISDIR(details.st_mode):
        return False
    if role == "ancestor":
        return mode & 0o022 == 0
    if role == "base":
        return sticky_shared or (details.st_uid == os.geteuid() and mode & 0o022 == 0)
    return role == "descendant" and details.st_uid == os.geteuid() and mode & 0o022 == 0


def _pinned_descriptor_path(descriptor: int) -> Path:
    """Read the kernel-held Linux path for one pinned directory descriptor."""
    path = Path(f"/proc/self/fd/{descriptor}").readlink()
    if not path.is_absolute() or str(path).endswith(" (deleted)"):
        _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)
    return path


def _open_pinned_runtime_parent(*, parent: Path, trusted_base: Path) -> int:
    """Walk every component without following symlinks and return the exact parent fd."""
    descriptor: int | None = None
    try:
        descriptor = os.open(
            Path(parent.anchor), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        root_details = os.fstat(descriptor)
        if not _trusted_runtime_component(
            root_details, role="base" if Path(parent.anchor) == trusted_base else "ancestor"
        ):
            _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)
        current = Path(parent.anchor)
        base_seen = current == trusted_base
        for component in parent.parts[1:]:
            lexical = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            details = os.fstat(next_descriptor)
            next_path = current / component
            role = (
                "base" if next_path == trusted_base else "descendant" if base_seen else "ancestor"
            )
            if (
                not _trusted_runtime_component(lexical, role=role)
                or not _trusted_runtime_component(details, role=role)
                or (lexical.st_dev, lexical.st_ino) != (details.st_dev, details.st_ino)
            ):
                os.close(next_descriptor)
                _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)
            os.close(descriptor)
            descriptor = next_descriptor
            current = next_path
            base_seen = base_seen or current == trusted_base
        if not base_seen or current != parent or _pinned_descriptor_path(descriptor) != parent:
            _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)
        return descriptor  # noqa: TRY300 - descriptor ownership transfers here.
    except SourceAttemptClaimError:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise
    except (OSError, TypeError, ValueError) as error:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise SourceAttemptClaimError(_SOURCE_ATTEMPT_LOCK_UNSAFE) from error


def _private_runtime_directory(*, output_root: Path) -> tuple[Path, int]:
    """Create and pin the private runtime directory used only for OS-held claims."""
    trusted_base = _TRUSTED_RUNTIME_BASE
    process_temp_override = os.environ.get("TMPDIR")
    if process_temp_override not in {None, str(trusted_base)}:
        _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)
    configured = os.environ.get(_ATTEMPT_LOCK_ROOT_ENV)
    path = (
        Path(configured)
        if configured is not None
        else trusted_base / f"asklegal-hk-v1-source-attempt-locks-{os.geteuid()}"
    )
    if (
        not trusted_base.is_absolute()
        or not path.is_absolute()
        or path in {Path(path.anchor), trusted_base}
        or any(part in {".", ".."} for part in (*trusted_base.parts, *path.parts))
    ):
        _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)
    try:
        path.relative_to(trusted_base)
    except ValueError:
        _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)
    _reject_runtime_evidence_overlap(path, output_root)
    parent_fd = _open_pinned_runtime_parent(parent=path.parent, trusted_base=trusted_base)
    descriptor: int | None = None
    try:
        _reject_runtime_evidence_overlap(
            _pinned_descriptor_path(parent_fd) / path.name, output_root
        )
        with suppress(FileExistsError):
            os.mkdir(path.name, _PRIVATE_RUNTIME_MODE, dir_fd=parent_fd)
        lexical = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
        details = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(lexical.st_mode)
            or not stat.S_ISDIR(details.st_mode)
            or lexical.st_uid != os.geteuid()
            or details.st_uid != os.geteuid()
            or stat.S_IMODE(lexical.st_mode) != _PRIVATE_RUNTIME_MODE
            or stat.S_IMODE(details.st_mode) != _PRIVATE_RUNTIME_MODE
            or (lexical.st_dev, lexical.st_ino) != (details.st_dev, details.st_ino)
            or _pinned_descriptor_path(descriptor) != path
        ):
            _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)
    except SourceAttemptClaimError:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise
    except (OSError, TypeError, ValueError) as error:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise SourceAttemptClaimError(_SOURCE_ATTEMPT_LOCK_UNSAFE) from error
    finally:
        with suppress(OSError):
            os.close(parent_fd)
    return path, descriptor


@contextmanager
def _attempt_claim(output_root: Path, attempt_id: str) -> Generator[None]:
    """Hold one non-blocking cross-process claim outside retained evidence."""
    runtime_path, directory_fd = _private_runtime_directory(output_root=output_root)
    identity = _canonical({"attempt_id": attempt_id, "output_root": str(output_root)})
    filename = hashlib.sha256(identity).hexdigest() + ".lock"
    lock_fd: int | None = None
    locked = False
    try:
        try:
            lock_fd = os.open(
                filename,
                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                _PRIVATE_LOCK_MODE,
                dir_fd=directory_fd,
            )
            details = os.fstat(lock_fd)
            current = os.fstat(directory_fd)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.geteuid()
                or stat.S_IMODE(details.st_mode) != _PRIVATE_LOCK_MODE
                or details.st_nlink != 1
                or not stat.S_ISDIR(current.st_mode)
                or _pinned_descriptor_path(directory_fd) != runtime_path
            ):
                _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in {errno.EACCES, errno.EAGAIN}:
                    raise SourceAttemptClaimError(_SOURCE_ATTEMPT_IN_PROGRESS) from error
                raise SourceAttemptClaimError(_SOURCE_ATTEMPT_LOCK_UNSAFE) from error
            locked = True
        except SourceAttemptClaimError:
            raise
        except (OSError, TypeError, ValueError) as error:
            raise SourceAttemptClaimError(_SOURCE_ATTEMPT_LOCK_UNSAFE) from error
        yield
    finally:
        if lock_fd is not None:
            if locked:
                with suppress(OSError):
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
            with suppress(OSError):
                os.close(lock_fd)
        with suppress(OSError):
            os.close(directory_fd)


@contextmanager
def source_attempt_claim(
    *, output_root: Path, attempt_id: str, repository_root: Path
) -> Generator[object]:
    """Own one exact attempt across CLI authorization and execution."""
    if _ATTEMPT_ID.fullmatch(attempt_id) is None:
        _fail("ATTEMPT_ID_MALFORMED")
    root = _safe_output_root(output_root, repository_root)
    with _attempt_claim(root, attempt_id):
        claim = _HeldSourceAttemptClaim(root, attempt_id)
        try:
            yield claim
        finally:
            claim.active = False


def _require_held_attempt_claim(claim: object, *, output_root: Path, attempt_id: str) -> None:
    """Accept only the active claim issued for this exact canonical identity."""
    if (
        type(claim) is not _HeldSourceAttemptClaim
        or not claim.active
        or claim.output_root != output_root
        or claim.attempt_id != attempt_id
    ):
        _attempt_claim_fail(_SOURCE_ATTEMPT_LOCK_UNSAFE)


def _registered_endpoints(
    source_family: str,
    *,
    judiciary_endpoint_204_version: str | None = None,
    hkex_historical_attempt_id: str | None = None,
) -> tuple[OfficialEndpointContract, ...]:
    if source_family == "HKEX":
        if hkex_historical_attempt_id is None:
            return load_hk_regulatory_source_register().endpoints
        try:
            return historical_hkex_replay_pin(hkex_historical_attempt_id).endpoints
        except KeyError:
            _fail("EXECUTION_AUTHORIZATION_BINDING_INVALID")
    if source_family == "JUDICIARY":
        register = load_hk_cases_source_register()
        admitted = {
            endpoint_id
            for source in register.sources
            if source.source_id in {"HK-CASE-HKLII-DISCOVERY", "HK-CASE-JUDICIARY-LRS-INVENTORY"}
            for endpoint_id in source.endpoint_ids
        }
        endpoints = tuple(
            endpoint for endpoint in register.endpoints if endpoint.endpoint_id in admitted
        )
        if judiciary_endpoint_204_version is None:
            return endpoints
        return tuple(
            replace(endpoint, version=judiciary_endpoint_204_version)
            if endpoint.endpoint_id == "sep_000000000000000000000000000000000000000000000204"
            else endpoint
            for endpoint in endpoints
        )
    if source_family in {"HKEL", "GLD"}:
        register = load_hk_legislation_source_register()
        source_ids = (
            {"HK-LEG-GLD-EGAZETTE"}
            if source_family == "GLD"
            else {
                "HK-LEG-BASIC-LAW-PORTAL",
                "HK-LEG-HKEL-CURRENT-DATA",
                "HK-LEG-HKEL-CURRENT-INVENTORY",
                "HK-LEG-HKEL-EDITORIAL-RECORDS",
                "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
            }
        )
        admitted = {
            endpoint_id
            for source in register.sources
            if source.source_id in source_ids
            for endpoint_id in source.endpoint_ids
        }
        return tuple(
            endpoint for endpoint in register.endpoints if endpoint.endpoint_id in admitted
        )
    _fail("SOURCE_FAMILY_NOT_IMPLEMENTED")


def _current_judiciary_authorization_urls() -> frozenset[str]:
    """Read the complete current Cases URL set independently of execution test shims."""
    register = load_hk_cases_source_register()
    source_ids = {"HK-CASE-HKLII-DISCOVERY", "HK-CASE-JUDICIARY-LRS-INVENTORY"}
    admitted = {
        endpoint_id
        for source in register.sources
        if source.source_id in source_ids
        for endpoint_id in source.endpoint_ids
    }
    return frozenset(
        endpoint.url for endpoint in register.endpoints if endpoint.endpoint_id in admitted
    )


_HISTORICAL_JUDICIARY_ENTRY_CONTRACT_VERSIONS = {
    "judiciary-live-baseline-20260828a": "1.0.0",
    "judiciary-live-baseline-20260830b": "1.0.0",
    "judiciary-live-baseline-20260830c": "1.0.1",
    "judiciary-live-baseline-20260830d": "1.0.2",
    "judiciary-live-baseline-20260830e": "1.0.3",
    "judiciary-live-baseline-20260830f": "1.0.4",
    "judiciary-live-baseline-20260830g": "1.0.5",
    "judiciary-live-baseline-20260830h": "1.0.6",
    "judiciary-live-baseline-20260830i": "1.0.7",
    "judiciary-live-baseline-20260830j": "1.0.8",
    "judiciary-live-baseline-20260830k": "1.0.9",
    "judiciary-live-baseline-20260830l": "1.0.10",
    "judiciary-live-baseline-20260830m": "1.0.10",
    "judiciary-live-baseline-20260831n": "1.0.10",
    "judiciary-live-baseline-20260831o": "1.0.11",
    "judiciary-live-baseline-20260831p": "1.0.12",
    "judiciary-live-baseline-20260831q": "1.0.12",
    "judiciary-live-baseline-20260831r": "1.0.12",
    "judiciary-live-baseline-20260831s": "1.0.12",
}
_HISTORICAL_HKEX_ATTEMPT_IDS = historical_hkex_attempt_ids()


def _judiciary_report_entry_contract_version(report: dict[str, object]) -> str:
    """Derive a continuation parent's closed form version from its retained entry record."""
    matches = [
        cast("dict[str, object]", raw)
        for raw in cast("list[object]", report.get("endpoints"))
        if type(raw) is dict
        and cast("dict[str, object]", raw).get("endpoint_id")
        == "sep_000000000000000000000000000000000000000000000204"
    ]
    if len(matches) != 1 or type(matches[0].get("endpoint_version")) is not str:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    version = cast("str", matches[0]["endpoint_version"])
    try:
        _judiciary_result_contract_version(version)
    except ValueError as error:
        raise PredecessorValidationError(_PREDECESSOR_REPORT_MALFORMED) from error
    return version


def _judiciary_report_entry_contract_version_if_reached(
    report: dict[str, object],
) -> str | None:
    """Return the retained form version, or none for a bounded pre-entry stop."""
    raw_endpoints = report.get("endpoints")
    if type(raw_endpoints) is not list:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    endpoints = tuple(cast("dict[str, object]", raw) for raw in cast("list[object]", raw_endpoints))
    if any(
        cast("str", endpoint.get("endpoint_id", "")).startswith(
            ("judiciary-year-", "judiciary-dis-")
        )
        for endpoint in endpoints
    ):
        return _judiciary_report_entry_contract_version(report)
    if any(
        endpoint.get("endpoint_id") == "sep_000000000000000000000000000000000000000000000204"
        for endpoint in endpoints
    ):
        return _judiciary_report_entry_contract_version(report)
    return None


def _judiciary_result_contract_version(  # noqa: C901, PLR0911, PLR0912
    entry_contract_version: str,
) -> str:
    """Map one frozen search-form grammar to its retained result-page grammar."""
    if entry_contract_version in {"1.0.0", "1.0.1"}:
        return "1.0.0"
    if entry_contract_version == "1.0.2":
        return "1.0.1"
    if entry_contract_version == "1.0.3":
        return "1.0.2"
    if entry_contract_version == "1.0.4":
        return "1.0.3"
    if entry_contract_version == "1.0.5":
        return "1.0.4"
    if entry_contract_version == "1.0.6":
        return "1.0.5"
    if entry_contract_version == "1.0.7":
        return "1.0.6"
    if entry_contract_version == "1.0.8":
        return "1.0.7"
    if entry_contract_version == "1.0.9":
        return "1.0.8"
    if entry_contract_version == "1.0.10":
        return "1.0.9"
    if entry_contract_version == "1.0.11":
        return "1.0.10"
    if entry_contract_version == "1.0.12":
        return "1.0.11"
    if entry_contract_version == "1.0.13":
        return "1.0.12"
    code = "JUDICIARY_RESULT_PAGE_CONTRACT_VERSION_INVALID"
    raise ValueError(code)


def _judiciary_partition_snapshot(
    partition: JudiciaryYearPartition,
) -> tuple[tuple[int, object, str], ...]:
    """Project one full unique listing map into identity-sorted stable bytes semantics."""
    return tuple(
        sorted(
            zip(
                partition.dis_ids,
                partition.decision_dates,
                partition.all_artifact_urls,
                strict=True,
            ),
            key=lambda item: item[0],
        )
    )


def _judiciary_inventory_snapshot(
    partitions: list[JudiciaryYearPartition],
) -> tuple[tuple[tuple[int, int, int, int], ...], tuple[tuple[int, object, str], ...]]:
    """Freeze per-year accounting and one global identity map for pass equality."""
    accounting = tuple(
        sorted(
            (
                partition.year,
                partition.reported_results,
                partition.reported_pages,
                partition.listing_count,
            )
            for partition in partitions
        )
    )
    if len({row[0] for row in accounting}) != len(accounting):
        code = "JUDICIARY_YEAR_PARTITION_DRIFT"
        raise ValueError(code)
    rows = tuple(
        row for partition in partitions for row in _judiciary_partition_snapshot(partition)
    )
    if len({row[0] for row in rows}) != len(rows) or len({row[2] for row in rows}) != len(rows):
        code = "JUDICIARY_DIS_DUPLICATE"
        raise ValueError(code)
    return accounting, tuple(sorted(rows, key=lambda item: item[0]))


def _write_immutable(path: Path, content: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as stream:
                stream.write(content)
                stream.flush()
        except FileExistsError:
            pass
        fingerprint, byte_length = _digest_file(path)
    except (OSError, TypeError, ValueError) as error:
        raise SourceEvidenceIntegrityError(_SOURCE_EVIDENCE_INTEGRITY_FAILURE) from error
    if fingerprint != _digest(content) or byte_length != len(content):
        _evidence_integrity_fail()


def _publish_attempt_report(path: Path, content: bytes) -> None:
    """Verify a same-directory temporary before atomically publishing the manifest."""
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(16)}.tmp")
    expected_fingerprint = _digest(content)
    try:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("xb") as stream:
                written = stream.write(content)
                if written != len(content):
                    _evidence_integrity_fail()
                stream.flush()
                os.fsync(stream.fileno())
            fingerprint, byte_length = _digest_file(temporary)
            if fingerprint != expected_fingerprint or byte_length != len(content):
                _evidence_integrity_fail()
            try:
                os.link(temporary, path)
            except FileExistsError:
                fingerprint, byte_length = _digest_file(path)
                if fingerprint != expected_fingerprint or byte_length != len(content):
                    _evidence_integrity_fail()
        except (OSError, TypeError, ValueError) as error:
            raise SourceEvidenceIntegrityError(_SOURCE_EVIDENCE_INTEGRITY_FAILURE) from error
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def _derived_report_result(counts: dict[str, int], procedures: list[dict[str, object]]) -> str:
    """Derive the only report result the writer may claim from terminal accounting."""
    if any(item.get("terminal_code") == "OBSERVATION_EXECUTION_FAILURE" for item in procedures):
        result = "OBSERVATION_EXECUTION_FAILURE"
    elif any(item.get("terminal_code") == "BUDGET_EXHAUSTED" for item in procedures):
        result = "OBSERVATION_BUDGET_EXHAUSTED"
    elif counts.get("TRUNCATED"):
        result = "TRUNCATED_RESPONSE"
    elif counts.get("OUTAGE") or counts.get("EMPTY_RESPONSE"):
        result = "SOURCE_OUTAGE"
    elif counts.get("SOURCE_CONTRACT_CHANGED") or any(
        item.get("terminal_code") == "SOURCE_CONTRACT_CHANGED" for item in procedures
    ):
        result = "SOURCE_CONTRACT_CHANGED"
    elif counts.get("CHALLENGE_AUTHORITY_REQUIRED"):
        result = "CHALLENGE_AUTHORITY_REQUIRED"
    elif counts.get("SESSION_PROCEDURE_NOT_IMPLEMENTED"):
        result = "SESSION_PROCEDURE_NOT_IMPLEMENTED"
    elif procedures and all(item.get("terminal_code") == "COMPLETE" for item in procedures):
        result = "COMPLETE"
    else:
        result = "EVIDENCE_CAPTURED_INCOMPLETE"
    return result


def _report_fingerprints(report: dict[str, object]) -> dict[str, str]:
    """Return the already-validated comparison projection without reading evidence."""
    result: dict[str, str] = {}
    for raw_endpoint in cast("list[object]", report["endpoints"]):
        endpoint = cast("dict[str, object]", raw_endpoint)
        endpoint_id = cast("str", endpoint["endpoint_id"])
        result[endpoint_id] = cast(
            "str", endpoint.get("comparison_fingerprint", endpoint["body_fingerprint"])
        )
    return result


def _valid_report_url(value: object) -> bool:
    """Recognize one inert exact HTTPS request locator without leaking parser errors."""
    if type(value) is not str:
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and port in {None, 443}
    )


def _validate_judiciary_retry_report(  # noqa: C901, PLR0912, PLR0915
    report: dict[str, object],
    *,
    request_start_offset: int = 0,
    retained_byte_offset: int = 0,
    elapsed_seconds_offset: float = 0.0,
) -> dict[str, object]:
    """Validate the schema-1.1 physical ledger before generic report replay checks."""
    expected_keys = _JUDICIARY_RETRY_REPORT_KEYS
    if frozenset(report) not in {expected_keys, expected_keys | {"observation_stop"}}:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    policy_name = recognized_execution_policy(
        report.get("execution_policy"), report.get("execution_policy_fingerprint")
    )
    if (
        report.get("source_family") != "JUDICIARY"
        or report.get("report_schema_version") != "1.1.0"
        or policy_name is None
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    raw_accounting = report.get("observation_accounting")
    raw_attempts = report.get("transport_attempts")
    if type(raw_accounting) is not dict or type(raw_attempts) is not list:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    accounting = cast("dict[str, object]", raw_accounting)
    attempts = cast("list[object]", raw_attempts)
    if frozenset(accounting) != frozenset(
        {
            "elapsed_seconds",
            "profile",
            "profile_fingerprint",
            "rejected_response_bytes",
            "request_starts",
            "retained_response_bytes",
            "stop_code",
        }
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    profile = accounting.get("profile")
    expected_profile = cast("dict[str, object]", _judiciary_observation_profile())
    if (
        type(profile) is not dict
        or _canonical(cast("dict[str, object]", profile)) != _canonical(expected_profile)
        or accounting.get("profile_fingerprint") != _digest(_canonical(expected_profile))
        or type(accounting.get("request_starts")) is not int
        or cast("int", accounting["request_starts"]) < 0
        or type(accounting.get("retained_response_bytes")) is not int
        or cast("int", accounting["retained_response_bytes"]) < 0
        or type(accounting.get("rejected_response_bytes")) is not int
        or cast("int", accounting["rejected_response_bytes"]) < 0
        or type(accounting.get("elapsed_seconds")) not in {int, float}
        or not math.isfinite(cast("float", accounting["elapsed_seconds"]))
        or cast("float", accounting["elapsed_seconds"]) < 0
        or accounting.get("stop_code")
        not in {
            None,
            "REQUEST_BUDGET_EXHAUSTED",
            "BYTE_BUDGET_EXHAUSTED",
            "ELAPSED_TIME_BUDGET_EXHAUSTED",
            "OBSERVATION_EXECUTION_FAILURE",
        }
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    grouped: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    seen_endpoint_ids: set[str] = set()
    for sequence, raw_attempt in enumerate(attempts, start=1):
        if type(raw_attempt) is not dict:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        attempt = cast("dict[str, object]", raw_attempt)
        if (
            frozenset(attempt) != _TRANSPORT_ATTEMPT_KEYS
            or type(attempt.get("sequence")) is not int
            or attempt.get("sequence") != sequence
            or type(attempt.get("endpoint_id")) is not str
            or type(attempt.get("endpoint_version")) is not str
            or _VERSION.fullmatch(cast("str", attempt["endpoint_version"])) is None
            or attempt.get("method") != "GET"
            or not _valid_report_url(attempt.get("requested_url"))
            or type(attempt.get("max_bytes")) is not int
            or cast("int", attempt["max_bytes"]) <= 0
            or type(attempt.get("attempt_number")) is not int
            or attempt.get("attempt_number") not in {1, 2}
            or type(attempt.get("start_elapsed_seconds")) not in {int, float}
            or not math.isfinite(cast("float", attempt["start_elapsed_seconds"]))
            or cast("float", attempt["start_elapsed_seconds"]) < 0
            or type(attempt.get("status")) is not int
            or not 0 <= cast("int", attempt["status"]) <= _HTTP_STATUS_MAX
            or type(attempt.get("media_type")) is not str
            or type(attempt.get("final_url")) not in {str, type(None)}
            or (
                attempt.get("final_url") is not None
                and not _valid_report_url(attempt.get("final_url"))
            )
            or type(attempt.get("redirect_rejected")) is not bool
            or type(attempt.get("byte_length")) is not int
            or cast("int", attempt["byte_length"]) < 0
            or type(attempt.get("body_fingerprint")) is not str
            or _FINGERPRINT.fullmatch(cast("str", attempt["body_fingerprint"])) is None
            or attempt.get("object_key")
            != f"objects/{cast('str', attempt['body_fingerprint']).removeprefix('sha256:')}.bin"
            or attempt.get("terminal_code") not in _ENDPOINT_TERMINALS
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        final_url = cast("str | None", attempt["final_url"])
        requested_url = cast("str", attempt["requested_url"])
        if final_url is not None and (
            urlsplit(final_url).hostname != urlsplit(requested_url).hostname
            or (
                final_url != requested_url
                and not (
                    attempt["endpoint_id"] == _JUDICIARY_CURRENT_LISTING_ENTRY_ID
                    and final_url == _JUDICIARY_CURRENT_LISTING_TARGET_URL
                )
            )
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        exact_maintenance = policy_name in {
            "JUDICIARY_TRANSPORT_ATTEMPTS_1.1.0",
            "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0",
        } and (
            maintenance_outage_facts(
                status=cast("int", attempt["status"]),
                body_byte_length=cast("int", attempt["byte_length"]),
                body_fingerprint=cast("str", attempt["body_fingerprint"]),
                media_type=cast("str", attempt["media_type"]),
                final_url=cast("str | None", attempt["final_url"]),
                redirect_rejected=cast("bool", attempt["redirect_rejected"]),
                requested_url=requested_url,
            )
        )
        if attempt["redirect_rejected"]:
            derived_terminal = "SOURCE_CONTRACT_CHANGED"
        elif cast("int", attempt["byte_length"]) > cast("int", attempt["max_bytes"]):
            derived_terminal = "TRUNCATED"
        elif exact_maintenance or not (
            _HTTP_SUCCESS_MIN <= cast("int", attempt["status"]) < _HTTP_SUCCESS_MAX
        ):
            derived_terminal = "OUTAGE"
        elif attempt["byte_length"] == 0:
            derived_terminal = "EMPTY_RESPONSE"
        else:
            derived_terminal = "CAPTURED"
        if attempt["terminal_code"] != derived_terminal:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        if sequence == 1 and attempt["start_elapsed_seconds"] != 0:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        endpoint_id = cast("str", attempt["endpoint_id"])
        if not current or endpoint_id == current[-1]["endpoint_id"]:
            current.append(attempt)
        else:
            if cast("str", current[-1]["endpoint_id"]) in seen_endpoint_ids:
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
            seen_endpoint_ids.add(cast("str", current[-1]["endpoint_id"]))
            grouped.append(current)
            current = [attempt]
    if current:
        if cast("str", current[-1]["endpoint_id"]) in seen_endpoint_ids:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        grouped.append(current)
    logical_endpoints = cast("list[object]", report["endpoints"])
    logical = {
        cast("str", item["endpoint_id"]): cast("dict[str, object]", item)
        for item in logical_endpoints
        if type(item) is dict
    }
    finalized_group_ids: set[str] = set()
    finalized_group_order: list[str] = []
    stopped_group_index: int | None = None
    for group in grouped:
        first = group[0]
        if first.get("attempt_number") != 1 or len(group) > _JUDICIARY_MAX_TRANSPORT_ATTEMPTS:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        if any(
            attempt.get(key) != first.get(key)
            for attempt in group[1:]
            for key in ("endpoint_version", "method", "requested_url", "max_bytes")
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        normalized_failure = (
            first.get("status") == 0
            and first.get("byte_length") == 0
            and first.get("body_fingerprint") == _digest(b"")
            and first.get("media_type") == "application/octet-stream"
            and first.get("final_url") is None
            and first.get("redirect_rejected") is False
        )
        exact_maintenance = policy_name in {
            "JUDICIARY_TRANSPORT_ATTEMPTS_1.1.0",
            "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0",
        } and (
            maintenance_outage_facts(
                status=cast("int", first["status"]),
                body_byte_length=cast("int", first["byte_length"]),
                body_fingerprint=cast("str", first["body_fingerprint"]),
                media_type=cast("str", first["media_type"]),
                final_url=cast("str | None", first["final_url"]),
                redirect_rejected=cast("bool", first["redirect_rejected"]),
                requested_url=cast("str", first["requested_url"]),
            )
        )
        exact_server_error = policy_name == "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0" and (
            publisher_server_error_facts(
                status=cast("int", first["status"]),
                body_byte_length=cast("int", first["byte_length"]),
                media_type=cast("str", first["media_type"]),
                final_url=cast("str | None", first["final_url"]),
                redirect_rejected=cast("bool", first["redirect_rejected"]),
                requested_url=cast("str", first["requested_url"]),
                max_bytes=cast("int", first["max_bytes"]),
            )
        )
        eligible = normalized_failure or exact_maintenance or exact_server_error
        if len(group) == _JUDICIARY_MAX_TRANSPORT_ATTEMPTS and (
            not eligible or group[1].get("attempt_number") != _JUDICIARY_MAX_TRANSPORT_ATTEMPTS
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        endpoint_id = cast("str", first["endpoint_id"])
        endpoint = logical.get(endpoint_id)
        if len(group) == 1 and eligible:
            if endpoint is not None or accounting.get("stop_code") is None:
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
            if stopped_group_index is not None:
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
            stopped_group_index = len(finalized_group_order)
            continue
        if endpoint is None:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        finalized_group_ids.add(endpoint_id)
        finalized_group_order.append(endpoint_id)
        final = group[-1]
        for key in (
            "body_fingerprint",
            "byte_length",
            "endpoint_id",
            "endpoint_version",
            "media_type",
            "method",
            "object_key",
            "requested_url",
            "status",
        ):
            if endpoint.get(key) != final.get(key):
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if set(logical) != finalized_group_ids:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if finalized_group_order != [
        cast("str", cast("dict[str, object]", item)["endpoint_id"]) for item in logical_endpoints
    ]:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if stopped_group_index is not None and stopped_group_index != len(finalized_group_order):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if any(
        cast("float", cast("dict[str, object]", later)["start_elapsed_seconds"])
        - cast("float", cast("dict[str, object]", earlier)["start_elapsed_seconds"])
        < _JUDICIARY_MINIMUM_START_INTERVAL_SECONDS
        for earlier, later in pairwise(attempts)
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    retained_bytes = sum(
        cast("int", cast("dict[str, object]", item)["byte_length"]) for item in attempts
    )
    expected_starts = len(attempts) + (
        1 if accounting.get("stop_code") == "BYTE_BUDGET_EXHAUSTED" else 0
    )
    if (
        accounting.get("retained_response_bytes") != retained_bytes
        or accounting.get("request_starts") != expected_starts
        or retained_byte_offset + cast("int", accounting["retained_response_bytes"])
        > _JUDICIARY_RETAINED_BYTE_LIMIT
        or request_start_offset + cast("int", accounting["request_starts"])
        > _JUDICIARY_REQUEST_START_LIMIT
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if attempts and cast("float", accounting["elapsed_seconds"]) < cast(
        "float", cast("dict[str, object]", attempts[-1])["start_elapsed_seconds"]
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if accounting["stop_code"] is None and (
        accounting["rejected_response_bytes"] != 0
        or elapsed_seconds_offset + cast("float", accounting["elapsed_seconds"])
        >= _JUDICIARY_ELAPSED_SECONDS_LIMIT
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    observation_stop = report.get("observation_stop")
    typed_observation_stop = (
        cast("dict[str, object]", observation_stop) if type(observation_stop) is dict else None
    )
    if (
        typed_observation_stop is None
        or accounting.get("stop_code") != typed_observation_stop.get("code")
    ) and (observation_stop is not None or accounting.get("stop_code") is not None):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    stop_code = accounting.get("stop_code")
    if (
        stop_code == "REQUEST_BUDGET_EXHAUSTED"
        and request_start_offset + cast("int", accounting["request_starts"])
        != _JUDICIARY_REQUEST_START_LIMIT
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if (
        stop_code == "ELAPSED_TIME_BUDGET_EXHAUSTED"
        and elapsed_seconds_offset + cast("float", accounting["elapsed_seconds"])
        < _JUDICIARY_ELAPSED_SECONDS_LIMIT
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if stop_code == "BYTE_BUDGET_EXHAUSTED" and (
        accounting["rejected_response_bytes"] == 0
        or retained_byte_offset
        + cast("int", accounting["retained_response_bytes"])
        + cast("int", accounting["rejected_response_bytes"])
        <= _JUDICIARY_RETAINED_BYTE_LIMIT
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    legacy = dict(report)
    for key in (
        "execution_policy",
        "execution_policy_fingerprint",
        "observation_accounting",
        "report_schema_version",
        "transport_attempts",
    ):
        del legacy[key]
    return legacy


def _validate_judiciary_continuation_report(  # noqa: C901, PLR0915 - closed schema verifier.
    report: dict[str, object],
) -> dict[str, object]:
    """Validate schema 1.2's composed logical projection and segment-only ledger."""
    if frozenset(report) not in {
        _JUDICIARY_CONTINUATION_REPORT_KEYS,
        _JUDICIARY_CONTINUATION_REPORT_KEYS | {"observation_stop"},
    }:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    binding = report.get("continuation_binding")
    cumulative = report.get("cumulative_observation_accounting")
    endpoints = report.get("endpoints")
    if type(binding) is not dict or type(cumulative) is not dict or type(endpoints) is not list:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    typed_binding = cast("dict[str, object]", binding)
    typed_cumulative = cast("dict[str, object]", cumulative)
    expected_binding_keys = frozenset(
        {
            "continuation_authority_manifest_fingerprint",
            "continuation_execution_authorization_fingerprint",
            "next_request",
            "predecessor_attempt_id",
            "predecessor_observation_accounting",
            "predecessor_report_fingerprint",
            "prefix_endpoint_count",
            "prefix_endpoints_fingerprint",
        }
    )
    if (
        frozenset(typed_binding) != expected_binding_keys
        or type(typed_binding.get("predecessor_attempt_id")) is not str
        or _ATTEMPT_ID.fullmatch(cast("str", typed_binding["predecessor_attempt_id"])) is None
        or type(typed_binding.get("predecessor_report_fingerprint")) is not str
        or _FINGERPRINT.fullmatch(cast("str", typed_binding["predecessor_report_fingerprint"]))
        is None
        or type(typed_binding.get("prefix_endpoint_count")) is not int
        or cast("int", typed_binding["prefix_endpoint_count"]) < 0
        or typed_binding.get("continuation_authority_manifest_fingerprint")
        != report.get("authority_manifest_fingerprint")
        or typed_binding.get("continuation_execution_authorization_fingerprint")
        != report.get("execution_authorization_fingerprint")
        or len(cast("list[object]", endpoints))
        < cast("int", typed_binding["prefix_endpoint_count"])
        or typed_binding.get("prefix_endpoints_fingerprint")
        != _digest(
            _canonical(
                cast("list[object]", endpoints)[
                    : cast("int", typed_binding["prefix_endpoint_count"])
                ]
            )
        )
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    next_request = typed_binding.get("next_request")
    attempts = cast("list[object]", report["transport_attempts"])
    if type(next_request) is not dict or not attempts:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    first_attempt = cast("dict[str, object]", attempts[0])
    expected_next_request: dict[str, object] = {
        "endpoint_id": first_attempt.get("endpoint_id"),
        "endpoint_version": first_attempt.get("endpoint_version"),
        "max_bytes": first_attempt.get("max_bytes"),
        "method": first_attempt.get("method"),
        "requested_url": first_attempt.get("requested_url"),
    }
    if _canonical(cast("dict[str, object]", next_request)) != _canonical(expected_next_request):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    segment = dict(report)
    segment.pop("continuation_binding")
    segment.pop("cumulative_observation_accounting")
    segment["report_schema_version"] = "1.1.0"
    prefix_count = cast("int", typed_binding["prefix_endpoint_count"])
    segment_endpoints = cast("list[object]", endpoints)[prefix_count:]
    segment["endpoints"] = segment_endpoints
    segment_counts: dict[str, int] = {}
    for raw_endpoint in segment_endpoints:
        if type(raw_endpoint) is not dict:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        terminal = cast("dict[str, object]", raw_endpoint).get("terminal_code")
        if type(terminal) is not str:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        segment_counts[terminal] = segment_counts.get(terminal, 0) + 1
    segment["endpoint_counts"] = dict(sorted(segment_counts.items()))
    predecessor_accounting = typed_binding.get("predecessor_observation_accounting")
    if type(predecessor_accounting) is not dict:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    typed_predecessor_accounting = cast("dict[str, object]", predecessor_accounting)
    if (
        frozenset(typed_predecessor_accounting)
        != frozenset(cast("dict[str, object]", report["observation_accounting"]))
        or type(typed_predecessor_accounting.get("request_starts")) is not int
        or type(typed_predecessor_accounting.get("retained_response_bytes")) is not int
        or type(typed_predecessor_accounting.get("elapsed_seconds")) not in {int, float}
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    predecessor_starts = cast("int", typed_predecessor_accounting["request_starts"])
    predecessor_bytes = cast("int", typed_predecessor_accounting["retained_response_bytes"])
    predecessor_elapsed = cast("float", typed_predecessor_accounting["elapsed_seconds"])
    validated = _validate_judiciary_retry_report(
        segment,
        request_start_offset=predecessor_starts,
        retained_byte_offset=predecessor_bytes,
        elapsed_seconds_offset=predecessor_elapsed,
    )
    segment_accounting = cast("dict[str, object]", report["observation_accounting"])
    expected_stop = (
        None
        if segment_accounting["stop_code"] is None
        else {
            "code": segment_accounting["stop_code"],
            "elapsed_seconds": segment_accounting["elapsed_seconds"],
            "profile": segment_accounting["profile"],
            "profile_fingerprint": segment_accounting["profile_fingerprint"],
            "rejected_response_bytes": segment_accounting["rejected_response_bytes"],
            "request_starts": segment_accounting["request_starts"],
            "retained_response_bytes": segment_accounting["retained_response_bytes"],
        }
    )
    expected_cumulative = dict(segment_accounting)
    expected_cumulative["request_starts"] = predecessor_starts + cast(
        "int", segment_accounting["request_starts"]
    )
    expected_cumulative["retained_response_bytes"] = predecessor_bytes + cast(
        "int", segment_accounting["retained_response_bytes"]
    )
    expected_cumulative["elapsed_seconds"] = predecessor_elapsed + cast(
        "float", segment_accounting["elapsed_seconds"]
    )
    if _canonical(report.get("observation_stop")) != _canonical(expected_stop) or _canonical(
        typed_cumulative
    ) != _canonical(expected_cumulative):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    validated["endpoints"] = endpoints
    validated["endpoint_counts"] = report["endpoint_counts"]
    return validated


def _predecessor_report_binding(  # noqa: C901, PLR0912, PLR0915 - closed report grammar.
    report: dict[str, object],
) -> tuple[str, str, str, str, str | None]:
    """Validate the complete canonical retained-report envelope before lineage use."""
    judiciary_retry_report = report.get("report_schema_version") == "1.1.0"
    judiciary_continuation_report = report.get("report_schema_version") == "1.2.0"
    hkex_role_aware_report = report.get("report_schema_version") == "2.0.0"
    if judiciary_retry_report:
        report = _validate_judiciary_retry_report(report)
    elif judiciary_continuation_report:
        report = _validate_judiciary_continuation_report(report)
    report_keys = frozenset(report)
    if report_keys not in {
        _LEGACY_REPORT_KEYS,
        _REPORT_KEYS,
        _JUDICIARY_OBSERVATION_REPORT_KEYS,
        _HKEX_ROLE_AWARE_REPORT_KEYS,
    }:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    attempt_id = report.get("attempt_id")
    source_family = report.get("source_family")
    observation_cutoff = report.get("observation_cutoff")
    authority_fingerprint = report.get("authority_manifest_fingerprint")
    authority_provenance = report.get("authority_provenance")
    execution_authorization_fingerprint = report.get("execution_authorization_fingerprint")
    predecessor_attempt_id = report.get("predecessor_attempt_id")
    change_state = report.get("change_state")
    result = report.get("result")
    raw_counts = report.get("endpoint_counts")
    raw_endpoints = report.get("endpoints")
    raw_procedures = report.get("source_procedures")
    raw_observation_stop: object = report.get("observation_stop")
    observation_stop = (
        cast("dict[str, object]", raw_observation_stop)
        if type(raw_observation_stop) is dict
        else {}
    )
    has_observation_stop = report_keys == _JUDICIARY_OBSERVATION_REPORT_KEYS
    if (
        type(attempt_id) is not str
        or _ATTEMPT_ID.fullmatch(attempt_id) is None
        or type(source_family) is not str
        or source_family not in {"GLD", "HKEL", "JUDICIARY", "HKEX"}
        or type(observation_cutoff) is not str
        or _HK_CUTOFF.fullmatch(observation_cutoff) is None
        or type(authority_fingerprint) is not str
        or _FINGERPRINT.fullmatch(authority_fingerprint) is None
        or authority_provenance != _AUTHORITY
        or (
            report_keys
            in {
                _REPORT_KEYS,
                _JUDICIARY_OBSERVATION_REPORT_KEYS,
                _HKEX_ROLE_AWARE_REPORT_KEYS,
            }
            and (
                type(execution_authorization_fingerprint) is not str
                or _FINGERPRINT.fullmatch(execution_authorization_fingerprint) is None
            )
        )
        or (
            predecessor_attempt_id is not None
            and (
                type(predecessor_attempt_id) is not str
                or _ATTEMPT_ID.fullmatch(predecessor_attempt_id) is None
                or predecessor_attempt_id == attempt_id
            )
        )
        or type(change_state) is not str
        or change_state not in {"FIRST_OBSERVATION", "NO_CHANGE_OBSERVED", "CHANGED_OBSERVED"}
        or (predecessor_attempt_id is None) != (change_state == "FIRST_OBSERVATION")
        or type(result) is not str
        or result not in _REPORT_RESULTS
        or report.get("readback_verified") is not True
        or type(raw_counts) is not dict
        or type(raw_endpoints) is not list
        or (not raw_endpoints and not has_observation_stop and not hkex_role_aware_report)
        or type(raw_procedures) is not list
        or (hkex_role_aware_report and source_family != "HKEX")
        or (
            has_observation_stop
            and (
                source_family != "JUDICIARY"
                or not observation_stop
                or frozenset(observation_stop)
                != frozenset(
                    {
                        "code",
                        "profile",
                        "profile_fingerprint",
                        "request_starts",
                        "rejected_response_bytes",
                        "retained_response_bytes",
                        "elapsed_seconds",
                    }
                )
                or observation_stop.get("code")
                not in {
                    "REQUEST_BUDGET_EXHAUSTED",
                    "BYTE_BUDGET_EXHAUSTED",
                    "ELAPSED_TIME_BUDGET_EXHAUSTED",
                    "OBSERVATION_EXECUTION_FAILURE",
                }
                or type(observation_stop.get("request_starts")) is not int
                or cast("int", observation_stop["request_starts"]) < 0
                or type(observation_stop.get("retained_response_bytes")) is not int
                or cast("int", observation_stop["retained_response_bytes"]) < 0
                or type(observation_stop.get("rejected_response_bytes")) is not int
                or cast("int", observation_stop["rejected_response_bytes"]) < 0
                or type(observation_stop.get("elapsed_seconds")) not in {int, float}
                or not math.isfinite(cast("float", observation_stop["elapsed_seconds"]))
                or cast("float", observation_stop["elapsed_seconds"]) < 0
                or type(observation_stop.get("profile")) is not dict
                or frozenset(cast("dict[str, object]", observation_stop["profile"]))
                != frozenset(
                    {
                        "elapsed_seconds_limit",
                        "minimum_start_interval_seconds",
                        "request_start_limit",
                        "retained_response_byte_limit",
                    }
                )
                or any(
                    type(value) not in {int, float} or not math.isfinite(cast("float", value))
                    for value in cast("dict[str, object]", observation_stop["profile"]).values()
                )
                or type(observation_stop.get("profile_fingerprint")) is not str
                or observation_stop["profile_fingerprint"]
                != _digest(_canonical(observation_stop["profile"]))
            )
        )
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    counts: dict[str, int] = {}
    for raw_code, raw_count in cast("dict[object, object]", raw_counts).items():
        if (
            type(raw_code) is not str
            or raw_code not in _ENDPOINT_TERMINALS
            or type(raw_count) is not int
            or raw_count <= 0
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        counts[raw_code] = raw_count
    endpoint_ids: set[str] = set()
    observed_counts: dict[str, int] = {}
    for raw_endpoint in cast("list[object]", raw_endpoints):
        if type(raw_endpoint) is not dict:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        endpoint = cast("dict[str, object]", raw_endpoint)
        endpoint_keys = frozenset(endpoint)
        endpoint_id = endpoint.get("endpoint_id")
        endpoint_version = endpoint.get("endpoint_version")
        method = endpoint.get("method")
        requested_url = endpoint.get("requested_url")
        media_type = endpoint.get("media_type")
        status = endpoint.get("status")
        terminal_code = endpoint.get("terminal_code")
        object_key = endpoint.get("object_key")
        byte_length = endpoint.get("byte_length")
        body_fingerprint = endpoint.get("body_fingerprint")
        comparison_fingerprint = endpoint.get("comparison_fingerprint")
        if (
            endpoint_keys not in {_ENDPOINT_KEYS, _ENDPOINT_KEYS | {"comparison_fingerprint"}}
            or type(endpoint_id) is not str
            or not endpoint_id
            or endpoint_id in endpoint_ids
            or type(endpoint_version) is not str
            or _VERSION.fullmatch(endpoint_version) is None
            or type(method) is not str
            or method not in {"GET", "LOCAL_PARSE", "POST"}
            or not _valid_report_url(requested_url)
            or type(media_type) is not str
            or not media_type
            or type(status) is not int
            or not 0 <= status <= _HTTP_STATUS_MAX
            or type(terminal_code) is not str
            or terminal_code not in _ENDPOINT_TERMINALS
            or type(object_key) is not str
            or _OBJECT_KEY.fullmatch(object_key) is None
            or type(byte_length) is not int
            or byte_length < 0
            or type(body_fingerprint) is not str
            or _FINGERPRINT.fullmatch(body_fingerprint) is None
            or object_key != f"objects/{body_fingerprint.removeprefix('sha256:')}.bin"
            or (
                comparison_fingerprint is not None
                and (
                    type(comparison_fingerprint) is not str
                    or _FINGERPRINT.fullmatch(comparison_fingerprint) is None
                    or source_family != "HKEL"
                    or (
                        not endpoint_id.startswith("hkel-session-")
                        and endpoint_id != _HKEL_CLIENT_CHECK_ENDPOINT_ID
                    )
                    or byte_length > _MAX_HKEL_COMPARISON_BYTES
                )
            )
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        endpoint_ids.add(endpoint_id)
        observed_counts[terminal_code] = observed_counts.get(terminal_code, 0) + 1
    if counts != observed_counts:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    endpoints = cast("list[object]", raw_endpoints)
    if (
        has_observation_stop
        and not judiciary_continuation_report
        and cast("int", observation_stop["retained_response_bytes"])
        != sum(
            cast("int", endpoint["byte_length"])
            for endpoint in (cast("dict[str, object]", item) for item in endpoints)
        )
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if has_observation_stop and not judiciary_continuation_report:
        profile = cast("dict[str, object]", observation_stop["profile"])
        if profile != _judiciary_observation_profile() or observation_stop[
            "profile_fingerprint"
        ] != _digest(_canonical(_judiciary_observation_profile())):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        request_starts = cast("int", observation_stop["request_starts"])
        rejected_response_bytes = cast("int", observation_stop["rejected_response_bytes"])
        elapsed_seconds = cast("float", observation_stop["elapsed_seconds"])
        endpoint_count = len(endpoints)
        request_limit = cast("int", profile["request_start_limit"])
        retained_limit = cast("int", profile["retained_response_byte_limit"])
        elapsed_limit = cast("float", profile["elapsed_seconds_limit"])
        stop_code = cast("str", observation_stop["code"])
        expected_request_starts = (
            request_starts
            if judiciary_retry_report
            else endpoint_count + (1 if stop_code == "BYTE_BUDGET_EXHAUSTED" else 0)
        )
        if (
            request_starts > request_limit
            or request_starts != expected_request_starts
            or cast("int", observation_stop["retained_response_bytes"]) > retained_limit
            or (
                stop_code == "REQUEST_BUDGET_EXHAUSTED"
                and (
                    request_starts != request_limit
                    or rejected_response_bytes != 0
                    or elapsed_seconds >= elapsed_limit
                )
            )
            or (
                stop_code == "BYTE_BUDGET_EXHAUSTED"
                and (
                    rejected_response_bytes <= 0
                    or cast("int", observation_stop["retained_response_bytes"])
                    + rejected_response_bytes
                    <= retained_limit
                    or elapsed_seconds >= elapsed_limit
                )
            )
            or (
                stop_code == "ELAPSED_TIME_BUDGET_EXHAUSTED"
                and (rejected_response_bytes != 0 or elapsed_seconds < elapsed_limit)
            )
            or (stop_code == "OBSERVATION_EXECUTION_FAILURE" and rejected_response_bytes != 0)
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    procedures: list[dict[str, object]] = []
    procedure_ids: set[str] = set()
    for raw_procedure in cast("list[object]", raw_procedures):
        if type(raw_procedure) is not dict:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        procedure = cast("dict[str, object]", raw_procedure)
        source_id = procedure.get("source_id")
        terminal_code = procedure.get("terminal_code")
        declared_member_count = procedure.get("declared_member_count")
        if (
            frozenset(procedure)
            != frozenset({"declared_member_count", "source_id", "terminal_code"})
            or type(source_id) is not str
            or source_id in procedure_ids
            or source_id not in _PROCEDURE_SOURCE_IDS[source_family]
            or type(terminal_code) is not str
            or terminal_code not in _PROCEDURE_TERMINALS
            or type(declared_member_count) is not int
            or declared_member_count < 0
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        procedure_ids.add(source_id)
        procedures.append(procedure)
    if frozenset(procedure_ids) != _PROCEDURE_SOURCE_IDS[source_family] or (
        not hkex_role_aware_report and result != _derived_report_result(counts, procedures)
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if has_observation_stop:
        stop_code = cast("str", observation_stop["code"])
        expected_terminal = (
            "OBSERVATION_EXECUTION_FAILURE"
            if stop_code == "OBSERVATION_EXECUTION_FAILURE"
            else "BUDGET_EXHAUSTED"
        )
        lrs = next(
            (item for item in procedures if item["source_id"] == "HK-CASE-JUDICIARY-LRS-INVENTORY"),
            cast("dict[str, object]", {}),
        )
        if lrs.get("terminal_code") != expected_terminal:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    return (
        source_family,
        observation_cutoff,
        authority_fingerprint,
        _AUTHORITY,
        cast("str | None", execution_authorization_fingerprint),
    )


def _verified_predecessor_fingerprints(  # noqa: C901, PLR0912
    output_root: Path, report: dict[str, object]
) -> dict[str, str]:
    """Independently reread every contained predecessor object before comparison."""
    try:
        resolved_root = output_root.resolve(strict=True)
    except OSError as error:
        raise PredecessorValidationError(_PREDECESSOR_EVIDENCE_READBACK_INVALID) from error
    fingerprints: dict[str, str] = {}
    for raw_endpoint in cast("list[object]", report["endpoints"]):
        endpoint = cast("dict[str, object]", raw_endpoint)
        endpoint_id = cast("str", endpoint["endpoint_id"])
        object_key = cast("str", endpoint["object_key"])
        body_fingerprint = cast("str", endpoint["body_fingerprint"])
        byte_length = cast("int", endpoint["byte_length"])
        expected_key = f"objects/{body_fingerprint.removeprefix('sha256:')}.bin"
        try:
            if object_key != expected_key or Path(object_key).is_absolute():
                _predecessor_fail(_PREDECESSOR_EVIDENCE_READBACK_INVALID)
            object_path = (resolved_root / object_key).resolve(strict=True)
            object_path.relative_to(resolved_root)
            retained_fingerprint, retained_length = _digest_file(object_path)
        except (OSError, ValueError) as error:
            raise PredecessorValidationError(_PREDECESSOR_EVIDENCE_READBACK_INVALID) from error
        if retained_fingerprint != body_fingerprint or retained_length != byte_length:
            _predecessor_fail(_PREDECESSOR_EVIDENCE_READBACK_INVALID)
        comparison_fingerprint = endpoint.get("comparison_fingerprint")
        if comparison_fingerprint is not None:
            try:
                comparison = _digest(_read_hkel_comparison(object_path.read_bytes()))
            except (OSError, TypeError, ValueError) as error:
                raise PredecessorValidationError(_PREDECESSOR_EVIDENCE_READBACK_INVALID) from error
            if comparison != comparison_fingerprint:
                _predecessor_fail(_PREDECESSOR_EVIDENCE_READBACK_INVALID)
            fingerprints[endpoint_id] = cast("str", comparison_fingerprint)
        else:
            fingerprints[endpoint_id] = body_fingerprint
    if report.get("report_schema_version") in {"1.1.0", "1.2.0"}:
        for raw_attempt in cast("list[object]", report["transport_attempts"]):
            attempt = cast("dict[str, object]", raw_attempt)
            object_key = cast("str", attempt["object_key"])
            body_fingerprint = cast("str", attempt["body_fingerprint"])
            byte_length = cast("int", attempt["byte_length"])
            try:
                object_path = (resolved_root / object_key).resolve(strict=True)
                object_path.relative_to(resolved_root)
                retained_fingerprint, retained_length = _digest_file(object_path)
            except (OSError, ValueError) as error:
                raise PredecessorValidationError(_PREDECESSOR_EVIDENCE_READBACK_INVALID) from error
            if retained_fingerprint != body_fingerprint or retained_length != byte_length:
                _predecessor_fail(_PREDECESSOR_EVIDENCE_READBACK_INVALID)
    return fingerprints


def _current_report_urls_are_bound(  # noqa: C901, PLR0911, PLR0912, PLR0915 - closed grammar.
    report: dict[str, object],
    *,
    registered_endpoints: tuple[OfficialEndpointContract, ...],
    allowed_urls: frozenset[str],
) -> bool:
    """Bind a current-authority retained report to exact static or derived locators."""
    static = {endpoint.endpoint_id: endpoint for endpoint in registered_endpoints}
    judiciary_entry = static.get("sep_000000000000000000000000000000000000000000000204")
    current_basic_law_binding = report.get("source_family") == "HKEL" and (
        _current_basic_law_binding(allowed_urls)
    )
    session = {
        "hkel-session-config-get": ("GET", _HKEL_TERMS_URL),
        "hkel-session-config-parse": ("LOCAL_PARSE", _HKEL_CONFIGURATION_GET),
        "hkel-session-config-post": ("POST", _HKEL_CONFIGURATION_ACTION),
    }
    if report.get("report_schema_version") in {"1.1.0", "1.2.0"}:
        for raw_attempt in cast("list[object]", report["transport_attempts"]):
            attempt = cast("dict[str, object]", raw_attempt)
            registered = static.get(cast("str", attempt["endpoint_id"]))
            if registered is not None and attempt.get("max_bytes") != registered.max_bytes:
                return False
            if (
                registered is None
                and cast("str", attempt["endpoint_id"]).startswith(
                    ("judiciary-year-", "judiciary-dis-")
                )
                and attempt.get("max_bytes") != _JUDICIARY_DYNAMIC_MAX_BYTES
            ):
                return False
    for raw_endpoint in cast("list[object]", report["endpoints"]):
        endpoint = cast("dict[str, object]", raw_endpoint)
        endpoint_id = cast("str", endpoint["endpoint_id"])
        endpoint_version = cast("str", endpoint["endpoint_version"])
        method = cast("str", endpoint["method"])
        requested_url = cast("str", endpoint["requested_url"])
        registered = static.get(endpoint_id)
        if registered is not None:
            if endpoint_id == _HKEL_CLIENT_CHECK_ENDPOINT_ID:
                if (
                    endpoint_version != registered.version
                    or registered.url != _HKEL_CLIENT_CHECK_URL
                    or registered.url not in allowed_urls
                    or requested_url != _HKEL_CLIENT_CHECK_COORDINATE
                    or method != "GET"
                ):
                    return False
                continue
            if (
                endpoint_version != registered.version
                or requested_url != registered.url
                or registered.url not in allowed_urls
                or method not in {item.value for item in registered.methods}
            ):
                return False
            continue
        session_binding = session.get(endpoint_id)
        if session_binding is not None:
            if endpoint_version != "1.0.0" or (method, requested_url) != session_binding:
                return False
            continue
        if method != "GET":
            return False
        derived_hash = hashlib.sha256(requested_url.encode()).hexdigest()[:24]
        if endpoint_id.startswith("basic-law-member-"):
            if endpoint_version != "1.0.0":
                return False
            try:
                if current_basic_law_binding:
                    require_basic_law_member_url(requested_url)
                else:
                    require_historical_basic_law_category_url(requested_url)
            except ValueError:
                return False
            if (
                endpoint_id != f"basic-law-member-{derived_hash}"
                or requested_url not in allowed_urls
            ):
                return False
            continue
        if endpoint_id.startswith("hkex-member-"):
            if endpoint_version != "1.0.0":
                return False
            try:
                require_hkex_member_url(requested_url)
            except ValueError:
                return False
            if endpoint_id != f"hkex-member-{derived_hash}":
                return False
            continue
        if endpoint_id.startswith("judiciary-year-"):
            match = re.fullmatch(
                r"judiciary-year-([0-9]{4})-(verification-)?page-([1-9][0-9]*)",
                endpoint_id,
            )
            if match is None:
                return False
            try:
                entry_version = judiciary_entry.version if judiciary_entry is not None else "1.0.1"
                result_version = _judiciary_result_contract_version(entry_version)
                if endpoint_version != result_version or (
                    match.group(2) is not None
                    and result_version
                    not in {
                        "1.0.6",
                        "1.0.7",
                        "1.0.8",
                        "1.0.9",
                        "1.0.10",
                        "1.0.11",
                        "1.0.12",
                    }
                ):
                    return False
                require_judiciary_year_result_url(
                    requested_url,
                    year=int(match.group(1)),
                    page=int(match.group(3)),
                    contract_version=entry_version,
                )
            except TypeError, ValueError:
                return False
            continue
        if endpoint_id.startswith("judiciary-dis-"):
            dis_id = endpoint_id.removeprefix("judiciary-dis-")
            if not dis_id.isdigit():
                return False
            try:
                entry_version = judiciary_entry.version if judiciary_entry is not None else "1.0.1"
                result_version = _judiciary_result_contract_version(entry_version)
                if endpoint_version != result_version:
                    return False
                if result_version == "1.0.1":
                    require_judiciary_result_frame_url(requested_url, dis_id=int(dis_id))
                elif result_version in {
                    "1.0.2",
                    "1.0.3",
                    "1.0.4",
                    "1.0.5",
                    "1.0.6",
                    "1.0.7",
                    "1.0.8",
                    "1.0.9",
                    "1.0.10",
                    "1.0.11",
                    "1.0.12",
                }:
                    require_judiciary_result_detail_frame_url(
                        requested_url,
                        dis_id=int(dis_id),
                        contract_version=result_version,
                    )
                else:
                    require_judiciary_detail_url(requested_url, dis_id=int(dis_id))
            except TypeError, ValueError:
                return False
            continue
        return False
    return True


@dataclass(frozen=True, slots=True)
class _RetainedAttemptState:
    """Validated zero-transport state for either a new attempt or exact replay."""

    predecessor_fingerprints: dict[str, str] | None
    restart_report: dict[str, object] | None
    judiciary_continuation: _JudiciaryContinuation | None = None


@dataclass(frozen=True, slots=True)
class _JudiciaryContinuation:
    """Exact verified outage prefix and its independently derived next request."""

    records: tuple[dict[str, object], ...]
    bodies: dict[str, bytes]
    fingerprints: dict[str, str]
    predecessor_accounting: dict[str, object]
    binding: dict[str, object]
    next_request: tuple[str, str, str, int]


def _projection_bodies(
    output_root: Path, report: dict[str, object]
) -> tuple[dict[str, str], dict[str, bytes]]:
    """Reread verified objects into the bounded representation used by writer rules."""
    fingerprints = _verified_predecessor_fingerprints(output_root, report)
    resolved_root = output_root.resolve(strict=True)
    bodies: dict[str, bytes] = {}
    try:
        for raw_endpoint in cast("list[object]", report["endpoints"]):
            endpoint = cast("dict[str, object]", raw_endpoint)
            endpoint_id = cast("str", endpoint["endpoint_id"])
            object_path = (resolved_root / cast("str", endpoint["object_key"])).resolve(strict=True)
            object_path.relative_to(resolved_root)
            if endpoint_id in _HKEL_ARCHIVE_ENDPOINT_IDS:
                with object_path.open("rb") as stream:
                    bodies[endpoint_id] = stream.read(4)
            else:
                bodies[endpoint_id] = object_path.read_bytes()
    except (OSError, ValueError) as error:
        raise PredecessorValidationError(_PREDECESSOR_EVIDENCE_READBACK_INVALID) from error
    return fingerprints, bodies


def _judiciary_semantic_stop_is_accepted_by_current_contract(  # noqa: PLR0913
    failed: dict[str, object],
    final_attempt: dict[str, object],
    body: bytes,
    *,
    current_registered_endpoints: tuple[OfficialEndpointContract, ...],
    historical_registered_endpoints: tuple[OfficialEndpointContract, ...],
    records: tuple[dict[str, object], ...],
    bodies: dict[str, bytes],
    observation_cutoff: str,
    record_urls_are_prevalidated: bool = False,
) -> bool:
    """Admit only an old listing stop repaired in today's full semantic context."""
    endpoint_id = failed.get("endpoint_id")
    match = (
        re.fullmatch(
            r"judiciary-year-([0-9]{4})-(verification-)?page-([1-9][0-9]*)",
            endpoint_id,
        )
        if type(endpoint_id) is str
        else None
    )
    try:
        entry = next(
            endpoint
            for endpoint in current_registered_endpoints
            if endpoint.endpoint_id == "sep_000000000000000000000000000000000000000000000204"
        )
        result_version = _judiciary_result_contract_version(entry.version)
        requested_url = cast("str", failed["requested_url"])
        if (
            match is None
            or failed.get("endpoint_version") == result_version
            or failed.get("method") != "GET"
            or final_attempt.get("endpoint_id") != endpoint_id
            or final_attempt.get("endpoint_version") != failed.get("endpoint_version")
            or final_attempt.get("method") != "GET"
            or final_attempt.get("requested_url") != requested_url
            or final_attempt.get("final_url") != requested_url
            or final_attempt.get("redirect_rejected") is not False
            or final_attempt.get("terminal_code") != "CAPTURED"
            or type(final_attempt.get("status")) is not int
            or not _HTTP_SUCCESS_MIN <= cast("int", final_attempt["status"]) < _HTTP_SUCCESS_MAX
            or final_attempt.get("media_type") != "text/html"
            or failed.get("status") != final_attempt.get("status")
            or failed.get("media_type") != final_attempt.get("media_type")
            or failed.get("byte_length") != final_attempt.get("byte_length")
            or failed.get("body_fingerprint") != final_attempt.get("body_fingerprint")
            or failed.get("object_key") != final_attempt.get("object_key")
        ):
            return False
        year = int(match.group(1))
        page = int(match.group(3))
        require_judiciary_year_result_url(
            requested_url,
            year=year,
            page=page,
            contract_version=entry.version,
        )
        parsed = parse_judiciary_year_result_page(
            body,
            year=year,
            page=page,
            contract_version=result_version,
        )
        if parsed.advertised_next_page is not None:
            build_judiciary_next_result_url(
                requested_url,
                result_page=parsed,
                form_contract_version=entry.version,
            )
        replay_records = {cast("str", record["endpoint_id"]): record for record in records}
        replay_terminals = dict.fromkeys(replay_records, "CAPTURED")
        _procedures, _dynamic, next_request = _replay_judiciary_procedures(
            bodies=dict(bodies),
            terminals=replay_terminals,
            records=replay_records,
            registered_endpoints=historical_registered_endpoints,
            observation_cutoff=observation_cutoff,
            observation_stop={"code": "REQUEST_BUDGET_EXHAUSTED"},
            result_contract_version_override=result_version,
            record_urls_are_prevalidated=record_urls_are_prevalidated,
        )
        if next_request is None:
            return False
    except KeyError, StopIteration, TypeError, ValueError:
        return False
    return True


def _judiciary_writer_semantic_fingerprints(
    output_root: Path,
    report: dict[str, object],
    *,
    registered_endpoints: tuple[OfficialEndpointContract, ...],
    allowed_urls: frozenset[str],
    continuation_urls_are_prevalidated: bool,
) -> dict[str, str]:
    """Replay either one contract or a recursively URL-validated continuation."""
    continuation = type(report.get("continuation_binding")) is dict
    if continuation != continuation_urls_are_prevalidated:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if not continuation:
        return _writer_semantic_fingerprints(
            output_root,
            report,
            registered_endpoints=registered_endpoints,
            allowed_urls=allowed_urls,
        )
    try:
        report_entry = next(
            endpoint
            for endpoint in registered_endpoints
            if endpoint.endpoint_id == "sep_000000000000000000000000000000000000000000000204"
        )
    except StopIteration as error:
        raise PredecessorValidationError(_PREDECESSOR_REPORT_MALFORMED) from error
    return _writer_semantic_fingerprints(
        output_root,
        report,
        registered_endpoints=registered_endpoints,
        allowed_urls=allowed_urls,
        report_urls_are_prevalidated=True,
        judiciary_result_contract_version_override=_judiciary_result_contract_version(
            report_entry.version
        ),
    )


def _judiciary_outage_continuation(  # noqa: PLR0913 - closed eligibility proof.
    output_root: Path,
    report_path: Path,
    report: dict[str, object],
    *,
    registered_endpoints: tuple[OfficialEndpointContract, ...],
    current_registered_endpoints: tuple[OfficialEndpointContract, ...],
    continuation_urls_are_prevalidated: bool = False,
    allowed_urls: frozenset[str],
    continuation_authority_fingerprint: str,
    continuation_execution_fingerprint: str,
) -> _JudiciaryContinuation:
    """Verify one resumable Judiciary transport or repaired-parser tip from bytes."""
    try:
        raw_report = report_path.read_bytes()
    except OSError as error:
        raise PredecessorValidationError(_PREDECESSOR_REPORT_MALFORMED) from error
    report_sha256 = hashlib.sha256(raw_report).hexdigest()
    if report.get("source_family") != "JUDICIARY" or report.get("report_schema_version") not in {
        "1.1.0",
        "1.2.0",
    }:
        _predecessor_fail("PREDECESSOR_REPORT_BINDING_INVALID")
    fingerprints = _judiciary_writer_semantic_fingerprints(
        output_root,
        report,
        registered_endpoints=registered_endpoints,
        allowed_urls=allowed_urls,
        continuation_urls_are_prevalidated=continuation_urls_are_prevalidated,
    )
    _verified, bodies = _projection_bodies(output_root, report)
    raw_records = cast("list[object]", report["endpoints"])
    raw_attempts = cast("list[object]", report["transport_attempts"])
    if not raw_records or not raw_attempts:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    records = tuple(cast("dict[str, object]", item) for item in raw_records)
    prefix = records[:-1]
    failed = records[-1]
    final_attempt = cast("dict[str, object]", raw_attempts[-1])
    exact_maintenance = maintenance_outage_facts(
        status=cast("int", final_attempt.get("status")),
        body_byte_length=cast("int", final_attempt.get("byte_length")),
        body_fingerprint=cast("str", final_attempt.get("body_fingerprint")),
        media_type=cast("str", final_attempt.get("media_type")),
        final_url=cast("str | None", final_attempt.get("final_url")),
        redirect_rejected=cast("bool", final_attempt.get("redirect_rejected")),
        requested_url=cast("str", final_attempt.get("requested_url")),
    )
    semantic_contract_stop = (
        failed.get("terminal_code") == "SOURCE_CONTRACT_CHANGED"
        and final_attempt.get("terminal_code") == "CAPTURED"
        and _judiciary_semantic_stop_is_accepted_by_current_contract(
            failed,
            final_attempt,
            bodies[cast("str", failed.get("endpoint_id"))],
            current_registered_endpoints=current_registered_endpoints,
            historical_registered_endpoints=registered_endpoints,
            records=records,
            bodies=bodies,
            observation_cutoff=cast("str", report["observation_cutoff"]),
            record_urls_are_prevalidated=continuation_urls_are_prevalidated,
        )
    )
    if (
        any(item.get("terminal_code") != "CAPTURED" for item in prefix)
        or failed.get("terminal_code") not in {"OUTAGE", "SOURCE_CONTRACT_CHANGED"}
        or (
            failed.get("terminal_code") == "SOURCE_CONTRACT_CHANGED"
            and not exact_maintenance
            and not semantic_contract_stop
        )
        or final_attempt.get("endpoint_id") != failed.get("endpoint_id")
        or final_attempt.get("requested_url") != failed.get("requested_url")
        or final_attempt.get("terminal_code") not in {"OUTAGE", "CAPTURED"}
        or (
            final_attempt.get("terminal_code") == "CAPTURED"
            and not exact_maintenance
            and not semantic_contract_stop
        )
        or report.get("result") not in {"SOURCE_OUTAGE", "SOURCE_CONTRACT_CHANGED"}
        or report.get("observation_stop") is not None
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    prefix_records = {cast("str", item["endpoint_id"]): item for item in prefix}
    prefix_terminals = {
        endpoint_id: cast("str", item["terminal_code"])
        for endpoint_id, item in prefix_records.items()
    }
    prefix_bodies_all = {endpoint_id: bodies[endpoint_id] for endpoint_id in prefix_records}
    try:
        _procedures, _dynamic, derived_next = _replay_judiciary_procedures(
            bodies=prefix_bodies_all,
            terminals=prefix_terminals,
            records=prefix_records,
            registered_endpoints=registered_endpoints,
            observation_cutoff=cast("str", report["observation_cutoff"]),
            observation_stop={"code": "REQUEST_BUDGET_EXHAUSTED"},
            record_urls_are_prevalidated=continuation_urls_are_prevalidated,
        )
    except (KeyError, StopIteration, TypeError, ValueError) as error:
        raise PredecessorValidationError(_PREDECESSOR_REPORT_MALFORMED) from error
    if derived_next is None:
        static = tuple(
            endpoint
            for endpoint in registered_endpoints
            if endpoint.endpoint_id not in _PROCEDURE_ONLY_ENDPOINT_IDS
        )
        if len(prefix) >= len(static):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        expected = static[len(prefix)]
        derived_next = (
            expected.endpoint_id,
            expected.version,
            "GET",
            expected.url,
            expected.max_bytes,
        )
    next_request = (
        derived_next[0],
        derived_next[1],
        derived_next[3],
        derived_next[4],
    )
    if (
        failed.get("endpoint_id"),
        failed.get("endpoint_version"),
        failed.get("method"),
        failed.get("requested_url"),
    ) != derived_next[:4]:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    accounting_key = (
        "cumulative_observation_accounting"
        if report.get("report_schema_version") == "1.2.0"
        else "observation_accounting"
    )
    accounting = cast("dict[str, object]", report[accounting_key])
    if (
        cast("int", accounting["request_starts"]) >= _JUDICIARY_REQUEST_START_LIMIT
        or cast("int", accounting["retained_response_bytes"]) >= _JUDICIARY_RETAINED_BYTE_LIMIT
        or cast("float", accounting["elapsed_seconds"]) >= _JUDICIARY_ELAPSED_SECONDS_LIMIT
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    prefix_fingerprints = {
        cast("str", item["endpoint_id"]): fingerprints[cast("str", item["endpoint_id"])]
        for item in prefix
    }
    prefix_bodies = {
        cast("str", item["endpoint_id"]): bodies[cast("str", item["endpoint_id"])]
        for item in prefix
    }
    binding: dict[str, object] = {
        "continuation_authority_manifest_fingerprint": continuation_authority_fingerprint,
        "continuation_execution_authorization_fingerprint": continuation_execution_fingerprint,
        "next_request": {
            "endpoint_id": next_request[0],
            "endpoint_version": next_request[1],
            "max_bytes": next_request[3],
            "method": "GET",
            "requested_url": next_request[2],
        },
        "predecessor_attempt_id": report["attempt_id"],
        "predecessor_observation_accounting": accounting,
        "predecessor_report_fingerprint": "sha256:" + report_sha256,
        "prefix_endpoint_count": len(prefix),
        "prefix_endpoints_fingerprint": _digest(_canonical(list(prefix))),
    }
    return _JudiciaryContinuation(
        prefix,
        prefix_bodies,
        prefix_fingerprints,
        dict(accounting),
        binding,
        next_request,
    )


def _rebind_judiciary_continuation_to_current_contract(
    continuation: _JudiciaryContinuation,
    *,
    registered_endpoints: tuple[OfficialEndpointContract, ...],
) -> _JudiciaryContinuation:
    """Keep a verified historical prefix while binding its new suffix to today's grammar."""
    entry = next(
        endpoint
        for endpoint in registered_endpoints
        if endpoint.endpoint_id == "sep_000000000000000000000000000000000000000000000204"
    )
    result_version = _judiciary_result_contract_version(entry.version)
    endpoint_id, _historical_version, requested_url, max_bytes = continuation.next_request
    next_request = (endpoint_id, result_version, requested_url, max_bytes)
    binding = dict(continuation.binding)
    binding["next_request"] = {
        "endpoint_id": endpoint_id,
        "endpoint_version": result_version,
        "max_bytes": max_bytes,
        "method": "GET",
        "requested_url": requested_url,
    }
    return replace(continuation, binding=binding, next_request=next_request)


def _judiciary_continuation_child_endpoints(
    child: dict[str, object],
    *,
    default_endpoints: tuple[OfficialEndpointContract, ...],
) -> tuple[OfficialEndpointContract, ...]:
    """Select the child's form contract from its exact bound result version."""
    attempt_id = cast("str", child["attempt_id"])
    historical_version = _HISTORICAL_JUDICIARY_ENTRY_CONTRACT_VERSIONS.get(attempt_id)
    binding = cast("dict[str, object]", child["continuation_binding"])
    next_request = cast("dict[str, object]", binding["next_request"])
    result_version = cast("str", next_request["endpoint_version"])
    if historical_version is not None:
        endpoints = _registered_endpoints(
            "JUDICIARY", judiciary_endpoint_204_version=historical_version
        )
        if _judiciary_result_contract_version(historical_version) != result_version:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        return endpoints
    candidates = (default_endpoints, _registered_endpoints("JUDICIARY"))
    matches: dict[str, tuple[OfficialEndpointContract, ...]] = {}
    for endpoints in candidates:
        entry = next(
            endpoint
            for endpoint in endpoints
            if endpoint.endpoint_id == "sep_000000000000000000000000000000000000000000000204"
        )
        if _judiciary_result_contract_version(entry.version) == result_version:
            matches[entry.version] = endpoints
    if len(matches) != 1:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    return next(iter(matches.values()))


def _retained_hkel_stage_terminal(
    endpoint: dict[str, object], body: bytes, *, max_bytes: int
) -> str:
    """Rederive one HKeL session terminal solely from its sanitized retained stage facts."""
    expected = {
        _HKEL_CLIENT_CHECK_ENDPOINT_ID: ("CAPABILITY_GET", _HKEL_CLIENT_CHECK_COORDINATE),
        "hkel-session-config-get": ("CONFIG_GET", _HKEL_CONFIGURATION_GET),
        "hkel-session-config-parse": ("CONFIG_PARSE", _HKEL_CONFIGURATION_GET),
        "hkel-session-config-post": ("CONFIG_POST", _HKEL_CONFIGURATION_ACTION),
    }
    endpoint_id = cast("str", endpoint["endpoint_id"])
    try:
        expected_stage_id, expected_final_url = expected[endpoint_id]
        document = parse_json_bytes(body, max_bytes=_MAX_HKEL_COMPARISON_BYTES)
        if type(document) is not dict or frozenset(document) != frozenset(
            {"observed_byte_length", "stable"}
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        observed_length = document.get("observed_byte_length")
        stable = document.get("stable")
        stable_keys = {
            "anti_forgery_control_present",
            "attempted",
            "configuration_action",
            "configuration_field_count",
            "derived_terminal_code",
            "final_url",
            "media_type",
            "redirect_rejected",
            "stage_id",
            "status",
            "terminal_assertion_consistent",
            "terminal_code",
        }
        if endpoint_id == _HKEL_CLIENT_CHECK_ENDPOINT_ID:
            stable_keys.add("endpoint_contract_fingerprint")
        if (
            type(observed_length) is not int
            or observed_length < 0
            or type(stable) is not dict
            or frozenset(stable) != frozenset(stable_keys)
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        facts = cast("dict[str, object]", stable)
        if (
            endpoint_id == _HKEL_CLIENT_CHECK_ENDPOINT_ID
            and facts.get("endpoint_contract_fingerprint")
            != _HKEL_CLIENT_CHECK_CONTRACT_FINGERPRINT
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        asserted = (
            facts.get("derived_terminal_code")
            if facts.get("terminal_assertion_consistent") is True
            else "INCONSISTENT_ASSERTION"
        )
        stage = HkelSessionStage(
            cast("str", facts.get("stage_id")),
            cast("str", asserted),
            cast("int", facts.get("status")),
            cast("str", facts.get("media_type")),
            cast("str | None", facts.get("final_url")),
            observed_length,
            cast("bool", facts.get("redirect_rejected")),
            cast("str | None", facts.get("configuration_action")),
            cast("int | None", facts.get("configuration_field_count")),
            cast("bool | None", facts.get("anti_forgery_control_present")),
            cast("bool", facts.get("attempted")),
        )
        typed, derived, effective, consistent = _validate_hkel_stage(
            stage,
            expected_stage_id=expected_stage_id,
            expected_final_url=expected_final_url,
            max_bytes=max_bytes,
        )
        regenerated, _comparison = _hkel_stage_documents(
            typed,
            derived_terminal=derived,
            effective_terminal=effective,
            assertion_consistent=consistent,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PredecessorValidationError(_PREDECESSOR_REPORT_MALFORMED) from error
    if (
        regenerated != body
        or endpoint.get("status") != stage.status
        or endpoint.get("media_type") != "application/json"
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    return effective


def _retained_response_terminal(endpoint: dict[str, object], body: bytes, *, max_bytes: int) -> str:
    """Rederive the ordinary response terminal from retained bytes and response facts."""
    status = cast("int", endpoint["status"])
    byte_length = cast("int", endpoint["byte_length"])
    if byte_length > max_bytes:
        return "TRUNCATED"
    if not _HTTP_SUCCESS_MIN <= status < _HTTP_SUCCESS_MAX:
        return "OUTAGE"
    if byte_length == 0:
        return "EMPTY_RESPONSE"
    if not body:
        _predecessor_fail(_PREDECESSOR_EVIDENCE_READBACK_INVALID)
    return "CAPTURED"


def _stopped_judiciary_procedures(
    terminals: dict[str, str], stop_code: str
) -> list[dict[str, object]]:
    """Derive the only incomplete Judiciary procedure terminals for a controller stop."""
    return [
        {
            "declared_member_count": (
                1
                if terminals.get("sep_000000000000000000000000000000000000000000000201")
                == "CAPTURED"
                else 0
            ),
            "source_id": "HK-CASE-HKLII-DISCOVERY",
            "terminal_code": (
                "COMPLETE"
                if terminals.get("sep_000000000000000000000000000000000000000000000201")
                == "CAPTURED"
                else "INCOMPLETE"
            ),
        },
        {
            "declared_member_count": 0,
            "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
            "terminal_code": (
                "OBSERVATION_EXECUTION_FAILURE"
                if stop_code == "OBSERVATION_EXECUTION_FAILURE"
                else "BUDGET_EXHAUSTED"
            ),
        },
    ]


def _judiciary_stop_requires_changed_observation(report: dict[str, object]) -> bool:
    """Treat every retained bounded Judiciary stop as an incomplete changed observation."""
    observation_stop = report.get("observation_stop")
    if type(observation_stop) is not dict:
        return False
    typed_stop = cast("dict[str, object]", observation_stop)
    return report.get("source_family") == "JUDICIARY" and typed_stop.get("code") in {
        "REQUEST_BUDGET_EXHAUSTED",
        "BYTE_BUDGET_EXHAUSTED",
        "ELAPSED_TIME_BUDGET_EXHAUSTED",
        "OBSERVATION_EXECUTION_FAILURE",
    }


def _replay_judiciary_procedures(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    bodies: dict[str, bytes],
    terminals: dict[str, str],
    records: dict[str, dict[str, object]],
    registered_endpoints: tuple[OfficialEndpointContract, ...],
    observation_cutoff: str,
    observation_stop: dict[str, object] | None = None,
    result_contract_version_override: str | None = None,
    record_urls_are_prevalidated: bool = False,
) -> tuple[list[dict[str, object]], set[str], tuple[str, str, str, str, int] | None]:
    """Rederive the exact year/page/detail writer procedure from retained facts."""
    static_ids = {
        item.endpoint_id
        for item in registered_endpoints
        if item.endpoint_id not in _PROCEDURE_ONLY_ENDPOINT_IDS
    }
    dynamic_ids = set(records) - static_ids
    record_order = tuple(records)
    static_order = tuple(
        item.endpoint_id
        for item in registered_endpoints
        if item.endpoint_id not in _PROCEDURE_ONLY_ENDPOINT_IDS
    )
    static_seen = tuple(item for item in record_order if item in static_ids)
    dynamic_order = tuple(item for item in record_order if item not in static_ids)
    if (
        static_seen != static_order[: len(static_seen)]
        or record_order[: len(static_seen)] != static_seen
        or any(item in static_ids for item in record_order[len(static_seen) :])
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if observation_stop is not None:
        stop_code = observation_stop.get("code")
        if type(stop_code) is not str or stop_code not in {
            "REQUEST_BUDGET_EXHAUSTED",
            "BYTE_BUDGET_EXHAUSTED",
            "ELAPSED_TIME_BUDGET_EXHAUSTED",
            "OBSERVATION_EXECUTION_FAILURE",
        }:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        if len(static_seen) != len(static_order):
            if dynamic_ids:
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
            return _stopped_judiciary_procedures(terminals, stop_code), set(), None
    if not all(terminals.get(item) == "CAPTURED" for item in static_ids):
        if dynamic_ids:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        return _source_procedures("JUDICIARY", bodies, terminals), set(), None
    entry_id = "sep_000000000000000000000000000000000000000000000204"
    entry = next(item for item in registered_endpoints if item.endpoint_id == entry_id)
    entry_url = entry.url
    entry_contract_version = entry.version
    result_contract_version = (
        _judiciary_result_contract_version(entry_contract_version)
        if result_contract_version_override is None
        else result_contract_version_override
    )
    partitions: list[JudiciaryYearPartition] = []
    expected_dynamic: set[str] = set()
    traversal_failed = False
    inventory_contract_changed = False
    partial_stop = False
    expected_dynamic_order: list[str] = []
    next_request: tuple[str, str, str, str, int] | None = None
    years = _judiciary_years(observation_cutoff)
    if result_contract_version in {
        "1.0.6",
        "1.0.7",
        "1.0.8",
        "1.0.9",
        "1.0.10",
        "1.0.11",
        "1.0.12",
    }:
        page_id = entry_id
        verification_partitions: list[JudiciaryYearPartition] = []
        try:
            for verification in (False, True):
                pass_partitions: list[JudiciaryYearPartition] = []
                for year in years:
                    expected_url = build_judiciary_year_result_url(
                        bodies[entry_id],
                        entry_url=entry_url,
                        year=year,
                        page=1,
                        contract_version=entry_contract_version,
                    )
                    parsed_pages: list[JudiciaryYearResultPage] = []
                    page_number = 1
                    while True:
                        page_id = (
                            f"judiciary-year-{year}-verification-page-{page_number}"
                            if verification
                            else f"judiciary-year-{year}-page-{page_number}"
                        )
                        page_record = records.get(page_id)
                        if page_record is None:
                            if observation_stop is None:
                                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                            next_request = (
                                page_id,
                                result_contract_version,
                                "GET",
                                expected_url,
                                _JUDICIARY_DYNAMIC_MAX_BYTES,
                            )
                            partial_stop = True
                            break
                        expected_dynamic.add(page_id)
                        expected_dynamic_order.append(page_id)
                        if (
                            not record_urls_are_prevalidated
                            and page_record.get("requested_url") != expected_url
                        ):
                            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                        if terminals[page_id] != "CAPTURED":
                            traversal_failed = True
                            break
                        parsed_page = parse_judiciary_year_result_page(
                            bodies[page_id],
                            year=year,
                            page=page_number,
                            contract_version=result_contract_version,
                        )
                        parsed_pages.append(parsed_page)
                        if parsed_page.advertised_next_page is None:
                            break
                        expected_url = build_judiciary_next_result_url(
                            expected_url,
                            result_page=parsed_page,
                            form_contract_version=entry_contract_version,
                        )
                        page_number = parsed_page.advertised_next_page
                    if partial_stop or traversal_failed:
                        break
                    pass_partitions.append(
                        reconcile_judiciary_year_partition(
                            tuple(parsed_pages), contract_version=result_contract_version
                        )
                    )
                if partial_stop or traversal_failed:
                    break
                try:
                    pass_snapshot = _judiciary_inventory_snapshot(pass_partitions)
                except ValueError:
                    inventory_contract_changed = True
                    break
                if verification:
                    verification_partitions = pass_partitions
                    if pass_snapshot != _judiciary_inventory_snapshot(partitions):
                        inventory_contract_changed = True
                        break
                else:
                    partitions = pass_partitions
            if not partial_stop and not traversal_failed and not inventory_contract_changed:
                if len(verification_partitions) != len(partitions):
                    inventory_contract_changed = True
                else:
                    for partition in partitions:
                        for dis_id, artifact_url in zip(
                            partition.in_scope_dis_ids, partition.artifact_urls, strict=True
                        ):
                            detail_id = f"judiciary-dis-{dis_id}"
                            detail_record = records.get(detail_id)
                            if detail_record is None:
                                if observation_stop is None:
                                    _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                                next_request = (
                                    detail_id,
                                    result_contract_version,
                                    "GET",
                                    artifact_url,
                                    _JUDICIARY_DYNAMIC_MAX_BYTES,
                                )
                                partial_stop = True
                                break
                            expected_dynamic.add(detail_id)
                            expected_dynamic_order.append(detail_id)
                            if (
                                not record_urls_are_prevalidated
                                and detail_record.get("requested_url") != artifact_url
                            ):
                                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                            if terminals[detail_id] != "CAPTURED":
                                traversal_failed = True
                                break
                        if partial_stop or traversal_failed:
                            break
        except PredecessorValidationError:
            raise
        except KeyError, StopIteration, TypeError, ValueError:
            if page_id == entry_id:
                terminals[entry_id] = "SOURCE_CONTRACT_CHANGED"
            else:
                terminals[page_id] = "SOURCE_CONTRACT_CHANGED"
            traversal_failed = True
    for year in (
        ()
        if result_contract_version
        in {"1.0.6", "1.0.7", "1.0.8", "1.0.9", "1.0.10", "1.0.11", "1.0.12"}
        else years
    ):
        page_id = f"judiciary-year-{year}-page-1"
        try:
            expected_url = build_judiciary_year_result_url(
                bodies[entry_id],
                entry_url=entry_url,
                year=year,
                page=1,
                contract_version=entry_contract_version,
            )
        except KeyError, StopIteration, TypeError, ValueError:
            # Mirror the writer: a retained static search-form parser failure
            # prevents the first dynamic request and reclassifies its owner.
            terminals[entry_id] = "SOURCE_CONTRACT_CHANGED"
            traversal_failed = True
            break
        try:
            parsed_pages: list[JudiciaryYearResultPage] = []
            page_number = 1
            while True:
                page_id = f"judiciary-year-{year}-page-{page_number}"
                page_record = records.get(page_id)
                if page_record is None:
                    if observation_stop is None:
                        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                    next_request = (
                        page_id,
                        result_contract_version,
                        "GET",
                        expected_url,
                        _JUDICIARY_DYNAMIC_MAX_BYTES,
                    )
                    partial_stop = True
                    break
                expected_dynamic.add(page_id)
                expected_dynamic_order.append(page_id)
                if (
                    not record_urls_are_prevalidated
                    and page_record.get("requested_url") != expected_url
                ):
                    _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                if terminals[page_id] != "CAPTURED":
                    traversal_failed = True
                    break
                parsed_page = parse_judiciary_year_result_page(
                    bodies[page_id],
                    year=year,
                    page=page_number,
                    contract_version=result_contract_version,
                )
                parsed_pages.append(parsed_page)
                if result_contract_version not in {
                    "1.0.2",
                    "1.0.3",
                    "1.0.4",
                    "1.0.5",
                    "1.0.6",
                    "1.0.7",
                    "1.0.8",
                    "1.0.9",
                    "1.0.10",
                    "1.0.11",
                    "1.0.12",
                }:
                    if parsed_page.reported_pages != 1:
                        terminals[page_id] = "SOURCE_CONTRACT_CHANGED"
                        traversal_failed = True
                    break
                if parsed_page.advertised_next_page is None:
                    break
                expected_url = build_judiciary_next_result_url(
                    expected_url,
                    result_page=parsed_page,
                    form_contract_version=entry_contract_version,
                )
                page_number = parsed_page.advertised_next_page
            if partial_stop or traversal_failed:
                break
            partition = reconcile_judiciary_year_partition(
                tuple(parsed_pages), contract_version=result_contract_version
            )
            if result_contract_version in {
                "1.0.6",
                "1.0.7",
                "1.0.8",
                "1.0.9",
                "1.0.10",
                "1.0.11",
                "1.0.12",
            }:
                expected_url = build_judiciary_year_result_url(
                    bodies[entry_id],
                    entry_url=entry_url,
                    year=year,
                    page=1,
                    contract_version=entry_contract_version,
                )
                verification_pages: list[JudiciaryYearResultPage] = []
                page_number = 1
                while True:
                    page_id = f"judiciary-year-{year}-verification-page-{page_number}"
                    page_record = records.get(page_id)
                    if page_record is None:
                        if observation_stop is None:
                            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                        next_request = (
                            page_id,
                            result_contract_version,
                            "GET",
                            expected_url,
                            _JUDICIARY_DYNAMIC_MAX_BYTES,
                        )
                        partial_stop = True
                        break
                    expected_dynamic.add(page_id)
                    expected_dynamic_order.append(page_id)
                    if (
                        not record_urls_are_prevalidated
                        and page_record.get("requested_url") != expected_url
                    ):
                        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                    if terminals[page_id] != "CAPTURED":
                        traversal_failed = True
                        break
                    parsed_page = parse_judiciary_year_result_page(
                        bodies[page_id],
                        year=year,
                        page=page_number,
                        contract_version=result_contract_version,
                    )
                    verification_pages.append(parsed_page)
                    if parsed_page.advertised_next_page is None:
                        break
                    expected_url = build_judiciary_next_result_url(
                        expected_url,
                        result_page=parsed_page,
                        form_contract_version=entry_contract_version,
                    )
                    page_number = parsed_page.advertised_next_page
                if partial_stop or traversal_failed:
                    break
                verification_partition = reconcile_judiciary_year_partition(
                    tuple(verification_pages), contract_version=result_contract_version
                )
                if _judiciary_partition_snapshot(partition) != _judiciary_partition_snapshot(
                    verification_partition
                ):
                    inventory_contract_changed = True
                    break
            for dis_id, artifact_url in zip(
                partition.in_scope_dis_ids, partition.artifact_urls, strict=True
            ):
                detail_id = f"judiciary-dis-{dis_id}"
                detail_record = records.get(detail_id)
                if detail_record is None:
                    if observation_stop is None:
                        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                    next_request = (
                        detail_id,
                        result_contract_version,
                        "GET",
                        artifact_url,
                        _JUDICIARY_DYNAMIC_MAX_BYTES,
                    )
                    partial_stop = True
                    break
                expected_dynamic.add(detail_id)
                expected_dynamic_order.append(detail_id)
                if (
                    not record_urls_are_prevalidated
                    and detail_record.get("requested_url") != artifact_url
                ):
                    _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                if terminals[detail_id] != "CAPTURED":
                    traversal_failed = True
                    break
            if partial_stop or traversal_failed:
                break
            partitions.append(partition)
        except PredecessorValidationError:
            raise
        except KeyError, StopIteration, TypeError, ValueError:
            terminals[page_id] = "SOURCE_CONTRACT_CHANGED"
            traversal_failed = True
            break
    if partial_stop:
        traversal_failed = True
    if dynamic_ids != expected_dynamic or dynamic_order != tuple(expected_dynamic_order):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if observation_stop is not None and (
        not partial_stop
        or any(terminals[endpoint_id] != "CAPTURED" for endpoint_id in expected_dynamic)
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    in_scope_count = sum(len(partition.in_scope_dis_ids) for partition in partitions)
    frame_content_unverified = (
        result_contract_version
        in {
            "1.0.1",
            "1.0.2",
            "1.0.3",
            "1.0.4",
            "1.0.5",
            "1.0.6",
            "1.0.7",
            "1.0.8",
            "1.0.9",
            "1.0.10",
            "1.0.11",
            "1.0.12",
        }
        and in_scope_count > 0
    )
    if observation_stop is not None:
        return (
            _stopped_judiciary_procedures(terminals, cast("str", observation_stop["code"])),
            expected_dynamic,
            next_request,
        )
    return (
        [
            {
                "declared_member_count": 1,
                "source_id": "HK-CASE-HKLII-DISCOVERY",
                "terminal_code": "COMPLETE",
            },
            {
                "declared_member_count": 0 if inventory_contract_changed else in_scope_count,
                "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
                "terminal_code": (
                    "SOURCE_CONTRACT_CHANGED"
                    if inventory_contract_changed
                    else (
                        "INCOMPLETE" if traversal_failed or frame_content_unverified else "COMPLETE"
                    )
                ),
            },
        ],
        expected_dynamic,
        None,
    )


def _replay_hkex_procedures(  # noqa: C901, PLR0912, PLR0915
    *,
    bodies: dict[str, bytes],
    terminals: dict[str, str],
    records: dict[str, dict[str, object]],
    registered_endpoints: tuple[OfficialEndpointContract, ...],
) -> tuple[list[dict[str, object]], set[str]]:
    """Rederive HKEX catalogue/member/section/PDF writer semantics from retained facts."""
    static_ids = {
        item.endpoint_id
        for item in registered_endpoints
        if item.endpoint_id not in _PROCEDURE_ONLY_ENDPOINT_IDS
    }
    dynamic_ids = set(records) - static_ids
    if not all(terminals.get(item) == "CAPTURED" for item in static_ids):
        if dynamic_ids:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        return _source_procedures("HKEX", bodies, terminals), set()
    endpoint_by_id = {item.endpoint_id: item for item in registered_endpoints}
    catalogue_id = "sep_000000000000000000000000000000000000000000000309"
    try:
        catalogue = parse_hkex_catalogue(bodies[catalogue_id])
    except KeyError, ValueError:
        terminals[catalogue_id] = "SOURCE_CONTRACT_CHANGED"
        catalogue = None
    root_specs = (
        (f"sep_{0x303:048x}", f"sep_{0x314:048x}", "HK-REG-HKEX-FEES-RULES"),
        (f"sep_{0x304:048x}", f"sep_{0x314:048x}", "HK-REG-HKEX-FEES-RULES"),
        (f"sep_{0x305:048x}", f"sep_{0x313:048x}", "HK-REG-HKEX-REGULATORY-FORMS"),
        (f"sep_{0x306:048x}", f"sep_{0x313:048x}", "HK-REG-HKEX-REGULATORY-FORMS"),
        (f"sep_{0x307:048x}", f"sep_{0x315:048x}", "HK-REG-HKEX-RULE-UPDATES"),
        (f"sep_{0x308:048x}", f"sep_{0x316:048x}", "HK-REG-HKEX-RULE-UPDATES"),
    )
    member_counts: dict[str, int] = {}
    expected_dynamic: set[str] = set()
    hkex_failed = catalogue is None
    for root_id, entire_id, source_id in () if hkex_failed else root_specs:
        try:
            membership = parse_hkex_role_membership(
                bodies[root_id],
                root_url=endpoint_by_id[root_id].url,
                entire_section_url=endpoint_by_id[entire_id].url,
            )
            captured_urls = [endpoint_by_id[entire_id].url]
            for member_url in membership.member_urls:
                require_hkex_member_url(member_url)
                member_id = "hkex-member-" + hashlib.sha256(member_url.encode()).hexdigest()[:24]
                expected_dynamic.add(member_id)
                member_record = records.get(member_id)
                if member_record is None or member_record.get("requested_url") != member_url:
                    _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                if terminals[member_id] != "CAPTURED":
                    hkex_failed = True
                    break
                captured_urls.append(member_url)
            if hkex_failed:
                break
            complete = reconcile_hkex_role_capture(membership, tuple(captured_urls))
            member_counts[source_id] = (
                member_counts.get(source_id, 0) + complete.declared_member_count
            )
        except PredecessorValidationError:
            raise
        except KeyError, TypeError, ValueError:
            terminals[root_id] = "SOURCE_CONTRACT_CHANGED"
            hkex_failed = True
            break
    pdf_id = "sep_000000000000000000000000000000000000000000000317"
    try:
        for section_id, pdf_id in (
            (
                "sep_000000000000000000000000000000000000000000000315",
                "sep_000000000000000000000000000000000000000000000317",
            ),
            (
                "sep_000000000000000000000000000000000000000000000316",
                "sep_000000000000000000000000000000000000000000000318",
            ),
        ):
            require_hkex_amendment_pdf_membership(
                bodies[section_id],
                section_url=endpoint_by_id[section_id].url,
                pdf_url=endpoint_by_id[pdf_id].url,
            )
        for pdf_id in (
            "sep_000000000000000000000000000000000000000000000311",
            "sep_000000000000000000000000000000000000000000000312",
            "sep_000000000000000000000000000000000000000000000317",
            "sep_000000000000000000000000000000000000000000000318",
        ):
            require_hkex_pdf(bodies[pdf_id])
    except KeyError, ValueError:
        terminals[pdf_id] = "SOURCE_CONTRACT_CHANGED"
        hkex_failed = True
    if dynamic_ids != expected_dynamic:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    source_counts = {
        "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS": 5,
        "HK-REG-HKEX-FEES-RULES": member_counts.get("HK-REG-HKEX-FEES-RULES", 0),
        "HK-REG-HKEX-REGULATORY-FORMS": member_counts.get("HK-REG-HKEX-REGULATORY-FORMS", 0),
        "HK-REG-HKEX-RULE-UPDATES": member_counts.get("HK-REG-HKEX-RULE-UPDATES", 0),
        "HK-REG-HKEX-RULEBOOK-CATALOGUE": 0 if catalogue is None else len(catalogue.role_roots),
    }
    return (
        [
            {
                "declared_member_count": source_counts[source.source_id],
                "source_id": source.source_id,
                "terminal_code": "INCOMPLETE" if hkex_failed else "COMPLETE",
            }
            for source in load_hk_regulatory_source_register().sources
        ],
        expected_dynamic,
    )


def _historical_hkel_specification_procedure(
    bodies: dict[str, bytes], terminals: dict[str, str]
) -> dict[str, object]:
    """Rederive the exact byte-marker policy contract used by writer 2026-08-28.2."""
    specification_ids = (
        "sep_000000000000000000000000000000000000000000000035",
        "sep_000000000000000000000000000000000000000000000036",
        "sep_000000000000000000000000000000000000000000000037",
        "sep_000000000000000000000000000000000000000000000038",
        "sep_000000000000000000000000000000000000000000000039",
        "sep_00000000000000000000000000000000000000000000003a",
        "sep_000000000000000000000000000000000000000000000051",
    )
    required_markers = (
        b"april 2026",
        b"automatic extraction",
        b"mass replication",
        b"product/database",
        b"attribution",
        b"version",
        b"non-endorsement",
        b"indemnity",
        b"third-party rights",
    )
    try:
        if any(terminals.get(item) != "CAPTURED" for item in specification_ids):
            _fail("HKEL_SPECIFICATION_CAPTURE_INCOMPLETE")
        if any(not bodies[item].startswith(b"%PDF-") for item in specification_ids[1:4]):
            _fail("HKEL_SPECIFICATION_PDF_INVALID")
        combined = (bodies[specification_ids[-1]] + b" " + bodies[specification_ids[-2]]).lower()
        if any(marker not in combined for marker in required_markers):
            _fail("HKEL_HISTORICAL_POLICY_PAGE_INVALID")
        terminal = "COMPLETE"
    except KeyError, TypeError, ValueError:
        terminal = (
            "SOURCE_CONTRACT_CHANGED"
            if all(terminals.get(item) == "CAPTURED" for item in specification_ids)
            else "INCOMPLETE"
        )
    return {
        "declared_member_count": len(specification_ids) if terminal == "COMPLETE" else 0,
        "source_id": "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
        "terminal_code": terminal,
    }


def _writer_semantic_fingerprints(  # noqa: C901, PLR0912, PLR0913, PLR0915
    output_root: Path,
    report: dict[str, object],
    *,
    registered_endpoints: tuple[OfficialEndpointContract, ...],
    allowed_urls: frozenset[str],
    historical_hkel_writer: bool = False,
    historical_judiciary_writer: bool = False,
    report_urls_are_prevalidated: bool = False,
    judiciary_result_contract_version_override: str | None = None,
) -> dict[str, str]:
    """Project one report through the writer's parsers without trusting stored outcomes."""
    source_family = cast("str", report["source_family"])
    if source_family == "HKEX" and report.get("report_schema_version") == "2.0.0":
        if (
            historical_hkel_writer
            or historical_judiciary_writer
            or report_urls_are_prevalidated
            or judiciary_result_contract_version_override is not None
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        try:
            replay_hkex_role_aware_report(
                report,
                output_root=output_root,
                endpoints=registered_endpoints,
            )
        except _HKEXRoleAwareEvidenceReadbackError as error:
            raise PredecessorValidationError(_PREDECESSOR_EVIDENCE_READBACK_INVALID) from error
        except ValueError as error:
            raise PredecessorValidationError(_PREDECESSOR_REPORT_MALFORMED) from error
        return _report_fingerprints(report)
    if report_urls_are_prevalidated and (
        source_family != "JUDICIARY"
        or judiciary_result_contract_version_override is None
        or historical_hkel_writer
        or historical_judiciary_writer
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if (
        not report_urls_are_prevalidated
        and not _current_report_urls_are_bound(
            report, registered_endpoints=registered_endpoints, allowed_urls=allowed_urls
        )
        and not historical_judiciary_writer
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    fingerprints, bodies = _projection_bodies(output_root, report)
    if historical_hkel_writer and source_family != "HKEL":
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if historical_judiciary_writer and source_family != "JUDICIARY":
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    records = {
        cast("str", endpoint["endpoint_id"]): endpoint
        for endpoint in (
            cast("dict[str, object]", item) for item in cast("list[object]", report["endpoints"])
        )
    }
    current_basic_law_binding = source_family == "HKEL" and (
        _current_basic_law_binding(allowed_urls)
    )
    static = {
        endpoint.endpoint_id: endpoint
        for endpoint in registered_endpoints
        if endpoint.endpoint_id not in _PROCEDURE_ONLY_ENDPOINT_IDS
        and not (
            source_family == "HKEL"
            and not current_basic_law_binding
            and endpoint.endpoint_id in {_BASIC_LAW_CONSTITUTION_ROOT_ID, _BASIC_LAW_TEXT_ROOT_ID}
        )
    }
    static_ids = tuple(sorted(static))
    missing_static = set(static_ids) - set(records)
    observation_stop = report.get("observation_stop")
    stopped_judiciary = source_family == "JUDICIARY" and type(observation_stop) is dict
    if missing_static and not stopped_judiciary:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    terminals: dict[str, str] = {}
    legacy_session_ids = (
        "hkel-session-config-get",
        "hkel-session-config-parse",
        "hkel-session-config-post",
    )
    session_ids = (*legacy_session_ids, _HKEL_CLIENT_CHECK_ENDPOINT_ID)
    terms = static.get("sep_000000000000000000000000000000000000000000000051")
    client_check = next(
        (
            item
            for item in registered_endpoints
            if item.endpoint_id == _HKEL_CLIENT_CHECK_ENDPOINT_ID
        ),
        None,
    )
    present_legacy = tuple(
        endpoint_id for endpoint_id in legacy_session_ids if endpoint_id in records
    )
    capability_present = _HKEL_CLIENT_CHECK_ENDPOINT_ID in records
    current_direct_binding = (
        source_family == "HKEL"
        and client_check is not None
        and client_check.url == _HKEL_CLIENT_CHECK_URL
        and client_check.url in allowed_urls
    )
    if (
        (present_legacy and len(present_legacy) != len(legacy_session_ids))
        or (present_legacy and capability_present)
        or (current_direct_binding and (present_legacy or not capability_present))
        or (not current_direct_binding and capability_present)
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if present_legacy:
        if source_family != "HKEL" or terms is None:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        for endpoint_id in present_legacy:
            terminals[endpoint_id] = _retained_hkel_stage_terminal(
                records[endpoint_id], bodies[endpoint_id], max_bytes=terms.max_bytes
            )
    if capability_present:
        if source_family != "HKEL" or client_check is None:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        terminals[_HKEL_CLIENT_CHECK_ENDPOINT_ID] = _retained_hkel_stage_terminal(
            records[_HKEL_CLIENT_CHECK_ENDPOINT_ID],
            bodies[_HKEL_CLIENT_CHECK_ENDPOINT_ID],
            max_bytes=client_check.max_bytes,
        )
    present_sessions = present_legacy or (
        (_HKEL_CLIENT_CHECK_ENDPOINT_ID,) if capability_present else ()
    )
    session_ready = (
        bool(present_legacy) and all(terminals[item] == "CAPTURED" for item in present_legacy)
    ) or (capability_present and terminals[_HKEL_CLIENT_CHECK_ENDPOINT_ID] == "CAPTURED")
    for endpoint_id, endpoint in static.items():
        if endpoint_id not in records:
            continue
        record = records[endpoint_id]
        body = bodies[endpoint_id]
        if endpoint.access_mode.value == "BROWSER_SESSION":
            if source_family == "GLD":
                terminal = "CHALLENGE_AUTHORITY_REQUIRED"
            elif source_family == "HKEL" and not session_ready:
                terminal = "SESSION_PROCEDURE_NOT_IMPLEMENTED"
            else:
                terminal = _retained_response_terminal(record, body, max_bytes=endpoint.max_bytes)
        else:
            terminal = _retained_response_terminal(record, body, max_bytes=endpoint.max_bytes)
        terminals[endpoint_id] = terminal
    dynamic_ids = set(records) - set(static_ids) - set(session_ids)
    for endpoint_id in sorted(dynamic_ids):
        terminals[endpoint_id] = _retained_response_terminal(
            records[endpoint_id], bodies[endpoint_id], max_bytes=_JUDICIARY_DYNAMIC_MAX_BYTES
        )
    if source_family == "JUDICIARY":
        stopped_attempt: dict[str, object] | None = None
        if report.get("report_schema_version") in {"1.1.0", "1.2.0"}:
            final_attempts: dict[str, dict[str, object]] = {}
            for raw_attempt in cast("list[object]", report["transport_attempts"]):
                attempt = cast("dict[str, object]", raw_attempt)
                endpoint_id = cast("str", attempt["endpoint_id"])
                if endpoint_id in records:
                    final_attempts[endpoint_id] = attempt
            for endpoint_id, attempt in final_attempts.items():
                physical_terminal = attempt.get("terminal_code")
                if physical_terminal != "CAPTURED":
                    terminals[endpoint_id] = cast("str", physical_terminal)
            stopped_attempts = [
                cast("dict[str, object]", item)
                for item in cast("list[object]", report["transport_attempts"])
                if cast("str", cast("dict[str, object]", item)["endpoint_id"]) not in records
            ]
            if len(stopped_attempts) > 1:
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
            stopped_attempt = stopped_attempts[0] if stopped_attempts else None
        static_order = tuple(static)
        static_seen = tuple(endpoint_id for endpoint_id in records if endpoint_id in static)
        if stopped_attempt is not None and len(static_seen) < len(static_order):
            expected_static = static[static_order[len(static_seen)]]
            if (
                stopped_attempt.get("endpoint_id"),
                stopped_attempt.get("endpoint_version"),
                stopped_attempt.get("method"),
                stopped_attempt.get("requested_url"),
                stopped_attempt.get("max_bytes"),
            ) != (
                expected_static.endpoint_id,
                expected_static.version,
                "GET",
                expected_static.url,
                expected_static.max_bytes,
            ):
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        procedures, _expected, dynamic_stop_request = _replay_judiciary_procedures(
            bodies=bodies,
            terminals=terminals,
            records=records,
            registered_endpoints=registered_endpoints,
            observation_cutoff=cast("str", report["observation_cutoff"]),
            observation_stop=cast("dict[str, object] | None", observation_stop),
            result_contract_version_override=judiciary_result_contract_version_override,
            record_urls_are_prevalidated=report_urls_are_prevalidated,
        )
        if (
            stopped_attempt is not None
            and len(static_seen) == len(static_order)
            and (
                dynamic_stop_request is None
                or (
                    stopped_attempt.get("endpoint_id"),
                    stopped_attempt.get("endpoint_version"),
                    stopped_attempt.get("method"),
                    stopped_attempt.get("requested_url"),
                    stopped_attempt.get("max_bytes"),
                )
                != dynamic_stop_request
            )
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    elif source_family == "HKEX":
        procedures, _expected = _replay_hkex_procedures(
            bodies=bodies,
            terminals=terminals,
            records=records,
            registered_endpoints=registered_endpoints,
        )
    else:
        if source_family == "HKEL":
            expected_dynamic: set[str] = set()
            readiness_ids = (*static_ids, *present_sessions)
            if all(terminals[item] == "CAPTURED" for item in readiness_ids):
                try:
                    if current_basic_law_binding:
                        membership = parse_basic_law_membership(
                            bodies[_BASIC_LAW_CONSTITUTION_ROOT_ID],
                            bodies[_BASIC_LAW_TEXT_ROOT_ID],
                            constitution_root_url=CONSTITUTION_ROOT_URL,
                            basic_law_root_url=BASIC_LAW_ROOT_URL,
                        )
                    else:
                        root_id = "sep_000000000000000000000000000000000000000000000050"
                        membership = parse_historical_basic_law_root_membership(
                            bodies[root_id],
                            root_url="https://www.basiclaw.gov.hk/en/index/index.html",
                        )
                    for member_url in membership.member_urls:
                        if current_basic_law_binding:
                            require_basic_law_member_url(member_url)
                        else:
                            require_historical_basic_law_category_url(member_url)
                        if member_url not in allowed_urls:
                            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                        member_id = _basic_law_member_endpoint_id(member_url)
                        if member_id not in static:
                            expected_dynamic.add(member_id)
                        member = records.get(member_id)
                        if member is None or member.get("requested_url") != member_url:
                            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
                        if current_basic_law_binding and terminals[member_id] == "CAPTURED":
                            try:
                                validate_basic_law_content_page(
                                    bodies[member_id],
                                    url=member_url,
                                    media_type=cast("str", member.get("media_type")),
                                )
                            except TypeError, ValueError:
                                terminals[member_id] = "SOURCE_CONTRACT_CHANGED"
                        if terminals[member_id] != "CAPTURED":
                            break
                except PredecessorValidationError:
                    raise
                except KeyError, TypeError, ValueError:
                    contract_root_id = (
                        _BASIC_LAW_CONSTITUTION_ROOT_ID
                        if current_basic_law_binding
                        else "sep_000000000000000000000000000000000000000000000050"
                    )
                    terminals[contract_root_id] = "SOURCE_CONTRACT_CHANGED"
                if dynamic_ids != expected_dynamic:
                    _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
            elif dynamic_ids:
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        elif dynamic_ids:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        procedures = _source_procedures(source_family, bodies, terminals)
        if source_family == "HKEL":
            procedures = [
                (
                    _basic_law_procedure(
                        bodies,
                        terminals,
                        current_binding=current_basic_law_binding,
                    )
                    if item["source_id"] == "HK-LEG-BASIC-LAW-PORTAL"
                    else _historical_hkel_specification_procedure(bodies, terminals)
                    if historical_hkel_writer
                    and item["source_id"] == "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS"
                    else item
                )
                for item in procedures
            ]
    claimed_terminals = {
        endpoint_id: cast("str", record["terminal_code"]) for endpoint_id, record in records.items()
    }
    counts: dict[str, int] = {}
    for terminal in terminals.values():
        counts[terminal] = counts.get(terminal, 0) + 1
    if (
        terminals != claimed_terminals
        or dict(sorted(counts.items())) != report.get("endpoint_counts")
        or procedures != report.get("source_procedures")
        or _derived_report_result(counts, procedures) != report.get("result")
    ):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    return fingerprints


def _retained_attempt_state(  # noqa: C901, PLR0912, PLR0913, PLR0915 - closed verifier.
    output_root: Path,
    attempt_id: str,
    predecessor_attempt_id: str | None,
    *,
    source_family: str,
    observation_cutoff: str,
    authority_manifest_fingerprint: str,
    execution_authorization_fingerprint: str,
    allow_legacy_unbound_report: bool,
    registered_endpoints: tuple[OfficialEndpointContract, ...],
    allowed_urls: frozenset[str],
) -> _RetainedAttemptState:
    reports: dict[str, dict[str, object]] = {}
    report_paths: dict[str, Path] = {}
    bindings: dict[str, tuple[str, str, str, str, str | None]] = {}
    predecessors: dict[str, str | None] = {}
    compatible_reports: dict[str, dict[str, object]] = {}
    compatible_referenced_predecessors: set[str] = set()
    required_binding = (
        source_family,
        observation_cutoff,
        authority_manifest_fingerprint,
        _AUTHORITY,
        execution_authorization_fingerprint,
    )

    def binding_matches(
        binding: tuple[str, str, str, str, str | None],
    ) -> bool:
        return binding == required_binding or (
            allow_legacy_unbound_report
            and binding[:4] == required_binding[:4]
            and binding[4] is None
        )

    def judiciary_report_endpoints(
        report: dict[str, object],
    ) -> tuple[OfficialEndpointContract, ...]:
        """Resolve one report's own exact form contract from pins or its bridge."""
        if source_family != "JUDICIARY" or report.get("source_family") != "JUDICIARY":
            return registered_endpoints
        if type(report.get("continuation_binding")) is dict:
            return _judiciary_continuation_child_endpoints(
                report,
                default_endpoints=registered_endpoints,
            )
        entry_version = _HISTORICAL_JUDICIARY_ENTRY_CONTRACT_VERSIONS.get(
            cast("str", report["attempt_id"])
        )
        if entry_version is None:
            entry_version = _judiciary_report_entry_contract_version_if_reached(report)
        return (
            registered_endpoints
            if entry_version is None
            else _registered_endpoints(
                "JUDICIARY",
                judiciary_endpoint_204_version=entry_version,
            )
        )

    judiciary_url_binding_cache: dict[tuple[str, int], bool] = {}

    def judiciary_report_urls_are_bound(  # noqa: C901 - exact iterative fail-closed walk.
        report: dict[str, object],
        records: list[object] | None = None,
    ) -> bool:
        """Validate each inherited segment iteratively under its owning contract."""
        selected = cast("list[object]", report["endpoints"]) if records is None else records
        current = report
        seen: set[str] = set()
        visited: list[tuple[str, int]] = []
        while True:
            attempt = current.get("attempt_id")
            current_records = cast("list[object]", current["endpoints"])
            if (
                type(attempt) is not str
                or attempt in seen
                or len(selected) > len(current_records)
                or _canonical(selected) != _canonical(current_records[: len(selected)])
            ):
                return False
            key = (attempt, len(selected))
            if judiciary_url_binding_cache.get(key) is True:
                for visited_key in visited:
                    judiciary_url_binding_cache[visited_key] = True
                return True
            seen.add(attempt)
            visited.append(key)
            current_endpoints = judiciary_report_endpoints(current)
            binding = current.get("continuation_binding")
            selected_is_full_report = len(selected) == len(current_records)
            if type(binding) is not dict:
                selected_report = dict(current)
                selected_report["endpoints"] = selected
                if not selected_is_full_report:
                    selected_report["transport_attempts"] = []
                valid = _current_report_urls_are_bound(
                    selected_report,
                    registered_endpoints=current_endpoints,
                    allowed_urls=allowed_urls,
                )
                if valid:
                    for visited_key in visited:
                        judiciary_url_binding_cache[visited_key] = True
                return valid
            typed_binding = cast("dict[str, object]", binding)
            predecessor_id = typed_binding.get("predecessor_attempt_id")
            predecessor = reports.get(cast("str", predecessor_id))
            prefix_count = typed_binding.get("prefix_endpoint_count")
            if (
                type(predecessor_id) is not str
                or predecessor is None
                or type(prefix_count) is not int
                or prefix_count < 0
            ):
                return False
            inherited_count = min(len(selected), prefix_count)
            suffix_report = dict(current)
            suffix_report["endpoints"] = selected[inherited_count:]
            if not selected_is_full_report:
                suffix_report["transport_attempts"] = []
            if not _current_report_urls_are_bound(
                suffix_report,
                registered_endpoints=current_endpoints,
                allowed_urls=allowed_urls,
            ):
                return False
            predecessor_records = cast("list[object]", predecessor["endpoints"])
            inherited = selected[:inherited_count]
            if _canonical(inherited) != _canonical(predecessor_records[:inherited_count]):
                return False
            current = predecessor
            selected = inherited

    def semantic_fingerprints(
        report: dict[str, object],
    ) -> dict[str, str]:
        continuation_binding = report.get("continuation_binding")
        historical_continuation_parent: str | None = None
        if type(continuation_binding) is dict:
            candidate = cast("dict[str, object]", continuation_binding).get(
                "predecessor_attempt_id"
            )
            if type(candidate) is str:
                historical_continuation_parent = candidate
        if (
            source_family == "JUDICIARY"
            and report.get("report_schema_version") == "1.2.0"
            and historical_continuation_parent is not None
        ):
            if report.get("attempt_id") != attempt_id:
                # Each ancestor's bridge is rederived in the lineage pass. Its objects
                # must still be reread, but only the requested restart needs its mixed
                # historical-prefix/current-suffix writer projection repeated here.
                return _verified_predecessor_fingerprints(output_root, report)
            report_endpoints = judiciary_report_endpoints(report)
            if not judiciary_report_urls_are_bound(report):
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
            report_entry = next(
                endpoint
                for endpoint in report_endpoints
                if endpoint.endpoint_id == "sep_000000000000000000000000000000000000000000000204"
            )
            return _writer_semantic_fingerprints(
                output_root,
                report,
                registered_endpoints=report_endpoints,
                allowed_urls=allowed_urls,
                report_urls_are_prevalidated=True,
                judiciary_result_contract_version_override=_judiciary_result_contract_version(
                    report_entry.version
                ),
            )
        report_endpoints = judiciary_report_endpoints(report)
        if (
            allow_legacy_unbound_report
            and report.get("execution_authorization_fingerprint") is None
        ):
            return _writer_semantic_fingerprints(
                output_root,
                report,
                registered_endpoints=report_endpoints,
                allowed_urls=allowed_urls,
                historical_hkel_writer=True,
            )
        return _writer_semantic_fingerprints(
            output_root,
            report,
            registered_endpoints=report_endpoints,
            allowed_urls=allowed_urls,
            historical_judiciary_writer=(
                allow_legacy_unbound_report and source_family == "JUDICIARY"
            ),
        )

    for path in sorted((output_root / "attempts").glob("*/report.json")):
        try:
            loaded: object = json.loads(path.read_bytes())
        except (OSError, json.JSONDecodeError) as error:
            raise PredecessorValidationError(_PREDECESSOR_REPORT_MALFORMED) from error
        if type(loaded) is not dict:
            _predecessor_fail("PREDECESSOR_REPORT_MALFORMED")
        report = cast("dict[str, object]", loaded)
        report_attempt = report.get("attempt_id")
        if type(report_attempt) is not str or report_attempt != path.parent.name:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        report_binding = _predecessor_report_binding(report)
        report_predecessor = cast("str | None", report["predecessor_attempt_id"])
        reports[report_attempt] = report
        report_paths[report_attempt] = path
        bindings[report_attempt] = report_binding
        predecessors[report_attempt] = report_predecessor
        if binding_matches(report_binding):
            compatible_reports[report_attempt] = report
            if report_predecessor is not None:
                compatible_referenced_predecessors.add(report_predecessor)
    child_counts: dict[str, int] = {}
    for report_attempt, report_predecessor in predecessors.items():
        if report_predecessor is None:
            continue
        predecessor = reports.get(report_predecessor)
        child = reports[report_attempt]
        continuation_bridge = (
            predecessor is not None
            and child.get("report_schema_version") == "1.2.0"
            and type(child.get("continuation_binding")) is dict
        )
        if predecessor is None or (
            bindings[report_predecessor] != bindings[report_attempt] and not continuation_bridge
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        if continuation_bridge:
            predecessor_endpoints = judiciary_report_endpoints(predecessor)
            child_endpoints = _judiciary_continuation_child_endpoints(
                child,
                default_endpoints=registered_endpoints,
            )
            expected_continuation = _judiciary_outage_continuation(
                output_root,
                report_paths[report_predecessor],
                predecessor,
                registered_endpoints=predecessor_endpoints,
                current_registered_endpoints=child_endpoints,
                continuation_urls_are_prevalidated=(
                    type(predecessor.get("continuation_binding")) is dict
                    and judiciary_report_urls_are_bound(predecessor)
                ),
                allowed_urls=allowed_urls,
                continuation_authority_fingerprint=cast(
                    "str", child["authority_manifest_fingerprint"]
                ),
                continuation_execution_fingerprint=cast(
                    "str", child["execution_authorization_fingerprint"]
                ),
            )
            expected_continuation = _rebind_judiciary_continuation_to_current_contract(
                expected_continuation,
                registered_endpoints=child_endpoints,
            )
            if _canonical(child.get("continuation_binding")) != _canonical(
                expected_continuation.binding
            ):
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        child_counts[report_predecessor] = child_counts.get(report_predecessor, 0) + 1
        if child_counts[report_predecessor] != 1:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        predecessor_fingerprints = _report_fingerprints(predecessor)
        report_fingerprints = _report_fingerprints(reports[report_attempt])
        expected_change = (
            "CHANGED_OBSERVED"
            if type(reports[report_attempt].get("continuation_binding")) is dict
            or _judiciary_stop_requires_changed_observation(reports[report_attempt])
            or predecessor_fingerprints != report_fingerprints
            else "NO_CHANGE_OBSERVED"
        )
        if reports[report_attempt].get("change_state") != expected_change:
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    for report_attempt in reports:
        seen: set[str] = set()
        cursor: str | None = report_attempt
        while cursor is not None:
            if cursor in seen:
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
            seen.add(cursor)
            cursor = predecessors[cursor]
    restart_report = reports.get(attempt_id)
    if restart_report is not None:
        if (
            not binding_matches(bindings[attempt_id])
            or restart_report.get("predecessor_attempt_id") != predecessor_attempt_id
        ):
            _predecessor_fail("PREDECESSOR_REPORT_BINDING_INVALID")
        cursor_report = restart_report
        cursor_fingerprints = semantic_fingerprints(cursor_report)
        while cursor_report.get("predecessor_attempt_id") is not None:
            cursor_predecessor_id = cast("str", cursor_report["predecessor_attempt_id"])
            cursor_predecessor = reports[cursor_predecessor_id]
            if not judiciary_report_urls_are_bound(cursor_predecessor):
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
            predecessor_fingerprints = semantic_fingerprints(cursor_predecessor)
            expected_change = (
                "CHANGED_OBSERVED"
                if type(cursor_report.get("continuation_binding")) is dict
                or _judiciary_stop_requires_changed_observation(cursor_report)
                or predecessor_fingerprints != cursor_fingerprints
                else "NO_CHANGE_OBSERVED"
            )
            if cursor_report.get("change_state") != expected_change:
                _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
            cursor_report = cursor_predecessor
            cursor_fingerprints = predecessor_fingerprints
        restart_urls_are_bound = (
            source_family == "HKEX" and restart_report.get("report_schema_version") == "2.0.0"
        ) or judiciary_report_urls_are_bound(restart_report)
        if not restart_urls_are_bound and not (
            allow_legacy_unbound_report and source_family == "JUDICIARY"
        ):
            _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
        return _RetainedAttemptState(None, restart_report)
    if predecessor_attempt_id is None:
        if set(compatible_reports) - compatible_referenced_predecessors:
            _predecessor_fail("PREDECESSOR_ATTEMPT_REQUIRED")
        return _RetainedAttemptState(None, None)
    if (
        _ATTEMPT_ID.fullmatch(predecessor_attempt_id) is None
        or predecessor_attempt_id == attempt_id
    ):
        _predecessor_fail("PREDECESSOR_ATTEMPT_INVALID")
    predecessor = reports.get(predecessor_attempt_id)
    if predecessor is None:
        _predecessor_fail("PREDECESSOR_ATTEMPT_INVALID")
    is_judiciary_continuation = (
        source_family == "JUDICIARY"
        and predecessor.get("source_family") == "JUDICIARY"
        and predecessor.get("observation_cutoff") == observation_cutoff
        and bindings[predecessor_attempt_id] != required_binding
        and not allow_legacy_unbound_report
    )
    if not is_judiciary_continuation and (
        predecessor.get("source_family") != source_family
        or predecessor.get("observation_cutoff") != observation_cutoff
        or predecessor.get("authority_manifest_fingerprint") != authority_manifest_fingerprint
        or predecessor.get("authority_provenance") != _AUTHORITY
    ):
        _predecessor_fail("PREDECESSOR_REPORT_BINDING_INVALID")
    if predecessor_attempt_id in compatible_referenced_predecessors:
        _predecessor_fail("PREDECESSOR_ATTEMPT_INVALID")
    predecessor_endpoints = judiciary_report_endpoints(predecessor)
    if not judiciary_report_urls_are_bound(predecessor):
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    if is_judiciary_continuation:
        continuation = _judiciary_outage_continuation(
            output_root,
            report_paths[predecessor_attempt_id],
            predecessor,
            registered_endpoints=predecessor_endpoints,
            current_registered_endpoints=registered_endpoints,
            continuation_urls_are_prevalidated=(
                type(predecessor.get("continuation_binding")) is dict
            ),
            allowed_urls=allowed_urls,
            continuation_authority_fingerprint=authority_manifest_fingerprint,
            continuation_execution_fingerprint=execution_authorization_fingerprint,
        )
        continuation = _rebind_judiciary_continuation_to_current_contract(
            continuation,
            registered_endpoints=registered_endpoints,
        )
        return _RetainedAttemptState(None, None, continuation)
    return _RetainedAttemptState(semantic_fingerprints(predecessor), None)


def _current_basic_law_binding(allowed_urls: frozenset[str]) -> bool:
    """Select the exact 20-member authority without admitting a partial new binding."""
    present = frozenset(CURRENT_BASIC_LAW_MEMBER_URLS).intersection(allowed_urls)
    historical_overlap = frozenset(_BASIC_LAW_REUSED_ENDPOINTS)
    if present not in {historical_overlap, frozenset(CURRENT_BASIC_LAW_MEMBER_URLS)}:
        _predecessor_fail(_PREDECESSOR_REPORT_MALFORMED)
    return present == frozenset(CURRENT_BASIC_LAW_MEMBER_URLS)


def _basic_law_member_endpoint_id(member_url: str) -> str:
    return _BASIC_LAW_REUSED_ENDPOINTS.get(
        member_url,
        "basic-law-member-" + hashlib.sha256(member_url.encode()).hexdigest()[:24],
    )


def _basic_law_procedure(
    bodies: dict[str, bytes],
    terminals: dict[str, str],
    *,
    current_binding: bool,
) -> dict[str, object]:
    """Rederive either the exact current inventory or the former two-root writer result."""
    basic_count = 0
    basic_terminal = "INCOMPLETE"
    try:
        if current_binding:
            if any(
                terminals.get(endpoint_id) != "CAPTURED"
                for endpoint_id in (_BASIC_LAW_CONSTITUTION_ROOT_ID, _BASIC_LAW_TEXT_ROOT_ID)
            ):
                _fail("BASIC_LAW_ROOT_CAPTURE_INCOMPLETE")
            membership = parse_basic_law_membership(
                bodies[_BASIC_LAW_CONSTITUTION_ROOT_ID],
                bodies[_BASIC_LAW_TEXT_ROOT_ID],
                constitution_root_url=CONSTITUTION_ROOT_URL,
                basic_law_root_url=BASIC_LAW_ROOT_URL,
            )
        else:
            root_id = "sep_000000000000000000000000000000000000000000000050"
            if terminals.get(root_id) != "CAPTURED":
                _fail("BASIC_LAW_ROOT_CAPTURE_INCOMPLETE")
            membership = parse_historical_basic_law_root_membership(
                bodies[root_id], root_url="https://www.basiclaw.gov.hk/en/index/index.html"
            )
        member_terminals = tuple(
            terminals.get(_basic_law_member_endpoint_id(member_url))
            for member_url in membership.member_urls
        )
        if "SOURCE_CONTRACT_CHANGED" in member_terminals:
            basic_terminal = "SOURCE_CONTRACT_CHANGED"
        elif all(item == "CAPTURED" for item in member_terminals):
            basic_count = len(membership.member_urls)
            basic_terminal = "COMPLETE" if current_binding else "INCOMPLETE"
    except KeyError, TypeError, ValueError:
        roots_captured = (
            all(
                terminals.get(endpoint_id) == "CAPTURED"
                for endpoint_id in (_BASIC_LAW_CONSTITUTION_ROOT_ID, _BASIC_LAW_TEXT_ROOT_ID)
            )
            if current_binding
            else terminals.get("sep_000000000000000000000000000000000000000000000050") == "CAPTURED"
        )
        if roots_captured:
            basic_terminal = "SOURCE_CONTRACT_CHANGED"
    return {
        "declared_member_count": basic_count,
        "source_id": "HK-LEG-BASIC-LAW-PORTAL",
        "terminal_code": basic_terminal,
    }


def _source_procedures(  # noqa: C901 - closed family dispatcher.
    source_family: str,
    bodies: dict[str, bytes],
    terminals: dict[str, str],
) -> list[dict[str, object]]:
    """Evaluate only family procedures whose exact parser contract is implemented."""
    if source_family == "HKEL":
        results: list[dict[str, object]] = []
        inventory = None
        inventory_terminal = "INCOMPLETE"
        inventory_contract_ids = (
            "sep_000000000000000000000000000000000000000000000001",
            "sep_000000000000000000000000000000000000000000000002",
            "sep_000000000000000000000000000000000000000000000003",
            "sep_000000000000000000000000000000000000000000000009",
        )
        if all(terminals.get(item) == "CAPTURED" for item in inventory_contract_ids):
            try:
                english = parse_hkel_current_inventory_xml(
                    bodies[inventory_contract_ids[1]], language="en"
                )
                chinese = parse_hkel_current_inventory_xml(
                    bodies[inventory_contract_ids[2]], language="zh-Hant"
                )
                inventory = reconcile_hkel_current_inventories(english, chinese)
                required_data_ids = inventory.required_data_endpoint_ids
                if all(terminals.get(item) == "CAPTURED" for item in required_data_ids):
                    register = load_hk_legislation_source_register()
                    endpoint_urls = {item.endpoint_id: item.url for item in register.endpoints}
                    parse_hkel_dataset_catalogue(
                        bodies[inventory_contract_ids[0]],
                        expected_dataset_name="hk-doj-hkel-list-of-legislation-current",
                        required_urls=tuple(
                            endpoint_urls[f"sep_{value:048x}"] for value in range(2, 8)
                        ),
                    )
                    parse_hkel_dataset_catalogue(
                        bodies[inventory_contract_ids[3]],
                        expected_dataset_name="hk-doj-hkel-legislation-current",
                        required_urls=tuple(endpoint_urls[item] for item in required_data_ids),
                    )
                    if any(not bodies[item].startswith(b"PK") for item in required_data_ids):
                        _fail("HKEL_CURRENT_DATA_ARCHIVE_INVALID")
                    inventory_terminal = "COMPLETE"
            except KeyError, TypeError, ValueError:
                inventory = None
                inventory_terminal = "SOURCE_CONTRACT_CHANGED"
        results.extend(
            (
                {
                    "declared_member_count": 0 if inventory is None else len(inventory.chapter_ids),
                    "source_id": "HK-LEG-HKEL-CURRENT-INVENTORY",
                    "terminal_code": inventory_terminal,
                },
                {
                    "declared_member_count": (
                        0 if inventory is None else len(inventory.required_data_endpoint_ids)
                    ),
                    "source_id": "HK-LEG-HKEL-CURRENT-DATA",
                    "terminal_code": inventory_terminal,
                },
            )
        )
        editorial_ids = (
            "sep_000000000000000000000000000000000000000000000033",
            "sep_000000000000000000000000000000000000000000000034",
        )
        editorial_complete = all(terminals.get(item) == "CAPTURED" for item in editorial_ids)
        results.append(
            {
                "declared_member_count": len(editorial_ids) if editorial_complete else 0,
                "source_id": "HK-LEG-HKEL-EDITORIAL-RECORDS",
                "terminal_code": "COMPLETE" if editorial_complete else "INCOMPLETE",
            }
        )
        specification_ids = (
            "sep_000000000000000000000000000000000000000000000035",
            "sep_000000000000000000000000000000000000000000000036",
            "sep_000000000000000000000000000000000000000000000037",
            "sep_000000000000000000000000000000000000000000000038",
            "sep_000000000000000000000000000000000000000000000039",
            "sep_00000000000000000000000000000000000000000000003a",
            "sep_000000000000000000000000000000000000000000000051",
        )
        try:
            if any(terminals.get(item) != "CAPTURED" for item in specification_ids):
                _fail("HKEL_SPECIFICATION_CAPTURE_INCOMPLETE")
            if any(not bodies[item].startswith(b"%PDF-") for item in specification_ids[1:4]):
                _fail("HKEL_SPECIFICATION_PDF_INVALID")
            validate_hkel_policy_pages(bodies[specification_ids[-1]], bodies[specification_ids[-2]])
            specification_terminal = "COMPLETE"
        except KeyError, TypeError, ValueError:
            specification_terminal = (
                "SOURCE_CONTRACT_CHANGED"
                if all(terminals.get(item) == "CAPTURED" for item in specification_ids)
                else "INCOMPLETE"
            )
        results.append(
            {
                "declared_member_count": (
                    len(specification_ids) if specification_terminal == "COMPLETE" else 0
                ),
                "source_id": "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
                "terminal_code": specification_terminal,
            }
        )
        results.append(_basic_law_procedure(bodies, terminals, current_binding=True))
        return sorted(results, key=lambda item: cast("str", item["source_id"]))
    if source_family == "JUDICIARY":
        return [
            {
                "declared_member_count": (
                    1
                    if terminals.get("sep_000000000000000000000000000000000000000000000201")
                    == "CAPTURED"
                    else 0
                ),
                "source_id": "HK-CASE-HKLII-DISCOVERY",
                "terminal_code": (
                    "COMPLETE"
                    if terminals.get("sep_000000000000000000000000000000000000000000000201")
                    == "CAPTURED"
                    else "INCOMPLETE"
                ),
            },
            {
                "declared_member_count": 0,
                "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
                "terminal_code": "YEAR_PARTITION_TRAVERSAL_PENDING",
            },
        ]
    if source_family == "HKEX":
        register = load_hk_regulatory_source_register()
        return [
            {
                "declared_member_count": 0,
                "source_id": source.source_id,
                "terminal_code": "MEMBERSHIP_PARSER_PENDING",
            }
            for source in register.sources
        ]
    return [
        {
            "declared_member_count": 0,
            "source_id": "HK-LEG-GLD-EGAZETTE",
            "terminal_code": "CHALLENGE_AUTHORITY_REQUIRED",
        }
    ]


def _judiciary_years(observation_cutoff: str) -> range:
    """Derive the exact inclusive baseline years from the frozen observation cutoff."""
    cutoff = _parse_hong_kong_cutoff(observation_cutoff)
    if cutoff.year < _JUDICIARY_FIRST_YEAR:
        _fail(_OBSERVATION_CUTOFF_MALFORMED)
    return range(_JUDICIARY_FIRST_YEAR, cutoff.year + 1)


def _is_hkex_role_aware_endpoint_set(
    endpoints: tuple[OfficialEndpointContract, ...],
) -> bool:
    """Recognize only the reviewed contiguous 301..320 candidate register shape."""
    return tuple(item.endpoint_id for item in endpoints) == tuple(
        _hkex_endpoint_id(suffix) for suffix in range(301, 321)
    )


def execute_source_family(  # noqa: PLR0913
    *,
    authority_manifest: Path,
    source_family: str,
    output_root: Path,
    attempt_id: str,
    predecessor_attempt_id: str | None = None,
    observation_cutoff: str,
    repository_root: Path,
    transport: ReadOnlySourceTransport,
    authorization: ExecutionAuthorization | None = None,
    matrix_path: Path | None = None,
    judiciary_clock: Callable[[], float] | None = None,
    judiciary_sleeper: Callable[[float], None] | None = None,
    hkex_clock: Callable[[], float] | None = None,
    hkex_sleeper: Callable[[float], None] | None = None,
    attempt_claim: object | None = None,
) -> dict[str, object]:
    """Own one exact attempt identity before any replay or external effect."""
    if _ATTEMPT_ID.fullmatch(attempt_id) is None:
        _fail("ATTEMPT_ID_MALFORMED")
    _parse_hong_kong_cutoff(observation_cutoff)
    root = _safe_output_root(output_root, repository_root)
    if attempt_claim is None:
        with source_attempt_claim(
            output_root=output_root,
            attempt_id=attempt_id,
            repository_root=repository_root,
        ):
            return _execute_source_family_claimed(
                authority_manifest=authority_manifest,
                source_family=source_family,
                output_root=output_root,
                attempt_id=attempt_id,
                predecessor_attempt_id=predecessor_attempt_id,
                observation_cutoff=observation_cutoff,
                repository_root=repository_root,
                transport=transport,
                authorization=authorization,
                matrix_path=matrix_path,
                judiciary_clock=judiciary_clock,
                judiciary_sleeper=judiciary_sleeper,
                hkex_clock=hkex_clock,
                hkex_sleeper=hkex_sleeper,
            )
    _require_held_attempt_claim(attempt_claim, output_root=root, attempt_id=attempt_id)
    return _execute_source_family_claimed(
        authority_manifest=authority_manifest,
        source_family=source_family,
        output_root=output_root,
        attempt_id=attempt_id,
        predecessor_attempt_id=predecessor_attempt_id,
        observation_cutoff=observation_cutoff,
        repository_root=repository_root,
        transport=transport,
        authorization=authorization,
        matrix_path=matrix_path,
        judiciary_clock=judiciary_clock,
        judiciary_sleeper=judiciary_sleeper,
        hkex_clock=hkex_clock,
        hkex_sleeper=hkex_sleeper,
    )


def _execute_source_family_claimed(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    authority_manifest: Path,
    source_family: str,
    output_root: Path,
    attempt_id: str,
    predecessor_attempt_id: str | None = None,
    observation_cutoff: str,
    repository_root: Path,
    transport: ReadOnlySourceTransport,
    authorization: ExecutionAuthorization | None = None,
    matrix_path: Path | None = None,
    judiciary_clock: Callable[[], float] | None = None,
    judiciary_sleeper: Callable[[float], None] | None = None,
    hkex_clock: Callable[[], float] | None = None,
    hkex_sleeper: Callable[[float], None] | None = None,
) -> dict[str, object]:
    """Capture every exact registered endpoint and write its terminal manifest last."""
    if _ATTEMPT_ID.fullmatch(attempt_id) is None:
        _fail("ATTEMPT_ID_MALFORMED")
    _parse_hong_kong_cutoff(observation_cutoff)
    selected_matrix = (
        matrix_path
        if matrix_path is not None
        else repository_root
        / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    root = _safe_output_root(output_root, repository_root)
    report_path = root / "attempts" / attempt_id / "report.json"
    if type(authorization) is ExecutionAuthorization and authorization.historical_replay:
        issued_authorization = authorize_retained_replay(
            authority_manifest=authority_manifest,
            matrix=selected_matrix,
            output_root=output_root,
            source_family=source_family,
            observation_cutoff=observation_cutoff,
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor_attempt_id,
            repository_root=repository_root,
        )
    else:
        try:
            issued_authorization = authorize_execution(
                authority_manifest=authority_manifest,
                matrix=selected_matrix,
                output_root=output_root,
                source_family=source_family,
                observation_cutoff=observation_cutoff,
                repository_root=repository_root,
            )
        except ValueError:
            if authorization is not None or not report_path.is_file():
                raise
            issued_authorization = authorize_retained_replay(
                authority_manifest=authority_manifest,
                matrix=selected_matrix,
                output_root=output_root,
                source_family=source_family,
                observation_cutoff=observation_cutoff,
                attempt_id=attempt_id,
                predecessor_attempt_id=predecessor_attempt_id,
                repository_root=repository_root,
            )
    if authorization is not None and authorization != issued_authorization:
        _fail("EXECUTION_AUTHORIZATION_BINDING_INVALID")
    bound_authorization = issued_authorization
    if (
        type(bound_authorization) is not ExecutionAuthorization
        or bound_authorization.source_family != source_family
        or bound_authorization.observation_cutoff != observation_cutoff
    ):
        _fail("EXECUTION_AUTHORIZATION_BINDING_INVALID")
    provenance, authority_fingerprint = _authority_identity(authority_manifest)
    if bound_authorization.authority_manifest_fingerprint != authority_fingerprint:
        _fail("EXECUTION_AUTHORIZATION_BINDING_INVALID")
    endpoints = _registered_endpoints(
        source_family,
        judiciary_endpoint_204_version=(
            _HISTORICAL_JUDICIARY_ENTRY_CONTRACT_VERSIONS.get(attempt_id)
            if source_family == "JUDICIARY" and bound_authorization.historical_replay
            else None
        ),
        hkex_historical_attempt_id=(
            attempt_id
            if source_family == "HKEX" and bound_authorization.historical_replay
            else None
        ),
    )
    basic_law_authorized_urls = frozenset(CURRENT_BASIC_LAW_MEMBER_URLS).intersection(
        bound_authorization.allowed_urls
    )
    if source_family == "HKEL" and basic_law_authorized_urls not in {
        frozenset(_BASIC_LAW_REUSED_ENDPOINTS),
        frozenset(CURRENT_BASIC_LAW_MEMBER_URLS),
    }:
        _fail("EXECUTION_AUTHORIZATION_BINDING_INVALID")
    current_basic_law_binding = source_family == "HKEL" and (
        basic_law_authorized_urls == frozenset(CURRENT_BASIC_LAW_MEMBER_URLS)
    )
    required_urls = {
        item.url
        for item in endpoints
        if item.endpoint_id not in _PROCEDURE_ONLY_ENDPOINT_IDS
        and not (
            source_family == "HKEL"
            and not current_basic_law_binding
            and item.endpoint_id in {_BASIC_LAW_CONSTITUTION_ROOT_ID, _BASIC_LAW_TEXT_ROOT_ID}
        )
    }
    if (
        source_family == "JUDICIARY"
        and not bound_authorization.historical_replay
        and frozenset(bound_authorization.allowed_urls) != _current_judiciary_authorization_urls()
    ):
        _fail("EXECUTION_AUTHORIZATION_BINDING_INVALID")
    if source_family == "JUDICIARY" and bound_authorization.historical_replay:
        required_urls.remove(_JUDICIARY_CURRENT_LISTING_ENTRY_URL)
        required_urls.add(_JUDICIARY_CURRENT_LISTING_TARGET_URL)
    if not required_urls.issubset(bound_authorization.allowed_urls):
        _fail("EXECUTION_AUTHORIZATION_BINDING_INVALID")
    hkel_client_endpoint = next(
        (item for item in endpoints if item.endpoint_id == _HKEL_CLIENT_CHECK_ENDPOINT_ID),
        None,
    )
    hkel_client_check_admitted = (
        source_family == "HKEL"
        and hkel_client_endpoint is not None
        and hkel_client_endpoint.url in bound_authorization.allowed_urls
    )
    if hkel_client_check_admitted and (
        hkel_client_endpoint is None
        or hkel_client_endpoint.url != _validated_hkel_client_check_url()
    ):
        _fail("EXECUTION_AUTHORIZATION_BINDING_INVALID")
    if (
        source_family == "HKEL"
        and not hkel_client_check_admitted
        and not {
            _HKEL_CONFIGURATION_GET,
            _HKEL_CONFIGURATION_ACTION,
        }.issubset(bound_authorization.allowed_urls)
    ):
        _fail("EXECUTION_AUTHORIZATION_BINDING_INVALID")
    if isinstance(transport, UrllibReadOnlyTransport):
        capability = transport.redirect_capability
        if (
            type(capability) is not RedirectCapability
            or capability.allowed_urls != frozenset(bound_authorization.allowed_urls)
            or capability.allowed_transitions
            != _redirect_transitions(frozenset(bound_authorization.allowed_urls))
            or not capability.same_origin_only
        ):
            _fail("EXECUTION_AUTHORIZATION_BINDING_INVALID")
    retained_state = _retained_attempt_state(
        root,
        attempt_id,
        predecessor_attempt_id,
        source_family=source_family,
        observation_cutoff=observation_cutoff,
        authority_manifest_fingerprint=authority_fingerprint,
        execution_authorization_fingerprint=bound_authorization.binding_fingerprint,
        allow_legacy_unbound_report=bound_authorization.historical_replay,
        registered_endpoints=endpoints,
        allowed_urls=frozenset(bound_authorization.allowed_urls),
    )
    if retained_state.restart_report is not None:
        return retained_state.restart_report
    if (
        source_family == "HKEX"
        and not bound_authorization.historical_replay
        and predecessor_attempt_id is None
        and _is_hkex_role_aware_endpoint_set(endpoints)
    ):
        capture = capture_hkex_role_aware(
            endpoints=endpoints,
            transport=transport,
            clock=time.monotonic if hkex_clock is None else hkex_clock,
            sleeper=time.sleep if hkex_sleeper is None else hkex_sleeper,
        )
        return publish_hkex_role_aware_report(
            output_root=root,
            attempt_id=attempt_id,
            observation_cutoff=observation_cutoff,
            authority_manifest_fingerprint=authority_fingerprint,
            authority_provenance=provenance,
            execution_authorization_fingerprint=bound_authorization.binding_fingerprint,
            predecessor_attempt_id=predecessor_attempt_id,
            capture=capture,
        )
    judiciary_continuation = retained_state.judiciary_continuation
    predecessor_accounting = (
        judiciary_continuation.predecessor_accounting if judiciary_continuation is not None else {}
    )
    judiciary_observation = (
        _JudiciaryObservationController(
            time.monotonic if judiciary_clock is None else judiciary_clock,
            time.sleep if judiciary_sleeper is None else judiciary_sleeper,
            cumulative_request_starts_before_segment=cast(
                "int", predecessor_accounting.get("request_starts", 0)
            ),
            cumulative_retained_bytes_before_segment=cast(
                "int", predecessor_accounting.get("retained_response_bytes", 0)
            ),
            cumulative_elapsed_seconds_before_segment=cast(
                "float", predecessor_accounting.get("elapsed_seconds", 0.0)
            ),
        )
        if source_family == "JUDICIARY"
        else None
    )
    prior = retained_state.predecessor_fingerprints
    records: list[dict[str, object]] = (
        [dict(item) for item in judiciary_continuation.records]
        if judiciary_continuation is not None
        else []
    )
    transport_attempts: list[dict[str, object]] = []
    counts: dict[str, int] = {"CAPTURED": len(records)} if records else {}
    current_fingerprints: dict[str, str] = (
        dict(judiciary_continuation.fingerprints) if judiciary_continuation is not None else {}
    )
    bodies: dict[str, bytes] = (
        dict(judiciary_continuation.bodies) if judiciary_continuation is not None else {}
    )
    media_types: dict[str, str] = {
        cast("str", item["endpoint_id"]): cast("str", item["media_type"]) for item in records
    }
    terminals: dict[str, str] = {
        cast("str", item["endpoint_id"]): cast("str", item["terminal_code"]) for item in records
    }

    def retain_classified(  # noqa: PLR0913 - exact evidence leaves remain explicit.
        *,
        endpoint_id: str,
        endpoint_version: str,
        method: str,
        requested_url: str,
        response: CapturedResponse,
        terminal: str,
        comparison_body: bytes | None = None,
    ) -> tuple[bytes, str]:
        """Retain one response only after its terminal was independently derived."""
        body = response.body
        fingerprint = _digest(body)
        comparison_fingerprint = (
            fingerprint if comparison_body is None else _digest(comparison_body)
        )
        object_key = f"objects/{fingerprint.removeprefix('sha256:')}.bin"
        try:
            _write_immutable(root / object_key, body)
        except SourceEvidenceIntegrityError:
            raise
        except (OSError, TypeError, ValueError) as error:
            raise SourceEvidenceIntegrityError(_SOURCE_EVIDENCE_INTEGRITY_FAILURE) from error
        if comparison_body is not None:
            try:
                retained_comparison = _digest(
                    _read_hkel_comparison((root / object_key).read_bytes())
                )
            except SourceEvidenceIntegrityError:
                raise
            except (OSError, TypeError, ValueError) as error:
                raise SourceEvidenceIntegrityError(_SOURCE_EVIDENCE_INTEGRITY_FAILURE) from error
            if retained_comparison != _digest(comparison_body):
                _evidence_integrity_fail()
        counts[terminal] = counts.get(terminal, 0) + 1
        current_fingerprints[endpoint_id] = comparison_fingerprint
        bodies[endpoint_id] = body[:4] if endpoint_id in _HKEL_ARCHIVE_ENDPOINT_IDS else body
        media_types[endpoint_id] = response.media_type
        terminals[endpoint_id] = terminal
        record: dict[str, object] = {
            "body_fingerprint": fingerprint,
            "byte_length": len(body),
            "endpoint_id": endpoint_id,
            "endpoint_version": endpoint_version,
            "media_type": response.media_type,
            "method": method,
            "object_key": object_key,
            "requested_url": requested_url,
            "status": response.status,
            "terminal_code": terminal,
        }
        if comparison_body is not None:
            record["comparison_fingerprint"] = comparison_fingerprint
        records.append(record)
        return body, terminal

    def retain_response(  # noqa: PLR0913 - exact evidence leaves remain explicit.
        *,
        endpoint_id: str,
        endpoint_version: str,
        method: str,
        requested_url: str,
        max_bytes: int,
        response: CapturedResponse,
    ) -> tuple[bytes, str]:
        """Derive and retain one ordinary bounded response terminal."""
        terminal = _response_terminal(response, max_bytes=max_bytes)
        if response.final_url is not None and (
            urlsplit(response.final_url).hostname != urlsplit(requested_url).hostname
        ):
            terminal = "SOURCE_CONTRACT_CHANGED"
        return retain_classified(
            endpoint_id=endpoint_id,
            endpoint_version=endpoint_version,
            method=method,
            requested_url=requested_url,
            response=response,
            terminal=terminal,
        )

    def retain_transport_attempt(  # noqa: PLR0913 - physical evidence remains explicit.
        *,
        endpoint_id: str,
        endpoint_version: str,
        requested_url: str,
        max_bytes: int,
        attempt_number: int,
        start_elapsed_seconds: float,
        response: CapturedResponse,
    ) -> str:
        """Persist one returned Judiciary GET before deciding whether it may retry."""
        terminal = _physical_response_terminal(
            response, requested_url=requested_url, max_bytes=max_bytes
        )
        fingerprint = _digest(response.body)
        object_key = f"objects/{fingerprint.removeprefix('sha256:')}.bin"
        _write_immutable(root / object_key, response.body)
        transport_attempts.append(
            {
                "attempt_number": attempt_number,
                "body_fingerprint": fingerprint,
                "byte_length": len(response.body),
                "endpoint_id": endpoint_id,
                "endpoint_version": endpoint_version,
                "final_url": response.final_url,
                "max_bytes": max_bytes,
                "media_type": response.media_type,
                "method": "GET",
                "object_key": object_key,
                "redirect_rejected": response.redirect_rejected,
                "requested_url": requested_url,
                "sequence": len(transport_attempts) + 1,
                "start_elapsed_seconds": start_elapsed_seconds,
                "status": response.status,
                "terminal_code": terminal,
            }
        )
        return terminal

    def capture_url(  # noqa: C901, PLR0911 - closed physical-attempt/retry state machine.
        *, endpoint_id: str, endpoint_version: str, url: str, max_bytes: int
    ) -> tuple[bytes, str]:
        """Capture one registered or procedure-bound GET into the common immutable account."""
        retained_terminal = terminals.get(endpoint_id)
        if retained_terminal is not None:
            return bodies[endpoint_id], retained_terminal
        if judiciary_observation is not None and not judiciary_observation.before_request():
            return b"", "OBSERVATION_STOPPED"
        start_elapsed_seconds = (
            judiciary_observation.elapsed_seconds if judiciary_observation is not None else 0.0
        )
        try:
            response = transport.get(url=url, max_bytes=max_bytes)
        except OSError, TimeoutError, urllib.error.URLError:
            response = CapturedResponse(0, "application/octet-stream", b"", None)
        if judiciary_observation is not None and not judiciary_observation.accept_response(
            response.body
        ):
            return b"", "OBSERVATION_STOPPED"
        if source_family == "JUDICIARY" and not bound_authorization.historical_replay:
            if judiciary_observation is None:
                _fail("CAPTURE_ACCOUNTING_INVALID")
            retain_transport_attempt(
                endpoint_id=endpoint_id,
                endpoint_version=endpoint_version,
                requested_url=url,
                max_bytes=max_bytes,
                attempt_number=1,
                start_elapsed_seconds=start_elapsed_seconds,
                response=response,
            )
            if retry_eligible(
                status=response.status,
                body=response.body,
                media_type=response.media_type,
                final_url=response.final_url,
                redirect_rejected=response.redirect_rejected,
                requested_url=url,
                max_bytes=max_bytes,
            ):
                if not judiciary_observation.before_request():
                    return b"", "OBSERVATION_STOPPED"
                retry_start_elapsed_seconds = judiciary_observation.elapsed_seconds
                try:
                    response = transport.get(url=url, max_bytes=max_bytes)
                except OSError, TimeoutError, urllib.error.URLError:
                    response = CapturedResponse(0, "application/octet-stream", b"", None)
                if not judiciary_observation.accept_response(response.body):
                    return b"", "OBSERVATION_STOPPED"
                retain_transport_attempt(
                    endpoint_id=endpoint_id,
                    endpoint_version=endpoint_version,
                    requested_url=url,
                    max_bytes=max_bytes,
                    attempt_number=2,
                    start_elapsed_seconds=retry_start_elapsed_seconds,
                    response=response,
                )
            if maintenance_outage(
                status=response.status,
                body=response.body,
                media_type=response.media_type,
                final_url=response.final_url,
                redirect_rejected=response.redirect_rejected,
                requested_url=url,
            ):
                return retain_classified(
                    endpoint_id=endpoint_id,
                    endpoint_version=endpoint_version,
                    method="GET",
                    requested_url=url,
                    response=response,
                    terminal="OUTAGE",
                )
        if endpoint_id == _JUDICIARY_CURRENT_LISTING_ENTRY_ID and (
            response.final_url != _JUDICIARY_CURRENT_LISTING_TARGET_URL
        ):
            response = CapturedResponse(
                response.status,
                response.media_type,
                response.body,
                response.final_url,
                response.redirect_rejected,
            )
            return retain_classified(
                endpoint_id=endpoint_id,
                endpoint_version=endpoint_version,
                method="GET",
                requested_url=url,
                response=response,
                terminal="SOURCE_CONTRACT_CHANGED",
            )
        return retain_response(
            endpoint_id=endpoint_id,
            endpoint_version=endpoint_version,
            method="GET",
            requested_url=url,
            max_bytes=max_bytes,
            response=response,
        )

    def mark_contract_changed(endpoint_id: str) -> None:
        """Reclassify one already retained response when its strict parser rejects it."""
        previous = terminals.get(endpoint_id)
        if previous is None or previous == "SOURCE_CONTRACT_CHANGED":
            return
        counts[previous] -= 1
        if counts[previous] == 0:
            del counts[previous]
        counts["SOURCE_CONTRACT_CHANGED"] = counts.get("SOURCE_CONTRACT_CHANGED", 0) + 1
        terminals[endpoint_id] = "SOURCE_CONTRACT_CHANGED"
        for record in records:
            if record.get("endpoint_id") == endpoint_id:
                record["terminal_code"] = "SOURCE_CONTRACT_CHANGED"
                return
        _fail("CAPTURE_ACCOUNTING_INVALID")

    hkel_session_ready = False
    if source_family == "HKEL":
        configure = getattr(transport, "configure_hkel_session", None)
        terms_endpoint = next(
            (
                item
                for item in endpoints
                if item.endpoint_id == "sep_000000000000000000000000000000000000000000000051"
            ),
            None,
        )
        session_endpoint = hkel_client_endpoint if hkel_client_check_admitted else terms_endpoint
        if hkel_client_check_admitted and not callable(configure):
            _evidence_integrity_fail()
        if callable(configure) and terms_endpoint is not None and session_endpoint is not None:
            try:
                configured = configure(
                    url=session_endpoint.url,
                    max_bytes=session_endpoint.max_bytes,
                )
            except OSError, TimeoutError, urllib.error.URLError:
                configured = _hkel_transport_outage_capture(direct=hkel_client_check_admitted)
            if type(configured) is not HkelSessionCapture:
                _evidence_integrity_fail()
            if hkel_client_check_admitted != (configured.capability is not None):
                _evidence_integrity_fail()
            if configured.capability is not None:
                if not hkel_client_check_admitted:
                    _evidence_integrity_fail()
                stage_specs = (
                    (
                        _HKEL_CLIENT_CHECK_ENDPOINT_ID,
                        "GET",
                        _HKEL_CLIENT_CHECK_COORDINATE,
                        session_endpoint.url,
                        configured.capability,
                        "CAPABILITY_GET",
                        session_endpoint.version,
                        session_endpoint.max_bytes,
                    ),
                )
            else:
                stage_specs = (
                    (
                        "hkel-session-config-get",
                        "GET",
                        terms_endpoint.url,
                        _HKEL_CONFIGURATION_GET,
                        configured.initial,
                        "CONFIG_GET",
                        "1.0.0",
                        terms_endpoint.max_bytes,
                    ),
                    (
                        "hkel-session-config-parse",
                        "LOCAL_PARSE",
                        _HKEL_CONFIGURATION_GET,
                        _HKEL_CONFIGURATION_GET,
                        configured.parser,
                        "CONFIG_PARSE",
                        "1.0.0",
                        terms_endpoint.max_bytes,
                    ),
                    (
                        "hkel-session-config-post",
                        "POST",
                        _HKEL_CONFIGURATION_ACTION,
                        _HKEL_CONFIGURATION_ACTION,
                        configured.submission,
                        "CONFIG_POST",
                        "1.0.0",
                        terms_endpoint.max_bytes,
                    ),
                )
            session_terminals: list[str] = []
            for (
                endpoint_id,
                method,
                requested_url,
                expected_final_url,
                raw_stage,
                expected_stage_id,
                endpoint_version,
                stage_max_bytes,
            ) in stage_specs:
                (
                    stage,
                    derived_terminal,
                    effective_terminal,
                    assertion_consistent,
                ) = _validate_hkel_stage(
                    raw_stage,
                    expected_stage_id=expected_stage_id,
                    expected_final_url=expected_final_url,
                    max_bytes=stage_max_bytes,
                )
                evidence, comparison = _hkel_stage_documents(
                    stage,
                    derived_terminal=derived_terminal,
                    effective_terminal=effective_terminal,
                    assertion_consistent=assertion_consistent,
                )
                _, terminal = retain_classified(
                    endpoint_id=endpoint_id,
                    endpoint_version=endpoint_version,
                    method=method,
                    requested_url=requested_url,
                    response=CapturedResponse(
                        stage.status,
                        "application/json",
                        evidence,
                        stage.final_url,
                        stage.redirect_rejected,
                    ),
                    terminal=effective_terminal,
                    comparison_body=comparison,
                )
                session_terminals.append(terminal)
            hkel_session_ready = all(item == "CAPTURED" for item in session_terminals)

    for endpoint in endpoints:
        if judiciary_observation is not None and judiciary_observation.stop_code is not None:
            break
        endpoint_id = endpoint.endpoint_id
        if endpoint_id in _PROCEDURE_ONLY_ENDPOINT_IDS or (
            source_family == "HKEL"
            and not current_basic_law_binding
            and endpoint_id in {_BASIC_LAW_CONSTITUTION_ROOT_ID, _BASIC_LAW_TEXT_ROOT_ID}
        ):
            continue
        url = endpoint.url
        max_bytes = endpoint.max_bytes
        if endpoint.access_mode.value == "BROWSER_SESSION":
            if source_family == "HKEL" and hkel_session_ready:
                capture_url(
                    endpoint_id=endpoint_id,
                    endpoint_version=endpoint.version,
                    url=url,
                    max_bytes=max_bytes,
                )
                continue
            response = CapturedResponse(0, "application/octet-stream", b"", None)
            body = b""
            terminal = (
                "CHALLENGE_AUTHORITY_REQUIRED"
                if source_family == "GLD"
                else "SESSION_PROCEDURE_NOT_IMPLEMENTED"
            )
            fingerprint = _digest(body)
            object_key = f"objects/{fingerprint.removeprefix('sha256:')}.bin"
            _write_immutable(root / object_key, body)
            counts[terminal] = counts.get(terminal, 0) + 1
            current_fingerprints[endpoint_id] = fingerprint
            bodies[endpoint_id] = body
            terminals[endpoint_id] = terminal
            records.append(
                {
                    "body_fingerprint": fingerprint,
                    "byte_length": 0,
                    "endpoint_id": endpoint_id,
                    "endpoint_version": endpoint.version,
                    "media_type": response.media_type,
                    "method": "GET",
                    "object_key": object_key,
                    "requested_url": url,
                    "status": 0,
                    "terminal_code": terminal,
                }
            )
        else:
            capture_url(
                endpoint_id=endpoint_id,
                endpoint_version=endpoint.version,
                url=url,
                max_bytes=max_bytes,
            )
            if judiciary_observation is not None and judiciary_observation.stop_code is not None:
                break

    procedure_override: list[dict[str, object]] | None = None
    if (
        source_family == "JUDICIARY"
        and judiciary_observation is not None
        and (judiciary_observation.stop_code is not None)
    ):
        procedure_override = [
            {
                "declared_member_count": (
                    1
                    if terminals.get("sep_000000000000000000000000000000000000000000000201")
                    == "CAPTURED"
                    else 0
                ),
                "source_id": "HK-CASE-HKLII-DISCOVERY",
                "terminal_code": (
                    "COMPLETE"
                    if terminals.get("sep_000000000000000000000000000000000000000000000201")
                    == "CAPTURED"
                    else "INCOMPLETE"
                ),
            },
            {
                "declared_member_count": 0,
                "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
                "terminal_code": (
                    "OBSERVATION_EXECUTION_FAILURE"
                    if judiciary_observation.stop_code == "OBSERVATION_EXECUTION_FAILURE"
                    else "BUDGET_EXHAUSTED"
                ),
            },
        ]
    elif source_family == "JUDICIARY" and all(
        terminal == "CAPTURED" for terminal in terminals.values()
    ):
        entry_id = "sep_000000000000000000000000000000000000000000000204"
        partitions: list[JudiciaryYearPartition] = []
        traversal_failed = False
        inventory_contract_changed = False
        frame_content_unverified = False
        contract_endpoint_id = entry_id
        try:
            entry = next(item for item in endpoints if item.endpoint_id == entry_id)
            entry_url = entry.url
            entry_contract_version = entry.version
            result_contract_version = _judiciary_result_contract_version(entry_contract_version)
            years = _judiciary_years(observation_cutoff)
            if result_contract_version in {
                "1.0.6",
                "1.0.7",
                "1.0.8",
                "1.0.9",
                "1.0.10",
                "1.0.11",
                "1.0.12",
            }:
                verification_partitions: list[JudiciaryYearPartition] = []
                for verification in (False, True):
                    pass_partitions: list[JudiciaryYearPartition] = []
                    for year in years:
                        current_url = build_judiciary_year_result_url(
                            bodies[entry_id],
                            entry_url=entry_url,
                            year=year,
                            page=1,
                            contract_version=entry_contract_version,
                        )
                        parsed_pages: list[JudiciaryYearResultPage] = []
                        page_number = 1
                        while True:
                            contract_endpoint_id = (
                                f"judiciary-year-{year}-verification-page-{page_number}"
                                if verification
                                else f"judiciary-year-{year}-page-{page_number}"
                            )
                            page_body, page_terminal = capture_url(
                                endpoint_id=contract_endpoint_id,
                                endpoint_version=result_contract_version,
                                url=current_url,
                                max_bytes=_JUDICIARY_DYNAMIC_MAX_BYTES,
                            )
                            if page_terminal != "CAPTURED":
                                traversal_failed = True
                                break
                            parsed_page = parse_judiciary_year_result_page(
                                page_body,
                                year=year,
                                page=page_number,
                                contract_version=result_contract_version,
                            )
                            parsed_pages.append(parsed_page)
                            if parsed_page.advertised_next_page is None:
                                break
                            current_url = build_judiciary_next_result_url(
                                current_url,
                                result_page=parsed_page,
                                form_contract_version=entry_contract_version,
                            )
                            page_number = parsed_page.advertised_next_page
                        if traversal_failed:
                            break
                        pass_partitions.append(
                            reconcile_judiciary_year_partition(
                                tuple(parsed_pages), contract_version=result_contract_version
                            )
                        )
                    if traversal_failed:
                        break
                    try:
                        pass_snapshot = _judiciary_inventory_snapshot(pass_partitions)
                    except ValueError:
                        inventory_contract_changed = True
                        break
                    if verification:
                        verification_partitions = pass_partitions
                        if pass_snapshot != _judiciary_inventory_snapshot(partitions):
                            inventory_contract_changed = True
                            break
                    else:
                        partitions = pass_partitions
                if not traversal_failed and not inventory_contract_changed:
                    if len(verification_partitions) != len(partitions):
                        inventory_contract_changed = True
                    else:
                        for partition in partitions:
                            for dis_id, artifact_url in zip(
                                partition.in_scope_dis_ids,
                                partition.artifact_urls,
                                strict=True,
                            ):
                                contract_endpoint_id = f"judiciary-dis-{dis_id}"
                                _, artifact_terminal = capture_url(
                                    endpoint_id=contract_endpoint_id,
                                    endpoint_version=result_contract_version,
                                    url=artifact_url,
                                    max_bytes=_JUDICIARY_DYNAMIC_MAX_BYTES,
                                )
                                if artifact_terminal != "CAPTURED":
                                    traversal_failed = True
                                    break
                            if traversal_failed:
                                break
                frame_content_unverified = any(
                    partition.in_scope_dis_ids for partition in partitions
                )
            for year in (
                ()
                if result_contract_version
                in {"1.0.6", "1.0.7", "1.0.8", "1.0.9", "1.0.10", "1.0.11", "1.0.12"}
                else years
            ):
                current_url = build_judiciary_year_result_url(
                    bodies[entry_id],
                    entry_url=entry_url,
                    year=year,
                    page=1,
                    contract_version=entry_contract_version,
                )
                parsed_pages: list[JudiciaryYearResultPage] = []
                page_number = 1
                while True:
                    contract_endpoint_id = f"judiciary-year-{year}-page-{page_number}"
                    page_body, page_terminal = capture_url(
                        endpoint_id=contract_endpoint_id,
                        endpoint_version=result_contract_version,
                        url=current_url,
                        max_bytes=_JUDICIARY_DYNAMIC_MAX_BYTES,
                    )
                    if page_terminal != "CAPTURED":
                        traversal_failed = True
                        break
                    parsed_page = parse_judiciary_year_result_page(
                        page_body,
                        year=year,
                        page=page_number,
                        contract_version=result_contract_version,
                    )
                    parsed_pages.append(parsed_page)
                    if result_contract_version not in {
                        "1.0.2",
                        "1.0.3",
                        "1.0.4",
                        "1.0.5",
                        "1.0.6",
                        "1.0.7",
                        "1.0.8",
                        "1.0.9",
                        "1.0.10",
                        "1.0.11",
                        "1.0.12",
                    }:
                        if parsed_page.reported_pages != 1:
                            mark_contract_changed(contract_endpoint_id)
                            traversal_failed = True
                        break
                    if parsed_page.advertised_next_page is None:
                        break
                    current_url = build_judiciary_next_result_url(
                        current_url,
                        result_page=parsed_page,
                        form_contract_version=entry_contract_version,
                    )
                    page_number = parsed_page.advertised_next_page
                if traversal_failed:
                    break
                partition = reconcile_judiciary_year_partition(
                    tuple(parsed_pages), contract_version=result_contract_version
                )
                if result_contract_version in {
                    "1.0.6",
                    "1.0.7",
                    "1.0.8",
                    "1.0.9",
                    "1.0.10",
                    "1.0.11",
                    "1.0.12",
                }:
                    current_url = build_judiciary_year_result_url(
                        bodies[entry_id],
                        entry_url=entry_url,
                        year=year,
                        page=1,
                        contract_version=entry_contract_version,
                    )
                    verification_pages: list[JudiciaryYearResultPage] = []
                    page_number = 1
                    while True:
                        contract_endpoint_id = (
                            f"judiciary-year-{year}-verification-page-{page_number}"
                        )
                        page_body, page_terminal = capture_url(
                            endpoint_id=contract_endpoint_id,
                            endpoint_version=result_contract_version,
                            url=current_url,
                            max_bytes=_JUDICIARY_DYNAMIC_MAX_BYTES,
                        )
                        if page_terminal != "CAPTURED":
                            traversal_failed = True
                            break
                        parsed_page = parse_judiciary_year_result_page(
                            page_body,
                            year=year,
                            page=page_number,
                            contract_version=result_contract_version,
                        )
                        verification_pages.append(parsed_page)
                        if parsed_page.advertised_next_page is None:
                            break
                        current_url = build_judiciary_next_result_url(
                            current_url,
                            result_page=parsed_page,
                            form_contract_version=entry_contract_version,
                        )
                        page_number = parsed_page.advertised_next_page
                    if traversal_failed:
                        break
                    verification_partition = reconcile_judiciary_year_partition(
                        tuple(verification_pages), contract_version=result_contract_version
                    )
                    if _judiciary_partition_snapshot(partition) != _judiciary_partition_snapshot(
                        verification_partition
                    ):
                        inventory_contract_changed = True
                        break
                for dis_id, artifact_url in zip(
                    partition.in_scope_dis_ids, partition.artifact_urls, strict=True
                ):
                    contract_endpoint_id = f"judiciary-dis-{dis_id}"
                    _, artifact_terminal = capture_url(
                        endpoint_id=contract_endpoint_id,
                        endpoint_version=result_contract_version,
                        url=artifact_url,
                        max_bytes=_JUDICIARY_DYNAMIC_MAX_BYTES,
                    )
                    if artifact_terminal != "CAPTURED":
                        traversal_failed = True
                        break
                if traversal_failed:
                    break
                partitions.append(partition)
                if result_contract_version in {
                    "1.0.1",
                    "1.0.2",
                    "1.0.3",
                    "1.0.4",
                    "1.0.5",
                    "1.0.6",
                    "1.0.7",
                    "1.0.8",
                    "1.0.9",
                    "1.0.10",
                    "1.0.11",
                    "1.0.12",
                } and (partition.in_scope_dis_ids):
                    frame_content_unverified = True
        except KeyError, StopIteration, TypeError, ValueError:
            mark_contract_changed(contract_endpoint_id)
            traversal_failed = True
        in_scope_count = sum(len(partition.in_scope_dis_ids) for partition in partitions)
        procedure_override = [
            {
                "declared_member_count": 1,
                "source_id": "HK-CASE-HKLII-DISCOVERY",
                "terminal_code": "COMPLETE",
            },
            {
                "declared_member_count": 0 if inventory_contract_changed else in_scope_count,
                "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
                "terminal_code": (
                    "SOURCE_CONTRACT_CHANGED"
                    if inventory_contract_changed
                    else (
                        "INCOMPLETE" if traversal_failed or frame_content_unverified else "COMPLETE"
                    )
                ),
            },
        ]
    elif source_family == "HKEX" and all(terminal == "CAPTURED" for terminal in terminals.values()):
        endpoint_by_id = {item.endpoint_id: item for item in endpoints}
        hkex_contract_endpoint_id = "sep_000000000000000000000000000000000000000000000309"
        try:
            catalogue = parse_hkex_catalogue(bodies[hkex_contract_endpoint_id])
        except KeyError, ValueError:
            mark_contract_changed(hkex_contract_endpoint_id)
            catalogue = None
        root_specs = (
            (
                "sep_000000000000000000000000000000000000000000000303",
                "sep_000000000000000000000000000000000000000000000314",
                "HK-REG-HKEX-FEES-RULES",
            ),
            (
                "sep_000000000000000000000000000000000000000000000304",
                "sep_000000000000000000000000000000000000000000000314",
                "HK-REG-HKEX-FEES-RULES",
            ),
            (
                "sep_000000000000000000000000000000000000000000000305",
                "sep_000000000000000000000000000000000000000000000313",
                "HK-REG-HKEX-REGULATORY-FORMS",
            ),
            (
                "sep_000000000000000000000000000000000000000000000306",
                "sep_000000000000000000000000000000000000000000000313",
                "HK-REG-HKEX-REGULATORY-FORMS",
            ),
            (
                "sep_000000000000000000000000000000000000000000000307",
                "sep_000000000000000000000000000000000000000000000315",
                "HK-REG-HKEX-RULE-UPDATES",
            ),
            (
                "sep_000000000000000000000000000000000000000000000308",
                "sep_000000000000000000000000000000000000000000000316",
                "HK-REG-HKEX-RULE-UPDATES",
            ),
        )
        member_counts: dict[str, int] = {}
        hkex_failed = catalogue is None
        for root_id, entire_id, source_id in () if hkex_failed else root_specs:
            hkex_contract_endpoint_id = root_id
            root_endpoint = endpoint_by_id[root_id]
            entire_endpoint = endpoint_by_id[entire_id]
            try:
                membership = parse_hkex_role_membership(
                    bodies[root_id],
                    root_url=root_endpoint.url,
                    entire_section_url=entire_endpoint.url,
                )
                captured_urls = [entire_endpoint.url]
                for member_url in membership.member_urls:
                    member_key = hashlib.sha256(member_url.encode()).hexdigest()[:24]
                    _, member_terminal = capture_url(
                        endpoint_id=f"hkex-member-{member_key}",
                        endpoint_version="1.0.0",
                        url=member_url,
                        max_bytes=_JUDICIARY_DYNAMIC_MAX_BYTES,
                    )
                    if member_terminal != "CAPTURED":
                        hkex_failed = True
                        break
                    captured_urls.append(member_url)
                if hkex_failed:
                    break
                complete = reconcile_hkex_role_capture(membership, tuple(captured_urls))
                member_counts[source_id] = (
                    member_counts.get(source_id, 0) + complete.declared_member_count
                )
            except TypeError, ValueError:
                mark_contract_changed(hkex_contract_endpoint_id)
                hkex_failed = True
                break
        try:
            for section_id, pdf_id in (
                (
                    "sep_000000000000000000000000000000000000000000000315",
                    "sep_000000000000000000000000000000000000000000000317",
                ),
                (
                    "sep_000000000000000000000000000000000000000000000316",
                    "sep_000000000000000000000000000000000000000000000318",
                ),
            ):
                hkex_contract_endpoint_id = pdf_id
                require_hkex_amendment_pdf_membership(
                    bodies[section_id],
                    section_url=endpoint_by_id[section_id].url,
                    pdf_url=endpoint_by_id[pdf_id].url,
                )
            for pdf_id in (
                "sep_000000000000000000000000000000000000000000000311",
                "sep_000000000000000000000000000000000000000000000312",
                "sep_000000000000000000000000000000000000000000000317",
                "sep_000000000000000000000000000000000000000000000318",
            ):
                hkex_contract_endpoint_id = pdf_id
                require_hkex_pdf(bodies[pdf_id])
        except KeyError, ValueError:
            mark_contract_changed(hkex_contract_endpoint_id)
            hkex_failed = True
        source_counts = {
            "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS": 5,
            "HK-REG-HKEX-FEES-RULES": member_counts.get("HK-REG-HKEX-FEES-RULES", 0),
            "HK-REG-HKEX-REGULATORY-FORMS": member_counts.get("HK-REG-HKEX-REGULATORY-FORMS", 0),
            "HK-REG-HKEX-RULE-UPDATES": member_counts.get("HK-REG-HKEX-RULE-UPDATES", 0),
            "HK-REG-HKEX-RULEBOOK-CATALOGUE": (
                0 if catalogue is None else len(catalogue.role_roots)
            ),
        }
        procedure_override = [
            {
                "declared_member_count": source_counts[source.source_id],
                "source_id": source.source_id,
                "terminal_code": "INCOMPLETE" if hkex_failed else "COMPLETE",
            }
            for source in load_hk_regulatory_source_register().sources
        ]
    elif source_family == "HKEL" and all(terminal == "CAPTURED" for terminal in terminals.values()):
        contract_root_id = (
            _BASIC_LAW_CONSTITUTION_ROOT_ID
            if current_basic_law_binding
            else "sep_000000000000000000000000000000000000000000000050"
        )
        try:
            if current_basic_law_binding:
                membership = parse_basic_law_membership(
                    bodies[_BASIC_LAW_CONSTITUTION_ROOT_ID],
                    bodies[_BASIC_LAW_TEXT_ROOT_ID],
                    constitution_root_url=CONSTITUTION_ROOT_URL,
                    basic_law_root_url=BASIC_LAW_ROOT_URL,
                )
            else:
                membership = parse_historical_basic_law_root_membership(
                    bodies[contract_root_id],
                    root_url="https://www.basiclaw.gov.hk/en/index/index.html",
                )
            for member_url in membership.member_urls:
                if current_basic_law_binding:
                    require_basic_law_member_url(member_url)
                else:
                    require_historical_basic_law_category_url(member_url)
                if member_url not in bound_authorization.allowed_urls:
                    _fail("BASIC_LAW_MEMBER_NOT_AUTHORIZED")
                existing_id = _BASIC_LAW_REUSED_ENDPOINTS.get(member_url)
                if existing_id is not None:
                    if terminals.get(existing_id) != "CAPTURED":
                        break
                    try:
                        validate_basic_law_content_page(
                            bodies[existing_id],
                            url=member_url,
                            media_type=media_types[existing_id],
                        )
                    except KeyError, TypeError, ValueError:
                        mark_contract_changed(existing_id)
                        break
                    continue
                member_key = hashlib.sha256(member_url.encode()).hexdigest()[:24]
                member_id = f"basic-law-member-{member_key}"
                member_body, member_terminal = capture_url(
                    endpoint_id=member_id,
                    endpoint_version="1.0.0",
                    url=member_url,
                    max_bytes=_JUDICIARY_DYNAMIC_MAX_BYTES,
                )
                if member_terminal != "CAPTURED":
                    break
                try:
                    validate_basic_law_content_page(
                        member_body,
                        url=member_url,
                        media_type=media_types[member_id],
                    )
                except KeyError, TypeError, ValueError:
                    mark_contract_changed(member_id)
                    break
        except SourceEvidenceIntegrityError:
            raise
        except KeyError, TypeError, ValueError:
            mark_contract_changed(contract_root_id)
    if (
        source_family == "JUDICIARY"
        and judiciary_observation is not None
        and (judiciary_observation.stop_code is not None)
    ):
        procedure_override = [
            {
                "declared_member_count": (
                    1
                    if terminals.get("sep_000000000000000000000000000000000000000000000201")
                    == "CAPTURED"
                    else 0
                ),
                "source_id": "HK-CASE-HKLII-DISCOVERY",
                "terminal_code": (
                    "COMPLETE"
                    if terminals.get("sep_000000000000000000000000000000000000000000000201")
                    == "CAPTURED"
                    else "INCOMPLETE"
                ),
            },
            {
                "declared_member_count": 0,
                "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
                "terminal_code": (
                    "OBSERVATION_EXECUTION_FAILURE"
                    if judiciary_observation.stop_code == "OBSERVATION_EXECUTION_FAILURE"
                    else "BUDGET_EXHAUSTED"
                ),
            },
        ]
    procedures = (
        procedure_override
        if procedure_override is not None
        else _source_procedures(source_family, bodies, terminals)
    )
    if source_family == "HKEL" and not current_basic_law_binding:
        procedures = [
            _basic_law_procedure(bodies, terminals, current_binding=False)
            if item["source_id"] == "HK-LEG-BASIC-LAW-PORTAL"
            else item
            for item in procedures
        ]
    bodies.clear()
    result = _derived_report_result(counts, procedures)
    change_state = "FIRST_OBSERVATION"
    if judiciary_continuation is not None:
        change_state = "CHANGED_OBSERVED"
    elif prior is not None:
        change_state = (
            "CHANGED_OBSERVED"
            if judiciary_observation is not None and judiciary_observation.stop_code is not None
            else "NO_CHANGE_OBSERVED"
            if prior == current_fingerprints
            else "CHANGED_OBSERVED"
        )
    report: dict[str, object] = {
        "attempt_id": attempt_id,
        "authority_manifest_fingerprint": authority_fingerprint,
        "authority_provenance": provenance,
        "change_state": change_state,
        "endpoint_counts": dict(sorted(counts.items())),
        "endpoints": records,
        "execution_authorization_fingerprint": bound_authorization.binding_fingerprint,
        "observation_cutoff": observation_cutoff,
        "predecessor_attempt_id": predecessor_attempt_id,
        "readback_verified": True,
        "result": result,
        "source_family": source_family,
        "source_procedures": procedures,
    }
    if judiciary_observation is not None and judiciary_observation.stop_code is not None:
        report["observation_stop"] = judiciary_observation.report_stop()
    if source_family == "JUDICIARY" and not bound_authorization.historical_replay:
        if judiciary_observation is None:
            _fail("CAPTURE_ACCOUNTING_INVALID")
        report["execution_policy"] = execution_policy()
        report["execution_policy_fingerprint"] = execution_policy_fingerprint()
        report["observation_accounting"] = judiciary_observation.report_accounting()
        if judiciary_continuation is not None:
            report["continuation_binding"] = judiciary_continuation.binding
            report["cumulative_observation_accounting"] = (
                judiciary_observation.report_cumulative_accounting()
            )
            report["report_schema_version"] = "1.2.0"
        else:
            report["report_schema_version"] = "1.1.0"
        report["transport_attempts"] = transport_attempts
    _publish_attempt_report(report_path, _canonical(report))
    return report
