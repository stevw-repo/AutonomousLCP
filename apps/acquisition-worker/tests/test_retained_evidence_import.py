"""Offline import of already-verified retained source evidence."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_acquisition_worker import retained_evidence_import
from asklegal_acquisition_worker.acquisition_journal import (
    ImportedCaptureVerifiedPayload,
    JournalTransition,
    LocalAcquisitionJournal,
    WorkItemIdentity,
)
from asklegal_acquisition_worker.retained_evidence_import import (
    RetainedEvidenceImportError,
    RetainedLineageReportPin,
    RetainedReportReference,
    import_known_v1_retained_evidence,
    import_retained_report,
)
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value


class _ExplodingTransport:
    calls: list[object]

    def __init__(self) -> None:
        self.calls = []

    def request(self, *_: object, **__: object) -> None:
        self.calls.append(object())
        msg = "offline import attempted transport"
        raise AssertionError(msg)


def _write_fixture(root: Path) -> RetainedReportReference:
    attempt_id = "judiciary-retained-fixture"
    report_path = root / "attempts" / attempt_id / "report.json"
    objects = root / "objects"
    report_path.parent.mkdir(parents=True)
    objects.mkdir()
    endpoints: list[JsonValue] = []
    for page, terminal_code, status in (
        (362, "CAPTURED", 200),
        (363, "CAPTURED", 200),
        (364, "OUTAGE", 502),
    ):
        body = f"page-{page}".encode()
        digest = sha256(body).hexdigest()
        object_key = f"objects/{digest}.bin"
        (root / object_key).write_bytes(body)
        endpoints.append(
            {
                "body_fingerprint": f"sha256:{digest}",
                "byte_length": len(body),
                "endpoint_id": f"judiciary-year-2011-page-{page}",
                "endpoint_version": "1.0.12",
                "media_type": "text/html",
                "method": "GET",
                "object_key": object_key,
                "requested_url": f"https://legalref.judiciary.hk/search?year=2011&page={page}",
                "status": status,
                "terminal_code": terminal_code,
            }
        )
    transport_attempts: list[JsonValue] = []
    for sequence, endpoint in enumerate(endpoints, start=1):
        assert type(endpoint) is dict
        transport_attempts.append(
            {
                "attempt_number": 1,
                "body_fingerprint": endpoint["body_fingerprint"],
                "byte_length": endpoint["byte_length"],
                "endpoint_id": endpoint["endpoint_id"],
                "endpoint_version": endpoint["endpoint_version"],
                "final_url": (
                    "https://legalref.judiciary.hk/final?year=2011&page=362"
                    if sequence == 1
                    else endpoint["requested_url"]
                ),
                "max_bytes": endpoint["byte_length"],
                "media_type": endpoint["media_type"],
                "method": "GET",
                "object_key": endpoint["object_key"],
                "redirect_rejected": False,
                "requested_url": endpoint["requested_url"],
                "sequence": sequence,
                "start_elapsed_seconds": float((sequence - 1) * 2),
                "status": endpoint["status"],
                "terminal_code": endpoint["terminal_code"],
            }
        )
    execution_policy: dict[str, JsonValue] = {
        "maximum_attempts_per_logical_request": 2,
        "minimum_start_interval_seconds": 2.0,
        "name": "JUDICIARY_TRANSPORT_ATTEMPTS_1.2.0",
        "retry_eligibility": {
            "normalized_transport_failure": {
                "body_byte_length": 0,
                "final_url": None,
                "media_type": "application/octet-stream",
                "redirect_rejected": False,
                "status": 0,
            },
            "publisher_maintenance_outage": {
                "body_byte_length": 255,
                "body_sha256": ("39f0a4df3dc88efbd6216caeaa03dc9fd1acbed9e73a477508e86f7e4229594f"),
                "final_url": "EXACT_REQUESTED_ADMITTED_HTTPS_URL",
                "media_type": "text/plain",
                "redirect_rejected": False,
                "status": 200,
            },
            "publisher_server_error": {
                "body_byte_length": "INTEGER_0_TO_REQUEST_MAX_BYTES",
                "final_url": "EXACT_REQUESTED_ADMITTED_HTTPS_URL",
                "media_type": "ANY_RETAINED_MEDIA_TYPE",
                "redirect_rejected": False,
                "statuses": [500, 502, 503, 504],
            },
        },
    }
    policy_fingerprint = "sha256:6e3f5849e2e7fb60a56b8b5adad35b370c123f017b0cb5854db9e8aeb656590a"
    observation_profile: dict[str, JsonValue] = {
        "elapsed_seconds_limit": 259200.0,
        "minimum_start_interval_seconds": 2.0,
        "request_start_limit": 50000,
        "retained_response_byte_limit": 68719476736,
    }
    profile_fingerprint = "sha256:11dd904c60b673e8445a70b64c748464825142382df472fd07b950cc9ba54cb3"
    report: dict[str, JsonValue] = {
        "attempt_id": attempt_id,
        "authority_manifest_fingerprint": "sha256:" + "a" * 64,
        "authority_provenance": "USER_ATTESTED_PERMISSION_DOCUMENT_PENDING",
        "change_state": "CHANGED_OBSERVED",
        "endpoint_counts": {"CAPTURED": 2, "OUTAGE": 1},
        "endpoints": endpoints,
        "execution_authorization_fingerprint": "sha256:" + "b" * 64,
        "execution_policy": execution_policy,
        "execution_policy_fingerprint": policy_fingerprint,
        "observation_accounting": {
            "elapsed_seconds": 4.0,
            "profile": observation_profile,
            "profile_fingerprint": profile_fingerprint,
            "rejected_response_bytes": 0,
            "request_starts": 3,
            "retained_response_bytes": sum(
                endpoint["byte_length"]
                for endpoint in endpoints
                if type(endpoint) is dict and type(endpoint["byte_length"]) is int
            ),
            "stop_code": None,
        },
        "observation_cutoff": "2026-08-31T11:05:35+08:00",
        "predecessor_attempt_id": None,
        "readback_verified": True,
        "report_schema_version": "1.1.0",
        "result": "SOURCE_OUTAGE",
        "source_family": "JUDICIARY",
        "source_procedures": [
            {
                "declared_member_count": 1,
                "source_id": "HK-CASE-HKLII-DISCOVERY",
                "terminal_code": "COMPLETE",
            },
            {
                "declared_member_count": 0,
                "source_id": "HK-CASE-JUDICIARY-LRS-INVENTORY",
                "terminal_code": "INCOMPLETE",
            },
        ],
        "transport_attempts": transport_attempts,
    }
    raw = canonicalize(checked_json_value(report))
    report_path.write_bytes(raw)
    return RetainedReportReference(
        report_path=report_path,
        expected_report_fingerprint=f"sha256:{sha256(raw).hexdigest()}",
        expected_authority_manifest_fingerprint="sha256:" + "a" * 64,
        expected_execution_authorization_fingerprint="sha256:" + "b" * 64,
        product_family="CASES",
        cycle_id="cyc_20260903_import_cases",
        expected_source_result="SOURCE_OUTAGE",
        expected_imported_item_count=2,
        expected_last_listing=(2011, 363),
    )


def test_imports_retained_capture_without_transport_or_object_copy(tmp_path: Path) -> None:
    """Captured objects are referenced in place without any transport call."""
    retained_root = tmp_path / "retained"
    reference = _write_fixture(retained_root)
    transport = _ExplodingTransport()
    state_root = tmp_path / "state"

    receipt = import_retained_report(
        state_root,
        reference,
        transport=transport,
    )

    assert transport.calls == []
    assert receipt.source_family == "CASES"
    assert receipt.imported_item_count == 2
    assert receipt.reused_object_bytes == len(b"page-362") + len(b"page-363")
    assert receipt.last_listing == (2011, 363)
    assert receipt.archive_pairs is None
    assert tuple(retained_root.glob("objects/*"))
    with LocalAcquisitionJournal(state_root, reference.cycle_id) as journal:
        entries = journal.replay()
        checkpoint = journal.load_checkpoint()
    assert [entry.transition for entry in entries].count(JournalTransition.DISCOVERED) == 2
    assert [entry.transition for entry in entries].count(
        JournalTransition.IMPORTED_CAPTURE_VERIFIED
    ) == 2
    assert all(
        entry.transition not in {JournalTransition.STARTED, JournalTransition.TRANSPORT_STARTED}
        for entry in entries
    )
    assert all(item.attempt_count == 0 for item in checkpoint.items)

    imported = next(
        entry
        for entry in entries
        if entry.transition is JournalTransition.IMPORTED_CAPTURE_VERIFIED
        and entry.work_item.locator.endswith("page=362")
    )
    assert type(imported.payload) is ImportedCaptureVerifiedPayload
    assert imported.payload.final_url == "https://legalref.judiciary.hk/final?year=2011&page=362"


def test_exact_import_is_idempotent(tmp_path: Path) -> None:
    """An exact second import appends nothing and returns the same receipt."""
    reference = _write_fixture(tmp_path / "retained")
    state_root = tmp_path / "state"
    first = import_retained_report(state_root, reference, transport=_ExplodingTransport())
    with LocalAcquisitionJournal(state_root, reference.cycle_id) as journal:
        count = len(journal.replay())
    second = import_retained_report(state_root, reference, transport=_ExplodingTransport())
    with LocalAcquisitionJournal(state_root, reference.cycle_id) as journal:
        assert len(journal.replay()) == count
    assert second == first


@pytest.mark.parametrize("mutation", ["report", "object", "length", "binding"])
def test_tamper_fails_before_first_journal_entry(tmp_path: Path, mutation: str) -> None:
    """Report, object, and binding drift fail before journal publication."""
    retained = tmp_path / "retained"
    reference = _write_fixture(retained)
    if mutation == "report":
        reference = replace(reference, expected_report_fingerprint="sha256:" + "f" * 64)
    elif mutation == "object":
        next((retained / "objects").iterdir()).write_bytes(b"tampered")
    elif mutation == "length":
        raw = reference.report_path.read_bytes()
        report = parse_json_bytes(raw, max_bytes=len(raw))
        assert type(report) is dict
        endpoints = report["endpoints"]
        assert type(endpoints) is list
        assert type(endpoints[0]) is dict
        endpoints[0]["byte_length"] = 9
        changed = canonicalize(checked_json_value(report))
        reference.report_path.write_bytes(changed)
        reference = replace(
            reference,
            expected_report_fingerprint=f"sha256:{sha256(changed).hexdigest()}",
        )
    else:
        reference = replace(
            reference,
            expected_execution_authorization_fingerprint="sha256:" + "f" * 64,
        )
    state_root = tmp_path / "state"

    with pytest.raises(RetainedEvidenceImportError):
        import_retained_report(state_root, reference, transport=_ExplodingTransport())

    entries = state_root / "acquisition-journals" / reference.cycle_id / "entries"
    assert not entries.exists() or tuple(entries.iterdir()) == ()


def test_projection_locator_drift_fails_before_write(tmp_path: Path) -> None:
    """A projection cannot substitute a different request identity."""
    reference = _write_fixture(tmp_path / "retained")
    state_root = tmp_path / "state"

    def collide(retained_record: JsonValue) -> WorkItemIdentity:
        assert type(retained_record) is dict
        return WorkItemIdentity.issue(
            source_family="CASES",
            source_role="RETAINED",
            cycle_id=reference.cycle_id,
            observation_cutoff="2026-08-31T11:05:35+08:00",
            procedure_version="1.0.12",
            locator="https://legalref.judiciary.hk/collision",
            stage="RETAINED_IMPORT",
            parent_id="judiciary-retained-fixture",
            media_type="text/html",
            max_bytes=64,
        )

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_PROJECTION_INVALID"):
        import_retained_report(
            state_root,
            reference,
            projection=collide,
            transport=_ExplodingTransport(),
        )
    assert not (state_root / "acquisition-journals").exists()


def test_object_symlink_is_rejected_before_write(tmp_path: Path) -> None:
    """Retained objects must be regular files reached without aliases."""
    retained = tmp_path / "retained"
    reference = _write_fixture(retained)
    target = next((retained / "objects").iterdir())
    body = target.read_bytes()
    replacement = tmp_path / "replacement.bin"
    replacement.write_bytes(body)
    target.unlink()
    target.symlink_to(replacement)
    state_root = tmp_path / "state"

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_SYMLINK_REJECTED"):
        import_retained_report(state_root, reference, transport=_ExplodingTransport())
    assert not (state_root / "acquisition-journals").exists()


def test_prior_journal_mutation_rejects_idempotent_import(tmp_path: Path) -> None:
    """Idempotence never masks a changed prior journal entry."""
    reference = _write_fixture(tmp_path / "retained")
    state_root = tmp_path / "state"
    import_retained_report(state_root, reference, transport=_ExplodingTransport())
    entries = state_root / "acquisition-journals" / reference.cycle_id / "entries"
    first = entries / "00000000000000000001.json"
    body = first.read_bytes()
    first.write_bytes(body[:-1] + (b"0" if body[-1:] != b"0" else b"1"))

    with pytest.raises(RetainedEvidenceImportError):
        import_retained_report(state_root, reference, transport=_ExplodingTransport())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("change_state", "FABRICATED_SUCCESS"),
        ("source_procedures", []),
        ("unknown_report_field", "accepted-by-shallow-parser"),
    ],
)
def test_resealed_report_semantic_drift_fails_before_write(
    tmp_path: Path,
    field: str,
    value: JsonValue,
) -> None:
    """A caller-updated raw SHA cannot authorize fabricated report semantics."""
    reference = _write_fixture(tmp_path / "retained")
    raw = reference.report_path.read_bytes()
    report = parse_json_bytes(raw, max_bytes=len(raw))
    assert type(report) is dict
    report[field] = value
    changed = canonicalize(checked_json_value(report))
    reference.report_path.write_bytes(changed)
    reference = replace(
        reference,
        expected_report_fingerprint=f"sha256:{sha256(changed).hexdigest()}",
    )
    state_root = tmp_path / "state"

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_REPORT_INVALID"):
        import_retained_report(state_root, reference, transport=_ExplodingTransport())

    assert not (state_root / "acquisition-journals").exists()


def test_resealed_physical_final_url_drift_fails_before_write(tmp_path: Path) -> None:
    """A retained transport ledger cannot substitute a foreign final authority."""
    reference = _write_fixture(tmp_path / "retained")
    raw = reference.report_path.read_bytes()
    report = parse_json_bytes(raw, max_bytes=len(raw))
    assert type(report) is dict
    attempts = report["transport_attempts"]
    assert type(attempts) is list
    assert type(attempts[0]) is dict
    attempts[0]["final_url"] = "https://attacker.invalid/final"
    changed = canonicalize(checked_json_value(report))
    reference.report_path.write_bytes(changed)
    reference = replace(
        reference,
        expected_report_fingerprint=f"sha256:{sha256(changed).hexdigest()}",
    )

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_REPORT_INVALID"):
        import_retained_report(
            tmp_path / "state",
            reference,
            transport=_ExplodingTransport(),
        )

    assert not (tmp_path / "state/acquisition-journals").exists()


def test_resealed_physical_terminal_drift_fails_before_write(tmp_path: Path) -> None:
    """A logical capture must agree with its final physical disposition."""
    reference = _write_fixture(tmp_path / "retained")
    raw = reference.report_path.read_bytes()
    report = parse_json_bytes(raw, max_bytes=len(raw))
    assert type(report) is dict
    attempts = report["transport_attempts"]
    assert type(attempts) is list
    assert type(attempts[0]) is dict
    attempts[0]["terminal_code"] = "OUTAGE"
    changed = canonicalize(checked_json_value(report))
    reference.report_path.write_bytes(changed)
    reference = replace(
        reference,
        expected_report_fingerprint=f"sha256:{sha256(changed).hexdigest()}",
    )

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_REPORT_INVALID"):
        import_retained_report(
            tmp_path / "state",
            reference,
            transport=_ExplodingTransport(),
        )

    assert not (tmp_path / "state/acquisition-journals").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_starts", 999),
        ("retained_response_bytes", 1),
        ("execution_policy_fingerprint", "sha256:" + "f" * 64),
    ],
)
def test_resealed_physical_accounting_drift_fails_before_write(
    tmp_path: Path,
    field: str,
    value: JsonValue,
) -> None:
    """Physical ledger accounting and policy identity are evidence-derived."""
    reference = _write_fixture(tmp_path / "retained")
    raw = reference.report_path.read_bytes()
    report = parse_json_bytes(raw, max_bytes=len(raw))
    assert type(report) is dict
    if field == "execution_policy_fingerprint":
        report[field] = value
    else:
        accounting = report["observation_accounting"]
        assert type(accounting) is dict
        accounting[field] = value
    changed = canonicalize(checked_json_value(report))
    reference.report_path.write_bytes(changed)
    reference = replace(
        reference,
        expected_report_fingerprint=f"sha256:{sha256(changed).hexdigest()}",
    )

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_REPORT_INVALID"):
        import_retained_report(
            tmp_path / "state",
            reference,
            transport=_ExplodingTransport(),
        )

    assert not (tmp_path / "state/acquisition-journals").exists()


def test_successful_physical_attempt_cannot_be_retried(tmp_path: Path) -> None:
    """Only a policy-eligible failure may precede a second physical attempt."""
    reference = _write_fixture(tmp_path / "retained")
    raw = reference.report_path.read_bytes()
    report = parse_json_bytes(raw, max_bytes=len(raw))
    assert type(report) is dict
    attempts = report["transport_attempts"]
    assert type(attempts) is list
    assert type(attempts[0]) is dict
    repeated = dict(attempts[0])
    repeated["attempt_number"] = 2
    attempts.insert(1, repeated)
    for sequence, attempt in enumerate(attempts, start=1):
        assert type(attempt) is dict
        attempt["sequence"] = sequence
        attempt["start_elapsed_seconds"] = float((sequence - 1) * 2)
    accounting = report["observation_accounting"]
    assert type(accounting) is dict
    accounting["request_starts"] = 4
    accounting["retained_response_bytes"] = sum(
        attempt["byte_length"]
        for attempt in attempts
        if type(attempt) is dict and type(attempt["byte_length"]) is int
    )
    accounting["elapsed_seconds"] = 6.0
    changed = canonicalize(checked_json_value(report))
    reference.report_path.write_bytes(changed)
    reference = replace(
        reference,
        expected_report_fingerprint=f"sha256:{sha256(changed).hexdigest()}",
    )

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_REPORT_INVALID"):
        import_retained_report(
            tmp_path / "state",
            reference,
            transport=_ExplodingTransport(),
        )

    assert not (tmp_path / "state/acquisition-journals").exists()


@pytest.mark.parametrize("mutation", ["sequence_bool", "endpoint_count_bool"])
def test_integer_ledger_fields_reject_boolean_coercion(
    tmp_path: Path,
    mutation: str,
) -> None:
    """JSON booleans cannot impersonate integer physical-ledger facts."""
    reference = _write_fixture(tmp_path / "retained")
    raw = reference.report_path.read_bytes()
    report = parse_json_bytes(raw, max_bytes=len(raw))
    assert type(report) is dict
    if mutation == "sequence_bool":
        attempts = report["transport_attempts"]
        assert type(attempts) is list
        assert type(attempts[0]) is dict
        attempts[0]["sequence"] = True
    else:
        counts = report["endpoint_counts"]
        assert type(counts) is dict
        counts["OUTAGE"] = True
    changed = canonicalize(checked_json_value(report))
    reference.report_path.write_bytes(changed)
    reference = replace(
        reference,
        expected_report_fingerprint=f"sha256:{sha256(changed).hexdigest()}",
    )

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_REPORT_INVALID"):
        import_retained_report(
            tmp_path / "state",
            reference,
            transport=_ExplodingTransport(),
        )

    assert not (tmp_path / "state/acquisition-journals").exists()


def test_lineage_pin_rejects_path_traversal() -> None:
    """A lineage attempt identity is one closed path component."""
    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_REFERENCE_INVALID"):
        RetainedLineageReportPin(
            attempt_id="../escape",
            expected_report_fingerprint="sha256:" + "a" * 64,
            predecessor_attempt_id=None,
        )


def test_semantic_inspection_and_hash_use_one_stable_descriptor(tmp_path: Path) -> None:
    """An in-place object replacement cannot split semantic and byte proofs."""
    path = tmp_path / "archive.bin"
    original = b"original-archive"
    replacement = b"replaced-archive"
    assert len(original) == len(replacement)
    path.write_bytes(original)

    def replace_during_inspection() -> None:
        with retained_evidence_import._open_verified_regular(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
            path,
            expected_length=len(original),
            expected_fingerprint=f"sha256:{sha256(original).hexdigest()}",
        ) as stream:
            assert stream.read() == original
            path.write_bytes(replacement)

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_OBJECT_INVALID"):
        replace_during_inspection()


def test_wrong_last_listing_fails_before_write(tmp_path: Path) -> None:
    """A caller's listing expectation is validated before journal publication."""
    reference = replace(
        _write_fixture(tmp_path / "retained"),
        expected_last_listing=(2012, 1),
    )

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_REPORT_INVALID"):
        import_retained_report(
            tmp_path / "state",
            reference,
            transport=_ExplodingTransport(),
        )

    assert not (tmp_path / "state/acquisition-journals").exists()


def test_known_hkel_receipt_derives_archive_member_pair_and_spec_counts(
    tmp_path: Path,
) -> None:
    """Known HKeL counts come from the retained ZIP/spec graph, never caller input."""
    repository_root = Path(__file__).resolve().parents[3]
    transport = _ExplodingTransport()

    receipts = import_known_v1_retained_evidence(
        tmp_path / "state",
        source_admission_root=repository_root / "var/hk-v1/source-admission",
        transport=transport,
    )

    assert transport.calls == []
    assert receipts.hkel.imported_item_count == 56
    assert receipts.hkel.archive_members == 12_858
    assert receipts.hkel.archive_pairs == 3_157
    assert receipts.hkel.publication_specifications == 7
    assert receipts.hkel.semantic_proof_fingerprint.startswith("sha256:")


def test_judiciary_lineage_accounting_drift_fails_before_object_read_or_write(
    tmp_path: Path,
) -> None:
    """A resealed child cannot contradict its exact predecessor accounting."""
    repository_root = Path(__file__).resolve().parents[3]
    source_attempts = repository_root / "var/hk-v1/source-admission/judiciary-attempt-p/attempts"
    retained = tmp_path / "retained"
    target_attempts = retained / "attempts"
    pins: list[RetainedLineageReportPin] = []
    predecessor: str | None = None
    for letter in "pqrstuv":
        attempt_id = f"judiciary-live-baseline-20260831{letter}"
        raw = (source_attempts / attempt_id / "report.json").read_bytes()
        target = target_attempts / attempt_id / "report.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        pins.append(
            RetainedLineageReportPin(
                attempt_id,
                f"sha256:{sha256(raw).hexdigest()}",
                predecessor,
            )
        )
        predecessor = attempt_id
    attempt_id = "judiciary-live-baseline-20260831w"
    raw = (source_attempts / attempt_id / "report.json").read_bytes()
    report = parse_json_bytes(raw, max_bytes=len(raw))
    assert type(report) is dict
    binding = report["continuation_binding"]
    assert type(binding) is dict
    accounting = binding["predecessor_observation_accounting"]
    assert type(accounting) is dict
    assert type(accounting["request_starts"]) is int
    accounting["request_starts"] += 1
    changed = canonicalize(checked_json_value(report))
    report_path = target_attempts / attempt_id / "report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_bytes(changed)
    reference = RetainedReportReference(
        report_path=report_path,
        expected_report_fingerprint=f"sha256:{sha256(changed).hexdigest()}",
        expected_authority_manifest_fingerprint=(
            "sha256:19add305980db4b4b18b2baffbc3550dea1f763d180024825a7ac882894e63e5"
        ),
        expected_execution_authorization_fingerprint=(
            "sha256:7f3510cf6e90bb312af3b93ea5feb4cc97a7dfd56e1a8e6d0be8b1dc0010acea"
        ),
        product_family="CASES",
        cycle_id="cyc_20260903_import_cases",
        expected_source_result="SOURCE_OUTAGE",
        expected_imported_item_count=5_590,
        lineage_report_pins=tuple(pins),
        expected_last_listing=(2011, 363),
    )

    with pytest.raises(RetainedEvidenceImportError, match="RETAINED_LINEAGE_INVALID"):
        import_retained_report(tmp_path / "state", reference, transport=_ExplodingTransport())

    assert not (retained / "objects").exists()
    assert not (tmp_path / "state/acquisition-journals").exists()
