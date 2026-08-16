"""M4 two-phase acquisition-worker conformance tests."""

from dataclasses import replace
from pathlib import Path

import pytest
from asklegal_acquisition_worker import AcquisitionService, PendingObservation
from asklegal_evidence_vault import (
    LocalImmutableVault,
    RecoveryCopier,
    RetentionProfile,
    VaultName,
)
from asklegal_management_register_ports import (
    AcquisitionObservationRecord,
    AcquisitionRecordConflict,
    InMemoryAcquisitionRegister,
)
from asklegal_source_connectors import (
    AuthenticationClass,
    ConnectorRequest,
    EndpointContract,
    HttpMethod,
    RegisteredSource,
    RetryProfile,
    SourcePolicyState,
    SourceRegistry,
    SyntheticConnector,
    SyntheticPage,
    SyntheticResponse,
)

SOURCE_ID = f"src_{'1' * 48}"
ENDPOINT_ID = f"sep_{'2' * 48}"
OBSERVATION_1 = f"obs_{'3' * 48}"
OBSERVATION_2 = f"obs_{'4' * 48}"
RULEBOOK_ID = f"rbp_{'5' * 48}"
PIPELINE_RUN_ID = f"run_{'6' * 48}"
WORK_ITEM_ID = f"wki_{'7' * 48}"


def _request(observation: str = OBSERVATION_1) -> ConnectorRequest:
    return ConnectorRequest(
        PIPELINE_RUN_ID,
        WORK_ITEM_ID,
        observation,
        "2026-08-16T00:00:00Z",
        SOURCE_ID,
        "1.0.0",
        ENDPOINT_ID,
        "1.0.0",
        RULEBOOK_ID,
        "1.0.0",
        HttpMethod.GET,
        f"obs_{'5' * 48}",
        f"snp_{'6' * 48}",
        "old",
        RetryProfile(2, 30, (0, 1), 7, True),
    )


def _response(
    *,
    status: int = 200,
    signal: str = "new",
    body: bytes = b"synthetic-source-content",
    media_type: str = "application/json",
    transient: bool = False,
    authentication_failed: bool = False,
) -> SyntheticResponse:
    return SyntheticResponse(
        status,
        "source.invalid",
        "/source/inventory",
        media_type,
        body,
        len(body),
        "identity",
        "utf-8",
        signal,
        "source.invalid",
        transient,
        authentication_failed,
    )


def _page(*, duplicate: bool = False) -> tuple[SyntheticPage, ...]:
    return (
        SyntheticPage(_response(body=b"page-a"), "START", "page-2", ("a",), 2, "g1"),
        SyntheticPage(
            _response(body=b"page-b"),
            "page-2",
            "END",
            ("a" if duplicate else "b",),
            2,
            "g1",
        ),
    )


def _service(
    tmp_path: Path,
) -> tuple[
    AcquisitionService,
    LocalImmutableVault,
    LocalImmutableVault,
    InMemoryAcquisitionRegister,
]:
    source = RegisteredSource(
        SOURCE_ID,
        "1.0.0",
        "TEST",
        "SYNTHETIC",
        (ENDPOINT_ID,),
        SourcePolicyState.CONFIGURED,
        "local-only",
        "2030-01-01T00:00:00Z",
    )
    endpoint = EndpointContract(
        ENDPOINT_ID,
        "1.0.0",
        SOURCE_ID,
        RULEBOOK_ID,
        "1.0.0",
        "source.invalid",
        "/source/",
        (HttpMethod.GET,),
        ("source.invalid",),
        AuthenticationClass.NONE,
        ("application/json", "text/html"),
        4096,
        3,
        10,
        30,
        True,
        True,
        True,
        ("CONTENT",),
    )
    primary = LocalImmutableVault(tmp_path / "primary", VaultName.PRIMARY)
    recovery = LocalImmutableVault(tmp_path / "recovery", VaultName.RECOVERY)
    register = InMemoryAcquisitionRegister()
    service = AcquisitionService(
        SyntheticConnector(SourceRegistry((source,), (endpoint,))),
        primary,
        register,
        RetentionProfile("synthetic-source", "2030-01-01T00:00:00Z"),
    )
    return service, primary, recovery, register


def _recover_and_record(
    service: AcquisitionService,
    primary: LocalImmutableVault,
    recovery: LocalImmutableVault,
    pending: PendingObservation,
) -> AcquisitionObservationRecord:
    receipt = pending.writer.finalize_recovery(
        RecoveryCopier(primary, recovery),
        RetentionProfile("synthetic-source", "2030-01-01T00:00:00Z"),
    )
    return service.record_after_recovery(pending, receipt)


def test_changed_source_is_registered_only_after_complete_two_vault_receipts(
    tmp_path: Path,
) -> None:
    service, primary, recovery, register = _service(tmp_path)
    pending = service.prepare(_request(), (_response(),), (_page(),))
    with pytest.raises(LookupError):
        register.get_observation(OBSERVATION_1)
    assert pending.primary_manifest.vault is VaultName.PRIMARY
    assert pending.snapshot_id.startswith("snp_")

    record = _recover_and_record(service, primary, recovery, pending)
    assert record.disposition == "SNAPSHOT_PRESERVED"
    assert record.consequence == "LEGAL_PROCESSING_ELIGIBLE"
    assert record.source_snapshot_id == pending.snapshot_id
    assert record.primary_manifest_version == record.recovery_manifest_version
    assert register.get_observation(OBSERVATION_1) == record


def test_no_change_records_no_snapshot_and_authorizes_no_downstream_work(tmp_path: Path) -> None:
    service, primary, recovery, _register = _service(tmp_path)
    pending = service.prepare(_request(), (_response(status=304),))
    record = _recover_and_record(service, primary, recovery, pending)
    assert record.disposition == "COMPLETE_NO_CHANGE"
    assert record.consequence == "NONE"
    assert record.source_snapshot_id == ""
    assert record.scraper_result is None


@pytest.mark.parametrize(
    ("responses", "scraper", "expected"),
    [
        ((_response(status=401, authentication_failed=True),), (), "SOURCE_CONTRACT_REVIEW"),
        ((_response(transient=True), _response(transient=True)), (), "COVERAGE_GAP"),
        (
            (
                _response(
                    body=b"<script>hostile instruction</script>",
                    media_type="text/html",
                ),
            ),
            (),
            "QUARANTINE",
        ),
        ((_response(),), (_page(duplicate=True),), "COVERAGE_GAP"),
    ],
)
def test_failed_changed_and_hostile_inputs_have_exact_fail_closed_paths(
    tmp_path: Path,
    responses: tuple[SyntheticResponse, ...],
    scraper: tuple[tuple[SyntheticPage, ...], ...],
    expected: str,
) -> None:
    service, primary, recovery, _register = _service(tmp_path)
    pending = service.prepare(_request(), responses, scraper)
    record = _recover_and_record(service, primary, recovery, pending)
    assert record.disposition == expected
    assert record.consequence == "NONE"
    assert record.source_snapshot_id == ""
    assert record.issue_id


def test_restart_is_exact_replay_and_conflicting_observation_is_rejected(tmp_path: Path) -> None:
    service, primary, recovery, register = _service(tmp_path)
    first_pending = service.prepare(_request(), (_response(status=304),))
    first = _recover_and_record(service, primary, recovery, first_pending)
    replay_pending = service.prepare(_request(), (_response(status=304),))
    replay = _recover_and_record(service, primary, recovery, replay_pending)
    assert replay == first

    with pytest.raises(AcquisitionRecordConflict):
        register.record_observation(replace(first, input_fingerprint="sha256:" + "f" * 64))


def test_recovery_receipt_for_another_observation_cannot_finalize_pending(tmp_path: Path) -> None:
    service, primary, recovery, _register = _service(tmp_path)
    first = service.prepare(_request(OBSERVATION_1), (_response(status=304),))
    other = service.prepare(_request(OBSERVATION_2), (_response(status=304),))
    wrong_receipt = other.writer.finalize_recovery(
        RecoveryCopier(primary, recovery),
        RetentionProfile("synthetic-source", "2030-01-01T00:00:00Z"),
    )
    with pytest.raises(ValueError, match="pending manifest"):
        service.record_after_recovery(first, wrong_receipt)
