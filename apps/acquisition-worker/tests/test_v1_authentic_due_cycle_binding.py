"""Canonical due-cycle binding for retained authentic source-admission evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from asklegal_acquisition_worker.hk_v1_due_cycle import HongKongV1DueCycleActivities
from asklegal_acquisition_worker.hk_v1_due_predecessor import LocalDueCyclePredecessorStore
from asklegal_acquisition_worker.source_admission_adapter import (
    AuthenticDueSourceCapture,
    RetainedSourceAdmissionAdapter,
)
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import LocalImmutableVault, VaultName
from asklegal_reporting import (
    DueChangeStatus,
    DueCycleKind,
    DueTerminalOutcome,
    hk_v1_due_source_payload_key,
    load_hk_v1_coverage_matrix,
)

from tools.hk_v1_hkex_policy import execution_policy, execution_policy_fingerprint

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_CURRENT_AUTHENTIC_SOURCE_ID = "HK-LEG-GLD-EGAZETTE"


def _context() -> ActivityContext:
    """Provide the inert SDK context required by direct activity tests."""
    return ActivityContext("hk-v1-authentic-due-cycle-test", 1)


@dataclass
class _Adapter:
    result: AuthenticDueSourceCapture
    calls: int = 0

    def capture(
        self, *, source_id: str, observation_cutoff: str
    ) -> AuthenticDueSourceCapture | None:
        assert observation_cutoff == "2026-08-27T14:52:09Z"
        if source_id != self.result.source_id:
            return None
        self.calls += 1
        return self.result

    @staticmethod
    def verify_retained_object(object_ref: str, content_fingerprint: str, byte_length: int) -> bool:
        del object_ref, content_fingerprint, byte_length
        return False


def _instruction(cycle_id: str) -> dict[str, str]:
    matrix = load_hk_v1_coverage_matrix()
    return {
        "cycle_id": cycle_id,
        "cycle_kind": DueCycleKind.FULL_PERIODIC.value,
        "scheduled_at": "2026-08-27T14:52:09Z",
        "observation_cutoff": "2026-08-27T14:52:09Z",
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
    }


def _request(
    plan: dict[str, object], instruction: dict[str, str], source_id: str
) -> dict[str, object]:
    return {
        "instruction": instruction,
        "expected_plan_fingerprint": plan["plan_fingerprint"],
        "source_id": source_id,
    }


def test_complete_authentic_adapter_result_is_retained_bound_and_restart_safe(
    tmp_path: Path,
) -> None:
    """A complete terminal carries exact evidence and an identical restart replays immutably."""
    source_id = _CURRENT_AUTHENTIC_SOURCE_ID
    adapter = _Adapter(
        AuthenticDueSourceCapture(
            source_id,
            DueTerminalOutcome.COMPLETE,
            DueChangeStatus.BASELINE,
            (),
            8,
            8,
            0,
            0,
            0,
            b'{"authority_provenance":"USER_ATTESTED_PERMISSION_DOCUMENT_PENDING","result":"COMPLETE"}',
        )
    )
    vault = LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY)
    activities = HongKongV1DueCycleActivities(
        vault,
        LocalDueCyclePredecessorStore(tmp_path / "state"),
        source_adapter=adapter,
    )
    instruction = _instruction("hk-v1-authentic-baseline")
    plan = cast("dict[str, object]", activities.plan_hk_v1_due_cycle(_context(), instruction))

    first = activities.capture_hk_v1_due_source(_context(), _request(plan, instruction, source_id))
    replay = activities.capture_hk_v1_due_source(_context(), _request(plan, instruction, source_id))

    assert first["payload_created"] is True
    assert replay["payload_created"] is False
    assert adapter.calls == 2
    payload_ref = vault.resolve_current(
        hk_v1_due_source_payload_key("hk-v1-authentic-baseline", source_id)
    )
    assert payload_ref is not None
    payload = json.loads(vault.read_exact(payload_ref))
    assert payload["outcome"] == "COMPLETE"
    assert payload["change_status"] == "BASELINE"
    assert payload["failure_codes"] == []
    assert payload["evidence_kind"] == "AUTHENTIC_SOURCE_EVIDENCE"
    assert payload["expected_count"] == payload["retained_count"] == 8

    terminal_references = [{"source_id": source_id, "reference": first["terminal_reference"]}]
    for other_source_id in cast("list[str]", plan["source_ids"]):
        if other_source_id == source_id:
            continue
        captured = activities.capture_hk_v1_due_source(
            _context(), _request(plan, instruction, other_source_id)
        )
        terminal_references.append(
            {"source_id": other_source_id, "reference": captured["terminal_reference"]}
        )
    assembled = activities.assemble_hk_v1_due_cycle(
        _context(),
        {
            "instruction": instruction,
            "expected_plan_fingerprint": plan["plan_fingerprint"],
            "terminal_references": terminal_references,
        },
    )
    assert assembled["accounting_complete"] is True
    assert assembled["release_blocking"] is True


@pytest.mark.parametrize(
    ("outcome", "failure_code"),
    [
        (DueTerminalOutcome.INCOMPLETE_OBSERVATION, "TRUNCATED_RESPONSE"),
        (DueTerminalOutcome.FAILED, "SOURCE_OUTAGE"),
        (DueTerminalOutcome.INCOMPLETE_OBSERVATION, "CHALLENGE_AUTHORITY_REQUIRED"),
    ],
)
def test_noncomplete_authentic_results_remain_fail_visible(
    tmp_path: Path, outcome: DueTerminalOutcome, failure_code: str
) -> None:
    """Truncation, outage, and GLD challenge cannot become no-change or complete terminals."""
    source_id = _CURRENT_AUTHENTIC_SOURCE_ID
    adapter = _Adapter(
        AuthenticDueSourceCapture(
            source_id,
            outcome,
            DueChangeStatus.NOT_PROVED,
            (failure_code,),
            1,
            0,
            0 if outcome is DueTerminalOutcome.FAILED else 1,
            0,
            1 if outcome is DueTerminalOutcome.FAILED else 0,
            None,
        )
    )
    activities = HongKongV1DueCycleActivities(
        LocalImmutableVault(tmp_path / "vault", VaultName.PRIMARY),
        LocalDueCyclePredecessorStore(tmp_path / "state"),
        source_adapter=adapter,
    )
    instruction = _instruction("hk-v1-authentic-" + failure_code.lower().replace("_", "-"))
    plan = cast("dict[str, object]", activities.plan_hk_v1_due_cycle(_context(), instruction))

    result = activities.capture_hk_v1_due_source(_context(), _request(plan, instruction, source_id))

    assert result["terminal_reference"]


def test_retained_report_adapter_reproves_cutoff_authority_and_every_object(tmp_path: Path) -> None:
    """The concrete adapter consumes only the exact manifest-last object graph."""
    source_id = "HK-REG-HKEX-RULEBOOK-CATALOGUE"
    root = (
        _REPOSITORY_ROOT
        / "var"
        / "test-source-admission-adapter"
        / tmp_path.parent.name
        / tmp_path.name
    )
    object_body = b"publisher bytes"
    fingerprint = "sha256:" + hashlib.sha256(object_body).hexdigest()
    object_path = root / "objects" / (fingerprint.removeprefix("sha256:") + ".bin")
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(object_body)
    report = {
        "attempt_id": "hkex-complete",
        "authority_manifest_fingerprint": "sha256:" + "b" * 64,
        "authority_provenance": "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        "change_state": "NO_CHANGE_OBSERVED",
        "endpoint_counts": {"CAPTURED": 1},
        "endpoints": [
            {
                "body_fingerprint": fingerprint,
                "byte_length": len(object_body),
                "endpoint_id": "hkex-member-proof",
                "endpoint_version": "1.0.0",
                "media_type": "text/html",
                "method": "GET",
                "object_key": "objects/" + fingerprint.removeprefix("sha256:") + ".bin",
                "requested_url": "https://en-rules.hkex.com.hk/rulebook/member",
                "status": 200,
                "terminal_code": "CAPTURED",
            }
        ],
        "observation_cutoff": "2026-08-27T22:52:09+08:00",
        "predecessor_attempt_id": None,
        "readback_verified": True,
        "result": "COMPLETE",
        "source_family": "HKEX",
        "source_procedures": [
            {
                "declared_member_count": 1,
                "source_id": source_id,
                "terminal_code": "COMPLETE",
            }
        ],
    }
    report_path = root / "attempts" / "hkex-complete" / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    adapter = RetainedSourceAdmissionAdapter(
        {source_id: report_path}, repository_root=_REPOSITORY_ROOT
    )

    capture = adapter.capture(source_id=source_id, observation_cutoff="2026-08-27T14:52:09Z")

    assert capture is not None
    assert capture.change_status is DueChangeStatus.NO_CHANGE
    assert capture.evidence_bytes == report_path.read_bytes()
    object_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SOURCE_ADMISSION_REPORT_INVALID"):
        adapter.capture(source_id=source_id, observation_cutoff="2026-08-27T14:52:09Z")


def test_adapter_preserves_report_level_parser_drift_over_generic_procedure_terminal(
    tmp_path: Path,
) -> None:
    """A parser-drift report must reach the due fact as SOURCE_CONTRACT_CHANGED."""
    source_id = "HK-REG-HKEX-RULEBOOK-CATALOGUE"
    root = (
        _REPOSITORY_ROOT
        / "var"
        / "test-source-admission-adapter"
        / tmp_path.parent.name
        / tmp_path.name
    )
    body = b"retained changed publisher contract"
    fingerprint = "sha256:" + hashlib.sha256(body).hexdigest()
    object_key = "objects/" + fingerprint.removeprefix("sha256:") + ".bin"
    object_path = root / object_key
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(body)
    report = {
        "attempt_id": "hkex-parser-drift",
        "authority_manifest_fingerprint": "sha256:" + "b" * 64,
        "authority_provenance": "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        "change_state": "FIRST_OBSERVATION",
        "endpoint_counts": {"SOURCE_CONTRACT_CHANGED": 1},
        "endpoints": [
            {
                "body_fingerprint": fingerprint,
                "byte_length": len(body),
                "endpoint_id": "hkex-catalogue",
                "endpoint_version": "1.0.0",
                "media_type": "text/html",
                "method": "GET",
                "object_key": object_key,
                "requested_url": "https://www.hkex.com.hk/Listing/Rules-and-Resources/Listing-Rules?sc_lang=en",
                "status": 200,
                "terminal_code": "SOURCE_CONTRACT_CHANGED",
            }
        ],
        "observation_cutoff": "2026-08-27T22:52:09+08:00",
        "predecessor_attempt_id": None,
        "readback_verified": True,
        "result": "SOURCE_CONTRACT_CHANGED",
        "source_family": "HKEX",
        "source_procedures": [
            {
                "declared_member_count": 0,
                "source_id": source_id,
                "terminal_code": "INCOMPLETE",
            }
        ],
    }
    report_path = root / "attempts" / "hkex-parser-drift" / "report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    adapter = RetainedSourceAdmissionAdapter(
        {source_id: report_path}, repository_root=_REPOSITORY_ROOT
    )

    capture = adapter.capture(source_id=source_id, observation_cutoff="2026-08-27T14:52:09Z")

    assert capture is not None
    assert capture.failure_codes == ("SOURCE_CONTRACT_CHANGED",)
    assert capture.outcome is DueTerminalOutcome.INCOMPLETE_OBSERVATION


def test_schema_2_hkex_external_membership_stays_fail_visible_for_every_source(
    tmp_path: Path,
) -> None:
    """The current HKEX policy surface preserves external and family-level incompleteness."""
    root = (
        _REPOSITORY_ROOT
        / "var"
        / "test-source-admission-adapter"
        / tmp_path.parent.name
        / tmp_path.name
        / "schema-2"
    )
    membership: dict[str, object] = {
        "attachment_occurrences": cast("list[object]", []),
        "membership_associations": cast("list[object]", []),
        "root_bindings": cast("list[object]", []),
    }
    source_ids = tuple(
        sorted(
            {
                "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
                "HK-REG-HKEX-FEES-RULES",
                "HK-REG-HKEX-REGULATORY-FORMS",
                "HK-REG-HKEX-RULE-UPDATES",
                "HK-REG-HKEX-RULEBOOK-CATALOGUE",
            }
        )
    )
    procedures = [
        {
            "declared_member_count": 1,
            "source_id": source_id,
            "terminal_code": (
                "EXTERNAL_REFERENCE_AUTHORITY_REQUIRED"
                if source_id == "HK-REG-HKEX-RULE-UPDATES"
                else "COMPLETE"
            ),
        }
        for source_id in source_ids
    ]
    report = {
        "attempt_id": "hkex-schema-2-due",
        "authority_manifest_fingerprint": "sha256:" + "a" * 64,
        "authority_provenance": "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        "change_state": "FIRST_OBSERVATION",
        "endpoint_counts": {},
        "endpoints": [],
        "execution_authorization_fingerprint": "sha256:" + "b" * 64,
        "execution_policy": execution_policy(),
        "execution_policy_fingerprint": execution_policy_fingerprint(),
        "hkex_attachment_occurrences": [],
        "hkex_dynamic_html_attempts": [],
        "hkex_membership_associations": [],
        "hkex_membership_fingerprint": "sha256:"
        + hashlib.sha256(
            json.dumps(membership, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "hkex_page_identities": [],
        "hkex_physical_starts": [],
        "hkex_plan_state": "COMPLETE_PLAN",
        "hkex_request_plan": [],
        "hkex_root_bindings": [],
        "hkex_traversal_accounting": {},
        "observation_cutoff": "2026-08-27T22:52:09+08:00",
        "predecessor_attempt_id": None,
        "readback_verified": True,
        "report_schema_version": "2.0.0",
        "result": "EVIDENCE_CAPTURED_INCOMPLETE",
        "source_family": "HKEX",
        "source_procedures": procedures,
    }
    report_path = root / "attempts/hkex-schema-2-due/report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")))
    adapter = RetainedSourceAdmissionAdapter(
        {cast("str", item["source_id"]): report_path for item in procedures},
        repository_root=_REPOSITORY_ROOT,
    )

    captures = {
        source_id: adapter.capture(
            source_id=source_id,
            observation_cutoff="2026-08-27T14:52:09Z",
        )
        for source_id in source_ids
    }

    updates = captures["HK-REG-HKEX-RULE-UPDATES"]
    assert updates is not None
    assert updates.failure_codes == ("EXTERNAL_REFERENCE_AUTHORITY_REQUIRED",)
    assert all(
        capture is not None and capture.outcome is DueTerminalOutcome.INCOMPLETE_OBSERVATION
        for capture in captures.values()
    )
    assert {
        capture.failure_codes
        for source_id, capture in captures.items()
        if source_id != "HK-REG-HKEX-RULE-UPDATES" and capture is not None
    } == {("EVIDENCE_CAPTURED_INCOMPLETE",)}

    forged = dict(report)
    forged["execution_policy_fingerprint"] = "sha256:" + "0" * 64
    report_path.write_text(json.dumps(forged, sort_keys=True, separators=(",", ":")))
    with pytest.raises(ValueError, match="SOURCE_ADMISSION_REPORT_INVALID"):
        adapter.capture(
            source_id="HK-REG-HKEX-RULE-UPDATES",
            observation_cutoff="2026-08-27T14:52:09Z",
        )
