"""Strict adapter from immutable Task 7 source reports into canonical due-source facts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from asklegal_contracts import parse_json_bytes
from asklegal_reporting import DueChangeStatus, DueTerminalOutcome

_AUTHORITY = "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING"
_MAX_REPORT = 32_000_000
_CAPTURE_INVALID = "AUTHENTIC_DUE_CAPTURE_INVALID"
_REPORT_BINDING_INVALID = "SOURCE_ADMISSION_REPORT_BINDING_INVALID"
_REPORT_INVALID = "SOURCE_ADMISSION_REPORT_INVALID"
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ATTEMPT_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,79}\Z")
_HK_CUTOFF = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\+08:00\Z")
_HKEX_SCHEMA_2_POLICY_FINGERPRINT = (
    "sha256:3d204e5dc8e8ac1fd500cf85cdeb28f43ddf3ceff1d2c3f285c56e615dce65c9"
)
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
_COMMON_REPORT_KEYS = frozenset(
    {
        "attempt_id",
        "authority_manifest_fingerprint",
        "authority_provenance",
        "change_state",
        "endpoint_counts",
        "endpoints",
        "execution_authorization_fingerprint",
        "observation_cutoff",
        "predecessor_attempt_id",
        "readback_verified",
        "result",
        "source_family",
        "source_procedures",
    }
)
_HKEX_SCHEMA_2_KEYS = _COMMON_REPORT_KEYS | {
    "execution_policy",
    "execution_policy_fingerprint",
    "hkex_attachment_occurrences",
    "hkex_dynamic_html_attempts",
    "hkex_membership_associations",
    "hkex_membership_fingerprint",
    "hkex_page_identities",
    "hkex_physical_starts",
    "hkex_plan_state",
    "hkex_request_plan",
    "hkex_root_bindings",
    "hkex_traversal_accounting",
    "report_schema_version",
}
_FAMILY_SOURCE_IDS = {
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
_KNOWN_HKEL_REPORT = Path(
    "hkel-attempt-b/attempts/hkel-live-baseline-basic-law20-20260828b/report.json"
)
_KNOWN_JUDICIARY_REPORT = Path(
    "judiciary-attempt-p/attempts/judiciary-live-baseline-20260831w/report.json"
)


def _instant(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError(_REPORT_INVALID)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(_REPORT_INVALID) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(_REPORT_INVALID)
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class AuthenticDueSourceCapture:
    """Closed source facts plus the exact retained manifest that proves a complete result."""

    source_id: str
    outcome: DueTerminalOutcome
    change_status: DueChangeStatus
    failure_codes: tuple[str, ...]
    expected_count: int
    retained_count: int
    not_published_count: int
    gap_count: int
    failed_count: int
    evidence_bytes: bytes | None
    evidence_kind: str = "AUTHENTIC_SOURCE_EVIDENCE"

    def __post_init__(self) -> None:
        """Reject inconsistent complete and incomplete source assertions."""
        if type(self.source_id) is not str or not self.source_id.startswith("HK-"):
            raise ValueError(_CAPTURE_INVALID)
        if self.evidence_kind not in {
            "AUTHENTIC_SOURCE_EVIDENCE",
            "CURRENT_FAMILY_ROLE_PROOF",
        }:
            raise ValueError(_CAPTURE_INVALID)
        if (
            type(self.outcome) is not DueTerminalOutcome
            or type(self.change_status) is not DueChangeStatus
        ):
            raise TypeError(_CAPTURE_INVALID)
        if (
            type(self.failure_codes) is not tuple
            or any(type(item) is not str or not item for item in self.failure_codes)
            or self.failure_codes != tuple(sorted(set(self.failure_codes)))
        ):
            raise ValueError(_CAPTURE_INVALID)
        counts = (
            self.expected_count,
            self.retained_count,
            self.not_published_count,
            self.gap_count,
            self.failed_count,
        )
        if any(type(item) is not int or item < 0 for item in counts):
            raise ValueError(_CAPTURE_INVALID)
        if self.outcome is DueTerminalOutcome.COMPLETE:
            if (
                self.change_status is DueChangeStatus.NOT_PROVED
                or self.failure_codes
                or self.evidence_bytes is None
                or self.retained_count != self.expected_count
                or self.gap_count
                or self.failed_count
            ):
                raise ValueError(_CAPTURE_INVALID)
        elif (
            self.change_status is not DueChangeStatus.NOT_PROVED
            or not self.failure_codes
            or self.evidence_bytes is not None
        ):
            raise ValueError(_CAPTURE_INVALID)


class AuthenticDueSourceAdapter(Protocol):
    """The canonical worker-side port for one already authorized due observation."""

    def capture(
        self, *, source_id: str, observation_cutoff: str
    ) -> AuthenticDueSourceCapture | None:
        """Return exact retained facts or None when this adapter does not own the role."""
        ...

    def verify_retained_object(
        self, object_ref: str, content_fingerprint: str, byte_length: int
    ) -> bool:
        """Re-prove one exact imported object used by a current family journal."""
        ...


class RetainedSourceAdmissionAdapter:
    """Read exact manifest-last Task 7 reports and re-prove every object fingerprint."""

    def __init__(
        self,
        reports: Mapping[str, Path],
        *,
        repository_root: Path | None = None,
        admission_root: Path | None = None,
    ) -> None:
        """Bind source IDs to one explicit retained root without accepting path escape."""
        if (repository_root is None) == (admission_root is None):
            raise ValueError(_REPORT_BINDING_INVALID)
        if admission_root is not None:
            if not admission_root.is_absolute() or admission_root.is_symlink():
                raise ValueError(_REPORT_BINDING_INVALID)
            var_root = admission_root.resolve(strict=True)
        else:
            if repository_root is None:
                raise ValueError(_REPORT_BINDING_INVALID)
            root = repository_root.resolve(strict=True)
            var_root = (root / "var").resolve(strict=False)
        copied: dict[str, Path] = {}
        for source_id, path in reports.items():
            if type(source_id) is not str or not source_id.startswith("HK-"):
                raise ValueError(_REPORT_BINDING_INVALID)
            resolved = path.resolve(strict=False)
            resolved.relative_to(var_root)
            copied[source_id] = resolved
        self._reports = copied

    def verify_retained_object(
        self, object_ref: str, content_fingerprint: str, byte_length: int
    ) -> bool:
        """Read one object only beneath the explicitly bound report output roots."""
        if (
            type(object_ref) is not str
            or not object_ref.startswith("objects/")
            or any(part in {"", ".", ".."} for part in object_ref.split("/"))
            or type(content_fingerprint) is not str
            or _FINGERPRINT.fullmatch(content_fingerprint) is None
            or type(byte_length) is not int
            or byte_length < 0
        ):
            return False
        roots = {path.parent.parent.parent.resolve(strict=True) for path in self._reports.values()}
        matched = False
        for root in roots:
            candidate = root / object_ref
            try:
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
                body = resolved.read_bytes()
            except OSError, ValueError:
                return False
            if (
                len(body) == byte_length
                and f"sha256:{hashlib.sha256(body).hexdigest()}" == content_fingerprint
            ):
                if matched:
                    return False
                matched = True
        return matched

    def capture(  # noqa: C901, PLR0912, PLR0915 - closed verification is linear.
        self, *, source_id: str, observation_cutoff: str
    ) -> AuthenticDueSourceCapture | None:
        """Return one fully re-proved canonical capture, or None for an unowned source."""
        path = self._reports.get(source_id)
        if path is None:
            return None
        raw = path.read_bytes()
        if len(raw) > _MAX_REPORT:
            raise ValueError(_REPORT_INVALID)
        document = parse_json_bytes(raw, max_bytes=_MAX_REPORT)
        if type(document) is not dict:
            raise ValueError(_REPORT_INVALID)
        report = cast("dict[str, object]", document)
        family = report.get("source_family")
        attempt_id = report.get("attempt_id")
        authority_fingerprint = report.get("authority_manifest_fingerprint")
        report_cutoff = report.get("observation_cutoff")
        predecessor = report.get("predecessor_attempt_id")
        if (
            json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            != raw
            or report.get("authority_provenance") != _AUTHORITY
            or type(family) is not str
            or source_id not in _FAMILY_SOURCE_IDS.get(family, frozenset())
            or type(attempt_id) is not str
            or _ATTEMPT_ID.fullmatch(attempt_id) is None
            or type(authority_fingerprint) is not str
            or _FINGERPRINT.fullmatch(authority_fingerprint) is None
            or type(report_cutoff) is not str
            or _HK_CUTOFF.fullmatch(report_cutoff) is None
            or _instant(report_cutoff) != _instant(observation_cutoff)
            or (
                predecessor is not None
                and (type(predecessor) is not str or _ATTEMPT_ID.fullmatch(predecessor) is None)
            )
            or report.get("readback_verified") is not True
        ):
            raise ValueError(_REPORT_INVALID)
        self._verify_current_hkex_shape(report)
        self._verify_objects(path, report)
        procedures = report.get("source_procedures")
        if type(procedures) is not list:
            raise ValueError(_REPORT_INVALID)
        matches: list[dict[str, object]] = []
        for value in cast("list[object]", procedures):
            if type(value) is dict:
                item = cast("dict[str, object]", value)
                if item.get("source_id") == source_id:
                    matches.append(item)
        if len(matches) != 1:
            raise ValueError(_REPORT_INVALID)
        procedure = matches[0]
        count = procedure.get("declared_member_count")
        terminal = procedure.get("terminal_code")
        if type(count) is not int or count < 0 or type(terminal) is not str:
            raise ValueError(_REPORT_INVALID)
        if terminal == "COMPLETE" and report.get("result") == "COMPLETE":
            change_key = report.get("change_state")
            if type(change_key) is not str:
                raise ValueError(_REPORT_INVALID)
            change = {
                "FIRST_OBSERVATION": DueChangeStatus.BASELINE,
                "NO_CHANGE_OBSERVED": DueChangeStatus.NO_CHANGE,
                "CHANGED_OBSERVED": DueChangeStatus.CHANGED,
            }.get(change_key)
            if change is None:
                raise ValueError(_REPORT_INVALID)
            endpoints = report.get("endpoints")
            if type(endpoints) is not list or not endpoints:
                raise ValueError(_REPORT_INVALID)
            for value in cast("list[object]", endpoints):
                if type(value) is not dict:
                    raise ValueError(_REPORT_INVALID)
                item = cast("dict[str, object]", value)
                if item.get("terminal_code") != "CAPTURED":
                    raise ValueError(_REPORT_INVALID)
            return AuthenticDueSourceCapture(
                source_id,
                DueTerminalOutcome.COMPLETE,
                change,
                (),
                count,
                count,
                0,
                0,
                0,
                raw,
            )
        report_result = report.get("result")
        failure_value = (
            "SOURCE_CONTRACT_CHANGED"
            if report_result == "SOURCE_CONTRACT_CHANGED"
            else terminal
            if terminal != "COMPLETE"
            else report_result
        )
        if type(failure_value) is not str or not failure_value:
            raise ValueError(_REPORT_INVALID)
        failure_code = failure_value
        outcome = (
            DueTerminalOutcome.FAILED
            if failure_code in {"SOURCE_OUTAGE", "OUTAGE"}
            else DueTerminalOutcome.INCOMPLETE_OBSERVATION
        )
        return AuthenticDueSourceCapture(
            source_id,
            outcome,
            DueChangeStatus.NOT_PROVED,
            (failure_code,),
            max(1, count),
            0,
            max(1, count) if outcome is DueTerminalOutcome.INCOMPLETE_OBSERVATION else 0,
            0,
            1 if outcome is DueTerminalOutcome.FAILED else 0,
            None,
        )

    @staticmethod
    def _verify_current_hkex_shape(report: dict[str, object]) -> None:
        """Bind current schema-2 HKEX reports to the exact policy and closed field surface."""
        if report.get("report_schema_version") != "2.0.0":
            return
        policy = report.get("execution_policy")
        policy_fingerprint = report.get("execution_policy_fingerprint")
        list_fields = (
            "hkex_attachment_occurrences",
            "hkex_dynamic_html_attempts",
            "hkex_membership_associations",
            "hkex_page_identities",
            "hkex_physical_starts",
            "hkex_request_plan",
            "hkex_root_bindings",
        )
        if (
            report.get("source_family") != "HKEX"
            or frozenset(report) != _HKEX_SCHEMA_2_KEYS
            or report.get("hkex_plan_state") not in _HKEX_PLAN_STATES
            or type(policy) is not dict
            or policy_fingerprint != _HKEX_SCHEMA_2_POLICY_FINGERPRINT
            or "sha256:"
            + hashlib.sha256(
                json.dumps(
                    policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            != _HKEX_SCHEMA_2_POLICY_FINGERPRINT
            or type(report.get("execution_authorization_fingerprint")) is not str
            or _FINGERPRINT.fullmatch(cast("str", report["execution_authorization_fingerprint"]))
            is None
            or type(report.get("hkex_membership_fingerprint")) is not str
            or _FINGERPRINT.fullmatch(cast("str", report["hkex_membership_fingerprint"])) is None
            or type(report.get("hkex_traversal_accounting")) is not dict
            or any(type(report.get(field)) is not list for field in list_fields)
        ):
            raise ValueError(_REPORT_INVALID)

    @staticmethod
    def _verify_objects(report_path: Path, report: dict[str, object]) -> None:
        endpoints = report.get("endpoints")
        if type(endpoints) is not list:
            raise ValueError(_REPORT_INVALID)
        output_root = report_path.parent.parent.parent
        for value in cast("list[object]", endpoints):
            if type(value) is not dict:
                raise ValueError(_REPORT_INVALID)
            endpoint = cast("dict[str, object]", value)
            key = endpoint.get("object_key")
            fingerprint = endpoint.get("body_fingerprint")
            byte_length = endpoint.get("byte_length")
            if (
                type(key) is not str
                or not key.startswith("objects/")
                or type(fingerprint) is not str
                or type(byte_length) is not int
                or byte_length < 0
            ):
                raise ValueError(_REPORT_INVALID)
            lexical_path = output_root / key
            if lexical_path.is_symlink() or not lexical_path.is_file():
                raise ValueError(_REPORT_INVALID)
            object_path = lexical_path.resolve(strict=True)
            object_path.relative_to(output_root.resolve(strict=True))
            body = object_path.read_bytes()
            actual = "sha256:" + hashlib.sha256(body).hexdigest()
            if actual != fingerprint or len(body) != byte_length:
                raise ValueError(_REPORT_INVALID)


def known_v1_retained_source_adapter(source_root: Path) -> RetainedSourceAdmissionAdapter:
    """Compose the accepted HKeL/Judiciary report bindings under one mounted root."""
    reports = {
        **dict.fromkeys(_FAMILY_SOURCE_IDS["HKEL"], source_root / _KNOWN_HKEL_REPORT),
        **dict.fromkeys(_FAMILY_SOURCE_IDS["JUDICIARY"], source_root / _KNOWN_JUDICIARY_REPORT),
    }
    return RetainedSourceAdmissionAdapter(reports, admission_root=source_root)
